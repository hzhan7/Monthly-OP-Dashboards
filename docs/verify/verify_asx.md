# 复核报告 —— ASX 数据源侦察（`/tmp/exch_recon/asx.md`）

复核日期 2026-08-06 ｜ slug `asx` ｜ 原判定 **B** ｜ **复核判定：维持 B**
复核方式：不读原 agent 的脚本（`/tmp/exch_recon/scratch/parse_mar.py` 全程未打开），
自建行序解析器（原 agent 用词坐标法，我用文本行序法 —— 两种方法互为独立验证）。
我的临时文件在 `/private/tmp/claude-501/-Users-hainan-Library-CloudStorage-OneDrive-Personal/00bde884-5d9d-4ce5-a363-6b721a0462f5/scratchpad/v/`

> **2026-08-19 追记（本轮回补改掉的 1 处事实）** —— 本文是 **2026-08-06** 的复核报告，
> **原文一字未删**。第 7 节里我背书的那一句「辅源 1 确实只有 2 期、确实不可回补」
> **是错的**，且这个错**两份报告都犯了** —— 原侦察稿断言不可回补，我复核时复现了它的
> 404 却没有质疑那个 URL 是**我们自己拼出来的**（官方五年换过 5 代命名，日期段三种写法）。
> 修掉 `fetch/asx.py::_SFE_LINK` 之后，2020-06…2026-05 共 72 期全部取回，
> 连同原有 2 期共 **74 个月零空洞**入库（2026-08-19 实测 `series/asx.csv`）。
> 详见 `docs/verify/asx.md` 的文首追记与口径坑 8 追记。
> **复核判定「维持 B」这个结论本身不变**，但支撑它的理由换了 —— 见第 7 节的就地追记。

---

## 结论一句话

**没有虚报。** 五类虚报（只抓最新期 / 第三方聚合站 / 需登录态 / 关键字段缺失 / 口径造假）**一条都不成立**，
所有交叉核对我都独立重跑并 100% 复现。B 是正确的复合判定。

**但是**：报告的「口径坑」章节 —— 也就是本该保护实现阶段的那部分 —— **有一个 7 年的日期错误、
两处字段自相矛盾**，另有 **3 个高杀伤力的坑完全没提**，其中一个正好落在它自己推荐的 series 起点窗口里。
**照这份文档直接实现会静默写入错数据。** 下面第 4 节给出修正。

---

## 1. 五类虚报逐条排除

| 攻击点 | 结论 | 我的实证 |
|---|---|---|
| **(a) 只抓到最新期，谎称有多年历史** | **不成立** | 我独立抓到并解析了 **2019-06 / 2016-06 / 2015-10 / 2015-09 / 2015-08 / 2013 / 2010**。全部走 `announcements.do` → `displayAnnouncement.do` 隐藏字段 → `announcements.asx.com.au` 直链，裸 `urllib` 完成。历史是真的可回溯。 |
| **(b) 拿第三方聚合站当官方源** | **不成立** | 全部路径落在 `www.asx.com.au` 与 `announcements.asx.com.au`（ASX 自家公告平台）。无 FIA / investing.com / wikipedia / 数据站。markitdigital 那条被明确标注「备而不用、不适合当主源」，符合规范。 |
| **(c) 靠浏览器登录态 / 手工点击** | **不成立** | 裸 `urllib`（默认 `Python-urllib` UA，零 header）三个入口全 200。`displayAnnouncement.do` 的条款页**只需 GET 读隐藏字段，不需要 POST、不需要 cookie**，我直接拿到 PDF 字节流。无人值守 cron 可跑。 |
| **(d) 字段口径写错** | **部分成立** | 见第 3 节 E1/E2/E3 —— 三处真实口径错误。 |
| **(e) 声称 A 但关键字段缺失** | **不成立** | 2026-07 那期我逐字比对了 PDF 原文，28 个字段全部存在且数值正确。 |

---

## 2. 我成功复现的部分（原报告为真）

