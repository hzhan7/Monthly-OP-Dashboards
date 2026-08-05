# -*- coding: utf-8 -*-
"""American Express (AXP) 月度信贷经营指标 —— 网页看板数据生成器。

把 build/build_axp.py（matplotlib / JPM「Managed Data Release」版式 PDF）里的每一张
exhibit 逐张移植成 payload 对象，写出 data/axp.js。图的顺序、编号、标题文案、图注、
窗口长度、口径断点全部照搬原 deck；数值一律在本文件算好并格式化成字符串，页面不做计算。

⚠️ 口径断点：AXP 自 2026 年 5 月起把 Card Member loans 与 receivables 合并披露为
   "Card balances"（含 pay-in-full 余额），并在 2026-05-15 的 8-K Exhibit 99.1 里
   重述了 24 个月历史。两套口径不可直接连比。PDF 分两页呈现，网页版没有分页概念，
   改用标题里的板块小标题 + Exhibit 分组表达：
     【新口径 · Card balances】  Exhibit 2-7    2024-05 起（重述历史 + 最新申报）
     【Lending Trust · 10-D】    Exhibit 8-11   2023-07 起（与 8-K 同日报送）
     【旧口径 · loans only】     Exhibit 12-18  2016-01 → 2026-03，只用于长历史与季节性

数据源（只读 series/*.csv，不碰 build/data/）：
    series/axp_newbasis.csv          新合并口径月度信贷指标
    series/axp_8k_card_balances.csv  8-K 原表（含平均余额与 total HFI）
    series/axp_trust.csv             Master Trust 月度 10-D 摘要
    series/axp_trust_full.csv        10-D 全字段（只取 filing_date 当发布日）
    series/axp.csv                   旧 loans-only 口径长历史
    series/fee_rates.csv             季度 net interest yield（新口径）

用法：python3 build/axp.py
"""
import datetime
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# ── 原 deck 逐字照搬的口径文案 ──
SRC_N = 'AXP 8-K Item 7.01, combined Card balances basis; format after J.P. Morgan'
SRC_O = 'AXP 8-K Item 7.01, Card Member loans basis; format after J.P. Morgan'
BASIS_N = 'Combined Card balances basis (loans + receivables), effective May-2026'
BASIS_O = 'Card Member loans only (pre-2026 basis) — not comparable to the new-basis exhibits above'
JUN_NOTE = ('Jun-26 write-off rate cut ~0.3pp (Consumer) / ~0.1pp (SBS) by a sale of '
            'written-off balances')
TRUST_SRC = ('American Express Credit Account Master Trust monthly Form 10-D '
             '(SEC CIK 0001003509)')
TRUST_NOTE = 'Trust pool = revolve-eligible balances only, so its rates sit below the 8-K rates'

SEC_A = '【新口径 · Card balances】'
SEC_T = '【Lending Trust · Form 10-D】'
SEC_O = '【旧口径 · Card Member loans only】'


# ────────────────────────────── 读数 ──────────────────────────────
def load(name):
    d = pd.read_csv(os.path.join(SERIES, name))
    d['month'] = pd.PeriodIndex(d['month'], freq='M')
    return d.set_index('month').sort_index()


def need(df, cols, who):
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise SystemExit(f'{who} 缺列 {miss} —— 拒绝静默出图')


new = load('axp_newbasis.csv')
avgbal = load('axp_8k_card_balances.csv')
trust = load('axp_trust.csv')
old = load('axp.csv').loc[:pd.Period('2026-03', 'M')]

need(new, ['consumer_balance_usdbn', 'consumer_dq30_pct', 'consumer_nco_pct',
           'sbs_balance_usdbn', 'sbs_dq30_pct', 'sbs_nco_pct'], 'axp_newbasis.csv')
need(avgbal, ['consumer_avg_bal_usdbn', 'smb_avg_bal_usdbn', 'total_hfi_usdbn'],
     'axp_8k_card_balances.csv')
need(trust, ['payment_rate_pct', 'portfolio_yield_pct', 'excess_spread_pct',
             'principal_receivables_usdbn', 'dq30_pct', 'nco_pct'], 'axp_trust.csv')
need(old, ['consumer_balance_usdbn', 'consumer_nco_pct', 'consumer_dq30_pct',
           'sbs_nco_pct'], 'axp.csv')

# 季度 net interest yield（新口径）→ 月度：当季各月用该季值，最新季之后沿用
_rates = pd.read_csv(os.path.join(SERIES, 'fee_rates.csv'))
_r = _rates[(_rates['company'] == 'AXP') & (_rates['metric'] == 'net_interest_yield_newbasis')]
if not len(_r):
    raise SystemExit('fee_rates.csv 里没有 AXP/net_interest_yield_newbasis')
_niy = (_r.assign(q=pd.PeriodIndex(_r['period'].str.replace('-', ''), freq='Q'))
          .set_index('q')['value'].astype(float).sort_index())
_q = pd.PeriodIndex(avgbal.index).asfreq('Q')
avgbal['niy'] = pd.Series([_niy.get(qq, np.nan) for qq in _q],
                          index=avgbal.index, dtype=float).ffill()
