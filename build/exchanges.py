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
import os
import sys

import numpy as np
import pandas as pd

import brief as B    # 页顶 ~300 字数据总结的规则库（只算事实，句子在本文件拼）
from monthlab import mlab   # x 轴月份标签 Jul-26 的唯一实现
import payload_guard
import pctile        # 3Y %ile 的唯一实现，全站共用（各写各的正是同一序列两页判定相反的原因）
import repo          # 仓库定位 + 发布日台账入口

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
# 开了 end_label 的长历史线图必须给到这个高度，**不能改小**。
# charts.js 的末点标签避让（spreadY）有一条兜底：整列标签的最上面一个若落在绘图区
# 顶缘 7px 以内，就认为「上下都顶满」，改成从顶缘顺排 —— 那会把三个末点标签
# 收成一摞贴在右上角，其中最低那条（本页 Exhibit 2 的 CME 172）被摆到 350 的高度上，
# 比它自己的线高出一大截，读者会当成另一条线的读数（比不标还糟）。
# 触发条件与数据无关，是纯几何：末点恰好是全图最大值时，标签落在 M.t + ph×0.0455 − 7，
# 而门限是 M.t + 7 —— 即 ph > 308 才安全。lines 图的 ph = height + XB − M.t − XB
# = height − 14（x 标签 90° 时 XB=48、无截轴时 M.t=14），故 height 需 ≥ 325。
# 取 360 留出余量；本页 Exhibit 2 与 8 的末点正好都是各自的全图最大值，是最坏情况。
LINE_H_ENDLABEL = 360
TBL_MONTHS = 13  # 末尾核对表：契约 §5.4 的 13 个月
MIN_COMMON = 24  # 共同历史短于这么多个月就不发（y/y + 25 个月曲线都画不出来）
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# ────────────────────────────── 通用零件 ──────────────────────────────


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
    """百分点差 —— 比率类指标（占比、同比读数）的差异一律用 pp/bp，不用百分比的百分比。

    契约 §2 的全站硬规矩：`abs(v) < 1` 时改用 bp（1pp = 100bp），否则用 pp。
    本页原来一律写 pp，于是 HKEX 现货 ADT 同比行的 m/m 印成「-0.6pp」，
    而同一轮渲染下 lpla 的 +34bp、axp 的 -10bp、schw 的 +98bp 都按规矩切了 bp ——
    数值本身没错（-0.6pp ≡ -60bp），错的是同一站里同类量出现两套单位写法。
    """
    if v is None or not np.isfinite(v):
        return '—'
    if abs(_z(v, dec)) < 1:
        return f'{_z(v * 100, 0):+,.0f}bp'
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


# ── 同比图「拆图还是截轴」的量化依据 ──
# 图注里的每一个数字都从这里算，不写死：写死的话下个月序列一变，图注就成了假话
# （本仓已经有过「图注说画了断点线、图上其实没有」的先例，同一类错不重犯）。
def _rng(*arrs):
    v = [float(x) for a in arrs for x in a if x is not None and np.isfinite(float(x))]
    return (min(v), max(v)) if v else (0.0, 0.0)


def _over(arr, hi):
    return sum(1 for x in arr if x is not None and np.isfinite(float(x)) and float(x) > hi)


CC25_LO, CC25_HI = _rng(win('cme_adv_yoy'), win('cboe_adv_yoy'))
HK25_LO, HK25_HI = _rng(win('hkex_adt_yoy'))
CCF_LO, CCF_HI = _rng(df['cme_adv_yoy'].values, df['cboe_adv_yoy'].values)
HKF_LO, HKF_HI = _rng(df['hkex_adt_yoy'].values)
# 「若强行同轴、把轴截到 CME/Cboe 的量程」会有多少个 HKEX 点越界 —— 截轴方案的代价
CLIP25 = _over(win('hkex_adt_yoy'), CC25_HI)
CLIPF = _over(df['hkex_adt_yoy'].values, CCF_HI)
HKF_N = int(np.isfinite(df['hkex_adt_yoy'].values.astype(float)).sum())
SPAN25 = (HK25_HI - HK25_LO) / max(1e-9, CC25_HI - CC25_LO)
SPANF = (HKF_HI - HKF_LO) / max(1e-9, CCF_HI - CCF_LO)


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


