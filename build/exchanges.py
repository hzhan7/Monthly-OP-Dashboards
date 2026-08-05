# -*- coding: utf-8 -*-
"""交易所组横截面（CME / Cboe / HKEX）—— 网页看板数据生成器，写出 data/exchanges.js。

原 deck：build/build_group_exchanges.py（matplotlib → PDF）。图序、标题文案、窗口、
口径提醒逐条移植；数值全部在本文件算好，页面（assets/page.js + charts.js）只画不算。

这张页只回答单份报告答不了的一个问题：**谁在跑赢**。所以它与 12 张单公司页有两条
本质不同的规矩，都照搬原 deck：

1. **单位不可加总。** 三家的「成交量」压根不是同一个东西 —— CME / Cboe 是合约张数，
   HKEX 是成交金额（HK$）。把它们加起来或按水平值排名都是错的口径，所以本页一律用
   **指数化**（各自在基期归 100）与**同比**做比较，绝不做绝对量的横向加总。
   汇总表里三家的水平值分行列出、各带各的单位，只为让人核对，不为让人相加。

2. **发布门槛 = 成员的共同最新月，不是各家自己的最新月。**
   三家的披露节奏不同（CME 次月第 1-2 个工作日、Cboe 第 3 个工作日、HKEX 上旬），
   任一时点上快的那家已经多出一个月。若各画各的最新月，读者会拿 CME 的 7 月去比
   Cboe 的 6 月，看到的「谁跑赢」有一整个月是口径造的。
   所以全页统一截到 **min(各家最新月)**，并在抬头、页脚、口径说明三处注明
   **哪家是短板、以及跑在前面的那家自己更新到了哪个月** —— 不写清楚，读者会默认
   整页都是最新的。

3. **算不出共同最新月就不写半张页。** 有成员还没建好（CSV 缺失 / 关键列没有任何有效值 /
   共同历史太短），打印说明并**以退出码 0 正常结束**：monthly_run.py 每次例行跑都会调
   build_cross()，成员齐了之后自然会把这一页补上。这里若抛异常，日志上会天天多一条
   假 FAIL；若硬写一张缺员的页，那才是真错误。

数据源（只读 series/*.csv，不读 build/data/）：
  series/cme.csv    CME Group 月度成交量
  series/cboe.csv   Cboe 月度成交量与 RPC
  series/hkex.csv   HKEX Monthly Market Highlights

用法: python3 build/exchanges.py     （可重复跑，除首行日期外逐字节相同）
"""
import datetime
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
OUT = os.path.join(ROOT, 'data', 'exchanges.js')

TICKER = 'exchanges'
SRC = ('Source: company monthly volume reports (CME, Cboe, HKEX); '
       'format after Goldman Sachs GIR')

# 成员固定配色：一家一色，全页所有图一致 —— 横截面页读者是在几张图之间来回比
# 「谁是谁」，颜色一旦按图重排，跨图对照就全废了。
# RED 不做数据色（它在这套语言里是断点与截轴离群值的专用色），故第三家用 GOLD。
CME_C, CBOE_C, HKEX_C = 'NAVY', 'MBLUE', 'GOLD'

# 门槛所依据的「头条成交量序列」：一家一条，就是首页与汇总表最上面那三行。
# 门槛只看它们 —— 其余列（未平仓、衍生品张数、品种占比）迟发或补发都不该拖住整页。
HEAD = [
    ('cme',  'CME',  'cme.csv',  'adv_total_kcontracts',      'k contracts/day'),
    ('cboe', 'Cboe', 'cboe.csv', 'adv_us_options_kcontracts', 'k contracts/day'),
    ('hkex', 'HKEX', 'hkex.csv', 'adt_hkdbn',                 'HK$bn/day'),
]

WIN_LINE = 25    # 曲线类近期图：照搬原 deck 的 win=25
HEAT_YEARS = 8   # 热力矩阵：照搬原 deck 的 n_years=8
TBL_MONTHS = 13  # 末尾核对表：契约 §5.4 的 13 个月
MIN_COMMON = 24  # 共同历史短于这么多个月就不发（y/y + 25 个月曲线都画不出来）
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# ────────────────────────────── 通用零件 ──────────────────────────────
def mlab(p):
    """与 gsx.mlab 一致：Period('2026-06') → 'Jun-26'。"""
    return f'{MONTHS[p.month - 1]}-{p.year % 100:02d}'


