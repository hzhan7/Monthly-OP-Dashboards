# 复核报告：SGX（slug: sgx）—— 对 /tmp/exch_recon/sgx.md 的独立复现

复核日期 2026-08-06。复核员未读原 agent 的解析脚本，自己重写了 `vparse.py`
（工作目录 `/private/tmp/claude-501/-Users-hainan-Library-CloudStorage-OneDrive-Personal/00bde884-5d9d-4ce5-a363-6b721a0462f5/scratchpad/`），
所有 HTTP 与数字均为本次重抓、重解析所得。

---

## 最终判定

**B —— 维持原判定。**

原报告的核心主张**全部为真且可复现**，没有任何一类虚报：

| 攻击项 | 结论 |
|---|---|
| (a) 只有最新一期却谎称多年历史 | **不成立**。我实抓并解析了 2010-02 / 2013-06 / 2015-01 / 2016-01 / 2017-06 / 2017-12 / 2018-01~06 / 2019-06 / 2019-12 / 2020-06 / 2025-06 / 2026-06，全部 plain curl HTTP 200 且可解析 |
| (b) 拿第三方聚合站当官方源 | **不成立**。全链路只有 `www.sgx.com` / `api2.sgx.com` / `api.sgx.com` / `links.sgx.com`，交叉核对用的是 SGXNet 上 SGX 自己的 News Release。无 FIA / investing.com / wikipedia |
| (c) 依赖浏览器登录态或手工点击 | **不成立**，且比原报告说的更好 —— 见「错误 1」，连 curl_cffi 都不需要 |
| (d) 字段口径写错 | **基本不成立**。张数/金额、月度总量/日均、本币/美元都分得清楚。只有一处单位换算表述含糊，见「错误 11」 |
| (e) 声称 A 但关键字段缺失 | **不适用**（它自己就报的 B），且核心档字段确实齐全 |

扣在 B 而非 A 的理由我认可（唯一格式是 PDF、CMS_VERSION 会轮换且静默失败、口径跨世代改名），
但我另外发现 **12 处错误或未记录的坑**，其中 3 处（错误 1 / 2 / 3）会直接影响实现，必须在写代码前修正。

---

## 我实际复现的证据

### 1. 发现链三步 —— 逐位一致

```
$ curl -sS https://www.sgx.com/config/appconfig.json
  HTTP=200  SIZE=4999
  CMS_VERSION = 09434be8973b96b28894aefc57aff9e6c1f8f9c6      ← 与原报告一致

$ curl -sS -G https://api2.sgx.com/content-api/ \
    --data-urlencode "queryId=$V:market_statistics_reports_list" \
    --data-urlencode 'variables={"lang":"EN","limit":1000}'
  HTTP=200  SIZE=82363                                        ← 与原报告 82,363 逐位一致
  data.list.count = 197,  len(results) = 197
  results[0] = June 2026, reportDate=1783612800, report.date=1783676970
  url = .../2026-07/SGX%20MONTHLY%20STATISTICS%20UPDATE%20%28FOR%20THE%20MONTH%20OF%20JUN%202026%29_260703_FA.pdf

$ curl -sS -L -D - -o sgx_2026-06.pdf '<上面那个 url>'
  HTTP/2 200 / content-type: application/pdf / 879518 bytes
  last-modified: Fri, 10 Jul 2026 09:49:24 GMT                ← 与原报告逐字一致
```

**覆盖完整性（我自己算的）**：`n unique = 197, first = 2010-02, last = 2026-06, gaps = []`。
零断档属实。197 条里 **PDF url 缺失数 = 0**。

**两个静默失败坑，我都复现了**：
- `variables` 不带 `limit` → `count` 仍是 197，但 `len(results) = 10`。属实。
- 假 hash → `HTTP=200` + `{"errors":[{"message":"The persisted query loader must return query string ... but got: null."}]}`。属实。

### 2. 历史真的可回溯（攻击项 a 的直接反证）

| 月份 | HTTP | 大小 | At-A-Glance 可解析 |
|---|---|---|---|
| 2010-02 | 200 | 52,236 | ❌ 文字层错乱（原报告所述属实，见下） |
| 2013-06 | 200 | — | ✅ |
| 2015-01 | 200 | 553,044 | ✅ |
| 2016-01 | 200 | 576,719 | ✅ |
| 2019-06 | 200 | 128,528 | ✅ |
| 2019-12 | 200 | 590,040 | ✅ |
| 2020-06 | 200 | 128,996 | ✅ |
| 2025-06 | 200 | — | ✅ |

