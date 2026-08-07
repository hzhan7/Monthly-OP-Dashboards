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

━━ 同比口径（2026-08-07 改）：曲线与表一律用 **12 个月滚动合计的同比** ━━
原来全页的同比都是**单月同比**（本月 ÷ 去年同月 − 1）。它的分子分母各只有一个月，
一次到期日错位、一次假期错月、去年同月的一次极端行情，都会整个吃进这一个读数里。
本页三条头条序列自己的实测（数字由 volcmp() 现算并印进图注，不写死）：

  · 逐月标准差从单月口径降到滚动口径，三家都腰斩量级；
  · 相邻月最大跳变，单月口径是三位数 pp，滚动口径是个位数到二十几 pp；
  · 最致命的是**符号相反**：有相当一批月份，单月同比说在涨、滚动合计同比说在跌
    （或反过来）—— 同一条序列、同一个月，两个口径讲的是相反的故事。

所以：Exhibit 1 的增长组、Exhibit 3/4/5/6 的同比曲线、抬头与页脚的 y/y 排序，
全部改成 12 个月滚动合计的同比。

**三个例外，逐条给理由（不是漏改）：**
  · Exhibit 9/10/11 的热力矩阵**保留单月同比**。矩阵是「行 = 年、列 = 月」，
    它存在的全部意义就是看**逐格**的月度波动与季节形状；换成滚动口径后相邻两格共享
    11 个月的数据，整张矩阵会变成一片平滑渐变，而「几月强、几月弱」这个唯一的题眼没了。
    标题里写死 "single-month"，图注点名差别。
  · 汇总表**水平值行（num / share）的 y/y 列保留单月**。那两列恒等于本行前三列的算术
    （本月 ÷ 或 − 去年同月）；给它印一个滚动同比，读者拿第一列除第三列会得到另一个数，
    **表内自相矛盾**，比口径混用更糟。组标题与表注都写明这一层，并把两个口径的当期
    读数并排印出来。增长组则相反：它三列显示的本身就是滚动同比读数，全程滚动口径。
  · 汇总表的 **m/m 列保留**：它是「本月 vs 上月」的运营监控量，本来就该看单月，
    平滑掉就没有监控意义了。
⇒ 全页单月口径只出现在这三处，每一处都在标题 / 组标题 / 图注里标死，
  并由 Exhibit 12 的诊断图把「两个口径能差到符号相反」直接画出来。

**滚动合计不乘交易日数。** 三家的源列都是日均口径（ADV / ADT），滚动合计 = 12 个月
日均值之和 = 12 × 滚动平均日均值，同比的分子分母同权，交易日在比值里不出现。
不乘的两条独立理由写在 TTM_UNIT_NOTE 里（一句话：cboe.csv 与 hkex.csv 根本没有交易日列，
且乘上去等于把日历差异重新塞回增长）。

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

import payload_guard
import pctile        # 3Y %ile 的唯一实现，全站共用（各写各的正是同一序列两页判定相反的原因）

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')


