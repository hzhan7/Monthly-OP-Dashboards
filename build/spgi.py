# -*- coding: utf-8 -*-
"""S&P Global (SPGI) 月度指标 —— 生成 data/spgi.js（网页看板的数据源）。

本文件是 build/build_spgi.py（matplotlib / PDF 版）的网页移植：exhibit 的顺序、编号、
标题文案、图注、口径断点全部照搬那份 deck，数值一律从 series/spgi_clean.csv 现算，
页面不做任何计算（见 build/CONTRACT.md）。

模版来源：Goldman Sachs「IBKR Monthly」的成对图法（水平柱 + 均线 + YoY 气泡）
          与 JPM AXP 的季节性/热力图型。
数据源：S&P Global 官网 IR「Quarterly Earnings & Monthly Metrics」栏目每月 15 日发布的
        xlsx（两个 sheet：S&P Global Ratings / S&P Dow Jones Indices）。
        该 xlsx **不进 SEC EDGAR**，只挂官网；investor.spglobal.com 对 curl 一律
        Cloudflare 403 —— 但 s29.q4cdn.com 的 CDN 直链可直接下载。

⚠️ 披露口径的硬约束（决定了本页为何比其他标的薄）：
   · Billed Issuance 官方**只披露同比百分比，从不给绝对面值**。故本页用同比链式
     构造一个指数（2024 年同月 = 100）来呈现相对水平，指数本身不是公司披露值。
   · SPDJI ADV 官方给绝对值，但每份 xlsx 只含当年与上年两年。2024 年的绝对值由
     2025 年值与官方「'25 v. '24 % Change」反算得到（披露数据的算术推导，非估计）。
   · 更早年份的历史文件在 CDN 上已不可访问，故序列起点为 2024-01。
   · 从 2025-12 起 ADV 定义剔除 event contracts，且不追溯重述早期月份 → 断点。

与 PDF 版的两处有意差异（其余逐字照搬）：
   1. gsx.lvl_bar 的右轴金色 y/y 折线在网页 `gs_bar` 里没有对位物，改为
      「Prior 12mo Avg.」虚线 + 左上角 y/y 气泡（CONTRACT §3 的 kind 映射表如此规定）。
   2. Exhibit 2 / 3 走通栏（25 根柱塞进半栏时每柱数值标签会互相压住）；
      热力图在 PDF 里是通栏，网页上留在半栏 —— 通栏卡片会被渲染器统一提到汇总表
      下方，Exhibit 7 若通栏就会跑到 Exhibit 2 前面，编号顺序比宽度更重要。
"""
import csv
import datetime
import json
import os

import payload_guard

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series', 'spgi_clean.csv')
OUT = os.path.join(ROOT, 'data', 'spgi.js')

SRC = 'Source: S&P Global monthly metrics xlsx; format after Goldman Sachs GIR'
DNOTE = ('2024 ADV values are back-calculated from the 2025 level and the officially '
         "disclosed 25 v. 24 % change")
INOTE = ('Billed issuance is disclosed as a y/y % only; this index chains those '
         'percentages (same month of 2024 = 100)')
EVENT = ('From Dec-2025 the ADV definition excludes event contracts, with no restatement '
         'of earlier months')

MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
CN_MON = ['1 月', '2 月', '3 月', '4 月', '5 月', '6 月',
          '7 月', '8 月', '9 月', '10 月', '11 月', '12 月']


# ────────────────────────────── 读数 ──────────────────────────────
def mkey(s):
    """'2026-06' → 整数月序，方便做相邻/同比检查。"""
    y, m = s.split('-')
    return int(y) * 12 + int(m) - 1


def mlab(s):
    """'2026-06' → 'Jun-26'（与 gsx.mlab 的 %b-%y 一致）。"""
    y, m = s.split('-')
    return f'{MON[int(m) - 1]}-{y[2:]}'


