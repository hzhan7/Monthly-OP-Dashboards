# NDAQ — Nasdaq, Inc. 月度经营数据源侦察

侦察日期 2026-08-06 · 全部结论均来自当日实测下载与解析，脚本与原始文件在
`/tmp/exch_recon/scratch/`。**本轮未修改 `/Users/hainan/Projects/monthly-op-dashboards` 任何文件。**

---

## 判定

**B（可实现但有坑）**

主源干净得接近 A：一个稳定 UUID 直链 → 一份 2 页 PDF → 四条月度序列 + 一张季度面板，
`urllib` + 浏览器 UA 直接 200，无 Cloudflare / 无 JS 渲染 / 无登录墙，
解析结果与官方自己的季度数**逐季闭合**（最大偏差 0.4%），
发布日有**三个互相独立的官方证人**（新闻稿电头 / PDF creationDate / HTTP Last-Modified，同一天）。

扣到 B 的**唯一原因是历史深度不对称**：

| 序列 | 能回溯到 | 说明 |
|---|---|---|
| 美股现货 matched 成交量 / 市占 / 交易日 | **2005-09** | nasdaqtrader.com 官方 xlsx，250 个月零断档 |
| 美股期权成交量 | **2025-01** | 只有 IR 那份 PDF 有，滚动 19–24 个月窗口 |
| 欧洲期权与期货成交量 | **2025-01** | 同上 |
| 欧洲现货成交额 | **2025-01** | 同上 |

也就是说：**四条头条月度序列里只有一条满足「至少 2019 起」，另外三条今天只有 19 个月。**
IR 那份 PDF 每月被原地替换，历史版本只在 Wayback 上（本机 hook 硬禁 web.archive.org），
Nasdaq 官网/IR/SEC 三个允许的口子里都找不到这三条序列的月度历史。
季度口径可回溯到 **1Q23**（PDF 第 2 页），能顶住同比但顶不住指数化。

⇒ 如果仓库对「四条腿都要 ≥2019」是硬要求，那三条腿单独看是 **C**（需降级：先用季度面板 1Q23 起，
月度从 2025-01 起逐月长）。整页作为一个 dashboard 建，判 **B**。

---

## 数据源

### 主源（月度，唯一真值）

| 项 | 值 |
|---|---|
| 落地页 | `https://ir.nasdaq.com/financials/volume-statistics` |
| 直链 | `https://ir.nasdaq.com/static-files/465d2157-c476-4546-a9f7-8d7ad0c9be77` |
| 格式 | PDF，2 页，Excel 导出（producer = `Microsoft® Excel® for Microsoft 365`） |
| 当期文件名 | `Monthly Reporting Sheet - July 2026 Final.pdf`（走 `Content-Disposition`） |
| 抓取方式 | `urllib.request` + 浏览器 UA，**必须带 UA** |
| 解析 | PyMuPDF `page.get_text('words')` + x/y 坐标分列分行 |

落地页上那一条叫 **"Monthly Metrics"** 的链接就是它（`<div class="blueHeading">Monthly Volumes</div>` 下面唯一一条 `dd`）。
UUID 自身**不带月份**，每月被原地替换 —— 所以：

- 「最新月」不能从 URL 或文件名推，只能**解析 PDF 内容**取「当年那一行最后一个非空月」；
- `Content-Disposition` 的 `filename` 里带月份（`… - July 2026 Final.pdf`），可作为交叉校验，但
  **不能当唯一判据**（"Final" 这个词说明还存在过非 Final 版）。

### 深度历史源（美股现货，官方）

```
列表页  https://www.nasdaqtrader.com/Trader.aspx?id=MarketShare
直链    https://www.nasdaqtrader.com/content/marketstatistics/marketshare/{YYYY}/marketshare{YY}.xlsx
        例 …/2026/marketshare26.xlsx      （sheet "US Equities" 一张表就含全部 250 个月）
同目录  …/2026/msoption26.xlsx            （期权，**只有 3 个月快照**，见口径坑 6）
```

