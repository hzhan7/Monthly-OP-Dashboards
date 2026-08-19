# 复核报告 — Deutsche Börse Group（slug: db1）

复核日期：2026-08-06　｜　复核人：verifier agent　｜　原判定：**B**　｜　**最终判定：B（维持）**

复现方式：全部独立重抓、重解析，不复用上一 agent 的任何下载物或脚本。
我的工作目录：`/tmp/exch_recon/verify_db1/`（`mbf.xlsx` / `eu_*.xls` / `fwb_20260731.xls` /
`mvd.pdf` / `parse_eurex.py` / `eurex_idx.json` / `fwb_idx.json`）。

---

## 一、结论摘要

**原判定 B 成立，维持不变。** 这份侦察报告的诚实度在本批里属于罕见的高：
我逐项攻击了五类虚报，**四类完全打不动**，只打出一个真实的口径错误（TWh 单位差 10⁶）
和若干条实现期会绊人的表述问题。

| 攻击面 | 结果 |
|---|---|
| (a) 只抓到最新一期却声称多年历史 | **不成立**。我自己下载并解析了 2019-01 / 2019-03 / 2020-01 / 2016-01 / 2008-01 / 2003-01 六期 Eurex 工作簿；集团台账实测 2002-01→2026-06 共 294 个月、零断档 |
| (b) 把第三方聚合站当官方源 | **不成立**。四个域名全是 DBG 系一方源（deutsche-boerse.com / eurex.com / cashmarket.deutsche-boerse.com / clearstream.com）。无 FIA、无 investing.com、无 wikipedia。不违反 README 第 4 行硬约束 |
| (c) 靠登录态或手工点击 | **不成立**。三条腿全部 plain `urllib` + 普通 UA + 无 cookie 直接 200，我亲自跑通 |
| (d) 字段口径写错 | **部分成立** —— 命中 1 处真错（EEX 三个 TWh 列差 10⁶），详见 §三.1 |
| (e) 声称 A 但关键字段缺失 | **不成立**（且它本来就没声称 A）。四类目标数字全部拿到并被我复算 |

判 B 而不是 A 的四条理由我逐条验过，**全部属实**：三源两节奏、`.xls` 是 BIFF 需 `xlrd`、
settlement 只含 ICSD、官方分类 ≠ 工作簿 section 树。不是为了显得谨慎而堆的虚坑。

---

## 二、我实际复现的证据

### 2.1 无人值守可行性（自测）

```
urllib.request，普通桌面 UA，无 cookie、无登录态、无浏览器：
  OK 200 125,364 B 1.3s  deutsche-boerse.com/dbg-en/investor-relations/statistics
  OK 200 145,470 B 1.3s  eurex.com/ex-en/data/statistics/monthly-statistics
  OK 200 126,730 B 2.3s  cashmarket.deutsche-boerse.com/.../monthly-statistics-cash-market
  OK 200 114,492 B       clearstream.com/clearstream-en/newsroom/20260114-4897982
  OK 200 119,814 B       cashmarket…/press-releases/Deutsche-B-rse-Trading-Volumes-in-July-2026-5379138
```
无 Cloudflare / Akamai 挑战、无 PerimeterX、无 JA3 拦截。**不需要 Chrome MCP，不需要 curl_cffi。**
blob hash 段不校验一事我也复验了：把 hash 换成 `deadbeef…` 仍返回同一文件（1,565,357 B，字节相同）。

### 2.2 集团台账 `major-business-figures_en.xlsx`

我从落地页正则取到的直链与报告完全一致：blob id **249090**，
`bytes=1,565,357`，`md5=24e501ead7976007b02a859a608170ad`，
`docProps` `dcterms:created=2014-01-13`、`dcterms:modified=**2026-07-10T12:41:26Z**`。
落地页原文我也抓到了：*"The documents will be available as of the second week after the reporting month."*

**2026-06 行逐格复算，与报告 §实测证据 A 一字不差**（fd_total 236,572,727 / fd_index 72,727,937 /
fd_equity 45,597,520 / fd_rates 117,810,131 / otc_out 53,353.254787275 / otc_cleared 15,242.668670318 /
360T 208.11108015228 / cash_ob 188,944,170,073.74844 / td 22 / ss_auc 17,459.2610110425 /
ss_settle 10.276066 / ss_coll 1,047.9078376764285 / ifs_auc 5,146.91280069374 / ifs_settle 7.487532 /
ims_etf 219.62625824539003 / ims_lic 66,823,684）。列号映射（3/5/7/9/11/13/15/17/19/21/23/25/27/29/31/41/43/45/47）也全部正确。