def zh(p):
    return f'{p.year} 年 {p.month} 月'


def num(v, dec=0):
    if v is None or not np.isfinite(v):
        return '—'
    return f'{v:,.{dec}f}'


def _z(v, dec):
    """把 -0.0 这类「四舍五入后其实是零」的值归零，否则会印出 '-0.0pp'。"""
    v = round(float(v), dec)
    return 0.0 if v == 0 else v


def pct(v, dec=1):
    """带符号的百分比变化。正负号交给 f-string 的 + 标志，不写死字面量。"""
    if v is None or not np.isfinite(v):
        return '—'
    return f'{_z(v, dec):+,.{dec}f}%'


def pp(v, dec=1):
    """百分点差 —— 比率类指标（占比、同比读数）的差异一律用 pp，不用百分比的百分比。"""
    if v is None or not np.isfinite(v):
        return '—'
    return f'{_z(v, dec):+.{dec}f}pp'


def L(a):
    """序列 → JSON 安全的 float 列表（NaN → None，线在缺口处断开而不是直连）。"""
    return [None if v is None or not np.isfinite(float(v)) else round(float(v), 6) for v in a]


def skip(msg):
    """成员没齐 —— 打印原因，退出码 0。见模块 docstring 第 3 条。"""
    print(f'{TICKER}: 跳过，未达发布门槛 —— {msg}')
    print('横截面页只在成员齐了之后生成；monthly_run 下次例行跑会自动重试。')
    sys.exit(0)


# ────────────────────────────── 1. 读数据 ──────────────────────────────
def read_csv(name):
    """series/<name> → 以连续月度 PeriodIndex 索引的 DataFrame（全列转数值）。

    reindex 成连续月：原始文件若中间缺月，pct_change(12) 会按**位置**移 12 行，
    算出来的「同比」其实跨了 13 个月而完全看不出来。
    """
    p = os.path.join(SERIES, name)
    if not os.path.exists(p):
        return None
    d = pd.read_csv(p)
    if 'month' not in d.columns:
        raise SystemExit(f'series/{name} 缺 month 列')
    d['month'] = pd.PeriodIndex(d['month'], freq='M')
    d = d.set_index('month').sort_index()
    d = d.apply(pd.to_numeric, errors='coerce')
    return d.reindex(pd.period_range(d.index[0], d.index[-1], freq='M'))


RAW = {key: read_csv(csv) for key, _, csv, _, _ in HEAD}

# ── 发布门槛：三条头条序列各自的最新有效月，取其 min ──
missing, latest_each = [], {}
for key, disp, csv, col, _unit in HEAD:
    d = RAW[key]
    if d is None:
        missing.append(f'{disp}（缺 series/{csv}）')
        continue
    if col not in d.columns:
        missing.append(f'{disp}（series/{csv} 缺列 {col}）')
        continue
    s = d[col].dropna()
    if s.empty:
        missing.append(f'{disp}（{col} 没有任何有效值）')
        continue
    latest_each[key] = s.index[-1]

if missing:
    skip('成员未就绪：' + '；'.join(missing))

LATEST = min(latest_each.values())
# 共同起点 = 三家都开始披露的那个月（HKEX 自 2019-01 起，是最晚的一家）
START = max(RAW[k][c].dropna().index[0] for k, _, _, c, _ in HEAD)
if START >= LATEST or (LATEST - START).n + 1 < MIN_COMMON:
    skip(f'共同历史只有 {max(0, (LATEST - START).n + 1)} 个月（{mlab(START)} – {mlab(LATEST)}），'
         f'不足 {MIN_COMMON} 个月，y/y 与 25 个月曲线都画不出来')

IDX = pd.period_range(START, LATEST, freq='M')
LAG = [disp for key, disp, _, _, _ in HEAD if latest_each[key] == LATEST]
AHEAD = [(disp, latest_each[key]) for key, disp, _, _, _ in HEAD if latest_each[key] > LATEST]


def col_of(key, col, scale=1.0):
    """取某家某列，截到共同窗口。"""
    d = RAW[key]
    if col not in d.columns:
        raise SystemExit(f'series/{key}.csv 缺列 {col}')
    return (d[col] * scale).reindex(IDX)