def load():
    with open(SERIES, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    need = ['month', 'spdji_adv_mn', 'spdji_adv_yoy', 'billed_issuance_yoy',
            'adv_derived', 'billed_issuance_index']
    for c in need:
        if c not in rows[0]:
            raise SystemExit(f'series/spgi_clean.csv 缺列 {c}')
    rows.sort(key=lambda r: r['month'])
    months = [r['month'] for r in rows]
    # 月份必须逐月连续：断档的序列画成相邻柱就是假的时间轴（gsx._tail_contiguous 的动机）
    for i in range(1, len(months)):
        if mkey(months[i]) - mkey(months[i - 1]) != 1:
            raise SystemExit(f'月份不连续：{months[i - 1]} → {months[i]}')

    def col(name):
        out = []
        for r in rows:
            v = (r[name] or '').strip()
            out.append(float(v) if v else None)
        return out

    return months, {c: col(c) for c in need[1:]}


MONTHS, COL = load()
ADV = COL['spdji_adv_mn']
ADVY = COL['spdji_adv_yoy']
BIY = COL['billed_issuance_yoy']
BIDX = COL['billed_issuance_index']
DERIVED = COL['adv_derived']
LATEST = MONTHS[-1]
LY, LM = int(LATEST[:4]), int(LATEST[5:])

for name, arr in (('spdji_adv_mn', ADV), ('spdji_adv_yoy', ADVY),
                  ('billed_issuance_yoy', BIY), ('billed_issuance_index', BIDX)):
    if arr[-1] is None:
        raise SystemExit(f'最新月 {LATEST} 的 {name} 为空，拒绝出图')


# ────────────────────────────── 小工具 ──────────────────────────────
def r6(v):
    """payload 里的数值统一收到 6 位小数：显示最多用到 3 位，多余的位只是噪音，
    而且会让 monthly_run 的「data 有没有实质变化」逐字节比较更脆。"""
    return None if v is None else round(float(v), 6)


def num(v, dec, pct=False):
    """已格式化的单元格字符串（页面不做计算，格式化是口径的一部分）。"""
    if v is None:
        return '—'
    return f'{v:,.{dec}f}' + ('%' if pct else '')


def tail(arr, n):
    return arr[-n:]


def prior12(vals):
    """「Prior 12mo Avg.」= 最新月**之前**的 12 个月均值（不含当月），
    与 IBKR 站 avg12(a[:12]) 在 13 个月窗口上的语义相同。"""
    hist = [v for v in vals[-13:-1] if v is not None]
    if len(hist) < 12:
        hist = [v for v in vals[:-1] if v is not None][-12:]
    if not hist:
        raise SystemExit('prior12：可用样本为 0')
    return sum(hist) / len(hist)


def pctile36(vals):
    """近 36 个月分位。单调序列（几乎只增不减）返回 None —— 分位恒 100 是噪音
    不是信息（CONTRACT §2）。"""
    hist = [v for v in vals if v is not None][-36:]
    if len(hist) < 8:
        return None
    d = [hist[i] - hist[i - 1] for i in range(1, len(hist))]
    if d and sum(1 for x in d if x >= 0) / len(d) >= 0.90:
        return None
    cur = hist[-1]
    return sum(1 for x in hist if x < cur) / max(1, len(hist) - 1) * 100


def at(month):
    """按月份取整行下标；月份不在序列里直接抛异常（CONTRACT §5：失败要响）。"""
    return MONTHS.index(month)


def shift(month, k):
    n = mkey(month) + k
    return f'{n // 12}-{n % 12 + 1:02d}'


# ────────────────────────── Exhibit 1：汇总表 ──────────────────────────
CUR = LATEST
PRV = shift(LATEST, -1)
YAG = shift(LATEST, -12)

# (板块, 标签, 序列, 小数位, pct, mode, xmonth)
#   mode='pp' → 差值用 pp/bp，'ratio' → 百分比变化
#   xmonth   → 该行的水平值跨月是否可比。False 时 m/m 与 3Y %ile 一律留空：
#              两者都是「拿这个月的读数去比另一个月的读数」，分母不同就无从解释。
SUM_ROWS = [
    ('S&P Dow Jones Indices', None, None, 0, False, '', True),
    (None, 'ADV of exchange-traded derivatives (mn contracts)', ADV, 2, False, 'ratio', True),
    (None, 'ADV y/y as disclosed (%)', ADVY, 1, True, 'pp', True),
    ('S&P Global Ratings', None, None, 0, False, '', True),
    (None, 'Billed issuance y/y as disclosed (%)', BIY, 1, True, 'pp', True),
    # 链式指数：每个月各自以自己的 2024 同月为基数（见 Exhibit 3 图注与页脚说明第 3 条）。
    # m/m 展开是 (BI_Jun26/BI_Jun24)/(BI_May26/BI_May24) —— 两个不同且从未披露的分母的
    # 比值之比，不对应任何可解释的量；分位是把 18 个各带不同基数的读数排在一起比大小
    # （与 CONTRACT §2 对 4-4-5 净销售额、build/cost.py 对 net_sales_bn 的处理同构）。
    # y/y 保留：BI_2024 同月在分子分母上精确对消，等于官方披露的同比。
    (None, 'Billed issuance index (2024 same month = 100)', BIDX, 1, False, 'ratio', False),
]


def diff(a, b, mode):
    if a is None or b is None:
        return None
    if mode == 'pp':
        return a - b
    if b == 0 or a * b < 0:      # 分母为 0 或两期异号时，百分比变化无意义
        return None
    return (a / b - 1) * 100


def diff_cell(v, mode):
    if v is None:
        return {'v': ''}
    if mode == 'pp':
        txt = f'{v * 100:+.0f}bp' if abs(v) < 1 else f'{v:+.2f}pp'
    else:
        txt = f'{v:+.1f}%'
    return {'v': txt, 'cls': 'pos' if v > 0 else ('neg' if v < 0 else '')}


srows = []
for grp, lab, arr, dec, pct, mode, xmonth in SUM_ROWS:
    if lab is None:
        srows.append({'kind': 'group', 'label': grp})
        continue
    ic, ip, iy = at(CUR), at(PRV), at(YAG)
    c, p1, p12 = arr[ic], arr[ip], arr[iy]
    # 跨月不可比的行不进分位：pctile36 只会挡单调序列，挡不住「每期基数不同」。
    pv = pctile36(arr[:ic + 1]) if xmonth else None
    pcell = {'v': ''} if pv is None else {
        'v': f'{pv:.0f}', 'cls': 'hi' if pv >= 66 else ('lo' if pv <= 33 else '')}
    srows.append({'label': lab, 'cells': [
        {'v': num(c, dec, pct), 'cls': 'cur'},
        {'v': num(p1, dec, pct)},
        {'v': num(p12, dec, pct)},
        # 走 diff_cell(None) 而不是就地塞 {'v': ''}：空格子只有一个来源，
        # 也和 diff() 因分母为 0 / 异号而留空的写法完全同形。
        diff_cell(diff(c, p1, mode) if xmonth else None, mode),
        diff_cell(diff(c, p12, mode), mode),
        pcell,
    ]})

summary = {
    'title': f'S&P Global monthly metrics summary — {mlab(LATEST)}',
    'heads': [f'本月 {mlab(CUR)}', f'上月 {mlab(PRV)}', f'去年同月 {mlab(YAG)}',
              'm/m', 'y/y', '3Y %ile'],
    'sep': 3,
    'rows': srows,
    'note': (DNOTE + '.&nbsp; ' + INOTE + '.&nbsp; ' + EVENT + '.<br>'
             '两条 y/y 行本身就是比率，m/m 与 y/y 一律用百分点差（|差|&lt;1 用 bp），'
             '不是「百分比的百分比变化」。3Y %ile = 当月读数在近 36 个月里高于百分之多少的观测；'
             '两条 y/y 与指数序列 2025-01 才起步，分位只有 18 个观测垫底，只能当粗略刻度读。<br>'
             '<b>指数行的 m/m 与 3Y %ile 是刻意留空，不是缺数</b>：指数每个月各自以自己的 '
             '2024 同月为基数，跨月的变化是两个不同分母（且从未披露）的比值之比，'
             '不对应任何可解释的量，分位同理是拿苹果比橘子。'
             f'该行只有 y/y 可读 —— 2024 年同月基数在分子分母上对消，'
             f'{num(BIDX[at(CUR)], 1)} / {num(BIDX[at(YAG)], 1)} 恰好等于官方披露的 '
             f'{BIY[at(CUR)]:+.0f}%（上一行）。相邻两列的水平值仍照 Exhibit 3 列出供核对，'
             '但不可相减。'),
}

# ────────────────────────── Exhibit 2：SPDJI ADV ──────────────────────────
W2 = 25                                        # 照搬 deck 的 win=25
adv_w = tail(ADV, W2)
xl2 = [mlab(m) for m in tail(MONTHS, W2)]
brk = '2025-12'
brk_i = tail(MONTHS, W2).index(brk)
adv_yoy_lvl = (ADV[at(CUR)] / ADV[at(YAG)] - 1) * 100

ex2 = {
    'n': 2, 'kind': 'gs_bar', 'full': True, 'fmt': 'f1', 'xlabels': xl2,
    'title': 'SPDJI average daily volume of ETDs',
    'ylab': 'mn contracts / day',
    'legend': 'Monthly ADV',
    'values': [r6(v) for v in adv_w],
    'avg12': r6(prior12(ADV)),
    'yoy_txt': f'{adv_yoy_lvl:+.0f}% y/y',
    'break_at': brk_i, 'break_label': 'ex-event contracts',
    'bar_marks': [i for i, m in enumerate(tail(MONTHS, W2))
                  if DERIVED[at(m)] == 1],
    'mark_note': '该月 ADV 由 2025 年值与官方 25 v. 24 % change 反算，非直接披露值',
    'note': (f'柱为公司披露的 SPDJI 交易所交易衍生品日均成交量；虚线为 Prior 12mo Avg.'
             f'（{prior12(ADV):.2f}mn/日），气泡是最新月对去年同月的水平值同比 '
             f'{adv_yoy_lvl:+.1f}%，与公司披露的 {ADVY[at(CUR)]:+.1f}% 互为校验。'
             '红色虚线右侧起 ADV 口径剔除 event contracts，与左侧不可直读。'
             '斜纹柱为 2024 年的反算值（见图下 Source 行）。'),
    'src_extra': EVENT + '. ' + DNOTE + '.',
}

# ────────────────────────── Exhibit 3：Billed issuance index ──────────────
idx_i = [i for i, v in enumerate(BIDX) if v is not None]
i0 = idx_i[0]
idx_months = MONTHS[i0:]
idx_vals = BIDX[i0:]
W3 = min(25, len(idx_vals))                    # deck 的 win=25，序列只有 18 个月
idx_w = tail(idx_vals, W3)
xl3 = [mlab(m) for m in tail(idx_months, W3)]
idx_yoy = (BIDX[at(CUR)] / BIDX[at(YAG)] - 1) * 100

ex3 = {
    'n': 3, 'kind': 'gs_bar', 'full': True, 'fmt': 'f0', 'xlabels': xl3,
    'title': 'Ratings billed issuance index',
    'ylab': 'index, 2024 same month = 100',
    'legend': 'Monthly index',
    'values': [r6(v) for v in idx_w],
    'avg12': r6(prior12(idx_vals)),
    'yoy_txt': f'{idx_yoy:+.0f}% y/y',
    'note': ('<b>指数不是公司披露值</b>：官方每月只给 billed issuance 的同比百分比，'
             '本图把这些百分比链式接到「2024 年同月 = 100」上。因此每根柱各自以自己的'
             '2024 同月为基数，跨月读高低会混进 2024 年的季节性，'
             f'只有同比（{idx_yoy:+.0f}%，与官方披露的 {BIY[at(CUR)]:+.0f}% 一致）'
             '与虚线（Prior 12mo Avg.）是干净的。'
             '指数从 2025-01 起才有，故 y/y 从 2026-01 起才存在。'),
    'src_extra': INOTE + '; the y/y line starts Jan-2026.',
}

# ────────────────────────── Exhibit 4：两条披露 y/y ──────────────────────────
W4 = 18                                        # 照搬 deck 的 win=18
m4 = tail(MONTHS, W4)
biy4 = [r6(BIY[at(m)]) for m in m4]
advy4 = [r6(ADVY[at(m)]) for m in m4]
if any(v is None for v in biy4 + advy4):
    raise SystemExit('Exhibit 4 的窗口内存在缺失月，lines_endlabels 不接受缺口')

ex4 = {
    'n': 4, 'kind': 'lines_endlabels', 'fmt': 'f0', 'xlabels': [mlab(m) for m in m4],
    'title': 'The two disclosed y/y series side by side',
    'ylab': '% y/y',
    'series': [
        {'name': 'Ratings billed issuance', 'color': 'NAVY', 'values': biy4},
        {'name': 'SPDJI ADV', 'color': 'MBLUE', 'values': advy4},
    ],
    'note': ('两条线都是公司**直接披露**的同比百分比，不是本页推导值 —— 也是 S&amp;P Global '
             '每月唯一公布的两个数。两者口径完全不同（评级业务的计费发行量 vs 指数业务的'
             '衍生品日均成交），同向或背离都不构成因果，只是把「这个月两块业务各自的动能」'
             f'放在一起看。窗口 {mlab(m4[0])}–{mlab(m4[-1])}。'),
    'src_extra': 'These are the only two figures S&P Global publishes monthly.',
}

# ────────────────────────── Exhibit 5：季度 ADV ──────────────────────────
QN = 10                                        # 照搬 deck 的 win=10
qmap = {}
for m in MONTHS:
    if ADV[at(m)] is None:
        continue
    y, mm = int(m[:4]), int(m[5:])
    qmap.setdefault((y, (mm - 1) // 3 + 1), []).append(ADV[at(m)])
qkeys = sorted(qmap)
qvals = [sum(qmap[k]) / len(qmap[k]) for k in qkeys]      # how='mean'，不是合计
qn_last = len(qmap[qkeys[-1]])
qyoy = [None] * len(qvals)
for i in range(4, len(qvals)):
    if qvals[i - 4]:
        qyoy[i] = (qvals[i] / qvals[i - 4] - 1) * 100
qk = qkeys[-QN:]
qv = qvals[-QN:]
qy = qyoy[-QN:]
# 断点：口径变更从 2025-12 起，落在 2025Q4 这一季（该季只有一个月是新口径）
q_brk = [i for i, k in enumerate(qk) if k == (2025, 4)]

ex5 = {
    'n': 5, 'kind': 'qtr_bar', 'fmt': 'f1', 'label_fmt': 'f1',
    'xlabels': [f'{k[0]}Q{k[1]}' for k in qk],
    'title': 'SPDJI ADV by quarter',
    'ylab': 'mn contracts / day',
    'legend': 'Quarterly ADV (avg of monthly)',
    'values': [r6(v) for v in qv],
    'partial_months': qn_last, 'qtr_months': 3,
    'line': {'name': 'y/y（RHS）', 'color': 'GREEN', 'values': [r6(v) for v in qy],
             'yfmt': 'pct0'},
    'note': ('季度值是该季各月 ADV 的**简单平均**（日均口径不能相加），'
             '右轴 y/y 用 4 个季度前作分母，故前 4 个季度留空。'
             '2024 各季用的是反算出来的月度 ADV；2025Q4 起口径变更只影响该季的 12 月一个月，'
             '红色虚线标在该季左缘 —— 季度柱本身跨了新旧两套口径，是本图最脏的一根。'
             + (f'最新一季只含 {qn_last} 个月，柱为浅蓝、右轴 y/y 已作废。'
                if qn_last < 3 else '')),
    'src_extra': DNOTE + '.',
}
if q_brk:
    ex5['break_at'] = q_brk[0]
    ex5['break_label'] = 'ex-event contracts（季内一个月）'

# ────────────────────────── Exhibit 6：分年 ADV 路径 ──────────────────────────
NY = 3                                         # 照搬 deck 的 n_years=3
years = sorted({int(m[:4]) for m in MONTHS if ADV[at(m)] is not None})[-NY:]
yser = []
for y in years:
    vals = [None] * 12
    for m in MONTHS:
        if int(m[:4]) == y and ADV[at(m)] is not None:
            vals[int(m[5:]) - 1] = r6(ADV[at(m)])
    yser.append({'name': str(y), 'values': vals})

ex6 = {
    'n': 6, 'kind': 'year_lines', 'fmt': 'f1', 'label_fmt': 'f1', 'xlabels': MON,
    'title': 'SPDJI ADV path by year',
    'ylab': 'mn contracts / day',
    'series': yser,
    'highlight': len(yser) - 1,
    'note': ('画的是**水平值**不是累计（日均量累计没有意义），红线为当年。'
             f'{years[0]} 年整条线是反算值；'
             f'{LY} 年只到 {MON[LM - 1]}，其后留空而不是画成 0。'
             '12-2025 起的口径变更落在最后一条完整年份线的年末，'
             f'{LY} 与 {years[0]} 两条线不完全同口径。'),
    'src_extra': DNOTE + '.',
}

# ────────────────────────── Exhibit 7：billed issuance y/y 热力矩阵 ──────────
hy = sorted({int(m[:4]) for m in MONTHS})[-NY:]
matrix = []
for y in hy:
    row = [None] * 12
    for m in MONTHS:
        if int(m[:4]) == y and BIY[at(m)] is not None:
            row[int(m[5:]) - 1] = r6(BIY[at(m)])
    matrix.append(row)

ex7 = {
    'n': 7, 'kind': 'heat_matrix', 'fmt': 'f0',
    'title': 'Ratings billed issuance y/y (%)',
    'rows': [str(y) for y in hy], 'cols': MON, 'matrix': matrix,
    'legend': 'Billed issuance y/y', 'row_head': '年', 'cell_h': 22,
    'note': ('色标取全部有限值的 5/95 分位，绿 = 发行量增速更快。'
             '2024 一整行留空：那一年公司只披露了同比百分比的对照基数本身，'
             '没有可用的 y/y 读数（第一批 y/y 从 2025-01 起）。'
             '同一格的高低是相对**去年同月**，不是相对上月，'
             '所以一行里连着两个大正数并不等于绝对水平在连涨。'),
    'src_extra': 'Green = faster issuance growth; 2024 is blank because only y/y is disclosed.',
}

EXHIBITS = [ex2, ex3, ex4, ex5, ex6, ex7]

# ────────────────────────── Exhibit 8：核对表 ──────────────────────────
TN = 13
tm = tail(MONTHS, TN)
table = {
    'n': 8,
    'title': f'近 {TN} 个月月度指标核对表（官方原始单位，未换算）',
    'idx': '月份',
    'cols': [
        ['SPDJI ADV（mn 张/日）', 'adv'],
        ['ADV y/y（%，披露）', 'advy'],
        ['Billed issuance y/y（%，披露）', 'biy'],
        ['Billed issuance 指数（推导，2024 同月 = 100）', 'idx'],
    ],
    'rows': [{
        'xl': mlab(m),
        'adv': num(ADV[at(m)], 3),
        'advy': num(ADVY[at(m)], 1),
        'biy': num(BIY[at(m)], 0),
        'idx': num(BIDX[at(m)], 2),
    } for m in tm],
}

# ────────────────────────── notes / 抬头 ──────────────────────────
NOTES = [
    ('<b>数据源</b>：S&amp;P Global 官网 IR「Quarterly Earnings &amp; Monthly Metrics」栏目'
     '每月约 15 日发布的 xlsx，两个 sheet（S&amp;P Global Ratings / S&amp;P Dow Jones Indices）。'
     '该文件<b>不进 SEC EDGAR</b>，只挂官网；investor.spglobal.com 对 curl 一律 Cloudflare 403，'
     '但 s29.q4cdn.com 的 CDN 直链可直接下载。'),
    ('<b>公司每月只给两个数</b>：Ratings billed issuance 的 y/y 百分比、SPDJI 交易所交易衍生品的 ADV。'
     '本页比其他标的薄不是漏做，是披露就这么多 —— 没有收入、没有 AUM、没有分部拆分。'),
    ('⚠️ <b>Billed issuance 没有绝对面值</b>：官方只披露同比百分比，从不给面值。'
     'Exhibit 3 的指数是把这些百分比链式接到「2024 年同月 = 100」上构造的，'
     '<b>指数本身不是公司披露值</b>；每个月各自以自己的 2024 同月为基数，'
     '跨月比较会混进 2024 年的季节性，指数的 m/m 不可当趋势读。'),
    ('⚠️ <b>2024 年的 ADV 是反算值</b>：官方给绝对值，但每份 xlsx 只含当年与上年两年。'
     '2024 年的月度 ADV 由 2025 年同月值与官方「\'25 v. \'24 % Change」反算得到 —— '
     '这是对披露数据的算术推导，不是估计，但精度受官方那个百分比的四舍五入限制。'
     'Exhibit 2 里这些月份画成斜纹柱。'),
    ('⚠️ <b>口径断点 2025-12</b>：从 2025 年 12 月起，ADV 的定义剔除 event contracts，'
     '且<b>不追溯重述</b>更早的月份。Exhibit 2 用红色虚线画在该月柱的左缘（语义是'
     '「从这一期起与左侧不可比」），Exhibit 5 的 2025Q4 那根柱本身就跨了新旧两套口径。'),
    ('<b>序列起点 2024-01</b>：更早年份的 xlsx 在 CDN 上已不可访问，'
     '所以本页没有疫情前的基准，也做不出真正意义上的长历史图与 3 年以上的分位。'),
    ('<b>Exhibit 5 的季度值是月度 ADV 的简单平均</b>，不是合计 —— ADV 已是日均口径，'
     '相加会得到一个没有单位含义的数。右轴 y/y 用 4 个季度前作分母，前 4 个季度留空；'
     '未满季时引擎会强制作废该季 y/y（拿 2 个月比上年完整 3 个月必然砸出假坑）。'),
    ('<b>汇总表的比率行用 pp / bp</b>：两条 y/y 本身就是比率，它们的变化只能用百分点差表示'
     '（|差| &lt; 1 用 bp），写成「百分比的百分比变化」会得到一个没人能解释的数。'
     '3Y %ile = 当月读数在近 36 个月里高于百分之多少的观测；两条 y/y 与指数序列只有 '
     '2025-01 以来的 18 个观测，分位只能当粗略刻度。'),
    ('<b>与 PDF 版的差异</b>：PDF 里 Exhibit 2/3 的柱图右轴有一条金色 y/y 折线，'
     '网页 <code>gs_bar</code> 没有对位物（见 CONTRACT §3 的 kind 映射表），'
     '改为「Prior 12mo Avg.」虚线 + 左上角 y/y 气泡；两者的数值口径一致。'
     '其余的顺序、编号、标题、图注、断点、窗口长度与 PDF 逐条一致。'),
    ('<b>核对表保持官方原始单位</b>：ADV 为 mn 张/日、两条 y/y 为百分比，均未换算；'
     '指数那一列是本页推导值，已在表头标注，拿它去核对官方文件会对不上。'),
]

adv_c, advy_c, biy_c, bidx_c = ADV[at(CUR)], ADVY[at(CUR)], BIY[at(CUR)], BIDX[at(CUR)]
headline = (f'SPDJI ADV {adv_c:,.2f} mn 张/日（{advy_c:+.1f}% y/y，公司披露）'
            f' · Ratings billed issuance {biy_c:+.0f}% y/y'
            f' · issuance 指数 {bidx_c:,.1f}（2024 同月 = 100，推导值）'
            f' · 序列 {MONTHS[0]} 起共 {len(MONTHS)} 个月')

payload = {
    'ticker': 'spgi',
    'tracker': 'SPGI Monthly Metrics Tracker',
    'title': f'S&P Global (SPGI)：月度指标跟踪 — {LY} 年 {LM} 月',
    'data_through': LATEST,
    'through_label': f'{LY} 年 {CN_MON[LM - 1]}',
    'subtitle': (f'数据源：S&P Global 官网 IR 月度指标 xlsx（S&P Global Ratings + '
                 f'S&P Dow Jones Indices 两个 sheet）· 覆盖 {MONTHS[0]} 至 {LATEST}'
                 f'（{len(MONTHS)} 个月）· 版式沿用 Goldman Sachs GIR monthly-metrics note'
                 f'，仅图无观点'),
    'headline': headline,
    'hub_line': (f'ADV {adv_c:.1f}mn/日（{advy_c:+.0f}% y/y）· '
                 f'billed issuance {biy_c:+.0f}% y/y'),
    'source': SRC,
    'xlabels': [mlab(m) for m in tm],
    'xlabels_long': [mlab(m) for m in MONTHS],
    'summary': summary,
    'exhibits': EXHIBITS,
    'table': table,
    'notes': NOTES,
    'footer': ('数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
               '仅供个人研究，不构成投资建议 · '
               'Billed issuance 指数与 2024 年 ADV 为推导值，已在对应图注标注'),
}


def main():
    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(OUT, payload, 'spgi')
    print(f'spgi: 数据截至 {LATEST}，Exhibit 1 汇总表 + '
          f'{len(EXHIBITS)} 张图 + Exhibit {table["n"]} 核对表 → '
          f'{os.path.relpath(OUT, ROOT)} ({os.path.getsize(OUT) / 1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
