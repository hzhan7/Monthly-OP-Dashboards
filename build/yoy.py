# -*- coding: utf-8 -*-
"""同比口径的**唯一实现**。所有生成器算同比一律走这里，不要再各写一遍。

## ⚠️ 2026-09：默认口径改成单月，本文件的角色跟着变

页面所有者的指令（CONTRACT §6 抬头引了原话）：**全站同比一律用单月**
（当月 ÷ 去年同月 − 1）；除了 §6.2 那张点名的例外表，页面上一条 12 个月滚动合计的
同比都不画。⚠️ 那个「除了」从句不许丢 —— §6.5 记着 `HANDOFF` 里正是丢掉它之后，
同一句话就成了假话（例外表上那几张今天仍然在画滚动同比，而且是契约批准的）。

于是本文件里的函数分成两类，用途完全不同：

  · **上页的**：`mom_yoy()` —— 流量、存量、比率三种 kind 全走它，页面上每一条
    同比线都由它算。
  · **只作对照的**：`ttm()` / `ttm_yoy()` / `ttm_mean_yoy()` / `ttm_yoy_unchecked()`。
    它们**没有被删**，因为 CONTRACT §6.1 第 3 条要求每张**流量**同比图印出单月口径的
    代价，而「代价」正是拿这一侧比出来的（`caliber_diff()` / `describe()` 内部在用）。
    **它们的返回值不许再进 payload 的 `values`。** 唯一的例外是 §6.2 那张表 ——
    **两页五张，每一张都不是折线**：`exchanges-apac` Ex5 与 Ex15、
    `exchanges12` Ex4 / 7 / 8。（上一版这里漏写了 Ex15，只说「两处」，
    与 §6.2 的「`exchanges-apac` 两张、`exchanges12` 三张」对不上。）

## 为什么要有这个文件

同比原先各家自己写。`build/CONTRACT.md` 开头那句「`to_monthly` / `yoy_line` 这批
零件在 cme.py、cboe.py、hkex.py 里各实现了一遍」说的就是它。
今天 `cme.py` / `cboe.py` / `hkex.py` / `single.py` 里仍各有一个叫 `yoy_line` 的函数，
但四个的函数体都已经只是**转发层** —— 算术转给本文件的 `mom_yoy()`，自己只管窗口
对齐、近零掩码这类外围的事。同比的**算术**只剩本文件这一份。
副本的代价不是重复代码，是**同一个判断要做 N 次，漏掉一次不报错**。

⚠️ **收敛还没做完，别以为它做完了 —— 而缺口就在本文件这一侧**：`caliber_diff()`
开头那个 `if kind != FLOW` 分支对存量与比率**根本不比**，滚动那一侧全回 `None`。
于是凡是要印「存量对 12 个月滚动**均值**同比」或「比率对百分点差」这类对照量的页，
共享实现给不了，只能自己再算一遍 —— 每多一份副本，同一个判断就要再做对一次。
要根治得给 `caliber_diff()` 补上这条对照支，那是另一轮的活。
⚠️ **哪几个生成器眼下还在自算、各自算的是哪一类，这里一律不复述。** 那是别的文件
当下的状态，抄进来当天就会漂（§6.4 连时点一起记着，并且明写要照 `grep -c
caliber_diff` 现数，别拿任何一个时点的快照当现状）。

2026-08 做过一次全站审计，逐序列复算两种口径的差异，用来支持「口径必须收敛」
这个判断。⚠️ **那批数一个都不在这里复述。** 它们连同 2026-09 的逐条复算结果
（哪几条对得上、哪几条只在退休了的旧图窗上成立、哪几条复算不出来）整节存在
CONTRACT §6.5，每一条都带窗口标注 —— **引用要连窗口一起引**。
在这里再抄一份就是在本文件里再存一份会过期的数：上一版的这段模块头正是
§6.5 点名的那个标本（五条实测一个窗口标注都没有，其中两条 §6.5 已判为复算不出来）。

要一句话的结论：不收敛的后果不是「图丑」，是**同一页里两张图对同一件事给出相反的
符号**，而读者没有任何线索知道该信哪张。这个病根 2026-09 统一成单月之后已经消掉
（§6.5 末段），但收敛这件事本身仍然只由这个文件保证。两种口径能差到什么程度，
`python3 build/yoy.py` 的第 ①⑤⑦ 节当场量给你看，不必信这段散文。

## 这个文件不做什么

不替调用方决定 `kind`。流量 / 存量 / 比率的判断需要知道那一列是什么东西，
`classify()` 只能按列名猜，猜错了后果很严重（把 OI 当流量做滚动合计 = 把 12 个
月末快照相加，那不是任何东西）。所以 `ttm()` / `ttm_yoy()` 的 `kind` 是**必填位置参数**,
没有默认值 —— 让「这是流量还是存量」这个判断在调用点显式写出来，而不是默认掉。

## 单位与交易日：日均序列不要乘回交易日

本仓的规范展示单位是**日均**（ADV / ADT / ADNV，per-day）。滚动合计因此是
「12 个日均值相加」，量纲是「日均 × 12 个月」。这看着别扭，但同比是个**比值**，
分子分母同权（都是 12 个日均之和），交易日在比值里直接约掉、根本不出现。
**不要为了「合计要有物理意义」把日均乘回交易日再加** —— 那会额外引进交易日序列的
误差，而它对同比的贡献恰好是你想抹掉的那部分噪声（cme Ex3 整张图讲的就是这件事：
交易日差异能在一个月之内把成交量的方向读反）。

而且跨家加权在物理上就做不到。**带交易日列的文件只是少数，而且各家口径互不相同**：
`asx` 有 3 列（cash / futures / eto）、`enx` 有 6 列、`db1` 有 2 列（eurex / cash）、
`hood` 的两列叫 `eqopt_trading_days` 与 `crypto_trading_days`、`lseg` 那三个文件
各带自己的一套；而 **`cboe.csv` 一个交易日列都没有**，`cost` / `lpla` / `msci` /
`schw` / `spgi` / `tsm` 也没有。横截面页（`exchanges*.js` / `wealth.js`）把这些家画在
同一张图上，只要有一家缺交易日列，「乘回交易日再比」这条路就断了。

⚠️ **这里不写「几个文件里有几个带交易日列」这种数** —— 它随 `series/` 长而变。
`python3 build/yoy.py` 的第 ⑥ 节当场清点，并把每一个带交易日列的文件连同它的列名
逐行印出来，清点方式也印在那里（文件数 = `series/*.csv`；月度序列表 = 表头含 `month` 列 ——
`cost.csv` 按 `ym` 记月，因此不进这个计数；带交易日列 = 表头有列名含 `trading_days`）。
上一版这段写死的「49 个文件、30 个月度序列表、13 个带交易日列」是 2026-08-07 的
清点，早已与同一个文件第 ⑥ 节当场印的数对不上 —— 一个文件里两处数字互相打脸，
这正是 §6.5 说的那条病。

（订正一处：任务单当年写的是「cboe.csv 与 hkex.csv 根本没有交易日列，只有 cme.csv
有」。实测 `hkex.csv` **有** `trading_days_cash`，真正一列都没有的是 `cboe`，
而带交易日列的文件远不止一个。结论方向不变 —— 缺口足以让跨家加权不成立。）

## 自测

    python3 build/yoy.py

用真实 `series/*.csv` 演示每个函数，并**当场重跑**下面所有阈值的推导 ——
阈值写死在常量里，但推导过程留在代码里，数据变了跑一遍就知道它还站不站得住。
"""
import glob
import os
import re

import numpy as np
import pandas as pd

# ── 口径常量 ────────────────────────────────────────────────────────────────
TTM_WIN = 12   # 滚动合计窗口（个月）。与 build/single.py 的 TTM_WIN 同值，改一处要改两处
LAG = 12       # 同比的比较跨度（个月）

FLOW = 'flow'    # 流量：成交量、成交额、募资额、净新增资产。可加总，滚动合计有意义
STOCK = 'stock'  # 存量/期末口径：AUM、市值、OI、账户数、余额。**不可加总**
RATIO = 'ratio'  # 比率：RPC、费率、占比、利润率。同比走百分点差，也不可加总
KINDS = (FLOW, STOCK, RATIO)

# 近零基数判据的阈值。**不是拍的**，推导见 near_zero_base() 的 docstring，
# 且 python3 build/yoy.py 会当场重跑这段推导。
NEAR_ZERO_BASE_FRAC = 0.15    # 基期 |b| < 本序列 |值| 中位数 × 这个数 → 该月同比不可读
NEAR_ZERO_SERIES_SHARE = 1 / 12  # 近零基数月占比 ≥ 平均每年一个月 → 整条序列别画同比

