# 复核报告 · ICE 月度数据源侦察

复核日期 2026-08-06 · slug `ice` · 原判定 **A** · **复核判定 A（维持）**

复核方式：不看原 agent 的脚本、不用它的中间产物，自己重写解析器、自己重抓全部链路。
我的工作目录：`/private/tmp/claude-501/-Users-hainan-Library-CloudStorage-OneDrive-Personal/00bde884-5d9d-4ce5-a363-6b721a0462f5/scratchpad/`
（`ice_verify_parse.py` = 我自己的解析器，行号映射独立写的；`ice_latest.xlsx` / `ice_jun2026.xlsx` /
`ice_jul2020.xlsx` / `hist.xlsx` / `pr_jul2026.pdf` / `pr_jun2026.pdf` / `ice_10k.htm` = 我自己抓的原始文件。）

---

## 一句话结论

**复现成功，A 维持。** 抓取链、解析结果、三路交叉核对我全部独立跑通，
声称的 245 个数字我用自己的解析器逐个比对，**0 处不一致**；
从 SEC EDGAR 独立取回的 FY2025 10-K 年末 OI 与我解析出的 2025-12 **逐位相等**。
不存在「只抓到最新一期假装有历史」「拿第三方聚合站冒充官方」「靠浏览器登录态」这三类虚报。

但报告的**注解层**有 6 处实质错误（不是数据错，是给实现阶段的指导错），
其中 2 处照抄进代码会直接出问题：§7 的恒等式阈值、§5 的 Cloudflare 判断。
另有 1 处竞争池论断（ICE vs HKEX）建立在仓内根本不存在的字段上。

---

## 一、我实际复现了什么

### 1.1 抓取链（纯标准库、冷启动、无 cookie / 无 key / 无浏览器）

```
feed  0.65s  ContentAsset.svc/GetContentAssetList  → 命中 Title=="Monthly Statistics Tracking" 1 条
xlsx  2.85s  s2.q4cdn.com/.../2011-2026-Monthly-Stats-July-2026_vF.xlsx  377,178 B
pr    3.36s  PressRelease.svc/GetPressReleaseList  → 08/05/2026 | ...Reports July 2026 Statistics
TOTAL 3.36s
sha256 = b091b514d189c979bf0808c0e62f625f93f8618b75f1d8e7ccb7645c73669a41
```

- **与原 agent 的 `monthly_stats_latest.xlsx` 逐字节相同**（sha256 一致）。
- `apiKey` 我一次都没传，全程 200。原报告「key 可省略、不要写进代码」**属实**。
- `Last-Modified: Wed, 05 Aug 2026 12:30:32 GMT`，与新闻稿日 2026-08-05 同日 —— 互证成立。
- `docProps/core.xml` 的 `dcterms:modified`：latest=2026-08-05T02:58:07Z、
  jun2026=2026-07-05T22:28:00Z、jul2020=**2020-08-04**T20:19:13Z —— 三个都与原报告一字不差，
  包括「2020-07 那期存盘早一天」这个论据。

### 1.2 我自己的解析器（独立行号映射，不看它的 `parse_ice.py`）

```
ice_latest.xlsx   months 187  2011-01 .. 2026-07  gaps: none  fields 54
ice_jun2026.xlsx  months 186  2011-01 .. 2026-06  gaps: none  fields 54
ice_jul2020.xlsx  months 115  2011-01 .. 2020-07  gaps: none  fields 54
```

表结构与原报告描述完全一致：`Derivs` sheet ADV 表头 row 5 / RPC row 58 / OI row 69；
`US Equity Options` row 5 与 row 15；`Cash Products` row **4** 与 row 34；
`CDS Clearing` row 5 且**从 col 2 起**（其余从 col 3）；CDS 日期是**月末**（2013-01-31）其余是月初。
月列是真 datetime、季度列是字符串 `'1Q11'`，交替出现 —— 全部照原样复现。

**声称数字逐格比对：245 个单元格，0 处不一致。**
（7 个时间切片 × 41 个字段，覆盖 2011-01 / 2015-01 / 2020-07 / 2025-07 / 2026-06 / 2026-07。）

其他可量化声称也全部精确复现：

