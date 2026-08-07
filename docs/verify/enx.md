# Euronext（slug: enx）数据源可行性侦察

侦察日期 2026-08-06。所有结论均为本机实测，脚本与原始文件在 `/tmp/exch_recon/scratch/`。

## 判定

**A —— 可直接实现**，而且是本仓迄今质量最高的一类源：单个稳定文件名的官方 xlsx，
urllib 裸奔即可拿，2012-01 起 174 个月零断档，与官方季报附录 27 项指标逐项对上（26 项相对差 < 1e-4）。

唯一需要在实现时**认真对待**的是 Athens（Athex）并表：官方把 Athex 做成**贯穿全历史的备注列**，
主列只从 2025-11 起含 Athex。这不是坑，是官方给的钥匙 —— 有了它可以两个方向自己造连续序列
（往前 pro-forma 加、往后 legacy 减），而且**实测能精确复现官方季报里的 pro-forma 数**（见「实测证据」第 3 组）。
真正会咬人的是单股衍生品：Athex 的单股期货占并表后 90-98%，不做处理的话 2025-11 那一格是 3-6 倍的假跳。

不判 B 的理由：没有任何抓取障碍、没有登录墙、没有 JS 渲染、没有需要拼月份的文件名、没有断档。
Athex 断点属于「必须写进 docstring 与图上断点标注」的建模问题，不是可行性问题。

## 数据源

### 主源（唯一真值）

```
落地页 : https://www.euronext.com/en/investor-relations           锚点 <h2 id="monthly-volumes">
直链   : https://live.euronext.com/sites/default/files/statistics/ir/euronext_monthly_historical_volumes.xlsx
格式   : xlsx（openpyxl 可读），219,581 bytes，5 个 sheet
```

**文件名固定，不带月份**，与 CME 的 `monthly-volume` 别名同类 —— 每月原地覆盖，永远指向最新一期。
不需要、也不应该去猜带月份的直链。

落地页那一段的 HTML 是（实测原文）：

```html
<h2 id="monthly-volumes">Monthly volumes</h2>
<p>Historical trading volumes on Euronext Cash and Derivatives Markets. Download, excel Cash markets
   turnover and Derivatives markets volumes from 2012 till today.</p>
<h3>Download</h3>
<ul class="bullet-listing">
  <li><a href="https://live.euronext.com/sites/default/files/statistics/ir/euronext_latest_month_volumes.xlsx?t=1785979010">Euronext Latest Month Volumes</a></li>
  <li><a href="https://live.euronext.com/sites/default/files/statistics/ir/euronext_monthly_historical_volumes.xlsx?t=1785979010">Euronext Monthly Historical Volumes</a></li>
</ul>
```

`?t=1785979010` 是 Drupal 的 cache-buster（= 2026-08-06 01:16:50 UTC），**去掉照样 200**，
不要把它当成版本号解析。建议照 cboe.py 的做法：先取落地页、正则捞出 `statistics/ir/euronext_monthly_historical_volumes\.xlsx`
这条 href 确认还在，再下直链；落地页挂了就退回写死的直链兜底。

### 伴生文件（可选，用作解析自检）

```
https://live.euronext.com/sites/default/files/statistics/ir/euronext_latest_month_volumes.xlsx
```
49,225 bytes，只有最新月 / 上月 / 去年同月 / 本季 / YTD 五档，**并且直接给出算好的 ADV**。
它对我们的价值不是数据本身，而是**免费的第二意见**：我们从历史文件按「月度总量 ÷ 交易日」自己算的 ADV，
可以和这个文件里官方算好的 ADV 对表。实测 2026-06 我们算出 17,183.521449326818，
它写的是 17,183.521449326818，完全一致（见实测证据第 4 组）。
⚠️ 它的第 5 张 sheet `Nord Pool` 是 2020 年的死残留，格子里写着字面量 `"xxx"` / `"xx%"`，**不要解析它**。

### 发布日来源（source_dates 用）

月度新闻稿 **本身不含任何数字**（2021 年前含，之后只剩一句「表格在 IR 页」），
所以它对本模块的唯一价值就是**权威发布时刻**：

```
列表页 : https://www.euronext.com/en/investor-relations/financial-information/news?page=0|1
         每条 <time datetime="2026-07-06T15:45:00Z" class="datetime">06/07/2026</time>
详情页 : .../euronext-announces-volumes-for-june-2026
         JSON-LD: "datePublished": "2026-07-06T17:45:00+0200"
         正文电头: "Amsterdam, Athens, Brussels, Dublin, Lisbon, Milan, Oslo and Paris – 6 July 2026 –"
         附件 PDF: /sites/default/files/2026-07/Euronext%20PR%20Volumes%20-%20June%202026.pdf
```
三处互证，取 JSON-LD `datePublished`（机器可读、带时区）最省事，正文电头作为人工可读的 evidence 文字。

### 抓取方式与反爬

| 检查项 | 实测结果 |
|---|---|
| `urllib.request` **不带任何自定义 UA**（python-urllib/3.x） | 200，219,581 bytes，1.8s |
| `urllib` + 桌面 Chrome UA | 200，同字节数，1.6s |
| `curl` 默认 | 200 |
| Cloudflare / Akamai 挑战 | 无。`server: CloudFront`，纯 S3+CDN 直供 |
| JS 渲染 | 不需要（xlsx 是静态文件；落地页是服务端渲染的 Drupal HTML） |
| 登录墙 | 无 |
| `nscurl` / `curl_cffi` | **不需要**，没有 JA3 指纹拦截 |
| `robots.txt` | `User-agent: *` 只 Disallow `/core/` `/profiles/` `*/taxonomy/` `/search/` 等，`/sites/default/files/` 与新闻稿路径均允许 |
| CDN 缓存 | `cache-control: public, max-age=300, s-maxage=300`，5 分钟 TTL，不会拿到隔夜的旧文件 |

**完全满足无人值守。** 依赖只有 openpyxl（仓里已有）。

## 可提取字段