# caliber_diff 判「放大」的倍数。审计判「放大」用的就是 2 倍这条线，这里沿用，
# 好让工具输出与那份审计能对上号。审计那条「69% 的序列存在某个月 |单月| ≥ 2×|滚动|」
# 的复算结果（偏高多少、在哪个窗口上）见 CONTRACT §6.5，不在这里复述。
AMPLIFY_X = 2.0

# 自测里用来对齐**审计当年那个窗口**的长度。⚠️ 它已经不是任何一张图的窗口了：
# `WIN_LONG = 25` 这个常量 2026-08-18（commit 9888e3c）从 build/single.py 里删掉了，
# 全站时序图的左端换成了 `single.WIN_FROM = '2016-01'`，长度随月份增长。
# 所以这个常量只有一个用途：让第 ⑦ 节能在**审计量过的那段窗口**上重跑，好和 §6.5
# 里标着「近 25 个月」的那一组对得上。⚠ 别拿它当图窗，也别在散文里把它写成图窗。
WIN_LONG_DEMO = 25

# 至少要有这么多个「两种口径都有值」的月份才出诊断。
# 12 是下限的理由：少于一整年，「符号相反的月份占比」这种统计量的分母太小 ——
# 3 个月里有 1 个相反就报 33%，读者会当成结构性问题，其实是样本噪声。
# build/single.py 的 `Page.MOM_COST_MIN` 用的是 24（两整年），那是**图注**的门槛
# （要写进正文的话该更保守）；这里是**诊断函数**的门槛，12 就够，
# 够不够由调用方看 `n` 自己判断。（那个门槛 2026-09 之前叫 `ex_ttm` 里的常数，
# 现在是 `Page` 的类属性，改名之后本注释跟着改过。）
MIN_DIAG_MONTHS = 12


class CaliberError(ValueError):
    """口径用错了 —— 比如对存量序列求滚动合计。

    继承 ValueError 而不是 SystemExit：这是「调用方写错了」，应当在开发时被
    traceback 抓住并改掉，不是运行期的数据问题。生成器不该 catch 它。
    """


# ── kind 分类 ───────────────────────────────────────────────────────────────
# 按列名的词根判。这些前缀/词根来自对 series/*.csv 里**每一个列名**的实际清点，
# 不是想当然列的。⚠ **这里不写「共几个列」** —— 那是个活数，而且「怎么数」有三种
# 答案，写死一个必然与别处对不上（上一版写的「全部 514 个数值列」既过期、也没说是
# 哪一种数法）。`python3 build/yoy.py` 第 ⑧ 节当场把三种数法一起印出来：
# 带 `month` 列的表里 month 之外的全部列 / 其中能转出数值的 / 其中有 ≥36 个月历史的。
# classify() 只看列名，所以它面对的是**第一种**（最大的那个）。
# **classify() 只是给个默认建议，不是权威** —— 有疑问时调用方
# 显式传 kind，别让一个正则替你决定要不要把 12 个月末快照加起来。
_STOCK_PAT = re.compile(
    r'(^|_)(oi|auc|aum|mktcap|balances?|outstanding|accounts?|dats|'
    r'client_assets|total_client_assets|assets_eop|eop|cash_balances|'
    r'advisors?|reps?|headcount|collateral|holdings?)(_|$)', re.I)
_RATIO_PAT = re.compile(
    r'(^|_)(rpc|rate|rates|ratio|share|pct|percent|margin|yield|fee|bps|'
    r'per100shares|per_usdmn|takerate)(_|$)', re.I)
_FLOW_PAT = re.compile(
    r'(^|_)(adv|adt|adnv|vol|val|turnover|volume|value|notional|funds|raised|'
    r'nna|flows?|inflows?|outflows?|trades|txn|settle|revenue|fees|'
    r'listings|ipo)(_|$)', re.I)
# 「本月新增的 X」是**流量**，哪怕 X 本身是存量。`new_brokerage_accounts_k`
# （当月新开户数）就是这样一列 —— 名字里有 accounts 但它是月度增量，
# 滚动合计（一年新开了多少户）完全合法。这一条必须**先于** _STOCK_PAT 判，
# 否则 accounts / listings / assets 这些词会把它拽进存量。
_NEW_FLOW_PAT = re.compile(
    r'^new_|(^|_)(opened|added|net_new|gross_new|issued|raised|redeemed)(_|$)', re.I)


def classify(name):
    """按列名猜 kind。**存量优先**：拿不准时宁可判成存量。

    为什么存量优先：判错方向的代价不对称。把流量误判成存量 → 少画一条滚动同比线
    （损失：信息少了一点，图还是对的）；把存量误判成流量 → 把 12 个月末的 OI
    加起来当「一年的量」，画出一条**看着很正常但完全没有意义**的线，而且不报错。

    顺序：比率 → 「本月新增」流量 → 存量 → 流量 → 兜底存量。
    第二档是实测补的：`schw.new_brokerage_accounts_k` 原本被 `accounts` 判成存量，
    但它是当月新开户数，是流量。

    返回 FLOW / STOCK / RATIO 之一。
    """
    n = str(name)
    if _RATIO_PAT.search(n):
        return RATIO
    if _NEW_FLOW_PAT.search(n):
        return FLOW
    if _STOCK_PAT.search(n):
        return STOCK
    if _FLOW_PAT.search(n):
        return FLOW
    return STOCK  # 见 docstring：拿不准判存量


def _as_series(s):
    """统一入口：ndarray / list / Series 都收，缺值一律变 np.nan（None 也是）。"""
    if isinstance(s, pd.Series):
        return pd.to_numeric(s, errors='coerce').astype(float)
    return pd.Series(pd.to_numeric(pd.Series(list(s)), errors='coerce').astype(float))


def _require_flow(kind, what):
    if kind not in KINDS:
        raise CaliberError(f'{what}：kind 必须是 {KINDS} 之一，收到 {kind!r}')
    if kind == STOCK:
        raise CaliberError(
            f'{what}：存量/期末口径序列不许求 {TTM_WIN} 个月滚动**合计**。'
            f'把 12 个月末的 OI / AUM / 市值 / 账户数加起来不是任何东西 —— '
            f'它既不是「一年的量」（存量不累积），也不是「平均水平」（没除以 12）。'
            f'两条出路：①点对点同比 `mom_yoy(s, STOCK)`（存量的默认口径，'
            f'比的是两个时点的存量、不含日历效应，比流量的单月同比稳得多；'
            f'噪声大用轴范围 ycap/yfloor 解决，不要换口径）；'
            f'②要平滑就用 `ttm_mean_yoy(s, STOCK)` —— {TTM_WIN} 个月滚动**均值**的同比，'
            f'那个对存量有意义（去年一年的平均市值 vs 前年一年的平均市值）。')
    if kind == RATIO:
        raise CaliberError(
            f'{what}：比率序列不许求 {TTM_WIN} 个月滚动合计。'
            f'12 个月的 RPC / 费率 / 占比相加没有意义；要「一年的平均费率」得用'
            f'**成交量加权**（Σ收入 ÷ Σ量），那要两条序列，不是这个函数能做的。'
            f'比率的同比走 mom_yoy(kind=RATIO)，出**百分点差**。')


# ── 三个基本口径 ─────────────────────────────────────────────────────────────
def ttm(s, kind):
    """12 个月滚动合计。`kind` 必填，存量 / 比率一律抛 CaliberError。

    s     月度序列（Series / list / ndarray），按月份升序，**缺月要留成 NaN 的空位**，
          不能压缩掉 —— 压缩掉的话「最近 12 个月」会悄悄变成「最近 12 个有数的月」。
    kind  FLOW / STOCK / RATIO，见模块头。必填位置参数，没有默认值。

    `min_periods=TTM_WIN`：窗口不满 12 个月一律出 NaN，不给「前 5 个月的合计」
    这种半截数 —— 半截合计与满窗合计放在同一条线上，前面那段天然偏低，
    看着像「这一年在增长」，其实只是窗口在变长。

    日均序列的量纲问题见模块头：**不要乘回交易日**。
    """
    _require_flow(kind, 'ttm()')
    return _as_series(s).rolling(TTM_WIN, min_periods=TTM_WIN).sum()


