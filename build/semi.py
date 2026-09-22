# -*- coding: utf-8 -*-
"""半导体组横截面（台积电 / 日月光 / 联发科 / 南亚科 / 联电 / 世芯 / 创意）—— 写出 data/semi.js。

═══════════════════════════════════════════════════════════════════════════
这是本仓口径最干净的一组横截面，理由要说清楚 —— 它决定了本页不做什么
═══════════════════════════════════════════════════════════════════════════
交易所那几张横截面页要先解决「这些数能不能放一起」：四种货币、张数与金额混着、
乘数是各所自选的产品设计参数，于是 `/exchanges12/` 要造一套定基名义额、
`/exchanges-apac/` 要锁基期汇率。**本页一样都不需要**：

  · 同一条法规 —— 台湾《证券交易法》要求上市公司**次月 10 日前**公告上月营收，
    七家公告的是同一个法定字段（合并营业收入净额），不是七种自选口径；
  · 同一个单位 —— 七家的 MOPS 申报货币都是新台币；
  · 同一个节奏 —— 七家的 LAG 落在次月第 7–15 天（`build/roster.py`），
    没有哪一家要等季报才出数。

**所以本页不折汇率，一个字都不折。** 七条线都以新台币计量，折美元只是把同一个常数
乘进每一条线 —— 增长率一点不变，却让读者以为这里做过汇率处理。
（唯一的例外是世芯，它的功能货币是美元，新台币栏是逐月折算值；见下面「世芯」那一段。）

⚠ 顺带一条**本页不能有的东西**：`series/fx.csv` 里**根本没有新台币**（那张表是 10 个
币种：AUD/BRL/CAD/CHF/EUR/GBP/HKD/JPY/SEK/SGD）。全仓唯一的 NTD/USD 序列是
`series/tsm_fx.csv`，由 `fetch/tsm.py` 维护。本页一条汇率都不用，所以两张表都不读 ——
写在这里是因为「横截面页要折汇率」是从别的横截面页继承来的**错误直觉**，
下一个人多半会先去找 `fx.csv` 里的 TWD，然后找不到。

═══════════════════════════════════════════════════════════════════════════
**本页不做跨家加总，一次都不做** —— 与 `/exchanges-apac/` 不画份额是同一类判断
═══════════════════════════════════════════════════════════════════════════
亚太那页不画份额，是因为四家法域隔离、不在同一个池子里抢单，分母只能是自己圈的。
本页的理由不同，而且更硬：**这七家在同一条价值链的不同层，相加是重复计算。**

    设计            联发科（SoC）、世芯 / 创意（ASIC 设计服务）
    代工            台积电（先进制程）、联电（成熟制程）
    封装测试        日月光
    存储            南亚科

世芯与创意的一颗 ASIC，设计费记在它们的营收里，晶圆再向台积电下单、记进台积电的营收，
封测再交给日月光、记进日月光的营收 —— **同一颗芯片在这张表里至少被数三次**。
所以本页上不会出现「半导体组合计」「七家总营收」「谁占几成」，一个都没有。
首页那条「不做跨家加总」的总规矩（`index.html` 第 2 条）在这一组上不是量纲问题，
是**重复计算**问题；两种理由不一样，别互相替换。

⇒ 能问的是两类问题，本页只画这两类：
  ① **谁在长**（指数化、同比、离散度）—— 增长率不需要加总；
  ② **同一个月各家差多少**（同比矩阵、最新月横比）—— 比的是率，不是份额。

═══════════════════════════════════════════════════════════════════════════
世芯（alchip）：唯一一家新台币栏是折算值的
═══════════════════════════════════════════════════════════════════════════
`build/mrspecs/alchip.py` 把它的**美元**栏定为 `value`（功能货币实绩，MOPS 官方栏），
新台币栏放进 `alt` 且 `summable=False` —— 各月用各月的换算汇率，十二个月相加
不等于官方本年累计。

本页仍然取它的**新台币栏**，理由与那一页不冲突：
  · 那一页要做季度桥 / QTD / YTD / TTM，全部依赖**可加总**，所以只能用美元栏；
  · 本页只做同比与指数化，**两者都不需要加总**，需要的是七家同一个计量货币。
  · 而且新台币栏是它**按法规申报**的那个数 —— 台湾市场看到的就是这个数。
⇒ 取新台币栏是对的，但它与另外六家**不是同一种数**（那六家是原生记账数）。

**这件事有多大，本轮实测过，答案是「小」** —— 所以它是页尾的一条说明，不是一张图。
本文件里一个数都不写死，全由 `alchip_fx_facts()` 在构建期现算：窗口两端的累计口径下，
世芯新台币增长里汇率那一份只占**很小一块**（对数分解），其余是经营。
⚠️ 但**有一个数不许印：新台币同比与美元同比之差的 pp**。世芯同比到 +200% 以上时，
那个差会印出二十几 pp，看上去像一场灾难，而当月汇率其实只动了个位数百分比 ——
pp 差随增速水平放大，是个**度量假象**。尺度无关的写法只有一个，且恒等于汇率同比：
    (1 + y_新台币) ÷ (1 + y_美元) − 1 ≡ 汇率同比
页尾那条说明印的就是它（`alchip_fx_facts()` 每轮复验这个恒等式，对不上就硬失败）。

═══════════════════════════════════════════════════════════════════════════
口径断点：**从各家自己的 spec 现读，本文件不抄一条**
═══════════════════════════════════════════════════════════════════════════
`/wealth/` 那页把 LPL 的并购表抄了一份在自己文件里，然后写了个 `_sync_lpla()`
每次构建对着 `build/lpla.py` 复核 —— 因为「改一处要改两处」这句话拦不住任何东西。
本页不抄：`BREAKS` 直接 `import mrspecs.<t>` 读 `SPEC['breaks']`（见 `load_breaks()`），
七家的断点登记表只有一份，**结构上不可能分叉**。
单公司页加一条断点，本页下一次构建就跟着有；删一条也一样。

⚠ 横截面页的断点标签**必须点名公司**：单公司页上整幅红线天然只指那一家，
本页七条线并排，不点名会被读成「七家在这里都换了口径」（同 `build/wealth.py` 的注释）。

═══════════════════════════════════════════════════════════════════════════
共同最新月与窗口
═══════════════════════════════════════════════════════════════════════════
· **发布门槛取共同最新月**，不是各家自己的最新月 —— 否则末端那几个月的「谁强谁弱」
  全是披露时点造成的假象。短板是谁、它自己更新到哪个月，由页面现算印出来。
· **序列起点七家不同**（世芯 2014-01 / 南亚科 · 联电 2013-01 / 台积电 · 联发科 ·
  创意 2016-01 / 日月光 2018-05），而日月光那个起点是**口径起点**不是「最早可得」：
  控股公司 2018-04-30 才成立，更早的月报属于前身主体（`build/mrspecs/ase.py`【1】）。
  ⇒ 七家共同覆盖的窗口从 2018-05 起。指数化基期取 **2019-01**（全仓唯一基期，
  = `build/notional.py` 的 BASE_MONTH），不取 2018-05：基期落在农历年之外的普通月份，
  七条线的起跑线才不带一次性的春节错位。

数据源（只读 series/*.csv，不下载、不写回）：
  series/tsm.csv / ase.csv / mtk.csv / nanya.csv / umc.csv / alchip.csv / guc.csv

用法: python3 build/semi.py   （可重复跑，除首行构建日期外逐字节相同）
成员没齐（CSV 缺失 / 缺列 / 全空）就打印原因并以**退出码 0** 结束 ——
`monthly_run.build_cross()` 会在成员齐了之后重跑，那不是失败。
"""
import datetime
import importlib
import os
import sys

import numpy as np
import pandas as pd

import axisfmt                     # 轴刻度格式的 Python 侧复算，只调用不修改
import exhibits                    # 图号：ORDER 定图序、正文 ⟨ex:…⟩ 占位符
import brief as B                  # 页顶 brief 的规则库（只算事实、不产文字）
import glossary as gloss           # 名词释义的版式层与护栏，全站共用
import mrwin                       # 窗口/排版的边界裁决层（DENSE 集合、layout_all），只调用不改
import payload_guard
import pctile                      # 3Y %ile 的唯一实现（CONTRACT §2）
import yoy as YOY                  # 同比口径的唯一实现（build/yoy.py），不自己写 pct_change(12)
#  ⚠ 模块别名是 YOY（大写），逐家算好的同比字典叫 **YOYS**（多一个 s）。
#    两者只差一个字母是刻意的 —— 但**不许把字典也叫 YOY**：那会把模块整个盖掉，
#    而 yoy_on() 在函数体里按名字查 YOY.mom_yoy，盖掉之后是运行期才炸的
#    AttributeError（同 build/exchanges_apac.py 文件头对 `import yoy` 的那条警告）。

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')

TICKER = 'semi'
OUT = os.path.join(ROOT, 'data', f'{TICKER}.js')
PAGE_DIR = os.path.join(ROOT, TICKER)

SRC = ('Source: 七家公司按台湾《证券交易法》公告的月度合并营收（MOPS 月营收申报表 / '
       '公司 IR 月度新闻稿 / SEC 6-K）；format after Goldman Sachs GIR')

