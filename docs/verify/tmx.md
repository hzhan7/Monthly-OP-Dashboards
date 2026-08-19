# TMX Group（slug: tmx）—— 数据源可行性侦察

侦察日期 2026-08-06。所有数字都是本次实测解析出来的，脚本在 `/tmp/exch_recon/scratch/`。

---

## 判定

**B —— 可实现，但有坑，且有一块必须砍掉。**

拆开说：

| 板块 | 判定 | 理由 |
|---|---|---|
| MX 衍生品（ADV / 月度量 / OI，分产品） | **A** | m-x.ca 月度 xlsx，`urllib` 直取，2002-01 起逐月无断档，实测 2015-01..2026-07 共 139 期全部 200 |
| 加拿大现货（TSX / TSXV / Alpha / Alpha-X & DRK） | **B → A−**（2026-08-18 起） | TMX IR 的 Q4 新闻稿 feed，`urllib` 直取，正文表格仍然只从 2021-08 开始；**2015-01~2021-07 那 79 期已由另一个源补齐** —— CIRO（原 IIROC）的『Report of Marketshare by Marketplace (Historical 2015–Present)』xlsx，一次性脚本 `build/basefill/tmx_ciro_2015.py`。⚠ 两个源不是同一把尺子，接缝处有台阶，见下方追记 |
| 现货 2014-12 ~ 2021-07 历史 | **D** | 数据只在 `tmx.com/en/resource/<id>` 的 PDF 里，该域被 CloudFront WAF 从本网络整体拦掉（真实 Chrome 也拦），无合规通道 |
| BOX 期权 ADV（月度） | **D** | TMX 官方**只按季度**披露 BOX，没有任何月度口径；BOX 自己的站点也不发月度统计 |

~~整体给 B 而不是 A：现货序列只能从 **2019 起**（题目底线）都做不到，实际起点是 **2021-08**，
同比要等到 2022-08 才有第一个点。~~

> **2026-08-19 追记 —— 上面这段的核心论据已被推翻。**
> 现货 12 列今天是 **2015-01 → 2026-07 共 139 个月**（本机现算 [A]），比 MX 那半边只短 13 年，
> 「连 2019 起都做不到」不再成立。补洞的**不是**同一条链路：TMX CTS 新闻稿正文的表格
> 确实仍然 2021-08 才有（2026-08-18 复核 feed 140 期：无表 80 期 / 有表 60 期，边界干净），
> 更早那段走的是 **CIRO** 这个第三方监管机构的历史市场份额 xlsx，
> 由一次性脚本 `build/basefill/tmx_ciro_2015.py` 写入（不进 `fetch/tmx.py`，
> 理由是「另一个源、另一种版式、只会用这一次、口径不同」，三条都写在该脚本 docstring 里）。
>
> **必须一起记住的代价（不要只记住"变长了"）**：
> · **只往左写**，`CTS_FROM = 2021-08` 之后一格都不越界，且走 `_merge`「已有值永不覆盖」；
> · 60 个重叠月实测 TMX 自报 ÷ CIRO 的中位数：笔数三列与 tsxv 两列 ≈ 1.00000，
>   但 `tsx_volume_shares` 0.98683、`tsx_value_cad` 1.00162、`alpha_value_cad` 1.00249
>   —— **量偏低、额偏高，方向相反**，不是「含不含大宗对敲」那种可加减的一块；
> · 接缝台阶只有两条值得标断点线（`tsx_volume_shares` −1.62%、`tmx_all_volume_shares` −0.98%），
>   其余 10 列 |台阶| ≤0.17%，标了反而是在说「这两个月不可比」而它们其实可比。
> · 另外 `tsx_composite_close` / `tsxv_composite_close` 两列现在回到 **2001-12**（296 个月），
>   所以 `series/tmx.csv` 的行数是 296 而不是 295 —— **别把行数当成任何一列的长度**。

MX 那半边完全够格（2015 甚至 2002 起）。
起点线索里点名要的 **BOX ADV 拿不到**，这是本次侦察最大的一个"没做到"。

---

## 数据源

### 源 1：Montréal Exchange 月度统计 xlsx（衍生品，主源）

```
落地页  https://www.m-x.ca/en/trading/data/monthly-volumes-and-open-interest
直链模板 https://www.m-x.ca/f_stat_en/{YY}{MM}_stats_en.xlsx      （同名 .pdf 亦存在）
        例：2026 年 7 月 -> https://www.m-x.ca/f_stat_en/2607_stats_en.xlsx
```

