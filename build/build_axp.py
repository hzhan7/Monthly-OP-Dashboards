# -*- coding: utf-8 -*-
"""American Express (AXP) 月度信贷经营指标 —— JPM「Managed Data Release」exhibit 版式（仅图）。

模版来源：J.P. Morgan「American Express June 2025 Managed Data Release」的四个图型：
  Fig 1  Growth and Credit Trends (y/y)      柱=水平值 + 线=同比，双轴，长窗口含疫情前
  Fig 2  AXP Credit Seasonality Trends       灰=过去 N 年同月均值 / 蓝=实际 的配对柱
  Fig 3  DQ & NCO (m/m) vs 10-year trends    逐日历月箱线图 + 当年/去年标记
  Fig 4  Balances, DQs and NCOs Trends       月 x 年热力矩阵
外加 GS Monthly 的 Exhibit 1 汇总表。

⚠️ 口径断点：AXP 自 2026 年 5 月起把 Card Member loans 与 receivables 合并披露为
   "Card balances"（含 pay-in-full 余额），并在 2026-05-15 的 8-K Exhibit 99.1 里
   重述了 24 个月历史。两套口径不可直接连比，本 PDF 分页呈现：
     第 1 页 = 新合并口径（2024-05 起，重述历史 + 最新申报）
     第 2 页 = 旧 loans-only 口径（2016-01 → 2026-03），仅用于长历史与季节性
数据源：SEC EDGAR CIK 0000004962 的 8-K Item 7.01（每月 15 日前后）。
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsx
import bridge

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser('~/Desktop')

SRC_N = 'Source: AXP 8-K Item 7.01, combined Card balances basis; format after J.P. Morgan'
SRC_O = 'Source: AXP 8-K Item 7.01, Card Member loans basis; format after J.P. Morgan'
BASIS_N = 'Combined Card balances basis (loans + receivables), effective May-2026'
BASIS_O = 'Card Member loans only (pre-2026 basis) — not comparable to page 1'
JUN_NOTE = 'Jun-26 write-off rate cut ~0.3pp (Consumer) / ~0.1pp (SBS) by a sale of written-off balances'


def load(name):
    d = pd.read_csv(os.path.join(D, 'data', name))
    d['month'] = pd.PeriodIndex(d['month'], freq='M')
    return d.set_index('month').sort_index()


new = load('axp_newbasis.csv')
# ── Lending Trust 月度 Form 10-D（与 8-K 同日报送，近 31 期 31/31 同日，故并入本份）──
avgbal = load('axp_8k_card_balances.csv')
_niy = bridge.rate_series('AXP', 'net_interest_yield_newbasis')          # %, annualised
_niy_m = bridge.to_monthly(_niy, avgbal.index)
avgbal['us_avg_bal'] = avgbal['consumer_avg_bal_usdbn'] + avgbal['smb_avg_bal_usdbn']
avgbal['implied_nii_usdmn'] = avgbal['us_avg_bal'] * 1000.0 * _niy_m / 100.0 / 12.0
avgbal['niy'] = _niy_m
NII_NOTE = ('Assumption: monthly NII = average U.S. Consumer + Small Business card balances x the '
            f'disclosed net interest yield / 12 ({_niy.index[-1]} = {_niy.iloc[-1]:.1f}%, held flat after). '
            'The yield is company-wide but the balances are U.S. card only.')

trust = load('axp_trust.csv')
trust = trust.join(new[['consumer_nco_pct', 'consumer_dq30_pct']], how='left')
TRUST_SRC = 'Source: American Express Credit Account Master Trust monthly Form 10-D (SEC CIK 0001003509)'
TRUST_NOTE = 'Trust pool = revolve-eligible balances only, so its rates sit below the 8-K rates'
old = load('axp.csv').loc[:pd.Period('2026-03', 'M')]   # 旧口径只到改口径前一个月

LATEST = new.index[-1]
new['total_balance'] = new['consumer_balance_usdbn'] + new['sbs_balance_usdbn']
old['total_balance'] = old['consumer_balance_usdbn'] + old['sbs_balance_usdbn']


def fn(deck):
    # ══════════ 第 1 页：新合并口径（当前画面） ══════════
    gsx.summary_table(deck, new, [
        ('U.S. Consumer Card', None, None, None, None, None, None),
        (None, 'Total Card balances ($bn)', 'consumer_balance_usdbn', 1, False, '$', False),
        (None, '30+ days past due (%)', 'consumer_dq30_pct', 2, True, '', True),
        (None, 'Net write-off rate, principal (%)', 'consumer_nco_pct', 2, True, '', True),
        ('U.S. Small Business Card', None, None, None, None, None, None),
        (None, 'Total Card balances ($bn)', 'sbs_balance_usdbn', 1, False, '$', False),
        (None, '30+ days past due (%)', 'sbs_dq30_pct', 2, True, '', True),
        (None, 'Net write-off rate, principal (%)', 'sbs_nco_pct', 2, True, '', True),
        ('Combined', None, None, None, None, None, None),
        (None, 'Card balances held for investment ($bn)', 'total_balance', 1, False, '$', False),
    ], f'AXP monthly credit metrics — {gsx.mlab(LATEST)}', SRC_N,
        extra=BASIS_N + '.  ' + JUN_NOTE + '.  Green = improving (lower delinquency / write-off).')

    gsx.lvl_bar(deck, new['consumer_balance_usdbn'], 'U.S. Consumer Card balances', SRC_N,
                win=25, dec=1, money='$', unit='$bn', extra=BASIS_N)

    gsx.multi_line(deck, new, ['consumer_dq30_pct', 'consumer_nco_pct'],
                   [gsx.MBLUE, gsx.RED], 'U.S. Consumer delinquency and write-off',
                   SRC_N, win=26, dec=2, unit='%',
                   names=['30+ days past due', 'Net write-off (principal)'],
                   extra=JUN_NOTE)

    gsx.lvl_bar(deck, new['sbs_balance_usdbn'], 'U.S. Small Business Card balances', SRC_N,
                win=25, dec=1, money='$', unit='$bn', extra=BASIS_N)

    gsx.multi_line(deck, new, ['sbs_dq30_pct', 'sbs_nco_pct'],
                   [gsx.MBLUE, gsx.RED], 'U.S. Small Business delinquency and write-off',
                   SRC_N, win=26, dec=2, unit='%',
                   names=['30+ days past due', 'Net write-off (principal)'],
                   extra=JUN_NOTE)

    gsx.lvl_bar(deck, avgbal['implied_nii_usdmn'], 'Implied U.S. card net interest income',
                SRC_N, win=25, dec=0, money='$', unit='$mn / month', extra=NII_NOTE)

    gsx.lvl_bar(deck, avgbal['niy'], 'Net interest yield on card balances', SRC_N,
                win=25, dec=2, unit='% annualised', pct_series=True,
                extra='The disclosed company-wide yield, stepped quarterly. This is the rate the bridge above multiplies by, so it is where the bridge can go wrong.')

    # ══════════ Lending Trust 月度 Form 10-D —— 与 8-K 同日报送，信息更细 ══════════
    gsx.summary_table(deck, trust, [
        ('Trust performance (%, monthly)', None, None, None, None, None, None),
        (None, 'Portfolio yield', 'portfolio_yield_pct', 2, True, '', False),
        (None, 'Payment rate', 'payment_rate_pct', 2, True, '', False),
        (None, 'Excess spread', 'excess_spread_pct', 2, True, '', False),
        (None, 'Annualised default rate, net of recoveries', 'nco_pct', 2, True, '', True),
        (None, 'Total 30+ day delinquency', 'dq30_pct', 2, True, '', True),
        ('Pool size', None, None, None, None, None, None),
        (None, 'Principal receivables ($bn)', 'principal_receivables_usdbn', 2, False, '$', False),
    ], f'Lending Trust monthly report — {gsx.mlab(trust.index[-1])}', TRUST_SRC,
        extra='Filed as Form 10-D on the same day as the 8-K credit statistics — 31 of the last 31 filings were same-day — so both reach you in one release. ' + TRUST_NOTE + '.')

    gsx.lvl_bar(deck, trust['excess_spread_pct'], 'Trust excess spread', TRUST_SRC,
                win=25, dec=2, unit='%', pct_series=True,
                extra='Portfolio yield less charge-offs, servicing and note coupon — the cushion that absorbs losses before noteholders are hit. The single most-watched number in the trust report')

    gsx.multi_line(deck, trust, ['portfolio_yield_pct', 'payment_rate_pct'],
                   [gsx.NAVY, gsx.MBLUE], 'Trust portfolio yield and payment rate',
                   TRUST_SRC, win=25, dec=1, unit='%',
                   names=['Portfolio yield', 'Payment rate'],
                   extra='Payment rate is how fast cardholders repay; a falling payment rate is an early warning that shows up months before delinquency does')

    gsx.multi_line(deck, trust, ['nco_pct', 'consumer_nco_pct'], [gsx.NAVY, gsx.RED],
                   'Loss rate: trust pool vs. 8-K Card balances', TRUST_SRC, win=25,
                   dec=2, unit='%', names=['Trust: annualised default rate, net of recoveries',
                                           '8-K: U.S. Consumer net write-off rate'],
                   extra='The two are close analogues but not the same definition, and ' + TRUST_NOTE.lower())

    gsx.multi_line(deck, trust, ['dq30_pct', 'consumer_dq30_pct'], [gsx.NAVY, gsx.RED],
                   'Delinquency: trust pool vs. 8-K Card balances', TRUST_SRC, win=25,
                   dec=2, unit='%', names=['Trust: total 30+ days delinquent',
                                           '8-K: U.S. Consumer 30+ days past due'],
                   extra='Both are 30+ day measures on the same concept, so the persistent gap is purely the pool difference: ' + TRUST_NOTE.lower())

    # ══════════ 第 2 页：旧 loans-only 口径 —— JPM 四图型的长历史层 ══════════
    # JPM Fig 1：柱=水平值 + 线=同比，长窗口含疫情前
    gsx.rev_bar_yoy(deck, old['consumer_balance_usdbn'],
                    'U.S. Consumer loans and y/y growth', SRC_O,
                    win=42, dec=0, unit='$bn', label_dec=0, extra=BASIS_O)

    # JPM Fig 2：季节性剥离
    gsx.seasonality(deck, old['consumer_nco_pct'],
                    'Write-off rate vs. same-month norm', SRC_O,
                    win=13, years=9, dec=2, unit='%', pct=True, extra=BASIS_O)

    # JPM Fig 3：逐日历月分布

    gsx.year_lines(deck, old['consumer_nco_pct'], 'Consumer write-off rate by year',
                   SRC_O, n_years=6, cumulative=False, dec=2, unit='%',
                   extra='Each line is one calendar year; red = current year.  ' + BASIS_O)

    gsx.seasonality(deck, old['consumer_dq30_pct'],
                    'Delinquency vs. same-month norm', SRC_O,
                    win=13, years=9, dec=2, unit='%', pct=True, extra=BASIS_O)

    gsx.year_lines(deck, old['sbs_nco_pct'], 'Small Business write-off rate by year',
                   SRC_O, n_years=6, cumulative=False, dec=2, unit='%',
                   extra='Each line is one calendar year; red = current year.  ' + BASIS_O)

    # JPM Fig 4：月 x 年热力矩阵（信用指标：低=好，故反转配色）
    gsx.heat_matrix(deck, old['consumer_nco_pct'],
                    'Consumer net write-off rate (%)', SRC_O,
                    dec=1, n_years=11, reverse=True,
                    extra='Green = lower write-off rate (better).  ' + BASIS_O)

    gsx.heat_matrix(deck, old['sbs_nco_pct'],
                    'Small Business net write-off rate (%)', SRC_O,
                    dec=1, n_years=11, reverse=True,
                    extra='Green = lower write-off rate (better).  ' + BASIS_O)


if __name__ == '__main__':
    path = os.path.join(OUT, f'AXP 月度信贷指标跟踪_{LATEST}.pdf')
    gsx.build(path, 'American Express (AXP) — Monthly Credit Metrics Tracker',
              f'Data through {gsx.mlab(LATEST)}  ·  charts only, no commentary  ·  template after J.P. Morgan managed-data-release note',
              f'American Express (AXP)  ·  SEC 8-K Item 7.01  ·  built {gsx.today()}  ·  personal research use',
              fn)
    print('SAVED', path)