BASE_M = '2019-01'        # 指数化基期（全仓唯一基期，= build/notional.py BASE_MONTH）
WIN_SHORT = 25            # 短窗口（近两年）x 轴
LINE_H = 360              # 开了 end_label 的长历史线图必须 ≥360（docs/CHART_KINDS.md §3.9）
TBL_MONTHS = 13           # 末尾核对表的行数
HEAT_MONTHS = 30          # 同比矩阵的列数

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# ────────────────────────────── 成员表 ──────────────────────────────
# (ticker, 页面显示名, 台股代号, 价值链层, 层内细分, 颜色)
#
# **显示名与代号都印在页面上**，所以两件事要说准：
#   · 日月光的 slug 是 `ase`，NYSE ADR 代号恰好叫 ASX —— 而 `asx` 在本仓已经是
#     ASX Limited（澳交所）。写串会同时污染两张页，且是静默污染（图照出、数全错）。
#     本页一律用台股代号（3711），不用 ADR 代号。
#   · **「价值链层」是本页的编辑分类，不是从任何一份申报里抄来的事实。**
#     它只用来分组、排序与讲解，**不参与任何一个数的计算**；汇总表的分隔条与页尾
#     说明都会点明这一点。公司自己不按这个分法披露，所以它也不该被当成口径。
# ⚠ **颜色：引擎只有 6 个数据色，本页有 7 家 —— 这不是配色偏好问题，是结构约束。**
#   `assets/charts.js` 的数据色是 NAVY / BLUE / MBLUE / GRAY / GREEN / GOLD 六个；
#   RED 是断点竖线与越界标记专用，不做数据色（`build/single.py` / `build/pools.py` 同）。
#   写一个引擎不认得的色名不会报错，会**静默退回 NAVY**（charts.js 的 col()）。
#   `build/exchanges12.py` 为同一件事定过规矩：**任何一张图都不许出现第 7 条线**，
#   成员多于六家时身份一律靠**标签**承载（heat_matrix 的行名 / grouped_bars 的 x 标签）。
#   ⇒ 本页因此有两条硬规则，下面的 `SIDE` 与 `selfcheck_colors()` 各管一条：
#     ① 七家同时出现的图**只用 heat_matrix 或 x 轴身份的柱图**，不用折线；
#     ② 折线图按 `SIDE` 拆成两半（制造 4 家 / 设计 3 家），于是 GOLD 可以在两半里
#        各用一次（日月光 / 创意）—— 两家**从不同框**，由 selfcheck_colors() 每轮验。
MEMBERS = [
    # ticker    名称      代号    价值链层        层内细分    颜色     制造/设计
    ('tsm',    '台积电',  '2330', '晶圆代工',      '先进制程', 'NAVY',  '制造'),
    ('umc',    '联电',    '2303', '晶圆代工',      '成熟制程', 'MBLUE', '制造'),
    ('ase',    '日月光',  '3711', '封装测试',      'OSAT',     'GOLD',  '制造'),
    ('nanya',  '南亚科',  '2408', '存储',          'DRAM',     'GRAY',  '制造'),
    ('mtk',    '联发科',  '2454', 'IC 设计',       'SoC',      'GREEN', '设计'),
    ('alchip', '世芯',    '3661', 'ASIC 设计服务', '世芯-KY',  'BLUE',  '设计'),
    ('guc',    '创意',    '3443', 'ASIC 设计服务', '创意电子', 'GOLD',  '设计'),
]
KEYS = [k for k, *_ in MEMBERS]
NAME = {k: n for k, n, *_ in MEMBERS}
CODE = {k: c for k, _n, c, *_ in MEMBERS}
LAYER = {k: l for k, _n, _c, l, *_ in MEMBERS}
SUBLAYER = {k: s for k, _n, _c, _l, s, *_ in MEMBERS}
COLOR = {k: c for k, _n, _c, _l, _s, c2, *_ in MEMBERS for c in [c2]}
SIDE = {k: s for k, _n, _c, _l, _sl, _col, s in MEMBERS}
#: 价值链层 → 成员，保持 MEMBERS 的先后。汇总表与「按层」的图都照它分组。
LAYERS = list(dict.fromkeys(LAYER[k] for k in KEYS))
BY_LAYER = {ly: [k for k in KEYS if LAYER[k] == ly] for ly in LAYERS}
#: 折线图的两半。**这不只是版面分组，它是一条业务轴**：左边四家自有产能（晶圆厂 /
#: 封测厂 / DRAM 厂），投的是资本支出，周期跟着产能与稼动率走；右边三家没有厂，
#: 接的是设计案，周期跟着客户的设计定案与量产爬坡走。两条周期不同步 ——
#: 这正是本页要给读者看的东西，所以按它拆图不是迁就调色板，是照业务分。
SIDES = ['制造', '设计']
BY_SIDE = {s: [k for k in KEYS if SIDE[k] == s] for s in SIDES}
#: 页面上点名一家时的统一写法，七处以上在用 —— 不要各写各的。
DISP = {k: f'{NAME[k]}（{CODE[k]}）' for k in KEYS}


def skip(msg):
    """成员没齐：打印原因并以退出码 0 结束（见模块 docstring 末段）。"""
    print(f'{TICKER}: 未生成 —— {msg}')
    sys.exit(0)


# ─────────────────────── 口径断点：现读各家的 spec ───────────────────────
def load_breaks():
    """→ [(Period, ticker, 断点说明)]，按月份排序。**本文件不抄任何一条断点。**

    单公司页的断点登记在 `build/mrspecs/<t>.py` 的 `SPEC['breaks']`（一条 = 一次
    可查证的公司行为：并表 / 出表 / 追溯重述）。本页直接 import 那七个模块现读，
    于是两边**结构上不可能分叉** —— `/wealth/` 那页靠 `_sync_lpla()` 每轮复核抄来的
    副本，是因为它抄了；本页不抄就不需要复核。

    import 失败 / 没有 SPEC / breaks 形状不对一律**抛异常**，不吞：
    断点少画一条的后果是页面上一段不可比的序列被读成连续的，
    而这种错误在图上完全看不出来（同 CONTRACT §5.2）。
    """
    out = []
    for k in KEYS:
        mod = importlib.import_module(f'mrspecs.{k}')
        spec = mod.SPEC                                  # 没有 SPEC → AttributeError，要的就是它
        for b in (spec.get('breaks') or []):
            if not isinstance(b, dict) or 'month' not in b or 'zh' not in b:
                raise SystemExit(f'build/semi: mrspecs/{k}.py 的 breaks 里有一条缺 '
                                 f'month/zh：{b!r}')
            out.append((pd.Period(str(b['month']), 'M'), k, str(b['zh'])))
    return sorted(out, key=lambda r: (r[0], KEYS.index(r[1])))


BREAKS = load_breaks()


def brk_in(idx, keys=None):
    """落在某张图横轴 `idx` 上的断点 → (break_at 下标, 竖排标签, 明细句子)。

    · 标签点名公司（横截面页的硬规矩，见模块 docstring）。同一个月有两家断点时
      合成一条线、标签并写 —— 引擎按 x 下标画线，同一格画两次只会叠在一起。
    · **`keys` 必须是这张图真正画了的那几家。** 本页的折线图按 SIDE 拆成两半，
      在制造侧那张上画联发科的断点，等于指着一条图上没有的线说「这里不可比」——
      读者只能把它按到旁边某一条上去。派生量的图（极差）传 KEYS 全员，
      并在图注里说明那是成员的断点传导进来的。
    """
    ks = set(KEYS if keys is None else keys)
    pos = {p: i for i, p in enumerate(idx)}
    hit = {}
    for p, k, _zh in BREAKS:
        if p in pos and k in ks:
            hit.setdefault(pos[p], []).append(k)
    at = sorted(hit)
    labels = ['／'.join(NAME[k] for k in hit[i]) for i in at]
    detail = [f'{DISP[k]} {p}：{zh}' for p, k, zh in BREAKS if p in pos and k in ks]
    return at, labels, detail


def brk_note(idx, keys=None,
             lead='<b>红色竖虚线 = 口径断点</b>，线右侧与左侧不可直接连比：'):
    """图注里那句断点说明。**图上没有线就不出这句话** —— 断点滚出窗口时线与文案
    一起消失，不会剩下一句假话（同 build/wealth.py 的 brk_note）。"""
    at, _lab, detail = brk_in(idx, keys)
    return (lead + '；'.join(detail) + '。') if at else ''


# ────────────────────────────── 读数据 ──────────────────────────────
def read_csv(name):
    p = os.path.join(SERIES, name)
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p)
    if 'month' not in df.columns:
        return None
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    return df.set_index('month').sort_index()


def ntd_col(spec):
    """一家的**新台币**月营收列名 —— 从它自己的 spec 里认，不在本文件写死列名。

    六家的 `value.col` 就是新台币列；世芯的 `value.col` 是美元列（功能货币），
    新台币列在 `alt.col` 里（理由见模块 docstring「世芯」那一段）。
    两处都不是新台币列就**硬失败**：本页的全部前提是「七家同一个计量货币」，
    默默换一个列等于把那个前提悄悄取消掉。
    """
    for node in (spec.get('value'), spec.get('alt')):
        col = (node or {}).get('col')
        if col and col.endswith('_ntd_mn'):
            return col
    return None


RAW, NTDCOL, LATEST_EACH, MISSING = {}, {}, {}, []
for _k in KEYS:
    _spec = importlib.import_module(f'mrspecs.{_k}').SPEC
    _df = read_csv(_spec['csv'])
    _col = ntd_col(_spec)
    if _df is None or _col is None or _col not in _df.columns:
        MISSING.append(f'{_k}（{_spec.get("csv")} 缺失或没有新台币列）')
        continue
    _s = pd.to_numeric(_df[_col], errors='coerce').dropna()
    if _s.empty:
        MISSING.append(f'{_k}（{_col} 全空）')
        continue
    RAW[_k], NTDCOL[_k], LATEST_EACH[_k] = _df, _col, _s.index[-1]

if MISSING:
    skip('成员未就绪：' + '、'.join(MISSING))

# 共同最新月 = 七家里最慢的那家（见模块 docstring）。
LATEST = min(LATEST_EACH.values())
LAGGARD = [k for k in KEYS if LATEST_EACH[k] == LATEST]
AHEAD = [(k, LATEST_EACH[k]) for k in KEYS if LATEST_EACH[k] > LATEST]
#: 七家共同覆盖的最早月（= 起点最晚那家的起点）。
START = max(pd.to_numeric(RAW[k][NTDCOL[k]], errors='coerce').dropna().index[0] for k in KEYS)
BASE = pd.Period(BASE_M, 'M')
if BASE < START:
    skip(f'指数化基期 {BASE_M} 早于七家共同起点 {START}')
if LATEST <= BASE:
    skip(f'共同最新月 {LATEST} 不晚于基期 {BASE_M}')

#: 各家新台币月营收，**NT$bn**，截到共同最新月（各家自己的起点保留，前段是 NaN）。
NTD = {k: (pd.to_numeric(RAW[k][NTDCOL[k]], errors='coerce') / 1000.0).loc[:LATEST]
       for k in KEYS}
IDX_ALL = pd.period_range(min(NTD[k].dropna().index[0] for k in KEYS), LATEST, freq='M')
#: 七家都有值的窗口（本页多数图的横轴）。
IDX = pd.period_range(START, LATEST, freq='M')
IDX_SHORT = IDX[-WIN_SHORT:]
CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12


def s_on(k, idx):
    """某家的 NT$bn 序列对齐到给定横轴（缺月 → NaN）。"""
    return NTD[k].reindex(idx)


def yoy_on(k, idx):
    """某家的**单月**同比（%），对齐到给定横轴。

    口径与全站唯一实现一致（`build/yoy.py` 的 mom_yoy + FLOW）：月营收是流量。
    ⚠ 不在这里写 `pct_change(12)` —— CONTRACT §6 要求同比只有一处实现。
    """
    return YOY.mom_yoy(NTD[k], YOY.FLOW).reindex(idx)


# ────────────────────────────── 格式化零件 ──────────────────────────────
def mlab(p):
    return f'{MONTHS[p.month - 1]}-{p.year % 100:02d}'


def zh(p):
    return f'{p.year} 年 {p.month} 月'


def _fin(v):
    return v is not None and np.isfinite(v)


def num(v, d=1):
    """千分位定点。负零不许从任何一条支路漏出去（'-0.0' 在页面上是个假信号）。"""
    if not _fin(v):
        return '—'
    v = 0.0 if abs(v) < 0.5 / 10 ** d else v
    return f'{v:,.{d}f}'