| 原报告声称 | 我的复现 | 判定 |
|---|---|---|
| 月度单元格 10,026 个，非整数 2,429 个，集中在 13 列 | 10,026 / 2,429 / 13 | ✅ 分毫不差 |
| 交易日两行 187 月里 69 月相同（118 月不等） | 69 / 187 | ✅ |
| 季度列全精度，2Q26 Financials ADV = 4996.292370711726 | 完全相同 | ✅ |
| 当前表无未来占位列 | 187 个月列，`TOTAL F&O` 全部非空 | ✅ |
| CDS 2013-01 起 163 个月连续 | 163，无断档 | ✅ |
| §6 跨 vintage 重述：2026-06 vs 2026-07 仅 CDS 1 格（291→391） | 完全相同 | ✅ |
| §6 2020-07 vs 2026-07 跨 6 年仅 8 格、6 个字段 | 同样 6 个字段、同样 8 格、同样 maxrel | ✅ |
| 发布节奏 32 期 32/32 符合 | 逐年拉 feed，32 个日期与表格**完全一致** | ✅ |

### 1.3 交叉核对（我自己重做，不是抄它的）

**（a）10-K —— 我从 SEC EDGAR 独立取回原文**
`CIK 0001571949` → `0001571949-26-000004` / `ice-20251231.htm`（2026-02-05 报送）。
10-K Item 7「Selected Operating Data」原文数字与我解析的月度序列：

```
年末 OI（10-K 原文）  Energy 62,776  Ag&Metals 3,470  Financial 36,406  Total 102,652
我解析的 2025-12      oi_energy 62776  oi_ag_metals 3470  oi_financials 36406  (comm+fin) 102652
                      ← 四个数逐位相等，这是解析正确性的决定性证据
ADV energy   5003.076 vs 10-K 5,003   (+0.00%)
ADV ag        422.781 vs 10-K   423   (-0.05%)
ADV fin      3834.607 vs 10-K 3,835   (-0.01%)
NYSE eq opt 10555.020 vs 10-K 10,556  (-0.01%)   行业 55787.0 vs 55,798 (-0.02%)
现货 handled 3398.677 vs 10-K 3,401   (-0.07%)   matched 份额 18.970% vs 19.0%
```

**（b）新闻稿 —— 我拿到了原文 PDF（见「新发现」§三）**
July 2026 稿：19 条 y/y 我逐条反算，**17/19 一致**，两处不一致正是原报告标注的
「Other Crude & Refined（口径坑 9）」与「Environmentals 63/54=16.7% vs 稿 18%（口径坑 3 四舍五入）」。
June 2026 稿：月度 **12/12** 一致；季度 6/7 一致，第 7 条 2Q Sugar 我算 30.51% 而稿写 30%
（原报告标为「边界·稿方截尾」，属实 —— 30.51 四舍五入应为 31，ICE 是截尾）。
「Total OI 自己加总 = oi_commodities + oi_financials」这条方法学：
2026-07 = 121,826、2025-07 = 102,863 → +18.44%，稿写 18% ✅ 方法成立。

**（c）第二份官方文件 —— 我用 feed 里的 `FilePath` 独立抓回，并核对了原报告没查的 2019 年**
`2015-2021-Historical-ADV_OI_vF.xlsx`（82,509 B，Last-Modified 2022-02-03，纯 urllib 200）。
该文件是**合约级**、单位是**张**（不是千张）。我取 2019-06 加总对账主源：

```
明细文件加总(张)      →千张    Monthly Stats   差
TOTAL Energy          2,754,652  2754.7   2755   -0.01%
TOTAL Ag & Metals       522,167   522.2    522   +0.03%
TOTAL Financials      3,008,531  3008.5   3009   -0.02%
Total Futures&Options 6,285,351  6285.4   6285   +0.01%
Brent(期货+期权)      1,111,456  1111.5   1111   +0.04%
Gasoil                  292,101   292.1    292   +0.03%
Total Interest Rates  2,343,146  2343.1   2343   +0.01%
Total Equity Indices    626,436   626.4    626   +0.07%
Sugar                   235,833   235.8    236   -0.07%
Total FX & Other         38,947    38.9     39   -0.14%
```

---

## 二、针对四类虚报的定点攻击结果

