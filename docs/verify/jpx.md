# JPX（日本取引所グループ / Japan Exchange Group）数据源可行性侦察

侦察日期：2026-08-06　|　slug：`jpx`　|　全部结论均来自本机实测，脚本在 `/tmp/exch_recon/scratch/jpx/`

---

## 判定

**A（可直接实现）**

理由：

- 全部字段来自 **JPX 官方统计站与 JPX 自己的 IR 决算资料**，不碰任何第三方聚合商，满足仓库硬约束。
- **无人值守零障碍**：`www.jpx.co.jp` 没有 Cloudflare / Akamai 挑战、没有 JS 渲染门、没有登录墙。
  实测 Python `urllib` **连 User-Agent 都不设**（默认 `Python-urllib/3.x`）也是 200，
  7 个目标 URL 全部通过，0.3–2.3s；`HEAD` 请求可用且返回 `Last-Modified`，
  可以零流量探新鲜度。`robots.txt` 是 `Disallow:`（空，全站放行）。
  **完全不需要 nscurl / curl_cffi / 浏览器登录态。**
- **历史深度远超要求**：现货成交额/量回溯到 **1985-01**（498 个月无断档），
  时价总额回溯到 **1949-05**，衍生品回溯到 **1985-10**（489 个月无断档）。
- **交叉核对全过**：与两条完全独立的发布管道对上——官方 Monthly Statistics Report PDF
  （25 个月逐月，相对偏差 1e-8 量级）与 JPX 决算说明资料（10 个数值，全部落在 IR 自己的四舍五入位内）。
- 每个统计落地页都有机器可读的 `<div class="JPX-site-update">Update : Jul. 07, 2026</div>`
  ——**官方自述发布日**，比 HKEX 只能拿 `Last-Modified` 强，`source_dates.csv` 有权威来源。

不判 B 的原因：下面「口径坑」那一节确实有 9 条，但**没有一条需要降级方案或人工介入**，
全部是确定性的、可在解析层写死的规则。坑的数量与 `fetch/cboe.py` 的 9 条同级。

唯一需要在**画图层**（不是抓取层）做决策的是：JPX 的原始合约张数因为
mini（1/10）与 micro（1/100）两档小合约而**无法直接与 CME / HKEX 的张数对比**
（2026-06 micro 一个产品就占了总张数的 44%）。解法是同时入库「大合约当量 ADV」
与「日均名义金额」两列，见「竞争池」一节。

---

## 数据源

全部走 `https://www.jpx.co.jp`，英文站。5 个主文件 + 2 个核对文件。

### 主数据（入 series/jpx.csv）

| # | 用途 | URL | 格式 | 抓取方式 |
|---|---|---|---|---|
| 1 | 衍生品逐产品 ADV / 月末 OI | `https://www.jpx.co.jp/automation/markets/statistics-derivatives/trading-volume/files/soukatsu_M.xlsx` | xlsx 2.2 MB | **稳定直链**，无月份 token，可写死 |
| 2 | 衍生品**总量与三大类小计** | `https://www.jpx.co.jp/english/markets/statistics-derivatives/trading-volume/{token}-att/tv_ts{YYYYMM}.xls` | xls(BIFF) 1.65 MB | token **每月变**，必须先抓落地页 `…/statistics-derivatives/trading-volume/index.html` 取 href |
| 3 | 现货股票成交量/额 | `https://www.jpx.co.jp/english/markets/statistics-equities/misc/tvdivq0000000vzk-att/historical-genbutsu.xlsx` | xlsx 142 KB | token 目录**固定**，文件每月原地覆盖 |
| 4 | ETF / ETN / REIT 成交量额 | `https://www.jpx.co.jp/english/markets/statistics-equities/misc/tvdivq0000000vzk-att/historical-toushin.xlsx` | xlsx 44 KB | 同上（与 #3 同目录） |
| 5 | 月末时价总额 | `https://www.jpx.co.jp/english/markets/statistics-equities/misc/tvdivq0000001w3y-att/historical-jika.xlsx` | xlsx 73 KB | token 目录**固定**，原地覆盖 |

> #2 是**必需的，不能省**：#1 的长表只收录「当前仍在挂牌」的产品，历史上退市的产品
> （日経300 先物、業種別先物、Nifty50、取引所 FX 证拠金…）整条不在里面。实测
> 「按 #1 逐产品求和 == #2 官方 Total」这条闭合式，**只有 2023-06 起才成立**；
> 489 个月里有 452 个月不闭合。本仓要 2015/2016 起，所以 Total 与三大类小计只能取 #2。

### 可选主数据（外资流向，日股独有）

