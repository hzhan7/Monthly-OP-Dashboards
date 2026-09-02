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
  · `series/ibkr_pr.csv` —— 月度新闻稿里的佣金口径（CPT、平均订单规模、CPT 的口径名、
    期货费用占比），2016-02 起逐月，由 fetch/ibkr.py 落库、由
    `build/basefill/ibkr_pr_2016.py` 一次性回填历史。
    **2026-09 之前这几个数是本模块每次构建现场解析 `cache/ibkr/pr_*.pdf` 得到的**，
    而 cache 是 gitignore 的 —— 换一台机器或清一次缓存，佣金那几张图就从十年缩回
    一两个月，一声不响。现在本模块**一个 PDF 数字都不解析**，只查表。
    （搬家理由与 `source_dates.py` docstring 写的是同一条：series/ 是唯一真值，
    cache/ 只是过程物。解析仍只在 `fetch/ibkr_source.py` 定义一处。）
  · `cache/ibkr/hist_latest.pdf` —— 只取 Notes 段的**文字**
    （账户口径调整的原文），用作护栏与图注；一个数字都不从这里取。

═══ 口径 ═══
  历史指标表首个区块 "(in Thousands, except Trading Days)" —— 账户/DARTs/合约/股数以千计；
  第二区块 "(in Billions)" —— 客户权益/现金/融资余额。
  新闻稿 Key products 两列 = Average Order Size（股/张）与 Average Commission per Cleared
  Commissionable Order（$/笔），**不是每股/每张单价**。

  ⚠ CPT 的口径在 **2019-11** 改过一次：此前是 per cleared **client** order，此后是
  per cleared **Commissionable** Order —— IBKR LITE 上线后免佣订单退出分母。
  口径名逐月存在 `series/ibkr_pr.csv` 的 `cpt_basis` 列里，**断点由数据现算，
  不在本文件写死日期**；跨这条线比 CPT 高低是跨口径比较，四张佣金图上都画了断点。

═══ 同比口径（2026-09 改：全页只剩一种）═══
  本页从前有两种同比并存（流量走 12 个月滚动合计、存量走点对点），页尾要拿一整段
  去逐处点名，还配了一套「登记 KIND → 从图上反读标记 → 对撞停机」的装置。
  **现在全页一律单月同比**（本月 ÷ 去年同月 − 1），页面所有者定的：
    · 与 Exhibit 1 汇总表的 y/y 列同口径 —— 读者拿第一列除第三列就能验算；
    · 五张柱图各自把同比画成次轴折线，柱是**单月**水平值，线也是**单月**同比。
      其中四张的柱与线取自同一列 —— 线上任一点就是这根柱相对 12 根柱之前的涨幅，
      读者数得出来；**Exhibit 2 是唯一的例外**（柱是表内披露的净新增账户，线走公司
      Notes 还原后的真实增长）。「例外只有这一张」不是一句写死的断言：例外名单在建图
      现场登记（`SPLIT_SRC`），页尾从它现算，构建期再拿 payload 复算「柱除柱」与线
      逐点对，实测出来的例外集与登记簿对不上就停机。
    · 页上再也没有「12 个月滚动」或「近 12 个月均值」的虚线／气泡／折线。
  这与 CONTRACT §6 的全站规矩一致，不是本页的偏离：§6.1 第 1 条把流量定为单月同比、
  第 2 条把存量定为点对点同比，两者在本页都落到「本月 ÷ 去年同月 − 1」这一个式子上。
  每一张画同比的图，标题或次轴标题里仍带「单月」二字 —— `tools/check_yoy_caliber.py`
  的 R4 认的就是这个（§6.6：单月同比没写进标题判 🟡）。
  **画流量同比的那三张（Exhibit 2 / 3 / 6）各自在图注里印出单月口径的代价**，
  用那条序列自己实测（§6.1 第 3 条要的三样：逐月标准差、相邻月最大跳变带月份、
  与 12 个月滚动口径符号相反的月份数；对照那一侧只以数字出现，页上不画）——
  「逐图」是字面意思，页尾那条口径说明是补充，不顶替它。存量的两张（Exhibit 10 / 11）
  按第 2 条走点对点，不欠这笔账。图号一律现算，上面这几个号只是本轮的实测结果。

═══ 窗口 ═══
  全站规矩：**数据只要存在就必须从 2016-01 画起**。`series/ibkr.csv` 从 2016-01 起
  逐月连续，`series/ibkr_pr.csv` 从 2016-02 起（2016-01 那期新闻稿官方没发）。

  主窗口          = `series/ibkr.csv` 的全部月份（2016-01 起，逐月连续）。
  新闻稿四张图    = 主窗口去掉第一格（2016-02 起），因为那两列数据从 2016-02 才有。
                    **2021-10 是序列中间的一个洞**（官方没发那期，见
                    `ibkr_source.PR_ABSENT`）——一律画成缺口，绝不补 0、绝不插值、
                    绝不拿邻月顶上。所以这四张图不能用 `mrwin.DENSE` 里的图型
                    （那几种对中段 null 会插值或抛错，`verify_pages.py` 也直接判 ERROR）。
  派生序列算不出的头几期由 `build/mrwin.py::resolve()` 裁左端（单月同比要 12 个月、
  implied cleared DARTs 要上月账户数）。**裁的是「算不出来的那几期」，不是「掐头到
  好看的地方」**：左端停在哪一期与为什么，登记在 LATE_WHY 里并回填进各自图注。
  Exhibit 1 的 3Y %ile 取近 36 个月；文末核对表固定最近 13 个月（那是核对表不是图）。

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

# series/ibkr_pr.csv 的列（表头由 build/basefill/ibkr_pr_2016.py::HEAD 定义，这里只列
# 本模块要读的那几列；对不上会在 read_pr_series() 里直接失败，不静默补 None）。
PR_COLS = ['cpt_all_usd', 'cpt_basis',
           'order_size_stocks_shares', 'cpt_stocks_usd',
           'order_size_options_contracts', 'cpt_options_usd',
           'order_size_futures_contracts', 'cpt_futures_usd', 'fut_fee_pct']

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


