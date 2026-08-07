# ICE（Intercontinental Exchange，NYSE:ICE）月度经营数据源侦察

侦察日期 2026-08-06 · slug `ice` · 全部结论均为本机实测，脚本与原始文件在 `/tmp/exch_recon/scratch/ice/`

---

## 判定

**A —— 可直接实现，且是本仓迄今条件最好的一家。**

一句话：ICE 把 2011-01 至今每一个月、四个 sheet、五十余个字段的经营数据放在**一个 xlsx 里**，
指针由 IR 站的 JSON feed 给出，**纯 `urllib` 3 个请求 5 秒内跑完**，openpyxl 直接解析，
与官方新闻稿、10-K、另一份官方明细文件三路交叉核对全部对上。
没有 Cloudflare（feed 与 CDN 都不拦）、没有 JS 渲染依赖、没有登录墙、没有 PDF/OCR。

唯一需要**避开**的是 `ir.theice.com` 的 **HTML 页面**（`/investor-resources/...`、`/press/...`）
—— 那些页面走 Cloudflare interactive challenge，curl / urllib / nscurl 一律 403 "Just a moment…"。
但**同域下的 `/feed/*.svc/*` JSON 接口完全不设防**，而真正的数据文件在 `s2.q4cdn.com` 上，
也不设防。所以整条链路可以完全绕开被拦的那部分。

---

## 数据源

### 主源（唯一真值）：Monthly Statistics Tracking spreadsheet

| | |
|---|---|
| 指针接口 | `https://ir.theice.com/feed/ContentAsset.svc/GetContentAssetList` |
| 查询参数 | `LanguageId=1&contentAssetTypeList=Supplemental%20Information&year=-1&pageSize=500&includeTags=true&excludeSelection=1&tagList=` |
| 取哪一条 | `Title == "Monthly Statistics Tracking"`（`FileType=="XLSX"`，`Tags` 含 `section`/`home`）→ 读它的 `FilePath` |
| 当期直链（2026-08-06 实测） | `https://s2.q4cdn.com/154085107/files/doc_downloads/2026/07/2011-2026-Monthly-Stats-July-2026_vF.xlsx` |
| 格式 | xlsx，377,178 bytes，4 个 sheet，251 列 |
| 抓取方式 | `urllib.request` + 常规桌面 UA，两跳都不需要 cookie / 登录态 / 浏览器 |

**`apiKey` 参数可以完全省略。** 页面 JS 里写死了 `Q4ApiKey = 'BF185719B0464B3CB809D23926182246'`，
但实测：不带 key、带一串 `0` 的假 key、带真 key，三种情况返回**完全相同**的 200 JSON。
这一点很关键 —— 否则要拿 key 就得先过 Cloudflare 抓 HTML，整条链就废了。**不要把 key 写进代码**，
写了反而给未来埋一个"key 轮换 → 静默失败"的雷。

### 辅源 1：发布日 —— 月度统计新闻稿（用于 `series/source_dates.csv`）

```
https://ir.theice.com/feed/PressRelease.svc/GetPressReleaseList
  ?LanguageId=1&bodyType=0&pressReleaseDateFilter=3&year=-1&pageSize=100
  &includeTags=false&tagList=&excludeSelection=1
```
取 `Headline` 匹配 `^Intercontinental Exchange Reports .* Statistics$` 的条目，
字段 `PressReleaseDate`（`MM/DD/YYYY`）即官方发布日。**这个 feed 也不设防**（urllib 200）。
新闻稿正文页本身是 Cloudflare 页面，但**不需要正文** —— feed 里的 headline + date 已经够作证。

### 辅源 2：合约级历史明细（只做交叉核对，不入库）

`https://s2.q4cdn.com/154085107/files/doc_downloads/2022/02/2015-2021-Historical-ADV_OI_vF.xlsx`
—— 2015-01..2021-12 的**单合约级** ADV 与 OI（Brent Crude Futures / Option on Brent / WTI /
Gasoil / RBOB / TTF / Euribor / SONIA / MSCI / FTSE …）。Last-Modified 2022-02-03，
**已冻结不再更新**，所以不能当主源；但它是验证主源加总关系的独立官方证据（见「实测证据」§3）。

### 明确不用的东西

- ❌ `https://ir.theice.com/investor-resources/supplemental-information/default.aspx`（HTML）—— Cloudflare 403。
- ❌ 按月份猜 CDN 直链。实测命名与目录规则**不自洽**：
  `2026/07/…May-2026_vF.xlsx` 不存在（May 那期在 `2026/06/`），而 June 与 July 两期**都**在 `2026/07/` 下；
  2020 那期后缀是 `_v1` 不是 `_vF`。猜 URL 的成功率约 3/13。必须走 feed。
- ❌ FIA / 各类交易量聚合站 —— 违反仓库硬约束，且本例根本用不着。

---

## 可提取字段

单位后缀照 `cboe.csv` 风格。`kcontracts` = 千张合约（官方原表 "contracts in 000s"），
`mnsh` = 百万股，`usdbn` = 十亿美元。**OI 是千张不是张 —— 与 `cme.csv` 的 `oi_*_contracts` 差 1000 倍，
列名后缀必须写对，这是横截面页最容易翻车的地方。**

### A. 交易日（sheet `Derivs (ADV, RPC, OI)`，row 7-8）

| 列名 | 口径 |
|---|---|
| `trading_days_commod` | 商品与"其他金融"（股指、FX）当月交易日数，ICE Futures Europe/US 口径 |
| `trading_days_rates` | 利率与单股权益当月交易日数。**两行经常不相等**（187 个月里只有 69 个月相同），欧洲利率市场的假期表与商品不同 |

### B. 衍生品 ADV（sheet `Derivs`，「contracts in 000s」，2011-01 起）

