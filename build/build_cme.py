# -*- coding: utf-8 -*-
"""CME Group (CME) 月度成交量 —— GS Monthly + Barclays day-count 版式（仅图）。

模版来源：
  · Goldman Sachs「IBKR Monthly」成对图法（水平柱 + 12mo 均线 + YoY/MoM 气泡 ⇄ 变化率曲线）
    与 Exhibit 7「堆叠柱 + 次轴占比线」的量能/结构同框做法
  · Barclays「IBKR July Monthly Metrics」的 day-count 调整 —— 该报告因交易日数差异，
    把「股票成交总量 +7%」修正为「按日 -5%」，方向被口径反转。CME 官方 xlsx 里
    直接给了每月交易日数，故本 PDF 用 Exhibit 4 显式呈现总量口径与按日口径的差。
数据源：CME Group IR 月度成交量 xlsx（cmegroupinc.gcs-web.com/monthly-volume），次月第 1-2 个工作日。
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsx
import bridge

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser('~/Desktop')
SRC = 'Source: CME Group monthly volume reports; format after Goldman Sachs GIR / Barclays'

df = pd.read_csv(os.path.join(D, 'data', 'cme.csv'))
df['month'] = pd.PeriodIndex(df['month'], freq='M')
df = df.set_index('month').sort_index()

CLS = [('adv_rates_kcontracts', 'Interest rates', gsx.NAVY),
       ('adv_equity_kcontracts', 'Equity index', gsx.MBLUE),
       ('adv_energy_kcontracts', 'Energy', gsx.BLUE),
       ('adv_ag_kcontracts', 'Agricultural', gsx.GRAY),
       ('adv_fx_kcontracts', 'FX', gsx.GREEN),
       ('adv_metals_kcontracts', 'Metals', gsx.GOLD)]

adv = df['adv_total_kcontracts'].astype(float)
days = df['trading_days'].astype(float)
LATEST = adv.index[-1]

# 月度总成交量 = ADV x 当月交易日数（百万张）
df['total_vol_mn'] = adv * days / 1000.0
df['adv_mn'] = adv / 1000.0
df['oi_total_mn'] = df['oi_total_contracts'].astype(float) / 1e6
# day-count 效应：总量同比 vs 按日同比，两者之差即交易日数贡献
df['vol_yoy'] = df['total_vol_mn'].pct_change(12) * 100
df['adv_yoy'] = adv.pct_change(12) * 100
df['daycount_effect'] = df['vol_yoy'] - df['adv_yoy']
for c, _, _ in CLS:
    df[c] = df[c].astype(float)
df['rates_share'] = df['adv_rates_kcontracts'] / adv * 100


# ── 量→收入桥：交易收入 = 月成交合约数 x 每张平均费率（RPC）──
_rpc = bridge.rate_series('CME', 'rpc_total')                  # USD / contract
_rpc_m = bridge.to_monthly(_rpc, df.index)
df['implied_txn_rev_usdmn'] = df['total_vol_mn'] * _rpc_m
BR_NOTE = ('Assumption: monthly transaction revenue = contracts traded x average rate per contract '
           f'({_rpc.index[-1]} = ${_rpc.iloc[-1]:.3f}, held flat after). CME derives RPC from reported '
           'revenue, so closed quarters reconstruct a known total — the value is the current quarter.')
_rpc_df = pd.DataFrame({k: pd.Series(bridge.rate_series('CME', v).values,
                                     index=pd.PeriodIndex([q.asfreq('M', 'end') for q in bridge.rate_series('CME', v).index], freq='M'))
                        for k, v in [('rates', 'rpc_interest_rates'), ('equity', 'rpc_equity_indexes'),
                                     ('energy', 'rpc_energy'), ('metals', 'rpc_metals')]})


def fn(deck):
    gsx.summary_table(deck, df, [
        ('Average daily volume (k contracts)', None, None, None, None, None, None),
        (None, 'Total ADV', 'adv_total_kcontracts', 0, False, '', False),
        (None, 'Interest rates', 'adv_rates_kcontracts', 0, False, '', False),
        (None, 'Equity index', 'adv_equity_kcontracts', 0, False, '', False),
        (None, 'Energy', 'adv_energy_kcontracts', 0, False, '', False),
        (None, 'Agricultural', 'adv_ag_kcontracts', 0, False, '', False),
        (None, 'FX', 'adv_fx_kcontracts', 0, False, '', False),
        (None, 'Metals', 'adv_metals_kcontracts', 0, False, '', False),
        ('Volume and open interest', None, None, None, None, None, None),
        (None, 'Total contracts traded (mn)', 'total_vol_mn', 1, False, '', False),
        (None, 'Month-end open interest (mn)', 'oi_total_mn', 1, False, '', False),
        (None, 'Trading days', 'trading_days', 0, False, '', False),
    ], f'CME Group monthly volume summary — {gsx.mlab(LATEST)}', SRC,
        extra='ADV is already day-count neutral; total contracts traded is not. Exhibit 4 isolates the difference.')

    gsx.lvl_bar(deck, df['adv_mn'], 'Total average daily volume', SRC,
                win=25, dec=1, unit='mn contracts / day')

    # Barclays day-count 图：总量同比 vs 按日同比
    gsx.multi_line(deck, df, ['vol_yoy', 'adv_yoy'], [gsx.GRAY, gsx.NAVY],
                   'Total volume vs. ADV growth: the day-count gap', SRC, win=25,
                   dec=1, unit='% y/y',
                   names=['Total contracts y/y', 'ADV y/y (day-count neutral)'],
                   extra='Gap between the two lines is purely the change in trading days — the Barclays adjustment')

    # GS Exhibit 7 版式：结构 + 体量同框
    gsx.stack_share(deck, df, [c for c, _, _ in CLS], [col for _, _, col in CLS],
                    ['adv_rates_kcontracts', 'adv_equity_kcontracts'],
                    'ADV mix by asset class', SRC, win=13, dec=0,
                    unit='k contracts / day', share_label='% rates + equity (RHS)',
                    names=[n for _, n, _ in CLS])

    gsx.multi_line(deck, df, [c for c, _, _ in CLS], [col for _, _, col in CLS],
                   'ADV by asset class', SRC, win=25, dec=0, unit='k contracts / day',
                   names=[n for _, n, _ in CLS])

    gsx.long_line(deck, df['adv_mn'], 'Full ADV history since 2008', SRC, dec=1,
                  unit='mn contracts / day', circle=3,
                  extra='Full disclosed history; red ring = latest 3 months')

    gsx.qtr_bar(deck, df['total_vol_mn'], 'Contracts traded aggregated to quarters', SRC,
                win=14, unit='mn contracts', dec=0, label_dec=0)

    gsx.lvl_bar(deck, df['oi_total_mn'], 'Month-end total open interest', SRC,
                win=25, dec=1, unit='mn contracts')

    gsx.lvl_bar(deck, df['adv_rates_kcontracts'], 'Interest-rate complex ADV', SRC,
                win=25, dec=0, unit='k contracts / day')

    gsx.lvl_bar(deck, df['adv_equity_kcontracts'], 'Equity-index complex ADV', SRC,
                win=25, dec=0, unit='k contracts / day')

    gsx.lvl_bar(deck, df['adv_energy_kcontracts'], 'Energy complex ADV', SRC,
                win=25, dec=0, unit='k contracts / day')

    gsx.lvl_bar(deck, df['implied_txn_rev_usdmn'], 'Implied transaction revenue', SRC,
                win=25, dec=0, money='$', unit='$mn / month', extra=BR_NOTE)

    gsx.multi_line(deck, _rpc_df, ['rates', 'equity', 'energy', 'metals'],
                   [gsx.NAVY, gsx.MBLUE, gsx.BLUE, gsx.GOLD],
                   'Rate per contract by asset class', SRC, win=14, dec=3, money='$',
                   unit='$ per contract',
                   names=['Interest rates', 'Equity index', 'Energy', 'Metals'],
                   extra='RPC differs several-fold across complexes, so a volume mix shift moves blended revenue even when total ADV is flat. This is the main uncertainty in the bridge above.')

    gsx.lvl_bar(deck, df['adv_fx_kcontracts'], 'FX complex ADV', SRC, win=25, dec=0,
                unit='k contracts / day')

    gsx.lvl_bar(deck, df['adv_metals_kcontracts'], 'Metals complex ADV', SRC, win=25,
                dec=0, unit='k contracts / day')

    gsx.lvl_bar(deck, df['adv_ag_kcontracts'], 'Agricultural complex ADV', SRC, win=25,
                dec=0, unit='k contracts / day')

    gsx.heat_matrix(deck, df['adv_yoy'], 'Total ADV y/y growth (%)', SRC, dec=0,
                    n_years=10, extra='Green = faster y/y growth, red = slower')

    gsx.heat_matrix(deck, df['rates_share'], 'Interest-rate share of total ADV (%)', SRC,
                    dec=0, n_years=10,
                    extra='Rates is the largest and most rate-cycle-sensitive complex')


if __name__ == '__main__':
    path = os.path.join(OUT, f'CME 月度成交量跟踪_{LATEST}.pdf')
    gsx.build(path, 'CME Group (CME) — Monthly Volume Tracker',
              f'Data through {gsx.mlab(LATEST)}  ·  charts only, no commentary  ·  template after Goldman Sachs GIR / Barclays monthly-metrics notes',
              f'CME Group (CME)  ·  monthly volume reports  ·  built {gsx.today()}  ·  personal research use',
              fn)
    print('SAVED', path)