| 用途 | URL | 备注 |
|---|---|---|
| 投資部門別売買状況（月次） | `…/statistics-equities/investor-type/{token}-att/stock_val_1_m{YYMM}.xls`（金额）与 `stock_vol_1_m{YYMM}.xls`（数量） | 落地页 `…/investor-type/00-01.html`，token 每月变；档案回溯到 2016 |

### 交叉核对用（不入库，只作证）

| 用途 | URL |
|---|---|
| 官方 Monthly Statistics Report「2-1 売買高・売買代金」 | `…/statistics-equities/monthly/{token}-att/02_baibai{YYMM}.pdf` |
| JPX 决算说明资料（IR，独立管道） | `https://www.jpx.co.jp/english/corporate/investor-relations/tvdivq000000lbh5-att/E_EM_JPX_Q1FY{YYYY}.pdf` |

### 抓取方式

```python
req = urllib.request.Request(url, headers={'User-Agent': UA})   # UA 可省，写上是零成本保险
urllib.request.urlopen(req, timeout=60).read()
```

依赖：`openpyxl`（读 #1/#3/#4/#5 的 xlsx）+ **`xlrd`**（读 #2 与投資部門別的老式 `.xls` BIFF，
openpyxl 读不了）+ `PyMuPDF`（仅核对 PDF 时用，生产不需要）。

---

## 可提取字段

照 `series/cboe.csv` 风格，列名带单位后缀。以下 26 列已**全部实测产出**
（`/tmp/exch_recon/scratch/jpx/jpx_preview.csv`，489 行 1985-10 … 2026-06）。

| 列名 | 口径说明 |
|---|---|
| `month` | `YYYY-MM` |
| `trading_days` | 该月立会日数（东证口径）。衍生品的立会日数在个别月与现货不同，本列取现货表 |
| `adt_cash_total_jpytn` | **东证现货日均成交额，兆円/日**。= 内国株 + 外国株 + 内国ETF + 外国ETF/ETN + 内国投資証券(REIT)。**这是 JPX IR 自己「Cash Equities ADT」的口径**，已实测对上（见下） |
| `adt_cash_stocks_jpytn` | 上面里只算股票（内国 + 外国）的部分 |
| `adt_cash_etfreit_jpytn` | 上面里 ETF/ETN/REIT 的部分。2026-06 = 0.72 兆円/日，占总额 5.1%，不可省 |
| `adv_cash_shares_mn` | 内国株日均成交**股数**，百万株/日 |
| `mktcap_eom_jpytn` | 月末时价总额（Prime+Standard+Growth+PRO 合计），兆円 |
| `adv_deriv_total_kcontracts` | JPX 衍生品日均成交**总张数**，千张/日。取 #2 的「合計 Total」列 ÷ 立会日数。**跨所比较前先读「口径坑 1」** |
| `adv_deriv_index_kcontracts` | 同上，「株価指数関連等 Stock index related」大类 |
| `adv_deriv_rates_kcontracts` | 同上，「国債・金利関連 Government bond and Interest rate related」大类 |
| `adv_deriv_cmdty_kcontracts` | 同上，「商品関連 Commodity related」大类（旧 TOCOM 品种） |
| `adnv_deriv_total_jpytn` | 衍生品**日均名义成交金额**，兆円/日。**这是唯一不受合约乘数扭曲的跨所可比量** |
| `adv_n225_futures_kcontracts` | 日経225先物（大型合约）ADV，千张/日 |
| `adv_n225_mini_kcontracts` | 日経225 mini ADV，千张/日 |
| `adv_n225_micro_kcontracts` | 日経225マイクロ先物 ADV，千张/日（2023-05 起才有） |
| `adv_n225_lgeq_kcontracts` | **日経225 复合体大合约当量 ADV** = 大型 + mini/10 + micro/100，千张/日。**JPX IR 报表用的就是这个口径**，已实测对上 |
| `adv_topix_futures_kcontracts` | TOPIX 先物（大型）ADV |
| `adv_minitopix_futures_kcontracts` | ミニTOPIX 先物 ADV |
| `adv_n225_options_kcontracts` | 日経225オプション ADV（Put+Call 合计） |
| `adnv_n225_options_jpybn` | 日経225オプション**日均权利金成交金额**，十亿円/日。IR 报表用这个而不是张数 |
| `adv_jgb10y_futures_kcontracts` | 長期国債（10年 JGB）先物 ADV |
| `adv_secoptions_kcontracts` | 有価証券オプション（个股/ETF 期权）ADV |
| `oi_n225_futures_contracts` | 月末未平仓，**张（不是千张）**，与 `series/cme.csv` 的 `oi_*_contracts` 同量纲 |
| `oi_n225_mini_contracts` | 同上 |
| `oi_topix_futures_contracts` | 同上 |
| `oi_n225_options_contracts` | 同上 |
| `oi_jgb10y_futures_contracts` | 同上 |

