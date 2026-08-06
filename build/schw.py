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
import inspect
import json
import os
import re

import numpy as np
import pandas as pd

import brief as B     # 页顶 ~300 字总结的共享规则库（R1-R6），只算事实不出文字
import payload_guard
import pctile          # 汇总表 3Y %ile 的唯一实现，各页不再各写各的（见该模块 docstring）
import repo            # 仓库定位 + 发布日台账入口

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')


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
for r in SUM_ROWS:
    if r[0] == 'group':
        srows.append({'kind': 'group', 'label': r[1]})
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
    'heads': [mlab(CUR), mlab(PRV), mlab(YAG), 'm/m', 'y/y', '3Y %ile'],
    'sep': 3,
    'rows': srows,
    # 'note' 在全部 exhibit 建完之后再填 —— 里面要引用「哪几张图真的画出了断点线」，
    # 那份编号必须从 payload 现读（见文件末尾 _BRK_DRAWN），不能写死。
}


# ────────────────────────────── Exhibit 2..18 ──────────────────────────────
ex = []
# 水平柱图的次轴 = 同比折线（同 PDF 的 gsx.lvl_bar），不是 12 个月均线。
# 均线只是把柱子再平滑一遍、不带新信息；这一条是 deck 的既定规矩，移植时曾丢掉。
YOY_NOTE = ('次轴金色折线为同比（y/y），口径与 PDF 版一致；'
            f'去年同月基数小于本序列绝对值中位数的 {YOY_BASE_MIN:.0%}、或与本月异号时不算同比，'
            '折线在该月断开 —— 那种月份算出来的是基数效应，不是业务变化。')
YOY_NOTE_PP = ('次轴金色折线为同比的<b>百分点差（pp）</b>，同 PDF 版；'
               '比率序列不算「百分比的百分比变化」。')
_BRK_TXT = (f'红色竖虚线 = 口径断点（{BRK}）：单一客户流入的剔除门槛自该期起从 $10bn 提到 '
            '$25bn，月报不重述历史，线左右两侧不可直读，跨断点的同比与均值同样要打折扣。')


def brk_note(i):
    """断点滚出窗口时不要留下「红色竖虚线」这句 —— 那就成了第二个自相矛盾的图注。"""
    return _BRK_TXT if i is not None else ''

# ── Exhibit 2：核心净新增资产（水平柱，25 个月窗口）──
d2 = tail(nna, 25)
_b2 = brk_idx(d2.index)
ex.append({
    'n': 2, 'kind': 'gs_bar', 'fmt': 'usd1', 'xlabels': xl(nna, 25),
    'title': 'Core net new assets',
    'ylab': '$bn', 'ylab2': '% y/y', 'legend': 'Monthly',
    'values': L(d2.values), 'yoy': yoy_axis(nna, 25),
    'mom_txt': oval(mom_of(nna), suffix=' m/m'),
    'break_at': _b2, 'break_label': BRK_LABEL,
    'note': (QNOTE + '。' + YOY_NOTE + yoy_gap_note(nna, 25)
             + '（4 月是结构性极小月：缴税季净流入几乎归零。）' + brk_note(_b2)),
})