### 2.1 抓取环境
```
200  508206  https://www.asx.com.au/about/media-centre
200  106264  .../media-releases/2026/43-06-august-2026-...-july-2026.pdf   (application/pdf)
200  121463  .../announcements.do?by=asxCode&asxCode=asx&timeframe=Y&year=2016
```
无 Cloudflare / Akamai / JS 渲染 / 登录墙 / UA 校验 —— 复现。

### 2.2 发现逻辑
媒体中心一次 GET 得 **493 条 PDF href，其中 80 条是 MAR** —— 与原文逐字相符。
去重后 **78 个月，2020-02 → 2026-07，0 断档** —— 复现（我第一次算成 77，是因为 `asx-group-monthly-activity-report%20-august-2020.pdf` 文件名里混了 `%20`，这本身也是个坑）。

### 2.3 最新一期字段（2026-07）
我把 PDF 全文 dump 出来逐行对照，原报告 28 个字段**全部正确**，包括
`6.645/5.952`、`180.814/164.465`、`63,134,490/47,806,329`、`711,012`、`713,411`、
`208,578`、`24,992`、`635.499`、`4,872.671`、`2,045/2,092`、`3,562.9`、`167.565`。

### 2.4 交叉核对 A（vs ASX 2025 年报）—— 完全复现
我自己下载了 `asx-2025-annual-report.pdf`（13.2 MB），**原报告表格里 18 个年报参照值，一个不差**。
然后用我自己的解析器重跑 12 份月报加总：

| | 用**原版** 2025-01 | 用**更正版** 2025-01 | 年报 |
|---|---|---|---|
| Total cash market value ($bn) | 1,827.088（**+0.2205%**） | **1,823.068（0.0000%）** | 1,823.068 |
| Trade reporting ($bn) | 284.726（**+1.1812%**） | **281.402（0.0000%）** | 281.402 |
| Centre Point ($bn) | 146.303（**+0.4780%**） | **145.607（0.0000%）** | 145.607 |
| OTC notional cleared ($bn) | — | **7,807.729（0.0000%）** | 7,807.729 |
| Total cash trades | — | 475,356,742（-0.0001%） | 475,357k |
| Futures+options 总张数 | — | 195,365,193（+0.0001%） | 195,365k |
| ADV futures+options | — | 763,145.3 | 763,145 |
| ADV single stock / index options | — | 247,120.7 / 28,174.8 | 247,121 / 28,175 |
| 交易日 cash / futures / ETO | — | 253 / 256 / 253 | 253 / 256 / 253 |

**原报告声称的 +0.48% / +1.18% / +0.22% 三个偏差，我分毫不差地复现了。**
这不是能编出来的数字 —— 它证明原 agent 真的下载并解析了 12 份独立 PDF，也证明 2025-01 更正版这个坑是真的。

### 2.5 交叉核对 B（vs FY26 新闻稿）—— 完全复现
新闻稿真实存在：`/content/dam/asx/about/media-releases/2026/16-july-media-release-asx-delivers-strongest-listings-result-since-fy22.pdf`。
四处引文我逐字核对，**全部原文命中**（含 "raised $37.8 billion in follow-on capital during FY26"）。
我自己加总 12 份月报：

```
sec(窄口径) 37,849   scrip 20,579   totsec 58,428
newq 91,024   mcap 32,596   newent 100
新闻稿:      37.8bn        20.6bn        58.4bn
             91.0bn        32.6bn        100
```
与原报告的 $37.849 / $58.428 / $91.024 / $32.596 / 100 **完全一致**。

### 2.6 交叉核对 C（vs Monthly SFE Trading Report）—— 完全复现
```
SFE 31072026:  Total Exchange 16,408,463   Daily Average 713,411
MAR 2026-07 :  Total contracts 16,408,463  Average daily 713,411
SPI200(AP) 814,634 / OI 231,151 ｜ YT 5,442,552 / 1,287,283
XT 4,502,250 / 1,425,106 ｜ IR 5,206,358 / 1,784,007 ｜ IB 34,499 / 25,266
利率期货小计 15,194,710
```
逐个命中。该直链确实印在 MAR 第 4 页正文里 —— 复现。