def load_source_dates():
    """按路径加载仓库根的 source_dates.py（官方发布日台账）。

    不能裸 import：`python3 build/exchanges.py` 跑起来时 sys.path 上只有 build/。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
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
TTM = 12         # 滚动窗口 = 12 个月（本页所有同比曲线的口径）
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
    """**单月**同比：先在该家自己的完整历史上算，再截到共同窗口。

    先截窗口再算同比，共同窗口头 12 个月的 y/y 会全成空 —— 那不是数据缺口，
    是算法把已有的历史扔了。

    ⚠ 本页只有三张热力矩阵（Exhibit 9/10/11）用它，理由见模块 docstring：
    矩阵要看的就是逐格月度波动，平滑掉等于把它唯一的题眼删了。
    其余所有同比一律走 ttm_of()。
    """
    d = RAW[key]
    return (d[col].pct_change(12) * 100).reindex(IDX)


def ttm_of(key, col):
    """**12 个月滚动合计的同比**（%）—— 本页曲线与汇总表的同比口径。

    算法：先在该家自己的完整历史上滚动求 12 个月的和，再对这条滚动序列取同比
    （本月的 12 个月合计 ÷ 去年同月的 12 个月合计 − 1），最后截到共同窗口。
    分子分母各覆盖 12 个整月，所以任何一次到期日错位、假期错月、单月极端行情
    都只占 1/12 的权重，而不是像单月同比那样整个吃进一个读数。

    先滚动再截窗口，理由与 yoy_of 相同：先截会白白扔掉窗口外已有的历史，
    害得共同窗口头 23 个月全成空 —— 那是算法造的缺口，不是数据缺口。

    **不乘交易日数**：源列本来就是日均（ADV / ADT），12 个日均值相加 =
    12 × 滚动平均日均值，同比是比值、分子分母同权，交易日在里面根本不出现。
    真乘上去反而把「今年这 12 个月比去年多两个交易日」这类日历差异重新塞回增长里。
    何况实读表头：series/cboe.csv 与 series/hkex.csv 根本没有交易日列
    （只有 series/cme.csv 有 trading_days），三家不可能用同一套加权。
    """
    d = RAW[key]
    return (d[col].rolling(TTM).sum().pct_change(12) * 100).reindex(IDX)


df = pd.DataFrame({
    'cme_adv': col_of('cme', 'adv_total_kcontracts'),
    'cboe_adv': col_of('cboe', 'adv_us_options_kcontracts'),
    'hkex_adt': col_of('hkex', 'adt_hkdbn'),
    'cme_oi': col_of('cme', 'oi_total_contracts', 1 / 1e6),
    'hkex_deriv': col_of('hkex', 'derivatives_adv_contracts', 1 / 1000.0),
}, index=IDX)
df['cme_rates_share'] = col_of('cme', 'adv_rates_kcontracts') / df['cme_adv'] * 100
df['cboe_index_share'] = col_of('cboe', 'adv_index_options_kcontracts') / df['cboe_adv'] * 100
# 单月同比：只喂三张热力矩阵与 Exhibit 12 的口径对照图
df['cme_adv_yoy'] = yoy_of('cme', 'adv_total_kcontracts')
df['cboe_adv_yoy'] = yoy_of('cboe', 'adv_us_options_kcontracts')
df['hkex_adt_yoy'] = yoy_of('hkex', 'adt_hkdbn')
# 12 个月滚动合计同比：全页曲线、汇总表、抬头、页脚的同比一律走这三列
df['cme_adv_ttm'] = ttm_of('cme', 'adv_total_kcontracts')
df['cboe_adv_ttm'] = ttm_of('cboe', 'adv_us_options_kcontracts')
df['hkex_adt_ttm'] = ttm_of('hkex', 'adt_hkdbn')

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


# ────────────── 口径对照：单月同比 vs 12 个月滚动合计同比（全部现算）──────────────
# 图注要回答的是「为什么不用单月同比」，那就必须拿**本页自己这三条序列**的实测说话。
# 引别的页的数字（哪怕结论一样）等于把一句没验过的话印在页面上。
def volcmp(mcol, tcol):
    """同一条底层序列的两个同比口径的对照量。

    三个量各自回答一个问题：
      · 逐月标准差 —— 这条曲线整体有多抖；
      · 相邻月最大跳变 —— 最坏的一次「一个月之内读数翻天」有多大；
      · 符号相反的月份 —— 最有杀伤力的一个：同一个月，一个口径说涨、另一个说跌。
        前两个只是「噪音大」，这一个是「结论反了」。
    """
    m, t = df[mcol], df[tcol]
    both = pd.DataFrame({'m': m, 't': t}).dropna()
    opp = both[(both['m'] * both['t']) < 0]
    jm, jt = m.diff().abs(), t.diff().abs()
    tv = t.dropna()
    return {
        'm_sd': float(m.dropna().std()), 't_sd': float(tv.std()),
        'm_jump': float(jm.max()), 'm_jump_at': jm.idxmax(),
        't_jump': float(jt.max()), 't_jump_at': jt.idxmax(),
        'n_opp': len(opp), 'n_both': len(both),
        'opp': [(p, float(r['m']), float(r['t'])) for p, r in opp.iterrows()],
        'first': tv.index[0] if len(tv) else None,
        'cur_m': float(m[CUR]), 'cur_t': float(t[CUR]),
    }


VC = {'CME': volcmp('cme_adv_yoy', 'cme_adv_ttm'),
      'Cboe': volcmp('cboe_adv_yoy', 'cboe_adv_ttm'),
      'HKEX': volcmp('hkex_adt_yoy', 'hkex_adt_ttm')}


def flips(name, k=2):
    """某家最刺眼的 k 个「符号相反月」写成人话 —— 按两个读数的距离排，最远的最有说服力。"""
    top = sorted(VC[name]['opp'], key=lambda x: -abs(x[1] - x[2]))[:k]
    return '、'.join(f'{mlab(p)}（单月 {pct(m)}，滚动 {pct(t)}）' for p, m, t in top)


_SD_TXT = '、'.join(f'{k} {v["m_sd"]:.1f}→{v["t_sd"]:.1f}pp' for k, v in VC.items())
_JUMP_TXT = '、'.join(f'{k} {v["m_jump"]:.1f}pp（{mlab(v["m_jump_at"])}）→{v["t_jump"]:.1f}pp'
                      for k, v in VC.items())
_OPP_TXT = '、'.join(f'{k} {v["n_opp"]}/{v["n_both"]} 个月' for k, v in VC.items())
# 举例用符号相反月最多的那一家 —— 不是挑对自己有利的，是挑证据最强的
_WORST = max(VC.items(), key=lambda kv: kv[1]['n_opp'])[0]

WHY_TTM = (
    '<b>为什么不用单月同比。</b>单月同比 = 本月 ÷ 去年同月 − 1，分子分母各只有一个月，'
    '一次到期日错位、一次假期错月、去年同月的一次极端行情，都会整个吃进这一个读数里。'
    f'本页三条头条序列在共同窗口 {mlab(START)}–{mlab(LATEST)} 上的实测（现算，不写死）：'
    f'<b>逐月标准差</b>（单月→滚动）{_SD_TXT}；'
    f'<b>相邻月最大跳变</b> {_JUMP_TXT}；'
    f'最要命的是<b>符号相反的月份</b> {_OPP_TXT} —— '
    f'例如 {_WORST} 的 {flips(_WORST)}，同一条序列、同一个月，'
    '单月同比说在涨、滚动合计同比说在跌（或反过来），图上讲的是相反的故事。'
)

TTM_UNIT_NOTE = (
    f'<b>滚动合计怎么算：{TTM} 个月的日均值直接相加，不乘交易日数。</b>'
    '三家的源列本来就是日均口径（CME / Cboe 是 ADV、HKEX 是 ADT），'
    f'{TTM} 个日均值相加 = {TTM} × 滚动平均日均值；同比是比值、分子分母同权，'
    '交易日在里面根本不出现。不乘的两条独立理由：'
    '① 实读表头，<code>series/cboe.csv</code> 与 <code>series/hkex.csv</code> '
    '根本没有交易日列（只有 <code>series/cme.csv</code> 有 <code>trading_days</code>），'
    '三家不可能用同一套加权；'
    '② 就算三家都有，乘上去也是把「今年这 12 个月比去年多两个交易日」这类日历差异'
    '重新塞回增长里，而那正是本页要消掉的噪音。'
)


# ── 同比图「拆图还是截轴」的量化依据 ──
# 图注里的每一个数字都从这里算，不写死：写死的话下个月序列一变，图注就成了假话
# （本仓已经有过「图注说画了断点线、图上其实没有」的先例，同一类错不重犯）。
def _rng(*arrs):
    v = [float(x) for a in arrs for x in a if x is not None and np.isfinite(float(x))]
    return (min(v), max(v)) if v else (0.0, 0.0)


def _over(arr, hi):
    return sum(1 for x in arr if x is not None and np.isfinite(float(x)) and float(x) > hi)


# 量程一律按**新口径（滚动合计同比）**算 —— 拆图/截轴的取舍要对着实际上图的那条线算，
# 拿旧口径的量程去论证新口径的版面是两码事。
CC25_LO, CC25_HI = _rng(win('cme_adv_ttm'), win('cboe_adv_ttm'))
HK25_LO, HK25_HI = _rng(win('hkex_adt_ttm'))
CCF_LO, CCF_HI = _rng(df['cme_adv_ttm'].values, df['cboe_adv_ttm'].values)
HKF_LO, HKF_HI = _rng(df['hkex_adt_ttm'].values)
# 「若强行同轴、把轴截到 CME/Cboe 的量程」会有多少个 HKEX 点越界 —— 截轴方案的代价
CLIP25 = _over(win('hkex_adt_ttm'), CC25_HI)
CLIPF = _over(df['hkex_adt_ttm'].values, CCF_HI)
HKF_N = int(np.isfinite(df['hkex_adt_ttm'].values.astype(float)).sum())
SPAN25 = (HK25_HI - HK25_LO) / max(1e-9, CC25_HI - CC25_LO)
SPANF = (HKF_HI - HKF_LO) / max(1e-9, CCF_HI - CCF_LO)


# ────────────────────────────── 2. Exhibit 1：汇总表 ──────────────────────────────
# (kind, 标签, 列, 小数位, 模式)
#   num    水平值，m/m 与 y/y 用百分比变化
#   share  占比（已是 %），差异用 pp
#   growth 同比读数（已是 %，带符号），差异用 pp
#
# ⚠ 口径分层，别把两组的 y/y 摆在一起读：
#   m/m 与 y/y 两列**恒等于本行三列的算术**（本月 对 上月 / 去年同月），这是硬约束 ——
#   若给水平值行印一个滚动同比，读者拿第一列除第三列会得到另一个数，表内自相矛盾，
#   那比口径混用更糟。所以：
#     · 水平值行（num / share）的 y/y 天然是**单月**口径，改不了，只能标清楚；
#     · 增长组三列显示的**本身就是滚动同比读数**，所以它的 m/m / y/y 是「滚动读数
#       这个月比上月/去年同月挪了几 pp」，全程滚动口径。
#   两者的差距由 WHY_TTM 现算印在表注里，读者一眼能看到它们不可比。
SUM_ROWS = [
    ('group', 'Volume — each in its own unit, not additive '
              '(m/m and y/y here are this row\'s own arithmetic ⇒ single-month basis)',
     None, None, None),
    ('row', 'CME total ADV (k contracts/day)', 'cme_adv', 0, 'num'),
    ('row', 'Cboe U.S. options ADV (k contracts/day)', 'cboe_adv', 0, 'num'),
    ('row', 'HKEX cash ADT (HK$bn/day)', 'hkex_adt', 0, 'num'),
    ('group', f'Growth (% y/y on a {TTM}-month rolling-sum basis, not single-month) '
              f'— this is the page\'s trend basis',
     None, None, None),
    ('row', 'CME total ADV', 'cme_adv_ttm', 1, 'growth'),
    ('row', 'Cboe U.S. options ADV', 'cboe_adv_ttm', 1, 'growth'),
    ('row', 'HKEX cash ADT', 'hkex_adt_ttm', 1, 'growth'),
    ('group', 'Mix and open interest '
              '(m/m and y/y here are this row\'s own arithmetic ⇒ single-month basis)',
     None, None, None),
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
                 f'<b>增长组是 {TTM} 个月滚动合计的同比</b>（本月往前 {TTM} 个月的合计 ÷ '
                 f'去年同月往前 {TTM} 个月的合计 − 1），不是单月同比。' + WHY_TTM
                 + '<b>⚠ 本表两组的 y/y 不是同一个口径，不要放在一起读。</b>'
                   'm/m 与 y/y 两列<b>恒等于本行前三列的算术</b>（本月 对 上月 / 去年同月）'
                   '—— 这是硬约束：给水平值行印一个滚动同比，读者拿第一列除第三列会得到'
                   '另一个数，表内自相矛盾，那比口径混用更糟。所以水平值组与「Mix and open '
                   'interest」组的 y/y <b>天然是单月口径</b>，组标题里已写明；'
                   '而增长组三列显示的<b>本身就是滚动同比读数</b>，其 m/m / y/y 读的是'
                   '「滚动读数这个月比上月 / 去年同月挪了几 pp」，全程滚动口径。'
                 + f'差多少本页现算：{mlab(CUR)} '
                 + '、'.join(f'{k}（水平值行 y/y {pct(v["cur_m"])}、'
                             f'增长组 {pct(v["cur_t"])}）' for k, v in VC.items())
                 + '。<b>要判断趋势与排名请只看增长组</b>；水平值行的三列与其 y/y 只为'
                   '与官方披露逐条核对。'
                 + '<b>m/m 列一律保持单月口径</b>：那是「本月 vs 上月」的运营监控量，'
                   '本来就该看单月，平滑掉就没有监控意义了。'
                 + TTM_UNIT_NOTE +
                 '占比与同比读数本身已是百分比，其变化用 pp/bp（绝对值不足 1pp 时写 bp）；'
                 '水平值的变化用百分比。'
                 '3Y %ile = 该读数在最近 36 个月里高于多少百分比的观测，'
                 '判据与留空规则由全站唯一实现 <code>build/pctile.py</code> 给出：'
                 '回放最近 24 个月，若 ≥70% 的月份分位都钉在 100 或 0，'
                 '说明这一列对该行没有区分度，留空。' + blank_txt),
    }


# ────────────────────────────── 3. Exhibit 2..12 ──────────────────────────────
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

_cur_yoy = (f'CME {pct(df["cme_adv_ttm"][CUR])}、Cboe {pct(df["cboe_adv_ttm"][CUR])}、'
            f'HKEX {pct(df["hkex_adt_ttm"][CUR])}')
# 同一个月两个口径的读数并排 —— 这是「换口径不是文字游戏」最短的一句证据
_cur_both = '、'.join(f'{k}（单月 {pct(v["cur_m"])} / 滚动 {pct(v["cur_t"])}）'
                      for k, v in VC.items())
_TTM_HEAD = f'{TTM} 个月滚动合计同比'

ex.append({
    'n': 3, 'kind': 'lines_endlabels', 'fmt': 'f1', 'zero_line': True,
    'title': f'Volume growth, {TTM}-month rolling-sum y/y — CME vs Cboe, '
             f'last {WIN_LINE} months',
    'ylab': f'% y/y ({TTM}-mo rolling sum)',
    'series': [
        {'name': 'CME total ADV', 'color': CME_C, 'values': L(win('cme_adv_ttm'))},
        {'name': 'Cboe U.S. options ADV', 'color': CBOE_C, 'values': L(win('cboe_adv_ttm'))},
    ],
    'src_extra': (f'Trailing-{TTM}-month sum of each company\'s own daily-average series, '
                  f'compared with the same {TTM}-month sum a year earlier. Not single-month '
                  f'y/y. HKEX is on its own axis in the next exhibit — its range over these '
                  f'{WIN_LINE} months is about {SPAN25:.0f}x wider'),
    'note': (f'<b>口径 = {_TTM_HEAD}</b>：本月往前 {TTM} 个月的合计 ÷ 去年同月往前 '
             f'{TTM} 个月的合计 − 1。同比把单位问题消掉了 —— 张数的同比与金额的同比'
             '都是纯数，可以直接比；这张图只放量级相近的 CME 与 Cboe，'
             '好让两者的差距占满纵轴。'
             f'{mlab(CUR)}：{_cur_yoy}（HKEX 见 Exhibit 4，<b>纵轴不同</b>，'
             '两张图的线高不可直接对望）。' + WHY_TTM
             + f'本月两个口径并排看就是：{_cur_both}。' + TTM_UNIT_NOTE
             + '端点标签保留一位小数 —— 取整会把相差不到 1pp 的两个读数印成同一个数字，'
               '而这几张图的题眼恰恰是谁跑赢。'),
})

ex.append({
    'n': 4, 'kind': 'lines_endlabels', 'fmt': 'f1', 'zero_line': True,
    'title': f'HKEX cash ADT, {TTM}-month rolling-sum y/y — last {WIN_LINE} months '
             f'(own axis)',
    'ylab': f'% y/y ({TTM}-mo rolling sum)',
    'series': [
        {'name': 'HKEX cash ADT', 'color': HKEX_C, 'values': L(win('hkex_adt_ttm'))},
    ],
    'src_extra': (f'Same {TTM}-month rolling-sum basis as the previous exhibit. Split out '
                  f'because its range over these {WIN_LINE} months is about {SPAN25:.0f}x '
                  f'wider; the axis is NOT shared with CME / Cboe'),
    'note': (f'<b>口径 = {_TTM_HEAD}</b>，与 Exhibit 3 同口径、不同纵轴'
             f'（本图 {HK25_LO:+.0f}% ~ {HK25_HI:+.0f}%，'
             f'Exhibit 3 {CC25_LO:+.0f}% ~ {CC25_HI:+.0f}%），'
             '所以两张图之间只能比走向、不能比线的高低；要比读数请看数字：'
             f'{mlab(CUR)} {_cur_yoy}。'
             f'<b>HKEX 正是本页换口径的最强证据</b>：它的单月同比与滚动同比在 '
             f'{VC["HKEX"]["n_opp"]}/{VC["HKEX"]["n_both"]} 个月里<b>符号相反</b>，'
             f'例如 {flips("HKEX", 3)}；单月同比的相邻月最大跳变 '
             f'{VC["HKEX"]["m_jump"]:.1f}pp（{mlab(VC["HKEX"]["m_jump_at"])}），'
             f'滚动口径只有 {VC["HKEX"]["t_jump"]:.1f}pp；逐月标准差 '
             f'{VC["HKEX"]["m_sd"]:.1f}pp → {VC["HKEX"]["t_sd"]:.1f}pp。'
             '港股成交额的增长是整段抬升而不是一两个离群月 —— 若强行与 Exhibit 3 同轴并'
             f'把轴截到 CME/Cboe 的量程，这 {WIN_LINE} 个月里会有 {CLIP25} 个点变成红色'
             '越界圈，那是把一条真实序列画成异常，所以本页选择拆图而不是截轴。'),
})

ex.append({
    'n': 5, 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H_ENDLABEL,
    'fmt': 'f1', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'zero_line': True,
    'end_label': True, 'label_fmt': 'f1',
    'title': f'Volume growth, {TTM}-month rolling-sum y/y — CME vs Cboe, '
             f'full common window',
    'ylab': f'% y/y ({TTM}-mo rolling sum)',
    'series': [
        {'name': 'CME total ADV', 'color': CME_C, 'values': L(df['cme_adv_ttm'].values)},
        {'name': 'Cboe U.S. options ADV', 'color': CBOE_C, 'values': L(df['cboe_adv_ttm'].values)},
    ],
    'src_extra': (f'Both series on the {TTM}-month rolling-sum basis over the whole common '
                  f'history; shows whether the current ranking is a new development or the '
                  f'standing order'),
    'note': (f'<b>口径 = {_TTM_HEAD}</b>。两家的同比在同一量级上'
             f'（共同窗口内 {CCF_LO:+.0f}% ~ {CCF_HI:+.0f}%），同轴可直读。'
             'HKEX 的同一口径见 Exhibit 6 —— 它的量程是这张图的 '
             f'{SPANF:.1f} 倍，同轴会把这两条线压成一条带。'
             f'改口径前这张图画的是单月同比，两家的逐月标准差分别是 '
             f'{VC["CME"]["m_sd"]:.1f}pp 与 {VC["Cboe"]["m_sd"]:.1f}pp，'
             f'现在是 {VC["CME"]["t_sd"]:.1f}pp 与 {VC["Cboe"]["t_sd"]:.1f}pp；'
             f'单月口径下 CME 有 {VC["CME"]["n_opp"]}/{VC["CME"]["n_both"]} 个月、'
             f'Cboe 有 {VC["Cboe"]["n_opp"]}/{VC["Cboe"]["n_both"]} 个月'
             '与滚动口径<b>符号相反</b>，那些月份原来的线在讲反话。'),
})

ex.append({
    'n': 6, 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H_ENDLABEL,
    'fmt': 'f1', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'zero_line': True,
    'end_label': True, 'label_fmt': 'f1',
    'title': f'HKEX cash ADT, {TTM}-month rolling-sum y/y — full common window (own axis)',
    'ylab': f'% y/y ({TTM}-mo rolling sum)',
    'series': [
        {'name': 'HKEX cash ADT', 'color': HKEX_C, 'values': L(df['hkex_adt_ttm'].values)},
    ],
    'src_extra': (f'Own axis: this series ranges {HKF_LO:+.0f}% to {HKF_HI:+.0f}% over the '
                  f'common window, about {SPANF:.1f}x the CME / Cboe range in the previous '
                  f'exhibit'),
    'note': (f'<b>口径 = {_TTM_HEAD}</b>。HKEX 的现货 ADT 自 {mlab(START)} 起才有披露，'
             f'而滚动同比要拿两段各 {TTM} 个月的合计相除，所以它的第一个读数落在 '
             f'<b>{mlab(VC["HKEX"]["first"])}</b>（单月同比是 {mlab(START + 12)}，'
             f'换口径的代价就是窗口前端多空 {(VC["HKEX"]["first"] - (START + 12)).n} 个月）。'
             '在那之前本图<b>没有线</b>（不是零增长，是没有数据；缺口一律留空、不连直线）。'
             f'共同窗口 {len(IDX)} 个月里本图有 {HKF_N} 个有效月。'
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


# 三张矩阵共用的口径提醒：它们是全页仅有的单月同比，必须让读者一眼看见差别。
HEAT_NOTE = (
    f'<b>本图是单月同比，与 Exhibit 3–6 和汇总表的 {TTM} 个月滚动合计同比'
    f'<u>不是同一个口径</u>，两处的读数不可互相印证。</b>'
    '保留单月口径是判定，不是漏改：矩阵的形状就是「行 = 年、列 = 月」，'
    '它存在的意义正是看<b>逐格</b>的月度波动与季节形状；换成滚动口径后相邻两格共享 '
    f'{TTM - 1} 个月的原始数据，整张矩阵会摊成一片平滑渐变，'
    '「几月强、几月弱」这个唯一的题眼就没了。'
    f'两个口径差多少，本页实测：逐月标准差（单月→滚动）{_SD_TXT}；'
    f'相邻月最大跳变 {_JUMP_TXT}；符号相反的月份 {_OPP_TXT}。'
    '<b>所以本图适合读季节性与单月异常，不适合读趋势</b> —— 趋势看 Exhibit 3–6。'
)


def heat(n, col, title, src_extra, legend, extra=''):
    """行=年、列=月的**单月**同比热力矩阵。年份从该序列自己的有效值取，全空的年不占一行。

    ⚠ 全页只有这三张图保留单月同比，是**判定不改**而不是漏改：矩阵的形状就是
    「行 = 年、列 = 月」，它存在的全部意义是看逐格的月度波动与季节形状。
    换成 12 个月滚动合计口径后，相邻两格共享 11 个月的原始数据，整张矩阵会摊成
    一片平滑渐变，「几月强、几月弱」这个唯一的题眼就没了 —— 平滑掉反而是错的。
    代价是本页同时存在两种同比口径，所以三张图的**标题里写死 single-month**，
    图注与页尾口径说明都点名差别，并把两个口径的实测差距摆出来。

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
            'src_extra': src_extra, 'note': HEAT_NOTE + extra}