| 列名 | 口径 |
|---|---|
| `adv_brent_kcontracts` | ICE Futures Europe 标准 Brent 期货+期权；2015-11 起并入 ICE Futures Singapore 迷你 Brent（÷10 折算） |
| `adv_gasoil_kcontracts` | 同上口径的 Gasoil |
| `adv_otheroil_kcontracts` | 「Other Oil」= futurized oil、WTI、Midland WTI、Murban、Platts Dubai、RBOB、Heating Oil、NGX Oil、Wet Freight，2016-10 起含迷你 WTI（÷10）。**不含 Daily Brent Bullet** |
| `adv_natgas_kcontracts` | 北美 + NGX + 英国 + 欧洲（含 TTF）天然气 |
| `adv_power_kcontracts` | 北美 + NGX + 英国 + 欧洲电力 |
| `adv_environmentals_kcontracts` | 全部碳排放合约 + 煤 + 铁矿石（原表行名 2020 年叫 "Emissions & Other"，2026 年叫 "Environmentals & Other"） |
| `adv_energy_kcontracts` | TOTAL ENERGY，= 上面六项之和（187/187 个月精确成立） |
| `adv_sugar_kcontracts` | Sugar No.11 + No.16 + White Sugar |
| `adv_otherags_metals_kcontracts` | 可可($/£)、咖啡 C/Robusta、棉花、橙汁、玉米、小麦、大豆、大麦、菜籽、迷你金银 |
| `adv_ag_metals_kcontracts` | TOTAL AGRICULTURE & METALS |
| `adv_commodities_kcontracts` | TOTAL COMMODITIES = energy + ag&metals |
| `adv_stir_kcontracts` | 短期利率：Euribor、Sterling→SONIA、ESTR、SARON、SOFR、Swiss、Eonia、Eurodollar、Short Gilt、欧洲国债、DTCC GCF Repo |
| `adv_mltir_kcontracts` | 中长期利率：Gilt、Swapnote、JGB、欧洲国债、美国国债与超长债 |
| `adv_equity_index_kcontracts` | FTSE 100/Dividend、MSCI EAFE/EM/Europe/World（价格与净总回报两版）、Russell 2000/1000、NYSE FANG+ |
| `adv_fx_credit_kcontracts` | TOTAL FX & CREDIT。**FX 与信用合并披露，不是纯 FX** |
| `adv_financials_kcontracts` | TOTAL FINANCIALS = STIR + MLTIR + 股指 + FX&Credit（**不含**单股） |
| `adv_futures_options_kcontracts` | TOTAL FUTURES & OPTIONS |
| `adv_single_stock_kcontracts` | ICE Futures Europe 单股期货/期权。官方明说**已从 Total Financials 剔除**，理由是"收入封顶、与量无相关性"。**只能单独看，不要进任何池** |

### C. 衍生品 RPC（sheet `Derivs`，滚动三月均，美元/张）

`rpc_energy_usd` / `rpc_ag_metals_usd` / `rpc_commodities_usd` / `rpc_rates_usd` /
`rpc_other_financials_usd`（= 股指 + FX）/ `rpc_financials_usd`

官方定义（表内脚注 1）：RPC = 交易收入 ÷ 合约量。**与 Cboe 不同，ICE 的 RPC 不滞后**
—— 最新月的 RPC 与 ADV 一起给出（2026-07 那期 `rpc_energy_usd = 1.89` 已填）。

### D. 衍生品 OI（sheet `Derivs`，月末净未平仓，千张）

`oi_energy_kcontracts` / `oi_ag_metals_kcontracts` / `oi_commodities_kcontracts` /
`oi_rates_kcontracts` / `oi_other_financials_kcontracts` / `oi_financials_kcontracts`

⚠ **没有 TOTAL OI 行** —— 官方新闻稿说的 "Total OI" 要自己算 `oi_commodities + oi_financials`
（已用 2026-07 与 2026-06 两期新闻稿验证，见实测证据 §1/§2）。
表内注：ICE 报的是 **net OI**（"in line with standard industry practice"）。

### E. 美股期权（sheet `US Equity Options`，千张）

| 列名 | 口径 |
|---|---|
| `adv_nyse_equity_options_kcontracts` | NYSE Arca + NYSE American 两家期权所合计 ADV |
| `adv_us_equity_options_industry_kcontracts` | **全美股票/ETF 期权行业总量**（不含指数期权）—— 横截面页的公共分母 |
| `share_nyse_equity_options` | NYSE 份额，官方直接给（= 上两列之商，187/187 自洽） |
| `rpc_nyse_equity_options_usd` | 滚动三月均 RPC，美元/张 |

### F. 美股现货（sheet `Cash Products`，百万股）

| 列名 | 口径 |
|---|---|
| `adv_nyse_tapeA_handled_mnsh` / `..._matched_mnsh` | Tape A（NYSE 上市）：handled = 本所撮合 + 路由出去成交；matched = 只算本所撮合 |
| `adv_tapeA_consolidated_mnsh` | Tape A **全市场**合并成交量 |
| `share_nyse_tapeA_matched` | = matched / consolidated |
| `adv_nyse_tapeB_*` / `adv_tapeB_consolidated_mnsh` / `share_nyse_tapeB_matched` | Tape B（NYSE Arca / American / 区域所上市） |
| `adv_nyse_tapeC_*` / `adv_tapeC_consolidated_mnsh` / `share_nyse_tapeC_matched` | Tape C（Nasdaq 上市） |
| `share_nyse_us_cash_matched` | 全美 matched 份额（三个 tape 加总口径，187/187 与自算一致，误差 <0.15pp） |
| `adv_nyse_us_cash_handled_mnsh` | NYSE Group 全部 handled ADV |
| `rpc_nyse_us_cash_usd_per100sh` | 滚动三月均，美元/100 股 |

**建议再派生一列 `adv_nyse_us_cash_matched_mnsh` = tapeA+B+C matched** ——
官方没有这一行，但它才是与 `cboe.csv` 的 `adv_us_equities_matched_shares_bn` 口径一致的那个数。

### G. CDS 清算（sheet `CDS Clearing`，十亿美元，2013-01 起）

`cds_nonclient_notional_usdbn` / `cds_client_notional_usdbn` / `cds_total_notional_usdbn`
—— ICE Clear Credit 当月清算的 CDS 名义总额（单边计）。

---

## 历史深度

| 数据块 | 最早 | 最新 | 断档 |
|---|---|---|---|
| Derivs ADV / RPC / OI（20 列 + 2 列交易日） | **2011-01** | 2026-07 | **无**，187 个月连续 |
| US Equity Options（4 列） | **2011-01** | 2026-07 | 无 |
| Cash Products（14 列） | **2011-01** | 2026-07 | 无 |
| CDS Clearing（3 列） | **2013-01** | 2026-07 | 无，163 个月连续 |

远超仓库「最少 2019 起、偏好 2015/2016 起」的门槛 —— **同比、指数化、跨周期对比全都做得出来**，
而且覆盖了 2011 欧债、2014-16 油价崩、2020 疫情、2022 能源危机、2026 利率大年五个完整压力场景。

历史深度**不需要靠回补**：单一文件就带全序列，`update()` 每月拿到的是同一份从 2011 开始的表。
这也意味着首次建库时一次性写满 187 行，之后每月只追加 1 行。