def pct(v, d=1, sign=True):
    """百分比。正负号交给 f-string 的 + 标志 —— 别写死字面量（CONTRACT §1）。"""
    if not _fin(v):
        return '—'
    v = 0.0 if abs(v) < 0.5 / 10 ** d else v
    return f'{v:+.{d}f}%' if sign else f'{v:.{d}f}%'


def pp(v, d=1):
    if not _fin(v):
        return '—'
    v = 0.0 if abs(v) < 0.5 / 10 ** d else v
    return f'{v:+.{d}f}pp'


def L(a):
    """np.nan → None（JSON 的 null）。CONTRACT §5.5：payload 里不许出现 NaN。"""
    return [None if not _fin(v) else float(v) for v in a]


def cls_of(v):
    """涨跌色跟着**印出来的那个数**走：印成 +0.0% 就不涂色，否则读者会看到一个
    绿色的零，以为是四舍五入吃掉了一个正数（同 build/wealth.py 的 chg）。"""
    if not _fin(v):
        return ''
    return 'pos' if round(v, 1) > 0 else ('neg' if round(v, 1) < 0 else '')


def ser(s):
    """pandas Series → pctile.py 吃的 [float | None]（按月升序，缺月 None）。"""
    return [None if not np.isfinite(v) else float(v) for v in s.values]


def spanl(a, b):
    return f'{mlab(a)}–{mlab(b)}'


# ─────────────────────── Exhibit 1：汇总表 ───────────────────────
def _mm(k):
    """环比（%）。月营收是流量，环比就是相邻两格相除，没有第二种口径。"""
    a, b = NTD[k].get(CUR), NTD[k].get(PRV)
    return (a / b - 1.0) * 100.0 if _fin(a) and _fin(b) and b else np.nan


def _yy(k):
    """单月同比（%）—— 与页上每一条同比线同源（yoy.mom_yoy + FLOW）。"""
    s = yoy_on(k, IDX)
    return float(s.loc[CUR]) if CUR in s.index and _fin(s.loc[CUR]) else np.nan


#: 逐家的 3Y 分位（值, 颜色类）。**不只是表里的一格** —— 汇总表的 note 要按它现算
#: 一句话：七家同时顶到 100 是个真事实（当月是各自近 36 个月的最高），不是坏掉的列。
#: 判「这一列有没有区分度」的是 build/pctile.py 的 24 个月回放（≥70% 钉在端点才算死列），
#: 本轮七家实测 8%–54%，都没到，所以这一列是活的，不能按 CONTRACT §2 那条留空。
PCTS = {}
SUM_ROWS = []
for _ly in LAYERS:
    SUM_ROWS.append({'kind': 'group', 'label': _ly})
    for _k in BY_LAYER[_ly]:
        _p, _c = pctile.cell(ser(NTD[_k].reindex(IDX)))
        PCTS[_k] = (_p, _c)
        SUM_ROWS.append({'label': f'{NAME[_k]} {CODE[_k]}', 'cells': [
            {'v': num(NTD[_k].get(CUR), 1)},
            {'v': num(NTD[_k].get(PRV), 1)},
            {'v': num(NTD[_k].get(YAG), 1)},
            {'v': pct(_mm(_k)), 'cls': cls_of(_mm(_k))},
            {'v': pct(_yy(_k)), 'cls': cls_of(_yy(_k))},
            {'v': _p, 'cls': _c} if _p else {'v': ''},
        ]})

#: 页面上多处要说「整页截到哪个月、被谁卡住」，一律取这一句，不要各写各的。
GATE_TXT = (f'本页所有图统一截到<b>共同最新月 {mlab(LATEST)}</b>'
            + ('（七家本月都已公告）'
               if not AHEAD else
               '，由最慢的成员 ' + '、'.join(NAME[k] for k in LAGGARD) + ' 决定；'
               + '、'.join(f'{NAME[k]} 自身已到 {mlab(p)}' for k, p in AHEAD))
            + '。各家自己更新到哪个月，看首页卡片上的月份与红点。')


def _pctile_line():
    """3Y %ile 那一列如果整列顶格，说一句为什么 —— 现算，不是固定文案。

    七家同时印 100 看上去像列坏了。它其实是「当月是各自近 36 个月的最高值」，
    而这正是本月值得记一笔的事。下个月只要有一家掉下来，这句话自己就变了；
    一家都不在 100 时整句消失。
    """
    top = [k for k in KEYS if PCTS.get(k, ('', ''))[0] == '100']
    if len(top) == len(KEYS):
        return (f' <b>本月 {len(KEYS)} 家的分位同时是 100</b> —— '
                '当月营收都是各自近 36 个月里的最高值。这一列不是坏的：'
                '判「有没有区分度」的是近 24 个月的回放（几成月份钉在区间端点），'
                '七家都远没到那条线。')
    if top:
        return (f' 其中 {len(top)} 家（{"、".join(NAME[k] for k in top)}）的分位是 100，'
                '即当月是各自近 36 个月里的最高值。')
    return ''


SUMMARY = {
    'title': f'半导体组 —— {zh(CUR)}（共同最新月）月营收与增速',
    'heads': ['本月 NT$bn', '上月 NT$bn', '去年同月 NT$bn', 'm/m', 'y/y（单月）', '3Y %ile'],
    'sep': 3,
    'rows': SUM_ROWS,
    'note': (GATE_TXT
             + ' 水平值是各家按台湾《证券交易法》公告的月度合并营收，'
             + f'本表换算成 NT$bn（原始单位 NT$mn，见末尾核对表）。'
             + 'y/y 是<b>单月同比</b>（当月 ÷ 去年同月 − 1），与页上每一条同比线同一口径；'
             + '3Y %ile 是近 36 个月百分位，区分度不足的行留空（判据与全站共用 '
             + '<code>build/pctile.py</code>）。'
             + '<b>分隔条上的「价值链层」是本页的编辑分类，不是公司的披露口径</b>，'
             + '不参与任何一个数的计算。'
             + '<b>本表没有合计行</b>：七家在同一条价值链的不同层，相加是重复计算，'
             # 不写「见页尾第 N 条」：notes 没有 exhibits 那套 id 机制，
             # 调一下顺序这个序号就成了假话，而且没有任何工具会报。
             + '理由见页尾「口径与方法说明」里讲价值链的那一条。'
             + _pctile_line()),
}


# ═══════════════════════════════════════════════════════════════════
# 派生量：全部在这里算完，页面不做任何计算（CONTRACT 抬头）
# ═══════════════════════════════════════════════════════════════════
#: 七家都算得出单月同比的最早月。日月光 2018-05 起才有序列，它的同比要等到
#: 2019-05；另外六家在 IDX 左端之前就有历史，同比从 IDX 左端就有。**不写死**。
YOYS = {k: yoy_on(k, IDX) for k in KEYS}
_ok = [p for p in IDX if all(_fin(YOYS[k].get(p)) for k in KEYS)]
if not _ok:
    skip('七家没有任何一个月同时算得出单月同比')
IDX_YOY = pd.period_range(_ok[0], LATEST, freq='M')
YOY_LATE = [k for k in KEYS if YOYS[k].dropna().index[0] == _ok[0]]

#: 指数化（基期 = 100）。**用 3 个月移动平均**：月营收带农历年与出货批次的
#: 块状噪声，原始月值的中位环比在 4%–13% 之间（逐家现算见 IDXNOTE），
#: 七条线叠在一起会糊成一团。3MMA 只平滑噪声，不动增长本身 ——
#: 指数末点的离散度几乎不变，这一点在图注里现算印出来，免得读者以为平滑掉了差距。
MA = 3


def rebased(k, idx, base=None):
    """某家以 BASE_M = 100 的指数（3MMA）。基期那一格必须恰好是 100 —— 由
    selfcheck_rebased() 每轮验（同 build/exchanges_apac.py 的 selfcheck_page）。"""
    s = NTD[k].rolling(MA, min_periods=MA).mean()
    b = s.get(base or BASE)
    if not _fin(b) or not b:
        return pd.Series(np.nan, index=idx)
    return (s / b * 100.0).reindex(idx)


IDX_REB = pd.period_range(BASE, LATEST, freq='M')
REB = {k: rebased(k, IDX_REB) for k in KEYS}

#: 原始月值的噪声有多大（图注用「为什么要 3MMA」的判据，现算不写死）。
NOISE = {k: float(NTD[k].pct_change().abs().median() * 100.0) for k in KEYS}


# ── 组内离散度：本页的核心实证 ────────────────────────────────────────
def _spread(keys, idx):
    """每月「这一组里最快的一家 − 最慢的一家」（pp）。"""
    m = pd.DataFrame({k: YOYS[k].reindex(idx) for k in keys})
    return (m.max(axis=1) - m.min(axis=1)).reindex(idx)


def _growing(idx):
    """每月「七家里有几家同比为正」。**对离群值免疫** —— 南亚科同比到三位数
    也只算一家，所以这条线量的是「分歧本身」，不是某一家的振幅。"""
    m = pd.DataFrame({k: YOYS[k].reindex(idx) for k in KEYS})
    n = (m > 0).sum(axis=1).astype(float)
    return n.mask(m.isna().any(axis=1)).reindex(idx)      # 有一家算不出就整月留空


GROW = _growing(IDX_YOY)
SPREAD_ALL = _spread(KEYS, IDX_YOY)
#: 「这个结论是不是只有存储在拉开」的对照组：去掉南亚科的六家。
KEYS_EXN = [k for k in KEYS if k != 'nanya']
SPREAD_EXN = _spread(KEYS_EXN, IDX_YOY)


def _split_pct(keys):
    """这一组里「有人涨、同时有人跌」的月份占比（%）。全员可算的月才计入。"""
    m = pd.DataFrame({k: YOYS[k].reindex(IDX_YOY) for k in keys})
    n = (m > 0).sum(axis=1).astype(float).mask(m.isna().any(axis=1)).dropna()
    return (float(((n > 0) & (n < len(keys))).mean() * 100.0), len(n)) if len(n) else (None, 0)


def _disp_facts():
    """离散度的判据数，全部现算。图注、brief、页尾说明都从这里取，不各算各的。

    ⚠ 名字叫 `DISPF` 不叫 `DISP` —— `DISP` 已经是「点名一家时怎么写」那张表了
    （见上面）。同名会把那张表整个盖掉，而它在七八处被引用。
    """
    g = GROW.dropna()
    n = len(g)
    if not n:
        return None
    same = int(((g == 0) | (g == len(KEYS))).sum())
    hard = int(((g >= 2) & (g <= len(KEYS) - 2)).sum())
    sa, se = SPREAD_ALL.dropna(), SPREAD_EXN.dropna()
    split_all, _ = _split_pct(KEYS)
    split_exn, _ = _split_pct(KEYS_EXN)
    return {
        'n': n, 'same': same, 'same_pct': same / n * 100.0,
        'split': n - same, 'split_pct': split_all,
        'hard': hard, 'hard_pct': hard / n * 100.0,
        'sp_med': float(sa.median()), 'sp_max': float(sa.max()),
        'sp_max_m': sa.idxmax(), 'sp_now': float(sa.iloc[-1]),
        'exn_med': float(se.median()) if len(se) else None,
        'exn_now': float(se.iloc[-1]) if len(se) else None,
        'exn_split_pct': split_exn,
    }