avgbal['us_avg_bal'] = avgbal['consumer_avg_bal_usdbn'] + avgbal['smb_avg_bal_usdbn']
avgbal['implied_nii_usdmn'] = avgbal['us_avg_bal'] * 1000.0 * avgbal['niy'] / 100.0 / 12.0

NII_NOTE = ('Assumption: monthly NII = average U.S. Consumer + Small Business card balances '
            f'x the disclosed net interest yield / 12 ({_niy.index[-1]} = {_niy.iloc[-1]:.1f}%, '
            'held flat after). The yield is company-wide but the balances are U.S. card only.')

trust = trust.join(new[['consumer_nco_pct', 'consumer_dq30_pct']], how='left')

new['total_balance'] = new['consumer_balance_usdbn'] + new['sbs_balance_usdbn']
old['total_balance'] = old['consumer_balance_usdbn'] + old['sbs_balance_usdbn']

LATEST = new.index[-1]
if trust.index[-1] != LATEST:
    raise SystemExit(f'8-K 最新月 {LATEST} 与 Trust 最新月 {trust.index[-1]} 不一致')
if old.index[-1] != pd.Period('2026-03', 'M'):
    raise SystemExit(f'旧口径序列末月应为 2026-03，实际 {old.index[-1]}')

# 逐月连续性护栏：断档会让 y/y 与同月均值整体错位
for df, who in ((new, 'axp_newbasis.csv'), (trust, 'axp_trust.csv'), (old, 'axp.csv')):
    d = np.diff(np.array([p.ordinal for p in df.index]))
    if len(d) and (d != 1).any():
        raise SystemExit(f'{who} 月份不连续')

# 发布日：10-D 的 filing_date（8-K 与 10-D 近 31 期 31/31 同日报送）
_tf = pd.read_csv(os.path.join(SERIES, 'axp_trust_full.csv'))
_tf['month'] = pd.PeriodIndex(_tf['month'], freq='M')
_fd = _tf.set_index('month')['filing_date']
SOURCE_DATE = str(_fd.get(LATEST, '')) or None


# ────────────────────────────── 小工具 ──────────────────────────────
def mlab(p):
    return p.strftime('%b-%y')


def xl(idx):
    return [mlab(p) for p in idx]


def L(a):
    """序列 → JSON 数组，NaN 写 null（缺口不连线，规矩 3）。"""
    return [None if v is None or not np.isfinite(float(v)) else round(float(v), 6) for v in a]


def lvl_yoy(s, pct_series=False):
    """照抄 gsx.lvl_bar 的次轴同比：比率序列取百分点差；水平值取百分比变化，
    但基数过小（< 0.15 x 中位绝对值）或两期异号时留空 —— 那种同比没有意义。"""
    v = np.asarray(s.values, dtype=float)
    scale = float(np.nanmedian(np.abs(v))) or 1.0
    out = np.full(len(v), np.nan)
    for i in range(12, len(v)):
        a, b = v[i], v[i - 12]
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        if pct_series:
            out[i] = a - b
        elif abs(b) < 0.15 * scale or a * b < 0:
            continue
        else:
            out[i] = (a / b - 1) * 100.0
    return pd.Series(out, index=s.index)


def plain_yoy(s):
    """照抄 gsx.rev_bar_yoy 用的 _yoy：不做基数保护，只要两期都在就算。"""
    v = np.asarray(s.values, dtype=float)
    out = np.full(len(v), np.nan)
    for i in range(12, len(v)):
        a, b = v[i], v[i - 12]
        if np.isfinite(a) and np.isfinite(b) and b != 0:
            out[i] = (a / b - 1) * 100.0
    return pd.Series(out, index=s.index)


def tail_contiguous(s):
    """gsx._tail_contiguous：先 dropna，再只留末尾逐月连续的一段。"""
    s = s.dropna()
    if len(s) < 3:
        return s
    idx = list(s.index)
    gaps = [(idx[i] - idx[i - 1]).n for i in range(1, len(idx))]
    stride = max(set(gaps), key=gaps.count)
    start = 0
    for i in range(len(idx) - 1, 0, -1):
        if (idx[i] - idx[i - 1]).n != stride:
            start = i
            break
    return s.iloc[start:]


def bar_yoy_ex(n, ttl, s_full, *, win, yfmt, ylab, pct_series=False,
               bar_color='BLUE', bar_name='Monthly', note=None, src_extra=None,
               xstep=None):
    """gsx.lvl_bar / gsx.rev_bar_yoy → 网页 bar_line_dual（柱 + 右轴 y/y 线）。"""
    s = tail_contiguous(s_full)
    y = (lvl_yoy(s, pct_series) if bar_color == 'BLUE' else plain_yoy(s)).iloc[-win:]
    d = s.iloc[-win:]
    ex = {
        'n': n, 'kind': 'bar_line_dual', 'title': ttl,
        'xlabels': xl(d.index), 'xrot': 90,
        'ylab': ylab, 'ylab2': ('y/y (pp)' if pct_series else 'y/y (%)'),
        'bar': {'name': bar_name, 'color': bar_color, 'values': L(d.values), 'yfmt': yfmt},
        'line': {'name': ('y/y (pp, RHS)' if pct_series else 'y/y (RHS)'), 'color': 'GREEN',
                 'values': L(y.values), 'yfmt': ('pp1' if pct_series else 'pct0')},
    }
    if xstep:
        ex['xstep'] = xstep
    if note:
        ex['note'] = note
    if src_extra:
        ex['src_extra'] = src_extra
    return ex


