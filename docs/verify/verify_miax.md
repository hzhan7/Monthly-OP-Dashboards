# 复核报告：MIAX 月度数据源侦察（/tmp/exch_recon/miax.md）

复核日期 2026-08-06 ｜ slug `miax` ｜ 原判定 **B** ｜ **最终判定 B（维持）**

复核工作区：`/private/tmp/claude-501/-Users-hainan-Library-CloudStorage-OneDrive-Personal/00bde884-5d9d-4ce5-a363-6b721a0462f5/scratchpad/vmiax/`
（未复用上一个 agent 的 `/tmp/exch_recon/scratch/miax/` 任何产物；PDF 重新下载、解析器
`vparse.py` / `vapi.py` 从零重写，用 x 坐标分桶而非 token 顺序。）

---

## 一、结论

**维持 B。** 这份侦察是我复核过的少见的「基本诚实」的一份：核心数字我全部独立复现，
关键交叉核对（新闻稿 9/9、10-K 5 项、API 136 个月）都真实存在且对得上。
四类虚报——第三方源冒充官方、只抓最新期谎称有历史、依赖浏览器登录态、口径写反——
**一条都不成立**。

但它有 **9 处事实错误**，其中 3 处会直接伤到实现（source_date 取错、重述护栏漏列、
列表页选链取错），必须在动手前修掉。这些错误不足以降级到 C（抓取本身零阻力、
全部可无人值守复现），但也说明「B」这个结论是对的而它给的**理由并不完整**。

不是 A 的真正原因（与原文一致，我确认成立）：
- 最有价值的字段 `rpc_multilist_options_usd` **只有 2025-01 起 18 个月**（不是原文说的 19 个月：
  2025-01…2026-06 有值，2026-07 因滞后为空），而 Cboe 同名列有 **2016-01 起 126 个月**
  （2026-08-19 实测；本文写作时是 2017-01 起 114 个月，2026-08-18 那一轮把 cboe 回补到了 2016-01）。
  并排画图的重叠窗口只有 18 个月，做不了同比。
- PDF 数字被拆词的陷阱是真的，且**静默**出错（见下）。

---

## 二、独立复现的证据

### 2.1 抓取：全部零阻力复现，纯 curl / urllib，无浏览器、无 cookie、无登录

| 检查 | 我的实测 | 与原文 |
|---|---|---|
| `ir.miaxglobal.com/volume-rpc-reports` + Chrome UA | HTTP 200，0.17s | 一致 |
| 同一 URL + 默认 `Python-urllib/3.x` | **HTTP 403** | 一致 |
| PDF 直链 302 → `filecache.investorroom.com/mr5ir_miaxglobal/{n}/` | 一致 | 一致 |
| `{n}` 是否稳定 | 我拿到 **253**，原文写 252（同一文件） | 反而**加强**了「不可猜」的结论 |
| `www.miaxglobal.com/indsum/*` | 无 UA 校验，纯 JSON | 一致 |
| 是否需要 curl_cffi / nscurl / Chrome MCP | **不需要** | 一致 |

**攻击 (c)「用了浏览器登录态」不成立** —— 我全程只用 `curl` 与标准库 `urllib`，
无 cookie、无 JS、无人工点击，全部成功。cron 可跑。

### 2.2 攻击 (b)「第三方聚合站冒充官方」——不成立

实际用到的源只有四个，全部是一手：
`ir.miaxglobal.com`（公司 IR）、`www.miaxglobal.com`（公司官网）、
`data.sec.gov` / `www.sec.gov`（EDGAR）、公司 IR 站上转载的自家 PRNewswire 通稿。
**没有 FIA、没有 investing.com、没有 wikipedia、没有任何聚合商。** 符合 README
「数据全部来自公司官网 IR 或 SEC 申报的原始披露」的硬约束。

### 2.3 攻击 (a)「只抓到最新一期却谎称有多年历史」——**不成立，历史是真的**

我实抓了 2019 与 2020 的月份（这是本次复核的重点攻击），全部返回真实月度数据：

