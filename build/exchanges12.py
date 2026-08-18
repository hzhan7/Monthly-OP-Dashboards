# -*- coding: utf-8 -*-
"""12 家交易所总览页 —— 写出 data/exchanges12.js。

这一页只回答一个问题：**12 家里谁在跑赢、谁在拐点**。

━━ 主口径：定基名义额（constant-basis notional）━━
    定基名义额 = 张数 × 乘数 × 2019-01 基期价格 × 2019-01 基期汇率

价格项与汇率项都是**常数**，所以：
  · 任何一条腿的定基名义额，其**增长率与该腿张数的增长率完全相同**；
  · 常数只改变「不同产品之间的权重」与「不同交易所之间的份额」，
    不把标的涨跌与汇率波动混进增长里。

为什么不能直接比张数：单张名义额 = 乘数 × 标的价格，而**乘数是交易所自选的产品设计**。
  · CME E-mini S&P（$50 × 指数）与 Micro E-mini（$5 × 指数）差 10 倍 ——
    把一张 E-mini 拆成 10 张 Micro，张数 ×10，敞口一点没变；
  · JPX 金融衍生品：原始张数与「大合约当量」在同一段窗口里**符号相反**
    （series/jpx.csv 的 adv_deriv_index_raw_ + adv_deriv_rates_raw_ 对
    adv_deriv_fin_lgeq_kcontracts，实测值由「JPX 两个单位」那张图现算，不写死）——
    同一家交易所、同一批合约，两个口径给出相反的结论。
张数列在 CSV 里保留、也进本页末尾的核对表，**但不进任何主图**。

「张数口径同比 vs 定基名义额口径同比」那两张图（下面 Exhibit 序列里的 7 与 8）
是这次改口径的核心证据 —— 编号会随分支变化，故正文一律现算不写死。
差值为正 = 增长来自「合约变小」（拆细、mini/micro 化）而不是敞口变大。

**这个差值只有在一家配了 ≥2 个合约产品时才是实测出来的。** 只配了一个篮子产品的家
（本页的 MIAX / HKEX / JPX / SGX），两个口径之间只差一个**同一个常数**，
同比恒等、差值恒为 0 —— 那是构造出来的零，不是"这家没有合约变小"。
把它们和真有测量结果的家画进同一张图，读者一定会把结构性 0 读成实测 0，
所以那两张图只画 ≥2 个合约产品的家，被排除的家在图注与口径说明里逐个点名。

JPX 恰恰是被这条规则排除的一家，而它又是全仓最强的一份反例，所以**单给它一张图**
（编号由 jpx_n 现算，见代码）：原始张数 vs 大合约当量，两条线都指数化到基期 100。
⚠ 当量列**不是 JPX 逐月发布的字段**，是 fetch/jpx.py 按 JPX IR 脚注的官方折算系数
（日経225mini ÷10、マイクロ ÷100、ミニTOPIX ÷10、ミニJGB ÷10 …）自建、
并用 IR 季度合计校准到 ~2% 以内的（docs/verify/verify_jpx.md §N2）。
这一条必须写在图注里 —— 说成"官方并列发布"是给读者一个它没有的权威等级。
那张图只取**金融**衍生品（股指 + 利率），不含商品：旧 TOCOM 2020-07 才迁入 OSE，
含商品的合计在那之前是 pro-forma（series/jpx.csv 的 cmdty_proforma 列标了 68 个月），
跨 2020-07 读会把一次并购读成成交量变化。

━━ 三条与单公司页不同的硬规矩（沿用 build/exchanges.py 的横截面页规矩）━━
1. **单位不可加总。** 12 家的源列有张数、股数、本币成交额三种，没有公约单位。
   定基名义额是本页唯一把它们摆进同一张图的办法 —— 换算链每一跳都有表作证
   （series/contract_specs.csv 的乘数与基期价、series/fx.csv 的基期汇率）。
2. **发布门槛 = 成员的共同最新月，不是各家自己的最新月。**
   12 家披露节奏不同，若各画各的最新月，「谁跑赢」里就有一整个月是口径造的。
   抬头 / 页脚 / 口径说明三处都写明短板是哪家、跑在前面的更新到了哪个月。
3. **缺常数只降级到图，不拖垮整页（2026-08-06 改）。** 见下一节。真·结构性失败
   （某家在基期窗口内没有数据、共同历史太短、源 CSV 缺列）仍然打印原因并
   **以退出码 0 正常结束**，绝不硬写一张缺员的页，也绝不抛异常
   （那会在 monthly_run 日志上天天多一条假 FAIL）。

━━ 优雅降级：为什么「缺基期常数」不该卡住增长类图 ━━
本页用到的 product_id 里有一部分填不出基期价格（清单与逐个原因见 GAP_REASONS；
具体几个由运行时算出来并打进页面正文 —— 这里**不写死一个会过期的数**，
2026-08-06 就因为 ICE 能源改走 Brent 而从 8 个变成了 7 个）。
原来的做法是整页 skip。但**篮子常数只在跨所比水平值时才需要**：

    某家的定基名义额  N(t) = Σ_p k_p · S_p(t)      k_p 是产品 p 的基期常数（未知或已知）
    指数化           I(t) = N(t) / N(基期) × 100

若这家只有**一个**产品块（p 只有一个），k_p 在分子分母里同时出现、**被完全约掉** ⇒
I(t) 与 k_p 无关，是精确值，一个常数都不需要。MIAX 正是这一种（四条腿同属
US_MULTILIST_EQ_OPT 一个产品，那个常数至今填不出来，但它的增长曲线是精确的）。
同构证据见 build/exchanges_apac.py 的日经 SGX/大阪比值指数（该页图注原话：
「任何恒定的乘数差在指数化里被完全约掉 ⇒ 那条趋势线不依赖任何未知常数，是精确的」）。

多于一个产品块时，k_p 不会约掉 —— 它决定块与块之间的权重。但仍有一个**精确**的结论：
N(t)/N(t') = Σ_p k_p S_p(t) / Σ_p k_p S_p(t')，这是各块自身比值 S_p(t)/S_p(t') 的
加权平均（权重 k_p·S_p(t') / Σ_q k_q S_q(t') 非负、和为 1，中位分数不等式）⇒

    **min_p [S_p(t)/S_p(t')]  ≤  N(t)/N(t')  ≤  max_p [S_p(t)/S_p(t')]**

两端都能在 k 取极端值时取到，所以这是**紧的、实测的**上下界，不含任何编出来的常数。
指数、同比、年度同比（分子分母各是同一组权重的线性组合）三者同理。
已定价的那些块之间权重是已知的，可以先合成一块 ⇒ 界只被真正未知的那几个产品撑开。

于是本页的降级规则是：
  · 增长类图（指数化、同比、年度同比）：**12 家全上**。一个块的家给点值，
    多个块的家给上下界（Exhibit 4 的 range_band 带 = 界，菱形 = 点值）。
  · 水平值类图（跨所名义额大小、池内占比）：**只画常数齐备的那几家**，
    缺的逐个点名，并区分制度性缺失与技术性未取到（GAP_REASONS）。
  · 张数 vs 定基名义额差值图：沿用原规矩，只取配了 ≥2 个合约产品**且合约块全部已定价**
    的家 —— 只配 1 个时两条序列只差同一个常数，同比恒等、差值恒为 0，
    画出来会被读成「这家没把合约做小」。

━━ 同比口径（2026-08-07 改）：一律 **12 个月滚动合计的同比**，不用单月同比 ━━
原来 Exhibit 4 / 7 / 8、汇总表第 ②③ 组、抬头的 y/y 与「拐点」全是**单月同比**
（本月 ÷ 去年同月 − 1）。分子分母各只有一个月，一次到期日错位、一次假期错月、
去年同月的一次极端行情都会整个吃进这一个读数。本页自己的产品块序列实测
（数字由 volcmp() 现算并印进图注与自检行，一个都不写死）：逐月标准差普遍腰斩，
相邻月最大跳变从三位数 pp 降到十几 pp，而且有大量月份两个口径**符号相反** ——
同一条序列、同一个月，一个说在涨、另一个说在跌。

改法：`ttm_yoy()` 取代 `yoy()` 进入所有对外读数。数学上这不破坏本页赖以成立的紧界：
    TTM_N(t) = Σ_{i<12} N(t−i) = Σ_p k_p · [Σ_{i<12} S_p(t−i)] = Σ_p k_p · T_p(t)
滚动合计仍是各产品块滚动合计的同一组常数线性组合 ⇒ TTM_N(t)/TTM_N(t−12) 依旧是
各块 T_p(t)/T_p(t−12) 的加权平均（权重 k_p·T_p(t−12)/Σ 非负、和为 1）⇒
min/max 仍是紧界，Exhibit 4 的蓝带语义一字不变。

**三处判定不改，逐条给理由（不是漏改）：**
  · **Exhibit 5 / 6 的年度同比**（annual_yoy）本来就是 12 个月量级的聚合，
    不是单月，没有要平滑的毛刺；而且它按**日历年**切、未满年同月对同月，
    与滚动窗口切法不同但同属「12 个月聚合」，12 月份那一格两者恰好相等。
  · **汇总表的 m/m 列**：那是「本月 vs 上月」的运营监控量，本来就该看单月。
  · **汇总表第 ① 组（水平值）的 y/y 列**：这一列**恒等于本行前三列的算术**
    （本月 ÷ 去年同月）。给水平值行印一个滚动同比，读者拿第一列除第三列会得到另一个数，
    **表内自相矛盾**，比口径混用更糟 ⇒ 它天然是单月口径，只能在组标题与表注里标死。
    第 ② 组不受此限：它三列显示的本身就是指数读数，y/y 直接取滚动口径。
  · **Exhibit 2 / 3 / 9 与核对表**：指数化水平值、当月水平值、张数对账，
    压根不是增长率，没有口径可改。
⇒ 改完**图上只剩一种同比曲线口径**（滚动合计），加上一种明确标注的年度聚合；
  唯一的单月同比在汇总表第 ① 组，组标题与表注都写死并印出两个口径的当期差距。

**滚动合计不乘交易日数**：本页所有腿早在 leg_units() 里就已经统一除成**日均**
（per='month' 的列除以当月交易日），这是本文件的既定做法。滚动合计 = 12 个日均值
之和 = 12 × 滚动平均日均值，同比的分子分母同权，交易日在比值里不出现。再乘回去
等于把「今年这 12 个月比去年多两个交易日」这类日历差异重新塞进增长里，而且 12 家
的交易日列名各不相同（cboe.csv / hkex.csv 干脆没有），第二套口径必然对不齐。

━━ Exhibit 序列 ━━
  1  汇总表：三组 —— 水平值（常数齐备的家）/ 指数化增长（12 家，缺常数的给区间）/ 口径差
  2  定基名义额指数化折线（基期 = 100），只含增长口径精确的家
  3  定基名义额水平值排序（**只含常数齐备的家**）—— 全页唯一的跨所水平值图
  4  12 家最新同比：菱形 = 精确点值，蓝带 = 常数未定时的精确区间
  5  热力矩阵：行 = 增长精确的家、列 = 近 8 年、格 = 年度同比
  6  热力矩阵：缺常数那几家**拆到产品块**（每块单产品 ⇒ 常数约掉，格格精确）
  7  同一批合约腿：张数口径 y/y vs 定基名义额口径 y/y（并排两根柱）
  8  两者之差（正 = 增长来自合约变小）—— 改口径的核心证据
  9  JPX 金融衍生品：原始张数 vs 大合约当量（被 7/8 结构性排除，但证据最强的一家）
 10  近 13 个月核对表（两个口径并列，供与官方新闻稿逐位对账）

━━ 为什么 6 家以上的图不用 diverging_bars，改用 grouped_bars ━━
数据色只有六个，12 家不可能一家一色，所以凡是同时呈现 6 家以上的图，身份一律靠标签
（heat_matrix 的行标签、grouped_bars 的 x 轴标签），这一条没有例外。
在「靠标签」的几种图型里本页选 grouped_bars 而不是 diverging_bars，理由是引擎实测：
assets/charts.js 里 `diverging_bars` 的图例与表格视图行名是**写死的 COST 专用字符串**
（legend 两项 'Reported > Core（油汇顺风）' / 'Reported < Core（油汇拖累）'，
seriesRows 的行名 'Reported − Core'），payload 没有任何字段能覆盖它们。
在交易所页上用它，图例会印出一句与本页毫无关系、且事实上错误的话。
`bars_labeled` 同样不行：它的纵轴被写死成 `y0 = 0`，负的差值会被画到绘图区之外。
grouped_bars 三样都对：图例读 groups[].name、纵轴 `y0 = min(0, mn×1.15)` 容得下负值、
`bar_labels: true` 时负值的数值标签也摆在柱下方。
代价是正负不再自动分色（引擎只给 diverging_bars 那一种分色），所以本页靠**排序**
（柱按数值从大到小排）与图注把符号讲清楚。要改这一点得动引擎，而引擎是 14 张已上线页
共用的，不为一张新页去改。

━━ 数据源 ━━ 只读 series/*.csv：
  12 家的月度披露 CSV（cme cboe hkex ice ndaq miax enx db1 jpx tmx asx sgx）
  series/contract_specs.csv  乘数 / 基期价格 / 计价币种（常数表）
  series/fx.csv              月度汇率（常数表，本页只取 2019-01 那一行）
换算由 build/notional.py 执行（它只依赖上面两张常数表，不依赖 build/pools.py）。

用法:
  python3 build/exchanges12.py              正式跑，写 data/exchanges12.js
  python3 build/exchanges12.py --selftest    渲染管线自检，见文件末尾 selftest()
幂等：重复跑除首行构建日期外逐字节相同。
"""
import json
import os
import sys

import numpy as np
import pandas as pd

import notional
import axisfmt
import payload_guard
import pctile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
OUT = os.path.join(ROOT, 'data', 'exchanges12.js')

TICKER = 'exchanges12'
SRC = ('Source: 12 exchange operators\' monthly volume disclosures; contract multipliers and '
       'Jan-19 base prices from series/contract_specs.csv; FX from ECB (series/fx.csv). '
       'Format after Goldman Sachs GIR')

BASE = pd.Period(notional.BASE_MONTH, freq='M')   # 2019-01，全仓锁死，见 notional.BASE_MONTH

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
HEAT_YEARS = 8       # 热力矩阵：近 8 年
TTM = 12             # 滚动窗口 = 12 个月（本页所有同比读数的口径）
TBL_MONTHS = 13      # 末尾核对表：契约 §5.4 的 13 个月
MIN_COMMON = 24      # 共同历史短于这么多个月就不发（y/y 都画不出来）
TOP_N = 5            # Exhibit 2 单独画的家数，其余合并「其他」

# 数据色只有六个（RED 是断点与截轴离群值的专用色，不做数据色）。
# 六色 = TOP_N 家 + 一条「其他」，正好用满，所以本页任何一张图都不许出现第 7 条线；
# 12 家一起出现的图一律用身份靠标签的图型（grouped_bars / heat_matrix）。
LINE_COLORS = ['NAVY', 'BLUE', 'MBLUE', 'GREEN', 'GOLD', 'GRAY']

# assets/charts.js 认得的全部 kind。写死在这里只为自检时对一遍 ——
# 引擎是别人的地盘，本文件只负责别递给它不认识的东西。
ENGINE_KINDS = {
    'bar_line', 'bar_line_dual', 'bars_labeled', 'bridge_bar', 'diverging_bars',
    'grouped_bars', 'gs_bar', 'gs_line', 'gs_line_avg', 'heat_matrix', 'lines',
    'lines_endlabels', 'qtr_bar', 'range_band', 'seasonality', 'stacked_dual', 'year_lines',
}


# ─────────────────────────── 成员与换算链声明 ───────────────────────────
# 每一「腿」= 某家某一条源列 + 它对应的 contract_specs.csv 产品。
#   col          series/<csv> 里的列名（本文件里的列名全部由 head -1 实读核对过）
#   scale        源列单位 → 规范单位（张 / 股 / 本币基本单位）的倍数
#                例：k contracts → 张 = 1000；€bn → € = 1e9；¥tn → ¥ = 1e12
#   per          'day'   源列本来就是日均（ADV / ADT / ADNV），直接用
#                'month' 源列是当月合计，要除以 days 列才是日均
#   days         per='month' 时的交易日列名
#   product      contract_specs.csv 的 product_id（乘数 / 基期价 / 币种从那里来）
#   zero_before  该列首个有效月晚于基期时，之前的月份是否按 0 计入（见 ZERO_WHY）
#
# 一家的「定基名义额」= 各腿定基名义额之和。**某个月只要有一条腿缺值，整家该月作废**
# —— 只加"还在的那几条腿"会画出一次凭空的下跌，比留空糟得多。
class Leg:
    __slots__ = ('col', 'scale', 'per', 'days', 'product', 'label', 'zero_before')

    def __init__(self, col, scale, product, label, per='day', days=None, zero_before=False):
        self.col, self.scale, self.product, self.label = col, scale, product, label
        self.per, self.days, self.zero_before = per, days, zero_before


# 成员：(key, 英文名, 中文名) —— key 同时是 series/<key>.csv 与 source_dates.csv 的 ticker
MEMBERS = [
    ('cme',  'CME Group',        'CME'),
    ('cboe', 'Cboe Global',      'Cboe'),
    ('ice',  'ICE / NYSE',       'ICE'),
    ('ndaq', 'Nasdaq',           'Nasdaq'),
    ('miax', 'MIAX',             'MIAX'),
    ('db1',  'Deutsche Börse',   '德交所'),
    ('enx',  'Euronext',         'Euronext'),
    ('hkex', 'HKEX',             '港交所'),
    ('jpx',  'JPX',              '日交所'),
    ('sgx',  'SGX',              '新交所'),
    ('asx',  'ASX',              '澳交所'),
    ('tmx',  'TMX',              '多交所'),
]
MEM_KEYS = [k for k, _, _ in MEMBERS]
DISP = {k: d for k, d, _ in MEMBERS}
ZHNAME = {k: z for k, _, z in MEMBERS}

# ── 类别轴（x 是交易所名而不是月份）一律水平排 ──
# 引擎给旋转 x 标签的底部空间只有 XB = 36px（charts.js:522），而 45° + anchor='end' 的
# 文字是**从锚点往左下方铺开**的：向下伸出 0.707 × 文字宽，锚点在 M.t+ph+9，
# 所以文字宽超过 (36−9)/0.707 ≈ 38px 就画到 SVG 画布外、盖在下方的 Note 正文上。
# 实测（getBoundingClientRect，含 transform）：「Deutsche Börse」宽 61px ⇒ 下越界 15.7px，
# Exhibit 3 / 4 / 7 / 8 四张全中。
# 水平排时引擎改用 XB = 22px、anchor='middle'、不旋转，只向下伸约 2px，几何上不可能越界；
# 约束改成「标签宽 < 自己那一格 band」：本页四张类别轴图都是通栏，
# 最挤的 Exhibit 4 有 12 格、band ≈ 92px，最宽的「Deutsche Börse」61px，
# 与左右邻居的净间距 ≥ 38px。姊妹页 exchanges_eu / exchanges_apac 本来就是 xrot: 0。
CAT_XROT = 0

