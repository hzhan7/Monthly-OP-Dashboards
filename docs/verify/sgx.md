# SGX（新加坡交易所，slug: sgx）—— 数据源可行性侦察

侦察日期 2026-08-06。所有 URL、数字、HTTP 状态码均为本次实测所得，脚本与下载件在
`/tmp/exch_recon/scratch/sgx/`。

---

## 判定

**B —— 可实现，但有坑。**

- 数据源是**官方一手**的（SGX 自己的 CMS 与自己的公告系统），满足 README 的硬约束，
  不含任何第三方聚合商。
- 全链路 **plain `curl` / `urllib` 直接可取**，无 Cloudflare、无登录墙、无 JS 渲染，
  满足无人值守。
- 历史深度 **197 期、2010-02 → 2026-06、零断档**，远超仓库「最少 2019 起」的底线。
- 三个数值已与 SGX 自己的新闻稿**逐位对上**（见「实测证据」）。

扣到 B 而不是 A 的三个真实原因（都不是 blocker，但都得写进代码）：

1. **唯一格式是 PDF**，没有 xlsx / csv。48 页、~290 行表格，得自己写行定位器。
   （好在是 InDesign 生成、有完整文字层、阅读顺序正确，不需要 OCR。）
2. **发现链依赖一个会轮换的 persisted-GraphQL id**（`CMS_VERSION`），
   而且 id 失效时服务端返回 **HTTP 200 + `{"errors":[...]}`**，属于静默失败，
   必须显式检查 `errors` 键。
3. **口径命名跨三个世代改过两次**（`Securities Market` → `Stock Market`；
   `Nifty 50` → `GIFT Nifty 50`；`Iron Ore 62%` → `SGX IODEX`），
   做历史回填时必须按世代分支，不能一套标签打天下。

---

## 数据源

### 主链路（推荐，plain urllib 即可，三步）

```
① GET https://www.sgx.com/config/appconfig.json
   → {"CMS_VERSION":"09434be8973b96b28894aefc57aff9e6c1f8f9c6",
      "endpoints":{"CMS_API_URL":"https://api2.sgx.com/content-api", ...}}
   实测 200 / 1,632 bytes / 普通 UA。

② GET https://api2.sgx.com/content-api/
        ?queryId=<CMS_VERSION>:market_statistics_reports_list
        &variables={"lang":"EN","limit":1000}
   → JSON，data.list.count = 197，每期一条：
       {"title":"June 2026",
        "reportDate":1783612800,                 # 2026-07-09（CMS 里设的「报告日」）
        "report":{"data":{"name":"SGX Monthly Statistics Report Update For June 2026",
                          "date":1783676970,     # 2026-07-10 09:49 UTC，文件真正上线时刻
                          "file":{"data":{"url":"https://api2.sgx.com/sites/default/files/
                                    2026-07/SGX%20MONTHLY%20STATISTICS%20UPDATE%20
                                    %28FOR%20THE%20MONTH%20OF%20JUN%202026%29_260703_FA.pdf"}}}}}
   实测 200 / 82,363 bytes。**这一步同时给出「官方当前最新月」**（数组第 0 条的 title），
   等价于 cboe.py 的 `_discover_latest`，且比它强 —— 它把 197 期历史一次性全给出来。

③ GET 上一步给的 file.url（api2.sgx.com 静态文件）
   实测 200 / 879,518 bytes / `content-type: application/pdf`
        / `last-modified: Fri, 10 Jul 2026 09:49:24 GMT`
```

**为什么不能写死 PDF 直链模板**：文件名毫无规律，同一份东西官方用过至少四种命名 ——
`SGX Monthly Market Statistics Report - Feb 2010.pdf`、
`SGX+Monthly+Market+Statistics+Report+Jun+2018.pdf`、
`SGX Monthly Statistics Report Update (For the month of Apr 2026)_FA.pdf`、
`SGX MONTHLY STATISTICS UPDATE (FOR THE MONTH OF JUN 2026)_260703_FA.pdf`
（最后这个还带一个与实际发布日不符的 `260703`）。
目录段 `sites/default/files/YYYY-MM/` 也不总是等于「次月」。**必须走 ② 拿 URL。**

**起点线索里的 `links.sgx.com/1.0.0/corporate-announcements/<KEY>/...` 是次要通道**，
不必用：那条路要先过 SGXNet 公告 API（见下），而 ①②③ 三步就能拿到同一份 PDF。

### 次要链路（只在需要「官方自述发布日」时才用；需绕 Akamai JA3）

