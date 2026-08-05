# -*- coding: utf-8 -*-
"""HKEX 香港交易所 (0388.HK) 月度市场统计 —— 网页看板数据生成器。

把 build/build_hkex.py（matplotlib / PDF）里的每一张 exhibit 重新实现成 payload 里的
一个 exhibit 对象，写出 data/hkex.js。图序、编号、标题文案、图注、口径断点全部照搬原 deck。

原 deck 的设计（模块 docstring，逐条沿用）：
  模版来源 Goldman Sachs「Hong Kong Exchanges (0388.HK): New listings and profit growth
  inflection to drive sustainable ADT growth」（Exhibit 1-15）与「Multiple tailwinds in
  2026E despite weak Nov ADT」（Exhibit 1-28）。核心做法：
    1) 三层时间窗：超长历史判周期位置 / 中长期判趋势 / 近 13-25 个月讲当下；
    2) 双图开场：整体 ADT 与南向 ADT 并列；
    3) 驱动量置顶：ADT / 衍生品张数这类经营量指标放在汇总表最上方，先于市值等存量。

数据源（只读 series/，不读 build/data/）：
  series/hkex.csv       HKEX Monthly Market Highlights 月度序列
  series/fee_rates.csv  HKEX 季度费率与现货分部收入（量→收入桥用）

用法: python3 build/hkex.py
"""
import datetime
import json
import os

import numpy as np
import pandas as pd

import payload_guard

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')

TICKER = 'hkex'
SRC = 'Source: HKEX Monthly Market Highlights; format after Goldman Sachs GIR'


# ────────────────────────────── 读数据 ──────────────────────────────
def mlab(p):
    return p.strftime('%b-%y')


def load():
    df = pd.read_csv(os.path.join(SERIES, 'hkex.csv'))
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    df = df.set_index('month').sort_index()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    need = ['adt_hkdbn', 'mktcap_hkdtn', 'new_listings', 'ipo_funds_hkdbn',
            'derivatives_adv_contracts', 'southbound_adt_hkdbn']
    miss = [c for c in need if c not in df.columns]
    if miss:
        raise SystemExit(f'series/hkex.csv 缺列: {miss}')
    return df


def rate_series(metric, scale=1.0):
    """series/fee_rates.csv 里 HKEX 的某个季度参数，索引 PeriodIndex(freq='Q')。"""
    d = pd.read_csv(os.path.join(SERIES, 'fee_rates.csv'))
    d = d[(d['company'] == 'HKEX') & (d['metric'] == metric)].copy()
    if not len(d):
        raise SystemExit(f'fee_rates.csv 里没有 HKEX/{metric}')
    d['q'] = pd.PeriodIndex(d['period'].str.replace('-', ''), freq='Q')
    return d.set_index('q')['value'].astype(float).sort_index() * scale


def to_monthly(rate_q, month_index):
    """季度费率 → 月度：当季各月用该季费率；最新季之后沿用最后一个已知值。"""
    q = pd.PeriodIndex(month_index).asfreq('Q')
    return pd.Series([rate_q.get(x, np.nan) for x in q],
                     index=month_index, dtype=float).ffill()


def tail_contiguous(s):
    """只保留末尾逐月连续的一段（南向通 2022-2024 断档 40 个月，直接取尾 N 个点
    会把相隔数年的月份并排画成相邻期 —— 那是假的时间轴）。同 gsx._tail_contiguous。"""
    s = s.dropna()
    if len(s) < 3:
        return s
    idx = list(s.index)
    gaps = [(idx[i] - idx[i - 1]).n for i in range(1, len(idx))]
    stride = max(set(gaps), key=gaps.count)
    start = 0
    for i in range(len(idx) - 1, 0, -1):
        if (idx[i] - idx[i - 1]).n != stride:
            start = i
            break
    return s.iloc[start:]


# ────────────────────────────── 格式化（一律在 Python 侧） ──────────────────────────────
def L(a):
    return [round(float(v), 6) for v in a]


def LN(a):
    return [None if v is None or not np.isfinite(v) else round(float(v), 6) for v in a]


def num(v, dec=1):
    return '—' if v is None or not np.isfinite(v) else f'{v:,.{dec}f}'


def pctf(x, dec=0):
    """oval / headline 用的百分比。正负号交给 f-string 的 + 标志。"""
    return '—' if not np.isfinite(x) else f'{x * 100:+.{dec}f}%'


def ppf(x, dec=0):
    return '—' if not np.isfinite(x) else f'{x:+.{dec}f}pp'


def yoy(a, lag=12):
    """序列末期相对 lag 期前的变化率（小数）。"""
    a = np.asarray(a, float)
    if len(a) <= lag or not np.isfinite(a[-1]) or not np.isfinite(a[-1 - lag]) or a[-1 - lag] == 0:
        return np.nan
    return a[-1] / a[-1 - lag] - 1


def mom(a):
    a = np.asarray(a, float)
    if len(a) < 2 or not np.isfinite(a[-1]) or not np.isfinite(a[-2]) or a[-2] == 0:
        return np.nan
    return a[-1] / a[-2] - 1


def avg_prior12(a):
    """「Prior 12mo Avg.」= 最新月之前 12 个月的均值（不含当月）。"""
    a = np.asarray(a, float)
    if len(a) < 13:
        return float(np.nanmean(a[:-1])) if len(a) > 1 else float(a[0])
    return float(np.nanmean(a[-13:-1]))


