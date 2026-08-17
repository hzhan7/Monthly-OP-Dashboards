# -*- coding: utf-8 -*-
"""Charles Schwab (SCHW) 月度 Activity Report —— 网页看板 payload 生成器。

把 build/build_schw.py（matplotlib → PDF）里的每一张 exhibit 逐张移植成
data/schw.js 里的一个 exhibit 对象。图序、编号、标题文案、图注、截轴设置照搬原 deck。

模版来源（与 PDF 版同）：
  · Goldman Sachs「SCHW First Take」Exhibit 2 的**恒等式滚存桥**
    （期初 BOP + 净新增 + 市值变动 = 期末 EOP）—— 让月度数据可无损累加到季度，
    是「用月度抢跑季报」的地基，本页的 Exhibit 5 即此图。
  · Goldman Sachs「LPLA monthly metrics」Exhibit 1 的口径规矩：**流量类不算环比百分比，
    改用年化有机增长率**（当月净新增 x 12 / 上月末资产），本页 Exhibit 4 采用。
  · GS「IBKR Monthly」的成对图法（水平柱 + 均线 + YoY/MoM 气泡 ⇄ 变化率曲线）。

数据源：series/schw.csv（Schwab Monthly Activity Report，次月 12-14 日）、
        series/schw_avg_margin.csv（2020-04 至 2025-12 的平均融资余额，之后停发）、
        series/fee_rates.csv（季报口径的生息资产与 NIM）。
季末月（3/6/9/12）无独立月报，该月数值取自当季季报，故序列连续。

所有数值与格式化都在这里算完，页面不做任何计算。构建日期只写文件首行注释，
不进 payload —— 进了 payload，monthly_run 的「data 有没有实质变化」检查会永久失效。
"""
import datetime
import inspect
import json
import os
import re

import numpy as np
import pandas as pd

import brief as B     # 页顶 ~300 字总结的共享规则库（R1-R6），只算事实不出文字
import payload_guard
import pctile          # 汇总表 3Y %ile 的唯一实现，各页不再各写各的（见该模块 docstring）
import yoy             # 同比口径的唯一实现（build/yoy.py）：本页不再自己写一份滚动同比

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')


