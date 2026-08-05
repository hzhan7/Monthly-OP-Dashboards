# -*- coding: utf-8 -*-
"""MSCI Inc. —— 挂钩 MSCI 指数的 ETF 月度 AUM：网页看板的数据生成器。

把 build/build_msci.py（matplotlib → PDF）里的每一张 exhibit 逐张移植成
window.DASH 的一个 exhibit 对象，写出 data/msci.js。图序、编号、标题、图注、
口径断点全部照搬原 deck；标题里的当期数字随最新月重算，不写死。

数据源（只读 series/，不读 build/data/）：
    series/msci.csv       month, aum_eop_usdbn, aum_avg_usdbn（2008-12 起）
    series/fee_rates.csv  MSCI 的 asset_based_fee_effective_rate_annualized（bp，季度）
                          与 asset_based_fee_revenue / disclosed_period_end_basis_point_fee_etf

口径提示（与原 deck 的模块 docstring 同源）：
    这是第三方 ETF 的资产规模（客户端产品），不是 MSCI 自身营收；但它由 MSCI 官方
    按月披露，且直接决定 asset-based fee 收入 —— 该收入近似 = 季度平均 AUM x 基点费率，
    故 Exhibit 5 用季度平均而非期末值。

幂等：payload 里不放构建日期（只写文件首行注释），窗口一律从数据最新月倒推，
      不用随机数、不依赖当前时间决定内容 —— 重复跑除首行外逐字节相同。
"""
import csv
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')

SRC = ('Source: MSCI IR, AUM in ETFs linked to MSCI equity indexes; '
       'format after Goldman Sachs GIR')

MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# ────────────────────────────── 月份/季度小工具 ──────────────────────────────
def mi(ym):
    """'YYYY-MM' → 绝对月序号，方便做加减与差分。"""
    y, m = ym.split('-')
    return int(y) * 12 + int(m) - 1


def ym(i):
    return f'{i // 12:04d}-{i % 12 + 1:02d}'


def mlab(s):
    """'2026-06' → 'Jun-26'（同 gsx.mlab 的 %b-%y）。"""
    y, m = s.split('-')
    return f'{MON[int(m) - 1]}-{y[2:]}'


def qof(s):
    """'2026-06' → '2026Q2'（同 pandas Period 的 str）。"""
    y, m = s.split('-')
    return f'{y}Q{(int(m) - 1) // 3 + 1}'


def qi(q):
    """'2026Q2' → 绝对季序号。"""
    y, k = q.split('Q')
    return int(y) * 4 + int(k) - 1


def qlab_month(q):
    """'2023Q3' → 该季末月份 '2023-09'（原 deck 把季度费率挂在季末月上）。"""
    y, k = q.split('Q')
    return f'{int(y):04d}-{int(k) * 3:02d}'


# ────────────────────────────── 格式化（一律 Python 侧） ──────────────────────────────
def f(v, d=1):
    return f'{v:,.{d}f}'


def sgn_pct(v, d=1):
    """带正负号的百分比；同 gsx 的 f'{v:+.1f}%'。"""
    return f'{v:+.{d}f}%'


def pp_txt(v):
    """gsx._pp：绝对值 < 2 用一位小数，否则整数。"""
    return f'{v:+.1f}%' if abs(v) < 2 else f'{v:+.0f}%'


def R(x, nd=6):
    return None if x is None else round(float(x), nd)


def RL(a, nd=6):
    return [R(v, nd) for v in a]


# ────────────────────────────── 读数据 ──────────────────────────────
def read_msci():
    path = os.path.join(SERIES, 'msci.csv')
    months, eop, avg = [], {}, {}
    with open(path, encoding='utf-8') as fh:
        for row in csv.DictReader(fh):
            k = row['month'].strip()
            if not k:
                continue
            months.append(k)
            eop[k] = float(row['aum_eop_usdbn'])
            avg[k] = float(row['aum_avg_usdbn'])
    months.sort()
    # 逐月连续是后面所有 y/y、m/m、季度汇总的前提；不连续就直接失败，不静默补洞
    for a, b in zip(months, months[1:]):
        if mi(b) - mi(a) != 1:
            raise SystemExit(f'series/msci.csv 月份不连续：{a} → {b}')
    return months, eop, avg