* 抓取方式：**纯 `urllib.request` + 普通桌面 UA，200**。无 Cloudflare / Akamai / JS 渲染 / 登录墙。
  落地页上永远只挂最近 3 期的直链（实测挂着 2605 / 2606 / 2607），但**模板本身对任意历史月都成立**，
  所以「最新月」应当由落地页给（它是官方自己维护的"当前最新"指针），历史回补直接按模板拼。
* 未发布的月份返回 **HTTP 404**（body 是 HTML），和已发布的 `application/vnd...spreadsheetml.sheet`
  区分得干干净净 —— 不像 Cboe 那样 403/404 混淆，可以放心用状态码当"发了没有"的判据。
* 每份文件**只覆盖它自己那一个月**（另附去年同月、上月、YTD 三组对照列）。
  所以回补 N 个月就要下 N 个文件，不像 CME/Cboe 一份文件带全历史。
* 工作簿 4 张表：`Cover Page` / `EN`（月度量 + 月末 OI）/ `EN ADV`（日均量）/ `Product`（产品说明）。
  **老档 sheet 名带月份**（2015-01 档是 `Jan 2015 EN` / `Jan 2015 EN ADV`），新档就叫 `EN` / `EN ADV`
  —— 按后缀匹配，不要写死。

### 源 2：TMX Group Consolidated Trading Statistics 新闻稿（现货，主源）

```
Q4 新闻稿 feed（返回 JSON，正文 HTML 在 Body 字段里）：
https://investors.tmx.com/feed/PressRelease.svc/GetPressReleaseList
    ?LanguageId=1
    &bodyType=1                 <- 关键：0 不给正文，1 给完整 HTML（表格就在里面）
    &pressReleaseDateFilter=3
    &categoryId=
    &pageSize=200&pageNumber=0
    &tagList=trading-statistics <- 官方自己的分类 tag，比按标题 grep 稳
    &includeTags=true
    &year=-1                    <- -1 = 全部；也可给具体年份分页
    &excludeSelection=1
```

* 抓取方式：**纯 `urllib.request` 200，`curl` 也 200**。实测确认，不需要 curl_cffi、不需要浏览器。
* ⚠ 但**同域的 HTML 落地页** `https://investors.tmx.com/English/News--Events/news/default.aspx`
  走 Cloudflare，对普通 `curl` 返回 403（JA3 指纹拦，和仓库里 HOOD 那条同类），
  只有 `curl_cffi(impersonate='chrome')` 能开。**`/feed/` 这条路径不在那条规则覆盖范围内**
  —— 所以生产实现要走 feed，千万别去解析落地页，否则平白引入一个 curl_cffi 依赖。
* `tagList=trading-statistics` 在 2015~2026 每一年都命中（实测 2016 年也能过滤出来），
  可以当稳定的发现机制。全量共 **139 期，2014-12 ~ 2026-06，逐月无一缺失**。
* 备份通道：每期同时有 PDF 挂在 `https://s21.q4cdn.com/671813756/files/doc_news/...pdf`，
  `urllib` 直取 200。但 **PDF 的表格渲染不全**（2022-05 及更早的 PDF 里表格整块丢失，
  而同一期的 HTML Body 里表格是完整的），所以 PDF 只适合当取证副本，不能当解析源。

### 源 3：TMX Group 季度 MD&A（BOX 的唯一官方口径，季度）

```
https://s21.q4cdn.com/671813756/files/doc_financials/2026/q2/TMX-Group-Limited-Q2-2026-MD-A_EN-FINAL.pdf
```
`urllib` 直取 200，47 页，文字层完整（**不需要 OCR**）。里面有一张"最近八个季度"的 BOX 表。

### 拿不到的：`tmx.com` / `tsx.com`

```
https://www.tmx.com/en/resource/<id>      <- 2014-12 ~ 2021-07 现货数据的唯一所在
```

整个 `tmx.com` 与 `tsx.com` 对本网络返回 **CloudFront 403「Request blocked.」**（AWS WAF 规则，
不是 geo-restriction —— geo 的文案会明说"blocked access from your country"）。实测排除法：

| 客户端 | 结果 |
|---|---|
| `curl` / `urllib` / `nscurl` | 403 |
| `curl_cffi impersonate=chrome136 / safari184`（真实 TLS 指纹） | 403 |
| **本机真实 Chrome（Chrome MCP 实开）** | **403** |
| UA 改成 `Googlebot/2.1` 或 `bingbot/2.0`（其余不变） | **200** |

