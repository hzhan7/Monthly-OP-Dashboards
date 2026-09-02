# -*- coding: utf-8 -*-
"""单公司页**通用底座** —— 一份 SPEC 配置 → `data/<ticker>.js`，payload 与既有 12 家同构。

## 为什么有这个文件

既有 12 家各写一份 `build/<t>.py`（700–980 行），而 `mlab` / `qlab` / `nz` / `load` /
`to_monthly` / `yoy_line` 这批零件在 `cme.py`、`cboe.py`、`hkex.py` 里**各实现了一遍**。
`build/pctile.py` 的模块注释记着这个教训的代价：「各写各的正是同一序列两页判定相反的
原因」。所以新增 9 家交易所不再逐个手写，改成「一次性底座 + 每家一份 spec」。

本文件收敛的零件（口径取三份既有实现里最严的那一份）：

| 零件 | 既有实现 | 本文件采信的口径 |
|---|---|---|
| `mlab` | cme/cboe/hkex 各一份，完全相同 | 照搬 |
| `nz(v,dec)` | cboe：四舍五入到 0 就去掉负号 | 照搬（hkex 的同名函数是**改字符串**的，不同义，这里叫 `nz_txt`） |
| `L` / `LN` | cboe 的 `L` 已含 null 兜底，hkex 的 `L` 不含 | 只保留含兜底的那版，命名 `LN` |
| `yoy_line` | cboe/hkex 各一份，判据相同（基数 < 中位绝对值 15% 或异号则放弃） | 照搬，并合并 hkex 的比率序列走百分点差 |
| `to_monthly` | 只有 hkex 有 | 照搬（季度参数摊到月，最新季之后 ffill） |
| 分位 | 三家都调 `build/pctile.py` | 继续调，不另写 |

**未来可把既有 12 家迁过来**：那 12 份 payload 已逐字验收上线，本轮一行都不改。迁移是
独立一件事，做法是逐家把 `build/<t>.py` 换成 `build/specs/<t>.py` 并**逐字节比对**
新旧 `data/<t>.js`（除首行构建日期），比对不上就说明底座还差那家的某个口径，先补底座。

## 删得干净是硬设计约束

用户明说「如果这些非美国交易所维护成本太高，我会选择性删除」。所以一家的注册
**就是 `build/specs/<ticker>.py` 这一份文件**，删除一家 = 删三样东西：

    build/specs/<t>.py   data/<t>.js   <t>/            （再从 roster 名单里去掉一行）

底座里**不许出现 `if ticker == 'xxx'`**，任何一家的特殊逻辑一律进它自己的 spec
（spec 是普通 Python 模块，需要时可以在里面算派生列并写进 CSV 之外的地方）。
本文件里没有任何一处认得任何一家的名字 —— 删掉全部 9 个 spec，本文件仍然自洽。

## 契约

见 `docs/SINGLE_SPEC.md`。字段名由主线程定死，底座与配置双方都不得自行更改。

## 用法

    python3 build/single.py ice              # 建一家
    python3 build/single.py ice ndaq db1     # 建几家
    python3 build/single.py --all            # build/specs/ 下全部

退出码：0 = 成功或「门槛没到、本次不出页」（原文件原地不动）；1 = spec 写错 / 数据结构
不对（要人去改）。两者的区别是「等数据」还是「等人」，见 `resolve_through()` 的注释。
"""
import argparse
import importlib.util
import math
import os
import re
import sys

import numpy as np
import pandas as pd

import axisfmt
import chartscale
import mrwin              # 窗口排版的裁决层（通栏 / x 标签抽稀），与台湾半导体 7 家共用
import payload_guard
import pctile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
DATA = os.path.join(ROOT, 'data')
SPECS = os.path.join(HERE, 'specs')

# ────────────────────────────── 全站口径常数 ──────────────────────────────
WIN_SHORT = 13          # 近期窗口（CONTRACT §5.4：核对表 13 个月）
WIN_HEAT = 24           # 热力矩阵列数

#: 时序图的窗口左端。**全站统一 2016-01**（2026-08-18 从「最近 25 个月」改过来）。
#:
#: 改这一条的理由：原来 `WIN_LONG = 25` 意味着无论 series 里躺着多少历史，页面上
#: 除了每页那 1-2 张「全历史」图之外，其余全部只画最近两年 —— db1 有 295 个月、
#: tmx 295、ndaq 251、ice 187，读者一个字节都看不到。把数据回补到 2016 而窗口不动，
#: 等于回补给谁看。
#:
#: 为什么是 2016-01 而不是「各页自己的全历史」：几页的历史长度差了一个数量级
#: （db1/tmx 2002 起 vs asx 2017-10 起），各画各的全历史会让横截面页与单公司页
#: 对同一个指标给出不同的起点，跨页读数没有共同基准。2016-01 是全站都够得着的
#: 最早共同起点（见各 fetch 模块 docstring 的回补记录）。
#:
#: ⚠️ 序列比 2016-01 短的家（例如 asx 2017-10、miax 主力列 2025-01）不会被强行拉长：
#: `Page.win_long()` 取 `max(序列首月, WIN_FROM)`，只往右让、不往左借。
WIN_FROM = '2016-01'

#: 抬头那行 headline 只需要「末月 + 上月 + 去年同月」三格就能算出 y/y 与 m/m，
#: 取 37 个月是原先 `WIN_LONG + 12` 的值，原样保留 —— 它与图窗无关，
#: 改动它会改变 headline 的数值口径（`chg_txt` 拿的是窗口内的相对位置）。
WIN_HEAD = 37
MIN_MONTHS = 24         # 共同历史短于它就不出页（同比 + 一年缓冲）
BACKTRACK = 12          # 头条列末月对不齐时，最多往回找几个月
SEASON_YEARS = 5        # 季节性的「过去 N 年同月均值」上限
MAX_LINES = 5           # 一张图最多几条靠颜色区分的序列（docs/CHART_KINDS.md §2）
LINE_H_ENDLABEL = 360   # 开了 end_label 的 lines 图的最小画布高（同 exchanges.py）

# 数据色只有 6 个，RED 是断点与截轴离群值专用色，**不做数据色**。
# GRAY 在本底座里另有专职（分位带与季节性基线），所以多列对比图只用前 5 个。
LINE_COLORS = ('NAVY', 'MBLUE', 'BLUE', 'GREEN', 'GOLD')
BAND_HI, BAND_LO = 'GRAY', 'BLUE'      # 分位带的上/下沿，见 ex_history 里的注释

# assets/charts.js 实有的 18 个格式器（fmtOf 对不认识的名字**静默退回 f1**，
# 所以这张表是硬校验，不是提示）。值 = (小数位, 前缀, 后缀)，供 Python 侧格式化用。
FMT_INFO = {
    'f0': (0, '', ''), 'f1': (1, '', ''), 'f2': (2, '', ''), 'f3': (3, '', ''),
    'f0c': (0, '', ''), 'int': (0, '', ''),
    'usd0': (0, '$', ''), 'usd1': (1, '$', ''), 'usd2': (2, '$', ''),
    'usd3': (3, '$', ''), 'usd4': (4, '$', ''),
    'pct0': (0, '', '%'), 'pct1': (1, '', '%'), 'pct2': (2, '', '%'), 'pct0z': (0, '', '%'),
    'pp0': (0, '', 'pp'), 'pp1': (1, '', 'pp'),
    'x0': (0, '', 'X'),
}
RATIO_FMT = {'pct0', 'pct1', 'pct2', 'pct0z', 'pp0', 'pp1'}   # 变化量走 pp/bp 的那些

SPEC_KEYS = {'ticker', 'name', 'title', 'csv', 'ccy', 'source',
             'headline', 'groups', 'slow_cols', 'breaks', 'notes',
             'decomp', 'ttm_yoy', 'headline_style'}
SPEC_REQUIRED = {'ticker', 'name', 'title', 'csv', 'ccy', 'source', 'headline', 'groups'}
COL_KEYS = {'col', 'zh', 'unit', 'fmt', 'stock', 'scale'}
COL_REQUIRED = {'col', 'zh', 'unit', 'fmt'}
GROUP_KEYS = {'zh', 'cols', 'mix'}
GROUP_REQUIRED = {'zh', 'cols'}

# ── groups[].mix —— 「总量柱 + 分项 100% 占比堆叠」两张图 ─────────────────────
# 这个字段做的是 `groups[].cols` 里那几列**彼此独立**这条默认假设的例外：
# 声明了 mix，就是声明「total 这一列 ≡ parts 各列之和（+ 可选残差）」这个**加总关系**。
# docs/SINGLE_SPEC.md §2.1 原来写着「本套 SPEC 里没有『分部』这个概念，所以不产出
# 堆叠图」—— 那句话现在只对**没写 mix 的组**成立：加总关系拿不出保证时确实不许堆，
# 但拿得出的时候，把它写下来并让底座**逐月复算**（见 `Page.mix_frame`）比不画更好。
#
# 复算是硬的：残差为负（分项之和超过合计）一律 SpecError —— 那说明分子分母不是同一个
# 口径，而图上只会画成一根更高的柱；残差为正且超过 `MIX_RESID_TOL` 却没给 `residual_zh`
# 也一律 SpecError —— 那种图会声称「堆叠 = 100%」而实际不是，是一句静默的假话。
# ⚠️ 这里**没有** granularity / total_col / weight_col。它们是 `ttm_yoy` 用来把日均列
# 还原成当月合计、好滚 12 个月的；mix 的合计柱次轴是**单月同比**（当月对去年同月，
# 本列除本列），一步还原都不需要。2026-09 从 MIX_KEYS 里删掉的时候三处一起删了 ——
# 留着就是死配置，而死配置会让下一个人以为这张图做过什么它其实没做的事。
MIX_KEYS = {'total', 'parts', 'residual_zh', 'rhs_share', 'note', 'share_note'}
MIX_REQUIRED = {'total', 'parts'}

#: 100% 堆叠的分段配色，**自下而上**按 `parts` 的声明顺序取；残差段永远在最上面、
#: 固定 `MIX_RESID_COLOR`。这 6 个就是本仓全部的数据色（RED 是断点与截轴离群值专用，
#: 不做数据色），所以 5 个分项 + 1 段残差是这个图型的**硬上限**。
#:
#: **按分项数分别排，不是取同一条序列的前 n 个。** 理由是残差段永远接在最后一个分项
#: 上面，于是「最后一个分项 → GRAY」这一对**随分项数换人**：取固定前缀
#: `('NAVY','BLUE','MBLUE','GOLD','GREEN')` 时，2 段那档落到 BLUE→GRAY（1.31:1）、
#: 4 段那档落到 GOLD→GRAY（1.20:1），而这两档恰恰是本仓真出过的形状。
#: 下面每一档都是把 5 个数据色 + GRAY 的全排列跑一遍、在「MBLUE 与 GREEN 不许相邻」
#: （对比度 1.07:1、灰度差 1.7%，docs/CHART_KINDS.md §3.6.1 记的雷区）这条约束下
#: **最大化最小相邻对比度**得来的，相邻对比度（WCAG 相对亮度比，自下而上、末尾接 GRAY）：
#:   1 段  NAVY                             | NAVY→GRAY 4.77
#:   2 段  BLUE  NAVY                       | 6.30 / 4.77
#:   3 段  MBLUE BLUE  NAVY                 | 2.62 / 6.30 / 4.77
#:   4 段  MBLUE BLUE  GREEN NAVY           | 2.62 / 2.46 / 2.56 / 4.77
#:   5 段  GOLD  NAVY  GREEN BLUE  MBLUE    | 3.98 / 2.56 / 2.46 / 2.62 / 1.99
#: 不给残差段时最后那一对不存在，其余各对不变 —— 所以同一张表两种情形都够用。
#: 重排之前先把上面这两条约束跑一遍，别凭「看着顺眼」调顺序。
MIX_SEG_COLORS = {
    1: ('NAVY',),
    2: ('BLUE', 'NAVY'),
    3: ('MBLUE', 'BLUE', 'NAVY'),
    4: ('MBLUE', 'BLUE', 'GREEN', 'NAVY'),
    5: ('GOLD', 'NAVY', 'GREEN', 'BLUE', 'MBLUE'),
}
MIX_RESID_COLOR = 'GRAY'
#: 残差段「小到画不出来」的判据（占合计的 %）。
#:
#: 引擎在每两段之间留 1.5px 白缝（`assets/charts.js` 的 `hgt = … - (s ? 1.5 : 0)`），
#: 而 100% 堆叠的绘图区高度在 260~280px 上下 ⇒ **占比低于 0.6% 的段，扣掉白缝之后
#: 高度就是 0**：它照样占一格图例、照样在图注里占一段，但图上一个像素都没有。
#: 这种段**不能删**（删了各段之和就不是 100，而图上仍写着「堆叠 = 100%」），
#: 但必须在图注里说破 —— 否则读者会在图上找一段根本找不到的东西，
#: 然后以为是自己看漏了。
MIX_TINY_SEG_PCT = 0.6
#: 残差 ÷ 合计 的上限：超过它就必须在 spec 里给残差段起名字。
#: 取 1e-6 而不是 0：源表里几亿的加元金额相加会有 float64 舍入（实测 6e-05 CAD /
#: 3e-14 相对），为那种量级逼 spec 写一句「其他」是噪声。
MIX_RESID_TOL = 1e-6
#: 100% 堆叠是 DENSE 图型（窗口内一个 null 都不许有，见 build/verify_pages.py 的 DENSE），
#: 所以窗口只能**截**不能补。截完短于这个数就不出这张图 —— 十几根柱的占比图读不出趋势。
MIX_MIN_MONTHS = 24

# ── 量价分解（decomp）与滚动同比（ttm_yoy）──────────────────────────────
# 两者共用一个前提：**「日均」列不能直接跨月相加**。各月立会日数在 18–23 天之间浮动，
# 直接相加等于给每个月同样的权重，年度均价 Σ金额/Σ股数 就用错了权重。所以两个字段都
# 提供 `*_total_col`（源表自带的当月合计列）与 `weight_col`（把日均 × 立会日数还原）
# 两条路，两条都给时底座**互相对账**（见 `Page.monthly_total`）。
DECOMP_KEYS = {'zh', 'kind', 'granularity', 'value', 'qty',
               'value_total_col', 'qty_total_col', 'weight_col',
               'price_zh', 'price_unit', 'price_fmt', 'price_scale',
               'bench_value', 'bench_qty', 'share_zh', 'mix_zh',
               'year_start_month', 'year_label', 'years', 'note'}
DECOMP_REQUIRED = {'zh', 'kind', 'granularity', 'value', 'qty',
                   'price_zh', 'price_unit', 'price_fmt'}
TTM_KEYS = {'zh', 'granularity', 'level', 'total_col', 'weight_col', 'note'}
TTM_REQUIRED = {'zh', 'granularity', 'level'}

# 源表的量列有两种粒度，本仓两种都有（SGX 的 sec_turnover_* 是当月总量，
# MIAX 的 API 列与 JPX 的 adt_/adv_ 是当月日均）。底座**猜不出来**，而猜错的代价是
# 图注里印出一句假话（「本身即当月合计口径」），`verify_pages.py` 查不出来 ——
# 它只看得见 payload 的结构，看不见那句话对不对。所以做成**必填、无缺省**：
# 有缺省就等于让下一个人默默继承上一家的粒度假设。
GRANS = ('monthly_total', 'daily_avg')

#: 头条列的开篇画法（spec 的 `headline_style`，缺省 `'band_yoy'` = 与从前逐字节相同）。
#:
#:   'band_yoy'  两张：①「全历史折线 + 近 3 年 P10/P90 分位带」②「单月同比柱」
#:   'bar_yoy'   **一张**：全历史的水平值柱 + 次轴单月同比折线
#:
#: `'bar_yoy'` 是 2026-09 按页面所有者的指令加的：「柱状图和 yoy 的折线图要在一个图里」。
#: ⚠️ **代价说清楚**：分位带在柱图上没有位置（引擎没有「柱 + 两条带 + 次轴线」这种
#: 图型），所以选 `'bar_yoy'` 就等于把 P10/P90 那条常态区间从页面上拿掉 ——
#: 汇总表的「3Y %ile」列还在（它不靠这张图），但页尾那句「Exhibit 2 的灰色分位带与它
#: 同窗口同口径」会自动消失，不会留下一句指着不存在的图的话。
HEADLINE_STYLES = ('band_yoy', 'bar_yoy')

# 分解出来的那个**派生量**（= 金额 ÷ 数量）到底是什么，全仓有三类，含义互不相通：
# 混用一套措辞会让读者把「订单碎片化」读成「价格下跌」，把「费率」读成「成交价」。
# 所以 `kind` 是必填字段，底座据它生成派生量的定性说明；spec 不许自己改这段话。
# (派生量的通用叫法, 必须印出来的「它不是什么」)
DECOMP_KINDS = {
    'share_price': (
        '成交量加权平均成交价',
        '它同时含两件事：（一）市场本身的涨跌；（二）<b>成交结构变化</b> —— 单价高的标的'
        '成交占比上升，即使每只票都没涨，这个数也会被抬高。'
        '<b>它不是股价指数的收益率</b>，不能读成「大盘涨了多少」。'),
    'per_trade': (
        '每笔平均成交额',
        '它衡量的是<b>订单碎片化程度</b>（一笔委托被拆成多少笔成交），与市场涨跌只有间接'
        '关系。<b>把它叫「价」是错的</b>：算法交易把大单拆细会让这个数一路走低，'
        '而同期标的价格完全可以在涨。'),
    'revenue_rate': (
        '单位成交量的实现费率',
        '这一类分解的是<b>收入</b>而不是成交额：费率受产品组合、阶梯定价与返佣影响，'
        '与「成交价格」无关。<b>它与「股数 × 均价」那一类不可并读</b>，'
        '两者的「量」也不是同一个量。'),
}

DECOMP_EPS = 1e-9        # 分解残差硬上限。恒等式的残差只应该是 float64 舍入（~1e-16）
DECOMP_YEARS = 5         # 默认画几根年度柱（要 years+1 个完整年才画得出 years 根）
DECOMP_LN_MIN = 1e-6     # |ln(V₁/V₀)| 低于它就整根柱留空（见 ex_decomp 里的权重说明）
TOTAL_TOL = 1e-6         # 「日均 × 权重」与「当月合计列」的一致性容差（见 monthly_total）
TTM_WIN = 12             # 滚动合计窗口（个月）

# 同比口径账本认的类别（页尾「同比口径」条目按类各写一段点名文案，见 notes()）：
#   ttm     = 12 个月滚动合计的同比 —— 流量默认口径（CONTRACT §6.1 第 1 条），ex_ttm 次轴金线
#   mom     = 单月同比（当月对去年同月）—— 头条同比图与 gs_bar 次轴
#   mom_pp  = 比率列的单月同比（百分点差 —— 比率不做滚动，CONTRACT §6.1 第 5 条）
#   stock   = 存量列的点对点同比（存量不可加总，CONTRACT §6.1 第 4 条）
#   heat    = 热力矩阵（格内是单月同比，按 CONTRACT §6.2 豁免保留）
# 做成白名单是因为拼错的类别只会静默丢一段点名文案，页面照常上线没人发现，
# 所以 log_yoy 对不认识的名字硬失败。
YOY_CALS = ('ttm', 'mom', 'mom_pp', 'stock', 'heat')


class SpecError(SystemExit):
    """spec 写错 / CSV 结构不对 —— 要人去改，退出码 1。

    与「门槛没到」严格区分：后者是等数据，退出码 0（见 Page.payload 的注释）。
    """


# ══════════════════════════════ 通用零件 ══════════════════════════════
def mlab(p):
    """Period('2026-06') → 'Jun-26'（与 gsx.mlab / 既有 12 家一致）。"""
    return p.strftime('%b-%y')


def nz(v, dec):
    """消掉负零。`round(-0.04, 1)` 是 -0.0，f-string 会照实印成「-0.0」——
    读者看到的是一个不存在的负数（既有页面在热力矩阵与 tsm 上都抓到过）。
    四舍五入到展示精度之后若等于 0，就把符号去掉。"""
    if v is None or not np.isfinite(v):
        return v
    r = round(float(v), dec)
    return 0.0 if r == 0 else float(v)


def nz_txt(txt):
    """已经格式化成字符串之后的负零（'-0%' / '-0bp'）。hkex 里那个同名函数就是这个，
    与上面的 `nz()` **不同义** —— 两个同名不同义的函数正是本轮要收敛的乱象之一。"""
    for bad, good in (('-0%', '0%'), ('-0.0%', '0.0%'), ('-0pp', '0pp'),
                      ('-0.0pp', '0.0pp'), ('-0bp', '0bp'), ('+0bp', '0bp')):
        if txt == bad:
            return good
    return txt


def LN(a):
    """序列 → JSON 数组，非有限值一律写 null（图上断笔、表里「—」）。

    payload 里绝不能出现 NaN：`json.dump` 默认 `allow_nan=True`，写出的裸 `NaN`
    不是合法 JSON 但是合法 JS，浏览器照渲染、退出码还是 0（CONTRACT §5 第 5 条）。
    """
    return [None if (v is None or not np.isfinite(v)) else round(float(v), 6) for v in a]


def flat_zero(*arrays):
    """窗口内所有序列的有限值是否**恒为 0**（至少要有一个有限值）。

    这不是「缺数据」，是**取值范围退化**。引擎给柱图定的量程写死成
    `y0 = 0；y1 = max × 1.22`（`assets/charts.js:622`，`bars_labeled` 是 `×1.13`）——
    max 也是 0 时上下界重合，`Y(v) = (v−y0)/(y1−y0)` 就是 0/0：刻度、网格线、柱、
    数值标签的坐标全成 NaN / ±Infinity，浏览器把非有限属性当 0 渲染，整张图糊在画布
    左上角并越出卡片。实测 tmx「BAX（CDOR，已停）月末未平仓」越界 8.0px、
    53 个坐标属性是非有限值。

    只判 0，不判「常数」：常数非 0 时 `y1 = c×1.22 > y0 = 0`，量程不退化，图正常。
    """
    seen = False
    for a in arrays:
        for v in a:
            if v is None or not np.isfinite(v):
                continue
            seen = True
            if float(v) != 0.0:
                return False
    return seen


def fmt_val(v, fmt):
    """按格式器名把一个数格式化成展示串（Python 侧算好，页面只贴字符串）。

    与引擎的同名格式器有一处**有意不同**：这里一律带千分位。引擎的 f0/f1 不带
    （图上标签窄，逗号会挤），而汇总表与核对表是 HTML 文本，五位数不带千分位读不动。
    """
    if v is None or not np.isfinite(v):
        return ''
    dec, pre, suf = FMT_INFO[fmt]
    body = f'{nz(v, dec):,.{dec}f}'
    if fmt in ('pp0', 'pp1') and v >= 0:
        body = '+' + body
    return f'{pre}{body}{suf}'


def unit_txt(v, c):
    """数值 + 单位。fmt 自带后缀（% / pp / X）时**不再补单位** —— 否则印出「19.1% %」。"""
    s = fmt_val(v, c['fmt'])
    if not s:
        return '—'
    suf = FMT_INFO[c['fmt']][2]
    u = (c['unit'] or '').strip()
    return s if (not u or u == suf) else f'{s} {u}'


def chg_txt(c, v, lag=12):
    """一列在窗口末端的变化。比率列走**百分点差**，其余走百分比变化。

    这一条不能靠调用处自觉：比率列写成「份额同比 +2.1%」时，读者无法判断那是
    「份额从 18.7% 涨到 19.1%（+0.4pp）」还是「份额本身涨了 2.1%」，而两者差 5 倍。
    """
    a = np.asarray(v, float)
    if len(a) <= lag:
        return '—'
    if c['fmt'] in RATIO_FMT:
        d = a[-1] - a[-1 - lag]
        return ppf(d) if np.isfinite(d) else '—'
    return pctf(yoy(a, lag=lag))


_MD_BOLD = re.compile(r'\*\*(.+?)\*\*', re.S)


def md_bold(s):
    """spec 自带的 notes 里 `**粗体**` → `<b>粗体</b>`。

    notes 走 innerHTML，Markdown 不会被解析，四个星号会原样印在页面上 —— 页面不报错、
    payload 也合法，只有截图上看得见（build/verify_pages.py 专门为它加过一条 WARN）。
    写 spec 的人手滑用 Markdown 是最常见的一种，所以底座在这里替换掉，而不是原样传下去。
    落单的 `**`（数量为奇数）保持原样，让 verify_pages 那条 WARN 继续响。
    """
    return _MD_BOLD.sub(r'<b>\1</b>', str(s))


def strip_source(s):
    """'Source: X; format after …' → 'X; format after …'（抬头/图注里不重复印 Source:）。"""
    return re.sub(r'^\s*Source:\s*', '', str(s))


def pctf(x, dec=1):
    """比率变化（小数入参）→ '+12.3%'。非有限值给「—」，不给空串：
    表里空着像是忘了填，「—」是「这里本来就没有」。"""
    if x is None or not np.isfinite(x):
        return '—'
    return nz_txt(f'{nz(x * 100, dec):+.{dec}f}%')


def ppf(x, dec=1):
    """百分点差 → '+1.2pp'。"""
    if x is None or not np.isfinite(x):
        return '—'
    return nz_txt(f'{nz(x, dec):+.{dec}f}pp')


def ppbp(v):
    """百分点差（入参单位 pp）→ '+40bp' / '+2.53pp'。

    判据与 build/hkex.py:894、本文件 summary() 里那一行逐字一致：|v| < 1pp 走 bp。
    不这么分档的话，0.4 个百分点会印成 '+0.4pp'，读者要数小数点位数才知道有多小。
    """
    if v is None or not np.isfinite(v):
        return '—'
    return nz_txt(f'{v * 100:+.0f}bp' if abs(v) < 1 else f'{v:+.2f}pp')


def ppbp_abs(v):
    """同 ppbp，但用于**幅度**（已取绝对值），不带正负号。"""
    if v is None or not np.isfinite(v):
        return '—'
    return f'{v * 100:.0f}bp' if abs(v) < 1 else f'{v:.2f}pp'