2019-06 At-A-Glance（我自己解出来的）：
```
Number of Trading Days (Securities)              21      19
Securities market Turnover Volume (Million Shares) 22,874  22,620
Securities market Turnover Value ($Million)      23,113  21,900
Securities Daily Average ($Million)               1,101   1,153
Total Number of Listed Securities                   739     738
Total Market Capitalisation ($Million)          951,516 981,400
Overall Turnover Velocity                           41%     36%
Derivatives Volume                           24,245,648 20,812,816
Derivatives Daily Average Volume              1,174,449 1,078,558
```
2020-06 同样 9 行齐全（Jun 2020: 22 天 / 38,021 / 1,728 / 715 / 816,779 / 68% / 19,689,053 / 935,289）。

2010-02 的文字层实测长这样（证实「不划算」的判断）：
```
'(5) Total Market Capitalisation of Listed Securities.\n601\n446\n352,677\n(2) SGX has a
substantial number of foreign listings...\n387\nTotal Market Capitalisation (5)\n598,477\n...'
```
行列关系确实全靠坐标，建议起点 2015-01 是对的（2015-01 我实测产品表 p12/p13/p15/p16/p17 全在）。

### 3. PDF 数字 —— 我用自己的解析器逐位重解，**20 项全部一致**

原报告列的 2026-06 期数字，我一条不落地重新解出来，全部逐位相同：

```
p2  At-A-Glance 9 行         19/21 · 38,737/29,882 · 45,837/44,639 · 2,412/2,126 ·
                             601/601 · 1,123,460/1,129,411 · 56%/49% ·
                             30,483,078/34,315,225 · 1,607,949/1,619,444   ✅ 全对
p13 Total Trading Volume     [97,512,297 95,007,014 30,208,711 30,483,078 34,315,225 363,489,920 192,519,311 26,109,454 31%]  ✅
p13 Average Daily Trading    [1,672,043 1,566,512 1,479,546 1,607,949 1,619,444 1,478,988 1,618,396 1,270,536 27%]            ✅
p3  Total Market Turnover V  [125,998 133,636 43,160 45,837 44,639 455,677 259,634 26,006 72%]                                ✅
p14 FTSE China A50           [30,700,860 ... 120,528,277 61,379,118 8,553,797 37%]                                            ✅
p15 GIFT Nifty 50 Futures    [5,633,480 ... 20,699,069 11,146,431 1,615,004 20%]                                              ✅
p16 Nikkei 225 Futures       [1,964,145 ... 6,931,059 3,598,909 597,336 25%]                                                  ✅
p21 FX Futures Total         [28,026,195 29,506,143 9,670,422 9,567,681 10,268,040 96,252,265 57,532,338 6,698,923 53%]       ✅
p21 USD_CNH FX Futures       [14,928,934 ... 48,921,555 ...]                                                                  ✅
p20 INR_USD FX Futures       [10,124,683 ... 37,276,890 ...]                                                                  ✅
p24 SGX IODEX Iron Ore Fut   [15,361,249 ... 61,663,792 ...]                                                                  ✅
p24 Metal & Dry Bulk Total   [18,713,773 ... 73,586,973 34,915,155 5,455,417 4%]                                              ✅
p43 New Bond Listings        [260 242 72 114 56 1,062 502 47 19%]                                                             ✅
p40 GIFT Nifty 50 月末 OI     [261,403 297,572 258,992 290,377 297,572]                                                       ✅
```

商品合计我也自己加了一遍：
`SICOM 3,895,114 + Energy 493,152 + Metal&DryBulk 73,586,973 + Dairy期货 688,923 +
Dairy期权 104,742 + Energy Metals 2,640 = 78,771,544` ✅，Crypto Total = 337,175 ✅。
「Commodities 不含 crypto」的口径判断属实。

**衍生品日均不能反推（原坑 4）—— 实测属实**：
`34,315,225 / 21 = 1,634,058 ≠ DDAV 1,619,444`（隐含 21.19 天）；
`30,483,078 / 19 = 1,604,373 ≠ 1,607,949`（隐含 18.96 天）。而证券侧是自洽的
（`43,160/21=2,055`、`45,837/19=2,412`、`44,639/21=2,126`，与 At-A-Glance SDAV 完全吻合）。
所以「月总量与日均两个都要入库」是对的。