def yoy_of(key, col):
    """同比：先在**该家自己的完整历史**上算，再截到共同窗口。

    先截窗口再算同比，共同窗口头 12 个月的 y/y 会全成空 —— 那不是数据缺口，
    是算法把已有的历史扔了。
    """
    d = RAW[key]
    return (d[col].pct_change(12) * 100).reindex(IDX)


df = pd.DataFrame({
    'cme_adv': col_of('cme', 'adv_total_kcontracts'),
    'cboe_adv': col_of('cboe', 'adv_us_options_kcontracts'),
    'hkex_adt': col_of('hkex', 'adt_hkdbn'),
    'cme_oi': col_of('cme', 'oi_total_contracts', 1 / 1e6),
    'hkex_deriv': col_of('hkex', 'derivatives_adv_contracts', 1 / 1000.0),
}, index=IDX)
df['cme_rates_share'] = col_of('cme', 'adv_rates_kcontracts') / df['cme_adv'] * 100
df['cboe_index_share'] = col_of('cboe', 'adv_index_options_kcontracts') / df['cboe_adv'] * 100
df['cme_adv_yoy'] = yoy_of('cme', 'adv_total_kcontracts')
df['cboe_adv_yoy'] = yoy_of('cboe', 'adv_us_options_kcontracts')
df['hkex_adt_yoy'] = yoy_of('hkex', 'adt_hkdbn')

# 失败要响：共同窗口内头条序列有洞，说明源数据坏了，不是「成员没齐」——
# 这种情况必须抛出去让 monthly_run 记 FAIL，绝不静默画一条带洞的线。
for c in ('cme_adv', 'cboe_adv', 'hkex_adt'):
    holes = [str(p) for p in IDX if not np.isfinite(df[c][p])]
    if holes:
        raise SystemExit(f'{c} 在共同窗口 {mlab(START)}–{mlab(LATEST)} 内缺值：{holes}')

CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12
W25 = IDX[-WIN_LINE:]
XL25 = [mlab(p) for p in W25]
XL_LONG = [mlab(p) for p in IDX]


def rebase(col, base=None):
    """归一化到基期 = 100。单位不可比的序列只能这么放在一张图上。"""
    s = df[col]
    b = float(s[base or START])
    if not np.isfinite(b) or b == 0:
        raise SystemExit(f'{col} 在基期 {base or START} 无有效值，无法指数化')
    return s / b * 100


def win(col, n=WIN_LINE):
    return df[col].iloc[-n:].values


# ────────────────────────────── 2. Exhibit 1：汇总表 ──────────────────────────────
# (kind, 标签, 列, 小数位, 模式)
#   num    水平值，m/m 与 y/y 用百分比变化
#   share  占比（已是 %），差异用 pp
#   growth 同比读数（已是 %，带符号），差异用 pp
SUM_ROWS = [
    ('group', 'Volume — each in its own unit, not additive', None, None, None),
    ('row', 'CME total ADV (k contracts/day)', 'cme_adv', 0, 'num'),
    ('row', 'Cboe U.S. options ADV (k contracts/day)', 'cboe_adv', 0, 'num'),
    ('row', 'HKEX cash ADT (HK$bn/day)', 'hkex_adt', 0, 'num'),
    ('group', 'Growth (% y/y)', None, None, None),
    ('row', 'CME total ADV', 'cme_adv_yoy', 1, 'growth'),
    ('row', 'Cboe U.S. options ADV', 'cboe_adv_yoy', 1, 'growth'),
    ('row', 'HKEX cash ADT', 'hkex_adt_yoy', 1, 'growth'),
    ('group', 'Mix and open interest', None, None, None),
    ('row', 'CME interest-rate share of ADV (%)', 'cme_rates_share', 1, 'share'),
    ('row', 'Cboe index-option share of U.S. options (%)', 'cboe_index_share', 1, 'share'),
    ('row', 'CME month-end open interest (mn contracts)', 'cme_oi', 1, 'num'),
    ('row', 'HKEX derivatives ADV (k contracts/day)', 'hkex_deriv', 0, 'num'),
]


