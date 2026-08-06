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
import re

import payload_guard
import pctile        # 3Y %ile 的唯一实现，全站共用（各写各的正是同一序列两页判定相反的原因）

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


def qname(j):
    """绝对季序号 → '2026Q2'（qi 的逆运算，用来现算「缺哪几个季度」）。"""
    return f'{j // 4:04d}Q{j % 4 + 1}'


def qlab_month(q):
    """'2023Q3' → 该季末月份 '2023-09'（原 deck 把季度费率挂在季末月上）。"""
    y, k = q.split('Q')
    return f'{int(y):04d}-{int(k) * 3:02d}'


# ────────────────────────────── 格式化（一律 Python 侧） ──────────────────────────────
# 负零（'-0.0%'、'-0'、'-$0.0'）是四舍五入的产物而不是数据：一整片两位数里冒出一个
# 「-0」，读者会停下来想这是不是缺失值（tsm Ex13、exchanges Ex8 都被人眼审查挑出来过）。
# 本页当前数据没有命中，但格式化口径应当先立在这里，不等下个月的数据来触发。
_NEGZERO = re.compile(r'^-(\$?)(0(?:[.,]0+)?)(\D*)$')


def nz(s):
    """把「四舍五入后等于零却带负号」的展示串去掉负号；其余原样返回。"""
    m = _NEGZERO.match(s)
    return m.group(1) + m.group(2) + m.group(3) if m else s


def f(v, d=1):
    return nz(f'{v:,.{d}f}')


def sgn_pct(v, d=1):
    """带正负号的百分比；同 gsx 的 f'{v:+.1f}%'。"""
    return nz(f'{v:+.{d}f}%')


