# -*- coding: utf-8 -*-
"""欧洲现货股票竞争页（Euronext / Deutsche Börse (Xetra+FWB) / Cboe Europe）
→ 写出 data/exchanges-eu.js。

本页是从旧的欧亚合页（`exchanges-intl`，其生成器 build/exchanges_intl.py 已于
2026-08-06 随该页一并删除）里把欧洲那一半拆出来单独成页。拆的理由不是版面，是**口径**：
欧洲三家争的是同一批股票的同一笔订单流（MiFID II 之下任何欧洲股票可以在任何场所交易），
所以「占比」这个词在这里是有内容的；而亚太四家是法域隔离的市场，几乎零替代性，
把它们的量加起来当分母只是我们自己圈了一个集合，占比没有任何外部指涉
—— 那一半改画增长与产品级头对头，不在本页。

━━━━━━━━━━━━━━ 一、本页最要紧的一件事：分母到底有没有 ━━━━━━━━━━━━━━
**结论：没有拿到，因此本页的占比是 `share='pool'`（分母 = 本池三家之和），
不是市场份额。**「市场份额」四个字在本页任何一处都不出现。

**分母 = 本池三家 lit + 自有暗池的披露口径之和，不含 SI（系统内部撮合商）、
不含第三方暗池与 OTC，也不含本池之外的场所（LSEG / Turquoise / Aquis / SIX 等）。
因此本页的占比系统性高估这三家在真实泛欧成交里的比重。**

查过的四条路，逐条写明为什么拿不到（都是本轮实际打开页面确认的，不是回忆）：

1. **FESE European Equity Market Report（EEMR）** — https://www.fese.eu/statistics/european-equity-market-report/
   实测：当期是 "EEMR 06/2026"，2014–2025 历年 xlsx 存档公开可下，**不要登录**。
   看上去最接近，但两处不成立：(a) 页面对口径只写了一句
   "provides equity trading figures from all major European trading venues"，
   真正的口径定义在另挂的 FESE Methodology PDF 里，页面正文抓不到 —— 即**范围未经证实**；
   (b) FESE 是**会员制交易所联合会**，统计口径是会员场所的成交，
   结构上就不含 SI 与非会员场所的 OTC/暗池。⇒ 就算把文件抓下来，
   它也不是「含 SI 与暗池的泛欧合并量」，只是另一个（更大的）成员集合之和。
   📌 未做：本轮没有下载 EEMR 文件逐列实测（仓库规矩是没实测的数字不许写），
   所以本页**没有引用它的任何一个数字**。要用它必须先建 fetch/fese.py 与 series/fese.csv。

2. **Cboe Europe Market Share（自家发布的泛欧市占）** — https://www.cboe.com/europe/equities/market_share/market/venue/
   实测：是一个前端渲染的透视表，数据**延迟至少 15 分钟**，按 venue / 市场 / 指数切片；
   页面自己写着「Cboe Europe does not track primary exchange volumes for markets
   marked with an asterisk」—— 即**它自己的分母就不全**。
   user_guide 页只讲怎么用界面，一个字没写覆盖范围（是否含 SI、含哪些暗池）。
   没有文档化的 CSV/API 端点。⇒ 一个由竞争对手维护、覆盖范围未文档化、
   自承有缺口的分母，不能拿来当本页的权威分母。

3. **big xyt（Liquidity Cockpit）** — 商业订阅产品。它确实是市场公认的
   「含 SI 与暗池的可寻址流动性」口径提供方，但**要钱、要合同**，
   公开渠道只有博客与新闻稿里的零星读数（例如媒体引用的欧洲日均约 €93bn），
   没有可无人值守抓取的月度序列。⇒ 与本仓「数据全部来自公司官网 IR 或监管申报的
   原始披露」这条硬约束也不相容。

4. **ESMA** — 实测：ESMA 公开的是**年度**透明度计算（每只证券的 ADT，用于定
   LIS 门槛）与暗池双重成交量上限（DVC）的逐月逐券数据，
   **没有**按场所汇总的月度成交额序列。更根本的一条：MiFIR 要求的
   **股票合并信息带（consolidated tape provider）到本轮为止还没有开始发布**
   —— ESMA 2026-04 还在就欧洲股票市场结构发 Call for Evidence。
   ⇒ 「官方泛欧合并量」这个东西在制度上目前还不存在，不是我们没找到。

**所以本页老实降级到 share='pool'，并在每一张占比图的图注里写死分母是谁。**
分母一旦有了（合并信息带上线、或 FESE/big xyt 的序列真的入库到 series/），
本页的占比图可以原地换分母，图型一张都不用改。

━━━━━━━━━━━━━━ 二、三家的口径差异（本页第二要紧的事）━━━━━━━━━━━━━━
| 成员 | 源列 | 口径 |
|------|------|------|
| Euronext | `adv_cash_equities_adnv_eurbn` | €bn/日 ADNV，**股票与投资基金**，单边计，2012-01 起 |
| Cboe Europe | `adv_eu_equities_adnv_eurbn` | €bn/日 ADNV，泛欧股票，单边计，2017-01 起 |
| Deutsche Börse | `turnover_cash_total_eurbn` ÷ `trading_days_cash` | Xetra + Börse Frankfurt 场内，**含 ETP / 结构化产品 / 债券 / 基金**，2010-01 起 |

前两条逐字同口径。第三条**更宽**，这是本页最大的一处妥协，理由与代价都实测过：

· 只有 `turnover_cash_total_eurbn` 有深度历史（**199 个月，2010-01 起**，2026-08-19 实测）。
  与前两家逐字同口径的窄口径列**没那么深，而且两条列自己还不一样长**（2026-08-18 回补后
  的现值，2026-08-19 重测；此处原写「只有 19 个月（2024-12 起）」，那是回补前的数）：
      turnover_xetra_equities_eurbn   2016-06 起，107 个月
      turnover_fwb_equities_eurbn     2016-06 起，**62** 个月
      两条同时有值（本页 DB1_NARROW 要的就是这个交集）  2016-06 起，**62** 个月
  62 个月比 19 个月好得多，但仍然远短于宽口径的 199 个月 —— 用窄口径，本页的长历史
  份额图会从 2010-01 缩到 2016-06，用户明确要的「季度口径、十年或更长」还是拿不到。
  ⇒ **妥协的结论没变，只是代价小了一些。** 哪天要重新权衡，先跑一次上面三行现算。
· 代价是可以**量出来**的，不是估的：重叠月里
  宽口径 ÷ 窄口径（Xetra 股票 + FWB 股票）的比值实测区间与中位数由运行时算出，
  折成池内占比，Deutsche Börse 被高估的幅度同样由运行时逐月算出并印在 Exhibit 12 的图注里。
  ⇒ **本页 Deutsche Börse 的占比是它的上界**，Euronext 与 Cboe 的占比是各自的下界。
  这句话写进图注、写进页脚，不藏在注释里。

━━━━━━━━━━━━━━ 三、Nasdaq 北欧：进图，但绝不进份额分子 ━━━━━━━━━━━━━━
Nasdaq 自报的「欧洲现货市占」（`series/ndaq_q.csv` 的 `q_share_nordic_cash`，
写这段时最新一季实测 74.5%；页面上的数字由运行时重算，不写死）
是**北欧+波罗的海**口径 —— NDAQ 2026Q1 8-K EX-99.1 脚注 7 原文：
"European cash equities markets include cash equities exchanges of Sweden, Denmark,
Finland, and Iceland"（转录见 fetch/ndaq.py 口径坑 1）。
而 Cboe Europe 的份额是泛欧口径。两者的分母是两个不同的宇宙：
把 74.5% 与 Cboe 的两成多并排画，读者会得出「Nasdaq 是 Cboe 的三倍」这个**完全反的**结论。
本页 Exhibit 10 把这件事画成算术：Nasdaq 自报份额反推出来的整个「欧洲市场」分母，
比 Cboe Europe **一家**的成交额还小 —— 具体倍数由运行时算出。

⇒ Nasdaq 北欧只出现在 **Exhibit 9（绝对值对比）** 与 **Exhibit 10（分母对撞）**，
   **不进任何一个份额的分子或分母**。
   另外它官方只发**当月合计**且**不给北欧交易日**（fetch/ndaq.py 口径坑 2），
   所以 Exhibit 9 一律用「€bn/月」而不是日均 —— 硬转 ADV 需要一个我们没有的日历。

━━━━━━━━━━━━━━ 四、口径断点：读 series/enx_breaks.csv，不写死月份 ━━━━━━━━━━━━━━
Euronext 现货列 `adv_cash_equities_adnv_eurbn` 的断点由 CSV 驱动。
⚠ 口传里的「2019 年并入 Oslo Børs」指的是**股指衍生品**列（官方脚注 since July 2019）；
**现货列的 Oslo 断点在 2018-01**。以 enx_breaks.csv 为准，不照抄口传。
2025-11 的 Athens 并表有官方备注列，可以**定量还原**（Exhibit 11）；
2021-05 的 Borsa Italiana 没有备注列，只能标不能还原。
RED 是断点与截轴离群值的专用色，不做数据色。

━━━━━━━━━━━━━━ 五、汇率 ━━━━━━━━━━━━━━
三家全部以 **EUR** 披露 ⇒ **池内占比里一点汇率都没有**，这是本页相对全仓其它横截面页
的一个结构性优势。定基名义额（锁 2019-01 月均 EUR/USD）只在把水平值折成美元时才起作用，
它与当期汇率口径的差**恒等于** EUR/USD 的累计变动 —— Exhibit 8 把这条恒等式画出来自检。

━━━━━━━━━━━━━━ 六、同比口径：本页的同比一律是「单月同比」，滚动口径一条线都不画 ━━━━━━━━━━━━━━
⚠ **2026-09 本页换过一次口径，这一节整段重写过。** 换之前，本页所有趋势读数用的是
12 个月滚动合计同比，单月同比被降级成一张「展示噪音」的矩阵；换之后正好反过来。
下面第一句是**换的理由**，别把它读成从数据里推出来的结论：

> **页面所有者要求全站的同比折线一律改成直接的单月同比（当月 ÷ 去年同月 − 1）。**

这是一条指令，是一件可以去核对的事实。`build/CONTRACT.md` §6 抬头引了原话，
§6.1 第 3 条要求**每一张画流量同比的图都把单月口径的代价印出来、用这条序列自己实测**
（该条自己把范围限定在流量 —— 本页画同比的都是流量），
并**明令禁止**替口径辩护（既不许写「看着更灵敏」，也不许写「滚动口径更好但我们没用」
—— 后者是替页面上不存在的东西背书）。所以本页写的是这条指令加上代价，一个字不辩护。
本页**不在 §6.2 那份例外名单里**（名单上是 `exchanges-apac` 的 Ex5 与 Ex15、
`exchanges12` 的 Ex4/7/8，五张全不是折线），所以这里一条滚动线都不许画。

**本轮改了哪几处**（口径变了，标题 / 轴名 / 序列名 / 图注一起改，只改数不改名比不改更糟）：
· **Exhibit 14** 四条趋势线：12 个月滚动合计同比 → 单月同比；
· **成交笔数图（HAS_VP 时是 Exhibit 16）** 的右轴线：同上，且换完之后那条线正好是
  **柱自己的同比**（§6.1 第 1 条要的那个「读者能自己核对」），实测线与「柱除以 12 根柱
  之前那根」逐点相等；
· **汇总表的同比那一组行**（原「12 个月滚动合计同比」组）与**抬头的 y/y**：一并换成
  单月。抬头是全页曝光最高的一行，上面写滚动、下面画单月，正是 CONTRACT §6 抬头那条
  审计发现说的自相矛盾。姊妹页 `exchanges-apac` 的汇总表本轮也是这个结构。

**没跟着改的**：
1. **Exhibit 13 的热力矩阵**本来就是单月同比（§6.3 的图型豁免：每一格就是一个月），
   口径一格没动。本轮改的是它周围那些话 —— 上一轮写的「本页唯一一处单月同比 /
   留着当反面教材」在 Exhibit 14 换口径的当天就成了假话，标题、图例、`src_extra`、
   图注逐处改写。它与 Exhibit 14 现在是**同一条序列的两种画法**，
   最近 24 个月里逐格的数与那条线**完全相同**（代码里有逐点相等的断言，
   不等就停止生成）。
2. **汇总表的「本月 vs 上月」「本月 vs 去年同月」两列**是那一行**自己展示的三个读数
   之间的算术**（表头已从 m/m / y/y 改成中文全称），§6.3 同样豁免。换完口径之后，
   成交额那一组行的「本月 vs 去年同月」与同比那一组行、与 Exhibit 13 / 14
   **是同一个数**；那一列只印最新一个月，同比那一组行还带上月 / 去年同月与 3Y %ile。
3. **成交额分解图的年度分解端点仍是 12 个月合计** —— 那是「一年对一年」，横轴是年，
   不是这里说的任何一种月度同比。

**滚动口径在本页还剩什么**：只剩图注里的**数字**。`MON_FULL` / `YOY12` 保留，
用途只有两个 —— 出图注里那组「当期对照」读数（建在月度成交额链上，与占比、季度图同源，
代码里有逐点相等的断言），以及让口径诊断有个对照面。**页上没有任何一条线画它。**

**代价必须写明，且由本页自己的序列实测**（数字全部由运行时算，一个都不写死；
统计量出自 `build/yoy.py` 的 `caliber_diff()`，它第一步就把两种口径的样本取交集对齐）：
· 单月同比的逐月标准差是 12 个月滚动同比的 1.3–1.7 倍；
· 相邻月跳变中位相差数倍，单月口径最大跳变实测数十个 pp（2020-04 那一档最大）；
· **符号相反**：三家各有近三成的月份两种口径一正一负，剔掉并表断点污染的月份后仍成立。
  ⇒ 拿单月同比读「谁在增长」，有近三成的月份会读出与滚动口径相反的方向。
· 换回来的两件事同样只是算术：一次并表断点只污染 **12 个**读数（滚动口径污染 24 个），
  窗口左端也不再有 24 个月画不出线。

⚠ **成交额的单月同比建在日均（ADV）上，不建在月度合计上**（CONTRACT §6.4：日均序列
不要乘回交易日，这一条在单月口径下更强）。滚动口径 12 个月一滚，日历差基本自抵；
单月口径里交易日数**不会**自己约掉，实测这一块最大能到二十个 pp 上下。
唯一的例外是成交笔数图的右轴线 —— 它建在**当月合计**笔数上，为的是满足 §6.1 第 1 条
「拿这根柱除以 12 根柱之前那根，就是线上这一点」；换成日均口径线就不再是这些柱的同比，
而图上完全看不出来。这条例外带进来的日历效应有多大，在那张图的图注里单量了一遍。

⚠ **不调 `yoy.describe()` 出图注文案，只取 `caliber_diff()` 的统计量、措辞本文件自己写。**
理由不是它写错了（它 2026-09 已经跟着改口径改过末句），是它按**一条序列**出一段话，
而本页要在同一段里覆盖三家 + 池合计四条线 —— 逐条各印一段会把图注撑成四倍，
所以这里出的是四条的**区间**（标准差倍数 1.28–1.69 之类）。措辞逐句对着
`build/single.py` 的 `mom_cost_zh()`（§6.1 第 3 条点名的两个底座之一）写，
要报的三样一样不少：逐月标准差、相邻月最大跳变（带月份）、符号相反的月份数。

━━━━━━━ 七、成交额分解：三家里只有 Euronext 有数据条件，且**不是量价分解** ━━━━━━━
⚠ **先把名字摆正。** 本页做的是 **成交额 = 成交笔数 × 每笔均值** 的分解，
**不是「股数 × 均价」**。第二项是每笔平均成交额，它主要反映**订单碎片化程度**
（一张单子多大），与市场涨跌只有间接关系 —— 把它叫「价」是错的，页面上一处都不这么叫。
真正的量价分解需要成交股数列，本页三家一列都没有。

恒等式 **成交额 ≡ 笔数 × 每笔均值** 是定义式，做分解不需要任何假设，
但**前提是分子分母同口径**。逐家扫过 series 里全部与现货相关、且不是金额/费率/家数的列
（扫描逻辑在 `cash_qty_candidates()`，结论由运行时打印，不是回忆）：

| 成员 | 现货数量列 | 判定 |
|------|-----------|------|
| Euronext | `adv_cash_trades_k`（日均成交笔数，千笔） | ✅ 可做（但只到「笔数 × 每笔均值」） |
| Cboe Europe | 只有 `adv_us_equities_matched_shares_bn`（**美国**撮合股数） | ❌ 与本页用的泛欧 ADNV 不同覆盖范围 |
| Deutsche Börse | **一列都没有**（现货侧 11 列全是 `turnover_*_eurbn`） | ❌ 缺的是列，不是口径 |

📌 **Cboe Europe 与 Deutsche Börse 不具备成交额分解的数据条件**，本页不为它们画这两张图，
也**不拿别人的数量列去凑**（拿 Cboe 的美国股数去除欧洲成交额，会造出一个方向和大小
都不可知的「均值」，而图上完全看不出来）。

Euronext 这一对的四条核对，逐条实测、逐条有机器判据：
1. **同一业务**：两列同出官方月报 Equity Markets 表的现货区块，
   `Total Turnover`(C6) 与 `Total number of trades`(C4)，同除 `Nb of trading days`(C3)。
2. **同一覆盖范围**：`series/enx_breaks.csv` 里两列的并表断点集合**逐个相同**
   （2017-01 Dublin / 2018-01 Oslo / 2021-05 Borsa Italiana / 2025-11 Athens），
   官方脚注也是同一句。代码里对这个集合做**相等断言**，哪天官方只对其中一列加断点，
   这两张图会自动停掉而不是继续画一个错的分解。
3. **⚠ 两种计数惯例 ⇒ 绝对水平不可读，本页一个都不印。**
   官方同一张表里金额列在 `Trading volume (single counted)` 分组下、
   笔数列在 `Transactions (buy and sell)` 分组下（`docs/verify/enx.md` 口径坑 6）。
   两者相除得到的**不是**每笔真实成交额，而是它除以一个计数因子；
   这个因子按定义应当是 2，但我们**没有独立证据**去确证（外部对账值本轮没有可无人值守
   核实的来源），所以本页**不去猜它**，也**不印任何每笔均值的绝对数**。
4. **但增长分解仍然成立，前提是「计数惯例逐月稳定」—— 这一条已经验过，不是假设。**
   两道检验：
   (a) **常数不变性**：分解对笔数列乘任何常数完全不变。代码拿 ×2、×0.5、×1.234567
       各算一遍，贡献值必须逐列相等（差 > 1e-9 抛异常）。
   (b) **惯例没有中途翻转**：若某月从单边翻成双边，每笔均值会在那一个月跳约
       ln2 ≈ 69.3%。逐月算 |Δln(每笔均值)|、排除并表断点月，看有没有月份接近 ln2。
       写这段时实测：165 个非断点月里最大单月跳变 21.1%（2020-03，COVID），
       **没有任何一个月落在 ln2 附近**；四个断点月自身的跳变也只有 3%–9%。
       判据写进代码（超过 ln2/2 就整块停画并写明原因），不是一次性的手工核对。

⚠ **口径代价必须写明**：与笔数同口径的金额列是 `adv_cash_adnv_eurbn`（**全部现货**：
股票与投资基金 + ETF + 结构化产品），比本页头条用的 `adv_cash_equities_adnv_eurbn`
（只有股票与投资基金）**宽**，实测比值区间由运行时算出并印在图注里。
分解图用宽列是因为窄列没有配对的笔数列 —— 宁可换一条自洽的序列，也不拿不同口径的
分子分母去凑一个均值。

⚠ **分解口径：用对数（LMDI），不用算术。** 算术那一路剩一个交叉项 Δn·Δm，
本页实测它占 ΔV 的中位数只有几个百分点，但 2020 年那种「笔数暴涨、均值暴跌、
两头几乎对冲」的年份能占到六成 —— 塞进任一侧都是任意分配，单独画成第三根读者读不懂。
对数分解无余项、任何年份都不失效。算术分解照样算，两路的差写进图注。
代价：对数增长率 ≠ 简单百分比（翻倍在对数里是 +69.3%），菱形是对数总增长，
简单百分比另在图注给出。

⚠ **端点一律用 12 个月合计，不用点对点单月。** 理由是这张图自己的：横轴是**年**，
问的是「这一年比上一年多出来的成交额里，多少来自笔数、多少来自每笔均值」，
拿单月当端点等于让一个异常月替一整年发言。**这条与第六节不再是同一个理由** ——
第六节那边（Exhibit 13 / 14 与成交笔数图的右轴）2026-09 起画的正是单月读数，
两者问的不是同一个问题。完整自然年天然满足；末尾再补一列 TTM（截至共同最新月的
12 个月 vs 前 12 个月），否则最新读数会比页面其余部分旧上最多 11 个月。

2020 那一列最能说明「这不是价格」（写这段时实测对数口径：笔数 +46.0%、每笔均值 −26.2%，
页面数字由运行时重算）—— 那不是「价格跌了四分之一」，是订单被切碎了。

数据源（只读 series/*.csv）：
  series/enx.csv        Euronext 月度 ADNV + 交易日 + Athens 备注列
  series/db1.csv        Deutsche Börse 月度现货成交额（三个口径）+ 交易日
  series/cboe.csv       Cboe Europe 泛欧股票 ADNV
  series/ndaq.csv       Nasdaq 北欧现货月度总额（US$bn）—— 只做绝对值对照
  series/ndaq_q.csv     Nasdaq 季度自报北欧市占 —— 只做分母对撞
  series/enx_breaks.csv Euronext 官方并表脚注的机器可读副本
  series/fx.csv         ECB 月均 / 月末汇率
  series/contract_specs.csv  只用来与本文件的换算公式对账

用法: python3 build/exchanges_eu.py    （可重复跑，除首行构建日期外逐字节相同）
"""
import csv
import os
import sys

import numpy as np
import pandas as pd

import axisfmt
import glossary as gloss   # 名词释义的版式层与护栏，全站共用
import payload_guard
import pctile        # 3Y %ile 的唯一实现，全站共用
import yoy           # 同比的唯一实现（单月 / 滚动 / 口径诊断），全站共用

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
# 目录名 = data 文件名 = payload 的 ticker，三者必须逐字相同（理由同 build/exchanges_na.py）：
# 模块名只能用下划线，输出物必须用连字符 —— 页面壳引的是 `../data/exchanges-eu.js`。
OUT = os.path.join(ROOT, 'data', 'exchanges-eu.js')

TICKER = 'exchanges-eu'
SRC = ('Source: Euronext, Deutsche Börse, Cboe Europe monthly volume disclosures; '
       'Nasdaq IR monthly/quarterly reporting sheet (Nordic, reference only); '
       'FX from ECB SDMX; format after Goldman Sachs GIR')

BASE_MONTH = '2019-01'   # 全仓基期，与 build/notional.py 的 BASE_MONTH 一致（加载时校验）
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
MIN_COMMON = 36          # 共同历史短于 36 个月不发（同比 + 年度占比 + 季度图都要）
MIN_QUARTERS = 12        # 季度长历史图至少要这么多个完整季，否则这张图不画
HEAT_MONTHS = 24         # y/y 矩阵的列数
YOY_YEARS = 4            # 同比同月份额图的年份数（grouped_bars 上限 4 组，第 5 组开始撞色）
# 开 end_label 的长历史线图的最小高度。理由见 docs/CHART_KINDS.md §3.9（绘图区 <308px 时
# 末点标签会收成一摞贴右上角，读数安到别的线上）。⚠ 原注写的是「见 build/exchanges.py 同名
# 常量」—— 那个文件在 e3c6f81「删除 /exchanges/ 三家横截面页」里已经删了，全仓不存在。
LINE_H_ENDLABEL = 360
TBL_MONTHS = 13


def mlab(p):
    """Period('2026-06') → 'Jun-26'。"""
    return f'{MONTHS[p.month - 1]}-{p.year % 100:02d}'


def qlab(q):
    """Period('2026Q2', 'Q') → '2Q26'。"""
    return f'{q.quarter}Q{q.year % 100:02d}'


def zh(p):
    return f'{p.year} 年 {p.month} 月'


def _z(v, dec):
    """把 -0.0 这类「四舍五入后其实是零」的值归零，否则会印出 '-0.0pp'。"""
    v = round(float(v), dec)
    return 0.0 if v == 0 else v


def ok(v):
    try:
        return v is not None and np.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def num(v, dec=0):
    return f'{float(v):,.{dec}f}' if ok(v) else '—'


def pct(v, dec=1):
    return f'{_z(v, dec):+,.{dec}f}%' if ok(v) else '—'


def pp(v, dec=1):
    """比率类指标的差异一律 pp/bp（契约 §2：绝对值不足 1pp 时写 bp）。"""
    if not ok(v):
        return '—'
    if abs(_z(v, dec)) < 1:
        return f'{_z(v * 100, 0):+,.0f}bp'
    return f'{_z(v, dec):+.{dec}f}pp'


def L(a):
    """序列 → JSON 安全的 float 列表（NaN → None，线在缺口处断开而不是直连）。"""
    return [None if not ok(v) else round(float(v), 6) for v in a]


def nice_max(v):
    """给右轴上界取一个整数刻度（stacked_dual 的右轴强制 0 起，只能调上界）。"""
    if not ok(v) or v <= 0:
        return 1
    step = 10 ** int(np.floor(np.log10(v)))
    for k in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0):
        if v <= k * step:
            return int(k * step) if k * step >= 1 else k * step
    return int(10 * step)


def skip(msg):
    """成员没齐 —— 打印原因，**退出码 0**。横截面页只在成员齐了之后生成。"""
    print(f'{TICKER}: 跳过，未达发布门槛 —— {msg}')
    print('monthly_run 下次例行跑会自动重试；这里不抛异常，免得日志天天多一条假 FAIL。')
    sys.exit(0)


