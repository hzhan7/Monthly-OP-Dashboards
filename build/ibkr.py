# -*- coding: utf-8 -*-
"""Interactive Brokers (IBKR) 月度经营指标 —— 网页看板 payload 生成器。

由独立仓 `ibkr-monthly-metrics/build_data.py` 移植而来。移植当时**图一张都没改**
（Exhibit 2-18 的序列、标题文案、图注、断点、截轴逐字照搬），只做两件事——

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
    （历史指标表里没有这两列，CSV 也就没有）；页尾脚注里「交易所／清算／监管费用占
    期货佣金的百分比」也在这份稿子里，**公司逐月披露、每月都在动**，故一律现算。
    解析函数复用 `fetch/ibkr_source.py`（`parse_pr` / `parse_pr_fut_fee`），
    不重写：解析口径只能有一处定义，各写一份迟早分叉，而分叉的表现是
    「fetch 落库的数与网页画出来的 CPT 对不上同一个月」——最难发现的那种错。
    （`ibkr_source.py` 搬自已删除的 `/IBKR月度指标` skill 的 `build_report.py`，逐字复制；
    `parse_pr_fut_fee` 是本仓后加的，原 skill 里没有这一句的解析。）
  · `cache/ibkr/hist_latest.pdf` —— 只取 Notes 段的**文字**
    （账户口径调整的原文），用作护栏与图注；一个数字都不从这里取。

═══ 口径 ═══
  历史指标表首个区块 "(in Thousands, except Trading Days)" —— 账户/DARTs/合约/股数以千计；
  第二区块 "(in Billions)" —— 客户权益/现金/融资余额。
  新闻稿 Key products 两列 = Average Order Size（股/张）与 Average Commission per Cleared
  Commissionable Order（$/笔），**不是每股/每张单价**。

═══ 窗口（2026-08 重构，原来是手搓的 13 个月）═══
  全站规矩：**数据只要存在就必须从 2016-01 画起**。本页原先 Exhibit 2-13 走的是自己
  在这里手搓的 13 个月窗口（`for d in range(-12, 1)`），而 `series/ibkr.csv` 从上线
  第一天起就是 2016-01 起的**全部**月份 —— 窗口外那十年是**画的时候扔掉的，不是没有**。
  （月数逐月增长，所以不在这里写死一个数；页尾 notes[0] 印的是 `len(ALL)`，现算。）

  Exhibit 2-5 / 10-13   CSV 全历史（2016-01 起，逐月连续）。派生序列算不出的头几期
                        由 `build/mrwin.py::resolve()` 裁左端（滚动同比要 24 个月、
                        单月同比要 12 个月、implied cleared DARTs 要上月账户数）。
                        **裁的是「算不出来的那几期」，不是「掐头到好看的地方」**：
                        左端停在哪一期与为什么，由那边生成一句话写进图注。
                        缺的期一律 NaN → null，绝不补 0、绝不回退成上一期的值。
  Exhibit 6-9           只覆盖**月度新闻稿**缓存区间，见下。
  Exhibit 14-17         同样 2016-01 起全历史（本来就是；原 Exhibit 14 已并入 Ex5，
                        见 Exhibit 5 处的注释，其后各图顺次前移一号）。
  Exhibit 1 的 3Y %ile 取近 36 个月；文末核对表固定最近 13 个月（那是核对表不是图）。

  ⚠ 新闻稿窗口：CPT（单笔佣金）与 Average Order Size **只在月度新闻稿里**，历史指标
  表没有这两列，CSV 也就没有。所以 Exhibit 6/7/8/9 的长度 = `cache/ibkr/pr_YYYYMM.pdf`
  中**紧贴最新月的那一段连续缓存**，由构建期扫出来，不写死。不去拿不连续的旧稿凑长度：
  缓存里还躺着一份孤立的 2024-11，接上去会把 Nov-24 与 Jun-25 画成相邻两格
  （CONTRACT 规矩 3 的假时间轴）。fetch/ibkr.py 每月下一期，这段会自己变长。

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
import mrwin          # 左端裁决与通栏/抽稀裁决的唯一实现（**只调用，不改**）
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
    读者会停下来猜它是不是缺失值（同一个毛病在 tsm Ex12 / exchanges Ex8 被人眼审查逮到）。
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


def half_day(v):
    """交易日专用：官方就是**半天**粒度（19.5 / 20.5 / 21.5），照印，不取整。

    取整会两头出错 —— Python 的格式化走 round-half-even：`f'{20.5:.0f}'` 给 '20'、
    `f'{21.5:.0f}'` 给 '22'，同一种「半天」在同一张表里被舍成两个方向。而页尾那张表
    的表头写着「官方原始单位，未换算」、用途正是拿着官方 PDF 逐格对数，取整恰好把
    这个用途毁掉。带半天的月份在 series/ibkr.csv 里不止一个（美股半日市：独立日前夜、
    感恩节次日、平安夜），随时会落进这张表的 13 行窗口，所以不能靠「当期恰好没有」蒙混。
    整数月照旧不带小数点（官方也写 '22'），只有半天才多出那个 .5。
    """
    s = f'{v:.1f}'
    return s[:-2] if s.endswith('.0') else s


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
# 本页实测（对齐到两种口径都算得出的同一批月份）：净新增账户的单月同比标准差高于
# 滚动口径，相邻月最大跳变高出一大截，且有相当一批月份两种口径**符号相反**。
# **具体数字与量级形容词一概不写死在注释里** —— 全部由 `cal_stats()` 每次构建现算，
# 印在 Exhibit 3 的图注与页尾口径说明里。窗口 2026-08 从 13 个月改成全历史时，原来
# 写在这里的「4.3 倍 / 95pp vs 9pp」就是这么变成假话的；同一次改动也让「数倍」这种
# 看着不像数字的说法跟着失真（倍数掉了一大截），所以连它一并删掉。真有一天方向翻转，
# 图注会自己说出来，注释不该抢在它前面下结论。
# 本页早就有一条现成的滚动口径线 —— Exhibit 14 画的就是 T12M 净新增账户，
# Exhibit 3 的新口径正是那条线的同比，两张图从此对得上。
#
# ⚠ 只对**流量**这么改。存量 / 期末口径（账户总数、客户权益、客户现金、融资余额）
# 不做滚动**合计**（那对存量是个假名字）。存量换成 12 个月**均值**同比是否更平滑，
# 同样由 `cal_stats()` 现算、由 `stock_note()` 按两个标准差之比自动选措辞（比值 < 1
# 才说「更吵」），注释里不复述结论。这里原先写着「客户现金换成 12 个月均值同比，标准差
# 从 2.8pp 涨到 3.6pp（更吵）」—— 那是**13 个月窗口**上的读数，窗口拉到全历史后方向
# 就反了（均值口径反而更平滑），而页面上同一句早已跟着现算改对，只剩这句注释在打对台。
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
    # 交易日走 half_day 而不是 :.0f：官方按半天披露（19.5 / 20.5 / 21.5），取整会把
    # 「多 1.5 天」说成「多 2 天」，而这句话的全部作用就是给读者一个可核对的日历修正。
    s3 = (f'先扣日历：{B.mo(ALL[i])}月{half_day(td[i])}个交易日比{B.mo(ALL[i - 1])}月多'
          f'{half_day(co["dday"])}天，期权表面跌{abs(co["raw"]) * 100:.1f}%、'
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

    # ── 全历史轴（本页除 Exhibit 6-9 外全部图都画在它上面）：必须逐月连续，
    #    否则 12 个月滚动和与 y/y 会按位置错位 ──
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

    # ── 主窗口 = 全历史 ──
    # 这里原来是 `for d in range(-12, 1)` 的 13 个月手搓窗口。窗口拉到 127 个月之后，
    # prevm / yagm 必然越界：2016-01 没有 2015-12，更没有 2015-01。**越界不是错误，
    # 是事实** —— 缺的那几期给 NaN，左端由 mrwin.resolve() 逐图裁，不掐头也不补 0。
    WIN, XL = list(ALL), list(XL_LONG)
    prevm, yagm = {}, {}
    for w in WIN:
        py, pmo = month_add(int(w[:4]), int(w[5:7]), -1)
        prevm[w] = f'{py}-{pmo:02d}'
        yagm[w] = f'{int(w[:4]) - 1}-{w[5:]}'
    # 只校验 WIN 自身（连续性上面已硬校验过）。prevm/yagm 里落在 2015 年的那几个键
    # 本来就不存在 —— 把它们并进 need 会让整个构建在「2015-01 缺失」上失败，
    # 而那正是「首年没有同比基数」的正常表现。
    missing = sorted(w for w in WIN if w not in series)
    if missing:
        raise SystemExit(f'series/ibkr.csv 缺月份: {missing}')

    # ── 月度新闻稿（佣金与订单规模）：只读缓存，不下载（下载是 fetch/ibkr.py 的职责）──
    # 窗口 = 紧贴最新月的那一段**连续**缓存，扫出来而不是写死 13。
    # 判有效而不只判存在：下载失败会在磁盘上留下 0 字节残骸，只判 exists 会放它过去，
    # 然后 br.parse_pr 崩在 EmptyFileError —— 报错点离真正的病因（一次瞬时 404）很远。
    def _pr_path(m):
        return os.path.join(CACHE, f'pr_{m.replace("-", "")}.pdf')

    def _pr_ok(m):
        p = _pr_path(m)
        return os.path.exists(p) and os.path.getsize(p) >= 5000

    if not _pr_ok(target):
        raise SystemExit(f'新闻稿缓存缺失或损坏 {_pr_path(target)}（删掉它再跑 fetch/ibkr.py）')
    _pi = ALL.index(target)
    _p0 = _pi
    while _p0 - 1 >= 0 and _pr_ok(ALL[_p0 - 1]):
        _p0 -= 1
    PWIN, PXL = ALL[_p0:_pi + 1], XL_LONG[_p0:_pi + 1]
    COMM = {m: br.parse_pr(_pr_path(m)) for m in PWIN}
    # 页尾脚注要的「交易所／清算／监管费用占期货佣金」比例：**公司逐月披露、每月都在动**，
    # 一律从目标月的新闻稿现算。原先这里写死了一个 56%（某一期的读数），而目标月那期是 54%
    # —— 一个不随数据走的常数，只要月份一翻就变成假话。缓存区间的跨度一并印出来，
    # 免得读者把当期这一个数当成公司的固定口径。
    FUT_FEE = {m: br.parse_pr_fut_fee(_pr_path(m)) for m in PWIN}
    # 连续段之外还缓存着的月份：**不接进图里**（接上去就是假时间轴），但要打印出来，
    # 否则「明明磁盘上有 15 份稿子、图上只有 14 个点」会看起来像丢数据。
    _pr_orphan = [m for m in ALL[:_p0] if _pr_ok(m)]

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

    # ── 全历史派生序列（本页除 Exhibit 6-9 外全部图的底料）──
    # 顺序上必须在窗口序列**之前**：窗口现在就是全历史，窗口序列直接复用这批数组，
    # 不再各算一遍（各算一遍正是「同一个量在两处给出不同结果」的来源）。
    A = lambda f: np.array([series[m][f] if series[m][f] is not None else np.nan for m in ALL], float)
    ann_all, acc_all, eq_all = A('ann_dart_acct'), A('accounts'), A('equity')
    cr_all, mg_all, dart_all = A('credits'), A('margin'), A('darts')
    nn_all = np.array([real_nn[m] for m in ALL], float)
    nn_rep = A('net_new')                                    # 表内披露值（未还原），Ex2 画它
    # 顶部 brief 的日历护栏（R3）要的三条：交易日数与两条**当月合计**成交量列。
    # 用原始合约数／股数而不是 Ex8 的 product DARTs —— 后者要除以新闻稿里的平均订单
    # 规模，而新闻稿只缓存了最近十几个月，长历史那半段算不出来。
    td_all, opt_all = A('trading_days'), A('opt_contracts')
    fut_all, stk_all = A('fut_contracts'), A('stk_shares')

    roll12 = np.full(len(ALL), np.nan)
    for i in range(11, len(ALL)):
        roll12[i] = nn_all[i - 11:i + 1].sum()
    cleared_all = np.full(len(ALL), np.nan)
    # 首月画不出来：推导式要**月初**账户数，而 2016-01 的上月不在序列里。
    # 这一格保持 NaN → 由 mrwin.resolve() 把 Exhibit 4 的左端裁到 2016-02，
    # 不是补 0，也不是拿当月账户数当月初值凑（那会造出一个数据里不存在的点）。
    cleared_all[1:] = ann_all[1:] / 252 * (acc_all[1:] + acc_all[:-1]) / 2
    # 右轴画「未清算占比」而不是 cleared/total 本身：bar_line_dual 的右轴强制含 0，
    # 而 cleared/total 常年贴着 100%，整条线会被挤进轴顶极窄的一条带里，2025 那个台阶
    # 只剩几个像素。取补数后序列贴近 0，量程自己展开，台阶清清楚楚，信息一模一样
    # （两者相加恒为 100%）。**具体区间不写死在这里** —— 原来写的「84%~92% / 量程 0-16%」
    # 是 13 个月窗口上的读数，窗口拉到全历史后上沿就越过 92 了。
    noncl_all = 100 - cleared_all / dart_all * 100
    cr_share = cr_all / eq_all * 100
    mg_share = mg_all / eq_all * 100
    cov_cleared = cleared_all / dart_all * 100                # 推导 cleared 对披露总量的覆盖率

    # ── 主窗口序列（WIN ≡ ALL，直接引用上面的数组）──
    net_new = nn_rep                                         # Ex2 画的是表内披露值
    nn_real = nn_all                                         # Ex3 的 y/y 用还原值
    ann_dart, cleared = ann_all, cleared_all
    margin, credits = mg_all, cr_all
    # GS 规矩 2：融资余额与客户现金都不是高增速指标，m/m 只是 ±2% 噪音，改画 y/y。
    # 原来是 `margin / [series[yagm[m]]['margin'] …]` —— 逐月去字典里取去年同月，
    # 窗口一到 2016 年就 KeyError（2015 年本站一格数据都没有）。改走 build/yoy.py 的
    # 单月同比：它按位置 shift(12)，头 12 期自然是 NaN，正是「首年没有同比基数」的表达。
    # 两者在都算得出的月份上完全等价（(v/v.shift(12)-1)*100 ÷ 100）。
    marg_yoy = mono_yoy_arr(mg_all, ALL)
    cred_yoy = mono_yoy_arr(cr_all, ALL)

    # ── 新闻稿窗口序列（Exhibit 6-9）──
    # CPT 与 Average Order Size 只有新闻稿有，所以这四张图短，短的是**数据**不是窗口。
    P = lambda f: np.array([series[m][f] for m in PWIN], float)
    cpt = np.array([COMM[m][0] for m in PWIN])
    stk_os = np.array([COMM[m][1] for m in PWIN]); stk_cpt = np.array([COMM[m][2] for m in PWIN])
    opt_os = np.array([COMM[m][3] for m in PWIN]); opt_cpt = np.array([COMM[m][4] for m in PWIN])
    fut_os = np.array([COMM[m][5] for m in PWIN]); fut_cpt = np.array([COMM[m][6] for m in PWIN])
    ptd = P('trading_days')
    stk_d = P('stk_shares') / stk_os / ptd
    opt_d = P('opt_contracts') / opt_os / ptd
    fut_d = P('fut_contracts') / fut_os / ptd
    pct_fo = (opt_d + fut_d) / (stk_d + opt_d + fut_d)
    cov_prod = (stk_d + opt_d + fut_d) / P('darts') * 100     # 推导产品 DARTs 对披露总量的覆盖率
    # 量纲：cleared（千笔/日）× cpt（$/笔）= 千美元/日；÷1000 → 百万美元/日（$mn/day）
    comm_day = cleared_all[[ALL.index(m) for m in PWIN]] * cpt / 1000

    # ── 窗口无关的取数助手 ──
    # ⚠ 这三个原来写死了 13 格窗口的下标（`a[:12]` / `a[-1]/a[0]`），在 13 格里恰好
    #   等价于「前 12 个月」与「对去年同月」；窗口一变它们就静默改口径：a[:12] 变成
    #   「2016 年的均值」，而 gs_bar 的图例仍写着 Prior 12mo Avg.。改成按尾部定位。
    LAG = 12

    def avg12(a):
        """当期之前 12 个月的均值 —— gs_bar 那条虚线（Prior 12mo Avg.）。"""
        return float(np.nanmean(np.asarray(a, float)[-(LAG + 1):-1]))

    def yoy(a):
        """末期对 12 个月前的同比（小数）。算不出返回 NaN。"""
        a = np.asarray(a, float)
        if len(a) <= LAG:
            return float('nan')
        c, b = a[-1], a[-1 - LAG]
        if not (np.isfinite(c) and np.isfinite(b)) or b == 0:
            return float('nan')
        return float(c / b - 1)

    mom = lambda a: float(a[-1] / a[-2] - 1)
    # 一律走 LN：窗口拉长之后派生序列的头几格是 NaN，裸 L 会把字面 NaN 送进 JSON
    # （payload_guard 会拦，但拦在最后一步，报错点离病因很远）。
    LN = lambda a: [None if v is None or not np.isfinite(v) else round(float(v), 6) for v in a]
    L = LN

    def yr_mean(arr, yr):
        idx = [i for i, k in enumerate(ALL) if k[:4] == yr]
        return float(np.nanmean(arr[idx])) if idx else float('nan')

    # 首年与当年（Exhibit 5 的年均对照要用，原先定义在长历史那一段的开头）
    y16, ylast = ALL[0][:4], target[:4]
    pre25 = [i for i, k in enumerate(ALL) if k < '2025-01']
    post25 = [i for i, k in enumerate(ALL) if k >= '2025-01']

    # ── 两种同比口径，一次在全历史上算完，各图按位置取 ──
    # 一律在**全历史**上算完再切窗：切完再算的话窗口最前 12 期永远是空的。
    # 窗口现在就是全历史，POS 因此是 range(len(ALL))；保留这个间接层是为了让
    # 「窗口内实测」与「全历史实测」在代码里仍是两个可分辨的概念 —— 哪天窗口再变短，
    # 下面那批 cal_stats 的口径不用再改一遍。
    POS = [ALL.index(w) for w in WIN]
    NN_MONO, NN_ROLL = mono_yoy_arr(nn_all, ALL), roll_yoy_arr(nn_all, ALL)
    CL_MONO, CL_ROLL = mono_yoy_arr(cleared_all, ALL), roll_yoy_arr(cleared_all, ALL)
    AN_MONO, AN_ROLL = mono_yoy_arr(ann_all, ALL), roll_yoy_arr(ann_all, ALL)
    # 存量三条的反事实对照口径是滚动**均值**（不是「合计」，见 mean_yoy_arr 的 docstring）
    ST_MG = cal_stats(mono_yoy_arr(mg_all, ALL), mean_yoy_arr(mg_all, ALL), POS, ALL)
    ST_CR = cal_stats(mono_yoy_arr(cr_all, ALL), mean_yoy_arr(cr_all, ALL), POS, ALL)
    ST_NN = cal_stats(NN_MONO, NN_ROLL, POS, ALL)
    ST_CL = cal_stats(CL_MONO, CL_ROLL, POS, ALL)
    ST_AN = cal_stats(AN_MONO, AN_ROLL, POS, ALL)
    # 全历史（不切窗）的净新增账户对照 —— 页尾口径说明用。窗口拉到全历史之后它与
    # ST_NN 恒等，所以 Exhibit 3 的图注里那段「把范围放到全历史差距更清楚」已经删掉：
    # 两个数字一模一样时那句话是在把同一件事说两遍。
    ST_NN_ALL = cal_stats(NN_MONO, NN_ROLL, list(range(len(ALL))), ALL)

    def at(a):
        """某条同比序列在**本页目标月**的读数（小数）；算不出返回 None。"""
        v = a[ALL.index(target)]
        return None if not np.isfinite(v) else float(v)

    # ── Exhibit 定义（标题文案逐字照抄 build_report.py 的 title_src 调用）──
    ex = []

    # ⚠ 口径调整月的标记方式换了（窗口 13 → 127 逼出来的）。
    # 原来是往 x 轴标签里塞一个 †（`XL2 = [x + '†' …]`）。127 个月的轴由 mrwin 按
    # xstep 抽稀标签，被标的月份多半不落在保留下来的那批标签上 —— † 会**静默消失**，
    # 而图注还在讲「† 的月份」。所以标记改为只走 `bar_marks`（斜纹柱，引擎逐柱都画、
    # 从不抽稀，且鼠标悬停会带出 mark_note），x 轴标签恢复成干净的月份。
    adj_nn = [k for k, a in ADJ.items() if a['field'] == 'net_new']

    # 图注只许声称**图上真有**的东西：措辞按窗口内实际被标记的月份现算。
    # 全历史窗口下三次调整都在窗口内，但这个判断保留着 —— 它防的是措辞与图脱节，
    # 不是防某个特定的月份（窗口哪天再变，这段自己会跟着变）。
    mk2 = [w for w in WIN if w in adj_nn]                             # Ex2 上真正标了斜纹的月份
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
        'n': 2, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': XL, 'xstep': 12,
        'title': f'IBKR added ~{net_new[-1]:.0f}k net new accounts, with monthly account growth {pctf(mom(net_new))} MoM…',
        'ylab': 'Net New Accounts (thousands)',
        'note': ('柱画的是历史指标表披露的 Net New Accounts（= 账户存量差分），'
                 f'{XL[0]} 起逐月，一格没有跳过。'
                 # 窗口从 13 拉到 127 之后这条虚线的含义必须写明白：它没有变成滚动均值。
                 '虚线是<b>最近 12 个月</b>（不含当期）的均值，也就是右端那一格的参照水平，'
                 '<b>不是逐月滚动均值</b> —— 一条横线跨过全图时读者很容易把它读成后者。'
                 + (f'含一次性口径调整、不可与相邻柱直读的月份以<b>斜纹柱</b>标出'
                    f'（悬停有说明）：{adj_txt}。' if mk2 else
                    f'本窗口内没有需要标注的调整月（全部调整见页尾说明：{nn_adj_txt}）。')
                 + 'Exhibit 3 的 y/y 已用还原值。'
                 + ('<br>PDF Notes 原文：' + ' / '.join(nt['text'] for nt in notes) if notes else '')),
        'legend': 'Net New Accounts', 'values': L(net_new), 'avg12': avg12(net_new),
        # 气泡里的 y/y 换成滚动口径，与 Exhibit 3 的那条线、Exhibit 14 的 T12M 水平线
        # 是同一个数。原来这里是单月同比，与同页那张 T12M 图讲的是两件事。
        'yoy_txt': (pctf(at(NN_ROLL)) + ' y/y·12M' if at(NN_ROLL) is not None
                    else pctf(yoy(nn_real)) + ' y/y·单月'),
        # ⚠ 这张图**不给 mom_txt**，另外三张 gs_bar（Ex4/10/12）给。差别不是排版偏好，
        # 是这里的气泡与本图标题**同源**：标题那句 'monthly account growth … MoM' 里的数
        # 就是 `pctf(mom(net_new))`，与气泡是同一个表达式，永远逐字相同。Ex4/10/12 的
        # 标题不含 MoM，气泡是它们唯一的环比读数，所以保留。
        #
        # 顺带记一个**系统性**的量：窗口拉到 127 根柱之后，charts.js 把 MoM 气泡钉在
        # `Xc(n-4) + band*0.2`，band 只剩 8.3px（13 个月窗口时 ~78px），气泡（宽 ~63px）
        # 于是整个压进末柱数值标签（宽 ~34px）的横向区间 —— 1280px 实测四张图的横向
        # 交叠都在 8.9–13.7px，**没有一张是分开的**。真正把它们分开的只有纵向，而纵向
        # 间距 = Y(min(last*1.13, y1*0.94)) 与 Y(last)−4.5 之差，完全由 last/量程决定：
        # Ex12 差 −1.0px（刚好错开）、Ex10 +0.7px、Ex4 +3.2px、Ex2 +7.3px。
        # 也就是说这四张谁越线只取决于当月数据，今天只有 Ex2 超了 visual_qa 的 8px² 底噪。
        # 不用「把 Ex2 调高一点」的办法收：那是拿一个写死的 height 去追一个随数据漂的
        # 间距，下个月就可能换成 Ex4 越线，而 Ex2 白高出 40px。
        'bar_marks': [i for i, w in enumerate(WIN) if w in adj_nn],
        'mark_note': '该月含一次性账户口径调整，不可与相邻柱直读（见图注）',
    })
    # 净新增账户是**流量**：同比换成 12 个月滚动合计口径。
    # 本页早就有一条现成的滚动线 —— Exhibit 14 画的就是 T12M 净新增账户，
    # 这张图画的正是那条线的同比，两张图对得上（原先一张滚动、一张单月）。
    #
    # ⚠ 左端：`gs_line` 属 mrwin.DENSE（Catmull-Rom 平滑 + 逐点标数值），前导 null
    #   会被当 0 插值、还会在标数值那步抛 TypeError。而滚动同比按定义要 24 个月历史
    #   （12 个月填窗 + 12 个月比较），序列头 23 期**算不出来**。所以左端交给
    #   `mrwin.resolve()` 裁到「第一个真的有读数的月」——这是真实起点，不是掐头：
    #   2016-01 至 2017-11 不是被藏起来了，是那些月份的 12 个月滚动同比不存在。
    #   备选是改成非 DENSE 的 `lines` 并保留 23 个空格，本页不选：那 23 格空白占全图
    #   五分之一宽，而它承载的信息（「这里算不出」）一句图注就说完了。
    nn_roll_win = np.array([NN_ROLL[i] for i in POS], float)
    _n3 = int(np.isfinite(nn_roll_win).sum())
    _use_roll3 = _n3 >= 6
    _v3full = (nn_roll_win if _use_roll3 else np.array([NN_MONO[i] for i in POS], float)) * 100
    _lag3 = ('12 个月滚动合计同比要 24 个月历史（12 个月填窗 + 12 个月比较）'
             if _use_roll3 else '单月同比要 12 个月历史')
    _w3 = mrwin.resolve('gs_line',
                        [mrwin.Leg('nn', '净新增账户同比', _v3full, 'primary', _lag3)], XL, 0)
    XL3, _v3 = _w3.cut(XL), np.array(_w3.cut(_v3full), float)
    _cur3 = float(_v3[-1])
    # 图注分段拼，不写成一个长三元表达式 —— 那种写法上一版在别的页上把「if 只作用于
    # 最后一段」这个优先级坑踩过一次，整段文案在某个分支下会静默丢掉。
    _n3_note = (f'分子分母一律用公司 Notes 还原后的真实账户增长：{nn_adj_txt}。'
                # 原来这里靠 x 轴标签上的 † 点名受影响的月份。窗口 127 个月、标签抽稀之后
                # † 多半不在图上，且**滚动口径下每个调整月会进入其后 24 个月的比较窗**，
                # 逐月打点本来也标不准 —— 改成把调整月本身列清楚。
                + (f'滚动口径下每次调整会影响其后 24 个月的读数，逐月标注反而失真，'
                   f'故只列调整月本身（上句）。' if _use_roll3 else '')
                + (f'直接用表内差分会让 {naive_ex[0]} 的单月同比从 {pctf(naive_ex[1])} '
                   f'虚高到 {pctf(naive_ex[2])}。' if naive_ex else ''))
    if _use_roll3:
        _n3_note += roll_note(ST_NN)
        _n3_note += (f'本图与 Exhibit 14 是同一件事的两种画法：那张画 T12M 净新增账户的'
                     f'<b>水平值</b>（当期 {roll12[-1]:,.0f}k），这张画它的<b>同比</b>。'
                     '两张图从此对得上 —— 原先一张滚动、一张单月，读者无从知道该信哪个。')
    else:
        _n3_note += (f'本序列在本窗口内只有 {_n3} 个滚动同比读数（滚动同比要 24 个月历史），'
                     '不足以画一条线，故仍用<b>单月同比</b> —— 这是数据长度的限制，'
                     '不是口径选择；判据写成条件，历史够了这张图会自己切到滚动口径。')
    ex.append({
        'n': 3, 'kind': 'gs_line', 'fmt': 'pct0z', 'xlabels': XL3, 'xstep': 12,
        'title': (f'…and net new accounts {"growing" if _cur3 > 0 else "declining"} '
                  f'{abs(_cur3):.0f}% YoY'
                  + (' (12M rolling)' if _use_roll3 else ' (single-month 单月同比)')),
        'ylab': ('Net new accounts, 12M rolling y/y (%)' if _use_roll3
                 else 'Change in Net New Accounts YoY, 单月 (%)'),
        'values': L(_v3),
        'note': _n3_note + _w3.why,
    })
    # cleared DARTs 是**流量率**（每天多少笔）：气泡与标题的 y/y 换滚动口径。
    # 左端：推导式要**月初**账户数，序列首月没有上月 → cleared_all[0] 恒为 NaN。
    # gs_bar 不属 DENSE、能吃前导 null，但那一格是「算不出」而不是「为 0」，
    # 留一根空柱在最左边只会让人以为那个月没数据。交给 resolve() 裁到 2016-02。
    _w4 = mrwin.resolve('gs_bar',
                        [mrwin.Leg('cl', 'Implied cleared DARTs', cleared_all, 'primary',
                                   '推导式要月初账户数，序列首月没有上月')], XL, 0)
    XL4, cl4 = _w4.cut(XL), np.array(_w4.cut(cleared_all), float)
    _y4 = at(CL_ROLL)
    _y4v = _y4 if _y4 is not None else yoy(cl4)
    _cov_lo, _cov_hi = float(np.nanmin(cov_cleared)), float(np.nanmax(cov_cleared))
    ex.append({
        'n': 4, 'kind': 'gs_bar', 'fmt': 'f0c', 'xlabels': XL4, 'xstep': 12,
        'title': f'Implied cleared DARTs came in {abs(_y4v)*100:.0f}% {"higher" if _y4v > 0 else "lower"} YoY '
                 + ('(12M rolling)' if _y4 is not None else '(单月)')
                 + f', and {abs(cl4[-1]/avg12(cl4)-1)*100:.0f}% '
                 f'{"above" if cl4[-1]/avg12(cl4)-1 > 0 else "below"} the prior 12-month average…',
        'ylab': 'Cleared DARTs (thousands of trades/day)',
        'note': 'We calculate cleared DARTs = Cleared avg. DART per account (annualized) / 252 trading days * '
                'average of beginning- and end-of-month total accounts. '
                '假设：账户数在月内线性变化（故取期初期末简单平均）；官方的年化口径就是按 252 天折算，'
                '不要换成当月实际交易日。'
                # 窗口从 13 个月拉到全历史之后这个区间会宽很多 —— 数字现算，不留旧窗口的实测值。
                f'结果约为 IBKR 单独披露的 Total Client DARTs 的 {_cov_lo:.0f}%–{_cov_hi:.0f}%'
                f'（{XL4[0]}–{XL4[-1]} 全区间，中位 {float(np.nanmedian(cov_cleared)):.0f}%），'
                '差额是口径差（cleared ≠ total client，见 Exhibit 17），不是估算误差。'
                + roll_note(ST_CL),
        'legend': 'Implied Cleared DARTs', 'values': L(cl4), 'avg12': avg12(cl4),
        'yoy_txt': (pctf(_y4) + ' y/y·12M') if _y4 is not None else (pctf(yoy(cl4)) + ' y/y·单月'),
        'mom_txt': pctf(mom(cl4)),
    })
    ex[-1]['note'] += _w4.why
    # ── Exhibit 5：人均年化 cleared DART ──────────────────────────────────────
    # 两处改动，理由都在这里：
    #
    # ① **图种从 `gs_line` 换成 `lines` + `zero_base`。** 窗口拉到全历史之后，本图与
    #    原 Exhibit 14 画的是**同一列 CSV（ann_dart_acct）、同一段月份**——两张一模一样
    #    的图。所以把两张合成一张：保留 Exhibit 5 的位置（Exhibit 4 的标题以「…」结尾，
    #    接的就是这张的「…leading to」，GS deck 的叙事链不能断），采用原 Exhibit 14 的
    #    画法（`lines` + `zero_base`）。**`zero_base` 只有 `lines` 认**（charts.js:48），
    #    而它是必须的：本图标题引用「比 2016 年低 N%」这种幅度，引擎默认下界是
    #    「最小值 − 极差 5%」，那是一次没有标注的隐性截轴，会把这个幅度在视觉上放大。
    #    顺带的好处：`lines` 不属 mrwin.DENSE，127 个点也不再逐点标数值。
    # ② 原 Exhibit 14 就此删除，其后各图（T12M 净新增 / 客户权益 / 生息基数占比 /
    #    Total DARTs）顺次前移一号，编号连号由文末的 `_ens` 硬校验兜底。
    _y5 = at(AN_ROLL)
    _y5v = _y5 if _y5 is not None else yoy(ann_all)
    _a16, _alast = yr_mean(ann_all, y16), yr_mean(ann_all, ylast)
    _y5g = (1 - _alast / _a16) * 100
    ex.append({
        'n': 5, 'kind': 'lines', 'fmt': 'f0', 'xlabels': XL, 'xstep': 12, 'zero_base': True,
        'title': f'…leading to {pctf(_y5v)} annualized cleared DARTs per account vs. last year'
                 + (' (12M rolling)' if _y5 is not None else ' (单月)')
                 + f'; {_a16:.0f}x avg. in {y16} → {_alast:.0f}x YTD in {ylast}, {_y5g:.0f}% below',
        'ylab': 'Annualized cleared DARTs / account (x)',
        'series': [{'name': 'Cleared avg. DART per account (annualized)', 'color': 'NAVY',
                    'values': L(ann_all)}],
        'note': '<b>公司直接披露的 Cleared Avg. DART per Account (Annualized)，非推导值。</b>'
                f'当月 {ann_all[-1]:.0f}x：环比 {pctf(mom(ann_all))}、'
                f'单月同比 {pctf(yoy(ann_all))}'
                + (f'、12 个月滚动合计同比 {pctf(_y5)}' if _y5 is not None else '')
                + '。年均：'
                + '、'.join(f'{y} {yr_mean(ann_all, y):.0f}x' for y in
                           [y16, '2019', '2020', '2022', '2023', ylast])
                + '。2020-21 的凸起是疫情期间的交易热潮，其后回落到的平台明显低于 2016-18 —— '
                  '本图从 2016-01 起画，正是为了让「结构性下台阶」与「周期性回落」分得开；'
                  '原先这张只画最近 13 个月，看到的只是那个已经腰斩后的低位平台在小幅抖动。'
                  '纵轴从 0 起（标题引用的是降幅，截过的轴会把降幅凭空放大）。'
                + roll_note(ST_AN),
    })
    # ── Exhibit 6-9：新闻稿窗口（PWIN）────────────────────────────────────────
    # 这四张短，短的**不是窗口是数据**：CPT 与 Average Order Size 只印在月度新闻稿上，
    # 历史指标表（= series/ibkr.csv 的全部内容）没有这两列。可用区间 = 本地已缓存且
    # 紧贴最新月的那一段连续新闻稿，由构建期扫出来。图注里逐张写明起点与原因。
    _PR_WHY = (f'<b>本图只覆盖 {PXL[0]}–{PXL[-1]}（{len(PWIN)} 个月），不是本页其余各图的 '
               f'{XL[0]} 起全历史</b>：本图要用的 CPT（单笔佣金）与 Average Order Size '
               '<b>只印在月度新闻稿上</b>，官方那份 Historical Brokerage Metrics 表（本站'
               '落库为 series/ibkr.csv 的全部 11 列）里根本没有这两列，所以更早的月份'
               '<b>不是被截掉了，是这两个数不存在于任何已入库的来源</b>。'
               f'窗口 = <code>cache/ibkr/pr_YYYYMM.pdf</code> 里紧贴最新月的连续区间，'
               '构建期扫出来、不写死，每月自动长一格。'
               + (f'缓存里另有 {"、".join(_pr_orphan)} 的稿子，与上述区间之间断了 '
                  f'{ALL.index(PWIN[0]) - ALL.index(_pr_orphan[-1]) - 1} 个月，'
                  '<b>没有接进来</b>——接上去会把不相邻的两个月画成相邻两格。'
                  if _pr_orphan else ''))
    _y6 = yoy(comm_day)
    _y6ok = np.isfinite(_y6)
    ex.append({
        'n': 6, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': PXL,
        'title': ('Implied commission revenue/day came in '
                  + (f'{abs(_y6)*100:.0f}% {"higher" if _y6 > 0 else "lower"} YoY (单月) and '
                     if _y6ok else '')
                  + f'{pctf(mom(comm_day))} MoM'),
        'ylab': 'Implied Commission Revenue / Day ($mn)',
        'note': 'Commission revenue/day estimated as cleared DARTs (千笔/日) x average commission per cleared '
                'commissionable order ($/笔) ÷ 1,000 → $mn/day。'
                '假设：新闻稿披露的是 average commission per cleared <b>commissionable</b> order，而乘数是全部 '
                'cleared DART，两个总体是否一致未经证实——若 DART 计入免佣订单，本图偏高；'
                'cleared DARTs 本身也是推导值，两层近似复合。要得到月度总额还需再乘当月官方交易日数。'
                '月度无对应披露可比，季度有（10-Q 的 Commissions 行），但尚未接入。'
                + _PR_WHY
                # 这一张是本页唯一「该用滚动却用不了」的图，理由是数据长度不是口径选择。
                + f'<b>口径：本图的 y/y 是单月同比</b>，因为算不出滚动口径 —— 12 个月滚动'
                  f'合计同比要 24 个月历史，而上面那段缓存只有 {len(PWIN)} 个月。'
                  '缓存长到两年之后这张图应改成滚动口径；在那之前请把这个读数当成受基数'
                  '影响的值看，趋势以柱本身与 Exhibit 4 为准'
                  '（那张的乘数 cleared DARTs 有全历史，已经是滚动口径）。',
        'legend': 'Implied Commission Revenue/Day', 'values': L(comm_day), 'avg12': avg12(comm_day),
        'yoy_txt': (pctf(_y6) + ' y/y·单月') if _y6ok else '', 'mom_txt': pctf(mom(comm_day)),
    })
    dc = (cpt[-1] - cpt[-2]) * 100
    vs7 = cpt[-1] / avg12(cpt) - 1
    ex.append({
        'n': 7, 'kind': 'gs_line_avg', 'fmt': 'usd2', 'xlabels': PXL,
        # 用户提供的参考 PDF（2026-07-03 生成）此处是分币符号 ¢；skill 当前版本
        # （2026-07-14 改过）写的是 ASCII 'c'。以参考 PDF 为准，并且 ¢ 是正确排版。
        'title': f'Average CPT {"decreased" if dc < 0 else "increased"} by {abs(dc):.0f}¢ MoM, and was '
                 f'{abs(vs7)*100:.0f}% {"below" if vs7 < 0 else "above"} the 12-month average',
        'ylab': 'Average commission / DART ($)', 'values': L(cpt), 'avg12': avg12(cpt),
        'legend': 'Avg. Commission/DART', 'avg_label': 'Prior 12mo Avg.',
        'note': _PR_WHY,
    })

    dpp = (pct_fo[-1] - pct_fo[-2]) * 100
    fo_mom = (opt_d[-1] + fut_d[-1]) / (opt_d[-2] + fut_d[-2]) - 1
    st_mom = stk_d[-1] / stk_d[-2] - 1
    clause = ('as stock DARTs increased more than options and futures' if (dpp < 0 and st_mom > fo_mom)
              else ('as options and futures DARTs outgrew stocks' if dpp > 0 else 'on shifting product mix'))
    ex.append({
        'n': 8, 'kind': 'stacked_dual', 'xlabels': PXL,
        'title': f'Implied product DARTs: the % in the form of F&O {"decreased" if dpp < 0 else "increased"} '
                 f'{abs(dpp):.1f}pp MoM, {clause}',
        # 全页 17 张图里原先唯一一张两个纵轴都没有轴标题的：读者看到 1,849 / 2,364 无从判断
        # 是千笔还是百万笔（左轴与 Exhibit 4 同量纲，右轴是 F&O 占比）。
        'ylab': 'Implied Product DARTs (thousands of trades/day)',
        'ylab2': 'F&O share of implied DARTs (%)',
        'note': 'Product DARTs estimated as monthly volume / average order size / US trading days. '
                '假设：average order size 取的是全部订单的均值；对期货与国际股票同样套用<b>美股</b>交易日数。'
                f'本图各产品推导值合计约为披露 Total Client DARTs 的 {cov_prod.min():.1f}%~{cov_prod.max():.1f}%'
                f'（{PXL[0]}–{PXL[-1]}），故本图口径接近 cleared 而非 total'
                '（下方总表那一列是 Total Client DARTs）。' + _PR_WHY,
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
        'n': 9, 'kind': 'lines_endlabels', 'fmt': 'usd2', 'xlabels': PXL,
        'title': 'Average commissions/trade ' + ' and '.join(parts or ['were stable']) + ' MoM' +
                 (f', and were largely flat for {", ".join(flat)}' if flat else ''),
        'ylab': 'Average commission per trade ($)',
        'series': [
            {'name': 'Stocks Avg CPT', 'color': 'NAVY', 'values': L(stk_cpt)},
            {'name': 'Options Avg CPT', 'color': 'BLUE', 'values': L(opt_cpt)},
            {'name': 'Futures Avg CPT', 'color': 'MBLUE', 'values': L(fut_cpt)},
        ],
        'note': _PR_WHY,
    })
    va10 = margin[-1] / avg12(margin) - 1
    ex.append({
        'n': 10, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': XL, 'xstep': 12,
        'title': f'Customer margin balances {"rose" if yoy(margin) > 0 else "fell"} by {abs(yoy(margin))*100:.0f}% YoY, '
                 f'{abs(va10)*100:.0f}% {"above" if va10 > 0 else "below"} the prior 12 month average',
        'ylab': 'Customer Margin Balances ($bn)',
        'legend': 'Customer Margin Balances', 'values': L(margin), 'avg12': avg12(margin),
        'yoy_txt': pctf(yoy(margin)) + ' y/y·单月', 'mom_txt': pctf(mom(margin)),
        'note': f'公司披露的期末余额，{XL[0]} 起逐月。虚线是<b>最近 12 个月</b>（不含当期）'
                '的均值，不是逐月滚动均值。' + stock_note(ST_MG, '客户融资余额'),
    })
    # Ex11 / Ex13 画的是**单月同比**：按定义要 12 个月历史，序列头 12 期算不出来。
    # 两张都是 gs_line（mrwin.DENSE），前导 null 会被 Catmull-Rom 当 0 插值、逐点标
    # 数值时抛 TypeError，所以左端交给 resolve() 裁到第一个真有读数的月份。
    # 这与「掐头」不同：2016 全年不是被藏起来，是那 12 个月没有去年同月可比
    #（series/ibkr.csv 从 2016-01 起，2015 年的数据本站一格都没有）。
    marg_yoy_pct = marg_yoy * 100
    _w11 = mrwin.resolve('gs_line',
                         [mrwin.Leg('mg', '融资余额单月同比', marg_yoy_pct, 'primary',
                                    '单月同比要去年同月做基数，序列前 12 个月没有')], XL, 0)
    XL11, v11 = _w11.cut(XL), np.array(_w11.cut(marg_yoy_pct), float)
    ex.append({
        'n': 11, 'kind': 'gs_line', 'fmt': 'pct0', 'xlabels': XL11, 'xstep': 12,
        'title': f'Customer margin balances {"increased" if v11[-1] > 0 else "decreased"} by {abs(v11[-1]):.0f}% YoY (单月同比)',
        'ylab': 'YoY customer margin balances change, 单月 (%)', 'values': L(v11),
        'note': '融资余额不是高增速指标，m/m 基本是噪音，故本图画 y/y（相对 Exhibit 10 同一序列的去年同月）。'
                '余额的绝对水平在创新高，但相对客户权益的占比仍在低位，见 Exhibit 16。'
                + stock_note(ST_MG, '客户融资余额') + _w11.why,
    })
    va12 = credits[-1] / avg12(credits) - 1
    ex.append({
        'n': 12, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': XL, 'xstep': 12,
        'title': f'Client cash {"increased" if yoy(credits) > 0 else "decreased"} {abs(yoy(credits))*100:.0f}% YoY, to '
                 f'{abs(va12)*100:.0f}% {"above" if va12 > 0 else "below"} the prior 12 months average…',
        'ylab': 'Total Client Cash ($bn)',
        'note': 'Client cash = total client credit balances, including insured bank deposit sweeps.'
                f'{XL[0]} 起逐月；虚线是<b>最近 12 个月</b>（不含当期）的均值，不是逐月滚动均值。'
                + stock_note(ST_CR, '客户现金（credit balances）'),
        'legend': 'Total Client Cash', 'values': L(credits), 'avg12': avg12(credits),
        'yoy_txt': pctf(yoy(credits)) + ' y/y·单月', 'mom_txt': pctf(mom(credits)),
    })
    cred_yoy_pct = cred_yoy * 100
    _w13 = mrwin.resolve('gs_line',
                         [mrwin.Leg('cr', '客户现金单月同比', cred_yoy_pct, 'primary',
                                    '单月同比要去年同月做基数，序列前 12 个月没有')], XL, 0)
    XL13, v13 = _w13.cut(XL), np.array(_w13.cut(cred_yoy_pct), float)
    ex.append({
        'n': 13, 'kind': 'gs_line', 'fmt': 'pct0', 'xlabels': XL13, 'xstep': 12,
        'title': f'…and was {"up" if v13[-1] > 0 else "down"} ~{abs(v13[-1]):.0f}% YoY (单月同比)',
        'ylab': 'YoY client cash change, 单月 (%)', 'values': L(v13),
        # 「m/m 中位数 1.4%」原来是写死的实测值（在 13 个月窗口上量的）。窗口一变它就
        # 成了假话，所以改成在全历史上现算。
        'note': f'同 Exhibit 11：客户现金的 m/m 绝对值中位数只有 '
                f'{float(np.nanmedian(np.abs(np.diff(cr_all) / cr_all[:-1]))) * 100:.1f}%'
                f'（{XL[1]}–{XL[-1]} 全区间实测），画 y/y 才有信息量。'
                + stock_note(ST_CR, '客户现金（credit balances）') + _w13.why,
    })

    # ── 长历史（Exhibit 14-17）：2016-01 起，x 轴每 12 个月一个标签 ──
    # 这三张 lines 图一律显式 zero_base：不给它时引擎走 y0 = min − 极差×5%，那是一次**没有
    # 任何标注的隐性截轴**，而它们的标题偏偏都在讲倍数／降幅（Ex15「14.0x」、Ex16
    # 「不到一半」）——截过的轴会把这些幅度凭空放大，图与文字互相打架。
    # Ex14 的数据本来就贴近 0，给上只是把「从 0 起」这件事写实。
    # 三张都给 end_label：末点读数正是各自标题引用的那个数，且末点都落在序列的极值端，
    # 标签周围是空的。
    #
    # ⚠ 原 Exhibit 14（人均年化 cleared DART 全历史）已经删掉，因为 Exhibit 2-13 的窗口
    #   拉到全历史之后，它与 Exhibit 5 变成同一列 CSV、同一段月份的**同一张图**。
    #   合并方式见 Exhibit 5 处的注释（Ex5 采用了它的 lines + zero_base 画法与年均文案）。
    #   其后各图顺次前移一号：15→14、16→15、17→16、18→17。
    #
    # 这四张原来只写 `x: 'long'` 而不写 `xlabels`，于是 `mrwin.layout_all()` 看不见它们的
    # 轴长（那边判的是 `len(e['xlabels'])`），三张 127 点折线一直留在半栏里（每格 3.9px）。
    # 本轮 Exhibit 5 变成同规格的 127 点 lines 图并被判成通栏，不补上就会出现「同一页、
    # 同样长的两张折线，一张通栏一张半栏」。所以显式给 xlabels，交给同一个判据裁。
    ex.append({
        'n': 14, 'kind': 'lines', 'x': 'long', 'xlabels': XL, 'xstep': 12, 'fmt': 'f0c',
        'zero_base': True, 'end_label': True,
        'title': f'Trailing-12-month net new accounts at {roll12[-1]:,.0f}k, vs. '
                 f'{roll12[ALL.index("2021-12")]:,.0f}k in Dec-21 and {roll12[ALL.index("2018-12")]:,.0f}k in Dec-18',
        # y 轴标题必须放得进绘图区高度：charts.js 把它 rotate(-90) 居中钉在 ph 的中点，
        # **没有任何回缩**（`fitVertical()` 只服务断点标签），排不下就两头伸出 <svg>。
        # 而 .plot svg 是 overflow:visible，伸出去的那截会原样印在卡片上 —— 上端正好
        # 落在图例那一行（实测 1280px 下越顶 20.8px、压 legend 172px²，768px 下 32px²）。
        # 放得下的判据是「文字长度 ≤ 2×cy」，cy = M.t + ph/2 —— 顶边距 M.t 只有 23.8px，
        # 所以**上端先撑破**，下端还空着 75px 也没用。这张图通栏时 ph=224.2、cy=135.9，
        # 预算 271.8px；原来那句 48 字符的轴标题实测 313.4px，上端于是伸出 20.8px。
        # 改法是把与 legend 逐字重复的那半句压成 legend 自己的写法（T12M），只保留轴标题
        # 真正该承担的东西：量纲。改后 34 字符实测 236.9px，上端留 17.5px、下端 75.2px。
        # （实测＝1280px 视口下量 text 的 getBoundingClientRect，含 txt() 的 4.08px 描边。）
        'ylab': 'Net new accounts, T12M (thousands)',
        'note': '12 个月滚动和，回答「这轮开户潮相对历史有多大」。已按公司 Notes 还原真实账户增长'
                f'（{nn_adj_txt}），前 11 个月不足一年故留空。',
        'series': [{'name': 'Net new accounts, T12M', 'color': 'NAVY', 'values': LN(roll12)}],
    })
    ex.append({
        'n': 15, 'kind': 'lines', 'x': 'long', 'xlabels': XL, 'xstep': 12, 'fmt': 'f0c',
        'zero_base': True, 'end_label': True,
        'title': f'Client equity at ${eq_all[-1]:,.0f}bn, {eq_all[-1] / eq_all[0]:.1f}x the '
                 f'${eq_all[0]:,.0f}bn of {XL_LONG[0]}',
        'ylab': 'Client Equity ($bn)',
        'note': '公司披露值（期末口径，不含非客户余额）。它是 Exhibit 10 / 12 两条余额的分母，也是 NII 的规模基数，'
                '此前站上一张图都没有。',
        'series': [{'name': 'Client Equity', 'color': 'NAVY', 'values': LN(eq_all)}],
    })
    ex.append({
        'n': 16, 'kind': 'lines', 'x': 'long', 'xlabels': XL, 'xstep': 12, 'fmt': 'pct1',
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
        'n': 17, 'kind': 'bar_line_dual', 'x': 'long', 'xlabels': XL, 'xstep': 12,
        'full': True, 'height': 300,
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
                f'（等价于 cleared/total 的补数——bar_line_dual 的右轴强制含 0，'
                f'直接画 {_cov_lo:.0f}%~{_cov_hi:.0f}% 的比值会被压成一条看不出变化的平线）。'
                'cleared/total 的逐年均值：'
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

    # 期货费用比例的脚注句：现算，且**必须点名是哪一期的读数**。缓存里每一期都不一样，
    # 只印一个光秃秃的百分数会被当成公司的固定口径（页尾从前那个写死的 56% 就是这样读的）。
    # 解析不到就一个数字都不印 —— 宁可少一句，也不能拿别的月份的读数顶上。
    _ff = sorted(v for v in FUT_FEE.values() if v is not None)
    if FUT_FEE.get(target) is not None:
        fut_fee_txt = (f'公司在 {month_name} 新闻稿里估计交易所／清算／监管费用约占期货佣金的 '
                       f'<strong>{FUT_FEE[target]:g}%</strong>'
                       + (f'（该比例<strong>逐月披露、每月都在动</strong>：本地缓存的 '
                          f'{PXL[0]}–{PXL[-1]} 共 {len(_ff)} 期落在 {_ff[0]:g}%–{_ff[-1]:g}% 之间，'
                          f'不是固定口径）' if len(_ff) >= 2 and _ff[0] != _ff[-1] else '')
                       + '。')
    else:
        fut_fee_txt = ('公司在月度新闻稿里逐月估计交易所／清算／监管费用占期货佣金的比例；'
                       f'{month_name} 那期没解析到这句话，故此处不印数字。')
    summary = {
        'title': f'{month_name} 汇总 —— 本月 vs 上月／去年同月，及近 3 年分位',
        # ⚠ 「去年同月」原来写的是 XL[0] —— 在 13 格窗口里它恰好就是去年同月，窗口拉到
        #   127 格之后它变成 1/16，而表里第三列取的是 arr[ti-12]。表头与表身对不上、
        #   而且不报错，是本轮最容易漏的一处。改成按尾部定位。
        'heads': ['本月 ' + XL[-1], '上月 ' + XL[-2], '去年同月 ' + XL[-1 - LAG], 'm/m',
                  'y/y 单月', '3Y %ile'],
        'sep': 3,
        'rows': srows,
        'note': '3Y %ile = 当月读数在最近 36 个月里高于多少个百分比的观测（分位越高越极端），'
                '判据与全站共用 <code>build/pctile.py</code>：把这一行的分位在近 24 个月里逐月回放，'
                '若 ≥70% 的月份都钉在区间端点（100 或 0），说明这一列对该行没有区分度，整行留空。'
                + (f'本表留空的是：{"；".join(blank_why)}。' if blank_why else '')
                + f'净新增账户按公司 Notes 还原（{nn_adj_txt}）。'
                f'CPT 与 F&O 占比来自月度新闻稿，本地只缓存 {len(PWIN)} 个月'
                f'（{PXL[0]}–{PXL[-1]}），做不出 3Y 分位，故不列。'
                '<br><b>本表的 y/y 列是「单月口径」= 本月 ÷ 去年同月 − 1，与 Exhibit 2/3/4/5 '
                '的滚动口径不同。</b>不改它是刻意的：这一列恒等于表内算术（第一列 ÷ 第三列），'
                '读者可以直接验算；换成滚动口径之后这一步会得出另一个数，'
                '表内自相矛盾比口径混用更糟。' + _CAL_TXT,
    }

    # ── 13 个月核对附表（官方原始单位，便于与披露逐条核对）──
    # 第三个字段是小数位；给**可调用对象**表示这一列自带格式化（交易日的半天不能取整，
    # 见 half_day 的 docstring）。
    TCOLS = [('交易日', 'trading_days', half_day), ('账户总数 千户', 'accounts', 1),
             ('净新增 千户', 'net_new', 1), ('Total Client DARTs 千笔/日（含未清算）', 'darts', 0),
             ('人均年化 DART', 'ann_dart_acct', 0), ('期权 千张', 'opt_contracts', 0),
             ('期货 千张', 'fut_contracts', 0), ('股数 千股', 'stk_shares', 0),
             ('客户权益 $bn', 'equity', 1), ('客户现金 $bn', 'credits', 1),
             ('融资余额 $bn', 'margin', 1)]
    # 核对表**刻意**只印最近 13 个月：它不是时序图，是给人拿着官方 PDF 逐格对数的表。
    # 127 行会把页面撑成一堵墙，而对数这件事只对最近几期有意义（历史行一旦对过就不会变）。
    TWIN, TXL = WIN[-13:], XL[-13:]
    trows = []
    for i, w in enumerate(TWIN):
        r = {'xl': TXL[i]}
        for _, key, dec in TCOLS:
            v = series[w][key]
            r[key] = None if v is None else (dec(v) if callable(dec) else comma(v, dec))
        trows.append(r)
    # 图号自查：exhibit 编号必须是 2..N 的连号，核对表接在最后一张之后。编号写死过一次
    # 代价就够大了 —— 全站审计发现别的页把核对表写死成 'n': 15，后来在末尾追加了两张图，
    # 页面就出现「…16、17、15」而没有任何东西报错。这里改成现算 + 硬拦。
    _ens = [e['n'] for e in ex]
    if _ens != list(range(2, 2 + len(_ens))):
        raise SystemExit(f'Exhibit 编号不连续: {_ens}')

    # ── 排版裁决：通栏 / x 标签抽稀，一律由 build/mrwin.py 按 charts.js 的量边距算式
    #    实测决定，**本页不自己判、也不改 mrwin**。窗口从 13 拉到 127 之后这一步是必需的：
    #    127 根柱塞进半栏卡片每根不到 3px（CONTRACT 的 `full` 字段那一行就是这么写的）。
    #    已经显式写了 xstep 的图（长历史一律 12，好让标签落在每年同一个月）它不会覆盖。
    mrwin.layout_all(ex)
    table = {
        'n': _ens[-1] + 1, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）',
        'idx': '月份', 'cols': [[lab, key] for lab, key, _ in TCOLS], 'rows': trows,
    }

    # 抬头一律 YoY + MoM 并列。原来只写 YoY —— 改这行的那个月几条 YoY 恰好全是正的，
    # 抬头看上去一片大好，而同月净新增与 cleared DARTs 的 MoM 都在两位数下跌，
    # 要翻到 Exhibit 1 汇总表才看得到。抬头是多数人唯一会读的一行，不能只挑好消息。
    # （那个月的具体读数不抄进注释：每个月都会变，抄了下个月就是假话；而这条规矩不变。）
    # 同时补上人均年化 DART：它是这页唯一结构性下行的指标（Exhibit 5 讲的就是它），
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
        'subtitle': (f'{month_name} update — Exhibits 2–17, recreated in Goldman Sachs GIR exhibit '
                     f'format from IBKR company data · 主窗口 {XL[0]} – {XL[-1]}'
                     f'（{len(XL)} 个月全历史）· '
                     f'Exhibits 6–9 只覆盖月度新闻稿区间 {PXL[0]} – {PXL[-1]}'),
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
            f'三段合计约为披露 Total Client DARTs 的 {cov_prod.mean():.0f}%'
            f'（{PXL[0]}–{PXL[-1]} 均值），即本图口径接近 cleared 而非 total。',
            '<strong>佣金口径</strong>：新闻稿「Key products」表两列分别是 <em>Average Order Size</em>'
            '（平均订单规模，股／张）与 <em>Average Commission per Cleared Commissionable Order</em>'
            '（单笔清算订单平均佣金，$，含交易所、清算与监管费用）。<strong>不是每股／每张单价。</strong>',
            '<strong>期货</strong>含期货期权；' + fut_fee_txt,
            '<strong>账户口径调整</strong>：历史指标 PDF 的 Notes 段披露过三次一次性调整'
            '（2025-03 escheat 13.3k、2025-09 一家 introducing broker 撤出 38.8k、'
            '2024-11 Total Accounts 下调 9.1k）。Exhibit 2 画表内披露值，'
            + (f'落在窗口内的净新增调整月（{"、".join(mk2)}）以<strong>斜纹柱</strong>标出'
               f'（悬停有说明）；原先另在 x 轴标签上挂 †，窗口拉到 {len(XL)} 个月后标签要抽稀、'
               f'† 会静默消失，故取消；'
               if mk2 else '本次窗口内没有净新增调整月，故图上没有斜纹柱；')
            + 'Exhibit 3 与 Exhibit 14 的分子分母一律用公司给的真实增长。解析器每月重新抓这段 Notes，'
            '出现未登记的调整会直接让构建失败。',

            '<strong>与本站其余各页的一处版式差异</strong>：本页 gs_bar 图（Exhibit 2 / 4 / 6 / 10 / 12）'
            '上的那条虚线画的是<strong>当期之前 12 个月的均值</strong>——'
            '窗口拉到全历史之后它仍然只是右端那一格的参照水平，'
            '<strong>不是逐月滚动均值</strong>，一条横线跨过全图时这一点必须写明；'
            '而从 Goldman Sachs deck 移植的各页'
            '（HKEX / CME / CBOE / MSCI / SPGI 等）在同一位置画的是<strong>次轴 y/y 折线</strong>。'
            '本页与 /cost/ 来自两个已上线并逐张验收过的独立站，均线是原站既有版式，故保留不动；'
            'y/y 在本页另有出处——图左上角气泡，以及 Exhibit 3 / 11 / 13 三张专门的 y/y 图，数字同源。',

            # ── 同比口径：本页有两种，逐处点名 ──
            # 「点名」不是客套：读者在同一页上看到两个都叫 YoY 的净新增账户读数，
            # 没人告诉他分母不同，他只会以为哪里算错了。
            '<b>⚠ 同比口径：本页有两种，逐处点名。</b>'
            '(1) <b>12 个月滚动合计同比</b>（本年 12 个月合计 ÷ 上年同 12 个月合计 − 1）—— '
            'Exhibit 3（净新增账户，整张图）、Exhibit 2 / 4 的 YoY 气泡与 Exhibit 2 / 4 / 5 的标题。'
            '<b>流量与流量率一律用这个口径。</b>'
            + (f'实测（对齐到两种口径都算得出的同一批月份，全历史 {ST_NN_ALL["n"]} 个月）：'
               f'净新增账户的单月同比标准差 {ST_NN_ALL["sd_m"]:,.1f}pp 是滚动口径 '
               f'{ST_NN_ALL["sd_r"]:,.1f}pp 的 {ST_NN_ALL["sd_m"] / ST_NN_ALL["sd_r"]:,.2f} 倍，'
               f'相邻月最大跳变 {ST_NN_ALL["jump_m"]:,.0f}pp vs {ST_NN_ALL["jump_r"]:,.0f}pp，'
               f'{len(ST_NN_ALL["flips"])} 个月两种口径符号相反。' if ST_NN_ALL else '')
            + f'<b>唯一的例外是 Exhibit 6</b>（隐含佣金收入/日）：它的乘数 CPT 只存在于月度'
            f'新闻稿里、本地只缓存 {len(PWIN)} 个月（{PXL[0]}–{PXL[-1]}），'
            f'凑不出滚动同比要的 24 个月历史，'
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
            + ((f'客户现金换成 12 个月均值同比，标准差从 {ST_CR["sd_m"]:,.1f}pp '
                + ('涨到' if ST_CR["sd_r"] > ST_CR["sd_m"] else '降到')
                + f' {ST_CR["sd_r"]:,.1f}pp'
                + ('（<b>反而更吵</b>）'
                   if ST_CR["sd_r"] > ST_CR["sd_m"] else
                   '（<b>确实更平滑</b>，但它按构造滞后约半年，回答的是「去年一整年的平均'
                   '水平」而不是「现在相对去年此刻」—— 本页要的是后者）')
                + f'，两种口径 {len(ST_CR["flips"])} 个月符号相反。') if ST_CR else '')
            + _CAL_TXT
            + f'<b>Exhibit 14（T12M 净新增账户）本来就是滚动口径的水平值</b>'
            f'（当期 {roll12[-1]:,.0f}k），Exhibit 3 现在画的正是它的同比 —— '
            '本轮之前这两张一张滚动一张单月，同一页里对同一件事给两个答案。',

            '<strong>纵轴</strong>：Exhibit 5 与 14-16 四张 <code>lines</code> 图一律'
            '<strong>从 0 起</strong>。引擎默认的下界是「最小值 − 极差 5%」，那是一次没有标注的'
            f'隐性截轴，会把这几张标题里引用的倍数与降幅（{_y5g:.0f}% below／'
            f'{eq_all[-1] / eq_all[0]:.1f}x／不到一半）在视觉上凭空放大。'
            '本页没有任何一张图设了截轴（ycap／yfloor）——各图序列量纲一致、没有把其余序列压平的离群尖峰。',
            '<strong>窗口</strong>（2026-08 改）：<b>本页所有取自 series/ibkr.csv 的图现在都从 '
            f'{XL[0]} 起画</b>（{len(XL)} 个月逐月连续）。'
            '此前 Exhibit 2-13 是写死的「最近 13 个月」，而 CSV 从上线第一天起就有全部 '
            f'{len(ALL)} 个月 —— 那 {len(ALL) - 13} 个月是画的时候扔掉的，不是没有。'
            '几张图的左端比 {0} 晚，原因逐张写在各自图注里，一律是「这一期算不出来」而不是'
            '「截掉不看」：Exhibit 3（12 个月滚动同比要 24 个月历史）、Exhibit 11 / 13'
            '（单月同比要去年同月做基数，本站没有 2015 年数据）、Exhibit 4'
            '（推导式要月初账户数，首月没有上月）。裁决与措辞都走全站共用的 '
            '<code>build/mrwin.py</code>，不在本页各写一份。'.format(XL[0])
            + f'<b>Exhibit 6-9 例外</b>：CPT 与平均订单规模只在月度新闻稿里，'
            f'本地缓存只回到 {PXL[0]}，故只有 {len(PWIN)} 个月 —— 这是来源限制，不是窗口选择。'
            f'Exhibit 14-17 本来就是 {ALL[0]} 起全历史；Exhibit 1 的 3Y %ile 取近 36 个月；'
            '文末核对表刻意保持 13 行（它是对数用的表，不是图）。'
            '窗口一律从数据最新月倒推，不依赖构建当天的日期。',
            'Exhibits 14-17 of the original Goldman Sachs note (IBKR app downloads and MAU) rely on '
            'proprietary Sensor Tower data and cannot be updated from public company disclosures; '
            '本站的 Exhibit 14-17 是另加的长历史图，与原 note 的编号无对应关系。',
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

    print(f'目标月 {target} | 主窗口 {WIN[0]} → {WIN[-1]}（{len(WIN)} 个月全历史）| '
          f'新闻稿窗口 {PWIN[0]} → {PWIN[-1]}（{len(PWIN)} 个月）'
          + (f' | 缓存里不连续、未采用的新闻稿：{_pr_orphan}' if _pr_orphan else ''))
    print('各图左端：' + '、'.join(
        f'Ex{e["n"]} {(e.get("xlabels") or XL_LONG)[0]}×{len(e.get("xlabels") or XL_LONG)}'
        for e in ex))
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）+ '
          f'Exhibit {table["n"]} 核对表')
    print(f'口径脚注 {len(notes)} 条，命中月份 {flagged}')
    print(f'写出 data/ibkr.js ({os.path.getsize(path)/1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
