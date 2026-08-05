# -*- coding: utf-8 -*-
"""Robinhood Markets (HOOD) 月度经营指标 —— 网页看板数据生成器。

把 build/build_hood.py（matplotlib / PDF）里的 Exhibit 1-27 逐张移植成 payload 里的
exhibit 对象，写出 data/hood.js。顺序、编号、标题文案、图注、口径断点全部照搬原 deck。

数据源（唯一）：series/hood.csv（月度）与 series/hood_q.csv（季度 GAAP P&L + 季度成交量）。
两份都来自 investors.robinhood.com → Monthly Metrics 的同一个 Excel；HOOD 的月度数据
按 Reg FD 挂在 IR 网站上，不走 8-K，盯 EDGAR 抓不到。

gsx 函数 → 网页 kind 的对应：
    gsx.lvl_bar        → bar_line_dual   柱（左轴）+ 右轴 y/y 线
                         （**不用 gs_bar**：gs_bar 画的是 "Prior 12mo Avg." 虚线，而本
                          deck 相对 GS 原版的第一处改动就是把滚动均线换成 y/y。用
                          gs_bar 等于把被砍掉的东西装回来。）
    gsx.stack_share    → stacked_dual
    gsx.multi_line     → lines_endlabels（费率那张退回 lines，见下）
    gsx.indexed_lines  → lines
    gsx.long_line      → lines
    gsx.bridge_bar     → bridge_bar
    gsx.implied_vs_actual → grouped_bars
    gsx.qtr_bar        → qtr_bar
    gsx.year_lines     → year_lines
    gsx.heat_matrix    → heat_matrix
    gsx.summary_table  → payload['summary']

三处与 PDF 的有意差异（引擎能力所限，均在对应图注里写明）：
  1. Exhibit 13（费率）PDF 用对数轴，charts.js 没有对数轴 → 线性轴 + 图注提示切表格视图。
     同时该图退回 kind='lines'：lines_endlabels 会对首/末点无条件调用格式器，而事件合约
     费率在 2023Q3 是缺失的（成交量四舍五入成 0.0），会直接抛 TypeError 把整页打挂。
  2. lvl_bar 的柱顶数值与 m/m 气泡：bar_line_dual 不画柱顶数值（数值在 tooltip 与表格
     视图里），m/m 改写进图注文字。
  3. Exhibit 26/27 热力矩阵不设 full:true —— 通栏卡片会被 page.js 挂到 #lead 里，
     排到 Exhibit 2 前面去，图序就乱了。半栏 12 列仍然读得清。
"""
import datetime
import json
import os

import numpy as np
import pandas as pd

D = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(D)
SRC = 'Source: Robinhood monthly metrics and quarterly reports'

# ────────────────────────── 读数据（只从 series/ 读）──────────────────────────
df = pd.read_csv(os.path.join(ROOT, 'series', 'hood.csv'), index_col=0)
df.index = pd.PeriodIndex(df.index, freq='M')
df = df.sort_index().apply(pd.to_numeric, errors='coerce')

q = pd.read_csv(os.path.join(ROOT, 'series', 'hood_q.csv'), index_col=0)
q.index = pd.PeriodIndex(q.index, freq='Q')
q = q.sort_index().apply(pd.to_numeric, errors='coerce')

# 失败要响：窗口靠「最新月倒推」，序列断档会让 y/y 与季度合计整体错位
gaps = [(df.index[i] - df.index[i - 1]).n for i in range(1, len(df))]
if set(gaps) != {1}:
    raise SystemExit(f'series/hood.csv 月份不连续：{sorted(set(gaps))}')
if len(df) < 25 or len(q) < 8:
    raise SystemExit(f'序列太短：月度 {len(df)}、季度 {len(q)}')

LATEST = df.index[-1]
LAST_Q = q.index[-1]

# ────────────────────────── 派生列（逐行照搬 build_hood.py）──────────────────────────
BRK_WONDERFI = pd.Period('2026-06', 'M')   # 收购 WonderFi，带进 ~30 万 Funded Customers
BRK_BITSTAMP = pd.Period('2025-06', 'M')   # Bitstamp 并入净流入、加密成交量与客户数
BRK_SWEEP = pd.Period('2026-02', 'M')      # High-Yield Cash 改版，>$6bn 从 sweep 挪到 deposits

tpa = df['total_platform_assets_usdbn']
nd = df['net_deposits_usdbn']
df['organic_growth_ann'] = nd * 12 / tpa.shift(1) * 100        # 年化有机增速
df['market_gains_usdbn'] = tpa.diff() - nd                      # 恒等式残差 = 市值变动
df['tpa_change_usdbn'] = tpa.diff()
df['crypto_bitstamp_share'] = (df['adv_crypto_bitstamp_usdmn']
                               / df['adv_crypto_usdmn'] * 100)
# $bn / mn 客户 = 10^9/10^6 = 千美元/客户，本身已经是 $k，不要再乘 1000
df['assets_per_customer_usdk'] = tpa / df['funded_customers_mn']
df['dats_total_mn'] = (df['dats_equity_mn'] + df['dats_options_mn']
                       + df['dats_crypto_mn'])

# ── 费率（季度实际收入 ÷ 季度成交量）与收入桥 ──
RATE = [('Options', 'rev_options_usdmn', 'q_vol_options_mn', 'vol_options_mn'),
        ('Equities', 'rev_equities_usdmn', 'q_vol_equity_usdbn', 'vol_equity_usdbn'),
        ('Crypto', 'rev_crypto_usdmn', 'q_vol_crypto_usdbn', 'vol_crypto_usdbn'),
        ('Event contracts', 'rev_event_usdmn', 'q_vol_event_bn', 'vol_event_bn')]