def load_source_dates():
    """按路径加载仓库根的 source_dates.py（裸 import 不行：sys.path 上只有 build/）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ────────────────────────── 1. 换算库与规格表 ──────────────────────────
# notional.py 坏了 / 规格表缺行 都算「未就绪」，一律 skip(0)，不抛异常。
try:
    import notional
except Exception as e:                                    # noqa: BLE001
    skip(f'build/notional.py 加载失败（{type(e).__name__}: {e}）')

try:
    SPECS = notional.load_specs(SERIES)
    FX = notional.load_fx(SERIES)
except Exception as e:                                    # noqa: BLE001
    skip(f'规格表 / 汇率表加载失败（{type(e).__name__}: {e}）')

if notional.BASE_MONTH != BASE_MONTH:
    skip(f'基期不一致：本页写死 {BASE_MONTH}，build/notional.py 是 {notional.BASE_MONTH} —— '
         '基期一变，所有定基序列的权重都变，必须两处同时改')


def fxr(ccy, month, basis='avg'):
    """1 单位该币值多少美元。缺月一律抛异常（绝不用相邻月顶上）。"""
    return notional.fx_rate(FX, ccy, str(month), basis)


def _verify_fx_against_specs():
    """把本文件的换算公式与 series/contract_specs.csv 逐行对账。

    本页把 €bn 折成美元只有汇率这一跳（金额类产品的乘数与基期价格恒为 1）。
    规格表里 EU_CASH_ADNV_EUR / RAISE_EUR 两行的 base_notional_per_unit_usd()
    必须与本文件的 fxr('EUR', BASE_MONTH) 完全相等 —— 不等说明规格表里的乘数
    或基期价格被改成了非 1，本文件公式的前提就没了。
    """
    checked = []
    for pid in ('EU_CASH_ADNV_EUR', 'RAISE_EUR'):
        if pid not in SPECS:
            return None, f'规格表缺产品 {pid}'
        sp = SPECS[pid]
        if sp['ccy'] != 'EUR':
            return None, f'{pid} 的币种是 {sp["ccy"]}，不是 EUR'
        lib = notional.base_notional_per_unit_usd(pid, SPECS, FX, 'avg')
        mine = fxr('EUR', BASE_MONTH)
        if lib != mine:
            return None, f'{pid}：规格表算出 {lib!r}，本文件公式算出 {mine!r}，不一致'
        checked.append(pid)
    return checked, None


FX_CHECK, FX_CHECK_ERR = _verify_fx_against_specs()
if FX_CHECK_ERR:
    skip(f'换算公式与规格表对账失败 —— {FX_CHECK_ERR}')

EURUSD_BASE = fxr('EUR', BASE_MONTH)


# ────────────────────────── 2. 成员定义 ──────────────────────────
# (key, 显示名, 短名, csv, 成交额列, 交易日列(源列是月度总额时给), 颜色)
# 列名全部来自 `head -1 series/*.csv` 的真实表头。
MEMBERS = [
    ('enx',  'Euronext（股票与投资基金）', 'Euronext', 'enx.csv',
     'adv_cash_equities_adnv_eurbn', None, 'NAVY'),
    ('cboe', 'Cboe Europe（泛欧 MTF）', 'Cboe Europe', 'cboe.csv',
     'adv_eu_equities_adnv_eurbn', None, 'MBLUE'),
    ('db1',  'Deutsche Börse（Xetra + Börse Frankfurt）', 'Deutsche Börse', 'db1.csv',
     'turnover_cash_total_eurbn', 'trading_days_cash', 'GOLD'),
]
KEYS = [m[0] for m in MEMBERS]
DISP = {m[0]: m[1] for m in MEMBERS}
SHORT = {m[0]: m[2] for m in MEMBERS}
COLOR = {m[0]: m[6] for m in MEMBERS}

NDAQ_C = 'GRAY'          # Nasdaq 北欧：只在 Ex9 / Ex10 出现，不与 GRAY 的别的用法同图
TOTAL_C = 'GREEN'        # 池合计
CUR_FX_C = 'GRAY'        # 当期汇率对照线（Ex7 / Ex8，Nasdaq 不在场）

# Deutsche Börse 的窄口径对照列（与另两家逐字同口径，但比宽口径浅：两条同时有值的
# 交集 2026-08-19 实测是 2016-06 起 62 个月，宽口径有 199 个月。此处原注写「只有 19 个月」，
# 那是 2026-08-18 回补前的数。重叠月数由运行时现算，注释里这个数只是给人看的参照）
DB1_NARROW = ['turnover_xetra_equities_eurbn', 'turnover_fwb_equities_eurbn']
# Nasdaq 北欧（只做绝对值对照，绝不进份额）
NDAQ_MON_COL = 'vol_nordic_cash_value_usdbn'          # 当月合计，US$bn
NDAQ_Q_VAL, NDAQ_Q_SHARE = 'q_nordic_cash_value_usdbn', 'q_share_nordic_cash'


# ────────────────────────── 3. 读数据 ──────────────────────────
def read_csv(name, index='month', freq='M'):
    """series/<name> → 连续周期索引的 DataFrame。

    reindex 成连续期：原始文件中间缺月时，pct_change(12) 会按**位置**移 12 行，
    算出来的「同比」其实跨了 13 个月而完全看不出来。
    """
    p = os.path.join(SERIES, name)
    if not os.path.exists(p):
        return None
    d = pd.read_csv(p)
    if index not in d.columns:
        raise SystemExit(f'series/{name} 缺 {index} 列')
    d[index] = pd.PeriodIndex(d[index], freq=freq)
    d = d.set_index(index).sort_index()
    d = d.apply(pd.to_numeric, errors='coerce')
    return d.reindex(pd.period_range(d.index[0], d.index[-1], freq=freq))


RAW = {k: read_csv(csvf) for k, _d, _s, csvf, _c, _dd, _col in MEMBERS}
RAW['ndaq'] = read_csv('ndaq.csv')
NDQ = read_csv('ndaq_q.csv', index='quarter', freq='Q')


def adv_of(key, df=None):
    """成员的**本币日均成交额**（€bn/日）—— 源列是月度总额的先除自己的交易日。"""
    _k, _d, _s, _csv, col, days, _c = next(m for m in MEMBERS if m[0] == key)
    d = RAW[key] if df is None else df
    s = d[col].astype(float)
    if days:
        dd = d[days]
        s = s.where(dd > 0) / dd.where(dd > 0)
    return s


# ── 发布门槛：三条头条现货序列各自的最新有效月，取其 min ──
missing, latest_each, first_each = [], {}, {}
for key, disp, _sh, csvf, col, days, _c in MEMBERS:
    d = RAW[key]
    if d is None:
        missing.append(f'{disp}（缺 series/{csvf}）')
        continue
    lack = [c for c in ([col] + ([days] if days else [])) if c not in d.columns]
    if lack:
        missing.append(f'{disp}（series/{csvf} 缺列 {"、".join(lack)}）')
        continue
    s = adv_of(key).dropna()
    if s.empty:
        missing.append(f'{disp}（{col} 没有任何可用值）')
        continue
    latest_each[key], first_each[key] = s.index[-1], s.index[0]

if missing:
    skip('成员未就绪：' + '；'.join(missing))

LATEST = min(latest_each.values())
START = max(first_each.values())          # = Cboe Europe 的披露起点，本页历史长度的天花板
if START >= LATEST or (LATEST - START).n + 1 < MIN_COMMON:
    skip(f'共同历史只有 {max(0, (LATEST - START).n + 1)} 个月'
         f'（{mlab(START)} – {mlab(LATEST)}），不足 {MIN_COMMON} 个月')
if pd.Period(BASE_MONTH, freq='M') > LATEST:
    skip(f'基期 {BASE_MONTH} 晚于共同最新月 {LATEST}，指数化无从谈起')

IDX = pd.period_range(START, LATEST, freq='M')
XL_LONG = [mlab(p) for p in IDX]
LAG = [SHORT[k] for k in KEYS if latest_each[k] == LATEST]
AHEAD = [(SHORT[k], latest_each[k]) for k in KEYS if latest_each[k] > LATEST]
CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12
BASE_P = pd.Period(BASE_MONTH, freq='M')

# ADV（€bn/日）。失败要响：共同窗口内头条序列有洞说明源数据坏了，不是「成员没齐」。
ADV = pd.DataFrame({k: adv_of(k).reindex(IDX) for k in KEYS}, columns=KEYS)
for k in KEYS:
    holes = [str(p) for p in IDX if not ok(ADV[k][p])]
    if holes:
        raise SystemExit(f'{DISP[k]} 的现货成交额在共同窗口 {mlab(START)}–{mlab(LATEST)} '
                         f'内缺值：{holes}')

ADV_TOT = ADV.sum(axis=1)

# ── 月长（交易日）与月度成交额：占比一律建在**月度成交额**上，不建在 ADV 上 ──
# 三家的交易日历**不完全相同**：德国交易所在 12/24、12/31 与圣灵降临节休市，
# 窗口内有若干个月 Deutsche Börse 的 trading_days_cash 比 Euronext 少 1–2 天
# —— **具体几个月不写在这里**，由下面的 `DAYS_N - DAYS_SAME` 现算并印进图注。
# （此处原注写死「11 个月」，2026-08-19 实跑已是 12/127，与同页 Exhibit 2 图注
#   现算出来的数字正面矛盾 —— 这就是为什么月数一律不许留在注释里。）
# ADV = 月成交额 ÷ 各自的交易日 —— 天数少的那家 ADV 被除大，按 ADV 算占比等于
# 给它凭空加权。这条偏差的最大幅度同样现算（`SHARE_ADV_MAXGAP`，落在 12 月），
# 比这张图想讲的结构性移动还大，而且每年 12 月复发一次，看上去像季节性规律。
# 所以占比的分子分母全部换成**当月实际成交额**，与季度图（Exhibit 3）同一条链，
# 月度图与季度图在重叠处因此严格自洽。
DAYS_EU = RAW['enx']['trading_days_cash'].reindex(IDX)
_dd_db1 = RAW['db1']['trading_days_cash'].reindex(IDX)
_both = [p for p in IDX if ok(DAYS_EU[p]) and ok(_dd_db1[p])]
DAYS_SAME = sum(1 for p in _both if float(DAYS_EU[p]) == float(_dd_db1[p]))
DAYS_N = len(_both)
if DAYS_EU.dropna().shape[0] != len(IDX):
    skip('Euronext 的 trading_days_cash 在共同窗口内有缺月，占比与季度聚合都算不出来')

# ── Deutsche Börse 宽口径列到底有多长：现算，页面正文两处引用它 ─────────────────
# ⚠ 页面原先两处都写死「198 个月历史」（宽/窄口径对照那张图的图注与 NOTES 第 3 条）。
#   （原注在这里写的是「Exhibit 6 图注」—— 点错了图：Exhibit 6 是定基名义额指数化那张，
#     它的图注里一个「个月历史」都没有。图号本来就不该写进注释，改成按内容指认。）
#   这一列自 2010-01 起逐月连续、**每个月 +1**，2026-08-19 实跑已经是 199 —— 也就是说
#   页面今天就在说一件假事，而同文件 docstring 里那句现算出来的话写的正是 199。
#   月数一律不写在文案里，统一走 DB1_WIDE_N / DB1_WIDE_FROM。
_DB1_WIDE = RAW['db1']['turnover_cash_total_eurbn'].dropna()
DB1_WIDE_N = int(len(_DB1_WIDE))
DB1_WIDE_FROM = mlab(_DB1_WIDE.index.min()) if DB1_WIDE_N else '—'
# ── 停机兜底：DB1_WIDE_N 必须是「真有数的月份数」，不能悄悄变成「跨度」──────────
# NOTES 第 3 条把这个数与窄口径的月数**并排比较**（「只有它有 N 个月历史，而窄口径列
# 只有 M 个月有数」）。上一轮翻车正是因为那两个数不是同一种量：宽口径给的是逐月连续的
# 观测数，窄口径给的却是**首末月之间的跨度**（122），而窄口径真有数的只有 62 个月。
# 宽口径这一列今天逐月连续，所以 dropna 长度 == 跨度，两个数才可比。哪天它也开始缺月，
# 这句比较就不再成立 —— 与其让页面继续印一句读者会读错的话，不如当场停机。
if DB1_WIDE_N:
    _wide_span = len(pd.period_range(_DB1_WIDE.index.min(), _DB1_WIDE.index.max(), freq='M'))
    if DB1_WIDE_N != _wide_span:
        raise SystemExit(
            f'宽口径 turnover_cash_total_eurbn 出现缺月：有数 {DB1_WIDE_N} 个月、'
            f'跨度 {_wide_span} 个月（{mlab(_DB1_WIDE.index.min())}–'
            f'{mlab(_DB1_WIDE.index.max())}）。NOTES 第 3 条拿它与窄口径的「有数月数」'
            f'并排比较，前提就是这一列逐月连续 —— 先改写那句话，再跑。')

MONTHLY_EUR = pd.DataFrame({k: ADV[k] * DAYS_EU for k in KEYS}, columns=KEYS)  # €bn/月
# Deutsche Börse 的月度总额是官方原生列，不必反推 —— 直接用它，精度更高。
MONTHLY_EUR['db1'] = RAW['db1']['turnover_cash_total_eurbn'].reindex(IDX)
MONTHLY_TOT = MONTHLY_EUR.sum(axis=1)

SHARE = MONTHLY_EUR.div(MONTHLY_TOT, axis=0) * 100   # 分母 = 本池三家之和，**不是市场份额**
# 若哪天改回按 ADV 算，这个差值会立刻超过 1pp —— 留一条实测量在手边，写进图注。
SHARE_ADV_MAXGAP = float((ADV.div(ADV_TOT, axis=0) * 100 - SHARE).abs().max().max())

# 定基（锁 2019-01 月均 EUR/USD）与当期（每月各用各的月均汇率），单位 USD bn/日。
# 三家全部以 EUR 披露 ⇒ 汇率对**每一家都是同一个常数**，占比里一点汇率都没有。
EURUSD = pd.Series([fxr('EUR', p) for p in IDX], index=IDX)
BASE_USD = ADV_TOT * EURUSD_BASE
CURR_USD = ADV_TOT * EURUSD
FX_CONTRIB = (CURR_USD / BASE_USD - 1) * 100
FX_MOVE = (EURUSD / EURUSD_BASE - 1) * 100
# 恒等式自检：两条序列在数学上必须逐点相等（同一个比值的两种写法）。
FX_IDENT_MAX = float((FX_CONTRIB - FX_MOVE).abs().max())


def yoy_full(key):
    """**单月同比**（当月 ÷ 去年同月 − 1，%）：先在该家自己的完整历史上算，再截到共同窗口。

    先截窗口再算同比，共同窗口头 12 个月的 y/y 会全成空 —— 那不是数据缺口，
    是算法把已有的历史扔了（Euronext 与 Deutsche Börse 的历史都远早于本页窗口）。

    实现走 `build/yoy.py` 的 `mom_yoy()`，本文件**不自己写 `pct_change(12)`**：
    同比是本仓唯一一处「同一个判断做 15 遍、漏掉一次不报错」的地方，口径只有一份实现。

    ⚠ **建在日均（ADV）上，不建在月度合计上。** 单月同比里交易日数不会自己约掉：
    当月与去年同月的交易日数不同，月度合计的同比就带着一块纯日历效应。本页实测这块
    差多少由 `MOM_DAYGAP_MAX` / `MOM_DAYGAP_MED` 现算并印进图注 —— 不是小数点后的事。
    滚动口径（YOY12）不受这条约束，12 个月窗口把日历差基本抵掉了，所以它照旧建在
    月度成交额上、与占比图同一条链。

    这条序列喂 Exhibit 13 的热力矩阵与 Exhibit 14 的四条趋势线（同一批数、同一个口径）。
    """
    return yoy.mom_yoy(adv_of(key), yoy.FLOW).reindex(IDX)


YOY = {k: yoy_full(k) for k in KEYS}
YOY_TOT = yoy.mom_yoy(ADV_TOT, yoy.FLOW).reindex(IDX)   # 池合计只能从窗口内算

# 单月同比建在日均上还是建在月度合计上，差多少 —— 现算，Exhibit 14 的图注引用它。
# （滚动口径里这块日历效应基本自抵，单月口径里它是实打实的一大块，所以必须量出来。）
_daygap = pd.concat([(YOY[k] - yoy.mom_yoy(MONTHLY_EUR[k], yoy.FLOW)).abs() for k in KEYS])
MOM_DAYGAP_MAX = float(_daygap.max())
MOM_DAYGAP_MED = float(_daygap.median())


# ── 12 个月滚动合计同比：2026-09 起**页上一条线都不画**，只留下面两个用途 ──
#   ① 图注里那组「当期对照」读数（CONTRACT §6.1 第 3 条允许对照口径以数字出现）；
#   ② 口径诊断的对照面（DIAG 自己另滚一遍日均链，见 yoy_diag 的 docstring）。
# 全站改单月是页面所有者定的（CONTRACT §6 抬头引了原话），本页不在 §6.2 的例外名单里。
ROLL = 12


def monthly_full(key):
    """该家**完整历史**上的月度成交额（€bn/月）—— 滚动合计的底料。

    必须在完整历史上算：滚动 12 个月再同比要回看 24 个月，若先截到共同窗口，
    Euronext 与 Deutsche Börse 那两条深历史序列的开头会平白丢掉两年的读数，
    而那两年的数据是有的。共同窗口只在最后 reindex 一次。
    """
    if key == 'db1':
        # 官方原生的月度总额，不必由 ADV 反推（与 MONTHLY_EUR['db1'] 同一列）。
        return RAW['db1']['turnover_cash_total_eurbn'].astype(float)
    # 另两家披露的是日均，乘 Euronext 的现货交易日还原成月度总额 ——
    # 与 MONTHLY_EUR 用的是**同一个**月长权重，两条链因此严格同源（下面有断言）。
    days = RAW['enx']['trading_days_cash'].astype(float)
    s = adv_of(key).astype(float)
    d = days.reindex(s.index)
    return s * d


MON_FULL = {k: monthly_full(k) for k in KEYS}
# 自检：新链在共同窗口内必须与既有的 MONTHLY_EUR 逐点相同。
# 不这么做会怎样：滚动同比与占比会悄悄建在两条不同的成交额序列上，两张图各说各话，
# 而差异小到肉眼看不出来 —— 正是这类偏差最难被发现。
MON_CHAIN_MAX = float(max(
    (MON_FULL[k].reindex(IDX) - MONTHLY_EUR[k]).abs().max() for k in KEYS))
if not (MON_CHAIN_MAX < 1e-9):
    raise SystemExit(f'滚动同比的月度成交额链与占比用的 MONTHLY_EUR 不一致，'
                     f'最大偏差 {MON_CHAIN_MAX:.3e} €bn —— 两者必须是同一条链')

# ⚠ 这里原先还留着 R12 / R12_TOT（滚动合计本身）。滚动合计与它的同比改由
#   yoy.ttm_yoy() 一步算完之后，那两个中间量再没人用 —— 一并删掉，别留半条死链。
YOY12 = {k: yoy.ttm_yoy(MON_FULL[k], yoy.FLOW).reindex(IDX) for k in KEYS}
# 池合计只能从窗口内算（Cboe Europe 的历史就是本页窗口的起点），
# 所以它的滚动同比比成员晚 23 个月才有第一个读数 —— 如实留空，不做任何外推。
YOY12_TOT = yoy.ttm_yoy(MONTHLY_TOT, yoy.FLOW).reindex(IDX)
# ⚠ 这里原先还算了 YOY12_FIRST / YOY12_TOT_FIRST（滚动同比第一个有值的月份），
#   唯一的用处是 Exhibit 14 图注里那句「Cboe 的线从 X 才起」。本轮 Exhibit 14 换成单月
#   口径，起点跟着变成 YOY_FIRST / YOY_TOT_FIRST，那两个常量再没人用 —— 一并删掉。
#   留着比删掉更糟：下一个人会以为页面上某处还在按滚动口径讲起点。


# ── 两种同比口径的实测对照（图注里引用的数字全部出自这里）──
def yoy_diag(s, breaks=()):
    """单月同比 vs 12 个月滚动同比的实测对照 —— 统计量一律由 `yoy.caliber_diff()` 出。

    这里**不自己算**标准差与跳变：`caliber_diff()` 第一步就是取「两种口径都有值的月份
    的交集」，不对齐会把「滚动那条少 12 个月历史」的样本效应混进标准差里读成口径效应
    （`build/CONTRACT.md` §6.4「比较两种口径时样本必须先对齐」，上一版编号是 §6.3）。
    `win=IDX`：诊断只量读者在图上看得到的那一段。

    本函数额外做的只有一件事 —— **断点洁净子集**：滚动同比回看 24 个月，所以要求
    [t−23, t] 里不含任何并表断点，两种口径才都没被并表污染。符号相反的例子拿这个
    子集里的，免得被人一句「那是并表造成的」挡回去。

    ⚠ **为什么不用 `yoy.describe()` 出图注文案**：不是它写错了（它 2026-09 已随全站
    改口径改过末句），是它按**一条序列**出一段话，而本页要在同一段里覆盖三家 + 池合计
    四条线 —— 逐条各印一段会把图注撑成四倍。所以只取它的**统计量**（数字一个都不自己
    算），措辞照着 CONTRACT §6.1 第 3 条点名的底座 `build/single.py::mom_cost_zh()` 写，
    要报的三样一样不少：逐月标准差、相邻月最大跳变（带月份）、符号相反的月份数。

    传进来的 `s` 是**成交额序列本身**（完整历史），不是算好的同比。
    """
    d = yoy.caliber_diff(s, yoy.FLOW, win=list(IDX))
    if d['n'] < 24 or not d['std_ttm']:
        return None
    clean = set(p for p in d['months']
                if not any(p - (2 * ROLL - 1) <= x <= p for x in breaks))
    flips = [t for t in d['opposite'] if t[0] in clean]
    d['n_clean'] = len(clean)
    d['flip_clean'] = len(flips)
    d['worst'] = max(flips, key=lambda t: abs(t[1] - t[2])) if flips else None
    return d


# DIAG 的实际计算在第 5 节之后（要用到 enx_breaks.csv 读出来的断点集合）。
# ────────────────────────── 4. 季度聚合 ──────────────────────────
# 季度份额必须**量加权**（Σ该季各月成交额 ÷ Σ该季池合计），不是三个月份额的算术平均：
# 平均会让一个只有 18 个交易日的 12 月与一个 23 天的 3 月等权，把日历噪音读成份额变化。
# 月度成交额 MONTHLY_EUR 与月长权重 DAYS_EU 在上一节已经建好（月度占比也建在它上面），
# 这里只做「按季求和再相除」这一步，两张图因此严格同源。
QP = pd.PeriodIndex([p.asfreq('Q') for p in IDX], freq='Q')
_qcnt = pd.Series(1, index=IDX).groupby(QP.values).sum()
QIDX = [q for q in _qcnt.index if _qcnt[q] == 3]          # 只要完整季，残季一律不画
QIDX = pd.PeriodIndex(sorted(QIDX), freq='Q')
if len(QIDX) < MIN_QUARTERS:
    skip(f'完整季只有 {len(QIDX)} 个，不足 {MIN_QUARTERS} 个，季度长历史份额图画不出来')
QVOL = MONTHLY_EUR.groupby(QP.values).sum(min_count=3).reindex(QIDX)
QSHARE = QVOL.div(QVOL.sum(axis=1), axis=0) * 100
QLAB = [qlab(q) for q in QIDX]
QSPAN_Y = (len(QIDX) * 3) / 12.0


# ────────────────────────── 5. Euronext 并表断点（由 enx_breaks.csv 驱动）──────────────────────────
ENX_COL = 'adv_cash_equities_adnv_eurbn'


def enx_break_months(column):
    """series/enx_breaks.csv → 该列的**全部**断点月份（不截窗口）。

    单独抽出来是因为有两处要用不截窗口的原始集合：
    (1) 判断某个月的 24 个月滚动同比窗口有没有被并表污染；
    (2) 比对「金额列」与「笔数列」的断点集合是否逐个相同（量价分解成对性的机器判据）。
    """
    p = os.path.join(SERIES, 'enx_breaks.csv')
    if not os.path.exists(p):
        return set()
    got = set()
    with open(p, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if (r.get('column') or '').strip() != column:
                continue
            m = (r.get('break_month') or '').strip()
            if m:
                got.add(pd.Period(m, freq='M'))
    return got


def enx_breaks(column):
    """series/enx_breaks.csv → 该列在本页窗口内的断点月份（升序、去重）。

    不在代码里写死月份：官方脚注改了、fetch 重抓了，这里自动跟上；
    反过来，代码里写死的月份出了错，图上永远看不出来。
    """
    if not os.path.exists(os.path.join(SERIES, 'enx_breaks.csv')):
        return [], [], '缺 series/enx_breaks.csv'
    got = enx_break_months(column)
    inwin = sorted(x for x in got if START < x <= LATEST)      # 严格大于起点，见下
    at_start = sorted(x for x in got if x == START)
    out = sorted(x for x in got if x < START)
    why = []
    if out:
        why.append(f'另有 {len(out)} 个断点（{"、".join(mlab(x) for x in out)}）'
                   f'早于本页窗口起点 {mlab(START)}，不画')
    if at_start:
        # 断点画在「该期左缘」，语义是「从这一期起与左侧不可比」；落在第一期时左侧
        # 根本没有数据，画一条贴着纵轴的红线只会让人以为图坏了。
        why.append(f'{"、".join(mlab(x) for x in at_start)} 的断点恰好落在窗口第一期，'
                   f'左侧没有可比对象，故不画竖线 —— 本页全程已在该次并表之后')
    return inwin, at_start, '；'.join(why)


ENX_BRK, ENX_BRK_AT_START, ENX_BRK_WHY = enx_breaks(ENX_COL)
BRK_LABEL = {'2021-05': '并表 Borsa Italiana', '2025-11': '并表 Athens',
             '2017-01': '并表 Dublin', '2018-01': '并表 Oslo'}
ENX_BRK_TXT = [BRK_LABEL.get(str(p), '口径断点') for p in ENX_BRK]
ENX_BRK_I = [list(IDX).index(p) for p in ENX_BRK]
# 季度图上的断点：落到该月所属季度那一格；同季多个断点去重，第一格不画（同上）。
_qb = []
for p, t in zip(ENX_BRK, ENX_BRK_TXT):
    q = p.asfreq('Q')
    if q in set(QIDX) and list(QIDX).index(q) > 0 and q not in [x for x, _ in _qb]:
        _qb.append((q, t))
QBRK_I = [list(QIDX).index(q) for q, _ in _qb]
QBRK_TXT = [t for _, t in _qb]

# ── 两种同比口径的实测对照（第 3 节定义了 yoy_diag，这里才有断点集合可用）──
ENX_BRK_ALL = enx_break_months(ENX_COL)
DIAG = {k: yoy_diag(adv_of(k), ENX_BRK_ALL if k == 'enx' else ()) for k in KEYS}
DIAG['_tot'] = yoy_diag(ADV_TOT)
DIAG_OK = [k for k in KEYS if DIAG[k]]
if not DIAG_OK:
    skip('两种同比口径都凑不满 24 个可比月，实测证据拿不出来 —— 本页的口径代价没法量')
# 页面文案要引用的四个汇总量：噪音倍数、相邻月跳变（最大与中位）、符号相反的月数
SD_RATIO = {k: DIAG[k]['std_ratio'] for k in DIAG_OK}
JUMP1_MAX = max(DIAG[k]['maxjump_mom'][0] for k in DIAG_OK)
JUMP1_WHO = max(DIAG_OK, key=lambda k: DIAG[k]['maxjump_mom'][0])
JUMP12_MAX = max(DIAG[k]['maxjump_ttm'][0] for k in DIAG_OK)
# 相邻月跳变的中位数按序列**各算各的**，页面上报区间而不是某一条 —— 报 max 会让读者
# 以为那是「本页的中位跳变」，其实是三条里最毛的那条。
MEDJ1_LO = min(DIAG[k]['medjump_mom'] for k in DIAG_OK)
MEDJ1_HI = max(DIAG[k]['medjump_mom'] for k in DIAG_OK)
MEDJ12_LO = min(DIAG[k]['medjump_ttm'] for k in DIAG_OK)
MEDJ12_HI = max(DIAG[k]['medjump_ttm'] for k in DIAG_OK)
FLIP_TOT = sum(DIAG[k]['opposite_n'] for k in DIAG_OK)
FLIP_N_TOT = sum(DIAG[k]['n'] for k in DIAG_OK)
# ⚠ 诊断的**滚动侧**是 caliber_diff 拿同一条**日均**序列自己滚出来的（12 个日均值等权
# 相加），而图注里那组「当期对照」读数取自 YOY12，建在**月度成交额**链上（与占比图同源）。
# 两者差的只是交易日数，差多少现算 —— 图注里说「诊断的滚动侧是个近似」凭的就是这个数，
# 没有它那句话就是空口。（两条都只以数字出现，页上一条线都不画。）
_ttmgap = pd.concat([(yoy.ttm_yoy(adv_of(k), yoy.FLOW).reindex(IDX) - YOY12[k]).abs()
                     for k in KEYS])
TTM_CHAIN_GAP_MAX = float(_ttmgap.max())
TTM_CHAIN_GAP_MED = float(_ttmgap.median())
# 「符号相反」的展示例子只从**断点洁净**子集里挑，且挑两个口径差得最远的那个月，
# 免得读者一句「那不过是并表造成的」就把整条证据挡回去。
_cands = [DIAG[k]['worst'] + (k,) for k in DIAG_OK if DIAG[k]['worst']]
FLIP_EX = max(_cands, key=lambda t: abs(t[1] - t[2])) if _cands else None

# Athens 备注列：主列 − 备注列 = 与并表前同口径的序列（本页唯一可定量还原的断点）
ATH_COL = 'athex_adv_cash_equities_adnv_eurbn'
_enx = RAW['enx']
ATH_P = pd.Period('2025-11', freq='M')
HAS_ATH = (ATH_COL in _enx.columns and _enx[ATH_COL].dropna().shape[0] > 0
           and ATH_P in set(IDX))
if HAS_ATH:
    ATH_START = max(_enx[ATH_COL].dropna().index[0], START)
    W_ATH = pd.period_range(ATH_START, LATEST, freq='M')
    ENX_HEAD = _enx[ENX_COL].reindex(W_ATH)
    ATH_BRK_I = [list(W_ATH).index(ATH_P)]
    # ⚠ 备注列的语义**在断点前后不同**（docs/verify/enx.md 字段对照表原文）：
    #   2025-11 之前 = 尚未并入主列的部分（主列里**没有**它）；
    #   2025-11 起   = 已经含在主列里的那部分。
    # 所以「与并表前同口径」= 断点前照抄主列、断点起才减备注列。一律减会把断点前
    # 的线整体压低一截（Athens 被减了两次），而那条被压低的线看上去完全正常。
    _ath = _enx[ATH_COL].reindex(W_ATH)
    ENX_EXATH = ENX_HEAD.copy()
    _post = [p for p in W_ATH if p >= ATH_P]
    ENX_EXATH.loc[_post] = ENX_HEAD.loc[_post] - _ath.loc[_post]
    ATH_PCT_NOW = (float(_ath.get(CUR, np.nan)) / float(ENX_HEAD.get(CUR, np.nan)) * 100
                   if ok(ENX_HEAD.get(CUR, np.nan)) and float(ENX_HEAD.get(CUR, 0)) else np.nan)
    # 并表对**池内占比**的影响：分子分母同时改，所以必须重算整池而不是只改 Euronext
    _sh_ath = {}
    for p in (ATH_P, CUR):
        if p in set(W_ATH):
            hd = {k: float(ADV[k][p]) for k in KEYS}
            ex_ = dict(hd, enx=float(ENX_EXATH[p]))
            _sh_ath[p] = (hd['enx'] / sum(hd.values()) * 100,
                          ex_['enx'] / sum(ex_.values()) * 100)
else:
    W_ATH = None
    ATH_PCT_NOW = np.nan
    _sh_ath = {}


# ────────────────────────── 6. Deutsche Börse 宽窄口径的实测代价 ──────────────────────────
_db1 = RAW['db1']
HAS_NARROW = all(c in _db1.columns for c in DB1_NARROW)
if HAS_NARROW:
    _nar_m = _db1[DB1_NARROW].sum(axis=1, min_count=len(DB1_NARROW)).reindex(IDX)
    _dd = _db1['trading_days_cash'].reindex(IDX)
    DB1_NARROW_ADV = _nar_m.where(_dd > 0) / _dd.where(_dd > 0)
else:
    DB1_NARROW_ADV = pd.Series(np.nan, index=IDX)

# 窄口径那两列**有值的月份**（用来算倍数与占比缺口的统计量）。
_NAR_OK = [p for p in IDX if ok(DB1_NARROW_ADV[p]) and ok(ADV['db1'][p])]
# ⚠ **画图的横轴不能用 _NAR_OK**，必须是从首个有值月到末个有值月的**逐月连续**区间。
# 2026-08-18 db1 回补之后这两列从「2024-12 起连续 20 个月」变成「2016-06 起、
# 中间有 2016-07 与 2017-06…2022-04 两大段空洞」。拿有值月直接当横轴，
# `May-17` 与 `May-22` 会被画成**相邻两格**，中间 5 年凭空消失 ——
# 那是 build/CONTRACT.md 规矩 3 明令禁止的「假时间轴」：
# 「dropna 会把中间缺的月直接从横轴上抹掉，于是相隔两个月的两点被并排画成相邻期」。
# 逐月铺开、缺月留 null，`lines` 图型（doSmooth=false）会断笔而不是压缩。
_IDXL = list(IDX)
W_NAR = (_IDXL[_IDXL.index(_NAR_OK[0]):_IDXL.index(_NAR_OK[-1]) + 1] if _NAR_OK else [])
HAS_NAR_WIN = len(_NAR_OK) >= 6


def _gap_txt(full, have):
    """把「哪几段没有数据」说成人话，供图注用。现算，不写死。"""
    hv = set(have)
    runs, cur = [], None
    for p in full:
        if p in hv:
            if cur:
                runs.append(cur)
                cur = None
        else:
            cur = [p, p] if cur is None else [cur[0], p]
    if cur:
        runs.append(cur)
    if not runs:
        return '中间无空洞'
    parts = [(f'{mlab(a)} 无数据' if a == b else f'{mlab(a)}–{mlab(b)} 整段无数据')
             for a, b in runs]
    return '；'.join(parts)


_NAR_GAP_TXT = _gap_txt(W_NAR, _NAR_OK) if W_NAR else ''
if HAS_NAR_WIN:
    # ⚠ 统计量一律走 `_NAR_OK`（**真有值**的月），不能走 `W_NAR`（画图用的逐月连续横轴）。
    # 两者 2026-08-18 之后不再相等：W_NAR 里含 2016-07 与 2017-06…2022-04 两段空洞，
    # 拿它算 min/median/max 会全变成 nan（payload_guard 当场拦下来过一次）。
    _ratio = pd.Series([float(ADV['db1'][p] / DB1_NARROW_ADV[p]) for p in _NAR_OK],
                       index=_NAR_OK)
    SCOPE_MIN, SCOPE_MED, SCOPE_MAX = (float(_ratio.min()), float(_ratio.median()),
                                       float(_ratio.max()))
    # 折成池内占比：窄口径下重算整池（分子分母同时变）
    _gap = []
    for p in _NAR_OK:
        wide = {k: float(ADV[k][p]) for k in KEYS}
        nar = dict(wide, db1=float(DB1_NARROW_ADV[p]))
        _gap.append(wide['db1'] / sum(wide.values()) * 100
                    - nar['db1'] / sum(nar.values()) * 100)
    SH_GAP_MIN, SH_GAP_MED, SH_GAP_MAX = (float(np.min(_gap)), float(np.median(_gap)),
                                          float(np.max(_gap)))
    NAR_SHARE_NOW = {k: (float(DB1_NARROW_ADV[_NAR_OK[-1]]) if k == 'db1'
                         else float(ADV[k][_NAR_OK[-1]]))
                     for k in KEYS}
    _ns = sum(NAR_SHARE_NOW.values())
    NAR_SHARE_NOW = {k: v / _ns * 100 for k, v in NAR_SHARE_NOW.items()}
else:
    SCOPE_MIN = SCOPE_MED = SCOPE_MAX = np.nan
    SH_GAP_MIN = SH_GAP_MED = SH_GAP_MAX = np.nan
    NAR_SHARE_NOW = {}


# ────────────────────────── 7. Nasdaq 北欧（只做绝对值与分母对撞）──────────────────────────
_nd = RAW['ndaq']
HAS_NDAQ = _nd is not None and NDAQ_MON_COL in _nd.columns
if HAS_NDAQ:
    NORD_USD = _nd[NDAQ_MON_COL].reindex(IDX)               # 当月合计，US$bn
    NORD_EUR = NORD_USD / EURUSD                            # 当期月均汇率折欧元
    _ND_OK = [p for p in IDX if ok(NORD_EUR[p])]
else:
    NORD_USD = NORD_EUR = pd.Series(np.nan, index=IDX)
    _ND_OK = []
# ⚠ 与上面的 `_NAR_OK` / `W_NAR` 同一条规矩（build/CONTRACT.md 规矩 3）：
# **画图的横轴不能用 `_ND_OK`**（有值的那些月），必须是首末之间的**逐月连续**区间。
# 今天两者恰好相等（这一列 2025-01…2026-07 共 19 个月、无洞），所以本次改动
# 输出零差异 —— 但它不是恒真的：IR 月报是「上一整年 + 本年 YTD」的滚动窗，
# 官方哪期漏发一个月，`_ND_OK` 就会出洞，而拿它当横轴的话那个洞**不会有任何症状**，
# 只会把相隔的两点静静画成相邻两格。这正是本页 Exhibit 12 栽过的那一跤
# （May-17 与 May-22 画成相邻），修在那里就该一并修在这里。
# 逐月铺开、缺月留 null：Exhibit 9 是 `lines`，不在 mrwin.DENSE 里，引擎会断笔。
W_ND = (_IDXL[_IDXL.index(_ND_OK[0]):_IDXL.index(_ND_OK[-1]) + 1] if _ND_OK else [])
_ND_GAP_TXT = _gap_txt(W_ND, _ND_OK) if W_ND else ''
HAS_NDAQ = len(_ND_OK) >= 6

if HAS_NDAQ:
    # 统计量一律走 `_ND_OK`（真有值的月），不走 `W_ND`（画图用的逐月连续横轴）——
    # 走 W_ND 的话一旦出洞，min/median/max 会整个变成 nan（payload_guard 拦过一次）。
    _rt = pd.Series([float(MONTHLY_EUR['cboe'][p] / NORD_EUR[p]) for p in _ND_OK],
                    index=_ND_OK)
    ND_RT_MIN, ND_RT_MED, ND_RT_MAX = float(_rt.min()), float(_rt.median()), float(_rt.max())
else:
    ND_RT_MIN = ND_RT_MED = ND_RT_MAX = np.nan

# 为什么这张图只有这么短的一段 —— 图上看得见的差异，图注就必须回答，
# 否则读者只能猜是「懒得补」。这是**源的边界**，不是窗口裁剪：
# 全部依据在 fetch/ndaq.py 的 A 组说明与「未找到」一节（ND_MEAS_D 那天重新实测过）。
#
# ⚠ **对照对象只许写这个池窗口（START/IDX），不许写「本页其余各图」。**
#   START 是三家现货池的**共同起点**（NOTES 第一条：由 Cboe Europe 的披露起点决定），
#   它是池窗口常量，**不是全页横轴的通称**。2026-08-19 逐图数过：本页 15 张图里真的
#   从 Jan-16 起的只有 5 张（Ex2 与 x='long' 的 Ex6/7/8/14）；Ex16 起于 Jan-12
#   （比 START 还早 4 年）、Ex12 Jun-16、Ex11 Jan-21、Ex13 Aug-24、Ex10 1Q23、
#   Ex3 1Q16、Ex15 2013、Ex4/5 是分类轴。写「其余各图自 Jan-16 起」读者往下滚一张
#   就能当场推翻，而这张图注存在的全部理由就是取信于读者。
#
# 实测数字一律**带日期落款**（ND_MEAS_D）写成历史陈述，而不是「近 N 个月」，
# 这样它不会随窗口滚动而变假；116/127 那个分数同理把两端月份写实，不跟着 IDX 走。
ND_MEAS_D = '2026-08-18'      # fetch/ndaq.py 里这几条实测的日期；那边重测了，这里要跟着改
ND_WIN_NOTE = (
    (f'<b>本图只有 {mlab(W_ND[0])} 起的 {len(W_ND)} 个月，而本页主口径那三家的共同窗口'
     f'自 {mlab(START)} 起、共 {len(IDX)} 个月（见页尾「发布门槛」那一条）；'
     f'这是源的边界，不是把窗口截短了。</b>'
     f'Nasdaq 北欧这一列出自 IR「Monthly Reporting Sheet」PDF，该文件<b>恒只含'
     f'「上一整年 + 本年 YTD」</b>（19–24 个月），且 IR 站不留历史副本'
     f'（{ND_MEAS_D} 实测：落地页全页只有 1 条 static-file 链接、0 条年份归档链接）。'
     f'官方更早的北欧月报本身是找得到的，但它给的是<b>欧元</b>的 on-exchange turnover，'
     f'折不回 IR 那条<b>美元</b>列：{ND_MEAS_D} 实测的 13 个重叠月里，按月均 EUR/USD '
     f'折算系统性低 0.77%–2.50%，按月末汇率更差，把 First North 加进来又高出一大截 —— '
     f'IR 那条美元列的确切 scope 与汇率口径没能复原，'
     f'<b>两截不同口径的线首尾相接就是造一条假历史</b>。'
     f'另有一路公告正文覆盖 2016-01–2026-07 的 116/127 个月的欧元日均'
     f'（同为 {ND_MEAS_D} 实测），但只有 2 位有效数字'
     f'（"3.327bn"），写进真值表是假精度。'
     + (f'　⚠ 窗口内还有缺口：{_ND_GAP_TXT}（缺月留 null、线断开，不补值）。'
        if _ND_GAP_TXT and _ND_GAP_TXT != '中间无空洞' else '')
     + '　') if HAS_NDAQ else '')

# 季度分母对撞：Nasdaq 自报份额反推出来的「欧洲市场」分母 vs Cboe Europe 一家
HAS_NDQ = (NDQ is not None and NDAQ_Q_VAL in NDQ.columns and NDAQ_Q_SHARE in NDQ.columns)
if HAS_NDQ:
    _qv = NDQ[NDAQ_Q_VAL]
    _qs = NDQ[NDAQ_Q_SHARE]
    QN = [q for q in NDQ.index if q in set(QIDX) and ok(_qv[q]) and ok(_qs[q]) and float(_qs[q]) > 0]
    HAS_NDQ = len(QN) >= 4
else:
    QN = []
if HAS_NDQ:
    QN = pd.PeriodIndex(sorted(QN), freq='Q')
    # Cboe Europe 的季度成交额折成美元：与 Nasdaq 的自报口径对齐，用**当期**月均汇率
    _cb_usd_m = MONTHLY_EUR['cboe'] * EURUSD
    _cb_q = _cb_usd_m.groupby(QP.values).sum(min_count=3).reindex(QN)
    ND_QV = pd.Series([float(_qv[q]) for q in QN], index=QN)
    ND_QD = pd.Series([float(_qv[q]) / float(_qs[q]) for q in QN], index=QN)   # 隐含分母
    ND_QRATIO = (_cb_q / ND_QD)
    ND_QR_MIN, ND_QR_MED, ND_QR_MAX = (float(ND_QRATIO.min()), float(ND_QRATIO.median()),
                                       float(ND_QRATIO.max()))
    ND_SHARE_LAST = float(_qs[QN[-1]]) * 100
    CB_Q_USD = _cb_q


# ──────────── 7b. 「成交额 = 成交笔数 × 每笔均值」分解：先判定谁有资格，再算 ────────────
# ⚠ 名字必须准确：这**不是**量价分解。分解出来的第二项是**每笔平均成交额**，
# 它主要反映订单碎片化程度（一张单子多大），与市场涨跌只有间接关系。
# 叫它「价」是错的 —— 真正的「股数 × 均价」需要成交股数列，本页三家一家都没有。
# 恒等式 成交额 ≡ 笔数 × 每笔均值 是定义式，不需要任何假设 —— 但**前提是分子分母同口径**。
# 拿口径不一致的两列凑一个均值，会造出一个方向与大小都不可知的偏差，
# 而图上完全看不出来（曲线照样光滑、恒等式照样成立）。所以先判定，判定不过就不画。
_CCY_SUF = ('_eurbn', '_eurm', '_eurmn', '_eurtn', '_usdbn', '_usdm', '_usd',
            '_bps', '_pct', '_eur')
_NOT_QTY = ('trading_days', 'issuers_', 'listed_', 'new_listings', 'mktcap',
            'rpc_', 'fee_', 'aum_', 'oi_')
_CASH_HINT = ('cash', 'equities', 'xetra', 'fwb')


def cash_qty_candidates(df):
    """扫这家 CSV 里**与现货相关、且不是金额/费率/家数**的列 = 候选「数量列」。

    为什么要扫而不是直接写死结论：「这家没有数量列」是一个否定命题，
    写死就等于把「我这一轮没找到」冒充成「它不存在」。扫描结果会打印在自检行里，
    哪天 fetch 新增了一列数量，自检行立刻变化，而不是继续沉默地少一张图。
    """
    if df is None:
        return []
    out = []
    for c in df.columns:
        if not any(h in c for h in _CASH_HINT):
            continue
        if any(c.endswith(s) for s in _CCY_SUF) or any(c.startswith(s) or s in c
                                                       for s in _NOT_QTY):
            continue
        out.append(c)
    return sorted(out)


QTY_SCAN = {k: cash_qty_candidates(RAW[k]) for k in KEYS}

# Euronext 是唯一一家有现货数量列的。与它同口径的金额列**不是**本页头条那一列：
#   笔数列  = Total number of trades(C4)  → 全部现货
#   头条列  = Turnover Equities(C8)       → 只有股票与投资基金  ← 口径更窄，不成对
#   配对列  = Total Turnover(C6)          → 全部现货            ← 与笔数列成对
VP_KEY = 'enx'
VP_VAL_COL = 'adv_cash_adnv_eurbn'      # €bn/日，单边计，全部现货
VP_TRD_COL = 'adv_cash_trades_k'        # 千笔/日，买卖双边计，全部现货
VP_WHY = []                              # 判定不通过的原因，如实写进页面
_e = RAW['enx']
if VP_TRD_COL not in QTY_SCAN[VP_KEY]:
    VP_WHY.append(f'Euronext 的现货数量列扫描结果里没有 {VP_TRD_COL}')
if VP_VAL_COL not in (_e.columns if _e is not None else []):
    VP_WHY.append(f'series/enx.csv 缺 {VP_VAL_COL}')
# 成对性的机器判据 1：两列的并表断点集合必须**逐个相同**。
# 不同就说明两列覆盖的市场集合不同（有一列并了某地、另一列没并），
# 那样算出来的「每笔均值」在断点两侧不是同一个东西。
VP_BRK_VAL = enx_break_months(VP_VAL_COL)
VP_BRK_TRD = enx_break_months(VP_TRD_COL)
if VP_BRK_VAL != VP_BRK_TRD:
    VP_WHY.append(f'{VP_VAL_COL} 的断点 {sorted(str(x) for x in VP_BRK_VAL)} 与 '
                  f'{VP_TRD_COL} 的断点 {sorted(str(x) for x in VP_BRK_TRD)} 不一致，'
                  '两列覆盖的市场集合不同，不成对')

HAS_VP = not VP_WHY
if HAS_VP:
    _d = _e['trading_days_cash'].astype(float)
    # 不许越过本页发布门槛：跑在前面那家的最新月不进本页任何一张图（页脚承诺）。
    _win = pd.PeriodIndex([p for p in _e.index if p <= LATEST], freq='M')
    VP_V = (_e[VP_VAL_COL].astype(float) * _d).reindex(_win)   # €bn/月
    VP_N = (_e[VP_TRD_COL].astype(float) * _d).reindex(_win)   # 千笔/月
    VP_E = (_e[ENX_COL].astype(float) * _d).reindex(_win)      # 头条口径，只用来量宽窄差
    _good = [p for p in _win if ok(VP_V[p]) and ok(VP_N[p]) and float(VP_N[p]) > 0]
    HAS_VP = len(_good) >= 24
    if not HAS_VP:
        VP_WHY.append(f'金额与笔数同时有值的月份只有 {len(_good)} 个，不足 24 个')
    # ⚠ 假时间轴防线（build/CONTRACT.md 规矩 3）：下面 `VP_MON` 直接由 `_good` 铺成横轴，
    # 中间一旦有洞，相隔数年的两点会被画成相邻两格 —— 本页 Exhibit 12 栽过这一跤。
    # 这里**不照 W_NAR 改成「连续轴 + null」**，因为 VP_MON 同时被当作「有值月集合」用：
    # `HAS_VP_TTM = all(p in set(VP_MON) ...)` 就是拿它判 TTM 那 24 个月齐不齐，
    # 铺成连续轴会让那个判据恒真、静默放行一个缺月的 TTM。两种语义要分家得连带审十几处，
    # 而这两列同出 series/enx.csv 一张表、2026-08-19 实测 2012-01…2026-07 共 175 个月无洞。
    # 所以选另一条：**真出洞就整块停画**，绝不画一条压缩过的假轴。
    elif (_good[-1] - _good[0]).n + 1 != len(_good):
        HAS_VP = False
        VP_WHY.append(
            f'金额与笔数同时有值的月份不连续（{mlab(_good[0])}–{mlab(_good[-1])} 共 '
            f'{(_good[-1] - _good[0]).n + 1} 个月里只有 {len(_good)} 个有值：'
            f'{_gap_txt(pd.period_range(_good[0], _good[-1], freq="M"), _good)}）；'
            f'把有值月直接当横轴会画出假时间轴，故整块不画')

if HAS_VP:
    VP_MON = pd.PeriodIndex(sorted(_good), freq='M')
    VP_XL = [mlab(p) for p in VP_MON]
    # 宽窄差：本页头条列（只有股票与投资基金）占配对列（全部现货）的多少，实测不估。
    _sc = np.array([float(VP_E[p] / VP_V[p]) for p in VP_MON
                    if ok(VP_E[p]) and ok(VP_V[p]) and float(VP_V[p])])
    VP_SC_MIN, VP_SC_MED, VP_SC_MAX = (float(_sc.min()) * 100, float(np.median(_sc)) * 100,
                                       float(_sc.max()) * 100)
    # 笔数本身：月度合计（百万笔/月）+ **单月同比**（当月 ÷ 去年同月 − 1）。
    # 单月口径下线画的就是**柱自己的同比**，读者可以拿相邻两根柱当场核对 —— 若改画
    # 日均口径的同比（把日历效应剔掉），线与柱就对不上了，而图上完全看不出来。
    # 代价：这条线里含日历效应，差多少由 VP_N_DAYGAP_* 现算并印进图注。
    VP_N_M = (VP_N / 1e3).astype(float)                       # 百万笔/月
    VP_N_MOM = yoy.mom_yoy(VP_N, yoy.FLOW).reindex(VP_MON)
    # ⚠ 原先这里还算一条 VP_N_YOY12（滚动同比）喂右轴。改口径后右轴走 VP_N_MOM，
    #   而口径对照的统计量由下面的 VP_CAL（yoy.caliber_diff）自己滚一遍 —— 那条中间量
    #   再没人用，删掉；留着会让人以为图上还有一条滚动线。
    VP_N_YOY_LO = float(VP_N_MOM.min())
    VP_N_YOY_HI = float(VP_N_MOM.max())
    VP_N_MOM_FIRST = VP_N_MOM.dropna().index[0]
    # 换口径的代价：同一条笔数序列，两种口径实测差多少（样本对齐由 caliber_diff 负责）
    VP_CAL = yoy.caliber_diff(VP_N, yoy.FLOW, win=list(VP_MON))
    _vp_adv_tr = (VP_N / _d.reindex(VP_N.index)).astype(float)      # 日均笔数（千笔/日）
    _vp_dg = (VP_N_MOM - yoy.mom_yoy(_vp_adv_tr, yoy.FLOW).reindex(VP_MON)).abs()
    VP_N_DAYGAP_MAX = float(_vp_dg.max())
    VP_N_DAYGAP_MED = float(_vp_dg.median())
    VP_N_DAYGAP_AT = _vp_dg.idxmax()

    # ── 成对性的机器判据 2：计数惯例必须**逐月稳定** ──
    # 官方同一张表里金额列是单边计、笔数列是买卖双边计（docs/verify/enx.md 口径坑 6），
    # 两者相除得到的不是每笔真实成交额，而是它除以一个我们没有独立证据确证的计数因子。
    # 这件事对**绝对水平**是致命的（所以本页一个每笔均值的绝对数都不印），
    # 但对增长分解只有一个前提：那个计数常数**不能中途改**。
    # 检验办法：若某月计数惯例从单边翻成双边（或反过来），每笔均值会在那一个月跳约
    # ln2 ≈ 69.3%。逐月算 |Δln(每笔均值)|，排除并表断点月（那些月覆盖范围本来就变了），
    # 看有没有任何一个月接近 ln2。有 ⇒ 惯例中途改过，这两张图一律不画。
    _r = (VP_V / VP_N).astype(float)
    _dln = np.log(_r).diff()
    _chk = [p for p in VP_MON
            if ok(_dln.get(p, np.nan)) and p not in VP_BRK_VAL and (p - 1) not in VP_BRK_VAL]
    VP_CONV_N = len(_chk)
    VP_CONV_MAX = max(abs(float(_dln[p])) for p in _chk) if _chk else np.nan
    VP_CONV_AT = max(_chk, key=lambda p: abs(float(_dln[p]))) if _chk else None
    VP_LN2 = float(np.log(2))
    # 判据留一半余量：最大单月跳变必须小于 ln2 的一半，才算「没有翻过计数惯例」。
    # 取一半而不是贴着 ln2，是因为翻转月同时还会叠加当月自然波动，可能不是整整 ln2。
    VP_CONV_OK = ok(VP_CONV_MAX) and VP_CONV_MAX < VP_LN2 / 2
    if not VP_CONV_OK:
        VP_WHY.append(f'每笔均值在非断点月里出现过 {VP_CONV_MAX * 100:.1f}% 的单月跳变'
                      f'（{VP_CONV_AT}），已达 ln2={VP_LN2 * 100:.1f}% 的一半以上 —— '
                      '无法排除计数惯例中途改过，增长分解的前提不成立')
        HAS_VP = False

if HAS_VP:
    # ── 年度聚合：只要 12 个月齐全的完整自然年 ──
    _yr = pd.Series([p.year for p in VP_MON], index=VP_MON)
    _cnt = _yr.value_counts()
    VP_YEARS = sorted(y for y in _cnt.index if _cnt[y] == 12)
    VP_GY = [y for y in VP_YEARS if (y - 1) in set(VP_YEARS)]   # 能算同比的年份
    HAS_VP = len(VP_GY) >= 5
    if not HAS_VP:
        VP_WHY.append(f'完整自然年只有 {len(VP_YEARS)} 个，可算同比的年份 {len(VP_GY)} 个，'
                      '不足 5 个，年度分解不画')

# ── 这两张图的图号：**会进 payload 的那一份**只有这一处，正文与 ex.append 都从这里取 ──
# ⚠ 「唯一一处」这四个字要说得起：上一轮写下它的时候，NOTES 颜色那一条里还留着两个裸的
#   「15 的两段」「16 的柱」，当场就被 grep 推翻（今天渲染对，是因为 HAS_VP=True 时
#   15/16 恰好是真号）。两处已改成从 VP_N_DEC / VP_N_TRD 取。**判据（可复跑）**：
#     grep -n "'1[56] \|Exhibit 1[56]" build/exchanges_eu.py
#   命中的行必须**全部**是 `#` 开头的注释（分节标题那种，给读代码的人定位，不进 payload）；
#   只要有一行是字符串字面量，「唯一一处」就已经是假话。
# ⚠ Exhibit 15 / 16 是**有条件生成**的（Euronext 那一对列没过判据就整块不画），
#   而核对表的表号是 `ex[-1]['n'] + 1` 跟着最后一张图走 —— 一停画，**核对表就顺推
#   占用 15 号**。此时正文里任何写死的「Exhibit 15」都会指到核对表上。
#   2026-08-19 用合成缺口（enx.csv 抠掉 2019-03 的金额列）实跑复现过：页面变成
#   「Exhibit 2-14 + Exhibit 15 核对表」，而 NOTES 同时在说「Exhibit 15 做的是成交额
#   分解」「因此 Exhibit 15 / 16 未生成」，Exhibit 13 的图注还在指一张不存在的
#   Exhibit 16。所以：**有图报真号，没图改说名字**，一个错号都不留。
VP_N_DEC, VP_N_TRD = (15, 16) if HAS_VP else (None, None)
EX_DEC = f'Exhibit {VP_N_DEC}' if HAS_VP else '成交额分解图'
EX_TRD = f'Exhibit {VP_N_TRD}' if HAS_VP else '成交笔数图'
EX_VP2 = (f'Exhibit {VP_N_DEC} / {VP_N_TRD}' if HAS_VP
          else '成交额分解与成交笔数那两张图')

if HAS_VP:
    VP_VY = pd.Series({y: float(VP_V[[p for p in VP_MON if p.year == y]].sum())
                       for y in VP_YEARS})
    VP_NY = pd.Series({y: float(VP_N[[p for p in VP_MON if p.year == y]].sum())
                       for y in VP_YEARS})

    def vp_log(v1, v0, n1, n0):
        """对数（LMDI）分解：ln(V₁/V₀) = ln(n₁/n₀) + ln(m₁/m₀)，m = V/n = 每笔均值。

        **本页图上用的就是这一种。** 选它不是口味问题，是算术分解在本页自己的数据上
        画不出来：算术那一路 ΔV = Δn·m₀ + Δm·n₀ + Δn·Δm 剩一个交叉项，
        实测交叉项占 ΔV 的中位数只有几个百分点，但 2020 年那种「笔数暴涨、均值暴跌、
        两头几乎对冲」的年份，交叉项能占到 ΔV 的六成 —— 把它塞进任一侧都是任意分配，
        单独画成第三根柱读者又读不懂。对数分解没有余项，且任何年份都不会失效。

        代价写明：对数增长率不等于简单百分比增长（翻倍在对数里是 +69.3% 而不是 +100%），
        所以本图的菱形是**对数总增长**，简单百分比另在图注给出。
        """
        return np.log(n1 / n0) * 100, np.log((v1 / n1) / (v0 / n0)) * 100, np.log(v1 / v0) * 100

    def vp_bennet(v1, v0, n1, n0):
        """Bennet（对称权重）算术分解，只用来在图注里给出与对数路的差，不上图。"""
        m1, m0 = v1 / n1, v0 / n0
        return ((n1 - n0) * (m1 + m0) / 2 / v0 * 100,
                (m1 - m0) * (n1 + n0) / 2 / v0 * 100,
                (v1 / v0 - 1) * 100)

    def vp_cross(v1, v0, n1, n0):
        """Laspeyres 交叉项 Δn·Δm 占 ΔV 的比例（%）—— 算术分解有多不稳的物证。"""
        m1, m0 = v1 / n1, v0 / n0
        dv = v1 - v0
        return abs((n1 - n0) * (m1 - m0) / dv) * 100 if dv else np.nan

    def vp_all(pairs):
        """pairs = [(标签, V₁, V₀, n₁, n₀)] → 逐列的对数分解 / 算术分解 / 交叉项占比。"""
        lv, lm, lt, bv, bm, bt, cr = [], [], [], [], [], [], []
        for _lab, v1, v0, n1, n0 in pairs:
            a, b, c = vp_log(v1, v0, n1, n0)
            lv.append(a), lm.append(b), lt.append(c)
            a, b, c = vp_bennet(v1, v0, n1, n0)
            bv.append(a), bm.append(b), bt.append(c)
            cr.append(vp_cross(v1, v0, n1, n0))
        return lv, lm, lt, bv, bm, bt, cr

    # 端点一律是 12 个月合计，不是点对点的单月 —— 这张图答的是「这一年 vs 上一年，
    # 增长里有多少来自笔数、多少来自每笔均值」，横轴本来就是年，拿单月当端点等于让
    # 一个异常月替一整年发言。⚠ 这条与本页同比口径**不再是同一条理由**：2026-09 起
    # Exhibit 13 / 14（及本图右边那张的右轴线）已改成单月同比，这里仍是 12 个月端点，
    # 因为两者答的问题不同（那边是逐月读数，这边是年对年分解）。完整自然年天然满足；
    # 末尾再补一列 TTM（截至共同最新月的 12 个月 vs 前 12 个月），否则最新的读数
    # 会比页面其余部分旧上最多 11 个月。
    VP_PAIRS = [(str(y), VP_VY[y], VP_VY[y - 1], VP_NY[y], VP_NY[y - 1]) for y in VP_GY]
    _cur12 = [LATEST - i for i in range(12)]
    _pre12 = [LATEST - 12 - i for i in range(12)]
    HAS_VP_TTM = all(p in set(VP_MON) for p in _cur12 + _pre12)
    if HAS_VP_TTM:
        VP_PAIRS.append((f'TTM {mlab(LATEST)}',
                         float(VP_V[_cur12].sum()), float(VP_V[_pre12].sum()),
                         float(VP_N[_cur12].sum()), float(VP_N[_pre12].sum())))
    VP_LAB = [t[0] for t in VP_PAIRS]
    VP_LV, VP_LM, VP_LT, VP_BV, VP_BM, VP_BT, VP_CR = vp_all(VP_PAIRS)

    # ── 硬护栏 1：恒等式。两块相加逐列等于总增长，差 > 1e-9 直接停 ──
    VP_RES = max(abs(VP_LV[i] + VP_LM[i] - VP_LT[i]) for i in range(len(VP_PAIRS)))
    VP_RES_B = max(abs(VP_BV[i] + VP_BM[i] - VP_BT[i]) for i in range(len(VP_PAIRS)))
    if not (VP_RES < 1e-9 and VP_RES_B < 1e-9):
        raise SystemExit(f'笔数 × 每笔均值分解不闭合：对数残差 {VP_RES:.3e}pp、'
                         f'算术残差 {VP_RES_B:.3e}pp —— 分解式写错了，画出来就是错的')

    # ── 硬护栏 2：汇率不变性。本币与**定基**美元下，贡献值必须逐列完全相同 ──
    # 定基汇率是常数，常数对增长率没有影响 —— 但这句话必须实测，不能只写在图注里。
    # 反过来也要说清：换成**当期**汇率就不成立了，那时序列里混进了汇率的月度波动，
    # 「每笔均值」那一项会变成「每笔均值 + 汇率」的混合物，而图上完全看不出来。
    _u = vp_all([(t[0], t[1] * EURUSD_BASE, t[2] * EURUSD_BASE, t[3], t[4]) for t in VP_PAIRS])
    VP_FX_MAX = max(max(abs(_u[0][i] - VP_LV[i]), abs(_u[1][i] - VP_LM[i]),
                        abs(_u[2][i] - VP_LT[i]), abs(_u[3][i] - VP_BV[i]),
                        abs(_u[4][i] - VP_BM[i])) for i in range(len(VP_PAIRS)))
    if not (VP_FX_MAX < 1e-9):
        raise SystemExit(f'分解在本币与定基美元下不一致，最大差 {VP_FX_MAX:.3e}pp —— '
                         '定基汇率是常数，出现差异说明折算里混进了非常数的东西')

    # ── 硬护栏 3：计数常数不变性。笔数列买卖双边计、金额列单边计 ──
    # 双边计等价于把笔数乘一个常数；分解对数量列乘任何常数都必须完全不变。
    # 这一条 + 上面的「计数惯例逐月稳定」检验一起，才够说明单双边这处口径差
    # **不污染本图任何一个数字**。也正因为它只对「增长」无害，本页一个每笔均值的
    # 绝对水平都不印 —— 那个数确实是不可读的。
    VP_SCALE_MAX = 0.0
    for _c in (2.0, 0.5, 1.234567):
        _s = vp_all([(t[0], t[1], t[2], t[3] * _c, t[4] * _c) for t in VP_PAIRS])
        VP_SCALE_MAX = max(VP_SCALE_MAX,
                           max(max(abs(_s[0][i] - VP_LV[i]), abs(_s[1][i] - VP_LM[i]),
                                   abs(_s[3][i] - VP_BV[i]), abs(_s[4][i] - VP_BM[i]))
                               for i in range(len(VP_PAIRS))))
    if not (VP_SCALE_MAX < 1e-9):
        raise SystemExit(f'分解对数量列的常数缩放不不变，最大差 {VP_SCALE_MAX:.3e}pp —— '
                         '那样单双边计不一致就会污染结果，这两张图不能画')

    VP_AL_MAX = max(max(abs(VP_LV[i] - VP_BV[i]), abs(VP_LM[i] - VP_BM[i]))
                    for i in range(len(VP_PAIRS)))
    VP_LT_B_MAX = max(abs(VP_LT[i] - VP_BT[i]) for i in range(len(VP_PAIRS)))
    VP_CR_MED = float(np.nanmedian(VP_CR))
    VP_CR_MAX = float(np.nanmax(VP_CR))
    VP_CR_AT = VP_LAB[int(np.nanargmax(VP_CR))]
    _dom = list(zip(VP_LAB, VP_LV, VP_LM))
    VP_VOL_YEARS = sum(1 for _l, a, b in _dom if abs(a) > abs(b))
    VP_BIG_V = max(_dom, key=lambda t: abs(t[1]))      # 笔数贡献最极端的一列
    VP_BIG_P = max(_dom, key=lambda t: abs(t[2]))      # 每笔均值贡献最极端的一列
    # 年度柱上的断点：并表发生在哪一年，那一年的「笔数」里就有一块是买来的，不是自然增长。
    VP_BRK_I = [VP_LAB.index(str(x.year)) for x in sorted(VP_BRK_VAL)
                if str(x.year) in VP_LAB]
    VP_BRK_TXT = [BRK_LABEL.get(str(x), '口径断点')
                  for x in sorted(VP_BRK_VAL) if str(x.year) in VP_LAB]
    # 月度笔数图上的断点：与本页其余各图同一套语义（画在该期左缘）。
    VP_BRK_MI = [list(VP_MON).index(x) for x in sorted(VP_BRK_TRD)
                 if x in set(VP_MON) and x > VP_MON[0]]
    VP_BRK_MTXT = [BRK_LABEL.get(str(x), '口径断点') for x in sorted(VP_BRK_TRD)
                   if x in set(VP_MON) and x > VP_MON[0]]
    # Athens 并表在两侧是**反向**的（笔数占比高于金额占比 ⇒ 抬笔数、压每笔均值），
    # 实测印在图注里，免得读者把 2025 那根柱的形状当成 Euronext 自身的结构变化。
    ATH_TRD_COL = 'athex_adv_cash_trades_k'
    ATH_VAL_COL = 'athex_adv_cash_adnv_eurbn'
    VP_ATH = None
    if ATH_TRD_COL in _e.columns and ATH_VAL_COL in _e.columns and ATH_P in set(VP_MON):
        _av = (_e[ATH_VAL_COL].astype(float) * _d).reindex(VP_MON)
        _an = (_e[ATH_TRD_COL].astype(float) * _d).reindex(VP_MON)
        _post = [p for p in VP_MON if p >= ATH_P]
        if _post and all(ok(_av[p]) and ok(_an[p]) for p in _post):
            VP_ATH = (float(sum(_av[p] for p in _post) / sum(VP_V[p] for p in _post) * 100),
                      float(sum(_an[p] for p in _post) / sum(VP_N[p] for p in _post) * 100),
                      len(_post))
else:
    VP_MON, VP_XL, VP_LAB = None, [], []


# ────────────────────────── 8. Exhibit 1：汇总表 ──────────────────────────
DENOM_TXT = ('<b>分母 = 本池三家之和</b>（Euronext + Cboe Europe + Deutsche Börse 的披露口径），'
             '<b>不含 SI（系统内部撮合商）、不含第三方暗池与 OTC、不含 LSEG / Turquoise / '
             'Aquis / SIX 等本池之外的场所</b> —— 因此这一列<b>系统性高估</b>三家在真实泛欧'
             '成交里的比重，只能读作「这三家披露口径之和里谁占多少」。'
             '<b>这一列不是市场份额</b>，页面上凡出现这四个字都是在否定它；'
             '为什么拿不到泛欧合并分母，见页尾第 2 条。')

# 同比口径的说明块（汇总表、Exhibit 13、Exhibit 14、成交笔数图共用一段，措辞一次写死
# 免得各处走样）。数字全部来自 DIAG（= yoy.caliber_diff），即本页自己这三条序列的实测，
# 不是从别的页搬来的。
_sd_lo, _sd_hi = min(SD_RATIO.values()), max(SD_RATIO.values())
_MOM_WHERE = ('Exhibit 13 的热力矩阵与 Exhibit 14 的四条线（建在<b>日均</b>成交额上）'
              + (f'、{EX_TRD} 的右轴线（建在<b>当月合计</b>笔数上，好让线与柱严格对应；'
                 f'两种底料差多少，那张图的图注里单量了一遍）' if HAS_VP else ''))
YOY_TXT = (
    f'<b>口径：本页的同比一律是<u>单月</u>同比</b>（当月 ÷ 去年同月 − 1）—— 全站统一，'
    f'<b>页面所有者指定</b>（<code>build/CONTRACT.md</code> §6 抬头引了原话）。'
    f'在本页它出现在 {_MOM_WHERE}，以及汇总表「现货成交额同比」那一组行与抬头的 y/y。'
    f'<b>代价用本页三家那 {len(DIAG_OK)} 条序列自己实测</b>（每条只取两种口径都算得出的月份，'
    f'样本先对齐；统计量由 <code>build/yoy.py</code> 的 <code>caliber_diff()</code> 出。'
    f'对照的 {ROLL} 个月滚动口径<b>只在图注里以数字出现，抬头与页上一条线都不画</b>，'
    f'且诊断里它按 {ROLL} 个月<b>等权相加</b>算 —— 日均列上这是个近似，'
    f'用来量「两种口径差多远」够了）：'
    f'单月同比的逐月标准差是滚动口径的 <b>{_sd_lo:.2f}–{_sd_hi:.2f} 倍</b>；'
    f'相邻月跳变的中位数逐条落在 <b>{MEDJ1_LO:.1f}–{MEDJ1_HI:.1f}pp</b>，'
    f'滚动口径是 {MEDJ12_LO:.1f}–{MEDJ12_HI:.1f}pp；'
    f'单月口径最大跳变 <b>{JUMP1_MAX:.1f}pp</b>（{SHORT[JUMP1_WHO]}，'
    f'{mlab(DIAG[JUMP1_WHO]["maxjump_mom"][2])}），滚动口径同期最大只有 {JUMP12_MAX:.1f}pp；'
    f'{FLIP_N_TOT} 个成员月里有 <b>{FLIP_TOT} 个'
    f'（{FLIP_TOT / FLIP_N_TOT * 100:.0f}%）两种口径符号相反</b>'
    + (f'，剔掉并表断点污染的月份后最极端的一例是 {SHORT[FLIP_EX[3]]} {mlab(FLIP_EX[0])}：'
       f'单月 {pct(FLIP_EX[1])}、滚动 {pct(FLIP_EX[2])}'
       if FLIP_EX else '') + '。'
    f'<b>⇒ 这几条线要连着水平值一起读</b>：低基数月份它会被放大，'
    f'单看它挑月份能把结论说成两个方向。'
    f'附带两件事同样只是算术：一次并表断点只污染 <b>{ROLL} 个</b>读数'
    f'（滚动口径要污染连续 {2 * ROLL} 个），窗口左端也不再有 {2 * ROLL} 个月画不出线。'
    f'⚠ 一条实现细节，免得上面的数字被读成别的东西：'
    f'<b>成交额的单月同比建在日均上，不建在月度合计上</b>。当月与去年同月的交易日数不同，'
    f'月度合计的单月同比会带一块纯日历效应，本页实测最大 <b>{MOM_DAYGAP_MAX:.1f}pp</b>、'
    f'中位 {MOM_DAYGAP_MED:.1f}pp —— 不是小数点后的事，'
    f'而日均口径把「今年这个月多开几天市」直接除掉了。'
    f'（当期对照，只给数不画线：{mlab(CUR)} 的 {ROLL} 个月滚动合计同比 —— '
    + '、'.join(f'{SHORT[k]} {pct(float(YOY12[k][CUR]))}'
                for k in KEYS if ok(YOY12[k][CUR]))
    + (f'、本池合计 {pct(float(YOY12_TOT[CUR]))}' if ok(YOY12_TOT[CUR]) else '')
    + f'。这一组建在<b>月度成交额</b>链上，与占比、季度图同源，'
      f'比上面诊断里那条等权近似准；页上<b>没有</b>任何一条线画它。）')

SUM_ROWS = [
    ('group', '现货成交额 — 日均（€bn/日，官方披露口径）', None, None, None),
] + [('row', DISP[k], ('A', k), 2, 'num') for k in KEYS] + [
    ('row', '本池三家合计', ('AT', None), 2, 'num'),
    ('group', '现货成交额同比 —— <b>单月</b>同比（%，当月 ÷ 去年同月 − 1，建在日均上）；'
              '三家同币种，里面没有汇率',
     None, None, None),
] + [('row', f'{SHORT[k]} y/y（单月）', ('Y', k), 1, 'growth') for k in KEYS] + [
    ('row', '本池三家合计 y/y（单月）', ('YT', None), 1, 'growth'),
    ('group', '池内相对占比（%）— 分母 = 本池三家之和，不是泛欧市场', None, None, None),
] + [('row', SHORT[k], ('S', k), 2, 'share') for k in KEYS] + [
    ('group', '美元口径对照（把同一批欧元读数折成美元）', None, None, None),
    ('row', f'本池合计（定基汇率，锁 {mlab(BASE_P)}；USD bn/日）', ('BU', None), 2, 'num'),
    ('row', '本池合计（当期月均汇率；USD bn/日）', ('CU', None), 2, 'num'),
    ('row', f'汇率贡献（当期 ÷ 定基 − 1，%）≡ EUR/USD 相对 {mlab(BASE_P)} 的累计变动',
     ('FXC', None), 2, 'growth'),
]
if HAS_NDAQ:
    SUM_ROWS += [
        ('group', '参照（不进本页任何份额）', None, None, None),
        ('row', 'Nasdaq 北欧现货（当月合计，US$bn；口径 = 瑞典/丹麦/芬兰/冰岛）',
         ('ND', None), 1, 'num'),
    ]

# 'Y' / 'YT' 指向 YOY 而不是 YOY12：2026-09 起**全站同比只有单月一种口径**
# （CONTRACT §6，页面所有者指定），本表这一组随 Exhibit 13 / 14 一起换成了单月同比。
# ⚠ 换完之后这一组与「本月 vs 去年同月」那一列在成交额行上是**同一个数**（都是当月 ÷
#   去年同月 − 1，都建在日均上）—— 这不是冗余：那一列只印最新一个月，这一组还带
#   上月 / 去年同月的同比读数与 3Y %ile，答的是「这条同比线自己在什么位置」。
#   姊妹页 exchanges-apac 的汇总表本轮也是这个结构（「… y/y（单月）」）。
# 对照的 12 个月滚动口径**只在图注里以数字出现，页上一条线都不画**（§6.1 第 3 条），
# 数据仍由 YOY12 / YOY12_TOT 提供 —— 那两条建在月度成交额链上，比诊断里那条
# 「12 个日均等权相加」的近似更准，所以拿它出对照数。
SERIES_OF = {'A': lambda k: ADV[k], 'Y': lambda k: YOY[k], 'S': lambda k: SHARE[k],
             'AT': lambda k: ADV_TOT, 'YT': lambda k: YOY_TOT,
             'BU': lambda k: BASE_USD, 'CU': lambda k: CURR_USD,
             'FXC': lambda k: FX_CONTRIB, 'ND': lambda k: NORD_USD}


def ser_of(s):
    """pandas Series → pctile.py 吃的「按月升序、缺失为 None」的 float 列表。

    NaN 不能直接喂：pctile 里 `v is not None` 会把 NaN 当有效样本收进 hist，
    而 NaN 的比较恒为 False，分位会被悄悄压低。
    """
    return [None if not ok(v) else float(v) for v in s.values]


def lvl(v, dec, mode):
    if not ok(v):
        return '—'
    if mode == 'growth':
        return f'{_z(v, dec):+,.{dec}f}%'
    if mode == 'share':
        return f'{float(v):,.{dec}f}%'
    return f'{float(v):,.{dec}f}'


def cls_of(v):
    if not ok(v):
        return ''
    return 'pos' if v > 0 else ('neg' if v < 0 else '')


def summary():
    rows, blank_why = [], []
    for kind, label, ref, dec, mode in SUM_ROWS:
        if kind == 'group':
            rows.append({'kind': 'group', 'label': label})
            continue
        s = SERIES_OF[ref[0]](ref[1])
        c, p1, p12 = (float(s.get(CUR, np.nan)), float(s.get(PRV, np.nan)),
                      float(s.get(YAG, np.nan)))
        if mode == 'num':
            mm = (c / p1 - 1) * 100 if ok(c) and ok(p1) and p1 else np.nan
            yy = (c / p12 - 1) * 100 if ok(c) and ok(p12) and p12 else np.nan
            dm, dy = pct(mm), pct(yy)
        else:                                    # 比率类：差异一律 pp/bp（契约 §2）
            mm = c - p1 if ok(c) and ok(p1) else np.nan
            yy = c - p12 if ok(c) and ok(p12) else np.nan
            dm, dy = pp(mm), pp(yy)
        cells = [{'v': lvl(c, dec, mode)}, {'v': lvl(p1, dec, mode)}, {'v': lvl(p12, dec, mode)},
                 {'v': dm, 'cls': cls_of(mm)}, {'v': dy, 'cls': cls_of(yy)}]
        ser = ser_of(s)
        txt_, cls_ = pctile.cell(ser)
        cells.append({'v': txt_, 'cls': cls_} if txt_ else {'v': ''})
        if not txt_:
            blank_why.append((label, pctile.why_blank(ser)))
        rows.append({'label': label, 'cells': cells})
    blank_txt = ('本轮留空：' + '；'.join(f'{lab}（{why}）' for lab, why in blank_why) + '。'
                 ) if blank_why else '本轮各行均未触发留空，分位照算。'
    return {
        'title': f'欧洲现货股票竞争 — {mlab(CUR)}（共同最新月）',
        # 列名从 m/m / y/y 改成中文全称：这两列永远是**本行自己展示的三个读数之间的
        # 算术**（本行的三个数相除），与「同比那一组行」是两回事 —— 那一组行是一条
        # 完整的同比序列，还带 3Y %ile。2026-09 改口径后两者在成交额行上碰巧是同一个数，
        # 名字仍要自带区分：占比行、汇率行上它们不是同比，是 pp 差。
        'heads': [f'本月 {mlab(CUR)}', f'上月 {mlab(PRV)}', f'去年同月 {mlab(YAG)}',
                  '本月 vs 上月', '本月 vs 去年同月', '3Y %ile'],
        'sep': 3,
        'rows': rows,
        'note': ('三家<b>全部以欧元披露</b>，所以本页的占比与同比里<b>一点汇率都没有</b> —— '
                 '这是本页相对其它横截面页的结构性优势，美元那一组只是把同一批欧元读数'
                 '换个单位给人看量级。' + DENOM_TXT +
                 '⚠ 三家的<b>涵盖范围并不一致</b>：Euronext 与 Cboe Europe 逐字同口径'
                 '（股票 ADNV、单边计），Deutsche Börse 这条含 ETP / 结构化产品 / 债券 / 基金，'
                 '比另两家宽 —— 高估幅度已实测，见 Exhibit 12。'
                 + YOY_TXT +
                 '📌 <b>「本月 vs 上月」「本月 vs 去年同月」两列是本行自己那三个读数之间的'
                 '算术</b>（本行的三个数相除，运营监控要的就是这个）。'
                 '在<b>成交额那一组行</b>上，「本月 vs 去年同月」与下面「现货成交额同比」'
                 '那一组行、与 Exhibit 13 / 14 <b>是同一个数</b>（都是当月 ÷ 去年同月 − 1，'
                 '都建在日均上）—— 那一列只印最新一个月，同比那一组行还带上月 / 去年同月的'
                 '同比读数与 3Y %ile。'
                 '在<b>占比行、汇率行与同比那一组行</b>上这两列则不是同比，是 <b>pp 差</b>'
                 '（那几行本身已经是百分比，再相除没有意义）—— 所以列名保留中文全称、'
                 '不写 m/m 与 y/y：同一列在不同的行上是不同的东西，名字不能只对一半的行成立。'
                 '占比与同比读数本身已是百分比，其变化用 pp/bp（绝对值不足 1pp 时写 bp）；'
                 '水平值的变化用百分比。'
                 '3Y %ile = 该读数在最近 36 个月里高于多少百分比的观测，'
                 '判据与留空规则由全站唯一实现 <code>build/pctile.py</code> 给出。' + blank_txt),
    }


# ────────────────────────── 9. Exhibit 2..13 ──────────────────────────
ex = []


def rebase(s, base=None):
    """归一到基期 = 100。"""
    b = float(s.get(base or START, np.nan))
    if not ok(b) or b == 0:
        raise SystemExit(f'基期 {base or START} 无有效值，无法指数化')
    return s / b * 100


# ── Exhibit 2：月度池内占比堆叠带 ──
_db1_share_max = float(SHARE['db1'].max())
ex.append({
    'n': 2, 'kind': 'stacked_dual', 'full': True, 'height': 340,
    'fmt': 'f2', 'xstep': 6, 'xrot': 90,
    'xlabels': XL_LONG,
    'title': f'Pool share of European cash-equity turnover, {mlab(START)} – {mlab(LATEST)}',
    'ylab': '% of pool（左，堆叠；分母 = 本池三家之和）',
    'ylab2': 'Deutsche Börse, %（右，同一条序列换个刻度）',
    'stacks': [{'name': SHORT[k], 'color': COLOR[k], 'values': L(SHARE[k].values),
                'label': False} for k in KEYS],
    'line': {'name': 'Deutsche Börse（RHS）', 'color': TOTAL_C,
             'values': L(SHARE['db1'].values),
             'ymax': nice_max(_db1_share_max * 1.15)},
    'break_at': ENX_BRK_I, 'break_label': ENX_BRK_TXT,
    'src_extra': ('Monthly shares are built on turnover, not on ADV; denominator = the three '
                  'members summed. There is no published pan-European consolidated total that '
                  'includes SIs and dark venues'),
    'note': ('堆叠三段之和<b>恒为 100%</b>（本池没有残差段：分母就是这三家之和，'
             '不存在「其余场所」这一块 —— 而真实的泛欧成交里那一块很大，'
             '这正是本页不把它叫作市场份额的原因）。'
             '<b>占比建在当月实际成交额上，不建在 ADV 上</b>：德国交易所在 12/24、12/31 '
             f'与圣灵降临节休市，窗口内 {DAYS_N - DAYS_SAME}/{DAYS_N} 个月 Deutsche Börse 的'
             '交易日比 Euronext 少 1–2 天，而 ADV = 成交额 ÷ 各自交易日 —— 照 ADV 算占比'
             f'等于给休市多的那家加权，实测最大虚高 <b>{SHARE_ADV_MAXGAP:.2f}pp</b>（落在 12 月，'
             '每年复发一次，看上去像季节性规律）。本图与 Exhibit 3 的季度线同一条链，'
             '重叠处严格自洽。'
             + DENOM_TXT +
             f'{mlab(START)} → {mlab(CUR)}：'
             + '、'.join(f'{SHORT[k]} {float(SHARE[k][START]):.1f}% → '
                         f'{float(SHARE[k][CUR]):.1f}%'
                         f'（{pp(float(SHARE[k][CUR]) - float(SHARE[k][START]))}）'
                         for k in KEYS) + '。'
             '右轴那条线是<b>同一条 Deutsche Börse 占比序列换一个刻度</b>，'
             '不是第四个东西 —— 最小的一段在 0–100 的堆叠里读不出几个 pp 的变化。'
             '段内不标数值（引擎的段内标签写死 6.6px，白字压在深色段上会糊成白斑）。'
             '⚠ 本卡的「表格」视图里堆叠段被<b>引擎写死成整数</b>'
             '（<code>charts.js</code> 对 stacked_dual 的段固定用 f0c，payload 改不了），'
             '所以那里读到的是 40 / 38 / 22 而不是两位小数 —— '
             '要两位小数请看 Exhibit 1 汇总表，要长期走向请看 Exhibit 3 的季度线。'
             + (f'红色竖虚线 = Euronext 的口径断点（{"、".join(ENX_BRK_TXT)}），'
                '线右侧与左侧不可比；断点月份来自 <code>series/enx_breaks.csv</code>'
                '（官方脚注的机器可读副本），不是代码里写死的。'
                if ENX_BRK_I else '本页窗口内没有可画的口径断点。')
             + (f'⚠ {ENX_BRK_WHY}。' if ENX_BRK_WHY else '')),
})

# ── Exhibit 3：季度口径的长历史份额（本页最该被读到的一张）──
_q0, _q1 = QIDX[0], QIDX[-1]
ex.append({
    'n': 3, 'kind': 'lines', 'full': True, 'height': LINE_H_ENDLABEL,
    'fmt': 'f1', 'yfmt': 'f0', 'xstep': 2, 'xrot': 90, 'markers': False,
    'zero_base': True, 'end_label': True, 'label_fmt': 'f1',
    'xlabels': QLAB,
    'title': f'Pool share, quarterly and volume-weighted — {qlab(_q0)} to {qlab(_q1)}',
    'ylab': '% of pool（分母 = 本池三家之和）',
    'series': [{'name': SHORT[k], 'color': COLOR[k], 'values': L(QSHARE[k].values)}
               for k in KEYS],
    'break_at': QBRK_I, 'break_label': QBRK_TXT,
    'src_extra': ('Quarterly shares are volume-weighted (sum of the quarter\'s monthly turnover, '
                  'not the average of three monthly shares)'),
    'note': ('月度占比太吵，结构性趋势要在季度上看。'
             f'本图 <b>{len(QIDX)} 个完整季（{qlab(_q0)} – {qlab(_q1)}，约 {QSPAN_Y:.1f} 年）</b>，'
             + (f'<b>不足十年</b> —— 上限是 Cboe Europe 的披露起点 {mlab(START)}，'
                f'再往前这个池只有两家，换分母的图不能与右半段放在同一条线上。'
                if QSPAN_Y < 10 else '')
             + '<b>量加权</b>：季度占比 = 该季三个月成交额之和 ÷ 该季池合计，'
             '不是三个月占比的算术平均 —— 平均会让 18 个交易日的 12 月与 23 天的 3 月等权，'
             '把日历噪音读成份额变化。'
             f'月长权重取 Euronext 的 <code>trading_days_cash</code>（欧元区口径），'
             f'它与 Deutsche Börse 同名列在窗口内 <b>{DAYS_SAME}/{DAYS_N} 个月完全相同</b>；'
             'Deutsche Börse 那一列本身就是官方原生的月度总额，不经这个权重。'
             '残季（本页窗口两端不满三个月的那一季）一律不画，不做年化。'
             + DENOM_TXT
             + (f'红色竖虚线 = Euronext 口径断点（{"、".join(QBRK_TXT)}），落在该断点所在季。'
                if QBRK_I else '')),
})

# ── Exhibit 4：同比同月份额，剔季节性 ──
_yy_years = []
for i in range(YOY_YEARS - 1, -1, -1):
    p = CUR - 12 * i
    if p in set(IDX) and all(ok(SHARE[k][p]) for k in KEYS):
        _yy_years.append(p)
_yy_pal = ['GRAY', 'BLUE', 'MBLUE', 'NAVY'][-len(_yy_years):] if _yy_years else []
if len(_yy_years) >= 3:
    _yy_note_rows = '；'.join(
        f'{SHORT[k]} ' + ' → '.join(f'{float(SHARE[k][p]):.1f}%' for p in _yy_years)
        for k in KEYS)
    ex.append({
        'n': 4, 'kind': 'grouped_bars', 'height': 300,
        'fmt': 'f1', 'label_fmt': 'f1', 'bar_labels': True, 'xrot': 0, 'xstep': 1,
        'title': f'Same month, {len(_yy_years)} years — seasonality removed',
        'ylab': '% of pool',
        'xlabels': [SHORT[k] for k in KEYS],
        'groups': [{'name': mlab(p), 'color': c,
                    'values': L([float(SHARE[k][p]) for k in KEYS])}
                   for p, c in zip(_yy_years, _yy_pal)],
        'src_extra': (f'Same calendar month in {len(_yy_years)} consecutive years, so the '
                      'holiday and expiry calendar is held constant'),
        'note': ('拿同一个日历月的连续几年并排，季节性（假期、到期日、指数再平衡）被固定住，'
                 '剩下的差就是结构变化。'
                 f'{mlab(_yy_years[0])} → {mlab(_yy_years[-1])}：{_yy_note_rows}。'
                 f'<b>只画 {len(_yy_years)} 年是引擎的硬上限</b> —— grouped_bars 的组色循环'
                 '只有 4 个，第 5 组开始与第 1 组撞色，读者分不出哪根是哪年。'
                 '更长的历史看 Exhibit 3 的季度线。'
                 + DENOM_TXT),
    })

# ── Exhibit 5：份额变化排序（单色，见 docs/CHART_KINDS.md §3.4 为什么不用 diverging_bars）──
_dsh = sorted(((k, float(QSHARE[k].iloc[-1]) - float(QSHARE[k].iloc[0])) for k in KEYS),
              key=lambda kv: -kv[1])
ex.append({
    'n': 5, 'kind': 'grouped_bars', 'height': 300,
    'fmt': 'pp1', 'label_fmt': 'pp1', 'bar_labels': True, 'xrot': 0, 'xstep': 1,
    'title': f'Change in pool share, {qlab(_q0)} → {qlab(_q1)} (pp)',
    'ylab': 'pp',
    'xlabels': [SHORT[k] for k, _ in _dsh],
    'groups': [{'name': f'占比变化 {qlab(_q0)} → {qlab(_q1)}（pp）', 'color': 'NAVY',
                'values': L([v for _, v in _dsh])}],
    'src_extra': 'The three bars sum to zero by construction — the denominator is the pool itself',
    'note': ('<b>三根柱之和恒为 0</b>：分母就是这三家，一家多一分必然有人少一分。'
             '正因为如此，这张图<b>只能读作三家之间的相对移动</b>，'
             '不能读作「谁从整个欧洲市场里拿走了份额」—— 真实的泛欧成交里还有 SI、'
             '暗池与本池之外的场所，那一块的进出完全不在这张图里。'
             '单色不分正负是刻意的：引擎的 <code>diverging_bars</code> 把 COST 的业务文案'
             '（「油汇顺风 / 油汇拖累」）写死在图例与表格列名里，'
             '交易所页上会凭空冒出「油汇」两个字（详见 <code>docs/CHART_KINDS.md</code> §3.4）；'
             '按变化降序排之后，正负分界一眼就在，不靠颜色。'
             '两端取的是<b>季度</b>值（Exhibit 3 的首尾），不是单月，免得端点撞上一个噪音月。'),
})

# ── Exhibit 6：定基名义额指数化增长对比 ──
_idx_now = {k: float(rebase(ADV[k], BASE_P)[CUR]) for k in KEYS}
_lead = max(_idx_now.items(), key=lambda kv: kv[1])
_lagr = min(_idx_now.items(), key=lambda kv: kv[1])
ex.append({
    'n': 6, 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H_ENDLABEL,
    'fmt': 'f0', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'markers': False,
    'zero_base': True, 'end_label': True, 'label_fmt': 'f0',
    'title': f'Turnover growth, base-locked USD notional — rebased to {mlab(BASE_P)} = 100',
    'ylab': f'index, {mlab(BASE_P)} = 100',
    'series': [{'name': SHORT[k], 'color': COLOR[k],
                'values': L(rebase(ADV[k], BASE_P).values)} for k in KEYS]
              + [{'name': '本池三家合计', 'color': TOTAL_C,
                  'values': L(rebase(ADV_TOT, BASE_P).values)}],
    'break_at': ENX_BRK_I, 'break_label': ENX_BRK_TXT,
    'src_extra': ('Local-currency turnover converted at the fixed Jan-2019 average EUR/USD rate, '
                  'then rebased. All three report in euro, so the constant cancels entirely'),
    'note': ('定基名义额 = 本币成交额 × <b>锁死的 2019-01 月均汇率</b>。'
             '本页三家全部以欧元披露 ⇒ 那个汇率对每一家都是<b>同一个常数</b>，'
             '<b>这张图与直接画欧元成交额的指数图逐点相同</b>，一分钱汇率都没混进来。'
             f'基期取 {mlab(BASE_P)}（全仓统一基期），而本页窗口自 {mlab(START)} 起，'
             f'所以 {mlab(BASE_P)} 之前的一段线在 100 附近上下是正常的，不是错。'
             f'{mlab(CUR)} 累计领先 <b>{SHORT[_lead[0]]}（{_lead[1]:,.0f}）</b>、'
             f'落后 {SHORT[_lagr[0]]}（{_lagr[1]:,.0f}）；'
             f'本池合计 {float(rebase(ADV_TOT, BASE_P)[CUR]):,.0f}。'
             '⚠ 增长率的比较不受口径宽窄影响（宽口径只是整条线乘一个常数），'
             '所以 Deutsche Börse 那条线在<b>这张图上是可比的</b>，'
             '而它在占比图上是高估的 —— 两件事不要混。'
             + (f'红色竖虚线 = Euronext 口径断点（{"、".join(ENX_BRK_TXT)}）：'
                '并表当月那条线会跳一档，那不是成交增长。' if ENX_BRK_I else '')),
})

# ── Exhibit 7：两种汇率口径 ──
_g_base = (float(BASE_USD[CUR]) / float(BASE_USD[START]) - 1) * 100
_g_curr = (float(CURR_USD[CUR]) / float(CURR_USD[START]) - 1) * 100
ex.append({
    'n': 7, 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H_ENDLABEL,
    'fmt': 'f1', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'markers': False,
    'zero_base': True, 'end_label': True, 'label_fmt': 'f1',
    'title': 'Pool total in USD, two FX bases — the gap IS the currency effect',
    'ylab': 'USD bn/day',
    'series': [
        {'name': f'定基汇率（锁 {mlab(BASE_P)} 月均 EUR/USD）', 'color': 'NAVY',
         'values': L(BASE_USD.values)},
        {'name': '当期汇率（每月月均 EUR/USD）', 'color': CUR_FX_C,
         'values': L(CURR_USD.values)},
    ],
    'src_extra': ('Identical euro inputs; the only difference is which month\'s EUR/USD is '
                  'applied. Every growth and share exhibit on this page uses euro directly'),
    'note': ('两条线的<b>欧元输入完全相同</b>，唯一差别是用哪个月的 EUR/USD —— '
             f'所以两者之差就是汇率贡献本身。自 {mlab(START)} 起：定基口径 {pct(_g_base)}，'
             f'当期汇率口径 {pct(_g_curr)}，{mlab(CUR)} 当期 ÷ 定基 = '
             f'{pct(float(FX_CONTRIB[CUR]), 2)}。'
             '<b>这张图只回答「按哪个汇率折，这个市场看上去多大」</b>；'
             '本页的增长图与占比图一律直接用欧元，压根不经过汇率这一跳，'
             '所以那些图上不存在「欧元贬了所以份额变了」这种事。'
             '当期那条线<b>不进任何增长或占比图</b> —— 它的同比里混着汇率波动。'),
})

# ── Exhibit 8：汇率恒等式自检 ──
ex.append({
    'n': 8, 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H_ENDLABEL,
    'fmt': 'f2', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'markers': False,
    'zero_line': True, 'end_label': True, 'label_fmt': 'f1',
    'title': 'Self-check: the two-basis gap must equal the EUR/USD move, exactly',
    'ylab': f'% vs {mlab(BASE_P)}',
    'series': [
        {'name': '池合计：当期口径 ÷ 定基口径 − 1', 'color': 'NAVY',
         'values': L(FX_CONTRIB.values)},
        {'name': f'EUR/USD 相对 {mlab(BASE_P)} 的累计变动', 'color': CUR_FX_C,
         'values': L(FX_MOVE.values)},
    ],
    'src_extra': 'ECB SDMX monthly average EUR/USD. Two lines, one identity — they must overlap',
    'note': ('<b>这张图上只看得见一条线，那正是它要证明的事。</b>'
             '本页的池是单一币种池（三家都报欧元），所以「两种汇率口径的差」在数学上'
             '<b>恒等于</b> EUR/USD 自身的累计变动 —— 两条线必须逐点重合。'
             f'实测最大偏差 <b>{FX_IDENT_MAX:.2e} pp</b>（浮点舍入量级），恒等式成立。'
             '若哪天这两条线分开了，说明池里混进了一个非欧元成员，'
             '而那时本页所有占比图都必须停掉：分子分母的币种不同，占比是假的。'
             f'{mlab(CUR)}：EUR/USD 相对 {mlab(BASE_P)} {pct(float(FX_MOVE[CUR]), 2)}。'),
})

# ── Exhibit 9：Nasdaq 北欧的绝对值对比（不进份额）──
if HAS_NDAQ:
    _xl_nd = [mlab(p) for p in W_ND]
    _nd_now, _cb_now = float(NORD_EUR[_ND_OK[-1]]), float(MONTHLY_EUR['cboe'][_ND_OK[-1]])
    ex.append({
        'n': 9, 'kind': 'lines', 'full': True, 'height': LINE_H_ENDLABEL,
        'fmt': 'f0', 'yfmt': 'f0', 'xstep': 2, 'xrot': 90, 'markers': False,
        'zero_base': True, 'end_label': True, 'label_fmt': 'f0',
        'xlabels': _xl_nd,
        'title': 'Nasdaq Nordic vs the three, in absolute terms (€bn per month)',
        'ylab': '€bn/月（当月合计）',
        'series': [{'name': SHORT[k], 'color': COLOR[k],
                    'values': L([float(MONTHLY_EUR[k][p]) for p in W_ND])} for k in KEYS]
                  + [{'name': 'Nasdaq 北欧（瑞典/丹麦/芬兰/冰岛）', 'color': NDAQ_C,
                      'values': L([float(NORD_EUR[p]) for p in W_ND])}],
        'src_extra': ('Monthly totals, not ADV: Nasdaq publishes a month total and does not '
                      'publish Nordic trading days, so a daily average cannot be derived'),
        'note': (ND_WIN_NOTE +
                 '<b>Nasdaq 北欧只出现在这张图与下一张，绝不进本页任何份额的分子或分母。</b>'
                 '它的可比性只有一层：绝对值。'
                 f'{mlab(_ND_OK[-1])}：Nasdaq 北欧 €{_nd_now:,.0f}bn/月，'
                 f'Cboe Europe €{_cb_now:,.0f}bn/月 —— 前者是后者的 '
                 f'<b>1/{_cb_now / _nd_now:.1f}</b>'
                 f'（窗口内该倍数 {ND_RT_MIN:.1f}–{ND_RT_MAX:.1f}，中位 {ND_RT_MED:.1f}）。'
                 '<b>为什么用「月」不用「日」</b>：Nasdaq 官方发的是当月合计，'
                 '且<b>不披露北欧交易日</b>（📌 未找到：IR 月报与季度面板都没有这个字段），'
                 '硬转 ADV 需要一个我们没有的日历。'
                 '所以这里把另外三家也乘回月度总额 —— Deutsche Börse 那条本来就是官方月度总额，'
                 'Euronext 用它自己的 <code>trading_days_cash</code>，'
                 f'Cboe Europe 借用同一列（欧元区口径，与 Deutsche Börse 同名列 '
                 f'{DAYS_SAME}/{DAYS_N} 个月相同）。'
                 '⚠ Nasdaq 的读数原生是美元，这里按当月月均 EUR/USD 折成欧元；'
                 '结论对汇率与交易日的假设都不敏感 —— 差的是三四倍，不是几个百分点。'),
    })

# ── Exhibit 10：分母对撞 —— 为什么两家的「份额」不可并排 ──
if HAS_NDQ:
    ex.append({
        'n': 10, 'kind': 'grouped_bars', 'full': True, 'height': 340,
        'fmt': 'f0', 'label_fmt': 'f0', 'bar_labels': False, 'xrot': 90, 'xstep': 1,
        'title': 'Why the two "European market shares" cannot be compared: the denominators',
        'ylab': 'US$bn/季（当期汇率）',
        'xlabels': [qlab(q) for q in QN],
        'groups': [
            {'name': 'Nasdaq 北欧现货成交额（自报）', 'color': NDAQ_C,
             'values': L(ND_QV.values)},
            {'name': 'Nasdaq 自报份额反推的整个「欧洲市场」分母', 'color': 'BLUE',
             'values': L(ND_QD.values)},
            {'name': 'Cboe Europe 一家的成交额', 'color': COLOR['cboe'],
             'values': L(CB_Q_USD.values)},
        ],
        'src_extra': ('Implied denominator = Nasdaq\'s own reported Nordic turnover divided by '
                      'its own reported share. Cboe Europe converted at the current monthly '
                      'average EUR/USD, same basis as Nasdaq\'s USD figures'),
        'note': ('这是一张算术图，不是观点图。Nasdaq 自报的欧洲现货市占本轮是 '
                 f'<b>{ND_SHARE_LAST:.1f}%</b>（{qlab(QN[-1])}），'
                 '拿它自己的成交额一除就得到它心里那个「欧洲市场」有多大 —— '
                 f'而 <b>Cboe Europe 一家的成交额是那个分母的 {ND_QR_MED:.1f} 倍</b>'
                 f'（窗口内 {ND_QR_MIN:.1f}–{ND_QR_MAX:.1f} 倍）。'
                 '原因不神秘：Nasdaq 那个份额的口径是<b>北欧+波罗的海</b>，'
                 'NDAQ 2026Q1 8-K EX-99.1 脚注 7 原文写着 "European cash equities markets '
                 'include cash equities exchanges of Sweden, Denmark, Finland, and Iceland"；'
                 'Cboe Europe 的份额是<b>泛欧</b>口径。两个分母是两个不同的宇宙。'
                 '<b>把这两个百分数并排放，会得出「Nasdaq 是 Cboe 的三倍」这个完全反的结论</b>'
                 '（实际关系见 Exhibit 9：Nasdaq 北欧只有 Cboe 的四分之一上下）。'
                 '所以本页的规矩是：Nasdaq 的<b>绝对值可比、份额不可比</b>，'
                 '它一个字都不进本页的份额图。'),
    })

# ── Exhibit 11：把 2025-11 的并表断点定量还原 ──
if HAS_ATH:
    _h_at = float(ENX_HEAD.get(ATH_P, np.nan))
    _x_at = float(ENX_EXATH.get(ATH_P, np.nan))
    _prev = float(ENX_HEAD.get(ATH_P - 1, np.nan))
    _mm_head = (_h_at / _prev - 1) * 100 if ok(_h_at) and ok(_prev) and _prev else np.nan
    _mm_ex = (_x_at / _prev - 1) * 100 if ok(_x_at) and ok(_prev) and _prev else np.nan
    _sh_txt = ''
    if CUR in _sh_ath:
        _a, _b = _sh_ath[CUR]
        _sh_txt = (f'折成池内占比：{mlab(CUR)} Euronext 主列口径 {_a:.1f}%、'
                   f'剔除 Athens 后 {_b:.1f}%（{pp(_a - _b)}）—— '
                   '并表把占比抬高了这么多，而不是成交多了这么多。')
    ex.append({
        'n': 11, 'kind': 'lines', 'full': True, 'height': LINE_H_ENDLABEL,
        'fmt': 'f2', 'yfmt': 'f1', 'xstep': 3, 'xrot': 90, 'markers': False,
        'zero_base': True, 'end_label': True, 'label_fmt': 'f2',
        'title': 'Euronext: headline vs like-for-like ex-Athens (€bn/day)',
        'ylab': '€bn/day',
        'xlabels': [mlab(p) for p in W_ATH],
        # 顺序刻意让灰线先画、主列后画：断点之前两条完全重合，谁后画谁在上层，
        # 而应当留在上层的是**官方主列**（本页其余各图用的都是它）。
        'series': [
            {'name': '剔除 Athens 备注列（与并表前同口径）', 'color': CUR_FX_C,
             'values': L(ENX_EXATH.values)},
            {'name': '官方主列（2025-11 起含 Athens）', 'color': COLOR['enx'],
             'values': L(ENX_HEAD.values)},
        ],
        'break_at': ATH_BRK_I, 'break_label': '并表 Athens',
        'src_extra': ('Euronext publishes Athens as a separate memo column, so this one break can '
                      'be undone exactly rather than merely flagged'),
        'note': ('<b>红线左侧只看得见一条线，那是对的</b> —— 并表之前 Athens 还没进主列，'
                 '两条线<b>完全重合</b>（此时去减备注列就是把它减了两次，会画出一道'
                 '全程存在的假缺口）；分岔只在红线右侧。'
                 '口径断点通常只能标出来，这一个可以<b>算清楚</b>：'
                 f'{mlab(CUR)} Athens 占 Euronext 主列 <b>{ATH_PCT_NOW:.1f}%</b>；'
                 f'断点当月（{mlab(ATH_P)}）主列 m/m {pct(_mm_head)}，'
                 f'剔除 Athens 后 {pct(_mm_ex)}。' + _sh_txt +
                 f'⚠ 备注列自 {mlab(W_ATH[0])} 才有，更早的历史没有还原条件；'
                 '2021-05 的 Borsa Italiana 并表<b>没有</b>对应备注列，'
                 '只能在图上标断点，无法定量还原。'
                 '<b>本页其余各图用的都是官方主列</b>（不做私自还原）—— '
                 '这张图的作用是告诉读者那道断点值多少钱。'),
    })

# ── Exhibit 12：Deutsche Börse 宽窄口径 —— 本页最大一处妥协的价码 ──
if HAS_NAR_WIN:
    _xl_nar = [mlab(p) for p in W_NAR]
    ex.append({
        'n': 12, 'kind': 'lines', 'full': True, 'height': LINE_H_ENDLABEL,
        'fmt': 'f2', 'yfmt': 'f1', 'xstep': 2, 'xrot': 90, 'markers': False,
        'zero_base': True, 'end_label': True, 'label_fmt': 'f2',
        'xlabels': _xl_nar,
        'title': 'What the Deutsche Börse scope compromise costs (€bn/day)',
        'ylab': '€bn/day',
        'series': [
            {'name': '本页用的宽口径：Xetra + Börse Frankfurt 全部现货', 'color': COLOR['db1'],
             'values': L([float(ADV['db1'][p]) for p in W_NAR])},
            {'name': '与另两家逐字同口径的窄口径：Xetra 股票 + FWB 股票', 'color': CUR_FX_C,
             'values': L([float(DB1_NARROW_ADV[p]) for p in W_NAR])},
        ],
        'src_extra': ('The narrow columns start only in Dec-2024, which is why the page runs on '
                      'the wide one; this exhibit measures the price of that choice'),
        'note': ('这张图不讲业务，只讲<b>本页最大的一处妥协值多少钱</b>。'
                 'Euronext 与 Cboe Europe 报的是股票 ADNV；Deutsche Börse 与之逐字同口径的'
                 f'两列<b>有数的月份只有 {len(_NAR_OK)} 个</b>，而且不连续 —— '
                 f'它们散落在 {mlab(W_NAR[0])} 至 {mlab(W_NAR[-1])} 这 {len(W_NAR)} 个月里'
                 f'（{_NAR_GAP_TXT}）。横轴按月逐格铺开、缺月断笔，'
                 f'<b>不是</b>把有数的月并排画在一起（那会让相隔数年的两点看着像相邻月）。'
                 f'所以本页用的是有 {DB1_WIDE_N} 个月历史（{DB1_WIDE_FROM} 起）的宽口径'
                 f'（含 ETP / 结构化产品 / 债券 / 基金）。'
                 f'代价实测：这 {len(_NAR_OK)} 个重叠月里宽 ÷ 窄 = '
                 f'<b>{SCOPE_MIN:.2f}–{SCOPE_MAX:.2f} 倍</b>（中位 {SCOPE_MED:.2f}）；'
                 f'折成池内占比，Deutsche Börse 被<b>高估 {SH_GAP_MIN:.1f}–{SH_GAP_MAX:.1f}pp</b>'
                 f'（中位 {SH_GAP_MED:.1f}pp）。'
                 + (f'{mlab(_NAR_OK[-1])} 窄口径下三家占比会是 '
                    + '、'.join(f'{SHORT[k]} {NAR_SHARE_NOW[k]:.1f}%' for k in KEYS)
                    + '，而本页各图印的是 '
                    + '、'.join(f'{float(SHARE[k][_NAR_OK[-1]]):.1f}%' for k in KEYS) + '。'
                    if NAR_SHARE_NOW else '')
                 + '⇒ <b>本页 Deutsche Börse 的占比是上界，Euronext 与 Cboe Europe 的是下界</b>。'
                 '增长率不受影响（宽口径只是整条线乘一个近似常数），'
                 '所以 Exhibit 6 与 Exhibit 14 照读。'),
    })

# ── Exhibit 13：单月同比矩阵 —— 与 Exhibit 14 同一口径、同一批数，只是换个读法 ──
# 这张图的口径本轮**一格没动**（热力矩阵的读法就是逐格比较，换成滚动口径后相邻格几乎
# 相同，整张矩阵退化成一条颜色渐变，图就没用了）；动的是它周围那些话：
# 上一轮它是本页唯一一处单月同比，标题、图例、图注都写着「留着它是当反面教材」。
# 本轮 Exhibit 14 也改成了单月同比，那三处措辞当场全成假话，逐处改写 ——
# 它现在与 Exhibit 14 是**同一条序列的两种画法**（矩阵看单月异常，折线看整段走势）。
_hm = IDX[-HEAT_MONTHS:]
_hm_mat = [[(round(float(YOY[k][p]), 6) if ok(YOY[k][p]) else None) for p in _hm]
           for k in KEYS]
_hm_flat = sorted(v for row in _hm_mat for v in row if v is not None)
if _hm_flat:
    _hm_p5 = float(np.percentile(_hm_flat, 5))
    _hm_p95 = float(np.percentile(_hm_flat, 95))
    _hm_neg = sum(1 for v in _hm_flat if v < 0)
    ex.append({
        'n': 13, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pct0z',
        'title': (f'SINGLE-MONTH y/y (%), last {len(_hm)} months — same basis as Exhibit 14, '
                  f'read cell by cell'),
        'rows': [SHORT[k] for k in KEYS], 'cols': [mlab(p) for p in _hm],
        'matrix': _hm_mat,
        'legend': '现货成交额 单月同比（%）—— 与 Exhibit 14 同一口径、同一批数',
        'cell_h': 26, 'row_lab_w': 108,
        'row_head': '交易所',
        'src_extra': ('Single-month y/y, the same basis as Exhibit 14 and as every y/y on this '
                      'page. No rolling 12-month-total line is drawn anywhere here'),
        'note': ('<b>这张矩阵与 Exhibit 14 是同一条序列的两种画法</b>：口径同为单月同比'
                 '（当月 ÷ 去年同月 − 1，建在日均上），逐格的数与 Exhibit 14 的线'
                 '<b>在同一个月上完全相同</b>，矩阵只是把最近 '
                 + f'{len(_hm)} 个月摊开、把「哪几个月异常」摆到台面上。'
                 '⚠ 仍然<b>不要沿着横轴把这张矩阵读成趋势</b> —— 单月读数逐格跳，'
                 '整段走势看 Exhibit 14 那条线（同一批数，只是画法不同）。'
                 + YOY_TXT +
                 '<b>这张图本轮为什么口径没跟着改：它本来就是单月的。</b>'
                 '热力矩阵的读法就是<b>逐格比较</b>，换成滚动口径后相邻格几乎相同，'
                 '整张矩阵会退化成一条平滑的颜色渐变，图存在的理由就没了。'
                 '请把它读成「哪几个月是异常月」'
                 '（假期、到期日、指数再平衡、事件驱动的成交爆发）。'
                 f'⚠ <b>红色不等于下跌。</b>色标取本矩阵全部有效格的 5/95 分位，本轮是 '
                 f'{_hm_p5:+.0f}% 与 {_hm_p95:+.0f}%，而 {len(_hm_flat)} 个格子里只有 '
                 f'<b>{_hm_neg} 个</b>是负的 —— 偏红的格子多数是「在这张矩阵里增速偏低」'
                 '的正增长，读数一律以格内数字为准。颜色只在本图内部可比。'
                 '格内取 0 位小数，−0.5% ~ 0 之间印成「0%」而不是「-0%」'
                 '（负零是格式化产物，不是缺失值）；真值切「表格」视图即可看到。'
                 '三家同币种，同比里没有任何汇率成分，也不受口径宽窄影响'
                 '（宽口径只是整条线乘一个常数）。'),
    })

# ── Exhibit 14：单月同比 —— 本轮按页面所有者的指令，由 12 个月滚动合计改成单月 ──
# 改的是**口径本身**，所以标题、ylab、src_extra、图注四处一起改：只改数不改名，
# 读者会拿一条逐月跳的线当已经平滑过的趋势线读，那比不改更糟。
# 序列直接复用 YOY（= Exhibit 13 那一批），不另起一条 —— 同一页上同一个口径出两个数，
# 正是 CONTRACT.md §6 开篇那条审计发现（cme Ex2 说 +19.1%、Ex8 说 −1.2%）。
_y1_now = {k: float(YOY[k][CUR]) for k in KEYS if ok(YOY[k][CUR])}
_y1_rank = sorted(_y1_now.items(), key=lambda kv: -kv[1])
YOY_FIRST = {k: (YOY[k].dropna().index[0] if YOY[k].notna().any() else None) for k in KEYS}
YOY_TOT_FIRST = YOY_TOT.dropna().index[0] if YOY_TOT.notna().any() else None
ex.append({
    'n': 14, 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H_ENDLABEL,
    'fmt': 'f1', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'markers': False,
    'zero_line': True, 'end_label': True, 'label_fmt': 'f1',
    'title': 'Turnover growth, SINGLE-MONTH y/y (this month vs. the same month a year earlier)',
    'ylab': '% y/y（单月同比：当月 ÷ 去年同月 − 1）',
    'series': [{'name': SHORT[k], 'color': COLOR[k], 'values': L(YOY[k].values)}
               for k in KEYS]
              + [{'name': '本池三家合计', 'color': TOTAL_C, 'values': L(YOY_TOT.values)}],
    'break_at': ENX_BRK_I, 'break_label': ENX_BRK_TXT,
    'src_extra': ('Single-month y/y on average daily turnover, so trading-day counts cancel in '
                  'the ratio. Same basis as the summary table and the headline; no rolling '
                  '12-month-total line is drawn anywhere on this page'),
    'note': (f'<b>本页要读「谁在增长」，读这一张。</b>{mlab(CUR)}：'
             + '、'.join(f'{SHORT[k]} {pct(v)}' for k, v in _y1_rank)
             + (f'；本池合计 {pct(float(YOY_TOT[CUR]))}' if ok(YOY_TOT[CUR]) else '')
             + '。' + YOY_TXT
             + ((f'⚠ Cboe Europe 与本池合计的线都从 {mlab(YOY_TOT_FIRST)} 才起'
                 if YOY_FIRST['cboe'] == YOY_TOT_FIRST else
                 f'⚠ Cboe Europe 的线从 {mlab(YOY_FIRST["cboe"])} 才起、本池合计从 '
                 f'{mlab(YOY_TOT_FIRST)} 才起')
                + f' —— 单月同比要回看 {ROLL} 个月，'
                  f'而 Cboe Europe 的披露起点 {mlab(START)} 就是本页窗口的起点，'
                  f'开头 {ROLL} 个月<b>如实留空，不做任何外推</b>。'
                  'Euronext 与 Deutsche Börse 的历史远早于本页窗口，所以它们全程有值。'
                if YOY_TOT_FIRST and YOY_FIRST.get('cboe') else '')
             + '⚠ 口径宽窄不影响这张图（宽口径只是整条线乘一个常数），'
             'Deutsche Börse 那条线在这里<b>是可比的</b>，它只在占比图上是高估的。'
             + (f'红色竖虚线 = Euronext 口径断点（{"、".join(ENX_BRK_TXT)}）：'
                f'每条线右侧 <b>{ROLL} 个月</b>的读数都含并表，不是自然增长'
                f'（滚动口径要污染 {2 * ROLL} 个月，这是换成单月口径省下来的那一半）。'
                if ENX_BRK_I else '')),
})

# ── Exhibit 15：Euronext 成交额 = 成交笔数 × 每笔均值（对数分解）──
if HAS_VP:
    _cr_txt = (f'算术分解那一路会剩一个交叉项，实测占 ΔV 的中位 <b>{VP_CR_MED:.1f}%</b>、'
               f'最大 <b>{VP_CR_MAX:.0f}%</b>（{VP_CR_AT}）—— '
               '在两头几乎对冲的年份里，交叉项能比净增长本身还大，'
               '塞进任一侧都是任意分配。这就是本图用对数分解的理由。')
    _ath_txt = ''
    if VP_ATH:
        _ath_txt = (f'⚠ 2025-11 并入 Athens 之后的 {VP_ATH[2]} 个月里，Athens 占 Euronext '
                    f'现货<b>金额的 {VP_ATH[0]:.1f}%、笔数的 {VP_ATH[1]:.1f}%</b> —— '
                    '它带来的笔数比金额多，所以那一列的形状里有一块是<b>抬笔数、压每笔均值</b>的'
                    '并表效应，不是 Euronext 自身的结构变化。')
    ex.append({
        'n': VP_N_DEC, 'kind': 'bridge_bar', 'full': True, 'height': 320,
        'fmt': 'f1', 'label_fmt': 'f1', 'xrot': 0, 'xstep': 1,
        'xlabels': VP_LAB,
        'title': ('Euronext cash turnover growth split into trade count and average trade value '
                  '(log decomposition, % per year)'),
        'ylab': '对数增长贡献（%）—— 两段之和 = 菱形',
        'stacks': [
            {'name': '成交笔数的贡献 ln(n₁/n₀)', 'color': 'NAVY', 'values': L(VP_LV)},
            {'name': '每笔均值的贡献 ln(m₁/m₀)', 'color': 'BLUE', 'values': L(VP_LM)},
        ],
        'net': {'name': '成交额对数增长 ln(V₁/V₀)', 'values': L(VP_LT)},
        'net_color': 'INK',
        'break_at': VP_BRK_I, 'break_label': VP_BRK_TXT,
        'src_extra': ('Identity: turnover = number of trades x average value per trade. '
                      'Endpoints are 12-month totals, never single months. This is NOT a '
                      'price/volume split — Euronext publishes no share count'),
        'note': ('⚠ <b>这不是量价分解。</b>第二段是<b>每笔平均成交额</b>，它主要反映'
                 '<b>订单碎片化程度</b>（一张单子多大：算法切单、暗池与大宗的进出、'
                 '并表带进来的新市场结构），与市场涨跌只有间接关系。'
                 '<b>它不是指数收益率，也不是加权平均股价</b> —— 真正的「股数 × 均价」'
                 '需要成交股数列，本页三家<b>一列都没有</b>。'
                 f'恒等式：成交额 ≡ 笔数 × 每笔均值，两段之和逐列<b>恒等于</b>菱形'
                 f'（实测最大残差 {VP_RES:.1e}pp，超过 1e-9 就直接停止生成）。'
                 f'⚠ <b>「每笔均值」的绝对水平本页一个都不印</b>：官方对这两列用的是'
                 f'<b>两种计数惯例</b> —— 金额列在 <code>Trading volume (single counted)</code> '
                 f'分组下、笔数列在 <code>Transactions (buy and sell)</code> 分组下'
                 f'（<code>docs/verify/enx.md</code> 口径坑 6）。'
                 f'两者相除得到的<b>不是</b>每笔真实成交额，而是它除以一个我们没有独立证据'
                 f'去确定的计数因子；本页<b>不去猜那个因子</b>，因此不报任何绝对水平。'
                 f'但<b>增长分解不受影响</b>，两条实测为证：(a) 分解对笔数列乘任何常数'
                 f'完全不变（实测最大差 {VP_SCALE_MAX:.1e}pp）；'
                 f'(b) 计数惯例<b>没有中途翻转</b> —— 惯例一翻，每笔均值会在那个月跳约 '
                 f'ln2 = {VP_LN2 * 100:.1f}%，而 {VP_CONV_N} 个非断点月里最大单月跳变只有 '
                 f'<b>{VP_CONV_MAX * 100:.1f}%</b>（{VP_CONV_AT}）。'
                 f'<b>口径：</b>这两列配的是 <code>{VP_VAL_COL}</code>（<b>全部现货</b>：'
                 f'股票与投资基金 + ETF + 结构化产品），比本页头条那一列宽 —— '
                 f'头条列只占它的 <b>{VP_SC_MIN:.0f}–{VP_SC_MAX:.0f}%</b>'
                 f'（中位 {VP_SC_MED:.0f}%）。用宽列是因为<b>窄列没有配对的笔数列</b>，'
                 f'宁可换一条自洽的序列，也不拿不同口径的分子分母去凑一个均值。'
                 f'<b>端点一律是 12 个月合计</b>（完整自然年；'
                 + (f'末列 {VP_LAB[-1]} = 截至 {mlab(LATEST)} 的 12 个月 vs 前 12 个月）'
                    if HAS_VP_TTM else '）')
                 + '，不用点对点单月 —— 这张图的横轴是<b>年</b>，问的是「这一年比上一年多出来的'
                 '成交额里，多少来自笔数、多少来自每笔均值」，拿单月当端点等于让一个异常月替'
                 '一整年发言。⚠ 别把它与 Exhibit 14 的单月同比混起来：那张图逐月画读数，'
                 '这张图年对年做分解，两者问的不是同一个问题。'
                 f'<b>算法：</b>用<b>对数（LMDI）分解</b>。{_cr_txt}'
                 f'算术（Bennet）分解照样算了，两路的贡献值最大差 <b>{VP_AL_MAX:.1f}pp</b>；'
                 f'代价是<b>对数增长率 ≠ 简单百分比</b>'
                 f'（成交额<b>翻一倍</b>在对数口径里记成 +{VP_LN2 * 100:.1f}%，不是一倍），'
                 f'两者最大差 {VP_LT_B_MAX:.1f}pp，'
                 f'例如末列对数 {pct(VP_LT[-1])}、简单百分比 {pct(VP_BT[-1])}。'
                 f'<b>汇率：</b>本币与定基美元下这张图<b>完全相同</b>（定基汇率是常数，'
                 f'对增长率没有影响）—— 代码里两条路各算一遍，实测最大差 {VP_FX_MAX:.1e}pp。'
                 f'换成<b>当期</b>汇率就不成立了，那时「每笔均值」会变成'
                 f'「每笔均值 + 汇率」的混合物，而图上完全看不出来。'
                 f'读数：{len(VP_LAB)} 列里有 <b>{VP_VOL_YEARS} 列</b>是笔数那一段占主导；'
                 f'笔数贡献最极端的一列是 {VP_BIG_V[0]}（{pct(VP_BIG_V[1])}），'
                 f'每笔均值最极端的是 {VP_BIG_P[0]}（{pct(VP_BIG_P[2])}）。'
                 + _ath_txt
                 + (f'红色竖虚线 = Euronext 口径断点（{"、".join(VP_BRK_TXT)}）：'
                    '并表当年的「笔数」里有一块是买来的，不是自然增长。'
                    if VP_BRK_I else '')),
    })

# ── Exhibit 16：成交笔数本身 —— 水平值 + 增速 ──
if HAS_VP:
    ex.append({
        'n': VP_N_TRD, 'kind': 'bar_line_dual', 'full': True, 'height': 340,
        'fmt': 'f0', 'yfmt': 'f0', 'xstep': 12, 'xrot': 90,
        'xlabels': VP_XL,
        'title': 'Euronext cash trades: monthly count and SINGLE-MONTH y/y growth',
        'ylab': '百万笔/月（当月合计）',
        'ylab2': '% y/y（单月同比：当月 ÷ 去年同月 − 1）',
        'bar': {'name': '成交笔数（百万笔/月）', 'color': COLOR['enx'],
                'values': L([float(VP_N_M[p]) for p in VP_MON])},
        'line': {'name': '单月同比（RHS）', 'color': CUR_FX_C,
                 'values': L([float(VP_N_MOM[p]) if ok(VP_N_MOM[p]) else None
                              for p in VP_MON]),
                 'yfmt': 'pct0'},
        'break_at': VP_BRK_MI, 'break_label': VP_BRK_MTXT,
        'src_extra': ('Trade counts are buy-and-sell counted, so the level is on the exchange\'s '
                      'own convention; growth is unaffected by any constant counting factor. '
                      'The line is the single-month y/y of the bars themselves'),
        'note': ('柱是<b>当月成交笔数合计</b>（官方日均笔数 × 当月现货交易日），'
                 '线是<b>这些柱自己的单月同比</b>（当月柱 ÷ 去年同月那根柱 − 1）—— '
                 '本轮按页面所有者的指令由 12 个月滚动合计同比改成单月同比，'
                 '<b>好处是这条线现在可以拿相邻的柱当场核对</b>，'
                 '代价与实测数字见下方那一段。'
                 f'⚠ 笔数是<b>买卖双边计</b>，所以柱的<b>绝对水平按交易所自己的口径读</b>，'
                 f'不要拿去与别家的「笔数」比；<b>增速不受这件事影响</b>'
                 f'（乘常数不变，实测最大差 {VP_SCALE_MAX:.1e}pp，见 {EX_DEC}）。'
                 f'窗口 {VP_XL[0]} – {VP_XL[-1]}（{len(VP_MON)} 个月，本页最长的一条序列）；'
                 f'单月同比自 {mlab(VP_N_MOM_FIRST)} 起才有值（要回看 {ROLL} 个月），'
                 f'之前如实留空。实测区间 {pct(VP_N_YOY_LO)} – {pct(VP_N_YOY_HI)}。'
                 f'<b>换口径的代价，用这条笔数序列自己实测</b>'
                 f'（{VP_CAL["n"]} 个两种口径都有值的月份，样本先对齐，'
                 f'实现见 <code>build/yoy.py</code> 的 <code>caliber_diff()</code>）：'
                 f'逐月标准差 <b>{VP_CAL["std_mom"]:.1f}pp</b> vs 滚动口径的 '
                 f'{VP_CAL["std_ttm"]:.1f}pp（放大 {VP_CAL["std_ratio"]:.2f} 倍）；'
                 f'相邻月跳变中位 {VP_CAL["medjump_mom"]:.1f}pp vs '
                 f'{VP_CAL["medjump_ttm"]:.1f}pp，最大 '
                 f'<b>{VP_CAL["maxjump_mom"][0]:.0f}pp</b>'
                 f'（{mlab(VP_CAL["maxjump_mom"][1])} → {mlab(VP_CAL["maxjump_mom"][2])}）'
                 f'而滚动口径同期最大 {VP_CAL["maxjump_ttm"][0]:.0f}pp；'
                 f'两者<b>符号相反</b>的月份有 {VP_CAL["opposite_n"]} 个'
                 f'（占 {VP_CAL["opposite_share"] * 100:.0f}%）'
                 + (f'，差得最远的是 {mlab(VP_CAL["worst_gap"][0])}：单月 '
                    f'{pct(VP_CAL["worst_gap"][1])} 而滚动 {pct(VP_CAL["worst_gap"][2])}'
                    if VP_CAL['worst_gap'] else '') + '。'
                 f'⚠ <b>这条线里含日历效应</b>：柱是当月<b>合计</b>笔数，当月与去年同月的'
                 f'交易日数不一定相同，这一块在比值里不会自己约掉。实测把它剔掉'
                 f'（改按日均笔数算同比）最大差 <b>{VP_N_DAYGAP_MAX:.1f}pp</b>、'
                 f'中位 {VP_N_DAYGAP_MED:.1f}pp（最大发生在 {mlab(VP_N_DAYGAP_AT)}）。'
                 f'本图仍取当月合计口径，是为了让线与柱严格对应 —— 换成日均口径，'
                 f'线就不再是这些柱的同比，而图上完全看不出来。'
                 f'（Exhibit 14 的四条线相反，画的是<b>日均</b>口径的单月同比：'
                 f'那张图上没有柱可对，日历效应剔掉更干净。）'
                 '⚠ <b>双轴的代价</b>：右轴的同比要跨零，而引擎默认把两轴零点画在同一高度，'
                 '所以左轴零线以下会空出一段（<code>docs/CHART_KINDS.md</code> §4）。'
                 '不接受这段留白就只能把增速另起一张图，而那样量与增速就对不上同一条时间轴了。'
                 '⚠ 这张图只有 Euronext —— Cboe Europe 与 Deutsche Börse '
                 '<b>没有任何现货数量列</b>（见页尾口径说明），不是本轮没找。'
                 + (f'红色竖虚线 = 笔数列的口径断点（{"、".join(VP_BRK_MTXT)}），'
                    '月份来自 <code>series/enx_breaks.csv</code>，与金额列的断点集合逐个相同 —— '
                    '这正是这两列可以配对的机器判据之一。'
                    if VP_BRK_MI else '')),
    })

# ── 硬护栏：改口径之后，图注里那两句「读者可以自己核对」必须真的成立 ──────────────
# 这两句话是可以被读者当场证伪的，所以不能靠人眼看一遍就写上去，得由机器每次生成时判。
#   ① Exhibit 13 的每一格 = Exhibit 14 同月同成员的那一点。图注写着「同一条序列的两种
#      画法、逐格的数完全相同」—— 哪天有人把其中一张换回别的口径或别的底料，这一句会
#      当场变成假话，而两张图长得都很正常，肉眼看不出来。
#   ② 成交笔数图的线 = 柱自己的同比（CONTRACT §6.1 第 1 条要的那个「拿这根柱除以 12 根柱
#      之前那根，就是线上这一点」）。容差取 1e-5pp：payload 里的数经 L() 取到小数点后 6 位，
#      实测这一项的残差在 5e-7pp 量级，而任何真的换错口径都会差出以 pp 计的量。
_e13 = next((e for e in ex if e['n'] == 13), None)
_e14 = next((e for e in ex if e['n'] == 14), None)
if _e13 and _e14:
    _pos = {m: i for i, m in enumerate(XL_LONG)}
    for _r, _nm in enumerate(_e13['rows']):
        _ln = next(s for s in _e14['series'] if s['name'] == _nm)
        for _c, _mo in enumerate(_e13['cols']):
            _a, _b = _e13['matrix'][_r][_c], _ln['values'][_pos[_mo]]
            if _a != _b:
                raise SystemExit(
                    f'Exhibit 13 与 Exhibit 14 在 {_nm} {_mo} 上不是同一个数'
                    f'（{_a} vs {_b}）—— 两张图的图注都写着它们同口径同一批数，'
                    f'先把那句话改掉，或者把口径改回来，再跑。')
if HAS_VP:
    _e16 = next(e for e in ex if e['n'] == VP_N_TRD)
    _bv, _lv = _e16['bar']['values'], _e16['line']['values']
    _gap = max((abs((_bv[i] / _bv[i - yoy.LAG] - 1) * 100 - _lv[i])
                for i in range(yoy.LAG, len(_bv))
                if _bv[i] is not None and _lv[i] is not None and _bv[i - yoy.LAG]),
               default=0.0)
    if not (_gap < 1e-5):
        raise SystemExit(
            f'{EX_TRD} 的右轴线不等于柱自己的同比，最大差 {_gap:.3e}pp —— '
            f'图注写着「可以拿相邻的柱当场核对」，这句话必须是真的（CONTRACT §6.1 第 1 条）。')

# ──────────────────── 10. Exhibit 17：核对表（官方原始单位）────────────────────
TBL_COLS = [
    ('Euronext 股票 ADNV（€bn/日）', 'enx', 'enx', ENX_COL, 1.0, 3),
    ('Euronext 现货交易日', 'enxd', 'enx', 'trading_days_cash', 1.0, 0),
    ('Cboe Europe ADNV（€bn/日）', 'cb', 'cboe', 'adv_eu_equities_adnv_eurbn', 1.0, 3),
    ('DB1 现货成交额（€bn/月）', 'db1', 'db1', 'turnover_cash_total_eurbn', 1.0, 1),
    ('DB1 现货交易日', 'db1d', 'db1', 'trading_days_cash', 1.0, 0),
    ('DB1 Xetra 股票（€bn/月，窄口径）', 'db1x', 'db1', 'turnover_xetra_equities_eurbn', 1.0, 1),
    ('Nasdaq 北欧现货（US$bn/月）', 'nd', 'ndaq', NDAQ_MON_COL, 1.0, 1),
]
# Exhibit 15 / 16 用的那一对列也进表 —— 这张表存在的唯一理由就是让人自己复算，
# 而这两张新图用的两列在上面一列都不在。不加进来，读者无从核对分解的分子分母。
if HAS_VP:
    TBL_COLS += [
        ('Euronext 全部现货 ADNV（€bn/日，单边计）', 'enxv', 'enx', VP_VAL_COL, 1.0, 3),
        ('Euronext 现货成交笔数（千笔/日，双边计）', 'enxt', 'enx', VP_TRD_COL, 1.0, 1),
    ]
W13 = IDX[-TBL_MONTHS:]
_fxrow = {str(p): fxr('EUR', p) for p in W13}
table = {
    # 表号跟着最后一张图走，不写死：Exhibit 15 / 16 是有条件生成的
    # （Euronext 那一对列没通过判据就整块不画），写死会在页面上留下 15、16 两个空号。
    'n': ex[-1]['n'] + 1,
    'title': f'近 {TBL_MONTHS} 个月原始指标核对表（各家官方原始单位与币种，未做任何换算）',
    'idx': '月份',
    'cols': [[h, k] for h, k, _, _, _, _ in TBL_COLS] + [['EUR/USD 月均（ECB）', 'fx']],
    'rows': [dict({'xl': mlab(p)},
                  **{k: (num(float(RAW[src][c].get(p, np.nan)) * sc, d)
                         if RAW[src] is not None and c in RAW[src].columns else '—')
                     for _, k, src, c, sc, d in TBL_COLS},
                  fx=num(_fxrow[str(p)], 4))
             for p in W13],
}

# ────────────────────────── 11. 口径与方法说明 ──────────────────────────
_ahead_txt = ('；'.join(f'{d} 自身已更新至 {mlab(m)}' for d, m in AHEAD)
              if AHEAD else '本期三家的最新月恰好一致，无人跑在前面')


# ── 色名复用：NDAQ_C 与 CUR_FX_C 是同一个色名，冲不冲突要**现扫 ex**，不能凭记忆枚举 ──
# ⚠ 原文写的是「Nasdaq 只在 Exhibit 9 / 10 出现，汇率对照线只在 Exhibit 7 / 8 / 11 / 12
#   出现」。前半句今天为真，后半句本页自己就证伪：同一个色名还用在同月柱的年份色、
#   「剔除 Athens 备注列」、窄口径列上，而**紧接着的下一句自己就写着「增速线用它」**。
#   真正要保证的只有一件事 —— 同一张图里它不能既是 Nasdaq 又是别的东西。所以现扫。
def _color_hits(o, c, out=None):
    """递归扫一个 exhibit，返回用到色名 c 的序列名（拿不到名字的记 '—'）。

    不假设 payload 的键名：bar / line / series / stacks / groups 各 kind 不一样，
    写死键名就等于又立一个会过期的枚举。
    """
    out = [] if out is None else out
    if isinstance(o, dict):
        if o.get('color') == c:
            out.append(o.get('name') or '—')
        for v in o.values():
            _color_hits(v, c, out)
    elif isinstance(o, list):
        for v in o:
            _color_hits(v, c, out)
    return out


_SHARED_C = [(e['n'], _color_hits(e, CUR_FX_C)) for e in ex]
_SHARED_C = [(n, nm) for n, nm in _SHARED_C if nm]


def _is_nd(nm):
    return any('Nasdaq' in x for x in nm)


# ── 哪几张图真的画了红色竖虚线：现扫 ex ─────────────────────────────────────
# ⚠ 原文写死「Exhibit 2 / 3 / 6 / 14（以及 15 / 16）都画了红色竖虚线」——
#   2026-08-19 实跑，带 break_at 的其实是 2 / 3 / 6 / 11 / 14 / 15 / 16：**漏了 Exhibit 11**
#   （它画的是 Nov-25 并表 Athens 那一条）。读者照着这张清单去数线，会发现多出一张。
#   各图窗口不同 ⇒ 落进窗口的断点条数也不同，所以连条数一起现算。
_BRK_EX = [(e['n'], len(e.get('break_at') or [])) for e in ex if e.get('break_at')]

_SHARED_ND = [n for n, nm in _SHARED_C if _is_nd(nm)]
_SHARED_CLASH = [n for n, nm in _SHARED_C
                 if _is_nd(nm) and any('Nasdaq' not in x for x in nm)]

NOTES = [
    f'<b>发布门槛：共同最新月。</b>本页统一截到 <b>{mlab(LATEST)}</b>，即三家现货成交额序列里'
    f'最慢那家的最新月。本期短板是 <b>{"、".join(LAG)}</b>；{_ahead_txt}。'
    '门槛存在的理由：各家披露节奏差一两周，若各画各的最新月，读者会拿一家的 7 月比另一家的'
    '6 月，看到的「谁在拿份额」有一整个月是口径造出来的。'
    '<b>跑在前面那家的最新一个月不在本页任何一张图、任何一行表里。</b>'
    f'共同起点 {mlab(START)} 由 Cboe Europe 的披露起点决定 —— 它是本页历史长度的天花板，'
    f'也是季度图只有 {QSPAN_Y:.1f} 年而不是十年的原因。',

    '<b>本页没有真分母，占比一律是「池内相对占比」。</b>' + DENOM_TXT +
    '为什么拿不到 —— 四条路本轮逐条查过，逐条写明：'
    '<b>(1) FESE European Equity Market Report</b>（fese.eu/statistics/european-equity-market-report/）：'
    '月度 xlsx 公开可下、不要登录，但页面对范围只写了一句 "provides equity trading figures '
    'from all major European trading venues"，真正的口径定义在另挂的 Methodology PDF 里；'
    '且 FESE 是<b>会员制交易所联合会</b>，统计口径结构上不含 SI 与非会员场所的 OTC/暗池 —— '
    '就算抓下来也只是另一个（更大的）成员集合之和，不是含 SI 与暗池的泛欧合并量。'
    '📌 本轮<b>没有</b>下载 EEMR 逐列实测，所以本页没有引用它的任何一个数字'
    '（要用它必须先建 fetch/fese.py 与 series/fese.csv）。'
    '<b>(2) Cboe Europe 自家的 Market Share 页</b>：前端渲染的透视表、数据延迟至少 15 分钟、'
    '无文档化的 CSV/API；页面自己写着 "does not track primary exchange volumes for markets '
    'marked with an asterisk"，即<b>它自己的分母就不全</b>；user_guide 页对是否含 SI 与暗池'
    '一个字没写。一个由竞争对手维护、覆盖范围未文档化、自承有缺口的分母，不能当权威分母。'
    '<b>(3) big xyt Liquidity Cockpit</b>：确实是市场公认的「含 SI 与暗池的可寻址流动性」'
    '口径提供方，但是<b>商业订阅产品</b>，公开渠道只有博客与新闻稿里的零星读数，'
    '没有可无人值守抓取的月度序列，也不符合本仓「数据来自公司官网 IR 或监管申报」的硬约束。'
    '<b>(4) ESMA</b>：公开的是<b>年度</b>透明度计算（每只证券的 ADT，用于定 LIS 门槛）'
    '与暗池双重成交量上限（DVC，逐券），<b>没有</b>按场所汇总的月度成交额；'
    '更根本的一条 —— MiFIR 要求的<b>股票合并信息带（consolidated tape）到本轮为止'
    '还没有开始发布</b>（ESMA 2026-04 还在就欧洲股票市场结构发 Call for Evidence）。'
    '⇒ 「官方泛欧合并量」这个东西目前在制度上还不存在，不是我们没找到。'
    '<b>分母一旦有了，本页的占比图可以原地换分母，一张图型都不用改。</b>',

    '<b>三家的涵盖范围不一致，Deutsche Börse 那条更宽 —— 这是本页最大的一处妥协。</b>'
    'Euronext（<code>adv_cash_equities_adnv_eurbn</code>：股票与投资基金、单边计）与 '
    'Cboe Europe（<code>adv_eu_equities_adnv_eurbn</code>：泛欧股票、单边计）逐字同口径；'
    'Deutsche Börse 用的是 <code>turnover_cash_total_eurbn</code>'
    '（Xetra + Börse Frankfurt 场内，含 ETP / 结构化产品 / 债券 / 基金）。'
    f'选它是因为只有它有 {DB1_WIDE_N} 个月历史（{DB1_WIDE_FROM} 起），'
    '而与另两家逐字同口径的窄口径列'
    # ⚠ 这半句原先是 f'只有 {len(W_NAR)} 个月（{mlab(W_NAR[0])} 起）'。数是现算的，
    #   但**算的不是同一种东西**：len(W_NAR) 是首末月之间的格子数（跨度），
    #   而并排比较的 DB1_WIDE_N 是逐月连续的真实观测数。窄口径列中间有整段空洞，
    #   跨度里真有数的只有 len(_NAR_OK) 个 —— 同页 Exhibit 12 的图注写的正是这个数。
    #   两个不同种类的数放进同一个比较句，读者会以为窄口径有跨度那么多月的数据。
    #   ⇒ 主数改成 _NAR_OK（有数的月），跨度作为附注跟在后面，两者都现算。
    #   「中间整段缺」这半句也不写死：缺口补齐了它就该自己消失，判据是 len 之差。
    + ((f'只有 {len(_NAR_OK)} 个月有数（散落在 {mlab(W_NAR[0])}–{mlab(W_NAR[-1])} '
        f'这 {len(W_NAR)} 个月里，中间缺 {len(W_NAR) - len(_NAR_OK)} 个月）'
        if len(_NAR_OK) < len(W_NAR) else
        f'只有 {len(_NAR_OK)} 个月（{mlab(W_NAR[0])}–{mlab(W_NAR[-1])} 逐月连续）')
       if HAS_NAR_WIN else '历史极短')
    + '，用窄口径本页的长历史份额图就没有了。'
    + (f'代价已实测并画在 Exhibit 12：宽 ÷ 窄 = {SCOPE_MIN:.2f}–{SCOPE_MAX:.2f} 倍，'
       f'折成池内占比 Deutsche Börse 被高估 {SH_GAP_MIN:.1f}–{SH_GAP_MAX:.1f}pp。'
       if HAS_NAR_WIN else '')
    + '⇒ <b>本页 Deutsche Börse 的占比读作上界，Euronext 与 Cboe Europe 的读作下界。</b>'
      '增长率与同比不受影响（宽口径只是整条线乘一个近似常数），Exhibit 6 与 Exhibit 13 照读。'
      '⚠ 另一处更细的差异：Cboe Europe 是<b>泛欧 MTF</b>，撮合的正是 Euronext 与 Xetra 上市的'
      '那批股票；Xetra 只覆盖德国上市。三家<b>争的确实是同一批订单流</b>（MiFID II 之下'
      '任何欧洲股票可在任何场所交易），这也正是欧洲页可以算占比、而亚太页不可以的原因。',

    '<b>Nasdaq 北欧：绝对值可比，份额不可比。</b>'
    'Nasdaq 在 IR 月报里发的是 "European equity volume (value of shares traded, $ billion)"，'
    '在季度面板里发的是「欧洲现货市占」'
    + (f'（本轮 {ND_SHARE_LAST:.1f}%）' if HAS_NDQ else '')
    + '。那个百分数的口径是<b>北欧+波罗的海</b> —— NDAQ 2026Q1 8-K EX-99.1 脚注 7 原文：'
      '"European cash equities markets include cash equities exchanges of Sweden, Denmark, '
      'Finland, and Iceland"（转录见 <code>fetch/ndaq.py</code> 口径坑 1、'
      '<code>docs/verify/verify_ndaq.md</code> E2）。'
      'Cboe Europe 的份额是泛欧口径。两个分母是两个不同的宇宙：'
    + (f'把它自己的成交额除以它自己的份额，反推出来的整个「欧洲市场」分母，'
       f'比 Cboe Europe <b>一家</b>还小 {ND_QR_MED:.1f} 倍'
       f'（窗口内 {ND_QR_MIN:.1f}–{ND_QR_MAX:.1f} 倍，Exhibit 10）。' if HAS_NDQ else '')
    + '⇒ 本页把 Nasdaq 北欧放进 Exhibit 9（绝对值）与 Exhibit 10（分母对撞），'
      '<b>不进任何份额的分子或分母</b>。'
      '另外它官方只发当月合计且<b>不给北欧交易日</b>，所以 Exhibit 9 用「€bn/月」'
      '而不是日均 —— 硬转 ADV 需要一个我们没有的日历。',

    '<b>季度份额是量加权的，不是三个月份额的平均。</b>'
    '季度占比 = 该季三个月成交额之和 ÷ 该季池合计。取平均会让一个 18 个交易日的 12 月'
    '与一个 23 天的 3 月等权，把日历噪音读成份额变化。'
    f'月长权重取 Euronext 的 <code>trading_days_cash</code>（欧元区口径），'
    f'与 Deutsche Börse 同名列在本页窗口内 <b>{DAYS_SAME}/{DAYS_N} 个月完全相同</b>'
    '（不同的那几个月差 1–2 天，集中在 12 月与 10 月）；'
    'Deutsche Börse 的月度总额本来就是官方原生列，不经这个权重。'
    '窗口两端不满三个月的残季一律不画、不年化。'
    f'月度图（Exhibit 2）保留 —— 它答的是「这个月发生了什么」；'
    f'季度图（Exhibit 3）答的是「结构在往哪走」，{len(QIDX)} 个季、约 {QSPAN_Y:.1f} 年。'
    '同比同月图（Exhibit 4）再把季节性彻底固定住：同一个日历月的连续几年并排。',

    '<b>同比口径。</b>'
    + YOY_TXT
    + f'逐处点名（口径这件事不许靠读者自己猜，所以把每一处写全）：'
      f'<b>单月同比（当月 ÷ 去年同月 − 1）</b> —— <b>Exhibit 13</b> 的热力矩阵、'
      f'<b>Exhibit 14</b> 的四条线'
    + (f'、<b>{EX_TRD}</b> 的右轴线' if HAS_VP else '')
    + f'、汇总表「现货成交额同比」那一组行、抬头的 y/y。'
      f'其中 <b>Exhibit 14</b>'
    + (f'、<b>{EX_TRD}</b>' if HAS_VP else '')
    + f'、汇总表那一组行与抬头是<b>本轮改的</b>（原为 12 个月滚动合计同比）；'
      f'<b>Exhibit 13 本来就是单月</b>，口径一格没动，改的只是它周围那些'
      f'「本页唯一一处单月同比 / 留着当反面教材」的话 —— 那些话在 Exhibit 14 换口径的'
      f'当天就成了假话，标题、图例、来源行、图注逐处改写过。'
      f'<b>不是同比、不要拿去与上面并排读的</b> —— (a) 汇总表的「本月 vs 上月」'
      f'「本月 vs 去年同月」两列是那一行自己三个读数之间的算术（表头已从 m/m / y/y '
      f'改成中文全称）：在成交额行上「本月 vs 去年同月」与同比那一组行是同一个数，'
      f'在占比行与汇率行上则是 pp 差，不是同比。'
      f'(b) <b>指数化图（Exhibit 6 / 7 / 8）不是同比</b>，它们画的是相对定基月的累计变动。'
      f'(c) <b>{EX_DEC} 的年度分解端点是 12 个月合计</b>，那是「一年对一年」，横轴是年，'
      f'不是这里说的任何一种月度同比。'
      f'(d) 抬头里的<b>季度口径</b>那一段是占比的季度对比（pp），也不是同比。',

    '<b>成交额分解：只有 Euronext 有数据条件，而且它做的不是量价分解。</b>'
    f'⚠ 先摆正名字：{EX_DEC} 做的是 <b>成交额 = 成交笔数 × 每笔均值</b>（对数分解），'
    '<b>不是「股数 × 均价」</b>。第二项是每笔平均成交额，主要反映<b>订单碎片化程度</b>'
    '（一张单子多大），与市场涨跌只有间接关系 —— 它<b>不是</b>指数收益率、'
    '<b>不是</b>加权平均股价，页面上一处都不叫它「价」。'
    '📌 <b>Cboe Europe 与 Deutsche Börse 不具备成交额分解的数据条件</b>：'
    f'扫过两家 CSV 里全部与现货相关、且不是金额/费率/家数的列 —— '
    f'Deutsche Börse <b>一列数量都没有</b>（现货侧全是 <code>turnover_*_eurbn</code>，'
    f'缺的是列，不是口径）；Cboe Europe 只有 '
    f'<code>adv_us_equities_matched_shares_bn</code>，那是<b>美国</b>撮合股数，'
    f'与本页用的泛欧 ADNV 不是同一个覆盖范围。'
    '<b>本页不拿它去凑</b> —— 用美国股数除欧洲成交额，会造出一个方向和大小都不可知的'
    '「均值」，而图上完全看不出来。准确优先于覆盖。'
    + (f'Euronext 这一对（<code>{VP_VAL_COL}</code> + <code>{VP_TRD_COL}</code>）'
       f'过了四道判据：同一张官方表的现货区块、同除现货交易日；'
       f'两列的并表断点集合<b>逐个相同</b>（代码里做相等断言，不同就自动停画）；'
       f'两列用的是<b>两种计数惯例</b>（金额单边计、笔数买卖双边计，'
       f'<code>docs/verify/enx.md</code> 口径坑 6），相除得到的不是每笔真实成交额，'
       f'所以<b>绝对水平一个都不印</b>；增长分解则由两条实测兜住 —— '
       f'对笔数乘任何常数完全不变（最大差 {VP_SCALE_MAX:.1e}pp），'
       f'且计数惯例<b>没有中途翻转</b>（惯例一翻每笔均值会跳约 ln2 = {VP_LN2 * 100:.1f}%，'
       f'而 {VP_CONV_N} 个非断点月里最大单月跳变只有 {VP_CONV_MAX * 100:.1f}%）。'
       f'口径代价：配对的金额列是<b>全部现货</b>，本页头条那一列只占它的 '
       f'{VP_SC_MIN:.0f}–{VP_SC_MAX:.0f}%（中位 {VP_SC_MED:.0f}%）—— '
       f'用宽列是因为窄列没有配对的笔数列。'
       f'算法用<b>对数（LMDI）分解</b>：算术那一路的交叉项实测占 ΔV 的中位 {VP_CR_MED:.1f}%、'
       f'最大 {VP_CR_MAX:.0f}%（{VP_CR_AT}），塞进任一侧都是任意分配；'
       f'两路贡献值最大差 {VP_AL_MAX:.1f}pp，写在 {EX_DEC} 图注里。'
       f'端点一律 12 个月合计（完整自然年 + 一列 TTM），不用点对点单月。'
       if HAS_VP else
       f'⚠ Euronext 这一对本轮也<b>没有</b>通过判据，因此{EX_VP2}未生成：'
       + '；'.join(VP_WHY) + '。'),

    '<b>汇率：本页几乎用不上它，这一点本身是结论。</b>'
    '三家全部以欧元披露 ⇒ 占比与同比里<b>一分钱汇率都没有</b>。'
    f'定基名义额（锁 {mlab(BASE_P)} 月均 EUR/USD = {EURUSD_BASE:.4f}）只在把水平值折成美元时'
    '才起作用，而那个常数对每一家都一样，所以指数化图（Exhibit 6）与直接画欧元的图逐点相同。'
    'Exhibit 7 给出两种汇率口径的池合计，两者之差就是汇率贡献；'
    f'Exhibit 8 把「这个差<b>恒等于</b> EUR/USD 自身的累计变动」画出来自检，'
    f'实测最大偏差 {FX_IDENT_MAX:.2e} pp（浮点舍入量级）。'
    '若哪天这两条线分开，说明池里混进了非欧元成员，那时所有占比图都必须停掉。'
    + (f'换算公式已与 <code>series/contract_specs.csv</code> 的 {len(FX_CHECK)} 个欧元金额类'
       f'产品（{"、".join(FX_CHECK)}）逐个对账，两条路算出来完全相等。' if FX_CHECK else ''),

    '<b>口径断点：图上留痕，能还原的还原，月份不写死在代码里。</b>'
    + (f'Euronext 现货列在本页窗口内有 {len(ENX_BRK)} 个并表断点'
       f'（{"、".join(f"{mlab(p)} {t}" for p, t in zip(ENX_BRK, ENX_BRK_TXT))}），'
       '画了红色竖虚线的是 '
       + '、'.join(f'Exhibit {n}（{c} 条）' for n, c in _BRK_EX)
       + '，语义是「从这一期起与左侧不可比」；条数不等是因为各图的横轴窗口不一样，'
       '只有落进窗口的断点才画得出来。'
       '⚠ 断点会污染同比：<b>Exhibit 14</b> 本轮改成单月同比之后，一次并表污染的是红线'
       '右侧<b>连续 12 个读数</b>（当月比去年同月，而去年同月还在并表之前），'
       '红线右侧这一年的同比一律不能当自然增长读。'
       '（这比原先的滚动口径少一半 —— 那时要滚 12 个月再回看 12 个月，一次断点污染'
       '<b>连续 24 个</b>读数。本轮换口径顺带省下的那一半就是它。）'
       if ENX_BRK else 'Euronext 现货列在本页窗口内没有可画的并表断点。')
    + (f'{ENX_BRK_WHY}。' if ENX_BRK_WHY else '')
    + '断点月份来自 <code>series/enx_breaks.csv</code>（官方脚注的机器可读副本），'
      '<b>不是代码里写死的</b> —— 官方哪天新增一次并表，这里自动跟上。'
      '⚠ 有一处必须澄清：口传里的「2019 年并入 Oslo Børs」指的是<b>股指衍生品</b>列'
      '（官方脚注 since July 2019）；<b>现货</b>列的 Oslo 断点在 <b>2018-01</b>。'
      '以 enx_breaks.csv 为准，不照抄口传。'
    + ('其中 2025-11 的 Athens 并表可以<b>定量还原</b>（官方给了备注列），见 Exhibit 11；'
       '2021-05 的 Borsa Italiana 没有备注列，只能标不能还原。' if HAS_ATH else '')
    + 'RED 在这套配色里是<b>断点与截轴离群值的专用色</b>，一律不做数据色。',

    '<b>份额变化图为什么是单色。</b>引擎的 <code>diverging_bars</code>（正负分色柱）把 COST 的'
    '业务文案写死在里面：图例固定「Reported &gt; Core（油汇顺风）」/「Reported &lt; Core'
    '（油汇拖累）」，表格视图列名固定「Reported − Core」，<code>ex.legend</code> 被忽略'
    '（<code>assets/charts.js</code> 第 1437 / 1522–1523 行；详见 '
    '<code>docs/CHART_KINDS.md</code> §3.4）。交易所份额页上会凭空出现「油汇」两个字。'
    '引擎不能动（14 页共用，改一行要重新验收 14 页），所以 Exhibit 5 改用'
    '<b>只放一个 group 的 grouped_bars</b>：图例名与表格列名都能自定义，'
    '纵轴照样容纳负柱。代价是正负不分色 —— 按变化降序排之后分界一眼就在，损失有限。'
    '不能用 <code>bars_labeled</code> 代替：它强制零基线，负柱会被画到画布外。',

    '<b>颜色：一家一色，全页不换。</b>'
    + '、'.join(f'{SHORT[k]} = {COLOR[k]}' for k in KEYS)
    + f'；本池合计 = {TOTAL_C}；Nasdaq 北欧 = {NDAQ_C}；当期汇率对照线 = {CUR_FX_C}。'
      '引擎的数据色只有 NAVY / BLUE / MBLUE / GRAY / GREEN / GOLD 六个'
      '（RED 是断点专用，不做数据色）。'
      f'Nasdaq 北欧与当期汇率对照线<b>共用 {CUR_FX_C} 这一个色名</b>，跨图复用。'
    + f'现扫本轮 payload，用到它的是：'
    + '；'.join(f'Exhibit {n}（{"、".join(nm)}）' for n, nm in _SHARED_C)
    + '。'
    + (f'Nasdaq 北欧那条线只出现在 '
       + '、'.join(f'Exhibit {n}' for n in _SHARED_ND) + '。'
       if _SHARED_ND else '本轮没有画 Nasdaq 北欧。')
    + ('<b>没有任何一张图里它同时是 Nasdaq 和别的序列</b>，'
       '所以在单张图内部读者不会把两者认混 —— 这就是复用色名的全部前提，'
       '判据现算，不靠记忆枚举图号。'
       if not _SHARED_CLASH else
       '⚠ ' + '、'.join(f'Exhibit {n}' for n in _SHARED_CLASH)
       + ' 里这个色名同时承担了两种含义，必须改色。')
    # ⚠ 这两句原先写的是裸的「15 的两段」「16 的柱」，不从 VP_N_DEC / VP_N_TRD 取；
    #   HAS_VP=True 时刚好是真号，所以渲染看不出问题，但只要在 15 号之前插一张图，
    #   正文与 ex.append 会跟着常量顺推、唯独这两句留在原地 —— 那正是本文件上面那条
    #   「图号全文件唯一一处」注释保证不会发生的事。改成从常量取，让那条注释成立。
    + (f'⚠ {EX_VP2} 是<b>单成员图</b>（只有 Euronext），成员色在那里不承担辨识职能：'
       f'{VP_N_DEC} 的两段用 {COLOR["enx"]}（成交笔数）与 BLUE（每笔均值）'
       f'—— 同一色系一深一浅，表示它们是同一个恒等式的两半，不是两个成员；'
       f'{VP_N_TRD} 的柱沿用 Euronext 的 {COLOR["enx"]}，'
       f'增速线用 {CUR_FX_C}（本页的辅助线色），与 Nasdaq 不同图，不冲突。'
       if HAS_VP else ''),

    f'<b>核对表（Exhibit {table["n"]}）用各家官方披露的原始计量单位与币种，一个换算都不做。</b>'
    '这张表存在的唯一理由是让人拿它与官方新闻稿逐位对账：'
    'Deutsche Börse 那两列是<b>月度总额</b>（其余各家是日均），所以并排给了现货交易日，'
    '日均 = 总额 ÷ 交易日；窄口径的 Xetra 股票列也列出来，让人自己复算 Exhibit 12 的比值；'
    'Nasdaq 北欧那列是<b>美元当月合计</b>，配一列 ECB 月均 EUR/USD，'
    '让人自己复算 Exhibit 9 的欧元读数。'
    + (f'最后两列是 {EX_VP2} 用的那一对（<code>{VP_VAL_COL}</code> 全部现货金额、'
       f'<code>{VP_TRD_COL}</code> 成交笔数），让人自己复算分解的分子分母；'
       f'注意<b>金额单边计、笔数双边计</b>，两者相除得到的每笔均值'
       f'<b>不是</b>可以直接读的水平值（理由见分解那一条）。' if HAS_VP else '')
    + f'表同样只到 {mlab(LATEST)}，与全页门槛一致。',
]

# ══════════════════════════════════════════════════════════════════════════════
# 11b. 名词释义（payload 的 `glossary`，排在所有 exhibit 之前）
#
# ━━ 与页尾 notes / 图注的分工 ━━
# notes 与图注说的是「这一张图这个月该怎么读」（含当月读数、当月实测的毛刺量）；
# 这一块说的是「这些词是什么意思」，一年到头是同一段 ⇒ 这里**不写当月读数**，
# 一个「最新一期」都不出现。要写数只写两类：把定义钉住的**结构性**量
# （宽窄口径的倍数、占比被高估多少 pp、定基汇率的常数值、ln2）与**恒等式本身** ——
# 且**一个都不写死**，全部取运行时已经算好的那些量（SCOPE_* / SH_GAP_* /
# SHARE_ADV_MAXGAP / EURUSD_BASE / DAYS_SAME / VP_LN2 / VP_SC_*），
# 与图注、页尾 notes 同源同值，改不出两个版本。
# ⚠ 同一条规矩也管**结构形状**，不只管数字：窄口径「缺哪几段月」取 _NAR_GAP_TXT
#   （与 Exhibit 12 图注同一个 _gap_txt），有值月数取 len(_NAR_OK)。
#   这一处原先写死成「中间断成两截」，而 2026-08-18 db1 回补之后实际是三截两洞 ——
#   写死的形状与写死的数一样会过期，且 glossary 一年到头不动，过期了没人会发现。
#
# ━━ 为什么是这 15 个词（选词判断）━━
# 判据只有一条：这个词出现在本页的图题 / 序列名 / 纵轴 / 汇总表行头 / 图注里，
# 而且**不看定义就会读错**。按「读错会出什么事」分五类：
#   ① 分母是谁   池内相对占比、市场份额 / 自报市占、SI、泛欧 MTF ——
#      本页最贵的一类坑，全部集中在这里。本页的「占比」分母是**本池三家之和**，
#      不是泛欧市场；读者若把它当市场份额，会把一个系统性高估的数当成竞争结论，
#      再拿它去与 Nasdaq 自报的「欧洲市占」并排，得出方向完全相反的结论
#      （Exhibit 10 就是这张算术图）。SI 与 MTF 是「分母为什么不全」与
#      「三家为什么争的是同一批订单流」的两个必要前提，缺一句这一类就讲不完整。
#   ② 同一件事的两套口径   ADNV、宽口径 / 窄口径、单边计 / 双边计 ——
#      两套口径都在页面上，读串的代价是整条线系统性偏高或偏低，而图形完全正常。
#   ③ 本页自己造的派生量   定基名义额、汇率贡献、指数化、量加权 ——
#      不是任何一家公司披露的数，是本页轧出来的；尤其「指数化」与「同比」
#      是两回事（页尾 notes 第 6 条专门点过），不点破会被当成一种东西读。
#   ④ 时间轴与发布规则   共同最新月 / 短板 —— 本页横截面的发布门槛，
#      不点破读者会以为某一家「这个月没数」。
#   ⑤ 单成员分解那两张图的专名   每笔均值、对数分解、Athens 备注列 ——
#      「每笔均值」最容易被读成「价」（它不是），「对数分解」的百分比不是普通百分比，
#      「备注列」是官方披露里的一个字段名、读者在别处见不到。
# **有意不收**：
#   · m/m、y/y、单月同比、3Y %ile、pp/bp —— 全站通用的读图约定，
#     summary.note 与页尾 notes 第 6 条已经逐条讲过（还带本页实测），
#     释义板再讲一遍就是两处各写一份，且那两处会随口径改动更新、这里不会。
#   · 「口径断点」「并表」—— 页尾 notes 第 9 条讲的是这两件事在本页的**具体落点**
#     （哪几张图画了几条红线、污染几个读数），是当期事实不是词义。
#     这里只留「Athens 备注列」一条，因为它是官方披露的**字段**，不是本页的排版决定。
#   · 成交额、市值、交易日这类本页没有特殊口径的常识词。
# ══════════════════════════════════════════════════════════════════════════════
_G_SCOPE = (
    f'重叠月实测宽 ÷ 窄 = <b>{SCOPE_MIN:.2f}–{SCOPE_MAX:.2f} 倍</b>'
    f'（中位 {SCOPE_MED:.2f}），折成池内占比，Deutsche Börse 被<b>高估 '
    f'{SH_GAP_MIN:.1f}–{SH_GAP_MAX:.1f}pp</b>（中位 {SH_GAP_MED:.1f}pp）。'
    if HAS_NAR_WIN else '')

GLOSSARY = [
    # ① 分母是谁 ────────────────────────────────────────────────────────────
    ('池内相对占比',
     '本页所有「占比」的口径：<b>分母 = 本池三家之和</b>'
     '（Euronext + Cboe Europe + Deutsche Börse 各自披露口径的成交额相加），'
     '<b>不是</b>泛欧市场的合并量。它<b>不含 SI、不含第三方暗池与 OTC、'
     '不含 LSEG / Turquoise / Aquis / SIX 等本池之外的场所</b>，'
     '因此<b>系统性高估</b>这三家在真实泛欧成交里的比重，'
     '只能读作「这三家披露口径之和里谁占多少」。'
     '三段之和恒为 100%（本池没有「其余场所」这一段，而真实市场里那一块很大）。'
     '⚠ 占比建在<b>当月成交额</b>上，不建在日均上：各家休市日不同，'
     f'照日均算等于给休市多的那家加权，实测最大虚高 <b>{SHARE_ADV_MAXGAP:.2f}pp</b>。'),

    ('市场份额 / 自报市占',
     '<b>本页一处都没有真正的市场份额</b> —— 「市场份额」四个字凡出现都是在否定它，'
     '因为含 SI 与暗池的泛欧合并量目前在制度上还不存在'
     '（MiFIR 要求的股票合并信息带尚未开始发布；四条替代路径为什么都不合格，'
     '见页尾口径说明）。⚠ 另一处同名不同物：Nasdaq 在季度面板里自报的'
     '「欧洲现货市占」有官方<b>口径</b>（8-K 脚注原文把它限定为瑞典、丹麦、芬兰、'
     '冰岛的现货股票交易所），但<b>分母那个数官方一个都不发</b> —— '
     '只能拿它自报的成交额 ÷ 它自报的份额<b>反推</b>出来（页面上专门有一张图画这件事）。'
     '反推出的那个「欧洲市场」是<b>北欧+波罗的海</b>，与本页的池内占比是两个宇宙。'
     '⇒ 本页对 Nasdaq 的规矩是<b>绝对值可比、份额不可比</b>，'
     '它一个数都不进本页任何份额的分子或分母。'),

    ('SI（系统内部撮合商）',
     'Systematic Internaliser：MiFID II 下用<b>自有账户</b>与客户成交的投资公司'
     '（券商与做市商），成交不经任何交易场所的订单簿撮合。'
     '它是本页分母缺的那一大块之一 —— <b>这三家的披露口径里没有它</b>，'
     '而真实的泛欧成交里它与暗池、OTC 合起来占比不小。'
     '⇒ 本页的占比是「三家之间的相对位置」，不是「谁从整个欧洲拿走了多少」。'),

    ('泛欧 MTF',
     'Multilateral Trading Facility（多边交易设施）：MiFID II 下与受监管市场（RM）'
     '并列的另一类交易场所，把多方的买卖意向按规则撮合成合约。'
     'Cboe Europe 是泛欧 MTF，撮合的正是 Euronext 与 Xetra <b>上市</b>的那批股票，'
     '它自己<b>不是</b>这批股票的上市地；'
     'Xetra 只覆盖德国上市。MiFID II 之下任何欧洲股票可以在任何场所交易，'
     '⇒ 三家<b>争的确实是同一批订单流</b>，这才是本页可以算占比、'
     '而法域隔离的亚太页不可以的原因。'),

    # ② 同一件事的两套口径 ──────────────────────────────────────────────────
    ('ADNV',
     'average daily notional value，<b>日均名义成交额</b>（€bn/日）。'
     'Euronext 与 Cboe Europe 的头条列<b>逐字同口径</b>（股票现货、<b>单边计</b>）。'
     '⚠ 三家日均的<b>来路并不相同</b>，只有一家是官方直接印的：'
     'Cboe Europe 取的就是官方那一行 ADNV，一天都不除；'
     'Euronext 与 Deutsche Börse 官方给的都是<b>当月总额</b>，'
     '日均一律是<code>当月成交额 ÷ 官方现货交易日</code> —— '
     'Euronext 这一步在入库时就做完了'
     '（<code>Turnover Equities</code> ÷ <code>Nb of trading days</code>，'
     '见 <code>docs/verify/enx.md</code>），Deutsche Börse 这一步在本页做。'
     '⇒ 核对表把 Deutsche Börse 的当月总额与现货交易日<b>并排给出</b>，可以自己复算。'),

    ('宽口径 / 窄口径',
     '专指 Deutsche Börse 这一家的两套现货列，本页最大的一处妥协。'
     '<b>宽口径</b>（Xetra + Börse Frankfurt 全部现货，含 ETP / 结构化产品 / 债券 / 基金）'
     f'有 {DB1_WIDE_N} 个月历史（{DB1_WIDE_FROM} 起），本页各图用的是它；'
     '<b>窄口径</b>（Xetra 股票 + FWB 股票）与另两家逐字同口径，但有数的月份少得多'
     + (f'（{len(_NAR_OK)} 个）' if _NAR_OK else '')
     + '、而且中间有<b>整段缺月</b>'
     # 缺月的段落形状**现算**（与 Exhibit 12 图注同源 _gap_txt），不写死：
     # 2026-08-18 db1 那次回补就把它从「2024-12 起连续 20 个月」变成了
     # 「2016-06 起、中间两大段空洞」。glossary 一年到头不动，写死下次回补就成假话。
     + (f'（{_NAR_GAP_TXT}）' if _NAR_GAP_TXT else '')
     + '，撑不起长历史份额图。'
     + _G_SCOPE
     + '⇒ <b>本页 Deutsche Börse 的占比读作上界，Euronext 与 Cboe Europe 读作下界</b>。'
       '增长率不受影响（宽口径只是整条线乘一个近似常数）。'),

    ('单边计 / 双边计',
     '两种计数惯例，本页两种都在用：<b>单边计</b>（一笔成交只计一次）用于三家的'
     '成交<b>金额</b>列；<b>双边计</b>（同一笔成交按买、卖各计一次）用于 Euronext 的'
     '成交<b>笔数</b>列（官方分组名 <code>Transactions (buy and sell)</code>，'
     '<code>docs/verify/enx.md</code> 口径坑 6）。'
     '⇒ 两列相除得到的<b>不是</b>每笔真实成交额，本页因此<b>不印它的绝对水平</b>；'
     '而增长与分解不受影响（对笔数乘任何常数结果完全不变）。'
     '笔数的<b>水平值</b>也只能按交易所自己的惯例读，不要拿去与别家的「笔数」比大小。'),

    # ③ 本页自己造的派生量 ──────────────────────────────────────────────────
    ('定基名义额',
     '<b>不是公司披露的数</b>，是本页轧出来的：<code>本币成交额 × 锁死的基期月均汇率'
     f'</code>，基期取 {mlab(BASE_P)}（全仓统一），EUR/USD = <b>{EURUSD_BASE:.4f}</b>。'
     '锁汇率是为了让「量」的变化里一分钱汇率都不混进来。'
     '⚠ 本页三家<b>全部以欧元披露</b> ⇒ 那个汇率对每一家都是<b>同一个常数</b>，'
     '所以定基口径的指数图与直接画欧元的指数图<b>逐点相同</b>；'
     '美元那一组只是把同一批欧元读数换个单位看量级。'),

    ('汇率贡献',
     '<code>当期汇率口径 ÷ 定基汇率口径 − 1</code>：两条线的<b>欧元输入完全相同</b>，'
     '唯一差别是用哪个月的 EUR/USD，所以两者之差就是汇率本身。'
     '在单一币种池里这个差<b>恒等于</b> EUR/USD 相对基期的累计变动 —— '
     '页面上专门画了一张自检图，两条线必须逐点重合（偏差只在浮点舍入量级）。'
     '⚠ <b>当期汇率那条线不进本页任何增长图与占比图</b>：它的同比里混着汇率波动。'
     '哪天这两条线分开，说明池里混进了非欧元成员，那时所有占比图都必须停掉。'),

    ('指数化',
     f'把一条序列除以它在<b>基期月</b>（{mlab(BASE_P)}，全仓统一）的读数再乘 100，'
     '画的是<b>相对基期的累计变动</b>。⚠ <b>指数化不是同比</b>：同比答「对去年同月」，'
     '指数答「对那个固定的基期月」，两者不能并排读。'
     '本页窗口的起点早于基期月，所以基期之前那一段线在 100 上下摆动是正常的，不是错。'
     '增长率的比较<b>不受口径宽窄影响</b>（宽口径只是整条线乘一个常数），'
     '所以在指数图上 Deutsche Börse 那条线是可比的，而它在占比图上是高估的。'),

    ('量加权',
     '季度占比的算法：<code>该季三个月成交额之和 ÷ 该季池合计</code>，'
     '<b>不是</b>三个月占比的算术平均。取平均会让 18 个交易日的 12 月与 23 天的 3 月'
     '等权，把日历噪音读成份额变化。月长权重取 Euronext 的 '
     '<code>trading_days_cash</code>（欧元区口径），'
     f'它与 Deutsche Börse 的同名列在本页窗口内 <b>{DAYS_SAME}/{DAYS_N} 个月完全相同</b>。'
     '窗口两端不满三个月的<b>残季一律不画、不年化</b>。'),

    # ④ 时间轴与发布规则 ────────────────────────────────────────────────────
    ('共同最新月 / 短板',
     '横截面页的<b>发布门槛</b>：全页统一截到三家现货序列里<b>最慢那家</b>的最新月，'
     '这个月叫共同最新月，卡住它的那家叫短板。'
     '<b>跑在前面那家的最新一个月不在本页任何一张图、任何一行表里</b> —— '
     '各家披露节奏差一两周，若各画各的最新月，读者会拿一家的 7 月去比另一家的 6 月，'
     '看到的「谁在拿份额」有一整个月是口径造出来的。'
     '同一条规矩管左端：<b>共同起点由披露起点最晚的那一家决定</b>，'
     '它是本页历史长度的天花板。'),

    # ⑤ 单成员分解那两张图的专名 ────────────────────────────────────────────
    ('每笔均值',
     '<code>成交额 ÷ 成交笔数</code>，恒等式 <code>成交额 ≡ 笔数 × 每笔均值</code> '
     '的第二项。⚠ <b>它不是价</b>：它反映的是<b>订单碎片化程度</b>（一张单子多大 —— '
     '算法切单、暗池与大宗的进出、并表带进来的新市场结构），'
     '<b>不是</b>指数收益率，也<b>不是</b>加权平均股价。'
     '真正的「股数 × 均价」需要成交股数列，本页三家<b>一列都没有</b>，'
     '⇒ 页面上一处都不把它叫「价」，也不印它的绝对水平（理由见单边计 / 双边计那条）。'
     + (f'另外，配对的金额列是 Euronext 的<b>全部现货</b>，比本页头条那一列宽 —— '
        f'头条列只占它的 {VP_SC_MIN:.0f}–{VP_SC_MAX:.0f}%（中位 {VP_SC_MED:.0f}%）。'
        if HAS_VP else '')),

    ('对数分解',
     '把成交额的增长拆成「笔数」与「每笔均值」两段所用的算法（LMDI，对数平均权重）。'
     '选它是因为算术分解那一路会剩一个<b>交叉项</b>，在两头几乎对冲的年份里'
     '它能比净增长本身还大，塞进任一侧都是任意分配；对数分解<b>没有残差</b>，'
     '两段之和恒等于总增长。'
     f'代价：<b>对数增长率不是普通百分比</b> —— 成交额<b>翻一倍</b>在对数口径里记成 '
     f'+{VP_LN2 * 100:.1f}%，不是 +100%。'
     '⚠ 这张图的端点一律是<b>12 个月合计</b>（完整自然年，末列是 TTM），横轴是<b>年</b>，'
     '与逐月画读数的同比图问的不是同一个问题，两者不要并排读。'),

    ('Athens 备注列',
     'Euronext 在官方表里为 Athens 单开的一列，是本页唯一<b>可以定量还原</b>的口径断点：'
     '主列与它相减即得「与并表前同口径」的序列。'
     '⚠ 这一列的语义在断点<b>前后不同</b>：并表之前它是<b>尚未进主列</b>的部分'
     '（此时去减就是把它减了两次，会画出一道全程存在的假缺口），'
     '并表起才是<b>已经含在主列里</b>的那部分。'
     + (f'⚠ 备注列自 {mlab(ATH_START)} 才有，更早的历史没有还原条件；'
        if HAS_ATH else '')
     + 'Euronext 其余几次并表（Dublin / Oslo / Borsa Italiana）<b>没有</b>对应的备注列，'
       '只能在图上标出断点，<b>无法定量还原</b>。'
       '<b>本页其余各图用的都是官方主列</b>，不做私自还原。'),
]

# ────────────────────────── 12. 抬头与 payload ──────────────────────────
# 抬头的同比用**单月**口径（当月 ÷ 去年同月 − 1，建在日均上），与汇总表那一组行、
# Exhibit 13 / 14 及成交笔数图的右轴线是**同一把尺子、同一批数**。
# ⚠ 抬头原先印的是 12 个月滚动合计 y/y。抬头是全页曝光最高的一行，上面写滚动、
#   下面图上画单月，正是 CONTRACT §6 抬头那条审计发现说的自相矛盾（cme Ex2 说 +19.1%、
#   同页 Ex8 说 −1.2%），所以 2026-09 全站改口径时抬头一并换掉。
#   对照的滚动读数**只留在图注里以数字出现**（§6.1 第 3 条），抬头一个都不印。
# m/m 与单月同比在抬头里各自带全称：一个答「这个月对上个月」，一个答「对去年同月」，
#   两者不是同一个问题，名字不能省。
# 📌 抬头里的「季度口径 1Q16 → 2Q26」那一段是**占比的季度对比（pp）**，不是任何一种同比，
#   与本轮口径改动无关，一个字没动。
_yoy_now = {k: float(YOY[k][CUR]) for k in KEYS if ok(YOY[k][CUR])}
_rank = sorted(_yoy_now.items(), key=lambda kv: -kv[1])
_mom = {k: (float(ADV[k][CUR]) / float(ADV[k][PRV]) - 1) * 100 for k in KEYS if ok(ADV[k][PRV])}
_neg = [SHORT[k] for k, v in _mom.items() if v < 0]
_share_top = max(((k, float(SHARE[k][CUR])) for k in KEYS), key=lambda kv: kv[1])
_share_d = float(QSHARE[_share_top[0]].iloc[-1]) - float(QSHARE[_share_top[0]].iloc[0])

SOURCE_DATE = load_source_dates().latest_of(SERIES, KEYS, {k: LATEST for k in KEYS})

payload = {
    'ticker': TICKER,
    'tracker': 'European Cash Equities Cross-Section — Euronext / Cboe Europe / Deutsche Börse',
    'title': f'欧洲现货股票竞争：同一批订单流，谁在拿走 — {zh(LATEST)}',
    'data_through': str(LATEST),
    'through_label': f'{zh(LATEST)}（共同最新月）',
    'subtitle': (f'数据源：三家官方月度披露 + Nasdaq 北欧对照 + ECB 汇率 · '
                 f'共同窗口 {mlab(START)} – {mlab(LATEST)}（{len(IDX)} 个月 / '
                 f'{len(QIDX)} 个完整季）· 三家同币同市场，占比可算 · '
                 # subtitle 走 page.js 的 set()，它用的是 textContent —— 标签会被原样印成
                 # 「<b>…</b>」的字面量（实测截图确认）。要强调只能靠措辞，不能靠 HTML。
                 # 页面上允许 HTML 的字段是 note / notes / summary 的 cell 与 label（innerHTML）。
                 f'但分母 = 本池三家之和，不含 SI 与暗池，不是市场份额 · '
                 f'发布门槛取成员共同最新月，短板 {"、".join(LAG)} · '
                 '版式仿 Goldman Sachs GIR · 仅图，无评论'),
    'headline': ('池内相对占比：'
                 + '、'.join(f'{SHORT[k]} {float(SHARE[k][CUR]):.1f}%' for k in KEYS)
                 + f'（分母 = 三家之和，不含 SI 与暗池）'
                 + f' · 季度口径 {qlab(_q0)} → {qlab(_q1)}：'
                 + '、'.join(f'{SHORT[k]} {pp(float(QSHARE[k].iloc[-1]) - float(QSHARE[k].iloc[0]))}'
                             for k in KEYS)
                 + ' · 单月 y/y（当月 ÷ 去年同月）：'
                 + '、'.join(f'{SHORT[k]} {pct(v)}' for k, v in _rank)
                 + ' · 当月环比 m/m（对上个月，与上面那组同比不是一把尺子）：'
                 + '、'.join(f'{SHORT[k]} {pct(v)}' for k, v in _mom.items())
                 + ('（三家 m/m 均为正）' if not _neg else f'（{"、".join(_neg)} 环比下滑）')
                 + (f' · Nasdaq 北欧只有 Cboe Europe 的 1/{ND_RT_MED:.1f}'
                    if HAS_NDAQ else '')
                 + (f'，其自报的欧洲市占 {ND_SHARE_LAST:.1f}%（{qlab(QN[-1])}）是'
                    f'北欧+波罗的海口径，与本页任何占比都不可比'
                    if HAS_NDQ else '')),
    'glossary': gloss.render(GLOSSARY, where='exchanges-eu glossary'),
    'hub_line': (f'共同最新月 {mlab(LATEST)}（短板 {"、".join(LAG)}）；'
                 f'池内占比领先 {SHORT[_share_top[0]]} {_share_top[1]:.1f}%'
                 f'（季度口径自 {qlab(_q0)} {pp(_share_d)}）；'
                 f'分母 = 三家之和，非市场份额'),
    'source': SRC,
    'xlabels': [mlab(p) for p in IDX[-TBL_MONTHS:]],
    'xlabels_long': XL_LONG,
    'summary': summary(),
    # 轴刻度小数位：引擎默认格式器把 2.5 印成「3」、把 0.5% 步长整列印成重复数字，
    # 判据与算法见 build/axisfmt.py（与 build/single.py 共用同一份）。
    'exhibits': axisfmt.fix_all(ex),
    'table': table,
    'notes': NOTES,
    'footer': (f'欧洲现货股票竞争 · {" / ".join(SHORT[k] for k in KEYS)}'
               f'（Nasdaq 北欧只做绝对值对照，不进任何份额）· '
               f'<b>发布门槛：共同最新月 {mlab(LATEST)}</b>，本期短板 {"、".join(LAG)} —— '
               '本页所有图表一律截到此月，'
               + (f'跑在前面的 {"、".join(f"{d}（已更新至 {mlab(m)}）" for d, m in AHEAD)} '
                  '的最新月份未纳入本页。' if AHEAD else '本期三家最新月一致。')
               + '<b>所有占比的分母 = 本池三家之和，不含 SI、暗池与本池之外的场所，'
                 '因此系统性高估三家的合计比重；这不是市场份额</b>'
                 '（为什么拿不到泛欧合并分母，见口径说明第 2 条）· '
                 'Deutsche Börse 的口径比另两家宽，其占比读作上界（Exhibit 12 给出实测幅度）· '
                 'charts only, no commentary · personal research use'),
}
if SOURCE_DATE:
    payload['source_date'] = SOURCE_DATE          # 查不到就整个字段省掉，渲染端判的是存在性


def main():
    payload_guard.write_dash(OUT, payload, TICKER)
    print(f'共同最新月 {LATEST} | 各家: '
          + ', '.join(f'{SHORT[k]}={latest_each[k]}' for k in KEYS))
    print(f'短板 {"、".join(LAG)} | 共同窗口 {START} → {LATEST}'
          f'（{len(IDX)} 个月 / {len(QIDX)} 个完整季，约 {QSPAN_Y:.1f} 年）')
    print(f'换算对账：{len(FX_CHECK)} 个欧元金额类产品与 contract_specs.csv 相等；'
          f'EUR/USD 基期 {EURUSD_BASE:.6f}')
    print(f'池内占比 {mlab(CUR)}：'
          + '、'.join(f'{SHORT[k]} {float(SHARE[k][CUR]):.2f}%' for k in KEYS)
          + '（分母 = 三家之和，非市场份额）')
    print(f'季度份额 {qlab(_q0)} → {qlab(_q1)}：'
          + '、'.join(f'{SHORT[k]} {float(QSHARE[k].iloc[0]):.2f}% → '
                      f'{float(QSHARE[k].iloc[-1]):.2f}%' for k in KEYS))
    print(f'Euronext 窗口内断点 {[str(p) for p in ENX_BRK]} {ENX_BRK_TXT}'
          + (f'；{ENX_BRK_WHY}' if ENX_BRK_WHY else ''))
    print(f'欧元区月长权重 enx vs db1 trading_days_cash 一致 {DAYS_SAME}/{DAYS_N} 个月')
    if HAS_NAR_WIN:
        print(f'DB1 口径宽/窄 {SCOPE_MIN:.3f}–{SCOPE_MAX:.3f}（中位 {SCOPE_MED:.3f}），'
              f'占比高估 {SH_GAP_MIN:.2f}–{SH_GAP_MAX:.2f}pp（中位 {SH_GAP_MED:.2f}pp），'
              f'重叠 {len(W_NAR)} 个月')
    if HAS_NDAQ:
        # 倍数是在 `_ND_OK`（真有值的月）上算的，报的月数就得是它 —— 报 len(W_ND)
        # 会在横轴出洞那天说「127 个月」而统计量其实只用了 68 个。
        print(f'Nasdaq 北欧 vs Cboe Europe 月度总额倍数 {ND_RT_MIN:.2f}–{ND_RT_MAX:.2f}'
              f'（中位 {ND_RT_MED:.2f}），{len(_ND_OK)} 个有值月 / 横轴 {len(W_ND)} 个月')
    if HAS_NDQ:
        print(f'Nasdaq 自报份额隐含分母 vs Cboe 一家 {ND_QR_MIN:.2f}–{ND_QR_MAX:.2f} 倍'
              f'（中位 {ND_QR_MED:.2f}），{len(QN)} 个季；自报份额 {ND_SHARE_LAST:.1f}%')
    print(f'汇率恒等式自检 max|gap − EURUSD move| = {FX_IDENT_MAX:.3e} pp')
    print(f'滚动同比链自检 max|MON_FULL − MONTHLY_EUR| = {MON_CHAIN_MAX:.3e} €bn')
    print('同比口径实测（单月 vs 12 个月滚动，统计量由 yoy.caliber_diff 出）：')
    for k in DIAG_OK:
        d = DIAG[k]
        print(f'  {SHORT[k]:<15s} n={d["n"]:>3d}  sd 单月 {d["std_mom"]:5.2f} / '
              f'滚动 {d["std_ttm"]:5.2f}（{d["std_ratio"]:.2f}×）  相邻月最大跳变 '
              f'{d["maxjump_mom"][0]:5.1f}pp@{d["maxjump_mom"][2]} / '
              f'{d["maxjump_ttm"][0]:4.1f}pp@{d["maxjump_ttm"][2]}  '
              f'中位跳变 {d["medjump_mom"]:.1f}/{d["medjump_ttm"]:.1f}pp  '
              f'符号相反 {d["opposite_n"]}/{d["n"]}'
              f'（{d["opposite_n"] / d["n"] * 100:.0f}%），'
              f'断点洁净子集 {d["flip_clean"]}/{d["n_clean"]}')
    if DIAG['_tot']:
        d = DIAG['_tot']
        print(f'  {"本池合计":<13s} n={d["n"]:>3d}  sd 单月 {d["std_mom"]:5.2f} / '
              f'滚动 {d["std_ttm"]:5.2f}（{d["std_ratio"]:.2f}×）  符号相反 '
              f'{d["opposite_n"]}/{d["n"]}（{d["opposite_n"] / d["n"] * 100:.0f}%）')
    print(f'  单月同比建在日均 vs 建在月度合计（纯日历效应）max {MOM_DAYGAP_MAX:.1f}pp / '
          f'中位 {MOM_DAYGAP_MED:.1f}pp；诊断的滚动侧（日均等权相加）vs 图注对照数'
          f'（YOY12，月度链）max {TTM_CHAIN_GAP_MAX:.2f}pp / 中位 {TTM_CHAIN_GAP_MED:.2f}pp')
    if FLIP_EX:
        print(f'  符号相反的最极端一例（断点洁净）：{SHORT[FLIP_EX[3]]} {FLIP_EX[0]} '
              f'单月 {FLIP_EX[1]:+.1f}% vs 滚动 {FLIP_EX[2]:+.1f}%')
    print('现货数量列扫描（判定谁能做成交额分解）：')
    for k in KEYS:
        print(f'  {SHORT[k]:<15s} {QTY_SCAN[k] or "（一列都没有）"}')
    print(f'  Cboe Europe 全部数量类列 = '
          f'{[c for c in (RAW["cboe"].columns if RAW["cboe"] is not None else []) if "shares" in c]}'
          f' → 美国口径，与本页的泛欧 ADNV 不同覆盖范围，不成对')
    if HAS_VP:
        print(f'Euronext 成交额分解（笔数 × 每笔均值，**不是量价分解**）：'
              f'{len(VP_LAB)} 列 {VP_LAB[0]}–{VP_LAB[-1]}')
        print(f'  成对性：{VP_VAL_COL} 与 {VP_TRD_COL} 断点集合相同 '
              f'{sorted(str(x) for x in VP_BRK_VAL)}')
        print(f'  计数惯例稳定性：{VP_CONV_N} 个非断点月，max|Δln(每笔均值)| = '
              f'{VP_CONV_MAX * 100:.1f}% < ln2/2 = {VP_LN2 / 2 * 100:.1f}% ⇒ 未翻转'
              f'（最大发生在 {VP_CONV_AT}）')
        print(f'  恒等式残差 对数 {VP_RES:.3e}pp / 算术 {VP_RES_B:.3e}pp；'
              f'汇率不变性 {VP_FX_MAX:.3e}pp；数量列常数缩放不变性 {VP_SCALE_MAX:.3e}pp')
        print(f'  对数 vs 算术 贡献最大差 {VP_AL_MAX:.2f}pp；总增长两口径最大差 '
              f'{VP_LT_B_MAX:.2f}pp；交叉项占 ΔV 中位 {VP_CR_MED:.1f}% 最大 '
              f'{VP_CR_MAX:.0f}%（{VP_CR_AT}）')
        print(f'  头条列占配对列 {VP_SC_MIN:.1f}–{VP_SC_MAX:.1f}%（中位 {VP_SC_MED:.1f}%）；'
              f'末列 {VP_LAB[-1]}：笔数 {VP_LV[-1]:+.2f}% + 每笔均值 {VP_LM[-1]:+.2f}% '
              f'= {VP_LT[-1]:+.2f}%（对数）')
    else:
        print(f'成交额分解未生成：{"；".join(VP_WHY)}')
    print(f'发布日 source_date = {SOURCE_DATE or "（成员里有查不到的，整字段省略）"}')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张）+ '
          f'Exhibit {table["n"]} 核对表')
    print(f'写出 {OUT}（{os.path.getsize(OUT) / 1024:.1f} KB）')
    print(payload['headline'])


if __name__ == '__main__':
    main()
