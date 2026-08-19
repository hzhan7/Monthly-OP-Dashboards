# -*- coding: utf-8 -*-
"""竞争池定义 —— 交易所横截面页的唯一真值。

一个池 = 一个「这些数放在一起是同一件事」的断言。本文件只声明断言，不做计算；
换算由 build/notional.py 执行，画图由各页 build 脚本执行。

═══════════════════════════════════════════════════════════════════════════
一、为什么主口径是「定基名义额」而不是张数
═══════════════════════════════════════════════════════════════════════════
**张数不可比。** 单张合约的名义额 = 乘数 × 标的价格，而乘数是交易所自己选的
产品设计参数，不是竞争结果：CME 的 E-mini S&P 是 $50 × 指数，Micro E-mini 是
$5 × 指数 —— 同一个标的、同一个交易所，两个产品的张数差 10 倍。
把 micro 合约切得更细，张数份额立刻上升，可市场上并没有多一分钱的风险转移。
所以「张数份额」里混进了产品设计策略，它不是竞争胜负。

定基名义额把这一层剥掉：

    定基名义额 = 张数 × 乘数 × **基期价格**    基期锁 2019-01，汇率同样锁基期

价格项与汇率项都是常数 ⇒ 每条序列的**增长率与它的张数增长率完全相同**，
名义额只改变「产品之间」与「成员之间」的权重。于是：
  · 增长图里不含标的涨跌（不会把一轮牛市读成成交量增长）；
  · 份额图里不含汇率波动（欧元贬值不会让 Euronext"丢份额"）；
  · 跨交易所、跨币种、跨资产类的量第一次可以放进同一根轴。

另算一列**当期名义额**（当期价格 × 当期汇率），只回答「这个市场现在多大」，
**不进任何增长图与份额图**。它的同比里混着标的涨跌与汇率，读者一定会读错。

**张数在 series/ 里原样保留**（定基名义额本来就从张数算，源数据必须存张数）。
两个用途：(a) 与官方新闻稿逐位对账、验证解析正确；(b) 将来接收入模型（费率是
按张收的，不是按名义额收的）。张数**不进主图** —— 每个成员的 `contracts_col`
就是这些原列，只出现在页尾核对表里。

═══════════════════════════════════════════════════════════════════════════
二、必须留痕的两条告诫
═══════════════════════════════════════════════════════════════════════════
1. **利率池的名义额不等于风险敞口。** 3 个月 SOFR 期货面值 100 万美元、久期 0.25 年；
   10 年期国债期货面值 10 万美元、久期约 8 年。按名义额，短端合约的"体量"是长端的
   10 倍；按 DV01（真正的利率风险敞口）却反过来，两者能差一个数量级。
   所以 `rates` 池的占比只能读作「各货币曲线的名义额构成」，不可读作
   「谁承担了更多利率风险」或「谁的风险转移生意更大」。要回答后者必须 DV01 加权，
   而月度成交报表里没有久期字段（📌 未找到，检索路径见 notional.py 模块 docstring）。
   同类告诫适用于 `energy`（不同能源品的热值不同，名义额相同不等于能量相同）。

2. **源列是金额的成员只能"锁汇率"，锁不了价格。** HKEX 的 ADT、Euronext 的 ADNV、
   Xetra 的成交额都是「股数 × 当期价格」，官方不披露成交股数（📌 未找到：三家的
   月度报表都只给金额；检索路径 = 各家月报的 cash market 段），我们没法把价格项剥出来。
   这类池标 `deflator='fx_only'`，图注必须写明「已剔汇率、未剔标的涨跌」。
   **绝不能把 fx_only 的成员和 base_price 的成员放进同一个池算份额** ——
   分子分母的价格基准不同，占比是假的。validate() 会拦这一条。

═══════════════════════════════════════════════════════════════════════════
三、share 三档：这个池的分母是谁
═══════════════════════════════════════════════════════════════════════════
| share    | 分母             | 允许画                           | 禁止 |
|----------|------------------|----------------------------------|------|
| `'true'` | 官方披露的行业分母 | 堆叠份额带（含残差）、Δpp 排序、归因桥 | —— |
| `'pool'` | 本池成员之和      | 池内相对占比（图注必须点名分母是这 N 家） | 「市场份额」四个字 |
| `'none'` | 没有可用分母      | 水平值（若 levels=True）、指数化、同比 | 任何形式的占比 |

**全仓只有北美两池 + fn_monopoly 是 `'true'`**，且都靠 ICE 一家带进来的行业分母。
这是 ICE 排在实现路线第一批的全部理由 —— 它的价值不是多一条线，是把分母带进来。

北美两池另标 `dual_unit=True`（额外出一张张数口径份额图）。它的意义**不是**"另一个
答案" —— 名义额份额与张数份额在这两池里恒等（同一批合约、同一个基期常数，分子分母
同乘一个数）—— 而是**唯一的对账通道**：官方自报的份额只有张数口径。
可对账的成员在 `selfreport` 里声明，`selfreport_checks()` 让它机械可执行。
实测（series/ice.csv 全部 187 个月）：na_cash 中位偏差 0.027pp / 最大 0.072pp，
na_multilist_opt 中位 0.022pp / 最大 0.051pp，容差一律取实测上界留一档余量的 0.10pp。

改用定基名义额之后，原设计稿（docs/verify/_design.md）里因**规格不一致**而定成 `'none'` 的池
（eu_deriv / apac_cash / apac_deriv / rates / equity_index / single_stock_etf_opt /
energy / ags / fx_futures）现在都能算池内占比了，一律升到 `'pool'`。
留在 `'none'` 的只剩两个，理由与单位无关，所以新口径救不了它们：
  · `fn_listing` —— 上市家数是计数，募资额是流量，两者都不构成一个可加总的"池"；
  · `fn_index_aum` —— 全球指数挂钩资产的分母远大于 MSCI + STOXX/DAX 两家之和，
    两家之和的占比会被读成「指数行业二分天下」。

`levels` 是与 share 正交的一个新字段，也是新口径带来的新能力：
**占比不成立不等于水平值不可比**。定基名义额把所有池的量都换成了同一个单位
（USD bn/day），所以 `share='none'` 的池现在也能把绝对值画进同一根轴 ——
这在张数口径下是被明令禁止的。

═══════════════════════════════════════════════════════════════════════════
四、head 与 members 是两个清单
═══════════════════════════════════════════════════════════════════════════
· `head`    = 决定本池共同最新月与共同起点的成员。必须**历史长、发布快、无空洞**。
· `members` = 进图的全部成员。历史短的成员在长历史图上前段留 None，引擎在缺口处
              断线（`L()` 已经这么做），**不会**把共同窗口砍到它的起点。

这条是被 TMX 现货（2021-08 起，比 HKEX 还短 2 年 7 个月）逼出来的：把它算进 head，
北美现货池的共同窗口会从 2011 年砍到 2021 年，为一个尾部对照成员扔掉十年历史。
`build/exchanges.py:240-243` 本来就只对 head 列查空洞，所以这个模型不需要改引擎。

**慢腿列不进 panel。** DB1 的 Clearstream / OTC / 360T、NDAQ 的 marketshare xlsx
（次月第 10 个工作日）天生会在最新月留空，而 exchanges.py 对共同窗口内的空洞直接
raise。这些列只能进单公司页，不进任何池 —— 见各池的 `excluded`。

**每池 ≤5 家。** 数据色只有 NAVY / BLUE / MBLUE / GRAY / GREEN / GOLD 六个
（RED 是断点与截轴离群值专用），份额堆叠带还要留一个给「其余」残差段。
超编时按「该成员在本池是否有不可替代的信息」取舍，被拿掉的进 `excluded`
并注明它在哪一页出场 —— 不是删掉，是搬家。

═══════════════════════════════════════════════════════════════════════════
五、换算链：build 脚本必须能机械执行，不许人肉判断
═══════════════════════════════════════════════════════════════════════════
每个成员的 `chain` 是一串**腿**，每条腿都是一次完整的换算：

    {'csv': 'ice.csv',                    # 不给则用成员自己的 csv
     'col': 'adv_nyse_tapeA_matched_mnsh', # 源列（**必须是 series/*.csv 里真有的列名**）
     'src': 'shares',                      # contracts | shares | notional
     'unit_scale': MN,                     # 源列 → 规范单位（张 / 股 / 本币元），恒为正
     'per_day': None,                      # 源列是月度总量时给 {'csv','col','div_col'}
     'sign': 1,                            # ±1，见下方「减法腿」
     'of_col': None,                       # 减法腿专用：它修正的是哪条主列
     'since': None,                        # 'YYYY-MM'，这条腿的生效起点
     'product': 'US_CASH_EQUITY_SHARE'}    # → contract_specs.csv → ccy → fx.csv

**列名的唯一事实来源是 series/*.csv 的表头，不是侦察稿里的建议名。**
本文件第一版是在任何一张交易所 CSV 落地之前写的，为 8 张还不存在的表凭空发明了
三十多个列名（adv_index_deriv_kcontracts / ddav_kcontracts / mx_adv_stir_kcontracts …），
而 check_columns() 把「表还没建」记成 pending 不算错 —— 于是测试全绿、
第一张真表一到就 0/3 命中。这一版的每一个列名都是 `head -1 series/*.csv` 逐个核过的。

**减法腿（sign=-1）** 用来还原并购前的可比口径。Euronext 从 2025-11 起把 Athens
并进主列，同时给了一列「其中属于 Athens 的那块」的备注列，主列 − 备注列 = legacy
Euronext；不这么做，单股衍生品那条线在 2025-11 会有 20 倍以上的假跳
（docs/verify/enx.md 口径坑 2 实测：2025-10 主列 35,573 → 2025-11 836,511，其中 Athens 781,183）。
减法腿必须同时写 `since` 与 `of_col`：备注列 2021-01 就有值，但 2025-10 及以前主列
**并不含它**（实测 2025-08 单股期货主列 0.080 千张/日、备注列 28.553），无脑相减是负数。
`of_col` 指向被修正的那条主列，notional.resolve_chain 据此逐对断言「备注列 ⊆ 主列」；
只查整链合计是不够的 —— 同一条链里的单股期权有 233.9 千张/日，
会把那 −28.47 盖成正的 349.7，整链护栏一声不吭。两道护栏都在，缺一个就漏。

`since` 同样用来表达「这一块当时确实还不存在」：MIAX 的 Pearl / Emerald / Sapphire
分别 2017-02 / 2019-03 / 2024-08 才开业，这些月份不是数据缺失而是零。
若按缺值处理（add_series 遇 None 整月置 None），四所合计会被砍到 2024-08 才起步。

`per_day` 的 `div_col` 是「**隐含**交易日」：源表给了月度总量与官方日均却没给日数
（SGX），两者相除就是交易所自己记账用的那个日数。不许拿证券市场的 sec_trading_days
去除衍生品量 —— 那是另一套日历。

链的最后一跳取哪一档汇率**不由腿自己说了算**，由池的 `flow` 机械推出：
`fx_basis(p)` → 'avg'（流量：成交额、募资额）或 'eom'（存量：AUM）。
build 脚本一律 `notional.resolve_chain(..., basis=pools.fx_basis(p))`，
不要在调用点手写 'avg' / 'eom' 字面量 —— fetch/fx.py 把「两列混用」列为它唯一一个
「用错了不会报错」的坑：拿月末汇率折整月成交额 = 把整月流量按最后一天记账，
拿月均折 AUM = 给时点余额安一个不存在的平均价。两种错都只在同比里多一段汇率噪声。
（fx.csv 是**宽表**：一行一个月、每币种 fx_avg_<ccy>usd 与 fx_eom_<ccy>usd 两列，
方向是「1 单位外币 = 多少美元」，所以是**乘**不是除。）

多条腿**先各自换算成名义额、再相加**（notional.resolve_chain 保证这个顺序）。
先把不同乘数的张数加起来，等于给这个成员编了一个并不存在的"平均合约"，
而它的值会随月度品种结构漂移，图上完全看不出来。

`src` 必须与 contract_specs.csv 里该产品的 `kind` 一致，notional.resolve_leg 会核。
`PRODUCTS` 是本文件对规格表的**需求清单**：每个 product_id 要什么、币种是什么、
基期乘数与价格该去哪儿取。清单里**一个数字都没有** —— 数字必须实测后写进
series/contract_specs.csv，那张表才是权威。

═══════════════════════════════════════════════════════════════════════════
六、张数口径成员（`contracts_only`）：不是缺口，是终局
═══════════════════════════════════════════════════════════════════════════
成员上的 `contracts_only=True` 表示：**这条腿永久停留在张数口径**，
只进增长图（指数化 / 同比），不进水平值图，不进任何份额的分子或分母。

必须有这个字段，是因为原先这个状态是**隐式**的 —— 靠 contract_specs.csv 里两个
空格子表达。而空格子在本仓的约定含义是「还没测出来」（`notional.pending_products`
就是这么读它的，build 脚本据此整池 skip）。两件完全不同的事共用一种表示：

    「还没测出来」  → 下一个人应该去测
    「测出来也不该用」→ 下一个人**不应该**去测

隐式表达的代价是具体的：ICE 的两档利率，上一轮已经有人把 reCAPTCHA、
409、规则手册全撞了一遍，结论写在 build/basefill/ice_enx2.py 的 docstring 里，
而 pools.py 这边看不见 —— 下一个人只会看到两个空格子，然后再撞一遍。

目前唯一的一组：`rates.ice` 与 `eu_deriv.ice`（product = ICE_STIR / ICE_MLTIR）。
理由写在 `ICE_RATES_CONTRACTS_ONLY` 常量里，两条各自独立成立 ——
① 官方把短端与中长端并成一列，拆不开；② **即便拆开，名义额对利率衍生品本身就是
误导性单位**（同名义额下 2 年期与 10 年期的 DV01 差 5 倍以上）。
第②条与能不能拿到分合约张数无关，所以这不是一个"等着被补上"的缺口。

三处配套，缺一个这个状态就又变回隐式的：
  · `contracts_only_why`（成员级）—— 写给下一个改代码的人，validate() 强制;
  · `contracts_only_note`（池级）—— 写给**看图的人**：「这条线为什么只在增长图里」，
    validate() 同样强制。没有它，读者会以为水平值图漏画了一家;
  · `products_needing_specs()` —— build 脚本判断「这个池能不能画」时用它，
    **不要用 `products_used()`**。后者会把这两个永久空常数当成待办，
    让 rates 与 eu_deriv 两页永久 skip —— 拿一个口径判断毁掉两页本来成立的图。

为什么增长图里放它一点折扣都不打：定基名义额 = 张数 × 常数，常数是常数，
所以**增长率与张数增长率恒等**。增长图上它与别人完全可比；不可比的只有水平值与占比。

═══════════════════════════════════════════════════════════════════════════
七、口径一致优先于覆盖率：ICE 能源那一腿的取舍
═══════════════════════════════════════════════════════════════════════════
`energy` 池的 ICE 腿 2026-08-06 由 `adv_energy_kcontracts`（ICE 全球全能源）
换成 `adv_brent_kcontracts`（仅 Brent），产品由 `ICE_ENERGY` 换成 `ICE_BRENT_IFEU`。

换掉的理由不是"全能源太难"，是**分子分母不同源**：ICE 唯一公开、不要 reCAPTCHA 的
分产品历史表（ice.com/report/7）只覆盖 ICE Futures Europe，2019-01 各能源列相加
只占全球口径的 67.0%，而 TTF 在 ICE Endex 上根本不在那张表里，且它**没有固定乘数**。
拿 67% 子集的品种结构算出一个篮子常数、再乘 100% 的量，得到的是一个
**方向与大小都不可知**的系统性偏差 —— 而它在图上完全看不出来（柱子只是整体高一截）。

换上的 Brent 一列则是口径自洽的：官方脚注(1) 明写迷你合约已被折成
「ICE Futures Europe 标准当量」，于是一个乘数（1,000 桶）对整列精确成立，
不需要权重、没有覆盖率缺口。代价是这条腿只代表 ICE 能源的约三分之一
（2019-01 34.8%，187 个月中位 33.3%）——**这个代价写在池的 `scope_note` 里，
必须落到图注上**，不许让读者把三分之一读成全部。

一句话的取舍准则，本仓通用：
    **宁可缩小产品范围让分子分母口径一致（覆盖率低但零偏差），
      也不要拿部分口径的参数去套全口径的数据。**
覆盖率低是**看得见**的缺陷（写在图注上，读者知道自己在看什么）；
口径不一致是**看不见**的缺陷（图上一切正常，结论已经错了）。

用法: python3 build/pools.py     （打印全部池的体检结果，不写任何文件）
"""

import os
import re

import notional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')

BASE_MONTH = notional.BASE_MONTH        # '2019-01'，全仓唯一基期

# ── 数量级：源列写法 → 规范单位（张 / 股 / 本币元）。这些是单位换算，不是实测值 ──
K, MN, BN, TN = 1e3, 1e6, 1e9, 1e12
ONE = 1.0

# ── 单位显示文案 ────────────────────────────────────────────────────────────
# 「跨池不可比、同池内可比」这条在张数口径下成立；换成定基名义额之后，
# 主口径的三个池间单位第一次统一了，所以文案里必须把基准写死，否则读者会
# 把 base-2019-01 的量和 current 的量混着看。
U_BASE = 'USD bn/day, base-2019-01 prices & FX'      # 主口径：定基名义额（日均）
U_BASE_MO = 'USD mn/month, base-2019-01 FX'          # 月度流量（募资额）
U_FXONLY = 'USD bn/day, base-2019-01 FX, current prices'   # 源列是金额，价格剔不掉
U_FXONLY_STOCK = 'USD bn, base-2019-01 FX, current prices'  # 存量（AUM）
U_CURRENT = 'USD bn/day, current prices & FX'        # 当期名义额，只答"现在多大"
U_KCTR = 'k contracts/day'                           # 张数，对账用，不进主图
U_SHARE_PP = 'pp'                                    # 份额序列本身
U_COUNT = 'count/month'                              # 纯计数

PALETTE = ('NAVY', 'BLUE', 'MBLUE', 'GRAY', 'GREEN', 'GOLD')   # RED 是断点专用
MAX_MEMBERS = 5                                      # 6 色 − 1 个残差色

# ── MIAX 四所的多重挂牌期权 ADV：一所一条腿 ────────────────────────────────
# miax.csv 里有两套期权量列，重叠期实测比值 0.9967–0.9976
# （docs/verify/verify_miax.md §2.8，差异来自 PDF 四舍五入到整千张）：
#   · IR 月报列 adv_multilist_options_kcontracts —— 四所合计，但只有 2025-01 起 19 个月；
#   · API 列 adv_{miax,pearl,emerald,sapphire}_options_api_kcontracts —— 分所给，
#     最早一条到 2015-04。
# 池里取 API 那套，因为 na_multilist_opt 的看点就是「MIAX 十年从 7% 爬到 18%」，
# 用 IR 列这条主线只剩 19 个月。
# `since` 写的是**该所开业的月份**（各列首个非空月实测）：Pearl 2017-02、
# Emerald 2019-03、Sapphire 2024-08 之前这几所根本不存在，那些月份是**零不是缺**。
# 不写 since 的话 add_series 遇 None 整月置 None，四所合计会被砍到 2024-08 才起步。
MIAX_OPT_VENUES = (('miax', '2015-04'), ('pearl', '2017-02'),
                   ('emerald', '2019-03'), ('sapphire', '2024-08'))
MIAX_OPT_COLS = ['adv_%s_options_api_kcontracts' % k for k, _s in MIAX_OPT_VENUES]


def miax_multilist_legs():
    """MIAX 四所合计的换算链。每次调用返回新的 list —— 池定义之间不共享可变对象。"""
    return [{'col': 'adv_%s_options_api_kcontracts' % k, 'src': 'contracts',
             'unit_scale': K, 'per_day': None, 'since': since,
             'product': 'US_MULTILIST_EQ_OPT'}
            for k, since in MIAX_OPT_VENUES]


# ── Euronext legacy 口径：主列 − athex 备注列 ──────────────────────────────
# 官方在每个主指标右侧配一列 `Athex` 备注列，含义**随月份翻转**
# （docs/verify/enx.md 口径坑 1，用官方 Q2-2026 业绩稿反推验证过）：
#   · 2025-10 及以前：主列**不含** Athens，备注列是 Athens 单独数
#     ⇒ 主列 + 备注列 = 官方 pro-forma；
#   · 2025-11 及以后：主列**已含** Athens，备注列是主列里属于 Athens 的那块
#     ⇒ 主列 − 备注列 = legacy Euronext。
# 池里一律取 legacy（并购前可比口径），所以减法腿的 since 卡在 2025-11。
# 少了这个 since，2021-01 – 2025-10 会减掉一块从没加进来的量：实测 2025-08 单股期货
# 主列 0.080k、备注列 28.553k，硬减得 −28.47 千张/日 —— notional.resolve_chain 会当场炸。
ENX_ATHEX_SINCE = '2025-11'
ENX_ATHEX_WHY = ('Athens 2025-11 并入主列，减掉官方备注列还原并购前的 legacy Euronext'
                 '（docs/verify/enx.md 口径坑 1）')