def _rate(rc, vc, p):
    """某季某类的反解费率。成交量为 0 时公司仍可能报几百万收入（事件合约 2024Q4 就是
    量四舍五入成 0.0、收入 $5mn），直接相除会得到 inf 并顺着 ffill 污染整条链。"""
    v, r = q[vc].get(p, np.nan), q[rc].get(p, np.nan)
    if not (np.isfinite(v) and np.isfinite(r)) or v <= 0:
        return np.nan
    return r / v


rate_q = {}
for _nm, _rc, _vc, _mc in RATE:
    rate_q[_nm] = pd.Series({p: _rate(_rc, _vc, p) for p in q.index}, dtype=float)
# 量纲：$1bn 名义额产生 r 个 $mn，即 r/1000 的费率 = r x 10 bp。
rate_options_c = rate_q['Options'] * 100          # $mn/mn张 = $/张 → 美分/张
rate_equities_bp = rate_q['Equities'] * 10        # $mn/$bn → bp
rate_crypto_bp = rate_q['Crypto'] * 10            # $mn/$bn → bp
rate_event_c = rate_q['Event contracts'] * 0.1    # $mn/bn张 → 美分/张

# 样本外预测：每个季度用**上一季**的费率 x 本季实际成交量。
# 某一类若上季没有可用费率（业务还没起量），该类同时从预测和实际里剔除。
pred = pd.Series(index=q.index, dtype=float)
actual_txn = pd.Series(index=q.index, dtype=float)
for i in range(1, len(q)):
    cur_q, prv_q = q.index[i], q.index[i - 1]
    tot = act = 0.0
    n_cls = 0
    for _nm, _rc, _vc, _mc in RATE:
        r, v = _rate(_rc, _vc, prv_q), q[_vc].get(cur_q, np.nan)
        if not (np.isfinite(r) and np.isfinite(v)):
            continue
        tot += r * v
        act += q[_rc][cur_q]
        n_cls += 1
    if n_cls:
        pred[cur_q], actual_txn[cur_q] = tot, act

# 隐含月度交易收入 = 当月成交量 x 该月所属季度的费率（最新季之后沿用最后一个已知费率）
qi = pd.PeriodIndex(df.index).asfreq('Q')
imp = pd.DataFrame(index=df.index)
for _nm, _rc, _vc, _mc in RATE:
    rq = rate_q[_nm].ffill()
    rm = pd.Series([rq.get(x, np.nan) for x in qi], index=df.index).ffill()
    imp[_nm] = rm * df[_mc]
df['implied_txn_rev_usdmn'] = imp.sum(axis=1, min_count=1)


# ────────────────────────── 小零件 ──────────────────────────
def mlab(p):
    return p.strftime('%b-%y')


def L(a):
    """序列 → JSON 数组，非有限值一律 null（不许把 NaN/inf 写上线）。"""
    out = []
    for v in (a.values if hasattr(a, 'values') else a):
        try:
            fv = float(v)
        except (TypeError, ValueError):
            out.append(None)
            continue
        out.append(round(fv, 6) if np.isfinite(fv) else None)
    return out


def fnum(v, dec=1, money='', pct=False):
    if v is None or not np.isfinite(v):
        return '—'
    return money + f'{v:,.{dec}f}' + ('%' if pct else '')


def pp_txt(x):
    """gsx._pp：小变化给 1 位小数，大变化给 0 位。"""
    if not np.isfinite(x):
        return '—'
    v = x * 100
    return f'{v:+.1f}%' if abs(v) < 2 else f'{v:+.0f}%'


def yoy_of(s, pct_series=False, lag=12):
    """照搬 gsx.lvl_bar 的次轴序列：比率序列取百分点差，其余取同比；
    基数过小（< 0.15 x 中位绝对值）或两期异号时同比无意义，留空。"""
    v = np.asarray(s.values, float)
    scale = np.nanmedian(np.abs(v))
    if not np.isfinite(scale) or scale == 0:
        scale = 1.0
    out = np.full(len(v), np.nan)
    for i in range(lag, len(v)):
        a, b = v[i], v[i - lag]
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        if pct_series:
            out[i] = a - b
        elif abs(b) < 0.15 * scale or a * b < 0:
            continue
        else:
            out[i] = (a / b - 1) * 100
    return pd.Series(out, index=s.index)


def mom_of(s):
    v = np.asarray(s.dropna().values, float)
    if len(v) < 2 or v[-2] == 0:
        return np.nan
    return v[-1] / v[-2] - 1


def brk_idx(index, period):
    """断点在窗口里的 x 索引；不在窗口内就不画（同 gsx._draw_break）。"""
    idx = list(index)
    return idx.index(period) if period in idx else None


MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

W25 = df.index[-25:]
W15 = df.index[-15:]
W13 = df.index[-13:]
XL25 = [mlab(p) for p in W25]
XL15 = [mlab(p) for p in W15]
XL13 = [mlab(p) for p in W13]
XL_LONG = [mlab(p) for p in df.index]
XQ = [str(p) for p in q.index]

EX = []


def lvl(n, s, title, *, win=25, fmt='f1', yfmt=None, ylab='', note='', pct_series=False,
        break_at=None, break_label=None, show_mom=False, bar_name='Monthly'):
    """gsx.lvl_bar → bar_line_dual：浅蓝柱（左轴水平值）+ 右轴 y/y 线。"""
    d = s.iloc[-win:]
    ys = yoy_of(s, pct_series=pct_series).iloc[-win:]
    labels = [mlab(p) for p in d.index]
    line_fmt = ('pp1' if pct_series and win <= 15 else 'pp0') if pct_series else 'pct0'
    ex = {
        'n': n, 'kind': 'bar_line_dual', 'title': title,
        'xlabels': labels, 'xstep': 2 if win > 14 else 1,
        'fmt': fmt, 'ylab': ylab,
        'ylab2': 'y/y (pp, RHS)' if pct_series else 'y/y (RHS)',
        'bar': {'name': bar_name, 'color': 'BLUE', 'values': L(d), 'yfmt': yfmt or fmt},
    }
    txt = note
    if show_mom:
        mv = ((d.values[-1] - d.values[-2]) if pct_series else mom_of(s))
        mtxt = (f'{mv:+.1f}pp m/m' if pct_series else pp_txt(mv) + ' m/m')
        txt = (txt + ' ' if txt else '') + f'Latest reading: {mtxt}.'
    if np.isfinite(ys.values).any():
        ex['line'] = {'name': 'y/y (pp, RHS)' if pct_series else 'y/y (RHS)',
                      'color': 'GREEN', 'values': L(ys), 'yfmt': line_fmt}
    else:
        ex.pop('ylab2')
    if txt:
        ex['note'] = txt
    if break_at is not None:
        bi = brk_idx(d.index, break_at)
        if bi is not None:
            ex['break_at'] = bi
            ex['break_label'] = break_label
    EX.append(ex)
    return ex