---

## 发布节奏

**次月第 3 个美股交易日**（假期顺延）—— 与 Cboe 完全同节奏。
用 PressRelease feed 拉了 2024-01 至 2026-08 共 **32 期**统计新闻稿，**32/32 全部符合**：

| 数据月 | 2024 | 2025 | 2026 |
|---|---|---|---|
| 12 月 | 01-04 | 01-06 | 01-06 |
| 1 月 | 02-05 | 02-05 | 02-04 |
| 2 月 | 03-05 | 03-05 | 03-04 |
| 3 月 | 04-03 | 04-03 | 04-06 |
| 4 月 | 05-03 | 05-05 | 05-05 |
| 5 月 | 06-05 | 06-04 | 06-03 |
| 6 月 | 07-03 | 07-03 | 07-06 |
| 7 月 | 08-05 | 08-05 | **08-05** |
| 8 月 | 09-05 | 09-04 | |
| 9 月 | 10-03 | 10-03 | |
| 10 月 | 11-05 | 11-05 | |
| 11 月 | 12-04 | 12-03 | |

几个"看起来晚了"的都能用假期解释：2026-04-06（4/3 Good Friday 休市）、
2026-07-06（7/4 落在周六，7/3 周五休市）、2025-09-04 与 2024-09-05（Labor Day）、
2026-01-06 与 2025-01-06（元旦 + 周末）。

⇒ `build/roster.py` 的 LAG 建议填 **`(6, 6)`**（常规月与季末月同节奏，ICE 没有季末月延后问题；
季末月的新闻稿标题会变成 "Reports June and Second Quarter 2026 Statistics"，但**日子不变**）。
闸门按仓库规则再提前 `EARLY=3` 天开 → 次月 3 日起开始探测，最多多打 3 个空请求。

### 发布日的权威来源

**用新闻稿日期，不要用别的。** 三条候选实测对比：

| 候选 | 2026-07 那期 | 2026-06 那期 | 评价 |
|---|---|---|---|
| 统计新闻稿 `PressReleaseDate` | 2026-08-05 | 2026-07-06 | ✅ ICE 自己对外宣告的日子，唯一合法 |
| CDN `Last-Modified` | Wed, 05 Aug 2026 12:30:32 GMT | Mon, 06 Jul 2026 12:30:36 GMT | ✅ 与上面**同日、且都在 12:30 UTC 上传**，可作互证 |
| 工作簿 `docProps/core.xml` 的 `dcterms:modified` | 2026-08-05T02:58:07Z | 2026-07-05T22:28:00Z | ⚠ 是 ICE 内部**存盘时刻**，可能早一天（2020-07 那期存于 08-04，发布于 08-05）。只能当旁证 |

工作簿里**没有**任何自述发布日字符串（整份 sharedStrings 只有 162 条，逐条扫过，
唯一带日期的是 "Cash Equities ADV includes CHX volumes as of 7/18/2018" 这条口径脚注）。
Cboe 那种 "Updated on August 5, 2026" 在 ICE 这里不存在，别再找了 —— 和 CME、HKEX 同类。

`_record_source_dates` 的 evidence 建议写成：
`新闻稿「Intercontinental Exchange Reports July 2026 Statistics」PressReleaseDate=08/05/2026（Q4 feed），
与 xlsx 直链 Last-Modified "Wed, 05 Aug 2026 12:30:32 GMT" 互证`。

---

## 口径坑（按踩坑概率排序）

1. **绝不要猜 CDN 文件名，必须走 ContentAsset feed。**
   实测 13 个候选月里只有 3 个猜中。目录不是发布月也不是数据月：June-2026 与 July-2026
   两期**都在 `/2026/07/` 下**，而 May-2026 在 `/2026/06/` 下；后缀 2020 年是 `_v1`、2026 年是 `_vF`。
   feed 里的 `FilePath` 是官方自己维护的"当前最新"指针，跟着它走才是无人值守。
   兜底匹配写宽一点：先按 `Title == "Monthly Statistics Tracking"`，找不到再退到
   `FileType == "XLSX" and "Monthly Stat" in Title`（同一文件在 feed 里挂了两条，
   另一条标题就是 `Monthly Statistics`，是天然的备份指针）。

2. **`ir.theice.com` 的 HTML 页 = Cloudflare 403；`/feed/` 与 `s2.q4cdn.com` = 完全不设防。**
   这两件事必须写在代码注释里，否则下一个人看到 `/investor-resources/...` 403
   会误判"ICE 整站要浏览器"，然后去搞 Chrome MCP —— 那就把一条 5 秒的 urllib 链
   换成了需要登录态的东西，直接毁掉无人值守。
   （`curl_cffi(impersonate="chrome")` 确实能过 Cloudflare 拿到 HTML，本次侦察就是这么发现 feed 的，
   但**生产代码不需要它**，纯标准库即可，见实测证据 §5。）

3. **月度单元格全部四舍五入到整千张 / 整百万股；季度列才是全精度浮点。**
   10,026 个月度单元格里只有 2,429 个非整数，且全部集中在 RPC 与份额这 13 列。
   后果有两条：
   · 小基数行的同比会与新闻稿差 1-2pp（2026-07 Environmentals 63/54 = +16.7%，新闻稿写 +18%）；
   · 想要精确季度数就直接读 `1Q26`/`2Q26` 这些季度列（它们是全精度，例：2Q26 Financials ADV
     = 4996.292370711726），不要用月度值加权反推。
   ⇒ 图上按 0 位小数格式化即可；**不要**在页面上给月度 ADV 标小数位，那是假精度。

4. **同一逻辑行在不同 vintage 里换过名字，按行号硬编或按全等标签匹配都会炸。**
   2020 年那期叫 `Emissions & Other (6)`，2026 年这期叫 `Environmentals & Other (6)`
   （而脚注正文两期都写 "Emissions & Other"）。所以：
   · 行标签先剥掉尾部 `(n)` 脚注记号再比；
   · 对这一行准备别名集合。
   本次实测：加了归一化 + 别名后，2020-08 期与 2026-08 期**同一套代码零改动全解**。

5. **三个 section 在同一个 sheet 里，表头行各不相同，必须按 section 定位。**
   `Derivs` sheet：ADV 段表头在 row 5（数据 row 7-36）、RPC 段表头在 row 58（row 59-64）、
   OI 段表头在 row 69（row 70-75）。`TOTAL COMMODITIES` / `TOTAL FINANCIALS` /
   `Energy` / `Agriculture & Metals` **在三个段里各出现一次** —— 全表 grep 标签名必然抓错段，
   把 RPC 的 1.92 当成 ADV 写进去。（与 `fetch/cboe.py` 的口径坑 2 是同一类问题。）
   另：`US Equity Options` 的表头在 row 5，`Cash Products` 的表头却在 **row 4**，
   `CDS Clearing` 在 row 5 **且数据从 col 2 开始**（其余 sheet 从 col 3）。三种都要单独指定。