def multi_line_ex(n, ttl, df, cols, colors, names, *, win, src_extra=None, note=None):
    """gsx.multi_line → 网页 lines_endlabels（多条平滑线，仅两端标数值）。"""
    d = df.iloc[-win:]
    ex = {
        'n': n, 'kind': 'lines_endlabels', 'title': ttl, 'fmt': 'pct1', 'yfmt': 'pct1',
        'xlabels': xl(d.index), 'xrot': 90, 'ylab': '%',
        'series': [{'name': nm, 'color': c, 'values': L(d[col].values)}
                   for col, c, nm in zip(cols, colors, names)],
    }
    if note:
        ex['note'] = note
    if src_extra:
        ex['src_extra'] = src_extra
    return ex


def seasonality_ex(n, ttl, s_full, *, win, years, src_extra=None):
    """gsx.seasonality → 网页 seasonality（灰=过去 N 年同月均值，蓝=实际）。"""
    s = s_full.dropna()
    d = s.iloc[-win:]
    base, used = [], []
    for p in d.index:
        prior = [s.get(p - 12 * k, np.nan) for k in range(1, years + 1)]
        prior = [v for v in prior if v is not None and np.isfinite(v)]
        used.append(len(prior))
        base.append(float(np.mean(prior)) if prior else np.nan)
    ex = {
        'n': n, 'kind': 'seasonality', 'title': ttl, 'fmt': 'pct1', 'label_fmt': 'pct1',
        'yfmt': 'pct1', 'xlabels': xl(d.index), 'xrot': 90, 'ylab': '%',
        'base': {'name': f'Prior {max(used)}yr same-month avg.', 'color': 'GRAY',
                 'values': L(base)},
        'actual': {'name': 'Actual', 'color': 'MBLUE', 'values': L(d.values)},
    }
    if src_extra:
        ex['src_extra'] = src_extra
    return ex, max(used)


def year_lines_ex(n, ttl, s_full, *, n_years, src_extra=None):
    """gsx.year_lines（cumulative=False）→ 网页 year_lines。"""
    s = s_full.dropna()
    yrs = sorted({p.year for p in s.index})[-n_years:]
    series = []
    for y in yrs:
        vals = [np.nan] * 12
        for p, v in s.items():
            if p.year == y:
                vals[p.month - 1] = v
        series.append({'name': str(y), 'values': L(vals)})
    return {
        'n': n, 'kind': 'year_lines', 'title': ttl, 'fmt': 'pct1', 'label_fmt': 'pct1',
        'yfmt': 'pct1', 'xlabels': MONTHS, 'ylab': '%', 'series': series,
        'highlight': len(series) - 1,
        'src_extra': src_extra,
    }


def heat_ex(n, ttl, s_full, *, n_years, src_extra=None):
    """gsx.heat_matrix（reverse=True：低核销率=绿）→ 网页 heat_matrix。"""
    s = s_full.dropna()
    yrs = sorted({p.year for p in s.index})[-n_years:]
    m = [[None] * 12 for _ in yrs]
    for p, v in s.items():
        if p.year in yrs:
            m[yrs.index(p.year)][p.month - 1] = round(float(v), 6)
    return {
        'n': n, 'kind': 'heat_matrix', 'title': ttl, 'fmt': 'f1', 'reverse': True,
        'rows': [str(y) for y in yrs], 'cols': MONTHS, 'matrix': m,
        'row_head': '年', 'legend': ttl.split('】')[-1], 'cell_h': 19,
        'src_extra': src_extra,
    }


# ────────────────────────────── Exhibit 1：汇总表 ──────────────────────────────
CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12


def fmt_val(v, dec, pct, money):
    if v is None or not np.isfinite(v):
        return '—'
    return f'{money}{v:,.{dec}f}' + ('%' if pct else '')


def fmt_chg(a, b, mode, dec, money):
    """gsx.summary_table 的变化率口径：比率类一律 pp/bp，|差| < 1 用 bp。"""
    if not (np.isfinite(a) and np.isfinite(b)):
        return None
    if mode == 'pp':
        v = a - b
        return f'{v * 100:+.0f}bp' if abs(v) < 1 else f'{v:+.2f}pp'
    if mode == 'abs':
        return money + f'{a - b:+,.{max(0, dec)}f}'
    if b == 0 or a * b < 0:
        return None
    return f'{(a / b - 1) * 100:+.1f}%'