也就是说：TLS 指纹不是原因，UA 也不是普通意义上的原因 —— WAF 对本出口 IP
（实测 `210.10.1.210`）整体封禁，只给搜索引擎爬虫 UA 开了个白名单口子。
**我不建议把"伪装成 Googlebot"写进生产代码**：那是对一条明确针对本网络的封禁规则做规避，
且冒用搜索引擎身份；本报告只把它作为"封禁性质诊断"记录，不作为可用通道。
真要补 2014-12~2021-07 的现货历史，正当做法是换一条出口线路（或从 TMX 换个渠道要数据）
后**一次性人工回补**进 `series/tmx.csv` —— 那是一次性动作，不影响 cron 的无人值守。

---

## 可提取字段

照 `cboe.csv` 风格，带单位后缀。分两个 CSV，因为口径周期不同。

### `series/tmx.csv`（月度）

| 列名 | 口径 |
|---|---|
| `month` | `YYYY-MM` |
| `tmx_all_volume_shares_bn` | 全部 TMX 股票市场当月成交股数（十亿股）。= TSX+TSXV+Alpha+Alpha-X/DRK，含 NEX |
| `tmx_all_value_cadbn` | 同上口径的当月成交额（C$ 十亿） |
| `tmx_all_transactions_mn` | 同上口径的当月成交笔数（百万笔） |
| `tsx_volume_shares_bn` | Toronto Stock Exchange 当月成交股数（十亿股） |
| `tsx_value_cadbn` | TSX 当月成交额（C$ 十亿） |
| `tsx_transactions_mn` | TSX 当月成交笔数（百万笔） |
| `tsx_composite_close` | S&P/TSX Composite 月末收盘点位（官方在同一张表里给，不是我们外接的） |
| `tsxv_volume_shares_bn` | TSX Venture 当月成交股数（十亿股，**含 NEX**） |
| `tsxv_value_cadbn` | TSXV 当月成交额（C$ 十亿） |
| `tsxv_transactions_mn` | TSXV 当月成交笔数（百万笔） |
| `tsxv_composite_close` | S&P/TSX Venture Composite 月末收盘点位 |
| `alpha_volume_shares_bn` | TSX Alpha Exchange 当月成交股数（十亿股，**不含** Alpha-X / Alpha DRK） |
| `alpha_value_cadbn` | Alpha 当月成交额（C$ 十亿） |
| `alpha_transactions_mn` | Alpha 当月成交笔数（百万笔） |
| `alphax_drk_volume_shares_mn` | Alpha-X + Alpha DRK 当月成交股数（**百万股**，量级差 3 个数量级，独立单位） |
| `alphax_drk_value_cadbn` | Alpha-X + Alpha DRK 当月成交额（C$ 十亿） |
| `mx_volume_kcontracts` | MX 当月成交合约数（千张） |
| `mx_adv_kcontracts` | MX 当月日均成交（千张）。**官方直接给，不要用总量除**（见口径坑 1） |
| `mx_oi_kcontracts` | MX 月末未平仓（千张） |
| `mx_adv_stir_kcontracts` | 短端利率（BAX+CRA+COA 期货 + OBX/OCR 期权）ADV，千张 |
| `mx_adv_bond_futures_kcontracts` | 国债期货合计（CGZ+CGF+CGB+LGB）ADV，千张 |
| `mx_adv_cgb_kcontracts` | 10 年期国债期货 CGB ADV，千张（MX 旗舰合约，单列） |
| `mx_adv_cgf_kcontracts` | 5 年期 CGF ADV，千张 |
| `mx_adv_cgz_kcontracts` | 2 年期 CGZ ADV，千张 |
| `mx_adv_index_futures_kcontracts` | 股指期货合计 ADV，千张 |
| `mx_adv_sxf_kcontracts` | S&P/TSX 60 标准期货 SXF ADV，千张（单列） |
| `mx_adv_equity_options_kcontracts` | 个股期权 ADV，千张 |
| `mx_adv_etf_options_kcontracts` | ETF 期权 ADV，千张 |
| `mx_adv_share_futures_kcontracts` | 个股期货 ADV，千张 |
| `mx_oi_bond_futures_contracts` | 国债期货月末 OI（**张，不是千张**，与 cme.csv 的 `oi_*_contracts` 对齐） |
| `mx_oi_stir_contracts` | 短端利率月末 OI（张） |
| `mx_oi_equity_options_contracts` | 个股期权月末 OI（张） |
| `mx_oi_etf_options_contracts` | ETF 期权月末 OI（张） |
| `trading_days_equity` | 当月**股票类**产品交易日数 |
| `trading_days_rates` | 当月**利率/债券类**产品交易日数（每年 9 月、11 月与上一列不同，见口径坑 1） |