### (a) 「只抓到最新一期，却声称有多年历史」→ **不成立，且我做了额外加固**

三条独立证据：

1. **当前文件本身就带全历史**：我的解析器在 `ice_latest.xlsx` 上，
   2019-06 这一列 **54 个字段全部有值**（与最新月一样多），2011-01 同理。不是空壳。
2. **2019 年的数据被第二份独立官方文件证实**（上面 §1.3c，10 项全对）——
   这一步是我加的，原报告只核了 2015-01 / 2018-06 / 2021-12。
3. **旧 vintage 文件本身也能纯 urllib 抓到**：我实抓
   `.../2020/08/2011-2020-Monthly-Stats-July-2020_v1.xlsx` → **200，201,560 B，
   Last-Modified Wed, 05 Aug 2020 12:35:35 GMT**，并用同一套解析器解出 2011-01..2020-07 共 115 个月。
   同时 `.../2026/07/...May-2026_vF.xlsx` 确实 **404** —— 原报告「目录规则不自洽、不要猜 URL」属实。

结论：历史深度 2011-01 起是真的，且是**免回补**的（单文件带全序列）。

### (b) 「拿第三方聚合站冒充官方」→ **不成立**

全链路只有三个域：
`ir.theice.com`（ICE 自己的 IR 站，Q4 Inc 托管）、
`s2.q4cdn.com/154085107/`（ICE 自己的 IR CDN，`154085107` 是 ICE 的 Q4 站点 ID）、
`www.sec.gov` / `data.sec.gov`（我做 10-K 核对时才用）。
**没有 FIA、没有 investing.com、没有 wikipedia、没有任何数据聚合站。**
报告里「❌ FIA / 各类交易量聚合站 —— 违反仓库硬约束」这条自我约束是明确写着的。

### (c) 「靠浏览器登录态或手工点击」→ **不成立**

生产链路我冷启动跑通，**纯 `urllib`，3.36 秒，无 cookie、无 session、无 apiKey、无浏览器**。
原 agent 确实用过 `curl_cffi`，但只用于侦察期的三件事（旧 vintage、Key Metrics、探测），
**都不在生产路径上**，而且我已验证其中的旧 vintage 与明细文件用纯 urllib 同样能拿。
无 PerimeterX、无 JA3 拦截、无验证码、无 JS 渲染依赖（JSON 接口直出）。

### (d) 字段口径写错 → **未发现实质错误**（有 1 处例外，见 §四.3）

我逐条核了容易翻车的那几个：

- **张数 vs 金额**：Derivs sheet 标题栏原文 `(contracts in 000s)` ✅ 千张；
  Cash Products `(shares in millions)` ✅ 百万股；CDS `$ in Billions` ✅ 十亿美元。三者标注正确。
- **月度 vs 季度 vs ADV**：Derivs / US Equity Options / Cash Products 三张表都是 **ADV**（日均），
  CDS 那张表标题是 `Credit Default Swap (CDS) Gross Notional Cleared`、行名
  `TOTAL CDS Gross Notional Cleared`，**没有 daily 字样 → 是当月总额不是 ADV**。
  原报告写「当月清算的 CDS 名义总额」✅ 正确，没有把月总量写成 ADV。
- **OI 单位**：ICE 是**千张**，原报告用 `oi_*_kcontracts` 并大字警告与 `cme.csv` 的
  `oi_*_contracts` 差 1000 倍 ✅ 我核了 cme.csv 表头，确实是 `oi_energy_contracts`（裸张数）。这个警告是对的、也是必要的。
- **RPC 定义**：脚注原文 `RPC is calculated by dividing transaction revenues by contract volume`
  ✅；`Other Financials includes Equity Indices and FX` ✅（原报告说 rpc_other_financials = 股指+FX，对）。
- **单股剔除**：脚注 (13) 原文 `Single Stock Equity activity has been excluded from the "Total Financials"
  subtotal... excluded from ADV, RPC, and OI` ✅ 原报告「不进任何池」正确。
- **Environmentals 行名漂移**：行标签是 `Environmentals & Other (6)`，而脚注 (6) 正文写
  `"Emissions & Other"` ✅ 原报告说的这个坑真实存在。