def chg_good(a, b, mode, inv):
    """返回 True=好 / False=坏 / None=不着色。
    gsx 把「零变化」着成红色（good = v > 0 为假），那是在说「没变 = 变坏」，
    这里改成中性 —— 口径判断在 Python 侧做完，页面不猜。"""
    if not (np.isfinite(a) and np.isfinite(b)):
        return None
    v = (a - b) if mode in ('pp', 'abs') else ((a / b - 1) if b and a * b > 0 else np.nan)
    if not np.isfinite(v) or v == 0:
        return None
    return (v < 0) if inv else (v > 0)


def pctile36(s, c):
    """近 36 个月分位。CONTRACT §2：几乎只增不减的序列分位恒为 100，是噪音不是信息，
    diff >= 0 的比例 >= 90% 就留空。"""
    hist = s.iloc[-36:]
    if not np.isfinite(c) or len(hist) < 8:
        return None
    d = np.diff(np.asarray(hist.values, dtype=float))
    d = d[np.isfinite(d)]
    if len(d) and float((d >= 0).sum()) / len(d) >= 0.90:
        return None
    return float((hist < c).sum()) / max(1, len(hist) - 1) * 100.0


SUM_ROWS = [
    ('U.S. Consumer Card', None, None, None, None, None, None),
    (new, 'Total Card balances ($bn)', 'consumer_balance_usdbn', 1, False, '$', False),
    (new, '30+ days past due (%)', 'consumer_dq30_pct', 2, True, '', True),
    (new, 'Net write-off rate, principal (%)', 'consumer_nco_pct', 2, True, '', True),
    ('U.S. Small Business Card', None, None, None, None, None, None),
    (new, 'Total Card balances ($bn)', 'sbs_balance_usdbn', 1, False, '$', False),
    (new, '30+ days past due (%)', 'sbs_dq30_pct', 2, True, '', True),
    (new, 'Net write-off rate, principal (%)', 'sbs_nco_pct', 2, True, '', True),
    ('Combined', None, None, None, None, None, None),
    (new, 'Card balances held for investment ($bn)', 'total_balance', 1, False, '$', False),
    ('Trust performance (%, monthly)', None, None, None, None, None, None),
    (trust, 'Portfolio yield', 'portfolio_yield_pct', 2, True, '', False),
    (trust, 'Payment rate', 'payment_rate_pct', 2, True, '', False),
    (trust, 'Excess spread', 'excess_spread_pct', 2, True, '', False),
    (trust, 'Annualised default rate, net of recoveries', 'nco_pct', 2, True, '', True),
    (trust, 'Total 30+ day delinquency', 'dq30_pct', 2, True, '', True),
    ('Pool size', None, None, None, None, None, None),
    (trust, 'Principal receivables ($bn)', 'principal_receivables_usdbn', 2, False, '$', False),
]

srows = []
for src_df, lab, col, dec, pct, money, inv in SUM_ROWS:
    if lab is None:
        srows.append({'kind': 'group', 'label': src_df})
        continue
    s = src_df[col].dropna()
    g = lambda p: (float(s.get(p, np.nan)) if p in s.index else np.nan)
    c, p1, p12 = g(CUR), g(PRV), g(YAG)
    mode = 'pp' if pct else 'ratio'
    cells = [{'v': fmt_val(c, dec, pct, money), 'cls': 'cur'},
             {'v': fmt_val(p1, dec, pct, money)},
             {'v': fmt_val(p12, dec, pct, money)}]
    for b in (p1, p12):
        t = fmt_chg(c, b, mode, dec, money)
        good = chg_good(c, b, mode, inv)
        cells.append({'v': t or '', 'cls': ('' if good is None else ('pos' if good else 'neg'))})
    pv = pctile36(s, c)
    if pv is None:
        cells.append({'v': ''})
    else:
        shown = (100 - pv) if inv else pv
        cells.append({'v': f'{pv:.0f}',
                      'cls': 'hi' if shown >= 66 else ('lo' if shown <= 33 else '')})
    srows.append({'label': lab, 'cells': cells})

summary = {
    'title': f'AXP monthly credit metrics — {mlab(LATEST)}'
             f'（原 deck 的 Exhibit 1 与 Exhibit 8 两张汇总表合并，两者最新月同为 {mlab(LATEST)}）',
    'heads': [mlab(CUR), mlab(PRV), mlab(YAG), 'm/m', 'y/y', '3Y %ile'],
    'sep': 3,
    'rows': srows,
    'note': (BASIS_N + '.  ' + JUN_NOTE + '.  Green = improving (lower delinquency / write-off).  '
             'Trust 各行来自与 8-K 同日报送的 Form 10-D（近 31 期 31/31 同日）；'
             + TRUST_NOTE + '.  比率类指标的差异一律用 pp / bp（|差| &lt; 1pp 时写 bp）；'
             '零变化不着色。3Y %ile = 当月读数在最近 36 个月里高于多少百分比的观测，'
             '逾期率／核销率等反向指标按「越低越好」着色（分位低=绿）。'
             f'注意新口径序列只有 {len(new)} 个月历史（{new.index[0]} 起），'
             f'其分位实际是在 {len(new)} 个月内取的；Trust 行才是满 36 个月。'),
}