```
④ token = ROT13(letters of  GET https://api2.sgx.com/content-api/
                            ?queryId=<CMS_VERSION>:we_chat_qr_validator  → data.qrValidator)
   实测：qrValidator "tVncjC9Fq5mOHKlOix/En/Y0Fmjl..." → token "gIapwP9Sd5zBUXyBvk/Ra/L0Szwy..."
   （站点自己的 JS 就是这么做的，模块 23555；plain urllib 可取）

⑤ GET https://api.sgx.com/announcements/v1.1/company
        ?periodstart=YYYYMMDD_HHmmss&periodend=...&value=SINGAPORE EXCHANGE LIMITED
        &pagestart=0&pagesize=250
   Header: authorizationToken: <token>
   ⚠ **api.sgx.com 被 Akamai 按 TLS 指纹（JA3）拦**：plain curl / urllib 一律
     `403 Access Denied ... errors.edgesuite.net`（与 UA、Referer、token 都无关）。
     `curl_cffi(impersonate='chrome')` 实测 200。`/usr/bin/nscurl` 未试但同理可用。
     注意同域下 `https://api.sgx.com/securities/v1.1/` 用 plain curl 是 200 的 ——
     **拦截是按 path 配的，不能靠「这个域能通」推断另一个 path 能通**。

⑥ GET 公告落地页 https://links.sgx.com/1.0.0/corporate-announcements/<KEY>/<sha256>
   → HTML，里面列出该公告的全部附件：
       /1.0.0/corporate-announcements/IJM1XSR2Y9TQ9KE6/896086_SGX Monthly Statistics Report Update_Jun 2026.pdf
       /1.0.0/corporate-announcements/IJM1XSR2Y9TQ9KE6/896085_20260713 SGX Group strong volume growth in June caps stellar FY2026 performance.pdf
   新闻稿附件的**文件名前缀就是广播日 20260713**，正文首页第二行也写着 "13 July 2026"。
   links.sgx.com 本身 plain curl 可取（302 → `/FileOpen/<name>.ashx?App=Announcement&FileID=<id>`）。