### 2.7 ~~辅源 1 的「只有 2 期」是真的~~ ← **2026-08-19 已推翻，见下方追记**
`31072026` / `30062026` → 200 (application/pdf)；`31052026` / `31122025` → **真 404**。
~~**这块给 C 是对的**，不是偷懒。~~

> **2026-08-19 追记：这一节是本文最贵的一处错，值得把错法记清楚。**
>
> 上面那四个 URL 我确实一个个发过、404 也确实是真的 —— **但那四个文件名是我们自己拼的**。
> 官方 2026-05 那一期的真名是 **`290526`**（不是 `31052026`）、2025-12 那期是 `251231`
> （不是 `31122025`）。官方五年换过 **5 代命名**，日期段有 YYMMDD / DDMMYY / DDMMYYYY
> 三种写法，2026-02 那期甚至从 DDMMYY 退回 YYMMDD。**404 的是我们编的 URL，
> 不是官方的文件。**
>
> ⇒ **这一节的方法错误**：我复核的是"原报告那次请求有没有真的返回 404"，
> 而该问的是"**那个 URL 是谁给的**"。正确做法是跟着 MAR 正文里印的链接走
> （期货段末尾 "Volume of futures trading by individual contract is available at the
> following link:"），**一个日期数字都不要自己解释**。
>
> 修掉 `fetch/asx.py::_SFE_LINK` 之后逐月实发：**2020-06…2026-05 共 72 期全部
> 200 + `application/pdf` + `%PDF-`**，用未改动的 `parse_sfe` 全部解析成功；
> 连同原有 2 期共 **74 个月零空洞**入库。两条独立判据都过（跨期自证 495/496 格逐位一致，
> 唯一那格是官方后期重述；页尾 `Total Exchange` ≡ 同月 MAR 期货合计，74/74 全等）。
>
> **仍然成立的一半**：**2020-06 是硬天花板**。判据是"链接指向哪个目录"而不是"多久以前" ——
> 2020-05 及更早的 MAR 指向老站点路径 `/data/market-reports/…`，今天整体 302 到
> `content/asx/404.html`（**200 + text/html 的 soft-404**，比真 404 更难发现）；
> 2016-01…2016-08 的 MAR 正文里根本没印这条链接。

### 2.8 存档覆盖 —— 原报告反而**低估**了
原文：「199 期，2009-12→2026-07，断档仅 2010-02」。
我做了 2009–2026 全量普查（大小写不敏感）：**2009-12 → 2026-07 共 200 个月，0 断档**。
原报告的「199」和「1 个断档」我复现不出来（真实更好），属安全方向的偏差。

### 2.9 其它已验证为真的点
- 竖排水印 `For personal use only` —— 2015/2016 年 PDF 中确认存在（坑 9 成立）。
- 列数按行变（4 列 / 2 列，7 月那期整份 2 列）—— 2020-02 与 2026-07 对照确认（坑 2 成立）。
- 发布节奏：我统计的日分布 `{3:33, 4:40, 5:58, 6:63, 7:13, 8:3, 20:1}`，形状与原文一致；
  `LAG=(8,8)` 安全（第 20 天那 1 个是 2022-06 的更正稿，不是原始发布）。
- 更正稿第 1 页是「Incorrect figure / Correct figure」对照表 —— 我 dump 确认，
  且 `Centre Point ($billion)` 在第 1 页就带着**错值 9.548** 出现。**跳过第 1 页是硬性要求**，坑 3 成立。

---

## 3. 我发现的错误（原报告写错的）

### E1 —— 口径坑 4 的断点日期错了 7 年【严重】
原文：「Listings 段在 **2016/2017** 之间换过定义」「跨 2016/2017 这条序列不可直接连比」。

**实测断点是 2023-10 / 2023-11，不是 2016/2017。** 我逐月扫了标签：