**「历史深度」表我逐列独立重算，13 行全中：**

| 列 | 报告称 | 我实测 |
|---|---|---|
| fd_index / equity / rates / trading_days | 2002-01 | **2002-01** ✅ |
| fd_total | 2009-01 | **2009-01** ✅ |
| cash_orderbook | 2010-01 | **2010-01** ✅ |
| settle_icsd / settle_ifs | 2010-01 | **2010-01** ✅ |
| ss_auc / ifs_auc / ims_etf_aum | 2012-01 | **2012-01** ✅ |
| gsf_collateral | 2007-01 | **2007-01** ✅ |
| 商品 TWh / 360T / cash balances | 2015-01 | **2015-01** ✅ |
| otc_* / ims_licensed | 2016-01 | **2016-01** ✅ |

月份连续性：期望 2002-01→2026-06 共 294 个月，实测 294 行，`missing=[] extra=[]`。**无断档属实。**

### 2.3 Eurex 归档与解析

翻页 `!search` 我自己跑了 13 页：`615 条 = 333 个月（199811 → 202607），missing=[]` —— **与报告逐数字相同**。
xls 覆盖 283 个月自 200301 起，pdf 覆盖 332 个月自 199811 起。落地页确实只挂 10 条（6 个月），必须走翻页。

我用自己写的 `parse_eurex.py`（按 A 列取组名、B 列 `Sum` 取组小计、A 列 `Sum` 取全表总计）解析 202607，
**8 个组 + 11 个产品的 contracts / ADV / OI 与报告 §实测证据 B 全部逐位相同**，
内部闭合检验也复现：8 组相加 = `160,603,224` = A 列 `Sum` 行，**EXACT**。

列位置全部复验：`hdr[34]='Change YtD'`、`hdr[35]='Open Interest'`、
5=Traded Contracts、6=Daily average、15=Capital Volume EUR、25=Paid Premiums、40=Capital OI —— 且 2008→2026 六期一致，**结构稳定**。

**历史可回溯性（针对攻击 (a) 的专项实抓）** —— 我真的把 2019 / 2020 期下下来了：

| 期 | 字节 | Cover `Created on:` | Eurex 总计 | DBG IR fd_total | 差 |
|---|---|---|---|---|---|
| 2026-06 | 2,437,632 | 02.07.2026 | 236,572,727 | 236,572,727 | **0** |
| 2024-12 | 2,443,264 | — | 166,095,735 | 166,095,735 | **0** |
| 2022-01 | 2,250,752 | — | 133,399,407 | 133,399,407 | **0** |
| **2020-01** | 2,088,448 | **05.02.2020** | 145,522,514 | 145,522,514 | **0** |
| **2019-03** | 1,831,424 | — | 203,257,361 | 203,257,361 | **0** |
| **2019-01** | 1,796,608 | **04.02.2019** | 147,780,602 | 147,780,602 | **0** |
| 2016-01 | 1,930,240 | — | 144,796,927 | 144,793,645 | **3,282** |

2019-01 / 2019-03 / 2020-01 是我额外加测的，报告没测过这三期，**结果同样对得上**。
2016-01 的 3,282 张差额（0.002%）我独立复现 —— **官方事后重述实证，报告的口径坑 5 成立**。

rates 分项差额也复现：2026-06 差 **-38,863**、2024-12 差 **-22,325**、
而 2016-01 / 2019-01 / **2019-03** / **2020-01** / 2022-01 **全部为 0**。
报告「分类映射在 2022–2024 之间改过」的推断，被我新增的 2019-03 / 2020-01 两期进一步坐实。

版式漂移也复验：`eu_200301.xls` sheet 名是 `['Eurex Statistics']`（单 sheet 旧版式，当前解析器会 raise），
`eu_200801.xls` 的 `Reported month:` 是 `'2008 January'`，2016 起是 `'January 2016'` —— **口径坑 12 属实**。

### 2.4 FWB 现货

翻页实测 **20 期，20241231 → 20260731**，与报告一致 —— **「只有 20 期」这个最难看的事实它没有隐瞒**。
落地页只挂 10 条。姊妹档 `Monthly_Turnover_Statistics` 我也翻了：**恰好 150 期，20140228 → 20260731**，与报告一字不差。