def ttm_yoy(s, kind):
    """12 个月滚动合计的同比（**%**，+3.2 表示 +3.2%）。

    ⚠️ **2026-09 起这不再是任何东西的默认口径，页面上也不画它**（CONTRACT §6）。
    它留在这里有两个用途：① `caliber_diff()` 拿它当对照，好让每张图把单月口径的
    代价印进图注（§6.1 第 3 条）；② §6.2 点名保留的那张例外表 —— **两页五张**：
    `exchanges-apac` Ex5 与 Ex15、`exchanges12` Ex4 / 7 / 8，每一张都不是折线。
    除这五张外，**它的返回值不许进 payload 的 `values`**。

    要 24 个月历史才有第一个点（12 个月填窗 + 12 个月比较），所以窗口左端
    没有线是正常的，不是数据缺失。图注要写这一句，否则读者会以为丢数据了。

    基数为 0 或与当期异号 → NaN（不是 0，也不是 ±inf）。滚动合计跨越 12 个月，
    异号只可能发生在净额类流量（NNA 净流出转净流入）上，那种「同比」没有意义。
    """
    r = ttm(s, kind)
    base = r.shift(LAG)
    bad = (base == 0) | (r * base < 0)
    out = (r / base - 1.0) * 100.0
    return out.mask(bad)


def ttm_mean_yoy(s, kind):
    """{TTM_WIN} 个月滚动**均值**的同比（%）—— 存量序列唯一合法的平滑口径。

    为什么单独给一个函数，而不是让存量也调 ttm_yoy：

      **算术上两者完全相同** —— Σ12 / Σ12' ≡ (Σ12/12) / (Σ12'/12)，除数约掉了。
      两条路只差 float64 的舍入：拿 `hkex` 市值实测，最大差是 **1e-14 量级**
      （`python3 build/yoy.py` 第 ② 节当场印出具体那个数；量级不会变，
      因为它是恒等式的浮点残差，不是数据的性质，但**具体几位小数会随序列长而动**，
      所以这里只说量级）。

      既然数一样，为什么还要分？因为**说法不一样，而说法是要印在图上的**。
      「12 个月滚动合计的同比」对存量是一句假话：那个「合计」（12 个月末市值相加）
      不指代任何真实的量，读者按字面去理解会得到一个不存在的东西。
      「12 个月滚动均值的同比」指代的是「去年一整年的平均市值 vs 前年一整年的
      平均市值」—— 一个真实存在、可以核对的量。

      这不是假想的风险：给存量列调本函数的生成器**不止一家**（`grep -n ttm_mean_yoy
      build/*.py` 当场数，别在这里写死一个会变的个数），其中有几家还专门在注释里把
      「说法」这条约束又写了一遍，措辞各不相同 —— 有的写「文案必须写『12 个月均值
      同比』」，有的写「文案绝不能写『合计』」。同一件事要在好几个地方各写对一次，
      函数名分开就少一次抄错的机会。

      ⚠️ 这里**不举页面上的具体例子**。上一版举过一条 hkex 市值图的，上一轮删它时
      又写了一段「已经逐版查证」的理由 —— 那段理由本身两句都是假的：把
      `git log --all -- data/hkex.js` 的每一版都跑过之后，市值图**每一版都是
      Exhibit 8**（不是它说的 Exhibit 7），而被指控的那句模板文案（「最近 12 个月
      合计 ÷ 上一个 12 个月合计 − 1」）**确实在这个文件里出现过**，只是印在成交量
      那几张图的图注上、不在市值图上。例子连同那段理由一起删：页面图号与图注会被
      重排改写，在这里举一次就得跟着维护一辈子，而本函数存在的理由不靠它。

    对 FLOW 也放行（流量的滚动均值同样等于滚动合计的同比，只是流量惯例说「合计」）。
    对 RATIO 仍然拒绝：比率的算术平均没有意义，要平均得用量加权。
    """
    if kind == RATIO:
        raise CaliberError(
            f'ttm_mean_yoy()：比率序列不许求 {TTM_WIN} 个月滚动均值 —— '
            f'RPC / 费率的算术平均没有意义，要「一年的平均费率」得用成交量加权'
            f'（Σ收入 ÷ Σ量），那要两条序列。比率的同比走 mom_yoy(kind=RATIO)。')
    if kind not in KINDS:
        raise CaliberError(f'ttm_mean_yoy()：kind 必须是 {KINDS} 之一，收到 {kind!r}')
    r = _as_series(s).rolling(TTM_WIN, min_periods=TTM_WIN).mean()
    base = r.shift(LAG)
    return ((r / base - 1.0) * 100.0).mask((base == 0) | (r * base < 0))


if ttm_mean_yoy.__doc__:   # python -OO 会把 docstring 抹成 None，别在那儿炸
    ttm_mean_yoy.__doc__ = ttm_mean_yoy.__doc__.replace('{TTM_WIN}', str(TTM_WIN))


def ttm_yoy_unchecked(s):
    """只给**审计工具**用的滚动同比：不检查 kind。生成器不许调用。

    存在的理由只有一个：`tools/check_yoy_caliber.py` 要反推「这张图上画的到底是
    哪种口径」，为此必须对存量序列也算一遍滚动同比 —— 只有算出来才能判断
    「有没有人对存量序列做了滚动合计」（那正是要报错的情形）。
    换句话说这个函数是用来**抓错误**的，不是用来产出的。
    """
    r = _as_series(s).rolling(TTM_WIN, min_periods=TTM_WIN).sum()
    base = r.shift(LAG)
    return ((r / base - 1.0) * 100.0).mask((base == 0) | (r * base < 0))


def mom_yoy(s, kind=FLOW):
    """单月同比。流量/存量出 **%**，比率出 **百分点差（pp）**。

    ⚠️ **2026-09 起这是全站唯一上页面的同比口径**（CONTRACT §6，页面所有者定）：
    流量走 `kind=FLOW`、存量走 `kind=STOCK`（点对点）、比率走 `kind=RATIO`（pp 差），
    三种都从这一个函数出。这段 docstring 上一版写的是「**保留**这个口径，因为确实有
    该用它的地方」并列了四类特许场景，末句是「除此之外用单月同比，得在标题里写明并
    给理由」—— 那是滚动为默认时的框，整个反了，所以重写。

    仍然要在标题里写明「单月 / single-month」（`tools/check_yoy_caliber.py` 的 R4
    只认 title / ylab2 / legend / yoy.name 四处），但那不再是「为偏离默认而辩护」，
    是让读者一眼知道这条线是拿柱子直接除出来的。图注里要印的是**代价**而不是理由
    （§6.1 第 3 条，走 `describe(caliber_diff(...))`）。

    原来那四类场景现在只是「本来就没有第二种口径可选」的几种，记着仍然有用：

      1. 命题本身就是「一个月之内会怎样」。cme Ex3（交易日数如何在一个月内把
         成交量的方向读反）改成滚动口径，图会自己消失 —— 12 个月窗口里交易日效应
         基本自抵：滚动口径下「日均」与「乘回交易日」两条线最大差只有 1pp 出头、
         **逐月符号完全一致**，而单月口径下两者有十几个月符号相反。
         这两组数由 `python3 build/yoy.py` 第 ⑥ 节当场算给你看（别在这里写死，
         它们随 cme 的新月份变）。
      2. 存量序列。OI / AUM / 账户数只有点对点同比，滚动合计非法（见 _require_flow）。
      3. 热力矩阵 / seasonality。逐格波动就是题眼，抹平了就没图了。
      4. m/m 运营监控列（汇总表的 m/m、y/y 两列）—— 那是核对表不是趋势判断。

    kind=RATIO 时返回 a − b（百分点），不是 (a/b−1)：
    RPC 从 0.24 到 0.25 是 **+1bp**，不是「+4.2%」。「百分比的百分比变化」是本仓
    明令禁止的写法（CONTRACT.md §2「比率类指标的差异一律用 pp / bp」）。
    """
    if kind not in KINDS:
        raise CaliberError(f'mom_yoy()：kind 必须是 {KINDS} 之一，收到 {kind!r}')
    v = _as_series(s)
    base = v.shift(LAG)
    if kind == RATIO:
        return v - base
    out = (v / base - 1.0) * 100.0
    return out.mask((base == 0) | (v * base < 0))