| 期间 | `新上市` 那一行的标签 | `合计` 那一行的标签 |
|---|---|---|
| …2020-02…2023-09 | `Initial capital raised ($million)` | `Total capital raised including other ($million)` |
| **2023-10（仅此一月）** | `Quoted market capital of new listings` （**无 -isation**） | `Total initial and secondary capital quoted` （**第三种写法**） |
| 2023-11 → 2026-07 | `Quoted market capitalisation of new listings` | `Total new capital quoted` |

2021-06 / 2022-06 / 2023-06 / 2023-07 / 2023-08 / 2023-09 全部仍是旧口径 —— 实测确认。
⇒ 结构性断点红线要画在 **2023-10**；且 **2023-10 是一个单月中间态**，精确标签匹配会把它整月丢掉。

### E2 —— 原报告自己犯了它警告的那个错【严重】
证据 2 里 `capital_new_quoted_audmn cur=2811 pcp=14806`（2016-06）。
我 dump 了同一份 PDF：**那一行的真实标签是 `Total capital raised including other ($million)` 2,811 / 14,806** —— 旧口径。
而证据 1 里同一个 key 喂的是 2026-07 的 `Total new capital quoted` 9,352。
**同一列名承接了两个不可比的定义 —— 正是坑 4 描述的静默串接，它自己犯了。**

### E3 —— 证据 1 的字段名与字段定义表自相矛盾
字段表：`capital_secondary_audmn` = 「二次融资额（**窄口径**，不含换股对价）」。
2026-07 PDF 原文：`Secondary capital raised 4,361` / `Other scrip 1,848` / `Total secondary capital raised 6,209`。
证据 1 却打印 `capital_secondary_audmn cur=6209` —— **装的是 Total，挂的是窄口径的名**。
（我的解析器两行都能分开取到，所以不是 PDF 的问题。）
若按这个映射入库，交叉核对 B 的 follow-on 对账（37.8bn）永远对不上。

### E4 —— `Average daily contracts` 出现次数不是常数 5
坑 1 写「同一份 PDF 里出现 **5 次**」。实测（区分大小写）：
**2015-08 / 2015-09 / 2015-10 / 2016-06 各 6 次**，2020-02 与 2026-07 各 5 次。
多出来的那次是 2016 版独有的 `Total equity options` ADV 行（2016-06 = 418,112 ≈ 347,474 + 70,639）。
它的补救方案（按 section 大标题切段）是对的，但**按 5 写死的代码在它自己推荐的起点窗口就是错的**。

### E5 —— 版式代际表差一个月
原文：「2015-10 及之后现代版；**2015-09 过渡版，两套标题同时出现**」。
实测标题集合：
- `g_august_2015.pdf` → 只有 `TRADING – FINANCIAL DERIVATIVES MARKETS`
- `g_september_2015.pdf` → 只有 `TRADING – FUTURES` + `TRADING – EQUITY OPTIONS`，**全文不含 FINANCIAL DERIVATIVES**
⇒ 切换点是 **2015-09**，且**不存在双标题过渡月**。

### E6 —— 年报页码
原文「第 150–152 页」。实际 PDF 页 **152 / 153 / 154**（印刷版心页码 150–152）。按 PDF 页锚定会取空。

### E7 / E8 —— 小偏差
- FY25 `futures+options 总张数`：原文 195,365.172（千），我算 195,365.193（千）。差 21 张，两者都四舍五入到年报的 195,365。
- 存档「199 期 / 断档 2010-02」复现不出（真实 200 个月 / 0 断档），安全方向。

---

## 4. 原报告完全没提、但会直接毁掉数据的坑【实现阶段必读】

### M1 —— `ASX Compliance Monthly Activity Report` 同名诱饵【最高危】
**2010-08 → 2016-06 共 71 个月，ASX 每月同一天发两份标题几乎相同的公告**：