`nasdaqtrader.com` 是 Nasdaq 自营的美国市场官方数据站（Nasdaq / PHLX / ISE / GEMX / MRX / NTX 的
规则、费率、统计都发在这里），**不是第三方聚合商**，符合 README 的硬约束。
`marketshare26.xlsx` 与 `marketshare25.xlsx` 都能直接下（`urllib` 连 UA 都不用带），
2022 及更早的年份文件 302 到 http404 页 —— 但用不着，**26 那一份自己就含 2005-09 起的全部历史**。

### 发布日源（source_dates）

```
https://ir.nasdaq.com/news-releases/news-release-details/nasdaq-reports-{month}-{year}-volumes
季末月           …/nasdaq-reports-{month}-{year}-volumes-and-{Q}q{yy}-statistics
2024 及更早       …/nasdaq-{month}-{year}-volumes          （无 "reports-"）
```

新闻稿正文**一个数字都没有**（只写「数据已挂在 IR 网站」），所以它的唯一用途就是作发布日的证人。

### 降级/旁证源（不做主数据，只备注）

- Nordic 官方月度统计稿：`https://api.news.eu.nasdaq.com/news/query.action?...&freeText=Statistics from Nasdaq Nordic Exchange`
  → 附件 PDF `Statistics_{Month}_{Year}_summary.pdf`，**可回溯到 2017-09**，纯 JSON API 免登录。
  但它给的是**本币 ADV**（SEK/EUR/DKK/ISK 分市场）和「cleared derivatives contracts/day」，
  与 IR 的 USD 口径不是同一条序列，只能当 sanity check（实测见「实测证据」第 5 条）。
- Nasdaq Commodities 月报 PDF：`https://www.nasdaq.com/solutions/monthly-market-reports-european-commodities`
  上挂 2014-01 起的逐月 PDF 直链（文件名不规则，2024-05 之后页面就没再更新）。这是北欧电力/商品业务，
  IR 那四条序列里根本不含它，**不要拿去凑「欧洲衍生品」**。

---

## 可提取字段

命名照 `series/cboe.csv` 风格（带单位后缀）。**注意 Nasdaq 官方给的是月度总量不是 ADV**，
所以列名用 `vol_` 前缀而不是 `adv_`；要跟 CME/Cboe 比就再用 `trading_days` 现算（见口径坑 1）。

### A 组 —— IR Monthly Reporting Sheet（PDF 第 1 页，月度）

| 列名 | 口径 |
|---|---|
| `vol_us_options_mmcontracts` | 美股期权当月**总成交合约数**（百万张）。六家 Nasdaq 期权所（NOM / PHLX / ISE / GEMX / MRX / NTX）合计，**含 index options**（PDF 脚注 1 明说 capture 口径含指数期权） |
| `vol_eu_derivs_mmcontracts` | 欧洲期权与期货当月总合约数（百万张），1 位小数 |
| `vol_us_matched_shares_mm` | 美股 on-exchange **matched** 股数（百万股）= Nasdaq + NTX(原 BX) + PSX 三个盘口撮合量之和（已实测证明，见证据 2）。不含内化与 TRF 报盘 |
| `vol_eu_equity_value_usdbn` | 欧洲现货成交**金额**（USD 十亿），1 位小数。注意是美元不是欧元 |

### B 组 —— nasdaqtrader marketshare{YY}.xlsx（月度，深度历史）

| 列名 | 口径 |
|---|---|
| `us_consolidated_vol_shares_bn` | 全市场 consolidated volume（十亿股），分母 |
| `us_nasdaq_matched_shares_bn` | 仅 The Nasdaq Stock Market 盘口撮合量 |
| `us_ntx_matched_shares_bn` | Nasdaq Texas（**2026 年起的名字，之前叫 BX**）撮合量 |
| `us_psx_matched_shares_bn` | PSX 撮合量 |
| `us_matched_mktshare_pct` | (Nasdaq+NTX+PSX) / consolidated，与 IR 季度那行「matched market share as a % of total industry volume」同口径 |
| `us_trading_days` | 当月美股交易日数（换算 ADV 用） |

