# Deutsche Börse Group（slug: db1）—— 数据源可行性侦察

侦察日期：2026-08-06　｜　侦察人：recon agent　｜　实测脚本：`/tmp/exch_recon/scratch/proof_db1.py`

---

## 判定

**B —— 可实现，但有坑。**

三个官方源全部 **plain `urllib` 直接 200**（无 Cloudflare / Akamai / JS 渲染 / 登录墙），
历史深、发布日有权威字段、与官方新闻稿逐位对上。任务点名要的四类数字**全部拿到**：
Xetra 现货 ADV（€bn）、Eurex ADV 与 OI（分利率 / 股指）、Clearstream AuC（€tn）与 settlement transactions。

判 B 不判 A 的四条理由（都在下面「口径坑」里展开）：

1. **一家要缝三个源、两种节奏**：Eurex / Xetra 次月 1–4 日就出，DBG IR 集团台账要等次月约 10 日。
   新月建行时 Clearstream / OTC / 360T 列天然为空 —— 必须照 `fetch/cboe.py` 的
   「RPC 滞后一月 → 只填空不覆盖」写回补，不写就永久留白。
2. **`.xls` 是 1990 年代的 BIFF/OLE2**，`openpyxl` 打不开，要新引入 `xlrd`（本机已有 2.0.2）。
3. **`Settlement transactions` 只含 ICSD，不含 CSD** —— 实测两个月都只等于 Clearstream 自己稿子里的
   国际业务那一行。照字面命名成「Clearstream 结算笔数」就是错标，而且错得毫无征兆。
4. **官方分类 ≠ 工作簿 section 树，且总数 ≠ 分项之和**（官方脚注自认）。想用 Eurex 工作簿
   重建 DBG 的 Index/Equity/Rates 三分类必然对不上。

---

## 数据源

### A. 集团口径月度台账（**主源**）

| 项 | 值 |
|---|---|
| 落地页 | `https://www.deutsche-boerse.com/dbg-en/investor-relations/statistics` |
| 直链 | `https://www.deutsche-boerse.com/resource/blob/249090/{任意32位hex}/data/major-business-figures_en.xlsx` |
| 格式 | xlsx（openpyxl），1 张 sheet `Major business figures`，294 行 × 47 有效列 |
| 抓法 | 落地页正则取 href → urllib 下载。blob id `249090` 常驻多年（docProps created 2014-01），可作兜底 |
| 覆盖 | 2002-01 → 2026-06（今日），无断档 |

配套 PDF（同页，只作人工核对，不入管道）：
`https://www.deutsche-boerse.com/resource/blob/249080/{hash}/data/monthly-volume-development_en.pdf`
—— 「Business indicators of Deutsche Börse Group」，2 页，口径脚注写在这里。

### B. Eurex 产品级 ADV / OI

| 项 | 值 |
|---|---|
| 列表页 | `https://www.eurex.com/ex-en/data/statistics/monthly-statistics`（**默认只挂 10 条**） |
| 全量列表 | `https://www.eurex.com/ex-en/data/statistics/monthly-statistics/3848!search?pageNum={0..12}&hitsPerPage=50&sort=freshness%20%20desc`（615 条 = 333 个月 × xls/pdf） |
| 直链 | `https://www.eurex.com/resource/blob/{blobid}/{hash}/data/monthlystat_{YYYYMM}.xls`，blobid **每月都变**，必须从列表页拿 |
| 格式 | BIFF `.xls`（`Composite Document File V2`），sheet = `Cover` + `Eurex Monthly Statistics`（3649 行 × 45 列） |
| 覆盖 | xls：2003-01 起（**当前版式自 2008-01**）；pdf：1998-11 起 |

### C. Xetra / Frankfurt 现货分资产类别

| 项 | 值 |
|---|---|
| 列表页 | `https://www.cashmarket.deutsche-boerse.com/cash-en/Data-Tech/statistics/Turnover-Statistics/monthly-statistics-cash-market` |
| 全量列表 | 同域 `.../monthly-statistics-cash-market/4090756!search?pageNum={0,1}&hitsPerPage=50&sort=sDate%20desc` |
| 直链 | `.../resource/blob/{blobid}/{hash}/data/FWB_Monthly_Cash_Market_Statistics.{YYYYMMDD}.xls` |
| 格式 | BIFF `.xls`，24 张 sheet，要的是 `Cover` + `Total View` |
| 覆盖 | **官方 CMS 只挂 2024-12 → 2026-07（20 期）** —— 这是那条 live 链路的物理天花板，不是抓取器窗口没开。⚠ 入库序列比这深得多：2026-08-18 由 `build/basefill/db1_spot_2016.py` 一次性回填到 2016-01/2016-06，见「历史深度」一节 |

姊妹档（个股级，不建议入管道）：`Monthly_Turnover_Statistics.{YYYYMMDD}.xls`，
同页 `.../monthly-turnover-statistics/4090748!search?...`，**150 期，2014-02 起** ——
它是逐 ISIN 的成交明细 + 指数级汇总，没有「分资产类别 / 分场所总额」那张表。

### 只作交叉核对、**不进管道**的两个源