```
01754741  ASX Group      Monthly Activity Report - June 2016   7 pages 232.1KB   ← 要的
01754742  ASX Compliance Monthly Activity Report - June 2016   5 pages 217.6KB   ← 诱饵
```

idsId 相邻、同日发布。**我自己就中招了** —— 第一次按 `'Monthly Activity' in title` 抓 June 2016，
拿回来的是 Compliance 版，里面有一行 `Listed entities at month end 2,204`，
**是个完全合法、看起来正确的数字，但整份没有任何成交数据**。写进 series 就是静默污染。

**这 71 个月与推荐起点 `2016-01` 重叠了 6 个月（2016-01 … 2016-06）。**
⇒ 发现逻辑必须显式 `'compliance' not in title.lower()`，且断言解析出的字段数 ≥ 阈值。

### M2 —— 标题变体让「月份」抽不出来
实测存在的变体（全部来自 `announcements.do`）：
- `ASX Group Monthly Activity Report - November`（**无年份**：2017-10、2017-11、2018-02、2018-03、2018-08、2018-11、2012-01）
- `ASX Monthly Activity Report - October 2016`（**无 "Group"**：2016-07…2016-10、2017-04）
- `ASX Group monthly activity report - July 2026`（**2026-04 起转小写**）
- `ASX Group Monthly Activity Report Feb 2010`（**月份缩写**）
- `Corrected ASX Group Monthly Activity Report for April 2015`
- `Correction to June 2022 ASX Group Monthly Activity Report`
- `Update to ASX Group Monthly Activity Report`
- `ASX Group Monthly Activity Report and Fee and Rebate Changes`（**完全无月份**）

⇒ 匹配必须大小写不敏感、"Group" 不能强求、月份支持缩写；
**标题无年份时，数据月 = 发布月 − 1**（这样才能得到我实测的 0 断档）。

### M3 —— 更正稿有 4 份，不是 2 份
实测同月出现 >1 份 Group 文档的月份：**2011-01、2015-04、2022-06、2025-01**。
原文只知道后两份。前两份在推荐起点之前，不影响入库，但去重规则要写成通用的
「同月存在 correction/corrected 时一律优先，且跳过第 1 页」。

### M4 —— soft-404（HTTP 200 的假成功）【高危】
2020 年代 MAR 正文里印的旧版分品种直链
`https://www.asx.com.au/data/market-reports/MonthlyFuturesMarketsReport{YYMMDD}.pdf`
**返回 HTTP 200 + `text/html` + 恒定 136,750 字节的错误页**，不是 404。
（`200228` / `190228` / `160630` 三个日期返回完全相同的字节数。）
⇒ 任何 `if status == 200: save()` 的写法会把 HTML 错误页当 PDF 存进去。
**必须同时校验 `Content-Type == application/pdf` 且首 5 字节 == `%PDF-`。**
（新版 `unlinked-docs/monthly-futures-markets-report-*.pdf` 是真 404，行为不一样 —— 更容易疏忽。）

### M5 —— 两份报告的 YTD 基准不同
- MAR：`February 2020 **Financial** YTD`（财年，7 月起算）
- SFE Report：`YTD 2026 (**149-Days**)` = **日历年** 1–7 月

⇒ 混用即错。原文完全没提。

### M6 —— ASX 期货量含 non-traded volume
SFE 报告页脚：volumes "include on-market, off-market and non-traded volumes"；
第 4 页单列 `Total Non Traded: 51,541`（2026-07，约占 16.4m 的 0.3%）。
MAR 的合计 = SFE `Total Exchange`，所以 MAR 口径同样含它。
与 CME 比时要注意：`cme.csv` 把 `adv_privately_negotiated_kcontracts` 单列，ASX 是并进总量的。

### M7 —— 辅源 2 两个页面的市值基准不同
- 当前页（2016 起）：`Total end of month market cap ($m)` —— 2026-06 = $3,257,972m
- 存档页（2015 及更早）：`Dom. Equity Mkt cap $m`（**仅本土**）—— 2015-12 = 1,628,501