**可选第二张表**（外资流向，建议单独 `series/jpx_investor_flow.csv`，理由见「口径坑 9」）：

| 列名 | 口径说明 |
|---|---|
| `month` | `YYYY-MM` |
| `survey_period` | 官方调查期字符串，如 `06/01-06/26`——**不是日历月**，必须入库 |
| `net_foreign_prime_jpybn` | 海外投資家 Prime 净买入（買い−売り），十亿円。负数=净卖出 |
| `net_individual_prime_jpybn` | 個人 净买入 |
| `net_trust_prime_jpybn` | 投資信託 净买入 |
| `net_bizcorp_prime_jpybn` | 事業法人 净买入（自社株买回的代理指标） |
| `foreign_share_pct` | 海外投資家占委託成交额比重（2026-06 Prime = 64.7%） |

**不建议入库**：新規上場社数 / IPO 募资额。JPX 的 New Listings 页
（`/english/listing/stocks/new/index.html`）是逐个发行人的 HTML 表格、档案只到 2022、
且不给募资额汇总；月度社数只在 Monthly Statistics Report 的第 16 张 PDF 里。
要做 HKEX 那样的 `new_listings` / `ipo_funds_hkdbn` 对照，成本远高于其它列，
建议第一版先不做，需要时单独立项。

---

## 历史深度

实测（不是页面宣称，是解析出来数月份数的结果）：

| 序列 | 最早 | 最新 | 月份数 | 断档 |
|---|---|---|---|---|
| 现货成交量/额（`historical-genbutsu.xlsx`） | **1985-01** | 2026-06 | 498 | **无** |
| ETF/ETN/REIT（`historical-toushin.xlsx`） | 1995-01（1995-05 起才有数） | 2026-06 | — | 无 |
| 时价总额（`historical-jika.xlsx`） | **1949-05** | **2026-07** | 875+51 | 无 |
| 衍生品总量与大类（`tv_ts202606.xls`） | **1985-10** | 2026-06 | 489 | **无** |
| 投資部門別（月次档案页） | 2016-01 | 2026-06 | — | 无（档案选择器 2016–2026） |

**逐产品序列的起点各不相同**（`soukatsu_M.xlsx` 实测）：

| 产品 | 最早月 |
|---|---|
| 10年 JGB 先物 | 1985-10 |
| TOPIX 先物 | 1988-09 |
| TOPIX オプション | 1989-10 |
| 有価証券オプション | 1997-07 |
| ミニTOPIX / TOPIX Core30 / 東証REIT 先物 | 2008-06 |
| **日経225 先物 / mini / オプション / TOPIX 以外的 OSE 品种** | **2014-12** |
| 東証グロース市場250 先物 / TAIEX / FTSE China 50 | 2016-07 |
| 商品（旧 TOCOM 全部） | 2020-07 |
| 日経225マイクロ / 日経225ミニオプション / 3M TONA | 2023-05 |

⇒ **本仓要的 2015/2016 起点全部满足**，日経225 复合体从 2014-12 起可用（比 2015 还早一个月）。
唯一要接受的是：日経225 相关序列**不能**回到 2014-12 之前——那是 OSE 与 TSE 衍生品市场
整合（2014-03-24）留下的分界，官方长表就是从那里开始的。TOPIX / JGB 系不受影响。

---

## 发布节奏

每条都同时有**官方明文规则**与**实测 `Last-Modified`**，两者一致。

| 文件 | 官方明文（页面 Note 原文） | 实测 Last-Modified（换算 JST） |
|---|---|---|
| `soukatsu_M.xlsx` / `tv_ts{YYYYMM}.xls` | "Updated at approximately **10:00 a.m. on the 5th business day** of each month." | 2026-07-07 10:00:22 JST（7 月第 5 个营业日：1、2、3、6、**7**）✓ |
| `historical-genbutsu.xlsx` / `historical-toushin.xlsx` | "Updated at approximately **1:00 p.m. on the 5th business day** of each month." | 2026-07-07 13:00:22 JST ✓ |
| `historical-jika.xlsx`（时价总额） | "Updated at approximately **1:00 p.m. on the 1st business day** of each month." | 2026-08-03 13:00:20 JST，且**已含 2026-07** ✓ |
| Monthly Statistics Report PDF | "Updated at approximately **9:00 a.m. on the 21st** of each month." | `02_baibai2606.pdf` = 2026-07-21 09:00:33 JST ✓；`02_baibai2601.pdf` = 2026-02-24（21 日周六、23 日天皇誕生日顺延）✓ |
| 投資部門別（月次） | "…on the day when data of the final week of the last month is posted."（挂在周次循环上） | `stock_val_1_m2606.xls` = 2026-07-02 15:30 JST |