# ── 近零基数判据 ────────────────────────────────────────────────────────────
def near_zero_base(s, frac=NEAR_ZERO_BASE_FRAC, share=NEAR_ZERO_SERIES_SHARE, win=None):
    """识别「同比读的不是量在变，而是分母在变」的序列。

    判据：基期 |b| < 本序列 |值| 中位数 × `frac` 的月份记为**近零基数月**；
    这种月份占「有基期的月份」的比例 ≥ `share` → 整条序列建议**别画同比、画水平值**。

    `win` 只切**计数范围**，不切 scale：分母（本序列 |值| 中位数）永远取全历史 ——
    序列的「正常量级」是它自己的历史属性，只拿图窗那一段去估会被最近一段行情带偏。
    但「有几个月不可读」必须只数图上画出来的那些月：一条 2010 年近零、现在早已正常
    的序列，若拿全历史计数就会永远背着这个标签，那是制造噪声。

    ── frac = 0.15 的推导（不是拍的，`python3 build/yoy.py` 第 ⑧ 节会当场重跑）──

    ⚠️ **下面整段是 2026-08-07 的一份快照，不是今天的读数。** 样本量、分桶的 n、
    每一档的百分位数今天全都不一样（那天是 49 个文件 / 514 个 ≥36 个月历史的数值列 /
    65,544 个可比点；今天几个，第 ⑧ 节当场印）。留着它是因为**要看的不是小数点，
    是那条单调且陡峭的曲线，以及「5 倍线」落在哪一档** —— 这个形状经得起重跑，
    而它才是阈值的理由。**引用这段一律连「2026-08-07」一起引**，别把它当现况。

    对当时的全部 ≥36 个月历史的数值列逐月算单月同比，按「基期 ÷ 本序列 |值| 中位数」
    （记 b/med）分桶：

        b/med 区间      n       |yoy| 的 P50    相对正常区        P90
        [0.75,1.00)   20,535        10.0%          0.9x         38.3%
        [0.50,0.75)    7,491        20.2%          1.8x         73.4%
        [0.30,0.50)    2,506        33.3%          2.9x        142.9%
        [0.20,0.30)      812        43.5%          3.8x        266.2%
        [0.15,0.20)      292        56.2%          4.9x        343.1%
        [0.10,0.15)      282        65.6%          5.7x        602.6%   ← 阈值落在这里
        [0.05,0.10)      250       100.0%          8.7x      1,468.8%
        [0.00,0.05)      306       290.2%         25.2x     21,973.4%

    「正常区」= b/med ∈ [0.5, 2.0]，占全部点的 **87.9%**，P50 |yoy| = 11.5%、
    P90 = 43.2%。把「同比读的已经是分母不是量」操作化为「典型读数被撑到正常区的
    **5 倍以上**」，这条线正好落在 0.15 与 0.20 之间（5.7x vs 4.9x）→ 取 **0.15**。

    0.15 **不是这一轮新发明的阈值**：本模块出现之前，页面生成器自己的 `yoy_line`
    里就已经写着同一个近零基数判据（基期 |b| < 全序列绝对值中位数 × 0.15）。
    这一轮做的是把那个仓库里已有的经验常数拿几万个真实点回测一遍，它站得住。
    ⚠️ **别在这里抄别的文件那一行的代码字面量。** 上一版抄了一行、还落了日期戳，
    当天就与工作树对不上 —— 那一行不归本文件管，随时会被改写；这个阈值的权威副本
    只有本模块的 `NEAR_ZERO_BASE_FRAC` 一份，要核以它为准。

    噪声控制（「宁可漏报不要天天喊狼来了」）：frac=0.15 命中的点只占全部的**百分之
    一点几**，而其中**三成以上**的 |yoy| > 300%；正常区里 |yoy| > 300% 的不到 0.5% ——
    **富集几十倍**。放宽到 0.30，命中量翻一倍多、命中率却掉三分之一以上，
    而多召回的极端点远不如多出来的命中量涨得快：多出来的一大半是正常读数，
    等于制造噪声，不划算。
    （这几个比例第 ⑧ 节当场重算并印出来，`frac=0.30` 的对照也在那里一起印。
    ⚠️ 富集倍数尤其敏感：2026-08-07 那份快照是 115 倍，今天已经不是那个数 ——
    所以这里只写量级，要具体数看第 ⑧ 节，别从这段散文里抄。）

    ── share = 1/12 的推导 ─────────────────────────────────────────────────

    对全部「有 ≥24 个可比月」的序列算「近零基数月占比」，这个分布**极度偏斜**：
    中位数与 P75 都是 **0.00%**（大多数序列一个近零月都没有），只有尾巴上那一小撮
    沾到过。取 1/12 = 8.33% 作阈值，语义是「平均每年至少有一个月的同比读数是分母
    造成的 —— 那条线在图上就不是一条可读的线」，它落在这条经验分布的**九十几分位**，
    命中的是**个位数百分比**的序列。

    ⚠️ **这里不写分位数的具体值、命中几条、也不写命中的是哪几条列。** 那批数
    2026-08-07 记过一版（507 条序列、≈P96、命中 21 条 = 4.1%，并逐条点名了
    db1 EURIBOR、enx 单一股票期货 OI 等等），今天条数、分位、每条的占比**全都变了**，
    连点名的那几条本身的占比也动了。`python3 build/yoy.py` 第 ⑧ 节当场重算这条分布，
    并把**今天占比最高的那十几条逐条列出来**（文件名 + 列名 + 占比）——
    要判断「命中的是不是该命中的那几条」，看那张现算的表，不要看这段散文。

    唯一在这里点名的对照是 `schw` Core NNA：它的占比远低于阈值 → **不命中，
    这是对的**。它的问题是口径（毛刺来自单月口径本身），不是「这条序列根本不能画
    同比」，两类问题不该用同一个判据报。它今天的占比与 flag 由第 ④ 节当场印。

    返回 dict：
      months        近零基数月的月份标签列表（Series 的 index）
      n_base        有基期的月份数（分母）
      share         近零基数月占比
      flag          share >= `share` 参数 → True，建议画水平值而不是同比
      scale         本序列 |值| 的中位数
      cut           判定阈值 = scale × frac
      worst         (月份, 基期值, 该月单月同比%) —— 最极端的那一个，写图注用
    """
    v = _as_series(s)
    fin = v[np.isfinite(v)]
    scale = float(np.median(np.abs(fin))) if len(fin) else float('nan')   # ← 全历史
    cut = scale * frac
    base = v.shift(LAG)
    has_base = np.isfinite(v) & np.isfinite(base) & _winmask(v.index, win)  # ← 只数窗内
    hit = has_base & (base.abs() < cut)
    n_base = int(has_base.sum())
    y = mom_yoy(v)
    worst = None
    if int(hit.sum()):
        # 「最极端」= |同比| 最大的那个近零月；同比算不出来时退回基期最小的那个
        cand = y.where(hit)
        k = cand.abs().idxmax() if np.isfinite(cand.values.astype(float)).any() \
            else base.where(hit).abs().idxmin()
        worst = (k, float(base[k]), float(y[k]))
    return {
        'months': list(v.index[hit]),
        'n_base': n_base,
        'share': (float(hit.sum()) / n_base) if n_base else float('nan'),
        'flag': bool(n_base and hit.sum() / n_base >= share),
        'scale': scale,
        'cut': cut,
        'worst': worst,
    }