⇒ 直接拼接会造出一个没有标注的断点。另外：当前页表格**只有月份名，年份在每年一个的表头里**，
且**比 MAR 慢一个月**（MAR 已到 2026-07，该页最新仅 2026-06）—— 月度 cron 里这一列会永远滞后一格。

### M8 —— 标签与数字不相邻，且标签里有数字
三个我实测踩到的变体：
1. 2024 版把括号说明夹在标签和数值之间：
   `Total trading days` → `(Cash market includes equity, ETP and interest rate market` → `transactions)` → `23` → `21`
2. 该说明里**含数字**：`(includes interest rate, ASX SPI 200, commodities and energy contracts)` —— 「跳过无数字行」的规则会失效
3. **脚注标记两种形态**：2026 版是上标 Unicode `¹`，2024 版是**普通 ASCII 数字直接粘在标签后**
   （`Total notional cleared value ($billion)1`）—— 精确等值匹配会把 2024-07…2024-10 整段静默丢掉（我就丢了）

### M9 —— 2016 版现货段的行名与现代版**全部不同**
| 现代版（字段表里写的） | 2016-06 实际行名 |
|---|---|
| `Total cash market value ($billion)` | `Total value ($billion)` |
| `On-market average daily value ($billion)` | `Average daily value on-market ($billion)` |
| `Total average daily value ($billion)` | `Average daily value ($billion)` |
| `Total listed entities` | `Total **L**isted entities (at end of month)`（大写 L） |
| `On-market value` | **不存在** —— 2016 版只有分项 + Total value |

2016 版另有 `Non-billable value (above cap)` / `Total billable value` 两行，后来消失。
⇒ 字段表只列了现代行名，回补到 2016 时至少要准备第二套 label map，
且 `value_cash_onmarket_audbn` 在早期是**真缺失**，不是解析失败。

---

## 5. 能不能和 cme / cboe / hkex 放进同一个竞争池

**能，但原报告的答案偏乐观，漏了三处单位/对手方问题。**

已核对现有 schema：
```
（区间为 2026-08-19 重测；2026-08-18 那一轮把 cboe / hkex 都回补到了 2016-01，
  下面这三行原写 cboe 2017-01 起、hkex 2019-01 起）
cme.csv   adv_*_kcontracts（千张）+ oi_*_contracts（张）+ trading_days   2008-01→2026-07
cboe.csv  adv_*_kcontracts（千张）+ rpc_*                                2016-01→2026-07
                                                （rpc_* 只到 2026-06，比 adv_* 少一个月）
hkex.csv  adt_hkdbn, mktcap_hkdtn, new_listings, ipo_funds_hkdbn,       2016-01→2026-07
          derivatives_adv_contracts（**张**）, southbound_adt_hkdbn      ← 这两列 2018-01 起
```

**可比的：**
- `adt_cash_onmarket_audbn` ↔ HKEX `adt_hkdbn` —— 同概念（本币日均成交额），指数化或折美元后可比。原文正确。
- ASX 期货+期权 ADV ↔ HKEX `derivatives_adv_contracts` —— **两边都是「张」，量纲一致**，是最干净的一组。

**原文漏掉的三点：**
1. **CME 也是 kcontracts。** 原文只对 Cboe 提醒了「×1000」，但 `cme.csv` 的 `adv_rates_kcontracts` / `adv_equity_kcontracts` 同样是千张。
   把 ASX 的 711,012（张）直接和 CME 的 8,733（千张）画一起，会差 1000 倍 —— 比它警告的「合约规模差异」严重得多。
2. **ASX 现货 ADT 在 Cboe 那边没有对手字段。** `cboe.csv` 的
   `adv_us_equities_matched_shares_bn` 是**股数**不是金额，`adv_eu_equities_adnv_eurbn` 是欧元名义额。
   ⇒ ASX 现货 ADT 只能与 HKEX（和 Cboe 的欧洲那一列）配对，不能进「北美现货」池。原文把这归为「无海外业务」，
   结论对但理由不对 —— 即使有，字段也接不上。
