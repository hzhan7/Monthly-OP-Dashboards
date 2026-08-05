# -*- coding: utf-8 -*-
"""CME Group (CME) 月度成交量 —— 网页看板数据生成器（build/build_cme.py 的移植）。

原 deck：build/build_cme.py（matplotlib → PDF）。本文件把它的每一张 exhibit
重新实现成 data/cme.js 里的一个 payload 对象，页面（assets/page.js + charts.js）
只负责画，不做任何计算。

模版来源（照抄原 deck 的 docstring）：
  · Goldman Sachs「IBKR Monthly」成对图法（水平柱 + 12mo 均线 + YoY 气泡 ⇄ 变化率曲线）
    与 Exhibit 7「堆叠柱 + 次轴占比线」的量能/结构同框做法
  · Barclays「IBKR July Monthly Metrics」的 day-count 调整 —— 该报告因交易日数差异，
    把「股票成交总量 +7%」修正为「按日 -5%」，方向被口径反转。CME 官方 xlsx 里
    直接给了每月交易日数，故本页用 Exhibit 3 显式呈现总量口径与按日口径的差。
数据源：CME Group IR 月度成交量 xlsx（cmegroupinc.gcs-web.com/monthly-volume），
        次月第 1-2 个工作日。费率取 series/fee_rates.csv 里的季度 RPC。

读取：  series/cme.csv、series/fee_rates.csv（唯一数据源，不读 build/data/）
输出：  data/cme.js

幂等：payload 里不放构建日期（只写文件首行注释），不用随机数，窗口一律从数据
      最新月倒推 —— 同一份 CSV 重复跑，输出逐字节相同（除首行）。
"""
import datetime
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
OUT = os.path.join(ROOT, 'data', 'cme.js')

SRC = 'Source: CME Group monthly volume reports; format after Goldman Sachs GIR / Barclays'

# 资产类别 →（CSV 列, 图例名, 引擎色名）。
# 原 deck 的金属用 gsx.GOLD(#BF9000)，charts.js 的 C.* 里没有金色（engine_kinds.md
# 明确说了这一点）—— 后来在 charts.js 的 C.* 里补上了 GOLD(#BF9000)，与 gsx.py 同色，
# 所以金属恢复用 GOLD。不能拿 RED 当数据色：RED 在这套语言里是断点与离群值的专用色，
# 一根红柱到底是「金属品种」还是「这个点被截轴了」会分不清。
CLS = [('adv_rates_kcontracts', 'Interest rates', 'NAVY'),
       ('adv_equity_kcontracts', 'Equity index', 'MBLUE'),
       ('adv_energy_kcontracts', 'Energy', 'BLUE'),
       ('adv_ag_kcontracts', 'Agricultural', 'GRAY'),
       ('adv_fx_kcontracts', 'FX', 'GREEN'),
       ('adv_metals_kcontracts', 'Metals', 'GOLD')]

WIN_BAR = 13     # gs_bar 类近期图：契约 §5.4「近期图固定 13 个月」
WIN_LINE = 25    # 曲线类图：照搬原 deck 的 win=25
WIN_QTR = 14     # 季度柱：照搬原 deck 的 win=14
HEAT_YEARS = 10  # 热力矩阵：照搬原 deck 的 n_years=10
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
ZH_MONTH = '一二三四五六七八九十十一十二'


def mlab(p):
    """与 gsx.mlab 一致：Period('2026-07') → 'Jul-26'。"""
    return f'{MONTHS[p.month - 1]}-{p.year % 100:02d}'


def num(v, dec=0):
    if v is None or not np.isfinite(v):
        return '—'
    return f'{v:,.{dec}f}'


def _z(v, dec):
    """把 -0.0 这类「四舍五入后其实是零」的值归零，否则会印出 '-0.0pp'。"""
    v = round(float(v), dec)
    return 0.0 if v == 0 else v