ex.append(heat(9, 'cme_adv_yoy', 'CME total ADV, single-month y/y (%)',
               'Single-month y/y (this month vs the same month a year earlier) — NOT the '
               f'{TTM}-month rolling-sum basis used in Exhibits 3-6. Green = faster growth. '
               'Colour scale is per-matrix (5th-95th percentile of its own cells), so the '
               'three matrices below are not colour-comparable with each other',
               'CME total ADV single-month y/y',
               '色标取本矩阵自己全部有效格的 5/95 分位，'
               '所以 Exhibit 9/10/11 三张图的<b>颜色不能横向比</b>。'))
ex.append(heat(10, 'cboe_adv_yoy', 'Cboe U.S. options ADV, single-month y/y (%)',
               f'Single-month y/y, not the {TTM}-month rolling-sum basis. Green = faster growth',
               'Cboe U.S. options ADV single-month y/y'))
ex.append(heat(11, 'hkex_adt_yoy', 'HKEX cash ADT, single-month y/y (%)',
               f'Single-month y/y, not the {TTM}-month rolling-sum basis. Green = faster growth. '
               f'HKEX cash ADT starts {mlab(START)}, so its first single-month y/y is '
               f'{mlab(START + 12)} — {START.year} has no row at all rather than an empty one',
               'HKEX cash ADT single-month y/y',
               f'本图起点比 Exhibit 6 早：单月同比自 {mlab(START + 12)} 就有值，'
               f'而滚动口径要到 {mlab(VC["HKEX"]["first"])} 才有第一个读数。'
               f'⚠ 本图 {VC["HKEX"]["n_opp"]} 个格子与 Exhibit 6 同月的读数<b>符号相反</b>'
               f'（例如 {flips("HKEX", 3)}）—— 两张图放在一起读之前请先看清各自的口径。'))