LEGS = {
    # ── CME：五大类 ADV（k 张/日）──
    'cme': [
        Leg('adv_rates_kcontracts',  1000, 'CME_RATES',        '利率'),
        Leg('adv_equity_kcontracts', 1000, 'CME_EQUITY_INDEX', '股指'),
        Leg('adv_energy_kcontracts', 1000, 'CME_ENERGY',       '能源'),
        Leg('adv_ag_kcontracts',     1000, 'CME_AG',           '农产品'),
        Leg('adv_fx_kcontracts',     1000, 'CME_FX',           '外汇'),
    ],
    # ── Cboe：指数期权按单品种走（这三个产品的基期价格已实测入库），
    #    其余走篮子产品。EU 现货与 FX 是金额口径，本身就是"钱"。──
    'cboe': [
        Leg('adv_spx_options_kcontracts',       1000, 'CBOE_SPX_OPT',        'SPX 期权'),
        Leg('adv_vix_options_kcontracts',       1000, 'CBOE_VIX_OPT',        'VIX 期权'),
        Leg('adv_xsp_options_kcontracts',       1000, 'CBOE_XSP_OPT',        'XSP 期权'),
        Leg('adv_vix_futures_kcontracts',       1000, 'CBOE_VIX_FUT',        'VIX 期货'),
        Leg('adv_multilist_options_kcontracts', 1000, 'US_MULTILIST_EQ_OPT', '个股/ETF 期权'),
        Leg('adv_us_equities_matched_shares_bn', 1e9, 'US_CASH_EQUITY_SHARE', '美股现货'),
        Leg('adv_eu_equities_adnv_eurbn',        1e9, 'EU_CASH_ADNV_EUR',    '欧股现货'),
        Leg('adv_fx_adnv_usdbn',                 1e9, 'FX_SPOT_USD',         'FX 现汇'),
    ],
    # ── ICE：Brent 原油 + 两档利率 + NYSE 现货与股票期权 ──
    # ⚠ 能源那条腿 2026-08-06 由 adv_energy_kcontracts / ICE_ENERGY（全球全能源合成篮子）
    #   换成 adv_brent_kcontracts / ICE_BRENT_IFEU（仅 Brent）。换的理由不是"Brent 更重要"，
    #   是**只有 Brent 这一列的口径与乘数对得上**：官方脚注(1) 保证整列以 ICE Futures
    #   Europe 标准合约当量计（新交所迷你合约已被官方 ÷10 折进来），所以「张数 × 1,000 桶」
    #   精确成立；而全能源那一列是全球口径（IFEU + Endex + IFUS + IFAD + NGX），
    #   唯一能拿到的分产品结构只覆盖 IFEU（2019-01 占全球 67.0%），拿它去套 100% 的量
    #   是方向与大小都不可知的偏差。详见 build/pools.py 模块 docstring 七。
    #   ⇒ 本页 ICE 的能源块因此**只含 Brent**，是它真实能源体量的约三分之一
    #     （2019-01 Brent 947 / 全能源 2,718 千张日均 = 34.8%）。
    #     这一句必须出现在页面的口径说明里，见 SCOPE_NOTES。
    'ice': [
        Leg('adv_brent_kcontracts',              1000, 'ICE_BRENT_IFEU', '能源（仅 Brent 原油）'),
        Leg('adv_stir_kcontracts',               1000, 'ICE_STIR',            '短端利率'),
        Leg('adv_mltir_kcontracts',              1000, 'ICE_MLTIR',           '中长端利率'),
        Leg('adv_nyse_equity_options_kcontracts', 1000, 'US_MULTILIST_EQ_OPT', 'NYSE 股票期权'),
        Leg('adv_nyse_us_cash_handled_mnsh',      1e6, 'US_CASH_EQUITY_SHARE', 'NYSE 现货'),
    ],
    # ── Nasdaq：本页只用有 2019-01 以前历史的美股现货撮合量（三个场内合计）──
    'ndaq': [
        Leg('vol_us_cash_matched_nasdaq_sh', 1, 'US_CASH_EQUITY_SHARE', 'Nasdaq 撮合',
            per='month', days='trading_days_us_equities'),
        Leg('vol_us_cash_matched_ntx_sh',    1, 'US_CASH_EQUITY_SHARE', 'BX 撮合',
            per='month', days='trading_days_us_equities'),
        Leg('vol_us_cash_matched_psx_sh',    1, 'US_CASH_EQUITY_SHARE', 'PSX 撮合',
            per='month', days='trading_days_us_equities'),
    ],
    # ── MIAX：四个期权场内的 ADV（官方 API 列）──
    'miax': [
        Leg('adv_miax_options_api_kcontracts',     1000, 'US_MULTILIST_EQ_OPT', 'MIAX Options'),
        Leg('adv_pearl_options_api_kcontracts',    1000, 'US_MULTILIST_EQ_OPT', 'MIAX Pearl'),
        Leg('adv_emerald_options_api_kcontracts',  1000, 'US_MULTILIST_EQ_OPT', 'MIAX Emerald',
            zero_before=True),
        Leg('adv_sapphire_options_api_kcontracts', 1000, 'US_MULTILIST_EQ_OPT', 'MIAX Sapphire',
            zero_before=True),
    ],
    # ── Deutsche Börse：Eurex 三大类 + Xetra/FWB 现货成交额 ──
    'db1': [
        Leg('adv_eurex_rates_contracts',  1, 'EUREX_RATES',  'Eurex 利率'),
        Leg('adv_eurex_index_contracts',  1, 'EUREX_INDEX',  'Eurex 股指'),
        Leg('adv_eurex_equity_contracts', 1, 'EUREX_EQUITY', 'Eurex 个股'),
        Leg('turnover_cash_total_eurbn', 1e9, 'EU_CASH_ADNV_EUR', '现货成交额',
            per='month', days='trading_days_cash'),
    ],
    # ── Euronext：现货 ADNV + 三类衍生品（期货与期权同产品，分两条腿相加）──
    'enx': [
        Leg('adv_cash_adnv_eurbn',                 1e9, 'EU_CASH_ADNV_EUR',       '现货 ADNV'),
        Leg('adv_index_futures_kcontracts',       1000, 'ENX_INDEX_DERIV',        '股指期货'),
        Leg('adv_index_options_kcontracts',       1000, 'ENX_INDEX_DERIV',        '股指期权'),
        Leg('adv_singlestock_futures_kcontracts', 1000, 'ENX_SINGLESTOCK_LEGACY', '个股期货'),
        Leg('adv_singlestock_options_kcontracts', 1000, 'ENX_SINGLESTOCK_LEGACY', '个股期权'),
        Leg('adv_commodity_futures_kcontracts',   1000, 'ENX_MATIF',              '商品期货'),
        Leg('adv_commodity_options_kcontracts',   1000, 'ENX_MATIF',              '商品期权'),
    ],
    # ── HKEX：现货 ADT（港元金额）+ 衍生品 ADV（张）──
    'hkex': [
        Leg('adt_hkdbn',                 1e9, 'HK_CASH_ADT_HKD', '现货 ADT'),
        Leg('derivatives_adv_contracts',   1, 'HKEX_DERIV',      '衍生品'),
    ],
    # ── JPX：现货 ADT（日元金额）+ 衍生品原始张数（篮子常数吸收 mini/micro 的乘数差）──
    'jpx': [
        Leg('adt_cash_total_jpytn',           1e12, 'JP_CASH_ADT_JPY', '现货 ADT'),
        Leg('adv_deriv_total_raw_kcontracts', 1000, 'JPX_DERIV',       '衍生品（原始张数）'),
    ],
    # ── SGX：现货 SDAV（新元金额）+ 衍生品 DDAV（张）──
    'sgx': [
        Leg('sdav_sgdmn',     1e6, 'SG_CASH_SDAV_SGD', '现货 SDAV'),
        Leg('ddav_contracts',   1, 'SGX_DERIV',        '衍生品'),
    ],
    # ── ASX：现货 ADT（澳元金额）+ 24 所期货期权 + ETO ──
    'asx': [
        Leg('adt_cash_total_audbn',            1e9, 'AU_CASH_ADT_AUD', '现货 ADT'),
        Leg('adv_futures_and_options_contracts', 1, 'ASX_DERIV',       'ASX 24 期货期权'),
        Leg('adv_single_stock_options_contracts', 1, 'ASX_ETO',        '个股期权'),
        Leg('adv_index_options_contracts',        1, 'ASX_ETO',        '指数期权'),
    ],
    # ── TMX：只有 Montréal Exchange 四类衍生品有 2019-01 以前的历史 ──
    'tmx': [
        Leg('mx_adv_stir_futures_contracts',   1, 'MX_STIR',       '短端利率期货'),
        Leg('mx_adv_bond_futures_contracts',   1, 'MX_BOND',       '国债期货'),
        Leg('mx_adv_equity_options_contracts', 1, 'MX_EQUITY_OPT', '个股期权'),
        Leg('mx_adv_etf_options_contracts',    1, 'MX_ETF_OPT',    'ETF 期权'),
    ],
}

# zero_before 的唯一理由，必须逐条写明；没有理由的列一律进 UNCOVERED 而不是补 0。
ZERO_WHY = (
    'MIAX 的官方 API 只从该交易所<b>上线当月</b>起返回数据，所以 Emerald（列自 2019-03 起）'
    '与 Sapphire（列自 2024-08 起）在那之前的缺月是「当时还没有这个交易所」，'
    '不是「数据没抓到」——按 0 计入即官方口径下的集团合计。'
    '⚠ 这一条是<b>推断</b>（上线月份未在本仓另行取证），故单独列出；'
    '其余任何首月晚于基期的列一律不补 0，直接进「未覆盖」清单。'
)

# 已知在本页范围内、但<b>没有进腿</b>的列，逐条给理由。
# 这张表存在的意义：读者看到的「某家的名义额」是它全部业务的一个<b>子集</b>，
# 子集边界不写清楚，跨家的份额与排名就会被当成全口径来读。
UNCOVERED = {
    'cme': [('adv_metals_kcontracts', 'contract_specs.csv 没有 CME 金属类的篮子产品行')],
    'cboe': [],
    'ice': [('adv_ag_metals_kcontracts / adv_equity_index_kcontracts / '
             'adv_fx_credit_kcontracts / adv_single_stock_kcontracts',
             'contract_specs.csv 没有对应的篮子产品行'),
            # ⚠ 这一条是本页 ICE 那根柱子最重要的一句话，不是脚注：
            #   能源块只含 Brent，而 Brent 只是 ICE 能源的三分之一。
            ('adv_natgas_kcontracts / adv_power_kcontracts / adv_otheroil_kcontracts / '
             'adv_environmentals_kcontracts（即 ICE 能源里 Brent 以外的全部）',
             '<b>本页 ICE 的能源块只含 Brent 原油（期货+期权）</b>，'
             '2019-01 占 ICE 全能源张数的 <b>34.8%</b>（947 / 2,718 千张日均），'
             '187 个月中位 33.3% ⇒ <b>ICE 这根柱子系统性低于它真实的能源体量</b>。'
             '这是主动选择：Brent 那一列由官方脚注保证整列以 ICE Futures Europe 标准合约'
             '当量计，一个乘数（1,000 桶）对全列精确成立；而天然气（含 TTF）、电力、'
             '其他油品、排放权每一行内部都混着多个交易所与多种量纲（MMBtu / therm / MWh / '
             '加仑 / 吨），一个乘数套不上去。原先挂的全能源合成篮子 ICE_ENERGY 已停用 —— '
             '它要用 67% 子集（ICE Futures Europe）的结构去套 100% 的量，'
             '偏差方向与大小都不可知'),
            ('adv_gasoil_kcontracts', 'Gasoil 的乘数有（100 公吨/张，官方规格页实测），'
             '缺 2019-01 的官方基期价格：ARA Gasoil 以美元/公吨报价，EIA 全站没有这个口径，'
             'ICE 自己的历史结算价在 Report Center 的 reCAPTCHA 后面。'
             '加上它能把覆盖率抬到 46.3%，但代价是一个来路不明的常数 ⇒ 不做'),
            ('cds_total_notional_usdbn', 'CDS 清算名义额是清算业务，不是成交量，口径不同不并入')],
    # 2026-08-18 更正：原文写「这三列自 2025-01 才有…无法定基」，其中**两列已经不成立**
    # （ndaq 那一轮把北欧衍生品回补到 2013-01、美股撮合量回补到 2010-10）。
    # 这句话是**印在页面上的**，不是代码注释，留着就是在页面上讲一件已经不成立的事。
    'ndaq': [('vol_us_options_mmcontracts / vol_nordic_cash_value_usdbn',
              '这两列自 2025-01 才有，早于基期 2019-01 没有历史，无法定基'
              '（美股期权：IR 落地页无年份归档、nasdaqtrader 的月表只有四行三列且口径只有'
              'IR 六所的一半，实测 source_hard；北欧现货美元列：官方月度原件是欧元，'
              '折美元后与 IR 系统性低 0.77%–2.50%，scope 复原不了）'),
             ('vol_nordic_derivs_mmcontracts / vol_us_cash_matched_mnsh',
              '这两列已分别回补到 2013-01 与 2010-10，历史足够定基；'
              '本页暂未纳入 —— 纳入要先给它们配 contract_specs 的合约乘数与基期价格，'
              '那是另一次改动（本页的张数→名义额换算链只认登记过的 product_id）')],
    'miax': [('adv_equities_api_mnshares', '列自 2020-12 起，且该月与 MIAX Pearl Equities 的'
              '上线月不重合，无法按「上线前记 0」处理，故整条腿不计入'),
             ('adv_index_options_api_kcontracts',
              'contract_specs.csv 没有 MIAX 指数期权的产品行')],
    'db1': [('adv_eurex_dividend_contracts', 'contract_specs.csv 没有股息衍生品的产品行'),
            ('vol_power_* / vol_gas_*', '电力与天然气的计量单位是 MWh，不是张，'
             '与本页的张数→名义额换算链不同源')],
    'enx': [('adv_mts_cash_eurbn / adv_mts_repo_eurbn',
             'MTS 是固定收益电子平台，回购名义额与现货成交额不可加总')],
    'hkex': [],
    'jpx': [('adv_secoptions_kcontracts',
             '已含在 adv_deriv_total_raw_kcontracts 里，单列会重复计数'),
            ('adv_deriv_*_lgeq_kcontracts',
             '大合约当量列不进换算链（乘数已经被折算掉了，再乘一次基期价就是重复计数）；'
             '它只在 JPX 那张「同一批合约、两个单位」的图里出现'),
            ('adnv_deriv_total_jpytn',
             '官方名义成交金额，但那是<b>当期</b>日元金额（含标的涨跌与汇率），'
             '与本页的定基口径不同源，不能混进增长图')],
    'sgx': [('vol_fx_futures_contracts',
             '已含在 ddav_contracts 里，单列会重复计数')],
    'asx': [],
    'tmx': [('tmx_all_value_cad / tsx_value_cad', '现货成交额列自 2021-08 才有，'
             '早于基期 2019-01 没有历史，无法定基'),
            ('mx_adv_index_futures_contracts / mx_adv_index_options_contracts / '
             'mx_adv_share_futures_contracts',
             'contract_specs.csv 没有对应的篮子产品行')],
}


# ───────────────── 基期常数缺口：8 个 product_id，逐个分类并写进页面 ─────────────────
# 页面必须区分这两类，因为它们对读者的含义完全不同：
#   制度性缺失 = 该交易所根本不发这个数，**补不上**（等官方改口径，不是等我们多跑一次）；
#   技术性未取到 = 官方路径存在且已验证可回溯，只是成本超出本页边界（下次能补）。
# 每条理由都指向仓内可复算的证据脚本；措辞照抄那些脚本里的实测结论，不做二次概括。
GAP_INST = 'institutional'
GAP_TECH = 'technical'
GAP_KIND_ZH = {
    GAP_INST: '制度性缺失（该交易所根本不发这个数，补不上）',
    GAP_TECH: '技术性未取到（官方路径存在且已验证，成本超出本页取数边界）',
}
GAP_REASONS = {
    'SGX_DERIV': (GAP_INST, 'SGX 按张收费，官方月报只发 Volume 与 Open Interest。'
                  '实测 2019-01 的 SGX Monthly Market Statistics Report（官方 PDF，32 页）：'
                  '衍生品节只有 Contract Volume 与 Open Interest 两类表，逐页正则扫 '
                  '<code>notional</code> / <code>turnover value</code> / '
                  '<code>contract value</code> 三个词<b>全文档零命中</b>；'
                  '「Turnover Value」只出现在现货（Securities market）节。'
                  '复算脚本 <code>build/basefill/eastasia2.py</code>。'),
    'HKEX_DERIV': (GAP_INST, 'HKEX 同样按张收费，从不公布衍生品成交金额。'
                   '四个官方口子逐个实测<b>全部 HTTP 200</b>（即不是被挡住，是表里就没有），'
                   '拿到的表头一律是 Contract Volume + Open Interest，没有任何金额列。'
                   '复算脚本 <code>build/basefill/eastasia2.py</code>。'),
    # ⚠ 2026-08-06：原来这里有一条 'ICE_ENERGY'（ICE 全能源合成篮子）。那个产品已停用 ——
    #   本页 ICE 的能源块改走 ICE_BRENT_IFEU（仅 Brent，常数已实测入库），
    #   所以它不再是一个"缺口"，而是一个**已经做出的口径取舍**，
    #   位置在 UNCOVERED['ice'] 里（缺口讲"补不上"，取舍讲"为什么不补"，两件事不能混在一栏）。
    'US_MULTILIST_EQ_OPT': (GAP_TECH, '乘数那一半已经解决（OCC By-Laws + ODD 原文，100 股/张）；'
                            '缺的是「2019-01 按期权成交量加权的标的均价」。'
                            'OCC 官方 Volume Query 通道已打通，但服务端硬限 '
                            '<code>Data available for the past 24 months</code>，2019-01 取不到；'
                            '连同它在内的<b>六条路径已逐条实测排除</b>（Cboe 期权量档案不含 ETF、'
                            'api.nasdaq.com 历史价对 2019 返回 totalRecords=0、nasdaqtrader FTP '
                            '止于 2016、SEC MIDAS 只有价格十分位、Cboe 美股月度只有全市场合计）。'
                            '复算脚本 <code>build/basefill/us_asx_mx2.py</code>。'),
    'MX_EQUITY_OPT': (GAP_TECH, 'MX 官方月报只到「Equity Options / ETF Options」两个合计，'
                      '没有逐类金额。逐类通道存在且可回溯，但期权类下拉框有 <b>940 个 symbol</b>，'
                      'm-x.ca 的 robots.txt 写死 <code>Crawl-delay: 15</code> ⇒ '
                      '940 × 15s ≈ <b>3.9 小时</b> / ≈1.2 GB。'
                      '复算脚本 <code>build/basefill/asx_mx.py</code>。'),
}
# ICE 的两档利率是**永久张数口径**，不是"还没取到"。这段文字与 build/pools.py 的
# ICE_RATES_CONTRACTS_ONLY、series/contract_specs.csv 里两行的 notes 说的是同一件事。
_ICE_RATES_GAP = (
    '<b>永久张数口径，不是暂时取不到</b>。两条理由各自独立成立：'
    '<br>① <b>官方拆不开</b>：ICE 唯一公开、不要 reCAPTCHA 的分产品历史表 '
    '<code>ice.com/report/7</code> 把短端与中长端并成<b>一列</b> Interest Rates'
    '（2019-01 期货 37,491,346 + 期权 7,632,263 = 45,123,609 张，与本仓 '
    '<code>adv_stir + adv_mltir</code> = 45,122,000 张只差 0.004%，确认是同一批合约）；'
    '要拆到合约层只有 Report Center 的 report 26/27，其 metadata 写着 '
    '<code>recaptchaRequired=true</code>、criteria 接口恒 409。'
    '而且 ICE Futures Europe 的官方规则 SECTION NNNN 通篇只有 '
    '"Contract Multiplier €2,500"，<b>没有面值</b>，常被引用的 EUR 1,000,000 是反推值。'
    '<br>② <b>即便拆开，名义额对利率衍生品本身就是误导性单位</b>：同样的名义额下，'
    '2 年期与 10 年期的 DV01 差 5 倍以上。正确的单位是 DV01 或久期加权名义额，'
    '而月度成交报表里没有久期字段 —— 那是另一个量级的工程。'
    '<br>⇒ 第②条与能不能拿到分合约张数无关，所以这两个常数<b>不会被补上</b>；'
    'ICE 的利率块只进增长口径（定基名义额的增长率与张数增长率恒等），不进水平值。'
    '复算脚本 <code>build/basefill/ice_enx2.py</code>。')