def enx_legacy_legs(cols, product, unit_scale=K, src='contracts'):
    """Euronext legacy 口径的换算链：主列先各自换算相加，再减去对应的 athex_* 备注列。

    备注列的列名规则是主列名加 `athex_` 前缀（实测 enx.csv 表头逐列成对）。
    没有备注列的主列不许传进来 —— 那说明这块业务本来就没有 Athens 成分
    （MATIF 农产品就是这样），凭空造一个减法腿会读到不存在的列。
    """
    legs = [{'col': c, 'src': src, 'unit_scale': unit_scale, 'per_day': None,
             'product': product} for c in cols]
    # of_col 把减法腿与它所修正的主列绑起来，让「备注列 ⊆ 主列」这条断言
    # 逐对可查。只查整链合计是不够的：实测 2025-08 单股期货 0.080 − 28.553 = −28.47，
    # 但同链的单股期权有 233.9，合计仍是正的，整链护栏抓不到。
    legs += [{'col': 'athex_' + c, 'of_col': c, 'src': src, 'unit_scale': unit_scale,
              'per_day': None, 'sign': -1, 'since': ENX_ATHEX_SINCE,
              'why': ENX_ATHEX_WHY, 'product': product} for c in cols]
    return legs

# ── 永久张数口径的成员：ICE 的两档利率 ────────────────────────────────────
# 2026-08-06 定案。这段文字同时出现在 rates 与 eu_deriv 两个池的 ICE 成员上，
# 所以写成一个常量 —— 抄两份就会有一天只改了一处，而两页说法不一致是看不出来的。
# ⚠ 这**不是**「还没测出来」。`contract_specs.csv` 里 ICE_STIR / ICE_MLTIR 的
#   base_price_local 会永远是空的，本仓也不再为它们留 TODO。
ICE_RATES_CONTRACTS_ONLY = (
    '⛔ **本成员永久停留在张数口径**：只进增长图（指数化 / 同比），'
    '不进水平值图，也不进任何份额的分子或分母。两条理由各自独立成立 ——\n'
    '① **官方拆不开。** ICE 唯一公开、不要 reCAPTCHA 的分产品历史表 '
    'https://www.ice.com/report/7 把短端与中长端并成**一列** Interest Rates'
    '（2019-01 期货 37,491,346 + 期权 7,632,263 = 45,123,609 张，'
    '与 ice.csv 的 adv_stir + adv_mltir = 45,122,000 张只差 0.004% ⇒ 确实是同一批合约）；'
    '要拆到合约层只有 Report Center 的 report 26/27，'
    '其 metadata 写着 recaptchaRequired=true、criteria 接口不带 token 恒返回 HTTP 409'
    '（build/basefill/ice_enx2.py 实测）。绕验证码是明令禁止的动作，'
    '人工点一次也无法让 cron 复算。'
    '另外 ICE Futures Europe 的官方规则 SECTION NNNN 通篇只有 '
    '"Contract Multiplier €2,500"，**没有任何 nominal / notional / face value 字样** —— '
    'Euribor 的 €1,000,000 是从每点欧元数反推的，反推值不许进规格表。\n'
    '② **即便拆开，名义额对利率衍生品本身就是误导性单位。** '
    '同样 1 亿美元名义额，2 年期与 10 年期的 DV01 差 5 倍以上；'
    '3M 合约面值 100 万、久期 0.25 年，10Y 国债期货面值 10 万、久期约 8 年 —— '
    '按名义额短端是长端的 10 倍，按风险反过来。'
    '正确的单位是 DV01 或久期加权名义额，而月度成交报表里没有久期字段'
    '（📌 未找到：CME / ICE / Eurex / MX / JPX 的月度报表都不含久期或 DV01；'
    '检索路径 = 逐合约取到期日与票息自行计算曲线，那是一整套需要每月维护的数据，'
    '远超本仓无人值守的边界）。\n'
    '⇒ 所以这**不是等着被补上的缺口**：理由②与能不能拿到分合约张数无关，'
    '就算哪天 report 26/27 开放了，结论也不变。'
    '增长图里它是完全合法的 —— 定基名义额的增长率与张数增长率恒等（价格项是常数），'
    '所以这条线放在增长图里与别人比，一点折扣都不打。')

SHARE_TIERS = ('true', 'pool', 'none')
UNIT_KINDS = ('notional', 'share_pp', 'count_and_raise')
DEFLATORS = ('base_price', 'fx_only', None)
# flow 的合法取值就是「有汇率基准可推」的那几个，所以直接取自映射表的键 ——
# 在这里另抄一份 ('per_day','per_month','stock')，加第四种 flow 时就会漏改一处，
# 而症状是那个池的 fx_basis() 抛异常、整页 skip，且没人看得出为什么。
FLOWS = tuple(notional.FLOW_TO_FX_BASIS)
# src（这一列装的是什么）→ kind（这个产品是什么）的映射只有 notional.py 一份，
# 这里直接引用，不另抄一份 —— 抄一份就迟早有一处漏改。
SRC_KINDS = notional.SRC_KINDS


class PoolSpecError(RuntimeError):
    """池定义本身写错了 —— 结构、配色、换算链、share 档次的自洽性问题。"""


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCTS —— 对 series/contract_specs.csv 的需求清单
# ═══════════════════════════════════════════════════════════════════════════
# 这里**一个数字都没有**。乘数与基期价格必须来自官方一手披露（合约规格页 / 月度
# 报表 / 年报），实测后写进 series/contract_specs.csv；本清单只声明「需要哪些产品、
# 它是哪一类、计价币种是什么、去哪儿取规格」。
#
# ccy 为 None = 该 product 是**跨币种的合成篮子**，币种要在规格表里定死一个记账币
# 并把合成方法写进 evidence 列。篮子的 base_notional_per_unit_local 不是某个合约的
# 规格，而是「基期(2019-01)按品种成交量加权的单张平均名义额」—— 这是本设计里
# 最容易做错的一处：它必须用**基期那个月**的品种结构算一次然后写死，
# 绝不能每月重算，否则价格项就不再是常数，定基口径当场失效。
#
# basket=True 的产品同理（单一币种但多个合约）。
_P = lambda zh, exch, kind, ccy, basket, src: {          # noqa: E731
    'zh': zh, 'exchange': exch, 'kind': kind, 'ccy': ccy,
    'basket': basket, 'spec_source': src}

PRODUCTS = {
    # ── 现货股票：kind='share'，乘数恒为 1，"基期价格" = 基期平均成交价/股 ──
    'US_CASH_EQUITY_SHARE': _P(
        '美国上市股票（合并市场平均一股）', 'US', 'share', 'USD', True,
        '基期平均成交价 = 2019-01 全美合并成交金额 ÷ 合并成交股数。'
        '📌 未找到现成的单一官方字段：ICE/Cboe/Nasdaq 的月度成交表只给股数不给金额。'
        '检索路径 = ICE 月度 metrics 的 consolidated volume（股数）配 SEC 的 '
        'Market Structure 数据或各所自己的 dollar volume 披露；两者必须同一个月同一个口径。'),
    'CA_CASH_EQUITY_SHARE': _P(
        '加拿大上市股票（平均一股）', 'TMX', 'share', 'CAD', True,
        'TMX 月度 Trading Statistics 同时给 volume（股）与 value（加元），'
        '取 2019-01 的 value ÷ volume。'),

    # ── 期权 ──
    'US_MULTILIST_EQ_OPT': _P(
        '美国多重挂牌股票/ETF 期权', 'US', 'contract', 'USD', True,
        '乘数是行业惯例的 100 股/张（OCC 合约规格）；基期价格 = 2019-01 加权平均标的价。'
        '📌 未找到按成交量加权的标的均价的官方单一字段；'
        '检索路径 = OCC 月度成交报表配 CBOE 的 average premium / notional 披露。'),
    'CBOE_INDEX_OPT': _P(
        'Cboe 指数期权（SPX / VIX / XSP / RUT 合成篮子）', 'Cboe', 'contract', 'USD', True,
        'Cboe 各指数期权的合约规格页给乘数（各产品不同）；基期价格取 2019-01 各标的'
        '指数收盘价，按该月各产品 ADV 加权成一个篮子常数。'),
    'NDAQ_US_OPT': _P(
        'Nasdaq 六所美股期权（含指数，官方不拆）', 'Nasdaq', 'contract', 'USD', True,
        'Nasdaq 只披露六所合计且含指数期权，拆不开（verify_ndaq）。'
        '篮子常数只能按 2019-01 的 multilist / index 结构估一次并在 evidence 写明假设。'),

    # ── 欧洲现货：源列已是金额 ──
    'EU_CASH_ADNV_EUR': _P(
        '欧洲现货股票成交额（€）', 'EU', 'notional', 'EUR', False,
        'kind=notional ⇒ multiplier 与 base_price_local 都填 1，只用基期 EUR/USD 汇率。'),

    # ── 欧洲衍生品 ──
    'EUREX_RATES': _P('Eurex 利率衍生品（Bund/Bobl/Schatz/Buxl…）', 'Eurex',
                      'contract', 'EUR', True,
                      'Eurex 合约规格页给各合约面值（Bund = €100,000）；'
                      '基期价格 = 2019-01 各合约结算价（占面值百分比），按该月成交量加权。'),
    'EUREX_INDEX': _P('Eurex 股指衍生品（ESTX50 / DAX 系）', 'Eurex',
                      'contract', 'EUR', True,
                      'Eurex 规格页给每点欧元数（ESTX50 €10/点、DAX €25/点，micro 另计）；'
                      '基期价格 = 2019-01 各指数收盘，按成交量加权。'),
    'EUREX_EQUITY': _P('Eurex 单股衍生品（含单股期货）', 'Eurex',
                       'contract', 'EUR', True,
                       '⚠ 与美国的纯期权列不同源，含单股期货。乘数多为 100 股/张但'
                       '各标的不同，篮子常数按 2019-01 成交结构合成。'),
    'ENX_INDEX_DERIV': _P('Euronext 股指衍生品（CAC / AEX / BEL，期货 + 期权）', 'Euronext',
                          'contract', 'EUR', True,
                          'Euronext 衍生品规格页给每点欧元数（CAC40 €10/点）。'
                          '⚠ 篮子含期货与期权两条主列，基期结构按 2019-01 两列的成交量加权。'),
    'ENX_SINGLESTOCK_LEGACY': _P(
        'Euronext 单股衍生品（legacy 口径，剔 Athex）', 'Euronext',
        'contract', 'EUR', True,
        '⚠ 必须用 legacy 口径（主列 − athex_* 备注列，减法腿 since=2025-11），'
        '否则 2025-11 有 20 倍以上的假跳（docs/verify/enx.md 口径坑 2）。'
        '基期 2019-01 早于 Athens 并表，所以篮子常数本身就是 legacy 结构，不受影响。'),
    # ⛔ 下面两个是**永久张数口径**产品，见模块 docstring 六。它们的 spec_source
    #    写的不是「去哪儿取」，而是「为什么这条路永久关闭」—— 因为把它当成
    #    「还没测出来」会让下一个人一次次回来撞同一堵墙。
    'ICE_STIR': _P('ICE 短端利率（Euribor / SONIA / €STR）', 'ICE',
                   'contract', None, True,
                   '⛔ 永久张数口径，不填基期常数。两条理由各自独立成立：'
                   '① **拆不开**：ICE 官方 report/7（唯一不要 reCAPTCHA 的 IFEU 分产品历史表）'
                   '把 STIR 与 MLTIR 并成一列 Interest Rates（2019-01 期货 37,491,346 + '
                   '期权 7,632,263 = 45,123,609 张，与 ice.csv 两列之和 45,122,000 差 0.004%），'
                   '分合约张数只在 Report Center 的 report 26/27 后面，'
                   'metadata recaptchaRequired=true、criteria 恒 HTTP 409'
                   '（build/basefill/ice_enx2.py 实测）；而且 ICE Futures Europe 的官方规则'
                   '（SECTION NNNN）通篇只写 "Contract Multiplier €2,500"，**没有面值**，'
                   'EUR 1,000,000 是反推值，反推值不许进表。'
                   '② **即便拆开，名义额对利率衍生品本身就是误导性单位**：同名义额下 '
                   '2 年期与 10 年期的 DV01 差 5 倍以上。正确单位是 DV01 或久期加权名义额，'
                   '而月度成交报表里没有久期字段 —— 那是另一个量级的工程。'
                   '⇒ 这条腿只进增长图（增长率与张数增长率恒等），不进水平值与份额图。'),
    'ICE_MLTIR': _P('ICE 中长端利率（Gilt 等）', 'ICE', 'contract', None, True,
                    '⛔ 永久张数口径，理由同 ICE_STIR（① 官方并成一列拆不开；'
                    '② 名义额对利率衍生品是误导性单位）。'
                    '⚠ 与 STIR 不同的是**面值这一半是有的**：ICE 官方规则 SECTION RRRR 原文 '
                    '"Unit of Trading £100,000 nominal value notional Gilt" —— '
                    '但只有面值没有权重，且第二条理由（DV01）与面值有没有无关，'
                    '所以结论一样：不填。'),

    # ── 亚太现货：源列已是金额 ──
    'HK_CASH_ADT_HKD': _P('HKEX 现货成交额（HK$）', 'HKEX', 'notional', 'HKD', False,
                          'kind=notional，只用基期 HKD/USD 汇率。'),
    'JP_CASH_ADT_JPY': _P('JPX 现货成交额（¥）', 'JPX', 'notional', 'JPY', False,
                          'kind=notional，只用基期 JPY/USD 汇率。'),
    'SG_CASH_SDAV_SGD': _P('SGX 现货成交额（S$）', 'SGX', 'notional', 'SGD', False,
                           'kind=notional，只用基期 SGD/USD 汇率。'),
    'AU_CASH_ADT_AUD': _P('ASX 现货成交额（A$，on-market）', 'ASX',
                          'notional', 'AUD', False,
                          'kind=notional，只用基期 AUD/USD 汇率。'),

    # ── 亚太衍生品 ──
    'HKEX_DERIV': _P('HKEX 衍生品合计（期货 + 期权）', 'HKEX', 'contract', 'HKD', True,
                     'HKEX 产品规格页给各合约乘数（HSI 期货 HK$50/点、Mini HK$10/点）；'
                     '篮子常数按 2019-01 各产品成交量加权。'),
    'SGX_DERIV': _P('SGX 衍生品合计', 'SGX', 'contract', None, True,
                    '⚠ 跨币种（FTSE China A50 与 Nikkei 以 USD 计、Nifty 以 USD、'
                    'MSCI Singapore 以 SGD）。记账币在规格表里定死。'),
    'JPX_DERIV': _P('JPX 衍生品合计', 'JPX', 'contract', 'JPY', True,
                    '⚠ 原始张数被 mini(1/10) 与 micro(1/100) 严重扭曲 —— '
                    '这正是名义额口径要解决的问题：篮子常数用 2019-01 的产品结构'
                    '按**各自真实乘数**加权，扭曲自动被吸收，'
                    '不再需要 adv_deriv_total_lgeq_kcontracts 那条派生列。'),
    'ASX_DERIV': _P('ASX 衍生品合计（利率 + 股指 + 商品 + 电力 + NZ）', 'ASX',
                    'contract', 'AUD', True,
                    '⚠ 混合口径且含 non-traded volume。篮子常数须在 evidence 里'
                    '写明混了哪几类，图注同步。'),

    # ── 利率（单独产品）──
    'CME_RATES': _P('CME 利率（SOFR 短端 + 国债长端合成篮子）', 'CME',
                    'contract', 'USD', True,
                    'CME 合约规格页给面值（SOFR $1,000,000、10Y Note $100,000）；'
                    '基期价格 = 2019-01 结算价，按该月成交量加权。'
                    '⚠ 名义额 ≠ 风险敞口，见模块 docstring 二.1。'),
    'MX_STIR': _P('MX 加元短端利率（BAX / CORRA）', 'TMX', 'contract', 'CAD', True,
                  'MX 合约规格页给面值（BAX C$1,000,000）。'),
    'MX_BOND': _P('MX 加拿大国债期货（CGB 系）', 'TMX', 'contract', 'CAD', True,
                  'MX 规格页给面值 C$100,000。'),
    'JPX_JGB10Y': _P('JPX 10 年期 JGB 期货', 'JPX', 'contract', 'JPY', False,
                     'JPX 规格页给面值 ¥100,000,000（单一合约，不是篮子）。'),

    # ── 股指 ──
    'CME_EQUITY_INDEX': _P('CME 股指（E-mini / Micro E-mini 合成篮子）', 'CME',
                           'contract', 'USD', True,
                           '⚠ 这是「张数不可比」最典型的一处：ES $50/点、MES $5/点，'
                           '同标的差 10 倍。篮子常数必须按 2019-01 各产品成交量加权。'),
    'JPX_N225_LGEQ': _P('JPX 日経225（大合约当量）', 'JPX', 'contract', 'JPY', True,
                        '⚠ 源列已经是大合约当量（mini 记 1/10、micro 记 1/100），'
                        '所以乘数直接取**大合约**的 ¥1,000/点，不要再折一次 —— '
                        '折两次会把 JPX 压掉一个数量级。'),
    'JPX_TOPIX_FUT': _P('JPX TOPIX 期货', 'JPX', 'contract', 'JPY', True,
                        'JPX 规格页给 ¥10,000/点（mini ¥1,000/点）。'),

    # ── 单股 / ETF 期权 ──
    'MX_EQUITY_OPT': _P('MX 单股期权', 'TMX', 'contract', 'CAD', True,
                        'MX 规格页 100 股/张；基期价格按 2019-01 标的均价加权。'),
    'MX_ETF_OPT': _P('MX ETF 期权', 'TMX', 'contract', 'CAD', True, '同上。'),
    'JPX_SEC_OPT': _P('JPX 有价证券期权', 'JPX', 'contract', 'JPY', True,
                      'JPX 规格页给各标的的交易单位（多为 100 株）。'),
    'ASX_ETO': _P('ASX 单股期权（ETO）', 'ASX', 'contract', 'AUD', True,
                  'ASX 规格页 100 股/张（有除权调整）。'),
    'ASX_INDEX_OPT': _P('ASX 股指期权（XJO 等）', 'ASX', 'contract', 'AUD', True,
                        '⚠ 本批次**新增的规格需求**：asx.csv 的 adv_index_options_contracts '
                        '既不是 ASX24 期货篮子（ASX_DERIV）也不是 100 股/张的单股期权'
                        '（ASX_ETO），它是指数期权，乘数是每点澳元数（XJO A$10/点）。'
                        '原先这一列被挂在 ASX_DERIV 上，等于给指数期权安了一个期货篮子的'
                        '单张名义额。规格取自 ASX 指数期权合约规格页，'
                        '基期价格 = 2019-01 ASX200 收盘。'),

    # ── 能源 / 农产品 ──
    'CME_ENERGY': _P('CME 能源（WTI / Henry Hub 合成篮子）', 'CME',
                     'contract', 'USD', True,
                     'CME 规格页：WTI 1,000 桶/张、HH 10,000 MMBtu/张。'
                     '⚠ 名义额相同 ≠ 能量相同（热值不同），图注须写明。'),
    # ⚠ 原来这里是 `ICE_ENERGY`（ICE 全能源合成篮子），2026-08-06 **撤掉**。
    #   撤的理由不是"太难"，是**分子分母不同源**：adv_energy_kcontracts 是 ICE 全球口径
    #   （官方脚注明说 Nat Gas / Power 含 North American、NGX、UK、European，
    #   即 IFEU + Endex + IFUS + IFAD + NGX 五处），而 ICE 唯一不要 reCAPTCHA 的
    #   分产品历史表 report/7 只覆盖 ICE Futures Europe（2019-01 各能源列相加只占全球 67.0%），
    #   TTF 在 Endex 上、而且**没有固定乘数**（官方页原文 "1 MW per day in contract period
    #   ... x 23, 24 or 25 hours"，一张月度合约 672–744 MWh 不等）。
    #   拿 67% 子集的结构算出的常数去套 100% 的量 = 方向与大小都不知道的系统性偏差，
    #   而它在图上完全看不出来（柱子只是整体高一截）。
    #   ⇒ 换成下面这个**口径一致的子集**：覆盖率低（2019-01 占 ICE 全能源张数 34.8%）
    #   但零偏差。代价必须写在页面上，见 energy 池的 scope_note。
    'ICE_BRENT_IFEU': _P(
        'ICE 布伦特原油（期货+期权，IFEU 标准合约当量）', 'ICE', 'contract', 'USD', False,
        'ICE 官方 Monthly Statistics Tracking 工作簿 Derivs sheet 脚注(1) 原文：'
        '"Brent" includes the standard size contracts at ICE Futures Europe and as of '
        'November 2015 also includes mini Brent contracts on ICE Futures Singapore, '
        'which are converted to standard ICE Futures Europe equivalent contracts '
        '(mini Brent contracts are divided by 10). ⇒ **整列已由官方折成 IFEU 标准当量**，'
        '所以「张数 × 1,000 桶」对全列精确成立 —— 这是本产品的全部合法性所在，'
        '也是它与被撤掉的 ICE_ENERGY 的唯一实质差别（不是"更小"，是"口径一致"）。'
        '乘数取 ice.com/products/219 官方规格页（"Contract Size 1,000 barrels"）；'
        '基期价格取 EIA 官方序列 RBRTE 的 2019-01 月均（现货 FOB，与 ICE 期货结算价的'
        '基差已量化并留痕）。实测与复算脚本：build/basefill/ice_brent.py。'),
    'JPX_CMDTY': _P('JPX 商品（旧 TOCOM）', 'JPX', 'contract', 'JPY', True,
                    '⚠ 2020-07 之前 JPX 并不拥有这块业务，规格表照填，'
                    '但 pools 里该成员的 start 卡在 2020-07，不得 pro-forma 回填。'),
    'CME_AG': _P('CME 农产品（玉米/大豆/小麦复合体）', 'CME', 'contract', 'USD', True,
                 'CME 规格页 5,000 蒲式耳/张；基期价格取 2019-01 结算价加权。'),
    'ENX_MATIF': _P('Euronext MATIF 农产品', 'Euronext', 'contract', 'EUR', True,
                    'Euronext 规格页：小麦/玉米 50 吨/张、菜籽 50 吨/张。'),
    'MIAX_AG_WHEAT': _P('MIAX Futures 硬红春小麦', 'MIAX', 'contract', 'USD', False,
                        'MIAX Futures（原 MGEX）规格页 5,000 蒲式耳/张。'),

    # ── FX ──
    'CME_FX': _P('CME 外汇期货（合成篮子）', 'CME', 'contract', None, True,
                 '⚠ 每个合约的面值以**基础货币**计（EUR/USD 是 €125,000、'
                 'JPY 是 ¥12,500,000）。篮子常数须先把各合约面值折成美元再加权，'
                 '折算用的就是基期汇率 —— 折算方法写进规格表 evidence。'),
    'SGX_FX': _P('SGX 外汇期货（USD/CNH、INR/USD 等）', 'SGX', 'contract', None, True,
                 'SGX 规格页给各合约面值；跨币种，记账币定死。'),
    'FX_SPOT_USD': _P('FX 即期 ECN 成交额（US$）', 'ECN', 'notional', 'USD', False,
                      'kind=notional。Cboe FX 与 Euronext FX 都以 US$ 披露。'),
    'FX_SPOT_EUR': _P('FX 即期 ECN 成交额（€）', 'ECN', 'notional', 'EUR', False,
                      'kind=notional。360T 以 €披露 —— 定基汇率折算后终于能与'
                      '另两家同轴，这是新口径最直接的一处收益。'),

    # ── 存量与一级市场 ──
    'AUM_USD': _P('挂钩 ETF 资产（US$）', 'MSCI', 'notional', 'USD', False,
                  'kind=notional；AUM 本身是市值，"定基"不适用，只锁汇率。'),
    'AUM_EUR': _P('挂钩 ETF 资产（€）', 'DB1', 'notional', 'EUR', False, '同上。'),
    'RAISE_HKD': _P('IPO 募资额（HK$）', 'HKEX', 'notional', 'HKD', False,
                    'kind=notional，只锁汇率。'),
    'RAISE_SGD': _P('IPO 募资额（S$）', 'SGX', 'notional', 'SGD', False, '同上。'),
    'RAISE_AUD': _P('新挂牌募资额（A$）', 'ASX', 'notional', 'AUD', False, '同上。'),
    'RAISE_EUR': _P('新上市募资额（€）', 'Euronext', 'notional', 'EUR', False, '同上。'),
}