⇒ **调度建议**：闸门开在**次月第 3 日**（`monthly_run.py` 的 `EARLY = 5` 天提前量已足够覆盖
第 5 个营业日最晚落在 8 日的情形）。2026-08-06 实测时最新月仍是 **2026-06**——
7 月数据要等 **2026-08-07**（8 月第 5 个营业日）。这不是故障，`latest_month()` 应如实返回 `2026-06`。

**注意跨文件节奏错位**：时价总额（第 1 个营业日）比成交额（第 5 个营业日）**早 4 天**。
所以 `historical-jika.xlsx` 里会先出现一个只有 mktcap、没有 ADT 的月份
（实测：2026-08-06 当天 jika 已有 2026-07，genbutsu 还停在 2026-06）。
`latest_month()` **必须以成交额文件为准**，否则会建出一整行只有 mktcap 的空行。

### source_dates 溯源

JPX 的落地页有 Cboe 那种「自述发布日」，而且是稳定的 DOM 结构：

```html
<div class="JPX-site-update">
        Update : Jul. 07, 2026
</div>
```

正则 `Update\s*[:：]\s*([A-Z][a-z]{2}\.?\s+\d{1,2},\s*\d{4})`，实测三个落地页全部命中，
且与该页所挂文件的 HTTP `Last-Modified` **同日**（衍生品页 Jul. 07 / 文件 07-07；
时价总额页 Aug. 03 / 文件 08-03）。两条独立证据互证。

⇒ `evidence` 字段建议写成：
`"落地页 …/statistics-derivatives/trading-volume/index.html 的 <div class=\"JPX-site-update\"> \"Update : Jul. 07, 2026\"；soukatsu_M.xlsx HTTP Last-Modified: Tue, 07 Jul 2026 01:00:22 GMT（= 07-07 10:00 JST）互证"`

**只在首次摄入某月时记一笔，事后不覆盖**——这几个文件都是**原地覆盖式**发布
（同一 URL 每月换内容），下个月再看 `Last-Modified` 就是下个月的日子了。

---

## 口径坑（按踩坑概率排序）

1. **合约张数跨所不可比：mini = 1/10、micro = 1/100。**
   日経225 有三档合约乘数。实测 2026-06：micro 单产品 ADV 1,040k 张，占 JPX 全所总张数
   2,366k 的 **44.0%**；mini 再占 33.5%。把 `adv_deriv_total_kcontracts` 直接和 CME 的
   `adv_total_kcontracts` 并排画柱，等于宣称 JPX 衍生品规模在 2023-05（micro 上市）
   一夜之间翻倍——那是合约拆细，不是成交增长。
   micro 上市前后：2023-04 总 ADV 1,207k → 2023-06 2,039k，其中 micro 从 0 到 55k
   （之后一路涨到 2026-06 的 1,040k）。
   ⇒ 跨所对比一律用 `adv_n225_lgeq_kcontracts`（大合约当量，**JPX IR 自己的口径**）
   或 `adnv_deriv_total_jpytn`（名义金额）。原始张数只用于 JPX 自身的时序图，
   且要在 2023-05 画结构性断点。

2. **现货 2022-04 那一行被劈成两张 sheet，必须相加。**
   `historical-genbutsu.xlsx` 的 `月間 monthly (旧 Old)` 覆盖 1985-01…**2022-04**
   （旧市场区分：一部/二部/マザーズ/JASDAQ），`月間 monthly` 覆盖 **2022-04**…至今
   （新区分：Prime/Standard/Growth/PRO）。2022-04-04 市场重组，
   旧表那一行**只有 1 个立会日**（4/1），新表那一行有 20 个（4/4–4/28）。
   只读新表 → 2022-04 的成交额少掉 4/1 那天且 `trading_days` 写成 20；
   只读旧表 → 少掉整整 20 天。实测相加后 = 21 个立会日、日均 3.42 兆円，与官方 PDF 一致。
   ⇒ 同时读两张表，同月相加；并在 2022-04 画结构性断点（段别口径从此不可比，
   但**合计口径连续**——官方 PDF 表注明说合计列 2022-04-01 及之前是旧六段之和）。

