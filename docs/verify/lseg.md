# LSEG（London Stock Exchange Group，LSE: LSEG）—— 四路月度数据源核查

核查日期 **2026-08-07** · slug `lseg` · 抓取代码 `fetch/lseg.py` + 四个 part 模块
`fetch/lseg_{orderbook,primary,tradeweb,lch}.py` · 页面配置 `build/specs/lseg.py` ·
真值 `series/lseg.csv`（115 行 × 86 个数据列）与四张 part CSV。

本文的数字分两类，逐处标了出处等级：

- **[A] 本机今日实测**：`series/*.csv` 的现值、`cache/lseg_primary_conflicts.csv` 的内容、
  以及本文「口径边界」一节里那份 LSEG 官方 RNS —— 都是写这份文档时当场读的。
- **[A·转抄]**：各 part 模块 docstring 里记录的实测统计（发布节奏分布、重述率、
  两源交叉核对残差）。那些统计是抓取模块作者当时逐期跑出来的，本文**原样转抄、不重算**，
  复算入口写在各节里。

没有 [C] 推算，也没有任何一个数来自训练知识或第三方转述。

---

## 判定

**B —— 可实现、已实现，但它是本仓结构最复杂的一家，且注定「每个月分几次写全」。**

一句话：LSEG 的月度经营数据**不存在一份总表**，它散在四个互不相干的官方发布物里 ——
四个网站、四种格式、四种发布节奏、历史深度从 24 个月到 115 个月不等。所以抓取拆成
四个独立 part 模块，各自落一张 part CSV，再由 `fetch/lseg.py` 按 month **外连接**成宽表。

四路全部满足无人值守：`urllib.request` 裸奔即可，无 Cloudflare 挑战（Tradeweb 那一路是个
反直觉的例外，见下）、无 JS 渲染依赖、无登录墙、无验证码、无 JA3 指纹拦截。

**最需要提前知道的两件事：**

1. **月度数据只覆盖 LSEG 四个分部里的 `Markets` 一个**，指数业务（FTSE Russell）
   一个月度字段都没有 —— 见下一节，这是本页最容易被误读的边界。
2. **LSE 订单簿那条腿比其余三路晚一个月**：今天（2026-08-07）宽表最新行是 2026-07，
   但那一行的 17 个订单簿列是空的，订单簿最新只到 2026-06。空格是事实，不是抓漏。

---

## 口径边界（最重要）：**月度数据不含 FTSE Russell**

**LSEG 是四分部结构，本页的四条腿全部落在其中一个分部（Markets）里。**
官方原文（`lseg.com/en/investor-relations`，等级 [A]）：

> "our four business divisions – Data and Analytics, FTSE Russell, Risk Intelligence,
> and **Markets** – …"

四个分部里，只有 `Markets` 按月对外发布经营量。另外三个分部（Data & Analytics、
FTSE Russell、Risk Intelligence）**没有任何月度披露**，本页因此一列都没有。
LSEG 官网 `about-us/what-we-do` 把边界写得更清楚（等级 [A]）：

> "**LSEG Markets** combines these flagship trading services with LCH, Post Trade
> Solutions and Regulatory Reporting Solutions…"

（"these flagship trading services" 指前一句列举的 London Stock Exchange、AIM、
Turquoise、FXall、FX Matching、Tradeweb。本页四条腿正好取其中四块。）

### 指数与 ETF AUM 只在**季度 Trading Update** 里给

这一条本机今日直接核过原件，不是推断。LSEG 2026 年第一季度的 Trading Update
（RNS 全文 PDF，`lseg.com/.../rns/lseg-trading-update-q1-2026-rns-23apr2026.pdf`，
2026-04-23 发布，本机下载 421,355 字节、10 页）在「Divisional non-financial KPIs」
表里给的是**季度**口径（等级 [A]，原件逐字）：

| FTSE Russell | Q1 2026 | Q1 2025 | Variance % |
|---|---|---|---|
| Index – ETF AUM ($bn)：Period end | 1,871 | 1,434 | 30.5% |
| Index – ETF AUM ($bn)：Average | 1,906 | 1,449 | 31.5% |

同一张表里 `Markets` 分部给的是 "Equities UK Value Traded (£bn) – average daily value"
一类的量 —— 也就是说，**季度 Trading Update 里 Markets 那几行是本页月度数据的季度汇总，
而 FTSE Russell 那两行在月频上根本没有对应物**。

⇒ 三条直接后果，谁接这一页都得记住：

1. **不要在 `/lseg/` 页上找指数或 ETF AUM，也不要有人问起时去 `series/lseg.csv` 里翻**
   —— 86 列里没有，将来也不会有（除非官方改成按月发）。
2. **不要拿 MSCI 的月度 AUM 去和 LSEG 配对**。`series/msci.csv` 的 `aum_eop_usdbn`
   是**月频**，FTSE Russell 是**季频**，两条线放同一张图必须先说明频率不同；
   `build/pools.py` 的指数 AUM 池注释里已经写过同一件事（"S&P DJI、FTSE Russell、
   CRSP、Bloomberg 都不在池里，且**没有一家按月披露**"）。
3. **不要把本页的量增速当成 LSEG 集团收入增速的代理**。Markets 只是四个分部之一；
   即便在 Markets 内部，Tradeweb 的 ADV 与收入之间还隔着一个本仓拿不到的 FPM
   （费率），且 FPM 官方自述是 "preliminary, subject to management's final review"。
   详见 `fetch/lseg_tradeweb.py` 的「并表关系」一节。

---

## 四路数据源与稳定入口

**四路的共同纪律：URL 一律从官方索引里读出来，一个都不许拼、不许猜。**
四个源站各有各的重传/版本号机制，硬拼文件名的失败模式有两种，第二种远比第一种致命：
404（看得见）与**200 但给的是几年前的旧文件**（看不见）。

### 路 1　`orderbook` —— LSE 主板 + Turquoise 电子订单簿

