# -*- coding: utf-8 -*-
"""Charles Schwab (SCHW) 月度 Activity Report —— 网页看板 payload 生成器。

把 build/build_schw.py（matplotlib → PDF）里的每一张 exhibit 逐张移植成
data/schw.js 里的一个 exhibit 对象。图序、编号、标题文案、图注、截轴设置照搬原 deck。

模版来源（与 PDF 版同）：
  · Goldman Sachs「SCHW First Take」Exhibit 2 的**恒等式滚存桥**
    （期初 BOP + 净新增 + 市值变动 = 期末 EOP）—— 让月度数据可无损累加到季度，
    是「用月度抢跑季报」的地基，本页的 Exhibit 4 即此图。
  · Goldman Sachs「LPLA monthly metrics」Exhibit 1 的口径规矩：**流量类不算环比百分比，
    改用年化有机增长率**（当月净新增 x 12 / 上月末资产），本页 Exhibit 3 采用。
  · GS「IBKR Monthly」的成对图法（水平柱 + 均线 + YoY/MoM 气泡 ⇄ 变化率曲线）。

数据源：series/schw.csv（Schwab Monthly Activity Report，次月 12-14 日）、
        series/schw_avg_margin.csv（2020-04 至 2025-12 的平均融资余额，之后停发）、
        series/fee_rates.csv（季报口径的生息资产与 NIM）。
季末月（3/6/9/12）无独立月报，该月数值取自当季季报，故序列连续。

所有数值与格式化都在这里算完，页面不做任何计算。构建日期只写文件首行注释，
不进 payload —— 进了 payload，monthly_run 的「data 有没有实质变化」检查会永久失效。
"""
import datetime
import json
import os

import numpy as np
import pandas as pd

import payload_guard
import pctile          # 汇总表 3Y %ile 的唯一实现，各页不再各写各的（见该模块 docstring）

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
    (1) 下面 assets.diff() 会把两个月的资产变动全记到后一个月，Exhibit 4 恒等式桥的
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
# 它是 Exhibit 3 次轴同比的基础 —— 单月年化率本身就是把一个月的噪音乘 12，
# 拿它再算同比等于把噪音平方一次（本页实测：单月年化率的相邻月最大跳变 7.1pp，
# 滚动口径 0.4pp，17 倍差距）。
df['organic_growth_roll'] = nna.rolling(12).sum() / assets.shift(12) * 100
df['dats_mn'] = df['dats_k'] / 1000.0
df['assets_tn'] = assets / 1000.0
# 2020-10 新开经纪账户 14,718k 系 TD Ameritrade 收购一次性并表
df['new_acct_ex'] = df['new_brokerage_accounts_k'].copy()
df.loc[pd.Period('2020-10', 'M'), 'new_acct_ex'] = np.nan

avgm = pd.read_csv(os.path.join(SERIES, 'schw_avg_margin.csv'))
avgm['month'] = month_index(avgm['month'])
avgm = avgm.set_index('month').sort_index()['avg_margin_balances_usdbn'].astype(float)
assert_monthly(avgm.index, 'series/schw_avg_margin.csv')   # Exhibit 10 同样按位置画

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
_ca_q = assets.groupby(assets.index.asfreq('Q')).mean()
_ratio = (_iea / _ca_q.reindex(_iea.index) * 100).dropna()
_bs_idx = pd.PeriodIndex([q.asfreq('M', 'end') for q in _ratio.index], freq='M')
_bs = pd.DataFrame({'iea_share': _ratio.values,
                    'nim': _nim.reindex(_ratio.index).values}, index=_bs_idx)

# ── 费率的「有效期」：本页月度数据每月前推，fee_rates.csv 每季才更新一次 ──
# 两张表节奏不同，所以「这张图用的是哪一季的费率、月度数据已经走到哪个月」这件事
# 长期存在，而且每个月的答案都不一样。它不是 bug，是口径 —— 但读者有权知道，
# 尤其当官方财报延迟、费率落后两个季度以上时。
# 下面四个量全部现算：写死季度号的话，下一季页面上就是一句假话
# （本文件已经为「过去 32 个季度单边降」返工过一次，同一个坑不踩第二遍）。
_FEE_USED_Q = _ratio.index[-1]                  # Exhibit 13 实际画到的最后一季
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


def yoy_series(s, win, pct_series=False):
    """窗口内逐月同比，喂 gs_bar 的次轴折线（口径同 gsx.lvl_bar，逐点判断基数）。"""
    s = s.dropna()
    scale = _scale_of(s)
    out = [_yoy_pair(float(s.iloc[i]), float(s.loc[p - 12]), scale, pct_series)
           if (p - 12) in s.index else None for i, p in enumerate(s.index)]
    return [None if v is None else round(v, 6) for v in out[-win:]]


def yoy_gap_note(s, win, pct_series=False):
    """窗口内哪些月因为「基数过小/异号」被放弃了同比 —— 图上是断口，必须交代。

    现算不写死：门槛、窗口、数据都会滚动，写死月份名迟早变成假话。
    """
    if pct_series:
        return ''
    s = s.dropna()
    scale = _scale_of(s)
    gaps = [mlab(p) for p in s.index[-win:]
            if (p - 12) in s.index
            and _yoy_pair(float(s.loc[p]), float(s.loc[p - 12]), scale, False) is None]
    if not gaps:
        return ''
    return f'本窗口内 {"、".join(gaps)} 的去年同月基数过小，同比作废，折线在该月断开。'


def yoy_axis(s, win, pct_series=False):
    """gs_bar 的次轴 y/y 折线。给了它引擎就不画 12 个月均线（engine_kinds.md §8）。

    为什么整页的水平柱图都从「均线」换成「次轴同比」：这些图对应的是 deck 的
    gsx.lvl_bar，它的 docstring 写得很直白 ——「均线只是把柱子再平滑一遍、不带新信息，
    同比才回答『相对去年这个月是好是坏』」。网页版此前一律画均线，是移植时丢的一条规矩。
    """
    return {'name': 'y/y (pp, RHS)' if pct_series else 'y/y (RHS)', 'color': 'GOLD',
            'values': yoy_series(s, win, pct_series),
            'yfmt': 'pp1' if pct_series else 'pct0'}


# ────────────────── 12 个月滚动合计同比（流量类的默认口径）──────────────────
# 为什么流量类不再画单月同比：单月同比的分母是**去年那一个月**，而流量的月度分布本身
# 带季节性与时点噪音（缴税季、月末结算日落在周几、大额单笔转入的到账月份）。
# 分母越小，同一笔绝对变化被放大得越狠 —— 这不是业务信号，是除法的性质。
# 12 个月滚动合计把整整一年的流量加起来再比，分母是一整年，季节性自动对消，
# 剩下的才是「这一年比上一年多收了多少」。
#
# 本页实测（对齐到两种口径都算得出的同一批月份之后，见 caliber_stats）：
# core NNA 的单月同比标准差是滚动口径的 4.6 倍，相邻月最大跳变 546pp vs 15pp，
# 25 个可比月里有 5 个月两种口径符号相反 —— 最极端的 Aug-24 单月 +569%、滚动 −13%。
# 具体数字一律由 caliber_stats() 现算后插进图注，不写死（数据每月往前滚，写死就是假话）。
#
# ⚠ 只对**流量**这么改。存量 / 期末口径（客户资产、融资余额、账户存量）不许做滚动合计 ——
# 12 个月末值相加不是任何东西；这类序列的点对点同比是合法的，噪声用轴范围解决。
def roll12(s):
    """12 个月滚动合计。不足 12 个月的位置留 NaN（不补零、不外推）。"""
    return s.dropna().rolling(12).sum()