```
date=20190329 → 17 行，DATA_START_DATE 01/03/2019 → DATA_END_DATE 29/03/2019
date=20200331 → 17 行，01/03/2020 → 31/03/2020
date=20151231 → 14 行，01/12/2015 → 31/12/2015
date=20150430 → 13 行，01/04/2015 → 30/04/2015
date=20140630 → []（空）      date=20121231 → []（空）  ← 2015-04 确实是起点
```

原文「实测证据 8」的回补表我**逐行重算**，除一处笔误外全部到小数点一致：

```
month      我的MIAX  PEARL  EMERALD SAPPHIRE  我的合计  行业(equity)  份额%   原文合计
2015-04     1015.6    0.0     0.0      0.0    1015.6    13773.8    7.37   1015.6 ✓
2016-01     1067.4    0.0     0.0      0.0    1067.4    16868.0    6.33   1067.4 ✓
2017-02      963.4   32.3     0.0      0.0     995.7    14623.0    6.81    995.7 ✓
2019-03      721.3  939.0    54.0      0.0    1714.2    16997.0   10.09   1714.3 ≈
2020-03      996.9 1106.9   967.1      0.0    3070.9    26382.5   11.64   3071.9 ✗
2022-06     2027.8 1727.3  1060.1      0.0    4815.2    35019.9   13.75   4815.2 ✓
2024-08     2767.6 1386.3  1764.3     68.5    5986.6    42602.6   14.05   5986.6 ✓
2025-01     3693.6 1667.8  2467.1   1015.1    8843.6    51406.9   17.20   8843.6 ✓
2026-07     5814.4 1217.2  1631.9   2327.1   10990.7    61472.8   17.88  10990.7 ✓
```

原文 2020-03 的 MIAX (M) 写 997.9，原始 JSON 是 `996879` → **996.9**。见错误 #5。

### 2.4 PDF 解析：我自己写的 x 分桶解析器，14 列 × 7 个月与原文**逐格相同**

拆词陷阱是**真的**，我亲眼看到：
- 2025 年那份：`Industry ADV` 行原始 token 是 `5 3,135 / 5 4,563 / …`，
  `MIH ADV(equities)` 行是 `1 95 / 1 70 / 2 06 …`
- 2026 年那份：`7 ,359`（农产品 1 月）
- **2025-12-05 那份更糟**：`Trading Days` 整行是 `2 0 1 9 2 1 2 1 …`（每个两位数都被拆）

用 `text.split()` 顺序对齐必然静默写错数量级。原文这条警告完全成立，
而且我发现它**低估了**：12052025 那份连 `Trading Days` 都拆，不只是万位数字。

我的解析结果（2026 年那份，与原文完全一致）：

```
month    trad_d  ind_adv  MIH_adv  share%  RPC$   ind_eq  MIH_eq  eq_sh%  capture$  ag_adv  ag_RPC  fin_adv  fin_RPC
2026-01    20     63025    11100    17.6   0.107   19436    161     0.8     0.004     7359   2.291     -        -
2026-02    19     63264    10812    17.1   0.107   19999    174     0.9     0.006    14944   2.104     -        -
2026-03    22     61770    10696    17.3   0.110   20471    194     0.9     0.005    10394   1.982     -        -
2026-04    21     62496    10593    16.9   0.116   17815    177     1.0     0.004    12421   1.977     -        -
2026-05    20     67186    11060    16.5   0.120   19398    188     1.0     0.000    10111   2.075    5897   -1.441
2026-06    21     69896    11318    16.2   0.124   23383    192     0.8    -0.001    16203   2.262    5740   -1.766
2026-07    22     64394    11019    17.1    ---    17437    117     0.7      ---     12123    ---     4194     ---
```

2025 年那份（12 个月 × 11 列）同样逐格一致，此处从略。

**额外发现**：2026 年那份 Futures/Financial 段除了原文提到的
`MIH - ADV from launch trade date` 外，还有一行 `Trading days from launch`
（2026-05 = 9、06 = 21、07 = 22），原文未提。行标签解析器要能吃掉它。

### 2.5 交叉核对 A（新闻稿）——我自己抓 PR 重比，**9/9 全等，真实**

`https://ir.miaxglobal.com/2026-08-05-Miami-International-Holdings-Reports-July-2026-Trading-Results`
HTTP 200，81,358 bytes，PRNewswire 原表：