| | |
|---|---|
| 官方源 | **LSEG Monthly Market Report**（每月一个 PDF），第 1 页 "LSEG - Electronic Order Book Trading" 的 **MTD 表** |
| 稳定入口 | `GET https://api.londonstockexchange.com/api/v1/pages?path=search&parameters=<双重 urlencode 的 "q=LSEG market report <Month> <Year>&tab=documents&size=..&page=.."/>` → `components[type=="search"].content[0].value.pagesdocuments` → 按 **title 精确匹配**取 `url` |
| 副源（只核对，不入库） | 同一检索接口拿到的 `Order book trading` 工作簿（xlsx，Monthly sheet 1997-10 起 346 行，成交额精确到便士） |
| 文件落在 | `https://docs.londonstockexchange.com/sites/default/files/reports/` |
| 抓取方式 | `urllib.request` 裸奔（两个域都是 CloudFront）；PDF 用 PyMuPDF，xlsx 用 openpyxl，均已在 `requirements.txt` |
| 落地 | 17 列，`series/lseg_part_orderbook.csv`，**2021-01 → 2026-06**（66 行，无空洞）[A] |

**字段、单位与币种**（列名自带单位，build 层不做二次换算）：

| 列族 | 列 | 单位 / 币种 |
|---|---|---|
| LSE 主板订单簿 | `lse_orderbook_value_gbp_m` / `_adv_gbp_m` | **英镑百万（£m）**，官方印到整数，不折美元 |
| | `lse_orderbook_trades_count` / `_avg_daily_trades_count` | 笔 |
| | `lse_trading_days_count` | 天 |
| Turquoise Integrated（lit） | `turquoise_integrated_value_gbp_m` / `_adv_gbp_m` / `_trades_count` / `_avg_daily_trades_count` | 同上 |
| Turquoise Dark（暗池） | `turquoise_dark_*` 四列 | 同上 |
| | `turquoise_trading_days_count` | 天，**与 LSE 那一列不同**（Turquoise 跟泛欧日历） |
| 份额（官方自己算的） | `lse_lit_uk_share_pct`、`turquoise_paneuropean_share_pct` | **百分点数值**（69.2 表示 69.2%，不是 0.692） |
| 换算率 | `gbp_eur_rate` | 报告里 "Exchange Rate (GBP/EUR)" 那一行的当月值，随报告一起入库，**不是 ECB 口径**，也不参与本页任何换算 |

📌 起点 2021-01 是**主动取舍**，不是抓不到：2020-12 及以前的月报还印 Italian /
Derivatives / MTS / EuroTLX 等行，且 `LSE Lit Orderbook trading in UK` 这个份额标签
2021-01 才出现。本仓禁止写 NaN，宁可少月份不许缺列。

📌 两源交叉核对：66 个月**全部对得上**，最大偏差 —— 笔数 8 笔、成交额 1.30 £m、
交易日 0 天 [A·转抄，`fetch/lseg_orderbook.py::_crosscheck()`]。

### 路 2　`primary` —— LSE 一级市场（Main Market + AIM）

| | |
|---|---|
| 官方源 | `Main Market factsheet <Month> <Year>.xlsx` 与 `AIM factsheet <Month> <Year>.xlsx`，**一个月一个文件** |
| 稳定入口（两跳） | ① `GET https://api.londonstockexchange.com/api/v1/pages?path=reports` 拿 `reportsFilterToggleFilters` 里 label 为 `Main Market` / `AIM` 的 `tabId` 与 `moduleId`；② `POST https://api.londonstockexchange.com/api/v1/components/refresh`，`componentId` 里的**冒号必须写成 `%3A`**，`parameters` 是二次编码的查询串 → `content[0].value.ctaItems[*].history.items[*].links` |
| 月份怎么定 | **从 label 解析**（`AIM factsheet April 2026.xlsx`），再用工作簿内第 3~4 行的标题格复核，不符就 raise |
| 抓取方式 | `urllib.request` + 普通 UA；2026-08-07 实测 8 线程一次拉 201 个 xlsx 零失败 |
| 落地 | 24 列，`series/lseg_part_primary.csv`，**2018-05 → 2026-07**（97 行；缺 2019-09、2022-12，是官方自己的洞）[A] |

**字段、单位与币种**：两个市场各一套，**谁都不并进谁**。

| 列 | 含义 | 单位 / 币种 |
|---|---|---|
| `mm_companies_eop_count` / `_uk_` / `_intl_`、`aim_companies_*` | 月末上市公司家数（总 / 英国 / 国际） | 家，**存量** |
| `mm_marketcap_eop_gbp_mn` / `_uk_` / `_intl_`、`aim_marketcap_eop_gbp_mn` | 月末总市值 | **英镑百万（£mn）**，存量 |
| `mm_new_issues_count` / `_uk_` / `_intl_`、`aim_new_issues_*` | 当月新上市家数 | 家，流量 |
| `mm_cancellations_count`、`aim_cancellations_count` | 当月注销家数 | 家，流量 |
| `mm_further_issues_count`、`aim_further_issues_count` | 当月增发次数 | 次，流量 |
| `mm_money_raised_new_gbp_mn` / `_further_`、`aim_money_raised_*` | 当月募资额（新上市 / 增发） | **英镑百万（£mn）**，流量 |

⚠ **`_gbp_mn`（本路）与 `_gbp_m`（订单簿）是同一个单位**，只是两条腿的命名习惯不同。
最容易犯的错是以为差 1000 倍去做二次缩放 —— 别做。

📌 **每份 factsheet 只覆盖「本年至今」**，所以某个月的月末存量只存在于那个月那一份文件里
（次月那份的年度块已经换成次月末的数）。36 个月 = 72 个文件，没有捷径。

📌 募资额一律取 **New Issues / Further Issues 专表**，不取 Summary 月度块、更不取年度块
（三处三个数；年度块那个在 Main Market 2026-07 上与专表差 43 倍，官方无脚注）。