> B 组的 `us_nasdaq_matched_shares_bn + us_ntx + us_psx` **等于** A 组的 `vol_us_matched_shares_mm`
> （18 个重叠月误差 ≤0.011%）。两组一起入库不是冗余：A 组是 IR 口径的权威值、B 组是历史与分拆，
> 且 B 组多出「分母」和「交易日」，A 组一个都没有。

### C 组 —— IR 第 2 页季度面板（季度，月度不发，`_q` 后缀单独存一份 `series/ndaq_q.csv`）

`q_us_options_mmcontracts` / `q_us_options_mktshare` / `q_us_options_capture_usd` /
`q_eu_derivs_mmcontracts` / `q_eu_derivs_capture_usd` /
`q_us_matched_shares_mm` / `q_us_matched_share_of_total` / `q_us_onexch_share_of_total` /
`q_us_matched_share_of_onexch` / `q_us_equity_capture_usd_per1k` /
`q_eu_equity_value_usdbn` / `q_eu_equity_mktshare` / `q_eu_equity_capture_usd_per1k` /
`q_etp_aum_usdbn` / `q_avg_aum_usdbn` / `q_index_futures_mmcontracts` /
`q_listed_cos_us` / `q_listed_cos_nordic` / `q_listed_cos_total` / `q_listed_etps` / `q_listed_total`

其中 revenue capture 四列是**本题要的 estimated revenue capture** —— 官方明确只按季发，
且当期那一格是 estimate（脚注 1 原文：*"Current period revenue capture is estimated until
confirmed when final quarterly results are issued"*）。**页面上必须注明它是估计值且会被改。**

---

## 历史深度

| 序列 | 最早 | 最新 | 断档 |
|---|---|---|---|
| `us_*`（B 组，nasdaqtrader） | **2005-09** | 2026-06 | **无**（250 个月连续，5 个字段零空值） |
| A 组四条（IR PDF） | **2025-01** | 2026-07 | 无（当期文件恒含「上一整年 + 本年 YTD」= 19–24 个月） |
| C 组季度面板 | **2023-Q1** | 2026-Q2 | 无（当期文件恒含 14 个季度滚动窗口） |
| Nordic 月度统计稿（旁证） | 2017-09 | 2026-07 | 未逐条核 |

**为什么 A 组回不去**：IR 那个 static-file UUID 是「当前最新一期」的稳定别名，每月原地替换，
历史期不在 IR 站上留任何副本；新闻稿正文没有数字，2016 年那批新闻稿的附件（实测下载
`92d76af2-…` → `NDAQ_News_2016_2_4_Financial.pdf`）也只是新闻稿本身的 PDF、同样没有数据表。
唯一的历史副本在 Wayback，而本机 hook 对 `web.archive.org` 是硬禁（历史 15/15 失败）。

**跨年不会掉数据**：12 月那期含全年 12 个月，次年 1 月那期含上一整年 + 1 月 —— 与 Cboe 那种
「跨年后上一年 12 月的 RPC 永远补不上」的窟窿不同，这里没有窟窿。

---

## 发布节奏

**次月第 2–6 个日历日**发上个月数据；**季末月（3/6/9/12）晚几天**，因为那期要一起更新第 2 页季度面板。
实测（新闻稿日期，逐条打开页面读的，不是推算）：

| 数据月 | 发布日 | | 数据月 | 发布日 | | 数据月 | 发布日 |
|---|---|---|---|---|---|---|---|
| 2026-01 | 02-04 | | 2019-01 | 02-04 | | 2016-01 | 02-04 |
| 2026-02 | 03-05 | | 2019-02 | 03-04 | | 2016-02 | 03-03 |
| 2026-03 | **04-08** | | 2019-04 | 05-06 | | 2016-04 | 05-05 |
| 2026-04 | 05-05 | | 2019-05 | 06-03 | | 2016-05 | 06-06 |
| 2026-05 | 06-03 | | 2019-07 | 08-06 | | 2016-07 | 08-04 |
| 2026-06 | **07-08** | | 2019-08 | 09-04 | | 2016-08 | 09-06 |
| 2026-07 | 08-05 | | 2019-10 | 11-04 | | 2016-10 | 11-03 |
|  |  | | 2019-11 | 12-02 | | 2016-11 | 12-06 |

