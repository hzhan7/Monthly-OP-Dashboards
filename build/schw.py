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

LATEST = df.index[-1]
assets = df['total_client_assets_usdbn']
nna = df['core_nna_usdbn']

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


def sgn_pct(v, d=1):
    return f'{v:+.{d}f}%'


def L(a):
    """序列 → JSON 数组；非有限值一律写 null（图与表都会断开，不画假点）。"""
    return [None if v is None or not np.isfinite(float(v)) else round(float(v), 6) for v in a]


def tail(s, win):
    """尾部连续 win 期（不足则全部）。dropna 后取尾段，避免把断档月并排画成相邻柱。"""
    s = s.dropna()
    return s.iloc[-win:]


def yoy_of(s, pct_series=False):
    """最新月同比：比率序列用百分点差，量/流量用百分比变化。口径同 gsx.lvl_bar。"""
    s = s.dropna()
    cur = s.index[-1]
    prev = cur - 12
    if prev not in s.index:
        return None
    a, b = float(s.iloc[-1]), float(s.loc[prev])
    if pct_series:
        return a - b
    if b == 0 or a * b < 0:
        return None
    return (a / b - 1) * 100


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


def prior12_avg(s, win):
    """「Prior 12mo Avg.」= 最新月之前 12 个月的均值（不含最新月本身）。"""
    d = tail(s, win)
    if len(d) < 2:
        return None
    prior = d.iloc[-13:-1] if len(d) >= 13 else d.iloc[:-1]
    return round(float(np.nanmean(prior.values)), 6)


def oval(v, unit='%', suffix=' y/y'):
    """图内气泡文案。百分点差保留 1 位小数 —— 0.79pp 四舍五入成「+1pp」会把口径读没了。"""
    if v is None or not np.isfinite(v):
        return None
    d = 1 if unit == 'pp' else 0
    return f'{v:+.{d}f}{unit}{suffix}'


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
        txt = f'{v * 100:+.0f}bp' if abs(v) < 1 else f'{v:+.2f}pp'
    elif mode == 'abs':
        v = a - b
        txt = ('$' if kind == '$' else '') + f'{v:+,.{max(0, d)}f}'
    else:
        if b == 0 or a * b < 0:
            return {'v': ''}
        v = a / b - 1
        txt = f'{v * 100:+.1f}%'
    return {'v': txt, 'cls': 'pos' if v > 0 else ('neg' if v < 0 else '')}


def pctile36(s):
    """近 36 个月分位。单调序列（几乎只增不减）留空 —— 分位恒为 100，是噪音不是信息。"""
    h = s.dropna().iloc[-36:]
    cur = s.dropna()
    if not len(cur):
        return {'v': ''}
    c = float(cur.iloc[-1])
    if len(h) < 8:
        return {'v': ''}
    dd = np.diff(h.values)
    if len(dd) and float((dd >= 0).sum()) / len(dd) >= 0.90:
        return {'v': ''}
    p = float((h.values < c).sum()) / max(1, len(h) - 1) * 100
    return {'v': f'{p:.0f}', 'cls': 'hi' if p >= 66 else ('lo' if p <= 33 else '')}


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
for r in SUM_ROWS:
    if r[0] == 'group':
        srows.append({'kind': 'group', 'label': r[1]})
        continue
    _, lab, col, d, kind, mode = r
    s = df[col]
    get = lambda p: (float(s.loc[p]) if p in s.index and np.isfinite(s.loc[p]) else None)
    c, p1, p12 = get(CUR), get(PRV), get(YAG)
    srows.append({'label': lab, 'cells': [
        {'v': cell(c, d, kind)}, {'v': cell(p1, d, kind)}, {'v': cell(p12, d, kind)},
        chg(c, p1, mode, d, kind), chg(c, p12, mode, d, kind), pctile36(s)]})