3. **HKEX 市值是 `mktcap_hkdtn`（万亿港元），ASX 辅源 2 是 A$ 百万** —— 差 6 个数量级，
   且基准还不同（HKEX 全市场 vs ASX 含外国注册 / 2015 前仅本土，见 M7）。

**真正不可比、必须隔离的：**
- `otc_notional_cleared_audbn` 是**双边计数**（官方脚注 `Cleared notional value is double sided`），与 CME/LCH 惯例不同。原文正确指出。
- ~~**最实质的限制**：能和 CME 的 `adv_rates_kcontracts` / `adv_equity_kcontracts` 分资产类对齐的
  ASX 分品种数据**只有 2 个月**。历史区间里 ASX 只能贡献一个**混合口径的期货 ADV**
  （利率 + 股指 + 商品 + 电力 + NZ 全混在一起，且含 non-traded volume），
  **无法拆进仓库已有的 CME 式资产类列**。~~ 原文用「利率占 ~92%，可作趋势代理」带过，
  这个代理在 FY25 成立，但它是随电力/NZ 产品增长而漂移的比例 —— 图注必须写明是混合量，不能标成利率量。

  > **2026-08-19 追记**：划掉的部分作废（见 §2.7 追记）。分资产类的列**有**，
  > `contracts_3y_bond_futures` / `contracts_10y_bond_futures` / `contracts_90d_bankbill_futures`
  > （+ 各自的 `oi_*`、+ `contracts_spi200_futures`）实测 **2020-06 → 2026-07 共 74 个月零空洞**。
  > ⇒ **不要再用混合期货 ADV 当利率代理** —— 上面那句"随电力/NZ 增长而漂移"仍然对，
  > 正因为它对，现在有真序列就更没理由画代理量了。
  >
  > ⚠ 但**能对齐 ≠ 能进池**：`build/pools.py` 的 `interest_rate` 池仍然排除 ASX，
  > 卡点是**起点 2020-06 晚于全仓基期 2019-01**（池合计按"任一成员缺值该月即缺"求交集，
  > ASX 一进来窗口从 2014-12 收到 2020-06、基期那格变 nan ⇒ 定基指数算不出、整页 `skip()`；
  > 走 ICE 那条 `contracts_only` 也躲不开，增长图同样 2019-01 = 100 定基）。
  > 而 2020-06 是官方存档天花板，**补不到**。完整理由见 `build/pools.py` 的
  > `interest_rate` → `excluded`。ASX 的利率量仍计入 `apac_deriv` 的混合口径。
  >
  > 次要且可解：这几列是**月总张数不是 ADV**，要对齐 CME 得先除 `trading_days_futures`。

---

## 6. 给实现阶段的具体警告（按优先级）

1. **发现逻辑必须排除 Compliance 版**：`'compliance' not in title.lower()`，
   并在解析后断言字段数 ≥ 阈值（Compliance 版没有成交段，会解析出极少字段）。影响 2010-08…2016-06，含推荐起点前 6 个月。
2. **下载后校验 `Content-Type` + `%PDF-` 魔数**，不能只看 HTTP 200 —— `/data/market-reports/` 路径是 soft-404。
3. **结构性断点红线画在 2023-10，不是 2016/2017**；且 2023-10 是单月中间标签态，要单独打特例。
4. **`capital_secondary_audmn` 必须取 `Secondary capital raised`（窄口径），
   `capital_secondary_total_audmn` 取 `Total secondary capital raised`** —— 别照证据 1 的映射抄。
5. **标签匹配用「规范化 + 前缀」，不要用精确等值**：先剥尾部上标 `¹²³`/ASCII 脚注数字/`*`，
   再前缀匹配；数值收集允许跨过 1–2 行括号说明（说明里可能含数字）。