DISPF = _disp_facts()
if DISPF is None:
    skip('离散度算不出来（同比窗口为空）')


# ── 季节性指数：月值 ÷ 当年 12 个月均值，只取**共同窗口里的完整年** ──────────
def _season():
    """→ {ticker: {月份 1-12: 指数×100}}，以及实际用到的年份清单。

    只用完整日历年（12 个月齐）—— 半年会把季节形状算成「上半年低、下半年没有」。
    年份限定在**共同窗口之内**，七家用同一批年，否则「谁的高峰在几月」比的是
    各自不同的历史时段。
    """
    yrs = [y for y in range(IDX[0].year, LATEST.year + 1)
           if all(len(NTD[k].loc[f'{y}-01':f'{y}-12'].dropna()) == 12 for k in KEYS)]
    out = {}
    for k in KEYS:
        by = {m: [] for m in range(1, 13)}
        for y in yrs:
            s = NTD[k].loc[f'{y}-01':f'{y}-12']
            mean = float(s.mean())
            if not mean:
                continue
            for p, v in s.items():
                by[p.month].append(float(v) / mean * 100.0)
        out[k] = {m: (sum(v) / len(v) if v else None) for m, v in by.items()}
    return out, yrs


SEASON, SEASON_YRS = _season()


def _peak_trough(k):
    d = {m: v for m, v in SEASON[k].items() if _fin(v)}
    if not d:
        return None, None
    return max(d, key=d.get), min(d, key=d.get)


# ── 同比的两两相关：对角线留空 ────────────────────────────────────────
def _corr():
    m = pd.DataFrame({k: YOYS[k].reindex(IDX_YOY) for k in KEYS}).dropna()
    c = m.corr()
    return c, len(m)


CORR, CORR_N = _corr()


def _leadlag(anchor='tsm', span=6):
    """「谁领先谁」的判据 —— 算出来是为了**说明本页为什么不画这张图**。

    对每一家算 corr(X[t], anchor[t−k])，k ∈ [−span, +span]，取相关最高的 k。
    再把窗口对半切，看那个最佳 k 与它的相关在前后两半里稳不稳。

    页面上那句「不要读成领先滞后」引用的每一个数都从这里来，一个都不写死：
    写死的坏处不是难看，是**下个月它就可能不成立，而页面照印**。
    """
    m = pd.DataFrame({k: YOYS[k].reindex(IDX_YOY) for k in KEYS}).dropna()
    if len(m) < 24 or anchor not in m:
        return None
    half = len(m) // 2
    out, gains, flips = {}, [], 0
    for k in KEYS:
        if k == anchor:
            continue
        cs = {kk: float(m[k].corr(m[anchor].shift(kk))) for kk in range(-span, span + 1)}
        best = max(cs, key=cs.get)
        out[k] = {'best': best, 'r': cs[best], 'r0': cs[0], 'gain': cs[best] - cs[0]}
        gains.append(cs[best] - cs[0])
        r1 = float(m[k].iloc[:half].corr(m[anchor].iloc[:half]))
        r2 = float(m[k].iloc[half:].corr(m[anchor].iloc[half:]))
        out[k].update(r1=r1, r2=r2)
        if _fin(r1) and _fin(r2) and r1 * r2 < 0:
            flips += 1
    return {'per': out, 'anchor': anchor, 'span': span,
            'at0': [k for k, v in out.items() if v['best'] == 0],
            'gain_max': max(gains) if gains else None,
            'flips': flips, 'n_half': half}


LL = _leadlag()
_off = [float(CORR.loc[a, b]) for i, a in enumerate(KEYS) for b in KEYS[i + 1:]]
CORR_MED = float(np.median(_off)) if _off else np.nan
CORR_HI = max(((a, b, float(CORR.loc[a, b])) for i, a in enumerate(KEYS)
               for b in KEYS[i + 1:]), key=lambda r: r[2])
CORR_LO = min(((a, b, float(CORR.loc[a, b])) for i, a in enumerate(KEYS)
               for b in KEYS[i + 1:]), key=lambda r: r[2])


# ── 世芯的汇率那一份有多大：现算，且**只用尺度无关的写法** ────────────────────
def alchip_fx_facts():
    """→ dict 或 None。页尾那条说明用它，图上不出现。

    两件事：
      · `fxy` —— (1+新台币同比) ÷ (1+美元同比) − 1，**恒等于当月汇率同比**。
        这个恒等式每轮复验（`resid`），对不上就是数据出了问题，硬失败。
      · `share` —— 窗口两端的累计增长里，汇率占的对数份额。
    ⚠ **不返回 pp 差**，因为页面上不许印它（理由见模块 docstring「世芯」那一段）。
    """
    df = RAW.get('alchip')
    if df is None or 'revenue_usd_mn' not in df.columns:
        return None
    # ⚠ 两列都取**原始单位**（US$mn 与 NT$mn），不要用 NTD[] 那份 —— 它已经除过
    #   1000 变成 NT$bn，相除得到的「汇率」会小一千倍。比值类的量（同比之商、
    #   累计增长比）不受影响，**但 fx_a / fx_b 是要印出来的水平值**，差三个数量级。
    usd = pd.to_numeric(df['revenue_usd_mn'], errors='coerce').reindex(IDX).dropna()
    ntd = pd.to_numeric(df[NTDCOL['alchip']], errors='coerce').reindex(IDX).dropna()
    yn = YOY.mom_yoy(ntd, YOY.FLOW).reindex(IDX_YOY) / 100.0
    yu = YOY.mom_yoy(usd, YOY.FLOW).reindex(IDX_YOY) / 100.0
    fxy = ((1 + yn) / (1 + yu) - 1.0).dropna() * 100.0
    if not len(fxy):
        return None
    fx = (ntd / usd).dropna()                       # 公司申报的当月换算汇率
    fxy_direct = (fx / fx.shift(12) - 1.0).reindex(fxy.index) * 100.0
    resid = float((fxy - fxy_direct).abs().max())
    if not _fin(resid) or resid > 0.01:             # 0.01pp：远大于浮点噪声，远小于任何真实差异
        raise SystemExit(f'build/semi: 世芯的「两条同比之商 ≡ 汇率同比」不成立'
                         f'（最大残差 {resid:.4f}pp）—— 先查 series/alchip.csv')
    # 窗口 = **本页的共同窗口**，不是世芯自己的序列全长。页尾那句话里的两个月份
    # 读者要能在本页的图上找到；印一个 2014 年的起点等于引一段本页没画的历史。
    a, b = fx.index[0], fx.index[-1]
    g_ntd, g_usd = float(ntd.loc[b] / ntd.loc[a]), float(usd.loc[b] / usd.loc[a])
    g_fx = float(fx.loc[b] / fx.loc[a])
    share = (np.log(g_fx) / np.log(g_ntd) * 100.0) if g_ntd > 0 and np.log(g_ntd) else None
    return {'a': a, 'b': b, 'fx_a': float(fx.loc[a]), 'fx_b': float(fx.loc[b]),
            'fx_chg': (g_fx - 1) * 100.0, 'share': share,
            'now': float(fxy.iloc[-1]), 'absmax': float(fxy.abs().max()),
            'absmax_m': fxy.abs().idxmax(), 'absmean': float(fxy.abs().mean())}


ALFX = alchip_fx_facts()


# ═══════════════════════════════════════════════════════════════════
# 图序：挪图**只改 ORDER 这一张表**（机制见 build/exhibits.py 文件头）
# ═══════════════════════════════════════════════════════════════════
ORDER = [
    'yoy-heat',        # 七家 × 近 N 月 单月同比矩阵 —— 七家同框只能用它
    'growing-count',   # 每月七家里有几家在增长（对离群值免疫的分歧度量）
    'spread',          # 组内同比极差；含「去掉南亚科」的对照线
    'rebased-mfg',     # 制造侧指数化（基期 = 100）
    'rebased-design',  # 设计侧指数化
    'yoy-mfg',         # 制造侧单月同比（**不含南亚科**，理由见图注）
    'yoy-design',      # 设计侧单月同比
    'season-heat',     # 季节性指数矩阵：低谷都在农历年，高峰各不相同
    'corr',            # 单月同比的两两相关
]
_seq = iter(exhibits.Seq(k) for k in range(2, 99))
E_HEAT, E_GROW, E_SPREAD = next(_seq), next(_seq), next(_seq)
E_REB_M, E_REB_D, E_YOY_M, E_YOY_D = (next(_seq) for _ in range(4))
E_SEASON, E_CORR = next(_seq), next(_seq)
E_TABLE = next(_seq)
#: 建图时的号 → id。本轮没出的图不登记（ORDER 里列了却没生成的 id 由 exhibits 跳过）。
EX_ID = {E_HEAT: 'yoy-heat', E_GROW: 'growing-count', E_SPREAD: 'spread',
         E_REB_M: 'rebased-mfg', E_REB_D: 'rebased-design',
         E_YOY_M: 'yoy-mfg', E_YOY_D: 'yoy-design',
         E_SEASON: 'season-heat', E_CORR: 'corr'}

XL_ALL = [mlab(p) for p in IDX]
XL_YOY = [mlab(p) for p in IDX_YOY]
XL_REB = [mlab(p) for p in IDX_REB]
ex = []


def _lines(keys, idx, getter, **kw):
    """一组公司 → `lines` 的 series[]。

    **只用 `lines`，不用 `lines_endlabels`** —— 后者在 `mrwin.DENSE` 里：走
    Catmull-Rom 平滑，数组里有一个 null 就画出一条塌到零的假线，前导 null 还会
    撞上左端标签按 fmt 抛异常。本页的日月光同比比另外六家晚 12 个月起
    （它的序列 2018-05 才开始），天生带前导 null；`lines` 走非平滑折线，
    null 是断笔，正是要的。
    """
    return [{'name': f'{NAME[k]}（{CODE[k]}·{SUBLAYER[k]}）', 'color': COLOR[k],
             'values': L(getter(k).reindex(idx).values)} for k in keys]


def _axis_owner(keys, idx, series_of):
    """谁把纵轴撑开了、撑开多少 —— 现算一句话（同 build/wealth.py 的 _cash_axis_txt）。"""
    last = {k: float(series_of(k).reindex(idx).dropna().iloc[-1])
            for k in keys if len(series_of(k).reindex(idx).dropna())}
    if len(last) < 2:
        return ''
    hi = max(last, key=last.get)
    lo = min(last, key=last.get)
    return (f'<b>纵轴由{NAME[hi]}定</b>：{mlab(idx[-1])} 它是{NAME[lo]}的 '
            f'{last[hi] / last[lo]:.1f} 倍，另外几条因此挤在下半幅 —— '
            f'读这张图请看<b>斜率</b>（谁在加速），不要按线的高低读「谁更大」，'
            f'水平值在 Exhibit 1 的汇总表里。')