```
Trading Days | 22                              ← PDF 22 ✓
U.S. Equity Options Industry ADV (000's) | 64,394   ← PDF 64394 ✓
MIAX Exchange Group Options ADV (000's) | 11,019    ← PDF 11019 ✓
MIAX Exchange Group Options Market Share | 17.1 %   ← PDF 17.1 ✓
U.S. Equities Industry ADV (Millions) | 17,437      ← PDF 17437 ✓
MIAX Pearl ADV (Millions) | 117                     ← PDF 117 ✓
MIAX Pearl Market Share | 0.7 %                     ← PDF 0.7 ✓
MIAX Futures ADV – Agricultural | 12,123            ← PDF 12123 ✓
MIAX Futures ADV – Financial (2) | 4,194            ← PDF 4194 ✓
```

同时确认 `Miami International Holdings, Inc. (MIAX) (NYSE: MIAX)` —— 交易所与代码写对了。

### 2.6 交叉核对 B（10-K）——**对照源真实存在，数字逐字对得上**

EDGAR `CIK 0001438472` = MIAMI INTERNATIONAL HOLDINGS, INC.，ticker `MIAX`，
10-K `miax-20251231.htm` 报送日 2026-03-06 —— 全部核实。
「Key Business Metrics」节原文（我从 4.6MB 的 htm 里抽出来的）：

```
Number of trading days 250 (options) / 251 (futures)
Market ADV – Equity and ETF (in thousands) 55,798
MIH ADV – Equity and ETF (in thousands) 9,538
MIH market share 17.1 %
Total Options revenue per contract (RPC) $0.108
Market ADV (in millions) 17,550        MIH ADV (in millions) 183
Equities capture (per 100 shares) $(0.012)
Agricultural products ADV 12,989       Agricultural products RPC $2.241
```

我用自己解析出的 PDF 月度值按交易日加权重算：

```
adv_multilist_options_kcontracts   加权=  9537.9  days=250  10-K= 9538   -0.00%
industry_adv_options_kcontracts    加权= 55797.6  days=250  10-K=55798   -0.00%
adv_equities_mnshares              加权=   183.2  days=250  10-K=  183   +0.11%
industry_adv_equities_mnshares     加权= 17584.3  days=250  10-K=17550   +0.20%  ← 对不上
adv_futures_ag_contracts           加权= 12989.6  days=251  10-K=12989   +0.00%
```

交易日合计 250 / 251 与 10-K 完全吻合。原文报的 9537.9 / 55797.6 / 183.2 / 12989.6
**一个不差**。`industry_adv_equities_mnshares` 与 10-K 差 +0.20% 是真实存在的未闭合缺口
（原文也承认了），实现时不能把这一列的 10-K 校验设成硬断言。

### 2.7 交叉核对 C（官方重述）——复现，但原文的结论**不完整**

两期 2025 年 PDF 逐格 diff，我得到与原文相同的三格：

```
2025-05  industry_adv_equities_mnshares  旧=17585 → 新=17586
2025-07  industry_adv_equities_mnshares  旧=17648 → 新=18033   (+2.2%)
2025-08  industry_adv_equities_mnshares  旧=16379 → 新=16380
```

脚注 4 原文我也核了，一字不差：
> "Due to a data processing error, industry ADV for U.S. equities in February 2026 and
> for certain months in 2025 were incorrectly reported in our summary volume table.
> Reported market share for MIAX Pearl Equities was not impacted during these periods."

**但原文说「只有这一列变过」是错的** —— 见错误 #3。

### 2.8 交叉核对 D（API 拆分）——复现，比值带宽比原文略宽

```
month    API合计    PDF     ratio  |  API行业    PDF行业   ratio
2026-01  11067.7  11100.0  0.9971  |  60763.2   63025.0  0.9641
2026-02  10776.3  10812.0  0.9967  |  61282.7   63264.0  0.9687   ← 行业差 3.1%
2026-03  10662.5  10696.0  0.9969  |  59575.4   61770.0  0.9645
2026-04  10558.7  10593.0  0.9968  |  60321.3   62496.0  0.9652
2026-05  11033.4  11060.0  0.9976  |  64912.4   67186.0  0.9662
2026-06  11284.0  11318.0  0.9970  |  66928.8   69896.0  0.9575
2026-07  10990.7  11019.0  0.9974  |  61472.8   64394.0  0.9546   ← 行业差 4.5%
```