def _source_dates():
    """按路径加载仓库根的 source_dates.py —— 本文件是 `python3 build/schw.py` 跑的，
    sys.path 上只有 build/，裸 import 会 ModuleNotFoundError。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SRC = 'Source: Schwab Monthly Activity Reports and quarterly reports'
QNOTE = ('Quarter-end months (Mar/Jun/Sep/Dec) have no standalone monthly report; '
         'those values come from the quarterly release')


# ────────────────────────────── 读数据 ──────────────────────────────
def month_index(s):
    return pd.PeriodIndex(s, freq='M')


df = pd.read_csv(os.path.join(SERIES, 'schw.csv'))
df['month'] = month_index(df['month'])
df = df.set_index('month').sort_index()
for c in df.columns:
    df[c] = pd.to_numeric(df[c], errors='coerce')

NEED = ['core_nna_usdbn', 'total_client_assets_usdbn', 'new_brokerage_accounts_k',
        'dats_k', 'margin_balances_usdbn']
missing = [c for c in NEED if c not in df.columns]
if missing:                                   # 规矩 5：失败要响，不静默写 NaN 上线
    raise SystemExit(f'series/schw.csv 缺列: {missing}')


def assert_monthly(index, src):
    """月份必须逐月连续 —— 缺一个月不是「少一根柱」而是三重污染：
    (1) 下面 assets.diff() 会把两个月的资产变动全记到后一个月，Exhibit 5 恒等式桥的
        轧差项直接翻倍，缺月那笔核心净新增凭空消失；
    (2) organic_growth_ann 的分母 assets.shift(1) 变成两个月前的存量；
    (3) 不相邻的两期被画成相邻柱（CONTRACT §5.3）。
    tail() 的 dropna() 只去得掉 NaN 值，看不见整行缺失，拦不住这些。
    所以按 §5.5 在这里响：位置必须早于任何按「相邻行」而非按日期做的推导。
    """
    idx = list(index)
    gaps = [(str(idx[i - 1]), str(idx[i])) for i in range(1, len(idx))
            if (idx[i] - idx[i - 1]).n != 1]
    if gaps:
        raise SystemExit(f'{src} 月份不连续: {gaps}')


assert_monthly(df.index, 'series/schw.csv')

LATEST = df.index[-1]
assets = df['total_client_assets_usdbn']
nna = df['core_nna_usdbn']

# ── core NNA 的口径断点（CONTRACT §5.2：断点必须画出来，不能只写图注）──
# 官方脚注原文：单一客户异常流入的剔除门槛「generally greater than $25 billion beginning
# in 2025; $10 billion in prior periods」——2025-01 起生效，且月报不重述历史，所以断点
# 左右两侧确实不可比。凡是画 core NNA 或其派生量（年化有机增速）的图都要带上。
BRK = pd.Period('2025-01', 'M')
BRK_Q = BRK.asfreq('Q')                       # 2025Q1，季度图用
# 断点竖排标签要短：引擎把它画在断点线左缘、从画布顶往下排，字越多压得越低，
# 「core NNA: $10bn → $25bn」这 23 个字符正好盖住断点左邻那根柱的数值标签
# （Dec-24 的 $61.4 被压掉末位，人眼审查把它读成了另一个数）。口径全称留在图注里，
# 线上只留最短的那句「谁变成了谁」。
BRK_LABEL = '$10bn → $25bn'


def brk_idx(index, period=BRK):
    """断点在该图窗口里的 x 索引；滚出窗口返回 None，payload 写 null、引擎整段不画。
    一律现算不写死索引 —— 窗口每月往前滚，硬编码的 7/8/80 下个月就指错月份。"""
    idx = list(index)
    return idx.index(period) if period in idx else None

# 恒等式滚存：期末 - 期初 = 净新增 + 市值变动  ⇒  市值变动为轧差项
df['asset_change'] = assets.diff()
df['market_gains'] = df['asset_change'] - nna
# 年化有机增长率 = 当月净新增 x 12 / 上月末资产（GS LPLA 的流量口径规矩）
df['organic_growth_ann'] = nna * 12 / assets.shift(1) * 100
# 同一个指标的**滚动 12 个月口径**：滚动 12 个月净新增 ÷ 12 个月前的月末客户资产。
# 分子已经是一整年的流量，不用再乘 12；分母取 12 个月前的期末存量，与分子的起点对齐。
# 2026-08-15 起它**不再上图**（Exhibit 4 的次轴已改回单月年化率的 pp 差），只留两个用途：
# 页尾「口径说明」里的对照读数，以及各图注里那句「这条线比滚动口径抖多少」的实测底数。
# 留着这一列不是历史包袱 —— 拿掉它，图注里的对比就成了无法核对的断言。
df['organic_growth_roll'] = nna.rolling(12).sum() / assets.shift(12) * 100
df['dats_mn'] = df['dats_k'] / 1000.0
df['assets_tn'] = assets / 1000.0
# ── 新开经纪账户：把官方明写的两笔并购搬账**净掉**（不是置空）──
# 月报脚注 (4) 原文（schw_nov2020_table.xlsx）：
#   "October 2020 includes 14.5 million new brokerage accounts related to the acquisition
#    of TD Ameritrade. May 2020 includes 1.1 million new brokerage accounts related to
#    the acquisition of the assets of USAA's Investment Management Company."
# 两笔都是官方自己给出的**确切数量**，所以这里做减法而不是把整个月扔掉：
#   2020-05  1,250 − 1,100 = 150 （左右邻月 201 / 201）
#   2020-10 14,718 − 14,500 = 218 （左右邻月 184 / 430）
# 减完的读数与邻月严丝合缝，说明这两笔就是全部的一次性成分。
# 本文件此前只处理了 2020-10、且用的是置空 —— 于是 2020-05 那 1,250k 一直当成真实开户量
# 画在图上（Exhibit 7 的柱、Exhibit 12 那条 2020 年线都被它顶出一个假尖峰），
# 而 2020-10 在逐年对照图上是个洞。两个毛病同一个根因：把「并购搬账」当成了「开户」。
ACQ_ACCOUNTS_K = {
    pd.Period('2020-05', 'M'): 1_100.0,     # USAA Investment Management
    pd.Period('2020-10', 'M'): 14_500.0,    # TD Ameritrade
}
df['new_acct_ex'] = df['new_brokerage_accounts_k'].astype(float)
for _p, _k in ACQ_ACCOUNTS_K.items():
    if _p in df.index:
        _raw = float(df.loc[_p, 'new_brokerage_accounts_k'])
        if _raw <= _k:                       # 官方口径变了/月份对错了 —— 响，别写负数
            raise SystemExit(f'{_p} 新开户 {_raw}k 不大于并购搬账 {_k}k，净额会是负数')
        df.loc[_p, 'new_acct_ex'] = _raw - _k

avgm = pd.read_csv(os.path.join(SERIES, 'schw_avg_margin.csv'))
avgm['month'] = month_index(avgm['month'])
avgm = avgm.set_index('month').sort_index()['avg_margin_balances_usdbn'].astype(float)
# 这条**月度平均**融资余额序列（2020-04 至 2025-12 后官方停发）2026-08-15 起不再上图：
# 它与 Exhibit 9 的**月末**口径不可接续，两条摆在一页上迟早被拼成一条 9 年的假长序列。
# 仍然读进来，是因为页尾「口径说明」要现算它的停发月份 —— 写死那个月份就是下一句假话。
assert_monthly(avgm.index, 'series/schw_avg_margin.csv')

# ── 为什么 SCHW 没有「量→收入」桥 ──
# Schwab 月报既不披露客户现金也不披露生息资产，唯一能当代理的是客户资产；
# 但生息资产/客户资产的比值在单边下行（趋势，不是噪音），把它当常数会造出假精度。
# 所以这里不搭桥，改把这个比值本身画出来 —— 它本身就是 NII 增长受限的原因。
_rates = pd.read_csv(os.path.join(SERIES, 'fee_rates.csv'))
_rates = _rates[_rates['company'] == 'SCHW'].copy()
_rates['q'] = pd.PeriodIndex(_rates['period'].str.replace('-', '', regex=False), freq='Q')


def rate_series(metric, scale=1.0):
    d = _rates[_rates['metric'] == metric]
    if not len(d):
        raise SystemExit(f'fee_rates.csv 里没有 SCHW/{metric}')
    return d.set_index('q')['value'].astype(float).sort_index() * scale


_iea = rate_series('avg_interest_earning_assets', 1e-3)      # USD_mn → $bn
_nim = rate_series('net_interest_margin')
_ca_q_cnt = assets.groupby(assets.index.asfreq('Q')).count()
_ca_q = assets.groupby(assets.index.asfreq('Q')).mean()
_ratio = (_iea / _ca_q.reindex(_iea.index) * 100).dropna()
# ── 起点那个不满 3 个月的季度要丢掉（Exhibit 10 改画全历史之后才暴露出来）──
# 月度序列自 2018-05 起，所以 2018Q2 的分母只由 5/6 两个月的客户资产求均，与其余季度
# 不是同一口径 —— 画在最左边就是一个凭空偏高/偏低的起点，而读者没有任何线索。
# **末**季的同一问题是允许的（季报总在季末前就发），由 _FEE_Q_MONTHS 那句图注交代；
# 首季没有对应的交代位置，所以直接截掉。现算不写死：起点一变该丢的季度自己就换了。
_R_HEAD = next((i for i, q in enumerate(_ratio.index) if int(_ca_q_cnt.get(q, 0)) >= 3), 0)
_Q_PARTIAL_HEAD = [str(q) for q in _ratio.index[:_R_HEAD]]
_ratio = _ratio.iloc[_R_HEAD:]
# lines_endlabels **不容忍 null**（docs/CHART_KINDS.md §1.2）：净息差缺任何一季都会
# 让该图首尾抛 TypeError 或把线画塌到 0。全历史窗口把这个风险从「窗口内碰巧都有」
# 变成「整条都得有」，所以在这里响，而不是等页面上出现一条塌到零的红线。
_nim_gap = [str(q) for q in _ratio.index if not np.isfinite(_nim.reindex([q]).values[0])]
if _nim_gap:
    raise SystemExit(f'fee_rates.csv 缺 SCHW 净息差: {_nim_gap}（Exhibit 10 不容忍空点）')
_bs_idx = pd.PeriodIndex([q.asfreq('M', 'end') for q in _ratio.index], freq='M')
_bs = pd.DataFrame({'iea_share': _ratio.values,
                    'nim': _nim.reindex(_ratio.index).values}, index=_bs_idx)

# ── 费率的「有效期」：本页月度数据每月前推，fee_rates.csv 每季才更新一次 ──
# 两张表节奏不同，所以「这张图用的是哪一季的费率、月度数据已经走到哪个月」这件事
# 长期存在，而且每个月的答案都不一样。它不是 bug，是口径 —— 但读者有权知道，
# 尤其当官方财报延迟、费率落后两个季度以上时。
# 下面四个量全部现算：写死季度号的话，下一季页面上就是一句假话
# （本文件已经为「过去 32 个季度单边降」返工过一次，同一个坑不踩第二遍）。
_FEE_USED_Q = _ratio.index[-1]                  # Exhibit 10 实际画到的最后一季
_FEE_HAVE_Q = _iea.index.intersection(_nim.index).max()   # 表里 SCHW 两个指标都齐的最新季
_LATEST_Q = LATEST.asfreq('Q')                  # 本页月度数据所在季
_FEE_LAG = (_LATEST_Q - _FEE_USED_Q).n          # 费率落后本页月度数据几个季度
# 末季的比值分母是该季客户资产的月度均值 —— 月份不满 3 个时它与前几季不是同一口径。
_FEE_Q_MONTHS = int(assets[assets.index.asfreq('Q') == _FEE_USED_Q].dropna().shape[0])
# 有月度数据、却还没有对应季度费率的那几个月（季度线在此处收尾，不外推）。
_FEE_TAIL = [p for p in df.index if p > _FEE_USED_Q.asfreq('M', 'end')]
# 「过期」判据：费率最新季比「本页数据月所在季的上一季」还老，即落后 ≥2 个季度。
# 落后 0–1 季只是节奏差（季报总在季末之后才发），落后 ≥2 季说明这张表没跟上，要明说。
_FEE_STALE = _FEE_LAG >= 2


# ────────────────────────────── 格式化零件 ──────────────────────────────
def mlab(p):
    return p.strftime('%b-%y')


def qlab(q):
    """季度 Period → 「2026-Q2」，与 series/fee_rates.csv 的 period 列写法一致，
    读者要回源核对时能直接在 CSV 里搜到这个字符串。"""
    return f'{q.year}-Q{q.quarter}'


def comma(v, d=0):
    return f'{v:,.{d}f}'


def money(v, d=0):
    """与 gsx._fmt(money='$') 一致：符号前缀直接拼在数字前（负数印成 $-113）。"""
    return '$' + comma(v, d)


def signed(v, d=0, unit='', sep=False):
    """带正负号的格式化，且**永远不产生「-0」**。

    -0.4% 按 0 位小数印出来是「-0%」：那是个纯格式化产物，读者会停下来想它是不是缺失值，
    也读不出到底是小跌还是没变。这里的做法是四舍五入后若变成 0 而原值不是 0，就自动
    多给一位小数（最多两位）；真的落到 0.00 以下才印无符号的 0。
    """
    for k in (d, d + 1, d + 2):
        t = f'{v:+,.{k}f}' if sep else f'{v:+.{k}f}'
        if float(t.replace(',', '')) != 0 or v == 0:
            return t + unit
    return (f'{0:,.{d}f}' if sep else f'{0:.{d}f}') + unit


def L(a):
    """序列 → JSON 数组；非有限值一律写 null（图与表都会断开，不画假点）。"""
    return [None if v is None or not np.isfinite(float(v)) else round(float(v), 6) for v in a]


def tail(s, win):
    """尾部连续 win 期（不足则全部）。dropna 后取尾段，避免把断档月并排画成相邻柱。"""
    s = s.dropna()
    return s.iloc[-win:]


# 同比的基数下限 = 序列绝对值中位数 × 这个系数；低于它就不算同比。
# gsx.lvl_bar 用的是 0.15，这里提到 0.25：SCHW 的 4 月与个别塌陷月是结构性极小月
# （2023-08 的 core NNA 只有 $4.9bn = 中位数的 16%），0.15 挡不住它，于是 2024-08
# 会算出 +569% —— 那说的是 2023-08 有多小，不是 2024-08 有多强，而且这一个点会把
# Exhibit 2 的次轴量程从 −32…+118 撑到 −32…+569，其余 22 个月全被压成一条平线。
# 这是「基数过小就放弃同比」这条口径判断的参数，按引擎契约本来就该在 Python 侧定。
YOY_BASE_MIN = 0.25


def _yoy_pair(a, b, scale, pct_series):
    """单个同比读数；算不出返回 None（图上断开、表里留空，不画假点）。"""
    if not (np.isfinite(a) and np.isfinite(b)):
        return None
    if pct_series:                                 # 比率序列 → 百分点差
        return a - b
    if b == 0 or a * b < 0 or abs(b) < YOY_BASE_MIN * scale:
        return None
    return (a / b - 1) * 100


def _scale_of(s):
    return float(np.nanmedian(np.abs(s.values))) or 1.0


def yoy_of(s, pct_series=False):
    """最新月同比：比率序列用百分点差，量/流量用百分比变化。口径同 gsx.lvl_bar。"""
    s = s.dropna()
    cur = s.index[-1]
    prev = cur - 12
    if prev not in s.index:
        return None
    return _yoy_pair(float(s.iloc[-1]), float(s.loc[prev]), _scale_of(s), pct_series)


# 窗口版的 yoy_series() / yoy_axis() / yoy_gap_note() 已删（2026-08-15）：
# 三者都按「尾部 win 期」切片，而本页所有图改画全历史之后，窗口不再是序列尾段的子集
# —— 有的图的柱与次轴取自不同长度的序列（Exhibit 7），切片对齐会整体错位一个月，
# 而那种错在图上看不出来。索引版的 ptp_yoy() / ptp_yoy_axis() / ptp_gap_note()（见下）
# 是唯一实现。留着窗口版只会让下一个人以为这页还有两条并行的同比路径。


# ────────────────── 同比口径：数值实现一律走 build/yoy.py ──────────────────
# 为什么流量类不再画单月同比：单月同比的分母是**去年那一个月**，而流量的月度分布本身
# 带季节性与时点噪音（缴税季、月末结算日落在周几、大额单笔转入的到账月份）。
# 分母越小，同一笔绝对变化被放大得越狠 —— 这不是业务信号，是除法的性质。
# 12 个月滚动合计把整整一年的流量加起来再比，分母是一整年，季节性自动对消。
# 本页实测：core NNA 的单月同比标准差是滚动口径的 4.6 倍，相邻月最大跳变 546pp vs 15pp，
# 25 个可比月里 5 个月两种口径符号相反（Aug-24 单月 +569%、滚动 −13%）——
# 这是全站审计里最严重的一处。具体数字一律现算后插进图注，不写死。
#
# ⚠ 一条更正（2026-08-07）：早先本文件写过「存量不许做滚动合计，因为 12 个月末值
# 相加不是任何东西，所以存量只能点对点」。**后半句是假的**：Σ12/Σ12′ 里的除数约掉，
# 12 个月滚动**合计**比恒等于 12 个月滚动**均值**比（共享模块 build/yoy.py 实测
# 两者差 2.3e-14），而「去年一整年的平均客户资产 vs 前年」是一个真实存在、
# 可以核对的量。**错的只是「合计」这个名字** —— 12 个月末余额相加确实不指代任何东西。
# 所以：存量**可以**平滑（走 yoy.ttm_mean_yoy，文案必须写「12 个月均值同比」，
# 绝不能写「合计」），本页仍然保留点对点，但理由必须是**本序列实测**出来的，
# 不能拿一句假的一般原理搪塞（见 stock_note）。
def roll_yoy(s):
    """12 个月滚动合计同比（%）—— 流量类。数值实现走共享模块，本页不另写一份。

    不 dropna：yoy.ttm 用 min_periods=12，缺月必须留成 NaN 的空位，
    压缩掉的话「最近 12 个月」会悄悄变成「最近 12 个有数的月」。
    """
    return yoy.ttm_yoy(s, yoy.FLOW)


def mean_yoy(s):
    """12 个月滚动**均值**同比（%）—— 存量类唯一说得通的平滑口径。

    数值上与滚动合计比完全相同（除数约掉），差别只在**说法**：对存量，
    「12 个月合计」不指代任何真实的量，「去年一整年的平均余额」才是。
    本页只拿它做反事实对照（stock_note 里那句「若改用均值口径会怎样」），
    图上画的仍是点对点。
    """
    return yoy.ttm_mean_yoy(s, yoy.STOCK)


def on(v, idx):
    """把一条 Series 对齐到某张图的 x 索引，缺的位置写 null。

    一律按**月份**对齐而不是按尾部切片：滚动口径天生比原序列少 11 个月，
    切片对齐会整体错位一年（那种错在图上看不出来，只会让人读出一个假趋势）。
    """
    return [None if p not in v.index or not np.isfinite(v.loc[p])
            else round(float(v.loc[p]), 6) for p in idx]


# roll_yoy_axis() / pp_axis() 已删（2026-08-15）：本页次轴不再画滚动口径，
# 而比率序列的点对点同比就是 pp 差，由 ptp_yoy_axis(pct_series=True) 一并处理。
# roll_yoy() 本身留着 —— 它还给 flow_stats() 与页尾的「对照读数」供数。


def ptp_yoy(s, pct_series=False):
    """点对点（单月）同比，按**月份**索引返回 —— 供 on() 对齐到任意窗口。

    与 yoy_series() 完全同口径（同一个 _yoy_pair、同一条 YOY_BASE_MIN 小基数护栏），
    差别只在返回形状：那个按「尾部 win 期」切片，只有当窗口正好是序列尾段时才对得上。
    本页改画全历史之后有两处对不上：
      · 柱与次轴取自**不同**序列的图（本页几张图的次轴走的是净除并购搬账之后的
        new_acct_ex，与原始披露列不是同一条），长度或缺值位置一旦不同，切片必错位；
      · dats/margin 这种起点晚于 df 的列，尾部切片会把 x 轴对齐搞成「最近 N 个有数的月」。
    错位在图上看不出来，只会让人读出一个假趋势（同 on() 的 docstring）。所以一律按月份对齐。
    """
    s = s.dropna()
    scale = _scale_of(s)
    idx, val = [], []
    for p in s.index:
        if (p - 12) not in s.index:
            continue
        v = _yoy_pair(float(s.loc[p]), float(s.loc[p - 12]), scale, pct_series)
        if v is None:                      # 基数过小/异号：不进序列，on() 会写成 null
            continue
        idx.append(p)
        val.append(v)
    return pd.Series(val, index=pd.PeriodIndex(idx, freq='M'), dtype=float)


def ptp_yoy_axis(s, idx, pct_series=False, ymax=None):
    """gs_bar 的次轴折线：**点对点（单月）同比**。给了它引擎就不画 12 个月均线。

    口径标签里写死「单月」：本页汇总表的 y/y 列、页顶 brief、各图次轴现在全是单月口径，
    但季度图（Exhibit 3）的右轴仍是季度合计同比，两者放在同一页上不点名就会被读成一个数。

    `ymax` = 右轴截轴上界（引擎的 rc.ymax）。语义与左轴的 ycap 完全一致：**截轴不删点**，
    超界的点钳到边界、画空心红圈、真值红色竖排标出。只在一两个基数效应尖峰把整条线
    压平时才给 —— 给了就必须在图注里点名是哪几个月、真值多少。
    """
    d = {'name': 'y/y (pp, 单月, RHS)' if pct_series else 'y/y (单月, RHS)',
         'color': 'GOLD', 'values': on(ptp_yoy(s, pct_series), idx),
         'yfmt': 'pp1' if pct_series else 'pct0'}
    if ymax is not None:
        d['ymax'] = float(ymax)
    return d


def ptp_gap_note(s, idx, what='去年同月基数过小'):
    """窗口内哪些月被小基数护栏放弃了同比 —— 图上是断口，必须交代。

    索引版的 yoy_gap_note()：全历史窗口下断口可能有十几个月，逐月点名会把图注撑爆，
    所以超过 6 个就只报个数与首尾，不再列全。月份一律现算，不写死。
    """
    s = s.dropna()
    scale = _scale_of(s)
    gaps = [p for p in idx
            if p in s.index and (p - 12) in s.index
            and _yoy_pair(float(s.loc[p]), float(s.loc[p - 12]), scale, False) is None]
    if not gaps:
        return ''
    who = ('、'.join(mlab(p) for p in gaps) if len(gaps) <= 6 else
           f'{mlab(gaps[0])} 至 {mlab(gaps[-1])} 之间的 {len(gaps)} 个月')
    return f'本窗口内 {who} 的{what}，同比作废，折线在该月断开。'


def caliber_stats(mono, roll, idx):
    """两种口径的实测对比，用于生成图注。返回 None 表示可比月份不足 3 个。

    ⚠ **必须先对齐到两种口径都算得出的同一批月份**再算标准差：滚动口径天然少掉头
    12 个月，不对齐就是拿两个不同样本比波动，样本效应会伪装成口径效应（本轮全站审计
    的方法论要求）。窗口再按 idx 截 —— 图上画的是哪几个月，就用哪几个月说话。
    """
    keep = [p for p in idx if p in mono.index and p in roll.index
            and np.isfinite(mono.loc[p]) and np.isfinite(roll.loc[p])]
    if len(keep) < 3:
        return None
    A, B = mono.loc[keep].astype(float), roll.loc[keep].astype(float)
    jump = lambda x: float(np.abs(np.diff(x.values)).max()) if len(x) > 1 else float('nan')
    return {'n': len(keep), 'sd_m': float(A.std(ddof=0)), 'sd_r': float(B.std(ddof=0)),
            'jump_m': jump(A), 'jump_r': jump(B),
            'flips': [(mlab(p), float(A.loc[p]), float(B.loc[p])) for p in keep
                      if A.loc[p] * B.loc[p] < 0],
            'lo_m': float(A.min()), 'hi_m': float(A.max()),
            'lo_r': float(B.min()), 'hi_r': float(B.max()),
            'cur_m': float(A.iloc[-1]), 'cur_r': float(B.iloc[-1]),
            'first': keep[0], 'last': keep[-1]}


def flow_stats(s, idx):
    """流量类：单月 vs 12 个月滚动合计，两者都走 build/yoy.py。"""
    return caliber_stats(yoy.mom_yoy(s, yoy.FLOW), roll_yoy(s), idx)


# roll_note() 已删（2026-08-15）：那段话的主语是「本图的次轴为什么是滚动口径」，
# 而次轴已经不是滚动口径了。它测出来的那组对比数字仍然有用（读者会问「这条线为什么
# 比上个版本抖」），改由 caliber_gap_note() 承担 —— 同一批统计量，换了个主语。


def stock_note(s, idx, what):
    """**存量**序列保留点对点（单月）同比的理由 —— 事实要说对，数字要现算。

    这段被更正过一次。旧版写的是「12 个月末值相加不是任何东西，所以存量只能
    点对点」，前半句对、后半句错：存量确实可以平滑，走的是 12 个月滚动**均值**同比
    （yoy.ttm_mean_yoy），它回答「去年一整年的平均余额 vs 前年」，是个真实的量。
    所以这里改成：先把「合计是假名字、均值是合法口径」说清楚，再用**本序列自己的
    实测数字**说明为什么这张图仍然不换。
    """
    st = caliber_stats(yoy.mom_yoy(s, yoy.STOCK), mean_yoy(s), idx)
    base = (f'次轴仍是<b>点对点（单月）同比</b>：{what}是<b>期末存量</b>。'
            '存量并非不能平滑 —— 合法的平滑口径是 <b>12 个月滚动均值同比</b>'
            '（去年一整年的平均余额 vs 前年；数值上等同于滚动合计比，除数约掉了），'
            '<b>但不能叫「12 个月合计同比」</b>：12 个月末余额相加不指代任何真实的量。'
            '本图不换口径的理由不是「不能换」，是实测下来换了没有收益：')
    if st is None:
        return base + '本序列两种口径都算得出的月份不足 3 个，暂时给不出对照数字。'
    ratio = st['sd_m'] / st['sd_r'] if st['sd_r'] else float('nan')
    return (base + f'对齐到同一批月份后（{st["n"]} 个月），点对点同比的标准差 '
            f'{st["sd_m"]:,.1f}pp、12 个月均值同比 {st["sd_r"]:,.1f}pp（{ratio:,.2f} 倍），'
            f'相邻月最大跳变 {st["jump_m"]:,.1f}pp vs {st["jump_r"]:,.1f}pp，'
            f'两种口径符号相反的月份 {len(st["flips"])} 个'
            + ('（一个都没有 —— 存量的分子分母都是时点数，不含日历效应，'
               '不像流量那样被小分母放大）' if not st['flips'] else '')
            + '。均值口径确实更平滑，但它按构造滞后约半年、回答的是另一个问题'
            '（「去年一年的平均水平」而不是「现在相对去年此刻」），'
            '而本图要回答的正是后者。噪声用轴范围解决。')


def ratio_note(what):
    """**比率**序列保留点对点同比的理由 —— 这一条是硬约束，不是选择。

    比率不许做 12 个月滚动均值：12 个月的占比做算术平均没有意义
    （每个月的分母不同），要「一年的平均占比」得用分母加权，即 Σ分子 ÷ Σ分母，
    那需要两条序列。共享模块 build/yoy.py 的 ttm_mean_yoy() 对 RATIO 直接抛
    CaliberError，正是为了拦住这一步。
    """
    return (f'次轴是<b>点对点（单月）同比的百分点差（pp）</b>。{what}是<b>比率</b>，'
            '12 个月滚动均值同比在这里是<b>非法</b>口径：把 12 个月的比率做算术平均没有意义'
            '（每个月的分母不同），要「一年的平均水平」必须用分母加权（Σ分子 ÷ Σ分母），'
            '那要两条序列而不是这一条。共享模块 <code>build/yoy.py</code> 的 '
            '<code>ttm_mean_yoy()</code> 对比率序列直接抛 <code>CaliberError</code>。'
            '所以比率只有点对点这一个口径，差异一律用 pp / bp，'
            '不算「百分比的百分比变化」。')


def mom_of(s, pct_series=False):
    s = s.dropna()
    if len(s) < 2:
        return None
    cur = s.index[-1]
    if (cur - 1) not in s.index:
        return None
    a, b = float(s.iloc[-1]), float(s.loc[cur - 1])
    if pct_series:
        return a - b
    if b == 0 or a * b < 0:
        return None
    return (a / b - 1) * 100


# prior12_avg()（Prior 12mo Avg.）已删：本页六张水平柱图改画次轴 y/y 之后没有任何图再用
# 均线，留着一个没人调的函数只会让下一个人以为这页还有均线。


def oval(v, unit='%', suffix=' y/y'):
    """图内气泡文案。百分点差保留 1 位小数 —— 0.79pp 四舍五入成「+1pp」会把口径读没了。"""
    if v is None or not np.isfinite(v):
        return None
    return signed(v, 1 if unit == 'pp' else 0, unit) + suffix


XL = [mlab(p) for p in df.index[-13:]]
XL_LONG = [mlab(p) for p in df.index]

# ── 窗口：全历史 ──────────────────────────────────────────────────────────
# 2026-08-15 起本页所有图一律画**全部可得历史**，不再用 25 个月 / 13 个月 / 14 个季度
# 这些倒推窗口。原始要求是「所有的图从 2016 年开始」，而 2016 年的数据**不存在**：
# Schwab 的月报附表走 CDN 直链（见 fetch/schw.py），2019-05 那一期是官网今天还挂着的
# 最老一份，它的 13 个月滚动表回溯到 2018-05 —— 更早的月报与季报附表 URL 全部 404
# （jan2016/jun2016/jan2017/may2017/jan2018/apr2018、q1_2017…q1_2019 逐个实测过）。
# 所以本页的「从头画起」= 从 2018-05 画起，各列还各有更晚的起点（dats/margin 是
# 2025-01）。**不补插、不外推**：按 §5.5，缺的月份就该是缺的。
ALL_N = len(df)


def xl(s, win):
    return [mlab(p) for p in tail(s, win).index]


# ────────────────────────────── Exhibit 1：汇总表 ──────────────────────────────
CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12


def cell(v, d, kind):
    if v is None or not np.isfinite(v):
        return '—'
    return money(v, d) if kind == '$' else (f'{v:,.{d}f}%' if kind == '%' else comma(v, d))


def chg(a, b, mode, d, kind):
    """m/m、y/y 单元格。比率类用 pp/bp（GS LPLA 规矩 2），不用百分比变化。"""
    if a is None or b is None or not (np.isfinite(a) and np.isfinite(b)):
        return {'v': ''}
    if mode == 'pp':
        v = a - b
        txt = signed(v * 100, 0, 'bp') if abs(v) < 1 else signed(v, 2, 'pp')
    elif mode == 'abs':
        v = a - b
        txt = ('$' if kind == '$' else '') + signed(v, max(0, d), sep=True)
    else:
        if b == 0 or a * b < 0:
            return {'v': ''}
        v = a / b - 1
        txt = signed(v * 100, 1, '%')
    return {'v': txt, 'cls': 'pos' if v > 0 else ('neg' if v < 0 else '')}


def pctile_cell(s):
    """近 36 个月分位，返回 (单元格, 留空原因)。原因只喂给表下注释，不进 payload。

    判据与算法全部走 build/pctile.py —— 本页不再自己实现。原因见该模块 docstring：
    分位是**口径**，同一条序列在两页判成两个结果（LPL 客户资产曾一页留空、一页印 100）
    的病根就是各写各的。旧的本地代理「36 个月里 ≥90% 的月环比不降」在这一页实测
    拦不住 margin balances（回放 11/11 个月全钉 100，代理只算出 88.2%），
    新判据改成「回放近 24 个月，≥70% 钉在极值就留空」，直接测这一列有没有区分度。
    """
    vals = [None if v is None or not np.isfinite(float(v)) else float(v) for v in s.values]
    txt, cls = pctile.cell(vals)
    if not txt:
        return {'v': ''}, pctile.why_blank(vals)
    return {'v': txt, 'cls': cls}, None


SUM_ROWS = [
    ('group', 'Client assets and flows'),
    ('row', 'Total client assets ($bn)', 'total_client_assets_usdbn', 0, '$', 'ratio'),
    ('row', 'Core net new assets ($bn)', 'core_nna_usdbn', 1, '$', 'ratio'),
    ('row', 'Annualised organic growth (%)', 'organic_growth_ann', 2, '%', 'pp'),
    ('row', 'Market gains, balancing item ($bn)', 'market_gains', 0, '$', 'abs'),
    ('group', 'Activity'),
    ('row', 'New brokerage accounts (k)', 'new_brokerage_accounts_k', 0, '', 'ratio'),
    ('row', 'Daily average trades (k)', 'dats_k', 0, '', 'ratio'),
    ('row', 'Margin balances ($bn)', 'margin_balances_usdbn', 1, '$', 'ratio'),
]

srows = []
dead_rows, short_rows, thin_rows = [], [], []   # 分位留空/样本偏短的行，喂表下注释
# 汇总表的 y/y 列**不换口径**，因为它恒等于表内算术「本月 ÷ 去年同月」：
# 读者拿第一列除第三列就能验算，换成滚动口径之后这一步会得出另一个数，
# 表内自相矛盾比口径混用更糟。改为在组标题上把口径写死，并在表注里把两种口径的
# 当期读数并排现算印出（见文件末尾 summary['note']）。
GRP_SUFFIX = '　·　y/y 列 = 单月口径（本月 ÷ 去年同月）'
for r in SUM_ROWS:
    if r[0] == 'group':
        srows.append({'kind': 'group', 'label': r[1] + GRP_SUFFIX})
        continue
    _, lab, col, d, kind, mode = r
    s = df[col]
    get = lambda p: (float(s.loc[p]) if p in s.index and np.isfinite(s.loc[p]) else None)
    c, p1, p12 = get(CUR), get(PRV), get(YAG)
    n_obs = int(s.dropna().iloc[-36:].shape[0])
    if n_obs < 36:
        thin_rows.append(f'{lab}（{n_obs} 个月）')
    pc, why = pctile_cell(s)
    if why:
        (short_rows if '样本不足' in why else dead_rows).append(lab)
    srows.append({'label': lab, 'cells': [
        {'v': cell(c, d, kind)}, {'v': cell(p1, d, kind)}, {'v': cell(p12, d, kind)},
        chg(c, p1, mode, d, kind), chg(c, p12, mode, d, kind), pc]})

summary = {
    'title': f'Schwab monthly activity summary — {mlab(LATEST)}',
    'heads': [mlab(CUR), mlab(PRV), mlab(YAG), 'm/m', 'y/y 单月', '3Y %ile'],
    'sep': 3,
    'rows': srows,
    # 'note' 在全部 exhibit 建完之后再填 —— 里面要引用「哪几张图真的画出了断点线」，
    # 那份编号必须从 payload 现读（见文件末尾 _BRK_DRAWN），不能写死。
}


# ────────────────────────────── Exhibit 2..14 ──────────────────────────────
ex = []

# ── 2026-08-15 的三处口径/版式变更（全页生效，逐条写在这里而不是散在各图注里）──
#
# (1) **窗口一律画全部可得历史**，不再倒推 25 个月 / 13 个月 / 14 个季度。
#     原始要求是「所有的图从 2016 年开始」，而 2016 年的数据在官方源上**不存在**
#     （见文件上方 ALL_N 处的实测记录）。所以「从头画起」= 从各列自己的第一个月画起：
#     月度主序列 2018-05、DATs 与月末融资余额 2025-01、季度费率表 2018Q3。
#     补插一段不存在的历史比截短更糟，§5.5 管的就是这件事。
#
# (2) **次轴同比一律改回点对点（单月）口径**，12 个月滚动合计同比整页不再出现。
#     此前流量类（核心净新增 / 新开账户 / 有机增速）画的是滚动口径，理由是实测更稳。
#     改回单月是要求，代价必须写在图注里而不是留给读者自己撞上：单月同比的分母是
#     **去年那一个月**，流量的月度分布带季节性与时点噪音，分母越小同一笔绝对变化被
#     放大得越狠。所以 YOY_BASE_MIN 那条小基数护栏一条都不能省 —— 它挡掉的正是
#     Aug-24 的 +569%（那说的是 Aug-23 只有 $4.9bn，不是 Aug-24 有多强）。
#     两种口径的实测差距仍然现算后印进图注：读者有权知道这条线为什么比从前抖。
#
# (3) 长历史图**通栏**（'full': True）。99 根柱塞进半栏每根不到 3px，
#     柱宽比描边还窄，等于把一张柱图画成了一片色块。
def xstep_for(n):
    """x 轴标签抽稀步长，**按该图自己的点数算**。

    引擎的标签循环是 `for i…: if (i % step) continue`（charts.js），锚点在 **i=0
    而不是最后一个点** —— step 不整除 (n−1) 时，**最新月的刻度会消失**：柱还在、
    柱顶数值标签也还在，只是轴上读不到月份，而那正是长历史图最该标出来的一格。

    所以既不能写死一个常数，也不能全页共用一个 —— 本页各图的点数并不相同
    （2026-08-17 现状：客户总资产 155 个月、核心净新增与年化有机增速各 114 个月、
    日均交易与月末融资余额各 19 个月，三档起点全不一样）。
    做法是从「约 14 档」这个目标密度起往上找第一个整除 (n−1) 的步长：
    密度最多疏一点点，锚点永远对，而且数据每多一个月它自己重算。
    """
    if n < 2:
        return 1
    lo = max(1, (n - 1) // 14)
    # 只在 [lo, 2*lo] 里找整除的步长。不封上界的话，(n−1) 是质数时会一路找到 n−1 本身，
    # 整条轴只剩首尾两个刻度 —— 那比丢掉最新月那一格糟得多。找不到就退回目标密度，
    # 代价是最新月没有刻度（可接受，且本页各图的长度已刻意对齐，实际走不到这一支）。
    return next((k for k in range(lo, 2 * lo + 1) if (n - 1) % k == 0), lo)
H_BAR = 330                            # 通栏长历史柱图的画布高（不含 x 标签带）
H_BRIDGE = 360                         # 桥图更高：它要同时容纳堆叠段、净额菱形与截轴真值
H_TALL = 420                           # 截轴图再高一档：截轴管「那一档占轴多少」，
                                       # 加高管「那一档有多少像素」，两件事互相独立

YOY_NOTE = ('单月同比的小基数保护：去年同月基数小于本序列绝对值中位数的 '
            f'{YOY_BASE_MIN:.0%}、或与本月异号时不算同比，折线在该月断开 —— '
            '那种月份算出来的是基数效应，不是业务变化。全历史窗口下这条护栏比 25 个月'
            '窗口时吃重得多：2018–2021 那几年的基数普遍只有现在的零头。')
_BRK_TXT = (f'红色竖虚线 = 口径断点（{BRK}）：单一客户流入的剔除门槛自该期起从 $10bn 提到 '
            '$25bn，月报不重述历史，线左右两侧不可直读，跨断点的同比与均值同样要打折扣。')


def brk_note(i):
    """断点滚出窗口时不要留下「红色竖虚线」这句 —— 那就成了第二个自相矛盾的图注。"""
    return _BRK_TXT if i is not None else ''


def ptp_stats(s, idx, pct_series=False):
    """图上那条单月同比折线的实际量程与断口数 —— 全部现算，供图注引用。

    全历史窗口的次轴量程由 2020–2021 那两年决定（疫情开户潮 + TD Ameritrade 并表），
    写死任何一个数字，下个月、或者历史被修订之后就是一句假话。
    """
    y = ptp_yoy(s, pct_series)
    keep = [p for p in idx if p in y.index]
    if not keep:
        return None
    v = y.loc[keep]
    n_slot = sum(1 for p in idx if p in s.dropna().index and (p - 12) in s.dropna().index)
    return {'n': len(keep), 'gaps': n_slot - len(keep),
            'lo': float(v.min()), 'hi': float(v.max()),
            'lo_m': mlab(v.idxmin()), 'hi_m': mlab(v.idxmax()),
            'cur': float(v.iloc[-1]), 'cur_m': mlab(v.index[-1])}


def ptp_axis_note(st, unit='%', d=0):
    """「这条金线是什么口径、量程被谁撑开的」—— 两句话，数字现算。"""
    if st is None:
        return '次轴为<b>点对点（单月）同比</b>（本月 ÷ 去年同月 − 1）。本窗口内暂无可算的点。'
    return (f'次轴金色折线是<b>点对点（单月）同比</b>（本月 ÷ 去年同月 − 1），'
            f'<b>不是</b> 12 个月滚动合计同比 —— 本页 2026-08-15 起统一改回单月口径。'
            f'全历史窗口下这条线有 {st["n"]} 个点，量程 {st["lo"]:+,.{d}f}{unit}'
            f'（{st["lo_m"]}）至 {st["hi"]:+,.{d}f}{unit}（{st["hi_m"]}），'
            f'当期 {st["cur"]:+,.{d}f}{unit}。')


def caliber_gap_note(st_cal, unit='%'):
    """单月 vs 滚动的实测差距 —— 页面已经不画滚动了，但「这条线为什么抖」得有个答案。"""
    if st_cal is None:
        return ''
    ratio = st_cal['sd_m'] / st_cal['sd_r'] if st_cal['sd_r'] else float('nan')
    t = (f'这条线比 12 个月滚动口径抖，幅度是实测的：对齐到两种口径都算得出的同一批月份'
         f'（{mlab(st_cal["first"])}–{mlab(st_cal["last"])}，{st_cal["n"]} 个月），'
         f'单月同比的标准差 {st_cal["sd_m"]:,.1f}pp 是滚动口径 {st_cal["sd_r"]:,.1f}pp 的 '
         f'{ratio:,.1f} 倍，相邻月最大跳变 {st_cal["jump_m"]:,.0f}pp vs {st_cal["jump_r"]:,.0f}pp')
    if st_cal['flips']:
        worst = max(st_cal['flips'], key=lambda f: abs(f[1] - f[2]))
        t += (f'，{len(st_cal["flips"])} 个月两种口径<b>符号相反</b>'
              f'（最极端的 {worst[0]}：单月 {worst[1]:+,.0f}{unit} / 滚动 {worst[2]:+,.0f}{unit}）')
    t += '。所以这条线只作「本月对去年同月」的读数用，不作趋势判断；趋势看柱本身。'
    return t


# ── Exhibit 2：核心净新增资产（全历史月度柱，通栏）──
d2 = tail(nna, ALL_N)
_bk2 = brk_idx(d2.index)
ST2 = flow_stats(nna, d2.index)          # 两种口径的实测差距，只用来写图注（页面已不画滚动）
P2 = ptp_stats(nna, d2.index)
ex.append({
    'n': 2, 'kind': 'gs_bar', 'full': True, 'height': H_BAR,
    'fmt': 'usd1', 'xlabels': xl(nna, ALL_N), 'xstep': xstep_for(len(d2)),
    'title': f'Core net new assets — {mlab(d2.index[0])} 至今',
    'ylab': '$bn', 'ylab2': '% y/y (单月)', 'legend': 'Monthly',
    'values': L(d2.values), 'yoy': ptp_yoy_axis(nna, d2.index),
    # m/m 气泡在 99 根柱上画不成：oval() 按文字长度定气泡宽、且只在**左**侧做边界钳制，
    # 通栏 n=99 时气泡右缘会越过绘图区压在右轴刻度数字上；箭头的锚点间距是 2×band
    # （约 20px），远小于气泡半宽，箭头于是反向横穿自己的气泡。先例是 build/msci.py 的
    # 127 根柱图，同样的理由删掉了它。m/m 读数在页顶抬头与汇总表里都有，不缺这一处。
    # 短序列的 Exhibit 8 / 9（19 根、半栏）不受影响，仍保留气泡。
    'break_at': _bk2, 'break_label': BRK_LABEL,
    'note': (QNOTE + '。' + ptp_axis_note(P2)
             + ptp_gap_note(nna, d2.index)
             + '（4 月是结构性极小月：缴税季净流入几乎归零，'
             '所以 4 月与它的次年同月正是护栏最常拦下的那几个。）'
             + caliber_gap_note(ST2) + brk_note(_bk2)),
})

# ── Exhibit 3：核心净新增资产（季度）——按要求紧接 Exhibit 2 ──
# 月度数据可无损累加到季度（恒等式见 Exhibit 5），所以这张图与上一张是同一个量的两种
# 时间粒度，摆在一起读最省事：柱的季节锯齿在月度图上是噪音，在季度图上就消失了。
_q = nna.dropna().groupby(nna.dropna().index.asfreq('Q'))
qsum, qcnt = _q.sum(), _q.count()
# 全历史，但**丢掉起点那个不满 3 个月的季度**：序列自 2018-05 起，2018Q2 只有 5/6 两个月，
# 画出来是一根凭空矮一截的柱，而读者没有任何线索知道它矮在哪。引擎的 partial_months
# 只标**末**季（按位置认最后一根），首季这种情况它兜不住 —— 所以在 Python 侧截掉。
# 现算不写死：起点月份一变（历史补齐/修订），该丢的季度自己就换了。
_QFIRST = next((i for i, p in enumerate(qsum.index) if int(qcnt.loc[p]) >= 3), 0)
_QDROP = [str(p) for p in qsum.index[:_QFIRST]]
qv = qsum.iloc[_QFIRST:]
qyoy = []
for p in qv.index:
    prev = p - 4
    if prev in qsum.index and qsum.loc[prev] and int(qcnt.loc[prev]) >= 3:
        qyoy.append(round(float(qsum.loc[p] / qsum.loc[prev] - 1) * 100, 6))
    else:
        # 去年同季本身不满 3 个月时同比作废：拿 2 个月的合计当分母，商里含的是缺的那个月。
        qyoy.append(None)
n_in_last = int(qcnt.iloc[-1])
_bk3 = brk_idx(qv.index, BRK_Q)               # 季度轴上断点是 2025Q1，不能传月度 period
ex.append({
    'n': 3, 'kind': 'qtr_bar', 'full': True, 'height': H_BAR,
    'fmt': 'usd0', 'label_fmt': 'usd0',
    'xlabels': [str(p) for p in qv.index],
    'title': f'Core net new assets by quarter — {qv.index[0]} 至今',
    'ylab': '$bn', 'legend': 'Complete quarter',
    'values': L(qv.values), 'partial_months': n_in_last, 'qtr_months': 3,
    # 名字里带口径：本页现在有两种同比口径（单月 / 季度合计），图例上不写清楚，
    # 读者把这条绿线与 Exhibit 2 的金线放在一起看必然对不上。
    'line': {'name': 'y/y (季度合计, RHS)', 'color': 'GREEN', 'values': qyoy, 'yfmt': 'pct0'},
    'break_at': _bk3, 'break_label': BRK_LABEL,
    'note': ('月度核心净新增资产按季汇总（恒等式可无损累加，见 Exhibit 5）。'
             '右轴是<b>季度合计同比</b>（本季 3 个月合计 ÷ 去年同季 3 个月合计），'
             '不是 Exhibit 2 那条单月同比 —— 两者当期读数并排见页尾「口径说明」。'
             + (f'序列起点 {mlab(df.index[0])} 落在季中，{"、".join(_QDROP)} 只有 '
                f'{int(qcnt.iloc[0])} 个月，不是完整季度，已整根剔除（不是数据缺失，'
                '是拿不满季的合计与完整季度并排会砸出一个假坑）。' if _QDROP else '')
             + '柱全为正而右轴 y/y 跨零，两轴零点不同源。走对齐还是走「两轴各自缩放」'
             '由 assets/charts.js 的 ALIGN_WASTE_MAX（阈值 38%）自动决定，不是本图写死的：'
             '本窗口实测 waste 28.6% 未超阈值，所以引擎走的是<b>对齐</b> —— 左轴因此被拉到'
             '负区（可见刻度自 -50 起），下方那段空白正是对齐的代价；右轴那条绿色零虚线与'
             '柱的基线<b>重合</b>，图内也<b>不</b>标「左右轴零点不同高」。真正超阈值触发'
             '兜底、并标出那句话的是 Exhibit 4（waste 50%）。'
             '⚠ 改窗口后这段必须重算：waste 随窗口变，'
             '跑 python3 tools/align_replica.py --note data/schw.js 3 取新数。'
             + (f'末季 {qv.index[-1]} 已含 {n_in_last} 个月，为完整季度。'
                if n_in_last >= 3 else
                f'末季 {qv.index[-1]} 只含 {n_in_last} 个月，柱为浅蓝且右轴 y/y 已作废 —— '
                '拿不满季的累计去比上年完整季度必然砸出一个假坑。')
             + brk_note(_bk3)
             + ('' if _bk3 is None else
                f' {BRK_Q}–{BRK_Q + 3} 这四个季度的右轴 y/y 拿新口径比旧口径，'
                '幅度里含口径差，只看方向不看大小。')),
})

# ── Exhibit 4：年化有机增长率（流量不算环比百分比，改用年化有机增速）──
og = df['organic_growth_ann']
ogr = df['organic_growth_roll']
# 按**自身序列**取窗（dropna），不铺满 df.index。
# 2026-08-16 的历史回填之后，本页各列的起点第一次不再相同：客户总资产与新开经纪账户
# 回到了 2013-09，而 core NNA 只回到 2017-02（官方 2018 年初才开始披露这个口径）。
# 有机增速的分子是 core NNA，所以它也只能从 2017-02 起 —— 铺满 df.index 的话左边会多出
# 41 个空列，读者看到的是「2013 年到 2017 年有机增速是零」，那是这一版最容易造出的假象。
d4 = tail(og, ALL_N)
_bk4 = brk_idx(d4.index)                      # 分子是 core NNA，断点原样传导过来
# 次轴 = 同一条**单月**年化率的百分点差（比率序列的点对点同比就是 pp 差），
# 不再是滚动 12 个月率的 pp 差 —— 与本页其余各图同口径。
ST4 = caliber_stats(og - og.shift(12), ogr - ogr.shift(12), d4.index)
P4 = ptp_stats(og, d4.index, pct_series=True)
ex.append({
    'n': 4, 'kind': 'gs_bar', 'full': True, 'height': H_BAR,
    'fmt': 'pct1', 'yfmt': 'pct0', 'xlabels': xl(og, ALL_N), 'xstep': xstep_for(len(d4)),
    'title': f'Annualised organic growth rate — {mlab(og.dropna().index[0])} 至今',
    'ylab': '% annualised', 'ylab2': 'pp y/y (单月)', 'legend': 'Monthly',
    'values': L(d4.values),
    'yoy': ptp_yoy_axis(og, d4.index, pct_series=True),
    'break_at': _bk4, 'break_label': BRK_LABEL,
    'note': ('Monthly core NNA x 12 / prior month-end client assets。'
             '这是 GS LPLA 版式的规矩：流量类指标不算环比百分比（分母是上月的流量，'
             '一个月的噪音会被放大成趋势），改用年化有机增长率把流量放回存量的尺度上。'
             + ptp_axis_note(P4, unit='pp', d=1)
             + '比率序列的同比一律用<b>百分点差（pp）</b>，不算「百分比的百分比变化」，'
             '所以这条线没有小基数护栏的问题（减法不做除法）。'
             + (f'与滚动口径的实测差距：对齐到同一批月份后（{ST4["n"]} 个月），'
                f'相邻月最大跳变 {ST4["jump_m"]:.1f}pp vs {ST4["jump_r"]:.1f}pp，'
                f'{len(ST4["flips"])} 个月符号相反；标准差的差距只有 '
                f'{ST4["sd_m"] / ST4["sd_r"]:.2f} 倍 —— 年化率本身已经把流量除以了存量，'
                '一半的噪音在这一步就被吸收了。' if ST4 else '')
             + f'当期读数：当月年化 {float(og.iloc[-1]):.2f}%、'
             f'（作为对照）滚动 12 个月 {float(ogr.dropna().iloc[-1]):.2f}%。'
             + brk_note(_bk4)),
})

# ── Exhibit 5：恒等式滚存桥（GS SCHW First Take Exhibit 2）──
# 桥的两段之一是 core NNA，所以窗口只能从 core NNA 的第一个月起 —— 客户资产虽然
# 回到了 2013-09，但那几年画出来会是「一整段只有浅蓝市值变动、深蓝恒为零」的假桥。
bAll = df.loc[nna.dropna().index[0]:]
_XL5 = [mlab(p) for p in bAll.index]
_bk5 = brk_idx(bAll.index)
# 截轴：全历史窗口下市值变动的量程是 −568…+1,458bn，而核心净新增只有 −9…+80bn。
# 不截的话深蓝那一段厚度只剩 1px，「40 还是 79」在图上完全读不出来 —— 而这张图的
# 全部意义就是「流入 vs 市值」的对比。门槛从 13 个月窗口时的 +420/−200 放宽到 ±600：
# 那两个数是照 13 根柱调的，全历史下会切掉 13 根柱（红色竖排真值糊成一片，反而读不了）；
# ±600 只切 2 根（Oct-20 的 TD Ameritrade 并表搬账、Apr-26 的市值大涨），
# 量程仍比不截时收窄四成有余。数字现算见 cap_note，不写死月份。
BR_CAP, BR_FLOOR = 600, -600
_cut5 = [mlab(p) for p in bAll.index
         if np.isfinite(bAll['asset_change'].loc[p])
         and (bAll['asset_change'].loc[p] > BR_CAP or bAll['asset_change'].loc[p] < BR_FLOOR
              or bAll['market_gains'].loc[p] > BR_CAP or bAll['market_gains'].loc[p] < BR_FLOOR)]
ex.append({
    'n': 5, 'kind': 'bridge_bar', 'full': True, 'height': H_BRIDGE,
    'fmt': 'usd0', 'xlabels': _XL5, 'xstep': xstep_for(len(_XL5)),
    'break_at': _bk5, 'break_label': BRK_LABEL,
    'title': f'What moved client assets: flows vs. markets — {mlab(bAll.index[0])} 至今',
    'ylab': '$bn change',
    'stacks': [
        {'name': 'Core net new assets', 'color': 'NAVY', 'values': L(bAll['core_nna_usdbn'].values)},
        {'name': 'Market gains (balancing)', 'color': 'BLUE', 'values': L(bAll['market_gains'].values)},
    ],
    'net': {'name': 'Total change in client assets',
            'values': L(bAll['asset_change'].values)},
    'net_color': 'INK',
    'ycap': BR_CAP, 'yfloor': BR_FLOOR,
    'cap_note': f'axis capped at ±{comma(BR_CAP)} — true values shown in red',
    'note': ('Identity: opening assets + core NNA + market gains = closing assets。'
             '市值变动是<b>轧差项</b>（= 客户资产环比变动 − 核心净新增），'
             '公司并不单独披露，所以它同时吸收了口径调整、并购转入与真实市场涨跌，'
             '不能整段当成「市场贡献」读 —— '
             f'{mlab(pd.Period("2020-10", "M"))} 那一根就是 TD Ameritrade 并表的资产搬账，'
             '不是市场涨了那么多。'
             f'首月（{mlab(bAll.index[0])}）没有上月余额，环比变动算不出，该列整根为空。'
             f'纵轴截在 +{comma(BR_CAP)} / {comma(BR_FLOOR)}：市值变动的量级是核心净新增的'
             '十几倍，不截轴深蓝那一段就薄得读不出逐月变化。超界的柱画到边界并加断口符号，'
             '真值以红色竖排标出，一个点都没有删'
             + (f'（本图超界的是 {"、".join(_cut5)}）。' if _cut5 else '。')
             + brk_note(_bk5)),
})

# ── Exhibit 6：客户总资产（全历史月度柱）──
# 存量：**不改口径**，本来就是点对点同比，这次只是把窗口拉到全历史。
atn = df['assets_tn']
d6 = tail(atn, ALL_N)
ST6 = caliber_stats(yoy.mom_yoy(atn, yoy.STOCK), mean_yoy(atn), d6.index)
P6 = ptp_stats(atn, d6.index)
ex.append({
    'n': 6, 'kind': 'gs_bar', 'full': True, 'height': H_BAR,
    # yfmt 必须显式给。不给的话左轴走引擎的 plainAxis(step)，而它对**半整数步长**判 0 位
    # 小数（`-floor(log10(2.5)) == 0`）—— 全历史之后次轴同比跨零（2022 年那段是负的），
    # 两轴对零点把左轴拉进负区，刻度步长于是变成 2.5，轴上就印出
    # 「15 │ 13 │ 10 │ 8 │ 5 │ 3 │ 0 │ -3」这种**看着不等距的等距刻度**
    # （12.5 被四舍五入成 13）。tools/visual_qa.py 对这个是硬 🔴。
    # 修在 payload 侧而不是 plainAxis：那个函数是 34 页共用的。
    'fmt': 'usd2', 'yfmt': 'f1', 'xlabels': xl(atn, ALL_N), 'xstep': xstep_for(len(d6)),
    'title': f'Total client assets — {mlab(d6.index[0])} 至今',
    'ylab': '$tn', 'ylab2': '% y/y (单月)', 'legend': 'Monthly',
    'values': L(d6.values), 'yoy': ptp_yoy_axis(atn, d6.index),
    'note': ('月末余额，官方口径为 $bn，此处除以 1,000 换成 $tn 便于读轴。'
             + stock_note(atn, d6.index, '客户总资产')
             + (f'全历史窗口内单月同比落在 {P6["lo"]:.0f}%（{P6["lo_m"]}）–'
                f'{P6["hi"]:.0f}%（{P6["hi_m"]}）之间'
                + ('，全程同号' if P6['lo'] * P6['hi'] > 0 else
                   '，跨零（2022 年的下跌年在这条线上是负区）') + '。' if P6 else '')
             + YOY_NOTE + ptp_gap_note(atn, d6.index)),
})

# ── Exhibit 7：新开经纪账户（全历史月度柱，截轴）──
# 这张图有两层「一个时代压平其余时代」的问题，分开治：
#
# (1) **并购搬账**：2020-05 的 USAA（1.1mn 户）与 2020-10 的 TD Ameritrade（14.5mn 户）。
#     它们不是开户，是把别家的存量账户搬进来。官方脚注给了确切数量，所以上面
#     ACQ_ACCOUNTS_K 直接把它们**净掉**（1,250→150、14,718→218），而不是留一根
#     14,718 的柱子再截轴——那根柱把纵轴顶到 1,600，其余 154 个月全挤在底部十分之一。
#     两根被调整过的柱画成**斜纹**（bar_marks），提醒读者这两个月与邻月不是同一回事，
#     原始披露值写在图注里，一个数都没有藏。
#
# (2) **2020–21 的开户狂潮**：净掉并购之后最高的仍是 2021-02 的 1,211k，是 2013–2019 年
#     月度中位数（106k）的 11 倍。这一段是真实业务（零利率 + 散户入市），不能动数据，
#     只能截轴：门槛取 700k，越界的是 2021 年 1/2/3 三个月，画到边界 + 断口符号 + 红色真值。
#     为什么是 700 而不是更低：500 会切掉 6 根、且全部连在一起，红色竖排真值会排成一堵墙
#     （引擎的 capLabel 只会把撞车的标签逐个右移，连着 6 根就全跑到别人的柱子上去了）。
#     700 只切 3 根，而 2013–2019 那一档的波动（70–165k）从占纵轴 6% 拉到 14%。
# 画布同时加高到 H_TALL：截轴改善的是「占轴多少」，加高改善的是「那一档有多少像素」，
# 两件事互相独立，一起做才够读。
nba = df['new_brokerage_accounts_k']
nba_ex = df['new_acct_ex']          # 已净掉并购搬账（见文件上方 ACQ_ACCOUNTS_K）
NBA_CAP = 700
# 右轴也要截。净除并购之后次轴仍有两个月冲到三位数：分母是疫情前的低基数（2020-01 的
# 167k、2020-02 的 159k），2021 年同月一放大就是 +556% / +662%。这两个点把右轴撑到 700%，
# 其余 141 个月全被压在零线附近的一条带子里 —— 与左轴那根 14,718k 的柱是同一类问题，
# 只是发生在另一条轴上。同样按「截轴不删点」处理：超界的点钳到边界 + 空心红圈 + 红色真值。
YOY_CAP7 = 300
d7 = tail(nba_ex, ALL_N)
_i7 = list(d7.index)
_marks7 = [_i7.index(p) for p in ACQ_ACCOUNTS_K if p in _i7]
_adj7 = '、'.join(
    f'{mlab(p)}（披露 {comma(float(nba.loc[p]))}k − 并购搬账 {comma(k)}k = '
    f'{comma(float(nba_ex.loc[p]))}k）'
    for p, k in ACQ_ACCOUNTS_K.items() if p in _i7)
_over7 = [(mlab(p), float(v)) for p, v in d7.items() if float(v) > NBA_CAP]
_ov7_txt = '、'.join(f'{m} 的 {comma(v)}k' for m, v in _over7)
P7 = ptp_stats(nba_ex, d7.index)
_y7 = ptp_yoy(nba_ex)
_yhi7 = '、'.join(f'{mlab(p)} 的 {v:+,.0f}%' for p, v in _y7.items()
                 if p in d7.index and v > YOY_CAP7)
ex.append({
    'n': 7, 'kind': 'gs_bar', 'full': True, 'height': H_TALL,
    'fmt': 'f0c', 'xlabels': xl(nba_ex, ALL_N), 'xstep': xstep_for(len(d7)),
    'title': f'New brokerage accounts opened — {mlab(d7.index[0])} 至今（已净除并购搬账）',
    'ylab': 'k accounts', 'ylab2': '% y/y (单月)', 'legend': 'Monthly (ex-acquisition)',
    'values': L(d7.values), 'yoy': ptp_yoy_axis(nba_ex, d7.index, ymax=YOY_CAP7),
    'bar_marks': _marks7,
    'ycap': NBA_CAP, 'yfloor': 0,
    'cap_note': (f'axis capped at {comma(NBA_CAP)}k — {len(_over7)} months in red'
                 if _over7 else None),
    'note': (QNOTE + '。这一行是<b>当月新开户数</b>（流量），不是账户存量。'
             + (f'<b>柱画的是净除并购搬账之后的开户量</b>：{_adj7}。'
                '两笔数量都是官方月报脚注 (4) 明写的，不是这里估的；'
                '它们是把别家的存量账户整批搬进来，不是当月有人来开户，'
                '留着会把纵轴顶到五位数、其余十几年全压成贴地的一条线。'
                '这两根柱画成<b>斜纹</b>以示与邻月不同源，披露原值已在上面列出。'
                if _adj7 else '')
             + (f'纵轴另截在 {comma(NBA_CAP)}k：净除并购之后最高的仍是 2020–21 年'
                f'开户狂潮的几个月（{_ov7_txt}），是 2013–2019 年月度中位数的十倍以上。'
                '那一段是真实业务，所以不动数据只截轴 —— 超界的柱画到边界加断口符号、'
                '真值红色竖排标出，点没有被删掉。'
                if _over7 else '')
             + '<b>次轴同比同样走净除后的序列</b>：拿并购月当基数算出来的是四位数的同比，'
             '描述的是一次搬账不是开户动能。'
             + (f'<b>右轴另截在 +{YOY_CAP7}%</b>：{_yhi7} —— 分母是疫情前的低基数，'
                '不截的话右轴要拉到 700%，其余十几年的同比全压在零线附近读不出。'
                '超界的点同样钳到边界、画空心红圈、真值红色竖排标出，没有删点。'
                if _yhi7 else '')
             + ptp_axis_note(P7) + ptp_gap_note(nba_ex, d7.index)),
})

# ── Exhibit 8：日均交易笔数 ──
# DATs 自 2026-01 的月报才开始披露、13 个月滚动表回溯到 2025-01，所以整条序列就这么长；
# 窗口设成「全历史」之后它自然就是全部 19 个月，不再需要「不足 25 个月」那句解释。
dm = df['dats_mn']
d9 = tail(dm, ALL_N)
_y9 = ptp_yoy_axis(dm, d9.index)
_n9 = sum(1 for v in _y9['values'] if v is not None)
ex.append({
    'n': 8, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': xl(dm, ALL_N),
    'title': 'Daily average trades',
    'ylab': 'mn trades / day', 'ylab2': '% y/y (单月)', 'legend': 'Monthly',
    'values': L(d9.values), 'yoy': _y9,
    'mom_txt': oval(mom_of(dm), suffix=' m/m'),
    'note': ('Client DATs first appear in the Jan-2026 report; the 13-month rolling table '
             'reaches back to Jan-2025。'
             f'本图画的就是这条序列的全部 {len(dm.dropna())} 个月'
             f'（{mlab(dm.dropna().index[0])} 起），不是被窗口截短的；'
             f'次轴只有最近 {_n9} 个点，更早的月份没有可比基数。'
             '次轴是<b>点对点（单月）同比</b>，与本页其余各图同口径 —— '
             '本序列还不满 24 个月，滚动 12 个月口径本来也算不出，'
             '而本页 2026-08-15 起整页统一走单月，历史长起来之后也不再自动切换口径。'
             + YOY_NOTE),
})

# ── Exhibit 9：月末融资余额 ──
mb = df['margin_balances_usdbn']
d10 = tail(mb, ALL_N)
_y10 = ptp_yoy_axis(mb, d10.index)
_n10 = sum(1 for v in _y10['values'] if v is not None)
ex.append({
    'n': 9, 'kind': 'gs_bar', 'fmt': 'usd0', 'xlabels': xl(mb, ALL_N),
    'title': 'Month-end margin balances',
    'ylab': '$bn', 'ylab2': '% y/y (单月)', 'legend': 'Monthly',
    'values': L(d10.values), 'yoy': _y10,
    'mom_txt': oval(mom_of(mb), suffix=' m/m'),
    'note': ('Schwab only began disclosing month-end margin balances in the Jan-2026 report; '
             'its 13-month rolling table reaches back to Jan-2025, so the y/y line starts '
             'Jan-2026。口径含 short credits。'
             f'本图同样画的是全部 {len(mb.dropna())} 个月，次轴同比只有最近 {_n10} 个点。'
             'Schwab 另有一条 2020-04 至 2025-12 的<b>月度平均</b>融资余额序列'
             '（series/schw_avg_margin.csv，官方已停发），它与本图的<b>月末</b>口径不同，'
             '不能接续成一条线，故本页不画。'
             + stock_note(mb, d10.index, '月末融资余额')
             + YOY_NOTE),
})


def fee_period_note(head='<b>费率期间。</b>'):
    """本页唯一用到 series/fee_rates.csv 的地方是 Exhibit 10（生息资产占比 + NIM）。
    这句话回答读者的三个问题：图上的费率是哪一季的、本页月度数据走到哪个月、
    两者错开时页面怎么处理。整句从数据现算 —— 季度号一律走 qlab()，不写死。"""
    t = (f'{head}生息资产与净息差是<b>季度</b>披露，本图两条线取至 '
         f'{qlab(_FEE_USED_Q)} 的公司披露值（<code>series/fee_rates.csv</code>；每季取自'
         '该季自己那份 8-K Ex-99.1 业绩新闻稿的原报值，官方后来的重述不回填）；'
         f'本页月度数据截至 {mlab(LATEST)}，属 {qlab(_LATEST_Q)}。')
    if _FEE_TAIL:
        # 落后几个月时逐月点名；落后久了改成区间，否则一年就是 12 个月份名，读不动。
        who = ('、'.join(mlab(p) for p in _FEE_TAIL) if len(_FEE_TAIL) <= 3 else
               f'{mlab(_FEE_TAIL[0])} 至 {mlab(_FEE_TAIL[-1])}')
        t += (f'{who} 这 {len(_FEE_TAIL)} 个月已有月报数字、尚无对应季度的费率，'
              f'季度线到 {mlab(_bs.index[-1])} 为止 —— 本页<b>不</b>把上一季的费率'
              '沿用到这几个月，也不外推、不补点。')
    elif _FEE_Q_MONTHS >= 3:
        t += '月度序列与季度线收在同一个季末，本图没有跨季沿用。'
    else:
        # 费率比月报先到（季报发布日早于当季最后一个月的月报），季度线反而跑在前面。
        t += (f'费率反而跑在月报前面：季度线已画到 {qlab(_FEE_USED_Q)}'
              f'（x 轴标 {mlab(_FEE_USED_Q.asfreq("M", "end"))}），而本页月报只到 '
              f'{mlab(LATEST)}，该季尚未走完。')
    if _FEE_STALE:
        t += (f'<b>⚠ 费率已过期：</b>{qlab(_FEE_USED_Q + 1)} 起的费率尚未进表，'
              f'已落后本页月度数据 {_FEE_LAG} 个季度（正常节奏是 0–1 季），'
              f'本图仍只到 {qlab(_FEE_USED_Q)}，请勿把它当作最新一季的水平读。')
    if _FEE_HAVE_Q > _FEE_USED_Q:
        t += (f'（表里 SCHW 已有 {qlab(_FEE_HAVE_Q)} 的费率，但该季的客户资产月份还没齐，'
              '比值的分母算不实，本图暂不画那一点。）')
    if _FEE_Q_MONTHS < 3:
        t += (f'末季 {qlab(_FEE_USED_Q)} 的分母只由 {_FEE_Q_MONTHS} 个月的客户资产求均，'
              '与前几季不是同一口径，该点只看方向不看水平。')
    return t


# ── Exhibit 10：为什么这里没有「量 → 收入」桥（季度序列，全历史）──
# lines_endlabels **不容忍 null**（docs/CHART_KINDS.md §1.2：首尾为 null 直接抛
# TypeError、中间的 null 把线画塌到 0），所以窗口只能取「两条线都有值」的那一段。
# 这也是本页唯一一张理论上能画到 2016 年的图 —— fee_rates.csv 的 SCHW 净息差回溯到
# 2013Q4 —— 但生息资产占比的分母是客户资产（2018-05 起），补不出来的那几年只能是
# null，而这个图型正好是不许有 null 的那一类。所以它同样从 2018 年画起。
bs = _bs
_r0, _r1 = float(bs['iea_share'].iloc[0]), float(bs['iea_share'].iloc[-1])
ex.append({
    'n': 10, 'kind': 'lines_endlabels', 'fmt': 'pct1',
    'xlabels': [mlab(p) for p in bs.index],
    'title': f'Why there is no revenue bridge here — {qlab(_ratio.index[0])} 起',
    'ylab': '%',
    'series': [
        {'name': 'Interest-earning assets / client assets', 'color': 'NAVY',
         'values': L(bs['iea_share'].values)},
        {'name': 'Net interest margin', 'color': 'RED', 'values': L(bs['nim'].values)},
    ],
    'note': ('Neither client cash nor interest-earning assets is published monthly. '
             'The only monthly proxy is client assets, and that ratio moved from '
             f'{_r0:.1f}% to {_r1:.1f}% over {len(bs) - 1} quarters — treating it as a constant '
             'would be false precision. Both series are quarterly。'
             'x 轴标的是各季<b>季末月</b>；PDF 版此处保留 2 位小数，网页图表引擎的格式器只到 '
             '1 位小数，切到「表格」视图可读到 2 位。'
             '本图不做窗口截取，画的是两条线都有值的全部季度。'
             f'2026-08-16 把客户总资产回填到 {mlab(df.index[0])} 之后，这张图的窗口从 '
             f'14 个季度扩到了 {len(bs)} 个 —— 分母（客户资产的季度均值）此前只回溯到 2018 年，'
             '把这条比值截在了金融危机后半段之外。现在它盖住了 2015–2019 那轮加息、'
             '2020 的零利率与 2022 起的又一轮加息，「生息资产占客户资产的比重在长期下行」'
             '这句话第一次有足够长的样本支撑。'
             '两条线同起同止：净息差本身在费率表里还能更早，但占比的分母补不出来，'
             '而 <code>lines_endlabels</code> 这个图型不容忍空点（docs/CHART_KINDS.md §1.2）。'),
    # 费率的期间放 src_extra —— 它是「这两条线的数出自哪一季」的出处说明，
    # 紧贴 Source 行显示；过期时那句 ⚠ 也在同一段，读者不用翻到页尾的方法论。
    'src_extra': fee_period_note(),
})


# ── Exhibit 11/12/13：逐年同期对照 ──
# 逐年对照图最多画几条线。上界不是审美偏好，是调色板的物理上限：引擎把往年线摊在
# 一条固定的蓝色明度带上（L* 约 77→24），10 条线时相邻两年差 ~6 个 L*，还分得开；
# 客户总资产与新开经纪账户回填到 2013-09 之后是 14 条，相邻年只差 ~4 个 L*，
# 2013/2014/2015 三条在图上是同一个蓝。这类图的题眼是「今年 vs 最近几年的同月」，
# 再往前的年份该去看 Exhibit 6 / 7 的全历史柱图，那里每个月都单独占一根柱。
YEAR_LINES_MAX = 10


def year_series(s, n_years=YEAR_LINES_MAX):
    """按年切成「Jan..Dec 十二格」的多条线。n_years=None 表示全部年份。"""
    s = s.dropna()
    yrs = sorted({p.year for p in s.index})
    if n_years:
        yrs = yrs[-n_years:]
    out = []
    for y in yrs:
        vals = []
        for m in range(1, 13):
            p = pd.Period(f'{y}-{m:02d}', 'M')
            vals.append(float(s.loc[p]) if p in s.index and np.isfinite(s.loc[p]) else None)
        out.append({'name': str(y), 'values': L(vals)})
    return out


MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def yr_span(names):
    """['2018','2019','2020'] → '2018–2020'；不连号或只有一个就原样并列。"""
    if len(names) <= 2:
        return '/'.join(names)
    ys = [int(x) for x in names]
    return f'{ys[0]}–{ys[-1]}' if ys == list(range(ys[0], ys[-1] + 1)) else '/'.join(names)


# ── Exhibit 11：核心净新增资产逐年同期对照 ──
y12 = year_series(nna)
# 断点在这张图上不是一个 x 位置 —— x 轴是 Jan..Dec，断点分的是**线**（年份）不是月份，
# 竖虚线画上去会被读成「某个月不可比」。所以改用 annot 把同一句话写在图内（annot 走
# charts.js 的通用分支，year_lines 吃得到），并按年份把两种口径点名。
_OLD12 = [s['name'] for s in y12 if int(s['name']) < BRK.year]
_NEW12 = [s['name'] for s in y12 if int(s['name']) >= BRK.year]
ex.append({
    'n': 11, 'kind': 'year_lines', 'fmt': 'usd0', 'xlabels': MONTHS,
    'title': 'Core NNA path by year',
    'ylab': '$bn', 'series': y12, 'highlight': len(y12) - 1,
    'annot': f'口径断点：{yr_span(_NEW12)} 为 $25bn 门槛，{yr_span(_OLD12)} 为 $10bn',
    'note': ('每年一条线叠在 Jan–Dec 轴上，当年红色加粗，往年按年份由浅到深。'
             '画的是<b>当月值</b>不是年初至今累计，'
             '所以 4 月与 12 月那两个季节性尖谷/尖峰可以逐年对齐着看。'
             f'本图画全部 {len(y12)} 年（{y12[0]["name"]}–{y12[-1]["name"]}）；'
             f'{y12[0]["name"]} 年只有 {sum(1 for v in y12[0]["values"] if v is not None)} '
             '个月有数（序列自年中起），该年那条线的左半段是空的，不是塌到零。'
             f'口径断点在年份之间而不在月份上，画不成竖虚线：{yr_span(_NEW12)} 用 $25bn '
             f'剔除门槛，{yr_span(_OLD12)} 用 $10bn（图内已标出），'
             '跨这两组做逐年对比要扣掉这一条。'),
})

# ── Exhibit 12：新开经纪账户逐年同期对照 ──
y13 = year_series(nba_ex)
ex.append({
    'n': 12, 'kind': 'year_lines', 'fmt': 'f0c', 'xlabels': MONTHS,
    'title': 'New accounts path by year',
    'ylab': 'k accounts', 'series': y13, 'highlight': len(y13) - 1,
    'note': ('画的是<b>净除并购搬账之后</b>的开户量，与 Exhibit 7 的柱同一条序列：'
             'May-2020 的 USAA（1.1mn 户）与 Oct-2020 的 TD Ameritrade（14.5mn 户）'
             '都是把别家的存量账户整批搬进来，不是当月有人来开户，官方脚注给了确切数量，'
             '所以这里做减法（1,250→150、14,718→218），减完与邻月严丝合缝。'
             f'本图窗口是最近 {len(y13)} 年（{y13[0]["name"]}–{y13[-1]["name"]}），'
             '2020 年<b>在</b>窗口内 —— 此前那条线在 May 处有一个 1,250k 的假尖峰'
             '（并购没净掉）、在 Oct 处是个洞（整月被置空），两处现在都是真实读数。'),
})

# ── Exhibit 13：日均交易笔数逐年同期对照（版式同 Exhibit 12）──
y14 = year_series(dm)
_y14_pts = sum(1 for s in y14 for v in s['values'] if v is not None)
ex.append({
    # label_fmt 必须显式给：year_lines 的末点标签兜底是 'f0c'（charts.js），
    # 那是照「k accounts」定的，套在 mn 单位上会把 11.6 印成一个「12」。
    'n': 13, 'kind': 'year_lines', 'fmt': 'f1', 'label_fmt': 'f1', 'xlabels': MONTHS,
    'title': 'Daily average trades path by year',
    'ylab': 'mn trades / day', 'series': y14, 'highlight': len(y14) - 1,
    'note': ('版式同 Exhibit 12：每年一条线叠在 Jan–Dec 轴上，当年红色加粗，'
             '画的是<b>当月的日均笔数</b>（公司披露口径本身已日均化，不再除交易日）。'
             f'本图只有 {len(y14)} 条线、共 {_y14_pts} 个点：DATs 自 2026-01 的月报才'
             f'开始披露、13 个月滚动表回溯到 {mlab(dm.dropna().index[0])}，'
             '在那之前 Schwab 根本没有公布过这个数 —— 线少不是筛掉了什么，是历史就这么长。'
             f'{y14[-1]["name"]} 那条线到 {MONTHS[LATEST.month - 1]} 为止，'
             '右半段是空的（还没到），不是塌到零。'
             '逐年对照图不换口径：逐月波动与季节形状就是这类图的题眼。'),
})

# ── Exhibit 14：年化有机增长率 月 x 年热力矩阵 ──
ogd = og.dropna()
hyrs = sorted({p.year for p in ogd.index})
matrix = []
for y in hyrs:
    row = []
    for m in range(1, 13):
        p = pd.Period(f'{y}-{m:02d}', 'M')
        row.append(round(float(ogd.loc[p]), 6)
                   if p in ogd.index and np.isfinite(ogd.loc[p]) else None)
    matrix.append(row)
ex.append({
    'n': 14, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pct1',
    # 标题里必须写「单月」：热力矩阵按定义是逐格月度读数。
    'title': 'Annualised organic growth rate — 单月年化 (%)',
    # 热力矩阵走 drawHeat 提前 return，通用断点/annot 分支都执行不到；而且这里断点分的
    # 是**行**（年）不是列（月）。唯一能落在图上的位置是行首标签，所以把口径写进行名 ——
    # 读者扫一眼行头就能看到门槛在哪一行换掉，而不是只在图注里看到一句话。
    'rows': [f'{y} · {25 if y >= BRK.year else 10}bn' for y in hyrs],
    'row_lab_w': 54,
    'cols': MONTHS, 'matrix': matrix,
    'legend': 'Annualised organic growth rate',
    'row_head': '年 · core NNA 剔除门槛（$bn）',
    'note': ('Green = faster organic asset gathering。色标取全部有限值的 5/95 分位，'
             '一两个离群月不会把整表压平。'
             f'本表画全部 {len(hyrs)} 年（{hyrs[0]}–{hyrs[-1]}）。'
             f'首行（{hyrs[0]}）前几格空白不是缺数：序列自 {mlab(df.index[0])} 起，'
             f'而年化有机增速要用上月末客户资产做分母，{mlab(ogd.index[0])} 才是第一个可算月。'
             f'行首标出各年的 core NNA 剔除门槛：{BRK.year} 年起为 $25bn，此前为 $10bn，'
             '跨这条界的上下行不可直读（矩阵图的断点在行之间，画不成竖虚线）。'
             '本图通栏（横跨两列），但仍按图号排在 Exhibit 13 之后，图序即阅读顺序。'
             '格内数字带 % 号，PDF 版是裸数字。'),
})


# ────────────────────────────── Exhibit 15：核对表 ──────────────────────────────
T13 = df.iloc[-13:]


def tcell(v, d=1):
    return None if v is None or not np.isfinite(v) else comma(float(v), d)


# 图号自查：exhibit 编号必须是 2..N 的连号，核对表接在最后一张之后。
# 编号写死过一次代价就够大了 —— 全站审计发现别的页把核对表写死成 'n': 15，
# 后来在末尾追加了两张图，页面就出现「…16、17、15」而没有任何东西报错。
# 这里改成现算 + 硬拦：追加图之后核对表自动往后挪，若中间断号直接构建失败。
_ENS = [e['n'] for e in ex]
if _ENS != list(range(2, 2 + len(_ENS))):
    raise SystemExit(f'Exhibit 编号不连续: {_ENS}')

table = {
    'n': _ENS[-1] + 1,
    'title': '近 13 个月月度指标核对表（官方原始单位，未换算）',
    'idx': '月份',
    'cols': [['Core NNA ($bn)', 'nna'],
             ['Total client assets ($bn)', 'assets'],
             ['New brokerage accounts (k)', 'acct'],
             ['Daily average trades (k)', 'dats'],
             ['Margin balances ($bn)', 'margin']],
    'rows': [{'xl': mlab(p),
              'nna': tcell(r['core_nna_usdbn'], 1),
              'assets': tcell(r['total_client_assets_usdbn'], 1),
              'acct': tcell(r['new_brokerage_accounts_k'], 0),
              'dats': tcell(r['dats_k'], 0),
              'margin': tcell(r['margin_balances_usdbn'], 1)}
             for p, r in T13.iterrows()],
}


# ────────────────────────────── 口径与方法说明 ──────────────────────────────
_lat_nna = float(nna.iloc[-1])
_lat_og = float(og.iloc[-1])
_lat_at = float(atn.iloc[-1])
_lat_dm = float(dm.dropna().iloc[-1])
_lat_mb = float(mb.dropna().iloc[-1])
_y_nna, _y_mb, _y_dm = yoy_of(nna), yoy_of(mb), yoy_of(dm)
_m_nna, _m_at, _m_dm, _m_mb = mom_of(nna), mom_of(atn), mom_of(dm), mom_of(mb)
_y_at = yoy_of(atn)
_y_og, _m_og = yoy_of(og, pct_series=True), mom_of(og, pct_series=True)

# ── 本页每条序列的当期同比读数，全部现算，供汇总表注与页尾口径说明并排印出 ──
# 2026-08-15 起全页次轴统一为单月口径，所以这一段的主要职责从「两种口径别搞混」
# 变成了「图与表现在是同一个数，可以互相验算」。滚动 12 个月的读数仍然并排印出，
# 但只作**对照**：各图图注里还引用它来解释「这条线为什么比从前抖」，
# 页尾却查不到当期值的话，那半句就成了无法核对的断言。
_R_NNA = roll_yoy(nna)
_R_NBA = roll_yoy(nba_ex)


def _pair_txt(name, m, r, unit='%', d=1):
    """「单月 X（对照：滚动 Y，差 Zpp）」——两个口径都有才印对照，缺一个就只印有的那个。"""
    a = None if m is None or not np.isfinite(m) else f'单月 {m:+,.{d}f}{unit}'
    b = None if r is None or not np.isfinite(r) else f'滚动 12 个月 {r:+,.{d}f}{unit}'
    if a and b:
        return f'{name}：{a}（对照 {b}，差 {abs(m - r):,.0f}pp）'
    return f'{name}：{a or b}' if (a or b) else ''


def _last(s):
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


# 季度合计同比（Exhibit 3 那条绿线）的当期读数 —— 全页仅存的第二种同比口径
_Q_NNA = next((v for v in reversed(qyoy) if v is not None), None)
_CAL_ROWS = [t for t in (
    _pair_txt('Core net new assets（Exhibit 2 次轴）', _y_nna, _last(_R_NNA)),
    _pair_txt('New brokerage accounts（Exhibit 7 次轴，已净除并购搬账）',
              yoy_of(nba_ex), _last(_R_NBA)),
    ('Core NNA 的另一种口径：季度合计同比（Exhibit 3 的绿线）'
     f'{_Q_NNA:+,.1f}%' if _Q_NNA is not None else ''),
    _pair_txt('年化有机增长率（Exhibit 4，比率取 pp 差）',
              _y_og, (lambda s: (float(s.iloc[-1]) - float(s.iloc[-13]))
                      if len(s) >= 13 else None)(ogr.dropna()), unit='pp', d=2),
    f'Total client assets（存量，Exhibit 6）：单月 {_y_at:+,.1f}%'
    if _y_at is not None else '',
    f'Month-end margin balances（存量，Exhibit 9）：单月 {_y_mb:+,.1f}%'
    if _y_mb is not None else '',
) if t]

# Exhibit 10 是不是真的单边下行、全序列有几个季度上升 —— 图注里那两句都得从数据现算。
# 该图现在画的就是全序列，所以窗口内与全序列是同一批点，两个判据仍分开算：
# 窗口一旦以后又被截短，这里不用跟着改。
_MONO13 = bool((np.diff(bs['iea_share'].values) <= 0).all())
_UP_ALL = int((np.diff(_bs['iea_share'].values) > 0).sum())

# 哪几张图真的画出了断点线，从 payload 现读，绝不写死一串编号。
# 原先要防的是「窗口往前滚、断点滚出去了，注释却还说有」；本轮把窗口改成全历史之后，
# 断点反而永远在窗口内 —— 但**图号**成了新的变量（本轮就把它们整体挪了一遍），
# 现读 payload 同时挡住了这两种漂移，所以这个写法保留，理由换了一条。
_BRK_DRAWN = '、'.join(str(e['n']) for e in ex if e.get('break_at') is not None)

summary['note'] = (
    QNOTE + '.  Core NNA is a flow, read through the annualised organic growth line '
    'per GS convention.  The core-NNA exclusion threshold moved from $10bn to $25bn in 2025'
    + (f' — the break is drawn on Exhibits {_BRK_DRAWN.replace("、", ", ")}.  '
       if _BRK_DRAWN else ' — all chart windows now sit entirely to the right of the break.  ')
    + 'Margin balances include short credits.  '
    '比率类指标（年化有机增长率）的差异用 pp/bp，不用百分比变化；'
    '市值变动是轧差项，其差异用绝对额（$bn）而非百分比。'
    '3Y %ile = 当月读数在最近 36 个月的<b>可用观测</b>里高于多少比例的观测'
    + (f'（本页 {"、".join(thin_rows)} 的披露史短于 36 个月，按其全部历史算）。'
       if thin_rows else '。')
    + '判据统一走 <code>build/pctile.py</code>（全站一份实现，避免同一条序列在两页判成'
    '两个结果）：把该行的分位在近 24 个月里逐月回放一遍，若 ≥70% 的月份钉在 100 或 0，'
    '这一列对这一行就没有区分度，留空。'
    + (f'本轮据此留空的行：{"、".join(dead_rows)}。' if dead_rows else '本轮无行触发该判据。')
    + (f'另有 {"、".join(short_rows)} 因可用样本不足 8 个月，分位算不出可信读数，一并留空。'
       if short_rows else '')
    + '<br><b>本表的 y/y 列是「单月口径」= 本月 ÷ 去年同月 − 1，'
    '与各图次轴的金色折线<b>现在是同一个口径</b>（2026-08-15 起全页统一）。</b>'
    '这一列仍恒等于表内算术（第一列 ÷ 第三列），读者可以直接验算，'
    '而且验算结果现在也能和图上那条线对上 —— 此前流量类的图画的是 12 个月滚动合计同比，'
    '表与图对不上是当时最常见的一类读者困惑。'
    '唯一还剩的另一种同比是 Exhibit 3 的季度合计同比（那条绿线，分母是去年同季 3 个月合计）。'
    f'当期各口径并排现算 —— {"；".join(_CAL_ROWS)}。')

notes = [
    f'<b>数据源与节奏。</b>Schwab Monthly Activity Report，通常次月 12–14 日发布；'
    f'本页数据截至 {mlab(LATEST)}，全序列自 {mlab(df.index[0])} 起。'
    '所有数值来自 <code>series/schw.csv</code> 与 <code>series/fee_rates.csv</code>，'
    '无任何估算或补插。'
    f'前者是<b>月度</b>表，<code>fee_rates.csv</code> 是<b>季度</b>表（随季报更新），'
    f'本页只有 Exhibit 10 用它，SCHW 两个指标都齐的最新一季是 {qlab(_FEE_HAVE_Q)}；'
    '两张表节奏不同，页面上「月度已走到哪个月、费率停在哪一季」的差随时可能出现，'
    '每张相关图的 Source 行下都写明了当期口径。',

    # ── 这一条是本轮改版最容易被误读的地方，所以排在方法论第二位 ──
    '<b>⚠ 时间轴：每张图画到它自己那条序列的第一个月，各图起点因此并不相同。</b>'
    '要求是「所有的图从 2016 年开始」。2026-08-16 为此做了一次历史回填'
    f'（<code>fetch/schw.py --backfill</code>，见该文件的「历史回填源」一节），'
    f'把序列从 99 个月接到了 {len(df)} 个月。结果分三档，<b>档与档的边界是官方的披露史，'
    '不是抓取能力</b>：'
    f'<b>(1) 客户总资产 / 新开经纪账户 → {mlab(df.index[0])}</b>（{len(atn.dropna())} 个月，'
    '已越过 2016 整整两年多）。这两列靠 SEC EDGAR 补齐：2017-03 之前 Schwab 把'
    '「月度活动报告」原样作为季度 8-K 的 EX-99.1 附上去，正文里就是那张 13 个月滚动表，'
    '相邻两期重叠 10 个月，可以逐期接续；2017-03 之后的缺口由官方 CDN 上几份'
    '文件名不规则（前缀 <code>schwab_</code>、扩展名大写 <code>.XLSX</code>）的老附表补上。'
    f'<b>(2) 核心净新增资产及其派生量 → {mlab(nna.dropna().index[0])}</b>'
    f'（{len(nna.dropna())} 个月，到不了 2016）。这是<b>披露边界</b>：'
    '<b>Core</b> Net New Assets 这一行 2018 年初才出现在滚动表里，'
    '在那之前同一位置只有未剔除的 Net New Assets。两者不是一条序列'
    '（官方对 2017-06 同时给过 37.7 与 22.1 两个数），'
    '<b>本页不拼接</b> —— 拼出来的那一段会让 2016–2017 年的「核心」净流入系统性偏高。'
    f'受此约束的是 Exhibit 2 / 3 / 4 / 5。<b>(3) 日均交易笔数 / 月末融资余额 → '
    f'{mlab(dm.dropna().index[0])}</b>（{len(dm.dropna())} 个月）：这两列是 2026-01 那期'
    '月报<b>新增</b>的，官方回填到 2025-01 就到头了，更早的年份公司从未公布过这两个数，'
    '任何来源都补不出来。'
    f'季度费率图（Exhibit 10）随客户总资产一起回到了 {qlab(_ratio.index[0])}。'
    '此前各图用的是「从最新月倒推 25 个月 / 13 个月 / 14 个季度」的滚动窗口，现已全部取消。'
    '<b>不补零、不外推、不拿旧口径顶新口径</b>：补不出来的月份就是空的。',

    f'<b>季末月口径。</b>{QNOTE}——3/6/9/12 月没有独立月报，这四个月的数值取自当季季报，'
    '所以序列是连续的，但它与其余月份的披露载体不同'
    '（Exhibit 2、7 的图注均标了这一条，Exhibit 3 的季度图按构造不受影响）。',

    '<b>市值变动是轧差项，不是披露值。</b>Exhibit 5 的滚存桥用的是恒等式'
    '「期初资产 + 核心净新增 + 市值变动 = 期末资产」，其中市值变动 = 客户资产环比变动 − 核心净新增。'
    '公司不单独披露这一项，所以它同时吸收了真实市场涨跌、口径调整与并购转入，'
    '不能整段当成「市场贡献」读 —— 全历史窗口下最刺眼的那一根（2020-10）就是 '
    'TD Ameritrade 并表的资产搬账。',

    '<b>流量类不算环比百分比。</b>核心净新增资产是流量，环比百分比的分母是上个月的流量，'
    '一个月的噪音会被放大成趋势。按 GS「LPLA monthly metrics」的规矩改用<b>年化有机增长率</b>'
    '（当月净新增 × 12 ÷ 上月末客户资产），见 Exhibit 4 与 Exhibit 14。'
    '比率序列的同比一律用<b>百分点差（pp/bp）</b>，不是「百分比的百分比变化」。',

    # ── 同比口径：本轮从四种收敛到两种，收敛本身就得写出来 ──
    # 读者手上可能还留着上一版的截图，上面写着「12M roll」；不点名这次换掉了什么，
    # 他只会以为哪一版算错了。
    '<b>⚠ 同比口径：本页现在只有两种（此前四种），逐处点名。</b>'
    '(1) <b>点对点（单月）同比</b>（本月 ÷ 去年同月 − 1；比率序列取百分点差）—— '
    '<b>所有月度图的次轴金色折线</b>（Exhibit 2 核心净新增资产、Exhibit 4 年化有机增长率、'
    'Exhibit 6 客户总资产、Exhibit 7 新开经纪账户、Exhibit 8 日均交易笔数、'
    'Exhibit 9 月末融资余额），Exhibit 1 汇总表的 y/y 列，'
    '页顶 brief 段里出现的全部同比读数，以及 Exhibit 14 热力矩阵的逐格读数。'
    '<b>图与表现在是同一个口径，可以互相验算</b>，这正是本轮改口径换来的东西。'
    '(2) <b>季度合计同比</b>（本季 3 个月合计 ÷ 去年同季 3 个月合计 − 1）—— '
    '仅 Exhibit 3 的右轴绿线。另有<b>环比</b>（m/m）出现在各图的气泡里，那不是同比。'
    '<b>已取消的两种</b>：12 个月滚动合计同比（此前 Exhibit 2 / 4 / 7 的次轴）与'
    '12 个月滚动均值同比（此前只作对照）。'
    + (f'取消是有代价的，代价现算如下：对齐到两种口径都算得出的同一批月份（{ST2["n"]} 个月），'
       f'核心净新增资产的单月同比标准差 {ST2["sd_m"]:,.1f}pp 是滚动口径 '
       f'{ST2["sd_r"]:,.1f}pp 的 {ST2["sd_m"] / ST2["sd_r"]:,.1f} 倍，'
       f'相邻月最大跳变 {ST2["jump_m"]:,.0f}pp vs {ST2["jump_r"]:,.0f}pp，'
       f'{len(ST2["flips"])} 个月两种口径符号相反。'
       if ST2 else '')
    + '<b>所以那条金线只作「本月对去年同月」的读数用，不作趋势判断</b>；'
    '趋势看柱本身、看 Exhibit 3 的季度图、看 Exhibit 11–13 的逐年对照。'
    f'{YOY_NOTE}'
    + (f'存量序列（客户总资产、月末融资余额）本来就是这个口径，本轮没动。实测：'
       f'客户总资产的点对点同比标准差 {ST6["sd_m"]:,.1f}pp，'
       f'12 个月均值同比 {ST6["sd_r"]:,.1f}pp，两种口径 {len(ST6["flips"])} 个月符号相反 —— '
       '均值口径更平滑，但按构造滞后约半年、回答的是「去年一整年的平均水平」，'
       '不是「现在相对去年此刻」。' if ST6 else '')
    + f'当期各口径并排现算：{"；".join(_CAL_ROWS)}。'
    '<b>热力矩阵（Exhibit 14）与逐年对照图（Exhibit 11 / 12 / 13）本来就是逐月读数</b>：'
    '逐格的月度波动与季节形状就是那几类图的题眼。',

    f'<b>核心净新增资产的剔除门槛在 {BRK.year} 年调过，断点已画在图上。</b>'
    '官方脚注为「generally greater than $25 billion beginning in 2025; $10 billion in '
    f'prior periods」——单一客户流入的剔除阈值自 {BRK} 起从 $10bn 提高到 $25bn，'
    '月报不重述历史，因此断点左右的「核心」口径不完全可比。原始月报没有给出调整前后的'
    '对照值，这里不做还原，但按规矩把断点画出来而不是只写一句话：'
    + (f'Exhibit {_BRK_DRAWN} 在 {BRK}（季度图为 {BRK_Q}）处有红色竖虚线，线左右不可直读，'
       '跨线的同比同样含口径差。' if _BRK_DRAWN else
       f'当前各图窗口已整段落在 {BRK} 右侧，无需画线。')
    + 'Exhibit 11 的断点分的是年份不是月份、Exhibit 14 的断点分的是行不是列，'
    '两张图画不成竖虚线，改为在图内注解与行首标签上标明门槛。'
    '窗口拉到全历史之后，断点两侧各有多少年一目了然：'
    f'左侧 {BRK.year - df.index[0].year} 年多用 $10bn 门槛，右侧用 $25bn。',

    f'<b>融资余额有两条口径不同的序列，本页只画其中一条。</b>Exhibit 9 画的是<b>月末</b>'
    f'余额，Schwab 自 2026-01 的月报才开始披露，其 13 个月滚动表回溯至 '
    f'{mlab(mb.dropna().index[0])}，所以 y/y 从 2026-01 才有。另有一条<b>月度平均</b>'
    f'余额（<code>series/schw_avg_margin.csv</code>，2020-04 至 {mlab(avgm.index[-1])} 后停发），'
    '与月末口径不可接续，本轮已从页面移除 —— 两条不同口径的线并排摆着，'
    '读者迟早会把它们拼成一条 9 年的长序列读。日均交易笔数（DATs）同理，'
    f'只有 {mlab(dm.dropna().index[0])} 起的历史。',

    '<b>这里没有「量 → 收入」桥。</b>Schwab 月报既不披露客户现金也不披露生息资产，'
    '唯一能当代理的是客户资产；但生息资产 / 客户资产的比值在 Exhibit 10 画的 '
    f'{len(bs)} 个季度（{mlab(bs.index[0])}–{mlab(bs.index[-1])}）里从 {_r0:.1f}% '
    f'{"单边" if _MONO13 else ""}走到 {_r1:.1f}%（趋势，不是噪音），把它当常数会造出假精度。'
    f'其中 {_UP_ALL} 个季度环比上升，高点是 {mlab(_bs["iea_share"].idxmax())} 的 '
    f'{float(_bs["iea_share"].max()):.1f}%，所以它不是一条单调下滑线。'
    '不搭桥，改把这个比值本身画出来（Exhibit 10）—— 它本身就是 NII 增长受限的原因。'
    '该图两条线都是<b>季度</b>数据，来自季报；净息差单独回溯得更早（费率表自 2013Q4 起），'
    '但占比的分母是月度客户资产，补不出来，而 <code>lines_endlabels</code> 这个图型'
    '不容忍空点（docs/CHART_KINDS.md §1.2），所以两条线同起同止。'
    + (f'起点那个不满 3 个月的季度（{"、".join(_Q_PARTIAL_HEAD)}）已剔除：'
       '它的分母只由 2 个月的客户资产求均，与其余季度不是同一口径。'
       if _Q_PARTIAL_HEAD else '')
    + fee_period_note(head='费率的期间：'),

    f'<b>截轴不删点。</b>窗口拉到全历史之后有两张图需要截轴，都不删点：'
    f'（1）Exhibit 7 的纵轴截在 {comma(NBA_CAP)}k'
    + (f'，越界的是 {_ov7_txt} —— 2020–21 年开户狂潮的几个月，那是真实业务，'
       '所以不动数据只截轴：柱画到边界加断口符号、真值红色竖排标出。'
       if _over7 else '。')
    + '<b>并购搬账则是另一回事，走的是减法不是截轴</b>：May-2020 的 USAA 与 Oct-2020 的 '
    'TD Ameritrade 把别家的存量账户整批搬进来，官方脚注给了确切数量（1.1mn / 14.5mn 户），'
    '所以 Exhibit 7 与 Exhibit 12 画的都是净除之后的开户量，那两根柱另画成斜纹以示不同源，'
    '披露原值在 Exhibit 7 的图注里。'
    '<b>不这么做的后果是量化的</b>：留着 14,718k 那一根，纵轴要顶到 1,600k，'
    '2013–2019 年那一档（月度 70–165k）只占纵轴 6%，十几年的逐月差异在图上是一条平线。'
    f'（2）Exhibit 5 的滚存桥截在 ±{comma(BR_CAP)} $bn：市值变动的量级是核心净新增的'
    '十几倍，不截轴深蓝那一段薄得读不出逐月变化'
    + (f'；本图超界的是 {"、".join(_cut5)}，同样是画到边界 + 红色真值。' if _cut5 else '。'),

    '<b>窗口：全部可得历史，不再倒推。</b>此前是「水平柱图 25 个月、滚存桥与核对表 13 个月、'
    '季度图 14 个季度、逐年对照图 6 年、热力矩阵 9 年」，本轮除<b>核对表</b>仍保留近 13 个月'
    '（它是逐行核对用的附录，不是图）之外，全部改为画到序列起点。'
    '数据本身短的（DATs、月末融资余额）按实际长度画，不补零、不外推；'
    '起点落在季中导致的不完整季度（季度图与季度费率图各一个）整根剔除，并在图注里点名。',

    '<b>网页版与 PDF 版的已知差异。</b>（1）PDF 的 deck 里有几张零基线长历史<b>折线</b>图'
    '（客户总资产 / 核心净新增 / 新开账户各一张，末 3 个月还画一个红色虚线圈）；'
    '网页版把它们全部去掉了 —— 各图窗口改成全历史之后，那几张折线与对应的柱图'
    '画的是同一条序列的同一段，只是少了次轴同比。逐月读数用 hover 与右上角「表格」视图；'
    '（2）Exhibit 10 的 PDF 版保留 2 位小数，网页图表引擎的格式器只到 1 位，表格视图仍是 2 位；'
    f'（3）Exhibit 5 的纵轴网页版截在 ±{comma(BR_CAP)} $bn（PDF 不截），'
    '超界值以红色真值标出；'
    f'（4）同比的小基数剔除门槛，PDF 是「基数 &lt; 0.15 × 序列绝对值中位数」，'
    f'网页版提到 {YOY_BASE_MIN:.0%} —— 0.15 挡不住 SCHW 的结构性极小月，'
    '一个 +569% 的基数效应读数会把整条次轴压平；'
    '（5）比率的同比/环比，PDF 印整数 pp，网页版保留 1 位小数（|差| &lt; 1pp 时改印 bp）；'
    '（6）Exhibit 3 的柱顶标签加了 $ 前缀、Exhibit 14 的格内数字加了 % 后缀，PDF 是裸数字；'
    '（7）<b>窗口不同</b>：PDF 的 deck 用的是倒推窗口，本页改画全部可得历史，'
    '所以同一张图上网页版的点数远多于 PDF，两边的轴范围与均值不可直接对照。'
    '次轴口径两边现在一致（都是单月同比）—— 这是本轮改回来的。'
    '所有数值与格式化都在 Python 侧完成，页面不做任何计算。',
]

# 抬头一律 y/y 与 m/m 都写。只写 y/y 会挑出一个纯正面的印象：本月客户总资产的
# y/y 是 +21.6%，m/m 却是 −0.4%，只报前者等于把当月的转向藏进汇总表里。
# 比率类（年化有机增长率）按 CONTRACT §2 用 pp/bp，不用百分比变化。
def _dpair(y, m, pct_diff=False, ylab='y/y'):
    """(y/y, m/m) → 「（+47% y/y·单月 / +26% m/m）」；两个都算不出就整段不写。

    ylab 仍然把口径写进标签。本页 2026-08-15 起全页只剩单月一种月度同比口径，
    标签看起来变成了冗余 —— 但抬头是多数人唯一会读的一行，也是最容易被截图单独传播的
    一行，页面上另有 Exhibit 3 的季度合计同比，标签留着才让这一行离开页面之后仍然自洽。
    """
    def one(v, suf):
        if v is None or not np.isfinite(v):
            return None
        if pct_diff:
            return (signed(v * 100, 0, 'bp') if abs(v) < 1 else signed(v, 2, 'pp')) + f' {suf}'
        return signed(v, 0, '%') + f' {suf}'
    parts = [t for t in (one(y, ylab), one(m, 'm/m')) if t]
    return f'（{" / ".join(parts)}）' if parts else ''


# 抬头的同比一律与图上那条金线、与汇总表 y/y 列同口径（单月）。
# 此前流量两项走的是滚动口径（因为当时 Exhibit 2 画的就是滚动），本轮跟着次轴一起改回来 ——
# 抬头与图不同口径，读者第一眼就会拿这一行去核那条线，然后对不上。
# 单月口径挑出来的数可能比滚动大得多（core NNA 本月单月 vs 滚动差十几 pp），
# 所以 m/m 必须同时印：只报 y/y 会挑出一个纯正面的印象。
_hy_nna = _y_nna
_hy_og = _y_og

headline = (
    f'核心净新增资产 {money(_lat_nna, 1)}bn'
    + _dpair(_hy_nna, _m_nna, ylab='y/y·单月')
    + f' · 年化有机增长率 {_lat_og:.1f}%'
    + _dpair(_hy_og, _m_og, pct_diff=True, ylab='y/y·单月')
    + f' · 客户总资产 {money(_lat_at, 2)}tn' + _dpair(_y_at, _m_at, ylab='y/y·单月')
    + f' · 日均交易 {_lat_dm:.1f}mn 笔/日' + _dpair(_y_dm, _m_dm, ylab='y/y·单月')
    + f' · 月末融资余额 {money(_lat_mb, 1)}bn' + _dpair(_y_mb, _m_mb, ylab='y/y·单月')
)


def _hi_streak(a, i):
    """从 i 往回数：连续多少个月的读数都是「截至当月为止的历史最高」。

    「又创新高」在一条爬坡序列上每个月都成立，是噪音不是信息（brief.py 的 T3）。
    有信息量的是**连了几个月**。返回 0 表示本月根本不在高点上。
    缺值月按「断了」处理，不跨过去续数。
    """
    a = np.asarray(a, float)
    k = 0
    while i - k >= 0 and np.isfinite(a[i - k]) and a[i - k] >= np.nanmax(a[:i - k + 1]):
        k += 1
    return k


# brief 的字数下界从 render 的签名里读一次，不在本文件里再写一遍数字 ——
# 口径只能有一处定义，各写各的正是同一条规则在两处判定相反的原因。
BRIEF_MIN = inspect.signature(B.render).parameters['lo'].default


def _quant(k, n, noun=''):
    """B.quant 的中文外壳：`B.cn(2)` 出的是「二」，量词位置上中文要「两」。

    共享库不改（那是全站口径），在调用侧把这一个字修掉。判据仍完全由 B.quant 决定 ——
    「只有/有/多达」跟着算出来的占比走，这里只动字形。
    """
    return B.quant(k, n, noun).replace('二个', '两个').replace('二条', '两条')


def _rank_txt(rk, n):
    """名次文案。前一半报「第 R（前 X%）」，后一半报「倒数第 M」。

    `B.top_pct` 对末位给出「前 100%」—— 数学上没错，读起来却等于没说。名次落在后半段时
    真正的信息是「离底还有几名」，所以换成倒数。两个分支都由算出来的 rk/n 选。
    """
    return (f'第{rk}、属{B.top_pct(rk, n)}' if rk * 2 <= n else f'倒数第{n - rk + 1}')


def compose_brief(frame=None):
    """SCHW 页顶部的 ~300 字数据总结（payload 的 `brief` 字段）。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R3 日历护栏 / R4 单位恒等 /
    R5 标注 / R6 有效位），那边只算事实，句子在这里拼 —— 措辞是口径的一部分。
    每个数字都当场从序列算，**没有一处硬编码**：排名、倍数、峰值月、连涨月数、披露史
    长度，下个月重跑都会自己变。**定性词同样不写死**：「只有/多达」走 `B.quant()`，
    「回落/走高」「净流入/净流出」「扩张/收缩」全部由当场算出的符号选分支 ——
    写死的措辞配一个算出来的数字，是这一段历史上最高频的一类 bug。

    `frame` 只给自检用：传 `df.iloc[:k]` 就能把序列截到过去任一个月重跑，确认那个月
    既不抛异常也不印自相矛盾的句子。缺值时**该句不写**（`B.need()`），不让一段解读
    把整页构建拖垮 —— 早于 2025-01 的月份没有融资余额与 DATs，s1 会自动缩编、s4 整句消失。

    ═══ 与同比口径的两轮改造（CONTRACT §6）的关系 ═══
    2026-08 那一轮把流量图的次轴改成 12 个月滚动合计同比，本段当时被要求逐处标「单月」，
    以免读者拿它去对图上的滚动金线。**2026-08-15 这一轮又把次轴改回了单月**，全页
    （次轴、汇总表 y/y 列、headline、本段）现在是同一个口径 —— 那些「单月」标注
    因此从「防混淆」变成了「防再次改口径」：留着它们，下一次谁再动次轴口径，
    这一段仍然自洽，而不是悄悄变成一句对不上的话。
    口径统一不改变本段的读法纪律：单月同比的分母是去年那一个月，拿它当「趋势」读
    正是本页反复踩过的坑（core NNA 的 Aug-24 单月 +569%，同月滚动 −13%），
    所以本段的同比只作「本月对去年同月」的读数用，落点句一律锚定「较去年同月」，
    不作趋势断言 —— 趋势看季度图（Exhibit 3）与逐年对照（Exhibit 11–13）。
    R4 恒等式里的三个同比同样逐一标「单月」：恒等式两边必须同口径。

    ═══ SCHW 独有，别家不能照抄 ═══
      · **季节轴按「同一日历月」对齐，不是「上一个季末月」。** 3/6/9/12 月没有独立月报、
        数取自季报，core NNA 在这四个月系统性抬升；但 3→6 本身就是个结构性台阶
        （2026-08-17 实测：10 次里 8 次为负，中位 −25%），拿「比上一个季末月低两成」
        当动能读，测到的仍是季节位置，正是这段要治的病。所以位次一律按同一日历月排（6 月对历年 6 月）。
        季节幅度也不再用「四个季末月合并对其余月份」的那个 1.5× —— 四个季末月差得很远
        （Dec 2.1×、Mar 1.8×、Jun 1.1×、Sep 1.1×），拿 1.5× 描述一个 6 月读数会高估
        该打的折扣。改成**本月这个日历月对上月那个日历月的历史中位数之比**：环比比的
        就是这两个月，这个比值正好是环比里季节该占的那一份。两组中位数都显式剔除本次
        的观测（拿被解释的观测去解释自己是循环），并且用「中位数之比」而不是「逐年环比
        的中位数」—— 后者分母是单月读数，4 月这种贴近 0 的月份会把比值放大到几百倍，
        测的是基数不是季节。分母中位数 ≤ 0 时这一截整个不写，只留同月位次。
      · **R3 日历护栏在这一页完全不成立。** `dats_k` 公司披露的就是 daily average
        trades（已日均化），`core_nna` / `margin_balances` 是月度流量与月末时点值，
        三者都不是「当月合计量」，series/schw.csv 里也没有交易日列。再除一次交易日
        会造出一个根本不存在的修正（brief.py 头部点名的坑）。
      · **R1 在这一页放宽了 `peak_scan` 的「只放存量」约束**：`dats_k` 是「笔/日」的
        强度率而非存量，本来不该进 LV。放它进来是因为本页只有三条非流量序列，去掉它
        「几条里有几条在峰上」就退化成两选一；代价是措辞必须跟着改 —— 文中一律写
        「水平/强度指标」，不写「水平指标」。core NNA 与新开账户是**流量**，仍然不进。
      · **客户资产环比转跌而 core NNA 为正是 SCHW 的常态而非异常**（Exhibit 5 的恒等式：
        期末 − 期初 = core NNA + 市值变动，后者是轧差项、非披露值）。所以本页把
        「资产下跌月里有多少个伴随正净流入」当成一条读法规则写出来，而不是当新闻。
        这一句只报那个共现计数与落点，**不把环比拆成「市值变动 vs 流量」两项并给出
        各自的量**（贡献度拆解是 brief 的禁区，恒等式本身由 Exhibit 5 负责画）。
      · **两组序列的样本深度差 8 倍**：客户资产有 155 个月（2026-08-16 回填到 2013-09），
        DATs 与月末融资余额是 2026-01 月报才开始披露的（回溯到 2025-01），只有 19 个月。
        差距比回填前（98 vs 18）又拉开了一档。同一句「创新高」在这两组里
        分量不同 —— 这是 T3 在本页的变体：挡不住的不是单调，是**样本太浅**。所以凡是
        「刷新新高」都要同时报连涨月数与披露史长度，s1 与 s4 用的是同一条 mb 序列，
        护栏两处都要带。
      · core NNA 的位次跨 2025 年的 $10bn→$25bn 剔除门槛（BRK），月报不重述历史，
        所以同月排名只读位次、不读幅度，句子里必须带这句限定。
    """
    d = df if frame is None else frame
    ALLm = [str(p) for p in d.index]
    i = len(ALLm) - 1
    n_all = len(ALLm)
    if i < 1:
        return ''
    A = lambda s: np.asarray(s, float)
    v_at = A(d['total_client_assets_usdbn'].values)
    v_nna = A(d['core_nna_usdbn'].values)
    v_mb = A(d['margin_balances_usdbn'].values)
    v_dm = A(d['dats_k'].values)

    # ── R1：峰值扫描。只放**水平/强度**读数，不放月度流量（docstring 第三条）。
    #    三条都不是单调序列（客户资产 98 个月里有 28 个下跌月，B.is_monotonic 判 False），
    #    所以不 skip。本月还没有读数的列先摘掉：peak_scan 会跳过它们，但「几个指标」
    #    这个分母要跟着缩，否则 2025-01 之前会印出「三个指标里只有一个……」而另两个
    #    根本还没开始披露。
    #    LV0 是显式白名单，不扫 df 的列名 —— 2026-08 同比口径改造给 df 加的派生列
    #    （organic_growth_roll 等）是比率/流量的衍生口径，不是水平/强度读数，
    #    按构造就进不来；往 LV0 里添列时先过 docstring 第三条再动手。
    LV0 = [('客户总资产', v_at), ('月末融资余额', v_mb), ('日均交易', v_dm)]
    LV = [(nm, a) for nm, a in LV0 if B.need(a[i])]
    absent = [nm for nm, a in LV0 if not B.need(a[i])]
    NOBS = {nm: int(np.isfinite(a).sum()) for nm, a in LV}
    pk = B.peak_scan(ALLm, LV, i, skip_monotonic=False)
    at, off = pk['at_peak'], pk['off_peak']
    # 「刷新新高」一律带连涨月数（T3）：只报「又新高」在爬坡序列上每月都成立，是噪音。
    hi = {nm: _hi_streak(a, i) for nm, a in LV if nm in at}
    # 连 2 个月以上就报连涨月数（T3）；只连了 1 个月的，有信息量的是「上一个高点在哪」
    # —— 那句话回答的是「这是久违的新高还是一路走上来的」，连涨月数回答不了。
    SER = dict(LV)

    def _hi_tag(nm):
        if hi[nm] >= 2:
            return f'连{hi[nm]}月'
        prior = SER[nm][:i]
        # 本月是这条序列的第一个读数时没有「上一个高点」：nanargmax 会在全 NaN 上
        # 直接 ValueError（2025-01 的融资余额/日均交易就是这种情形）。
        return f'（上次高点{ALLm[int(np.nanargmax(prior))]}）' if np.isfinite(prior).any() else ''

    at_txt = '、'.join(nm + _hi_tag(nm) for nm in at)
    # 峰值月照样板（build/ibkr.py）的写法：名字先并列，最后统一接一个「峰值停在…」，
    # 而不是每条各挂一个括号 —— 两条以上时括号里的逗号与名字之间的顿号会绞在一起，
    # 读者分不清哪个峰值属于谁。距峰值多远不再写：本页的 off 绝大多数时候就是客户
    # 总资产，而它离峰的幅度正是下一句要报的环比，同一个数没必要印两遍。
    off_txt = ('、'.join(nm for nm, _ in off) + '峰值停在'
               + '、'.join(sorted({k for _, k in off}))) if off else ''
    if len(LV) < 2:
        # 只剩一条序列时不写「一个指标里只有一个……」：那句话的信息量是零，
        # 而「N 个里有几个」的框架在 N=1 时本来就退化。
        head = f'{at_txt}刷新新高' if at else off_txt
    elif at and off:
        head = (f'{B.cn(len(LV))}个水平/强度指标{_quant(len(off), len(LV), "个")}'
                f'没跟上：{off_txt}；{at_txt}刷新新高')
    elif at:
        head = f'{B.cn(len(LV))}个水平/强度指标本月全部刷新新高：{at_txt}'
    else:
        head = f'{B.cn(len(LV))}个水平/强度指标本月无一刷新新高：{off_txt}'
    # 浅样本护栏：刷新新高的那几条里，披露史短于全序列的必须把月数一起报出来。
    # （全序列多长写在页面 subtitle 里，这里不重复。）
    thin = [nm for nm in at if NOBS[nm] < n_all]
    shallow = sorted({NOBS[nm] for nm in thin})
    # 刷新的不全是浅序列时要点名，否则「但披露史只有 1 个月」会被读成三条都只有 1 个月。
    who = '' if len(thin) == len(at) else '、'.join(thin) + '的'
    # 「只有」是定性词，得由算出来的比例决定：18/98 配得上「只有」，97/98 就不配。
    few = '只有' if shallow and max(shallow) * 2 <= n_all else '有'
    s1 = head + (f'，但{who}披露史{few}{"/".join(str(x) for x in shallow)}个月。'
                 if shallow else '。')

    # ── R2：客户总资产的基数护栏，落点是「资产跌 ≠ 撤资」（docstring 第四条）。
    #    句式照样板 s2：读数 → 环比（连上月读数一起给）→ 上月的位次 → 同比 → 一句落点。
    #    同比标「单月」（docstring 的口径一段）：客户总资产是存量，Exhibit 6 的次轴与
    #    汇总表 y/y 列都是单月口径，这里与它们同数。标注留着是为下一次改口径防呆，
    #    见 docstring 的口径一段。
    s2 = ''
    be = B.base_effect(v_at, i)
    if B.need(v_at[i], v_at[i - 1]) and be['mm'] is not None:
        ch = float(v_at[i] - v_at[i - 1])
        # R2 要求两种情形都给上月的位次：环比与同比反号时（读者会把基数当趋势），
        # 以及上月本身就落在全样本前三高时（那个环比是被上月的极值顶出来的）。
        show_base = be['conflict'] or (be['prev_rank'] or 99) <= 3
        mm_txt = f'{abs(be["mm"]) * 100:.1f}'
        # 方向词按符号选：资产上行的月份写「跌」是反的。四舍五入后为 0 时整个换成
        # 「持平」——「跌 0.0%」是既给了方向又没给量的组合，读者只会停下来猜。
        s2 = (f'客户总资产环比与上月{money(v_at[i - 1] / 1000, 2)}tn持平'
              if mm_txt == '0.0' else
              f'客户总资产环比从{money(v_at[i - 1] / 1000, 2)}tn'
              f'{"跌" if ch < 0 else "涨"}{mm_txt}%')
        if show_base:
            s2 += ('，但上月是全样本'
                   + ('最高月' if be['prev_is_max'] else f'第{be["prev_rank"]}高月'))
        if be['yy'] is not None:
            s2 += f'，单月同比{B.pct(be["yy"])}'
        dn = [j for j in range(1, n_all)
              if B.need(v_at[j], v_at[j - 1]) and v_at[j] < v_at[j - 1]]
        both = [j for j in dn if B.need(v_nna[j]) and v_nna[j] > 0]
        if dn:
            # 「读反了」这句得同时满足两条，两条都是算出来的：历史上正流入确实占多数
            # （判据与 B.quant 的「多达」同一条），且本月流量自己也是正的。
            flip = len(both) * 3 >= len(dn) * 2 and B.need(v_nna[i]) and v_nna[i] > 0
            # 两个计数相等时只印一个数：「1 个下跌月多达一个伴随正净流入」
            # 既啰嗦又会把阿拉伯数字和中文数字并排摆着。
            share = ('全部' if len(both) == len(dn)
                     else _quant(len(both), len(dn), '个'))
            s2 += (f'；{len(dn)}个资产下跌月{share}伴随正净流入'
                   + ('，<b>读成撤资就读反了</b>。' if flip else '。'))
        else:
            s2 += '。'

    # ── 季节轴：同一日历月对同一日历月（docstring 第一条）。位置对应样板的「先扣日历」
    #    ——R3 在本页不成立（见 docstring 第二条），季节就是它在这一页的对应物。
    s3 = ''
    cal, pcal = int(ALLm[i][5:7]), int(ALLm[i - 1][5:7])
    qe = lambda k: int(k[5:7]) in (3, 6, 9, 12)
    same = [j for j in range(n_all) if int(ALLm[j][5:7]) == cal and B.need(v_nna[j])]
    hist = [j for j in same if j != i]                       # 同月历史，剔除本月自身
    # 环比这一步的季节基准 = 「本月这个日历月」对「上月那个日历月」的历史中位数之比。
    # 用中位数之比而不是逐年环比的中位数：后者的分母是单月读数，4 月这种接近 0 的月份
    # 会把比值放大到几百倍，测的是基数不是季节。两组都剔除本次的两个观测。
    pbase = [j for j in range(n_all) if int(ALLm[j][5:7]) == pcal
             and j != i - 1 and B.need(v_nna[j])]
    if hist and B.need(v_nna[i]):
        rk_same = int(np.sum(v_nna[same] > v_nna[i])) + 1
        # 读数与位次摆在一起（样板 s2 的写法：「净新增131.8千户…排历史第4」）。
        # 原来这一句从头到尾没印过核心净新增本身，读者只看到一个名次——而这条正是
        # 全页的主指标，位次挂在一个没说出口的数上，等于把它藏进了汇总表。
        tail = (f'按同一日历月排，本月的{money(v_nna[i], 1)}bn是{len(same)}个{cal}月里'
                f'{"最高" if rk_same == 1 else f"第{rk_same}高"}，'
                f'跨{BRK.year}年门槛调整只读位次')
        # 季节台阶算得出来就当前缀写上，算不出（4 月这种中位数落到 0 附近甚至为负的
        # 月份做分母）就只留同月位次 —— 位次才是这一句非有不可的部分。
        step_txt = ''
        if pbase:
            m_hist = float(np.median(v_nna[hist]))
            m_prev = float(np.median(v_nna[pbase]))
            if m_prev > 0 and m_hist > 0:
                step = m_hist / m_prev
                # 比值小于 0.1 时给两位小数：4 月对 3 月是 0.04 倍，按一位印出来是
                # 「0.0 倍」，读起来像「等于零」，那是把一个真实的季节塌陷印成了缺失。
                sx = f'{step:.2f}' if step < 0.1 else f'{step:.1f}'
                # 抬高这一档的原因只在本月确是季末月、且这一步确实向上时才写 ——
                # 5 月对 4 月同样是往上一大截，那是缴税季结束，不是季末机构流入。
                tag = ['季末机构流入'] if (qe(ALLm[i]) and not qe(ALLm[i - 1])
                                          and step > 1) else []
                # 「数取自季报」是来源不是原因（来源换了数值不会变），所以只在这一步
                # 真的碰到季末月时作为口径提示出现，且不放在解释位。两条并进同一个
                # 括号：括号套括号、一句里挂两组括号都是分寸失控的样子。
                if qe(ALLm[i]) or qe(ALLm[i - 1]):
                    tag.append('数取自季报')
                step_txt = (f'核心净新增在{cal}月的历史中位数是{pcal}月的{sx}倍'
                            + (f'（{"，".join(tag)}）' if tag else '') + '；')
        s3 = f'先扣季节：{step_txt}{tail}' if step_txt else f'核心净新增{tail}'
        yy = (v_nna[i] / v_nna[i - 12] - 1 if i >= 12
              and B.need(v_nna[i], v_nna[i - 12]) and v_nna[i - 12] > 0 else None)
        mm = (v_nna[i] / v_nna[i - 1] - 1
              if B.need(v_nna[i], v_nna[i - 1]) and v_nna[i - 1] > 0 else None)
        # 「反号」在 s2 里指的是资产的 m/m vs y/y，这里指的是另一件事，换个说法免得
        # 两句连着读像同一件事重复了一遍。口径必须点名「单月」：core NNA 的图
        # （Exhibit 2）现在也画单月同比，两者同数；但季度图（Exhibit 3）的绿线是季度
        # 合计同比，与这半句可以差出几十个 pp 甚至反号（core NNA 的 Aug-24：单月 +569%
        # vs 滚动 −13%，季度口径同理会平掉）。反号本身只当基数警示报（R2），不作趋势判断。
        s3 += ('，单月同比与环比反向。' if yy is not None and mm is not None
                                        and (yy < 0) != (mm < 0) else '。')

    # ── R4：单位恒等。融资余额/客户资产是**推导值**（公司只分别披露分子与分母，R5）。
    #    措辞照样板走「同比 X%，是分子 A% 除以分母 B% 的商，+ 一句落点」的口语式恒等：
    #    印出来的 X% 是比率序列自己当场算的同比，不是把 A 与 B 直接相除得来的数。
    #    显式写成「增长指数 1.98 ÷ 1.22」那种贡献度拆解，brief 里不写（那是 Exhibit 的活）。
    #    三个同比逐一标「单月」（docstring 的口径一段）：恒等式两边必须同口径，而分子
    #    融资余额在 Exhibit 9、分母客户资产在 Exhibit 6，两条次轴现在都是单月口径，
    #    与这里同数。落点锚定「较去年同月」，不作趋势断言。
    s4 = ''
    pu = B.per_unit(v_mb, v_at, i, scale=100)
    r = pu['series']
    if (B.need(pu['value']) and i >= 12 and B.need(r[i - 12]) and r[i - 12] > 0
            and B.need(pu.get('num_yoy'), pu.get('den_yoy'))):
        st = _hi_streak(r, i)
        nfin = int(np.isfinite(r).sum())
        lead = (f'连{st}月刷新最高' if pu['is_max'] and st >= 2
                else ('刷新披露以来最高' if pu['is_max']
                      else f'排披露以来{_rank_txt(B.rank_of(r, i), nfin)}'))
        r_yoy = float(r[i] / r[i - 12] - 1)
        # T3 的浅样本护栏要跟着 mb 序列走到这一句（s1 挂了、s4 用的是同一条序列，
        # 两处都要带），但并进「（推导值，样本N个月）」一个括号里，不另起半句。
        s4 = (f'融资余额/客户资产<b>{B.num(pu["value"], 2)}%</b>（推导值，样本{nfin}个月）'
              # 序列本身已经是百分数，只印百分比变化会被读成 pp，故补一个 pp 折合；
              # pp 差不能再过 B.pct（它会再乘一次 100），走本页的 signed()
              # （与汇总表 pp/bp 口径同源），|差| 再小也不印「+0pp」。
              f'{lead}，单月同比{B.pct(r_yoy)}（{signed(r[i] - r[i - 12], 2, "pp")}），'
              f'是融资余额单月{B.pct(pu["num_yoy"])}除以客户资产单月{B.pct(pu["den_yoy"])}的商，'
              f'杠杆较去年同月在{"扩张" if r_yoy > 0 else "收缩"}。')
    else:
        # 杠杆率这一句算不出（2026-01 之前没有月末融资余额，2026-01 起也还要满 12 个月
        # 才有同比基数）。缺值不是让整页失败的理由，也不该留一段空白 —— 改讲同样是
        # **推导值**、且从序列第二个月起就一直算得出来的年化有机增长率。
        og_v = A(d['organic_growth_ann'].values)
        fin = [j for j in range(n_all) if B.need(og_v[j])]
        if B.need(og_v[i]) and len(fin) >= 2:
            rk_og = B.rank_of(og_v, i)
            w12 = [j for j in fin if i - 12 <= j <= i]
            why = (f'{"、".join(absent)}本月尚无披露' if absent
                   else '月末融资余额还不满12个月、凑不出同比基数')
            med12 = float(np.median(og_v[w12]))
            gap = float(og_v[i]) - med12
            # 括号里的口径不为省字删：「年化有机增长率」不是公司披露的字段，读者不知道
            # 它是怎么来的就没法判断它跟核心净新增是不是同一件事说两遍。「单月」也不能
            # 省：本页另有滚动 12 个月口径的有机增速（不上图，只在页尾「口径说明」里
            # 作对照读数；Exhibit 14 的标题同样写明画的是「单月年化」）。
            s4 = (f'{why}，融资余额/客户资产的同比读不出；改看单月年化有机增长率'
                  f'<b>{og_v[i]:.1f}%</b>（推导值：核心净新增×12÷上月末资产），'
                  f'在{len(fin)}个月里{_rank_txt(rk_og, len(fin))}，'
                  # 差值走本页的 signed()：四舍五入成 0 时它会自己多给一位小数，
                  # 不会印出「低 0.0pp」这种既有方向词又没有量的组合。差值**恰好**为 0
                  # 时 signed 会给出带正号的「+0.0pp」，那时候直接说「持平」。
                  + (f'与近{len(w12)}个月中位数持平。' if gap == 0 else
                     f'较近{len(w12)}个月中位数{med12:.1f}%（{signed(gap, 1, "pp")}）。'))

    live = [s for s in (s1, s2, s3, s4) if s]
    # 序列刚开头时凑不出一段能读的解读。这时**整段不写**，而不是拿一段 90 字的残句
    # 去撞 render() 的下界护栏 —— 那个护栏是给「模板拼坏了」用的，不该被数据不足触发。
    # 超长仍然交给 render 去响：那才真的是模板坏了。
    if len(re.sub(r'<[^>]+>', '', ''.join(live))) < BRIEF_MIN:
        return ''
    return B.render(live)


payload = {
    'ticker': 'schw',
    'tracker': 'SCHW Monthly Activity Tracker',
    'title': f'Charles Schwab (SCHW)：月度经营指标跟踪 — {LATEST.year} 年 {LATEST.month} 月',
    'data_through': str(LATEST),
    'through_label': f'{LATEST.year} 年 {LATEST.month} 月',
    'subtitle': (f'Schwab Monthly Activity Report · 覆盖 {mlab(df.index[0])} – {mlab(LATEST)}'
                 f'（{len(df)} 个月）· 版式沿用 Goldman Sachs GIR 的 monthly-metrics 体例'
                 '（SCHW First Take 的恒等式滚存桥 + LPLA 的流量口径规矩）· 仅图表，无观点'),
    'headline': headline,
    # 那一行给读数，这一段给「读数该怎么读」。见 compose_brief 的 docstring。
    'brief': compose_brief(),
    'hub_line': (f'客户资产 {money(_lat_at, 2)}tn · 核心净新增 {money(_lat_nna, 1)}bn · '
                 f'年化有机增长 {_lat_og:.1f}%'),
    'source': SRC,
    'xlabels': XL,
    'xlabels_long': XL_LONG,
    'summary': summary,
    'exhibits': ex,
    'table': table,
    'notes': notes,
    'footer': ('数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
               '仅供个人研究，不构成投资建议'),
}

# 抬头的「官方发布于 …」：按 data_through 那个月去台账里查（fetch/schw.py 摄入时记的，
# 来自新闻稿电头）。查不到就整个字段不写 —— 渲染端判的是字段在不在，写 None 或空串
# 会让页面印出「官方发布于 」这么半句。
_src_date = _source_dates().lookup(SERIES, 'schw', str(LATEST))
if _src_date:
    payload['source_date'] = _src_date


def main():
    out_dir = os.path.join(ROOT, 'data')
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'schw.js')
    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(path, payload, 'schw')
    print(f'数据截至 {LATEST} | 全序列 {df.index[0]} → {df.index[-1]}（{len(df)} 个月）')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）'
          f' + Exhibit {table["n"]} 核对表')
    print(f'写出 data/schw.js  ({os.path.getsize(path) / 1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