def yoy(v, i=-1, lag=12):
    """末期（或第 i 期）相对 lag 期前的变化率（小数）。基数缺失／为 0／异号 → nan。"""
    v = np.asarray(v, float)
    if not len(v):
        return np.nan
    i = i % len(v)
    j = i - lag
    if j < 0 or not (np.isfinite(v[i]) and np.isfinite(v[j])) or v[j] == 0 or v[i] * v[j] < 0:
        return np.nan
    return v[i] / v[j] - 1


def yoy_line(s_full, win, pct_series=False, lag=12):
    """逐月同比序列（%），窗口对齐到 win，供次轴 y/y 折线与同比柱用。

    口径逐行照抄 gsx.lvl_bar（build/gsx.py:285-296），cboe.py / hkex.py 各抄了一遍：
      · 比率序列（pct_series=True）用**百分点差**，不是「百分比的百分比变化」；
      · 基数 |b| < 中位绝对值 × 0.15 → 放弃（小基数会把同比放大成几百个百分点）；
      · 两期异号 → 放弃（负转正的「同比」没有意义）。
    放弃的期写 null：引擎不替这一步做判断，图上断开、表格视图里是「—」。

    同比在**切窗口之前**算 —— 切完再算的话，窗口最前面 12 期永远没有同比。
    """
    v = np.asarray(s_full.values, float)
    scale = float(np.nanmedian(np.abs(v))) if len(v) else 1.0
    scale = scale if (scale and np.isfinite(scale)) else 1.0
    out = np.full(len(v), np.nan)
    for i in range(lag, len(v)):
        a, b = v[i], v[i - lag]
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        if pct_series:
            out[i] = a - b
        elif abs(b) < 0.15 * scale or a * b < 0:
            continue
        else:
            out[i] = (a / b - 1) * 100
    return pd.Series(out, index=s_full.index).reindex(win).values


def yoy_rhs(s_full, win, pct_series=False):
    """gs_bar 的次轴 y/y 字段（给了它引擎就画同比折线、不画 12 个月均线）。

    **整条同比都算不出来时返回 None**：引擎只看 `ex.yoy` 在不在就判 dual，
    值全是 null 时 `Math.max.apply(null, [])` = −Infinity，量程退化成 [0, 1]，
    于是右边印出一列「0% 0% 0% 1% 1% 1%」的假刻度，而那条金线一个点都没画
    （实测 enx Ex30 电力衍生品 OI、sgx Ex17 加密永续 —— 两条序列都只有几个月历史，
    窗口内没有任何一对可比的同月）。宁可不要次轴。
    """
    v = LN(yoy_line(s_full, win, pct_series))
    if not any(x is not None for x in v):
        return None
    return {
        'name': 'y/y (pp, RHS)' if pct_series else 'y/y (RHS)',
        'color': 'GOLD',
        'yfmt': 'pp0' if pct_series else 'pct0',
        'values': v,
    }


NO_YOY_NOTE = ('窗口内没有任何一对可比的同月（序列历史短于 12 个月），故不画次轴同比；'
               '也没有 12 个月均线可画，所以这张用的是 <code>bars_labeled</code>（深蓝柱 + 每柱数值），'
               '与本页其余 <code>gs_bar</code>（浅蓝柱 + 金色同比）不同色是刻意的。')


# ════════════════ 图注里的口径断言：互斥对自检 ════════════════
# 底座已经被抓到**两次**在图注里无条件印出关于口径的断言，而那断言对某些页是假的：
#   ① decomp 的「本身即当月合计口径，未做还原」印在了日均列上；
#   ② ttm_yoy 的「柱是日均，已除过交易日数」印在了月合计列上，
#      而且与同一段前半句的「未做还原」自相矛盾。
# 两次的病根一样：口径措辞被写死进 f-string，而不是从
# granularity / total_col / weight_col 推导出来。
#
# `verify_pages.py` 查不出这一类缺陷 —— 它看得见 payload 的结构，看不见散文的真伪
# （两次都是 0 ERROR 通过的）。所以在生成端加一道机器判据：**同一段图注里若同时出现
# 一对互相排斥的口径断言，就抛异常**。它抓不到「孤立的一句假话」（那需要知道真值），
# 但抓得到「自相矛盾」——上面两次翻车都属于后者，因为正确的那半句本来就在同一段里。
#
# 判据故意收得很窄：只认这几对确凿互斥的说法，宁可漏报也不误报 ——
# 误报会让一张本来正确的页停更，那比漏报贵。
_CALIBER_CONFLICTS = (
    (r'本身即<b>当月合计</b>口径，未做还原', r'柱是<b>日均</b>|已除过交易日数',
     '同一段里既说该列未做还原（本身就是当月合计），又说柱是已除过交易日数的日均'),
    (r'是<b>当月日均</b>', r'本身即<b>当月合计</b>口径',
     '同一段里把同一批列既说成当月日均、又说成当月合计'),
    (r'先还原成当月合计再逐年相加', r'未做还原',
     '同一段里既说做过还原、又说未做还原'),
    (r'两列都是当月合计，跨月相加不涉及交易日权重', r'是<b>当月日均</b>|已除过交易日数',
     '同一段里既说两列都是当月合计、又说其中有日均列'),
)


def caliber_audit(exhibits):
    """扫全部图注，撞上互斥口径断言就返回 [(n, 说明), …]。空列表 = 干净。"""
    out = []
    for ex in exhibits or []:
        note = (ex or {}).get('note') or ''
        for pa, pb, why in _CALIBER_CONFLICTS:
            if re.search(pa, note) and re.search(pb, note):
                out.append((ex.get('n'), why))
    return out


def bar_ex(n, title, c, xl, v, rhs, *, ylab2):
    """一条月度序列 → 柱图。**有没有同比决定用哪个 kind**。

    `gs_bar` 在 `ex.yoy` 缺席时会回落到「柱 + 12 个月均线」，而均线的值取自
    `ex.avg12`；两个都不给，引擎画的是 `Y(undefined)` = NaN（那条虚线根本不出现），
    图例却照旧列着「Prior 12mo Avg.」—— 一条图例里有、图上没有的线。
    `build/verify_pages.py` 专门有一条规则拦这个。

    序列短于 12 个月时两样都算不出来（enx Ex30 电力衍生品 OI 只有 4 个月、
    sgx Ex17 加密永续只有 8 个月），所以改用 `bars_labeled`：柱 + 每柱数值、
    单轴、没有图例（`legendHTML` 对这个 kind 不产出任何条目），不承诺任何画不出来的东西。
    """
    if rhs:
        return {
            'n': n, 'kind': 'gs_bar', 'fmt': c['fmt'], 'xlabels': xl,
            'title': title, 'ylab': c['unit'], 'ylab2': ylab2,
            'legend': c['zh'], 'values': LN(v), 'yoy': rhs, '_cols': [c['col']],
        }
    return {
        'n': n, 'kind': 'bars_labeled', 'fmt': c['fmt'], 'label_fmt': c['fmt'],
        'xlabels': xl, 'title': title, 'ylab': c['unit'], 'values': LN(v),
        '_cols': [c['col']],
    }


def source_dates():
    """按路径加载仓库根的 source_dates.py（发布日台账）。

    不能裸 import：本文件是 `python3 build/single.py` 跑的，sys.path 上只有 build/。
    """
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load(csv_path):
    """读 series/<csv> → 月度 DataFrame（PeriodIndex，全部转数值）。

    返回 (df, holes)：holes 是**原文件里缺行的月份**。这里不硬失败而是补成空行 ——
    缺月补空之后，图上那一段会断笔（CONTRACT 规矩 3：不可比的相邻期不能连成一条线），
    比抛异常让整页永久停更好；但它也不静默：月份列进 notes、跑的时候打印出来。
    月份索引必须逐月连续是硬前提：窗口切片、同比、季度合计全靠位置对齐。
    """
    if not os.path.exists(csv_path):
        raise SpecError(f'找不到数据文件: {csv_path}')
    df = pd.read_csv(csv_path)
    if 'month' not in df.columns:
        raise SpecError(f'{csv_path} 没有 month 列')
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    if df['month'].duplicated().any():
        dup = sorted({str(m) for m in df['month'][df['month'].duplicated()]})
        raise SpecError(f'{csv_path} 有重复月份: {dup[:6]}')
    df = df.set_index('month').sort_index()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    full = pd.period_range(df.index[0], df.index[-1], freq='M')
    holes = [str(p) for p in full.difference(df.index)]
    if holes:
        df = df.reindex(full)
    df.index.name = 'month'
    return df, holes


# ─────────────── 迁移备件：本底座暂无调用方，但迁移既有 12 家时一定要用 ───────────────
# 留在这里而不是留在各家文件里，是因为 cme/cboe/hkex 现在各有一份**逐字相同**的实现，
# 而重复实现正是 build/pctile.py 记下的那个教训的来源。三份的口径完全一致，这里照搬其一。
# 本文件不调它们：9 家交易所的 series/*.csv 里既没有季度费率表，也没有 hkex 南向那种
# 中段断档。**加调用方之前不要按「看着不对」去改它们** —— 它们的正确性由既有 12 家背书。
def qlab(q):
    """PeriodIndex(freq='Q') 的一格 → '2026-Q2'（与 series/fee_rates.csv 的 period 列同写法）。"""
    return f'{q.year}-Q{q.quarter}'


def to_monthly(rate_q, month_index):
    """季度参数 → 月度：当季各月用该季的值；最新季之后沿用最后一个已知值（同 hkex）。

    「量 × 费率 = 隐含收入」这条桥的必备零件：月度量按月走、费率按季披露，
    最新一两个月用上一季费率是常态口径，不是缺数。
    """
    q = pd.PeriodIndex(month_index).asfreq('Q')
    return pd.Series([rate_q.get(x, np.nan) for x in q],
                     index=month_index, dtype=float).ffill()


def tail_contiguous(s):
    """只保留末尾逐月连续的一段（同 gsx._tail_contiguous / hkex.tail_contiguous）。

    给「序列中段真的停发过」的列用（hkex 南向 2022-2024 停了 40 个月）：直接取尾 N 个点
    会把相隔数年的月份并排画成相邻期 —— 那是一根假时间轴。
    """
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


def pct_band(vals, window=pctile.WINDOW, lo=10, hi=90, minobs=12):
    """逐月的「近 window 个月」分位带。样本不足 minobs 的月份留 None（不硬算）。

    窗口含当期（与 build/pctile.py 的 `series[lo:i+1]` 同口径）—— 两处若一个含一个不含，
    图上的带与汇总表的 3Y %ile 会对不上，而那种错没人看得出来。
    """
    v = list(vals)
    out_lo, out_hi = [], []
    for i in range(len(v)):
        h = [x for x in v[max(0, i - window + 1):i + 1] if x is not None and np.isfinite(x)]
        if len(h) < minobs:
            out_lo.append(np.nan)
            out_hi.append(np.nan)
        else:
            out_lo.append(float(np.percentile(h, lo)))
            out_hi.append(float(np.percentile(h, hi)))
    return np.array(out_lo), np.array(out_hi)


# ══════════════════════ 轴刻度小数位（引擎默认格式器会印错） ══════════════════════
# 判据与算法在 build/axisfmt.py（引擎 ticks()/plainAxis() 的 Python 复算）。
# 抽成独立模块是因为横截面页（exchanges_*.py）踩的是同一个坑，那边也要调。


def label_width(s):
    """热力矩阵行标签的像素宽估算（8px 字号，中文按 8.2px、拉丁按 4.6px）。

    row_lab_w 给小了，行标签会被 SVG 左边界切掉一半，而引擎不会报错。
    """
    w = sum(8.2 if ord(ch) > 0x2E80 else 4.6 for ch in s)
    return int(min(150, max(44, math.ceil(w) + 8)))


def share_txt(v):
    """占比读数 → 字符串。一位小数，**但不许把它凑成 0.0% 或 100.0%**。

    100% 堆叠里这两个端点是有语义的：印成 `100.0%` 等于宣称「这一段就是全部」，
    而同一段图注两句之后还写着「有一段残差」—— 自相矛盾（实测 CRA 在 Aug-25 是
    99.98657%，一位小数下印成 100.0%）。凑到端点的时候多给两位，让读者看得出它没到顶。
    """
    t = f'{v:.1f}'
    if t in ('0.0', '100.0') and not (v == 0.0 or v == 100.0):
        return f'{v:.3f}'
    return t


def axis_short(zh, cap=14):
    """把段名收成能当**纵轴标题**用的短名。

    纵轴标题是 `rotate(-90)` 竖排的，长度直接吃绘图区高度；引擎的 `fitVertical` 只会
    缩字号，缩到下限还超就画到画布外，并压住卡片的图例与「表格」按钮
    （实测：残差段叫「其他股指期货（SXM 迷你等，官方未单列）」时越出画布上缘 36.9px、
    压住图例 172px²，`tools/visual_qa.py` 判 🔴）。
    所以这里做两件事，都只动**轴标题**，图例与图注仍用全名：
      ① 去掉末尾那对括号里的补充说明 —— 它解释的是「这一段包含什么」，那件事属于图注；
      ② 还超长就截断加省略号。轴标题的职责是「这根轴是谁」，不是下定义。
    """
    t = re.sub(r'（[^（）]*）\s*$', '', str(zh)).strip()
    return t if len(t) <= cap else t[:cap - 1] + '…'


def nice_max(v):
    """`stacked_dual` 右轴的上界取一个整刻度。

    引擎把这个轴写死成 `ticks(0, rc.ymax || 60, 6)`、下界恒为 0（`assets/charts.js`），
    所以能调的只有上界。与 `build/exchanges_eu.py` / `build/exchanges_na.py` 里那份
    同名函数逐字同源 —— 三处都在给同一个写死的右轴挑刻度，改一处要想想另两处。
    """
    if not (isinstance(v, (int, float)) and np.isfinite(v)) or v <= 0:
        return 1
    step = 10 ** int(np.floor(np.log10(v)))
    for k in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0):
        t = k * step
        if v <= t:
            # ⚠️ **这里不能写 `int(t)`。** `exchanges_eu.py` / `exchanges_na.py` 的两份
            # 副本就是那么写的，而 `int()` 在 1.5 / 2.5 这两档上是**截断**：
            # step==1 时 nice_max(1.2) 会返回 int(1.5)=1 —— 一个**比入参还小**的上界。
            # 右轴用它当 ymax，比 ymax 大的点会被引擎顶到画布外，而且不报错。
            # 那两份副本目前喂进去的值（40 / 80）落不到这两档上，所以没暴露；
            # 本副本按整刻度取整、只在结果本来就是整数时才转 int。
            return int(t) if (t >= 1 and float(t).is_integer()) else float(t)
    return int(10 * step)


# ══════════════════════════════ SPEC 校验 ══════════════════════════════
def _check_keys(d, allowed, required, where):
    bad = sorted(set(d) - allowed)
    if bad:
        raise SpecError(f'{where} 有未知字段 {bad}（拼错的字段会被静默忽略，'
                        f'所以这里硬失败）；允许的字段：{sorted(allowed)}')
    miss = sorted(required - set(d))
    if miss:
        raise SpecError(f'{where} 缺必填字段 {miss}')


def _norm_col(c, where):
    """一条列配置 → 归一化 dict。fmt 必须是引擎实有的格式器名。"""
    if not isinstance(c, dict):
        raise SpecError(f'{where} 必须是 dict，收到 {type(c).__name__}')
    _check_keys(c, COL_KEYS, COL_REQUIRED, where)
    if c['fmt'] not in FMT_INFO:
        raise SpecError(f"{where} 的 fmt={c['fmt']!r} 不是 assets/charts.js 实有的格式器名"
                        f"（引擎对不认识的名字**静默退回 f1**，所以这里硬失败）；"
                        f"可用：{sorted(FMT_INFO)}")
    scale = float(c.get('scale', 1.0))
    if not (np.isfinite(scale) and scale != 0):
        raise SpecError(f'{where} 的 scale={c.get("scale")!r} 非法')
    return {'col': c['col'], 'zh': c['zh'], 'unit': c['unit'], 'fmt': c['fmt'],
            'stock': bool(c.get('stock', False)), 'scale': scale}


def _norm_decomp(d, where):
    """一条量价分解配置 → 归一化 dict。

    恒等式 **金额 ≡ 数量 × 均价** 是定义式（均价 = 金额 ÷ 数量），没有任何假设，
    所以这张图唯一能出错的地方是**分子分母不同口径**：拿含 A 的金额除以不含 A 的数量，
    造出来的「均价」带着一个方向与大小都不可知的偏差，而图上完全看不出来。
    底座没法判断两列覆盖的是不是同一批标的（那是源表口径，只有写 spec 的人知道），
    所以这里只做机械校验，口径对齐由 spec 作者自己核实并写进 `note`。
    """
    if not isinstance(d, dict):
        raise SpecError(f'{where} 必须是 dict，收到 {type(d).__name__}')
    _check_keys(d, DECOMP_KEYS, DECOMP_REQUIRED, where)
    if d['kind'] not in DECOMP_KINDS:
        raise SpecError(
            f"{where} 的 kind={d['kind']!r} 不是三类之一 —— 派生量（金额 ÷ 数量）的含义"
            f"随类别完全不同，措辞混用会让读者把「订单碎片化」读成「价格下跌」；"
            f'可用：{sorted(DECOMP_KINDS)}')
    if d['granularity'] not in GRANS:
        raise SpecError(f"{where} 的 granularity={d['granularity']!r} 只能是 "
                        f"'monthly_total'（列本身就是当月合计）或 'daily_avg'（列是当月日均）；"
                        f'写错会让图注印出一句关于口径的假话，而没有任何自动判据查得出来')
    if (('bench_value' in d) != ('bench_qty' in d)):
        raise SpecError(f'{where} 的 bench_value / bench_qty 必须**同时给或同时不给** —— '
                        f'三分法要靠这一对算出份额 s = 量÷行业量 与结构 r = 价÷行业价，'
                        f'只给一个算不出任何一块')
    out = {
        'zh': str(d['zh']),
        'kind': str(d['kind']),
        'granularity': str(d['granularity']),
        'value': _norm_col(d['value'], f'{where}.value'),
        'qty': _norm_col(d['qty'], f'{where}.qty'),
        'value_total_col': d.get('value_total_col'),
        'qty_total_col': d.get('qty_total_col'),
        'weight_col': d.get('weight_col'),
        'price_zh': str(d['price_zh']),
        'price_unit': str(d['price_unit']),
        'price_fmt': str(d['price_fmt']),
        # 均价的**单位换算常数**（金额列与数量列的量纲不一定配套：兆円 ÷ 百万株 要 ×1e6
        # 才是「円/股」）。它对增长率**完全没有影响**（分子分母同乘一个常数，比值不变），
        # 只决定图注里报出来的均价水平值读数 —— 所以它没法被用来把分解结果调好看。
        'price_scale': float(d.get('price_scale', 1.0)),
        'bench_value': (_norm_col(d['bench_value'], f'{where}.bench_value')
                        if d.get('bench_value') else None),
        'bench_qty': (_norm_col(d['bench_qty'], f'{where}.bench_qty')
                      if d.get('bench_qty') else None),
        'share_zh': str(d.get('share_zh') or ''),
        'mix_zh': str(d.get('mix_zh') or ''),
        'year_start_month': int(d.get('year_start_month', 1)),
        # 财年叫哪一年，全球没有统一规矩：JPX 的 FY2025 = 2025-04…2026-03（按**起始**年
        # 命名，日本「年度」的惯例），SGX 的 FY2026 = 2025-07…2026-06（按**结束**年命名）。
        # 底座猜不出来，猜错会让整排柱的标签集体偏一年，而图形本身完全正常 ——
        # 这种错没有任何自动判据能发现，所以做成必须由 spec 明说的字段。
        'year_label': str(d.get('year_label', 'start')),
        'years': int(d.get('years', DECOMP_YEARS)),
        'note': str(d.get('note') or ''),
    }
    if out['price_fmt'] not in FMT_INFO:
        raise SpecError(f"{where} 的 price_fmt={out['price_fmt']!r} 不是引擎实有的格式器名；"
                        f'可用：{sorted(FMT_INFO)}')
    if d.get('weight_col') and out['granularity'] != 'daily_avg':
        raise SpecError(f"{where} 声明 granularity='monthly_total'（列本身已是当月合计）"
                        f"却又给了 weight_col={d['weight_col']!r} —— 再乘一次交易日数"
                        f'会把年度合计放大二十几倍，而图形照画、量级看着还挺像')
    if out['year_label'] not in ('start', 'end'):
        raise SpecError(f"{where} 的 year_label={out['year_label']!r} 只能是 'start'"
                        f"（财年按起始年命名，如 JPX FY2025 = 2025-04…2026-03）或 'end'"
                        f"（按结束年命名，如 SGX FY2026 = 2025-07…2026-06）")
    if out['year_start_month'] == 1 and out['year_label'] != 'start':
        raise SpecError(f'{where} 是日历年（year_start_month=1），起始年与结束年是同一年，'
                        f"year_label 只能留空或写 'start'")
    if not 1 <= out['year_start_month'] <= 12:
        raise SpecError(f"{where} 的 year_start_month={out['year_start_month']} 越界 —— "
                        f'1 = 日历年，4 = 4 月制财年，取值 1–12')
    if out['years'] < 2:
        raise SpecError(f"{where} 的 years={out['years']} < 2 —— 一根柱没有「逐年对比」可言")
    if not (np.isfinite(out['price_scale']) and out['price_scale'] > 0):
        raise SpecError(f"{where} 的 price_scale={d.get('price_scale')!r} 必须是正的有限数")
    return out


def _norm_ttm(t, where):
    """一条「水平值 + 12 个月滚动同比」配置 → 归一化 dict。"""
    if not isinstance(t, dict):
        raise SpecError(f'{where} 必须是 dict，收到 {type(t).__name__}')
    _check_keys(t, TTM_KEYS, TTM_REQUIRED, where)
    if t['granularity'] not in GRANS:
        raise SpecError(f"{where} 的 granularity={t['granularity']!r} 只能是 "
                        f"{GRANS[0]!r} 或 {GRANS[1]!r}（见 DECOMP_REQUIRED 上方的注释）")
    if t.get('weight_col') and t['granularity'] != 'daily_avg':
        raise SpecError(f"{where} 声明 granularity='monthly_total' 却给了 weight_col —— "
                        f'当月合计再乘一次交易日数是错的')
    return {
        'zh': str(t['zh']),
        'granularity': str(t['granularity']),
        'level': _norm_col(t['level'], f'{where}.level'),
        'total_col': t.get('total_col'),
        'weight_col': t.get('weight_col'),
        'note': str(t.get('note') or ''),
    }


def _norm_mix(m, where):
    """一条 `groups[].mix` → 归一化 dict。这里只做**机械**校验，加总关系留给 Page 复算。

    `total` / `parts` 写的是**列名**，不是列配置 —— 列配置只在 `groups[].cols` 里声明一次，
    这里引用。理由是「一列只声明一次」：同一列若在两处各写一份 unit/fmt，
    两份迟早会分叉，而分叉之后图与核对表会对同一个数印出两个单位，没有任何护栏会响。
    """
    if not isinstance(m, dict):
        raise SpecError(f'{where} 必须是 dict，收到 {type(m).__name__}')
    _check_keys(m, MIX_KEYS, MIX_REQUIRED, where)
    parts = list(m['parts'])
    if not parts:
        raise SpecError(f'{where} 的 parts 一项都没有 —— 没有分项就没有占比可画')
    if len(parts) != len(set(parts)):
        raise SpecError(f'{where} 的 parts 里有重复列名 {parts} —— 同一列堆两次会让'
                        f'各段之和超过合计，而图上只会画成一根更高的柱')
    if str(m['total']) in parts:
        raise SpecError(f'{where} 的 total={m["total"]!r} 同时出现在 parts 里 —— '
                        f'合计不是自己的分项，堆进去各段之和会是合计的两倍')
    # 分项段数上限跟着配色走（见 MIX_SEG_COLORS 上方那段）：残差段用的是它自己的
    # GRAY，不占分项的配色位，所以上限就是配色表的长度。
    if len(parts) not in MIX_SEG_COLORS:
        raise SpecError(
            f'{where} 有 {len(parts)} 个分项'
            + ('（外加一个残差段）' if m.get('residual_zh') else '')
            + f'，超过本图配色能分开的 {max(MIX_SEG_COLORS)} 段 —— '
              f'请先在 spec 里把小项并进残差（docs/CHART_KINDS.md §3.6.1：'
              f'分段一多就只能靠颜色区分，而数据色只有 6 个、RED 是断点专用色）')
    rs = m.get('rhs_share')
    if rs and rs != 'residual' and rs not in parts:
        raise SpecError(
            f'{where} 的 rhs_share={rs!r} 既不是 parts 里的列名，也不是字面量 '
            f"'residual' —— 右轴那条线的语义是「把其中**一段**换个刻度重画一遍」，"
            f'它不许是第四个量。可选：{parts + ["residual"]}')
    if rs == 'residual' and not m.get('residual_zh'):
        raise SpecError(f"{where} 的 rhs_share='residual' 但没有 residual_zh —— "
                        f'没有残差段就没有那条线可画')
    return {
        'total': str(m['total']),
        'parts': [str(x) for x in parts],
        'residual_zh': str(m.get('residual_zh') or ''),
        'rhs_share': str(m.get('rhs_share') or ''),
        'note': str(m.get('note') or ''),
        'share_note': str(m.get('share_note') or ''),
    }


