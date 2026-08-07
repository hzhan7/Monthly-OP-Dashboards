# -*- coding: utf-8 -*-
"""Interactive Brokers (IBKR) 月度经营指标 —— 网页看板 payload 生成器。

由独立仓 `ibkr-monthly-metrics/build_data.py` 移植而来：**图一张都没改**（Exhibit 2-18
的序列、标题文案、图注、断点、截轴逐字照搬），只做两件事——

  1. payload 顶层换成 monthly-op-dashboards 的统一契约（`window.DASH`，见 build/CONTRACT.md）：
     加 ticker/tracker/title/through_label/subtitle/notes/footer，去掉 month_name/footnote/window。
  2. 汇总表的行从 `{lab,cur,prev,yag,mm,yy,mode,inv,pctile}` 改成 `cells[]` 形式。
     **原来写在 index.html 那段 JS 里的格式化口径一并搬到 Python 侧**：
     比率类差异用 pp/bp（|v|<1 用 bp）、反向指标（inv）决定绿红、分位对反向指标要反转后
     再判高低、单调序列不给分位。页面只排版，不做任何计算。

═══ 数据源 ═══
  · `series/ibkr.csv` —— 历史指标表（2016-01 起逐月，官方原始单位），由 fetch/ibkr.py 落库。
    **所有存量/流量指标都从这里读**，本模块不下载、不自己解析历史 PDF 的数字。
  · `cache/ibkr/pr_YYYYMM.pdf` —— 月度新闻稿，佣金与平均订单规模
    （历史指标表里没有这两列，CSV 也就没有）。解析函数复用 `fetch/ibkr_source.py::parse_pr`，
    不重写：解析口径只能有一处定义，各写一份迟早分叉，而分叉的表现是
    「fetch 落库的数与网页画出来的 CPT 对不上同一个月」——最难发现的那种错。
    （`ibkr_source.py` 搬自已删除的 `/IBKR月度指标` skill 的 `build_report.py`，逐字复制。）
  · `cache/ibkr/hist_latest.pdf` —— 只取 Notes 段的**文字**
    （账户口径调整的原文），用作护栏与图注；一个数字都不从这里取。

═══ 口径 ═══
  历史指标表首个区块 "(in Thousands, except Trading Days)" —— 账户/DARTs/合约/股数以千计；
  第二区块 "(in Billions)" —— 客户权益/现金/融资余额。
  新闻稿 Key products 两列 = Average Order Size（股/张）与 Average Commission per Cleared
  Commissionable Order（$/笔），**不是每股/每张单价**。

═══ 窗口 ═══
  Exhibit 2-13   最近 13 个月（从 CSV 最新月倒推，不依赖构建当天日期）
  Exhibit 14-18  2016-01 起全历史
  Exhibit 1 的 3Y %ile 取近 36 个月

构建日期只写文件首行注释，不进 payload —— 进了 payload，monthly_run 的
「data 有没有实质变化」检查（忽略首行的正文比较）就永久失效，每天都会产出一个
内容相同、只有日期变了的 no-op commit。
"""
import csv
import datetime
import importlib.util
import json
import os
import re

import numpy as np
import pandas as pd

import brief as B
import payload_guard
import pctile
import yoy            # 同比口径的唯一实现（build/yoy.py）：本页不再自己写一份滚动同比

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
PIPELINE = os.path.join(ROOT, 'fetch', 'ibkr_source.py')
CACHE = os.path.join(ROOT, 'cache', 'ibkr')

SRC = ('Source: Company data (IBKR monthly brokerage metrics); '
       'chart format after Goldman Sachs GIR')

# ── 账户口径的一次性调整（历史指标 PDF 的 Notes 段，解析器的数字正则抓不到）──
# 键 = 'YYYY-MM'；field 指明这条脚注调的是哪条序列：
#   'net_new'  —— 表内 Net New Accounts 就是账户差分，真实增长另有其数，画 y/y 必须用 real
#   'accounts' —— 调的是 Total Accounts 的**存量口径**，net_new 那一行已经是真实值
# reported/real 单位与表内一致（千户）。三条都逐字核对过 hist_latest.pdf 的 Notes 原文。
ADJ = {
    # 第 2 页 Notes(1)：real growth 87.7 vs calculated 74.4，差额 13.3 上交政府
    '2025-03': {'field': 'net_new', 'reported': 74.4, 'real': 87.7,
                'reason': '13.3k 账户按法律要求上交政府（escheat），被计进了账户差分'},
    # 第 2 页 Notes(1)：real growth 111.9 vs calculated 73.1，差额 38.8 来自一家 IB 撤出
    '2025-09': {'field': 'net_new', 'reported': 73.1, 'real': 111.9,
                'reason': '一家 introducing broker（Futu 子公司）撤出，带走 38.8k 账户'},
    # 第 3 页 Notes(1)：Total Accounts at Nov 30, 2024 下调 9.1k（为受制裁证券开的非交易账户）。
    # 核对算术：accounts 3,249.1 − 3,185.4 = 63.7，而表内 net_new = 72.8，差 9.1 正是这笔下调，
    # 即**净新增那一行已经是还原后的真实值**，只有账户存量序列在 2024-11 有一个向下的台阶。
    # 所以这条不改 net_new，只作为脚注渲染出来（也用于「有脚注必须有登记」的护栏）。
    '2024-11': {'field': 'accounts', 'level_adj': -9.1,
                'reason': '2024-11-30 的 Total Accounts 下调 9.1k（两年间为受制裁证券开立、不可交易）'},
}

# IBKR 写这类脚注的四种固定措辞。命中即视为「该月有口径调整」，必须在 ADJ 里有登记。
NOTE_RE = re.compile(r'real account growth|adjusted downward|escheat|withdraw', re.I)
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
          'July', 'August', 'September', 'October', 'November', 'December']
MONTH_RE = re.compile(r'\b(' + '|'.join(MONTHS) + r')\b\s+(?:\d{1,2}\s*,\s*)?(20\d{2})')

COLS = ['trading_days', 'accounts', 'net_new', 'darts', 'ann_dart_acct',
        'opt_contracts', 'fut_contracts', 'stk_shares', 'equity', 'credits', 'margin']


def load_pipeline():
    """只为拿 parse_pr（新闻稿解析）——历史指标的数字一律走 series/ibkr.csv。

    按路径加载而不是 `import ibkr_source`：管道文件在 fetch/ 下，本脚本以子进程方式
    跑（sys.path[0] 是 build/），裸 import 找不到它。
    """
    if not os.path.exists(PIPELINE):
        raise SystemExit(f'找不到解析管道: {PIPELINE}')
    spec = importlib.util.spec_from_file_location('ibkr_source', PIPELINE)
    br = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(br)
    return br


def month_add(y, m, delta):
    t = y * 12 + (m - 1) + delta
    return t // 12, t % 12 + 1


def read_series():
    """series/ibkr.csv → {'YYYY-MM': {列: float}}。缺列直接失败，不静默补 None。"""
    path = os.path.join(SERIES, 'ibkr.csv')
    if not os.path.exists(path):
        raise SystemExit(f'找不到 {path}')
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit('series/ibkr.csv 是空的')
    missing = [c for c in COLS if c not in rows[0]]
    if missing:
        raise SystemExit(f'series/ibkr.csv 缺列: {missing}')
    out = {}
    for r in rows:
        key = r['month'].strip()
        if not re.fullmatch(r'20\d{2}-\d{2}', key):
            raise SystemExit(f'series/ibkr.csv 月份格式异常: {r["month"]!r}')
        out[key] = {c: (float(r[c]) if r[c] not in ('', None) else None) for c in COLS}
    return out


def parse_hist_notes(page):
    """抓历史指标 PDF 每页 'Notes:' 到页脚之间、与口径调整有关的条目原文。

    ibkr_source.parse_hist_page 用的是整串锚定的数字正则，Notes 段的长句一句都命中不了，
    于是「表内差分 ≠ 真实账户增长」这类说明被整段丢弃，Ex3 就挂着 +22pp 的错值而
    页面上没有任何痕迹。这里单独再抓一遍：既渲染到页面上，也用来做护栏——
    命中脚注却没在 ADJ 里登记的月份直接 raise，宁可月度 routine 失败也不静默发错图。
    """
    t = page.get_text()
    i = t.find('Notes:')
    if i < 0:
        return []
    seg = re.split(r'Page \d+ of \d+', t[i + len('Notes:'):])[0]
    out = []
    # Notes 段是 (1)(2)(3) 编号条目；按编号切而不是按句号切——正文里有 "vs." 这种缩写，
    # 按句号切会把「real account growth in September 2025 was 111.9 ... vs.」拦腰截断。
    for part in re.split(r'\(\d\)\s*', seg):
        s = ' '.join(part.split())
        if not s or not NOTE_RE.search(s):
            continue
        ms = sorted({f'{y}-{MONTHS.index(mo) + 1:02d}' for mo, y in MONTH_RE.findall(s)})
        out.append({'text': s, 'months': ms})
    return out


def pctf(x, d=0):
    """与 build_report.py 的 pctf 一致，另加一条：**四舍五入后为 0 时不带符号**。

    原式对 x = -0.002 给出 '-0%'。负零是格式化产物不是数据，夹在一片两位整数里特别扎眼，
    读者会停下来猜它是不是缺失值（同一个毛病在 tsm Ex13 / exchanges Ex8 被人眼审查逮到）。
    除这一种输入外输出与从前逐字符相同。"""
    s = f'{x * 100:.{d}f}'
    if float(s) == 0:
        s = f'{0.0:.{d}f}'
        return s + '%'
    return ('+' if float(s) > 0 else '') + s + '%'


def comma(v, d=0):
    """同上：'-0.0' 这类负零一律去掉负号。"""
    s = f'{v:,.{d}f}'
    if s.startswith('-') and float(s.replace(',', '')) == 0:
        s = s[1:]
    return s


def signed(v, d, unit):
    """汇总表的变化文本。四舍五入后为 0 时不带符号（'-0.0%' / '-0bp' 是负零产物）。"""
    s = f'{v:+.{d}f}'
    if float(s) == 0:
        s = f'{0.0:.{d}f}'
    return s + unit


