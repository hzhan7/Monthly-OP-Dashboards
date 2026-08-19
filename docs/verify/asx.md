# ASX（ASX Limited，澳大利亚证券交易所）—— 数据源可行性侦察

侦察日期 2026-08-06 ｜ slug `asx` ｜ 本轮只做侦察，未改动 `/Users/hainan/Projects/monthly-op-dashboards` 任何文件
临时脚本与样本 PDF 全在 `/tmp/exch_recon/scratch/`

> **2026-08-19 追记（本轮回补改掉的 5 处事实 + 1 条新结论）** —— 本文是 **2026-08-06** 的
> 点位侦察报告，**原文一字未删**；下面几条在 2026-08-18/19 那轮回补里被实发推翻，
> 各相关小节已就地加追记。
>
> ① **「辅源 1（ASX 24 分品种）只有最近 2 期、历史 404、不可回补」—— 全错，而且错在我们这边。**
>    根因是本仓抓取器 `fetch/asx.py::_SFE_LINK` 把文件名的日期段写死成 8 位数字，
>    而官方五年换过 **5 代命名**、日期段有 YYMMDD / DDMMYY / DDMMYYYY 三种写法
>    （2026-02 那期还从 DDMMYY 退回 YYMMDD），主机名 www/www2、协议 http/https 也乱换。
>    正则只认词干、日期段一个数字都不解释之后，2026-08 逐月实发 2020-06…2026-05 共 **72 期
>    全部 200 + `application/pdf` + `%PDF-`**，用未改动的 `parse_sfe` 全部解析成功。
>    `series/asx.csv` 那 8 列今天是 **2020-06 → 2026-07 共 74 个月、零空洞**（2026-08-19 实测）。
>    ⇒ 不是官方撤了历史，是我们自己拼错了文件名。见 §判定、§辅源列、§历史深度、口径坑 8。
>
> ② **真正的天花板是 2020-06，而且它是硬的 —— 判据是「链接指向哪个目录」，不是「多久以前」。**
>    2019-12…2020-05（以及 2016-09…2019-11）的 MAR 正文印的是老站点路径
>    `/data/market-reports/…`，该路径今天整体 302 到 `content/asx/404.html`
>    （**200 + text/html 的 soft-404**，不校验内容就会当成成功）；2016-01…2016-08 的 MAR
>    正文里根本没有这条链接。⇒ 结论从「只能往后攒」改成「**2020-06 之前补不到**」。
>
> ③ **落地的列名与口径都与本文的建议不同，别照着本文找列。** 实际入库的是 8 列
>    `contracts_spi200_futures` / `oi_spi200_futures` / `contracts_3y_bond_futures` /
>    `oi_3y_bond_futures` / `contracts_10y_bond_futures` / `oi_10y_bond_futures` /
>    `contracts_90d_bankbill_futures` / `oi_90d_bankbill_futures`，**是月度总张数，不是 ADV**。
>    本文 §辅源列 那套 `adv_*_futures_contracts` 命名**一个都没有落地**。
>
> ④ **§横截面 利率衍生品那条「回补期只能退用 `adv_futures_contracts` 合计当代理」的建议作废。**
>    现在有真的分品种序列，用不着代理；而且那个代理口径自身就有漂移（期货合计**含电力与 NZ 品种**，
>    占比逐年变），本来也不该作为长期方案。
>
> ⑤ **§横截面 能源商品那条「电力期货只在辅源 1 里、2026-06 起」的日期同样过期**，
>    但结论要换个方向改：辅源 1 的窗口已是 2020-06 起，而**本仓一列电力/NZ 都没抽**
>    （`fetch/asx.py::SFE_SPEC` 只取 AP / YT / XT / IR 四个代码）。
>    ⇒ 从「建不起历史」改成「**建得起，但本仓没建**」。
>
> ⑥ **新结论：数据够用 ≠ 能进池。** 8 列 74 个月零空洞之后，ASX **仍然进不了**
>    `build/pools.py` 的 `interest_rate` 池，卡点与数据质量无关 —— 见 §横截面·标的池
>    之后新增的「为什么有了分品种数据，ASX 仍进不了利率池」。

---

## 判定

**B（可实现，但有坑）**

拆开说：

| 部分 | 判定 | 理由 |
|---|---|---|
| **ASX Group Monthly Activity Report（MAR）全部字段** | **A** | 纯 HTTP GET，裸 `urllib`（连自定义 UA 都不需要）即 200；无 Cloudflare / Akamai / JS 渲染 / 登录墙；官方自家域名 `asx.com.au`；发现逻辑确定；78 期连续无断档，存档可到 2009-12；与年报 / 新闻稿逐项 **0 偏差** 交叉核对通过 |
| **ASX 24 分品种（SPI 200 / 3yr / 10yr 国债 / 90d Bank Bill）月度 ADV 与 OI** | ~~**C**~~ → **A**（2026-08-19 改判） | 原文：数据存在、格式干净、也是 `asx.com.au` 自家 DAM，但~~**官方只保留最近 2 期**，历史 404，**无法回补**。只能从 2026-06 起往后逐月攒~~ —— **后半句已被实发推翻**，见文首追记 ① ②：实际是 **2020-06 → 2026-07 共 74 个月零空洞**已入库，"只有 2 期"是本仓文件名正则太窄造的假象 |

之所以整体记 B 而不是 A：任务起点线索里点名要的「3年期与10年期国债期货、SPI 200 的 ASX 24 ADV」正好落在那块只有 2 个月窗口的源上。MAR 本身只给 **futures 合计**，不拆品种。除此之外没有别的障碍。

之所以不记 C：现货 ADT、上市公司数、融资额、期货合计 ADV、股票期权 ADV 这五项——也就是横截面页真正要用的东西——全部 A 级可得，且能一路回到 2016 年初。

> **2026-08-19 追记：上面这段「记 B 不记 A」的理由已经不成立。** 承重的那句
> （分品种源"只有 2 个月窗口"）是假象，见文首追记 ①。今天分品种与 MAR 同为 A 级可取，
> 只是**窗口不同**：MAR 2016-01 起 127 个月，分品种 2020-06 起 74 个月。
> **但整体判定仍留 B**，理由换成另外两条实测坑（都写在 `fetch/asx.py` 的口径坑里）：
> 同名诱饵 ASX Compliance MAR（口径坑 1，中招表现是"上市实体数对、成交全空"且不报错）、
> 以及分品种链接的 **soft-404 与陈注解**（口径坑 2 / 22 —— 2024-11 与 2024-12 的 PDF
> 链接注解都指向 9 月那一份，HTTP 层完全合法，只有首页抬头能认出来）。
> 这两条都属于"能无人值守、但错了不响"，B 仍然是对的档位。