def pct(v, dec=1):
    """带符号的百分比变化，正负号交给 f-string 的 + 标志。"""
    if v is None or not np.isfinite(v):
        return '—'
    return f'{_z(v, dec):+,.{dec}f}%'


def pp(v, dec=1):
    """百分点差（比率类指标的差异一律用 pp）。"""
    if v is None or not np.isfinite(v):
        return '—'
    return f'{_z(v, dec):+.{dec}f}pp'


def L(a):
    """序列 → JSON 安全的 float 列表（NaN → None）。"""
    return [None if v is None or not np.isfinite(float(v)) else round(float(v), 6) for v in a]


# ══════════════════════════ 1. 读数据（只读 series/*.csv）══════════════════════════
def load():
    p = os.path.join(SERIES, 'cme.csv')
    df = pd.read_csv(p)
    need = ['month', 'adv_total_kcontracts', 'oi_total_contracts', 'trading_days'] + \
           [c for c, _, _ in CLS]
    miss = [c for c in need if c not in df.columns]
    if miss:                                     # 失败要响：绝不静默写 NaN 上线
        raise SystemExit(f'series/cme.csv 缺列 {miss}')
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    df = df.set_index('month').sort_index()
    gaps = [(df.index[i] - df.index[i - 1]).n for i in range(1, len(df))]
    if set(gaps) != {1}:
        bad = [str(df.index[i]) for i in range(1, len(df)) if (df.index[i] - df.index[i - 1]).n != 1]
        raise SystemExit(f'series/cme.csv 月份不连续，断在 {bad}')
    for c in need[1:]:
        if df[c].isna().any():
            raise SystemExit(f'series/cme.csv 的 {c} 有缺值，无法画连续序列')
    return df.astype(float)


def rpc_quarterly(metrics):
    """从 series/fee_rates.csv 取 CME 的季度 RPC（$/张）。"""
    d = pd.read_csv(os.path.join(SERIES, 'fee_rates.csv'))
    d = d[d['company'] == 'CME']
    out = {}
    for key, metric in metrics:
        s = d[d['metric'] == metric]
        if not len(s):
            raise SystemExit(f'fee_rates.csv 里没有 CME/{metric}')
        u = set(s['unit'].dropna())
        if u != {'USD_per_contract'}:
            raise SystemExit(f'CME/{metric} 单位不是 USD_per_contract：{u}')
        q = pd.PeriodIndex(s['period'].str.replace('-', ''), freq='Q')
        out[key] = pd.Series(s['value'].astype(float).values, index=q).sort_index()
    return out


def to_monthly(rate_q, month_index):
    """季度费率 → 月度：当季各月用该季费率；最新季之后沿用最后一个已知值（同 bridge.to_monthly）。"""
    q = pd.PeriodIndex(month_index).asfreq('Q')
    return pd.Series([rate_q.get(qq, np.nan) for qq in q], index=month_index, dtype=float).ffill()


# ══════════════════════════ 2. 派生序列（照抄原 deck 的算法）══════════════════════════
df = load()
adv = df['adv_total_kcontracts']
days = df['trading_days']
LATEST = df.index[-1]

df['total_vol_mn'] = adv * days / 1000.0                    # 月度总成交量 = ADV x 交易日（百万张）
df['adv_mn'] = adv / 1000.0
df['oi_total_mn'] = df['oi_total_contracts'] / 1e6
df['vol_yoy'] = df['total_vol_mn'].pct_change(12) * 100
df['adv_yoy'] = adv.pct_change(12) * 100
df['daycount_effect'] = df['vol_yoy'] - df['adv_yoy']       # 两者之差 = 交易日数贡献
df['rates_share'] = df['adv_rates_kcontracts'] / adv * 100

RPC = rpc_quarterly([('total', 'rpc_total'), ('rates', 'rpc_interest_rates'),
                     ('equity', 'rpc_equity_indexes'), ('energy', 'rpc_energy'),
                     ('metals', 'rpc_metals')])