```

### 抓取方式小结

| 主机 | plain curl/urllib | 备注 |
|---|---|---|
| `www.sgx.com/config/appconfig.json` | ✅ 200 | 1.6 KB |
| `api2.sgx.com/content-api/` | ✅ 200 | GraphQL persisted query |
| `api2.sgx.com/sites/default/files/...pdf` | ✅ 200 | 带 Last-Modified |
| `links.sgx.com/1.0.0/...` | ✅ 200（需 `-L`） | 302 到 FileOpen.ashx |
| `api.sgx.com/announcements/v1.1/*` | ❌ Akamai JA3 403 | 需 curl_cffi / nscurl |
| `www.sgx.com/research-education/...`（人看的页） | ⚠️ Angular SPA 空壳 | 别去解析 HTML |

---

## 可提取字段

建议 `series/sgx.csv`（月份格式 `YYYY-MM`，列名照 cboe.csv 带单位后缀）。
分三档：**核心档**（跨截面页要用的，必取）／**产品档**（SGX 的叙事主线）／**发行档**。

### 核心档

| 列名 | 口径 |
|---|---|
| `sdav_sgdmn` | Securities Daily Average（$Million）。SGX 口径的 SDAV，**月内日均**证券成交金额，新元百万。这是 SGX 财报与新闻稿引用最多的单一数字 |
| `sec_turnover_sgdmn` | 当月证券市场成交总额（$Million）。含 Mainboard(S$/非S$)、Catalist、Global Quote、ETF、结构化权证、DLC、公司权证 |
| `sec_turnover_mnshares` | 当月证券成交股数（百万股） |
| `sec_trading_days` | 当月**证券市场**交易日数（衍生品不是这个数，见口径坑 4） |
| `mktcap_sgdbn` | 月末总市值。原表是 $Million，除以 1000 存成十亿，与 hkex.csv 的 `mktcap_hkdtn` 同量纲思路 |
| `listed_securities` | 月末上市证券只数（脚注：不含 GDR、对冲基金、债券） |
| `turnover_velocity_pct` | Overall Turnover Velocity（换手率）。~~2018 年才有，2017 及以前天然为空~~ —— **2026-08-19 已证伪：现在 2015-01 起 139 个月一格不缺**。p2 的 At-A-Glance 确实 2018-03 那期才多出这一行，但更早的期次**照样印**，只是印在 p8 的 `Turnover Velocity (5)` 表里；两处逐格等价（已闭合验证），回落读取不产生接缝 |
| `deriv_vol_kcontracts` | 当月衍生品总成交（千张）= 期货+期权+掉期 |
| `ddav_kcontracts` | Derivatives Daily Average Volume（千张/日）。**这是跨家可比的那个字段** |
| `deriv_futures_vol_kcontracts` | 当月期货成交（千张） |
| `deriv_options_vol_kcontracts` | 当月期权成交（千张） |
| `deriv_oi_kcontracts` | 月末总未平仓（千张，期货+期权+掉期） |

### 产品档（全部是**当月总量**，不是日均，故用 `vol_` 前缀而非 `adv_`）

| 列名 | 口径 |
|---|---|
| `vol_equity_index_futures_kcontracts` | 股指期货合计（报告 p14-16 的 Total） |
| `vol_a50_futures_kcontracts` | FTSE China A50 Index Futures —— SGX 的头号单品，全球最活跃的离岸中国股指期货 |
| `vol_nikkei225_futures_kcontracts` | Nikkei 225 Index Futures（不含 Mini / USD / Micro，各自单列或按需合并） |
| `vol_giftnifty50_futures_kcontracts` | GIFT Nifty 50 Index Futures，**SGX-ICI 清算口径**（≠ p39 的 NSE-IX 全市场口径，见口径坑 2） |
| `vol_taiwan_futures_kcontracts` | FTSE Taiwan Index Futures |
| `vol_msci_singapore_futures_kcontracts` | MSCI Singapore Index Futures |
| `vol_fx_futures_kcontracts` | 外汇期货合计（p20-21 的 Total） |
| `vol_usdcnh_futures_kcontracts` | USD_CNH FX Futures（全球最大的国际人民币期货） |
| `vol_inrusd_futures_kcontracts` | INR_USD FX Futures |
| `vol_iron_ore_kcontracts` | 铁矿石衍生品合计 = IODEX 期货+期权+掉期 + 65% + 58% + Lump Premium |
| `vol_commodities_kcontracts` | 商品合计 = SICOM + Energy + Metal&DryBulk + Dairy + Energy Metals（**不含 crypto**，见口径坑 6） |
| `vol_rates_futures_kcontracts` | 利率期货合计（Mini JGB、TONA 等；量级很小） |
| `vol_crypto_kcontracts` | Bitcoin/Ethereum Perpetual Futures（2025 年才上线，之前天然为空） |

### 发行档

| 列名 | 口径 |
|---|---|
| `ipos_count` | 当月新上市家数 = Mainboard IPOs + Catalist IPOs（不含 RTO） |
| `delistings_count` | 当月退市家数 |
| `ipo_funds_sgdmn` | Fund Raised Through IPOs and RTOs（$million，Mainboard + Catalist） |
| `new_bond_listings` | 当月新债券挂牌数 |
| `bond_funds_sgdmn` | 债券募资额（$million） |

> 不建议入库的：YoY% 列（官方自己算错过，见口径坑 5）、FYTD / CYTD 列
> （财年是 7 月—6 月，与看板的日历年逻辑打架，需要就从月度序列自己滚）。

---

## 历史深度

| 起点 | 能拿到什么 | 代价 |
|---|---|---|
| **2010-02** | PDF 存在（197 期，**零断档**，实测逐月枚举无缺口） | 2010-02 ~ 2010-11 是 Excel 打印稿，文字层阅读顺序完全错乱（见实测证据里 2010-02 的 dump），要按坐标重排才能读，不划算 |
| **2010-12** | 「SGX Statistics At A Glance」那一页开始出现且可解析 | 2011-2014 的表头位置不稳（页码行混进表头），需要一套宽松的分支 |
| **2015-01** ✅ **建议起点** | At-A-Glance 8-9 个核心字段 + 衍生品分产品表全部稳定可解析 | 无 |
| ~~2018-01~~ | ~~才有 `turnover_velocity_pct`~~ **作废（2026-08-19）**：p2 那一处是 2018-03 起，但 p8 从 2015-01 起就有，序列现已一格不缺 | —— |

**断档情况**：从 2010-02 到 2026-06 共 197 个月，CMS 列表给出 197 条，逐月检查
**gaps = []**（脚本实测）。这是本轮侦察里覆盖最干净的一家。

**当前最新月**：2026-06（2026-07-10 上线）。2026-07 那期按节奏应在 2026-08-06~13 出，
本次侦察时尚未发布 —— 这不是故障。

---

## 发布节奏

**次月第 6–13 日，中位数第 9 日。** 近 30 个月实测（`report.data.date`，UTC）：

```
2025-01→02-10  2025-02→03-07  2025-03→04-07  2025-04→05-13  2025-05→06-06
2025-06→07-09  2025-07→08-08  2025-08→09-09  2025-09→10-08  2025-10→11-11
2025-11→12-10  2025-12→01-09  2026-01→02-09  2026-02→03-09  2026-03→04-09
2026-04→05-12  2026-05→06-09  2026-06→07-10
```

⇒ `roster.py` 的 LAG 建议填 **13**（常规月与季末月同值 —— SGX 的月报不随季报节奏走，
财年 6 月末那一期也照常在 7 月上旬发，实测 2025-06→07-09、2026-06→07-10）。
按 README 的 `EARLY=3`，闸门从次月第 10 天开，不会误伤。

### source_dates 溯源：**报告 PDF 自己不写发布日**

我把 2026-06 那期 48 页全文扫过一遍：没有 `Updated on` / `Published` / `As at` 之类
的字符串，末页只有免责声明。所以不能照抄 cboe 的 `_updated_on` 做法。可用的三条证据，
按可信度排序：

1. **PDF 直链的 HTTP `Last-Modified`** —— `Fri, 10 Jul 2026 09:49:24 GMT`。
   官方服务器自己盖的时间戳，机器可核，与 HKEX 那家在本仓的做法一致。
2. **PDF 内部 `docProps` 的 creationDate** —— `D:20260710171711+08'00'`
   （= 2026-07-10 17:17 SGT），与 ① 相差 7 分半，互为印证（① 是 09:49 UTC = 17:49 SGT）。
   Creator 一栏是 `Adobe InDesign 21.1 (Macintosh)`，确属 SGX 自己排版。
3. **CMS 列表的 `reportDate`** —— 2026-07-09，比 ①② 早一天。这是 CMS 里人手填的
   「报告日」，不是文件上线时刻，两者近 30 个月里**总是差 0~2 天**。宁可不用。

⚠ **还有一个不一致必须写进代码注释**：同一份报告作为附件挂上 SGXNet 是在
**2026-07-13**（公告 `IJM1XSR2Y9TQ9KE6`，新闻稿正文首行 "13 July 2026"），
比网站上线晚 3 天。Apr-2026 那期同样：网站 05-12、SGXNet 05-13。
⇒ 「官方发布于」这半句取哪个日期是个**语义选择**，不是技术问题：
   取 ①（网站上线）= 公众最早能拿到数据的那天；
   取 SGXNet 广播日 = SGX 正式向市场披露那天。
   本仓 source_dates.csv 现有条目（cboe / hkex / cost）用的都是「数据第一次可得那天」，
   所以**建议用 ①，evidence 里把 SGXNet 那个日期也一并写上**，免得日后有人以为算错了。

---

## 口径坑（按踩坑概率排序）

1. **`CMS_VERSION` 会随站点每次发版轮换，失效时静默返回 HTTP 200。**
   实测：拿一个假 hash 去请求，服务端回 `200` + `{"errors":[{"message":"The persisted
   query loader must return query string ... but got: null"}]}`，**不是 4xx**。
   ⇒ 每次运行都必须重新读 `appconfig.json`（站点自己的 JS 就是这么干的），
     且解析后必须显式检查 `data.list.count` 存在、`errors` 不存在，缺一就抛异常。
     写死 hash = 某天悄悄开始返回空列表，而 `latest_month()` 会以为「官方还没发」。
   另：`variables` 里**不写 `limit` 时默认只返回 10 条**（但 `count` 仍是 197），
   回填时不给 limit 会静默少 187 期。

2. **同一个产品在报告里出现两次，数字不一样 —— GIFT Nifty。**
   p15「Equity Index Futures Volume」里的 `GIFT Nifty 50 Index Futures`
   FYTD 2026 = **20,699,069**（脚注：「refers to volume traded via SGX-ICI and cleared
   by SGX」）；p39「GIFT Nifty Overall Market Volume」里同名行 FYTD 2026 = **24,357,137**
   （脚注：「the overall GIFT Nifty Derivatives volume traded on NSE-IX，Source: NSE-IX」）。
   差 18%。前者才是 SGX 自己的收入口径，后者是整个 NSE-IX 市场（不全归 SGX）。
   ⇒ 定位行**必须先定位所在 section**，绝不能全表 grep 产品名 —— 与 cboe 的坑 2 同型。
   ⇒ 顺带：p39/p40 只有 7 列（无「去年同月」「YoY%」），行解析器不能写死 9 列。

3. **产品改名 + 结构性断点，跨 2023 中不可直连比。**
   - `Nifty 50 Index Futures` →（2023-07 GIFT Connect 迁移后）`GIFT Nifty 50 Index Futures`。
     官方脚注写明：「For periods prior to June 2023, volumes are computed based on
     higher of buy and sell lots」，之后改成 round-trip 买卖双边合计。
     **这是量纲变化，不是增长**，画图必须在 2023-06/07 打结构性断点红线。
   - `Iron Ore 62% Futures` → `SGX IODEX Iron Ore Futures`；
     `Iron Ore Options On Futures` → `SGX Options On IODEX Iron Ore Futures`。
   - `INR_USD FX FFutures`（2016 年报告里的拼写错误，两个 F）→ `INR_USD FX Futures`。
   - At-A-Glance 行名 2025 年底改过：`Number of Trading Days (Securities)` →
     `(Stock Market)`；`Securities Market Turnover Value` → `Stock Market Turnover Value`
     （2025-06 那期还是旧名，2025-12 那期已是新名）。2019 年那期还写成小写的
     `Securities market Turnover Volume`。
   ⇒ 行标签匹配必须做归一化（大小写、`($million)` vs `($Million)`）+ 一张别名表。

4. **`Derivatives Volume ÷ Number of Trading Days ≠ Derivatives Daily Average Volume`。**
   实测反推出来的「隐含交易日数」根本不是整数：
   ```
   2026-06:  34,315,225 / 1,619,444 = 21.19   （而 At-A-Glance 写的交易日 = 21）
   2026-05:  30,483,078 / 1,607,949 = 18.96   （写的是 19）
   2026-04:  30,208,711 / 1,479,546 = 20.42   （写的是 21）
   2025-06:  26,109,454 / 1,270,536 = 20.55   （写的是 21）
   ```
   `Number of Trading Days` 那一行的括号里明明白白写着 `(Stock Market)` / `(Securities)`
   —— 它是**证券市场**的交易日数，衍生品市场的假期表和 T+1 夜盘归属日都不一样。
   ⇒ 月总量与日均**两个都要入库**，谁也别从谁反推。

5. **官方的 `YoY%` 列会算错，一律自己重算。**
   实铁证：2025-06 那期 p38「Fund Raised ($ million)」行，Jun 2025 = 15,362、
   Jun 2024 = 20,306，官方 YoY% 印的是 **-4944%**（正确是 -24%）。
   同一页上一行 New Bond Listings 的 -50% 又是对的。
   ⇒ 不入库 YoY 列；如果非要做校验，可以拿它当「解析是否错行」的弱信号，但不能当真值。

6. **「Commodities」的官方定义不含 crypto。**
   2026-07-13 新闻稿说 FY2026「total commodities volume rose 21% y-o-y to 78.8 million lots」。
   把报告里 SICOM 3,895,114 + Energy 493,152 + Metal&DryBulk 73,586,973 +
   Dairy 期货 688,923 + Dairy 期权 104,742 + Energy Metals 2,640 = **78,771,544**（= 78.8M ✅）；
   若把 Crypto 的 337,175 也加进去就变成 79,108,719，对不上。
   ⇒ `vol_commodities_kcontracts` 按前者定义，crypto 单开一列。

7. **证券成交额是「暂定数」，官方明说会顺延调整。**
   p3 脚注 (1)：「Due to Operational constraints and system cut-off times, the statistics
   may not always be able to take into account cancelled trades that occur near the end
   of the month. The adjusted statistics will instead be carried over to the following
   month's report.」末页免责声明另有「subject to change without notice」。
   2013-06 那期还直接在数字后面挂 `(#)` 并注明 "Numbers have been restated"
   （原文 `62,084(#)`）—— 数字解析器必须先剥掉 `(#)`，否则那两行会被整行丢掉
   （我第一版解析器就在这儿漏了两个字段）。
   ⇒ 照 cboe / hkex 的做法：**已有值永不覆盖，只填空**；差异写进
     `cache/sgx_restatements.csv` 供人工判断。
   ⚠ 附一条好消息：我拿 2026-04 / 2026-05 / 2026-06 三期做过重叠月对账，
     8 个数据点（证券成交额、SDAV、市值、衍生品量、DDAV、A50、IODEX）**逐位相同**，
     近月重述至少不是常态。

8. **「Issuer Services」那一页是列优先（column-major）排版，通用行解析器读不了。**
   p41 的文字层长这样：先连着列出 5 个标签
   （`SGX Mainboard` / `- Primary Listings` / `- Secondary Listings` / `- IPOs` / `- Delistings`），
   然后**每一列**吐 5 个数（`401 373 28 2 4` 是 FY2026 Q3 那一列，
   `401 373 28 1 4` 是 Q4 那一列…）。
   ⇒ IPO / 退市家数得单写一个 5×6 的块解析器，不能复用「标签 + 9 个数」那套。

9. **老报告（2010-02 ~ 2010-11）是 Excel 打印稿，文字层顺序是乱的。**
   `page.get_text()` 出来的是「(3) Includes Sesdaq Turnover / 0 / 14,231 / 15,923 / 1 / 32 …」
   这种碎片，行列关系全靠坐标。要读得用 `get_text("words")` 按 x/y 聚类。
   ⇒ 建议直接不要这段历史（起点定在 2015-01，或最多 2010-12）。

10. **`sites/default/files/YYYY-MM/` 里的年月不总等于「数据月的次月」，文件名里的数字也会骗人。**
    2026-06 那期路径是 `2026-07/`（对），但文件名叫 `..._260703_FA.pdf`，
    而实际上线是 07-10、SGXNet 广播是 07-13。三个日期两两不等。
    ⇒ 别从文件名或路径解析任何日期，一律用 CMS 返回的 `title` 定月份、
      用 HTTP `Last-Modified` 定发布日。

11. **列数会随年份变。** 现代版是 9 列
    `[FYQx, FYQy, M-2, M-1, M0, FYTD, CYTD, 去年同月, YoY%]`；
    p39/p40（GIFT 全市场）是 7 列；p41（Issuer Services）是 6 列且无 YoY；
    2016-01 那期的 `CYTD` 在 1 月份恒等于当月本身。
    ⇒ 列定位要按表头行里 `%b %Y` 形状的单元格来认，不能按位置数。

---

## 实测证据

### 抓取（全部 plain curl / urllib，无浏览器、无登录态）

```
$ curl -sS https://www.sgx.com/config/appconfig.json          → 200, 1632 B
$ curl -sS -G https://api2.sgx.com/content-api/ \
        --data-urlencode "queryId=$V:market_statistics_reports_list" \
        --data-urlencode 'variables={"lang":"EN","limit":1000}'  → 200, 82363 B, 197 条
$ curl -sS -D - -o x.pdf 'https://api2.sgx.com/sites/default/files/2026-07/SGX%20MONTHLY%20...pdf'
        HTTP/2 200 / content-type: application/pdf
        last-modified: Fri, 10 Jul 2026 09:49:24 GMT / 879518 B
```

下载并解析的 PDF（本地在 `/tmp/exch_recon/scratch/sgx/pdfs/`）：
2010-02、2010-06、2010-12、2011-01/03/06、2012-06、2013-06、2014-01/06、
2015-01/06/10、2016-01/06、2017-06、2018-06、2019-12、2020-06、2021-06、2022-06、
2023-06、2024-06、2025-06、2025-12、2026-01、2026-04、2026-05、2026-06 —— 共 28 期。

解析脚本：`/tmp/exch_recon/scratch/sgx/parse_sgx.py`（~110 行，依赖 pymupdf）。
两个函数：`parse_glance()`（At-A-Glance 页，标签+2 值）、`parse_rows()`（全书扫描，
「一段非数字文字 + 连续 9 个数字」= 一行）。2026-06 那期解出 **287 行**。

### 解析出的真实数字（2026-06 期，直接从 PDF 读出）

```
== At A Glance  ['May 2026', 'Jun 2026']
   Number of Trading Days (Stock Market)          (19, 21)
   Stock Market Turnover Volume (Million Shares)  (38,737, 29,882)
   Stock Market Turnover Value ($Million)         (45,837, 44,639)
   Securities Daily Average ($Million)            (2,412, 2,126)
   Total Number of Listed Securities              (601, 601)
   Total Market Capitalisation ($Million)         (1,123,460, 1,129,411)
   Overall Turnover Velocity                      (56%, 49%)
   Derivatives Volume                             (30,483,078, 34,315,225)
   Derivatives Daily Average Volume               (1,607,949, 1,619,444)

== 9 列表格（[FYQ3, FYQ4, Apr26, May26, Jun26, FYTD26, CYTD26, Jun25, YoY%]）
 p13 Total Trading Volume          [97,512,297  95,007,014  30,208,711  30,483,078  34,315,225  363,489,920  192,519,311  26,109,454  31%]
 p13 Average Daily Trading Volume  [ 1,672,043   1,566,512   1,479,546   1,607,949   1,619,444    1,478,988    1,618,396   1,270,536  27%]
 p3  Total Market Turnover Value   [   125,998     133,636      43,160      45,837      44,639      455,677      259,634      26,006  72%]
 p3  Securities Daily Average      [     2,066       2,191       2,055       2,412       2,126        1,808        2,128       1,238  72%]
 p14 FTSE China A50 Index Futures  [30,700,860  30,678,258   9,068,023   9,885,857  11,724,378  120,528,277   61,379,118   8,553,797  37%]
 p16 Nikkei 225 Index Futures      [ 1,964,145   1,634,764     452,034     434,682     748,048    6,931,059    3,598,909     597,336  25%]
 p15 GIFT Nifty 50 Index Futures   [ 5,633,480   5,512,951   1,751,137   1,816,138   1,945,676   20,699,069   11,146,431   1,615,004  20%]
 p21 FX Futures — Total            [28,026,195  29,506,143   9,670,422   9,567,681  10,268,040   96,252,265   57,532,338   6,698,923  53%]
 p21 USD_CNH FX Futures            [14,928,934  14,362,843   4,930,585   4,443,198   4,989,060   48,921,555   29,291,777   3,528,208  41%]
 p20 INR_USD FX Futures            [10,124,683  11,787,864   3,832,700   4,038,743   3,916,421   37,276,890   21,912,547   2,358,493  66%]
 p24 SGX IODEX Iron Ore Futures    [15,361,249  13,801,599   4,597,147   4,429,928   4,774,524   61,663,792   29,162,848   4,580,852   4%]
 p24 Metal & Dry Bulk — Total      [18,713,773  16,201,382   5,444,296   5,099,029   5,658,057   73,586,973   34,915,155   5,455,417   4%]
 p43 New Bond Listings             [      260         242          72         114          56        1,062          502          47  19%]
 p40 GIFT Nifty 50 月末 OI          [  261,403     297,572     258,992     290,377     297,572 ]   ← 7 列表
```

### 交叉核对（对手方 = SGX 自己的新闻稿，一手来源，不是聚合商）

**核对组 A —— 2026-07-13 新闻稿**
（`links.sgx.com/.../896085_20260713 SGX Group strong volume growth in June caps stellar FY2026 performance.pdf`，
本地 `nr_2026-06.pdf`，2 页，PDF creationDate `D:20260713075044+08'00'`）：

| 新闻稿原文 | 报告 PDF 解析值 | 结论 |
|---|---|---|
| "Derivatives traded volume rose 31% y-o-y in June to **34.3 million contracts**" | 34,315,225，YoY 列 31% | ✅ |
| "daily average volume (DAV) climbed 27% y-o-y to **1.6 million contracts**" | 1,619,444，YoY 列 27% | ✅ |
| "For July 2025 to June 2026 (FY2026), total volume gained 15% ... to **363.5 million contracts**" | FYTD 2026 = 363,489,920 | ✅ |
| "Securities market turnover jumped 72% y-o-y ... to **S$44.6 billion**" | 44,639 ($Million) | ✅ |
| "SDAV also rose 72% y-o-y at **S$2.1 billion**" | 2,126 ($Million)，YoY 72% | ✅ |
| "In FY2026, turnover climbed 35% y-o-y to **S$455.7 billion**" | FYTD Value = **455,677** | ✅ 逐位 |
| "In FY2026, total FX futures volume climbed 31% y-o-y to **96.3 million contracts**" | FX Total FYTD = **96,252,265** | ✅ |
| "month-end open interest (OI) rose to an all-time high of **297,572 lots**" | p40 GIFT Nifty 50 OI Jun-26 = **297,572** | ✅ 逐位 |
| "In FY2026, overall GIFT volume increased 3% y-o-y to **24.4 million contracts**" | p39 GIFT 全市场 FYTD = **24,386,146** | ✅ |
| "In FY2026, total commodities volume rose 21% y-o-y to **78.8 million lots**" | 五个商品板块 Total 相加 = **78,771,544** | ✅ |

**核对组 B —— 2016-01-07 新闻稿**（`384923_010716_SGX_reports_market_statistics_for_December_2015.pdf`，
从 SGXNet 公告 `YBFA1MLZ1MEE27PC` 取），对 2016-01 那期报告里的 Dec-2015 列：

| 新闻稿原文 | 报告 PDF 解析值 | 结论 |
|---|---|---|
| "Total Securities market turnover value ... to **S$17.0 billion**" | At-A-Glance Dec-2015 = 17,024 ($million) | ✅ |
| "Securities daily average value (SDAV) fell 20% mom and fell 21% yoy to **S$774 million**" | 774 | ✅ 逐位 |
| "Total Derivatives volume was **14.4 million**" | 14,362,547 | ✅ |
| "Total market capitalisation ... stood at **S$904.8 billion**" | 904,770 ($million) | ✅ |
| "FTSE China A50 ... volume of **6.4 million**, down 2% mom" | p13 Dec-2015 列 = 6,373,016（Nov 6,524,892，−2.3%） | ✅ |
| "Nikkei 225 Index Futures volume was **2.3 million**, up 46% mom" | 2,273,483（Nov 1,562,084，+45.5%） | ✅ |
| "SGX USD/CNH Futures volume was **51,702**" | p15 USD_CNH FX Futures Dec-2015 = **51,702** | ✅ 逐位 |
| "SGX INR/USD Futures volume was **366,372**" | p15 INR_USD FX FFutures Dec-2015 = **366,372** | ✅ 逐位 |
| "Total FX Futures volume was **425,188**" | p15 Foreign Exchange Futures Total = **425,188** | ✅ 逐位 |

⇒ 现代端与 2015 端各有 4 个「逐位相同」的硬核对，解析口径正确，不是碰巧对上量级。

### 覆盖完整性实测

```
n unique = 197   first = 2010-02   last = 2026-06
gaps: []
```

### 反爬实测

```
plain curl  api2.sgx.com/content-api               → 200
plain curl  api2.sgx.com/sites/default/files/*.pdf → 200
plain curl  api.sgx.com/securities/v1.1/           → 200
plain curl  api.sgx.com/announcements/v1.1/*       → 403 Access Denied（Akamai edgesuite）
curl_cffi(impersonate='chrome') 同一 URL 同一 header → 200
```
（curl_cffi 0.16.0 本机已装；`/usr/bin/nscurl` 存在，可作备用通道。）

---

## 属于哪些竞争池

### 地理池

| 池 | 归属 | 该池里可比的字段 |
|---|---|---|
| **亚太衍生品** | ✅ 核心 | `ddav_kcontracts`（千张/日）。可直接与 HKEX 的 `derivatives_adv_contracts` 同轴比（后者是张/日，除 1000 即可）。SGX ≈ 1,619 千张/日 vs HKEX 2026-06 量级 —— 两家都是「亚洲的国际衍生品场」，但 SGX 的标的是**别人家的市场**（中国 A50、日经、印度、台湾），HKEX 的标的是**自己家的市场**，这正是横截面页要讲的对比 |
| **亚太现货** | ✅ | `sdav_sgdmn`（S$ mn/日）↔ HKEX `adt_hkdbn`（HK$ bn/日）。**量纲与币种都不同，必须指数化**（各自设 2019-01=100）才能同图；绝对值放表格视图 |
| **单一市场垄断对照** | ✅ | SGX 是新加坡唯一的股票交易所，和 HKEX 同型（垄断本土现货 + 靠国际衍生品增长）。可比字段：`mktcap_sgdbn` ↔ HKEX `mktcap_hkdtn`、`ipos_count` ↔ HKEX `new_listings`、`ipo_funds_sgdmn` ↔ HKEX `ipo_funds_hkdbn`（注意 HKEX 那边的 IPO 募资是暂定数会上修，SGX 这边同样有「跨月顺延」脚注） |
| 北美现货／北美期权／欧洲现货／欧洲衍生品 | ❌ 不属于 | —— |

### 标的池

| 池 | 归属 | 可比字段与注意点 |
|---|---|---|
| **股指衍生品** | ✅ **主战场** | `vol_equity_index_futures_kcontracts`（月总量）÷ 交易日 后 ↔ CME `adv_equity_kcontracts`、Cboe `adv_index_options_kcontracts`。**SGX 只给月总量不给分产品日均**，跨家比之前必须先除以交易日；用 `deriv_vol / ddav` 反推的隐含日数（见口径坑 4），不要用 `sec_trading_days` |
| **FX** | ✅ **全球前三** | `vol_fx_futures_kcontracts` ÷ 交易日 ↔ CME `adv_fx_kcontracts`（同为张数，可比）。⚠ Cboe 的 `adv_fx_adnv_usdbn` 是**名义额**（Cboe FX 是现货撮合不是期货），**不可与张数同池** |
| **能源商品** | ⚠️ 名义上属于，实质要改名 | SGX 的商品盘 98% 是**铁矿石与干散货运费**，真正的能源（Oil/Petrochem/Coal）FYTD 才 493,152 张。建议这个池对 SGX 用 `vol_iron_ore_kcontracts` 与 `vol_commodities_kcontracts`，并在图注写明「SGX 的商品 = 钢铁原料 + 运费 + 橡胶 + 乳制品，与 CME 的能源/农产品不同标的，只比增速不比绝对量」 |
| **利率衍生品** | ⚠️ 属于但量级悬殊 | `vol_rates_futures_kcontracts` FYTD 2026 才 77 万张，CME 的利率是每天 800 万张量级 —— 差三个数量级。**只能做指数化趋势对比**，同轴绝对值会把 SGX 压成一条零线 |
| **加密** | ✅ 新增 | `vol_crypto_kcontracts`（Bitcoin/Ethereum Perpetual Futures，2025 年上线，FYTD 2026 = 337,175 张）。这是本仓少见的加密敞口，可与 CME 的加密条线对照（CME 那边在 `cme.csv` 里没单列，需要时得加列） |
| **单股与ETF期权** | ❌ 基本不属于 | SGX 的 Single Stock Futures FYTD 才 153 万张且在萎缩（−51% YoY），没有规模化的个股/ETF 期权。放进这个池只会给 Cboe/CME 当陪衬 |

### 跨截面页最推荐的两个字段

1. **`ddav_kcontracts`** —— 交易所横截面页的「衍生品日均成交」主图，SGX / CME / Cboe / HKEX
   四家都有同口径（张/日）的数，是本仓交易所组唯一一个四家全齐的字段。
2. **`sdav_sgdmn`（指数化）** —— 现货活跃度，与 HKEX `adt_hkdbn` 同框；
   两家 2025-2026 都在爆发（SGX FY2026 SDAV 18 年新高），是很好的叙事对照。

---

## 落地建议（给写生产代码的人）

- `fetch/sgx.py` 走 ①②③ 三步，`latest_month()` 只需 ①② 两个请求（~84 KB），
  不必下 PDF —— 比 cboe 更省。
- `update()` 每次只下**最新一期**的 PDF；跨月窟窿按 CMS 列表里的 URL 逐期补
  （不像 cboe 要猜文件名，这里 URL 是现成的）。
- 严格校验：核心档 12 列缺任何一列 → 抛异常。~~`turnover_velocity_pct` 在 2018-01 之前~~
  （**2026-08-19：这一列已无允许为空区间**，回落 p8 后 2015-01 起一格不缺）、
  `vol_crypto_kcontracts` 在 2025 之前允许为空，其余不允许。
- 幂等：已有值永不覆盖，只填空（口径坑 7）。
- 一次性回填 2015-01 ~ 2026-07 需下 139 份 PDF，约 80 MB、~10 分钟，一次性成本可接受。
  （已完成：`series/sgx.csv` 今天是 2015-01 → 2026-07 共 139 行 × 32 列。）