---

## 数据源

### 主源：ASX Group Monthly Activity Report（月度经营报告，PDF）

ASX 自己是上市公司（ASX:ASX），MAR 是它按澳洲持续披露义务发给 ASIC 与自家 Market Announcements Office 的**市场公告**，性质等同于美股的 8-K Item 7.01。首页抬头逐字写着：

> `ASX GROUP MONTHLY ACTIVITY REPORT – JULY 2026` / `Release of market announcement authorised by: Andrew Tobin, Chief Financial Officer`

两条独立取回路径，都在 `www.asx.com.au` 一手域名上：

**路径 A（月度增量用，2020-02 起，无同意页）—— 媒体中心页 + DAM 直链**

```
索引页  https://www.asx.com.au/about/media-centre
        整页服务端渲染，一次 GET 拿到 493 条 PDF href，其中 80 条是 MAR
直链    https://www.asx.com.au/content/dam/asx/about/media-releases/{YYYY}/
        {seq}-{DD}-{month}-{YYYY}-asx-group-monthly-activity-report-{month}-{YYYY}.pdf
例      .../2026/43-06-august-2026-asx-group-monthly-activity-report-july-2026.pdf
        （seq=43 是**日历年内公告序号**，与数据月无关；不要拿它拼 URL，只能从索引页读）
```

文件名末尾的 `{month}-{YYYY}` 是**数据月**（已实测确认：`...-february-2020.pdf` 内页写 "ASX GROUP MONTHLY ACTIVITY REPORT – FEBRUARY 2020 / 5 March 2020"）。

**路径 B（历史回补用，2009-12 起，有 click-through 条款页）—— 历史公告存档**

```
列表  https://www.asx.com.au/asx/v2/statistics/announcements.do?by=asxCode&asxCode=asx&timeframe=Y&year={YYYY}
      纯 HTML 表格，给标题 + idsId + **精确到分钟的发布时刻**（"06/08/2026  8:40 am"）
中转  https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId={idsId}
      返回一页 ASX「使用条款」同意页；页面里的 <input name="pdfURL" value="..."> 隐藏字段
      直接写出真实 PDF 直链
直链  https://announcements.asx.com.au/asxpdf/{YYYYMMDD}/pdf/{hash}.pdf
```

> ⚠ 路径 B 的中转页是一个**点击即接受条款**的同意页。本次侦察只做了 GET（读隐藏字段 + 下载 PDF），**没有 POST 那个表单**。要不要在无人值守里穿过它属于策略决定，不是技术问题。
> **建议**：历史回补一次性人工跑路径 B；月度 cron 只走路径 A（无同意页、无中转）。

**另有第三条冗余路径**（备而不用）：`https://asx.api.markitdigital.com/asx-research/1.0/companies/ASX/announcements` 返回最近 5 条公告的 JSON（含 `documentKey`），PDF 走 `https://asx.api.markitdigital.com/asx-research/1.0/file/{documentKey}`。这是 `asx.com.au` 网站自身的后端（MarkitDigital 是 ASX 的网站服务商，不是聚合商），但它**只回 5 条**、且不是 asx.com.au 域名 —— 只适合当「本月发了没有」的探针，不适合当主源。

### 辅源 1：ASX 24 Monthly SFE Trading Report（分品种，只有近 2 期）

```
https://www.asx.com.au/content/dam/asx/documents/unlinked-docs/monthly-futures-markets-report-{DDMMYYYY}.pdf
DDMMYYYY = 该数据月的最后一个日历日
```

实测：`31072026` → 200（133 KB）、`30062026` → 200；`31052026` / `31122025` / `30062025` / `31122016` / `30062016` → **全部 404**。这个直链**写在 MAR 正文里**（MAR 第 4 页原文给出当期链接），所以不用猜，跟着 MAR 走即可。

内容：每个合约一行，给 `Mth Vol 本年 / Mth Vol 去年 / YTD 本年 / YTD 去年 / Op Int 本年 / Op Int 去年`。含 SPI 200(AP)、3 Year Bonds(YT)、10 Year Bonds(XT)、90-Day Bank Bills(IR)、30 Day Interbank Cash Rate(IB)、20 Year Bonds(LT)、各州电力期货、小麦、NZ 产品。

### 辅源 2：ASX Historical market statistics（月末市值与指数，回溯到 2004）

```
https://www.asx.com.au/about/market-statistics/historical-market-statistics          （2016 至今）
https://www.asx.com.au/about/market-statistics/historical-market-statistics/historical-market-statistics-archive  （2015 及更早）
```

服务端渲染的 HTML `<table>`，给 `All Ords price index / S&P/ASX 200 price index / Total end of month market cap ($m)` 与 `Number of companies and securities listed`。MAR 里**没有**月末市值，要画「市值 vs ADT 换手率」得靠这一页。

### 辅源 3：年报「Transaction levels and statistics」（年度基准，用于对账）

`https://www.asx.com.au/content/dam/asx/annual-reports/asx-{YYYY}-annual-report.pdf` 的第 150–152 页，5 年一张表，**分品种年度合约数**（SPI 200 / 90d bank bills / 3yr / 5yr / 10yr / 20yr bonds / 30 day cash rate / agricultural / electricity / NZ 90d）。不是月度，但**是校验月度加总的唯一权威基准**（见「实测证据」）。

---

## 可提取字段

照 `series/cboe.csv` 风格（单位后缀 + 月份 `YYYY-MM`）。全部来自 MAR，除非注明。

### 现货（Cash Markets）

| 列名 | 口径 |
|---|---|
| `adt_cash_onmarket_audbn` | on-market 日均成交额 A$bn。= (Open trading + Auctions + Centre Point) ÷ 现货交易日。**不含** trade reporting |
| `adt_cash_total_audbn` | 含 trade reporting 的日均成交额 A$bn |
| `value_cash_onmarket_audbn` | 当月 on-market 成交额 A$bn（MAR 行名 `On-market value`） |
| `value_cash_total_audbn` | 当月总成交额 A$bn（`Total cash market value`） |
| `value_centrepoint_audbn` | Centre Point（ASX 自家暗池 / 中点撮合）成交额 A$bn |
| `value_tradereport_audbn` | 场外成交事后向 ASX 报告的金额 A$bn |
| `trades_cash_total` | 当月成交笔数（含 equity + ETP + interest rate 三类） |
| `adt_cash_trades` | 日均成交笔数 |
| `avg_value_per_trade_aud` | 平均每笔金额 A$ |
| `trading_days_cash` | 现货交易日数 |
| `vix_asx200_avg` | S&P/ASX 200 VIX 月内日均值。⚠ **「2016 年后才有此行」说的是表行，不是这个数**：2019-10 之前 MAR 把它印在正文要点里（`The average daily S&P/ASX 200 VIX was 11.3`），2019-10 起才多出表行；两处 26 期并存实测同值。`fetch/asx.py::_vix_from_prose()` 因此在表里取不到时从正文取，**这一列的 `since` 是 2016-01 而不是 2019-10**，2026-08-19 实测 2016-01..2026-07 共 127 个月一格不缺 |