- 现货月度新闻稿：`https://www.cashmarket.deutsche-boerse.com/cash-en/Stay-Informed/newsroom/press-releases/Deutsche-B-rse-Trading-Volumes-in-{Month}-{Year}-{id}`
  （id 不可预测；同文也挂在 `deutsche-boerse.com/dbg-en/media/news-stories/press-releases/…`）
- Clearstream 自己的月报：`https://www.clearstream.com/clearstream-en/newsroom/{YYYYMMDD}-{id}`
  （**文章页 server-rendered、curl 可读**，但 newsroom 列表页是 Next.js 客户端渲染、
  无公开 JSON API、`?page=` 无效 —— **发现不了新链接，所以不能当无人值守源**。
  它的价值是给出 ICSD / CSD / IFS 的三分拆，DBG IR 那份只给合并数。）

---

## 可提取字段

单位后缀照 `series/cboe.csv` 风格。**来源列**：`G`=DBG IR xlsx、`E`=Eurex xls、`X`=FWB cash market xls。

### 衍生品（Eurex）

| CSV 列名 | 源 | 口径 |
|---|---|---|
| `adv_eurex_total_kcontracts` | G(col3)/E | 全 Eurex 月成交合约数 ÷ 交易日，千张。G 与 E 的月总数逐位相等（2019/2022/2024/2026 实测），G 更权威（含事后重述） |
| `adv_eurex_rates_kcontracts` | G(col9) | DBG 报告口径「Interest rate derivatives」。**不要**用 Eurex 工作簿的 `Interest Rate Derivatives` Sum 重建 |
| `adv_eurex_index_kcontracts` | G(col5) | DBG 口径「Equity index derivatives」，**已把 dividend derivatives 摊进来**（官方脚注 2） |
| `adv_eurex_equity_kcontracts` | G(col7) | DBG 口径「Equity derivatives」，同样含摊入的 dividend |
| `oi_eurex_total_contracts` | E(row `Sum`, col 35) | 月末未平仓合约数。**G 里没有 OI，只能从 Eurex 工作簿取** |
| `oi_eurex_rates_contracts` | E(`Interest Rate Derivatives` Sum, col35) | 同上，注意与 G 的 rates 分类不同源 |
| `oi_eurex_index_contracts` | E(`Equity Index Derivatives` Sum) | |
| `oi_eurex_equity_contracts` | E(`Equity Derivatives` Sum) | |
| `adv_bund_kcontracts` | E(code `FGBL`) | Euro-Bund Futures，欧洲长端基准 |
| `adv_bobl_kcontracts` | E(`FGBM`) | Euro-Bobl |
| `adv_schatz_kcontracts` | E(`FGBS`) | Euro-Schatz |
| `adv_btp_kcontracts` | E(`FBTP`) | Euro-BTP（意债，欧洲主权利差的量温计） |
| `adv_estoxx50_fut_kcontracts` | E(`FESX`) | EURO STOXX 50 Index Futures |
| `adv_estoxx50_opt_kcontracts` | E(`OESX`) | EURO STOXX 50 Index Options |
| `oi_estoxx50_opt_contracts` | E(`OESX`, col35) | 27.0m 张，占全所 OI 的 19%，是 Eurex 最粘的一块 |
| `adv_dax_fut_kcontracts` / `adv_dax_opt_kcontracts` | E(`FDAX`/`ODAX`) | |
| `adv_vstoxx_fut_kcontracts` | E(`FVS`) | VSTOXX 期货 —— 对标 Cboe 的 `adv_vix_futures_kcontracts` |
| `trading_days` | G(col25) / E(row7col5) | 两处独立给出，实测一致（2026-06 均 22、2026-07 Eurex 23）。G 滞后，做本月 ADV 用 E |

### 现货（Xetra / Frankfurt）

| CSV 列名 | 源 | 口径 |
|---|---|---|
| `adv_xetra_adnv_eurbn` | X(`Total View` B19)÷trading_days | Xetra 电子盘 order book turnover 日均，**single-counted（单边）** |
| `adv_fwb_adnv_eurbn` | X(`Total View` C19)÷trading_days | Frankfurt 场内（专家撮合），量级只有 Xetra 的 4% |
| `adv_cash_total_adnv_eurbn` | G(col23)÷G(col25) | Xetra+Frankfurt 合计，**这是 DBG 报告段口径**，历史最深（2010-01 起） |
| `turnover_xetra_equities_eurbn` | X(B14) | 月度总额，非 ADV |
| `turnover_xetra_etp_eurbn` | X(B15) | ETF/ETC/ETN，Xetra 是欧洲最大 ETF 交易场 |
| `turnover_fwb_bonds_eurbn` | X(C16) | 债券只在 Frankfurt 场内成交，Xetra 恒为空 |
| `turnover_fwb_structured_eurbn` | X(C18) | 结构化产品（certificates/warrants） |

### 后交易与其余分部（这一组是全仓库唯一的非成交量月度指标）