⇒ `build/roster.py` 的 `LAG` 建议 **(6, 9)**（常规月 6 天，季末月 9 天）。
闸门按仓库规矩再减 `EARLY=3`。

nasdaqtrader 的 `marketshare{YY}.xlsx` 慢得多：June-2026 那版 `Last-Modified: Mon, 13 Jul 2026 19:11:15 GMT`
（官方自己写「Monthly Market Activity 约在次月第 10 个工作日可得」）。**所以 B 组必然比 A 组晚一个多星期**，
不能拿 B 组当「最新月」的判据。

### source_dates 溯源（三个独立证人，同一天）

| 证人 | 值（2026-07 那期） |
|---|---|
| 新闻稿标题日 + GLOBE NEWSWIRE 电头 | `Nasdaq Reports July 2026 Volumes` / `NEW YORK, Aug. 05, 2026 (GLOBE NEWSWIRE)` |
| PDF `creationDate`（= `modDate`） | `D:20260805140952-04'00'` → 2026-08-05 14:09:52 EDT |
| static-file HTTP `Last-Modified` | `Wed, 05 Aug 2026 18:28:01 GMT` → 2026-08-05 14:28 EDT |

三者同为 **2026-08-05**，PDF 存盘早于上线 19 分钟。
**建议 evidence 首选新闻稿电头**（它是官方对外的正式断言，且不会因重传而变），
`creationDate` 作第二证人写进同一条 evidence。理由与 `fetch/hkex.py` 相反：HKEX 哪儿都不写发布日
只能退而求其次用 Last-Modified；Nasdaq 有明确电头，就不该用会被重传污染的 Last-Modified 当第一证人。

---

## 口径坑（按踩坑概率排序）

1. **官方给的是「当月总量」，不是 ADV** —— 这是本家与 CME / Cboe / HKEX 最大的口径差。
   Cboe 的 `adv_*` 是日均，Nasdaq 这四条是月度合计。要横截面比就必须自己除交易日：
   美股交易日在 `marketshare{YY}.xlsx` 的 `Trading Days` 列（2005-09 起全有），
   **欧洲交易日 IR 一个字都不给**（Nordic 月度统计稿正文里有一句「Vilnius 22 天、其余 23 天」，
   要 OCR 正文才拿得到）。⇒ 欧洲两条序列只能画月度总量，不要硬转 ADV。

2. **PDF 左缘有旋转 90° 的分区侧标**（`Equity Derivatives` / `Cash Equities` / `Index` / `Listings`），
   bbox 恒为 `x0=30.9, x1=40.3`，y 跨度覆盖整个分区。按 y 聚行会把它们混进正文，
   第 1 页会拼出 `Derivatives January February …` 导致表头识别当场失配。
   **不能用 x 阈值切**（第 2 页正文标签本身也从 x≈30 起排），要用「bbox 窄而高」判旋转：
   `len(word) > 2 and (x1-x0) < (y1-y0)`。这是实测踩到的第一个坑。

3. **第 2 页的标签会换行、脚注号单独成词**，同一行里 `Nasdaq on-exchange matched market share`
   与 `… as a % of total industry volume` 是两个不同指标，前者是后者的子串。
   纯文本流解析必错位。必须先用季度表头行拿到 14 个列 x 坐标，再按
   「x < 首列 x − 20 = 标签、其余 = 值」切，并且**匹配标签时用 startswith 且长的优先**。

4. **`BX` → `NTX` 改名（2026 起）**。`marketshare25.xlsx` 的列头是 `BX Matched Volume`，
   `marketshare26.xlsx` 是 `NTX Matched Volume`（Nasdaq BX 迁址改名 Nasdaq Texas）。
   同一根序列换了名字，写死列名跨年必炸。要 `'NTX Matched Volume' if 存在 else 'BX Matched Volume'`。

