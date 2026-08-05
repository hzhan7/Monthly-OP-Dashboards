# -*- coding: utf-8 -*-
"""交易所组横截面：CME / CBOE / HKEX —— 只回答单份报告答不了的问题「谁在跑赢」。

发布门槛：小组内所有成员的当月数据都出来之后才生成。脚本自动取三家的**共同最新月**，
并在标题与页脚注明哪家是短板、其自身更新到哪个月。

口径提醒：三家的成交量单位不可直接相加（CME/CBOE 是合约张数、HKEX 是成交金额），
所以本报告一律用**指数化**与**同比**做比较，不做绝对量的横向加总。
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsx

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser('~/Desktop')
SRC = 'Source: company monthly volume reports (CME, Cboe, HKEX); format after Goldman Sachs GIR'


def load(name):
    d = pd.read_csv(os.path.join(D, 'data', name))
    d['month'] = pd.PeriodIndex(d['month'], freq='M')
    return d.set_index('month').sort_index().apply(pd.to_numeric, errors='coerce')


cme, cboe, hkex = load('cme.csv'), load('cboe.csv'), load('hkex.csv')

VOL = {
    'CME (total ADV, k contracts)': cme['adv_total_kcontracts'],
    'Cboe (U.S. options ADV, k contracts)': cboe['adv_us_options_kcontracts'],
    'HKEX (cash ADT, HK$bn)': hkex['adt_hkdbn'],
}
LATEST_EACH = {k: v.dropna().index[-1] for k, v in VOL.items()}
LATEST = min(LATEST_EACH.values())                    # 共同最新月 = 发布门槛
LAG = [k.split(' (')[0] for k, v in LATEST_EACH.items() if v == LATEST]

# 统一到共同最新月，避免某家多一个月造成横向不可比
df = pd.DataFrame({
    'cme_adv': cme['adv_total_kcontracts'],
    'cboe_adv': cboe['adv_us_options_kcontracts'],
    'hkex_adt': hkex['adt_hkdbn'],
    'cme_oi': cme['oi_total_contracts'] / 1e6,
    'cboe_index_share': cboe['adv_index_options_kcontracts'] / cboe['adv_us_options_kcontracts'] * 100,
    'cme_rates_share': cme['adv_rates_kcontracts'] / cme['adv_total_kcontracts'] * 100,
    'hkex_deriv': hkex['derivatives_adv_contracts'] / 1000.0,
}).loc[:LATEST]

for c, src_ in [('cme_adv', 'cme_adv'), ('cboe_adv', 'cboe_adv'), ('hkex_adt', 'hkex_adt')]:
    df[c + '_yoy'] = df[src_].pct_change(12) * 100


def fn(deck):
    gsx.summary_table(deck, df, [
        ('Volume (each in its own unit — not additive)', None, None, None, None, None, None),
        (None, 'CME total ADV (k contracts/day)', 'cme_adv', 0, False, '', False),
        (None, 'Cboe U.S. options ADV (k contracts/day)', 'cboe_adv', 0, False, '', False),
        (None, 'HKEX cash ADT (HK$bn/day)', 'hkex_adt', 0, False, '', False),
        ('Growth (%, y/y)', None, None, None, None, None, None),
        (None, 'CME', 'cme_adv_yoy', 1, True, '', False),
        (None, 'Cboe', 'cboe_adv_yoy', 1, True, '', False),
        (None, 'HKEX', 'hkex_adt_yoy', 1, True, '', False),
        ('Mix and open interest', None, None, None, None, None, None),
        (None, 'CME interest-rate share of ADV (%)', 'cme_rates_share', 1, True, '', False),
        (None, 'Cboe index-option share of U.S. options (%)', 'cboe_index_share', 1, True, '', False),
        (None, 'CME month-end open interest (mn contracts)', 'cme_oi', 1, False, '', False),
        (None, 'HKEX derivatives ADV (k contracts/day)', 'hkex_deriv', 0, False, '', False),
    ], f'Exchange group — {gsx.mlab(LATEST)}', SRC,
        extra='Volumes are in different units and must not be added or ranked against each other in levels; the comparison below is done on growth and on rebased indices.')

    gsx.indexed_lines(deck, {'CME': df['cme_adv'], 'Cboe': df['cboe_adv'], 'HKEX': df['hkex_adt']},
                      'Volume growth since 2019, rebased', SRC, base='2019-01',
                      extra='Rebased to 100 at Jan-2019, the first month all three disclose. Compares growth only — the three units are not comparable in levels')

    gsx.multi_line(deck, df, ['cme_adv_yoy', 'cboe_adv_yoy', 'hkex_adt_yoy'],
                   [gsx.NAVY, gsx.RED, gsx.MBLUE], 'Volume growth, y/y', SRC, win=25,
                   dec=0, unit='% y/y', names=['CME', 'Cboe', 'HKEX'])

    gsx.multi_line(deck, df, ['cme_adv_yoy', 'cboe_adv_yoy', 'hkex_adt_yoy'],
                   [gsx.NAVY, gsx.RED, gsx.MBLUE], 'Volume growth, y/y — full window', SRC,
                   win=len(df), dec=0, unit='% y/y', names=['CME', 'Cboe', 'HKEX'],
                   extra='Same three series over the whole common history; shows whether the current ranking is a new development or the standing order')

    gsx.multi_line(deck, df, ['cme_rates_share', 'cboe_index_share'],
                   [gsx.NAVY, gsx.RED], 'Mix quality: high-fee share of volume', SRC,
                   win=25, dec=1, unit='% of own volume',
                   names=['CME: rates share of ADV', 'Cboe: index-option share'],
                   extra='Both are the highest-value product inside each franchise, so a rising share lifts blended revenue per unit of volume')

    gsx.indexed_lines(deck, {'CME open interest': df['cme_oi'], 'HKEX derivatives ADV': df['hkex_deriv'],
                             'Cboe U.S. options ADV': df['cboe_adv']},
                      'Derivatives franchises, rebased', SRC, base='2019-01',
                      extra='Rebased to 100 at Jan-2019. CME open interest is a stock, the other two are flows — read the slopes, not the crossings')

    gsx.heat_matrix(deck, df['cme_adv_yoy'], 'CME total ADV y/y (%)', SRC, dec=0, n_years=8,
                    extra='Green = faster growth')
    gsx.heat_matrix(deck, df['cboe_adv_yoy'], 'Cboe U.S. options ADV y/y (%)', SRC, dec=0, n_years=8,
                    extra='Green = faster growth')
    gsx.heat_matrix(deck, df['hkex_adt_yoy'], 'HKEX cash ADT y/y (%)', SRC, dec=0, n_years=8,
                    extra='Green = faster growth')


if __name__ == '__main__':
    lag_txt = ' / '.join(f'{k.split(" (")[0]} through {gsx.mlab(v)}' for k, v in LATEST_EACH.items())
    path = os.path.join(OUT, f'交易所组 横截面_{LATEST}.pdf')
    gsx.build(path, 'Exchange Group — CME / Cboe / HKEX Cross-Section',
              f'Common reporting month {gsx.mlab(LATEST)}  ·  charts only, no commentary  ·  gated on the slowest member of the group',
              f'{lag_txt}  ·  built {gsx.today()}  ·  personal research use',
              fn)
    print('SAVED', path)
    print('共同最新月', LATEST, '| 各家:', {k.split(' (')[0]: str(v) for k, v in LATEST_EACH.items()})