def roll_yoy(s):
    """12 个月滚动合计同比（%），返回与滚动合计同索引的 Series；算不出留 NaN。"""
    r = roll12(s)
    out = pd.Series(np.nan, index=r.index, dtype=float)
    for p in r.index:
        if (p - 12) not in r.index:
            continue
        a, b = float(r.loc[p]), float(r.loc[p - 12])
        if not (np.isfinite(a) and np.isfinite(b)) or b == 0 or a * b < 0:
            continue
        out.loc[p] = (a / b - 1) * 100
    return out


def on(v, idx):
    """把一条 Series 对齐到某张图的 x 索引，缺的位置写 null。

    一律按**月份**对齐而不是按尾部切片：滚动口径天生比原序列少 11 个月，
    切片对齐会整体错位一年（那种错在图上看不出来，只会让人读出一个假趋势）。
    """
    return [None if p not in v.index or not np.isfinite(v.loc[p])
            else round(float(v.loc[p]), 6) for p in idx]


def roll_yoy_axis(s, idx):
    """gs_bar 的次轴折线：12 个月滚动合计同比。给了它引擎就不画 12 个月均线。"""
    return {'name': 'y/y (12M roll, RHS)', 'color': 'GOLD',
            'values': on(roll_yoy(s), idx), 'yfmt': 'pct0'}


def pp_axis(s, idx, name):
    """比率序列的次轴：百分点差（比率不算「百分比的百分比变化」）。"""
    return {'name': name, 'color': 'GOLD',
            'values': on(s - s.shift(12), idx), 'yfmt': 'pp1'}


def caliber_stats(s, idx, roll=None, mono=None):
    """两种口径的实测对比，用于生成图注。返回 None 表示样本不足。

    ⚠ **必须先对齐到两种口径都算得出的同一批月份**再算标准差：滚动口径天然少掉头
    12 个月，不对齐就是拿两个不同样本比波动，样本效应会伪装成口径效应（本轮全站审计
    的方法论要求）。窗口再按 idx 截 —— 图上画的是哪几个月，就用哪几个月说话。
    """
    d = s.dropna()
    m = pd.Series(yoy_series(d, len(d)), index=d.index, dtype=float) if mono is None else mono
    r = roll_yoy(d) if roll is None else roll
    keep = [p for p in idx if p in m.index and p in r.index
            and np.isfinite(m.loc[p]) and np.isfinite(r.loc[p])]
    if len(keep) < 3:
        return None
    A = m.loc[keep].astype(float)
    B = r.loc[keep].astype(float)
    jump = lambda x: float(np.abs(np.diff(x.values)).max()) if len(x) > 1 else float('nan')
    flips = [(mlab(p), float(A.loc[p]), float(B.loc[p])) for p in keep
             if A.loc[p] * B.loc[p] < 0]
    return {'n': len(keep), 'sd_m': float(A.std(ddof=0)), 'sd_r': float(B.std(ddof=0)),
            'jump_m': jump(A), 'jump_r': jump(B), 'flips': flips,
            'lo_m': float(A.min()), 'hi_m': float(A.max()),
            'lo_r': float(B.min()), 'hi_r': float(B.max()),
            'cur_m': float(A.iloc[-1]), 'cur_r': float(B.iloc[-1]), 'first': keep[0],
            'last': keep[-1]}


def roll_note(st, unit='%'):
    """「本图的次轴为什么是滚动 12 个月合计同比」——数字全部来自本页自己的序列，现算。"""
    if st is None:
        return ('次轴为 <b>12 个月滚动合计同比</b>（本年 12 个月合计 ÷ 上年同 12 个月合计 − 1）。'
                '本序列可比月份不足 3 个，两种口径的对比留待历史长起来后自动出现。')
    ratio = st['sd_m'] / st['sd_r'] if st['sd_r'] else float('nan')
    t = (f'次轴金色折线为 <b>12 个月滚动合计同比</b>（本年 12 个月合计 ÷ 上年同 12 个月合计 − 1），'
         f'不是单月同比。理由是实测的，不是偏好：把两种口径<b>对齐到同一批月份</b>后'
         f'（{mlab(st["first"])}–{mlab(st["last"])}，{st["n"]} 个月），'
         f'单月同比的标准差 {st["sd_m"]:,.1f}pp 是滚动口径 {st["sd_r"]:,.1f}pp 的 {ratio:,.1f} 倍，'
         f'相邻月最大跳变 {st["jump_m"]:,.0f}pp vs {st["jump_r"]:,.0f}pp')
    if st['flips']:
        worst = max(st['flips'], key=lambda f: abs(f[1] - f[2]))
        t += (f'，其中 {len(st["flips"])} 个月两种口径<b>符号相反</b>'
              f'（{"、".join(f"{m} 单月 {a:+,.0f}{unit} / 滚动 {b:+,.0f}{unit}" for m, a, b in st["flips"])}）'
              f'—— 最极端的 {worst[0]} 相差 {abs(worst[1] - worst[2]):,.0f}pp，'
              '一个说「翻了几倍」、一个说「在收缩」。')
    else:
        t += '，本窗口内两种口径没有符号相反的月份。'
    t += (f'当期两种口径并排：单月 {st["cur_m"]:+,.1f}{unit}、滚动 {st["cur_r"]:+,.1f}{unit}'
          f'（差 {abs(st["cur_m"] - st["cur_r"]):,.0f}pp）。')
    return t


def stock_note(st, what):
    """存量序列**保留**单月同比的理由，同样现算。

    这一条不是免责声明，是口径判断：12 个月末值相加不是任何东西，
    存量做滚动合计等于把同一笔钱数 12 遍。所以存量只能点对点比。
    """
    if st is None:
        return (f'{what}是<b>期末存量</b>，同比一律点对点（本月末 ÷ 去年同月末），'
                '不做 12 个月滚动合计 —— 12 个月末值相加不是任何东西。')
    ratio = st['sd_m'] / st['sd_r'] if st['sd_r'] else float('nan')
    return (f'次轴仍是<b>单月同比</b>，这是刻意的：{what}是<b>期末存量</b>，'
            '12 个月末值相加不是任何东西（同一笔钱会被数 12 遍），所以存量只能点对点比，'
            '流量那套滚动合计在这里根本不成立。'
            f'代价也实测过：对齐到同一批月份后（{st["n"]} 个月），本序列单月同比标准差 '
            f'{st["sd_m"]:,.1f}pp，若强行按滚动合计算是 {st["sd_r"]:,.1f}pp（{ratio:,.2f} 倍），'
            f'两种口径符号相反的月份 {len(st["flips"])} 个 —— '
            '差别远小于流量类，噪声问题这里用轴范围而不是换口径解决。')


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


# ────────────────────────────── Exhibit 2..18 ──────────────────────────────
ex = []
# 水平柱图的次轴 = 同比折线（同 PDF 的 gsx.lvl_bar），不是 12 个月均线。
# 均线只是把柱子再平滑一遍、不带新信息；这一条是 deck 的既定规矩，移植时曾丢掉。
# 这段只剩**存量**图（Exhibit 5 / 9）在用了：流量图的次轴已改成 12 个月滚动合计同比，
# 小基数剔除门槛在那个口径下根本用不上（分母是一整年的流量，不会接近零）。
YOY_NOTE = ('单月同比的小基数保护：去年同月基数小于本序列绝对值中位数的 '
            f'{YOY_BASE_MIN:.0%}、或与本月异号时不算同比，折线在该月断开 —— '
            '那种月份算出来的是基数效应，不是业务变化。')
_BRK_TXT = (f'红色竖虚线 = 口径断点（{BRK}）：单一客户流入的剔除门槛自该期起从 $10bn 提到 '
            '$25bn，月报不重述历史，线左右两侧不可直读，跨断点的同比与均值同样要打折扣。')