MIAX 合计比值 0.9967–0.9976 —— 与原文报的 **完全一致**。
行业比值我得到 3.1%–4.5%，原文写 3.4%–4.5%（2026-02 那个月它算窄了）。

股票口径也复现：`PEARLEQ (H)` 2026-07 `EXCHANGE_AVERAGE_TRADE_VOLUME = 116,811,747`
（116.8mn，新闻稿 117 ✓），份额 0.67%（新闻稿 0.7% ✓），
`EXCHANGE_AVERAGE_NOTIONAL_VALUE = 4,058,114,390.86`（$4.06bn ✓），占比 0.39% ✓。
股票端起点 2020-12 也核实：2020-11 / 2020-06 / 2019-06 全部返回 `[]`。

### 2.9 API 边界行为（口径坑 3）——**四条全部复现**

```
getDate?exchType=options        → {"status":"success","date":"20260805"}
date=20261231（未来）           → 01/08/2026 → 05/08/2026   ← 静默给当月 MTD，不报错
date=20260715（月中）           → 01/07/2026 → 15/07/2026   ← 静默给半个月
date=20190331（周日，月末日历日）→ 01/03/2019 → 29/03/2019   ← 正确回落到最后交易日
date=20140630（2015 之前）      → []
```

**补充一条原文没说的**：传「该月最后一个**日历日**」即使落在周末也能正确返回整月，
所以不需要交易日历，`calendar.monthrange()` 就够。

---

## 三、发现的错误（9 处）

### #1 ⚠️ 高危：`last-modified` 与 PDF 自述 `Updated on` **并不总是一致**

原文（发布节奏节）：「实测两者对同一期完全一致（2026-08-05）。上一年那份 PDF 的两个字段也一致（2026-05-06）。
建议 evidence 字段两句都写，像 cme 那行一样互证。」

它只测了恰好相同的那两份。我测了 **5 份，3 份不一致**：

```
文件                                        Updated on (PDF内)   HTTP last-modified              结论
MIH_Volume_and_RPC_Report_08052026.pdf      August 5, 2026       Wed, 05 Aug 2026 14:05:35 GMT   一致
MIH_Volume_and_RPC_Report_2025_05062026.pdf May 6, 2026          Wed, 06 May 2026 16:26:28 GMT   一致
MIH_Volume_and_RPC_Report_12052025.pdf      December 5, 2025     Tue, 02 Dec 2025 15:54:53 GMT   差 +3 天
MIH_Volume_and_RPC_Report_06032026.pdf      June 3, 2026         Tue, 02 Jun 2026 20:41:16 GMT   差 +1 天
MIH_Volume_and_RPC_Report_07072026.pdf      July 7, 2026         Mon, 06 Jul 2026 18:27:03 GMT   差 +1 天
```

`last-modified` **早于** `Updated on` 1–3 天（文件先上传、后挂通稿）。
**后果**：若按原文建议拿 `last-modified` 当 source_date，2025-11 那期会被记成 12-02
而不是官方标注的 12-05，`build/roster.py` 的红点判据与 `source_dates.csv` 都会偏。

### #2 中危：`MIH_Volume_and_RPC_Report_06032026.pdf` **没有 404，它活着**

原文：「同期的 `..._06032026.pdf` 已 404 —— **旧期不可靠，别指望回补**。」

我实抓：**HTTP 200，420,187 bytes**，302 → `filecache…/250/`，
`last-modified: Tue, 02 Jun 2026 20:41:16 GMT`，内容是完整的
「Volume & Revenue Per Contract/Capture Report - 2026 / Updated on June 3, 2026」。
上一个 agent 存下来的 `old_MIH_Volume_and_RPC_Report_06032026.pdf` 只有 196 字节，
是一段 404 HTML —— 它那次抓取是**瞬时失败**，却被当成了永久结论。

同批我还测了 `05062026 / 04072026 / 09052025` → 三个都是真 404。
所以正确结论是「旧期**部分**存活、不可预测」，而不是「不可靠、别指望」。