# ────────────────────────────── Exhibit 2..18 ──────────────────────────────
ex = []

# ══ 板块 A：新合并口径（PDF 第 1 页，Exhibit 2-7）══
ex.append(bar_yoy_ex(
    2, SEC_A + 'U.S. Consumer Card balances', new['consumer_balance_usdbn'],
    win=25, yfmt='usd1', ylab='$bn', src_extra=SRC_N + '.  ' + BASIS_N))

ex.append(multi_line_ex(
    3, SEC_A + 'U.S. Consumer delinquency and write-off', new,
    ['consumer_dq30_pct', 'consumer_nco_pct'], ['MBLUE', 'RED'],
    ['30+ days past due', 'Net write-off (principal)'],
    win=26, src_extra=SRC_N + '.  ' + JUN_NOTE))

ex.append(bar_yoy_ex(
    4, SEC_A + 'U.S. Small Business Card balances', new['sbs_balance_usdbn'],
    win=25, yfmt='usd1', ylab='$bn', src_extra=SRC_N + '.  ' + BASIS_N))

ex.append(multi_line_ex(
    5, SEC_A + 'U.S. Small Business delinquency and write-off', new,
    ['sbs_dq30_pct', 'sbs_nco_pct'], ['MBLUE', 'RED'],
    ['30+ days past due', 'Net write-off (principal)'],
    win=26, src_extra=SRC_N + '.  ' + JUN_NOTE))

ex.append(bar_yoy_ex(
    6, SEC_A + 'Implied U.S. card net interest income', avgbal['implied_nii_usdmn'],
    win=25, yfmt='f0c', ylab='$mn / month', note=NII_NOTE, src_extra=SRC_N))

_niy_yy_set = sorted({round(float(v), 1) for v in
                      lvl_yoy(tail_contiguous(avgbal['niy']), True).iloc[-25:].dropna().values})
ex.append(bar_yoy_ex(
    7, SEC_A + 'Net interest yield on card balances', avgbal['niy'],
    win=25, yfmt='pct1', ylab='% annualised', pct_series=True,
    note=f'费率是季度阶梯（同一季度三个月同值），所以右轴同比（百分点差）在整个窗口内'
         f'恒为 {"／".join(f"{v:+.1f}pp" for v in _niy_yy_set)} —— 那条绿线是平的不是画错，'
         f'右轴刻度因量程只有 0.2pp 而出现重复读数，以线的位置为准。',
    src_extra=SRC_N + '.  The disclosed company-wide yield, stepped quarterly. This is the '
              'rate the bridge above multiplies by, so it is where the bridge can go wrong.'))

# ══ 板块 B：Lending Trust 月度 10-D（PDF Exhibit 9-12；Exhibit 8 的汇总表已并入上表）══
ex.append(bar_yoy_ex(
    8, SEC_T + 'Trust excess spread', trust['excess_spread_pct'],
    win=25, yfmt='pct1', ylab='%', pct_series=True,
    src_extra=TRUST_SRC + '.  Portfolio yield less charge-offs, servicing and note coupon — '
              'the cushion that absorbs losses before noteholders are hit. The single '
              'most-watched number in the trust report'))

ex.append(multi_line_ex(
    9, SEC_T + 'Trust portfolio yield and payment rate', trust,
    ['portfolio_yield_pct', 'payment_rate_pct'], ['NAVY', 'MBLUE'],
    ['Portfolio yield', 'Payment rate'], win=25,
    src_extra=TRUST_SRC + '.  Payment rate is how fast cardholders repay; a falling payment '
              'rate is an early warning that shows up months before delinquency does'))

ex.append(multi_line_ex(
    10, SEC_T + 'Loss rate: trust pool vs. 8-K Card balances', trust,
    ['nco_pct', 'consumer_nco_pct'], ['NAVY', 'RED'],
    ['Trust: annualised default rate, net of recoveries',
     '8-K: U.S. Consumer net write-off rate'], win=25,
    src_extra=TRUST_SRC + '.  The two are close analogues but not the same definition, and '
              + TRUST_NOTE.lower()))

ex.append(multi_line_ex(
    11, SEC_T + 'Delinquency: trust pool vs. 8-K Card balances', trust,
    ['dq30_pct', 'consumer_dq30_pct'], ['NAVY', 'RED'],
    ['Trust: total 30+ days delinquent', '8-K: U.S. Consumer 30+ days past due'], win=25,
    src_extra=TRUST_SRC + '.  Both are 30+ day measures on the same concept, so the persistent '
              'gap is purely the pool difference: ' + TRUST_NOTE.lower()))

# ══ 板块 C：旧 loans-only 口径（PDF 第 2 页，Exhibit 13-19）══
# JPM Fig 1：柱=水平值 + 线=同比，长窗口含疫情前
ex.append(bar_yoy_ex(
    12, SEC_O + 'U.S. Consumer loans and y/y growth', old['consumer_balance_usdbn'],
    win=42, yfmt='usd0', ylab='$bn', bar_color='NAVY', bar_name='Reported',
    xstep=2, src_extra=SRC_O + '.  ' + BASIS_O))