# ── Exhibit 12：口径对照（新增图一律追加在末尾，不插在中间）──
# 本页同时存在两种同比口径（曲线是滚动、矩阵是单月），契约要求要么全改、要么把差别
# 显式点明。文字点名还不够 —— 「符号相反」这件事只有画出来才叫看得见，
# 所以专门给一张诊断图，把 HKEX 的两条线叠在同一根轴上（同为 %，量纲相同，可同轴）。
# 选 HKEX 是因为它是三家里符号相反月最多、跳变最大的一条，也正是本页与亚太页共用的序列。
ex.append({
    'n': 12, 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H_ENDLABEL,
    'fmt': 'f1', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'zero_line': True,
    'end_label': True, 'label_fmt': 'f1',
    'title': f'Why not single-month y/y — HKEX cash ADT, both bases on one axis (diagnostic)',
    'ylab': '% y/y',
    'series': [
        {'name': 'Single-month y/y (old basis)', 'color': 'GRAY',
         'values': L(df['hkex_adt_yoy'].values)},
        {'name': f'{TTM}-month rolling-sum y/y (this page\'s basis)', 'color': HKEX_C,
         'values': L(df['hkex_adt_ttm'].values)},
    ],
    'src_extra': ('Diagnostic exhibit: the same underlying HKEX cash ADT series measured two '
                  'ways. Both are pure numbers in %, so they share one axis. This is the only '
                  'exhibit on the page where the two bases appear together'),
    'note': ('<b>这张图不是用来读港股趋势的，是用来读「口径差多少」的。</b>'
             '两条线的底层数据完全一样 —— 同一条 HKEX 现货 ADT，只是同比的分子分母'
             f'一个取 1 个月、一个取 {TTM} 个月。'
             f'共同窗口里两条线都存在的 {VC["HKEX"]["n_both"]} 个月中，有 '
             f'<b>{VC["HKEX"]["n_opp"]} 个月符号相反</b>：'
             f'{flips("HKEX", 4)}。'
             f'灰线（单月）的逐月标准差 {VC["HKEX"]["m_sd"]:.1f}pp、相邻月最大跳变 '
             f'{VC["HKEX"]["m_jump"]:.1f}pp（{mlab(VC["HKEX"]["m_jump_at"])}）；'
             f'金线（滚动）分别是 {VC["HKEX"]["t_sd"]:.1f}pp 与 '
             f'{VC["HKEX"]["t_jump"]:.1f}pp（{mlab(VC["HKEX"]["t_jump_at"])}）。'
             f'另两家同一组对照：CME {VC["CME"]["m_sd"]:.1f}→{VC["CME"]["t_sd"]:.1f}pp / '
             f'{VC["CME"]["n_opp"]} 个月符号相反，'
             f'Cboe {VC["Cboe"]["m_sd"]:.1f}→{VC["Cboe"]["t_sd"]:.1f}pp / '
             f'{VC["Cboe"]["n_opp"]} 个月符号相反。'
             f'灰线起点早（{mlab(START + 12)}）、金线起点晚（{mlab(VC["HKEX"]["first"])}）'
             f'，那段只有灰线的区间不参与上面的符号比对。' + TTM_UNIT_NOTE),
})