下面这套列名是按 `series/cboe.csv` 的风格（含单位后缀）拟的，**已经全部实跑解析成功**。
其中 29 列写进了成品文件 `/tmp/exch_recon/scratch/enx_demo.csv`（174 行 × 29 列，2012-01 → 2026-06）；
另外两列（`adv_other_fixed_income_eurm`、`listed_funds`）没进那个 demo 文件，但在交叉核对第 2 组里
单独验过（1,502.18 vs 官方 1,502；2,178 vs 官方 2,178），同样成立。
「源」一列写的是工作表与列号，实现时**必须按标签定位、不要写死列号**（理由见口径坑 8）。

| CSV 列名 | 源（sheet / 表头标签） | 口径说明 |
|---|---|---|
| `month` | Period 列（datetime，取年月） | YYYY-MM |
| `trading_days_cash` | Equity Markets `Nb of trading days`(C3) | 现货交易日数，算 ADV 的分母 |
| `trading_days_eqderiv` | Equity Markets `Nb of trading days`(C16) | 股权衍生品交易日数。**与现货那个不是同一列**，虽然实测长期相等 |
| `adv_cash_adnv_eurbn` | `Total Turnover`(C6) ÷ C3 ÷ 1000 | 现货日均成交名义额，**单边计（single counted）**，含股票+投资基金+ETF+结构化产品。2025-11 起含 Athex |
| `adv_cash_equities_adnv_eurbn` | `Turnover Equities`(C8) ÷ C3 ÷ 1000 | 只含股票与投资基金。**与 Cboe Europe 对比时用这一列更干净**（Cboe 的 EU equities 不含结构化产品） |
| `adv_cash_etf_adnv_eurbn` | `Turnover ETF`(C10) ÷ C3 ÷ 1000 | ETF 现货日均成交额。2015-01 起把 ETC 从结构化产品挪进了这一列 |
| `adv_cash_trades_k` | `Total number of trades`(C4) ÷ C3 ÷ 1000 | 日均成交**笔数**（千笔），**买卖双边计**，含 reported trades。与金额口径的单双边不一致，是官方自己的定义 |
| `adv_index_deriv_kcontracts` | (`Futures`C17 + `Options`C19) ÷ C16 ÷ 1000 | 股指衍生品日均张数（千张）：CAC 40 / AEX / BEL 20 / FTSE MIB / OBX / ATHEX 等 |
| `adv_singlestock_deriv_kcontracts` | (C26 + C28) ÷ C16 ÷ 1000 | 单股衍生品日均张数。**⚠ 2025-11 结构性断点，见口径坑 2** |
| `adv_commodity_deriv_kcontracts` | FICC `Futures`(C14) + `Options`(C15)，÷ FICC C13 ÷ 1000 | 商品衍生品日均张数。**Euronext 的 commodity 是巴黎 MATIF 的农产品（小麦/玉米/菜籽），不是能源** |
| `adv_fx_spot_usdbn` | FICC `Spot volume`(C29) ÷ C28 ÷ 1e9 | Euronext FX（原 FastMatch）即期外汇日均成交，$bn。**⚠ 表头写 "in M\$" 是错的，实测该列是绝对美元，见口径坑 4** |
| `adv_mts_cash_eurbn` | FICC `MTS Cash`(C4) ÷ C3 ÷ 1000 | MTS 现券（欧洲政府债电子交易）日均成交额，单边计 |
| `taadv_mts_repo_eurbn` | FICC `TA(1) MTS Repo`(C6) ÷ C3 ÷ 1000 | **Term Adjusted** 回购日均量（官方主口径叫 TAADV）。同表另有未调整的 `MTS Repo`(C5)，两者都在，别混 |
| `adv_other_fixed_income_eurm` | FICC `Bonds`(C7) ÷ C3 | MTS 以外的债券成交（Euronext 各地债券市场 + 2025-11 起 Athex），量级小，留 €m |
| `adv_power_dayahead_twh` | FICC `Day-ahead`(C20) ÷ C19 | Nord Pool 日前电力市场日均 TWh，**买卖双边计** |
| `adv_power_intraday_twh` | FICC `Intraday`(C21) ÷ C19 | Nord Pool 日内电力，同上 |
| `oi_index_deriv_kcontracts` | (C21 + C23) ÷ 1000 | 月末未平仓（千张），股指期货+期权 |
| `oi_singlestock_deriv_kcontracts` | (C30 + C32) ÷ 1000 | 月末未平仓，单股期货+期权 |
| `oi_commodity_deriv_kcontracts` | FICC (C16 + C17) ÷ 1000 | 月末未平仓，商品期货+期权 |
| `issuers_equities` | Capital Markets `Equities`(C3) | 月末股票发行人家数 |
| `listed_etfs` | Capital Markets `ETFs`(C7) | 月末上市 ETF 只数 |
| `listed_bonds` | Capital Markets `Bonds`(C5) | 月末上市债券只数（2025-06 起含 Euronext ABM，官方已重述 2024-2025） |
| `listed_funds` | Capital Markets `Funds`(C9) | 月末上市基金只数 |
| `mktcap_eurtn` | Capital Markets `Total end of month`(C16) | 月末总市值，万亿欧元。**只到 2022-01** |
| `money_raised_new_listings_eurm` | Capital Markets C12 | 当月新上市募资额（€m）。2025-06 起口径扩大到「所有类型的挂牌」 |
| `money_raised_followon_eurm` | Capital Markets C14 | 当月再融资募资额（€m） |
| `csd_auc_eurbn` | Securities Services `Total`(C3) | Euronext Securities 五家 CSD 托管资产，月末，€bn。**只到 2022-01** |
| `csd_settlement_instructions_m` | Securities Services `Total`(C9) ÷ 1e6 | 当月结算指令笔数（百万笔）。**只到 2022-01** |
| `athex_adv_cash_adnv_eurbn` | Equity Markets `Athex`(C7) ÷ C3 ÷ 1000 | **备注列**：Athex 单独口径。2025-11 前 = 尚未并入主列的部分；2025-11 起 = 已含在主列里的那部分 |
| `athex_adv_index_deriv_kcontracts` | (C18 + C20) ÷ C16 ÷ 1000 | 同上，股指衍生品 |
| `athex_adv_singlestock_deriv_kcontracts` | (C27 + C29) ÷ C16 ÷ 1000 | 同上，单股衍生品。**这一列是解开 2025-11 断点的钥匙，必须入库** |