- **handled vs matched**：脚注原文区分清楚，原报告「不要用 handled，因为含路由出去成交的量」✅ 正确。

### (e) 声称 A 但关键字段缺失 → **不成立**

54 个字段在 187 个月上**全部齐备**（我检查了每月字段数：最新月 54、2019-06 54、union 54）。
ADV / RPC / OI / 份额 / 交易日 / 行业分母 六类都在。没有「只有量没有价」或「只有最新几个月有值」。

---

## 三、原报告漏掉的一个重要发现（有利，建议实现阶段采纳）

**新闻稿全文 PDF 就挂在不设防的 CDN 上，无人值守可取，不需要 curl_cffi、不需要浏览器。**

`PressRelease.svc` 返回的每一条都带一个 `DocumentPath` 字段：

```
https://s2.q4cdn.com/154085107/files/doc_news/Intercontinental-Exchange-Reports-July-2026-Statistics-2026.pdf
```

我用纯 urllib 抓到 **200 / 117,783 B / 3 页**，PyMuPDF 直接出文本（不需要 OCR），
两期新闻稿（7 月、6 月）的全部 y/y 百分比都取到了 —— 上面 §1.3b 的对账就是这么做的。
`Body` 字段是空的，别去读它；用 `DocumentPath`。

**价值**：`_validate()` 可以每月自动拿官方新闻稿的 y/y 百分比回校解析结果，
这是比内部恒等式强得多的一道闸；`_record_source_dates` 的 evidence 也能引原文而不只是引 headline。

---

## 四、发现的错误（按危害排序）

### 1. 🔴 §7 恒等式「TOTAL ENERGY = 6 个子项之和，187/187 成立」—— **假的，直接写进 `_validate()` 会天天报警**

原报告 §7 把这条列为「可直接写进 `_validate()`」。实测（严格相等，容差 0.5）：

```
ENERGY = 6 子项和    max_abs=2.00   精确成立  85/187   ±1 内 179/187   ±2 内 187/187
AG     = sugar+other max_abs=1.00   精确成立 140/187   ±1 内 187/187
COMM   = energy+ag   max_abs=1.00   精确成立 138/187   ±1 内 187/187
FIN    = 4 子项和    max_abs=2.00   精确成立 109/187   ±1 内 185/187   ±2 内 187/187
```

原因就是原报告自己在口径坑 3 里说过的「月度单元格全部四舍五入到整千张」——
6 个各自四舍五入的加数，和的误差自然可达 ±2~3。原报告在口径坑 3 写对了、在 §7 又忘了。

**实现阶段必须**：这四条恒等式一律用 `abs(diff) <= 3`（ENERGY / FIN 是 6 项和与 4 项和，
给 3 最稳），不要用相等。用相等会在 187 个月里失败 102 次。

其余 §7 条目我复现无误：
`CDS foot（容差 2）` 最新期 163/163 成立、6 月版能抓出 2026-01 那格 ✅；
`现货 matched 份额` 187/187（误差 <0.15pp）✅；`NYSE 期权份额` 187/187 ✅；
`TOTAL F&O = COMM + FIN` **166/187（±1）、max rel 0.531%** —— 与原报告写的
「166/187、偏差 <0.55%」**分毫不差**，这条是对的。

### 2. 🔴 §5 拦截对照表 —— **我复现不出来，且它要求把错的事实写进代码注释**

原报告 §5 表格与口径坑 2 断言：`ir.theice.com` 的 HTML 页「curl / urllib / nscurl 一律 403
"Just a moment…"」，并要求「这两件事必须写在代码注释里」。

我今天用同样的桌面 UA、纯 urllib 实测：

```
200  64,725 B  ir.theice.com/investor-resources/supplemental-information/default.aspx
200  64,730 B  ir.theice.com/ir-resources/supplemental-information      ← 新闻稿正文里给的现行路径
200  74,131 B  ir.theice.com/press/news-details/2026/...July-2026-Statistics/default.aspx
（Server: cloudflare，有 cf-ray，但页面里没有 "Just a moment"，是正常正文）
```

Cloudflare 在前面，但**没有下挑战**。原 agent 侦察时短时间内打了几十次，
大概率是被限速触发了 interactive challenge，把「当时被拦」误当成「结构性被拦」。