# ── ⟨ex:yoy-heat⟩ 七家 × 近 N 月：单月同比矩阵 ────────────────────────────
_HM = list(IDX_YOY[-HEAT_MONTHS:])
ex.append({
    'n': E_HEAT, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pct0z',
    'title': f'七家的单月同比，近 {len(_HM)} 个月（%）—— 同一个月里各家差得有多远',
    'rows': [f'{NAME[k]} {CODE[k]}' for k in KEYS],
    'cols': [mlab(p) for p in _HM],
    'matrix': [L(YOYS[k].reindex(_HM).values) for k in KEYS],
    'legend': '月营收 单月同比（%）',
    'cell_h': 24, 'row_lab_w': 104, 'row_head': '公司',
    'src_extra': '同比口径 = 单月（当月 ÷ 去年同月 − 1），全站唯一实现 build/yoy.py。',
    'note': (
        '<b>七家唯一能同框的图型就是它。</b>引擎只有 6 个数据色，七条折线画不出来；'
        '更要紧的是<b>七家的同比不在一个量级上</b> —— '
        f'{DISP["nanya"]}这样的存储周期，单月同比可以到三位数，'
        '而晶圆代工是个位数到两位数。把它们放进同一根线性纵轴，'
        '代工那几条会被压成一条直线（这一条是南亚科自己那页定的读法，'
        '见 <code>/nanya/</code>「这是一条存储器周期序列」）。'
        '矩阵按<b>格子</b>着色，不共用一根纵轴，所以不受这个限制。'
        '<br><b>色标是本图自己的 5/95 分位</b>（引擎的 heatScale）：极端月份会顶到色阶两端、'
        '不会把其余格子的分辨率吃掉，但也因此<b>两张矩阵之间颜色不可比</b>，'
        '别拿本图的红跟下面季节性那张的红对照。'
        + (f'<br>{DISP["ase"]}的同比从 {mlab(IDX_YOY[0])} 起才有：'
           '它的序列 2018-05 才开始（控股公司 2018-04-30 才成立，更早的月报属于前身主体，'
           '不可前接），再往前一年才凑得出分母。' if 'ase' in YOY_LATE else '')),
})

# ── ⟨ex:growing-count⟩ 每月有几家在增长 ──────────────────────────────────
_g_now = int(GROW.dropna().iloc[-1])
ex.append({
    'n': E_GROW, 'kind': 'bars_labeled', 'full': True, 'height': 280,
    'fmt': 'f0', 'label_fmt': 'f0',
    'title': (f'「半导体」不是一个周期：{len(KEYS)} 家里当月同比为正的有几家'
              f'（{mlab(CUR)}：{_g_now} 家）'),
    'xlabels': XL_YOY, 'ylab': f'同比为正的家数（0–{len(KEYS)}）',
    'values': L(GROW.values),
    # ⚠ **不要给这张图 annot。** bars_labeled 的 annot 画在图的左上角，而本图的柱
    #   顶到 7（七家全涨）时柱顶数值标签正好落在同一块地方 —— visual_qa 实测
    #   「7」与 annot 压字 15.3px²。那条信息在下面的 note 里已经有了，
    #   同一句话不必在图上再占一次位置。
    'src_extra': (f'窗口 {spanl(IDX_YOY[0], LATEST)}，{DISPF["n"]} 个月；'
                  '每月要七家都算得出单月同比才计入，否则整月留空。'),
    'note': (
        f'<b>{DISPF["n"]} 个月里，七家同向（全涨或全跌）的只有 {DISPF["same"]} 个月，'
        f'占 {DISPF["same_pct"]:.0f}%。</b>'
        f'反过来说 <b>{DISPF["split_pct"]:.0f}% 的月份里，有人在涨的同时有人在跌</b>；'
        f'其中 {DISPF["hard"]} 个月（{DISPF["hard_pct"]:.0f}%）是至少两家涨、'
        '同时至少两家跌的「硬分歧」。'
        '<br>这条线<b>对离群值免疫</b>：南亚科同比到三位数也只算一家，'
        '所以它量的是分歧本身，不是某一家的振幅 —— '
        f'⟨ex:spread@+1:下一张图⟩把幅度单独画出来。'
        + (f'<br><b>这个结论不是存储一家撑起来的</b>：去掉{NAME["nanya"]}'
           f'之后，剩下六家仍有 {DISPF["exn_split_pct"]:.0f}% 的月份涨跌不同向。'
           if DISPF['exn_split_pct'] is not None else '')),
})

# ── ⟨ex:spread⟩ 组内同比极差 ────────────────────────────────────────────
ex.append({
    'n': E_SPREAD, 'kind': 'lines', 'full': True, 'height': LINE_H,
    'fmt': 'f0', 'label_fmt': 'f0', 'yfmt': 'f0',
    'title': (f'当月最快的一家比最慢的一家高出多少（pp）—— 中位 '
              f'{DISPF["sp_med"]:.0f}pp，{mlab(CUR)} 为 {DISPF["sp_now"]:.0f}pp'),
    'xlabels': XL_YOY, 'ylab': '单月同比的组内极差（pp）',
    'zero_base': True, 'end_label': True,
    'series': [
        {'name': f'{len(KEYS)} 家', 'color': 'NAVY', 'values': L(SPREAD_ALL.values)},
        {'name': f'{len(KEYS_EXN)} 家（不含{NAME["nanya"]}）', 'color': 'GRAY',
         'values': L(SPREAD_EXN.values)},
    ],
    'src_extra': '极差 = 当月七家单月同比的最大值 − 最小值，单位是百分点（pp），不是百分比。',
    'note': (
        f'峰值 <b>{DISPF["sp_max"]:.0f}pp</b> 出现在 {mlab(DISPF["sp_max_m"])}。'
        f'灰线是去掉{NAME["nanya"]}的对照：中位仍有 '
        f'<b>{DISPF["exn_med"]:.0f}pp</b>'
        f'（{mlab(CUR)} {DISPF["exn_now"]:.0f}pp）—— '
        '即「同期各家增速相差几十个百分点」不靠存储周期也成立。'
        '<br><b>这是 pp 不是 %。</b>两条同比之差只能用百分点：'
        '把「+50% 与 +10%」说成「高 5 倍」会随基数变，说成「高 40pp」不会。'
        # 本图是七家的**派生量**，图上没有任何一家自己的线 —— 所以断点说明的引导语
        # 不能照抄默认那句（默认那句在读者眼里指的是「这条线在这里断了」）。
        + (('<br>' + brk_note(
            IDX_YOY,
            lead='<b>红色竖虚线 = 某一位成员的口径断点</b>，它会经由那一家的同比传导进本图的极差：'))
           if brk_in(IDX_YOY)[0] else '')),
    **({'break_at': brk_in(IDX_YOY)[0], 'break_label': brk_in(IDX_YOY)[1]}
       if brk_in(IDX_YOY)[0] else {}),
})

# ── ⟨ex:rebased-mfg⟩ / ⟨ex:rebased-design⟩ 指数化 ────────────────────────
_NOISE_TXT = '、'.join(f'{NAME[k]} {NOISE[k]:.0f}%' for k in KEYS)
for _e, _side in ((E_REB_M, '制造'), (E_REB_D, '设计')):
    _ks = BY_SIDE[_side]
    _lastv = {k: float(REB[k].dropna().iloc[-1]) for k in _ks if len(REB[k].dropna())}
    _rank = sorted(_lastv, key=_lastv.get, reverse=True)
    ex.append({
        'n': _e, 'kind': 'lines', 'full': True, 'height': LINE_H,
        'fmt': 'f0', 'label_fmt': 'f0', 'yfmt': 'f0',
        'title': (f'{_side}侧：月营收指数（{mlab(BASE)} = 100，{MA} 个月移动平均）'
                  f'—— {mlab(CUR)} 领先的是{NAME[_rank[0]]}（{_lastv[_rank[0]]:.0f}）'),
        'xlabels': XL_REB, 'ylab': f'指数（{mlab(BASE)} = 100）',
        'zero_base': True, 'end_label': True,
        'series': _lines(_ks, IDX_REB, lambda k: REB[k]),
        'src_extra': (f'各家自己的新台币月营收，{MA} 个月移动平均后以 {mlab(BASE)} 为 100 '
                      '重定基。指数只反映<b>各家自己</b>的增长，条与条之间不做加总。'),
        'note': (
            f'<b>为什么是 {MA} 个月移动平均</b>：原始月值的中位环比在 '
            f'{min(NOISE.values()):.0f}%–{max(NOISE.values()):.0f}% 之间'
            f'（逐家：{_NOISE_TXT}），农历年与出货批次把线打得很碎。'
            '移动平均只压噪声，压不掉增长 —— 末点的离散度几乎不变。'
            f'<br><b>基期取 {mlab(BASE)}</b>（全仓统一基期）而不是七家共同起点 '
            f'{mlab(START)}：后者是二月，正撞农历年，'
            '拿一个当月本来就偏低的月份当 100，会让每条线的起跑都被垫高一截。'
            f'<br>{_axis_owner(_ks, IDX_REB, lambda k: REB[k])}'
            + (('<br>' + brk_note(IDX_REB, _ks)) if brk_in(IDX_REB, _ks)[0] else '')),
        **({'break_at': brk_in(IDX_REB, _ks)[0], 'break_label': brk_in(IDX_REB, _ks)[1]}
           if brk_in(IDX_REB, _ks)[0] else {}),
    })

# ── ⟨ex:yoy-mfg⟩ / ⟨ex:yoy-design⟩ 单月同比 ──────────────────────────────
# ⚠ 制造侧那张**不含南亚科**。这不是版面取舍，是 /nanya/ 那页自己定的读法：
#   「这里的『增速』在量级上不能跟晶圆代工或交易所那种个位数增长同框比较」
#   （build/mrspecs/nanya.py 的 _CYCLE_NOTE，本页不抄那句话、只遵守它）。
#   南亚科在 ⟨ex:yoy-heat⟩ 与 ⟨ex:growing-count⟩ 里都在，那两张不共用线性纵轴。
YOY_EXCLUDE = {'nanya'}
for _e, _side in ((E_YOY_M, '制造'), (E_YOY_D, '设计')):
    _ks = [k for k in BY_SIDE[_side] if k not in YOY_EXCLUDE]
    _out = [k for k in BY_SIDE[_side] if k in YOY_EXCLUDE]
    _rng = pd.concat([YOYS[k].reindex(IDX_YOY) for k in _ks]).dropna()
    ex.append({
        'n': _e, 'kind': 'lines', 'full': True, 'height': LINE_H,
        'fmt': 'pct0', 'label_fmt': 'pct0', 'yfmt': 'pct0',
        'title': f'{_side}侧：月营收的单月同比（single-month y/y，%）',
        'xlabels': XL_YOY, 'ylab': '% y/y（单月）', 'zero_line': True, 'end_label': True,
        'series': _lines(_ks, IDX_YOY, lambda k: YOYS[k]),
        'src_extra': ('单月同比 = 当月 ÷ 去年同月 − 1（build/yoy.py 的 mom_yoy，全站唯一实现）；'
                      '拿这张图上任意一家的当月柱除以十二个月前那根，就是线上这一点 ——'
                      '本页没有任何一条同比线取自公司公告值或还原值。'),
        'note': (
            f'本图区间 {_rng.min():+.0f}% ~ {_rng.max():+.0f}%。'
            + (f'<br><b>{"、".join(NAME[k] for k in _out)}不在这张图上。</b>'
               'DRAM 是标准品、营收 = 位元出货 × 合约价，两条腿同向时相乘，'
               '单月同比可以到三位数；跟个位数到两位数的代工增速共用一根线性纵轴，'
               '会把代工那几条压成直线。这条读法是 <code>/nanya/</code> 页自己定的，'
               '本页遵守它。它的同比在 ⟨ex:yoy-heat⟩ 的矩阵里（按格着色，不共用纵轴）。'
               if _out else '')
            + (('<br>' + brk_note(IDX_YOY, _ks)) if brk_in(IDX_YOY, _ks)[0] else '')),
        **({'break_at': brk_in(IDX_YOY, _ks)[0], 'break_label': brk_in(IDX_YOY, _ks)[1]}
           if brk_in(IDX_YOY, _ks)[0] else {}),
    })