| CSV 列名 | 源 | 口径 |
|---|---|---|
| `auc_securities_services_eurtn` | G(col27)/1000 | Clearstream **ICSD + CSD** 托管资产，**月内平均值**（"average value"），不是月末时点数 |
| `auc_fund_services_eurtn` | G(col41)/1000 | Clearstream IFS（基金） |
| `auc_group_total_eurtn` | 两列相加 | = Clearstream 自己稿子里的 "Total Assets under Custody" |
| `settle_icsd_txn_mn` | G(col29) | ⚠ **只含 ICSD**，不含 CSD。别叫 "Clearstream settlement transactions" |
| `settle_ifs_txn_mn` | G(col43) | IFS 结算笔数 |
| `gsf_collateral_outstanding_eurbn` | G(col31) | Global Securities Financing 平均在外量 |
| `otc_notional_outstanding_eurtn` | G(col11)/1000 | EurexOTC Clear 名义未平仓（平均值） |
| `otc_notional_cleared_eurtn` | G(col13)/1000 | 月内清算名义量（含压缩） |
| `adv_360t_fx_eurbn` | G(col21) | 360T FX 日均名义（含 GTX，2018-07 起） |
| `aum_stoxx_dax_etf_eurbn` | G(col45) | 挂钩 STOXX/DAX 指数的 ETF 资产 —— **可与 `msci.aum_eop_usdbn` 同形对比** |
| `vol_power_deriv_twh` / `vol_power_spot_twh` / `vol_gas_twh` | G(col17/15/19) | EEX 电力与天然气，TWh |

---

## 历史深度

**建议起点 `2016-01`**（全部列齐备）。各列首个非空月实测：

| 列组 | 最早月 | 备注 |
|---|---|---|
| `fd_index / fd_equity / fd_rates / trading_days` | **2002-01** | 294 个月，无断档 |
| `fd_total`（全所合约总数） | **2009-01** | 2002–2008 只有三分项，没有 total |
| Eurex 产品级 ADV/OI（xls 当前版式） | **2008-01** | 2003-01～2007-12 的 xls 是单 sheet `Eurex Statistics` 旧版式，要另写解析；1998-11 起有 PDF |
| `cash_orderbook`（Xetra+FWB 总额） | **2010-01** | |
| `settle_icsd / settle_ifs` | **2010-01** | |
| `ss_auc / ifs_auc / ims_etf_aum` | **2012-01** | |
| `gsf_collateral` | **2007-01** | |
| 商品 TWh / 360T / cash balances | **2015-01** | |
| `otc_*` / `ims_licensed_index_contracts` | **2016-01** | |
| ~~**FWB 分资产类别拆分（`turnover_xetra_*`）**~~ | ~~2024-12~~ → **2016-01 / 2016-06** | **2026-08-18 已回填，「只有 20 期」不再成立。** 现值（2026-08-19 实测）：`turnover_xetra_eurbn` / `turnover_fwb_eurbn` **2016-01 起 127 个月**；六条资产类别拆分列 **2016-06 起**，但**各自条数不同** —— `turnover_xetra_equities` / `_etp` 107、`turnover_fwb_equities` / `_bonds` / `_structured` 62、`turnover_fwb_etp` / `_funds` 52、`turnover_xetra_structured` 只有 21。⚠ 那**不是断档，是官方在不同年份才开始拆这些类**；回填走的是一次性脚本 `build/basefill/db1_spot_2016.py`（archive.org 上的官方工作簿副本 + 月度现货新闻稿两条腿），不在 cron 路径上，官方 CMS 今天仍然只挂 20 期 |

**Eurex 月度文件目录无断档**：1998-11 → 2026-07 共 333 个月全部在架（实测把 13 页 615 条抓全后逐月比对，missing = 空列表）。

---

## 发布节奏

三条腿节奏不同，这是本家最需要在代码里体现的事实：

| 源 | 节奏（实测） | 权威「发布日」字段 |
|---|---|---|
| **Eurex xls** | 次月 **1–5 日**（近 24 期：最早 1 号、最晚 5 号，中位 2–3 号） | 工作簿 `Cover` 的 `Created on:` = `04.08.2026`，与列表页 `search-result-date` = `Aug 04, 2026` **逐日相同** |
| **FWB cash market xls** | 次月 **1–4 日** | `Cover` 的 `Created on:` 是 Excel 序列号（46237 → 2026-08-03），与列表页 `Aug 03, 2026` **逐日相同** |
| **现货新闻稿** | 次月第 **1–3** 个工作日（2026-07 档：Aug 03） | 页面 `Aug 03, 2026` |
| **DBG IR xlsx（集团台账）** | 次月 **约 10 日**（页面原文：*"available as of the second week after the reporting month"*；2026-06 档 = 2026-07-10） | `docProps/core.xml` 的 `dcterms:modified` = `2026-07-10T12:41:26Z`，与配套 PDF 的 `creationDate D:20260710132703+02'00'` 互证 |
| **Clearstream 月报页** | 次月 **中旬**（2025-12 档 14.01.2026、2026-03 档 17.04.2026） | 页面 `Last Updated 17.04.2026` |

**`source_dates.csv` 的建议**：用「确立该月的那一期」的自述日期 ——
即 `max(Eurex Cover Created on, FWB Cover Created on)`（两者都到齐，该月的成交列才写全）。
evidence 一栏写清两个文件名与两处单元格，并注明「Clearstream/OTC/360T 列由次月约 10 日的
`major-business-figures_en.xlsx` 回补，不改本行发布日」。