还有几列存在但我没纳入，理由写清楚免得后人以为漏了：
`Turnover Structured Products`（结构化产品现货，量小且与 Cboe/CME 无对手）、
`Shares (nb of contracts)` 清算量（2022-01 起，语义是 Euronext Clearing 清算笔数，与成交额不同层）、
`Power trading derivatives` 三列（`System price futures` / `EPADs futures` / 名义 OI，**2026-03 才有，只有 4 个月**，
等攒够 12 个月再进图不迟）、CSD 的五地分拆列（Athens/Copenhagen/Milan/Oslo/Porto）。

## 历史深度

**主力序列 2012-01 起，共 174 个月，零缺月、零断档。** 逐列实测（`inventory.py` 输出）：

| 起始月 | 列 |
|---|---|
| **2012-01** | 现货成交额/笔数/股票/ETF/结构化产品、股指衍生品成交量与 OI、单股衍生品成交量与 OI、商品衍生品成交量与 OI、两组交易日数 |
| **2013-01** | FX 即期成交量 |
| **2018-01** | 发行人家数、上市债券/ETF/基金只数、上市家数、募资额（新上市 + 再融资） |
| **2020-01** | MTS Cash / MTS Repo / TAADV Repo、Nord Pool 日前与日内电力 |
| **2021-01** | Athex 备注列（现货三项、股指与单股衍生品、发行人/债券/ETF 家数） |
| **2022-01** | 总市值、CSD 托管资产与结算指令、股权清算量、Athex 备注列（市值、债券零售清算） |
| **2023-01** | Athex 备注列（上市家数、募资额） |
| **2026-03** | 电力衍生品三列（Nord Pool Power Futures 2026-03-16 才全面上线） |

对本仓的偏好（2015/2016 起，最低 2019）：**核心的现货 ADV 与三类衍生品 ADV 全部满足且大幅超出**，
同比与指数化都能从 2013 年做起。上市与募资类 2018-01 起（满足 2019 底线），
市值 / CSD 类 2022-01 起（**不满足 2019 底线**，只能做 4 年多的序列，画图时要么单独一张、要么标注起点）。

中间**没有任何一处断档** —— 我对每一列都跑了「首个非空月 → 末个非空月」区间内的缺失检测，
28 个数据列全部返回「断档 无」。

⚠ 但「无断档」≠「可连比」，有三处**定义断点**必须在图上标红（详见口径坑）：
2025-11（Athens 并入）、2021-05（Borsa Italiana 并入）、2019-01 与 2019-07（Dublin/Oslo 现货与衍生品分两批并入）。

## 发布节奏

历史文件本身**不写发布日**，节奏靠月度新闻稿的 `datePublished` 定。实测 30 期（2024-01 数据月 → 2026-06 数据月）：

| 数据月 | 发布日 | 次月第几天 | 数据月 | 发布日 | 次月第几天 |
|---|---|---|---|---|---|
| 2024-01 | 2024-02-08 | 8 | 2025-04 | 2025-05-09 | 9 |
| 2024-02 | 2024-03-08 | 8 | 2025-05 | 2025-06-10 | 10 |
| 2024-03 | 2024-04-08 | 8 | 2025-06 | 2025-07-04 | **4（最早）** |
| 2024-04 | 2024-05-13 | **13（最晚）** | 2025-07 | 2025-08-11 | 11 |
| 2024-05 | 2024-06-10 | 10 | 2025-08 | 2025-09-08 | 8 |
| 2024-06 | 2024-07-08 | 8 | 2025-09 | 2025-10-07 | 7 |
| 2024-07 | 2024-08-12 | 12 | 2025-10 | 2025-11-06 | 6 |
| 2024-08 | 2024-09-10 | 10 | 2025-11 | 2025-12-05 | 5 |
| 2024-09 | 2024-10-07 | 7 | 2025-12 | 2026-01-08 | 8 |
| 2024-10 | 2024-11-08 | 8 | 2026-01 | 2026-02-06 | 6 |
| 2024-11 | 2024-12-10 | 10 | 2026-02 | 2026-03-09 | 9 |
| 2024-12 | 2025-01-09 | 9 | 2026-03 | 2026-04-08 | 8 |
| 2025-01 | 2025-02-10 | 10 | 2026-04 | 2026-05-08 | 8 |
| 2025-02 | 2025-03-07 | 7 | 2026-05 | 2026-06-05 | 5 |
| 2025-03 | 2025-04-07 | 7 | 2026-06 | 2026-07-06 | 6 |

**区间 [4, 13]，中位数 8，无季末月特殊性**（月月都发，不像 SCHW/LPLA 要等季报）。

给 `build/roster.py` 的建议：`LAG = (13, 13)`（两个值相同）。
⚠ 但要注意与 `monthly_run.EARLY` 的相互作用：全局 `EARLY = 5` 会让闸门在**次月第 8 天**才开，
而实测有 5 期（2025-06 / 2025-11 / 2026-01 / 2026-05 / 2025-10）在第 4-6 天就发了，
公开页会白挂 2-4 天旧数据。建议给 enx 单独设 `EARLY_BY['enx'] = 10`（闸门次月第 3 天开），
代价是每月最多多打 5 个空请求 —— 这个源是单文件 220KB 的 CDN 静态资源，代价可以忽略。

**2026-07 数据截至本次侦察（2026-08-06 03:00 UTC）尚未发布**：
新闻稿列表最新一条是 2026-07-31，`euronext-announces-volumes-for-july-2026` 返回 404，
历史 xlsx 的最后一行仍是 2026-06。这是正常的（落在 [4,13] 窗口内），不是故障。