def read_rates():
    """MSCI 的季度费率与季度实际 asset-based fee 收入（供图注引用）。"""
    path = os.path.join(SERIES, 'fee_rates.csv')
    bp, rev, disc = {}, {}, {}
    with open(path, encoding='utf-8') as fh:
        for row in csv.DictReader(fh):
            if row['company'] != 'MSCI':
                continue
            q = row['period'].replace('-', '')
            m, v, u = row['metric'], float(row['value']), row['unit']
            if m == 'asset_based_fee_effective_rate_annualized':
                if u != 'bp_of_etf_aum':
                    raise SystemExit(f'MSCI 费率单位意外：{u}')
                bp[q] = v
            elif m == 'asset_based_fee_revenue':
                if u != 'USD_mn':
                    raise SystemExit(f'MSCI ABF 收入单位意外：{u}')
                rev[q] = v
            elif m == 'disclosed_period_end_basis_point_fee_etf':
                disc[q] = v
    if not bp:
        raise SystemExit('series/fee_rates.csv 里没有 MSCI 的有效费率')
    return bp, rev, disc


def main():
    months, EOP, AVG = read_msci()
    BP_Q, REV_Q, DISC_Q = read_rates()
    LATEST = months[-1]
    li = mi(LATEST)

    # ── 派生序列 ──
    diff = {k: EOP[k] - AVG[k] for k in months}          # 期末 − 月均：月内走势方向
    mom = {}                                             # 月末 AUM 的 m/m（%）
    for k in months[1:]:
        p = ym(mi(k) - 1)
        mom[k] = (EOP[k] / EOP[p] - 1) * 100

    # ── 量→收入桥：asset-based fee = 平均 AUM x 有效基点费率 / 12 ──
    # 季度费率 → 月度：当季各月用该季费率；最新已知季之后沿用最后一个值（这是假设，写进图注）。
    qs = sorted(BP_Q, key=qi)
    last_q, last_bp = qs[-1], BP_Q[qs[-1]]
    rate_m = {}
    for k in months:
        q = qof(k)
        if q in BP_Q:
            rate_m[k] = BP_Q[q]
        elif qi(q) > qi(last_q):
            rate_m[k] = last_bp                          # ffill：最新季之后沿用
    abf = {k: AVG[k] * 1000.0 * rate_m[k] / 10000.0 / 12.0 for k in rate_m}
    abf_months = sorted(abf)
    # 有几个月落在最新已知季度之后（那几个月的费率是沿用值 = 真估计），本次是几就写几
    n_ffill = sum(1 for k in abf_months if qof(k) not in BP_Q)
    BR_NOTE = ('Assumption: monthly asset-based fee = month average AUM x the effective rate / 12 '
               f'({last_q} = {last_bp:.3f}bp, held flat after). The rate is back-solved from '
               'reported revenue, so closed quarters are an allocation, not an estimate.')

    # ── 窗口（全部从最新月倒推）──
    W25 = [ym(li - k) for k in range(24, -1, -1)]        # 月度图 25 个月，同 win=25
    XL25 = [mlab(k) for k in W25]
    W13 = [ym(li - k) for k in range(12, -1, -1)]        # 核对表 13 个月
    XL13 = [mlab(k) for k in W13]
    XL_LONG = [mlab(k) for k in months]

    def yoy(d, k):
        p = ym(mi(k) - 12)
        return (d[k] / d[p] - 1) * 100 if p in d else None

    # ══════════════════════════ Exhibit 1：汇总表 ══════════════════════════
    cur, prv, yag = LATEST, ym(li - 1), ym(li - 12)

    def pctile36(d, keys, k):
        """近 36 个月分位；单调序列（diff>=0 占比 ≥ 90%）留空 —— 分位恒为 100 是噪音。"""
        i = keys.index(k)
        hist = [d[x] for x in keys[max(0, i - 35):i + 1]]
        if len(hist) < 8:
            return None
        dd = [b - a for a, b in zip(hist, hist[1:])]
        if dd and sum(1 for x in dd if x >= 0) / len(dd) >= 0.90:
            return None
        return sum(1 for x in hist if x < d[k]) / max(1, len(hist) - 1) * 100

    def sum_row(label, d, keys, dec=1, money='$', mode='ratio'):
        c, p1, p12 = d[cur], d[prv], d[yag]
        cells = [{'v': money + f(c, dec)}, {'v': money + f(p1, dec)}, {'v': money + f(p12, dec)}]
        for a, b in ((c, p1), (c, p12)):
            if mode == 'abs':
                v = a - b
                # 负号写在货币符号外面（$-59.5 读起来像负的货币单位）
                cells.append({'v': ('+' if v >= 0 else '-') + money + f'{abs(v):,.{dec}f}',
                              'cls': 'pos' if v > 0 else 'neg'})
            elif b == 0 or a * b < 0:                     # 分母为 0 / 两期异号 → 比率无意义
                cells.append({'v': ''})
            else:
                v = (a / b - 1) * 100
                cells.append({'v': sgn_pct(v), 'cls': 'pos' if v > 0 else 'neg'})
        pc = pctile36(d, keys, cur)
        if pc is None:
            cells.append({'v': ''})
        else:
            cells.append({'v': f'{pc:.0f}',
                          'cls': 'hi' if pc >= 66 else ('lo' if pc <= 33 else '')})
        return {'label': label, 'cells': cells}

    summary = {
        'title': f'MSCI-linked ETF AUM summary — {mlab(LATEST)}',
        'heads': [mlab(cur), mlab(prv), mlab(yag), 'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': [
            {'kind': 'group', 'label': 'ETF AUM linked to MSCI indexes'},
            sum_row('Month-end AUM ($bn)', EOP, months),
            sum_row('Average AUM for the month ($bn)', AVG, months),
            # 期末−月均会在零附近变号，百分比变化没有意义 —— 这一行的差异用绝对额（$bn）
            sum_row('Month-end less monthly average ($bn)', diff, months, mode='abs'),
        ],
        'note': ('Average AUM is the fee-relevant measure: asset-based fees accrue on average assets, '
                 'not the month-end snapshot. All figures are MSCI estimates and include linked ETNs '
                 '(&lt;1% of AUM). 3Y %ile = 当月读数在最近 36 个月里高于多少百分比的观测；'
                 '「期末 − 月均」一行会在零附近变号，故 m/m 与 y/y 用绝对额（$bn）而非百分比变化。'),
    }

    ex = []

    # ══════════════════════════ Exhibit 2：月末 AUM 水平柱 ══════════════════════════
    v2 = [EOP[k] for k in W25]
    avg12_2 = sum(EOP[ym(li - k)] for k in range(12, 0, -1)) / 12.0   # Prior 12mo Avg.
    yoy2, mom2 = yoy(EOP, LATEST), (EOP[LATEST] / EOP[ym(li - 1)] - 1) * 100
    ex.append({
        'n': 2, 'kind': 'gs_bar', 'fmt': 'f0c', 'label_fmt': 'f0c', 'xlabels': XL25,
        'title': (f'Month-end AUM in MSCI-linked ETFs — ${f(EOP[LATEST], 0)}bn in {mlab(LATEST)}, '
                  f'{pp_txt(yoy2)} YoY and {pp_txt(mom2)} MoM'),
        'ylab': '$bn', 'legend': 'Month-end AUM',
        'values': RL(v2), 'avg12': R(avg12_2),
        'yoy_txt': f'{yoy2:+.0f}% y/y', 'mom_txt': f'{pp_txt(mom2)} m/m',
        'note': ('第三方 ETF 的资产规模（客户端产品），不是 MSCI 自身营收；由 MSCI 官方按月披露。'
                 '虚线为 Prior 12mo Avg.（最新月之前 12 个月的均值）。'
                 '数值为 MSCI 估算，含挂钩 ETN（&lt;1% of AUM）。'),
    })

    # ══════════════════════════ Exhibit 3：月末 AUM m/m ══════════════════════════
    ex.append({
        'n': 3, 'kind': 'gs_line', 'fmt': 'pct1', 'xlabels': XL25,
        'title': (f'Month-end AUM, m/m change — {mlab(LATEST)} {sgn_pct(mom[LATEST])}, '
                  f'近 25 个月里 {sum(1 for k in W25 if mom[k] > 0)} 个月为正'),
        'ylab': '% m/m', 'values': RL([mom[k] for k in W25]),
        'note': '与 Exhibit 2 成对：柱看水平、线看动能。月末快照的环比含市场涨跌与净流入两部分，本序列不拆分。',
    })

    # ══════════════════════════ Exhibit 4：全历史（月末） ══════════════════════════
    BRK = '2019-04'
    if BRK not in EOP:
        raise SystemExit(f'口径断点 {BRK} 不在序列里，无法画 break_at')
    brk_i = months.index(BRK)
    ex.append({
        'n': 4, 'kind': 'lines', 'x': 'long', 'full': True, 'height': 300,
        'fmt': 'f0c', 'xstep': max(1, len(months) // 14), 'xrot': 90,
        'title': (f'Full AUM history since {mlab(months[0])} — from ${f(EOP[months[0]], 0)}bn to '
                  f'${f(EOP[LATEST], 0)}bn ({EOP[LATEST] / EOP[months[0]]:.1f}x over '
                  f'{(li - mi(months[0])) / 12:.0f} years)'),
        'ylab': '$bn',
        'series': [{'name': 'Month-end AUM', 'color': 'NAVY', 'values': RL([EOP[k] for k in months])}],
        'break_at': brk_i, 'break_label': 'data provider switch',
        'src_extra': ('Before Apr-2019 the figures are MSCI estimates built on Bloomberg data; '
                      'from May-2019 on Refinitiv data'),
        'note': ('⚠️ 红色虚线（2019-04）是数据供应商切换的口径断点：左侧为基于 Bloomberg 数据的估算，'
                 '右侧起改用 Refinitiv 数据，两侧不可直读为同一条连续序列。'),
    })

    # ══════════════════════════ Exhibit 5：季度平均 AUM ══════════════════════════
    qmap = {}
    for k in months:
        qmap.setdefault(qof(k), []).append(AVG[k])
    qkeys = sorted(qmap, key=qi)
    qavg = {q: sum(qmap[q]) / len(qmap[q]) for q in qkeys}
    QW = qkeys[-14:]
    q_yoy = []
    for q in QW:
        p = qkeys[qkeys.index(q) - 4] if qkeys.index(q) >= 4 else None
        q_yoy.append((qavg[q] / qavg[p] - 1) * 100 if p and qavg[p] else None)
    n_last_q = len(qmap[QW[-1]])
    ex.append({
        'n': 5, 'kind': 'qtr_bar', 'fmt': 'f0c', 'label_fmt': 'f0c', 'xlabels': QW,
        'title': (f'Quarterly average AUM (fee-relevant basis) — {QW[-1]} ${f(qavg[QW[-1]], 0)}bn, '
                  f'{q_yoy[-1]:+.0f}% YoY'),
        'ylab': '$bn', 'legend': 'Quarterly average AUM',
        'values': RL([qavg[q] for q in QW]),
        'partial_months': n_last_q, 'qtr_months': 3,
        'line': {'name': 'y/y (RHS)', 'color': 'GREEN', 'values': RL(q_yoy), 'yfmt': 'pct0'},
        'src_extra': ('Quarterly mean of the monthly average-AUM series; '
                      'drives asset-based fee revenue'),
        'note': ('asset-based fee 按平均资产计提，故这里用季度平均而非期末值。'
                 f'末季 {QW[-1]} 已含 {n_last_q} 个月'
                 + ('（已满季，可与往季直读）。' if n_last_q >= 3 else
                    '（未满季，柱为浅蓝，右轴 y/y 已作废，不可与完整季直读）。')),
    })

    # ══════════════════════════ Exhibit 6：月末 vs 月均 ══════════════════════════
    ex.append({
        'n': 6, 'kind': 'lines_endlabels', 'fmt': 'f0c', 'xlabels': XL25,
        'title': (f'Month-end vs. average AUM — {mlab(LATEST)} 月末 ${f(EOP[LATEST], 0)}bn '
                  f'高于月均 ${f(AVG[LATEST], 0)}bn ${f(diff[LATEST], 1)}bn'
                  if diff[LATEST] >= 0 else
                  f'Month-end vs. average AUM — {mlab(LATEST)} 月末 ${f(EOP[LATEST], 0)}bn '
                  f'低于月均 ${f(AVG[LATEST], 0)}bn ${f(-diff[LATEST], 1)}bn'),
        'ylab': '$bn',
        'series': [
            {'name': 'Month-end AUM', 'color': 'NAVY', 'values': RL([EOP[k] for k in W25])},
            {'name': 'Average AUM for month', 'color': 'MBLUE', 'values': RL([AVG[k] for k in W25])},
        ],
        'note': ('两条线的差（期末 − 月均）是月内走势的方向指示：正 = 月末高于月均（月内上行）。'
                 'asset-based fee 计提在月均那条线上，不是月末那条。'),
    })

    # ══════════════════════════ Exhibit 7：隐含 asset-based fee（月） ══════════════════════════
    W25a = abf_months[-25:]
    XL25a = [mlab(k) for k in W25a]
    ai = abf_months.index(LATEST)
    avg12_7 = sum(abf[k] for k in abf_months[ai - 12:ai]) / 12.0
    yoy7 = (abf[LATEST] / abf[ym(li - 12)] - 1) * 100
    ex.append({
        'n': 7, 'kind': 'gs_bar', 'fmt': 'f1', 'label_fmt': 'f1', 'xlabels': XL25a,
        'title': (f'Implied asset-based fee revenue — {mlab(LATEST)} ${abf[LATEST]:.1f}mn, '
                  f'{yoy7:+.0f}% YoY'),
        'ylab': '$mn / month', 'legend': 'Implied asset-based fee',
        'values': RL([abf[k] for k in W25a]), 'avg12': R(avg12_7),
        'yoy_txt': f'{yoy7:+.0f}% y/y',
        'src_extra': BR_NOTE,
        'note': ('<b>Implied</b>：不是公司披露的月度值。' + BR_NOTE +
                 f' 序列自 {mlab(abf_months[0])} 起，因为费率最早只回溯到 {qs[0]}。'),
    })

    # ══════════════════════════ Exhibit 8：有效费率（季度） ══════════════════════════
    bpq = [BP_Q[q] for q in qs]
    XLbp = [mlab(qlab_month(q)) for q in qs]
    avg12_8 = sum(bpq[-5:-1]) / 4.0                       # 前 4 个季度 = Prior 12mo Avg.
    yoy8 = bpq[-1] - bpq[-5]                              # 比率序列的同比是百分点差
    ex.append({
        # 原 deck 用 dec=2；网页侧只能用 f1 —— assets/charts.js 的 FMT 里没有 'f2'，
        # 传 'f2' 会静默退回 f1（fmtOf 的默认分支）。宁可显式写 f1，也不要让格式静默降级。
        # 三位小数的精确值写进图注与核对表。
        'n': 8, 'kind': 'gs_bar', 'fmt': 'f1', 'label_fmt': 'f1', 'xlabels': XLbp,
        'title': (f'Effective asset-based fee rate — {last_q} {last_bp:.3f}bp, '
                  f'{yoy8:+.2f}pp YoY（{bpq[0]:.2f}bp → {bpq[-1]:.2f}bp over {len(qs)} quarters）'),
        'ylab': 'bp of average ETF AUM', 'legend': 'Effective rate (quarterly)',
        'values': RL(bpq), 'avg12': R(avg12_8),
        'yoy_txt': f'{yoy8:+.2f}pp y/y',
        'note': ('Reported asset-based fee revenue / average MSCI-linked ETF AUM. '
                 'This is the bridge\'s real uncertainty: AUM compounded but the rate compressed from '
                 f'{bpq[0]:.1f}bp to {bpq[-1]:.1f}bp in {len(qs) - 1} quarters. '
                 f'The period-end ETF fee of {DISC_Q[last_q]:.2f}bp is lower as it also covers '
                 'non-ETF licensing. 比率序列的同比用<b>百分点差</b>，不是「百分比的百分比变化」；'
                 'x 轴标的是各季末月份。柱顶标签四舍五入到 0.1bp，逐季精确值（bp）：'
                 + '、'.join(f'{q} {BP_Q[q]:.3f}' for q in qs) + '。'),
    })

    # ══════════════════════════ Exhibit 9：逐年 AUM 路径 ══════════════════════════
    years = sorted({k[:4] for k in months})[-6:]
    yseries = []
    for y in years:
        vals = [EOP.get(f'{y}-{m:02d}') for m in range(1, 13)]
        yseries.append({'name': y, 'values': RL(vals)})
    cy = years[-1]
    cy_last = max(int(k[5:]) for k in months if k[:4] == cy)
    ex.append({
        'n': 9, 'kind': 'year_lines', 'fmt': 'f0c', 'label_fmt': 'f0c',
        'xlabels': MON, 'series': yseries, 'highlight': len(years) - 1,
        'title': (f'AUM path by year — {cy} 年 {cy_last} 月末 ${f(EOP[LATEST], 0)}bn，'
                  f'较 {years[-2]} 年同月 {pp_txt(yoy(EOP, LATEST))}'),
        'ylab': '$bn',
        'note': ('画的是月末水平值本身（不是年初至今累计），红线 = 当年。'
                 f'{cy} 年只到 {MON[cy_last - 1]}（{cy_last} 月），其后为空。'
                 '2019-04 的数据供应商切换落在图外的早期年份，这 6 年内不含断点。'),
    })

    # ══════════════════════════ Exhibit 10：隐含 ABF（季度） ══════════════════════════
    aq = {}
    for k in abf_months:
        aq.setdefault(qof(k), []).append(abf[k])
    aqk = sorted(aq, key=qi)
    aqsum = {q: sum(aq[q]) for q in aqk}
    AQW = aqk[-14:]
    aq_yoy = []
    for q in AQW:
        j = aqk.index(q)
        p = aqk[j - 4] if j >= 4 else None
        aq_yoy.append((aqsum[q] / aqsum[p] - 1) * 100 if p and aqsum[p] else None)
    n_last_aq = len(aq[AQW[-1]])
    ex.append({
        'n': 10, 'kind': 'qtr_bar', 'fmt': 'f0c', 'label_fmt': 'f0c', 'xlabels': AQW,
        'title': (f'Implied asset-based fee by quarter — {AQW[-1]} ${f(aqsum[AQW[-1]], 0)}mn'
                  + (f'，实际披露 ${REV_Q[AQW[-1]]:.0f}mn'
                     if AQW[-1] in REV_Q else '，该季尚未披露实际值')),
        'ylab': '$mn / quarter', 'legend': 'Implied asset-based fee',
        'values': RL([aqsum[q] for q in AQW]),
        'partial_months': n_last_aq, 'qtr_months': 3,
        'line': {'name': 'y/y (RHS)', 'color': 'GREEN', 'values': RL(aq_yoy), 'yfmt': 'pct0'},
        'src_extra': ('Quarterly sum of the monthly bridge; the latest bar is quarter-to-date '
                      'if the quarter is incomplete'),
        'note': ('<b>Implied</b>：月度桥的季度合计。已收官季度可与公司披露的 asset-based fee 收入对表 —— '
                 + '；'.join(f'{q} 隐含 ${aqsum[q]:.0f}mn vs 实际 ${REV_Q[q]:.0f}mn'
                             f'（差 {(aqsum[q] / REV_Q[q] - 1) * 100:+.1f}%）'
                             for q in AQW[-4:] if q in REV_Q)
                 + '。差异来自月均 AUM 与公司季均口径的细微出入，不是费率错。'),
    })

    # ══════════════════════════ Exhibit 11：全历史（月均） ══════════════════════════
    ex.append({
        'n': 11, 'kind': 'lines', 'x': 'long', 'full': True, 'height': 300,
        'fmt': 'f0c', 'xstep': max(1, len(months) // 14), 'xrot': 90,
        'title': (f'Average AUM since {mlab(months[0])} — ${f(AVG[LATEST], 0)}bn in {mlab(LATEST)}, '
                  f'{AVG[LATEST] / AVG[months[0]]:.1f}x the {months[0][:4]} starting level'),
        'ylab': '$bn',
        'series': [{'name': 'Average AUM for month', 'color': 'NAVY',
                    'values': RL([AVG[k] for k in months])}],
        'break_at': brk_i, 'break_label': 'data provider switch',
        'note': '⚠️ 与 Exhibit 4 同一个断点：2019-04 起数据供应商由 Bloomberg 换成 Refinitiv。',
    })

    # ══════════════════════════ Exhibit 12：隐含费收 y/y ══════════════════════════
    # 原 deck 用 win=25，但 y/y 在窗口第一格（比 12 个月前）无值，matplotlib 那边就是空点；
    # 网页的 gs_line 走平滑曲线，吃不了 null，所以直接取 24 个有值的点 —— 画面内容一致。
    yw = [k for k in abf_months if ym(mi(k) - 12) in abf][-24:]
    yv = [(abf[k] / abf[ym(mi(k) - 12)] - 1) * 100 for k in yw]
    aum_yoy = yoy(AVG, LATEST)
    ex.append({
        'n': 12, 'kind': 'gs_line', 'fmt': 'pct1', 'xlabels': [mlab(k) for k in yw],
        'title': (f'Implied fee revenue, y/y — {mlab(LATEST)} {sgn_pct(yv[-1])}，'
                  f'慢于平均 AUM 的 {sgn_pct(aum_yoy)}'),
        'ylab': '% y/y', 'values': RL(yv),
        'src_extra': 'Grows more slowly than AUM because the effective rate has been compressing',
        'note': ('增速慢于 AUM，差额就是有效费率的压缩（见 Exhibit 8）。'
                 f'{mlab(LATEST)}：隐含费收 {sgn_pct(yv[-1])} vs 平均 AUM {sgn_pct(aum_yoy)}，'
                 f'缺口 {yv[-1] - aum_yoy:+.1f}pp。'),
    })

    # ══════════════════════════ Exhibit 13：m/m 热力矩阵 ══════════════════════════
    hyears = sorted({k[:4] for k in mom})[-11:]
    matrix = [[R(mom.get(f'{y}-{m:02d}')) for m in range(1, 13)] for y in hyears]
    ex.append({
        'n': 13, 'kind': 'heat_matrix', 'full': True,
        'title': (f'Month-end AUM m/m change (%) — {mlab(LATEST)} {sgn_pct(mom[LATEST])}；'
                  f'{hyears[0]}–{hyears[-1]} 共 '
                  f'{sum(1 for r in matrix for v in r if v is not None and v > 0)} 个月为正、'
                  f'{sum(1 for r in matrix for v in r if v is not None and v < 0)} 个月为负'),
        'rows': hyears, 'cols': MON, 'matrix': matrix,
        'fmt': 'pct1', 'reverse': False, 'legend': 'Month-end AUM m/m (%)',
        'row_head': '年', 'cell_h': 19,
        'src_extra': 'Green = AUM rose, red = AUM fell',
        'note': ('色标取全部有限值的 5–95 分位，一两个离群月不会把整表压平。'
                 '2019-04 的供应商切换落在矩阵内部，但热力矩阵没有连续 x 轴，画不了断点线 —— '
                 '读 2019 那一行时请记得左右两侧口径不同。'),
    })

    # ══════════════════════════ 核对表 ══════════════════════════
    trows = []
    for k in W13:
        trows.append({
            'xl': mlab(k),
            'eop': f(EOP[k], 1),
            'avg': f(AVG[k], 1),
            'diff': f'{diff[k]:+,.1f}',
            'mom': sgn_pct(mom[k]) if k in mom else None,
            'rate': f'{rate_m[k]:.3f}' if k in rate_m else None,
            'abf': f(abf[k], 1) if k in abf else None,
        })
    table = {
        'n': 14, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）', 'idx': '月份',
        'cols': [['月末 AUM（$bn）', 'eop'], ['当月平均 AUM（$bn）', 'avg'],
                 ['月末 − 月均（$bn）', 'diff'], ['月末 AUM m/m（%）', 'mom'],
                 ['有效费率（bp，季度值）', 'rate'], ['隐含 ABF（$mn，推导）', 'abf']],
        'rows': trows,
    }

    # ══════════════════════════ 口径与方法说明 ══════════════════════════
    notes = [
        '<b>这不是 MSCI 的营收。</b>本页画的是<b>第三方</b>挂钩 MSCI 指数的 ETF 资产规模（客户端产品）；'
        '它由 MSCI 官方按月披露，且直接决定 asset-based fee 收入，故可用作月度抢跑季报的高频量。',
        'Average AUM 才是费率相关口径：asset-based fee 按<b>平均</b>资产计提，不是月末快照。'
        'Exhibit 5 因此用季度平均而非期末值。',
        '所有数字均为 MSCI 估算值，且包含挂钩 ETN（占 AUM &lt;1%）；MSCI 每月中旬发布上一月数据。',
        f'⚠️ <b>口径断点 2019-04（数据供应商切换）</b>：该月之前是 MSCI 基于 Bloomberg 数据的估算，'
        f'{mlab("2019-05")} 起改用 Refinitiv 数据。Exhibit 4 / 11 已用红色虚线画出，'
        '虚线两侧不可当作一条连续序列直读；Exhibit 13 的热力矩阵没有连续 x 轴，画不了这条线。',
        '<b>桥的假设（Exhibit 7 / 10 / 12）</b>：月度 asset-based fee = 当月平均 AUM × 有效费率 ÷ 12。'
        f'有效费率是从季报披露的 asset-based fee 收入反解出来的，所以<b>已收官季度是分摊而不是估计</b>；'
        f'最新已知季度（{last_q} = {last_bp:.3f}bp）之后的月份沿用该值，那一段才是真正的估计 —— '
        + (f'本次有 {n_ffill} 个月落在这一段。' if n_ffill else
           f'本次费率已覆盖到最新月 {mlab(LATEST)}，沿用段为空，桥全程是分摊。')
        + f'隐含序列只回溯到 {mlab(abf_months[0])}（费率最早覆盖 {qs[0]}）。',
        f'<b>桥的真实不确定性在费率而不是 AUM。</b>{qs[0]}–{last_q} 这 {len(qs)} 个季度里 AUM 复利上行，'
        f'但有效费率从 {bpq[0]:.2f}bp 压到 {bpq[-1]:.2f}bp；公司另行披露的期末 ETF 基点费率 '
        f'{DISC_Q[last_q]:.2f}bp 更低，因为它还覆盖非 ETF 的授权收入，两个口径不可互换。',
        '凡标题带 <b>Implied</b> 的都不是公司披露值（Exhibit 7 / 10 / 12）。Exhibit 10 的图注里逐季列了'
        '「隐含 vs 实际披露」的偏差，用来看桥搭得准不准 —— 看那组数，不看嘴上说。',
        '<b>窗口一律从数据最新月倒推</b>，不依赖构建日期：月度图 25 个月、季度图 14 个季度、'
        '年线图最近 6 年、热力矩阵最近 11 个年度、核对表 13 个月。'
        'Exhibit 12 取 24 个点（y/y 在第 25 格无值），画面内容与原 deck 相同。',
        '标题里的当期数字（YoY / MoM / 倍数 / 分位）全部随最新月重算，没有写死的字面量；'
        '比率序列（Exhibit 8）的同比一律用<b>百分点差</b>，不用「百分比的百分比变化」。',
        '汇总表的「月末 − 月均」一行会在零附近变号，百分比变化无意义，故其 m/m 与 y/y 用绝对额（$bn）；'
        '近 3 年分位对几乎单调的序列会恒等于 100，判定为单调（逐月差 ≥0 占比 ≥90%）时该行分位留空。',
    ]

    payload = {
        'ticker': 'msci',
        'tracker': 'MSCI Monthly ETF AUM Tracker',
        'title': f'MSCI Inc. (MSCI)：挂钩 MSCI 指数的 ETF 月度 AUM — {LATEST[:4]} 年 {int(LATEST[5:])} 月',
        'data_through': LATEST,
        'through_label': f'{LATEST[:4]} 年 {int(LATEST[5:])} 月',
        'subtitle': ('数据源：MSCI IR「AUM in ETFs Linked to MSCI Equity Indexes」（每月中旬更新上月）'
                     f' · 覆盖 {mlab(months[0])} – {mlab(LATEST)}（{len(months)} 个月）'
                     ' · 版式仿 Goldman Sachs GIR monthly-metrics'),
        'headline': (f'月末 AUM ${f(EOP[LATEST], 1)}bn（{sgn_pct(yoy(EOP, LATEST))} YoY，'
                     f'{sgn_pct(mom[LATEST])} MoM） · 当月平均 AUM ${f(AVG[LATEST], 1)}bn'
                     f'（{sgn_pct(aum_yoy)} YoY） · 隐含 asset-based fee ${abf[LATEST]:.1f}mn/月'
                     f'（{sgn_pct(yv[-1])} YoY） · 有效费率 {last_bp:.3f}bp（{last_q} 起沿用）'),
        'hub_line': (f'月末 AUM ${f(EOP[LATEST], 0)}bn，{pp_txt(yoy(EOP, LATEST))} YoY；'
                     f'有效费率压到 {last_bp:.2f}bp'),
        'source': SRC,
        'xlabels': XL13,
        'xlabels_long': XL_LONG,
        'summary': summary,
        'exhibits': ex,
        'table': table,
        'notes': notes,
        'footer': ('数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
                   '仅供个人研究，不构成投资建议'),
    }

    out = os.path.join(ROOT, 'data', 'msci.js')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as fh:
        # 构建日期只写首行注释，不进 payload：进了 payload，monthly_run 的
        # 「data 有没有实质变化」检查（忽略首行的正文比较）就永久失效。
        fh.write(f'// 由 build/msci.py 生成于 {datetime.date.today().isoformat()}，请勿手改\n')
        fh.write('window.DASH = ')
        json.dump(payload, fh, ensure_ascii=False, separators=(',', ':'))
        fh.write(';\n')

    print(f'数据最新月 {LATEST}｜月度序列 {months[0]} → {months[-1]}（{len(months)} 个月）')
    print(f'费率季度 {qs[0]} → {qs[-1]}（{len(qs)} 季）｜隐含 ABF 覆盖 {abf_months[0]} → {abf_months[-1]}')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）+ Exhibit {table["n"]} 核对表')
    print(f'写出 {out}（{os.path.getsize(out) / 1024:.1f} KB）')
    print(payload['headline'])


if __name__ == '__main__':
    main()