# JPM Fig 2：季节性剥离
e13, y13 = seasonality_ex(13, SEC_O + 'Write-off rate vs. same-month norm',
                          old['consumer_nco_pct'], win=13, years=9,
                          src_extra=SRC_O + '.  ' + BASIS_O)
ex.append(e13)

# JPM Fig 3：逐日历月分布
ex.append(year_lines_ex(
    14, SEC_O + 'Consumer write-off rate by year', old['consumer_nco_pct'], n_years=6,
    src_extra=SRC_O + '.  Each line is one calendar year; red = current year.  ' + BASIS_O))

e15, y15 = seasonality_ex(15, SEC_O + 'Delinquency vs. same-month norm',
                          old['consumer_dq30_pct'], win=13, years=9,
                          src_extra=SRC_O + '.  ' + BASIS_O)
ex.append(e15)

ex.append(year_lines_ex(
    16, SEC_O + 'Small Business write-off rate by year', old['sbs_nco_pct'], n_years=6,
    src_extra=SRC_O + '.  Each line is one calendar year; red = current year.  ' + BASIS_O))

# JPM Fig 4：月 x 年热力矩阵（信用指标：低=好，故反转配色）
ex.append(heat_ex(
    17, SEC_O + 'Consumer net write-off rate (%)', old['consumer_nco_pct'], n_years=11,
    src_extra=SRC_O + '.  Green = lower write-off rate (better).  ' + BASIS_O))

ex.append(heat_ex(
    18, SEC_O + 'Small Business net write-off rate (%)', old['sbs_nco_pct'], n_years=11,
    src_extra=SRC_O + '.  Green = lower write-off rate (better).  ' + BASIS_O))


# ────────────────────────────── Exhibit 19：核对表 ──────────────────────────────
TB_WIN = [LATEST - k for k in range(12, -1, -1)]
tb_cols = [
    ['Consumer 余额 ($bn)', 'c_bal'], ['Consumer 30+ DPD (%)', 'c_dq'],
    ['Consumer 平均余额 ($bn)', 'c_avg'], ['Consumer 净核销 (%)', 'c_nco'],
    ['SBS 余额 ($bn)', 's_bal'], ['SBS 30+ DPD (%)', 's_dq'],
    ['SBS 平均余额 ($bn)', 's_avg'], ['SBS 净核销 (%)', 's_nco'],
    ['Card balances HFI ($bn)', 'hfi'],
    ['Trust 组合收益率 (%)', 't_py'], ['Trust 还款率 (%)', 't_pay'],
    ['Trust 超额利差 (%)', 't_es'], ['Trust 30+ 逾期 (%)', 't_dq'],
    ['Trust 年化净违约率 (%)', 't_nco'], ['Trust 本金应收 ($bn)', 't_bal'],
]


def cell(df, p, col, dec):
    if p not in df.index or col not in df.columns:
        return None
    v = df.loc[p, col]
    return None if v is None or not np.isfinite(float(v)) else f'{float(v):,.{dec}f}'


tb_rows = []
for p in TB_WIN:
    tb_rows.append({
        'xl': mlab(p),
        'c_bal': cell(avgbal, p, 'consumer_total_bal_usdbn', 1),
        'c_dq': cell(avgbal, p, 'consumer_dpd30_pct', 1),
        'c_avg': cell(avgbal, p, 'consumer_avg_bal_usdbn', 1),
        'c_nco': cell(avgbal, p, 'consumer_nwo_pct', 1),
        's_bal': cell(avgbal, p, 'smb_total_bal_usdbn', 1),
        's_dq': cell(avgbal, p, 'smb_dpd30_pct', 1),
        's_avg': cell(avgbal, p, 'smb_avg_bal_usdbn', 1),
        's_nco': cell(avgbal, p, 'smb_nwo_pct', 1),
        'hfi': cell(avgbal, p, 'total_hfi_usdbn', 1),
        't_py': cell(trust, p, 'portfolio_yield_pct', 4),
        't_pay': cell(trust, p, 'payment_rate_pct', 4),
        't_es': cell(trust, p, 'excess_spread_pct', 4),
        't_dq': cell(trust, p, 'dq30_pct', 2),
        't_nco': cell(trust, p, 'nco_pct', 4),
        't_bal': cell(trust, p, 'principal_receivables_usdbn', 3),
    })

table = {
    'n': 19,
    'title': f'近 13 个月月度指标核对表（{mlab(TB_WIN[0])} → {mlab(TB_WIN[-1])}，官方原始单位，未换算）',
    'idx': '月份', 'cols': tb_cols, 'rows': tb_rows,
}