def main():
    df = load()

    # ── 序列完整性体检：中间缺月必须响，不能静默降级 ──
    # 近期图的窗口一律由 tail_contiguous 取「末尾逐月连续段」。这个函数是为南向通
    # 2022-01~2025-06 那 40 个月的**真实停发**设计的（Exhibit 5 的图注专门讲它，
    # 缺口不用直线连 —— CONTRACT 规矩 3），所以对南向的空洞必须保留原行为。
    # 但对逐月必发的列，中间少一个月会让「末尾连续段」只剩最后 1 个点：25 点窗口塌成
    # 1 点、y/y 与 m/m 全变「—」、Exhibit 3 还会写出字面 NaN，而退出码仍是 0，
    # 页面照常发布且肉眼看不出 —— 正是 CONTRACT 规矩 5 要禁的「静默写 NaN 上线」。
    # 尾部半行（当前 2026-07 只有衍生品/IPO/南向）不受影响：那是各列自己的末月之后，
    # 不构成中间空洞，也是 fetch/hkex.py 声明的正常状态。
    GAPPY_OK = {'southbound_adt_hkdbn'}          # 唯一允许中间空洞的列，见上
    for c in [x for x in df.columns if x not in GAPPY_OK]:
        s = df[c].dropna()
        if len(s) < 2:
            continue
        holes = [str(p) for p in
                 pd.period_range(s.index[0], s.index[-1], freq='M').difference(s.index)]
        if holes:
            raise SystemExit(
                f'series/hkex.csv 的 {c} 在 {s.index[0]}~{s.index[-1]} 之间缺 {len(holes)} 个月：'
                f'{holes[:6]}{" …" if len(holes) > 6 else ""}。近期图窗口取末尾逐月连续段，'
                f'中间缺月会把 25 点窗口砍成 1 点并写出 NaN，请先补齐 series/hkex.csv 再重建')

    # 汇总表用「核心量指标已齐备」的最后一个月；衍生品 / IPO / 南向更新更快，图上保留最新月
    CORE = df['adt_hkdbn'].dropna()
    LATEST = CORE.index[-1]
    NEWEST = df.index[-1]
    dfc = df.loc[:LATEST].copy()

    for d in (df, dfc):
        d['deriv_adv_k'] = d['derivatives_adv_contracts'] / 1000.0
        d['sb_share'] = d['southbound_adt_hkdbn'] / d['adt_hkdbn'] * 100
        # 换手率代理：年化成交额 / 市值
        d['velocity'] = d['adt_hkdbn'] * 252 / (d['mktcap_hkdtn'] * 1000) * 100

    # ── 量→收入桥：现货交易费 = 成交额 x 有效交易费率（双边）──
    tf_eff = rate_series('trading_fee_effective_rate_both_sides')      # 由收入倒算
    tf_list = rate_series('trading_fee_listed_rate_per_side', 2.0)     # 挂牌费率，双边
    td = rate_series('trading_days')
    tf_m = to_monthly(tf_list, df.index)
    td_q = to_monthly(td, df.index)
    df['implied_tradefee_hkdbn'] = df['adt_hkdbn'] * (td_q / 3.0) * tf_m / 100.0
    BR_NOTE = ('Assumption: monthly cash trading-fee revenue = ADT x trading days x the statutory '
               'both-sides trading-fee rate published in the HKEX fee schedule (0.00565% per side). '
               'That rate is independent of reported revenue, so the bridge check below is a real test, '
               'not an identity.')

    cf = rate_series('clearing_fee_effective_rate_both_sides')
    cf_m = to_monthly(cf, df.index)
    df['implied_clearfee_hkdbn'] = df['adt_hkdbn'] * (td_q / 3.0) * cf_m / 100.0
    CLR_NOTE = ('Assumption: monthly clearing-fee revenue = ADT x trading days x the effective '
                f'both-sides clearing rate ({cf.index[-1]} = {cf.iloc[-1]:.5f}%, held flat after). '
                'Unlike the trading fee, this rate is back-solved from revenue, so it is a now-cast '
                'rather than a test.')

    imp_all = df['implied_tradefee_hkdbn'].dropna()
    cnt = pd.Series(1, index=imp_all.index).groupby(
        pd.PeriodIndex(imp_all.index).asfreq('Q')).sum()
    ok_q = list(cnt[cnt == 3].index)
    imp_q = imp_all.groupby(pd.PeriodIndex(imp_all.index).asfreq('Q')).sum()
    imp_q = imp_q.loc[[q for q in imp_q.index if q in ok_q]]
    act_q = rate_series('cash_seg_trading_fee_revenue', 1e-3)          # HKD_mn → HKD_bn

    ex = []

    # ══════════ Exhibit 2：ADT 水平柱（gsx.lvl_bar, win=25, show_mom=True）══════════
    adt = tail_contiguous(df['adt_hkdbn']).iloc[-25:]
    XL_ADT = [mlab(p) for p in adt.index]
    adt_v = adt.values
    ex.append({
        'n': 2, 'kind': 'gs_bar', 'fmt': 'f0', 'xlabels': XL_ADT,
        'title': 'Average daily turnover',
        'ylab': 'HK$bn / day', 'legend': 'Monthly ADT',
        'values': L(adt_v), 'avg12': round(avg_prior12(adt_v), 6),
        'yoy_txt': pctf(yoy(adt_v)),
        'note': f'原 deck 在此图上打了环比气泡：{mlab(adt.index[-1])} 的 ADT 为 '
                f'HK${adt_v[-1]:,.1f}bn/日，m/m {pctf(mom(adt_v), 1)}、y/y {pctf(yoy(adt_v), 1)}。'
                '虚线是前 12 个月均值（网页版式），原 PDF 该位置画的是次轴 y/y 折线，'
                'y/y 已改由左上角气泡给出。',
    })

    # ══════════ Exhibit 3：ADT m/m 变化率（gsx.chg_line, win=25, kind='mom'）══════════
    full_adt = tail_contiguous(df['adt_hkdbn'])
    mm = full_adt.pct_change() * 100
    mm = mm.iloc[-25:]
    ex.append({
        'n': 3, 'kind': 'gs_line', 'fmt': 'pct1', 'xlabels': [mlab(p) for p in mm.index],
        'title': 'ADT, m/m change',
        'ylab': '% m/m', 'values': L(mm.values),
        'note': '与 Exhibit 2 同一序列的环比。ADT 的月度波动本身就是这门生意的收入波动，'
                '所以水平值与变化率成对看。',
    })

    # ══════════ Exhibit 4：ADT 超长历史（gsx.long_line, circle=3）══════════
    adt_long = df['adt_hkdbn'].dropna()
    XL_LONG = [mlab(p) for p in adt_long.index]
    last3 = ' / '.join(f'{mlab(p)} {v:,.0f}' for p, v in adt_long.iloc[-3:].items())
    ex.append({
        'n': 4, 'kind': 'lines', 'fmt': 'f0', 'xlabels': XL_LONG, 'xstep': 6,
        'title': 'Full ADT history since 2019',
        'ylab': 'HK$bn / day',
        'series': [{'name': 'Average daily turnover', 'color': 'NAVY', 'values': L(adt_long.values)}],
        'note': f'Full disclosed history（{XL_LONG[0]} → {XL_LONG[-1]}，{len(adt_long)} 个月）。'
                f'原 deck 在末 3 个月打红圈标记，网页 lines 图型没有该标记，最新 3 个月为 {last3}'
                '（HK$bn/日）。',
    })

    # ══════════ Exhibit 5：整体 vs 南向（gsx.multi_line）══════════
    # 原 deck win=25，窗口里南向有 12 个月空缺（2022-01 起断档 40 个月，2025-07 才恢复公布）。
    # 网页 lines_endlabels 要在两端标数值、且做平滑，序列中不能有缺口 ——
    # 故窗口取「两条序列同时有值的连续末段」，缺口不用直线连（CONTRACT 规矩 3）。
    both = df[['adt_hkdbn', 'southbound_adt_hkdbn']].dropna()
    both = tail_contiguous(both['adt_hkdbn']).index.intersection(both.index)
    both = df.loc[sorted(both)]
    sb_win = both.iloc[-25:]
    ex.append({
        'n': 5, 'kind': 'lines_endlabels', 'fmt': 'f0',
        'xlabels': [mlab(p) for p in sb_win.index],
        'title': 'Total vs. southbound turnover',
        'ylab': 'HK$bn / day',
        'series': [
            {'name': 'Total market ADT', 'color': 'NAVY', 'values': L(sb_win['adt_hkdbn'].values)},
            {'name': 'Southbound ADT', 'color': 'MBLUE',
             'values': L(sb_win['southbound_adt_hkdbn'].values)},
        ],
        'note': 'Southbound carries a lower fee take, so mix matters to revenue. Its 40-month '
                'publication gap (2022-2024) is why it is shown here and not as a bar chart。'
                f'原 deck 的 25 个月窗口里南向有一半是空的；此处只画两条序列同时有值的连续末段'
                f'（{mlab(sb_win.index[0])} → {mlab(sb_win.index[-1])}，{len(sb_win)} 个月），'
                f'南向占整体 ADT 的比例已从 {sb_win["southbound_adt_hkdbn"].iloc[0] / sb_win["adt_hkdbn"].iloc[0] * 100:.1f}% '
                f'变为 {sb_win["southbound_adt_hkdbn"].iloc[-1] / sb_win["adt_hkdbn"].iloc[-1] * 100:.1f}%。',
    })

    # ══════════ Exhibit 6：衍生品 ADV（gsx.lvl_bar, win=25）══════════
    dv = tail_contiguous(df['deriv_adv_k']).iloc[-25:]
    dv_v = dv.values
    ex.append({
        # fmt 用 f0 而非 f0c：25 根柱的半栏图上，'1,731' 比柱距还宽，逗号会让相邻标签黏成一团
        'n': 6, 'kind': 'gs_bar', 'fmt': 'f0', 'xlabels': [mlab(p) for p in dv.index],
        'title': 'Derivatives average daily volume',
        'ylab': 'k contracts / day', 'legend': 'Monthly derivatives ADV',
        'values': L(dv_v), 'avg12': round(avg_prior12(dv_v), 6),
        'yoy_txt': pctf(yoy(dv_v)),
        'note': f'期货与期权合计，公司披露的原始单位是张数，此处除以 1,000 显示为「千张/日」'
                f'（核对表里给原始张数）。{mlab(dv.index[-1])} 的 ADV 为 {dv_v[-1]:,.0f} 千张/日，'
                f'y/y {pctf(yoy(dv_v), 1)}。衍生品比现货多披露一个月。',
    })

    # ══════════ Exhibit 7：季度 ADT（gsx.qtr_bar, win=14, how='mean'）══════════
    qs = df['adt_hkdbn'].dropna()
    qg = qs.groupby(pd.PeriodIndex(qs.index).asfreq('Q'))
    qmean = qg.mean()
    qcnt = qg.count()
    n_in_last = int(qcnt.iloc[-1])
    qv = qmean.values
    qyoy = np.array([(qv[i] / qv[i - 4] - 1) * 100 if i >= 4 and qv[i - 4] else np.nan
                     for i in range(len(qv))])
    qw = qmean.iloc[-14:]
    qy = qyoy[-14:]
    ex.append({
        'n': 7, 'kind': 'qtr_bar', 'fmt': 'f0', 'label_fmt': 'f0',
        'xlabels': [str(p) for p in qw.index],
        'title': 'ADT by quarter',
        'ylab': 'HK$bn / day', 'legend': 'Complete quarter',
        'values': L(qw.values), 'partial_months': n_in_last, 'qtr_months': 3,
        'line': {'name': 'y/y (RHS)', 'color': 'GREEN', 'values': LN(qy), 'yfmt': 'pct0'},
        'note': '季度值是该季各月 ADT 的<b>简单平均</b>（每日成交额的季度均值），不是季度合计 —— '
                'ADT 本身已经是「每日」口径，合计会随季内交易日数变化而失真。'
                f'最新季 {qw.index[-1]} 已含 {n_in_last} 个月'
                + ('（完整季）。' if n_in_last >= 3 else '，未满季与完整季不可比，右轴 y/y 已作废。'),
    })

    # ══════════ Exhibit 8：市值（gsx.lvl_bar, win=25, show_mom=True）══════════
    mc = tail_contiguous(df['mktcap_hkdtn']).iloc[-25:]
    mc_v = mc.values
    ex.append({
        'n': 8, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': [mlab(p) for p in mc.index],
        'title': 'Securities market capitalisation',
        'ylab': 'HK$tn', 'legend': 'Month-end market cap',
        'values': L(mc_v), 'avg12': round(avg_prior12(mc_v), 6),
        'yoy_txt': pctf(yoy(mc_v)),
        'note': f'期末口径。原 deck 在此图上打了环比气泡：{mlab(mc.index[-1])} 为 '
                f'HK${mc_v[-1]:,.1f}tn，m/m {pctf(mom(mc_v), 1)}、y/y {pctf(yoy(mc_v), 1)}。'
                '它是 Exhibit 9 换手率的分母。',
    })

    # ══════════ Exhibit 9：隐含换手率（gsx.lvl_bar, pct_series=True）══════════
    vel = tail_contiguous(df['velocity']).iloc[-25:]
    vel_v = vel.values
    vel_pp = vel_v[-1] - vel_v[-13] if len(vel_v) >= 13 else np.nan
    ex.append({
        'n': 9, 'kind': 'gs_bar', 'fmt': 'f0', 'xlabels': [mlab(p) for p in vel.index],
        'title': 'Implied market velocity',
        'ylab': '% of market cap, annualised', 'legend': 'Implied velocity (%)',
        'values': L(vel_v), 'avg12': round(avg_prior12(vel_v), 6),
        'yoy_txt': ppf(vel_pp),
        'note': 'ADT x 252 / market cap — the ratio GS uses to judge whether turnover is '
                'structurally higher。<b>推导值，非公司披露</b>：252 是惯例年化交易日数，'
                '不是当年实际交易日数；分母用当月期末市值。比率序列的同比用百分点差，'
                f'{mlab(vel.index[-1])} 为 {vel_v[-1]:,.1f}%，y/y {ppf(vel_pp, 1)}。',
    })

    # ══════════ Exhibit 10：隐含现货交易费收入（gsx.lvl_bar, dec=2）══════════
    # 单位由 HK$bn 改为 HK$mn（= 公司分部收入的披露单位）：charts.js 的 FMT 里没有 f2，
    # 传 'f2' 会静默退回 f1，0.72bn 会被印成 0.7 —— 换成 mn 后用 f0c 反而更精确。
    tfee = tail_contiguous(df['implied_tradefee_hkdbn']).iloc[-25:] * 1000.0
    tfee_v = tfee.values
    ex.append({
        'n': 10, 'kind': 'gs_bar', 'fmt': 'f0c', 'xlabels': [mlab(p) for p in tfee.index],
        'title': 'Implied cash trading-fee revenue',
        'ylab': 'HK$mn / month', 'legend': 'Implied trading fee',
        'values': L(tfee_v), 'avg12': round(avg_prior12(tfee_v), 6),
        'yoy_txt': pctf(yoy(tfee_v)),
        'note': BR_NOTE + f' 费率与交易日数只有 {tf_list.index[0]} 起 {len(tf_list)} 个季度，'
                          f'故本序列自 {mlab(tfee.index[0])} 起；季内各月同费率，最新季之后沿用。'
                          '月度交易日数按「季度交易日数 ÷ 3」摊，不是当月实际交易日数。'
                          '单位用 HK$mn（公司分部收入的披露单位），原 deck 是 HK$bn 保留两位小数。',
    })

    # ══════════ Exhibit 11：桥的检验（gsx.implied_vs_actual）══════════
    qidx = [q for q in imp_q.index if q in act_q.index][-14:]
    imp = np.array([imp_q[q] for q in qidx], float) * 1000.0     # HK$bn → HK$mn（披露单位）
    act = np.array([act_q[q] for q in qidx], float) * 1000.0
    err = np.where(act != 0, (imp / act - 1) * 100, np.nan)
    mae = float(np.nanmean(np.abs(err)))
    ex.append({
        'n': 11, 'kind': 'grouped_bars', 'fmt': 'f0c',
        'xlabels': [str(q) for q in qidx],
        'title': 'Bridge check: statutory rate vs. reported fees',
        'ylab': 'HK$mn / quarter', 'ylab2': 'Error (%)', 'bar_labels': False,
        'groups': [
            {'name': 'Implied by the bridge', 'color': 'BLUE', 'values': L(imp)},
            {'name': 'Actually reported', 'color': 'NAVY', 'values': L(act)},
        ],
        'line': {'name': 'Error (RHS)', 'color': 'RED', 'values': L(err), 'yfmt': 'pct1'},
        'note': 'The implied bar applies the published statutory rate to all turnover; the reported '
                'bar is the actual cash-segment trading-fee line. The gap is fee-exempt turnover '
                '(market makers, certain ETF and structured-product flow).'
                f'  Mean absolute error over the window: {mae:.1f}%.'
                f' 误差始终为正、区间 {np.nanmin(err):+.1f}% ~ {np.nanmax(err):+.1f}%，'
                '说明免费成交占比稳定 —— 这条误差线一旦变窄或变宽，就是 mix 在动。'
                f'只有 {len(qidx)} 个季度可比，因为公司分部收入拆分只回溯到 {qidx[0]}。',
    })

    # ══════════ Exhibit 12：有效费率 vs 法定费率（gsx.multi_line, dec=4）══════════
    # 原 deck 用「% of turnover」保留 4 位小数；网页格式器最多 1 位小数（FMT 里没有 f2），
    # 0.0097% 会被印成 0.0%。改成「每成交 HK$1m 收多少费」，乘 1e4 后 f1 恰好等价于原来的 4 位小数。
    rq = [q for q in tf_eff.index if q in tf_list.index]
    XL_RATE = [mlab(q.asfreq('M', 'end')) for q in rq]
    eff_r = np.array([tf_eff[q] for q in rq], float) * 1e4
    lst_r = np.array([tf_list[q] for q in rq], float) * 1e4
    ex.append({
        'n': 12, 'kind': 'lines_endlabels', 'fmt': 'f1', 'xlabels': XL_RATE,
        'title': 'Fee capture: effective vs. statutory rate',
        'ylab': 'HK$ of trading fee per HK$1m traded',
        'series': [
            {'name': 'Effective (revenue / turnover)', 'color': 'NAVY', 'values': L(eff_r)},
            {'name': 'Statutory schedule rate', 'color': 'GRAY', 'values': L(lst_r)},
        ],
        'note': 'The persistent shortfall is the share of turnover that pays no trading fee. '
                'Watching this ratio is how you catch a mix shift before it shows up in revenue。'
                '单位由原 deck 的「% of turnover（4 位小数）」改为「每成交 HK$1m 的交易费」'
                f'（× 10,000，等价换算）：法定 HK${lst_r[-1]:,.1f} 恒定，'
                f'实收 HK${eff_r[-1]:,.1f}，捕获率 {eff_r[-1] / lst_r[-1] * 100:.1f}%。'
                'x 轴标的是各季末月份。',
    })

    # ══════════ Exhibit 13：隐含现货清算费收入（gsx.lvl_bar, dec=2）══════════
    cfee = tail_contiguous(df['implied_clearfee_hkdbn']).iloc[-25:] * 1000.0   # → HK$mn
    cfee_v = cfee.values
    ex.append({
        'n': 13, 'kind': 'gs_bar', 'fmt': 'f0c', 'xlabels': [mlab(p) for p in cfee.index],
        'title': 'Implied cash clearing-fee revenue',
        'ylab': 'HK$mn / month', 'legend': 'Implied clearing fee',
        'values': L(cfee_v), 'avg12': round(avg_prior12(cfee_v), 6),
        'yoy_txt': pctf(yoy(cfee_v)),
        'note': CLR_NOTE + ' 清算费有最低/最高收费与 CCASS 结算费等分项，倒算出的有效费率把这些'
                           '一并吸收进去了，所以它随 mix 漂移，不能当法定费率读。',
    })

    # ══════════ Exhibit 14：衍生品 ADV 超长历史（gsx.long_line）══════════
    dv_long = df['deriv_adv_k'].dropna()
    XL_DV = [mlab(p) for p in dv_long.index]
    dv3 = ' / '.join(f'{mlab(p)} {v:,.0f}' for p, v in dv_long.iloc[-3:].items())
    ex.append({
        'n': 14, 'kind': 'lines', 'fmt': 'f0c', 'xlabels': XL_DV, 'xstep': 6,
        'title': 'Derivatives ADV history since 2019',
        'ylab': 'k contracts / day',
        'series': [{'name': 'Derivatives ADV', 'color': 'NAVY', 'values': L(dv_long.values)}],
        'note': f'{XL_DV[0]} → {XL_DV[-1]}，{len(dv_long)} 个月。原 deck 在末 3 个月打红圈，'
                f'网页 lines 图型没有该标记，最新 3 个月为 {dv3}（千张/日）。',
    })

    # ══════════ Exhibit 15：市值超长历史（gsx.long_line）══════════
    mc_long = df['mktcap_hkdtn'].dropna()
    XL_MC = [mlab(p) for p in mc_long.index]
    mc3 = ' / '.join(f'{mlab(p)} {v:,.1f}' for p, v in mc_long.iloc[-3:].items())
    ex.append({
        'n': 15, 'kind': 'lines', 'fmt': 'f1', 'xlabels': XL_MC, 'xstep': 6,
        'title': 'Market capitalisation since 2019',
        'ylab': 'HK$tn',
        'series': [{'name': 'Securities market cap', 'color': 'NAVY', 'values': L(mc_long.values)}],
        'note': f'{XL_MC[0]} → {XL_MC[-1]}，{len(mc_long)} 个月，期末口径。原 deck 在末 3 个月打红圈，'
                f'网页 lines 图型没有该标记，最新 3 个月为 {mc3}（HK$tn）。'
                '与 Exhibit 4 对照看：市值这一轮并没有跟着成交额同步扩张，换手率（Exhibit 9）才是差额。',
    })

    # ══════════ Exhibit 16：逐年 ADT 路径（gsx.year_lines, n_years=6, cumulative=False）══════════
    yrs = sorted({p.year for p in adt_long.index})[-6:]
    yseries = []
    for y in yrs:
        vals = [None] * 12
        for p, v in adt_long.items():
            if p.year == y:
                vals[p.month - 1] = round(float(v), 6)
        yseries.append({'name': str(y), 'values': vals})
    ex.append({
        'n': 16, 'kind': 'year_lines', 'fmt': 'f0', 'label_fmt': 'f0',
        'xlabels': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug',
                    'Sep', 'Oct', 'Nov', 'Dec'],
        'title': 'ADT path by year',
        'ylab': 'HK$bn / day', 'series': yseries, 'highlight': len(yrs) - 1,
        'note': f'Red = current year。画的是每月 ADT 的水平值（原 deck cumulative=False），'
                f'不是年初至今累计。{yrs[-1]} 年只有 {sum(1 for v in yseries[-1]["values"] if v is not None)} '
                f'个月，后面留空。',
    })

    # ══════════ Exhibit 17：ADT 热力矩阵（gsx.heat_matrix, n_years=8）══════════
    def heat(s, n_years=8):
        ys = sorted({p.year for p in s.index})[-n_years:]
        M = [[None] * 12 for _ in ys]
        for p, v in s.items():
            if p.year in ys:
                M[ys.index(p.year)][p.month - 1] = round(float(v), 6)
        return [str(y) for y in ys], M

    rows17, M17 = heat(adt_long)
    ex.append({
        'n': 17, 'kind': 'heat_matrix', 'fmt': 'f0',
        'title': 'Average daily turnover (HK$bn)',
        'rows': rows17, 'matrix': M17, 'legend': 'Average daily turnover (HK$bn)',
        'row_head': '年',
        'note': 'Green = heavier turnover。色标取全部有限值的 5/95 分位，一两个离群月不会把整表压平。',
    })

    rows18, M18 = heat(dv_long)
    ex.append({
        'n': 18, 'kind': 'heat_matrix', 'fmt': 'f0c',
        'title': 'Derivatives ADV (k contracts / day)',
        'rows': rows18, 'matrix': M18, 'legend': 'Derivatives ADV (k contracts / day)',
        'row_head': '年',
        'note': 'Green = heavier derivatives activity。同 Exhibit 17 的色标口径（5/95 分位）。'
                '与 Exhibit 17 对照：衍生品的季节性形状与现货并不完全同步。',
    })

    # ══════════ Exhibit 1：汇总表 ══════════
    cur, prv, yag = LATEST, LATEST - 1, LATEST - 12
    SUM = [
        ('group', 'Cash market drivers'),
        ('row', 'Average daily turnover (HK$bn)', 'adt_hkdbn', 1, 'ratio'),
        ('row', 'Southbound ADT (HK$bn)', 'southbound_adt_hkdbn', 1, 'ratio'),
        ('row', 'Southbound share of ADT (%)', 'sb_share', 1, 'pp'),
        ('row', 'Implied market velocity (%)', 'velocity', 1, 'pp'),
        ('group', 'Derivatives'),
        ('row', 'ADV of futures and options (k contracts)', 'deriv_adv_k', 0, 'ratio'),
        ('group', 'Market size and primary market'),
        ('row', 'Securities market cap (HK$tn)', 'mktcap_hkdtn', 1, 'ratio'),
        ('row', 'New listings in the month', 'new_listings', 0, 'abs'),
        ('row', 'IPO funds raised (HK$bn)', 'ipo_funds_hkdbn', 1, 'ratio'),
    ]

    def chg(a, b, mode):
        if not (np.isfinite(a) and np.isfinite(b)):
            return None
        if mode in ('pp', 'abs'):
            return float(a - b)
        if b == 0 or a * b < 0:
            return None
        return float(a / b - 1) * 100

    def chg_cell(v, mode, dec):
        if v is None:
            return {'v': ''}
        if mode == 'pp':
            txt = f'{v * 100:+.0f}bp' if abs(v) < 1 else f'{v:+.2f}pp'
        elif mode == 'abs':
            txt = f'{v:+,.{max(0, dec)}f}'
        else:
            txt = f'{v:+.1f}%'
        return {'v': txt, 'cls': 'pos' if v > 0 else ('neg' if v < 0 else '')}

    srows = []
    for item in SUM:
        if item[0] == 'group':
            srows.append({'kind': 'group', 'label': item[1]})
            continue
        _, lab, col, dec, mode = item
        s = dfc[col].dropna()
        c = float(s.get(cur, np.nan)) if cur in s.index else np.nan
        p1 = float(s.get(prv, np.nan)) if prv in s.index else np.nan
        p12 = float(s.get(yag, np.nan)) if yag in s.index else np.nan
        hist = s.iloc[-36:].values.astype(float)
        pc = {'v': ''}
        if np.isfinite(c) and len(hist) >= 8:
            d = np.diff(hist)
            # 单调序列的分位恒为 100，是噪音不是信息（CONTRACT §2）
            if not (len(d) and float((d >= 0).sum()) / len(d) >= 0.90):
                pv = float((hist < c).sum()) / max(1, len(hist) - 1) * 100
                pc = {'v': f'{pv:.0f}',
                      'cls': 'hi' if pv >= 66 else ('lo' if pv <= 33 else '')}
        srows.append({'label': lab, 'cells': [
            {'v': num(c, dec)}, {'v': num(p1, dec)}, {'v': num(p12, dec)},
            chg_cell(chg(c, p1, mode), mode, dec),
            chg_cell(chg(c, p12, mode), mode, dec),
            pc,
        ]})

    summary = {
        'title': f'HKEX monthly market highlights — {mlab(LATEST)}',
        'heads': [f'本月 {mlab(cur)}', f'上月 {mlab(prv)}', f'去年同月 {mlab(yag)}',
                  'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': srows,
        'note': 'Velocity is derived as ADT x 252 / market cap, not a disclosed figure. '
                'New-listing and IPO series have gaps in the published monthly summary. '
                '3Y %ile = 当月读数高于最近 36 个<b>已公布</b>观测里多少百分比的观测；'
                '比率类指标（南向占比、换手率）的差异一律用 pp／bp，不用百分比的百分比变化。'
                '南向 ADT 2022-01 起断档 40 个月，它那一行的 36 个观测里混了 2020-21 的月份，'
                '不是连续的近 36 个月；去年同月无披露时 y/y 留空。',
    }

    # ══════════ Exhibit 19：核对表（官方原始单位，不换算）══════════
    tail = df.iloc[-13:]
    trows = []
    for p, r in tail.iterrows():
        trows.append({
            'xl': mlab(p),
            'adt': None if not np.isfinite(r['adt_hkdbn']) else f"{r['adt_hkdbn']:,.3f}",
            'mcap': None if not np.isfinite(r['mktcap_hkdtn']) else f"{r['mktcap_hkdtn']:,.4f}",
            'sb': None if not np.isfinite(r['southbound_adt_hkdbn']) else f"{r['southbound_adt_hkdbn']:,.3f}",
            'dv': None if not np.isfinite(r['derivatives_adv_contracts']) else f"{r['derivatives_adv_contracts']:,.0f}",
            'nl': None if not np.isfinite(r['new_listings']) else f"{r['new_listings']:,.0f}",
            'ipo': None if not np.isfinite(r['ipo_funds_hkdbn']) else f"{r['ipo_funds_hkdbn']:,.3f}",
        })
    table = {
        'n': 19, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）',
        'idx': '月份',
        'cols': [['ADT (HK$bn)', 'adt'], ['Market cap (HK$tn)', 'mcap'],
                 ['Southbound ADT (HK$bn)', 'sb'],
                 ['Derivatives ADV (contracts)', 'dv'],
                 ['New listings', 'nl'], ['IPO funds (HK$bn)', 'ipo']],
        'rows': trows,
    }

    # ══════════ notes ══════════
    notes = [
        '<b>数据源</b>：HKEX 每月公布的 Monthly Market Highlights（月度市场概况）与季度业绩'
        '中的现货分部收入、费率与交易日数。版式沿用 Goldman Sachs GIR 两份 HKEX note'
        '（「New listings and profit growth inflection to drive sustainable ADT growth」'
        'Exhibit 1-15 与「Multiple tailwinds in 2026E despite weak Nov ADT」Exhibit 1-28）：'
        '三层时间窗（超长历史判周期位置 / 中长期判趋势 / 近 25 个月讲当下）、双图开场、驱动量置顶。',

        f'<b>⚠️ 各序列的截止月不一样</b>：现货 ADT、市值、新上市家数到 {mlab(LATEST)}；'
        f'衍生品 ADV、IPO 募资、南向 ADT 已有 {mlab(NEWEST)}。'
        '汇总表与页面顶部的「数据截至」一律取<b>核心量指标齐备的最后一个月</b>，'
        '各图则各自画到自己序列的最新月 —— 所以 Exhibit 6/14/18 的末端比 Exhibit 2/4/17 多一个月。',

        '<b>⚠️ 南向 ADT 有 40 个月断档</b>：2022-01 至 2025-06 的月度概况未披露南向成交额，'
        '2025-07 起恢复。缺口不用直线连（不可比的相邻期不能画成连续序列），'
        'Exhibit 5 因此只画恢复披露后的连续段，汇总表里南向那一行的「去年同月」也是空的。',

        '<b>换手率是推导值，不是披露值</b>：Implied market velocity = ADT × 252 ÷ 市值。'
        '252 是惯例年化交易日数（不是港股当年实际交易日数），分母用当月期末市值。'
        '它回答的是「这轮成交放大里有多少来自存量资产周转加快、而不是市值本身变大」。',

        '<b>量→收入桥的两条假设，性质不同</b>：'
        '（a）现货交易费用<b>法定挂牌费率</b>（每边 0.00565%，双边 0.0113%）× ADT × 交易日数 —— '
        '这个费率独立于已披露收入，所以 Exhibit 11 是一次<b>真检验</b>；'
        '（b）现货清算费用<b>由收入倒算</b>的有效费率，只能算 now-cast，不能当检验。'
        '两者标题都带 Implied。',

        f'<b>费率序列只有 {tf_list.index[0]} 起 {len(tf_list)} 个季度</b>：季内各月共用该季费率，'
        '最新季之后沿用最后一个已知值；月度交易日数按「季度交易日数 ÷ 3」摊，'
        f'不是当月实际交易日数。因此 Exhibit 10 / 13 的隐含收入序列自 {mlab(tfee.index[0])} 起，'
        '早于此的月份不画（宁可短，不拿近似值糊）。',

        f'<b>桥的误差是结构性的，不是估算误差</b>：Exhibit 11 显示按法定费率算出的交易费'
        f'系统性高于实际披露 {np.nanmin(err):+.1f}% ~ {np.nanmax(err):+.1f}%（窗口内平均绝对误差 {mae:.1f}%），'
        '差额是不付交易费的成交 —— 做市商、部分 ETF 与结构性产品流。'
        '这条误差线一旦变窄或变宽，就是成交结构在动，会先于收入体现出来。',

        '<b>网页版式与原 PDF 的已知差异</b>：'
        '（1）gs_bar 的虚线是「前 12 个月均值」，原 PDF 该位置画的是次轴 y/y 折线，'
        'y/y 改由图左上角气泡给出，数字同源；'
        '（2）网页图表引擎的数值格式器最多一位小数，所以两位小数的口径改用更细的单位表达：'
        'Exhibit 10 / 11 / 13 由 HK$bn 改为 <b>HK$mn</b>（也正是公司分部收入的披露单位），'
        'Exhibit 12 由「% of turnover（4 位小数）」改为「每成交 HK$1m 收多少交易费」'
        '（× 10,000 的等价换算）—— 换算是恒等的，精度只增不减；'
        '（3）Exhibit 4 / 14 / 15 在原 deck 里给最新 3 个月打了红圈，网页 lines 图型没有该标记，'
        '这三个月的具体数值改写在各自图注里。',

        '<b>3Y %ile</b> = 当月读数高于最近 36 个已公布观测里多少百分比的观测；'
        '几乎只增不减的序列（判据：差分非负的比例 ≥ 90%）分位恒为 100，是噪音不是信息，'
        '那一行留空。比率类指标的变化一律用 pp／bp。',

        '<b>核对表（Exhibit 19）保持官方原始单位</b>：衍生品 ADV 给原始张数（不是千张），'
        'ADT／南向／IPO 给 HK$bn、市值给 HK$tn，小数位与官方披露一致，可与 Monthly Market '
        'Highlights 原文逐格对齐。所有图表的数值都由这套原始序列在 Python 侧算好并格式化，'
        '页面不做任何计算。',
    ]

    # ── headline / hub_line：整行锁死在 LATEST，不许各取各的 [-1] ──
    # 这一行紧挨着抬头的「数据截至 {through_label}」，首页卡片上也已经有一个权威月份徽章，
    # 两处都没有逐指标标月份的位置 —— 所以整行必须与 data_through 同口径。
    # 取各序列自己的末值会串到 NEWEST（衍生品与南向比现货多披露一个月），
    # 于是同一页对同一指标给出两个互斥读数（衍生品 1,731 vs 1,926、南向 129.2 vs 130.0），
    # 与本页 Exhibit 1 和 /exchanges/ Exhibit 1 直接打架。
    # 领先一个月的读数不会丢：Exhibit 6 / 18 / 19 逐点带月份标签地展示它们。
    def hv(col, name):
        """headline 用的序列：截到 LATEST 的末尾连续段，并校验末月确实是 LATEST。"""
        s = tail_contiguous(df[col].loc[:LATEST]).iloc[-25:]
        if not len(s) or s.index[-1] != LATEST:
            raise SystemExit(f'headline 口径月错位：{name}({col}) 末月 = '
                             f'{s.index[-1] if len(s) else "空序列"}，data_through = {LATEST}')
        return s.values

    h_adt = hv('adt_hkdbn', 'ADT')
    h_sb = hv('southbound_adt_hkdbn', '南向 ADT')
    h_dv = hv('deriv_adv_k', '衍生品 ADV')
    h_mc = hv('mktcap_hkdtn', '市值')
    h_vel = hv('velocity', '换手率')
    h_tfee = hv('implied_tradefee_hkdbn', '隐含现货交易费') * 1000.0

    headline = (
        f'ADT HK${h_adt[-1]:,.1f}bn/日（{pctf(yoy(h_adt), 1)} y/y，{pctf(mom(h_adt), 1)} m/m）'
        f' · 南向 ADT HK${h_sb[-1]:,.1f}bn'
        f' · 衍生品 ADV {h_dv[-1]:,.0f} 千张/日（{pctf(yoy(h_dv), 1)} y/y）'
        f' · 市值 HK${h_mc[-1]:,.1f}tn · 换手率 {h_vel[-1]:,.1f}%'
        f' · 隐含现货交易费 HK${h_tfee[-1]:,.0f}mn/月'
    )

    payload = {
        'ticker': TICKER,
        'tracker': 'HKEX Monthly Market Tracker',
        'title': f'Hong Kong Exchanges (0388.HK)：月度市场统计跟踪 — {LATEST.year} 年 {LATEST.month} 月',
        'data_through': str(LATEST),
        'through_label': f'{LATEST.year} 年 {LATEST.month} 月',
        'subtitle': f'数据源 HKEX Monthly Market Highlights + 季度业绩费率表 · '
                    f'覆盖 {mlab(adt_long.index[0])} → {mlab(NEWEST)}（核心量指标至 {mlab(LATEST)}）· '
                    f'版式沿用 Goldman Sachs GIR 的 HKEX exhibit 体例 · 仅图，无观点',
        'headline': headline,
        'hub_line': f'ADT HK${h_adt[-1]:,.0f}bn/日（{pctf(yoy(h_adt))} y/y）· '
                    f'衍生品 ADV {h_dv[-1]:,.0f}k 张/日',
        'source': SRC,
        'xlabels': XL_ADT,
        'xlabels_long': XL_LONG,
        'summary': summary,
        'exhibits': ex,
        'table': table,
        'notes': notes,
        'footer': '数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
                  '仅供个人研究，不构成投资建议 · 所有推导值均已在图注中标注 Implied 与假设',
    }

    # 兜底：json.dump 对 float('nan') 会写出**字面 NaN** —— 那不是合法 JSON，
    # 但 Python 的 json.loads 与浏览器的 window.DASH = 都照单全收，于是坏 payload
    # 能一路发布而不报错（CONTRACT 规矩 5）。缺值一律走 LN() 出 null，不能出 NaN。
    # 这里原本有一份本地的 scan_nonfinite，已并入 build/payload_guard.py 统一实现
    # （多一条：还扫已被 f-string 格式化进展示串的小写 nan，本地那版看不见）。
    path = os.path.join(ROOT, 'data', f'{TICKER}.js')
    payload_guard.write_dash(path, payload, TICKER)

    print(f'核心月 {LATEST} | 最新月 {NEWEST} | 长历史 {adt_long.index[0]} → {adt_long.index[-1]}'
          f'（{len(adt_long)} 个月）')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）+ '
          f'Exhibit {table["n"]} 核对表')
    print(f'写出 {path}  ({os.path.getsize(path) / 1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