### ASX 24 期货与期货期权

| 列名 | 口径 |
|---|---|
| `adv_futures_contracts` | 期货日均张数（含利率、SPI 200、商品、能源；**含 NZ 产品**） |
| `adv_options_on_futures_contracts` | 期货期权日均张数 |
| `adv_futures_total_contracts` | 上面两者合计日均张数（横截面池的主用字段） |
| `trading_days_futures` | 期货交易日数（与现货**经常不等**） |

### 股票期权（ASX Clear ETO）

| 列名 | 口径 |
|---|---|
| `adv_single_stock_options_contracts` | 单股期权日均张数 |
| `adv_index_options_contracts` | 指数期权日均张数（不含 SPI 200 期货期权） |
| `trading_days_eto` | ETO 交易日数 |

### 上市与融资

| 列名 | 口径 |
|---|---|
| `listed_entities_total` | 月末在册实体总数（含股票、批发/零售债、LIC/LIT、订书式实体；**不含** ETF 与 mFund） |
| `new_listed_entities` | 当月新上市实体数 |
| `delisted_entities` | 当月退市实体数（2026 版才有独立行，早年只在正文里） |
| `mktcap_new_listings_audmn` | 新上市实体的挂牌市值 A$mn（**2017 年后口径**，早年是 `Initial capital raised`，见口径坑 5） |
| `capital_secondary_audmn` | 二次融资额 A$mn（**窄口径**，不含换股对价） |
| `capital_other_scrip_audmn` | 含 scrip-for-scrip 的其他融资 A$mn |
| `capital_secondary_total_audmn` | 上面两者之和（MAR 行名 `Total secondary capital raised`） |
| `capital_new_quoted_audmn` | 新增挂牌资本合计 A$mn（`Total new capital quoted`） |
| `capital_net_new_quoted_audmn` | 扣除退市市值后的净增 A$mn（2026 版才有） |

### 清算 / 结算 / 抵押品

| 列名 | 口径 |
|---|---|
| `otc_notional_cleared_audbn` | 当月 OTC 利率衍生品中央清算名义额 A$bn（**双边计数**，官方脚注明说） |
| `otc_open_notional_audbn` | 月末未平仓名义额 A$bn（双边计数） |
| `billable_cash_cleared_audbn` | 当月可计费现货清算金额 A$bn |
| `chess_holdings_audbn` | 月末 CHESS 托管证券市值 A$bn |
| `austraclear_holdings_audbn` | 月末 Austraclear 托管证券市值 A$bn |
| `margin_total_audbn` | 月末参与者保证金总额 A$bn（ASX Clear + ASX Clear (Futures) + 债券抵押） |
| `settlement_msgs_mn` | 当月 dominant settlement messages（百万条） |
| `participants_asx_total` / `participants_asx24_total` | 月末参与者数（2021 年后才有此段） |

### 辅源列（另建 CSV 或同表补列）

| 列名 | 来源 | 口径 |
|---|---|---|
| `mktcap_total_audmn` | 辅源 2 | 月末全市场市值 A$mn（**含外国注册**，与年报的 domestic 口径不同） |
| `index_allords_close` / `index_asx200_close` | 辅源 2 | 月末指数点位 |
| `adv_spi200_futures_contracts` | 辅源 1 | SPI 200 期货月度总量 ÷ 交易日；~~**只有 2026-06 起**~~ ← 见下方追记 |
| `adv_3y_bond_futures_contracts` | 辅源 1 | 3 年期国债期货（代码 YT）；同上 |
| `adv_10y_bond_futures_contracts` | 辅源 1 | 10 年期国债期货（代码 XT）；同上 |
| `adv_90d_bankbill_futures_contracts` | 辅源 1 | 90 日银行票据期货（代码 IR）；同上 |
| `oi_3y_bond_contracts` / `oi_10y_bond_contracts` / `oi_spi200_contracts` | 辅源 1 | 月末未平仓张数；同上 |

> **2026-08-19 追记：上表这 8 行两处都没落地 —— 列名不同、口径也不同。**
> 实际入库的是下面这 8 列（`fetch/asx.py::SFE_SPEC`，2026-08-19 从 `series/asx.csv` 现算）：
>
> | 落地列名 | 段 / 合约代码 | 口径 | 覆盖 |
> |---|---|---|---|
> | `contracts_spi200_futures` / `oi_spi200_futures` | `equity indices - futures` / **AP** | 当月总张数 / 月末 OI | 2020-06 → 2026-07（74，0 空洞） |
> | `contracts_3y_bond_futures` / `oi_3y_bond_futures` | `interest rates - futures` / **YT** | 同上 | 同上 |
> | `contracts_10y_bond_futures` / `oi_10y_bond_futures` | `interest rates - futures` / **XT** | 同上 | 同上 |
> | `contracts_90d_bankbill_futures` / `oi_90d_bankbill_futures` | `interest rates - futures` / **IR** | 同上 | 同上 |
>
> 两处差异都会咬人：
> · **是月度总张数，不是 ADV** —— 要 ADV 自己除 `trading_days_futures`（那一列 2016-01 起 127 个月全有）。
>   本仓 series 只放官方原始披露，派生量在 build 层用 `per_day` 算。
> · **`oi_90d_bankbill_futures` 上表压根没列**（原文只提了 3 个 OI 列），实际是 4 个品种各有 OI。
>
> 另外：**先切 section 再查代码，不能只查代码** —— 同一个 `3 Year Bonds / YT` 在
> `Interest Rates - Futures` 与 `Interest Rates - Options` 两段各出现一次。

---

## 历史深度