def ser_of(s):
    """pandas Series → pctile.py 吃的「按月升序、缺失为 None」的 float 列表。

    NaN 不能直接喂进去：pctile 里 `v is not None` 会把 NaN 当有效样本收进 hist，
    而 NaN 的比较恒为 False，分位会被悄悄压低。
    """
    return [None if v is None or not np.isfinite(float(v)) else float(v) for v in s.values]


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
    # 3Y %ile 一律走 build/pctile.py：判据（回放近 24 个月，≥70% 的月份钉在极值就留空）
    # 是**口径**，口径只能有一处定义。本页原来那份「逐月差 ≥0 占比 ≥90% 就留空」的本地
    # 实现与其余 13 个生成器各写各的，正是同一条序列在两页判定相反的根因。
    rows, blank_why = [], []
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
        else:                                   # 比率类：差异一律 pp/bp（契约 §2）
            mm = c - p1 if np.isfinite(c) and np.isfinite(p1) else np.nan
            yy = c - p12 if np.isfinite(c) and np.isfinite(p12) else np.nan
            dm, dy = pp(mm), pp(yy)
        cells = [{'v': lvl(c, dec, mode)}, {'v': lvl(p1, dec, mode)}, {'v': lvl(p12, dec, mode)},
                 {'v': dm, 'cls': cls_of(mm)}, {'v': dy, 'cls': cls_of(yy)}]
        ser = ser_of(s)                          # 按月升序的整条共同窗口序列，CUR 是最后一格
        txt_, cls_ = pctile.cell(ser)
        cells.append({'v': txt_, 'cls': cls_} if txt_ else {'v': ''})
        if not txt_:
            blank_why.append((label, pctile.why_blank(ser)))
        rows.append({'label': label, 'cells': cells})
    blank_txt = ('本轮留空：' + '；'.join(f'{lab}（{why}）' for lab, why in blank_why) + '。'
                 ) if blank_why else '本轮各行均未触发留空，分位照算。'
    return {
        'title': f'Exchange group — {mlab(CUR)}（共同最新月）',
        'heads': [f'本月 {mlab(CUR)}', f'上月 {mlab(PRV)}', f'去年同月 {mlab(YAG)}',
                  'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': rows,
        'note': ('三家的成交量单位互不相同（CME / Cboe 是合约张数、HKEX 是成交金额），'
                 '<b>水平值之间既不能相加也不能排名</b>；本表把它们分行列出只为逐条核对，'
                 '横向比较一律看下面各图的同比与指数化曲线。'
                 '占比与同比读数本身已是百分比，其变化用 pp/bp（绝对值不足 1pp 时写 bp）；'
                 '水平值的变化用百分比。'
                 '3Y %ile = 该读数在最近 36 个月里高于多少百分比的观测，'
                 '判据与留空规则由全站唯一实现 <code>build/pctile.py</code> 给出：'
                 '回放最近 24 个月，若 ≥70% 的月份分位都钉在 100 或 0，'
                 '说明这一列对该行没有区分度，留空。' + blank_txt),
    }


# ────────────────────────────── 3. Exhibit 2..11 ──────────────────────────────
# 同比图为什么是**四张而不是两张**（原 deck 与本页此前都是两张、三条线同轴）：
#   HKEX 的现货 ADT 同比与 CME / Cboe 的张数同比虽然都是「%」，量程却差一个数量级
#   （SPANF 实测约 2.7 倍，港股成交自 2024-09 起是一整段行情，不是一两个离群月）。
#   三条线同轴的结果是 CME 与 Cboe 被压进 0 附近一条窄带里互相纠缠，而汇总表告诉你
#   「CME vs Cboe 的同比差」正是本月的关键差距 —— 在图上读不出来，这张图就白画了。
#   两条路都算过（数字见 CLIP25 / CLIPF，图注里也印出来）：①截轴（ycap + 红色空心圈）
#   —— 把轴截到 CME/Cboe 的量程，25 个月窗口里要截掉 CLIP25 个点、全窗口 CLIPF 个，
#   红圈比线还多，那不叫「离群值处理」，那是把一条真实序列画成异常；
#   ②拆图 —— 各用各的轴，谁也不压谁。选②，并在两张图的图注里互相写出对方的当期读数，
#   保证「谁在跑赢」仍然是一眼可得的（横向比较的正本仍是 Exhibit 1 与 Exhibit 2）。
# 版面：拆出来的两张按**半栏成对**排（Exhibit 3|4 一行、5|6 各自通栏），
#   页面网格是两列，半栏卡片必须成对出现，否则右半边留一大块空白（读者会以为图没加载）。
ex = []

ex.append({
    'n': 2, 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H_ENDLABEL,
    'fmt': 'f0', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'markers': False,
    # end_label ← 原 deck 的 gsx.indexed_lines 对每条线的末点都 annotate 了数值
    # （gsx.py:951-956，粗体、同色）。网页版此前一个都没画，于是抬头里那句
    # 「累计指数领先者 HKEX（361）」在图上找不到落点，只能靠轴刻度目测。
    'end_label': True, 'label_fmt': 'f0',
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
             '与谁的绝对体量大无关。'
             f'末点已标数值（{mlab(START)} = 100）。'),
})

_cur_yoy = (f'CME {pct(df["cme_adv_yoy"][CUR])}、Cboe {pct(df["cboe_adv_yoy"][CUR])}、'
            f'HKEX {pct(df["hkex_adt_yoy"][CUR])}')

ex.append({
    'n': 3, 'kind': 'lines_endlabels', 'fmt': 'f1', 'zero_line': True,
    'title': f'Volume growth, y/y — CME vs Cboe, last {WIN_LINE} months',
    'ylab': '% y/y',
    'series': [
        {'name': 'CME total ADV', 'color': CME_C, 'values': L(win('cme_adv_yoy'))},
        {'name': 'Cboe U.S. options ADV', 'color': CBOE_C, 'values': L(win('cboe_adv_yoy'))},
    ],
    'src_extra': ('Same-month-prior-year basis for each company, on its own unit. '
                  f'HKEX is on its own axis in the next exhibit — its range over these '
                  f'{WIN_LINE} months is about {SPAN25:.0f}x wider'),
    'note': ('同比把单位问题消掉了 —— 张数的同比与金额的同比都是纯数，可以直接比；'
             '这张图只放量级相近的 CME 与 Cboe，好让两者的差距占满纵轴。'
             f'{mlab(CUR)}：{_cur_yoy}（HKEX 见 Exhibit 4，<b>纵轴不同</b>，'
             '两张图的线高不可直接对望）。'
             '端点标签保留一位小数 —— 取整会把相差不到 1pp 的两个读数印成同一个数字，'
             '而这几张图的题眼恰恰是谁跑赢。'),
})

ex.append({
    'n': 4, 'kind': 'lines_endlabels', 'fmt': 'f1', 'zero_line': True,
    'title': f'HKEX cash ADT, y/y — last {WIN_LINE} months (own axis)',
    'ylab': '% y/y',
    'series': [
        {'name': 'HKEX cash ADT', 'color': HKEX_C, 'values': L(win('hkex_adt_yoy'))},
    ],
    'src_extra': (f'Split out from the previous exhibit because its range over these '
                  f'{WIN_LINE} months is about {SPAN25:.0f}x wider; the axis is NOT shared '
                  f'with CME / Cboe'),
    'note': (f'<b>纵轴与 Exhibit 3 不同</b>（本图 {HK25_LO:+.0f}% ~ {HK25_HI:+.0f}%，'
             f'Exhibit 3 {CC25_LO:+.0f}% ~ {CC25_HI:+.0f}%），'
             '所以两张图之间只能比走向、不能比线的高低；要比读数请看数字：'
             f'{mlab(CUR)} {_cur_yoy}。'
             '港股成交额的同比是整段抬升而不是一两个离群月 —— 若强行与 Exhibit 3 同轴并'
             f'把轴截到 CME/Cboe 的量程，这 {WIN_LINE} 个月里会有 {CLIP25} 个点变成红色'
             '越界圈，那是把一条真实序列画成异常，所以本页选择拆图而不是截轴。'),
})