GAP_REASONS['ICE_STIR'] = (GAP_INST, _ICE_RATES_GAP)
GAP_REASONS['ICE_MLTIR'] = (GAP_INST, _ICE_RATES_GAP)
GAP_REASONS['MX_ETF_OPT'] = (
    GAP_TECH, GAP_REASONS['MX_EQUITY_OPT'][1]
    + '且那 940 个 symbol 里没有官方的「哪些是 ETF」标记，拆分还要再加一道人工判定。')


# ────────────────────────────── 通用零件 ──────────────────────────────
def mlab(p):
    """Period('2026-06') → 'Jun-26'（与 gsx.mlab / exchanges.py 一致）。"""
    return f'{MONTHS[p.month - 1]}-{p.year % 100:02d}'


def zh(p):
    return f'{p.year} 年 {p.month} 月'


def _z(v, dec):
    """把 -0.0 这类「四舍五入后其实是零」的值归零，否则会印出 '-0.0pp'。"""
    v = round(float(v), dec)
    return 0.0 if v == 0 else v


def num(v, dec=0):
    if v is None or not np.isfinite(v):
        return '—'
    return f'{v:,.{dec}f}'


def pct(v, dec=1):
    if v is None or not np.isfinite(v):
        return '—'
    return f'{_z(v, dec):+,.{dec}f}%'


def pp(v, dec=1):
    """比率类指标的差异一律 pp/bp（契约 §2：绝对值不足 1pp 时写 bp）。"""
    if v is None or not np.isfinite(v):
        return '—'
    if abs(_z(v, dec)) < 1:
        return f'{_z(v * 100, 0):+,.0f}bp'
    return f'{_z(v, dec):+.{dec}f}pp'


def L(a):
    """序列 → JSON 安全的 float 列表（NaN → None，线在缺口处断开而不是直连）。"""
    return [None if v is None or not np.isfinite(float(v)) else round(float(v), 6) for v in a]


def skip(msg, detail=()):
    """门槛没过 —— 打印原因，退出码 0。见模块 docstring 第 3 条。"""
    print(f'{TICKER}: 跳过，未达发布门槛 —— {msg}')
    for line in detail:
        print(f'  {line}')
    print('12 家总览页只在全部成员都能换算成定基名义额之后生成；'
          'monthly_run 下次例行跑会自动重试。')
    sys.exit(0)


def read_csv(name):
    """series/<name>.csv → 以**连续**月度 PeriodIndex 索引的 DataFrame（全列转数值）。

    reindex 成连续月：原始文件若中间缺月，pct_change(12) 会按**位置**移 12 行，
    算出来的「同比」其实跨了 13 个月而完全看不出来。
    """
    p = os.path.join(SERIES, f'{name}.csv')
    if not os.path.exists(p):
        return None
    d = pd.read_csv(p)
    if 'month' not in d.columns:
        raise SystemExit(f'series/{name}.csv 缺 month 列')
    d['month'] = pd.PeriodIndex(d['month'], freq='M')
    d = d.set_index('month').sort_index()
    d = d.apply(pd.to_numeric, errors='coerce')
    return d.reindex(pd.period_range(d.index[0], d.index[-1], freq='M'))


# ───────────────────── 换算：源列 → 规范单位 → 定基美元名义额 ─────────────────────
def leg_units(raw, key, leg):
    """一条腿的源列 → **规范单位/日**（张/日、股/日、本币元/日）。

    per='month' 的列要除以交易日列。除法一律用「同月的交易日」，不用平均值：
    一个 19 天的月和一个 23 天的月差 20%，那正好是本页要读的增长量级。
    """
    d = raw[key]
    if leg.col not in d.columns:
        return None, f'series/{key}.csv 缺列 {leg.col}'
    s = d[leg.col].astype(float) * leg.scale
    if leg.per == 'month':
        if leg.days not in d.columns:
            return None, f'series/{key}.csv 缺交易日列 {leg.days}'
        days = d[leg.days].astype(float)
        s = s.where(days > 0) / days.where(days > 0)
    elif leg.per != 'day':
        return None, f'腿 {leg.col} 的 per={leg.per!r} 非法'
    return s, None


def base_k(product, specs, fx):
    """product_id → 单位（张/股/本币元）的定基美元名义额，一个与月份无关的常数。

    本页全部是**流量**（日均成交量/成交额），故汇率一律取 basis='avg'
    （notional.FLOW_TO_FX_BASIS 里 per_day → avg）。存量口径（AUM、市值）不进本页。
    """
    return notional.base_notional_per_unit_usd(product, specs, fx, basis='avg')


def member_series(raw, key, specs, fx, kconst, idx, contract_only=False):
    """一家的定基名义额（美元/日）与张数（张/日），都截到 idx 窗口。

    某个月只要有一条腿缺值，整家该月作废（返回 NaN）—— 只加"还在的那几条腿"
    会在图上画出一次凭空的下跌，那是编出来的事实。
    """
    notion = pd.Series(0.0, index=idx)
    counts = pd.Series(0.0, index=idx)
    has_count = False
    for leg in LEGS[key]:
        s, err = leg_units(raw, key, leg)
        if err:
            raise SystemExit(f'{key}: {err}')            # 门槛检查已经放行过，这里再断就是真坏了
        s = s.reindex(idx)
        if leg.zero_before:
            # 该列上线之前按 0 计入，理由见 ZERO_WHY；上线之后的缺月**不补**，照常作废
            first = s.dropna()
            if not first.empty:
                s = s.copy()
                s[s.index < first.index[0]] = 0.0
        is_contract = specs[leg.product]['kind'] == 'contract'
        if contract_only and not is_contract:
            continue
        notion = notion + s * kconst[leg.product]
        if is_contract:
            counts = counts + s
            has_count = True
    if not has_count:
        # 这家一条合约腿都没有（纯金额口径）：张数与"仅合约腿的名义额"都不存在，
        # 一律给 NaN。留 0 会让它以「零增长」的身份混进那两张口径差图，那是假的。
        counts = pd.Series(np.nan, index=idx)
        if contract_only:
            notion = pd.Series(np.nan, index=idx)
    return notion, counts


def contract_products(key, specs):
    """这家在本页配了几个**不同的**合约产品（product_id）。

    口径差那两张图的差值＝「同一批合约腿的张数同比 − 定基名义额同比」。名义额是张数各乘
    一个产品常数再相加，所以：
      · 只有 1 个合约产品时，两条序列只差**同一个常数**，同比在数学上恒等，差值恒为 0；
      · ≥2 个时，差值 = 品种结构在这一年里往大合约还是小合约迁移了，才是实测量。
    本页有四家（MIAX / HKEX / JPX / SGX）落在前一种：它们的官方披露只给一个"衍生品合计"，
    我们也只给了一个篮子产品。那个 0 是**构造出来的**，画进图里会被读成"这家没有合约变小"。
    """
    return {lg.product for lg in LEGS[key] if specs[lg.product]['kind'] == 'contract'}


def fx_only_legs(key, specs):
    """这家有哪几条腿是 kind='notional' —— 即 notional.py 说的 deflator='fx_only'。

    notional.py 的三源表（那里是本仓对这件事的唯一定义）：
      · kind='contract' / 'share' → 价格项是**基期常数**，完全定基；
      · kind='notional'           → 源列本来就是本币成交额，multiplier 与 base_price_local
                                     恒为 1，我们拿不到股数所以剥不出价格项 ⇒ **只锁了汇率，
                                     价格是当期**。
    所以这类腿的增长里含标的涨跌，「增长率＝张数增长率」对它们不成立。本页把两类腿加在
    同一个总额里（HKEX / SGX 甚至只有这一类），注 1 因此必须按腿分别表述，不能一句话
    盖住全页 —— 这正是 pools.py:49 与 notional.py:31-32 立的规矩（图注必须写明「已剔汇率、
    未剔标的涨跌」），本页此前漏接。
    """
    return [lg for lg in LEGS[key] if specs[lg.product]['kind'] == 'notional']


def fx_only_weight(BLK, kconst, specs, months):
    """每家在 months 各月里，来自 fx_only 腿的定基名义额占比（0–1）。

    只有常数齐备的家算得出占比（分母要完整）；缺常数的家返回 None，但**是否含 fx_only 腿**
    与占比无关，那个由 fx_only_legs() 单独回答，缺常数也照样点名。
    """
    out = {}
    for k in BLK:
        if any(p not in kconst for p in BLK[k]):
            out[k] = None
            continue
        tot = sum(BLK[k][p] * kconst[p] for p in BLK[k])
        num_parts = [BLK[k][p] * kconst[p] for p in BLK[k]
                     if specs[p]['kind'] == 'notional']
        if not num_parts:
            out[k] = tuple(0.0 for _ in months)
            continue
        num = sum(num_parts)
        out[k] = tuple(
            float(num[m] / tot[m])
            if (m in tot.index and np.isfinite(tot[m]) and tot[m]) else float('nan')
            for m in months)
    return out


# ────────────────────────── 门槛：成员是否都能换算 ──────────────────────────
def readiness(raw, specs, fx):
    """逐腿检查「列在不在、基期价有没有、基期窗口内有没有数」，返回 (报告行, 阻塞项)。"""
    lines, blocked, kconst = [], [], {}
    for key, disp, _zh in MEMBERS:
        d = raw[key]
        if d is None:
            blocked.append((key, '—', f'缺 series/{key}.csv'))
            lines.append(f'  {disp:16s} ✗ 缺 series/{key}.csv')
            continue
        ok, bad = [], []
        for leg in LEGS[key]:
            s, err = leg_units(raw, key, leg)
            if err:
                bad.append(f'{leg.col}（{err}）')
                blocked.append((key, leg.product, err))
                continue
            valid = s.dropna()
            if valid.empty:
                bad.append(f'{leg.col}（整列无有效值）')
                blocked.append((key, leg.product, f'{leg.col} 整列无有效值'))
                continue
            if valid.index[0] > BASE and not leg.zero_before:
                why = (f'{leg.col} 首个有效月 {valid.index[0]} 晚于基期 {BASE}，'
                       f'无法定基')
                bad.append(f'{leg.col}（首月 {valid.index[0]} > 基期）')
                blocked.append((key, leg.product, why))
                continue
            if leg.product in kconst:
                ok.append(leg.col)
                continue
            try:
                kconst[leg.product] = base_k(leg.product, specs, fx)
                ok.append(leg.col)
            except notional.NotionalError as e:
                one = str(e).split('。')[0]
                bad.append(f'{leg.col} → {leg.product}（{one}）')
                blocked.append((key, leg.product, one))
        mark = '✓' if not bad else '✗'
        lines.append(f'  {disp:16s} {mark} 可换算 {len(ok)}/{len(LEGS[key])} 腿'
                     + ('' if not bad else '；阻塞：' + '、'.join(bad)))
    return lines, blocked, kconst


# ────────────────────────────── 派生计算 ──────────────────────────────
def yoy(s):
    """**单月**同比（%）。先在完整历史上算，再由调用方截窗口。

    ⚠ 2026-08-07 起本页**没有任何对外读数走它** —— 它只留给 volcmp() 做口径对照，
    用来算「换成滚动口径到底改了多少」。要画给读者看的同比一律用 ttm_yoy()。
    """
    return (s.pct_change(12) * 100)


def ttm_yoy(s):
    """**12 个月滚动合计的同比**（%）—— 本页全部对外同比读数的口径。

    先滚动求 12 个月的和，再对这条滚动序列取同比：分子分母各覆盖 12 个整月，
    任何一次到期日错位、假期错月、单月极端行情都只占 1/12 的权重。

    **不乘交易日数**：本页所有腿在 leg_units() 里已经统一除成日均，是本文件的既定做法；
    12 个日均值相加 = 12 × 滚动平均日均值，同比是比值、分子分母同权，交易日不出现。
    乘回去等于把日历差异重新塞进增长，而且 12 家的交易日列名各不相同、两家干脆没有。

    紧界不受影响：滚动合计 Σ_i N(t−i) = Σ_p k_p·[Σ_i S_p(t−i)]，仍是各产品块滚动合计
    的同一组常数线性组合 ⇒ 其同比依旧是各块同比的加权平均（权重非负、和为 1），
    hull() 给的 min/max 依旧是紧界。
    """
    return (s.rolling(TTM).sum().pct_change(12) * 100)


def volcmp(s, idx):
    """同一条序列在两个同比口径下的对照量 —— 图注与自检行里的每个数字都从这里来。

    三个量各答一个问题：整体有多抖（逐月标准差）、最坏的一次一月之内翻天有多大
    （相邻月最大跳变）、以及最有杀伤力的一个：有多少个月两个口径**符号相反**
    （前两个只是噪音大，这一个是结论反了）。
    """
    m, t = yoy(s).reindex(idx), ttm_yoy(s).reindex(idx)
    both = pd.DataFrame({'m': m, 't': t}).dropna()
    if both.empty:
        return None
    opp = both[(both['m'] * both['t']) < 0]
    jm, jt = m.diff().abs(), t.diff().abs()
    return {
        'm_sd': float(m.dropna().std()), 't_sd': float(t.dropna().std()),
        'm_jump': float(jm.max()), 'm_jump_at': jm.idxmax(),
        't_jump': float(jt.max()), 't_jump_at': jt.idxmax(),
        'n_opp': len(opp), 'n_both': len(both),
        'opp': [(p, float(r['m']), float(r['t'])) for p, r in opp.iterrows()],
        'cur_m': float(m.iloc[-1]), 'cur_t': float(t.iloc[-1]),
    }


def annual_yoy(s, year):
    """年度同比（%），**同月对同月**。

    2026 只到 6 月时，拿「1-6 月合计」比「上年 1-6 月合计」，不比上年全年 ——
    比全年会砸出一个 −50% 的假坑，而线上没有任何提示说这一格不可比。
    """
    cur = s[[p for p in s.index if p.year == year]].dropna()
    if cur.empty:
        return np.nan
    months = sorted({p.month for p in cur.index})
    prv = s[[p for p in s.index if p.year == year - 1 and p.month in months]].dropna()
    if len(prv) != len(months) or len(cur) != len(months):
        return np.nan
    a, b = float(cur.sum()), float(prv.sum())
    return (a / b - 1) * 100 if b else np.nan


# JPX 的「同一批合约、两个单位」证据列。**只取金融衍生品（股指 + 利率），不含商品**：
# 旧 TOCOM 2020-07-27 才迁入 OSE，含商品的合计在那之前是 pro-forma
# （series/jpx.csv 有 cmdty_proforma 标记列），跨 2020-07 读会把一次并购读成成交量变化。
# 原始张数一侧没有现成的「金融合计」列，用两个大类的 raw 列相加 —— 它与当量列
# adv_deriv_fin_lgeq_kcontracts 的口径边界（股指关联 + 国债利率关联）逐字对应。
JPX_RAW_COLS = ('adv_deriv_index_raw_kcontracts', 'adv_deriv_rates_raw_kcontracts')
JPX_LGEQ_COL = 'adv_deriv_fin_lgeq_kcontracts'
# 当量列的来历必须跟着数字走：它**不是** JPX 逐月发布的字段。
JPX_LGEQ_PROV = (
    '「大合约当量」列由 <code>fetch/jpx.py</code> 按 JPX IR 脚注的官方折算系数自建'
    '（日経225mini ÷10、日経225マイクロ ÷100、ミニTOPIX ÷10、ミニJGB ÷10 等），'
    '并用 IR 的季度 Financial Derivatives 合计校准到 ~2% 以内'
    '（docs/verify/verify_jpx.md §N2）。<b>JPX 并不逐月发布这一列</b> —— '
    '折算系数是官方的，逐月序列是本仓算的，两件事不能混为一谈。')


def jpx_unit_evidence(raw, idx):
    """JPX 金融衍生品：原始张数 vs 大合约当量，截到本页共同窗口 idx。

    这是本页唯一一处「同一批合约被两个单位量了两遍」的直接观测，也是 JPX 那张图的全部内容。
    数字全部现算，一个都不写死 —— 写死的话下个月序列一变，图注就成了假话。

    返回 dict 或 None（列缺、窗口内有洞、基期为 0 都返回 None，由调用方决定要不要画）。
    累计口径用**首尾各 12 个月的均值**比，不用单月比单月：单月会把一次结算日错位读成趋势。
    同理，raw_yoy / lgeq_yoy 也是 **12 个月滚动合计的同比**（与全页同口径），
    不是单月同比 —— 这两个数会被抬头与图注引用，挂单月口径等于在全页里插一个异类。
    """
    d = raw.get('jpx')
    if d is None:
        return None
    if any(c not in d.columns for c in JPX_RAW_COLS) or JPX_LGEQ_COL not in d.columns:
        return None
    a = sum(d[c] for c in JPX_RAW_COLS).reindex(idx)
    b = d[JPX_LGEQ_COL].reindex(idx)
    if not np.isfinite(a.values.astype(float)).all() or not np.isfinite(b.values.astype(float)).all():
        return None                       # 窗口内有洞就整张图不画，绝不带洞上线
    a0, b0 = float(a[idx[0]]), float(b[idx[0]])
    if not (a0 > 0 and b0 > 0):
        return None
    cur = idx[-1]
    w = 12
    # 同比走滚动合计口径（与全页一致）；窗口不足 24 个月时 ttm_yoy 给 NaN，整张图不画
    ry_s, ly_s = ttm_yoy(a), ttm_yoy(b)
    ry, ly = float(ry_s[cur]), float(ly_s[cur])
    if not (np.isfinite(ry) and np.isfinite(ly)):
        return None
    # 单月口径的同一对读数：只用来在图注里说明「为什么不用它」，不进任何曲线
    mry, mly = float(yoy(a)[cur]), float(yoy(b)[cur])
    rc = (float(a.iloc[-w:].mean()) / float(a.iloc[:w].mean()) - 1) * 100
    lc = (float(b.iloc[-w:].mean()) / float(b.iloc[:w].mean()) - 1) * 100
    return {
        'raw_idx': a / a0 * 100, 'lgeq_idx': b / b0 * 100,
        'cur': cur, 'raw_yoy': ry, 'lgeq_yoy': ly, 'gap_pp': ry - ly,
        'raw_yoy_m': mry, 'lgeq_yoy_m': mly, 'gap_pp_m': mry - mly,
        'raw_cum': rc, 'lgeq_cum': lc, 'opposite': rc * lc < 0,
        'raw_end': float(a[cur]) / a0 * 100, 'lgeq_end': float(b[cur]) / b0 * 100,
        'ratio0': a0 / b0, 'ratio1': float(a[cur]) / float(b[cur]),
        'span': f'{mlab(idx[0])}–{mlab(idx[w - 1])} 均值 → 最近 12 个月均值',
    }