summary = {
    'title': f'Schwab monthly activity summary — {mlab(LATEST)}',
    'heads': [mlab(CUR), mlab(PRV), mlab(YAG), 'm/m', 'y/y', '3Y %ile'],
    'sep': 3,
    'rows': srows,
    'note': (QNOTE + '.  Core NNA is a flow, read through the annualised organic growth line '
             'per GS convention.  The core-NNA exclusion threshold moved from $10bn to $25bn '
             'in 2025.  Margin balances include short credits.  '
             '比率类指标（年化有机增长率）的差异用 pp/bp，不用百分比变化；'
             '市值变动是轧差项，其差异用绝对额（$bn）而非百分比。'
             '3Y %ile = 当月读数在最近 36 个月里高于多少个百分比的观测；'
             '客户总资产近乎单调上行（分位恒为 100，零信息量），故该行分位留空。'),
}


# ────────────────────────────── Exhibit 2..18 ──────────────────────────────
ex = []
AVG_NOTE = ('虚线为 Prior 12mo Avg.（最新月之前 12 个月的均值，不含最新月本身）；'
            'PDF 版此处画的是次轴金色 y/y 折线，网页版把 y/y 收进右上角气泡与表格视图。')

# ── Exhibit 2：核心净新增资产（水平柱，25 个月窗口）──
d2 = tail(nna, 25)
ex.append({
    'n': 2, 'kind': 'gs_bar', 'fmt': 'usd1', 'xlabels': xl(nna, 25),
    'title': 'Core net new assets',
    'ylab': '$bn', 'legend': 'Monthly',
    'values': L(d2.values), 'avg12': prior12_avg(nna, 25),
    'yoy_txt': oval(yoy_of(nna)), 'mom_txt': oval(mom_of(nna), suffix=' m/m'),
    'note': QNOTE + '。' + AVG_NOTE,
})

# ── Exhibit 3：年化有机增长率（流量不算环比百分比，改用年化有机增速）──
og = df['organic_growth_ann']
ex.append({
    'n': 3, 'kind': 'gs_bar', 'fmt': 'pct1', 'yfmt': 'pct0', 'xlabels': xl(og, 25),
    'title': 'Annualised organic growth rate',
    'ylab': '% annualised', 'legend': 'Monthly',
    'values': L(tail(og, 25).values), 'avg12': prior12_avg(og, 25),
    'yoy_txt': oval(yoy_of(og, pct_series=True), unit='pp'),
    'note': ('Monthly core NNA x 12 / prior month-end client assets。'
             '这是 GS LPLA 版式的规矩：流量类指标不算环比百分比（分母是上月的流量，'
             '一个月的噪音会被放大成趋势），改用年化有机增长率把流量放回存量的尺度上。'
             '比率序列的同比用**百分点差**，不是「百分比的百分比变化」。' + AVG_NOTE),
})

# ── Exhibit 4：恒等式滚存桥（GS SCHW First Take Exhibit 2）──
b13 = df.iloc[-13:]
ex.append({
    'n': 4, 'kind': 'bridge_bar', 'fmt': 'usd0', 'xlabels': XL,
    'title': 'What moved client assets: flows vs. markets',
    'ylab': '$bn change',
    'stacks': [
        {'name': 'Core net new assets', 'color': 'NAVY', 'values': L(b13['core_nna_usdbn'].values)},
        {'name': 'Market gains (balancing)', 'color': 'BLUE', 'values': L(b13['market_gains'].values)},
    ],
    'net': {'name': 'Total change in client assets',
            'values': L(b13['asset_change'].values)},
    'net_color': 'INK',
    'note': ('Identity: opening assets + core NNA + market gains = closing assets。'
             '市值变动是**轧差项**（= 客户资产环比变动 − 核心净新增），'
             '公司并不单独披露，所以它同时吸收了口径调整、并购转入与真实市场涨跌，'
             '不能整段当成「市场贡献」读。'),
})

# ── Exhibit 5：客户总资产（水平柱）──
atn = df['assets_tn']
ex.append({
    'n': 5, 'kind': 'gs_bar', 'fmt': 'usd2', 'xlabels': xl(atn, 25),
    'title': 'Total client assets',
    'ylab': '$tn', 'legend': 'Monthly',
    'values': L(tail(atn, 25).values), 'avg12': prior12_avg(atn, 25),
    'yoy_txt': oval(yoy_of(atn)),
    'note': '月末余额，官方口径为 $bn，此处除以 1,000 换成 $tn 便于读轴。' + AVG_NOTE,
})