3. **英文列名会撞车，一律按日文名定位。**
   `tv_ts{YYYYMM}.xls` 里 `TOPIX Options` 出现 **4 次**、`Security Options` 出现 **5 次**、
   `JPX-Nikkei Index 400 Options` 4 次。原因是表尾有一段 Flex Options 的
   **`【うち…】`（of which）明细列**，英文名与正牌产品完全同名。
   第一版按英文名建字典，TOPIX Options 整条被 Flex 的 0 覆盖，
   2024 年三个月凭空「归零」。日文名带 `【うち` 前缀，天然唯一。
   ⇒ 按日文名（第 9 行合并单元格）定位；且**求和时必须排除所有 `【うち` 开头的列**，
   否则重复计数。实测排除后「逐产品和 == 官方 Total」在 **489/489 个月**上成立。

4. **`soukatsu_M.xlsx` 只收录当前挂牌产品，历史总量凑不齐。**
   长表 95 条产品序列，宽表 119 个产品列——差的是已退市品种（日経300 先物、業種別先物、
   S&P/TOPIX150、取引所 FX 证拠金、Nifty50…）。实测「长表逐产品求和 == 宽表 Total」
   **只有 2023-06 起成立**（489 个月里 452 个月不闭合；2023-05 差 79,401 张、
   2015-01 差 2,067,619 张）。
   ⇒ Total 与三大类小计**必须**取宽表 `tv_ts`，不能省掉那次带 token 的抓取。

5. **日経225オプション在 2015-05…2023-05 两个文件口径不同。**
   官方在落地页写明："Data for Nikkei 225 Options from May 2015 to May 2023 includes data
   for Nikkei 225 Weekly Options."——这句只对**宽表**成立。实测：
   2022-10 宽表 2,337,244 / 长表 2,228,089（差 109,155）；
   2022-12 差 109,007；2023-03 差 132,550；**2023-06 起两表逐格相同**
   （週次オプション 2023-05 改称「日経225ミニオプション」独立成列）。
   ⇒ `adv_n225_options_kcontracts` 取长表（不含週次）可得连续口径；
   若取宽表，须在 2015-05 与 2023-06 各画一条断点。本文建议取长表。

6. **2020-07 商品品种是半个月。**
   旧 TOCOM 品种 2020-07-27 迁入 OSE。长表 `soukatsu_M` 的 2020-07 行**只含迁入后那 4 天**
   （金標準先物 192,067 张），宽表含整月（566,228 张）；**2020-08 起两表完全相同**。
   ⇒ `adv_deriv_cmdty_kcontracts` 取宽表；且 2020-07 这一格要么按半月标注、
   要么直接留空——按整月日均算会低估 66%。

7. **官方明说会重述，但实测没重述过。**
   两个 vintage 对照：`02_baibai2601.pdf`（2026-02-24 发）vs `02_baibai2606.pdf`（2026-07-21 发），
   重叠 **20 个月（2024-06…2026-01）逐字节完全相同**，与今天的 xlsx 也只差
   1–4 百万円的四舍五入残差。
   ⇒ 现货序列很稳，但仍照仓库惯例**已有值永不覆盖、只填空**。
   Monthly Statistics Report 页面自己有 "Revision Information" 页和 `*` 重述标记，
   真要盯重述应该盯那个页面而不是靠比对。

8. **单位陷阱，三处。**
   (a) TOKYO PRO Market 段在现货表里是 **株 / 千円**，其余段是 **千株 / 百万円**——
   混用会让 PRO 的成交额被放大 1000 倍。
   (b) 衍生品 OI 是**张**，ADV 建议存千张——两者差 1000 倍，与 `series/cme.csv` 同坑。
   (c) 投資部門別文件的单位藏在 `r4 c10` 的 `'千円,%  1,000 yen, %'`，是**千円**。

9. **投資部門別的「月度」不是日历月，而且是双边计数。**
   实测 2026-06 那份文件抬头写 `06/01～06/26`——官方按**完整调查周**汇总，
   6/29、6/30 两个交易日被推到 7 月那份里。同时「総売買代金」是**売り+買い 双边合计**
   （518,960,251,400 千円 = 518.96 兆円 ≈ Prime 单边 285.4 兆 × 2 × 20/22 个交易日）。
   ⇒ 绝对不能和 `adt_cash_*` 放进同一张 CSV 做除法。建议单独一张表，
   并把 `survey_period` 原文入库；只用净买入（差引き Balance）这一列，
   净额不受双边计数影响。

---

## 实测证据

### 脚本清单（`/tmp/exch_recon/scratch/jpx/`）