ex.append({
    'n': 5, 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H_ENDLABEL,
    'fmt': 'f1', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'zero_line': True,
    'end_label': True, 'label_fmt': 'f1',
    'title': 'Volume growth, y/y — CME vs Cboe, full common window',
    'ylab': '% y/y',
    'series': [
        {'name': 'CME total ADV', 'color': CME_C, 'values': L(df['cme_adv_yoy'].values)},
        {'name': 'Cboe U.S. options ADV', 'color': CBOE_C, 'values': L(df['cboe_adv_yoy'].values)},
    ],
    'src_extra': ('Both series over the whole common history; shows whether the current ranking '
                  'is a new development or the standing order'),
    'note': (f'两家的同比在同一量级上（共同窗口内 {CCF_LO:+.0f}% ~ {CCF_HI:+.0f}%），'
             '同轴可直读。HKEX 的同一口径见 Exhibit 6 —— 它的量程是这张图的 '
             f'{SPANF:.1f} 倍，同轴会把这两条线压成一条带。'),
})

ex.append({
    'n': 6, 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H_ENDLABEL,
    'fmt': 'f1', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'zero_line': True,
    'end_label': True, 'label_fmt': 'f1',
    'title': 'HKEX cash ADT, y/y — full common window (own axis)',
    'ylab': '% y/y',
    'series': [
        {'name': 'HKEX cash ADT', 'color': HKEX_C, 'values': L(df['hkex_adt_yoy'].values)},
    ],
    'src_extra': (f'Own axis: this series ranges {HKF_LO:+.0f}% to {HKF_HI:+.0f}% over the '
                  f'common window, about {SPANF:.1f}x the CME / Cboe range in the previous '
                  f'exhibit'),
    'note': (f'HKEX 的现货 ADT 自 {mlab(START)} 起才有披露，其第一个同比落在 '
             f'{mlab(START + 12)}，在那之前本图<b>没有线</b>（不是零增长，是没有数据；'
             '缺口一律留空、不连直线）。'
             '<b>纵轴与 Exhibit 5 不同</b>，两图之间只比走向不比高低。'),
})