# ── Exhibit 3：年化有机增长率（流量不算环比百分比，改用年化有机增速）──
og = df['organic_growth_ann']
d3 = tail(og, 25)
_b3 = brk_idx(d3.index)                      # 分子是 core NNA，断点原样传导过来
ex.append({
    'n': 3, 'kind': 'gs_bar', 'fmt': 'pct1', 'yfmt': 'pct0', 'xlabels': xl(og, 25),
    'title': 'Annualised organic growth rate',
    'ylab': '% annualised', 'ylab2': 'pp y/y', 'legend': 'Monthly',
    'values': L(d3.values), 'yoy': yoy_axis(og, 25, pct_series=True),
    'break_at': _b3, 'break_label': BRK_LABEL,
    'note': ('Monthly core NNA x 12 / prior month-end client assets。'
             '这是 GS LPLA 版式的规矩：流量类指标不算环比百分比（分母是上月的流量，'
             '一个月的噪音会被放大成趋势），改用年化有机增长率把流量放回存量的尺度上。'
             + YOY_NOTE_PP + brk_note(_b3)),
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
atn = df['assets_tn']
ex.append({
    'n': 5, 'kind': 'gs_bar', 'fmt': 'usd2', 'xlabels': xl(atn, 25),
    'title': 'Total client assets',
    'ylab': '$tn', 'ylab2': '% y/y', 'legend': 'Monthly',
    'values': L(tail(atn, 25).values), 'yoy': yoy_axis(atn, 25),
    'note': ('月末余额，官方口径为 $bn，此处除以 1,000 换成 $tn 便于读轴。'
             + YOY_NOTE + yoy_gap_note(atn, 25)),
})

# ── Exhibit 6：新开经纪账户（水平柱）──
nba = df['new_brokerage_accounts_k']
ex.append({
    'n': 6, 'kind': 'gs_bar', 'fmt': 'f0', 'xlabels': xl(nba, 25),
    'title': 'New brokerage accounts opened',
    'ylab': 'k accounts', 'ylab2': '% y/y', 'legend': 'Monthly',
    'values': L(tail(nba, 25).values), 'yoy': yoy_axis(nba, 25),
    'note': QNOTE + '。' + YOY_NOTE + yoy_gap_note(nba, 25),
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
dm = df['dats_mn']
_y8 = yoy_axis(dm, 25)
_n8 = sum(1 for v in _y8['values'] if v is not None)
ex.append({
    'n': 8, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': xl(dm, 25),
    'title': 'Daily average trades',
    'ylab': 'mn trades / day', 'ylab2': '% y/y', 'legend': 'Monthly',
    'values': L(tail(dm, 25).values), 'yoy': _y8,
    'mom_txt': oval(mom_of(dm), suffix=' m/m'),
    'note': ('Client DATs first appear in the Jan-2026 report; the 13-month rolling table '
             'reaches back to Jan-2025, so the y/y line starts Jan-2026。'
             f'本图只有 {len(dm.dropna())} 个月的历史（{mlab(dm.dropna().index[0])} 起），'
             '短于 25 个月的窗口设定，不是数据缺失；'
             f'因此次轴同比只有最近 {_n8} 个点，更早的月份没有可比基数。' + YOY_NOTE),
})

# ── Exhibit 9：月末融资余额 ──
mb = df['margin_balances_usdbn']
_y9 = yoy_axis(mb, 25)
_n9 = sum(1 for v in _y9['values'] if v is not None)
ex.append({
    'n': 9, 'kind': 'gs_bar', 'fmt': 'usd0', 'xlabels': xl(mb, 25),
    'title': 'Month-end margin balances',
    'ylab': '$bn', 'ylab2': '% y/y', 'legend': 'Monthly',
    'values': L(tail(mb, 25).values), 'yoy': _y9,
    'mom_txt': oval(mom_of(mb), suffix=' m/m'),
    'note': ('Schwab only began disclosing month-end margin balances in the Jan-2026 report; '
             'its 13-month rolling table reaches back to Jan-2025, so the y/y line starts '
             'Jan-2026。口径含 short credits。'
             f'次轴同比同样只有最近 {_n9} 个点。' + YOY_NOTE),
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
    'line': {'name': 'y/y (RHS)', 'color': 'GREEN', 'values': qyoy, 'yfmt': 'pct0'},
    'break_at': _b11, 'break_label': BRK_LABEL,
    'note': ('月度核心净新增资产按季汇总（恒等式可无损累加，见 Exhibit 4）。'
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
    'title': 'Annualised organic growth rate (%)',
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


table = {
    'n': 19,
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
       if short_rows else ''))

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
    '水平柱图的次轴 y/y 折线与 PDF 一致（本轮从「12 个月均线」改回同比，'
    '均线只是把柱子再平滑一遍、不带新信息）。'
    '所有数值与格式化都在 Python 侧完成，页面不做任何计算。',
]

# 抬头一律 y/y 与 m/m 都写。只写 y/y 会挑出一个纯正面的印象：本月客户总资产的
# y/y 是 +21.6%，m/m 却是 −0.4%，只报前者等于把当月的转向藏进汇总表里。
# 比率类（年化有机增长率）按 CONTRACT §2 用 pp/bp，不用百分比变化。
def _dpair(y, m, pct_diff=False):
    """(y/y, m/m) → 「（+47% y/y / +26% m/m）」；两个都算不出就整段不写。"""
    def one(v, suf):
        if v is None or not np.isfinite(v):
            return None
        if pct_diff:
            return (signed(v * 100, 0, 'bp') if abs(v) < 1 else signed(v, 2, 'pp')) + f' {suf}'
        return signed(v, 0, '%') + f' {suf}'
    parts = [t for t in (one(y, 'y/y'), one(m, 'm/m')) if t]
    return f'（{" / ".join(parts)}）' if parts else ''


headline = (
    f'核心净新增资产 {money(_lat_nna, 1)}bn' + _dpair(_y_nna, _m_nna)
    + f' · 年化有机增长率 {_lat_og:.1f}%' + _dpair(_y_og, _m_og, pct_diff=True)
    + f' · 客户总资产 {money(_lat_at, 2)}tn' + _dpair(_y_at, _m_at)
    + f' · 日均交易 {_lat_dm:.1f}mn 笔/日' + _dpair(_y_dm, _m_dm)
    + f' · 月末融资余额 {money(_lat_mb, 1)}bn' + _dpair(_y_mb, _m_mb)
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

    ═══ SCHW 独有，别家不能照抄 ═══
      · **季节轴按「同一日历月」对齐，不是「上一个季末月」。** 3/6/9/12 月没有独立月报、
        数取自季报，core NNA 在这四个月系统性抬升；但 3→6 本身就是个结构性台阶（历史
        中位 −29%、8 次里 7 次为负），拿「比上一个季末月低 21%」当动能读，测到的仍是
        季节位置，正是这段要治的病。所以位次一律按同一日历月排（6 月对历年 6 月）。
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
      · **客户资产环比转跌而 core NNA 为正是 SCHW 的常态而非异常**（Exhibit 4 的恒等式：
        期末 − 期初 = core NNA + 市值变动，后者是轧差项、非披露值）。所以本页把
        「资产下跌月里有多少个伴随正净流入」当成一条读法规则写出来，而不是当新闻。
        这一句只报那个共现计数与落点，**不把环比拆成「市值变动 vs 流量」两项并给出
        各自的量**（贡献度拆解是 brief 的禁区，恒等式本身由 Exhibit 4 负责画）。
      · **两组序列的样本深度差 5 倍**：客户资产有 98 个月，DATs 与月末融资余额是 2026-01
        月报才开始披露的（回溯到 2025-01），只有 18 个月。同一句「创新高」在这两组里
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
            s2 += f'，同比{B.pct(be["yy"])}'
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
        # 两句连着读像同一件事重复了一遍。
        s3 += ('，同比方向与环比相反。' if yy is not None and mm is not None
                                        and (yy < 0) != (mm < 0) else '。')

    # ── R4：单位恒等。融资余额/客户资产是**推导值**（公司只分别披露分子与分母，R5）。
    #    措辞照样板走「同比 X%，是分子 A% 除以分母 B% 的商，+ 一句落点」的口语式恒等：
    #    印出来的 X% 是比率序列自己当场算的同比，不是把 A 与 B 直接相除得来的数。
    #    显式写成「增长指数 1.98 ÷ 1.22」那种贡献度拆解，brief 里不写（那是 Exhibit 的活）。
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
              f'{lead}，同比{B.pct(r_yoy)}（{signed(r[i] - r[i - 12], 2, "pp")}），'
              f'是融资余额{B.pct(pu["num_yoy"])}除以客户资产{B.pct(pu["den_yoy"])}的商，'
              f'杠杆在自己{"扩张" if r_yoy > 0 else "收缩"}。')
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
            # 它是怎么来的就没法判断它跟核心净新增是不是同一件事说两遍。
            s4 = (f'{why}，融资余额/客户资产的同比读不出；改看年化有机增长率'
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
_src_date = repo.source_date('schw', str(LATEST))
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