### 路 3　`tradeweb` —— Tradeweb Markets（LSEG 并表子公司，Nasdaq: TW）

| | |
|---|---|
| 官方源 | Tradeweb 自己按月发的 **Monthly Activity Report** 配套工作簿 `TW Historical ADV and Day Count through <Month> <Year>.xlsx` |
| 稳定入口 | 每次先抓索引页 `https://www.tradeweb.com/newsroom/monthly-activity-reports/`，从 href 里解析出 `/<6位缓存串>/globalassets/newsroom/<MM.DD.YY>-<month>-mar/…xlsx`。**那两段每月都变**：6 位缓存串是 CMS 的 asset 版本号，目录名里的 `MM.DD.YY` 就是发布日 |
| 发布日证据 | 目录名里的 `MM.DD.YY` **与 HTTP `Last-Modified` 交叉校验**，对不上就抛异常 |
| 抓取方式 | ⚠ **反直觉**：`www.tradeweb.com` 挂 Cloudflare managed challenge，但它拦的是 TLS/HTTP2 指纹不是 UA —— `curl`（HTTP/2，任何 UA）→ 403 `cf-mitigated: challenge`；**`python urllib.request`（HTTP/1.1）→ 200 完整 HTML**。首选 urllib 裸奔，仅在拿回挑战页时回落 `curl_cffi(impersonate='chrome124')`（`requirements.txt:75` 已有）。**不要因为 curl 打不开就断定这站抓不了** |
| 落地 | 27 列，`series/lseg_part_tradeweb.csv`，**2017-01 → 2026-07**（115 行，**一格不缺**）[A] |

**字段、单位与币种**：工作簿内部单位是**百万美元**，而公司对外一律讲万亿/十亿美元。
本路按列名写死单位，build 层不再换算：

| 列 | 单位 / 币种 |
|---|---|
| `tradeweb_volume_total_usd_tn` | **万亿美元 / 月**（工作簿值 ÷ 1e6）—— **本页头条列** |
| `tradeweb_adv_total_usd_bn` | **十亿美元 / 日**（工作簿值 ÷ 1e3）—— 本页头条列 |
| `tradeweb_trading_days_blended` | 天，**加权反推值**（= 月成交额 ÷ 月 ADV），2026-07 实测 23.06 天；各产品分母天生不同（ICD Portal 报的是按自然日平均的现金余额，2026-07 是 30.43 天）⇒ **不要拿它算任何单一产品的日均，也不要与别家的 `trading_days` 直接比** |
| 其余 24 列（`tradeweb_adv_*`：rates / credit / equities / money markets 四大类及其子项） | 十亿美元 / 日 |

⚠ 成交额是**名义本金**，且部分市场双边计（完全匿名、Tradeweb 做 matched principal 时两边都算；
美债与按揭是单边；按揭按 current face value；回购按抵押品名义额）⇒ **与交易所的「成交金额」
不是同一种量，跨家横比要先说明口径**。

⚠ 非美元品种按**上一个月**的月均汇率折美元（官方 Disclosures 原文）⇒ 欧债 / 欧洲信用这几列里
含一个月的汇率滞后。

### 路 4　`lch` —— LCH 清算量（SwapClear / ForexClear / RepoClear）

| | |
|---|---|
| 官方源 | `https://www.lseg.com/en/post-trade/clearing/lch-services/{swapclear,forexclear,repoclear}/volumes`（`lch.com` 已整体 301 到这里） |
| 稳定入口 | 三个页面**三种完全不同的技术形态**：① SwapClear = AEM 组件 JSON，每个 DataGrid 带 `data-api-url="….datatable.json"`，四个页签里只有第一个随首屏 HTML 下来，其余三个要按 `data-content-location` 再取一次；② ForexClear = S3 预签名 CSV，`s3FileKey` **从页面 href 解析**（自己编 key 会 403/404 交替且分不清）；③ RepoClear = 内联静态 JSON，数据写死在首屏 HTML 的 `data-row-data-static` 属性里，三张表字段完全相同，**只能靠紧邻其上的 `<h2>/<h3>` 标题区分** |
| 抓取方式 | `urllib.request` 裸奔，依赖只有标准库。⚠ ForexClear 的预签名链接 `X-Amz-Expires=70`（**70 秒过期**，不能存下来复用，台账里记 `s3FileKey` 与 S3 对象的 `Last-Modified`）；⚠ 页面走 CloudFront `max-age=900`，**最长可能看到 15 分钟前的页面**，发布日当天连跑两次第二次才见新月份是正常现象 |
| 落地 | 18 列，`series/lseg_part_lch.csv`，**2024-08 → 2026-07**（24 行，但列之间深度不一，见专节）[A] |

**字段、单位与币种**：

| 服务 | 列 | 单位 / 币种 | 流量 / 存量 |
|---|---|---|---|
| SwapClear（OTC 利率互换） | `swapclear_notional_registered_usd_tn`、`swapclear_client_notional_registered_usd_tn` | **万亿美元** | 流量（当月登记） |
| | `swapclear_trades_registered_count`、`swapclear_client_trades_registered_count` | 笔 | 流量 |
| | `swapclear_notional_outstanding_eom_usd_tn`、`..._client_...`、`swapclear_trades_outstanding_eom_count`、`..._client_...` | 万亿美元 / 笔 | **存量（月末快照）** |
| ForexClear（外汇衍生品） | `forexclear_notional_registered_usd_tn`、`forexclear_trades_registered_count` | 万亿美元 / 笔 | 流量 |
| | `forexclear_notional_outstanding_eom_usd_tn`、`forexclear_trades_outstanding_eom_count` | 万亿美元 / 笔 | 存量 |
| RepoClear（回购） | `repoclear_ltd_nominal_value_eur_tn`、`repoclear_sa_*`、`repoclear_ltd_cash_value_eur_tn`、`repoclear_sa_*` | **万亿欧元** | 流量 |
| | `repoclear_ltd_cleared_trade_sides_count`、`repoclear_sa_*` | **边（trade sides）** | **流量** |