ex.append({
    # 通栏：本页的半栏卡片必须成对出现（Exhibit 3|4 已配成一对），
    # 这张再走半栏就会单独占一行、右半边空一大块。
    'n': 7, 'kind': 'lines_endlabels', 'fmt': 'f1', 'full': True, 'height': 300,
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
    'n': 8, 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H_ENDLABEL,
    'fmt': 'f0', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90,
    'end_label': True, 'label_fmt': 'f0',
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
    """行=年、列=月的同比热力矩阵。年份从该序列自己的有效值取，全空的年不占一行。

    fmt 用 `pct0z` 而不是 `pct0`：格内是 0 位小数，−0.5% ~ 0 之间的格子在 pct0 下会印成
    「-0%」（Cboe 2024-03 实测 −0.35% → 「-0%」）。负零是纯格式化产物，夹在一片两位整数
    里特别扎眼，读者会停下来判断它是不是缺失值。pct0z 把 |v|<0.5 的格子归零印成「0%」；
    表格视图与 tooltip 走 PRECISE 映射自动升到 pct1，真值（−0.3%）一个也没丢。
    """
    s = df[col].dropna()
    yrs = sorted({p.year for p in s.index})[-HEAT_YEARS:]
    M = [[None] * 12 for _ in yrs]
    for p, v in s.items():
        if p.year in yrs:
            M[yrs.index(p.year)][p.month - 1] = round(float(v), 6)
    return {'n': n, 'kind': 'heat_matrix', 'full': True, 'title': title, 'fmt': 'pct0z',
            'rows': [str(y) for y in yrs], 'cols': MONTHS, 'matrix': M,
            'legend': legend, 'cell_h': 20, 'row_lab_w': 38, 'row_head': '年',
            'src_extra': src_extra}


ex.append(heat(9, 'cme_adv_yoy', 'CME total ADV y/y (%)',
               'Green = faster growth. Colour scale is per-matrix (5th–95th percentile of its own '
               'cells), so the three matrices below are not colour-comparable with each other',
               'CME total ADV y/y'))
ex.append(heat(10, 'cboe_adv_yoy', 'Cboe U.S. options ADV y/y (%)',
               'Green = faster growth', 'Cboe U.S. options ADV y/y'))
ex.append(heat(11, 'hkex_adt_yoy', 'HKEX cash ADT y/y (%)',
               f'Green = faster growth. HKEX cash ADT starts {mlab(START)}, so its first y/y is '
               f'{mlab(START + 12)} — {START.year} has no row at all rather than an empty one',
               'HKEX cash ADT y/y'))

# ────────────────────────── 4. Exhibit 12：核对表（官方原始单位）──────────────────────────
# 计数列一律显示成**张/日的整数**，不再显示成「千张 + 3 位小数」。
# 原来 CME 写「25,683.347」、Cboe 写「4,639.229」，而同一张表里 HKEX 衍生品写
# 「1,392,646」—— 三列都是合约张数却并排两套精度风格，且「25,683.347」第一眼极易被读成
# 「两千五百万点三四七」。series CSV 以千张存，这里乘 1000 还原回**各家新闻稿本身用的
# 张数口径**，属于回到官方原始单位，不是新增换算（契约 §4 要的正是官方原始单位）。
# HKEX 现货 ADT 保持 HK$bn + 3 位小数：它是金额不是计数，3 位小数就是百万港元精度。
TBL_COLS = [
    ('CME total ADV (contracts)', 'cme_adv', 'cme', 'adv_total_kcontracts', 1000.0, 0),
    ('CME month-end OI (contracts)', 'cme_oi', 'cme', 'oi_total_contracts', 1.0, 0),
    ('Cboe U.S. options ADV (contracts)', 'cb_adv', 'cboe', 'adv_us_options_kcontracts', 1000.0, 0),
    ('Cboe index options ADV (contracts)', 'cb_idx', 'cboe', 'adv_index_options_kcontracts', 1000.0, 0),
    ('HKEX cash ADT (HK$bn)', 'hk_adt', 'hkex', 'adt_hkdbn', 1.0, 3),
    ('HKEX derivatives ADV (contracts)', 'hk_der', 'hkex', 'derivatives_adv_contracts', 1.0, 0),
]
W13 = IDX[-TBL_MONTHS:]
table = {
    'n': 12,
    'title': f'近 {TBL_MONTHS} 个月三家原始指标核对表（各家官方原始单位，未指数化）',
    'idx': '月份',
    'cols': [[h, k] for h, k, _, _, _, _ in TBL_COLS],
    'rows': [dict({'xl': mlab(p)},
                  **{k: num(float(RAW[key][c].get(p, np.nan)) * sc, d)
                     for _, k, key, c, sc, d in TBL_COLS})
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

    f'<b>指数化的基期。</b>Exhibit 2 与 Exhibit 8 一律以 <b>{mlab(START)}</b> 为 100 —— '
    f'那是三家都开始披露的第一个月（HKEX 现货序列自 {mlab(START)} 起）。'
    '基期选择会改变线的相对高度：换一个基期，「谁跑赢」的结论就变成「自那个月以来谁跑赢」。'
    '本页只用这一个基期，且写在轴标题里，读的时候请把它当成结论的一部分。',

    f'<b>同比的算法。</b>各家的 y/y 在<b>该家自己的完整历史</b>上算（当月 ÷ 去年同月 − 1），'
    f'再截到共同窗口，所以 CME / Cboe 的同比从 {mlab(START)} 起就有值。'
    f'HKEX 现货 ADT 自 {mlab(START)} 才有披露，其第一个同比落在 {mlab(START + 12)}，'
    f'在此之前 Exhibit 6 里没有线 —— 那是<b>没有数据</b>，不是零增长，缺口一律留空、'
    f'不连直线；Exhibit 11 的热力矩阵同理，干脆不给 {START.year} 排一行 —— '
    '排了就是一整行灰格摆在矩阵顶上，第一眼像数据没加载出来。',

    '<b>同比图为什么拆成四张（Exhibit 3–6）。</b>三家的同比虽然都是纯数，量级却不在一个'
    f'数量级上：共同窗口内 CME 与 Cboe 合起来只在 {CCF_LO:+.0f}% ~ {CCF_HI:+.0f}% 之间，'
    f'而 HKEX 现货 ADT 在 {HKF_LO:+.0f}% ~ <b>{HKF_HI:+.0f}%</b>，量程是前者的 '
    f'{SPANF:.1f} 倍。三条线同轴时，CME 与 Cboe 被压进零线附近一条窄带里互相纠缠，'
    f'<b>而本月汇总表里「CME {pct(df["cme_adv_yoy"][CUR])} vs '
    f'Cboe {pct(df["cboe_adv_yoy"][CUR])}」正是最该看的差距</b> —— 读不出来这张图就白画了。'
    '截轴（ycap + 红色空心圈）在这里不成立：港股成交额是整段抬升而不是一两个离群月，'
    f'把轴截到 CME/Cboe 的量程会让近 {WIN_LINE} 个月里的 {CLIP25} 个点、'
    f'全窗口 {HKF_N} 个有效月里的 {CLIPF} 个点变成越界圈，那是把真实序列画成异常。'
    '所以改为按量级拆图：Exhibit 3 / 5 放 CME 与 Cboe（同轴可直读），'
    'Exhibit 4 / 6 给 HKEX 自己的纵轴。'
    '<b>代价是 Exhibit 3 与 4（5 与 6）的纵轴不同，两张图之间只能比走向、不能比线高。</b>'
    '要一眼比三家读数，看 Exhibit 1 的汇总表与 Exhibit 2 的指数化曲线，'
    '两张图的图注里也各写了三家的当期同比。',

    '<b>Mix quality（Exhibit 7）两条线的分母不同。</b>CME 那条是利率品种占其总 ADV 的比重，'
    'Cboe 那条是指数期权占其美股期权成交的比重 —— 各自是本家单位价值最高的品种，'
    '占比上升会抬高本家的混合费率。因为分母不同，'
    '<b>只能各读各的走向，两条线的高低本身没有意义</b>。'
    'HKEX 无对应列：其现货成交额本身就是金额口径，官方未按品种拆出可比的占比。',

    '<b>存量与流量不可混读（Exhibit 8）。</b>CME 的月末未平仓合约是期末快照（存量），'
    'Cboe 的美股期权 ADV 与 HKEX 的衍生品 ADV 是当月日均（流量）。'
    '三条线放在一张指数图里只为对比<b>爬升速度</b>；线的交叉不对应任何事件，别当成「超越」。',

    '<b>热力矩阵的色标是每张图各自算的。</b>每张矩阵取自己全部有效格的 5/95 分位作为端点色，'
    '所以 Exhibit 9/10/11 三张图的<b>颜色不能横向比</b>（同一个绿在三张图里代表的增速不同）。'
    '要跨家比同比，请回 Exhibit 3–6 的曲线。'
    '格内数值取 0 位小数，−0.5% ~ 0 之间的格子印成「0%」而不是「-0%」'
    '（负零是格式化产物，不是缺失值）；真值保留到一位小数，切「表格」视图或悬停即可看到。',

    '<b>没有口径断点，全页也确实一条断点线都没画。</b>本页三条头条序列在共同窗口内均无'
    '并购并表或口径重分类，故 payload 里没有任何 <code>break_at</code>，相邻期可直读 —— '
    '这一条与图上是对得上的，不存在「图注说画了断点、图上找不到」的情况。'
    '需要留意的是 Cboe 2017 年的数字是 Bats pro-forma combined —— 但那段早于本页共同起点 '
    f'{mlab(START)}，不进本页。日后若任一家出现口径变更，必须在这里登记并在对应图上画出 '
    'break，不能只靠图注文字提一句；断点随窗口滚出去时应当让它自然消失（连同这段文案），'
    '而不是让生成器报错停更。',

    f'<b>核对表（Exhibit 12）用各家官方披露的原始计量单位，不做口径换算</b>：'
    'CME 总 ADV 与 Cboe ADV 按<b>张/日</b>显示（series CSV 以千张存，表中乘 1000 还原成'
    '各家新闻稿本身的张数口径），CME 月末未平仓为张，HKEX 衍生品 ADV 为张/日；'
    'HKEX 现货 ADT 是金额不是计数，保持 HK$bn/日、3 位小数（即百万港元精度）。'
    f'表同样只到 {mlab(LATEST)}，与全页门槛一致 —— '
    '跑在前面那家已披露但未纳入的月份，不在这张表里。',

    '<b>与原 PDF 版（build/build_group_exchanges.py）的差异。</b>'
    '(a) 原 deck 的「全窗口同比」用三家索引的并集（自 CME 的 2008 起），'
    'Cboe / HKEX 在前十年是整段空白；本页改为共同窗口，'
    '因为横截面页上的一段「只有一条线」不承载任何横截面信息。'
    '(b) 网页引擎的数据色里 RED 是断点与截轴离群值的专用色，'
    '故 HKEX 由原 deck 的 MBLUE 序位改用 GOLD，三家全页同色不换。'
    '(c) <b>同比图由 deck 的 2 张（三条线同轴）拆成 4 张</b>（Exhibit 3–6，理由见上一条），'
    '因此本页编号自 Exhibit 5 起比 deck 各多 2：deck 的「Mix quality」= 本页 Exhibit 7、'
    '「Derivatives rebased」= Exhibit 8、三张热力矩阵 = Exhibit 9–11。'
    '(d) 指数化图（Exhibit 2 / 8）补上了 deck 有、网页版此前漏掉的<b>末点数值标注</b>'
    '（gsx.indexed_lines 对每条线的末点都标了数值）。'
    '(e) 其余图序、标题文案、窗口长度（曲线 25 个月、热力 8 年）与原 deck 一致。',
]

# ────────────────────────── 6. 页顶 brief（~300 字，怎么读本月读数）──────────────────────────
def compose_brief():
    """交易所组横截面页顶部的 ~300 字数据总结（payload 的 `brief` 字段）。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R3 日历护栏 / R4 单位恒等 /
    R5 标注 / R6 有效位），那边只算事实，句子在这里拼 —— 措辞是口径的一部分，属于本页自己。

    ═══ 本函数的第一条纪律：定性词必须由当场算出的量决定分支 ═══
    「只有 / 集中在 / 反而 / 全部 / 从高位回落 / 不是掉头」这类词一旦写死，而它旁边的
    数字是现算的，句子就会在某个月自己打自己。上一版 s3 写的是「跌只来自一个品种：
    CME 利率 ADV 环比{x}、非利率反而{y}」，把共同窗口里 89 个可重放月各截断一次重跑：
    88 个月的「只来自一个品种」在公司披露的六条品种线粒度上不成立、53 个月的「反而」
    其实利率与非利率同向、47 个月的「跌只来自」印在总量上涨的月份上。所以本函数里：
      · 方向词一律取自 `tot_d`／`be['mm']` 的符号（`d2`／`d3` 两个变量），且必须出现在
        句面上 —— 「最弱」不含方向，后半句的「从高位回落」就没有依托；
      · **动词也算方向词**：`sh >= 1` 那支原来固定写「单条抵掉净{d3}幅」，重放里 2026-05
        印出「单条抵掉净涨幅的 1.0 倍」——「抵掉」是冲销，在上涨月是反义词。改成
        跌用「抵掉」、涨用「顶起」，同样由 `tot_d` 的符号决定；
      · 计数类定性词一律走 `B.quant()`（≤1/3 才配「只有」，≥2/3 是「多达」）；**唯一的
        例外是 k == n**：`B.quant` 给「多达三家」，而分母也是三家，「三家多达三家」读着
        像数没算对，故 `cnt2` 在全中时改说「全部」—— 仍由 len 决定，不是写死的定性词；
      · 「集中在」只在单条变动 ≥ 净变动时才印，否则降级成「最大一块来自」，方向再反
        就换成「反在另一边」；
      · 缺值月用 `B.need()` 挡在拼句之前 —— 那一句不写，而不是整页构建失败。
    重放口径：本页 MIN_COMMON=24，共同历史不足 24 个月时 `skip()` 就退出了、根本不出
    payload，所以可重放的是 START+23 起的 67 个月（不是全部 90 个）。对现在这版：
    67 个月全部构建成功、无自相矛盾，去标签字数 270–317，恒为 4 句、<b> 2–3 处。

    ═══ 这一家（横截面页）独有，别家不能照抄 ═══
      · **主语是三家之间的相对位置，不是三段各说各的。**12 张单公司页的 brief 讲「这家
        本月怎么读」；本页唯一要回答的是「谁在跑赢」，所以四句话分别是：谁在纪录位而谁
        不在（跨家）、落后那家的变动是不是基数造的（跨家里唯一反向的那个）、它的变动落在
        哪个品种、以及换个分母看累计领先（并把两个占比的序数位置挂在同一句里）。
        四个层次对应样板 build/ibkr.py 的 规模 / 基数 / 口径背离 / 分母。
      · **R3（日历护栏）在本页不成立，而且是主动排除的。**CME 与 Cboe 披露的本来就是
        ADV、HKEX 披露的是 ADT，**三条头条列都已经日均化**；series/cme.csv 里确实还躺着
        一列 trading_days，但对已日均的列再除一次交易日会造出一个根本不存在的修正
        （brief.py 开头点名的第一个坑）。所以第二句反过来把这件事写出来：环比里没有
        交易日效应可扣，那个变动是真的。判据是「这一列是当月合计还是已经日均」，
        不是「有没有交易日列」。
      · **单位不可加总，所以 R1 的峰值扫描是本页唯一能做的横向排名。**三家的量分别是
        合约张数与港元金额，水平值既不能相加也不能排名（见 NOTES 第二条）；但「各自
        有没有站在自己历史的最高点」是纯序数判断，不吃单位，跨家可比。
      · **五条量指标里混着一条存量（CME 月末未平仓），故意留着不剔。**剔了会丢掉本页
        最值钱的那个背离。但落后的三条里有两条本身就是成交侧（CME ADV、HKEX 衍生品），
        所以句子只说「站上高点的全是成交侧、唯一的存量列不在其中」，不写成「落后的是
        存量」—— 后者用流量/存量解释不了另外两条。
      · **品种拆解按公司披露的粒度说话。**CME 披露六条品种线，所以「跌只来自一个品种」
        这种话必须在六条粒度上成立才能写；本月为负的其实有两条（利率 −27.7%、能源
        −10.5%），故改口径：报「单条变动 ÷ 总量净变动」的倍数（利率一条 Δ −5,216 千张，
        总量净 Δ 只有 −2,605 千张，即单条就抵掉净跌幅的两倍，其余四线合计 +2,892 还在
        往回补 —— 这是只看总量 m/m 绝对读不出来的那一层），同向条数交给 B.quant。
      · **两个占比只报各自的序数位置，不做费率推断。**本页 cme.csv 没有 RPC 列，
        费率方向要去 series/fee_rates.csv 查；而那里的实测是 CME 利率 RPC 为六条线里
        **最低**（2026-Q2 $0.480 < rpc_total $0.678），53 个季度 corr(利率占比, rpc_total)
        = −0.07 —— 上一版据 Exhibit 7 note 的前提写出的「混合费率方向相反」方向是反的。
        本函数不再碰费率，只留两个占比的序数与「分母不同、只能各读各的」这句限定。
        （Exhibit 7 的 note 那句前提另需一处修正，不在 brief 范围内。）
      · **T4 的两个主语必须同时出现、且必须点名，但只比排序、不做分解。**Exhibit 2 的
        末点指数是「当月 ÷ 基月」（两个单月），`regime_ratio` 是「首年年均 ÷ 近 13 个月
        均值」（两段期间均值）—— 不是一个东西，所以第四句把两个口径都点出名字，只断言
        「排序对不对得上」（`same_order` 当场验，两个降序名单逐位相等才敢写「同序」）。
        **上一版还把差额拆成「末点效应 vs 基月效应」并印出「差额的 66% 来自基月偏低」——
        那是二元贡献度分解，超出 brief 的分寸（brief.py::render 明文禁的那一类），已删。**
        样板 build/ibkr.py 的第四句只报「十个指标里哪个相对起点下行 + 起止两段均值」，
        本句照这个深度：报三家的期间均值倍数，不报差额从哪来。
      · **不复述抬头与 Exhibit 1 的水平值，但锚一个环比幅度是允许的。**利率占比的水平值
        与其 pp 变化、累计指数末点都已印在抬头里，这里一个都不再念；第二句保留 CME 的
        环比幅度，是因为「上月是第几高月」离开幅度就没有着落（样板同样在句中重念了
        净新增的 131.8k 与 -30.7%）。其余全是抬头没印过的数：上月的全样本名次、峰值年月、
        品种拆解与倍数、占比的序数位置、期间均值倍数。
    """
    i, n = len(IDX) - 1, len(IDX)
    if i < 1:
        return ''      # 只有一个月：环比、品种拆解、基数护栏全都无从谈起，整段不写
                       # （本页 MIN_COMMON=24，实际到不了这里；留着是为了重放时不炸）
    months = [str(p) for p in IDX]
    ym = lambda k: f'{k[2:4]}年{int(k[5:7])}月'          # '2019-05' → '19年5月'
    cme, cboe, hkex = df['cme_adv'].values, df['cboe_adv'].values, df['hkex_adt'].values

    # ── s1 / R1：跨家峰值扫描。单位不可加总，但「在不在各自的历史最高点」是序数判断，不吃单位。
    #    五条都是 ADV/ADT/期末快照（已日均或本就是水平值），argmax 不含日历噪音。
    OI = 'CME 未平仓'        # 五条里唯一的**存量**列，其余四条都是速率（ADV/ADT）
    SC = [('Cboe 期权', cboe), ('HKEX 现货', hkex), ('CME ADV', cme),
          (OI, df['cme_oi'].values), ('HKEX 衍生品', df['hkex_deriv'].values)]
    pk = B.peak_scan(months, SC, i)      # 实测五条全非单调，skip_monotonic 不会吞掉任何一条
    at, off = pk['at_peak'], pk['off_peak']
    m = len(at) + len(off)               # 本月有读数的条数，不写死 5（某条缺值时会少）
    # 命中数多时只报个数不列名 —— 列名会让这句随命中数膨胀，撞上 render 的字数上限
    at_txt = f'（{"、".join(at)}）' if 0 < len(at) <= 3 else ''
    # 「最陈旧的一条」= off_peak 里离本月最远的那个峰值，现算，不写死是哪条
    stale = max(off, key=lambda t: i - months.index(t[1])) if off else None
    seen = at + [nm for nm, _ in off]
    hit = ('无一站上最高点' if not at else
           '全部站上最高点' if not off else
           f'{B.quant(len(at), m, "条")}在最高点{at_txt}')
    # 「高点全在成交侧」由未平仓在不在 at_peak 里决定，不是写死的判断；且只说命中的那几条
    # 是什么（未平仓是五条里唯一的存量列，故 OI 不在 at 时这句必真），不说落后的是什么 ——
    # 落后的三条里有两条本身就是成交侧，「存量没跟上」解释不了它们。
    tail1 = ('——存量的未平仓这次也在高点。' if OI in at else
             '——高点全在成交侧。' if at and OI in seen else '。')
    s1 = (f'{n}个月里{B.cn(m)}条量指标{hit}'
          # 名字一律以拉丁字母开头（CME / Cboe / HKEX …），前面补一个空格，
          # 否则「最陈旧的CME 未平仓」里中文与字母贴死，读起来像一个词
          + (f'；最陈旧的 {stale[0]}峰值停在{ym(stale[1])}' if stale else '') + tail1)

    # ── s2 / R2：三家里环比与同比反号的那一条，基数护栏。名次、方向全部现算。
    #    没有反号月时（三家同向）整句换成「环比最弱的那家 + 它上月的名次」，前提不落空。
    BE = [(nm, B.base_effect(a, i)) for nm, a in
          [('CME', cme), ('Cboe', cboe), ('HKEX', hkex)]]
    BE = [x for x in BE if B.need(x[1]['mm']) and x[1]['prev_rank']]
    if not BE:
        s2 = ''                                   # 头一个月没有上月，这句不写（整页照发）
    else:
        rev = [x for x in BE if x[1]['conflict']]
        nm2, be = (rev[0] if rev else min(BE, key=lambda x: x[1]['mm']))
        d2 = '跌' if be['mm'] < 0 else '涨'        # 方向词跟着符号走，不写死
        mag2 = f'{abs(be["mm"]) * 100:.1f}%'       # 幅度与方向词分开给，不用带符号的 B.pct
        # y/y 的符号不再写出来：与「反号」+ 环比方向重复，且抬头已印三家的 y/y。
        # 无反号月走 argmin 那支时，「最弱」两个字不含方向，而后半句的「从高位回落」
        # 需要方向才站得住 —— 故按 mm 的符号写成「跌幅最大」或「涨幅最小」（两者对
        # argmin 都恒真），把方向摆到句面上。
        # k == n 时 B.quant 给的是「多达三家」，而分母也是三家 —— 「三家多达三家」读着像
        # 数没算对。全中是一个确定的事实，直接说「全部」，仍由 len 决定，不是写死的定性词。
        cnt2 = '全部' if len(rev) == len(BE) else B.quant(len(rev), len(BE), '家')
        lead2 = (f'{B.cn(len(BE))}家{cnt2}环比与同比反号：'
                 f'{nm2} 环比{d2}{mag2}'
                 if rev else f'{B.cn(len(BE))}家环比同比同向，{nm2} 环比{d2}{mag2}、'
                             f'{d2}幅最{"大" if be["mm"] < 0 else "小"}')
        # 「从高位回落」只在**跌**且上月确实在前三分之一时才成立；涨则看上月是不是低基数
        base2 = ('从高位回落不是掉头' if be['mm'] < 0 and be['prev_rank'] <= n / 3 else
                 '是低基数顶出来的，不是拐点' if be['mm'] > 0 and be['prev_rank'] > n * 2 / 3
                 else f'上月不在极端，这{d2}不在基数上')
        s2 = (lead2 + f'，上月却是全样本'
              + ('最高月' if be['prev_is_max'] else f'第{be["prev_rank"]}高月')
              + f'——{base2}；{B.cn(len(BE))}条本是 ADV／ADT <b>日均值</b>，{d2}里无交易日效应。')

    # ── s3 / 口径背离：总量的变动集中在哪一条品种线上。
    #    公司披露的粒度是六条品种线，所以「只来自一个品种」必须在六条粒度上成立才能写；
    #    改报「单条 Δ ÷ 总量净 Δ」的倍数 —— 只看总量 m/m 读不出「一条抵掉净跌幅两倍」。
    LINES = [('利率', 'adv_rates_kcontracts'), ('股指', 'adv_equity_kcontracts'),
             ('能源', 'adv_energy_kcontracts'), ('农产', 'adv_ag_kcontracts'),
             ('外汇', 'adv_fx_kcontracts'), ('金属', 'adv_metals_kcontracts')]
    LV = [(nm, col_of('cme', c).values) for nm, c in LINES]
    LV = [(nm, a) for nm, a in LV if i >= 1 and B.need(a[i], a[i - 1]) and a[i - 1]]
    mix = ''
    if len(LV) >= 2 and i >= 1 and B.need(cme[i], cme[i - 1]) and cme[i] != cme[i - 1]:
        tot_d = float(cme[i] - cme[i - 1])
        dl = [(nm, float(a[i] - a[i - 1]), float(a[i] / a[i - 1] - 1)) for nm, a in LV]
        ln, ld, lmm = max(dl, key=lambda t: abs(t[1]))
        d3 = '跌' if tot_d < 0 else '涨'            # 方向词跟着总量的符号走
        same = [nm for nm, x, _ in dl if x and (x < 0) == (tot_d < 0)]
        sh = ld / tot_d
        # 动词跟着总量方向走：「抵掉净涨幅」在上涨月里是反义词（抵掉 = 冲销），
        # 重放里 2026-05 就印出过「单条抵掉净涨幅的1.0倍」。上涨用「顶起」。
        mix = ((f'CME 的{d3}集中在{ln}：环比{B.pct(lmm)}，'
                f'单条{"抵掉" if tot_d < 0 else "顶起"}净{d3}幅的<b>{sh:.1f}倍</b>' if sh >= 1 else
                # 占比这里不带符号：「跌幅的 +71%」里的加号是格式化产物，与同句的「跌」打架
                f'CME 的{d3}最大一块来自{ln}：环比{B.pct(lmm)}，'
                f'占净{d3}幅的{B.pct(sh, 0, sign=False)}' if sh > 0 else
                f'CME 总量{d3}，但变动最大的{ln}反在另一边（环比{B.pct(lmm)}）')
               + f'，{B.cn(len(LV))}条线里同{d3}的{B.quant(len(same), len(LV), "条")}。')
    s3 = mix

    # ── 两个占比的序数位置（挂到 s4 的后半句，不单独成句 —— 四句是本页的上限）──
    # 两个占比都是 A/B 形式的推导值（两家都只披露分子与分母），R5 要逐个标 —— 一句里
    # 标一次不覆盖并列项，故写成「均为推导值」一次性罩住两项。
    #    两条里有一条缺读数时只报另一条（不是整句丢掉）：R5 的标注是逐项的，
    #    并列项少一个，「均为」也要跟着变成单项的「（推导值）」。
    #    句末的「。」交给 s4 收，这里不带 —— 否则并进 s4 会出现两个句号。
    rsh, csh = df['cme_rates_share'].values, df['cboe_index_share'].values
    SHR = [(nm, B.rank_of(a, i), int(np.isfinite(a).sum()))
           for nm, a in [('利率', rsh), ('Cboe 指数期权', csh)]]
    SHR = [x for x in SHR if x[1]]
    # 与 s1 同窗口时省掉分母（s1 开头已写「N 个月里」），不同才逐个标出来
    pos = ('第' + '与第'.join(str(r) for _, r, _ in SHR) + '位'
           if all(k == n for _, _, k in SHR)
           else '与'.join(f'第{r}/{k}位' for _, r, k in SHR))
    sh_txt = ('' if not SHR else
              f'{SHR[0][0]}与 {SHR[1][0]}占比（均为推导值）分列{pos}，分母不同各读各的'
              if len(SHR) == 2 else f'{SHR[0][0]}占比（推导值）落在{pos}')

    # ── s4 / 分母：换一段口径看累计领先，再把两个占比的序数挂在同一句里。
    #    末点指数 = 当月÷基月（两个单月）；regime_ratio = 首年年均÷近13个月均值
    #    （两段期间均值）。两者不是一个东西，所以**两个口径都点名**，但只断言一件事：
    #    排序对不对得上。上一版还把两者的差额拆成「末点效应 vs 基月效应」并印出
    #    「差额的 66% 来自基月偏低」——那是二元贡献度分解，超出 brief 的分寸
    #    （brief.py::render 明文禁的那一类），连同 uni / gap / frac 一起删掉。
    #    留下的 same_order 仍是**当场验**的断言：两种口径的降序名单逐位相等才敢写「同序」，
    #    不同序时点名末点口径下领先的是谁（那家现算，不写死）。
    rg = B.regime_ratio(months, [('CME', cme), ('Cboe', cboe), ('HKEX', hkex)], i)
    RS = dict(rg['ratios'])
    endp = {'CME': float(rebase('cme_adv').values[i]),
            'Cboe': float(rebase('cboe_adv').values[i]),
            'HKEX': float(rebase('hkex_adt').values[i])}
    same_order = ([nm for nm, _ in sorted(endp.items(), key=lambda kv: -kv[1])]
                  == [nm for nm, _ in sorted(RS.items(), key=lambda kv: -kv[1])])
    s4 = (f'换个分母：<b>{rg["y0"][2:]}年均÷近13月均值</b>是 '
          + '、'.join(f'{nm} {r:.1f}' for nm, r in sorted(RS.items(), key=lambda kv: -kv[1])) + '倍'
          + ('，与 Exhibit 2 末点（当月÷基月）同序' if same_order else
             f'，与 Exhibit 2 末点（当月÷基月）不同序：末点口径{max(endp, key=endp.get)}领先')
          + (f'；{sh_txt}。' if sh_txt else '。')) if RS else ''

    return B.render([s1, s2, s3, s4])


# ────────────────────────────── 7. 抬头与 payload ──────────────────────────────
_idx_now = {k: float(rebase(k)[CUR]) for k in ('cme_adv', 'cboe_adv', 'hkex_adt')}
_yoy_now = {'CME': float(df['cme_adv_yoy'][CUR]),
            'Cboe': float(df['cboe_adv_yoy'][CUR]),
            'HKEX': float(df['hkex_adt_yoy'][CUR])}
_rank = sorted(_yoy_now.items(), key=lambda kv: -kv[1])
# 抬头必须把 m/m 也写出来：只写 y/y 的抬头会给出一个纯正面的印象，而 m/m 常常反向
# （本月 CME 总 ADV 的 m/m 就是两位数下跌，只写 y/y 的话要翻到汇总表才看得到）。
# 三家的 m/m 一律列出，不做「挑一个最难看的」这种选择性叙事。
_mom_now = {'CME': (float(df['cme_adv'][CUR]) / float(df['cme_adv'][PRV]) - 1) * 100,
            'Cboe': (float(df['cboe_adv'][CUR]) / float(df['cboe_adv'][PRV]) - 1) * 100,
            'HKEX': (float(df['hkex_adt'][CUR]) / float(df['hkex_adt'][PRV]) - 1) * 100}
_mom_txt = '、'.join(f'{k} {pct(v)}' for k, v in _mom_now.items())
_neg = [k for k, v in _mom_now.items() if v < 0]
_lead_idx = max(zip(['CME', 'Cboe', 'HKEX'],
                    [_idx_now['cme_adv'], _idx_now['cboe_adv'], _idx_now['hkex_adt']]),
                key=lambda kv: kv[1])
_lag_txt = '、'.join(f'{d}（{mlab(latest_each[k])}）'
                     for k, d, _, _, _ in HEAD if latest_each[k] == LATEST)
_all_txt = ' · '.join(f'{d} 更新至 {mlab(latest_each[k])}' for k, d, _, _, _ in HEAD)

# 官方发布日：横截面页取**成员里最晚**的那一个 —— 这一页要三家都发齐才成立，
# 所以「它什么时候可用」等于最后到的那一家。查的是共同最新月 LATEST，不是各家自己的
# 最新月：CME/Cboe 可能已经到 7 月了，但这页画的是 6 月，标 7 月的发布日就是张冠李戴。
# 有任何一家查不到就整体省略（latest_of 的语义）—— 拿部分成员算 max 必然偏早，
# 而偏早的日期看上去完全正常，没人会发现。
SOURCE_DATE = repo.latest_source_date(
    [k for k, *_ in HEAD], {k: LATEST for k, *_ in HEAD})

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
                 + f' · m/m：{_mom_txt}'
                 + ('（三家 m/m 均为正）' if not _neg else
                    f'（{"、".join(_neg)} 环比下滑）')
                 + f' · 自 {mlab(START)} 累计指数领先者 {_lead_idx[0]}（{_lead_idx[1]:,.0f}，'
                   f'基期 = 100）· CME 利率品种占 ADV {df["cme_rates_share"][CUR]:.0f}%'
                   f'（{pp(float(df["cme_rates_share"][CUR]) - float(df["cme_rates_share"][PRV]))}'
                   f' m/m）、Cboe 指数期权占美股期权 {df["cboe_index_share"][CUR]:.0f}%'),
    'brief': compose_brief(),
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
if SOURCE_DATE:
    payload['source_date'] = SOURCE_DATE          # 查不到就整个字段省掉，渲染端判的是存在性


def main():
    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(OUT, payload, TICKER)
    print(f'共同最新月 {LATEST} | 各家: '
          + ', '.join(f'{d}={latest_each[k]}' for k, d, _, _, _ in HEAD))
    print(f'短板 {"、".join(LAG)} | 共同窗口 {START} → {LATEST}（{len(IDX)} 个月）')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张）+ '
          f'Exhibit {table["n"]} 核对表')
    print(f'写出 {OUT}（{os.path.getsize(OUT) / 1024:.1f} KB）')
    print(payload['headline'])


if __name__ == '__main__':
    main()