| 文件 | 作用 |
|---|---|
| `parse_equities.py` | 解析 `historical-genbutsu.xlsx`（新旧两 sheet 合并） |
| `parse_deriv.py` | 解析 `soukatsu_M.xlsx`（长表）与 `tv_ts202606.xls`（宽表） |
| `xcheck_equities.py` | 现货 xlsx vs 官方 Monthly Statistics Report PDF |
| `xcheck_ir.py` | vs JPX 决算说明资料（独立管道） |
| `xcheck_deriv.py` / `diag.py` | 衍生品两版式互对 + 三处不符的定位 |
| `robust.py` | urllib / 无 UA / HEAD / robots 实测 |
| `build_series.py` | 产出 `jpx_preview.csv`（489 行 × 26 列） |

已下载的期次：`soukatsu_M.xlsx`、`tv_ts202606.xls`、`historical-genbutsu.xlsx`、
`historical-toushin.xlsx`、`historical-jika.xlsx`、`inv_val_m2606.xls`、
`02_baibai2606.pdf`（**2026-07-21 期**）、`02_baibai2601.pdf`（**2026-02-24 期**，第二个 vintage）、
`E_EM_JPX_Q1FY2026.pdf`。

### 解析出的真实数字

**现货（`adt_cash_*`，兆円/日；`mktcap`，兆円）**

```
month     days   ADT合计   =  股票    + ETF/REIT   月末时价总额
2026-06    22    14.0845     13.3652    0.7193      1384.75
2026-05    18    13.2900     12.7291    0.5609      1377
2026-04    21     9.8500      9.3302    0.5198      1293
2026-03    21    10.2200      9.5740    0.6460      1213
2026-02    18    10.9100     10.3403    0.5697      1372
2026-01    19     8.5680      8.0545    0.5135      1247
2025-06    21     5.8961      5.6039    0.2922      1012.61
2022-04    21     3.4210        —          —         711.63   <- 两 sheet 相加
2016-06    21     2.9378      2.6035    0.3343       480.69
```

**衍生品（千张/日；OI 为张）**

```
month     ADV总  其中mini  其中micro  micro占比  大合约当量  日均名义(兆円)
2026-06    2366     793      1040      44.0%      166.8       26.97
2026-05    1926     676       869      45.1%      123.5       16.99
2025-06    1513     607       409      27.1%      133.1       17.06
2023-06    2039    1268        55       2.7%      262.7       20.71
2023-04    1207     855         0       0.0%      142.3        8.71
2019-06    1651     994         0       0.0%      219.7       16.62
2016-06    1572     924         0       0.0%      228.1       11.70

月末 OI（张）  N225fut   N225mini  TOPIXfut  N225opt    JGB10y
2026-06        178,611   235,305   408,960    765,660   179,884
2025-06        202,196   298,504   390,656    774,417   148,007
2019-06        331,380   337,642   522,529  1,809,538   105,023
```

### 交叉核对 1 —— vs 官方 Monthly Statistics Report PDF（25 个月逐月）

PDF 表 2-1 的「合計」= 内国株 + 外国株（表注明说），所以对账式是
`PDF_total == xlsx_domestic + xlsx_foreign`。

```
month       PDF_val_total     xlsx_dom+for     diff   xlsx_foreign   日均ADT一致?
2026-06         294034079        294034076        3          2060        YES
2026-05         229123829        229123826        3          2424        YES
2026-03         201055027        201055024        3          2372        YES
2025-10         173529164        173529163        1          1936        YES
2024-06          98000426         98000425        1          1138        YES
… 共 25 个月（2024-06 … 2026-06），diff 全部在 1–4 百万円之间
```

残差来源已定位到分（不是「大概是舍入」）：xlsx 把内国、外国**各自**四舍五入到百万円后分别存，
PDF 先加后舍。逐段验证 2026-06：

```
             xlsx内国        + 外国    = 合计        PDF列
Prime      285,399,572   +      13   = 285,399,585   285,399,586
Standard     4,560,708   +     801   =   4,561,509     4,561,509  ✓
Growth       4,071,586   +   1,246   =   4,072,832     4,072,833
TOKYO PRO      150.301（千円换算）                            150
TradingDays         22                                        22  ✓
```

相对偏差 **2.7 / 294,034,079 = 9.2e-9**。同时 PDF 的「1日平均」列与
`(dom+for)/trading_days` 在 25 个月上全部一致（容差 ≤1 百万円）。

### 交叉核对 2 —— vs JPX 决算说明资料（**完全独立的发布管道**）

`E_EM_JPX_Q1FY2026.pdf` 第 5 页由 JPX **公司 IR** 于 2026-07-28 发布；
上面的统计文件由 **TSE / OSE 数据服务部**于 2026-07-07 发布。两条管道、两批人、两个日期。
JPX 财年 3 月结束，Q1 = 4–6 月。IR 那页脚注写明 mini / micro 按 1/10、1/100 折算。

