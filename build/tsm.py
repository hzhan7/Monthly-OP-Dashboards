# -*- coding: utf-8 -*-
"""TSMC (2330.TW) 月度营收 —— 网页看板数据生成器（data/tsm.js）。

移植自 build/build_tsm.py（matplotlib / PDF 版），exhibit 顺序、编号、标题文案、
图注与窗口设置逐条对齐；数据全部来自 series/tsm.csv、series/tsm_fx.csv、
series/tsm_guidance.csv 三个文件，不引入任何外部估计。

口径（与 PDF 版同源）：
  · 唯一的官方披露字段是「合并营收（NT$mn，未经查核）」，台湾法定次月 10 日前公告。
    月营收 NT$bn / 3 个月移动平均 / QTD / YTD / TTM / 占 TTM 比重全部由它派生。
  · y/y 有两个来源：公司随营收一并公告的 yoy_pct（用于热力矩阵与核对表），
    以及本脚本按序列自算的 y/y（用于 Ex2 的右轴线、Ex5 的季度 y/y）。两者极小差异
    来自公司口径的四舍五入，不做人工对齐。
  · 美元口径一律是**推导值（Implied）**：NT$ 营收 ÷ 当月平均 NTD/USD 汇率，
    不是公司披露的美元营收。汇率贡献 = NT$ y/y − US$ y/y（百分点）。
  · 指引区间与实际（Ex6/Ex7）来自季度业绩说明会，与月营收序列不同源。

⚠️ 断点：TSMC 月营收自 2016-01 起口径连续，未发生并表/重述，故全站未设 break_at，
   也未设截轴 ycap/yfloor —— 不是忘了设，是确实没有。

用法：python3 build/tsm.py
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
DATA = os.path.join(ROOT, 'data')

SRC = 'Source: TSMC monthly revenue reports; format after Goldman Sachs GIR'
SRC_G = 'Exhibit source: TSMC quarterly earnings-call guidance and reported results.'
SRC_FX = 'Exhibit source: monthly average NTD/USD (FRED series EXTAUS).'
ASSUMP = ('Assumption: NT$ converted at the month average NTD/USD rate — an approximation')

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
CN_MONTH = None


def mlab(p):
    """与 gsx.mlab 同：'Jun-26'。"""
    return p.strftime('%b-%y')


def num(v, nd=6):
    """写进 payload 的数值：非有限一律 None，有限的统一定点舍入，保证幂等。"""
    if v is None:
        return None
    f = float(v)
    if not np.isfinite(f):
        return None
    return round(f, nd)


def L(seq, nd=6):
    return [num(v, nd) for v in seq]


def f(v, dec=1, pct=False, money=''):
    """与 gsx._fmt 同：千分位 + 固定小数位；非有限返回 '—'。"""
    if v is None or not np.isfinite(float(v)):
        return '—'
    s = f'{float(v):,.{dec}f}'
    return (money + s + '%') if pct else (money + s)


def sgn(v, dec=1, suffix='%'):
    if v is None or not np.isfinite(float(v)):
        return '—'
    return f'{float(v):+,.{dec}f}{suffix}'


# ────────────────────────────── 读数据 ──────────────────────────────
def load():
    p = os.path.join(SERIES, 'tsm.csv')
    df = pd.read_csv(p)
    for c in ('month', 'revenue_ntd_mn', 'yoy_pct'):
        if c not in df.columns:
            raise SystemExit(f'series/tsm.csv 缺列 {c}')
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    df = df.set_index('month').sort_index()
    if df.index.has_duplicates:
        raise SystemExit('series/tsm.csv 有重复月份')
    # 月份必须逐月连续 —— 断档会让相隔数月的柱画成相邻柱（假时间轴）
    gaps = [(df.index[i] - df.index[i - 1]).n for i in range(1, len(df))]
    if any(g != 1 for g in gaps):
        bad = [str(df.index[i]) for i in range(1, len(df)) if (df.index[i] - df.index[i - 1]).n != 1]
        raise SystemExit(f'series/tsm.csv 月份不连续，断在 {bad}')

    fxp = os.path.join(SERIES, 'tsm_fx.csv')
    fx = pd.read_csv(fxp)
    fx['month'] = pd.PeriodIndex(fx['month'], freq='M')
    fx = fx.set_index('month').sort_index()['ntd_per_usd'].astype(float)

    g = pd.read_csv(os.path.join(SERIES, 'tsm_guidance.csv'))
    return df, fx, g


def main():
    df, fx, g = load()

    rev = df['revenue_ntd_mn'].astype(float)
    LATEST = rev.index[-1]

    # ── 派生序列（逐行对齐 build_tsm.py）──
    rev_bn = rev / 1000.0
    rev_3ma = rev.rolling(3).mean() / 1000.0
    ytd_bn = rev.groupby(rev.index.year).cumsum() / 1000.0
    qkey = rev.index.asfreq('Q')
    qtd_bn = rev.groupby(qkey).cumsum() / 1000.0
    ttm = rev.rolling(12).sum()
    share_ttm = rev / ttm * 100
    ttm_bn = ttm / 1000.0
    yoy = df['yoy_pct'].astype(float)                    # 公司公告的 y/y

    fx_al = fx.reindex(rev.index)
    if fx_al.isna().any():
        miss = [str(p) for p in fx_al.index[fx_al.isna()]]
        raise SystemExit(f'series/tsm_fx.csv 缺月份 {miss}')
    rev_usdmn = rev / fx_al                              # 假设：按当月平均汇率折算
    yoy_usd = rev_usdmn.pct_change(12) * 100
    fx_contrib = yoy - yoy_usd                           # 同比之差 = 汇率贡献（pp）

    # 本脚本自算的月度 y/y（Ex2 右轴）
    yoy_self = rev.pct_change(12) * 100

    # ── 季度指引 vs 实际 ──
    g['qlabel'] = [x[:4] + 'Q' + x[-1] for x in g['quarter']]
    g = g.set_index('qlabel')
    g_mid = (g['guide_low_usdbn'].astype(float) + g['guide_high_usdbn'].astype(float)) / 2
    g_act = pd.to_numeric(g['actual_rev_usdbn'], errors='coerce')
    beat = (g_act / g_mid - 1) * 100
    beat_idx = pd.PeriodIndex([f'{q[:4]}-{int(q[-1]) * 3:02d}' for q in g.index], freq='M')
    beat_s = pd.Series(beat.values, index=beat_idx).dropna()

    # 当季 QTD（美元）：当季已公布月份的 NT$ 累计 ÷ 当季平均汇率
    qtd_ntd = rev.groupby(qkey).sum()
    qtd_n = rev.groupby(qkey).count()
    fxq = fx_al.groupby(qkey).mean()
    CQ = rev.index[-1].asfreq('Q')
    QTD_N = int(qtd_n.get(CQ, 0))
    QTD_USD = float(qtd_ntd.get(CQ, np.nan) / 1000.0 / fxq.get(CQ, np.nan)) if QTD_N else float('nan')

    # ── x 轴标签 ──
    ALL = list(rev.index)
    XL_LONG = [mlab(p) for p in ALL]
    XL13 = [mlab(p) for p in ALL[-13:]]

    def win_labels(n):
        return [mlab(p) for p in ALL[-n:]]

    # ══════════════════ Exhibit 1：汇总表 ══════════════════
    cur, prv, yag = ALL[-1], ALL[-1] - 1, ALL[-1] - 12
    heads = [mlab(cur), mlab(prv), mlab(yag), 'm/m', 'y/y', '3Y %ile']

    def pctile36(s, c):
        """近 36 个月分位。单调序列（diff>=0 占比 ≥90%）留空 —— 分位恒 ~100 是噪音。"""
        h = s.dropna().iloc[-36:]
        if len(h) < 8 or not np.isfinite(c):
            return None
        d = np.diff(h.values)
        if len(d) and float((d >= 0).sum()) / len(d) >= 0.90:
            return None
        return float((h.values < c).sum()) / max(1, len(h) - 1) * 100

    def chg(a, b, mode):
        if not (np.isfinite(a) and np.isfinite(b)):
            return None
        if mode == 'pp':
            return float(a - b)
        if b == 0 or a * b < 0:
            return None
        return float(a / b - 1) * 100

    def chg_txt(v, mode, inv=False):
        """比率类用 pp/bp（|v|<1 用 bp），其余用百分比变化。返回 (文本, cls)。"""
        if v is None:
            return '', ''
        good = (v < 0) if inv else (v > 0)
        cls = 'pos' if good else ('neg' if v != 0 else '')
        if mode == 'pp':
            txt = f'{v * 100:+.0f}bp' if abs(v) < 1 else f'{v:+.2f}pp'
        else:
            txt = f'{v:+.1f}%'
        return txt, cls

    # 末位 cum = True 标记「周期内累计」序列（QTD/YTD）—— 跨期归零的锯齿序列，
    # 它的 m/m 与 3Y %ile 两列在结构上就没有信息，一律留空（详见循环里的注释）。
    SUM_ROWS = [
        ('group', 'Revenue', None, None, None, None, None, False),
        ('row', 'Monthly revenue (NT$bn)', rev_bn, 1, False, 'ratio', False, False),
        ('row', '3-month moving avg. (NT$bn)', rev_3ma, 1, False, 'ratio', False, False),
        ('group', 'Cumulative', None, None, None, None, None, False),
        ('row', 'Quarter-to-date (NT$bn)', qtd_bn, 1, False, 'ratio', False, True),
        ('row', 'Year-to-date (NT$bn)', ytd_bn, 1, False, 'ratio', False, True),
        ('group', 'Seasonality', None, None, None, None, None, False),
        ('row', '% of trailing-12-month revenue', share_ttm, 2, True, 'pp', False, False),
    ]
    srows, blanked, cum_blanked = [], [], []
    for kind, lab, s, dec, pct, mode, inv, cum in SUM_ROWS:
        if kind == 'group':
            srows.append({'kind': 'group', 'label': lab})
            continue
        c = float(s.get(cur, np.nan))
        p1 = float(s.get(prv, np.nan))
        p12 = float(s.get(yag, np.nan))
        mm, yy = chg(c, p1, mode), chg(c, p12, mode)
        mtx, mcls = chg_txt(mm, mode, inv)
        ytx, ycls = chg_txt(yy, mode, inv)
        if cum:
            # 周期内累计行的两列结构性噪音，一并留空：
            #  · m/m：同期内分子分母只差一个月，恒等于「上月累计 + 当月营收」
            #    （Jun-26：827.7 + 442.7 = 1,270.4 → +53.5%），跨期时又变成 1 个月比
            #    3/12 个月（Jan-26 会印 QTD −61.6%、YTD −89.5% 并涂红，而当月 y/y 是 +36.8%）。
            #    两种情形都不可比，且符号由日历位置决定 —— 算出来再上色只会误导。
            #  · 3Y %ile：分位池混装 1/2/3 个月量纲的累计值，读数由「本月是期内第几个月」
            #    决定 —— 实测季内第 1/2/3 月分别锚在 29–43 / 77–89 / 97–100，组间差碾压组内差。
            #    （pctile36 的单调判据抓不住这种带周期重置的锯齿：YTD diff>=0 占比 0.914 会留空，
            #    QTD 只有 0.686 就漏过去了 —— 漏过去纯粹因为它归零更频繁，不是因为更有信息。）
            # 可比的口径是 y/y：QTD 是 3 个月 vs 3 个月、YTD 是 6 个月 vs 6 个月，保留。
            mtx, mcls = '', ''
            cum_blanked.append(lab)
        pc = None if cum else pctile36(s, c)
        if pc is None:
            if not cum:
                blanked.append(lab)
            pcell = {'v': ''}
        else:
            pv = (100 - pc) if inv else pc
            pcell = {'v': f'{pc:.0f}', 'cls': 'hi' if pv >= 66 else ('lo' if pv <= 33 else '')}
        srows.append({'label': lab, 'cells': [
            {'v': f(c, dec, pct), 'cls': 'cur'},
            {'v': f(p1, dec, pct)},
            {'v': f(p12, dec, pct)},
            {'v': mtx, 'cls': mcls},
            {'v': ytx, 'cls': ycls},
            pcell,
        ]})

    summary = {
        'title': f'TSMC monthly revenue summary — {mlab(cur)}',
        'heads': heads,
        'sep': 3,
        'rows': srows,
        'note': ('All figures derived from the single officially disclosed field: consolidated '
                 'net revenue (NT$mn, unaudited)。'
                 '「3Y %ile」= 当月读数在最近 36 个月中高于多少百分比的观测，分位越高越极端；'
                 '比率行（占 TTM 比重）的 m/m、y/y 一律用百分点差（|差|&lt;1pp 时改用 bp），'
                 '不用「百分比的百分比变化」。'
                 + (f'周期内累计的行（{"、".join(cum_blanked)}）的 m/m 与 3Y %ile 已一并留空：'
                    'm/m 的分子分母在同一期内只差一个月（本期累计 = 上月累计 + 当月营收），'
                    '跨期时又变成 1 个月比 3／12 个月，两种情形都不可比，正负号只反映日历位置；'
                    '分位则由「本月是期内第几个月」决定 —— 季内第 1／2／3 个月分别锚在约 '
                    '30／80／100，与经营好坏无关。这两行的可比读数是 y/y'
                    '（QTD 为 3 个月 vs 3 个月、YTD 为 6 个月 vs 6 个月），已保留。'
                    if cum_blanked else '')
                 + (f'单调序列的行（{"、".join(blanked)}）分位恒接近 100，是噪音不是信息，已留空。'
                    if blanked else '')),
    }

    # ══════════════════ Exhibit 2..13 ══════════════════
    ex = []

    # ── Exhibit 2：GS 台股月营收核心图（Hon Hai / Wistron Exhibit 1 版式），win=20 ──
    W2 = 20
    ex.append({
        'n': 2, 'kind': 'bar_line_dual', 'height': 300,
        'title': 'TSMC monthly revenues',
        'xlabels': win_labels(W2), 'xrot': 90,
        'ylab': 'NT$bn', 'ylab2': '% y/y',
        'bar': {'name': 'Reported', 'color': 'NAVY',
                'values': L(rev_bn.iloc[-W2:].values), 'yfmt': 'f0'},
        'line': {'name': 'y/y (RHS)', 'color': 'GREEN',
                 'values': L(yoy_self.iloc[-W2:].values), 'yfmt': 'pct0'},
        'src_extra': ('Line = y/y growth (RHS)。PDF 版这条线是金色（GOLD #BF9000），'
                      '网页色板过了色盲安全校验、其中没有金色，改用绿色。'),
        'note': ('柱是公司公告的月度合并营收（NT$mn，此处换算成 NT$bn 显示）；'
                 '右轴 y/y 由本脚本按序列自算（当月 ÷ 去年同月 − 1），'
                 '与公司随公告给出的 yoy_pct 可能有 ±0.1pp 的舍入差，'
                 '热力矩阵（Exhibit 13）与核对表用的是公司原值。'),
    })

    # ── Exhibit 3：GS HKEX 式超长历史层 ──
    ex.append({
        'n': 3, 'kind': 'lines', 'full': True, 'height': 300, 'x': 'long',
        'title': 'Full monthly revenue history since 2016',
        'fmt': 'f0', 'ylab': 'NT$bn', 'xstep': 9, 'xrot': 90, 'zero_line': True,
        'series': [{'name': 'Monthly revenue (NT$bn)', 'color': 'NAVY', 'values': L(rev_bn.values)}],
        'src_extra': (f'Full disclosed history since {mlab(ALL[0])}（共 {len(ALL)} 个月）。'
                      'PDF 版在末端画了一个红色虚线椭圆圈出最近 3 个月，网页引擎无此图元，已省略。'),
        'note': '纵轴自 0 起（同 PDF），所以看得出的是量级台阶而不是月度噪音；月度波动请看 Exhibit 2。',
    })

    # ── Exhibit 4：环比变化率（与 Ex2 成对），win=25 ──
    W4 = 25
    mom_all = rev.pct_change(1) * 100
    ex.append({
        'n': 4, 'kind': 'gs_line', 'fmt': 'pct1',
        'title': 'Month-on-month revenue change',
        'xlabels': win_labels(W4), 'xrot': 90,
        'ylab': '% m/m', 'zero_line': True,
        'values': L(mom_all.iloc[-W4:].values),
        'note': ('环比不做季节调整。台湾半导体的月营收有很强的日历效应（2 月天数少、'
                 '农历年错位），单月 m/m 不能当趋势读，要和 Exhibit 11 的逐年 YTD 曲线一起看。'),
    })

    # ── Exhibit 5：月度 → 季度桥（当季未满月份浅色），win=14 ──
    W5 = 14
    qsum = (rev_bn.groupby(qkey).sum())
    qcnt = rev_bn.groupby(qkey).count()
    qv = qsum.values
    qyoy = np.array([(qv[i] / qv[i - 4] - 1) * 100 if i >= 4 and qv[i - 4] else np.nan
                     for i in range(len(qv))])
    n_in_last = int(qcnt.iloc[-1])
    qd = qsum.iloc[-W5:]
    ex.append({
        'n': 5, 'kind': 'qtr_bar',
        'title': 'Monthly revenue aggregated to quarters',
        'xlabels': [str(p) for p in qd.index], 'xrot': 90,
        'values': L(qd.values), 'fmt': 'f0c', 'label_fmt': 'f0c',
        'ylab': 'NT$bn', 'legend': 'Complete quarter',
        'partial_months': n_in_last, 'qtr_months': 3,
        'line': {'name': 'y/y (RHS)', 'color': 'GREEN',
                 'values': L(pd.Series(qyoy, index=qsum.index).iloc[-W5:].values), 'yfmt': 'pct0'},
        'note': ('季度值 = 该季已公布月份的 NT$ 营收直接相加，不做任何调整。'
                 + (f'本期 {qd.index[-1]} 已满 3 个月，是完整季度；'
                    if n_in_last >= 3 else
                    f'本期 {qd.index[-1]} 只公布了 3 个月中的 {n_in_last} 个月，末柱画成浅蓝，'
                    f'且右轴 y/y 的最后一点已被图表引擎强制作废（{n_in_last} 个月累计'
                    '对上年完整 3 个月不可比）；')
                 + '这张图是「用月营收抢跑季报」的核心图，但季报口径含其他收入项，与本表不完全相等。'
                 + '右轴 y/y 跨零，按引擎「两轴零点必须同高」的硬规矩，左轴被迫向下扩到负区，'
                   '柱因此压在画布上半张 —— 与 PDF（matplotlib 不对齐零点）观感不同，数值一致。'),
    })

    # ── Exhibit 6：季度指引区间 vs 实际 ──
    qlab = list(g.index)
    show_qtd = (0 < QTD_N < 3) and np.isfinite(QTD_USD)
    ex6 = {
        'n': 6, 'kind': 'range_band',
        'title': 'Quarterly revenue vs. company guidance',
        'xlabels': qlab, 'xrot': 90,
        'lo': L(g['guide_low_usdbn'].astype(float).values),
        'hi': L(g['guide_high_usdbn'].astype(float).values),
        'actual': L(g_act.values),
        'actual_color': 'NAVY',
        'names': {'range': 'Guidance range', 'actual': 'Actual',
                  'qtd': f'quarter-to-date ({QTD_N} of 3 months)',
                  'lo': 'Guidance low (US$bn)', 'hi': 'Guidance high (US$bn)'},
        'fmt': 'usd1', 'label_fmt': 'usd1', 'ylab': 'US$bn',
        'src_extra': (SRC_G + ' Bars are the revenue range TSMC guided at the prior quarter '
                              'earnings call; diamonds are the reported result.'
                      + (f' The hollow diamond is the current quarter with {QTD_N} of 3 months '
                         'reported, converted at monthly average FX.' if show_qtd else '')),
        'note': ('指引与实际都是公司自己给的美元数，和本页其余图的 NT$ 月营收不同源：'
                 '两者之间的差额同时含汇率与口径差（季度营收含非月营收项），不可直接相减。'
                 + (f'最后一格 {qlab[-1]} 只有指引、尚无实际值。' if not np.isfinite(g_act.values[-1]) else '')),
    }
    if show_qtd:
        ex6['qtd'] = num(QTD_USD)
        ex6['qtd_at'] = len(qlab) - 1
    ex.append(ex6)

    # ── Exhibit 7：实际 vs 指引中值，win=14 ──
    W7 = 14
    bd = beat_s.iloc[-W7:]
    mae = float(np.mean(np.abs(bd.values)))
    hit = int((bd.values > 0).sum())
    ex.append({
        'n': 7, 'kind': 'grouped_bars',
        'title': 'Actual vs. guidance midpoint',
        'xlabels': [mlab(p) for p in bd.index], 'xrot': 90,
        'groups': [{'name': 'Actual vs. guided midpoint', 'color': 'BLUE', 'values': L(bd.values)}],
        'bar_labels': True, 'fmt': 'pct1', 'label_fmt': 'pct1', 'ylab': '% vs midpoint',
        'src_extra': SRC_G,
        'note': ('Positive = came in above the midpoint of the guided range. A persistent positive '
                 'bias is the company guiding conservatively, not a series of surprises。'
                 f'窗口内 {len(bd)} 个季度里有 {hit} 个高于中值，平均绝对偏离 {mae:.1f}%。'
                 'x 轴标的是该季的最后一个月（Mar-23 = 2023Q1）。'
                 'PDF 版这张是 gsx.lvl_bar（浅蓝柱 + 右轴金色 y/y-pp 线）；网页的 gs_bar 纵轴强制自 0 起，'
                 '会把 2023Q1 的负值画到画布外，故改用单组 grouped_bars（含负值、带柱顶数值标签）。'),
    })

    # ── Exhibit 8：汇率贡献拆分 —— NT$ vs US$ 增速，win=25 ──
    W8 = 25
    ex.append({
        'n': 8, 'kind': 'lines_endlabels', 'fmt': 'pct0',
        'title': 'Revenue growth: NT$ vs. US$',
        'xlabels': win_labels(W8), 'xrot': 90, 'ylab': '% y/y',
        'series': [
            {'name': 'NT$ revenue y/y (as reported)', 'color': 'NAVY', 'values': L(yoy.iloc[-W8:].values)},
            {'name': 'US$ revenue y/y (converted)', 'color': 'MBLUE', 'values': L(yoy_usd.iloc[-W8:].values)},
        ],
        'src_extra': 'The gap between the two lines is the currency contribution. ' + ASSUMP,
        'note': ('US$ 线是**推导值（Implied）**：NT$ 月营收 ÷ 当月平均 NTD/USD，'
                 '不是公司披露的美元营收。假设：全部营收按当月平均汇率一次性折算，'
                 '忽略月内汇率路径、对冲与递延收款，因此这条线只能看方向与量级。'),
    })

    # ── Exhibit 9：汇率对报表增速的贡献，win=25 ──
    W9 = 25
    fcd = fx_contrib.iloc[-W9:]
    ex.append({
        'n': 9, 'kind': 'grouped_bars',
        'title': 'Currency contribution to reported growth',
        'xlabels': win_labels(W9), 'xrot': 90,
        'groups': [{'name': 'Currency contribution', 'color': 'BLUE', 'values': L(fcd.values)}],
        'bar_labels': True, 'fmt': 'pp1', 'label_fmt': 'pp1', 'ylab': 'pp of y/y',
        'src_extra': ('NT$ y/y less US$ y/y. Positive = a weaker NT dollar flattered the reported '
                      'number. ' + ASSUMP),
        'note': ('本图是 Exhibit 8 两条线之差，单位是百分点，不是百分比。'
                 'PDF 版同样是 gsx.lvl_bar；网页 gs_bar 纵轴自 0 起会截掉负值柱，'
                 '故与 Exhibit 7 一样改用单组 grouped_bars。'),
    })

    # ── Exhibit 10：NTD/USD 月均汇率（超长历史层）──
    ex.append({
        'n': 10, 'kind': 'lines', 'full': True, 'height': 300, 'x': 'long',
        'title': 'NTD per USD, monthly average',
        'fmt': 'f1', 'ylab': 'NTD per USD', 'xstep': 9, 'xrot': 90,
        'series': [{'name': 'NTD per USD (monthly avg.)', 'color': 'NAVY', 'values': L(fx_al.values)}],
        'src_extra': (SRC_FX + ' Roughly 70% of TSMC revenue is US-dollar denominated but reported '
                               'in NT$, so this rate moves the headline.'),
        'note': ('纵轴按数据范围自适应，未照 PDF 那样自 0 起 —— 28~34 的汇率压在 0 起点的轴上'
                 '会变成一条直线，看不出 2025 年那波急升。这是本页唯一一处刻意偏离 PDF 的轴设置。'),
    })

    # ── Exhibit 11：逐年 YTD 追赶曲线（n_years=6）──
    NY = 6
    yrs = sorted({p.year for p in ALL})[-NY:]
    yseries = []
    for y in yrs:
        vals = [None] * 12
        run = 0.0
        for p in ALL:
            if p.year != y:
                continue
            run += float(rev_bn.get(p))
            vals[p.month - 1] = round(run, 6)
        yseries.append({'name': str(y), 'values': vals})
    ex.append({
        'n': 11, 'kind': 'year_lines',
        'title': 'YTD revenue pace vs. prior years',
        'xlabels': MONTHS, 'series': yseries, 'highlight': len(yrs) - 1,
        'fmt': 'f0c', 'label_fmt': 'f0c', 'ylab': 'NT$bn cumulative',
        'src_extra': 'Cumulative from January of each year; red = current year.',
        'note': (f'每条线是该年 1 月起的累计营收（NT$bn），只取最近 {NY} 年。'
                 f'当年（{yrs[-1]}）只画到已公布的 {mlab(ALL[-1])}，其后为空，'
                 '所以年末的高度不可与往年整年直接比。'),
    })

    # ── Exhibit 12：滚动 12 个月营收（剔除季节性的趋势线）──
    ex.append({
        'n': 12, 'kind': 'lines', 'full': True, 'height': 300, 'x': 'long',
        'title': 'Trailing-12-month revenue',
        'fmt': 'f0', 'ylab': 'NT$bn (TTM)', 'xstep': 9, 'xrot': 90, 'zero_line': True,
        'series': [{'name': 'Trailing-12-month revenue (NT$bn)', 'color': 'NAVY',
                    'values': L(ttm_bn.values)}],
        'src_extra': '12-month rolling sum removes seasonality entirely.',
        'note': f'前 11 个月无 12 个月窗口，故序列自 {mlab(ALL[11])} 起。',
    })

    # ── Exhibit 13：同比热力矩阵（n_years=9）──
    NH = 9
    hyrs = sorted({p.year for p in yoy.dropna().index})[-NH:]
    matrix = []
    for y in hyrs:
        row = [None] * 12
        for p, v in yoy.dropna().items():
            if p.year == y:
                row[p.month - 1] = num(v, 4)
        matrix.append(row)
    ex.append({
        'n': 13, 'kind': 'heat_matrix', 'full': True,
        'title': 'Monthly revenue y/y growth (%)',
        'rows': [str(y) for y in hyrs], 'cols': MONTHS, 'matrix': matrix,
        'fmt': 'f0', 'legend': 'Revenue y/y (%)', 'row_head': '年', 'cell_h': 21,
        'src_extra': ('Green = faster y/y growth, red = slower; blanks are months not yet reported. '
                      '色标取全部有限值的 5/95 分位。'),
        'note': ('格内是公司随月营收公告的 y/y 原值（series/tsm.csv 的 yoy_pct），'
                 '不是本脚本算的。空格是尚未公布的月份。'),
    })

    # ══════════════════ 末尾核对表 ══════════════════
    T = 13
    trows = []
    for p in ALL[-T:]:
        trows.append({
            'xl': mlab(p),
            'rev': f(rev.get(p), 0),
            'yoy': f(yoy.get(p), 1),
            'fx': f(fx_al.get(p), 4),
            'usd': f(rev_usdmn.get(p), 0),
        })
    table = {
        'n': 14,
        'title': f'近 {T} 个月核对表（官方原始单位，未换算）',
        'idx': '月份',
        'cols': [['Consolidated revenue (NT$mn)', 'rev'],
                 ['y/y (%) — as disclosed', 'yoy'],
                 ['NTD/USD (monthly avg.)', 'fx'],
                 ['Implied revenue (US$mn)', 'usd']],
        'rows': trows,
    }

    # ══════════════════ 抬头 ══════════════════
    cur_rev_bn = float(rev_bn.iloc[-1])
    cur_yoy = float(yoy.iloc[-1])
    cur_mom = float(mom_all.iloc[-1])
    cur_q = qsum.index[-1]
    cur_q_bn = float(qsum.iloc[-1])
    cur_q_yoy = float(qyoy[-1])
    ytd_now = float(ytd_bn.iloc[-1])
    ytd_prev = float(ytd_bn.get(ALL[-1] - 12, np.nan))
    ytd_yoy = (ytd_now / ytd_prev - 1) * 100 if np.isfinite(ytd_prev) and ytd_prev else float('nan')
    cur_usd_yoy = float(yoy_usd.iloc[-1])
    cur_fx_pp = float(fx_contrib.iloc[-1])

    headline = (f'{mlab(cur)} 合并营收 NT${cur_rev_bn:,.1f}bn（{sgn(cur_yoy)} y/y、{sgn(cur_mom)} m/m）'
                f' · {cur_q} 累计 NT${cur_q_bn:,.0f}bn（{sgn(cur_q_yoy, 0)} y/y，'
                f'{n_in_last} of 3 months）'
                f' · YTD NT${ytd_now:,.0f}bn（{sgn(ytd_yoy, 0)} y/y）'
                f' · 美元口径 y/y {sgn(cur_usd_yoy, 0)}，汇率贡献 {sgn(cur_fx_pp, 1, "pp")}')
    hub_line = f'{mlab(cur)} 营收 NT${cur_rev_bn:,.0f}bn，{sgn(cur_yoy, 0)} y/y；YTD {sgn(ytd_yoy, 0)} y/y'

    notes = [
        ('<b>唯一数据源</b>：TSMC 官网 IR 月度营收公告（合并营收，NT$mn，未经会计师查核，'
         '台湾法定次月 10 日前公布）。本页 12 张图与两张表全部由这一个字段加一条月均汇率序列派生，'
         '不引入任何券商预测或外部估计。'),
        ('<b>版式出处</b>：Goldman Sachs GIR「Hon Hai (2317.TW)」与「Wistron (3231.TW)」两份台股'
         '月营收报告的 Exhibit 1-2，外加 GS HKEX 深度的超长历史层与 JPM AXP 的季节性剥离图型。'),
        ('<b>y/y 有两个来源，不要混用</b>：Exhibit 13 热力矩阵与核对表用公司随公告给出的 '
         '<code>yoy_pct</code> 原值；Exhibit 2 的右轴线与 Exhibit 5 的季度 y/y 由本脚本按序列自算。'
         '两者可能差 ±0.1pp，来自公司口径的四舍五入，未做人工对齐。'),
        ('<b>美元口径全部是推导值（Implied）</b>：US$ 营收 = NT$ 营收 ÷ 当月平均 NTD/USD。'
         '假设全部营收按当月平均汇率一次性折算，忽略月内汇率路径、对冲与递延收款。'
         '汇率贡献（Exhibit 9）= NT$ y/y − US$ y/y，单位是百分点。'),
        ('<b>汇率序列口径</b>：月均 NTD/USD，等价于 FRED 的 EXTAUS（该月全部营业日美联储 H.10 '
         '台湾牌价的算术平均）。TSMC 约七成营收以美元计价却以新台币入账，所以这条线直接推动报表增速。'),
        ('<b>指引 vs 实际（Exhibit 6-7）与月营收不同源</b>：这两张图的美元数来自季度业绩说明会的'
         '指引区间与实际披露，季度营收口径含非月营收项；与月营收累加值之间的差额同时含汇率与口径差，'
         '不可直接相减。'),
        ('<b>未满季提示</b>：Exhibit 5 的末季不足 3 个月时会画成浅蓝柱，且右轴 y/y 会被图表引擎强制'
         '作废 —— 拿 2 个月累计去比上年完整 3 个月必然砸出一个假坑。'
         f'本期 {cur_q} 已含 {n_in_last} 个月，'
         + ('为完整季度，无此标记。' if n_in_last >= 3 else '故末柱与末点按上述规则处理。')),
        ('⚠️ <b>无口径断点、无截轴</b>：TSMC 月营收自 2016-01 起口径连续，未发生并表或重述，'
         '所以本页没有任何 <code>break_at</code> 红色虚线，也没有 <code>ycap</code>/<code>yfloor</code>。'
         '这是核对过的结论，不是漏设。'),
        ('<b>网页版与 PDF 版的三处已知差异</b>：(1) PDF 里 y/y 线是金色 GOLD #BF9000，网页色板过了'
         '色盲安全校验、其中没有金色，改用绿色；(2) PDF 长历史图末端有一个红色虚线椭圆圈出最近 3 个月，'
         '网页引擎无此图元，已省略；(3) Exhibit 7 与 Exhibit 9 在 PDF 里是 <code>gsx.lvl_bar</code>，'
         '网页对应的 <code>gs_bar</code> 纵轴强制自 0 起会把负值柱画到画布外，故改用单组 '
         '<code>grouped_bars</code>（保留负值与柱顶数值标签）。'),
        ('<b>汇总表的分位与累计行</b>：「3Y %ile」= 当月读数在最近 36 个月中高于多少百分比的观测。'
         '周期内累计的序列（QTD／YTD）的 <b>m/m 与分位两列一律留空</b>：分位由「本月是期内'
         '第几个月」决定（季内第 1／2／3 个月锚在约 30／80／100），m/m 则只是「上月累计 + 当月营收」'
         '的算术恒等式、跨季跨年时又变成 1 个月比 3／12 个月 —— 两者都与经营好坏无关，'
         '按数据契约「不可比的相邻期不算变化率、单调/锯齿序列不算分位」留空。'
         '这两行看 y/y（3 个月 vs 3 个月、6 个月 vs 6 个月，口径可比）。'
         '比率行的 m/m、y/y 一律用百分点（|差|&lt;1pp 时改用 bp）。'),
    ]

    payload = {
        'ticker': 'tsm',
        'tracker': 'TSMC Monthly Revenue Tracker',
        'title': f'台积电 TSMC (2330.TW / TSM)：月度营收跟踪 — {cur.year} 年 {cur.month} 月',
        'data_through': str(cur),
        'through_label': f'{cur.year} 年 {cur.month} 月',
        'subtitle': (f'数据源：TSMC 官网 IR 月度营收公告（次月 10 日前）· '
                     f'覆盖 {mlab(ALL[0])} – {mlab(ALL[-1])} 共 {len(ALL)} 个月 · '
                     f'版式仿 Goldman Sachs GIR 台股月营收报告（charts only, no commentary）'),
        'headline': headline,
        'hub_line': hub_line,
        'source': SRC,
        'xlabels': XL13,
        'xlabels_long': XL_LONG,
        'summary': summary,
        'exhibits': ex,
        'table': table,
        'notes': notes,
        'footer': ('图表与派生算法源自本机 <code>monthly-op-dashboards</code> 项目，'
                   '与 <code>build/build_tsm.py</code>（PDF 版）同源 · '
                   '仅供个人研究，不构成投资建议'),
    }

    # 上线前的自检：payload 里不许有 NaN / Infinity（json.dump 会写成裸字面量，
    # 浏览器 JSON 解析不了；而 window.DASH = 是 JS 求值，NaN 会被静默吞进图里）。
    # 原来这里是本地一段大小写敏感的 `'NaN' in txt` 子串检查，已并入
    # build/payload_guard.py 统一实现 —— 那版漏掉了已被 f-string 格式化进展示串的
    # 小写 nan（`f'{nan:+.1f}%'` → `'nan%'`），共用版按词边界一并抓。
    path = os.path.join(DATA, 'tsm.js')
    payload_guard.write_dash(path, payload, 'tsm')

    print(f'窗口 {ALL[0]} → {ALL[-1]}（{len(ALL)} 个月）· 季度 {qsum.index[0]} → {qsum.index[-1]}')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张）+ Exhibit {table["n"]} 核对表')
    print(headline)
    print(f'写出 data/tsm.js ({os.path.getsize(path) / 1024:.1f} KB)')


if __name__ == '__main__':
    main()