| 路径 | 覆盖 | 断档 |
|---|---|---|
| 媒体中心（路径 A） | **2020-02 → 2026-07，78 期** | **0**（逐月核过） |
| 历史公告存档（路径 B） | **2009-12 → 2026-07，199 期** | 仅 **2010-02** 一期（该期标题写法不同，正则漏掉，人工可补） |
| 辅源 1 分品种 | ~~**2026-06 → 2026-07（滚动 2 期）**~~ → **2020-06 → 2026-07，74 期**（2026-08-19） | ~~更早全部 404，**不可回补**~~ —— 已全部回补，**0 空洞**；真 404 的是 **2020-05 及更早**（老站点 soft-404），见文首追记 ① ② |
| 辅源 2 市值/指数 | **约 2004 → 2026-06** | 未逐月核 |

**版式代际（决定实际可用起点）** —— 实测切换点精确到月：

| 期间 | 版式 | 单一解析器能否覆盖 |
|---|---|---|
| 2015-10 及之后 | 现代版：`TRADING – FUTURES` 在前、`TRADING – EQUITY OPTIONS` 在后 | ✅ |
| 2015-09 | 过渡版：两套标题同时出现 | ⚠ 需特判 |
| 2015-08 及之前（到 2013 左右） | 旧版：合并成 `TRADING – FINANCIAL DERIVATIVES MARKETS`，**期权段在期货段之前** | ⚠ 需第二套 label map |
| 2012 及更早 | 更旧，字段错位、偶有空 token 让 `float()` 炸 | ❌ 不建议 |

**建议 series 起点：`2016-01`**（版式统一、字段最全、正好落在仓库偏好的 2015/2016）。退一步可到 `2015-10`。追到 2009 收益极低、代价很高。

> **2026-08-19 追记：这条建议已落地。** `series/asx.csv` 今天是 **2016-01 → 2026-07 共 127 行 × 55 列**
> （2026-08-18 从 2017-10 起前推 21 个月）。⚠ 行数不等于列长，三列另有各自的边界：
> `participants_asx_total` / `participants_asx24_total` **2016-07 才有**（2016-01…06 的 MAR
> 正文到 SETTLEMENT 段就结束，官方没印）、`capital_initial_raised_audmn` 与
> `capital_total_raised_incl_other_audmn` **2023-09 之后官方不再印**。
> ~~「分品种数据只有 2 个月窗口且不可回补」（下文口径坑 8）**没变**。~~
> ⚠ **这一句写下的当天（2026-08-19 晚些时候）就被推翻了**：修掉 `fetch/asx.py::_SFE_LINK`
> 之后那 8 列已回补到 **2020-06 → 2026-07 共 74 个月、零空洞**。见文首追记 ①，
> 以及口径坑 8 下方的追记。（留着这句作废的原话是有用的：它说明 2026-08-18 那一轮
> 只重验了 MAR 主源，**没有去实发分品种链接** —— 光凭上一份文档的断言就写了"没变"。）

---

## 发布节奏

**次月第 3–8 个日历日，众数第 5–6 日。** 199 期公告时间戳的分布（来自历史公告存档页，精确到分钟）：

```
次月第 3 天 : 31 期      次月第 6 天 : 60 期
次月第 4 天 : 38 期      次月第 7 天 : 13 期
次月第 5 天 : 55 期      次月第 8 天 :  2 期
```

发布时刻集中在悉尼时间 **8:30–9:30 am**（例：2026-07 数据 `06/08/2026 8:40 am`）。

**没有季末月特殊性** —— ASX 财年 6 月底结束，但 6 月的月报照常在 7 月初发（2025-06 数据 → 2025-07-04；2026-06 数据 → 2026-07-06）。`build/roster.py` 的 `LAG` 建议直接写 `(8, 8)`，两档相同。

**source_dates 溯源字段（三条，按权威度排序）：**

1. **PDF 正文第一行的日期**——首页抬头就是 `6 August 2026`，是 ASX 自己写的发布日，**首选**。正则 `^\s*(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})\s*$` 在 2010–2026 全部样本上都命中。
2. 历史公告存档页的日期 + 时刻（`06/08/2026  8:40 am`），可精确到分钟，与 1 一致。
3. DAM 副本的 HTTP `Last-Modified`（`Wed, 05 Aug 2026 23:10:54 GMT` = 2026-08-06 09:10 AEST）。**它比真实发布晚约 30 分钟**（公告 8:40 am 上市场，DAM 副本 9:10 am 才上传），所以只能当旁证，**不要拿它当发布日**。

---

## 口径坑（按踩坑概率排序）

1. **同一份 PDF 里 `Average daily contracts` 出现 5 次**，依次是 期货 / 期货期权 / 期货合计 / 单股期权 / 指数期权。**绝不能按出现序号取**，必须先用 section 大标题（`TRADING – FUTURES` / `TRADING – EQUITY OPTIONS`）切段再查行 —— 这就是 `fetch/cboe.py` 口径坑 2 的同一类错误。
   **实测代价**：本次先按序号写了一版，跑 2015-07 那期时把 ETO 的 342,964 写进了 `adv_futures_total`、把期货的 404,251 写进了 `adv_single_stock_options`、把期货期权的 5,224 写进了 `adv_index_options` —— 全部串位且**每个数都是合法数字，静默错到底**。原因是那一代版式里期权段排在期货段前面。

2. **列数是按行变的，不是按报告变的。** 8 月至次年 6 月的报告，流量类行有 **4 列** `[本月, 去年同月, 本财年 YTD, 去年同期 YTD]`；时点类行（`Total listed entities` / `Value of CHESS holdings` / margins）只有 **2 列**；而 **7 月**那一期因为 YTD ≡ 本月，官方直接把后两列删掉，整份只有 2 列。
   ⇒ 只能取「标签右侧第 1 个数字」。任何「取最后一列」「按列数判断是哪一代」的写法都会在某个月炸。
   实测同一份 2026-06 报告里：`Secondary capital raised` → `[2465, 3384, 37849, 31499]`，`Total listed entities¹` → `[2042, 2083]`。

3. **ASX 会当天补发更正版，而更正版第 1 页是「错误值 vs 正确值」对照表。**
   实测 2025-01：原版 `Centre Point 9.548` / `trade reporting 17.523` —— 与 2024-12 的值**一模一样**，是复制粘贴事故；ASX 当天另发 `CORRECTION TO ASX GROUP MONTHLY ACTIVITY REPORT – JAN 2025`，正确值 `8.852` / `14.199`。
   用原版加总 FY25：Centre Point 偏 **+0.48%**、trade reporting 偏 **+1.18%**、总成交额偏 **+0.22%**；换成更正版后与年报**逐项 0 偏差**。
   ⇒ 索引里出现 `correction` 的那一期必须**优先于**同月原版；且解析更正稿时必须**跳过第 1 页**，否则会把对照表里的「错误值」列当成本月值。已知另有 2022-06 一份 correction。