5. **`ir.nasdaq.com` 对默认 `Python-urllib/3.x` UA 是「挂住不返回」而不是 403**。实测：
   落地页 45 秒 `TimeoutError`、static-file 30 秒 `RemoteDisconnected`；
   同一条 URL 换浏览器 UA 后 1.6–1.9 秒 200。这与仓库里 HOOD 那条 Akamai/JA3 记录**表现相同但成因不同**
   —— 这里 `curl` 与 `urllib` 带上普通 UA 都能过，说明拦的是 UA 不是 TLS 指纹，
   **不需要 curl_cffi / nscurl**。同一站的新闻稿页面反而默认 UA 也能过（策略只挂在部分路径上），
   所以「有一条 URL 能通」不能证明「这个域没问题」。
   `nasdaqtrader.com` 完全不挑 UA。

6. **`msoption{YY}.xlsx` 不是期权版的 marketshare** —— 别拿它填 `vol_us_options_mmcontracts`。
   两个致命差别：(a) 它只含 **NOM + PHLX + NTX/BX 三家**，标题写死
   `Nasdaq Stock Market and Nasdaq BX Volumes`，不含 ISE / GEMX / MRX；
   (b) 它是**三个月的快照**（本月 / 上月 / 去年同月），不是历史序列，且每年那一份年底就定格。
   实测 2026-06：`msoption26` 的 Combined = 214,471,257 张，IR 同月是 **428 百万张** —— 差一半。

7. **同名标签在第 2 页出现两次**：`Volume (mm contracts)` 同时是美股期权段和欧洲衍生品段的行名，
   `Market share` 同时是美股期权段和欧洲现货段的行名，`Revenue capture per contract` 也是两段各一次。
   必须先用大标题（`U.S. equity options quarterly summary` / `European options and futures quarterly summary` / …）
   切段再查行，全表 grep 标签名必抓错（与 `fetch/cboe.py` 口径坑 2 同型）。

8. **季度 revenue capture 的当期那一格是估计值，会被改**。脚注 1 原文：
   *"Current period revenue capture is estimated until confirmed when final quarterly results are issued."*
   本轮只拿到一份 PDF，**无法实测重述幅度**（历史版本拿不到）。
   ⇒ 保守做法：capture 四列对已有值不覆盖，但把当期那一格标记成可覆盖一次（下一期文件到手时刷新），
   或者干脆在图上给最后一个季度画成空心点 + 注明 estimate。

9. **月度加总与官方季度不完全相等**（因为月度是四舍五入后印出来的）。实测最大偏差
   0.397%（2026-Q2 欧洲现货：月度和 278.1 vs 官方 277）。
   ⇒ 严格校验的阈值取 **0.6%**，取更严会每季度误报一次；也**不要**拿月度和去覆盖官方季度值。

10. **`marketshare{YY}.xlsx` 的 "US Equities" sheet 底部混着说明文字行**（第 1 列是数字 `4` 但同行是
    一大段 Handled Market Share 的定义），`max_row` 一路到 259。按「第 1 列是 datetime」筛行，
    不要按行号或非空判断。同一工作簿还有 `NASDAQ` / `NYSE` / `Amex + Regional` / `US_ETF` 四张分 tape 的表，
    **列头完全一样**，取错 sheet 数字会小一大截且不会报错。

11. **B 组的 `Consolidated Volume` 与 `NASDAQ Matched Volume` 是股数（个位），A 组是百万股**。
    两者差 1e6，写列名时单位后缀必须写清楚，否则横截面页上会差六个数量级。

12. 新闻稿 slug 三套命名，回溯抓发布日时要按序试：
    `nasdaq-reports-{m}-{y}-volumes`（2025+）→ `nasdaq-{m}-{y}-volumes`（2024 及更早）→
    季末月再加 `-and-{Q}q{yy}-statistics`。实测 2016/2019 的季末月（3/6/9/12）四种拼法都没命中，
    命名还有第四套，**回补发布日时季末月大概率要人工找**。

---

## 实测证据