> ⚠ **闸门排期**：`build/roster.py` 的 LAG 若按 DBG IR 的次月 10 日设，页面会白白晚 6 天才亮成交数据；
> 若按次月 3 日设，则每次跑到第 3 日时集团列必空。建议 LAG 取 **(常规月 3, 季末月 3)** 走快腿，
> 集团列靠「只填空回补」在后续几天自然补齐 —— 这与 cboe 的 RPC 完全同构。

---

## 口径坑（按踩坑概率排序）

1. **三个源两种节奏，新月天然缺列。**
   次月 1–4 日能拿到 Eurex + Xetra 的全部成交列；Clearstream AuC / OTC / 360T / 商品 / IMS
   要等次月约 10 日的 DBG IR xlsx。**新月建行时这些格必须允许为空、且不能因此抛异常**；
   同时必须做「已有值永不覆盖、只填空」的回补，否则每个月的 Clearstream 列会永久留白。
   （与 `fetch/cboe.py` 口径坑 1 完全同构，抄那段逻辑即可。）

2. **`Settlement transactions` 只含 ICSD，不含 CSD。**
   实测两期：
   `2025-12` DBG IR = **9.823717 m**，Clearstream 自己稿子：ICSD 9.8 m / CSD 17.6 m / IFS 5.9 m；
   `2026-03` DBG IR = **11.867241 m**，Clearstream 稿：ICSD 12 m / CSD 25 m / IFS 8 m。
   两次都只等于 ICSD。**列名必须写成 `settle_icsd_txn_mn`**，图注要写「不含德国本土 CSD 的约 2 倍笔数」。
   （AuC 那一行反而是 ICSD+CSD 合并 —— 同一张表两行两个口径，这就是这个坑最阴的地方。）

3. **AuC 是月内平均值，不是月末时点数。**
   PDF 原文 `Value of securities deposited (average value)`。HKEX 的 `mktcap_hkdtn` 是月末时点，
   两者放同一张图要注明；做「月末跳变」类叙事会踩空。
   `otc_notional_outstanding` 与 `gsf_collateral` 同样是 average outstandings。

4. **DBG 的三分类 ≠ Eurex 工作簿的 section 树，且分项之和 ≠ 总数。**
   官方 PDF 两条脚注写死了：
   - *"The total shown does not equal the sum of the individual figures as it includes other traded products such as ETC, agricultural and precious metals derivatives."*
   - *"Dividend derivatives have been allocated to the equity index and equity derivatives."*
   实测 2026-06：DBG rates 117,810,131 vs Eurex `Interest Rate Derivatives` Sum 117,771,268（差 38,863）；
   2024-12 差 22,325；而 2016-01 / 2019-01 / 2022-01 **完全相等** —— 说明分类映射在 2022–2024 之间改过。
   ⇒ **三分类一律取 DBG IR 的列，产品级与 OI 一律取 Eurex 工作簿，两边不要互相验算分项。**

5. **Eurex 会重述历史。**
   2016-01 首发工作簿（2016-02-02 published）grand total = **144,796,927**；
   今天 DBG IR 台账里的 2016-01 = **144,793,645**，差 3,282 张（0.002%）。
   2019 / 2022 / 2024 / 2026 四个抽样月两边逐位相同。
   ⇒ 照 cboe / hkex 的做法：**已有值不覆盖**，冲突写进 `cache/db1_restatements.csv` 供人工判断。

6. **`.xls` 是 BIFF/OLE2，`openpyxl` 打不开。**
   `file(1)` 报 `Composite Document File V2 Document … Eurex Monthly Short Statistics`。
   要 `xlrd`（本机 2.0.2 可读 `.xls`；注意 xlrd ≥2.0 **不再**读 `.xlsx`，所以 DBG IR 那份仍用 openpyxl）。
   `requirements.txt` 需新增 `xlrd`。

7. **Eurex 工作簿的层级要按标签走，不能按行号。**
   A 列 = 大组名（`Equity Derivatives` / `Interest Rate Derivatives` / …），B 列 = 产品族，
   C 列 = 子族，D 列 = 产品名，E 列 = 产品代码，F 列起才是数值。
   **组小计出现在 B 列写着 `Sum` 的那一行**（不是 A 列），全表总计在 A 列 `Sum`（2026-07 是第 3587 行）。
   组的数量与名字逐年变：2016-01 有 `Property Derivatives` / `Capital Market Derivatives`，2026 没了；
   2008-01 只有 6 个组、2010-01 有 12 个、2026-07 有 8 个。**遍历取组名，不要写死清单。**
   列位置：5=Traded Contracts、6=ADV、15=Capital Volume EUR、25=Paid Premiums、**35=Open Interest**、40=Capital OI。
   （35 很容易错记成 34，34 是 `Change YtD`。）

8. **Eurex / FWB 的列表页默认只挂 10 条。**
   直接 GET 落地页只能看到最近 5–6 个月。历史必须走 `{pageId}!search?pageNum=N&hitsPerPage=50`，
   Eurex 的 pageId = `3848`、FWB = `4090756`、Monthly Turnover = `4090748`；
   `pageNum` 从 **0（省略）** 开始，`pageNum=1` 是第二页。