# ── 口径对比诊断 ────────────────────────────────────────────────────────────
def caliber_diff(s, kind=FLOW, win=None):
    """两种同比口径的对比诊断 —— 「这张图该用哪个口径」的证据。

    **样本必须对齐**，这是整个函数最要紧的一行：滚动同比比单月同比少 12 个月历史
    （滚动合计要填 12 个月的窗，同比再要 12 个月），不对齐就把「样本不同」的效应
    混进标准差里读成「口径不同」。所以先取**两种口径都有值的月份的交集**，
    此后所有统计量都只在这个交集上算；审计那批可比「序列 × 月」也是这么来的
    （具体条数与它的复算见 CONTRACT §6.5，那里连窗口一起记着）。

    实测这一步不是学究气：`schw` Core NNA 在**全历史**上不对齐与对齐后的 std 比
    明显不同，差的那一截全是「滚动那一侧少了十来个月历史」造成的样本效应，
    不是口径效应。⚠️ **这一对数不写死在这里**：它随 `series/schw.csv` 回填而变 ——
    上一版写的「4.48x / 4.77x、差 0.3 倍」正是回填前的读数，CONTRACT §6.4 已经
    查明并留痕。今天的值由 `python3 build/yoy.py` 第 ⑤ 节当场印。
    ⚠️ 而且**这个例子只在长窗口上看得见**：改用末 25 个月去量，两种口径每个月都有值，
    对齐前后一模一样（第 ⑤ 节把两个窗口并排印出来，正是为了让这一点看得见）。

    相邻月跳变同样只量「相邻两个月**都在交集里**」的那些对 —— np.diff 碰到 NaN
    自然出 NaN，nanmax 会跳过，所以不需要额外处理，但要知道这是有意的：
    跨过一个空洞的「跳变」不是跳变，是两段序列接在一起。

    win   限定统计范围。None = 全历史；int = 最后 N 个月；可迭代 = 指定的月份标签。
          **要和审计对齐就得给 win** —— 审计量的是「图上画出来的那一段」（长度由
          build/single.py 的 WIN_FROM 决定，不是固定期数），
          图外的历史读者根本看不到。全历史算出来的「符号相反的序列占比」会逼近
          100%（任何一条几十年的序列总能找到一个相反的月），那个数没有信息量。
          同比本身**永远在全历史上算完再切窗**（切完再算的话窗口最前 12 期永远空），
          这个参数只切统计范围。

    返回 dict（kind=STOCK 时 ttm 侧全部为 None，只回 mom 侧的统计 + reason）：
      n              对齐后的月份数
      months         对齐后的月份标签
      std_mom/std_ttm            两种口径的逐月标准差（pp）
      std_ratio                  std_mom / std_ttm。审计管它叫「放大倍数」，但审计记的
                                 那个 2.08 **在审计自己的分母上复算不出来**
                                 （§6.5 逐档留痕），别拿本字段的输出去对那个数
      maxjump_mom/maxjump_ttm    相邻月**最大**跳变 (pp, 前一月, 后一月)。
                                 ⚠️ §6.5 查明审计通篇写的「跳变」指的是**这一个**
      medjump_mom/medjump_ttm    相邻月跳变**中位数**（pp）。⚠️ 它**不是**审计那个
                                 「30pp vs 4.8pp」—— 那两个数按 medjump 复算只有个位数
                                 pp，读成 maxjump 才落得回去（§6.5）。两个字段并存就是
                                 为了别再把这两个统计量混成一个
      opposite                   符号相反的月份 [(月份, 单月%, 滚动%)]
      opposite_n / opposite_share
      amplified_n / amplified_share   |单月| ≥ AMPLIFY_X × |滚动| 的月份数与占比
      worst_gap                  两者差最远的月份 (月份, 单月%, 滚动%)
      near_zero                  near_zero_base() 的结果，原样带出
      verdict                    'ttm' / 'mom' / 'level' —— 建议口径，见 recommend()
      reason                     一句话理由（中文，可直接进图注）
    """
    v = _as_series(s)
    nz = near_zero_base(v, win=win)
    a = mom_yoy(v, kind)
    inwin = _winmask(v.index, win)
    a = a.where(inwin)

    if kind != FLOW:
        # 存量 / 比率没有合法的滚动口径，不比，直接给结论。
        why = ('存量/期末口径' if kind == STOCK else '比率口径')
        return {
            'kind': kind, 'n': int(np.isfinite(a).sum()), 'months': list(v.index[np.isfinite(a)]),
            'std_mom': _std(a), 'std_ttm': None, 'std_ratio': None,
            'maxjump_mom': _maxjump(a, v.index), 'maxjump_ttm': None,
            'medjump_mom': _medjump(a), 'medjump_ttm': None,
            'opposite': [], 'opposite_n': 0, 'opposite_share': float('nan'),
            'amplified_n': 0, 'amplified_share': float('nan'),
            'worst_gap': None, 'near_zero': nz,
            'verdict': 'level' if nz['flag'] else 'mom',
            'reason': (f'{why}，滚动合计非法，点对点同比是唯一合法口径；'
                       + ('但近零基数月占 {:.0%}，建议改画水平值。'.format(nz['share'])
                          if nz['flag'] else '噪声大请用轴范围（ycap/yfloor）解决，不要换口径。')),
        }

    b = ttm_yoy(v, kind).where(inwin)
    av, bv = a.values.astype(float), b.values.astype(float)
    m = np.isfinite(av) & np.isfinite(bv)          # ← 对齐：交集，一次做完
    idx = list(v.index)
    aa = np.where(m, av, np.nan)
    bb = np.where(m, bv, np.nan)

    opp = [(idx[i], float(aa[i]), float(bb[i]))
           for i in np.flatnonzero(m & (av * bv < 0))]
    amp = int(np.nansum(np.abs(aa) >= AMPLIFY_X * np.abs(bb)))
    n = int(m.sum())
    gap = np.abs(aa - bb)
    kg = int(np.nanargmax(gap)) if n and np.isfinite(gap).any() else None

    d = {
        'kind': kind, 'n': n, 'months': [idx[i] for i in np.flatnonzero(m)],
        'std_mom': _std(aa), 'std_ttm': _std(bb),
        'std_ratio': (_std(aa) / _std(bb)) if _std(bb) else float('nan'),
        'maxjump_mom': _maxjump(aa, idx), 'maxjump_ttm': _maxjump(bb, idx),
        'medjump_mom': _medjump(aa), 'medjump_ttm': _medjump(bb),
        'opposite': opp, 'opposite_n': len(opp),
        'opposite_share': (len(opp) / n) if n else float('nan'),
        'amplified_n': amp, 'amplified_share': (amp / n) if n else float('nan'),
        'worst_gap': (idx[kg], float(aa[kg]), float(bb[kg])) if kg is not None else None,
        'near_zero': nz,
    }
    d['verdict'], d['reason'] = _verdict(d)
    return d


def _winmask(index, win):
    """win → 布尔 mask。None 全 True；int 取最后 N 个；可迭代按标签取。"""
    if win is None:
        return pd.Series(True, index=index)
    if isinstance(win, int):
        m = pd.Series(False, index=index)
        if win > 0:
            m.iloc[-win:] = True
        return m
    return pd.Series([k in set(win) for k in index], index=index)


def _std(x):
    x = np.asarray(x, float)
    return float(np.nanstd(x, ddof=1)) if np.isfinite(x).sum() >= 2 else float('nan')


def _medjump(x):
    dx = np.abs(np.diff(np.asarray(x, float)))
    return float(np.nanmedian(dx)) if np.isfinite(dx).any() else float('nan')


def _maxjump(x, idx):
    dx = np.abs(np.diff(np.asarray(x, float)))
    if not np.isfinite(dx).any():
        return None
    i = int(np.nanargmax(dx))
    return (float(dx[i]), idx[i], idx[i + 1])


def _verdict(d):
    """由 caliber_diff 的统计量给出建议口径。两档，按严重程度短路。

    ⚠️ **2026-09 契约改了默认口径**（CONTRACT §6：全站单月，页面所有者指定），
    所以这个函数原来那三档里的两档 —— 「按契约默认用 12 个月滚动同比」——
    整个作废，一律回 'mom'。它现在只剩一个还有判断力的分支：近零基数。

    门槛为什么是这几个数：
      · 近零基数 → 'level'。最优先，而且在单月口径下**比从前更要紧**：滚动合计
        原本还能把 `db1` EURIBOR OI 那种极端跳变压掉一个数量级（§6.5 逐位复算过
        那条：单月侧 40,608.58pp，2024-10 → 2024-11，三个窗口里都是窗内最大；
        第 ④ 节把两种口径的最大跳变并排印出来，看得到「压下来之后仍然是四位数 pp」），
        压完剩下的仍然是「分母的故事」，所以当时也判 level。现在连那层缓冲都没有了。
      · 其余一律 'mom'。这是**契约的默认**，不是这个函数逐条投票投出来的 ——
        统计量在这里的用途是让调用方把**代价**印进图注（§6.1 第 3 条），
        不是让它按数据自动换口径。
        n < MIN_DIAG_MONTHS 时同样回 'mom'，只是 reason 里注明证据不足 ——
        「量不出差异」本身也是一句该印给读者看的话（这条线的可比月很少）。
    """
    nz = d['near_zero']
    if nz['flag']:
        return 'level', (f'近零基数月占 {nz["share"]:.0%}（基期 < 本序列中位数 × '
                         f'{NEAR_ZERO_BASE_FRAC}），同比读的是分母不是量，建议画水平值。')
    if d['n'] < MIN_DIAG_MONTHS:
        return 'mom', (f'与 {TTM_WIN} 个月滚动口径都有值的月份只有 {d["n"]} 个'
                       f'（< {MIN_DIAG_MONTHS}），差异量不出来；本图按契约用单月同比，'
                       f'但这条线的可比月很少，斜率不要外推。')
    return 'mom', describe(d)


