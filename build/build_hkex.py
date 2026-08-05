# -*- coding: utf-8 -*-
"""HKEX 香港交易所 00388 月度市场统计 —— GS HKEX exhibit 版式（仅图）。

模版来源：Goldman Sachs「Hong Kong Exchanges (0388.HK): New listings and profit growth
          inflection to drive sustainable ADT growth」（Exhibit 1-15）与
          「Multiple tailwinds in 2026E despite weak Nov ADT」（Exhibit 1-28）。
          这两份的核心做法本 PDF 全部照搬：
   1) **三层时间窗**：超长历史判周期位置 / 中长期判趋势 / 近 13-18 个月讲当下；
   2) **双图开场**：整体 ADT 与南向 ADT 并列，末端打数据标签、最新点红圈；
   3) **驱动量置顶**：把 ADT / 衍生品张数这类经营量指标放在汇总表最上方，先于任何其他行。
数据源：HKEX Monthly Market Highlights（每月更新上一月）。
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsx
import bridge

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser('~/Desktop')
SRC = 'Source: HKEX Monthly Market Highlights; format after Goldman Sachs GIR'

df = pd.read_csv(os.path.join(D, 'data', 'hkex.csv'))
df['month'] = pd.PeriodIndex(df['month'], freq='M')
df = df.set_index('month').sort_index()
for c in df.columns:
    df[c] = pd.to_numeric(df[c], errors='coerce')

# 汇总表用「核心量指标已齐备」的最后一个月；衍生品等更新更快的序列在图上保留最新月
CORE = df['adt_hkdbn'].dropna()
LATEST = CORE.index[-1]
dfc = df.loc[:LATEST]

df['deriv_adv_k'] = df['derivatives_adv_contracts'] / 1000.0
dfc['deriv_adv_k'] = dfc['derivatives_adv_contracts'] / 1000.0
df['sb_share'] = df['southbound_adt_hkdbn'] / df['adt_hkdbn'] * 100
dfc['sb_share'] = dfc['southbound_adt_hkdbn'] / dfc['adt_hkdbn'] * 100
# 换手率代理：年化成交额 / 市值
df['velocity'] = df['adt_hkdbn'] * 252 / (df['mktcap_hkdtn'] * 1000) * 100
dfc['velocity'] = dfc['adt_hkdbn'] * 252 / (dfc['mktcap_hkdtn'] * 1000) * 100


# ── 量→收入桥：现货交易费 = 成交额 x 有效交易费率（双边）──
_tf_eff = bridge.rate_series('HKEX', 'trading_fee_effective_rate_both_sides')  # 由收入倒算
_tf_list = bridge.rate_series('HKEX', 'trading_fee_listed_rate_per_side') * 2   # 挂牌费率，双边
_tf = _tf_list                                                                  # 桥用挂牌费率
_td = bridge.rate_series('HKEX', 'trading_days')
_tf_m = bridge.to_monthly(_tf, df.index)
_td_q = bridge.to_monthly(_td, df.index)
df['implied_tradefee_hkdbn'] = df['adt_hkdbn'] * (_td_q / 3.0) * _tf_m / 100.0
BR_NOTE = ('Assumption: monthly cash trading-fee revenue = ADT x trading days x the statutory '
           'both-sides trading-fee rate published in the HKEX fee schedule (0.00565% per side). '
           'That rate is independent of reported revenue, so the bridge check below is a real test, '
           'not an identity.')
_imp_q = bridge.quarterly(df['implied_tradefee_hkdbn'])
_act_q = bridge.rate_series('HKEX', 'cash_seg_trading_fee_revenue', to='bn')
_ok = bridge.complete_quarters(df['implied_tradefee_hkdbn'])
_imp_q = _imp_q.loc[[q for q in _imp_q.index if q in _ok]]
_cf = bridge.rate_series('HKEX', 'clearing_fee_effective_rate_both_sides')
_cf_m = bridge.to_monthly(_cf, df.index)
df['implied_clearfee_hkdbn'] = df['adt_hkdbn'] * (_td_q / 3.0) * _cf_m / 100.0
CLR_NOTE = ('Assumption: monthly clearing-fee revenue = ADT x trading days x the effective both-sides '
            f'clearing rate ({_cf.index[-1]} = {_cf.iloc[-1]:.5f}%, held flat after). Unlike the trading '
            'fee, this rate is back-solved from revenue, so it is a now-cast rather than a test.')
_rate_df = pd.DataFrame({
    'eff': pd.Series(_tf_eff.values, index=pd.PeriodIndex([q.asfreq('M', 'end') for q in _tf_eff.index], freq='M')),
    'listed': pd.Series(_tf_list.values, index=pd.PeriodIndex([q.asfreq('M', 'end') for q in _tf_list.index], freq='M')),
})


def fn(deck):
    # GS Ex27 版式：经营量驱动指标置于表格最顶端，先于市值等存量
    gsx.summary_table(deck, dfc, [
        ('Cash market drivers', None, None, None, None, None, None),
        (None, 'Average daily turnover (HK$bn)', 'adt_hkdbn', 1, False, '', False),
        (None, 'Southbound ADT (HK$bn)', 'southbound_adt_hkdbn', 1, False, '', False),
        (None, 'Southbound share of ADT (%)', 'sb_share', 1, True, '', False),
        (None, 'Implied market velocity (%)', 'velocity', 1, True, '', False),
        ('Derivatives', None, None, None, None, None, None),
        (None, 'ADV of futures and options (k contracts)', 'deriv_adv_k', 0, False, '', False),
        ('Market size and primary market', None, None, None, None, None, None),
        (None, 'Securities market cap (HK$tn)', 'mktcap_hkdtn', 1, False, '', False),
        (None, 'New listings in the month', 'new_listings', 0, False, '', False, 'abs'),
        (None, 'IPO funds raised (HK$bn)', 'ipo_funds_hkdbn', 1, False, '', False),
    ], f'HKEX monthly market highlights — {gsx.mlab(LATEST)}', SRC,
        extra='Velocity is derived as ADT x 252 / market cap, not a disclosed figure. New-listing and IPO series have gaps in the published monthly summary.')

    # GS 双图开场
    gsx.lvl_bar(deck, df['adt_hkdbn'], 'Average daily turnover', SRC, win=25, dec=0,
                unit='HK$bn / day', show_mom=True)

    gsx.chg_line(deck, df['adt_hkdbn'], 'ADT, m/m change', SRC, win=25, kind='mom')

    # 超长历史层
    gsx.long_line(deck, df['adt_hkdbn'], 'Full ADT history since 2019', SRC, dec=0,
                  unit='HK$bn / day', circle=3,
                  extra='Full disclosed history; red ring = latest 3 months')

    gsx.multi_line(deck, df, ['adt_hkdbn', 'southbound_adt_hkdbn'],
                   [gsx.NAVY, gsx.MBLUE], 'Total vs. southbound turnover', SRC, win=25,
                   dec=0, unit='HK$bn / day',
                   names=['Total market ADT', 'Southbound ADT'],
                   extra='Southbound carries a lower fee take, so mix matters to revenue. Its 40-month publication gap (2022-2024) is why it is shown here and not as a bar chart')

    gsx.lvl_bar(deck, df['deriv_adv_k'], 'Derivatives average daily volume', SRC,
                win=25, dec=0, unit='k contracts / day')

    gsx.qtr_bar(deck, df['adt_hkdbn'].dropna(), 'ADT by quarter', SRC, win=14,
                unit='HK$bn / day', dec=0, label_dec=0, how='mean')

    gsx.lvl_bar(deck, df['mktcap_hkdtn'], 'Securities market capitalisation', SRC,
                win=25, dec=1, unit='HK$tn', show_mom=True)

    gsx.lvl_bar(deck, df['velocity'], 'Implied market velocity', SRC, win=25, dec=0,
                unit='% of market cap, annualised', pct_series=True,
                extra='ADT x 252 / market cap — the ratio GS uses to judge whether turnover is structurally higher')

    gsx.lvl_bar(deck, df['implied_tradefee_hkdbn'], 'Implied cash trading-fee revenue', SRC,
                win=25, dec=2, unit='HK$bn / month', extra=BR_NOTE)

    gsx.implied_vs_actual(deck, _imp_q, _act_q,
                          'Bridge check: statutory rate vs. reported fees', SRC,
                          dec=2, unit='HK$bn / quarter',
                          extra='The implied bar applies the published statutory rate to all turnover; the reported bar is the actual cash-segment trading-fee line. The gap is fee-exempt turnover (market makers, certain ETF and structured-product flow).')

    gsx.multi_line(deck, _rate_df, ['eff', 'listed'], [gsx.NAVY, gsx.GRAY],
                   'Fee capture: effective vs. statutory rate', SRC, win=14, dec=4,
                   unit='% of turnover, both sides',
                   names=['Effective (revenue / turnover)', 'Statutory schedule rate'],
                   extra='The persistent shortfall is the share of turnover that pays no trading fee. Watching this ratio is how you catch a mix shift before it shows up in revenue.')

    gsx.lvl_bar(deck, df['implied_clearfee_hkdbn'], 'Implied cash clearing-fee revenue',
                SRC, win=25, dec=2, unit='HK$bn / month', extra=CLR_NOTE)

    gsx.long_line(deck, df['deriv_adv_k'], 'Derivatives ADV history since 2019', SRC,
                  dec=0, unit='k contracts / day', circle=3)

    gsx.long_line(deck, df['mktcap_hkdtn'], 'Market capitalisation since 2019', SRC,
                  dec=0, unit='HK$tn', circle=3)

    gsx.year_lines(deck, df['adt_hkdbn'], 'ADT path by year', SRC, n_years=6,
                   cumulative=False, dec=0, unit='HK$bn / day')

    gsx.heat_matrix(deck, df['adt_hkdbn'], 'Average daily turnover (HK$bn)', SRC,
                    dec=0, n_years=8, extra='Green = heavier turnover')

    gsx.heat_matrix(deck, df['deriv_adv_k'], 'Derivatives ADV (k contracts / day)', SRC,
                    dec=0, n_years=8, extra='Green = heavier derivatives activity')


if __name__ == '__main__':
    path = os.path.join(OUT, f'HKEX 月度市场统计跟踪_{LATEST}.pdf')
    gsx.build(path, 'HKEX (0388.HK) — Monthly Market Statistics Tracker',
              f'Data through {gsx.mlab(LATEST)}  ·  charts only, no commentary  ·  template after Goldman Sachs GIR HKEX notes',
              f'Hong Kong Exchanges and Clearing (0388.HK)  ·  Monthly Market Highlights  ·  built {gsx.today()}  ·  personal research use',
              fn)
    print('SAVED', path)