def ser_of(s):
    """pandas Series → pctile.py 吃的「按月升序、缺失为 None」的 float 列表。"""
    return [None if v is None or not np.isfinite(float(v)) else float(v) for v in s.values]


def cls_of(v):
    if v is None or not np.isfinite(v):
        return ''
    return 'pos' if v > 0 else ('neg' if v < 0 else '')


# ─────────────────────── 产品块、界、以及缺常数的降级口径 ───────────────────────
def block_series(raw, key, idx):
    """product_id → 这家该产品的规范单位/日（同一产品的多条腿先相加），截到 idx。

    「产品块」是本页做界的最小单位：同一个 product_id 只有一个基期常数，
    所以**块内部**的权重是已知的（就是各腿自己的量），
    只有**块与块之间**的权重才依赖那个可能填不出来的常数。
    """
    out = {}
    for leg in LEGS[key]:
        s, err = leg_units(raw, key, leg)
        if err:
            raise SystemExit(f'{key}: {err}')            # 就绪度已经放行过，这里再断就是真坏了
        s = s.reindex(idx)
        if leg.zero_before:
            first = s.dropna()
            if not first.empty:
                s = s.copy()
                s[s.index < first.index[0]] = 0.0
        out[leg.product] = s if leg.product not in out else out[leg.product] + s
    return out


def hull_parts(blocks, kconst):
    """一家 → [(产品 id 元组, 序列, 是否已定价)]：已定价的块先按已知常数合成一块。

    定基名义额 N(t) = Σ_p k_p · S_p(t)。已定价的那些 p 之间权重已知，可以先合成；
    每个未定价的 p 各自成一块，其权重 k_p 未知但**非负**。
    返回的块数 = 1 时，该家的任何比值都与未知常数无关（常数被完全约掉），是精确值。
    """
    priced = [p for p in blocks if p in kconst]
    unpriced = [p for p in blocks if p not in kconst]
    parts = []
    if priced:
        parts.append((tuple(priced), sum(blocks[p] * kconst[p] for p in priced), True))
    for p in unpriced:
        parts.append(((p,), blocks[p], False))
    return parts


def hull(parts, f):
    """f: Series → Series（指数 / 同比 / 环比…）。返回 (点值 or None, 下界, 上界)。

    只有一块时 f(块) 就是精确值。多块时任何这类比值都是各块同一比值的**加权平均**
    （权重非负、和为 1，见模块 docstring 的中位分数不等式）⇒ 必落在 min / max 之间，
    且 k 取极端值时两端都能取到 —— 这是**紧界**，不是保守放大。
    skipna=False：任何一块缺值，界本身就是未知的，不许拿剩下几块凑一个假界出来。
    """
    vals = [f(s) for _p, s, _ok in parts]
    m = pd.concat(vals, axis=1)
    return (vals[0] if len(vals) == 1 else None), m.min(axis=1, skipna=False), \
        m.max(axis=1, skipna=False)


def f_index(s):
    """基期 = 100 的指数。基期值为 0 / 无效时整条作废（硬除会得到 inf）。"""
    b = float(s[BASE]) if BASE in s.index else np.nan
    if not np.isfinite(b) or b == 0:
        return pd.Series(np.nan, index=s.index, dtype=float)
    return s / b * 100


def f_mom(s):
    return s.pct_change(1) * 100


def part_label(key, prods):
    """块 → 人话名字。腿名拼起来太长时退成「首腿 等 N 腿」。"""
    labs = [lg.label for lg in LEGS[key] if lg.product in prods]
    j = '＋'.join(labs)
    return j if len(j) <= 14 else f'{labs[0]} 等 {len(labs)} 腿'


def rng_num(lo, hi, dec=0):
    """区间 → 展示串。上下界重合（本来就是精确值）时只印一个数。"""
    if lo is None or hi is None or not np.isfinite(lo) or not np.isfinite(hi):
        return '—'
    if abs(hi - lo) < 0.5 * 10 ** (-dec):
        return num(lo, dec)
    return f'{num(lo, dec)}–{num(hi, dec)}'


def rng_pct(lo, hi, dec=1):
    if lo is None or hi is None or not np.isfinite(lo) or not np.isfinite(hi):
        return '—'
    if abs(hi - lo) < 0.5 * 10 ** (-dec):
        return pct(lo, dec)
    return f'{pct(lo, dec)}–{pct(hi, dec)}'


def load_notional_source():
    """series/contract_specs.csv 的 notional_source 列（notional.load_specs 不保留它）。

    三档可信度：official_notional（官方直发名义额）> reconstructed（按官方乘数与
    官方价格重算）> definitional（面值本身就是定义，如 SOFR 的 100 万美元）。
    页面要报这个分布，因为「常数齐备」不等于「常数一样硬」。
    """
    import csv as _csv
    p = os.path.join(SERIES, 'contract_specs.csv')
    with open(p, newline='', encoding='utf-8') as f:
        return {r['product_id'].strip(): (r.get('notional_source') or '').strip()
                for r in _csv.DictReader(f)}