9. **blob URL 的 hash 段不校验，但 blob id 每月都变（DBG IR 那份除外）。**
   实测：把 hash 换成 `00000000000000000000000000000000` 三个域名都照样 200 返回同一文件。
   但 Eurex / FWB 每期一个新 blob id，所以**必须解析列表页拿 id**；
   只有 `major-business-figures_en.xlsx` 的 id `249090` 是常驻的，可以写死作兜底。

10. **Xetra ≠ Deutsche Börse 现货全部。**
    新闻稿的「€163.37 billion」是 Xetra + Frankfurt 合计；「€157.51 billion」才是 Xetra。
    ADV 要各除各的：Xetra ADV = 157.51 / 23 = 6.85（新闻稿正是这么写的）。
    另外 order book turnover 是 **single-counted（单边）**，而 HKEX 的南向 ADT 是双边 —— 跨家比要注明。

11. **FWB 分资产类别档只有 2024-12 起（20 期）。**
    要 2024 之前的 ETF / 债券 / 结构化拆分，官方没有现成的月度总表；
    `Monthly_Turnover_Statistics`（2014-02 起、150 期）是逐 ISIN 明细，能拼出指数级但拼不出资产类别级。
    ⇒ 深史只能用 `cash_orderbook`（2010-01 起的 Xetra+FWB 总额）。

12. **Eurex `Cover` 的 `Reported month:` 格式变过。**
    2008-01 档是 `'2008 January'`，2010 起是 `'January 2010'`。
    别拿它当解析锚点 —— 用文件名里的 `YYYYMM` 更稳；`Cover` 只用来取 `Created on:`。

13. **FWB 的 `Created on:` 是 Excel 日期序列号，不是字符串。**
    `46237.0` → `xlrd.xldate.xldate_as_datetime(46237, wb.datemode)` = 2026-08-03。
    Eurex 的同名单元格反而是字符串 `'04.08.2026'`（DD.MM.YYYY，欧洲序）。两家写法不同。

14. **Clearstream newsroom 列表页是 Next.js 客户端渲染。**
    文章页本身 curl 可读（server-rendered），但列表是 JS 拉的，`?page=` 无效、无 `sitemap.xml`、
    JS chunk 里只有 `/api/auth/*` 两个端点。**无法无人值守发现新链接** ——
    所以 ICSD/CSD/IFS 三分拆只能当人工核对，不能进 cron。

15. **`Cash equities – Total order book volume` 的表头单位写着 `(in €m)`，实际是 EUR。**
    2026-06 那格 = `188,944,170,073.75`，对应新闻稿的 €188.94 bn。表头是陈年笔误，别照它换算。

---

## 实测证据

脚本：`/tmp/exch_recon/scratch/proof_db1.py`（全程 `urllib.request`，无 curl、无浏览器）
完整输出：`/tmp/exch_recon/scratch/proof_out.txt`
下载物：`major_business_figures.xlsx`(1,565,357 B) / `eurex_202607.xls`(2,441,728 B) /
`eurex_202606.xls` / `eurex_201601.xls` / `fwb_20260731.xls`(1,748,480 B) / `fwb_20241231.xls` /
`monthly_volume_development.pdf`

### A) DBG IR `major-business-figures_en.xlsx`

```
discovered: https://www.deutsche-boerse.com/resource/blob/249090/a878c0fa1964bd7e7fe50ce5881f641e/data/major-business-figures_en.xlsx
bytes: 1565357 | docProps dcterms:modified = 2026-07-10T12:41:26Z
月份数 294，2002-01 -> 2026-06

2026-06:
    fd_total_contracts               236572727
    fd_index_contracts               72727937
    fd_equity_contracts              45597520
    fd_rates_contracts               117810131
    otc_notional_outstanding_eurbn   53353.254787275
    otc_notional_cleared_eurbn       15242.668670318
    fx_360t_adv_eurbn                208.11108015228
    cash_orderbook_turnover_eur      188944170073.74844
    trading_days                     22
    ss_auc_eurbn                     17459.2610110425
    ss_settlement_txn_m              10.276066
    ss_collateral_eurbn              1047.9078376764285
    ifs_auc_eurbn                    5146.91280069374
    ifs_settlement_txn_m             7.487532
    ims_etf_aum_eurbn                219.62625824539003
    ims_licensed_index_contracts     66823684
2025-12:
    fd_total_contracts  172730288      ss_auc_eurbn        16788.0103973964
    cash_orderbook      116317714202.31639 (19 交易日)
    ss_settlement_txn_m 9.823717       ss_collateral_eurbn 932.9160100086021
    ifs_auc_eurbn       4414.13535204331   ifs_settlement_txn_m 5.91006
2016-01:
    fd_total_contracts  144793645      ss_auc_eurbn 11154.531562899272
    cash_orderbook      127531902381.19 (20 交易日)   ims_etf_aum_eurbn 93.5
```

### B) Eurex `monthlystat_202607.xls`