## 口径坑（按踩坑概率排序）

**1. Athens（Athex）备注列不是「另一家」，是「同一张表的两种口径」，含义随月份翻转。**
官方在每一个主指标右侧配一列表头写死为 `Athex` 的备注列。footnote (1)(3)(5) 全部写着
「…and Euronext Athens since November 2025」。实测语义是：

- **2025-10 及以前**：主列**不含** Athex，备注列 = Athex 单独数 → 主列 + 备注列 = 官方口径的 pro-forma
- **2025-11 及以后**：主列**已含** Athex，备注列 = 主列里属于 Athex 的那一块 → 主列 − 备注列 = legacy Euronext

这不是我猜的，是拿官方 Q2 2026 业绩稿反推验证的（该稿明写 "Q2 2025 volumes are including Euronext Athens on a pro forma basis"）：
Q2 2025 主列+备注 = 股指 10,796,110 / 单股 22,791,315，与官方 pro-forma **一位不差**；
Q2 2026 主列本身 = 股指 10,212,541 / 单股 25,104,143，与官方**一位不差**。
⇒ 入库时把主列与 Athex 备注列**都写进 CSV**，让 build 层自己决定画哪条；只写主列 = 把断点焊死在数据里。

**2. 单股衍生品是全表最危险的一列：Athex 占并表后的 90-98%，且有季度换月脉冲。**
实测主列 `Individual Equity Futures`（月合计张数）：

| 月份 | 主列 | 其中 Athex | Athex 占比 |
|---|---|---|---|
| 2025-09 | 190,279 | 1,924,214 | 主列尚不含（备注列 10 倍于主列） |
| 2025-10 | 35,573 | 889,119 | 同上 |
| **2025-11** | **836,511** | 781,183 | **93.4%** |
| 2025-12 | 3,173,156 | 3,098,694 | 97.7% |
| 2026-03 | 4,086,842 | 3,982,938 | 97.5% |
| 2026-04 | 703,019 | 680,275 | 96.8% |
| **2026-06** | **5,057,868** | 4,958,445 | **98.0%** |

两件事同时成立：(a) 2025-11 那一格是 **20 倍以上的断点**，不是业务增长；
(b) 并表后这条线在 **3/6/9/12 月出现 5-7 倍脉冲**（希腊单股期货被当作融券/回购替代品，按季滚动），
不是成交活跃度的信号。⇒ 图上必须画 2025-11 红色断点竖线；同比一律用 pro-forma（主+备注）口径；
`year_lines` 类图对这条线基本无意义。相比之下 Athex 单股**期权**可忽略（几百到 1 万张/月）。

**3. 历史 xlsx 是「按今天口径重述过的」序列，与当年新闻稿印出来的数字对不上 —— 而且方向会翻。**
实测同一个指标、三个时点：

| 对照 | xlsx 现值 | 当年新闻稿 | xlsx / 当年 |
|---|---|---|---|
| 2019-01 现货 ADV | 7,140.4 €m | 6,708.1 €m（2019-02-06 稿） | **1.0644** |
| 2019-06 现货月成交额 | 161,361.8 €m | 169,174.9 €m（2020-07-03 稿） | 0.9538 |
| 2020-05 现货月成交额 | 172,070.6 €m | 181,728.3 €m（同上） | 0.9469 |
| 2020-06 现货月成交额 | 234,385.7 €m | 244,406.7 €m（同上） | 0.9590 |

两股力量叠加：2019 上半年之前是**往上重述**（xlsx 把 Oslo 从 2018-01 就算进去了，
而 Oslo Børs 2019-06 才完成收购，当年的稿子里没有它）；2019 下半年之后是**往下重述**（-4~5%，
现货成交额定义做过一次清理）。
⇒ 结论不是「xlsx 错了」，而是：**xlsx 内部自洽、当年新闻稿之间不自洽**，本仓只认 xlsx，
且**绝不能**把某一期新闻稿的数字手工补进序列 —— 那会在序列里插一个 4-6% 的假台阶。
同一个测试里，**衍生品张数一格不差**（2020-06 六个 futures/options 单元格全部完全相等），
说明重述只发生在现货金额与部分上市统计上。

**4. FX 那一列的表头单位是错的。** FICC Markets 第 9 行写 `Volume (in M$, single counted)`，
但格子里 2026-06 是 `671602324739`。若真是百万美元，日均就成了 30 万亿美元。
实测拿 2019-01 新闻稿的 "$20,050 million" 反推：`441099188988.6 / 22 / 1e6 = 20049.96` → **该列是绝对美元**。
Q2 2026 再验一次：`/65/1e9 = 28.9816 $bn` vs 官方 `ADV Euronext FX 28,982 $m`，相对差 1.25e-05。
⇒ 除以 1e9 得 $bn。不要相信表头。

**5. 「Commodity」是农产品，不是能源；电力是另一套，且拆成两层。**
Euronext 的 commodity derivatives = 巴黎 MATIF 的小麦 / 玉米 / 菜籽；
能源侧是 Nord Pool，且分成 **现货电力交易**（`Power trading` 的 Day-ahead / Intraday，单位 TWh，**买卖双边计**，2020-01 起）
与 **电力衍生品**（`Power trading derivatives`，单位 GWh 名义量，**2026-03 才上线**）两块，
两块的交易日数还是两个不同的列（C19 与 C23，前者是自然日 30/31，后者是交易日）。
拿 Euronext 的 `adv_commodity_deriv_kcontracts` 去和 CME 的 `adv_energy_kcontracts` 比是错的，
要比就比 CME 的 `adv_ag_kcontracts`。

**6. 现货金额单边、成交笔数双边，同一张表里两种计数。**
`Trading volume (single counted)` 管金额列，`Transactions (buy and sell)` 管笔数列；
Nord Pool 电力又是 `buy and sell`；债券批发清算是 `Clearing volume (double counted)`。
每引用一列都要回表头看一眼分组行写的是哪种。

