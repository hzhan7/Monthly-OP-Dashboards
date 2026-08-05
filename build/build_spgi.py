# -*- coding: utf-8 -*-
"""S&P Global (SPGI) 月度指标 —— GS Monthly exhibit 版式（仅图）。

模版来源：Goldman Sachs「IBKR Monthly」的成对图法（水平柱 + 12mo 均线 + YoY/MoM 气泡
          ⇄ 变化率曲线）与 JPM AXP 的季节性/热力图型。
数据源：S&P Global 官网 IR「Quarterly Earnings & Monthly Metrics」栏目每月 15 日发布的 xlsx
        （两个 sheet：S&P Global Ratings / S&P Dow Jones Indices）。
        注意该 xlsx **不进 SEC EDGAR**，只挂官网，且 investor.spglobal.com 对 curl 一律
        Cloudflare 403 —— 但 s29.q4cdn.com 的 CDN 直链可直接下载。

⚠️ 披露口径的硬约束（决定了本 PDF 为何比其他标的薄）：
   · Billed Issuance 官方**只披露同比百分比，从不给绝对面值**。故本 PDF 用同比链式
     构造一个指数（2024 年同月 = 100）来呈现相对水平，指数本身不是公司披露值。
   · SPDJI ADV 官方给绝对值，但每份 xlsx 只含当年与上年两年。2024 年的绝对值由
     2025 年值与官方「'25 v. '24 % Change」反算得到（披露数据的算术推导，非估计）。
   · 更早年份的历史文件在 CDN 上已不可访问，故序列起点为 2024-01。
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsx

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser('~/Desktop')
SRC = 'Source: S&P Global monthly metrics xlsx; format after Goldman Sachs GIR'
DNOTE = '2024 ADV values are back-calculated from the 2025 level and the officially disclosed 25 v. 24 % change'
INOTE = 'Billed issuance is disclosed as a y/y % only; this index chains those percentages (same month of 2024 = 100)'

df = pd.read_csv(os.path.join(D, 'data', 'spgi_clean.csv'))
df['month'] = pd.PeriodIndex(df['month'], freq='M')
df = df.set_index('month').sort_index()
for c in df.columns:
    df[c] = pd.to_numeric(df[c], errors='coerce')

LATEST = df.index[-1]
adv = df['spdji_adv_mn']


def fn(deck):
    gsx.summary_table(deck, df, [
        ('S&P Dow Jones Indices', None, None, None, None, None, None),
        (None, 'ADV of exchange-traded derivatives (mn contracts)', 'spdji_adv_mn', 2, False, '', False),
        (None, 'ADV y/y as disclosed (%)', 'spdji_adv_yoy', 1, True, '', False),
        ('S&P Global Ratings', None, None, None, None, None, None),
        (None, 'Billed issuance y/y as disclosed (%)', 'billed_issuance_yoy', 1, True, '', False),
        (None, 'Billed issuance index (2024 same month = 100)', 'billed_issuance_index', 1, False, '', False),
    ], f'S&P Global monthly metrics summary — {gsx.mlab(LATEST)}', SRC,
        extra=DNOTE + '.  ' + INOTE + '.  From Dec-2025 the ADV definition excludes event contracts, with no restatement of earlier months.')

    gsx.lvl_bar(deck, adv, 'SPDJI average daily volume of ETDs', SRC, win=25, dec=1,
                unit='mn contracts / day', break_at=pd.Period('2025-12', 'M'),
                break_label='ex-event contracts', extra='From Dec-2025 the ADV definition excludes event contracts, with no restatement of earlier months')

    gsx.lvl_bar(deck, df['billed_issuance_index'].dropna(),
                'Ratings billed issuance index', SRC, win=25, dec=0,
                unit='index, 2024 same month = 100',
                extra=INOTE + '; the y/y line starts Jan-2026')

    gsx.multi_line(deck, df, ['billed_issuance_yoy', 'spdji_adv_yoy'],
                   [gsx.NAVY, gsx.MBLUE],
                   'The two disclosed y/y series side by side', SRC, win=18, dec=0,
                   unit='% y/y', names=['Ratings billed issuance', 'SPDJI ADV'],
                   extra='These are the only two figures S&P Global publishes monthly')

    gsx.qtr_bar(deck, adv, 'SPDJI ADV by quarter', SRC, win=10,
                unit='mn contracts / day', dec=1, label_dec=1, how='mean')

    gsx.year_lines(deck, adv, 'SPDJI ADV path by year', SRC, n_years=3,
                   cumulative=False, dec=1, unit='mn contracts / day', extra=DNOTE)

    gsx.heat_matrix(deck, df['billed_issuance_yoy'], 'Ratings billed issuance y/y (%)',
                    SRC, dec=0, n_years=3,
                    extra='Green = faster issuance growth; 2024 is blank because only y/y is disclosed')


if __name__ == '__main__':
    path = os.path.join(OUT, f'SPGI 月度指标跟踪_{LATEST}.pdf')
    gsx.build(path, 'S&P Global (SPGI) — Monthly Metrics Tracker',
              f'Data through {gsx.mlab(LATEST)}  ·  charts only, no commentary  ·  template after Goldman Sachs GIR monthly-metrics notes',
              f'S&P Global (SPGI)  ·  monthly metrics xlsx  ·  built {gsx.today()}  ·  personal research use',
              fn)
    print('SAVED', path)