```
══ Cash Equities 季度 ADT（兆円/日）══
quarter        内国株   外国株    ETF等    REIT   合计ADT   IR公布   偏差
Q1FY2026       11.788  0.0001    0.546   0.058   12.392    12.39   +0.01%
Q1FY2025        5.675  0.0004    0.285   0.049    6.009     6.01   -0.02%

══ 衍生品季度 ADV（万张/日）══
quarter    product                              算得    IR公布    偏差
Q1FY2026   TOPIX Futures (Large)                9.23      9.2     +0.3%
Q1FY2026   Nikkei225 Fut 含 mini/micro         13.51     13.5     +0.1%
Q1FY2026   10-year JGB Futures                  5.24      5.2     +0.8%
Q1FY2026   Nikkei225 Options（十亿円/日）       44.47     44.5     -0.1%
Q1FY2025   TOPIX Futures (Large)                8.77      8.8     -0.3%
Q1FY2025   Nikkei225 Fut 含 mini/micro         14.96     15.0     -0.3%
Q1FY2025   10-year JGB Futures                  4.27      4.3     -0.7%
Q1FY2025   Nikkei225 Options（十亿円/日）       27.26     27.3     -0.1%
```

**10 个数值全部落在 IR 自己的有效数字位内**（IR 只印 2–3 位有效数字）。
这一步同时**定死了两件事**：`adt_cash_total` 必须含 ETF/REIT（不含就是 11.79 vs 12.39，差 4.9%）；
`adv_n225_lgeq` 的 1/10 与 1/100 折算系数是官方口径。

### 交叉核对 3 —— 两个 vintage 的重述检验

```
Jan-2026 期 PDF（2026-02-24 发） vs Jun-2026 期 PDF（2026-07-21 发）
重叠 20 个月（2024-06 … 2026-01），逐字节相同 20 个月，CHANGED 0 个月
```

### 交叉核对 4 —— 衍生品两版式互对与口径闭合

```
1) 产品级成交量逐格对账（2015-01 起）：比对 2961 格
   按英文名匹配 → 不符 230 格（全部是「口径坑 3」的列名撞车 + 坑 5/6 的口径差）
   按日文名匹配并扣除已知口径差后 → 不符 0 格
2) 长表自洽 ADV x days == vol：偏差全部来自官方把日均四舍五入到整数张
3) 逐产品和 == 官方 Total：排除【うち】列后，489/489 个月成立（diff 恰为 0）
4) 长表逐产品和 == 官方 Total：仅 2023-06 起成立（见口径坑 4）
```

### 无人值守实测

```
== A) python urllib，带 Chrome UA ==
  landing_deriv        200        27,996 B  Last-Modified Tue, 07 Jul 2026 01:00:20 GMT  0.52s
  landing_misc         200        79,056 B  Tue, 07 Jul 2026 04:00:22 GMT                0.42s
  automation_soukatsu  200     2,248,093 B  Tue, 07 Jul 2026 01:00:22 GMT                1.33s
  genbutsu             200       141,922 B  Tue, 07 Jul 2026 04:00:22 GMT                1.33s
  jika                 200        73,491 B  Mon, 03 Aug 2026 04:00:20 GMT                2.29s
  tv_ts                200     1,654,272 B  Tue, 07 Jul 2026 01:00:20 GMT                1.18s
  ir_pdf               200       424,147 B  Tue, 28 Jul 2026 03:03:17 GMT                0.59s

== B) python urllib，**完全不设 UA**（默认 Python-urllib/3.x）==
  7 个 URL 全部 200，字节数与 A 完全相同，0.28–1.26s
  ⇒ 没有 UA 校验、没有 TLS 指纹（JA3）拦截、没有 Cloudflare/Akamai 挑战

== C) HEAD 请求 ==
  automation_soukatsu  200  0.34s  Last-Modified=Tue, 07 Jul 2026 01:00:22 GMT
  genbutsu             200  0.37s  Last-Modified=Tue, 07 Jul 2026 04:00:22 GMT
  jika                 200  0.35s  Last-Modified=Mon, 03 Aug 2026 04:00:20 GMT
  ⇒ 可用 HEAD 零流量探新鲜度，不必每天拉 2.2 MB

== D) robots.txt ==
  User-Agent:*
  Disallow:                      ← 空，全站放行
  Sitemap:https://www.jpx.co.jp/sitemap.xml
```