脚本：`/tmp/exch_recon/scratch/ndaq_parse.py`（解析器）、`ndaq_verify.py`（核对），
输出存 `ndaq_verify_out.txt`。实测下载的官方文件：

```
ndaq_2026-07.pdf   352,432 B  IR Monthly Reporting Sheet - July 2026 Final   （2026-08-05 版）
ndaq_ms26.xlsx     266,892 B  nasdaqtrader marketshare26.xlsx                （2026-07-13 版，含 2005-09..2026-06）
ndaq_ms25.xlsx     259,110 B  nasdaqtrader marketshare25.xlsx                （2025 年定格版，含 2005-09..2025-12）
ndaq_opt26.xlsx     17,153 B  nasdaqtrader msoption26.xlsx                   （2026-06 快照）
ndaq_opt25.xlsx     16,872 B  nasdaqtrader msoption25.xlsx                   （2025-12 快照）
ndaq_2016-01.pdf    14,751 B  2016-01 新闻稿附件（证明它不含数据表）
ndaq_nordic_stats_2026-07.pdf  Nordic 官方 7 月统计稿
```

### 1) 解析出的最新一期月度数字（IR PDF 第 1 页，2026-07 edition）

```
us_options_mmcontracts   n=19  2025-01..2026-07
  2025: 302 306 327 346 316 296 317 323 378 423 351 380
  2026: 384 373 393 382 389 428 402
eu_derivs_mmcontracts    n=19
  2025: 5.3 4.8 5.8 5.5 4.9 5.2 4.3 3.8 7.1 5.8 4.3 6.0
  2026: 4.9 5.1 7.6 4.4 4.3 4.6 4.1
us_matched_shares_mm     n=19
  2025: 43,688 42,588 51,273 59,214 49,454 49,572 53,416 49,123 56,035 65,603 53,382 52,388
  2026: 56,874 58,110 68,730 54,204 57,757 72,547 56,161
eu_equity_value_usdbn    n=19
  2025: 67.1 78.1 88.5 90.0 80.0 72.8 73.9 66.8 74.3 85.3 78.0 68.0
  2026: 96.9 109.3 105.3 89.4 95.5 93.2 88.0
```

季度面板（14 个季度全部解析成功，21 行无缺失），摘几行：

```
q_us_options_mmcontracts  1Q23..2Q26 = 811 746 790 781 773 776 858 921 935 957 1018 1154 1150 1200
q_us_options_capture_usd                $0.13 …… $0.10 $0.10 $0.10
q_us_matched_share_of_total             16.7% …… 14.4% 15.1% 14.7%
q_us_equity_capture_usd_per1k           $0.64 …… $0.61 $0.56 $0.69
q_eu_equity_mktshare                    69.4% …… 73.9% 74.3% 74.5%
q_etp_aum_usdbn                         $366 …… $882 $836 $1,114
q_listed_total                          5,413 …… 5,599 5,677 5,768
```

### 2) 交叉核对 A：IR 月度数 vs nasdaqtrader（**独立文件、独立域名**）

假设 `IR us_matched_shares = NASDAQ matched + NTX matched + PSX matched`，18 个重叠月逐月比：

```
2025-01  IR=43,688      trader合计=43,688.090   差 +0.0002%   (trading_days=20)
2025-06  IR=49,572      trader合计=49,567.017   差 -0.0101%   (trading_days=20)   ← 最大偏差
2025-12  IR=52,388      trader合计=52,386.493   差 -0.0029%   (trading_days=22)
2026-03  IR=68,730      trader合计=68,729.714   差 -0.0004%   (trading_days=22)
2026-06  IR=72,547      trader合计=72,546.039   差 -0.0013%   (trading_days=21)
```

18/18 月全部 |差| ≤ 0.011%。**这同时证明了两件事**：解析没抓错行，
以及 IR 那条「U.S. matched equity volume」的确切口径是三个 Nasdaq 盘口撮合量之和。

### 3) 交叉核对 B：季度市占率（IR 官方 vs 用 trader 分子分母现算）