def read_pr_series():
    """series/ibkr_pr.csv → {'YYYY-MM': {列: float|str}}。

    **本模块不再解析任何新闻稿 PDF**（2026-09 起）：数值由 fetch/ibkr.py 摄入时落库、
    由 build/basefill/ibkr_pr_2016.py 一次性回填历史。缺行 = 官方那期没发（登记在
    `ibkr_source.PR_ABSENT`），由调用方画成缺口 —— 这里不补、不猜、不抛。
    """
    path = os.path.join(SERIES, 'ibkr_pr.csv')
    if not os.path.exists(path):
        raise SystemExit(f'找不到 {path}（先跑 python3 build/basefill/ibkr_pr_2016.py）')
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit('series/ibkr_pr.csv 是空的')
    missing = [c for c in PR_COLS if c not in rows[0]]
    if missing:
        raise SystemExit(f'series/ibkr_pr.csv 缺列: {missing}')
    out = {}
    for r in rows:
        key = r['month'].strip()
        if not re.fullmatch(r'20\d{2}-\d{2}', key):
            raise SystemExit(f'series/ibkr_pr.csv 月份格式异常: {r["month"]!r}')
        out[key] = {c: (r[c] if c == 'cpt_basis' else
                        (float(r[c]) if r[c] not in ('', None) else np.nan))
                    for c in PR_COLS}
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
    除这一种输入外输出与从前逐字符相同。

    再加一条（2026-09）：**算不出来时返回 'n/a'，不返回 'nan%'**。新闻稿那几张图现在
    有缺月（官方没发那期），去年同月或上月落在缺口上时同比/环比就是算不出来 ——
    `f'{float("nan"):.0f}'` 会产出字面 'nan'，一路写进标题；payload_guard 的展示串判据
    只认带单位后缀的 'nan'，'nan%' 不在它的 _UNITS 里，于是能一路发上线。"""
    if x is None or not np.isfinite(x):
        return 'n/a'
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


# ────────────────── 同比：全页只有一种口径（单月）──────────────────
# 2026-09 之前本页并存两种口径：流量走 12 个月滚动合计、存量走点对点，页尾拿一整段
# 逐处点名，并配了一套「建图时登记 KIND → 从图上印出来的标记反读 → 对撞不上就停机」
# 的装置（`_cal` / `_rule_break` / `roll_note` / `stock_note` / `cal_stats`）。
# 页面所有者 2026-09 定下**全站统一单月同比**（CONTRACT §6），那一整套随之删除 ——
# 留着它只会守一条已经不存在的规则，而「守着一条假规则的护栏」比没有护栏更贵。
#
# 单月同比的代价没有变，只是全站一起承担它：分母是**去年那一个月**，流量的月度分布
# 带季节性与一次性事件（escheat、introducing broker 撤出、行情月），分母越小、同一笔
# 绝对变化被放大得越狠。所以图上一律把它标成「单月」，且柱与线同源（线上任一点 =
# 这根柱相对 12 根柱之前的涨幅），读者能自己数出基数效应来自哪一格。
# 2020-03…2021-02 那一段就是活例：疫情开户潮把净新增账户的单月同比顶到 +690%，
# Exhibit 2 的右轴因此截在 +200%（截轴不删点，超界的点画空心红圈 + 真值）。
def _S(v, keys):
    """numpy 数组 + 月份键 → pandas Series，好喂给共享模块 build/yoy.py。

    ALL 是逐月连续的（main() 开头已经硬校验过），所以 shift 按位置算就等于按月份算 ——
    缺月会让这个等式失效，那正是那道校验存在的原因。
    """
    return pd.Series(np.asarray(v, float), index=list(keys))


def mono_yoy_arr(v, keys):
    """点对点（单月）同比（**小数**，与本页 pctf() 的约定一致）。本页唯一的同比实现。"""
    return yoy.mom_yoy(_S(v, keys), yoy.FLOW).values / 100.0


def mom_cost_zh(v, keys, win, per_day=False):
    """单月同比的**代价**，拿这条序列自己实测 —— 只报数，不替口径辩护。

    CONTRACT §6.1 第 3 条：**每一张**画流量同比的图都要印出单月口径的代价，
    且「逐图」是字面意思 —— 页尾那段读者在看某一条金线时够不到，而这段话的全部
    用处就是让人读那条线的时候知道它有多毛刺。本页从前只有页尾一句定性的
    「分母是去年那一个月……2020-03 至 2021-02 是活例」，那句留着（它讲的是**怎么看
    这一页**），但顶不了这一段。

    措辞照 `build/single.py` 的 `mom_cost_zh()`（契约点名的两个底座之一，只读不改），
    要报的三样一样不少：逐月标准差、相邻月最大跳变（**带月份**）、两种口径符号相反
    的月份数。统计量全部走 `yoy.caliber_diff()` —— 它第一步就把两种口径都有值的月份
    取交集对齐，不对齐会把「滚动那条少 12 个月历史」的样本效应读成口径效应
    （CONTRACT §6.4）。对照的那一侧（12 个月滚动合计）**只在这段文字里以数字出现，
    页上一条线都不画**。

    `win` 传**这张图实际画出来的窗口**（月份键的列表）：诊断只该量读者在图上看得到
    的那一段，全历史算出来的数报的是一张不存在的图。

    `per_day=True` 用于**日均列**（本页的 cleared DARTs 与 commission revenue/day 都是
    「每日」口径）：对照那一侧是把 12 个月的日均值等权相加，各月交易日数不同，所以它
    是真滚动口径的一个**近似** —— 这句话必须印出来，不能让读者以为那是精确值。
    （§6.4「日均序列不要乘回交易日」管的是**图上画的**那条线：单月同比里日历效应
    已经被日均口径除掉了，乘回去等于把它请回来。这里只是为了量差异才相加，不上图。）
    底座 `build/single.py` 的 `mom_cost_zh()` 对同一件事印的是同一句话。

    ⚠️ 范围限定在**流量**（第 3 条自己写明的）：Exhibit 10 / 11 的融资余额与客户现金
    是存量，走第 2 条的点对点，它们的对照量（12 个月滚动**均值**同比）回答的是另一个
    问题，不是「换口径的代价」，所以不欠这笔账，也不要为了格式整齐硬补。
    ⚠️ 不许写「看着更灵敏」，也不许写「滚动口径更好但我们没用」—— 前者是替口径辩护，
    后者是替页面上不存在的东西背书（§6.1 第 3 条的两条禁令）。
    """
    d = yoy.caliber_diff(_S(v, keys), yoy.FLOW, win=list(win))
    head = ('<b>单月口径的代价用本序列自己实测</b>'
            '（CONTRACT §6.1 第 3 条要求每张画流量同比的图逐图印，页尾那段不顶数）：')
    if d['n'] < yoy.MIN_DIAG_MONTHS:
        # 「小于」写成中文而不是裸的 `<`：图注当作 HTML 塞进页面，一个裸 `<` 会让
        # 按标签剥文本的工具（tools/check_yoy_caliber.py 的 `_txt`）把后面一整段吃掉。
        return (head + f'本图窗口内两种口径都算得出的月份只有 {d["n"]} 个'
                       f'（少于 {yoy.MIN_DIAG_MONTHS} 个），差异<b>量不出来</b>，'
                       f'此处不报数 —— 这本身也是一句提醒：这条线的可比月很少，'
                       f'斜率不要外推。')
    j = d['maxjump_mom']
    body = (f'本图窗口内 {d["n"]} 个两种口径都算得出的月份（{d["months"][0]} – '
            f'{d["months"][-1]}；对照的 12 个月滚动合计口径<b>只在这段文字里以数字'
            f'出现，页上一条线都不画</b>'
            + ('，且本列是<b>日均</b>口径，那一侧按 12 个月等权相加算，'
               '各月交易日数不同、所以是个近似' if per_day else '')
            + f'）：单月同比的逐月标准差 {d["std_mom"]:.1f}pp、'
            f'滚动 {d["std_ttm"]:.1f}pp（放大 {d["std_ratio"]:.1f} 倍）；'
            f'相邻月最大跳变 {j[0]:.0f}pp（{j[1]} → {j[2]}）'
            + (f' vs 滚动 {d["maxjump_ttm"][0]:.0f}pp' if d['maxjump_ttm'] else '')
            + f'；两者<b>符号相反</b>的月份 {d["opposite_n"]} 个'
              f'（占 {d["opposite_share"] * 100:.0f}%）')
    if d['worst_gap']:
        g = d['worst_gap']
        body += f'，差得最远的是 {g[0]}（单月 {g[1]:+.1f}% vs 滚动 {g[2]:+.1f}%）'
    return (head + body + '。⇒ <b>这条线要连着水平值一起读</b>：去年同月是低基数时'
                          '它会被放大，单看它挑月份能把结论说成两个方向。')


def compose_brief(ALL, acc, eq, cr, mg, ann, nn, dart, td, opt, fut, stk):
    """IBKR 页顶部的 ~300 字数据总结（payload 的 `brief` 字段）。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R3 日历护栏 /
    R4 单位恒等 / R5 标注 / R6 有效位），那边只算事实，句子在这里拼 ——
    措辞是口径的一部分，属于各家自己。

    每个数字都是当场从序列算出来的，**没有一处硬编码**：排名、「几个月最低」、
    「峰值停在哪个月」下月重跑都会自己变。

    ═══ IBKR 独有，别家不能照抄 ═══
      · `ann_dart_acct` 与 `darts` **分子不同源**：前者只数 IBKR 自清算的订单
        （"cleared" 修饰的是 DARTs，不是账户 —— 两者的分母都是全部客户账户，
        10-K 把 Total Accounts 与 cleared customer accounts 当同一个数印）；
        后者含 execution-only 客户的单。所以文中保留「cleared」一词，
        且全篇不做 darts ÷ accounts 这类跨口径除法。
        ⚠ 这里从前写的是「分母是 cleared 账户」，2026-09 查证为**错**（见 Total client
        DARTs 那张双轴图的图注）；禁令本身保留，依据换成分子。
      · `net_new` 的 2025-03 / 2025-09 一次性调整（见 ADJ）是 IBKR 专有，
        排名一律按**还原口径**算，句子里必须写「（还原口径）」。
      · R3 日历护栏在这里成立，是因为 opt/fut/stk 三列是**当月合计**。
        月末时点值（融资余额、客户现金）没有日历效应，硬套会造出一个假修正。

    ═══ 同比口径 ═══
      全页只有单月同比（见模块 docstring 的「同比口径」一段），所以这里的每个同比
      读数与汇总表、与各图次轴那条线**都是同一个数**，读者拿哪个去核都对得上。
      2026-09 之前本页并存两种口径，这一段曾经要把「单月 X% / 滚动 Y%」并排印出来
      并各带标签；那套措辞连同它引用的 Exhibit 3 一并删除了。
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
    #    同比只有一个读数（全页单月口径），与页上那条次轴折线、与汇总表 y/y 列同源。
    be = B.base_effect(nn, i)
    trend = f'同比{B.pct(be["yy"])}'
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
          f'为{n}个月{"最低" if pu["is_min"] else "低位"}，同比{B.pct(pu["yoy"])}，'
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

    # ── 月度新闻稿口径：查表，不解析 PDF ─────────────────────────────────────
    # 2026-09 之前这里是「扫 cache/ 里紧贴最新月的一段连续 PDF，逐份现场解析」。
    # 那让 Exhibit 6-9 的长度取决于**本机缓存**而不是数据本身：cache/ 是 gitignore 的，
    # 换机器就只剩一个月，而且中间任何一个月缺一份稿子，回溯就当场停住、把它左边的
    # 十年全部丢掉（2021-10 官方就没发过，一个洞卡掉 60 多个月）。
    # 现在数值入库在 series/ibkr_pr.csv（tracked），窗口 = 台账里第一个月到目标月的
    # **整段连续月份轴**，中间没有台账行的月份画成缺口（null），不压缩、不插值。
    PR = read_pr_series()
    if target not in PR:
        raise SystemExit(f'series/ibkr_pr.csv 缺目标月 {target} —— 先跑 fetch/ibkr.py '
                         f'（若官方那期确实没发，把它登记进 ibkr_source.PR_ABSENT）')
    _p0 = ALL.index(min(PR))
    PWIN, PXL = ALL[_p0:], XL_LONG[_p0:]
    PR_GAPS = [m for m in PWIN if m not in PR]          # 官方没发那期 → 图上一个缺口
    _PW = lambda col: np.array([PR[m][col] if m in PR else np.nan for m in PWIN], float)
    # 页尾脚注要的「交易所／清算／监管费用占期货佣金」比例：**公司逐月披露、不是固定口径**，
    # 一律取目标月那一期。原先这里写死了一个 56%（某一期的读数），而目标月那期是 54%
    # —— 一个不随数据走的常数，只要月份一翻就变成假话。区间跨度一并印出来，
    # 免得读者把当期这一个数当成公司的固定口径。
    FUT_FEE = {m: (PR[m]['fut_fee_pct'] if m in PR else None) for m in PWIN}
    # CPT 的口径名（client_order → commissionable_order，IBKR LITE 上线后免佣订单
    # 退出分母）。**断点月由台账现算，不在这里写死日期**：官方哪期改词是事实，
    # 写死的日期只是当时的抄件。
    _basis = [(m, PR[m]['cpt_basis']) for m in PWIN if m in PR]
    _cpt_brk = next((i for i, m in enumerate(PWIN)
                     if m in PR and PR[m]['cpt_basis'] == 'commissionable_order'
                     and any(b == 'client_order' for mm, b in _basis if mm < m)), None)

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
    # 是旧的 13 个月窗口上的读数，窗口拉到全历史后上沿就越过 92 了。
    noncl_all = 100 - cleared_all / dart_all * 100
    cr_share = cr_all / eq_all * 100
    mg_share = mg_all / eq_all * 100
    # 生息基数占比图的对照基准：三年的年均占比。基准年份写在这里一处，图注与页尾都引它
    # —— 「一半」这种量级形容词一概不写死（见 Ex16 的图注注释）。
    # 连**标签**也从年份列表生成：原来正文里手打「2016-18」，改一次 _B_YEARS 就成假话。
    _B_YEARS = ('2016', '2017', '2018')
    _B_LAB = f'{_B_YEARS[0]}-{_B_YEARS[-1][2:]}'
    _B1618 = [i for i, k in enumerate(ALL) if k[:4] in _B_YEARS]
    if not _B1618:
        raise SystemExit(f'生息基数占比图的对照基准年 {_B_YEARS} 在序列 {ALL[0]}–{ALL[-1]} 里一格都没有')
    _cr_b1618 = float(np.nanmean(cr_share[_B1618]))
    _mg_b1618 = float(np.nanmean(mg_share[_B1618]))
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
    cpt = _PW('cpt_all_usd')
    stk_os, stk_cpt = _PW('order_size_stocks_shares'), _PW('cpt_stocks_usd')
    opt_os, opt_cpt = _PW('order_size_options_contracts'), _PW('cpt_options_usd')
    fut_os, fut_cpt = _PW('order_size_futures_contracts'), _PW('cpt_futures_usd')
    ptd = P('trading_days')
    stk_d = P('stk_shares') / stk_os / ptd
    opt_d = P('opt_contracts') / opt_os / ptd
    fut_d = P('fut_contracts') / fut_os / ptd
    pct_fo = (opt_d + fut_d) / (stk_d + opt_d + fut_d)
    prod_d = stk_d + opt_d + fut_d
    cov_prod = prod_d / P('darts') * 100     # 推导产品 DARTs 对披露总量的覆盖率
    # 量纲：cleared（千笔/日）× cpt（$/笔）= 千美元/日；÷1000 → 百万美元/日（$mn/day）
    comm_day = cleared_all[[ALL.index(m) for m in PWIN]] * cpt / 1000

    # ── 窗口无关的取数助手 ──
    # ⚠ 一律按**尾部**定位，不写死窗口下标：原来的 `a[:12]` / `a[-1]/a[0]` 在 13 格
    #   窗口里恰好等价于「前 12 个月」与「对去年同月」，窗口一变就静默改口径。
    #   2026-09 删掉了 `avg12()`（gs_bar 那条「Prior 12mo Avg.」虚线的来源）——
    #   本页不再画均线，也不再有任何标题引用「相对前 12 个月均值高/低多少」。
    LAG = 12

    def yoy(a):
        """末期对 12 个月前的同比（小数）。算不出返回 NaN。本页唯一的同比口径。"""
        a = np.asarray(a, float)
        if len(a) <= LAG:
            return float('nan')
        c, b = a[-1], a[-1 - LAG]
        if not (np.isfinite(c) and np.isfinite(b)) or b == 0:
            return float('nan')
        return float(c / b - 1)

    def mom(a):
        """末期环比（小数）。上月缺值（新闻稿那几张图有洞）时返回 NaN 而不是崩。"""
        a = np.asarray(a, float)
        if len(a) < 2 or not (np.isfinite(a[-1]) and np.isfinite(a[-2])) or a[-2] == 0:
            return float('nan')
        return float(a[-1] / a[-2] - 1)
    # 一律走 LN：窗口拉长之后派生序列的头几格是 NaN，裸 L 会把字面 NaN 送进 JSON
    # （payload_guard 会拦，但拦在最后一步，报错点离病因很远）。
    LN = lambda a: [None if v is None or not np.isfinite(v) else round(float(v), 6) for v in a]
    L = LN

    def yr_mean(arr, yr):
        idx = [i for i, k in enumerate(ALL) if k[:4] == yr]
        return float(np.nanmean(arr[idx])) if idx else float('nan')

    def peak_zh(arr, unit='$', dec=1, suffix='B'):
        """当期相对**全历史峰值**的位置，一句话现算。

        ⚠ 这个函数是为了根除「余额在创新高」那类写死的断言而存在的。2026-07 实测：
        融资余额峰值停在 2026-06 的 $108.5B、客户现金停在 2026-06 的 $182.4B，当月
        两条都不是新高 —— 而页面上两处「在创新高」是写死的英文/中文短语，数据怎么走
        它们都不会变。凡是要说「新高／离高点多远」，一律调这里，不要自己写形容词。
        """
        a = np.asarray(arr, float)
        i = int(np.nanargmax(a))
        f = lambda v: f'{unit}{v:,.{dec}f}{suffix}'
        if i == len(a) - 1:
            return f'当期 {f(a[-1])} 就是 {ALL[0]} 以来的最高'
        return (f'当期 {f(a[-1])}，峰值 {f(a[i])} 停在 {ALL[i]}'
                f'（当期比峰值低 {(1 - a[-1] / a[i]) * 100:.1f}%）')

    # 首年与当年（Exhibit 5 的年均对照要用，原先定义在长历史那一段的开头）
    y16, ylast = ALL[0][:4], target[:4]
    pre25 = [i for i, k in enumerate(ALL) if k < '2025-01']
    post25 = [i for i, k in enumerate(ALL) if k >= '2025-01']

    # ── 同比：一次在全历史上算完，各图按位置取 ──
    # 一律在**全历史**上算完再切窗：切完再算的话窗口最前 12 期永远是空的
    # （CONTRACT §6.4 第一条）。全页只有单月口径，见模块 docstring。
    NN_MONO = mono_yoy_arr(nn_all, ALL)          # 净新增账户（**还原口径**，见 ADJ）
    CL_MONO = mono_yoy_arr(cleared_all, ALL)     # implied cleared DARTs
    AN_MONO = mono_yoy_arr(ann_all, ALL)         # 人均年化 cleared DART
    MG_MONO = mono_yoy_arr(mg_all, ALL)          # 融资余额（期末存量）
    CR_MONO = mono_yoy_arr(cr_all, ALL)          # 客户现金（期末存量）

    def at(a):
        """某条同比序列在**本页目标月**的读数（小数）；算不出返回 None。"""
        v = a[ALL.index(target)]
        return None if not np.isfinite(v) else float(v)

    def yoy_rhs(vals, name, ymax=None, color='GOLD', yfmt='pct0'):
        """gs_bar 的次轴同比对象。给了它引擎就画次轴折线、**不画 12 个月均线**，
        左上角那个 y/y 气泡也自动不画（同一件事说两遍）。

        · `vals` 是**小数**同比，这里乘 100 统一转成百分点，免得各处各乘一遍；
        · 前 12 期必然是 NaN → 一律过 `LN()` 转 None（裸 NaN 会被 payload_guard 拦在
          最后一步，报错点离病因很远），引擎对 null 断笔、不插值；
        · 整条都算不出来时返回 None 而不是一个空对象 —— 引擎只看 `ex.yoy` 在不在就判
          双轴，值全空时右轴会印出一列假刻度而线一个点都没画
          （CONTRACT §6.4「整条同比都算不出来时不要给次轴」）。
        """
        v = LN(np.asarray(vals, float) * 100)
        if not any(x is not None for x in v):
            return None
        o = {'name': name, 'color': color, 'yfmt': yfmt, 'values': v}
        if ymax is not None:
            o['ymax'] = ymax
        return o

    # ── Exhibit 定义（标题文案逐字照抄 build_report.py 的 title_src 调用）──
    ex = []
    # 左端裁决登记簿：{exhibit 编号: 为什么它的左端比主窗口晚}。**在建图现场登记，
    # 理由字符串与交给 mrwin.Leg 的那一份是同一个变量** —— 页尾窗口说明照它现算，
    # 不再手抄一份图号名单（手抄的那份改一次图号就成假话）。
    # 建完之后有一道硬校验：实际左端晚了却没登记理由的，直接让构建失败。
    LATE_WHY = {}

    # 图注里要指**另一张图**时不写死图号：写占位符，建完统一回填。
    # 照 build/cme.py 的 ⟨nav:…⟩ 办法：登记了却没有任何一处用到 → 停机；
    # 回填之后 payload 里还残留 ⟨nav: → 停机。2026-08 的合并里各图前移过一号，
    # 手写的「见 Exhibit 16」当时全靠人肉跟着改，没有任何东西会报错。
    # 2026-09 又改了一次号（删两张、并两对、挪一张），这套占位符是唯一没出事的一处。
    NAV = {}

    # `gs_bar` 的次轴字段叫 `yoy`，但**它只是「右轴那条线」的通道**，不一定装同比：
    # Exhibit 8 用它画 F&O 占比。登记在这里，好让下面「凡是画了同比就必须写明单月」
    # 那道护栏别误伤 —— 判据认字段名会把一条占比线当成没标口径的同比。
    RHS_NOT_YOY = set()

    # ── 三本登记簿，都在**建图现场**登记、页尾从它们现算，并各配一道复核护栏 ──
    # 手写的名单会在增删图之后指着错的图，而页面上没有任何痕迹（本页 2026-08 的
    # 「见 Exhibit 16」栽过一次，NAV 那套占位符就是那次的产物）。
    #
    # STOCK_YOY：次轴那条线画的是**存量**的点对点同比（CONTRACT §6.1 第 2 条）。
    #   登记它是为了让下面「流量图必须逐图印代价」那道护栏知道谁不欠这笔账 ——
    #   §6.1 第 3 条自己把范围限定在流量，存量的对照量回答的是另一个问题。
    # COST_NOTE：§6.1 第 3 条要求的那段逐图实测代价的原文（`mom_cost_zh()` 出）。
    #   护栏要拿它把自己从「页面上不许再出现滚动措辞」那条反向检查里排除 ——
    #   那条检查防的是**残留**的旧口径措辞，而这一段里的滚动数字是契约明令要印的。
    # SPLIT_SRC：柱与线**不同源**、因而「拿柱直接除得出线」这句话不成立的图。
    #   页尾那句承诺（「线上任一点就是这根柱相对 12 根柱之前的涨幅」）的例外名单。
    STOCK_YOY, COST_NOTE, SPLIT_SRC = {}, {}, {}

    # （2026-09 删：这里原有一本「序列类型登记簿」KIND，flow/stock 在建图现场登记，
    #  供页尾那句「流量走 12 个月滚动、存量走点对点」现算例外名单、并与图上印出来的
    #  口径标记对撞停机。全站统一单月同比之后那句话与那份名单都不存在了，登记簿随之删除；
    #  接替它的护栏在下面「同比口径」一段 —— 凡画同比就必须在标题域写明「单月」。）

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

    # ══════════════════ Exhibit 2：净新增账户（柱）+ 单月同比（次轴）══════════════
    # 2026-09 的合并：原 Exhibit 3（净新增账户的 12 个月滚动同比，整张 gs_line）删掉，
    # 那条同比改画成本图的**次轴折线** —— 同一张图上，柱与线终于讲的是同一个指标。
    #
    # ⚠ 但**「同一个指标」不等于「同一列」**：本图是全页唯一一张柱与线口径不同源的图，
    #   所以「线上任一点 = 这根柱相对 12 根柱之前的涨幅」这句话在**别的图上成立、
    #   在本图上不成立**，页尾那条口径说明因此把本图单独拎出来点名。
    #   柱画的是历史指标表**表内披露**的
    #   Net New Accounts（= 账户存量差分），线的分子分母一律用公司 Notes **还原后**的
    #   真实增长（见 ADJ）。不写明就是错 —— 2025-03 / 2025-09 两个月两者差一大截。
    _nn_cap = 200.0          # 次轴截轴上界，理由见下面的 cap 注释
    _nn_over = [i for i, v in enumerate(NN_MONO) if np.isfinite(v) and v * 100 > _nn_cap]
    ex.append({
        'n': 2, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': XL, 'xstep': 12,
        'title': f'IBKR added ~{net_new[-1]:.0f}k net new accounts, {pctf(at(NN_MONO))} YoY '
                 f'and {pctf(mom(net_new))} MoM',
        'ylab': 'Net New Accounts (thousands)',
        'ylab2': 'y/y, single month (%)',
        'note': ('柱画的是历史指标表披露的 Net New Accounts（= 账户存量差分），'
                 f'{XL[0]} 起逐月，一格没有跳过。'
                 '<b>次轴金色折线是净新增账户的单月同比</b>（本月 ÷ 去年同月 − 1），'
                 '本页全部同比都是这个口径，与下方汇总表的 y/y 列逐格对得上。'
                 '<b>但柱与线不同源，所以本图的线<u>不能</u>拿柱直接除出来</b>'
                 '（本页其余几张画同比的图可以，那是单月口径的好处；本图是唯一的例外）：'
                 '柱是表内披露值，线的分子分母一律用公司 Notes '
                 f'还原后的真实账户增长（{nn_adj_txt}）—— '
                 + (f'直接用表内差分会让 {naive_ex[0]} 的同比从 {pctf(naive_ex[1])} '
                    f'虚高到 {pctf(naive_ex[2])}。' if naive_ex else '')
                 + (f'含一次性口径调整、不可与相邻柱直读的月份以<b>斜纹柱</b>标出'
                    f'（悬停有说明）：{adj_txt}。' if mk2 else
                    f'本窗口内没有需要标注的调整月（全部调整见页尾说明：{nn_adj_txt}）。')
                 # 截轴：不是为了好看，是因为不截的话近十年那一段读不出来。数字现算。
                 + (f'<b>次轴截在 +{_nn_cap:.0f}%</b>：单月同比在 '
                    f'{ALL[_nn_over[0]]}–{ALL[_nn_over[-1]]} 那 {len(_nn_over)} 个月被疫情'
                    f'开户潮的低基数顶到最高 {max(NN_MONO[i] for i in _nn_over) * 100:,.0f}%'
                    f'（{ALL[int(np.nanargmax(np.where(np.isfinite(NN_MONO), NN_MONO, -np.inf)))]}），'
                    '不截的话其余十年全被压成贴着零线的一条平线。'
                    '<b>截轴不删点</b>：超界的点画成空心红圈、真值红色竖排标在图顶'
                    '（连续几个月的真值标签会依次向右错开，标签下方那根柱才是它的月份）。'
                    if _nn_over else '')
                 + ('<br>PDF Notes 原文：' + ' / '.join(nt['text'] for nt in notes) if notes else '')),
        'legend': 'Net New Accounts', 'values': L(net_new),
        'yoy': yoy_rhs(NN_MONO, 'y/y, single month (RHS)', ymax=_nn_cap),
        'cap_note': (f'right axis capped at +{_nn_cap:.0f}% — {len(_nn_over)} months exceed it '
                     f'(true values shown)' if _nn_over else None),
        # ⚠ 本图不给 mom_txt / yoy_txt。给了 `yoy` 之后引擎就不画 y/y 气泡了
        #   （同一件事说两遍），而 mom 气泡被钉在 `Xc(n-4) + band*0.2` —— 128 根柱通栏后
        #   band 只有 ~8px，气泡整个落进末柱数值标签与次轴末点读数的横向区间。
        #   环比读数在下方汇总表的 m/m 列里，一格不少。
        'bar_marks': [i for i, w in enumerate(WIN) if w in adj_nn],
        'mark_note': '该月含一次性账户口径调整，不可与相邻柱直读（见图注）',
    })
    _n_nn = ex[-1]['n']
    # 逐图代价（§6.1 第 3 条）：线走**还原口径**的真实增长（nn_real），所以实测的也是
    # 那条序列 —— 量的必须是图上真画着的那条线，不是与它差一截的表内披露值。
    # 窗口 = 本图横轴（WIN ≡ ALL，柱一根不缺）。
    COST_NOTE[_n_nn] = mom_cost_zh(nn_real, ALL, WIN)
    ex[-1]['note'] += COST_NOTE[_n_nn]
    # 柱与线不同源，页尾那句「拿柱直接除就是线上这一点」在本图不成立 —— 登记在这里，
    # 页尾从登记簿现算，并由下面那道护栏用 payload 自己复核（多一张少一张都停机）。
    SPLIT_SRC[_n_nn] = ('柱是历史指标表内<b>披露</b>的 Net New Accounts（账户存量差分），'
                        '而线的分子分母一律走公司 Notes <b>还原后</b>的真实增长，'
                        '口径调整月两者差一大截')

    # ══════════════════ Exhibit 3：implied cleared DARTs（柱）+ 单月同比 ═══════════
    # 左端：推导式要**月初**账户数，序列首月没有上月 → cleared_all[0] 恒为 NaN。
    # gs_bar 能吃前导 null，但那一格是「算不出」而不是「为 0」，留一根空柱在最左边
    # 只会让人以为那个月没数据。交给 resolve() 裁到序列第二个月。
    _lag4 = '推导式要月初账户数，序列首月没有上月'
    _w4 = mrwin.resolve('gs_bar',
                        [mrwin.Leg('cl', 'Implied cleared DARTs', cleared_all, 'primary',
                                   _lag4)], XL, 0)
    XL4, cl4 = _w4.cut(XL), np.array(_w4.cut(cleared_all), float)
    _y4v = at(CL_MONO)
    _cov_lo, _cov_hi = float(np.nanmin(cov_cleared)), float(np.nanmax(cov_cleared))
    ex.append({
        'n': 3, 'kind': 'gs_bar', 'fmt': 'f0c', 'xlabels': XL4, 'xstep': 12,
        'title': f'Implied cleared DARTs at {cl4[-1]:,.0f}k/day, {pctf(_y4v)} YoY '
                 f'and {pctf(mom(cl4))} MoM…',
        'ylab': 'Cleared DARTs (thousands of trades/day)',
        'ylab2': 'y/y, single month (%)',
        'note': 'We calculate cleared DARTs = Cleared avg. DART per account (annualized) / 252 trading days * '
                'average of beginning- and end-of-month total accounts. '
                '假设：账户数在月内线性变化（故取期初期末简单平均）；官方的年化口径就是按 252 天折算，'
                '不要换成当月实际交易日。'
                # 窗口是全历史，这个区间会宽 —— 数字现算，不留旧窗口的实测值。
                f'结果约为 IBKR 单独披露的 Total Client DARTs 的 {_cov_lo:.0f}%–{_cov_hi:.0f}%'
                f'（{XL4[0]}–{XL4[-1]} 全区间，中位 {float(np.nanmedian(cov_cleared)):.0f}%），'
                '差额是口径差（cleared ≠ total client），那张图与那条差额线见 ⟨nav:totaldarts⟩，'
                '不是估算误差。'
                '次轴金色折线是本图柱的<b>单月同比</b>（本月 ÷ 去年同月 − 1）。',
        'legend': 'Implied Cleared DARTs', 'values': L(cl4),
        'yoy': yoy_rhs(_w4.cut(CL_MONO), 'y/y, single month (RHS)'),
    })
    ex[-1]['note'] += _w4.why
    LATE_WHY[ex[-1]['n']] = _lag4
    _n_cl = ex[-1]['n']
    # 逐图代价（§6.1 第 3 条）。窗口 = 本图横轴（左端被 resolve() 裁掉了首月），
    # 所以 win 走 `_w4.cut(WIN)` 而不是全历史：诊断只该量读者在图上看得到的那一段。
    COST_NOTE[_n_cl] = mom_cost_zh(cleared_all, ALL, _w4.cut(WIN), per_day=True)
    ex[-1]['note'] += COST_NOTE[_n_cl]

    # ══════════════════ Exhibit 4：人均年化 cleared DART ═══════════════════════════
    # 图种是 `lines` + `zero_base`：标题引用「比 2016 年低 N%」这种幅度，而引擎默认下界
    # 是「最小值 − 极差 5%」，那是一次没有标注的隐性截轴，会把这个幅度在视觉上放大。
    # 顺带的好处：`lines` 不属 mrwin.DENSE，128 个点不再逐点标数值。
    _y5v = at(AN_MONO)
    _a16, _alast = yr_mean(ann_all, y16), yr_mean(ann_all, ylast)
    _y5g = (1 - _alast / _a16) * 100
    ex.append({
        'n': 4, 'kind': 'lines', 'fmt': 'f0', 'xlabels': XL, 'xstep': 12, 'zero_base': True,
        'end_label': True,
        'title': f'…leading to {pctf(_y5v)} annualized cleared DARTs per account vs. last year'
                 f'; {_a16:.0f}x avg. in {y16} → {_alast:.0f}x YTD in {ylast}, {_y5g:.0f}% below',
        'ylab': 'Annualized cleared DARTs / account (x)',
        'series': [{'name': 'Cleared avg. DART per account (annualized)', 'color': 'NAVY',
                    'values': L(ann_all)}],
        'note': '<b>公司直接披露的 Cleared Avg. DART per Account (Annualized)，非推导值。</b>'
                f'当月 {ann_all[-1]:.0f}x：环比 {pctf(mom(ann_all))}、单月同比 {pctf(_y5v)}。年均：'
                + '、'.join(f'{y} {yr_mean(ann_all, y):.0f}x' for y in
                           [y16, '2019', '2020', '2022', '2023', ylast])
                + '。2020-21 的凸起是疫情期间的交易热潮，其后回落到的平台明显低于 2016-18 —— '
                  '本图从 2016-01 起画，正是为了让「结构性下台阶」与「周期性回落」分得开。'
                  '纵轴从 0 起（标题引用的是降幅，截过的轴会把降幅凭空放大）。',
    })
    _n_ann = ex[-1]['n']

    # ══════════════════ Exhibit 5：Total client DARTs（披露）+ 未被推导覆盖的占比 ═══
    # 2026-09 从页尾（原 Exhibit 17）挪到这里：它讲的正是上面两张 cleared DARTs 图与
    # 公司披露总量之间的差额，紧挨着被解释的对象比隔着十张图有用。
    # 断点索引现算且**允许算不出**：`ALL.index()` 找不到就 ValueError，整个 routine 硬失败
    # 退出，页面永久停更（build/lpla.py 就是栽在这上面）。断点不在轴上就不给 break_at，
    # 同时把图注里「红色虚线」那句一并省掉：图注只许声称图上真有的东西。
    # ── Exhibit 5 图注要用的三样，一律现算 ────────────────────────────────
    # ① **一条与推导式完全无关的独立复算**：用新闻稿的 Average Order Size 反推订单数
    #    （股数÷每单股数 + 期权张数÷每单张数 + 期货张数÷每单张数，再÷当月交易日）。
    #    这条路一次都不碰 ann_dart_acct、也不碰账户数，却与推导 cleared DARTs 吻合到
    #    百分之一以内 —— 这是「推导式本身没错，缺口在分子口径」最硬的一条证据。
    _cl_on_pw = cleared_all[[ALL.index(m) for m in PWIN]]
    _xcheck = prod_d / _cl_on_pw * 100
    _xc_med = float(np.nanmedian(_xcheck))
    _xc_lo, _xc_hi = float(np.nanmin(_xcheck)), float(np.nanmax(_xcheck))
    # ② 逐年覆盖率（= 100 − 本线），用来定位「哪两年下了台阶」——年份**现算**，不手写：
    #    手写「2019 前后」会把读者引向 IBKR LITE，而实测台阶落在 2018 年年中到 2019 年初。
    _cov_yr = {y: float(np.nanmean(100 - noncl_all[[i for i, k in enumerate(ALL) if k[:4] == y]]))
               for y in sorted({k[:4] for k in ALL})}
    _cov_yrs = sorted(_cov_yr)
    _drops = sorted(((_cov_yr[a] - _cov_yr[b], a, b)
                     for a, b in zip(_cov_yrs, _cov_yrs[1:])), reverse=True)[:2]
    _drop_txt = '、'.join(f'{a}→{b}（−{d:.1f}pp）' for d, a, b in sorted(_drops, key=lambda t: t[1]))

    BRK_M = '2025-01'
    brk = ALL.index(BRK_M) if BRK_M in ALL else None
    brk_note = '（红色虚线右侧与左侧不可直读）' if brk is not None else ''
    ex.append({
        'n': 5, 'kind': 'bar_line_dual', 'x': 'long', 'xlabels': XL, 'xstep': 12,
        'full': True, 'height': 300,
        'title': f'Total client DARTs (disclosed) at {dart_all[-1]:,.0f}k/day; the share NOT captured by implied '
                 f'cleared DARTs stepped up from ~{np.nanmean(noncl_all[pre25]):.0f}% to '
                 f'~{np.nanmean(noncl_all[post25]):.0f}% during 2025',
        'ylab': 'Total Client DARTs (thousands of trades/day)',
        'ylab2': 'Share not captured by implied cleared (%)',
        'bar': {'name': 'Total Client DARTs (disclosed)', 'color': 'BLUE', 'values': LN(dart_all),
                'yfmt': 'f0c'},
        'line': {'name': 'Share of total client DARTs not captured by implied cleared (RHS)',
                 'color': 'GREEN', 'values': LN(noncl_all), 'yfmt': 'pct0'},
        # ⚠ 这段图注被返工过一次。第一版**内容是全的**，但排成了一堵四百字的连续中文，
        #   而且第一句讲的是柱、定义落在第二句 —— 用户读完仍然问「这个指标是什么意思」。
        #   所以现在的规矩：**定义放第一句、算式与当期代入紧跟其后、每一节用 <br> 断开**。
        #   信息一个字没减，只是让「我在看什么」这一问在第一行就有答案。
        'note': ('<b>右轴那条绿线：公司披露的交易笔数里，本页那根推导出来的 cleared DARTs '
                 '够不着的那一块，占披露总量的百分之几。</b>'
                 f'<br><b>算式</b>：线 = 1 − 推导 cleared DARTs ÷ 披露 Total Client DARTs。'
                 f'当期代入 —— 披露 {dart_all[-1]:,.0f}k 笔/日，推导 cleared {cleared_all[-1]:,.0f}k 笔/日，'
                 f'差 {dart_all[-1] - cleared_all[-1]:,.0f}k；'
                 f'{dart_all[-1] - cleared_all[-1]:,.0f} ÷ {dart_all[-1]:,.0f} = {noncl_all[-1]:.1f}%，'
                 '就是线右端那个点。线越高 = 推导值离披露值越远。'
                 '<br><b>两条腿分别是什么</b>：柱是公司<b>每月直接披露</b>的 Total Client DARTs '
                 '（全部客户合计的日均交易笔数，官方原文口径，一步推导都没有）；'
                 f'线的分子来自 Exhibit {_n_cl} 那根<b>推导值</b>'
                 '（官方披露的 Cleared Avg. DART per Account 年化值 ÷ 252 个交易日 × '
                 '期初期末账户总数的平均值，非公司披露）。'
                 '<b>2017 年之前这个比值有官方版本</b>：IBKR 当年在季度 8-K 的 BROKERAGE '
                 'STATISTICS 表里把 Cleared DARTs 与 Total Customer DARTs 并排印出来，'
                 '一直印到 1Q2017；此后不再拆分披露，本页的推导才成为唯一来源。'
                 '<br><b>线往上走意味着什么</b>：披露总量里推导 cleared 够不着的那一块在变大 —— '
                 '<b>那就是 IBKR 执行但不由自己清算的那部分客户订单</b>。公司在 10-K 里把客户'
                 '二分得很干净：cleared customers 用 IBKR 的执行<b>与清算</b>；'
                 'non-cleared customers「including trading firms that provide liquidity in our ATS, '
                 'use our trade execution services while clearing with another prime broker or a '
                 'custodian bank」。后者的单进 Total Client DARTs，不进 cleared 口径。'
                 f'<br><b>这不是推导误差</b>：另有一条与推导式<b>完全无关</b>的算法能对上 —— '
                 f'用新闻稿的 Average Order Size 反推订单数（三大产品成交量 ÷ 每单规模 ÷ 当月交易日，'
                 f'既不碰人均年化 DART、也不碰账户数），它是推导 cleared DARTs 的 '
                 f'{_xc_med:.1f}%（{PXL[0]}–{PXL[-1]} 中位，区间 {_xc_lo:.0f}%–{_xc_hi:.0f}%），'
                 f'同时也比披露总量低一成多。两条互不相干的路径给同一个答案。'
                 '推导式剩下的近似只有三条、合计一两个百分点，且都不随时间走：'
                 '账户数取期初期末两点（假设月内线性）、官方人均值只印整数、'
                 '年化按 252 天折算。<b>换成当月实际交易日反而会算出「推导值大于披露总量」的月份</b>，'
                 '所以 252 是对的，不要改。'
                 '<br><b>它不是什么</b>：不是清算失败率、也不是未交收比例（与 settlement 无关）；'
                 '不是市场份额、也不是客户流失。'
                 '<b>更正一处本页从前的说法</b>：这里曾写着「官方那个 per-account 指标的分母是 '
                 'cleared 账户，所以用总账户数反推会有系统性误差」—— <b>那是错的</b>。'
                 'IBKR 的 10-K 把 Total Accounts 与 cleared customer accounts 当同一个数印'
                 '（FY2025：正文「approximately 4.4 million cleared customer accounts」、'
                 'MD&A 表「Total Accounts 4,399」千户），non-cleared 客户是机构交易公司、'
                 '本来就不计进账户数；且 2010–2017 年公司同时印过 Cleared DARTs 与 Total Accounts，'
                 '用<b>总账户数</b>复算它自印的 per-account 值，十几个季度误差都在 1% 以内。'
                 f'<br><b>为什么画「够不着的那一块」而不直接画覆盖率</b>：覆盖率'
                 f'（cleared ÷ total）全区间只在 {_cov_lo:.0f}%–{_cov_hi:.0f}% 之间走，'
                 '而本图型的右轴强制含 0 —— 一条 '
                 f'{_cov_lo:.0f}–{_cov_hi:.0f} 的线钉在 0–100 的轴上就是贴着轴顶的一条平线，'
                 f'看不出任何变化；取补数之后是 {100 - _cov_hi:.0f}%–{100 - _cov_lo:.0f}%，'
                 '在同一根轴上摊得开。两者互为 100 减，信息量完全一样，'
                 '要读覆盖率就拿 100 减这条线。'
                 '<br><b>覆盖率的逐年均值</b>（= 100% 减本线）：'
                 + '、'.join(f'{y} {np.nanmean(1 - noncl_all[[i for i, k in enumerate(ALL) if k[:4] == y]] / 100) * 100:.1f}%'
                            for y in ['2016', '2019', '2022', '2024', '2025', ylast])
                 + f' —— 逐年看下过两次台阶：{_drop_txt}。'
                 + '（<b>注意不是 IBKR LITE</b>：LITE 2019-09 上线，而第一次下台阶在那之前就走完了；'
                 '公司自己披露 LITE 当时只有约 1 千笔/日、占当月 DARTs 的 0.1%，量级差两个数量级。）'
                 '<b>疑似口径/分类变更，未经公司确认</b>' + brk_note + '。'
                 '<br><b>推导值有过官方对照</b>：2016-01 至 1Q2017 公司按季单独披露过 Cleared DARTs，'
                 '与本页同期推导出的覆盖率逐季相差不到 1pp —— 这条线在有官方数可对的那几年是准的，'
                 '2017 年以后才没得对。'),
    })
    if brk is not None:
        # 断点与图注那句话绑在一起给：给了 brk_note 就必须给 break_at，反之亦然，
        # 不然又会出现「图注说画了红虚线、图上一条都没有」。
        ex[-1]['break_at'] = brk
        ex[-1]['break_label'] = f'{BRK_M[:4]}：疑似口径变更'
    NAV['⟨nav:totaldarts⟩'] = ex[-1]['n']
    _n_td = ex[-1]['n']

    # ══════════════════ Exhibit 6-9：新闻稿口径的四张（PWIN）══════════════════════
    # 这四张用的 CPT 与 Average Order Size **只印在月度新闻稿上**，官方那份 Historical
    # Brokerage Metrics 表（= series/ibkr.csv 的全部内容）里没有这两列。数值已入库到
    # series/ibkr_pr.csv，所以它们现在与主窗口几乎同长 —— 2026-09 之前只有十几个月，
    # 那是**本机缓存**的长度，不是数据的长度。
    _PR_WHY = (f'<b>本图 {PXL[0]}–{PXL[-1]}（{len(PXL)} 期），比主窗口 {XL[0]} 晚 '
               f'{len(XL) - len(PXL)} 期</b>：本图要用的 CPT（单笔佣金）与 Average Order Size '
               '<b>只印在月度新闻稿上</b>，官方那份 Historical Brokerage Metrics 表'
               f'（本站落库为 series/ibkr.csv 的全部 {len(COLS)} 列）里根本没有这两列，'
               f'而官方第一份月度新闻稿是 {PXL[0]}。数值逐月入库在 '
               '<code>series/ibkr_pr.csv</code>，本页只查表、不解析 PDF。'
               + (f'<b>{"、".join(PR_GAPS)} 是图上的缺口</b>：官方那期新闻稿从来没发过'
                  '（下载端点对不存在的文件返回 200 + 0 字节，实测过十几种文件名），'
                  '所以那一格留空 —— 不补 0、不插值、不拿邻月顶上。'
                  if PR_GAPS else '')
               + (f'<b>{PXL[_cpt_brk]} 起口径变了</b>（图上红色竖虚线）：CPT 的定义从 per cleared '
                  '<em>client</em> order 改成 per cleared <em>Commissionable</em> Order —— '
                  'IBKR LITE 上线后免佣订单退出分母。公司在改词的前一期先以脚注说过同一件事'
                  '（「DARTs and cleared client orders do not include IBKR LITE clients\' '
                  'U.S. Reg.-NMS orders since they are commission free」）。'
                  '<b>跨这条线比 CPT 高低是跨口径比较</b>，实测跨线那两期只差 1 美分，'
                  '但口径变了这件事本身不因幅度小而消失。'
                  if _cpt_brk is not None else ''))
    # 断点标签**必须短**：引擎把它 rotate(-90) 从图顶往下挂，长文案会一路盖到柱顶的
    # 数值标签上（实测「2019-11：CPT 口径改为 Commissionable Order」在 Ex6 上压掉两个
    # 柱值，visual_qa 判 🔴）。完整说明放图注，标签只留「哪一期 + 变了什么」。
    _brk_kw = ({'break_at': _cpt_brk, 'break_label': f'{PWIN[_cpt_brk]} CPT 口径变更'}
               if _cpt_brk is not None else {})

    _cd_mono = mono_yoy_arr(comm_day, PWIN)
    ex.append({
        # ⚠ 左轴显式给 `yfmt`。次轴同比含负值 → 引擎为对齐两轴零点把左轴下界推到负数，
        #   刻度落在 2.5 的整数倍上；而引擎的自动刻度格式器 `plainAxis()` 对 2.5 这种
        #   步长按 log10 只算出 0 位小数，于是 12.5 / 7.5 / 2.5 印成 13 / 8 / 3 ——
        #   刻度看上去不等距（visual_qa 判 🔴「轴刻度不等距（值被四舍五入）」）。
        #   本页只改自己这一格；引擎那条通用毛病不在本轮范围内。
        'n': 6, 'kind': 'gs_bar', 'fmt': 'f1', 'yfmt': 'f1', 'xlabels': PXL, 'xstep': 12,
        'title': f'Implied commission revenue/day at ${comm_day[-1]:,.1f}mn, '
                 f'{pctf(_cd_mono[-1] if np.isfinite(_cd_mono[-1]) else float("nan"))} YoY '
                 f'and {pctf(mom(comm_day))} MoM',
        'ylab': 'Implied Commission Revenue / Day ($mn)',
        'ylab2': 'y/y, single month (%)',
        'note': 'Commission revenue/day estimated as cleared DARTs (千笔/日) x average commission per cleared '
                'commissionable order ($/笔) ÷ 1,000 → $mn/day。'
                '假设：新闻稿披露的是 average commission per cleared <b>commissionable</b> order，而乘数是全部 '
                'cleared DART，两个总体是否一致未经证实——若 DART 计入免佣订单，本图偏高；'
                'cleared DARTs 本身也是推导值，两层近似复合。要得到月度总额还需再乘当月官方交易日数。'
                '月度无对应披露可比，季度有（10-Q 的 Commissions 行），但尚未接入。'
                '次轴金色折线是本图柱的<b>单月同比</b>。'
                + _PR_WHY,
        'legend': 'Implied Commission Revenue/Day', 'values': L(comm_day),
        'yoy': yoy_rhs(_cd_mono, 'y/y, single month (RHS)'),
        **_brk_kw,
    })
    _n_cd = ex[-1]['n']
    # 逐图代价（§6.1 第 3 条）。本图走新闻稿窗口（PWIN），中间还有一格官方没发过的洞 ——
    # 两种口径都算得出的月份因此比主窗口那两张少，实测数照实报，不拿主窗口的数顶替。
    COST_NOTE[_n_cd] = mom_cost_zh(comm_day, PWIN, PWIN, per_day=True)
    ex[-1]['note'] += COST_NOTE[_n_cd]

    dc = (cpt[-1] - cpt[-2]) * 100 if np.isfinite(cpt[-2]) else float('nan')
    _cpt_lo, _cpt_hi = float(np.nanmin(cpt)), float(np.nanmax(cpt))
    ex.append({
        # 原来是 `gs_line_avg`（平滑线 + 12 个月均线 + 右端均值标注）。均线按需求删掉，
        # 而那个图型的 `avg12` 是必填（build/verify_pages.py 的 need 表），所以换图型。
        # 换成 `lines` 而不是 `gs_line`，三条理由：
        #   ① `gs_line` 属 mrwin.DENSE —— 中段有 null 时 verify_pages 直接判 ERROR，
        #      而本序列有 2021-10 这个洞（官方没发那期稿子）；
        #   ② `gs_line` 逐点标数值，127 个点抽稀后剩下的是一串孤立读数，噪音大于信息；
        #   ③ `gs_line` 的纵轴是「最小值 − 极差 30%」，一次没有标注的隐性截轴，会把
        #      2016→2021 那段降幅在视觉上放大约 1.5 倍。`lines` + zero_base 从 0 起。
        'n': 7, 'kind': 'lines', 'fmt': 'usd2', 'xlabels': PXL, 'xstep': 12,
        'zero_base': True, 'end_label': True,
        'title': f'Average commission per cleared order at ${cpt[-1]:.2f}, '
                 + (f'{"down" if dc < 0 else "up"} {abs(dc):.0f}¢ MoM' if np.isfinite(dc)
                    else 'MoM not comparable (prior month not published)')
                 + f'; ${_cpt_hi:.2f} → ${_cpt_lo:.2f} range since {PXL[0]}',
        'ylab': 'Average commission / cleared order ($)',
        'series': [{'name': 'Avg. commission per cleared order', 'color': 'NAVY',
                    'values': L(cpt)}],
        'note': '纵轴从 0 起（标题引用的是区间与幅度，截过的轴会把幅度凭空放大）。' + _PR_WHY,
        **_brk_kw,
    })
    _n_cpt = ex[-1]['n']

    dpp = (pct_fo[-1] - pct_fo[-2]) * 100 if np.isfinite(pct_fo[-2]) else float('nan')
    fo_mom = (opt_d[-1] + fut_d[-1]) / (opt_d[-2] + fut_d[-2]) - 1
    st_mom = stk_d[-1] / stk_d[-2] - 1
    clause = ('as stock DARTs increased more than options and futures' if (dpp < 0 and st_mom > fo_mom)
              else ('as options and futures DARTs outgrew stocks' if dpp > 0 else 'on shifting product mix'))
    ex.append({
        # 原来是 `stacked_dual`。那个图型属 mrwin.DENSE（中段 null 直接判 ERROR），且
        # 它对缺月的处理是 `base[i] + null == base[i]` —— 会把 2021-10 画成一根**零高的柱**，
        # 与「那个月一笔没成交」在画面上无法区分。改成 `gs_bar` + `stacks`：
        # 引擎对 `values[i]` 为 null 的柱整根跳过（charts.js 的 `if (!isNum(...)) continue`），
        # 缺口就是缺口。右轴仍是 F&O 占比，走 gs_bar 的次轴通道。
        # 段内逐格数值标签一并关掉（`bar_labels: False` 关柱顶总额）：127 根柱上每段
        # 印一个数只会连成一片，占比看堆叠高度、看右轴那条线，明细看表格视图。
        'n': 8, 'kind': 'gs_bar', 'fmt': 'f0c', 'xlabels': PXL, 'xstep': 12,
        'bar_labels': False,
        'title': f'Implied product DARTs: the % in the form of F&O '
                 + (f'{"decreased" if dpp < 0 else "increased"} {abs(dpp):.1f}pp MoM, {clause}'
                    if np.isfinite(dpp) else f'at {pct_fo[-1] * 100:.1f}%')
                 + f'; {pct_fo[0] * 100:.0f}% in {PXL[0]}',
        'ylab': 'Implied Product DARTs (thousands of trades/day)',
        'ylab2': 'F&O share of implied DARTs (%)',
        'note': 'Product DARTs estimated as monthly volume / average order size / US trading days. '
                '假设：average order size 取的是全部订单的均值；对期货与国际股票同样套用<b>美股</b>交易日数。'
                f'本图各产品推导值合计约为披露 Total Client DARTs 的 '
                f'{np.nanmin(cov_prod):.1f}%~{np.nanmax(cov_prod):.1f}%'
                f'（{PXL[0]}–{PXL[-1]}，中位 {np.nanmedian(cov_prod):.1f}%），'
                '故本图口径接近 cleared 而非 total（下方总表那一列是 Total Client DARTs）。'
                + _PR_WHY,
        'values': L(prod_d),
        'stacks': [
            {'name': 'Implied Stock DARTs', 'color': 'BLUE', 'values': L(stk_d)},
            {'name': 'Implied Options DARTs', 'color': 'GRAY', 'values': L(opt_d)},
            {'name': 'Implied Futures DARTs', 'color': 'NAVY', 'values': L(fut_d)},
        ],
        'yoy': yoy_rhs(pct_fo, '% Futures & Options (RHS)', color='GREEN', yfmt='pct1'),
        **_brk_kw,
    })
    _n_pd = ex[-1]['n']
    RHS_NOT_YOY.add(_n_pd)          # 本图右轴是占比，不是同比（见 RHS_NOT_YOY 的说明）

    chg_cpt = [('stocks', stk_cpt[-1] / stk_cpt[-2] - 1), ('options', opt_cpt[-1] / opt_cpt[-2] - 1),
               ('futures', fut_cpt[-1] / fut_cpt[-2] - 1)]
    dec = [f'{abs(c)*100:.0f}% for {n}' for n, c in chg_cpt if c <= -0.01]
    inc = [f'{abs(c)*100:.0f}% for {n}' for n, c in chg_cpt if c >= 0.01]
    flat = [n for n, c in chg_cpt if abs(c) < 0.01]
    parts = []
    if dec: parts.append('decreased ' + ', '.join(dec))
    if inc: parts.append('increased ' + ', '.join(inc))
    ex.append({
        # 原来是 `lines_endlabels`（两端都标数值）。同 Exhibit 7 的第 ① 条：它属 DENSE，
        # 中段 null 会被 verify_pages 判 ERROR，而本序列有 2021-10 那个洞。
        # `lines` + `end_label` 只标末点；起点读数改写进标题，信息不丢。
        'n': 9, 'kind': 'lines', 'fmt': 'usd2', 'xlabels': PXL, 'xstep': 12,
        'zero_base': True, 'end_label': True,
        'title': 'Average commissions/trade ' + ' and '.join(parts or ['were stable']) + ' MoM' +
                 (f', and were largely flat for {", ".join(flat)}' if flat else '') +
                 f'; in {PXL[0]} they were ${stk_cpt[0]:.2f} / ${opt_cpt[0]:.2f} / ${fut_cpt[0]:.2f}',
        'ylab': 'Average commission per trade ($)',
        'series': [
            {'name': 'Stocks Avg CPT', 'color': 'NAVY', 'values': L(stk_cpt)},
            {'name': 'Options Avg CPT', 'color': 'BLUE', 'values': L(opt_cpt)},
            {'name': 'Futures Avg CPT', 'color': 'MBLUE', 'values': L(fut_cpt)},
        ],
        'note': f'纵轴从 0 起。三条线与 Exhibit {_n_cpt} 的总额来自同一张 Key products 表。'
                + _PR_WHY,
        **_brk_kw,
    })
    _n_pcpt = ex[-1]['n']
    # 这四张的左端比主窗口晚，理由是**来源**而不是算不出来：登记进 LATE_WHY，
    # 由下面的回填①写进各自图注，页尾那句「原因逐张写在各自图注里」才守得住。
    _PR_NS = [_n_cd, _n_cpt, _n_pd, _n_pcpt]
    _lag_pr = (f'CPT 与平均订单规模只印在月度新闻稿上，而官方第一份月度新闻稿是 {PXL[0]}'
               f'（{XL[0]} 那期从未发布）')
    for _n in _PR_NS:
        LATE_WHY[_n] = _lag_pr

    # ══════════════════ Exhibit 10 / 11：两条余额（柱 + 单月同比）═══════════════════
    # 2026-09 的合并：原 Exhibit 10+11（融资余额柱 + 它的 y/y 折线）与 12+13
    # （客户现金柱 + 它的 y/y 折线）各自并成一张，y/y 改画成次轴折线。
    # 合并前那两对是「同一列数据的水平值与同比分居两张图」，读者要在两张图之间来回对；
    # 合并后线上任一点就是这根柱相对 12 根柱之前的涨幅。
    # 左端不用裁：gs_bar 不属 DENSE，次轴走 `polyline(..., doSmooth=false)`，
    # 前 12 期的 null 直接断笔（不画、不补值），所以左段只有柱没有线。
    ex.append({
        'n': 10, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': XL, 'xstep': 12,
        'title': f'Customer margin balances at ${margin[-1]:,.1f}bn, {pctf(at(MG_MONO))} YoY '
                 f'and {pctf(mom(margin))} MoM',
        'ylab': 'Customer Margin Balances ($bn)',
        'ylab2': 'y/y, single month (%)',
        'legend': 'Customer Margin Balances', 'values': L(margin),
        'yoy': yoy_rhs(MG_MONO, 'y/y, single month (RHS)'),
        'note': f'公司披露的期末余额，{XL[0]} 起逐月；次轴金色折线是它的<b>单月同比</b>'
                '（本月末 ÷ 去年同月末 − 1）。融资余额不是高增速指标，m/m 基本是噪音，'
                '所以图上给的是 y/y 而不是环比。'
                f'绝对水平：{peak_zh(mg_all)}；相对客户权益的占比是另一回事 —— 当期 '
                f'{mg_share[-1]:.1f}%，{ALL[0]} 以来的区间 {np.nanmin(mg_share):.1f}%–'
                f'{np.nanmax(mg_share):.1f}%，见 ⟨nav:share⟩。',
    })
    _n_mg = ex[-1]['n']
    # 存量：次轴那条线是**点对点**同比（CONTRACT §6.1 第 2 条），把 12 个月末的
    # 余额加起来不是任何东西，滚动口径对它根本不存在 —— 所以它不欠第 3 条那笔
    # 「换口径的代价」（第 3 条自己把范围限定在流量）。登记在这里，好让下面那道
    # 「流量图必须逐图印代价」的护栏知道本图为什么没有那一段。
    STOCK_YOY[_n_mg] = '融资余额是月末存量'

    ex.append({
        'n': 11, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': XL, 'xstep': 12,
        'title': f'Client cash at ${credits[-1]:,.1f}bn, {pctf(at(CR_MONO))} YoY '
                 f'and {pctf(mom(credits))} MoM',
        'ylab': 'Total Client Cash ($bn)',
        'ylab2': 'y/y, single month (%)',
        'note': 'Client cash = total client credit balances, including insured bank deposit sweeps。'
                f'{XL[0]} 起逐月；次轴金色折线是它的<b>单月同比</b>。'
                f'客户现金的 m/m 绝对值中位数只有 '
                f'{float(np.nanmedian(np.abs(np.diff(cr_all) / cr_all[:-1]))) * 100:.1f}%'
                f'（{XL[1]}–{XL[-1]} 全区间实测），所以次轴画 y/y 才有信息量。'
                f'绝对水平：{peak_zh(cr_all)}。',
        'legend': 'Total Client Cash', 'values': L(credits),
        'yoy': yoy_rhs(CR_MONO, 'y/y, single month (RHS)'),
    })
    _n_cr = ex[-1]['n']
    STOCK_YOY[_n_cr] = '客户现金是月末存量'

    # ══════════════════ Exhibit 12 / 13：长历史两张 lines ══════════════════════════
    # 两张都显式 zero_base：不给它时引擎走 y0 = min − 极差×5%，那是一次**没有任何标注的
    # 隐性截轴**，而它们的标题偏偏都在讲倍数／占比（Ex12 的「N.Nx」、Ex13 的两组端点）
    # —— 截过的轴会把这些幅度凭空放大，图与文字互相打架。
    # 两张都给 end_label：末点读数正是各自标题引用的那个数。
    ex.append({
        'n': 12, 'kind': 'lines', 'x': 'long', 'xlabels': XL, 'xstep': 12, 'fmt': 'f0c',
        'zero_base': True, 'end_label': True,
        'title': f'Client equity at ${eq_all[-1]:,.0f}bn, {eq_all[-1] / eq_all[0]:.1f}x the '
                 f'${eq_all[0]:,.0f}bn of {XL_LONG[0]}',
        'ylab': 'Client Equity ($bn)',
        'note': '公司披露值（期末口径，不含非客户余额）。'
                f'它是 Exhibit {_n_mg} / {_n_cr} 两条余额的分母，也是 NII 的规模基数。',
        'series': [{'name': 'Client Equity', 'color': 'NAVY', 'values': LN(eq_all)}],
    })

    # ⚠ 标题从前只给 pp 差、不给端点：「client cash 19.3%（-1.3pp over 12M）」—— 去年同月
    #   那个数图上一处都没有，−1.3pp 无从核对。更糟的是它与端点**减不出来**：两条腿都
    #   贴着四舍五入的边界（真值 −1.2501pp 印成 −1.3，而两个端点各按一位小数印出来是
    #   20.5 与 19.3，差 −1.2）。所以三个数一律由**同一份四舍五入后的值**导出，
    #   标题里的算术必须自洽；两位小数的真值与舍入差额写进图注、现算。
    _w16 = min(LAG, len(cr_share) - 1)
    _sg = lambda v: (v > 0) - (v < 0)
    _vb16 = {1: 'rose', -1: 'fell', 0: 'was unchanged'}

    def _leg16(s):
        """(去年同月, 当期, 差, 方向词)：四个都由同一份 .1f 值导出，读者当场能减出来。"""
        a, b = round(float(s[-1 - _w16]), 1), round(float(s[-1]), 1)
        d = round(b - a, 1)
        return a, b, d, _vb16[_sg(d)]

    _c0, _c1, _dc16, _vc = _leg16(cr_share)
    _m0, _m1, _dm16, _vm = _leg16(mg_share)
    _t16 = (f'Client cash {_vc} from {_c0:.1f}% to {_c1:.1f}% of client equity over the past '
            f'{_w16} months ({_dc16:+.1f}pp, vs. {cr_share[0]:.1f}% in {XL_LONG[0]}) '
            f'while margin loans {_vm} from {_m0:.1f}% to {_m1:.1f}% '
            f'({_dm16:+.1f}pp, vs. {mg_share[0]:.1f}% in {XL_LONG[0]})')
    # 停机兜底：两条 clause 的**方向词与两个端点**从原始序列重算（不复用 _leg16 的返回值），
    # 逐字对不上就让构建失败。上一版守的是「标题里有没有 Both」，那只覆盖「两条同向」
    # 这一件事；现在每一个印出来的读数都在守备范围内。
    for _nm, _s in (('Client cash', cr_share), ('margin loans', mg_share)):
        _a, _b = round(float(_s[-1 - _w16]), 1), round(float(_s[-1]), 1)
        _want = f'{_nm} {_vb16[_sg(round(_b - _a, 1))]} from {_a:.1f}% to {_b:.1f}%'
        if _want not in _t16:
            raise SystemExit(f'Exhibit 13 标题与数据对不上：期待子句 {_want!r}；实得 {_t16!r}')
    # 舍入差额也现算：写死「差 0.1pp」在两个端点恰好整除的月份就是假话。
    _rd = [abs(round(float(s[-1]), 1) - round(float(s[-1 - _w16]), 1)
               - (float(s[-1]) - float(s[-1 - _w16]))) for s in (cr_share, mg_share)]
    ex.append({
        'n': 13, 'kind': 'lines', 'x': 'long', 'xlabels': XL, 'xstep': 12, 'fmt': 'pct1',
        'zero_base': True, 'end_label': True,
        'title': _t16,
        'ylab': 'as % of client equity (%)',
        'note': '<b>这是比值，不是公司披露值</b>：分子分母都取自官方历史指标表同一张表内的 Client Credits / '
                'Client Margin Loans / Client Equity，两条的分母是同一列（期末客户权益），'
                '所以两个占比同口径、可直接比较。'
                f'<b>标题里那两个 pp 就是标题里两个端点相减</b>，不是另算的第三个数：'
                f'客户现金/权益 {ALL[-1 - _w16]} 的 {cr_share[-1 - _w16]:.2f}% → '
                f'{ALL[-1]} 的 {cr_share[-1]:.2f}%（真值 '
                f'{cr_share[-1] - cr_share[-1 - _w16]:+.2f}pp）、融资余额/权益 '
                f'{mg_share[-1 - _w16]:.2f}% → {mg_share[-1]:.2f}%（真值 '
                f'{mg_share[-1] - mg_share[-1 - _w16]:+.2f}pp）。'
                f'标题按一位小数印，与真值差 {max(_rd):.2f}pp / {min(_rd):.2f}pp —— 那是四舍五入；'
                '本页选的是「标题里三个数彼此减得出来」，不是「pp 那一位最准」。'
                f'历史最低：客户现金/权益 '
                f'{np.nanmin(cr_share):.2f}%（{ALL[int(np.nanargmin(cr_share))]}）、融资余额/权益 '
                f'{np.nanmin(mg_share):.2f}%（{ALL[int(np.nanargmin(mg_share))]}）。'
                f'两条绝对额（Exhibit {_n_mg} / {_n_cr}）与这里的占比是两件事：'
                f'融资余额{peak_zh(mg_all)}、客户现金{peak_zh(cr_all)}。'
                f'占比与 {_B_LAB} 年均相比：'
                f'客户现金/权益 {cr_share[-1]:.1f}% vs {_cr_b1618:.1f}%'
                f'（为其 {cr_share[-1] / _cr_b1618 * 100:.0f}%）、融资余额/权益 '
                f'{mg_share[-1]:.1f}% vs {_mg_b1618:.1f}%（为其 {mg_share[-1] / _mg_b1618 * 100:.0f}%）。',
        'series': [
            {'name': 'Client cash / client equity', 'color': 'NAVY', 'values': LN(cr_share)},
            {'name': 'Margin loans / client equity', 'color': 'MBLUE', 'values': LN(mg_share)},
        ],
    })
    NAV['⟨nav:share⟩'] = ex[-1]['n']

    # ── 页尾脚注要点名的几批图：**一律从建完的 `ex` 现算**，不在文案里手抄编号 ──
    # 这些名单从前是写死的图号串。写死的名单已经被撞过两次（2026-08 的合并、2026-09 的
    # 删并挪），任何一处漏改都会指到别的图上，而没有东西报错。
    def _exlist(ns):
        return ('Exhibit ' + ' / '.join(str(n) for n in ns)) if ns else ''

    _pr_ns = list(_PR_NS)                   # 画在新闻稿口径上的那几张（建图现场登记）
    _pr_span = (f'{_pr_ns[0]}-{_pr_ns[-1]}'
                if _pr_ns == list(range(_pr_ns[0], _pr_ns[-1] + 1))
                else '／'.join(str(n) for n in _pr_ns))
    _xl_of = {e['n']: (e.get('xlabels') or XL) for e in ex}
    # ⚠ 判据要与句子逐字对应。页尾那句说的是「覆盖**完整**的主窗口（N 个月逐月连续）」，
    #   所以判据就得是「这张的 xlabels 与主窗口逐格相同」，不能只比左端 —— 只比左端时，
    #   一张起点相同但右端更短的图会被算进「覆盖完整」，而没有东西会报错。
    # ⚠ 分堆的判据是**轴**，不是数据源：2026-09 之后新闻稿那四张与主窗口只差第一格，
    #   `xlabels == PXL` 已经不能把它们与同样裁掉首格的 Exhibit 3 分开（两个列表逐格相同）。
    #   所以「哪几张是新闻稿口径」改由建图现场登记（`_PR_NS`），而这里只按轴分堆。
    _ontime_ns = [e['n'] for e in ex if _xl_of[e['n']] == XL]
    _late_ns = [e['n'] for e in ex if _xl_of[e['n']][0] != XL[0]]
    _odd = [e['n'] for e in ex if e['n'] not in _ontime_ns and e['n'] not in _late_ns]
    if _odd:
        raise SystemExit(f'Exhibit {_odd} 的轴既不等于主窗口、左端又不比它晚（右端短了？）'
                         f'—— 页尾把 {len(ex)} 张分成「完整」与「左端更晚」两堆，'
                         f'出现第三种形状就必须先把那段话改对')
    # 左端晚了却没在建图现场登记理由 —— 宁可构建失败，也不要页尾少说一张。
    _unreg = [n for n in _late_ns if n not in LATE_WHY]
    if _unreg:
        raise SystemExit(f'Exhibit {_unreg} 的左端比主窗口 {XL[0]} 晚，'
                         f'但 LATE_WHY 里没有登记理由（见 ex = [] 处的说明）')
    # 理由相同的合并成一行（新闻稿那四张是同一句），并且用「——」而不是括号：
    # 登记的理由本身带括号，再套一层括号读者数不清层级。
    _late_groups = []
    for n in _late_ns:
        if _late_groups and _late_groups[-1][0] == LATE_WHY[n]:
            _late_groups[-1][1].append(n)
        else:
            _late_groups.append((LATE_WHY[n], [n]))
    _late_txt = '；'.join(f'{_exlist(g)} —— {why}' for why, g in _late_groups)

    _gsbar_ns = [e['n'] for e in ex if e['kind'] == 'gs_bar']
    _zb_ns = [e['n'] for e in ex if e.get('zero_base')]
    _zb_kinds = sorted({e['kind'] for e in ex if e.get('zero_base')})
    # ⚠ 截轴名单必须连**右轴**的 `yoy.ymax` 一起算。只看 ycap／yfloor 时，页尾会一边印
    #   「本页没有任何一张图设了截轴」，一边有一张图的右轴真的截在 +200% —— 而那句话
    #   没有任何东西在守。Exhibit 2 就是这种情况。
    _cap_ns = [e['n'] for e in ex if e.get('ycap') is not None or e.get('yfloor') is not None
               or (e.get('yoy') or {}).get('ymax') is not None]
    _nyears = len({k[:4] for k in ALL})
    _exn = {e['n']: e for e in ex}

    # ── 回填①：左端更晚的那几张，把登记的**根因**写进它自己的图注 ─────────────
    # 页尾原来声称「另外 N 张更晚，原因逐张写在各自图注里」，而 Exhibit 4 的图注里
    # 连「左端」二字都没有：它是 gs_bar（不属 mrwin.DENSE），`resolve().why` 返回空串，
    # 那句 `note += _w4.why` 什么也没加。Ex3/11/13 虽有 mrwin 那一段，但单腿时它的
    # `who` 退化成一个日期，印出来是「定住左端的是 12/17」这种同义反复 —— 登记在
    # LATE_WHY 里的真正理由一个字都没进图注。mrwin.py 是全站共用文件、本轮不许改，
    # 所以改法留在本页：把登记的那句话 append 进对应图注，然后**逐张核对，对不上就停机**。
    # 页尾那句话从此是被守住的，不是被相信的。
    for _n in _late_ns:
        _e = _exn[_n]
        _exl = _e.get('xlabels') or XL
        _k = len(XL) - len(_exl)                      # 比主窗口起点晚几期
        if LATE_WHY[_n] not in (_e.get('note') or ''):
            # mrwin 已经写过「本图左端截在 X」那一段的（DENSE 图型），这里不再重复左端，
            # 只补它没印出来的那半句：**数据上**为什么这几期不存在。
            _said = '本图左端截在' in (_e.get('note') or '')
            _e['note'] = (_e.get('note') or '') + (
                (f'<b>而那 {_k} 期本来就算不出来</b>：{LATE_WHY[_n]} —— '
                 f'不是截掉不看。' if _said else
                 f'<b>本图左端是 {_exl[0]}、比主窗口起点 {XL[0]} 晚 {_k} 期</b>：'
                 f'{LATE_WHY[_n]}，那 {_k} 期<b>算不出来</b>，不是截掉不看。'))
    _nowhy = [_n for _n in _late_ns if LATE_WHY[_n] not in (_exn[_n].get('note') or '')]
    if _nowhy:
        raise SystemExit(f'Exhibit {_nowhy} 的左端比主窗口 {XL[0]} 晚，LATE_WHY 里登记了理由，'
                         f'却没有写进它自己的图注 —— 页尾「原因逐张写在各自图注里」会变成假话')

    # ── 回填②：图注里的图号占位符 ⟨nav:…⟩（照 build/cme.py 的办法）──────────
    for _tag, _tn in NAV.items():
        _hit = 0
        for _e in ex:
            for _f in ('title', 'note', 'ylab'):
                if _tag in (_e.get(_f) or ''):
                    _e[_f] = _e[_f].replace(_tag, f'Exhibit {_tn}')
                    _hit += 1
        if _hit == 0:
            raise SystemExit(f'占位符 {_tag} 登记了图号 {_tn}，却没有任何一处用到 —— '
                             f'要么那句导航被删了，要么占位符敲错了')

    # ── 同比口径：全页只有一种，护栏也只剩一条 ─────────────────────────────
    # 2026-09 之前这里是一整套「建图时登记 KIND（flow/stock）→ 从标题与气泡里真印出来的
    # 口径标记反读 → 两者对撞不上就停机」的装置，服务的是「流量走滚动、存量走点对点」
    # 那条规则。规则没了，装置随之删除 —— 留着它只会守一条已经不存在的规则。
    #
    # 换上的是与新规则等价的那一条：**凡是画了同比的图，都必须在标题域里写明「单月」**。
    # 这不只是文案要求 —— `tools/check_yoy_caliber.py` 的 R4 判据就认这个
    #   （`_MOM_DECL` 扫 title / yoy.name / ylab2 / legend 四处，只写在图注里不算），
    # CONTRACT §6.6 把「单月同比没写进标题」列为 🟡。写不出来就停机，
    # 免得「页尾说全页单月、某张图上一个字都没有」这种事再靠人眼发现。
    _yoy_ns = [e['n'] for e in ex if e.get('yoy') and e['n'] not in RHS_NOT_YOY]
    _MOM_DECL_FIELDS = ('title', 'ylab2', 'legend')
    _undeclared = []
    for _e in ex:
        if not _e.get('yoy') or _e['n'] in RHS_NOT_YOY:
            continue
        _scope = ' '.join(str(_e.get(f) or '') for f in _MOM_DECL_FIELDS) + \
                 ' ' + str((_e.get('yoy') or {}).get('name') or '')
        if 'single month' not in _scope and 'single-month' not in _scope and '单月' not in _scope:
            _undeclared.append(_e['n'])
    if _undeclared:
        raise SystemExit(
            f'Exhibit {_undeclared} 画了次轴同比，但 title／ylab2／legend／yoy.name 里'
            f'一处都没写明是单月口径 —— CONTRACT §6.6 把这种情况列为 🟡，'
            f'tools/check_yoy_caliber.py 的 R4 也只扫这四处（只写在图注里不算）')
    # 逐图代价（CONTRACT §6.1 第 3 条）：凡是画**流量**同比的图，图注里必须有那一段
    # 实测代价，而且必须是登记簿里这一张自己的那一段。页尾另有一段定性的口径说明，
    # 但第 3 条写明「逐图是字面意思，页级不算数」—— 读者看某条金线时够不到页尾。
    # 谁欠这笔账现算：画了同比的图，减去右轴不是同比的（RHS_NOT_YOY）、
    # 减去存量的（STOCK_YOY，走第 2 条的点对点，对它不存在滚动口径）。
    # 新加一张流量同比图而忘了印代价 → 这里停机，不靠人眼发现。
    _ex_by_n = {e['n']: e for e in ex}
    _flow_yoy_ns = [n for n in _yoy_ns if n not in STOCK_YOY]
    _cost_missing = [n for n in _flow_yoy_ns
                     if n not in COST_NOTE
                     or COST_NOTE[n] not in str(_ex_by_n[n].get('note') or '')]
    if _cost_missing:
        raise SystemExit(
            f'Exhibit {_cost_missing} 画的是流量的单月同比，但图注里没有那段用本序列'
            f'自己实测的代价（逐月标准差／相邻月最大跳变带月份／两种口径符号相反的月份数）'
            f'—— CONTRACT §6.1 第 3 条要求逐图印，页尾那段不顶数。'
            f'补法：COST_NOTE[n] = mom_cost_zh(序列, 序列的月份键, 本图窗口) 再拼进 note')
    _cost_extra = sorted(set(COST_NOTE) - set(_flow_yoy_ns))
    if _cost_extra:
        raise SystemExit(
            f'Exhibit {_cost_extra} 印了「换口径的代价」那一段，但它们不是画流量同比的图'
            f'（存量走 §6.1 第 2 条的点对点，比率走第 4 条，两者都不欠这笔账）—— '
            f'印上去等于替一个对它们不存在的对照口径背书')

    # 反向护栏：页面上不许再出现任何滚动口径的措辞。全页改单月之后，残留一句
    # 「12 个月滚动」既是假话，又会让 check_yoy_caliber 的 R3 把本页判成混用。
    # ⚠ 唯一的豁免是 COST_NOTE 登记的那几段：§6.1 第 3 条**明令**要把滚动那一侧
    #   当对照量以数字印在图注里（页上一条线都不画）。所以这里先把登记在案的原文
    #   从 note 里剥掉再扫 —— 豁免的是「那一段」，不是「那张图」：同一张图的别处
    #   再冒出一句滚动措辞，照样停机。
    _ROLL_WORDS = ('12 个月滚动', '12个月滚动', '滚动合计', '滚动同比', '12M rolling', 'TTM')

    def _roll_scope(e, f):
        t = str(e.get(f) or '')
        c = COST_NOTE.get(e['n'])
        return t.replace(c, '') if (f == 'note' and c) else t

    _roll_left = sorted({e['n'] for e in ex for f in ('title', 'note', 'ylab', 'ylab2', 'legend')
                         for w in _ROLL_WORDS if w in _roll_scope(e, f)})
    if _roll_left:
        raise SystemExit(f'Exhibit {_roll_left} 的文案里还留着滚动口径的措辞'
                         f'（命中 {_ROLL_WORDS} 之一）—— 本页已改成全页单月，那是假话')

    # ── 「拿柱直接除就是线上这一点」这句承诺，逐图复核 ──────────────────────
    # 页尾对读者说的是「线上任一点就是这根柱相对 12 根柱之前的涨幅 —— 读者数得出来」，
    # 而本页有一张例外（柱是表内披露值、线是还原口径）。例外名单登记在 SPLIT_SRC，
    # 页尾从它现算；但**只登记不复核守不住这句承诺** —— 哪天某张图的柱与线换成了
    # 不同源的两列，页尾那句当场变成假话，而没有任何东西会响。
    # 所以这里拿 payload 自己复算一遍：用图上那些柱算「本柱 ÷ 12 根柱之前那根 − 1」，
    # 与图上那条线逐点比，实测对不上的那一批必须与登记簿**逐号相等**。
    # 容差 0.05pp：柱与线都是 round(…, 6) 之后的数，真不同源的差是十几个 pp 起。
    def _bar_over_bar(e):
        # 回 (可核月数, 对不上的月数)。可核 = 柱、12 个月前那根柱、线三者都有值。
        v, y = e['values'], ((e.get('yoy') or {}).get('values') or [])
        ok = bad = 0
        for i in range(12, min(len(v), len(y))):
            a, b, ln = v[i], v[i - 12], y[i]
            if a is None or b is None or ln is None or not b:
                continue
            ok += 1
            if abs((a / b - 1) * 100 - ln) > 0.05:
                bad += 1
        return ok, bad

    _split_found, _uncheckable = {}, []
    for _e in ex:
        if not _e.get('yoy') or _e['n'] in RHS_NOT_YOY:
            continue
        _ok, _bad = _bar_over_bar(_e)
        if not _ok:
            _uncheckable.append(_e['n'])
        elif _bad:
            _split_found[_e['n']] = (_ok, _bad)
    if _uncheckable:
        raise SystemExit(
            f'Exhibit {_uncheckable} 画了同比，但图上一个「柱、12 个月前那根柱、线'
            f'三者都有值」的月份都没有 —— 页尾那句「拿柱直接除就是线上这一点」在这张图上'
            f'无从复核，那句承诺就不该替它作数')
    if set(_split_found) != set(SPLIT_SRC):
        raise SystemExit(
            f'「柱与线不同源」的例外名单对不上：登记簿 SPLIT_SRC 是 {sorted(SPLIT_SRC)}，'
            f'而拿 payload 复算出来的是 {sorted(_split_found)}。'
            f'要么某张图的柱与线换成了不同源的两列（登记它，并在它自己的图注里说明），'
            f'要么登记簿里躺着一张早已同源的图（删掉它）—— 页尾那句「线上任一点就是'
            f'这根柱相对 12 根柱之前的涨幅」按登记簿现算，名单不对就是对读者说假话')

    # 页尾那两句「柱与线可以直接除」「例外只有这一张」的措辞，从上面两本登记簿现算
    # （名单与实测数都不写死：写死的名单被撞过两次，而实测数下个月就会变）。
    _same_src_ns = [n for n in _yoy_ns if n not in SPLIT_SRC]
    _split_txt = ''.join(
        f'<b>Exhibit {n} 是例外</b>（构建期实测：{_split_found[n][0]} 个可核月里 '
        f'{_split_found[n][1]} 个月柱除柱与线对不上，全是口径调整月）：{why} —— '
        f'所以那一条线拿柱直接除是除不出来的，该图图注里把调整月逐月点了名。'
        for n, why in sorted(SPLIT_SRC.items()))

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
    # 汇总表的 y/y 列恒等于表内算术「本月 ÷ 去年同月」——读者拿第一列除第三列就能验算。
    # 2026-09 全页统一单月口径之后，它与各图次轴那条线是**同一个数**，不再需要在组标题上
    # 挂一条「本列是单月口径」的尾巴去与别处区分（页尾口径说明里说一次就够）。
    srows, blank_why = [], []
    for grp, lab, arr, d, pre, mode, inv in SUM_ROWS:
        if lab is None:
            srows.append({'kind': 'group', 'label': grp})
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

    month_name = datetime.date(ty, tm, 1).strftime('%B %Y')

    # 期货费用比例的脚注句：现算，且**必须点名是哪一期的读数**。缓存里每一期都不一样，
    # 只印一个光秃秃的百分数会被当成公司的固定口径（页尾从前那个写死的 56% 就是这样读的）。
    # 解析不到就一个数字都不印 —— 宁可少一句，也不能拿别的月份的读数顶上。
    _ff = sorted(v for v in FUT_FEE.values() if v is not None)
    # ⚠「每月都在动」是个**可数的**全称断言，而它自己引用的这批读数当场证伪它：
    #   2026-08-19 实测 14 期里有 4 个环比与上月完全相同（7/25→8/25 都是 57%、
    #   2/26→3/26→4/26 连着三期 58%、5/26→6/26 都是 56%）。方向没错（写死一个百分数会
    #   过期），但频次不能拍脑袋 —— 改成现算：相邻两期**都**解析到才算一个环比，
    #   免得把「没变」和「那个月没解析到」混成一件事。
    _ffs = [FUT_FEE[m] for m in PWIN]
    _ff_pairs = [(a, b) for a, b in zip(_ffs, _ffs[1:]) if a is not None and b is not None]
    _ff_moves = sum(1 for a, b in _ff_pairs if a != b)
    if FUT_FEE.get(target) is not None:
        fut_fee_txt = (f'公司在 {month_name} 新闻稿里估计交易所／清算／监管费用约占期货佣金的 '
                       f'<strong>{FUT_FEE[target]:g}%</strong>'
                       + (f'（该比例<strong>逐月披露、不是固定口径</strong>：入库的 '
                          f'{PXL[0]}–{PXL[-1]} 共 {len(_ff)} 期落在 {_ff[0]:g}%–{_ff[-1]:g}% 之间，'
                          f'{len(_ff_pairs)} 个月环比里 {_ff_moves} 个变了、'
                          f'{len(_ff_pairs) - _ff_moves} 个与上月持平）'
                          if len(_ff) >= 2 and _ff[0] != _ff[-1] else '')
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
                f'CPT 与分产品明细来自月度新闻稿（另一张表 <code>series/ibkr_pr.csv</code>，'
                f'{PXL[0]} 起 {len(PR)} 期），本表只收官方历史指标表里的列，'
                '好让读者拿着官方那份 PDF 逐格对数；佣金那几个数在 '
                f'Exhibit {_pr_span} 上。'
                f'<br><b>本表的 y/y 列 = 本月 ÷ 去年同月 − 1</b>，与本页每一张图的次轴同比'
                '<b>同口径、同一个数</b>（全页只有单月同比，见页尾口径说明）。'
                '它恒等于表内算术（第一列 ÷ 第三列），读者可以直接验算。',
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
    #    实测决定，**本页不自己判、也不改 mrwin**。窗口是全历史，这一步是必需的：
    #    一百多根柱塞进半栏卡片每根不到 3px（CONTRACT 的 `full` 字段那一行就是这么写的）。
    #    已经显式写了 xstep 的图（长历史一律 12，好让标签落在每年同一个月）它不会覆盖。
    #
    # ── 已知残留：几张 gs_bar 的柱顶数值标签超预算 —— **判 KEPT，不回退窗口** ──
    # 现象：`mrwin.label_clash()` 量出末柱的数值标签比预算宽两三个像素。当场复核
    #   （cd build 之后整段粘贴）：
    #     python3 -c "import mrwin,json;s=open('../data/ibkr.js',encoding='utf-8').read();\
    #     [print(e['n'],e['kind'],round(mrwin.label_clash(e)['over'],2),\
    #     round(mrwin.label_clash(e,False)['over'],2)) for e in \
    #     json.loads(s[s.index('{'):s.rindex('}')+1])['exhibits'] \
    #     if mrwin.label_clash(e) and mrwin.label_clash(e)['over']>0]"
    #   末两列 = 现状（通栏）与反事实（半栏）的超支。**具体数字不抄进注释**：
    #   哪几张、超多少，随数据、随图型、随有没有次轴（次轴把右边距从 14 撑到 56）逐月变，
    #   抄下来下个月就是假话。这里记的是**怎么复核**，不是一句结论。
    # 三条不动它的理由：
    #   ① 通栏是在**减轻**它，不是造成它 —— 上面那条命令的两列就是证据（半栏那一列
    #      恒大于通栏那一列）。真要清零只能把窗口缩回十几个月，那与「数据只要存在就必须
    #      从 2016-01 画起」直接冲突。
    #   ② 页面上有没有真的压到字，以 `python3 tools/visual_qa.py --page ibkr` 为准
    #      （TEXT_OVERLAP 底噪 8px²）。**那是跑出来的结论，不是一条永远成立的话**，
    #      改完图必须重跑；本轮改完两个视口都是 🔴0 🟡0 🔵0。
    #   ③ 真要收口只能改 `assets/charts.js` —— 34 页共用的渲染层，本页无权改；而它已经
    #      自带兜底：数值标签真的压上刻度时删掉**那一根**刻度（1px 容差、至少留 2 根），
    #      见 charts.js 里处理 `data-tick` 的那一段（grep 「不做预防性删除」）。
    mrwin.layout_all(ex)
    table = {
        'n': _ens[-1] + 1, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）',
        'idx': '月份', 'cols': [[lab, key] for lab, key, _ in TCOLS], 'rows': trows,
    }

    # 抬头一律 YoY + MoM 并列。原来只写 YoY —— 改这行的那个月几条 YoY 恰好全是正的，
    # 抬头看上去一片大好，而同月净新增与 cleared DARTs 的 MoM 都在两位数下跌，
    # 要翻到 Exhibit 1 汇总表才看得到。抬头是多数人唯一会读的一行，不能只挑好消息。
    # （那个月的具体读数不抄进注释：每个月都会变，抄了下个月就是假话；而这条规矩不变。）
    # 同时补上人均年化 DART：抬头列的这六个读数里只有它是结构性下行（Exhibit {_n_ann}
    # 讲的就是它；页上另有那两条占比也在长期下行，所以「全页唯一」是句假话），
    # 抬头里一个字都没有，等于把最该看的那条曲线藏起来。
    # 2026-09 起全页只有一种同比口径，所以抬头里的 YoY 不再逐个挂口径标签
    # （从前挂「·12M滚动」「·单月」是因为两种并存，光秃秃的 YoY 会让读者核不上）。
    headline = (f'净新增账户 {net_new[-1]:.1f}k（{pctf(at(NN_MONO))} YoY，{pctf(mom(net_new))} MoM） · '
                f'cleared DARTs {cleared[-1]:,.0f}k（{pctf(at(CL_MONO))} YoY，{pctf(mom(cleared))} MoM） · '
                f'人均年化 DART {ann_dart[-1]:.0f}x（{pctf(at(AN_MONO))} YoY，{pctf(mom(ann_dart))} MoM） · '
                f'CPT ${cpt[-1]:.2f}（{pctf(mom(cpt))} MoM） · '
                f'融资余额 ${margin[-1]:.1f}B（{pctf(at(MG_MONO))} YoY，{pctf(mom(margin))} MoM） · '
                f'客户现金 ${credits[-1]:.1f}B（{pctf(at(CR_MONO))} YoY，{pctf(mom(credits))} MoM）')
    hub = (f'净新增 {net_new[-1]:.0f}k（{pctf(at(NN_MONO))} YoY）、'
           f'cleared DARTs {cleared[-1]:,.0f}k（{pctf(at(CL_MONO))} YoY）')

    payload = {
        'ticker': 'ibkr',
        'tracker': 'Interactive Brokers Group (IBKR): Monthly Brokerage Metrics',
        'title': f'Monthly Brokerage Metrics — {month_name}',
        'data_through': target,
        'through_label': month_name,
        'subtitle': (f'{month_name} update — Exhibits {ex[0]["n"]}–{ex[-1]["n"]}, '
                     f'recreated in Goldman Sachs GIR exhibit '
                     f'format from IBKR company data · 主窗口 {XL[0]} – {XL[-1]}'
                     f'（{len(XL)} 个月全历史）· 全页同比一律单月口径 · '
                     f'Exhibits {_pr_span} 起于 {PXL[0]}（官方第一份月度新闻稿）'),
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
            '<strong>数据源</strong>：IBKR 官网 IR 的两份 PDF，数值全部入库到 tracked 的 '
            '<code>series/</code>，本页只查表、不在构建时解析任何 PDF 数字 —— '
            f'① Historical Brokerage Metrics（每月更新，共 {_nyears} 个年度逐月数据，'
            f'落库 <code>series/ibkr.csv</code>，{ALL[0]} 起 {len(ALL)} 个月连续）；'
            f'② 各月度 Metrics 新闻稿（佣金与产品明细，历史表里没有这两列，'
            f'落库 <code>series/ibkr_pr.csv</code>，{PXL[0]} 起 {len(PR)} 期）。',
            '<strong>单位</strong>：历史指标表首个区块标注 “(in Thousands, except Trading Days)”，'
            '故账户数、净新增、DARTs、期权／期货合约数、股票成交股数均以<strong>千</strong>为单位；'
            '客户权益、客户现金、融资余额区块标注 “(in Billions)”。文末核对表保持官方原始单位，'
            '便于与披露逐条核对。',
            f'<strong>Cleared DARTs</strong>（Exhibit {_n_cl}）= Cleared avg. DART per account（年化）÷ 252 '
            '个交易日 × 期初与期末账户总数的平均值。这是券商研究里的标准还原口径，'
            '<strong>非公司直接披露值</strong>，故图标题一律以 Implied 打头。'
            f'它与公司披露的 Total Client DARTs 之间的差额画在 Exhibit {_n_td} 的右轴上。',
            f'<strong>Commission revenue/day</strong>（Exhibit {_n_cd}）= cleared DARTs（千笔/日）× '
            '单笔清算订单平均佣金（$/笔）<strong>÷ 1,000</strong> → 百万美元/日（$mn/day）。'
            '要得到月度总额还需再乘当月官方交易日数。',
            f'<strong>Product DARTs</strong>（Exhibit {_n_pd}）= 当月成交量 ÷ 平均订单规模 ÷ 美股交易日数。'
            f'三段合计约为披露 Total Client DARTs 的 {np.nanmean(cov_prod):.0f}%'
            f'（{PXL[0]}–{PXL[-1]} 均值），即本图口径接近 cleared 而非 total。',
            '<strong>佣金口径</strong>：新闻稿「Key products」表两列分别是 <em>Average Order Size</em>'
            '（平均订单规模，股／张）与 <em>Average Commission per Cleared Commissionable Order</em>'
            '（单笔清算订单平均佣金，$，含交易所、清算与监管费用）。<strong>不是每股／每张单价。</strong>'
            + (f'<b>后一列的口径在 {PWIN[_cpt_brk]} 改过</b>：此前是 per cleared '
               '<em>client</em> order，此后是 per cleared <em>Commissionable</em> Order '
               '—— IBKR LITE 上线后免佣订单退出分母。口径名逐月存在 '
               '<code>series/ibkr_pr.csv</code> 的 <code>cpt_basis</code> 列里，'
               f'Exhibit {_pr_span} 上那条红色竖虚线由它现算，本页不写死日期。'
               if _cpt_brk is not None else ''),
            '<strong>期货</strong>含期货期权；' + fut_fee_txt,
            '<strong>账户口径调整</strong>：历史指标 PDF 的 Notes 段披露过三次一次性调整'
            '（2025-03 escheat 13.3k、2025-09 一家 introducing broker 撤出 38.8k、'
            f'2024-11 Total Accounts 下调 9.1k）。Exhibit {_n_nn} 的<b>柱</b>画表内披露值，'
            + (f'落在窗口内的净新增调整月（{"、".join(mk2)}）以<strong>斜纹柱</strong>标出'
               f'（悬停有说明）；原先另在 x 轴标签上挂 †，窗口拉到 {len(XL)} 个月后标签要抽稀、'
               f'† 会静默消失，故取消；'
               if mk2 else '本次窗口内没有净新增调整月，故图上没有斜纹柱；')
            + f'而同一张图<b>次轴那条同比线</b>的分子分母一律用公司给的真实增长。'
            '解析器每月重新抓这段 Notes，出现未登记的调整会直接让构建失败。',

            # ── 同比口径：全页只有一种，说一次就够 ──
            # 2026-09 之前这里是一整段「本页有两种口径，逐处点名」的说明，配着一套
            # KIND 登记 + 反读对撞的装置。规则改成「全站单月」之后，那一段连同装置一并删除。
            # 现在这条只回答两个问题：口径是什么、怎么核。**不替口径辩护**
            # （CONTRACT §6.1 第 3 条：口径是所有者定的，这里该说的是代价，不是理由）。
            f'<b>⚠ 同比口径：全页只有一种 —— 单月同比</b>（本月 ÷ 去年同月 − 1）。'
            f'画了同比次轴的是 {_exlist(_yoy_ns)} 这 {len(_yoy_ns)} 张，'
            '与下方汇总表的 y/y 列<b>同口径、同一个数</b>，读者拿表里第一列除第三列就能验算。'
            '<b>这就是本站的口径，不是本页的偏离</b>：<code>build/CONTRACT.md</code> §6 规定'
            '全站同比一律单月 —— 流量按 §6.1 第 1 条走单月同比、存量按第 2 条走点对点同比，'
            '在本页两者落到同一个式子上；页上<b>一条 12 个月滚动合计的同比都没有</b>。'
            f'本页画同比的图都是「柱是当月水平值 + 线是它的单月同比」，其中 '
            f'{_exlist(_same_src_ns)} 这 {len(_same_src_ns)} 张的柱与线取自<b>同一列</b>：'
            '线上任一点就是这根柱相对 12 根柱之前的涨幅 —— 读者数得出来，不必信我们。'
            + _split_txt
            + '（哪几张是例外不是手写的：构建期拿本页 payload 自己复算一遍'
              '「本柱 ÷ 12 根柱之前那根」再与线逐点对，实测对不上的那一批必须与建图现场的'
              '登记簿逐号相等，对不上就让构建失败。）'
            '<b>代价逐图印在各自的图注里</b>，不只写在这里 —— CONTRACT §6.1 第 3 条要的'
            '三样（逐月标准差、相邻月最大跳变带月份、与 12 个月滚动口径符号相反的月份数）'
            f'全部拿那条序列自己实测：{_exlist(_flow_yoy_ns)} 画的是流量同比，'
            f'各自图注里都有一段；{_exlist(sorted(STOCK_YOY))} 画的是<b>存量</b>的点对点同比'
            '（§6.1 第 2 条），把 12 个月末的余额加起来不指代任何东西，对它不存在滚动口径，'
            '所以不欠这笔账。'
            '这一段是定性的补充：单月同比的分母是<b>去年那一个月</b>，'
            '一次性事件与季节性会被放大 —— '
            f'2020-03 至 2021-02 那一段就是活例（净新增账户的同比被疫情低基数顶到三位数，'
            f'Exhibit {_n_nn} 的右轴因此截了轴）。这类月份在图上是看得见的：'
            '截轴的点画成空心红圈并标出真值，账户口径调整月画成斜纹柱。',

            f'<strong>纵轴</strong>：{_exlist(_zb_ns)} 这 {len(_zb_ns)} 张 '
            f'<code>{"／".join(_zb_kinds)}</code> 图一律<strong>从 0 起</strong>。'
            '引擎默认的下界是「最小值 − 极差 5%」，那是一次没有标注的'
            f'隐性截轴，会把这几张标题里引用的倍数与降幅（{_y5g:.0f}% below／'
            f'{eq_all[-1] / eq_all[0]:.1f}x／{cr_share[0]:.1f}%→{cr_share[-1]:.1f}% 与 '
            f'{mg_share[0]:.1f}%→{mg_share[-1]:.1f}%）在视觉上凭空放大。'
            + ('本页没有任何一张图设了截轴（ycap／yfloor／次轴 ymax）。' if not _cap_ns else
               f'<b>本页设了截轴的是 {_exlist(_cap_ns)}</b>，截的是<b>次轴</b>（同比那条线）'
               f'而不是柱：不截的话疫情那一年的低基数尖峰会把其余十年压成贴着零线的一条平线。'
               '<b>截轴不删点</b> —— 超界的点画成空心红圈、真值红色竖排标在图顶。'),
            # ⚠ 这一条的首句在前几轮里换过两次皮，两次都是同一种假话：先是「本页**所有**
            #   取自 series/ibkr.csv 的图现在都从 1/16 起画」，后是「那 12 张**都**画在同一条
            #   主窗口轴上」—— 而其中有几张既不在那条轴上、也不是逐月连续，紧接着的下一句
            #   自己就在列它们。所以这一版首句里一个「都」字都不留：只印现算的计数与名单，
            #   读者对着页面能一张一张数。
            f'<strong>窗口</strong>：<b>{len(ex)} 张图里，{len(_ontime_ns)} 张覆盖完整的主窗口 '
            f'{XL[0]}–{XL[-1]}（{len(XL)} 个月逐月连续）：{_exlist(_ontime_ns)}</b>。'
            + ((f'另外 {len(_late_ns)} 张的左端更晚。每一张的根因都在建图现场登记，'
                f'并回填进它<b>自己的图注</b>——登记了却没进图注就让构建失败，'
                f'所以这句话不是承诺而是判据：{_late_txt}。')
               if _late_ns else
               f'这 {len(ex)} 张的左端当前正好都是 {XL[0]}。')
            + '<b>左端裁到哪一期</b>由全站共用的 <code>build/mrwin.py</code> 判，本页不另写一套；'
              '<b>根因文字</b>登记在本页：mrwin 只为它的 <code>DENSE</code> 图型'
              '产出左端说明，非 DENSE 的图型拿到的是空串。'
            + (f'<b>{"、".join(PR_GAPS)} 是 Exhibit {_pr_span} 上的缺口</b>：'
               '官方那期月度新闻稿从来没发过（下载端点对不存在的文件返回 200 + 0 字节，'
               '实测过十几种文件名），所以那一格留空 —— 不补 0、不插值、不拿邻月顶上。'
               if PR_GAPS else '')
            + 'Exhibit 1 的 3Y %ile 取近 36 个月；'
            f'文末核对表刻意保持 {len(TWIN)} 行（它是对数用的表，不是图）。'
            '窗口一律从数据最新月倒推，不依赖构建当天的日期。',
            'Exhibits 14-17 of the original Goldman Sachs note (IBKR app downloads and MAU) rely on '
            'proprietary Sensor Tower data and cannot be updated from public company disclosures; '
            f'本站这 {len(ex)} 张的编号是自己排的，<b>与原 note 的图号没有任何对应关系</b> —— '
            '本页的图集与原 note 只是版式相同，内容各排各的（本站的编号在 2026-08 与 2026-09 '
            '各变过一次，任何「本站 ExN = 原 note ExN」的读法都不成立）。',
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
    # 图号占位符必须全部兑现：漏一个就会把 ⟨nav:…⟩ 原样印到页面上。
    # （回填在 ex 里做，这里是最后一道 —— 防的是有人把占位符写进 payload 的别处。）
    _resid = json.dumps(payload, ensure_ascii=False)
    if '⟨nav:' in _resid:
        _i = _resid.index('⟨nav:')
        raise SystemExit(f'payload 里还残留图号占位符：…{_resid[max(0, _i - 60):_i + 40]}…')
    payload_guard.write_dash(path, payload, 'ibkr')

    print(f'目标月 {target} | 主窗口 {WIN[0]} → {WIN[-1]}（{len(WIN)} 个月全历史）| '
          f'新闻稿窗口 {PWIN[0]} → {PWIN[-1]}（{len(PWIN)} 格，其中 {len(PR)} 期有数据）'
          + (f' | 官方没发那期、图上留缺口：{PR_GAPS}' if PR_GAPS else ''))
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