6. **section 切段取值，永远不要按 `Average daily contracts` 的出现序号取** —— 次数在 5 和 6 之间变。
7. **同月存在 correction 时优先用它，并跳过第 1 页**（第 1 页含「错误值」列）。已知 4 个月：2011-01 / 2015-04 / 2022-06 / 2025-01。
8. **标题无年份时，数据月 = 发布月 − 1**；匹配大小写不敏感、支持月份缩写、不强求 "Group"。
9. **月度 cron 只走媒体中心（路径 A）**，历史回补一次性跑存档（路径 B）。B 技术上纯 GET 可通（我实测），
   但穿过条款页是策略问题，建议人工跑一次后固化 CSV。
10. **辅源 2 比 MAR 慢一个月**，且 2015/2016 分属两个市值基准 —— 别在同一列里拼。
11. **跨家对比前统一量纲**：CME/Cboe 是 kcontracts，ASX/HKEX 是 contracts。
12. 起点建议仍取 **2016-01**（我同意），但要清楚：`value_cash_onmarket_audbn` 在 2016 版**真的不存在**，
    该列早期为空是正常的，不是抓取失败。

---

## 7. 判定

**维持 B。**

理由：MAR 主源确实是 A 级 —— 裸 HTTP、官方一手域名、200 个月 0 断档、
与年报 18 项 / 新闻稿 4 项 / 另一份官方报告 2 项交叉核对全部 0 偏差（我独立复现）。
~~辅源 1 确实只有 2 期、确实不可回补，C 是实事求是的。~~ 任务起点线索点名要的
3yr/10yr/SPI 200 月度 ADV 正好卡在那块 —— B 这个复合判定是准确的。

~~不上调到 A：分品种历史真的没有。~~
不下调：没有任何一条虚报成立，所有承重的声称我都独立跑通了。

> **2026-08-19 追记 —— 上面划掉的两句是本文唯一的实质错误，而且是我复核时漏掉的那一类。**
>
> 事实：分品种历史**有**，`series/asx.csv` 那 8 列今天是 **2020-06 → 2026-07 共 74 个月、
> 零空洞**。原侦察稿的 404 实测（`31052026` 404）用的是**我们自己按格式拼出来的文件名**，
> 官方那一期的真名是 `290526` —— 404 的是我们编的 URL。我当时复现了那个 404，
> 却没有去问「这个 URL 是谁给的」。⇒ **复核的盲点：复现了对方的实验，没有复核对方的假设。**
> 判据是"链接指向哪个目录"而不是"多久以前"：2020-06 起指向 DAM，之前指向已下线的老站点
> （302 到 200 + text/html 的 soft-404）。所以 **2020-06 之前确实补不到**，
> 但那是天花板，不是"只有 2 期"。
>
> **判定仍是 B，理由换成两条「错了不响」的坑**（都写在 `fetch/asx.py` 的口径坑里）：
> 同名诱饵 ASX Compliance MAR（中招表现是"上市实体数对、成交全空"，不抛异常）、
> 以及分品种链接的 soft-404 与**陈注解**（2024-11 / 2024-12 两期的 PDF 链接注解都指向
> 9 月那一份，字节数 / Content-Type / `%PDF-` 全正常，只有首页抬头能认出来）。
> 这一版的 B 比原来那版更硬 —— 原来的 B 靠"数据拿不到"，现在靠"拿错了不会报错"。
>
> ⚠ 另外：**数据够用不等于能进池。** ASX 至今仍进不了 `build/pools.py` 的 `interest_rate` 池，
> 因为起点 2020-06 晚于全仓基期 2019-01（池合计求交集 ⇒ 基期那一格变 nan ⇒ 整页 skip）。
> 完整理由见 `build/pools.py` 的 `interest_rate` → `excluded` 与 `docs/verify/asx.md` §横截面追记。

**但文档质量与判定分离**：口径坑章节有 3 处硬错误（E1/E2/E3）+ 3 个高危遗漏（M1/M4/M8），
**直接照抄实现会静默产出错数据**。上面第 4、6 节的修正必须并入后再进实现阶段。