补充实测：把 token 目录写死去猜下个月的文件名
（`…/b5b4pj0000039yyj-att/tv_ts202607.xls`）返回 **404**（不是 403），
所以「还没发」与「命名规则变了」都表现为 404、无法区分
——**必须走落地页取 href**，不能猜直链。

---

## 属于哪些竞争池

### 地理池

| 池 | 落入 | 该池里可比的字段 |
|---|---|---|
| **亚太现货** | ✅ 东证 | `adt_cash_total_jpytn` → 换算 USD 后对 HKEX `adt_hkdbn`；`mktcap_eom_jpytn` → 对 HKEX `mktcap_hkdtn`。**两家口径高度可比**：都是「日均成交额 + 月末时价总额」，都含 ETF/REIT，都含场内大宗（东证 ToSTNeT / 港交所非自动对盘）。这是本仓目前最干净的一对现货对照 |
| **亚太衍生品** | ✅ 大阪取引所 | 对 HKEX `derivatives_adv_contracts`。**必须用 `adv_n225_lgeq_kcontracts` + `adv_topix_futures_kcontracts` 而不是 `adv_deriv_total_kcontracts`**——HKEX 没有 1/100 档的微型合约，直接比总张数会把 JPX 抬高一个量级（见口径坑 1）。更稳的是比 `adnv_deriv_total_jpytn`（名义金额） |
| **单一市场垄断对照** | ✅ | JPX 在日本上市股票现货上是事实垄断（与 HKEX 在港股的地位同构）。可比字段：`adt_cash_total_jpytn` / `mktcap_eom_jpytn` / `foreign_share_pct`。**但衍生品不是垄断**——日経225 期货同时在 SGX 与 CME 挂牌，所以只有现货那半边适合放进这个池 |
| 北美现货 / 北美期权 / 欧洲现货 / 欧洲衍生品 | ❌ | JPX 无任何海外市场业务 |

### 标的池

| 池 | 落入 | 该池里可比的字段 |
|---|---|---|
| **股指衍生品** | ✅ 主力 | `adv_n225_lgeq_kcontracts`、`adv_topix_futures_kcontracts`、`adv_n225_options_kcontracts` → 对 CME `adv_equity_kcontracts`、Cboe `adv_index_options_kcontracts`。**跨所必须统一到大合约当量或名义金额**；`adnv_n225_options_jpybn`（权利金金额）是与 Cboe SPX/VIX 期权最诚实的对照量 |
| **利率衍生品** | ✅ | `adv_jgb10y_futures_kcontracts` + `adv_deriv_rates_kcontracts` → 对 CME `adv_rates_kcontracts`。**结构性差异要写在图注里**：CME 的利率量以 SOFR 短端为主，JPX 以 10 年 JGB 长端为主，绝对量差两个数量级（2026-06：JPX 75k 张/日 vs CME 数百万张/日），**只适合看各自的趋势与占比，不适合看相对份额** |
| **单股与 ETF 期权** | ✅ | `adv_secoptions_kcontracts` → 对 Cboe `adv_multilist_options_kcontracts`。量级差距极大（JPX 2026-06 25k 张/日 vs Cboe 数百万张/日），做**指数化（各自 =100）**而不是绝对值并排 |
| **能源商品** | ✅ 旧 TOCOM | `adv_deriv_cmdty_kcontracts` → 对 CME `adv_energy_kcontracts`。含电力（东/西/中部，base+peak）、原油（Platts Dubai）、汽油/煤油/柴油、LNG(JKM)。**电力期货是 CME 没有对应物的独有品类**，作占比图比作对比图有意义 |
| **FX** | ⚠️ 名义上有 | USD/JPY、CNH/JPY、EUR/JPY 先物 **2026-04 才上市，只有 3 个月数据**，不足以进任何时序图。**第一版不入池**，等满 24 个月再说 |
| **加密** | ❌ | JPX 无加密衍生品 |

### 横截面页建议

1. **`/exchanges/` 现货那张图**：JPX 与 HKEX 并排最合适（都是单一市场垄断、都披露 ADT + 月末时价总额）。
   CME / Cboe 没有可比的现货 ADT，不放。
2. **`/exchanges/` 衍生品那张图**：四家（CME / Cboe / HKEX / JPX）**只能用指数化或名义金额**，
   绝不能并排画原始张数——CME 的张数以 SOFR 为主、Cboe 以多标的期权为主、
   JPX 有 1/10 与 1/100 两档小合约，三家的「一张」根本不是同一个东西。
3. JPX 独有、其余三家都没有的一张图：**`net_foreign_prime_jpybn`（外资月度净买入）**。
   这是日股独有的高频资金流数据，没有横截面对照，但作为 JPX 单页的「谁在买」很有价值。
