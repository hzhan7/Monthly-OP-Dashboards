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
| `yoy_line` | cboe/hkex 各一份，判据相同（基数 < 中位绝对值 15% 或异号则放弃） | 算术转发 `build/yoy.py` 的 `mom_yoy()`（比率走百分点差）；近零基数掩码与窗口对齐留在本文件，阈值取 `yoy.NEAR_ZERO_BASE_FRAC` |
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

    python3 build/single.py ndaq             # 建一家
    python3 build/single.py ndaq db1 sgx     # 建几家
    python3 build/single.py --all            # build/specs/ 下全部

退出码：0 = 成功或「门槛没到、本次不出页」（原文件原地不动）；1 = spec 写错 / 数据结构
不对（要人去改）。两者的区别是「等数据」还是「等人」，见 `resolve_through()` 的注释。
"""
import argparse
import datetime
import importlib.util
import math
import os
import re
import sys

import numpy as np
import pandas as pd

import axisfmt
import chartscale
import brief as B         # 数据总结（brief）的规则库与字数护栏（build/brief.py），全站共用
import glossary as gloss   # 名词释义的版式层与护栏（build/glossary.py），全站共用
import mrwin              # 窗口排版的裁决层（通栏 / x 标签抽稀），与台湾半导体 7 家共用
import payload_guard
import pctile
import yoy as ycal        # 同比口径的**唯一实现**（build/yoy.py）。取别名是因为本文件里
#                           已经有一个模块级函数 `yoy(v, i, lag)`（末期对 12 期前的变化率，
#                           给 summary / 抬头行用），两个名字撞在一起会静默遮蔽其中一个。

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

# ══════════ 「这一列是不是比率」——判据不只看 fmt（CONTRACT §6.1 第 4 条）══════════
# 2026-09 之前这里只有一行 `c['fmt'] in RATIO_FMT`，于是**显示格式顺带决定了口径**：
# 一列真比率只要因为别的理由没配 pct*/pp*，它的同比就静默从「百分点差」翻成
# 「百分比的百分比变化」—— 正是第 4 条点名禁止的那种（RPC 0.24 → 0.25 是 +1bp，
# 不是 +4.2%）。这不是假想：`build/specs/miax.py` 的 `share_equities_pct` 被本底座
# **另一条**护栏（比率量纲体检要求 pct* 列缩放后最大值 > 1.5，而这一列真实上限只有
# 1.3）挤出了 RATIO_FMT，`build/specs/ndaq.py` 的 NTX / PSX 两列（份额上限 4.52% /
# 1.43%）出于逐字相同的理由也被挤了出去 —— 一条**量纲**护栏顺手改掉了三列的**口径**，
# 而且不响。2026-09-02 全站实测被这样翻掉的图有 5 张（ice Ex12/Ex15、miax Ex9/12/13）。
#
# 判据现在三级，从强到弱：
#   ① spec 显式 `ratio: True/False` —— 写 spec 的人知道这一列是什么，最权威。
#      它同时是本底座给 spec 侧留的出口：下面 ③ 认不出来的真比率靠它声明。
#   ② `fmt ∈ RATIO_FMT` —— 显式选了 pct*/pp* 格式的列就是按比率显示的列（原判据）。
#   ③ `yoy.classify()` 判成比率 **且** `unit` 也是比率的量纲 —— 两个互相独立的证据
#      同时成立才算数。为什么不能只信 classify：它按**列名词根**猜，`_RATIO_PAT` 里的
#      `rate|rates` 会把利率**产品**的成交量与未平仓（`adv_eurex_rates_contracts`、
#      `oi_rates_kcontracts`、`vol_rates_futures_contracts`…）、`share` 会把**个股**
#      期货 ADV（`mx_adv_share_futures_contracts`）、`margin` 会把保证金**余额**
#      （`margin_total_audbn`，A$bn）统统判成比率 —— 2026-09-02 在本底座这 10 页上实测
#      这类假阳性有 14 列，只信 classify 会把它们的同比整批翻成 pp，那是把第 4 条的
#      错误反着犯一遍。`yoy.classify()` 自己的 docstring 也写着「只是给个默认建议，
#      不是权威 —— 有疑问时调用方显式传 kind」。
#      为什么也不能只信 unit：`asx.avg_value_per_trade_aud`（A$/trade，量级 1e4）
#      的量纲长得和 RPC 一模一样，但它的同比只能是百分比变化 ——「平均每笔金额同比
#      +3000.00pp」是句胡话。它的列名里没有任何比率词根，classify 判 flow，挡住了。
#
# 比率量纲怎么认：单位里有 `%`，或者单位是「X 每一个**可数的活动单位**」
# （USD/contract、USD/100 shares、A$/trade…）。分母是**时间**的不算（contracts/day、
# USD bn/day 是日均流量，CONTRACT §6.4 明说日均列是流量）；分母是**货币**的也不算
# （`lseg.gbp_eur_rate` 的 EUR per GBP 是汇率，习惯用 % 报，写成「+16bp」是另一句
# 胡话）。白名单式判定 —— 认不出的单位一律**不**算比率，与 `classify()` 的
# 「拿不准判存量」同一个保守方向：漏判只是维持现状（图仍按 % 画，可由 ① 纠正），
# 误判则是当场印出一句假话。
_RATIO_UNIT_DENOM = re.compile(
    r'(?:/|\s+per\s+)\s*[\d,\s]*'
    r'(contracts?|shares?|trades?|transactions?|orders?|messages?|lots?|张|股|笔|单)\b',
    re.I)


def unit_is_ratio(unit):
    """`unit` 这个量纲配不配用百分点差表示变化。见 RATIO_FMT 下方那段。"""
    u = (unit or '').strip()
    if not u:
        return False
    return ('%' in u) or bool(_RATIO_UNIT_DENOM.search(u))


# ══════════ 比率里的一个子类：**分子是钱**的比率，它的差不是百分点 ══════════
#
# `unit_is_ratio()` 认的「比率」有两种分子：
#   · 百分数（`%`、`% of UK lit order book`）—— 差出来是**百分点**，pp / bp 是对的；
#   · 钱（`USD/contract`、`USD/100 shares`）—— 差出来仍然是**钱**，
#     「每张少收 0.01 美元」。把它叫 1bp 是换了一个量在说话。
#
# 这一处 2026-09 之前是错的，而且错得不显眼：ice Exhibit 12 / 15 与 miax Exhibit 9 /
# 13 四张图的右轴标题写着「pp y/y」、图注写着「同比 −1bp」，而那四列的量纲是
# USD/contract 与 USD/100 shares。ICE 的 NYSE 期权 RPC 从 0.05 掉到 0.04 是**跌了
# 五分之一**，页面上却写着「−1bp」—— 一个只看页面的读者会把 20% 的单位经济下滑
# 读成万分之一的波动。汇总表（Exhibit 1）那两行同样印着「-1bp」「+0.5bp」。
#
# ⚠️ **改的只是这个差的单位名，算术一格没动。** 这几列走的仍然是
# CONTRACT §6.1 第 4 条要的 `yoy.mom_yoy(s, yoy.RATIO)`（当月减去年同月，
# 不是「百分比的百分比变化」），payload 里 `yoy.values` 逐字节不变 ——
# `tools/check_yoy_caliber.py` 的回源复算认的是那些数，动它们等于拿判据的失明换措辞。
# §6.1 第 4 条里那句「RPC 从 0.24 到 0.25 是 +1bp」说的就是这同一个减法；
# 本轮只是不再把这个差叫作 bp。契约文本不在本文件里，这里只改单位名，不动契约。
#
# 判据是白名单式的，与 `unit_is_ratio()` 同一个保守方向：**分子里认得出币种记号**
# 才算「钱」，认不出一律维持现状（照旧按 pp/bp 走）。误判的代价是当场印出一句
# 假单位，漏判只是维持现状。
_MONEY_NUM = re.compile(
    r'(?:US\$|NT\$|A\$|C\$|S\$|HK\$|R\$|\$|£|€|¥|₩|'
    r'USD|EUR|GBP|JPY|CAD|AUD|SGD|HKD|CHF|CNY|RMB|TWD|SEK|NOK|DKK|KRW|INR|BRL)',
    re.I)


def unit_is_money_ratio(unit):
    """这个比率量纲的**分子是钱**吗 —— 决定它的差该叫「pp/bp」还是「每单位多少钱」。

    条件三条同时成立：① 本来就是 `unit_is_ratio()` 认的比率量纲；
    ② 单位里没有 `%`（有 `%` 的分子就是百分数，差就是百分点）；
    ③ 分母记号（`/` 或 ` per `）**左边**认得出币种。取左边而不是整串，是因为
    `USD bn/day` 这种「按天的金额」压根进不了 ①（分母是时间不是可数活动单位），
    而 `EUR per GBP` 这种汇率同样进不了 ①，两类都不必在这里再挡一次。
    """
    u = (unit or '').strip()
    if not u or '%' in u or not unit_is_ratio(u):
        return False
    head = re.split(r'/|\s+per\s+', u, 1)[0]
    return bool(_MONEY_NUM.search(head))


def col_is_money_ratio(c):
    """这一列的同比差该不该按「钱」印。`col_is_ratio()` 与量纲两票都要过。"""
    return col_is_ratio(c) and unit_is_money_ratio(c.get('unit'))


def col_is_ratio(c):
    """这一列的「同比」该不该走百分点差（pp/bp）。三级判据见 RATIO_FMT 下方那段。

    ⚠️ 这是全底座**唯一**的比率判据 —— `chg_txt()`、`Page.is_ratio()`、
    `_norm_level_yoy()` 的比率护栏全部走它。从前 `chg_txt` 与 `Page.is_ratio`
    各写了一遍 `c['fmt'] in RATIO_FMT`，两处一旦分叉，同一张图的次轴单位与图注里
    那句「同比 X」就会各说各话。
    """
    if c.get('ratio') is not None:
        return bool(c['ratio'])
    if c['fmt'] in RATIO_FMT:
        return True
    return ycal.classify(c['col']) == ycal.RATIO and unit_is_ratio(c.get('unit'))


def _mark_section(ex, start, want):
    """把 `ex[start:]` 这一段想要的分节标题记在临时键 `_section` 上（2026-09 新增）。

    只记不判：真正「哪一张起标题、哪一张算延续」由 payload() 末尾那一轮收口统一决定。
    分两步而不是就地判断，是因为**同一个 section 可以跨好几个 group** —— 就地判断
    就得让每个挂载点自己知道「我是不是这一节的第一张」，而它看不到别的组。

    `want` 为空 = 这一段没声明 ⇒ 不写 `_section`，收口时视为「沿用上一节」，
    不会打断一个已经开着的 section，也不会凭空起一个空标题。
    """
    if not want:
        return
    for e_ in ex[start:]:
        e_['_section'] = str(want)


SPEC_KEYS = {'ticker', 'name', 'title', 'csv', 'ccy', 'source',
             'headline', 'groups', 'slow_cols', 'breaks', 'notes',
             'decomp', 'level_yoy', 'headline_style', 'glossary',
             # ── 以下三个 2026-09 新增，全部**加性、可选**：不给就一个字节都不变 ──
             # 'brief'：页顶「本月读数怎么读」，与 glossary 同一套分派（字面量或
             #   callable(page)）。此前只有手写生成器写得出，spec 页一律空着。
             # 'headline_section' / 'season_section'：头条派生的那两段图（①② 与 ④）
             #   由 spec 自己命名章节 —— 它们不属于任何一个 group，没有别的挂载点。
             'brief', 'headline_section', 'season_section'}
SPEC_REQUIRED = {'ticker', 'name', 'title', 'csv', 'ccy', 'source', 'headline', 'groups'}
COL_KEYS = {'col', 'zh', 'unit', 'fmt', 'stock', 'scale', 'ratio', 'no_yoy'}
COL_REQUIRED = {'col', 'zh', 'unit', 'fmt'}
GROUP_KEYS = {'zh', 'cols', 'mix', 'section', 'ratio_rhs', 'spike_cap'}
GROUP_REQUIRED = {'zh', 'cols'}

# ── groups[].spike_cap —— 尖刺截轴的**开关**（2026-09 补，默认关）────────────────
# `True` = 本组的多列对比图允许 `Page.spike_cap()` 截轴（判据仍然全部现算，见那个方法）。
# 不给 / `False` = 一步都不走，逐字节回到没有这条通路之前。
#
# ⚠️ **为什么必须是 opt-in，而不是靠数据判据当闸。** 这条通路 2026-09 上线时是
# **全站无条件**生效的，唯一的闸是数据相关的 `SPIKE_HEAD = 0.35`。而实测「日常上沿
# 占轴比例」在别人的页上是 jpx Ex16 = 0.526、db1 Ex7 = 0.567 —— 离门的距离**随月份
# 漂**，哪天漂过去，那两页会在页面所有者没下过任何指令的情况下被截轴。实测反例：
# 只把 `series/jpx.csv` 的 `adv_n225_mini_kcontracts` 在窗口中段注入一个月的大额
# （1,094.6 → 5,200），jpx Ex16 的比例就掉到 0.304，spec 一个字没改、页面上多出
# 一条截轴与一行「axis capped」。
# 本轮另两条新底座通路（`groups[].ratio_rhs`、`decomp` 的 `bucket` / `after_group`）
# 走的都是同一条纪律：**加性、可选、缺省逐字节不变**。截轴改的是读者读到的量程，
# 比那两条更该守这条纪律，不该反而是唯一的例外。
#
# 落在 group 上而不是 SPEC 顶层，理由与 `ratio_rhs` 一样：需求是逐组提的
#（asx 页面所有者 2026-09 的原话点的是「ex19/20」那两组融资图），页级开关会把
# 同一页其余组的图一起交出去，而那些图没人要求过。

# ── groups[].ratio_rhs —— 「两根并排柱 + 右轴比值线」一张图 ────────────────────
# 与 `mix` 一样，这是 `groups[].cols` 里各列**彼此独立**那条默认假设的例外：
# 声明了 ratio_rhs，就是声明「num 这一列 ⊆ den 这一列」这个**包含关系**
# （num 是 den 的一部分，逐月 den > 0 且 0 ≤ num ≤ den）。声明之后这一桶不再画折线，
# 改画 `grouped_bars`：两条列各出一根并排柱（左轴，同一单位），比值 num/den×100
# 走右轴（pct1）。
#
# 为什么必须是这个图型：引擎里能双轴的只有 5 种 kind（`docs/CHART_KINDS.md` §4），
# 其中 `lines` / `lines_endlabels` **没有次轴** —— 不是「payload 没给」，是绘图、
# 图例、表格、tooltip 四处都不读 `ex.line`。而把 80–91 的无量纲比值塞进 3.6–12.0
# A$bn/day 的同一根左轴，两条 ADT 线会被压进绘图区高度的一成，等于把这张图作废。
# `grouped_bars` 是唯一一种「N 条同单位序列 + 可选右轴线」的图型，不动引擎就装得下三样。
#
# 比值**由底座现算**，不进 CSV：`COL_KEYS` 是封闭白名单，没有派生列这个概念，
# 而 spec 引用的列必须真实存在于 CSV，所以「往 CSV 里补一列比值」既绕不过校验，
# 也会让同一个数在源表和图上各存一份、迟早分叉。
#
# 构建期硬校验（全部在 `Page.__init__` 里，见 `ratio_rhs` 那一段）：
#   ① num / den 必须都在**本组**的 cols 里（拼错的列名会让整张图静默退回折线）；
#   ② 两列同 unit、同 stock 档，且本组里没有第三列与它们同 unit ——
#      分桶按 unit 走，有第三列时这一桶就不是「恰好 num 与 den 两列」；
#   ③ 逐月 den > 0、num ≥ 0、num ≤ den，有反例就报出月份与两个读数并硬失败。
#      `num ≥ 0` 与另外两条同源：包含关系里 num 是 den 的一段，一段不可能是负的。
#      它同时是图注三句话的前提（比值区间、右轴刻度、两轴零点对齐是空操作），
#      所以必须是**护栏**而不是注释里的一句假设 —— 见 `Page.__init__` 里 bad_neg 那段。
#   ④ 可选的 `dup_part`：本页某条 mix 的分项列名，声明「本比值 ≡ 100% − 那一段占比」。
#      底座会**逐月复算**两者的差，把实测最大差写进图注；差超过 `RATIO_DUP_TOL`
#      就硬失败（图注里那句「这是同一条序列」会变成假话）。
#      **底座只印它能证明的**（实测最大差 / 中位 / 共同月数 / 容差）。「两者为什么会
#      有差」是底座证不了的事实断言（口径差？取整差？还是别的），由可选的 `dup_note`
#      从 spec 承载 —— 从前这句写死成「这里是日均、那里是当月合计」，而两侧同口径、
#      逐月差恒为 0.0000pp 的组合照样会印出它。
RATIO_RHS_KEYS = {'num', 'den', 'zh', 'note', 'dup_part', 'dup_note'}
RATIO_RHS_REQUIRED = {'num', 'den', 'zh'}
#: `dup_part` 声称的恒等式允许的最大逐月偏差（百分点）。本仓真实的来源只有一种：
#: 日均口径（各列先除以交易日数再取整）与当月合计口径各自四舍五入的残渣。
RATIO_DUP_TOL = 0.05
#: 右轴比值线的候选色，按序取第一个没被并排柱占用的。
#: **GOLD 不在表里**：本站金色是同比专用色（页面所有者 2026-09 /cboe/ 那一轮的原话
#: 「不用 GOLD，本站金色是同比专用」），这条线不是同比。
#: RED 也不在：它是断点与截轴离群值的专用色（见 `MIX_SEG_COLORS` 上方那段）。
RATIO_RHS_COLORS = ('GREEN', 'MBLUE', 'BLUE', 'NAVY', 'GRAY')
#: 图注里指认「右轴那条 X 色的线」用的中文色名。**由挑色的结果现算**，不写死一个
#: 「绿线」—— 柱的配色一变，挑出来的线色就换人，图注里那个词必须跟着换，
#: 否则页面上写着「绿线」而画面上是蓝线（`stacked_dual` 那处从前就写死过 GREEN）。
_COLOR_ZH = {'GREEN': '绿', 'MBLUE': '中蓝', 'BLUE': '浅蓝', 'NAVY': '深蓝',
             'GRAY': '灰', 'GOLD': '金', 'RED': '红'}

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
# ⚠️ 这里**没有** granularity / total_col / weight_col。它们曾经是 `ttm_yoy`（今名
# `level_yoy`）用来把日均列还原成当月合计、好滚 12 个月的；mix 的合计柱次轴是
# **单月同比**（当月对去年同月，本列除本列），一步还原都不需要。2026-09 从 MIX_KEYS
# 里删掉的时候三处一起删了；同年 `level_yoy` 也改成单月口径，那三个字段就此在本文件
# 里绝迹 —— 留着就是死配置，而死配置会让下一个人以为这张图做过什么它其实没做的事。
# `abs_stack`（2026-09 补）把这一组从「两张」改成**一张**：不出合计柱、也不出 100%
# 占比堆叠，只出一张**绝对值**堆叠柱（一个月一根柱，柱高 = 合计，段 = 各分项）。
# 它与 `rhs_share` / `share_note` 互斥 —— 那两个键只有 100% 占比那张读得到，
# 开了 abs_stack 还写它们就是死配置（本文件删掉 granularity / total_col / weight_col
# 时记过同一条账：死配置会让下一个人以为这张图做过什么它其实没做的事）。
MIX_KEYS = {'total', 'parts', 'residual_zh', 'rhs_share', 'note', 'share_note',
            'abs_stack'}
MIX_REQUIRED = {'total', 'parts'}

#: 页尾断点那段里，「这一图型本身不挂断点线」那一档要报的**图型中文名**。
#: 判据不在这里 —— 是不是这一档由构建期的事实账 `Page._brk_asked` 说了算
#: （`mark_breaks()` 记）；这张表只负责把 kind 翻成读者认得的词，查不到就原样印 kind，
#: 于是新增一个不调 `mark_breaks` 的图型时页面顶多措辞硬一点，不会印出一句假理由。
BRK_NODRAW_ZH = {'bridge_bar': '量价分解', 'heat_matrix': '热力矩阵'}

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

# ── 量价分解（decomp）───────────────────────────────────────────────────
# 前提：**「日均」列不能直接跨月相加**。各月立会日数在 18–23 天之间浮动，直接相加等于
# 给每个月同样的权重，年度均价 Σ金额/Σ股数 就用错了权重。所以这个字段提供
# `*_total_col`（源表自带的当月合计列）与 `weight_col`（把日均 × 立会日数还原）
# 两条路，两条都给时底座**互相对账**（见 `Page.monthly_total`）。
#
# ⚠️ `level_yoy`（旧名 `ttm_yoy`）曾经也共用这个前提 —— 它要把日均列还原成当月合计
# 才滚得动 12 个月。2026-09 全站同比改成单月口径之后，那张图的次轴变成「本列除本列」，
# 一步还原都不需要，于是它的 granularity / total_col / weight_col 三个字段一起删了。
DECOMP_KEYS = {'zh', 'kind', 'granularity', 'value', 'qty',
               'value_total_col', 'qty_total_col', 'weight_col',
               'price_zh', 'price_unit', 'price_fmt', 'price_scale',
               'bench_value', 'bench_qty', 'share_zh', 'mix_zh',
               'year_start_month', 'year_label', 'years', 'note', 'section',
               # ── 以下两个 2026-09 新增，**纯加法**：不写就与从前逐字节相同 ──
               # 'bucket'：横轴一格是什么。缺省 'year'（一格 = 一个完整年度，
               #   最新年不满 12 个月时末格追加 YTD），另一个合法值 'monthly'
               #   （一格 = 一个月，基期去年同月 = 单月同比）。
               # 'after_group'：把这张图**就地**排在某个 group 的图之后（见 payload）。
               'bucket', 'after_group'}
DECOMP_REQUIRED = {'zh', 'kind', 'granularity', 'value', 'qty',
                   'price_zh', 'price_unit', 'price_fmt'}
#: `bucket` 的白名单。做成白名单而不是 `!= 'monthly' 就当年度`：拼错一个字母
#: （'month' / 'Monthly'）会静默掉回年度桶，画出来是一张**完全合法**的年度图，
#: 没有任何自动判据看得出所有者要的是月度。
DECOMP_BUCKETS = ('year', 'monthly')
#: 月度桶下**必须不出现**的三个年度键。判据用 `k in d`（原始 dict），不是归一化结果 ——
#: 归一化带缺省，读到的永远是 1 / 'start' / 5，分不出「没写」与「写了个缺省值」。
#: 理由同 LEVEL_YOY 那次删键：留着一个再也不起作用的声明，比当场报错糟 ——
#: 它会让下一个人以为月度图的横轴还受 year_start_month 管。
DECOMP_YEAR_ONLY_KEYS = ('year_start_month', 'year_label', 'years')
# ── level_yoy —— 「水平值柱 + 次轴单月同比」那几张（一律排在页尾）─────────────
# 旧名 `ttm_yoy`：次轴曾是 12 个月滚动合计的同比。2026-09 按页面所有者的指令改成
# **单月同比**（当月对去年同月，本列除本列），键名、函数名与标题一并跟着改 ——
# 留着 `ttm_yoy` 这个名字，就是让配置替一张不再做滚动合计的图署名。
LEVEL_YOY_KEYS = {'zh', 'level', 'note', 'section'}
LEVEL_YOY_REQUIRED = {'zh', 'level'}

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
#: 「交叉项占净增长百分之多少」这个比例的**分母下限**：|g_V| 低于它就不算占比。
#: 年度桶只有 5 根柱、几乎撞不上；月度桶一格一个月，128 格里净增长近零的格子成片出现
#: （ASX 实测 116 格里有 26 格），沿用年度版那个「交叉项 ÷ 净增长」会印出几百个
#: 百分点的假占比 —— 大的不是交叉项，是分母小。所以占比只在 |g_V| ≥ 它的格上算，
#: 交叉项本身一律另印 pp（绝对值中位与最大），两者并列给读者。
DECOMP_NEAR0_G = 0.05
#: 月度分解图注里「中蓝段」那句交叉引用的**占位符**。`_decomp_monthly` 先埋、
#: 全页图建完之后由 `Page._pleg_fill()` 换成真话（那句话是页面级超级式，
#: 图建到一半时算不出来 —— 理由见 `_pleg_fill` 的 docstring）。
#: ⚠️ 用控制字符是故意的：万一哪天有一条回填路径漏掉，它**不能悄悄上页**。
#: `payload()` 里那道硬护栏见到它还在就当场 raise，页面宁可不出。
PLEG_MARK = '\x01PLEG\x01'
TOTAL_TOL = 1e-6         # 「日均 × 权重」与「当月合计列」的一致性容差（见 monthly_total）
TTM_WIN = 12             # 滚动合计窗口（个月）—— 现在只用来**对照**，页上不画

# 同比口径账本认的类别（页尾「同比口径」条目按类各写一段点名文案，见 notes()）：
#   mom     = 单月同比（当月对去年同月）—— 头条同比图、gs_bar 次轴、level_yoy 次轴
#   mom_pp  = 比率列的单月同比（百分点差 —— 比率不做滚动，CONTRACT §6.1 第 4 条）
#   stock   = 存量列的点对点同比（存量不可加总，CONTRACT §6.1 第 2 条）
#   heat    = 热力矩阵（格内是单月同比，量列 → 百分比变化）
#   heat_pp = 热力矩阵，但整组都是比率列（格内是单月同比的**百分点差**，§6.1 第 4 条）
# ⚠️ **`'ttm'` 已从白名单里删掉**：2026-09 按页面所有者的指令，本底座产出的同比
# 一条不剩全是单月口径，页上再没有 12 个月滚动合计的同比。留着这个类别的代价不是
# 一行死代码，是页尾会保留一段「本页并存两种口径」的分支 —— 哪天有人误传 'ttm'，
# 页面会印出一段指着不存在的滚动折线的话。现在误传直接硬失败。
# 做成白名单是因为拼错的类别只会静默丢一段点名文案，页面照常上线没人发现，
# 所以 log_yoy 对不认识的名字硬失败。
YOY_CALS = ('mom', 'mom_pp', 'mom_money', 'stock', 'heat', 'heat_pp', 'heat_money')


class SpecError(SystemExit):
    """spec 写错 / CSV 结构不对 —— 要人去改，退出码 1。

    与「门槛没到」严格区分：后者是等数据，退出码 0（见 Page.payload 的注释）。
    """


# ══════════════════════════════ 通用零件 ══════════════════════════════
def mlab(p):
    """Period('2026-06') → 'Jun-26'（与 gsx.mlab / 既有 12 家一致）。"""
    return p.strftime('%b-%y')


def through_gap(latest, newest):
    """副标题与页注里那半句「；数据月止于 X」。两者相等时返回空串。

    ⚠ 措辞别改成「头条口径止于 X」：本仓的「口径」一律指**测量基准**
    （「IR 月报口径」「Nordic + Baltic 口径」，exchanges_apac.py 里还有
    「分解口径 vs 头条口径」的同比对照），拿它表示时间边界是给一个高频词
    加第二种意思。「数据月」才是本仓对 data_through 的既有叫法
    （见汇总表的组标题「头条指标（决定本页数据月）」与核对表那条
    「表尾若有月份晚于本页数据月 X」——本文件里都能 grep 到）。

    `newest` 是整表最后一行的月份，`latest` 是 data_through（头条列共同最新月）。
    有「发布更快的腿」的页面上两者会差一期 —— 那些更晚的月份是真的印出来的
    （核对表多一行、快腿各列的图各自多画一根柱），所以「覆盖 … newest」没写错；
    但它与抬头的「数据截至 latest」并排出现时，单看任何一句都读不出另一句的存在。
    ndaq 2026-09 就是这样：抬头「2026 年 7 月」、副标题「覆盖 Sep-05 – Aug-26」，
    两行之间没有任何一个字解释这一个月的落差是从哪来的。
    ⇒ 只在有落差时补这半句；没落差的页（绝大多数）一个字都不变。
    """
    return f'；数据月止于 {mlab(latest)}' if newest != latest else ''


_MLAB_MON = {m: i + 1 for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
     'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])}


def _mlab_ord(lab):
    """'Jun-26' → 月序号（用来判相邻）。认不出返回 None。"""
    try:
        mon, yy = str(lab).split('-')
        return (2000 + int(yy)) * 12 + _MLAB_MON[mon]
    except Exception:
        return None


def _month_runs_zh(labs, cap=24):
    """一串横轴月标签 → 'Jan-16 至 Dec-18、Mar-21' 这种压缩写法。

    近零基数月常常成段出现（一条序列刚起步的头两年），逐月列出来是几十个标签、
    读者一个都记不住；压成区间才看得出「是哪一段」。**只压真正连续的月份**，
    中间断开就另起一段 —— 把不连续的写成区间会让读者以为中间那些月也命中了。
    段数超过 `cap` 时只列前 `cap` 段并说清楚还剩几段，不静默截断。
    """
    labs = [str(x) for x in labs]
    if not labs:
        return ''
    runs, cur = [], [labs[0], labs[0]]
    prev = _mlab_ord(labs[0])
    for x in labs[1:]:
        o = _mlab_ord(x)
        if prev is not None and o == prev + 1:
            cur[1] = x
        else:
            runs.append(tuple(cur))
            cur = [x, x]
        prev = o
    runs.append(tuple(cur))
    bits = [a if a == b else f'{a} 至 {b}' for a, b in runs[:cap]]
    more = len(runs) - cap
    return '、'.join(bits) + (f'，另有 {more} 段' if more > 0 else '')


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

    ⚠️ 判据走 `col_is_ratio()`，**不是** `c['fmt'] in RATIO_FMT`（2026-09 改）——
    从前这里与 `Page.is_ratio()` 各写了一遍同一句 fmt 判断，图的次轴按一套走、
    图注里这句「同比 X」按另一套走的隐患一直在；现在两处同源。
    差额小于 1pp 时改印 bp，理由与 §2 汇总表那一行逐字相同：份额从 19.1% 掉到 19.0%
    写成「-0.0pp」读起来像没动，写成「-10bp」才是那件事。
    ⚠️ **分子是钱的比率不走 pp/bp**：`USD/contract` 的差还是 `USD/contract`
    （见 `unit_is_money_ratio`）。分派在 `ratio_diff_txt()` 里做，本函数只转发 ——
    汇总表的 `cell()` 走的是同一份实现。
    """
    a = np.asarray(v, float)
    if len(a) <= lag:
        return '—'
    if col_is_ratio(c):
        d = a[-1] - a[-1 - lag]
        return ratio_diff_txt(d, c) if np.isfinite(d) else '—'
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


# ── bp 读数的位数：按量级取，不是一律取整 ──────────────────────────────────
# 2026-09 之前 bp 一律 `:+.0f`。那一档把两类读数一起毁掉：
#
#   ① **非零的差被抹成「0bp」**：|差| < 0.5bp 的每一个读数都印 0bp，
#      与真正的零（同一张表里也有）在页面上一模一样。当时实测被抹平的两处是
#      ice Exhibit 15 现货 RPC 的环比 0.001、miax Exhibit 9 多挂牌期权 RPC 的
#      环比 0.004。
#      ⚠️ **这两处今天已经不走 bp 了**：它们是**美元量纲**的比率（USD/100 shares、
#      USD/contract），差出来的仍然是钱不是百分点，2026-09 改由 `money_diff_txt()`
#      印成「+0.001 USD/100 shares」（判据见 `unit_is_money_ratio`）。
#      举它们只是为了说清 `:+.0f` 那一档毁掉的是什么 —— 位数这条规矩对**真正的
#      百分点比率**（份额、逾期率那些）一字未变，下面 `_bp_dec` 仍然只服务它们。
#   ② **整 bp 分不开时，四舍五入不稳**：本机实测
#      `0.041 - 0.036 = 0.0050000000000000044` → `:+.0f` 进位印「+1bp」，
#      而同为 0.005 的 `0.040 - 0.035 = 0.0049999999999999975` → 印「0bp」。
#      同一个真值 0.005pp，浮点残差落在哪一侧决定读者看到 +1bp 还是 0bp。
#
# 所以位数按**量级**取（下面 `_bp_dec`），而不是按四舍五入之后是不是零来取：
# 后者仍然要在 0.5bp 那个点上做一次「进位还是舍去」的判断，不稳的还是不稳。
# 量级取位之后 0.5bp 的两种浮点写法都落在 1 位小数这一档，都印「+0.5bp」。
#
# ⚠️ 只改**格式化**，payload 里的数值一格没动 —— `tools/check_yoy_caliber.py`
# 的回源复算认的是 `values` 里的数，动数值等于拿判据的失明换可读性。
BP_DEC_MAX = 2      # bp 最多给 2 位小数（0.01bp = 1e-4 pp），再细的差按「≈0bp」印


def _bp_dec(bp):
    """一个 bp 读数要几位小数，第一位有效数字才露得出来（上限 `BP_DEC_MAX`）。

    ⚠️ 先把值**量化到展示分辨率**再看量级，不是直接看原值 —— 否则浮点残差会把
    读数推错一档：本机实测 `(2.20 - 2.21) * 100 = -0.9999999999999787`
    （= −0.9999…bp；这两个数取自 `series/ice.csv` 的 `rpc_ag_metals_usd`
    2026-07 与 2025-07），直接按原值取档会掉进 1 位小数那一档，
    把「-1bp」印成「-1.0bp」。

    ⚠️ **上一版这里把同一个残差挂在 `0.04 - 0.05` 名下，那个例子是编的，留痕在此**：
    Python 里 `0.04 - 0.05 = -0.010000000000000002`，×100 = −1.0000000000000002，
    残差落在 1 的**另一侧** —— 按原值取档同样得 0 位小数，整段演示不出它要演示的
    那件事。残差值本身是真的，只是来处写错了（同一批 RPC 列里另一条）。
    """
    a = abs(round(bp, BP_DEC_MAX))
    dec = 0
    while dec < BP_DEC_MAX and a < 10.0 ** -dec:
        dec += 1
    return dec


def _bp_txt(bp, signed=True):
    """bp 读数 → 展示串。全站 bp 只由这里印，`ppbp` / `ppbp_abs` / 汇总表都走它。

    真零印「0bp」（没有方向，不带正负号）。位数封顶之后仍然印成零的，
    印「≈0bp」而不是「0bp」—— 它比 0.01bp 还小，但它不是零，两者在页面上要分得开。
    """
    if bp == 0:
        return '0bp'
    dec = _bp_dec(bp)
    txt = f'{bp:+.{dec}f}bp' if signed else f'{abs(bp):.{dec}f}bp'
    return '≈0bp' if float(txt[:-2]) == 0 else txt


def ppbp(v):
    """百分点差（入参单位 pp）→ '+40bp' / '+0.5bp' / '+2.53pp'。

    |v| < 1pp 走 bp，与 §2 汇总表那一行同一条判据 —— 现在是**同一份实现**：
    `summary()` 的 `cell()` 调的就是下面这个 `_bp_txt`，不再各印各的。
    不这么分档的话，0.4 个百分点会印成 '+0.4pp'，读者要数小数点位数才知道有多小。
    （底座之外还有几份手写生成器也在印 pp/bp，例如 `build/hkex.py`；
    它们不 import 本文件，本轮也没有动它们。）
    """
    if v is None or not np.isfinite(v):
        return '—'
    return f'{v:+.2f}pp' if abs(v) >= 1 else _bp_txt(v * 100)


def ppbp_abs(v):
    """同 ppbp，但用于**幅度**，不带正负号。

    入参本来就该是非负的（两处调用点给的都是 `max(abs(…))`），两个分支一律再取一次
    绝对值只是让函数与它的名字一致 —— 从前 pp 那一支是直接 `f'{v:.2f}pp'`，
    真收到负数会印出一个带负号的「幅度」。
    """
    if v is None or not np.isfinite(v):
        return '—'
    return f'{abs(v):.2f}pp' if abs(v) >= 1 else _bp_txt(v * 100, signed=False)


#: 「钱的差」最多在该列自己的小数位上再多给几位（见 `money_diff_txt`）。
MONEY_DIFF_EXTRA_DEC = 2


def money_diff_txt(d, c):
    """**分子是钱**的比率的同比／环比差 → '-0.01 USD/contract'。见 `unit_is_money_ratio`。

    位数从**这一列自己的 `fmt`** 起（CONTRACT §5 那条「小数位一律等于官方发的位数」）：
    两个各带 k 位小数的数相减，差在 k 位上就是准确的，不必也不该多印。
    只有一种情况往下补位 —— 差不是零、却在 k 位上四舍五入成零。那种读数与真正的零
    在页面上一模一样，正是 `_bp_dec` 上方那段记着的同一个毛病，这里照它的办法处理：
    补到第一位有效数字露出来为止，最多再补 `MONEY_DIFF_EXTRA_DEC` 位；仍然是零
    就印「≈0」，与「0」分得开。

    单位**原样引用 spec 里的 `unit`**，不在这里翻译成「每张」「每 100 股」——
    轴标题、核对表表头与这里必须是同一串字，翻译一次就多一处会漂的副本。
    """
    if d is None or not np.isfinite(d):
        return '—'
    u = (c.get('unit') or '').strip()
    dec = FMT_INFO[c['fmt']][0]
    if d == 0:
        return f'0 {u}'.strip()
    cap = dec + MONEY_DIFF_EXTRA_DEC
    while dec < cap and round(abs(d), dec) == 0:
        dec += 1
    body = f'{d:+.{dec}f}'
    if float(body) == 0:
        body = '≈0'          # 补到位数上限仍然印成零：它不是零，两者要分得开
    return f'{body} {u}'.strip()


def ratio_diff_txt(d, c):
    """一个比率列的差该怎么印：钱走 `money_diff_txt`，百分点走 `ppbp`。

    全底座**只有这一处**做这个分派 —— `chg_txt()` 与汇总表的 `cell()` 都调它。
    两处各写一遍的下场是同一张页上图注说「-0.01 USD/contract」、汇总表说「-1bp」。
    只做带符号的那一档：本底座里比率的差全是**方向性**读数（同比／环比），
    没有「幅度」那种用法（`ppbp_abs` 那一路服务的是量价分解的贡献差，不按列走）。
    """
    if col_is_money_ratio(c):
        return money_diff_txt(d, c)
    if d is None or not np.isfinite(d):
        return '—'
    return ppbp(d)


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


def yoy_line(s_full, win, pct_series=False):
    """逐月同比序列（%），窗口对齐到 win，供次轴 y/y 折线与同比柱用。

    **算术一律转发 `build/yoy.py` 的 `mom_yoy()`**（CONTRACT §6.4：同比只有一份实现）。
    2026-09 之前本函数自己写了一遍 `a − b` 与 `(a / b − 1) × 100`，于是页面上每一条
    同比线走的其实是这份副本、不是 `yoy.mom_yoy()`。两边当时算出来的数逐点一样，
    但「一样」没有任何东西在守着：改一边不报错，副本会静默漂走。

    转发之后本函数只剩两件 `mom_yoy()` 不做的事：

      · **近零基数掩码** —— 基期 |b| < 本序列 |值| 中位数 × `ycal.NEAR_ZERO_BASE_FRAC`
        的月份写 null（小基数会把同比放大成几百个百分点）。阈值取自 yoy.py 的常量，
        本文件不另立一个数。这一层**没有**并进 `mom_yoy()` 是刻意的：`mom_yoy()` 是
        算术，而 `yoy.near_zero_base()` 是对**整条序列**下判断（「这条线该不该画」，
        返回一个统计 dict），两者问的不是同一个问题。比率序列（`pct_series=True`）
        不掩码 —— 百分点差没有分母，小基数放大不了它。
      · **窗口对齐** —— 同比在切窗口之前算；切完再算的话，窗口最前面 12 期永远没有同比。

    「基期为 0」与「两期异号」这两条放弃条件现在由 `mom_yoy()` 里那一行 mask 承担，
    本函数不再重写一遍。放弃的期写 null：引擎不替这一步做判断，图上断开、
    表格视图里是「—」。

    `pct_series` 只区分「比率 / 非比率」，因为 `mom_yoy()` 的 FLOW 与 STOCK 两支是
    **同一个算术**（都是点对点 `a / b − 1`），只有 RATIO 那支改成百分点差；
    调用点手上有没有 `stock` 标志，对这里算出来的数没有影响。

    ⚠️ 原来的 `lag=12` 参数 2026-09 删掉了：跨度现在是 yoy.py 的模块常量 `LAG`，
    再留一个自己的 lag 只会造出「传了 lag=1 却仍然按 12 个月算」的静默错。
    三处调用点原本就都在吃默认值。
    """
    out = ycal.mom_yoy(s_full, ycal.RATIO if pct_series else ycal.FLOW)
    if not pct_series:
        v = pd.to_numeric(pd.Series(s_full), errors='coerce').astype(float)
        scale = float(np.nanmedian(np.abs(v.values))) if len(v) else 1.0
        scale = scale if (scale and np.isfinite(scale)) else 1.0
        out = out.mask(v.shift(ycal.LAG).abs() < scale * ycal.NEAR_ZERO_BASE_FRAC)
    return out.reindex(win).values


def yoy_rhs(s_full, win, pct_series=False, diff_unit=None):
    """gs_bar 的次轴 y/y 字段（给了它引擎就画同比折线、不画 12 个月均线）。

    **整条同比都算不出来时返回 None**：引擎只看 `ex.yoy` 在不在就判 dual，
    值全是 null 时 `Math.max.apply(null, [])` = −Infinity，量程退化成 [0, 1]，
    于是右边印出一列「0% 0% 0% 1% 1% 1%」的假刻度，而那条金线一个点都没画
    （实测 enx Ex30 电力衍生品 OI、sgx Ex17 加密永续 —— 两条序列都只有几个月历史，
    窗口内没有任何一对可比的同月）。宁可不要次轴。

    `diff_unit`：比率列的差**不是百分点**时，把那个单位串传进来（今天只有
    「分子是钱」这一类，见 `unit_is_money_ratio`）。它只改序列名与刻度族 ——
    `values` 一格不动，仍是 `yoy.mom_yoy(s, RATIO)` 的差。序列名要写对，
    是因为 `tools/check_yoy_caliber.py` 的 R4 认的四处里有 `yoy.name`，
    而读者手上只有这四处能知道右边那条线的单位。
    """
    v = LN(yoy_line(s_full, win, pct_series))
    if not any(x is not None for x in v):
        return None
    if pct_series and diff_unit:
        # 钱的差：`pp` 族印出来就是假单位，一律用纯数字族，单位交给 ylab2 与图注
        # （与 `pp_yfmt()` 换族那一支同一条理由，只是这里连 pp0 都不能要）。
        name, yfmt = f'y/y ({diff_unit}, RHS)', 'f0'
    elif pct_series:
        name, yfmt = 'y/y (pp, RHS)', pp_yfmt(v)
    else:
        name, yfmt = 'y/y (RHS)', 'pct0'
    return {'name': name, 'color': 'GOLD', 'yfmt': yfmt, 'values': v}


def rhs_ylab2(c, mom=False):
    """次轴标题（`ylab2`）。三档：非比率 `% y/y`、百分点比率 `pp y/y`、
    **分子是钱**的比率 `<unit>, y/y 差`（见 `unit_is_money_ratio`）。

    `mom=True` 时追加「（单月）」—— `tools/check_yoy_caliber.py` 的 R4 只认
    title / ylab2 / legend / yoy.name 四处，走这一档的路径（头条柱图、level_yoy）
    靠 ylab2 把「单月」写进去。比率列的 R4 由 `legal_mom` 豁免，所以不带这个尾巴。
    """
    tag = '（单月）' if mom else ''
    if col_is_money_ratio(c):
        return f'{c["unit"]}, y/y 差{tag}'
    return ('pp y/y' if col_is_ratio(c) else '% y/y') + tag


def yoy_diff_word(c):
    """图注里指代「这条同比线的量纲」的那半个词，与 `rhs_ylab2` 同一套判据。"""
    if col_is_money_ratio(c):
        return f'{c["unit"]} 的差'
    return '百分点差' if col_is_ratio(c) else '%'


def pp_yfmt(values):
    """百分点差那条线的右轴格式器：`pp` 族印不出来的量级改用纯数字刻度。

    `assets/charts.js` 的 FMT 表里 `pp` 族只有 **pp0 / pp1** 两档，而比率列的
    百分点差量级常常在 0.01–0.05pp（ICE 的 NYSE 期权 RPC 一年动 1–6 个基点、
    MIAX 多挂牌期权 RPC 动 0.7 个基点）——整列右轴刻度会被 pp1 印成
    「0.0pp 0.0pp 0.0pp」，相邻两条网格线同一个数字。那正是 `build/axisfmt.py`
    模块头点名要消灭的那种轴，但它**只能在同族内升位**，到 pp1 就顶格、
    然后**静默**放弃（`_bump()` 同族没有更高位数就原样返回）。

    所以这里在生成端换族：刻度顶不住时用纯数字族 `f0`（axisfmt 随后会按真实刻度
    升到 f1/f2/f3 够用的位数），单位由右轴标题 `ylab2`（「pp y/y」）与图注承担 ——
    与左轴「数字 + 轴标题给单位」的读法一致，不是把单位丢了。
    判据不是拍脑袋的阈值，是把引擎的刻度算法（`axisfmt.ticks`，逐行等价于
    `charts.js` 的 `ticks()`）先跑一遍，看 1 位小数够不够把刻度标签区分开。

    量程要**跟引擎一样只把 0 折进下界**：右轴是
    `ticks(min(rv.concat([0])), max(rv), 9)`（`charts.js:1005`，`zero_base` 默认开、
    `yoy_rhs()` 从不关它），并排柱是 `y0 = min(0, mn*1.15); y1 = mx*1.22`
    （`charts.js:926`）—— 两处上界都不含 0。从前这里上下界都塞了 0，整列同号的
    序列就被模型化成一条跨零的轴：miax Ex12（Pearl 份额同比全负，真值
    −0.5…−0.1pp）被算成 [−0.5, 0] step 0.1「1 位够用」，引擎实际画的是
    [−0.5, −0.1] step 0.05，于是右轴印出「−0.2pp −0.2pp」「−0.5pp −0.5pp」，
    相邻刻度同一个数、像素-数值比也不再等距。判错的是量程，不是位数。
    """
    fin = [float(x) for x in values if x is not None and np.isfinite(x)]
    if not fin:
        return 'pp0'
    tk = axisfmt.ticks(min(fin + [0.0]), max(fin), 9)
    labs = [f'{t:.1f}' for t in tk]
    return 'pp0' if len(set(labs)) == len(labs) else 'f0'


def prior12(v):
    """`gs_bar` 那条「Prior 12mo Avg.」虚线的值：**最新月之前**的 12 个月均值。

    切片口径 `[-13:-1]` 抄的是仓里已有的三处同一实现（`build/cboe.py` 的 `prior12`、
    `build/axp.py` 的 `gs_bar_ex(no_yoy=True)`、`build/lpla.py` 的 `avg_prior12`）——
    行为上最接近的是 lpla 那个（同样 round 到 6 位、全 NaN 时不返回数）。
    四处取不同的切片等于同一条虚线有四种含义，那是这个仓库反复治的病。
    """
    a = np.asarray(v, float)[-13:-1]
    if not np.isfinite(a).any():
        return None
    return round(float(np.nanmean(a)), 6)


def no_yoy_off_zh(c, avg12):
    """spec 用 `no_yoy` 关掉次轴同比时，图注里替代 `NO_YOY_NOTE` 的那半句。

    ⚠️ **不能复用 `NO_YOY_NOTE`**：那一段断言的是「窗口内没有任何一对可比的同月
    （序列历史短于 12 个月）」，而走到这里的列历史长得很 —— 那句话在这张图上是假的。
    这里只说底座自己证得出的两件事：同比是 spec 关掉的、虚线画的是哪个数。
    """
    return ('本图<b>不画次轴同比</b>：spec 对这一列声明了 <code>no_yoy</code>，'
            '次轴那条金线连同它的右轴一并撤掉。'
            + ('深蓝虚线 = <b>最新月之前 12 个月的均值</b>，回答「当前 vs 过去一年常态」；'
               '柱与虚线同一根轴，可以直接比高低。'
               if avg12 is not None else
               '窗口末尾 12 个月一个有效值都没有，均线也画不出来，'
               '所以这张退回 <code>bars_labeled</code>（深蓝柱 + 每柱数值）。')
            + '<b>最新一个月的同比仍在紧接着的那句话里</b>（逐月现算），只是不再画成一条线。')


NO_YOY_NOTE = ('窗口内没有任何一对可比的同月（序列历史短于 12 个月），故不画次轴同比；'
               '也没有 12 个月均线可画，所以这张用的是 <code>bars_labeled</code>（深蓝柱 + 每柱数值），'
               '与本页其余 <code>gs_bar</code>（浅蓝柱 + 金色同比）不同色是刻意的。')


# ════════════════ 图注里的口径断言：互斥对自检 ════════════════
# 底座已经被抓到**两次**在图注里无条件印出关于口径的断言，而那断言对某些页是假的：
#   ① decomp 的「本身即当月合计口径，未做还原」印在了日均列上；
#   ② ttm_yoy（今 level_yoy）的「柱是日均，已除过交易日数」印在了月合计列上，
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


# ════════════ 标题里的「YYYY-MM 起」与图窗左端对不上 ════════════
# 组名里那半句「（2002-01 起）」是本仓的通行写法，说的是**这一列数据从哪个月起有**
# （tmx 的 `_since()`、ndaq / miax 的组名都这么写，而且都从 CSV 现算）。
# 但图窗左端由底座定（`WIN_FROM` = 2016-01），两者一撞，标题上就出现一个
# 图上根本找不到的月份：tmx「MX 衍生品 ADV（2002-01 起）」那组的图，组名写着
# 「2002-01 起」、图注里的横轴却从 2016-01 开始（**按内容点名、不写图号** ——
# 图号会随增删图整体位移，写死一次就要错一次）。
# 读者没有线索判断这是漏画了十几年还是标题在说别的事。
#
# 根因在两侧各一半：月份由 spec 给、窗口由底座定。底座这一侧能做的是**把关系说破**，
# 而且只在真撞上时说 —— 判据是「标题里出现的年月早于本图横轴左端」，
# 一个字都不写死，spec 改了组名或数据回补到更早，这句话自己跟着变或消失。
_TITLE_YM = re.compile(r'(\d{4})-(\d{2})')


def title_since_zh(ex):
    """标题里印着一个比本图横轴左端更早的年月 → 一句把两者关系说破的话；否则 ''。

    只断言底座**自己知道**的事：这张图画的是 xlabels[0] → xlabels[-1]，
    所以标题里那个更早的月份说的不是「这张图从哪个月画起」。
    标题那半句到底在说什么（数据从哪个月起有、还是口径从哪个月换代）由 spec 作者写，
    这里不替它下定义。
    """
    xl = ex.get('xlabels') or []
    title = str(ex.get('title') or '')
    if len(xl) < 2:
        return ''
    try:
        # mlab() 就是 strftime('%b-%y')，同一进程里 strptime 是它的逆
        lo = datetime.datetime.strptime(xl[0], '%b-%y')
    except ValueError:
        return ''   # 横轴不是月份标签（qtr_bar / bridge_bar / seasonality 的年标签）
    hit = [f'{y}-{m}' for y, m in _TITLE_YM.findall(title)
           if (int(y), int(m)) < (lo.year, lo.month)]
    if not hit:
        return ''
    at_win_from = (lo.year, lo.month) == tuple(int(x) for x in WIN_FROM.split('-'))
    return (f'<b>标题里的 {"、".join(dict.fromkeys(hit))} 早于本图横轴的左端</b>'
            f'（本图画的是 {xl[0]} → {xl[-1]}，共 {len(xl)} 期）—— 那半句说的不是'
            f'这张图从哪个月画起。'
            + (f'本图左端是全站时序图统一的左界 {WIN_FROM}：各页的历史长度差着一个'
               f'数量级，左界不统一的话同一个指标在不同页上起点不同，跨页比不出高低。'
               if at_win_from else ''))


def _span_vs_win(win):
    """开篇「全历史」图与本页其余时序图（左界 `WIN_FROM`）的长度关系 —— **三分支，不写死**。

    2026-09 之前这半句无条件印「比本页其余时序图（2016-01 起）长」。对 tmx 为真
    （头条列自 2002-01 起，比左界早 14 年），对 **asx 字面为假**：asx 的 series 首月
    就是 2016-01 = `WIN_FROM`，两个月份在同一句话里逐字相同，却断言一边比另一边长
    —— 而这是开篇图，是读者看到的第一段文字。没有任何护栏查得出这种错（payload
    结构完全正常），所以判据必须写在生成端。

    判据复用 `title_since_zh()` 里那条（首月 == WIN_FROM）的同一套比较。
    第三支（首月**晚于** WIN_FROM）今天全仓没有页面命中，但留着：那种情形下原句
    是反向假，而「这一列比别的图短」恰恰是读者最该被告知的事（左边那段是披露史）。
    """
    lo = pd.Period(WIN_FROM, freq='M')
    if win[0] < lo:
        return f'比本页其余时序图（{mlab(lo)} 起）长。'
    if win[0] == lo:
        # ⚠️ 这一支**不许说「与其余各图一样长」**。左界相同 ≠ 长度相同：同一页上
        # 任何一条自己起点更晚的列（辅源天花板、官方后来才加的行）画出来就更短，
        # 而那种图上「同一个横轴下标」根本不是同一个月。2026-09 校验实测：
        # asx 页 37 张里有 5 张不与本图等长，其中一张的左端整整晚了 4 年半。
        # 只断言「左界」这一件能证明的事，长度那半句由各图自己的窗口说明去讲。
        return (f'左端与本页其余时序图<b>同一个左界</b>（{mlab(lo)}）—— 本列的首个有值月'
                f'正好就是全站时序图统一的左界，所以这张「全历史」并不比它们更靠左；'
                f'「全历史」说的是右端画到本列自己的末月，不是左端更早。'
                f'（本页另有几张图起点更晚 —— 那是各自那一列的披露史，'
                f'与本图不等长，别按横轴下标去对读它们。）')
    return (f'比本页其余时序图（{mlab(lo)} 起）<b>短</b>：这一列 {mlab(win[0])} 才'
            f'开始有值，左边那段空白是披露史，不是数据缺失。')


def caliber_audit(exhibits):
    """扫全部图注，撞上互斥口径断言就返回 [(n, 说明), …]。空列表 = 干净。"""
    out = []
    for ex in exhibits or []:
        note = (ex or {}).get('note') or ''
        for pa, pb, why in _CALIBER_CONFLICTS:
            if re.search(pa, note) and re.search(pb, note):
                out.append((ex.get('n'), why))
    return out


def bar_ex(n, title, c, xl, v, rhs, *, ylab2, avg12=None):
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
    # `no_yoy` 关掉同比、而 12 个月均线算得出来时走这一支：仍是 gs_bar（浅蓝柱），
    # 只是把金色同比线换成深蓝虚线的均值。**不写 ylab2** —— gs_bar 的双轴由
    # `!!rhsOf(ex)` 决定（assets/charts.js），右轴整根不画，留个 ylab2 就是给一根
    # 不存在的轴写标题。
    if avg12 is not None:
        return {
            'n': n, 'kind': 'gs_bar', 'fmt': c['fmt'], 'xlabels': xl,
            'title': title, 'ylab': c['unit'],
            'legend': c['zh'], 'values': LN(v), 'avg12': avg12, '_cols': [c['col']],
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


# ══════════════ 引擎几何的 Python 复刻（只给 `spike_cap()` 用）══════════════
# `spike_cap()` 的端点护栏与图注都要报像素数，而像素数只有 `assets/charts.js` 说了算。
# 这里把要用的那几行逐行搬过来、并在每一项后面写上对照行号 —— **不是**在这里另立一套
# 常数：引擎改一行，这里必须跟着改一行，行号就是给下一个人对账用的。
#
# ⚠️ 这里没有「FS = 1」这一档。引擎的字号是按卡片宽度在 [FS_MIN, FS_MAX] 之间插值的
#（`charts.js:126`），**下界就是 1.45**；`FS = 1` 只是 `fscale()` 的退化写法，
# 全站没有任何一张图画在那一档上。图注里报 FS=1 的像素数，报的是一根不存在的轴。
FS_MIN, FS_MAX = 1.45, 1.70          # charts.js:126


def _js_round(x):
    """JS 的 `Math.round`（半数一律向上）。Python 的 `round()` 是半数向偶，两者在
    `26×(FS−1) = 17.5` 这一档上正好差 1px —— 而那一档恰是 ph 的极小值所在。"""
    return math.floor(x + 0.5)


def _fscale(v, fs):
    return _js_round(v * fs * 100) / 100                      # charts.js:133


def _plot_h(kind, fs, capped=True, height=None):
    """这张图的绘图区高 `ph`。charts.js:783（H）+ :814（M.t）+ :823（ph）。

    `M.b == XB`，而 `H` 里也加了同一个 `XB`，一加一减正好抵消 —— 所以 ph 与
    `xrot` / x 标签长短无关，只跟字号档位 `FS`、`ex.height` 与截轴开关有关。
    `perPointLabels`（charts.js:772）**不含 `lines`**：只有 `lines_endlabels`
    那一支才按 FS 补 `round(26×(FS−1))` 的高。
    """
    per = kind == 'lines_endlabels'
    h0 = height if height is not None else (268 if per else 248)
    return h0 + (_js_round(26 * (fs - 1)) if per else 0) - _fscale(30 if capped else 14, fs)


def _plot_h_min(kind, height=None):
    """`ph` 在 FS ∈ [FS_MIN, FS_MAX] 上的**最小值** —— 端点护栏取最保守的那一档。

    ph(FS) 在 `round(26×(FS−1))` 的每一级台阶内随 FS 单调下降（−30×ΔFS），
    所以极小值只可能出现在某级台阶的**右端**或 FS_MAX 上，逐个试完取小即可。
    实测：`lines_endlabels` 半栏 236.5 / 通栏 235.0，全区间极小 234.81（FS→1.6731⁻）。
    """
    cands = [_plot_h(kind, FS_MAX, True, height)]
    k = int(math.floor(26 * (FS_MIN - 1)))
    while True:
        fs = 1 + (k + 0.5) / 26
        if fs > FS_MAX:
            break
        if fs > FS_MIN:
            cands.append(_plot_h(kind, fs - 1e-9, True, height))
        k += 1
    return min(cands)


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
    # `ratio` 是**三态**：None（不声明，由 col_is_ratio 的 ②③ 两级推）、True、False。
    # 不给它 bool 兜底，否则「没写」与「写了 False」在下游长得一模一样，
    # 而后者的用途正是**否决**推导（见 col_is_ratio 的 ①）。
    ratio = c.get('ratio', None)
    if ratio is not None and not isinstance(ratio, bool):
        raise SpecError(f'{where} 的 ratio={ratio!r} 必须是 True / False，或者干脆不写'
                        f'（不写 = 交给底座按 fmt + yoy.classify() + unit 推，'
                        f'见 build/single.py 里 col_is_ratio 上方那段）')
    return {'col': c['col'], 'zh': c['zh'], 'unit': c['unit'], 'fmt': c['fmt'],
            'stock': bool(c.get('stock', False)), 'scale': scale, 'ratio': ratio,
            'no_yoy': _norm_flag(c.get('no_yoy'), f'{where}.no_yoy')}


def _norm_decomp(d, where):
    """一条量价分解配置 → 归一化 dict。

    恒等式 **金额 ≡ 数量 × 均价** 是定义式（均价 = 金额 ÷ 数量），没有任何假设，
    所以这张图唯一能出错的地方是**分子分母不同口径**：拿含 A 的金额除以不含 A 的数量，
    造出来的「均价」带着一个方向与大小都不可知的偏差，而图上完全看不出来。
    底座没法判断两列覆盖的是不是同一批标的（那是源表口径，只有写 spec 的人知道），
    所以这里只做机械校验，口径对齐由 spec 作者自己核实并写进 `note`。

    ── `bucket` 两支（2026-09 新增，缺省 'year' = 与从前逐字节相同）────────────
    `'year'`：横轴一格 = 一个完整年度，`year_start_month` / `year_label` / `years`
      三个键与它们那四条校验**逐字保留**。
    `'monthly'`：横轴一格 = 一个月、基期去年同月，那三个键**只要出现就 SpecError**
      （见 `DECOMP_YEAR_ONLY_KEYS`），归一化结果里一并置 None —— 月度分支哪天不小心
      读到它们，会当场 TypeError 而不是读到一个假缺省算出一张看着正常的图。
    与桶无关的那几条（price_fmt / price_scale / weight_col × granularity / kind /
    bench 成对）两支都跑。
    """
    if not isinstance(d, dict):
        raise SpecError(f'{where} 必须是 dict，收到 {type(d).__name__}')
    _check_keys(d, DECOMP_KEYS, DECOMP_REQUIRED, where)
    bucket = str(d.get('bucket', 'year'))
    if bucket not in DECOMP_BUCKETS:
        raise SpecError(
            f"{where} 的 bucket={d.get('bucket')!r} 不是 {DECOMP_BUCKETS} 之一 —— "
            f"'year' 是一格一个完整年度（末格可为当年 YTD），'monthly' 是一格一个月、"
            f'基期去年同月；拼错一个字母会静默掉回年度桶，画出来是一张完全合法的年度图，'
            f'没有任何自动判据看得出这不是要的那张')
    if bucket == 'monthly':
        # 判据是 `k in d`（**原始 dict**），不是归一化后的值：归一化带缺省，
        # 「没写」与「写了 year_start_month=1」在结果里长得一模一样。
        stray = [k for k in DECOMP_YEAR_ONLY_KEYS if k in d]
        if stray:
            raise SpecError(
                f"{where} 声明 bucket='monthly'（一格 = 一个月，基期去年同月），"
                f"却还写着 {'、'.join(stray)} —— 这几个键只管年度分桶，月度桶下"
                f'一个也读不到。留着一个再也不起作用的声明，比当场报错糟：'
                f'下一个人会以为月度图的横轴还受它们管，改了它却什么都不动')
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
        'bucket': bucket,
        # 挂载点：某个 group 的 zh 字符串。留空 = 老行为（排在页尾、核对表之前）。
        # 组名存不存在、唯不唯一由 `Page.__init__` 现查（那里才拿得到 groups）。
        'after_group': (str(d['after_group']) if d.get('after_group') else None),
        # ⚠️ 三个年度键在月度桶下一律 **None**（上面已保证 spec 里没写过它们）：
        # 置 None 而不是留缺省，是为了让「月度分支不小心读到它们」当场炸掉 ——
        # 读到 1 / 'start' / 5 的话会算出一张看着完全正常、口径却不是所有者要的图。
        'year_start_month': (int(d.get('year_start_month', 1))
                             if bucket == 'year' else None),
        # 财年叫哪一年，全球没有统一规矩：JPX 的 FY2025 = 2025-04…2026-03（按**起始**年
        # 命名，日本「年度」的惯例），SGX 的 FY2026 = 2025-07…2026-06（按**结束**年命名）。
        # 底座猜不出来，猜错会让整排柱的标签集体偏一年，而图形本身完全正常 ——
        # 这种错没有任何自动判据能发现，所以做成必须由 spec 明说的字段。
        'year_label': (str(d.get('year_label', 'start')) if bucket == 'year' else None),
        'years': (int(d.get('years', DECOMP_YEARS)) if bucket == 'year' else None),
        'note': str(d.get('note') or ''),
        'section': str(d['section']) if d.get('section') else None,
    }
    if out['price_fmt'] not in FMT_INFO:
        raise SpecError(f"{where} 的 price_fmt={out['price_fmt']!r} 不是引擎实有的格式器名；"
                        f'可用：{sorted(FMT_INFO)}')
    if d.get('weight_col') and out['granularity'] != 'daily_avg':
        raise SpecError(f"{where} 声明 granularity='monthly_total'（列本身已是当月合计）"
                        f"却又给了 weight_col={d['weight_col']!r} —— 再乘一次交易日数"
                        f'会把年度合计放大二十几倍，而图形照画、量级看着还挺像')
    # ── 下面四条**只管年度桶**：月度桶下这三个键根本不存在（上面已挡），
    #    值也已置 None，拿 None 去比大小只会得到一个与口径无关的 TypeError。
    if out['bucket'] == 'year':
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
            raise SpecError(f"{where} 的 years={out['years']} < 2 —— "
                            f'一根柱没有「逐年对比」可言')
    if not (np.isfinite(out['price_scale']) and out['price_scale'] > 0):
        raise SpecError(f"{where} 的 price_scale={d.get('price_scale')!r} 必须是正的有限数")
    return out


def _norm_level_yoy(t, where):
    """一条「水平值 + 次轴单月同比」配置 → 归一化 dict。**只收流量列。**

    ⚠️ 2026-09 之前这个字段叫 `ttm_yoy`，还带 `granularity` / `total_col` /
    `weight_col` 三个键 —— 那是为了把日均列还原成当月合计好滚 12 个月。次轴改成
    单月同比（本列除本列）之后那三个键一步也用不上了，所以从 `LEVEL_YOY_KEYS` 里
    删掉而不是留着不读：`_check_keys` 是白名单，删掉之后旧 spec 会**当场报错**，
    而不是带着一个再也不起作用的还原声明静默上线。

    ── 为什么在这里把比率列与存量列硬挡回去 ────────────────────────────────
    `ex_level_yoy` 把「这是流量」写死在四处：标题 `…：水平值与单月同比`、
    `ylab2='% y/y（单月）'`、`yoy_rhs(..., pct_series=False)`、`log_yoy(n, 'mom')`。
    而 `_norm_col` 本身允许 `stock=True` 与 `fmt='pct*'`，两者之间从前没有任何东西
    把关：
      · 比率列 → `yoy_rhs` 按 (a/b−1) 出数，画出来是「百分比的百分比变化」，
        违 CONTRACT §6.1 第 4 条（比率的同比一律走百分点差）；
      · 存量列 → 点对点同比本身是合法的，但这张图会把它称作「单月同比」、
        记进页尾 `'mom'` 那一段，标题里也没有 `ex_stock` / `ex_mix_total` 都写着的
        「（存量，期末口径）」—— 而 `tools/check_yoy_caliber.py` 的 `_STOCK_TXT`
        正是靠那几个字认出存量图并豁免 R1/R4 的。口径对、说法错，
        照样是一句印在页面上的假话。
    今天没有 spec 踩到，但那是没护栏不是没发生。

    挡在**读 spec 的这一刻**而不是画图那一刻：这是「spec 写错了、要人去改」，
    该走退出码 1，不该等排到第 40 张图才炸。也不做「自动按 kind 分支」——
    比率与存量本来就各有一条画得更对的路（见报错文案），多一条分支只是多一处
    要维护的口径措辞。
    """
    if not isinstance(t, dict):
        raise SpecError(f'{where} 必须是 dict，收到 {type(t).__name__}')
    for dead in ('granularity', 'total_col', 'weight_col'):
        if dead in t:
            raise SpecError(
                f'{where} 还带着 {dead!r} —— 这是旧 `ttm_yoy` 用来把日均列还原成当月'
                f'合计、好滚 12 个月的字段。本图的次轴 2026-09 已改成**单月同比**'
                f'（本列除本列，一步还原都不需要），三个字段一并删除；请直接删掉这一行。')
    _check_keys(t, LEVEL_YOY_KEYS, LEVEL_YOY_REQUIRED, where)
    lvl = _norm_col(t['level'], f'{where}.level')
    # 判据走 col_is_ratio 而不是只看 fmt：只看 fmt 的话，一列真比率只要没配 pct*/pp*
    # 就能从这里溜进去，而这张图的次轴是**写死**的 (a/b−1)（见下面那段报错）。
    if col_is_ratio(lvl):
        raise SpecError(
            f'{where}.level 的 {lvl["col"]} 是**比率列**（fmt={lvl["fmt"]!r}、'
            f'unit={lvl["unit"]!r}、yoy.classify()={ycal.classify(lvl["col"])!r}，'
            f'判据见 build/single.py 的 col_is_ratio）—— level_yoy 只收流量列。这张图的次轴写死成'
            f'「% y/y（单月）」并按 (a/b−1) 出数，对比率算出来的是「百分比的百分比'
            f'变化」；CONTRACT §6.1 第 4 条要求比率的同比一律走**百分点差**'
            f'（0.24 → 0.25 是 +1bp，不是 +4.2%）。'
            f'出路：把这一列放进 groups[].cols 的单列桶，`ex_single` 会按 pp 处理。')
    if lvl['stock']:
        raise SpecError(
            f'{where}.level 的 {lvl["col"]} 声明了 stock=True —— level_yoy 只收流量列。'
            f'存量的点对点同比本身合法（CONTRACT §6.1 第 2 条），但这张图会把它称作'
            f'「单月同比」、记进页尾 mom 那一段，标题里也不带「（存量，期末口径）」'
            f'—— tools/check_yoy_caliber.py 的 _STOCK_TXT 认的就是那几个字。'
            f'出路：把这一列放进 groups[].cols，`ex_stock` 画的是同一种'
            f'「水平值柱 + 次轴同比」，只是口径与措辞都按存量写对了。')
    return {
        'zh': str(t['zh']),
        'level': lvl,
        'note': str(t.get('note') or ''),
        'section': str(t['section']) if t.get('section') else None,
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
    abs_stack = _norm_flag(m.get('abs_stack'), f'{where}.abs_stack')
    dead = [k for k in ('rhs_share', 'share_note') if abs_stack and m.get(k)]
    if dead:
        raise SpecError(
            f'{where} 同时写了 abs_stack 与 {dead} —— 后者只有 100% 占比那张图'
            f'读得到，而 abs_stack 根本不出那张图（只出一张绝对值堆叠柱）。'
            f'留着就是死配置：下一个人会以为这张图上有一条右轴线 / 一段占比说明')
    return {
        'total': str(m['total']),
        'parts': [str(x) for x in parts],
        'residual_zh': str(m.get('residual_zh') or ''),
        'rhs_share': str(m.get('rhs_share') or ''),
        'note': str(m.get('note') or ''),
        'share_note': str(m.get('share_note') or ''),
        'abs_stack': abs_stack,
    }


def _norm_flag(v, where):
    """spec 里的一个布尔开关。`None`（没写）算 False，其余只认 `True` / `False`。

    不写成 `bool(v)`：`'false'` / `'0'` / `[]` 在 Python 里各有各的真假，而写 spec 的人
    看到的是一个开关。真假判错的后果是「以为关着其实开着」——那正是本轮要治的病。
    """
    if v is None or v is False:
        return False
    if v is True:
        return True
    raise SpecError(f'{where}={v!r} 只能写 True 或 False（不写 = False）')


def _norm_ratio_rhs(r, where):
    """一条 `groups[].ratio_rhs` → 归一化 dict。这里只做**机械**校验。

    「num / den 在不在本组」「同不同单位」「逐月的包含关系（den > 0、num ≥ 0、
    num ≤ den）」这三件事都要看别的东西（本组的列表、CSV 的数），一律留给
    `Page.__init__` 复算 —— 与 `_norm_mix` 同一分工。
    `num` / `den` / `dup_part` 写的是**列名**，不是列配置：列配置只在 `groups[].cols`
    里声明一次，这里引用（理由见 `_norm_mix` 的 docstring）。
    """
    if not isinstance(r, dict):
        raise SpecError(f'{where} 必须是 dict，收到 {type(r).__name__}')
    _check_keys(r, RATIO_RHS_KEYS, RATIO_RHS_REQUIRED, where)
    num, den = str(r['num']), str(r['den'])
    if num == den:
        raise SpecError(f'{where} 的 num 与 den 是同一列（{num}）—— 一列除以自己'
                        f'恒为 100%，右轴那条线会是一条直线')
    if not str(r['zh']).strip():
        raise SpecError(f'{where} 的 zh 是空的 —— 它是右轴那条线的图例名与轴标题，'
                        f'空着页面上就只剩一条没有名字的线')
    dup_part, dup_note = str(r.get('dup_part') or ''), str(r.get('dup_note') or '').strip()
    if dup_note and not dup_part:
        raise SpecError(
            f'{where} 给了 dup_note 却没给 dup_part —— dup_note 解释的是「本比值与那条 '
            f'mix 分项互为补集时，两者为什么还有差」，没有 dup_part 就没有那段可解释，'
            f'这句话在页面上会挂在半空')
    return {'num': num, 'den': den, 'zh': str(r['zh']).strip(),
            'note': str(r.get('note') or ''),
            'dup_part': dup_part, 'dup_note': dup_note}


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
                'section': str(g['section']) if g.get('section') else None,
                'mix': _norm_mix(g['mix'], f'groups[{gi}]（{g["zh"]}）.mix')
                if g.get('mix') else None,
                'ratio_rhs': _norm_ratio_rhs(
                    g['ratio_rhs'], f'groups[{gi}]（{g["zh"]}）.ratio_rhs')
                if g.get('ratio_rhs') else None,
                # 只认真正的布尔量：`'yes'` / `1` 这种写法在别处是「真」，在这里
                # 会让下一个人以为可以写一个阈值或图号进去。硬失败比默默当真好。
                'spike_cap': _norm_flag(g.get('spike_cap'),
                                        f'groups[{gi}]（{g["zh"]}）.spike_cap')})

        self.headline_style = str(spec.get('headline_style') or 'band_yoy')
        if self.headline_style not in HEADLINE_STYLES:
            raise SpecError(f"headline_style={self.headline_style!r} 只能是 "
                            f"{HEADLINE_STYLES[0]!r}（两张：全历史分位带 + 同比柱）或 "
                            f"{HEADLINE_STYLES[1]!r}（一张：全历史柱 + 次轴单月同比）")
        self.decomp = [_norm_decomp(d, f'decomp[{i}]')
                       for i, d in enumerate(spec.get('decomp') or [])]
        # ── `after_group` 的锚点必须**写得对**且唯一（这一档是「等人」，硬失败）──────
        # 这条改动最可能的失败模式就是**名字打错**：不校验的话，锚点匹配不上，
        # 这张图会静默掉回页尾 —— 图还在、页面照常上线、闸门全过，
        # 只有对着页面数图号的人才发现所有者要的位置没生效。
        # 重名同理：两个同名 group 时「排在它之后」有两个答案，挑哪个都是猜。
        #
        # ⚠️ **这一轮只查「spec 里写的名字对不对」，查的是剔空列之前的组名表。**
        # 「名字写对了、但那一组本轮整组没有数据（列全空）」是**另一件事**，
        # 归下面剔空列之后那一段（`decomp_moved`）—— 那一档是等数据，不许硬失败。
        # 两件事在这里合成一段的代价实测过：锚点组因整列为空而消失时，
        # 这里放行、`payload()` 的 groups 循环再也不给出那个组名（`_decomp_here` 不触发）、
        # 页尾那一轮又 `if d['after_group']: continue` ⇒ **两头都没人接**，
        # 整张分解图凭空不见，`skipped` 空、`decomp_report` 空、退出码 0、闸门全过。
        _gz = [g['zh'] for g in self.groups]
        for i, d in enumerate(self.decomp):
            a = d['after_group']
            if a is None:
                continue
            k = _gz.count(a)
            if k != 1:
                raise SpecError(
                    f"decomp[{i}]（{d['zh']}）的 after_group={a!r} 在 groups 里"
                    + (f'找不到 —— 可用的组名：{_gz}' if k == 0 else
                       f'出现 {k} 次 —— 「排在它之后」有 {k} 个答案，挑哪个都是猜')
                    + '。名字对不上就静默掉回页尾，图还在、闸门全过，'
                      '只有对着页面数图号的人才看得出所有者要的位置没生效')
        self.level_yoy = [_norm_level_yoy(t, f'level_yoy[{i}]')
                          for i, t in enumerate(spec.get('level_yoy') or [])]

        # ── 列必须真实存在于 CSV。缺列是 spec 写错，硬失败（要人去改，不是等数据）──
        have = set(self.df.columns)
        allc = self.head + [c for g in self.groups for c in g['cols']]
        # decomp / level_yoy 引用的列同样要查。它们**不进** allc：allc 还管
        # 「整列为空就剔除」与核对表，而分解图的列是否上核对表由 spec 自己在 groups 里决定，
        # 不该因为写了一条 decomp 就被顺带塞进表里（那会让同一列在表上出现两次）。
        aux = ([c['col'] for d in self.decomp for c in (d['value'], d['qty'])]
               + [d[k] for d in self.decomp
                  for k in ('value_total_col', 'qty_total_col', 'weight_col') if d[k]]
               + [t['level']['col'] for t in self.level_yoy]
               )    # mix 的 total / parts 引用的都是 groups 里已声明的列，已在 allc 里
        missing = sorted({c['col'] for c in allc if c['col'] not in have}
                         | {c for c in aux if c not in have})
        if missing:
            raise SpecError(f'series/{spec["csv"]} 缺列 {missing} —— 写 spec 之前先 '
                            f'`head -1 series/{spec["csv"]}` 核对列名')

        # 「这张图问过断点」的账（图号）。真正的每轮清零在 `payload()` 里，这里只给一个
        # 空集兜底：`mark_breaks()` 万一在 payload 之外被调到，不该炸在一本账上。
        self._brk_asked = set()
        # 与上面配套的另一本账：**没问过断点**的那几张图各自用了哪几条列
        # （图号 → 列名）。同样只在这里兜底，每轮清零在 `payload()` 里。
        # 用处见 `note_nodraw_cols()`。
        self._nodraw_cols = {}
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
        _declared = {g['zh']: [c['col'] for c in g['cols']] for g in self.groups}
        for g in self.groups:
            g['cols'] = [c for c in g['cols'] if c['col'] not in self.empty]
        self.groups = [g for g in self.groups if g['cols']]

        # ── `after_group` 的锚点组**本轮还在不在**（这一档是「等数据」，不硬失败）─────
        # 名字对不对上面已经查过了，能走到这里的锚点都是 spec 写对了的；
        # 组没了只可能是**它声明的列本轮整列为空**，被上面那三行剔掉了整组。
        # 「等数据 ≠ 等人」：源表少一列不该让整页停更，也不该让这张图凭空消失 ——
        # 锚点没有着落时**退回缺省位置（页尾）并记一笔**，源表补上列就自动回到原位。
        #
        # ⚠️ **没有并进 `self.skipped` 那本账**（红队骨架里写的是它，这里改了落点）：
        # 那本账的抬头是「本轮未出的派生图」、收尾是「数据补齐后自动回来」，
        # 而这一档的图**出了**，只是位置退到页尾 —— 塞进去等于印一句「它没出」的假话。
        # 判例同 `dup_yoy_zh()` 上面那段注释（图已经出了的事不进「未出」那本账）。
        # 所以另开一本：`build()` 打一行给维护者，页尾印一句给读者，两处都点名到组。
        self.decomp_moved = []
        _live = {g['zh'] for g in self.groups}
        for d in self.decomp:
            a = d['after_group']
            if a is None or a in _live:
                continue
            gone = [c for c in _declared.get(a, []) if c in self.empty]
            # 这条字串**同时**进构建日志与页尾，所以一律纯文本：不写 <b>（终端里会
            # 露出标签），也不写 Markdown 的星号（页尾走 innerHTML，星号原样印出来）。
            self.decomp_moved.append(
                f'{d["zh"]}：spec 要它紧跟「{a}」那一组出图，但那一组本轮整组不在页上'
                f'（它声明的 {len(gone)} 列 '
                f'{"、".join(gone) or "（列已被别处剔除）"} 整列为空），锚点没有着落，'
                f'这张图改排页尾')
            # 锚点作废：置回 None，让页尾那一轮（`payload()` ⑥）接住它。
            # 不置 None 的话 `_decomp_here` 不触发、页尾又 `continue`，两头都没人接。
            d['after_group'] = None

        # ── groups[].mix：列名 → 列配置，并把「被 mix 吃掉」的列记下来 ──────────────
        #
        # 引用而不是另写一份列配置（见 `_norm_mix` 的 docstring），所以这里要做三件事：
        #   ① 名字必须指向**本 spec 已声明**的列 —— 拼错的列名会让整张图静默消失；
        #   ② total 与 parts 必须同一个 `unit`、同一个 `stock` 档 —— 单位不同的两列相除
        #      得到的「占比」没有指称，而流量与存量混堆等于把「一个月发生了多少」和
        #      「月末剩下多少」加起来；
        #   ③ 记下**本组自己**被吃掉的列名（`g['consumed']`）：它们的水平值与结构由
        #      这一组的「合计柱 + 占比堆叠」交代，不再进本组的常规对比图，
        #      否则同一批数在同一页上画两遍。
        #      ⚠️ **合计那一列的水平值不一定由「这一组的合计柱」交代。** 它已经被本页
        #      别处那张同族、同口径、横轴更宽的图画过时，本组的合计柱有意不出
        #      （`Page.total_drawn_wider`），水平值改由那张更宽的交代 —— 但这一列
        #      **照样算被吃掉**（不然它掉回常规分桶再画一遍，见 `mix_pair` 里 eaten
        #      那段的 ⚠️）。所以这里说的是「由这一组的 mix 交代」，不是「由两张图交代」。
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
                    f'{where} 里 {bad_ratio} 是比率列（判据见 `col_is_ratio`：'
                    f'spec 的 ratio 声明、或 fmt ∈ {sorted(RATIO_FMT)}、'
                    f'或列名与单位的量纲都认它是比率）—— '
                    f'比率不许进 mix：合计柱的次轴走的是流量的单月同比（本列除本列），'
                    f'而比率的同比应当是**百分点差**（CONTRACT §6.1 第 4 条：'
                    f'0.24 → 0.25 是 +1bp，不是 +4.2%）；'
                    f'占比堆叠那一侧更直接 —— 几个比率相加不等于合计那个比率。'
                    f'要画比率就走常规的单列 gs_bar（`ex_single` 会按 pp 处理）')
            # 本组自己声明了哪几列 —— `mix_pair` 拿它把「被吃掉的列」限定在本组内。
            # 跨组引用的语义是「借它的数画结构」，不是「替它把水平值也讲了」。
            g['declared'] = {c['col'] for c in g['cols']}

        # ── cols[].no_yoy 的落点校验：只有 `ex_single` 那一条产图路径读得到它 ────────
        #
        # 声明在别的路径上会被**静默忽略**：图照画、同比照旧、五道闸门全绿，
        # 只有对着页面数线的人才发现「去掉同比」这条指令根本没生效。
        # 本仓对「拼错/放错位置就静默失效」的字段一律硬失败（判例：decomp 的
        # `after_group` 锚点校验、`slow_cols` 的列名校验）。
        #
        # ⚠️ **名单里必须有 `ex_heat`**。超过 MAX_LINES 的同单位桶画的是**同比**热力
        #    矩阵（`ex_heat` 自己调 `log_yoy`），那是唯一一条「声明被忽略、而同比
        #    照样画在页面上」的路 —— 漏了它，这段守卫自己的报错文案就是假的。
        #    2–5 列的桶走 `ex_lines`（本来就不画同比），危害小，但同样点名。
        #
        # ⚠️ **分桶要按「最坏情形」算，不能照抄 `payload()`。** 两处的 `eaten` 天生不同源：
        #    `payload()` 按**真画出来的图**扣列（`mix_pair` 那张没出成就一列都不扣），
        #    而守卫在 `__init__` 里跑、那时还不知道图出不出得来，只能按**声明**扣。
        #    照声明算就会漏人：mix 那张图因为窗口不足而没出时，被「声明扣掉」的列
        #    会重新回到桶里，桶一超过 MAX_LINES 就走 `ex_heat`（画同比）——
        #    声明既没报错、又没生效，而同比照画在页面上，正是这道守卫要消灭的形状。
        #    所以下面对**两种情形各分一次桶**：mix 生效（扣列）与 mix 落空（不扣列），
        #    任一种下这一列不是独占一桶就拦。宁可多拦：多拦是一句报错，
        #    漏拦是页面上一条没人知道的假同比。
        _ny, _seen_ny = [], set()
        for i, c in enumerate(self.head):
            if c['no_yoy']:
                _ny.append(f'headline[{i}]「{c["zh"]}」→ 走 ex_head_bar / ex_yoy')
        for g in self.groups:
            m = g.get('mix')
            eaten = set()
            if m:
                eaten = {m['total']['col']} | {c['col'] for c in m['parts']}
                if m['total']['no_yoy']:
                    _ny.append(f'groups「{g["zh"]}」.mix 的 total'
                               f'「{m["total"]["zh"]}」→ 走 ex_mix_total')
                for c in m['parts']:
                    if c['no_yoy']:
                        # 措辞不能写「根本不出水平值柱」：`abs_stack` 那张图的每一段
                        # 画的**就是**分项的水平值（jpx Exhibit 9 两段 = 两个分项的
                        # ¥tn/day 原值）。结论（这个开关没人读）不变，理由要说对。
                        _ny.append(f'groups「{g["zh"]}」.mix 的分项'
                                   f'「{c["zh"]}」→ 走 ex_mix_share / ex_mix_abs，'
                                   f'两者都不画次轴同比、也不读这个开关')
            for c in g['cols']:
                if c['no_yoy'] and c['stock']:
                    _ny.append(f'groups「{g["zh"]}」的「{c["zh"]}」'
                               f'（stock=True）→ 走 ex_stock')
            # 没有 mix 的组只有一种情形；有 mix 的组两种都要算（见上面那段的理由）。
            cases = ([('', set())] if not eaten
                     else [('mix 生效（分项被扣掉）', eaten),
                           ('mix 落空（分项回到桶里）', set())])
            for eaten_case, ea in cases:
                flow = [c for c in g['cols'] if not c['stock'] and c['col'] not in ea]
                buckets = []
                for c in flow:
                    for b in buckets:
                        if b[0] == c['unit']:
                            b[1].append(c)
                            break
                    else:
                        buckets.append((c['unit'], [c]))
                for _u, cs in buckets:
                    if len(cs) == 1:
                        continue                  # ← 唯一读得到 no_yoy 的桶
                    path = ('ex_heat（>{} 列，画的是同比热力矩阵，**同比照画**）'
                            .format(MAX_LINES) if len(cs) > MAX_LINES
                            else 'ex_lines（多列折线，本来就不画同比）')
                    for c in cs:
                        if c['no_yoy'] and c['zh'] not in _seen_ny:
                            _seen_ny.add(c['zh'])
                            _ny.append(
                                f'groups「{g["zh"]}」的「{c["zh"]}」'
                                + (f'在「{eaten_case}」这种情形下' if eaten_case else '')
                                + f'与同单位的另外 {len(cs) - 1} 列同桶 → 走 {path}')
        for i, t in enumerate(self.level_yoy):
            if t['level']['no_yoy']:
                _ny.append(f'level_yoy[{i}]「{t.get("zh", "?")}」的 level'
                           f'「{t["level"]["zh"]}」→ 走 ex_level_yoy')
        # `decomp` 的四个列位置也走 `_norm_col`，所以 `no_yoy` 在那里**语法上写得进去**，
        # 而 `ex_decomp` 从不读它 —— 声明会被静默吞掉、payload 一字不改、零报错。
        # 这正是本守卫要消灭的那种失效方式，漏了它守卫自己的报错文案就是假的。
        # （`_norm_col` 共 7 个调用点：headline、groups[].cols、level_yoy.level
        #   与这里的四个；前三处在上面已经点过名。）
        for i, d in enumerate(self.decomp):
            for k in ('value', 'qty', 'bench_value', 'bench_qty'):
                c = d.get(k)
                if isinstance(c, dict) and c.get('no_yoy'):
                    _ny.append(f'decomp[{i}]「{d.get("zh", "?")}」的 {k}'
                               f'「{c["zh"]}」→ 走 ex_decomp（分解图不画次轴同比，'
                               f'这个开关那条路径根本不读）')
        if _ny:
            raise SpecError(
                'no_yoy 只有 `ex_single`（groups 里**单独占一个单位桶**的流量列）'
                '读得到，下面这些地方声明了它但根本没人看，声明会被静默忽略、'
                f'同比照画：{_ny} —— 要关那几条路径上的同比，'
                '得先在对应的产图函数里实现，不是在这里多写一行')

        # ── groups[].ratio_rhs：列名 → 列配置，并复算「num ⊆ den」这个包含关系 ──────
        #
        # 与 mix 同一条分工：`_norm_ratio_rhs` 只做机械校验，凡是要看别的东西
        # （本组的列表、CSV 的数）的判据都在这里，而且**全部现算、不许写死**。
        for g in self.groups:
            r = g.get('ratio_rhs')
            if not r:
                continue
            where = f'groups（{g["zh"]}）.ratio_rhs'
            own = {c['col']: c for c in g['cols']}
            miss = [x for x in (r['num'], r['den']) if x not in own]
            if miss:
                gone = [x for x in miss if x in self.empty]
                if gone:
                    # 整列为空是「等数据」不是「spec 写错」（同 mix）：记账、这一桶
                    # 退回常规路径，不硬失败。
                    self.mix_skipped.append(
                        f'{g["zh"]}：{"、".join(gone)} 整列为空，'
                        f'并排柱与右轴比值线都不出，这一桶退回常规折线/柱图')
                    g['ratio_rhs'] = None
                    continue
                raise SpecError(
                    f'{where} 的 {miss} 不在**本组**的 cols 里 —— num/den 写的是列名，'
                    f'列配置只在 groups[].cols 里声明一次。本组现有列：{sorted(own)}。'
                    f'（跨组引用不许：这张图画的是这一桶自己的两根柱，'
                    f'借别的组的列会让那一组的水平值图凭空少一张）')
            cn, cd = own[r['num']], own[r['den']]
            if cn['unit'] != cd['unit']:
                raise SpecError(
                    f'{where} 的 num（{cn["zh"]}，{cn["unit"]}）与 den（{cd["zh"]}，'
                    f'{cd["unit"]}）单位不同 —— 单位不同的两列相除得到的「比值」'
                    f'没有指称，而且分桶按 unit 走，两列根本落不进同一张图')
            if cn['stock'] != cd['stock']:
                raise SpecError(
                    f'{where} 的 num 与 den 一个是流量一个是存量 —— '
                    f'流量按月累计发生、存量是某一天的截面，相除得到的数没有指称；'
                    f'存量列在本底座里还各自成图（ex_stock），根本不进这一桶')
            if cn['stock']:
                raise SpecError(
                    f'{where} 引用的是存量列 —— 存量列走 `ex_stock` 各自成图，'
                    f'不进按单位分的流量桶，声明了也画不出并排柱')
            # 本桶必须**恰好**是 num 与 den 两列：分桶按 unit 走，同单位还有第三列时
            # 这一桶会是三根柱 + 一条只解释其中两根的比值线。
            eaten = set()
            if g.get('mix'):
                eaten = ({g['mix']['total']['col']}
                         | {c['col'] for c in g['mix']['parts']}) & set(own)
            same = [c for c in g['cols']
                    if not c['stock'] and c['unit'] == cn['unit'] and c['col'] not in eaten]
            if {c['col'] for c in same} != {r['num'], r['den']}:
                raise SpecError(
                    f'{where}：本组里单位为 {cn["unit"]} 的流量列是 '
                    f'{[c["zh"] for c in same]}，不是恰好 num 与 den 两列 —— '
                    f'底座按 unit 分桶、一桶一张图，多出来的列会跟着画成第三根柱，'
                    f'而右轴那条比值线只解释其中两根。'
                    f'出路：把多出来的列拆进另一个 group')
            # ── 包含关系逐月复算：den > 0、num ≥ 0、num ≤ den。反例报月份与两个读数 ──
            sn, sd = self.ser(cn), self.ser(cd)
            bad_den = [(str(p), float(sd[p])) for p in self.df.index
                       if np.isfinite(sd[p]) and sd[p] <= 0]
            if bad_den:
                raise SpecError(
                    f'{where} 的 den（{cd["zh"]}）在 '
                    f'{"、".join(f"{m} = {v:g}" for m, v in bad_den[:6])}'
                    f'{"（等 %d 个月）" % len(bad_den) if len(bad_den) > 6 else ""} '
                    f'不是正数 —— 比值 num/den 在那些月要么爆掉、要么变号')
            # num < 0 与 den <= 0 是**同一个理由**：包含关系（num ⊆ den）里分子是
            # den 的一段，一段不可能是负的。护栏漏掉这一条时页面上会同时出三处假话：
            # 图注写死的「比值是 0–100 的无量纲数」（实测可以到 −304.8%）、
            # 「右轴刻度不从 0 起」那半句的前提，以及 `ex_ratio_rhs` 里
            # 「柱全非负 ⇒ 两轴零点对齐是空操作」那段论证 ——
            # 柱一旦跨零，左轴 y0 = min(0, mn×1.15) < 0、右轴下界也 < 0，
            # 引擎的 f 就不再是 0（实测 f=0.7778、waste=0.7111 > ALIGN_WASTE_MAX 0.38），
            # 会走兜底分支、在图上印「左右轴零点不同高」那行红字，
            # 而图注里那串右轴刻度是**对齐之前**算的，两处对不上。
            # 三处假话没有一处会自己响，所以判据放在这里、和 den 一起硬失败。
            bad_neg = [(str(p), float(sn[p]), float(sd[p])) for p in self.df.index
                       if np.isfinite(sn[p]) and sn[p] < 0]
            if bad_neg:
                raise SpecError(
                    f'{where} 声明 num（{cn["zh"]}）是 den（{cd["zh"]}）的一部分，'
                    f'但 {"、".join(f"{m}：{a:g}（den {b:g}）" for m, a, b in bad_neg[:6])}'
                    f'{"（等 %d 个月）" % len(bad_neg) if len(bad_neg) > 6 else ""} '
                    f'的 num 是负数 —— 一段不可能是负的，比值也就不是占比。'
                    f'负的分子还会把两根柱拉到零轴以下，引擎的两轴零点对齐随之从'
                    f'空操作变成真重排（超 ALIGN_WASTE_MAX 就在图上印'
                    f'「左右轴零点不同高」红字），而图注里的右轴刻度是对齐之前算的。'
                    f'出路：这两列不是包含关系，去掉 ratio_rhs 各自画水平值')
            bad_le = [(str(p), float(sn[p]), float(sd[p])) for p in self.df.index
                      if np.isfinite(sn[p]) and np.isfinite(sd[p])
                      and sn[p] > sd[p] * (1 + 1e-9)]
            if bad_le:
                raise SpecError(
                    f'{where} 声明 num（{cn["zh"]}）是 den（{cd["zh"]}）的一部分，'
                    f'但 {"、".join(f"{m}：{a:g} > {b:g}" for m, a, b in bad_le[:6])}'
                    f'{"（等 %d 个月）" % len(bad_le) if len(bad_le) > 6 else ""} '
                    f'—— 比值 > 100% 的「占比」不是占比，多半是两列口径不同')
            r['num_col'], r['den_col'] = cn, cd

            # ── 可选：dup_part —— 主动认领「这条比值 ≡ 100% − 某条 mix 里的某一段」──
            # 本仓判例第 1 条是「同一条序列换个切法再画一遍要删」。这条比值确实与
            # 占比堆叠里的某一段互为补集，删不掉（右轴那条线是所有者点名要的），
            # 所以只能在图注里正面交代 —— 而「交代」必须带一个**实测**的差，
            # 不能只写一句「两者等价」。差由这里逐月复算，超容差就硬失败：
            # 图注里那句话会因为数据变化变成假话，而假话不会自己响。
            if not r['dup_part']:
                continue
            host = next((h for h in self.groups if h.get('mix')
                         and r['dup_part'] in {c['col'] for c in h['mix']['parts']}), None)
            if host is None:
                raise SpecError(
                    f'{where} 的 dup_part={r["dup_part"]!r} 不是本页任何一条 mix 的分项 —— '
                    f'它的语义是「本比值 ≡ 100% − 那张 100% 堆叠图里的那一段」，'
                    f'那一段不存在就没有重复可交代。'
                    f'现有分项：{sorted({c["col"] for h in self.groups if h.get("mix") for c in h["mix"]["parts"]})}')
            c_part = next(c for c in host['mix']['parts'] if c['col'] == r['dup_part'])
            c_tot = host['mix']['total']
            sh = self.ser(c_part) / self.ser(c_tot) * 100.0
            rt = sn / sd * 100.0
            dif = (rt - (100.0 - sh)).abs().dropna()
            if dif.empty:
                raise SpecError(
                    f'{where} 的 dup_part={r["dup_part"]!r} 与本比值没有一个共同月份 —— '
                    f'两者对不上任何一期，「等价」这句话无从复算')
            if float(dif.max()) > RATIO_DUP_TOL:
                raise SpecError(
                    f'{where} 声明本比值 ≡ 100% −「{c_part["zh"]}」占比，'
                    f'但逐月最大差 {float(dif.max()):.4f}pp（{dif.idxmax()}）已超过 '
                    f'{RATIO_DUP_TOL}pp 的容差 —— 两者不再是同一条序列，'
                    f'图注里那句「这是同一个数」会是假话。'
                    f'要么去掉 dup_part，要么先查清两个口径为什么分叉')
            r['dup'] = {'zh': c_part['zh'], 'gz': host['zh'], 'total_zh': c_tot['zh'],
                        'max': float(dif.max()), 'max_at': str(dif.idxmax()),
                        'med': float(dif.median()), 'n': int(dif.size),
                        # 「那张堆叠图回答『几个分项各占多少』」里的那个数：从宿主 mix
                        # 的 parts 现算。从前写死「四个」—— 宿主换一条 mix 就成假话。
                        'nparts': len(host['mix']['parts']),
                        'note': r['dup_note']}
            # ⚠️ **交代必须是双向的。** 上面那条只让比值线那张图指认「我与某张占比图的
            # 某一段是同一个数」；从占比图进来的读者仍然不知道同一个数在别处又出现了一次。
            # 判例第 4 条要的是「页面上交代」，不是「在两张图里挑一张交代」。
            # 所以在**宿主组的 mix 上**回挂同一笔账，由 `ex_mix_share` 印出反向那句。
            # 两句共用这一份现算的差值 ⇒ 不可能一处说 0.02pp、另一处说别的数。
            # `note` 也共用同一份 `dup_note`：那句解释从前在两处各写死一遍
            #（「这里是日均、那里是当月合计」与「一处日均、一处当月合计」），
            # 两份写死的话既证不了、又会各自漂。
            host['mix']['dup_back'] = {
                'part_zh': c_part['zh'], 'ratio_zh': r['zh'], 'gz': g['zh'],
                'max': float(dif.max()), 'max_at': str(dif.idxmax()),
                'med': float(dif.median()), 'n': int(dif.size),
                'note': r['dup_note']}

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
        # 「合计柱**有意**不出」这本账：mix 的合计列已经被本页别处那张横轴更宽的
        # bar_yoy 图原样画过时记一笔（形状见 `total_drawn_wider` 的返回值，外加
        # `gz` 与 `share_drawn`；记账在 `mix_pair` 里、占比图出结果之后）。
        # 它不进 `skipped` —— 那本账是给「想画而画不成」用的，两件事在页面上要分开说。
        # 两个出口：页尾「图型选择规则」那一段由 `mix_folded_zh()` 现算（哪几组、
        # 两张的窗口、绝对量去哪看、占比那张有没有画成），`build()` 另打一行给维护者。
        self.mix_folded = []
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
        """见模块级 `col_is_ratio()` —— 全底座唯一的比率判据，这里只是转发。"""
        return col_is_ratio(c)

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

        页尾「同比口径」条目从这本账**现算**点名文案，写成「Exhibit X、Y：单月同比」
        这种可核对的形式。逐处点名的写法出自 CONTRACT §6.2（那一节要求同页并存两种
        口径时必须逐张点名）；本底座只产出单月一种口径，所以这段话在这里不是为了
        分辨口径，而是让读者能一眼数清哪些图上有同比线 —— §6.1 第 3 条的 ⚠️ 明说
        页尾这段「可以有（点名口径用），但不能顶替逐图那一段」，逐图那一段由
        `mom_cost_zh()` 印在每张图自己的图注里。点名必须由产图的代码自报、
        图号必须是派生的，两个理由：
          · 被点名的对象里有底座自己生成的图（头条同比图、各类柱图的次轴同比线），
            spec 作者看不见它们排在几号，没法在 spec 的 notes 里点对；
          · 写死的图号会在删图加图后指向错的图而**不报任何错**（本仓吃过这亏 ——
            图号硬编码在别处造成过「Exhibit 17 之后跟着 15」）。账本跟着产图走，
            哪张图不再画同比、或新增一张，页尾那段话自动跟随。
        """
        if cal not in YOY_CALS:
            raise SpecError(f'log_yoy 收到未知口径类别 {cal!r} —— 这是底座代码写错，'
                            f'不是 spec 的问题（拼错的类别会静默丢一段点名文案，'
                            f'所以硬失败）；认得的类别：{YOY_CALS}')
        self.yoy_log.append({'n': n, 'cal': cal})

    #: 「同一条同比画了两遍」这本账认的两个图族。查重只在**同一列 + 同一口径**里做，
    #: 图族决定撞上之后是硬失败还是告警：
    #:   bar_yoy  = 水平值柱 + 次轴同比（ex_single / ex_head_bar / ex_mix_total /
    #:              ex_stock / ex_level_yoy 五条路径都产出这一种）
    #:   yoy_only = 纯同比图，整张画布只有同比（ex_yoy 的头条 grouped_bars）
    YOY_FAMILIES = ('bar_yoy', 'yoy_only')

    def log_yoy_bar(self, n, c, win, cal, family, where):
        """登记「Exhibit n 在列 c 上画了一条 cal 口径的同比」，并当场查重。

        ── 为什么要有这本账 ────────────────────────────────────────────────
        改口径之前，`ex_level_yoy` 画滚动、`ex_single` 画单月，同一列两张图口径不同、
        各有各的用处。2026-09 全站统一成单月之后，只要同一列走了两条路径，页面上就会
        出现同一条同比的两个副本。原来的护栏（`_solo_bar_cols`）**只由 `ex_single`
        登记、只由 `ex_level_yoy` 查**，四条产出「水平值柱 + 次轴同比」的路径里挡住了
        一条；`ex_head_bar` / `ex_mix_total` / `ex_stock` 一个都不登记，头条那张纯同比图
        也从来不进任何账。它当时的报错文案却写得像已经挡全了，那句话一并改掉了。
        现在五条 bar_yoy 路径 + 头条 yoy_only 全部走这一个入口，登记与查重是同一次调用。

        ── 两档判据，为什么不一律硬失败 ─────────────────────────────────────
          · **同族 + 同窗口 → 硬失败。** 两张图连横轴都逐格相同，读者看到的是一字不差
            的两张，留着只会让人以为自己看漏了差别。spec 删一条就好。
          · **同族但窗口不同、或不同族 → 只告警，不停机。** 这一档的两张图确实共用
            一条数组，但各自还带着对方没有的东西：头条那张纯同比图把同比放大到整张
            画布的高度，柱图那张把它压在水平值柱旁边（不同族、窗口相同）。
            一律硬失败会把好几家页当场打挂，而那不是「重复」该付的代价。
            所以记进 `self.dup_yoy`：构建期打印一行、页尾写明哪两张是同一条线。
            ⚠️ **「同族但窗口不同」那一支从前的例子是 `tmx` 的开篇柱与同列的 mix
            合计柱**（同族、同口径，窗口一宽一窄）。2026-09 按页面所有者的指令把那一对
            并成了一张：`mix_pair` 现在先查这本账，合计柱的窗口被别处那张**真包含**
            时就不出图（见 `Page.total_drawn_wider`），所以那种「窄的完全是宽的真子集」
            已经进不到这里来。**这一支的判据与文案照旧留着**：窗口只**部分**重叠、
            或两张各自都有对方没有的月份，仍然是两张都该留的正当情形。
            ⚠️ **上面那一档（同族 + 窗口逐格相同 → 硬失败）一格都没让出去**：
            `total_drawn_wider` 对等宽显式放行、不折叠，就是为了让那种 spec 原样撞到
            这里来。底座替 spec 静默删一张图，与「spec 自己删一条」不是同一件事。

        `where` 只进报错文案（「level_yoy「XX」」这种），让人知道去 spec 的哪一段删。
        """
        if family not in self.YOY_FAMILIES:
            raise SpecError(f'log_yoy_bar 收到未知图族 {family!r} —— 这是底座代码写错，'
                            f'认得的：{self.YOY_FAMILIES}')
        rec = {'n': n, 'family': family, 'cal': cal, 'where': where,
               'win': (mlab(win[0]), mlab(win[-1]), len(win)),
               'p0': win[0], 'p1': win[-1]}
        for prev in self._yoy_bar_cols.get(c['col'], []):
            if prev['cal'] != cal:
                continue
            if prev['family'] == family and prev['win'] == rec['win']:
                raise SpecError(
                    f'{where} 的列 {c["col"]} 与 Exhibit {prev["n"]}（{prev["where"]}）'
                    f'画的是同一张图：同一列、同一口径（{cal}）、同一图族（{family}）、'
                    f'横轴逐格相同（{rec["win"][0]} 至 {rec["win"][1]}，'
                    f'{rec["win"][2]} 个月）—— 两张一字不差，请从 spec 里删掉其中一条。'
                    f'（若确实要留两张，得让它们有实质差别：换窗口、换列，'
                    f'或者把其中一列并进同单位的多列对比桶。）')
            self.dup_yoy.append({'zh': c['zh'], 'col': c['col'], 'cal': cal,
                                 'a': prev, 'b': rec})
        self._yoy_bar_cols.setdefault(c['col'], []).append(rec)

    #: 图族在页面语言里怎么叫（`log_yoy_bar` 的 YOY_FAMILIES 对应的中文）。
    YOY_FAMILY_ZH = {'bar_yoy': '水平值柱 + 次轴同比', 'yoy_only': '纯同比图'}

    def dup_yoy_zh(self):
        """`dup_yoy` 这本账 → 页尾那一段。空账返回 ''。

        写给读者的用处很具体：同一条金线出现在相隔几十号的两张图上时，读者会去找
        「这两条到底差在哪」，而答案是**不差**。与其让人自己比，不如直接说清楚
        哪两张同源、以及**这一对**里各自多给了什么 —— 逐对现算，不给一句涵盖
        所有情形的套话：窗口相同的那种根本没有「更长的历史」可言，把两种理由
        并成一句写上去，其中一半对每一对都是假的。
        """
        if not self.dup_yoy:
            return ''
        fam = self.YOY_FAMILY_ZH
        bits = []
        for d in self.dup_yoy:
            a, b = d['a'], d['b']
            if a['win'] == b['win']:
                extra = (f'横轴逐格相同（{a["win"][0]} 至 {a["win"][1]}，'
                         f'{a["win"][2]} 个月），两条线逐点相等')
            else:
                extra = (f'Exhibit {a["n"]} 画 {a["win"][0]} 至 {a["win"][1]}'
                         f'（{a["win"][2]} 个月）、Exhibit {b["n"]} 画 {b["win"][0]} 至 '
                         f'{b["win"][1]}（{b["win"][2]} 个月），重叠的那一段逐点相等')
            # ── 那留着两张的意义是什么：逐对说，说不出就不说 ──
            why = []
            lo, hi = (a, b) if a['p0'] < b['p0'] else (b, a)
            if lo['p0'] < hi['p0']:
                why.append(f'Exhibit {lo["n"]} 往左多给 {mlab(lo["p0"])} 至 '
                           f'{mlab(hi["p0"] - 1)} 共 {(hi["p0"] - lo["p0"]).n} 个月的历史')
            if a['family'] != b['family']:
                yo = a if a['family'] == 'yoy_only' else b
                bar = b if yo is a else a
                why.append(f'Exhibit {yo["n"]} 把这条同比放大到整张画布的高度、'
                           f'Exhibit {bar["n"]} 把它压在水平值柱旁边当次轴读')
            bits.append(
                f'Exhibit {a["n"]}（{fam[a["family"]]}）与 Exhibit {b["n"]}'
                f'（{fam[b["family"]]}）画的是同一列 <code>{d["col"]}</code>（{d["zh"]}）'
                f'的同一条同比，{extra}'
                + ('——两张都留着是因为' + '，而且'.join(why) if why else ''))
        return ('<b>同一条同比出现在不止一张图上。</b>' + '；'.join(bits)
                + '。<b>这不是两个读数</b>，不必去找它们的差别。'
                  '要不要并成一张由页面所有者定；并之前，这段话由构建期逐图比对现算，'
                  '删掉任一张它自动消失。')

    def audit_mom_cost(self):
        """兜底：每一张画**流量**单月同比的图都必须自己印过一段代价（§6.1 第 3 条）。

        ── 为什么必须有这一道 ────────────────────────────────────────────────
        `cost_ns` / `cost_thin_ns` 是**产图时自报**的账本：`mom_cost_zh()` 印出那一段
        才往里加一笔。而页尾 `cost_ns_zh()` 拿这本账写出「上面<b>每一张</b>的图注里
        都各自把这笔代价标了出来」—— 也就是说，**漏印一整条产图路径时，页尾照样这么
        印，而且退出码是 0**：账本空一块，那句话跟着缩成「Exhibit A、B 的图注里…」，
        读者无从知道 C、D 也该有。这正是 2026-09 之前发生过的事（`ex_single` 那条路
        一个字都不印，而这句话当时是无条件写死的）。

        同门的 `build/cboe.py`（`_cost_missing` / `_cost_extra`）与 `build/cme.py`
        （`_COST_MISSING` / `_COST_EXTRA`）早就把这件事做成了硬失败，而且**两个方向
        都查**。本底座补齐，判据形状与它们一致 —— 否则「cboe 会响、single 不会响」
        本身就是下一个人踩的坑。

        ── 两侧各是什么 ─────────────────────────────────────────────────────
          · 欠账方（该印）= 口径账本 `yoy_log` 里 `cal == 'mom'` 的图号。这一档**只有
            流量列**会进：比率列记 `mom_pp` / `mom_money`、存量列记 `stock`、热力矩阵
            记 `heat*`，四条产图路径在调 `log_yoy()` 之前就按 `col_is_ratio()` /
            `c['stock']` 分好了档。§6.1 第 3 条的范围正是流量，存量与比率不欠这笔账
            （它们没有第二种合法口径可作对照），所以不能把它们算进分子。
          · 已付方 = `cost_ns`（真印了实测三样）∪ `cost_thin_ns`（可比月不足
            `MOM_COST_MIN`，照实写了「量不出来」——契约明说那也算付）。

        两个方向都要对：漏印会让页尾那句话变假；反过来账本里多一个图号，
        `cost_ns_zh()` 会点名一张**并没有画流量单月同比**的图，同样是替不存在的东西
        背书。所以这里不是「子集检查」，是**相等**检查。
        """
        owed = {r['n'] for r in self.yoy_log if r['cal'] == 'mom'}
        paid = self.cost_ns | self.cost_thin_ns
        miss = sorted(owed - paid)
        if miss:
            raise SpecError(
                f'[{self.ticker}] 这些图画了**流量**单月同比却没有逐图代价段：'
                f'Exhibit {miss} —— CONTRACT §6.1 第 3 条要求每一张都用**它自己那条'
                f'序列、自己那段窗口**实测，把逐月标准差、相邻月最大跳变（带月份）与'
                f'两种口径符号相反的月份数印进**本图的**图注；「逐图」是字面意思，'
                f'页尾那段顶替不了。'
                f'（本页记了流量单月同比的图号：{sorted(owed)}；'
                f'账本里已付的：{sorted(paid)}。）'
                f'改法：那条产图路径上补一句 '
                f'`self.mom_cost_zh(n, c, win)`（或 `brief=True` 的一行式）。'
                f'⚠️ 不要靠删掉页尾那句话绕过去 —— 欠的是图注，不是页尾。')
        extra = sorted(paid - owed)
        if extra:
            raise SpecError(
                f'[{self.ticker}] 这些图号进了逐图代价账本，却不在「画了流量单月同比」'
                f'的名单里：Exhibit {extra}（本页真画了流量单月同比的是 '
                f'{sorted(owed)}）—— 页尾那段点名现读这本账，多一个图号就等于替一张'
                f'没画这条线的图背书。多半是某条路径在 `rhs is None`（整条同比都算不'
                f'出来、图退回 bars_labeled）时仍然调了 `mom_cost_zh()`：'
                f'没有线就没有这笔债，把那次调用挪进 `if rhs:` 里。')

    # ── 近零基数（CONTRACT §6.1 第 5 条）：不撤线，改成截轴 + 图注警告 ──────────
    #
    # 条文写的是「近零基数的序列不画同比，画水平值」。页面所有者 2026-09 拍板改成
    # **保留同比线**（他要的就是每家都有单月同比折线），代价用两样东西付：
    #   · **截轴**把那种几千个百分点的读数钳住 —— 不钳的话整条线被一个点压成零线上的
    #     一道横杠（`db1` Ex29 的 +1,958.6% 与 `jpx` Ex14 的 +9,865% 就是这样）；
    #   · **图注警告**明写哪几个月的基数近零、这条线在那一段读的是分母不是量。
    # 截轴走引擎既有约定：超界的点钳到轴顶、画空心红圈、真值竖排标出，**一个点不删**
    #（`assets/charts.js` 的 polyline 里 `_rhsCap` 那一支；右轴的字段名是
    # `ex.yoy.ymax`，左轴才是 `ycap`/`yfloor`）。
    #
    # ⚠️ **比率列不走这一套。** 百分点差（以及「分子是钱」的差）没有分母，近零基期
    # 放大不了它 —— `yoy_line()` 的近零掩码同样只对非比率生效，理由那里写着。
    #
    # ⚠️ **近零那几个月本来就没画**：`yoy_line()` 把基期低于阈值的月份一律写成 null。
    # 所以警告文案不能说「那几个月的读数不可信」（读者在图上根本找不到它们），
    # 要说的是「那一段的基期低到这个地步，紧接着画出来的读数是分母在动」——
    # 底下的文案因此报的是**画出来的那个最大读数和它自己的基期**，全部现算。

    #: 截轴上界取「本图画出来的同比读数」的这个百分位。取 P90 而不是拍一个整数：
    #: 保证被钳住的点不超过一成，其余九成的形状原样留在轴内。
    NZ_CAP_Q = 90
    #: 但上界不低于这个数 —— 翻一倍是正常的高增长，不该被当成离群值截掉。
    NZ_CAP_FLOOR = 100.0

    # ── 尖刺截轴（`spike_cap()`）的两个常量。放在这里是因为它与上面那两个是同一件事的
    #    另一半：近零基数治的是**同比线**被基数效应顶出去，尖刺治的是**水平值折线**被
    #    一两个一次性大额顶出去。两处共用引擎同一套 `ycap` + `cap_note` 约定。 ──
    #
    #: Tukey **极端**离群栅栏的倍数（Q3 + k×IQR）。取 6.0 与 `build/lpla.py` 的 `CAP_K`
    #: 同一个数、同一条判据 —— 全仓治尖刺只有这一把尺子，两处取不同的 k 等于同一个页面
    #: 集合里有两种「离群」的定义。
    #:
    #: 实测的 k 敏感性（2026-09 的 `data/asx.js`，两张命中图各扫 k=3…12，报越界点数）：
    #:   · 上市融资旧口径那张：k 从 3 一路到 12 都只划出 **1** 个点（2022-02），
    #:     结论对 k 完全不敏感；
    #:   · 二次融资那张：k=5–6 划出 **4** 个点（2022-02 与 2025-02 各两条序列），
    #:     k=4 变 6 个（把 2022-06 的 19,499 也划进去 —— 那是日常高点，不该截），
    #:     k=7 变 3 个、k≥8 变 2 个（2025-02 的换股对价回到栅栏内，上界随之放宽一档）。
    #:   所以 k 在这里**不是**一个「取多少都一样」的数：6 是「刚好只圈住两桩大额换股并购、
    #:   一个日常高点都不误伤」的那一档。**改 k 之前先把上面这串数重跑一遍。**
    #: 图注里那句「Q3 + k×IQR」引这个常量而不写字面 6：调了 k 而图注还写 6，
    #: 就又是一句会过期的假话。
    #:
    #: ⚠️ **需求原话存这里**（2026-09，/asx/ 页面所有者）：
    #:     「ex19/20 部分点数字太高在图形上显示尖刺，处理下」
    #: ——「处理」两个字没有指定手段，是本底座选的截轴（本仓治尖刺的唯一既有手段：
    #: 引擎没有对数刻度，而平滑 / 换切法撞判例第 1、5 条）。下一个人要判「这段代码
    #: 答的是不是他问的问题」，判据是这句原话，不是下面那串 k 的敏感性数字 ——
    #: 那串数是**方法**的凭据，不是**需求**的凭据。
    SPIKE_K = 6.0
    #: 触发门：**日常上沿**（栅栏内最大值）在「不截轴时的那根轴」上所占的比例。
    #: 低于这个门才截 —— 高于它说明尖刺并没有把其余点压扁，截了只是白截别人的图。
    #:
    #: 0.35 不是拍的，是从实测空档里挑的。把当时全站 `data/*.js` 里 **61 张**
    #: `lines_endlabels` 的这个比例全量出来（判据与下面 `spike_cap()` 里那段量程复算
    #: 逐字同源），过得了「栅栏外真有点」这一关的一共 6 张，比例从小到大：
    #:     0.188 asx 二次融资（3 条序列）/ 0.223 asx 上市融资旧口径（2 条序列）
    #:     ── 空档 ──
    #:     0.526 jpx 迷你化（大型合约 vs mini）/ 0.567 db1 FESX / OESX
    #:     0.659 exchanges12 的恒定基准名义额
    #:     0.860 lpla 渠道 NNA（**已经**由 build/lpla.py 的 cap_pack 截过轴，比例是截后的）
    #:     其余 55 张一个栅栏外的点都没有（比例 ≥ 0.847），本来也进不到这一步。
    #: 0.223 与 0.526 之间是空的，阈值放在这段空档里对数据抖动最不敏感；取中点 0.35。
    #: **这道门是必须的**：没有它，同一条规则会连带截掉 jpx / db1 那两张 ——
    #: 它们的尖峰只把日常上沿压到轴的一半略高，那是形状本身，不是尖刺。
    #: （exchanges12 / lpla 两张由各自的 build 脚本生成、根本走不到本底座，
    #:   但比例照样量给出来 —— 判据要能在全站数据上重跑，不能只在自己这 9 页上成立。）
    #: 写法照 `assets/charts.js` 的 `ALIGN_WASTE_MAX`（阈值放实测空档里，并把那批数留在注释里）。
    SPIKE_HEAD = 0.35

    def near_zero_guard(self, n, c, win, obj, field='ymax', vals=None):
        """近零基数的处理：就地给截轴上界，返回那段图注警告（不命中返回 ''）。

        `obj` / `field` 指向**放截轴字段的那个 dict**，两种图型不同：
          · gs_bar 的同比在**右轴** → `obj` 是 `ex['yoy']`、`field='ymax'`；
          · `ex_yoy` 的同比自己占**主轴** → `obj` 是 `ex`、`field='ycap'`。
        `vals` = 这条同比线画出来的那串值（不给就取 `obj['values']`）——
        `ex_yoy` 那一路的值在 `ex['groups'][0]` 里，与放字段的地方不是同一个 dict。

        判据、文案与账本三处共用一份实现 —— 分两份写的下场是某一条产图路径漏了警告，
        而没有任何东西会响。
        """
        if self.is_ratio(c):
            return ''
        s_ = self.ser(c)
        s_ = s_.set_axis([mlab(p) for p in s_.index])
        nz = ycal.near_zero_base(s_, win=[mlab(p) for p in win])
        if not nz['flag']:
            return ''
        if vals is None:
            vals = (obj or {}).get('values') or []
        fin = [(mlab(p), float(v)) for p, v in zip(win, vals)
               if v is not None and np.isfinite(float(v))]
        cap = None
        if fin:
            q = float(np.percentile([v for _, v in fin], self.NZ_CAP_Q))
            cand = max(self.NZ_CAP_FLOOR, float(nice_max(q)))
            # ⚠️ **截轴上界不许低于末点读数** —— 引擎的末点标签用的是**未钳位的原值**：
            # `assets/charts.js` 里 `txt(g, Xc(jy) + 5, Y2(vy[jy]) + 9.5, …)`，
            # 而 `Y2(v) = M.t + ph − ((v − r0)/(r1 − r0))·ph`，v > r1 时算出来在画布**上方**。
            # 实测（2026-09-03，本轮新加截轴之后）：jpx Ex14 末点 +1076.4% 而 cap 取到 400，
            # 那个「1076%」被画到 y = −266.9，而 viewBox 只有 349.6 高 —— 整个标签在画布外。
            # 超界的**历史**点不受影响：它们走 polyline 的钳位分支，画成红色空心圈并把真值
            # 竖排标出（同一张图上 y = 40.5 那个「1076%」就是它，可见且正确）。
            # 出问题的只有末点那一个标签，因为它不走钳位分支。
            #
            # 为什么不去改引擎：`assets/charts.js` 同时服务 34 页，改一行要重新验收全站
            # （文件头那条「引擎不许改」）。生成端把上界抬到不低于末点，代价是这两张图的
            # cap 变松（jpx Ex14 400 → 1100、enx Ex26 1000 → 1400），但**历史极值仍被钳住**
            # （jpx 最大 9865、enx 最大 2156），近零基数那个病照样治得住，而最新那个读数
            # 是整张图上最该被看见的数字，不能为了压平历史把它推到画布外。
            end_v = fin[-1][1]
            if end_v > cand:
                cand = max(self.NZ_CAP_FLOOR, float(nice_max(end_v)))
            if max(v for _, v in fin) > cand:
                cap = cand
                obj[field] = cap
        # 画出来的那个最大读数 + 它自己的基期 —— 这才是读者在图上看得见的东西
        peak = max(fin, key=lambda t: abs(t[1])) if fin else None
        peak_zh = ''
        if peak:
            base = float(s_.shift(ycal.LAG).get(peak[0], np.nan))
            if np.isfinite(base) and nz['scale']:
                peak_zh = (f'本图画出来的最极端的一点是 {peak[0]} 的 {peak[1]:+.0f}%，'
                           f'它的基期（{peak[0]} 的去年同月）是 '
                           f'{fmt_val(base, c["fmt"])} {c["unit"]}，'
                           f'只有本序列全历史中位数 {fmt_val(nz["scale"], c["fmt"])} 的 '
                           f'{abs(base) / nz["scale"]:.0%}。')
        self.nz_ns.append({'n': n, 'col': c['col'], 'zh': c['zh'],
                           'share': nz['share'], 'k': len(nz['months']),
                           'n_base': nz['n_base'], 'cap': cap,
                           'peak': peak, 'months': list(nz['months'])})
        return (
            f'<b>⚠️ 近零基数：这条同比线有一整段读的是分母，不是量。</b>'
            f'判据是 CONTRACT §6.1 第 5 条 —— 基期的绝对值低于本序列<b>全历史</b>'
            f'|值| 中位数（{fmt_val(nz["scale"], c["fmt"])} {c["unit"]}）的 '
            f'{ycal.NEAR_ZERO_BASE_FRAC:.0%}，即低于 {fmt_val(nz["cut"], c["fmt"])} '
            f'{c["unit"]}，就记一个近零基数月；本图窗口内<b>当月与去年同月都有值</b>的 '
            f'{nz["n_base"]} 个月里占了 <b>{nz["share"]:.1%}</b>'
            f'（{len(nz["months"])} 个月：{_month_runs_zh(nz["months"])}），'
            f'超过条文里 1/12 的线。'
            f'这 {len(nz["months"])} 个月的同比<b>在本图上是空的</b> —— '
            f'底座对基期低于阈值的月份一律不画那一点（<code>yoy_line()</code> 的近零掩码）。'
            + peak_zh
            + (f'因此给右轴设了<b>截轴上界 +{cap:.0f}%</b>（引擎随后把轴顶对齐到整刻度，'
               f'画出来的轴顶可能略高于这个数）：判据是「本图画出来的同比读数的 '
               f'P{self.NZ_CAP_Q} 分位向上取整到整刻度，且不低于 '
               f'+{self.NZ_CAP_FLOOR:.0f}%」—— 前一半保证被钳住的点不超过一成、'
               f'后一半保证「翻一倍」这种正常的高增长不会被当成离群值截掉。'
               f'超界的点<b>一个都没删</b>：按引擎既有约定钳到轴顶、画空心红圈、'
               f'把真值竖排标在旁边（<code>assets/charts.js</code> 的截轴规矩）。'
               if cap else
               '本图窗口内的读数没有超出正常量程，所以没有截轴。')
            + '<b>读法：这条线在低基数那几年只能看方向，不能看幅度</b>；'
              '幅度请读同一张图上的深蓝柱（水平值）。')

    def _spike_axis(self, ex, a):
        """不截轴时引擎给这张图的 `(y0, y1, 轴顶那句话)`。**逐行对着 charts.js 写。**

        两种 kind 走引擎**两条不同**的量程分支，占比判据（下面第 ② 步）拿哪一条都不能
        将就 —— 拿错了算出来的「日常上沿占轴多少」是个假数，那道门就形同虚设。
          · `lines_endlabels`（charts.js:939）：`y0 = mn − 极差×0.20; y1 = mx + 极差×0.18`
          · `lines`（charts.js:945-969）：`zero_base` 时 `y0 = 0`（非负段）、`y1 = mx×1.16`；
            否则 `y0 = dmn − 极差×0.05; y1 = dmx + 极差×0.05`（`incZero` 只由 `zero_line`
            触发 —— 本底座的 `lines` 不带柱、也不设 `zero_line`，但照抄不省）。
        随后两条都过 `charts.js:972`：`yfloor` 覆盖 y0（`ycap` 覆盖 y1，那是截完的事）。

        同一条式子在本仓另有三份副本：`build/axisfmt.py` 的 `_left_range`、
        `build/mrbase.py` 的 `align_sim`、`tools/align_replica.py` 的 `left_range`。
        **改这条式子要四处一起改**，否则这里算出来的占比与页面上真画的不是同一根轴。
        """
        kind = ex.get('kind')
        mn, mx = float(a.min()), float(a.max())
        if kind == 'lines_endlabels':
            r2 = (mx - mn) or 1.0
            y0, y1 = mn - r2 * 0.20, mx + r2 * 0.18
            top = '「最大值 + 极差×18%」'
        elif ex.get('zero_base'):
            rz = (mx - mn) or abs(mx) or 1.0
            y0 = mn - rz * 0.08 if mn < 0 else 0.0
            y1 = mx * 1.16 if mx > 0 else rz * 0.08
            top = '「最大值×1.16」（本图型开了 <code>zero_base</code>，下界钉在 0）'
        else:
            dmn = min(mn, 0.0) if ex.get('zero_line') else mn
            dmx = max(mx, 0.0) if ex.get('zero_line') else mx
            rg = (dmx - dmn) or 1.0
            y0, y1 = dmn - rg * 0.05, dmx + rg * 0.05
            top = '「最大值 + 极差×5%」'
        if ex.get('yfloor') is not None:
            y0 = float(ex['yfloor'])
        return y0, y1, top

    #: 端点标签与绘图区顶边之间必须留够的像素（按 kind 分）。**判据全在引擎里**：
    #: `spreadY()` 的顶边兜底门是 `lo = M.t + 7`（charts.js:1293），越过它整列标签就被
    #: 重排成一摞，所以每种 kind 的要求 = 7 − 该 kind 端点标签相对 `Y(值)` 的落笔偏移。
    #:   · `lines_endlabels`：两端标签落在 `Y(值) + 3.2`（charts.js:1517/1518）⇒ 7 − 3.2；
    #:   · `lines`：末点标签落在 `Y(值) − 7`（charts.js:1354）⇒ 7 + 7。
    SPIKE_HEAD_PX = {'lines_endlabels': 7 - 3.2, 'lines': 7 + 7}

    def spike_cap(self, n, ex, cols):
        """尖刺截轴：一两个一次性大额把其余读数压成贴地一条线时，截轴 + 返回那段图注。

        **只由声明了 `groups[].spike_cap: True` 的组调用**（见模块头 GROUP_KEYS 那一段）。
        命中就地写 `ex['ycap']` 与 `ex['cap_note']`、记一笔 `self.cap_ns`，返回图注；
        不命中返回 `''` —— **不截，也不写那行字**（理由见下面「cap_note 的坑」）。

        ── 为什么不是对数轴 ────────────────────────────────────────────────────
        `assets/charts.js` 全文没有对数刻度，而引擎**不许改**
        （`docs/CHART_KINDS.md` 文件头：它同时服务几十张已上线的页，改一行要重新验收全站）。
        线性量程逻辑还另有三份 Python 副本（`build/axisfmt.py` 的 `fix_all`、
        `build/mrbase.py` 的 `align_sim`、`tools/align_replica.py`），换刻度族是四处一起动
        的事。所以这条路封死，本仓治尖刺的唯一既有手段就是 `ycap` + `cap_note`：
        **截轴不删点** —— 超界的点钳到轴顶、画成空心红圈、真值红色竖排标出。

        ── 判据（四步，全部现算，一个常数都不手挑）──────────────────────────────
        ① 把本图**全部序列**的有限值合在一起做 Tukey 极端离群栅栏 `Q3 + SPIKE_K×IQR`。
           合在一起判是因为它们本来就画在**同一根轴**上：分序列各判各的，等于同一根轴上
           有两套「离群」的定义。栅栏外一个点都没有 → 返回 ''。
           **只判上界**：本图型的尖刺是被顶上去的，下界那一侧由 `yfloor` 管
           （`ex_lines()` 里非负组已经把它钉在 0）。真出现向下的极端离群时该做的是给
           `yfloor` 并单独写图注，那是另一件事，别在这里顺手做。
        ② 复算「不截轴时的轴顶」（`_spike_axis()`，按 kind 取引擎对应的那条量程分支），
           看**日常上沿**（栅栏内最大值）在那根轴上占多少 —— ≥ `SPIKE_HEAD` 就返回 ''
           （那种图的尖峰并没有把其余点压扁，截了是白截）。
        ③ 上界 = `nice_max(栅栏内最大值)`，取一个干净整刻度（与 `stacked_dual` 右轴同一个
           取整器，那边的注释记着为什么不能写 `int()`）。
        ④ 端点护栏（见下）。抬完若已经没有越界点 → 返回 ''，不截。

        ── 端点护栏：判据是**像素**，不是「有没有越界」 ────────────────────────────
        `near_zero_guard()` 里那段「截轴上界不许低于末点读数」同一条理由，但那边只护末点、
        判的也只是越不越界。这里两处都不够：

        ① **护首末两端**。`lines_endlabels` 两端都是无条件按 `Y(值)` 落笔的
           （`LE.push({y: Y(sr.values[0]) + 3.2 …})` / `RE.push(… values[n-1] …)`，
           charts.js:1517/1518），既不钳也不跳过 —— 与 `kind:'lines'` 的
           `clampY(v) !== v → continue`、`bars_labeled` 的 `yl !== vals[i] → continue`
           正相反。（`lines` 那一支的末点标签虽然会跳过被截的点，但**没被截的**那个最高
           末点照样能顶进兜底区，所以两种 kind 都要护，只是像素余量不同。）

        ② **判据是「离顶边还有几个像素」，不是「越没越界」。**
           `lifted = end_hi > cap` 这种写法留了一条盲带：引擎真正的失败门槛是
           `spreadY()` 的 `lo = M.t + 7`（charts.js:1293），而标签落笔在 `Y(值) + 3.2`，
           所以要求的是 `Y(值) ≥ M.t + (7 − 3.2)`。末点只要落在轴顶下方不到 3.8px，
           标签就跌进 `lo` 之下，触发「上下都顶满就从上边界顺排」的兜底：**整列端点读数
           被重排成一摞**，与各自的线对不上号，而且没有任何东西报错。
           换算成读数：半栏（FS=1.45，ph=236.5）cap 至少要比末点高 1.633%，
           通栏（FS=1.70，ph=235.0）1.644%。实算四例全部落进盲带：
           末点 149/cap 150、396→400、300→300、250→250，四例的最大错位 148–195px。
           对数均匀抽 4×10⁵ 次，`nice_max` 抬完仍落进盲带的占 **6.37%**；
           末点本身正好是整刻度时（150 / 250 / 300 / 400 …）**必然**触发。
           所以护栏改成解一次像素方程：
               `need = y0 + (end_hi − y0) / (1 − HEAD_PX / ph)`，`need > cap` 才算触发。
           `ph` 取 FS 全区间的**最小值**（`_plot_h_min()`，`lines_endlabels` 是 234.81）
           —— ph 越小，同样的像素余量占轴的比例越大，取小就是取最保守的那一档。

        代价与 `near_zero_guard()` 那边一样：护栏一抬，上界就变松、历史尖刺压得没那么平。
        但两端读数是这张图上最该被看见的两个数字，不能为了压平历史把它们推到画布外。

        ── ⚠️ `cap_note` 的坑 ────────────────────────────────────────────────────
        引擎的截轴开关是 `capOn = ex.ycap != null || ex.yfloor != null || _rhsCap != null`，
        **`yfloor` 也算**。而本底座几乎每张 `lines_endlabels` 都带 `yfloor: 0`（那是归零，
        不是截轴：没有点落在 0 以下）。所以 `cap_note` 只能与 `ycap` **同时**写 ——
        无条件写的话，全站每一张这种图的图顶都会印出「axis capped」这句假话。
        `build/mrbase.py` 记过同一个坑（「yfloor 不等于截轴，要看有没有点真的被它挡住」），
        `build/lpla.py` 的 `cap_pack()` 是同一条：没有越界点就不截、也不写那行字。
        """
        kind = ex.get('kind')
        if kind not in self.SPIKE_HEAD_PX:
            # 这一支是**真判据**，不是装饰：`ex_lines()` 只会产出 lines_endlabels / lines
            # 两种，第三种 kind 出现在这里就意味着有人从别的路径调了它，而那条路径的
            # 量程式（`_spike_axis()`）与端点落笔偏移（`SPIKE_HEAD_PX`）这里都没有。
            # 缺了这两样算出来的占比与护栏都是假数，静默不截等于让开关白声明。
            raise SpecError(
                f'[{self.ticker}] Exhibit {n} 的 kind 是 {kind!r}，'
                f'而 spike_cap() 只复刻了 {sorted(self.SPIKE_HEAD_PX)} 两种图型的量程式与'
                f'端点落笔偏移 —— 别的图型请先把这两样从 assets/charts.js 补进来再调它。')

        xl = ex.get('xlabels') or []
        pts = [(i, s['name'], float(v))
               for s in (ex.get('series') or [])
               for i, v in enumerate(s.get('values') or [])
               if v is not None and np.isfinite(float(v))]
        if len(pts) < 8:            # 样本太少，四分位没有意义（同 lpla.cap_bounds）
            return ''
        a = np.array([v for _, _, v in pts], dtype=float)
        q1, q3 = (float(x) for x in np.percentile(a, [25, 75]))
        iqr = q3 - q1
        fence = q3 + self.SPIKE_K * iqr
        inb = a[a <= fence]
        if inb.size == 0 or not (a > fence).any():
            return ''
        inb_max = float(inb.max())

        # ── ② 不截轴时的轴顶（按 kind 取引擎对应的量程分支，见 `_spike_axis()`）──
        mx = float(a.max())
        y0, y1, top_zh = self._spike_axis(ex, a)
        if not (y1 > y0):
            return ''
        head = (inb_max - y0) / (y1 - y0)
        if head >= self.SPIKE_HEAD:
            return ''

        # ── ③ 上界 + ④ 端点护栏 ──
        # `cap0` 留着给图注：那句「上界取栅栏内最大值向上取整，得 X」报的是**护栏抬之前**
        # 那个数。护栏触发时直接印抬完的 cap，读者会看到「取整得 400；再经护栏抬到 400」，
        # 一句自相矛盾的话（护栏没抬触发不了，抬了两个数就不该相同）。
        cap = cap0 = float(nice_max(inb_max))
        ends = []
        for s in ex['series']:
            fv = [float(v) for v in (s.get('values') or [])
                  if v is not None and np.isfinite(float(v))]
            if not fv:
                continue
            # `lines_endlabels` 首末两端都标（charts.js:1517/1518）；
            # `lines` 的 `end_label` 只标**末点**（charts.js:1350 `lastFinite`），
            # 首点在那一支上根本不落笔，把它算进护栏只会白白抬高上界。
            ends += ([(s['name'], fv[0])] if kind == 'lines_endlabels' else []) \
                + [(s['name'], fv[-1])]
        end_hi = max([v for _, v in ends], default=float('-inf'))
        # 护栏解的是像素方程，不是「越没越界」——盲带那 6.37% 的理由见 docstring ②。
        # ph 取 FS 全区间最小值（最保守的那一档）；`lines` 的画布高由 `ex['height']` 定。
        head_px = self.SPIKE_HEAD_PX[kind]
        ph_min = _plot_h_min(kind, height=ex.get('height'))
        need = y0 + (end_hi - y0) / (1 - head_px / ph_min)
        lifted = bool(np.isfinite(need) and need > cap)
        if lifted:
            cap = float(nice_max(need))
        # 按**窗口下标**排，不按月份标签的字典序 —— 'Feb-22' < 'Jan-16' 是字母序，
        # 印出来的清单会不按时间走，读者对着横轴逐个核对时要来回跳。
        over = [(xl[i] if i < len(xl) else str(i), nm, v)
                for i, nm, v in sorted((p for p in pts if p[2] > cap),
                                       key=lambda p: (p[0], p[1]))]
        if not over:
            # 护栏把上界抬到所有点之上了 —— 那就没有尖刺可治，别留一个只写着
            # 「axis capped」却一个红圈都没有的轴顶。
            return ''

        ex['ycap'] = cap
        ex['cap_note'] = f'axis capped at {fmt_val(cap, cols[0]["fmt"])} — true values shown in red'

        # ── 图注要报的几何：绘图区高 ph ──
        # 全部走 `_plot_h()`（`assets/charts.js` 的逐行复刻，行号写在那里），不再手写常数。
        #
        # ⚠️ 这里报的是**半栏卡（FS = 1.45）**的真值，不是「基线字号 FS = 1」。
        #    引擎的字号是按卡片宽度在 [1.45, 1.70] 之间插值的（charts.js:126），
        #    **FS = 1 这一档全站根本不存在**：半栏真值是 `M.t = 43.5 / ph = 236.5`，
        #    而 `268 − 30 = 238` 那种算法系统性偏约 0.6%，报的是一根不存在的轴。
        #    通栏（FS = 1.70）另有一档，一并报出来，免得读者拿半栏的数去量通栏的图。
        # 截轴开关**含 yfloor**：本图早就有 yfloor 时，加 ycap 并不会改变上边距。
        h_ex = ex.get('height')
        capped_before = ex.get('yfloor') is not None
        ph0 = _plot_h(kind, FS_MIN, capped_before, h_ex)     # 不截轴时的绘图区高
        ph1 = _plot_h(kind, FS_MIN, True, h_ex)              # 截轴后（半栏）
        ph1w = _plot_h(kind, FS_MAX, True, h_ex)             # 截轴后（通栏）
        med = float(np.median(a))
        px0 = (med - y0) / (y1 - y0) * ph0
        px1 = (med - y0) / (cap - y0) * ph1

        fmt, unit = cols[0]['fmt'], cols[0]['unit']

        def F(v):
            return fmt_val(float(v), fmt)

        # 栅栏那三个数（Q3 / IQR / 栅栏）单独一个格式器：它们是**现算的统计量**，不是官方
        # 披露的读数，用列自己的 fmt 印会把「4,535 + 6×3,752 = 27,050」印成一道算错的算式
        #（f0c 把 3,752.5 抹成 3,752，读者按显示值一乘就对不上）。位数按量级取，
        # 保证印出来的加法自己成立。
        _ref = max(abs(q3), abs(iqr), 1e-12)
        _sd = max(1, min(6, 3 - int(np.floor(np.log10(_ref)))))

        def S(v):
            return f'{float(v):,.{_sd}f}'

        # 各序列自己的中位数 —— 底下那句「截轴治不了贴地」要拿最小与最大的两条对比。
        smed = sorted(((s['name'], float(np.median([float(v) for v in s['values']
                                                    if v is not None and np.isfinite(float(v))])))
                       for s in ex['series']
                       if any(v is not None and np.isfinite(float(v)) for v in s['values'])),
                      key=lambda t: t[1])
        months = list(dict.fromkeys(m for m, _, _ in over))
        end_zh = '两端' if kind == 'lines_endlabels' else '末点'
        lab_zh = ('两端标签是<b>无条件</b>按读数落笔的（既不钳到轴顶、也不跳过）'
                  if kind == 'lines_endlabels' else
                  '末点标签按读数落笔（被截的那个会跳过、真值改走红字竖排，'
                  '但没被截的最高那个照样顶得进顶边）')
        # ⚠️ 这本账记的是**官方原始量级**（本方法跑在 `chartscale.fix_all()` 之前）。
        # 它有两个下游，两个下游要的量级不一样：
        #   · `build()` 里那行维护者日志 —— 要原始量级，那是拿去跟官方披露对账的；
        #   · 页尾 `cap_zh()` —— 要**页面上真画出来的**那个量级，所以它按图号回读最终
        #     payload 的 `ycap`/`ylab`/`fmt`，不读这里的 `cap`/`unit`/`fmt`（见那边的注释）。
        self.cap_ns.append({'n': n, 'cap': cap, 'fence': fence, 'head': head,
                            'over': over, 'months': months, 'unit': unit, 'fmt': fmt,
                            'y1_uncapped': y1, 'inb_max': inb_max, 'lifted': lifted})
        return (
            f'<b>⚠️ 已截轴：纵轴上界截在 {F(cap)} {unit}，'
            f'{len(over)} 个越界读数钳在轴顶。</b>'
            f'不截的话轴顶要一路画到 <b>{F(y1)} {unit}</b>（本图型的轴顶是'
            f'{top_zh}，而极差被最大的那一点 '
            f'{F(mx)} 撑开），其余 {len(a) - len(over)} 个点全被压进画布最底下的 '
            f'<b>{head:.1%}</b>：本图全部读数的中位数 {F(med)} {unit} 在那根轴上离轴底只有 '
            f'{px0:.1f}px，截轴后抬到 <b>{px1:.1f}px</b>'
            f'（绘图区高 {ph1:g}px —— 半栏卡的字号档 FS=1.45；'
            f'通栏卡 FS=1.70 时是 {ph1w:g}px）。'
            f'<b>截轴不删点</b> —— 越界的点按引擎既有约定钳到轴顶、画成空心红圈、'
            f'真值红色竖排标在旁边（<code>assets/charts.js</code> 的截轴规矩），'
            f'一个点没删、一个数没改。越界的是 '
            + '、'.join(f'{m}「{nm}」{F(v)}' for m, nm, v in over) + '。'
            + f'判据现算：本图 {len(ex["series"])} 条序列在窗口内的 {len(a)} 个有限值合在'
              f'同一根轴上做 Tukey 极端离群栅栏 Q3 + {self.SPIKE_K:g}×IQR = '
              f'{S(q3)} + {self.SPIKE_K:g}×{S(iqr)} = <b>{S(fence)} {unit}</b>，'
              f'栅栏之外算尖刺；上界取栅栏内最大值 {F(inb_max)} 向上取整到整刻度，'
              f'得 {F(cap0)}'
            + (f'；再经端点护栏抬到 {F(cap)} —— 本图{end_zh}读数最高 {F(end_hi)}，'
               f'而{lab_zh}，上界与它之间至少要留出全轴的 '
               f'{head_px / ph_min:.2%}（= {head_px:g}px ÷ 绘图区高 {ph_min:g}px），'
               f'不然那一列标签会被挤进画布顶边、整列重排成一摞'
               if lifted else
               f'；端点护栏未触发（本图{end_zh}读数最高 {F(end_hi)}，'
               f'它离上界的余量本来就在全轴的 {head_px / ph_min:.2%} 以上）')
            + '。'
            + ('<b>代价照实写</b>：'
               + (f'被截的那一个读数（{over[0][0]}）在图上钳在轴顶，它比轴顶高出多少'
                  f'<b>在图上读不出来</b>，只能读旁边那个红字真值。'
                  if len(over) == 1 else
                  f'被截的 {len(over)} 个读数（落在 {len(months)} 个月：'
                  f'{"、".join(months)}）在图上是压平在轴顶的一段，'
                  f'它们彼此之间的高低<b>在图上读不出来</b>，'
                  f'只能读旁边那几个红字真值。'))
            + (f'而且截轴治不了「{smed[0][0]}」本身贴地这件事 —— 它的中位数 '
               f'{F(smed[0][1])} {unit} 只有「{smed[-1][0]}」中位数 {F(smed[-1][1])} '
               f'{unit} 的 {smed[0][1] / smed[-1][1]:.1%}，那是<b>真实的量级差</b>，'
               f'不是尖刺，换什么轴都压不出来。'
               if len(smed) > 1 and smed[-1][1] else ''))

    def _cap_final(self, ex, z):
        """一笔截轴账 → **最终 payload 上**那张图的 (上界, 单位, 格式器, 越界清单)。

        为什么不直接读 `self.cap_ns`：`spike_cap()` 跑在 `chartscale.fix_all()` **之前**，
        而 `chartscale` 会把 `ycap` 连同全部数值一起除掉（它的 `_SCALARS`）。9 位数的图
        缩完之后，账本里那个 25,000 与轴上真画出来的 0.025 差着一个缩放倍数 —— 拿账本的
        数去写页尾，读者对着图上的轴顶怎么读都对不上。所以这里一律回读最终 payload。

        `ylab` 而不是列的 `unit`：`chartscale` 缩完会把量级词写进 `ylab`
        （`A$mn` → `A$mn（百万）`），那正是读者在轴上看到的那行字。
        """
        e = ex.get(z['n']) if isinstance(ex, dict) else None
        if not isinstance(e, dict) or e.get('ycap') is None:
            # 图没了 / 上界被别人抹了 —— 页尾照旧口径讲一遍好过讲一句没人核得动的话。
            return z['cap'], z['unit'], z['fmt'], z['over']
        cap = float(e['ycap'])
        xl = e.get('xlabels') or []
        over = [(xl[i] if i < len(xl) else str(i), s['name'], float(v))
                for i, s, v in sorted(
                    ((i, s, v) for s in (e.get('series') or [])
                     for i, v in enumerate(s.get('values') or [])
                     if v is not None and np.isfinite(float(v)) and float(v) > cap),
                    key=lambda t: (t[0], t[1]['name']))]
        if len(over) != len(z['over']):
            # 缩放是同一个倍数除下来的，`v > ycap` 这个不等式必须原样成立。数不上
            # 就说明中间有一步单独动了 ycap 或数值 —— 页尾那句「N 个读数越界」会变成
            # 一个跟图上红圈数对不上的数，宁可当场停机。
            raise SpecError(
                f'[{self.ticker}] Exhibit {z["n"]} 的越界点数在最终 payload 上是 '
                f'{len(over)}，而 spike_cap() 截轴时数出来的是 {len(z["over"])} —— '
                f'`ycap` 与序列数值之间被人分开动过，页尾与图上的红圈会对不上。')
        return cap, (e.get('ylab') or z['unit']), (e.get('fmt') or z['fmt']), over

    def recap_notes(self, ex):
        """`chartscale` 缩完之后，按**缩放后的** `ycap` + 新 `fmt` 重写 `cap_note`。

        ⚠️ `cap_note` 不是图注，是**画在绘图区里的图元**（`charts.js` 的 `capLabel` 之外
        那行图顶斜体小字）。`chartscale` 往 `note` 末尾追加的那句免责
        「本图注文字、汇总表与末尾核对表仍是官方原始量级」**覆盖不到它** ——
        它就画在被缩放过的那根轴旁边。不重写的后果是同一张画布上并存三个量级：
        轴顶读 25、图顶斜体小字写 25,000,000、红字真值写 985.35，
        而三者之间差的正好是那个缩放倍数，页面上没有任何一个字解释这件事。

        只重写本底座 `spike_cap()` 自己写下的那几张（`self.cap_ns` 点名）——
        别的生成器（`build/wealth.py` / `build/ibkr.py` / `build/schw.py`）各有各的
        `cap_note` 措辞，那些页不走这条路，不该被这里改一个字。
        """
        by_n = {e['n']: e for e in (ex or []) if isinstance(e, dict) and 'n' in e}
        for z in (self.cap_ns or []):
            e = by_n.get(z['n'])
            if not isinstance(e, dict) or e.get('ycap') is None or not e.get('cap_note'):
                continue
            e['cap_note'] = (f'axis capped at '
                             f'{fmt_val(float(e["ycap"]), e.get("fmt") or z["fmt"])}'
                             f' — true values shown in red')

    def cap_zh(self, ex=None):
        """页尾那一段：本页到底有没有图截了轴、截在多少、几个点越界。**两分支现算。**

        由 spec 的 `notes` 用 `callable(page)` 挂上（`lambda page: page.cap_zh()`）
        —— 底座不无条件印它，理由见 `notes()` 末尾那段分派的注释。
        `ex` 不给就取 `notes()` 挂上来的那一份最终 payload。

        ⚠️ 三件事必须分开数，否则这段话必然说谎：

        ① **`yfloor: 0` 是归零，不是截轴。** 本底座几乎每张 `lines_endlabels` 都带它
           （`ex_lines()` 里那句注释：默认下界是 min − 极差×20%，会在零轴以下留出一大块
           不存在的量纲区间；没有点落在 0 以下，所以那不是截轴）。把它算进「截了轴」的
           名单，页尾会声称几十张图截过轴，而那些图自己的图注写着相反的话。
           判据照 `build/mrbase.py` 的 `_cut()`：**看有没有点真的被那条界挡住**。

        ② **同比线绝大多数画在右轴，它的截轴字段是 `yoy.ymax` 不是 `ycap`**
           （CONTRACT §6.2 那条 ⚠️）。只看 `ycap` 的话，`near_zero_guard()` 真截了右轴的页
           会一边印「本页没有任何一张图截轴」、一边有一条同比线钳在 +400% ——
           `build/ibkr.py` 的同一处注释记着这个坑。右轴那半边直接读 `self.nz_ns` 这本账
           （`near_zero_guard()` 只在**真有点超界**时才往里记 `cap`），不去复刻引擎的
           右轴刻度取整：那套算法（`ticks()` + 零点对齐）在 `build/axisfmt.py` 与
           `tools/align_replica.py` 各有一份副本，在这里再抄第三份只会多一处会漂的假话。

        ③ **「本页一张都没截」是常态，所以这句话不许写死成「没有」。** 9 张 spec 页里
           今天只有一页命中；下一次谁给某张图加了 cap，页尾必须自己跟着变
           （`build/axp.py` 的同一处注释：「不手写：本轮一张都没有，但这句话不能写死」）。

        ④ **左轴那半边的数字一律回读最终 payload，不读 `self.cap_ns`。** 账本记的是
           `chartscale` 缩放**之前**的原始量级，而页尾这段话是让读者对着图上的轴顶与红圈
           逐个核对的 —— 两边不是同一个量级就核不动。见 `_cap_final()`。
           （右轴那半边没有这个问题：`chartscale` 不碰 `yoy`，它画的是百分数。）
        """
        def _nums(seq):
            return [float(v) for v in (seq or [])
                    if isinstance(v, (int, float)) and np.isfinite(float(v))]

        if ex is None:
            ex = getattr(self, '_ex', None) or []
        # 左轴真被挡住的点（`yfloor` 归零那一类在这里自然落选：没有点低于 0）
        floor0 = []
        for e in (ex or []):
            if not isinstance(e, dict) or e.get('yfloor') is None or e.get('ycap') is not None:
                continue
            lv = _nums(e.get('values'))
            for grp in ('series', 'stacks', 'groups'):
                for s in (e.get(grp) or []):
                    lv += _nums(s.get('values'))
            for k in ('bar', 'base'):
                lv += _nums((e.get(k) or {}).get('values'))
            if lv and min(lv) >= float(e['yfloor']):
                floor0.append(e['n'])

        rhs = sorted({z['n'] for z in (self.nz_ns or []) if z.get('cap')})
        lhs = sorted(self.cap_ns, key=lambda z: z['n'])
        head = '<b>截轴（纵轴上界被人为压低）。</b>'
        if not lhs and not rhs:
            body = ('<b>本页没有任何一张图截轴</b> —— 没有一张图设 <code>ycap</code>，'
                    '也没有哪条同比线的次轴设 <code>ymax</code>。'
                    '这句话是现算的：底座逐张读最终 payload 与截轴账本，'
                    '哪天真有一张被截，这里会自己改口。')
        else:
            by_n = {e['n']: e for e in (ex or []) if isinstance(e, dict) and 'n' in e}
            seg = []
            for z in lhs:
                # 上界 / 单位 / 格式器 / 越界清单四样全部回读最终 payload（见 ④ 与
                # `_cap_final()`）—— 读者拿这段话对的是图上的轴顶与红字，不是构建日志。
                cap, unit, cfmt, over = self._cap_final(by_n, z)
                seg.append(
                    f'<b>Exhibit {z["n"]}</b> 的<b>左轴</b>截在 '
                    f'{fmt_val(cap, cfmt)} {unit}，'
                    f'{len(over)} 个读数越界（'
                    + '、'.join(f'{m}「{nm}」{fmt_val(v, cfmt)}' for m, nm, v in over)
                    + '）')
            for j in rhs:
                caps = [z['cap'] for z in self.nz_ns if z['n'] == j and z.get('cap')]
                seg.append(f'<b>Exhibit {j}</b> 的<b>次轴</b>（同比那条线）截在 '
                           f'+{max(caps):.0f}%（近零基数，见该图图注）')
            body = (f'本页有 <b>{len(lhs) + len(rhs)}</b> 张图截了轴：' + '；'.join(seg)
                    + '。<b>截轴一个点都不删</b> —— 超界的点钳到边界、画成空心红圈、'
                      '真值红色竖排标在旁边，图顶左上角另有一行斜体小字说明。'
                      '被截的那几个月在图上是压平的一段，它们彼此之间的高低读不出来，'
                      '只能读红字真值；其余各月的形状是原样的。')
        tail = ''
        if floor0:
            tail = (f'另有 {len(floor0)} 张图设了 <code>yfloor</code> 把纵轴<b>归零</b>'
                    f'（Exhibit {"、".join(str(j) for j in floor0)}），'
                    f'<b>那不是截轴</b>：一个点都没有落在那条界之下（判据现算，逐张比最小值）。'
                    f'归零是为了让线的高度可以直接当绝对水平读 —— 引擎给这个图型的默认下界是'
                    f'「最小值 − 极差×20%」，那是一次没有标注的隐性截轴，'
                    f'会在零线以下留出一大块不存在的量纲区间。')
        return head + body + tail

    def cost_ns_zh(self, mom_ns):
        """页尾那半句：逐图代价（§6.1 第 3 条）到底印在了哪几张图上。

        `mom_ns` = 本页画流量单月同比的全部图号（口径账本里 cal=='mom' 的那批）。
        三种形态见调用处的注释。写成一个函数而不是在 `notes()` 里堆三层三元表达式，
        是因为这段话的真伪判据（cost_ns / cost_thin_ns / mom_ns 三个集合的关系）
        比它的措辞值钱：读的人要能一眼看出「什么情况下这句话会变」。
        """
        printed = sorted(self.cost_ns & mom_ns)
        thin = sorted(self.cost_thin_ns & mom_ns)
        if not printed and not thin:
            return ''
        head = ('；上面<b>每一张</b>的图注里都各自把这笔代价' if printed and not thin else
                '；' + '、'.join(f'Exhibit {j}' for j in printed)
                + f' 的图注里{"各自" if len(printed) > 1 else ""}把这笔代价') if printed else ''
        body = (head + '<b>用那条序列在那张图窗口内的实测数字</b>标了出来'
                       '（逐月标准差、相邻月最大跳变、两种口径符号相反的月份数）——'
                       f'滚动口径就只在那{"几" if len(printed) > 1 else "一"}段文字里'
                       '以数字出现' if printed else '')
        if thin:
            body += ('；' + '、'.join(f'Exhibit {j}' for j in thin)
                     + f' 的可比月不足 {self.MOM_COST_MIN} 个（两种口径都有值的月份），'
                       f'分母太小、报出来是样本噪声，那几张的图注里照实写了「量不出来」，'
                       f'不是漏印')
        return body

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
        """给一张**横轴是月份**的图挂上断点。heat_matrix 不支持 break_at，别调它。

        ⚠️ 顺带记一笔账（`self._brk_asked`）：**这张图问过断点**。页尾那段要把
        「窗口跨过断点月却没画线」的图分成两档来解释，而两档的理由完全不同 ——
        问过而没命中的，理由是「断点按列登记，这张没用到那一列」；**根本没问过**的
        （`bridge_bar` 那一支就不调本方法），理由是「这一图型不挂断点线」，与它用了
        哪几条列无关。把后者算进前者，就是替它编一个对它不成立的理由（2026-09
        实测：/tmx/ 的两张月度量价分解正是这一档，而它们的量腿恰恰是登记了换源断点
        的那条列，同一条列在别的图上画着红线）。
        账记在这里而不是按图型写死一张名单：判据是「构建时到底有没有问过」这件事实，
        以后新增图型不必回来改名单。
        """
        if ex.get('n') is not None:
            self._brk_asked.add(ex['n'])
        at, lab, hit = self.breaks_for(window, cols)
        if at:
            ex['break_at'] = at
            if len(window) <= self.BREAK_LABEL_MAX:
                ex['break_label'] = lab
        return hit

    def note_nodraw_cols(self, ex, cols):
        """记一笔账：这张图**不调 `mark_breaks`**（画不出断点线），它的输入列是这几条。

        `self._brk_asked` 的配套账，缺了它页尾那段就只能对这一档说一句无条件的话。
        由来：页尾把「窗口跨过断点月却没画线」的图分成两档之后，`by_kind` 那一档末尾
        还挂着一句**关于别人图注内容**的断言 ——「跨断点的那几格改由它们各自的图注点名
        交代」。它当时是**无条件**印的：在 /tmx/ 上为真（那两张月度分解的图注确实把
        2021-08 换源那 12 格逐句交代了），在 /asx/ 上是假的 —— asx 唯一那张
        `bridge_bar` 的两条输入列**一条都没登记断点**，它压根没有可交代的东西，
        图注里「断点」「换代」「红色竖虚线」也确实出现 0 次。

        判据要现算就得知道「这张图用了哪几条列」。`_cols`（chartscale 那个临时键）指望
        不上：`bridge_bar` / `heat_matrix` 两支根本不写它，而且它在
        `chartscale.fix_all()` 里被 pop 掉，`notes()` 跑到的时候早就没了。所以另记一本。

        ⚠️ 两条硬要求：
          · 键是**最终图号**（`ex['n']`），且只在这张图**真的出得来**的时候记 ——
            `ex_decomp` 中途 `return None` 的那几支会把同一个号让给后面的图，
            先记就会记到别人头上；
          · 没记过的图型在页尾那段里落进「**什么都不说**」的一档（见 `notes()`）：
            宁可少说半句，也不要替一张不知道用了什么列的图编一个理由。
        """
        if ex.get('n') is not None:
            self._nodraw_cols[ex['n']] = [str(c['col'] if isinstance(c, dict) else c)
                                          for c in cols]

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
            # 隐性截轴，长历史图上会把增长幅度凭空放大（cboe Ex6 / hkex Ex15 都栽过 ——
            # 两个都是当时的号，那两张全历史线后来分别按页面所有者的指令删了）。
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
        money = col_is_money_ratio(c)
        rhs = yoy_rhs(s_, win, pct_series=ratio,
                      diff_unit=c['unit'] if money else None)
        ex = bar_ex(n, f'{c["zh"]}：全历史水平值与单月同比', c, xl, v, rhs,
                    ylab2=rhs_ylab2(c, mom=True))
        ex['full'] = True
        ex['_cols'] = [c['col']]
        if rhs:
            cal = ('mom_money' if money else 'mom_pp') if ratio else 'mom'
            self.log_yoy(n, cal)
            self.log_yoy_bar(n, c, win, cal, 'bar_yoy', '头条开篇图（headline_style=bar_yoy）')
        hit = self.mark_breaks(ex, win, [c])
        ex['src_extra'] = 'Full disclosed history; the right-hand line is the single-month y/y'
        ex['note'] = (
            f'<b>本页的开篇图：一张图上同时给水平值与增速。</b>'
            f'深蓝柱 = {c["zh"]}的水平值（{c["unit"]}，原始单位），'
            f'横轴是<b>全部已披露历史</b> {xl[0]} → {xl[-1]}（{len(win)} 个月），'
            f'{_span_vs_win(win)}'
            + (f'金色折线（右轴）= <b>单月同比</b>（当月对去年同月'
               + (f'，单位是 {yoy_diff_word(c)}' if ratio else '') + f'）。'
               if rhs else NO_YOY_NOTE)
            + f'{xl[-1]} 读数 {unit_txt(v[-1], c)}，'
              f'同比 {chg_txt(c, v)}、环比 {chg_txt(c, v, lag=1)}。'
            + (self.mom_cost_zh(n, c, win) if rhs else '')
            + (self.near_zero_guard(n, c, win, rhs) if rhs else '')
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
        # 整张画布就是同比，所以主轴的单位就是这条同比的单位 —— 三档与次轴
        # 那条线同一套判据（`rhs_ylab2` / `yoy_diff_word`）：非比率 %、
        # 百分点比率 pp、**分子是钱**的比率还是钱。
        money = col_is_money_ratio(c)
        # 钱的差给纯数字，位数取该列自己的 fmt（官方发几位就是几位，CONTRACT §5）。
        mdec = min(FMT_INFO[c['fmt']][0], 3)
        # grouped_bars 而不是 diverging_bars：后者的图例与表格列名被引擎写死成 COST 的
        # 文案（charts.js:1437/1522-1523），换任何一家都会印出「油汇顺风」。
        ex = {
            'n': n, 'kind': 'grouped_bars',
            'fmt': (f'f{mdec}' if money else 'pp1') if ratio else 'pct1',
            # pp 族只有 pp0/pp1 两档，量级细的比率会被印成一列「0.0pp」——
            # 判据与次轴那条线同源，见 `pp_yfmt()`。钱的差连 pp0 都不能要。
            'yfmt': ('f0' if money else pp_yfmt(LN(yv))) if ratio else 'pct0',
            'xlabels': xl, 'bar_labels': False,
            'title': f'{c["zh"]}：单月同比',
            'ylab': (f'{c["unit"]}, y/y 差' if money else 'pp y/y') if ratio else '% y/y',
            'groups': [{'name': (f'同比（{c["unit"]} 的差）' if money else
                                 '同比（百分点）' if ratio else '同比 y/y'),
                        'color': 'NAVY', 'values': LN(yv)}],
        }
        hit = self.mark_breaks(ex, win, [c])
        fin = [x for x in yv if x is not None and np.isfinite(x)]
        u = (f' {c["unit"]}' if money else 'pp') if ratio else '%'
        dec = mdec if money else 1
        rng = (f'窗口内在 {nz_txt(f"{min(fin):+.{dec}f}{u}")} ~ '
               f'{nz_txt(f"{max(fin):+.{dec}f}{u}")} 之间。' if fin else '')
        ex['note'] = (
            f'{self.win_zh(win)}的同比，正负同色、零线由引擎画出（数据色只有 6 个，'
            f'RED 是断点专用色，所以不按正负分色）。'
            + (f'本列是<b>分子为钱</b>的比率，同比是<b>{c["unit"]} 的差</b>，'
               f'既不是「百分比的百分比变化」也不是百分点（pp/bp）。' if money else
               '比率序列的同比用<b>百分点差</b>，不是「百分比的百分比变化」。' if ratio else
               '基数不足序列中位绝对值 15% 或两期异号的月份留空 —— 那种同比不是信息，'
               '是把一个接近零的分母放大成三位数。')
            + rng
            # §6.1 第 3 条：整张画布画的就是单月同比，这张比谁都欠这笔账。
            # 一行式，理由同 ex_single（`_mom_cost_brief` 的调用方 docstring）。
            + (self.mom_cost_zh(n, c, win, brief=True) if fin else '')
            # 这张图的同比画在**主轴**上，所以截的是 ycap 而不是次轴的 ymax。
            + (self.near_zero_guard(n, c, win, ex, field='ycap',
                                    vals=ex['groups'][0]['values']) if fin else '')
            + (self.brk_zh(hit, win) + '：跨断点的同比本身就不可比。' if hit else ''))
        # 整张图画的都是单月口径（比率列 = 百分点差）→ 记进口径账本，页尾点名
        cal = ('mom_money' if money else 'mom_pp') if ratio else 'mom'
        self.log_yoy(n, cal)
        # 同时进查重账（图族 yoy_only）：头条列常常又被 level_yoy 或某个单列桶画一遍
        # 「水平值柱 + 次轴同比」，那条次轴金线与本图的柱是同一个数组。
        # 一整列都算不出同比时不登记 —— 没画出线就谈不上重复。
        if fin:
            self.log_yoy_bar(n, c, win, cal, 'yoy_only', '头条同比图（headline）')
        return ex

    # ────────────────────── exhibit：分组多列对比 ──────────────────────
    def ex_group(self, n0, gz, cols, rr=None, spike=False):
        """一组同单位的流量列 → 一张图。返回 exhibit 列表（可能 0 或 1 张）。

        · 1 列   → gs_bar（水平柱 + 次轴同比），单条线没有「对比」可言
        · 2–5 列 → lines_endlabels（窗口内逐点稠密时）/ lines（有缺口时）
        · >5 列  → heat_matrix，画的是**同比**而不是水平值（见下面的注释）

        `rr` = 本组的 `ratio_rhs`（可选，见模块头 GROUP_KEYS 那一段）。给了、且本桶
        恰好是它的 num 与 den 两列时，`ex_lines` 改出 `grouped_bars` + 右轴比值线。
        不给就走原路径 —— 没声明 ratio_rhs 的 8 个 spec 页逐字节不变。

        `spike` = 本组的 `spike_cap`（同上，默认 False）。False 时 `spike_cap()`
        一步都不走，输出逐字节回到那条通路上线之前。
        """
        if len(cols) == 1:
            return [self.ex_single(n0, gz, cols[0])]
        end = max(self.last_month(c) for c in cols)
        if len(cols) <= MAX_LINES:
            return [self.ex_lines(n0, gz, cols, end, rr=rr, spike=spike)]
        return [self.ex_heat(n0, gz, cols, end)]

    def ex_single(self, n, gz, c):
        end = self.last_month(c)
        win = self.win_long(end)
        xl = [mlab(p) for p in win]
        v = self.vals(c, win)
        if self.flat0_skip(gz, [c], win, [v]):
            return None
        ratio = self.is_ratio(c)
        money = col_is_money_ratio(c)
        # 掐在 `rhs` 上而不是事后删字段：下面 `if rhs:` 那一整块（口径账本 log_yoy、
        # 查重账 log_yoy_bar、逐图代价 mom_cost_zh、近零 + 右轴截轴 near_zero_guard）
        # 全部跟着自动退场，页尾那几段点名文案现算 —— 不会出现「账本记着某张图有同比、
        # 而页面上没有那条线」的背书。
        rhs = None if c['no_yoy'] else yoy_rhs(
            self.ser(c), win, pct_series=ratio,
            diff_unit=c['unit'] if money else None)
        avg12 = prior12(v) if (c['no_yoy'] and not rhs) else None
        ex = bar_ex(n, f'{gz}：{c["zh"]}', c, xl, v, rhs,
                    ylab2=rhs_ylab2(c), avg12=avg12)
        if rhs:      # 次轴金线是单月口径的同比；rhs 没画出来就没有同比可点名
            cal = ('mom_money' if money else 'mom_pp') if ratio else 'mom'
            self.log_yoy(n, cal)
            # 进查重账。记在**真画出来之后**（flat0 跳过的、没有次轴的都不算），
            # 判据才跟着页面走而不是跟着 spec 的声明走。
            self.log_yoy_bar(n, c, win, cal, 'bar_yoy', f'groups「{gz}」的单列桶')
        hit = self.mark_breaks(ex, win, [c])
        ex['note'] = (
            f'{self.win_zh(win)}。'
            + (f'金色折线 = 次轴<b>单月</b>同比'
               f'（{yoy_diff_word(c)}，同 GS deck 的 lvl_bar —— 那个位置画的是同比，'
               f'不是滚动均线：均线只是把柱子再平滑一遍、不带新信息）。' if rhs else
               (no_yoy_off_zh(c, avg12) if c['no_yoy'] else NO_YOY_NOTE))
            + f'{xl[-1]} {unit_txt(v[-1], c)}，'
            f'同比 {chg_txt(c, v)}、环比 {chg_txt(c, v, lag=1)}。'
            # §6.1 第 3 条的「逐图」：本页绝大多数带同比的柱图都出自这条路径，
            # 从前它一个字都不印，那条硬约定在最主要的出图路径上等于没实现。
            # 用一行式（`brief=True`）：三样一个不少，全页共用的那半段留在页尾。
            + (self.mom_cost_zh(n, c, win, brief=True) if rhs else '')
            + (self.near_zero_guard(n, c, win, rhs) if rhs else '')
            + self.slow_tail([c])
            + (self.brk_zh(hit, win) + '。' if hit else ''))
        return ex

    def ex_lines(self, n, gz, cols, end, rr=None, spike=False):
        win = self.win_long(end)
        xl = [mlab(p) for p in win]
        vs = [self.vals(c, win) for c in cols]
        # 整组都恒为 0 才跳：其中一条为 0 是有信息的对比，量程由别的列定，图正常。
        if self.flat0_skip(gz, cols, win, vs):
            return None
        # 声明了 ratio_rhs 且本桶恰好是那两列 → 换 grouped_bars（并排柱 + 右轴比值线）。
        # 判据写成「恰好」而不是「包含」：多一列就有一根柱不被右轴那条线解释。
        if rr and {c['col'] for c in cols} == {rr['num'], rr['den']}:
            return self.ex_ratio_rhs(n, gz, cols, win, xl, rr)
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
        # 尖刺截轴。**只在本组声明了 `spike_cap: True` 时才走**（见模块头 GROUP_KEYS
        # 那一段：数据相关的门当不了闸，别人的页不该在没有指令的情况下被截轴）。
        #
        # ⚠️ 这里**不再**按 kind 分流。上面那个 `dense` 是**数据决定**的：窗口里缺一个月，
        # 同一组就从 lines_endlabels 掉成 lines。按 kind 挡在门外的写法有两个后果：
        #   ① 声明了开关的组会因为下个月少一行数据就静默不截 —— 所有者的指令被数据吃掉；
        #   ② `spike_cap()` 里那句 `kind != 'lines_endlabels'` 的 `raise` 永远走不到，
        #      是一段假装在守门的死代码。
        # 所以两种 kind 都送进去，由 `spike_cap()` 自己按 kind 取引擎对应的那套量程式与
        # 端点护栏（两套都在那里逐行对着 charts.js 写着），第三种 kind 才真的 raise。
        # 落点在 yfloor / zero_base 之后 —— 那道门要看的是**这张图最终那根轴**，下界还没
        # 定就算不出占比；也在 mark_breaks 之前 —— 断点只往 ex 上挂 break_at/break_label，
        # 与量程无关，但保持「先把轴定死、再往上挂标注」这个顺序，后来的人不用去想耦合。
        spike_zh = self.spike_cap(n, ex, cols) if spike else ''
        hit = self.mark_breaks(ex, win, cols)
        last = '、'.join(f'{c["zh"]} {fmt_val(v[-1], c["fmt"]) or "—"}' for c, v in zip(cols, vs))
        ex['note'] = (
            f'{self.win_zh(win)}，同一单位（{cols[0]["unit"]}）才画在同一根轴上 —— '
            f'量纲不同的列由底座自动拆成各自成图。{xl[-1]}：{last}。'
            + ('' if dense else '窗口内有缺月，改用不平滑的 lines 图型：缺口处断笔，'
                                '不用直线连（平滑图型会把 null 当 0 画出一条塌到零的假线）。')
            + spike_zh
            + self.slow_tail(cols)
            + (self.brk_zh(hit, win) + '。' if hit else ''))
        return ex

    def ex_ratio_rhs(self, n, gz, cols, win, xl, rr):
        """声明了 `ratio_rhs` 的那一桶：并排柱（左轴）+ 右轴比值线。

        为什么是 `grouped_bars` 而不是给 `lines_endlabels` 加一条线：
        `lines` / `lines_endlabels` **没有次轴** —— 不是 payload 没给，是引擎的绘图、
        图例、表格、tooltip 四处都不读 `ex.line`（`docs/CHART_KINDS.md` §4）。
        而比值与两条水平值列量纲不同，塞进同一根左轴会把两条主线压成贴底的一条。
        引擎里能「N 条同单位序列 + 可选右轴线」的只有这一种 kind。
        """
        cn, cd = rr['num_col'], rr['den_col']
        # 柱按 spec 的列序画（读者从上一版折线图带过来的颜色记忆不变：
        # LINE_COLORS 的前两个就是原来那两条线的颜色）。
        vs = [self.vals(c, win) for c in cols]
        bar_colors = [LINE_COLORS[i] for i in range(len(cols))]
        used = set(bar_colors)
        c_line = next((x for x in RATIO_RHS_COLORS if x not in used), None)
        if c_line is None:
            raise SpecError(
                f'[{self.ticker}] Exhibit {n}「{gz}」：并排柱已经占掉 '
                f'{"、".join(sorted(used))}，右轴那条比值线没有颜色可用 —— '
                f'金色是本站同比专用、红色是断点与截轴专用，两个都不许拿来当数据色')
        vn, vd = self.vals(cn, win), self.vals(cd, win)
        with np.errstate(invalid='ignore', divide='ignore'):
            rv = np.where(np.isfinite(vn) & np.isfinite(vd) & (vd != 0), vn / vd * 100.0, np.nan)
        fin = rv[np.isfinite(rv)]
        if not fin.size:
            raise SpecError(
                f'[{self.ticker}] Exhibit {n}「{gz}」：{mlab(win[0])}–{mlab(win[-1])} '
                f'窗口内一个月都算不出比值 —— 右轴会印出一列假刻度而线一个点都没画')
        i_lo, i_hi = int(np.nanargmin(rv)), int(np.nanargmax(rv))
        # 标题按**画出来的顺序**列柱名（不是 num/den 的顺序），后面挂一个短的比值名 ——
        # 与 `ex_lines` 同一条规矩：名字太长就退回条数，免得标题折行把卡片顶开。
        # 比值名走 `axis_short`（去掉末尾那对解释性括号），全名留在图例与图注里。
        names = ' / '.join(c['zh'] for c in cols)
        ex = {
            'n': n, 'kind': 'grouped_bars', 'fmt': cols[0]['fmt'], 'xlabels': xl,
            'title': (f'{gz}：{names if len(names) <= 30 else "%d 条序列对比" % len(cols)}'
                      f'，右轴{axis_short(rr["zh"])}'),
            'ylab': cols[0]['unit'],
            'ylab2': f'{axis_short(rr["zh"], 18)}，%（右）',
            '_cols': [c['col'] for c in cols],       # 见 ex_history 里对 `_cols` 的说明
            # `bar_labels` 不开（引擎缺省就是关的，这里不写）：本图 128 期 × 2 根柱，
            # 逐根标数值会糊成一片，逐格读数走右上角「表格」。
            'groups': [{'name': c['zh'], 'color': cc, 'values': LN(v)}
                       for c, cc, v in zip(cols, bar_colors, vs)],
            'line': {'name': f'{rr["zh"]}（RHS）', 'color': c_line, 'values': LN(rv),
                     'yfmt': 'pct1',
                     # 右轴住的是一条**水平量**（结构性地贴在某一带），不是跨零的
                     # 同比：强行把 0 纳入量程会把十个百分点的结构压成轴顶的一条直线
                     # （`assets/charts.js` 给 line/yoy 留的正是这个口子，TSM Ex12 的
                     # 月均汇率是同一类）。
                     # 「柱全非负 ⇒ 两轴零点对齐是空操作」这个前提**已被护栏强制**：
                     # `Page.__init__` 里逐月硬失败 den > 0 且 num ≥ 0（bad_den /
                     # bad_neg），本图两根柱画的正是这两列 ⇒ 左轴 y0 = min(0, mn×1.15)
                     # = 0 ⇒ 零点比例为 0；比值 = num/den ≥ 0 ⇒ 右轴下界 ≥ 0 ⇒ 也为 0。
                     # 于是引擎的 f = 0，走「两轴本就同零点」那一支：不重排量程、
                     # 不重算刻度、不印「零点不同高」那行红字。
                     # 从前这里只是一句注释里的假设，而红队用一列会转负的分子实测到
                     # f=0.7778、waste=0.7111 > ALIGN_WASTE_MAX(0.38)：引擎真走了
                     # misalign 分支、真印了红字，图注里那串右轴刻度还是对齐之前算的。
                     'zero_base': False},
        }
        self.saw_ratio_rhs = True     # 页尾「图型选择规则」按真画出来的图措辞
        hit = self.mark_breaks(ex, win, cols)
        # 右轴刻度按引擎同一条算式现算（`charts.js` 的 ticks(min, max, 9)）。
        # 上面那段注释已经论证过零点对齐在本形状下是空操作（而且那个前提由
        # `Page.__init__` 的 bad_den / bad_neg 强制），所以这就是最终刻度。
        rtk = axisfmt.ticks(float(np.nanmin(rv)), float(np.nanmax(rv)), 9)
        # 「不从 0 起」是**这张图的刻度算出来的结果**，不是本图型的性质：
        # `zero_base: False` 只是不把 0 硬塞进量程，而 ticks() 会把下界向下取整到
        # 步长边界 —— 比值贴近 0 的那些页（红队实测 sgx 的 0.0%–11.0% 一组，
        # 下界落在 0.0）照印「不从 0 起」就是当着读者的面说反话。所以按 rtk[0] 分支。
        #
        # 分支之前先把「右轴下界 ≥ 0」这个前提查一遍。num ≥ 0 / den > 0 ⇒ 比值恒 ≥ 0
        # ⇒ ticks() 的 lo = floor(mn/step)×step ≥ 0 —— **但这一步要 mn < mx**。
        # 窗口内比值恒定时 ticks() 走 `mn == mx → mn−1, mx+1` 那一支，下界会掉到负数
        # （实测恒为 0.5% 时 rtk[0] = −0.5）：右轴零点比例不再是 0、两轴零点对齐从空操作
        # 变成真重排，与 num 转负是同一种失效，只是走的退化那条路。
        # 拒掉它与 `_norm_ratio_rhs` 里「num 与 den 是同一列」同源 —— 恒定的比值画出来
        # 就是一条直线，这张图本来也没有画的必要。
        # 拒掉之后剩下的只有「从 0 起」与「从正数起」两支。
        if rtk[0] < 0:
            raise SpecError(
                f'[{self.ticker}] Exhibit {n}「{gz}」：{mlab(win[0])}–{mlab(win[-1])} '
                f'窗口内比值恒为 {share_txt(float(fin[0]))}%，右轴刻度因此退化到 '
                f'{rtk[0]:g} —— 右轴下界为负会让两轴零点对齐不再是空操作，'
                f'而图注里那串刻度是对齐之前算的；何况恒定的比值画出来就是一条直线。'
                f'出路：去掉 ratio_rhs')
        rhs_from_zero = rtk[0] <= 0
        last = '、'.join(f'{c["zh"]} {fmt_val(v[-1], c["fmt"]) or "—"}' for c, v in zip(cols, vs))
        dup = rr.get('dup')
        ex['note'] = (
            f'{self.win_zh(win)}。<b>左轴两根并排柱</b>是同一单位（{cols[0]["unit"]}）的'
            f'水平值，<b>右轴那条{ _COLOR_ZH.get(c_line, "彩色") }线是{rr["zh"]}</b>'
            f'（{cn["zh"]} ÷ {cd["zh"]} × 100）。'
            f'{xl[-1]}：{last}，比值 {share_txt(float(rv[-1]))}%；'
            f'窗口内在 {share_txt(float(rv[i_lo]))}%（{xl[i_lo]}）到 '
            f'{share_txt(float(rv[i_hi]))}%（{xl[i_hi]}）之间，中位 '
            f'{share_txt(float(np.nanmedian(rv)))}%。'
            f'<b>它必须有自己的一根轴</b>：两根柱走在 '
            f'{fmt_val(float(np.nanmin(np.concatenate(vs))), cols[0]["fmt"])}–'
            f'{fmt_val(float(np.nanmax(np.concatenate(vs))), cols[0]["fmt"])} '
            f'{cols[0]["unit"]}，比值是 {share_txt(float(rv[i_lo]))}–'
            f'{share_txt(float(rv[i_hi]))} 的无量纲数（本图实测区间，不是 0–100 '
            f'这个理论上限），放进同一根左轴，'
            f'两根柱会被压进绘图区高度的一成 —— 等于把这张图作废。'
            + (f'右轴刻度 {share_txt(rtk[0])}–{share_txt(rtk[-1])}%、'
               f'<b>恰好从 0 起</b>：<code>zero_base</code> 是关着的（引擎不把 0 硬塞进'
               f'右轴量程 —— 这条线是水平量，不是同比那类跨零序列），但本图比值最低到 '
               f'{share_txt(float(rv[i_lo]))}%，刻度算式向下取整到步长边界就落在 0。'
               f'<b>这是算出来的，不是设定的</b>：比值贴得高的图上，同一段开关会给出一根'
               f'不从 0 起的右轴。'
               if rhs_from_zero else
               f'右轴刻度 {share_txt(rtk[0])}–{share_txt(rtk[-1])}%、<b>不从 0 起</b>：'
               f'这条线结构性地贴在窗口区间那一带，把 0 纳入量程会让十个百分点的结构'
               f'压成轴顶的一条直线（引擎给「水平量」右轴留的口子，同比那类跨零序列不适用）。')
            + f'并排柱不标柱顶数值（{len(win)} 期 × {len(cols)} 根会糊成一片），'
              f'逐格读数走右上角「表格」。'
            + (rr['note'] or '')
            # dup 段：底座只印**它能证明的**（实测最大差 / 中位 / 共同月数 / 容差）。
            # 「两者为什么会有差」是事实断言，由 spec 的 `dup_note` 承载 ——
            # 从前这里写死「这里是日均、那里是当月合计」，而两侧同口径、逐月差恒为
            # 0.0000pp 的组合照样会印出它（红队实测）。
            + (f'<b>这条比值与本页「{dup["gz"]}」那张 100% 堆叠图里的'
               f'「{dup["zh"]}」是同一条序列</b>：本比值 ≡ 100% − 那一段占比。'
               + (dup['note'] or '')
               + f'逐月绝对差实测最大 {dup["max"]:.4f}pp（{dup["max_at"]}）、'
               f'中位 {dup["med"]:.4f}pp，{dup["n"]} 个共同月份全部在 '
               f'{RATIO_DUP_TOL}pp 以内（这个差由构建期逐月复算，超容差不发页）。'
               f'本仓判例第 1 条是「同一条序列换个切法再画一遍要删」，'
               f'这一处留着是因为它在这张图上回答的是另一个问题 —— '
               f'那张堆叠图回答「{dup["nparts"]} 个分项各占多少」，'
               f'这条线回答「两根柱之间的缺口有多大」，'
               f'但读者有权知道这两处读到的是同一个数。' if dup else '')
            + self.slow_tail(cols)
            + (self.brk_zh(hit, win) + '。' if hit else ''))
        return ex

    def ex_heat(self, n, gz, cols, end):
        """>5 列：热力矩阵。**画同比，不画水平值。**

        色标是「全部有限值的 5/95 分位」共用一条 —— 水平值量级相差几十倍的列放进同一张
        矩阵，最大的那列会把色标整个占掉，其余各列全部糊成一个颜色。同比是无量纲的，
        才能跨列比。水平值请看核对表与各自的分组图。

        ⚠️ **整张矩阵只有一条色标、一个单位**，所以比率列（格内是百分点差）与量列
        （格内是百分比变化）不许混在同一张里 —— 混了色标就是拿 pp 和 % 比高低。
        今天不会发生：分桶按 `unit` 走（见 `payload()` 里那段），而比率判据
        （`col_is_ratio`）本身就把 unit 算成证据之一。护栏留着是因为「不会发生」
        靠的是两处约定的巧合，哪天分桶换了判据，这里得响一声而不是静默画错。
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
        kinds = {self.is_ratio(c) for c in cols if c['zh'] in set(rows)}
        if len(kinds) > 1:
            raise SpecError(
                f'[{self.ticker}] Exhibit {n}「{gz}」的热力矩阵里比率列与量列混在一起 —— '
                f'格内一半是百分点差、一半是百分比变化，而整张矩阵共用一条色标，'
                f'颜色深浅会被读成「谁涨得多」。比率列：'
                f'{[c["zh"] for c in cols if self.is_ratio(c)]}；'
                f'量列：{[c["zh"] for c in cols if not self.is_ratio(c)]}。'
                f'出路：把两批列拆进不同的 groups[]（或给其中一批显式的 ratio 声明）。')
        ratio = bool(kinds and kinds.pop())
        # ⚠️ 比率里还要再分一次：分子是百分数的差是**百分点**，分子是钱的差**还是钱**
        #    （见 `unit_is_money_ratio`）。整张矩阵一条色标一个单位，两类混在一起就是
        #    拿 pp 和 USD/contract 比高低 —— 与上面那道「比率 × 量」的护栏同一条理由。
        kept = [c for c in cols if c['zh'] in set(rows)]
        money_kinds = {col_is_money_ratio(c) for c in kept} if ratio else {False}
        if len(money_kinds) > 1:
            raise SpecError(
                f'[{self.ticker}] Exhibit {n}「{gz}」的热力矩阵里「分子是钱」的比率与'
                f'「分子是百分数」的比率混在一起 —— 格内一半是 {kept[0]["unit"]} 的差、'
                f'一半是百分点，而整张矩阵共用一条色标。'
                f'钱：{[c["zh"] for c in kept if col_is_money_ratio(c)]}；'
                f'百分点：{[c["zh"] for c in kept if not col_is_money_ratio(c)]}。'
                f'出路：把两批列拆进不同的 groups[]。')
        money = bool(money_kinds and money_kinds.pop())
        # 钱的差：格内给纯数字，位数取本组各列自己 fmt 里最细的那一档（官方发几位就是
        # 几位，CONTRACT §5）；单位由图例与图注承担 —— 与 `pp_yfmt()` 换族同一条读法。
        mdec = max(FMT_INFO[c['fmt']][0] for c in kept) if money else 0
        mfmt = f'f{min(mdec, 3)}'
        munit = kept[0]['unit'] if money else ''
        self.saw_group_heat = True      # 同上
        ex = {
            'n': n, 'kind': 'heat_matrix', 'full': True,
            'fmt': (mfmt if money else 'pp1') if ratio else 'pct0',
            'title': f'{gz}：{len(rows)} 条序列 × 近 {len(win)} 个月同比',
            'rows': rows, 'cols': [mlab(p) for p in win], 'matrix': M,
            'legend': (f'同比（{munit} 的差）' if money else
                       '同比（百分点差 pp）' if ratio else '同比 y/y (%)'),
            'row_head': '序列',
            'row_lab_w': max(label_width(r) for r in rows),
            'src_extra': (f'Cells are y/y change in {munit}, not levels' if money else
                          'Cells are y/y change in percentage points, not levels' if ratio
                          else 'Cells are y/y growth, not levels'),
        }
        # 格内是单月同比。heat_matrix 在 CONTRACT §6.3「图型豁免」名单上（每一格
        # 本来就是一个月的读数），但豁免的是**改口径**这件事，页尾的口径点名不豁免。
        # 比率矩阵记 'heat_pp' / 'heat_money'：页尾那段要说对格内那个差是什么单位。
        self.log_yoy(n, ('heat_money' if money else 'heat_pp') if ratio else 'heat')
        ex['note'] = (
            (f'格内是<b>同比的差，单位 {munit}</b>，不是水平值、不是百分比变化，'
             f'<b>也不是百分点（pp/bp）</b> —— 本组各列都是比率，而它们的<b>分子是钱</b>'
             f'（{munit}），当月减去年同月得到的仍然是钱。'
             f'比率的同比走差值，这一条是 CONTRACT §6.1 第 4 条；'
             f'差的单位跟着分子走，所以这张矩阵不写 pp。'
             if money else
             f'格内是<b>同比的百分点差</b>（pp），不是水平值也不是百分比变化 —— '
             f'本组各列都是比率（{cols[0]["unit"]}），比率的同比一律走百分点差'
             f'（CONTRACT §6.1 第 4 条：份额从 24.0% 到 25.0% 是 +1pp，不是 +4.2%）。'
             if ratio else
             f'格内是<b>同比</b>（%），不是水平值：')
            + f'色标由全部有限值的 5/95 分位共用一条，'
            f'量级相差几十倍的列放同一张矩阵会被最大的那列吃掉整条色标。'
            f'绿 = 同比高、红 = 同比低；<b>每张矩阵各算各的色标，两张矩阵之间颜色不可比</b>。'
            f'水平值请看末尾核对表。列数 {len(cols)} > {MAX_LINES}，'
            f'超出「一张图最多 5 条靠颜色区分的序列」的上限，故用行标签区分身份。'
            + (f'（{"、".join(dropped)} 整行没有可算的同比，已不列入。）' if dropped else '')
            + self.near_zero_rows_zh(n, kept, win)
            + '热力矩阵不支持断点竖线（矩阵没有连续横轴），本页的口径断点见「口径与方法说明」。'
            + self.slow_tail(cols))
        # 上面那句「不支持断点竖线」正是页尾 by_kind 那一档说的图型。记下真正画进矩阵的
        # 那几条列（`kept`，整行没有同比的已经被剔出去了），好让页尾现算得出「它们的列上
        # 到底登记没登记断点」—— 见 `note_nodraw_cols()`。
        self.note_nodraw_cols(ex, kept)
        return ex

    def near_zero_rows_zh(self, n, cols, win):
        """热力矩阵版的近零基数警告（CONTRACT §6.1 第 5 条），逐**行**判。

        与 `near_zero_guard()` 同一条判据、同一本账，但**不截轴** —— 矩阵没有纵轴，
        超界的格子由色标的 5/95 分位自己吃掉，没有「钳到轴顶」这回事。
        所以这里只做另一半：把哪几行、哪几个月说出来。
        """
        hits = []
        for c in cols:
            if self.is_ratio(c):
                continue        # 百分点差没有分母，理由同 near_zero_guard
            s_ = self.ser(c)
            s_ = s_.set_axis([mlab(p) for p in s_.index])
            d_ = ycal.near_zero_base(s_, win=[mlab(p) for p in win])
            if not d_['flag']:
                continue
            hits.append(f'<b>{c["zh"]}</b>（{len(d_["months"])} 个月：'
                        f'{_month_runs_zh(d_["months"])}，占本行当月与去年同月都有值的 '
                        f'{d_["n_base"]} 个月的 {d_["share"]:.1%}）')
            self.nz_ns.append({'n': n, 'col': c['col'], 'zh': c['zh'],
                               'share': d_['share'], 'k': len(d_['months']),
                               'n_base': d_['n_base'], 'cap': None,
                               'peak': None, 'months': list(d_['months'])})
        if not hits:
            return ''
        return (f'<b>⚠️ 近零基数：</b>' + '、'.join(hits)
                + f' —— 这些月份的基期低于该行<b>全历史</b> |值| 中位数的 '
                  f'{ycal.NEAR_ZERO_BASE_FRAC:.0%}（CONTRACT §6.1 第 5 条），'
                  f'同比读的是分母不是量，所以那几格<b>是空的</b>而不是 0。'
                  f'矩阵没有纵轴可截，这几行只看方向、不看格子的深浅。')

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
            self.log_yoy_bar(n, c, win, 'stock', 'bar_yoy', f'groups「{gz}」的存量列')
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
            + (self.near_zero_guard(n, c, win, rhs) if rhs else '')
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

    def total_drawn_wider(self, m):
        """这一组 `mix` 的合计柱，是不是**已经被本页别处那张更宽的图原样画过**了？
        是就返回一笔账，没有就 `None`。

        返回的是 dict 而不是图号：页尾那句话要把**两张的窗口**与「本组这张落在那张的
        哪一段」现算着说出来（见 `mix_folded_zh()`），构建日志那行也要同一批数。
            {'n': 那张图的图号, 'col': 合计列名, 'where': 那张图在账本里的出处,
             'wide': 那张的 (左, 右, 期数), 'own': 本组这张本来要画的 (左, 右, 期数),
             'side': '右边一段' / '左边一段' / '中间一段'}

        ── 为什么是现算而不是一个 spec 开关 ──────────────────────────────────
        「这一列已经被画成过一张水平值柱 + 次轴同比」是 `log_yoy_bar` 那本账
        （`self._yoy_bar_cols`）上**现读得出来的事实**。做成可声明的开关会有两种烂法：
        漏声明 → 页面上照旧两张一模一样的图；声明了而头条哪天换了列 → 那句声明
        原地变成假的，而且没有任何东西会响。账本跟着**真画出来的图**走，两种都不会发生。
        时序也是靠得住的：`payload()` 里 ① 头条（`headline_style='bar_yoy'` 那一支）
        在 ③ groups 之前就跑完了，轮到这里时那张一定已经登记在案。
        （①②/③/⑤ 这套阶段编号在 `payload()` 里，不在 `build()` 里 —— 这条时序是本函数
        正确性的全部依据，指错函数名下一个人就核不动它。）

        ── 判据：四条同时成立才算「同一张」──────────────────────────────────
        同一列、同一口径（`cal`）、同一图族（`bar_yoy`），且那张图的窗口**真包含**
        本组合计柱要画的窗口（完整覆盖，且至少有一端更靠外）。四条齐了，合计柱按构造
        就是那张图里的一段连续子集 —— 同一条序列自己除自己、同一种同比、更窄的横轴，
        逐点相等（2026-09 并图当天人工实测 `tmx` 的 `mx_adv_contracts`：重叠那一段
        values 与 yoy 的最大绝对差都是 0.0；本函数只比元数据，不复算数据点）。
        两个窗口都是同一条月度索引的**连续切片**，所以「只比两个端点」等价于完整覆盖，
        不会被中间有洞的窗口骗过。

        差一条都不算，三档各有各的去处：
          · 口径不同 / 图族不同 → 画出来是两条不同的线，两张都该留（`dup_yoy` 告警档）；
          · 窗口只盖住一半 → 合计柱那一段左边还有对方没有的月份，同样是 `dup_yoy`；
          · ⚠️ **窗口逐格相同 → 这里必须放过去，不许折叠。** 那一档是 `log_yoy_bar`
            的**硬失败**（同族 + 同窗口 → 退出码 1，docs/SINGLE_SPEC.md 的硬失败表里
            也躺着这一行）：两张一字不差，正确的收场是「spec 删一条」，而不是底座
            替 spec 静默删一张图。收进来的后果是双重的 —— 那条硬失败从此不可能触发，
            而页尾那句「窗口更宽 / 是它的一段」当场变假（等宽既不更宽、也没有「一段」）。
            所以下面那个 `continue` 不是优化，是把闸门留在原位。

        ── 为什么要把图号记回来 ────────────────────────────────────────────
        占比图的图注要写「<b>合计</b>的绝对量看 Exhibit k」。这张不出**不等于**
        那句话该消失：它仍然指得出来（指的就是那张更宽的），所以还得指
        —— 连带那句话括号里的**名字**也得换（见 `ex_mix_share` 的 `total_zh`）。
        """
        c = m['total']
        end = self.last_month(c)
        if end is None:
            return None          # 整列为空 —— 让 ex_mix_total 去记「画不出来」的理由
        win = self.win_long(end)
        # 合计柱走哪种口径由列的性质定，与 `ex_mix_total` 里两条分支逐字对应。
        cal = 'stock' if c['stock'] else 'mom'
        for prev in self._yoy_bar_cols.get(c['col'], []):
            if (prev['family'] != 'bar_yoy' or prev['cal'] != cal
                    or prev['p0'] > win[0] or prev['p1'] < win[-1]):
                continue
            if prev['p0'] == win[0] and prev['p1'] == win[-1]:
                continue         # 等宽：留给 ex_mix_total 去撞 log_yoy_bar 的硬失败
            return {
                'n': prev['n'], 'col': c['col'], 'where': prev['where'],
                'wide': prev['win'],
                'own': (mlab(win[0]), mlab(win[-1]), len(win)),
                # 本组这张落在那张的哪一段：右端相同 → 右边一段，左端相同 → 左边一段，
                # 两端都更靠外 → 中间一段。**三种都可能**（那张图的右端是它自己那一列的
                # 末月，与 `win_long` 的右端不必然相同），写死「右边一段」会在另外两档
                # 变成假话，而页尾那句话直接引它。
                'side': ('右边一段' if prev['p1'] == win[-1] else
                         '左边一段' if prev['p0'] == win[0] else '中间一段'),
            }
        return None

    def mix_folded_zh(self):
        """`mix_folded` 这本账 → 页尾「图型选择规则」⑤ 后面那句例外。空账返回 ''。

        ⚠️ 每一个断言都现算，一句都不许写死：
          · **「更宽」不是字面量。** 判据是真包含（见 `total_drawn_wider` 的等宽那一支），
            所以这句成立；但两张的窗口照样印出来，让读者自己数得出来它宽在哪。
          · **「是它右边一段」按 `side` 分叉**：右端相同才叫右边一段。
          · **「所以只出占比那一张」按占比图是否真画出来分叉。** 占比图自己也有几条
            画不出来的路（窗口不足 24 个月、某月合计 ≤ 0），两张都没出的时候这一组是
            **0 张图**，再说「只出占比那一张」就是一句读者一数就能拆穿的假话，而且会与
            页尾「本轮未出的派生图」那一段当场打架。
        """
        if not self.mix_folded:
            return ''
        bits = []
        for d in self.mix_folded:
            b = (f'「{d["gz"]}」：这一组合计那一列已经由 Exhibit {d["n"]} 那张'
                 f'<b>横轴更宽</b>的柱图画过（那张画 {d["wide"][0]} → {d["wide"][1]}，'
                 f'{d["wide"][2]} 个月；本组的合计柱只会画 {d["own"][0]} → {d["own"][1]}，'
                 f'{d["own"][2]} 个月，是它{d["side"]}的逐点复制）')
            b += (f'，所以只出占比那一张，<b>合计的绝对量看 Exhibit {d["n"]}</b>。'
                  if d['share_drawn'] else
                  f'；而占比堆叠这一张本轮也没画成（原因见「本轮未出的派生图」那一段），'
                  f'所以<b>这一组这一次一张图都没有</b>，'
                  f'合计的绝对量仍看 Exhibit {d["n"]}。')
            bits.append(b)
        return '⚠️ <b>例外</b>：' + ''.join(bits)

    def mix_pair(self, n, g):
        """一条 `mix` → ([合计柱图, 占比堆叠图], 本组被这一组的 mix 吃掉的列名集合)。

        两张一起产出而不是各自成图，是为了让占比图能在图注里指名道姓地说
        「绝对量看 Exhibit k」—— 图号是算出来的，写死会在增删图之后指到错的图上
        （见 `log_yoy` 的 docstring 记的同一条教训）。

        ⚠️ **返回的不一定是两张。** 合计柱有三种不出的情形，前两种是「想画画不成」、
        第三种是「有意不画」，语义不同，处理也不同 —— 见下面 `total_drawn_wider` 那一支。
        """
        m, gz = g['mix'], g['zh']
        # ── abs_stack：整组只出**一张**绝对值堆叠柱 ──────────────────────────────
        # 合计柱不再单出：柱高本身就是合计，再画一张同列同窗口的水平值柱是同一个数
        # 说两遍；而它带的次轴单月同比会与开篇头条图（同一列、`headline_style`
        # 那两张）撞进 `dup_yoy` 查重账。占比堆叠也不出：所有者要的是**绝对值**。
        if m['abs_stack']:
            one, why = self.ex_mix_abs(n, gz, m)
            if why:
                self.skipped.append(why)
            if one is None:
                return [], set()
            # 吃掉合计与全部分项：三条序列的水平值都在这一张图上（柱高 + 各段），
            # 再让它们进本组的常规对比图就是同一批数在同一页上画两遍。
            return [one], ({m['total']['col']}
                           | {c['col'] for c in m['parts']}) & g['declared']
        # ⚠️ `abs_stack` 那一支在下面这道折叠之**前**：它本来就不出合计柱，
        # 折不折叠对它没有意义；而 `total_drawn_wider` 要去读合计列的窗口，
        # 放在它前面等于替一张根本不出的图白算一遍。
        # 合计柱出图之前先问一句：这一列是不是已经被本页别处那张更宽的图原样画过了
        # （今天会命中的是 `headline_style='bar_yoy'` 的开篇图）。是就不出这一张 ——
        # 它按构造是那张的一段子集，逐点相等，出了就是同一条序列换个窗口再画一遍。
        fold = self.total_drawn_wider(m)
        # ⚠️ 折叠掉的那一组，`note` 是**死配置**：它唯一的去处是合计柱那张图的图注末尾
        # （`ex_mix_total`），合计柱不出就一个字都印不出来。静默吞掉等于让 spec 作者
        # 以为自己交代过的事已经在页面上了 —— 本仓对死配置一律硬失败（`residual_zh`
        # 声明了而残差恒为 0、`mix` / `level_yoy` 带滚动合计那三个死键，都是这么办的）。
        if fold is not None and m['note']:
            raise SpecError(
                f'groups「{gz}」.mix 写了 note，但这一组的**合计柱不出**：'
                f'{m["total"]["col"]} 已经由 Exhibit {fold["n"]}（{fold["where"]}）画过，'
                f'横轴更宽（那张 {fold["wide"][0]}–{fold["wide"][1]} {fold["wide"][2]} 个月，'
                f'本组这张只有 {fold["own"][0]}–{fold["own"][1]} {fold["own"][2]} 个月）。'
                f'note 只追加在合计柱的图注末尾，这一档下它一个字都上不了页 —— '
                f'请把这段话挪进 share_note（占比图的图注）或 spec 顶层的 notes。')
        drawn = fold['n'] if fold else None
        total, why_t = (None, None) if fold else self.ex_mix_total(n, gz, m)
        # 合计柱没出时占比图顶上来占 n，图号不留洞。三种情形：
        #   · 合计列整列为空 / 窗口内恒为 0 —— **想画而画不成**，理由记进 `skipped`，
        #     页尾照实说「本页少了这张、为什么」；
        #   · 已经被别处画过（`fold`）—— **有意不画**，一个字都不进 `skipped`：
        #     那本账是给「画不成」用的，把这一档混进去等于告诉读者页面上缺了点东西。
        # 前两种没有合计柱可指（`total_n=None`，那句交叉引用整句不印），
        # 第三种指得出来 —— `total_n` 传的就是那张已有的图号。
        # ⚠️ 括号里那个**名字**也得跟着 `total_n` 的语义走：折叠档下它指的是别人家的图，
        # 页面上没有任何地方管那张叫「合计柱」（它的标题、它自己的图注、页尾三处都不叫），
        # 一个解析不出去的指路牌与写错图号是同一类错。
        share, why_s = self.ex_mix_share(n + (1 if total else 0), gz, m,
                                         total_n=(n if total else drawn),
                                         total_zh=('合计柱' if total else
                                                   '同一列、横轴更宽的那张柱图'))
        if fold is not None:
            # ⚠️ 记账必须在 `ex_mix_share` **出结果之后**：页尾那句话要按占比图是否
            # 真画出来分叉（见 `mix_folded_zh`）。在这之前记，占比图也没画成时这一组
            # 是 0 张图，而页尾会同时印「所以只出占比那一张」与「占比堆叠不出」。
            self.mix_folded.append({**fold, 'gz': gz, 'share_drawn': share is not None})
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
        # ⚠️ `drawn` 那一档**必须照样收走这一列**：不收的话它掉回本组的常规分桶、
        # 走 `ex_single` 把同数同窗口的图原样再画一遍，而 `log_yoy_bar` 因为窗口
        # 与那张更宽的不同，只降级成 `dup_yoy` 告警 —— 四道闸门一道都不会拦下来
        # （`check_yoy_caliber` 会因为 `ex_single` 的标题里没有「单月」二字报一条
        # 🟡 R4，但退出码仍是 0）。这是这一支最容易漏的一处。
        if total is not None or drawn is not None:
            eaten.add(m['total']['col'])
        if share is not None:
            eaten |= {c['col'] for c in m['parts']}
        return [e for e in (total, share) if e is not None], eaten & g['declared']

    #: 图注里报口径差异所需的最少月份数（两种口径**都有值**、且都落在本图窗口内）。
    #: 比 `yoy.MIN_DIAG_MONTHS`（12）保守一倍，理由与 yoy.py 那段注释同源：12 是
    #: 诊断函数的门槛，24（两整年）是**要写进正文**的门槛 —— 「符号相反的月份占 33%」
    #: 这种句子在分母只有 3 的时候读起来像结构性问题，其实是样本噪声。
    MOM_COST_MIN = 24

    def cost_sample_gap(self, c, win, d):
        """代价那几个数是在哪个样本上量的 —— 它常常**不等于**金线画出来的那些点。

        `caliber_diff()` 必须先取两种口径的交集（CONTRACT §6.4：不对齐就把样本效应
        读成口径效应），而滚动那一侧要先填满 12 个月的窗，比单月侧少一年历史。
        于是**画在图上、却不在统计里**的那几个月，恰恰是序列刚起步、基数最低、
        因而最陡的那一段。

        2026-09-03 实测 `miax` Exhibit 23（`adv_equities_api_mnshares`，图窗
        Jan-16 至 Jul-26）：金线画出 52 个点，两种口径都有值的只有 45 个
        （Nov-22 至 Jul-26）；被排除的 7 个月是 Jan-22 与 May-22 至 Oct-22。
        图注当时报「逐月标准差 39.3pp、相邻月最大跳变 63.9pp（Sep-23 → Oct-23）」，
        而读者眼前那条线自己的标准差是 **88.0pp**（2.24 倍）、最大跳变
        **120.7pp（May-22 → Jun-22）**——那一跳就落在被排除的 7 个月里。
        数没算错，错的是**没说清这是哪个样本**，而同一段图注前面还写着
        「只统计本图画出来的这段窗口」。（这几个读数随数据变，下面的文案一个都不写死。）

        返回 None（金线画出来的点与交集逐月相同）或一个 dict：
          n_drawn / n_out / out（多画出来的那些月）/ std / jump（(pp, 前月, 后月)）。
        `std` 与 `jump` 用的是**金线自己画出来的那些点**，不取任何交集 ——
        它回答的是「读者看到的这条线有多毛刺」，与 `caliber_diff()` 回答的
        「两种口径差多少」不是同一个问题，后者必须对齐样本，前者不能。
        """
        labs = [mlab(p) for p in win]
        yv = yoy_line(self.ser(c), win, pct_series=self.is_ratio(c))
        a = np.array([np.nan if (v is None or not np.isfinite(v)) else float(v)
                      for v in yv], float)
        fin = np.isfinite(a)
        out = [l for l, f in zip(labs, fin) if f and l not in set(d['months'])]
        if not out:
            return None
        dj = np.abs(np.diff(a))
        k = int(np.nanargmax(dj)) if np.isfinite(dj).any() else None
        return {
            'n_drawn': int(fin.sum()), 'n_out': len(out), 'out': out,
            'std': float(np.nanstd(a[fin], ddof=1)) if fin.sum() >= 2 else float('nan'),
            'jump': (float(dj[k]), labs[k], labs[k + 1]) if k is not None else None,
        }

    def mom_cost_zh(self, n, c, win, brief=False):
        """单月同比的**代价**，拿这条序列自己实测 —— 只报数，不替它辩护。

        CONTRACT §6.1 第 3 条：每一张画<u>流量</u>同比的图都要印出单月口径的代价。
        口径本身不需要在图注里辩护 —— 全站单月是页面所有者定的（§6 抬头引了原话）；
        要交代的是**这条线有多毛刺**：单月同比同时被交易日数、假期与到期日的月度形状、
        以及去年同月那一个数的高低推着走，毛刺可以大到与趋势符号相反。
        所以这里把两种口径的差**量出来印上去**，让读者知道自己在读什么。

        ── `win` 是必填参数，不是可选的方便 ───────────────────────────────────
        这个函数原来一个参数都不收窗口，统计范围写死成 `self.df.index` 全长，
        而调用它的三张图窗口各不相同。后果是图注里报的月份读者在图上根本找不到：
        `ndaq` Ex14 的图窗是 Jan-16 → Jul-26（127 个月），图注却写「228 个月份…
        相邻月最大跳变 139.17pp（2008-08 → 2008-09）」；`db1` Ex41「差得最远的是
        2010-05」同样在图窗左侧之外；`enx` Ex38 在一张 127 期的图上写「152 个…月份」；
        `tmx` 的 `mx_adv_contracts` 当时被开篇柱与 mix 合计柱各画一张（296 期 vs
        128 期），两张图注却印着同一组 273 个月的实测数（那一对已在 2026-09 并成一张，
        见 `Page.total_drawn_wider` —— 这里按列名留证，不写会随增删图位移的图号）。
        所以窗口由调用方把**这张图真画出来的那一段**传进来，一处都不许省。

        ── 走 `build/yoy.py`，不自己写口径 ──────────────────────────────────
        CONTRACT §6.4 白纸黑字：「`yoy.caliber_diff()` 已经先取交集再比，别自己写」。
        这个函数从前自己写了一遍 `(s/s.shift(12)-1)*100` 与 `rolling(12).sum()`，
        因此既没有 `mom_yoy` 的 `(base==0) | (v*base<0)` 掩码，也没有近零基数那一层。
        现在统计量一律由 `ycal.caliber_diff()` 给、文案一律由 `ycal.describe()` 写，
        本文件只负责把口径那一句和窗口交代清楚。

        ── 月份标签用 `mlab`，与横轴逐字相同 ────────────────────────────────
        传进 `caliber_diff` 的序列先把索引换成 `Jan-16` 这种横轴标签，
        于是图注里点到的每一个月份都能在本图的 x 轴上原样找到。
        （`%b-%y` 在本仓 25 年的跨度内不会撞名，横轴本来也用它。）

        ── `kind` 按列判，不一律传 FLOW ─────────────────────────────────────
        比率列的「滚动合计」与存量列的「12 个月末快照相加」都不是合法口径，
        对它们算一遍再印进图注，印出去的就是 §6.1 第 2 / 第 4 条点名的那种
        「关于自己算术的假话」。`caliber_diff` 对这两类根本不比，只回一句结论，
        这里照它给的说。

        ⚠️ 不许在这里写「滚动口径更好但我们没用」—— 那是替页面上不存在的东西背书
        （§6.1 第 3 条的 ⚠️ 那半句）。

        ── `brief=True`：同一笔账的**一行式**写法 ──────────────────────────────
        2026-09 之前只有开篇图 / mix 合计柱 / level_yoy 三条路径调本函数，而本底座
        十页上 164 张 gs_bar（2026-09-02 全站 223 张里的绝大多数）主要出自
        `ex_single`（groups 的单列桶）—— 那条路径一个字都没印，
        §6.1 第 3 条「逐图」两个字在最主要的出图路径上等于没实现
        （实测：87 张画流量单月同比的图里只有 20 张印了代价）。
        补上之后一页要多出七八段，全长版每段约 430 字，页面会明显变重。
        所以给它一个短写法，**三样一样不少**（逐月标准差、相邻月最大跳变带月份、
        两种口径符号相反的月份数），砍掉的只有这三类：
          · 「口径是所有者定的 / 拿柱除以 12 根柱之前那根可核对」—— 全页共用的话，
            §6.1 第 3 条的 ⚠️ 允许留在页尾（`notes()` 里那段），不必逐图重复；
          · `describe()` 里的相邻月跳变**中位**与「差得最远的月份」—— 契约点名要的
            三样之外的两个补充统计量；
          · 收尾那句「这条线要连着柱高一起读」的长版本，压成半句。
        数字一个都不自己算：仍旧全部来自 `ycal.caliber_diff()` 的同一个 dict，
        与全长版逐位相同 —— 短的是措辞，不是口径，也不是证据。
        ⚠️ 它**不**走 `ycal.describe()`（那是全长版的措辞），所以这里是本仓第二处
        写这段话的地方；两处的数字同源，改口径统计量只需要改 `build/yoy.py` 一处，
        但要是想改**措辞**，记得这里也有一份。
        """
        kind = (ycal.RATIO if self.is_ratio(c)
                else ycal.STOCK if c['stock'] else ycal.FLOW)
        s_ = self.ser(c)
        s_ = s_.set_axis([mlab(p) for p in s_.index])
        d = ycal.caliber_diff(s_, kind, win=[mlab(p) for p in win])

        if brief:
            return self._mom_cost_brief(n, c, win, kind, d)
        if kind == ycal.STOCK:
            # §6.1 第 2 条：存量没有第二种合法口径，所以没有「换口径的代价」可报。
            # §6.1 第 3 条也把「印代价」这条债限定在流量列上。这里只把口径说清楚。
            return (f'<b>口径：本图次轴是<u>点对点</u>同比</b>（本月末 vs 去年同月末）——'
                    f'存量列的唯一合法口径：把 {TTM_WIN} 个月末的快照加起来既不是'
                    f'「一年的量」（存量不累积）也不是「平均水平」（没除以 12），'
                    f'那是一句关于自己算术的假话（CONTRACT §6.1 第 2 条）。'
                    f'所以本图没有第二种口径可拿来做对照，也就没有「换口径的代价」可报。')
        if kind == ycal.RATIO:
            # §6.1 第 4 条：比率的同比是**差**；滚动合计与滚动均值对比率都不成立
            #（「一年的平均费率」要按量加权，那要两条序列），同样没有对照可比。
            # ⚠️ 差的**单位**跟着分子走：分子是百分数 → 百分点（pp/bp）；分子是钱 →
            #    还是钱（USD/contract 的差还是 USD/contract）。算术一格没动，
            #    两支走的都是 `yoy.mom_yoy(s, RATIO)`，改的只是怎么称呼这个差。
            if col_is_money_ratio(c):
                return (f'<b>口径：本图次轴是<u>单月</u>同比的<u>差</u>，单位 {c["unit"]}</b>'
                        f'（当月的 {c["unit"]} 减去去年同月的 {c["unit"]}，'
                        f'不是「百分比的百分比变化」）—— CONTRACT §6.1 第 4 条要的就是这个减法。'
                        f'<b>这条线不是 pp 也不是 bp</b>：这一列的分子是钱，'
                        f'差出来仍然是钱。把它读成百分点会差几个数量级 —— '
                        f'0.05 → 0.04 是<b>跌了五分之一</b>，而「−1bp」读起来是万分之一。'
                        f'比率既不许做 {TTM_WIN} 个月滚动合计也不许做滚动均值'
                        f'（「一年的平均比率」要按量加权，那要两条序列），'
                        f'所以本图同样没有第二种口径可做对照。')
            return (f'<b>口径：本图次轴是<u>单月</u>同比，走百分点差</b>'
                    f'（当月的比率减去去年同月的比率，不是「百分比的百分比变化」）——'
                    f'CONTRACT §6.1 第 4 条。比率既不许做 {TTM_WIN} 个月滚动合计也不许'
                    f'做滚动均值（「一年的平均比率」要按量加权，那要两条序列），'
                    f'所以本图同样没有第二种口径可做对照。')

        head = (f'<b>口径：本图次轴是<u>单月</u>同比</b>（当月对去年同月，本列除本列）——'
                f'全站统一，页面所有者指定（CONTRACT §6 抬头引了原话）。'
                f'好处是可核对：<b>拿这根柱除以 12 根柱之前那根，就是线上这一点</b>。')
        if d['n'] < self.MOM_COST_MIN:
            self.cost_thin_ns.add(n)     # 见 cost_thin_ns 的定义处
            return (head +
                    f'代价本该在这里用本序列自己实测，但本图窗口 {self.win_zh(win)} 内'
                    f'两种口径都算得出的月份只有 {d["n"]} 个'
                    f'（不足 {self.MOM_COST_MIN} 个月，分母太小、报出来的比例是样本噪声'
                    f'不是结构），此处不报差异；这本身也是一句提醒：'
                    f'这条线的可比月很少，斜率不要外推。')
        # 记账：这张图**真的**印出了逐图代价。页尾那段「同比口径」拿它现算点名，
        # 从前那里无条件写着「每张图的图注里都…标出了这笔代价」，而画同比的图里
        # 只有开篇图 / mix 合计柱 / level_yoy 这三条路径走本函数，那句话对别的图为假。
        self.cost_ns.add(n)
        # 统计范围**不是**整段图窗，而是图窗内两种口径都有值的那些月 ——
        # 这句话从前写成「只统计本图画出来的这段窗口 —— Jan-16 至 Jul-26（127 个月）」，
        # 读者会把紧接着的标准差与最大跳变当成金线自己的读数，而它们常常小一半以上
        #（`cost_sample_gap` 的 docstring 记着实测的那一张）。所以这里报的是**交集**
        # 的起止与月数，缺口那一半由 `cost_sample_gap()` 现算补齐。
        g = self.cost_sample_gap(c, win, d)
        ms = list(d['months'])
        return (head +
                f'下面这段代价在<b>本图窗口内两种口径都有值的那些月份</b>上量 —— '
                f'{ms[0]} 至 {ms[-1]}，共 {d["n"]} 个月（图窗是 {self.win_zh(win)}；'
                f'窗外的历史读者看不到，所以不进统计）。'
                + (f'⚠️ <b>这不是本图金线的全部</b>：金线在本图上画出 {g["n_drawn"]} 个点，'
                   f'比这个样本多 {g["n_out"]} 个月（{_month_runs_zh(g["out"])}）——'
                   f'滚动那一侧在那几个月<b>没有值</b>（它要先填满 {TTM_WIN} 个月的窗，'
                   f'所以序列起步的头一年、以及任何缺口之后的一年都算不出来），'
                   f'配不成对；而两种口径的对比只能在配得成对的月份上做（CONTRACT §6.4）。'
                   f'把金线自己画出来的 {g["n_drawn"]} 个点一起量：'
                   f'逐月标准差 {g["std"]:.1f}pp'
                   + (f'、相邻月最大跳变 {g["jump"][0]:.0f}pp'
                      f'（{g["jump"][1]} → {g["jump"][2]}）' if g['jump'] else '')
                   + f' —— <b>这两个数才是你在图上看到的那条线</b>，'
                     f'下面那两个只描述交集那一段。' if g else '')
                + ycal.describe(d))

    def _mom_cost_brief(self, n, c, win, kind, d):
        """`mom_cost_zh(brief=True)` 的正文。理由与取舍见调用方的 docstring。

        窗口不必在这里重述：走这条路径的两种图（`ex_single` 的单列桶、`ex_yoy` 的
        头条同比图）图注**开头第一句**就是 `self.win_zh(win)`，读者往上看一行就有；
        但「统计的是本图这段窗口」这层意思必须留着，所以下面写成
        「本图窗口内两种口径都有值的 N 个月」——N 由 `caliber_diff` 在这段窗口上数出来。
        """
        if kind == ycal.STOCK:
            return (f'<b>口径：<u>点对点</u>同比</b>（本月末 vs 去年同月末）—— 存量列唯一'
                    f'合法的口径（把 {TTM_WIN} 个月末快照相加不指代任何量），'
                    f'没有第二种口径可做对照，也就没有「换口径的代价」可报'
                    f'（CONTRACT §6.1 第 2 条）。')
        if kind == ycal.RATIO:
            # 差的单位跟着分子走，理由与全长版逐字相同（见 `mom_cost_zh` 的 RATIO 分支）。
            if col_is_money_ratio(c):
                return (f'<b>口径：<u>单月</u>同比的<u>差</u>，单位 {c["unit"]}</b>'
                        f'（当月的 {c["unit"]} 减去去年同月的 {c["unit"]}，不是'
                        f'「百分比的百分比变化」）—— <b>不是 pp 也不是 bp</b>：'
                        f'这一列的分子是钱，差出来仍然是钱。比率不做 {TTM_WIN} 个月滚动'
                        f'合计也不做滚动均值，同样没有第二种口径可做对照'
                        f'（CONTRACT §6.1 第 4 条）。')
            return (f'<b>口径：<u>单月</u>同比，走百分点差</b>（当月的比率减去去年同月的'
                    f'比率，不是「百分比的百分比变化」）—— 比率不做 {TTM_WIN} 个月滚动'
                    f'合计也不做滚动均值，同样没有第二种口径可做对照'
                    f'（CONTRACT §6.1 第 4 条）。')
        if d['n'] < self.MOM_COST_MIN:
            self.cost_thin_ns.add(n)     # 见 cost_thin_ns 的定义处
            return (f'<b>单月口径的代价：本图量不出来</b> —— 本图窗口内两种口径都有值的'
                    f'月份只有 {d["n"]} 个（不足 {self.MOM_COST_MIN}，分母太小、'
                    f'报出来的比例是样本噪声不是结构），所以这里不报差异；'
                    f'这本身就是提醒：这条线的可比月很少，斜率不要外推。')
        self.cost_ns.add(n)      # 与全长版同一本账：页尾那段点名拿它现算
        j = d['maxjump_mom']
        ms = list(d['months'])
        # 与全长版同一条：这几个数量的是**交集**那一段，不是金线画出来的全部点。
        # 差着几个月时把金线自己的离散度也报出来 —— 读者拿这段话去读的正是那条线。
        g = self.cost_sample_gap(c, win, d)
        return (f'<b>单月口径的代价（用本列自己实测，样本是本图窗口内两种口径都有值的 '
                f'{d["n"]} 个月：{ms[0]} 至 {ms[-1]}）</b>：'
                f'逐月标准差 {d["std_mom"]:.1f}pp vs {TTM_WIN} 个月滚动 '
                f'{d["std_ttm"]:.1f}pp（放大 {d["std_ratio"]:.1f} 倍）；'
                + (f'相邻月最大跳变 {j[0]:.0f}pp（{j[1]} → {j[2]}）；' if j else '')
                + f'两种口径<b>符号相反</b>的月份 {d["opposite_n"]} 个'
                  f'（占 {d["opposite_share"]:.0%}）。'
                + (f'⚠️ 金线在本图上还画着另外 {g["n_out"]} 个月'
                   f'（{_month_runs_zh(g["out"])} —— 滚动侧要先填满 {TTM_WIN} 个月的窗，'
                   f'在那几个月没有值、配不成对）；'
                   f'把画出来的 {g["n_drawn"]} 个点一起量是标准差 {g["std"]:.1f}pp'
                   + (f'、最大跳变 {g["jump"][0]:.0f}pp'
                      f'（{g["jump"][1]} → {g["jump"][2]}）' if g['jump'] else '')
                   + '，那才是你看到的这条线。' if g else '')
                + f'⇒ 这条线要连着柱高一起读；对照的 {TTM_WIN} 个月滚动口径'
                  f'<b>只在这段文字里以数字出现</b>，页上一条线都不画。')

    def ex_mix_total(self, n, gz, m):
        """`mix` 的第一张：合计列的水平值柱 + 次轴**单月**同比。

        ⚠️ **这张不是无条件出的**：合计列已经被本页别处那张更宽的 `bar_yoy` 图原样
        画过时，`mix_pair` 根本不会调到这里（判据见 `Page.total_drawn_wider`）——
        那种情形下这张按构造是那张的一段子集、逐点相等，出了就是同一条序列换个窗口
        再画一遍。所以本函数里两条 `return None`（整列为空 / 窗口内恒为 0）说的都是
        「想画而画不成」，与那一档的「有意不画」不是一回事，别把两者混进同一本账。

        ⚠️ **这里曾经是 12 个月滚动同比，2026-09 按页面所有者的指令改成单月。**
        现行 CONTRACT §6.1 第 1 条就是「流量序列用单月同比」，没有第二种可选口径 ——
        上一版契约那套「滚动是默认、要用单月得逐张辩护」的框整个作废了，
        这段 docstring 从前照着它写（「第 1 条把滚动定为流量的默认口径，第 2 条允许
        用单月但要求标题里写明 + 图注说明为什么」），三处引用现在全指错了地方。

        改口径要付的账仍然要付，只是理由那一栏空了：
          · **标题与 `ylab2` 都写明「单月同比」** —— 不是为了辩护，是让读者一眼知道
            这条线是拿柱子直接除出来的。`tools/check_yoy_caliber.py` 的 R4 只认
            title / ylab2 / legend / yoy.name 这四处，所以两处都写。
          · **图注印代价** —— `mom_cost_zh()` 拿这条序列自己、在**本图这个窗口**里
            实测（§6.1 第 3 条）。不许写「看着更灵敏」，也不许写「滚动更好但没用」。

        存量列走点对点同比（§6.1 第 2 条：12 个月末快照相加不指代任何量），
        它本来就是这个口径，不受这次改动影响 —— 也因此没有「换口径的代价」可报。
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
                self.log_yoy_bar(n, c, win, 'stock', 'bar_yoy',
                                 f'groups「{gz}」.mix 的合计柱（存量）')
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
                   f'那是一句关于自己算术的假话（CONTRACT §6.1 第 2 条）。'
                   if rhs else NO_YOY_NOTE)
                + f'{xl[-1]} {unit_txt(v[-1], c)}，'
                + (f'同比 {chg_txt(c, v)}、环比 {chg_txt(c, v, lag=1)}。'
                   if rhs else f'环比 {chg_txt(c, v, lag=1)}。')
                + '<b>存量与本页的流量列不能相加</b>：流量按月累计发生，存量是某一天的截面。'
                + (self.near_zero_guard(n, c, win, rhs) if rhs else '')
                + self.slow_tail([c])
                + (self.brk_zh(hit, win) + '。' if hit else '')
                + (' ' + md_bold(m['note']) if m['note'] else ''))
            return ex, None

        ex = bar_ex(n, f'{gz}：{c["zh"]} —— 水平值与单月同比', c, xl, v, rhs,
                    ylab2='% y/y（单月）')
        if rhs:
            self.log_yoy(n, 'mom')
            self.log_yoy_bar(n, c, win, 'mom', 'bar_yoy', f'groups「{gz}」.mix 的合计柱')
        hit = self.mark_breaks(ex, win, [c])
        ex['note'] = (
            f'深蓝柱 = {c["zh"]}的<b>水平值</b>（{c["unit"]}，原始单位，未做任何指数化）。'
            f'{self.win_zh(win)}。'
            + (f'金色折线（右轴）= <b>单月同比</b>（当月对去年同月，'
               f'{c["col"]} 自己除自己，不换列、不做任何还原）。'
               if rhs else NO_YOY_NOTE)
            + f'{xl[-1]} 水平值 {unit_txt(v[-1], c)}，同比 {chg_txt(c, v)}、'
              f'环比 {chg_txt(c, v, lag=1)}。'
            + (self.mom_cost_zh(n, c, win) if rhs else '')
            + (self.near_zero_guard(n, c, win, rhs) if rhs else '')
            + self.slow_tail([c])
            + (self.brk_zh(hit, win) + '。' if hit else '')
            + (' ' + md_bold(m['note']) if m['note'] else ''))
        return ex, None

    def ex_mix_abs(self, n, gz, m):
        """`mix` 的 `abs_stack` 支：**绝对值**堆叠柱（一个月一根柱，段 = 各分项）。

        与 `ex_mix_share` 的分工是一句话：那张答「结构」（段高恒和为 100%），
        这张答「规模 + 结构」（柱高 = 合计的水平值，段高 = 分项的水平值）。
        所以本页开了 abs_stack 就不再出合计柱 —— 柱高已经把合计讲完了。

        加总关系逐月复算，三条硬失败与 `ex_mix_share` 逐字同源（残差为负、
        残差超容差却没命名、命名了却恒为 0）。差别只有一处：**这里不做「各段之和
        = 100」那道收尾自检**，改成量「各段之和 = 合计」——单位不同，判据也不同。

        ⚠️ 不给 `yoy`、也不给 `avg12`：kind 是 `stacked_dual` 不是 `gs_bar`，
        `build/verify_pages.py` 那条「gs_bar 必须有 avg12 或 yoy」不适用；
        而真给一条次轴同比，它与开篇头条图那条金线是同一列同口径的同一个数组。
        """
        tot_c, parts = m['total'], m['parts']
        cols = [tot_c] + parts
        win = self.mix_window(cols)
        got = 0 if win is None else len(win)
        if got < MIX_MIN_MONTHS:
            return None, (f'{gz}：合计与全部分项都有值的连续窗口只有 {got} 个月'
                          f'（不足 {MIX_MIN_MONTHS} 个月），绝对值堆叠柱不出 —— '
                          f'stacked_dual 是 DENSE 图型，窗口只能截不能补')
        xl = [mlab(p) for p in win]
        tv = self.vals(tot_c, win)
        pvs = [self.vals(c, win) for c in parts]
        if self.flat0_skip(gz, [tot_c], win, [tv]):
            return None, f'{gz}：{tot_c["zh"]} 窗口内恒为 0，绝对值堆叠柱不出'
        resid = tv - np.sum(pvs, axis=0)
        # 残差的判据用**相对值**（÷ 合计），与 MIX_RESID_TOL 同量纲；
        # 绝对值堆叠里合计可以是 0 以外的任何正数，所以先挡掉 ≤0 的月份。
        if float(np.min(tv)) <= 0:
            k = int(np.argmin(tv))
            return None, (f'{gz}：{tot_c["zh"]} 在 {mlab(win[k])} 为 '
                          f'{fmt_val(tv[k], tot_c["fmt"])}（≤0），残差判据无定义，本图不出')
        rel = resid / tv
        k_lo, k_hi = int(np.argmin(rel)), int(np.argmax(rel))
        if float(rel[k_lo]) < -MIX_RESID_TOL:
            raise SpecError(
                f'groups「{gz}」.mix（abs_stack）：分项之和在 {mlab(win[k_lo])} '
                f'**超过**合计 {abs(float(rel[k_lo])) * 100:.4g}%'
                f'（{tot_c["zh"]} {fmt_val(tv[k_lo], tot_c["fmt"])} vs 分项之和 '
                f'{fmt_val(float(tv[k_lo] - resid[k_lo]), tot_c["fmt"])}）—— '
                f'子集关系不成立时柱高不再是合计，而图上只会画成一根更高的柱')
        big = float(rel[k_hi])
        if big > MIX_RESID_TOL and not m['residual_zh']:
            raise SpecError(
                f'groups「{gz}」.mix（abs_stack）：'
                f'{"、".join(c["zh"] for c in parts)} 之和并不等于 {tot_c["zh"]} —— '
                f'残差最大出现在 {mlab(win[k_hi])}，占合计 {big * 100:.4g}%'
                f'（{fmt_val(float(resid[k_hi]), tot_c["fmt"])} {tot_c["unit"]}）。'
                f'柱高声称是合计，所以那一块必须画出来：'
                f"请给 mix 加一个 'residual_zh' 说清楚它是什么")
        if big <= MIX_RESID_TOL and m['residual_zh']:
            raise SpecError(
                f'groups「{gz}」.mix（abs_stack）声明了 residual_zh='
                f'{m["residual_zh"]!r}，但窗口内 {mlab(win[0])}–{mlab(win[-1])} '
                f'分项之和逐月恰等于合计（最大残差 {big * 100:.2g}%，在容差 '
                f'{MIX_RESID_TOL:.0e} 之内）—— 一条恒为 0 的「其他」段会让读者'
                f'以为存在一块查不到的业务。请删掉它')

        neg = [(parts[i]['zh'], mlab(win[int(np.argmin(pv))]),
                float(np.min(pv))) for i, pv in enumerate(pvs) if float(np.min(pv)) < 0]
        if neg:
            raise SpecError(
                f'groups「{gz}」.mix（abs_stack）：这些分项在窗口内出现负值 '
                + '；'.join(f'{zh} 在 {m} 为 {v:.6g}' for zh, m, v in neg)
                + ' —— 引擎的 stacked_dual 把正段自 0 向上堆、负段削成零高度不画，'
                  '于是柱顶落在**正段之和**上而不是合计；一个负分项配一个补偿的正分项'
                  '还能让「各段之和 = 合计」这道收尾自检照常通过，图上却已经画错。'
                  'build/verify_pages.py 的负段 ERROR 只覆盖 gs_bar，接不住这一种，'
                  '所以在这里硬失败')

        palette = MIX_SEG_COLORS[len(parts)]
        segs = [(c['zh'], pvs[i], palette[i]) for i, c in enumerate(parts)]
        if m['residual_zh']:
            segs.append((m['residual_zh'], np.maximum(resid, 0.0), MIX_RESID_COLOR))
        # 收尾自检：各段之和逐格等于合计。量的是**绝对值**，所以容差按合计折算回来。
        ssum = np.sum([sv for _z, sv, _c in segs], axis=0)
        off = float(np.max(np.abs(ssum - tv) / tv))
        if not off <= MIX_RESID_TOL + 1e-12:
            raise SpecError(f'groups「{gz}」.mix（abs_stack）：各段之和偏离合计达 '
                            f'{off:.3e}（相对，上限 {MIX_RESID_TOL:.0e}）—— 底座算错了')

        ex = {
            'n': n, 'kind': 'stacked_dual', 'height': 340,
            'fmt': tot_c['fmt'], 'xrot': 90,
            'title': f'{gz}：各分项绝对值堆叠（柱高 = {tot_c["zh"]}）',
            'xlabels': xl,
            'ylab': tot_c['unit'],
            'stacks': [{'name': zh, 'color': cc, 'values': LN(sv), 'label': False}
                       for zh, sv, cc in segs],
            'src_extra': ('Segments are the disclosed components in original units; '
                          'they sum to the disclosed total on the same row'),
            '_cols': [tot_c['col']] + [c['col'] for c in parts],
        }
        hit = self.mark_breaks(ex, win, cols)
        tiny = [zh for zh, sv, _c in segs
                if float(np.max(sv / tv)) * 100 < MIX_TINY_SEG_PCT]
        ex['note'] = (
            f'一个月一根柱，柱高 = {tot_c["zh"]}的<b>水平值</b>'
            f'（{tot_c["unit"]}，原始单位，未做任何指数化、未做占比归一）；'
            f'自下而上按声明顺序分段：'
            + '、'.join(f'<b>{zh}</b>' for zh, _sv, _c in segs) + '。'
            + f'{self.win_zh(win)}。'
            + f'{xl[-1]} 合计 {unit_txt(tv[-1], tot_c)}，其中 '
            + '、'.join(f'{zh} {fmt_val(float(sv[-1]), tot_c["fmt"])}'
                        for zh, sv, _c in segs) + '。'
            + ('本图<b>不画次轴同比</b>：这几条序列的单月同比在页内别处已经画过，'
               '同一个数组在一页上画两遍不带新信息；本图回答的是'
               '「规模有多大、由哪几块构成」。'
               )
            + (f'<b>{"、".join(tiny)}</b> 占合计的峰值也不到 '
               f'{MIX_TINY_SEG_PCT}%，扣掉段间白缝之后在图上几乎没有高度 —— '
               f'它照样占一格图例、在上面的读数里也有，但别指望在柱上找到它。'
               if tiny else '')
            + self.slow_tail(cols)
            + (self.brk_zh(hit, win) + '。' if hit else '')
            + (' ' + md_bold(m['note']) if m['note'] else ''))
        return ex, None

    def ex_mix_share(self, n, gz, m, total_n=None, total_zh='合计柱'):
        """`mix` 的第二张：分项占合计的比重，**100% 堆叠柱**（`stacked_dual`）。

        `total_n` / `total_zh` 是「合计的绝对量看第几张、那张在页面上叫什么」——
        **两个都由调用方现算**（`mix_pair`）。图号会随增删图整体位移，名字则会随
        「指的是本组自己那张合计柱、还是别处那张更宽的图」换人：折叠那一档下页面上
        没有任何地方管被指的那张叫「合计柱」，写死这三个字就是一块解析不出去的指路牌。

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
            # 线色不能与**任何一段**撞。⚠️ **理由 2026-09 换过一次**：从前是
            # 「polyline 无描边、同色时它穿过那一段整段看不见」，而引擎现在给
            # `stacked_dual` 的这条右轴线打了一层白 casing（`assets/charts.js` 的
            # `polyline(…, halo)`），线**恒有一个形状**，「整段看不见」不再成立。
            # 但禁令照旧，换了个理由：casing 保证的只是「线色 vs 白」那条内边，
            # 同色时白边两侧仍是同一个颜色 —— 读者看到的是一条被白线镶了两道边的
            # 段色带，认不出哪一半是线、哪一半是它压着的段；而且图例里同一个色块
            # 要同时指一段和一条线，那张图的色→量对应当场断掉
            # （`build/mrbase.py` 的 `_SEG_COLORS` 上方记着同源的实测教训）。
            # 从前写死 GREEN，而 GREEN 现在进了 5 段那档的配色表 —— 那就是一颗定时炸弹。
            used = {cc for _z, _v, cc in segs}
            c_line = next((x for x in ('GREEN', 'GOLD', 'MBLUE', 'BLUE') if x not in used),
                          None)
            if c_line is None:
                raise SpecError(
                    f'groups「{gz}」.mix 要画右轴线，但 6 个数据色已经被 {len(segs)} 段'
                    f'占满（{"、".join(sorted(used))}），没有一个色留给这条线 —— '
                    f'同色的线与它压着的那一段在图上、在图例里都分不开'
                    f'（引擎给这条线打的白 casing 只镶边，不解决同色）。'
                    f'要么去掉 rhs_share，要么先把小分项并进残差')
            ex['line'] = {'name': f'{zh_r}（RHS）', 'color': c_line, 'values': LN(sv_r),
                          # 右轴下界被引擎写死成 0，只能调上界；留 15% 顶空免得线贴轴顶。
                          'ymax': nice_max(float(np.max(sv_r)) * 1.15)}
            ex['ylab2'] = f'{axis_short(zh_r)}，%（右，同一条序列换个刻度）'
            # 色名跟着 `c_line` 现查，**不写死「绿」**。从前这两句写死 GREEN，而线色
            # 早就是上面那行 next(...) 挑出来的：4 个分项就把 GREEN 用掉了（见
            # MIX_SEG_COLORS 的 4 段档），/asx/ 两张占比图实际拿到的是 GOLD ——
            # 于是页面上印着「绿线」而画出来是金色，读者对不上是哪一条。
            # ⚠️ 拿到 GOLD 本身是**退而求其次**：本站金色是同比线专用色（引擎给
            # `gs_bar` 的 `yoy` 写死 GOLD），一条非同比的金线会和满页的同比金线撞语义。
            # 要根治得把 GOLD 从候选里拿掉，而那会让 4 分项的图当场无色可用 ⇒ 必须先重排
            # MIX_SEG_COLORS，那张表是在「MBLUE 与 GREEN 不许相邻」约束下跑全排列
            # 最大化最小相邻对比度得来的，改一档要重跑优化并重验全站堆叠图的对比度。
            # 那是单独一轮的事，这里只把话说对，不动配色。
            zh_line = {'GREEN': '绿', 'GOLD': '金', 'MBLUE': '中蓝', 'BLUE': '浅蓝'}[c_line]
            rhs_line = (f'<b>右轴那条{zh_line}线不是新的量</b>：它就是「{zh_r}」这一段'
                        f'换成 0–{ex["line"]["ymax"]}% 的刻度重画一遍 —— '
                        f'这一段在 0–100 的堆叠里只占几个百分点，几 pp 的变化在那里量不出来。'
                        f'柱顶上方那排{zh_line}色的百分比是它的读数（`assets/charts.js` 的 '
                        f'thinLabels 会按密度抽稀，不是每一期都标；逐格读数走「表格」）。'
                        + ('⚠️ 本站金色在别处是<b>同比线</b>专用色（本页另有多张图的右轴'
                           '金线画的是单月同比）；这一条是<b>占比</b>，不是同比 —— '
                           '它拿到金色是因为堆叠的各段已经把其余数据色占满了。'
                           if c_line == 'GOLD' else ''))
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
            # 被指的那张图只画合计那一条列，分项的水平值只在末尾核对表里。
            # 括号里的名字由调用方现算（见本函数 docstring 的 `total_zh`）。
            + (f'<b>合计</b>的绝对量看 Exhibit {total_n}（{total_zh}）；' if total_n else '')
            + '<b>各分项</b>的绝对量在末尾核对表里（本图一个绝对量都没画）。'
            + rhs_line
            # 反向那句与比值线那张图共用同一份现算的差值**和同一句 `dup_note`**：
            # 两边各写死一句「口径不同」的时候，它既证不了、又会各自漂。
            + (f'<b>「{_db["part_zh"]}」这一段在本页出现两次。</b>'
               f'「{_db["gz"]}」那张图的右轴画的是<b>{_db["ratio_zh"]}</b>，'
               f'而它 ≡ 100% − 本段占比 —— 同一个数的两种读法。'
               + (_db['note'] or '')
               + f'逐月绝对差实测最大 {_db["max"]:.4f}pp（{_db["max_at"]}）、'
               f'中位 {_db["med"]:.4f}pp（{_db["n"]} 个共同月份，构建期逐月复算）。'
               f'分工：本图答「各分项各占多少」，那条线答「那一段有多厚」。'
               if (_db := m.get('dup_back')) else '')
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

    # ═══════════ exhibit：量价分解（decomp）的取数口径 ═══════════
    # 上一版这行写的是「量价分解 与 12 个月滚动同比（共用的取数口径）」—— 那个「共用」
    # 在 2026-09 断了：`level_yoy` 的次轴改成单月同比（本列除本列）之后不再需要把日均
    # 还原成当月合计，`monthly_total()` 现在只有 `ex_decomp` 一个调用方。
    def monthly_total(self, c, total_col, weight_col, gran, where, bucket='year'):
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
        # 日均、又没有任何权重列可用。
        #
        # ⚠️ **这一支的措辞按 bucket 分岔**，因为「等权相加」这件事只在年度桶里发生。
        # 月度桶（`bucket='monthly'`）横轴一格就是一个月、基期是去年同月，全程**没有
        # 任何一次跨月相加**：既不需要还原成当月合计，也不存在权重偏差。把年度桶那句
        # 警告原样印在月度图上，是在这张图上凭空承认一个它根本没犯的错 —— 与本函数
        # 上一次被抓到的病（无条件印「本身即当月合计口径」）同型，只是方向相反。
        if bucket == 'monthly':
            return s, (f'<code>{c["col"]}</code> 是<b>当月日均</b>，而月度桶的一格'
                       f'就是一个月、基期是去年同月，<b>全程不做任何跨月相加</b> —— '
                       f'所以既不需要还原成当月合计，也没有各月交易日数不同带来的'
                       f'权重偏差。日均除日均，立会日数在分子分母上自己约掉了')
        # 年度桶：**必须把话说满**。等权相加是一个近似，偏差随各月交易日数的离散程度
        # 走，本页量不出来（没有交易日列就是没有）。早先这里无条件印「本身即当月合计
        # 口径」——对日均列那是一句假话，而 verify_pages 只看 payload 结构、
        # 看不出图注对不对。
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

    def ex_decomp(self, n, d, built=None):
        """金额增长 → 量的贡献 + 派生量的贡献。

        **横轴一格是什么由 `d['bucket']` 决定**（2026-09 新增，缺省 `'year'`）：

          `'year'`   一格 = 一个完整年度，最新年不完整时末格追加一根 YTD 柱
                     （同比基期对齐到去年同期月份，见 `_ytd`）。以下整段讲的是它。
          `'monthly'` 一格 = 一个月，基期 = 去年同月（= 单月同比，与全站同口径）。
                     整条路径在 `_decomp_monthly()` 里，本方法只做**共用的取数**
                     （`monthly_total` 两列 + bench 两列）就转过去。
                     年度那一支的 `_years()` / `_ytd()` 它一个都不调 ——
                     每格只有一个月，「完整年度」「YTD 覆盖几个月」都无从谈起。

        `built` 是**本页已经建好的那些 exhibit**（`payload()` 里那个列表）。
        月度分支拿它做构建期现验：菱形与输入那张图的次轴金线必须逐点相同。
        年度分支用不到（年度桶与本页任何一张月度图都不同轴，无从逐格对读）。
        ⚠️ 图注里那句**页面级**的「中蓝段对应哪一张」不在这里定 —— 它扫的是全页，
        由 `Page._pleg_fill()` 在全部 exhibit 建完之后回填，这里只埋占位符。

        ── 以下是年度桶（`bucket='year'`）的口径说明，逐字未动 ──
        横轴一格 = 一个完整年度；最新年不完整时**末格追加一根 YTD 柱**
        （同比基期对齐到去年同期月份，见 _ytd）。

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
                                        gran, f'decomp「{d["zh"]}」的金额列',
                                        bucket=d['bucket'])
        q_s, q_how = self.monthly_total(d['qty'], d['qty_total_col'], d['weight_col'],
                                        gran, f'decomp「{d["zh"]}」的数量列',
                                        bucket=d['bucket'])
        bench = bool(d['bench_value'] and d['bench_qty'])
        need = [v_s, q_s]
        bv_s = bq_s = None
        if bench:
            # 行业对照走**同一条** monthly_total（同一套 total_col / weight_col / 粒度）——
            # 自家按合计、行业按日均的话，份额 s 会带一个逐月漂移的假趋势。
            bv_s, _ = self.monthly_total(d['bench_value'], None, d['weight_col'],
                                         gran, f'decomp「{d["zh"]}」的行业金额列',
                                         bucket=d['bucket'])
            bq_s, _ = self.monthly_total(d['bench_qty'], None, d['weight_col'],
                                         gran, f'decomp「{d["zh"]}」的行业数量列',
                                         bucket=d['bucket'])
            need += [bv_s, bq_s]
        # 本图的**输入列**（两支共用，拼装顺序与 `need` 同源）。页尾那段断点说明要拿它
        # 现算「这张图的列上到底登记没登记断点」—— 见 `note_nodraw_cols()`。
        # 只在图真出得来的那一刻才记账（两支各自在 `return ex, None` 之前调）。
        cols_in = ([d['value'], d['qty']]
                   + ([d['bench_value'], d['bench_qty']] if bench else []))

        # 每格合计的单位**不是**展示列的单位（日均列的 12 个月合计是「兆円/年」，
        # 不是「兆円/日」），拿展示单位去标它就是印错单位。所以图注里报的是把该格合计
        # 除回展示口径的**窗口内均值**：有权重列就除以同窗口权重合计（= 窗口内日均，
        # 与日均列同单位），没有就除以窗口月数（完整年 = 12，YTD = 实际月数；
        # 月度桶 = 1，于是「除回展示口径」在那一支自动成立）。两种都回到展示单位。
        wcol = self.df[d['weight_col']].astype(float) if d['weight_col'] else None

        def agg_one(y, label, ms):
            """一个桶（完整年 / YTD 窗口 / 单个月）→ 行 tuple 或 (None, 原因)。

            行结构 (年份, V, Q, P, V均, Q均, BV, BQ, 月数)：完整年月数恒为 12，
            YTD 桶是实际入选月数，**月度桶恒为 1** —— 图注报「窗口内均值」时要用它
            当除数（月度桶下 div = 1，合计与均值是同一个数，正是想要的）。

            ⚠️ **返回的「原因」只说这一桶发生了什么，不说后果。**
            后果两个桶各不相同：年度桶 5 根柱，废一桶等于整张图不出（那一支自己在
            call site 补上「，不出这张图」）；月度桶 128 格，废一桶只废**这一格**，
            图照出、那一格进 `gaps_hole` 那本账。原文里写死「不出这张图」的话，
            月度桶把它原样带进图注就是印一句假话 —— 图明明出了。
            """
            V = float(v_s.reindex(ms).values.astype(float).sum())
            Q = float(q_s.reindex(ms).values.astype(float).sum())
            pre = f'{d["zh"]}：{label}的'
            if not (V > 0 and Q > 0):
                return None, (f'{pre}合计不是正数（金额 {V:g}、数量 {Q:g}），'
                              f'比值与对数都没有定义')
            div = (float(wcol.reindex(ms).values.astype(float).sum())
                   if wcol is not None else float(len(ms)))
            if not div > 0:
                return None, f'{pre}{d["weight_col"]} 合计为 {div:g}，除不回展示口径'
            row = [y, V, Q, V / Q * d['price_scale'], V / div, Q / div, None, None, len(ms)]
            if bench:
                BV = float(bv_s.reindex(ms).values.astype(float).sum())
                BQ = float(bq_s.reindex(ms).values.astype(float).sum())
                if not (BV > 0 and BQ > 0):
                    return None, (f'{pre}行业合计不是正数'
                                  f'（金额 {BV:g}、数量 {BQ:g}），份额与相对价没有定义')
                row[6], row[7] = BV, BQ
            return tuple(row), None

        if d['bucket'] == 'monthly':
            # 月度桶从这里分出去，**共用上面这个 `agg_one`**（桶是「一个月」而已）。
            # **年度那一支以下一个字都没改**：不把它整段包进一个 `if` 里，是因为那要给
            # 三百行重排缩进 —— 改动面变成整段、diff 里看不出「哪一行的语义动了」，
            # 而另外 5 页 9 条 decomp 全靠这一段逐字节不变。上移的只有 `wcol` 与
            # `agg_one` 两块（连注释一并搬，文本未改），它们不依赖年度桶的任何东西。
            e_, why_ = self._decomp_monthly(n, d, v_s, q_s, v_how, q_how,
                                            bench, need, agg_one, built)
            if e_ is not None:
                self.note_nodraw_cols(e_, cols_in)
            return e_, why_

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

        agg = []
        for y, ms in sel:
            row, err = agg_one(y, f'{y} 年', ms)
            if err:
                # 后果由 call site 补（`agg_one` 只说发生了什么）：年度桶一共 5 根柱，
                # 废掉一桶就没有「相对上一年」可比，整张图不出。
                return None, f'{err}，不出这张图'
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
                return None, f'{err}，不出这张图'
            base, err = agg_one(y_t - 1, f'{lab_t} 的同比基期（{ms_prev[0]}…{ms_prev[-1]}）',
                                ms_prev)
            if err:
                return None, f'{err}，不出这张图'
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
        self.note_nodraw_cols(ex, cols_in)      # 年度桶同样不挂断点线，见那个方法
        return ex, None

    #: 净额菱形在引擎里写死的半径（`assets/charts.js` 的 `diamond(…, 3.2, …)`），
    #: 与 bridge_bar 的柱宽系数（同文件那一支的 `BW(0.70)`）。
    #: 两个数**只**用来算「有多少格的薄段会被菱形盖住」这一个计数，不进任何画出来的值。
    DIA_R_PX, BRIDGE_BW = 3.2, 0.70
    #: bridge_bar 的绘图区高（px）。`charts.js`：H = 268 + XB（bridge_bar 属
    #: perPointLabels 那一档）、M.t = fscale(14)（本图型没有 ycap/yfloor，capOn 恒 false）、
    #: M.b = XB ⇒ ph = 268 − 14 = 254。桌面 FS = 1；窄屏更挤，是同一结论的加强版。
    BRIDGE_PLOT_PX = 254.0

    def _decomp_yoy_refs(self, built, xl):
        """本页横轴与 `xl` 逐格相同的那些**单列 + 有次轴同比**的图 → [exhibit, …]。

        `_cols` 是各 ex_* 挂的临时键（这张图画了哪几列），`payload()` 末尾才 pop 掉 ——
        所以在 groups 循环里就地出图的分解图拿得到它。按**列**认图而不是按标题认，
        标题是文案、会改；列名是数据。

        两处调用给的 `built` **范围不同，而且必须不同**：
          · `_decomp_monthly` 找输入那两张图（菱形认领的金额列、深蓝段认领的数量列）
            传的是**当前累积到一半**的 ex 列表 —— 「分解图紧跟它的输入」正是
            `after_group` 的全部理由，输入必须已经在场；
          · `_pleg_fill` 找中蓝段那句话的候选传的是**全页** —— 那句话说的是「本页」，
            判据的范围必须与断言的范围一致（见那个方法的 docstring）。
        """
        out = []
        for e in (built or []):
            if len(e.get('_cols') or []) != 1 or not e.get('yoy'):
                continue
            if (e.get('xlabels') or []) != xl:
                continue
            out.append(e)
        return out

    @staticmethod
    def _pair_gap(a, b):
        """两条等长的「%」序列（含 None）→ 逐格最大绝对差（pp）与可比格数。"""
        dif = [abs(x - y) for x, y in zip(a, b) if x is not None and y is not None]
        return (max(dif) if dif else float('nan')), len(dif)

    @staticmethod
    def _round_quantum(vals):
        """一条列**自己的取整粒度** δ —— 从它的实测值现算，不写死。

        源表里的每一格都是十进制文本，写到哪一位就是那一列的取整粒度：整数张数
        δ=1，两位小数 δ=0.01。这里取「让全部值都成为 δ 的整数倍」的最大那个
        10 的整数次幂，也就是这一列上**观测得到**的最细一档。

        ⚠️ 它算出来的**两个方向都可能偏**，不是无条件的上界：
          · 源表报到两位小数、而观测到的每一格恰好都以 0 结尾 ⇒ 这里把粒度看成 0.1，
            **比真 δ 粗**；
          · 源表按千 / 百万报数（全部观测值都是 10 的更高次幂的倍数）⇒ 这里照旧返回
            10⁰ = 1，**比真 δ 细**。
        要说清楚的是前一档，因为它让门槛更**宽松**：δ 看粗一档 ⇒ 下面那个 pp 上界更大
        ⇒ 「差异量级就是取整」这句话更容易被放行。所以它不是一道保守闸门，而是一道
        **够用**的闸门：真正要挡的那一档（页上一条毫不相干的列，差着几十个百分点）
        δ 相对自身量级小好几个数量级，宽松几倍也照样挡得住；而它要放行的那一档
        （真是同一个派生量、只差在取整）本来就贴着上界。后一档只会让本函数更严
        （门槛更小、更不敢署名），落进去的后果是不署名而不是错署名。
        算不出（没有有限值）返回 None。
        """
        fin = [float(v) for v in vals if np.isfinite(v)]
        if not fin:
            return None
        k = 0
        for v in fin:
            while k < 9 and abs(round(v, k) - v) > 1e-9 * max(1.0, abs(v)):
                k += 1
        return 10.0 ** (-k)

    def _round_yoy_bound(self, col, win, other, ref_yoy):
        """一条列的取整粒度最多能让它的**单月同比**偏多少百分点（pp）。

        用处只有一个：`_decomp_monthly` 那句「那一列画的正是本图这个派生量
        （…最大差只有 X pp —— 差异量级就是该列自己的取整）」是**可证伪的断言**，
        这里把它自己声称的东西算出来当门槛。实测差 ≤ 本上界才敢署那一列的名。

        算法是区间端点，不做线性近似：每格的真值落在 [x−δ/2, x+δ/2] 里，于是同比
        x₁/x₀−1 能取到的最大值是 (x₁+δ/2)/(x₀−δ/2)−1、最小值是 (x₁−δ/2)/(x₀+δ/2)−1，
        本格的上界就是这两端离 x₁/x₀−1 较远的那一侧，×100 换成 pp；
        全窗口取各格的最大值。
        只统计**两条线都画得出来**的那些格（与 `_pair_gap` 的可比集合一致：
        断言比的是那一批格，门槛就得量同一批格）。基期非正的格跳过 ——
        `yoy_line` 本来就把它们掩成 null，不进可比集合。

        一格都算不出来返回 nan ⇒ 调用方不署名，改印那句点名「最接近的是哪一张、
        差多少、为什么仍不署名」的话（见 `_decomp_monthly` 里 `p_near` 那一支）。
        """
        if col not in self.df.columns:
            return float('nan')
        s = self.df[col].astype(float)
        dq = self._round_quantum(s.values)
        if dq is None:
            return float('nan')
        h, worst, n = dq / 2.0, 0.0, 0
        for i, p in enumerate(win):
            if i >= len(other) or i >= len(ref_yoy):
                break
            if other[i] is None or ref_yoy[i] is None:
                continue
            x1, x0 = float(s.get(p, np.nan)), float(s.get(p - 12, np.nan))
            if not (np.isfinite(x1) and np.isfinite(x0)) or x0 <= h or x1 < 0:
                continue
            r = x1 / x0
            worst = max(worst, 100.0 * max((x1 + h) / (x0 - h) - r,
                                           r - (x1 - h) / (x0 + h)))
            n += 1
        return worst if n else float('nan')

    def _decomp_monthly(self, n, d, v_s, q_s, v_how, q_how, bench, need, agg_one, built):
        """`bucket='monthly'` 那一支：**一格 = 一个月，本期该月、基期去年同月**。

        方法与三道护栏与年度桶完全一样（恒等式 → 对数分解 → 按总增长重标定），
        换的只有桶。口径纪律逐条对着 `build/cme.py` 的月度量价分解抄（那是页面所有者
        亲自下过两轮同样指令之后定下来的判例）：

        （1）桶 = 一个月，本期该月、基期去年同月 = **单月同比**，与本页所有月度图和
             汇总表 y/y 同口径（CONTRACT §6：全站只有这一种）。年度版那两条
             「YTD 基期要逐月对齐」「YTD 柱不能与完整年柱比大小」随之作废 ——
             每格覆盖的月数都是 1，格与格本来就可比。
        （2）单月桶里**没有任何平均**：P = 当月金额 ÷ 当月数量。年度版那段
             「Σ金额 ÷ Σ数量，不是逐月简单平均」在这里解释的是一个不存在的陷阱，不印。
        （3）图上画对数分解按总增长重标定后的两块；算术版照算，只进图注。
        （4）|ln(V₁/V₀)| < `DECOMP_LN_MIN` 整格留空。规则留着 —— 它防的是极端巧合，
             「这轮没命中」不是删兜底的理由。
        （5）算术闭合 / 对数闭合 / 重标定闭合三道残差超限一律 raise。

        ⚠️ **payload 里一个字都不写 `xrot` / `full` / `height` / `xstep`。**
        `build/mrwin.py` 的 `layout_all` 见 `xrot == 0` 就整张 `continue`，既不判通栏
        也不抽标签 —— 128 格会以每格 3.9px 塞进半栏卡片，而引擎、`verify_pages`、
        `visual_qa` **全都不报错**。年度桶那句「年度类别轴：标签不斜排」是对的，
        照抄到月度轴上就是这个坑（`build/cme.py` 的 `EX_DECOMP` 为同一件事留了明文警告）。
        排版一律交给 `self._layout_long(ex)` → `mrwin.layout_all()`。
        """
        vc, qc = d['value'], d['qty']
        end = self.last_month(vc)
        if end is None:
            return None, f'{d["zh"]}：{vc["col"]} 整列为空，月度分解一格都画不出来'
        win = self.win_long(end)
        xl = [mlab(p) for p in win]
        idx = set(self.df.index)

        # ── 横轴现验①：本页必须有一张「金额列的水平值 + 次轴单月同比」图，
        #    而且横轴与本图**逐格相同**。图注要声称「可以逐格上下对读同一个月」，
        #    还要声称「菱形就是那条金线」—— 两句话都得有一张真图在场才成立。
        refs = self._decomp_yoy_refs(built, xl)
        val_ref = [e for e in refs if e['_cols'] == [vc['col']]]
        if len(val_ref) != 1:
            same_col = [e['n'] for e in (built or []) if (e.get('_cols') or []) == [vc['col']]]
            raise SpecError(
                f'decomp「{d["zh"]}」bucket=\'monthly\'：本页找不到唯一一张'
                f'「{vc["col"]} 的水平值 + 次轴单月同比、且横轴与本图逐格相同」的图'
                f'（找到 {len(val_ref)} 张；画了这一列的图号：{same_col}，'
                f'本图横轴 {len(xl)} 格 {xl[0]}…{xl[-1]}）—— '
                f'没有它，图注里「菱形与那张图的金线是同一条数」「可以逐格上下对读」'
                f'两句话都无从现验，而这两句话正是把分解图前移到输入之后的全部理由')
        v_ref = val_ref[0]
        qty_ref = [e for e in refs if e['_cols'] == [qc['col']]]

        # `need` 逐条对应的列名（拼装顺序抄自 `ex_decomp`：先 value / qty，
        # 有 bench 再追加行业两列）。留空格要点名「哪一列、哪个月缺值」——
        # 光说「留空」等于让读者猜。顺序一旦对不上就当场报错：点错列名比不点名更糟。
        need_names = ([vc['col'], qc['col']]
                      + ([d['bench_value']['col'], d['bench_qty']['col']] if bench else []))
        if len(need_names) != len(need):
            raise SpecError(
                f'decomp「{d["zh"]}」：need 有 {len(need)} 条序列、列名表只有 '
                f'{len(need_names)} 个 —— `ex_decomp` 里 need 的拼装顺序改过了，'
                f'这里必须跟着改，否则留空格会点错列名')
        _pre = f'{d["zh"]}：'      # `agg_one` 原文自带的图名前缀，见下面 `_why` 的说明

        def _why(msg):
            """`agg_one` 的原文 → 去掉「<图名>：」前缀之后的那一句。

            前缀是给年度桶用的（那一支的原因会进 `self.skipped`，混在别的图里，
            不带图名认不出是谁）。这里的原因印在**这张图自己**的图注与自检行里，
            前缀原样留着就是每一格重复一遍图名。除前缀之外一个字不改 ——
            「合计不是正数（金额 …、数量 …）」那种话必须是构建期原文，不许转述。
            """
            return msg[len(_pre):] if msg.startswith(_pre) else msg

        pairs = [(mlab(p), [p], [p - 12]) for p in win]
        xl2, c_q, c_p, net, rows, blanks = [], [], [], [], [], []
        # ── 留空分**两本账**（2026-09 拆开，之前是合成一个 `gaps` 列表）────────────
        #   `gaps_base` 基期那一行**不在本表里**。本表索引在 `load()` 里补成连续月份，
        #              所以这一档等价于「基期落在本表首月之前」= 真·左端连续一段。
        #   `gaps_hole` 基期就在表里，废掉这一格的是**输入自己**：源表那一格空着，
        #              或者 `agg_one` 判定这一桶取不了对数（合计不是正数等）。
        # 合成一本的代价实测过（红队注入 `trades_cash_total` 的 2022-05 / 06 两个洞）：
        # 图注与自检行照旧印「另有**左端** 16 格（Jan-16 – Jun-23）留空……它们的基期
        # 落在本表首月之前，源表里根本没有那一行」—— 其中 May-22 / Jun-22 / May-23 /
        # Jun-23 四格的基期**全都在表内**，读者被告知一个错误的原因；而「左端 N 格
        # （首 – 末）」的措辞还把中段的两个洞伪装成一段横跨七年半的连续左边界。
        gaps_base, gaps_hole = [], []
        c_b, c_s, c_m = [], [], []
        for lab, ms1, ms0 in pairs:
            p1, p0 = ms1[0], ms0[0]
            xl2.append(lab)
            # 基期不在索引、或任一列两侧任一月缺值 ⇒ **c_q / c_p / net 三处同时留空**。
            # 只留一处会撞底座那道「菱形留空但堆叠段有值」的护栏（下面护栏④）。
            r1 = r0 = None
            base_out = p0 not in idx
            hole = None
            if not base_out:
                miss = [f'{nm} 在{w} 缺值'
                        for nm, s in zip(need_names, need)
                        for w, p in ((f'本期 {lab}', p1), (f'基期 {mlab(p0)}', p0))
                        if not np.isfinite(float(s.get(p, np.nan)))]
                if miss:
                    hole = '、'.join(miss)
                else:
                    r1, e1 = agg_one(p1.year, '本期', ms1)
                    r0, e0 = agg_one(p0.year, f'同比基期（{p0}）', ms0)
                    # 单月桶里 agg_one 的报错（合计非正）只该废掉**这一格**，
                    # 不该废掉整张 128 格的图 —— 年度桶只有 5 根柱，那里返回 None 是对的。
                    # ⚠️ **只废一格不等于可以不说**：原文逐格带进 `gaps_hole`，
                    # 图注与自检行都点名到格、到原因，别让读者拿「留空」两个字去猜。
                    if e1 or e0:
                        hole = '；'.join(_why(x) for x in (e1, e0) if x)
            if base_out:
                gaps_base.append(lab)
            elif hole is not None:
                gaps_hole.append((lab, hole))
            if base_out or hole is not None:
                for arr in (c_q, c_p, c_b, c_s, c_m, net):
                    arr.append(np.nan)
                continue
            _y1, V1, Q1, P1, Va1, Qa1, BV1, BQ1, nm1 = r1
            _y0, V0, Q0, P0, _Va0, _Qa0, BV0, BQ0, _nm0 = r0
            gV, gQ, gP = V1 / V0 - 1, Q1 / Q0 - 1, P1 / P0 - 1
            cross = gQ * gP
            lV, lQ, lP = math.log(V1 / V0), math.log(Q1 / Q0), math.log(P1 / P0)

            # ── 硬护栏①：算术分解逐格闭合（三项，含交叉项）──────────────
            r_1 = gV - (gQ + gP + cross)
            if not abs(r_1) <= DECOMP_EPS:
                raise SpecError(
                    f'decomp「{d["zh"]}」{lab} 算术分解不闭合：量 {gQ:+.12f} + 价 {gP:+.12f}'
                    f' + 交叉 {cross:+.12f} = {gQ + gP + cross:+.12f}，'
                    f'总增长 {gV:+.12f}，残差 {r_1:+.3e} > {DECOMP_EPS:.0e}')
            # ── 硬护栏②：纯对数分解逐格闭合（本来就该零残差，没有交叉项）──
            r_2 = lV - (lQ + lP)
            if not abs(r_2) <= DECOMP_EPS:
                raise SpecError(
                    f'decomp「{d["zh"]}」{lab} 对数分解不闭合：量 {lQ:+.12f} + 价 {lP:+.12f}'
                    f' = {lQ + lP:+.12f}，总计 {lV:+.12f}，残差 {r_2:+.3e} > {DECOMP_EPS:.0e}')

            row = {'lab': lab, 'per': p1, 'V1': V1, 'Q1': Q1, 'P1': P1,
                   'V0': V0, 'Q0': Q0, 'P0': P0, 'Va1': Va1, 'Qa1': Qa1,
                   'gV': gV, 'gQ': gQ, 'gP': gP, 'cross': cross, 'lV': lV,
                   'w': np.nan, 'cq': np.nan, 'cp': np.nan}
            if abs(lV) < DECOMP_LN_MIN:
                # 整格留空：w = g_V/ln(V₁/V₀) 此时是 0/0，算出来的两块没有有效位。
                blanks.append(lab)
                for arr in (c_q, c_p, c_b, c_s, c_m, net):
                    arr.append(np.nan)
                rows.append(row)
                continue
            w = gV / lV
            cq, cp = w * lQ * 100, w * lP * 100
            # ── 硬护栏③：**画在图上的那两块**逐格相加 == 总增长 ────────────
            r_3 = gV * 100 - (cq + cp)
            if not abs(r_3) <= DECOMP_EPS:
                raise SpecError(
                    f'decomp「{d["zh"]}」{lab} 图上两块不闭合：量 {cq:+.12f}pp + 价 '
                    f'{cp:+.12f}pp = {cq + cp:+.12f}pp，总增长 {gV * 100:+.12f}%，'
                    f'残差 {r_3:+.3e} > {DECOMP_EPS:.0e}')
            row['w'], row['cq'], row['cp'] = w, cq, cp
            c_q.append(cq)
            c_p.append(cp)
            net.append(gV * 100)
            if bench:
                # V ≡ V_行业 × s × r（同年度桶那一支，定义式、零假设）。
                lBV = math.log(BV1 / BV0)
                ls = math.log((Q1 / BQ1) / (Q0 / BQ0))
                lr = math.log(((V1 / Q1) / (BV1 / BQ1)) / ((V0 / Q0) / (BV0 / BQ0)))
                r_5 = lV - (lBV + ls + lr)
                if not abs(r_5) <= DECOMP_EPS:
                    raise SpecError(
                        f'decomp「{d["zh"]}」{lab} 三分法不闭合：行业 {lBV:+.12f} + 份额 '
                        f'{ls:+.12f} + 结构 {lr:+.12f} = {lBV + ls + lr:+.12f}，'
                        f'总计 {lV:+.12f}，残差 {r_5:+.3e} > {DECOMP_EPS:.0e}')
                cb, cs_, cm = w * lBV * 100, w * ls * 100, w * lr * 100
                r_6 = gV * 100 - (cb + cs_ + cm)
                if not abs(r_6) <= DECOMP_EPS:
                    raise SpecError(
                        f'decomp「{d["zh"]}」{lab} 三块重标定后不闭合：'
                        f'{cb:+.12f} + {cs_:+.12f} + {cm:+.12f} = {cb + cs_ + cm:+.12f}pp，'
                        f'总增长 {gV * 100:+.12f}%，残差 {r_6:+.3e} > {DECOMP_EPS:.0e}')
                c_b.append(cb)
                c_s.append(cs_)
                c_m.append(cm)
            rows.append(row)

        if not any(np.isfinite(x) for x in net):
            return None, (f'{d["zh"]}：{len(xl2)} 格全部留空（两侧不齐，或落在 '
                          f'|ln(V₁/V₀)| < {DECOMP_LN_MIN:.0e} 的区间），一格都画不出来')

        kind_zh, kind_warn = DECOMP_KINDS[d['kind']]
        share_zh = d['share_zh'] or (f'{d["qty"]["zh"]}份额' if bench else '')
        mix_zh = d['mix_zh'] or (f'{d["price_zh"]}相对行业（品种结构）' if bench else '')
        ex = {
            'n': n, 'kind': 'bridge_bar', 'fmt': 'pct1', 'yfmt': 'pct0',
            # ⚠️ 不写 'xrot'（年度桶写的是 0）：见本方法 docstring 末尾那段。
            # full / height / xstep 同理一律不手写，交给 mrwin.layout_all()。
            'xlabels': xl2,
            'title': f'{d["zh"]}：增长的量价分解（一格 = 一个月，本期该月、基期去年同月）',
            'ylab': '% y/y（单月）', 'net_color': 'INK',
            'stacks': ([
                {'name': f'{d["bench_value"]["zh"]}的贡献', 'color': 'NAVY', 'values': LN(c_b)},
                {'name': f'{share_zh}的贡献', 'color': 'MBLUE', 'values': LN(c_s)},
                {'name': f'{mix_zh}的贡献', 'color': 'GREEN', 'values': LN(c_m)},
            ] if bench else [
                {'name': f'{d["qty"]["zh"]}的贡献', 'color': 'NAVY', 'values': LN(c_q)},
                {'name': f'{d["price_zh"]}的贡献', 'color': 'MBLUE', 'values': LN(c_p)},
            ]),
            'net': {'name': f'{d["value"]["zh"]}增长（单月）', 'values': LN(net)},
            'src_extra': ('Log-weight decomposition of an accounting identity; no model. '
                          'One bar = one month vs. the same month a year ago '
                          '(single-month y/y)'),
        }
        # ── 硬护栏④：**写进 payload 的那组数**也要闭合；留空格两段必须同空 ────
        for i, x in enumerate(ex['net']['values']):
            parts = [st['values'][i] for st in ex['stacks']]
            if x is None:
                if any(p is not None for p in parts):
                    raise SpecError(f'decomp「{d["zh"]}」{xl2[i]} 净额留空但堆叠段有值 —— '
                                    f'菱形不见了、柱子还在，读者会当成「净额为 0」')
                continue
            got = sum(parts)
            if not abs(got - x) <= 2e-6:
                raise SpecError(f'decomp「{d["zh"]}」{xl2[i]} 写进 payload 的两块相加 '
                                f'{got:.9f} ≠ 净额 {x:.9f}（差 {got - x:.3e}）')
        # ── 横轴现验②：横轴逐格等于那张输入图（`_decomp_yoy_refs` 已按 xl 过滤，
        #    这里再对 payload 里真正发出去的 `xl2` 核一遍 —— 上面过滤用的是 `xl`）。
        if xl2 != (v_ref.get('xlabels') or []):
            raise SpecError(
                f'decomp「{d["zh"]}」的横轴与 Exhibit {v_ref["n"]} 对不上'
                f'（{len(xl2)} vs {len(v_ref.get("xlabels") or [])} 格）—— '
                f'图注那句「逐格上下对读同一个月」就是假话')
        # ── 现验③：**菱形逐点等于那张图的次轴金线**。两边都是 LN() 之后的数，
        #    差只可能是 0（同一个算术、同一个窗口）。这一条是「同一条数」那句话的许可证。
        dia_gap, dia_n = self._pair_gap(ex['net']['values'], v_ref['yoy']['values'])
        if not dia_n or dia_gap > 1e-9:
            raise SpecError(
                f'decomp「{d["zh"]}」的净额菱形与 Exhibit {v_ref["n"]} 的次轴金线'
                f'对不上（可比 {dia_n} 格，最大差 {dia_gap:.3e}pp）—— '
                f'图注声称两者「是同一条数、逐点相同」，对不上就不许出图')

        # 两本留空账的合计。图注那句「而不是缩到 X 格」是拿**画得出来的格数**说事，
        # 两本都要减 —— 只减 `gaps_base` 的话，中段有洞时那个数会多算。
        n_gap = len(gaps_base) + len(gaps_hole)
        # 「因权重退化而留空」那一段末尾要点名另外哪几本账在下面，非空的才点。
        _other_gap = '、'.join(x for x, ok in (('基期缺失', gaps_base),
                                              ('输入缺口', gaps_hole)) if ok)

        # ── 统计**只在画得出来的格上算** ─────────────────────────────────────
        # 留空格与两侧不齐的格上 |g_V| ≈ 0 或根本没有值，拿它们算「交叉项 ÷ 净增长」
        # 能得到几百个百分点的假占比，而那些格图上根本没有柱。
        fin = [r for r in rows if np.isfinite(r['cq'])]
        last = rows[-1] if rows else None
        if last is None or last['lab'] != xl2[-1] or not np.isfinite(last['cq']):
            # 缺值格走 continue 不进 rows，留空格却会进且 cq 是 NaN ⇒ 只比标签挡不住。
            raise SpecError(
                f'decomp「{d["zh"]}」：图注与自检行都印「末格的读数」，'
                f'但末格必须是**画得出来**的那一格 —— 横轴末格是 {xl2[-1]}、'
                f'rows 末条是 {last["lab"] if last else "（空）"}、'
                f'它的量腿是 {last["cq"] if last else "—"}')
        x_pp = [abs(r['cross']) * 100 for r in fin]
        cross_med, cross_max = float(np.median(x_pp)), float(max(x_pp))
        cross_at = max(fin, key=lambda r: abs(r['cross']))['lab']
        near0 = [r for r in fin if abs(r['gV']) < DECOMP_NEAR0_G]
        far = [r for r in fin if abs(r['gV']) >= DECOMP_NEAR0_G]
        cross_sh = (float(max(abs(r['cross'] / r['gV']) * 100 for r in far))
                    if far else float('nan'))
        opp_n = sum(1 for r in fin if r['cq'] * r['cp'] < 0)
        w_lo, w_hi = min(r['w'] for r in fin), max(r['w'] for r in fin)
        w_med = float(np.median([r['w'] for r in fin]))
        lv_row = min(rows, key=lambda r: abs(r['lV']))
        lv_min = abs(float(lv_row['lV']))
        gapq = max(abs(r['gQ'] * 100 - r['cq']) for r in fin)
        gapp = max(abs(r['gP'] * 100 - r['cp']) for r in fin)
        # ── 两腿与页上各自那张输入图的金线差多少（点破「同一条同比乘过 w」）───────
        # **只在两分法下做**：三分法画出来的三块是行业 / 份额 / 结构，页上没有哪一列
        # 直接对应它们，硬拿 stacks[0]、stacks[1] 去比会把行业腿说成数量腿。
        q_gap, q_gn, q_ref_n = float('nan'), 0, None
        if not bench:
            if len(qty_ref) == 1:
                q_ref_n = qty_ref[0]['n']
                q_gap, q_gn = self._pair_gap(ex['stacks'][0]['values'],
                                             qty_ref[0]['yoy']['values'])
            # ── 中蓝段那句交叉引用**这里不写** ──────────────────────────────
            # 只把料记下来、在图注里埋一个占位符，等**全页**图都建完之后由
            # `_pleg_fill()` 回填。理由与做法见那个方法的 docstring：那句话是
            # 页面级超级式（「本页最接近…」「本页没有另一张图画这个派生量」），
            # 而这里手上只有 `built` —— 当前累积到一半的 ex 列表。
            self._pleg.append({
                'ex': ex, 'zh': d['zh'], 'price_zh': d['price_zh'],
                'xl': xl, 'win': win,
                'p_yoy': LN(yoy_line(v_s / q_s * d['price_scale'], win)),
                'gapp': gapp,
                # 恒等式两端的两条**输入**列。P ≡ V ÷ Q，V 与 Q 按构造都不是 P，
                # 所以它们自己的图不进候选（金额列那张已由上面「菱形是同一条数」
                # 认领，数量列那张由上面「深蓝段」认领）。
                # ⚠️ 按**列名**排除、不按图号：候选集改成全页之后，排在本图**后面**
                # 的那张数量列图不会进 `qty_ref`（它只扫 `built`）、`q_ref_n` 是 None，
                # 按图号排除会漏掉它，于是数量列可能被推上来当「最接近这个派生量」的
                # 那一张。列名是数据、图号是位置，这里认的是数据。
                'skip_cols': [vc['col'], qc['col']],
            })

        # ── 排版实测：菱形固定 6.4px 见方，长轴通栏后柱宽也只有 6px 出头 ⇒
        #    比柱还宽的菱形会盖掉薄段。有多少格会被盖住，这里现算（见 BRIDGE_PLOT_PX）。
        #    通栏与否照 `mrwin.layout()` 的规则先算一遍（bridge_bar 不在 VLABEL_KINDS，
        #    所以下限就是 MIN_BAND）—— 真正的 full 由 `_layout_long()` 稍后写进 payload，
        #    这里只是把同一条判据先跑一次，好让图注报的 px 与最终版式一致。
        use_full = mrwin.band_px(ex, full=False) < mrwin.MIN_BAND
        band = mrwin.band_px(ex, full=use_full)
        bar_px = max(1.5, min(band * self.BRIDGE_BW, band - 1.5))
        # 量程与「哪一段最薄」都从**写进 payload 的那几组数**上算，不从 rows 上算 ——
        # 三分法画的是另外三块，拿 cq / cp 去量就是在量一段图上没有的柱。
        drawn = [[v for v in st['values'] if v is not None] for st in ex['stacks']]
        env = [x for x in ex['net']['values'] if x is not None]
        for i, x in enumerate(ex['net']['values']):
            if x is None:
                continue
            vs = [st['values'][i] for st in ex['stacks']]
            env.append(sum(v for v in vs if v > 0))
            env.append(sum(v for v in vs if v < 0))
        pp_per_px = ((max(env) - min(env)) * 1.32) / self.BRIDGE_PLOT_PX
        dia_pp = self.DIA_R_PX * 2 * pp_per_px
        k_thin = min(range(len(drawn)), key=lambda k: np.median([abs(v) for v in drawn[k]]))
        thin_name = ex['stacks'][k_thin]['name']
        thin_med = float(np.median([abs(v) for v in drawn[k_thin]]))
        under_dia = sum(1 for v in drawn[k_thin] if abs(v) < dia_pp)
        # 三个「−0.0%」要走 nz_txt，先算好再进 f-string（本仓跑 3.9，f-string 里
        # 不许再嵌同种引号）。
        a_gq = nz_txt(f'{last["gQ"] * 100:+.1f}')
        a_gp = nz_txt(f'{last["gP"] * 100:+.1f}')
        a_gv = nz_txt(f'{last["gV"] * 100:+.1f}')

        ex['note'] = (
            f'<b>恒等式：{vc["zh"]} ≡ {qc["zh"]} × {d["price_zh"]}</b>，'
            f'其中 {d["price_zh"]} ≡ {vc["zh"]} ÷ {qc["zh"]}。'
            f'这是<b>定义式</b>，不含任何模型假设，两边逐格恒等。'

            # ① 横轴怎么读
            f'<b>横轴一格 = 一个月</b>：本期是该月，基期是<b>去年同月</b>'
            f'（当月 ÷ 去年同月 − 1，就是单月同比），共 {len(xl2)} 格'
            f'（{xl2[0]} – {xl2[-1]}），左端是全站时序图统一的左界 {xl2[0]}，'
            f'<b>与本页那些同样自 {xl2[0]} 起、同样 {len(xl2)} 格的月度图可以逐格上下对读'
            f'同一个月</b>（构建期核对横轴与 Exhibit {v_ref["n"]} 逐格相同，对不上就不出图）。'
            # ⚠️ 这句话**不许写成「与本页其余月度图」**：同一页上任何一条自己起点更晚的列
            # （辅源天花板、官方后来才加的行）画出来格数更少，同一个横轴下标不是同一个月，
            # 按下标去对读会整段错位。构建期那道现验只保证与 v_ref 那一张对齐，
            # 不保证与全页每一张对齐 —— 断言的范围必须与判据的范围一致。
            f'起点更晚的那几张图格数更少，<b>别按横轴下标去对读它们</b>。'
            # ②
            f'每一格覆盖的月数都是 1，所以<b>格与格之间可以直接比大小</b> —— '
            f'这与 2026-09 之前那版<b>按日历年分桶、末格是当年 YTD</b> 的分解图不同：'
            f'那版的末格与完整年柱覆盖月数不同，本来就不可比。'

            # ⑤ 与输入那几张图的关系
            f'<b>菱形（净额）与 Exhibit {v_ref["n"]} 次轴的金色折线是同一条数</b>，'
            f'逐点相同（构建期逐点现验，{dia_n} 格可比、最大差 {dia_gap:.1e}pp，'
            f'对不上就不出图）：那张画的是{vc["zh"]}的水平值与它的单月同比，'
            f'本图把同一条同比拆成量与{d["price_zh"]}两块。'
            f'换口径的代价（CONTRACT §6.1 第 3 条）就印在 Exhibit {v_ref["n"]} '
            f'自己的图注里、用的正是这条序列自己的实测，本图不重复印一遍。'
            + (f'<b>深蓝段与 Exhibit {q_ref_n} 的金线读的是同一条{qc["zh"]}单月同比</b>，'
               f'但深蓝段乘过重标定权重 w、走的是对数口径，两者最大差 {q_gap:.2f}pp'
               f'（{q_gn} 格可比）—— 逐格对读时以本图为准。'
               if q_ref_n is not None else '')
            # 中蓝段那句话在这里只留一个占位符，回填见 `_pleg_fill()`。三分法
            # （bench）那一档本来就不印这句，连占位符都不埋。
            + ('' if bench else PLEG_MARK)

            # ③ 单月桶里没有平均
            + f'<b>单月桶里没有任何平均</b>：{d["price_zh"]} = 该月的{vc["zh"]} ÷ '
              f'同一个月的{qc["zh"]}，本期与基期各自只有一个月，'
              f'两侧都不存在「逐月该怎么加权」的问题。'
              f'金额：{v_how}；数量：{q_how}。'

            # 算法
            + f'<b>图上画的是对数分解（按总增长重标定）。</b>'
              f'ln(V₁/V₀) = ln(Q₁/Q₀) + ln(P₁/P₀) 天然可加、<b>没有交叉项</b>；'
              f'再乘上 w = g<sub>额</sub> ÷ ln(V₁/V₀) 把两块换算成百分点，'
              f'于是<b>深蓝 + 中蓝逐格等于</b>菱形标的总增长（三道闭合检查残差 ≤ '
              f'{DECOMP_EPS:.0e}，超了本页直接不出 —— 护栏在 '
              f'<code>build/single.py</code> 的 <code>_decomp_monthly</code>）。'
              f'w 对量与价一视同仁，不含任何分配假设；本窗口实测 '
              f'{w_lo:.2f}–{w_hi:.2f}（中位 {w_med:.2f}）。'

            # ④ 算术分解：印 pp，占比只在净增长不近零的格上算
            + f'<b>为什么不画算术分解。</b>算术分解 g<sub>额</sub> = g<sub>量</sub> + '
              f'g<sub>价</sub> + g<sub>量</sub>·g<sub>价</sub> 多一个交叉项，'
              f'而它不是可忽略的余项：{len(fin)} 格里有 {opp_n} 格'
              f'（{opp_n / len(fin) * 100:.0f}%，分母是<b>画得出来</b>的格数）'
              f'量与{d["price_zh"]}<b>方向相反</b>。'
              f'实测交叉项<b>绝对值</b>中位 {cross_med:.2f}pp、最大 {cross_max:.2f}pp'
              f'（{cross_at}）；'
            + (f'「占净增长百分之多少」只在净增长本身不近零时才有意义 —— '
               f'净增长绝对值 ≥ {DECOMP_NEAR0_G * 100:.0f}% 的 {len(far)} 格里最大 '
               f'{cross_sh:.0f}%（另有 {len(near0)} 格净增长不足 '
               f'{DECOMP_NEAR0_G * 100:.0f}%，那里的占比读的是分母不是交叉项）。'
               if far else
               f'本窗口没有一格的净增长绝对值达到 {DECOMP_NEAR0_G * 100:.0f}%，'
               f'「交叉项占净增长」在这里没有可靠的分母，所以只印 pp。')
            + f'{last["lab"]} 的算术读数：量 {a_gq}%、'
              f'{d["price_zh"]} {a_gp}%、交叉项 '
              f'{ppbp(last["cross"] * 100)}。两种口径对「量」的贡献读数最大差 '
              f'{ppbp_abs(gapq)}、对「{d["price_zh"]}」最大差 {ppbp_abs(gapp)}。'

            + ((f'<b>本图是三分法。</b>在两分法（量 × 价）之外再拆一层：'
                f'{vc["zh"]} ≡ {d["bench_value"]["zh"]} × {share_zh} × {mix_zh}'
                f'（份额 ≡ {qc["zh"]} ÷ {d["bench_qty"]["zh"]}；'
                f'结构 ≡ 自家{d["price_zh"]} ÷ 行业{d["price_zh"]}）。'
                f'代入前一条恒等式两边逐项对消即得，同样是定义式。'
                f'三块对数相加 = 总对数增长，重标定后逐格 = 总增长，'
                f'残差 ≤ {DECOMP_EPS:.0e}（护栏⑤⑥）。'
                f'<b>⚠️ 份额与结构两块的分界依赖 bench 与本家同口径：分子必须是分母的'
                f'子集。换一家用之前先核这一条</b>。') if bench else '')

            # ⑥ 留空：两种留空各说各的，没命中就把「离阈值多远」印出来
            + (f'<b>因权重退化而留空的格</b>：{"、".join(blanks)} 的 |ln(V₁/V₀)| < '
               f'{DECOMP_LN_MIN:.0e}（两期几乎持平），重标定权重 w 是 0/0、'
               f'算出来没有有效位，所以整格留空而不是印一个假的分解。' if blanks else
               f'<b>本轮没有任何一格因权重退化而留空</b>（判据 |ln(V₁/V₀)| < '
               f'{DECOMP_LN_MIN:.0e}，两期几乎持平时 w = 0/0'
               # 「下面那批」指的是下面两本留空账 —— 哪本非空就点哪本的名。
               # 写死成「基期缺失」的话，某一页哪天只有中段的洞（表首月早于
               # WIN_FROM 十二个月以上时 `gaps_base` 就是空的，db1 / ndaq / tmx
               # 那几张表的起点都够早），这句话就会指向一批并不存在的格。
               + (f'；这一档与下面那批{_other_gap}的格是两回事' if _other_gap else '')
               + f'）：最接近的一格是 '
               f'{lv_row["lab"]}，|ln(V₁/V₀)| = {lv_min:.6f}，是阈值的 '
               f'{lv_min / DECOMP_LN_MIN:,.0f} 倍。规则留着 —— 它防的是极端巧合，'
               f'「这轮没命中」不是删兜底的理由。')
            # ⑦ 留空的另外两本账：**基期落在表外**与**输入自己有洞**各说各的。
            #    措辞不许互借：前者是「左端连续一段、随窗口右移自动消失」，
            #    后者是「窗口里任意位置、只有源表补格才会消失」。
            + (f'<b>另有左端 {len(gaps_base)} 格（{gaps_base[0]} – {gaps_base[-1]}）留空</b>，'
               f'原因与上面那一条无关：它们的<b>基期</b>（各自的去年同月）'
               f'落在本表首月 {mlab(list(self.df.index)[0])} 之前，'
               f'源表里根本没有那一行，单月同比无从算起。'
               f'横轴仍取本页统一的 {len(xl2)} 格而不是缩到 {len(xl2) - n_gap} 格：'
               f'缩了就与本页其余月度图对不齐，「可以逐格上下对读同一个月」那句话'
               f'随之作废。逐格点名见构建日志的自检行。' if gaps_base else '')
            + (f'<b>另有 {len(gaps_hole)} 格留空，原因不是「基期落在表外」</b>：'
               f'这些格的<b>基期就在本表里</b>，废掉它们的是<b>输入自己</b> —— '
               f'源表那一格空着，或者那一个月的合计取不了对数。'
               f'逐格点名（括号里是构建期原文）：'
               + '；'.join(f'<b>{lab}</b>（{why}）' for lab, why in gaps_hole)
               + f'。这一档<b>不会随窗口右移而消失</b>，要等源表把那一格补上，'
                 f'与「基期落在本表之外」那一档是两回事，所以分两本账印。'
                 f'画不出来的格就是画不出来，图上不会有任何柱段或菱形替它站位。'
               if gaps_hole else '')

            + f'<b>⚠️「{d["price_zh"]}」是什么、不是什么。</b>它是 {vc["zh"]} ÷ '
              f'{qc["zh"]} 得到的{kind_zh}。{kind_warn}'

              f'<b>汇率进不来。</b>本图每一格都是同一列自身的单月增长率，'
              f'本币（{self.spec["ccy"]}）在分子分母上同时出现、逐项抵消；'
              f'换成任何一种货币、任何一种换汇口径（月均 / 月末 / 锁基期），'
              f'两块的高度与菱形的位置一个都不会变。'

              f'{last["lab"]} 读数：{vc["zh"]} {unit_txt(last["V1"], vc)}'
              f'（去年同月 {unit_txt(last["V0"], vc)}）、'
              f'{qc["zh"]} {unit_txt(last["Q1"], qc)}'
              f'（{unit_txt(last["Q0"], qc)}）；{d["price_zh"]} '
              f'{fmt_val(last["P1"], d["price_fmt"])}（'
              f'{fmt_val(last["P0"], d["price_fmt"])}）{d["price_unit"]} ⇒ '
              f'量 {ppbp(last["cq"])} + {d["price_zh"]} {ppbp(last["cp"])} = 净 '
              f'{a_gv}%。'

            # ⑧ 菱形会盖掉薄段
            + f'<b>逐格读数请走卡片右上角的「表格」</b>：{len(xl2)} 格'
              f'{"通栏之后" if use_full else ""}每格只有 '
              f'{band:.1f}px、柱宽 {bar_px:.1f}px，而<b>净额菱形是固定 '
              f'{self.DIA_R_PX * 2:.1f}px 见方</b>（<code>assets/charts.js</code> 里'
              f'半径写死 {self.DIA_R_PX}px，<b>不随格宽缩</b>）—— 它比这里的柱还宽一点，'
              f'画在净额那个高度上，于是矮于 {self.DIA_R_PX * 2:.1f}px 的柱段会被它'
              f'<b>盖掉一截</b>。本窗口最薄的那一段是「{thin_name}」，绝对值中位 '
              f'{thin_med:.1f}pp，其中 {under_dia} 格矮于菱形'
              f'（按本图自己的量程折算 ≈ {dia_pp:.2f}pp）。'
              f'被盖住的段<b>不是零</b>，要读某一格的各块分别是多少，一律走表格，'
              f'不要拿眼睛去量柱段。'
            + (' ' + md_bold(d['note']) if d['note'] else ''))

        # ── 自检行：由 build() 打印。**一个数都不写死。** ──
        self.decomp_report.append(
            f'decomp「{d["zh"]}」（月度桶，当月 vs 去年同月）：{len(xl2)} 格 '
            f'{xl2[0]} – {xl2[-1]}，画得出 {len(fin)} 格；'
            f'末格 {last["lab"]} {vc["col"]} {last["V1"]:,.4g} vs {last["V0"]:,.4g}、'
            f'{qc["col"]} {last["Q1"]:,.4g} vs {last["Q0"]:,.4g}、'
            f'{d["price_zh"]} {last["P1"]:,.4g} vs {last["P0"]:,.4g} → '
            f'量 {last["cq"]:+.2f}pp + 价 {last["cp"]:+.2f}pp = 净 '
            f'{last["gV"] * 100:+.2f}%；净额区间 '
            f'{min(r["gV"] for r in fin) * 100:+.1f}% – '
            f'{max(r["gV"] for r in fin) * 100:+.1f}%；两腿反号 {opp_n} 格；'
            f'交叉项 |中位| {cross_med:.2f}pp / |最大| {cross_max:.2f}pp（{cross_at}）；'
            f'w {w_lo:.4f}–{w_hi:.4f}（中位 {w_med:.4f}）；'
            f'最小 |ln(V1/V0)| = {lv_min:.6f}（{lv_row["lab"]}，阈值 '
            f'{DECOMP_LN_MIN:.0e} 的 {lv_min / DECOMP_LN_MIN:,.0f} 倍）；'
            f'菱形 vs Exhibit {v_ref["n"]} 金线最大差 {dia_gap:.1e}pp（{dia_n} 格）；'
            f'三道闭合残差 ≤ {DECOMP_EPS:.0e} 全过'
            + (f'；留空格 {"、".join(blanks)}' if blanks else '；无留空格')
            # 自检行同样分两本账印：措辞混用一次，读者就会拿「基期落在表外」去解释
            # 一个基期明明在表内的洞（红队实测：挖两个洞，这一行照旧印
            # 「基期缺失留空 16 格」，多出来的四格基期全在表内）。
            + (f'；基期缺失留空 {len(gaps_base)} 格：{"、".join(gaps_base)}'
               if gaps_base else '；无基期缺失格')
            + (f'；输入缺口留空 {len(gaps_hole)} 格：'
               + '、'.join(f'{lab}（{why}）' for lab, why in gaps_hole)
               if gaps_hole else '；无输入缺口格'))
        return ex, None

    def _pleg_fill(self, ex_all):
        """回填月度分解图注里「中蓝段」那一句 —— **全页图都建完之后**才算得出来。

        **为什么必须两趟。**这句话有三个分支，三句都是**页面级**断言：
          · 「<b>中蓝段同理对应 Exhibit k</b>：那一列画的正是本图这个派生量…」
          · 「<b>本页最接近这个派生量的是 Exhibit k</b>，但…<b>本图不替它署名</b>」
          · 「<b>本页没有另一张图画这个派生量</b>」
        「本页」就是本页 —— **判据的范围必须与断言的范围一致**。而 `_decomp_monthly`
        手上只有 `built`（**当前累积到一半**的 ex 列表）：分解图排在页尾时它恰好等于
        全页，那三句话为真；2026-09 给 /tmx/ 的两张分解加了 `after_group`、把它们
        前移到各自输入之后，候选集立刻缩成「本图之前那些图」，三句话同时变成假话。
        实测（2026-09 这一版窗口）：Ex20 印的是 Exhibit 6（差 64.352pp），而全页最近的
        是 Exhibit 37（S&P/TSX Composite 点对点同比，35.480pp）；Ex23 印 Exhibit 6
        （67.835pp），全页最近同样是 Exhibit 37（29.616pp）。**不止图号与数错**：
        Ex20 连落哪一档都会换 —— 35.480pp 已经大于画出来的中蓝段自己的 32.331pp，
        落的是「还不如中蓝段近」那一档，而不是「超过那一列取整能解释的量」那一档。
        ⚠️ 这一类错**四道闸门一道都查不出来**：它们看 payload 的结构与数值闭合，
        看不见散文的真伪。

        **为什么不改成「把话说小」**（例如「本图之前那些图里最接近的是…」）。那样也能
        说成真话，但会把一个**判断错误**永久固化：真正对应这个派生量的那一列一旦排在
        本图后面（`after_group` 干的正是这件事），署名那一支永远轮不到它，页面会一边
        印「本页没有另一张图画这个派生量」，一边让读者在同一页上看见它。范围缩小之后
        这句话字面为真、实质仍在误导，所以走两趟。底座里已有同类先例：`mix_pair` 的
        「各分项的构成见 Exhibit k」也是等两张图都产出之后才回填 —— 图号是算出来的，
        写死或早算都会指错。

        `ex_all` 是**全页**已建好的 exhibit 列表（`payload()` 里那个 `ex`）。
        ⚠️ 必须排在 `chartscale.fix_all()` **之前**调用：那一步会把 `_cols` pop 掉
        （`_decomp_yoy_refs` 按列认图，没有它一张都认不出来），还会按显示量级缩放数值。
        """
        for rec in (self._pleg or []):
            ex, xl, win = rec['ex'], rec['xl'], rec['win']
            p_yoy, price_zh, gapp = rec['p_yoy'], rec['price_zh'], rec['gapp']
            # 价腿没有「自己那一列」（P 是本图现算的派生量），所以对照图靠**实测**挑：
            # 取本页与「P 的单月同比」最接近的那条金线，且它必须比画出来的价腿更接近 P
            # （否则它跟的根本不是同一个量）。两个差照旧都印出来、读者自己判。
            #
            # ⚠️ **「敢不敢替那一列署名」另有一道门槛。**认领这张对照图的那句图注写的是
            # 「那一列画的正是本图这个派生量…差异量级就是该列自己的取整」，
            # 这是一句**可证伪的断言**，而挑选只保证「本页最近的一条」——
            # 页上一条真正对应的列都没有时，最近的那条照样会被推上来：
            # /tmx/ 的两张月度分解实测挑中的是 S&P/TSX Composite 月末点位的点对点同比，
            # 逐格最大差 35.480pp / 29.616pp（对照 /asx/ 那张真对应的官方均价列是
            # 0.027pp），而图注若照旧宣布「差异量级就是取整」，上线就是一句假话。
            #
            # 所以这里加的不是一个拍脑袋的阈值常量（本仓教条：凡能现算的一律现算，
            # 写死一个 0.5pp 既推翻上面那条「不设阈值」的决定，又是在「不写死数字」的
            # 仓里写死一个没有推导的数），而是**把那句话自己声称的东西现算出来**：
            # 那一列在 CSV 里存到哪一位（`_round_quantum`），这个取整粒度最多能让它的
            # 单月同比偏多少百分点（`_round_yoy_bound`，按区间端点精确算、不做线性近似）。
            # 实测差挤得进这个上界 ⇒ 「差异量级就是该列自己的取整」成立，署名。
            #
            # ⚠️ **挤不进时不许落回「本页没有另一张图画这个派生量」那句。**那是一句
            # 无条件的**存在性**断言，而这道门槛拒绝候选的理由根本不是「页上没有这一列」，
            # 是「实测差挤不进那一列的取整上界」—— 两者一分家，那句话就是假的。
            # 所以下面把三件事分开记：页上一张候选都没有 ⇒ 才印那句存在性断言；
            # 有候选没过门槛 ⇒ 改印「最接近的是 Exhibit k、差多少、卡在哪一条判据上、
            # 所以不替它署名」。两句都是**实测结论**，各自成立。
            # 实测：/asx/ 的 avg_value_per_trade_aud 在 series/asx.csv 里存成整数
            # A$/笔（δ=1），本窗口上界 0.0347pp，而实测差 0.027pp ⇒ 照常署名，
            # 那张图的图注逐字节不变（2026-09 改这一处、以及本轮改成两趟时都重跑对比过）。
            # ⚠️ 那一页的余量只有约两成（0.027 / 0.0347），而 `gap` 与 `bound` 都是在
            # **左界钉死、右端每月往前走**的窗口上取最大值 ⇒ 两者只增不减，gap 哪个月
            # 越过 bound 就**永久**越过、回不去。那一天到来时四道闸门一道都不会响，
            # 页面只是从「署名」换成上面那句点名的说法 —— 换过去的那句仍然为真，
            # 这正是把兜底句分叉的理由。（数字是 2026-09 这一版窗口的实测，会变。）
            cand = [e for e in self._decomp_yoy_refs(ex_all, xl)
                    if (e['_cols'][0] not in rec['skip_cols'])]
            scored = [(self._pair_gap(p_yoy, e['yoy']['values'])[0], e) for e in cand]
            scored = [(g, e) for g, e in scored if np.isfinite(g)]
            txt = (f'<b>本页没有另一张图画这个派生量</b>，所以中蓝段只能与本图现算的 '
                   f'{price_zh} 自己的算术单月同比对读（最大差 {ppbp_abs(gapp)}）。')
            if scored:
                g0, e0 = min(scored, key=lambda t: t[0])
                leg_g = self._pair_gap(ex['stacks'][1]['values'],
                                       e0['yoy']['values'])[0]
                r_bd = self._round_yoy_bound(e0['_cols'][0], win,
                                             p_yoy, e0['yoy']['values'])
                if np.isfinite(leg_g) and g0 < leg_g and np.isfinite(r_bd) and g0 <= r_bd:
                    txt = (f'<b>中蓝段同理对应 Exhibit {e0["n"]}</b>：'
                           f'那一列画的正是本图这个派生量'
                           f'（它的金线与本图现算的 {price_zh} 单月同比逐格最大差只有 '
                           f'{g0:.3f}pp —— 差异量级就是该列自己的取整），'
                           f'与画出来的中蓝段最大差 {leg_g:.2f}pp，多出来的那一截'
                           f'全是 w 与对数口径造成的。')
                else:
                    # 卡在哪一条判据上，逐档写实话 —— 三档的理由互不相同，
                    # 合并成一句「差太大」会在另外两档变成假话。
                    if not (np.isfinite(leg_g) and g0 < leg_g):
                        why = ('它离本图这个派生量还不如画出来的中蓝段近'
                               + (f'（中蓝段 {leg_g:.2f}pp）' if np.isfinite(leg_g)
                                  else '（中蓝段一格都比不出来）')
                               + '，跟的不是同一个量')
                    elif not np.isfinite(r_bd):
                        why = '而那一列在本窗口上一格都算不出取整上界'
                    else:
                        # ⚠️ 上界常常比 0.0001pp 还小（整数张数那种大数列），一律 .4f
                        # 会印成「0.0000pp」—— 读者会当成真零，而真零与「小到印不出来」
                        # 在这句话里是两回事。小的那一档改印科学计数（与本图注里
                        # 「菱形 vs 金线最大差 {:.1e}pp」同一种写法）。
                        bd = (f'{r_bd:.4f}pp' if r_bd >= 5e-4 else f'{r_bd:.1e}pp')
                        why = f'超过那一列自己的取整最多能解释的 {bd}'
                    # ⚠️ 这句与上面那句存在性断言**不是**同一句话的两种说法：
                    # 上面那句断言「页上没有」，这一句断言「页上有一张最近的、
                    # 但它不是这个派生量」。哪一句为真由挑选与门槛现算决定，不许合并。
                    txt = (f'<b>本页最接近这个派生量的是 Exhibit {e0["n"]}</b>，'
                           f'但它的金线与本图现算的 {price_zh} 单月同比逐格最大差 '
                           f'{g0:.3f}pp，{why} —— <b>本图不替它署名</b>：'
                           f'中蓝段只与本图现算的 {price_zh} 自己的算术单月同比对读'
                           f'（最大差 {ppbp_abs(gapp)}）。')
            # 占位符必须**恰好一个**。零个 = 这条记账早就与图注脱了钩（回填悄悄失效、
            # 页面少一整句话）；两个 = 图注被复制粘贴过，两处会被填成同一句。
            k = ex.get('note', '').count(PLEG_MARK)
            if k != 1:
                raise SpecError(
                    f'decomp「{rec["zh"]}」（Exhibit {ex.get("n")}）的图注里有 {k} 个'
                    f'中蓝段占位符，应当恰好 1 个 —— `_decomp_monthly` 埋占位符那一处'
                    f'与 `_pleg_fill` 回填那一处已经对不上了')
            ex['note'] = ex['note'].replace(PLEG_MARK, txt)

    def ex_level_yoy(self, n, t):
        """一条量的**水平值**（柱）+ **单月同比**（次轴金线）。

        ⚠️ **这张图 2026-09 之前画的是 12 个月滚动合计的同比**（函数名 `ex_ttm`、
        spec 键 `ttm_yoy`、标题写「水平值与 12 个月滚动同比」）。按页面所有者的指令，
        全站同比一律改成**单月**：当月对去年同月，**本列除本列** —— 读者拿这根柱和
        12 根柱之前那根一除就能核对上，中间没有任何还原步骤。

        改口径要付的两笔账，这里都付：
          · **标题与 `ylab2` 都写明「单月」** —— 不引具体条号，因为 §6 抬头那句
            「全站同比只有一种口径：单月同比」本身就是全部依据，条号还会随契约改版
            漂移（这一行从前引的「§6.1 第 2 条」现在指的是存量点对点，指错了）。
            要看机器判据看 `tools/check_yoy_caliber.py` 的 **R4** ——
            它只认 title / ylab2 / legend / yoy.name 这四处，所以标题与 ylab2 都写。
          · **图注印代价** —— 由 `mom_cost_zh()` 拿**这条序列自己**、在**本图这个窗口**
            里实测（逐月标准差、相邻月最大跳变、符号相反的月份数）。图注里没有
            「为什么用单月」这一栏：口径是所有者定的，不需要每张图辩护一遍。

        ── 这张图只收**流量**列，比率与存量在 `_norm_level_yoy()` 里就被挡回去 ──
        下面这段代码把标题 `…：水平值与单月同比`、`ylab2='% y/y（单月）'`、
        `yoy_rhs(..., pct_series=False)`、`log_yoy(n, 'mom')` 四处**硬写死**成流量的
        形状。而 `_norm_col` 本身是允许 `stock=True` 与 `fmt='pct*'` 的，
        所以在加上入口护栏之前，这四处写死是几句**只对流量成立的话被无条件印出去**：
          · 比率列会画成「百分比的百分比变化」（0.24 → 0.25 印成 +4.2% 而不是 +1bp），
            违 CONTRACT §6.1 第 4 条；
          · 存量列的点对点同比虽然合法（§6.1 第 2 条），却会被这张图称作「单月同比」
            并记进页尾 `'mom'` 那一段，标题里也不带 `ex_stock` 写着的
            「（存量，期末口径）」—— `tools/check_yoy_caliber.py` 认的正是那几个字。
        今天没有 spec 踩到，但那是没护栏不是没发生。护栏放在 `_norm_level_yoy()`
        而不是这里，是因为它属于「spec 写错了」而不是「数据还没到」——
        要人去改，就该在读 spec 的那一刻硬失败（退出码 1），别等排到第 40 张图。
        比率列与存量列**不是没地方画**：放进 `groups[].cols` 的单列桶即可，
        `ex_single` 会按百分点差处理比率，`ex_stock` 会按点对点同比处理存量，
        两条路都已经把口径写进标题与图注。

        随之作废的三件东西，一并删掉而不是留着：`ttm_rhs()`（算滚动次轴）、
        `ttm_spike_zh()`（比两种口径的毛刺）、`bar_line_caliber_zh()`（解释「柱是日均、
        线是当月合计的滚动同比」为什么口径不同）。最后一个现在恒为一句废话 ——
        柱与线本来就是同一列。
        """
        c = t['level']
        end = self.last_month(c)
        if end is None:
            return None, f'{t["zh"]}：{c["col"]} 整列为空'
        win = self.win_long(end)
        xl = [mlab(p) for p in win]
        v = self.vals(c, win)
        if self.flat0_skip(t['zh'], [c], win, [v]):
            return None, f'{t["zh"]}：窗口内恒为 0'

        rhs = yoy_rhs(self.ser(c), win)
        ex = bar_ex(n, f'{t["zh"]}：水平值与单月同比', c, xl, v, rhs,
                    ylab2='% y/y（单月）')
        if rhs:
            self.log_yoy(n, 'mom')
            # 查重在这里，不在函数开头：要比的是**窗口**，而窗口这时候才算出来。
            # 撞上同族同窗口硬失败，撞上头条那张纯同比图只告警 —— 见 log_yoy_bar。
            self.log_yoy_bar(n, c, win, 'mom', 'bar_yoy', f'level_yoy「{t["zh"]}」')
        hit = self.mark_breaks(ex, win, [c])
        ex['note'] = (
            f'深蓝柱 = {c["zh"]}的<b>水平值</b>（{c["unit"]}，原始单位，未做任何指数化）。'
            # 这里原来写「近 N 个月」。窗口左端是钉死的 WIN_FROM（或序列首月），
            # 不是滚动近端窗口 —— `win_zh` 的 docstring 记的就是这条，本页其余图早就
            # 改用它了，只有这一张漏下。
            f'{self.win_zh(win)}。'
            + (f'金色折线（右轴）= <b>单月同比</b>（当月对去年同月，'
               f'<code>{c["col"]}</code> 自己除自己，不换列、不乘交易日数、'
               f'不做任何还原）—— <b>拿这根柱除以 12 根柱之前那根，就是线上这一点</b>。'
               if rhs else NO_YOY_NOTE)
            + f'{xl[-1]} 水平值 {unit_txt(v[-1], c)}，'
            + (f'同比 {chg_txt(c, v)}、环比 {chg_txt(c, v, lag=1)}。'
               if rhs else f'环比 {chg_txt(c, v, lag=1)}。')
            + (self.mom_cost_zh(n, c, win) if rhs else '')
            + (self.near_zero_guard(n, c, win, rhs) if rhs else '')
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
                    # 与图注同一份实现（`chg_txt` 也调它）：百分点走 pp/bp，
                    # 分子是钱的比率走「每单位多少钱」，见 `ratio_diff_txt`。
                    txt = ratio_diff_txt(v, c)
                else:
                    txt = f'{nz(v, 1):+.1f}%'
                txt = nz_txt(txt)
                if txt.lstrip('+-') in ('0', '0.0', '0bp', '≈0bp',
                                        '0.0pp', '0.0%', '0%'):
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

        # 「分子是钱的比率」这几行的 m/m / y/y 不写 pp/bp 而写「每单位多少钱」，
        # 逐行现算点名 —— 名单空了这半句自己消失（见 `unit_is_money_ratio`）。
        money_zh = []
        for c in self.head + [c for g in self.groups for c in g['cols']]:
            if col_is_money_ratio(c) and c['zh'] not in money_zh:
                money_zh.append(f'{c["zh"]}（{c["unit"]}）')
        note = (
            f'「3Y %ile」= 当月读数在最近 {pctile.WINDOW} 个月里高于多少比例的观测'
            f'（≥66 绿、≤33 红），由全站唯一的 <code>build/pctile.py</code> 计算：'
            f'把这一行的分位在近 24 个月里逐月回放，若 ≥70% 的月份都钉在 100 或 0，'
            f'说明这一列对该指标没有区分度，留空。'
            f'比率类指标的变化用<b>差</b>而不是「百分比的百分比变化」'
            f'；其余用百分比变化，分母为 0 或两期异号时留空。'
            + (f'差的单位跟着<b>分子</b>走：分子是百分数的写 pp／bp'
               f'（差额绝对值小于 1pp 时写 bp）；'
               f'<b>分子是钱</b>的写钱 —— 本表里的 {"、".join(money_zh)} '
               f'就是这一档，它们的 m/m 与 y/y 印成「每一个活动单位差多少钱」'
               f'（例如「-0.01 USD/contract」），<b>不是 pp 也不是 bp</b>：'
               f'每张少收一分钱是钱，不是万分之一个百分点。'
               if money_zh else
               f'比率的差一律写 pp／bp（差额绝对值小于 1pp 时写 bp）。')
            + f'bp 的小数位按量级给：整 bp 分不出量级时多给一到两位（例如「+0.5bp」），'
            f'所以这张表里写着「0bp」的格子是<b>真的没动</b>（两期读数相等），'
            f'不是被四舍五入抹平的一个小变化。'
            f'「算不算比率」不由显示格式决定 —— 2026-09 之前这里判的是 fmt，'
            f'于是 RPC、份额这类真比率只要因为量纲护栏没配 pct*/pp* 格式，'
            f'它的同比就静默翻成百分比变化；现在的判据是 spec 显式声明、'
            f'或 fmt、或「列名（<code>build/yoy.py</code> 的 <code>classify()</code>）'
            f'与单位量纲同时认它是比率」。')
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

    def _decomp_here(self, ex, n, gz):
        """在 groups 循环里就地出「锚点 = gz」的那些分解图 → 新的图号计数 n。

        提成一个方法而不是把七行贴进循环体：`payload()` 的 groups 循环已经在管
        mix / 单位分桶 / 存量剔除三件事，再塞一段就地出图会让「这个循环到底负责什么」
        说不清。它与页尾那一轮共用同一个 `ex_decomp` 与同一套记账
        （`skipped` / `decomp_report` / `_mark_section`），两处不许各写一遍。
        """
        for d in self.decomp:
            if d['after_group'] != gz:
                continue
            _d0 = len(ex)
            e, why = self.ex_decomp(n, d, ex)
            if e is None:
                self.skipped.append(why)
                continue
            ex.append(e)
            n += 1
            _mark_section(ex, _d0, d.get('section'))
        return n

    # ────────────────────── 组装 ──────────────────────
    def payload(self):
        got, why = self.resolve_through()
        if got is None:
            return None, why
        latest, common = got
        # glossary / brief 的 callable 拿得到页面钉死的那个数据月 —— 各列自己的
        # [-1] 会串到发布更快的腿上，同一页对同一指标给出两个互斥读数。
        self.latest = latest
        idx = list(self.df.index)
        newest = idx[-1]
        ex, n = [], 2
        _h0 = 0
        self.yoy_log = []       # 口径账本每次组装从零记，防重复调用时把图号记两遍
        # 「同一列画了几条同比」的账 + 撞上之后的告警，见 log_yoy_bar()。
        # 同样每次组装从零记：重复调用 payload() 时不能把上一轮的图号带进来。
        # `win` 是给人读的三元组（左标签, 右标签, 期数），`p0` / `p1` 是那两端的
        # **Period 本身**。p0/p1 从前只在 log_yoy_bar 内部私用，2026-09 起
        # `total_drawn_wider()` 也读它们来判「窗口是不是真包含」—— 已经是跨函数契约，
        # 所以列在这里：动它们要连那一支一起看。
        self._yoy_bar_cols = {}    # col → [{'n','family','cal','win','where','p0','p1'}, …]
        self.dup_yoy = []          # 只告警不停机的那一档，页尾由 dup_yoy_zh() 现算
        # 「合计柱有意不出」的账，同样每次组装从零记：重复调用 payload() 时把上一轮的
        # 图号带进来，页尾那句「绝对量看 Exhibit k」就会指到上一轮的号上。
        self.mix_folded = []
        # 「这张图问过断点」的账（图号），由 mark_breaks() 记、页尾那段断点说明读。
        # 同样每次组装从零记，理由与上面几本账逐字同源。
        self._brk_asked = set()
        # 「没问过断点的那张图用了哪几条列」的账（图号 → 列名），由
        # note_nodraw_cols() 记、页尾那段断点说明读。键是图号，重复调用 payload()
        # 不清零就会把上一轮的图号带进来 —— 理由与上面几本账逐字同源。
        self._nodraw_cols = {}
        self.cost_ns = set()       # 真印出了「逐图代价」那一段的图号，见 mom_cost_zh()
        # 可比月太少、图注里照实写了「量不出来」的图号。单独记而不是拿
        # 「mom 全集 − cost_ns」倒推：倒推只在「每条 mom 路径都调过 mom_cost_zh」
        # 这个前提下成立，而那正是本轮才补上的事 —— 前提哪天再破一次，
        # 倒推会把「漏印」静默说成「量不出来」，那是页尾替漏洞背书。
        self.cost_thin_ns = set()
        # 近零基数（§6.1 第 5 条）命中的图：每命中一条序列记一笔，
        # `build()` 逐条打印。从零记，理由同上。
        self.nz_ns = []
        # 尖刺截轴（`spike_cap()`）真截了轴的图：每张记一笔。与 nz_ns 同生命周期 ——
        # 页尾那句「本页哪几张截了轴 / 一张都没有」现读这本账，重复调用 payload() 时
        # 把上一轮的图号带进来，就等于替一张这一轮根本没截轴的图背书。
        self.cap_ns = []
        self.saw_group_lines = self.saw_group_heat = self.saw_ratio_rhs = False
        self.decomp_report = []  # decomp 自检行同理，从零记
        # 月度分解图注里「中蓝段」那句话的**待回填**清单（见 `_pleg_fill`）。
        # 同样每次组装从零记：留着上一轮的记录，回填就会去改一张早已不在这一轮
        # 页面上的图，而这一轮真正埋了占位符的那张反倒没人填 —— 下面那道
        # 「占位符还在就 raise」的护栏会当场把它拦下来，但账本本身先得是干净的。
        self._pleg = []

        if self.headline_style == 'bar_yoy':
            # ①② 并成一张：全历史的水平值柱 + 次轴单月同比（见 HEADLINE_STYLES）。
            for c in self.head:
                ex.append(self.ex_head_bar(n, c)); n += 1
        else:
            for c in self.head:                               # ① 长历史 + 3Y 分位带
                ex.append(self.ex_history(n, c)); n += 1
            for c in self.head:                               # ② 同比
                ex.append(self.ex_yoy(n, c)); n += 1
        _mark_section(ex, _h0, self.spec.get('headline_section'))

        # 「派生图没出成」的账本：③ 的 mix 也会往里记，所以要在 ③ 之前开。
        self.skipped = list(self.mix_skipped)

        for g in self.groups:                                 # ③ 每组多列对比
            _g0 = len(ex)
            # 声明了 mix 且合计是**流量**列 → 先出「合计柱 + 占比堆叠」。
            # （**不写死「两张」**：合计那一列已被本页别处那张更宽的图画过时只出后一张，
            #   见 `mix_pair` / `total_drawn_wider`；两张各自还都可能画不成。）
            # 合计是存量列的留到 ⑤ 与本页其余存量图排在一起（存量与流量不共轴，
            # 也不该在阅读顺序上互相插队）。
            eaten = set()
            if g['mix'] and not g['mix']['total']['stock']:
                pair, eaten = self.mix_pair(n, g)
                for e in pair:
                    ex.append(e); n += 1
            # 被 mix 吃掉的列不再进常规对比图：结构由占比堆叠交代，水平值由那张
            # **画了合计这一列的柱图**交代 —— 通常是本组自己的合计柱，合计柱有意不出
            # 的那一档（`total_drawn_wider`）则是本页别处那张横轴更宽的图。
            # 两种情形下这一列都算被吃掉，再画一遍都是同一批数在同一页上出现两次。
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
                for e in self.ex_group(n, g['zh'], cs, rr=g.get('ratio_rhs'),
                                       spike=g.get('spike_cap', False)):
                    if e is None:
                        continue
                    ex.append(e)
                    n += 1
            _mark_section(ex, _g0, g.get('section'))
            # 声明了 `after_group` 的分解图**就地**出图（见下面 ⑥ 那段注释里的例外条款）。
            # 排在本组 `_mark_section` 之后，好让分解图带自己的 section 走 ——
            # 混进上面那一段的话它会被无条件涂成本组的 section。
            n = self._decomp_here(ex, n, g['zh'])

        _s0 = len(ex)
        for c in self.head:                                   # ④ 季节性
            e = self.ex_season(n, c)
            if e is not None:
                ex.append(e); n += 1
        _mark_section(ex, _s0, self.spec.get('season_section'))

        for g in self.groups:                                 # ⑤ 存量列单独成图
            _g0 = len(ex)
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
            _mark_section(ex, _g0, g.get('section'))

        # ⑥ 量价分解 与 ⑦「水平值 + 单月同比」：**缺省追加在最末**（核对表之前）。
        # 缺省不插在 ③ 里，理由没变：图号一移，正文与图注里所有「见 Exhibit k」的
        # 交叉引用全错，而那种错不会报任何异常。新图型往后加，既有图号一个都不动。
        #
        # ⚠️ **`after_group` 是明示例外**（2026-09 按页面所有者的指令加：
        # 「把分解图前移到紧跟它的输入之后」）。它就地出图，因此它之后的每一张图
        # 号都会平移 —— 所以**用它的页必须自己保证 spec 与页尾文案里没有指着
        # 「本轮这一版」的硬编码图号**（底座自己生成的那些「见 Exhibit k」都是现算的，
        # 跟着走不会错；靠不住的是人手写死在 spec 注释 / notes / glossary 里的那些）。
        # 判据是 `grep -n 'Exhibit [0-9]' build/specs/<页>.py` 的每一处都能归进
        # **三类白名单**：① 汇总表 Exhibit 1（底座把它钉在 1 号，永不移动）；
        # ② 历史账里的「原 Exhibit N」（明文冻结的改版前编号，正是页面所有者
        # 「删图要向读者交代」那条指令要求写的东西，跟着新编号改反而会让它指错）；
        # ③ 注释里标着「别改」的改版前实测证据。归不进去的才是会过期的引用。
        # ⚠️ **这句话原来写的是「今天只有 asx 满足（其余 8 家各有 2–8 处）」——
        # 已经过期，别再照它判。**asx 自己那轮的历史账就往 asx.py 里写进了 5 处
        # 「原 Exhibit N」；2026-09 的 tmx 同样一边用 after_group、一边按同一条指令
        # 写历史账。判据因此从「grep 为空」改成上面那三类白名单，两条指令不再打架。
        # 下面这一轮只处理**没有** after_group 的那些（有的已在 ③ 里就地出过了）。
        for d in self.decomp:
            if d['after_group']:
                continue
            _d0 = len(ex)
            e, why = self.ex_decomp(n, d, ex)
            if e is None:
                self.skipped.append(why)
                continue
            ex.append(e); n += 1
            _mark_section(ex, _d0, d.get('section'))
        for t_ in self.level_yoy:
            _d0 = len(ex)
            e, why = self.ex_level_yoy(n, t_)
            if e is None:
                self.skipped.append(why)
                continue
            ex.append(e); n += 1
            _mark_section(ex, _d0, t_.get('section'))

        # ── 第二趟：把月度分解图注里那句**页面级**交叉引用填上（见 `_pleg_fill`）──
        # 位置是硬要求，不是随手放的：
        #   · 必须排在**全部** exhibit 都进了 `ex` 之后 —— 那句话说的是「本页…」，
        #     判据的范围必须与断言的范围一致（`after_group` 会把分解图挪到页中间，
        #     一趟走完时它后面的图还一张都没建）；
        #   · 必须排在 `chartscale.fix_all()` 之前 —— 那一步 pop 掉 `_cols`（按列认图
        #     的唯一依据）并按显示量级缩放数值。
        self._pleg_fill(ex)
        # 占位符一个都不许上页。回填哪天被绕过去（新加一条分解路径、或者哪张图被
        # 后面的步骤替换成了新 dict），这里当场停机 —— 页面宁可不出，也不发一串
        # 控制字符或者半句话。判据现读 payload，不依赖 `self._pleg` 那本账。
        _left = [e_.get('n') for e_ in ex if PLEG_MARK in (e_.get('note') or '')]
        if _left:
            raise SpecError(
                f'[{self.ticker}] Exhibit {_left} 的图注里还留着中蓝段占位符 —— '
                f'`_pleg_fill()` 没有回填到它们（`_decomp_monthly` 埋占位符那一处'
                f'与本页的记账 `self._pleg` 已经对不上了）')

        # 分节标题收口：`_mark_section` 只是把「这一段想要什么标题」记在 `_section` 上，
        # 真正决定「哪一张图起标题」在这里 —— 想要的标题与上一张相同就不重复起，
        # 于是「一个 section 跨好几个 group」只要在这些 group 里都写同一个字符串即可。
        _last = None
        for e_ in ex:
            want = e_.pop('_section', None)
            if want and want != _last:
                e_['section'] = want
            if want:
                _last = want

        # ── 标题里的「YYYY-MM 起」与图窗左端对不上时补一句（见 title_since_zh）──
        # 放在这里而不是各 ex_* 里：判据只跟最终 payload 有关（标题 + 横轴），
        # 散在每个 ex_* 里必然漏掉后加的图型 —— 与下面 axisfmt 那一步同一个理由。
        # 必须排在 chartscale / _layout_long 之前：那两步会往 note 末尾追加自己的
        # 排版说明，插在它们后面会把「标题与横轴」这件事挤到排版话术的下面去。
        for e_ in ex:
            since = title_since_zh(e_)
            if since:
                e_['note'] = (e_.get('note') or '') + since

        # ⑥ 显示缩放：把 9 位数压成 3 位数。**必须排在 axisfmt 之前** —— 轴刻度的
        # 小数位是按最终数值算的。只动图（series / ylab / 数值格式器），
        # summary() 与 table() 走的是 self.ser()，一个字节都不碰，仍是官方原始量级。
        # 顺带把各 exhibit 上的临时键 `_cols` pop 掉。
        disp = chartscale.fix_all(ex)
        # 缩放会把 `ycap` 一起除掉（`chartscale._SCALARS`），但**画在绘图区里的那行
        # 「axis capped at …」不在它的名单里**，会留在原始量级上，与它旁边的轴顶差一个
        # 缩放倍数。所以缩完立刻按新的 `ycap` + 新 `fmt` 把它重写一遍。见 `recap_notes()`。
        self.recap_notes(ex)

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

        # ⑨ 逐图代价的账本自检（§6.1 第 3 条）—— 必须排在 notes() 之前：
        # 页尾那句「上面每一张…」正是拿这本账写的，账本不对就不该发出这一页。
        self.audit_mom_cost()

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
                        f'（{len(idx)} 个月{through_gap(latest, newest)}）'
                        f'· 本币 {self.spec["ccy"]} · '
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
        # 名词释义：排在**所有 exhibit 之前**（CONTRACT §1）。内容全部来自
        # spec['glossary']，底座一个字都不写 —— 这一页的词该怎么定义是那一页自己的
        # 口径判断，与 notes 同一条分工。不给这个字段就整块不渲染（page.js 判空）。
        g = self.spec.get('glossary')
        if callable(g):                       # 需要从 CSV 现算结构性数字的家传函数
            g = g(self)
        gh = gloss.render(g, where=f'{self.ticker} glossary')
        if gh:
            payload['glossary'] = gh
        # 数据总结（brief）：与 glossary **同一套分派**（字面量或 callable(page)）。
        # 分工也一样 —— 版式与 230–380 字护栏在 build/brief.py，措辞在 spec 自己那边：
        # 「措辞是口径的一部分」。R1–R6 只算事实，句子由各页自己拼。
        # 不给这个字段就整块不渲染（页壳里那个 div 判空 hidden）。
        br = self.spec.get('brief')
        if callable(br):
            br = br(self)
        if br:
            payload['brief'] = B.render(br)
        # 抬头右侧「官方发布于 X」。台账按月钉死，所以只查 data_through 这一个月；
        # 查不到就**整个字段不写** —— 渲染端判的是字段在不在，给 None 会印出一句空断言。
        day = source_dates().lookup(self.series_dir, self.ticker, str(latest))
        if day:
            payload['source_date'] = day
        # ── 有「发布更快的腿」时，抬头还欠一句：那多出来的一期是什么时候发的 ──────
        # newest > latest ⇒ 整表已经有比数据月更晚的月份（只有快腿那几列有值），
        # 而**那些月份是真的印在页面上的**：核对表多一行，快腿各列的图各自多画一根柱。
        # 只印 source_date 的话，抬头那句「官方发布于 <latest 的发布日>」对页面上最新的
        # 那部分内容就是假的 —— ndaq 2026-09 就撞上了：抬头写 2026-08-05（07 月那期），
        # 而页面上画着的 Aug-26 是 2026-09-02 才发的，日期就躺在同一张台账里。
        # ⚠ 不能改成「查 newest」了事：CONTRACT 的 `source_date` 明写**不许把新一期的
        # 发布日安到旧月份上**。所以另起字段、自带月份标签，两句话各自成立、互不冒充。
        if newest != latest:
            fast = source_dates().lookup(self.series_dir, self.ticker, str(newest))
            if fast:
                payload['source_date_fast'] = fast
                payload['source_date_fast_label'] = mlab(newest)
        return payload, None

    # ────────────────────── 口径与方法说明 ──────────────────────
    def notes(self, latest, common, ex, scaled, newest, disp, _scales=()):
        # spec 的页尾条目允许写成 `callable(page)`（见本方法末尾那段分派）。那种条目要读的
        # 是**建好之后的 payload**（例如「本页哪几张图截了轴、截在多少」），而 `notes()`
        # 是唯一同时拿得到 page 与建好的 exhibits 的地方 —— 挂到 page 上供它们取用。
        self._ex = ex
        idx = list(self.df.index)
        head_zh = '、'.join(c['zh'] for c in self.head)
        out = [
            f'<b>数据源与口径。</b>全部数值来自本仓 <code>series/{self.spec["csv"]}</code>，'
            f'{strip_source(self.spec["source"])}。'
            f'覆盖 {mlab(idx[0])} – {mlab(newest)}'
            f'（{len(idx)} 个月{through_gap(latest, newest)}）。'
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
                # ⚠️ **「没画线」有两种，理由完全不同，合成一句就会替其中一种编假理由。**
                #   · 问过断点、没命中（`mark_breaks` 调过，但这张用的列上没登记）
                #     ⇒ 理由是「断点按列登记，只画到用了那一列的图上」；
                #   · **根本没问过**（`bridge_bar` 那一支不调 `mark_breaks`）
                #     ⇒ 理由是「这一图型不挂断点线」，与它用了哪几条列无关。
                # 2026-09 之前这里只有前一句：/tmx/ 那两张月度量价分解的量腿正是登记了
                # 换源断点的那条列（同一条列在别的图上画着红线），拿前一句去解释它就是假话。
                # 判据取自构建期的事实账（`self._brk_asked`），不是按图型写死的名单。
                asked = getattr(self, '_brk_asked', set())
                s_col = [e for e in silent if e['n'] in asked]
                s_kind = [e for e in silent if e['n'] not in asked]
                # ⚠️ 只有**两档同时存在**时才把名单拆开重列一遍。只剩一档时整份名单就是
                # 那一档，再抄一遍是排版噪声（而且那句话本来就成立）—— 这也让没有第二档
                # 的页面逐字节不变。
                by_col = ('断点是<b>按列</b>登记的，只画到用了那一列的图上，'
                          '而窗口跨不跨断点月是另一回事。')
                # ⚠️ **这一档的措辞必须限定在「它自己窗口里跨到的那几个断点月」上，
                # 不许说成「它用的列上一条断点都没登记」。** 两者不等价：一张图可以
                # 既用着登记了断点的列、又落在这一档 —— 只要那条断点**不在它的窗口里**。
                # 2026-09 收口复核实测的例子在 /asx/：那张「参与者保证金·旧口径
                # （…已停发）」画的正是登记了 2024-08 断点的列，但它的窗口停在 2024-07，
                # 断点在窗外；它之所以进 `silent`，是因为窗口里含着**另一个**断点月
                # （2023-10，登记在几条 capital 列上，那几条它确实没用）。
                # 说成「用的都不是登记了断点的那几条列」对它就是假话。
                # 判据本身是现成的、而且恰好就是 `mark_breaks` 刚算过的那一件事：
                # 这几张图之所以在 `silent` 里而不在 `drawn` 里，就是因为
                # 「窗口 ∩ 本图各列登记的断点月」为空 —— 所以限定版按构造为真。
                kz = '、'.join(sorted({BRK_NODRAW_ZH.get(e['kind'], e['kind'])
                                       for e in s_kind}))
                # ⚠️ **「跨断点的那几格改由它们各自的图注点名交代」这半句不许无条件印。**
                # 它 2026-09 上一轮是挂在 by_kind 末尾的一句无条件断言，而它只在
                # /tmx/ 上碰巧为真（那两张月度分解的图注确实逐句交代了 2021-08 换源那
                # 12 格）；在 /asx/ 上是假的 —— asx 唯一那张 `bridge_bar` 的两条输入列
                # **一条都没登记断点**，它压根没有可交代的东西，图注里「断点」「换代」
                # 「红色竖虚线」也确实出现 0 次。同一句话被两页共用，于是一页真、一页假。
                #
                # 改成现算，判据全是构建期已知的事实，一个都不写死：
                #   ① 这张图用了哪几条列 —— `self._nodraw_cols`（`note_nodraw_cols()` 记；
                #      `_cols` 指望不上，它在 `chartscale.fix_all()` 里早被 pop 掉了）；
                #   ② 哪几条列登记了断点、断在哪个月 —— `self.breaks`；
                #   ③ 那半句说的是**别人图注里的内容**，所以还要那张图的图注真的把那个月
                #      印出来了才敢说。三条都过才印，否则各说各的：
                #        · `k_told` 输入列上登记了断点，且它自己的图注点了那个月；
                #        · `k_mute` 输入列上登记了断点，但它的图注没点名 ⇒ 不许替它认领，
                #          改成告诉读者自己扣；
                #        · `k_free` 输入列上一条断点都没登记 ⇒ 那半句一个字都不印，
                #          只照实说「它的列上没登记断点、红线本来也画不到它身上」。
                #          ⚠️ 这一档说的是**断点表**，不是「这张图没有任何口径问题」——
                #          2026-09 的 /tmx/ Exhibit 23 就在这一档，而它自己的图注照样
                #          交代着 2021-08 换源（那次换源只登记在成交股数那条列上，
                #          它用的成交额 / 成交笔数两条列都没登记）。措辞因此只敢说
                #          「没登记」与「画不出线」，一个字都不许扩到「没什么可交代」。
                #        · 三档都不进（没记过输入列的图型）⇒ **什么都不说**。
                brk_hit, k_told, k_mute, k_free = {}, [], [], []
                for e in s_kind:
                    got = self._nodraw_cols.get(e['n'])
                    if got is None:
                        continue
                    xls = set(e.get('xlabels') or ())
                    hit = sorted({str(b['month']) for b in self.breaks
                                  if b['col'] in set(got) and mlab(b['month']) in xls})
                    if not hit:
                        k_free.append(e)
                        continue
                    brk_hit[e['n']] = hit
                    en = e.get('note') or ''
                    (k_told if all(m in en or mlab(pd.Period(m, 'M')) in en for m in hit)
                     else k_mute).append(e)

                def _kseg(lst, alone):
                    """一档 → 它在 by_kind 里的那半句（`alone` = 这一档就是全部）。

                    `alone` 时不再把图号抄一遍（前半句刚点过名），改用代词；否则按
                    「Exhibit N、M 」点名 —— 末尾那个空格是全站写法（中文与 ASCII 之间空一格）。
                    """
                    one = len(lst) == 1
                    who = ('而' + ('它' if one else '它们')) if alone else \
                          ('Exhibit ' + '、'.join(str(e['n']) for e in lst) + ' ')
                    mn = sorted({m for e in lst for m in brk_hit.get(e['n'], ())})
                    ms = '、'.join(mn)
                    if lst is k_told:
                        return (f'{who}用到了登记了断点的列（断在 {ms}），跨断点的那几格改由'
                                + ('它自己' if one else '它们各自') + '的图注点名交代')
                    if lst is k_mute:
                        return (f'{who}用到了登记了断点的列（断在 {ms}），而'
                                + ('它自己' if one else '它们各自')
                                + '的图注里没有点到' + ('这个月' if len(mn) == 1 else '这些月')
                                + '，读' + ('它' if one else '它们')
                                + '的跨断点格要照本条开头那几个月自己扣')
                    return (f'{who}用的输入列上一条断点都没登记，'
                            + '红线本来也画不到' + ('它' if one else '它们') + '身上')

                got_k = [g for g in (k_told, k_mute, k_free) if g]
                alone = len(got_k) == 1 and len(got_k[0]) == len(s_kind)
                # 「不过」是给读者的转折提示：上半句说红线画不画与列无关（图型的事），
                # 下半句说的是另一件事 —— 这几张图各自的列上到底登记没登记断点。
                # 只在「有一档确实登记了断点」且要点名图号时才需要，其余两种情形
                # 那半句本来就以「而它/它们」起头，再加转折词就是叠字。
                lead = ('；不过 ' if got_k and got_k[0] is not k_free and not alone
                        else '；')
                by_kind = (f'<b>这一图型本身不挂断点线</b>（构建时根本没登记过断点），'
                           f'与{"它" if len(s_kind) == 1 else "它们"}用了哪几条列无关'
                           + (lead + '；'.join(_kseg(g, alone) for g in got_k)
                              if got_k else '') + '。')
                if not s_kind:
                    # 只剩这一档时不再逐图点名（前半句刚点过），但限定语照旧要有 ——
                    # 上面那段注释里的 /asx/ 例子正落在这一档。
                    why = ('—— 它们在自己的窗口里跨到的那几个断点月，'
                           '都没有登记在它们用的列上：' + by_col)
                elif not s_col:
                    # 单复数跟着张数走（本文件其余几处同款）：jpx 只有一张 bridge_bar，
                    # 写「这几张都是」会让读者去找不存在的第二张。
                    why = (('—— 这张是' if len(s_kind) == 1 else '—— 这几张都是')
                           + f'{kz}，' + by_kind)
                else:
                    why = ('：其中 Exhibit ' + '、'.join(str(e['n']) for e in s_col)
                           + f' 在它们自己的窗口里跨到的那几个断点月，都没有登记在'
                             f'它们用的列上（{by_col[:-1]}）；'
                           + '另有 Exhibit ' + '、'.join(str(e['n']) for e in s_kind)
                           + f' 是{kz}，' + by_kind)
                out.append(
                    '<b>⚠️ 口径断点。</b>' + txt + '。红色竖虚线画在 Exhibit '
                    + '、'.join(str(e['n']) for e in drawn)
                    + '（断点那一期的<b>左缘</b>，语义是「从这一期起与左侧不可比」）'
                    # 「其中至少一个」不是修辞上的谨慎：`silent` 的判据是
                    # 「本图 xlabels 与断点月集合**有交集**」，一张图跨到几个断点月
                    # 是它自己窗口的事（/asx/ 那张停发的旧口径图就只跨到两个里的一个）。
                    # 写成「跨过这些月份」等于替每一张都认领了全部断点月。
                    + (f'。<b>另有 {len(silent)} 张图的横轴窗口同样跨过其中至少一个月份、'
                       f'但没有画线</b>'
                       f'（Exhibit ' + '、'.join(str(e['n']) for e in silent)
                       + '）' + why
                       + '读这些图的跨断点比较同样要扣掉这一层。'
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
        _has_rr = bool(getattr(self, 'saw_ratio_rhs', False))
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
               # ⑤ 的「两张」不能无条件印：合计那一列已经被本页别处那张更宽的柱图
               #    画过时，这一组只出后一张（`mix_folded`，见 `total_drawn_wider`）。
               #    哪几组、宽在哪、绝对量去哪看、后一张有没有画成，全部由
               #    `mix_folded_zh()` 逐组现算 —— 写死一句「都出两张」，
               #    在这一页上就是一句读者一数就能拆穿的假话。
               + ('⑤ 声明了 <code>mix</code> 的组出<b>两张</b>：合计的水平值柱'
                  '（次轴同比，流量走单月、存量走点对点）与分项的 100% 占比堆叠。'
                  '各段之和逐月复算，对不上就不发页。'
                  + self.mix_folded_zh()
                  if _has_mix else '')
               + ('⑥ 声明了 <code>ratio_rhs</code> 的组（num ⊆ den 这个包含关系）'
                  '不画折线，改画并排柱 + 右轴比值线：引擎里 <code>lines</code> / '
                  '<code>lines_endlabels</code> 没有次轴，而比值与水平值不同量纲，'
                  '同轴会把柱压扁。包含关系逐月复算（den &gt; 0、num ≤ den），'
                  '对不上就不发页。' if _has_rr else '')))
        # ── 同比口径：从 yoy_log 账本现算，逐处点名（写法出自 CONTRACT §6.2；
        #    §6.1 第 3 条的 ⚠️ 明说页尾这段顶替不了逐图那一段，逐图那段在图注里）──
        # 这段话为什么必须由底座生成、图号为什么必须派生，见 log_yoy 的 docstring。
        # 文案按类别分段拼装，只写账本里真有的类别。
        # ⚠️ 2026-09 起本底座**一条滚动同比都不产出**（页面所有者指定全站单月口径），
        # 所以这里再没有「本页并存两种口径」那条分支 —— 留着它等于替一种页上不存在的
        # 口径预留一句话，而 `YOY_CALS` 已经不认 'ttm'，那条分支永远进不去。
        cal_ns = {}
        for r in self.yoy_log:
            cal_ns.setdefault(r['cal'], set()).add(r['n'])
        if cal_ns:
            def _exs(k):
                return '、'.join(f'Exhibit {j}' for j in sorted(cal_ns[k]))
            seg = []
            if 'mom' in cal_ns:
                seg.append(
                    f'{_exs("mom")}：<b>单月同比</b>（当月对去年同月，本列除本列）——'
                    f'全页统一口径，页面所有者指定。单月口径吃基数与日历效应'
                    f'（当月开市天数、假期与到期日的月度形状、去年同月那一个数的高低），'
                    f'毛刺比 {TTM_WIN} 个月滚动口径大得多'
                    f'（<b>那种口径本页一条线都不画</b>）'
                    # 逐图代价（§6.1 第 3 条）现在由**每一条**画流量单月同比的路径印出
                    # （2026-09 补上 `ex_single` 与 `ex_yoy` 两条；在那之前只有开篇图 /
                    # mix 合计柱 / level_yoy 三条走，全站 87 张里只有 20 张印了，
                    # 而这里当时无条件写着「每张图的图注里都…标出了这笔代价」，
                    # 对另外 67 张整句为假）。所以这句话分三种形态，全部由账本派生：
                    #   · 全覆盖 → 说「上面每一张」，不再抄一遍十几个图号；
                    #   · 有几张可比月太少 → **点名**它们，并说清它们印的是
                    #     「量不出来」而不是什么都没印 —— 只列印出来的那几张，
                    #     读者无从判断剩下的是漏了还是本来就量不出来；
                    #   · 一张都没印 → 整句消失。
                    + self.cost_ns_zh(cal_ns['mom'])
                    + f' —— <b>这条线要连着柱高一起读</b>')
            if 'mom_pp' in cal_ns:
                seg.append(
                    f'{_exs("mom_pp")}：比率列的同比 = 单月口径的<b>百分点差</b>'
                    f'（比率不做滚动合计也不做滚动均值 —— 「一年的平均比率」要按量'
                    f'加权，换个窗口得不到）')
            if 'mom_money' in cal_ns:
                # 比率里「分子是钱」的那一档：差还是钱，不是 pp/bp（`unit_is_money_ratio`）。
                # 这里不复述单位 —— 每一张的单位写在它自己的轴标题与图注里，
                # 页尾再抄一遍就多一处会漂的副本。
                seg.append(
                    f'{_exs("mom_money")}：这几列的比率<b>分子是钱</b>，所以同比是'
                    f'<b>当月减去年同月的差、单位就是该列自己的量纲</b>'
                    f'（每一个活动单位差多少钱），<b>不是 pp 也不是 bp</b> —— '
                    f'算术与上一档完全相同，只是差的单位跟着分子走')
            if 'stock' in cal_ns:
                seg.append(
                    f'{_exs("stock")}：存量列的<b>点对点同比</b>（月末快照 vs 去年'
                    f'同月月末）—— 存量不可加总，把 12 个月末快照相加不指代任何'
                    f'真实的量，所以存量没有「滚动合计」口径可选')
            if 'heat' in cal_ns:
                seg.append(
                    f'{_exs("heat")}（热力矩阵）：格内是<b>单月同比</b>，按豁免保留 '
                    f'—— 这张图逐格看的就是单月波动，抹平了信息就没了')
            if 'heat_pp' in cal_ns:
                seg.append(
                    f'{_exs("heat_pp")}（热力矩阵，整组都是比率列）：格内是单月同比的'
                    f'<b>百分点差</b>（pp），不是百分比变化 —— 色标与别的矩阵不同单位，'
                    f'两张矩阵之间的颜色深浅不可比')
            if 'heat_money' in cal_ns:
                seg.append(
                    f'{_exs("heat_money")}（热力矩阵，整组都是<b>分子为钱</b>的比率列）：'
                    f'格内是单月同比的<b>差</b>，单位是该组自己的量纲（写在图例上），'
                    f'<b>不是 pp 也不是 bp</b>；色标与别的矩阵不同单位，颜色深浅不可比')
            out.append(
                '<b>同比口径（全页只有一种：单月）。</b>' + '；'.join(seg) + '。'
                + '汇总表（Exhibit 1）的 m/m 与 y/y 列及页顶抬头行同样是「本月 / 上月 / '
                  '去年同月」三个具名月份的<b>单月</b>读数，与图上那条金线同口径 ——'
                  '本页任意两处增速可以直接比高低，不需要先核对口径。')
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
        # 声明了 decomp / level_yoy 却没画出来，一律点名说是哪一条、为什么 ——
        # 静默少一张图与「这家本来就没有这张图」在页面上长得一模一样。
        if getattr(self, 'skipped', None):
            out.append('<b>本轮未出的派生图。</b>'
                       + '；'.join(self.skipped)
                       + '。数据补齐后自动回来，不需要改 spec。')
        # `after_group` 的锚点组本轮整组不在页上 ⇒ 分解图退回缺省位置（页尾）。
        # **同样没有并进上面那本账**：上面那段说的是「没出」「补齐后回来」，
        # 而这一档的图**出了**，只是位置变了 —— 塞进去就是一句假话。理由同下面 dup 那段。
        if getattr(self, 'decomp_moved', None):
            out.append('<b>本轮改排页尾的分解图。</b>'
                       + '；'.join(self.decomp_moved)
                       + '。<b>图本身照常出、每一格的数一个都没变</b>，'
                         '变的只有它在本页的排序位置：本来该紧跟它的输入之后，'
                         '现在退到页尾。源表补上那几列之后自动回到原位，不需要改 spec。')
        # 同一条同比画了两遍（只告警的那一档）。**没有并进上面那本账**：
        # 上面那段的收尾是「数据补齐后自动回来」，而这一档的图**已经出了**、
        # 也不会因为数据补齐而变化 —— 塞进去就是两句假话（说它没出、说它会回来）。
        dup = self.dup_yoy_zh()
        if dup:
            out.append(dup)
        # spec 的页尾条目：**字面量或 `callable(page)`** —— 与 `glossary` / `brief` 同一套
        # 分派（见 `payload()` 里那两处）。要现算的条目必须走 callable：写成字面量的那一刻
        # 它就开始过期，而页尾没有任何东西在守它。
        # ⚠️ 为什么这类话不由底座无条件印一段：`build/single.py` 服务 9 张 spec 页，
        #    底座每多印一段，9 页的 payload 就一起变。**哪一页要哪一段由那一页的 spec 说了算，
        #    话本身仍然由底座现算**（例如 `Page.cap_zh()`：spec 里一个数字、一个图号都没有）。
        # ⚠️ **callable 返回空串 ⇒ 整条丢掉**，这是 callable 那一支的「收放」出口：
        #    一条只在某种情形下才成立的话（`page.cap_zh()` 已经有 `return ''` 这一支；
        #    `tmx` 的并图历史账同理），不成立时应当**整条消失**，而不是在页尾留一个
        #    空条目。不 strip 原串：只判空，不改内容，既有页面逐字节不变。
        # ⚠️ **只作用在 callable 这一档**（2026-09 收口时缩回来的）。上一版对字面量
        #    也丢，那是一条 9 页共用、没有任何信号的底座行为改动：spec 里声明的东西
        #    可以无声消失，而同一轮自己刚立的两条规矩是「mix 的 note 成死配置就硬失败」
        #    「合计柱有意不出必须另打一行日志」—— 不同调。字面量空串是 spec 写错，
        #    不是「这一次不成立」，它该原样露在页面上被人看见，而不是被底座悄悄吞掉。
        # ⚠️ **收起来的必须响一声**：记进 `self.notes_folded`，`build()` 另打一行给
        #    维护者（与「合计柱有意不出」那行同源同理由）。callable 写错、恒返回 ''
        #    时，整条页尾说明会从页面上消失，而构建输出里一个字都没有。
        self.notes_folded = []
        spec_notes = []
        for i, v in enumerate(self.spec.get('notes') or []):
            if not callable(v):
                spec_notes.append(str(v))
                continue
            x = v(self)
            if x.strip():
                spec_notes.append(x)
            else:
                self.notes_folded.append({'i': i, 'name': getattr(v, '__name__', '?')})
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
    # 图出了、但位置从 `after_group` 退回页尾。单独一行、不并进上面那一档：
    # 上面那行说的是「未出」，这一行说的是「出了但挪了位」，两件事。
    for why in (getattr(page, 'decomp_moved', None) or []):
        if not quiet:
            print(f'[{t}] ⚠️ 分解图改排页尾：{why}')
    # 同一条同比画在两张图上（同族同窗口那一档已经在 log_yoy_bar 里硬失败了，
    # 到这里的都是「留着有信息、但读者会以为看漏了差别」的那一档）。
    # 不硬失败，但必须响：页尾那段是给读者的，这一行是给维护者的。
    for d in (getattr(page, 'dup_yoy', None) or []):
        if not quiet:
            a, b = d['a'], d['b']
            print(f'[{t}] ⚠️ 同一条同比画了两遍：Exhibit {a["n"]}（{a["where"]}，'
                  f'{a["win"][0]}–{a["win"][1]} {a["win"][2]} 个月）与 Exhibit {b["n"]}'
                  f'（{b["where"]}，{b["win"][0]}–{b["win"][1]} {b["win"][2]} 个月）'
                  f'同列 {d["col"]}、同口径 {d["cal"]}'
                  + ('，窗口也逐格相同' if a['win'] == b['win'] else '，窗口不同'))
    # 「合计柱**有意**不出」那一档（`Page.total_drawn_wider`）。这一档不进 `skipped`
    # ——那本账是给「想画而画不成」用的——但同样**必须响**，理由与上面那条逐字同源：
    # 页尾那段是给读者的，这一行是给维护者的。少一张图而构建输出里一个字都没有，
    # 与「这家本来就没这张图」在日志里长得一模一样；而这本账恰恰是唯一一本
    # **会让一张图从页面上消失**的账。
    for d in (getattr(page, 'mix_folded', None) or []):
        if not quiet:
            print(f'[{t}] ⚠️ 合计柱有意不出：groups「{d["gz"]}」.mix 的 {d["col"]} '
                  f'折进 Exhibit {d["n"]}（{d["where"]}，{d["wide"][0]}–{d["wide"][1]} '
                  f'{d["wide"][2]} 个月），本组这张本来要画 {d["own"][0]}–{d["own"][1]} '
                  f'{d["own"][2]} 个月（是它{d["side"]}）'
                  + ('' if d['share_drawn'] else
                     '；⚠️ 占比堆叠也没画成，这一组本轮 0 张图'))
    # 页尾条目按现算结果**整条收起**那一档（`callable(page)` 返回空串，见 `notes()`）。
    # 同样不硬失败、同样必须响：那是 spec 里声明过的一整段说明从页面上消失，
    # 与「合计柱有意不出」逐字同源 —— 页尾那边什么都不会留下，只有这一行看得见。
    for d in (getattr(page, 'notes_folded', None) or []):
        if not quiet:
            print(f'[{t}] ⚠️ 页尾条目整条收起：spec notes 第 {d["i"]} 条'
                  f'（{d["name"]}）本次现算为空串')
    # 近零基数（§6.1 第 5 条）：命中的图逐条打印。不硬失败 —— 线是页面所有者要留的，
    # 这一行是给维护者的清单，好让「今天到底是哪几张」随时能重跑出来，
    # 而不必去散文里翻一个会过期的数。
    for z in (getattr(page, 'nz_ns', None) or []):
        if not quiet:
            print(f'[{t}] ⚠️ Exhibit {z["n"]} 近零基数：{z["col"]}（{z["zh"]}）'
                  f'窗口内 {z["k"]}/{z["n_base"]} 个月基期近零（{z["share"]:.1%}）'
                  + (f'，右轴已截到 +{z["cap"]:.0f}%' if z['cap'] else '，未截轴'))
    # 尖刺截轴同理：这一行是给维护者的清单，好让「今天到底截了哪几张、截在多少」
    # 随时能重跑出来，而不必去页面散文里翻一个会过期的数。
    for z in (getattr(page, 'cap_ns', None) or []):
        if not quiet:
            print(f'[{t}] ⚠️ Exhibit {z["n"]} 尖刺截轴：上界 {z["cap"]:,.0f} {z["unit"]}'
                  f'（Tukey 栅栏 {z["fence"]:,.0f}、日常上沿占未截轴的 {z["head"]:.1%}）'
                  f'，{len(z["over"])} 个越界点：'
                  + '、'.join(f'{m} {nm} {v:,.0f}' for m, nm, v in z['over']))
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
    # payload 覆盖回 decomp/level_yoy/seasonality 那套旧图列 —— 页面不报错、闸门也全过，
    # 只是图列悄悄换了一套。这是本轮路由审计查出的唯一真撞车口子，故在这里单向堵死。
    # 2026-09 判据放宽：从「build/<t>.py 里有没有 mrbase 字样」改成「build/<t>.py 在不在」，
    # 与 monthly_run.builder() 同源（那边也只看文件在不在，不认名字）。
    # 起因是 ice：它从 build/specs/ 改成了手写的 build/ice.py，而手写页里没有 mrbase 这个词，
    # 旧判据认不出来 —— 只要 spec 还在，跑一次 `--all` 就会把它的 payload 覆盖回旧图列。
    # 放宽之后这一支同时盖住两类被别处接管的页（mrbase 薄壳 与 手写生成器），
    # 而「specs 有、build/<t>.py 没有」的那 9 家交易所不受影响。
    owned = [t for t in ts if os.path.exists(os.path.join(HERE, f'{t}.py'))]
    if owned:
        for t in owned:
            print(f'[{t}] 跳过：本页由 build/{t}.py 接管（mrbase 薄壳或手写生成器），'
                  f'用 `python3 build/{t}.py` 重建，不要走 single.py')
        ts = [t for t in ts if t not in owned]
        if not ts:
            # 显式点名给的 ticker 全被挡下 ⇒ 是用错命令了，非零退出把它喊出来。
            # `--all` 展开后全被挡下不可能发生（specs/ 里还有 9 家交易所）。
            return 1

    for t in ts:
        build(load_spec(t))
    return 0


if __name__ == '__main__':
    sys.exit(main())