⚠ **三条腿的单双边口径各不相同，横向相加毫无意义**（官方原文，等级 [A]，各自页面正文）：
ForexClear 双边（"include the two legs of each cleared transaction"）；
RepoClear 双边（"double counted"）；SwapClear 的 SERVICE 列是 **novation 后**的组合口径、
CLIENT 列**只算客户那一边**。⇒ 两列都写进 CSV，**不做减法、不算「自营 = 总 − 客户」**，
跨腿求和（"LCH 总清算量"）同样禁止。

⚠ **RepoClear 的 LTD 与 SA 是两个法人不是两条产品线**：LCH Ltd（伦敦，清英国金边债与部分欧债，
€tn 量级 4 左右/月）、LCH SA（巴黎，清欧元区主权债，€tn 量级 25 左右/月）。规模差 6 倍，
加总后曲线基本就是 SA 自己；清算边数 SA 是 LTD 的 11 倍（2026-05：1,205,030 vs 106,192）。
⇒ **分列存、分组分图**，要合计由 build 层显式做并在图上写明。

⚠ **CDSClear 一列都没有。** 官方 CDSClear volumes 页三块内容全是**当日快照**
（日频 2 行、自开业累计 2 行、三个 `latest/` CSV 的 `Date` 列全是同一天），
即官方不发布 CDSClear 月度合计、也不留日频归档。按铁律 2，本路**不输出任何 `cdsclear_*` 列**
（不是写 0 占位，不是用日均×交易日估算）。`snapshot_cdsclear()` 每次运行把当日数据追加进
`cache/lseg_lch/cdsclear_daily.csv`，跑满一个完整月之后才有人有资格加这些列 ——
到那时聚合规则必须写死成：月度 = 该月所有 `Date` 的 Gross Notional **直接相加**（流量），
Open Interest **绝不能相加**，只取月末最后一个交易日那一格。

---

## 发布节奏（各路实测，转抄自各自 docstring）

⚠ 四路节奏差**一个数量级**，这是本页所有结构性设计的根因。

### `tradeweb`（头条腿，LAG 与闸门只跟它）

样本 = 把 `investors.tradeweb.com` 新闻稿列表页按年份翻了 2019-2026 全部 8 年、共 279 条稿件，
逐条匹配月报标题（措辞换过至少 6 种写法），命中 **88 个数据月** [A·转抄]：

```
全样本 2019-01 → 2026-07   n=88   次月第 2 至第 11 天，中位第 5 天
2021-01 起                 n=65   第 2 至第 8 天，中位第 5 天
最近 36 个月（2023-08 起） n=36   第 3 至第 8 天，中位第 6 天
按天计数：2→1  3→17  4→12  5→22  6→21  7→7  8→3  9→3  10→1  11→1
星期分布：周四 31 / 周三 27 / 周二 11 / 周一 10 / 周五 9
最晚：2019-03 数据 → 2019-04-11（第 11 天）；2021 起再没超过第 8 天
最早：2023-01 数据 → 2023-02-02（第 2 天，88 期里仅此一次）
```

⇒ `LAG['lseg'] = (8, 8)`（照 2021 年以后那 65 期的最晚值，不被 2019-2020 IPO 初期的尾巴绑架）、
`EARLY_BY['lseg'] = (7, 7)` ⇒ 次月**第 1 天**开闸。判据与理由见 `docs/CRON_WIRING.md` §2.2。

📌 该 docstring 里有一条**自我更正**值得读：此前写「最晚 2020-01 → 2020-02-12（第 12 天）」是错的，
真实发布日是 2020-02-05（第 5 天）。错因是列表页解析用了跨 `<tr>` 的非贪婪正则，把某一行的日期
配到了另一行的标题上；正确做法是先按 `<tr>` 切块、再在块内取 `<td>`。**LAG / EARLY_BY 不受影响**
（它们只取 2021 年以后的窗口，那一段两次解析结果完全一致）。

### `primary`（慢腿）

判据取工作簿 `docProps/core.xml` 的 `dcterms:created`，样本 = 2018-05 起两个市场**全部 197 期**
（不是抽样）[A·转抄]：

| 市场 | 样本 | 最早 | 中位 | P75 | P90 | 最晚 | ≤3 天 | ≤5 天 | ≤9 天 | ≤12 天 |
|---|---|---|---|---|---|---|---|---|---|---|
| AIM | 99 | +1 | +2 | +5 | +13 | +27 | 66 期 | 78 期 | 89 期 | 89 期 |
| Main Market | 98 | +1 | +2 | +4 | +9 | +27 | 68 期 | 79 期 | 89 期 | 91 期 |

（数字都是「数据月月末后第几天」，+1 = 次月 1 日。）近 24 个月（2024-08 ~ 2026-07）两个市场
都是 min +1 / 中位 +3 / 24 期里 22 期 ≤+9。

两个市场**不是每月同步发**：98 个共有月份里 68 个 `created` 日完全相同、74 个相差 ≤1 天，
其余 24 个最大相差 25 天。

⚠ `dcterms:created` 是**文件生成时刻**，不等于首次发布时刻 —— 文件被重新生成过，created 就跟着跳
（与 `fetch/db1.py` 的 Eurex Cover "Created on" 是同一个坑）。所以本路只给「本次运行刚确立的
那个月」当发布日证据，**绝不给回补的历史月份补记发布日**。HTTP `Last-Modified` 被重传污染得更狠
（AIM 103 期里 58 期与 created 不同，最大滞后 **751 天**），只能当旁证。

### `orderbook`（最慢的一条腿）

样本 = 2021-01 → 2026-06 共 **66 期一期不缺**，判据是 PDF 内嵌的 `/CreationDate`
（Excel 导出时间戳）[A·转抄]。复算：`python3 fetch/lseg_orderbook.py --cadence`。