`Total View` 解析结果与报告 §实测证据 C 逐位相同
（Equities Xetra 117,971,076,737.379 / Frankfurt 3,991,957,256.6637；Total 157,511,145,533.111 / 5,862,577,015.44355）。
`Cover` 的 `Created on:` 确实是 Excel 序列号 `46237.0`（cell_type=3），
`xldate_as_datetime` → **2026-08-03**，而 Eurex 同名格是字符串 `'04.08.2026'` —— **口径坑 13 属实，两家写法确实不同**。

### 2.5 交叉核对源：真的存在，数字真的对得上

**① 官方新闻稿**（`…Trading-Volumes-in-July-2026-5379138`，我自己 200 抓到原文）：
> "…generated a turnover of **€163.37 billion** in July… **€157.51 billion** were attributable to
> Deutsche Börse Xetra… average daily Xetra trading volume to **€6.85 billion**… Deutsche Börse
> Frankfurt were **€5.86 billion**… (previous month: €188.94 billion)"

我的复算：157,511,145,533/1e9 = **157.51** ✅；5,862,577,015/1e9 = **5.86** ✅；合计 **163.37** ✅；
157.51/23 = **6.85** ✅；DBG IR 2026-06 cash_ob 188,944,170,073.75 → **188.94** ✅。

**② Clearstream 月报页**（两页我都自己 200 抓到，`Last Updated 14.01.2026` / `17.04.2026` 均属实）：

| 项 | 我从 DBG IR 解析 | Clearstream 稿原文 | 结论 |
|---|---|---|---|
| 2025-12 ss_auc | 16,788.0104 | ICSD 9,756 + CSD 7,032 = 16,788 | ✅ |
| 2025-12 ifs_auc | 4,414.1354 | IFS 4,414 | ✅ |
| 2025-12 合计 | 21,202.15 | Total AuC 21,202 | ✅ |
| 2025-12 ss_collateral | 932.9160 | GSF Volume outstanding 932.9 | ✅ |
| **2025-12 ss_settlement** | **9.823717** | **ICSD 9.8**（CSD 17.6 不在内） | ✅ 坑 2 成立 |
| 2026-03 ss_auc | 17,135.8619 | ICSD 10,091 + CSD 7,045 = 17,136 | ✅ |
| 2026-03 ifs_auc | 4,796.9043 | IFS 4,797 | ✅ |
| **2026-03 ss_settlement** | **11.867241** | **ICSD 12**（CSD 25 不在内） | ✅ 坑 2 再次成立 |

**「同一张表两行两个口径」这个最阴的坑是真的**：AuC 那行 = ICSD+CSD 合并，
settlement 那行 = 只有 ICSD。两期独立复现，不是碰巧。

**③ 官方 PDF**（我自己下的，207,198 B，`CreationDate D:20260710132703+02'00'`，与 xlsx 的 modified 同日互证）。
报告引的两条脚注，我在 PDF 正文里**逐字找到**：
> "The total shown does not equal the sum of the individual figures as it includes other traded
> products such as ETC, agricultural and precious metals derivatives."
> "Dividend derivatives have been allocated to the equity index and equity derivatives."

「average value」也逐字找到：`Value of securities deposited (average value)`、
`Notional outstanding volumes (average value)`、`Collateral management (average outstandings)`、
`Order book turnover 1) Single-counted`。**口径坑 3、4、10 全部有官方书面依据。**

**④ Clearstream newsroom 列表页不可用于无人值守 —— 我复验了，属实**：
列表页 HTML 里 `/newsroom/YYYYMMDD-id` 文章链接数 = **0**；`?page=2` 返回几乎同样长度的页面（104,923 vs 104,966 B，仍 0 链接）；
`https://www.clearstream.com/sitemap.xml` → **HTTP 404**。它把这个源排除在管道外是**正确的决定**。

### 2.6 仓库侧引用全部真实存在

我核对了 `/Users/hainan/Projects/monthly-op-dashboards`：
`fetch/cboe.py`、`build/roster.py`、`build/exchanges.py`、`series/{cboe,cme,hkex,msci,source_dates}.csv` 全部存在。
报告引用的兄弟列名 **无一虚构**：`cboe.adv_eu_equities_adnv_eurbn` / `adv_fx_adnv_usdbn` /
`adv_multilist_options_kcontracts` / `adv_index_options_kcontracts` / `adv_spx_options_kcontracts` /
`adv_vix_futures_kcontracts`；`cme.adv_total_kcontracts` / `adv_rates_kcontracts` / `adv_equity_kcontracts` /
`adv_energy_kcontracts` / `adv_fx_kcontracts` / `oi_total_contracts` / `oi_rates_contracts`；
`hkex.adt_hkdbn` / `mktcap_hkdtn`；`msci.aum_eop_usdbn`。