# ── ⟨ex:season-heat⟩ 季节性 ─────────────────────────────────────────────
_PK = {k: _peak_trough(k) for k in KEYS}
_pk_groups = {}
for _k in KEYS:
    _pk_groups.setdefault(_PK[_k][0], []).append(_k)
_PK_TXT = '；'.join(
    f'{MONTHS[m - 1]} 月 —— {"、".join(NAME[k] for k in ks)}'
    for m, ks in sorted(_pk_groups.items()) if m)
ex.append({
    'n': E_SEASON, 'kind': 'heat_matrix', 'full': True, 'fmt': 'f0',
    'title': (f'季节性：每月营收相当于当年月均的百分之几（{SEASON_YRS[0]}–{SEASON_YRS[-1]} '
              f'{len(SEASON_YRS)} 个完整年的平均）'),
    'rows': [f'{NAME[k]} {CODE[k]}' for k in KEYS],
    'cols': MONTHS,
    'matrix': [L([SEASON[k][m] for m in range(1, 13)]) for k in KEYS],
    'legend': '占当年月均（%，100 = 与当年月均持平）',
    'cell_h': 24, 'row_lab_w': 104, 'row_head': '公司',
    'src_extra': (f'只用<b>完整日历年</b>，且年份限定在共同窗口之内（{SEASON_YRS[0]}–'
                  f'{SEASON_YRS[-1]}）—— 七家用同一批年，否则比的是各自不同的历史时段。'),
    'note': (
        f'<b>低谷七家一致，高峰七家不一致。</b>'
        f'{sum(1 for k in KEYS if _PK[k][1] == 2)} 家的最低月是 2 月、'
        f'{sum(1 for k in KEYS if _PK[k][1] == 1)} 家是 1 月 —— 农历年停工是全组共同的，'
        '它是日历事件，不是景气信号。'
        f'<br>高峰却散在三个月上：{_PK_TXT}。'
        '设计侧靠里程碑与新案量产爬坡，代工与封测跟着下半年的消费电子备货，'
        '存储跟自己的合约价周期 —— 同一组公司的旺季不在同一个月，'
        '这也是⟨ex:growing-count@<:上面那张⟩里「同月涨跌不同向」的一部分来源。'
        '<br><b>这张图不是景气判断。</b>它把各年同月平均掉了，'
        f'{SEASON_YRS[0]}–{SEASON_YRS[-1]} 之间存储与 ASIC 两轮大周期的涨跌都落在同一批格子里 ——'
        '某一家的旺季指数偏高，可能只是它在某一年的那几个月刚好处在上行段。'
        '<br>色标同样是<b>本图自己的</b> 5/95 分位，与⟨ex:yoy-heat⟩那张不可比。'),
})

# ── ⟨ex:corr⟩ 同比的两两相关 ────────────────────────────────────────────
_cm = []
for _i, _a in enumerate(KEYS):
    _row = []
    for _j, _b in enumerate(KEYS):
        _row.append(None if _i == _j else float(CORR.loc[_a, _b]))
    _cm.append(_row)
ex.append({
    'n': E_CORR, 'kind': 'heat_matrix', 'full': True, 'fmt': 'f2',
    'title': (f'两两相关：单月同比，{spanl(IDX_YOY[0], LATEST)} 共 {CORR_N} 个月'
              f'（中位 {CORR_MED:+.2f}）'),
    'rows': [f'{NAME[k]} {CODE[k]}' for k in KEYS],
    'cols': [NAME[k] for k in KEYS],
    'matrix': _cm,
    'legend': '单月同比的皮尔逊相关系数',
    'cell_h': 26, 'row_lab_w': 104, 'row_head': '公司',
    'src_extra': ('对角线<b>留空</b>：一家与自己的相关恒为 1，既不含信息，'
                  '还会把 5/95 分位色标的上端整个占掉。'),
    'note': (
        f'<b>中位 {CORR_MED:+.2f} —— 这一组整体上并不同步。</b>'
        f'最高的一对是{NAME[CORR_HI[0]]}与{NAME[CORR_HI[1]]}（{CORR_HI[2]:+.2f}），'
        f'最低的一对是{NAME[CORR_LO[0]]}与{NAME[CORR_LO[1]]}（{CORR_LO[2]:+.2f}）。'
        '<br><b>不要把它读成领先滞后 —— 本页没有、也不会有那张图。</b>'
        + (f'把另外六家的同比对{NAME[LL["anchor"]]}做 ±{LL["span"]} 个月的错位相关，'
           f'其中 {len(LL["at0"])} 家的相关在<b>错位 0 期</b>就已经最高'
           f'（{"、".join(NAME[k] for k in LL["at0"])}），错位一点好处都没有；'
           f'其余几家「最佳错位」带来的提升最多 {LL["gain_max"]:.2f}。'
           f'把窗口对半切（各 {LL["n_half"]} 个月），'
           + (f'有 {LL["flips"]} 家的相关在前后两半里<b>正负号相反</b>。'
              if LL['flips'] else '各家相关的符号在前后两半里没有翻转。')
           + '一个换半段样本就改号的领先关系，画出来只会被当成规律。'
           if LL else '相关系数不带方向，错位相关在本页的窗口上算不出稳定结果。')
        + f'<br>窗口是全部 {CORR_N} 个月，没有挑区间。'),
})


# ─────────────────────── 末尾核对表（官方原始单位，未换算）───────────────────────
def raw_dec(k):
    """某家新台币列的**官方小数位** —— 同样从它自己的 spec 认，不在这里写死。

    这张表的标题写着「官方原始单位，未换算」，所以小数位也得是官方那个：
    联电 / 南亚科 / 创意 / 世芯的公告单位是 NT$ 千元，落库成 NT$mn 之后那三位
    小数**恰好就是官方的千元位**；舍掉它等于一边宣称未换算、一边丢掉三位官方数字
    （理由与 `build/mrspecs/umc.py` ① 逐字相同）。
    """
    spec = importlib.import_module(f'mrspecs.{k}').SPEC
    for node in (spec.get('value'), spec.get('alt')):
        node = node or {}
        if node.get('col') == NTDCOL[k]:
            d = node.get('raw_dec', node.get('dec'))
            if isinstance(d, int):
                return d
    return 0


RAW_DEC = {k: raw_dec(k) for k in KEYS}
_TBL_IDX = list(IDX[-TBL_MONTHS:])
TABLE = {
    'n': E_TABLE,
    'title': f'近 {len(_TBL_IDX)} 个月月营收核对表（NT$mn，官方原始单位，未换算）',
    'idx': '月份',
    'full': True,
    'cols': [[f'{NAME[k]} {CODE[k]}', k] for k in KEYS],
    'rows': [{'xl': mlab(p), **{
        k: (num(float(RAW[k][NTDCOL[k]].get(p)), RAW_DEC[k])
            if _fin(RAW[k][NTDCOL[k]].get(p)) else None) for k in KEYS}}
        for p in _TBL_IDX],
    'note': (
        '拿这张表去跟公司公告逐格对：七家的公告单位都是新台币，'
        f'{"、".join(NAME[k] for k in KEYS if RAW_DEC[k] >= 3)} 公告的是 NT$ 千元，'
        '本表保留三位小数 —— 那三位就是官方的千元位，不是凑出来的精度。'
        f'<br>{DISP["alchip"]}这一列是它 MOPS 申报表上的<b>新台币栏</b>；'
        '它的功能货币是美元，新台币栏 = 当月美元 × 当月换算汇率（官方註1）。'
        '所以<b>这一列逐月相加不等于它的官方本年累计</b>（官方累计走累计汇率，是另一个算式），'
        '本页也从不对它做任何加总 —— 只做同比与指数化，两者都不需要相加。'
        '<br><b>本表没有横向合计</b>：七家在同一条价值链的不同层，相加是重复计算。'),
}


# ─────────────────────────── 名词释义 ───────────────────────────
# 收词判据（CONTRACT §1）：本页的图与表里出现过、不看定义就会读错的词。
# `m/m`／`y/y`／`pp`／`3Y %ile` 这类全站通用读图约定**不收**（汇总表的 note 已经讲过）。
# 这里收的全是**本页特有**的：横截面页才有的门槛、本页自己造的统计量、
# 以及三处一望便知却会被读错的东西（价值链层、功能货币、矩阵色标）。
GLOSSARY = [
    ('共同最新月',
     '七家里<b>最慢</b>那一家的最新月。本页所有图统一截到它 —— 各家披露节奏散在次月第 '
     '7–15 天，若每家都画到自己的最新月，末端那几个月的「谁强谁弱」全是披露时点'
     '造成的假象。'),
    ('制造侧 / 设计侧',
     '本页把七家分成自有产能的四家（晶圆代工、封测、存储）与无厂的三家'
     '（IC 设计、ASIC 设计服务）。前者的周期跟着产能与稼动率走，后者跟着客户的'
     '设计定案与量产爬坡走 —— 折线图按它拆成两张，比的是同一类生意。'),
    ('价值链层',
     '汇总表分隔条上的那一行字，是<b>本页的编辑分类，不是公司的披露口径</b>。'
     '公司自己不按这个分法披露，它也不参与任何一个数的计算，只用来分组与排序。'),
    ('指数化（重定基）',
     f'把每家自己的月营收除以它在基期 {mlab(BASE)} 的值再乘 100。'
     '于是七条线从同一个起跑线出发，比的是<b>各自的增长倍数</b>，与体量无关；'
     '线与线之间不做任何加总。'),
    ('组内极差',
     '当月七家单月同比的<b>最大值减最小值</b>，单位是百分点（pp）。'
     '它量的是「同一个月里各家差得有多远」，一家的极端值会直接进到这个数里 —— '
     '所以本页另画一条去掉存储那家的对照线。'),
    ('功能货币',
     '公司记账用的那种货币。七家里六家是新台币；'
     f'{NAME["alchip"]}是美元，它 MOPS 申报表上的新台币栏是<b>按当月换算汇率折出来的</b>，'
     '不是原生记账数 —— 所以那一列逐月相加不等于它的官方本年累计。'),
    ('口径断点',
     '并表、出表或追溯重述使得某一家的序列在那个月前后不可直接连比，图上画一条'
     '红色竖虚线。横截面页的标签<b>点名公司</b>：七条线并排时不点名，会被读成'
     '「大家在这里都换了口径」。'),
    ('矩阵色标',
     '两张热力矩阵各自按<b>本图</b>全部格子的 5/95 分位定色阶。好处是极端月份顶到'
     '色阶两端、不会吃掉其余格子的分辨率；代价是<b>两张矩阵之间颜色不可比</b>。'),
]