rpc_m = to_monthly(RPC['total'], df.index)
df['implied_txn_rev_usdmn'] = df['total_vol_mn'] * rpc_m    # 百万张 x $/张 = $mn
RPC_Q, RPC_V = RPC['total'].index[-1], float(RPC['total'].iloc[-1])

BR_NOTE = ('Assumption: monthly transaction revenue = contracts traded x average rate per contract '
           f'({RPC_Q} = ${RPC_V:.3f}, held flat after). CME derives RPC from reported revenue, so '
           'closed quarters reconstruct a known total — the value is the current quarter. '
           '费率是季度值，当季各月共用该季 RPC，最新季之后沿用；品种结构变化会让混合 RPC 偏离，'
           '见 Exhibit 13。')

W13 = df.index[-WIN_BAR:]
W25 = df.index[-WIN_LINE:]
XL13 = [mlab(p) for p in W13]
XL25 = [mlab(p) for p in W25]
XL_LONG = [mlab(p) for p in df.index]


def win(col, n):
    return df[col].iloc[-n:].values


def prior12_avg(col):
    """12 个月均线：本月之前的 12 个月（= 13 个月窗口的前 12 个点）。"""
    v = df[col].iloc[-WIN_BAR:-1].values
    return round(float(np.mean(v)), 6)


def yoy_txt(col, dec=1):
    v = df[col].values
    return pct(v[-1] / v[-13] * 100 - 100, dec)


# ══════════════════════════ 3. Exhibit 1：汇总表 ══════════════════════════
CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12

SUM_ROWS = [
    ('group', 'Average daily volume (k contracts)', None, None),
    ('row', 'Total ADV', 'adv_total_kcontracts', 0),
    ('row', 'Interest rates', 'adv_rates_kcontracts', 0),
    ('row', 'Equity index', 'adv_equity_kcontracts', 0),
    ('row', 'Energy', 'adv_energy_kcontracts', 0),
    ('row', 'Agricultural', 'adv_ag_kcontracts', 0),
    ('row', 'FX', 'adv_fx_kcontracts', 0),
    ('row', 'Metals', 'adv_metals_kcontracts', 0),
    ('group', 'Volume and open interest', None, None),
    ('row', 'Total contracts traded (mn)', 'total_vol_mn', 1),
    ('row', 'Month-end open interest (mn)', 'oi_total_mn', 1),
    ('row', 'Trading days', 'trading_days', 0),
]


def pctile36(s):
    """近 36 个月分位。近乎单调的序列（逐月上升占比 ≥ 90%）留空 —— 分位恒为 100 是噪音。"""
    h = s.iloc[-36:].values
    c = h[-1]
    if len(h) < 8 or not np.isfinite(c):
        return None
    d = np.diff(h)
    if len(d) and float((d >= 0).sum()) / len(d) >= 0.90:
        return None
    return float((h < c).sum()) / max(1, len(h) - 1) * 100