def pp_txt(v):
    """gsx._pp：绝对值 < 2 用一位小数，否则整数。"""
    return nz(f'{v:+.1f}%' if abs(v) < 2 else f'{v:+.0f}%')


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

    # ── 费率的期间披露（Exhibit 7 / 8 / 10 / 12 与核对表的「有效费率」列共用）──
    # AUM 每月往前走、费率每季才更新一次，所以「最新一两个月用的是上一季费率」是这页的
    # 常态口径而不是 bug —— 但图上看不出来，读者有权知道当期到底吃的哪一季。
    # 整段全部从数据现算：季度号写死的话，下个季度这句话就变成假话。
    DQ = qof(LATEST)                                     # 本页数据最新月所在季度
    lag_q = qi(DQ) - qi(last_q)                          # 费率落后数据月所在季度几个季度
    # 沿用段的起点：第一个「所在季度还没有披露费率」的月份（n_ffill=0 时为 None）
    ffill_from = next((k for k in abf_months if qof(k) not in BP_Q), None)
    # 过期判据：季报总在季末之后才发，故「费率落后 1 个季度」是正常节奏（本季末月的费率
    # 要等下季才披露）；比上一季还老才算过期，此时必须显式说，不能让读者自己去数。
    STALE = lag_q > 1
    miss_qs = [qname(j) for j in range(qi(last_q) + 1, qi(DQ) + 1)]
    FEE_Q_BODY = (
        f'费率取 <b>{last_q}</b> 的公司披露值（{last_bp:.3f}bp），'
        f'本页 AUM 数据截至 {mlab(LATEST)}（{DQ}）—— 费率按季披露、AUM 按月披露，两者天然错位。'
        + (f'因此 {mlab(ffill_from)} 起的 {n_ffill} 个月沿用 {last_q} 的费率，'
           '这一段的隐含值是估计而不是分摊。'
           if n_ffill else
           f'本轮费率已覆盖到最新月所在的 {DQ}，没有任何月份沿用更早季度的费率。')
        + (f' ⚠️ <b>费率已过期</b>：尚未更新至 {"、".join(miss_qs)}，本图仍用 {last_q} '
           f'的费率，落后本页数据月所在季度 {lag_q} 个季度（正常节奏是落后 1 季以内）。'
           if STALE else ''))
    FEE_Q_CN = '<b>费率期间</b>：' + FEE_Q_BODY          # 图注里用，自带小标题
    FEE_Q_EN = (
        f'Quarterly fee rate: latest disclosed is {last_q} at {last_bp:.3f}bp, while AUM here runs '
        f'through {mlab(LATEST)} ({DQ})'
        + (f'; the {n_ffill} month(s) from {mlab(ffill_from)} carry the {last_q} rate forward.'
           if n_ffill else
           f' — the rate already covers {DQ}, so no month carries an older quarter’s rate.')
        + (f' WARNING: the rate has not been updated to {"/".join(miss_qs)}; it lags the data '
           f'quarter {DQ} by {lag_q} quarters.' if STALE else ''))

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

    # 3Y %ile 一律走 build/pctile.py：判据（回放近 24 个月，≥70% 钉在极值就留空）是**口径**，
    # 口径只能有一处定义。本页原来那份「逐月差 ≥0 占比 ≥90% 就留空」的本地实现拦不住
    # 月末 / 月均这两行 —— 它们上下波动过得了 90% 那关，可分位常年钉 100，印出来是噪音。
    blank_why = []

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
        ser = [d[x] for x in keys]                     # 按月升序的整条序列，cur 是最后一格
        txt_, cls_ = pctile.cell(ser, keys.index(cur))
        cells.append({'v': txt_, 'cls': cls_} if txt_ else {'v': ''})
        if not txt_:
            blank_why.append((label, pctile.why_blank(ser)))
        return {'label': label, 'cells': cells}

    # 先把行算出来（sum_row 会往 blank_why 里登记留空原因），表注再引用它 ——
    # 靠 dict 字面量的求值顺序来保证「先 rows 后 note」太脆，显式分两步。
    srows = [
        {'kind': 'group', 'label': 'ETF AUM linked to MSCI indexes'},
        sum_row('Month-end AUM ($bn)', EOP, months),
        sum_row('Average AUM for the month ($bn)', AVG, months),
        # 期末−月均会在零附近变号，百分比变化没有意义 —— 这一行的差异用绝对额（$bn）
        sum_row('Month-end less monthly average ($bn)', diff, months, mode='abs'),
    ]
    blank_txt = ('本轮留空：'
                 + '；'.join(f'{lab}（{why}）' for lab, why in blank_why) + '。'
                 ) if blank_why else '本轮各行均未触发留空，分位照算。'
    summary = {
        'title': f'MSCI-linked ETF AUM summary — {mlab(LATEST)}',
        'heads': [mlab(cur), mlab(prv), mlab(yag), 'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': srows,
        'note': ('Average AUM is the fee-relevant measure: asset-based fees accrue on average assets, '
                 'not the month-end snapshot. All figures are MSCI estimates and include linked ETNs '
                 '(&lt;1% of AUM). 3Y %ile = 当月读数在最近 36 个月里高于多少百分比的观测，'
                 '判据与留空规则由全站唯一实现 <code>build/pctile.py</code> 给出：'
                 '回放最近 24 个月，若 ≥70% 的月份分位都钉在 100 或 0，说明这一列对该行没有区分度，留空。'
                 + blank_txt +
                 '「期末 − 月均」一行会在零附近变号，故 m/m 与 y/y 用绝对额（$bn）而非百分比变化。'),
    }

    ex = []

    # ══════════════════════════ Exhibit 2：月末 AUM 水平柱 ══════════════════════════
    v2 = [EOP[k] for k in W25]
    yoy2, mom2 = yoy(EOP, LATEST), (EOP[LATEST] / EOP[ym(li - 1)] - 1) * 100
    # 次轴同比取代 12 个月均线：原 deck 这张图走 gsx.lvl_bar，其 docstring 明写
    # 「次轴画的是同比而不是滚动均线 —— 均线只是把柱子再平滑一遍、不带新信息」。
    yoy2_s = [yoy(EOP, k) for k in W25]                 # 25 个月各自的 y/y（%）
    ex.append({
        'n': 2, 'kind': 'gs_bar', 'fmt': 'f0c', 'label_fmt': 'f0c', 'xlabels': XL25,
        'title': (f'Month-end AUM in MSCI-linked ETFs — ${f(EOP[LATEST], 0)}bn in {mlab(LATEST)}, '
                  f'{pp_txt(yoy2)} YoY and {pp_txt(mom2)} MoM'),
        'ylab': '$bn', 'ylab2': '% y/y', 'legend': 'Month-end AUM',
        'values': RL(v2),
        'yoy': {'name': 'y/y (RHS)', 'color': 'GOLD', 'values': RL(yoy2_s), 'yfmt': 'pct0'},
        'mom_txt': f'{pp_txt(mom2)} m/m',
        'note': ('第三方 ETF 的资产规模（客户端产品），不是 MSCI 自身营收；由 MSCI 官方按月披露。'
                 '金色线是<b>右轴同比</b>（%），不是 12 个月均线 —— 均线只是把柱子再平滑一遍、'
                 '不带新信息，同比才回答「相对去年这个月是好是坏」（同原 deck 的 gsx.lvl_bar）。'
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
    # 断点滚出窗口就优雅降级：brk_i = None → 不给 break_at，图注里也不提那条线。
    # 本页两张长历史图画的是**全序列**，2019-04 只要还在 CSV 里就一定在窗口内；
    # 会滚出去的是取尾窗的图（lpla 就是在这种守卫上硬失败的），所以这里不抛异常。
    BRK = '2019-04'
    brk_i = months.index(BRK) if BRK in EOP else None
    BRK_LAB = '数据源切换'          # 整页中文，断点标签不再写英文 'data provider switch'
    # 线画在 2019-04，语义是「从这一期起与左侧不可比」，而 2019-04 本身就是缝合月 ——
    # 原文案写「May-19 起改用 Refinitiv」，把 2019-04 排除在两侧之外，与线的位置自相矛盾。
    BRK_SRC = ('Apr-2019 is the stitched month: the month-end figure is already Refinitiv while the '
               'monthly average splices 4/1-4/25 Bloomberg with 4/26-4/30 Refinitiv. Earlier months '
               'are MSCI estimates built on Bloomberg data; from May-2019 the series is fully Refinitiv.')
    BRK_CN = ('⚠️ 红色虚线画在 <b>2019-04</b>，语义是「从这一期起与左侧不可比」：MSCI 的数据供应商在 '
              '2019 年 4–5 月由 Bloomberg 换成 Refinitiv，而 <b>2019-04 这一格本身就是缝合月</b> —— '
              '月末值已是 Refinitiv，月均值是 4/1–4/25 Bloomberg 加 4/26–4/30 Refinitiv 拼出来的，'
              '2019-05 起才全程 Refinitiv。线左侧、线上这一格、线右侧是三段口径，不可直读为一条连续序列。')
    NO_BRK_CN = ('（口径断点 2019-04 已不在本图窗口内，故本图没有画断点线；'
                 '数据供应商切换的说明见页尾「口径与方法说明」。）')

    ex4 = {
        'n': 4, 'kind': 'lines', 'x': 'long', 'full': True, 'height': 300,
        'fmt': 'f0c', 'label_fmt': 'f0c', 'xstep': max(1, len(months) // 14), 'xrot': 90,
        # zero_base：不给的话引擎走 y0 = min − 极差×5%，那是一次没有标注的隐性截轴，
        #   在长历史图上会凭空放大增幅（同 gsx.long_line 的 set_ylim(0, max*1.16)）。
        # end_label：deck 的 n_label —— 长历史图上唯一的绝对水平锚点。这两张图原来
        #   一个数据标签都没有，读者只能对着几百 $bn 一格的刻度目测。
        'zero_base': True, 'end_label': True,
        'title': (f'Full AUM history since {mlab(months[0])} — from ${f(EOP[months[0]], 0)}bn to '
                  f'${f(EOP[LATEST], 0)}bn ({EOP[LATEST] / EOP[months[0]]:.1f}x over '
                  f'{(li - mi(months[0])) / 12:.0f} years)'),
        'ylab': '$bn',
        'series': [{'name': 'Month-end AUM', 'color': 'NAVY', 'values': RL([EOP[k] for k in months])}],
        'note': BRK_CN if brk_i is not None else NO_BRK_CN,
    }
    if brk_i is not None:
        ex4['break_at'] = brk_i
        ex4['break_label'] = BRK_LAB
        ex4['src_extra'] = BRK_SRC
    ex.append(ex4)

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
    yoy7 = (abf[LATEST] / abf[ym(li - 12)] - 1) * 100
    # 同 Exhibit 2：次轴同比取代 12 个月均线（原 deck 走 gsx.lvl_bar）
    yoy7_s = [((abf[k] / abf[ym(mi(k) - 12)] - 1) * 100) if ym(mi(k) - 12) in abf else None
              for k in W25a]
    ex.append({
        'n': 7, 'kind': 'gs_bar', 'fmt': 'f1', 'label_fmt': 'f1', 'xlabels': XL25a,
        'title': (f'Implied asset-based fee revenue — {mlab(LATEST)} ${abf[LATEST]:.1f}mn, '
                  f'{yoy7:+.0f}% YoY'),
        'ylab': '$mn / month', 'ylab2': '% y/y', 'legend': 'Implied asset-based fee',
        'values': RL([abf[k] for k in W25a]),
        'yoy': {'name': 'y/y (RHS)', 'color': 'GOLD', 'values': RL(yoy7_s), 'yfmt': 'pct0'},
        'src_extra': BR_NOTE + ' ' + FEE_Q_EN,
        'note': ('<b>Implied</b>：不是公司披露的月度值。' + BR_NOTE +
                 f' 序列自 {mlab(abf_months[0])} 起，因为费率最早只回溯到 {qs[0]}。'
                 '金色线是<b>右轴同比</b>（%），不是滚动均线。' + FEE_Q_CN),
    })

    # ══════════════════════════ Exhibit 8：有效费率（季度） ══════════════════════════
    # 窗口：原 deck 是 win=14（最近 14 个季度）。原来这里画的是全序列（现已 30 季），
    # 与同页 Ex5 / Ex10 的 qkeys[-14:] 不一致，且季度越攒越多柱子越挤。
    QS8 = qs[-14:]
    bpq = [BP_Q[q] for q in QS8]
    XLbp = [mlab(qlab_month(q)) for q in QS8]
    # 序列本身的刻度就是 bp（CSV unit=bp_of_etf_aum），所以两个 bp 相减得到的同比差额
    # 单位仍是 bp，不是 pp。标成 pp 会把幅度放大 100 倍（-0.49bp 读成 -49bp）。
    def bp_yoy(q):
        j = qs.index(q)
        return BP_Q[q] - BP_Q[qs[j - 4]] if j >= 4 else None
    yoy8_s = [bp_yoy(q) for q in QS8]                     # 逐季基点差（bp），次轴用
    yoy8 = yoy8_s[-1]
    ex.append({
        # 原 deck 用 dec=2，本页原来退到 f1，理由是「FMT 里没有 f2」—— 那条注释早已过时
        # （assets/charts.js:105 有 f2）。f1 会把 3.984/4.022/3.995/3.956 四个季度全印成
        # 「4.0」、3.747/3.722 全印成「3.7」，而这张图的全部信息量就是这 0.7bp 的压缩。
        'n': 8, 'kind': 'gs_bar', 'fmt': 'f2', 'label_fmt': 'f2', 'xlabels': XLbp,
        'title': (f'Effective asset-based fee rate — {last_q} {last_bp:.3f}bp, '
                  f'{yoy8:+.2f}bp YoY（近 {len(QS8)} 个季度 {bpq[0]:.2f}bp → {bpq[-1]:.2f}bp）'),
        'ylab': 'bp of average ETF AUM', 'ylab2': 'y/y（基点差，bp）',
        'legend': 'Effective rate (quarterly)',
        'values': RL(bpq),
        # pct_series 型序列的同比是基点差；右轴刻度就是 bp，故 yfmt 用 f2 而不是 pp/pct
        'yoy': {'name': 'y/y（bp 差，RHS）', 'color': 'GOLD', 'values': RL(yoy8_s), 'yfmt': 'f2'},
        'note': ('Reported asset-based fee revenue / average MSCI-linked ETF AUM. '
                 'This is the bridge\'s real uncertainty: AUM compounded but the rate compressed from '
                 f'{bpq[0]:.2f}bp to {bpq[-1]:.2f}bp over the {len(QS8)} quarters shown. '
                 f'The period-end ETF fee of {DISC_Q[last_q]:.2f}bp is lower as it also covers '
                 'non-ETF licensing. 本图窗口取最近 '
                 f'{len(QS8)} 个季度（同原 deck 的 win=14，也与同页 Ex5 / Ex10 一致）；'
                 f'费率全序列自 {qs[0]} 起共 {len(qs)} 季，更早的季度不在图上。'
                 '柱子从 0 起（柱图不许截基线），所以 4.1bp → 3.4bp 这段压缩在柱高上看不出来 —— '
                 '要看压缩请读<b>金色的右轴线</b>：它画的是逐季基点差，'
                 f'最近一季 {yoy8:+.2f}bp。y 轴刻度就是 bp，故同比用<b>基点差（bp）</b>，'
                 '不是「百分比的百分比变化」，也不是百分点（1pp = 100bp）；'
                 'x 轴标的是各季末月份。逐季精确值（bp）：'
                 + '、'.join(f'{q} {BP_Q[q]:.3f}' for q in QS8) + '。' + FEE_Q_CN
                 + f'本图最右一根柱就是 {last_q}，右侧没有画到的月份不是数据缺失，'
                 '而是该季费率还没披露。'),
        'src_extra': FEE_Q_EN,
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
                      'if the quarter is incomplete. ' + FEE_Q_EN),
        'note': ('<b>Implied</b>：月度桥的季度合计。已收官季度可与公司披露的 asset-based fee 收入对表 —— '
                 + '；'.join(f'{q} 隐含 ${aqsum[q]:.0f}mn vs 实际 ${REV_Q[q]:.0f}mn'
                             f'（差 {(aqsum[q] / REV_Q[q] - 1) * 100:+.1f}%）'
                             for q in AQW[-4:] if q in REV_Q)
                 + '。差异来自月均 AUM 与公司季均口径的细微出入，不是费率错。' + FEE_Q_CN),
    })

    # ══════════════════════════ Exhibit 11：全历史（月均） ══════════════════════════
    ex11 = {
        'n': 11, 'kind': 'lines', 'x': 'long', 'full': True, 'height': 300,
        'fmt': 'f0c', 'label_fmt': 'f0c', 'xstep': max(1, len(months) // 14), 'xrot': 90,
        'zero_base': True, 'end_label': True,          # 同 Exhibit 4，理由见那里
        'title': (f'Average AUM since {mlab(months[0])} — ${f(AVG[LATEST], 0)}bn in {mlab(LATEST)}, '
                  f'{AVG[LATEST] / AVG[months[0]]:.1f}x the {months[0][:4]} starting level'),
        'ylab': '$bn',
        'series': [{'name': 'Average AUM for month', 'color': 'NAVY',
                    'values': RL([AVG[k] for k in months])}],
        'note': ('⚠️ 与 Exhibit 4 同一条断点线（2019-04）。<b>月均这一列受缝合的影响比月末更大</b>：'
                 '2019-04 的月均值是 4/1–4/25 Bloomberg 加 4/26–4/30 Refinitiv 拼出来的，'
                 '而同月的月末值已经全是 Refinitiv。'
                 if brk_i is not None else NO_BRK_CN),
    }
    if brk_i is not None:
        ex11['break_at'] = brk_i
        ex11['break_label'] = BRK_LAB
        ex11['src_extra'] = BRK_SRC
    ex.append(ex11)

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
        'src_extra': ('Grows more slowly than AUM because the effective rate has been compressing. '
                      + FEE_Q_EN),
        'note': ('增速慢于 AUM，差额就是有效费率的压缩（见 Exhibit 8）。'
                 f'{mlab(LATEST)}：隐含费收 {sgn_pct(yv[-1])} vs 平均 AUM {sgn_pct(aum_yoy)}，'
                 f'缺口 {yv[-1] - aum_yoy:+.1f}pp。' + FEE_Q_CN),
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
            'diff': nz(f'{diff[k]:+,.1f}'),
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
        '⚠️ <b>口径断点 2019-04（数据供应商切换）</b>：MSCI 在 2019 年 4–5 月把数据供应商从 Bloomberg '
        '换成 Refinitiv，<b>2019-04 这一格本身就是缝合月</b> —— 月末值已是 Refinitiv，'
        '月均值是 4/1–4/25 Bloomberg 加 4/26–4/30 Refinitiv 拼的，2019-05 起才全程 Refinitiv。'
        + ('断点线因此画在 2019-04（引擎语义：从这一期起与左侧不可比），Exhibit 4 / 11 各一条红色竖虚线；'
           if brk_i is not None else
           '该月已不在 Exhibit 4 / 11 的窗口内，本次没有画出断点线；')
        + 'Exhibit 13 的热力矩阵没有连续 x 轴，画不了这条线，读 2019 那一行请自行留意。',
        '<b>桥的假设（Exhibit 7 / 10 / 12）</b>：月度 asset-based fee = 当月平均 AUM × 有效费率 ÷ 12。'
        f'有效费率是从季报披露的 asset-based fee 收入反解出来的，所以<b>已收官季度是分摊而不是估计</b>；'
        f'最新已知季度（{last_q} = {last_bp:.3f}bp）之后的月份沿用该值，那一段才是真正的估计 —— '
        + (f'本次有 {n_ffill} 个月落在这一段。' if n_ffill else
           f'本次费率已覆盖到最新月 {mlab(LATEST)}，沿用段为空，桥全程是分摊。')
        + f'隐含序列只回溯到 {mlab(abf_months[0])}（费率最早覆盖 {qs[0]}）。',
        # 核对表（Exhibit 14）的渲染器只吃 cols/rows，挂不上 note；它的「有效费率」列
        # 里同一季的三个月是同一个数，读者最容易把它误读成月度披露值 —— 所以这条必须在。
        '<b>费率的期间口径（Exhibit 7 / 8 / 10 / 12 与核对表的「有效费率」列）</b>：' + FEE_Q_BODY
        + f'Exhibit 8 的最右一根柱就是 {last_q}；核对表里同属一个季度的月份填的是<b>同一个</b>'
        '费率值（季度值下挂到月，不是月度披露）。判据本身也是现算的：费率最新可得季度比'
        '「数据月所在季度的上一季」还老，就在上面这段里加一句过期提示。',
        f'<b>桥的真实不确定性在费率而不是 AUM。</b>{qs[0]}–{last_q} 这 {len(qs)} 个季度里 AUM 复利上行，'
        f'但有效费率从 {BP_Q[qs[0]]:.2f}bp 压到 {BP_Q[qs[-1]]:.2f}bp（Exhibit 8 只画最近 {len(QS8)} 季，'
        f'即 {QS8[0]} 的 {bpq[0]:.2f}bp → {QS8[-1]} 的 {bpq[-1]:.2f}bp）；'
        f'公司另行披露的期末 ETF 基点费率 '
        f'{DISC_Q[last_q]:.2f}bp 更低，因为它还覆盖非 ETF 的授权收入，两个口径不可互换。',
        '凡标题带 <b>Implied</b> 的都不是公司披露值（Exhibit 7 / 10 / 12）。Exhibit 10 的图注里逐季列了'
        '「隐含 vs 实际披露」的偏差，用来看桥搭得准不准 —— 看那组数，不看嘴上说。',
        '<b>窗口一律从数据最新月倒推</b>，不依赖构建日期：月度图 25 个月、季度图 14 个季度'
        f'（Exhibit 5 / 8 / 10 三张都是 14 季）、年线图最近 6 年、热力矩阵最近 11 个年度、核对表 13 个月。'
        'Exhibit 12 取 24 个点（y/y 在第 25 格无值），画面内容与原 deck 相同。',
        '<b>柱图的右轴金色线是同比，不是滚动均线</b>（Exhibit 2 / 7 / 8）：均线只是把柱子再平滑一遍、'
        '不带新信息，同比才回答「相对去年这个月是好是坏」，这也是原 deck（gsx.lvl_bar）的画法。'
        '开了同比线的图不再画那条 12 个月均线虚线，也不再另给同比气泡。'
        'Exhibit 8 的右轴单位是<b>基点差（bp）</b>而不是百分比：该序列的刻度本身就是 bp。',
        '标题里的当期数字（YoY / MoM / 倍数 / 分位）全部随最新月重算，没有写死的字面量；'
        '有效费率（Exhibit 8）以 bp 为刻度，其同比一律用<b>基点差（bp）</b>的绝对差，'
        '不用「百分比的百分比变化」，也不写成百分点（1pp = 100bp）。'
        '四舍五入后等于零的负数一律写成 0（不写「-0」，那是格式化产物不是数据）。',
        '汇总表的「月末 − 月均」一行会在零附近变号，百分比变化无意义，故其 m/m 与 y/y 用绝对额（$bn）；'
        '3Y %ile 的算法与留空判据由全站唯一实现 <code>build/pctile.py</code> 提供'
        '（回放近 24 个月，≥70% 的月份分位钉在 100 或 0 就留空），本页不再自带一份分位逻辑 —— '
        '同一条序列在两页判定相反，根因就是各写各的。',
        '<b>与原 deck 仍有的两处差距（网页引擎的能力缺口，不是笔误）</b>：一是数值标签的 '
        '「$ + 千分位」这一档格式器 charts.js 没有，所以 Exhibit 2 / 6 / 7 / 9 与 Exhibit 4 / 11 的'
        '末点标签写作 <code>2,818</code> 而非 <code>$2,818</code>，单位由纵轴标题（$bn / $mn）交代；'
        '二是 deck 在 Exhibit 4 / 11 的最近 3 个点外圈了一个红色虚线椭圆（"最近三个月在这里"），'
        '网页没有这个图元，改由末点数值标注承担「最新一点在哪」的作用。',
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
                     # 抬头不能只报喜：费率是这页唯一往下走的量，同比压缩幅度要一起写出来。
                     # 「起沿用」只在真有沿用月份时才说（n_ffill=0 时那句话是假的）。
                     f'（{sgn_pct(yv[-1])} YoY） · 有效费率 {last_bp:.3f}bp'
                     f'（{last_q}，{yoy8:+.2f}bp YoY'
                     + (f'，其后 {n_ffill} 个月沿用该值）' if n_ffill else '，已覆盖到最新月）')),
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
        # 这一页没有 source_date，而且**永远不会有**：MSCI 的 AUM 页是一张「活页面」，
        # 每月悄悄改表，页面正文、meta、Drupal 设置、RSS、email-alerts、download-library、
        # sitemap 全查过，没有任何自述发布日；也不为此发新闻稿。唯一的机器时间戳
        # HTTP Last-Modified 是边缘渲染时刻不是数据时刻（见 fetch/msci.py docstring）。
        # 季报 8-K 的 Table 7 虽然有确定申报日，但一年只覆盖 4 个季末月、口径只有整数十亿的
        # 季末值（本页画的月均它证明不了），而且多半晚于 IR 页实际上线的日子 ——
        # 拿它当发布日就是一个看不出来是假的、系统性偏晚的日期。所以宁可明说没有。
        # 若哪天 MSCI 在页面上加了 "Updated" 行：_download() 每天都存快照
        # cache/msci_aum_YYYYMMDD.html，到时候解析很容易补上。
        'source_date_note': '官方未标注发布日',
    }

    out = os.path.join(ROOT, 'data', 'msci.js')
    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(out, payload, 'msci')

    print(f'数据最新月 {LATEST}｜月度序列 {months[0]} → {months[-1]}（{len(months)} 个月）')
    print(f'费率季度 {qs[0]} → {qs[-1]}（{len(qs)} 季）｜隐含 ABF 覆盖 {abf_months[0]} → {abf_months[-1]}')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）+ Exhibit {table["n"]} 核对表')
    print(f'写出 {out}（{os.path.getsize(out) / 1024:.1f} KB）')
    print(payload['headline'])


if __name__ == '__main__':
    main()