### #3 ⚠️ 高危：重述**不止** `industry_adv_equities_mnshares` 一列

原文口径坑 5：「重述集中在 `industry_adv_equities_mnshares` 这一列」「其余 100+ 格全部逐字节相同」。

我把复活的 06032026（6/3 版）与 08052026（8/5 版）做逐格 diff（64 个非空格）：

```
DIFF ('futures','agricultural','Rolling three-month average RPC') 2026-04: 旧=1.981 → 新=1.977
```

**`rpc_futures_ag_usd` 也会被重述。** 幅度小（-0.2%）但方向明确。
原文只 diff 了两份 2025 年 PDF，从未 diff 过两份 2026 年 PDF（因为它以为 06032026 死了），
所以漏掉了这一类。**重述护栏必须覆盖全部列，不能只盯 equities 行业 ADV。**

（附带澄清：我第一眼从 `extract_text()` 里看到 6/3 版 May-26 RPC=0.110、8/5 版=0.120，
差点当成 RPC 重述——用 x 分桶重解后发现 6/3 版 May 那格是**空的**，0.110 其实是 Q1'26 列。
这正好是原文警告的陷阱的活样本，也说明**任何 diff 都必须在分桶解析之后做，不能对文本做**。）

### #4 中危：「MIAX 四所指数期权实测恒为 0」是**错的**

原文（标的池）：「MIAX 四所的 `INDEX_OPTION_TOTAL_AVERAGE_VOLUME` 实测恒为 0 ——
MIAX 完全不做指数期权」。

我逐月扫了 API：

```
2019-01  0        2019-06  773      2019-12  10,208   ← 峰值
2020-01  5,248    2020-02  7,068    2020-03  1,003
2020-06  3        2020-12  12       2021-06  184
2023-06  4        2026-07  0
```

全部挂在 `MIAX (M)` 这一所。**2019-06 到 2023 年间 MIAX 是做过指数期权的**，
2019-12 日均破万手。「当前为 0」成立，「恒为 0」不成立。
护城河叙事的方向没错，但若实现里写个 `assert index_opt == 0` 的校验，回补到 2019–2023 会当场炸。

### #5 低危：回补表 2020-03 数字笔误

原文 `2020-03 MIAX = 997.9、合计 = 3071.9`；原始 JSON `EQUITY_OPTION_TOTAL_AVERAGE_VOLUME = 996879`
→ **996.9**，合计 **3070.9**。原文自己那行的份额 11.64% 恰好等于 3070.9/26382.5，
说明是誊写笔误而非抓到了不同的数。

### #6 中危：列表页不是「永远挂 3 条链接」

原文：「页面结构 永远挂 3 条链接」。实际我解析出 **5 条相关链接**，含一整块 2025-12-05 的陈旧区块：

```
'Latest Monthly Volumes Press Release'  → 2025-12-05-…-Trading-Results-for-November-2025   ← 陈旧
'Historical Volumes RPC File (PDF)'     → image/MIH_Volume_and_RPC_Report_12052025.pdf      ← 陈旧，且标题没有年份
'Latest Monthly Volumes Press Release'  → 2026-08-05-…-July-2026-Trading-Results            ← 当期
'2026 Historical Volumes RPC File (PDF)'→ image/MIH_Volume_and_RPC_Report_08052026.pdf      ← 当期
'2025 Historical Volumes RPC File (PDF)'→ image/MIH_Volume_and_RPC_Report_2025_05062026.pdf ← 当期
```

**取第一个匹配的选链逻辑会拿到 2025-11 那份旧 PDF。** 而且陈旧那条的链接文字
是 `Historical Volumes RPC File (PDF)`（**无年份前缀**），所以「按 `<年份> Historical` 匹配」
反而是安全写法——但必须显式要求年份前缀存在，不能用 `endswith('Historical Volumes RPC File (PDF)')`。

### #7 低危：农产品期货的量级对照错了一倍