# ────────────────────────────── headline / notes ──────────────────────────────
c_bal, c_bal_y = new.loc[CUR, 'consumer_balance_usdbn'], new.loc[YAG, 'consumer_balance_usdbn']
s_bal, s_bal_y = new.loc[CUR, 'sbs_balance_usdbn'], new.loc[YAG, 'sbs_balance_usdbn']
c_dq, c_dq_y = new.loc[CUR, 'consumer_dq30_pct'], new.loc[YAG, 'consumer_dq30_pct']
c_nco, c_nco_y = new.loc[CUR, 'consumer_nco_pct'], new.loc[YAG, 'consumer_nco_pct']
t_es, t_es_y = trust.loc[CUR, 'excess_spread_pct'], trust.loc[YAG, 'excess_spread_pct']
hfi = new.loc[CUR, 'total_balance']

HEADLINE = (
    f'{mlab(CUR)}：U.S. Consumer Card 余额 ${c_bal:,.1f}bn（{(c_bal / c_bal_y - 1) * 100:+.1f}% y/y）'
    f' · 30+ 逾期 {c_dq:.1f}%（{(c_dq - c_dq_y) * 100:+.0f}bp y/y）'
    f' · 净核销 {c_nco:.1f}%（{(c_nco - c_nco_y) * 100:+.0f}bp y/y，含出售已核销余额的一次性影响）'
    f' · SBS 余额 ${s_bal:,.1f}bn（{(s_bal / s_bal_y - 1) * 100:+.1f}% y/y）'
    f' · Card balances HFI ${hfi:,.1f}bn'
    f' · Trust 超额利差 {t_es:.2f}%（{(t_es - t_es_y) * 100:+.0f}bp y/y）')

HUB = (f'Consumer Card 余额 ${c_bal:,.1f}bn（{(c_bal / c_bal_y - 1) * 100:+.1f}% y/y）；'
       f'净核销 {c_nco:.1f}%；Trust 超额利差 {t_es:.2f}%')

NOTES = [
    f'<b>两套口径不可连比。</b>AXP 自 2026 年 5 月起把 Card Member loans 与 receivables 合并披露为'
    f' "Card balances"（含 pay-in-full 余额），并在 2026-05-15 的 8-K Exhibit 99.1 里重述了 24 个月历史。'
    f'原 PDF 分两页呈现，网页版没有分页概念，改用标题里的板块小标题分组：'
    f'<b>{SEC_A}</b>为 Exhibit 2-7（{new.index[0]} 起），'
    f'<b>{SEC_O}</b>为 Exhibit 12-18（{old.index[0]} → {old.index[-1]}）。'
    f'跨这两组读同一条指标是错的 —— 合并口径的余额里多了不计息的 pay-in-full 部分，'
    f'分母变大会把逾期率与核销率整体压低。',

    f'<b>旧口径序列刻意截到 {old.index[-1]}</b>（改口径前最后一个月），只用于长历史与季节性；'
    f'{new.index[0]} 之后的新口径数字不会被接到旧序列尾巴上，避免画出一条假的连续曲线。',

    f'<b>⚠️ {JUN_NOTE}。</b>受影响的是 Exhibit 3 / 5 的核销率末点、Exhibit 10 的 8-K 线末点，'
    f'以及汇总表里 Consumer / SBS 两行的净核销 m/m 与 y/y —— 这一档下降不是资产质量改善，'
    f'不要外推。',

    f'<b>Exhibit 6 是推导值，标了 Implied。</b>{NII_NOTE} 净利息收益率是公司整体口径（含非美卡与其他贷款），'
    f'而余额只取美国 Consumer + Small Business 卡，两者总体不一致；季度费率按「当季各月同值、'
    f'最新季之后沿用」摊到月度（Exhibit 7 画的就是这条阶梯）。公司不按月披露 NII，因此这张图无从对账。',

    f'Exhibit 6 / 7 的序列比其余新口径图短两个月：{new.index[0]} 与 {new.index[0] + 1} 落在 '
    f'{_niy.index[0]} 之前，没有可用的新口径净利息收益率，按「缺列就没有那个点」处理，不做外推。',

    f'<b>Lending Trust（Exhibit 8-11）是另一个池子，不是 8-K 的子集。</b>{TRUST_NOTE}；'
    f'信托池只含 revolve-eligible 余额，所以组合收益率、违约率、逾期率都系统性低于/异于 8-K 口径，'
    f'Exhibit 10 / 11 里那条持续存在的缺口是池子差异，不是数据错。Form 10-D 与 8-K 同日报送'
    f'（近 31 期 31/31 同日），所以两份材料一次到手。',

    f'<b>汇总表把原 deck 的两张表合并成了一张。</b>原 PDF 的 Exhibit 1（8-K 指标）与 Exhibit 8'
    f'（Trust 月报）是两张独立的汇总表，网页版只有一个汇总表位，两者最新月同为 {mlab(LATEST)}、'
    f'列口径也完全一致，故合并并用板块分隔条区分；其后各图顺延一位编号（PDF 的 Fig 9-19 = 本页的 '
    f'Exhibit 8-18）。',

    f'比率类指标的变化一律用百分点：|差| &lt; 1pp 写 bp，否则写 pp，不用「百分比的百分比变化」。'
    f'逾期率、核销率、信托违约率按「越低越好」着色（下降为绿）。3Y %ile 是当月读数在最近 36 个月内的'
    f'百分位；对几乎只增不减的序列（diff ≥ 0 的比例 ≥ 90%）留空 —— 那种分位恒为 100，是噪音不是信息。'
    f'本期没有任何一行触发该规则。',

    f'Exhibit 13 / 15 的灰柱是<b>过去 {y13} 年同一日历月的均值</b>（不是滚动均值），'
    f'用来把季节性从水平值里剥掉；Exhibit 14 / 16 每条线是一个日历年，红线为当前年（{old.index[-1].year} 年'
    f'只到 {MONTHS[old.index[-1].month - 1]}）。Exhibit 17 / 18 的热力矩阵配色已反转：'
    f'<b>绿 = 核销率低（好）</b>，色标取全部有限值的 5/95 分位，一两个离群月不会把整表压平。',

    f'<b>与原 PDF 的三处有意差异。</b>(1) 原 deck 的 lvl_bar / rev_bar_yoy 是「柱 + 右轴同比线」，'
    f'这里用 <code>bar_line_dual</code> 还原同一形态（而不是 CONTRACT §3 建议的 <code>gs_bar</code>）——'
    f'<code>gs_bar</code> 的 MoM 气泡与箭头位置写死在 13 个月窗口上，而本页这几张图是 24 / 25 / 42 个月'
    f'窗口，箭头会指到画面中间的错误柱子上，柱顶数值标签也会在 24 根柱上叠成一团，'
    f'且会丢掉整条同比线。'
    f'(2) 两张热力矩阵没有走通栏：通栏卡片会被渲染器排到汇总表正下方、跑到 Exhibit 2 前面，'
    f'为保住原 deck 的图序改用半栏（引擎会按格宽自动收字号）。'
    f'(3) 汇总表里「零变化」不着色（原 deck 把 0 着成红色，等于说「没变 = 变坏」）。'
    f'除此之外顺序、窗口、标题与图注均照搬。',
]

