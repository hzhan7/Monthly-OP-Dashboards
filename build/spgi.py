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
   1. Exhibit 2 / 3 走通栏（25 根柱塞进半栏时每柱数值标签会互相压住）；
      热力图在 PDF 里是通栏，网页上留在半栏 —— 通栏卡片会被渲染器统一提到汇总表
      下方，Exhibit 7 若通栏就会跑到 Exhibit 2 前面，编号顺序比宽度更重要。
   2. Exhibit 5 因引擎强制「两轴零点同高」，左轴被右轴的负同比带到 0 以下几格
      （deck 的 gsx.qtr_bar 是硬写 ylim(0, max*1.32)）。ADV 恒为正，那几格是空的，
      但这是网页引擎的规矩不是数据，写进 NOTES 里说明，不假装没发生。

Exhibit 2 / 3 的右轴曾经画成「Prior 12mo Avg.」水平虚线（引擎当时没有次轴 y/y）。
那条替代线有两处硬伤：Ex3 是对本页自己宣布「跨月不可比」的链式指数做 12 个月平均
（汇总表拒绝算的 m/m 与分位，正是同一种跨月运算）；Ex2 的 12 个月窗口六比六地
横跨 2025-12 口径断点，却被图注当成一个单一数字引用。引擎补上 gs_bar 的次轴
y/y 之后，两张图一律回到 deck 的 lvl_bar 原型：金色 y/y 折线，不画均线。
"""
import csv
import datetime
import importlib.util
import json
import os

import payload_guard
import pctile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES_DIR = os.path.join(ROOT, 'series')
SERIES = os.path.join(SERIES_DIR, 'spgi_clean.csv')
OUT = os.path.join(ROOT, 'data', 'spgi.js')


def _source_dates():
    """按路径加载仓库根的 source_dates.py（发布日台账）。
    `python3 build/spgi.py` 跑起来时 sys.path 上只有 build/，裸 import 必挂。"""
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SRC = 'Source: S&P Global monthly metrics xlsx; format after Goldman Sachs GIR'
DNOTE = ('2024 ADV values are back-calculated from the 2025 level and the officially '
         "disclosed 25 v. 24 % change")
INOTE = ('Billed issuance is disclosed as a y/y % only; this index chains those '
         'percentages (same month of 2024 = 100)')
EVENT = ('From Dec-2025 the ADV definition excludes event contracts, with no restatement '
         'of earlier months')

# ADV 的口径断点。凡是把 ADV（或它的同比）画成时间轴的图都要带上这条红虚线；
# billed issuance 不受影响，Ex3 / Ex7 不画。
BRK_M = '2025-12'
BRK_Y = int(BRK_M[:4])
BRK_LABEL = 'ex-event contracts'

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


def nz(v, dec):
    """把「四舍五入之后是 0、但原值是负数」的情况归零，避免印出 -0 / -0.0。
    今天本页没有这样的读数（BIY 是整数百分比、ADVY 一位小数都够大），但公司下个月
    披露一个 -0.04% 就会印出「-0.0%」—— 那读起来像「精确的负数」，其实是 0。"""
    if v is None:
        return None
    return 0.0 if abs(round(v, dec)) < 10 ** -dec / 2 else v


def num(v, dec, pct=False):
    """已格式化的单元格字符串（页面不做计算，格式化是口径的一部分）。"""
    if v is None:
        return '—'
    return f'{nz(v, dec):,.{dec}f}' + ('%' if pct else '')


def tail(arr, n):
    return arr[-n:]


# prior12()（Prior 12mo Avg. 的均值）已随 Exhibit 2/3 的均线一起删除：
# 本页两张 gs_bar 现在画的是 deck 原型的次轴 y/y，均线不再有任何调用方。
# 留一个没人调的函数在这里，下一个人会以为「本页还允许画均线」。


def yoy_of(vals):
    """水平值序列的逐月同比（%），与 gsx.lvl_bar 的次轴口径一致：
    滞后 12 期、基数为 0 或两期异号时放弃该点（同比在那里没有意义）。
    序列本身必须逐月连续 —— load() 已经强制过。"""
    out = [None] * len(vals)
    for i in range(12, len(vals)):
        a, b = vals[i], vals[i - 12]
        if a is None or b is None or b == 0 or a * b < 0:
            continue
        out[i] = (a / b - 1) * 100
    return out


def brk_idx(months):
    """ADV 口径断点在该窗口里的 x 索引；滚出窗口返回 None，payload 写 null、
    引擎整段不画（图注文案也要跟着省掉，否则就成了「说画了其实没画」）。

    一律现算、且不用会抛异常的 .index()：窗口每月往前滚，硬编码索引下个月就指错，
    而断点滚出窗口那天 list.index() 会直接 raise —— 那等于让本页永久停更
    （build/lpla.py 现在就是这个毛病）。"""
    ms = list(months)
    return ms.index(BRK_M) if BRK_M in ms else None


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
    # 分位一律走 build/pctile.py（全站唯一实现）：它挡的是「这一列在近两年回放里几乎
    # 恒定在端点、对这一行没有区分度」。本页额外留空的那一行是另一回事 ——
    # 指数的**每期基数都不同**，连排序都无从解释，那是页面自己的口径判断（xmonth）。
    ptxt, pcls = pctile.cell(arr, ic) if xmonth else ('', '')
    pcell = {'v': ptxt, 'cls': pcls} if ptxt else {'v': ''}
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
m2 = tail(MONTHS, W2)
adv_w = tail(ADV, W2)
xl2 = [mlab(m) for m in m2]
brk_i = brk_idx(m2)
adv_yoy_lvl = (ADV[at(CUR)] / ADV[at(YAG)] - 1) * 100
# 次轴同比与 deck 的 gsx.lvl_bar 同源：拿水平值自己算，不是抄披露值那一列。
# 两者本来就应当相等（2024 年的 ADV 正是用披露的同比反算出来的），最新月
# +30.0% vs 披露 +30.0% 即互为校验；不等就说明 CSV 内部矛盾，宁可让它露出来。
advy_w = tail(yoy_of(ADV), W2)
# 断点右侧的同比是「新口径的当月 ÷ 旧口径的去年同月」——公司不重述，只能这么算，
# 但必须在图注里点名，不能让读者把它当成同口径的动能。
n_mixed = sum(1 for i, m in enumerate(m2)
              if advy_w[i] is not None and mkey(m) >= mkey(BRK_M))
# 「同比从哪个月起才有」「斜纹柱是哪几年」都现算：ADV 序列每月往前长，官方补发历史
# 文件时 adv_derived 也会变，这两句写死就会在某个月变成假话。
advy_from = next((mlab(m) for i, m in enumerate(m2) if advy_w[i] is not None), None)
mark_i = [i for i, m in enumerate(m2) if DERIVED[at(m)] == 1]
mark_y = sorted({m2[i][:4] for i in mark_i})

ex2 = {
    'n': 2, 'kind': 'gs_bar', 'full': True, 'fmt': 'f1', 'xlabels': xl2,
    'title': 'SPDJI average daily volume of ETDs',
    'ylab': 'mn contracts / day', 'ylab2': '% y/y',
    'legend': 'Monthly ADV',
    'values': [r6(v) for v in adv_w],
    'break_at': brk_i, 'break_label': BRK_LABEL,
    'bar_marks': mark_i,
    'mark_note': '该月 ADV 由 2025 年值与官方 25 v. 24 % change 反算，非直接披露值',
    'note': (f'柱为公司披露的 SPDJI 交易所交易衍生品日均成交量；金线（右轴）是同月对'
             f'去年同月的水平值同比，最新月 {adv_yoy_lvl:+.1f}% 与公司披露的 '
             f'{ADVY[at(CUR)]:+.1f}% 互为校验。'
             + (f'窗口最左端没有上年对位月，同比从 {advy_from} 起才有。'
                if advy_from else '窗口内还没有上年对位月，暂时只有柱、没有同比线。')
             + (f'红色竖虚线 = 口径断点（{mlab(BRK_M)}）：该月起 ADV 剔除 event '
                f'contracts 且不重述历史，线左右两侧不可直读；断点右侧的 {n_mixed} 个'
                '同比读数是「新口径的当月 ÷ 旧口径的去年同月」，跨口径比值，'
                '比柱本身还要打折扣。' if brk_i is not None else '')
             + (f'斜纹柱为 {"、".join(mark_y)} 年的反算值（见图下 Source 行）。'
                if mark_y else '')),
    'src_extra': EVENT + '. ' + DNOTE + '.',
}
# 窗口内一个同比点都没有时不挂 yoy：给引擎一条全 null 的次轴序列，等于让它为一条
# 画不出来的线开出一整套右轴刻度（同 Exhibit 3 的写法）。
if advy_from:
    ex2['yoy'] = {'name': 'y/y（RHS）', 'color': 'GOLD', 'yfmt': 'pct0',
                  'values': [r6(v) for v in advy_w]}

# ────────────────────────── Exhibit 3：Billed issuance index ──────────────
idx_i = [i for i, v in enumerate(BIDX) if v is not None]
i0 = idx_i[0]
idx_months = MONTHS[i0:]
idx_vals = BIDX[i0:]
W3 = min(25, len(idx_vals))                    # deck 的 win=25，序列只有 18 个月
idx_w = tail(idx_vals, W3)
xl3 = [mlab(m) for m in tail(idx_months, W3)]
idx_yoy = (BIDX[at(CUR)] / BIDX[at(YAG)] - 1) * 100
# 指数的同比 = 官方披露的 billed issuance 同比：2024 年同月那个（从未披露的）基数
# 在分子分母上精确对消。这是本图**唯一**可跨月读的量 —— 水平值不是。
idxy_w = tail(yoy_of(idx_vals), W3)
idxy_at = [i for i, v in enumerate(idxy_w) if v is not None]
idxy_n = len(idxy_at)
# 指数序列只会越来越长，同比只会越来越全；但窗口内一个点都没有时（序列 < 13 个月）
# 不能让 [0] 抛异常 —— 那是又一个「某个月起本页永久停更」。此时整条线不画、文案改口。
idxy_from = mlab(tail(idx_months, W3)[idxy_at[0]]) if idxy_at else None

ex3 = {
    'n': 3, 'kind': 'gs_bar', 'full': True, 'fmt': 'f0', 'xlabels': xl3,
    'title': 'Ratings billed issuance index',
    'ylab': 'index, 2024 same month = 100', 'ylab2': '% y/y',
    'legend': 'Monthly index',
    'values': [r6(v) for v in idx_w],
    'note': ('<b>指数不是公司披露值</b>：官方每月只给 billed issuance 的同比百分比，'
             '本图把这些百分比链式接到「2024 年同月 = 100」上。因此每根柱各自以自己的'
             '2024 同月为基数，<b>跨月读高低会混进 2024 年的季节性</b>，柱与柱之间'
             '不能相减、也不能取平均（汇总表的 m/m 与分位为同一原因留空）。'
             + (f'干净的只有金线（右轴）那条同比：2024 同月基数在分子分母上精确对消，'
                f'{idx_yoy:+.0f}% 与官方披露的 {BIY[at(CUR)]:+.0f}% 一致。'
                f'指数从 {mlab(idx_months[0])} 起才有，故同比从 {idxy_from} 起'
                f'才存在（窗口内 {idxy_n} 个点）。' if idxy_from else
                f'指数从 {mlab(idx_months[0])} 起才有，窗口内还没有满 12 个月的对位'
                '基数，故本图暂时只有柱、没有同比线。')),
    'src_extra': INOTE + (f'; the y/y line starts {idxy_from}.' if idxy_from else '.'),
}
if idxy_from:
    ex3['yoy'] = {'name': 'y/y（RHS）', 'color': 'GOLD', 'yfmt': 'pct0',
                  'values': [r6(v) for v in idxy_w]}

# ────────────────────────── Exhibit 4：两条披露 y/y ──────────────────────────
W4 = 18                                        # 照搬 deck 的 win=18
m4 = tail(MONTHS, W4)
biy4 = [r6(BIY[at(m)]) for m in m4]
advy4 = [r6(ADVY[at(m)]) for m in m4]
if any(v is None for v in biy4 + advy4):
    raise SystemExit('Exhibit 4 的窗口内存在缺失月，lines_endlabels 不接受缺口')
# 本图是全页唯一把 ADV 同比画成时间序列的图，断点必须也画在这里：
# 窗口内 Dec-25 及其后的每个 ADV 同比读数都是「剔除 event 的当月 ÷ 含 event 的去年同月」。
b4 = brk_idx(m4)
n4_mixed = len(m4) - b4 if b4 is not None else 0

ex4 = {
    'n': 4, 'kind': 'lines_endlabels', 'fmt': 'f0', 'xlabels': [mlab(m) for m in m4],
    'title': 'The two disclosed y/y series side by side',
    'ylab': '% y/y',
    'series': [
        {'name': 'Ratings billed issuance', 'color': 'NAVY', 'values': biy4},
        {'name': 'SPDJI ADV', 'color': 'MBLUE', 'values': advy4},
    ],
    'break_at': b4, 'break_label': BRK_LABEL,
    'note': ('两条线都是公司**直接披露**的同比百分比，不是本页推导值 —— 也是 S&amp;P Global '
             '每月唯一公布的两个数。两者口径完全不同（评级业务的计费发行量 vs 指数业务的'
             '衍生品日均成交），同向或背离都不构成因果，只是把「这个月两块业务各自的动能」'
             f'放在一起看。窗口 {mlab(m4[0])}–{mlab(m4[-1])}。'
             + (f'红色竖虚线 = ADV 的口径断点（{mlab(BRK_M)}）：'
                f'蓝线（SPDJI ADV）在虚线右侧的 {n4_mixed} 个读数是「剔除 event contracts '
                '的当月 ÷ 含 event contracts 的去年同月」，跨口径比值 —— 公司不重述历史，'
                '只能这么算，但不能与虚线左侧的读数放在一条趋势里读。'
                '深蓝线（billed issuance）不受这次口径变更影响。'
                if b4 is not None else '')),
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
    'ylab': 'mn contracts / day', 'ylab2': '% y/y',
    'legend': 'Quarterly ADV (avg of monthly)',
    'values': [r6(v) for v in qv],
    'partial_months': qn_last, 'qtr_months': 3,
    # 与 Ex2/Ex3/Ex4 同色（deck 的 y/y 一律是 GOLD）：全页三种 y/y 线一个颜色，
    # 读者不用每张图重认一次。yfmt 用 pct1 而不是 pct0 —— 末点读数就画在右轴刻度
    # 旁边，两边都印「15%」时看起来像同一个数字被打印了两遍。
    'line': {'name': 'y/y（RHS）', 'color': 'GOLD', 'values': [r6(v) for v in qy],
             'yfmt': 'pct1'},
    'note': ('季度值是该季各月 ADV 的**简单平均**（日均口径不能相加），'
             '右轴 y/y 用 4 个季度前作分母，故前 4 个季度留空。'
             '2024 各季用的是反算出来的月度 ADV。'
             + ('2025Q4 起口径变更只影响该季的 12 月一个月，红色竖虚线标在该季左缘 —— '
                '季度柱本身跨了新旧两套口径（季内两个月旧、一个月新），是本图最脏的一根，'
                '它右侧各季的 y/y 也都是跨口径比值。' if q_brk else '')
             + (f'最新一季只含 {qn_last} 个月，柱为浅蓝、右轴 y/y 已作废。'
                if qn_last < 3 else '')
             + '左轴刻度延到 0 以下几格是双轴零点对齐的副作用（右轴同比有负值），'
             'ADV 本身恒为正，零线下方是空的。'),
    'src_extra': DNOTE + '.',
}
if q_brk:
    ex5['break_at'] = q_brk[0]
    # 标签竖排、从绘图区顶端往下走：写成「ex-event contracts（季内一个月）」时
    # 那串字会一路穿到画布中段，正好压在 y/y 折线上（人眼审查实测）。
    # 括号里那半句移进图注，图上只留与 Ex2 同一个标签。
    ex5['break_label'] = BRK_LABEL

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

# 「哪几年整条是反算值」不许写死 2024：adv_derived 是 CSV 里的列，官方哪天补发历史
# xlsx，这一列就会变，图注不能还挂着一个手写的年份。
DERIVED_Y = [y for y in years
             if all(DERIVED[at(m)] == 1 for m in MONTHS if int(m[:4]) == y)]
# 每条年线属于哪套口径：断点年自身混口径，之前/之后各成一组。
CAL_GRP = []
if BRK_Y in years:
    CAL_GRP.append(f'{BRK_Y} <b>线内混口径</b>'
                   f'（1–{int(BRK_M[5:]) - 1} 月旧、{int(BRK_M[5:])} 月新）')
for _lab, _sel in (('旧口径', [y for y in years if y < BRK_Y]),
                   ('新口径', [y for y in years if y > BRK_Y])):
    if _sel:
        CAL_GRP.append('、'.join(str(y) for y in _sel) + ' ' + _lab)

ex6 = {
    'n': 6, 'kind': 'year_lines', 'fmt': 'f1', 'label_fmt': 'f1', 'xlabels': MON,
    'title': 'SPDJI ADV path by year',
    'ylab': 'mn contracts / day',
    'series': yser,
    'highlight': len(yser) - 1,
    'note': ('画的是**水平值**不是累计（日均量累计没有意义），红线为当年。'
             + (f'{"、".join(str(y) for y in DERIVED_Y)} 年整条线是反算值；'
                if DERIVED_Y else '')
             + f'{LY} 年只到 {MON[LM - 1]}，其后留空而不是画成 0。'
             + (f'口径变更在 {mlab(BRK_M)}，而本图 x 轴是 1–12 月不是时间轴，'
                '画不出断点竖线（只有真时间轴的图能画，见下方口径说明第 5 条），'
                '只能在此说明这几条线各自属于哪套口径：' + '；'.join(CAL_GRP) +
                '。跨口径的线不要拿同一个月份的点直接比高低。'
                if len(CAL_GRP) > 1 else '')),
    'src_extra': DNOTE + '.',
}

# ────────────────────────── Exhibit 7：billed issuance y/y 热力矩阵 ──────────
hy = sorted({int(m[:4]) for m in MONTHS})[-NY:]
BIY_FROM = next(m for m in MONTHS if BIY[at(m)] is not None)
matrix = []
rowlab = []
for y in hy:
    row = [None] * 12
    for m in MONTHS:
        if int(m[:4]) == y and BIY[at(m)] is not None:
            row[int(m[5:]) - 1] = r6(BIY[at(m)])
    matrix.append(row)
    # 整行无数据时把原因写进行标签本身。图注里已经解释过，但读者的第一眼落在矩阵上：
    # 一条完整的灰色空行看起来就是「数据没加载出来」，而不是「这一年本来就没有 y/y」。
    rowlab.append(f'{y}（无 y/y）' if all(v is None for v in row) else str(y))
BLANK_Y = [str(y) for y, row in zip(hy, matrix) if all(v is None for v in row)]

ex7 = {
    'n': 7, 'kind': 'heat_matrix', 'fmt': 'f0',
    'title': 'Ratings billed issuance y/y (%)',
    'rows': rowlab, 'cols': MON, 'matrix': matrix,
    'legend': 'Billed issuance y/y', 'row_head': '年', 'cell_h': 22,
    'row_lab_w': 62,                       # 行标签加了「（无 y/y）」，32px 装不下
    'note': ('色标取全部有限值的 5/95 分位，绿 = 发行量增速更快。'
             + (f'{"、".join(BLANK_Y)} 一整行是灰的（行标已标「无 y/y」），不是没加载出来：'
                '那一年公司只披露了绝对水平的对照基数本身，没有可用的 y/y 读数'
                f'（第一个 y/y 读数是 {mlab(BIY_FROM)}）。留着这一行是为了让'
                '三年的月份列对齐，也让「哪一年没有数」一眼可见。' if BLANK_Y else '')
             + '同一格的高低是相对**去年同月**，不是相对上月，'
             '所以一行里连着两个大正数并不等于绝对水平在连涨。'),
    'src_extra': ('Green = faster issuance growth'
                  + (f'; {"/".join(BLANK_Y)} is blank because only y/y is disclosed.'
                     if BLANK_Y else '.')),
}

EXHIBITS = [ex2, ex3, ex4, ex5, ex6, ex7]

# 图注里「哪几张画了断点线」不许手写：断点滚出某张图的窗口时（或某张图换了窗口长度），
# 手写的编号就变成一句假话。这里从真正写进 payload 的 break_at 反查。
BRK_DRAWN = [e['n'] for e in EXHIBITS if e.get('break_at') is not None]
BRK_TXT = ('Exhibit ' + '、'.join(str(n) for n in BRK_DRAWN) + ' 上画了红色竖虚线'
           '（语义是「从这一期起与左侧不可比」）。' if BRK_DRAWN else
           '断点已滚出所有图的窗口，本页当前没有任何一张图画竖虚线。')
# 「受影响的不只是柱本身」这段同样逐条挂在真实状态上：断点滚出某张图的窗口之后，
# 再说「Exhibit X 断点右侧的读数」就成了指着一条不存在的线说话。
_more = []
_yoy_ex = [n for n in BRK_DRAWN if n in (2, 4)]
if _yoy_ex:
    _more.append('Exhibit ' + '、'.join(str(n) for n in _yoy_ex) +
                 ' 里断点右侧的每一个 ADV 同比读数，都是「新口径的当月 ÷ 旧口径的去年同月」')
if q_brk:
    _more.append(f'Exhibit 5 的 {qk[q_brk[0]][0]}Q{qk[q_brk[0]][1]} 那根柱'
                 '季内两个月旧、一个月新，是全页最脏的一根')
if BRK_Y in years:
    _more.append(f'Exhibit 6 的 x 轴是 1–12 月、画不了竖线，改在图注里说明 {BRK_Y} '
                 '那条年线自身就是混口径')
BRK_MORE = ('受影响的不只是柱本身：' + '；'.join(_more) + '。') if _more else ''

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
    (f'⚠️ <b>口径断点 {BRK_M}</b>：从 {BRK_Y} 年 {int(BRK_M[5:])} 月起，ADV 的定义剔除 '
     'event contracts，且<b>不追溯重述</b>更早的月份。' + BRK_TXT + BRK_MORE +
     'Ratings billed issuance（Exhibit 3 / 7）与这次变更无关，不画断点。'),
    ('<b>序列起点 2024-01</b>：更早年份的 xlsx 在 CDN 上已不可访问，'
     '所以本页没有疫情前的基准，也做不出真正意义上的长历史图与 3 年以上的分位。'),
    ('<b>Exhibit 5 的季度值是月度 ADV 的简单平均</b>，不是合计 —— ADV 已是日均口径，'
     '相加会得到一个没有单位含义的数。右轴 y/y 用 4 个季度前作分母，前 4 个季度留空；'
     '未满季时引擎会强制作废该季 y/y（拿 2 个月比上年完整 3 个月必然砸出假坑）。'),
    ('<b>汇总表的比率行用 pp / bp</b>：两条 y/y 本身就是比率，它们的变化只能用百分点差表示'
     '（|差| &lt; 1 用 bp），写成「百分比的百分比变化」会得到一个没人能解释的数。'
     '3Y %ile = 当月读数在近 36 个月里高于百分之多少的观测，由全站共用的 '
     '<code>build/pctile.py</code> 统一给出（同一条序列在两页得到相反判定，'
     '正是因为从前各页各写各的）：它会把「近两年回放里几乎恒定钉在 0 或 100」的行整列留空。'
     '本页三行都不是死列，所以都出了数；但两条 y/y 与指数序列只有 2025-01 以来的 '
     '18 个观测垫底，分位只能当粗略刻度。'),
    ('<b>与 PDF 版的差异</b>：Exhibit 2/3 已回到 PDF 的原型 —— 浅蓝柱 + 右轴金色 y/y 折线，'
     '<b>不画 12 个月均线</b>（deck 的 <code>gsx.lvl_bar</code> 原话：均线只是把柱子再平滑'
     '一遍、不带新信息）。此前网页版用「Prior 12mo Avg.」虚线顶替，那条线在 Exhibit 3 上'
     '等于对本页自己宣布「跨月不可比」的链式指数取 12 个月平均，在 Exhibit 2 上又六比六地'
     '横跨了 2025-12 的口径断点却被当成一个单一数字引用 —— 两处都已随虚线一起删掉。'
     '其余的顺序、编号、标题、图注、断点、窗口长度与 PDF 逐条一致。'),
    ('<b>双轴图的左轴会被拉到 0 以下</b>（Exhibit 2 / 5）：本引擎强制「左右两轴的零点画在'
     '同一条水平线上」，右轴同比含负值时，左轴就得跟着往下扩出一段空白 —— PDF 版的 '
     'matplotlib 不对齐零点，所以 deck 上左轴是从 0 起的。ADV 恒为正，零线下方那几格'
     '一定是空的，不是数据；代价过大（浪费四成以上画布）时引擎会改为不对齐并在图上标红字。'),
    ('<b>核对表保持官方原始单位</b>：ADV 为 mn 张/日、两条 y/y 为百分比，均未换算；'
     '指数那一列是本页推导值，已在表头标注，拿它去核对官方文件会对不上。'),
]

adv_c, advy_c, biy_c, bidx_c = ADV[at(CUR)], ADVY[at(CUR)], BIY[at(CUR)], BIDX[at(CUR)]
# 抬头那行印的第一个数就是 ADV 同比，而当分子已在新口径、分母还在旧口径时，
# 这个数本身是跨口径比值 —— 只印数不印这句，就是把最显眼的位置留给一个报喜的数字。
adv_mixed = mkey(CUR) >= mkey(BRK_M) > mkey(YAG)
headline = (f'SPDJI ADV {adv_c:,.2f} mn 张/日（{advy_c:+.1f}% y/y，公司披露'
            + ('；分子已剔除 event contracts、分母未重述，同比跨口径' if adv_mixed else '')
            + f'） · Ratings billed issuance {biy_c:+.0f}% y/y'
            f' · issuance 指数 {bidx_c:,.1f}（2024 同月 = 100，推导值，跨月不可比）'
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

# 抬头那行「官方发布于」——取台账里 data_through 这个月的发布日，源头是 xlsx 页脚
# 自述的 "Published on M/D/YYYY"（fetch/spgi.py 摄入时记的）。查不到就**整个字段省掉**：
# 渲染端判的是字段在不在（assets/page.js 的 `D.source_date ? …`），写 None 会印出 "None"。
# 按月份查而不是取台账里最新的一条：cache/ 里可能躺着比 data_through 更新的一期文件，
# 那会把新一期的发布日安到旧月份的数据上。
_pub = _source_dates().lookup(SERIES_DIR, 'spgi', LATEST)
if _pub:
    payload['source_date'] = _pub


def main():
    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(OUT, payload, 'spgi')
    print(f'spgi: 数据截至 {LATEST}，Exhibit 1 汇总表 + '
          f'{len(EXHIBITS)} 张图 + Exhibit {table["n"]} 核对表 → '
          f'{os.path.relpath(OUT, ROOT)} ({os.path.getsize(OUT) / 1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