def brk_note(i):
    """断点滚出窗口时不要留下「红色竖虚线」这句 —— 那就成了第二个自相矛盾的图注。"""
    return _BRK_TXT if i is not None else ''

# ── Exhibit 2：核心净新增资产（水平柱，25 个月窗口）──
# 全站审计里最严重的一处单月同比就在这张图：Aug-24 单月同比 +569%，同月滚动口径 −13%，
# 相邻月跳变 546pp。+569% 说的是 Aug-23 的 core NNA 只有 $4.9bn（本序列中位数的 16%），
# 不是 Aug-24 有多强。所以次轴换成 12 个月滚动合计同比；柱本身照旧是当月流量。
d2 = tail(nna, 25)
_b2 = brk_idx(d2.index)
ST2 = caliber_stats(nna, d2.index)
ex.append({
    'n': 2, 'kind': 'gs_bar', 'fmt': 'usd1', 'xlabels': xl(nna, 25),
    'title': 'Core net new assets',
    'ylab': '$bn', 'ylab2': '% y/y (12M roll)', 'legend': 'Monthly',
    'values': L(d2.values), 'yoy': roll_yoy_axis(nna, d2.index),
    'mom_txt': oval(mom_of(nna), suffix=' m/m'),
    'break_at': _b2, 'break_label': BRK_LABEL,
    'note': (QNOTE + '。' + roll_note(ST2)
             + '柱仍是<b>当月</b>核心净新增（水平值本身没有口径问题），'
             '换的只是次轴那条折线。'
             '（4 月是结构性极小月：缴税季净流入几乎归零 —— 单月同比正是被这种月份的'
             '基数放大的，滚动合计把它摊进整年后就不再是个问题。）' + brk_note(_b2)),
})

# ── Exhibit 3：年化有机增长率（流量不算环比百分比，改用年化有机增速）──
og = df['organic_growth_ann']
ogr = df['organic_growth_roll']
d3 = tail(og, 25)
_b3 = brk_idx(d3.index)                      # 分子是 core NNA，断点原样传导过来
# 次轴的两个候选口径都是「百分点差」，差别在于**拿哪个水平值去比**：
# 单月年化率（当月流量 x12）还是滚动 12 个月率（整年流量）。实测取后者。
ST3 = caliber_stats(og, d3.index,
                    mono=(og - og.shift(12)), roll=(ogr - ogr.shift(12)))
ex.append({
    'n': 3, 'kind': 'gs_bar', 'fmt': 'pct1', 'yfmt': 'pct0', 'xlabels': xl(og, 25),
    'title': 'Annualised organic growth rate',
    'ylab': '% annualised', 'ylab2': 'pp y/y (12M roll)', 'legend': 'Monthly',
    'values': L(d3.values),
    'yoy': pp_axis(ogr, d3.index, 'y/y (pp, 12M roll, RHS)'),
    'break_at': _b3, 'break_label': BRK_LABEL,
    'note': ('Monthly core NNA x 12 / prior month-end client assets。'
             '这是 GS LPLA 版式的规矩：流量类指标不算环比百分比（分母是上月的流量，'
             '一个月的噪音会被放大成趋势），改用年化有机增长率把流量放回存量的尺度上。'
             '<b>柱是当月年化率，次轴换成了滚动口径的同比</b>：次轴画的是'
             '「滚动 12 个月核心净新增 ÷ 12 个月前的月末客户资产」这条比率的<b>百分点差</b>，'
             '不是当月年化率的百分点差。'
             + (f'把两种口径对齐到同一批月份后（{ST3["n"]} 个月），相邻月最大跳变 '
                f'{ST3["jump_m"]:.1f}pp vs {ST3["jump_r"]:.1f}pp，'
                f'{len(ST3["flips"])} 个月符号相反'
                + (f'（最大的一处 {max(ST3["flips"], key=lambda f: abs(f[1] - f[2]))[0]}：'
                   f'{max(ST3["flips"], key=lambda f: abs(f[1] - f[2]))[1]:+.2f}pp vs '
                   f'{max(ST3["flips"], key=lambda f: abs(f[1] - f[2]))[2]:+.2f}pp）'
                   if ST3['flips'] else '')
                + '；标准差的差距只有 '
                f'{ST3["sd_m"] / ST3["sd_r"]:.2f} 倍 —— 年化率本身已经把流量除以了存量，'
                '一半的噪音在这一步就被吸收了，剩下的那一半才是滚动口径解决的。'
                if ST3 else '')
             + f'当期读数：当月年化 {float(og.iloc[-1]):.2f}%、'
             f'滚动 12 个月 {float(ogr.dropna().iloc[-1]):.2f}%。'
             '比率序列的同比一律用<b>百分点差（pp）</b>，不算「百分比的百分比变化」。'
             + brk_note(_b3)),
})

# ── Exhibit 4：恒等式滚存桥（GS SCHW First Take Exhibit 2）──
b13 = df.iloc[-13:]
# 13 个月窗口目前整段落在断点右侧，brk_idx 返回 None、引擎不画线；照样传是为了让
# 「凡画 core NNA 的图都带断点」成为数据驱动的不变量，而不是靠人记住哪张图要加。
_b4 = brk_idx(b13.index)
ex.append({
    'n': 4, 'kind': 'bridge_bar', 'fmt': 'usd0', 'xlabels': XL,
    'break_at': _b4, 'break_label': BRK_LABEL,
    'title': 'What moved client assets: flows vs. markets',
    'ylab': '$bn change',
    'stacks': [
        {'name': 'Core net new assets', 'color': 'NAVY', 'values': L(b13['core_nna_usdbn'].values)},
        {'name': 'Market gains (balancing)', 'color': 'BLUE', 'values': L(b13['market_gains'].values)},
    ],
    'net': {'name': 'Total change in client assets',
            'values': L(b13['asset_change'].values)},
    'net_color': 'INK',
    # 截轴：市值变动一项就能跑到 ±800bn，而核心净新增只有 $7–79bn。不截的话轴要摊到
    # −660…+1040（1,700bn 的量程），深蓝那一段厚度只剩 2–3px，「40 还是 79」在图上
    # 完全读不出来 —— 而这张图的全部意义就是「流入 vs 市值」的对比。
    # 按本仓规矩截轴不删点：超界的段画到边界 + 柱端断口符号，该列的真实包络值与净额
    # 一律竖排标出（当前是 2026-03/04/05 三列）。量程从 1,700 收到 620bn，深蓝段厚度
    # 随之翻到 2.7 倍，逐月的流入变化才看得出来。
    'ycap': 420, 'yfloor': -200,
    'cap_note': 'axis capped — true values shown in red',
    'note': ('Identity: opening assets + core NNA + market gains = closing assets。'
             '市值变动是<b>轧差项</b>（= 客户资产环比变动 − 核心净新增），'
             '公司并不单独披露，所以它同时吸收了口径调整、并购转入与真实市场涨跌，'
             '不能整段当成「市场贡献」读。'
             '纵轴截在 +420 / −200：市值变动的量级是核心净新增的十倍以上，不截轴'
             '深蓝那一段就薄得读不出逐月变化。超界的柱画到边界并加断口符号，'
             '真值以红色竖排标出，一个点都没有删。' + brk_note(_b4)),
})

# ── Exhibit 5：客户总资产（水平柱）──
# 存量：**不改口径**。12 个月末的客户资产相加不是任何东西，滚动合计在这里无定义。
atn = df['assets_tn']
d5 = tail(atn, 25)
ST5 = caliber_stats(atn, d5.index)
ex.append({
    'n': 5, 'kind': 'gs_bar', 'fmt': 'usd2', 'xlabels': xl(atn, 25),
    'title': 'Total client assets',
    'ylab': '$tn', 'ylab2': '% y/y (单月)', 'legend': 'Monthly',
    'values': L(d5.values), 'yoy': yoy_axis(atn, 25),
    'note': ('月末余额，官方口径为 $bn，此处除以 1,000 换成 $tn 便于读轴。'
             + stock_note(ST5, '客户总资产')
             + (f'本窗口内单月同比落在 {ST5["lo_m"]:.1f}%–{ST5["hi_m"]:.1f}% 之间、'
                '全程同号，次轴量程本身就是收敛的，不需要再动。' if ST5 else '')
             + YOY_NOTE + yoy_gap_note(atn, 25)),
})