### 4. 交叉核对源 —— 真实存在，我自己抓下来逐句核了

**这是原报告最容易造假的地方，结果是真的。**

```
$ curl -sS -L 'https://links.sgx.com/1.0.0/corporate-announcements/IJM1XSR2Y9TQ9KE6/
               896085_20260713%20SGX%20Group%20strong%20volume%20growth%20...pdf'
  HTTP=200 (302 → /FileOpen/...ashx) / 292,608 bytes / PDF 1.7 / 2 pages / plain curl 即可
```
新闻稿正文我全文提取，原报告引的 **10 句全部逐字属实**，且与我自己解的 PDF 数字对得上：
"rose 31% y-o-y in June to 34.3 million contracts" / "DAV climbed 27% ... to 1.6 million" /
"FY2026, total volume gained 15% ... to 363.5 million" / "turnover jumped 72% ... to S$44.6 billion" /
"SDAV also rose 72% ... at S$2.1 billion" / "In FY2026, turnover climbed 35% ... to S$455.7 billion" /
"total FX futures volume climbed 31% ... to 96.3 million" / "OI rose to an all-time high of 297,572 lots" /
"overall GIFT volume increased 3% ... to 24.4 million" / "total commodities volume rose 21% ... to 78.8 million lots"。

**2015 端也真**：`YBFA1MLZ1MEE27PC/384923_010716_...pdf` HTTP=200 / 301,953 bytes，
"S$17.0 billion" / "SDAV ... S$774 million" / "Derivatives volume was 14.4 million" /
"S$904.8 billion" / "A50 ... 6.4 million, down 2%" / "Nikkei ... 2.3 million, up 46%" /
"FX Futures volume was 425,188" / "INR/USD ... 366,372" / "USD/CNH ... 51,702" 全部逐字属实。
2016-01 报告的 Dec-2015 列我重解：`17,024 / 774 / 14,362,547 / 904,770 / 22 天`，
A50 `6,373,016`（Nov 6,524,892 → −2.3%）、Nikkei `2,273,483`（Nov 1,562,084 → +45.5%）全对。

额外硬证据：我把 2016-01 p15 FX 各行的 Dec-2015 值自己加了一遍 —
`90+81+1,239+366,372+2,055+5+3,644+51,702 = 425,188`，与新闻稿逐位相同。
连原报告提到的拼写错误 **`INR_USD FX FFutures`（两个 F）在 2016-01 的 p15 上确实存在**。

**结论：交叉核对不是编的，对照源真实、一手、可 plain curl 复现。**

### 5. 其他被我逐条证实的坑

- **坑 5 官方 YoY 算错** —— 完全属实，我在 2025-06 期 p38 原样看到：
  `Fund Raised ($ million)  [83,916 66,480 21,608 29,510 15,362 295,985 150,396 20,306 -4944%]`
  （15,362 vs 20,306 正确应为 −24%）；同页上一行 New Bond Listings 的 −50% 是对的。
- **坑 7 `(#)` 重述标记** —— 2013-06 实测 13 处，含原报告引的 `62,084(#)`、`37,303(#)`，
  以及 `(#) Numbers have been restated.`。
- **坑 8 Issuer Services 列优先** —— 属实。p41 先出 5 个标签
  （`SGX Mainboard / - Primary Listings / - Secondary Listings / - IPOs / - Delistings`），
  再每列吐 5 个数，`401 373 28 2 4` 正是 FY2026 Q3 那一列（且 373+28=401 自洽）。
- **坑 3 跨世代改名** —— 属实且我补充了证据：2015-01 是 `($million)` 小写、
  且**行顺序不同**（Derivatives 在 Listed Securities 之前）；2019 是
  `Securities market Turnover Value`（market 小写）；2026 是 `Stock Market Turnover Value ($Million)`。
  按标签+归一化匹配、不能按位置，是对的。
- **坑 11 列数会变** —— 部分属实，p40 那条是错的，见「错误 7」。

---

## 发现的错误与虚报

### 错误 1 ⚠️ 高 —— Akamai / JA3 拦截的说法是**错的**，且方向正好相反