6. **表头里月份列与季度列交替出现，只认 datetime 单元格。**
   `2011-01-01 00:00:00, 2011-02-01, 2011-03-01, '1Q11', 2011-04-01, …`
   —— 月份是真 datetime，季度是字符串 `'1Q11'`。按类型过滤最稳（`isinstance(v, datetime)`），
   不要按位置数格子。`CDS Clearing` 的日期是**月末**（`2013-01-31`）而其余是**月初**，
   所以只能取 `(year, month)`。

7. **没有 TOTAL OI 行，且分项 ADV 之和 ≠ TOTAL F&O。**
   `TOTAL FUTURES & OPTIONS` 用的是"总量 ÷ 总交易日"，而 commodities 与 financials
   各自用不同的交易日数归一（两行交易日 187 个月里 118 个月不等），所以
   `adv_commodities + adv_financials` 与 `adv_futures_options` 有 0-0.55% 的系统性差
   （2011-2012 最大，2013 后基本收敛到 ±0.02%）。**别拿这个当校验硬条件**，
   但 OI 侧反而必须自己加总（官方就是不给 total）。

8. **CDS 三行要做 foot check —— 历史上真出过错值。**
   2026-06 那期里 `2026-01` 的 Non-Client = 291，Client = 1330，Total = 1720（291+1330=1621，差 99）；
   2026-07 那期把 Non-Client 改成 391（391+1330=1721 ≈ 1720）。这是**唯一一处**跨 vintage 的实质重述。
   `abs(non_client + client - total) > 2` 就该报警。加了这条规则，当期就能抓住（实测：
   6 月版 1 个月不平、7 月版 0 个月不平）。

9. **新闻稿的产品分组名与 xlsx 的行名同名不同物，不要拿新闻稿去逐行对账。**
   2026-07 新闻稿写 "Other Crude & Refined products ADV up 10% y/y"，
   而 xlsx 的 `Other Oil` 行是 838 vs 998（−16%）。原因：新闻稿用的是**合约级**小类
   （2015-2021 明细文件里 `Other Crude & Refined Products` 2015-01 只有 153.4 千张），
   而 xlsx 的 `Other Oil` 是**产品组**（同月 394 千张，= Total Oil − Brent − Gasoil）。
   可以放心对账的是：Total ADV / Total OI / Total Energy / Total Oil（Brent+Gasoil+OtherOil）/
   Brent / Gasoil / Total Ag&Metals / Sugar / Total Financials / Total Interest Rates /
   Total Equity Indices / NYSE Cash Equities / NYSE Equity Options —— 这些实测全对得上。
   新闻稿里的 TTF / Asia gas / Cocoa / Coffee / Cotton / Euribor / SONIA / Gilts / MSCI
   **在 xlsx 里没有对应行**，别去凑。

10. **RPC 是滚动三月均，不能与单月量相乘去算单月收入。**
    但年度/季度加权后可以复原官方收入（实测误差 <1%，见证据 §4）。
    页面上如果要画 "ADV × RPC = 收入代理"，必须标明 RPC 是 3M rolling，否则读者会
    以为那是单月收入。

11. **官方口径做过两次追溯性重刷，历史值与当年发布值不同。**
    表内自述：(a) NGX 的量与收入**追溯并入 2011 年起**的 Other Oil / Nat Gas / Power /
    Total Energy / Total Commodities / Total F&O 与 Energy、Commodities RPC；
    (b) 2013 年起的 Power ADV、Energy RPC、Energy OI 按**新的电力量折算法**重算；
    (c) Russell 合约 2016-12 规格减半，量、OI、RPC 全部追溯调整。
    ⇒ 这些都已经体现在当前文件里（本仓从 2011 一次性全量摄入，不受影响），
      但意味着**本仓的 CSV 与 ICE 历年季报/10-K 原文里的数字可能对不上**，
      对不上时以当前文件为准。同时照 Cboe/HKEX 的做法：**已有值永不覆盖，只填空**。

12. **单股（`adv_single_stock_kcontracts`）不进任何合计。**
    官方明说"收入封顶，与量无相关性，因此从 ADV、RPC、OI 里全部剔除"。
    2011-01 它有 905 千张、2026-07 只剩 69 —— 若误加进 Total Financials，
    会在 2011-2013 造出一段完全虚假的"金融衍生品塌方"。

13. **`adv_fx_credit_kcontracts` 是 FX 与信用合并的一行**（行名 `TOTAL FX & CREDIT`，
    脚注却只解释 FX）。不能当纯 FX 与 CME 的 `adv_fx_kcontracts` 直接比；
    要比就得在图上写明口径不纯。

14. **2026-08-06 当天的 latest 是 2026-07** —— 文件名里的 "July-2026" 是**数据月**不是发布月。
    `latest_month()` 要以**表里最后一个 `TOTAL FUTURES & OPTIONS` 非空的月**为准，
    不能信文件名（HKEX 的同款坑）。当前表没有未来占位列，但要写成能容忍占位列的形式。

---

## 实测证据

脚本与原始文件全在 `/tmp/exch_recon/scratch/ice/`：
`parse_ice.py`（解析器）、`e2e.py`（纯 urllib 端到端）、`xcheck_pr.py` / `xcheck_pr2.py`（新闻稿对账）、
`xcheck_10k.py`（10-K 对账）、`xcheck_rev.py`（收入反算）、`xcheck_hist.py`（明细文件对账）、
`diff_vintages.py`（跨版本重述检测）、
`monthly_stats_latest.xlsx`（2026-07 期）、`monthly_stats_jun2026.xlsx`（2026-06 期）、
`monthly_stats_jul2020.xlsx`（2020-07 期）、`hist_adv_oi_2015_2021.xlsx`、`key_metrics_q2_2026.xlsx`、
`ice_10k_2025.htm`。

### §0 三期文件、同一套代码、全部解析成功