```
2025-Q4   trader算 14.4090%   IR官方 14.4%    IR成交量 171,373mm   trader 171,371mm
2026-Q1   trader算 15.0726%   IR官方 15.1%    IR成交量 183,714mm   trader 183,713mm
2026-Q2   trader算 14.7239%   IR官方 14.7%    IR成交量 184,500mm   trader 184,505mm
```

三个季度的市占率误差 ≤0.03pp，成交量误差 ≤0.003%。

### 4) 交叉核对 C：PDF 自身闭合（月度求和 vs 官方季度），24 组全过

```
US 期权     2025-Q1 935 vs 935 (+0.000%)   2025-Q4 1154 vs 1154 (0.000%)   2026-Q2 1199 vs 1200 (-0.083%)
欧洲衍生品  六个季度全部 ±0.000%
US matched  2026-Q1 183,714 vs 183,714 (0.000%)   2026-Q2 184,508 vs 184,500 (+0.004%)
欧洲现货    2026-Q1 311.5 vs 312 (-0.160%)        2026-Q2 278.1 vs 277 (+0.397%)  ← 最大偏差
```

### 5) 交叉核对 D：Nordic 官方月度统计稿（第三个域名）

2026-07 那份写：*"The value of average daily share trading amounted to EUR 3.3 billion … all other
exchanges had 23 trading days."* → 3.3 × 23 = EUR 75.9bn ≈ USD 88.0bn（EURUSD ≈ 1.16），
与 IR 的 `eu_equity_value_usdbn = 88.0` 吻合。
但同一份稿写「cleared derivatives contracts/day = 202,060」→ ×23 = 4.65mm 张，
IR 同月是 4.1mm 张 —— **不是同一口径**（Nordic 那个含固收衍生品与清算 OTC）。
⇒ 欧洲现货那条可用它做 sanity check，欧洲衍生品那条不可以。

### 6) 重述体检：两个 vintage 的同一份 xlsx

`ndaq_ms25.xlsx`（2025-12 定格）与 `ndaq_ms26.xlsx`（2026-06 版）重叠 **244 个月（2005-09..2025-12）**，
对 `consolidated / nasdaq_matched / psx_matched / trading_days` 四个字段逐格比：

```
逐格不一致数 = 0
```

**Nasdaq 不重述美股月度成交量。** 这与 Cboe（官方明说 subject to revisions）和 HKEX（IPO 暂定数每月上修）
是相反的性质 —— 所以本家的 `update()` 可以不做重述台账，但**季度 revenue capture 除外**（口径坑 8）。

### 7) 历史深度与连续性

```
marketshare26.xlsx "US Equities"：月份数 250   最早 2005-09   最新 2026-06   断档：无
consolidated / nasdaq_matched / second_matched / psx_matched / trading_days 五个字段空值均为 0
```

### 8) 无人值守可行性

```
                                带浏览器UA                    裸 urllib 默认 UA
IR 落地页                      200  103,179B  1.93s          FAIL 45s TimeoutError
IR static-file (PDF)           200  352,432B  1.65s          FAIL 31s RemoteDisconnected
IR 新闻稿(July 2026)            200  103,657B  0.67s          200  0.25s
trader Trader.aspx?id=MarketShare  200  58,600B  1.33s        200  1.33s
trader marketshare26.xlsx      200  266,892B  2.06s          200  1.67s
trader msoption26.xlsx         200   17,153B  1.40s          200  1.39s
```

无 Cloudflare / 无 PerimeterX / 无 JS 渲染 / 无登录墙 / 无验证码；**不需要 curl_cffi 或 nscurl**。
唯一要求是带一个正常浏览器 UA。全部数据都在静态文件里（落地页只需正则抓一条 `/static-files/<uuid>` 链接）。

---

## 属于哪些竞争池

### 地理池