**但绕开 HTML 的结论仍然正确 —— 只是理由不同，我验证了真正的理由**：
那张 supplemental-information 页的 HTML 里 **一个 `Monthly-Stats*.xlsx` 链接都没有**
（`re.findall(r'Monthly-Stats[^"\']*\.xlsx', html)` → 0 命中），列表是前端用同一个 feed
客户端渲染出来的。所以必须走 feed，**不是因为 HTML 被拦，是因为链接根本不在 HTML 里**。

**实现阶段必须**：代码注释写「HTML 页不含 xlsx 直链，列表由前端从同一 feed 渲染 → 走 feed」，
**不要**写「HTML = Cloudflare 403」。后者是错的，会误导下一个人（比如让他以为需要 curl_cffi）。

### 3. 🟡 口径坑 13 / FX 池：`adv_fx_credit` **多半不是「FX 与信用合并」**，原报告把标签当成了定义

原报告说这一行「FX 与信用合并披露，不是纯 FX」，并据此警告不能与 CME 的 `adv_fx_kcontracts` 比。
证据链是反的：

- 表内**脚注 (12) 原文**：`"TOTAL FX" includes futures and options for the U.S. Dollar Index and
  foreign exchange.` —— **只说了 USDX 和外汇，一个字没提 credit**。
- 独立的 2015-2021 明细文件里对应行是 `Total FX & Other` = `FX & Other Financials` + `USDX`，
  2019-06 = 38,947 张 = 38.9 千张，与主源 `adv_fx_credit` = 39 **精确相符**。信用不在里面。
- 该序列 2011-2026 每年 6 月分别是 47/44/60/32/69/40/36/34/39/33/38/51/29/41/41/34 千张，
  **没有任何结构性跳变** —— 若某年并入了信用类合约，不该这么平。

只有 col1 的行标签写着 `TOTAL FX & CREDIT`（col2 写 `FX & Credit (12)`），
定义与实测都指向 FX+USDX。原报告把标签当事实了。

**实现阶段**：字段名建议改成 `adv_fx_usdx_kcontracts` 或保留 `adv_fx_credit` 但注释写清
「行标签含 Credit，但脚注 (12) 与 2015-2021 明细文件均显示口径为 FX + USDX」。
实际影响不大 —— 这一行只有 22~69 千张，对 CME FX 的 811 千张（2026-07）是量级差，
本来就只能画指数化，别并排画绝对量。

### 4. 🟡 口径坑 7 的**因果解释**被数据证伪（结论对、理由错）

原报告说 `adv_commodities + adv_financials ≠ adv_futures_options` 是因为
「commodities 与 financials 各自用不同的交易日数归一」。但偏差最大的几个月里两行交易日是**相等**的：

```
2011-08  gap 32  td_commod 23  td_rates 23   ← 相等
2011-10  gap 27  td_commod 21  td_rates 21   ← 相等
2012-08  gap 16  td_commod 23  td_rates 23   ← 相等
2012-03  gap 20  td_commod 22  td_rates 22   ← 相等
```

交易日差异解释不了。真实原因未查明（可能是 2011-2013 的追溯重刷只重刷了小类没重刷合计）。
**结论仍然正确**（不要当硬校验、幅度 0-0.55%、166/187 —— 这三个数我都复现了），
但代码注释里不要写那个错的因果，否则下一个人会照着它去「修」一个修不好的东西。

### 5. 🟡 竞争池：「ICE 与 HKEX 两边都是 187 个月的连续序列」—— **假的**，且这张图**建不出来**

原报告把「ICE 份额十五年跌 8pp vs HKEX 恒为 100%」称为「整个看板最直白的一张图」。
我查了 `~/Projects/monthly-op-dashboards/series/hkex.csv`：

```
month,adt_hkdbn,mktcap_hkdtn,new_listings,ipo_funds_hkdbn,derivatives_adv_contracts,southbound_adt_hkdbn
2019-01,...                                    ← 起点是 2019-01，不是 2011-01
共 91 行                                        ← 不是 187 个月
```