4. **口径断点：Listings 段在 2016/2017 之间换过定义。**
   - 2016 版：`Initial capital raised ($million)`（IPO 实际募资额）
   - 2026 版：`Quoted market capitalisation of new listings ($million)`（新上市实体的挂牌市值）
   这两个**不是一回事**：FY26 新闻稿同时给出 `IPO capital raised $5.6bn` 与 `new listings added $32.6bn in quoted market capitalisation`，差 6 倍。同样 `Total capital raised including other` → `Total new capital quoted` 也换了名字。
   ⇒ 跨 2016/2017 这条序列**不可直接连比**，画图要按仓库约定打红色虚线结构性断点。

5. **`Total secondary capital raised` ≠ 新闻稿说的 follow-on。** MAR 里 `Total secondary = Secondary capital raised + Other capital raised including scrip-for-scrip`。FY26 实测：窄口径 **$37.849bn**（新闻稿 follow-on `$37.8bn` ✅），含换股对价 **$58.428bn**。
   ⇒ 两列都要存，只存一列必然对不上任何一份官方文本。

6. **交易日数有三套且经常不等**：cash / futures / ETO。2026-04 实测 `cash=19, futures=20, ETO=19`。用 `ADV × 交易日` 反推月度总量时配错就整月偏 5%。

7. **ASX 现货 ≠ 澳洲现货全市场。** Cboe Australia（原 Chi-X）的成交不在 MAR 里。要谈「澳洲市场规模」或 ASX 份额，得另抓 Australian Cash Market Report 周报（`/content/dam/asx/markets/trade-our-cash-market/acmr/{YYYY}/{month}/acmr-weekly-{YYYYMMDD}.pdf`，2021 起、每周一期）。本仓的横截面页若只用 MAR，口径是「ASX 自身经营量」，不是「澳洲市场量」—— 这点要在图注写明。

8. ~~**分品种数据只有 2 个月窗口，且不可回补。** `monthly-futures-markets-report-{DDMMYYYY}.pdf` 实测 `31072026`/`30062026` 200，`31052026` 起全部 404。年报里有 FY 级分品种 5 年表（FY21–FY25），可以做年度对照，但做不出月度序列。~~
   ~~⇒ 若要 3yr/10yr/SPI 200 的月度序列，**只能从 2026-06 起逐月抓、往后攒**，且这份报告在 MAR 正文里给链接，漏抓一个月就永久缺一个月。~~

   > **2026-08-19 追记：整条作废，而且这条坑的诊断本身就是坑。**
   > 上面那次实测（`31052026` 404）是**拿本文自己拼出来的文件名去请求的**，官方那一期的
   > 真名是 `290526` —— 404 的是我们编的 URL，不是官方的文件。逐期实测的五代命名：
   >
   > ```
   > 2019-12…2020-01  /data/market-reports/MonthlySfeMarketsReport{YYMMDD}.pdf
   > 2020-02…2020-05  /data/market-reports/MonthlyFuturesMarketsReport{YYMMDD}.pdf
   > 2020-06          …/unlinked-docs/MonthlyFuturesMarketsReport{YYMMDD}.pdf
   > 2020-07…2022-02  …/unlinked-docs/finance-reports[/{YYYY}]/monthly-futures-markets-report-{YYMMDD}.pdf
   > 2022-03 至今     …/unlinked-docs/monthly-futures-markets-report-{日期}.pdf
   > ```
   >
   > 日期段：2025-07 之前 YYMMDD、2025-08…2026-05 改 DDMMYY（**2026-02 那期又写回
   > YYMMDD 的 `260227`**，所以连"哪一代用哪种"都不成规则）、2026-06 起 DDMMYYYY。
   > ⇒ 正确做法是**只认文件名词干，日期段一个数字都不解释**，链接一律从 MAR 正文里取。
   >
   > 结果：2020-06…2026-05 共 **72 期全部取回并解析成功**，连同原有 2 期共 **74 个月零空洞**。
   > 两条独立判据（都是官方自己在别处印的同一个数，不是我们算的）：
   > ① **跨期自证** —— t 期报告的第 2 / 第 6 个数字列就是 t−12 月的当月量 / 月末 OI，
   >    撞 series 已有行，**495/496 格逐位一致**；唯一那格是官方后期重述
   >    （2025-03 期把 2024-03 的 YT 当月量印成 5,378,144，当期原印 5,379,506），
   >    按本仓规矩入库留**当期原值**。
   > ② **页尾 `Total Exchange` 当月量 ≡ 同月 MAR 的期货合计**，74/74 全等。
   >
   > **仍然成立的两点**（别一起丢掉）：
   > · **2020-06 是硬天花板** —— 更早的 MAR 印的是老站点路径，今天整体 302 到
   >   200 + text/html 的 **soft-404**（口径坑 2 说的就是它）；2016-01…2016-08 的 MAR
   >   正文里连这条链接都没有。所以"补不到"这三个字对 2020-05 及更早仍然成立。
   > · **链接印在 MAR 正文里**（期货段末尾"Volume of futures trading by individual
   >   contract is available at the following link:"），所以跟着 MAR 走、不用猜文件名 ——
   >   但**光跟着走还不够**：正文里的 URL 会在 `-` 处换行断开（2020-08…11 四期），
   >   而 PDF 链接注解 8 期缺失、2 期多带句号、**2024-11 与 2024-12 两期是陈的、都指向
   >   9 月那一份**。⇒ 正文优先、注解兜底、逐条试，最终由 `parse_sfe()` 的首页抬头校验当判官
   >   （陈注解取回的是一份完全合法的 9 月报告，字节数 / Content-Type / `%PDF-` 全正常）。
   >   完整记录见 `fetch/asx.py` 口径坑 22。

9. **竖排水印 `For personal use only` 会污染标签。** pymupdf 把这四个词按 y 坐标并进任意一行的词流，实测把 `Total notional cleared value ($billion)¹` 变成 `For Total notional cleared value ($billion)¹`，前缀锚定的正则直接失配。必须先按词过滤掉 `For|personal|use|only`。

10. **数值列的左边界要按页宽比例算，不能全行扫数字。** 标签内嵌数字的行会被吃掉：`S&P/ASX 200 VIX (average daily value) 11.3 11.3` 会被读成「本月值 = 200」。实测 `numcut = 0.47 × 页宽` 对 2010–2026 全部版式都成立（值列 x 起点：2016 版 ~311，2026 版 ~450；标签最远 ~262）。