# ── Exhibit 6：新开经纪账户（水平柱）──
nba = df['new_brokerage_accounts_k']
ex.append({
    'n': 6, 'kind': 'gs_bar', 'fmt': 'f0', 'xlabels': xl(nba, 25),
    'title': 'New brokerage accounts opened',
    'ylab': 'k accounts', 'legend': 'Monthly',
    'values': L(tail(nba, 25).values), 'avg12': prior12_avg(nba, 25),
    'yoy_txt': oval(yoy_of(nba)),
    'note': QNOTE + '。' + AVG_NOTE,
})

# ── Exhibit 7：客户总资产全历史 ──
ex.append({
    'n': 7, 'kind': 'lines', 'x': 'long', 'fmt': 'f1', 'xstep': max(1, len(df) // 14),
    'title': 'Total client assets since 2018',
    'ylab': '$tn', 'yfloor': 0,
    'series': [{'name': 'Total client assets', 'color': 'NAVY', 'values': L(atn.values)}],
    'note': ('Full assembled history。PDF 版在末 3 个月画一个红色虚线圈标出最新窗口，'
             '网页版不画圈 —— 改用 hover 读数与右上角「表格」视图逐月核对。'),
})

# ── Exhibit 8：日均交易笔数 ──
dm = df['dats_mn']
ex.append({
    'n': 8, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': xl(dm, 25),
    'title': 'Daily average trades',
    'ylab': 'mn trades / day', 'legend': 'Monthly',
    'values': L(tail(dm, 25).values), 'avg12': prior12_avg(dm, 25),
    'yoy_txt': oval(yoy_of(dm)), 'mom_txt': oval(mom_of(dm), suffix=' m/m'),
    'note': ('Client DATs first appear in the Jan-2026 report; the 13-month rolling table '
             'reaches back to Jan-2025, so the y/y line starts Jan-2026。'
             f'本图只有 {len(dm.dropna())} 个月的历史（{mlab(dm.dropna().index[0])} 起），'
             '短于 25 个月的窗口设定，不是数据缺失。' + AVG_NOTE),
})

# ── Exhibit 9：月末融资余额 ──
mb = df['margin_balances_usdbn']
ex.append({
    'n': 9, 'kind': 'gs_bar', 'fmt': 'usd0', 'xlabels': xl(mb, 25),
    'title': 'Month-end margin balances',
    'ylab': '$bn', 'legend': 'Monthly',
    'values': L(tail(mb, 25).values), 'avg12': prior12_avg(mb, 25),
    'yoy_txt': oval(yoy_of(mb)), 'mom_txt': oval(mom_of(mb), suffix=' m/m'),
    'note': ('Schwab only began disclosing month-end margin balances in the Jan-2026 report; '
             'its 13-month rolling table reaches back to Jan-2025, so the y/y line starts '
             'Jan-2026。口径含 short credits。' + AVG_NOTE),
})

# ── Exhibit 10：平均融资余额全历史（与 Exhibit 9 不同口径）──
ex.append({
    'n': 10, 'kind': 'lines', 'fmt': 'f0', 'xlabels': [mlab(p) for p in avgm.index],
    'xstep': max(1, len(avgm) // 14),
    'title': 'Average margin balances since 2020',
    'ylab': '$bn (monthly average)', 'yfloor': 0,
    'series': [{'name': 'Average margin balances', 'color': 'NAVY', 'values': L(avgm.values)}],
    'note': ('Different basis from Exhibit 9: this is the average-balance line Schwab published '
             'Apr-2020 to Dec-2025 and then dropped. It is the only long monthly margin history '
             f'that exists。序列止于 {mlab(avgm.index[-1])}，此后无同口径披露，'
             '不要与 Exhibit 9 的月末余额接续成一条线读。'),
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
ex.append({
    'n': 11, 'kind': 'qtr_bar', 'fmt': 'usd0', 'label_fmt': 'usd0',
    'xlabels': [str(p) for p in qv.index],
    'title': 'Core net new assets by quarter',
    'ylab': '$bn', 'legend': 'Complete quarter',
    'values': L(qv.values), 'partial_months': n_in_last, 'qtr_months': 3,
    'line': {'name': 'y/y (RHS)', 'color': 'GREEN', 'values': qyoy, 'yfmt': 'pct0'},
    'note': ('月度核心净新增资产按季汇总（恒等式可无损累加，见 Exhibit 4）。'
             + (f'末季 {qv.index[-1]} 已含 {n_in_last} 个月，为完整季度。'
                if n_in_last >= 3 else
                f'末季 {qv.index[-1]} 只含 {n_in_last} 个月，柱为浅蓝且右轴 y/y 已作废 —— '
                '拿不满季的累计去比上年完整季度必然砸出一个假坑。')),
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
             'x 轴标的是各季**季末月**；PDF 版此处保留 2 位小数，网页图表引擎的格式器只到 '
             '1 位小数，切到「表格」视图可读到 2 位。'),
})

# ── Exhibit 14：核心净新增资产全历史 ──
ex.append({
    'n': 14, 'kind': 'lines', 'x': 'long', 'fmt': 'usd0', 'xstep': max(1, len(df) // 14),
    'title': 'Core net new assets since 2018',
    'ylab': '$bn', 'zero_line': True,
    'series': [{'name': 'Core net new assets', 'color': 'NAVY', 'values': L(nna.values)}],
    'note': (QNOTE + '。PDF 版此图纵轴从 0 起，2019-04、2022-04、2023-04 三个负值月被压在轴外；'
             '网页版把纵轴放到负区并画出零线，负值月看得见。'
             'PDF 版末 3 个月的红色虚线圈网页版不画。'),
})

# ── Exhibit 15：新开经纪账户全历史（截轴 1,600k）──
ex.append({
    'n': 15, 'kind': 'lines', 'x': 'long', 'fmt': 'f0c', 'xstep': max(1, len(df) // 14),
    'title': 'New brokerage accounts since 2018',
    'ylab': 'k accounts', 'ycap': 1600, 'yfloor': 0,
    'cap_note': 'axis capped — outlier shown in red',
    'series': [{'name': 'New brokerage accounts', 'color': 'NAVY', 'values': L(nba.values)}],
    'note': ('Axis capped at 1,600k so the series is readable. The Oct-2020 reading of 14,718k '
             'is the TD Ameritrade onboarding — a balance transfer, not accounts opened. '
             'Shown in red, not removed。截轴不删点：超界的点画成空心红圈，真值竖排标出。'),
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
ex.append({
    'n': 16, 'kind': 'year_lines', 'fmt': 'usd0', 'xlabels': MONTHS,
    'title': 'Core NNA path by year',
    'ylab': '$bn', 'series': y16, 'highlight': len(y16) - 1,
    'note': ('每年一条线叠在 Jan–Dec 轴上，当年红色加粗。画的是**当月值**不是年初至今累计，'
             '所以 4 月与 12 月那两个季节性尖谷/尖峰可以逐年对齐着看。'),
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
    'rows': [str(y) for y in hyrs], 'cols': MONTHS, 'matrix': matrix,
    'legend': 'Annualised organic growth rate', 'row_head': '年',
    'note': ('Green = faster organic asset gathering。色标取全部有限值的 5/95 分位，'
             '一两个离群月不会把整表压平。'
             '本图为通栏，因此排在汇总表下方的通栏区，编号仍是原 deck 的 Exhibit 18。'),
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

    '<b>核心净新增资产的剔除门槛在 2025 年调过。</b>单一客户流入的剔除阈值从 $10bn 提高到 $25bn，'
    '因此 2025 年前后的「核心」口径不完全可比。原始月报没有给出调整前后的对照值，'
    '这里不做还原，只在此声明。',

    f'<b>两条融资余额序列口径不同，不能接续。</b>Exhibit 9 是<b>月末</b>余额，'
    f'Schwab 自 2026-01 的月报才开始披露，其 13 个月滚动表回溯至 2025-01，'
    f'所以 y/y 从 2026-01 才有；Exhibit 10 是<b>月度平均</b>余额，'
    f'Schwab 从 2020-04 发到 {mlab(avgm.index[-1])} 后停发。两者是不同口径，'
    '不要拼成一条长序列读。日均交易笔数（DATs）同理，只有 2025-01 起的历史。',

    '<b>这里没有「量 → 收入」桥。</b>Schwab 月报既不披露客户现金也不披露生息资产，'
    '唯一能当代理的是客户资产；但生息资产 / 客户资产的比值在过去 '
    f'{len(_bs) - 1} 个季度从 {float(_bs["iea_share"].iloc[0]):.1f}% 单边降到 '
    f'{float(_bs["iea_share"].iloc[-1]):.1f}%（趋势，不是噪音），'
    '把它当常数会造出假精度。所以不搭桥，改把这个比值本身画出来（Exhibit 13）——'
    '它本身就是 NII 增长受限的原因。该图两条线都是<b>季度</b>数据，来自季报。',

    '<b>截轴不删点。</b>Exhibit 15 的纵轴截在 1,600k：2020-10 的 14,718k 是 TD Ameritrade '
    '并表带来的账户转移，不是当月新开户，留着会把 2018 年以来整条线压平。'
    '被截的点画成空心红圈并把真值竖排标出，点没有被删掉。'
    'Exhibit 17 的逐年对照图按同样理由把 2020-10 排除在外。',

    '<b>窗口一律从数据最新月倒推。</b>水平柱图 25 个月、滚存桥与核对表 13 个月、'
    '季度图 14 个季度、逐年对照图 6 年、热力矩阵 9 年；'
    '数据不足窗口长度时按实际长度画（DATs 与月末融资余额即如此），不补零、不外推。',

    '<b>网页版与 PDF 版的已知差异。</b>（1）PDF 的水平柱图在次轴画金色 y/y 折线，'
    '网页版改为柱 + Prior 12mo Avg. 虚线，y/y 与 m/m 收进图内气泡与表格视图；'
    '（2）PDF 在长历史图末 3 个月画红色虚线圈，网页版不画，改用 hover 与表格视图；'
    '（3）Exhibit 13 的 PDF 版保留 2 位小数，网页图表引擎的格式器只到 1 位，表格视图仍是 2 位；'
    '（4）Exhibit 18 为通栏图，被排到汇总表下方的通栏区，编号仍为原 deck 的 18。'
    '所有数值与格式化都在 Python 侧完成，页面不做任何计算。',
]

headline = (
    f'核心净新增资产 {money(_lat_nna, 1)}bn'
    + (f'（{sgn_pct(_y_nna, 0)} y/y）' if _y_nna is not None else '')
    + f' · 年化有机增长率 {_lat_og:.1f}% · 客户总资产 {money(_lat_at, 2)}tn'
    + f' · 日均交易 {_lat_dm:.1f}mn 笔/日'
    + (f'（{sgn_pct(_y_dm, 0)} y/y）' if _y_dm is not None else '')
    + f' · 月末融资余额 {money(_lat_mb, 1)}bn'
    + (f'（{sgn_pct(_y_mb, 0)} y/y）' if _y_mb is not None else '')
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
    with open(path, 'w', encoding='utf-8') as f:
        # 构建日期只写首行注释，不进 payload（否则幂等检查永久失效）
        f.write(f'// 由 build/schw.py 生成于 {datetime.date.today().isoformat()}，请勿手改\n')
        f.write('window.DASH = ')
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')
    print(f'数据截至 {LATEST} | 全序列 {df.index[0]} → {df.index[-1]}（{len(df)} 个月）')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）'
          f' + Exhibit {table["n"]} 核对表')
    print(f'写出 data/schw.js  ({os.path.getsize(path) / 1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