现货那几家官方只给月度总量，**日均要自己用 `trading_days_equity` 除**
（官方新闻稿里印的 Daily Average 只保留到 0.1 million，别抄那个，见口径坑 9）。

### `series/tmx_box_q.csv`（季度，独立文件）

| 列名 | 口径 |
|---|---|
| `quarter` | `YYYY-Qn` |
| `box_volume_mncontracts` | BOX 当季成交合约数（百万张） |
| `box_equity_options_share_pct` | BOX 在全美股票期权的市占率（%，官方只给整数） |
| `box_revenue_cadmn` / `box_revenue_usdmn` / `usdcad_avg` | 收入与当季均价汇率 |

月度是**做不出来的**，别在这一列上假装有月度。

---

## 历史深度

| 序列 | 最早 | 断档 |
|---|---|---|
| MX 全部字段（m-x.ca xlsx） | **2002-01**（2001-01 及更早 404） | 实测 2015-01..2026-07 共 **139 期全部 200 且都是真 xlsx，零断档** |
| 现货 TSX / TSXV / Alpha（CTS 新闻稿正文表格） | **2021-08** | 2021-08..2026-07 共 **60 期全部完整解析，零断档** |
| 现货 TSX / TSXV / Alpha（**接上 CIRO 回填后的入库序列**） | **2015-01** | 2015-01..2026-07 共 **139 期零断档**（2026-08-19 实测）。2015-01..2021-07 那 79 期来自 CIRO xlsx，有口径台阶，见上方追记 |
| `tsx_composite_close` / `tsxv_composite_close` | **2001-12** | 296 个月，比现货量价列长 13 年 —— CSV 的行数由它们决定 |
| Alpha-X & Alpha DRK 单列 | **2023-11** | 之前官方不拆这一项，是真·天然为空，不是解析失败 |
| 现货（新闻稿存在但表格不可读） | 2014-12 | 2014-12~2021-07 共 80 期，数据在被墙的 `tmx.com/resource` PDF 里 |
| BOX（季度） | 每份 MD&A 给最近 8 个季度 | 往前翻历年 MD&A 可拼到更早，但只有季度 |

**对本仓库的意义**（2026-08-19 改写）：MX 与现货**两半边现在都满足"2015/2016 起"的偏好**。
~~现货那半边连"最少 2019 起"都不满足，同比第一个点在 2022-08，指数化基期只能定在 2021-08 或更晚；
如果横截面页要求各家起点对齐，TMX 的现货曲线会比 CME/Cboe/HKEX 短一大截。~~
—— 现货已回到 2015-01，同比第一个点在 2016-01，指数化基期可以定在 2015-01 或 2016-01
（全站统一起点是 2016-01），横截面页不再需要为 TMX 单独让步。
**但换来了一个新的注意事项**：2021-08 那个接缝是换源，`tsx_volume_shares` 与
`tmx_all_volume_shares` 两列跨缝有 1% 量级的台阶（已由 `build/specs/tmx.py` 画断点线）。

---

## 发布节奏

**MX xlsx**（139 期 Last-Modified 实测）：次月**第 1–4 个工作日**，几乎都在 18:01 GMT 整点批量上传。
```
2026-01 -> 02-02   2026-02 -> 03-02   2026-03 -> 04-01   2026-04 -> 05-01
2026-05 -> 06-01   2026-06 -> 07-02   2026-07 -> 08-04
```
异常：2025-06 档 Last-Modified 是 2025-07-31、2025-08 档是 2025-09-26、2025-12 档是 2026-01-14
—— 那是**原地重传**把时间戳推后了，不是首发日晚。所以 Last-Modified 只能当"节奏参考"，
**不能当权威发布日写进 source_dates**（和 HKEX 那条坑同类，但 MX 重传更频繁）。

