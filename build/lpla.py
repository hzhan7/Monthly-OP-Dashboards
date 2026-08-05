# -*- coding: utf-8 -*-
"""LPL Financial (LPLA) 月度经营指标 —— 把 build/build_lpla.py 的 matplotlib deck
逐张移植成网页看板 payload，写出 data/lpla.js。

模版来源：Goldman Sachs (Alexander Blostein 团队)「LPL Financial Holdings (LPLA):
          April metrics…」的 Exhibit 1，以及同系列 11 月期。该表的三条口径规矩本站全部照搬：
   1) **流量类（NNA）不算环比/同比百分比**，改用「年化有机增长率」= 当月 NNA x 12 / 上月末资产；
   2) **比率类差异一律用 bp / pp**，不用百分比变化；
   3) 存量分两个业务口径（Advisory / Brokerage）+ Total + 占比行。
   另采用 GS「SCHW First Take」Exhibit 2 的恒等式滚存桥（期初 + 净新增 + 市值变动 = 期末）。
数据源：LPL Financial IR 月度经营指标新闻稿。季末月（3/6/9/12）无独立月报，取自当季季报。

⚠️ 并购导入：2025 年 8 月 NNA 中含 Commonwealth Financial Network 约 2,850 亿美元资产导入，
   该月不是有机流入，图上以红色竖虚线标出。

输入（只读，一律来自 series/）：
    series/lpla.csv       月度经营指标（2018-07 起）
    series/fee_rates.csv  季度费率与季度实际收入（company = LPLA）
输出：
    data/lpla.js          window.DASH = {...}

幂等：payload 里不写构建日期（只写首行注释），不使用随机数，窗口一律从数据最新月倒推。
"""
import datetime
import json
import math
import os

import numpy as np
import pandas as pd

import payload_guard

D = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(D)
SERIES = os.path.join(ROOT, 'series')

SRC = ('Source: LPL Financial monthly activity and quarterly reports; '
       'format after Goldman Sachs GIR')
# $275bn 是公司披露值，不是估算：LPL 2025Q3 报告原文
# "This included $275 billion of acquired net new assets resulting from the acquisition
#  of Commonwealth" —— 曾经这里写过 ~$285bn（来自原 deck docstring 的约数），
# 而同一事件在 wealth 页又写成 $277.0bn，同一个数在站内出现三种写法。
BNOTE = ('Red dashed line = Aug-2025 Commonwealth onboarding ($275bn); '
         'that month is not organic flow')
QNOTE = ('Quarter-end months have no standalone monthly report; those values come from '
         'the quarterly release')

# 官方同页披露的 Acquired NNA（$bn）。2022 年起完整；更早年份原件用旧行名，未解析，故不调整。
# 逐条与 build/build_lpla.py 的 ACQ 表一致 —— 它不是 series/lpla.csv 的一列，
# 而是 deck 里登记的公司披露常量，移植时原样带过来（见 notes 第 4 条）。
ACQ = {'2023-01': 3.2, '2023-03': 0.5, '2024-04': 5.0, '2024-08': 0.3, '2024-09': 0.3,
       '2024-10': 88.3, '2024-11': 0.8, '2024-12': 0.3, '2025-01': 0.1, '2025-02': 0.7,
       '2025-03': 7.1, '2025-08': 275.0, '2025-12': 2.0}

BREAK = pd.Period('2025-08', 'M')
WIN_L = 25          # gsx.lvl_bar / multi_line 在原 deck 里的窗口
WIN_S = 13          # gsx.stack_share / bridge_bar 的窗口
WIN_Q = 14          # gsx.qtr_bar / implied_vs_actual 的窗口（季度）


# ────────────────────────────── 读数 ──────────────────────────────
def mlab(p):
    return p.strftime('%b-%y')


def load():
    df = pd.read_csv(os.path.join(SERIES, 'lpla.csv'))
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    df = df.set_index('month').sort_index()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    need = ['total_assets_usdbn', 'advisory_assets_usdbn', 'brokerage_assets_usdbn',
            'nna_total_usdbn', 'nna_advisory_usdbn', 'nna_brokerage_usdbn',
            'client_cash_usdbn']
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise SystemExit(f'series/lpla.csv 缺列: {missing}')
    # 逐月连续性：断档会让「相隔数月的两点」被画成相邻柱（规矩 3）
    idx = list(df.index)
    for i in range(1, len(idx)):
        if (idx[i] - idx[i - 1]).n != 1:
            raise SystemExit(f'series/lpla.csv 月份不连续: {idx[i-1]} → {idx[i]}')
    return df


