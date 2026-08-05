# -*- coding: utf-8 -*-
"""Robinhood Markets (HOOD) 月度经营指标 —— GS Monthly exhibit 版式（仅图）。

模版来源：Goldman Sachs「Robinhood Markets Inc. (HOOD): Monthly」（James Yaro 团队，
          Goldman Sachs & Co. LLC），本地 OneDrive/机构报告 下有四份，最全的一份是
          2025-05-13「Strong net deposits and robust trading volume」，15 张 exhibit。
          GS 的结构是：Ex1 汇总表 → 账户 → DARTs → 收入/日 → CPT → 产品结构 →
          分产品 CPT → 融资余额（水平 + 环比）→ 现金归集（水平 + 环比）→ app 下载。
          与同组分析师做的「IBKR Monthly」版式同源，所以能直接复用本项目的 gsx 内核。

对 GS 版本的三处改动（按用户既定规范）：
  1. GS 每张图都挂 "Prior 12mo Avg." 虚线、汇总表也有 12M Avg. 列 —— 全部换成 y/y。
     滚动均值只是把序列再平滑一遍，不回答「相对去年同月是好是坏」。
  2. GS 把「水平值」和「环比」拆成两张图（Ex9/10 融资余额、Ex11/12 现金归集）——
     合并成「柱 + 右轴 y/y 线」，环比只留给真高增速的指标（事件合约、净流入）。
  3. GS 的佣金收入是 "GSe take rate for the quarter * volume for the month" —— 一个
     未经验证的第三方估计。本报告改用**公司自己披露的季度收入**反解费率，并且加了
     GS 没有的**样本外检验**（用上季度费率预测本季度收入，再与实际披露对照）。

数据源（唯一）：investors.robinhood.com → Monthly Metrics → Excel。
     HOOD 的月度数据不走 8-K，是按 Reg FD 挂在 IR 网站上的，盯 EDGAR 抓不到。
     季度收入来自同一个 Excel 的 Quarterly GAAP P&L 页。
     先跑 extract_hood.py 生成 data/hood.csv 与 data/hood_q.csv。
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gsx

D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser('~/Desktop')
SRC = 'Source: Robinhood monthly metrics and quarterly reports'

df = pd.read_csv(os.path.join(D, 'data', 'hood.csv'), index_col=0)
df.index = pd.PeriodIndex(df.index, freq='M')
df = df.sort_index().apply(pd.to_numeric, errors='coerce')

q = pd.read_csv(os.path.join(D, 'data', 'hood_q.csv'), index_col=0)
q.index = pd.PeriodIndex(q.index, freq='Q')
q = q.sort_index().apply(pd.to_numeric, errors='coerce')

LATEST = df.index[-1]

# ── 结构性断点（全部取自官方脚注，不是我们自己判断的）──
BRK_WONDERFI = '2026-06'   # 收购 WonderFi，带进 ~30 万 Funded Customers 与其加密资产
BRK_BITSTAMP = '2025-06'   # Bitstamp 并入净流入、加密成交量与客户数
BRK_SWEEP = '2026-02'      # High-Yield Cash 改版，>$6bn 从 Cash Sweep 挪到 Cash and Deposits

# ── 派生列 ──
tpa = df['total_platform_assets_usdbn']
nd = df['net_deposits_usdbn']
df['organic_growth_ann'] = nd * 12 / tpa.shift(1) * 100      # 年化有机增速
df['market_gains_usdbn'] = tpa.diff() - nd                    # 恒等式残差 = 市值变动
df['tpa_change_usdbn'] = tpa.diff()
df['crypto_bitstamp_share'] = (df['adv_crypto_bitstamp_usdmn']
                               / df['adv_crypto_usdmn'] * 100)
# $bn / mn 客户 = 10^9/10^6 = 千美元/客户，本身已经是 $k，不要再乘 1000
df['assets_per_customer_usdk'] = tpa / df['funded_customers_mn']
df['dats_total_mn'] = (df['dats_equity_mn'] + df['dats_options_mn']
                       + df['dats_crypto_mn'])

# ── 费率（季度实际收入 ÷ 季度成交量）与收入桥 ──
# 这些费率是**反解**出来的：公司披露收入与成交量，费率是二者相除的结果。
# 因此「隐含收入 vs 同季实际收入」必然完全吻合，是循环论证、没有信息量。
# 有信息量的检验只有一种：拿**上一季**的费率去预测**本季**收入，再和实际对照。
RATE = [('Options', 'rev_options_usdmn', 'q_vol_options_mn', 'vol_options_mn'),
        ('Equities', 'rev_equities_usdmn', 'q_vol_equity_usdbn', 'vol_equity_usdbn'),
        ('Crypto', 'rev_crypto_usdmn', 'q_vol_crypto_usdbn', 'vol_crypto_usdbn'),
        ('Event contracts', 'rev_event_usdmn', 'q_vol_event_bn', 'vol_event_bn')]

for name, rc, vc, _ in RATE:
    q['rate_' + name.split()[0].lower()] = q[rc] / q[vc]
# 量纲：$1bn 名义额产生 r 个 $mn，即 r/1000 的费率 = r x 10 bp。
# （曾经写成 x0.1，差了 100 倍 —— 换算表放在这里就是为了让下次能一眼核对。）
q['rate_options_c'] = q['rate_options'] * 100          # $mn/mn张 = $/张 → 美分/张
q['rate_equities_bp'] = q['rate_equities'] * 10        # $mn/$bn → bp
q['rate_crypto_bp'] = q['rate_crypto'] * 10            # $mn/$bn → bp
q['rate_event_c'] = q['rate_event'] * 0.1              # $mn/bn张 → 美分/张

def _rate(rc, vc, p):
    """某季某类的反解费率。成交量为 0 时公司仍可能报几百万收入（事件合约 2024Q4 就是
    量四舍五入成 0.0、收入 $5mn），直接相除会得到 inf 并顺着 ffill 污染整条链。"""
    v, r = q[vc].get(p, np.nan), q[rc].get(p, np.nan)
    if not (np.isfinite(v) and np.isfinite(r)) or v <= 0:
        return np.nan
    return r / v


# 样本外预测：每个季度用**上一季**的费率 x 本季实际成交量。
# 某一类若上季没有可用费率（业务还没起量），该类同时从预测和实际里剔除，
# 保证两根柱子口径一致 —— 否则预测缺一块、实际多一块，误差是假的。
pred = pd.Series(index=q.index, dtype=float)
actual_txn = pd.Series(index=q.index, dtype=float)
for i in range(1, len(q)):
    cur, prv = q.index[i], q.index[i - 1]
    tot = act = 0.0
    n = 0
    for name, rc, vc, _ in RATE:
        r, v = _rate(rc, vc, prv), q[vc].get(cur, np.nan)
        if not (np.isfinite(r) and np.isfinite(v)):
            continue
        tot += r * v
        act += q[rc][cur]
        n += 1
    if n:
        pred[cur], actual_txn[cur] = tot, act

# 隐含月度交易收入 = 当月成交量 x 该月所属季度的费率（最新季之后沿用最后一个已知费率）
qi = pd.PeriodIndex(df.index).asfreq('Q')
imp = pd.DataFrame(index=df.index)
for name, rc, vc, mc in RATE:
    rq = pd.Series({p: _rate(rc, vc, p) for p in q.index}).ffill()
    rm = pd.Series([rq.get(x, np.nan) for x in qi], index=df.index).ffill()
    imp[name] = rm * df[mc]
# 起量前的类别贡献视为 0（事件合约 2025 之前收入本来就接近 0），但整行全空则留 NaN
df['implied_txn_rev_usdmn'] = imp.sum(axis=1, min_count=1)

LAST_Q = q.index[-1]
# 注释预算：半宽图 4 行 x 89 字符，SRC 占掉 1 行 → extra 最多 ~267 字符。
# implied_vs_actual 还会自动追加一句平均绝对误差（约 44 字符），那张的预算是 ~220。
BRIDGE_NOTE = (
    'Assumption: constant take rate within a quarter, back-solved as reported revenue / volume '
    f'({LAST_Q}: options {q["rate_options_c"][LAST_Q]:.0f}c/contract, '
    f'equities {q["rate_equities_bp"][LAST_Q]:.2f}bp, crypto {q["rate_crypto_bp"][LAST_Q]:.1f}bp), '
    'held flat afterwards. Matches its own quarter by construction — Exhibit 14 is the real test.')


def fn(deck):
    gsx.summary_table(deck, df, [
        ('Customers and assets', None, None, None, None, None, None),
        (None, 'Total platform assets ($bn)', 'total_platform_assets_usdbn', 0, False, '$', False),
        (None, 'Net deposits ($bn)', 'net_deposits_usdbn', 1, False, '$', False),
        (None, 'Annualised organic growth (%)', 'organic_growth_ann', 1, True, '', False),
        (None, 'Funded customers (mn)', 'funded_customers_mn', 1, False, '', False),
        (None, 'Assets per funded customer ($k)', 'assets_per_customer_usdk', 1, False, '$', False),
        ('Trading — average daily volumes', None, None, None, None, None, None),
        (None, 'Equity notional ($bn/day)', 'adv_equity_usdbn', 1, False, '$', False),
        (None, 'Options contracts (mn/day)', 'adv_options_mn', 1, False, '', False),
        (None, 'Crypto notional ($mn/day)', 'adv_crypto_usdmn', 0, False, '$', False),
        (None, '  of which Bitstamp ($mn/day)', 'adv_crypto_bitstamp_usdmn', 0, False, '$', False),
        (None, 'Event contracts (mn/day)', 'adv_event_mn', 0, False, '', False),
        (None, 'Total DATs (mn/day)', 'dats_total_mn', 1, False, '', False),
        ('Interest-earning assets ($bn)', None, None, None, None, None, None),
        (None, 'Margin book', 'margin_book_usdbn', 1, False, '$', False),
        (None, 'Cash sweep', 'cash_sweep_usdbn', 1, False, '$', False),
        (None, 'Cash and deposits', 'cash_and_deposits_usdbn', 1, False, '$', False),
        (None, 'Securities lending revenue ($mn)', 'seclend_total_usdmn', 0, False, '$', False),
    ], f'Robinhood monthly metrics — {gsx.mlab(LATEST)}', SRC,
        extra='Three official basis changes sit inside this window and are marked on the charts: '
              'Bitstamp enters net deposits and crypto volume from Jun-2025; the High-Yield Cash '
              'programme moved over $6bn from cash sweep to cash and deposits in Feb-2026; '
              'WonderFi adds about 300k funded customers from Jun-2026. y/y for those rows is '
              'not like-for-like.')

    # ── 客户与资产 ──
    gsx.lvl_bar(deck, tpa, 'Total platform assets', SRC, win=25, dec=0, money='$',
                unit='$bn', break_at=BRK_WONDERFI, break_label='WonderFi',
                extra='Previously reported as Assets Under Custody; renamed and widened to include '
                      'TradePMR-advised assets not custodied by Robinhood')

    gsx.lvl_bar(deck, nd, 'Net deposits', SRC, win=25, dec=1, money='$', unit='$bn',
                show_mom=True, break_at=BRK_BITSTAMP, break_label='Bitstamp',
                extra='m/m shown because net deposits swing far more than y/y can express. '
                      'Bitstamp enters from Jun-2025, TradePMR from Mar-2026, WonderFi from Jun-2026')

    gsx.lvl_bar(deck, df['organic_growth_ann'], 'Annualised organic growth rate', SRC,
                win=25, dec=1, unit='% annualised', pct_series=True,
                extra='Monthly net deposits x 12 / prior month-end total platform assets — the same '
                      'convention used for Schwab core NNA and LPL organic NNA in this series')

    gsx.lvl_bar(deck, df['funded_customers_mn'], 'Funded customers', SRC, win=25, dec=1,
                unit='mn customers', break_at=BRK_WONDERFI, break_label='WonderFi +300k',
                extra='Jun-2026 includes about 300k funded customers acquired with WonderFi on '
                      '1 Jun 2026 — a stock transfer, not organic acquisition')

    gsx.bridge_bar(deck, df, ['net_deposits_usdbn', 'market_gains_usdbn'],
                   [gsx.NAVY, gsx.BLUE], ['Net deposits', 'Market gains (balancing)'],
                   'What moved platform assets: flows vs. markets', SRC, win=13, dec=0,
                   money='$', unit='$bn change', net_label='Total change in platform assets',
                   extra='Identity: opening assets + net deposits + market gains = closing assets. '
                         'Market gains is the balancing item, so it also absorbs any acquired assets')

    # ── 交易量 ──
    gsx.lvl_bar(deck, df['adv_equity_usdbn'], 'Equity notional ADV', SRC, win=25, dec=1,
                money='$', unit='$bn / day', show_mom=True,
                extra='m/m shown: equity volume is running at more than twice last year, so y/y '
                      'alone no longer separates months')

    gsx.lvl_bar(deck, df['adv_options_mn'], 'Options contracts ADV', SRC, win=25, dec=1,
                unit='mn contracts / day', show_mom=True)

    gsx.stack_share(deck, df, ['adv_crypto_app_usdmn', 'adv_crypto_bitstamp_usdmn'],
                    [gsx.NAVY, gsx.BLUE], ['adv_crypto_bitstamp_usdmn'],
                    'Crypto ADV: Robinhood App vs. Bitstamp', SRC, win=15, dec=0,
                    unit='$mn / day', share_label='% Bitstamp (RHS)',
                    names=['Robinhood App', 'Bitstamp'],
                    break_at=BRK_BITSTAMP, break_label='Bitstamp acquired',
                    extra='Bitstamp is institutional and carries a different take rate from the '
                          'retail app, so the mix shift matters for revenue, not just for volume')

    gsx.lvl_bar(deck, df['adv_event_mn'], 'Event contracts ADV', SRC, win=25, dec=0,
                unit='mn contracts / day', show_mom=True,
                extra='Prediction Markets Hub. Launched at scale in 2025 — y/y is off a near-zero '
                      'base for most of the window, so read the levels and the m/m bubble')

    gsx.multi_line(deck, df, ['dats_equity_mn', 'dats_options_mn', 'dats_crypto_mn'],
                   [gsx.NAVY, gsx.RED, gsx.MBLUE], 'Daily average trades by asset class', SRC,
                   win=25, dec=1, unit='mn trades / day',
                   names=['Equity', 'Options', 'Crypto'],
                   extra='Crypto DATs exclude Bitstamp institutional activity; crypto trades every '
                         'calendar day while equities and options use exchange trading days')

    gsx.indexed_lines(deck, {'Equity notional': df['adv_equity_usdbn'],
                             'Options contracts': df['adv_options_mn'],
                             'Crypto notional': df['adv_crypto_usdmn'],
                             'Funded customers': df['funded_customers_mn']},
                      'Volume vs. customer growth, rebased', SRC, base='2023-04',
                      colors=[gsx.NAVY, gsx.RED, gsx.MBLUE, gsx.GREEN],
                      extra='Rebased to 100 at Apr-2023, the first month in the published file. '
                            'The gap between the volume lines and the customer line is monetisation '
                            'per customer, not customer acquisition')

    # ── 收入桥：先讲费率，再讲检验，最后才给隐含值 ──
    gsx.multi_line(deck, q, ['rate_options_c', 'rate_equities_bp', 'rate_crypto_bp',
                             'rate_event_c'],
                   [gsx.NAVY, gsx.RED, gsx.MBLUE, gsx.GREEN],
                   'Effective take rate by asset class', SRC, win=13, dec=2,
                   unit='cents/contract (opt, event) · bp of notional (eq, crypto)',
                   names=['Options (c/contract)', 'Equities (bp)', 'Crypto (bp)',
                          'Event contracts (c/contract)'], log=True,
                   extra='Quarterly reported revenue / quarterly volume — derived, not disclosed. '
                         'Log scale: the four rates span 1.3 to 55, so a linear axis pins equities '
                         'and event contracts to zero. Crypto is the volatile one and it is what '
                         'makes the revenue bridge miss')

    gsx.implied_vs_actual(deck, pred, actual_txn,
                          'Bridge test: last quarter\'s rate applied to this quarter\'s volume',
                          SRC, dec=0, money='$', unit='$mn per quarter', win=12,
                          extra='The only non-circular test: the prior quarter\'s rate applied to '
                                'this quarter\'s actual volumes, versus revenue reported '
                                'afterwards. Both bars cover the same four asset classes.')

    gsx.lvl_bar(deck, df['implied_txn_rev_usdmn'], 'Implied transaction revenue', SRC,
                win=25, dec=0, money='$', unit='$mn / month', extra=BRIDGE_NOTE)

    gsx.stack_share(deck, q, ['rev_options_usdmn', 'rev_equities_usdmn', 'rev_crypto_usdmn',
                              'rev_event_usdmn'],
                    [gsx.NAVY, gsx.MBLUE, gsx.BLUE, gsx.GREEN], ['rev_event_usdmn'],
                    'Transaction revenue mix by asset class', SRC, win=13, dec=0,
                    unit='$mn per quarter', share_label='% event contracts (RHS)',
                    names=['Options', 'Equities', 'Crypto', 'Event contracts'],
                    extra='Quarterly actuals, not derived. Event contracts went from nothing to a '
                          'fifth of transaction revenue in six quarters — the fastest mix shift in '
                          'the business')

    # ── 生息资产 ──
    gsx.lvl_bar(deck, df['margin_book_usdbn'], 'Margin book', SRC, win=25, dec=1,
                money='$', unit='$bn',
                extra='Period-end margin loans receivable, including balances from RIAs on the '
                      'TradePMR platform')

    gsx.multi_line(deck, df, ['cash_sweep_usdbn', 'cash_and_deposits_usdbn'],
                   [gsx.NAVY, gsx.MBLUE], 'Cash sweep vs. cash and deposits', SRC,
                   win=25, dec=1, money='$', unit='$bn',
                   names=['Cash sweep (off balance sheet)', 'Cash and deposits'],
                   break_at=BRK_SWEEP, break_label='High-Yield Cash change',
                   extra='In Feb-2026 the first $10k of enrolled balances per customer moved to '
                         'free credit balances to fund margin lending, shifting over $6bn between '
                         'these two lines. The y/y decline in cash sweep after that date is '
                         'mechanical, not customer attrition — read the two lines together')

    gsx.multi_line(deck, df, ['seclend_total_usdmn', 'seclend_net_usdmn'],
                   [gsx.NAVY, gsx.BLUE], 'Securities lending revenue', SRC, win=25, dec=0,
                   money='$', unit='$mn / month',
                   names=['Total securities lending revenue', 'Securities lending, net'],
                   extra='Net excludes interest on cash collateral for margin-based lending, so the '
                         'gap between the two lines widens as the margin book grows')

    gsx.lvl_bar(deck, df['assets_per_customer_usdk'], 'Assets per funded customer', SRC,
                win=25, dec=1, money='$', unit='$k per customer',
                break_at=BRK_WONDERFI, break_label='WonderFi',
                extra='Total platform assets / funded customers. Rises when existing customers '
                      'deposit or markets rally, falls when acquisitions bring in customers with '
                      'smaller balances')

    # ── 长历史 ──
    gsx.long_line(deck, tpa, 'Total platform assets — full published history', SRC,
                  dec=0, money='$', unit='$bn', circle=3,
                  extra='The monthly file publishes a rolling window starting Apr-2023; earlier '
                        'months exist only in prior monthly releases and are not carried here')

    gsx.qtr_bar(deck, nd, 'Net deposits by quarter', SRC, win=13, dec=1, money='$',
                unit='$bn per quarter', label_dec=1, how='sum',
                extra='Quarterly totals remove the month-length and month-end timing noise in the '
                      'monthly series')

    gsx.year_lines(deck, nd, 'Net deposits path by year', SRC, n_years=4, cumulative=True,
                   dec=0, money='$', unit='$bn cumulative',
                   extra='Cumulative within each calendar year. The 2023 line starts in April '
                         'because that is where the published file begins — it is not a weak year, '
                         'it is a short one, and is not comparable with the full years')

    gsx.lvl_bar(deck, df['crypto_bitstamp_share'], 'Bitstamp share of crypto volume', SRC,
                win=15, dec=0, unit='% of crypto ADV', pct_series=True,
                break_at=BRK_BITSTAMP, break_label='Bitstamp acquired',
                extra='Institutional crypto now runs above half of total crypto volume but earns a '
                      'far lower take rate than the retail app, which is why crypto revenue has '
                      'not followed crypto volume')

    gsx.qtr_bar(deck, df['dats_total_mn'], 'Total daily average trades by quarter', SRC,
                win=13, dec=1, unit='mn trades / day', label_dec=1, how='mean',
                extra='Quarterly average of the three asset classes; removes the month-length '
                      'differences between equity trading days and crypto calendar days')

    gsx.heat_matrix(deck, df['organic_growth_ann'], 'Annualised organic growth rate (%)',
                    SRC, dec=0, n_years=4, extra='Green = faster organic growth')

    gsx.heat_matrix(deck, df['adv_equity_usdbn'].pct_change(12) * 100,
                    'Equity notional ADV y/y (%)', SRC, dec=0, n_years=4,
                    extra='Green = faster growth')


if __name__ == '__main__':
    path = os.path.join(OUT, f'HOOD 月度经营指标跟踪_{LATEST}.pdf')
    gsx.build(path, 'Robinhood Markets (HOOD) — Monthly Operating Metrics',
              f'Data through {gsx.mlab(LATEST)}  ·  charts only, no commentary  ·  '
              f'template after Goldman Sachs GIR "HOOD Monthly"',
              f'Robinhood Markets (HOOD)  ·  monthly metrics published on the IR site under Reg FD, '
              f'not filed on Form 8-K  ·  built {gsx.today()}  ·  personal research use',
              fn)
    print('SAVED', path)
    print(f'月度窗口 {df.index[0]} → {LATEST}（{len(df)} 个月）| 季度 {q.index[0]} → {q.index[-1]}')