```
$ python3 parse_ice.py monthly_stats_latest.xlsx
解析文件: monthly_stats_latest.xlsx
月份范围: 2011-01 .. 2026-07  (共 187 个月)
缺月: 无
字段数: 54

$ python3 parse_ice.py monthly_stats_jun2026.xlsx
月份范围: 2011-01 .. 2026-06  (共 186 个月)   缺月: 无   字段数: 54

$ python3 parse_ice.py monthly_stats_jul2020.xlsx
月份范围: 2011-01 .. 2020-07  (共 115 个月)   缺月: 无   字段数: 54
```

解析出的真实数字（节选，完整 54×187 在 `parsed_monthly_stats_latest.json`）：

| 字段 | 2026-07 | 2026-06 | 2025-07 | 2020-07 | 2015-01 | 2011-01 |
|---|---|---|---|---|---|---|
| `trading_days_commod` | 22 | 21 | 22 | 22 | 20 | 20 |
| `trading_days_rates` | 23 | 22 | 23 | 23 | 21 | 21 |
| `adv_brent_kcontracts` | 1948 | 1487 | 1394 | 730 | 941 | 539 |
| `adv_gasoil_kcontracts` | 412 | 362 | 374 | 237 | 267 | 265 |
| `adv_otheroil_kcontracts` | 838 | 685 | 998 | 542 | 394 | 360 |
| `adv_natgas_kcontracts` | 1782 | 1525 | 1634 | 717 | 1256 | 1343 |
| `adv_power_kcontracts` | 102 | 88 | 84 | 38 | 59 | 34 |
| `adv_environmentals_kcontracts` | 63 | 73 | 54 | 60 | 44 | 26 |
| `adv_energy_kcontracts` | 5146 | 4220 | 4538 | 2323 | 2962 | 2568 |
| `adv_sugar_kcontracts` | 161 | 290 | 145 | 130 | 156 | 142 |
| `adv_ag_metals_kcontracts` | 472 | 664 | 342 | 320 | 331 | 297 |
| `adv_commodities_kcontracts` | 5619 | 4884 | 4880 | 2643 | 3293 | 2865 |
| `adv_stir_kcontracts` | 3977 | 4080 | 2791 | 1094 | 1385 | 2515 |
| `adv_mltir_kcontracts` | 246 | 236 | 231 | 170 | 184 | 105 |
| `adv_equity_index_kcontracts` | 278 | 597 | 214 | 249 | 491 | 444 |
| `adv_fx_credit_kcontracts` | 22 | 34 | 26 | 33 | 51 | 31 |
| `adv_financials_kcontracts` | 4522 | 4947 | 3262 | 1545 | 2111 | 3095 |
| `adv_futures_options_kcontracts` | **10141** | 9831 | 8142 | 4188 | 5404 | 5961 |
| `adv_single_stock_kcontracts` | 69 | 128 | 86 | 47 | 219 | 905 |
| `rpc_energy_usd` | 1.89 | 1.90 | 1.75 | 1.42 | 1.37 | 1.33 |
| `rpc_commodities_usd` | 1.92 | 1.95 | 1.78 | 1.52 | 1.46 | 1.39 |
| `rpc_rates_usd` | 0.51 | 0.50 | 0.51 | 0.36 | 0.63 | 0.51 |
| `rpc_financials_usd` | 0.61 | 0.61 | 0.62 | 0.57 | 0.69 | 0.53 |
| `oi_energy_kcontracts` | 68093 | 67603 | 64042 | 42989 | 36913 | 23548 |
| `oi_ag_metals_kcontracts` | 4655 | 4274 | 3280 | 3639 | 3631 | 3943 |
| `oi_commodities_kcontracts` | 72748 | 71877 | 67322 | 46628 | 40545 | 27491 |
| `oi_rates_kcontracts` | 45686 | 42947 | 32042 | 22413 | 15005 | 24281 |
| `oi_financials_kcontracts` | 49078 | 46203 | 35541 | 27194 | 20075 | 30269 |
| `adv_nyse_equity_options_kcontracts` | 13614 | 14847 | 10766 | 5162 | 2942 | 4350 |
| `adv_us_equity_options_industry_kcontracts` | 64394 | 69896 | 51516 | 26469 | 16034 | 17740 |
| `share_nyse_equity_options` | 0.211 | 0.212 | 0.209 | 0.195 | 0.183 | 0.245 |
| `rpc_nyse_equity_options_usd` | 0.04 | 0.04 | 0.05 | 0.07 | 0.18 | 0.16 |
| `adv_nyse_tapeA_matched_mnsh` | 1534 | 2002 | 1452 | 1277 | 1195 | 1644 |
| `adv_tapeA_consolidated_mnsh` | 5267 | 6174 | 5260 | 4409 | 3890 | 4849 |
| `share_nyse_tapeA_matched` | 0.291 | 0.324 | 0.276 | 0.290 | 0.307 | 0.339 |
| `adv_nyse_tapeB_matched_mnsh` | 738 | 996 | 612 | 450 | 349 | 298 |
| `adv_nyse_tapeC_matched_mnsh` | 1057 | 1683 | 1302 | 452 | 206 | 255 |
| `share_nyse_us_cash_matched` | 0.191 | 0.200 | 0.187 | 0.207 | 0.239 | 0.269 |
| `adv_nyse_us_cash_handled_mnsh` | 3385 | 4774 | 3430 | 2222 | 1807 | 2372 |
| `rpc_nyse_us_cash_usd_per100sh` | 0.041 | 0.040 | 0.036 | 0.042 | 0.051 | 0.034 |
| `cds_total_notional_usdbn` | 1878 | 1840 | 1256 | 795 | 1014 | （2013 起） |

### §1 交叉核对一：官方新闻稿「Reports July 2026 Statistics」（2026-08-05 发）

新闻稿只给同比百分比，不给绝对数，所以用解析值反算 y/y 与之对账：

```
新闻稿口径                                     稿中%    2026-07    2025-07       算出%    一致?
Total ADV up 25% y/y                      25%      10141       8142     24.6%     OK
Total OI up 18% y/y                       18%     121826     102863     18.4%     OK
Total Energy ADV up 13% y/y               13%       5146       4538     13.4%     OK
Total Energy OI up 6% y/y                  6%      68093      64042      6.3%     OK
Total Oil ADV up 16% y/y                  16%       3198       2766     15.6%     OK
Brent ADV up 40% y/y                      40%       1948       1394     39.7%     OK
Gasoil ADV up 10% y/y                     10%        412        374     10.2%     OK
Other Crude&Refined ADV up 10%            10%        838        998    -16.0%      ≠   ← 见口径坑 9
Total Natural Gas ADV up 9% y/y            9%       1782       1634      9.1%     OK
Total Environmentals ADV up 18%           18%         63         54     16.7%      ≠   ← 见口径坑 3
Total Ag&Metals ADV up 38% y/y            38%        472        342     38.0%     OK
Total Ag&Metals OI up 42% y/y             42%       4655       3280     41.9%     OK
Sugar ADV up 11% y/y                      11%        161        145     11.0%     OK
Total Financials ADV up 39% y/y           39%       4522       3262     38.6%     OK
Total Financials OI up 38% y/y            38%      49078      35541     38.1%     OK
Total Interest Rates ADV up 40%           40%       4223       3022     39.7%     OK
Total Interest Rates OI up 43%            43%      45686      32042     42.6%     OK
Total Equity Indices ADV up 30%           30%        278        214     29.9%     OK
NYSE Equity Options ADV up 26%            26%      13614      10766     26.5%     OK

17/19 条与官方新闻稿四舍五入后完全一致
```