# ══════════════════════ 客户与资产 ══════════════════════
lvl(2, tpa, 'Total platform assets', win=25, fmt='usd0', ylab='$bn',
    break_at=BRK_WONDERFI, break_label='WonderFi',
    note='Previously reported as Assets Under Custody; renamed and widened to include '
         'TradePMR-advised assets not custodied by Robinhood')

lvl(3, nd, 'Net deposits', win=25, fmt='usd1', ylab='$bn', show_mom=True,
    break_at=BRK_BITSTAMP, break_label='Bitstamp',
    note='m/m shown because net deposits swing far more than y/y can express. '
         'Bitstamp enters from Jun-2025, TradePMR from Mar-2026, WonderFi from Jun-2026.')

lvl(4, df['organic_growth_ann'], 'Annualised organic growth rate', win=25, fmt='pct1',
    ylab='% annualised', pct_series=True,
    note='Monthly net deposits x 12 / prior month-end total platform assets — the same '
         'convention used for Schwab core NNA and LPL organic NNA in this series')

lvl(5, df['funded_customers_mn'], 'Funded customers', win=25, fmt='f1', ylab='mn customers',
    break_at=BRK_WONDERFI, break_label='WonderFi +300k',
    note='Jun-2026 includes about 300k funded customers acquired with WonderFi on '
         '1 Jun 2026 — a stock transfer, not organic acquisition')

_b = df.iloc[-13:]
EX.append({
    'n': 6, 'kind': 'bridge_bar', 'title': 'What moved platform assets: flows vs. markets',
    'xlabels': XL13, 'fmt': 'usd0', 'ylab': '$bn change',
    'stacks': [
        {'name': 'Net deposits', 'color': 'NAVY', 'values': L(_b['net_deposits_usdbn'])},
        {'name': 'Market gains (balancing)', 'color': 'BLUE', 'values': L(_b['market_gains_usdbn'])},
    ],
    'net': {'name': 'Total change in platform assets', 'values': L(_b['tpa_change_usdbn'])},
    'net_color': 'INK',
    'note': 'Identity: opening assets + net deposits + market gains = closing assets. '
            'Market gains is the balancing item, so it also absorbs any acquired assets',
})

# ══════════════════════ 交易量 ══════════════════════
lvl(7, df['adv_equity_usdbn'], 'Equity notional ADV', win=25, fmt='usd1', ylab='$bn / day',
    show_mom=True,
    note='m/m shown: equity volume is running at more than twice last year, so y/y '
         'alone no longer separates months.')

lvl(8, df['adv_options_mn'], 'Options contracts ADV', win=25, fmt='f1',
    ylab='mn contracts / day', show_mom=True)

_c = df.iloc[-15:]
_cshare = (_c['adv_crypto_bitstamp_usdmn'] /
           (_c['adv_crypto_app_usdmn'] + _c['adv_crypto_bitstamp_usdmn']) * 100)
_ex9 = {
    'n': 9, 'kind': 'stacked_dual', 'title': 'Crypto ADV: Robinhood App vs. Bitstamp',
    'xlabels': XL15, 'xstep': 2, 'fmt': 'f0c', 'ylab': '$mn / day',
    'ylab2': '% Bitstamp (RHS)',
    'stacks': [
        {'name': 'Robinhood App', 'color': 'NAVY', 'values': L(_c['adv_crypto_app_usdmn']),
         'label': True, 'label_color': 'WHITE'},
        {'name': 'Bitstamp', 'color': 'BLUE', 'values': L(_c['adv_crypto_bitstamp_usdmn']),
         'label': True, 'label_color': 'NAVY'},
    ],
    'line': {'name': '% Bitstamp (RHS)', 'color': 'GREEN', 'values': L(_cshare),
             'ymax': float(np.ceil(np.nanmax(_cshare.values) / 10.0) * 10)},
    'note': 'Bitstamp is institutional and carries a different take rate from the '
            'retail app, so the mix shift matters for revenue, not just for volume',
}
_bi = brk_idx(_c.index, BRK_BITSTAMP)
if _bi is not None:
    _ex9['break_at'] = _bi
    _ex9['break_label'] = 'Bitstamp acquired'
EX.append(_ex9)

lvl(10, df['adv_event_mn'], 'Event contracts ADV', win=25, fmt='f0',
    ylab='mn contracts / day', show_mom=True,
    note='Prediction Markets Hub. Launched at scale in 2025 — y/y is off a near-zero '
         'base for most of the window, so read the levels and the m/m figure.')

_d = df.iloc[-25:]
EX.append({
    'n': 11, 'kind': 'lines_endlabels', 'title': 'Daily average trades by asset class',
    'xlabels': XL25, 'xstep': 2, 'fmt': 'f1', 'ylab': 'mn trades / day',
    'series': [
        {'name': 'Equity', 'color': 'NAVY', 'values': L(_d['dats_equity_mn'])},
        {'name': 'Options', 'color': 'RED', 'values': L(_d['dats_options_mn'])},
        {'name': 'Crypto', 'color': 'MBLUE', 'values': L(_d['dats_crypto_mn'])},
    ],
    'note': 'Crypto DATs exclude Bitstamp institutional activity; crypto trades every '
            'calendar day while equities and options use exchange trading days',
})