def pctile36(s):
    """近 36 个月分位。近乎单调的序列（逐月不降占比 ≥ 90%）留空 —— 分位恒为 100 是噪音。"""
    h = s.dropna().iloc[-36:].values
    if len(h) < 8 or not np.isfinite(h[-1]):
        return None
    d = np.diff(h)
    if len(d) and float((d >= 0).sum()) / len(d) >= 0.90:
        return None
    return float((h < h[-1]).sum()) / max(1, len(h) - 1) * 100


def lvl(v, dec, mode):
    if v is None or not np.isfinite(v):
        return '—'
    if mode == 'growth':
        return f'{_z(v, dec):+,.{dec}f}%'
    if mode == 'share':
        return f'{v:,.{dec}f}%'
    return f'{v:,.{dec}f}'


def cls_of(v):
    if v is None or not np.isfinite(v):
        return ''
    return 'pos' if v > 0 else ('neg' if v < 0 else '')


def summary():
    rows = []
    for kind, label, col, dec, mode in SUM_ROWS:
        if kind == 'group':
            rows.append({'kind': 'group', 'label': label})
            continue
        s = df[col]
        c, p1, p12 = float(s[CUR]), float(s[PRV]), float(s[YAG])
        if mode == 'num':
            mm = (c / p1 - 1) * 100 if np.isfinite(p1) and p1 else np.nan
            yy = (c / p12 - 1) * 100 if np.isfinite(p12) and p12 else np.nan
            dm, dy = pct(mm), pct(yy)
        else:                                   # 比率类：差异一律 pp（契约 §2）
            mm = c - p1 if np.isfinite(c) and np.isfinite(p1) else np.nan
            yy = c - p12 if np.isfinite(c) and np.isfinite(p12) else np.nan
            dm, dy = pp(mm), pp(yy)
        cells = [{'v': lvl(c, dec, mode)}, {'v': lvl(p1, dec, mode)}, {'v': lvl(p12, dec, mode)},
                 {'v': dm, 'cls': cls_of(mm)}, {'v': dy, 'cls': cls_of(yy)}]
        q = pctile36(s)
        cells.append({'v': ''} if q is None else
                     {'v': f'{q:.0f}', 'cls': 'hi' if q >= 66 else ('lo' if q <= 33 else '')})
        rows.append({'label': label, 'cells': cells})
    return {
        'title': f'Exchange group — {mlab(CUR)}（共同最新月）',
        'heads': [f'本月 {mlab(CUR)}', f'上月 {mlab(PRV)}', f'去年同月 {mlab(YAG)}',
                  'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': rows,
        'note': ('三家的成交量单位互不相同（CME / Cboe 是合约张数、HKEX 是成交金额），'
                 '<b>水平值之间既不能相加也不能排名</b>；本表把它们分行列出只为逐条核对，'
                 '横向比较一律看下面各图的同比与指数化曲线。'
                 '占比与同比读数本身已是百分比，其变化用 pp；水平值的变化用百分比。'
                 '3Y %ile = 该读数在最近 36 个月里高于多少百分比的观测，近乎单调的序列留空。'),
    }


# ────────────────────────────── 3. Exhibit 2..9 ──────────────────────────────
ex = []

ex.append({
    'n': 2, 'kind': 'lines', 'x': 'long', 'full': True, 'height': 300,
    'fmt': 'f0', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'markers': False,
    'title': f'Volume growth since {mlab(START)}, rebased',
    'ylab': f'index, {mlab(START)} = 100',
    'series': [
        {'name': 'CME total ADV', 'color': CME_C, 'values': L(rebase('cme_adv').values)},
        {'name': 'Cboe U.S. options ADV', 'color': CBOE_C, 'values': L(rebase('cboe_adv').values)},
        {'name': 'HKEX cash ADT', 'color': HKEX_C, 'values': L(rebase('hkex_adt').values)},
    ],
    'src_extra': (f'Rebased to 100 at {mlab(START)}, the first month all three disclose. '
                  'Compares growth only — the three units are not comparable in levels'),
    'note': ('指数化是本页唯一能把三家画进一张图的办法：张数与金额没有公约单位，'
             '归一之后比较的是<b>各自相对自己基期的增长</b>，线的高低差就是累计增速差，'
             '与谁的绝对体量大无关。'),
})

ex.append({
    'n': 3, 'kind': 'lines_endlabels', 'fmt': 'f0', 'zero_line': True,
    'title': f'Volume growth, y/y — last {WIN_LINE} months',
    'ylab': '% y/y',
    'series': [
        {'name': 'CME', 'color': CME_C, 'values': L(win('cme_adv_yoy'))},
        {'name': 'Cboe', 'color': CBOE_C, 'values': L(win('cboe_adv_yoy'))},
        {'name': 'HKEX', 'color': HKEX_C, 'values': L(win('hkex_adt_yoy'))},
    ],
    'src_extra': 'Same-month-prior-year basis for each company, on its own unit',
    'note': ('同比把单位问题消掉了 —— 张数的同比与金额的同比都是纯数，可以直接比。'
             f'{mlab(CUR)}：CME {pct(df["cme_adv_yoy"][CUR])}、'
             f'Cboe {pct(df["cboe_adv_yoy"][CUR])}、HKEX {pct(df["hkex_adt_yoy"][CUR])}。'),
})

ex.append({
    'n': 4, 'kind': 'lines', 'x': 'long', 'full': True, 'height': 300,
    'fmt': 'f0', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'zero_line': True,
    'title': 'Volume growth, y/y — full common window',
    'ylab': '% y/y',
    'series': [
        {'name': 'CME', 'color': CME_C, 'values': L(df['cme_adv_yoy'].values)},
        {'name': 'Cboe', 'color': CBOE_C, 'values': L(df['cboe_adv_yoy'].values)},
        {'name': 'HKEX', 'color': HKEX_C, 'values': L(df['hkex_adt_yoy'].values)},
    ],
    'src_extra': ('Same three series over the whole common history; shows whether the current '
                  'ranking is a new development or the standing order'),
    'note': (f'HKEX 的现货 ADT 自 {mlab(START)} 起才有披露，其同比要到 '
             f'{mlab(START + 12)} 才成立，前 12 个月为空 —— 线在此处断开而不是连成直线。'),
})

ex.append({
    'n': 5, 'kind': 'lines_endlabels', 'fmt': 'f1',
    'title': 'Mix quality: high-fee share of volume',
    'ylab': '% of own volume',
    'series': [
        {'name': 'CME: rates share of ADV', 'color': CME_C,
         'values': L(win('cme_rates_share'))},
        {'name': 'Cboe: index-option share of U.S. options', 'color': CBOE_C,
         'values': L(win('cboe_index_share'))},
    ],
    'src_extra': ('Both are the highest-value product inside each franchise, so a rising share '
                  'lifts blended revenue per unit of volume'),
    'note': ('两条线各自是「本家最贵的品种占本家成交的比重」，分母不同，'
             '所以看的是<b>各自的走向</b>而不是两条线的高低。HKEX 未列 —— '
             '其现货成交额本身就是金额口径，没有对应的「品种占比」披露。'),
})

ex.append({
    'n': 6, 'kind': 'lines', 'x': 'long', 'full': True, 'height': 300,
    'fmt': 'f0', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90,
    'title': f'Derivatives franchises, rebased to {mlab(START)}',
    'ylab': f'index, {mlab(START)} = 100',
    'series': [
        {'name': 'CME month-end open interest', 'color': CME_C,
         'values': L(rebase('cme_oi').values)},
        {'name': 'Cboe U.S. options ADV', 'color': CBOE_C,
         'values': L(rebase('cboe_adv').values)},
        {'name': 'HKEX derivatives ADV', 'color': HKEX_C,
         'values': L(rebase('hkex_deriv').values)},
    ],
    'src_extra': ('Rebased to 100. CME open interest is a stock, the other two are flows — '
                  'read the slopes, not the crossings'),
    'note': ('<b>存量与流量混在一张图里，只能读斜率。</b>月末未平仓合约是期末快照（存量），'
             'ADV 是当月日均（流量）；两条线交叉不代表任何事件，只有各自的爬升速度可比。'),
})


def heat(n, col, title, src_extra, legend):
    """行=年、列=月的同比热力矩阵。年份从该序列自己的有效值取，全空的年不占一行。"""
    s = df[col].dropna()
    yrs = sorted({p.year for p in s.index})[-HEAT_YEARS:]
    M = [[None] * 12 for _ in yrs]
    for p, v in s.items():
        if p.year in yrs:
            M[yrs.index(p.year)][p.month - 1] = round(float(v), 6)
    return {'n': n, 'kind': 'heat_matrix', 'full': True, 'title': title, 'fmt': 'pct0',
            'rows': [str(y) for y in yrs], 'cols': MONTHS, 'matrix': M,
            'legend': legend, 'cell_h': 20, 'row_lab_w': 38, 'row_head': '年',
            'src_extra': src_extra}


ex.append(heat(7, 'cme_adv_yoy', 'CME total ADV y/y (%)',
               'Green = faster growth. Colour scale is per-matrix (5th–95th percentile of its own '
               'cells), so the three matrices below are not colour-comparable with each other',
               'CME total ADV y/y'))
ex.append(heat(8, 'cboe_adv_yoy', 'Cboe U.S. options ADV y/y (%)',
               'Green = faster growth', 'Cboe U.S. options ADV y/y'))
ex.append(heat(9, 'hkex_adt_yoy', 'HKEX cash ADT y/y (%)',
               f'Green = faster growth. HKEX cash ADT starts {mlab(START)}, so its first y/y is '
               f'{mlab(START + 12)}', 'HKEX cash ADT y/y'))

# ────────────────────────── 4. Exhibit 10：核对表（官方原始单位）──────────────────────────
TBL_COLS = [
    ('CME total ADV (k contracts)', 'cme_adv', 'cme', 'adv_total_kcontracts', 3),
    ('CME month-end OI (contracts)', 'cme_oi', 'cme', 'oi_total_contracts', 0),
    ('Cboe U.S. options ADV (k contracts)', 'cb_adv', 'cboe', 'adv_us_options_kcontracts', 3),
    ('Cboe index options ADV (k contracts)', 'cb_idx', 'cboe', 'adv_index_options_kcontracts', 3),
    ('HKEX cash ADT (HK$bn)', 'hk_adt', 'hkex', 'adt_hkdbn', 3),
    ('HKEX derivatives ADV (contracts)', 'hk_der', 'hkex', 'derivatives_adv_contracts', 0),
]
W13 = IDX[-TBL_MONTHS:]
table = {
    'n': 10,
    'title': f'近 {TBL_MONTHS} 个月三家原始指标核对表（各家官方原始单位，未换算、未指数化）',
    'idx': '月份',
    'cols': [[h, k] for h, k, _, _, _ in TBL_COLS],
    'rows': [dict({'xl': mlab(p)},
                  **{k: num(float(RAW[key][c].get(p, np.nan)), d)
                     for _, k, key, c, d in TBL_COLS})
             for p in W13],
}

# ────────────────────────────── 5. 口径与方法说明 ──────────────────────────────
_ahead_txt = ('；'.join(f'{d} 自身已更新至 {mlab(m)}' for d, m in AHEAD)
              if AHEAD else '本期三家的最新月恰好一致，无人跑在前面')

NOTES = [
    f'<b>发布门槛：共同最新月。</b>本页统一截到 <b>{mlab(LATEST)}</b>，'
    f'即三家中最慢的那家的最新月。本期短板是 <b>{"、".join(LAG)}</b>；{_ahead_txt}。'
    '门槛存在的理由：三家披露节奏不同（CME 次月第 1-2 个工作日、Cboe 第 3 个工作日、'
    'HKEX 上旬），若各画各的最新月，读者会拿一家的 7 月去比另一家的 6 月，'
    '看到的「谁跑赢」里有一整个月是口径造出来的。'
    '<b>跑在前面那家的最新一个月不在本页任何一张图、任何一行表里</b> —— 要看它，'
    '请去它自己的单公司页。',

    '<b>单位不可加总，这是本页最硬的一条口径。</b>CME 与 Cboe 的成交量是<b>合约张数</b>，'
    'HKEX 的现货 ADT 是<b>成交金额（HK$）</b>。三者没有公约单位，'
    '<b>既不能相加，也不能按水平值排名</b>（「谁的数大」只反映谁的计量单位小）。'
    '因此全页的横向比较只用两种口径：<b>同比</b>（纯数，可比）与'
    '<b>指数化</b>（各自基期归 100，比的是相对自己的增长）。'
    '汇总表与核对表里保留各家的水平值，只为逐条与官方披露核对。',

    f'<b>指数化的基期。</b>Exhibit 2 与 Exhibit 6 一律以 <b>{mlab(START)}</b> 为 100 —— '
    f'那是三家都开始披露的第一个月（HKEX 现货序列自 {mlab(START)} 起）。'
    '基期选择会改变线的相对高度：换一个基期，「谁跑赢」的结论就变成「自那个月以来谁跑赢」。'
    '本页只用这一个基期，且写在轴标题里，读的时候请把它当成结论的一部分。',

    f'<b>同比的算法。</b>各家的 y/y 在<b>该家自己的完整历史</b>上算（当月 ÷ 去年同月 − 1），'
    f'再截到共同窗口，所以 CME / Cboe 的同比从 {mlab(START)} 起就有值。'
    f'HKEX 现货 ADT 自 {mlab(START)} 才有披露，其第一个同比落在 {mlab(START + 12)}，'
    '在此之前 Exhibit 4 与 Exhibit 9 里是空的 —— 那是<b>没有数据</b>，不是零增长，'
    '所以线在那里断开而不是连成直线。',

    '<b>Mix quality（Exhibit 5）两条线的分母不同。</b>CME 那条是利率品种占其总 ADV 的比重，'
    'Cboe 那条是指数期权占其美股期权成交的比重 —— 各自是本家单位价值最高的品种，'
    '占比上升会抬高本家的混合费率。因为分母不同，'
    '<b>只能各读各的走向，两条线的高低本身没有意义</b>。'
    'HKEX 无对应列：其现货成交额本身就是金额口径，官方未按品种拆出可比的占比。',

    '<b>存量与流量不可混读（Exhibit 6）。</b>CME 的月末未平仓合约是期末快照（存量），'
    'Cboe 的美股期权 ADV 与 HKEX 的衍生品 ADV 是当月日均（流量）。'
    '三条线放在一张指数图里只为对比<b>爬升速度</b>；线的交叉不对应任何事件，别当成「超越」。',

    '<b>热力矩阵的色标是每张图各自算的。</b>每张矩阵取自己全部有效格的 5/95 分位作为端点色，'
    '所以 Exhibit 7/8/9 三张图的<b>颜色不能横向比</b>（同一个绿在三张图里代表的增速不同）。'
    '要跨家比同比，请回 Exhibit 3 与 Exhibit 4 的曲线。',

    '<b>没有口径断点。</b>本页三条头条序列在共同窗口内均无并购并表或口径重分类，'
    '故全页没有红色竖虚线断点，相邻期可直读。'
    '需要留意的是 Cboe 2017 年的数字是 Bats pro-forma combined —— 但那段早于本页共同起点 '
    f'{mlab(START)}，不进本页。日后若任一家出现口径变更，必须在这里登记并在对应图上画出 '
    'break，不能只靠图注文字提一句。',

    f'<b>核对表（Exhibit 10）用各家官方原始单位，不做任何换算</b>：'
    'CME ADV 为千张/日、未平仓为张；Cboe ADV 为千张/日；HKEX 现货 ADT 为 HK$bn/日、'
    f'衍生品 ADV 为张/日。表同样只到 {mlab(LATEST)}，与全页门槛一致 —— '
    '跑在前面那家已披露但未纳入的月份，不在这张表里。',

    '<b>与原 PDF 版（build/build_group_exchanges.py）的差异。</b>'
    '(a) 原 deck 的「全窗口同比」用三家索引的并集（自 CME 的 2008 起），'
    'Cboe / HKEX 在前十年是整段空白；本页改为共同窗口，'
    '因为横截面页上的一段「只有一条线」不承载任何横截面信息。'
    '(b) 网页引擎的数据色里 RED 是断点与截轴离群值的专用色，'
    '故 HKEX 由原 deck 的 MBLUE 序位改用 GOLD，三家全页同色不换。'
    '(c) 其余图序、编号、标题文案、窗口长度（曲线 25 个月、热力 8 年）与原 deck 一致。',
]

# ────────────────────────────── 6. 抬头与 payload ──────────────────────────────
_idx_now = {k: float(rebase(k)[CUR]) for k in ('cme_adv', 'cboe_adv', 'hkex_adt')}
_yoy_now = {'CME': float(df['cme_adv_yoy'][CUR]),
            'Cboe': float(df['cboe_adv_yoy'][CUR]),
            'HKEX': float(df['hkex_adt_yoy'][CUR])}
_rank = sorted(_yoy_now.items(), key=lambda kv: -kv[1])
_lead_idx = max(zip(['CME', 'Cboe', 'HKEX'],
                    [_idx_now['cme_adv'], _idx_now['cboe_adv'], _idx_now['hkex_adt']]),
                key=lambda kv: kv[1])
_lag_txt = '、'.join(f'{d}（{mlab(latest_each[k])}）'
                     for k, d, _, _, _ in HEAD if latest_each[k] == LATEST)
_all_txt = ' · '.join(f'{d} 更新至 {mlab(latest_each[k])}' for k, d, _, _, _ in HEAD)

payload = {
    'ticker': TICKER,
    'tracker': 'Exchange Group Cross-Section — CME / Cboe / HKEX',
    'title': f'交易所组横截面（CME / Cboe / HKEX）：谁在跑赢 — {zh(LATEST)}',
    'data_through': str(LATEST),
    'through_label': f'{zh(LATEST)}（共同最新月）',
    'subtitle': (f'数据源：三家官方月度成交量披露 · 共同窗口 {mlab(START)} – {mlab(LATEST)}'
                 f'（{len(IDX)} 个月）· 发布门槛取成员的共同最新月，'
                 f'短板 {"、".join(LAG)} · 单位不可加总，一律用同比与指数化比较 · '
                 '版式仿 Goldman Sachs GIR · 仅图，无评论'),
    'headline': (f'y/y 排序：'
                 + '、'.join(f'{k} {pct(v)}' for k, v in _rank)
                 + f' · 自 {mlab(START)} 累计指数领先者 {_lead_idx[0]}（{_lead_idx[1]:,.0f}，'
                   f'基期 = 100）· CME 利率品种占 ADV {df["cme_rates_share"][CUR]:.0f}%、'
                   f'Cboe 指数期权占美股期权 {df["cboe_index_share"][CUR]:.0f}%'),
    'hub_line': (f'共同最新月 {mlab(LATEST)}（短板 {"、".join(LAG)}）；'
                 f'y/y 领先 {_rank[0][0]} {pct(_rank[0][1])}'),
    'source': SRC,
    'xlabels': XL25,
    'xlabels_long': XL_LONG,
    'summary': summary(),
    'exhibits': ex,
    'table': table,
    'notes': NOTES,
    'footer': (f'交易所组横截面 · CME / Cboe / HKEX · '
               f'<b>发布门槛：共同最新月 {mlab(LATEST)}</b>，本期短板 {_lag_txt} —— '
               f'本页所有图表一律截到此月，'
               + (f'跑在前面的 {"、".join(f"{d}（已更新至 {mlab(m)}）" for d, m in AHEAD)} '
                  f'的最新月份未纳入本页，请看其单公司页。'
                  if AHEAD else '本期三家最新月一致。')
               + f'各家最新披露：{_all_txt} · '
                 '三家成交量单位不可相加，本页只做同比与指数化比较 · '
                 'charts only, no commentary · personal research use'),
}


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        # 构建日期只写首行注释，不进 payload —— 进了 payload，monthly_run 的
        # 「data 有没有实质变化」检查（忽略首行的正文比较）就永久失效。
        f.write(f'// 由 build/{TICKER}.py 生成于 {datetime.date.today().isoformat()}，请勿手改\n')
        f.write('window.DASH = ')
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')
    print(f'共同最新月 {LATEST} | 各家: '
          + ', '.join(f'{d}={latest_each[k]}' for k, d, _, _, _ in HEAD))
    print(f'短板 {"、".join(LAG)} | 共同窗口 {START} → {LATEST}（{len(IDX)} 个月）')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张）+ '
          f'Exhibit {table["n"]} 核对表')
    print(f'写出 {OUT}（{os.path.getsize(OUT) / 1024:.1f} KB）')
    print(payload['headline'])


if __name__ == '__main__':
    main()