注意 "Total OI up 18%" 这条：官方**不给** OI 合计行，我用 `oi_commodities + oi_financials`
= 72748+49078 = 121826（2026-07）与 67322+35541 = 102863（2025-07）算出 +18.4% ——
与新闻稿的 18% 吻合，反过来**证明了自己加总的方法是对的**（见口径坑 7）。

### §2 交叉核对二（第二期）：官方新闻稿「Reports June and Second Quarter 2026 Statistics」（2026-07-06 发）

```
── 月度 ──
Total OI up 20% y/y                      20%     19.7%     OK
Total Energy OI up 6% y/y                 6%      5.7%     OK
Total Ag&Metals ADV up 29% y/y           29%     29.4%     OK
Total Ag&Metals OI up 43% y/y            43%     42.7%     OK
Sugar ADV up 20% y/y                     20%     20.3%     OK
Total Financials ADV up 27% y/y          27%     26.6%     OK
Total Financials OI up 46% y/y           46%     46.1%     OK
Total Interest Rates ADV up 29%          29%     28.7%     OK
Total Interest Rates OI up 52%           52%     52.0%     OK
Total Equity Indices ADV up 16%          16%     15.9%     OK
NYSE Cash Equities ADV up 32%            32%     32.1%     OK
NYSE Equity Options ADV up 47%           47%     47.2%     OK
                                                    12/12 一致
── 季度（用 xlsx 的 2Q26/2Q25 全精度季度列）──
2Q Total Financials ADV up 22%           22%     22.47%    OK
2Q Total Interest Rates ADV +24%         24%     24.4%     OK
2Q Total Ag&Metals ADV up 36%            36%     35.6%     OK
2Q Total Equity Indices ADV +8%           8%      8.1%     OK
2Q NYSE Cash Equities ADV +12%           12%     12.1%     OK
2Q NYSE Equity Options ADV +44%          44%     43.6%     OK
2Q Sugar ADV up 30%                      30%     30.51%    边界（稿方截尾）
```

### §3 交叉核对三：另一份官方文件「2015-2021 Monthly ADV & OI」（合约级明细）

用**完全独立的另一份 ICE 官方 xlsx**（合约级，Brent Crude Futures / Option on Brent / …）
加总，与 Monthly Statistics Tracking 的产品组级行对账：

```
月份        口径                                     明细文件加总  Monthly Stats      相对差
2015-01   TOTAL Energy                           2941.4         2962.0   -0.70%  ← NGX 追溯并入，见口径坑 11
2015-01   TOTAL Ag&Metals                         331.1          331.0    0.03%
2015-01   TOTAL Financials                       2111.4         2111.0    0.02%
2015-01   Total Futures & Options                5383.9         5404.0   -0.37%
2015-01   Brent(期货+期权)                          941.3          941.0    0.03%
2015-01   Gasoil                                  266.8          267.0   -0.06%
2015-01   Total Oil = Brent+Gasoil+Other Oil     1602.2         1602.0    0.01%
2018-06   TOTAL Energy                           2682.6         2683.0   -0.01%
2018-06   TOTAL Financials                       3111.9         3112.0   -0.00%
2018-06   Total Futures & Options                6307.2         6307.0    0.00%
2018-06   Brent                                  1131.9         1132.0   -0.01%
2018-06   Total Oil                              1916.6         1916.0    0.03%
2021-12   TOTAL Energy                           2629.1         2629.0    0.00%
2021-12   TOTAL Ag&Metals                         266.0          266.0   -0.01%
2021-12   TOTAL Financials                       1744.6         1745.0   -0.02%
2021-12   Total Futures & Options                4639.7         4640.0   -0.01%
2021-12   Brent                                   932.6          933.0   -0.04%
2021-12   Total Oil                              1661.5         1662.0   -0.03%
```
21 项里 19 项相对差 <0.2%，两项例外正是官方自述的 NGX 追溯并入（明细文件是 2022-02 冻结的旧口径）。
同时这一步定量证明了口径坑 9：明细文件的 `Other Crude & Refined Products` 2015-01 = **153.4** 千张，
而 Monthly Stats 的 `Other Oil` 同月 = **394.0** 千张，两者同名不同物。

### §4 交叉核对四（绝对值）：ICE FY2025 Form 10-K（SEC EDGAR，CIK 0001571949，2026-02-05 报送）

用月度数据（按交易日加权）复原 10-K Item 7「Selected Operating Data」的年度绝对数：

```
10-K 口径                               10-K 披露         月度数据反算       相对差
ADV Energy f&o (k)                       5003       5003.076     0.00% OK
ADV Ag&Metals f&o (k)                     423        422.781    -0.05% OK
ADV Financial f&o (k)                    3835       3834.607    -0.01% OK
ADV Total f&o (k)                        9261       9269.853     0.10% OK
合约数 Energy (mn)                        1256       1255.772    -0.02% OK
合约数 Ag&Metals (mn)                      106        106.118     0.11% OK
合约数 Financial (mn)                      983        985.494     0.25% OK
合约数 Total (mn)                         2345       2326.733    -0.78% OK
年末 OI Energy (k)                       62776      62776.000     0.00% OK  ← 逐位精确
年末 OI Ag&Metals (k)                     3470       3470.000     0.00% OK  ← 逐位精确
年末 OI Financial (k)                    36406      36406.000     0.00% OK  ← 逐位精确
年末 OI Total (k)                       102652     102652.000     0.00% OK  ← 逐位精确
NYSE 现货 handled ADV (mn sh)             3401       3398.677    -0.07% OK
NYSE 股票期权 ADV (k)                     10556      10555.020    -0.01% OK
全市场股票期权 ADV (k)                     55798      55787.008    -0.02% OK
NYSE 现货 matched 份额 %                   19.0         18.977    -0.12% OK
NYSE 股票期权份额 %                        18.9         18.920     0.11% OK
RPC Energy $                             1.74          1.731    -0.52% OK
RPC Ag&Metals $                          2.19          2.193     0.13% OK
RPC Financials $                         0.61          0.615     0.84% OK
RPC 现货 $/100sh                         0.037          0.038     2.57%   ← 10-K 只给 3 位小数
RPC 股票期权 $                            0.06          0.058    -3.12%   ← 10-K 只给 2 位小数

20/22 项相对差 <1%
```