BASE = pd.Period('2023-04', 'M')
_idx = {'Equity notional': df['adv_equity_usdbn'], 'Options contracts': df['adv_options_mn'],
        'Crypto notional': df['adv_crypto_usdmn'], 'Funded customers': df['funded_customers_mn']}
EX.append({
    'n': 12, 'kind': 'lines', 'title': 'Volume vs. customer growth, rebased',
    'xlabels': XL_LONG, 'xstep': 3, 'fmt': 'f0', 'ylab': 'index, base = 100',
    'series': [{'name': k, 'color': c, 'values': L(v / v.loc[BASE] * 100)}
               for (k, v), c in zip(_idx.items(), ['NAVY', 'RED', 'MBLUE', 'GREEN'])],
    'note': f'Rebased to 100 at {mlab(BASE)}, the first month in the published file. '
            'The gap between the volume lines and the customer line is monetisation '
            'per customer, not customer acquisition',
})

# ══════════════════════ 收入桥：先讲费率，再讲检验，最后才给隐含值 ══════════════════════
EX.append({
    'n': 13, 'kind': 'lines', 'markers': True,
    'title': 'Effective take rate by asset class',
    # fmt 用 f1 而不是 f2：charts.js 的 FMT 表里没有 f2，给了会静默回落到 f1
    'xlabels': XQ, 'fmt': 'f1',
    'ylab': 'cents/contract (opt, event) · bp (eq, crypto)',
    'series': [
        {'name': 'Options (c/contract)', 'color': 'NAVY', 'values': L(rate_options_c)},
        {'name': 'Equities (bp)', 'color': 'RED', 'values': L(rate_equities_bp)},
        {'name': 'Crypto (bp)', 'color': 'MBLUE', 'values': L(rate_crypto_bp)},
        {'name': 'Event contracts (c/contract)', 'color': 'GREEN', 'values': L(rate_event_c)},
    ],
    'note': 'Quarterly reported revenue / quarterly volume — derived, not disclosed. '
            'Crypto is the volatile one and it is what makes the revenue bridge miss. '
            'PDF 版用对数轴（四条费率跨 1.1 到 55，线性轴会把股票与事件合约压到零附近）；'
            '网页图表引擎没有对数轴，本图为线性轴，低位两条线请切右上角「表格」视图读逐季数值。',
})

_pi = [p for p in pred.index if p in actual_txn.index][-12:]
_pv = np.array([pred.get(p, np.nan) for p in _pi], float)
_av = np.array([actual_txn.get(p, np.nan) for p in _pi], float)
_err = np.where(_av != 0, (_pv / _av - 1) * 100, np.nan)
_mae = float(np.nanmean(np.abs(_err)))
EX.append({
    'n': 14, 'kind': 'grouped_bars', 'height': 300,
    'title': "Bridge test: last quarter's rate applied to this quarter's volume",
    'xlabels': [str(p) for p in _pi], 'fmt': 'f0c', 'ylab': '$mn per quarter',
    'ylab2': 'Error (%)',
    'groups': [
        {'name': 'Implied by the bridge', 'color': 'BLUE', 'values': L(_pv)},
        {'name': 'Actually reported', 'color': 'NAVY', 'values': L(_av)},
    ],
    'line': {'name': 'Error (RHS)', 'color': 'RED', 'values': L(_err), 'yfmt': 'pct1'},
    'note': "The only non-circular test: the prior quarter's rate applied to this "
            "quarter's actual volumes, versus revenue reported afterwards. Both bars "
            f'cover the same four asset classes. Mean absolute error over the window: {_mae:.1f}%. '
            '双轴图的零点必须落在同一条水平线上，误差线跨零时左轴被迫向下扩，柱子因此'
            '压在画布上半张 —— 与 PDF 观感不同，数值一致。',
})

lvl(15, df['implied_txn_rev_usdmn'], 'Implied transaction revenue', win=25, fmt='usd0',
    ylab='$mn / month',
    note='Assumption: constant take rate within a quarter, back-solved as reported revenue / volume '
         f'({LAST_Q}: options {rate_options_c[LAST_Q]:.0f}c/contract, '
         f'equities {rate_equities_bp[LAST_Q]:.2f}bp, crypto {rate_crypto_bp[LAST_Q]:.1f}bp), '
         'held flat afterwards. Matches its own quarter by construction — Exhibit 14 is the real test.')

_rq = q.iloc[-13:]
_rcols = ['rev_options_usdmn', 'rev_equities_usdmn', 'rev_crypto_usdmn', 'rev_event_usdmn']
_rshare = _rq['rev_event_usdmn'] / _rq[_rcols].sum(axis=1) * 100
EX.append({
    'n': 16, 'kind': 'stacked_dual', 'title': 'Transaction revenue mix by asset class',
    'xlabels': [str(p) for p in _rq.index], 'fmt': 'f0c', 'ylab': '$mn per quarter',
    'ylab2': '% event contracts (RHS)',
    'stacks': [
        {'name': 'Options', 'color': 'NAVY', 'values': L(_rq['rev_options_usdmn']),
         'label': True, 'label_color': 'WHITE'},
        {'name': 'Equities', 'color': 'MBLUE', 'values': L(_rq['rev_equities_usdmn']),
         'label': True, 'label_color': 'WHITE'},
        {'name': 'Crypto', 'color': 'BLUE', 'values': L(_rq['rev_crypto_usdmn']),
         'label': True, 'label_color': 'NAVY'},
        {'name': 'Event contracts', 'color': 'GREEN', 'values': L(_rq['rev_event_usdmn']),
         'label': True, 'label_color': 'WHITE'},
    ],
    'line': {'name': '% event contracts (RHS)', 'color': 'GREEN', 'values': L(_rshare),
             'ymax': float(np.ceil(np.nanmax(_rshare.values) / 5.0) * 5)},
    'note': 'Quarterly actuals, not derived. Event contracts went from nothing to a '
            'fifth of transaction revenue in six quarters — the fastest mix shift in '
            'the business',
})

