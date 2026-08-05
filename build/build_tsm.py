# -*- coding: utf-8 -*-
"""TSMC (2330.TW) 月度营收 —— GS 台股月营收 exhibit 版式（仅图，无正文）。

模版来源：Goldman Sachs「Hon Hai (2317.TW): Mar rev +46% YoY」与
          「Wistron (3231.TW): Monthly revenues preview」两份同构报告的 Exhibit 1-2，
          外加 GS HKEX 深度的超长历史层与 JPM AXP 的季节性剥离图型。
数据源：TSMC 官网 IR Monthly Revenue（台湾法定次月 10 日前公告）。
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsx

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser('~/Desktop')

SRC = 'Source: TSMC monthly revenue reports; format after Goldman Sachs GIR'
SRC_G = 'Source: TSMC quarterly earnings-call guidance and reported results'
SRC_FX = 'Source: monthly average NTD/USD (FRED series EXTAUS)'

df = pd.read_csv(os.path.join(D, 'data', 'tsm.csv'))
df['month'] = pd.PeriodIndex(df['month'], freq='M')
df = df.set_index('month').sort_index()

rev = df['revenue_ntd_mn'].astype(float)
LATEST = rev.index[-1]

# ── 派生序列（全部由月营收单一字段推出，不引入外部估计）──
df['rev_bn'] = rev / 1000.0                      # NT$bn
df['rev_3ma'] = rev.rolling(3).mean() / 1000.0   # 3 个月移动平均 NT$bn
ytd = rev.groupby(rev.index.year).cumsum()
df['ytd_bn'] = ytd / 1000.0
qtr_key = rev.index.asfreq('Q')
df['qtd_bn'] = rev.groupby(qtr_key).cumsum() / 1000.0
# 当月占「滚动 12 个月」营收的比重 —— 用 TTM 做分母，避免当年只有半年数据时
# 分母偏小导致占比被虚增（均值权重 = 8.33%）。
df['share_ttm'] = rev / rev.rolling(12).sum() * 100
df['ttm_bn'] = rev.rolling(12).sum() / 1000.0    # 滚动 12 个月营收 NT$bn
df['yoy'] = df['yoy_pct'].astype(float)

# ── 汇率拆分（任务 5）：把新台币营收按月均汇率折成美元，同比之差即汇率贡献 ──
fx = pd.read_csv(os.path.join(D, 'data', 'tsm_fx.csv'))
fx['month'] = pd.PeriodIndex(fx['month'], freq='M')
fx = fx.set_index('month').sort_index()['ntd_per_usd']
df['fx'] = fx
df['rev_usdmn'] = rev / df['fx']                       # 假设：按当月平均汇率折算
df['yoy_usd'] = df['rev_usdmn'].pct_change(12) * 100
df['fx_contrib_pp'] = df['yoy'] - df['yoy_usd']        # 同比之差 = 汇率贡献（百分点）

# ── 季度指引 vs 实际（任务 2）──
g = pd.read_csv(os.path.join(D, 'data', 'tsm_guidance.csv'))
g['q'] = g['quarter']
qkey = rev.index.asfreq('Q')
qtd_ntd = rev.groupby(qkey).sum()                      # 各季已公布月份的新台币累计
qtd_months = rev.groupby(qkey).count()
CURQ = str(rev.index[-1].asfreq('Q'))
_gq = [str(x).replace('20', '20', 1) for x in g['quarter']]
g['qlabel'] = [x[:4] + 'Q' + x[-1] for x in g['quarter']]
# 当前季度的 QTD 美元值（用当季已公布月份的新台币累计 / 该季平均汇率）
_cq = rev.index[-1].asfreq('Q')
_fxq = df['fx'].groupby(df.index.asfreq('Q')).mean()
QTD_USD = (qtd_ntd.get(_cq, np.nan) / 1000.0) / _fxq.get(_cq, np.nan) if _cq in qtd_ntd.index else np.nan
QTD_N = int(qtd_months.get(_cq, 0))
# 指引表用公司自己的季度标签对齐
g = g.set_index('qlabel')
g_mid = (g['guide_low_usdbn'] + g['guide_high_usdbn']) / 2
g_beat = pd.Series(((g['actual_rev_usdbn'] / g_mid - 1) * 100).values,
                   index=pd.PeriodIndex([f'{q[:4]}-{int(q[-1])*3:02d}' for q in g.index], freq='M')).dropna()
ASSUMP = 'Assumption: NT$ converted at the month average NTD/USD rate — an approximation'


def fn(deck):
    # ── Exhibit 1：GS Monthly 汇总表 ──
    gsx.summary_table(deck, df, [
        ('Revenue', None, None, None, None, None, None),
        (None, 'Monthly revenue (NT$bn)', 'rev_bn', 1, False, '', False),
        (None, '3-month moving avg. (NT$bn)', 'rev_3ma', 1, False, '', False),
        ('Cumulative', None, None, None, None, None, None),
        (None, 'Quarter-to-date (NT$bn)', 'qtd_bn', 1, False, '', False),
        (None, 'Year-to-date (NT$bn)', 'ytd_bn', 1, False, '', False),
        ('Seasonality', None, None, None, None, None, None),
        (None, '% of trailing-12-month revenue', 'share_ttm', 2, True, '', False),
    ], f'TSMC monthly revenue summary — {gsx.mlab(LATEST)}', SRC,
        extra='All figures derived from the single officially disclosed field: consolidated net revenue (NT$mn, unaudited).')

    # ── Exhibit 2：GS 台股月营收核心图（Hon Hai / Wistron Exhibit 1 版式）──
    gsx.rev_bar_yoy(deck, df['rev_bn'], 'TSMC monthly revenues', SRC, win=20, dec=0,
                    unit='NT$bn', label_dec=0,
                    extra='Gold line = y/y growth (RHS)')

    # ── Exhibit 3：GS HKEX 式超长历史层 ──
    gsx.long_line(deck, df['rev_bn'], 'Full monthly revenue history since 2016',
                  SRC, dec=0, unit='NT$bn', circle=3,
                  extra='Full disclosed history since Jan-2016; red ring = latest 3 months')

    # ── Exhibit 4：环比变化率（与 Ex2 成对）──
    gsx.chg_line(deck, rev, 'Month-on-month revenue change', SRC, win=25, kind='mom')

    # ── Exhibit 5：月度 → 季度桥（当季未满月份浅色）──
    gsx.qtr_bar(deck, df['rev_bn'], 'Monthly revenue aggregated to quarters', SRC,
                win=14, unit='NT$bn', label_dec=0)

    # ── Exhibit 7：逐日历月分布箱线图 ──

    # ── 任务 2：季度指引区间 vs 实际 ──
    gsx.range_vs_actual(deck, list(g.index), g['guide_low_usdbn'], g['guide_high_usdbn'],
                        g['actual_rev_usdbn'],
                        'Quarterly revenue vs. company guidance', SRC_G,
                        dec=1, money='$', unit='US$bn',
                        qtd=(QTD_USD if QTD_N and QTD_N < 3 else None),
                        qtd_label=f'quarter-to-date ({QTD_N} of 3 months)',
                        extra='Bars are the revenue range TSMC guided at the prior quarter earnings call; diamonds are the reported result. ' + (f'The hollow diamond is the current quarter with {QTD_N} of 3 months reported, converted at monthly average FX. ' if QTD_N and QTD_N < 3 else ''))

    gsx.lvl_bar(deck, g_beat, 'Actual vs. guidance midpoint', SRC_G, win=14, dec=1,
                unit='% vs midpoint', pct_series=True, labels=True,
                extra='Positive = came in above the midpoint of the guided range. A persistent positive bias is the company guiding conservatively, not a series of surprises')

    # ── 任务 5：汇率贡献拆分 ──
    gsx.multi_line(deck, df, ['yoy', 'yoy_usd'], [gsx.NAVY, gsx.MBLUE],
                   'Revenue growth: NT$ vs. US$', SRC, win=25, dec=0, unit='% y/y',
                   names=['NT$ revenue y/y (as reported)', 'US$ revenue y/y (converted)'],
                   extra='The gap between the two lines is the currency contribution. ' + ASSUMP)

    gsx.lvl_bar(deck, df['fx_contrib_pp'], 'Currency contribution to reported growth', SRC,
                win=25, dec=1, unit='pp of y/y', pct_series=True,
                extra='NT$ y/y less US$ y/y. Positive = a weaker NT dollar flattered the reported number. ' + ASSUMP)

    gsx.long_line(deck, df['fx'], 'NTD per USD, monthly average', SRC_FX, dec=1,
                  unit='NTD per USD', circle=3,
                  extra='Roughly 70% of TSMC revenue is US-dollar denominated but reported in NT$, so this rate moves the headline')

    # ── Exhibit 8：逐年 YTD 追赶曲线 ──
    gsx.year_lines(deck, df['rev_bn'], 'YTD revenue pace vs. prior years', SRC,
                   n_years=6, cumulative=True, dec=0, unit='NT$bn cumulative')

    # ── Exhibit 9：滚动 12 个月营收（剔除季节性的趋势线）──
    gsx.long_line(deck, df['ttm_bn'], 'Trailing-12-month revenue', SRC, dec=0,
                  unit='NT$bn (TTM)', circle=3,
                  extra='12-month rolling sum removes seasonality entirely')

    # ── Exhibit 10：同比热力矩阵 ──
    gsx.heat_matrix(deck, df['yoy'], 'Monthly revenue y/y growth (%)',
                    SRC, dec=0, n_years=9,
                    extra='Green = faster y/y growth, red = slower; blanks are months not yet reported')


if __name__ == '__main__':
    path = os.path.join(OUT, f'TSMC 月度营收跟踪_{LATEST}.pdf')
    gsx.build(path, 'TSMC (2330.TW) — Monthly Revenue Tracker',
              f'Data through {gsx.mlab(LATEST)}  ·  charts only, no commentary  ·  template after Goldman Sachs GIR Taiwan monthly-revenue notes',
              f'Taiwan Semiconductor Manufacturing (2330.TW / TSM)  ·  built {gsx.today()}  ·  personal research use',
              fn)
    print('SAVED', path)