def _load_breaks(spec, series_dir):
    """`breaks` 归一化成 [{'month': Period, 'zh': str, 'col': str|None}]。

    支持两种写法：
      · 列表字面量 [{'month': '2025-11', 'zh': '并入雅典交易所', 'col': ...(可选)}]
      · 字符串 'enx_breaks.csv' —— 从 series/ 读那张表（口径断点本来就该跟着数据走，
        「能读 CSV 就读，别写死」）。列名认 month/break_month 与 zh/footnote/note，
        可选 column/col 用来把断点限定在画了那一列的图上。
    """
    raw = spec.get('breaks') or []
    if isinstance(raw, str):
        p = os.path.join(series_dir, raw)
        if not os.path.exists(p):
            raise SpecError(f'breaks 指向的文件不存在: {p}')
        t = pd.read_csv(p)
        cm = next((c for c in ('month', 'break_month') if c in t.columns), None)
        cz = next((c for c in ('zh', 'footnote', 'note', 'official_footnote')
                   if c in t.columns), None)
        cc = next((c for c in ('col', 'column') if c in t.columns), None)
        if not cm or not cz:
            raise SpecError(f'{raw} 缺月份列或说明列（认 month/break_month 与 '
                            f'zh/footnote/note）；现有列：{list(t.columns)}')
        raw = [{'month': r[cm], 'zh': str(r[cz]), **({'col': r[cc]} if cc else {})}
               for _, r in t.iterrows()]
    out, seen = [], set()
    for b in raw:
        _check_keys(b, {'month', 'zh', 'col'}, {'month', 'zh'}, 'breaks 的一条')
        # CSV 里的空格子读出来是 float('nan')，直接 str() 会得到字符串 'nan' 印上页面
        # （payload_guard 会拦下，但报错指向的是「payload 有 nan」而不是「断点表有空格」）。
        zh = b['zh']
        if zh is None or (isinstance(zh, float) and zh != zh) or not str(zh).strip():
            raise SpecError(f'breaks 里 {b["month"]} 那条没有说明文字 —— '
                            f'断点线旁边要写「这里发生了什么」，不写等于没标')
        col = b.get('col')
        col = str(col) if isinstance(col, str) and col.strip() else None
        m = pd.Period(str(b['month']), freq='M')
        key = (m, col)
        if key in seen:              # CSV 里同一断点常常按多列重复登记
            continue
        seen.add(key)
        out.append({'month': m, 'zh': str(zh).strip(), 'col': col})
    return sorted(out, key=lambda x: x['month'])