原文：「vs `cme.csv` 的 `adv_ag_kcontracts`……量级差 ~300 倍（MIAX 12k 手/日 vs CME ~4,000k 手/日）」。
`series/cme.csv` 实际值：2026-04 = 1,997、05 = 1,916.7、06 = 2,319.0、**07 = 1,952.5**（千手/日）。
CME 农产品是 ~**1,950k** 手/日不是 4,000k，倍数是 **~160×** 不是 ~300×。

### #8 中危：原文自相矛盾（第 70 行 vs 第 389 行）

- 第 70 行：indsum 里别家的量「**不许倒灌进 `series/cboe.csv`**」。
- 第 389 行：横截面页建议「从 `indsum` API 的 `TOTAL` 行取全行业 ADV，**两家同除**」。

第二条实际上就是拿 MIAX 官网的数据去算 **Cboe** 的份额，与第一条以及 README
「数据全部来自公司官网 IR 或 SEC 申报的原始披露」的精神冲突。
这不是 D 级违规（indsum 是 MIAX 自家官网、不是聚合商，而且原文明确禁止写库），
但**横截面页到底用谁的分母，必须先定死**，不能两条并存。

### #9 低危：API 行业比值区间写窄了；RPC 月数写多了一个

- 行业比值我实测 **3.1%–4.5%**（2026-02 是 3.1%），原文写 3.4%–4.5%。
- 原文「RPC 线只有 2025-01 起共 **19** 个月」——实际有值的是 2025-01…2026-06 = **18** 个月
  （2026-07 因滞后为空）。

### 未复核项（低风险，据实说明）

- 「历史 PR 要去 `miaxglobal.com/news?page=N`（约 98 页）」——未验证页数。仅校验源，不入库，风险低。
- BSX / TISE 不披露月度成交量——未独立验证。

---

## 四、能不能和 cme / cboe / hkex 放进同一个竞争池

这是我被要求额外判断的一项。逐池给结论：

### ✅ 北美多重挂牌期权池 —— **真可比，而且是本次唯一硬通货**

`series/cboe.csv` 确实有 `adv_multilist_options_kcontracts` 与 `rpc_multilist_options_usd`
（我在 `fetch/cboe.py:97` 与 `:110` 核到源标签 `Multiply-listed options (Equities & ETPs)`）。

单位与分母我实算过一遍，站得住：

```
2026-07 行业(MIAX PDF) = 64,394k 手/日
        Cboe multilist = 15,687k  → 24.4%
        MIAX           = 11,019k  → 17.1%
        两家合计                    41.5%   ← 量级合理，没有重复计数
```

两家都是「千手/日」，都是 equity & ETF 多重挂牌，**不需要换算**。
RPC 定义我把两边的原文对过，MIAX 10-K/PDF 脚注 2 与 Cboe 源标签指向同一件事：
> transaction and clearing fees less liquidity payments, brokerage, clearing and exchange
> fees and Section 31 fees (Net Transaction Fees), divided by total contracts traded

**这一组可以直接并排。** 但重叠窗口只有 **2025-01…2026-06 共 18 个月**
（Cboe 有 **126** 个月 —— 2026-08-19 实测，本文原写 114；MIAX 仍只有 18）。

### 🔶 北美现货池 —— ADV 可比，**capture / RPC 绝对不可比**

- ADV：`cboe.adv_us_equities_matched_shares_bn`（十亿股）vs `miax.adv_equities_mnshares`（百万股），
  ×1000 换算后可比。2026-07 Cboe 1.569bn = 1,569mn vs MIAX Pearl 117mn。可作尾部对照。
- **capture 不可比，已实锤**：`fetch/cboe.py:107` 的源标签是
  `'U.S. Equities - Exchange - per 100 touched shares'`，
  而 MIAX 10-K 脚注 3 是 `divided by one-hundredth of total shares`。
  **一个 touched、一个 total，分母不同，不能相减、不能画在同一根轴上。**
  原文这条判断正确，我确认成立。

### ❌ 农产品 —— **不是一个竞争池，只能当量级背景**

原文建议把「能源商品」池改名「大宗商品」以容纳 MIAX 农产品。我不同意把它当**份额**用：
- `cme.adv_ag_kcontracts` 2026-07 = 1,952.5k 手/日（玉米/大豆/小麦/畜牧的**整个复合体**）
- `miax.adv_futures_ag_contracts` = 12,123 手/日，实质是 **Minneapolis 硬红春小麦一个品种**
- 相差 ~160×，且**标的不重合**——两家几乎不争同一张合约。