def rate_series(metric, to=None):
    """series/fee_rates.csv 里 LPLA 的季度序列，索引 PeriodIndex(freq='Q')。"""
    d = pd.read_csv(os.path.join(SERIES, 'fee_rates.csv'))
    d = d[(d['company'] == 'LPLA') & (d['metric'] == metric)].copy()
    if not len(d):
        raise SystemExit(f'fee_rates.csv 里没有 LPLA/{metric}')
    d['q'] = pd.PeriodIndex(d['period'].str.replace('-', '', regex=False), freq='Q')
    out = d.set_index('q')['value'].astype(float).sort_index()
    if to:
        units = set(d['unit'].dropna())
        if len(units) != 1:
            raise SystemExit(f'LPLA/{metric} 单位不唯一: {units}')
        scale = {('USD_k', 'mn'): 1e-3, ('USD_mn', 'mn'): 1.0, ('USD_bn', 'mn'): 1e3}
        u = units.pop()
        if (u, to) not in scale:
            raise SystemExit(f'LPLA/{metric} 单位 {u} 无法换算到 {to}')
        out = out * scale[(u, to)]
    return out


# ────────────────────────────── 格式化零件 ──────────────────────────────
def num(v, dec=1, money='', pct=False):
    if v is None or not np.isfinite(v):
        return '—'
    return f'{money}{v:,.{dec}f}' + ('%' if pct else '')


def L(a):
    """序列 → JSON 数组，非有限值写 None（页面自动断开，不画假线）。"""
    return [None if (v is None or not np.isfinite(float(v))) else round(float(v), 6) for v in a]


def yoy_txt(s, pct_series=False):
    """gs_bar 气泡里的 y/y 文案。比率序列用 pp（GS 规矩 2），水平值用百分比。"""
    a, b = float(s.iloc[-1]), float(s.iloc[-13])
    if not (np.isfinite(a) and np.isfinite(b)):
        return None
    if pct_series:
        return f'{a - b:+.1f}pp y/y'
    if b == 0 or a * b < 0:
        return None
    return f'{(a / b - 1) * 100:+.0f}% y/y'


def avg_prior12(s):
    """「Prior 12mo Avg.」= 最新月之前的 12 个月均值（不含最新月）。"""
    v = s.iloc[-13:-1].astype(float)
    if not np.isfinite(v.values).any():
        raise SystemExit('avg12 无有效值')
    return round(float(np.nanmean(v.values)), 6)