```
全样本 66 期：最早 +1 天，最晚 +51 天，中位 +4 天，均值 +7.2 天
分布：+1 天 16 期 / +2..+6 天 28 期 / +7..+9 天 4 期 / +10..+24 天 17 期 / +51 天 1 期
季末月（22 期）与非季末月（44 期）无系统差异（中位 4.5 vs 4.0）
```

⚠ **节奏在 2024 年明显变慢，看这条腿只能看近两年：**

```
2021 年 12 期  +1..+6  天，中位 +2
2022 年 12 期  +1..+5  天，中位 +2
2023 年 12 期  +1..+6  天，中位 +2.5
2024 年 12 期  +5..+20 天，中位 +9.5
2025 年 12 期  +2..+15 天，中位 +10
2026 上半年 6 期 +2..+51 天，中位 +21
近 30 期（2024-01 起）：实测最晚 +24（2026-03 数据 → 2026-04-24），实测最早 +2
```

📌 那个 +51 天（2026-01 数据）**只能当上界读**：那一期文件名是 `..._1.pdf`（重传件），
CreationDate 记的是重新导出的时间。但同日生成的还有 2026-02 那期（文件名无后缀、非重传），
说明 2026 年初确实积压了两个月一起补发 —— 不是纯粹的重传假象。

📌 副源 xlsx 自己也会落后：2026-08-07 实测 `Order book trading` 工作簿 `Last-Modified`
停在 2026-07-30、数据只到 7 月 30 日，而同一天 2026-07 那期月报**还没发**（检索接口查无此条）。
**「LSEG 的月度订单簿数据慢」是常态，别把 NOCHANGE 当成抓取坏了。**

### `lch`（⚠ 样本期数 = 1，本页最大的诚实缺口）

四条腿的页面都**只挂当前这一份**，没有任何历史发布日留痕（不像 Euronext 有新闻列表可逐月回查、
也不像 Deutsche Börse 的 xls 封面写着 "Created on"）。下面每一行都是 **2026-08-07 一次快照里
量到的**，不是分布统计 [A·转抄]：

| 腿 | 数据月 | 发布 / 落地时刻（实测） | 次月第几天 |
|---|---|---|---|
| SwapClear | 2026-07 | `PublishedDate` = Aug 03, 2026 14:10 UTC | 3 |
| ForexClear | 2026-07 | CSV 内部 `Creation Date` = 2026-08-01 01:31（生成）；S3 `Last-Modified` = Aug 03, 2026 17:05 UTC（上线） | 1 / 3 |
| RepoClear | **2026-05** | 页面无任何发布日戳；抓取当日（8/7）最新月仍是 2026-05 | **≈ +2 个月** |
| CDSClear | 日频 | S3 `Last-Modified` = Aug 06, 2026 21:40:40 UTC | T+0 当晚 |

真正的分布只能靠每月把 `PublishedDate` 追加进 `cache/lseg_lch/source_dates.csv`，攒够 12 期再回来改。
⚠ **绝不要把闸门绑到 RepoClear 上** —— 那会让 SwapClear/ForexClear 白等两个月。

---

## 订单簿晚一个月：这对 `data_through` 意味着什么

**今天的事实（2026-08-07，本机现算 [A]）：**

| | 覆盖到 | 说明 |
|---|---|---|
| `series/lseg.csv`（宽表） | **2026-07**（115 行 × 86 列） | `data/lseg.js` 的 `data_through` = `2026-07` |
| `lseg_part_tradeweb.csv` | 2026-07 | 头条腿 |
| `lseg_part_primary.csv` | 2026-07 | |
| `lseg_part_lch.csv` | 2026-07 | 但 RepoClear 那 6 列只到 2026-05 |
| `lseg_part_orderbook.csv` | **2026-06** | 比其余三路晚整整一个月 |

宽表最后三行的空格分布，逐列点过：

```
2026-05  缺 0 列   —— 四路齐全
2026-06  缺 6 列   —— 全是 repoclear_*（RepoClear 自身滞后约两个月）
2026-07  缺 23 列  —— 17 个订单簿列 + 6 个 repoclear_* 列
```

**`data_through` 为什么仍然是 2026-07，而不是退回 2026-06：**

`build/specs/lseg.py` 的 `headline` 是 `tradeweb_volume_total_usd_tn` 与
`tradeweb_adv_total_usd_bn` —— 两列都在 Tradeweb 那条腿上，而 `data_through` 由 headline 决定
（`docs/SINGLE_SPEC.md` §5）。选 Tradeweb 做头条不是偏好，是三条判据逐条比下来的唯一答案：

- **历史长**：tradeweb 115 月（2017-01 起）> primary 97 > orderbook 66 > lch 24
- **无空洞**：tradeweb 那 27 列是 86 列里**唯一零空格**的一组；orderbook 前置 48 月空、
  primary 有 2019-09 / 2022-12 两个官方的洞、SwapClear 与 RepoClear 各只有 12 期
- **发布快**：tradeweb 是唯一进得了「次月一周内」的腿

另外两条是**硬性排除**不是偏好：`lch` 连 `SINGLE_SPEC` §3「共同连续历史 ≥ 24 个月」的门槛都过不了；
`orderbook` 若做头条，今天的 `data_through` 立刻退回 2026-06，且按 `docs/CRON_WIRING.md` §2.1
「LAG 跟着决定 data_through 的那条腿走」，`LAG['lseg']` 要从 (8,8) 抬到约 (26,26)，
**整页每月晚 18 天上线**。

⇒ 工程上的落实：除 tradeweb 外的三条腿全部进 `slow_cols`，**不参与门槛判定**；
底座会在每张涉及它们的图注末尾自动追加一句「XX 是慢腿：发布比头条晚，最新月留空是正常的」，
并在页尾统一点名。配合 `fetch/lseg.py` 的「**只填空不覆盖**」，2026-07 那一行会在两三周后
由 orderbook 自动补齐 —— 那正是这个幂等机制存在的理由。