# ═══════════════════════════════════════════════════════════════════════════
# POOLS
# ═══════════════════════════════════════════════════════════════════════════
POOLS = [

    # ══════════════════════ 轴一：地理池 ══════════════════════

    {
        'id': 'na_cash', 'zh': '北美现货股票', 'axis': 'geo', 'page': 'exchanges-na',
        'unit_kind': 'notional', 'deflator': 'base_price', 'flow': 'per_day',
        'unit': U_BASE, 'unit_current': U_CURRENT, 'unit_contracts': 'bn shares/day',
        'share': 'true', 'levels': True, 'dual_unit': True,
        'basis': (
            '全部为 matched（本所撮合）成交股数，换成定基名义额（股数 × 基期平均成交价 '
            '× 基期汇率）。一律不用 handled —— handled 含路由到别家成交的量，'
            'Cboe / Nasdaq 不披露对应口径。'),
        'share_caveat': None,
        'dual_note': (
            '本池的份额在两种口径下**数值相同**：所有成员交易的是同一批证券，'
            '每股的基期价格是同一个常数，分子分母同乘一个数不改变比值。'
            '所以股数份额图不是"另一个答案"，而是**对账通道** —— '
            '它能与 ICE 自报的 share_nyse_us_cash_matched 逐位核对，'
            '而名义额份额没有任何外部数字可比。两条序列若对不上，'
            '一定是换算链坏了。'),
        'recon_tol_pp': 0.10,
        'recon_note': (
            '容差 0.10pp，是**实测定出来的，不是拍的**：拿 series/ice.csv 全部 187 个月'
            '（2011-01 – 2026-07）逐月比「Σ NYSE Tape A/B/C matched ÷ Σ Tape A/B/C '
            'consolidated」与 ICE 自报的 share_nyse_us_cash_matched，'
            '187/187 可比，中位偏差 0.027pp、最大 0.072pp（2017-12）。'
            '⚠ 原先这里写的是 0.05pp —— 太紧，会在 2011-10 / 2012-07 / 2016-09 / '
            '2017-12 等月份误报。偏差来源是两处舍入而不是口径差：'
            '自报份额只给到 3 位小数（步长 0.001 = 0.1pp，仅此一项就有 ±0.05pp），'
            '分子分母的 mnsh 又都是**整数百万股**。'
            '两者叠加的实测上界 0.072pp，取 0.10pp 留一档余量。'),
        'denom': {
            'key': 'ice', 'csv': 'ice.csv', 'start': '2011-01',
            'label': '全美合并成交量（Tape A+B+C consolidated）',
            'chain': [
                {'col': 'adv_tapeA_consolidated_mnsh', 'src': 'shares',
                 'unit_scale': MN, 'per_day': None, 'product': 'US_CASH_EQUITY_SHARE'},
                {'col': 'adv_tapeB_consolidated_mnsh', 'src': 'shares',
                 'unit_scale': MN, 'per_day': None, 'product': 'US_CASH_EQUITY_SHARE'},
                {'col': 'adv_tapeC_consolidated_mnsh', 'src': 'shares',
                 'unit_scale': MN, 'per_day': None, 'product': 'US_CASH_EQUITY_SHARE'},
            ],
            'contracts_col': ['adv_tapeA_consolidated_mnsh',
                              'adv_tapeB_consolidated_mnsh',
                              'adv_tapeC_consolidated_mnsh'],
            'evidence': 'docs/verify/verify_ice.md §5.1：2026-07 = 17.437bn 股/日，'
                        'NYSE 3.329bn = 19.1% 与 ICE 自报 share 0.191 逐位相符',
        },
        'residual': '其余（ATS / MEMX / IEX / TRF 场外等未单列的场所）',
        'head': ['ice', 'cboe'],                 # 两家都是次月第 3 个交易日
        'members': [
            {'key': 'ice', 'disp': 'NYSE Group', 'color': 'NAVY', 'csv': 'ice.csv',
             'start': '2011-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_nyse_tapeA_matched_mnsh', 'src': 'shares',
                  'unit_scale': MN, 'per_day': None, 'product': 'US_CASH_EQUITY_SHARE'},
                 {'col': 'adv_nyse_tapeB_matched_mnsh', 'src': 'shares',
                  'unit_scale': MN, 'per_day': None, 'product': 'US_CASH_EQUITY_SHARE'},
                 {'col': 'adv_nyse_tapeC_matched_mnsh', 'src': 'shares',
                  'unit_scale': MN, 'per_day': None, 'product': 'US_CASH_EQUITY_SHARE'},
             ],
             'contracts_col': ['adv_nyse_tapeA_matched_mnsh',
                               'adv_nyse_tapeB_matched_mnsh',
                               'adv_nyse_tapeC_matched_mnsh'],
             # 全仓唯一能与外部数字逐位核的一对：自算份额 vs 官方自报份额。
             # scale=1.0 因为这一列存的是小数（0.191），不是百分数。
             'selfreport': {
                 'col': 'share_nyse_us_cash_matched', 'scale': 1.0,
                 'tol_pp': 0.10,
                 'evidence': '187/187 个月可比，中位 0.027pp、最大 0.072pp（2017-12）'},
             'note': '官方无 A+B+C 合计行，需派生；ICE 另给 share_nyse_us_cash_matched '
                     '可做自校验（见 dual_note / recon_note）'},
            {'key': 'cboe', 'disp': 'Cboe U.S.', 'color': 'MBLUE', 'csv': 'cboe.csv',
             'start': '2017-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_us_equities_matched_shares_bn', 'src': 'shares',
                  'unit_scale': BN, 'per_day': None, 'product': 'US_CASH_EQUITY_SHARE'},
             ],
             'contracts_col': ['adv_us_equities_matched_shares_bn']},
            {'key': 'ndaq', 'disp': 'Nasdaq', 'color': 'GOLD', 'csv': 'ndaq.csv',
             'start': '2010-10', 'in_share': True,
             'chain': [
                 {'col': 'vol_us_cash_matched_mnsh', 'src': 'shares',
                  'unit_scale': MN,
                  'per_day': {'csv': 'miax.csv', 'col': 'trading_days_options'},
                  'product': 'US_CASH_EQUITY_SHARE'},
             ],
             'contracts_col': ['vol_us_cash_matched_mnsh'],
             'note': '⚠ 原始是**月度总量**（实测 2026-06 = 72,547 百万股）不是 ADV，'
                     '不除交易日会比同行大 ~20 倍（docs/verify/verify_ndaq.md E1）。'
                     '交易日**不取 ndaq.trading_days_us_equities** —— 它来自 nasdaqtrader，'
                     '实测停在 2026-06 而量列已到 2026-07（次月第 10 个工作日才出，'
                     '会把整页门槛拖后一周）；改用 miax.trading_days_options'
                     '（次月第 3-5 天）—— 美股与美式期权同一套 NYSE 假期日历。'
                     '⚠ 起点由 2010-10 改为 **2025-01**：实测 vol_us_cash_matched_mnsh '
                     '只有 2025-01 起 19 个月。2010-10 起的那条是份额列 '
                     'share_us_cash_matched_group，不是量列，它在 fn_monopoly 出场'},
            {'key': 'miax', 'disp': 'MIAX Pearl Equities', 'color': 'GRAY',
             'csv': 'miax.csv', 'start': '2020-12', 'in_share': True,
             'chain': [
                 {'col': 'adv_equities_api_mnshares', 'src': 'shares',
                  'unit_scale': MN, 'per_day': None, 'product': 'US_CASH_EQUITY_SHARE'},
             ],
             'contracts_col': ['adv_equities_api_mnshares'],
             'note': '尾部对照。⚠ 用 **API 列**（2020-12 起 68 个月）而不是 IR 月报列 '
                     'adv_equities_mnshares（只有 2025-01 起 19 个月）—— 两列重叠期实测'
                     '逐月吻合（2026-07: 117 vs 116.81 百万股/日）。'
                     'capture 与 Cboe 分母不同（total vs touched），只进量与份额，'
                     '不进 take rate 图（docs/verify/verify_miax.md §四）'},
            {'key': 'tmx', 'disp': 'TMX（加拿大，另一分母）', 'color': 'GREEN',
             'csv': 'tmx.csv', 'start': '2015-01', 'in_share': False,
             'chain': [
                 {'col': 'tmx_all_volume_shares', 'src': 'shares',
                  'unit_scale': ONE,
                  'per_day': {'col': 'trading_days_equity'},
                  'product': 'CA_CASH_EQUITY_SHARE'},
             ],
             'contracts_col': ['tmx_all_volume_shares'],
             'note': '只做规模对照，**绝不进份额分子** —— TSX 不在美国合并成交量里。'
                     '换成定基名义额之后它第一次能与美国四家同轴比水平值'
                     '（加元股价 × 基期 CAD/USD），这是新口径的直接收益；'
                     '但分母仍然是两个国家，份额照旧不成立。'
                     '⚠ 源列是**月度总股数的裸数**（2026-06 = 15,568,012,598 股），'
                     '所以 unit_scale=ONE 且必须除 trading_days_equity；'
                     '原写的 tmx_all_volume_shares_bn（bn 股）在表里不存在。'
                     '起点 2021-08，不进 head'},
        ],
        'excluded': [],
    },

    {
        'id': 'na_multilist_opt', 'zh': '北美多重挂牌期权', 'axis': 'geo',
        'page': 'exchanges-na',
        'unit_kind': 'notional', 'deflator': 'base_price', 'flow': 'per_day',
        'unit': U_BASE, 'unit_current': U_CURRENT, 'unit_contracts': U_KCTR,
        'share': 'true', 'levels': True, 'dual_unit': True,
        'basis': ('equity & ETF 多重挂牌期权，**均不含指数期权**。'
                  'Cboe 与 MIAX 的列名、RPC 定义逐字相同。'
                  '定基名义额 = 张数 × 100 股/张 × 基期加权标的价 × 1（USD）。'),
        'share_caveat': None,
        'dual_note': (
            '与 na_cash 同理：三家挂的是同一批多重挂牌合约，单张基期名义额是同一个常数，'
            '所以名义额份额 ≡ 张数份额。张数口径的意义是**可对账** —— '
            'ICE 自报 share_nyse_equity_options、MIAX 自报 share_multilist_options_pct，'
            '两条官方序列都是张数口径，是全仓唯一能与外部数字逐位核的份额。'),
        'recon_tol_pp': 0.10,
        'recon_note': (
            '容差 0.10pp，实测：series/ice.csv 全部 187 个月比「adv_nyse_equity_options '
            '÷ adv_us_equity_options_industry」与 ICE 自报 share_nyse_equity_options，'
            '187/187 可比，中位偏差 0.022pp、最大 0.051pp（2016-09）。'
            '与 na_cash 同源的舍入（自报份额 3 位小数 + 千张整数），取同一个 0.10pp。'),
        'denom': {
            'key': 'ice', 'csv': 'ice.csv', 'start': '2011-01',
            'label': '全美股票/ETF 期权行业 ADV',
            'chain': [
                {'col': 'adv_us_equity_options_industry_kcontracts', 'src': 'contracts',
                 'unit_scale': K, 'per_day': None, 'product': 'US_MULTILIST_EQ_OPT'},
            ],
            'contracts_col': ['adv_us_equity_options_industry_kcontracts'],
            'evidence': 'docs/verify/verify_ice.md §5.2：2026-07 行业 64,394k，NYSE 21.1% + '
                        'Cboe 24.4% = 45.5%，余下 54.5% 给 Nasdaq/MIAX/BOX，量级自洽；'
                        'ICE 10-K 自报 2025 年 18.9% 可反算。'
                        '⚠ 另一处实测佐证：miax.industry_adv_options_kcontracts 与本列'
                        '在 2025-01 起 19 个月**逐月完全相同**（2026-07 双方均 64,394k），'
                        '两家 IR 用的是同一个行业口径',
            'caveat': '⚠ ICE 从未书面说明该分母是否含指数期权。页面上只能写「经与 Cboe '
                      'multilist 及 ICE 10-K 交叉验证，口径与多重上市股票/ETF 期权一致」，'
                      '不得写成「ICE 官方定义为不含指数期权」',
            'alt_rejected': (
                'miax.industry_adv_options_kcontracts 是第二个候选分母，**已定死不用**：'
                'ICE 那条有 187 个月历史（MIAX 只有 18 个月），且 ICE 官方直接给'
                ' share_nyse_equity_options 可自校验。两条并存会造出两套份额、'
                '两套 Δpp、两套归因桥（docs/verify/verify_miax.md §12、'
                'docs/verify/_design.md §五.1）。MIAX 的自报份额只做交叉核对。'),
        },
        'residual': '其余（Nasdaq 六所 / BOX / MEMX Options）',
        'head': ['ice', 'cboe', 'miax'],
        'members': [
            {'key': 'cboe', 'disp': 'Cboe', 'color': 'MBLUE', 'csv': 'cboe.csv',
             'start': '2017-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_multilist_options_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'US_MULTILIST_EQ_OPT'},
             ],
             'contracts_col': ['adv_multilist_options_kcontracts']},
            {'key': 'miax', 'disp': 'MIAX（四所合计）', 'color': 'GOLD', 'csv': 'miax.csv',
             'start': '2015-04', 'in_share': True,
             'chain': miax_multilist_legs(),
             'contracts_col': list(MIAX_OPT_COLS),
             'crosscheck_col': ['adv_multilist_options_kcontracts'],
             'note': '份额 2015 年 7.4% → 2026-07 17.9%。四所分别一条腿（见 '
                     'miax_multilist_legs），IR 月报的四所合计列 '
                     'adv_multilist_options_kcontracts 只有 19 个月，留在 contracts_col '
                     '里做「四条 API 腿之和 ≈ 合计列」的解析自检（实测比值 0.9967–0.9976）。'
                     '单所线（M/P/D/S）2019-03 Emerald 起量时有内部导流造成的假跳，'
                     '画单所必须标注。'
                     '⚠ **刻意不给 selfreport**：MIAX 自报的 '
                     'share_multilist_options_pct 分母是 MIH 自己的行业 ADV，'
                     '与本池用的 ICE 分母不是同一个数，两者本就不该相等；'
                     '拿它当对账基准会把一个口径差伪装成解析错误，只做交叉核对'},
            {'key': 'ice', 'disp': 'NYSE（Arca + American）', 'color': 'NAVY',
             'csv': 'ice.csv', 'start': '2011-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_nyse_equity_options_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'US_MULTILIST_EQ_OPT'},
             ],
             'contracts_col': ['adv_nyse_equity_options_kcontracts'],
             'selfreport': {
                 'col': 'share_nyse_equity_options', 'scale': 1.0,
                 'tol_pp': 0.10,
                 'evidence': '187/187 个月可比，中位 0.022pp、最大 0.051pp（2016-09）'}},
        ],
        'rpc': {                       # 全仓唯一一对逐字同定义的 take rate
            'unit': 'USD/contract',
            'series': [('cboe', 'rpc_multilist_options_usd', '2017-01'),
                       ('miax', 'rpc_multilist_options_usd', '2025-01'),
                       ('ice', 'rpc_nyse_equity_options_usd', '2011-01')],
            'overlap': '2025-01 – 2026-06（18 个月）',
            'caveat': ('⚠ RPC 是**每张**的费率，天然是张数口径，不换算成名义额 —— '
                       '把它除以名义额会造出一个没有任何官方对应物的"bp 费率"。'
                       '三家的滞后不同：Cboe 与 MIAX 的 RPC 滞后一个月（最新月天然为空），'
                       'ICE 的不滞后。任何并排图必须在绘图层截齐到三家都有值的那个月，'
                       '否则每月看板一刷新都像是 Cboe 抓挂了'
                       '（docs/verify/verify_ice.md §5.3）。'
                       'MIAX 的 rpc_multilist_options_usd 实测只有 2025-01–2026-06 共 '
                       '**18** 个月（2026-07 因滞后为空）⇒ 2026-12 之前做不了同比、'
                       '做不了指数化'),
        },
        'excluded': [
            ('tmx', 'BOX 只有季度数据（series/tmx_box_q.csv：box_volume_mncontracts / '
                    'box_equity_options_share_pct），北美期权池永远缺 TMX'
                    '（docs/verify/_design.md §四 批 6）'),
        ],
    },

    {
        'id': 'na_total_opt', 'zh': '北美期权总量（含指数）', 'axis': 'geo',
        'page': 'exchanges-na',
        'unit_kind': 'notional', 'deflator': 'base_price', 'flow': 'per_day',
        'unit': U_BASE, 'unit_current': U_CURRENT, 'unit_contracts': U_KCTR,
        'share': 'pool', 'levels': True, 'dual_unit': False,
        'basis': (
            '含指数期权的美股期权。**这个池是定基名义额收益最大的一处**：'
            '一张 SPX 期权的名义额是一张普通股票期权的两个数量级以上'
            '（100 × 指数点位 vs 100 × 个股价），张数口径下 Cboe 的指数业务被完全'
            '低估。Cboe 拆成 multilist + index 两条腿分别换算再相加；'
            'Nasdaq 的口径含指数期权且官方不拆，只能用一个合成篮子常数。'),
        'share_caveat': '分母 = 本池三家之和，不是全美期权行业。不得写「市场份额」。',
        'denom': None,
        'head': ['cboe', 'ndaq'],
        'members': [
            {'key': 'cboe', 'disp': 'Cboe（总）', 'color': 'MBLUE', 'csv': 'cboe.csv',
             'start': '2017-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_multilist_options_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'US_MULTILIST_EQ_OPT'},
                 {'col': 'adv_index_options_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'CBOE_INDEX_OPT'},
             ],
             'contracts_col': ['adv_multilist_options_kcontracts',
                               'adv_index_options_kcontracts'],
             'crosscheck_col': ['adv_us_options_kcontracts'],
             'note': '⚠ 换算走 multilist + index 两条腿，**不走 adv_us_options_kcontracts '
                     '合计列** —— 合计列是两类合约的裸张数和，乘不了单一乘数。'
                     '合计列挪到 crosscheck_col（不是 contracts_col）：用途是断言'
                     '「两条腿的张数之和 = 合计列」，这是本池最便宜的一道解析自检；'
                     '但它**不可与两条分项同时求和**，混进 contracts_col 会让张数口径'
                     '的分子凭空翻倍'},
            {'key': 'ndaq', 'disp': 'Nasdaq（六所）', 'color': 'GOLD', 'csv': 'ndaq.csv',
             'start': '2025-01', 'in_share': True,
             'chain': [
                 {'col': 'vol_us_options_mmcontracts', 'src': 'contracts',
                  'unit_scale': MN,
                  'per_day': {'csv': 'miax.csv', 'col': 'trading_days_options'},
                  'product': 'NDAQ_US_OPT'},
             ],
             'contracts_col': ['vol_us_options_mmcontracts'],
             'note': '⚠ 只有 19 个月（IR PDF 每月原地替换，历史只在 Wayback 而本机硬禁）。'
                     '2026-12 之前做不了同比。篮子常数含指数期权，假设写进规格表 evidence'},
            {'key': 'miax', 'disp': 'MIAX', 'color': 'GRAY', 'csv': 'miax.csv',
             'start': '2015-04', 'in_share': True,
             'chain': miax_multilist_legs(),
             'contracts_col': list(MIAX_OPT_COLS),
             'crosscheck_col': ['adv_index_options_api_kcontracts'],
             'note': 'MIAX 完全不做指数期权（adv_index_options_api_kcontracts '
                     '实测 136 个月**恒为 0**，放在 crosscheck_col 里让这条断言可执行），'
                     '这本身就是它与 Cboe 最大的结构差异 —— 换成名义额之后这个差异'
                     '从"少一条产品线"变成"少一个数量级的名义额"，图上第一次看得见'},
        ],
        'excluded': [],
    },

    {
        'id': 'eu_cash', 'zh': '欧洲现货股票', 'axis': 'geo', 'page': 'exchanges-eu',
        'unit_kind': 'notional', 'deflator': 'fx_only', 'flow': 'per_day',
        'unit': U_FXONLY, 'unit_current': U_CURRENT, 'unit_contracts': None,
        'share': 'pool', 'levels': True, 'dual_unit': False,
        'basis': (
            '全部为 €bn/日 ADNV、单边计、股票口径，只折基期 EUR/USD 汇率。'
            '三家同币同单位，所以水平值本来就可比；折成美元的唯一目的是让它能与'
            '其它池并置在同一根轴上。'
            '**份额不是市场份额**：覆盖范围不同（Xetra 只德国上市，Cboe Europe 与 '
            'Euronext 是泛欧），全欧 lit 成交没有任何一家披露分母。'),
        'share_caveat': ('分母 = 本池三家之和。⚠ 源列是金额 ⇒ 已剔汇率、**未剔标的涨跌**，'
                         '欧股整体上涨会让全池一起变大，不要读成成交活跃度上升。'),
        'denom': None,
        'residual': None,
        'head': ['enx', 'cboe'],
        'members': [
            {'key': 'enx', 'disp': 'Euronext（legacy 口径）', 'color': 'NAVY',
             'csv': 'enx.csv', 'start': '2012-01', 'in_share': True,
             'chain': enx_legacy_legs(['adv_cash_equities_adnv_eurbn'],
                                      'EU_CASH_ADNV_EUR', unit_scale=BN,
                                      src='notional'),
             'contracts_col': [],
             'note': '⚠ 不要用 adv_cash_adnv_eurbn（含结构化产品与 ETF），Cboe 那列不含。'
                     '⚠ 减法腿的 since=2025-11 不可省：athex 备注列 2021-01 就有值，'
                     '但 2025-10 及以前**主列并不含它**（docs/verify/enx.md 口径坑 1），'
                     '无脑相减会把 2021–2025 的 Euronext 减小一块从没加进来的量。'
                     '现货侧 Athens 只有约 0.28/15.52 = 1.8%，断点不像单股衍生品那么凶，'
                     '但同一个池里两条线的口径必须一致，所以照减。'
                     '其余断点无备注列可逆（📌 未找到：Borsa Italiana 2021-05、'
                     'Oslo 2018-01、Dublin 2017-01 官方都没给对应的 memo 列，'
                     'series/enx_breaks.csv 只登记了断点月份），只能画红色断点竖线'},
            {'key': 'cboe', 'disp': 'Cboe Europe', 'color': 'MBLUE', 'csv': 'cboe.csv',
             'start': '2017-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_eu_equities_adnv_eurbn', 'src': 'notional',
                  'unit_scale': BN, 'per_day': None, 'product': 'EU_CASH_ADNV_EUR'},
             ],
             'contracts_col': []},
            {'key': 'db1', 'disp': 'Xetra（股票口径）', 'color': 'GOLD', 'csv': 'db1.csv',
             'start': '2016-06', 'in_share': True,
             'chain': [
                 {'col': 'turnover_xetra_equities_eurbn', 'src': 'notional',
                  'unit_scale': BN,
                  'per_day': {'col': 'trading_days_cash'},
                  'product': 'EU_CASH_ADNV_EUR'},
             ],
             'contracts_col': [],
             'note': '⚠ 原写的 adv_xetra_adnv_eurbn 在 db1.csv 里**不存在**。真实表里有三列，'
                     '各有各的代价，本池取股票口径那一条：'
                     '(a) turnover_xetra_equities_eurbn —— Xetra 电子盘**股票**月成交额，'
                     '与 Cboe / Euronext 逐字同口径。**2026-08-18 已回补到 2016-06、共 107 个月**'
                     '（原写「只有 2024-12 起 20 个月」，已过期）；'
                     '⚠ 但它**中间有 15 格空洞 4 段**（2016-07、2017-06~2018-04、'
                     '2018-06~07、2019-12 —— 官方那几年不发分场所的分类拆分）。'
                     '真要把本池接上渲染，**空洞月必须留 null 不能参与占比分母** ——'
                     '一家缺一格而分母照旧求和，会把另外两家的占比凭空抬高；'
                     '(b) turnover_xetra_eurbn —— 含 ETP 与结构化产品，'
                     '**2016-01 起 127 个月、无空洞**（原写 31 个月，已过期）；'
                     '(c) turnover_cash_total_eurbn —— Xetra + Frankfurt 场内、含债券基金，'
                     '198 个月（2010-01 起），docs/verify/verify_db1.md §四的 8.59 €bn/日'
                     '就是这一条。历史深十倍，但口径与另两家不同 ⇒ **不进本池**，'
                     '否则 DB1 这一段会被系统性抬高约三成（2026-06 实测 8.59 vs 6.31）。'
                     '⚠ 三列都是**月度总额不是 ADV**，必须除 trading_days_cash；'
                     '而 trading_days_cash 是慢腿（实测停在 2026-06，Xetra 量列已到 '
                     '2026-07）⇒ db1 不进 head'},
        ],
        'evidence': '2026-06 实测 Euronext 15.523 / Cboe 14.95 / Xetra 股票 '
                    '138.768÷22 = 6.31 €bn per day（docs/verify/verify_enx.md §1.7、'
                    'docs/verify/verify_db1.md §四）；同月 Xetra+Frankfurt 全口径 '
                    '188.944÷22 = 8.59，就是两个口径的差',
        'excluded': [
            ('db1_slow', 'Clearstream（auc_securities_services_eurbn / '
                         'auc_fund_services_eurbn）、OTC（otc_notional_cleared_eurbn）、'
                         '360T 都是慢腿，最新月天然留空，不进 panel'
                         '（docs/verify/verify_db1.md §四.3）'),
        ],
    },

    {
        'id': 'eu_deriv', 'zh': '欧洲衍生品', 'axis': 'geo', 'page': 'exchanges-eu',
        'unit_kind': 'notional', 'deflator': 'base_price', 'flow': 'per_day',
        'unit': U_BASE, 'unit_current': U_CURRENT, 'unit_contracts': U_KCTR,
        'share': 'pool', 'levels': True, 'dual_unit': False,
        'basis': (
            '⬆ **这个池的档次因新口径而变**：原设计定为 share=none，理由是'
            '「合约乘数差数十倍（Bund vs CAC40 vs Brent），只能指数化」。'
            '定基名义额正是为这件事设计的 —— 乘数差异被吸收进常数，'
            '现在可以算池内占比，也可以同轴比水平值。'
            'Eurex 拆成利率 / 股指 / 单股三条腿分别换算再相加，'
            '不走 adv_eurex_total_contracts 合计列。'
            '⚠ 但本池的 **ICE 那条腿是张数口径**（只进增长图），见 contracts_only_note。'),
        'share_caveat': ('分母 = 本池**两家**之和（Eurex + Euronext）—— '
                         '**ICE 不在分子也不在分母**（张数口径成员，见 contracts_only_note）。'
                         '它是「欧洲场内衍生品名义额构成」，不是竞争份额 —— '
                         '三家的标的曲线大体不重合。'
                         '⚠ Eurex 那条腿含利率合约 ⇒ 名义额 ≠ 风险敞口，'
                         '见模块 docstring 二.1。'),
        'contracts_only_note': (
            '本页的 ICE Futures Europe 利率线**只有增长口径**（指数化 / 同比），'
            '不出现在水平值图与占比图里，占比的分母也不含它。'
            '这不是数据缺失，是口径判断 —— 详见该成员的 contracts_only_why。'),
        'denom': None,
        'head': ['db1', 'enx'],
        'members': [
            {'key': 'db1', 'disp': 'Eurex', 'color': 'NAVY', 'csv': 'db1.csv',
             'start': '2008-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_eurex_rates_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'EUREX_RATES'},
                 {'col': 'adv_eurex_index_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'EUREX_INDEX'},
                 {'col': 'adv_eurex_equity_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'EUREX_EQUITY'},
             ],
             'contracts_col': ['adv_eurex_rates_contracts',
                               'adv_eurex_index_contracts',
                               'adv_eurex_equity_contracts'],
             'crosscheck_col': ['adv_eurex_total_contracts'],
             'note': '⚠ 列名与单位都与原写法不同：db1.csv 里是 adv_eurex_*_contracts、'
                     '存的是**裸张数的日均**（实测 2026-06 总量 10,753,305.77 张/日），'
                     '不是千张 ⇒ unit_scale=ONE，原写的 _kcontracts + K 会放大 1000 倍。'
                     '⚠ 起点由 2002-01 改为 **2008-01**：2002-2007 只有 vol_fd_* '
                     '那组月度合约数，Eurex 产品级 ADV 从 2008-01 起'
                     '（docs/verify/db1.md §历史深度）。'
                     '⚠ 三条腿之和不一定等于 adv_eurex_total_contracts（总数含商品等'
                     '未单列品种）—— 合计列放在 crosscheck_col，差额若超过合计的 5%，'
                     '说明有一整块业务没进池，build 脚本要打印出来；但**不要**把差额'
                     '当第四条腿补进去，那等于给一块不知道是什么的量硬安一个乘数'},
            {'key': 'enx', 'disp': 'Euronext 衍生品（legacy 口径）', 'color': 'MBLUE',
             'csv': 'enx.csv', 'start': '2012-01', 'in_share': True,
             'chain': (enx_legacy_legs(['adv_index_futures_kcontracts',
                                        'adv_index_options_kcontracts'],
                                       'ENX_INDEX_DERIV')
                       + enx_legacy_legs(['adv_singlestock_futures_kcontracts',
                                          'adv_singlestock_options_kcontracts'],
                                         'ENX_SINGLESTOCK_LEGACY')),
             'contracts_col': ['adv_index_futures_kcontracts',
                               'adv_index_options_kcontracts',
                               'adv_singlestock_futures_kcontracts',
                               'adv_singlestock_options_kcontracts'],
             'crosscheck_col': ['athex_adv_index_futures_kcontracts',
                                'athex_adv_index_options_kcontracts',
                                'athex_adv_singlestock_futures_kcontracts',
                                'athex_adv_singlestock_options_kcontracts'],
             'note': '⚠ enx.csv 里**没有** adv_index_deriv_kcontracts、也没有 '
                     'adv_singlestock_deriv_legacy_kcontracts 这两列（原写法凭空发明的）。'
                     '真实表是期货与期权**分开存**，各配一列 athex_ 备注列，'
                     '所以这里是 8 条腿：4 条主列 + 4 条 since=2025-11 的减法腿。'
                     'legacy 口径在 build 侧由减法腿现算，不再指望 fetch 侧派生一列 —— '
                     '口径写在这一处，改也只改这一处。'
                     '⚠ 单股那条不用 legacy 会在 2025-11 有 20 倍以上假跳'
                     '（docs/verify/enx.md 口径坑 2：2025-10 主列 35,573 → '
                     '2025-11 836,511 张/月，其中 Athens 781,183）'},
            {'key': 'ice', 'disp': 'ICE Futures Europe（利率，张数口径）', 'color': 'GOLD',
             'csv': 'ice.csv', 'start': '2011-01', 'in_share': False,
             'contracts_only': True,
             'contracts_only_why': ICE_RATES_CONTRACTS_ONLY,
             'chain': [
                 {'col': 'adv_stir_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'ICE_STIR'},
                 {'col': 'adv_mltir_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'ICE_MLTIR'},
             ],
             'contracts_col': ['adv_stir_kcontracts', 'adv_mltir_kcontracts'],
             'note': '⚠ 原写「STIR 的名义额会显著压过股指腿」—— 那句话已作废：'
                     '本成员**不再进名义额口径**（contracts_only=True），'
                     '只进增长图。理由见 contracts_only_why'},
        ],
        'excluded': [
            ('ndaq', 'Nasdaq 北欧衍生品：📌 未找到北欧交易日列（Nasdaq IR 月报不给），'
                     'vol_nordic_derivs_mmcontracts 是**月度总量**（2025-01 起 19 个月），'
                     '换算不到本池的 /day 单位。强行用 trading_days_us_equities 是错的日历。'
                     '它只在 ndaq 单公司页画月度总量'),
        ],
    },

    {
        'id': 'apac_cash', 'zh': '亚太现货股票', 'axis': 'geo', 'page': 'exchanges-apac',
        'unit_kind': 'notional', 'deflator': 'fx_only', 'flow': 'per_day',
        'unit': U_FXONLY, 'unit_current': U_CURRENT, 'unit_contracts': None,
        'share': 'pool', 'levels': True, 'dual_unit': False,
        'basis': (
            '⬆ **档次因新口径而变**：原设计是 share=none / 只能指数化，理由是'
            '「币种与量纲全不同，不做汇率折算 —— FX 换算是派生量」。'
            '本批次改了这条：series/ 仍然只存官方原始披露（HK$bn / ¥tn / S$mn / A$bn），'
            '**折算发生在 build 侧**，用的是入库的 series/fx.csv 基期汇率，'
            '所以派生量有据可查、可复现，且锁基期 ⇒ 汇率波动不进增长与份额。'),
        'share_caveat': ('分母 = 本池四家之和。⚠ 源列是成交额 ⇒ 已剔汇率、'
                         '**未剔标的涨跌**：港股一轮大涨会让 HKEX 的占比上升，'
                         '但那不是它抢了别人的单。'),
        'denom': None,
        'head': ['hkex', 'jpx', 'sgx', 'asx'],
        'members': [
            {'key': 'hkex', 'disp': 'HKEX', 'color': 'GOLD', 'csv': 'hkex.csv',
             'start': '2019-01', 'in_share': True,
             'chain': [
                 {'col': 'adt_hkdbn', 'src': 'notional', 'unit_scale': BN,
                  'per_day': None, 'product': 'HK_CASH_ADT_HKD'},
             ],
             'contracts_col': []},
            {'key': 'jpx', 'disp': 'JPX（东证）', 'color': 'NAVY', 'csv': 'jpx.csv',
             'start': '2014-12', 'in_share': True,
             'chain': [
                 {'col': 'adt_cash_total_jpytn', 'src': 'notional', 'unit_scale': TN,
                  'per_day': None, 'product': 'JP_CASH_ADT_JPY'},
             ],
             'contracts_col': [],
             'note': '与 HKEX 是全仓最干净的一对现货对照：都是日均成交额 + 月末时价总额，'
                     '都含 ETF/REIT，都含场内大宗。'
                     '⚠ 起点由 1985-01 改为 **2014-12**：jpx.csv 实测就是 2014-12 起 '
                     '139 个月，「1985 年起」是侦察稿里对官方历史文件的描述，不是入库范围'},
            {'key': 'sgx', 'disp': 'SGX', 'color': 'MBLUE', 'csv': 'sgx.csv',
             'start': '2015-01', 'in_share': True,
             'chain': [
                 {'col': 'sdav_sgdmn', 'src': 'notional', 'unit_scale': MN,
                  'per_day': None, 'product': 'SG_CASH_SDAV_SGD'},
             ],
             'contracts_col': []},
            {'key': 'asx', 'disp': 'ASX', 'color': 'GREEN', 'csv': 'asx.csv',
             'start': '2017-10', 'in_share': True,
             'chain': [
                 {'col': 'adt_cash_onmarket_audbn', 'src': 'notional', 'unit_scale': BN,
                  'per_day': None, 'product': 'AU_CASH_ADT_AUD'},
             ],
             'contracts_col': [],
             'note': 'on-market 口径，不含场外报告成交；Cboe Australia 约占澳洲两成'
                     '且不在此数里 ⇒ 池内占比会系统性高估 ASX，图注必写。'
                     '起点跟着 asx.csv 自己走（2026-08-18 该表已回补到 2016-01，本字段是惰性的、'
                     '实际起点由数据现算，不由这里写死）'},
        ],
        'excluded': [],
    },

    {
        'id': 'apac_deriv', 'zh': '亚太衍生品', 'axis': 'geo', 'page': 'exchanges-apac',
        'unit_kind': 'notional', 'deflator': 'base_price', 'flow': 'per_day',
        'unit': U_BASE, 'unit_current': U_CURRENT, 'unit_contracts': U_KCTR,
        'share': 'pool', 'levels': True, 'dual_unit': False,
        'basis': (
            '⬆ **档次因新口径而变，而且这个池是收益最大的一个**。原设计说它'
            '「是全站最容易画错的一个：JPX 的原始张数被 mini(1/10) 与 micro(1/100) 严重扭曲」，'
            '并为此专门新建了派生列 adv_deriv_total_lgeq_kcontracts。'
            '定基名义额从根上解决了这件事：篮子常数按 2019-01 各产品的**真实乘数**加权，'
            'mini / micro 自动被记成它们该有的大小，'
            '**不再需要那条"大合约当量"派生列**（它留在 series/ 里做对账，不进本池）。'),
        'share_caveat': ('分母 = 本池四家之和，是「亚太场内衍生品名义额构成」，'
                         '不是竞争份额 —— 四家的主力标的（HSI / 日経 / A50 / SPI）'
                         '几乎不重合。⚠ 含利率合约 ⇒ 名义额 ≠ 风险敞口。'),
        'denom': None,
        'head': ['hkex', 'sgx', 'asx'],
        'members': [
            {'key': 'hkex', 'disp': 'HKEX', 'color': 'GOLD', 'csv': 'hkex.csv',
             'start': '2019-01', 'in_share': True,
             'chain': [
                 {'col': 'derivatives_adv_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'HKEX_DERIV'},
             ],
             'contracts_col': ['derivatives_adv_contracts'],
             'note': 'HKEX 存的是**裸张数**（不是千张），unit_scale=1'},
            {'key': 'sgx', 'disp': 'SGX', 'color': 'MBLUE', 'csv': 'sgx.csv',
             'start': '2015-01', 'in_share': True,
             'chain': [
                 {'col': 'ddav_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'SGX_DERIV'},
             ],
             'contracts_col': ['ddav_contracts'],
             'note': '⚠ 列名是 ddav_contracts 不是 ddav_kcontracts，且入库时**没有** ÷1000：'
                     '实测 2026-06 = 1,619,444，就是官方 At-A-Glance 的 DDAV 原值（张/日）'
                     '⇒ unit_scale=ONE。原写法（_kcontracts + K）会把 SGX 放大 1000 倍'},
            {'key': 'jpx', 'disp': 'JPX', 'color': 'NAVY', 'csv': 'jpx.csv',
             'start': '2014-12', 'in_share': True,
             'chain': [
                 {'col': 'adv_deriv_total_raw_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'JPX_DERIV'},
             ],
             'contracts_col': ['adv_deriv_total_raw_kcontracts'],
             'crosscheck_col': ['adv_deriv_total_lgeq_kcontracts'],
             'note': '⚠ 与原设计相反：这里用**原始张数列**配 JPX_DERIV 篮子常数，'
                     '**不用 lgeq 当量列** —— 当量列已经做过一次 1/10、1/100 折算，'
                     '再乘大合约乘数就是折两次。'
                     '⚠ 真实列名是 adv_deriv_total_**raw**_kcontracts（raw / lgeq 两套'
                     '并存），原写的 adv_deriv_total_kcontracts 不存在。'
                     '当量列放 crosscheck_col：build 应当断言「原始张数 × 篮子常数」与'
                     '「当量列 × 大合约名义额」在基期同一个月对得上（这是对篮子常数'
                     '最强的一道外部校验），但两列**绝不可相加**。'
                     '实测两者差 4.5 倍（2026-06: raw 2,365.65 vs lgeq 522.57 千张/日），'
                     '这正是 mini/micro 造成的张数扭曲本身'},
            {'key': 'asx', 'disp': 'ASX', 'color': 'GREEN', 'csv': 'asx.csv',
             'start': '2017-10', 'in_share': True,
             'chain': [
                 {'col': 'adv_futures_and_options_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'ASX_DERIV'},
                 {'col': 'adv_single_stock_options_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'ASX_ETO'},
                 {'col': 'adv_index_options_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'ASX_INDEX_OPT'},
             ],
             'contracts_col': ['adv_futures_and_options_contracts',
                               'adv_single_stock_options_contracts',
                               'adv_index_options_contracts'],
             'crosscheck_col': ['adv_futures_contracts',
                                'adv_options_on_futures_contracts'],
             'note': '⚠ 混合口径（利率 + 股指 + 商品 + 电力 + NZ），且含 non-traded volume。'
                     '图注必须写明是混合量，不能标成任何单一资产类。'
                     '⚠ 三处改动：(a) adv_futures_total_contracts 不存在，ASX24 那条腿'
                     '改用 adv_futures_and_options_contracts（= adv_futures_contracts + '
                     'adv_options_on_futures_contracts，两条分项进 crosscheck_col 做加总自检，'
                     '实测 2026-07: 711,012 + 2,400 = 713,411 逐位相符）；'
                     '(b) 指数期权那条腿原先挂在 ASX_DERIV 上 —— 那是给指数期权安了一个'
                     '期货篮子的单张名义额，改挂**新增的 ASX_INDEX_OPT**；'
                     '(c) 起点 2016-01 → 2017-10（实测表首行）'},
        ],
        'excluded': [],
    },

    # ══════════════════════ 轴二：标的池 ══════════════════════

    {
        'id': 'rates', 'zh': '利率衍生品', 'axis': 'product', 'page': 'exchanges-products',
        'unit_kind': 'notional', 'deflator': 'base_price', 'flow': 'per_day',
        'unit': U_BASE, 'unit_current': U_CURRENT, 'unit_contracts': U_KCTR,
        'share': 'pool', 'levels': True, 'dual_unit': False,
        'basis': (
            '⬆ **档次因新口径而变**（原设计 none，理由是「千张/日，绝对量无意义」）。'
            '定基名义额之后水平值可比、占比可算。但这个池的看点仍然**不是谁抢谁的单**，'
            '而是各条货币曲线的周期错位：CME = 美元（SOFR / Treasuries）、'
            'ICE + Eurex = 欧元与英镑、TMX = 加元、JPX = 日元。互补而非竞争。'),
        'share_caveat': (
            '⚠⚠ 这是全仓最需要小心的一张占比图。占比只能读作「各货币曲线的**名义额**构成」。'
            '名义额 ≠ 风险敞口：3M SOFR 面值 100 万美元 / 久期 0.25 年，'
            '10Y Note 面值 10 万美元 / 久期约 8 年 —— 按名义额短端是长端的 10 倍，'
            '按 DV01 反过来，两者能差一个数量级。'
            '所以「CME 名义额占比最大」**不等于**「CME 承担了最多利率风险」，'
            '更不等于「CME 的利率生意最大」（收入是按张收的，见 contracts_col）。'
            '⚠ 分母 = 本池**四家**之和（CME + Eurex + MX + JPX）—— '
            '**ICE 的欧洲曲线不在分子也不在分母**（张数口径成员，见 contracts_only_note）。'
            '所以这张占比图里「欧元/英镑曲线」只由 Eurex 代表，读作全欧就是错的。'),
        'contracts_only_note': (
            '本池的 ICE（欧洲曲线）**只有增长口径**：它出现在指数化与同比图里，'
            '不出现在水平值图与占比图里，占比的分母也不含它。'
            '这不是数据缺失、也不是"以后会补" —— 详见该成员的 contracts_only_why 的第②条：'
            '名义额对利率衍生品本身就是误导性单位，正确单位是 DV01。'
            '同一条告诫其实对本池**所有**成员都成立，只是别的成员至少有官方面值可依，'
            'ICE 连面值都没有官方原文。'),
        'risk_note': (
            'DV01 加权是这个池唯一正确的"风险口径"，但月度成交报表里没有久期字段。'
            '📌 未找到：CME / ICE / Eurex / MX / JPX 的月度成交报表都不含久期或 DV01。'
            '检索路径 = 各所的合约规格页逐合约取到期日与票息后自行计算 —— '
            '那是一整套需要每月维护的曲线数据，远超本仓无人值守的边界，第一版不做。'),
        'denom': None,
        'head': ['cme', 'ice', 'db1'],
        'members': [
            {'key': 'cme', 'disp': 'CME（美元）', 'color': 'NAVY', 'csv': 'cme.csv',
             'start': '2008-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_rates_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'CME_RATES'},
             ],
             'contracts_col': ['adv_rates_kcontracts']},
            {'key': 'ice', 'disp': 'ICE（欧洲曲线，张数口径）', 'color': 'MBLUE',
             'csv': 'ice.csv', 'start': '2011-01', 'in_share': False,
             'contracts_only': True,
             'contracts_only_why': ICE_RATES_CONTRACTS_ONLY,
             'chain': [
                 {'col': 'adv_stir_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'ICE_STIR'},
                 {'col': 'adv_mltir_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'ICE_MLTIR'},
             ],
             'contracts_col': ['adv_stir_kcontracts', 'adv_mltir_kcontracts']},
            {'key': 'db1', 'disp': 'Eurex（欧债）', 'color': 'GOLD', 'csv': 'db1.csv',
             'start': '2008-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_eurex_rates_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'EUREX_RATES'},
             ],
             'contracts_col': ['adv_eurex_rates_contracts'],
             'crosscheck_col': ['adv_bund_contracts', 'adv_bobl_contracts',
                                'adv_schatz_contracts', 'adv_euribor3m_contracts'],
             'note': '⚠ 列名 adv_eurex_rates_contracts、单位是**裸张数日均**（unit_scale=ONE）；'
                     '起点 2008-01。四条主力合约列放 crosscheck_col，'
                     '用途是「分品种之和 ≤ 合计」的量级自检，**不可与合计列相加**'},
            {'key': 'tmx', 'disp': 'MX（加元）', 'color': 'GREEN', 'csv': 'tmx.csv',
             'start': '2002-01', 'in_share': True,
             'chain': [
                 {'col': 'mx_adv_stir_futures_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'MX_STIR'},
                 {'col': 'mx_adv_bond_futures_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'MX_BOND'},
             ],
             'contracts_col': ['mx_adv_stir_futures_contracts',
                               'mx_adv_bond_futures_contracts'],
             'crosscheck_col': ['mx_adv_bax_contracts', 'mx_adv_cra_contracts',
                                'mx_adv_cgb_contracts'],
             'note': '⚠ 真实列名带 _futures_ 且是**裸张数**（unit_scale=ONE，'
                     '实测 2026-07 STIR 192,122 张/日）；原写的 mx_adv_stir_kcontracts / '
                     'mx_adv_bond_futures_kcontracts 两列都不存在。'
                     'BAX / CORRA / CGB 三条主力合约列进 crosscheck_col'},
            {'key': 'jpx', 'disp': 'JPX（日元）', 'color': 'GRAY', 'csv': 'jpx.csv',
             'start': '2014-12', 'in_share': True,
             'chain': [
                 {'col': 'adv_jgb10y_futures_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'JPX_JGB10Y'},
             ],
             'contracts_col': ['adv_jgb10y_futures_kcontracts'],
             'note': 'CME 以 SOFR 短端为主、JPX 以 10 年 JGB 长端为主。'
                     '张数口径下两者差两个数量级；名义额口径下差距缩小但仍在，'
                     '**而 DV01 口径下 JPX 会显著上移** —— 这正是 share_caveat 说的那件事'},
        ],
        'excluded': [
            ('enx', 'Euronext 没有利率期货。MTS 现券与回购（adv_mts_cash_eurbn / '
                    'taadv_mts_repo_eurbn）是**另一层**（现券与回购不是衍生品），'
                    '禁止进同一张图'),
            # 2026-08-19 两次改这一条，记账如下：
            # ① 原文「实测只有 2026-06 起 2 个月、不可回补」是抓取器造的假象
            #    （fetch/asx.py:_SFE_LINK 把文件名日期写死 8 位），已回补到 2020-06。
            # ② 第一版改写只说了「起点晚 53 个月 + 是月总张数」，把它写成两件待办 ——
            #    实测下来那两条都不是真正的拦路虎：per_day/div_col 本来就支持除交易日，
            #    而「53 个月」本身是错的（那是 asx.csv 自己的起点 2016-01 到 2020-06；
            #    本池的约束成员是 jpx 2014-12，实际晚 66 个月）。
            #    真正的拦路虎是**起点晚于全仓基期**，且它对两条入池路径同时成立 ——
            #    复刻 exchanges_products.py 第 407-471 行实测：
            #      现状 4 家 → 窗口 2014-12–2026-07（140 个月，0 空洞），基期合计 1,986,926.8
            #      加 ASX   → 窗口 2020-06–2026-07（ 74 个月，0 空洞），基期合计 nan ⇒ skip() 整页不发
            ('asx', '分品种列（contracts_3y_bond_futures / contracts_10y_bond_futures / '
                    'contracts_90d_bankbill_futures）实测 2020-06 起 74 个月、零空洞，'
                    '数据本身够用 —— 拦住它的是**起点晚于全仓基期 2019-01**。'
                    '本池合计按「任一成员缺值该月即缺」求交集：ASX 一进来，'
                    '池窗口就从 2014-12 收到 2020-06（本池少 66 个月），'
                    '而基期 2019-01 落在窗口之外 ⇒ 池在基期没有合计，'
                    '定基指数与「自基期 ±pp」的独占度都无从算起。'
                    '⚠ 走 ICE 那条 contracts_only（只进增长图）**同样不行**：'
                    '增长图也是以 2019-01 = 100 定基，ICE 能进是因为它 2011-01 就有数。'
                    '而 2020-06 是**官方存档天花板**（更早那批链接指向已下线的老站点、'
                    '整体 soft-404），所以这不是「等回补」而是「补不到」。'
                    '另有一处次要且**可解**的口径差：这三列是月总张数不是 ADV，'
                    '真要入池需按 per_day 除以 trading_days_futures。'
                    'ASX 的利率量仍计入 apac_deriv 的混合口径'),
        ],
    },

    {
        'id': 'equity_index', 'zh': '股指衍生品', 'axis': 'product',
        'page': 'exchanges-products',
        'unit_kind': 'notional', 'deflator': 'base_price', 'flow': 'per_day',
        'unit': U_BASE, 'unit_current': U_CURRENT, 'unit_contracts': U_KCTR,
        'share': 'pool', 'levels': True, 'dual_unit': False,
        'basis': (
            '⬆ **档次因新口径而变，而且这个池就是新口径的教科书案例**。'
            '原设计说：「标的与乘数完全不同（ES $50/点 vs SPX 期权 $100/点 vs '
            'CAC40 €10/点 vs 日経225 ¥1000/点），**绝对值同轴就是误导**，只能指数化」。'
            '定基名义额把乘数与基期点位都乘进去之后，这四个数第一次是同一个东西：'
            '「每天有多少美元的股指风险易手」。'),
        'share_caveat': ('分母 = 本池五家之和，是「主要法域股指衍生品名义额构成」，'
                         '不是竞争份额 —— 各家的标的指数几乎不重合。'),
        'denom': None,
        'head': ['cme', 'cboe', 'db1'],
        'members': [
            {'key': 'cme', 'disp': 'CME（E-mini / Micro 系）', 'color': 'NAVY',
             'csv': 'cme.csv', 'start': '2008-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_equity_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'CME_EQUITY_INDEX'},
             ],
             'contracts_col': ['adv_equity_kcontracts'],
             'note': '⚠ 这一列混了 E-mini（$50/点）与 Micro E-mini（$5/点），'
                     '而 Micro 系 2019-05 才上市并迅速起量 —— 张数口径下 CME 的股指业务'
                     '被 Micro 灌了水（多一倍张数只对应十分之一名义额）。'
                     '篮子常数按 2019-01 结构定死会**低估** Micro 起量后的产品拆细效应；'
                     '这是本设计有意接受的偏差：定基就是要把产品设计的变化挡在外面。'
                     '想看拆细本身，去看 contracts_col 的张数序列'},
            {'key': 'cboe', 'disp': 'Cboe（SPX / VIX 期权）', 'color': 'MBLUE',
             'csv': 'cboe.csv', 'start': '2017-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_index_options_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'CBOE_INDEX_OPT'},
             ],
             'contracts_col': ['adv_index_options_kcontracts'],
             'crosscheck_col': ['adv_spx_options_kcontracts',
                                'adv_vix_options_kcontracts'],
             'note': 'SPX 与 VIX 两条分项列挪到 crosscheck_col —— 它们是 '
                     'adv_index_options_kcontracts 的**子集**，与合计列同时求和会重复计数'},
            {'key': 'db1', 'disp': 'Eurex（ESTX50 / DAX）', 'color': 'GOLD',
             'csv': 'db1.csv', 'start': '2008-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_eurex_index_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'EUREX_INDEX'},
             ],
             'contracts_col': ['adv_eurex_index_contracts'],
             'crosscheck_col': ['adv_estoxx50_fut_contracts',
                                'adv_estoxx50_opt_contracts',
                                'adv_dax_fut_contracts', 'adv_dax_opt_contracts']},
            {'key': 'enx', 'disp': 'Euronext（CAC / AEX，legacy 口径）', 'color': 'GREEN',
             'csv': 'enx.csv', 'start': '2012-01', 'in_share': True,
             'chain': enx_legacy_legs(['adv_index_futures_kcontracts',
                                       'adv_index_options_kcontracts'],
                                      'ENX_INDEX_DERIV'),
             'contracts_col': ['adv_index_futures_kcontracts',
                               'adv_index_options_kcontracts'],
             'crosscheck_col': ['athex_adv_index_futures_kcontracts',
                                'athex_adv_index_options_kcontracts'],
             'note': '⚠ 期货与期权在 enx.csv 里是**两列**，没有 adv_index_deriv_kcontracts '
                     '这个合计列；两条主列 + 两条 since=2025-11 的 athex 减法腿'},
            {'key': 'jpx', 'disp': 'JPX（N225 + TOPIX）', 'color': 'GRAY',
             'csv': 'jpx.csv', 'start': '2014-12', 'in_share': True,
             'chain': [
                 {'col': 'adv_n225_lgeq_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'JPX_N225_LGEQ'},
                 {'col': 'adv_topix_futures_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'JPX_TOPIX_FUT'},
             ],
             'contracts_col': ['adv_n225_lgeq_kcontracts',
                               'adv_topix_futures_kcontracts'],
             'note': '⚠ N225 用的是**大合约当量列**，所以 JPX_N225_LGEQ 的乘数取大合约的 '
                     '¥1,000/点，不要再折 mini/micro —— 折两次会把 JPX 压掉一个数量级'},
        ],
        'excluded': [
            ('ice', 'ICE 的股指腿（FTSE / MSCI 授权合约）第 6 个成员，超出每池 ≤5 家的'
                    '硬约束（6 个数据色 − 1 个残差色）。它与 msci.csv 的「上游指数 IP × '
                    '下游成交量」对照放在 fn_index_aum 池；ICE 本身在 rates / energy / '
                    'na_* 四个池已经出场，不是把它从看板上删掉'),
            ('sgx', 'vol_equity_index_futures_contracts 是**月度总量**，需先除交易日；'
                    '隐含日数要用 deriv_vol_contracts ÷ ddav_contracts 反推'
                    '（per_day 的 div_col，见 fx_futures 的 SGX 腿），不能用 sec_trading_days。'
                    'SGX 的股指量已计入 apac_deriv 的合计口径，单列会与那条重复计数'),
            ('miax', 'adv_futures_fin_contracts 实测只有 2026-05 起 **3 个月**，'
                     '2026-07 = 4,194 张/日 vs CME adv_equity_kcontracts 同月量级，'
                     '差三个数量级。只能做「新产品爬坡曲线」，进池会造出无经济含义的占比'),
            ('ndaq', 'series/ndaq_q.csv 的 q_index_linked_derivs_mmcontracts 是'
                     '**别家撮合、Nasdaq 只收授权费**的量，与 CME 的股指量有重合部分'
                     '（同一批合约被两家分别记账）。绝不能与 CME 同柱比「谁成交大」。'
                     '且是**季度**表，不能插值成月度'),
        ],
    },

    {
        'id': 'single_stock_etf_opt', 'zh': '单股与 ETF 期权', 'axis': 'product',
        'page': 'exchanges-products',
        'unit_kind': 'notional', 'deflator': 'base_price', 'flow': 'per_day',
        'unit': U_BASE, 'unit_current': U_CURRENT, 'unit_contracts': U_KCTR,
        'share': 'pool', 'levels': True, 'dual_unit': False,
        'basis': (
            '⬆ 档次因新口径而变（原 none）。**这个池只在北美内部是真竞争**'
            '（见 na_multilist_opt），其余各家是不同法域的同业务形态对照 —— '
            '各自本土的唯一或主要场所，不争同一批订单流。'
            '图注必须写明，否则会被误读成市占率此消彼长。'),
        'share_caveat': ('分母 = 本池五家之和，是「各法域单股/ETF 期权名义额构成」。'
                         '美国侧只放 Cboe 一家做法域代表 —— 美国内部的真份额在 '
                         'na_multilist_opt，那里有官方行业分母，信息比这里强得多。'),
        'denom': None,
        'head': ['cboe', 'db1'],
        'members': [
            {'key': 'cboe', 'disp': 'Cboe（美国代表）', 'color': 'MBLUE', 'csv': 'cboe.csv',
             'start': '2017-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_multilist_options_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'US_MULTILIST_EQ_OPT'},
             ],
             'contracts_col': ['adv_multilist_options_kcontracts']},
            {'key': 'db1', 'disp': 'Eurex（欧洲）', 'color': 'NAVY', 'csv': 'db1.csv',
             'start': '2008-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_eurex_equity_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'EUREX_EQUITY'},
             ],
             'contracts_col': ['adv_eurex_equity_contracts'],
             'note': '⚠ 含 single stock futures，Cboe 那列是纯期权。'
                     '名义额口径下这个差异被放大（单股期货的名义额与期权同量级），'
                     '图注必须点名。列名 _contracts、裸张数、起点 2008-01'},
            {'key': 'tmx', 'disp': 'MX（加拿大）', 'color': 'GREEN', 'csv': 'tmx.csv',
             'start': '2002-01', 'in_share': True,
             'chain': [
                 {'col': 'mx_adv_equity_options_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'MX_EQUITY_OPT'},
                 {'col': 'mx_adv_etf_options_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'MX_ETF_OPT'},
             ],
             'contracts_col': ['mx_adv_equity_options_contracts',
                               'mx_adv_etf_options_contracts']},
            {'key': 'jpx', 'disp': 'JPX（日本）', 'color': 'GRAY', 'csv': 'jpx.csv',
             'start': '2014-12', 'in_share': True,
             'chain': [
                 {'col': 'adv_secoptions_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'JPX_SEC_OPT'},
             ],
             'contracts_col': ['adv_secoptions_kcontracts']},
            {'key': 'asx', 'disp': 'ASX ETO（澳洲）', 'color': 'GOLD', 'csv': 'asx.csv',
             'start': '2017-10', 'in_share': True,
             'chain': [
                 {'col': 'adv_single_stock_options_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'ASX_ETO'},
             ],
             'contracts_col': ['adv_single_stock_options_contracts'],
             'note': '⚠ 同一列也进 apac_deriv 的合计口径。同一个量出现在两个池里不是错误'
                     '（两个池回答不同问题），但两页的数字必须一致，build 应当交叉断言'},
        ],
        'excluded': [
            ('miax', '美国侧本池只放一个法域代表（Cboe）。MIAX 与 Cboe 的真份额对比在 '
                     'na_multilist_opt —— 那里有 ICE 的官方行业分母，'
                     '把两家同时塞进本池只会用掉一个颜色位却回答同一个问题'),
            ('enx', 'adv_singlestock_futures_kcontracts + adv_singlestock_options_kcontracts '
                    '含期货，且 2025-11 起 Athex 单股期货占 90-98% 且是融券替代品'
                    '不是方向性交易。legacy 口径（主列 − athex 备注列）已经在 eu_deriv 的'
                    '合计腿里算了；单独成线要等 legacy 序列回补够长'),
        ],
    },

    {
        'id': 'energy', 'zh': '能源商品', 'axis': 'product', 'page': 'exchanges-products',
        'unit_kind': 'notional', 'deflator': 'base_price', 'flow': 'per_day',
        'unit': U_BASE, 'unit_current': U_CURRENT, 'unit_contracts': U_KCTR,
        'share': 'pool', 'levels': True, 'dual_unit': False,
        'basis': (
            '⬆ 档次因新口径而变（原 none：「合约标的不可比（桶 / MMBtu / MWh）」）。'
            '定基名义额把桶价、气价、电价都换成基期美元，三者可加可比。'
            '全仓最有故事的一对：**Brent（ICE）vs WTI（CME）的基准之争** —— '
            '这一对是真正争同一批订单流的。'
            '⚠ **本池的 ICE 只含 Brent 原油（期货+期权），不是 ICE 的全部能源** —— '
            '详见 scope_note，这一条必须进图注。'),
        # 📌 页面硬性要求：任何画到 ICE 这条腿的图，图注必须带这段话。
        #    它不是"补充说明"，它是这条腿能被读懂的前提 —— 少了它，读者会把
        #    ICE 的三分之一读成 ICE 的全部，进而得出「CME 能源规模是 ICE 的几倍」
        #    这种**方向都可能反**的结论。
        'scope_note': (
            '⚠ **ICE 这条腿只含 Brent 原油（期货 + 期权），不是 ICE 的全部能源。** '
            '2019-01 Brent 占 ICE 全能源张数的 34.8%（947 / 2,718 千张日均），'
            '187 个月中位 33.3%；ICE 的天然气（含 TTF）、电力、其他油品、排放权**都不在这条线里**。'
            '这是**主动选择的低覆盖**：ICE 全能源那一列（adv_energy_kcontracts）是全球口径'
            '（IFEU + Endex + IFUS + IFAD + NGX），而 ICE 唯一公开、不要 reCAPTCHA 的'
            '分产品历史表只覆盖 ICE Futures Europe（2019-01 只占全球 67.0%），'
            'TTF 更在 Endex 上且没有固定乘数。用 67% 的结构去套 100% 的量，'
            '偏差方向与大小都不可知；宁可覆盖 34.8% 而零偏差。'
            '⇒ 本池的 ICE 柱**系统性地低于** ICE 的真实能源体量，'
            '「CME 能源是 ICE 的几倍」这句话在本图上不成立。'
            '（Gasoil 本可再加 11.5pp 覆盖率，卡在 2019-01 官方基期价拿不到 —— '
            'Gasoil 以美元/公吨报价，EIA 全站没有这个口径，ICE 自己的历史结算价在 '
            'reCAPTCHA 后面。见 contract_specs.csv 的 ICE_GASOIL_FUT 行。）'),
        'share_caveat': ('分母 = 本池三家之和，且 **ICE 那一份只算 Brent**（见 scope_note）'
                         '⇒ ICE 的占比是**下界**，不是它在能源里的真实份额。'
                         '⚠ **名义额相同不等于能量相同**：'
                         '一张 WTI 是 1,000 桶原油、一张 HH 是 10,000 MMBtu 天然气，'
                         '热值完全不同。占比读作「美元名义额构成」，不是「能源风险构成」。'),
        'denom': None,
        'head': ['cme', 'ice'],
        'members': [
            {'key': 'cme', 'disp': 'CME（WTI / Henry Hub）', 'color': 'NAVY',
             'csv': 'cme.csv', 'start': '2008-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_energy_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'CME_ENERGY'},
             ],
             'contracts_col': ['adv_energy_kcontracts']},
            {'key': 'ice', 'disp': 'ICE（仅 Brent 原油）', 'color': 'MBLUE', 'csv': 'ice.csv',
             'start': '2011-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_brent_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'ICE_BRENT_IFEU'},
             ],
             'contracts_col': ['adv_brent_kcontracts'],
             'crosscheck_col': ['adv_energy_kcontracts'],
             'note': '⚠ **列换了**：2026-08-06 由 adv_energy_kcontracts（ICE 全球全能源）'
                     '改为 adv_brent_kcontracts（仅 Brent）。原因不是"Brent 更重要"，'
                     '是**只有 Brent 这一列的口径与乘数对得上** —— 官方脚注(1) 保证整列'
                     '以 ICE Futures Europe 标准合约当量计（新交所的迷你合约已被官方 ÷10 '
                     '折算进来），所以「张数 × 1,000 桶」精确成立；'
                     '而 Nat Gas / Power / Other Oil / Environmentals 每一行内部都混着'
                     '多种量纲与多个交易所，一个乘数套不上去。'
                     '⚠ 全能源那一列留在 crosscheck_col 里**只做覆盖率对账**'
                     '（Brent ÷ 全能源 = 这条腿代表了多少），'
                     '**绝不可加进 chain** —— 加进去就回到了口径不一致的老路。'
                     '⚠ OI 一边千张一边裸张：ice.oi_energy_kcontracts vs '
                     'cme.oi_energy_contracts 差 1000 倍。OI 若要并排画，'
                     '同样走名义额链，且 ICE 侧没有 Brent 单独的 OI 列（官方只到 Energy 合计）'
                     '⇒ **OI 这一对暂时画不了**，别拿 Brent 的量配全能源的 OI'},
            {'key': 'jpx', 'disp': 'JPX（旧 TOCOM）', 'color': 'GRAY', 'csv': 'jpx.csv',
             'start': '2020-08', 'in_share': True,
             'chain': [
                 {'col': 'adv_deriv_cmdty_raw_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'JPX_CMDTY'},
             ],
             'contracts_col': ['adv_deriv_cmdty_raw_kcontracts'],
             'crosscheck_col': ['cmdty_proforma'],
             'note': '⚠ 列名是 adv_deriv_cmdty_**raw**_kcontracts（另有 _lgeq_ 当量列，'
                     '本池不用，理由同 apac_deriv）。'
                     '⚠ 起点由 2020-07 改为 **2020-08**：jpx.csv 自带一列 cmdty_proforma '
                     '标记哪些月是回填的，实测它在 2014-12 – **2020-07** 恒为 1、'
                     '2020-08 起为空 ⇒ 2020-07 那一格本身还是 pro-forma，'
                     '卡在 2020-07 会把一格假数画进图。之前的月份必须留空，不得 pro-forma'},
        ],
        'excluded': [
            ('db1', 'vol_power_deriv_mwh / vol_gas_mwh 是 **MWh 不是张数**'
                    '（实测 2026-06 电力 960,720,291 MWh），'
                    '没有"张"就没有乘数，换算链的第一跳就断了。'
                    '📌 未找到 EEX 电力/天然气的月度张数列（官方只给能量单位）。'
                    '只能单独做同比，不进本池'),
            ('enx', 'Nord Pool 电力是 TWh/GWh（adv_power_dayahead_twh 等）且仓内无对手；'
                    'adv_commodity_futures_kcontracts + adv_commodity_options_kcontracts '
                    '是**农产品**（MATIF），要配 cme.adv_ag_kcontracts，'
                    '绝不能配 adv_energy_kcontracts'),
            ('sgx', 'vol_commodities_contracts 里 98% 是铁矿石与干散货运费，'
                    '与能源不是同一标的'),
        ],
    },

    {
        'id': 'ags', 'zh': '农产品', 'axis': 'product', 'page': 'exchanges-products',
        'unit_kind': 'notional', 'deflator': 'base_price', 'flow': 'per_day',
        'unit': U_BASE, 'unit_current': U_CURRENT, 'unit_contracts': U_KCTR,
        'share': 'pool', 'levels': True, 'dual_unit': False,
        'basis': ('⬆ 档次因新口径而变（原 none）。蒲式耳与吨都换成基期美元后可加可比。'
                  '但标的几乎不重合（玉米/大豆/小麦复合体 vs MATIF 欧洲小麦/菜籽 vs '
                  '春小麦），占比是量级构成不是竞争结果。'),
        'share_caveat': '分母 = 本池两家之和（MIAX 只做规模对照，不进分子）。',
        'denom': None,
        'head': ['cme', 'enx'],
        'members': [
            {'key': 'cme', 'disp': 'CME（玉米/大豆/小麦复合体）', 'color': 'NAVY',
             'csv': 'cme.csv', 'start': '2008-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_ag_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'CME_AG'},
             ],
             'contracts_col': ['adv_ag_kcontracts']},
            {'key': 'enx', 'disp': 'Euronext MATIF', 'color': 'MBLUE', 'csv': 'enx.csv',
             'start': '2012-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_commodity_futures_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'ENX_MATIF'},
                 {'col': 'adv_commodity_options_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'ENX_MATIF'},
             ],
             'contracts_col': ['adv_commodity_futures_kcontracts',
                               'adv_commodity_options_kcontracts'],
             'note': '⚠ enx.csv 里没有 adv_commodity_deriv_kcontracts 合计列，'
                     '期货与期权分两列 ⇒ 两条腿。'
                     '⚠ **没有** athex 减法腿：enx.csv 的 athex_* 备注列里没有商品项'
                     '（MATIF 与 Athens 无关），凭空造一个减法腿会读到不存在的列'},
            {'key': 'miax', 'disp': 'MIAX Futures（春小麦）', 'color': 'GRAY',
             'csv': 'miax.csv', 'start': '2025-01', 'in_share': False,
             'chain': [
                 {'col': 'adv_futures_ag_contracts', 'src': 'contracts',
                  'unit_scale': ONE, 'per_day': None, 'product': 'MIAX_AG_WHEAT'},
             ],
             'contracts_col': ['adv_futures_ag_contracts'],
             'note': '⚠ 只有 Minneapolis 硬红春小麦一个品种，与 CME 标的不重合。'
                     '复核明确反对把它当份额用（docs/verify/verify_miax.md §四）'
                     '—— in_share=False，'
                     '只进量级对照。换成名义额并没有改变这个理由：'
                     '不重合的标的不因为单位统一了就变成同一门生意'},
        ],
        'excluded': [],
    },

    {
        'id': 'fx_futures', 'zh': 'FX 期货', 'axis': 'product', 'page': 'exchanges-products',
        'unit_kind': 'notional', 'deflator': 'base_price', 'flow': 'per_day',
        'unit': U_BASE, 'unit_current': U_CURRENT, 'unit_contracts': U_KCTR,
        'share': 'pool', 'levels': True, 'dual_unit': False,
        'basis': ('⬆ 档次因新口径而变（原 none）。**期货张数**换成基期美元名义额。'
                  '与下面的 FX 即期 ECN 池是两层不同的东西（场内期货 vs 场外即期），'
                  '严禁混画 —— 但现在两池的单位相同了，更要靠图与图的分隔来防混读。'),
        'share_caveat': '分母 = 本池两家之和。全球 FX 期货还有别家（如 B3、MOEX），不在池里。',
        'denom': None,
        'head': ['cme', 'sgx'],
        'members': [
            {'key': 'cme', 'disp': 'CME', 'color': 'NAVY', 'csv': 'cme.csv',
             'start': '2008-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_fx_kcontracts', 'src': 'contracts',
                  'unit_scale': K, 'per_day': None, 'product': 'CME_FX'},
             ],
             'contracts_col': ['adv_fx_kcontracts']},
            {'key': 'sgx', 'disp': 'SGX（全球前三）', 'color': 'MBLUE', 'csv': 'sgx.csv',
             'start': '2015-01', 'in_share': True,
             'chain': [
                 {'col': 'vol_fx_futures_contracts', 'src': 'contracts',
                  'unit_scale': ONE,
                  'per_day': {'col': 'deriv_vol_contracts',
                              'div_col': 'ddav_contracts'},
                  'product': 'SGX_FX'},
             ],
             'contracts_col': ['vol_fx_futures_contracts'],
             'crosscheck_col': ['deriv_vol_contracts', 'ddav_contracts'],
             'note': '⚠ sgx.csv 里**没有** implied_days 这一列（原写法凭空发明的），'
                     '也没有 vol_fx_futures_kcontracts —— 真实列是 '
                     'vol_fx_futures_contracts，**月度总张数**（2026-06 = 10,268,040）。'
                     '隐含交易日在换算链里现算：per_day 的 div_col 让引擎取 '
                     'deriv_vol_contracts ÷ ddav_contracts（官方月总量 ÷ 官方日均），'
                     '实测 2026-06 = 21.19 天、2026-05 = 18.96 天 —— 非整数是因为官方对 '
                     'DDAV 做过舍入，但这就是 SGX 自己记账用的那个日数。'
                     '**不要用 sec_trading_days**（21 / 19 天，是证券市场日历，'
                     '与衍生品不同；docs/verify/verify_sgx.md 口径坑 4/6）'},
        ],
        'excluded': [
            ('ice', 'adv_fx_credit_kcontracts 是 **FX 与信用合并**披露，口径不纯；'
                    '两类合约的名义额量纲虽同为美元，但信用合约的名义额与 FX 完全不是'
                    '同一件事。要进必须先拆，官方不拆'),
            ('tmx', '📌 tmx.csv 里没有任何 FX 期货列（USX 量太小，fetch 侧没入库），'
                    '无从入池'),
            ('jpx', '📌 jpx.csv 里没有 FX 期货列；USD/JPY 等 2026-04 才上市，'
                    '第一版不入池'),
        ],
    },

    {
        'id': 'fx_spot_ecn', 'zh': 'FX 即期 ECN', 'axis': 'product',
        'page': 'exchanges-products',
        'unit_kind': 'notional', 'deflator': 'fx_only', 'flow': 'per_day',
        'unit': U_FXONLY, 'unit_current': U_CURRENT, 'unit_contracts': None,
        'share': 'pool', 'levels': True, 'dual_unit': False,
        'basis': (
            'ADNV、单边计。Euronext FX（原 FastMatch）与 Cboe FX（原 Hotspot）'
            '是**同一门生意**，全仓最干净的一对之一。'
            '⚠ 源列是成交额 ⇒ deflator=fx_only。但 FX 即期的"标的涨跌"就是汇率本身，'
            '所以这里的 fx_only 有一层额外含义：360T 的 €金额折成美元只换了记账币，'
            '并没有剔掉它成交的那些货币对的波动 —— 后者无法剔，也不该剔'
            '（FX 成交额的自然口径就是名义额）。'),
        'share_caveat': ('分母 = 本池三家之和。全球 FX 即期的分母（BIS 三年一次的'
                         'Triennial Survey）频率对不上月度看板，不能当分母。'),
        'denom': None,
        'head': ['cboe', 'enx'],
        'members': [
            {'key': 'cboe', 'disp': 'Cboe FX', 'color': 'MBLUE', 'csv': 'cboe.csv',
             'start': '2017-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_fx_adnv_usdbn', 'src': 'notional', 'unit_scale': BN,
                  'per_day': None, 'product': 'FX_SPOT_USD'},
             ],
             'contracts_col': []},
            {'key': 'enx', 'disp': 'Euronext FX', 'color': 'NAVY', 'csv': 'enx.csv',
             'start': '2013-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_fx_spot_usdbn', 'src': 'notional', 'unit_scale': BN,
                  'per_day': None, 'product': 'FX_SPOT_USD'},
             ],
             'contracts_col': []},
            {'key': 'db1', 'disp': '360T', 'color': 'GOLD', 'csv': 'db1.csv',
             'start': '2015-01', 'in_share': True,
             'chain': [
                 {'col': 'adv_360t_fx_eurbn', 'src': 'notional', 'unit_scale': BN,
                  'per_day': None, 'product': 'FX_SPOT_EUR'},
             ],
             'contracts_col': [],
             'note': '⬆ **in_share 从 False 改成 True，这是新口径最直接的一处收益**。'
                     '原设计因为「单位是 EUR bn，另两家是 USD bn，不做汇率折算（仓库硬约束）」'
                     '把 360T 排除在水平图与池内占比之外，只让它进指数化图。'
                     '本批次的规则把折算从"禁止"改成"锁基期汇率、在 build 侧做、'
                     '汇率入库可查"，于是 360T 第一次能与另两家同轴、也能进分子。'
                     '⚠ 但 360T 是慢腿列（DB1 的 OTC 侧，实测停在 2026-06 而 db1.csv '
                     '已有 2026-07 行），**它进池但不进 head**，'
                     '且 build 必须容忍它在最新月缺值。起点实测 2015-01（原写 2016-01）'},
        ],
        'evidence': '2026-06 实测 Euronext 30.527 vs Cboe 64.27 USD bn/day '
                    '（docs/verify/verify_enx.md §1.7）',
        'excluded': [],
    },

    # ══════════════════════ 轴三：职能层 ══════════════════════
    # 交易所不是只有撮合一层。这一轴回答「同一家公司在价值链的哪一段赚钱、
    # 哪一段在被侵蚀」——Euronext 与 DB1 的上市/结算是垄断而交易是竞争，
    # 这个「一半垄断、一半竞争」的结构，正是横截面页最值得画出来的那条张力。

    {
        'id': 'fn_listing', 'zh': '上市与募资（一级市场）', 'axis': 'function',
        # 归属 exchanges-apac：4 个成员位里 3 个（hkex / sgx / asx）是亚太，
        # head 也是这三家，enx 只是欧洲那一侧的对照。原挂在 exchanges-intl 上，
        # 那张欧亚合页已于 2026-08-06 删除（见 docs/DELIVERY.md §4.4）。
        'page': 'exchanges-apac',
        'unit_kind': 'count_and_raise', 'deflator': 'fx_only', 'flow': 'per_month',
        'unit': U_COUNT, 'unit_raise': U_BASE_MO, 'unit_current': None,
        'unit_contracts': None,
        'share': 'none', 'levels': True, 'dual_unit': False,
        'basis': (
            '两个量、两种单位：**新上市家数是纯计数，本来就可直接跨家比**；'
            '募资额是各家本币的月度流量，折基期汇率后可比（这是新口径带来的改进，'
            '原设计只能指数化）。'
            '一级市场是交易所里少数几乎没有跨境竞争的环节 —— 它的周期与二级市场成交量'
            '经常反向，把它与撮合量并列，才看得出「量在别人手上、单子在自己手上」。'),
        'share_caveat': None,
        'why_none': (
            'share=none 不是因为单位不可比（新口径已经解决了），而是因为**没有池**：'
            '一家公司在哪里上市不是这四家在瓜分同一批 IPO —— 大部分发行人根本没有'
            '跨法域选择。把四家家数加起来当分母，占比会随某地一次大 IPO 剧烈跳动，'
            '却不代表任何人赢了或输了。'),
        'denom': None,
        'head': ['hkex', 'sgx', 'asx'],
        'members': [
            {'key': 'hkex', 'disp': 'HKEX', 'color': 'GOLD', 'csv': 'hkex.csv',
             'start': '2024-06', 'in_share': False,
             'count_col': 'new_listings',
             'chain': [
                 {'col': 'ipo_funds_hkdbn', 'src': 'notional', 'unit_scale': BN,
                  'per_day': None, 'product': 'RAISE_HKD'},
             ],
             'contracts_col': [],
             'note': '⚠ IPO 募资是暂定数，官方会上修 ⇒ 只填空不覆盖，且末月要标「暂定」。'
                     '⚠ 起点由 2019-01 改为 **2024-06**：hkex.csv 的 adt/衍生品列确实'
                     '从 2019-01 起，但本池要的两列晚得多 —— new_listings 实测 '
                     '2024-06 起 25 个月、ipo_funds_hkdbn 2024-01 起 31 个月，'
                     '取两者较晚的那个。成员起点写早了会让 head 的空洞检查当场 raise'},
            {'key': 'sgx', 'disp': 'SGX', 'color': 'MBLUE', 'csv': 'sgx.csv',
             'start': '2015-01', 'in_share': False,
             'count_col': 'ipos_count',
             'chain': [
                 {'col': 'ipo_funds_sgdmn', 'src': 'notional', 'unit_scale': MN,
                  'per_day': None, 'product': 'RAISE_SGD'},
             ],
             'contracts_col': []},
            {'key': 'asx', 'disp': 'ASX', 'color': 'GREEN', 'csv': 'asx.csv',
             'start': '2023-10', 'in_share': False,
             'count_col': 'new_listed_entities',
             'chain': [
                 {'col': 'capital_new_quoted_audmn', 'src': 'notional', 'unit_scale': MN,
                  'per_day': None, 'product': 'RAISE_AUD'},
             ],
             'contracts_col': [],
             'note': '⚠ 上市实体含债券发行人，与 HKEX 的「新上市公司」口径不同，图注必写。'
                     '⚠ 起点 **2023-10**：new_listed_entities 从 2017-10 起，'
                     '但募资列 capital_new_quoted_audmn 实测只有 2023-10 起 34 个月'},
            {'key': 'enx', 'disp': 'Euronext（legacy 口径）', 'color': 'NAVY',
             'csv': 'enx.csv', 'start': '2018-01', 'in_share': False,
             'count_col': None,
             'chain': enx_legacy_legs(['money_raised_new_listings_eurm'],
                                      'RAISE_EUR', unit_scale=MN, src='notional'),
             'contracts_col': [],
             'note': 'issuers_equities 是**存量家数**不是新增，与另三家的口径不同 ⇒ '
                     'count_col 留 None，Euronext 只进募资图，不进家数图。'
                     '募资额同样走 legacy 口径（athex_money_raised_new_listings_eurm '
                     '备注列，since=2025-11），与 eu_cash / eu_deriv 的 Euronext 一致'},
        ],
        'excluded': [
            ('ndaq', 'series/ndaq_q.csv 的 q_listed_cos_us / q_listings_total 是**季度**，'
                     '不能插值成月度'),
            ('jpx', 'jpx.csv 有 ipo_public_offerings / ipo_funds_jpybn 两列，'
                    '但第一版不做（侦察稿已说明成本判断）；要进池需先核对'
                    '「公开发行家数」与另三家「新上市家数」是否同一口径'),
        ],
    },

    {
        'id': 'fn_index_aum', 'zh': '指数 IP 与挂钩资产（存量）', 'axis': 'function',
        'page': 'exchanges-products',
        'unit_kind': 'notional', 'deflator': 'fx_only', 'flow': 'stock',
        'unit': U_FXONLY_STOCK, 'unit_current': 'USD bn, current prices & FX',
        'unit_contracts': None,
        'share': 'none', 'levels': True, 'dual_unit': False,
        'basis': (
            '挂钩自家指数的 ETF 资产。**全仓唯一一对真正同形的指数授权规模指标** —— '
            '与成交量池并置的意义在于：成交量是流量、AUM 是存量，'
            '同一轮行情里两者的弹性完全不同，只看成交量会把周期性误读成结构性。'
            '⬆ 折基期汇率后 €bn 与 $bn 第一次能同轴比水平值（原设计只能指数化）。'
            '⚠ AUM 本身就是市值 ⇒ "定基价格"不适用，只锁汇率（deflator=fx_only）：'
            '资产涨了和资金流入了在这条序列里分不开，这是它的固有属性不是我们的选择。'),
        'share_caveat': None,
        'why_none': (
            '全球指数挂钩资产的分母远大于 MSCI + STOXX/DAX 两家之和'
            '（S&P DJI、FTSE Russell、CRSP、Bloomberg 都不在池里，且没有一家按月披露）。'
            '两家之和的占比会被读成「指数行业二分天下」——'
            '这正是 share=pool 那一档最容易被误读的形态，所以这里退到 none。'),
        'denom': None,
        'head': ['msci', 'db1'],
        'members': [
            {'key': 'msci', 'disp': 'MSCI 挂钩 ETF AUM', 'color': 'NAVY', 'csv': 'msci.csv',
             'start': '2008-12', 'in_share': False,
             'chain': [
                 {'col': 'aum_eop_usdbn', 'src': 'notional', 'unit_scale': BN,
                  'per_day': None, 'product': 'AUM_USD'},
             ],
             'contracts_col': []},
            {'key': 'db1', 'disp': 'STOXX / DAX 挂钩 ETF AUM', 'color': 'GOLD',
             'csv': 'db1.csv', 'start': '2012-01', 'in_share': False,
             'chain': [
                 {'col': 'aum_stoxx_dax_etf_eurbn', 'src': 'notional', 'unit_scale': BN,
                  'per_day': None, 'product': 'AUM_EUR'},
             ],
             'contracts_col': []},
        ],
        'excluded': [
            ('hkex', 'mktcap_hkdtn 是**市值**不是托管/AUM，只能并置不能相除'),
            ('db1_auc', 'Clearstream 托管资产（db1.csv 里是 auc_securities_services_eurbn '
                        '与 auc_fund_services_eurbn 两列，没有 auc_group_total_eurtn 这一列）'
                        '是慢腿，次月约 10 日才出 ⇒ 不得进横截面 panel，只放 db1 单公司页'),
        ],
    },

    {
        'id': 'fn_monopoly', 'zh': '结构对照：垄断 vs 竞争', 'axis': 'function',
        'page': 'exchanges-na',
        'unit_kind': 'share_pp', 'deflator': None, 'flow': 'per_day',
        'unit': U_SHARE_PP, 'unit_current': None, 'unit_contracts': U_KCTR,
        'share': 'true', 'levels': True, 'dual_unit': False,
        'basis': (
            '⚠ 这个池是**复核过程中被砍掉一半**的那个。原侦察稿设想「ICE 份额十五年跌 8pp '
            'vs HKEX 恒为 100%」是最直白的一张图，但 docs/verify/verify_ice.md §5 实锤：'
            'hkex.csv 里**根本没有任何份额字段**，"HKEX 恒为 100%" 是断言不是数据，'
            '要画只能在代码里硬写常数 1.0 —— 那不是数据看板该干的事。'
            '⇒ 本池只保留**有真实份额序列的成员**。'
            '本池的成员是**份额序列本身**（pp），不走名义额换算链 —— '
            '份额是无量纲的比值，乘一个常数只会把它变成一个没有意义的数。'),
        'share_caveat': None,
        'dual_note': (
            '⚠ 官方给的这四条份额序列**全部是张数/股数口径**，'
            '这也是它们能被外部核对的原因。名义额口径下的份额由 na_cash / '
            'na_multilist_opt 两池自己算，两者应当相等（同一批合约、同一个基期常数）。'
            '若不相等，是换算链坏了，不是"两种口径的差异"。'),
        'denom': None,          # 份额序列自带分母，不需要本池再声明一个
        # head 只放 ICE 的两条：它们从 2011-01 起 187 个月无空洞、次月第 3 个交易日就出。
        # MIAX 起点 2015-04、NDAQ 那条来自 nasdaqtrader（次月第 10 个工作日，慢腿），
        # 任一进 head 都会把「NYSE 十五年份额下滑」这条主线的窗口砍掉四年或拖慢一周。
        'head': ['ice', 'ice2'],
        'members': [
            {'key': 'ice', 'disp': 'NYSE 美股现货份额', 'color': 'NAVY', 'csv': 'ice.csv',
             'start': '2011-01', 'in_share': True, 'chain': None,
             'share_col': 'share_nyse_us_cash_matched', 'share_scale': 100.0,
             'contracts_col': [],
             'note': '官方直接给，187/187 与自算一致（误差 <0.15pp）。'
                     '2011-01 26.9% → 2026-07 19.1%'},
            {'key': 'ice2', 'disp': 'NYSE 美股期权份额', 'color': 'MBLUE', 'csv': 'ice.csv',
             'start': '2011-01', 'in_share': True, 'chain': None,
             'share_col': 'share_nyse_equity_options', 'share_scale': 100.0,
             'contracts_col': [], 'note': '24.5% → 21.1%'},
            {'key': 'miax', 'disp': 'MIAX 期权份额', 'color': 'GOLD', 'csv': 'miax.csv',
             'start': '2025-01', 'in_share': True, 'chain': None,
             'share_col': 'share_multilist_options_pct', 'share_scale': 1.0,
             'contracts_col': [],
             'note': '⚠ 官方自报份额，分母是 MIH 自己的行业 ADV。与 ICE 分母不同 ⇒ '
                     '本页统一改用 ICE 行业分母重算，官方值只做校验。'
                     '⚠ 起点由 2015-04 改为 **2025-01**：这条自报份额来自 IR 月报，'
                     '实测只有 19 个月（2026-07 = 17.1，已经是百分数 ⇒ share_scale=1.0）。'
                     '2015-04 起的长历史在 API 列那边，但那是量不是份额，'
                     '要长历史份额只能用 ICE 分母自己算（na_multilist_opt 已经这么做）'},
            {'key': 'ndaq', 'disp': 'Nasdaq 美股现货份额', 'color': 'GRAY', 'csv': 'ndaq.csv',
             'start': '2010-10', 'in_share': True, 'chain': None,
             'share_col': 'share_us_cash_matched_group', 'share_scale': 100.0,
             'contracts_col': [],
             'note': '⚠ 列名是 share_us_cash_matched_group（原写的 '
                     'us_matched_mktshare_pct 不存在），且存的是**小数**不是百分数'
                     '（实测 2026-06 = 0.1477）⇒ share_scale=**100.0**。'
                     '写成 1.0 会把 14.8% 画成 0.15pp，而图上只是一条贴着零轴的线。'
                     '⚠ 来自 nasdaqtrader（次月第 10 个工作日，实测停在 2026-06）'
                     '⇒ **慢腿，不进 head**；最新月用 ICE 分母现算，历史用官方值回补'},
        ],
        'excluded': [
            ('hkex', 'hkex.csv 没有任何份额字段，"垄断方恒为 100%" 是断言不是数据。'
                     '垄断侧改用可测量的替代指标：画垄断方的**量本身**与竞争方的**份额**并置'),
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# 查询与校验
# ═══════════════════════════════════════════════════════════════════════════
POOL_BY_ID = {p['id']: p for p in POOLS}


def pool(pool_id):
    if pool_id not in POOL_BY_ID:
        raise PoolSpecError('没有 id=%r 的池（已有 %s）'
                            % (pool_id, ', '.join(sorted(POOL_BY_ID))))
    return POOL_BY_ID[pool_id]


def pools_on(page):
    """某一页要画的池，按 POOLS 里的顺序。"""
    return [p for p in POOLS if p['page'] == page]


def fx_basis(p):
    """池 → 该用哪一档汇率：'avg' 配流量、'eom' 配存量。

    **build 脚本取汇率档次的唯一合法入口。** 不要在调用点手写 'avg' / 'eom'
    字面量 —— fetch/fx.py 把「两列混用」列为它唯一一个「用错了不会报错」的坑：
    拿月末汇率折整月成交额，等于把整月流量按最后一天记账；拿月均折 AUM，
    等于给一个时点余额安一个不存在的平均价。两种错都只会在同比里多出一段
    汇率噪声，没有任何一处会抛异常。

    所以档次不由人选，由池的 `flow` 字段机械推出，映射表在
    notional.FLOW_TO_FX_BASIS（只有一份，这里只是委托）。
    全仓 17 个池里 16 个是流量，唯一的存量池是 fn_index_aum（挂钩 ETF 的 AUM）。
    """
    return notional.basis_for_flow(p['flow'])


def chains_of(p):
    """池里所有带换算链的对象（成员 + 分母），吐 (标签, csv, chain) 三元组。"""
    out = []
    d = p.get('denom')
    if d and d.get('chain'):
        out.append(('%s.denom' % p['id'], d['csv'], d['chain']))
    for m in p['members']:
        if m.get('chain'):
            out.append(('%s.%s' % (p['id'], m['key']), m['csv'], m['chain']))
    return out


def products_used(pools=None):
    """全部（或指定）池引用到的 product_id，排序去重。喂给 notional.pending_products。"""
    out = set()
    for p in (pools if pools is not None else POOLS):
        for _lab, _csv, chain in chains_of(p):
            for leg in chain:
                out.add(leg['product'])
    return sorted(out)


def contracts_only_members(p):
    """本池里永久停留在张数口径的成员（只进增长图）。"""
    return [m for m in p['members'] if m.get('contracts_only')]


def contracts_only_products(pools=None):
    """**只**被张数口径成员引用的 product_id —— 它们的基期常数永远不会填。

    为什么要单独有这个清单：`notional.pending_products` 把「没有基期价格」一律
    当成「还没测出来」，而 build 脚本照 exchanges.py 第 3 条规矩会**整池 skip**。
    ICE_STIR / ICE_MLTIR 属于「测不出来，而且就算测出来也不该用」，
    照 pending 处理会让 rates 与 eu_deriv 两个池永久画不出来 —— 那是拿一个
    口径判断去毁掉两页本来完全成立的图。

    「只被」三个字是硬要求：同一个 product 若还被别的（非张数口径）成员引用，
    它仍然必须补齐常数，不能借这条通道蒙混过关。
    """
    only, other = set(), set()
    for p in (pools if pools is not None else POOLS):
        co = {id(m) for m in contracts_only_members(p)}
        d = p.get('denom')
        if d and d.get('chain'):
            other |= {leg['product'] for leg in d['chain']}
        for m in p['members']:
            bucket = only if id(m) in co else other
            bucket |= {leg['product'] for leg in (m.get('chain') or [])}
    return sorted(only - other)


def products_needing_specs(pools=None):
    """真正需要基期常数的产品 = products_used() − contracts_only_products()。

    **build 脚本查「这个池能不能画」时该用这个，不是 products_used()。**
    """
    skip = set(contracts_only_products(pools))
    return [pid for pid in products_used(pools) if pid not in skip]


def csvs_used(pools=None):
    """全部池要读的 series/*.csv。用于「成员是否就绪」的门槛检查。"""
    out = set()
    for p in (pools if pools is not None else POOLS):
        d = p.get('denom')
        if d:
            out.add(d['csv'])
        for m in p['members']:
            out.add(m['csv'])
            for leg in (m.get('chain') or []):
                if leg.get('csv'):
                    out.add(leg['csv'])
                pd_spec = leg.get('per_day')
                if pd_spec and pd_spec.get('csv'):
                    out.add(pd_spec['csv'])
    return sorted(out)


def cols_used(p):
    """某池要读的 {csv: [列名…]} —— 换算链、交易日、张数对账列、份额列、计数列全算上。

    build 脚本用它做「该池的 CSV 齐不齐、列全不全」的门槛检查，
    照 exchanges.py 第 3 条规矩：缺就整池 skip 并打印原因，不抛异常。
    """
    out = {}

    def add(csv_name, col):
        if csv_name and col:
            out.setdefault(csv_name, set()).add(col)

    objs = [(p['denom']['csv'], p['denom'])] if p.get('denom') else []
    objs += [(m['csv'], m) for m in p['members']]
    for own_csv, obj in objs:
        for leg in (obj.get('chain') or []):
            leg_csv = leg.get('csv') or own_csv
            add(leg_csv, leg['col'])
            pd_spec = leg.get('per_day')
            if pd_spec:
                days_csv = pd_spec.get('csv') or leg_csv
                add(days_csv, pd_spec['col'])
                add(days_csv, pd_spec.get('div_col'))
        for c in (obj.get('contracts_col') or []):
            add(own_csv, c)
        # crosscheck_col 与 contracts_col 的区别：前者**不可与后者相加**（它是合计列或
        # 子集列），只用来做「分项之和 = 合计」这类解析自检。但它同样要进门槛检查 ——
        # 一个写错的自检列名会让那道自检静默跳过，而自检跳过是看不出来的。
        for c in (obj.get('crosscheck_col') or []):
            add(own_csv, c)
        add(own_csv, obj.get('share_col'))
        add(own_csv, obj.get('count_col'))
    return {k: sorted(v) for k, v in sorted(out.items())}


def selfreport_checks(p):
    """本池里可与官方自报份额对账的成员，吐 (成员, selfreport 声明) 二元组。

    **这是全仓唯一一处能把自算结果与外部数字逐位核的地方**，所以它必须是
    机械可执行的、而不是写在 note 里的一句话。对账式子：

        Σ 成员 contracts_col ÷ Σ denom contracts_col  ≈  自报列 × scale   (pp)

    两侧都是张数/股数口径 —— 官方自报的份额本来就是这么算的。名义额份额与它
    恒等（同一批合约、同一个基期常数，分子分母同乘一个数），所以核了张数口径
    就等于核了名义额口径，见各池 dual_note。

    容差 tol_pp 一律写实测值，不许拍脑袋：偏差的来源是官方自己的舍入
    （自报份额只给 3 位小数、成交量给到整数百万股或整数千张），
    容差定得比舍入下界还紧，就会每隔几年误报一次，而每隔几年假一次的警报，
    人很快就学会无视了（与 README 的红点是同一条道理）。
    """
    out = []
    if not p.get('denom'):
        return out
    for m in p['members']:
        if m.get('selfreport'):
            out.append((m, m['selfreport']))
    return out


def recon_cols(member):
    """对账列：与官方披露逐位核对时该看哪几列。**每个成员都必须有至少一列。**

    「与官方新闻稿逐位对账」是张数保留在 series/ 里的头号理由，所以张数原列优先；
    但不是每个成员都有张数：
      · 金额型成员（HKEX 的 ADT、Euronext 的 ADNV）—— 对账对象就是官方披露的那个金额；
      · 份额型成员（fn_monopoly 的四条）—— 对账对象是官方自报的那条份额序列本身，
        这恰恰是全仓最该被对账的一类数（它是唯一能与外部数字核的份额）；
      · 计数型成员（fn_listing 的新上市家数）—— 对账对象是家数列。
    一个对账列都给不出来的成员，等于这条线画出来之后没人能验证它对不对。
    """
    if member.get('contracts_col'):
        return list(member['contracts_col'])
    cols = [leg['col'] for leg in (member.get('chain') or [])]
    for k in ('share_col', 'count_col'):
        if member.get(k):
            cols.append(member[k])
    return cols


_MONTH_RE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')


def _check_chain(where, chain, own_csv, errs):
    for i, leg in enumerate(chain):
        tag = '%s 第 %d 条腿' % (where, i + 1)
        for k in ('col', 'src', 'unit_scale', 'product'):
            if k not in leg:
                errs.append('%s 缺字段 %r' % (tag, k))
        if 'src' in leg and leg['src'] not in SRC_KINDS:
            errs.append('%s src=%r 只能是 %s' % (tag, leg['src'], list(SRC_KINDS)))
        # unit_scale 恒为正：它是「这一列的写法」（千张 / 百万股），是数量级不是方向。
        # 想表达减法用 sign=-1 —— 两件事分开写，体检才拦得住「把负号藏进量纲」这种事。
        if 'unit_scale' in leg and not (isinstance(leg['unit_scale'], (int, float))
                                        and leg['unit_scale'] > 0):
            errs.append('%s unit_scale=%r 必须是正数（要减法请用 sign=-1）'
                        % (tag, leg['unit_scale']))
        sign = leg.get('sign', 1)
        if sign not in notional.LEG_SIGNS:
            errs.append('%s sign=%r 只能是 1 或 -1' % (tag, sign))
        if sign == -1:
            if i == 0:
                errs.append('%s 是第一条腿却 sign=-1 —— 一条链不能从减法开始，'
                            '被减的那个主列必须先在场' % tag)
            if not leg.get('why'):
                errs.append('%s 是减法腿却没写 why —— 减掉的是哪个被并购市场、'
                            '依据是哪份官方备注列，必须留在定义里' % tag)
            if not leg.get('since'):
                errs.append('%s 是减法腿却没写 since —— 备注列的含义随并表月份翻转，'
                            '不卡生效起点就会减掉一块当时还没并进主列的量，'
                            '结果是负的名义额' % tag)
            of_col = leg.get('of_col')
            if not of_col:
                errs.append('%s 是减法腿却没写 of_col —— 必须指明它修正的是哪条主列，'
                            '否则「备注列 ⊆ 主列」这条逐对护栏无从执行，'
                            '而只查整链合计漏得掉真实的口径错（同链别的腿会把它盖住）'
                            % tag)
            else:
                mate = [j for j, o in enumerate(chain)
                        if o.get('sign', 1) > 0 and o.get('col') == of_col]
                if not mate:
                    errs.append('%s 的 of_col=%r 在同一条链里没有对应的正腿'
                                % (tag, of_col))
                elif chain[mate[0]].get('product') != leg.get('product'):
                    errs.append('%s 与它的主列 %r 用了不同的 product —— '
                                '两者必须同一个基期常数，否则相减的是两个不同的东西'
                                % (tag, of_col))
        since = leg.get('since')
        if since is not None and not _MONTH_RE.match(str(since)):
            errs.append('%s since=%r 必须是 YYYY-MM' % (tag, since))
        pid = leg.get('product')
        if pid not in PRODUCTS:
            errs.append('%s 的 product=%r 不在 PRODUCTS 清单里' % (tag, pid))
        elif leg.get('src') in notional.SRC_TO_KIND:
            want = notional.SRC_TO_KIND[leg['src']]
            if PRODUCTS[pid]['kind'] != want:
                errs.append('%s src=%s 要求 kind=%s，但 PRODUCTS[%s].kind=%s'
                            % (tag, leg['src'], want, pid, PRODUCTS[pid]['kind']))
        if not (leg.get('csv') or own_csv):
            errs.append('%s 没有 csv，成员也没有默认 csv' % tag)
        pd_spec = leg.get('per_day')
        if pd_spec is not None:
            if not isinstance(pd_spec, dict) or 'col' not in pd_spec:
                errs.append('%s per_day 必须是 None 或 '
                            '{"col": …, "csv": 可选, "div_col": 可选}' % tag)
            elif pd_spec.get('div_col') == pd_spec['col']:
                errs.append('%s per_day 的 div_col 与 col 相同 —— 隐含日数会恒为 1' % tag)
    # 全是减法腿的链不可能有正的结果；这一条在有数据之前就能拦。
    if chain and all(leg.get('sign', 1) < 0 for leg in chain):
        errs.append('%s 整条链都是减法腿 —— 没有被减的主列，结果必为负' % where)


def validate():
    """池定义的自洽性体检。返回错误列表（空 = 全过）。

    这里查的都是「写错了在图上看不出来」的那一类：颜色撞车只会让两条线同色、
    head 里写了一个不存在的 key 只会让门槛静默失效、fx_only 与 base_price 混在
    一个池里只会让占比悄悄偏一点 —— 没有一个会自己报错。
    """
    errs = []
    # PRODUCTS 是「对规格表的需求清单」。清单里躺着没人用的产品 = 让填表的人白测一个数，
    # 而且下一个人会以为它有用而不敢删。
    unused = sorted(set(PRODUCTS) - set(products_used()))
    if unused:
        errs.append('PRODUCTS 里有没被任何池引用的产品：%s' % unused)

    seen_ids = set()
    for p in POOLS:
        pid = p['id']
        if pid in seen_ids:
            errs.append('池 id 重复：%s' % pid)
        seen_ids.add(pid)

        for k in ('zh', 'axis', 'page', 'unit_kind', 'unit', 'share', 'levels',
                  'basis', 'head', 'members'):
            if k not in p:
                errs.append('池 %s 缺字段 %r' % (pid, k))
        if p.get('unit_kind') not in UNIT_KINDS:
            errs.append('池 %s unit_kind=%r 只能是 %s'
                        % (pid, p.get('unit_kind'), list(UNIT_KINDS)))
        if p.get('deflator') not in DEFLATORS:
            errs.append('池 %s deflator=%r 只能是 %s'
                        % (pid, p.get('deflator'), list(DEFLATORS)))
        if p.get('flow') not in FLOWS:
            errs.append('池 %s flow=%r 只能是 %s' % (pid, p.get('flow'), list(FLOWS)))
        else:
            # flow 合法还不够，还得真能推出汇率档次 —— 这一跳断了整池画不出来，
            # 而 flow 字段本身看上去完全正常
            try:
                fx_basis(p)
            except notional.NotionalError as e:
                errs.append('池 %s 的 flow=%r 推不出汇率基准：%s'
                            % (pid, p.get('flow'), e))
        if p.get('share') not in SHARE_TIERS:
            errs.append('池 %s share=%r 只能是 %s'
                        % (pid, p.get('share'), list(SHARE_TIERS)))

        members = p.get('members') or []
        if not members:
            errs.append('池 %s 一个成员都没有' % pid)
        if len(members) > MAX_MEMBERS:
            errs.append('池 %s 有 %d 个成员，超过每池 ≤%d 家（6 个数据色 − 1 个残差色）'
                        % (pid, len(members), MAX_MEMBERS))

        keys, colors = set(), set()
        for m in members:
            # ⚠ `start` 是**惰性字段**：这里只校验它「在不在」，全仓没有任何地方拿它切数据
            #   （池子的起点由各列自己的首个非空月现算）。所以它写错不会让图错，
            #   只会让**注释与页面文案**说假话 —— 2026-08 那轮回补就让 tmx / ndaq / asx
            #   三处同时过期。改数据起点时记得回来同步它，或者干脆哪天把它改成现算。
            for k in ('key', 'disp', 'color', 'csv', 'start'):
                if k not in m:
                    errs.append('池 %s 的成员 %r 缺字段 %r' % (pid, m.get('key'), k))
            if m.get('key') in keys:
                errs.append('池 %s 成员 key 重复：%s' % (pid, m.get('key')))
            keys.add(m.get('key'))
            if m.get('color') not in PALETTE:
                errs.append('池 %s 成员 %s 的 color=%r 不在数据色板 %s 里'
                            '（RED 是断点与截轴离群值专用，不做数据色）'
                            % (pid, m.get('key'), m.get('color'), list(PALETTE)))
            if m.get('color') in colors:
                errs.append('池 %s 里 %s 这个颜色用了两次 —— 同池内颜色必须唯一'
                            % (pid, m.get('color')))
            colors.add(m.get('color'))
            if 'in_share' not in m:
                errs.append('池 %s 成员 %s 没写 in_share（进不进份额分子必须显式声明）'
                            % (pid, m.get('key')))
            if 'contracts_col' not in m:
                errs.append('池 %s 成员 %s 没写 contracts_col（张数对账列，无则写 []）'
                            % (pid, m.get('key')))
            cc = m.get('crosscheck_col')
            if cc is not None:
                if not isinstance(cc, list):
                    errs.append('池 %s 成员 %s 的 crosscheck_col 必须是 list'
                                % (pid, m.get('key')))
                else:
                    dup = sorted(set(cc) & set(m.get('contracts_col') or []))
                    if dup:
                        errs.append(
                            '池 %s 成员 %s 的 %s 同时出现在 contracts_col 与 '
                            'crosscheck_col —— 两张清单的语义相反：前者可相加、'
                            '后者是合计列或子集列，不可相加。同一列不能两边都算'
                            % (pid, m.get('key'), dup))

            # ── 张数口径成员：必须显式声明，且不许悄悄溜进名义额口径 ──────
            # 这个字段的存在本身就是要点：原先「ICE 利率画不出水平值」是靠
            # contract_specs.csv 里两个空格子**隐式**表达的，而空格子的含义是
            # 「还没测」——下一个人会去测，撞完 reCAPTCHA 再回来，然后发现
            # 就算测出来也不该用。把判断写在定义里，这段路才不用再走一遍。
            if m.get('contracts_only'):
                if not m.get('contracts_only_why'):
                    errs.append('池 %s 成员 %s 声明了 contracts_only 却没写 '
                                'contracts_only_why —— 「这条腿永远不进名义额口径」'
                                '是一个口径判断不是一个数据状态，理由必须写在定义里，'
                                '否则下一个人只会看到一个没解释的开关'
                                % (pid, m.get('key')))
                if m.get('in_share'):
                    errs.append('池 %s 成员 %s 同时是 contracts_only 与 in_share=True —— '
                                '张数口径的量进不了名义额份额的分子：分子分母的单位不同，'
                                '算出来的占比没有任何读法' % (pid, m.get('key')))
                if not m.get('contracts_col'):
                    errs.append('池 %s 成员 %s 是 contracts_only 却没有 contracts_col —— '
                                '张数原列就是它唯一能被读的东西，一列都没有等于这条腿'
                                '什么都画不出来' % (pid, m.get('key')))

            if p.get('unit_kind') == 'share_pp':
                if not m.get('share_col'):
                    errs.append('池 %s（share_pp）成员 %s 缺 share_col'
                                % (pid, m.get('key')))
                if m.get('chain'):
                    errs.append('池 %s（share_pp）成员 %s 不该有换算链 —— '
                                '份额是无量纲比值，乘常数没有意义'
                                % (pid, m.get('key')))
            else:
                if not m.get('chain'):
                    errs.append('池 %s 成员 %s 缺换算链 chain' % (pid, m.get('key')))
                else:
                    _check_chain('池 %s 成员 %s' % (pid, m.get('key')),
                                 m['chain'], m.get('csv'), errs)

        for h in (p.get('head') or []):
            if h not in keys:
                errs.append('池 %s 的 head 里有 %r，但它不是本池成员' % (pid, h))
        if not p.get('head'):
            errs.append('池 %s 没有 head —— 共同最新月与共同起点算不出来' % pid)

        # share 档次与分母的自洽
        if p.get('share') == 'true':
            if p.get('unit_kind') == 'notional' and not p.get('denom'):
                errs.append('池 %s 声明 share=true 却没有 denom —— '
                            '"真份额"的全部含义就是有一个官方披露的分母' % pid)
            if p.get('denom'):
                d = p['denom']
                for k in ('csv', 'chain', 'label', 'evidence'):
                    if not d.get(k):
                        errs.append('池 %s 的 denom 缺字段 %r' % (pid, k))
                if d.get('chain'):
                    _check_chain('池 %s 的 denom' % pid, d['chain'], d.get('csv'), errs)
        elif p.get('denom'):
            errs.append('池 %s 的 share=%s 却带了 denom —— '
                        '有分母就该是 true，没有就不该留一个半截的 denom'
                        % (pid, p.get('share')))

        if p.get('share') == 'pool' and not p.get('share_caveat'):
            errs.append('池 %s 是 share=pool 却没写 share_caveat —— '
                        '池内占比的图注必须点名分母是本池哪几家，这一条不许省' % pid)

        # ── 池一级：有张数口径成员就必须有给读者看的那句话 ──────────────
        co = contracts_only_members(p)
        if co and not p.get('contracts_only_note'):
            errs.append('池 %s 有张数口径成员（%s）却没写 contracts_only_note —— '
                        '成员的 contracts_only_why 是写给下一个改代码的人的，'
                        'contracts_only_note 是写给**看图的人**的：'
                        '「这条线为什么只在增长图里出现」必须落在页面上，'
                        '否则读者会以为那几张图漏画了一家'
                        % (pid, '、'.join(m.get('key') for m in co)))
        if co and p.get('share') in ('pool', 'true'):
            in_share = [m for m in members if m.get('in_share')]
            if len(in_share) < 2:
                errs.append('池 %s 去掉张数口径成员后只剩 %d 家进份额分子 —— '
                            '一家的"占比"恒等于 100%%，这张图不该画'
                            % (pid, len(in_share)))
        if co and len(co) == len(members):
            errs.append('池 %s 的成员全是张数口径 —— 那它就不是一个名义额池，'
                        'unit_kind 与 levels 都该重判，而不是留一个画不出水平值的壳'
                        % pid)
        if p.get('share') == 'none' and not p.get('why_none') and p.get('unit_kind') != 'share_pp':
            errs.append('池 %s 是 share=none 却没写 why_none —— '
                        '新口径把「单位不可比」这条理由消掉了，'
                        '还留在 none 的必须写清楚是别的什么理由' % pid)

        # dual_unit 只给有官方分母、且分母本身是张数/股数口径的池
        if p.get('dual_unit'):
            if p.get('share') != 'true':
                errs.append('池 %s dual_unit=True 但 share=%s —— '
                            '张数口径份额图的意义是与官方数字对账，'
                            '没有官方分母就没有可对账的对象'
                            % (pid, p.get('share')))
            if not p.get('dual_note'):
                errs.append('池 %s dual_unit=True 却没写 dual_note' % pid)
            # dual_unit 的全部意义就是"能与官方数字对账"，一个可对账的成员都没有
            # 就说明这个开关是空头支票
            if not selfreport_checks(p):
                errs.append('池 %s dual_unit=True 却没有任何成员声明 selfreport —— '
                            '张数口径份额图的意义是与官方自报份额逐位核，'
                            '没有可核的对象就不该开这个开关' % pid)
            if not p.get('recon_note'):
                errs.append('池 %s dual_unit=True 却没写 recon_note（容差怎么定的）'
                            % pid)
            # ── dual_note 承诺的恒等式，机器检一遍 ────────────────────────
            # dual_note 写的是「名义额份额 ≡ 张数份额」。这条恒等**不是普遍成立的**，
            # 它只在一种情况下成立：分子与分母的每一条腿都解析到**同一个 product_id**，
            # 于是同一个基期常数在分子分母上下相约。
            # 只要有一个成员换了产品（比如把 TMX 的加元股票混进美国现货池，
            # 或者分母用了含指数期权的篮子而成员用纯 multilist），
            # 两个口径的份额就会差一个常数比，而图上两条线都很"正常"，
            # 唯一的症状是与官方自报份额对不上 —— 而那时人会先去怀疑抓取。
            d = p.get('denom')
            if d and d.get('chain'):
                dprod = {leg['product'] for leg in d['chain']}
                mprod = {leg['product']
                         for m in members if m.get('in_share')
                         for leg in (m.get('chain') or [])}
                both = dprod | mprod
                if len(both) != 1:
                    errs.append(
                        '池 %s dual_unit=True 但分母与 in_share 成员没有解析到同一个 '
                        'product：分母 %s / 成员 %s。dual_note 承诺的「名义额份额 ≡ '
                        '张数份额」只在两侧共用同一个基期常数时成立，'
                        '产品不同一 ⇒ 那句话是错的，张数份额图也就不再是对账通道'
                        % (pid, sorted(dprod), sorted(mprod)))

        for m in p['members']:
            sr = m.get('selfreport')
            if not sr:
                continue
            if not p.get('denom'):
                errs.append('池 %s 成员 %s 声明了 selfreport，但本池没有 denom —— '
                            '没有分母就算不出可对账的份额' % (pid, m.get('key')))
            for k in ('col', 'scale', 'tol_pp', 'evidence'):
                if sr.get(k) in (None, ''):
                    errs.append('池 %s 成员 %s 的 selfreport 缺字段 %r'
                                % (pid, m.get('key'), k))
            if not m.get('contracts_col'):
                errs.append('池 %s 成员 %s 要与自报份额对账，却没有张数/股数原列'
                            % (pid, m.get('key')))
            tol = sr.get('tol_pp')
            if isinstance(tol, (int, float)) and not (0 < tol <= 1.0):
                errs.append('池 %s 成员 %s 的 tol_pp=%r 不合理 —— '
                            '份额对账的容差应当是零点几个 pp 的量级'
                            % (pid, m.get('key'), tol))

        # 价格基准不许在一个池里混
        if p.get('unit_kind') == 'notional':
            srcs = {leg['src'] for _l, _c, ch in chains_of(p) for leg in ch}
            mixed = ('notional' in srcs) and bool(srcs - {'notional'})
            if mixed:
                errs.append(
                    '池 %s 混了金额型（notional）与数量型（contracts/shares）源列：%s。'
                    '前者只能锁汇率、价格是当期，后者是完全定基 —— '
                    '两种基准放进同一个分母，占比是假的' % (pid, sorted(srcs)))
            want = 'fx_only' if srcs == {'notional'} else 'base_price'
            if p.get('deflator') != want and not mixed:
                errs.append('池 %s 的源列全是 %s，deflator 应当是 %r，实际写的是 %r'
                            % (pid, sorted(srcs), want, p.get('deflator')))
    return errs


def missing_csvs(series_dir=SERIES, pools=None):
    """哪些 series/*.csv 还没建。分批上线时用它决定整页 skip。"""
    return [c for c in csvs_used(pools)
            if not os.path.exists(os.path.join(series_dir, c))]


def column_demands(pools=None):
    """POOLS 对每张 series/*.csv 提出的**全部**列名需求：{csv: [列名…]}。

    这是本文件对 fetch 侧的完整需求清单。它必须能在表还没建的时候就打印出来 ——
    见 check_columns() 的说明。
    """
    want = {}
    for p in (pools if pools is not None else POOLS):
        for c, cols in cols_used(p).items():
            want.setdefault(c, set()).update(cols)
    return {k: sorted(v) for k, v in sorted(want.items())}


def check_columns(series_dir=SERIES):
    """对 series/*.csv 逐列核对 POOLS 声明的列名是否真的在表头里。

    返回 (已核对的 (csv, 列) 数, [错误串…], {缺表: [该表被引用的全部列名…]})。

    ⚠ **第三个返回值从「表名清单」改成了「表名 → 列名需求」，这是本次重写的核心之一。**
    老版本把「CSV 还没建」记成一个光秃秃的表名、并且不算错，于是：本文件为 8 张
    尚不存在的表凭空发明了三十多个列名，测试却一路全绿 —— 绿灯在说谎。
    第一张真表（enx.csv）一落地，命中率 0/3。

    表没建当然不该判失败（分批上线是正常状态），但**必须把这张表被要求的每一个列名
    都打出来**：那是唯一能在表落地之前发现"名字是编的"的机会 ——
    有人拿这份清单去对官方报表，就能当场看出 adv_index_deriv_kcontracts 根本不存在。
    调用方（test_pools.py / build 脚本）拿到非空的缺表字典时，必须以
    SKIPPED-WITH-WARNING 收尾，不许静默 PASS。
    """
    import csv as _csv
    want = column_demands()
    checked, errs, missing = 0, [], {}
    for name in sorted(want):
        path = os.path.join(series_dir, name)
        if not os.path.exists(path):
            missing[name] = list(want[name])
            continue
        with open(path, newline='', encoding='utf-8') as f:
            header = set(next(_csv.reader(f)))
        for col in sorted(want[name]):
            checked += 1
            if col not in header:
                errs.append('series/%s 没有列 %r（POOLS 里引用了它）' % (name, col))
    return checked, errs, missing


def format_missing_demands(missing):
    """把 check_columns 的缺表字典排成可读的多行文本。测试与 __main__ 共用一份。"""
    lines = []
    for name in sorted(missing):
        cols = missing[name]
        lines.append('  series/%s 还没建 —— POOLS 对它提出 %d 个列名需求：'
                     % (name, len(cols)))
        for c in cols:
            lines.append('      · ' + c)
    return '\n'.join(lines)


def summary_rows():
    """一行一个池的体检摘要，给 __main__ 与测试用。"""
    rows = []
    for p in POOLS:
        rows.append({
            'id': p['id'], 'zh': p['zh'], 'page': p['page'],
            'share': p['share'], 'levels': p['levels'],
            'dual': bool(p.get('dual_unit')),
            'unit_kind': p['unit_kind'], 'deflator': p['deflator'],
            'flow': p['flow'], 'fx': fx_basis(p),
            'n_members': len(p['members']),
            'n_in_share': sum(1 for m in p['members'] if m.get('in_share')),
            'n_products': len({leg['product']
                               for _l, _c, ch in chains_of(p) for leg in ch}),
        })
    return rows


if __name__ == '__main__':
    errs = validate()
    print('POOLS: %d 个池 / %d 个成员位 / %d 个 product_id'
          % (len(POOLS), sum(len(p['members']) for p in POOLS),
             len(products_used())))
    print('PRODUCTS 清单: %d 个（contract_specs.csv 必须逐个填齐）' % len(PRODUCTS))
    print('validate(): %s' % ('全过' if not errs else '%d 处错误' % len(errs)))
    for e in errs:
        print('  ✗ ' + e)

    print('\n%-22s %-18s %-6s %-6s %-5s %-11s %-10s %-4s %-4s %-4s' %
          ('池', '页', 'share', 'levels', 'dual', 'deflator', 'flow', 'fx',
           '成员', '产品'))
    print('-' * 108)
    for r in summary_rows():
        print('%-22s %-18s %-6s %-6s %-5s %-11s %-10s %-4s %-4d %-4d'
              % (r['id'], r['page'], r['share'], str(r['levels']), str(r['dual']),
                 str(r['deflator']), r['flow'], r['fx'],
                 r['n_members'], r['n_products']))

    n, cerrs, missing = check_columns()
    print('\n列名核对：已建 CSV 里核了 %d 个 (表,列)，%d 处对不上；%d 张表还没建'
          % (n, len(cerrs), len(missing)))
    for e in cerrs:
        print('  ✗ ' + e)
    if missing:
        # 缺表不判失败，但要把需求全打出来 —— 见 check_columns 的 docstring
        print(format_missing_demands(missing))
        print('  ⚠ SKIPPED-WITH-WARNING：上面这些列名**一个都没有被真实表头验证过**，'
              '不要当成已核对')

    try:
        specs = notional.load_specs(SERIES)
        # 用 products_needing_specs 而不是 products_used：张数口径产品的空常数
        # 是**终局状态**，混进"待实测"清单里会让人一次次回去撞同一堵墙。
        todo = notional.pending_products(products_needing_specs(), specs)
        frozen = contracts_only_products()
        print('\n规格表：%d 个产品已入库，%d 个待实测' % (len(specs), len(todo)))
        for pid, why in todo:
            print('  · %s —— %s' % (pid, why))
        if frozen:
            print('  ⛔ 永久张数口径（**不是待办**，基期常数永远留空）：%s'
                  % '、'.join(frozen))
            for p in POOLS:
                for m in contracts_only_members(p):
                    print('     · %s.%s —— %s'
                          % (p['id'], m['key'],
                             m['contracts_only_why'].split('\n')[0]))
    except notional.NotionalError as e:
        print('\n规格表：%s' % e)