11. **`OTC 名义额是双边计数`**（官方脚注 `Cleared notional value is double sided`）。与 CME / LCH 的口径不同，跨家比之前要先统一。

12. **上市实体数含债券发行人。** `Total listed entities` 的脚注写明含批发/零售债、LIC/LIT、订书式实体，**不含 ETF 与 mFund**。和 HKEX 的 `new_listings`（主板+GEM 股票）口径不同，横截面页放一起要标注。

13. **媒体中心文件名里的序号是日历年内公告序号，不是月份。** `43-06-august-2026-…` 的 43 与数据月无关；2020–2021 那批文件名甚至完全不带发布日（`asx-group-monthly-activity-report-june-2020.pdf`）。⇒ 发布日只能从 PDF 正文或存档页取，别从文件名反推。

14. **路径 B 有 click-through 条款页。** 2020-02 之前的回补必须经过 `displayAnnouncement.do`，它先返回一页 ASX 使用条款同意表单。本次侦察只 GET 读了隐藏字段里的真实直链、没有 POST 表单。是否让 cron 自动穿过属于策略决定 —— 建议历史回补人工一次性跑完，月度增量走无同意页的路径 A。

15. **媒体中心是单页全量渲染（493 条 PDF、508 KB）。** 现在没有分页，但一旦 ASX 改成分页/懒加载，发现逻辑即失效。⇒ 主源用媒体中心，失败时退回 `announcements.do` 存档（该页 2009 年至今结构十年未变），两条腿都断才抛异常。

---

## 实测证据

### 环境与反爬结论

```
$ python3 -c "import urllib.request; ..."   # 裸 urllib，默认 Python-urllib UA，不带任何 header
200  508206  Thu, 06 Aug 2026 01:20:54 GMT  https://www.asx.com.au/about/media-centre
200  106264  Wed, 05 Aug 2026 23:10:54 GMT  https://www.asx.com.au/content/dam/asx/about/media-releases/2026/43-06...
200  121463  None                            https://www.asx.com.au/asx/v2/statistics/announcements.do?...&year=2016
```

⇒ **无 Cloudflare / 无 Akamai / 无 JS 渲染 / 无登录墙 / 不校验 UA**。`curl`、`urllib` 均直接可用，不需要 `nscurl` / `curl_cffi`。满足无人值守。

### 用到的临时脚本

```
/tmp/exch_recon/scratch/grab.py       # 两条腿的发现与下载（media centre / announcements 存档）
/tmp/exch_recon/scratch/parse_mar.py  # MAR PDF -> dict（词坐标行聚类 + 数值列左边界 + 水印过滤）
```

### 证据 1：最新一期解析（2026-07，2026-08-06 发布）

`python3 parse_mar.py asx_mar_2026-07.pdf`（值 = 当月，pcp = 2025 年同月）

```
adt_cash_onmarket_audbn                cur=6.645            pcp=5.952
adt_cash_total_audbn                   cur=7.861            pcp=7.151
value_cash_total_audbn                 cur=180.814          pcp=164.465
value_cash_onmarket_audbn              cur=152.834          pcp=136.9
value_centrepoint_audbn                cur=12.748           pcp=13.053
value_tradereport_audbn                cur=27.98            pcp=27.565
adt_cash_trades                        cur=2744978.0        pcp=2078536.0
trades_cash_total                      cur=63134490.0       pcp=47806329.0
trading_days_cash                      cur=23.0             pcp=23.0
avg_value_per_trade_aud                cur=2864.0           pcp=3440.0
vix_asx200_avg                         cur=11.3             pcp=11.3
adv_futures_contracts                  cur=711012.0         pcp=592065.0
adv_options_on_futures_contracts       cur=2400.0           pcp=833.0
adv_futures_and_opt_contracts          cur=713411.0         pcp=592898.0
trading_days_futures                   cur=23.0             pcp=23.0
adv_single_stock_options_contracts     cur=208578.0         pcp=203595.0
adv_index_options_contracts            cur=24992.0          pcp=26132.0
trading_days_eto                       cur=23.0             pcp=23.0
otc_notional_cleared_audbn             cur=635.499          pcp=706.591
otc_open_notional_audbn                cur=4872.671         pcp=5066.189
listed_entities_total                  cur=2045.0           pcp=2092.0
new_listed_entities                    cur=12.0             pcp=16.0
capital_new_quoted_audmn               cur=9352.0           pcp=7701.0
capital_secondary_audmn                cur=6209.0           pcp=6033.0
mktcap_new_listings_audmn              cur=3143.0           pcp=1668.0
chess_holdings_audbn                   cur=3562.9           pcp=3345.1
austraclear_holdings_audbn             cur=3625.1           pcp=3268.6
billable_cash_cleared_audbn            cur=167.565          pcp=150.73
```

同一期的**公告平台副本**（103,441 B）与 **asx.com.au DAM 副本**（106,264 B）是两个不同的 PDF 文件，解析结果 **28/28 字段完全一致**。

### 证据 2：较早一期解析（2016-06，2016-07-05 发布）

`python3 parse_mar.py asx_mar_2016-06.pdf`（节选，与 PDF 原文逐字核过）

```
adt_cash_onmarket_audbn                cur=4.484            pcp=4.259
adt_cash_total_audbn                   cur=5.04             pcp=4.802
value_cash_total_audbn                 cur=105.833          pcp=100.841
trades_cash_total                      cur=22321943.0       pcp=17570452.0
adt_cash_trades                        cur=1062950.0        pcp=836688.0
adv_futures_contracts                  cur=747360.0         pcp=641005.0
adv_futures_and_opt_contracts          cur=755601.0         pcp=646361.0
adv_single_stock_options_contracts     cur=347474.0         pcp=411453.0
adv_index_options_contracts            cur=70639.0          pcp=44044.0
otc_notional_cleared_audbn             cur=644.46           pcp=101.975
listed_entities_total                  cur=2204.0           pcp=2220.0
capital_new_quoted_audmn               cur=2811.0           pcp=14806.0
```

另跑通的期次：2010-06、2013-06、2014-06、2015-07/08/09/10/11/12、2016-01、2019-06、2020-02、2024-07 ~ 2026-07 共 30+ 期。

### 交叉核对 A —— 与 **ASX 2025 年报**「Transaction levels and statistics」（p.150-151）对账

把 **12 份独立的月度 PDF**（2024-07 ~ 2025-06）解析出来后加总，与年报公布的 FY25 数字比：