# ────────────────────── 4. 核对表（官方原始单位）——编号接在最后一张图之后 ──────────────────────
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
# 编号现算：末尾加了一张诊断图之后写死 12 就会与 Exhibit 12 撞号，
# 而页面不会报错 —— 只是两张卡片顶着同一个编号，读者以为漏了一张。
table = {
    'n': ex[-1]['n'] + 1,
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

    f'<b>同比的口径：{TTM} 个月滚动合计，不是单月。</b>'
    f'本页 Exhibit 3–6 的曲线、Exhibit 1 汇总表的增长组、抬头与页脚的 y/y 排序，'
    f'一律是「本月往前 {TTM} 个月的合计 ÷ 去年同月往前 {TTM} 个月的合计 − 1」。' + WHY_TTM
    + TTM_UNIT_NOTE +
    f'算法上先在<b>该家自己的完整历史</b>上滚动求和再取同比，最后才截到共同窗口 —— '
    f'先截会白扔掉窗口外已有的历史。所以 CME / Cboe 的滚动同比从 {mlab(START)} '
    f'起就有值；HKEX 现货 ADT 自 {mlab(START)} 才有披露，'
    f'滚动同比要两段各 {TTM} 个月的合计，其第一个读数落在 '
    f'<b>{mlab(VC["HKEX"]["first"])}</b>（共同窗口 {len(IDX)} 个月里有 {HKF_N} 个有效月）。'
    f'在此之前 Exhibit 6 里没有线 —— 那是<b>没有数据</b>，不是零增长，缺口一律留空、'
    f'不连直线；Exhibit 11 的热力矩阵按单月口径排年，干脆不给 {START.year} 排一行 —— '
    '排了就是一整行灰格摆在矩阵顶上，第一眼像数据没加载出来。',

    f'<b>⚠ 本页同时存在两种同比口径，这里把差别一次说清。</b>'
    f'① <b>{TTM} 个月滚动合计同比</b> —— Exhibit 3、4、5、6 的曲线，Exhibit 1 的增长组，'
    '抬头与页脚的 y/y 排序，全部是这一种；'
    '② <b>单月同比</b> —— Exhibit 9、10、11 三张热力矩阵，Exhibit 12 口径对照图里那条灰线，'
    '以及 <b>Exhibit 1 汇总表里「水平值」与「Mix and open interest」两组的 y/y 列</b>'
    '（那两列恒等于本行三列的算术：本月 ÷ 去年同月；给它印一个滚动同比，读者自己一除就'
    '对不上，表内自相矛盾 —— 所以只能标清楚，不能改）。'
    '<b>保留②是判定，不是漏改</b>：热力矩阵的形状就是「行 = 年、列 = 月」，'
    '它存在的意义正是看逐格的月度波动与季节形状；换成滚动口径后相邻两格共享 '
    f'{TTM - 1} 个月的原始数据，整张矩阵摊成一片平滑渐变，'
    '「几月强、几月弱」这个唯一的题眼就没了 —— 那才是把图画错。'
    '<b>代价必须说明白：两种口径的读数不可互相印证。</b>'
    f'本页实测，同一条序列在两个口径下<b>符号相反</b>的月份数是 {_OPP_TXT}；'
    f'例如 {_WORST} 的 {flips(_WORST, 3)}。'
    'Exhibit 12 就是把这件事画出来的那张诊断图。'
    '结论：<b>读趋势与排名看 Exhibit 3–6 与汇总表的「增长」组；'
    '读季节性与单月异常看 Exhibit 9–11 与汇总表水平值行的 y/y；'
    '不要把两处的读数摆在一起比。</b>'
    '汇总表的 m/m 列不受影响 —— 它是「本月 vs 上月」的运营监控量，本来就该看单月。',

    '<b>同比图为什么拆成四张（Exhibit 3–6）。</b>三家的同比虽然都是纯数，量级却不在一个'
    f'数量级上：共同窗口内 CME 与 Cboe 合起来只在 {CCF_LO:+.0f}% ~ {CCF_HI:+.0f}% 之间，'
    f'而 HKEX 现货 ADT 在 {HKF_LO:+.0f}% ~ <b>{HKF_HI:+.0f}%</b>，量程是前者的 '
    f'{SPANF:.1f} 倍。三条线同轴时，CME 与 Cboe 被压进零线附近一条窄带里互相纠缠，'
    f'<b>而本月汇总表里「CME {pct(df["cme_adv_ttm"][CUR])} vs '
    f'Cboe {pct(df["cboe_adv_ttm"][CUR])}」正是最该看的差距</b> —— 读不出来这张图就白画了。'
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
    '要跨家比同比，请回 Exhibit 3–6 的曲线（<b>注意那三张矩阵是单月口径、曲线是滚动口径</b>，'
    '见上面「两种同比口径」那条）。'
    '格内数值取 0 位小数，−0.5% ~ 0 之间的格子印成「0%」而不是「-0%」'
    '（负零是格式化产物，不是缺失值）；真值保留到一位小数，切「表格」视图或悬停即可看到。',

    f'<b>Exhibit 12 是诊断图，不是结论图。</b>它把 HKEX 现货 ADT 的两种同比口径叠在'
    '同一根轴上（都是 %，量纲相同，可以同轴），唯一的用途是让「换口径」这件事看得见。'
    f'选 HKEX 是因为它在三家里符号相反的月份最多（{VC["HKEX"]["n_opp"]}/'
    f'{VC["HKEX"]["n_both"]}）、单月口径的相邻月跳变也最大'
    f'（{VC["HKEX"]["m_jump"]:.1f}pp @ {mlab(VC["HKEX"]["m_jump_at"])}）。'
    '<b>不要拿这张图读港股趋势</b> —— 读趋势请看 Exhibit 4 与 6 的金线。',

    '<b>没有口径断点，全页也确实一条断点线都没画。</b>本页三条头条序列在共同窗口内均无'
    '并购并表或口径重分类，故 payload 里没有任何 <code>break_at</code>，相邻期可直读 —— '
    '这一条与图上是对得上的，不存在「图注说画了断点、图上找不到」的情况。'
    '需要留意的是 Cboe 2017 年的数字是 Bats pro-forma combined —— 但那段早于本页共同起点 '
    f'{mlab(START)}，不进本页。日后若任一家出现口径变更，必须在这里登记并在对应图上画出 '
    'break，不能只靠图注文字提一句；断点随窗口滚出去时应当让它自然消失（连同这段文案），'
    '而不是让生成器报错停更。',

    f'<b>核对表（Exhibit {table["n"]}）用各家官方披露的原始计量单位，不做口径换算</b>：'
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
    f'(e) <b>同比口径由单月改成 {TTM} 个月滚动合计</b>（deck 与本页此前都是单月），'
    f'并在末尾新增 Exhibit 12 口径对照诊断图，核对表因此顺延为 Exhibit {table["n"]}；'
    '热力矩阵（Exhibit 9–11）保留单月口径，理由见上面「两种同比口径」那条。'
    '(f) 其余图序、标题文案、窗口长度（曲线 25 个月、热力 8 年）与原 deck 一致。',
]