⚠ **改 headline 就必须同步改 `build/roster.py` 的 `LAG['lseg']`**，否则红点会在慢腿到达之前每月假红。

---

## LCH 各服务的历史深度不一（这是官方滚动窗口，不是起点设窄）

| 服务 | 拿到的月数 | 实测区间 | 官方证据 |
|---|---|---|---|
| **ForexClear** | **24 个月** | 2024-08 → 2026-07 | 月度 CSV 末行原文 `Row Count: 24`，固定滚 24 行 |
| **SwapClear** | **12 个月** | 2025-08 → 2026-07 | 四张月度 datatable JSON 各固定 12 行 |
| **RepoClear** | **12 个月** | 2025-06 → 2026-05 | 三张月度 grid 各固定 12 行（同页**年度** grid 有 28 行、回溯到 1999 —— 证明官方有更深历史，但**只以年度形式公开**） |
| CDSClear | 0 | — | 只有当日快照，见上 |

⇒ 首月落地就是 24 行，其中只有最近 12 个月带 SwapClear 列、最近 12 个月带 RepoClear 列
（且 RepoClear 那 12 个月比 SwapClear 早两个月结束）。**后果比「只有 24 个月」更严重：
12 期连 13 期的点对点同比都算不出，24 期的 TTM 同比只有一个点、不成线。**
所以 LCH 的 18 列本轮一律只画水平值，且绝不进 headline。跑满一年后自然长到 24 期。

**官方免费口径下不存在更深的月度历史**，四条路都核过、都是死路 [A·转抄]：
LSEG IR「Trading Statistics」页只是把三个 volumes 页链回去、自己不带任何 LCH 数据文件；
SwapClear 的 "Volume Data Products" 子页写着 "as far back as 2011" 但那是**收费数据产品**
（走 LSEG Workspace 订阅）；RepoClear 页上那份 `rcl-monthly-nominal.pdf` 是按发债国分的**图**、
x 轴同样只有 12 个月且无数据标签；web.archive.org 在本机是硬禁域名。
**宁可 24 行真的，不要 36 行编的。**

---

## 已知的源侧缺陷（不是我们的 bug，是官方自己的）

### 1. LSE 一级市场 factsheet：官方在同一份工作簿里给两个募资额，且事后重述

募资额同时出现在 Summary 月度块与 New Issues / Further Issues **专表**。把 2018-05 起 197 期
每期自己那个月的两处逐位比对，**只有 3 期不等，而且 3 期全都是 Summary 那一侧后来被改成专表的值，
方向一次都没反过来** [A·转抄]。这 3 处已登记在 `cache/lseg_primary_conflicts.csv`
（本机今日读取原文，等级 [A]）：

| 期 | 市场 | 字段 | 专表值 | Summary 月度块值 | 后续期里的 Summary |
|---|---|---|---|---|---|
| 2018-06 | **Main Market** | `money_new` | 7.00999995 | 237.97915935 | 7.00999995（7 月那期已回改） |
| 2022-03 | **AIM** | `money_further` | 214.37873751 | 207.48509751 | 214.37873751（6 月那期已回改） |
| 2026-05 | **Main Market** | `money_further` | 969.83130022 | 833.32263722 | — （当前最新，尚未回改） |

📌 **注意口径**：这 3 处里 **AIM 只占 1 处，Main Market 占 2 处** —— 不要笼统说成
「AIM factsheet 被重述过 3 次」。这个日志登记的是**两个市场合计**的 3 处 Summary-vs-专表冲突。

⇒ 处理方式：**募资额一律取专表**；取完再与 Summary 月度块比对，不等就记进冲突日志供人工判断，
**不自动吞、也不自动改**。第三条还有一个闭合旁证：Main Market 2026-07 那期年度块的 YTD Further
= 2126.76110737，与 Further Issues 专表 YTD **逐位相等**，而 Summary 月度块 7 个月加起来只有
1990.25244437 —— 差的正好是 5 月那 136.5。

⚠ 两个市场的专表列名写法不同：AIM 写「New Issues (£m)」，Main Market 写
「Money Raised - **New Shares**」。别被后者误导成「只算新股、不算老股减持」——
2018-07 那期把 Summary 回改成了专表的值，说明官方自己就把这两个当同一个序列。

### 2. Tradeweb：新闻稿与历史工作簿**系统性微差**（首发口径 vs 事后重述）

两件事叠在一起，都由官方 Disclosures 自述，且本机实测过后果 [A·转抄]：

**(a) 首发新闻稿的精度就不够。** 稿子里只有四舍五入到 1 位小数的总 ADV（"$2.9tn"，
误差可达 ±$50bn），且 rates / credit / equities / money markets 四个**资产类别合计**
只在 xlsx 里有。⇒ **IR 新闻稿只配当发布节奏的台账，不配当数据源。**

**(b) 历史值会被官方悄悄改，实测重述率 6.6%。** Disclosures 原文：
"Volumes can reflect cancellations, corrections and settlement of NAV trades on ETFs that occur
after prior postings; historical volumes are periodically updated."
本机实测（2023-01 起每 3 个月抽 1 期新闻稿共 15 期，与今天的工作簿逐格比，**121 个可比
「字段 × 月份」**）：

```
一致 113 个，被事后改过 8 个 —— 6.6%
6 处在 ±0.15% 以内（四舍五入级）
1 处 −0.83%（2023-10 Swaps/Swaptions ≥1Y  463.4 → 459.535）
1 处 +11.5%（2024-01 美债  $182.1bn → $203.073bn）
最爱被改的是 Other Money Markets（8 处里占 4 处）
```

那 +11.5% 有官方口径变更做解释：2024-12 起 Tradeweb 改了并购业务的 ADV 分母算法并
**回溯重述了 2024 年两笔收购**（r8fin 交割 2024-01-19、ICD 2024-08-01）。
⚠ 因果只说到能证的那一层：日期与官方自述完全吻合，但**官方没给逐项对照表**，
所以只陈述实测差额，不断言这 11.5% 全部由该变更造成。