原文（次要链路 ⑤）：
> `api.sgx.com` 被 Akamai 按 TLS 指纹（JA3）拦：plain curl / urllib 一律 `403 Access Denied
> ... errors.edgesuite.net`（**与 UA、Referer、token 都无关**）。`curl_cffi(impersonate='chrome')` 实测 200。

我的实测：

```
plain curl, 不带 token                        → HTTP 401       （到了源站，不是边缘拦截）
plain curl, 带 authorizationToken             → HTTP 200, 9,264 bytes, 合法 JSON
                                                 meta.code=200, totalItems=11
plain curl  api.sgx.com/securities/v1.1/      → HTTP 200       （对照组）
```

也就是说：**这根本不是 TLS 指纹拦截，就是普通的 token 鉴权**。
「与 token 无关」这句话与事实完全相反 —— token 恰恰是唯一起作用的因素。
`curl_cffi` / `nscurl` **一个都不需要**。

顺带把 ROT13 那步也验了：`we_chat_qr_validator` 返回的
`tVncjC9Fq5mOHKlOix/En/Y0Fmjl...` → ROT13 → `gIapwP9Sd5zBUXyBvk/Ra/L0Szwy...`，
与原报告一致，站点 `index.js` 里确实是 `queryId=${CMS_VERSION}:we_chat_qr_validator`。

> 这条同时影响用户 MEMORY 里的 `reference_akamai_ja3_bypass`：SGX 不是那条经验的例子，
> 不要因为这份报告把 SGX 也登记成「JA3 受害者」。

### 错误 2 ⚠️ 高 —— `Last-Modified` 对 2018-07 及更早的月份是**站点迁移时间戳**，不是发布日

原文（source_dates 溯源 & 坑 10）把 HTTP `Last-Modified` 定为一等证据，并说
「一律用 HTTP `Last-Modified` 定发布日」。但它**只在 2026-06 这一期上验过**。

我按月抽验（`Last-Modified` 与 CMS `report.data.date` 两者恒等）：

| 数据月 | Last-Modified | 路径段 | 判断 |
|---|---|---|---|
| 2010-02 | 2018-08-21 | `2018-08/` | ❌ 迁移戳 |
| 2012-06 | 2018-08-21 | `2018-08/` | ❌ 迁移戳 |
| 2015-01 | 2018-08-21 | `2018-08/` | ❌ 迁移戳 |
| 2016-06 | 2018-08-21 | `2018-08/` | ❌ 迁移戳 |
| 2017-06 | 2018-08-14 | `2018-08/` | ❌ 迁移戳 |
| 2018-06 | 2018-08-08 | `2018-08/` | ❌ 迁移戳 |
| 2018-12 | 2019-01-09 | `2019-01/` | ✅ 真发布日 |
| 2019-06 | 2019-07-09 | `2019-07/` | ✅ |
| 2020-06 | 2020-07-13 | `2020-07/` | ✅ |
| 2026-06 | 2026-07-10 | `2026-07/` | ✅ |

**2010-02 ~ 2018-07 共约 102 期（197 期里的过半）会被盖上 2018-08-xx。**
对每月 cron 的当期没有影响（2018-08 之后都是真的），但只要有人回填
`source_dates.csv`，就会写进一百多条假发布日。原报告没有给这个限定条件。

对照仓库现有约定：`series/source_dates.csv` 里 hkex 用的正是
「xlsx 直链 HTTP Last-Modified + docProps 互证」，所以**方法本身与本仓一致**，
问题只出在原报告把它无条件推广到了历史。

### 错误 3 ⚠️ 高 —— `LAG = 13` 不安全，两头都不满足 README 的设计目标

原文：「近 30 个月实测 … `roster.py` 的 LAG 建议填 **13**」。我把 197 期全算了一遍
（剔除 2018-08 及以前的迁移戳，剩 95 个可信月）：

```
次月第 N 天分布：{6:5, 7:6, 8:10, 9:21, 10:18, 11:10, 12:8, 13:7, 14:1, 16:2, 22:2, 23:1, 24:1, 53:1, 54:1, 83:1}
超过第 13 天的 10 个月：2018-08(24) 2018-09(22) 2019-12(16) 2020-10(83) 2020-11(53)
                        2020-12(22) 2022-11(14) 2022-12(54) 2023-01(23) 2023-07(16)
最晚：2020-10 → 2021-01-22（第 83 天）
```