# ────────────────────────────── 6. 抬头与 payload ──────────────────────────────
_idx_now = {k: float(rebase(k)[CUR]) for k in ('cme_adv', 'cboe_adv', 'hkex_adt')}
# 抬头的 y/y 走**滚动合计口径** —— 抬头是全页读者最先看到的一行，
# 挂单月同比等于把一个毛刺读数当成本期结论（本月三家的两个口径读数就差得很远，
# 排序都不一样，_rank_m 与 _rank 一起印出来正是为了让这件事无法被忽略）。
_yoy_now = {'CME': float(df['cme_adv_ttm'][CUR]),
            'Cboe': float(df['cboe_adv_ttm'][CUR]),
            'HKEX': float(df['hkex_adt_ttm'][CUR])}
_rank = sorted(_yoy_now.items(), key=lambda kv: -kv[1])
_mo_now = {'CME': float(df['cme_adv_yoy'][CUR]),
           'Cboe': float(df['cboe_adv_yoy'][CUR]),
           'HKEX': float(df['hkex_adt_yoy'][CUR])}
_rank_m = sorted(_mo_now.items(), key=lambda kv: -kv[1])
# 两个口径的排序名单一不一样，是「换口径不是修辞」最短的一句话，且完全由数据决定
_same_order = [k for k, _v in _rank] == [k for k, _v in _rank_m]
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
SOURCE_DATE = load_source_dates().latest_of(
    SERIES, [k for k, *_ in HEAD], {k: LATEST for k, *_ in HEAD})