- **HKEX 序列只有 91 个月，从 2019-01 起**，不是 187 个月。
- **hkex.csv 里根本没有任何「份额」字段**。所谓「HKEX 恒为 100%」不是数据，是断言 ——
  要画这张图只能在代码里硬写一个常数 1.0，那不是数据看板该干的事。
- 顺带：`derivatives_adv_contracts` 是**裸张数**（2026-07 = 1,731,267），ICE 是千张，又差 1000 倍。

**实现阶段**：这张图要么放弃，要么明确标注 HKEX 那条线是「口径假设：本地垄断，非披露数据」，
且时间轴只能从 2019-01 起对齐。

### 6. 🟢 仓库常量记错：`EARLY` 是 **5** 不是 3

原报告写「闸门按仓库规则再提前 `EARLY=3` 天开 → 次月 3 日起开始探测」。
`monthly_run.py:67` 是 `EARLY = 5`。配 `LAG=(6,6)` 则闸门在**月末后第 1 天**就开，
不是次月 3 日。LAG=(6,6) 本身我认为**是对的**（我实测 32 期里最晚落在次月 6 日：
2025-01-06 / 2026-01-06 / 2026-04-06 / 2026-07-06）。
但要注意 `cboe` 同样是「次月第 3 个交易日」却配了 `(4,4)` —— ICE 配 6 会比 Cboe 宽两天，
这是保守选择，可以接受，但最好在注释里说明为什么与 Cboe 不同。

### 7. 🟢 发布节奏那 32 期，用它文档里的那个 feed 调用**拿不到**

原报告 §辅源 1 给的调用是 `pressReleaseDateFilter=3&year=-1&pageSize=100`。
我实测：这个调用返回 100 条，其中统计新闻稿**只有 7 条**（最早 2026-01）。
32 期的表是靠**逐年**调用得到的 —— 我用 `pressReleaseDateFilter=1&year=2024/2025/2026`
分别拿到 12 / 12 / 8 条，合计 32 条，**32 个日期与原报告表格完全一致**（所以表本身没造假）。

**实现阶段**：生产只需要最新一期，用 `year=-1` 的那个调用没问题；
但如果要回补 `source_dates.csv` 的历史，必须逐年调 `year=YYYY`，不要照抄 §辅源 1 那一行。

### 8. 🟢 两处小瑕疵

- `scratch/ice/monthly_stats_feb2017.xlsx` **不是 2017 年的月度统计 vintage**，
  它的 sheet 是 `Pro Forma NonGAAP` / `Pro Forma Reconciliation`，是一份非 GAAP 财务对账表。
  报告正文没有引用它做任何声称，但别把它当 2017 年版本复用。
- §4 那行「合约数 Total (mn) 2345 vs 反算 2326.733，-0.78%」我算不出来：
  按各类别各自的交易日行加权，我得到 **2,347.384（+0.10%）**。它这个反算数偏低。
  源数据没问题，是它的算术；不影响结论。
- 原报告口径坑 4 说「按行号硬编会炸」。我这次**就是**用硬编行号的解析器，
  2026-07 期与 2020-07 期**都解对了**（跨版本 diff 只有 8 格不同 / 6,210 格）。
  行位置在 2020→2026 之间是稳定的。**它给的防御性建议（剥脚注记号 + 别名集合）仍然值得做**，
  但「不这么做一定炸」不成立 —— 别为了这条去做过度设计。

---

## 五、能不能和 cme / cboe / hkex 放进同一个竞争池？（我实际拿仓内 CSV 对了）

### 5.1 ✅ 北美现货 —— **可比，而且是 ICE 最大的贡献**（原报告这条我验证成立）

ICE 的 `adv_tapeA/B/C_consolidated_mnsh` 是**真正的全行业分母**。我用它算 Cboe：

```
2026-07  全美合并 17.437bn 股/日 | NYSE matched 3.329bn = 19.1%（ICE 自报 0.191 ✅）| Cboe 1.569bn = 9.0%
2026-06  全美合并 23.382bn      | NYSE 20.0%                                        | Cboe 9.3%
2019-06  全美合并  7.185bn      | NYSE 24.8%                                        | Cboe 15.3%
```