| 池 | 落不落 | 跨家可比的那个字段 |
|---|---|---|
| **北美现货** | ✅ 主战场 | `vol_us_matched_shares_mm ÷ us_trading_days` → 日均 matched 股数。与 Cboe 的 `adv_us_equities_matched_shares_bn` 直接同口径（都是 matched shares 的 ADV，只差 10⁻³ 量纲）。**更硬的可比字段是 `us_matched_mktshare_pct`** —— 分母（consolidated volume）两家共用同一个市场总量，份额可以直接叠在一张图上，不受量纲和 FX 干扰 |
| **北美期权** | ✅ | `vol_us_options_mmcontracts ÷ trading_days` → ADV（千张）。与 Cboe `adv_us_options_kcontracts` 同口径。⚠ Nasdaq 这个数**含指数期权**，Cboe 把 multi-list 与 index 分开列 —— 要比就用 Cboe 的 `adv_us_options_kcontracts`（总数），不要拿 Cboe 的 multilist 去比 |
| **欧洲现货** | ✅ | `vol_eu_equity_value_usdbn` vs Cboe `adv_eu_equities_adnv_eurbn`。**两家币种不同（USD vs EUR）且一个是月度总额一个是 ADNV**，要比必须同时做 FX 与交易日换算 —— 建议横截面页上只比**市占率**（Nasdaq 季度 `q_eu_equity_mktshare` 74.5% vs Cboe 的欧洲份额），别比绝对值 |
| **欧洲衍生品** | ✅（体量小） | `vol_eu_derivs_mmcontracts`（月度总张数）。可与 Eurex / Euronext 的月度合约数比。⚠ 4–8mm 张/月，比 Eurex 小两个数量级，同一张图上会被压平，建议做**指数化**而非绝对值 |
| **亚太现货 / 亚太衍生品** | ❌ | Nasdaq 无亚太交易场所 |
| **单一市场垄断对照** | ❌ | Nasdaq 在每个池里都是竞争者不是垄断者，正好是 HKEX 那种垄断样本的对照面 —— 可以作为「垄断 vs 竞争」这张图里的**竞争侧样本** |

### 标的池

| 池 | 落不落 | 可比字段 |
|---|---|---|
| **单股与ETF期权** | ✅ | `vol_us_options_mmcontracts`。跨家可比对象：Cboe `adv_multilist_options_kcontracts`、MIAX、BOX 的月度合约数。⚠ 口径坑 6：不要用 `msoption{YY}.xlsx` 那个三家合计数 |
| **股指衍生品** | 🟡 间接 | `q_index_futures_mmcontracts`（跟踪 Nasdaq 指数的期货 + 期货期权 + 指数期权成交量）。**这不是 Nasdaq 自己撮合的量**，是别家（主要 CME 的 NQ / MNQ）在别家交易所成交、Nasdaq 只收授权费的量。所以它**不能**跟 CME 的 `adv_equity_kcontracts` 摆在同一根柱子上比「谁的成交大」，只能作为「Nasdaq 指数 IP 的变现基数」单独画。真要比 CME 的股指业务，比的是 `q_index_futures_mmcontracts` 与 CME `adv_equity_kcontracts` 的**重合部分** —— 那是同一批合约被两家分别记账 |
| **利率衍生品** | ❌ | Nasdaq 北欧固收衍生品体量微小且不单独披露 |
| **能源商品** | ❌ 主线不落 | Nasdaq Commodities 有独立月报 PDF（2014→2024-05），但 IR 那四条序列不含它。要做就是另开一列，且源已停更 |
| **FX** | ❌ | Nasdaq 无 FX 撮合业务（对比：Cboe 有 `adv_fx_adnv_usdbn`） |
| **加密** | ❌ | 无 |

### 建议再开的第三类池（Nasdaq 独有，本仓目前没有）

**上市与指数 AUM 池** —— `q_listed_cos_us` / `q_listed_total` / `q_etp_aum_usdbn`。
可比对象是 HKEX 的 `new_listings` / `mktcap_hkdtn` 和 MSCI 的 AUM 序列。
Nasdaq 是本仓 12 家里少数同时有「交易量」和「上市/指数 AUM」两条腿的公司，
把它只放进交易量池会丢掉一半的经营叙事。注意这几个都是**季度**，得进 `series/ndaq_q.csv`。