# ────────────────── 12 个月滚动合计同比（流量类的默认口径）──────────────────
# 单月同比的分母是**去年那一个月**。净新增账户、cleared DARTs 这类流量的月度分布
# 带季节性与一次性事件（escheat、introducing broker 撤出、行情月），分母越小，
# 同一笔绝对变化被放大得越狠 —— 这不是业务信号，是除法的性质。
# 本页实测（对齐到两种口径都算得出的同一批月份）：13 个月窗口内净新增账户的单月同比
# 标准差是滚动口径的 4.3 倍，相邻月最大跳变 95pp vs 9pp；全历史 104 个可比月里
# 25 个月两种口径符号相反（2021-04 单月 −26%、滚动 +217%，差 242pp）。
# 本页早就有一条现成的滚动口径线 —— Exhibit 15 画的就是 T12M 净新增账户，
# Exhibit 3 的新口径正是那条线的同比，两张图从此对得上。
#
# ⚠ 只对**流量**这么改。存量 / 期末口径（账户总数、客户权益、客户现金、融资余额）
# 不做滚动**合计**（那对存量是个假名字）。本页实测：客户现金换成 12 个月均值同比，
# 标准差从 2.8pp 涨到 3.6pp（更吵）。
# ⚠ 一条更正（2026-08-07）：早先本文件写过「存量不许做滚动合计，所以只能点对点」。
# **后半句是假的**：Σ12/Σ12′ 里的除数约掉，12 个月滚动**合计**比恒等于 12 个月滚动
# **均值**比（build/yoy.py 实测两者差 2.3e-14），而「去年一整年的平均客户权益 vs 前年」
# 是个真实存在、可以核对的量。错的只是**「合计」这个名字**（12 个月末余额相加不指代
# 任何东西）。所以存量**可以**平滑，本页仍保留点对点，理由由**本序列实测**给出。
def _S(v, keys):
    """numpy 数组 + 月份键 → pandas Series，好喂给共享模块 build/yoy.py。

    ALL 是逐月连续的（main() 开头已经硬校验过），所以 rolling / shift 按位置算
    就等于按月份算 —— 缺月会让这个等式失效，那正是那道校验存在的原因。
    """
    return pd.Series(np.asarray(v, float), index=list(keys))


def roll_yoy_arr(v, keys):
    """12 个月滚动合计同比（**小数**，与本页 yoy() / pctf() 的约定一致）—— 流量类。"""
    return yoy.ttm_yoy(_S(v, keys), yoy.FLOW).values / 100.0


def mono_yoy_arr(v, keys):
    """点对点（单月）同比（小数）。"""
    return yoy.mom_yoy(_S(v, keys), yoy.FLOW).values / 100.0


def mean_yoy_arr(v, keys):
    """12 个月滚动**均值**同比（小数）—— 存量类唯一说得通的平滑口径。

    数值上与滚动合计比完全相同（除数约掉），差别只在**说法**：对存量，
    「12 个月合计」不指代任何真实的量，「去年一整年的平均余额」才是。
    本页只拿它做反事实对照，图上画的仍是点对点。
    """
    return yoy.ttm_mean_yoy(_S(v, keys), yoy.STOCK).values / 100.0


def cal_stats(mono, roll, pos, keys):
    """两种口径的实测对比。返回 None 表示可比月份不足 3 个。

    ⚠ **必须先对齐到两种口径都算得出的同一批月份**：滚动口径天然少掉头 12 个月，
    不对齐就是拿两个不同样本比波动，样本效应会伪装成口径效应。
    """
    keep = [i for i in pos if np.isfinite(mono[i]) and np.isfinite(roll[i])]
    if len(keep) < 3:
        return None
    A = np.array([mono[i] for i in keep]) * 100
    B = np.array([roll[i] for i in keep]) * 100
    jump = lambda x: float(np.abs(np.diff(x)).max()) if len(x) > 1 else float('nan')
    return {'n': len(keep), 'sd_m': float(A.std()), 'sd_r': float(B.std()),
            'jump_m': jump(A), 'jump_r': jump(B),
            'flips': [(keys[i], float(A[j]), float(B[j]))
                      for j, i in enumerate(keep) if A[j] * B[j] < 0],
            'lo_m': float(A.min()), 'hi_m': float(A.max()),
            'lo_r': float(B.min()), 'hi_r': float(B.max()),
            'cur_m': float(A[-1]), 'cur_r': float(B[-1]),
            'first': keys[keep[0]], 'last': keys[keep[-1]]}


def roll_note(st):
    """流量类：为什么用 12 个月滚动合计同比 —— 数字全部来自本页自己的序列，现算。"""
    head = ('本图的同比是 <b>12 个月滚动合计同比</b>（本年 12 个月合计 ÷ 上年同 12 个月合计 − 1），'
            '不是单月同比。')
    if st is None:
        return head + '本序列两种口径都算得出的月份不足 3 个，暂不给对比数字。'
    ratio = st['sd_m'] / st['sd_r'] if st['sd_r'] else float('nan')
    t = (head + f'实测：把两种口径<b>对齐到同一批月份</b>后（{st["first"]}–{st["last"]}，'
         f'{st["n"]} 个月），单月同比标准差 {st["sd_m"]:,.1f}pp、滚动口径 {st["sd_r"]:,.1f}pp'
         f'（{ratio:,.2f} 倍），相邻月最大跳变 {st["jump_m"]:,.0f}pp vs {st["jump_r"]:,.0f}pp')
    if st['flips']:
        w = max(st['flips'], key=lambda f: abs(f[1] - f[2]))
        t += (f'，{len(st["flips"])} 个月两种口径<b>符号相反</b>'
              f'（最极端的 {w[0]}：单月 {w[1]:+,.0f}% vs 滚动 {w[2]:+,.0f}%，'
              f'差 {abs(w[1] - w[2]):,.0f}pp）')
    else:
        t += '，本窗口内两种口径没有符号相反的月份'
    return (t + f'。当期并排：单月 {st["cur_m"]:+,.1f}%、滚动 {st["cur_r"]:+,.1f}%'
            f'（差 {abs(st["cur_m"] - st["cur_r"]):,.0f}pp）。')


def stock_note(st, what):
    """**存量**序列保留点对点（单月）同比的理由 —— 事实要说对，数字要现算。

    对照口径是 12 个月滚动**均值**同比（yoy.ttm_mean_yoy），不是「合计」：
    对存量，「12 个月合计」不指代任何真实的量，是个假名字；而均值口径
    （去年一整年的平均余额 vs 前年）是合法的，所以不换必须给实测理由。
    """
    base = (f'本图的同比是<b>点对点（单月）同比</b>（本月末 ÷ 去年同月末 − 1）。'
            f'{what}是<b>期末存量</b>；存量并非不能平滑 —— 合法的平滑口径是 '
            '<b>12 个月滚动均值同比</b>（去年一整年的平均余额 vs 前年；数值上等同于'
            '滚动合计比，除数约掉了），<b>但不能叫「12 个月合计同比」</b>，'
            '因为 12 个月末余额相加不指代任何真实的量。本图不换的理由是实测：')
    if st is None:
        return base + '本序列两种口径都算得出的月份不足 3 个，暂不给对照数字。'
    ratio = st['sd_m'] / st['sd_r'] if st['sd_r'] else float('nan')
    verdict = ('<b>均值口径在这条序列上反而更吵</b>' if ratio < 1 else
               '均值口径确实更平滑，但按构造滞后约半年、回答的是另一个问题'
               '（「去年一整年的平均水平」而非「现在相对去年此刻」）')
    return (base + f'对齐到同一批月份后（{st["n"]} 个月），点对点同比标准差 '
            f'{st["sd_m"]:,.1f}pp、12 个月均值同比 {st["sd_r"]:,.1f}pp（{ratio:,.2f} 倍），'
            f'相邻月最大跳变 {st["jump_m"]:,.1f}pp vs {st["jump_r"]:,.1f}pp，'
            f'两种口径符号相反的月份 {len(st["flips"])} 个 —— {verdict}。噪声用轴范围解决。')


def compose_brief(ALL, acc, eq, cr, mg, ann, nn, dart, td, opt, fut, stk):
    """IBKR 页顶部的 ~300 字数据总结（payload 的 `brief` 字段）。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R3 日历护栏 /
    R4 单位恒等 / R5 标注 / R6 有效位），那边只算事实，句子在这里拼 ——
    措辞是口径的一部分，属于各家自己。

    每个数字都是当场从序列算出来的，**没有一处硬编码**：排名、「几个月最低」、
    「峰值停在哪个月」下月重跑都会自己变。

    ═══ IBKR 独有，别家不能照抄 ═══
      · `ann_dart_acct` 的分母是 **cleared** 账户，而 `darts` 含 non-cleared，
        两者不同源。所以文中保留「cleared」一词，且全篇不做 darts ÷ accounts
        这类跨口径除法（Exhibit 13 的图注讲的就是这个推导误差）。
      · `net_new` 的 2025-03 / 2025-09 一次性调整（见 ADJ）是 IBKR 专有，
        排名一律按**还原口径**算，句子里必须写「（还原口径）」。
      · R3 日历护栏在这里成立，是因为 opt/fut/stk 三列是**当月合计**。
        月末时点值（融资余额、客户现金）没有日历效应，硬套会造出一个假修正。

    ═══ 与本页 2026-08 同比口径改造的关系（移植时的口径适配）═══
      远端写这一段时全页还是单月同比；本地 Exhibit 2 / 3 / 4 / 5 已改
      **12 个月滚动合计同比**，汇总表 y/y 列保留单月（表内算术恒等）。适配照
      CONTRACT §6 与 cboe 的先例：brief 引用的单月同比一律标「单月」
      （与汇总表同口径，可逐格对上），只作位置与基数陈述；净新增那句要下
      「不是塌方」的趋势判断，趋势归滚动口径，故单月 / 滚动两个读数并排印、
      各带标签 —— 与页尾「当期各口径并排现算」同一条规矩，只印单月会让读者
      拿它去对 Exhibit 3 的线，对不上还以为哪边算错了。存量（户均现金的
      分子分母）本页图上本就是点对点，标「单月」只为与全页措辞统一。
    """
    i = len(ALL) - 1
    n = len(ALL)

    # ── R1：存量峰值扫描。账户数几乎只增不减，本该被 is_monotonic 挡掉，
    #    但「四个总量里只有它创新高」正是本月要讲的事，故显式不跳过。
    pk = B.peak_scan(ALL, [('账户', acc), ('权益', eq), ('现金', cr), ('融资', mg)], i,
                     skip_monotonic=False)
    s1 = (f'{B.mo(ALL[i])}月末账户<b>{B.num(acc[i], 1)}千户</b>为{n}个月最高，'
          f'是{B.cn(len(pk["at_peak"]) + len(pk["off_peak"]))}个总量指标里唯一创新高的：'
          f'{"、".join(nm for nm, _ in pk["off_peak"])}峰值停在{B.peak_months_txt(pk["off_peak"])}月。')

    # ── R2：净新增的基数护栏。名次按还原口径排（见 ADJ）。
    #    单月同比（base_effect 的 yy）与 12 个月滚动同比（Exhibit 3 的口径）并排给，
    #    见 docstring「口径适配」一段。
    be = B.base_effect(nn, i)
    r3 = roll_yoy_arr(nn, ALL)[i]
    trend = (f'单月同比{B.pct(be["yy"])}、12个月滚动同比{B.pct(r3)}（Exhibit 3口径）'
             if B.need(r3) else f'单月同比{B.pct(be["yy"])}')
    s2 = (f'净新增{B.num(nn[i], 1)}千户（还原口径）排历史第{be["rank"]}；'
          f'环比从{B.mo(ALL[i - 1])}月{B.num(nn[i - 1], 1)}千户跌{abs(be["mm"]) * 100:.1f}%，'
          f'但{B.mo(ALL[i - 1])}月是全样本'
          f'{"最高月" if be["prev_is_max"] else f"第{be['prev_rank']}高月"}，'
          f'{trend}，<b>只看环比会误读成塌方</b>。')

    # ── R3：opt/stk 是当月合计，交易日多一天会把跌幅整体盖住一截。
    co, cs = B.calendar_split(opt, td, i), B.calendar_split(stk, td, i)
    gap = B.months_since_lower(cs['series'], i)
    s3 = (f'先扣日历：{B.mo(ALL[i])}月{td[i]:.0f}个交易日比{B.mo(ALL[i - 1])}月多'
          f'{co["dday"]:.0f}天，期权表面跌{abs(co["raw"]) * 100:.1f}%、'
          f'日均实跌{abs(co["per_day"]) * 100:.1f}%，'
          f'股票日均跌{abs(cs["per_day"]) * 100:.1f}%为{gap}个月最低。')

    # ── R4：分母侧。期间均值对期间均值，不与单月读数混用；三条成交量列先日均化。
    rg = B.regime_ratio(ALL, [('账户', acc), ('净新增', nn), ('总DARTs', dart),
                              ('人均年化cleared DART', ann), ('期权/日', opt / td),
                              ('期货/日', fut / td), ('股票/日', stk / td),
                              ('权益', eq), ('现金', cr), ('融资', mg)], i)
    pu = B.per_unit(cr, acc, i, scale=1e9 / 1e3)      # 户均现金：$bn ÷ 千户 → 美元
    s4 = (f'分母：{B.cn(len(rg["ratios"]))}个指标只有{"、".join(rg["down"])}相对起点下行'
          f'（{rg["y0"]}年均{np.nanmean(ann[rg["base_idx"]]):.1f}倍→'
          f'近13个月{np.nanmean(ann[rg["win_idx"]]):.1f}倍）；'
          f'户均现金（推导值）<b>{B.usd(pu["value"])}</b>'
          f'为{n}个月{"最低" if pu["is_min"] else "低位"}，单月同比{B.pct(pu["yoy"])}，'
          f'是客户现金{B.pct(pu["num_yoy"])}除以账户{B.pct(pu["den_yoy"])}的商，属摊薄而非撤资。')

    return B.render([s1, s2, s3, s4])