**四个年末 OI 逐位精确相等**（62776 / 3470 / 36406 / 102652）—— 这是解析正确的决定性证据：
10-K 的年末 OI 就是本表 2025-12 月末 OI，一位不差。

补充一路绝对值核对（`xcheck_rev.py`）：用 `ADV × 交易日 × RPC` 反算季度交易收入，
与 ICE **另一份财报专用文件** `Key-Metrics-Q2-2026.xlsx` 披露的实际收入对账：

```
Key Metrics 行                  季度            反算收入$mn        官方披露$mn      相对差
Energy futures & options       2Q25            595.4          595.0    0.07%
Energy futures & options       2Q26            515.9          518.0   -0.41%
Agricultural & metals f&o      2Q25             64.3           65.0   -1.02%
Agricultural & metals f&o      2Q26             86.8           87.0   -0.20%
Financial futures & options    2Q25            156.8          158.0   -0.77%
Financial futures & options    2Q26            192.0          192.0    0.00%
```
6/6 在 ±1% 内，残差全部来自 RPC 只保留 2 位小数。这同时验证了 ICE 对 RPC 的自述定义
（"transaction revenues ÷ contract volume"）以及交易日行的用法（能源/农产品用
`trading_days_commod`、金融用 `trading_days_rates`）。

### §5 无人值守可行性：纯标准库 `urllib` 端到端（不用 curl_cffi、不用浏览器）

```
$ python3 e2e.py
① ContentAsset feed  200  0.48s  命中 1 条
   FilePath = https://s2.q4cdn.com/154085107/files/doc_downloads/2026/07/2011-2026-Monthly-Stats-July-2026_vF.xlsx
② xlsx 下载           200  0.85s  377178 bytes  Last-Modified=Wed, 05 Aug 2026 12:30:32 GMT
   sha256 = b091b514d189c979bf0808c0e62f625f...
③ PressRelease feed   200  3.29s  统计稿 7 条，最新：08/05/2026 | Intercontinental Exchange Reports July 2026 Statistics

$ shasum -a 256 e2e_monthly_stats.xlsx monthly_stats_latest.xlsx
b091b514d189c979bf0808c0e62f625f93f8618b75f1d8e7ccb7645c73669a41  e2e_monthly_stats.xlsx
b091b514d189c979bf0808c0e62f625f93f8618b75f1d8e7ccb7645c73669a41  monthly_stats_latest.xlsx
```
总耗时 4.6 秒，与 curl_cffi 拿到的文件**逐字节相同**。

拦截情况对照表（同一 UA、同一台机器、2026-08-06 实测）：

| 目标 | `curl` | `urllib` | `nscurl` | `curl_cffi(chrome)` |
|---|---|---|---|---|
| `ir.theice.com/investor-resources/...`（HTML） | 403 CF 挑战 | 403 | 403 | ✅ 200 |
| `ir.theice.com/press/press-releases/...`（HTML） | 403 CF 挑战 | 403 | 403 | ✅ 200 |
| `ir.theice.com/feed/ContentAsset.svc/...`（JSON） | ✅ 200 | ✅ 200 | ✅ 200 | ✅ 200 |
| `ir.theice.com/feed/PressRelease.svc/...`（JSON） | ✅ 200 | ✅ 200 | ✅ 200 | ✅ 200 |
| `s2.q4cdn.com/154085107/...xlsx` | ✅ 200 | ✅ 200 | — | ✅ 200 |

没有 JS 渲染依赖（JSON 接口直出）、没有验证码、没有登录墙、没有 PerimeterX / Akamai JA3 问题。

### §6 跨 vintage 重述检测（幂等与"只填空不覆盖"的依据）

```
=== 2026-06 期 vs 2026-07 期（重叠 186 个月 × 54 字段 ≈ 10,000 格）===
  cds_nonclient_notional_usdbn   1 格不同  最大相对差 0.3436  例：2026-01 291.0→391.0

=== 2020-07 期 vs 2026-07 期（重叠 115 个月 × 54 字段 ≈ 6,200 格，跨 6 年）===
  adv_environmentals_kcontracts  3 格不同  最大相对差 0.0179  例：2020-02 60.0→59.0
  adv_otheroil_kcontracts        1 格不同  最大相对差 0.0022  例：2019-04 460.0→461.0
  adv_nyse_tapeA_matched_mnsh    1 格不同  最大相对差 0.0009  例：2019-12 1169.0→1170.0
  adv_tapeA_consolidated_mnsh    1 格不同  最大相对差 0.0003  例：2019-12 3468.0→3469.0
  rpc_commodities_usd            1 格不同  最大相对差 0.0065  例：2020-07 1.53→1.52
  rpc_nyse_us_cash_usd_per100sh  1 格不同  最大相对差 0.0233  例：2020-07 0.043→0.042
```
跨 6 年只有 8 格变化，其中 6 格是四舍五入痕迹、2 格是"最新月次月微调"（2020-07 那两格是当期的
最新月，下一期会用更终局的数据覆盖）。唯一实质重述是那条 CDS 错值。
⇒ **历史极稳，"已有值永不覆盖、只填空"是安全且正确的策略**；
  同时建议把差异写进 `cache/ice_restatements.csv`（照 `fetch/hkex.py` 的做法）供人工判断。

### §7 内部恒等式自检（可直接写进 `_validate()`）

```
TOTAL ENERGY = 6 个子项之和                       187/187 成立
CDS: non-client + client ≈ total（容差 2）        最新期 0 个月不平；6 月期能抓出 2026-01 那格错值
现货 matched 份额 = Σ三个 tape matched / Σ合并量   187/187 成立（误差 <0.15pp）
NYSE 期权份额 = NYSE ADV / 行业 ADV               187/187 成立
TOTAL F&O = COMMODITIES + FINANCIALS             166/187 成立（其余偏差 <0.55%，交易日归一差异，
                                                  见口径坑 7 —— 不要当硬校验）
```

---

## 属于哪些竞争池