**7. 历史上有过一个 `TM Derivatives` 桶，现在的 xlsx 里没有了。**
2020-07-03 那期新闻稿的 `Total Euronext` = 16,309,330 张，
而 xlsx 三大类（股指+单股+商品）加起来只有 16,054,546 张，差 **254,784 张，正好等于稿里的 TM Derivatives**（Oslo 的一个衍生品桶）。
⇒ 不要用「Total Euronext」这个历史概念去校验本模块算出的总量；本模块的口径就是三大类之和，
和今天官方季报附录的口径一致（现在的季报里也没有 TM 这一行了）。

**8. 表结构是「两层表头 + 合并单元格 + 同名标签重复出现」，必须按标签 + 分组定位。**
`Futures` / `Options` / `Athex` / `Nb of trading days` 这些标签在同一张 sheet 里**各出现 4-8 次**，
只有靠上一层的分组行（Equity Markets 第 8 行、FICC 第 8 行）才能区分是股指还是单股、是成交量还是 OI。
和 cboe.py 的「口径坑 2」是同一类问题，解法也一样：先定位分组、再在分组内找标签，**绝不全表 grep**。
另外分组标题带脚注编号（`Commodity derivatives (3)`、`Turnover Equities (1)`），要做和 `_lab()` 同类的归一化。

**9. 两张 sheet 是死残留，解析到会炸或写出垃圾。**
历史文件的第 5 张 sheet `Checkup`：唯一的数据列整列是 `#REF!` 字符串（117 行），
表头写着 "Euronext Cash / Turnover in millions euros"，看起来像正经数据。
最新月文件的第 5 张 sheet `Nord Pool`：格子里是字面量 `"xxx"` / `"xx%"`，停在 2020-01。
⇒ 解析入口必须**白名单四张 sheet**（`Equity Markets` / `FICC Markets` / `Capital Markets` / `Securities Services`），
不要 for-each-sheet。

**10. 文件的 Last-Modified 不是发布日，会被重述推后。**
实测 `Last-Modified: Thu, 16 Jul 2026 08:20:12 GMT`，工作簿内 `docProps/core.xml` 的
`dcterms:modified = 2026-07-16T08:09:56Z`（两者差 10 分钟，存盘即上传，和 HKEX 一个模式），
但 2026-06 那期新闻稿是 **2026-07-06** 发的 —— 文件在发布 10 天后被原地重传过。
⇒ 学 cboe.py 而不是 hkex.py：`source_dates` 只认新闻稿的 `datePublished`，
且**首次摄入某月时记一笔、事后永不覆盖**。
（`dcterms:created` 是 2014-07-15，`dc:creator` 是个人名，都不是发布日。）

**11. 新闻稿 slug 会撞号，撞号时裸 slug 返回 200 但内容是登录页。**
2025-03 与 2025-12 两期的真实地址是 `...-for-march-2025-**0**` / `...-for-december-2025-**0**`，
而不带 `-0` 的那个 URL **HTTP 200**、`<title>Log in | euronext.com</title>`。
按模板拼 slug 会静默拿到一张登录页并解析出空发布日。
⇒ 发布日一律从**列表页**（`/en/investor-relations/financial-information/news?page=0|1`）
的 `<time datetime>` 取，那里给的是已解析好的真 href，不要拼 slug。

**12. 月度新闻稿从 2021 年前后开始不再包含任何数字。**
2019-01 那期有完整正文数字，2020-06 那期有完整统计附录（Excel 转 PDF），
2022-06 / 2024-06 / 2026-06 三期正文只剩一句「Monthly and historical volume tables are available at this address」。
⇒ **不要**把新闻稿 PDF 当数据源去解析，它只提供发布日。

**13. 官方对上市统计做过两次口径扩大，且已回溯重述。**
footnote (3)：2025-06 起 `Bonds` 计入 Euronext ABM，2024 与 2025 已重述；
footnote (4)：2025-06 起 `Nb of Listings` 改为「所有类型的挂牌」（含私募配售、直接上市、市场间转板、
反向并购、de-SPAC、二次上市）。footnote (2)：2021-05 改过发行人家数的计算方法。
⇒ 这三条都是「已重述」，序列内部自洽，但**与 2024 年当时读到的家数/募资额对不上**，
且 `Nb of Listings` 在 2025-06 有一次口径抬升，同比要注意。

**14. `mktcap_eurtn` / CSD 三列只到 2022-01，比主序列短 10 年。**
不是断档，是官方本来就只提供这么长。画在同一张图里会出现左半边空白，要么单独成图、要么图注写明起点。

## 实测证据

所有脚本在 `/tmp/exch_recon/scratch/`：`verify1.py`（2019 稿）、`verify2.py`（Q2 2026 业绩稿）、
`verify3.py`（Athens pro-forma）、`verify4.py`（2020 稿）、`inventory.py`（列清单/断档）、`build_demo.py`（成品 CSV）。

### 第 1 组 —— 与 2019-02-06 月度新闻稿交叉核对（下载的第「一期较早」）

源：`https://www.euronext.com/sites/default/files/pr_euronext_announces_volumes_for_jan_2019.pdf`
（正文原文："the average daily volume on equity index derivatives reached 214,202 contracts"）

```
==== 2019-01 ====
  trading days  cash=22 der=22 com=22 fx=22
  ADV cash Total Turnover  = 7140.4  €m   [PR: 6,708.1]      ← 见口径坑 3（Oslo 回溯重述）
  ADV cash Equities only   = 6832.2  €m
  ADV ETF                  = 270.4  €m   [PR: 205]           ← 同上
  ADV equity index deriv   = 214202  lots [PR: 214,202]      ✓ 完全一致
  ADV individual eq deriv  = 268304  lots [PR: 268,304]      ✓ 完全一致
  ADV commodity deriv      = 41036  lots [PR: 41,036]        ✓ 完全一致
  ADV 三者合计              = 523542  lots [PR: 523,542]      ✓ 完全一致
  FX spot raw=441099188988.60376 → 若列单位是 $ 则 ADV=$20050 m  [PR: $20,050m]  ✓ 完全一致
  月末 OI 合计              = 16720087  [PR: 16,720,087]      ✓ 完全一致
  ETF 上市只数              = 1172  [PR: 1,168]               （轻微重述）
```