两条份额曲线的走势彼此自洽、量级也对（NYSE 从 ~25% 掉到 ~19%，Cboe 从 ~15% 掉到 ~9%，
差额被场外/TRF 吃掉）—— 这是仓内第一次能在**同一个分母**下画份额。原报告这个判断成立。

⚠ 实现注意：单位是**百万股**，`cboe.csv` 是 `adv_us_equities_matched_shares_bn`（**十亿股**），
必须 ÷1000；且 ICE 只按 tape 给 matched，需要派生 `adv_nyse_us_cash_matched_mnsh = A+B+C`
（原报告已指出，正确）。

### 5.2 ✅ 北美期权 —— 可比，但「不含指数期权」这句是**推断不是官方定义**

```
2026-07  行业 64,394k | NYSE 13,614k = 21.1% | Cboe multilist 15,687k = 24.4%
2025-07  行业 51,516k | NYSE 20.9%           | Cboe 23.7%
```

两家加起来 45.5%，给 Nasdaq/MIAX/BOX 留 54.5% —— 量级合理，10-K 也自报 2025 年 NYSE 份额 18.9%
（我反算 18.920%）。可比性成立。

⚠ 但：工作簿里 `Total Equity Options` 这一行**没有任何脚注**，ICE 从未书面说明它是否含指数期权。
「不含指数期权」是从 Cboe 交叉比例反推出来的合理读法（若含指数，NYSE 份额会算成 23-24%，
与 10-K 自报的 18.9% 对不上）。**页面上不要把它写成「ICE 官方定义为不含指数期权」**，
只能写「经与 Cboe multilist 及 ICE 10-K 交叉验证，该分母口径与多重上市股票/ETF 期权一致」。

### 5.3 ⚠ RPC 跨家对比有一个会被当成 bug 的错位

- ICE 的 RPC：滚动三月均，**不滞后**（2026-07 期 `rpc_energy = 1.89` 已填）。
- Cboe 的 RPC：滚动三月均，**滞后一个月**。我核了 `series/cboe.csv` 最后一行 2026-07，
  所有 `rpc_*` 列**全空**，`fetch/cboe.py` 开头也明写「RPC 滞后一个月…新月份入库时 RPC 天然为空」。

⇒ 任何 ICE vs Cboe 的 RPC 并排图，**ICE 那条线每个月都会比 Cboe 多伸出一格**。
必须在绘图层截齐或加标注，否则每月看板一刷新都像是 Cboe 抓挂了。

### 5.4 ⚠ 与 CME 比衍生品：单位差 1000 倍是真的，合约规格不可比也是真的

```
cme.csv  adv_energy_kcontracts 2632.58（千张）  oi_energy_contracts 11,042,384（裸张）
ice      adv_energy 5146（千张）                oi_energy 68,093（千张 = 68.09M 张）
```

ADV 两边都是千张，**单位可比**；OI 一边千张一边裸张，**必须 ×1000 才能比**。原报告的警告正确。
但合约标的（Brent 桶 / TTF MWh / Henry Hub MMBtu）本身不可比，所以只能画同比与指数化 ——
原报告这一点也说对了，且这是它最重要的一条自我约束。

利率同理：ICE = 欧洲曲线（Euribor/SONIA/Gilts），CME = 美国曲线（SOFR/Treasuries），
互补不竞争。作为「同一池」画绝对量没有意义，画增速有意义。

### 5.5 ❌ 与 HKEX：**不可比**，见 §四.5。

`derivatives_adv_contracts` 是裸张数、序列只到 2019-01、且**没有份额字段**。
原报告设想的那张「垄断 vs 竞争」对照图，仓内没有支撑它的数据。

### 5.6 ⚠ 一个原报告没说的口径前提：2011-2013 的 NYSE 数据是**追溯并入的形式数**

`Derivs` sheet row 79 原文：
`For comparison purposes, we include NYSE ADV, RPC and OI in all periods covered in this spreadsheet`

ICE 是 **2013 年 11 月**才完成 NYSE Euronext 收购的。所以 2011-01 ~ 2013-10 的
NYSE 现货与 NYSE 期权数据，是 ICE 事后按「假设当时就拥有」口径回填的形式数据。