def describe(d):
    """把 caliber_diff 的结果写成一段可直接进图注的中文。

    存在的理由：CONTRACT §6.1 第 3 条要求**每一张画<u>流量</u>同比的图**都印出单月
    口径的代价，而且要「用本序列自己实测」（存量与比率不在第 3 条的范围里 ——
    `caliber_diff()` 对它们根本不比，本函数直接把 `reason` 原样回出去）。
    那段文案原本写死在一个生成器里，别的生成器要么抄要么没有。放这儿，
    import 它的生成器共用一份措辞 —— 具体几个，`grep -rln '^import yoy' build/*.py`
    与 `grep -rln 'describe(' build/*.py` 当场数，别在这里写死一个会变的个数。

    ⚠️ **本函数的返回值直接进页面图注**（`data/*.js` 里搜「口径差异用本序列自己实测」
    就是它）。改这里的措辞等于改一批已发布页面的文案，不是纯注释改动 —— 改之前先
    确认这是不是你要做的事，并把受影响的页重跑一遍。

    ⚠️ 末句 2026-09 改过：原来是「所以本图用滚动口径」，那是上一版契约（滚动为默认）
    的收尾。现在页上一条滚动线都不画，那句话会指着一个不存在的东西，所以换成
    「这条线要连着柱高一起读」—— 同样一句从这批数字里推得出来的结论，但它说的是
    **怎么读这张图**，不是替另一种口径背书。
    """
    if d['kind'] != FLOW:
        return d['reason']
    if not d['n']:
        return '窗口内没有任何一对两种口径都有值的月份，无法比较。'
    parts = [f'<b>口径差异用本序列自己实测</b>（{d["n"]} 个两种同比都有值的月份）：'
             f'单月同比逐月标准差 {d["std_mom"]:.1f}pp，'
             f'{TTM_WIN} 个月滚动同比 {d["std_ttm"]:.1f}pp（放大 {d["std_ratio"]:.1f} 倍）；'
             f'相邻月跳变中位 {d["medjump_mom"]:.1f}pp vs {d["medjump_ttm"]:.1f}pp。']
    if d['maxjump_mom']:
        j = d['maxjump_mom']
        parts.append(f'单月口径相邻月最大跳变 {j[0]:.0f}pp（{j[1]} → {j[2]}）'
                     + (f'，滚动口径同期最大 {d["maxjump_ttm"][0]:.0f}pp。'
                        if d['maxjump_ttm'] else '。'))
    if d['opposite_n']:
        parts.append(f'两者<b>符号相反</b>的月份有 {d["opposite_n"]} 个'
                     f'（占 {d["opposite_share"]:.0%}）。')
    if d['worst_gap']:
        g = d['worst_gap']
        parts.append(f'差得最远的是 {g[0]}：单月 {g[1]:+.1f}% 而滚动 {g[2]:+.1f}%。')
    parts.append('⇒ <b>这条线要连着柱高一起读</b>：低基数月份它会被放大，'
                 '单看它挑月份能把结论说成两个方向。'
                 f'（对照的 {TTM_WIN} 个月滚动口径<b>只在这段文字里以数字出现</b>，'
                 '页上一条线都不画 —— 全站单月，见 CONTRACT §6。）')
    return ''.join(parts)


def recommend(s, kind=None, name=None, win=None):
    """一站式：给一条序列和它的列名，回「该画什么」。

    kind 不给就用 classify(name) 猜；**猜出来的 kind 会原样回在结果里**，
    调用方有责任看一眼对不对（见 classify 的 docstring：猜错的代价不对称）。
    `win` 应当填这张图实际画出来的窗口 —— 生成器里就是 `build/single.py` 的
    `Page.win_long()`（左端 = `max(序列首月, WIN_FROM)`）。
    ⚠️ 上一版这里写的是 `self.win(end, WIN_LONG)`，那个写法连同 `WIN_LONG = 25`
    这个常量在 2026-08-18 就一起没了。诊断要和读者看到的东西同范围，
    否则报的是图外的问题。

    返回 caliber_diff 的 dict，外加 'name' / 'kind_guessed'。
    """
    guessed = kind is None
    kind = kind if kind is not None else classify(name)
    d = caliber_diff(s, kind, win=win)
    d['name'] = name
    d['kind_guessed'] = guessed
    return d


# ── 自测：用真实序列演示每个函数，并重跑全部阈值推导 ───────────────────────────
def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(csv):
    df = pd.read_csv(os.path.join(_repo_root(), 'series', csv))
    return df.set_index('month').sort_index()


def _recalibrate():
    """当场重跑 NEAR_ZERO_BASE_FRAC / NEAR_ZERO_SERIES_SHARE 的推导。

    阈值可以写死，推导不能丢 —— 数据长出两年之后跑一遍就知道它还站不站得住。
    """
    pts, per = [], []
    ncol_all = ncol_num = ncol = nfile_month = 0
    for f in sorted(glob.glob(os.path.join(_repo_root(), 'series', '*.csv'))):
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if 'month' not in df.columns:
            continue
        nfile_month += 1
        df = df.set_index('month').sort_index()
        ncol_all += len(df.columns)
        for c in df.columns:
            v = pd.to_numeric(df[c], errors='coerce').values.astype(float)
            fin = np.isfinite(v)
            if fin.sum():
                ncol_num += 1
            if fin.sum() < 36:
                continue
            ncol += 1
            med = float(np.median(np.abs(v[fin]))) or 1.0
            hits = tot = 0
            for i in range(LAG, len(v)):
                a, b = v[i], v[i - LAG]
                if not (np.isfinite(a) and np.isfinite(b)) or b == 0:
                    continue
                pts.append((abs(b) / med, abs(a / b - 1) * 100))
                tot += 1
                hits += abs(b) / med < NEAR_ZERO_BASE_FRAC
            if tot >= 24:
                per.append((hits / tot, os.path.basename(f)[:-4], c))
    p = np.array(pts)
    norm = p[(p[:, 0] >= 0.5) & (p[:, 0] <= 2.0), 1]
    hit = p[p[:, 0] < NEAR_ZERO_BASE_FRAC, 1]
    named = sorted(per, reverse=True)
    per = np.array([x[0] for x in per])
    print(f'  样本：{len(p):,} 个可比点 / '
          f'{len(glob.glob(os.path.join(_repo_root(), "series", "*.csv")))} 个 series 文件，'
          f'其中 {nfile_month} 个带 month 列')
    # 「几个列」有三种数法，一起印 —— classify() 只看列名，它面对的是第一个数。
    print(f'  列数三种数法：month 之外的全部列 {ncol_all} / 能转出数值的 {ncol_num} / '
          f'有 ≥36 个月历史的 {ncol}（下面的推导只用最后这一种）')
    print(f'  正常区 b/med∈[0.5,2]：占 {len(norm) / len(p):.1%}，'
          f'|yoy| P50={np.percentile(norm, 50):.1f}%  P90={np.percentile(norm, 90):.1f}%')
    print('  分桶（非累积）—— 阈值取在 P50 越过正常区 5 倍的那一档：')
    edges = [0, .05, .10, .15, .20, .30, .50, .75, 1.0]
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p[:, 0] >= lo) & (p[:, 0] < hi)
        if m.sum() < 30:
            continue
        x = p[m, 1]
        mark = '  ← 阈值' if abs(hi - NEAR_ZERO_BASE_FRAC) < 1e-9 else ''
        print(f'    b/med [{lo:.2f},{hi:.2f})  n={int(m.sum()):6d}  '
              f'P50={np.percentile(x, 50):7.1f}% ({np.percentile(x, 50) / np.percentile(norm, 50):5.1f}x)'
              f'  P90={np.percentile(x, 90):9.1f}%{mark}')
    for fr in (NEAR_ZERO_BASE_FRAC, 0.30):
        h = p[p[:, 0] < fr, 1]
        tag = '  ← 在用' if fr == NEAR_ZERO_BASE_FRAC else '  ← 放宽到这里的对照'
        print(f'  frac={fr}：命中 {len(h):,} 点（占 {len(h) / len(p):.2%}），'
              f'其中 |yoy|>300% 占 {(h > 300).mean():.1%}（{int((h > 300).sum())} 个）；'
              f'正常区仅 {(norm > 300).mean():.2%}'
              f'（富集 {(h > 300).mean() / max((norm > 300).mean(), 1e-9):.0f} 倍）{tag}')
    h30 = p[p[:, 0] < 0.30, 1]
    print(f'    → 0.15 放宽到 0.30：命中量 ×{len(h30) / max(len(hit), 1):.2f}，'
          f'命中率 {(hit > 300).mean():.1%} → {(h30 > 300).mean():.1%}，'
          f'极端点只多召回 {int((h30 > 300).sum() - (hit > 300).sum())} 个 '
          f'（+{((h30 > 300).sum() - (hit > 300).sum()) / max((hit > 300).sum(), 1):.0%}）'
          ' —— 多出来的一大半是正常读数，不划算')
    print(f'  序列级近零月占比分布（{len(per)} 条 ≥24 个可比月的序列）：'
          f'P50={np.percentile(per, 50):.2%}  P90={np.percentile(per, 90):.2%}  '
          f'P95={np.percentile(per, 95):.2%}')
    nhit = int((per >= NEAR_ZERO_SERIES_SHARE).sum())
    print(f'  share={NEAR_ZERO_SERIES_SHARE:.4f}（≈P{(per < NEAR_ZERO_SERIES_SHARE).mean() * 100:.0f}）：'
          f'命中 {nhit} / {len(per)} = {(per >= NEAR_ZERO_SERIES_SHARE).mean():.1%} 的序列')
    # 命中的是不是「该命中的那几条」，看这张现算的表 —— near_zero_base() 的
    # docstring 从前在散文里点名了七八条列并写死了各自的占比，早已全部过期。
    print(f'  今天占比最高的 {min(nhit, 14)} 条（文件.列名 —— 判断「命中的是不是该命中的」看这里）：')
    for sh, fn, cn in named[:min(nhit, 14)]:
        print(f'    {sh:7.1%}  {fn}.{cn}')


