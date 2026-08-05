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


# ────────────────────────────── 格式化零件 ──────────────────────────────
def mlab(p):
    return p.strftime('%b-%y')


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
    '<code>series/fee_rates.csv</code>，无任何估算或补插。',

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
    '该图两条线都是<b>季度</b>数据，来自季报。',

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