| 指标 | 12 份月报加总 | 2025 年报 | 偏差 |
|---|---|---|---|
| Cash market trading days | 253 | 253 | **0** |
| Total cash market trades ('000) | 475,356.742 | 475,357 | **-0.0001%** |
| Average daily cash market trades | 1,878,880.4 | 1,878,880 | **+0.0000%** |
| Total cash market value ($bn) | 1,823.068 | 1,823.068 | **0.00000%** |
| Trade reporting ($bn) | 281.402 | 281.402 | **0.00000%** |
| Centre Point ($bn) | 145.607 | 145.607 | **0.00000%** |
| Average daily on-market value ($bn) | 6.094 | 6.094 | **-0.0075%** |
| Average daily value incl trade rep ($bn) | 7.206 | 7.206 | **-0.0027%** |
| Average trade size ($) | 3,835.16 | 3,835 | **+0.0041%** |
| Futures trading days | 256 | 256 | **0** |
| Total futures + options on futures ('000) | 195,365.172 | 195,365 | **+0.0001%** |
| Daily avg futures + options contracts | 763,145.2 | 763,145 | **+0.0000%** |
| ETO trading days | 253 | 253 | **0** |
| Avg daily single stock options contracts | 247,120.6 | 247,121 | **-0.0002%** |
| Avg daily index options contracts | 28,174.8 | 28,175 | **-0.0005%** |
| OTC total notional cleared ($bn) | 7,807.729 | 7,807.729 | **0.00000%** |
| Total billable cash mkt value cleared ($bn) | 1,683.963 | 1,684.0 | **-0.0022%** |
| Total listed entities（2025-06 月报 vs 年报期末） | 2,083 | 2,083 | **0** |

> **注**：这张表是用**更正版**的 2025-01 数据算出来的。用原版（错误的 Centre Point 9.548 / trade reporting 17.523）时，Centre Point +0.48%、trade reporting +1.18%、总成交额 +0.22% —— 正是这三项偏差把「2025-01 有更正版」这个坑挖了出来，见口径坑 3。

**18 项对账，17 项偏差 < 0.008%，其余为四舍五入痕迹。**

### 交叉核对 B —— 与 **ASX 新闻稿**（2026-07-16《ASX delivers strongest listings result since FY22》）对账

把 12 份月报（2025-07 ~ 2026-06 = FY26）的 Listings 段加总：

| 指标 | 12 份月报加总 | 新闻稿原文 | 结论 |
|---|---|---|---|
| Total new capital quoted | **$91.024 bn** | "Total new capital quoted reached **$91.0 billion**" | ✅ |
| Quoted market cap of new listings | **$32.596 bn** | "New listings added **$32.6 billion** in quoted market capitalisation" | ✅ |
| Secondary capital raised（窄口径） | **$37.849 bn** | "raised **$37.8 billion** in follow-on capital during FY26" | ✅ |
| New listed entities | **100** | "A total of **100** new entities listed on ASX in FY26" | ✅ 完全相等 |
| Total secondary capital raised（含 scrip-for-scrip） | $58.428 bn | —（新闻稿不用这个口径） | 见口径坑 5 |

### 交叉核对 C —— MAR vs **同月 Monthly SFE Trading Report**（两份不同的官方文件）

2026-07：

```
MAR 第 4 页            Total futures and options on futures — Total contracts 16,408,463
                                                              Average daily contracts   713,411
SFE Report 第 3 页     Total Exchange                                        16,408,463
                       Daily Average                                            713,411
```

同期分品种（SFE Report，本次抓到的真实数字）：

```
SPI 200 (AP)               月量  814,634    OI   231,151
3 Year Bonds (YT)          月量 5,442,552   OI 1,287,283
10 Year Bonds (XT)         月量 4,502,250   OI 1,425,106
90-Day Bank Bills (IR)     月量 5,206,358   OI 1,784,007
30 Day Interbank Cash (IB) 月量    34,499   OI    25,266
利率期货小计               月量 15,194,710
```

### 交叉核对 D —— 月报之间的 pcp 链条自洽

2026-07 那期的 pcp 列（2025 年 7 月）与**一年前独立发布**的 2025-07 那期的本月列，**28/28 字段逐个相等**：

```
                       2026-07 报告的 pcp 列      2025-07 报告的本月列
adt_cash_onmarket             5.952                   5.952
trades_cash_total          47,806,329              47,806,329
adv_futures_and_opt           592,898                 592,898
adv_single_stock_options      203,595                 203,595
otc_notional_cleared          706.591                 706.591
listed_entities_total           2,092                   2,092
chess_holdings                3,345.1                 3,345.1
```

同样的链条在 2013-06 / 2014-06 之间也成立（futures+options ADV 648,310；单股期权 695,705；指数期权 18,067 —— 三项在两份相隔一年的 PDF 里完全一致）。

### 发布节奏实测（199 期公告时间戳）

```
次月第 3 天: 31   第 4 天: 38   第 5 天: 55   第 6 天: 60   第 7 天: 13   第 8 天: 2
```

覆盖检查：

```
media centre 覆盖: 78 个月; 2020-02 -> 2026-07     断档: []
存档覆盖   199 个月; 2009-12 -> 2026-07            断档: [('2010-01','2010-03')]
```

---

## 属于哪些竞争池

### 地理池

| 池 | 是否落入 | 该池里可比的字段 | 备注 |
|---|---|---|---|
| **亚太现货** | ✅ | `adt_cash_onmarket_audbn` ↔ HKEX `adt_hkdbn` | 两边都是「本币日均成交额」。**币种不同**，绝对值不可直接比 —— 建议在 build 层指数化（2016-01 = 100）或按月均汇率折 USD；FX 换算是派生量，别写进 `series/`（仓库硬约束：series 只放官方原始披露） |
| **亚太衍生品** | ✅ | `adv_futures_total_contracts` + `adv_single_stock_options_contracts` + `adv_index_options_contracts` ↔ HKEX `derivatives_adv_contracts` | 都是「张数」，但合约规模天差地别（ASX 3yr bond 面值 A$100k vs HKEX 恒指期货）。**只能比增速与指数化水平，不能比绝对张数** |
| **单一市场垄断对照** | ✅ | `otc_notional_cleared_audbn`、`billable_cash_cleared_audbn`、`chess_holdings_audbn` ↔ HKEX 同类 | ASX 在澳洲的清算 / 结算 / 上市 / 衍生品是**事实独家**，现货是唯一有竞争的环节（Cboe Australia 约占两成，且不在 MAR 数里 —— 见口径坑 7）。与 HKEX 同组做「垄断型交易所」对照最贴切 |
| 北美现货 / 北美期权 / 欧洲现货 / 欧洲衍生品 | ❌ | — | ASX 无海外市场业务 |

### 标的池

| 池 | 是否落入 | 该池里可比的字段 | 备注 |
|---|---|---|---|
| **利率衍生品** | ⚠ 见下方追记 | 首选 ~~`adv_3y_bond_futures_contracts` + `adv_10y_bond_futures_contracts` + `adv_90d_bankbill_futures_contracts`~~ → 落地列名是 `contracts_3y_bond_futures` / `contracts_10y_bond_futures` / `contracts_90d_bankbill_futures`（月总张数）↔ CME `adv_rates_kcontracts`；~~**但只有 2026-06 起**。回补期只能退用 `adv_futures_contracts` 合计（实测 FY25 利率类占 ASX 期货 ~92%，做趋势代理是可以的，要在图注写明是代理量）~~ ← **两句都作废，见下方追记** | ASX 是**澳元利率曲线的独家场所**，与 CME（美元）、Eurex（欧元）是同一生意的不同货币版本，指数化后放一张图很有信息量 |
| **股指衍生品** | ✅ | `adv_index_options_contracts`（ETO 指数期权）+ ~~`adv_spi200_futures_contracts`（2026-06 起）~~ → `contracts_spi200_futures`（**2020-06 起 74 个月零空洞**，月总张数，2026-08-19）↔ CME `adv_equity_kcontracts` / Cboe `adv_index_options_kcontracts` | SPI 200 是澳洲唯一的股指期货基准。⚠ **推断（本仓尚未立账）**：`equity_index` 池现有 5 家起点最晚的是 jpx 2014-12，ASX 的 2020-06 一进来同样会把窗口收到基期 2019-01 之后 —— 与 `interest_rate` 是同一堵墙（见本节下方追记）。但 `build/pools.py` 的 `equity_index` → `excluded` 里**没有 asx 条目**，所以这是结构推断、不是已记录的决定；真要放 SPI 200 进去得先实测一次 |
| **单股与 ETF 期权** | ✅ | `adv_single_stock_options_contracts` ↔ Cboe `adv_multilist_options_kcontracts`（注意 Cboe 是**千张**，ASX 是**张**，别忘了 ×1000） | ASX ETO 是澳洲唯一的股票期权市场，量级只有 Cboe 的千分之几，放一张图必须指数化 |
| **能源商品** | ⚠ 部分 | 分州电力期货（NSW/QLD/VIC/SA base load + $300 cap）与 NZ 电力期货，只在辅源 1 里，~~**2026-06 起**~~ → 辅源 1 的窗口已是 **2020-06 起 74 期**（2026-08-19） | ~~ASX 电力期货是澳新电力市场的主力对冲工具，但月度序列建不起历史~~ → **建得起，但本仓没建**：`fetch/asx.py::SFE_SPEC` 只取 AP / YT / XT / IR 四个代码，一列电力/NZ 都没抽。要做得先加 SPEC 行再重跑 `--sfe-backfill` |
| FX | ❌ | — | ASX 无 FX 产品 |
| 加密 | ❌ | — | ASX 无加密产品（只有几只被动持币 ETF 在现货挂牌，不构成独立业务线） |

> ### 2026-08-19 追记 —— 为什么有了分品种数据，ASX 仍进不了利率池
>
> **先把两条作废的建议说清楚：**
> · ~~「分品种只有 2026-06 起」~~ —— 假象，实际 **2020-06 → 2026-07 共 74 个月零空洞**，见文首追记 ①。
> · ~~「回补期退用 `adv_futures_contracts` 合计当代理」~~ —— **不要这么做，两个理由**：
>   ① 现在有**真的分品种序列**，没有任何理由画代理量；
>   ② 那个代理口径本身就漂 —— `adv_futures_contracts` 是 **ASX 24 全部期货合计**，
>      里面还有分州电力（NSW/QLD/VIC/SA）与 NZ 电力等品种（见上方能源商品行）。
>      "FY25 利率类占 ~92%" 是**单年**的比例，不是常数；拿一条口径随年份漂的合计线
>      去和 CME / Eurex 的纯利率线做指数化对比，斜率差里混着成分变化，读者无从分辨。
>
> **然后是真正的拦路虎，它与数据质量无关：起点 2020-06 晚于全仓基期 2019-01。**
>
> `build/pools.py` 的池合计按「**任一成员缺值该月即缺**」求交集。现状 4 家
> （cme / ice / db1 / jpx，约束成员是 jpx 的 2014-12）窗口是 **2014-12–2026-07，140 个月 0 空洞**，
> 基期 2019-01 那一格合计 = 1,986,926.8。**ASX 一进来，窗口立刻收成 2020-06–2026-07（74 个月），
> 基期 2019-01 落到窗口之外 ⇒ 基期合计 = nan**，定基指数与「自基期 ±pp」的独占度都算不出来，
> 页面直接 `skip()` 整页不发。（复刻 `build/exchanges_products.py` 第 407-471 行实测。）
>
> ⚠ **走 ICE 那条 `contracts_only`（只进增长图、不进合计）同样躲不开** —— 增长图也是
> **以 2019-01 = 100 定基**；ICE 能走这条路是因为它 2011-01 就有数。
>
> ⚠ 而 **2020-06 是官方存档天花板**（更早那批链接指向已下线的老站点、整体 soft-404，
> 见口径坑 8 的追记），所以这不是"等下一轮回补"，是"**补不到**"。
>
> 另有一处次要且**可解**的口径差：这三列是**月总张数不是 ADV**，真要入池得按 `per_day`
> 除以 `trading_days_futures`（`pools.py` 的 `per_day` / `div_col` 本来就支持，不是障碍）。
>
> ⇒ **完整、且唯一权威的理由写在 `build/pools.py` 的 `interest_rate` → `excluded` 里**
> （那份注释还记了这条结论自己被改过两次的账）。ASX 的利率量仍计入 `apac_deriv` 的混合口径。

### 跨家可比性的一句话结论

ASX 唯一能与其他家**同量纲直接对比**的字段是 **`adt_cash_onmarket_audbn`（换算或指数化后）** 与 **合约张数类 ADV（仅可指数化对比）**。其余（清算名义额双边计数、上市实体含债券发行人、on-market 不含场外报告）都各有各的口径，横截面页放一起必须在图注写清定义差异，否则读者会把「ASX 期货 71 万张/日 vs CME 2,400 万张/日」误读成规模差 34 倍——那是合约规模差异，不是业务量差异。