放同一张份额图会造出「MIAX 占农产品 0.6%」这种没有经济含义的数字。
建议只在「规模对照」表里出现，或者干脆不进池。

### ❌ 股指衍生品 —— 差 2000 倍，不能进池

`miax.adv_futures_fin_contracts` 2026-07 = 4,194 手/日 vs `cme.adv_equity_kcontracts` = 8,168.8k
（= 8,168,834 手/日），**差约 1,950 倍**。只能做「新产品爬坡曲线」，原文这条成立。

### ❌ HKEX —— 无任何交集

`series/hkex.csv` 的列是 `adt_hkdbn` / `mktcap_hkdtn` / `derivatives_adv_contracts` /
`southbound_adt_hkdbn`——地理与标的都不重合。且 HKEX 衍生品 ADV 是**裸合约张数**
（2026-07 = 1,731,267），与 MIAX 的「千手」差 1000 倍量纲，即便硬凑也无意义。原文判 ❌ 正确。

### 一句话

**MIAX 只在「北美多重挂牌期权」这一个池里是真正的可比对手（且这一池的信息增量确实很高）；
「北美现货」只能比 ADV 不能比 take rate；农产品、股指、亚太三池都不该建池。**
原文对池的判断方向基本正确，只有农产品那条建议偏激进、量级还写错了一倍。

---

## 五、给实现阶段的具体警告

1. **source_date 只认 PDF 里的 `Updated on <Month D, YYYY>`，不要用 HTTP `last-modified`。**
   实测 5 份里 3 份不一致，`last-modified` 早 1–3 天。可以把 `last-modified` 写进 evidence
   当**辅助线索**，但权威字段必须是 PDF 自述那一行。原文「两者互证」的说法不成立。

2. **选链必须要求年份前缀。** 列表页有 5 条相关链接，含一块 2025-12-05 的陈旧区块，
   其中一条 PDF 链接的文字是**没有年份**的 `Historical Volumes RPC File (PDF)`。
   取第一个匹配 = 拿到 2025-11 那份旧文件。只接受
   `^(?P<year>20\d{2}) Historical Volumes RPC File \(PDF\)$`，且断言恰好命中 2 条（当年 + 上一年）。

3. **重述护栏覆盖全部列，不能只盯 `industry_adv_equities_mnshares`。**
   已实证 `rpc_futures_ag_usd` 2026-04 从 1.981 改到 1.977。照 `fetch/spgi.py` 的做法：
   每次重解析与库里全表比对，任何格不同就 warning，而不是只监控一列。

4. **diff / 校验一律在 x 分桶解析之后做，绝不对 `extract_text()` 的文本做。**
   我自己就差点因为文本比对把「Q1'26 列」误判成「May 列的 RPC 重述」。
   月度列与 `Q1'26 / Q2'26 / FY'25 / Year to Date` 季度年度列的 x 中心必须都建桶，
   把落到季/年桶里的 word **丢弃**，否则月份列会吃到相邻季度列的值。

5. **别写 `assert index_options == 0`。** MIAX (M) 在 2019-06…2023 期间有指数期权，
   2019-12 日均 10,208 手。当前为 0 是事实，恒为 0 不是。

6. **旧期 PDF 是「部分存活」不是「全死」。** `06032026` / `07072026` 活着，
   `05062026` / `04072026` / `09052025` 是真 404。可以机会性回补，但**不能把回补当作必要路径**，
   也不能因为某一期 404 就让 `update()` 失败。另外 filecache 路径里的 `{n}`
   我拿到 253 而上一个 agent 拿到 252（同一文件）——**确认不可猜，必须走 302**。

7. **每次 `update()` 都要下当年 + 上一年两份 PDF 并合并。** 12 月的 RPC 在当年那份里是空的，
   要等次年 5 月左右重发上一年那份才补上（已实证 Dec-25 RPC = $0.106 出现在 2026-05-06 那份里）。
   只下当年那份 = 12 月 RPC 永久留白。