# ─────────────────────────── 页尾说明 ───────────────────────────
def _brk_lines():
    _at, _lab, _det = brk_in(IDX)
    if not _at:
        return ('本页窗口内没有任何一家登记了口径断点 —— 这不等于历史上没发生过并表或重述，'
                '只等于七家的 spec 里没有落在这段窗口上的登记条目。')
    return ('本页窗口内共 ' + str(len(_det)) + ' 条：' + '；'.join(_det) + '。')


_LAGS = importlib.import_module('roster').LAG
_LAG_TXT = '、'.join(f'{NAME[k]} {_LAGS[k][0]}' for k in
                     sorted(KEYS, key=lambda k: _LAGS.get(k, (99,))[0]) if k in _LAGS)
_SLOW = max((k for k in KEYS if k in _LAGS), key=lambda k: _LAGS[k][0])

NOTES = [
    ('<b>本页不做跨家加总，一次都不做。</b>七家在同一条价值链的不同层：'
     f'{"；".join(ly + " —— " + "、".join(NAME[k] for k in BY_LAYER[ly]) for ly in LAYERS)}。'
     f'{NAME["alchip"]}或{NAME["guc"]}的一颗 ASIC，设计费记在它们的营收里，'
     f'晶圆再向{NAME["tsm"]}下单、记进{NAME["tsm"]}的营收，封测再交给{NAME["ase"]}、'
     f'记进{NAME["ase"]}的营收 —— 同一颗芯片至少被数三次。'
     '所以页面上没有「七家合计」「谁占几成」，一个都没有；'
     '首页那条「不做跨家加总」的总规矩在这一组上不是量纲问题，是<b>重复计算</b>问题。'),

    ('<b>主口径是新台币，本页不折汇率。</b>七家按台湾《证券交易法》公告的都是'
     '新台币合并营业收入净额 —— 同一条法规、同一个单位、同一个节奏，'
     '这是本站口径最干净的一组横截面（交易所那几页要折汇率或造定基名义额，本页都不需要）。'
     '折美元只会把同一个常数乘进每一条线，增长率一点不变，却让人以为这里做过汇率处理。'),

    (f'<b>{DISP["alchip"]}是唯一一家新台币栏为折算值的</b>，它的功能货币是美元，'
     '新台币栏 = 当月美元 × 当月换算汇率（MOPS 官方註1）。本页仍取它的新台币栏：'
     '本页只做同比与指数化，两者都不需要加总，需要的是七家同一个计量货币；'
     '而新台币栏正是它按法规申报、台湾市场看到的那个数。'
     + (f'这件事有多大，本轮实测：{spanl(ALFX["a"], ALFX["b"])} 之间 NTD/USD 从 '
        f'{ALFX["fx_a"]:.4f} 到 {ALFX["fx_b"]:.4f}（{ALFX["fx_chg"]:+.2f}%），'
        f'按对数分解只占它同期新台币累计增长的 <b>{ALFX["share"]:.1f}%</b>，'
        f'其余是经营。逐月看，汇率的同比平均 {ALFX["absmean"]:.1f}%、'
        f'最大 {ALFX["absmax"]:.1f}%（{mlab(ALFX["absmax_m"])}），'
        f'{mlab(CUR)} 为 {ALFX["now"]:+.2f}%。'
        '⚠ 这里印的是<b>汇率同比</b>，不是「新台币同比与美元同比之差」：'
        '后者会随增速水平放大，它在同比 +200% 以上的月份能印出二十几 pp，'
        '而当月汇率其实只动了个位数 —— 那是度量假象。'
        '尺度无关的写法只有一个，且恒等于汇率同比：(1+新台币同比) ÷ (1+美元同比) − 1，'
        '本页每轮复验这个恒等式。'
        if ALFX else '')),

    (GATE_TXT + f' 七家的发布节奏（月末后第几天，来自 <code>build/roster.py</code> 的 LAG）：'
     f'{_LAG_TXT} —— <b>最慢的是{NAME[_SLOW]}</b>，通常由它决定本页能画到哪个月。'),

    ('<b>口径断点从各家自己的配置现读，本页不抄任何一条。</b>'
     '单公司页把断点登记在 <code>build/mrspecs/&lt;ticker&gt;.py</code> 里，'
     '本页构建时直接读那七份配置 —— 两边结构上不可能分叉，'
     '单公司页加一条，本页下次构建就跟着有。' + _brk_lines()
     + '每条竖虚线都<b>点名公司</b>：七条线并排时不点名会被读成「大家都换了口径」；'
     '一张图只画它自己画了的那几家的断点。'),

    (f'<b>{DISP["nanya"]}不进同比折线图。</b>DRAM 是标准品，营收 = 位元出货 × 合约价，'
     '两条腿同向时相乘，单月同比可以到三位数；与个位数到两位数的代工增速共用一根'
     '线性纵轴，会把代工那几条压成直线。这条读法是 <code>/nanya/</code> 页自己定的'
     '（「这是一条存储器周期序列」），本页遵守它。'
     '它在两张不共用纵轴的图上都在：同比矩阵按格着色，'
     '增长家数那张把它只算一家 —— 后者正是为了让结论不依赖它。'),

    (f'<b>窗口从 {mlab(START)} 起，因为{NAME["ase"]}的序列从那里起。</b>'
     '那是<b>口径起点</b>不是「最早可得」：控股公司 2018-04-30 才成立，'
     '更早的月报属于前身主体，主体不同、不可前接（它自己那页的【1】写了全部证据）。'
     f'另外六家的序列都更长（最早到 2013-01），本页不把它们截短来迁就 —— '
     '只是七家同框的图只能从共同起点画。'
     f'指数化基期取 {mlab(BASE)}（全站统一基期）而不是 {mlab(START)}：'
     '后者是二月、正撞农历年，拿一个本来就偏低的月份当 100，每条线的起跑都会被垫高。'),

    ('<b>抬头没有「官方发布于」那一行，这是有意留白。</b>横截面页的发布日取成员里'
     '最晚的那一个，缺任何一个成员就整体省略 —— 拿部分成员算出来的最大值会偏早，'
     f'而偏早的日期看上去完全正常。本页缺的不止一家，其中{NAME["alchip"]}是'
     '<b>结构性的缺</b>：它不发月营收新闻稿、也不预告日期，没有任何一处「源头自己写下的'
     '发布日」可取。与其编一个像模像样的日期，不如留白。'),

    ('<b>为什么没有一张图同时画七条线。</b>图表引擎只有六个数据色'
     '（第七个红色是断点竖线专用），写一个引擎不认得的色名不会报错、会静默退回深蓝。'
     '所以七家同框时身份一律靠<b>标签</b>承载（热力矩阵的行名），'
     '折线图则按制造 / 设计拆成两张、每张不超过四条。'
     '这不是迁就调色板：那条拆法本身就是一条业务轴。'),

    ('仅供个人研究，不构成投资建议。数值以公司原始披露为准，'
     '末尾核对表保留官方原始单位未做换算，可逐格对账。'),
]


# ─────────────────────── 页顶 brief（本月读数怎么读）───────────────────────
def compose_brief():
    """`build/brief.py` 的规矩：这里只把**事实**拼成句子，措辞在 Python 侧定死，
    页面不做任何判断。`B.render` 对成品长度有硬闸门（230–380 字），超了就失败 ——
    所以每一句都要短，宁可少说一件事。
    """
    yy = {k: _yy(k) for k in KEYS}
    ok = [k for k in KEYS if _fin(yy[k])]
    if not ok:
        return None
    hi, lo = max(ok, key=lambda k: yy[k]), min(ok, key=lambda k: yy[k])
    npos = int(GROW.dropna().iloc[-1]) if len(GROW.dropna()) else None

    s1 = (f'{zh(CUR)}，{len(KEYS)} 家里 {npos} 家单月同比为正；'
          f'最快的{NAME[hi]} {pct(yy[hi], 0)}、最慢的{NAME[lo]} {pct(yy[lo], 0)}，'
          f'相差 {DISPF["sp_now"]:.0f}pp。')
    s2 = (f'这不是个别月份：{DISPF["n"]} 个月里只有 {DISPF["same_pct"]:.0f}% 全体同向，'
          f'极差中位 {DISPF["sp_med"]:.0f}pp。')
    s3 = ((f'去掉{NAME["nanya"]}之后，六家的极差中位仍有 {DISPF["exn_med"]:.0f}pp —— '
           '这一组本来就不在同一个周期上。')
          if DISPF['exn_med'] is not None else None)
    s4 = (f'指数化看（{mlab(BASE)} = 100，{MA} 个月移动平均），'
          + '、'.join(f'{NAME[k]} {float(REB[k].dropna().iloc[-1]):.0f}'
                      for k in sorted(KEYS, key=lambda k: -float(REB[k].dropna().iloc[-1]))[:3])
          + f' 排在前面，最慢的{NAME[sorted(KEYS, key=lambda k: float(REB[k].dropna().iloc[-1]))[0]]}'
          + f' {float(REB[sorted(KEYS, key=lambda k: float(REB[k].dropna().iloc[-1]))[0]].dropna().iloc[-1]):.0f}。')
    s5 = (f'七家两两相关的中位只有 {CORR_MED:+.2f}，最高的一对是'
          f'{NAME[CORR_HI[0]]}与{NAME[CORR_HI[1]]}（{CORR_HI[2]:+.2f}）。')
    s6 = ('它们在价值链的不同层、营收互为上下游，'
          '所以本页只比增速与指数，不做任何加总。')
    # s3 是可让位的那一句：六句都放得下就全出，超了先精简它（B.fit_optional 的用法）。
    lines_ = [s1, s2, s3 or '', s4, s5, s6]
    lines_[2] = B.fit_optional(
        lines_, 2, compact=lambda: (f'去掉{NAME["nanya"]}后六家极差中位仍有 '
                                    f'{DISPF["exn_med"]:.0f}pp。') if DISPF['exn_med'] else '')
    return B.render([x for x in lines_ if x])