payload = {
    'ticker': TICKER,
    'tracker': 'Exchange Group Cross-Section — CME / Cboe / HKEX',
    'title': f'交易所组横截面（CME / Cboe / HKEX）：谁在跑赢 — {zh(LATEST)}',
    'data_through': str(LATEST),
    'through_label': f'{zh(LATEST)}（共同最新月）',
    'subtitle': (f'数据源：三家官方月度成交量披露 · 共同窗口 {mlab(START)} – {mlab(LATEST)}'
                 f'（{len(IDX)} 个月）· 发布门槛取成员的共同最新月，'
                 f'短板 {"、".join(LAG)} · 单位不可加总，一律用同比与指数化比较 · '
                 f'同比口径 = {TTM} 个月滚动合计（热力矩阵 Exhibit 9-11 是单月口径，'
                 f'另计）· 版式仿 Goldman Sachs GIR · 仅图，无评论'),
    'headline': (f'y/y（{TTM} 个月滚动合计口径）排序：'
                 + '、'.join(f'{k} {pct(v)}' for k, v in _rank)
                 + '（同月的单月同比是 '
                 + '、'.join(f'{k} {pct(v)}' for k, v in _rank_m)
                 + ('，排序一致，但幅度差得远' if _same_order else '，连排序都不一样')
                 + '，本页不采用）'
                 + f' · m/m：{_mom_txt}'
                 + ('（三家 m/m 均为正）' if not _neg else
                    f'（{"、".join(_neg)} 环比下滑）')
                 + f' · 自 {mlab(START)} 累计指数领先者 {_lead_idx[0]}（{_lead_idx[1]:,.0f}，'
                   f'基期 = 100）· CME 利率品种占 ADV {df["cme_rates_share"][CUR]:.0f}%'
                   f'（{pp(float(df["cme_rates_share"][CUR]) - float(df["cme_rates_share"][PRV]))}'
                   f' m/m）、Cboe 指数期权占美股期权 {df["cboe_index_share"][CUR]:.0f}%'),
    'hub_line': (f'共同最新月 {mlab(LATEST)}（短板 {"、".join(LAG)}）；'
                 f'y/y 领先 {_rank[0][0]} {pct(_rank[0][1])}'
                 f'（{TTM} 个月滚动合计口径）'),
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
                 f'<b>同比口径 = {TTM} 个月滚动合计</b>（单月同比毛刺过大：'
                 f'本页实测符号相反的月份 {_OPP_TXT}）；'
                 f'仅 Exhibit 9–11 的热力矩阵、Exhibit 12 的灰线、'
                 f'以及汇总表水平值行的 y/y 列（那列恒等于本行三列的算术）保留单月口径，'
                 f'两种口径不可互相印证 · '
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
    # 口径自检：改口径的全部依据一行一家印出来，跑一次核对一次（图注里的数字同源）
    print(f'同比口径 = {TTM} 个月滚动合计（热力矩阵 Exhibit 9-11 保留单月，见口径说明）')
    for k, v in VC.items():
        print(f'  {k:5s} 逐月标准差 {v["m_sd"]:6.1f}→{v["t_sd"]:5.1f}pp | '
              f'相邻月最大跳变 {v["m_jump"]:6.1f}pp({mlab(v["m_jump_at"])})'
              f'→{v["t_jump"]:5.1f}pp({mlab(v["t_jump_at"])}) | '
              f'符号相反 {v["n_opp"]:2d}/{v["n_both"]} 个月 | '
              f'{mlab(CUR)} 单月 {v["cur_m"]:+.1f}% vs 滚动 {v["cur_t"]:+.1f}%')
    print(f'写出 {OUT}（{os.path.getsize(OUT) / 1024:.1f} KB）')
    print(payload['headline'])


if __name__ == '__main__':
    main()