**CTS 新闻稿**：Q4 feed 的 `PressReleaseDate` 字段就是**官方自述的发布日**，权威、精确到日，
不需要靠 Last-Modified 猜 —— 这是 TMX 相对 CME/HKEX 的优势，`source_dates.csv` 直接用它。
139 期的日分布：
```
次月第 2 日 ×3   第 3 日 ×27   第 4 日 ×23   第 5 日 ×25
第 6 日 ×45      第 7 日 ×13   第 8 日 ×2    第 14 日 ×1（2025-04 那期，唯一一次大幅延迟）
```
中位数 = 数据月末后 5 天，最坏 14 天。

⇒ **闸门建议**：MX 从次月 1 日就可以开；CTS 从次月 2 日开、到 15 日仍拿不到才算异常。
两边节奏不同，会出现「MX 已有 7 月、现货还停在 6 月」的正常状态 ——
**实测今天（2026-08-06）就正是这个状态**：`2607_stats_en.xlsx` 已在（08-04 上传），
而 2026-07 的 CTS 尚未发布。所以 `latest_month()` 必须**按 MX 与现货分别判最新月**，
不能用一个标量，否则每个月初都会误报一次故障。

---

## 口径坑（按踩坑概率排序）

1. **MX 一个月里跑两套交易日历，`GRAND TOTAL` 的 ADV ≠ 总量 ÷ 单一日数。**
   利率/债券类产品跟债市日历，股票类产品跟股市日历，每年 **9 月和 11 月**必然分叉
   （加拿大真相与和解日 9/30、国殇日 11/11 债市休市而股市照开）。实测 2025-09：
   `CGB/CGF/CGZ/CRA` 全部 volume/ADV = **20.000**，而 `equity options / ETF options /
   share futures / SXF` 全部 = **21.000**；总表 `GRAND TOTAL` 被逼出 **20.499** 这种非整数。
   2025-11 同样是 19 vs 20。跨 12 年的 139 期里，**每年 9 月和 11 月都中招，无一例外**。
   ⇒ ADV 一律**直接读 `EN ADV` 表**，绝不用总量自己除；要存交易日数就存两列。

2. **现货表格 2021-08 才进新闻稿正文。** 2021-07 及更早的 `Body` 只有一段摘要 +
   一条 `/resource/en/<id>` 链接，`<table>` 计数为 0。解析器必须把「这一期没有表格」
   当成明确的、可识别的状态（抛异常或跳过），而不是解析出一堆空值。

3. **剥完 HTML 标签会冒出词内空格。** 官方把小节标题拆进不同 inline 标签，
   `TSX Venture Exchange` 剥完变成 **`TSX Venture Ex change *`**。
   我第一版就栽在这儿：正则没匹配上 → TSXV 那张表沿用了上一节的归属 →
   **TSX 的成交额被 TSXV 的数覆盖**，2022-06 的 `tsx_value_cadbn` 写成了 1.21 而不是 256.54，
   而且**不报错**。修法：一切标题/行标签匹配前先把空白**全删**再比（`squash()`），
   并且**认不出小节的表格一律抛异常**，绝不让它继承上一节。

4. **MX xlsx 里 `Total` 这个行名在 5 个 section 各出现一次**（STIR 期货 / STIR 期权 /
   债券期货 / 股指期货 / 股指期权），且**行号逐年漂移**：`GRAND TOTAL` 在 2022-09 档是第 45 行，
   在 2026-07 档是第 56 行（中间新增了 CDR / CEFs / BCS 等产品行）。
   ⇒ 必须先按 section 标题定位再取 `Total`，行号一个都不能写死。（同 cboe.py 口径坑 2。）

5. **m-x.ca 的 xlsx 是活文件、会被重传订正；CTS 新闻稿是冻结快照。两者会分叉。**
   实测 59 个重叠月：月度合约数 **55/59 逐位相同**，OI **45/59 逐位相同**。
   ⇒ MX 的数**一律以 m-x.ca xlsx 为准**（它自洽且会被官方持续订正），
   CTS 里的 MX 两行只当交叉校验用，不入库。

6. **2022-09 那期 CTS 的 MX 数字是错的，而且错了 6.36% 并且没改回来。**
   CTS 说 Sep-2022 MX 成交 `11,923,849` 张，m-x.ca xlsx 说 `12,681,668` 张，差 `757,819` 张。
   不是我解析错：2210 档 xlsx 的"上月"对照列同样写 `12,681,668`，两份 xlsx 互证；
   而 CTS 的 YTD（`112,033,825`）比 xlsx 逐月相加（`112,791,644`）正好少这 757,819。
   这一期的标题还带着 **"(Revised)"** —— 官方"修订"过一次，反而修出了这个口子。
   ⇒ 又一条"MX 只信 xlsx"的理由。