- **晚的一头**：LAG=13 会在这 10 个月误报红点。（2023-08 之后没再出现，尚可接受。）
- **早的一头（更要命）**：README 的闸门是 `LAG - EARLY`。最近 35 个月里
  **8 个月（23%）在第 6~7 天就发布了**（2024-04/05/07/10/11、2025-02/03/05），
  而 LAG=13 时闸门要到第 8 天才开 → 公开页面挂旧数据 1~2 天。
  这直接违反 README 写明的「改成 `-EARLY` 后 24 档**无一迟到**」。

**正确做法**：`LAG['sgx'] = (13, 13)` 保留给红点，另加
`monthly_run.EARLY_BY['sgx'] = (7, 7)`，使闸门落在第 6 天。原报告没提 `EARLY_BY` 这个机制。

### 错误 4 —— `EARLY` 常数记错了

原文：「按 README 的 `EARLY=3`，闸门从次月第 10 天开」。
实测 `monthly_run.py:67` 是 **`EARLY = 5`**，README 正文也写的 5。
所以 LAG=13 时闸门是**第 8 天**，不是第 10 天。两个数都错。

### 错误 5 —— `turnover_velocity_pct` 的起始月错了

原文两处都说 2018-01（历史深度表「2018-01 才有」、落地建议「2018-01 之前允许为空，其余不允许」）。
我逐月实测 At-A-Glance 里 `Overall Turnover Velocity` 行：

```
2017-06 ❌   2017-12 ❌   2018-01 ❌   2018-02 ❌   2018-03 ✅   2018-04 ✅   2018-05 ✅   2018-06 ✅
```

**真正的起点是 2018-03。** 按原报告写的校验规则，回填 2018-01 与 2018-02 时
会撞上 README 护栏 2（「缺列一律失败」）直接抛异常。

> **2026-08-19 追记 —— 这条「起点」也只是 p2 那一处来源的起点，序列本身已回到 2015-01。**
> `turnover_velocity_pct` 今天是 **2015-01 → 2026-07 共 139 个月**（本机现算）。
> 原因是**同一份文档里有第二处官方来源**：p2 的 At-A-Glance 确实要到 2018-03 那期才多出
> `Overall Turnover Velocity` 这一行，但在此之前 p8 的 `Turnover Velocity (5)` 表
> （首行 `SGX Overall`）**照样每期都印**。两处已闭合验证为逐格等价
> （2018-03 期 p2 印 Feb 55% / Mar 43%，同期 p8 印 Jan 41% / Feb 55% / Mar 43%，
> 跨 vintage 也一致），所以往回读那 38 个月**不产生接缝、不必画断点**。
> ⇒ `FIRST_MONTH['turnover_velocity_pct']` 现在是 `START_MONTH`（2015-01），
> 不再是 2018-03。取数顺序仍是 **p2 优先、取不到才回落 p8** —— 反过来会动到既有入库值。
> **这条错误的核查本身是对的**（原文说 2018-01 确实错），只是「2018-03 是天花板」这个
> 隐含结论被后来的 p8 回落推翻了。

### 错误 6 —— `appconfig.json` 大小写错

原文「实测 200 / **1,632 bytes**」。实测 **4,999 bytes**（原 agent 自己 scratch 里那份也是 4,999）。

### 错误 7 —— p40 是 5 列，不是 7 列

原文坑 11 说「p39/p40（GIFT 全市场）是 7 列」，解析清单里也把一条 5 值的 p40 行标成「← 7 列表」。
实测表头：p39 = 7 列 `[FYQ3, FYQ4, Apr, May, Jun, FYTD, CYTD]` ✅；
**p40 = 5 列** `[FYQ3, FYQ4, Apr, May, Jun]`（月末 OI 没有 FYTD/CYTD）。
对「按表头形状认列」的解析器是小坑，但坑 11 本身就是讲列数的，写错了得纠正。

（另：坑 2 引 p39 单品行 24,357,137、交叉核对表引 p39 Total 24,386,146，两个数我都验到了
——`24,357,137 + 29,009(Bank) = 24,386,146`，是两行不同的东西，不算错，但标注不一致易误导。）

---

