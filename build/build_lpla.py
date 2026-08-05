# -*- coding: utf-8 -*-
"""LPL Financial (LPLA) 月度经营指标 —— GS「LPLA monthly metrics」exhibit 版式（仅图）。

模版来源：Goldman Sachs (Alexander Blostein 团队)「LPL Financial Holdings (LPLA):
          April metrics…」的 Exhibit 1，以及同系列 11 月期。该表的三条口径规矩本 PDF 全部照搬：
   1) **流量类（NNA）不算环比/同比百分比**，改用「年化有机增长率」= 当月 NNA x 12 / 上月末资产；
   2) **比率类差异一律用 bp / pp**，不用百分比变化；
   3) 存量分两个业务口径（Advisory / Brokerage）+ 加粗 Total + 斜体占比行。
   另采用 GS「SCHW First Take」Exhibit 2 的恒等式滚存桥（期初 + 净新增 + 市值变动 = 期末）。
数据源：LPL Financial IR 月度经营指标新闻稿。季末月（3/6/9/12）无独立月报，取自当季季报。

⚠️ 并购导入：2025 年 8 月 NNA 中含 Commonwealth Financial Network 约 2,850 亿美元资产导入，
   该月不是有机流入，图上以红色竖虚线标出。
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsx
import bridge

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser('~/Desktop')
SRC = 'Source: LPL Financial monthly activity and quarterly reports; format after Goldman Sachs GIR'
BREAK = pd.Period('2025-08', 'M')
BNOTE = 'Red dashed line = Aug-2025 Commonwealth onboarding (~$285bn); that month is not organic flow'
QNOTE = 'Quarter-end months have no standalone monthly report; those values come from the quarterly release'

df = pd.read_csv(os.path.join(D, 'data', 'lpla.csv'))
df['month'] = pd.PeriodIndex(df['month'], freq='M')
df = df.set_index('month').sort_index()
for c in df.columns:
    df[c] = pd.to_numeric(df[c], errors='coerce')

LATEST = df.index[-1]
tot = df['total_assets_usdbn']
nna = df['nna_total_usdbn']

df['pct_advisory'] = df['advisory_assets_usdbn'] / tot * 100
df['organic_growth_ann'] = nna * 12 / tot.shift(1) * 100
df['cash_pct_assets'] = df['client_cash_usdbn'] / tot * 100
df['market_gains'] = tot.diff() - nna
# 有机口径：把并购导入月整月剔除（不置 0，直接留空），否则有机增速序列被一根柱压扁
# 官方同页披露的 Acquired NNA（2022 年起完整；更早年份原件用旧行名，未解析，故不调整）
ACQ = {'2023-01': 3.2, '2023-03': 0.5, '2024-04': 5.0, '2024-08': 0.3, '2024-09': 0.3,
       '2024-10': 88.3, '2024-11': 0.8, '2024-12': 0.3, '2025-01': 0.1, '2025-02': 0.7,
       '2025-03': 7.1, '2025-08': 275.0, '2025-12': 2.0}
acq = pd.Series({pd.Period(k, 'M'): v for k, v in ACQ.items()}).reindex(df.index).fillna(0.0)
df['acquired_nna'] = acq
df['nna_ex'] = nna - acq                                   # 有机净新增
df['organic_growth_ex'] = df['nna_ex'] * 12 / tot.shift(1) * 100
df['total_tn'] = tot / 1000.0


# ── 量→收入桥：client cash revenue = 客户现金 x 净收益率 ──
_cy = bridge.rate_series('LPLA', 'client_cash_net_yield')      # bp, annualised
_cy_m = bridge.to_monthly(_cy, df.index)
df['implied_cash_rev_usdmn'] = df['client_cash_usdbn'] * 1000.0 * _cy_m / 10000.0 / 12.0
BR_NOTE = ('Assumption: monthly client-cash revenue = month-end client cash x the disclosed '
           'net yield / 12. ' + bridge.last_rate_note(_cy, 'bp', 'The yield'))
_imp_q = bridge.quarterly(df['implied_cash_rev_usdmn'])
_ok = bridge.complete_quarters(df['implied_cash_rev_usdmn'])
_imp_q = _imp_q.loc[[q for q in _imp_q.index if q in _ok]]
_act_q = bridge.rate_series('LPLA', 'client_cash_revenue', to='mn')


def fn(deck):
    # GS LPLA Exhibit 1 的行分组范式：存量 → 流量 → 结构
    gsx.summary_table(deck, df, [
        ('Assets ($bn)', None, None, None, None, None, None),
        (None, 'Advisory', 'advisory_assets_usdbn', 1, False, '', False),
        (None, 'Brokerage', 'brokerage_assets_usdbn', 1, False, '', False),
        (None, 'Total client assets', 'total_assets_usdbn', 1, False, '', False),
        (None, '% Advisory', 'pct_advisory', 1, True, '', False),
        ('Net new assets ($bn)', None, None, None, None, None, None),
        (None, 'Advisory NNA', 'nna_advisory_usdbn', 1, False, '', False, 'abs'),
        (None, 'Brokerage NNA', 'nna_brokerage_usdbn', 1, False, '', False, 'abs'),
        (None, 'Total NNA', 'nna_total_usdbn', 1, False, '', False, 'abs'),
        (None, 'Annualised organic growth (%)', 'organic_growth_ann', 2, True, '', False),
        ('Client cash ($bn)', None, None, None, None, None, None),
        (None, 'Client cash balances', 'client_cash_usdbn', 1, False, '', False),
        (None, '% of client assets', 'cash_pct_assets', 2, True, '', False),
    ], f'LPL Financial monthly metrics — {gsx.mlab(LATEST)}', SRC,
        extra='Per GS convention: flow items (NNA) show an absolute change rather than a percentage, and are read through the annualised organic growth line.  ' + QNOTE + '.')

    gsx.lvl_bar(deck, df['total_tn'], 'Total client assets', SRC, win=25, dec=2,
                money='$', unit='$tn', break_at=BREAK, break_label='M&A')

    gsx.lvl_bar(deck, df['nna_ex'], 'Organic net new assets', SRC,
                win=25, dec=1, money='$', unit='$bn',
                extra='Total NNA less the Acquired NNA that LPL discloses on the same page (Atria Oct-24 $88.3bn, Commonwealth Aug-25 $275.0bn)')

    gsx.lvl_bar(deck, df['organic_growth_ex'], 'Annualised organic growth rate', SRC,
                win=25, dec=1, unit='% annualised', pct_series=True,
                extra='Organic NNA x 12 / prior month-end assets, the GS convention; acquired assets stripped out using the disclosed split')

    gsx.stack_share(deck, df, ['advisory_assets_usdbn', 'brokerage_assets_usdbn'],
                    [gsx.NAVY, gsx.BLUE], ['advisory_assets_usdbn'],
                    'Client assets: advisory vs. brokerage', SRC, win=13, dec=0,
                    unit='$bn', share_label='% advisory (RHS)',
                    names=['Advisory', 'Brokerage'],
                    break_at=BREAK, break_label='M&A')

    gsx.bridge_bar(deck, df, ['nna_total_usdbn', 'market_gains'],
                   [gsx.NAVY, gsx.BLUE], ['Net new assets', 'Market gains (balancing)'],
                   'What moved client assets: flows vs. markets', SRC, win=13, dec=0,
                   money='$', unit='$bn change',
                   net_label='Total change in client assets',
                   extra='Identity: opening assets + NNA + market gains = closing assets.  ' + BNOTE)

    gsx.multi_line(deck, df, ['nna_advisory_usdbn', 'nna_brokerage_usdbn'],
                   [gsx.NAVY, gsx.RED], 'Net new assets by channel', SRC, win=25,
                   dec=1, money='$', unit='$bn',
                   names=['Advisory NNA', 'Brokerage NNA'],
                   break_at=BREAK, break_label='M&A',
                   extra='Brokerage NNA has been persistently negative — the advisory conversion is visible as a mirror image')

    gsx.long_line(deck, df['total_tn'], 'Total client assets since 2018', SRC, dec=1,
                  unit='$tn', circle=3, break_at=BREAK, break_label='M&A',
                  extra=BNOTE)

    gsx.lvl_bar(deck, df['client_cash_usdbn'], 'Client cash balances', SRC, win=25,
                dec=1, money='$', unit='$bn')

    gsx.lvl_bar(deck, df['cash_pct_assets'], 'Client cash as % of client assets', SRC,
                win=25, dec=2, unit='% of assets', pct_series=True,
                extra='Cash share is the key net-interest-revenue driver; a falling share is a headwind')

    gsx.qtr_bar(deck, nna, 'Net new assets by quarter', SRC, win=14, unit='$bn',
                dec=0, label_dec=0,
                extra='3Q25 includes the ~$285bn Commonwealth onboarding and is not comparable')

    gsx.lvl_bar(deck, df['advisory_assets_usdbn'], 'Advisory assets', SRC, win=25,
                dec=0, money='$', unit='$bn', break_at=BREAK, break_label='M&A')

    gsx.lvl_bar(deck, df['implied_cash_rev_usdmn'], 'Implied client-cash revenue', SRC,
                win=25, dec=0, money='$', unit='$mn / month', extra=BR_NOTE)

    gsx.implied_vs_actual(deck, _imp_q, _act_q,
                          'Bridge check: implied vs. reported client-cash revenue', SRC,
                          dec=0, money='$', unit='$mn / quarter',
                          extra='Reported = the client-cash revenue line in LPL results. The bridge applies the disclosed yield to MONTH-END cash while LPL earns it on AVERAGE cash — that proxy error is what this tests.')

    gsx.lvl_bar(deck, df['brokerage_assets_usdbn'], 'Brokerage assets', SRC, win=25,
                dec=0, money='$', unit='$bn', break_at=BREAK, break_label='M&A')

    gsx.lvl_bar(deck, df['pct_advisory'], 'Advisory share of client assets', SRC, win=25,
                dec=2, unit='% of assets', pct_series=True,
                extra='Advisory assets carry a higher payout-adjusted margin than brokerage, so the mix shift is a structural profit driver')

    gsx.long_line(deck, df['client_cash_usdbn'], 'Client cash since 2018', SRC, dec=0,
                  unit='$bn', circle=3)

    gsx.year_lines(deck, df['organic_growth_ex'], 'Organic growth path by year', SRC,
                   n_years=6, cumulative=False, dec=1, unit='% annualised')

    gsx.heat_matrix(deck, df['organic_growth_ex'], 'Annualised organic growth rate (%)',
                    SRC, dec=1, n_years=9,
                    extra='Green = faster organic asset gathering; acquired assets removed using the disclosed split (complete from 2022 onward)')


if __name__ == '__main__':
    path = os.path.join(OUT, f'LPLA 月度经营指标跟踪_{LATEST}.pdf')
    gsx.build(path, 'LPL Financial (LPLA) — Monthly Metrics Tracker',
              f'Data through {gsx.mlab(LATEST)}  ·  charts only, no commentary  ·  template after Goldman Sachs GIR LPLA monthly-metrics notes',
              f'LPL Financial Holdings (LPLA)  ·  monthly activity reports  ·  built {gsx.today()}  ·  personal research use',
              fn)
    print('SAVED', path)