8. **`indsum` API 必校验 `DATA_START_DATE` / `DATA_END_DATE`。** 未来日期与月中日期都会
   **静默**返回当月 MTD 而不报错。传该月最后一个**日历日**即可（周末也能正确回落到最后交易日，
   无需交易日历）。先打 `getDate?exchType=options` 拿官方最新可用日。
   日期格式是 `DD/MM/YYYY`，别当成美式。

9. **`indsum` 的 `TOTAL` 行有个陷阱字段。** 各交易所行的 `TOTAL_MARKET_AVERAGE_TRADE_VOLUME`
   = 17,441,439,632（真·全市场），但 `TOTAL` 行自己的同名字段 = 331,387,353,008
   （≈ 19 倍，等于按行数重复累加）。**算份额的分母要用交易所行的 `TOTAL_MARKET_*`
   或 `TOTAL` 行的 `EXCHANGE_AVERAGE_*`，绝不能用 `TOTAL` 行的 `TOTAL_MARKET_*`。**
   notional 端同病（1,028bn vs 19,540bn）。原文完全没提这一条。

10. **`industry_adv_equities_mnshares` 不要对 10-K 做硬断言。** 我加权得 17,584.3，
    10-K 写 17,550，差 +0.20% 且官方两边都没修。设成 hard assert 会让年度校验永远失败。
    其余四项（9,538 / 55,798 / 183 / 12,989）可以硬校验，我实测误差 ≤0.11%。

11. **`LAG` 建议 `(6, 6)` 我认为可用但偏紧。** 实测发布日（按 `Updated on`）是次月第 3–5 个工作日，
    即月末后第 3–7 个日历日（2025-11 → 12-05 是第 5 个日历日；2026-06 → 07-07 是第 7 个）。
    `(6,6)` 会让 7 月那种独立日错峰的月份**假红一天**。建议 `(8, 8)`，或至少确认 `GRACE = 5`
    能兜住。原文「季末月不需要单独一档」的判断正确——MIAX 月报独立于季报（2026-06 数据
    7/7 就发了，Q2 财报 8/5 才发）。

12. **横截面份额的分母口径先定死再动手。** 原文第 70 行禁止用 indsum 算别家，
    第 389 行又建议用 indsum 的 `TOTAL` 给 Cboe 和 MIAX 同除。二选一。
    若选后者，等于 Cboe 的份额数字来自 MIAX 官网，需要先跟仓库「各家只用各家 IR」的原则对齐。

13. **RPC 并排图只有 18 个月重叠**（2025-01…2026-06），Cboe 侧有 **126** 个月
    （2026-08-19 实测，本文原写 114；重叠窗口由 MIAX 决定，**这一条的结论没变**）。
    页面上必须写明 MIAX 线的起点，且 2026-12 之前做不了同比 / 指数化。

14. **`adv_futures_ag_contracts` 是「手」，`cme.adv_ag_kcontracts` 是「千手」。**
    量纲差 1000，且 CME 是整个农产品复合体、MIAX 实质是单一小麦品种。
    建议只做规模对照，不建份额图。原文的「~300 倍」应改为「~160 倍」。

---

## 六、判定汇总

| 项 | 结果 |
|---|---|
| 原判定 | B |
| **最终判定** | **B（维持）** |
| 是否独立复现抓取与解析 | **是** —— PDF 重下重解、API 重抓重算、PR 与 10-K 重新核对 |
| (a) 谎称历史 | 不成立，2015-04 / 2019 / 2020 实抓成功 |
| (b) 第三方源冒充官方 | 不成立，全部一手 |
| (c) 依赖浏览器/登录态 | 不成立，纯 curl + urllib 可跑 |
| (d) 字段口径写错 | 未发现口径性错误；单位、张数/金额、月度/ADV 全部正确 |
| (e) 声称 A 但字段缺失 | 不适用（它声称的就是 B，且缺陷自己说了） |
| 事实错误 | **9 处**，其中 3 处（#1 source_date、#3 重述范围、#6 选链）会直接伤实现 |
| 跨家可比性 | 只有「北美多重挂牌期权」一池真可比；现货仅 ADV 可比、take rate 不可比；农产品/股指/亚太不该建池 |