def _selftest():
    print('=' * 78)
    print('build/yoy.py 自测 —— 全部用 series/*.csv 的真实序列')
    print('=' * 78)

    # ① 流量：cme 总 ADV。ttm / ttm_yoy / mom_yoy / caliber_diff 全跑一遍
    cme = _load('cme.csv')
    adv = cme['adv_total_kcontracts']
    print('\n① 流量序列 cme.adv_total_kcontracts（日均，千张）')
    print(f'   classify → {classify("adv_total_kcontracts")}')
    r = ttm(adv, FLOW)
    print(f'   ttm() 末 3 期：{r.tail(3).round(0).to_dict()}')
    print(f'      前 {TTM_WIN - 1} 期为 NaN（窗口不满不给半截合计）：'
          f'{bool(r.head(TTM_WIN - 1).isna().all())}')
    print(f'   ttm_yoy() 末 3 期（%）：{ttm_yoy(adv, FLOW).tail(3).round(2).to_dict()}')
    print(f'   mom_yoy() 末 3 期（%）：{mom_yoy(adv, FLOW).tail(3).round(2).to_dict()}')
    d = caliber_diff(adv, FLOW)
    print(f'   caliber_diff：n={d["n"]}  std 单月 {d["std_mom"]:.1f}pp vs 滚动 '
          f'{d["std_ttm"]:.1f}pp（放大 {d["std_ratio"]:.2f}x）')
    print(f'      相邻月跳变中位 {d["medjump_mom"]:.1f}pp vs {d["medjump_ttm"]:.1f}pp；'
          f'最大 {d["maxjump_mom"][0]:.0f}pp（{d["maxjump_mom"][1]}→{d["maxjump_mom"][2]}）'
          f' vs {d["maxjump_ttm"][0]:.0f}pp')
    print(f'      符号相反 {d["opposite_n"]} 个月（{d["opposite_share"]:.0%}），'
          f'前 3 个：{d["opposite"][:3]}')
    print(f'      verdict={d["verdict"]}')

    # ② 存量：拒绝滚动合计
    print('\n② 存量序列 cme.oi_total_contracts（月末 OI）—— 必须拒绝滚动合计')
    oi = cme['oi_total_contracts']
    print(f'   classify → {classify("oi_total_contracts")}')
    try:
        ttm(oi, STOCK)
        print('   !!! 没抛异常，判据坏了')
    except CaliberError as e:
        print(f'   ttm(oi, STOCK) → CaliberError：{str(e)[:96]}…')
    print(f'   mom_yoy(oi, STOCK) 末 3 期（%）：{mom_yoy(oi, STOCK).tail(3).round(2).to_dict()}')
    print(f'   caliber_diff(oi, STOCK).verdict = {caliber_diff(oi, STOCK)["verdict"]}'
          f' ／ {caliber_diff(oi, STOCK)["reason"][:60]}…')
    # 存量的平滑口径：ttm_mean_yoy。它与「滚动合计的同比」在算术上是同一个数，
    # 差的只有 float64 舍入 —— 这一行把那个残差量出来，省得有人以为两者真有差别。
    mc = _load('hkex.csv')['mktcap_hkdtn']
    _resid = np.abs((ttm_yoy_unchecked(mc) - ttm_mean_yoy(mc, STOCK)).values.astype(float))
    print(f'   ttm_mean_yoy vs ttm_yoy（hkex.mktcap_hkdtn，{int(np.isfinite(_resid).sum())} 个可比月）：'
          f'最大差 {np.nanmax(_resid):.3e}pp —— 恒等式的浮点残差，'
          f'两者数值相同、**说法不同**（存量说「合计」是假话）')

    # ③ 比率：出 pp 不出 %
    print('\n③ 比率序列 cboe.rpc_us_options_usd —— 同比出百分点差')
    rpc = _load('cboe.csv')['rpc_us_options_usd']
    print(f'   classify → {classify("rpc_us_options_usd")}')
    print(f'   mom_yoy(kind=RATIO) 末 3 期（pp）：{mom_yoy(rpc, RATIO).tail(3).round(4).to_dict()}')
    print(f'   mom_yoy(kind=FLOW)  末 3 期（%）：{mom_yoy(rpc, FLOW).tail(3).round(2).to_dict()}'
          '  ← 同一条序列，口径不同读数完全不同')
    try:
        ttm(rpc, RATIO)
    except CaliberError as e:
        print(f'   ttm(rpc, RATIO) → CaliberError：{str(e)[:80]}…')

    # ④ 近零基数：db1 EURIBOR（审计里跳 40,609pp 那条）
    print('\n④ 近零基数 db1.adv_euribor3m_contracts / oi_euribor3m_contracts')
    db1 = _load('db1.csv')
    for c in ('adv_euribor3m_contracts', 'oi_euribor3m_contracts'):
        for w, tag in ((None, '全历史'), (WIN_LONG_DEMO, f'末 {WIN_LONG_DEMO} 个月')):
            nz = near_zero_base(db1[c], win=w)
            line = (f'   {c} [{tag}]: 近零月 {len(nz["months"])}/{nz["n_base"]} = '
                    f'{nz["share"]:.1%}  flag={nz["flag"]}')
            if w is None:
                line += f'  scale={nz["scale"]:,.0f} cut={nz["cut"]:,.0f}'
            print(line)
            if nz['worst'] and w is None:
                print(f'      最极端：{nz["worst"][0]} 基期 {nz["worst"][1]:,.4g} → '
                      f'单月同比 {nz["worst"][2]:+,.0f}%')
    print(f'   → recommend(..., win={WIN_LONG_DEMO}).verdict = '
          f'{recommend(db1["oi_euribor3m_contracts"], name="oi_euribor3m_contracts", win=WIN_LONG_DEMO)["verdict"]}')
    # 「滚动合计能把这种极端跳变压掉一个数量级、但压完还是分母的故事」——
    # _verdict() 的 docstring 引的就是这一对数，在这里现算，别写死在那边。
    _de = caliber_diff(db1['oi_euribor3m_contracts'], FLOW)
    print(f'   同一条列的相邻月最大跳变（全历史）：单月 {_de["maxjump_mom"][0]:,.0f}pp'
          f'（{_de["maxjump_mom"][1]}→{_de["maxjump_mom"][2]}）'
          f' vs 滚动 {_de["maxjump_ttm"][0]:,.0f}pp —— 滚动压掉一个数量级，'
          f'剩下的仍然是分母的故事，所以两种口径下都判 level')
    nnz = near_zero_base(_load('schw.csv')['core_nna_usdbn'])
    print(f'   对照 schw.core_nna_usdbn（全历史）：近零月占 {nnz["share"]:.1%} → '
          f'flag={nnz["flag"]}（对的：它的问题是单月口径的毛刺，不是分母）')

    # ⑤ 样本对齐：不对齐会把样本效应读成口径效应。
    #    两个窗口并排跑 —— 这个例子只在长窗口上看得见（CONTRACT §6.4）。
    print('\n⑤ 样本对齐的效果（schw.core_nna_usdbn，审计里最极端的那条）')
    nna = _load('schw.csv')['core_nna_usdbn']
    for w, tag in ((None, '全历史'), (WIN_LONG_DEMO, f'末 {WIN_LONG_DEMO} 个月')):
        inw = _winmask(nna.index, w)
        a, b = mom_yoy(nna, FLOW).where(inw), ttm_yoy(nna, FLOW).where(inw)
        d = caliber_diff(nna, FLOW, win=w)
        print(f'   [{tag}] 不对齐：单月 n={int(np.isfinite(a).sum())} std={_std(a):.1f}pp，'
              f'滚动 n={int(np.isfinite(b).sum())} std={_std(b):.1f}pp → 比 {_std(a) / _std(b):.2f}x')
        print(f'   [{tag}] 对齐后：n={d["n"]}，std {d["std_mom"]:.1f}pp vs {d["std_ttm"]:.1f}pp'
              f' → 比 {d["std_ratio"]:.2f}x'
              + ('   ← 这个才是口径效应' if w is None else
                 '   ← 两种口径月月都有值，对齐前后一模一样：这个例子在短窗口上是看不见的'))
    d = caliber_diff(nna, FLOW)
    if d['opposite']:
        w = max(d['opposite'], key=lambda t: abs(t[1]))
        print(f'   符号相反最极端：{w[0]} 单月 {w[1]:+.0f}% vs 滚动 {w[2]:+.0f}%')

    # ⑥ 日均序列：不要乘回交易日 —— 实测证明比值里交易日约掉了
    print('\n⑥ 日均序列不要乘回交易日（cme 有 trading_days，可以实测）')
    tot = adv * cme['trading_days']            # 乘回交易日 = 月度总量
    y_adv, y_tot = ttm_yoy(adv, FLOW), ttm_yoy(tot, FLOW)
    m = np.isfinite(y_adv) & np.isfinite(y_tot)
    _sd = int((np.sign(y_adv[m].values) != np.sign(y_tot[m].values)).sum())
    print(f'   滚动同比：日均口径 vs 乘回交易日口径，{int(m.sum())} 个可比月最大差 '
          f'{np.nanmax(np.abs((y_adv - y_tot)[m])):.2f}pp，符号相反 {_sd} 个月'
          '  ← 12 个月窗口里交易日效应自抵，乘回去只多引进一条序列的误差')
    ya, yt = mom_yoy(adv, FLOW), mom_yoy(tot, FLOW)
    m2 = np.isfinite(ya) & np.isfinite(yt)
    _sd2 = int((np.sign(ya[m2].values) != np.sign(yt[m2].values)).sum())
    print(f'   单月同比：同样两个口径 {int(m2.sum())} 个可比月最大差 '
          f'{np.nanmax(np.abs((ya - yt)[m2])):.1f}pp，符号相反 {_sd2} 个月'
          '  ← 单月口径下交易日差异是主要噪声源（cme Ex3 整张图讲的就是这件事）')
    # 交易日列的清点。数法写在这里，免得和模块头对不上：
    #   文件数   = series/*.csv 的个数
    #   月度序列表 = 表头里有一列叫 month（cost.csv 按 ym 记月，因此不进这个计数）
    #   带交易日列 = 表头里有列名含 trading_days
    files = sorted(glob.glob(os.path.join(_repo_root(), 'series', '*.csv')))
    heads = [open(f, encoding='utf-8').readline().strip().split(',') for f in files]
    dayfiles = [(os.path.basename(f)[:-4], [c for c in h if 'trading_days' in c])
                for f, h in zip(files, heads) if any('trading_days' in c for c in h)]
    nmon = sum(1 for h in heads if 'month' in h)
    print(f'   清点：{len(files)} 个 series/*.csv，其中 {nmon} 个带 month 列，'
          f'只有 {len(dayfiles)} 个带交易日列，且口径各不相同 —— 跨家加权做不到：')
    for nm, cols in dayfiles:
        print(f'      {nm:22s} {len(cols)} 列  {", ".join(cols)}')

    # ⑦ 全仓复算：审计的几个总量数字，用本文件的实现在**同一个窗口口径**下重跑
    print(f'\n⑦ 全仓复算（所有流量列，统计范围 = 审计当年那段窗口的末 {WIN_LONG_DEMO} 个月）')
    print('   ⚠️ 这**不是**今天的图窗：全站时序图 2026-08-18 起左端钉在 '
          'single.WIN_FROM = 2016-01，长度随月份增长。')
    print('   这里仍用 25 个月，只是为了和 CONTRACT §6.5 里标着「近 25 个月」的那一组同范围。')
    rows = {}
    for w in (WIN_LONG_DEMO, None):
        ratios, opps, jm, jt, xm, xt = [], [], [], [], [], []
        for f, h in zip(files, heads):
            if 'month' not in h:
                continue
            df = pd.read_csv(f).set_index('month').sort_index()
            for c in df.columns:
                if classify(c) != FLOW:
                    continue
                s = pd.to_numeric(df[c], errors='coerce')
                if np.isfinite(s.values.astype(float)).sum() < 36:
                    continue
                d = caliber_diff(s, FLOW, win=w)
                if d['n'] < MIN_DIAG_MONTHS or not np.isfinite(d['std_ratio']):
                    continue
                ratios.append(d['std_ratio'])
                opps.append(d['opposite_n'] > 0)
                jm.append(d['medjump_mom'])
                jt.append(d['medjump_ttm'])
                if d['maxjump_mom'] and d['maxjump_ttm']:
                    xm.append(d['maxjump_mom'][0])
                    xt.append(d['maxjump_ttm'][0])
        rows[w] = (len(ratios), np.median(ratios), np.mean(opps),
                   np.median(jm), np.median(jt), np.median(xm), np.median(xt))
    n, r, o, a, b, xa, xb = rows[WIN_LONG_DEMO]
    print(f'   {n} 条流量序列：std 放大倍数中位 {r:.2f}x')
    print(f'   至少一个月符号相反的序列占 {o:.0%}')
    print(f'   相邻月跳变**中位**（medjump）：单月 {a:.1f}pp vs 滚动 {b:.1f}pp（比 {a / b:.1f}x）')
    print(f'   逐序列**最大**跳变的中位（maxjump）：单月 {xa:.1f}pp vs 滚动 {xb:.1f}pp'
          f'（比 {xa / xb:.1f}x）')
    n2, r2, o2, a2, b2, xa2, xb2 = rows[None]
    print(f'   对照 —— 不切窗（全历史）：{n2} 条，放大 {r2:.2f}x，'
          f'符号相反的序列占 {o2:.0%}，medjump {a2:.1f}/{b2:.1f}pp，maxjump {xa2:.1f}/{xb2:.1f}pp')
    print('   → 「符号相反的序列占比」对窗口极敏感：几十年的序列总能找到一个相反的月，'
          '不切窗这个数会逼近 100% 而失去信息量。')
    print('     所以这类统计量离开窗口标注就没有意义 —— 这正是 §6.5 那节反复在说的事。')
    print('   注一：上面每个数都是**当场算的**，会随 series/ 长而变 —— 不要抄进散文里。')
    print('   注二：本节的宇宙是「series/*.csv 全部流量列」，审计的是「223 张图上画的')
    print('         225 条序列」，两者不是同一批：审计那批混着存量与比率（它们不进')
    print('         「符号相反」这一项的分母），本节只取流量列，而流量恰恰是口径分歧')
    print('         最大的一类 —— 所以这里的「符号相反的序列占比」天然偏高。')
    print('         审计那几个数、它们各自的窗口、以及 2026-09 逐条复算的结果')
    print('         （哪几条对得上、哪几条复算不出来）全在 CONTRACT §6.5，这里不复述。')
    print('   注三：⚠️ 上面两行跳变**不是同一个统计量**，别混着读，更别拿去对审计的')
    print('         「30pp vs 4.8pp」—— §6.5 已经查明审计通篇写的「跳变」指的是')
    print('         **最大**跳变（maxjump），照 medjump 复算只有个位数 pp。')
    print('         上一版这里印着一句「放大倍数（2.15x vs 2.08x）与跳变量级对得上」，')
    print('         两处都是错的：2.15 是写那句话时的旧值（同一节上面三行就现算并印着')
    print('         另一个数），而两侧跳变量级本来就差着一个统计量的定义。已删。')

    print('\n⑧ 阈值推导重跑')
    _recalibrate()
    print('\n' + '=' * 78)
    print('自测通过')


if __name__ == '__main__':
    _selftest()