`fetch/cboe.py` 里确实有「只填空、不覆盖」的回补实现（第 421/456/505 行附近）与 RPC 滞后一月的处理，
`build/roster.py` 确实有 `LAG` 表 + `GRACE=5`。**报告「与 cboe 完全同构」的说法有代码依据，不是修辞。**

README 第 4 行的硬约束原文：「数据全部来自公司官网 IR 或 SEC 申报的原始披露，不含任何券商研报的观点或数据。」
**db1 的四个源全部合规。**

---

## 三、发现的错误与虚报

### 1. 【真错，必须改】EEX 三个商品列的单位差 10⁶ —— 工作簿是 MWh，不是 TWh

报告「可提取字段」表写：

> `vol_power_deriv_twh` / `vol_power_spot_twh` / `vol_gas_twh` ｜ G(col17/15/19) ｜ EEX 电力与天然气，**TWh**

**照写就错 100 万倍。** 表头虽然标着 `(in TWh)`，但单元格里的值是 MWh：

| 列 | 报告的取法 | 实际单元格值（2026-06） | 官方 PDF | 倍数 |
|---|---|---|---|---|
| col15 power spot | 直接用 | 88,034,094.5 | **88.0 TWh** | 1,000,387× |
| col17 power deriv | 直接用 | 960,720,291.0 | **960.7 TWh** | 1,000,021× |
| col19 gas | 直接用 | 679,742,442.5 | **679.7 TWh** | 1,000,062× |

正确取法是 `G(col15/17/19) / 1e6`。物理常识也能一眼判死：全球年发电量约 3 万 TWh，
「一个月 8,800 万 TWh」不可能。

**最讽刺的是**：报告的口径坑 15 亲手抓住了**同一类**陷阱（col23 表头写 `(in €m)` 实为 EUR），
却在紧邻的商品列块上原样踩了进去，而且**没有任何征兆提示**。
这是全篇唯一会直接产出错数据的缺陷。

### 2. 【表述陷阱，会让实现者取错格】单元格坐标是 xlrd 0-indexed，却写成 Excel A1 样式

报告写 `X(Total View B19)`、`X(B14)`、`X(C16)`、`X(C18)`、`E(row7col5)`。
实测这些是 **xlrd 的 0-indexed 行号**：0-indexed 行 19 = Total 行、行 14 = Equities 行。
换算成 Excel A1 应分别是 **B20 / B15 / C17 / C19**。
按 Excel 记法照抄的人，`B14` 会取到表头 `'EUR'` 那一行（会炸，但排查要花时间），
`B19` 会取到 `Structured Products` 那行（**不会炸，会静默产出错数**）。落地前必须把记法统一并标注。

### 3. 【小错】Eurex 2008-01 的组数不是 6，是 7

报告口径坑 7 称「2008-01 只有 6 个组」。我实测是 **7 个**：
`Credit / Interest Rate / Equity Index / Exchange Traded Funds® / Equity / Volatility / Inflation Derivatives`。
不影响结论（它的核心主张「遍历取组名、不要写死清单」仍然正确），但数字是错的。

### 4. 【报告没提到的实现陷阱】A 列里混着一行脚注，会被当成第 9 个组

Eurex 工作簿 A 列除组名外，还有一行：
`* CO2 and power derivatives are products of the European Energy Exchange AG (EEX); within the
Eurex/EEX cooperation these products are also available for trading via Eurex.`
2016 / 2019 / 2020 / 2022 / 2024 / 2026 各期都有。
报告只说「遍历取组名，不要写死清单」，**没提这行**。
naive 实现（「A 列非空即组名」）会得到 9 个组而不是 8。
我的解析器之所以没中招，是因为组小计锚定在 B 列 `Sum` 上，那行脚注后面没有 Sum 行 —— **务必保留这个锚定方式**。

### 5. 【建议值偏紧，与仓库明规矩相悖】LAG 取 3 太紧

报告建议 `LAG = (3, 3)`。但它自己实测的 Eurex 发布日是「次月 1–5 日」，
我实测 **2020-01 期的 `Created on:` = 05.02.2020，正好是第 5 天**。
`build/roster.py` 的注释写死了仓库规矩：「数值取自各 fetch/<t>.py docstring 里的实测发布日，
不是公司承诺；**宁可给宽一点**」，且 LAG 的语义是「**月末后第几天**」而非「次月第几号」。
建议改为 `(5, 5)`。`GRACE=5` 虽然能兜住，但用宽限额度去补一个已知偏紧的 LAG，
正是那段注释批评的「红点假红」反模式。