⇒ 两条纪律：① `write_csv()` **只填空不覆盖**，冲突写 `cache/lseg_tradeweb_restatements.csv`
供人工判断（与 enx / db1 同一处理方式）；② **绝对不要把某一期新闻稿的数字手工补进序列** ——
工作簿内部是重述后的一致口径，同比可以算；手工混入首发值会插进一个 11% 的假台阶。

📌 另一个「对不上不是错」的例子：工作簿 Credit Total ADV（2026-07 = $40.0bn）与稿子标题里的
"Fully electronic U.S. credit ADV $9.4bn" 不是一回事（前者含信用衍生品、中国债等）。
要对，请用 `tradeweb_adv_us_hg_fully_electronic_usd_bn` 与 `..._us_hy_...` 之和。

### 3. LSE Monthly Market Report：**YTD 区块排版会出错**

实测证据是 **2026-06 那一期**：YTD 区块里 Turquoise Integrated 的 £m 印成 28,264
（**与 MTD 一模一样**）、€m 印成 204,771、同比 −83% —— 官方自己排错了版 [A·转抄]。

⇒ 本路**只解析第 1 页 "Average Daily" 之前的 MTD 表 + "Trading days" 表，YTD 区块从不碰**。
`fetch/lseg_orderbook.py` 的 `_parse()` 里对此有硬性窗口约束，谁要加 YTD 列，
**先去逐格核对这一期**。

📌 **精确说明证据强度**：在本仓留痕的**只有 2026-06 这一期**的 YTD 错误（其余期没有逐期核过 ——
因为从一开始就决定不解析 YTD 区块，没有产生对照数据）。所以「YTD 区块不可信」这条结论的
证据是「1 期确凿出错 + 从未被验证过的其余 65 期」，不是「反复出错的统计」。
要把 YTD 列做进页面的人，得先自己把 66 期全核一遍。

### 4. 行标签改过名字（三条腿共 3 次），以及表头行会上下对调

- Turquoise 暗池：`Turquoise MidPoint` → `Turquoise Plato™`（2017 起）→ `Turquoise Dark`
  （2026-01 起）—— **同一条腿改名**，统一写进 `turquoise_dark_*`。
- LSE 现货：`UK order book`（→2020-12）→ `LSE Order Book`（2021-01→）。
- 份额行：`UK Lit Orderbook trading`（→2020-12）→ `LSE Lit Orderbook trading in UK`。
- 标签里的 `™` 与结尾空格都要 strip（"Turquoise Dark " 在 Average Daily 区块里带尾空格）。
- factsheet 的表头两行会上下对调（AIM 2023-03 起、Main Market 2022-10 起是新版式），
  **按行号定位必挂**。

---

## 已知功能缺口：本模块**不写** `series/source_dates.csv`

这是个刻意留的洞，不是遗漏。页面抬头那句「官方发布于 YYYY-MM-DD」按
`build/CONTRACT.md` §1 是**一句关于外部世界的事实断言**，而在四路拼一页的情形下，
「这个月是哪天可以看的」取决于哪条腿决定 `data_through` —— 四条腿能给出的东西还不对等：

| 腿 | 能不能给发布日 | 形态 |
|---|---|---|
| `tradeweb` | ✅ 能，且能交叉校验 | xlsx 目录名里的 `MM.DD.YY` + HTTP `Last-Modified` |
| `orderbook` | ⚠ 能逐月给，但要剔除 `_N.pdf` 重传件 | PDF 内嵌 `/CreationDate` |
| `primary` | ⚠ 能逐月给，但只对「本次刚确立的那个月」有效 | xlsx `docProps/core.xml` 的 `dcterms:created` |
| `lch` | ❌ 只有当前快照的一个日期 | SwapClear `PublishedDate` / ForexClear S3 `Last-Modified`；RepoClear 页面无戳 |

**硬凑一个「四者取最晚」写进台账，等于用一个说不清含义的日期去冒充事实断言。**
所以宁可让页面缺这半句（底座会自动省掉），而不是写一个自己都解释不了的日子。

另一个技术理由：四路是**并行**跑的，四个进程同时往同一个共享台账里追加必然打架 ——
所以发布日由各 part 模块的 `release_date()` 返回，交给合流层统一钉。合流层已经留好
`release_dates()` 接口，**等 `data_through` 政策定下来可以一次接上**，
不需要改任何 part 模块。页面上这句缺口也已经在 `build/specs/lseg.py` 的页尾 notes 里
向读者交代过（`_NOTE_SOURCE_DATE`），不是无声缺席。

---

## 横截面：本轮**未接**，且不是漏接

**LSEG 只有单公司页 `/lseg/`，`build/exchanges*.py` 与 `data/exchanges-*.js` 这一轮逐字节未动。**
`/exchanges12/` 仍是那 12 家、`/exchanges-eu/` 仍是 Euronext / Cboe Europe / Deutsche Börse 三家。

原因是口径，不是工期：本页 86 列里没有一列与现有横截面池同口径同量纲。

| 现有池 | LSEG 有没有对应物 | 判断 |
|---|---|---|
| 欧洲现货竞争（`/exchanges-eu/`，成交额 ADV） | `lse_orderbook_adv_gbp_m`、`turquoise_integrated_adv_gbp_m` | **最有希望的一组**，但要先解决三件事：① 币种是 GBP，池内是 EUR，折算会把 [A] 变成派生的 [C]；② 这条腿**晚一个月**，接进去会把整页的共同最新月拖回 2026-06；③ 官方份额列（`lse_lit_uk_share_pct`）的分母是「英国 Lit 订单簿」，与池内「三家之和」的分母不是一回事，两个占比不能混画 |
| 欧洲衍生品（见 `docs/verify/ice.md`） | ❌ 无 | LSEG 月度里**没有场内衍生品成交量**。LCH 是**清算**名义额与清算边数（且三条服务线单双边口径各不相同），Tradeweb 是 **OTC** 固收/信用的名义额 ADV —— 与 ICE 的 `adv_*_kcontracts`（张数）量纲与内容都对不上 |
| 指数 AUM（`build/pools.py`） | ❌ 无 | **FTSE Russell 不按月披露**，见本文「口径边界」一节。硬拿季度 ETF AUM 去和 MSCI 的月度 AUM 并排，是频率不同的两条线 |
| 一级市场 | ❌ 池不存在 | 本仓目前没有一级市场横截面页；LSE 是唯一一家有月度 IPO / 募资数据的 |