```
latest xls month=202607  published(listing)=Aug 04, 2026
Cover: {'Reported month:': 'July 2026', 'Created on:': '04.08.2026'} | trading days = 23.0

Equity Derivatives            contracts=21340370    ADV=927842.17     OI=75068634
Equity Index Derivatives      contracts=43678872    ADV=1899081.39    OI=49572331
Dividend Derivatives          contracts=1684206     ADV=73226.35      OI=6568206
Volatility Index Derivatives  contracts=831765      ADV=36163.70      OI=263127
ETF & ETC Derivatives         contracts=250132      ADV=10875.30      OI=345893
Commodity Derivatives         contracts=268         ADV=11.65         OI=1479
Interest Rate Derivatives     contracts=92779897    ADV=4033908.57    OI=10860566
Foreign Exchange Derivatives  contracts=37714       ADV=1639.74       OI=82882
__TOTAL__                     contracts=160603224   ADV=6982748.87    OI=142763118

FGBL Euro-Bund Futures            ADV=1066417.04   OI=1695630
FGBM Euro-Bobl Futures            ADV=834767.35    OI=1695286
FGBS Euro-Schatz Futures          ADV=738635.74    OI=2609340
FBTP Euro-BTP Futures             ADV=320448.30    OI=546072
FOAT Euro-OAT-Futures             ADV=265486.04    OI=642627
FESX EURO STOXX 50 Index Futures  ADV=514906.74    OI=1925434
OESX EURO STOXX 50 Index Options  ADV=702815.43    OI=27022743
FDAX DAX Futures                  ADV=23014.91     OI=55700
ODAX DAX Options                  ADV=46998.65     OI=794571
FVS  Futures on VSTOXX            ADV=29760.22     OI=113338
FEU3 Three-Month EURIBOR Futures  ADV=150117.57    OI=456618
```

**内部闭合检验**：8 个组小计相加
`21,340,370+43,678,872+1,684,206+831,765+250,132+268+92,779,897+37,714 = 160,603,224`
= A 列 `Sum` 行的总计，**逐位相等**（说明层级定位没有漏组也没有重复计入）。

### C) Xetra / Frankfurt `FWB_Monthly_Cash_Market_Statistics.20260731.xls`

```
latest file=20260731  published(listing)=Aug 03, 2026 | Cover reported month: July 2026
Equities                                  Xetra=117971076737.379  Frankfurt=3991957256.6637
ETFs, ETCs, ETNs                          Xetra= 39539972187.9133 Frankfurt=  192664748.0459
Bonds                                     Xetra=(空)              Frankfurt=  463934056.820717
Funds                                     Xetra=(空)              Frankfurt=   44695478.475
Structured Products and Other Instruments Xetra=       96607.8186 Frankfurt= 1169325475.43823
Total                                     Xetra=157511145533.111  Frankfurt= 5862577015.44355
```

### D) 交叉核对（**15 项，全部对上**）

对照对象一：官方新闻稿
《Deutsche Börse Trading Volumes in July 2026》，`cashmarket.deutsche-boerse.com/…-5379138`，Aug 03, 2026。
原文：*"…generated a turnover of €163.37 billion in July… €157.51 billion were attributable to
Deutsche Börse Xetra… average daily Xetra trading volume to €6.85 billion… Deutsche Börse Frankfurt
were €5.86 billion… equities accounted in total for €121.96 billion… ETFs/ETCs/ETNs €39.73 billion…
bonds €0.46 billion, certificates €1.17 billion, funds €0.04 billion."*

| # | 我解析出的数 | 官方公开数 | 结论 |
|---|---|---|---|
| 1 | Xetra 2026-07 = 157,511,145,533.111 → **157.51 €bn** | 新闻稿 157.51 | ✅ |
| 2 | Frankfurt 2026-07 = 5,862,577,015.44 → **5.86 €bn** | 新闻稿 5.86 | ✅ |
| 3 | 两者合计 → **163.37 €bn** | 新闻稿 163.37 | ✅ |
| 4 | Xetra ADV = 157.51 / 23 交易日 → **6.85 €bn** | 新闻稿 6.85 | ✅（交易日数取自 Eurex 工作簿，两个源互证）|
| 5 | Equities = 117.971+3.992 → **121.96 €bn** | 新闻稿 121.96 | ✅ |
| 6 | ETF/ETC/ETN = 39.540+0.193 → **39.73 €bn** | 新闻稿 39.73 | ✅ |
| 7 | 债券 0.464 / 结构化 0.0001+1.169 / 基金 0.0447 → **0.46 / 1.17 / 0.04** | 新闻稿同 | ✅ |

对照对象二：Eurex 工作簿 ↔ DBG IR 台账（同一事实两个官方文件）

| # | Eurex `monthlystat_YYYYMM.xls` grand total | DBG IR `fd_total_contracts` | 结论 |
|---|---|---|---|
| 8 | 2026-06 = **236,572,727** | 236,572,727 | ✅ 逐位 |
| 9 | 2024-12 = 166,095,735 | 166,095,735 | ✅ 逐位 |
| 10 | 2022-01 = 133,399,407 | 133,399,407 | ✅ 逐位 |
| 11 | 2019-01 = 147,780,602 | 147,780,602 | ✅ 逐位 |
| 12 | 2016-01 = 144,796,927 | 144,793,645 | ⚠ 差 3,282（0.002%）→ **官方事后重述的实证**，见口径坑 5 |

| # | DBG IR `cash_orderbook_turnover_eur` 2026-06 = 188,944,170,073.75 → **188.94 €bn** | 新闻稿 "previous month: €188.94 billion" | ✅ |
|---|---|---|---|