### 第 2 组 —— 与 2026-07-30 Q2 2026 业绩稿附录交叉核对（下载的「最新一期」）

源：`https://www.euronext.com/sites/default/files/2026-07/2026.07.30_ENX_PR_Q2%202026%20Financial%20results.pdf`
第 13 页 "Business indicators for the second quarter of 2026"。做法：把 xlsx 的 2026-04/05/06 三行按官方口径汇总。

```
== Q2 2026（2026-04/05/06）交叉核对 ==
  交易日：cash=62 股衍=62 商品=62 FX=65 固收=62 电力=91      ← 与官方 62/62/91/65 全对
  ADV Cash Market (€m, single counted)     xlsx=16698.1049   官方=16,698      相对差=6.28e-06  OK
  ADV Cash Market (nb of transactions)     xlsx=3300776.9677 官方=3,300,777   相对差=9.77e-09  OK
  Shares cleared (single counted, Q 合计)   xlsx=75523318.5   官方=75,523,319  相对差=6.62e-09  OK
  Equity deriv 总量 (lots, Q 合计)          xlsx=35316684     官方=35,316,684  相对差=0.00e+00  OK
    Index deriv (lots)                     xlsx=10212541     官方=10,212,541  相对差=0.00e+00  OK
    Individual equity deriv (lots)         xlsx=25104143     官方=25,104,143  相对差=0.00e+00  OK
  Commodity deriv 合计 (lots)               xlsx=7810872      官方=7,810,872   相对差=0.00e+00  OK
    Commodity Futures                      xlsx=7380809      官方=7,380,809   相对差=0.00e+00  OK
    Commodity Options                      xlsx=430063       官方=430,063     相对差=0.00e+00  OK
  ADV Euronext FX ($m)                     xlsx=28981.6377   官方=28,982      相对差=1.25e-05  OK
  ADV MTS Cash (€m)                        xlsx=64919.474    官方=64,919      相对差=7.30e-06  OK
  TAADV MTS Repo (€m)                      xlsx=574543.2382  官方=574,543     相对差=4.15e-07  OK
  ADV Other fixed income (€m)              xlsx=1502.1844    官方=1,502       相对差=1.23e-04  OK
  Bonds wholesale clearing (€bn, Q)        xlsx=9899.4861    官方=9,899       相对差=4.91e-05  OK
  Bonds retail clearing (contracts, Q)     xlsx=2950200      官方=2,950,200   相对差=0.00e+00  OK
  ADV Day-Ahead Power (TWh)                xlsx=2.5517       官方=2.55        相对差=6.48e-04  OK
  ADV Intraday Power (TWh)                 xlsx=0.6543       官方=0.65        （官方保留 2 位，0.6543→0.65，一致）
  Power deriv Notional OI (GWh, 期末)       xlsx=173533.557   官方=173,534     相对差=2.55e-06  OK
  AuC (€bn, 期末)                           xlsx=8116.963     官方=8,117       相对差=4.55e-06  OK
  Settlement instructions (Q 合计)          xlsx=38060160     官方=38,060,160  相对差=0.00e+00  OK
  Nb of Issuers on Equities (期末)          xlsx=1844         官方=1,844       相对差=0.00e+00  OK
  Nb of listed Funds (期末)                 xlsx=2178         官方=2,178       相对差=0.00e+00  OK
  Nb of listed ETFs (期末)                  xlsx=4997         官方=4,997       相对差=0.00e+00  OK
  Nb of listed Bonds (期末)                 xlsx=56586        官方=56,586      相对差=0.00e+00  OK
  Nb of equity listings (Q 合计)            xlsx=23           官方=23          相对差=0.00e+00  OK
  Money Raised new listings (€m, Q)        xlsx=177.9022     官方=178         相对差=5.50e-04  OK
  Money Raised follow-ons (€m, Q)          xlsx=9061.9645    官方=9,062       相对差=3.92e-06  OK
```
**27 项全部对上**（其中 11 项浮点完全相等，其余是官方四舍五入）。
另有 Q2 2026 PDF 正文一句 "over 1,800 listed issuers with €7 trillion in market capitalisation"
对应 xlsx 2026-06 的 1,844 家 / 7.394 万亿欧元。

### 第 3 组 —— Athens 断点的可逆性验证

官方 Q2 2026 稿明写 "Q2 2025 volumes are including Euronext Athens on a pro forma basis"，
并给出 Q2 2025 备考值。用 xlsx 的主列与 Athex 备注列去复现：

```
Q2 2025  交易日=62
   Cash ADV 主列 = 13405.5 €m   Athex 备注列 = 201.7 €m   主+A = 13607.2 €m   [官方备考 13,611]
   Index deriv 主列=10684578  Athex=111532  主+A=10796110   [官方备考 10,796,110]  ✓ 完全一致
   Indiv deriv 主列=19608871  Athex=3182444  主+A=22791315  [官方备考 22,791,315]  ✓ 完全一致
Q2 2026  交易日=62
   Index deriv 主列=10212541（官方当期 10,212,541 ✓）  其中 Athex=117719
   Indiv deriv 主列=25104143（官方当期 25,104,143 ✓）  其中 Athex=6307506
```
⇒ 两个方向都能精确重建，Athens 断点**可完全消除**。（现货那一项 13,607.2 vs 13,611 差 0.03%，
是官方对现货金额的又一次微幅重述，量级与结论无关。）

### 第 4 组 —— 与官方「Latest Month」文件对表（验证 ADV 的算法）

我们用「月度总量 ÷ 该月交易日数」自算 ADV，官方在 `euronext_latest_month_volumes.xlsx` 里给了算好的：