# ══════════════════════ 生息资产 ══════════════════════
lvl(17, df['margin_book_usdbn'], 'Margin book', win=25, fmt='usd1', ylab='$bn',
    note='Period-end margin loans receivable, including balances from RIAs on the '
         'TradePMR platform')

_ex18 = {
    'n': 18, 'kind': 'lines_endlabels', 'title': 'Cash sweep vs. cash and deposits',
    'xlabels': XL25, 'xstep': 2, 'fmt': 'usd1', 'ylab': '$bn',
    'series': [
        {'name': 'Cash sweep (off balance sheet)', 'color': 'NAVY',
         'values': L(_d['cash_sweep_usdbn'])},
        {'name': 'Cash and deposits', 'color': 'MBLUE',
         'values': L(_d['cash_and_deposits_usdbn'])},
    ],
    'note': 'In Feb-2026 the first $10k of enrolled balances per customer moved to '
            'free credit balances to fund margin lending, shifting over $6bn between '
            'these two lines. The y/y decline in cash sweep after that date is '
            'mechanical, not customer attrition — read the two lines together',
}
_si = brk_idx(_d.index, BRK_SWEEP)
if _si is not None:
    _ex18['break_at'] = _si
    _ex18['break_label'] = 'High-Yield Cash change'
EX.append(_ex18)

EX.append({
    'n': 19, 'kind': 'lines_endlabels', 'title': 'Securities lending revenue',
    'xlabels': XL25, 'xstep': 2, 'fmt': 'usd0', 'ylab': '$mn / month',
    'series': [
        {'name': 'Total securities lending revenue', 'color': 'NAVY',
         'values': L(_d['seclend_total_usdmn'])},
        {'name': 'Securities lending, net', 'color': 'BLUE',
         'values': L(_d['seclend_net_usdmn'])},
    ],
    'note': 'Net excludes interest on cash collateral for margin-based lending, so the '
            'gap between the two lines widens as the margin book grows',
})

lvl(20, df['assets_per_customer_usdk'], 'Assets per funded customer', win=25, fmt='usd1',
    ylab='$k per customer', break_at=BRK_WONDERFI, break_label='WonderFi',
    note='Total platform assets / funded customers. Rises when existing customers '
         'deposit or markets rally, falls when acquisitions bring in customers with '
         'smaller balances')

# ══════════════════════ 长历史 ══════════════════════
EX.append({
    'n': 21, 'kind': 'lines', 'title': 'Total platform assets — full published history',
    'xlabels': XL_LONG, 'xstep': 2, 'fmt': 'usd0', 'ylab': '$bn', 'zero_line': True,
    'series': [{'name': 'Total platform assets', 'color': 'NAVY', 'values': L(tpa)}],
    'note': 'The monthly file publishes a rolling window starting Apr-2023; earlier '
            'months exist only in prior monthly releases and are not carried here',
})

_qs = nd.groupby(nd.index.asfreq('Q')).agg(['sum', 'count'])
_qsum = _qs['sum']
_qyoy = np.array([(_qsum.values[i] / _qsum.values[i - 4] - 1) * 100
                  if i >= 4 and _qsum.values[i - 4] else np.nan for i in range(len(_qsum))])
_nlast = int(_qs['count'].iloc[-1])
_w = _qsum.iloc[-13:]
EX.append({
    'n': 22, 'kind': 'qtr_bar', 'title': 'Net deposits by quarter',
    'xlabels': [str(p) for p in _w.index], 'fmt': 'usd1', 'label_fmt': 'usd1',
    'ylab': '$bn per quarter', 'ylab2': 'y/y (RHS)',
    'legend': 'Complete quarter', 'values': L(_w),
    'partial_months': _nlast, 'qtr_months': 3,
    'line': {'name': 'y/y (RHS)', 'color': 'GREEN',
             'values': L(pd.Series(_qyoy, index=_qsum.index).iloc[-13:]), 'yfmt': 'pct0'},
    'note': 'Quarterly totals remove the month-length and month-end timing noise in the '
            'monthly series'
            + ('' if _nlast >= 3 else
               ' Latest bar is quarter-to-date and not comparable to full quarters.'),
})

_yrs = sorted({p.year for p in nd.index})[-4:]
_ylines = []
for _y in _yrs:
    sub = nd[[p.year == _y for p in nd.index]].cumsum()
    vals = [None] * 12
    for p, v in sub.items():
        vals[p.month - 1] = round(float(v), 6)
    _ylines.append({'name': str(_y), 'values': vals})
EX.append({
    'n': 23, 'kind': 'year_lines', 'title': 'Net deposits path by year',
    'xlabels': MON, 'fmt': 'usd0', 'label_fmt': 'usd0', 'ylab': '$bn cumulative',
    'series': _ylines, 'highlight': len(_ylines) - 1,
    'note': 'Cumulative within each calendar year. The 2023 line starts in April '
            'because that is where the published file begins — it is not a weak year, '
            'it is a short one, and is not comparable with the full years',
})

lvl(24, df['crypto_bitstamp_share'], 'Bitstamp share of crypto volume', win=15, fmt='pct0',
    ylab='% of crypto ADV', pct_series=True,
    break_at=BRK_BITSTAMP, break_label='Bitstamp acquired',
    note='Institutional crypto now runs above half of total crypto volume but earns a '
         'far lower take rate than the retail app, which is why crypto revenue has '
         'not followed crypto volume')