## 原报告漏掉的坑（未记录，但会咬人）

### 漏坑 A ⚠️ 高 —— **章节标题在文字层里排在表格之后**

原报告坑 2 只说「定位行必须先定位所在 section」，但没说 section 标题**跟在表格后面**。
实测 p22 原始阅读顺序：

```
... SGX Bitcoin Perpetual Futures / 132,651 / ...
    Total / 168,880 / 121,746 / 31,046 / 38,624 / 52,076 / 337,175 / 290,626 / 0 / 0%
    Cryptocurrency Derivatives Volume        ← 标题在这里才出现
    (下一张表的表头) ...
    Total / 1,158,349 / ... / 3,895,114 / ...
    SICOM Volume                             ← 又是后置
```

全书扫描确认 p22~p26、p30~p38、p39/p40 都是**标题后置**，而 p20/p21/p27/p29 是标题前置
——**同一份 PDF 里两种顺序混用**。任何「找到标题 → 读下面的行」的 section 解析器，
会把每一个 `Total` 归错一节（商品/加密全线错位），而且是静默错。
考虑到商品档有 6 个都叫 `Total` 的行，这是本家最高概率的实现 bug。

### 漏坑 B ⚠️ 中 —— CMS `title` 不是统一格式，`%B %Y` 会静默丢掉 92 期

原报告说「用 CMS 返回的 `title` 定月份」，示例只给了 `"June 2026"`。实测 197 条里：
- **92 条是缩写月**（`Jun 2018`、`Dec 2015` …，2018-06 及更早全是）
- 另有夹杂空白：`' Jan 2015'`（前导空格）、`'Feb 2017\t'`、`'Aug 2016\t'`、`'Feb 2014\t'`（尾部 tab）、`'Feb  2011'`（双空格）

只写 `strptime(title, "%B %Y")` 会静默丢掉 **92/197 期**，且因为 `count` 仍是 197，
很难发现。必须 `.strip()` + 同时试 `%B %Y` 与 `%b %Y`。

### 漏坑 C —— `(#)` 也会污染**列表头**

原报告只说数值要剥 `(#)`。实测 2013-06 期，`(#)` 同时出现在表头单元格上：`'May 2013(#)'`。
而原报告坑 11 又要求「列定位要按表头行里 `%b %Y` 形状的单元格来认」——
这两条放在一起会互相打架：表头正则不剥 `(#)` 就认不出该列。

### 漏坑 D —— 静默失败**对合法 query 名也会发生**，必须重试

我第一次请求 `we_chat_qr_validator`（名字来自站点自己的 index.js，完全合法）拿到的是
`HTTP 200 + {"errors":[... but got: null]}`，**重试一次就正常返回**。
所以坑 1 说的「显式检查 errors」不够 —— 还得**带退避重试**，否则会把瞬时抖动
当成「官方还没发」而静默跳过一个月。

---

## 「能不能进同一个竞争池」的独立判断

先说结论：**能进，而且是四家里对得最齐的一个**。题面担心的
「只有成交金额、没有合约张数」在 SGX 身上**不成立** —— 它两样都给。

我拉了本仓现有三家的实际量级来对：

| 交易所 | 字段 | 2026-06 实值 | 单位 |
|---|---|---|---|
| CME | `adv_total_kcontracts` | 30,599.986 | 千张/日 |
| Cboe | `adv_us_options_kcontracts` + `adv_futures_kcontracts` | 22,977.3 + 242.0 | 千张/日 |
| HKEX | `derivatives_adv_contracts` | 1,925,817 | 张/日 |
| **SGX** | At-A-Glance DDAV | **1,619,444** | 张/日 |

- **衍生品日均（张/日）四家真的同口径可比**，SGX 1,619k vs HKEX 1,926k 是同一量级，
  与 CME 差约 19 倍、与 Cboe 差约 14 倍 —— 可以同轴，但横截面图上 SGX/HKEX 会被压扁，
  建议同轴 + 表格视图，或按 README 的「离群值截轴不删点」处理。
- 一点纠正：原报告说 `ddav` 是「本仓交易所组唯一一个四家全齐的字段」。
  **Cboe 并没有「衍生品总量」这一列**，得自己把 `adv_us_options_kcontracts + adv_futures_kcontracts`
  加出来（而且 Cboe 99% 是期权、几乎没有期货）。「全齐」是构造出来的，不是现成的。