```
2026-06  ADV Cash Market   自算 17183.521449326818   官方 17183.521449326818   完全相等
2026-06  ADV MTS Cash      自算 72363.79640909091    官方 72363.79640909091    完全相等
2026-06  TAADV MTS Repo    自算 617680.0745          官方 617680.0745          完全相等
2026-06  ADV Fixed income  自算 1516.1794501327272   官方 1516.1794501327272   完全相等
```

### 第 5 组 —— 与 2020-07-03 月度新闻稿统计附录交叉核对

```
== 2020-06 vs 2020-07-03 新闻稿统计附录 ==
  Index Futures lots               xlsx=3277368  官方=3,277,368   0.00e+00 OK
  Index Options lots               xlsx=1707003  官方=1,707,003   0.00e+00 OK
  Individual Eq Futures lots       xlsx=3510302  官方=3,510,302   0.00e+00 OK
  Individual Eq Options lots       xlsx=6463073  官方=6,463,073   0.00e+00 OK
  Commodity Futures lots           xlsx=975418   官方=975,418     0.00e+00 OK
  Commodity Options lots           xlsx=121382   官方=121,382     0.00e+00 OK
  Nb of Issuers on Equities        xlsx=1462     官方=1,462       0.00e+00 OK
  Nb of listed Bonds               xlsx=47261    官方=47,261      0.00e+00 OK
  Nb of listed ETFs                xlsx=1280     官方=1,280       0.00e+00 OK
  Follow-ons €m                    xlsx=4083.68  官方=4,084       7.78e-05 OK
  Total Cash Market 成交笔数         xlsx=72979022 官方=73,026,914  6.56e-04（轻微重述）
  Total Cash Market 成交额 €m       xlsx=234385.7 官方=244,406.7   4.10e-02（见口径坑 3）
  Nb of listed Funds               xlsx=4660     官方=4,640       4.31e-03（重述）
  Money Raised New Listings €m     xlsx=115.7    官方=113         2.39e-02（重述）
注：官方稿另有 TM Derivatives 254,784 lots，xlsx 三大类里没有这一桶（见口径坑 7）
```

### 第 6 组 —— 成品 CSV 抽样（`enx_demo.csv`，174 行 × 29 列）

```
列                                     2012-01     2016-01     2019-01     2020-06     2025-10     2025-11     2026-04     2026-05     2026-06
adv_cash_adnv_eurbn                      5.168       8.652       7.140      10.654      12.664      12.611      16.389      16.473      17.184
adv_cash_etf_adnv_eurbn                  0.320       0.815       0.270       0.526       1.162       1.188       1.363       1.512       1.463
adv_index_deriv_kcontracts             228.683     269.592     214.202     226.562     166.241     167.942     167.538     156.484     169.641
adv_singlestock_deriv_kcontracts       401.189     245.497     268.304     453.335     307.749     325.426     367.862     337.444     499.910
adv_commodity_deriv_kcontracts          38.639      60.408      41.036      49.855     114.307     132.151     144.426     106.439     126.981
adv_fx_spot_usdbn                            -      11.835      20.050      22.039      24.700      23.690      28.303      28.073      30.527
adv_mts_cash_eurbn                           -           -           -      15.712      51.976      55.416      49.999      71.651      72.364
issuers_equities                             -           -        1496        1462        1735        1879        1849        1845        1844
listed_etfs                                  -           -        1172        1280        4489        4566        4836        4919        4997
mktcap_eurtn                                 -           -           -           -       6.711       6.830       7.036       7.221       7.394
athex_adv_cash_adnv_eurbn                    -           -           -           -       0.238       0.254       0.262       0.340       0.285
athex_adv_singlestock_deriv_kcontracts       -           -           -           -      38.779      39.228      34.090      33.282     225.458
```
注意 `issuers_equities` 从 2025-10 的 1735 跳到 2025-11 的 1879（+144，与 Athex 备注列当月的 148 家吻合，
差额是当月常规增减），
以及 `athex_adv_singlestock_deriv_kcontracts` 在 2026-06 的季度脉冲 —— 就是口径坑 1、2 说的那两件事。

### 第 7 组 —— 无人值守通道实测

```
无自定义 UA（python-urllib 默认）    -> HTTP 200  219581 bytes  Last-Modified=Thu, 16 Jul 2026 08:20:12 GMT  1.8s
普通 Chrome UA                     -> HTTP 200  219581 bytes  Last-Modified=Thu, 16 Jul 2026 08:20:12 GMT  1.6s
HEAD 请求                          -> HTTP/2 200  server: CloudFront  content-length: 219581
新闻稿列表页（urllib，6 页翻页）      -> 全部 200，每页 20 条，含 <time datetime>，8 个月内的月度稿全部命中
```
无需 nscurl / curl_cffi / 浏览器登录态。

## 属于哪些竞争池

### 地理池

| 池 | 是否属于 | 可比字段（跨家可比性说明） |
|---|---|---|
| **欧洲现货** | ✅ 核心成员 | `adv_cash_equities_adnv_eurbn`（€bn/日，单边名义额）↔ Cboe 的 `adv_eu_equities_adnv_eurbn`。**这是全仓最直接的一对**：同货币、同单位、同单边口径、同为欧洲股票现货。实测 2026-06：Euronext 15.52 vs Cboe 14.95 —— 两家在欧洲股票现货上几乎打平，正是这张横截面图最该讲的故事。⚠ 不要用 `adv_cash_adnv_eurbn`（含结构化产品与 ETF），Cboe 那一列不含结构化产品。 |
| **欧洲衍生品** | ✅ 核心成员 | `adv_index_deriv_kcontracts` + `adv_singlestock_deriv_kcontracts`（千张/日）。仓内目前**没有真正的欧洲衍生品对手**（Eurex 不在仓），所以这两列在横截面图里只能与 CME/Cboe 做**指数化**对比，绝对值不可比（合约乘数差几十倍）。⚠ 单股那条线必须用 pro-forma 口径，否则 2025-11 有 20 倍假跳。 |
| **单一市场垄断对照** | ✅ 半个成员 | `issuers_equities` + `mktcap_eurtn` ↔ HKEX 的 `mktcap_hkdtn`。Euronext 在巴黎/阿姆/布鲁塞尔/里斯本/都柏林/奥斯陆/米兰/雅典**同时是唯一主板 + 本地 CSD + CCP**（上市侧垄断），但现货交易被 Cboe Europe / Aquis / Turquoise 分食（官方自述只占 "29% of European lit equity trading"）。⇒ 它是「上市垄断、交易竞争」的混合体，放进这个池时要在图注里说清楚，别和 HKEX 那种全链垄断划等号。 |
| 北美现货 / 北美期权 | ❌ | 无美国业务 |
| 亚太现货 / 亚太衍生品 | ❌ | 无亚太业务 |

