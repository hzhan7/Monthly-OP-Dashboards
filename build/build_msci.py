# -*- coding: utf-8 -*-
"""MSCI Inc. — 挂钩 MSCI 指数的 ETF 月度 AUM（GS Monthly exhibit 版式，仅图）。

模版来源：Goldman Sachs「Interactive Brokers Monthly」系列的成对图法
          （水平柱 + Prior-12mo-Avg 虚线 + YoY/MoM 椭圆气泡 ⇄ 变化率曲线），
          外加 GS HKEX 深度的超长历史层与 JPM AXP 的季节性/热力图型。
数据源：MSCI 官网 IR「AUM in ETFs Linked to MSCI Equity Indexes」，每月中旬更新上月。

口径提示：这是第三方 ETF 的资产规模（客户端产品），不是 MSCI 自身营收；
          但它由 MSCI 官方按月披露，且直接决定 asset-based fee 收入 ——
          该收入近似 = 季度平均 AUM x 基点费率，故 Exhibit 5 用季度平均而非期末值。
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsx
import bridge

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser('~/Desktop')
SRC = 'Source: MSCI IR, AUM in ETFs linked to MSCI equity indexes; format after Goldman Sachs GIR'

df = pd.read_csv(os.path.join(D, 'data', 'msci.csv'))
df['month'] = pd.PeriodIndex(df['month'], freq='M')
df = df.set_index('month').sort_index()

eop = df['aum_eop_usdbn'].astype(float)
avg = df['aum_avg_usdbn'].astype(float)
LATEST = eop.index[-1]

df['eop'] = eop
df['avg'] = avg
# 期末 vs 当月均值的差 —— 月内走势的方向指示（正=月末高于月均，即月内上行）
df['eop_less_avg'] = eop - avg
df['mom_pct'] = eop.pct_change() * 100


# ── 量→收入桥：asset-based fee = 平均 AUM x 有效基点费率 ──
_bp = bridge.rate_series('MSCI', 'asset_based_fee_effective_rate_annualized')  # bp
_bp_m = bridge.to_monthly(_bp, df.index)
df['implied_abf_usdmn'] = df['avg'] * 1000.0 * _bp_m / 10000.0 / 12.0
BR_NOTE = ('Assumption: monthly asset-based fee = month average AUM x the effective rate / 12 '
           f'({_bp.index[-1]} = {_bp.iloc[-1]:.3f}bp, held flat after). The rate is back-solved from '
           'reported revenue, so closed quarters are an allocation, not an estimate.')
_imp_q = bridge.quarterly(df['implied_abf_usdmn'])
_ok = bridge.complete_quarters(df['implied_abf_usdmn'])
_imp_q = _imp_q.loc[[q for q in _imp_q.index if q in _ok]]
_act_q = bridge.rate_series('MSCI', 'asset_based_fee_revenue', to='mn')
_bp_q = pd.Series(_bp.values, index=pd.PeriodIndex([q.asfreq('M', 'end') for q in _bp.index], freq='M'))


def fn(deck):
    gsx.summary_table(deck, df, [
        ('ETF AUM linked to MSCI indexes', None, None, None, None, None, None),
        (None, 'Month-end AUM ($bn)', 'eop', 1, False, '$', False),
        (None, 'Average AUM for the month ($bn)', 'avg', 1, False, '$', False),
        (None, 'Month-end less monthly average ($bn)', 'eop_less_avg', 1, False, '$', False),
    ], f'MSCI-linked ETF AUM summary — {gsx.mlab(LATEST)}', SRC,
        extra='Average AUM is the fee-relevant measure: asset-based fees accrue on average assets, not the month-end snapshot. All figures are MSCI estimates and include linked ETNs (<1% of AUM).')

    gsx.lvl_bar(deck, eop, 'Month-end AUM in MSCI-linked ETFs', SRC,
                win=25, dec=0, money='$', unit='$bn', show_mom=True)

    gsx.chg_line(deck, eop, 'Month-end AUM, m/m change', SRC, win=25, kind='mom')

    gsx.long_line(deck, eop, 'Full AUM history since 2008', SRC, dec=0,
                  unit='$bn', circle=3, break_at=pd.Period('2019-04', 'M'),
                  break_label='data provider switch',
                  extra='Before Apr-2019 the figures are MSCI estimates built on Bloomberg data; from May-2019 on Refinitiv data')

    # 季度平均 AUM —— asset-based fee 的直接驱动量
    gsx.qtr_bar(deck, avg, 'Quarterly average AUM (fee-relevant basis)', SRC,
                win=14, unit='$bn', dec=0, label_dec=0, how='mean',
                extra='Quarterly mean of the monthly average-AUM series; drives asset-based fee revenue')

    gsx.multi_line(deck, df, ['eop', 'avg'], [gsx.NAVY, gsx.MBLUE],
                   'Month-end vs. average AUM', SRC, win=25, dec=0, money='$',
                   unit='$bn', names=['Month-end AUM', 'Average AUM for month'])

    gsx.lvl_bar(deck, df['implied_abf_usdmn'], 'Implied asset-based fee revenue', SRC,
                win=25, dec=1, money='$', unit='$mn / month', extra=BR_NOTE)

    gsx.lvl_bar(deck, _bp_q, 'Effective asset-based fee rate', SRC, win=14, dec=2,
                unit='bp of average ETF AUM', pct_series=True,
                extra='Reported asset-based fee revenue / average MSCI-linked ETF AUM. This is the bridge\'s real '
                      'uncertainty: AUM compounded but the rate compressed from 3.9bp to 3.4bp in five '
                      'quarters. The period-end ETF fee of 2.28bp is lower as it also covers non-ETF licensing.')

    gsx.year_lines(deck, eop, 'AUM path by year', SRC, n_years=6, cumulative=False,
                   dec=0, money='$', unit='$bn')

    gsx.qtr_bar(deck, df['implied_abf_usdmn'], 'Implied asset-based fee by quarter', SRC,
                win=14, unit='$mn / quarter', dec=0, label_dec=0,
                extra='Quarterly sum of the monthly bridge; the latest bar is quarter-to-date if the quarter is incomplete')

    gsx.long_line(deck, avg, 'Average AUM since 2008', SRC, dec=0, unit='$bn', circle=3,
                  break_at=pd.Period('2019-04', 'M'), break_label='data provider switch')

    gsx.chg_line(deck, df['implied_abf_usdmn'], 'Implied fee revenue, y/y', SRC, win=25,
                 kind='yoy',
                 extra='Grows more slowly than AUM because the effective rate has been compressing')

    gsx.heat_matrix(deck, df['mom_pct'], 'Month-end AUM m/m change (%)', SRC,
                    dec=1, n_years=11,
                    extra='Green = AUM rose, red = AUM fell')


if __name__ == '__main__':
    path = os.path.join(OUT, f'MSCI 月度ETF AUM跟踪_{LATEST}.pdf')
    gsx.build(path, 'MSCI Inc. — Monthly ETF AUM Tracker',
              f'Data through {gsx.mlab(LATEST)}  ·  charts only, no commentary  ·  template after Goldman Sachs GIR monthly-metrics notes',
              f'MSCI Inc. (MSCI)  ·  AUM in ETFs linked to MSCI equity indexes  ·  built {gsx.today()}  ·  personal research use',
              fn)
    print('SAVED', path)