def main():
    br = load_pipeline()
    import fitz

    series = read_series()

    # ── 历史指标 PDF 的 Notes 段：只取文字（护栏 + 图注），数字全部来自 CSV ──
    hist_pdf = os.path.join(CACHE, 'hist_latest.pdf')
    if not os.path.exists(hist_pdf):
        raise SystemExit(f'找不到 {hist_pdf}（先跑 fetch/ibkr.py 落缓存）')
    doc = fitz.open(hist_pdf)
    notes = []
    for i in range(doc.page_count):
        notes.extend(parse_hist_notes(doc[i]))

    # 护栏：脚注点名的月份必须在 ADJ 里有登记，否则整个 routine 失败
    flagged = sorted({m for nt in notes for m in nt['months']})
    unknown = [m for m in flagged if m not in ADJ]
    if unknown:
        raise SystemExit(
            f'历史指标 PDF 的 Notes 提到 {unknown} 有账户口径调整，但 build/ibkr.py 的 ADJ 表里没有登记。\n'
            f'请照 PDF 原文补 ADJ 条目后再跑（宁可失败也不要把未还原的 y/y 发上线）。\n'
            + '\n'.join('  · ' + nt['text'] for nt in notes))

    # ── 目标月 = 最新有 trading_days 的月份 ──
    avail = sorted(k for k, v in series.items() if v.get('trading_days'))
    if not avail:
        raise SystemExit('series/ibkr.csv 里没有可用月份')
    target = avail[-1]
    ty, tm = int(target[:4]), int(target[5:7])

    # ── 全历史轴（Exhibit 14-18）：必须逐月连续，否则 12 个月滚动和与 y/y 会错位 ──
    ALL = avail
    for i in range(1, len(ALL)):
        py, pmo = month_add(int(ALL[i - 1][:4]), int(ALL[i - 1][5:7]), 1)
        if f'{py}-{pmo:02d}' != ALL[i]:
            raise SystemExit(f'历史序列不连续: {ALL[i-1]} → {ALL[i]}')
    XL_LONG = [f'{int(k[5:7])}/{k[2:4]}' for k in ALL]

    # 还原后的净新增账户：y/y 的分子分母一律用 real
    real_nn = {k: series[k]['net_new'] for k in ALL}
    for k, a in ADJ.items():
        if a['field'] == 'net_new' and k in real_nn:
            real_nn[k] = a['real']

    # ── 13 个月窗口 ──
    WIN, XL = [], []
    for d in range(-12, 1):
        y, m = month_add(ty, tm, d)
        WIN.append(f'{y}-{m:02d}')
        XL.append(f'{m}/{y % 100:02d}')
    prevm, yagm = {}, {}
    for i, w in enumerate(WIN):
        y, m = month_add(ty, tm, -13 + i)
        prevm[w] = f'{y}-{m:02d}'
        yagm[w] = f'{int(w[:4])-1}-{w[5:]}'

    need = set(WIN) | set(prevm.values()) | set(yagm.values())
    missing = sorted(w for w in need if w not in series)
    if missing:
        raise SystemExit(f'series/ibkr.csv 缺月份: {missing}')

    # ── 月度新闻稿（佣金与订单规模）：只读缓存，不下载（下载是 fetch/ibkr.py 的职责）──
    COMM = {}
    for w in WIN:
        p = os.path.join(CACHE, f'pr_{w.replace("-", "")}.pdf')
        # 判有效而不只判存在：下载失败会在磁盘上留下 0 字节残骸，只判 exists 会放它过去，
        # 然后 br.parse_pr 崩在 EmptyFileError —— 报错点离真正的病因（一次瞬时 404）很远。
        if not os.path.exists(p) or os.path.getsize(p) < 5000:
            raise SystemExit(f'新闻稿缓存缺失或损坏 {p}（删掉它再跑 fetch/ibkr.py）')
        COMM[w] = br.parse_pr(p)

    # 数据源发布日：先查台账 series/source_dates.csv（fetch/ibkr.py 摄入该月时按月份钉进去的）。
    # 台账优先于当场解析，因为 cache/ 是 gitignore 的、随时可以清 —— 清掉之后当场解析
    # 会让抬头那半句静默消失。下面两条回落保留着，用于台账还没有记录的历史月份。
    source_date = None
    try:
        import importlib.util
        _spec = importlib.util.spec_from_file_location(
            'source_dates', os.path.join(ROOT, 'source_dates.py'))
        _sd = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_sd)
        source_date = _sd.lookup(os.path.join(ROOT, 'series'), 'ibkr', target)
    except Exception:
        pass
    if not source_date:
        try:
            prt = fitz.open(os.path.join(CACHE, f'pr_{target.replace("-", "")}.pdf'))[0].get_text()
            mdl = re.search(r'\b(' + '|'.join(MONTHS) + r')\s+(\d{1,2}),\s*(20\d{2})\s*[—–-]', prt)
            if mdl:
                source_date = f'{mdl.group(3)}-{MONTHS.index(mdl.group(1)) + 1:02d}-{int(mdl.group(2)):02d}'
        except Exception:
            pass
    if not source_date:
        cd = (doc.metadata or {}).get('creationDate') or ''
        m = re.match(r'D:(\d{4})(\d{2})(\d{2})', cd)
        if m:
            source_date = f'{m.group(1)}-{m.group(2)}-{m.group(3)}'

    # ── 派生序列（逐行照抄 build_report.py 的算法）──
    S = lambda f: np.array([series[m][f] for m in WIN], float)
    cpt = np.array([COMM[m][0] for m in WIN])
    stk_os = np.array([COMM[m][1] for m in WIN]); stk_cpt = np.array([COMM[m][2] for m in WIN])
    opt_os = np.array([COMM[m][3] for m in WIN]); opt_cpt = np.array([COMM[m][4] for m in WIN])
    fut_os = np.array([COMM[m][5] for m in WIN]); fut_cpt = np.array([COMM[m][6] for m in WIN])

    net_new = S('net_new')                                   # Ex2 画的是表内披露值
    nn_real = np.array([real_nn[m] for m in WIN])            # Ex3 的 y/y 用还原值
    nn_yoy = np.array([real_nn[m] / real_nn[yagm[m]] - 1 for m in WIN])
    ann_dart = S('ann_dart_acct'); accounts = S('accounts')
    acct_prev = np.array([series[prevm[m]]['accounts'] for m in WIN])
    cleared = ann_dart / 252 * (accounts + acct_prev) / 2
    # 量纲：cleared（千笔/日）× cpt（$/笔）= 千美元/日；÷1000 → 百万美元/日（$mn/day）
    comm_day = cleared * cpt / 1000
    margin = S('margin'); credits = S('credits')
    # GS 规矩 2：融资余额与客户现金都不是高增速指标，m/m 只是 ±2% 噪音，改画 y/y
    marg_yoy = margin / np.array([series[yagm[m]]['margin'] for m in WIN]) - 1
    cred_yoy = credits / np.array([series[yagm[m]]['credits'] for m in WIN]) - 1
    td = S('trading_days')
    stk_d = S('stk_shares') / stk_os / td
    opt_d = S('opt_contracts') / opt_os / td
    fut_d = S('fut_contracts') / fut_os / td
    pct_fo = (opt_d + fut_d) / (stk_d + opt_d + fut_d)
    darts_win = S('darts')
    cov_prod = (stk_d + opt_d + fut_d) / darts_win * 100      # 推导产品 DARTs 对披露总量的覆盖率
    cov_cleared = cleared / darts_win * 100

    avg12 = lambda a: float(np.mean(a[:12]))
    yoy = lambda a: float(a[-1] / a[0] - 1)
    mom = lambda a: float(a[-1] / a[-2] - 1)
    L = lambda a: [round(float(v), 6) for v in a]
    LN = lambda a: [None if v is None or not np.isfinite(v) else round(float(v), 6) for v in a]

    # ── 全历史派生序列（Exhibit 14-18）──
    A = lambda f: np.array([series[m][f] if series[m][f] is not None else np.nan for m in ALL], float)
    ann_all, acc_all, eq_all = A('ann_dart_acct'), A('accounts'), A('equity')
    cr_all, mg_all, dart_all = A('credits'), A('margin'), A('darts')
    nn_all = np.array([real_nn[m] for m in ALL], float)
    # 顶部 brief 的日历护栏（R3）要的三条：交易日数与两条**当月合计**成交量列。
    # 用原始合约数／股数而不是 Ex8 的 product DARTs —— 后者要除以新闻稿里的平均订单
    # 规模，而新闻稿本地只缓存 13 个月，长历史那半段算不出来。
    td_all, opt_all = A('trading_days'), A('opt_contracts')
    fut_all, stk_all = A('fut_contracts'), A('stk_shares')

    roll12 = np.full(len(ALL), np.nan)
    for i in range(11, len(ALL)):
        roll12[i] = nn_all[i - 11:i + 1].sum()
    cleared_all = np.full(len(ALL), np.nan)
    cleared_all[1:] = ann_all[1:] / 252 * (acc_all[1:] + acc_all[:-1]) / 2
    # 右轴画「未清算占比」而不是 cleared/total 本身：bar_line_dual 的右轴强制含 0，
    # 84%~92% 的序列会被压在轴顶 8% 的高度里，2025 那个台阶只剩 3px。取补数后量程
    # 0-16%，台阶清清楚楚，信息一模一样（两者相加恒为 100%）。
    noncl_all = 100 - cleared_all / dart_all * 100
    cr_share = cr_all / eq_all * 100
    mg_share = mg_all / eq_all * 100

    def yr_mean(arr, yr):
        idx = [i for i, k in enumerate(ALL) if k[:4] == yr]
        return float(np.nanmean(arr[idx])) if idx else float('nan')

    pre25 = [i for i, k in enumerate(ALL) if k < '2025-01']
    post25 = [i for i, k in enumerate(ALL) if k >= '2025-01']

    # ── 两种同比口径，一次在全历史上算完，各图按位置取 ──
    # 一律在**全历史**上算完再切窗：切完再算的话窗口最前 12 期永远是空的。
    POS = [ALL.index(w) for w in WIN]          # 13 个月窗口在 ALL 里的位置
    NN_MONO, NN_ROLL = mono_yoy_arr(nn_all, ALL), roll_yoy_arr(nn_all, ALL)
    CL_MONO, CL_ROLL = mono_yoy_arr(cleared_all, ALL), roll_yoy_arr(cleared_all, ALL)
    AN_MONO, AN_ROLL = mono_yoy_arr(ann_all, ALL), roll_yoy_arr(ann_all, ALL)
    # 存量三条的反事实对照口径是滚动**均值**（不是「合计」，见 mean_yoy_arr 的 docstring）
    ST_MG = cal_stats(mono_yoy_arr(mg_all, ALL), mean_yoy_arr(mg_all, ALL), POS, ALL)
    ST_CR = cal_stats(mono_yoy_arr(cr_all, ALL), mean_yoy_arr(cr_all, ALL), POS, ALL)
    ST_NN = cal_stats(NN_MONO, NN_ROLL, POS, ALL)
    ST_CL = cal_stats(CL_MONO, CL_ROLL, POS, ALL)
    ST_AN = cal_stats(AN_MONO, AN_ROLL, POS, ALL)
    # 全历史（不切窗）的净新增账户对照 —— 页尾口径说明用，13 个月窗口太短，
    # 「25 个月里 1 个符号相反」读起来像偶然，104 个月里 25 个才看得出是系统性的。
    ST_NN_ALL = cal_stats(NN_MONO, NN_ROLL, list(range(len(ALL))), ALL)

    def at(a):
        """某条同比序列在**本页目标月**的读数（小数）；算不出返回 None。"""
        v = a[ALL.index(target)]
        return None if not np.isfinite(v) else float(v)

    # ── Exhibit 定义（标题文案逐字照抄 build_report.py 的 title_src 调用）──
    ex = []

    # Ex2 的 x 标签给有口径调整的月份挂 †：柱画的是表内披露值，读者要能一眼看到哪根柱不可直读
    adj_nn = [k for k, a in ADJ.items() if a['field'] == 'net_new']
    XL2 = [x + ('†' if WIN[i] in adj_nn else '') for i, x in enumerate(XL)]
    XL3 = [x + ('†' if (WIN[i] in adj_nn or yagm[WIN[i]] in adj_nn) else '') for i, x in enumerate(XL)]

    # 图注只许声称**图上真有**的东西。窗口每月往前滚，2025-03 已经滚出去了、2025-09 明年也会滚出去；
    # 原来的图注把 ADJ 里全部三条都当成「† 的月份」写死，届时会出现「图注讲两个 †、图上一个都没有」。
    # 所以 † 的措辞按窗口内实际打了标记的月份现算，一个都没有时整句换成「本窗口内没有」。
    mk2 = [w for w in WIN if w in adj_nn]                             # Ex2 上真正带 † 的月份
    mk3 = [w for w in WIN if w in adj_nn or yagm[w] in adj_nn]        # Ex3 上真正带 † 的月份
    adj_txt = '；'.join(f'{k} 表内 {ADJ[k]["reported"]:.1f}k → 公司披露真实增长 {ADJ[k]["real"]:.1f}k'
                       f'（{ADJ[k]["reason"]}）' for k in mk2)
    # 还原口径的全量清单（不受窗口影响，Ex3/Ex15 与页尾 notes 共用）
    nn_adj_txt = '、'.join(f'{k} {ADJ[k]["real"]:.1f}k（表内 {ADJ[k]["reported"]:.1f}k）'
                          for k in sorted(adj_nn))
    # 「不还原会错多少」的例子也现算：取窗口内最后一个**分母**被还原的月份
    naive_ex = None
    for m in reversed(WIN):
        if yagm[m] in adj_nn and series[m]['net_new'] and series[yagm[m]]['net_new']:
            naive_ex = (m, real_nn[m] / real_nn[yagm[m]] - 1,
                        series[m]['net_new'] / series[yagm[m]]['net_new'] - 1)
            break

    ex.append({
        'n': 2, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': XL2,
        'title': f'IBKR added ~{net_new[-1]:.0f}k net new accounts, with monthly account growth {pctf(mom(net_new))} MoM…',
        'ylab': 'Net New Accounts (thousands)',
        'note': ('柱与 12 个月均线画的是历史指标表披露的 Net New Accounts（= 账户存量差分）。'
                 + (f'† 的月份含一次性口径调整，不可与相邻柱直读：{adj_txt}。' if mk2 else
                    '本窗口内没有带 † 的月份——历次一次性账户口径调整都已滚出这 13 个月窗口'
                    f'（全部调整见页尾说明：{nn_adj_txt}）。')
                 + 'Exhibit 3 的 y/y 已用还原值。'
                 + ('<br>PDF Notes 原文：' + ' / '.join(nt['text'] for nt in notes) if notes else '')),
        'legend': 'Net New Accounts', 'values': L(net_new), 'avg12': avg12(net_new),
        # 气泡里的 y/y 换成滚动口径，与 Exhibit 3 的那条线、Exhibit 15 的 T12M 水平线
        # 是同一个数。原来这里是单月同比，与同页 Exhibit 15 讲的是两件事。
        'yoy_txt': (pctf(at(NN_ROLL)) + ' y/y·12M' if at(NN_ROLL) is not None
                    else pctf(yoy(nn_real)) + ' y/y·单月'),
        'mom_txt': pctf(mom(net_new)),
        'bar_marks': [i for i, w in enumerate(WIN) if w in adj_nn],
        'mark_note': '该月含一次性账户口径调整，见图注 †',
    })
    # 净新增账户是**流量**：同比换成 12 个月滚动合计口径。
    # 本页早就有一条现成的滚动线 —— Exhibit 15 画的就是 T12M 净新增账户，
    # 这张图现在画的正是那条线的同比，两张图从此对得上（原先一张滚动、一张单月）。
    nn_roll_win = np.array([NN_ROLL[i] for i in POS], float)
    _n3 = int(np.isfinite(nn_roll_win).sum())
    _use_roll3 = _n3 >= 6
    _v3 = (nn_roll_win if _use_roll3 else nn_yoy)
    _cur3 = float(_v3[-1])
    # 图注分段拼，不写成一个长三元表达式 —— 那种写法上一版在别的页上把「if 只作用于
    # 最后一段」这个优先级坑踩过一次，整段文案在某个分支下会静默丢掉。
    _n3_note = (f'分子分母一律用公司 Notes 还原后的真实账户增长：{nn_adj_txt}。'
                + (f'† 标出本窗口内受影响的月份（{"、".join(mk3)}：自身或去年同月被还原）。'
                   if mk3 else '本窗口内没有受影响的月份（历次调整已滚出窗口），故图上没有 †。')
                + (f'直接用表内差分会让 {naive_ex[0]} 的单月同比从 {pctf(naive_ex[1])} '
                   f'虚高到 {pctf(naive_ex[2])}。' if naive_ex else ''))
    if _use_roll3:
        _n3_note += roll_note(ST_NN)
        if ST_NN_ALL and ST_NN_ALL['flips']:
            _w = max(ST_NN_ALL['flips'], key=lambda f: abs(f[1] - f[2]))
            _n3_note += (f'把范围放到全历史（{ST_NN_ALL["n"]} 个可比月）差距更清楚：'
                         f'{len(ST_NN_ALL["flips"])} 个月两种口径符号相反，最极端的 {_w[0]} '
                         f'单月 {_w[1]:+,.0f}% vs 滚动 {_w[2]:+,.0f}%，'
                         f'相差 {abs(_w[1] - _w[2]):,.0f}pp。')
        _n3_note += (f'本图与 Exhibit 15 是同一件事的两种画法：那张画 T12M 净新增账户的'
                     f'<b>水平值</b>（当期 {roll12[-1]:,.0f}k），这张画它的<b>同比</b>。'
                     '两张图从此对得上 —— 原先一张滚动、一张单月，读者无从知道该信哪个。')
    else:
        _n3_note += (f'本序列在本窗口内只有 {_n3} 个滚动同比读数（滚动同比要 24 个月历史），'
                     '不足以画一条线，故仍用<b>单月同比</b> —— 这是数据长度的限制，'
                     '不是口径选择；判据写成条件，历史够了这张图会自己切到滚动口径。')
    ex.append({
        'n': 3, 'kind': 'gs_line', 'fmt': 'pct0z', 'xlabels': XL3,
        'title': (f'…and net new accounts {"growing" if _cur3 > 0 else "declining"} '
                  f'{abs(_cur3)*100:.0f}% YoY'
                  + (' (12M rolling)' if _use_roll3 else ' (single-month 单月同比)')),
        'ylab': ('Net new accounts, 12M rolling y/y (%)' if _use_roll3
                 else 'Change in Net New Accounts YoY, 单月 (%)'),
        'values': L(_v3 * 100),
        'note': _n3_note,
    })
    # cleared DARTs 是**流量率**（每天多少笔）：气泡与标题的 y/y 换滚动口径。
    _y4 = at(CL_ROLL)
    _y4v = _y4 if _y4 is not None else yoy(cleared)
    ex.append({
        'n': 4, 'kind': 'gs_bar', 'fmt': 'f0c',
        'title': f'Implied cleared DARTs came in {abs(_y4v)*100:.0f}% {"higher" if _y4v > 0 else "lower"} YoY '
                 + ('(12M rolling)' if _y4 is not None else '(单月)')
                 + f', and {abs(cleared[-1]/avg12(cleared)-1)*100:.0f}% '
                 f'{"above" if cleared[-1]/avg12(cleared)-1 > 0 else "below"} the prior 12-month average…',
        'ylab': 'Cleared DARTs (thousands of trades/day)',
        'note': 'We calculate cleared DARTs = Cleared avg. DART per account (annualized) / 252 trading days * '
                'average of beginning- and end-of-month total accounts. '
                '假设：账户数在月内线性变化（故取期初期末简单平均）；官方的年化口径就是按 252 天折算，'
                '不要换成当月实际交易日。'
                f'结果约为 IBKR 单独披露的 Total Client DARTs 的 {cov_cleared.min():.0f}%–{cov_cleared.max():.0f}%'
                '（窗口内），差额是口径差（cleared ≠ total client，见 Exhibit 18），不是估算误差。'
                + roll_note(ST_CL),
        'legend': 'Implied Cleared DARTs', 'values': L(cleared), 'avg12': avg12(cleared),
        'yoy_txt': (pctf(_y4) + ' y/y·12M') if _y4 is not None else (pctf(yoy(cleared)) + ' y/y·单月'),
        'mom_txt': pctf(mom(cleared)),
    })
    # 人均年化 cleared DART 是**流量率**（每户每年多少笔）：标题与图注的 y/y 换滚动口径。
    # 13 个月窗口内实测：单月同比标准差 11.1pp vs 滚动 6.2pp，7/13 个月符号相反 ——
    # 这条序列上「今年是涨是跌」两种口径给的是相反答案，标题里必须写清楚是哪个。
    _y5 = at(AN_ROLL)
    _y5v = _y5 if _y5 is not None else yoy(ann_dart)
    ex.append({
        'n': 5, 'kind': 'gs_line', 'fmt': 'x0',
        'title': f'…leading to {pctf(_y5v)} annualized cleared DARTs per account vs. last year'
                 + (' (12M rolling)' if _y5 is not None else ' (单月)'),
        'ylab': 'Annualized DARTs / Account (x)', 'values': L(ann_dart),
        # 原来这里开着 ovals_at_bottom：两个气泡被钉在纵轴下界那条刻度线上，各拖一条**水平**虚线
        # 箭头指向右边的空白处，跟任何数据点都没连上；而且 mom 那个数（-19%）在标题和图注里都
        # 没出处，读者无从知道它比的是哪两个月。gs_line 的气泡只有「贴底 + 水平箭头」这一种摆法，
        # 所以改成不画气泡（同页另外三张 gs_line —— Ex3/11/13 —— 本来就没有气泡，这样反而一致），
        # 两个数字改为写进标题（YoY，原本就在）与图注（MoM）。
        'note': '公司直接披露的 Cleared Avg. DART per Account (Annualized)，非推导值。'
                f'当月 {ann_dart[-1]:.0f}x：环比 {pctf(mom(ann_dart))}、'
                f'单月同比 {pctf(yoy(ann_dart))}'
                + (f'、12 个月滚动合计同比 {pctf(_y5)}' if _y5 is not None else '')
                + '。' + roll_note(ST_AN)
                + '长历史见 Exhibit 14——窗口内的波动是一个已经腰斩后的低位平台。',
    })
    ex.append({
        'n': 6, 'kind': 'gs_bar', 'fmt': 'f1',
        'title': f'Implied commission revenue/day came in {abs(yoy(comm_day))*100:.0f}% {"higher" if yoy(comm_day) > 0 else "lower"} YoY (单月) '
                 f'and {pctf(mom(comm_day))} MoM',
        'ylab': 'Implied Commission Revenue / Day ($mn)',
        'note': 'Commission revenue/day estimated as cleared DARTs (千笔/日) x average commission per cleared '
                'commissionable order ($/笔) ÷ 1,000 → $mn/day。'
                '假设：新闻稿披露的是 average commission per cleared <b>commissionable</b> order，而乘数是全部 '
                'cleared DART，两个总体是否一致未经证实——若 DART 计入免佣订单，本图偏高；'
                'cleared DARTs 本身也是推导值，两层近似复合。要得到月度总额还需再乘当月官方交易日数。'
                '月度无对应披露可比，季度有（10-Q 的 Commissions 行），但尚未接入。'
                # 这一张是本页唯一「该用滚动却用不了」的图，理由是数据长度不是口径选择。
                f'<b>口径：本图的 y/y 是单月同比</b>，因为算不出滚动口径 —— 它的乘数 CPT '
                f'（单笔佣金）只存在于月度新闻稿里，本地只缓存 {len(WIN)} 个月，'
                '而 12 个月滚动合计同比需要 24 个月历史。缓存长到两年之后这张图应改成滚动口径；'
                '在那之前请把这个读数当成受基数影响的值看，趋势以柱本身与 Exhibit 4 为准'
                '（那张的乘数 cleared DARTs 有全历史，已经是滚动口径）。',
        'legend': 'Implied Commission Revenue/Day', 'values': L(comm_day), 'avg12': avg12(comm_day),
        'yoy_txt': pctf(yoy(comm_day)) + ' y/y·单月', 'mom_txt': pctf(mom(comm_day)),
    })
    dc = (cpt[-1] - cpt[-2]) * 100
    vs7 = cpt[-1] / avg12(cpt) - 1
    ex.append({
        'n': 7, 'kind': 'gs_line_avg', 'fmt': 'usd2',
        # 用户提供的参考 PDF（2026-07-03 生成）此处是分币符号 ¢；skill 当前版本
        # （2026-07-14 改过）写的是 ASCII 'c'。以参考 PDF 为准，并且 ¢ 是正确排版。
        'title': f'Average CPT {"decreased" if dc < 0 else "increased"} by {abs(dc):.0f}¢ MoM, and was '
                 f'{abs(vs7)*100:.0f}% {"below" if vs7 < 0 else "above"} the 12-month average',
        'ylab': 'Average commission / DART ($)', 'values': L(cpt), 'avg12': avg12(cpt),
        'legend': 'Avg. Commission/DART', 'avg_label': 'Prior 12mo Avg.',
    })

    dpp = (pct_fo[-1] - pct_fo[-2]) * 100
    fo_mom = (opt_d[-1] + fut_d[-1]) / (opt_d[-2] + fut_d[-2]) - 1
    st_mom = stk_d[-1] / stk_d[-2] - 1
    clause = ('as stock DARTs increased more than options and futures' if (dpp < 0 and st_mom > fo_mom)
              else ('as options and futures DARTs outgrew stocks' if dpp > 0 else 'on shifting product mix'))
    ex.append({
        'n': 8, 'kind': 'stacked_dual',
        'title': f'Implied product DARTs: the % in the form of F&O {"decreased" if dpp < 0 else "increased"} '
                 f'{abs(dpp):.1f}pp MoM, {clause}',
        # 全页 17 张图里原先唯一一张两个纵轴都没有轴标题的：读者看到 1,849 / 2,364 无从判断
        # 是千笔还是百万笔（左轴与 Exhibit 4 同量纲，右轴是 F&O 占比）。
        'ylab': 'Implied Product DARTs (thousands of trades/day)',
        'ylab2': 'F&O share of implied DARTs (%)',
        'note': 'Product DARTs estimated as monthly volume / average order size / US trading days. '
                '假设：average order size 取的是全部订单的均值；对期货与国际股票同样套用<b>美股</b>交易日数。'
                f'本图各产品推导值合计约为披露 Total Client DARTs 的 {cov_prod.min():.1f}%~{cov_prod.max():.1f}%'
                '（近 13 个月），故本图口径接近 cleared 而非 total（下方总表那一列是 Total Client DARTs）。',
        'stacks': [
            {'name': 'Implied Stock DARTs', 'color': 'BLUE', 'values': L(stk_d), 'label': True, 'label_color': 'NAVY'},
            {'name': 'Implied Options DARTs', 'color': 'GRAY', 'values': L(opt_d), 'label': True, 'label_color': 'WHITE'},
            {'name': 'Implied Futures DARTs', 'color': 'NAVY', 'values': L(fut_d), 'label': False},
        ],
        'line': {'name': '% Futures/Options', 'color': 'GREEN', 'values': L(pct_fo * 100), 'ymax': 60},
    })
    chg_cpt = [('stocks', stk_cpt[-1] / stk_cpt[-2] - 1), ('options', opt_cpt[-1] / opt_cpt[-2] - 1),
               ('futures', fut_cpt[-1] / fut_cpt[-2] - 1)]
    dec = [f'{abs(c)*100:.0f}% for {n}' for n, c in chg_cpt if c <= -0.01]
    inc = [f'{abs(c)*100:.0f}% for {n}' for n, c in chg_cpt if c >= 0.01]
    flat = [n for n, c in chg_cpt if abs(c) < 0.01]
    parts = []
    if dec: parts.append('decreased ' + ', '.join(dec))
    if inc: parts.append('increased ' + ', '.join(inc))
    ex.append({
        'n': 9, 'kind': 'lines_endlabels', 'fmt': 'usd2',
        'title': 'Average commissions/trade ' + ' and '.join(parts or ['were stable']) + ' MoM' +
                 (f', and were largely flat for {", ".join(flat)}' if flat else ''),
        'ylab': 'Average commission per trade ($)',
        'series': [
            {'name': 'Stocks Avg CPT', 'color': 'NAVY', 'values': L(stk_cpt)},
            {'name': 'Options Avg CPT', 'color': 'BLUE', 'values': L(opt_cpt)},
            {'name': 'Futures Avg CPT', 'color': 'MBLUE', 'values': L(fut_cpt)},
        ],
    })
    va10 = margin[-1] / avg12(margin) - 1
    ex.append({
        'n': 10, 'kind': 'gs_bar', 'fmt': 'f1',
        'title': f'Customer margin balances {"rose" if yoy(margin) > 0 else "fell"} by {abs(yoy(margin))*100:.0f}% YoY, '
                 f'{abs(va10)*100:.0f}% {"above" if va10 > 0 else "below"} the prior 12 month average',
        'ylab': 'Customer Margin Balances ($bn)',
        'legend': 'Customer Margin Balances', 'values': L(margin), 'avg12': avg12(margin),
        'yoy_txt': pctf(yoy(margin)) + ' y/y·单月', 'mom_txt': pctf(mom(margin)),
        'note': stock_note(ST_MG, '客户融资余额'),
    })
    ex.append({
        'n': 11, 'kind': 'gs_line', 'fmt': 'pct0',
        'title': f'Customer margin balances {"increased" if marg_yoy[-1] > 0 else "decreased"} by {abs(marg_yoy[-1])*100:.0f}% YoY (单月同比)',
        'ylab': 'YoY customer margin balances change, 单月 (%)', 'values': L(marg_yoy * 100),
        'note': '融资余额不是高增速指标，m/m 基本是噪音，故本图画 y/y（相对 Exhibit 10 同一序列的去年同月）。'
                '余额的绝对水平在创新高，但相对客户权益的占比仍在低位，见 Exhibit 17。'
                + stock_note(ST_MG, '客户融资余额'),
    })
    va12 = credits[-1] / avg12(credits) - 1
    ex.append({
        'n': 12, 'kind': 'gs_bar', 'fmt': 'f1',
        'title': f'Client cash {"increased" if yoy(credits) > 0 else "decreased"} {abs(yoy(credits))*100:.0f}% YoY, to '
                 f'{abs(va12)*100:.0f}% {"above" if va12 > 0 else "below"} the prior 12 months average…',
        'ylab': 'Total Client Cash ($bn)',
        'note': 'Client cash = total client credit balances, including insured bank deposit sweeps.'
                + stock_note(ST_CR, '客户现金（credit balances）'),
        'legend': 'Total Client Cash', 'values': L(credits), 'avg12': avg12(credits),
        'yoy_txt': pctf(yoy(credits)) + ' y/y·单月', 'mom_txt': pctf(mom(credits)),
    })
    ex.append({
        'n': 13, 'kind': 'gs_line', 'fmt': 'pct0',
        'title': f'…and was {"up" if cred_yoy[-1] > 0 else "down"} ~{abs(cred_yoy[-1])*100:.0f}% YoY (单月同比)',
        'ylab': 'YoY client cash change, 单月 (%)', 'values': L(cred_yoy * 100),
        'note': '同 Exhibit 11：客户现金的 m/m 中位数只有约 1.4%，画 y/y 才有信息量。'
                + stock_note(ST_CR, '客户现金（credit balances）'),
    })

    # ── 长历史（Exhibit 14-18）：2016-01 起，x 轴每 12 个月一个标签 ──
    # 四张长历史 lines 图一律显式 zero_base：不给它时引擎走 y0 = min − 极差×5%，那是一次**没有
    # 任何标注的隐性截轴**，而这四张图的标题偏偏都在讲倍数／降幅（Ex14「53% below」、
    # Ex16「14.0x」、Ex17「不到一半」）——截过的轴会把这些幅度凭空放大，图与文字互相打架。
    # Ex15 的数据本来就贴近 0，给上只是把「从 0 起」这件事写实。
    # end_label 只给 Ex15/16/17：这三张的末点读数正是各自标题引用的那个数（1,398k / $907bn /
    # 19.9% 与 11.1%），且末点都落在序列的极值端，标签周围是空的。
    # Ex14 不给：它的标题引用的是**年均值**（432x / 203x）而不是末点，末点 180x 又正好落在
    # 一段密集抖动的尾巴上，标上去只是多一个没人对得上的数字压在线上。
    y16, ylast = ALL[0][:4], target[:4]
    ex.append({
        'n': 14, 'kind': 'lines', 'x': 'long', 'xstep': 12, 'fmt': 'f0',
        'zero_base': True,
        'title': f'Annualized cleared DARTs per account: {yr_mean(ann_all, y16):.0f}x avg. in {y16} → '
                 f'{yr_mean(ann_all, ylast):.0f}x YTD in {ylast}, '
                 f'{(1 - yr_mean(ann_all, ylast) / yr_mean(ann_all, y16)) * 100:.0f}% below the {y16} level',
        'ylab': 'Annualized cleared DARTs / account (x)',
        'note': '<b>公司直接披露值，非本站推导。</b>年均：'
                + '、'.join(f'{y} {yr_mean(ann_all, y):.0f}x' for y in
                           [y16, '2019', '2020', '2022', '2023', ylast])
                + '。2020-21 的凸起是疫情期间的交易热潮，其后回落到的平台明显低于 2016-18——'
                  'Exhibit 5 的窗口只覆盖最后 13 个月，看不出这是结构性下台阶还是周期性回落。',
        'series': [{'name': 'Cleared avg. DART per account (annualized)', 'color': 'NAVY',
                    'values': LN(ann_all)}],
    })
    ex.append({
        'n': 15, 'kind': 'lines', 'x': 'long', 'xstep': 12, 'fmt': 'f0c',
        'zero_base': True, 'end_label': True,
        'title': f'Trailing-12-month net new accounts at {roll12[-1]:,.0f}k, vs. '
                 f'{roll12[ALL.index("2021-12")]:,.0f}k in Dec-21 and {roll12[ALL.index("2018-12")]:,.0f}k in Dec-18',
        'ylab': 'Net new accounts, trailing 12 months (thousands)',
        'note': '12 个月滚动和，回答「这轮开户潮相对历史有多大」。已按公司 Notes 还原真实账户增长'
                f'（{nn_adj_txt}），前 11 个月不足一年故留空。',
        'series': [{'name': 'Net new accounts, T12M', 'color': 'NAVY', 'values': LN(roll12)}],
    })
    ex.append({
        'n': 16, 'kind': 'lines', 'x': 'long', 'xstep': 12, 'fmt': 'f0c',
        'zero_base': True, 'end_label': True,
        'title': f'Client equity at ${eq_all[-1]:,.0f}bn, {eq_all[-1] / eq_all[0]:.1f}x the '
                 f'${eq_all[0]:,.0f}bn of {XL_LONG[0]}',
        'ylab': 'Client Equity ($bn)',
        'note': '公司披露值（期末口径，不含非客户余额）。它是 Exhibit 10 / 12 两条余额的分母，也是 NII 的规模基数，'
                '此前站上一张图都没有。',
        'series': [{'name': 'Client Equity', 'color': 'NAVY', 'values': LN(eq_all)}],
    })
    ex.append({
        'n': 17, 'kind': 'lines', 'x': 'long', 'xstep': 12, 'fmt': 'pct1',
        'zero_base': True, 'end_label': True,
        'title': f'Both interest-earning bases keep shrinking vs. client equity: client cash '
                 f'{cr_share[-1]:.1f}% and margin loans {mg_share[-1]:.1f}%, vs. '
                 f'{cr_share[0]:.1f}% / {mg_share[0]:.1f}% in {XL_LONG[0]}',
        'ylab': 'as % of client equity (%)',
        'note': '<b>这是比值，不是公司披露值</b>：分子分母都取自官方历史指标表同一张表内的 Client Credits / '
                'Client Margin Loans / Client Equity。历史最低：客户现金/权益 '
                f'{np.nanmin(cr_share):.2f}%（{ALL[int(np.nanargmin(cr_share))]}）、融资余额/权益 '
                f'{np.nanmin(mg_share):.2f}%（{ALL[int(np.nanargmin(mg_share))]}）。'
                'Exhibit 10 / 12 的绝对额在创新高，但这两条生息基数相对资产规模仍不到 2016-18 年的一半。',
        'series': [
            {'name': 'Client cash / client equity', 'color': 'NAVY', 'values': LN(cr_share)},
            {'name': 'Margin loans / client equity', 'color': 'MBLUE', 'values': LN(mg_share)},
        ],
    })
    # 断点索引现算且**允许算不出**：`ALL.index()` 找不到就 ValueError，整个 routine 硬失败退出，
    # 页面永久停更（build/lpla.py 就是栽在这上面）。这里照 schw.py / wealth.py 的写法降级——
    # 断点不在轴上就不给 break_at，同时把图注里「红色虚线」那句话一并省掉：
    # 图注只许声称图上真有的东西。
    BRK_M = '2025-01'
    brk = ALL.index(BRK_M) if BRK_M in ALL else None
    brk_note = '（红色虚线右侧与左侧不可直读）' if brk is not None else ''
    ex.append({
        'n': 18, 'kind': 'bar_line_dual', 'x': 'long', 'xstep': 12, 'full': True, 'height': 300,
        'title': f'Total client DARTs (disclosed) at {dart_all[-1]:,.0f}k/day; the share NOT captured by implied '
                 f'cleared DARTs stepped up from ~{np.nanmean(noncl_all[pre25]):.0f}% to '
                 f'~{np.nanmean(noncl_all[post25]):.0f}% during 2025',
        'ylab': 'Total Client DARTs (thousands of trades/day)',
        'ylab2': 'Implied non-cleared share (%)',
        'bar': {'name': 'Total Client DARTs (disclosed)', 'color': 'BLUE', 'values': LN(dart_all),
                'yfmt': 'f0c'},
        'line': {'name': '1 − implied cleared ÷ total client DARTs (RHS)', 'color': 'GREEN',
                 'values': LN(noncl_all), 'yfmt': 'pct0'},
        'note': '柱是公司直接披露的 Total Client DARTs；右轴线 = 1 − 推导 cleared DARTs ÷ 披露 Total Client DARTs'
                '（等价于 cleared/total 的补数——bar_line_dual 的右轴强制含 0，直接画 85%~92% 的比值会被压成一条'
                '看不出变化的平线）。cleared/total 的逐年均值：'
                + '、'.join(f'{y} {np.nanmean(1 - noncl_all[[i for i, k in enumerate(ALL) if k[:4] == y]] / 100):.3f}'
                           for y in ['2016', '2019', '2022', '2024', '2025', ylast])
                + '——2019 前后降过一档，2019-2024 六年横盘，2025 起再降一档并保持，'
                  '<b>疑似口径/分类变更，未经公司确认</b>' + brk_note + '。'
                  '另需提示：推导 cleared DARTs 是用<b>总账户数</b>反推的，而官方指标是 per <b>cleared</b> account，'
                  '若 cleared 账户占总账户的比例本身在变，这条线里就混了推导误差，不能整条归因给 omnibus 渠道。',
    })
    if brk is not None:
        # 断点与图注那句话绑在一起给：给了 brk_note 就必须给 break_at，反之亦然，
        # 不然又会出现「图注说画了红虚线、图上一条都没有」。
        ex[-1]['break_at'] = brk
        ex[-1]['break_label'] = f'{BRK_M[:4]}：疑似口径变更'

    # ── Exhibit 1：汇总表（本月|上月|去年同月 ‖ m/m|y/y|3Y %ile）──
    # 单元格全部是**已格式化的字符串** + 颜色类：pp/bp、反向指标、分位反转这些格式化口径
    # 原先写在 index.html 的 chgCell() 里，现在一并搬到 Python 侧（CONTRACT §2）。
    ti = len(ALL) - 1

    # 分位一律走 build/pctile.py（全站唯一实现）。原来这里自带的 pctile36 用「上升月份占比 ≥90%」
    # 当单调性的代理，实测挡不住「上下波动但分位常年钉 100」的行：客户现金上升月占比只有 83%，
    # 于是印出一个绿色的 97，而它近 24 个月里有 21 个月钉在 100、区间只有 94–100。
    # 判据是口径，口径只能有一处定义——各写各的正是同一条序列在两页判定相反的原因。
    def as_list(arr):
        """numpy → pctile.py 吃的 list。NaN 必须换成 None：pctile.py 用 `is not None` 判缺失，
        NaN 混进去过得了那一关，之后所有比较都返回 False，分位会静默算错而不是报错。"""
        return [None if not np.isfinite(v) else float(v) for v in arr]

    def chg(a, b, mode):
        if not (np.isfinite(a) and np.isfinite(b)):
            return None
        if mode == 'pp':
            return round(float(a - b), 4)
        if b == 0 or a * b < 0:          # 分母为 0 或两期异号时百分比变化无意义
            return None
        return round(float(a / b - 1) * 100, 4)

    # (板块, 标签, 序列, 小数位, 前缀, mode, invert)；invert=True 表示下降为好
    SUM_ROWS = [
        ('账户', None, None, 0, '', '', False),
        (None, '账户总数（千户）', acc_all, 1, '', 'ratio', False),
        (None, '净新增账户（千户，已还原口径）', nn_all, 1, '', 'ratio', False),
        ('交易活动', None, None, 0, '', '', False),
        (None, '人均年化 cleared DART（x）', ann_all, 0, '', 'ratio', False),
        (None, 'Implied cleared DARTs（千笔/日）', cleared_all, 0, '', 'ratio', False),
        ('客户资产与余额', None, None, 0, '', '', False),
        (None, '客户权益（$bn）', eq_all, 1, '$', 'ratio', False),
        (None, '客户现金（$bn）', cr_all, 1, '$', 'ratio', False),
        (None, '融资余额（$bn）', mg_all, 1, '$', 'ratio', False),
    ]
    # 汇总表的 y/y 列**不换口径**：它恒等于表内算术「本月 ÷ 去年同月」，读者拿第一列
    # 除第三列就能验算。换成滚动口径之后这一步会得出另一个数，表内自相矛盾比口径混用更糟。
    # 改为在组标题上把口径写死，并在表注里把两种口径的当期读数并排现算印出。
    GRP_SUFFIX = '　·　y/y 列 = 单月口径（本月 ÷ 去年同月）'
    srows, blank_why = [], []
    for grp, lab, arr, d, pre, mode, inv in SUM_ROWS:
        if lab is None:
            srows.append({'kind': 'group', 'label': grp + GRP_SUFFIX})
            continue
        c, p1, p12 = arr[ti], arr[ti - 1], arr[ti - 12]
        f = lambda v: ('—' if not np.isfinite(v) else pre + comma(v, d))
        cells = [{'v': f(c), 'cls': 'cur'}, {'v': f(p1)}, {'v': f(p12)}]
        for b in (p1, p12):
            v = chg(c, b, mode)
            if v is None:
                cells.append({'v': ''})
                continue
            # 比率类指标的差异用 pp / bp（|v| < 1 用 bp）；其余用百分比变化
            if mode == 'pp':
                txt = signed(v * 100, 0, 'bp') if abs(v) < 1 else signed(v, 2, 'pp')
            else:
                txt = signed(v, 1, '%')
            good = (v < 0) if inv else (v > 0)      # 反向指标（越低越好）在这里定色
            # 四舍五入后就是 0 的变化不涂色：一个显示为「0.0%」的格子涂成绿或红，
            # 读者会以为方向是确定的，其实那是噪音。
            zero = float(txt.rstrip('%pb')) == 0
            cells.append({'v': txt, 'cls': '' if zero else ('pos' if good else 'neg')})
        ser = as_list(arr)
        pv, pcls = pctile.cell(ser, ti, inverse=inv)   # 反向指标只反转颜色，数值照算
        cells.append({'v': pv, 'cls': pcls})
        if not pv:
            why = pctile.why_blank(ser)
            if why:
                blank_why.append(f'{lab}（{why}）')
        srows.append({'label': lab, 'cells': cells})

    # 两种口径的当期读数，现算后并排印出 —— 不并排印，读者拿表里的 y/y 去核
    # Exhibit 3 的那条线必然对不上，还以为哪边算错了。
    def _pair(name, m, r, unit='%'):
        if m is None and r is None:
            return ''
        a = f'单月 {m * 100:+,.1f}{unit}' if m is not None else ''
        b = f'12 个月滚动 {r * 100:+,.1f}{unit}' if r is not None else ''
        both = ' / '.join(x for x in (a, b) if x)
        gap = (f'（差 {abs(m - r) * 100:,.0f}pp）' if (m is not None and r is not None) else '')
        return f'{name}：{both}{gap}'

    _CAL_ROWS = [t for t in (
        _pair('净新增账户（Exhibit 2/3 画滚动）', at(NN_MONO), at(NN_ROLL)),
        _pair('Implied cleared DARTs（Exhibit 4 画滚动）', at(CL_MONO), at(CL_ROLL)),
        _pair('人均年化 cleared DART（Exhibit 5 画滚动）', at(AN_MONO), at(AN_ROLL)),
        _pair('客户现金（存量，Exhibit 12/13 画点对点）', at(mono_yoy_arr(cr_all, ALL)),
              at(mean_yoy_arr(cr_all, ALL))).replace('12 个月滚动', '12 个月均值'),
        _pair('融资余额（存量，Exhibit 10/11 画点对点）', at(mono_yoy_arr(mg_all, ALL)),
              at(mean_yoy_arr(mg_all, ALL))).replace('12 个月滚动', '12 个月均值'),
    ) if t]
    _CAL_TXT = (f'当期各口径并排现算 —— {"；".join(_CAL_ROWS)}。' if _CAL_ROWS else '')

    month_name = datetime.date(ty, tm, 1).strftime('%B %Y')
    summary = {
        'title': f'{month_name} 汇总 —— 本月 vs 上月／去年同月，及近 3 年分位',
        'heads': ['本月 ' + XL[-1], '上月 ' + XL[-2], '去年同月 ' + XL[0], 'm/m', 'y/y 单月',
                  '3Y %ile'],
        'sep': 3,
        'rows': srows,
        'note': '3Y %ile = 当月读数在最近 36 个月里高于多少个百分比的观测（分位越高越极端），'
                '判据与全站共用 <code>build/pctile.py</code>：把这一行的分位在近 24 个月里逐月回放，'
                '若 ≥70% 的月份都钉在区间端点（100 或 0），说明这一列对该行没有区分度，整行留空。'
                + (f'本表留空的是：{"；".join(blank_why)}。' if blank_why else '')
                + f'净新增账户按公司 Notes 还原（{nn_adj_txt}）。'
                'CPT 与 F&O 占比来自月度新闻稿，本地只缓存 13 个月，做不出 3Y 分位，故不列。'
                '<br><b>本表的 y/y 列是「单月口径」= 本月 ÷ 去年同月 − 1，与 Exhibit 2/3/4/5 '
                '的滚动口径不同。</b>不改它是刻意的：这一列恒等于表内算术（第一列 ÷ 第三列），'
                '读者可以直接验算；换成滚动口径之后这一步会得出另一个数，'
                '表内自相矛盾比口径混用更糟。' + _CAL_TXT,
    }

    # ── 13 个月核对附表（官方原始单位，便于与披露逐条核对）──
    TCOLS = [('交易日', 'trading_days', 0), ('账户总数 千户', 'accounts', 1),
             ('净新增 千户', 'net_new', 1), ('Total Client DARTs 千笔/日（含未清算）', 'darts', 0),
             ('人均年化 DART', 'ann_dart_acct', 0), ('期权 千张', 'opt_contracts', 0),
             ('期货 千张', 'fut_contracts', 0), ('股数 千股', 'stk_shares', 0),
             ('客户权益 $bn', 'equity', 1), ('客户现金 $bn', 'credits', 1),
             ('融资余额 $bn', 'margin', 1)]
    trows = []
    for i, w in enumerate(WIN):
        r = {'xl': XL[i]}
        for _, key, dec in TCOLS:
            v = series[w][key]
            r[key] = None if v is None else comma(v, dec)
        trows.append(r)
    # 图号自查：exhibit 编号必须是 2..N 的连号，核对表接在最后一张之后。编号写死过一次
    # 代价就够大了 —— 全站审计发现别的页把核对表写死成 'n': 15，后来在末尾追加了两张图，
    # 页面就出现「…16、17、15」而没有任何东西报错。这里改成现算 + 硬拦。
    _ens = [e['n'] for e in ex]
    if _ens != list(range(2, 2 + len(_ens))):
        raise SystemExit(f'Exhibit 编号不连续: {_ens}')
    table = {
        'n': _ens[-1] + 1, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）',
        'idx': '月份', 'cols': [[lab, key] for lab, key, _ in TCOLS], 'rows': trows,
    }

    # 抬头一律 YoY + MoM 并列。原来只写 YoY，而本月五个 YoY 恰好全是正的，抬头看上去一片大好；
    # 真实情况是净新增 -31% MoM、cleared DARTs -16% MoM、人均年化 DART 同比环比双降 ——
    # 要翻到 Exhibit 1 汇总表才看得到。抬头是多数人唯一会读的一行，不能只挑好消息。
    # 同时补上人均年化 DART：它是这页唯一结构性下行的指标（Exhibit 5 / 14 讲的就是它），
    # 抬头里一个字都没有，等于把最该看的那条曲线藏起来。
    # 每个 y/y 都带口径标签：本页有两种同比口径，一个光秃秃的 YoY 在抬头里等于误导
    # （读者会拿它去核汇总表或图上的线，然后对不上）。流量类用滚动、存量类用点对点。
    def _hy(roll_arr, fallback):
        v = at(roll_arr)
        return (pctf(v) + ' YoY·12M滚动') if v is not None else (pctf(fallback) + ' YoY·单月')

    headline = (f'净新增账户 {net_new[-1]:.1f}k（{_hy(NN_ROLL, yoy(nn_real))}，{pctf(mom(net_new))} MoM） · '
                f'cleared DARTs {cleared[-1]:,.0f}k（{_hy(CL_ROLL, yoy(cleared))}，{pctf(mom(cleared))} MoM） · '
                f'人均年化 DART {ann_dart[-1]:.0f}x（{_hy(AN_ROLL, yoy(ann_dart))}，{pctf(mom(ann_dart))} MoM） · '
                f'CPT ${cpt[-1]:.2f}（{pctf(mom(cpt))} MoM） · '
                f'融资余额 ${margin[-1]:.1f}B（{pctf(yoy(margin))} YoY·单月，{pctf(mom(margin))} MoM） · '
                f'客户现金 ${credits[-1]:.1f}B（{pctf(yoy(credits))} YoY·单月，{pctf(mom(credits))} MoM）')
    hub = (f'净新增 {net_new[-1]:.0f}k（{_hy(NN_ROLL, yoy(nn_real))}）、'
           f'cleared DARTs {cleared[-1]:,.0f}k（{_hy(CL_ROLL, yoy(cleared))}）')

    payload = {
        'ticker': 'ibkr',
        'tracker': 'Interactive Brokers Group (IBKR): Monthly Brokerage Metrics',
        'title': f'Monthly Brokerage Metrics — {month_name}',
        'data_through': target,
        'through_label': month_name,
        'subtitle': (f'{month_name} update — Exhibits 2–13, recreated in Goldman Sachs GIR exhibit '
                     f'format from IBKR company data · 窗口 {XL[0]} – {XL[-1]} · '
                     f'Exhibits 14–18 为 {XL_LONG[0]} 起全历史'),
        'headline': headline,
        # headline 之下、Exhibit 1 之上的 ~300 字解读。职责与 headline 互补：
        # 那一行给读数，这一段给「读数该怎么读」。见 compose_brief 的 docstring。
        'brief': compose_brief(ALL, acc_all, eq_all, cr_all, mg_all, ann_all, nn_all,
                               dart_all, td_all, opt_all, fut_all, stk_all),
        'hub_line': hub,
        'source': SRC,
        'xlabels': XL,
        'xlabels_long': XL_LONG,
        'summary': summary,
        'exhibits': ex,
        'table': table,
        'notes': [
            '<strong>数据源</strong>：IBKR 官网 IR 的 Historical Brokerage Metrics PDF（每月更新，'
            f'共 11 个年度逐月数据，本站落库为 <code>series/ibkr.csv</code>，{ALL[0]} 起 {len(ALL)} 个月连续）'
            '+ 各月度 Metrics 新闻稿（佣金与产品明细，历史表里没有这两列）。',
            '<strong>单位</strong>：历史指标表首个区块标注 “(in Thousands, except Trading Days)”，'
            '故账户数、净新增、DARTs、期权／期货合约数、股票成交股数均以<strong>千</strong>为单位；'
            '客户权益、客户现金、融资余额区块标注 “(in Billions)”。文末核对表保持官方原始单位，'
            '便于与披露逐条核对。',
            '<strong>Cleared DARTs</strong>（Exhibit 4）= Cleared avg. DART per account（年化）÷ 252 '
            '个交易日 × 期初与期末账户总数的平均值。这是券商研究里的标准还原口径，'
            '<strong>非公司直接披露值</strong>，故图标题一律以 Implied 打头。',
            '<strong>Commission revenue/day</strong>（Exhibit 6）= cleared DARTs（千笔/日）× '
            '单笔清算订单平均佣金（$/笔）<strong>÷ 1,000</strong> → 百万美元/日（$mn/day）。'
            '要得到月度总额还需再乘当月官方交易日数。',
            '<strong>Product DARTs</strong>（Exhibit 8）= 当月成交量 ÷ 平均订单规模 ÷ 美股交易日数。'
            f'三段合计约为披露 Total Client DARTs 的 {cov_prod.mean():.0f}%，'
            '即本图口径接近 cleared 而非 total。',
            '<strong>佣金口径</strong>：新闻稿「Key products」表两列分别是 <em>Average Order Size</em>'
            '（平均订单规模，股／张）与 <em>Average Commission per Cleared Commissionable Order</em>'
            '（单笔清算订单平均佣金，$，含交易所、清算与监管费用）。<strong>不是每股／每张单价。</strong>',
            '<strong>期货</strong>含期货期权；公司估计交易所／清算／监管费用约占期货佣金的 56%。',
            '<strong>账户口径调整</strong>：历史指标 PDF 的 Notes 段披露过三次一次性调整'
            '（2025-03 escheat 13.3k、2025-09 一家 introducing broker 撤出 38.8k、'
            '2024-11 Total Accounts 下调 9.1k）。Exhibit 2 画表内披露值，'
            + (f'落在当前 13 个月窗口内的调整月（{"、".join(mk2)}）以 † 与斜纹柱标出；'
               if mk2 else '本次窗口内没有调整月，故图上没有 † 与斜纹柱；')
            + 'Exhibit 3 与 Exhibit 15 的分子分母一律用公司给的真实增长。解析器每月重新抓这段 Notes，'
            '出现未登记的调整会直接让构建失败。',

            '<strong>与本站其余各页的一处版式差异</strong>：本页 gs_bar 图（Exhibit 2 / 4 / 6 / 10 / 12）'
            '上的那条虚线画的是<strong>前 12 个月均值</strong>；而从 Goldman Sachs deck 移植的各页'
            '（HKEX / CME / CBOE / MSCI / SPGI 等）在同一位置画的是<strong>次轴 y/y 折线</strong>。'
            '本页与 /cost/ 来自两个已上线并逐张验收过的独立站，均线是原站既有版式，故保留不动；'
            'y/y 在本页另有出处——图左上角气泡，以及 Exhibit 3 / 11 / 13 三张专门的 y/y 图，数字同源。',

            # ── 同比口径：本页有两种，逐处点名 ──
            # 「点名」不是客套：读者在同一页上看到两个都叫 YoY 的净新增账户读数，
            # 没人告诉他分母不同，他只会以为哪里算错了。
            '<b>⚠ 同比口径：本页有两种，逐处点名。</b>'
            '(1) <b>12 个月滚动合计同比</b>（本年 12 个月合计 ÷ 上年同 12 个月合计 − 1）—— '
            'Exhibit 3（净新增账户，整张图）、Exhibit 2 / 4 / 5 的 YoY 气泡与标题。'
            '<b>流量与流量率一律用这个口径。</b>'
            + (f'实测（对齐到两种口径都算得出的同一批月份，全历史 {ST_NN_ALL["n"]} 个月）：'
               f'净新增账户的单月同比标准差 {ST_NN_ALL["sd_m"]:,.1f}pp 是滚动口径 '
               f'{ST_NN_ALL["sd_r"]:,.1f}pp 的 {ST_NN_ALL["sd_m"] / ST_NN_ALL["sd_r"]:,.2f} 倍，'
               f'相邻月最大跳变 {ST_NN_ALL["jump_m"]:,.0f}pp vs {ST_NN_ALL["jump_r"]:,.0f}pp，'
               f'{len(ST_NN_ALL["flips"])} 个月两种口径符号相反。' if ST_NN_ALL else '')
            + f'<b>唯一的例外是 Exhibit 6</b>（隐含佣金收入/日）：它的乘数 CPT 只存在于月度'
            f'新闻稿里、本地只缓存 {len(WIN)} 个月，凑不出滚动同比要的 24 个月历史，'
            '所以那一张仍是单月同比 —— 这是数据长度的限制，不是口径选择，图注里写明了。'
            '(2) <b>点对点（单月）同比</b>（本月末 ÷ 去年同月末 − 1）—— Exhibit 10 / 11'
            '（融资余额）、12 / 13（客户现金）与 Exhibit 1 汇总表的 y/y 列；'
            '顶部「本月读数怎么读」一段中标明「单月」的读数与汇总表同口径、可逐格对上，'
            '同属 (2) —— 该段引用的 12 个月滚动同比已在句内点名（Exhibit 3 的口径），'
            '属 (1)。'
            '<b>这里要更正一句本站从前的说法</b>：「存量不能做滚动，所以只能点对点」是'
            '<b>错的</b> —— Σ12/Σ12′ 里的除数约掉，12 个月滚动合计比恒等于 12 个月滚动'
            '<b>均值</b>比，而「去年一整年的平均客户现金 vs 前年」是个真实存在的量。'
            '假的只是<b>「合计」这个名字</b>（12 个月末余额相加不指代任何东西）。'
            '所以存量<b>可以</b>平滑，本页仍用点对点，理由由实测给出：'
            + (f'客户现金换成 12 个月均值同比，标准差从 {ST_CR["sd_m"]:,.1f}pp 涨到 '
               f'{ST_CR["sd_r"]:,.1f}pp（<b>反而更吵</b>），两种口径 {len(ST_CR["flips"])} '
               '个月符号相反。' if ST_CR else '')
            + _CAL_TXT
            + f'<b>Exhibit 15（T12M 净新增账户）本来就是滚动口径的水平值</b>'
            f'（当期 {roll12[-1]:,.0f}k），Exhibit 3 现在画的正是它的同比 —— '
            '本轮之前这两张一张滚动一张单月，同一页里对同一件事给两个答案。',

            '<strong>纵轴</strong>：Exhibit 14-17 四张长历史图一律<strong>从 0 起</strong>。'
            '引擎默认的下界是「最小值 − 极差 5%」，那是一次没有标注的隐性截轴，'
            '会把这四张图标题里引用的倍数与降幅（53% below／14.0x／不到一半）在视觉上凭空放大。'
            '本页没有任何一张图设了截轴（ycap／yfloor）——各图序列量纲一致、没有把其余序列压平的离群尖峰。',
            '<strong>窗口</strong>：Exhibit 2-13 固定为最近 13 个月（便于 YoY 首末对比与 prior-12mo '
            f'均值计算，本次为 {XL[0]} – {XL[-1]}）；Exhibit 14-18 为 {ALL[0]} 起的全历史；'
            'Exhibit 1 的 3Y %ile 取近 36 个月。窗口一律从数据最新月倒推，不依赖构建当天的日期。',
            'Exhibits 14-17 of the original Goldman Sachs note (IBKR app downloads and MAU) rely on '
            'proprietary Sensor Tower data and cannot be updated from public company disclosures; '
            '本站的 Exhibit 14-18 是另加的长历史图，与原 note 的编号无对应关系。',
            '本页图表版式模仿 Goldman Sachs GIR exhibit 风格，仅为视觉版式，不含其研究观点或数据。'
            '仅供个人研究，不构成投资建议。',
        ],
        'footer': ('数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
                   '数值以 IBKR 官网原始披露为准。每张图右上角可切换「表格」视图逐条核对。'),
    }
    if source_date:
        payload['source_date'] = source_date

    path = os.path.join(ROOT, 'data', 'ibkr.js')
    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    # 这里原来是裸 json.dump（allow_nan 默认 True），最新行少一个值就把字面 NaN
    # 写进 data/ibkr.js —— 文件变成非法 JSON、合法 JS，页面照渲染而退出码是 0。
    payload_guard.write_dash(path, payload, 'ibkr')

    print(f'目标月 {target} | 窗口 {WIN[0]} → {WIN[-1]}（{len(WIN)} 个月）| '
          f'长历史 {ALL[0]} → {ALL[-1]}（{len(ALL)} 个月）')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）+ '
          f'Exhibit {table["n"]} 核对表')
    print(f'口径脚注 {len(notes)} 条，命中月份 {flagged}')
    print(f'写出 data/ibkr.js ({os.path.getsize(path)/1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