# ══════════════════════════════ 一页 ══════════════════════════════
class Page:
    """把一份 SPEC 变成 payload。构造只做校验与读数，不产生任何 exhibit。"""

    def __init__(self, spec, series_dir=SERIES):
        _check_keys(spec, SPEC_KEYS, SPEC_REQUIRED, 'SPEC')
        self.spec = spec
        self.ticker = str(spec['ticker'])
        if not re.fullmatch(r'[a-z0-9-]+', self.ticker):
            raise SpecError(f'ticker={self.ticker!r} 只能是小写字母/数字/连字符 —— '
                            f'它同时是目录名、data 文件名与 payload.ticker，三者逐字相同')
        self.series_dir = series_dir
        self.df, self.holes = load(os.path.join(series_dir, spec['csv']))

        self.head = [_norm_col(c, f'headline[{i}]') for i, c in enumerate(spec['headline'])]
        if not 1 <= len(self.head) <= 3:
            raise SpecError(f'headline 要 1–3 条（现在 {len(self.head)} 条）：它决定本页的'
                            f'共同最新月与发布门槛，条数一多就等于把最慢的那条当门槛')
        self.groups = []
        for gi, g in enumerate(spec['groups']):
            _check_keys(g, GROUP_KEYS, GROUP_REQUIRED, f'groups[{gi}]')
            cols = [_norm_col(c, f'groups[{gi}].cols[{ci}]') for ci, c in enumerate(g['cols'])]
            if not cols:
                raise SpecError(f'groups[{gi}]（{g["zh"]}）一列都没有')
            self.groups.append({
                'zh': g['zh'], 'cols': cols,
                'mix': _norm_mix(g['mix'], f'groups[{gi}]（{g["zh"]}）.mix')
                if g.get('mix') else None})

        self.headline_style = str(spec.get('headline_style') or 'band_yoy')
        if self.headline_style not in HEADLINE_STYLES:
            raise SpecError(f"headline_style={self.headline_style!r} 只能是 "
                            f"{HEADLINE_STYLES[0]!r}（两张：全历史分位带 + 同比柱）或 "
                            f"{HEADLINE_STYLES[1]!r}（一张：全历史柱 + 次轴单月同比）")
        self.decomp = [_norm_decomp(d, f'decomp[{i}]')
                       for i, d in enumerate(spec.get('decomp') or [])]
        self.ttm = [_norm_ttm(t, f'ttm_yoy[{i}]')
                    for i, t in enumerate(spec.get('ttm_yoy') or [])]

        # ── 列必须真实存在于 CSV。缺列是 spec 写错，硬失败（要人去改，不是等数据）──
        have = set(self.df.columns)
        allc = self.head + [c for g in self.groups for c in g['cols']]
        # decomp / ttm_yoy 引用的列同样要查。它们**不进** allc：allc 还管
        # 「整列为空就剔除」与核对表，而分解图的列是否上核对表由 spec 自己在 groups 里决定，
        # 不该因为写了一条 decomp 就被顺带塞进表里（那会让同一列在表上出现两次）。
        aux = ([c['col'] for d in self.decomp for c in (d['value'], d['qty'])]
               + [d[k] for d in self.decomp
                  for k in ('value_total_col', 'qty_total_col', 'weight_col') if d[k]]
               + [t['level']['col'] for t in self.ttm]
               + [t[k] for t in self.ttm for k in ('total_col', 'weight_col') if t[k]]
               )    # mix 的 total / parts 引用的都是 groups 里已声明的列，已在 allc 里
        missing = sorted({c['col'] for c in allc if c['col'] not in have}
                         | {c for c in aux if c not in have})
        if missing:
            raise SpecError(f'series/{spec["csv"]} 缺列 {missing} —— 写 spec 之前先 '
                            f'`head -1 series/{spec["csv"]}` 核对列名')

        self.slow = set(spec.get('slow_cols') or [])
        unknown_slow = sorted(self.slow - have)
        if unknown_slow:
            raise SpecError(f'slow_cols 里的 {unknown_slow} 不在 series/{spec["csv"]} 里')
        unused_slow = sorted(self.slow - {c['col'] for c in allc})
        if unused_slow:
            raise SpecError(f'slow_cols 里的 {unused_slow} 没有出现在 headline/groups 里 —— '
                            f'多半是列名拼错了，慢腿声明就此静默失效')
        head_slow = sorted({c['col'] for c in self.head} & self.slow)
        if head_slow:
            raise SpecError(f'{head_slow} 既是头条又是慢腿 —— 头条定义门槛，慢腿被排除在'
                            f'门槛之外，两者不能同时成立')

        # ── 整列为空的列：跳过并记账（不静默画空图）──
        self.empty = sorted({c['col'] for c in allc if self.df[c['col']].dropna().empty})
        for g in self.groups:
            g['cols'] = [c for c in g['cols'] if c['col'] not in self.empty]
        self.groups = [g for g in self.groups if g['cols']]

        # ── groups[].mix：列名 → 列配置，并把「被 mix 吃掉」的列记下来 ──────────────
        #
        # 引用而不是另写一份列配置（见 `_norm_mix` 的 docstring），所以这里要做三件事：
        #   ① 名字必须指向**本 spec 已声明**的列 —— 拼错的列名会让整张图静默消失；
        #   ② total 与 parts 必须同一个 `unit`、同一个 `stock` 档 —— 单位不同的两列相除
        #      得到的「占比」没有指称，而流量与存量混堆等于把「一个月发生了多少」和
        #      「月末剩下多少」加起来；
        #   ③ 记下**本组自己**被吃掉的列名（`g['consumed']`）：它们的水平值由这一组的
        #      「合计柱 + 占比堆叠」两张图交代，不再进本组的常规对比图，
        #      否则同一批数在同一页上画两遍。
        #      ⚠️ **按组算，不按全页算。** 曾经写成全页一个集合，后果是：某一组的 mix
        #      跨组引用了另外几组的列当分项，那几组自己的水平值柱**整批消失**
        #      （实测 tmx 的「MX 月末未平仓」mix 一加，SXF / 个股期权 / ETF 期权
        #      三张存量柱当场没了）。跨组引用的语义是「借它的数画结构」，
        #      不是「替它把水平值也讲了」—— 水平值仍归它自己那一组。
        by_name = {c['col']: c for c in allc}
        self.mix_skipped = []
        for g in self.groups:
            m = g.get('mix')
            if not m:
                continue
            where = f'groups（{g["zh"]}）.mix'
            miss = [x for x in [m['total']] + m['parts'] if x not in by_name]
            if miss:
                raise SpecError(
                    f'{where} 引用了没有在本 spec 里声明的列 {miss} —— '
                    f'mix 的 total/parts 写的是列名，列配置只在 groups[].cols 里声明一次'
                    f'（headline 也算）。现有列名：{sorted(by_name)}')
            gone = [x for x in [m['total']] + m['parts'] if x in self.empty]
            if gone:
                # 整列为空是「等数据」不是「spec 写错」，所以不硬失败：记账、这张图不出。
                self.mix_skipped.append(f'{g["zh"]}：{"、".join(gone)} 整列为空，'
                                        f'总量柱与占比堆叠都不出')
                g['mix'] = None
                continue
            m['total'] = by_name[m['total']]
            m['parts'] = [by_name[x] for x in m['parts']]
            bad_unit = [c['zh'] for c in m['parts'] if c['unit'] != m['total']['unit']]
            if bad_unit:
                raise SpecError(
                    f'{where} 的分项 {bad_unit} 与合计 {m["total"]["zh"]} 单位不同'
                    f'（{m["total"]["unit"]}）—— 占比 = 分项 ÷ 合计，两边不同单位时'
                    f'这个比值不指代任何东西')
            bad_kind = [c['zh'] for c in m['parts'] if c['stock'] != m['total']['stock']]
            if bad_kind:
                raise SpecError(
                    f'{where} 的分项 {bad_kind} 与合计 {m["total"]["zh"]} 一个是流量'
                    f'一个是存量 —— 流量按月累计发生、存量是某一天的截面，两者不能相加，'
                    f'堆出来的柱高没有指称')
            bad_ratio = [c['zh'] for c in [m['total']] + m['parts'] if self.is_ratio(c)]
            if bad_ratio:
                raise SpecError(
                    f'{where} 里 {bad_ratio} 是比率列（fmt ∈ {sorted(RATIO_FMT)}）—— '
                    f'比率不许进 mix：合计柱的次轴要么是 12 个月滚动合计的同比'
                    f'（比率不许做滚动合计，CONTRACT §6.1 第 5 条），'
                    f'要么是点对点同比而比率的同比应当是**百分点差**；'
                    f'占比堆叠那一侧更直接 —— 几个比率相加不等于合计那个比率。'
                    f'要画比率就走常规的单列 gs_bar（`ex_single` 会按 pp 处理）')
            # 本组自己声明了哪几列 —— `mix_pair` 拿它把「被吃掉的列」限定在本组内。
            # 跨组引用的语义是「借它的数画结构」，不是「替它把水平值也讲了」。
            g['declared'] = {c['col'] for c in g['cols']}

        # ── 同一列不许被画成两根柱 ────────────────────────────────────────────
        # mix 的 total 走 `ex_mix_total`；没被本组吃掉的列走常规 `ex_single` / `ex_stock`。
        # 两条路都会给同一列画一张柱图，而页面上看不出这是同一批数
        # （标题里的组名不同）。跨组引用 total 时最容易撞上：合计列声明在 A 组、
        # 被 B 组的 mix 当 total，而 A 组没把它吃掉，于是 A、B 各画一张。
        totals = {g['mix']['total']['col'] for g in self.groups if g.get('mix')}
        eaten_max = set()          # 按声明算的「最多能被吃掉」的列（保守上界）
        for g in self.groups:
            mm = g.get('mix')
            if mm:
                eaten_max |= ({mm['total']['col']} | {c['col'] for c in mm['parts']}) \
                    & {c['col'] for c in g['cols']}
        plain = {c['col'] for g in self.groups for c in g['cols']} - eaten_max
        dup = sorted(totals & plain)
        if dup:
            raise SpecError(
                f'{dup} 既是某条 mix 的 total（会画成合计柱），又在自己那一组里没有被'
                f'吃掉（会再画一张常规柱）—— 同一列两根柱，页面上看不出是同一批数。'
                f'要么把它移进声明 mix 的那一组，要么让它自己那一组的 mix 也引用它')

        # 窗口内恒为 0 的图由各 ex_* 自己判（flat0_skip），这里只开账本。
        self.flat0 = []
        # decomp 的自检行（柱构成 + YTD 覆盖月份）：ex_decomp 记账、build() 打印。
        self.decomp_report = []
        # 同比口径账本：各 ex_* 每画一条同比就记一笔 (图号, 口径类别)，
        # 页尾「同比口径」条目从这本账现算点名文案（见 log_yoy 与 notes()）。
        # payload() 组装前会再清一遍 —— 这里先建着，免得单测直接调 ex_* 时炸。
        self.yoy_log = []
        self.breaks = _load_breaks(spec, series_dir)
        for b in self.breaks:
            if b['col'] and b['col'] not in have:
                raise SpecError(f'breaks 里 col={b["col"]!r} 不在 series/{spec["csv"]} 里')

        # ── 比率列的量纲体检：pct* 期望**百分数刻度**（29.0 → "29%"）──
        # 源表里 share 类列常常是 0..1 的小数，直接配 pct1 会把 21.1% 印成 "0.2%"，
        # 图照画、没人报错。这是本底座最容易被静默画错的一处，所以硬失败。
        for c in allc:
            if c['fmt'] not in ('pct0', 'pct1', 'pct2', 'pct0z') or c['col'] in self.empty:
                continue
            mx = float(np.nanmax(np.abs(self.df[c['col']].values.astype(float)))) * c['scale']
            if np.isfinite(mx) and mx <= 1.5:
                raise SpecError(
                    f'{c["col"]} 的最大绝对值只有 {mx:.4g}，看着是 0–1 的小数比率，'
                    f'但 fmt={c["fmt"]!r} 期望百分数刻度（29.0 表示 29%）—— '
                    f"请加 'scale': 100，或换成 f2/f3")

    # ────────────────────── 门槛 ──────────────────────
    def resolve_through(self):
        """本页的共同最新月与共同历史长度。算不出返回 (None, 原因)。

        判据只看**头条列**：`slow_cols` 一律排除在外，否则一条天生晚发的腿会把整页拖住
        （最新月留空是慢腿的正常状态，不是故障）。非头条的普通列不参与门槛，它们缺最新月
        时那一格是 null，图上断笔、表里「—」。

        算不出时**退出码 0**：多数情形是「这个月还没发全」，等下个月自愈；硬失败会让
        monthly_run 每天记一次 FAIL，喊狼来了喊到没人看。spec 写错（缺列、格式器名不对）
        才是 SpecError → 退出码 1，因为那个不会自愈。
        """
        cols = [c['col'] for c in self.head]
        ends = {}
        for c in cols:
            s = self.df[c].dropna()
            if not len(s):
                return None, f'头条列 {c} 整列为空'
            ends[c] = s.index[-1]
        idx = list(self.df.index)
        cand = min(ends.values())
        latest = None
        for k in range(BACKTRACK + 1):
            m = cand - k
            if m < idx[0]:
                break
            if all(np.isfinite(self.df[c].get(m, np.nan)) for c in cols):
                latest = m
                break
        if latest is None:
            det = '、'.join(f'{c} 至 {ends[c]}' for c in cols)
            return None, (f'{BACKTRACK} 个月内找不到「全部头条列都有值」的共同月（{det}）')

        n = 0
        p = latest
        while p >= idx[0] and all(np.isfinite(self.df[c].get(p, np.nan)) for c in cols):
            n += 1
            p -= 1
        if n < MIN_MONTHS:
            return None, (f'共同历史只有 {n} 个月（截至 {latest}），不足 {MIN_MONTHS} 个月 —— '
                          f'同比与 3Y 分位都算不出来，这一页现在还不该发')
        return (latest, n), None

    # ────────────────────── 取数小工具 ──────────────────────
    def win(self, end, k):
        """以 end 结尾的 k 个月窗口（不足则从序列开头起）。"""
        idx = list(self.df.index)
        j = idx.index(end)
        return idx[max(0, j - k + 1): j + 1]

    def win_long(self, end):
        """时序图的长窗口：`WIN_FROM` 起到 end 为止（序列更短就从序列首月起）。

        只往右让、不往左借 —— 序列没有的月份造不出来。取代原先写死的 25 个月，
        理由见 `WIN_FROM` 那段注释。
        """
        idx = list(self.df.index)
        j = idx.index(end)
        # 索引是 pandas Period，不能直接与字符串比 —— 先转成同 freq 的 Period。
        lo = pd.Period(WIN_FROM, freq='M')
        i = 0
        while i < j and idx[i] < lo:
            i += 1
        return idx[i:j + 1]

    def _layout_long(self, exs):
        """窗口拉到 2016-01 之后逐张判「通栏」与「x 标签抽稀」。

        规则层与适配层都在 `build/mrwin.py`（`layout()` / `layout_all()`）——
        本文件不复制它的算式，也不复制适配逻辑：全站已经有过三份互相抄来的量边距算式，
        11 个自建生成器（cboe / hkex / schw / …）现在共用 `mrwin.layout_all()` 这一份。
        """
        mrwin.layout_all(exs)

    def win_zh(self, win):
        """图注里描述窗口的那半句。

        窗口现在动辄 100+ 期，再写「近 N 个月」会让人以为是滚动近端窗口；
        实际上左端是钉死的 `WIN_FROM`（或序列首月，哪个晚用哪个）。
        """
        return f'{mlab(win[0])} 至 {mlab(win[-1])}（{len(win)} 个月）'

    def ser(self, c):
        """一列的全序列（已乘 scale）。"""
        return self.df[c['col']].astype(float) * c['scale']

    def vals(self, c, window):
        return self.ser(c).reindex(window).values.astype(float)

    def last_month(self, c):
        s = self.ser(c).dropna()
        return s.index[-1] if len(s) else None

    def is_ratio(self, c):
        return c['fmt'] in RATIO_FMT

    def flat0_skip(self, gz, cols, win, vs):
        """窗口内恒为 0 → 记账并让调用方返回 None（不出这张图，见 flat_zero）。

        记的是「哪一组、哪几列、什么窗口、最后一个非零月是哪个月多少」，
        一个数都不写死、全部现算：指标哪天恢复非零，图自动回来。
        """
        if not flat_zero(*vs):
            return False
        for c in cols:
            s = self.ser(c).dropna()
            nz_s = s[s != 0]
            self.flat0.append({
                'gz': gz, 'zh': c['zh'], 'unit': c['unit'], 'fmt': c['fmt'],
                'win': (mlab(win[0]), mlab(win[-1]), len(win)),
                # 最后一个非零月来自**全序列**而不是窗口 —— 窗口里已经全是 0，
                # 读者要知道的正是「它是什么时候归零的」。
                'last_nz': (str(nz_s.index[-1]), float(nz_s.iloc[-1])) if len(nz_s) else None,
            })
        return True

    def log_yoy(self, n, cal):
        """记账：Exhibit n 画了一条 cal 类口径的同比（cal ∈ YOY_CALS）。

        页尾「同比口径」条目从这本账**现算**点名文案（CONTRACT §6.1 第 3 条：同页并存
        两种口径必须逐处点名成「Exhibit X、Y：单月同比」这种可核对的形式）。点名必须由
        产图的代码自报、图号必须是派生的，两个理由：
          · 被点名的对象里有底座自己生成的图（头条同比、滚动同比次轴），spec 作者
            看不见它们排在几号，没法在 spec 的 notes 里点对；
          · 写死的图号会在删图加图后指向错的图而**不报任何错**（本仓吃过这亏 ——
            图号硬编码在别处造成过「Exhibit 17 之后跟着 15」）。账本跟着产图走，
            哪张图不再画同比、或新增一张，页尾那段话自动跟随。
        """
        if cal not in YOY_CALS:
            raise SpecError(f'log_yoy 收到未知口径类别 {cal!r} —— 这是底座代码写错，'
                            f'不是 spec 的问题（拼错的类别会静默丢一段点名文案，'
                            f'所以硬失败）；认得的类别：{YOY_CALS}')
        self.yoy_log.append({'n': n, 'cal': cal})

    def breaks_for(self, window, cols=()):
        """窗口内的断点 → (break_at, break_label, 命中的断点列表)。

        `break_at` 的语义是「从这一期起与左侧不可比」，红虚线画在该期**左缘**；
        落在窗口第 0 格的断点不画 —— 左缘就是画布边线，画了也读不出是断点
        （cboe.py 的 `BREAK_PF = I_2018 if I_2018 else None` 同一条）。
        """
        names = {c['col'] for c in cols}
        at, lab, hit = [], [], []
        seen = set()
        for b in self.breaks:
            if b['col'] and names and b['col'] not in names:
                continue
            if b['month'] not in window:
                continue
            i = window.index(b['month'])
            if i == 0:
                continue
            # 同一断点常常按列登记好几份（一次口径换代涉及新旧两列）。一张图同时画了
            # 其中两列时，不去重就会在同一格上画两条重合的红虚线、并排两份同样的竖排
            # 标签，图注里那句「口径断点（…）」也会把同一句话写两遍。
            if (i, b['zh']) in seen:
                continue
            seen.add((i, b['zh']))
            at.append(i)
            lab.append(b['zh'])
            hit.append(b)
        return at, lab, hit

    #: 超过这么多期就不再给断点线挂竖排文字标签（线照画、图注照点名）。
    #:
    #: 竖排标签是 `rotate(-90)` 从图顶往下挂的，长度 = 文案长度，动辄 150-200px，
    #: 要竖着穿过大半个绘图区。`assets/charts.js` 有一套避让（沿同一条竖直带找空档，
    #: 找不到就靠 z 序让数字压在红字上面保命）—— **窗口 25 期时它够用，127 期时不够**：
    #: 那条竖直带上现在挤着上百个柱值标签，一个空档都没有，于是标签只能原地压着。
    #: 实测（tools/visual_qa.py --all）：窗口从 25 拉到 127 之后 🔴 从 4 条涨到 94 条，
    #: 新增的 90 条**全是同一个根因**，enx 45 条 / jpx 36 条 / sgx 9 条，
    #: 重叠面积 86.3px²（占小者 47%），远超 🔴 的 60px² 门槛。
    #:
    #: 去掉文案不丢信息：**图注本来就把每条断点按从左到右的顺序逐个点名**
    #: （`hit` → 各 ex_* 里那句「红色竖虚线 = 口径断点（…）」），
    #: 而 127 期窗口下竖排小字本来也读不出来。红色虚线本身保留 ——
    #: 「从这一期起与左侧不可比」这个语义是线给的，不是文字给的。
    BREAK_LABEL_MAX = 60

    def brk_zh(self, hit, window):
        """图注里描述断点的那半句。窗口长到不挂竖排标签时，补一句「按从左到右的顺序」。

        没有这半句，读者在 127 期的图上会看到几条没有文字的红虚线，
        而图注里并列着几个断点名 —— 谁对谁完全靠猜。
        """
        if not hit:
            return ''
        names = '、'.join(b['zh'] for b in hit)
        if len(window) <= self.BREAK_LABEL_MAX:
            return f'红色竖虚线 = 口径断点（{names}）'
        order = '这一条' if len(hit) == 1 else f'{len(hit)} 条自左向右依次是'
        return (f'红色竖虚线 = 口径断点，{order}：{names}'
                f'（窗口 {len(window)} 期，竖排标签在这个密度下既读不出来又会压住柱值，'
                f'所以线上不挂字、改在这里点名）')

    def mark_breaks(self, ex, window, cols=()):
        """给一张**横轴是月份**的图挂上断点。heat_matrix 不支持 break_at，别调它。"""
        at, lab, hit = self.breaks_for(window, cols)
        if at:
            ex['break_at'] = at
            if len(window) <= self.BREAK_LABEL_MAX:
                ex['break_label'] = lab
        return hit

    # ────────────────────── exhibit：头条长历史 + 3Y 分位带 ──────────────────────
    def ex_history(self, n, c):
        # 横轴取「首个有值的月 → 末个有值的月」**逐月连续**的整段，不是 dropna 后的索引：
        # dropna 会把中间缺的月直接从横轴上抹掉，于是相隔两个月的两点被并排画成相邻期 ——
        # 那是一根假时间轴（CONTRACT 规矩 3）。留成 null 由 lines 图型断笔才是对的。
        s = self.ser(c)
        fin = s.dropna()
        idx = list(self.df.index)
        win = idx[idx.index(fin.index[0]):idx.index(fin.index[-1]) + 1]
        v = s.reindex(win).values.astype(float)
        lo, hi = pct_band(v)
        xl = [mlab(p) for p in win]
        zero_ok = bool(np.nanmin(v) >= 0)
        ex = {
            'n': n, 'kind': 'lines', 'fmt': c['fmt'], 'label_fmt': c['fmt'],
            'xlabels': xl, 'xstep': max(1, len(win) // 14),
            'full': True, 'height': LINE_H_ENDLABEL, 'end_label': True,
            'title': f'{c["zh"]}：全历史与近 3 年分位带',
            'ylab': c['unit'],
            # `_cols` 是给 chartscale 用的临时键（这张图画了哪几列），payload() 里被 pop 掉。
            # 它存在的唯一理由：同一列出现在长历史图 / 季节性图 / 自己那张组图里时，
            # 三处必须同一个显示倍数，否则同一条序列在 Exhibit 3 印「1.56」、
            # 在 Exhibit 13 印「1,562,551」，读者会当成两条不同的序列。
            '_cols': [c['col']],
            'series': [
                {'name': c['zh'], 'color': 'NAVY', 'values': LN(v)},
                # 带的上下沿必须**两个色**。同色两条线在图例里指不到具体哪条（位置能分开、
                # 图例分不开），build/verify_pages.py 的多线可辨识度检查也是判「颜色有没有
                # 真的撞上」。GRAY 与 BLUE 是六个数据色里最浅的两个，做辅助线不抢主线。
                {'name': f'近 {pctile.WINDOW} 个月 P90（上沿）', 'color': BAND_HI, 'values': LN(hi)},
                {'name': f'近 {pctile.WINDOW} 个月 P10（下沿）', 'color': BAND_LO, 'values': LN(lo)},
            ],
            'src_extra': 'Full disclosed history; grey lines are the trailing 36-month '
                         'P10/P90 of the same series',
        }
        if zero_ok:
            # 纵轴从 0 起：不给的话引擎走 y0 = min − 极差×5%，那是一次没有任何标注的
            # 隐性截轴，长历史图上会把增长幅度凭空放大（cboe Ex6 / hkex Ex15 都栽过）。
            ex['zero_base'] = True
        hit = self.mark_breaks(ex, win, [c])
        cur, plo, phi = v[-1], lo[-1], hi[-1]
        pos = ('高于近 3 年 P90' if np.isfinite(phi) and cur > phi else
               '低于近 3 年 P10' if np.isfinite(plo) and cur < plo else '在近 3 年 P10–P90 带内')
        ex['note'] = (
            f'{xl[0]} → {xl[-1]} 共 {len(win)} 个月。灰线（上沿 P90）与浅蓝线（下沿 P10）'
            f'是<b>同一条序列</b>近 {pctile.WINDOW} 个月（含当月）的滚动分位，'
            f'两条合起来就是「近 3 年的常态区间」，与汇总表「3Y %ile」同窗口同口径；'
            f'样本不足 12 个月的早期月份不画带（不硬算）。'
            f'{xl[-1]} 读数 {unit_txt(cur, c)}，'
            f'{pos}。同比 {chg_txt(c, v)}、环比 {chg_txt(c, v, lag=1)}。'
            + ('纵轴从 0 起（不截轴）。' if zero_ok else '序列含负值，纵轴不强制从 0 起。')
            + (self.brk_zh(hit, win) + '，线左边那段与右边不可比。' if hit else ''))
        return ex

    def ex_head_bar(self, n, c):
        """`headline_style='bar_yoy'`：把 ①（全历史 + 分位带）与 ②（同比）并成**一张**。

        全历史的水平值柱 + 次轴**单月**同比折线。窗口与 `ex_history` 逐字相同 ——
        「首个有值月 → 末个有值月」的**逐月连续**整段（不是 dropna 后的索引：dropna 会把
        中间缺的月从横轴上抹掉，相隔两个月的两点被并排画成相邻期，那是一根假时间轴）。

        ⚠️ **分位带没了**，这是这个开关的代价，不是漏画：引擎没有「柱 + 两条带 + 次轴线」
        这种图型，而带的上下沿与柱同量纲、画上去会被读成第三、第四根柱。
        页尾那句「Exhibit N 的灰色分位带与汇总表同窗口同口径」由 `notes()` 按这张图在不在
        自动收放，不会留下一句指着不存在的图的话。
        """
        s_ = self.ser(c)
        fin = s_.dropna()
        idx = list(self.df.index)
        win = idx[idx.index(fin.index[0]):idx.index(fin.index[-1]) + 1]
        v = s_.reindex(win).values.astype(float)
        xl = [mlab(p) for p in win]
        ratio = self.is_ratio(c)
        rhs = yoy_rhs(s_, win, pct_series=ratio)
        ex = bar_ex(n, f'{c["zh"]}：全历史水平值与单月同比', c, xl, v, rhs,
                    ylab2=('pp y/y（单月）' if ratio else '% y/y（单月）'))
        ex['full'] = True
        ex['_cols'] = [c['col']]
        if rhs:
            self.log_yoy(n, 'mom_pp' if ratio else 'mom')
        hit = self.mark_breaks(ex, win, [c])
        ex['src_extra'] = 'Full disclosed history; the right-hand line is the single-month y/y'
        ex['note'] = (
            f'<b>本页的开篇图：一张图上同时给水平值与增速。</b>'
            f'深蓝柱 = {c["zh"]}的水平值（{c["unit"]}，原始单位），'
            f'横轴是<b>全部已披露历史</b> {xl[0]} → {xl[-1]}（{len(win)} 个月），'
            f'比本页其余时序图（{mlab(pd.Period(WIN_FROM, freq="M"))} 起）长。'
            + (f'金色折线（右轴）= <b>单月同比</b>（当月对去年同月）。'
               if rhs else NO_YOY_NOTE)
            + f'{xl[-1]} 读数 {unit_txt(v[-1], c)}，'
              f'同比 {chg_txt(c, v)}、环比 {chg_txt(c, v, lag=1)}。'
            + self.mom_cost_zh(c)
            + (self.brk_zh(hit, win) + '，线左边那段与右边不可比。' if hit else ''))
        return ex

    # ────────────────────── exhibit：头条同比 ──────────────────────
    def ex_yoy(self, n, c):
        ratio = self.is_ratio(c)
        end = self.last_month(c)
        win = self.win_long(end)
        xl = [mlab(p) for p in win]
        s = self.ser(c)
        yv = yoy_line(s, win, pct_series=ratio)
        # grouped_bars 而不是 diverging_bars：后者的图例与表格列名被引擎写死成 COST 的
        # 文案（charts.js:1437/1522-1523），换任何一家都会印出「油汇顺风」。
        ex = {
            'n': n, 'kind': 'grouped_bars',
            'fmt': 'pp1' if ratio else 'pct1', 'yfmt': 'pp0' if ratio else 'pct0',
            'xlabels': xl, 'bar_labels': False,
            'title': f'{c["zh"]}：单月同比',
            'ylab': 'pp y/y' if ratio else '% y/y',
            'groups': [{'name': ('同比（百分点）' if ratio else '同比 y/y'),
                        'color': 'NAVY', 'values': LN(yv)}],
        }
        hit = self.mark_breaks(ex, win, [c])
        fin = [x for x in yv if x is not None and np.isfinite(x)]
        u = 'pp' if ratio else '%'
        rng = (f'窗口内在 {nz_txt(f"{min(fin):+.1f}{u}")} ~ '
               f'{nz_txt(f"{max(fin):+.1f}{u}")} 之间。' if fin else '')
        ex['note'] = (
            f'{self.win_zh(win)}的同比，正负同色、零线由引擎画出（数据色只有 6 个，'
            f'RED 是断点专用色，所以不按正负分色）。'
            + ('比率序列的同比用<b>百分点差</b>，不是「百分比的百分比变化」。' if ratio else
               '基数不足序列中位绝对值 15% 或两期异号的月份留空 —— 那种同比不是信息，'
               '是把一个接近零的分母放大成三位数。')
            + rng
            + (self.brk_zh(hit, win) + '：跨断点的同比本身就不可比。' if hit else ''))
        # 整张图画的都是单月口径（比率列 = 百分点差）→ 记进口径账本，页尾点名
        self.log_yoy(n, 'mom_pp' if ratio else 'mom')
        return ex

    # ────────────────────── exhibit：分组多列对比 ──────────────────────
    def ex_group(self, n0, gz, cols):
        """一组同单位的流量列 → 一张图。返回 exhibit 列表（可能 0 或 1 张）。

        · 1 列   → gs_bar（水平柱 + 次轴同比），单条线没有「对比」可言
        · 2–5 列 → lines_endlabels（窗口内逐点稠密时）/ lines（有缺口时）
        · >5 列  → heat_matrix，画的是**同比**而不是水平值（见下面的注释）
        """
        if len(cols) == 1:
            return [self.ex_single(n0, gz, cols[0])]
        end = max(self.last_month(c) for c in cols)
        if len(cols) <= MAX_LINES:
            return [self.ex_lines(n0, gz, cols, end)]
        return [self.ex_heat(n0, gz, cols, end)]

    def ex_single(self, n, gz, c):
        end = self.last_month(c)
        win = self.win_long(end)
        xl = [mlab(p) for p in win]
        v = self.vals(c, win)
        if self.flat0_skip(gz, [c], win, [v]):
            return None
        ratio = self.is_ratio(c)
        rhs = yoy_rhs(self.ser(c), win, pct_series=ratio)
        ex = bar_ex(n, f'{gz}：{c["zh"]}', c, xl, v, rhs,
                    ylab2=('pp y/y' if ratio else '% y/y'))
        if rhs:      # 次轴金线是单月口径的同比；rhs 没画出来就没有同比可点名
            self.log_yoy(n, 'mom_pp' if ratio else 'mom')
        hit = self.mark_breaks(ex, win, [c])
        ex['note'] = (
            f'{self.win_zh(win)}。'
            + (f'金色折线 = 次轴同比'
               f'（{"百分点差" if ratio else "%"}，同 GS deck 的 lvl_bar —— 那个位置画的是同比，'
               f'不是滚动均线：均线只是把柱子再平滑一遍、不带新信息）。' if rhs else NO_YOY_NOTE)
            + f'{xl[-1]} {unit_txt(v[-1], c)}，'
            f'同比 {chg_txt(c, v)}、环比 {chg_txt(c, v, lag=1)}。'
            + self.slow_tail([c])
            + (self.brk_zh(hit, win) + '。' if hit else ''))
        return ex

    def ex_lines(self, n, gz, cols, end):
        win = self.win_long(end)
        xl = [mlab(p) for p in win]
        vs = [self.vals(c, win) for c in cols]
        # 整组都恒为 0 才跳：其中一条为 0 是有信息的对比，量程由别的列定，图正常。
        if self.flat0_skip(gz, cols, win, vs):
            return None
        dense = all(np.isfinite(v).all() for v in vs)
        allv = np.concatenate(vs)
        zero_ok = bool(np.nanmin(allv) >= 0)
        # lines_endlabels 平滑（Catmull-Rom）且首尾必须有值：序列里有 null 会被 JS 当 0，
        # 画出一条塌到零的假线，首尾为 null 还会 null.toFixed() 抛 TypeError、
        # 该卡片之后的 exhibit 全不渲染（docs/CHART_KINDS.md §1.2）。所以有缺口就换 lines。
        kind = 'lines_endlabels' if dense else 'lines'
        self.saw_group_lines = True     # 页尾「图型选择规则」按真画出来的图措辞
        names = ' / '.join(c['zh'] for c in cols)
        ex = {
            'n': n, 'kind': kind, 'fmt': cols[0]['fmt'], 'xlabels': xl,
            # 标题优先列出序列名（读者一眼知道图上是哪几条）；名字太长就退回条数，
            # 免得标题折行把卡片顶开。
            'title': f'{gz}：{names}' if len(names) <= 30 else f'{gz}：{len(cols)} 条序列对比',
            'ylab': cols[0]['unit'],
            '_cols': [c['col'] for c in cols],       # 见 ex_history 里对 `_cols` 的说明
            'series': [{'name': c['zh'], 'color': LINE_COLORS[i], 'values': LN(v)}
                       for i, (c, v) in enumerate(zip(cols, vs))],
        }
        if kind == 'lines':
            ex['end_label'] = True
            ex['label_fmt'] = cols[0]['fmt']
            ex['height'] = LINE_H_ENDLABEL     # 低于 308px 绘图区时末点标签会收成一摞
            if zero_ok:
                ex['zero_base'] = True
        elif zero_ok:
            # lines_endlabels 没有 zero_base 开关，默认下界是 min − 极差×20%，
            # 会在零轴以下留出一大块不存在的量纲区间。没有点落在 0 以下，所以这不是截轴。
            ex['yfloor'] = 0
        hit = self.mark_breaks(ex, win, cols)
        last = '、'.join(f'{c["zh"]} {fmt_val(v[-1], c["fmt"]) or "—"}' for c, v in zip(cols, vs))
        ex['note'] = (
            f'{self.win_zh(win)}，同一单位（{cols[0]["unit"]}）才画在同一根轴上 —— '
            f'量纲不同的列由底座自动拆成各自成图。{xl[-1]}：{last}。'
            + ('' if dense else '窗口内有缺月，改用不平滑的 lines 图型：缺口处断笔，'
                                '不用直线连（平滑图型会把 null 当 0 画出一条塌到零的假线）。')
            + self.slow_tail(cols)
            + (self.brk_zh(hit, win) + '。' if hit else ''))
        return ex

    def ex_heat(self, n, gz, cols, end):
        """>5 列：热力矩阵。**画同比，不画水平值。**

        色标是「全部有限值的 5/95 分位」共用一条 —— 水平值量级相差几十倍的列放进同一张
        矩阵，最大的那列会把色标整个占掉，其余各列全部糊成一个颜色。同比是无量纲的，
        才能跨列比。水平值请看核对表与各自的分组图。
        """
        win = self.win(end, WIN_HEAT)
        rows, M, dropped = [], [], []
        for c in cols:
            yv = yoy_line(self.ser(c), win, pct_series=self.is_ratio(c))
            if not np.isfinite(yv).any():
                dropped.append(c['zh'])
                continue
            rows.append(c['zh'])
            M.append(LN(yv))
        if not rows:
            return None
        self.saw_group_heat = True      # 同上
        ex = {
            'n': n, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pct0',
            'title': f'{gz}：{len(rows)} 条序列 × 近 {len(win)} 个月同比',
            'rows': rows, 'cols': [mlab(p) for p in win], 'matrix': M,
            'legend': '同比 y/y (%)', 'row_head': '序列',
            'row_lab_w': max(label_width(r) for r in rows),
            'src_extra': 'Cells are y/y growth, not levels',
        }
        # 格内是单月同比（豁免图型，但页尾口径点名不豁免 —— CONTRACT §6.2）
        self.log_yoy(n, 'heat')
        ex['note'] = (
            f'格内是<b>同比</b>（%），不是水平值：色标由全部有限值的 5/95 分位共用一条，'
            f'量级相差几十倍的列放同一张矩阵会被最大的那列吃掉整条色标。'
            f'绿 = 同比高、红 = 同比低；<b>每张矩阵各算各的色标，两张矩阵之间颜色不可比</b>。'
            f'水平值请看末尾核对表。列数 {len(cols)} > {MAX_LINES}，'
            f'超出「一张图最多 5 条靠颜色区分的序列」的上限，故用行标签区分身份。'
            + (f'（{"、".join(dropped)} 整行没有可算的同比，已不列入。）' if dropped else '')
            + '热力矩阵不支持断点竖线（矩阵没有连续横轴），本页的口径断点见「口径与方法说明」。'
            + self.slow_tail(cols))
        return ex

    # ────────────────────── exhibit：存量列 ──────────────────────
    def stock_tail0(self, ex, xl, v):
        """已停产品的零尾巴：关掉柱顶标签并给出那句说明（就地改 `ex`，返回图注文字）。

        窗口从 25 期拉到 2016-01 起之后，这类图**第一次出现**：BAX（CDOR，已停）
        最后一个非零月是 2024-05，之后二十几个月恒为 0，而旧窗口（近 25 期）整段全零、
        被 `flat0_skip` 整张跳过了 —— 也就是说这不是新问题，是**以前根本没画出来**。
        现在它带着上百个月的真实历史回来了，该画；只是零尾巴上每格都印一个「0.0」，
        与次轴那一年的「-100%」钉在同一条零线上叠字（实测重叠 106px²，超 🔴 门槛 60px²，
        且两组标签分属柱与次轴、引擎的 thinLabels 只在组内抽稀，跨组不管）。
        关掉柱顶标签而不是关掉这张图：零高度的柱上那个「0.0」本来就没有信息，
        而上百个月的历史有。读数仍可走右上角「表格」视图。

        ⚠️ 抽成公共方法是因为存量柱现在有**两个产地**：`ex_stock` 与
        `ex_mix_total` 的存量分支。留两份的下场是其中一份忘了关标签 ——
        同一页上两张同类图，一张干净一张叠字，而没有任何护栏会响。
        """
        tail0 = 0
        for x in reversed(v):
            if x is not None and np.isfinite(x) and x == 0:
                tail0 += 1
            else:
                break
        if tail0 < 12:
            return ''
        ex['bar_labels'] = False
        return (f'<b>本序列已停更：最后一个非零月是 {xl[len(v) - tail0 - 1]}，'
                f'其后 {tail0} 个月恒为 0。</b>零尾巴上的柱顶数值标签已关掉'
                f'（零高度的柱上印「0」不带信息，却会与次轴同比的「-100%」'
                f'钉在同一条零线上叠字）；逐格读数走右上角「表格」。')

    def ex_stock(self, n, gz, c):
        end = self.last_month(c)
        win = self.win_long(end)
        xl = [mlab(p) for p in win]
        v = self.vals(c, win)
        if self.flat0_skip(gz, [c], win, [v]):
            return None
        rhs = yoy_rhs(self.ser(c), win)
        ex = bar_ex(n, f'{gz}：{c["zh"]}（存量，期末口径）', c, xl, v, rhs, ylab2='% y/y')
        if rhs:      # 存量的次轴同比是点对点口径（月末快照 vs 去年同月月末）
            self.log_yoy(n, 'stock')
        ex['src_extra'] = 'Period-end stock, not a flow'
        tail0_zh = self.stock_tail0(ex, xl, v)
        hit = self.mark_breaks(ex, win, [c])
        ex['note'] = (
            tail0_zh +
            f'<b>存量（期末值）</b>，与本页其余「日均 / 当月合计」的流量列不是一回事：'
            f'流量按月累计发生，存量是某一天的截面，两者不能相加，跨币种换算时前者配月均'
            f'汇率、后者配月末汇率（本页只标注本币 {self.spec["ccy"]}，换算不在本页做）。'
            f'{xl[-1]} {unit_txt(v[-1], c)}，'
            + (f'同比 {chg_txt(c, v)}、环比 {chg_txt(c, v, lag=1)}。金色折线 = 次轴同比。'
               if rhs else f'环比 {chg_txt(c, v, lag=1)}。' + NO_YOY_NOTE)
            + self.slow_tail([c])
            + (self.brk_zh(hit, win) + '。' if hit else ''))
        return ex

    # ────────────────────── exhibit：分项占比（groups[].mix）──────────────────────
    #
    # 一条 `mix` 出两张图，**顺序固定**：先「合计的水平值柱 + 次轴同比」，再「分项 100%
    # 占比堆叠」。两张回答的是两个问题，合在一张图上必然要抢纵轴：
    #   · 柱图回答「这门生意有多大、在不在长」；
    #   · 占比图回答「结构往哪边走」—— 而占比最有价值的场合恰恰是「总量在涨、某一块的
    #     占比反而在掉」，那正是绝对量图上看不出来的。
    def mix_window(self, cols):
        """合计与全部分项**都有值**的、以 `WIN_FROM` 为左界的末端连续窗口。

        100% 堆叠是 DENSE 图型（`build/verify_pages.py` 的 `DENSE`）：窗口内一个 `null`
        都不许有 —— JS 会把它当 0 参与堆叠，画出一根凭空矮一截的柱，而且不报错。
        所以这里**只截不补**（同 `build/mrwin.py:26-30` 对 DENSE 的处理）：
          · 右端取「最后一个各列都有值的月」—— 慢腿页每个月初都会有一格这种空
            （本页头条已经发了、现货那半边还没发），那是正常状态不是故障；
          · 左端取「末端连续段的起点」再与 `WIN_FROM` 取晚 —— 中间真有洞时从洞之后起算，
            跨洞画等于把两段不相邻的历史画成相邻。
        """
        idx = list(self.df.index)
        mask = np.ones(len(idx), dtype=bool)
        for c in cols:
            mask &= np.isfinite(self.ser(c).values.astype(float))
        hits = np.flatnonzero(mask)
        if not len(hits):
            return None
        j = int(hits[-1])
        i = j
        while i - 1 >= 0 and mask[i - 1]:
            i -= 1
        lo = pd.Period(WIN_FROM, freq='M')
        while i < j and idx[i] < lo:
            i += 1
        return idx[i:j + 1]

    def mix_cut_zh(self, cols, win):
        """占比图的窗口为什么起止在这两个月 —— 逐列现算，不写死。

        没有这半句，读者在一张比同页别的图短的占比图上无从判断「左边那几年去哪了」：
        是源里本来就没有，还是我们挑了一段好看的。两种可能在图上长得一模一样。
        """
        lo = pd.Period(WIN_FROM, freq='M')
        ends, firsts = {}, {}
        for c in cols:
            ends[c['zh']] = self.last_month(c)
            ser = self.ser(c).dropna()
            firsts[c['zh']] = ser.index[0] if len(ser) else None
        bits = []
        # ── 右端：只有当**确实有列还能往右走**时才需要解释 ──
        later = [z for z, e in ends.items() if e is not None and e > win[-1]]
        if later:
            stops = [z for z, e in ends.items() if e == win[-1]]
            bits.append(f'右端停在 {mlab(win[-1])}：{"、".join(stops)} 到此为止'
                        f'（{"、".join(later)} 还有更晚的月份，但 100% 堆叠缺一列'
                        f'整根柱就不成立，所以按最短的那条截）')
        # ── 左端：三种可能，按判据分开说，不许含糊成一句「数据从这里开始」 ──
        starts = [z for z, f in firsts.items() if f is not None and f == win[0]]
        if win[0] == lo:
            bits.append(f'左端起于全站统一的 {mlab(win[0])}（各图共同的左界）')
        elif starts:
            bits.append(f'左端起于 {mlab(win[0])}：{"、".join(starts)} 这个月才有第一个值')
        else:
            bits.append(f'左端起于 {mlab(win[0])}：再往前，合计与各分项并非月月都有值，'
                        f'而 100% 堆叠是平滑图型、缺一格就把柱画塌，只能截不能补')
        return '<b>窗口口径</b>：' + '；'.join(bits) + '。'

    def mix_pair(self, n, g):
        """一条 `mix` → ([合计柱图, 占比堆叠图], 本组被这两张图吃掉的列名集合)。

        两张一起产出而不是各自成图，是为了让占比图能在图注里指名道姓地说
        「绝对量看 Exhibit k」—— 图号是算出来的，写死会在增删图之后指到错的图上
        （见 `log_yoy` 的 docstring 记的同一条教训）。
        """
        m, gz = g['mix'], g['zh']
        total, why_t = self.ex_mix_total(n, gz, m)
        # 合计柱没出（整列为空 / 窗口内恒为 0）时占比图顶上来占 n，图号不留洞。
        share, why_s = self.ex_mix_share(n + (1 if total else 0), gz, m,
                                         total_n=n if total else None)
        for w in (why_t, why_s):
            if w:
                self.skipped.append(w)
        if total is not None and share is not None:
            # 图号是算出来的，两边互指都在这里回填 —— 写死会在增删图之后指到错的图上
            # （`log_yoy` 的 docstring 记的是同一条教训）。
            total['note'] += (f'各分项的构成见 Exhibit {share["n"]}（100% 占比堆叠）—— '
                              f'本图只讲规模，那张只讲结构。')
        # 「哪几列算被这一组吃掉了」跟着**真画出来的图**走，不跟声明走：
        # 两张图各自都可能不出（合计整列为空、占比窗口不足 24 个月、某月合计 ≤0）。
        # 按声明扣列的后果是那几列的图**整批消失**而页面上没有任何痕迹 ——
        # 声明了一张画不出来的图，不该连带把本来画得出来的图也删掉。
        eaten = set()
        if total is not None:
            eaten.add(m['total']['col'])
        if share is not None:
            eaten |= {c['col'] for c in m['parts']}
        return [e for e in (total, share) if e is not None], eaten & g['declared']

    def mom_cost_zh(self, c):
        """单月同比的**代价**，拿这条序列自己实测 —— 只报数，不替它辩护。

        CONTRACT §6.1 第 2 条：用单月同比必须在图注里说明为什么。本页的理由是
        **页面所有者要求全页统一成单月口径**（一句可核对的事实，不是「看着更灵敏」）。
        但只写理由不写代价等于把话说了一半 —— 单月同比同时被交易日数、假期与到期日的
        月度形状、以及去年同月那一个数的高低推着走，毛刺可以大到与趋势符号相反。
        所以这里把两种口径的差**量出来印上去**，让读者知道自己在读什么。

        对照那一侧（12 个月滚动）只作参照、本页不画，按 12 个月**等权相加**算 ——
        日均列上这是个近似（各月交易日数不同），但用来量「两种口径差多远」够了，
        而且下面那句话会说明它是近似。算不出（历史不足 24 个月）就整段不印。
        """
        s_ = self.ser(c)
        roll = s_.rolling(TTM_WIN, min_periods=TTM_WIN).sum()
        b_all = (roll / roll.shift(12) - 1).values.astype(float) * 100
        a_all = (s_ / s_.shift(12) - 1).values.astype(float) * 100
        m = np.isfinite(a_all) & np.isfinite(b_all)
        if int(m.sum()) < 24:
            return ('<b>口径：本图次轴是单月同比</b>（当月对去年同月），'
                    '全页统一 —— 页面所有者指定。本序列历史不足以与滚动口径对照，'
                    '此处不报差异。')
        a = np.where(m, a_all, np.nan)
        b = np.where(m, b_all, np.nan)
        idx = list(self.df.index)
        ja = float(np.nanmax(np.abs(np.diff(a))))
        jb = float(np.nanmax(np.abs(np.diff(b))))
        i_ja = int(np.nanargmax(np.abs(np.diff(a))))
        opp = int(np.nansum((a * b) < 0))
        k_gap = int(np.nanargmax(np.abs(a - b)))
        sd_a, sd_b = float(np.nanstd(a, ddof=1)), float(np.nanstd(b, ddof=1))
        return (
            f'<b>口径：本图次轴是<u>单月</u>同比</b>（当月对去年同月），全页统一 —— '
            f'页面所有者指定，不是底座的默认口径（CONTRACT §6.1 把 {TTM_WIN} 个月'
            f'滚动合计的同比定为流量的默认，单月要在标题里写明并在这里交代，两条都照办）。'
            f'<b>代价用本序列自己实测</b>（{int(m.sum())} 个两种口径都算得出的月份，'
            f'滚动那一侧只作对照、本页不画，按 {TTM_WIN} 个月等权相加算，'
            f'日均列上是个近似）：单月同比的逐月标准差 {ppbp_abs(sd_a)}、'
            f'滚动 {ppbp_abs(sd_b)}；相邻月最大跳变 {ppbp_abs(ja)}'
            f'（{idx[i_ja]} → {idx[i_ja + 1]}）vs {ppbp_abs(jb)}；'
            f'两者<b>符号相反</b>的月份 {opp} 个（占 {opp / int(m.sum()) * 100:.0f}%），'
            f'差得最远的是 {idx[k_gap]}（单月 {nz_txt(f"{a[k_gap]:+.1f}")}% '
            f'vs 滚动 {nz_txt(f"{b[k_gap]:+.1f}")}%）。'
            f'⇒ <b>这条线要连着柱高一起读</b>：低基数月份它会被放大，'
            f'单看它挑月份能把结论说成两个方向。')

    def ex_mix_total(self, n, gz, m):
        """`mix` 的第一张：合计列的水平值柱 + 次轴**单月**同比。

        ⚠️ **这里曾经是 12 个月滚动同比，2026-09 按页面所有者的指令改成单月。**
        CONTRACT §6.1 第 1 条把滚动定为流量的默认口径，第 2 条允许用单月但要求
        「标题里写明 + 图注说明为什么」—— 两条都照办了：标题带「单月同比」四个字
        （`tools/check_yoy_caliber.py` 的 R4 只认 title/ylab2/legend/yoy.name 这四处），
        理由由 `mom_cost_zh()` 连同**实测代价**一起印在图注里。
        理由是「页面所有者要求全页统一口径」——这是一句可核对的事实，不是
        「看着更灵敏」那种被 §6.1 点名禁止的说法；而它的代价（毛刺、符号相反的月份）
        必须同时印出来，不能只写结论。

        存量列本来就走点对点同比（12 个月末快照相加不指代任何量），不受这次改动影响。
        """
        c = m['total']
        end = self.last_month(c)
        if end is None:
            return None, f'{gz}：{c["col"]} 整列为空，合计柱不出'
        win = self.win_long(end)
        xl = [mlab(p) for p in win]
        v = self.vals(c, win)
        if self.flat0_skip(gz, [c], win, [v]):
            return None, f'{gz}：{c["zh"]} 窗口内恒为 0，合计柱不出'
        rhs = yoy_rhs(self.ser(c), win)
        if c['stock']:
            # 标题里的「（存量，期末口径）」不是排版修辞：`tools/check_yoy_caliber.py`
            # 的 `_STOCK_TXT` 认这几个字，认到了才把 R1/R4（单月同比未声明）整条豁免掉 ——
            # 点对点同比正是存量的合法默认口径。措辞与 `ex_stock` 保持逐字相同。
            ex = bar_ex(n, f'{gz}：{c["zh"]}（存量，期末口径）—— 水平值与点对点同比',
                        c, xl, v, rhs, ylab2='% y/y')
            if rhs:
                self.log_yoy(n, 'stock')
            ex['src_extra'] = 'Period-end stock, not a flow'
            tail0_zh = self.stock_tail0(ex, xl, v)
            hit = self.mark_breaks(ex, win, [c])
            ex['note'] = (
                tail0_zh +
                f'深蓝柱 = {c["zh"]}的<b>水平值</b>（{c["unit"]}，官方原始口径）。'
                f'{self.win_zh(win)}。'
                + (f'金色折线（右轴）= <b>点对点同比</b>（本月末 vs 去年同月末）。'
                   f'<b>存量不做 {TTM_WIN} 个月滚动合计</b>：把 12 个月末的快照加起来'
                   f'既不是「一年的量」（存量不累积）也不是「平均水平」（没除以 12），'
                   f'那是一句关于自己算术的假话（CONTRACT §6.1 第 4 条）。'
                   if rhs else NO_YOY_NOTE)
                + f'{xl[-1]} {unit_txt(v[-1], c)}，'
                + (f'同比 {chg_txt(c, v)}、环比 {chg_txt(c, v, lag=1)}。'
                   if rhs else f'环比 {chg_txt(c, v, lag=1)}。')
                + '<b>存量与本页的流量列不能相加</b>：流量按月累计发生，存量是某一天的截面。'
                + self.slow_tail([c])
                + (self.brk_zh(hit, win) + '。' if hit else '')
                + (' ' + md_bold(m['note']) if m['note'] else ''))
            return ex, None

        ex = bar_ex(n, f'{gz}：{c["zh"]} —— 水平值与单月同比', c, xl, v, rhs,
                    ylab2='% y/y（单月）')
        if rhs:
            self.log_yoy(n, 'mom')
        hit = self.mark_breaks(ex, win, [c])
        ex['note'] = (
            f'深蓝柱 = {c["zh"]}的<b>水平值</b>（{c["unit"]}，原始单位，未做任何指数化）。'
            f'{self.win_zh(win)}。'
            + (f'金色折线（右轴）= <b>单月同比</b>（当月对去年同月，'
               f'{c["col"]} 自己除自己，不换列、不做任何还原）。'
               if rhs else NO_YOY_NOTE)
            + f'{xl[-1]} 水平值 {unit_txt(v[-1], c)}，同比 {chg_txt(c, v)}、'
              f'环比 {chg_txt(c, v, lag=1)}。'
            + self.mom_cost_zh(c)
            + self.slow_tail([c])
            + (self.brk_zh(hit, win) + '。' if hit else '')
            + (' ' + md_bold(m['note']) if m['note'] else ''))
        return ex, None

    def ex_mix_share(self, n, gz, m, total_n=None):
        """`mix` 的第二张：分项占合计的比重，**100% 堆叠柱**（`stacked_dual`）。

        **缺省不给右轴那条线**：占比型堆叠里各段之和恒为 100，段高本身就把每一块读出来了，
        再拿其中一段换个刻度画一遍是同一个数说两遍（`build/CONTRACT.md` §3 的
        `stacked_dual` 那一行、`docs/CHART_KINDS.md` §3.14 同一条）。
        唯一的例外由 spec 的 `rhs_share` 显式打开，判据见下面那段注释。

        **加总关系在这里逐月复算，不信 spec 的自述**：
          · 残差为负（分项之和 > 合计）→ 硬失败。那说明分子分母不是同一个口径，
            而图上只会画成一根更高的柱，没有任何护栏会响。
          · 残差为正且超过 `MIX_RESID_TOL` 却没给 `residual_zh` → 硬失败。
            那种图会声称「堆叠 = 100%」而实际不是。
          · 声明了 `residual_zh` 而残差恒为 0 → 也硬失败：一条恒为 0 的「其他」段
            会让读者以为存在一块查不到的业务。
        """
        tot_c, parts = m['total'], m['parts']
        cols = [tot_c] + parts
        win = self.mix_window(cols)
        got = 0 if win is None else len(win)
        if got < MIX_MIN_MONTHS:
            return None, (f'{gz}：合计与全部分项都有值的连续窗口只有 {got} 个月'
                          f'（不足 {MIX_MIN_MONTHS} 个月），占比堆叠不出 —— '
                          f'100% 堆叠是 DENSE 图型，窗口只能截不能补')
        tv = self.vals(tot_c, win)
        pvs = [self.vals(c, win) for c in parts]
        if float(np.min(tv)) <= 0:
            k = int(np.argmin(tv))
            return None, (f'{gz}：{tot_c["zh"]} 在 {mlab(win[k])} 为 '
                          f'{fmt_val(tv[k], tot_c["fmt"])}（≤0），占比无定义，本图不出')
        resid = tv - np.sum(pvs, axis=0)
        rel = resid / tv
        k_lo, k_hi = int(np.argmin(rel)), int(np.argmax(rel))
        # 容差之内的**负**残差是几亿的数相减剩下的浮点噪声（实测 -1e-16 量级）。
        # 不钳掉的话它会以两种方式上页面：图注里印出「窗口内在 -0.0%…」，
        # 而引擎会给那一段画一个负高度的 rect（`Math.max(0, …)` 兜住了高度，
        # 但 base[i] 已经被减过头，上面各段整体下移）。两者都不报错。
        # 只钳容差之内的：真的超出容差就该在上面那两条硬失败里炸掉，不该被悄悄抹平。
        if float(rel[k_lo]) < -MIX_RESID_TOL:
            raise SpecError(
                f'groups「{gz}」.mix：分项之和在 {mlab(win[k_lo])} **超过**合计 '
                f'{abs(float(rel[k_lo])) * 100:.4g}%'
                f'（{tot_c["zh"]} {fmt_val(tv[k_lo], tot_c["fmt"])} vs 分项之和 '
                f'{fmt_val(float(tv[k_lo] - resid[k_lo]), tot_c["fmt"])}）—— '
                f'子集关系不成立时占比大于 100%，而图上只会画成一根更高的柱。'
                f'请核对两边是不是同一个口径，或者换一条真正是合计的列')
        big = float(rel[k_hi])
        if big > MIX_RESID_TOL and not m['residual_zh']:
            raise SpecError(
                f'groups「{gz}」.mix：{"、".join(c["zh"] for c in parts)} 之和'
                f'并不等于 {tot_c["zh"]} —— 残差最大出现在 {mlab(win[k_hi])}，'
                f'占合计 {big * 100:.4g}%（{fmt_val(float(resid[k_hi]), tot_c["fmt"])} '
                f'{tot_c["unit"]}）。这张图会声称「堆叠 = 100%」，所以残差必须画出来：'
                f"请给 mix 加一个 'residual_zh'，用它说清楚那一块是什么"
                f'（官方未单列的品种？已停的旧合约？），别让它消失')
        if big <= MIX_RESID_TOL and m['residual_zh']:
            raise SpecError(
                f'groups「{gz}」.mix 声明了 residual_zh={m["residual_zh"]!r}，'
                f'但窗口内 {mlab(win[0])}–{mlab(win[-1])} 分项之和逐月恰等于合计'
                f'（最大残差 {big * 100:.2g}%，在容差 {MIX_RESID_TOL:.0e} 之内）—— '
                f'一条恒为 0 的「其他」段会让读者以为存在一块查不到的业务。请删掉它')

        palette = MIX_SEG_COLORS[len(parts)]
        segs = [(c['zh'], pvs[i] / tv * 100, palette[i]) for i, c in enumerate(parts)]
        if m['residual_zh']:
            segs.append((m['residual_zh'], np.maximum(resid, 0.0) / tv * 100,
                         MIX_RESID_COLOR))
        # 收尾自检：各段之和必须逐格等于 100。
        # ⚠️ **单位要与 `MIX_RESID_TOL` 对齐**：那个阈值是**相对值**（残差 ÷ 合计），
        # 而这里量的是**百分点**。曾经两边都写 1e-6，差了 100 倍 —— 相对残差落在
        # 1e-8~1e-6 之间的月份，上面的硬失败放它过（在容差内），这里却会炸。
        ssum = np.sum([sv for _z, sv, _c in segs], axis=0)
        off = float(np.max(np.abs(ssum - 100.0)))
        if not off <= MIX_RESID_TOL * 100 + 1e-9:
            raise SpecError(f'groups「{gz}」.mix：各段之和偏离 100% 达 {off:.3e}pp'
                            f'（上限 {MIX_RESID_TOL * 100:.0e}pp）—— 底座算错了')

        ex = {
            'n': n, 'kind': 'stacked_dual', 'height': 340, 'fmt': 'pct1', 'xrot': 90,
            # 标题不写「{列名}的分项构成」：本仓的列名多半以拉丁字母收尾
            # （「股指期货合计 ADV」「CGB（10 年）」），后面直接跟「的」会挤成「ADV的」。
            # 把分母放进括号既避开了这个，又把「占谁的比重」摆在最显眼的位置。
            'title': f'{gz}：各分项占比（分母 = {tot_c["zh"]}，堆叠 = 100%）',
            'xlabels': [mlab(p) for p in win],
            'ylab': f'% of {axis_short(tot_c["zh"], 18)}（堆叠 = 100%）',
            'stacks': [{'name': zh, 'color': cc, 'values': LN(sv), 'label': False}
                       for zh, sv, cc in segs],
            'src_extra': ('Shares are computed as each component divided by the disclosed '
                          'total on the same row; the stacks sum to 100% by construction'),
        }
        # ── 可选：把其中**一段**换个刻度在右轴上重画一遍 ────────────────────────
        # 缺省不画（`build/CONTRACT.md` §3 的 `stacked_dual` 那一行：占比型堆叠里
        # 各段之和恒为 100，段高本身已经把每一块读出来了，再画一遍是同一个数说两遍）。
        # 例外只有一种，也正是 `/exchanges-eu/` Ex2 立这条例外的理由：某一段常年只占
        # 几个百分点，在 0–100 的堆叠里它几个 pp 的变化根本量不出来。
        # ⚠️ 这条线**不是第四个量**，`_norm_mix` 只许它指向 parts 里的一段或残差段。
        rhs_line = ''
        if m['rhs_share']:
            k_r = (len(segs) - 1 if m['rhs_share'] == 'residual'
                   else [c['col'] for c in parts].index(m['rhs_share']))
            zh_r, sv_r = segs[k_r][0], segs[k_r][1]
            # 线色不能与**任何一段**撞：polyline 无描边、画在柱之后，同色时它穿过那一段
            # 整段看不见（`build/mrbase.py` 的 `_SEG_COLORS` 上方记着同一条实测教训）。
            # 从前写死 GREEN，而 GREEN 现在进了 5 段那档的配色表 —— 那就是一颗定时炸弹。
            used = {cc for _z, _v, cc in segs}
            c_line = next((x for x in ('GREEN', 'GOLD', 'MBLUE', 'BLUE') if x not in used),
                          None)
            if c_line is None:
                raise SpecError(
                    f'groups「{gz}」.mix 要画右轴线，但 6 个数据色已经被 {len(segs)} 段'
                    f'占满（{"、".join(sorted(used))}），没有一个色留给这条线 —— '
                    f'同色的线穿过那一段整段看不见。要么去掉 rhs_share，'
                    f'要么先把小分项并进残差')
            ex['line'] = {'name': f'{zh_r}（RHS）', 'color': c_line, 'values': LN(sv_r),
                          # 右轴下界被引擎写死成 0，只能调上界；留 15% 顶空免得线贴轴顶。
                          'ymax': nice_max(float(np.max(sv_r)) * 1.15)}
            ex['ylab2'] = f'{axis_short(zh_r)}，%（右，同一条序列换个刻度）'
            rhs_line = (f'<b>右轴那条绿线不是新的量</b>：它就是「{zh_r}」这一段'
                        f'换成 0–{ex["line"]["ymax"]}% 的刻度重画一遍 —— '
                        f'这一段在 0–100 的堆叠里只占几个百分点，几 pp 的变化在那里量不出来。'
                        f'柱顶上方那排绿色的百分比是它的读数（`assets/charts.js` 的 '
                        f'thinLabels 会按密度抽稀，不是每一期都标；逐格读数走「表格」）。')
        hit = self.mark_breaks(ex, win, cols)
        rng = []
        for zh, sv, _cc in segs:
            lo_i, hi_i = int(np.argmin(sv)), int(np.argmax(sv))
            rng.append(f'{zh} 最新 {share_txt(sv[-1])}%，窗口内在 {share_txt(sv[lo_i])}%'
                       f'（{mlab(win[lo_i])}）到 {share_txt(sv[hi_i])}%（{mlab(win[hi_i])}）之间')
        rz = ''
        if m['residual_zh']:
            # ⚠️ 这里**不许**写「它不是一条披露列」：底座只知道自己是拿减法算出来的，
            # 不知道源表里有没有一条列恰好等于它（本仓就有这种情形 —— tmx 现货三张图的
            # 残差逐月恰等于 Alpha-X & Alpha DRK，而那三条列同页另有自己的图）。
            # 所以这里只说**能证明的**：它是算出来的。它到底是什么，由 spec 的
            # `share_note` 逐家交代。
            rz = (f'<b>最上面那段是<u>算出来的</u>残差，不是直接取自某一条列</b>：'
                  f'残差 ≡ {tot_c["zh"]} − {"、".join(c["zh"] for c in parts)}，'
                  f'本页把它叫作「{m["residual_zh"]}」。'
                  f'窗口内它最大占到 <b>{big * 100:.2f}%</b>（{mlab(win[k_hi])}）、'
                  f'最新 {float(rel[-1]) * 100:.2f}%。'
                  f'把它画出来而不是删掉，是因为删掉之后各段之和就不是 100 了，'
                  f'而图上仍会写着「堆叠 = 100%」。'
                  + (f'⚠️ <b>但它在图上看不见</b>：最高的那个月也只占柱高 '
                     f'{big * 100:.2f}%，而引擎在每两段之间留 1.5px 白缝，'
                     f'低于 {MIX_TINY_SEG_PCT}% 的段扣完白缝高度就是 0。'
                     f'图例里那一格与这段话是它在本图上仅有的痕迹，'
                     f'逐月读数走卡片右上角的「表格」。'
                     if big * 100 < MIX_TINY_SEG_PCT else ''))
        else:
            # 「最大偏差 0%，只是 float64 舍入」是自相矛盾的：恰为 0 就不是舍入。
            # 两种情形分开说 —— 恒等式**精确**成立与「残差小到只剩浮点噪声」不是一回事。
            gap = (f'逐月<b>分毫不差</b>，残差恰为 0' if big == 0.0 else
                   f'最大偏差 {big * 100:.2g}%，只是 float64 舍入')
            rz = (f'<b>没有残差段</b>：{"、".join(c["zh"] for c in parts)} 之和'
                  f'在窗口内逐月恰等于{tot_c["zh"]}（{gap}），'
                  f'所以这张图的分母没有任何一块落在名单之外。')
        ex['note'] = (
            f'<b>占比是现算的：分项 ÷ {tot_c["zh"]}</b>（同一行的两个数相除，'
            f'不是各分项互相之间的比例）。{self.win_zh(win)}。'
            + ('<b>本图是存量口径的占比</b>：分子分母都是月末快照，'
               '读作「月末的未平仓/余额里各占多少」，不是「这个月新做了多少」。'
               if tot_c['stock'] else '')
            + f'<b>每根柱恒高 100%</b>，所以这张图只讲<b>结构</b>、一个字都没讲规模 —— '
              f'柱高一样不代表那个月的量一样。'
            + '；'.join(rng) + '。'
            + rz
            + ('<b>本图只有两段，两者互补</b>（和恒为 100%）：看其中一段的进退'
               '就等于看另一段的反向进退，不是两个独立的量。'
               if len(segs) == 2 else '')
            + '<b>占比动了不等于哪一块变差了</b>：分母是合计，'
              '一块绝对量原地不动、另一块猛涨，前者的占比照样往下走。'
            # ⚠️ 合计的绝对量与**分项**的绝对量在两个地方，别混着指：
            # 合计柱那张图只画合计那一条列，分项的水平值只在末尾核对表里。
            + (f'<b>合计</b>的绝对量看 Exhibit {total_n}（合计柱）；' if total_n else '')
            + '<b>各分项</b>的绝对量在末尾核对表里（本图一个绝对量都没画）。'
            + rhs_line
            + '段内不标数值：引擎的段内标签写死 6.6px 且只印整数，'
              '压在深色段上会糊成一片；逐格读数走卡片右上角的「表格」。'
            + self.mix_cut_zh(cols, win)
            + self.slow_tail(cols)
            + (self.brk_zh(hit, win) + '。' if hit else '')
            + (' ' + md_bold(m['share_note']) if m['share_note'] else ''))
        return ex, None

    # ────────────────────── exhibit：季节性 ──────────────────────
    def ex_season(self, n, c):
        s = self.ser(c).dropna()
        end = self.last_month(c)
        win = self.win(end, WIN_SHORT)
        base, used = [], []
        for p in win:
            prior = [s.get(p - 12 * k, np.nan) for k in range(1, SEASON_YEARS + 1)]
            prior = [float(x) for x in prior if x is not None and np.isfinite(x)]
            used.append(len(prior))
            base.append(float(np.mean(prior)) if prior else np.nan)
        nyr = max(used) if used else 0
        if not nyr:
            return None
        act = self.vals(c, win)
        ex = {
            'n': n, 'kind': 'seasonality', 'fmt': c['fmt'], 'label_fmt': c['fmt'],
            'xlabels': [mlab(p) for p in win],
            'title': f'{c["zh"]}：与同月常态比',
            'ylab': c['unit'],
            '_cols': [c['col']],                     # 见 ex_history 里对 `_cols` 的说明
            'base': {'name': f'过去 {nyr} 年同月均值', 'color': 'GRAY', 'values': LN(base)},
            'actual': {'name': '实际', 'color': 'MBLUE', 'values': LN(act)},
        }
        self.mark_breaks(ex, win, [c])
        d = act[-1] - base[-1] if np.isfinite(base[-1]) else np.nan
        # 比率列与同月常态的差同样走百分点，不走「百分比的百分比」
        gap = ppf(d) if self.is_ratio(c) else pctf((d / base[-1]) if (np.isfinite(d) and base[-1])
                                                   else np.nan)
        ex['note'] = (
            f'灰柱 = 该月份在过去最多 {SEASON_YEARS} 年里的同月均值（实际用到 {nyr} 年，'
            f'哪个月有几年就用几年，缺的年份不补），蓝柱 = 实际。'
            f'交易所的量有稳定的月度形状（假期、到期日、季末再平衡），'
            f'看同比之外还要看「相对自己的同月常态」。'
            f'{mlab(win[-1])} 实际 {unit_txt(act[-1], c)} vs 同月常态 '
            f'{fmt_val(base[-1], c["fmt"]) or "—"}（{gap}）。')
        return ex

    # ═══════════ exhibit：量价分解 与 12 个月滚动同比（共用的取数口径） ═══════════
    def monthly_total(self, c, total_col, weight_col, gran, where):
        """一列 → **当月合计**口径的序列，外加一份口径对账记录。

        为什么非做这一步不可：本仓的量与额多半存成「日均」（ADT / ADV），而各月立会日数
        在 18–23 天之间浮动。把日均直接跨月相加，等于给每个月同样的权重，年度均价
        Σ金额 ÷ Σ股数 就用错了权重 —— 交易日多的月份被低配，交易日少的月份被高配，
        偏差随月份分布走，方向不固定。所以年度口径一律先还原成当月合计再相加。

        三条路，优先级从高到低：
          1. `total_col` —— 源表自带的当月合计列（最可信：官方自己发的）
          2. `weight_col` —— 日均 × 立会日数（源表没发合计列时的还原）
          3. 都不给 —— 该列本身就是当月合计口径

        **两条都给时互相对账**：`日均 × 权重` 与 `当月合计列` 的最大相对偏差超过
        `TOTAL_TOL` 就硬失败。这一条不是形式主义 —— 它正是「用 weight_col 去还原另一列」
        这件事的许可证：同一个权重列能把 A 列还原成 A 的官方合计，才有理由相信它也能
        把同一张表的 B 列还原对。对不上就说明两列的立会日数口径不是一回事，
        那么用它还原出来的年度合计是错的，而错在哪一根柱上完全看不出来。
        """
        s = self.ser(c)
        w = self.df[weight_col].astype(float) if weight_col else None
        t = self.df[total_col].astype(float) if total_col else None
        gap = None
        if t is not None and w is not None:
            a, b = (s * w).values.astype(float), t.values.astype(float)
            m = np.isfinite(a) & np.isfinite(b) & (b != 0)
            if not m.any():
                raise SpecError(f'{where}：{c["col"]} × {weight_col} 与 {total_col} '
                                f'没有任何一个月能对账 —— 两列没有共同的有值月份')
            gap = float(np.max(np.abs((a[m] - b[m]) / b[m])))
            if not gap <= TOTAL_TOL:
                raise SpecError(
                    f'{where}：{c["col"]} × {weight_col} 与源表自带的 {total_col} '
                    f'最大相对偏差 {gap:.3e} > {TOTAL_TOL:.0e}（{int(m.sum())} 个月）—— '
                    f'两列不是同一个立会日数口径，用 {weight_col} 还原出来的当月合计不可信')
        if t is not None:
            how = (f'源表自带的当月合计列 <code>{total_col}</code>'
                   + (f'（已与 {c["col"]} × <code>{weight_col}</code> 逐月对账，'
                      f'最大相对偏差 {gap:.1e}）' if gap is not None else ''))
            return t, how
        if w is not None:
            return s * w, (f'{c["zh"]}是<b>当月日均</b>，× <code>{weight_col}</code> '
                           f'还原成当月合计（源表没有现成的合计列）')
        if gran == 'monthly_total':
            return s, f'<code>{c["col"]}</code> 本身即<b>当月合计</b>口径，未做还原'
        # 日均、又没有任何权重列可用。这一支**必须把话说满**：等权相加是一个近似，
        # 偏差随各月交易日数的离散程度走，本页量不出来（没有交易日列就是没有）。
        # 早先这里无条件印「本身即当月合计口径」——对日均列那是一句假话，
        # 而 verify_pages 只看 payload 结构、看不出图注对不对。
        return s, (f'⚠️ <code>{c["col"]}</code> 是<b>当月日均</b>，而本页没有可用的'
                   f'交易日权重列，年度只能按月<b>等权</b>相加。各月交易日数不同，'
                   f'这一步带一个<b>本页量不出来</b>的权重偏差（要消掉它，'
                   f'得让 fetch 层把该口径的交易日数落成一列，再填进 weight_col）')

    def _years(self, start_month, series_list):
        """→ [(年份, [该年的 12 个月]), …]，只保留 12 个月齐全且各列都有值的完整年度。

        缺月的年份直接丢掉，不按 11 个月折算成 12 个月 —— 折算要假设缺的那个月与其余
        月份同分布，而缺月最常见的原因恰恰是「那个月不正常」。
        """
        buckets = {}
        for p in self.df.index:
            y = p.year if p.month >= start_month else p.year - 1
            buckets.setdefault(y, []).append(p)
        out = []
        for y in sorted(buckets):
            ms = buckets[y]
            if len(ms) != 12:
                continue
            if all(np.isfinite(s.reindex(ms).values.astype(float)).all() for s in series_list):
                out.append((y, ms))
        # 只保留末尾**逐年连续**的一段：中间断一年就把两个不相邻的年度画成相邻柱，
        # 那根柱上的「同比」实际上跨了两年（同 tail_contiguous 的道理）。
        run = out[-1:]
        for k in range(len(out) - 2, -1, -1):
            if out[k][0] != run[0][0] - 1:
                break
            run.insert(0, out[k])
        return run

    def _ytd(self, start_month, series_list, run):
        """最新一个**不完整**年度的 YTD 桶 → (年份, 当年月份, 去年同月月份)；凑不出返回 None。

        `_years` 只收完整年度，最新年不满 12 个月时整年被丢掉 —— 于是「今年到目前
        为止发生了什么」在分解图上是空白。这个方法把那半年捡回来，但**同比基期必须
        对齐到去年同期月份**：基期 = 当年每个入选月各自减 12 个月，两侧月份集合
        **逐月相同**。不对齐就是拿 k 个月比 12 个月，柱高毫无意义。

        窗口从该年首月（start_month）起逐月推进，**任一侧**（当月或去年同月）任一列
        缺值即止 —— 某条腿滞后一个月时，YTD 就停在两侧数据都齐的最后一个月，
        实际截至月由图注现算写明。首月就不齐则没有 YTD 桶（从年中起算的「YTD」是假话）。

        只对 run 的下一年找 YTD：基期月份因此全部落在最后一个完整年里（该年 12 个月
        各列都验过有值），不会拿一个自身带洞的年份当基期。
        """
        if not run:
            return None
        y = run[-1][0] + 1
        idx = set(self.df.index)
        ms = []
        p = pd.Period(f'{y}-{start_month:02d}', freq='M')
        while p in idx and len(ms) < 12:
            q = p - 12
            if q not in idx:
                break
            if not all(np.isfinite(float(s.get(p, np.nan)))
                       and np.isfinite(float(s.get(q, np.nan))) for s in series_list):
                break
            ms.append(p)
            p += 1
        if not ms or len(ms) == 12:
            # 12 个月齐 = 那本来就是完整年，_years 会收；能走到这里而 run 没收它，
            # 说明有别的洞 —— 宁可不出 YTD，也不造一根冒充完整年的柱。
            return None
        return y, ms, [m - 12 for m in ms]

    def ex_decomp(self, n, d):
        """金额增长 → 量的贡献 + 派生量的贡献。横轴一格 = 一个完整年度；
        最新年不完整时**末格追加一根 YTD 柱**（同比基期对齐到去年同期月份，见 _ytd）。

        恒等式 **金额 ≡ 数量 × 派生量**（派生量 ≡ 金额 ÷ 数量）是定义式，零假设零误差。
        由它能写出两种分解，本方法**两种都算**：

          算术：g_V = g_Q + g_P + g_Q·g_P        ← 有交叉项，只进图注
          对数：ln(V₁/V₀) = ln(Q₁/Q₀) + ln(P₁/P₀)  ← 可加、无残差，**画在图上**

        **为什么图上必须用对数。**算术分解的交叉项 g_Q·g_P 不是可以忽略的余项：
        量与价一涨一跌（这在交易所数据里是常态）时它与净增长同量级、甚至几倍于净增长，
        堆叠柱根本堆不出来 —— 三块里两块巨大反号、第三块是它们的乘积，读者只能看出
        「有三根柱」，看不出任何归因。对数分解没有交叉项，两块相加恒等于总量。

        **画在图上的是「对数权重重标定」后的两块**：
            w = g_V / ln(V₁/V₀)，  贡献_量 = w·ln(Q₁/Q₀)，  贡献_价 = w·ln(P₁/P₀)
        两块相加 = w·ln(V₁/V₀) = g_V，**逐格等于菱形标的总增长**（就是页面其它地方那个
        同比 %），所以纵轴仍然是 %，读者不必在「对数点」和「百分比」之间换算。
        w 是一个恒等变换的比例因子，不是权重假设：它对量与价一视同仁，
        没有把任何一部分残差偷偷分配给谁。

        **w 在 V₁ ≈ V₀ 时不稳。**解析上 w → 1（g_V 与 ln 同阶无穷小），不会发散；
        但数值上那是 0/0，两个都由大数相减得来的小量相除，有效位会被吃光。
        所以 |ln(V₁/V₀)| < DECOMP_LN_MIN 的那一格**整根留空**，不印一个算不准的数。

        横轴是年度类别轴，因此 `xrot: 0`，且**不调 mark_breaks** —— 断点索引是按月份
        窗口算出来的，扣到年度轴上会把红虚线画到错的柱子上（断点仍在页尾说明里列着）。
        """
        gran = d['granularity']
        v_s, v_how = self.monthly_total(d['value'], d['value_total_col'], d['weight_col'],
                                        gran, f'decomp「{d["zh"]}」的金额列')
        q_s, q_how = self.monthly_total(d['qty'], d['qty_total_col'], d['weight_col'],
                                        gran, f'decomp「{d["zh"]}」的数量列')
        bench = bool(d['bench_value'] and d['bench_qty'])
        need = [v_s, q_s]
        bv_s = bq_s = None
        if bench:
            # 行业对照走**同一条** monthly_total（同一套 total_col / weight_col / 粒度）——
            # 自家按合计、行业按日均的话，份额 s 会带一个逐月漂移的假趋势。
            bv_s, _ = self.monthly_total(d['bench_value'], None, d['weight_col'],
                                         gran, f'decomp「{d["zh"]}」的行业金额列')
            bq_s, _ = self.monthly_total(d['bench_qty'], None, d['weight_col'],
                                         gran, f'decomp「{d["zh"]}」的行业数量列')
            need += [bv_s, bq_s]
        start = d['year_start_month']
        run = self._years(start, need)
        sel = run[-(d['years'] + 1):]
        # YTD 桶**只对日历年**追加（start == 1）。本仓的 YTD 口径按用户指令
        # （2026-08-07）定义在日历年上：「按日历年 Jan–Dec……今年数据出到 7 月，
        # 用 YTD 表示」。财年制的页不自动加 —— 比如 7 月制财年在 8 月的「FYTD」
        # 只有 1 个月，那正是本图注明确反对的「拿单月当端点」；财年页要加 YTD，
        # 得先对「FYTD 从几个月起才有意义」另定口径，不许在这里顺手继承。
        ytd = self._ytd(start, need, run) if start == 1 else None
        if len(sel) < 2 and ytd is None:
            return None, (f'{d["zh"]}：完整年度只有 {len(run)} 个（起始月 {start}），'
                          f'画不出任何一根「相对上一年」的柱，也凑不出两侧月份对齐的 YTD 桶')

        # 每格合计的单位**不是**展示列的单位（日均列的 12 个月合计是「兆円/年」，
        # 不是「兆円/日」），拿展示单位去标它就是印错单位。所以图注里报的是把该格合计
        # 除回展示口径的**窗口内均值**：有权重列就除以同窗口权重合计（= 窗口内日均，
        # 与日均列同单位），没有就除以窗口月数（完整年 = 12，YTD = 实际月数；
        # = 窗口内月均，与月合计列同单位）。两种都回到展示单位。
        wcol = self.df[d['weight_col']].astype(float) if d['weight_col'] else None

        def agg_one(y, label, ms):
            """一个桶（完整年或 YTD 窗口）→ 行 tuple 或 (None, 原因)。

            行结构 (年份, V, Q, P, V均, Q均, BV, BQ, 月数)：完整年月数恒为 12，
            YTD 桶是实际入选月数 —— 图注报「窗口内均值」时要用它当除数。
            """
            V = float(v_s.reindex(ms).values.astype(float).sum())
            Q = float(q_s.reindex(ms).values.astype(float).sum())
            if not (V > 0 and Q > 0):
                return None, (f'{d["zh"]}：{label}的合计不是正数（金额 {V:g}、数量 {Q:g}），'
                              f'比值与对数都没有定义，不出这张图')
            div = (float(wcol.reindex(ms).values.astype(float).sum())
                   if wcol is not None else float(len(ms)))
            if not div > 0:
                return None, (f'{d["zh"]}：{label}的 {d["weight_col"]} 合计为 {div:g}，'
                              f'除不回展示口径')
            row = [y, V, Q, V / Q * d['price_scale'], V / div, Q / div, None, None, len(ms)]
            if bench:
                BV = float(bv_s.reindex(ms).values.astype(float).sum())
                BQ = float(bq_s.reindex(ms).values.astype(float).sum())
                if not (BV > 0 and BQ > 0):
                    return None, (f'{d["zh"]}：{label}的行业合计不是正数'
                                  f'（金额 {BV:g}、数量 {BQ:g}），份额与相对价没有定义')
                row[6], row[7] = BV, BQ
            return tuple(row), None

        agg = []
        for y, ms in sel:
            row, err = agg_one(y, f'{y} 年', ms)
            if err:
                return None, err
            agg.append(row)

        # 年度 → 柱标签只此一处映射。早先「基期」那句直接印了原始桶年（2015），
        # 而同一句里其余标签是 FY 制（FY2016…），读者会以为基期是日历 2015 年。
        # 映射写两遍就一定会漏用一处，所以收敛成一个闭包。
        def ylab(y):
            if start == 1:
                return f'{y}'
            return f'FY{y + (1 if d["year_label"] == "end" else 0)}'

        # 柱 = 相邻两个完整年的对比，末尾可追加一根 YTD 柱。**YTD 的基期不是上一根
        # 完整年柱**，而是去年同一批月份（_ytd 已保证两侧逐月对齐）—— 所以这里改成
        # 显式的 (标签, 本期行, 基期行) 三元组，不再用 zip(agg[1:], agg[:-1]) 隐含
        # 「基期 = 前一行」：那个隐含对 YTD 是错的，而图上完全看不出来。
        pairs = [(ylab(r1[0]), r1, r0) for r1, r0 in zip(agg[1:], agg[:-1])]
        ytd_info = None
        if ytd is not None:
            y_t, ms_cur, ms_prev = ytd
            lab_t = f'{ylab(y_t)} YTD'
            cur, err = agg_one(y_t, f'{lab_t}（{ms_cur[0]}…{ms_cur[-1]}）', ms_cur)
            if err:
                return None, err
            base, err = agg_one(y_t - 1, f'{lab_t} 的同比基期（{ms_prev[0]}…{ms_prev[-1]}）',
                                ms_prev)
            if err:
                return None, err
            pairs.append((lab_t, cur, base))
            ytd_info = (y_t, ms_cur, ms_prev, lab_t)

        xl, c_q, c_p, net, rows, blanks = [], [], [], [], [], []
        c_b, c_s, c_m = [], [], []
        for lab, (_y1, V1, Q1, P1, Va1, Qa1, BV1, BQ1, nm1), \
                (_y0, V0, Q0, P0, _Va0, _Qa0, BV0, BQ0, _nm0) in pairs:
            xl.append(lab)
            gV, gQ, gP = V1 / V0 - 1, Q1 / Q0 - 1, P1 / P0 - 1
            cross = gQ * gP
            lV, lQ, lP = math.log(V1 / V0), math.log(Q1 / Q0), math.log(P1 / P0)

            # ── 硬护栏①：算术分解逐列闭合（三项，含交叉项）──────────────
            # 残差只应该是 float64 舍入（~1e-16）。超了就是代码写错（取错列、
            # 年度分桶串了一格），而画出来的图**看不出任何异常**：柱照堆、菱形照画，
            # 读者拿到的是一个不成立的恒等式。所以宁可整页不出。
            r1 = gV - (gQ + gP + cross)
            if not abs(r1) <= DECOMP_EPS:
                raise SpecError(
                    f'decomp「{d["zh"]}」{lab} 算术分解不闭合：量 {gQ:+.12f} + 价 {gP:+.12f}'
                    f' + 交叉 {cross:+.12f} = {gQ + gP + cross:+.12f}，'
                    f'总增长 {gV:+.12f}，残差 {r1:+.3e} > {DECOMP_EPS:.0e}')
            # ── 硬护栏②：纯对数分解逐列闭合（这一种本来就该零残差，没有交叉项）──
            r2 = lV - (lQ + lP)
            if not abs(r2) <= DECOMP_EPS:
                raise SpecError(
                    f'decomp「{d["zh"]}」{lab} 对数分解不闭合：量 {lQ:+.12f} + 价 {lP:+.12f}'
                    f' = {lQ + lP:+.12f}，总计 {lV:+.12f}，残差 {r2:+.3e} > {DECOMP_EPS:.0e}')

            if abs(lV) < DECOMP_LN_MIN:
                # 整根柱留空：w = g_V/ln(V₁/V₀) 此时是 0/0，算出来的两块没有有效位。
                blanks.append(lab)
                c_q.append(np.nan)
                c_p.append(np.nan)
                c_b.append(np.nan)
                c_s.append(np.nan)
                c_m.append(np.nan)
                net.append(np.nan)
                rows.append((lab, Va1, Qa1, P1, gV, gQ, gP, cross, np.nan, np.nan, nm1))
                continue
            w = gV / lV
            cq, cp = w * lQ * 100, w * lP * 100
            # ── 硬护栏③：**画在图上的那两块**逐列相加 == 总增长 ────────────
            r3 = gV * 100 - (cq + cp)
            if not abs(r3) <= DECOMP_EPS:
                raise SpecError(
                    f'decomp「{d["zh"]}」{lab} 图上两块不闭合：量 {cq:+.12f}pp + 价 '
                    f'{cp:+.12f}pp = {cq + cp:+.12f}pp，总增长 {gV * 100:+.12f}%，'
                    f'残差 {r3:+.3e} > {DECOMP_EPS:.0e}')
            c_q.append(cq)
            c_p.append(cp)
            net.append(gV * 100)
            if bench:
                # V ≡ V_行业 × s × r，其中 s ≡ Q/Q_行业（份额）、r ≡ P/P_行业（品种结构）。
                # 代入 V=Q·P 两边逐项对消即得，是**定义式**，与两分法同源、零假设。
                lBV = math.log(BV1 / BV0)
                ls = math.log((Q1 / BQ1) / (Q0 / BQ0))
                lr = math.log(((V1 / Q1) / (BV1 / BQ1)) / ((V0 / Q0) / (BV0 / BQ0)))
                # ── 硬护栏⑤：三分法的三块对数相加 == 总对数增长 ──────────────
                r5 = lV - (lBV + ls + lr)
                if not abs(r5) <= DECOMP_EPS:
                    raise SpecError(
                        f'decomp「{d["zh"]}」{lab} 三分法不闭合：行业 {lBV:+.12f} + 份额 '
                        f'{ls:+.12f} + 结构 {lr:+.12f} = {lBV + ls + lr:+.12f}，'
                        f'总计 {lV:+.12f}，残差 {r5:+.3e} > {DECOMP_EPS:.0e}')
                cb, cs_, cm = w * lBV * 100, w * ls * 100, w * lr * 100
                r6 = gV * 100 - (cb + cs_ + cm)
                if not abs(r6) <= DECOMP_EPS:
                    raise SpecError(
                        f'decomp「{d["zh"]}」{lab} 三块重标定后不闭合：'
                        f'{cb:+.12f} + {cs_:+.12f} + {cm:+.12f} = {cb + cs_ + cm:+.12f}pp，'
                        f'总增长 {gV * 100:+.12f}%，残差 {r6:+.3e} > {DECOMP_EPS:.0e}')
                c_b.append(cb)
                c_s.append(cs_)
                c_m.append(cm)
            rows.append((lab, Va1, Qa1, P1, gV, gQ, gP, cross, cq, cp, nm1))

        if not any(np.isfinite(x) for x in net):
            return None, (f'{d["zh"]}：{len(xl)} 个年度全部落在 |ln(V₁/V₀)| < '
                          f'{DECOMP_LN_MIN:.0e} 的留空区间，没有一根柱画得出来')

        kind_zh, kind_warn = DECOMP_KINDS[d['kind']]
        share_zh = d['share_zh'] or (f'{d["qty"]["zh"]}份额' if bench else '')
        mix_zh = d['mix_zh'] or (f'{d["price_zh"]}相对行业（品种结构）' if bench else '')
        ex = {
            'n': n, 'kind': 'bridge_bar', 'fmt': 'pct1', 'yfmt': 'pct0',
            'xlabels': xl, 'xrot': 0,          # 年度类别轴：标签不斜排
            'title': (f'{d["zh"]}：增长的量价分解'
                      + ('（一格 = 一个完整年度，末格 = 当年 YTD）' if ytd_info
                         else '（一格 = 一个完整年度）')),
            'ylab': '% y/y', 'net_color': 'INK',
            'stacks': ([
                {'name': f'{d["bench_value"]["zh"]}的贡献', 'color': 'NAVY', 'values': LN(c_b)},
                {'name': f'{share_zh}的贡献', 'color': 'MBLUE', 'values': LN(c_s)},
                {'name': f'{mix_zh}的贡献', 'color': 'GREEN', 'values': LN(c_m)},
            ] if bench else [
                {'name': f'{d["qty"]["zh"]}的贡献', 'color': 'NAVY', 'values': LN(c_q)},
                {'name': f'{d["price_zh"]}的贡献', 'color': 'MBLUE', 'values': LN(c_p)},
            ]),
            'net': {'name': f'{d["value"]["zh"]}增长', 'values': LN(net)},
            'src_extra': 'Log-weight decomposition of an accounting identity; no model',
        }
        # ── 硬护栏④：**写进 payload 的那组数**也要闭合 ────────────────────
        # 上面查的是浮点原值，这里查的是 LN() 四舍五入到 6 位之后真正发出去的数。
        # 差别只可能来自舍入（≤ 3 × 5e-7）；大于这个就是序列化环节动了数。
        for i, x in enumerate(ex['net']['values']):
            parts = [st['values'][i] for st in ex['stacks']]
            if x is None:
                if any(p is not None for p in parts):
                    raise SpecError(f'decomp「{d["zh"]}」{xl[i]} 净额留空但堆叠段有值 —— '
                                    f'菱形不见了、柱子还在，读者会当成「净额为 0」')
                continue
            got = sum(parts)
            if not abs(got - x) <= 2e-6:
                raise SpecError(f'decomp「{d["zh"]}」{xl[i]} 写进 payload 的两块相加 '
                                f'{got:.9f} ≠ 净额 {x:.9f}（差 {got - x:.3e}）')

        # ── 图注：每一个数都在这里现算，spec 里一个数都没有 ──
        fin = [r for r in rows if np.isfinite(r[8])]
        per = ('日历年' if start == 1 else
               f'财年（{start} 月—次年 {start - 1 if start > 1 else 12} 月；'
               f'{ylab(agg[-1][0])} = {agg[-1][0]} 年 {start} 月起的 12 个月，'
               f'本页财年按{"结束" if d["year_label"] == "end" else "起始"}年命名）')
        last = rows[-1]
        idx_all = list(self.df.index)
        # ── 横轴怎么读 + 末端到哪。YTD 桶在场时这两段必须换一套说法：
        # 「每个端点都是 12 个月的合计」对 YTD 那一格是假话，
        # 「尚未凑满一个完整年度、不在本图上」对已进 YTD 窗口的月份也是假话。
        n_full = len(xl) - (1 if ytd_info else 0)
        if ytd_info:
            y_t, ms_cur, ms_prev, lab_t = ytd_info
            axis_txt = (
                f'横轴共 {len(xl)} 格：'
                + (f'前 {n_full} 格各 = 一个完整{per}（{xl[0]} … {xl[n_full - 1]}，'
                   f'首格 {xl[0]} 的同比基期是 {ylab(agg[0][0])}），' if n_full else '')
                + f'最后一格 {lab_t} 是<b>年初至今（YTD）</b>。'
                  '完整年各格的端点都是<b>整整 12 个月的合计</b>，不是某一个月的点值 —— '
                  '拿单月当端点，挑到一个异常月就能把归因整个说反。'
                + f'<b>{lab_t} 覆盖 {ms_cur[0]} … {ms_cur[-1]} 共 {len(ms_cur)} 个月</b>，'
                  f'同比基期取<b>去年同一批月份</b>（{ms_prev[0]} … {ms_prev[-1]}），'
                  f'两侧月份集合逐月相同 —— 不对齐就是拿 {len(ms_cur)} 个月比 12 个月，'
                  f'柱高毫无意义。'
                  f'<b>⚠️ YTD 柱与完整年柱不可直接比大小</b>（覆盖月数不同：'
                  f'{len(ms_cur)} vs 12），它回答的是「今年到目前为止 vs 去年同期」，'
                  f'不是「今年全年」。')
            last_plot = ms_cur[-1]
            tail = [p for p in idx_all if p > last_plot]
            tail_n, tail_from = len(tail), (tail[0] if tail else None)
            tail_txt = (
                (f'{lab_t} 实际截至 {last_plot}；其后的 {tail_n} 个月'
                 f'（{tail_from} … {idx_all[-1]}）当月或其去年同月在本图所用的列上'
                 f'仍有缺值，两侧对不齐，不进 YTD 窗口、<b>不在本图上</b> —— '
                 f'本页其余各图画到各自最新月，两者末端不同不是错。') if tail_n else
                f'{lab_t} 截至 {last_plot}，与本表最新月同期。')
        else:
            axis_txt = (
                f'横轴一格 = 一个完整{per}，共 {len(xl)} 格（{xl[0]} … {xl[-1]}，'
                f'基期 {ylab(agg[0][0])}）。每个端点都是<b>整整 12 个月的合计</b>，'
                f'不是某一个月的点值 —— 拿单月当端点，挑到一个异常月就能把归因整个说反。')
            last_plot = sel[-1][1][-1]
            tail = [p for p in idx_all if p > last_plot]
            tail_n, tail_from = len(tail), (tail[0] if tail else None)
            tail_txt = (
                (f'最新一格 {xl[-1]} 到 {last_plot} 收官；'
                 f'其后的 {tail_n} 个月（{tail_from} … {idx_all[-1]}）'
                 f'尚未凑满一个完整年度，<b>不在本图上</b> —— 本页其余各图画到最新月，'
                 f'两者末端不同不是错。') if tail_n else
                f'最新一格 {xl[-1]} 到 {last_plot} 收官，与本页数据月同期。')
        # 「均值」叫日均还是月均，由**列的粒度**决定，不由有没有 weight_col 决定：
        #   有 weight_col → Σ金额 ÷ Σ交易日 = 日均
        #   无 weight_col + 月合计列 → Σ月合计 ÷ 月数 = 月均
        #   无 weight_col + 日均列 → Σ日均 ÷ 月数 = 日均（各月日均的等权平均）
        # 第三种早先被印成「月均」——把一个日均数说成月均，量级差二十几倍。
        # 除数用**被报告那一格自己的月数**（完整年 = 12，YTD = 实际入选月数），
        # 写死 12 会把 YTD 格的均值算小一截。
        # ── 措辞随「图上有没有 YTD 格」二选一，两套都由同一批判据推导 ──
        # 有 YTD 格时「年度合计 / 年内均值」是假话（末格不是一年），要说「该格」；
        # 没有 YTD 格时保持原措辞逐字不动 —— 未切日历年、没有 YTD 的财年页
        # （如 ASX）不因本轮加 YTD 能力而产生任何字节变化。
        nm_last = last[10]
        cell_zh = '该格' if ytd_info else '年度'
        if d['weight_col']:
            avg_zh = '窗口内日均' if ytd_info else '年内日均'
            avg_how = (f'该格合计 ÷ 同窗口 <code>{d["weight_col"]}</code> 合计' if ytd_info
                       else f'年度合计 ÷ 该年 <code>{d["weight_col"]}</code> 合计')
        elif gran == 'daily_avg':
            avg_zh = '窗口内日均' if ytd_info else '年内日均'
            avg_how = (f'{nm_last} 个月日均的等权平均，即该格合计 ÷ {nm_last}' if ytd_info
                       else '12 个月日均的等权平均，即年度合计 ÷ 12')
        else:
            avg_zh = '窗口内月均' if ytd_info else '年内月均'
            avg_how = f'该格合计 ÷ {nm_last}' if ytd_info else '年度合计 ÷ 12'
        # 「还原」这一步只有日均列才需要做。列本身就是当月合计时说「先还原」是假话。
        restored = bool(d['weight_col'] or d['value_total_col'] or d['qty_total_col']
                        or gran == 'daily_avg')
        agg_how = ('先还原成当月合计再逐年相加' if restored else '逐年把当月合计相加')
        # 交叉项到底有多大：绝对值最大的一格，以及它相对该年净增长的倍数
        i_x = max(range(len(rows)), key=lambda i: abs(rows[i][7]))
        big = rows[i_x]
        ratio = (abs(big[7]) / abs(big[4])) if big[4] else float('inf')
        # 两法差异：同一年「量的贡献」在算术口径与对数权重口径下差几个百分点
        gapq = max(abs(r[5] * 100 - r[8]) for r in fin) if fin else float('nan')
        gapp = max(abs(r[6] * 100 - r[9]) for r in fin) if fin else float('nan')
        ex['note'] = (
            f'<b>恒等式：{d["value"]["zh"]} ≡ {d["qty"]["zh"]} × {d["price_zh"]}</b>，'
            f'其中 {d["price_zh"]} ≡ {d["value"]["zh"]} ÷ {d["qty"]["zh"]}。'
            f'这是<b>定义式</b>，不含任何模型假设，两边{"逐格" if ytd_info else "逐年"}恒等。'
            + axis_txt
            # 「最新一格覆盖到哪个月、后面还剩几个月没进图」必须说出来：
            # 本页别处的图画到最新月，这张的末端由完整年度 / 两侧对齐的 YTD 窗口决定。
            # 不说的话，读者会以为这张图也含最新月，把「还没发生 / 没进窗口」当成「没有增长」。
            + tail_txt

            + f'<b>{"各格的合计" if ytd_info else "年度合计"}怎么加。</b>'
            f'金额：{v_how}；数量：{q_how}。'
            f'{agg_how}，{cell_zh}{d["price_zh"]} = Σ金额 ÷ Σ数量。'
            + ('直接把「日均」跨月相加会给交易日多的月份配错权重。'
               if gran == 'daily_avg' else
               '两列都是当月合计，跨月相加不涉及交易日权重。')

            + f'<b>图上画的是对数分解（按总增长重标定）。</b>'
            f'ln(V₁/V₀) = ln(Q₁/Q₀) + ln(P₁/P₀) 天然可加、<b>没有交叉项</b>；'
            f'再乘上 w = g<sub>额</sub> ÷ ln(V₁/V₀) 把两块换算成百分点，'
            f'于是<b>深蓝 + 中蓝逐格等于</b>菱形标的总增长（残差 ≤ {DECOMP_EPS:.0e}，'
            f'超了本页直接不出 —— 护栏在 <code>build/single.py</code> 的 '
            f'<code>ex_decomp</code>）。w 对量与价一视同仁，不含任何分配假设。'

            f'<b>为什么不画算术分解。</b>算术分解 g<sub>额</sub> = g<sub>量</sub> + '
            f'g<sub>价</sub> + g<sub>量</sub>·g<sub>价</sub> 多一个交叉项，'
            f'而它不是可忽略的余项：本窗口里最大的一格是 {big[0]} 的 '
            f'{ppbp(big[7] * 100)}，'
            + (f'相当于该年净增长（{nz_txt(f"{big[4] * 100:+.1f}")}%）的 {ratio:.1f} 倍。'
               if np.isfinite(ratio) else '而该年净增长为零。')
            + f'量与价一涨一跌时它与净增长同量级，堆叠柱堆不出可读的归因。'
              f'算术口径同期的读数：{last[0]} 量 {nz_txt(f"{last[5] * 100:+.1f}")}%、'
              f'价 {nz_txt(f"{last[6] * 100:+.1f}")}%、交叉项 '
              f'{ppbp(last[7] * 100)}。'
              f'两种口径对「量」的贡献读数最大差 {ppbp_abs(gapq)}、'
              f'对「价」最大差 {ppbp_abs(gapp)}。'

            + ((f'<b>本图是三分法。</b>在两分法（量 × 价）之外再拆一层：'
                f'{d["value"]["zh"]} ≡ {d["bench_value"]["zh"]} × {share_zh} × {mix_zh}'
                f'（份额 ≡ {d["qty"]["zh"]} ÷ {d["bench_qty"]["zh"]}；'
                f'结构 ≡ 自家{d["price_zh"]} ÷ 行业{d["price_zh"]}）。'
                f'代入前一条恒等式两边逐项对消即得，同样是定义式。'
                f'三块对数相加 = 总对数增长，重标定后逐格 = 总增长，'
                f'残差 ≤ {DECOMP_EPS:.0e}（护栏⑤⑥）。'
                f'同期两分法的读数：{last[0]} 量 {ppbp(last[8])}、价 {ppbp(last[9])} —— '
                f'两分法看不出这里面哪些是行业整体在动、哪些是自家在抢或丢份额。'
                f'<b>⚠️ 份额与结构两块的分界依赖 bench 与本家同口径：分子必须是分母的子集。'
                f'换一家用之前先核这一条</b> —— 不是子集的话，「份额」会算出大于 1 的数，'
                f'而图上只会显示成一根更高的柱。') if bench else '')
            + (f'<b>留空的柱。</b>{"、".join(blanks)} 的 |ln(V₁/V₀)| < '
               f'{DECOMP_LN_MIN:.0e}（两年几乎持平），重标定权重 w 是 0/0、'
               f'算出来没有有效位，所以整根留空而不是印一个假的分解。' if blanks else '')

            + f'<b>⚠️「{d["price_zh"]}」是什么、不是什么。</b>它是 {d["value"]["zh"]} ÷ '
              f'{d["qty"]["zh"]} 得到的{kind_zh}。{kind_warn}'

              f'<b>汇率进不来。</b>本图每一格都是同一列自身的年度增长率，'
              f'本币（{self.spec["ccy"]}）在分子分母上同时出现、逐项抵消；'
              f'换成任何一种货币、任何一种换汇口径（月均 / 月末 / 锁基期），'
              f'两块的高度与菱形的位置一个都不会变。'

              f'{last[0]} 的{avg_zh}：{d["value"]["zh"]} {unit_txt(last[1], d["value"])}、'
              f'{d["qty"]["zh"]} {unit_txt(last[2], d["qty"])}；'
              f'{cell_zh}{d["price_zh"]}（Σ金额 ÷ Σ数量）'
              f'{fmt_val(last[3], d["price_fmt"])} {d["price_unit"]}。'
              f'前两个数是<b>{cell_zh}合计除回展示口径</b>的结果（{avg_how}）—— '
              f'{cell_zh}合计本身的单位是「{d["value"]["unit"]} × 期数」，'
              f'拿展示单位去标它就是印错单位。'
            + (' ' + md_bold(d['note']) if d['note'] else ''))

        # ── 自检行：柱的构成（几根完整年 + YTD 覆盖哪些月）由 build() 打印 ──
        # 一个数都不写死：spec 改口径 / 数据多一个月，这行自己变。
        self.decomp_report.append(
            f'decomp「{d["zh"]}」：共 {len(xl)} 根柱 = '
            + (f'{n_full} 根完整年柱（{xl[0]} … {xl[n_full - 1]}，'
               f'基期 {ylab(agg[0][0])}）' if n_full else '0 根完整年柱')
            + (f' + 1 根 YTD 柱（{ytd_info[3]}：{ytd_info[1][0]}…{ytd_info[1][-1]} '
               f'共 {len(ytd_info[1])} 个月，同比基期 {ytd_info[2][0]}…{ytd_info[2][-1]}）'
               if ytd_info else '，无 YTD 桶（最新年已收官，或次年凑不出两侧对齐的月份）'))
        return ex, None

    def ttm_rhs(self, tot, win):
        """当月合计序列 → (次轴金线, 窗口内的滚动同比数组, 单月同比序列, 滚动同比序列)。

        `tot` 由 `monthly_total()` 给出（口径怎么还原的由它交代）。整条同比都算不出来时
        `rhs` 返回 None —— 引擎只看 `ex.yoy` 在不在就判双轴，值全是 null 时右轴量程会
        退化成 [0, 1]，印出一列假刻度而金线一个点都没画（CONTRACT §6.3 最后一条）。
        """
        roll = tot.rolling(TTM_WIN, min_periods=TTM_WIN).sum()
        ttm_yoy = (roll / roll.shift(12) - 1) * 100
        mo_yoy = (tot / tot.shift(12) - 1) * 100
        rv = ttm_yoy.reindex(win).values.astype(float)
        rhs = None
        if np.isfinite(rv).any():
            rhs = {'name': f'{TTM_WIN} 个月滚动合计的同比（RHS）', 'color': 'GOLD',
                   'yfmt': 'pct0', 'values': LN(rv)}
        return rhs, rv, mo_yoy, ttm_yoy

    def bar_line_caliber_zh(self, c, total_col, weight_col, gran):
        """「柱与线是不是同一个口径」那一段 —— **由字段推导，不许无条件写死**。

        这曾经是底座里第二句假话（见 `_CALIBER_CONFLICTS` 上方那段）。
        柱画的是 `c` 这一列本身；线的滚动合计取自 `monthly_total()` 的结果。
        两者是否**真的**不同口径，只由两件事决定：
          (i)  这一列是不是日均（`gran`）——「已除过交易日数」这半句的真伪；
          (ii) 滚动合计是不是换了一列 / 乘了权重（`total_col` ≠ 本列，或有 `weight_col`）。
        SGX 的配置里两件事都不成立（月合计列、无 total_col、无 weight_col），
        柱与线是同一列同一口径，印那句话既是假话、又与同段前半句「未做还原」自相矛盾。
        """
        same_col = (not total_col) or total_col == c['col']
        line_recast = (not same_col) or bool(weight_col)
        if gran == 'daily_avg' and line_recast:
            return ('<b>柱与线的口径不同是有意的</b>：柱是<b>日均</b>（已除过交易日数，'
                    '看的是「开市那天有多热」），线是<b>当月合计</b>的滚动同比'
                    '（看的是「一整年的总量在不在长」）。两者不该相互印证到小数点后一位。')
        if gran == 'daily_avg':
            return ('<b>柱与线取自同一列</b>（' + f'<code>{c["col"]}</code>' + '，当月<b>日均</b>）：'
                    '柱是水平值，线是它 12 个月滚动合计的同比。'
                    '⚠️ 本页没有交易日权重列，这个滚动合计是把 12 个<b>日均</b>等权相加 —— '
                    '不是当月合计的和，各月交易日数不同带来的差异消不掉。')
        if line_recast:
            return (f'<b>柱与线取自不同的列</b>：柱是 <code>{c["col"]}</code> 的水平值，'
                    f'线的滚动合计取自 <code>{total_col}</code>。两列都是当月合计口径。')
        return ('<b>柱与线取自同一列同一口径</b>（' + f'<code>{c["col"]}</code>' +
                '，当月<b>合计</b>，未做任何还原）：柱是水平值，线是它 12 个月滚动合计的同比。'
                '两者的差别只在「水平 vs 增速」，不在口径。')

    def ttm_spike_zh(self, mo_yoy, ttm_yoy):
        """两种同比的毛刺量级 —— 拿**这条序列自己**实测，一个数都不引别家的例子。

        从 `ex_ttm` 里原样搬出来的，因为「总量柱 + 滚动同比」现在有两个产地
        （`ex_ttm` 与 `ex_mix_total`）。搬而不抄：同一段实测文案在两处各写一份，
        改一处漏一处的时候，页面上会出现两段读数互相矛盾的图注而没有任何护栏会响。
        """
        # ── 毛刺量级：拿这条序列自己实测，两种同比只在**都有值**的月份上比 ──
        a_all, b_all = mo_yoy.values.astype(float), ttm_yoy.values.astype(float)
        m = np.isfinite(a_all) & np.isfinite(b_all)
        spike = ''
        if int(m.sum()) >= 24:
            a = np.where(m, a_all, np.nan)
            b = np.where(m, b_all, np.nan)
            # np.diff 在缺月两侧自动出 nan，nanmax 因此只量「相邻两个月都有值」的跳变
            ja, jb = np.nanmax(np.abs(np.diff(a))), np.nanmax(np.abs(np.diff(b)))
            i_ja = int(np.nanargmax(np.abs(np.diff(a))))
            idx = list(self.df.index)
            opp = int(np.nansum((a * b) < 0))
            k_gap = int(np.nanargmax(np.abs(a - b)))
            sd_a, sd_b = float(np.nanstd(a, ddof=1)), float(np.nanstd(b, ddof=1))
            # 「滚动更平」不许写死 —— 它对某些序列是**假的**：序列本身在爬坡时，
            # 标准差量到的是趋势幅度而不是噪声，滚动同比反而更大（实测存在这种页）。
            # 所以两个判据都报，并由数据决定这段话怎么说；相邻月跳变才是「毛刺」的判据，
            # 标准差回答的是「整段波动多大」，两者问的不是同一件事。
            if sd_b < sd_a and jb < ja:
                verdict = ('两个判据一致：滚动同比的逐月标准差与相邻月跳变都更小。')
            elif jb < ja:
                verdict = (f'⚠️ 注意：本序列<b>滚动同比的标准差反而更大</b>'
                           f'（{ppbp_abs(sd_b)} vs {ppbp_abs(sd_a)}）。'
                           f'那不是滚动更毛刺，而是标准差量的是<b>整段波动幅度</b> —— '
                           f'序列本身在单向爬坡时它会被趋势撑大。'
                           f'判「毛刺」要看<b>相邻月跳变</b>，这个判据上滚动仍然小得多。')
            else:
                verdict = (f'⚠️ 本序列<b>两个判据都没显示滚动更平</b>'
                           f'（标准差 {ppbp_abs(sd_b)} vs {ppbp_abs(sd_a)}、'
                           f'相邻月跳变 {ppbp_abs(jb)} vs {ppbp_abs(ja)}）。'
                           f'本图仍用滚动同比，理由不是「更平」而是<b>口径</b>：'
                           f'任意连续 {TTM_WIN} 个月覆盖同一套日历与同一套到期周期，'
                           f'单月同比里那截「今年这个月比去年多开几天市」的差被整个消掉。')
            spike = (
                f'<b>毛刺有多大，用本序列自己实测</b>（{int(m.sum())} 个两种同比都有值的月份）：'
                f'单月同比的逐月标准差 {ppbp_abs(sd_a)}，'
                f'{TTM_WIN} 个月滚动同比 {ppbp_abs(sd_b)}；'
                f'相邻月最大跳变 {ppbp_abs(float(ja))}（{idx[i_ja]} → {idx[i_ja + 1]}）'
                f' vs {ppbp_abs(float(jb))}。{verdict}'
                f'两者<b>符号相反</b>的月份有 {opp} 个'
                f'（占 {opp / int(m.sum()) * 100:.0f}%）；差得最远的是 {idx[k_gap]}，'
                f'单月 {nz_txt(f"{a[k_gap]:+.1f}")}% 而滚动 {nz_txt(f"{b[k_gap]:+.1f}")}%。'
                f'用单月同比，光是挑月份就能把结论说成两个方向。')

        return spike

    def ex_ttm(self, n, t):
        """一条量的**水平值**（柱）+ **12 个月滚动合计的同比**（次轴金线）。

        为什么次轴不画单月同比：单月同比同时被三件事推着走 —— 立会日数（18 vs 23 天，
        差 28%）、假期与到期日的月度形状、以及去年同月那一个数本身的高低。三者叠加，
        单月同比的毛刺可以大到与趋势符号相反。滚动 12 个月合计把这三件事全部抹平
        （任意连续 12 个月都覆盖同样的日历与同样的到期周期），代价是转折点晚半年才显形。
        毛刺到底有多大不靠引用别家的例子 —— 下面的图注用**这条序列自己**实测。
        """
        c = t['level']
        tot, how = self.monthly_total(c, t['total_col'], t['weight_col'],
                                      t['granularity'], f'ttm_yoy「{t["zh"]}」')
        end = self.last_month(c)
        if end is None:
            return None, f'{t["zh"]}：{c["col"]} 整列为空'
        win = self.win_long(end)
        xl = [mlab(p) for p in win]
        v = self.vals(c, win)
        if self.flat0_skip(t['zh'], [c], win, [v]):
            return None, f'{t["zh"]}：窗口内恒为 0'

        rhs, rv, mo_yoy, ttm_yoy = self.ttm_rhs(tot, win)
        ex = bar_ex(n, f'{t["zh"]}：水平值与 {TTM_WIN} 个月滚动同比', c, xl, v, rhs,
                    ylab2=f'% y/y（{TTM_WIN}M 滚动）')
        if rhs:      # 次轴金线是滚动口径；短历史画不出金线时就没有滚动同比可点名
            self.log_yoy(n, 'ttm')
        hit = self.mark_breaks(ex, win, [c])

        spike = self.ttm_spike_zh(mo_yoy, ttm_yoy)

        bar_line_caliber = self.bar_line_caliber_zh(
            c, t['total_col'], t['weight_col'], t['granularity'])
        ex['note'] = (
            f'深蓝柱 = {c["zh"]}的<b>水平值</b>（{c["unit"]}，原始单位，未做任何指数化）。'
            f'近 {len(win)} 个月。'
            + (f'金色折线（右轴）= <b>{TTM_WIN} 个月滚动合计的同比</b>：'
               f'先把最近 {TTM_WIN} 个月的量加成一个滚动合计，再与前 {TTM_WIN} 个月的'
               f'同一口径比。滚动合计取自：{how}。'
               if rhs else NO_YOY_NOTE)
            + f'{xl[-1]} 水平值 {unit_txt(v[-1], c)}，'
            + (f'滚动同比 {nz_txt(f"{rv[-1]:+.1f}")}%（单月同比 '
               f'{nz_txt(f"{float(mo_yoy.reindex(win).values[-1]):+.1f}")}%，两者并列'
               f'只为让读者看到差距，图上画的是前者）。'
               if rhs and np.isfinite(rv[-1]) else '')
            + spike
            + bar_line_caliber
            + self.slow_tail([c])
            + (self.brk_zh(hit, win) + '。' if hit else '')
            + (' ' + md_bold(t['note']) if t['note'] else ''))
        return ex, None

    # ────────────────────── Exhibit 1：汇总表 ──────────────────────
    def summary(self, latest):
        cur, prv, yag = latest, latest - 1, latest - 12
        idx = list(self.df.index)
        i_cur = idx.index(cur)
        rows, blanks, dashes = [], [], []

        def one(c):
            s = self.ser(c)
            g = lambda p: (float(s.get(p, np.nan)) if p in s.index else np.nan)
            a, b1, b12 = g(cur), g(prv), g(yag)
            ratio = self.is_ratio(c)

            def chg(x, y):
                if not (np.isfinite(x) and np.isfinite(y)):
                    return None
                if ratio:
                    return float(x - y)          # 比率之差走 pp/bp，不走百分比的百分比
                if y == 0 or x * y < 0:
                    return None
                return (x / y - 1) * 100

            def cell(v):
                if v is None:
                    return {'v': ''}
                if ratio:
                    txt = f'{v * 100:+.0f}bp' if abs(v) < 1 else f'{v:+.2f}pp'
                else:
                    txt = f'{nz(v, 1):+.1f}%'
                txt = nz_txt(txt)
                if txt.lstrip('+-') in ('0', '0.0', '0bp', '0.0pp', '0.0%', '0%'):
                    return {'v': txt.lstrip('+-')}
                return {'v': txt, 'cls': 'pos' if v > 0 else ('neg' if v < 0 else '')}

            cells = [{'v': fmt_val(a, c['fmt']) or '—', 'cls': 'cur'},
                     {'v': fmt_val(b1, c['fmt']) or '—'},
                     {'v': fmt_val(b12, c['fmt']) or '—'},
                     cell(chg(a, b1)), cell(chg(a, b12))]
            # 分位一律走 build/pctile.py：判据是**口径**，口径只能有一处定义（各页各写各的，
            # 正是同一条序列在两页被判定相反的原因，见 build/pctile.py 的模块 docstring）。
            ser = [None if not np.isfinite(x) else float(x) for x in s.values]
            if not np.isfinite(a):
                qv, qcls = '', ''
                dashes.append(c['zh'])
            else:
                qv, qcls = pctile.cell(ser, i_cur)
            cells.append({'v': qv, 'cls': qcls} if qv else {'v': ''})
            if not qv and np.isfinite(a):
                blanks.append((c['zh'], pctile.why_blank(ser) or '样本不足'))
            rows.append({'label': f'{c["zh"]}（{c["unit"]}）', 'cells': cells})

        rows.append({'kind': 'group', 'label': '头条指标（决定本页数据月）'})
        for c in self.head:
            one(c)
        for g in self.groups:
            rows.append({'kind': 'group', 'label': g['zh']})
            for c in g['cols']:
                one(c)

        note = (
            f'「3Y %ile」= 当月读数在最近 {pctile.WINDOW} 个月里高于多少比例的观测'
            f'（≥66 绿、≤33 红），由全站唯一的 <code>build/pctile.py</code> 计算：'
            f'把这一行的分位在近 24 个月里逐月回放，若 ≥70% 的月份都钉在 100 或 0，'
            f'说明这一列对该指标没有区分度，留空。'
            f'比率类指标（fmt 为 pct*/pp*）的变化一律用 pp／bp（差额绝对值小于 1pp 时写 bp），'
            f'不用「百分比的百分比变化」；其余用百分比变化，分母为 0 或两期异号时留空。')
        if dashes:
            note += (f'<b>{"、".join(sorted(set(dashes)))}</b> 的本月一列是「—」：'
                     f'该列本月尚未披露（慢腿见下方说明），不是 0。')
        if blanks:
            note += '本月分位留空的行：' + '；'.join(f'{a}（{b}）' for a, b in blanks) + '。'
        return {
            'title': f'{self.spec["name"]} 月度经营指标汇总 — {mlab(cur)}',
            'heads': [f'本月 {mlab(cur)}', f'上月 {mlab(prv)}', f'去年同月 {mlab(yag)}',
                      'm/m', 'y/y', f'{pctile.WINDOW // 12}Y %ile'],
            'sep': 3,
            'rows': rows,
            'note': note,
        }

    # ────────────────────── 末尾核对表 ──────────────────────
    def table(self, n):
        """近 13 个月核对表（CONTRACT §5.4）。

        单位就是 spec 里写的单位；唯一的换算是列自己声明的 `scale`（恒等换算），
        用到的列在表注里逐条点名 —— 「官方原始单位」的意义是能与公司披露逐格对账，
        所以任何一次换算都必须说出来。
        """
        cols = self.head + [c for g in self.groups for c in g['cols']]
        win = self.win(self.df.index[-1], WIN_SHORT)
        keys, seen = [], set()
        for i, c in enumerate(cols):
            k = f'c{i}'
            if c['col'] in seen:            # 同一列在 headline 与 group 里都出现过
                continue
            seen.add(c['col'])
            keys.append((k, c))
        rows = []
        for p in win:
            r = {'xl': mlab(p)}
            for k, c in keys:
                v = float(self.ser(c).get(p, np.nan))
                r[k] = fmt_val(v, c['fmt']) or None
            rows.append(r)
        scaled = [f'{c["zh"]}（× {c["scale"]:g}）' for _, c in keys if c['scale'] != 1.0]
        # 倍数本身也要带出去：notes() 要按「是不是全都 ×100」分档措辞，
        # 不能靠回头解析上面那串中文（那是 stringly-typed，改个字就悄悄失效）。
        scales = [float(c['scale']) for _, c in keys if c['scale'] != 1.0]
        return {
            'n': n,
            'title': f'近 {len(win)} 个月月度指标核对表（本页单位，可与官方披露逐格对账）',
            'idx': '月份',
            'cols': [[f'{c["zh"]}（{c["unit"]}）', k] for k, c in keys],
            'rows': rows,
        }, scaled, scales

    # ────────────────────── 慢腿提示 ──────────────────────
    def slow_tail(self, cols):
        s = [c['zh'] for c in cols if c['col'] in self.slow]
        if not s:
            return ''
        return (f'（{"、".join(s)} 是慢腿：发布比头条晚，最新月留空是正常的，'
                f'不参与本页数据月的判定。）')

    # ────────────────────── 组装 ──────────────────────
    def payload(self):
        got, why = self.resolve_through()
        if got is None:
            return None, why
        latest, common = got
        idx = list(self.df.index)
        newest = idx[-1]
        ex, n = [], 2
        self.yoy_log = []       # 口径账本每次组装从零记，防重复调用时把图号记两遍
        self.saw_group_lines = self.saw_group_heat = False
        self.decomp_report = []  # decomp 自检行同理，从零记

        if self.headline_style == 'bar_yoy':
            # ①② 并成一张：全历史的水平值柱 + 次轴单月同比（见 HEADLINE_STYLES）。
            for c in self.head:
                ex.append(self.ex_head_bar(n, c)); n += 1
        else:
            for c in self.head:                               # ① 长历史 + 3Y 分位带
                ex.append(self.ex_history(n, c)); n += 1
            for c in self.head:                               # ② 同比
                ex.append(self.ex_yoy(n, c)); n += 1

        # 「派生图没出成」的账本：③ 的 mix 也会往里记，所以要在 ③ 之前开。
        self.skipped = list(self.mix_skipped)

        for g in self.groups:                                 # ③ 每组多列对比
            # 声明了 mix 且合计是**流量**列 → 先出「合计柱 + 占比堆叠」两张。
            # 合计是存量列的留到 ⑤ 与本页其余存量图排在一起（存量与流量不共轴，
            # 也不该在阅读顺序上互相插队）。
            eaten = set()
            if g['mix'] and not g['mix']['total']['stock']:
                pair, eaten = self.mix_pair(n, g)
                for e in pair:
                    ex.append(e); n += 1
            # 被 mix 吃掉的列不再进常规对比图：它们的水平值由合计柱交代、
            # 结构由占比堆叠交代，再画一遍是同一批数在同一页上出现两次。
            flow = [c for c in g['cols'] if not c['stock'] and c['col'] not in eaten]
            # 单位不同的列不能共用一根轴（cboe 原 deck 的 Exhibit 9 把 2 : 15 : 64 三个
            # 量级画在同一根轴上，最小的那条振幅只占画布 0.9% —— 那条线是白画的）。
            # 所以按单位分桶，一桶一张图；分桶保持 spec 里的先后顺序。
            buckets = []
            for c in flow:
                for b in buckets:
                    if b[0] == c['unit']:
                        b[1].append(c)
                        break
                else:
                    buckets.append((c['unit'], [c]))
            for _, cs in buckets:
                for e in self.ex_group(n, g['zh'], cs):
                    if e is None:
                        continue
                    ex.append(e)
                    n += 1

        for c in self.head:                                   # ④ 季节性
            e = self.ex_season(n, c)
            if e is not None:
                ex.append(e); n += 1

        for g in self.groups:                                 # ⑤ 存量列单独成图
            eaten = set()
            if g['mix'] and g['mix']['total']['stock']:
                pair, eaten = self.mix_pair(n, g)
                for e in pair:
                    ex.append(e); n += 1
            for c in g['cols']:
                if not c['stock'] or c['col'] in eaten:
                    continue
                e = self.ex_stock(n, g['zh'], c)              # 窗口内恒为 0 → None
                if e is not None:
                    ex.append(e); n += 1

        # ⑥ 量价分解 与 ⑦ 滚动同比：**一律追加在最末**（核对表之前）。
        # 不能插在 ③ 里：图号一移，正文与图注里所有「见 Exhibit k」的交叉引用全错，
        # 而那种错不会报任何异常。新图型往后加，既有图号一个都不动。
        for d in self.decomp:
            e, why = self.ex_decomp(n, d)
            if e is None:
                self.skipped.append(why)
                continue
            ex.append(e); n += 1
        for t_ in self.ttm:
            e, why = self.ex_ttm(n, t_)
            if e is None:
                self.skipped.append(why)
                continue
            ex.append(e); n += 1

        # ⑥ 显示缩放：把 9 位数压成 3 位数。**必须排在 axisfmt 之前** —— 轴刻度的
        # 小数位是按最终数值算的。只动图（series / ylab / 数值格式器），
        # summary() 与 table() 走的是 self.ser()，一个字节都不碰，仍是官方原始量级。
        # 顺带把各 exhibit 上的临时键 `_cols` pop 掉。
        disp = chartscale.fix_all(ex)

        # ⑦ 轴刻度小数位统一收口：放在全部 exhibit 建完之后做一遍，
        # 而不是散在每个 ex_* 里 —— 判据只跟最终 payload 有关（量程 + ycap/yfloor），
        # 各处各写一遍必然漏掉后加的图型。
        axisfmt.fix_all(ex)
        self._layout_long(ex)
        # 缩放之后再量一遍标签宽：还压字就是本页遇到了 chartscale 兜不住的形状，
        # 让它在构建日志里响一声，不要等到有人去截图才发现（缺陷 F 的机器判据）。
        self.tight = chartscale.audit(ex)

        # ⑧ 图注口径自检：宁可整页不出，也不发一段自相矛盾的口径说明。
        conflicts = caliber_audit(ex)
        if conflicts:
            det = '；'.join(f'Exhibit {k}：{w}' for k, w in conflicts)
            raise SpecError(
                f'[{self.ticker}] 图注里出现互相排斥的口径断言 —— {det}。'
                f'这类措辞必须由 granularity / total_col / weight_col 推导，'
                f'不许无条件写进 f-string（见 _CALIBER_CONFLICTS 上方的注释）')

        summary = self.summary(latest)
        table, scaled, _scales = self.table(n)                # ⑧ 核对表

        # ── 抬头一行数据条：同比与环比都写 ──
        # 只写同比的话，同比在高位、环比在跌的月份会给出一个纯正面的印象，
        # 读者要翻到 Exhibit 1 才知道环比掉了多少。
        # 整行锁死在 data_through 这一个月：取各列自己的 [-1] 会串到发布更快的腿上，
        # 于是同一页对同一指标给出两个互斥读数（hkex 就栽过这一处）。
        parts = []
        for c in self.head:
            v = self.ser(c).reindex(self.win(latest, WIN_HEAD)).values.astype(float)
            parts.append(f'{c["zh"]} {unit_txt(v[-1], c)}'
                         f'（{chg_txt(c, v)} y/y、{chg_txt(c, v, lag=1)} m/m）')
        headline = ' · '.join(parts)
        c0 = self.head[0]
        v0 = self.ser(c0).reindex(self.win(latest, WIN_HEAD)).values.astype(float)
        hub = f'{c0["zh"]} {unit_txt(v0[-1], c0)}（{chg_txt(c0, v0)} y/y）'
        if len(hub) > 60:                                     # CONTRACT：hub_line ≤ 60 字
            hub = f'{c0["zh"]} {fmt_val(v0[-1], c0["fmt"])}（{chg_txt(c0, v0)} y/y）'
        if len(hub) > 60:
            hub = hub[:59] + '…'

        xl_short = [mlab(p) for p in self.win(latest, WIN_SHORT)]
        xl_long = [mlab(p) for p in idx]
        src_head = strip_source(self.spec['source']).split(';')[0].strip()

        payload = {
            'ticker': self.ticker,
            'tracker': f'{self.spec["name"]} Monthly Operating Tracker',
            'title': f'{self.spec["title"]} — {latest.year} 年 {latest.month} 月',
            'data_through': str(latest),
            'through_label': f'{latest.year} 年 {latest.month} 月',
            'subtitle': f'数据源 {src_head} · 覆盖 {mlab(idx[0])} – {mlab(newest)}'
                        f'（{len(idx)} 个月）· 本币 {self.spec["ccy"]} · '
                        f'版式沿用 Goldman Sachs GIR monthly-metrics note · 只出图，不带观点',
            'headline': headline,
            'hub_line': hub,
            'source': self.spec['source'],
            'xlabels': xl_short,
            'xlabels_long': xl_long,
            'summary': summary,
            'exhibits': ex,
            'table': table,
            'notes': self.notes(latest, common, ex, scaled, newest, disp, _scales),
            'footer': f'{self.spec["name"]} · {src_head} · charts only, no commentary · '
                      f'个人研究用，不构成投资建议',
        }
        # 抬头右侧「官方发布于 X」。台账按月钉死，所以只查 data_through 这一个月；
        # 查不到就**整个字段不写** —— 渲染端判的是字段在不在，给 None 会印出一句空断言。
        day = source_dates().lookup(self.series_dir, self.ticker, str(latest))
        if day:
            payload['source_date'] = day
        return payload, None

    # ────────────────────── 口径与方法说明 ──────────────────────
    def notes(self, latest, common, ex, scaled, newest, disp, _scales=()):
        idx = list(self.df.index)
        head_zh = '、'.join(c['zh'] for c in self.head)
        out = [
            f'<b>数据源与口径。</b>全部数值来自本仓 <code>series/{self.spec["csv"]}</code>，'
            f'{strip_source(self.spec["source"])}。'
            f'覆盖 {mlab(idx[0])} – {mlab(newest)}（{len(idx)} 个月）。'
            f'本页所有数值、格式化与口径判断都在 Python 侧完成，页面只画不算。'
            f'本币 {self.spec["ccy"]}；跨币种换算不在本页做（另由 build/notional.py 处理），'
            f'本页只按本币标注。',

            f'<b>本页的「数据月」怎么定。</b>头条序列（{head_zh}）决定共同最新月与发布门槛：'
            f'取各头条列末月里最早的那个，再往回找到最近一个<b>全部头条列都有值</b>的月份，'
            f'即 {latest}；共同连续历史 {common} 个月（门槛要求 ≥ {MIN_MONTHS} 个月）。'
            f'非头条列缺最新月时那一格是 null（图上断笔、表里「—」），不拖住整页。',
        ]
        if self.slow:
            zh = {c['col']: c['zh'] for g in self.groups for c in g['cols']}
            out.append(
                f'<b>⚠️ 慢腿（发布比头条晚）。</b>'
                + '、'.join(zh.get(c, c) for c in sorted(self.slow))
                + f' 一律<b>不参与门槛判定</b> —— 否则一条天生晚发的腿会把整页拖住。'
                  f'这些列最新月留空是正常状态，不是数据故障；它们各自的图画到自己序列的'
                  f'最新月为止，汇总表里本月一列显示「—」。')
        drawn = [e for e in ex if e.get('break_at')]
        if self.breaks:
            # 断点表按列登记时，同一个事件会在多列上重复出现（enx_breaks.csv 就是这样），
            # 但读者只需要知道「哪个月发生了什么」——按 (月份, 说明) 去重再列。
            uniq = list(dict.fromkeys((str(b['month']), b['zh']) for b in self.breaks))
            txt = '；'.join(f'{m} {z}' for m, z in uniq)
            has_heat = any(e.get('kind') == 'heat_matrix' for e in ex)
            if drawn:
                # 「其余各图窗口里没落进断点」曾经是写死的一句 —— 而它在 asx / enx 上是**假的**
                # （asx 37 张图只有 2 张画了线，其余 31 张的窗口里都含着 2023-10 与 2024-08）。
                # 断点画在哪几张图上，由各页 spec 的 break 登记决定（按列登记，只画到用了那列的图）；
                # 「窗口含不含断点月」是另一回事，两者本来就不是一码事。所以这句改成**现算**：
                # 逐图把断点月换成本页的 x 标签，看在不在它自己的 xlabels 里。
                bm = {mlab(pd.Period(m, 'M')) for m, _ in uniq}
                silent = [e for e in ex
                          if not e.get('break_at') and bm & set(e.get('xlabels') or ())]
                out.append(
                    '<b>⚠️ 口径断点。</b>' + txt + '。红色竖虚线画在 Exhibit '
                    + '、'.join(str(e['n']) for e in drawn)
                    + '（断点那一期的<b>左缘</b>，语义是「从这一期起与左侧不可比」）'
                    + (f'。<b>另有 {len(silent)} 张图的横轴窗口同样跨过这些月份、但没有画线</b>'
                       f'（Exhibit ' + '、'.join(str(e['n']) for e in silent)
                       + '）—— 断点是<b>按列</b>登记的，只画到用了那一列的图上，'
                         '而窗口跨不跨断点月是另一回事。读这些图的跨断点比较同样要扣掉这一层。'
                       if silent else '；其余各图的横轴窗口里没有落进断点。')
                    + ('热力矩阵没有连续横轴、画不出断点线，跨断点读它的同比要自己扣掉这一层。'
                       if has_heat else ''))
            else:
                out.append(
                    '<b>口径断点已滚出当前所有窗口。</b>' + txt +
                    '。这些断点不在任何一张图的横轴范围内，故本页不画断点线 —— '
                    '但长期趋势仍要从最后一个断点之后起算。')
        stock_zh = [c['zh'] for g in self.groups for c in g['cols'] if c['stock']]
        if stock_zh:
            out.append(
                f'<b>存量与流量分开读。</b>{"、".join(stock_zh)}是<b>存量</b>（期末截面值），'
                f'其余列是流量（日均或当月合计）。两者不能相加；跨币种换算时流量配月均汇率、'
                f'存量配月末汇率。存量列一律单独成图，不与流量列共轴。')
        if self.empty:
            out.append(f'<b>本次跳过的列。</b>{"、".join(self.empty)} 在当前 CSV 里整列为空，'
                       f'已从图与表里剔除（不画空图，也不留一行「—」冒充有数据）。'
                       f'源表补上之后重跑即自动回来。')
        if self.holes:
            out.append(f'<b>⚠️ 源表缺行。</b>{"、".join(self.holes[:8])}'
                       f'{"（等 %d 个月）" % len(self.holes) if len(self.holes) > 8 else ""}'
                       f' 在 <code>series/{self.spec["csv"]}</code> 里没有对应行，'
                       f'已补成空行：图在缺口处断笔（不可比的相邻期不能连成一条线），'
                       f'平滑类图型自动降级为不平滑的折线。')
        # 三个判据按**真画出来的图**算，不按 spec 声明算 —— 声明了一张画不出来的图
        # 与「本页本来就没这种图」，在页面上长得一模一样，而这段话只该描述前者之外的事实。
        # `ex_history` 出的头条长历史图也是 kind='lines'，所以「有没有多列折线组图」
        # 不能靠扫 kind，改由 `ex_lines` / `ex_heat` 自己记账（见那两个函数）。
        _has_lines = bool(getattr(self, 'saw_group_lines', False))
        _has_heat = bool(getattr(self, 'saw_group_heat', False))
        _has_mix = any(e.get('kind') == 'stacked_dual' for e in (ex or [])
                       if isinstance(e, dict))
        out.append(
            # ⚠️ 这一段**只讲这一页真画过的那几条规则**。它原来是一段无条件文案，
            # 开头写着「全部由底座按数据形状定」—— 而 `groups[].mix` 让 spec 也能
            # 指定图型，同一段里还并列着几条这一页一张图都没命中的规则
            # （tmx 现在一张折线组图、一张热力矩阵都没有）。
            # 「页面上说的规则」与「页面上画的图」对不上，读者只会当成自己看漏了。
            (f'<b>图型选择规则（'
               + ('底座按数据形状定；声明了 mix 的组另由 spec 指定'
                  if _has_mix else '全部由底座按数据形状定，不逐家手调')
               + '）。</b>'
               + '① 同一张图上<b>只放同一单位</b>的列：量纲不同的列自动拆成各自成图 —— '
                 '把 2 : 15 : 64 三个量级画在一根轴上，最小的那条振幅只占画布 1%，等于白画。'
               + (f'② 一桶 1 列画柱图（水平值 + 次轴同比）、2–{MAX_LINES} 列画折线、'
                  f'超过 {MAX_LINES} 列改画热力矩阵：数据色只有 6 个，'
                  f'第 6 条线必然与别人同色。' if _has_lines or _has_heat else
                  '② 本页每一桶都只有一列（或整桶被 <code>mix</code> 收走），'
                  '所以一张多列折线图都没有；多列时底座会按列数改画折线或热力矩阵。')
               + ('③ 折线在窗口内逐点稠密时用平滑的 lines_endlabels，有缺口时降级为不平滑的 '
                  'lines —— 平滑图型会把 null 当 0，画出一条塌到零的假线还不报错。'
                  if _has_lines else '')
               + ('④ 热力矩阵画同比不画水平值：色标是全表共用的 5/95 分位，'
                  '水平值量级差几十倍时会被最大的那列吃掉整条色标。' if _has_heat else '')
               + ('⑤ 声明了 <code>mix</code> 的组出<b>两张</b>：合计的水平值柱'
                  '（次轴同比，流量走 12 个月滚动、存量走点对点）与分项的 100% 占比堆叠。'
                  '各段之和逐月复算，对不上就不发页。' if _has_mix else '')))
        # ── 同比口径：从 yoy_log 账本现算，逐处点名（CONTRACT §6.1 第 3 条）──
        # 这段话为什么必须由底座生成、图号为什么必须派生，见 log_yoy 的 docstring。
        # 文案按类别分段拼装，只写账本里真有的类别 —— 页上没画滚动同比就绝不出现
        # 「其余均为滚动」这类以偏概全的断言（没有滚动图时那是一句假话）。
        cal_ns = {}
        for r in self.yoy_log:
            cal_ns.setdefault(r['cal'], set()).add(r['n'])
        if cal_ns:
            def _exs(k):
                return '、'.join(f'Exhibit {j}' for j in sorted(cal_ns[k]))
            # 「并存」只看滚动 vs 单月两大侧：mom / mom_pp / stock / heat 都属单月侧
            # 的合法形态。读者要防的是拿滚动折线和单月读数跨口径比高低。
            mixed = 'ttm' in cal_ns and len(cal_ns) > 1
            seg = []
            if 'ttm' in cal_ns:
                seg.append(
                    f'{_exs("ttm")} 的次轴金色折线：<b>{TTM_WIN} 个月滚动合计的同比</b>'
                    f'（流量的默认口径 —— 任意连续 {TTM_WIN} 个月覆盖同一套日历与'
                    f'到期周期，交易日数与月度形状的差整个消掉）')
            if 'mom' in cal_ns:
                seg.append(
                    f'{_exs("mom")}：<b>单月同比</b>（当月对去年同月）—— 单月口径'
                    f'吃基数与日历效应，毛刺比滚动口径大，同一序列的两种同比甚至'
                    f'可以符号相反，跨图比增速之前先核对口径')
            if 'mom_pp' in cal_ns:
                seg.append(
                    f'{_exs("mom_pp")}：比率列的同比 = 单月口径的<b>百分点差</b>'
                    f'（比率不做滚动合计也不做滚动均值 —— 「一年的平均比率」要按量'
                    f'加权，换个窗口得不到）')
            if 'stock' in cal_ns:
                seg.append(
                    f'{_exs("stock")}：存量列的<b>点对点同比</b>（月末快照 vs 去年'
                    f'同月月末）—— 存量不可加总，把 12 个月末快照相加不指代任何'
                    f'真实的量，所以存量没有「滚动合计」口径可选')
            if 'heat' in cal_ns:
                seg.append(
                    f'{_exs("heat")}（热力矩阵）：格内是<b>单月同比</b>，按豁免保留 '
                    f'—— 这张图逐格看的就是单月波动，抹平了信息就没了')
            out.append(
                '<b>同比口径'
                + ('（本页并存两种口径，逐处点名 —— 不要跨口径比高低）' if mixed else '')
                + '。</b>' + '；'.join(seg) + '。'
                + '汇总表（Exhibit 1）的 m/m 与 y/y 列及页顶抬头行是「本月 / 上月 / '
                  '去年同月」三个具名月份的<b>单月</b>读数（运营核对用途，按豁免保留 '
                  '—— 放滚动值进去与列头自相矛盾）。'
                + ('趋势判断看滚动折线，当月核对看单月读数，两者并存是分工不是疏忽。'
                   if mixed else ''))
        _band_n = next((e.get('n') for e in (ex or []) if isinstance(e, dict)
                        and e.get('kind') == 'lines'
                        and 'P90' in str(e)), None)
        out.append(
            f'<b>汇总表读法。</b>「{pctile.WINDOW // 12}Y %ile」= 当月读数在最近 '
            f'{pctile.WINDOW} 个月中的分位，由全站唯一的 <code>build/pctile.py</code> 计算'
            f'（判据：把这一行的分位在近 24 个月里逐月回放，若 ≥70% 的月份钉在 0 或 100，'
            f'该行对这一列没有区分度，留空）。'
            # ⚠️ 这句话原来无条件印着「Exhibit 2 的灰色分位带与它同窗口同口径」——
            # `headline_style='bar_yoy'` 的页面上根本没有分位带那张图，那就是一句
            # 指着不存在的图的话。改成按**真画出来的图**收放。
            + (f'Exhibit {_band_n} 的灰色分位带与它同窗口同口径。' if _band_n else
               '本页没有画分位带那张图（开篇图是「柱 + 次轴同比」，'
               '带的上下沿与柱同量纲、画上去会被读成第三根柱），'
               '所以这一列的分位只在本表里出现。')
            + f'比率类指标的差异用 pp／bp，不用百分比的百分比变化。')
        if disp:
            # 「图上按百万、表里按张」这件事必须在页注里说一次。不说的话，读者拿 Exhibit
            # 里的 1.73 去对核对表的 1,729,208，会以为其中一处算错了。
            by_k = {}
            for u, k, w in disp:
                by_k.setdefault((k, w), []).append(u or '无单位')
            det = '；'.join(f'轴标题写「{w}」的图 ÷ {int(k):,}（{"、".join(dict.fromkeys(us))}）'
                            for (k, w), us in sorted(by_k.items(), reverse=True))
            out.append(
                f'<b>图上的显示缩放（只作用于图，不作用于表）。</b>{det}。'
                f'倍数按<b>每张图自己那条序列的量级</b>定，所以同一个单位在不同 Exhibit 上'
                f'可能一个按百万、一个按千 —— 每张图的轴标题与图注各写明一遍。'
                f'做这件事的原因是几何而不是口径：数值标签居中钉在自己那根柱上，7 位数带'
                f'千分位的标签宽 35.6px，而一格柱只有 18.4px 宽，标签会向左伸出去压住纵轴'
                f'刻度，读成「8000000076,941,267」这样两个数粘在一起的一串。'
                f'<b>汇总表与末尾核对表一律保持官方原始量级</b>，它们的用途正是与官方披露'
                f'逐格对账；同一个数在图上与表里数量级不同，不是其中一处算错了。')
        out.append(
            f'<b>末尾核对表。</b>近 {WIN_SHORT} 个月、本页单位，可与官方披露逐格对账；'
            f'列数较多时窄屏需要左右滚动。'
            # 这句原来写死成「源表是 0–1 的小数比率，本页统一按百分数显示」——
            # 但喂它的判据是 `c['scale'] != 1.0`，那涵盖**任何**倍数换算。tmx 上列出的
            # 15 列全是 ×1e-9 / ×1e-6 的量级换算，一个比率都没有，那句话 100% 是假的。
            # 改成按实际倍数分档：全是 ×100 才说「比率→百分数」，否则只说量级换算。
            + (f'其中 {"、".join(scaled)} 做过恒等换算'
               + ('（源表是 0–1 的小数比率，本页统一按百分数显示）'
                  if _scales and set(_scales) == {100.0} else
                  '（括号里是换算倍数；这是量级换算，不改变口径）')
               + '，除此之外不做任何换算。' if scaled else
               '除各列自己声明的单位外不做任何换算。')
            + f'表尾若有月份晚于本页数据月 {latest}，那是发布更快的腿，'
              f'其余列在那些行显示「—」。')
        # 窗口内恒为 0 的序列：图不出，但**列仍在核对表里**（官方报的就是 0，
        # 那也是一个要能与披露逐格对上的事实）。这里点名说清楚是哪几条、
        # 以及它们最后一次非零是什么时候 —— 一个数都不写死，全部现算：
        # 指标哪天恢复非零，图自动回来、这段话自动消失。
        if getattr(self, 'flat0', None):
            det = []
            for f in self.flat0:
                w0, w1, wn = f['win']
                nz_s = (f'最后一次非零是 {f["last_nz"][0]}（'
                        f'{fmt_val(f["last_nz"][1], f["fmt"])} {f["unit"]}）'
                        if f['last_nz'] else '全序列从未出现过非零值')
                det.append(f'{f["gz"]}／{f["zh"]}（{w0}–{w1} 共 {wn} 个月恒为 0，{nz_s}）')
            out.append(
                '<b>本轮恒为 0、故不出图的序列。</b>' + '；'.join(det)
                + '。<b>它们仍留在末尾核对表里</b> —— 「官方报的就是 0」与「本页没有这个'
                  '指标」是两回事，核对表要能对上前者。不画图是因为柱图的纵轴上界写死成 '
                  # TODO（不在本轮改）：这里本来写的是那三个字母的英文缩写，结果被
                  # build/payload_guard.py 拦下 —— 它是**按子串**在展示字符串里搜那个词的，
                  # 散文里提到它就误杀。判据应当只查**数值字段**、不查散文。
                  # 现在绕开是因为 payload_guard.py 被每个 builder import，这一轮动它风险太大。
                  '<code>max × 1.22</code>，max 也是 0 时上下界重合、'
                  '坐标全成非有限值，'
                  '画出来是一团糊在画布角上并越出卡片的东西，不是一排零高的柱。')
        # 声明了 decomp / ttm_yoy 却没画出来，一律点名说是哪一条、为什么 ——
        # 静默少一张图与「这家本来就没有这张图」在页面上长得一模一样。
        if getattr(self, 'skipped', None):
            out.append('<b>本轮未出的派生图。</b>'
                       + '；'.join(self.skipped)
                       + '。数据补齐后自动回来，不需要改 spec。')
        spec_notes = [str(x) for x in (self.spec.get('notes') or [])]
        self.md_fixed = sum(1 for x in spec_notes if _MD_BOLD.search(x))
        out += [md_bold(x) for x in spec_notes]
        return out


# ══════════════════════════════ 驱动 ══════════════════════════════
def load_spec(ticker, specs_dir=SPECS):
    """按路径加载 build/specs/<ticker>.py 里的 SPEC。"""
    p = os.path.join(specs_dir, f'{ticker}.py')
    if not os.path.exists(p):
        raise SpecError(f'找不到配置文件 {p}')
    spec_ = importlib.util.spec_from_file_location(f'spec_{ticker}', p)
    mod = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(mod)
    if not hasattr(mod, 'SPEC'):
        raise SpecError(f'{p} 里没有名为 SPEC 的 dict')
    s = mod.SPEC
    if s.get('ticker') != ticker:
        raise SpecError(f'{p} 的 ticker={s.get("ticker")!r} 与文件名 {ticker!r} 不一致 —— '
                        f'目录名 = data 文件名 = payload.ticker 三者必须逐字相同')
    return s


def build(spec, series_dir=SERIES, out_dir=DATA, quiet=False):
    """一份 SPEC → data/<ticker>.js。门槛没到时返回 None（不写文件，退出码仍是 0）。"""
    page = Page(spec, series_dir)
    payload, why = page.payload()
    t = page.ticker
    if payload is None:
        if not quiet:
            print(f'[{t}] 门槛没到，本次不出页：{why}')
            print(f'[{t}] 已有的 data/{t}.js（若存在）原地不动，退出码 0。')
        return None
    if page.empty and not quiet:
        print(f'[{t}] 跳过整列为空的列：{"、".join(page.empty)}')
    if page.holes and not quiet:
        print(f'[{t}] ⚠️ 源表缺 {len(page.holes)} 个月的行，已补空行：{page.holes[:6]}')
    for why in (getattr(page, 'skipped', None) or []):
        if not quiet:
            print(f'[{t}] ⚠️ 派生图未出：{why}')
    for line in (getattr(page, 'decomp_report', None) or []):
        if not quiet:
            print(f'[{t}] {line}')
    for n_, sym, det in (getattr(page, 'tight', None) or []):
        # 不硬失败：压 1px 的图仍然读得出来，而硬失败会让 monthly_run 停更整页。
        # 但必须响 —— 这是 VISUAL_QA §3.F 那 18 处压字唯一的自动化哨兵。
        if not quiet:
            print(f'[{t}] ⚠️ Exhibit {n_} {sym}：{det}')
    if getattr(page, 'md_fixed', 0) and not quiet:
        print(f'[{t}] spec 的 notes 里有 {page.md_fixed} 条用了 Markdown 的 **粗体**，'
              f'已替换成 <b>（notes 走 innerHTML，星号会原样印在页面上）')
    out = os.path.join(out_dir, f'{t}.js')
    # gen 传 'single' 而不是 ticker：首行注释写的是「由 build/<gen>.py 生成」，
    # 传 ticker 会指向一个**并不存在**的 build/<t>.py，下一个人照着去找会扑空。
    # 代价是护栏的报错前缀丢了 ticker，所以这里补一层，把是哪一家写回去。
    try:
        payload_guard.write_dash(out, payload, 'single')
    except payload_guard.PayloadGuardError as e:
        raise payload_guard.PayloadGuardError(f'[{t}]（spec: build/specs/{t}.py）{e}')
    if not quiet:
        idx = list(page.df.index)
        print(f'[{t}] 数据 {idx[0]} → {idx[-1]}（{len(idx)} 个月）；'
              f'data_through = {payload["data_through"]}')
        print(f'[{t}] Exhibit 1 汇总表 + Exhibit {payload["exhibits"][0]["n"]}-'
              f'{payload["exhibits"][-1]["n"]}（{len(payload["exhibits"])} 张图）'
              f' + Exhibit {payload["table"]["n"]} 核对表')
        print(f'[{t}] 写出 {out}  ({os.path.getsize(out) / 1024:.1f} KB)')
        print(f'[{t}] {payload["headline"]}')
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='单公司页通用底座：spec → data/<ticker>.js')
    ap.add_argument('tickers', nargs='*', help='要构建的 ticker（= build/specs/<t>.py）')
    ap.add_argument('--all', action='store_true', help='构建 build/specs/ 下的全部配置')
    a = ap.parse_args(argv)
    ts = list(a.tickers)
    if a.all:
        ts += sorted(f[:-3] for f in os.listdir(SPECS)
                     if f.endswith('.py') and not f.startswith('_')) if os.path.isdir(SPECS) else []
    ts = list(dict.fromkeys(ts))
    if not ts:
        ap.error('至少给一个 ticker，或 --all')

    # ── 反向守卫：别把已经归 mrbase 的那几页打回旧图列 ──────────────────────────
    # 2026-08 起 7 家台湾半导体走 build/mrbase.py + build/mrspecs/<t>.py（TSM 图列），
    # 入口是 build/<t>.py 薄壳。monthly_run.builder() 认薄壳优先、走不到本脚本，
    # **但本脚本的 `--all` 会枚举 build/specs/ 全量**，而那 6 家的旧 spec 还躺在那里
    # （它们作为页面配置已经死了，只被 make_shells12.singles() 当枚举源用）。
    # 于是人手跑一次 `python3 build/single.py --all`（docs/SINGLE_SPEC.md §0 与
    # docs/VISUAL_QA.md 的幂等核对那一步都在教这条命令）就会**静默**把 6 页的
    # payload 覆盖回 decomp/ttm_yoy/seasonality 那套旧图列 —— 页面不报错、闸门也全过，
    # 只是图列悄悄换了一套。这是本轮路由审计查出的唯一真撞车口子，故在这里单向堵死。
    # 判据与 mrbase.owned_elsewhere() 同源：看 build/<t>.py 里有没有 mrbase 字样。
    owned = []
    for t in ts:
        shell = os.path.join(HERE, f'{t}.py')
        try:
            with open(shell, encoding='utf-8') as fh:
                if 'mrbase' in fh.read():
                    owned.append(t)
        except OSError:
            pass
    if owned:
        for t in owned:
            print(f'[{t}] 跳过：本页已归 build/mrbase.py（build/{t}.py 是薄壳），'
                  f'用 `python3 build/{t}.py` 重建，不要走 single.py')
        ts = [t for t in ts if t not in owned]
        if not ts:
            # 显式点名给的 ticker 全被挡下 ⇒ 是用错命令了，非零退出把它喊出来。
            # `--all` 展开后全被挡下不可能发生（specs/ 里还有 10 家交易所）。
            return 1

    for t in ts:
        build(load_spec(t))
    return 0


if __name__ == '__main__':
    sys.exit(main())
