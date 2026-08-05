# -*- coding: utf-8 -*-
"""Cboe Global Markets (CBOE) 月度成交量与 RPC —— GS Monthly exhibit 版式（仅图）。

模版来源：Goldman Sachs「IBKR Monthly」的成对图法与 Exhibit 6-9 的「量 x 价」处理 ——
          GS 对券商永远同时画「量」(DARTs) 与「单位价格」(CPT)，再用二者乘积画收入/日。
          Cboe 是全清单里唯一官方同时披露 ADV 与 RPC 的标的，因此这套量价框架可以
          完整复刻：ADV x RPC = 每日交易净收入的直接估算。
数据源：Cboe 官网 Monthly volume and revenue per contract (RPC) reports，次月第 3 个工作日。
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsx

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser('~/Desktop')
SRC = 'Source: Cboe monthly volume and RPC reports; format after Goldman Sachs GIR'

df = pd.read_csv(os.path.join(D, 'data', 'cboe.csv'))
df['month'] = pd.PeriodIndex(df['month'], freq='M')
df = df.set_index('month').sort_index()
for c in df.columns:
    df[c] = pd.to_numeric(df[c], errors='coerce')

LATEST = df.index[-1]
LATEST_RPC = df['rpc_us_options_usd'].dropna().index[-1]

# 量 x 价 = 每日交易净收入估算（仅美国期权口径，$mn/day）
df['opt_rev_day_usdmn'] = df['adv_us_options_kcontracts'] * df['rpc_us_options_usd'] / 1000.0
df['idx_rev_day_usdmn'] = df['adv_index_options_kcontracts'] * df['rpc_index_options_usd'] / 1000.0
df['adv_us_options_mn'] = df['adv_us_options_kcontracts'] / 1000.0
df['adv_index_options_mn'] = df['adv_index_options_kcontracts'] / 1000.0
df['adv_spx_mn'] = df['adv_spx_options_kcontracts'] / 1000.0
df['adv_vix_opt_mn'] = df['adv_vix_options_kcontracts'] / 1000.0
df['adv_xsp_mn'] = df['adv_xsp_options_kcontracts'] / 1000.0
df['adv_multilist_mn'] = df['adv_multilist_options_kcontracts'] / 1000.0
df['index_share'] = df['adv_index_options_kcontracts'] / df['adv_us_options_kcontracts'] * 100
df['spx_share'] = df['adv_spx_options_kcontracts'] / df['adv_index_options_kcontracts'] * 100


def fn(deck):
    gsx.summary_table(deck, df, [
        ('U.S. options ADV (k contracts/day)', None, None, None, None, None, None),
        (None, 'Total U.S. options', 'adv_us_options_kcontracts', 0, False, '', False),
        (None, 'Index options (proprietary)', 'adv_index_options_kcontracts', 0, False, '', False),
        (None, '  of which SPX', 'adv_spx_options_kcontracts', 0, False, '', False),
        (None, '  of which VIX options', 'adv_vix_options_kcontracts', 0, False, '', False),
        (None, 'Multiply-listed options', 'adv_multilist_options_kcontracts', 0, False, '', False),
        ('Other franchises', None, None, None, None, None, None),
        (None, 'Futures ADV (k contracts/day)', 'adv_futures_kcontracts', 0, False, '', False),
        (None, 'U.S. equities matched (bn shares/day)', 'adv_us_equities_matched_shares_bn', 2, False, '', False),
        (None, 'European equities ADNV (EUR bn/day)', 'adv_eu_equities_adnv_eurbn', 1, False, '', False),
        (None, 'Global FX ADNV ($bn/day)', 'adv_fx_adnv_usdbn', 1, False, '', False),
        ('Revenue per contract ($)', None, None, None, None, None, None),
        (None, 'U.S. options RPC', 'rpc_us_options_usd', 3, False, '$', False),
        (None, 'Index options RPC', 'rpc_index_options_usd', 3, False, '$', False),
        (None, 'Multiply-listed options RPC', 'rpc_multilist_options_usd', 3, False, '$', False),
    ], f'Cboe monthly volume and RPC summary — {gsx.mlab(LATEST)}', SRC,
        extra=f'Volume through {gsx.mlab(LATEST)}; RPC through {gsx.mlab(LATEST_RPC)} — RPC is a three-month rolling average published on a one-month lag, so blank RPC cells are not a data gap. 2017 figures are Bats pro-forma combined.')

    gsx.lvl_bar(deck, df['adv_us_options_mn'], 'Total U.S. options ADV', SRC,
                win=25, dec=1, unit='mn contracts / day')

    # GS 量价对：RPC 单独成图
    gsx.multi_line(deck, df, ['rpc_us_options_usd', 'rpc_index_options_usd',
                              'rpc_multilist_options_usd'],
                   [gsx.NAVY, gsx.MBLUE, gsx.BLUE], 'Revenue per contract by book', SRC,
                   win=25, dec=3, money='$', unit='$ per contract',
                   names=['All U.S. options', 'Index (proprietary)', 'Multiply-listed'],
                   extra='RPC is a three-month rolling average published on a one-month lag, not a single-month figure. Index options carry roughly 10x the RPC of multiply-listed')

    # 量 x 价 = 每日交易收入
    gsx.lvl_bar(deck, df['opt_rev_day_usdmn'].dropna(),
                'Implied options transaction revenue per day', SRC,
                win=25, dec=2, money='$', unit='$mn / day',
                extra='Current-month ADV x three-month rolling RPC. Cboe is the only name in this set where BOTH inputs are officially disclosed monthly, so no quarterly rate has to be assumed — but the RPC is a three-month average, so the result is smoothed.')

    # 结构：自有指数期权 vs 多重挂牌
    gsx.stack_share(deck, df, ['adv_index_options_kcontracts', 'adv_multilist_options_kcontracts'],
                    [gsx.NAVY, gsx.BLUE], ['adv_index_options_kcontracts'],
                    'U.S. options mix: proprietary index vs. multiply-listed', SRC,
                    win=13, dec=0, unit='k contracts / day',
                    share_label='% index (RHS)',
                    names=['Index options (proprietary)', 'Multiply-listed options'])

    gsx.long_line(deck, df['adv_us_options_mn'], 'Full U.S. options ADV history since 2017',
                  SRC, dec=1, unit='mn contracts / day', circle=3,
                  extra='Full disclosed history; red ring = latest 3 months')

    # Cboe 只单列这三个指数期权产品（另有 VIX / Mini VIX 期货，属期货不属期权）
    gsx.multi_line(deck, df, ['adv_spx_mn', 'adv_vix_opt_mn', 'adv_xsp_mn'],
                   [gsx.NAVY, gsx.RED, gsx.GREEN],
                   'Proprietary index options ADV by product', SRC, win=25, dec=2,
                   unit='mn contracts / day',
                   names=['SPX options', 'VIX options', 'XSP options (Mini-SPX)'],
                   log=True,
                   extra='The only three index option products Cboe breaks out (XSP from Jan-2019). Log scale: XSP is a fraction of SPX in absolute terms but has grown fastest')

    gsx.qtr_bar(deck, df['adv_us_options_mn'], 'U.S. options ADV by quarter', SRC,
                win=14, unit='mn contracts / day', dec=1, label_dec=1, how='mean')

    gsx.multi_line(deck, df, ['adv_us_equities_matched_shares_bn', 'adv_eu_equities_adnv_eurbn',
                              'adv_fx_adnv_usdbn'],
                   [gsx.NAVY, gsx.MBLUE, gsx.GREEN], 'Non-options franchises', SRC,
                   win=25, dec=1, unit='mixed units',
                   names=['U.S. equities (bn shares/day)', 'European equities (EURbn/day)',
                          'Global FX ($bn/day)'],
                   extra='Three different units on one axis — read levels within each series, not across')

    gsx.lvl_bar(deck, df['adv_futures_kcontracts'], 'Futures (CFE) ADV', SRC, win=25,
                dec=0, unit='k contracts / day', show_mom=True)

    gsx.lvl_bar(deck, df['adv_eu_equities_adnv_eurbn'], 'European equities ADNV', SRC,
                win=25, dec=1, unit='EUR bn / day')

    gsx.heat_matrix(deck, df['index_share'], 'Index options share of U.S. options ADV (%)',
                    SRC, dec=0, n_years=10,
                    extra='Green = richer mix (index options earn far higher RPC)')


if __name__ == '__main__':
    path = os.path.join(OUT, f'CBOE 月度成交量与RPC跟踪_{LATEST}.pdf')
    gsx.build(path, 'Cboe Global Markets (CBOE) — Monthly Volume & RPC Tracker',
              f'Data through {gsx.mlab(LATEST)}  ·  charts only, no commentary  ·  template after Goldman Sachs GIR monthly-metrics notes',
              f'Cboe Global Markets (CBOE)  ·  monthly volume and RPC reports  ·  built {gsx.today()}  ·  personal research use',
              fn)
    print('SAVED', path)