def summary():
    rows = []
    for kind, label, col, dec in SUM_ROWS:
        if kind == 'group':
            rows.append({'kind': 'group', 'label': label})
            continue
        s = df[col]
        c, p1, p12 = float(s[CUR]), float(s[PRV]), float(s[YAG])
        mm = (c / p1 - 1) * 100 if p1 else np.nan
        yy = (c / p12 - 1) * 100 if p12 else np.nan
        q = pctile36(s)
        cells = [{'v': num(c, dec)}, {'v': num(p1, dec)}, {'v': num(p12, dec)},
                 {'v': pct(mm), 'cls': 'pos' if mm > 0 else ('neg' if mm < 0 else '')},
                 {'v': pct(yy), 'cls': 'pos' if yy > 0 else ('neg' if yy < 0 else '')}]
        if q is None:
            cells.append({'v': ''})
        else:
            cells.append({'v': f'{q:.0f}',
                          'cls': 'hi' if q >= 66 else ('lo' if q <= 33 else '')})
        rows.append({'label': label, 'cells': cells})
    return {
        'title': f'CME Group monthly volume summary — {mlab(CUR)}',
        'heads': [f'本月 {mlab(CUR)}', f'上月 {mlab(PRV)}', f'去年同月 {mlab(YAG)}',
                  'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': rows,
        'note': ('ADV is already day-count neutral; total contracts traded is not. '
                 'Exhibit 3 isolates the difference.（原 PDF 此处误写作 Exhibit 4 —— '
                 '汇总表本身占 Exhibit 1，day-count 图是 Exhibit 3。）'
                 '3Y %ile = 当月读数在最近 36 个月里高于多少百分比的观测；'
                 '近乎单调的序列留空（见「口径与方法说明」第 7 条）。'
                 '全部为 CME 官方披露值，无推导。'),
    }


# ══════════════════════════ 4. Exhibit 2..18 ══════════════════════════
def gs_bar(n, col, title, ylab, fmt, legend, note=None, src_extra=None):
    """← gsx.lvl_bar：浅蓝柱 + 12 个月均线 + y/y 气泡。窗口 13 个月（契约 §5.4）。"""
    ex = {'n': n, 'kind': 'gs_bar', 'title': title, 'fmt': fmt, 'ylab': ylab,
          'legend': legend, 'values': L(win(col, WIN_BAR)), 'avg12': prior12_avg(col),
          'yoy_txt': yoy_txt(col)}
    if note:
        ex['note'] = note
    if src_extra:
        ex['src_extra'] = src_extra
    return ex


ex = []

ex.append(gs_bar(2, 'adv_mn', 'Total average daily volume', 'mn contracts / day', 'f1',
                 'Total ADV'))

ex.append({
    'n': 3, 'kind': 'lines_endlabels', 'fmt': 'f1', 'xlabels': XL25,
    'title': 'Total volume vs. ADV growth: the day-count gap',
    'ylab': '% y/y', 'zero_line': True,
    'series': [
        {'name': 'Total contracts y/y', 'color': 'GRAY', 'values': L(win('vol_yoy', WIN_LINE))},
        {'name': 'ADV y/y (day-count neutral)', 'color': 'NAVY',
         'values': L(win('adv_yoy', WIN_LINE))},
    ],
    'src_extra': ('Gap between the two lines is purely the change in trading days — '
                  'the Barclays adjustment'),
    'note': (f'{mlab(CUR)}：总成交 {pct(df["vol_yoy"][CUR])} y/y，按日 {pct(df["adv_yoy"][CUR])} y/y，'
             f'交易日数贡献 {pp(float(df["daycount_effect"][CUR]))}'
             f'（{days[CUR]:.0f} 天 vs 去年同月 {days[YAG]:.0f} 天）。'),
})

_stack13 = {c: win(c, WIN_BAR) for c, _, _ in CLS}
_share13 = (win('adv_rates_kcontracts', WIN_BAR) + win('adv_equity_kcontracts', WIN_BAR)) \
    / win('adv_total_kcontracts', WIN_BAR) * 100
# 右轴上界取 10 的整数倍：占比线要压在堆叠柱之上，太高会掉进柱子里
_ymax = float(np.ceil(np.nanmax(_share13) / 10.0) * 10)
if np.nanmax(_share13) / _ymax > 0.995:
    _ymax += 10
ex.append({
    'n': 4, 'kind': 'stacked_dual', 'fmt': 'f0c', 'xlabels': XL13,
    'title': 'ADV mix by asset class',
    'ylab': 'k contracts / day', 'ylab2': '% rates + equity',
    'stacks': [{'name': nm, 'color': cl, 'values': L(_stack13[c])} for c, nm, cl in CLS],
    'line': {'name': '% rates + equity (RHS)', 'color': 'GREEN',
             'values': L(_share13), 'ymax': _ymax, 'yfmt': 'pct0'},
    'note': ('六个品种加总即披露的 Total ADV（CME 的品种划分是穷尽且互斥的）。'
             '右轴是利率 + 股指两大品种占总 ADV 的比重 —— 体量与结构同框，'
             '总量持平但结构位移一样会改变混合费率（见 Exhibit 13）。'),
})

ex.append({
    'n': 5, 'kind': 'lines_endlabels', 'fmt': 'f0c', 'xlabels': XL25,
    'title': 'ADV by asset class', 'ylab': 'k contracts / day',
    'series': [{'name': nm, 'color': cl, 'values': L(win(c, WIN_LINE))} for c, nm, cl in CLS],
})

ex.append({
    'n': 6, 'kind': 'lines', 'x': 'long', 'full': True, 'height': 300,
    'fmt': 'f1', 'yfmt': 'f0', 'xstep': 12, 'xrot': 90, 'zero_line': True,
    'title': 'Full ADV history since 2008', 'ylab': 'mn contracts / day',
    'series': [{'name': 'Total ADV', 'color': 'NAVY', 'values': L(df['adv_mn'].values)}],
    'src_extra': f'Full disclosed history: {mlab(df.index[0])} – {mlab(LATEST)}（{len(df)} 个月）',
    'note': ('原 PDF 在末端画了一个红色虚线椭圆圈出最近 3 个月，网页引擎没有对应的注解图元，'
             '故未移植；最近 13 个月的读数见 Exhibit 2 与末尾核对表。'),
})

_qs = df['total_vol_mn'].groupby(df.index.asfreq('Q')).agg(['sum', 'count'])
_qv = _qs['sum'].values
_qyoy = np.array([(_qv[i] / _qv[i - 4] - 1) * 100 if i >= 4 and _qv[i - 4] else np.nan
                  for i in range(len(_qv))])
_npart = int(_qs['count'].iloc[-1])
ex.append({
    'n': 7, 'kind': 'qtr_bar', 'fmt': 'f0c', 'label_fmt': 'f0c',
    'xlabels': [str(p) for p in _qs.index[-WIN_QTR:]],
    'title': 'Contracts traded aggregated to quarters', 'ylab': 'mn contracts',
    'ylab2': '% y/y',
    'values': L(_qv[-WIN_QTR:]),
    'partial_months': _npart, 'qtr_months': 3,
    'line': {'name': 'y/y (RHS)', 'color': 'GREEN', 'values': L(_qyoy[-WIN_QTR:]),
             'yfmt': 'pct0'},
    'src_extra': 'Latest bar is quarter-to-date and not comparable to full quarters',
    'note': (f'季度合计 = 该季各月「ADV x 当月交易日」之和，在 Python 侧算好。'
             f'末柱 {_qs.index[-1]} 只含 {_npart} 个月（浅蓝），其右轴 y/y 已被作废 —— '
             '拿未满季去比上年完整季必然砸出一个假坑。'),
})

ex.append(gs_bar(8, 'oi_total_mn', 'Month-end total open interest', 'mn contracts', 'f1',
                 'Month-end OI',
                 note='月末未平仓合约是存量口径（期末快照），与 ADV 这类流量口径不可直接相加。'))
ex.append(gs_bar(9, 'adv_rates_kcontracts', 'Interest-rate complex ADV',
                 'k contracts / day', 'f0c', 'Interest rates ADV'))
ex.append(gs_bar(10, 'adv_equity_kcontracts', 'Equity-index complex ADV',
                 'k contracts / day', 'f0c', 'Equity index ADV'))
ex.append(gs_bar(11, 'adv_energy_kcontracts', 'Energy complex ADV',
                 'k contracts / day', 'f0c', 'Energy ADV'))
ex.append(gs_bar(12, 'implied_txn_rev_usdmn', 'Implied transaction revenue', '$mn / month',
                 'usd0', 'Implied transaction revenue', note=BR_NOTE))

_rq = RPC['total'].index[-WIN_QTR:]
ex.append({
    'n': 13, 'kind': 'lines_endlabels', 'fmt': 'usd2',
    'xlabels': [mlab(q.asfreq('M', 'end')) for q in _rq],
    'title': 'Rate per contract by asset class', 'ylab': '$ per contract',
    'series': [
        {'name': 'Interest rates', 'color': 'NAVY', 'values': L(RPC['rates'].reindex(_rq).values)},
        {'name': 'Equity index', 'color': 'MBLUE', 'values': L(RPC['equity'].reindex(_rq).values)},
        {'name': 'Energy', 'color': 'BLUE', 'values': L(RPC['energy'].reindex(_rq).values)},
        {'name': 'Metals', 'color': 'GOLD', 'values': L(RPC['metals'].reindex(_rq).values)},
    ],
    'src_extra': ('RPC differs several-fold across complexes, so a volume mix shift moves blended '
                  'revenue even when total ADV is flat. This is the main uncertainty in the bridge '
                  'above.'),
    'note': (f'季度值，x 轴标的是各季末月（{mlab(_rq[0].asfreq("M", "end"))} = 1Q{_rq[0].year % 100:02d}，'
             f'最新为 {RPC_Q}）。'
             f'{mlab(_rq[-1].asfreq("M", "end"))}：利率 ${RPC["rates"].iloc[-1]:.3f}、'
             f'股指 ${RPC["equity"].iloc[-1]:.3f}、能源 ${RPC["energy"].iloc[-1]:.3f}、'
             f'金属 ${RPC["metals"].iloc[-1]:.3f} —— 图上按 $0.01 显示（原 PDF 为 $0.001），'
             '第三位小数以此注为准。'),
})

ex.append(gs_bar(14, 'adv_fx_kcontracts', 'FX complex ADV', 'k contracts / day', 'f0c', 'FX ADV'))
ex.append(gs_bar(15, 'adv_metals_kcontracts', 'Metals complex ADV', 'k contracts / day', 'f0c',
                 'Metals ADV'))
ex.append(gs_bar(16, 'adv_ag_kcontracts', 'Agricultural complex ADV', 'k contracts / day', 'f0c',
                 'Agricultural ADV'))


def heat(n, col, title, src_extra, fmt='pct0', legend=None):
    s = df[col].dropna()
    yrs = sorted({p.year for p in s.index})[-HEAT_YEARS:]
    M = [[None] * 12 for _ in yrs]
    for p, v in s.items():
        if p.year in yrs:
            M[yrs.index(p.year)][p.month - 1] = round(float(v), 6)
    return {'n': n, 'kind': 'heat_matrix', 'full': True, 'title': title, 'fmt': fmt,
            'rows': [str(y) for y in yrs], 'cols': MONTHS, 'matrix': M,
            'legend': legend or title, 'cell_h': 20, 'row_lab_w': 38, 'row_head': '年',
            'src_extra': src_extra}


ex.append(heat(17, 'adv_yoy', 'Total ADV y/y growth (%)',
               'Green = faster y/y growth, red = slower', legend='Total ADV y/y'))
ex.append(heat(18, 'rates_share', 'Interest-rate share of total ADV (%)',
               'Rates is the largest and most rate-cycle-sensitive complex',
               legend='Rates share of ADV'))

# ══════════════════════════ 5. Exhibit 19：核对表（官方原始单位）══════════════════════════
TBL_COLS = [('Total ADV (k)', 'adv', 'adv_total_kcontracts', 3),
            ('Rates (k)', 'rates', 'adv_rates_kcontracts', 3),
            ('Equity (k)', 'eq', 'adv_equity_kcontracts', 3),
            ('Energy (k)', 'en', 'adv_energy_kcontracts', 3),
            ('Ag (k)', 'ag', 'adv_ag_kcontracts', 3),
            ('FX (k)', 'fx', 'adv_fx_kcontracts', 3),
            ('Metals (k)', 'me', 'adv_metals_kcontracts', 3),
            ('Open interest (contracts)', 'oi', 'oi_total_contracts', 0),
            ('Trading days', 'days', 'trading_days', 0)]
table = {
    'n': 19, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）', 'idx': '月份',
    'cols': [[h, k] for h, k, _, _ in TBL_COLS],
    'rows': [dict({'xl': mlab(p)},
                  **{k: num(float(df[c][p]), d) for _, k, c, d in TBL_COLS})
             for p in W13],
}

# ══════════════════════════ 6. 口径与方法说明 ══════════════════════════
NOTES = [
    f'<b>数据源与节奏。</b>CME Group IR 月度成交量 xlsx（cmegroupinc.gcs-web.com/monthly-volume），'
    f'次月第 1-2 个工作日发布。本页覆盖 {mlab(df.index[0])} – {mlab(LATEST)} 共 {len(df)} 个连续月，'
    f'无缺月；ADV、未平仓合约、交易日数三项均为公司直接披露，未经加工。',

    '<b>版式出处。</b>Goldman Sachs「IBKR Monthly」的成对图法（水平柱 + 12 个月均线 + YoY 气泡）'
    '与其 Exhibit 7「堆叠柱 + 次轴占比线」的量能/结构同框做法；day-count 那张图取自 Barclays'
    '「IBKR July Monthly Metrics」。',

    '<b>ADV 与总量的口径差（Barclays 调整）。</b>ADV 本身已按交易日中性化，总成交合约数没有。'
    'Barclays 那份报告因交易日数差异，把「股票成交总量 +7%」修正为「按日 -5%」，方向被口径整个反转。'
    'Exhibit 3 把两条同比并排画出来，两线之差纯粹是交易日数的变化；'
    '月度总成交量 = ADV × 当月交易日数，这一步换算是本页做的，不是公司披露的单独口径。',

    f'<b>唯一的推导值：Exhibit 12。</b>Implied transaction revenue = 当月成交合约数 × 每张平均费率'
    f'（RPC）。RPC 是季度值（CME 季报），当季各月共用该季费率，最新季（{RPC_Q} = ${RPC_V:.3f}）'
    '之后沿用。CME 的 RPC 本身是用已披露收入倒推的，所以已收官季度只是把一个已知总额重建一遍 —— '
    '这张图的价值全在<b>当前未收官的季度</b>。标题带 Implied 即表示非公司披露值。',

    '<b>RPC 的口径风险。</b>各品种 RPC 相差数倍（Exhibit 13），因此总 ADV 不变、只要品种结构位移，'
    '混合费率与隐含收入照样会动。这是上面那座桥最大的不确定性，也是 Exhibit 4 把结构与体量画在'
    '同一张图里的原因。',

    f'<b>未满季不可直读。</b>Exhibit 7 的末柱是季度至今（{_qs.index[-1]} 目前只含 {_npart} 个月），'
    '用浅蓝标出，其右轴 y/y 的最后一点被引擎强制作废 —— 拿未满季的累计去比上年完整季，'
    '必然砸出一个纯口径造成的假坑。',

    '<b>汇总表的 3Y %ile。</b>= 当月读数在最近 36 个月里高于多少百分比的观测。'
    '近乎单调的序列（逐月不降的月份占比 ≥ 90%）留空 —— 那种序列的分位恒为 100，是噪音不是信息。'
    '比率类指标的差异一律用 pp/bp；本页汇总表里没有比率行，故全部是百分比变化。',

    '<b>口径断点：本页没有。</b>CME 的 ADV / 未平仓合约 / 交易日口径自 2008-01 至今保持一致，'
    '品种六分类穷尽且互斥，所以全页没有红色竖虚线断点，相邻期可以直读。'
    '若日后出现并购并表或品种重分类，必须在这里登记并在对应图上画出 break，'
    '不能只靠图注文字提一句。',

    '<b>与原 PDF 版的有意差异（三处）。</b>(a) gs_bar 类近期图的窗口由 25 个月收到 13 个月 —— '
    '契约 §5.4 的规定，且「12 个月均线 + y/y 气泡」这套标注本就按 13 个月窗口定义；'
    '曲线类（Exhibit 3/5）与长历史图（Exhibit 6）的窗口一字未改。'
    '(b) 网页引擎的调色板不含 PDF 的金色，金属品种改用红色（Exhibit 4/5/13）。'
    '(c) Exhibit 6 的「最近 3 个月红色虚线圈」与 Exhibit 13 的第三位小数无对应实现，'
    '前者说明写进图注，后者的精确值写进图注。',

    '<b>核对表（Exhibit 19）用官方原始单位，不做任何换算</b>：ADV 为千张/日、未平仓合约为张、'
    '交易日为天，可直接与 CME 月度 xlsx 逐格对。图上的「百万张」「百万美元」都是本页换算后的口径，'
    '核对时请以核对表为准。',
]

# ══════════════════════════ 7. 抬头与 payload ══════════════════════════
_adv_yy = float(df['adv_yoy'][CUR])
_vol_yy = float(df['vol_yoy'][CUR])
_dc = float(df['daycount_effect'][CUR])
_oi_yy = (float(df['oi_total_mn'][CUR]) / float(df['oi_total_mn'][YAG]) - 1) * 100
_share = float(df['rates_share'][CUR])

payload = {
    'ticker': 'cme',
    'tracker': 'CME Monthly Volume Tracker',
    'title': f'CME Group (CME): 月度成交量跟踪 — {CUR.year}年{CUR.month}月',
    'data_through': str(CUR),
    'through_label': f'{CUR.year} 年 {CUR.month} 月',
    'subtitle': (f'数据源：CME Group IR 月度成交量报告（次月第 1-2 个工作日发布）· '
                 f'覆盖 {mlab(df.index[0])} – {mlab(LATEST)}（{len(df)} 个月）· '
                 f'版式仿 Goldman Sachs GIR「IBKR Monthly」与 Barclays day-count 调整 · 仅图，无评论'),
    'headline': (f'ADV {df["adv_mn"][CUR]:,.1f}mn 张/日（{pct(_adv_yy)} y/y）· '
                 f'总成交 {df["total_vol_mn"][CUR]:,.0f}mn 张（{pct(_vol_yy)} y/y，'
                 f'交易日贡献 {pp(_dc)}）· 月末未平仓 {df["oi_total_mn"][CUR]:,.1f}mn 张'
                 f'（{pct(_oi_yy)} y/y）· 利率品种占 ADV {_share:.0f}% · '
                 f'隐含交易收入 ${df["implied_txn_rev_usdmn"][CUR]:,.0f}mn'),
    'hub_line': (f'ADV {df["adv_mn"][CUR]:,.1f}mn 张/日，{pct(_adv_yy)} y/y；'
                 f'利率品种占 {_share:.0f}%'),
    'source': SRC,
    'xlabels': XL13,
    'xlabels_long': XL_LONG,
    'summary': summary(),
    'exhibits': ex,
    'table': table,
    'notes': NOTES,
    'footer': 'CME Group (CME) · monthly volume reports · charts only, no commentary · '
              'personal research use',
}


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        # 构建日期只写首行注释，不进 payload —— 进了 payload，monthly_run 的
        # 「data 有没有实质变化」检查（忽略首行的正文比较）就永久失效。
        f.write(f'// 由 build/cme.py 生成于 {datetime.date.today().isoformat()}，请勿手改\n')
        f.write('window.DASH = ')
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')
    print(f'数据截至 {CUR} | 月份 {df.index[0]} → {LATEST}（{len(df)}）')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张）+ '
          f'Exhibit {table["n"]} 核对表')
    print(f'写出 {OUT}（{os.path.getsize(OUT) / 1024:.1f} KB）')
    print(payload['headline'])


if __name__ == '__main__':
    main()