⇒ 要接横截面，**先定跨口径规则再接**，不要为了让欧洲页多一条线就把 GBP 折成 EUR。
本仓的立场一贯是「宁可少一条线，不要一条说不清口径的线」。

---

## 已知的、写在这里免得下一个人重踩

1. **四路 URL 一个都不能拼。** 四个源站的重传机制各不相同，但失败模式一样致命：
   - 一级市场：2026-08-07 全量统计，AIM 2018-01 起 103 期里 **43 期**带 `_N` 后缀、
     Main Market 98 期里 **31 期**带。硬拼文件名会有**四成月份 404**。
   - 订单簿：Drupal 同名重传会加后缀（`Order book trading_1558.xlsx`，数字每传一次 +1）。
     不带后缀的 `Order book trading.xlsx` **确实存在且返回 200**，但 `Last-Modified`
     停在 **2020-09-15** —— 这是最恶心的一种坑：猜出来的 URL 不报错，只是永远给你六年前的数据。
   - 少数条目的 title 里带扩展名（2022-06 那期在 CMS 里叫 `LSEG market report June 2022.pdf`），
     匹配时要先把 title 末尾的 `.pdf` 去掉。
2. **两个官方 JSON 接口的编码要求，少一层不报错、只静默给错结果。**
   检索接口的 `parameters` 是**双重 urlencode**；`components/refresh` 的 `componentId`
   里冒号必须写成 `%3A`（不编码时接口照样 200，但 body 是空数组 `[]`）。
   ⇒ 两处都对空结果直接 raise，**绝不当成「本月没有报告」**。
3. **走过的三条死路，别再走**（订单簿那一路）：`docs.londonstockexchange.com` 的目录页返回 403；
   Angular 的 `/api/v1/components/refresh` 用页面里的 block_content id 拉 tab 模块**一律返回 `[]`**
   （页面级 component 如 hero 却能拉到，说明 id 不通用）；web.archive.org 在本机是黑名单。
4. **Tradeweb 的月报不上 SEC EDGAR。** CIK 1758730 自 2018-11 至今只有 65 份 8-K，逐条看过 items
   全是 2.02（季度业绩）+ 5.02/5.07/1.01 这些公司行为。想省事去 EDGAR 找月报的会白翻一遍。
5. **`build/yoy.py` 的 `classify()` 对本表 15 列判错 kind**，本页不受影响
   （`build/single.py` 有自己的 `yoy_line`，只看 `fmt` 是不是 pct*/pp*），
   但**横截面页若接 lseg 的列必须显式传 `kind`**：
   - `tradeweb_adv_rates_usd_bn` / `_rates_cash_` / `_rates_derivatives_` 会被 `_RATIO_PAT`
     里字面的 `rates` 判成 RATIO（**这里的 Rates 是资产类别名不是费率**），
     `mom_yoy(s, RATIO)` 走 `v − base`，会把 +47% 印成「+562pp」**而且不报错**；
   - `repoclear_*_cleared_trade_sides_count` 2 列会兜底成 STOCK（官方术语是 trade **sides**，
     `_FLOW_PAT` 认的是 `trades`），方向在安全侧（`ttm()` 抛 CaliberError 而不是给错数）。
   **不许改 `build/yoy.py`** —— `CONTRACT.md` §6 明写 `classify()` 只是建议，
   有疑问时由调用方显式传 kind。
6. **`EARLY_BY` 必须写成元组。** 取值处是 `EARLY_BY.get(t, (EARLY, EARLY))[1 if qe else 0]`，
   写成裸整数会在下标那步 TypeError，**崩掉的是整轮 `monthly_run`，不只是这一家**
   （`fetch/enx.py` 已经踩过一次）。
7. **不要把成交额与 ADV 绑成量价恒等式。** `decomp` / `ttm_yoy` 一旦同时给 `weight_col`
   与 `*_total_col`，底座会逐月对账，相对偏差 > 1e-6 就**整页硬失败**（退出码 1）。
   实测残差：Tradeweb `ADV × blended 天数 vs 月成交额` 2.5e-4、
   orderbook `ADV × 交易日 vs 月合计` 9.1e-4 —— 两条腿都远超阈值，原因是官方自己就把 £m
   四舍五入到整数、把 blended 天数印到 2 位小数。
8. **`series/lseg_breaks.csv` 不存在，`breaks` 是空的**，这是刻意的。三处已知口径变化
   （Turquoise 改名、Tradeweb 2024-12 分母重述、订单簿起点 2021-01）都不该画成全页红线 ——
   红线画在**每一张**横轴是月份的图上，为一两列的变化误伤其余八十多列不划算。
   三条都写进页尾 `notes` 了。
9. **降级与不降级的分界**（`fetch/lseg.py`）：**源头缺席**（站挂了 / 官方还没发 / 解析器按铁律 2 主动抛）
   → 该路本轮不刷新，但**已落库的 part CSV 照常参与合流**，其余三路照跑，打 WARN；
   四路**全挂**才抛异常（否则 `monthly_run` 会看到 `added=[]` 报 NOCHANGE，
   把一次全站故障伪装成「本月没有新数据」）。**结构缺席**（part 模块文件不见了 /
   part CSV 表头与该模块 `COLUMNS` 对不上）→ **立刻抛，不降级**：那两种情况下宽表会
   静默少一整列或静默错位，而少一列的宽表照样能写出去、照样能画图，没有任何人会发现。