# ────────────────────────────── payload 组装 ──────────────────────────────
def build_payload(raw, specs, fx, kconst, source_date):
    """全部数值在这里算完；页面只画不算。

    kconst 只含**填得出基期常数**的 product_id。缺的那些不再卡整页，
    而是按模块 docstring 的降级规则：增长类图给点值或紧界，水平值类图直接不画那几家。
    """
    nsrc = load_notional_source()

    # ── 共同窗口（不需要任何常数：某月只要有一条腿缺值，这家该月就作废）──
    starts, lasts = {}, {}
    for key in MEM_KEYS:
        full = pd.period_range(min(raw[key].index[0], BASE), raw[key].index[-1], freq='M')
        v = sum(block_series(raw, key, full).values()).dropna()
        if v.empty:
            skip(f'{DISP[key]} 的源列整条为空')
        starts[key], lasts[key] = v.index[0], v.index[-1]

    late = [k for k in MEM_KEYS if starts[k] > BASE]
    if late:
        skip('有成员在基期 %s 没有完整数据：%s' % (BASE, '、'.join(DISP[k] for k in late)),
             [f'{DISP[k]} 最早完整月 = {starts[k]}' for k in late])

    LATEST = min(lasts.values())
    IDX = pd.period_range(BASE, LATEST, freq='M')
    if len(IDX) < MIN_COMMON:
        skip(f'共同历史只有 {len(IDX)} 个月（{mlab(BASE)} – {mlab(LATEST)}），'
             f'不足 {MIN_COMMON} 个月')

    LAG = [DISP[k] for k in MEM_KEYS if lasts[k] == LATEST]
    AHEAD = [(DISP[k], lasts[k]) for k in MEM_KEYS if lasts[k] > LATEST]

    # ── 产品块（多取 24 个月，好让共同窗口首月就有滚动同比）──
    # 为什么是 24 不是 12：滚动同比要「本月往前 12 个月的合计 ÷ 去年同月往前 12 个月的合计」，
    # 最早那个读数要用到 t−23 的原始月。只多取 12 个月的话，共同窗口前 12 个月的滚动同比
    # 会整段变空 —— 那不是数据缺口，是取数窗口开小了造出来的假缺口。
    # 各家 CSV 若本来就没有那么早的历史（HKEX 就是自 BASE 起），reindex 出来是 NaN，
    # 图上照常留空并在图注点名，绝不用近似值填。
    full_idx = pd.period_range(BASE - 2 * TTM, LATEST, freq='M')
    BLK = {}
    for key in MEM_KEYS:
        span = pd.period_range(min(raw[key].index[0], BASE - 2 * TTM),
                               raw[key].index[-1], freq='M')
        BLK[key] = {p: s.reindex(full_idx) for p, s in block_series(raw, key, span).items()}

    # ── 失败要响：共同窗口内部有洞 = 源数据坏了，不是「常数没齐」──────────────
    # 尾部参差由 LATEST = min(各家最后一个完整月) 处理掉了，剩下的洞只可能在中间。
    # 中间的洞会让线在图上断开、让年度同比少算一个月，两者都不报错也看不出来。
    # 这一类必须抛出去让 monthly_run 记一条真 FAIL（与 build/exchanges.py:240-243 同规矩），
    # 不能走 skip —— skip 的语义是"还没齐，下次再来"，会把源数据损坏悄悄拖成常态。
    holes = {}
    for k in MEM_KEYS:
        tot = sum(BLK[k].values())
        bad = [str(p) for p in IDX if not np.isfinite(tot.get(p, np.nan))]
        if bad:
            holes[k] = bad
    if holes:
        raise SystemExit(
            '共同窗口 %s–%s 内这些成员的源列有洞：%s。'
            '洞的成因只有一个：该家某条腿在这些月缺值（成员整月作废是本页的既定行为）。'
            '请先修 series/*.csv 或调整该家的腿，不要靠画一条断线上线。'
            % (mlab(BASE), mlab(LATEST),
               '；'.join(f'{DISP[k]} {len(v)} 个月（最早 {v[0]}）' for k, v in holes.items())))

    # ── 覆盖度分档：这四个 dict 是全页降级逻辑的唯一依据 ──
    UNPRICED = {k: [p for p in BLK[k] if p not in kconst] for k in MEM_KEYS}
    PARTS = {k: hull_parts(BLK[k], kconst) for k in MEM_KEYS}
    LEVEL_OK = {k: not UNPRICED[k] for k in MEM_KEYS}          # 水平值可算（常数齐备）
    EXACT = {k: len(PARTS[k]) == 1 for k in MEM_KEYS}          # 增长精确（常数被约掉或已知）
    lvl_keys = [k for k in MEM_KEYS if LEVEL_OK[k]]
    grow_keys = [k for k in MEM_KEYS if EXACT[k]]
    band_keys = [k for k in MEM_KEYS if not EXACT[k]]
    if not grow_keys:
        skip('没有任何一家的增长口径是精确的（每家都有 ≥2 个产品块且含未定价块），'
             '本页连一条可信的指数线都画不出来')

    BN = 1e9   # 美元 → US$bn
    lvl = {k: (PARTS[k][0][1] / BN).reindex(IDX) for k in lvl_keys}
    # 不变式：走产品块合成出来的水平值必须与老路径 member_series 逐位相同。
    # 这两条路一旦分叉，页面上看不出来（只是某家的柱高一截），所以在这里当场对。
    for k in lvl_keys:
        ref = (member_series(raw, k, specs, fx, kconst,
                             pd.period_range(BASE, LATEST, freq='M'))[0] / BN)
        d = (lvl[k] - ref).abs().max()
        if not np.isfinite(d) or d > 1e-6:
            raise SystemExit(f'{DISP[k]}：产品块合成的定基名义额与 member_series 不一致'
                             f'（最大差 {d}），两条换算路径已分叉，先修再发页。')

    # ── 增长：点值 + 紧界（指数 / 滚动同比 / 环比 / 单月同比）──
    # YOY* 是**单月**口径，2026-08-07 起不进任何对外读数，只喂 volcmp 的口径对照与自检；
    # 页面上的 y/y 一律取 TYOY*（12 个月滚动合计）。
    IDXP, IDXLO, IDXHI = {}, {}, {}
    YOYP, YOYLO, YOYHI = {}, {}, {}
    TYOYP, TYOYLO, TYOYHI = {}, {}, {}
    MOMP, MOMLO, MOMHI = {}, {}, {}
    for k in MEM_KEYS:
        for f, (P, LO, HI) in ((f_index, (IDXP, IDXLO, IDXHI)),
                               (yoy, (YOYP, YOYLO, YOYHI)),
                               (ttm_yoy, (TYOYP, TYOYLO, TYOYHI)),
                               (f_mom, (MOMP, MOMLO, MOMHI))):
            p_, lo_, hi_ = hull(PARTS[k], f)
            P[k] = None if p_ is None else p_.reindex(IDX)
            LO[k], HI[k] = lo_.reindex(IDX), hi_.reindex(IDX)

    # ── 把全页赖以成立的那条数学断言，每跑一次就拿真实数据验一遍 ──
    # 断言：加权平均（权重非负、和为 1）必落在各分量的 min / max 之间。
    # 常数齐备的家是唯一能双向验证的样本：它的精确值算得出来，同时又可以**假装**
    # 每个产品的常数都未知、按 hull 做一遍界。精确值必须落在那个界里。
    # 落不进去 = hull 的实现错了（轴取反、skipna 漏了、块拆错），而那种错在页面上
    # 只会表现为"区间画得有点宽"，没人看得出来 —— 所以宁可在这里炸掉。
    for k in lvl_keys:
        if len(BLK[k]) < 2:
            continue
        solo = [((p,), s, False) for p, s in BLK[k].items()]
        # 滚动同比也必须验：它是本页对外的那个口径，而「滚动合计仍是同一组常数的
        # 线性组合 ⇒ 紧界不变」这条推导只在纸上成立过一次，每跑一次就拿真数据验一次。
        for fname, f, P in (('指数', f_index, IDXP), ('单月同比', yoy, YOYP),
                            (f'{TTM} 个月滚动合计同比', ttm_yoy, TYOYP)):
            _pt, blo, bhi = hull(solo, f)
            blo, bhi = blo.reindex(IDX), bhi.reindex(IDX)
            v = P[k]
            bad = []
            for p in IDX:
                if not (np.isfinite(v[p]) and np.isfinite(blo[p]) and np.isfinite(bhi[p])):
                    continue
                tol = 1e-9 * max(1.0, abs(float(bhi[p])), abs(float(blo[p])))
                if not (float(blo[p]) - tol <= float(v[p]) <= float(bhi[p]) + tol):
                    bad.append(f'{p} 精确值 {float(v[p]):.6f} ∉ '
                               f'[{float(blo[p]):.6f}, {float(bhi[p]):.6f}]')
            if bad:
                raise SystemExit(
                    f'{DISP[k]} 的{fname}落在产品块的界之外：{bad[:4]}（共 {len(bad)} 处）。'
                    '这说明 hull() 的实现与「加权平均必落在分量 min/max 之间」这条断言'
                    '已经脱钩 —— 全页 5 家的区间口径都建立在它上面，先修 hull 再发页。')

    CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12
    XL_LONG = [mlab(p) for p in IDX]
    XL13 = [mlab(p) for p in IDX[-TBL_MONTHS:]]

    # 基期为 0 / 无效 ⇒ 指数化整条作废。这不是"缺一个点"，是整条线的分母没了。
    bad_base = [DISP[k] for k in MEM_KEYS if not np.isfinite(IDXHI[k][CUR])]
    if bad_base:
        skip(f'这些成员在基期 {mlab(BASE)} 的量为 0 或无效，无法指数化：'
             + '、'.join(bad_base))

    # ── 张数口径 vs 定基名义额口径：只有「合约块全部已定价且 ≥2 个」才是实测量 ──
    con_prod = {k: contract_products(k, specs) for k in MEM_KEYS}
    CNT = {}
    for k in MEM_KEYS:
        cs = [s for p, s in BLK[k].items() if specs[p]['kind'] == 'contract']
        CNT[k] = sum(cs) if cs else pd.Series(np.nan, index=full_idx)
    mix_keys = [k for k in MEM_KEYS
                if len(con_prod[k]) >= 2 and not (con_prod[k] & set(UNPRICED[k]))]
    flat_keys = [k for k in MEM_KEYS if len(con_prod[k]) == 1]
    gapblock_keys = [k for k in MEM_KEYS
                     if len(con_prod[k]) >= 2 and (con_prod[k] & set(UNPRICED[k]))]
    nocontract_keys = [k for k in MEM_KEYS if not con_prod[k]]
    # 差值两侧都走滚动同比 —— 两侧必须同口径，混口径算出来的差不是「合约变小」而是噪音差。
    # m_gap 是同一批合约在**单月**口径下的差值，只进图注（量化「改口径改了多少」），不画柱。
    gap, m_gap = {}, {}
    for k in mix_keys:
        n_con, c_con = member_series(raw, k, specs, fx, kconst, full_idx, contract_only=True)
        gap[k] = (ttm_yoy(c_con) - ttm_yoy(n_con)).reindex(IDX)
        m_gap[k] = (yoy(c_con) - yoy(n_con)).reindex(IDX)
    # 结构性 0 必须真的是 0；不是就说明 gap 的两条腿已经不是同一批合约了
    for k in flat_keys:
        if con_prod[k] & set(UNPRICED[k]):
            continue                                   # 常数都没有，本来就算不出来
        n_con, c_con = member_series(raw, k, specs, fx, kconst, full_idx, contract_only=True)
        g = (ttm_yoy(c_con) - ttm_yoy(n_con)).reindex(IDX)
        bad = [str(p) for p in IDX if np.isfinite(g[p]) and abs(float(g[p])) > 1e-6]
        if bad:
            raise SystemExit(
                f'{DISP[k]} 只配了 1 个合约产品，两个口径的同比在数学上必须恒等，'
                f'但这些月差值不为 0：{bad[:6]}（共 {len(bad)} 个月）。'
                'gap 的两条腿已经不是同一批合约了，先修算法再发页。')

    jp = jpx_unit_evidence(raw, IDX)

    # ── 口径对照：单月同比 vs 滚动合计同比，逐**产品块**实测 ──
    # 为什么按产品块而不是按家：块自身的同比是精确的（那个常数在比值里被完全约掉），
    # 而缺常数的家合起来只有区间，区间谈不上「符号相反」。按块测，12 家一个不落，
    # 每个读数都是实测量，没有一个是构造出来的。
    VC = {}
    for k in MEM_KEYS:
        for prods, s, _ok in PARTS[k]:
            v = volcmp(s, IDX)
            if v is not None:
                # 整家只有一块时那一块就是这家本身，名字不必再挂块名
                VC[DISP[k] if EXACT[k] else f'{DISP[k]}·{part_label(k, set(prods))}'] = v
    if not VC:
        skip('没有任何一条序列能同时算出单月同比与滚动同比，无法给出口径对照')
    _sd_cut = sorted((v['t_sd'] / v['m_sd']) for v in VC.values() if v['m_sd'] > 0)
    _sd_med = _sd_cut[len(_sd_cut) // 2]
    _opp_tot = sum(v['n_opp'] for v in VC.values())
    _obs_tot = sum(v['n_both'] for v in VC.values())
    _worst_jump = max(VC.items(), key=lambda kv: kv[1]['m_jump'])
    _worst_opp = max(VC.items(), key=lambda kv: kv[1]['n_opp'])

    def flips(name, n=2):
        """某条序列最刺眼的 n 个「符号相反月」—— 按两个读数的距离排，最远的最有说服力。"""
        top = sorted(VC[name]['opp'], key=lambda x: -abs(x[1] - x[2]))[:n]
        return '、'.join(f'{mlab(p)}（单月 {pct(m)}，滚动 {pct(t)}）' for p, m, t in top)

    WHY_TTM = (
        f'<b>为什么不用单月同比。</b>单月同比 = 本月 ÷ 去年同月 − 1，分子分母各只有一个月，'
        '一次到期日错位、一次假期错月、去年同月的一次极端行情，都会整个吃进这一个读数。'
        f'本页拿自己的 {len(VC)} 条产品块序列在 {mlab(IDX[0])}–{mlab(LATEST)} 上实测'
        f'（现算，不写死）：<b>逐月标准差</b>换成滚动口径后中位数降到原来的 '
        f'{_sd_med * 100:.0f}%；<b>单月口径相邻月最大跳变</b> '
        f'{_worst_jump[1]["m_jump"]:.1f}pp（{_worst_jump[0]}，'
        f'{mlab(_worst_jump[1]["m_jump_at"])}），同一条序列滚动口径只有 '
        f'{_worst_jump[1]["t_jump"]:.1f}pp；最要命的是<b>符号相反</b> —— '
        f'{_obs_tot} 个「序列 × 月」观测里有 <b>{_opp_tot} 个</b>两个口径一正一负，'
        f'最严重的是 {_worst_opp[0]}（{_worst_opp[1]["n_opp"]}/'
        f'{_worst_opp[1]["n_both"]} 个月），例如 {flips(_worst_opp[0], 3)}。'
        '同一条序列、同一个月，一个口径说在涨、另一个说在跌，'
        '图上讲的是相反的故事，所以本页的同比一律改成滚动合计口径。'
    )
    TTM_UNIT_NOTE = (
        f'<b>滚动合计怎么算：{TTM} 个月的日均值直接相加，不乘交易日数。</b>'
        '本页所有腿在 <code>leg_units()</code> 里已经统一除成日均'
        '（per=\'month\' 的列除以当月交易日），这是本文件的既定做法，不另起一套；'
        f'{TTM} 个日均值相加 = {TTM} × 滚动平均日均值，同比是比值、分子分母同权，'
        '交易日在里面根本不出现。再乘回去等于把「今年这 12 个月比去年多两个交易日」'
        '这类日历差异重新塞进增长，而且 12 家的交易日列名各不相同、'
        '<code>series/cboe.csv</code> 与 <code>series/hkex.csv</code> 干脆没有这一列。'
    )
    TTM_BASIS = (
        f'<b>口径 = {TTM} 个月滚动合计的同比</b>（本月往前 {TTM} 个月的合计 ÷ '
        f'去年同月往前 {TTM} 个月的合计 − 1），不是单月同比。')

    # ── 缺常数的清单（页面到处要用）──
    gap_prods = sorted({p for k in MEM_KEYS for p in UNPRICED[k]})
    unknown = [p for p in gap_prods if p not in GAP_REASONS]
    if unknown:
        raise SystemExit(
            f'这些 product_id 缺基期常数但 GAP_REASONS 里没有登记原因：{unknown}。'
            '页面必须逐个说明「制度性缺失」还是「技术性未取到」—— '
            '把原因写进 GAP_REASONS 再跑，不许让读者看到一个没有解释的空缺。')
    prod_users = {p: [DISP[k] for k in MEM_KEYS if p in UNPRICED[k]] for p in gap_prods}
    inst_prods = [p for p in gap_prods if GAP_REASONS[p][0] == GAP_INST]
    tech_prods = [p for p in gap_prods if GAP_REASONS[p][0] == GAP_TECH]

    def gap_html(prods):
        return ''.join(
            f'<li><b>{p}</b>（影响 {"、".join(prod_users[p])}）：{GAP_REASONS[p][1]}</li>'
            for p in prods)

    # 缺口清单：常数补齐的那天 gap_prods 为空，这段整个消失（而不是留下一串空 <ul>）。
    # 区间跨 0 的家：连「同比是正是负」都由那个未知常数决定，不由数据决定。
    # 这是缺常数造成的最强一种限制，Exhibit 4 的图注要单独点名。
    straddle = [DISP[k] for k in band_keys
                if float(TYOYLO[k][CUR]) < 0 <= float(TYOYHI[k][CUR])]

    gap_note = ''
    if gap_prods:
        gap_note = (
            f'本页 {len(gap_prods)} 个 product_id 填不出 {mlab(BASE)} 基期常数，'
            f'因此 <b>{"、".join(DISP[k] for k in band_keys)}</b> 没有水平值。'
            f'两类缺口对读者的意义完全不同，页面必须分开写：<ul>'
            + (f'<li><b>{GAP_KIND_ZH[GAP_INST]}</b></li>{gap_html(inst_prods)}'
               if inst_prods else '')
            + (f'<li><b>{GAP_KIND_ZH[GAP_TECH]}</b></li>{gap_html(tech_prods)}'
               if tech_prods else '')
            + '</ul>')

    ex = []

    # ── Exhibit 2：指数化折线（只画增长口径精确的家）──
    # 必须单画的是「增长精确但没有水平值」的家（常数被完全约掉的那种）——
    # 它们没有美元水平值，压根没法并进「其他 N 家合计」那条线里。
    must = [k for k in grow_keys if not LEVEL_OK[k]]
    pool = sorted([k for k in grow_keys if LEVEL_OK[k]], key=lambda k: -float(lvl[k][CUR]))
    draw = must + pool[:max(0, TOP_N - len(must))]
    rest = [k for k in pool if k not in draw]
    if len(draw) + (1 if rest else 0) > len(LINE_COLORS):
        skip(f'指数化折线要画 {len(draw)} 条单线 + {"1" if rest else "0"} 条合计，'
             f'超过数据色上限 {len(LINE_COLORS)}')
    series2 = []
    for i, k in enumerate(draw):
        tag = (f'（{lvl[k][CUR]:,.0f}）' if LEVEL_OK[k] else '（水平值缺常数）')
        series2.append({'name': f'{DISP[k]}{tag}', 'color': LINE_COLORS[i],
                        'values': L(IDXP[k].values)})
    if rest:
        other_lvl = sum(lvl[k] for k in rest)
        series2.append({'name': f'其他 {len(rest)} 家合计（{other_lvl[CUR]:,.0f}）',
                        'color': LINE_COLORS[len(draw)],
                        'values': L((other_lvl / float(other_lvl[BASE]) * 100).values)})
    ex.append({
        'n': 2, 'kind': 'lines_endlabels', 'full': True, 'height': 380,
        'fmt': 'f0', 'yfmt': 'f0', 'xlabels': XL_LONG, 'xstep': 6, 'xrot': 90,
        'title': f'Constant-basis notional, rebased to {mlab(BASE)} = 100 '
                 f'— exchanges whose growth needs no unknown constant',
        'ylab': f'index, {mlab(BASE)} = 100',
        'series': series2,
        'src_extra': ('Constant-basis notional = contracts × multiplier × Jan-19 price × Jan-19 FX. '
                      'Price and FX terms are constants, so every line\'s growth equals the growth '
                      'of its own volume — index levels and currency moves are excluded by '
                      'construction'),
        'note': ('本图只含<b>增长口径精确</b>的 %d 家：要么全部产品块都有基期常数，'
                 '要么整家只有<b>一个</b>产品块 —— 后者的那个常数在指数化里被完全约掉，'
                 '所以即使它至今填不出来，这条线仍然是精确的（%s 正是这一种，'
                 '图例里因此写「水平值缺常数」）。'
                 % (len(grow_keys),
                    '、'.join(DISP[k] for k in must) if must else '本期没有'))
        + ('缺常数、增长只能给区间的 <b>%s</b> 不在本图，请看 Exhibit 4 与 Exhibit 6。'
           % '、'.join(DISP[k] for k in band_keys) if band_keys else '')
        + ('图例括号里是该家<b>最新月</b>的定基名义额（US$bn/日），只为让人知道谁大谁小；'
           '线的高低比的是<b>各自相对 %s 的增长</b>，与体量无关。'
           % mlab(BASE))
        + (f'单独画 {len(draw)} 家，其余 {len(rest)} 家'
           f'（{"、".join(DISP[k] for k in rest)}）先按美元名义额相加再指数化 ——'
           '相加之所以成立，正是因为定基之后它们已经是同一个单位（美元）。' if rest else '')
        + '两端已标数值。',
    })

    # ── Exhibit 3：水平值排序（全页唯一的跨所水平值图，只含常数齐备的家）──
    ord3 = sorted(lvl_keys, key=lambda k: -float(lvl[k][CUR]))
    pool_sum = float(sum(float(lvl[k][CUR]) for k in ord3))
    # 截轴：龙头把其余几家压成一条平线时（本期 CME 是第二名的 15 倍），不截轴等于
    # 只画了一根柱。引擎的截轴**不删点** —— 超界的柱画到界 + 白色断口符号，
    # 真值竖排标在图外（charts.js:919-923）。判据写成规则而不是写死一个数：
    # 只有「第一名 > 第二名 ×3」时才截，截到第二名 ×1.15。
    v3 = [float(lvl[k][CUR]) for k in ord3]
    cap3 = v3[1] * 1.15 if len(v3) >= 2 and v3[0] > 3 * v3[1] else None
    cap_txt = ''
    if cap3:
        cap_txt = (f'<b>纵轴已截到 {cap3:,.0f}</b>：{DISP[ord3[0]]} 的 {v3[0]:,.0f} '
                   f'是第二名的 {v3[0] / v3[1]:.1f} 倍，不截轴其余 {len(ord3) - 1} 家会被压成一条平线。'
                   '截轴<b>不删点</b> —— 超界那根柱画到界并加断口符号，真值以红字竖排标在柱顶之上，'
                   '判据是「第一名 > 第二名 ×3 才截，截到第二名 ×1.15」，不是手挑的一个数。')
    ex.append({
        'n': 3, 'kind': 'bars_labeled', 'full': True, 'height': 300,
        'xlabels': [DISP[k] for k in ord3], 'xrot': CAT_XROT,
        # f0c 而不是 f0：本图的量级跨到五位数（截轴那根的真值 > 1 万），
        # 没有千分位时红色竖排的 '11309' 要数一遍才知道是不是 1.1 万。
        'fmt': 'f0c', 'label_fmt': 'f0c', 'ylab': 'US$bn/日（定基名义额）',
        'values': L([lvl[k][CUR] for k in ord3]),
        **({'ycap': round(cap3, 6),
            'cap_note': 'axis capped — true value shown in red'} if cap3 else {}),
        'title': f'Constant-basis notional level, {mlab(CUR)} — only exchanges with a complete '
                 f'set of base constants',
        'annot': f'{len(ord3)} 家合计 {pool_sum:,.0f}',
        'src_extra': ('Levels are comparable across exchanges only because price and FX are '
                      'locked at Jan-19. Exchanges with any unpriced product block are absent '
                      'by construction, not by omission'),
        'note': ('<b>这是全页唯一一张跨所比水平值的图，也是唯一一张真的需要基期常数的图。</b>'
                 + (f'只有 {len(ord3)} 家上榜：<b>{"、".join(DISP[k] for k in band_keys)}</b> '
                    '至少有一个产品块填不出基期常数，而水平值里那个常数<b>不会被约掉</b>'
                    '（它决定块与块之间的权重），所以宁可不画也不能给一个编出来的数。'
                    if band_keys else
                    f'<b>12 家全部上榜</b>：本期每一家的每一个产品块都有基期常数，'
                    f'水平值因而全都算得出来 —— 这是本页最强的一种状态。')
                 + gap_note
                 + f'左上角的合计 {pool_sum:,.0f} US$bn/日<b>只是这几家的和，不是市场总量</b> —— '
                   '缺席的几家里有两家（Cboe、ICE）体量都不小，'
                   '把这里的占比读成市场份额一定是错的。' + cap_txt),
    })

    # ── Exhibit 4：12 家最新同比 —— 菱形 = 精确点值，蓝带 = 精确区间 ──
    # 排序按**下界**：下界的语义是「不管那个未知常数取什么值，至少涨了这么多」，
    # 是唯一一个对精确家与区间家含义都成立的排序键。取中点排序会隐含一个不存在的中心估计。
    ord4 = sorted(MEM_KEYS, key=lambda k: -float(TYOYLO[k][CUR]))
    ex.append({
        'n': 4, 'kind': 'range_band', 'full': True, 'height': 320,
        'xlabels': [DISP[k] for k in ord4], 'xrot': CAT_XROT,
        'fmt': 'pct1', 'label_fmt': 'pct1', 'ylab': f'% y/y ({TTM}-mo rolling sum)',
        'title': f'Constant-basis notional, {TTM}-month rolling-sum y/y — all 12 ({mlab(CUR)}); '
                 f'band = exact range when a base constant is unknown',
        'lo': L([TYOYLO[k][CUR] for k in ord4]),
        'hi': L([TYOYHI[k][CUR] for k in ord4]),
        'actual': L([TYOYP[k][CUR] if EXACT[k] else np.nan for k in ord4]),
        'names': {'range': '缺常数 ⇒ 精确区间（上下界都取得到）',
                  'actual': '常数已知或被约掉 ⇒ 精确点值',
                  'lo': '区间下界', 'hi': '区间上界'},
        'src_extra': (f'Trailing-{TTM}-month sum vs the same {TTM}-month sum a year earlier — '
                      'not single-month y/y. The band is not a confidence interval: it is the '
                      'exact set of values the y/y can take as the unknown base constants range '
                      'over all non-negative values. Both endpoints are attainable'),
        'note': (TTM_BASIS + WHY_TTM + TTM_UNIT_NOTE +
                 '<b>换成滚动口径不影响蓝带的语义</b>：滚动合计 Σ N(t−i) = '
                 'Σ_p k_p·[Σ S_p(t−i)]，仍是各产品块滚动合计的同一组常数线性组合，'
                 '其同比依旧是各块同比的加权平均（权重非负、和为 1）⇒ 上下界照旧是紧界。'
                 '<b>12 家全在这张图上 —— 缺常数的家不是被删掉，是被画成区间。</b>'
                 '一家若只有一个产品块，常数在同比里被完全约掉，给的是<b>菱形点值</b>；'
                 '若有多个块而其中若干块的常数未知，同比是各块同比的加权平均'
                 '（权重非负、和为 1），因此必落在各块的 min / max 之间 —— '
                 '<b>蓝带就是那个区间，两端都取得到，不是置信区间、不是估计误差</b>。'
                 + (f'带子越窄，说明未知常数对结论越无关紧要：本期 '
                    + '、'.join(
                        f'{DISP[k]} 带宽 '
                        f'{abs(float(TYOYHI[k][CUR]) - float(TYOYLO[k][CUR])):.1f}pp'
                        for k in sorted(band_keys,
                                        key=lambda k: abs(float(TYOYHI[k][CUR])
                                                          - float(TYOYLO[k][CUR])))) + '。'
                    if band_keys else
                    '<b>本期一条带子都没有</b>：12 家的基期常数都齐了，全是菱形点值。')
                 + 'x 轴<b>按下界排序</b>（「不管常数取什么值都至少涨了这么多」），'
                   '不按中点 —— 中点会凭空造出一个并不存在的中心估计。'
                 + (f'<b>{"、".join(straddle)} 的区间跨过 0</b>：'
                    f'这几家连「同比是正是负」都不由数据决定，而由那个填不出来的常数决定，'
                    f'所以本页在任何地方都不说它们是涨还是跌 —— '
                    f'页面顶端的「拐点」也只统计给得出点值的 {len(grow_keys)} 家。'
                    if straddle else '')
                 + ('各家区间为什么缺常数，见 Exhibit 3 的图注；'
                    '缺常数那几家拆到产品块之后每一格都是精确的，见 Exhibit 6。'
                    if band_keys else '')),
    })

    # ── Exhibit 5：热力矩阵（增长精确的家 × 近 8 年年度同比）──
    yrs = sorted({p.year for p in IDX})[-HEAT_YEARS:]
    row5 = sorted(grow_keys, key=lambda k: -float(IDXP[k][CUR]))
    heat5 = [[None if not np.isfinite(v) else round(float(v), 6)
              for v in (annual_yoy(PARTS[k][0][1], y) for y in yrs)] for k in row5]
    part_yrs = [y for y in yrs if len({p.month for p in IDX if p.year == y}) < 12]
    ex.append({
        'n': 5, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pct0z',
        'title': f'Constant-basis notional, annual y/y (%) — the {len(row5)} exchanges whose '
                 f'growth is exact, × last {len(yrs)} years',
        'rows': [DISP[k] for k in row5], 'cols': [str(y) for y in yrs],
        'matrix': heat5, 'legend': '年度同比（定基名义额）',
        'cell_h': 22, 'row_lab_w': 96, 'row_head': '交易所',
        'src_extra': ('Annual y/y on a calendar-year basis (part-years compare like months only) '
                      f'— a {TTM}-month aggregate, like the rolling-sum basis used elsewhere on '
                      'this page, but cut by calendar year rather than by a rolling window. '
                      'Green = faster growth. Colour scale is the 5th–95th percentile of this '
                      'matrix\'s own cells'),
        'note': ('<b>本图是年度同比，不是单月同比，也不是滚动同比。</b>'
                 f'它按<b>日历年</b>切（未满年同月对同月），而 Exhibit 4 / 7 / 8 与汇总表按'
                 f'<b>最近 {TTM} 个月</b>的滚动窗口切 —— 两者都是 {TTM} 个月量级的聚合，'
                 '都不受单月毛刺影响，切法不同而已；'
                 '完整年份的 12 月那一格，两个口径在数学上恰好相等。'
                 f'所以本页<b>没有单月同比曲线</b>：单月口径的毛刺实测见 Exhibit 4 的图注。'
                 '行按<b>最新月的指数（增长）</b>从高到低排'
                 + ('，不按体量 —— 因为本图里的 %s 没有可比的体量'
                    '（它的基期常数至今空着，只是那个常数在增长里被约掉了）。'
                    % '、'.join(DISP[k] for k in must)
                    if must else '（本图各家都有体量，按增长排是为了和 Exhibit 3 的'
                                 '体量排序互补，两张一起看才知道是大所带小所还是反过来）。')
                 + (f'{"、".join(str(y) for y in part_yrs)} 年只到 {mlab(LATEST)}，'
                    f'该列拿<b>同月对同月</b>比上年（不是比上年全年，否则会砸出一个假坑）。'
                    if part_yrs else '')
                 + '色标取本矩阵自己全部有效格的 5/95 分位，'
                   '所以颜色只在本图内部可比，不要拿去和别的热力图对望。'
                 + (f'缺常数的 <b>{"、".join(DISP[k] for k in band_keys)}</b> 不在本图：'
                    '它们的年度同比是区间不是点值，塞进热力图会被读成实测值。'
                    '它们拆到产品块之后每一格都是精确的 —— 那就是下一张图。'
                    if band_keys else '')),
    })

    # ── Exhibit 6：缺常数那几家拆到产品块（每块单产品 ⇒ 常数约掉，格格精确）──
    if band_keys:
        rows6, heat6 = [], []
        for k in band_keys:
            for prods, s, ok in PARTS[k]:
                rows6.append(f'{DISP[k]}·{part_label(k, set(prods))}'
                             + ('（已定基）' if ok else '（缺常数）'))
                heat6.append([None if not np.isfinite(v) else round(float(v), 6)
                              for v in (annual_yoy(s, y) for y in yrs)])
        # 热力图的空格与「那一年没有成交」在视觉上分不开（CHART_KINDS §3 明写），
        # 所以有几格空、空在谁身上，必须在图注里点名。
        blank6 = sum(v is None for row in heat6 for v in row)
        blank6_who = [f'{rows6[i]} {yrs[j]}' for i, row in enumerate(heat6)
                      for j, v in enumerate(row) if v is None]
        ex.append({
            'n': 6, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pct0z',
            'title': f'The {len(band_keys)} constant-gap exchanges, broken out by product block '
                     f'— annual y/y (%), every cell exact',
            'rows': rows6, 'cols': [str(y) for y in yrs],
            'matrix': heat6, 'legend': '年度同比（产品块自身的量）',
            # row_lab_w 204：最长行标签「ICE / NYSE·能源（仅 Brent 原油） 等 2 腿（已定基）」
            # 实测 196.1px（visual_qa 报 168 时左溢 28.1px），取 204 留 8px 余量。
            'cell_h': 22, 'row_lab_w': 204, 'row_head': '交易所·产品块',
            'src_extra': ('Each row is a single product block, so its own base constant cancels '
                          'out of the growth rate entirely. No unknown constant enters any cell'),
            'note': ('<b>这张图是上一张的补集，也是「缺常数不等于看不见增长」的直接证明。</b>'
                     '每一行都是<b>一个</b>产品块（或一组常数已知、权重因而已知的块），'
                     '块自己的基期常数在同比里被完全约掉 ⇒ <b>每一格都是精确值</b>，'
                     '和常数齐备的家享有同等的可信度。'
                     '缺的只有一件事：这些行之间<b>不能相加</b>，因为块与块的权重正是那个'
                     '未知常数决定的 —— 那也正是它们合并起来只能给区间（Exhibit 4）的原因。'
                     '标「已定基」的行是该家常数已知的那几条腿先按已知权重合成的一块。'
                     + (f'<b>空格 = 该块在上一年没有可比历史，年度同比算不出来，'
                        f'不是那一年没有成交</b>（本图 {blank6} 格：'
                        f'{"、".join(blank6_who)}）—— 块与块的源列起点不同，'
                        f'{yrs[0]} 年那一列尤其明显，因为它要拿 {yrs[0] - 1} 年做分母，'
                        f'而本页的共同窗口从 {mlab(BASE)} 才开始。'
                        if blank6 else '')),
        })

    # ── Exhibit 7 / 8：张数口径 vs 定基名义额口径（本次改口径的核心证据）──
    # JPX 那张图的编号必须**现算**：band_keys 为空时 Exhibit 6 整张不画、后面的号全部前移，
    # mix_keys 为空时 7/8 两张也不画。写死一个 9，等常数补齐那天它就指到核对表上去了。
    jpx_n = ex[-1]['n'] + (2 if mix_keys else 0) + 1
    flat_txt = ''
    if flat_keys:
        flat_txt = (f'<b>{"、".join(DISP[k] for k in flat_keys)} 不在本图（结构性）</b>：'
                    f'这几家的官方披露只给一个"衍生品合计"，本页也就只配了一个篮子产品，'
                    f'两个口径之间只差<b>同一个常数</b>，同比在数学上恒等、差值恒为 0 —— '
                    f'那是构造出来的零，不是"这家没有合约变小"，画进来只会被读成后者。'
                    + (f'JPX 正是其中之一，而它恰恰是全仓最强的一份反例，'
                       f'所以单给它一张 Exhibit {jpx_n}。'
                       if 'jpx' in flat_keys and jp is not None else ''))
    if gapblock_keys:
        flat_txt += (f'<b>{"、".join(DISP[k] for k in gapblock_keys)} 也不在本图（缺常数）</b>：'
                     f'它们配了 ≥2 个合约产品，本来是可测的，但其中至少一个产品的基期常数'
                     f'填不出来 ⇒ 名义额那一侧算不出来，差值无从谈起。原因见 Exhibit 3 图注。')
    if mix_keys:
        ord7 = sorted(mix_keys, key=lambda k: -float(gap[k][CUR]))
        yy_cnt = {k: ttm_yoy(CNT[k]).reindex(IDX) for k in mix_keys}
        # 单月口径的同一组差值：只用来在图注里量化「改口径改了多少」，不进任何柱子
        m_gap_txt = '、'.join(f'{DISP[k]} 单月 {pp(float(m_gap[k][CUR]))}'
                             f' / 滚动 {pp(float(gap[k][CUR]))}' for k in ord7)
        ex.append({
            'n': ex[-1]['n'] + 1, 'kind': 'grouped_bars', 'full': True, 'height': 300,
            'xlabels': [DISP[k] for k in ord7], 'xrot': CAT_XROT,
            'fmt': 'pct1', 'label_fmt': 'pct1', 'bar_labels': True,
            'ylab': f'% y/y ({TTM}-mo rolling sum)',
            'title': f'Same contracts, two units: contract-count vs constant-basis notional, '
                     f'{TTM}-month rolling-sum y/y ({mlab(CUR)})',
            'groups': [
                {'name': f'张数口径 y/y（{TTM} 个月滚动合计）', 'color': 'NAVY',
                 'values': L([yy_cnt[k][CUR] for k in ord7])},
                {'name': f'定基名义额口径 y/y（{TTM} 个月滚动合计）', 'color': 'MBLUE',
                 'values': L([yy_cnt[k][CUR] - gap[k][CUR] for k in ord7])},
            ],
            'src_extra': ('Both bars cover exactly the same contract legs — only the unit differs. '
                          f'Both are on the {TTM}-month rolling-sum basis, not single-month y/y. '
                          'Cash-equity and cash-turnover legs are excluded because they have no '
                          'contract count'),
            'note': (TTM_BASIS +
                     '两根柱的<b>成分完全一样</b>，只是计量单位不同：左柱按张数、右柱按'
                     '「张数 × 乘数 × 基期价格」。两根不一样高，说明这一年里成交往'
                     '<b>更小或更大的合约</b>迁移了。'
                     f'本图 {len(ord7)} 家 = 配了 ≥2 个合约产品、<b>且这些产品的基期常数全都填得出</b>、'
                     '差值才是实测量的那几家。'
                     '纯金额口径的腿（现货成交额）没有张数，不入本图。'
                     + WHY_TTM + TTM_UNIT_NOTE + flat_txt),
        })
        ex.append({
            'n': ex[-1]['n'] + 1, 'kind': 'grouped_bars', 'full': True, 'height': 300,
            'xlabels': [DISP[k] for k in ord7], 'xrot': CAT_XROT,
            'fmt': 'pp1', 'label_fmt': 'pp1', 'bar_labels': True,
            'ylab': 'pp（张数 y/y − 名义额 y/y）',
            'title': f'Contract-shrink effect: contract-count minus constant-basis notional, '
                     f'{TTM}-month rolling-sum y/y ({mlab(CUR)})',
            'groups': [{'name': '差值（正 = 增长来自合约变小）', 'color': 'NAVY',
                        'values': L([gap[k][CUR] for k in ord7])}],
            'src_extra': ('Positive = contract count grew faster than the exposure it represents, '
                          'i.e. trading migrated into smaller contracts (minis / micros). '
                          f'Negative = the mix moved into larger contracts. Both sides on the '
                          f'{TTM}-month rolling-sum basis'),
            'note': ('<b>这是本页改口径的全部理由。</b>差值为正 = 张数涨得比敞口快，'
                     '增长来自「合约变小」（拆细、mini / micro 化）而不是敞口变大；'
                     '为负则相反。两个口径都是纯数（%），差值用 pp。'
                     '单位换算的常数是定基的，所以这个差值里不含标的涨跌与汇率。'
                     f'<b>两侧都取 {TTM} 个月滚动合计的同比</b>，必须同口径 —— '
                     '一侧滚动一侧单月，算出来的差是噪音差不是结构差。'
                     f'同一批合约在单月口径下的差值是：{m_gap_txt}；'
                     '差得越远，越说明单月口径下这个「合约变小」的读数里混着毛刺。'
                     '<b>本图量的是「品种结构在一年里往哪边挪」，不是"这家有没有 micro 合约"</b>：'
                     '一家把成交全迁进 micro 但品种间比例没变，本图读到的仍然是 0 —— '
                     '要看得见那种迁移，得有 mini / micro 的拆分列，本页 12 家里一家都没有。'
                     + flat_txt),
        })

    # ── JPX 的两个单位（被结构性排除，但证据最强的一家）——编号由前面的图决定 ──
    if jp is not None:
        if ex[-1]['n'] + 1 != jpx_n:
            raise SystemExit(
                f'JPX 那张图的实际编号 {ex[-1]["n"] + 1} 与前面图注里引用的 {jpx_n} 对不上 —— '
                'Exhibit 7/8 的图注会把读者指到别的图上。改了出图顺序就要同步改 jpx_n。')
        ex.append({
            'n': jpx_n, 'kind': 'lines_endlabels', 'full': True, 'height': 320,
            'fmt': 'f0', 'yfmt': 'f0', 'xlabels': XL_LONG, 'xstep': 6, 'xrot': 90,
            'title': f'JPX financial derivatives, two units on the same contracts '
                     f'(rebased {mlab(BASE)} = 100)',
            'ylab': f'index, {mlab(BASE)} = 100',
            'series': [
                {'name': f'原始张数（{jp["raw_end"]:,.0f}）', 'color': 'NAVY',
                 'values': L(jp['raw_idx'].values)},
                {'name': f'大合约当量（{jp["lgeq_end"]:,.0f}）', 'color': 'GOLD',
                 'values': L(jp['lgeq_idx'].values)},
            ],
            'src_extra': ('Same contracts, counted two ways. The large-contract-equivalent line '
                          'divides mini / micro contracts by JPX\'s own official ratios, so the '
                          'gap between the lines is pure contract-size mix — no price, no FX'),
            'note': ('<b>同一批合约，量了两遍。</b>两条线之间张开多少，就是「合约变小」'
                     '本身的大小 —— 没有价格、没有汇率、没有并购，两条线的分母是同一批交易。'
                     '两条线都只是<b>张数的两个单位</b>，一个基期常数都没用上，'
                     '这也是本页「常数缺口不挡增长」那条规矩最干净的一个例子。'
                     f'累计（{jp["span"]}）：原始张数 {pct(jp["raw_cum"])}、'
                     f'大合约当量 {pct(jp["lgeq_cum"])}'
                     + ('，<b>符号相反</b>。' if jp['opposite'] else '，同号但幅度差一大截。')
                     + f'最新月 {mlab(jp["cur"])} 的同比（<b>{TTM} 个月滚动合计口径</b>，'
                       f'与全页一致）：张数 {pct(jp["raw_yoy"])}、'
                       f'当量 {pct(jp["lgeq_yoy"])}，差 <b>{pp(jp["gap_pp"])}</b>。'
                       f'同月的单月同比是张数 {pct(jp["raw_yoy_m"])}、'
                       f'当量 {pct(jp["lgeq_yoy_m"])}（差 {pp(jp["gap_pp_m"])}）—— '
                       f'两组数差这么远，正是本页不用单月口径的原因，'
                       f'页面上引用的一律是滚动口径那一组。'
                       f'原始/当量的倍率从基期的 {jp["ratio0"]:.2f}x 走到 {jp["ratio1"]:.2f}x —— '
                       '倍率不是常数而是单调走高，这正是"张数不可跨期比"的直接观测。'
                       '<b>本图只含金融衍生品（股指 + 利率），不含商品</b>：旧 TOCOM 2020-07 '
                       '才迁入 OSE，含商品的合计在那之前是 pro-forma，跨那个月读会把一次并购'
                       '读成成交量变化。' + JPX_LGEQ_PROV),
        })

    # ── Exhibit 1：汇总表 ──
    rows, blank_why = [], []
    # ⚠ 这一组的 m/m / y/y 两列**恒等于本行前三列的算术**（本月 ÷ 上月 / 去年同月）。
    # 给水平值行印一个滚动同比，读者拿第一列除第三列会得到另一个数，表内自相矛盾 ——
    # 那比口径混用更糟。所以它天然是单月口径，只能在组标题与表注里标死，不能改。
    # 第 ② 组则相反：它三列显示的本身就是指数读数，其 y/y 直接取滚动口径的 TYOYP。
    rows.append({'kind': 'group',
                 'label': f'① 定基名义额水平值（US$bn/日，{mlab(BASE)} 价格与汇率）'
                          f'—— 只有常数齐备的 {len(lvl_keys)} 家有这一组；'
                          f'本组 m/m 与 y/y 是<b>本行三列的算术</b>，'
                          f'因而是<b>单月口径</b>，与第 ② 组的 y/y 不可比'})
    for k in ord3:
        s = lvl[k]
        c, p1, p12 = float(s[CUR]), float(s[PRV]), float(s[YAG])
        mm = (c / p1 - 1) * 100 if np.isfinite(p1) and p1 else np.nan
        yy_ = (c / p12 - 1) * 100 if np.isfinite(p12) and p12 else np.nan
        cells = [{'v': num(c, 0)}, {'v': num(p1, 0)}, {'v': num(p12, 0)},
                 {'v': pct(mm), 'cls': cls_of(mm)}, {'v': pct(yy_), 'cls': cls_of(yy_)}]
        t_, cl_ = pctile.cell(ser_of(s))
        cells.append({'v': t_, 'cls': cl_} if t_ else {'v': ''})
        if not t_:
            blank_why.append((DISP[k], pctile.why_blank(ser_of(s))))
        rows.append({'label': f'{DISP[k]}（{ZHNAME[k]}）', 'cells': cells})

    rows.append({'kind': 'group',
                 'label': f'② 指数化增长（{mlab(BASE)} = 100）—— 12 家全在；'
                          f'缺常数的家给<b>紧界区间</b>，不是估计值。'
                          f'y/y 列是 <b>{TTM} 个月滚动合计口径</b>，m/m 列是单月环比'})
    ord_idx = sorted(MEM_KEYS, key=lambda k: -float(IDXLO[k][CUR]))
    for k in ord_idx:
        if EXACT[k]:
            cells = [{'v': num(float(IDXP[k][p]), 0)} for p in (CUR, PRV, YAG)]
            mmv, yyv = float(MOMP[k][CUR]), float(TYOYP[k][CUR])
            cells += [{'v': pct(mmv), 'cls': cls_of(mmv)}, {'v': pct(yyv), 'cls': cls_of(yyv)}]
            t_, cl_ = pctile.cell(ser_of(IDXP[k]))
            cells.append({'v': t_, 'cls': cl_} if t_ else {'v': ''})
            if not t_:
                blank_why.append((f'{DISP[k]} 指数', pctile.why_blank(ser_of(IDXP[k]))))
            lab = f'{DISP[k]}（{ZHNAME[k]}）'
        else:
            cells = [{'v': rng_num(float(IDXLO[k][p]), float(IDXHI[k][p]), 0)}
                     for p in (CUR, PRV, YAG)]
            cells += [{'v': rng_pct(float(MOMLO[k][CUR]), float(MOMHI[k][CUR]))},
                      {'v': rng_pct(float(TYOYLO[k][CUR]), float(TYOYHI[k][CUR]))}]
            cells.append({'v': ''})
            lab = f'{DISP[k]}（{ZHNAME[k]}）· 区间'
        rows.append({'label': lab, 'cells': cells})

    if mix_keys:
        rows.append({'kind': 'group',
                     'label': f'③ 张数口径 − 定基名义额口径的同比差（pp，两侧同为 {TTM} 个月'
                              f'滚动合计口径；仅 ≥2 个合约产品且常数齐备的家；正 = 合约变小）'})
        for k in sorted(mix_keys, key=lambda k: -float(gap[k][CUR])):
            s = gap[k]
            c, p1, p12 = float(s[CUR]), float(s[PRV]), float(s[YAG])
            mm = c - p1 if np.isfinite(c) and np.isfinite(p1) else np.nan
            yy_ = c - p12 if np.isfinite(c) and np.isfinite(p12) else np.nan
            cells = [{'v': pp(c)}, {'v': pp(p1)}, {'v': pp(p12)},
                     {'v': pp(mm), 'cls': cls_of(mm)}, {'v': pp(yy_), 'cls': cls_of(yy_)}]
            t_, cl_ = pctile.cell(ser_of(s))
            cells.append({'v': t_, 'cls': cl_} if t_ else {'v': ''})
            if not t_:
                blank_why.append((f'{DISP[k]} 差值', pctile.why_blank(ser_of(s))))
            rows.append({'label': f'{DISP[k]}（{ZHNAME[k]}）', 'cells': cells})

    blank_txt = ('本轮留空：' + '；'.join(f'{a}（{b}）' for a, b in blank_why) + '。'
                 ) if blank_why else '本轮各行均未触发留空，分位照算。'
    summary = {
        'title': f'12 家总览 — {mlab(CUR)}（共同最新月）',
        'heads': [f'本月 {mlab(CUR)}', f'上月 {mlab(PRV)}', f'去年同月 {mlab(YAG)}',
                  'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': rows,
        'note': ('<b>三组的可信度不一样，读之前先看组标题。</b>'
                 f'第 ① 组是水平值（US$bn/日）：因为价格与汇率都锁在 {mlab(BASE)}，'
                 '它可以横向相加与排名 —— 但<b>只有基期常数齐备的家才有这一组</b>，'
                 f'缺席的 {len(band_keys)} 家不是没数据，是那个常数在水平值里不会被约掉。'
                 '第 ② 组是指数化增长，<b>12 家一个不缺</b>：单产品块的家常数被完全约掉，'
                 '给点值；多产品块且有块缺常数的家给<b>紧界区间</b>（写成 a–b），'
                 '那是未知常数取遍所有非负值时该指标的<b>全部可能取值</b>，两端都取得到，'
                 '既不是置信区间也不是估计误差。区间行不算 3Y %ile —— '
                 '分位要求一条单值序列，区间没有。'
                 + ('第 ③ 组是同一批合约腿在两个口径下的同比差，单位 pp。'
                    if mix_keys else '')
                 + f'<b>第 ②③ 组的 y/y 是 {TTM} 个月滚动合计口径</b>'
                   f'（本月往前 {TTM} 个月的合计 ÷ 去年同月往前 {TTM} 个月的合计 − 1），'
                   '不是单月同比。' + WHY_TTM + TTM_UNIT_NOTE
                 + '<b>⚠ 第 ① 组的 y/y 是例外，它是单月口径。</b>'
                   'm/m 与 y/y 两列<b>恒等于本行前三列的算术</b>（本月 ÷ 上月 / 去年同月）'
                   '—— 给水平值行印一个滚动同比，读者拿第一列除第三列会得到另一个数，'
                   '表内自相矛盾，那比口径混用更糟。所以第 ① 组只能标清楚、不能改；'
                   '第 ② 组三列显示的本身就是指数读数，其 y/y 直接取滚动口径。'
                 + f'差多少本页现算：{mlab(CUR)} '
                 + '、'.join(f'{DISP[k]}（① 组 {pct(float(YOYP[k][CUR]))}、'
                             f'② 组 {pct(float(TYOYP[k][CUR]))}）' for k in ord3)
                 + '。<b>要判断趋势与排名请只看第 ②③ 组</b>；第 ① 组的水平值与其 y/y '
                   '只为与官方披露逐条核对。'
                 + '<b>m/m 列一律保持单月口径</b>：那是「本月 vs 上月」的运营监控量，'
                   '本来就该看单月，平滑掉就没有监控意义了。'
                 + '3Y %ile = 该读数在最近 36 个月里高于多少百分比的观测，判据与留空规则'
                   '由全站唯一实现 <code>build/pctile.py</code> 给出。' + blank_txt),
    }

    # ── 末尾核对表：13 个月 ──
    # 张数**不需要任何常数**，所以核对表里 11 家都有张数列，而名义额列只有常数齐备的家。
    # 官方新闻稿发的就是张数，这一列是全页与官方逐位对账的唯一入口。
    tcols, cnt_keys = [], [k for k in MEM_KEYS if con_prod[k]]
    for k in ord3:
        tcols.append((f'{DISP[k]} 名义额 (US$bn/d)', f'{k}_n'))
    for k in cnt_keys:
        tcols.append((f'{DISP[k]} 张数 (张/d)', f'{k}_c'))
    trows = []
    for p in IDX[-TBL_MONTHS:]:
        r = {'xl': mlab(p)}
        for k in ord3:
            r[f'{k}_n'] = num(float(lvl[k][p]), 1)
        for k in cnt_keys:
            r[f'{k}_c'] = num(float(CNT[k][p]), 0)
        trows.append(r)
    table = {
        'n': ex[-1]['n'] + 1,
        'title': f'近 {TBL_MONTHS} 个月核对表：定基名义额（US$bn/日，仅常数齐备的 '
                 f'{len(ord3)} 家）与张数（张/日，{len(cnt_keys)} 家）并列',
        'idx': '月份',
        'cols': [[h, k] for h, k in tcols],
        'rows': trows,
    }

    # ── 抬头 / 页脚 / 口径说明 ──
    yy_exact = sorted(((DISP[k], float(TYOYP[k][CUR])) for k in grow_keys), key=lambda kv: -kv[1])
    # 单月口径的同一组排序：只印在抬头里做对照，让「换口径不是修辞」无法被忽略
    yy_month = sorted(((DISP[k], float(YOYP[k][CUR])) for k in grow_keys), key=lambda kv: -kv[1])
    _same_order = [a for a, _b in yy_exact] == [a for a, _b in yy_month]
    win_txt = '、'.join(f'{a} {pct(b)}' for a, b in yy_exact[:3])
    lose_txt = '、'.join(f'{a} {pct(b)}' for a, b in yy_exact[-3:])
    idx_rank = sorted(((DISP[k], float(IDXP[k][CUR])) for k in grow_keys), key=lambda kv: -kv[1])
    lag_txt = '、'.join(f'{DISP[k]}（{mlab(lasts[k])}）' for k in MEM_KEYS if lasts[k] == LATEST)
    ahead_txt = ('；'.join(f'{d} 自身已更新至 {mlab(m)}' for d, m in AHEAD)
                 if AHEAD else '本期 12 家的最新月恰好一致，无人跑在前面')
    all_txt = ' · '.join(f'{DISP[k]} 更新至 {mlab(lasts[k])}' for k in MEM_KEYS)
    gap_rank = sorted(((DISP[k], float(gap[k][CUR])) for k in mix_keys), key=lambda kv: -kv[1])

    # 拐点：同比由负转正 / 由正转负。**只认精确家** —— 区间跨 0 的家谈不上"翻转"，
    # 说它翻转就是在区间里替读者挑了一个点。
    # 走**滚动口径**：单月口径下一个正负号翻转多半只是去年同月的一次异常，
    # 本页实测符号相反的月份成百上千地出现，拿它认「拐点」等于每个月都在报假拐点。
    turn_up = [DISP[k] for k in grow_keys
               if np.isfinite(TYOYP[k][CUR]) and np.isfinite(TYOYP[k][PRV])
               and TYOYP[k][PRV] < 0 <= TYOYP[k][CUR]]
    turn_dn = [DISP[k] for k in grow_keys
               if np.isfinite(TYOYP[k][CUR]) and np.isfinite(TYOYP[k][PRV])
               and TYOYP[k][PRV] >= 0 > TYOYP[k][CUR]]
    turn_txt = ('精确口径的 %d 家本月无同比正负号翻转' % len(grow_keys) if not (turn_up or turn_dn)
                else '；'.join(x for x in [
                    ('转正：' + '、'.join(turn_up)) if turn_up else '',
                    ('转负：' + '、'.join(turn_dn)) if turn_dn else ''] if x))
    jpx_txt = ('' if jp is None else
               f'JPX 把这件事摆得最明白：同一批金融衍生品，'
               f'{mlab(jp["cur"])} 的张数 y/y {pct(jp["raw_yoy"])}、'
               f'大合约当量 y/y {pct(jp["lgeq_yoy"])}，差 <b>{pp(jp["gap_pp"])}</b>；'
               f'拉长看（{jp["span"]}）张数 {pct(jp["raw_cum"])}、当量 {pct(jp["lgeq_cum"])}，'
               + ('<b>符号相反</b>' if jp['opposite'] else '同号但幅度差一大截')
               + f'（Exhibit {ex[-1]["n"]}，{JPX_LGEQ_PROV}）。')

    uncov_txt = '；'.join(
        f'<b>{DISP[k]}</b> 未纳入 ' + '、'.join(f'{c}（{why}）' for c, why in UNCOVERED[k])
        for k in MEM_KEYS if UNCOVERED[k])
    zero_legs = [f'{DISP[k]}·{lg.col}' for k in MEM_KEYS for lg in LEGS[k] if lg.zero_before]
    used_prods = sorted({p for k in MEM_KEYS for p in BLK[k]})
    tier = {}
    for p in used_prods:
        if p in kconst:
            tier.setdefault(nsrc.get(p) or '（未标注）', []).append(p)
    tier_txt = '、'.join(f'{t} {len(v)} 个' for t, v in sorted(tier.items()))

    # ── 注 1 的分腿口径：fx_only 腿不满足「增长率＝张数增长率」，必须点名 ──
    # 见 fx_only_legs() 的 docstring：kind='notional' 的腿只锁了汇率，价格是当期。
    # 权重按 BASE / LATEST 两个时点给，好让读者自己判断这家的读数受不受影响。
    fxo_leg = {k: fx_only_legs(k, specs) for k in MEM_KEYS}
    fxo_w = fx_only_weight(BLK, kconst, specs, (BASE, LATEST))
    fxo_keys = [k for k in MEM_KEYS if fxo_leg[k]]
    pure_keys = [k for k in MEM_KEYS if not fxo_leg[k]]
    all_fxo = [k for k in fxo_keys if not contract_products(k, specs)
               and not any(specs[p]['kind'] == 'share' for p in BLK[k])]

    def _fxo_one(k):
        w = fxo_w.get(k)
        cols = '、'.join(lg.col for lg in fxo_leg[k])
        if w is None or not np.isfinite(w[0]) or not np.isfinite(w[1]):
            tail = '（常数未齐，占比算不出）' if k not in all_fxo else '（<b>整家都是</b>）'
            return f'<b>{DISP[k]}</b> {cols}{tail}'
        return (f'<b>{DISP[k]}</b> {cols}'
                f'（占该家名义额 {mlab(BASE)} {w[0] * 100:.1f}% → {mlab(LATEST)} {w[1] * 100:.1f}%'
                + ('，<b>整家都是</b>' if k in all_fxo else '') + '）')

    fxo_txt = '；'.join(_fxo_one(k) for k in fxo_keys)

    notes = [
        f'<b>主口径：定基名义额。</b>定基名义额 = 张数 × 乘数 × <b>{mlab(BASE)} 基期价格</b>，'
        f'汇率同样锁在 {mlab(BASE)}。'
        f'对<b>合约腿与股数腿</b>（规格表 kind=contract / share，本页 {len(pure_keys)} 家'
        f'{"全部" if not fxo_keys else "的全部腿与另 %d 家的部分腿" % len(fxo_keys)}属于这一类），'
        '价格项与汇率项都是常数，所以这些序列的'
        '<b>增长率与它自己的张数增长率完全相同</b> —— 常数只改变产品之间与交易所之间的'
        '相对权重，不把标的涨跌与汇率波动混进增长里。',

        ('<b>但有一类腿只剔掉了汇率、没剔掉标的涨跌，读增长时必须先看这一条。</b>'
         '源头只披露本币成交额（HKEX 的 ADT、Euronext 的 ADNV、JPX/SGX/ASX 的现货成交额）时，'
         '金额 ≡ 股数 × <b>当期</b>价格，我们拿不到股数就没法把价格项剥出来'
         '（📌 未找到：这几家的月度报表都不披露成交股数）。规格表把这类源标 kind=notional、'
         'multiplier 与基期价格恒为 1，notional.py 称其 deflator=<code>fx_only</code>。'
         f'<br>本页有 <b>{len(fxo_keys)} 家</b>含这类腿：{fxo_txt}。'
         '<br><b>对这些腿，上一条的「增长率＝张数增长率」不成立</b>：它们的增长 = 成交量增长 '
         '+ 标的涨跌。所以 Exhibit 2 的指数线、Exhibit 4 的同比带里，这几家的读数含股价/指数'
         '涨幅，与纯合约腿的家<b>不是同一个口径</b>，跨家比增长时必须把这件事算进去。'
         + (f'<br>其中 <b>{"、".join(DISP[k] for k in all_fxo)}</b> 一条合约腿都没有，'
            f'整家读数都是 fx_only —— 这几家的指数线只能读作「本币成交额的定基指数」，'
            f'不能读作成交量。' if all_fxo else '')
         + '<br>本页不因此拒收这些腿：拒了就等于把 4 家亚太所与 Euronext 的现货业务整块删掉，'
           '那比口径混杂更失真。但<b>混了 deflator 的池不许算份额</b>（notional.py:32），'
           '所以本页任何一处都没有把 Exhibit 3 的水平值读成市场份额。'),

        ('<b>缺基期常数怎么办：降级到图，不拖垮整页（这一条是本页最需要先读懂的）。</b>'
         f'本页用到 {len(used_prods)} 个 product_id，其中 <b>{len(gap_prods)} 个</b>填不出基期常数。'
         '关键在于<b>常数只在比水平值时才需要</b>：'
         '<br>· 一家若只有<b>一个</b>产品块，它的指数与同比里那个常数在分子分母同时出现、'
         '<b>被完全约掉</b> ⇒ 即使常数至今空着，增长曲线仍是精确的'
         + (f'（本期 <b>{"、".join(DISP[k] for k in must)}</b> 就是这一种：'
            f'它一个基期常数都没有，指数线却和常数齐备的家一样精确）。'
            if must else '（本期没有这一种 —— 缺常数的家都不止一个产品块）。')
         + '<br>· 一家若有多个块而其中若干块常数未知，任何比值都是各块同一比值的加权平均'
           '（权重非负、和为 1）⇒ 必落在各块的 min / max 之间，而且两端在常数取极端值时'
           '<b>都取得到</b>。所以页面给的是<b>紧界</b>，不是估计、不是置信区间：'
         + (f'本期 <b>{"、".join(DISP[k] for k in band_keys)}</b> 走这条路。'
            if band_keys else '本期没有一家走到这一步 —— 12 家的常数都齐了。')
         + '<br>· 水平值那个常数不会被约掉（它就是块与块之间的权重），'
         + f'所以 Exhibit 3、汇总表第 ① 组、核对表的名义额列一律<b>只含常数齐备的 '
           f'{len(lvl_keys)} 家</b>，缺的宁可不画。' + gap_note),

        f'<b>本页用到的常数有多硬（notional_source 三档）。</b>'
        f'已定价的 {sum(len(v) for v in tier.values())} 个 product_id 里：{tier_txt}。'
        'official_notional = 官方直发的名义额，可信度最高；'
        'reconstructed = 按官方乘数与官方价格重算（每一跳都有 evidence 列作证）；'
        'definitional = 面值本身就是合约定义（如 3 个月 SOFR 期货的 100 万美元、'
        '美债期货的 10 万美元），不依赖任何行情。'
        '<b>「常数齐备」不等于「常数一样硬」</b>，跨所比水平值时这三档混在一起，'
        '这是 Exhibit 3 之外的另一层不确定性，页面无法用图形表达，只能写在这里。',

        '<b>为什么不直接比张数。</b>单张名义额 = 乘数 × 标的价格，而<b>乘数是交易所自选的'
        '产品设计</b>：CME 的 E-mini S&P（$50 × 指数）与 Micro E-mini（$5 × 指数）差 10 倍，'
        '把一张 E-mini 拆成 10 张 Micro，张数 ×10 而敞口一点没变。'
        + jpx_txt +
        f'所以张数只留在 Exhibit {table["n"]} 的核对表里用于对账，不进任何主图；'
        + '差值图（若本期画得出来）把两个口径的差摆出来，'
        '就是要让这件事在页面上看得见。'
        '<b>CME 的 Micro 效应本页无法独立验证</b>：series/cme.csv 只有分品类的合计 ADV，'
        '没有 mini / micro 的拆分列。',

        f'<b>各家的口径边界（这一条决定了排名能读到什么程度）。</b>'
        f'本页的「某家名义额」= 该家<b>已进换算链的那几条腿之和</b>，不是它的全部业务。'
        f'已知在范围内但没进腿的列逐条列明：{uncov_txt or "无"}。'
        '因此 Exhibit 3 的水平值可以相加、可以排名，但<b>不等于市场份额</b> —— '
        '边界不同的两家放在一起比水平值，比的一部分是覆盖度；'
        '何况本期还有几家因为缺常数根本不在那张图上。'
        '要比增长则不受影响：每家都是拿自己和自己的去年比。',

        f'<b>发布门槛：共同最新月。</b>本页统一截到 <b>{mlab(LATEST)}</b>，'
        f'即 12 家中最慢的那家的最新月。本期短板是 <b>{"、".join(LAG)}</b>；{ahead_txt}。'
        '门槛存在的理由：12 家的披露节奏差好几天到两周，若各画各的最新月，'
        '读者会拿一家的 7 月去比另一家的 6 月，看到的「谁跑赢」里有一整个月是口径造出来的。'
        '<b>跑在前面那些家的最新一个月不在本页任何一张图、任何一行表里</b> —— 要看它们，'
        '请去各自的单公司页。',

        f'<b>基期 {mlab(BASE)} 是全仓锁死的（build/notional.py 的 BASE_MONTH）。</b>'
        '它是仓内最晚开始的一条主序列的起点。基期一旦发布就不能再改 —— '
        '改了所有历史图的水平值全部平移，而页面上不会有任何提示。'
        '本页任何一家在基期月缺完整数据都会直接整页跳过，不会拿相邻月顶上。',

        f'<b>同比的口径：{TTM} 个月滚动合计，不是单月（2026-08-07 改）。</b>'
        f'本页 Exhibit 4 / 7 / 8、汇总表第 ②③ 组、抬头的 y/y 与「拐点」，'
        f'一律是「本月往前 {TTM} 个月的合计 ÷ 去年同月往前 {TTM} 个月的合计 − 1」。'
        + WHY_TTM + TTM_UNIT_NOTE +
        '算法上先在<b>该家自己的完整历史</b>上滚动求和再取同比，最后才截到共同窗口 —— '
        f'先截会白扔掉窗口外已有的历史。取数窗口因此从基期往前多开 {2 * TTM} 个月'
        f'（滚动同比最早那个读数要用到 t−{2 * TTM - 1} 的原始月）；'
        f'某家 CSV 本来就没有那么早的历史时，窗口前端的读数如实留空，不用近似值填。'
        '<b>换口径不影响紧界</b>：滚动合计 Σ N(t−i) = Σ_p k_p·[Σ S_p(t−i)]，'
        '仍是各产品块滚动合计的同一组常数线性组合 ⇒ 其同比依旧是各块同比的加权平均'
        '（权重非负、和为 1），上下界照旧两端可取。这条断言每跑一次都拿真实数据验一遍'
        '（见 build_payload 里的 hull 自检）。',

        f'<b>年度同比（Exhibit 5 / 6）是另一种 {TTM} 个月聚合，判定不改。</b>'
        '它按<b>日历年</b>切、且是<b>同月对同月</b>：未满的年份只拿已有的那几个月去比上年'
        '同样的几个月，绝不拿半年比全年。'
        f'与本页其余地方的滚动窗口相比，两者<b>都是 {TTM} 个月量级的聚合、都不受单月毛刺'
        '影响</b>，只是切法不同（一个按日历年、一个按最近 12 个月）；'
        '完整年份的 12 月那一格，两个口径在数学上恰好相等。'
        '<b>所以本页的图上没有任何一处是单月同比。</b>'
        '<b>唯一的单月同比在汇总表第 ① 组的 y/y 列</b> —— 那一列恒等于本行三列的算术'
        '（本月 ÷ 去年同月），给它印一个滚动同比读者自己一除就对不上，表内自相矛盾，'
        '所以只能在组标题与表注里标死、不能改；两个口径当期差多少，表注里现算印出来了。'
        '区间家的年度同比同样是紧界，但热力图一格只能放一个数，'
        '所以它们改用产品块的分解（Exhibit 6）呈现。'
        '汇总表的 m/m 列是单月环比 —— 那是「本月 vs 上月」的运营监控量，本来就该看单月。',

        '<b>差值图只覆盖合约腿。</b>现货成交额（HKEX 的 ADT、Euronext 的 ADNV、'
        'Xetra 的 turnover 等）源头就是金额，没有张数，所以它们不进那两张图；'
        '图里每一家的两根柱、以及差值，成分都是<b>同一批合约腿</b>，'
        '只有计量单位不同 —— 若成分不同，差值就不是「合约变小」而是「口径不同」。'
        f'<b>两侧的同比也必须同口径</b>（都取 {TTM} 个月滚动合计）：'
        '一侧滚动一侧单月，算出来的差是噪音差，不是结构差。',

        ('<b>差值恒为 0 的家为什么不画。</b>'
         '定基名义额是每条合约腿的张数各乘一个产品常数再相加。'
         '一家若只配了<b>一个</b>合约产品，两条序列就只差同一个常数，'
         '同比在数学上<b>恒等</b>，差值恒为 0 —— 这是构造出来的零，'
         '不是"这家没有把合约做小"。'
         + (f'本期这样的家：<b>{"、".join(DISP[k] for k in flat_keys)}</b>。'
            if flat_keys else '本期没有这样的家。')
         + (f'另有 <b>{"、".join(DISP[k] for k in gapblock_keys)}</b> 是配了 ≥2 个合约产品、'
            f'但合约块里有常数填不出来，名义额那一侧算不出，差值同样无从谈起 —— '
            f'这一类是<b>可以补上</b>的，与上一类的"结构性恒等"完全不同。'
            if gapblock_keys else '')
         + (f'另有 <b>{"、".join(DISP[k] for k in nocontract_keys)}</b> 一条合约腿都没有'
            f'（本页给它取的是股数或本币成交额，不是张数）。'
            if nocontract_keys else '')),

        '<b>一条必须留痕的告诫：名义额 ≠ 风险敞口。</b>利率池尤其危险 —— '
        '3 个月 SOFR 期货面值 100 万美元、久期约 0.25 年；10 年期国债期货面值 10 万美元、'
        '久期约 8 年。按名义额短端是长端的 10 倍，按 DV01（真正的风险敞口）却相反，'
        '<b>两者能差一个数量级</b>。所以本页的名义额只能读作「被交易的名义规模」，'
        '不可读作「谁承担了更多利率风险」。同样的告诫适用于能源（不同能源品热值不同）。'
        '要回答风险口径必须 DV01 加权 —— 📌 各交易所的月度成交报表都不含久期或 DV01 字段。',

        '<b>期权的名义额是「标的敞口」，不是权利金。</b>SPX 期权的名义额 = 张数 × 100 × '
        '基期指数点位，这是被交易的风险敞口口径，与交易所自己按张收费的 RPC 口径'
        '<b>不可互推</b>；把两者放在一起会得到一个既不是收入也不是敞口的数。',

        ('<b>缺月一律留空，唯一的例外写在这里。</b>某家某月只要有一条腿缺值，'
         '该家该月整月作废（图上断开），绝不只加"还在的那几条腿" —— 那会画出一次凭空的下跌。'
         + (f'唯一按 0 计入的是：{"、".join(zero_legs)}。{ZERO_WHY}' if zero_legs else '')),

        f'<b>核对表（Exhibit {table["n"]}）把两个口径并排列出</b>：定基名义额（US$bn/日，'
        f'仅常数齐备的 {len(ord3)} 家）与张数（张/日，{len(cnt_keys)} 家）。'
        f'<b>张数一列不需要任何常数</b>，所以它比名义额列多覆盖 '
        f'{len(cnt_keys) - len([k for k in ord3 if con_prod[k]])} 家 —— '
        f'官方发布的就是张数，这一列是全页与各家新闻稿逐位对账的唯一入口。'
        f'表同样只到 {mlab(LATEST)}，与全页门槛一致。',

        '<b>本页没有画任何断点线。</b>共同窗口内 12 家的头条口径均无并购并表或重分类需要'
        '标注，故 payload 里没有任何 <code>break_at</code>，相邻期可直读。'
        '日后若任一家出现口径变更，必须在这里登记并在对应图上画出 break。',
    ]

    head_bits = [
        f'指数化增长（{mlab(BASE)}=100）领先 {idx_rank[0][0]} {idx_rank[0][1]:,.0f}、'
        f'落后 {idx_rank[-1][0]} {idx_rank[-1][1]:,.0f}（精确口径 {len(grow_keys)} 家）',
        f'y/y（{TTM} 个月滚动合计口径）前三：{win_txt}',
        f'后三：{lose_txt}',
        f'同月的单月同比前三是 {"、".join(f"{a} {pct(b)}" for a, b in yy_month[:3])}'
        + ('（排序一致，但幅度差得远）' if _same_order else '（连排序都不一样）')
        + '，本页不采用',
        f'拐点（同口径）：{turn_txt}',
    ]
    if band_keys:
        head_bits.append(
            f'缺常数 {len(gap_prods)} 个 product_id ⇒ {len(band_keys)} 家只给紧界区间'
            + (f'（{"、".join(f"{DISP[k]} {rng_pct(float(TYOYLO[k][CUR]), float(TYOYHI[k][CUR]))}" for k in band_keys)}）'))
    if mix_keys:
        head_bits.append(
            f'张数 − 名义额同比差（{len(mix_keys)} 家可测）最大 {gap_rank[0][0]} '
            f'{pp(gap_rank[0][1])}（正 = 增长来自合约变小）、最小 {gap_rank[-1][0]} '
            f'{pp(gap_rank[-1][1])}')
    if jp is not None:
        head_bits.append(f'JPX 同一批合约两个单位：张数 {pct(jp["raw_yoy"])} vs 大合约当量 '
                         f'{pct(jp["lgeq_yoy"])}（差 {pp(jp["gap_pp"])}）')
    head_bits.append(f'共同最新月 {mlab(LATEST)}，短板 {"、".join(LAG)}')

    payload = {
        'ticker': TICKER,
        'tracker': 'Twelve Exchange Operators — Constant-Basis Notional',
        'title': f'12 家交易所总览：谁在跑赢、谁在拐点 — {zh(LATEST)}',
        'data_through': str(LATEST),
        'through_label': f'{zh(LATEST)}（共同最新月）',
        # subtitle 走 page.js 的 set()（textContent），**不能带 HTML 标签** ——
        # 标签会被原样印成字面量。要加粗只能在 note / notes / summary / footer 里。
        'subtitle': (f'数据源：12 家官方月度披露 · 主口径「定基名义额」'
                     f'（张数 × 乘数 × {mlab(BASE)} 价格，汇率同锁 {mlab(BASE)}）· '
                     f'共同窗口 {mlab(BASE)} – {mlab(LATEST)}（{len(IDX)} 个月）· '
                     f'增长口径 12 家全在（{len(grow_keys)} 家精确点值、'
                     f'{len(band_keys)} 家紧界区间）；水平值口径只含常数齐备的 {len(lvl_keys)} 家 · '
                     f'同比口径 = {TTM} 个月滚动合计（不是单月；年度同比另按日历年切）· '
                     f'短板 {"、".join(LAG)} · 版式仿 Goldman Sachs GIR · 仅图，无评论'),
        'headline': ' · '.join(head_bits),
        'hub_line': (f'共同最新月 {mlab(LATEST)}（短板 {"、".join(LAG)}）；'
                     f'指数化增长领先 {idx_rank[0][0]} {idx_rank[0][1]:,.0f}'
                     f'（{mlab(BASE)}=100）；{len(band_keys)} 家因缺基期常数只给区间'),
        'source': SRC,
        'xlabels': XL13,
        'xlabels_long': XL_LONG,
        'summary': summary,
        # 轴刻度小数位与截轴护栏：判据见 build/axisfmt.py（全站唯一实现）。
        'exhibits': axisfmt.fix_all(ex),
        'table': table,
        'notes': notes,
        'footer': (f'12 家交易所总览 · 主口径定基名义额（{mlab(BASE)} 价格与汇率锁死）· '
                   f'<b>发布门槛：共同最新月 {mlab(LATEST)}</b>，本期短板 {lag_txt} —— '
                   f'本页所有图表一律截到此月，'
                   + (f'跑在前面的 {"、".join(f"{d}（已更新至 {mlab(m)}）" for d, m in AHEAD)} '
                      f'的最新月份未纳入本页，请看其单公司页。'
                      if AHEAD else '本期 12 家最新月一致。')
                   + f'各家最新披露：{all_txt} · '
                     f'{len(gap_prods)} 个 product_id 缺 {mlab(BASE)} 基期常数：'
                     f'增长类图照常出（常数被约掉或给紧界），水平值类图只含常数齐备的 '
                     f'{len(lvl_keys)} 家 · '
                     '张数不可跨所加总，本页一律用定基名义额比较 · '
                     f'<b>同比口径 = {TTM} 个月滚动合计</b>（单月同比毛刺过大：本页 '
                     f'{len(VC)} 条产品块序列实测，{_obs_tot} 个「序列 × 月」观测里有 '
                     f'{_opp_tot} 个两个口径符号相反）；Exhibit 5/6 的年度同比按日历年切，'
                     f'同属 {TTM} 个月聚合 · '
                     'charts only, no commentary · personal research use'),
    }
    if source_date:
        payload['source_date'] = source_date
    diag = {
        'LATEST': LATEST, 'IDX': IDX, 'LAG': LAG, 'lasts': lasts,
        'lvl_keys': lvl_keys, 'grow_keys': grow_keys, 'band_keys': band_keys,
        'mix_keys': mix_keys, 'gap_prods': gap_prods,
        'idx_rank': idx_rank, 'yy_exact': yy_exact,
        'bands': {k: (float(TYOYLO[k][CUR]), float(TYOYHI[k][CUR])) for k in band_keys},
        'idx_bands': {k: (float(IDXLO[k][CUR]), float(IDXHI[k][CUR])) for k in band_keys},
        'gap': {k: float(gap[k][CUR]) for k in mix_keys},
        'vc': VC, 'sd_med': _sd_med, 'opp_tot': _opp_tot, 'obs_tot': _obs_tot,
        'straddle': straddle,
    }
    return payload, diag


def load_source_dates():
    """按路径加载仓库根的 source_dates.py（官方发布日台账）。

    不能裸 import：`python3 build/exchanges12.py` 跑起来时 sys.path 上只有 build/。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ────────────────────────────── 入口 ──────────────────────────────
def load_all():
    raw = {k: read_csv(k) for k in MEM_KEYS}
    specs = notional.load_specs(SERIES)
    fx = notional.load_fx(SERIES)
    return raw, specs, fx


def run(kconst_override=None, out_path=None, banner=None):
    """跑一遍。

    2026-08-06 起**缺基期常数不再拦页**：readiness 的 blocked 从「发不发页」的判据
    降级成「哪几家走区间口径」的输入。真·结构性失败（缺 CSV、基期无数据、窗口太短）
    仍然由 build_payload 里的 skip() 挡住。
    kconst_override 非空时走自检模式（见 selftest）。
    """
    raw, specs, fx = load_all()
    miss = [k for k in MEM_KEYS if raw[k] is None]
    if miss:
        skip('成员未就绪：' + '、'.join(f'{DISP[k]}（缺 series/{k}.csv）' for k in miss))

    lines, blocked, kconst = readiness(raw, specs, fx)
    print('换算就绪度（12 家 / %d 条腿）：' % sum(len(v) for v in LEGS.values()))
    for ln in lines:
        print(ln)

    if kconst_override is not None:
        kconst = dict(kconst)
        kconst.update(kconst_override)
        blocked = [b for b in blocked if b[1] not in kconst_override]

    if blocked:
        by_prod = {}
        for _key, prod, why in blocked:
            by_prod.setdefault(prod, set()).add(_key)
        print(f'\n缺基期常数的 product_id：{len(by_prod)} 个，'
              f'牵动 {len({k for k, _p, _w in blocked})} 家 —— **不拦页**，按降级规则处理：')
        for prod, keys in sorted(by_prod.items()):
            kind, _why = GAP_REASONS.get(prod, ('?', ''))
            print(f'  · {prod:24s} ← {"、".join(DISP[k] for k in sorted(keys))}'
                  f'（{GAP_KIND_ZH.get(kind, "未登记原因")}）')
        print('  增长类图照出（单产品块 ⇒ 常数被完全约掉；多块 ⇒ 给紧界区间）；'
              '水平值类图只含常数齐备的家。')
        print('  要让这几家回到水平值口径，把它们的 base_price_local / '
              'base_notional_per_unit_local 实测填进 series/contract_specs.csv。\n')

    src_date = load_source_dates().latest_of(SERIES, MEM_KEYS, {k: None for k in MEM_KEYS})
    payload, d = build_payload(raw, specs, fx, kconst, src_date)

    path = out_path or OUT
    payload_guard.write_dash(path, payload, TICKER)
    if banner:
        print(banner)
    print(f'共同最新月 {d["LATEST"]} | 短板 {"、".join(d["LAG"])} | '
          f'共同窗口 {d["IDX"][0]} → {d["IDX"][-1]}（{len(d["IDX"])} 个月）')
    print('各家最新：' + ', '.join(f'{DISP[k]}={d["lasts"][k]}' for k in MEM_KEYS))
    print(f'覆盖度：水平值可算 {len(d["lvl_keys"])} 家（{"、".join(DISP[k] for k in d["lvl_keys"])}）'
          f'｜增长精确 {len(d["grow_keys"])} 家（{"、".join(DISP[k] for k in d["grow_keys"])}）'
          f'｜增长给区间 {len(d["band_keys"])} 家'
          f'（{"、".join(DISP[k] for k in d["band_keys"])}）'
          f'｜口径差可测 {len(d["mix_keys"])} 家（{"、".join(DISP[k] for k in d["mix_keys"])}）')
    print('指数化增长排序（%s = 100，精确口径）：' % mlab(BASE)
          + '、'.join(f'{a} {b:,.1f}' for a, b in d['idx_rank']))
    if d['idx_bands']:
        print('区间口径的指数（下界–上界）：'
              + '、'.join(f'{DISP[k]} {lo:,.1f}–{hi:,.1f}'
                          for k, (lo, hi) in d['idx_bands'].items()))
        print('区间口径的 y/y（下界–上界）：'
              + '、'.join(f'{DISP[k]} {lo:+.1f}%–{hi:+.1f}%'
                          for k, (lo, hi) in d['bands'].items()))
    if d['gap']:
        print(f'张数 − 名义额同比差（pp，{TTM} 个月滚动合计口径，正 = 合约变小）：'
              + '、'.join(f'{DISP[k]} {v:+.2f}' for k, v in
                          sorted(d['gap'].items(), key=lambda kv: -kv[1])))
    # 口径自检：改口径的全部依据一行一条印出来，跑一次核对一次（图注里的数字同源）
    print(f'同比口径 = {TTM} 个月滚动合计（年度同比按日历年切，同属 {TTM} 个月聚合；'
          f'm/m 保持单月）')
    print(f'  逐月标准差中位降幅：滚动/单月 = {d["sd_med"]:.2f}；'
          f'符号相反 {d["opp_tot"]}/{d["obs_tot"]} 个「序列 × 月」观测')
    for name, v in sorted(d['vc'].items(), key=lambda kv: -kv[1]['n_opp']):
        print(f'  {name:34s} std {v["m_sd"]:6.1f}→{v["t_sd"]:5.1f}pp | '
              f'maxjump {v["m_jump"]:7.1f}({mlab(v["m_jump_at"])})→{v["t_jump"]:5.1f}pp | '
              f'符号相反 {v["n_opp"]:2d}/{v["n_both"]} | '
              f'当期 单月 {v["cur_m"]:+7.1f}% vs 滚动 {v["cur_t"]:+7.1f}%')
    print(f'Exhibit 1 汇总表 + Exhibit {payload["exhibits"][0]["n"]}-'
          f'{payload["exhibits"][-1]["n"]}（{len(payload["exhibits"])} 张）+ '
          f'Exhibit {payload["table"]["n"]} 核对表')
    print(f'写出 {path}（{os.path.getsize(path) / 1024:.1f} KB）')
    print(payload['headline'])
    return path


def selftest():
    """渲染管线自检 —— **不写 data/，不产生任何对外数字**。

    降级之后正式跑已经能出页，但正式跑走的是**降级分支**（band_keys 非空、
    lvl_keys 只有一部分），它证明不了「常数全填齐那天」的分支还画得出来 ——
    那条分支上 band_keys 为空、Exhibit 6 整张消失、Exhibit 2 的 must 列表为空，
    全是只有换一组常数才走得到的代码。
    所以这里用一组**合成常数**（每个缺价产品统一给 1.0 美元/单位，是显然假的占位值）
    把「常数齐备」那条分支也跑一遍，输出写到临时目录。
    与 build/test_pools.py 用 tempfile 合成夹具是同一个做法。
    """
    import tempfile
    raw, specs, fx = load_all()
    _lines, blocked, _k = readiness(raw, specs, fx)
    fake = {prod: 1.0 for _k2, prod, _w in blocked if prod != '—'}
    out = os.path.join(tempfile.mkdtemp(prefix='exchanges12_selftest_'), 'exchanges12.js')
    print('=' * 78)
    print('自检模式：以下数字全部无效 —— %d 个缺基期价的 product_id 被统一置成 '
          '1.0 美元/单位的假常数。' % len(fake))
    print('目的：跑通「常数齐备」那条分支（正式跑走的是降级分支，覆盖不到它）。'
          '不产生任何对外结论。')
    print('=' * 78)
    run(kconst_override=fake, out_path=out,
        banner='（自检输出，非交付物）')
    with open(out, encoding='utf-8') as f:
        f.readline()
        body = f.read()
    obj = json.loads(body[len('window.DASH = '):].rstrip().rstrip(';'))
    print(f'自检：payload 解析回来 {len(obj["exhibits"])} 张图、'
          f'汇总表 {len(obj["summary"]["rows"])} 行、'
          f'核对表 {len(obj["table"]["rows"])} 行 × {len(obj["table"]["cols"])} 列、'
          f'口径说明 {len(obj["notes"])} 条')
    kinds = sorted({e['kind'] for e in obj['exhibits']})
    bad = [k for k in kinds if k not in ENGINE_KINDS]
    print(f'自检：用到的 kind = {kinds}'
          + ('（均在 assets/charts.js 的 17 种之内）' if not bad
             else f'  ✗ 引擎不认识：{bad}'))
    # x 轴标签数 ≠ 数据点数时，charts.js 以标签数为准**静默丢点**（n = labels.length），
    # 图上少几个月不会报错也看不出来 —— 所以在这里当场核。
    for e in obj['exhibits']:
        if e['kind'] == 'heat_matrix':
            shape = (len(e['matrix']), {len(r) for r in e['matrix']})
            print(f'  Exhibit {e["n"]} heat_matrix：{len(e["rows"])} 行 × '
                  f'{len(e["cols"])} 列，matrix {shape[0]} × {sorted(shape[1])}'
                  + ('  ✗ 行列数对不上'
                     if shape[0] != len(e['rows']) or shape[1] != {len(e['cols'])} else '  ✓'))
            continue
        nx = len(e.get('xlabels') or obj['xlabels'])
        # range_band 的三条序列（lo / hi / actual）与 bars_labeled 的 values 都不在
        # series / groups 里，漏掉它们等于这两种图型完全没被核过长度。
        lens = ({len(s['values']) for s in e.get('series', [])}
                | {len(g['values']) for g in e.get('groups', [])}
                | {len(e[f]) for f in ('lo', 'hi', 'actual', 'values') if f in e})
        print(f'  Exhibit {e["n"]} {e["kind"]}：xlabels {nx}，序列长度 {sorted(lens)}'
              + ('  ✓' if lens == {nx} else '  ✗ 与 xlabels 不等长，charts.js 会静默丢点'))
    return out


def main():
    if '--selftest' in sys.argv:
        selftest()
        return
    run()


if __name__ == '__main__':
    main()