FOOTER = ('American Express (AXP)  ·  SEC 8-K Item 7.01 (CIK 0000004962) + Credit Account Master '
          'Trust Form 10-D (CIK 0001003509)  ·  template after J.P. Morgan managed-data-release '
          'note  ·  charts only, no commentary  ·  personal research use')

payload = {
    'ticker': 'axp',
    'tracker': 'AXP Monthly Credit Metrics Tracker',
    'title': f'American Express (AXP)：月度信贷经营指标 — {LATEST.year} 年 {LATEST.month} 月',
    'data_through': str(LATEST),
    'through_label': f'{LATEST.year} 年 {LATEST.month} 月',
    'subtitle': f'数据源：SEC 8-K Item 7.01（CIK 0000004962）与 American Express Credit Account '
                f'Master Trust Form 10-D（CIK 0001003509）　·　覆盖 {old.index[0]} → {LATEST}'
                f'（旧 loans-only 口径 {old.index[0]} → {old.index[-1]}；新合并 Card balances 口径 '
                f'{new.index[0]} 起；Trust {trust.index[0]} 起）　·　版式仿 J.P. Morgan'
                f'「Managed Data Release」',
    'headline': HEADLINE,
    'hub_line': HUB,
    'source': 'Source: AXP 8-K Item 7.01 (SEC CIK 0000004962) and American Express Credit Account '
              'Master Trust Form 10-D (SEC CIK 0001003509); format after J.P. Morgan',
    'xlabels': [mlab(p) for p in TB_WIN],
    'xlabels_long': xl(old.index),
    'summary': summary,
    'exhibits': ex,
    'table': table,
    'notes': NOTES,
    'footer': FOOTER,
}
if SOURCE_DATE:
    payload['source_date'] = SOURCE_DATE


def main():
    out_dir = os.path.join(ROOT, 'data')
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'axp.js')
    with open(path, 'w', encoding='utf-8') as f:
        # 构建日期只写首行注释，不进 payload —— 进了 payload，monthly_run 的
        # 「data 有没有实质变化」检查（忽略首行的正文比较）就永久失效。
        f.write(f'// 由 build/axp.py 生成于 {datetime.date.today().isoformat()}，请勿手改\n')
        f.write('window.DASH = ')
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')

    print(f'最新月 {LATEST}  ·  旧口径 {old.index[0]} → {old.index[-1]}（{len(old)} 个月）'
          f'  ·  新口径 {new.index[0]} → {new.index[-1]}（{len(new)} 个月）'
          f'  ·  Trust {trust.index[0]} → {trust.index[-1]}（{len(trust)} 个月）')
    print(f'Exhibit 1 汇总表（{len(srows)} 行）+ Exhibit {ex[0]["n"]}-{ex[-1]["n"]}'
          f'（{len(ex)} 张图）+ Exhibit {table["n"]} 核对表（{len(tb_rows)} 行 x {len(tb_cols)} 列）'
          f'  ·  notes {len(NOTES)} 条')
    print(f'写出 data/axp.js  ({os.path.getsize(path) / 1024:.1f} KB)')
    print(HEADLINE)


if __name__ == '__main__':
    main()