_dq = df['dats_total_mn'].groupby(df.index.asfreq('Q')).agg(['mean', 'count'])
_dmean = _dq['mean']
_dyoy = np.array([(_dmean.values[i] / _dmean.values[i - 4] - 1) * 100
                  if i >= 4 and _dmean.values[i - 4] else np.nan for i in range(len(_dmean))])
_dlast = int(_dq['count'].iloc[-1])
_wd = _dmean.iloc[-13:]
EX.append({
    'n': 25, 'kind': 'qtr_bar', 'title': 'Total daily average trades by quarter',
    'xlabels': [str(p) for p in _wd.index], 'fmt': 'f1', 'label_fmt': 'f1',
    'ylab': 'mn trades / day', 'ylab2': 'y/y (RHS)',
    'legend': 'Complete quarter', 'values': L(_wd),
    'partial_months': _dlast, 'qtr_months': 3,
    'line': {'name': 'y/y (RHS)', 'color': 'GREEN',
             'values': L(pd.Series(_dyoy, index=_dmean.index).iloc[-13:]), 'yfmt': 'pct0'},
    'note': 'Quarterly average of the three asset classes; removes the month-length '
            'differences between equity trading days and crypto calendar days'
            + ('' if _dlast >= 3 else
               ' Latest bar is quarter-to-date and not comparable to full quarters.'),
})


def heat(n, s, title, note, legend, n_years=4, fmt='f0'):
    ss = s.dropna()
    yrs = sorted({p.year for p in ss.index})[-n_years:]
    M = [[None] * 12 for _ in yrs]
    for p, v in ss.items():
        if p.year in yrs and np.isfinite(v):
            M[yrs.index(p.year)][p.month - 1] = round(float(v), 6)
    EX.append({
        'n': n, 'kind': 'heat_matrix', 'title': title,
        'rows': [str(y) for y in yrs], 'cols': MON, 'matrix': M,
        'fmt': fmt, 'legend': legend, 'row_head': '年', 'cell_h': 20, 'note': note,
    })


heat(26, df['organic_growth_ann'], 'Annualised organic growth rate (%)',
     'Green = faster organic growth. Colour scale runs on the 5–95 percentile of all '
     'finite cells, so one outlier month does not flatten the table.',
     'Annualised organic growth (%)')
heat(27, df['adv_equity_usdbn'].pct_change(12) * 100, 'Equity notional ADV y/y (%)',
     'Green = faster growth. The first 12 months of the published file have no prior-year '
     'comparison, so 2024 starts in April.', 'Equity notional ADV y/y (%)')


# ────────────────────────── Exhibit 1：汇总表 ──────────────────────────
CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12


def pctile36(ss):
    """近 36 个月分位。几乎只增不减的序列分位恒为 ~100，是噪音不是信息 → 留空。"""
    hist = ss.iloc[-36:]
    c = ss.iloc[-1]
    if len(hist) < 8 or not np.isfinite(c):
        return None
    d = np.diff(hist.values)
    if len(d) and float((d >= 0).sum()) / len(d) >= 0.90:
        return None
    return float((hist.values < c).sum()) / max(1, len(hist) - 1) * 100


def chg_cell(a, b, mode, inv):
    if not (np.isfinite(a) and np.isfinite(b)):
        return {'v': '—'}
    if mode == 'pp':
        v = a - b
        txt = f'{v * 100:+.0f}bp' if abs(v) < 1 else f'{v:+.2f}pp'
    else:
        if b == 0 or a * b < 0:
            return {'v': '—'}
        v = (a / b - 1) * 100
        txt = f'{v:+.1f}%'
    good = (v < 0) if inv else (v > 0)
    return {'v': txt, 'cls': 'pos' if good else 'neg'}


SUM = [
    ('g', 'Customers and assets'),
    ('r', 'Total platform assets ($bn)', tpa, 0, '$', False),
    ('r', 'Net deposits ($bn)', nd, 1, '$', False),
    ('r', 'Annualised organic growth (%)', df['organic_growth_ann'], 1, '', True),
    ('r', 'Funded customers (mn)', df['funded_customers_mn'], 1, '', False),
    ('r', 'Assets per funded customer ($k)', df['assets_per_customer_usdk'], 1, '$', False),
    ('g', 'Trading — average daily volumes'),
    ('r', 'Equity notional ($bn/day)', df['adv_equity_usdbn'], 1, '$', False),
    ('r', 'Options contracts (mn/day)', df['adv_options_mn'], 1, '', False),
    ('r', 'Crypto notional ($mn/day)', df['adv_crypto_usdmn'], 0, '$', False),
    ('r', '&nbsp;&nbsp;of which Bitstamp ($mn/day)', df['adv_crypto_bitstamp_usdmn'], 0, '$', False),
    ('r', 'Event contracts (mn/day)', df['adv_event_mn'], 0, '', False),
    ('r', 'Total DATs (mn/day)', df['dats_total_mn'], 1, '', False),
    ('g', 'Interest-earning assets ($bn)'),
    ('r', 'Margin book', df['margin_book_usdbn'], 1, '$', False),
    ('r', 'Cash sweep', df['cash_sweep_usdbn'], 1, '$', False),
    ('r', 'Cash and deposits', df['cash_and_deposits_usdbn'], 1, '$', False),
    ('r', 'Securities lending revenue ($mn)', df['seclend_total_usdmn'], 0, '$', False),
]

srows = []
for item in SUM:
    if item[0] == 'g':
        srows.append({'kind': 'group', 'label': item[1]})
        continue
    _, lab, s, dec, money, pct = item
    ss = s.dropna()
    mode = 'pp' if pct else 'ratio'
    c = float(ss.get(CUR, np.nan)) if CUR in ss.index else np.nan
    p1 = float(ss.get(PRV, np.nan)) if PRV in ss.index else np.nan
    p12 = float(ss.get(YAG, np.nan)) if YAG in ss.index else np.nan
    pt = pctile36(ss)
    if pt is None:
        pcell = {'v': ''}
    else:
        pcell = {'v': f'{pt:.0f}',
                 'cls': 'hi' if pt >= 66 else ('lo' if pt <= 33 else '')}
    srows.append({'label': lab, 'cells': [
        {'v': fnum(c, dec, money, pct), 'cls': 'cur'},
        {'v': fnum(p1, dec, money, pct)},
        {'v': fnum(p12, dec, money, pct)},
        chg_cell(c, p1, mode, False),
        chg_cell(c, p12, mode, False),
        pcell,
    ]})