try:
    BRIEF = compose_brief()
except SystemExit as e:
    # B.render 的长度闸门（230–380 字）没过。**不让它拦住整页发布** —— brief 不是
    # 必填字段，缺了页面只是少一段导读；但也不要静默，否则下次有人改措辞把它撑爆，
    # 页面会一声不响地少掉一块。所以：打印真实原因，payload 里不写 brief。
    print(f'{TICKER}: brief 未写入（{e}）')
    BRIEF = None

_yy_now = {k: _yy(k) for k in KEYS}
_ok_now = [k for k in KEYS if _fin(_yy_now[k])]
_hi = max(_ok_now, key=lambda k: _yy_now[k]) if _ok_now else None
HEADLINE = (
    f'{zh(CUR)}：{len(KEYS)} 家里 {int(GROW.dropna().iloc[-1])} 家单月同比为正，'
    f'最快与最慢相差 {DISPF["sp_now"]:.0f}pp'
    + (f'（{NAME[_hi]} {pct(_yy_now[_hi], 0)}）' if _hi else ''))

payload = {
    'ticker': TICKER,
    'tracker': '半导体组 · Taiwan Semiconductor Monthly Revenue Cross-Section',
    'title': f'半导体组（台股 7 家）：月营收横截面 — {zh(CUR)}',
    'data_through': str(LATEST),
    'through_label': zh(CUR),
    'subtitle': (f'台积电 / 联电 / 日月光 / 南亚科 / 联发科 / 世芯 / 创意 七家按台湾'
                 f'《证券交易法》公告的月度合并营收，{spanl(START, LATEST)}；'
                 '同一条法规、同一个单位、同一个节奏 —— 全部以新台币计量，不折汇率，'
                 '不做跨家加总。版式仿 Goldman Sachs GIR exhibit。'),
    'headline': HEADLINE,
    'hub_line': (f'{len(KEYS)} 家台股半导体的月营收横截面：'
                 f'{mlab(CUR)} 最快与最慢相差 {DISPF["sp_now"]:.0f}pp'),
    'source': SRC,
    'xlabels': XL_YOY,
    'xlabels_long': XL_ALL,
    'summary': SUMMARY,
    'exhibits': ex,
    'table': TABLE,
    'notes': NOTES,
    'footer': ('数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
               '每张图右上角可切「表格」视图逐条核对原值 · '
               '仅供个人研究，不构成投资建议'),
}
if BRIEF:
    payload['brief'] = BRIEF
payload['glossary'] = gloss.render(GLOSSARY, where=f'{TICKER} glossary')

# ⚠ `source_date` 有意不给：横截面页取成员里最晚的那个发布日，缺任何一个成员就整体省略
#   （source_dates.latest_of 的语义）。本页七家里有四家台账无记录，其中世芯是**结构性**
#   的缺 —— 它不发月营收新闻稿、也不预告日期，`fetch/alchip.py` 明写「没有。这是一等
#   状态，不要给它设兜底」。所以这一行永远取不到，留白，理由写进页尾说明。
#   也**不给** `source_date_note`：那个字段是留给「源头根本不标发布日」的，
#   而本页另外三家只是台账还没记上，两种缺口不一样，不许拿一句话盖过去。


# ═══════════════════════════════════════════════════════════════════
# 自检：本页特有的三类错误，各一道；三道都是「图上看不出来」的那种
# ═══════════════════════════════════════════════════════════════════
def selfcheck_colors():
    """同一张图里不许出现两条同色的线。

    本页有七家而引擎只有六个数据色，日月光与创意**共用 GOLD** —— 成立的前提是
    「它们从不同框」（一个在制造侧、一个在设计侧）。那是个约定，而约定拦不住
    任何东西：哪天有人把两侧并成一张图，页面上会出现两条一模一样的金线，
    图例写着两个名字，**引擎不会报错，截图也看不出来**。所以这里是一段会失败的代码。
    """
    bad = []
    for e in ex:
        seen = {}
        for s in e.get('series', []) or []:
            c = s.get('color')
            if c in seen:
                bad.append(f'Exhibit {e["n"]}「{e["title"][:24]}」：'
                           f'{seen[c]} 与 {s["name"]} 都是 {c}')
            seen[c] = s['name']
    if bad:
        raise SystemExit('build/semi 配色自检失败：\n  · ' + '\n  · '.join(bad))
    return sum(len(e.get('series', []) or []) for e in ex)


def selfcheck_rebased():
    """凡是纵轴写着「= 100」的图，基期那一格必须真的是 100。

    照搬 `build/exchanges_apac.py` 的 selfcheck_page 那一道：轴标题说指数、
    series 却喂了水平值，引擎不会报错，图看上去也完全正常（几条线按体量排开，
    像极了一张「谁体量大」的图），只有末点标签的数量级不对。
    ⚠ 本页的指数是 3MMA，前 MA−1 个月天然是 null —— 基期 BASE 在窗口左端，
      它必须有值，正好一并验到。
    """
    bad, n = [], 0
    for e in ex:
        if '= 100' not in e.get('ylab', '') or e.get('kind') != 'lines':
            continue
        n += 1
        xl = e.get('xlabels') or []
        want = mlab(BASE)
        if want not in xl:
            bad.append(f'Exhibit {e["n"]}：轴标题的基期 {want} 不在本图 xlabels 里')
            continue
        j = xl.index(want)
        hit = 0
        for s in e['series']:
            v = s['values'][j]
            if v is None:
                bad.append(f'Exhibit {e["n"]} 的「{s["name"]}」在基期 {want} 上是空的')
            elif abs(v - 100.0) > 0.01:
                bad.append(f'Exhibit {e["n"]} 的「{s["name"]}」在基期 {want} 上是 {v}，不是 100')
            else:
                hit += 1
        if not hit:
            bad.append(f'Exhibit {e["n"]}：基期 {want} 上没有任何一条序列等于 100')
    if bad:
        raise SystemExit('build/semi 指数化自检失败：\n  · ' + '\n  · '.join(bad))
    return n


def selfcheck_dense_and_text():
    """两件小事，都会静默出错：

    ① `mrwin.DENSE` 的图型（走 Catmull-Rom 平滑）里有 null，会画出一条塌到零的
       假线，还可能按 fmt 抛 TypeError 把本图之后的 exhibit 全部吃掉。本页有意
       全部用 `lines`（非平滑，null = 断笔），这一道验的是「有没有人改回去」。
    ② `page.js` 用纯文本写抬头那几个字段，塞 HTML 进去会把标签原样印在页面上。
    """
    bad = []
    for e in ex:
        if e.get('kind') in mrwin.DENSE:
            for s in (e.get('series') or []) + (e.get('stacks') or []):
                if any(v is None for v in s.get('values', [])):
                    bad.append(f'Exhibit {e["n"]}（{e["kind"]}，属 DENSE）的'
                               f'「{s.get("name")}」里有 null')
    for f in ('tracker', 'title', 'subtitle', 'headline', 'through_label', 'hub_line'):
        if '<' in str(payload.get(f, '')):
            bad.append(f'payload["{f}"] 里有 HTML 标签，但这个字段由 page.js 按纯文本写入')
    if bad:
        raise SystemExit('build/semi 自检失败：\n  · ' + '\n  · '.join(bad))


def main():
    n_series = selfcheck_colors()
    n_reb = selfcheck_rebased()
    selfcheck_dense_and_text()
    # 排版：先 mrwin（决定通栏与 x 标签抽稀，并把实测数写进图注），
    # 再 axisfmt（补轴刻度小数位）。顺序不能反 —— 见 build/ice.py 的同款注释。
    mrwin.layout_all(ex)
    axisfmt.fix_all(ex)
    # 图号：补 id、正文里建图时的号换成 ⟨ex:id⟩，交出 ORDER；write_dash 编号兑号。
    exhibits.bind_ids(payload, EX_ID, E_TABLE, where=f'build/{TICKER}')
    payload['order'] = ORDER
    payload_guard.write_dash(OUT, payload, TICKER)

    print(f'共同最新月 {LATEST} | 七家: '
          + '、'.join(f'{NAME[k]}={LATEST_EACH[k]}' for k in KEYS))
    print(f'窗口 {spanl(START, LATEST)}（{len(IDX)} 个月）| 同比窗口 '
          f'{spanl(IDX_YOY[0], LATEST)}（{len(IDX_YOY)} 个月，'
          f'{"、".join(NAME[k] for k in YOY_LATE)} 起步最晚）')
    print(f'断点：现读 mrspecs，共 {len(BREAKS)} 条，落在本页窗口内 '
          f'{len(brk_in(IDX)[2])} 条')
    print(f'离散度：{DISPF["n"]} 个月里全体同向 {DISPF["same"]}（{DISPF["same_pct"]:.1f}%）、'
          f'硬分歧 {DISPF["hard"]}（{DISPF["hard_pct"]:.1f}%）| 极差中位 '
          f'{DISPF["sp_med"]:.1f}pp、峰值 {DISPF["sp_max"]:.1f}pp @{DISPF["sp_max_m"]}'
          f' | 去掉{NAME["nanya"]}后中位 {DISPF["exn_med"]:.1f}pp')
    print(f'指数化（{BASE_M}=100，{MA}MMA）末点：'
          + '、'.join(f'{NAME[k]} {float(REB[k].dropna().iloc[-1]):.0f}'
                      for k in sorted(KEYS, key=lambda k: -float(REB[k].dropna().iloc[-1]))))
    print(f'相关：{CORR_N} 个月，中位 {CORR_MED:+.2f}，'
          f'最高 {NAME[CORR_HI[0]]}–{NAME[CORR_HI[1]]} {CORR_HI[2]:+.2f}，'
          f'最低 {NAME[CORR_LO[0]]}–{NAME[CORR_LO[1]]} {CORR_LO[2]:+.2f}')
    if LL:
        print(f'错位相关（对{NAME[LL["anchor"]]}，±{LL["span"]} 月）：'
              f'{len(LL["at0"])} 家最佳错位就是 0 期，最大增益 {LL["gain_max"]:.3f}，'
              f'前后半段符号翻转 {LL["flips"]} 家 ⇒ 本页不画领先滞后图')
    if ALFX:
        print(f'世芯汇率：{spanl(ALFX["a"], ALFX["b"])} NTD/USD {ALFX["fx_chg"]:+.2f}%，'
              f'占其新台币累计增长的 {ALFX["share"]:.2f}%（对数分解）；'
              f'恒等式 (1+y_NTD)/(1+y_USD)−1 ≡ 汇率同比 已复验')
    print(f'自检：配色 {n_series} 条线无同图同色 ✓ | 指数化 {n_reb} 张「= 100」图'
          f'基期格等于 100 ✓ | DENSE/纯文本 ✓')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张）+ '
          f'Exhibit {TABLE["n"]} 核对表')
    print(f'写出 {OUT}（{os.path.getsize(OUT) / 1024:.1f} KB）')
    print(payload['headline'])


if __name__ == '__main__':
    main()
