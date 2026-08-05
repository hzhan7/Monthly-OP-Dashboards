# -*- coding: utf-8 -*-
"""Charles Schwab (SCHW) 月度 Activity Report —— GS 版式（仅图）。

模版来源：
  · Goldman Sachs「SCHW First Take」Exhibit 2 的双面板月度差异表与**恒等式滚存桥**
    （期初 BOP + 净新增 + 市值变动 = 期末 EOP）—— 让月度数据可无损累加到季度，
    是「用月度抢跑季报」的地基，本 PDF 的 Exhibit 4 即此图。
  · Goldman Sachs「LPLA monthly metrics」Exhibit 1 的口径规矩：**流量类不算环比百分比，
    改用年化有机增长率**（当月净新增 x 12 / 上月末资产），本 PDF Exhibit 3 采用。
  · GS「IBKR Monthly」的成对图法（水平柱 + 12mo 均线 + YoY/MoM 气泡 ⇄ 变化率曲线）。
数据源：Schwab Monthly Activity Report（次月 12-14 日）；季末月（3/6/9/12）无独立月报，
        该月数值取自当季季报，故序列连续。
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsx
import bridge

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser('~/Desktop')
SRC = 'Source: Schwab Monthly Activity Reports and quarterly reports'
QNOTE = 'Quarter-end months (Mar/Jun/Sep/Dec) have no standalone monthly report; those values come from the quarterly release'

df = pd.read_csv(os.path.join(D, 'data', 'schw.csv'))
df['month'] = pd.PeriodIndex(df['month'], freq='M')
df = df.set_index('month').sort_index()
for c in df.columns:
    df[c] = pd.to_numeric(df[c], errors='coerce')

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
# 2020-10 新开经纪账户 14,718k 系 TD Ameritrade 收购一次性并表，会把分布图整个压平
avgm = pd.read_csv(os.path.join(D, 'data', 'schw_avg_margin.csv'))
avgm['month'] = pd.PeriodIndex(avgm['month'], freq='M')
avgm = avgm.set_index('month').sort_index()['avg_margin_balances_usdbn']

df['new_acct_ex'] = df['new_brokerage_accounts_k'].copy()
df.loc[pd.Period('2020-10', 'M'), 'new_acct_ex'] = np.nan


# ── 为什么 SCHW 没有「量→收入」桥 ──
# Schwab 月报既不披露客户现金也不披露生息资产，唯一能当代理的是客户资产；
# 但生息资产/客户资产的比值 10 个季度从 4.9% 单边降到 3.4%（趋势，不是噪音），
# 把它当常数会造出假精度。所以这里不搭桥，改把这个比值本身画出来 —— 它本身就是
# NII 增长受限的原因。
_iea = bridge.rate_series('SCHW', 'avg_interest_earning_assets', to='bn')
_nim = bridge.rate_series('SCHW', 'net_interest_margin')
_ca_q = df['total_client_assets_usdbn'].groupby(df.index.asfreq('Q')).mean()
_ratio = (_iea / _ca_q.reindex(_iea.index) * 100).dropna()
_bs = pd.DataFrame({
    'iea_share': pd.Series(_ratio.values, index=pd.PeriodIndex([q.asfreq('M', 'end') for q in _ratio.index], freq='M')),
    'nim': pd.Series(_nim.reindex(_ratio.index).values, index=pd.PeriodIndex([q.asfreq('M', 'end') for q in _ratio.index], freq='M')),
})


def fn(deck):
    gsx.summary_table(deck, df, [
        ('Client assets and flows', None, None, None, None, None, None),
        (None, 'Total client assets ($bn)', 'total_client_assets_usdbn', 0, False, '$', False),
        (None, 'Core net new assets ($bn)', 'core_nna_usdbn', 1, False, '$', False),
        (None, 'Annualised organic growth (%)', 'organic_growth_ann', 2, True, '', False),
        (None, 'Market gains, balancing item ($bn)', 'market_gains', 0, False, '$', False, 'abs'),
        ('Activity', None, None, None, None, None, None),
        (None, 'New brokerage accounts (k)', 'new_brokerage_accounts_k', 0, False, '', False),
        (None, 'Daily average trades (k)', 'dats_k', 0, False, '', False),
        (None, 'Margin balances ($bn)', 'margin_balances_usdbn', 1, False, '$', False),
    ], f'Schwab monthly activity summary — {gsx.mlab(LATEST)}', SRC,
        extra=QNOTE + '.  Core NNA is a flow, read through the annualised organic growth line per GS convention.  The core-NNA exclusion threshold moved from $10bn to $25bn in 2025.  Margin balances include short credits.')

    gsx.lvl_bar(deck, nna, 'Core net new assets', SRC, win=25, dec=1, money='$',
                unit='$bn', show_mom=True, extra=QNOTE)

    # 流量不算 %，改用年化有机增速
    gsx.lvl_bar(deck, df['organic_growth_ann'], 'Annualised organic growth rate', SRC,
                win=25, dec=1, unit='% annualised', pct_series=True,
                extra='Monthly core NNA x 12 / prior month-end client assets')

    # GS SCHW Exhibit 2 的恒等式滚存桥
    gsx.bridge_bar(deck, df, ['core_nna_usdbn', 'market_gains'],
                   [gsx.NAVY, gsx.BLUE], ['Core net new assets', 'Market gains (balancing)'],
                   'What moved client assets: flows vs. markets', SRC, win=13, dec=0,
                   money='$', unit='$bn change',
                   net_label='Total change in client assets',
                   extra='Identity: opening assets + core NNA + market gains = closing assets')

    gsx.lvl_bar(deck, df['assets_tn'], 'Total client assets', SRC, win=25, dec=2,
                money='$', unit='$tn')

    gsx.lvl_bar(deck, df['new_brokerage_accounts_k'], 'New brokerage accounts opened', SRC,
                win=25, dec=0, unit='k accounts', extra=QNOTE)

    gsx.long_line(deck, df['assets_tn'], 'Total client assets since 2018', SRC, dec=1,
                  unit='$tn', circle=3,
                  extra='Full assembled history; red ring = latest 3 months')

    gsx.lvl_bar(deck, df['dats_mn'], 'Daily average trades', SRC, win=25, dec=1,
                unit='mn trades / day', show_mom=True,
                extra='Client DATs first appear in the Jan-2026 report; the 13-month rolling table reaches back to Jan-2025, so the y/y line starts Jan-2026')

    gsx.lvl_bar(deck, df['margin_balances_usdbn'], 'Month-end margin balances', SRC,
                win=25, dec=0, money='$', unit='$bn', show_mom=True,
                extra='Schwab only began disclosing month-end margin balances in the Jan-2026 report; its 13-month rolling table reaches back to Jan-2025, so the y/y line starts Jan-2026')

    gsx.long_line(deck, avgm, 'Average margin balances since 2020', SRC, dec=0,
                  unit='$bn (monthly average)', circle=3,
                  extra='Different basis from Exhibit 9: this is the average-balance line Schwab published Apr-2020 to Dec-2025 and then dropped. It is the only long monthly margin history that exists.')

    gsx.qtr_bar(deck, nna, 'Core net new assets by quarter', SRC, win=14,
                unit='$bn', dec=0, label_dec=0)

    gsx.chg_line(deck, df['margin_balances_usdbn'], 'Margin balances, m/m change', SRC,
                 win=25, kind='mom')

    gsx.multi_line(deck, _bs, ['iea_share', 'nim'], [gsx.NAVY, gsx.RED],
                   'Why there is no revenue bridge here', SRC, win=14, dec=2, unit='%',
                   names=['Interest-earning assets / client assets', 'Net interest margin'],
                   extra='Neither client cash nor interest-earning assets is published monthly. The only monthly proxy is client assets, and that ratio fell from 4.9% to 3.4% in ten quarters — treating it as a constant would be false precision. Both series are quarterly.')

    gsx.long_line(deck, nna, 'Core net new assets since 2018', SRC, dec=0, money='$',
                  unit='$bn', circle=3, extra=QNOTE)

    gsx.long_line(deck, df['new_brokerage_accounts_k'], 'New brokerage accounts since 2018',
                  SRC, dec=0, unit='k accounts', circle=3, clip_at=1600,
                  extra='Axis capped at 1,600k so the series is readable. The Oct-2020 reading of '
                        '14,718k is the TD Ameritrade onboarding — a balance transfer, not accounts '
                        'opened. Shown in red, not removed.')

    gsx.year_lines(deck, nna, 'Core NNA path by year', SRC, n_years=6, cumulative=False,
                   dec=0, money='$', unit='$bn')

    gsx.year_lines(deck, df['new_acct_ex'], 'New accounts path by year', SRC, n_years=6,
                   cumulative=False, dec=0, unit='k accounts',
                   extra='Oct-2020 excluded (TD Ameritrade onboarding)')

    gsx.heat_matrix(deck, df['organic_growth_ann'], 'Annualised organic growth rate (%)',
                    SRC, dec=1, n_years=9,
                    extra='Green = faster organic asset gathering')


if __name__ == '__main__':
    path = os.path.join(OUT, f'SCHW 月度经营指标跟踪_{LATEST}.pdf')
    gsx.build(path, 'Charles Schwab (SCHW) — Monthly Activity Tracker',
              f'Data through {gsx.mlab(LATEST)}  ·  charts only, no commentary  ·  template after Goldman Sachs GIR monthly-metrics notes',
              f'Charles Schwab (SCHW)  ·  Monthly Activity Report  ·  built {gsx.today()}  ·  personal research use',
              fn)
    print('SAVED', path)