def main():
    df = load()
    LATEST = df.index[-1]
    tot = df['total_assets_usdbn']
    nna = df['nna_total_usdbn']

    df['pct_advisory'] = df['advisory_assets_usdbn'] / tot * 100
    df['organic_growth_ann'] = nna * 12 / tot.shift(1) * 100
    df['cash_pct_assets'] = df['client_cash_usdbn'] / tot * 100
    df['market_gains'] = tot.diff() - nna
    acq = pd.Series({pd.Period(k, 'M'): v for k, v in ACQ.items()}).reindex(df.index).fillna(0.0)
    df['acquired_nna'] = acq
    df['nna_ex'] = nna - acq
    df['organic_growth_ex'] = df['nna_ex'] * 12 / tot.shift(1) * 100
    df['total_tn'] = tot / 1000.0

    # ── 量→收入桥：client cash revenue = 月末客户现金 x 披露净收益率 / 12 ──
    cy = rate_series('client_cash_net_yield')                    # bp, annualised
    q_of_month = pd.PeriodIndex(df.index).asfreq('Q')
    cy_m = pd.Series([cy.get(qq, np.nan) for qq in q_of_month], index=df.index).ffill()
    df['implied_cash_rev_usdmn'] = df['client_cash_usdbn'] * 1000.0 * cy_m / 10000.0 / 12.0
    BR_NOTE = ('Assumption: monthly client-cash revenue = month-end client cash x the disclosed '
               'net yield / 12. The yield is taken from the quarterly report '
               f'({cy.index[-1]} = {cy.iloc[-1]:,.4g} bp) and held flat for months after '
               'that quarter')

    # 桥的季度验证：只保留满 3 个月的季度
    imp_m = df['implied_cash_rev_usdmn'].dropna()
    qi = pd.PeriodIndex(imp_m.index).asfreq('Q')
    imp_q = imp_m.groupby(qi).sum()
    cnt = pd.Series(1, index=imp_m.index).groupby(qi).sum()
    imp_q = imp_q.loc[[q for q in imp_q.index if cnt.get(q, 0) == 3]]
    act_q = rate_series('client_cash_revenue', to='mn')

    # ── 三个窗口 ──
    W25 = df.iloc[-WIN_L:]
    W13 = df.iloc[-WIN_S:]
    XL25 = [mlab(p) for p in W25.index]
    XL13 = [mlab(p) for p in W13.index]
    XLALL = [mlab(p) for p in df.index]
    B25 = list(W25.index).index(BREAK) if BREAK in W25.index else None
    B13 = list(W13.index).index(BREAK) if BREAK in W13.index else None
    BALL = list(df.index).index(BREAK) if BREAK in df.index else None
    if B25 is None or B13 is None or BALL is None:
        raise SystemExit(f'口径断点 {BREAK} 不在数据里，断点线画不出来')

    def bar(n, col, title, legend, ylab, fmt, note, pct_series=False,
            window=W25, xl=XL25, break_at=None, extra=None):
        """gsx.lvl_bar → 网页 gs_bar（柱 + Prior-12mo 均线 + 每柱数值 + y/y 气泡）。"""
        s = df[col].dropna()
        ex = {'n': n, 'kind': 'gs_bar', 'fmt': fmt, 'yfmt': fmt, 'xlabels': xl,
              'title': title, 'ylab': ylab, 'legend': legend,
              'values': L(window[col].values), 'avg12': avg_prior12(s)}
        y = yoy_txt(s, pct_series)
        if y:
            ex['yoy_txt'] = y
        if break_at is not None:
            ex['break_at'] = break_at
            ex['break_label'] = 'M&A'
        if note:
            ex['note'] = note
        if extra:
            ex['src_extra'] = extra
        return ex

    ex = []

    # ── Exhibit 2：Total client assets（gsx.lvl_bar, win=25, dec=2, $tn）──
    ex.append(bar(2, 'total_tn', 'Total client assets', 'Total client assets',
                  'Total client assets ($tn)', 'usd2',
                  '原 deck 的 gsx.lvl_bar（win=25、dec=2、单位 $tn）。柱为月末客户资产总额，'
                  '虚线为最新月之前 12 个月的均值，气泡为 y/y。' + BNOTE + '。',
                  break_at=B25))

    # ── Exhibit 3：Organic net new assets（gsx.lvl_bar, win=25, dec=1, $bn）──
    ex.append(bar(3, 'nna_ex', 'Organic net new assets', 'Organic NNA',
                  'Organic net new assets ($bn)', 'usd1',
                  'Total NNA less the Acquired NNA that LPL discloses on the same page '
                  '(Atria Oct-24 $88.3bn, Commonwealth Aug-25 $275.0bn)。'
                  '并购导入按公司披露的拆分逐月扣除，不整月置零。'))

    # ── Exhibit 4：Annualised organic growth rate（gsx.lvl_bar, pct_series）──
    ex.append(bar(4, 'organic_growth_ex', 'Annualised organic growth rate',
                  'Annualised organic growth', 'Organic growth (% annualised)', 'pct1',
                  'Organic NNA x 12 / prior month-end assets, the GS convention; acquired '
                  'assets stripped out using the disclosed split。比率序列的 y/y 用百分点差（GS 规矩 2）。',
                  pct_series=True))

    # ── Exhibit 5：Client assets advisory vs brokerage（gsx.stack_share, win=13）──
    share13 = (W13['advisory_assets_usdbn'] / (W13['advisory_assets_usdbn']
                                               + W13['brokerage_assets_usdbn']) * 100)
    ymax_share = max(60.0, 10.0 * math.ceil(float(share13.max()) / 10.0))
    ex.append({
        'n': 5, 'kind': 'stacked_dual', 'xlabels': XL13,
        'title': 'Client assets: advisory vs. brokerage',
        'ylab': 'Client assets ($bn)', 'ylab2': '% advisory (RHS)',
        'yfmt': 'f0c',
        'stacks': [
            {'name': 'Advisory', 'color': 'NAVY', 'values': L(W13['advisory_assets_usdbn'].values),
             'label': True, 'label_color': 'WHITE'},
            {'name': 'Brokerage', 'color': 'BLUE', 'values': L(W13['brokerage_assets_usdbn'].values),
             'label': True, 'label_color': 'NAVY'},
        ],
        'line': {'name': '% advisory (RHS)', 'color': 'GREEN', 'values': L(share13.values),
                 'ymax': ymax_share},
        'break_at': B13, 'break_label': 'M&A',
        'note': '堆叠柱为两个业务口径的月末资产（$bn），右轴绿线为 advisory 占比。'
                '红色虚线右侧含 Commonwealth 并表，与左侧不可直读。' + QNOTE + '。',
    })

    # ── Exhibit 6：What moved client assets（gsx.bridge_bar, win=13）──
    net13 = W13['nna_total_usdbn'].fillna(0) + W13['market_gains'].fillna(0)
    ex.append({
        'n': 6, 'kind': 'bridge_bar', 'xlabels': XL13, 'fmt': 'f0',
        'title': 'What moved client assets: flows vs. markets',
        'ylab': 'Change in client assets ($bn)',
        'stacks': [
            {'name': 'Net new assets', 'color': 'NAVY', 'values': L(W13['nna_total_usdbn'].values)},
            {'name': 'Market gains (balancing)', 'color': 'BLUE', 'values': L(W13['market_gains'].values)},
        ],
        'net': {'name': 'Total change in client assets', 'values': L(net13.values)},
        'net_color': 'INK',
        'break_at': B13, 'break_label': 'M&A',
        'note': 'Identity: opening assets + NNA + market gains = closing assets. '
                'Market gains 是恒等式的配平项（当月资产变动 − 当月 NNA），不是公司披露值。'
                + BNOTE + '。',
    })

    # ── Exhibit 7：NNA by channel（gsx.multi_line, win=25）──
    ex.append({
        'n': 7, 'kind': 'lines_endlabels', 'fmt': 'usd1', 'xlabels': XL25,
        'title': 'Net new assets by channel', 'ylab': 'Net new assets ($bn)',
        'series': [
            {'name': 'Advisory NNA', 'color': 'NAVY', 'values': L(W25['nna_advisory_usdbn'].values)},
            {'name': 'Brokerage NNA', 'color': 'RED', 'values': L(W25['nna_brokerage_usdbn'].values)},
        ],
        'break_at': B25, 'break_label': 'M&A',
        'note': 'Brokerage NNA has been persistently negative — the advisory conversion is '
                'visible as a mirror image。Aug-2025 的 Commonwealth 并表把两条线同时顶起，'
                '纵轴被那一个月主导（与原 deck 一致，未截轴）。',
    })

    # ── Exhibit 8：Total client assets since 2018（gsx.long_line）──
    ex.append({
        'n': 8, 'kind': 'lines', 'x': 'long', 'full': True, 'fmt': 'usd1', 'xstep': 6,
        'title': 'Total client assets since 2018', 'ylab': 'Total client assets ($tn)',
        'series': [{'name': 'Total client assets', 'color': 'NAVY', 'values': L(df['total_tn'].values)}],
        'break_at': BALL, 'break_label': 'M&A',
        'note': BNOTE + '。原 deck 在末端画了一个红色虚线圈标出最近 3 个月，网页版没有等价元素，'
                        '改由 x 轴末端与表格视图直接读数。',
    })

    # ── Exhibit 9：Client cash balances（gsx.lvl_bar, win=25）──
    ex.append(bar(9, 'client_cash_usdbn', 'Client cash balances', 'Client cash balances',
                  'Client cash ($bn)', 'usd1',
                  '月末客户现金余额（含银行存款 sweep）。' + QNOTE + '。'))

    # ── Exhibit 10：Client cash as % of client assets（gsx.lvl_bar, pct_series）──
    ex.append(bar(10, 'cash_pct_assets', 'Client cash as % of client assets',
                  'Client cash / client assets', 'Client cash (% of client assets)', 'pct1',
                  'Cash share is the key net-interest-revenue driver; a falling share is a '
                  'headwind。原 deck 这张图取两位小数，网页格式器只有一位（pct1），'
                  '两位数值请看末尾核对表。',
                  pct_series=True))

    # ── Exhibit 11：NNA by quarter（gsx.qtr_bar, win=14）──
    nq = nna.dropna()
    qidx = pd.PeriodIndex(nq.index).asfreq('Q')
    q_sum = nq.groupby(qidx).sum()
    q_cnt = pd.Series(1, index=nq.index).groupby(qidx).sum()
    q_yoy = pd.Series([(q_sum.iloc[i] / q_sum.iloc[i - 4] - 1) * 100
                       if i >= 4 and q_sum.iloc[i - 4] else np.nan
                       for i in range(len(q_sum))], index=q_sum.index)
    qw = q_sum.iloc[-WIN_Q:]
    qy = q_yoy.iloc[-WIN_Q:]
    partial = int(q_cnt.iloc[-1])
    qlabs = [str(p) for p in qw.index]
    qbreak = list(qw.index).index(BREAK.asfreq('Q')) if BREAK.asfreq('Q') in qw.index else None
    exq = {
        'n': 11, 'kind': 'qtr_bar', 'xlabels': qlabs, 'fmt': 'f0c', 'label_fmt': 'f0c',
        'title': 'Net new assets by quarter', 'ylab': 'Net new assets ($bn)',
        'ylab2': 'y/y (%)',
        'legend': 'Complete quarter',
        'values': L(qw.values), 'qtr_months': 3,
        'line': {'name': 'y/y (RHS)', 'color': 'GREEN', 'values': L(qy.values), 'yfmt': 'pct0'},
        'note': '3Q25 includes the $275bn Commonwealth onboarding and is not comparable。'
                '月度 NNA 按日历季汇总；未满季的 y/y 由引擎作废（图、表、tooltip 一致）。',
    }
    if partial < 3:
        exq['partial_months'] = partial
    if qbreak is not None:
        exq['break_at'] = qbreak
        exq['break_label'] = 'M&A'
    ex.append(exq)

    # ── Exhibit 12：Advisory assets（gsx.lvl_bar, win=25）──
    ex.append(bar(12, 'advisory_assets_usdbn', 'Advisory assets', 'Advisory assets',
                  'Advisory assets ($bn)', 'f0c',
                  '月末 advisory 口径客户资产。' + BNOTE + '。',
                  break_at=B25))

    # ── Exhibit 13：Implied client-cash revenue（gsx.lvl_bar, win=25）──
    ex.append(bar(13, 'implied_cash_rev_usdmn', 'Implied client-cash revenue',
                  'Implied client-cash revenue', 'Implied client-cash revenue ($mn / month)',
                  'usd0', BR_NOTE + '。<b>推导值，非公司披露</b>，验证见 Exhibit 14。'))

    # ── Exhibit 14：Bridge check（gsx.implied_vs_actual）──
    qs = [q for q in imp_q.index if q in act_q.index][-WIN_Q:]
    imp_v = np.array([float(imp_q[q]) for q in qs])
    act_v = np.array([float(act_q[q]) for q in qs])
    err = np.where(act_v != 0, (imp_v / act_v - 1) * 100, np.nan)
    mae = float(np.nanmean(np.abs(err)))
    ex.append({
        'n': 14, 'kind': 'grouped_bars', 'xlabels': [str(q) for q in qs],
        'fmt': 'f0c', 'label_fmt': 'f0c',
        'title': 'Bridge check: implied vs. reported client-cash revenue',
        'ylab': 'Client-cash revenue ($mn / quarter)', 'ylab2': 'Error (%)',
        'groups': [
            {'name': 'Implied by the bridge', 'color': 'BLUE', 'values': L(imp_v)},
            {'name': 'Actually reported', 'color': 'NAVY', 'values': L(act_v)},
        ],
        'line': {'name': 'Error (RHS)', 'color': 'RED', 'values': L(err), 'yfmt': 'pct1'},
        'note': 'Reported = the client-cash revenue line in LPL results. The bridge applies the '
                'disclosed yield to MONTH-END cash while LPL earns it on AVERAGE cash — that '
                f'proxy error is what this tests. 窗口内平均绝对误差 {mae:.1f}%。'
                '未满 3 个月的季度不参与对比（2026Q2 只有 2 个月）。',
    })

    # ── Exhibit 15：Brokerage assets（gsx.lvl_bar, win=25）──
    ex.append(bar(15, 'brokerage_assets_usdbn', 'Brokerage assets', 'Brokerage assets',
                  'Brokerage assets ($bn)', 'f0c',
                  '月末 brokerage 口径客户资产。' + BNOTE + '。',
                  break_at=B25))

    # ── Exhibit 16：Advisory share of client assets（gsx.lvl_bar, pct_series）──
    ex.append(bar(16, 'pct_advisory', 'Advisory share of client assets',
                  'Advisory share', 'Advisory share (% of client assets)', 'pct1',
                  'Advisory assets carry a higher payout-adjusted margin than brokerage, so the '
                  'mix shift is a structural profit driver。原 deck 取两位小数，'
                  '网页格式器只有一位（pct1）。',
                  pct_series=True))

    # ── Exhibit 17：Client cash since 2018（gsx.long_line）──
    ex.append({
        'n': 17, 'kind': 'lines', 'x': 'long', 'full': True, 'fmt': 'f0c', 'xstep': 6,
        'title': 'Client cash since 2018', 'ylab': 'Client cash ($bn)',
        'series': [{'name': 'Client cash', 'color': 'NAVY',
                    'values': L(df['client_cash_usdbn'].values)}],
        'note': '2020 的台阶是疫情期间的现金堆积，2022-24 的回落是现金搬家（cash sorting）；'
                '这条线是 Exhibit 13 隐含收入的规模基数。',
    })

    # ── Exhibit 18：Organic growth path by year（gsx.year_lines, n_years=6）──
    og = df['organic_growth_ex'].dropna()
    yrs6 = sorted({p.year for p in og.index})[-6:]
    yl_series = []
    for y in yrs6:
        vals = [None] * 12
        for p, v in og.items():
            if p.year == y:
                vals[p.month - 1] = round(float(v), 6)
        yl_series.append({'name': str(y), 'values': vals})
    ex.append({
        'n': 18, 'kind': 'year_lines', 'fmt': 'pct1', 'label_fmt': 'pct1',
        'xlabels': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct',
                    'Nov', 'Dec'],
        'title': 'Organic growth path by year', 'ylab': 'Organic growth (% annualised)',
        'series': yl_series, 'highlight': len(yl_series) - 1,
        'note': 'Red = current year。画的是各月的年化有机增速本身（非累计，同原 deck 的 '
                'cumulative=False）。2021 年 4 月是 Waddell & Reed 导入（当月 NNA $73.8bn），'
                '公司当年用旧行名披露 Acquired NNA、未解析，故未扣除，纵轴被它拉高。',
    })

    # ── Exhibit 19：Organic growth heat matrix（gsx.heat_matrix, n_years=9）──
    yrs9 = sorted({p.year for p in og.index})[-9:]
    matrix = []
    for y in yrs9:
        row = [None] * 12
        for p, v in og.items():
            if p.year == y:
                row[p.month - 1] = round(float(v), 6)
        matrix.append(row)
    ex.append({
        'n': 19, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pct1',
        'title': 'Annualised organic growth rate (%)',
        'rows': [str(y) for y in yrs9],
        'cols': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct',
                 'Nov', 'Dec'],
        'matrix': matrix, 'legend': 'Annualised organic growth', 'row_head': '年',
        'note': 'Green = faster organic asset gathering; acquired assets removed using the '
                'disclosed split (complete from 2022 onward)。色标取全部有限值的 5/95 分位，'
                '2021-04 那类离群月不会把整表压平。',
    })

    # ── Exhibit 1：汇总表（gsx.summary_table 的行分组范式）──
    cur, prv, yag = LATEST, LATEST - 1, LATEST - 12

    def _rank36(win, c):
        """c 在 36 个月窗口 win 里的百分位（0-100）。"""
        return float((win.values < c).sum()) / max(1, len(win) - 1) * 100

    def pctile36(s):
        """近 36 个月分位。近乎单调的序列留空 —— 分位钉在 100（或 0）不动，是噪音不是信息。

        判据不用 CONTRACT §2 写的「上升月份占比 ≥ 90%」代理，而是**直接回放这一列**：
        把序列逐月截断，重算过去 24 个月每个月本该印出的分位，数其中有多少个月钉在
        极值（100 或 0）。理由是这个代理在本页根本分不开（实测于 series/lpla.csv）：

            列                       上升月占比   过去 24 个月里印 100 的月数
            advisory_assets           0.800        20 / 24
            brokerage_assets          0.771        20 / 24
            total_assets              0.771        20 / 24
            pct_advisory              0.800        14 / 24（分位实测 66–100，有真实离散度）

        市值型存量序列每年有 20%+ 的下跌月，所以代理判不出它单调 —— 可它照样月月刷
        36 个月新高，分位列就是一列恒定的绿 100。反过来，任何低到能盖住 brokerage
        (0.771) 的门槛都会连 % Advisory (0.800) 一起误杀，而后者是比率不是存量、
        Commonwealth 并表把 advisory 占比推到记录高位是有内容的读数。也就是说
        **调门槛救不了这个代理，只能换判据**。

        门槛 0.70 取自实测间隔的中点：留空组 20/24 = 0.833，保留组里最高的
        % Advisory 14/24 = 0.583，17/24 = 0.708 到两侧各差 3 个月，不是贴着数据卡的。
        """
        ss = s.dropna()
        c = ss.get(cur, np.nan)
        h = ss.iloc[-36:]
        if len(h) < 8 or not np.isfinite(c):
            return None
        hi = lo = n = 0
        for k in range(min(24, len(ss))):
            w = ss.iloc[:len(ss) - k]
            wh = w.iloc[-36:]
            if len(wh) < 8:
                break
            n += 1
            p = _rank36(wh, float(w.iloc[-1]))
            hi += p >= 100
            lo += p <= 0          # 单调下行的对称情形：分位恒为 0，同样没有信息
        if n and max(hi, lo) / n >= 0.70:
            return None
        return _rank36(h, c)

    def srow(label, col, dec, mode, pct=False, money='', inv=False):
        s = df[col].dropna()
        c = s.get(cur, np.nan)
        p1 = s.get(prv, np.nan)
        p12 = s.get(yag, np.nan)
        cells = [{'v': num(c, dec, money, pct)}, {'v': num(p1, dec, money, pct)},
                 {'v': num(p12, dec, money, pct)}]
        for b in (p1, p12):
            if not (np.isfinite(c) and np.isfinite(b)):
                cells.append({'v': ''})
                continue
            if mode in ('pp', 'abs'):
                v = c - b
            elif b == 0 or c * b < 0:
                cells.append({'v': ''})
                continue
            else:
                v = (c / b - 1) * 100
            if mode == 'pp':
                txt = f'{v*100:+.0f}bp' if abs(v) < 1 else f'{v:+.2f}pp'
            elif mode == 'abs':
                txt = f'{money}{v:+,.{max(0, dec)}f}'
            else:
                txt = f'{v:+.1f}%'
            good = (v < 0) if inv else (v > 0)
            cells.append({'v': txt, 'cls': 'pos' if good else 'neg'})
        p = pctile36(s)
        if p is None:
            cells.append({'v': ''})
        else:
            pv = (100 - p) if inv else p
            cells.append({'v': f'{p:.0f}',
                          'cls': 'hi' if pv >= 66 else ('lo' if pv <= 33 else '')})
        return {'label': label, 'cells': cells}

    summary = {
        'title': f'LPL Financial monthly metrics — {mlab(LATEST)}',
        'heads': [mlab(cur), mlab(prv), mlab(yag), 'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': [
            {'kind': 'group', 'label': 'Assets ($bn)'},
            srow('Advisory', 'advisory_assets_usdbn', 1, 'ratio'),
            srow('Brokerage', 'brokerage_assets_usdbn', 1, 'ratio'),
            srow('Total client assets', 'total_assets_usdbn', 1, 'ratio'),
            srow('% Advisory', 'pct_advisory', 1, 'pp', pct=True),
            {'kind': 'group', 'label': 'Net new assets ($bn)'},
            srow('Advisory NNA', 'nna_advisory_usdbn', 1, 'abs'),
            srow('Brokerage NNA', 'nna_brokerage_usdbn', 1, 'abs'),
            srow('Total NNA', 'nna_total_usdbn', 1, 'abs'),
            srow('Annualised organic growth (%)', 'organic_growth_ann', 2, 'pp', pct=True),
            {'kind': 'group', 'label': 'Client cash ($bn)'},
            srow('Client cash balances', 'client_cash_usdbn', 1, 'ratio'),
            srow('% of client assets', 'cash_pct_assets', 2, 'pp', pct=True),
        ],
        'note': 'Per GS convention: flow items (NNA) show an absolute change rather than a '
                'percentage, and are read through the annualised organic growth line. '
                + QNOTE + '. 3Y %ile = 当月读数在最近 36 个月里高于多少百分比的观测；'
                '若回放过去 24 个月、该行有 ≥ 70% 的月份分位钉在 100（或 0），说明这一列'
                '恒定不动、无信息量，留空 —— Advisory / Brokerage / Total client assets '
                '三行（24 个月里 20 个月都在刷 36 个月新高）即因此留空，它们的强弱读 m/m 与 y/y。',
    }

    # ── 末尾核对表（官方原始单位，未换算）──
    T13 = df.iloc[-13:]
    tcols = [['Total client assets ($bn)', 'tot'], ['Advisory ($bn)', 'adv'],
             ['Brokerage ($bn)', 'brk'], ['Total NNA ($bn)', 'nna'],
             ['Advisory NNA ($bn)', 'nnaa'], ['Brokerage NNA ($bn)', 'nnab'],
             ['Acquired NNA ($bn)', 'acq'], ['Client cash ($bn)', 'cash'],
             ['Client cash (% of assets)', 'cashp']]
    trows = []
    for p, r in T13.iterrows():
        trows.append({
            'xl': mlab(p),
            'tot': num(r['total_assets_usdbn'], 1),
            'adv': num(r['advisory_assets_usdbn'], 1),
            'brk': num(r['brokerage_assets_usdbn'], 1),
            'nna': num(r['nna_total_usdbn'], 1),
            'nnaa': num(r['nna_advisory_usdbn'], 1),
            'nnab': num(r['nna_brokerage_usdbn'], 1),
            'acq': num(r['acquired_nna'], 1),
            'cash': num(r['client_cash_usdbn'], 1),
            'cashp': num(r['cash_pct_assets'], 2, pct=True),
        })
    table = {
        'n': 20, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）',
        'idx': '月份', 'cols': tcols, 'rows': trows,
    }

    # ── 抬头 ──
    latest = df.iloc[-1]
    y_tot = (float(latest['total_assets_usdbn']) / float(df['total_assets_usdbn'].iloc[-13]) - 1) * 100
    y_cash = (float(latest['client_cash_usdbn']) / float(df['client_cash_usdbn'].iloc[-13]) - 1) * 100
    d_adv = float(latest['pct_advisory']) - float(df['pct_advisory'].iloc[-13])
    headline = (f"客户资产 ${float(latest['total_assets_usdbn']):,.1f}bn（{y_tot:+.1f}% y/y）"
                f" · 总 NNA ${float(latest['nna_total_usdbn']):,.1f}bn，"
                f"有机 ${float(latest['nna_ex']):,.1f}bn"
                f"（年化有机增速 {float(latest['organic_growth_ex']):.1f}%）"
                f" · 客户现金 ${float(latest['client_cash_usdbn']):,.1f}bn"
                f"（{y_cash:+.1f}% y/y，占资产 {float(latest['cash_pct_assets']):.2f}%）"
                f" · Advisory 占比 {float(latest['pct_advisory']):.2f}%（{d_adv:+.2f}pp y/y）")
    hub = (f"客户资产 ${float(latest['total_assets_usdbn'])/1000:.2f}tn（{y_tot:+.0f}% y/y）"
           f"、有机增速 {float(latest['organic_growth_ex']):.1f}%")

    payload = {
        'ticker': 'lpla',
        'tracker': 'LPLA Monthly Metrics Tracker',
        'title': f'LPL Financial Holdings (LPLA)：月度经营指标 — {LATEST.year} 年 {LATEST.month} 月',
        'data_through': str(LATEST),
        'through_label': f'{LATEST.year} 年 {LATEST.month} 月',
        'subtitle': ('LPL Financial 月度经营指标新闻稿 + 季报（季末月无独立月报）· '
                     f'覆盖 {df.index[0]} – {LATEST}（{len(df)} 个月）· '
                     '版式照 Goldman Sachs GIR「LPLA monthly metrics」系列'),
        'headline': headline,
        'hub_line': hub,
        'source': SRC,
        'xlabels': XL13,
        'xlabels_long': XLALL,
        'summary': summary,
        'exhibits': ex,
        'table': table,
        'notes': [
            '<b>数据源。</b>全部数值来自 <code>series/lpla.csv</code>（LPL Financial IR 月度经营指标'
            f'新闻稿，{df.index[0]} 起逐月连续）与 <code>series/fee_rates.csv</code>（LPLA 季度净收益率与'
            '季度实际客户现金收入）。页面不做任何计算，所有口径判断与格式化都在 '
            '<code>build/lpla.py</code> 里完成。',
            '<b>季末月口径。</b>' + QNOTE + '（3/6/9/12 月无独立月报，取自当季季报），'
            '因此这几个月的披露时点与其余月份不同，但口径一致。',
            '<b>⚠️ 2025 年 8 月并购断点。</b>' + BNOTE + '。凡是跨这一期读的图，'
            '都在该期柱的左缘画了红色竖虚线并标 M&A：从这一期起与左侧不可比。'
            '受影响的是 Exhibit 2、5、6、7、8、11、12、15。',
            '<b>有机口径与 Acquired NNA。</b>Exhibit 3/4/18/19 用的是有机 NNA = 总 NNA − '
            '公司同页披露的 Acquired NNA。该拆分自 2022 年起完整（Atria Oct-24 $88.3bn、'
            'Commonwealth Aug-25 $275.0bn 等），更早年份原件用旧行名、未解析，故未调整 —— '
            '2021 年 4 月 Waddell &amp; Reed 导入的 $73.8bn 仍留在有机序列里，'
            'Exhibit 18 的纵轴被它拉高。这张 Acquired NNA 常量表随原 deck 一并移植，'
            '不是 <code>series/lpla.csv</code> 的一列。',
            '<b>GS 规矩 1：流量不算百分比。</b>NNA 是流量，月度环比/同比百分比没有经济含义，'
            '汇总表里给的是绝对变化（$bn），趋势请读「年化有机增长率」= 当月 NNA × 12 / '
            '上月末客户资产。',
            '<b>GS 规矩 2：比率类差异用 pp / bp。</b>% Advisory、% of client assets、'
            '年化有机增速这三行的 m/m 与 y/y 都是百分点差；绝对值小于 1pp 时改用 bp。',
            '<b>推导值必须标 Implied。</b>Exhibit 13 的月度客户现金收入 = 月末客户现金 × '
            '公司披露的季度净收益率 ÷ 12，是<b>推导值</b>；Exhibit 6 的 Market gains 是恒等式'
            '配平项（当月资产变动 − 当月 NNA），同样不是披露值。Exhibit 14 把桥算出的季度值'
            f'与公司披露的实际值并排，窗口内平均绝对误差 {mae:.1f}% —— 误差主要来自'
            '「月末余额 vs 季度平均余额」这一个近似。',
            '<b>窗口。</b>近期柱图与双序列线图沿用原 deck 的 25 个月窗口，堆叠图与滚存桥用 13 个月，'
            '季度图用 14 个季度，长历史图用全序列。窗口一律从数据最新月倒推，不依赖构建当天的日期。',
            '<b>与原 PDF 的已知差异。</b>(1) 网页数值格式器只有一位小数的百分比（pct1），'
            '原 deck 里两位小数的比率图（Exhibit 10/16）在图上显示一位，两位数值见末尾核对表；'
            '(2) 原 deck 的 gsx.lvl_bar 在右轴画 y/y 折线，网页 gs_bar 画的是「最新月之前 12 个月」'
            '均线 + 右上角 y/y 气泡，数值同源；(3) 原 deck 长历史图末端的红色虚线圈没有网页等价元素。',
            '<b>核对表。</b>末尾 Exhibit 20 是官方原始单位、未做任何换算的近 13 个月明细，'
            '用来与 LPL 新闻稿逐条对账。每张图右上角的「表格」按钮同样给出该图的源数值。',
        ],
        'footer': ('数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
                   '仅供个人研究，不构成投资建议'),
    }

    path = os.path.join(ROOT, 'data', 'lpla.js')
    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(path, payload, 'lpla')

    print(f'数据截至 {LATEST} | 25 个月窗口 {W25.index[0]} → {W25.index[-1]} | '
          f'长历史 {df.index[0]} → {df.index[-1]}（{len(df)} 个月）')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）+ '
          f'Exhibit {table["n"]} 核对表')
    print(f'桥验证：{len(qs)} 个完整季度，平均绝对误差 {mae:.2f}%')
    print(f'写出 data/lpla.js ({os.path.getsize(path)/1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