**这直接打在原报告的头号叙事上**：「`share_nyse_us_cash_matched` 从 26.9%（2011-01）
跌到 19.1%（2026-07）」的前 34 个月，讲的不是 ICE 的份额、是被收购前 NYSE Euronext 的份额。
数据本身没错（ICE 自己就是这么披露的），但页面上必须标注「2013-11 前为追溯并入口径」，
否则这条线在讲一个 ICE 当时并不拥有的故事。

---

## 六、给实现阶段的具体警告（按必须程度排序）

1. **恒等式阈值一律 `abs(diff) <= 3`，不要用相等。** ENERGY(6项和)/FIN(4项和) 精确相等只在
   85 和 109 个月成立。CDS 那条容差 2 是对的，保留。
2. **代码注释不要写「ICE 的 HTML 页 = Cloudflare 403」。** 那是当时的限速表现，我今天纯 urllib
   拿到 200。正确的注释是「HTML 不含 xlsx 直链，列表前端从同一 feed 渲染，所以必须走 feed」。
3. **不要写死 `apiKey`。** 我全程不带 key 都是 200，原报告这条建议正确且重要。
4. **指针必须走 `ContentAsset.svc` 的 `FilePath`，不要猜 CDN 路径。** 我实证
   `.../2026/07/...May-2026_vF.xlsx` = 404。兜底：先 `Title == "Monthly Statistics Tracking"`，
   再退 `FileType=="XLSX" and "Monthly Stat" in Title`（feed 里确有第二条 `Monthly Statistics`
   指向同一 URL，我看到了，天然备份指针成立）。
5. **`_validate()` 建议加一道新闻稿回校**：用 `PressRelease.svc` 条目的 `DocumentPath`
   取 PDF（纯 urllib，不需 OCR），把稿里的 y/y 与解析值对，容差 ±1pp，
   并把 `Other Crude & Refined` 与小基数的 `Environmentals` 列入白名单（这两条稳定对不上，
   原因分别是口径坑 9 和四舍五入）。
6. **`latest_month()` 以「最后一个 `TOTAL FUTURES & OPTIONS` 非空的月」为准，不要信文件名。**
   当前表没有占位列（我验证过），但要写成能容忍占位列的形式。原报告这条正确。
7. **单位换算三处别漏**：ICE OI 千张 → CME 裸张 ×1000；ICE 现货百万股 → Cboe 十亿股 ÷1000；
   ICE 衍生品 ADV 千张 → HKEX 裸张 ×1000（如果真要比的话）。
8. **`adv_fx_credit` 的注释改掉**（见 §四.3），别写成「含信用」。
9. **`share_nyse_us_cash_matched` / `share_nyse_equity_options` 的图必须标注
   「2013-11 前为 NYSE 追溯并入口径」**（见 §五.6）。
10. **「已有值永不覆盖、只填空」是安全的** —— 我独立复现了跨 6 年只有 8 格变化、
    唯一实质重述是 CDS 2026-01 那格。建议照原报告写 `cache/ice_restatements.csv`。
11. **回补 `source_dates.csv` 历史要逐年调 feed**（`year=YYYY`），`year=-1` 那个调用只回 7 条。
12. **别为「行名漂移」做过度设计** —— 硬编行号在 2020↔2026 上是通的（我实测）。
    做别名归一化是好习惯，但不要因此把解析器写成一坨。

---

## 七、最终判定

**A（维持原判定）。**

理由：源是官方第一方、无人值守纯标准库 3.4 秒跑通、文件字节级可复现、
187 个月 54 字段无断档、并通过三条彼此独立的官方链路（月度新闻稿 PDF / FY2025 10-K / 
2015-2021 合约级明细文件）交叉验证，其中 10-K 年末 OI 四个数与我的解析**逐位相等**。
这是我复核过的交易所里证据链最完整的一家。

发现的 6 处错误全部落在**注解与建议层**，不触及数据源本身、URL 链、解析正确性或字段完整度，
因此不构成降级理由 —— 但其中第 1、2 条若不修正就照抄进代码，会分别造成
「每月 100+ 次假告警」和「一条把后人引向 curl_cffi 的错误注释」，必须在实现前改掉。
第 5 条（HKEX 对照图）是唯一一处**做不出来**的承诺，产品层面要么砍掉要么明确标注为口径假设。