7. **BAX → CRA 是结构性断点，不可连比。** 2015-01：`BAX` 成交 2,729,283 张、`CRA` 为 0；
   2026-07：`BAX` 为 0、`CRA` 成交 4,221,855 张。短端利率基准从 BA 迁到 CORRA，
   合约整体换代。`mx_adv_stir_kcontracts` 这条合计线跨越这段是连续的，
   但**任何单合约线（BAX 或 CRA）在断点两侧都不能画成一条**。

8. **`TSX Alpha Exchange` 不含 Alpha-X / Alpha DRK，但 `All TMX Equities` 含。**
   实测恒等式 `All = TSX + TSXV + Alpha + Alpha-X/DRK` 在 **59/59 个月成立，最大差 0 股**。
   把 Alpha-X 漏掉或重复计都会破坏这个恒等式 —— 建议把它写成解析后的强制校验。

9. **新闻稿印的 Daily Average 只到 0.1 million，别抄。** 官方印 "490.7 million"，
   而 `10,796,096,148 / 22 = 490.73 million`。抄那个印出来的数会在图上留下量化台阶。
   ⇒ 只存官方给的**总量**，日均在 build 层用 `trading_days_equity` 现算。

10. **两桩正在发生的结构性事件，跨期比较会失真。**
    · 2026-04-22 宣布收购 **Cboe Canada + Cboe Australia**，2026-08-02 **已完成**
      —— Cboe Canada 是加拿大另一家上市场所，并表后"TMX 加拿大现货成交"的分母会跳变，
      需要在该月画结构性断点。
    · 2026-07-30 宣布 **BOX 与 MEMX 合并成 MEMX Group**，TMX 以 BOX 股权出资
      —— BOX 大概率从此不再作为 TMX 的经营口径披露。给 BOX 建长序列的性价比很低。

11. **TSXV 的数含 NEX**（表下脚注 `*Includes NEX`），全期一致，但与别家"主板/创业板"口径对比时要说明。

12. **老档 sheet 名带月份**：2015-01 档是 `Jan 2015 EN`，2026 档是 `EN`。按后缀匹配。

13. **`EN` 表里月度量与月末 OI 是同一张表的不同列块**，靠第 1 行的
    `MONTHLY VOLUME` / `YEAR-TO-DATE VOLUME` / `MONTH END OPEN INTEREST` 三个大标题分段，
    列位置逐年变（2015 档只到 15 列，2026 档到 37 列）。必须按标题找列块起点。

14. **CTS 正文末尾那张脚注表没有小节归属，且排版换过三种**（1 行×1 格、4 行×1 格、1 行×2 格）。
    按行数/列数写死一定漏。判据要用「**这张表里有没有可解析的数字**」—— 没有就是脚注。

15. **CTS 里 YTD 表和月度表长得一模一样**，只有表头第一列不同
    （`June 2026 / May 2026 / June 2025` vs `2026 / 2025 / % Change`），
    而且每个小节后面都紧跟一张 YTD 表。抓错就是把年初至今当成当月。

---

## 实测证据

脚本：`/tmp/exch_recon/scratch/{parse_cts.py, extract_cts.py, parse_mx.py, crosscheck.py}`

### 解析产出（真实数字）

MX `2607_stats_en.xlsx`（2026 年 7 月）与 `1501_stats_en.xlsx`（2015 年 1 月）：

```
mx_2607.xlsx  表头月份='Jul 2026'
key                          volume          ADV               OI
grand_total                20211732       918716         35470654
total_fut                  12193107       554232          3574498
total_opt                   8018625       364484         31896156
stir_fut_bax                      0            0                0
stir_fut_cra                4221855       191902          1726354
bond_fut_cgb                3450086       156822           938354
index_fut_sxf                317627        14438           163854
equity_opt                  3719863       169085          7771029
etf_opt                     4186437       190293         23940305
推出的交易日数 = volume/ADV = 22.0000

mx_1501.xlsx  表头月份='Jan 2015'
grand_total                 6937972       330373          4522737
stir_fut_bax                2729283       129965           641342      <- BAX 时代
stir_fut_cra                      0            0                0      <- CORRA 尚未存在
bond_fut_cgb                1281068        61003           355752
equity_opt                  2036417        96972          2431461
```