对照对象三：Clearstream 自己的月报页
《Clearstream's December 2025 figures》`clearstream.com/clearstream-en/newsroom/20260114-4897982`（Last Updated 14.01.2026）
《Clearstream's March 2026 figures》`clearstream.com/clearstream-en/newsroom/20260416-5082946`（Last Updated 17.04.2026）

| # | 我从 DBG IR 解析出的数 | Clearstream 稿 | 结论 |
|---|---|---|---|
| 13 | 2025-12 `ss_auc` = **16,788.0104 €bn** | ICSD 9,756 + CSD 7,032 = 16,788 | ✅ |
| 14 | 2025-12 `ifs_auc` = **4,414.1354 €bn** | IFS 4,414 | ✅ |
| 15 | 2025-12 合计 = **21,202.15 €bn** | Total AuC 21,202 | ✅ |
| 16 | 2025-12 `ss_collateral` = **932.9160 €bn** | GSF Volume outstanding 932.9 | ✅ |
| 17 | 2025-12 `ss_settlement` = **9.823717 m** | ICSD 9.8（CSD 17.6 **不在内**） | ✅ 且证实了口径坑 2 |
| 18 | 2026-03 `ss_auc` = **17,135.8619 €bn** | ICSD 10,091 + CSD 7,045 = 17,136 | ✅ |
| 19 | 2026-03 `ifs_auc` = **4,796.9043 €bn** | IFS 4,797 | ✅ |
| 20 | 2026-03 `ss_settlement` = **11.867241 m** | ICSD 12（CSD 25 不在内） | ✅ |

对照对象四：DBG IR 的 xlsx ↔ 同页 PDF
PDF《Business indicators of Deutsche Börse Group – June 2026》逐项与 xlsx 2026-06 行一致
（236.6m / 72.7m / 117.8m / 45.6m / 53,353 / 15,243 / 208.1 / 188.9 / 17,459 / 10.3 / 1,048 / 5,147 / 7.5 / 219.6 / 66.8）。

### E) 无人值守可行性实测

```
urllib.request（普通桌面 UA，无 cookie、无登录态）：
  OK 200 125363 1.4s  https://www.deutsche-boerse.com/dbg-en/investor-relations/statistics
  OK 200 145240 1.3s  https://www.eurex.com/ex-en/data/statistics/monthly-statistics
  OK 200 127149 1.9s  https://www.cashmarket.deutsche-boerse.com/…/monthly-statistics-cash-market
  OK 200 113990 1.3s  https://www.clearstream.com/clearstream-en/newsroom/20260416-5082946

blob hash 段不校验（三个域名都是）：
  .../blob/249090/deadbeefdeadbeefdeadbeefdeadbeef/data/major-business-figures_en.xlsx → 200, 1565357 B
  .../blob/5415764/00000000000000000000000000000000/data/monthlystat_202607.xls        → 200, 2441728 B
  .../blob/5414144/ffffffffffffffffffffffffffffffff/data/FWB_…20260731.xls             → 200, 1748480 B
```

无 Cloudflare / Akamai 交互式挑战，无 PerimeterX，无 JS 渲染要求（除 Clearstream newsroom **列表**页），
无 TLS 指纹拦截（不需要 `curl_cffi` / `nscurl`）。整条管道每月约 4 次 HTTP GET（两张列表页 + 三个文件）。

### F) Eurex 归档完整性实测

```
13 页 !search 抓全 → 615 条 = 333 个月（199811 → 202607），missing = []
其中 xls 覆盖 200301 起；当前版式（Cover + Eurex Monthly Statistics）自 200801 起可用同一套代码解析：
  200801 td=22 groups=6  TOTAL=207,439,083  FGBL_ADV=1,289,983.59  FESX_ADV=1,881,875.77
  201001 td=20 groups=12 TOTAL=140,170,712  FGBL_ADV=  748,845.35  FESX_ADV=1,327,938.45
  201306 td=20 groups=11 TOTAL=162,638,699
  201901 td=22 groups=11 TOTAL=147,780,602
  202201 td=21 groups=9  TOTAL=133,399,407
  202412 td=18 groups=9  TOTAL=166,095,735
  200301/200401/200501/200601/200701 → sheet 名是 ['Eurex Statistics']，旧版式，当前解析器 raise
```

---

## 属于哪些竞争池

### 地理池

| 池 | 落不落 | 本家在池内可比的那个字段 | 跨家可比性说明 |
|---|---|---|---|
| **欧洲现货** | ✅ 核心 | `adv_xetra_adnv_eurbn` | 与 `cboe.adv_eu_equities_adnv_eurbn`（Cboe Europe ADNV €bn）**同单位同口径**，是全仓库最干净的一对头对头。注意 Xetra 只覆盖德国上市，Cboe Europe 是泛欧 —— 水平值不能直接排名，做**指数化 + 同比**（正是 `build/exchanges.py` 已有的规矩） |
| **欧洲衍生品** | ✅ 核心 | `adv_eurex_total_kcontracts` + `oi_eurex_total_contracts` | 池内目前只有 DB1；与 `cme.adv_total_kcontracts` / `cme.oi_total_contracts` 做**跨洲对照**，单位同为合约张数（但合约规模不同，仍只能指数化） |
| **北美现货 / 北美期权** | ❌ | — | DBG 无美国业务 |
| **亚太现货 / 亚太衍生品** | ❌ | — | |
| **单一市场垄断对照** | ⚠ 弱 | `adv_xetra_adnv_eurbn` vs `hkex.adt_hkdbn` | Xetra **不是**垄断（Cboe Europe / Turquoise / Tradegate 抢单），放这个池只能当「本土主场 vs 真垄断」的反例。**真正的垄断资产是 Clearstream 的德国 CSD**，但那条的月度字段是 AuC 不是成交量，进不了这个池 |