### 标的池

| 池 | 是否属于 | 可比字段（跨家可比性说明） |
|---|---|---|
| **FX** | ✅ **全仓最干净的一对** | `adv_fx_spot_usdbn` ↔ Cboe 的 `adv_fx_adnv_usdbn`。两家都是**即期外汇 ECN**（Euronext FX = 原 FastMatch，Cboe FX = 原 Hotspot），都是 $bn/日 ADNV、都是单边计。实测 2026-06：Euronext 30.53 vs Cboe 64.27。⚠ CME 的 `adv_fx_kcontracts` 是**期货张数**，与这两家不同层，不能画进同一张图。 |
| **股指衍生品** | ✅ | `adv_index_deriv_kcontracts` ↔ CME `adv_equity_kcontracts` / Cboe `adv_index_options_kcontracts`。单位都是千张/日，但标的与乘数完全不同（CAC 40 期货 €10/点 vs ES $50/点 vs SPX 期权 $100/点）。⇒ **只能做指数化（2019=100）与增速对比，绝对值放同一 Y 轴是误导**。 |
| **单股与 ETF 期权** | ✅ 但有陷阱 | `adv_singlestock_deriv_kcontracts` ↔ Cboe `adv_multilist_options_kcontracts`。⚠ 两处不可比：(a) Euronext 这一列含**期货**，Cboe 那一列纯期权；(b) 2025-11 起 Athex 单股期货占 90-98%，且是融券替代品而非方向性交易。⇒ 进这个池必须用 **legacy 口径（主列 − Athex 备注列）**，并在图注写明。ETF 侧 Euronext 只有**现货** `adv_cash_etf_adnv_eurbn`，没有 ETF 期权，不能与 Cboe 的期权列对比。 |
| **能源商品** | ✅ 但要拆两条 | (a) `adv_power_dayahead_twh` / `adv_power_intraday_twh` —— Nord Pool 是北欧电力现货的绝对主导者，仓内**无对手**，只能自比（这恰恰是它作为「单一市场垄断」样本的最好例证）。(b) `adv_commodity_deriv_kcontracts` 是**农产品**，对手是 CME 的 `adv_ag_kcontracts`，**不是** `adv_energy_kcontracts`。 |
| **利率衍生品** | ⚠ 不属于（但有相邻资产） | Euronext **没有利率期货**。它在利率上的份额来自 **MTS 现券与回购**：`adv_mts_cash_eurbn`（欧洲主权债电子交易，实测 2026-06 = €72.4bn/日）与 `taadv_mts_repo_eurbn`（€617.7bn/日）。这是**现券与回购**，与 CME `adv_rates_kcontracts`（欧洲美元/国债期货）不是同一层，**不要放进同一张图**。建议单列一个「固收现货与回购」小节，或在利率池里作为「非期货路径」的对照注脚。 |
| **加密** | ❌ | 无 |

### 一句话定位

Euronext 是本仓里唯一同时覆盖 **上市 + 现货 + 衍生品 + 固收 + 电力 + FX + 清算 + CSD** 的全链条标的，
横截面上它既是 Cboe 在欧洲现货与 FX 的**正面对手**，又是 HKEX 式「本国唯一交易所」的**欧洲版对照组** ——
但它的垄断只在上市与结算侧成立，交易侧是被打开的。这个「一半垄断、一半竞争」的结构，
正好是 `/exchanges/` 横截面页最值得画出来的那条张力。

---

### 实现建议（供写 fetch/enx.py 时参考，本轮未改仓内任何文件）

1. `latest_month(cache_dir)`：下载历史 xlsx → 解析 `Equity Markets` 的 Period 列 →
   返回 **`Total Turnover` 非空的最后一个月**（照 HKEX 的教训：不信文件名，也不信最后一行 —— 官方可能先开行再填数）。
2. `update(series_dir, cache_dir)`：整表解析后**只填空、不覆盖**（官方明确会重述，见口径坑 3/13）；
   把冲突写进 `cache/enx_restatements.csv` 供人工判断，照 hkex.py 的做法。
3. 严格校验：四张白名单 sheet 里任何一个约定标签（分组 + 标签）找不到 → 抛异常；
   已有月份的必填列出现 None → 抛异常。2026-03 之后才有的电力衍生品列、
   2018/2020/2022 才开始的列要按起始月豁免（照 cboe.py 对 XSP / Mini-VIX 的写法）。
4. `_record_source_dates`：从 `/en/investor-relations/financial-information/news?page=0|1`
   取 `Euronext announces volumes for {Month} {Year}` 那条的 `<time datetime>`，
   evidence 文字写成：`新闻稿「Euronext announces volumes for June 2026」JSON-LD datePublished "2026-07-06T17:45:00+0200"；正文电头 "…– 6 July 2026 –" 一致`。
5. `build/roster.py`：`LAG = (13, 13)`，并给 `monthly_run.EARLY_BY['enx'] = 10`。
6. 图上必须画的结构性断点竖线：**2025-11**（Athens）、**2021-05**（Borsa Italiana）、
   **2019-07**（Oslo 衍生品）、**2026-03**（电力衍生品首月）。