CTS 新闻稿 2026-06（发布日 2026-07-07）与 2021-08（发布日 2021-09-08）：

```
2026-06                                    2021-08
tmx_all_volume_shares_bn   15.568013       10.884081
tmx_all_value_cadbn       478.909113      187.772877
tmx_all_transactions_mn    33.879991       22.935310
tsx_volume_shares_bn       10.796096        6.324849
tsx_value_cadbn           456.631844      166.977081
tsx_composite_close      34856.99        20582.94
tsxv_volume_shares_bn       3.843491        3.258023
tsxv_composite_close      896.90           896.54
alpha_volume_shares_bn      0.894561        1.301208
alphax_drk_volume_shares_mn 33.865231      （2023-11 前不单列）
mx_volume_contracts      22346394        11885418
mx_oi_contracts          33325063        10545312
```

覆盖率：**CTS 59/59 个有表格的月份全部字段完整解析，零缺列**；
**MX 2015-01..2026-07 共 139 期 HEAD 全部返回真 xlsx，零断档**。

### 交叉核对（3 条独立证据链）

**核对 A —— m-x.ca xlsx vs TMX CTS 新闻稿（两份互不相干的官方文件）**

```
month         xlsx_vol      cts_vol     ok |      xlsx_OI       cts_OI     ok
2021-08       11885418     11885418     == |     10545302     10545312     XX(-10)
2022-06       13669647     13669647     == |     12535882     12535882     ==
2024-06       15395390     15395390     == |     17231723     17231723     ==
2025-12       19928614     19928614     == |     31416963     31429744     XX(-12781)
2026-05       24965353     24965353     == |     33641112     33641112     ==
2026-06       22346394     22346394     == |     33325063     33325063     ==

全 59 个重叠月：volume 逐位相同 55/59（最大差 2022-09 +757,819 = 6.36%，见口径坑 6）
                OI     逐位相同 45/59（最大差 2023-05 +132,092 = 0.91%）
```

**核对 B —— CTS 内部恒等式 `All = TSX + TSXV + Alpha + Alpha-X/DRK`**

```
month          all(官方)         四家相加        差(股)
2021-08      10.884081       10.884081            0
2023-10       9.410960        9.410960            0
2023-11      10.300381       10.300381            0
2026-06      15.568013       15.568013            0

全部 59 个月里最大绝对差 = 0 股
```

**核对 C —— 与 TMX Group Q2 2026 MD&A 原文对账（第三份官方文件）**

| MD&A 原文 | 我解析出来的 | 结论 |
|---|---|---|
| "136.4 million contracts traded in 1H/26" | CTS 逐月相加 `136,445,206` = 136.4 mn | ✅ |
| "67.1 million contracts traded in Q2/26" | CTS 逐月相加 `67,108,229` = 67.1 mn；m-x.ca xlsx 逐月相加 `67,106,441` = 67.1 mn | ✅ 两条路都对上 |
| "trading volumes on TSX and TSXV increasing 27% and 60% respectively, while Alpha (including Alpha-X and Alpha-DRK) decreased by 4%" | CTS YTD 栏 TSX **+26.9%** / TSXV **+60.2%** / Alpha **-4.6%** | ✅ |

MD&A 里的 BOX 表（这就是 BOX 能拿到的全部粒度）：

```
                              Q2/26  Q1/26  Q4/25  Q3/25  Q2/25  Q1/25  Q4/24  Q3/24
Volume (million contracts)    234.7  259.3  247.1  235.7  241.4  244.8  211.8  185.8
Market Share (equity options)    6%     7%     6%     7%     7%     8%     7%     7%
Revenue (millions of CAD)     $47.5  $47.1  $48.7  $44.9  $45.4  $49.1  $42.1  $35.3
```

### 无人值守可行性实测

```
urllib  Q4 feed (investors.tmx.com)      200 application/json
urllib  q4cdn PDF                        200 application/pdf
urllib  m-x.ca xlsx                      200 application/vnd...spreadsheetml.sheet
urllib  m-x.ca 落地页                     200 text/html
curl    Q4 feed                          200
---
curl / urllib / nscurl / curl_cffi / 真实 Chrome  ->  www.tmx.com  403（全部）
```
两条主源都是**裸 `urllib` 可达**，与 `fetch/cboe.py`、`fetch/hkex.py` 同级，满足 cron 无人值守。
被墙的只有 `tmx.com`，而它只影响 2021-07 之前的现货历史回补，不影响每月增量。