# ── Exhibit 6：新开经纪账户（水平柱）──
# 流量（当月新开户数，不是账户存量）→ 次轴换滚动 12 个月合计同比。
nba = df['new_brokerage_accounts_k']
d6 = tail(nba, 25)
ST6 = caliber_stats(nba, d6.index)
ex.append({
    'n': 6, 'kind': 'gs_bar', 'fmt': 'f0', 'xlabels': xl(nba, 25),
    'title': 'New brokerage accounts opened',
    'ylab': 'k accounts', 'ylab2': '% y/y (12M roll)', 'legend': 'Monthly',
    'values': L(d6.values), 'yoy': roll_yoy_axis(nba, d6.index),
    'note': (QNOTE + '。这一行是<b>当月新开户数</b>（流量），不是账户存量，'
             '所以同比按 12 个月滚动合计算。' + roll_note(ST6)),
})

# ── Exhibit 7：客户总资产全历史 ──
ex.append({
    'n': 7, 'kind': 'lines', 'x': 'long', 'fmt': 'f1', 'xstep': max(1, len(df) // 14),
    'title': 'Total client assets since 2018',
    # zero_base + end_label 补的是 deck 的 long_line 本来就有、网页版一直缺的两件：
    # 零基线（不给就是一次没有标注的隐性截轴，把增长幅度凭空放大）与末点数值
    # （长历史图上唯一的绝对水平锚点，轴刻度间隔按 $tn 计，目测读不出来）。
    'ylab': '$tn', 'zero_base': True, 'end_label': True, 'label_fmt': 'usd2',
    'series': [{'name': 'Total client assets', 'color': 'NAVY', 'values': L(atn.values)}],
    'note': ('Full assembled history。纵轴从 0 起（同 PDF）；末点标出最新读数。'
             'PDF 版在末 3 个月画一个红色虚线圈标出最新窗口，'
             '网页版不画圈 —— 改用 hover 读数与右上角「表格」视图逐月核对。'),
})

# ── Exhibit 8：日均交易笔数 ──
# DATs 是「每天平均多少笔」的流量率，本该走滚动 12 个月合计口径；但 Schwab 从 2026-01
# 的月报才开始披露、滚动表只回溯到 2025-01，序列长度不够 —— 滚动同比要 24 个月
# （12 个月凑出本期合计 + 再 12 个月凑出去年同期合计）。所以这里**按数据长度自动降级**：
# 算得出就画滚动口径，算不出就退回单月同比并在图注里说明这是数据长度限制、不是口径选择。
# 写成自愈判据而不是写死一句「本图用单月」——等历史长到 24 个月，它自己就切过去了。
dm = df['dats_mn']
d8 = tail(dm, 25)
_r8 = roll_yoy(dm)
_r8n = int(np.isfinite(_r8.reindex(d8.index).values.astype(float)).sum())
_ROLL_MIN_N = 6                      # 滚动折线至少要有这么多个点才值得画
if _r8n >= _ROLL_MIN_N:
    _y8, _lab8 = roll_yoy_axis(dm, d8.index), '% y/y (12M roll)'
    _n8note = roll_note(caliber_stats(dm, d8.index))
else:
    _y8, _lab8 = yoy_axis(dm, 25), '% y/y (单月)'
    _n8note = (f'次轴仍是<b>单月同比</b>，这是<b>数据长度</b>的限制、不是口径选择：'
               f'本序列只有 {len(dm.dropna())} 个月（{mlab(dm.dropna().index[0])} 起），'
               '而 12 个月滚动合计同比需要 24 个月才有第一个读数'
               f'（当前只能算出 {_r8n} 个点，低于起画门槛 {_ROLL_MIN_N} 个）。'
               '判据写成条件而不是写死一句话 —— 历史长到 24 个月，这张图会自己切到滚动口径，'
               '不需要有人记得回来改。在那之前，请把次轴当成一个受基数影响的读数看，'
               '趋势以柱本身与右上角「表格」视图为准。')
_n8 = sum(1 for v in _y8['values'] if v is not None)
ex.append({
    'n': 8, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': xl(dm, 25),
    'title': 'Daily average trades',
    'ylab': 'mn trades / day', 'ylab2': _lab8, 'legend': 'Monthly',
    'values': L(d8.values), 'yoy': _y8,
    'mom_txt': oval(mom_of(dm), suffix=' m/m'),
    'note': ('Client DATs first appear in the Jan-2026 report; the 13-month rolling table '
             'reaches back to Jan-2025。'
             f'本图只有 {len(dm.dropna())} 个月的历史（{mlab(dm.dropna().index[0])} 起），'
             '短于 25 个月的窗口设定，不是数据缺失；'
             f'次轴只有最近 {_n8} 个点，更早的月份没有可比基数。' + _n8note),
})

# ── Exhibit 9：月末融资余额 ──
# 存量：**不改口径**（月末余额相加没有意义）。
mb = df['margin_balances_usdbn']
d9 = tail(mb, 25)
_y9 = yoy_axis(mb, 25)
_n9 = sum(1 for v in _y9['values'] if v is not None)
ex.append({
    'n': 9, 'kind': 'gs_bar', 'fmt': 'usd0', 'xlabels': xl(mb, 25),
    'title': 'Month-end margin balances',
    'ylab': '$bn', 'ylab2': '% y/y (单月)', 'legend': 'Monthly',
    'values': L(d9.values), 'yoy': _y9,
    'mom_txt': oval(mom_of(mb), suffix=' m/m'),
    'note': ('Schwab only began disclosing month-end margin balances in the Jan-2026 report; '
             'its 13-month rolling table reaches back to Jan-2025, so the y/y line starts '
             'Jan-2026。口径含 short credits。'
             f'次轴同比同样只有最近 {_n9} 个点。'
             + stock_note(caliber_stats(mb, d9.index), '月末融资余额')
             + YOY_NOTE),
})

# ── Exhibit 10：平均融资余额全历史（与 Exhibit 9 不同口径）──
ex.append({
    'n': 10, 'kind': 'lines', 'fmt': 'f0', 'xlabels': [mlab(p) for p in avgm.index],
    'xstep': max(1, len(avgm) // 14),
    'title': 'Average margin balances since 2020',
    'ylab': '$bn (monthly average)', 'zero_base': True, 'end_label': True, 'label_fmt': 'f0c',
    'series': [{'name': 'Average margin balances', 'color': 'NAVY', 'values': L(avgm.values)}],
    'note': ('Different basis from Exhibit 9: this is the average-balance line Schwab published '
             'Apr-2020 to Dec-2025 and then dropped. It is the only long monthly margin history '
             f'that exists。序列止于 {mlab(avgm.index[-1])}，此后无同口径披露，'
             '不要与 Exhibit 9 的月末余额接续成一条线读。'
             '纵轴从 0 起（同 PDF）；末点标出的是序列最后一个月的读数，不是最新月。'),
})

# ── Exhibit 11：核心净新增资产（季度）──
_q = nna.dropna().groupby(nna.dropna().index.asfreq('Q'))
qsum, qcnt = _q.sum(), _q.count()
QWIN = 14
qv = qsum.iloc[-QWIN:]
qyoy = []
for p in qv.index:
    prev = p - 4
    if prev in qsum.index and qsum.loc[prev]:
        qyoy.append(round(float(qsum.loc[p] / qsum.loc[prev] - 1) * 100, 6))
    else:
        qyoy.append(None)
n_in_last = int(qcnt.iloc[-1])
_b11 = brk_idx(qv.index, BRK_Q)               # 季度轴上断点是 2025Q1，不能传月度 period
ex.append({
    'n': 11, 'kind': 'qtr_bar', 'fmt': 'usd0', 'label_fmt': 'usd0',
    'xlabels': [str(p) for p in qv.index],
    'title': 'Core net new assets by quarter',
    'ylab': '$bn', 'legend': 'Complete quarter',
    'values': L(qv.values), 'partial_months': n_in_last, 'qtr_months': 3,
    # 名字里带口径：本页现在有三种同比口径（滚动 12 个月合计 / 季度合计 / 单月），
    # 图例上不写清楚，读者把这条绿线与 Exhibit 2 的金线放在一起看必然对不上。
    'line': {'name': 'y/y (季度合计, RHS)', 'color': 'GREEN', 'values': qyoy, 'yfmt': 'pct0'},
    'break_at': _b11, 'break_label': BRK_LABEL,
    'note': ('月度核心净新增资产按季汇总（恒等式可无损累加，见 Exhibit 4）。'
             '右轴是<b>季度合计同比</b>（本季 3 个月合计 ÷ 去年同季 3 个月合计），'
             '既不是 Exhibit 2 的 12 个月滚动合计同比，也不是单月同比 —— '
             '三者当期读数并排见页尾「口径说明」。'
             '柱全为正而右轴 y/y 跨零，两轴零点若强行对齐要把左轴拉到 −144、下方四成画布'
             '全空，所以引擎按兜底规则改成两轴各自缩放，并在图内左上角标了'
             '「左右轴零点不同高」—— 右轴的零在那条绿色虚线上，不在柱的基线上。'
             '左轴从 0 起，与 PDF 版一致。'
             + (f'末季 {qv.index[-1]} 已含 {n_in_last} 个月，为完整季度。'
                if n_in_last >= 3 else
                f'末季 {qv.index[-1]} 只含 {n_in_last} 个月，柱为浅蓝且右轴 y/y 已作废 —— '
                '拿不满季的累计去比上年完整季度必然砸出一个假坑。')
             + brk_note(_b11)
             + ('' if _b11 is None else
                f' {BRK_Q}–{BRK_Q + 3} 这四个季度的右轴 y/y 拿新口径比旧口径，'
                '幅度里含口径差，只看方向不看大小。')),
})

# ── Exhibit 12：融资余额环比变化率（与 Exhibit 9 成对）──
mm = (mb.dropna().pct_change() * 100).dropna()
mm = mm.iloc[-25:]
ex.append({
    'n': 12, 'kind': 'gs_line', 'fmt': 'pct1', 'xlabels': [mlab(p) for p in mm.index],
    'title': 'Margin balances, m/m change',
    'ylab': '% m/m', 'legend': 'm/m change',
    'values': L(mm.values),
    'note': (f'与 Exhibit 9 成对：水平值看规模、变化率看动能。首月（{mlab(mb.dropna().index[0])}）'
             '没有上月基数，算不出环比，故本图从次月起画，不留空点。'),
})


def fee_period_note(head='<b>费率期间。</b>'):
    """本页唯一用到 series/fee_rates.csv 的地方是 Exhibit 13（生息资产占比 + NIM）。
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


# ── Exhibit 13：为什么这里没有「量 → 收入」桥（季度序列）──
bs = _bs.iloc[-14:]
_r0, _r1 = float(bs['iea_share'].iloc[0]), float(bs['iea_share'].iloc[-1])
ex.append({
    'n': 13, 'kind': 'lines_endlabels', 'fmt': 'pct1',
    'xlabels': [mlab(p) for p in bs.index],
    'title': 'Why there is no revenue bridge here',
    'ylab': '%',
    'series': [
        {'name': 'Interest-earning assets / client assets', 'color': 'NAVY',
         'values': L(bs['iea_share'].values)},
        {'name': 'Net interest margin', 'color': 'RED', 'values': L(bs['nim'].values)},
    ],
    'note': ('Neither client cash nor interest-earning assets is published monthly. '
             'The only monthly proxy is client assets, and that ratio fell from '
             f'{_r0:.1f}% to {_r1:.1f}% in {len(bs) - 1} quarters — treating it as a constant '
             'would be false precision. Both series are quarterly。'
             'x 轴标的是各季<b>季末月</b>；PDF 版此处保留 2 位小数，网页图表引擎的格式器只到 '
             '1 位小数，切到「表格」视图可读到 2 位。'),
    # 费率的期间放 src_extra —— 它是「这两条线的数出自哪一季」的出处说明，
    # 紧贴 Source 行显示；过期时那句 ⚠ 也在同一段，读者不用翻到页尾的方法论。
    'src_extra': fee_period_note(),
})

# ── Exhibit 14：核心净新增资产全历史 ──
_b14 = brk_idx(nna.index)                     # 全序列图，x 用 xlabels_long（= df.index）
# 负值月现算不写死：写死月份名，数据一滚（新的负值月、或历史被修订）图注就成了假话。
_neg14 = [mlab(p) for p in nna.dropna().index if float(nna.loc[p]) < 0]
ex.append({
    'n': 14, 'kind': 'lines', 'x': 'long', 'fmt': 'usd0', 'xstep': max(1, len(df) // 14),
    'title': 'Core net new assets since 2018',
    'ylab': '$bn', 'zero_line': True, 'end_label': True, 'label_fmt': 'usd0',
    'series': [{'name': 'Core net new assets', 'color': 'NAVY', 'values': L(nna.values)}],
    'break_at': _b14, 'break_label': BRK_LABEL,
    'note': (QNOTE + '。PDF 版此图纵轴从 0 起，'
             + (f'{"、".join(_neg14)} 共 {len(_neg14)} 个负值月被压在轴外；' if _neg14 else
                '负值月会被压在轴外；')
             + '网页版把纵轴放到负区并画出零线，负值月看得见；末点标出最新读数。'
             'PDF 版末 3 个月的红色虚线圈网页版不画。' + brk_note(_b14)),
})

# ── Exhibit 15：新开经纪账户全历史（截轴 1,600k）──
NBA_CAP = 1600
# 截轴说明里点名是哪个月 —— deck 的 long_line 在离群点旁标的是「值 + 月份」两行，
# 网页引擎的 capLabel 只标值；x 轴刻度最近的一档是 Sep-20，读者只能猜。
# 月份从数据现算，别写死：门槛或历史一变，写死的月份就是下一个「图注说的和图上不符」。
_over15 = [(mlab(p), float(nba.loc[p])) for p in nba.dropna().index if float(nba.loc[p]) > NBA_CAP]
_ov_txt = '、'.join(f'{m} 的 {comma(v)}k' for m, v in _over15)
ex.append({
    'n': 15, 'kind': 'lines', 'x': 'long', 'fmt': 'f0c', 'xstep': max(1, len(df) // 14),
    'title': 'New brokerage accounts since 2018',
    'ylab': 'k accounts', 'ycap': NBA_CAP, 'yfloor': 0, 'end_label': True,
    'cap_note': (f'axis capped at {comma(NBA_CAP)}k — {_over15[0][0]} outlier shown in red'
                 if len(_over15) == 1 else f'axis capped at {comma(NBA_CAP)}k — outliers in red'),
    'series': [{'name': 'New brokerage accounts', 'color': 'NAVY', 'values': L(nba.values)}],
    'note': (f'Axis capped at {comma(NBA_CAP)}k so the series is readable. '
             + (f'The {_over15[0][0]} reading of {comma(_over15[0][1])}k is the TD Ameritrade '
                'onboarding — a balance transfer, not accounts opened. Shown in red, not '
                'removed。' if len(_over15) == 1 else '')
             + '截轴不删点：超界的点画成空心红圈，真值竖排标出'
             + (f'（本图超界的是 {_ov_txt}，图顶的截轴说明里也点了月份）。' if _over15 else '。')
             + '末点标出最新读数。'),
})

# ── Exhibit 16：核心净新增资产逐年同期对照 ──
def year_series(s, n_years):
    s = s.dropna()
    yrs = sorted({p.year for p in s.index})[-n_years:]
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
y16 = year_series(nna, 6)
# 断点在这张图上不是一个 x 位置 —— x 轴是 Jan..Dec，断点分的是**线**（年份）不是月份，
# 竖虚线画上去会被读成「某个月不可比」。所以改用 annot 把同一句话写在图内（annot 走
# charts.js 的通用分支，year_lines 吃得到），并按年份把两种口径点名。
_OLD16 = [s['name'] for s in y16 if int(s['name']) < BRK.year]
_NEW16 = [s['name'] for s in y16 if int(s['name']) >= BRK.year]
ex.append({
    'n': 16, 'kind': 'year_lines', 'fmt': 'usd0', 'xlabels': MONTHS,
    'title': 'Core NNA path by year',
    'ylab': '$bn', 'series': y16, 'highlight': len(y16) - 1,
    'annot': f'口径断点：{"/".join(_NEW16)} 为 $25bn 门槛，{"/".join(_OLD16)} 为 $10bn',
    'note': ('每年一条线叠在 Jan–Dec 轴上，当年红色加粗。画的是<b>当月值</b>不是年初至今累计，'
             '所以 4 月与 12 月那两个季节性尖谷/尖峰可以逐年对齐着看。'
             f'口径断点在年份之间而不在月份上，画不成竖虚线：{"、".join(_NEW16)} 用 $25bn '
             f'剔除门槛，{"、".join(_OLD16)} 用 $10bn（图内右下角已标出），'
             '跨这两组做逐年对比要扣掉这一条。'),
})

# ── Exhibit 17：新开经纪账户逐年同期对照 ──
y17 = year_series(df['new_acct_ex'], 6)
ex.append({
    'n': 17, 'kind': 'year_lines', 'fmt': 'f0c', 'xlabels': MONTHS,
    'title': 'New accounts path by year',
    'ylab': 'k accounts', 'series': y17, 'highlight': len(y17) - 1,
    'note': ('Oct-2020 excluded (TD Ameritrade onboarding)。该月 14,718k 是余额转移不是新开户，'
             f'留着会把整张图压平；本图窗口为 {y17[0]["name"]}–{y17[-1]["name"]}，'
             '2020 年本就不在窗口内，剔除规则是为口径一致而保留的。'),
})

# ── Exhibit 18：年化有机增长率 月 x 年热力矩阵 ──
ogd = og.dropna()
hyrs = sorted({p.year for p in ogd.index})[-9:]
matrix = []
for y in hyrs:
    row = []
    for m in range(1, 13):
        p = pd.Period(f'{y}-{m:02d}', 'M')
        row.append(round(float(ogd.loc[p]), 6)
                   if p in ogd.index and np.isfinite(ogd.loc[p]) else None)
    matrix.append(row)
ex.append({
    'n': 18, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pct1',
    # 标题里必须写「单月」：热力矩阵按定义是逐格月度读数，而本页别处已经改用滚动口径。
    # 这张图豁免于「换滚动」那条规矩 —— 逐格的月度波动与季节形状就是它的题眼，
    # 平滑掉等于把这张图唯一的信息抹掉；但豁免不等于可以不写清楚画的是哪个口径。
    'title': 'Annualised organic growth rate — 单月年化 (%)',
    # 热力矩阵走 drawHeat 提前 return，通用断点/annot 分支都执行不到；而且这里断点分的
    # 是**行**（年）不是列（月）。唯一能落在图上的位置是行首标签，所以把口径写进行名 ——
    # 读者扫一眼行头就能看到门槛在哪一行换掉，而不是只在图注里看到一句话。
    # 门槛写成 10bn / 25bn 而不是 $10bn —— 行首每宽 1px，12 列热力格就各窄 1/12px，
    # 375px 下格内字号是被 (cw-5) 卡住的，标签越省，窄屏上的数字越读得清。
    'rows': [f'{y} · {25 if y >= BRK.year else 10}bn' for y in hyrs],
    'row_lab_w': 54,
    'cols': MONTHS, 'matrix': matrix,
    'legend': 'Annualised organic growth rate',
    'row_head': '年 · core NNA 剔除门槛（$bn）',
    'note': ('Green = faster organic asset gathering。色标取全部有限值的 5/95 分位，'
             '一两个离群月不会把整表压平。'
             f'首行（{hyrs[0]}）前几格空白不是缺数：序列自 {mlab(df.index[0])} 起，'
             f'而年化有机增速要用上月末客户资产做分母，{mlab(ogd.index[0])} 才是第一个可算月。'
             f'行首标出各年的 core NNA 剔除门槛：{BRK.year} 年起为 $25bn，此前为 $10bn，'
             '跨这条界的上下行不可直读（矩阵图的断点在行之间，画不成竖虚线）。'
             '本图通栏（横跨两列），但仍按图号排在 Exhibit 17 之后，图序与原 deck 一致。'
             '格内数字带 % 号，PDF 版是裸数字。'),
})


# ────────────────────────────── Exhibit 19：核对表 ──────────────────────────────
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

# ── 本页每条序列「两种口径的当期读数」，全部现算，供汇总表注与页尾口径说明并排印出 ──
# 写死任何一个都是下个月的假话；而不并排印出来，读者拿汇总表的 y/y 去核图上的次轴
# 必然对不上，还以为哪边算错了。
_R_NNA = roll_yoy(nna)
_R_NBA = roll_yoy(nba)


def _pair_txt(name, m, r, unit='%', d=1):
    """「单月 X / 滚动 Y（差 Zpp）」——两个口径都有才印，缺一个就只印有的那个。"""
    a = None if m is None or not np.isfinite(m) else f'单月 {m:+,.{d}f}{unit}'
    b = None if r is None or not np.isfinite(r) else f'滚动 12 个月 {r:+,.{d}f}{unit}'
    if a and b:
        return f'{name}：{a} / {b}（差 {abs(m - r):,.0f}pp）'
    return f'{name}：{a or b}' if (a or b) else ''


def _last(s):
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


# 季度合计同比（Exhibit 11 那条绿线）的当期读数 —— 第三种口径，也要并排给出
_Q_NNA = next((v for v in reversed(qyoy) if v is not None), None)
_CAL_ROWS = [t for t in (
    _pair_txt('Core net new assets（Exhibit 2 画滚动）', _y_nna, _last(_R_NNA)),
    _pair_txt('New brokerage accounts（Exhibit 6 画滚动）', yoy_of(nba), _last(_R_NBA)),
    ('Core NNA 的第三种口径：季度合计同比（Exhibit 11 的绿线）'
     f'{_Q_NNA:+,.1f}%' if _Q_NNA is not None else ''),
    _pair_txt('年化有机增长率（Exhibit 3，比率取 pp 差）',
              _y_og, (lambda s: (float(s.iloc[-1]) - float(s.iloc[-13]))
                      if len(s) >= 13 else None)(ogr.dropna()), unit='pp', d=2),
    f'Total client assets（存量，Exhibit 5 保留单月）：单月 {_y_at:+,.1f}%'
    if _y_at is not None else '',
    f'Month-end margin balances（存量，Exhibit 9 保留单月）：单月 {_y_mb:+,.1f}%'
    if _y_mb is not None else '',
) if t]

# Exhibit 13 窗口内是不是真的单边下行、全序列有几个季度上升 —— 图注里那两句都得从
# 数据现算。原文写死的「过去 32 个季度单边降」在补齐历史之后已经是假话。
_MONO13 = bool((np.diff(bs['iea_share'].values) <= 0).all())
_UP_ALL = int((np.diff(_bs['iea_share'].values) > 0).sum())

# 哪几张图真的画出了断点线，从 payload 现读 —— 写死一串编号，等窗口滚过 2025-01
# 之后就会变成第二个「注释说有、页面没有」的自相矛盾（正是 #9 的病根）。
_BRK_DRAWN = '、'.join(str(e['n']) for e in ex if e.get('break_at') is not None)

# 汇总表脚注同理：原文把「the break is drawn on Exhibits 2, 3, 11 and 14」写死在英文里，
# 窗口每月往前滚，2025-01 一旦滚出 Ex2/Ex3 的 25 个月窗口，这句就成了第二个
# 「注释说有、页面没有」—— 与本文件 brk_note() 那条防呆写法自相矛盾。改成现读 payload。
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
    + '<br><b>本表的 y/y 列是「单月口径」= 本月 ÷ 去年同月 − 1，与图上的次轴不同口径。</b>'
    '不改它是刻意的：这一列恒等于表内算术（第一列 ÷ 第三列），读者可以直接验算；'
    '换成滚动口径之后这一步会得出另一个数，表内自相矛盾比口径混用更糟。'
    '流量类的图（Exhibit 2 / 6）画的是 12 个月滚动合计同比，比这一列稳得多。'
    f'当期两种口径并排现算 —— {"；".join(_CAL_ROWS)}。')

notes = [
    f'<b>数据源与节奏。</b>Schwab Monthly Activity Report，通常次月 12–14 日发布；'
    f'本页数据截至 {mlab(LATEST)}，全序列自 {mlab(df.index[0])} 起。'
    '所有数值来自 <code>series/schw.csv</code>、<code>series/schw_avg_margin.csv</code> 与 '
    '<code>series/fee_rates.csv</code>，无任何估算或补插。'
    f'前两者是<b>月度</b>表，<code>fee_rates.csv</code> 是<b>季度</b>表（随季报更新），'
    f'本页只有 Exhibit 13 用它，SCHW 两个指标都齐的最新一季是 {qlab(_FEE_HAVE_Q)}；'
    '两张表节奏不同，页面上「月度已走到哪个月、费率停在哪一季」的差随时可能出现，'
    '每张相关图的 Source 行下都写明了当期口径。',

    f'<b>季末月口径。</b>{QNOTE}——3/6/9/12 月没有独立月报，这四个月的数值取自当季季报，'
    '所以序列是连续的，但它与其余月份的披露载体不同（Exhibit 2、6、14 的图注均标了这一条）。',

    '<b>市值变动是轧差项，不是披露值。</b>Exhibit 4 的滚存桥用的是恒等式'
    '「期初资产 + 核心净新增 + 市值变动 = 期末资产」，其中市值变动 = 客户资产环比变动 − 核心净新增。'
    '公司不单独披露这一项，所以它同时吸收了真实市场涨跌、口径调整与并购转入，'
    '不能整段当成「市场贡献」读。',

    '<b>流量类不算环比百分比。</b>核心净新增资产是流量，环比百分比的分母是上个月的流量，'
    '一个月的噪音会被放大成趋势。按 GS「LPLA monthly metrics」的规矩改用<b>年化有机增长率</b>'
    '（当月净新增 × 12 ÷ 上月末客户资产），见 Exhibit 3 与 Exhibit 18。'
    '比率序列的同比一律用<b>百分点差（pp/bp）</b>，不是「百分比的百分比变化」。',

    # ── 同比口径：本页现在同时存在四种，逐处点名 ──
    # 「点名」不是客套：读者在同一页上看到 +47%、+31%、+21% 三个都叫 y/y 的数，
    # 如果没人告诉他它们分母不同，他只会以为哪里算错了。
    '<b>⚠ 同比口径：本页有四种，逐处点名。</b>'
    '(1) <b>12 个月滚动合计同比</b>（本年 12 个月合计 ÷ 上年同 12 个月合计 − 1）—— '
    'Exhibit 2（核心净新增资产）与 Exhibit 6（新开经纪账户）的次轴，'
    '以及 Exhibit 3 次轴所依据的滚动有机增速。<b>流量类一律用这个口径。</b>'
    + (f'实测（对齐到两种口径都算得出的同一批月份，{ST2["n"]} 个月）：核心净新增资产的'
       f'单月同比标准差 {ST2["sd_m"]:,.1f}pp 是滚动口径 {ST2["sd_r"]:,.1f}pp 的 '
       f'{ST2["sd_m"] / ST2["sd_r"]:,.1f} 倍，相邻月最大跳变 {ST2["jump_m"]:,.0f}pp vs '
       f'{ST2["jump_r"]:,.0f}pp，{len(ST2["flips"])} 个月两种口径符号相反。'
       if ST2 else '')
    + '(2) <b>单月同比</b>（本月 ÷ 去年同月 − 1）—— Exhibit 5（客户总资产）、'
    'Exhibit 9（月末融资余额）的次轴，Exhibit 1 汇总表的 y/y 列，'
    + ('Exhibit 8（日均交易笔数，序列还不到 24 个月、滚动同比算不出，见该图图注），'
       if _r8n < _ROLL_MIN_N else '')
    + '以及 Exhibit 18 热力矩阵的逐格读数。'
    '<b>存量序列保留单月同比是口径判断，不是偷懒</b>：12 个月末的客户资产相加不是任何东西，'
    '同一笔钱会被数 12 遍，滚动合计在存量上根本无定义。'
    + (f'代价也量过：客户总资产的单月同比标准差 {ST5["sd_m"]:,.1f}pp，'
       f'若强行按滚动合计算是 {ST5["sd_r"]:,.1f}pp，两种口径 {len(ST5["flips"])} 个月符号相反 —— '
       '存量上的差距远小于流量，噪声用轴范围解决即可。' if ST5 else '')
    + '(3) <b>季度合计同比</b>（本季 3 个月合计 ÷ 去年同季 3 个月合计 − 1）—— '
    'Exhibit 11 的右轴绿线。'
    '(4) <b>环比</b> —— Exhibit 12（融资余额 m/m）与各图的 m/m 气泡。'
    f'当期各口径并排现算：{"；".join(_CAL_ROWS)}。'
    '<b>热力矩阵（Exhibit 18）与逐年对照图（Exhibit 16 / 17）不换口径</b>：'
    '逐格的月度波动与季节形状就是那两类图的题眼，平滑掉等于把它们唯一的信息抹掉；'
    '但标题里已写明画的是「单月」读数。',

    f'<b>核心净新增资产的剔除门槛在 {BRK.year} 年调过，断点已画在图上。</b>'
    '官方脚注为「generally greater than $25 billion beginning in 2025; $10 billion in '
    f'prior periods」——单一客户流入的剔除阈值自 {BRK} 起从 $10bn 提高到 $25bn，'
    '月报不重述历史，因此断点左右的「核心」口径不完全可比。原始月报没有给出调整前后的'
    '对照值，这里不做还原，但按规矩把断点画出来而不是只写一句话：'
    + (f'Exhibit {_BRK_DRAWN} 在 {BRK}（季度图为 {BRK_Q}）处有红色竖虚线，线左右不可直读，'
       '跨线的同比与 12 个月均值同样含口径差。' if _BRK_DRAWN else
       f'当前各图窗口已整段落在 {BRK} 右侧，无需画线。')
    + 'Exhibit 16 的断点分的是年份不是月份、Exhibit 18 的断点分的是行不是列，'
    '两张图画不成竖虚线，改为在图内注解与行首标签上标明门槛。',

    f'<b>两条融资余额序列口径不同，不能接续。</b>Exhibit 9 是<b>月末</b>余额，'
    f'Schwab 自 2026-01 的月报才开始披露，其 13 个月滚动表回溯至 2025-01，'
    f'所以 y/y 从 2026-01 才有；Exhibit 10 是<b>月度平均</b>余额，'
    f'Schwab 从 2020-04 发到 {mlab(avgm.index[-1])} 后停发。两者是不同口径，'
    '不要拼成一条长序列读。日均交易笔数（DATs）同理，只有 2025-01 起的历史。',

    # 「单边降」这句原先是拿全序列（33 个季度）说的，而全序列里有 9 个季度是上升的、
    # 2020Q2 还触过 9.15% 的顶 —— 是假话，而且窗口与 Exhibit 13 画的 14 个季度不符。
    # 改成：口径按图上的窗口说，全序列的形状另说一句，两句都从数据现算。
    '<b>这里没有「量 → 收入」桥。</b>Schwab 月报既不披露客户现金也不披露生息资产，'
    '唯一能当代理的是客户资产；但生息资产 / 客户资产的比值在 Exhibit 13 画的 '
    f'{len(bs)} 个季度窗口（{mlab(bs.index[0])}–{mlab(bs.index[-1])}）里从 {_r0:.1f}% '
    f'{"单边" if _MONO13 else ""}降到 {_r1:.1f}%（趋势，不是噪音），把它当常数会造出假精度。'
    f'更长的全序列（{len(_bs)} 个季度，自 {mlab(_bs.index[0])} 起）不是单边的：'
    f'其中 {_UP_ALL} 个季度环比上升，高点是 {mlab(_bs["iea_share"].idxmax())} 的 '
    f'{float(_bs["iea_share"].max()):.1f}%。所以不搭桥，改把这个比值本身画出来'
    '（Exhibit 13）—— 它本身就是 NII 增长受限的原因。'
    '该图两条线都是<b>季度</b>数据，来自季报。'
    + fee_period_note(head='费率的期间：'),

    f'<b>截轴不删点。</b>Exhibit 15 的纵轴截在 {comma(NBA_CAP)}k：'
    + (f'{_ov_txt} 是 TD Ameritrade 并表带来的账户转移，不是当月新开户，'
       if _over15 else '')
    + '留着会把 2018 年以来整条线压平。'
    '被截的点画成空心红圈并把真值竖排标出，图顶的截轴说明里点名了是哪个月，点没有被删掉。'
    'Exhibit 17 的逐年对照图按同样理由把 2020-10 排除在外。'
    'Exhibit 4 的滚存桥同样截了轴（+420 / −200 $bn）：市值变动的量级是核心净新增的十倍以上，'
    '不截轴深蓝那一段薄得读不出逐月变化；超界的柱画到边界加断口符号，真值红色竖排标出。',

    '<b>窗口一律从数据最新月倒推。</b>水平柱图 25 个月、滚存桥与核对表 13 个月、'
    '季度图 14 个季度、逐年对照图 6 年、热力矩阵 9 年；'
    '数据不足窗口长度时按实际长度画（DATs 与月末融资余额即如此），不补零、不外推。',

    '<b>网页版与 PDF 版的已知差异。</b>（1）PDF 在长历史图末 3 个月画红色虚线圈，'
    '网页版不画，改用 hover 与表格视图；'
    '（2）Exhibit 13 的 PDF 版保留 2 位小数，网页图表引擎的格式器只到 1 位，表格视图仍是 2 位；'
    '（3）Exhibit 14 的 PDF 版纵轴从 0 起、负值月看不见，网页版放到负区并画零线；'
    'Exhibit 4 的纵轴网页版截在 +420/−200 $bn（PDF 不截），超界值以红色真值标出；'
    f'（4）同比的小基数剔除门槛，PDF 是「基数 &lt; 0.15 × 序列绝对值中位数」，'
    f'网页版提到 {YOY_BASE_MIN:.0%} —— 0.15 挡不住 SCHW 的结构性极小月，'
    '一个 +569% 的基数效应读数会把整条次轴压平；'
    '（5）比率的同比/环比，PDF 印整数 pp，网页版保留 1 位小数（|差| &lt; 1pp 时改印 bp）；'
    '（6）Exhibit 11 的柱顶标签加了 $ 前缀、Exhibit 18 的格内数字加了 % 后缀，PDF 是裸数字。'
    '（7）<b>水平柱图的次轴口径与 PDF 不同</b>：PDF 的 <code>gsx.lvl_bar</code> 次轴画的是'
    '单月同比，本页的<b>流量类</b>图（Exhibit 2 / 3 / 6）已改成 12 个月滚动合计同比，'
    '存量类（Exhibit 5 / 9）仍与 PDF 一致画单月同比 —— 理由与实测数字见上一条'
    '「同比口径」。这是本页相对 PDF 的第一处<b>口径</b>（而非排版）差异，'
    '拿本页的次轴读数去核 PDF 时要先看图例里的口径标签。'
    '所有数值与格式化都在 Python 侧完成，页面不做任何计算。',
]

# 抬头一律 y/y 与 m/m 都写。只写 y/y 会挑出一个纯正面的印象：本月客户总资产的
# y/y 是 +21.6%，m/m 却是 −0.4%，只报前者等于把当月的转向藏进汇总表里。
# 比率类（年化有机增长率）按 CONTRACT §2 用 pp/bp，不用百分比变化。
def _dpair(y, m, pct_diff=False, ylab='y/y'):
    """(y/y, m/m) → 「（+31% y/y·12M滚动 / +26% m/m）」；两个都算不出就整段不写。

    ylab 一律把口径写进标签：抬头是多数人唯一会读的一行，一个不带口径的 y/y
    在一张有四种同比口径的页面上是纯误导（读者会拿它去核汇总表，然后对不上）。
    """
    def one(v, suf):
        if v is None or not np.isfinite(v):
            return None
        if pct_diff:
            return (signed(v * 100, 0, 'bp') if abs(v) < 1 else signed(v, 2, 'pp')) + f' {suf}'
        return signed(v, 0, '%') + f' {suf}'
    parts = [t for t in (one(y, ylab), one(m, 'm/m')) if t]
    return f'（{" / ".join(parts)}）' if parts else ''


# 抬头里的流量类同比一律用滚动口径，与 Exhibit 2 画的那条线是同一个数。
# 原来这里用的是单月同比：本月 +47% 而滚动只有 +31%，抬头挑的正好是大的那个。
_hy_nna = _last(_R_NNA)
_hy_og = ((float(ogr.dropna().iloc[-1]) - float(ogr.dropna().iloc[-13]))
          if len(ogr.dropna()) >= 13 else None)

headline = (
    f'核心净新增资产 {money(_lat_nna, 1)}bn'
    + _dpair(_hy_nna, _m_nna, ylab='y/y·12M滚动')
    + f' · 年化有机增长率 {_lat_og:.1f}%'
    + _dpair(_hy_og, _m_og, pct_diff=True, ylab='y/y·12M滚动')
    # 存量三项保留单月同比（滚动合计在存量上无定义），标签写「单月」把口径挑明
    + f' · 客户总资产 {money(_lat_at, 2)}tn' + _dpair(_y_at, _m_at, ylab='y/y·单月')
    + f' · 日均交易 {_lat_dm:.1f}mn 笔/日' + _dpair(_y_dm, _m_dm, ylab='y/y·单月')
    + f' · 月末融资余额 {money(_lat_mb, 1)}bn' + _dpair(_y_mb, _m_mb, ylab='y/y·单月')
)

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