summary = {
    'title': f'Robinhood monthly metrics — {mlab(LATEST)}',
    'heads': [mlab(CUR), mlab(PRV), mlab(YAG), 'm/m', 'y/y', '3Y %ile'],
    'sep': 3,
    'rows': srows,
    'note': 'Three official basis changes sit inside this window and are marked on the charts: '
            'Bitstamp enters net deposits and crypto volume from Jun-2025; the High-Yield Cash '
            'programme moved over $6bn from cash sweep to cash and deposits in Feb-2026; '
            'WonderFi adds about 300k funded customers from Jun-2026. y/y for those rows is '
            'not like-for-like. 3Y %ile = 当月读数在近 36 个月里高于多少百分比的观测；'
            '几乎只增不减的序列（分位恒为 ~100，零信息量）留空。比率行的差异用 pp / bp，不用百分比变化。',
}

# ────────────────────────── 核对表（官方原始单位，未换算）──────────────────────────
TCOLS = [
    ('Funded customers (mn)', 'fc', 'funded_customers_mn', 1),
    ('Total platform assets ($bn)', 'tpa', 'total_platform_assets_usdbn', 1),
    ('Net deposits ($bn)', 'nd', 'net_deposits_usdbn', 1),
    ('Equity notional ADV ($bn)', 'aeq', 'adv_equity_usdbn', 1),
    ('Options ADV (mn contracts)', 'aop', 'adv_options_mn', 1),
    ('Crypto ADV ($mn)', 'acr', 'adv_crypto_usdmn', 0),
    ('of which Bitstamp ($mn)', 'abs', 'adv_crypto_bitstamp_usdmn', 0),
    ('Event contracts ADV (mn)', 'aev', 'adv_event_mn', 0),
    ('Equity DATs (mn)', 'deq', 'dats_equity_mn', 1),
    ('Options DATs (mn)', 'dop', 'dats_options_mn', 1),
    ('Crypto DATs (mn)', 'dcr', 'dats_crypto_mn', 1),
    ('Margin book ($bn)', 'mb', 'margin_book_usdbn', 1),
    ('Cash sweep ($bn)', 'cs', 'cash_sweep_usdbn', 1),
    ('Cash and deposits ($bn)', 'cd', 'cash_and_deposits_usdbn', 1),
    ('Sec. lending revenue ($mn)', 'sl', 'seclend_total_usdmn', 0),
    ('Eq/opt trading days', 'td', 'eqopt_trading_days', 1),
]
trows = []
for p in W13:
    row = {'xl': mlab(p)}
    for _h, key, col, dec in TCOLS:
        v = df[col].get(p, np.nan)
        row[key] = None if not np.isfinite(v) else f'{float(v):,.{dec}f}'
    trows.append(row)

table = {
    'n': 28, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）', 'idx': '月份',
    'cols': [[h, k] for h, k, _c, _d in TCOLS], 'rows': trows,
}

# ────────────────────────── 口径与方法说明 ──────────────────────────
notes = [
    '<b>数据源（唯一）</b>：investors.robinhood.com → Monthly Metrics 的 Excel。HOOD 的月度数据'
    '按 Reg FD 挂在 IR 网站上，<b>不走 8-K</b>，盯 EDGAR 抓不到；季度收入与季度成交量取自同一个'
    ' Excel 的 Quarterly GAAP P&amp;L 页。本页读的是仓库里的 <code>series/hood.csv</code> 与'
    ' <code>series/hood_q.csv</code>。',

    '<b>版式出处</b>：Goldman Sachs「Robinhood Markets Inc. (HOOD): Monthly」（James Yaro 团队）。'
    '本报告对 GS 版本做了三处改动：(1) GS 每张图挂的 "Prior 12mo Avg." 虚线与汇总表的 12M Avg. 列'
    '全部换成 y/y —— 滚动均值只是把序列再平滑一遍，不回答「相对去年同月是好是坏」；'
    '(2) GS 把「水平值」与「环比」拆成两张图，这里合并成「柱 + 右轴 y/y 线」；'
    '(3) GS 的佣金收入用的是 GSe 季度费率 x 当月成交量（未经验证的第三方估计），'
    '本报告改用<b>公司自己披露的季度收入</b>反解费率，并加了 GS 没有的样本外检验（Exhibit 14）。',

    '⚠️ <b>窗口内有三个官方口径断点，图上均以红色虚线标出，虚线右侧与左侧不可直读</b>：'
    'Bitstamp 自 <b>2025-06</b> 并入净流入、加密成交量与客户数；High-Yield Cash 改版于'
    ' <b>2026-02</b> 把逾 $6bn 从 Cash sweep 挪到 Cash and deposits；WonderFi 于 <b>2026-06</b>'
    '带进约 30 万 funded customers（股权交易，不是自然获客）。这三行的 y/y 不是 like-for-like。',

    '<b>费率是反解值，不是披露值</b>：季度披露收入 ÷ 同季披露成交量。量纲换算——$1bn 名义额产生'
    ' r 个 $mn，即 r/1000 的费率 = r x 10 bp；$mn/mn 张 = $/张，x100 得美分/张。'
    '因此「隐含收入 vs 同季实际收入」必然完全吻合，是循环论证、没有信息量；'
    '<b>唯一有信息量的检验是 Exhibit 14</b>：拿上一季的费率去预测本季收入，再与事后披露的实际值对照。',

    '<b>Exhibit 14 的口径对齐</b>：某一类若上季没有可用费率（业务还没起量、或成交量四舍五入成 0.0），'
    '该类同时从预测和实际里剔除，保证两根柱子覆盖同样的资产类别 —— 否则预测缺一块、实际多一块，'
    '算出来的误差是假的。',

    '<b>Exhibit 15（Implied transaction revenue）是推导值，不是公司披露值</b>：假设季度内费率恒定，'
    '最新季之后沿用最后一个已知费率；某类业务在其起量之前的贡献视为 0（整行全空才留空）。',

    '<b>年化有机增速</b> = 当月净流入 x 12 / 上月末总平台资产 —— 与本系列里 Schwab core NNA、'
    'LPL organic NNA 用的是同一套约定。<b>市值变动</b>是恒等式残差（期末 − 期初 − 净流入），'
    '因此也吸收并购带进来的资产，不能当成纯市场回报读。',

    '<b>交易日口径不一</b>：股票与期权按交易所交易日折算 ADV/DATs，加密按自然日；'
    'Crypto DATs 不含 Bitstamp 的机构交易，而 Crypto ADV 含。季度图（Exhibit 22 / 25）正是为了'
    '抹掉月长与月末时点差异而做的。',

    '<b>Total platform assets 曾名 Assets Under Custody</b>，改名后口径扩大到包含 TradePMR 顾问的'
    '资产（这部分并不由 Robinhood 托管）。Exhibit 21 的全历史只到 2023-04 —— 月度文件发布的是'
    '滚动窗口，更早的月份只存在于历史新闻稿里，本站不做拼接。',

    '<b>所有数值与格式化都在 Python 侧完成</b>，页面只负责排版：同一个数字在两种语言里各算一遍，'
    '迟早会出现图上与表里对不上而没人发现。每张卡右上角的「表格」是与图同源的数值，'
    '比坐标轴多给一位小数，可直接与公司披露逐条核对。',
]

