# -*- coding: utf-8 -*-
"""财富/券商组横截面：SCHW / LPLA / IBKR —— 三家在同一批指标上口径可比。

发布门槛：小组内所有成员的当月数据都出来之后才生成；脚本自动取**共同最新月**，
页脚注明各家自身更新到哪个月。

可比性说明（决定了每张图放哪几家）：
  · 客户资产：SCHW total client assets / LPLA total client assets / IBKR client equity —— 三家都有
  · 客户现金：LPLA client cash / IBKR client credits —— SCHW 未在月报中单列，故只两家
  · 融资余额：SCHW month-end margin / IBKR margin —— LPLA 不披露
  · 日均交易：SCHW DATs / IBKR DARTs —— LPLA 不披露
  · 有机增速：SCHW core NNA / LPLA organic NNA —— IBKR 不披露净新增资产，只披露净新增账户
IBKR 数据为只读引用自 ~/.claude/skills/IBKR月度指标 的官方历史指标 PDF，未改动该项目。
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsx

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser('~/Desktop')
SRC = 'Source: company monthly disclosures (Schwab Monthly Activity Report, LPL monthly metrics, IBKR brokerage metrics)'


def load(name):
    d = pd.read_csv(os.path.join(D, 'data', name))
    d['month'] = pd.PeriodIndex(d['month'], freq='M')
    return d.set_index('month').sort_index().apply(pd.to_numeric, errors='coerce')


schw, lpla, ibkr = load('schw.csv'), load('lpla.csv'), load('ibkr.csv')

# LPLA 有机口径（官方同页披露的 Acquired NNA，与单票报告保持一致）
ACQ = {'2023-01': 3.2, '2023-03': 0.5, '2024-04': 5.0, '2024-08': 0.3, '2024-09': 0.3,
       '2024-10': 88.3, '2024-11': 0.8, '2024-12': 0.3, '2025-01': 0.1, '2025-02': 0.7,
       '2025-03': 7.1, '2025-08': 275.0, '2025-12': 2.0}
acq = pd.Series({pd.Period(k, 'M'): v for k, v in ACQ.items()}).reindex(lpla.index).fillna(0.0)

LATEST_EACH = {'SCHW': schw.dropna(how='all').index[-1],
               'LPLA': lpla.dropna(how='all').index[-1],
               'IBKR': ibkr.dropna(how='all').index[-1]}
LATEST = min(LATEST_EACH.values())

df = pd.DataFrame({
    'schw_assets': schw['total_client_assets_usdbn'],
    'lpla_assets': lpla['total_assets_usdbn'],
    'ibkr_equity': ibkr['equity'],
    'lpla_cash': lpla['client_cash_usdbn'],
    'ibkr_cash': ibkr['credits'],
    'schw_margin': schw['margin_balances_usdbn'],
    'ibkr_margin': ibkr['margin'],
    'schw_dats': schw['dats_k'],
    'ibkr_darts': ibkr['darts'],
    'ibkr_accounts': ibkr['accounts'],
    'schw_new_accts': schw['new_brokerage_accounts_k'],
    'schw_nna': schw['core_nna_usdbn'],
    'lpla_nna_org': lpla['nna_total_usdbn'] - acq,
}).loc[:LATEST]

df['schw_org'] = df['schw_nna'] * 12 / df['schw_assets'].shift(1) * 100
df['lpla_org'] = df['lpla_nna_org'] * 12 / df['lpla_assets'].shift(1) * 100
df['ibkr_acct_growth'] = df['ibkr_accounts'].pct_change(12) * 100
for a, b in [('schw_assets', 'schw'), ('lpla_assets', 'lpla'), ('ibkr_equity', 'ibkr')]:
    df[b + '_assets_yoy'] = df[a].pct_change(12) * 100


def fn(deck):
    gsx.summary_table(deck, df, [
        ('Client assets ($bn) — same unit, directly comparable', None, None, None, None, None, None),
        (None, 'Schwab total client assets', 'schw_assets', 0, False, '$', False),
        (None, 'LPL total client assets', 'lpla_assets', 0, False, '$', False),
        (None, 'IBKR client equity', 'ibkr_equity', 0, False, '$', False),
        ('Organic growth (%, annualised)', None, None, None, None, None, None),
        (None, 'Schwab core NNA growth', 'schw_org', 2, True, '', False),
        (None, 'LPL organic NNA growth', 'lpla_org', 2, True, '', False),
        (None, 'IBKR account growth, y/y', 'ibkr_acct_growth', 1, True, '', False),
        ('Balance sheet ($bn)', None, None, None, None, None, None),
        (None, 'LPL client cash', 'lpla_cash', 1, False, '$', False),
        (None, 'IBKR client credits', 'ibkr_cash', 1, False, '$', False),
        (None, 'Schwab margin balances', 'schw_margin', 1, False, '$', False),
        (None, 'IBKR margin loans', 'ibkr_margin', 1, False, '$', False),
        ('Activity (k trades/day)', None, None, None, None, None, None),
        (None, 'Schwab DATs', 'schw_dats', 0, False, '', False),
        (None, 'IBKR cleared DARTs', 'ibkr_darts', 0, False, '', False),
    ], f'Wealth and brokerage group — {gsx.mlab(LATEST)}', SRC,
        extra='Schwab does not break out client cash in the monthly report and LPL discloses neither margin nor trades, so those rows carry only the two firms that publish them. IBKR reports no net new assets, so its growth line is account growth.')

    gsx.indexed_lines(deck, {'Schwab': df['schw_assets'], 'LPL': df['lpla_assets'],
                             'IBKR': df['ibkr_equity']},
                      'Client assets since 2018, rebased', SRC, base='2018-07',
                      extra='Rebased to 100 at Jul-2018. LPL includes its two acquisitions; the others do not')

    gsx.multi_line(deck, df, ['schw_assets_yoy', 'lpla_assets_yoy', 'ibkr_assets_yoy'],
                   [gsx.NAVY, gsx.RED, gsx.MBLUE], 'Client asset growth, y/y', SRC,
                   win=25, dec=0, unit='% y/y', names=['Schwab', 'LPL', 'IBKR'],
                   extra='LPL 2024-10 and 2025-08 spikes are the Atria and Commonwealth onboardings, not organic')

    gsx.multi_line(deck, df, ['schw_org', 'lpla_org'], [gsx.NAVY, gsx.RED],
                   'Annualised organic growth: Schwab vs. LPL', SRC, win=25, dec=1,
                   unit='% annualised', names=['Schwab core NNA', 'LPL organic NNA'],
                   extra='Both: monthly net new assets x 12 / prior month-end assets, LPL acquired assets stripped out')

    gsx.multi_line(deck, df, ['schw_margin', 'ibkr_margin'], [gsx.NAVY, gsx.MBLUE],
                   'Margin balances: Schwab vs. IBKR', SRC, win=25, dec=0, money='$',
                   unit='$bn', names=['Schwab month-end margin', 'IBKR margin loans'],
                   extra='LPL does not disclose margin. Schwab includes short credits, IBKR does not')

    gsx.multi_line(deck, df, ['lpla_cash', 'ibkr_cash'], [gsx.RED, gsx.MBLUE],
                   'Client cash: LPL vs. IBKR', SRC, win=25, dec=0, money='$', unit='$bn',
                   names=['LPL client cash', 'IBKR client credits'],
                   extra='Schwab does not break out client cash monthly. Both are the key net-interest-revenue driver')

    gsx.multi_line(deck, df, ['schw_dats', 'ibkr_darts'], [gsx.NAVY, gsx.MBLUE],
                   'Daily average trades: Schwab vs. IBKR', SRC, win=25, dec=0,
                   unit='k trades / day', names=['Schwab DATs', 'IBKR cleared DARTs'],
                   extra='Schwab DATs count client trades; IBKR DARTs are cleared commissionable orders — not identical')

    gsx.indexed_lines(deck, {'Schwab margin': df['schw_margin'], 'IBKR margin': df['ibkr_margin'],
                             'IBKR credits': df['ibkr_cash'], 'LPL cash': df['lpla_cash']},
                      'Balance-sheet items since 2019, rebased', SRC, base='2019-01',
                      colors=[gsx.NAVY, gsx.MBLUE, gsx.BLUE, gsx.RED],
                      extra='Rebased to 100 at Jan-2019. Margin is the cyclical item, client cash the rate-sensitive one')

    gsx.heat_matrix(deck, df['schw_assets_yoy'], 'Schwab client assets y/y (%)', SRC,
                    dec=0, n_years=7, extra='Green = faster growth')
    gsx.heat_matrix(deck, df['lpla_assets_yoy'], 'LPL client assets y/y (%)', SRC,
                    dec=0, n_years=7, extra='Green = faster growth; 2024-10 and 2025-08 carry acquisitions')
    gsx.heat_matrix(deck, df['ibkr_assets_yoy'], 'IBKR client equity y/y (%)', SRC,
                    dec=0, n_years=7, extra='Green = faster growth')


if __name__ == '__main__':
    lag = ' / '.join(f'{k} through {gsx.mlab(v)}' for k, v in LATEST_EACH.items())
    path = os.path.join(OUT, f'财富券商组 横截面_{LATEST}.pdf')
    gsx.build(path, 'Wealth & Brokerage Group — Schwab / LPL / IBKR Cross-Section',
              f'Common reporting month {gsx.mlab(LATEST)}  ·  charts only, no commentary  ·  gated on the slowest member of the group',
              f'{lag}  ·  built {gsx.today()}  ·  personal research use',
              fn)
    print('SAVED', path)
    print('共同最新月', LATEST, '| 各家:', {k: str(v) for k, v in LATEST_EACH.items()})