### 6. 【未经验证的断言】两处「可直接比水平值」缺少支撑

- `aum_stoxx_dax_etf_eurbn` 被称与 `msci.aum_eop_usdbn`「同形…换汇后可直接比水平值」。
  但**报告从未确认这一列是月末时点还是月内均值**。官方 PDF 对 Clearstream 各行明确标了
  `(average value)`，唯独 `Assets under management in STOXX & DAX ETFs` **没标** —— 暗示是 EOP，
  但这是推断不是证据。它在 AuC 上那么较真，在这里却直接下了结论。落地前需确认。
- `adv_xetra_adnv_eurbn` vs `cboe.adv_eu_equities_adnv_eurbn` 被称「全仓库最干净的一对头对头」。
  Xetra 侧的 single-counted 有 PDF 脚注佐证，**但 Cboe 侧的单边/双边口径报告没查**。
  仓库里 `fetch/cboe.py` 的相邻列描述是 `European Equities - per matched notional value (bps)`，
  "matched" 暗示同为单边、大概率对齐，但同样是推断。这是它自己选作「最干净」的那一对，**理应查实**。

### 7. 【漏掉的便宜历史，不算错】FWB 的 Xetra/Frankfurt 月度分拆比它说的深一年

报告称 FWB 分资产类别「只有 2024-12 起（20 期）」—— 对**资产类别拆分**而言准确。
但我发现 `Total View` 表底部还有两块它没提的区域：
第 57–63 行是**本年度逐月**的 Xetra / Frankfurt order book turnover（EUR），
第 26–50 行是 **2001–2025 年度**值（Mio. EUR）。
因此把 20 期档案全下下来，`Xetra 与 Frankfurt 分开的月度值`可以回溯到 **2024-01**（而非 2024-12），
年度值可回溯到 2001。属于白捡的深度，非错误。

> **2026-08-19 追记**：这条建议后来被采纳并**走得更远**。`turnover_xetra_eurbn` /
> `turnover_fwb_eurbn` 今天是 **2016-01 起 127 个月**（不是 2024-01），六条资产类别拆分列
> **2016-06 起**（各列条数不同：107 / 62 / 52 / 21，那是官方逐年才开始拆，不是断档）。
> 多出来的深度**不是从那 20 期档案里挖的** —— 官方 CMS 至今仍只挂 20 期，
> 回填走的是 `build/basefill/db1_spot_2016.py`：archive.org 上的官方工作簿副本（满精度）
> + 同站月度现货新闻稿（四舍五入到 €bn）两条腿，**都不进 `fetch/db1.py`**，
> 理由（源站已清库、CDX 命中固定 32 期不会再长）写在该脚本 docstring 里。

---

## 四、能不能和 cme / cboe / hkex 放进同一个竞争池

**能，而且是这批候选里口径最贴的一家。不存在「只有成交金额、没有合约张数」的问题 —— 两样都有。**

我用实测值直接对了一遍量级（2026-06，同月）：

| 池 | db1 字段 | db1 实测值 | 池内对手实测值 | 判断 |
|---|---|---|---|---|
| 衍生品张数 | `adv_eurex_total_kcontracts` | **10,753.3** k张/日 | `cme.adv_total_kcontracts` = 30,600.0 | **同量纲同单位**，直接可比 |
| 利率衍生品 | `adv_eurex_rates_kcontracts` | **5,355.0** k张/日 | `cme.adv_rates_kcontracts` = 13,606.4 | **同单位**，欧债 vs 美债，池内信息量最高的一组 |
| 未平仓 | `oi_eurex_total_contracts` | **137,117,991** 张 | `cme.oi_total_contracts` = 127,600,179 | **同单位且同数量级**，Eurex 反超 CME，是真头对头 |
| 欧洲现货 | `adv_cash_total_adnv_eurbn` | **8.59** €bn/日 | `cboe.adv_eu_equities_adnv_eurbn` = 14.95 | **同单位、同币种、同地区**，全仓库最贴的一对 |

三点补充判断：

1. **合约张数不可比水平值这件事在本仓不构成障碍。** `build/exchanges.py` 本来就把所有序列
   rebase/指数化再画（第 251 行 `rebase()` 注释原文：「单位不可比的序列只能这么放在一张图上」），
   且 HKEX 早就是以 HK$bn/日 与 CME 的 k张/日 并存、单独走 own-axis。db1 混着张数与 €bn 属于既有模式，
   **不需要改 schema**。