# ────────────────────────── payload ──────────────────────────
_tpa_yoy = float(tpa.iloc[-1] / tpa.iloc[-13] - 1)
_nd_mom = mom_of(nd)
_og = float(df['organic_growth_ann'].iloc[-1])
_eq_yoy = float(df['adv_equity_usdbn'].iloc[-1] / df['adv_equity_usdbn'].iloc[-13] - 1)
_fc = float(df['funded_customers_mn'].iloc[-1])

headline = (
    f'总平台资产 ${tpa.iloc[-1]:,.0f}bn（{pp_txt(_tpa_yoy)} y/y） · '
    f'净流入 ${nd.iloc[-1]:,.1f}bn（{pp_txt(_nd_mom)} m/m，年化有机增速 {_og:.1f}%） · '
    f'股票名义 ADV ${df["adv_equity_usdbn"].iloc[-1]:,.1f}bn/日（{pp_txt(_eq_yoy)} y/y） · '
    f'期权 ADV {df["adv_options_mn"].iloc[-1]:,.1f}mn 张/日 · '
    f'事件合约 ADV {df["adv_event_mn"].iloc[-1]:,.0f}mn 张/日 · '
    f'融资余额 ${df["margin_book_usdbn"].iloc[-1]:,.1f}bn · '
    f'入金客户 {_fc:,.1f}mn'
)

payload = {
    'ticker': 'hood',
    'tracker': 'HOOD Monthly Operating Metrics',
    'title': f'Robinhood Markets (HOOD)：月度经营指标 — {LATEST.year} 年 {LATEST.month} 月',
    'data_through': str(LATEST),
    'through_label': f'{LATEST.year} 年 {LATEST.month} 月',
    'subtitle': f'数据源：Robinhood 月度经营指标（IR 网站，Reg FD 披露）+ 季度 GAAP P&L · '
                f'覆盖 {mlab(df.index[0])} – {mlab(LATEST)}（{len(df)} 个月）与 '
                f'{q.index[0]} – {LAST_Q}（{len(q)} 个季度） · '
                f'版式沿用 Goldman Sachs GIR「HOOD Monthly」，含 GS 版没有的收入桥样本外检验',
    'headline': headline,
    'hub_line': f'总平台资产 ${tpa.iloc[-1]:,.0f}bn（{pp_txt(_tpa_yoy)} y/y）·'
                f'净流入 ${nd.iloc[-1]:,.1f}bn · 入金客户 {_fc:,.1f}mn',
    'source': SRC,
    'xlabels': XL25,
    'xlabels_long': XL_LONG,
    'summary': summary,
    'exhibits': EX,
    'table': table,
    'notes': notes,
    'footer': '仅供个人研究，不构成投资建议 · 数值全部来自 Robinhood 官方月度指标与季度报告，'
              '推导值（费率、隐含收入、有机增速、市值变动）已在图注中标明假设',
}

out = os.path.join(ROOT, 'data', 'hood.js')
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, 'w', encoding='utf-8') as f:
    # 构建日期只写首行注释，不进 payload —— 进了 payload，monthly_run 的
    # 「data 有没有实质变化」检查（忽略首行的正文比较）就永久失效。
    f.write(f'// 由 build/hood.py 生成于 {datetime.date.today().isoformat()}，请勿手改\n')
    f.write('window.DASH = ')
    json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    f.write(';\n')

print(f'月度窗口 {df.index[0]} → {LATEST}（{len(df)} 个月）| 季度 {q.index[0]} → {LAST_Q}（{len(q)} 个季度）')
print(f'Exhibit 1 汇总表 + Exhibit {EX[0]["n"]}-{EX[-1]["n"]}（{len(EX)} 张）+ Exhibit {table["n"]} 核对表')
print(f'Exhibit 14 窗口内平均绝对误差 {_mae:.1f}%')
print(f'写出 {out}  ({os.path.getsize(out) / 1024:.1f} KB)')
print(headline)