- **现货池实际只有 SGX ↔ HKEX 两家**：SGX `sdav`（S$ mn/日）vs HKEX `adt_hkdbn`（HK$ bn/日），
  币种 + 量纲都不同，必须指数化；CME 没有现货，Cboe 现货是**股数**
  （`adv_us_equities_matched_shares_bn`）与欧股**名义额**（EUR bn），都不能与 S$ 金额同池。
- **FX 池要小心**：SGX `vol_fx_futures` 是张数，CME `adv_fx_kcontracts` 也是张数 ✅ 可比；
  但 Cboe 的 `adv_fx_adnv_usdbn` 是**名义美元额**，绝不能混进来。原报告已明确指出，属实且重要。
- **市值/IPO 池**：SGX `mktcap`（S$ million 原值）vs HKEX `mktcap_hkdtn`（HK$ **万亿**）——
  差 6 个数量级 + 币种，只能指数化。`ipos_count` ↔ HKEX `new_listings` 可直接比（都是家数）✅。

---

## 给实现阶段的具体警告

1. **不要引入 `curl_cffi`。** SGX 全链路 plain curl 即可，包括 `api.sgx.com/announcements`
   —— 它只是要 `authorizationToken`（ROT13(qrValidator)），不是 JA3 拦截。（错误 1）
2. **section 解析器必须按「标题后置」写**，或干脆放弃 section 定位、改用
   「上一条非 `Total` 的产品行名」来锚定，再用页码兜底。全书有 6 个都叫 `Total`
   的商品行，错位是静默的。（漏坑 A）
3. **月份解析必须 `title.strip()` + 同时试 `%B %Y` / `%b %Y`**，否则静默丢 92 期。
   解析完断言 `len(parsed) == data.list.count`。（漏坑 B）
4. **`source_dates` 只对 2018-08 之后的月份用 `Last-Modified`**；更早的一律留空或标注
   「CMS 迁移戳，非发布日」。绝不要批量回填。（错误 2）
5. **`LAG['sgx']=(13,13)` 必须配 `EARLY_BY['sgx']=(7,7)`**，否则最近 35 个月里有 8 个月
   会晚 1~2 天才抓到。注意仓库里 `EARLY = 5` 不是 3。（错误 3、4）
6. ~~**`turnover_velocity_pct` 的允许为空区间是「< 2018-03」**，不是 2018-01。~~
   **2026-08-19：这一列已经没有「允许为空区间」了** —— 回落 p8 之后它从 `START_MONTH`
   （2015-01）起 139 个月一格不缺，`FIRST_MONTH` 里写的就是 `START_MONTH`。（错误 5 的追记）
7. **单位换算要显式写清楚**：SGX 原始值是**张**（DDAV 1,619,444），存进
   `*_kcontracts` 列必须 `÷1000`。原报告那句「（后者是张/日，除 1000 即可）」只说了 HKEX，
   容易让人以为 SGX 已经是千张 —— 那会造成对 CME `adv_total_kcontracts`（30,600）的 1000 倍错位。
8. **表头正则要先剥 `(#)`**（`'May 2013(#)'`），否则 2013 那几期认不出列。（漏坑 C）
9. **GraphQL 请求要带退避重试**，合法 query 名也会瞬时返回 `200 + errors`。（漏坑 D）
10. **列定位按表头形状认**：p39=7 列、**p40=5 列**、p41=6 列、现代主表=9 列。（错误 7）
11. 原报告未验证的一处：`ipos_count` 我确认可从 p41 列优先块取到
    （Jun 2026 = Mainboard 0 + Catalist 0），但该页**没有 FYTD/CYTD**，
    别指望从这页做年度校验。

---

## 一句话给上游

原 agent 这份 SGX 侦察**没有虚报**，抓取、历史、解析、交叉核对我全部独立复现成功，
判定 B 合理、可以进实现。但有 3 处会直接影响代码的错误必须先改：
**Akamai/JA3 的诊断是错的（白白引入依赖）**、
**`Last-Modified` 对半数历史是迁移戳**、
**`LAG=13` 配 `EARLY=5` 会让 23% 的月份晚 1~2 天**；
外加一个它没写、但踩中概率最高的解析坑：**PDF 里章节标题排在表格后面**。