2. **共同窗口不会被拖累。** 现有 `hkex.csv` 起于 2019-01、`cboe.csv` 起于 2017-01、`cme.csv` 起于 2008-01；
   db1 建议起点 2016-01 早于 hkex，**共同窗口的约束仍是 hkex，不因加入 db1 而收窄**。

3. **⚠ 但有一个会让 build 直接崩的雷，报告没写。** `build/exchanges.py` 第 242–243 行：
   共同窗口内任一入选列有空值就 `raise SystemExit`。
   而 db1 的 Clearstream / OTC / 360T / 商品 / IMS 列**天生会在最新月留空**（等次月约 10 日的集团台账）。
   ⇒ **这些慢腿列绝对不能进 `exchanges.py` 的横截面 panel**，只能放在 db1 自己的页面上。
   进池的只能是快腿列（`adv_eurex_*` / `oi_eurex_*` / `adv_xetra_*` / `adv_cash_total_*`）。

**不可比、不应入池的**（报告已正确标注，我确认）：
`vol_power_*_twh` / `vol_gas_twh`（TWh vs 张数，量纲无关，只能同比）；
`auc_*_eurtn` vs `hkex.mktcap_hkdtn`（托管 vs 市值，只能并置不能相除）。

---

## 五、给实现阶段的具体警告

1. **`vol_power_spot_twh` / `vol_power_deriv_twh` / `vol_gas_twh` 必须除以 1e6**。
   工作簿表头写 `(in TWh)` 是错的，实际是 MWh。用官方 PDF 的 88.0 / 960.7 / 679.7（2026-06）做落地断言。
2. **把 db1.md 里所有单元格坐标当作 xlrd 0-indexed 读**，不要按 Excel A1 理解。
   `Total View` 的 Total 行 = 0-indexed 行 19，Equities 行 = 行 14。写代码时改用行标签匹配（找 A 列文本 `'Total'` / `'Equities'`），别用行号。
3. **Eurex 组小计必须锚定在 B 列 `Sum`**，绝不能「A 列非空即组名」—— A 列有一行 EEX 合作脚注会被误当组。
   保留报告建议的闭合校验（组小计之和 == A 列 `Sum`），我实测 2026-07 为 EXACT，可作硬断言。
4. **`LAG` 建议改为 (5, 5)** 而非报告的 (3, 3)：实测 Eurex 最晚发布日是月末后第 5 天（2020-01 期）。
   语义是「月末后第几天」，别理解成「次月第几号」。
5. **慢腿列（Clearstream/OTC/360T/商品/IMS）不得进 `build/exchanges.py` 横截面** ——
   该文件第 242 行对共同窗口内的空值直接 `raise SystemExit`，而这些列最新月必空。
6. **照抄 `fetch/cboe.py` 的「只填空、不覆盖」** —— 这条我验证过代码真的存在（第 456/505 行）。
   2016-01 的 3,282 张重述差是真的，冲突必须落 `cache/db1_restatements.csv`，不能自动吞。
7. **`settle_icsd_txn_mn` 的命名不能妥协** —— 我两期独立复现，DBG IR 那格只等于 ICSD，
   不含约 2 倍笔数的 CSD；而同表的 AuC 行却是 ICSD+CSD 合并。图注必须写明。
8. **`requirements.txt` 加 `xlrd`**（本机 2.0.2 已验证可读这些 BIFF 文件）；
   注意 xlrd≥2.0 不读 .xlsx，集团台账仍走 openpyxl。2003–2007 的 Eurex 是单 sheet 旧版式，
   当前解析器会 raise —— 若起点定在 2016-01 则不受影响。
9. **落地前补两次核实**：(a) `aum_stoxx_dax_etf_eurbn` 是 EOP 还是月均（决定能否与 `msci.aum_eop_usdbn` 比水平值）；
   (b) `cboe.adv_eu_equities_adnv_eurbn` 是单边还是双边（决定能否与单边的 Xetra 比水平值）。
   两处报告都直接下了「可比」的结论但没查。
10. ~~**FWB 那 20 期档案值得全下一遍**~~ —— **2026-08-18 已做，且比这条建议走得更远**：
    Xetra/Frankfurt 分开的月度序列今天回到 **2016-01**（127 个月），不是 2024-01。
    见 §三.7 的追记与 `build/basefill/db1_spot_2016.py`。