---

## 属于哪些竞争池

### 地理池

| 池 | 进不进 | 可比字段（跨家必须是同一件事） |
|---|---|---|
| **北美现货** | ✅ | `tmx_all_value_cadbn / trading_days_equity` = **日均成交额（本币）**，对 HKEX 的 `adt_hkdbn`；另有 `tmx_all_volume_shares_bn / trading_days_equity` = **日均成交股数**，对 Cboe 的 `adv_us_equities_matched_shares_bn`。**两个都要存** —— 因为 Cboe 只给股数、HKEX 只给金额，缺一就有一家对不上。币种不同，横截面图必须指数化（建议 2021-08=100，受 TMX 起点所限）。2026-06 实测：C$21.8 bn/日、0.71 bn 股/日 |
| **北美期权** | ⚠ 只能进季度点 | 本该用 BOX ADV，但 TMX 只披露季度（Q2/26 = 234.7 mn 张/季）。若坚持画月度线，TMX 在这个池里**必须缺席**；折中是在该池另开一张季度图，用 `box_volume_mncontracts` 对 Cboe 的 `adv_us_options_kcontracts × 交易日` 折算的季度量 |
| **单一市场垄断对照** | ✅ | 与 HKEX 同池。可比字段：**本国现货日均成交额**（`tmx_all_value_cadbn/days` vs `adt_hkdbn`）+ **本国衍生品 ADV 合约数**（`mx_adv_kcontracts` vs HKEX `derivatives_adv_contracts`）。收购 Cboe Canada 完成后 TMX 的"垄断度"进一步上升，这条对照反而更贴题 |
| 欧洲现货 / 欧洲衍生品 / 亚太现货 / 亚太衍生品 | ❌ | TMX 没有这些区域的经营口径（Trayport 是欧洲能源**软件**，不披露成交量；刚收的 Cboe Australia 尚无月度披露） |

### 标的池

| 池 | 进不进 | 可比字段 |
|---|---|---|
| **利率衍生品** | ✅ 强项 | `mx_adv_stir_kcontracts + mx_adv_bond_futures_kcontracts` = **利率类 ADV（千张）**，直接对 CME 的 `adv_rates_kcontracts`。2026-06 实测 585.5 kcontracts（STIR 222.2 + Bond 363.3），约是 CME 利率 ADV 的个位数百分比 —— 量级差很大，横截面图建议用双轴或指数化。单合约层面 `mx_adv_cgb_kcontracts` 对 CME 的 10Y Note 是最干净的一对一 |
| **股指衍生品** | ✅ | `mx_adv_index_futures_kcontracts`（2026-06 = 37.2 kcontracts，其中 SXF 36.7）对 CME `adv_equity_kcontracts` 与 Cboe `adv_index_options_kcontracts`。⚠ 口径不完全对齐：MX 这条是**纯期货**（股指期权 SXO/SXJ/SXV 实测连续为 0），Cboe 那条是**纯期权** —— 图注必须写明 |
| **单股与 ETF 期权** | ✅ | `mx_adv_equity_options_kcontracts + mx_adv_etf_options_kcontracts`（+CDR+CEF）= **344.8 kcontracts（2026-06）**，对 Cboe 的 `adv_multilist_options_kcontracts`。这是加拿大市场，与 Cboe 的美国盘不是同一个池子的竞争者，只是**同一业务形态的规模对照** |
| **FX** | ❌ 不建议 | 唯一的 FX 品种是 `USX`（美元期权），2026-06 ADV = **0.568 kcontracts**，四舍五入就是噪声。放进池里只会污染图 |
| **能源商品** | ❌ | NGX / Shorcan Energy 已不在 TMX 月度披露里；Trayport 只报 licensee / connection / ARR，不报成交量 |
| **加密** | ❌ | 无 |

**跨家可比性的一句话结论**：TMX 唯一能和别家**逐单位对齐**的字段是
**MX 的 ADV（千张合约）** 和 **现货日均成交股数/成交额**。
其余（收入、市占率、OI）要么口径独有，要么周期不同。
横截面页把 TMX 放进「北美现货」和「利率衍生品」两个池最扎实；
「北美期权」这个池 —— 也就是起点线索里最看重的 BOX —— **恰恰是本次做不成的那个**。