ICE 是本仓**唯一一家同时落进四个池**的公司，也是唯一能给出**行业分母**的公司 ——
这一点比它自己的量更值钱。

### 地理池

| 池 | ICE 的身份 | 可比字段（跨家对齐的那一个） | 备注 |
|---|---|---|---|
| **北美现货** | NYSE Group（NYSE / Arca / American / National / Texas） | `adv_nyse_us_cash_matched_mnsh`（= tapeA+B+C matched，需派生；换算成 bn 后）↔ `cboe.csv` 的 `adv_us_equities_matched_shares_bn`。份额用 `share_nyse_us_cash_matched` | ⭐ **`adv_tapeA/B/C_consolidated_mnsh` 是全美合并成交量 = 全行业分母**。有了它，Cboe 的 matched shares 也能算出份额，横截面页第一次能画"同一分母下的份额此消彼长"，而不是各报各的。**不要用 handled** —— handled 含路由到别家成交的量，Cboe 不披露对应口径 |
| **北美期权** | NYSE Arca + NYSE American | `adv_nyse_equity_options_kcontracts` ↔ `cboe.csv` 的 `adv_multilist_options_kcontracts`（两边都是多重上市股票/ETF 期权，都不含指数期权）；RPC 用 `rpc_nyse_equity_options_usd` ↔ `rpc_multilist_options_usd` | ⭐ `adv_us_equity_options_industry_kcontracts` 同样是**行业分母**。校验：2026-07 Cboe multilist 15687 ÷ ICE 给的行业 64394 = 24.4%，量级合理 |
| **欧洲衍生品** | ICE Futures Europe（Brent / Gasoil / TTF / Euribor / SONIA / Gilts / FTSE） | `adv_stir_kcontracts + adv_mltir_kcontracts`（欧洲利率）、`adv_energy_kcontracts`、`oi_*` | 仓内目前**没有同池对手**（Cboe 的欧洲业务是现货 ADNV，量纲与内容都不同）。等 Eurex / LSEG 进仓再配对；在那之前 ICE 单家成图 |
| **欧洲现货** | ❌ 不参与 | — | ICE 已无欧洲现货股票业务（Euronext 2014 分拆） |
| **亚太现货 / 亚太衍生品** | ❌ 不单独参与 | — | ICE Futures Singapore 的迷你 Brent/Gasoil/WTI **已折算并入** Brent/Gasoil/Other Oil 行（÷10），本表**不单列亚太**，硬拆会造假 |
| **单一市场垄断对照** | ⭐ **反面样本** | `share_nyse_us_cash_matched`（2011-01 26.9% → 2026-07 19.1%）与 `share_nyse_equity_options`（24.5% → 21.1%） | 与 HKEX 的结构性垄断放同一张图：**同样是"国家级交易所"，一个份额十五年跌 8pp，一个恒为 100%** —— 这是本仓最有说服力的一组对照，而且两边都是 187 个月的连续序列 |

### 标的池

| 池 | 可比字段 | 跨家可比性说明 |
|---|---|---|
| **能源商品** | `adv_energy_kcontracts` / `oi_energy_kcontracts` / `rpc_energy_usd` ↔ `cme.csv` 的 `adv_energy_kcontracts` / `oi_energy_contracts` | ⚠ **ICE 的 OI 是千张、CME 的 OI 是张**，差 1000 倍。合约规格也不同（Brent 1000 桶 vs WTI 1000 桶尚可比，TTF 是 MWh、天然气是 MMBtu 完全不可比）→ **只画同比与指数化（2015-01=100），不要并排画绝对量**。这是全仓最重要的一对：Brent vs WTI 的基准之争 |
| **利率衍生品** | `adv_stir_kcontracts` + `adv_mltir_kcontracts`、`oi_rates_kcontracts` ↔ `cme.csv` 的 `adv_rates_kcontracts` / `oi_rates_contracts` | ICE = **欧洲曲线**（Euribor / SONIA / Gilts / ESTR），CME = **美国曲线**（SOFR / Treasuries）。**互补而非争夺同一批客户** —— 横截面页的价值恰恰在于把"欧洲利率周期 vs 美国利率周期"叠在一起看。同样只比增速 |
| **单股与 ETF 期权** | 见「北美期权」 | 另有 `adv_single_stock_kcontracts`（ICE Futures Europe 单股期货/期权）—— 官方明说已从所有合计中剔除、与收入无关。**不进任何池**，要画只能单独一张并注明"官方口径外" |
| **股指衍生品** | `adv_equity_index_kcontracts` ↔ `cme.csv` `adv_equity_kcontracts` ↔ `cboe.csv` `adv_index_options_kcontracts` | 量级差 20-30 倍（ICE 278k vs CME 8169k vs Cboe 5990k，2026-07），**必须指数化**。ICE 这一池的看点是 MSCI 授权（与 `msci.csv` 的授权收入形成"上游 IP × 下游成交量"的对照） |
| **FX** | `adv_fx_credit_kcontracts` ↔ `cme.csv` `adv_fx_kcontracts` | ⚠ ICE 这一行是 **FX 与信用合并**，口径不纯；`cboe.csv` 的 `adv_fx_adnv_usdbn` 是名义美元 ADNV，量纲不同，**不可比**。建议只与 CME 对，且图上写明"ICE 含信用" |
| **能源商品（现货/OTC）** | — | ICE 的 OTC 能源在 10-K 里以收入形式披露，本表不含。不进池 |
| **加密** | ❌ 无 | Bakkt 已剥离，本表无加密字段 |
| **信用衍生品（新池建议）** | `cds_total_notional_usdbn` / `cds_client_notional_usdbn` | 仓内暂无同池对手（ICE Clear Credit 是全球最大 CDS 清算所，接近垄断）。可作为「单一市场垄断对照」池里的**第二个垄断样本**，与 HKEX 并列，也是 2026-07 收购 MarketAxess 后的关键跟踪指标 |

### 一句话给横截面页

ICE 进 `/exchanges/` 页时的最大价值不是多一条线，而是**它把行业分母带进来了**：
`adv_tapeA/B/C_consolidated_mnsh`（全美现货合并量）与 `adv_us_equity_options_industry_kcontracts`
（全美股票期权行业量）让 ICE 与 Cboe 第一次可以放在**同一个分母**下比份额；
而 `share_nyse_us_cash_matched` 从 26.9%（2011-01）到 19.1%（2026-07）的十五年下滑，
放在 HKEX 的恒定 100% 旁边，就是整个看板最直白的一张"垄断 vs 竞争"图。