### 标的池

| 池 | 落不落 | 可比字段 | 说明 |
|---|---|---|---|
| **利率衍生品** | ✅ 最强 | `adv_eurex_rates_kcontracts` | 对 `cme.adv_rates_kcontracts`。这是全仓库最有信息量的一组：欧债（Bund/Bobl/Schatz/BTP/OAT）vs 美债（Treasury/SOFR）。产品级还可再拆 `adv_bund_kcontracts` 等四条 |
| **股指衍生品** | ✅ | `adv_eurex_index_kcontracts` | 对 `cme.adv_equity_kcontracts`（E-mini 系）与 `cboe.adv_index_options_kcontracts`（SPX/VIX）。三家标的不同（ESTX50/DAX vs S&P vs SPX），只能指数化；产品级 `adv_estoxx50_fut/opt_kcontracts` 可与 Cboe 的 `adv_spx_options_kcontracts` 做「各自本土旗舰指数」对照 |
| **单股与 ETF 期权** | ✅ | `adv_eurex_equity_kcontracts` | 对 `cboe.adv_multilist_options_kcontracts`。⚠ Eurex 这一格含 single stock **futures**，Cboe 那格是纯期权；且欧洲单股期权乘数与美国不同 —— 只做同比/指数化，别比水平 |
| **FX** | ✅ | `adv_360t_fx_eurbn` | 对 `cboe.adv_fx_adnv_usdbn`（需 EUR/USD 换算，或双方都指数化）。对 `cme.adv_fx_kcontracts` 只能指数化（名义 vs 张数） |
| **能源商品** | ⚠ 弱 | `vol_power_deriv_twh` / `vol_gas_twh` | 对 `cme.adv_energy_kcontracts`。TWh vs 合约张数**根本不同量纲**，只能同比/指数化；且 EEX 是欧洲电力/天然气、CME 是原油/天然气，产业逻辑不同。建议只放同比，别放同一张水平图 |
| **加密** | ❌ | — | Crypto Finance 无公开月度指标 |

### 建议新增一个池：**后交易与指数资产（本家的独有价值）**

仓库现有三家交易所都是纯成交量，DB1 是唯一带**存量资产**月度指标的：

- `auc_group_total_eurtn`（Clearstream 总托管，2026-06 = 22.6 €tn）——
  **量级参照**：`hkex.mktcap_hkdtn`（港股总市值）是同类的「存量 vs 流量」对照，
  但一个是托管、一个是市值，只能并置不能相除。
- `aum_stoxx_dax_etf_eurbn`（挂钩 STOXX/DAX 的 ETF 资产，2026-06 = 219.6 €bn）——
  **与 `msci.aum_eop_usdbn` 同形**：都是「挂钩自家指数的 ETF 资产」，
  是全仓库唯一一对真正可比的指数授权规模指标（换汇后可直接比水平值）。
  同时 `ims_licensed_index_contracts` 对应 MSCI 的授权衍生品合约量。
- `settle_icsd_txn_mn`、`gsf_collateral_outstanding_eurbn`、`otc_notional_outstanding_eurtn` ——
  池内无同类，只做本家纵向。

---

## 落地建议（给写 `fetch/db1.py` 的人）

1. **`latest_month(cache_dir)` 只看快腿**：解析 Eurex 列表页取最大 `monthlystat_YYYYMM`，
   再解析 FWB 列表页取最大 `FWB_…YYYYMMDD`，取两者的 `min`。
   **不要**用 DBG IR xlsx 定最新月 —— 它慢一周，会让整页晚 6 天更新，
   且会拖累 `build/exchanges.py` 的「共同最新月」把 CME/Cboe/HKEX 一起拉回去一个月。
2. **`update(series_dir, cache_dir)` 三段式**：
   a) Eurex 最新一期 → 写 `adv_eurex_*` / `oi_*` / 产品级 / `trading_days`；
   b) FWB 最新一期 → 写 `adv_xetra_*` / `turnover_*`；
   c) DBG IR xlsx 全表 → **只填空、不覆盖**地回补所有月份的集团列（Clearstream / OTC / 360T / 商品 / IMS），
      并把与既有值冲突的写进 `cache/db1_restatements.csv`。
3. **严格校验**：Eurex 8 个组小计之和必须等于 A 列 `Sum`（本轮实测逐位相等），不等就 raise；
   FWB `Total` 行必须等于上面 5 个 instrument group 之和；
   DBG IR 缺 `fd_total` 以外任一已有列 → raise。
4. **依赖**：`requirements.txt` 加 `xlrd`（读 `.xls`），`openpyxl` 已有。
5. **不要动**：`Monthly_Turnover_Statistics`（逐 ISIN、719 KB/期、对看板无增量）、
   Clearstream newsroom（发现不了新链接）。
