# MIAX（Miami International Holdings, NYSE: MIAX）—— 月度经营数据源可行性侦察

侦察日期 2026-08-06 ｜ slug `miax` ｜ 临时文件 `/tmp/exch_recon/scratch/miax/`

---

## 判定

**B —— 可实现，但有 6 个必须写进 docstring 的坑。**

三句话说清为什么不是 A、也不是 C：

- 不是 A：**主源是 PDF 不是 xlsx**，且必须按 **x 坐标定列**；官方 PDF 里
  `53,135` 会被 pdfplumber 拆成两个 word `5` + `3,135`，按 token 顺序解析会**静默**
  产出 `3,135` —— 数量级错 17 倍而不报错。这类「解析成功但数字是错的」正是本仓
  最忌讳的失败模式，必须靠列桶合并 + 交叉核对护栏兜住。
- 不是 C：抓取本身零阻力（普通浏览器 UA 的 `curl` / `urllib` 直接 200，无
  Cloudflare / Akamai / JS 渲染 / 登录墙），PDF 里有官方自述的
  `Updated on August 5, 2026`（与 HTTP `Last-Modified` 互证），
  且**实测把 4 期 PDF + 136 个月的 API 数据全部解析出来并与新闻稿、10-K 三方对上了**。
- **信息增量确实是本轮最大的一家**：MIAX 的 `Multiply-listed options` ADV 与 RPC
  与 Cboe 是**逐字同口径**（同一个业务分段名、同一个 RPC 定义），
  Cboe multi-list RPC ~$0.06 vs MIAX ~$0.11-0.12，这是全仓唯一一组
  可直接并排的美股期权 take rate。

**唯一的实质缺陷是历史深度分层**：含 RPC 的 IR 报表只到 2025-01（公司 2025-08 才上市）；
ADV 与市占可以靠 miaxglobal.com 自己的市占看板 API 回溯到 **2015-04**（136 个月无断档），
但那条线**没有 RPC**，而且与 IR 口径有一个稳定的 **-0.3%** 水平差（见口径坑 4）。

---

## 数据源

### 主源 A：IR 站「Volume & RPC/Capture Report」PDF（口径权威，含 RPC）

| 项 | 值 |
|---|---|
| 列表页 | `https://ir.miaxglobal.com/volume-rpc-reports` |
| 页面结构 | 永远挂 3 条链接：`Latest Monthly Volumes Press Release`、`<当年> Historical Volumes RPC File (PDF)`、`<上一年> Historical Volumes RPC File (PDF)` |
| 当年 PDF | `https://ir.miaxglobal.com/image/MIH_Volume_and_RPC_Report_{MMDDYYYY}.pdf`（实测 `..._08052026.pdf`） |
| 上一年 PDF | `https://ir.miaxglobal.com/image/MIH_Volume_and_RPC_Report_{YYYY}_{MMDDYYYY}.pdf`（实测 `..._2025_05062026.pdf`） |
| 真实存储 | 302 跳到 `https://filecache.investorroom.com/mr5ir_miaxglobal/{n}/<同名>.pdf`，`{n}` 每期变（实测 252），**不可猜** |
| 格式 | 单页 PDF，1 张宽表；`pdfplumber` 可解（本机已装） |
| 抓取方式 | `urllib.request` + **浏览器 UA**（默认 `Python-urllib/3.x` 一律 **403**，见口径坑 6） |

**文件名里的 `MMDDYYYY` 是发布日不是数据月**，所以和 `fetch/cboe.py` 一样：
只能先解析列表页拿链接，不能按月份拼 URL。已实测旧期快照
`..._07072026.pdf`（6 月数据）仍在 filecache 上活着，但同期的 `..._06032026.pdf` 已 404 ——
**旧期不可靠，别指望回补**。

### 主源 B：miaxglobal.com 市占看板 JSON API（ADV 深历史，无 RPC）

MIAX 自己官网 `/company/data/market-share` 那张饼图背后的接口，纯 JSON，无鉴权：

```
https://www.miaxglobal.com/indsum/getDate?exchType=options            -> {"status":"success","date":"20260805"}
https://www.miaxglobal.com/indsum/detail?tid=1&exchType=options&date=YYYYMMDD
https://www.miaxglobal.com/indsum/detail?tid=1&exchType=equities&sumType=volume&date=YYYYMMDD
https://www.miaxglobal.com/indsum/detail?tid=1&exchType=equities&sumType=notional&date=YYYYMMDD
```

`tid=1` = **MTD Average**；把 `date` 给成某月最后一个日历日，返回的就是**该自然月**
每家交易所的日均量 + 一行 `TOTAL`。字段：
`EQUITY_OPTION_TOTAL_AVERAGE_VOLUME` / `INDEX_OPTION_TOTAL_AVERAGE_VOLUME` /
`OPTION_TOTAL_AVERAGE_VOLUME` / `..._PERCENTAGE` / `EXCHANGE_GROUP`（MIAX 四家标为 `MIAX`）/
`DATA_START_DATE` / `DATA_END_DATE`。

- 这是 **MIAX 自己官网发布的数据**，不是 FIA / Bloomberg 之类第三方聚合商，符合仓库硬约束。
- 但它同时报出 Cboe / Nasdaq / NYSE / BOX / MEMX 各家的量 —— **那部分对别家而言是第三方**，
  只能用来算 MIAX 自己的行业口径与份额，**不许倒灌进 `series/cboe.csv`**。
- `robots.txt` 未 Disallow `/indsum/`；136 次请求 114 秒（~0.84 s/次）无任何限流或封禁。

### 校验源（不入库，只做交叉核对）

- 月度新闻稿：`https://ir.miaxglobal.com/{YYYY-MM-DD}-Miami-International-Holdings-Reports-{Month}-{Year}-Trading-Results`
  （2025 年底那期命名不同：`...-Reports-Trading-Results-for-November-2025`）。
  IR 新闻列表**只挂最近 5 条**，历史 PR 要去 `miaxglobal.com/news?page=N`（约 98 页）。
- SEC EDGAR **CIK 0001438472**，10-K `miax-20251231.htm`（2026-03-06 报送）的
  “Key Business Metrics” 节给年度 ADV / 市占 / RPC，可做年度闭合检验。

---

## 可提取字段

照 `series/cboe.csv` 风格（`month` = `YYYY-MM`）：

| 列名 | 来源 | 口径说明 |
|---|---|---|
| `trading_days_options` | PDF | 当月美股期权交易日数。PDF 里 Options 段与 Equities 段共用同一行值，Futures 段单列（1 月差 1 天）。 |
| `industry_adv_options_kcontracts` | PDF | **全行业** equity & ETF 期权 ADV（千手/日）。这是 MIH 自报的行业分母，与 API 的 `TOTAL` 不等，见口径坑 4。 |
| `adv_multilist_options_kcontracts` | PDF | MIAX 四所合计 equity & ETF 期权 ADV（千手/日）。**与 `series/cboe.csv` 同名列逐字同口径**。 |
| `share_multilist_options_pct` | PDF | MIH 官方自报份额（%）。官方只给 1 位小数，精度不够时用 `adv/industry` 自算。 |
| `rpc_multilist_options_usd` | PDF | **滚动三月平均** RPC（美元/手），口径 = 交易与清算费 − 流动性返还 − 经纪/清算/交易所费 − Section 31 费，除以期内总手数。**与 `cboe.csv` 的 `rpc_multilist_options_usd` 同名同义**。滞后一个月。 |
| `adv_miax_options_kcontracts` | API | MIAX Options（代码 M）单所 ADV。 |
| `adv_pearl_options_kcontracts` | API | MIAX Pearl Options（P），2017-02 起。 |
| `adv_emerald_options_kcontracts` | API | MIAX Emerald（D），2019-03 起。 |
| `adv_sapphire_options_kcontracts` | API | MIAX Sapphire（S），2024-08 起。四列之和 ≠ `adv_multilist_options_kcontracts`，差 -0.3%，见口径坑 4；建议按四列**占比**去拆 PDF 的合计值，而不是直接写 API 绝对数。 |
| `industry_adv_equities_mnshares` | PDF | 全美股票市场 ADV（百万股/日，含 TRF 场外）。**这一列官方承认出过数据处理错误并重述过**，见口径坑 5。 |
| `adv_equities_mnshares` | PDF | MIAX Pearl Equities ADV（百万股/日）。Cboe 那边是 `adv_us_equities_matched_shares_bn`（十亿股），横截面页要换算 1 : 1000。 |
| `share_equities_pct` | PDF | MIAX Pearl Equities 份额（%，分母含 TRF）。 |
| `capture_equities_usd_per100shares` | PDF | 每 100 股捕获（美元），滚动三月平均，**长期为负**（inverted / taker-rebate 模型）。Cboe 同位列是 `rpc_us_equities_usd_per100shares`，但 Cboe 的分母是 **touched** shares，MIAX 是总股数 —— **名字像，分母不同，不能直接减**。 |
| `adnv_equities_usdbn` | API | MIAX Pearl Equities 日均名义额（十亿美元），`sumType=notional` 的 `EXCHANGE_AVERAGE_NOTIONAL_VALUE`。2020-12 起。这一列是与 Cboe `adv_eu_equities_adnv_eurbn` / `adv_fx_adnv_usdbn` 同维度的 notional 口径。 |
| `trading_days_futures` | PDF | MIAX Futures 交易日数（与股票期权差 0-1 天）。 |
| `adv_futures_ag_contracts` | PDF | 农产品期货 ADV（**手**，不是千手）。核心是 Minneapolis Hard Red Spring Wheat。 |
| `rpc_futures_ag_usd` | PDF | 农产品期货滚动三月 RPC（美元/手），$1.8-2.5 量级。 |
| `adv_futures_fin_contracts` | PDF | 金融期货（Bloomberg 股指期货系列）ADV，**2026-05 才有**。 |
| `rpc_futures_fin_usd` | PDF | 金融期货滚动三月 RPC，**目前为负**（-$1.44 / -$1.77，新品促量返还）。 |

不建议入库的两项：
- PDF 里的 `MIH - ADV from launch trade date` 行（金融期货首月的另一种 ADV 定义，
  分母只算上线后的交易日，2026-05 是 13,105 而非 5,897）。**同一格两个数**，
  入库会制造一个永久的解释负担；用主行即可，把它写进 docstring。
- Q1'26 / Q2'26 / FY'25 / Year to Date 这些季度与年度列 —— 月度列已足够，
  加进来只会让 `_month_columns` 类逻辑多一条误判路径。

---

## 历史深度

| 指标 | 最早月 | 断档 | 出处 |
|---|---|---|---|
| 四所合计 & 单所期权 ADV、行业 ADV、份额 | **2015-04** | **无**（实测 136 个月连续，2015-04 → 2026-07 全部返回非空） | indsum API |
| MIAX Pearl Equities 股票 ADV / ADNV / 份额 | **2020-12** | 无 | indsum API（Pearl Equities 2020 年才开业，这就是它的全生命周期） |
| **RPC / capture（全部三条）** | **2025-01** | 无 | IR PDF 只有 2025、2026 两份 |
| 农产品期货 ADV + RPC | **2025-01** | 无 | IR PDF |
| 金融期货 ADV + RPC | **2026-05** | 无（产品 2026-05-17 上线） | IR PDF |
| 年度口径 ADV/RPC（做校验用） | **2024**（FY） | — | 10-K 的 2025 vs 2024 对照 |

各所首个非零月（API 实测）：MIAX **2015-04**、Pearl **2017-02**、Emerald **2019-03**、
Sapphire **2024-08**。注意 Emerald 2019-03 起量后 MIAX 单所量当月骤降（721k vs 上年同期 745k
而集团合计跳到 1,714k）—— 那是**内部导流**不是市场份额变化，画单所线一定要标注。

**结论对照仓库偏好**：ADV / 份额线满足「2015/2016 起」的理想档；
**RPC 线只有 2025-01 起共 19 个月，连「最少 2019 起」都达不到**。
所以 RPC 图在 2026 年内只能画绝对值与环比，**做不了同比也做不了指数化**，
到 2026-12 才第一次有完整的 12 个月同比。这一点必须在页面上写明，
不能让读者以为那条线是断的。

---

## 发布节奏

**次月第 3-5 个工作日**，与月度新闻稿同一天发（PDF 与 PR 同步更新）。实测四期：

| 数据月 | 发布日 | 是次月第几个工作日 |
|---|---|---|
| 2025-11 | 2025-12-05（五） | 5 |
| 2026-05 | 2026-06-03（三） | 3 |
| 2026-06 | 2026-07-07（二） | 4（7/3 因独立日休市） |
| 2026-07 | 2026-08-05（三） | 3 |

`build/roster.py` 的 `LAG` 建议 `(6, 6)` —— **季末月不需要单独一档**：MIAX 的月度报表
独立于季报发布（2026-08-05 当天既发 7 月数据也发 Q2 财报，但 6 月数据早在 7/7 就发了）。

**source_dates 有两个互相印证的权威字段**，取任一都行、取两个更稳：

1. PDF 第 2 行 A 列自述 `Updated on August 5, 2026` —— 与 `fetch/cboe.py` 的
   `_updated_on()` 是同一种东西，可以照抄那段逻辑（`%B %d, %Y` / `%b %d, %Y` 两种都试）。
2. PDF 直链的 HTTP 头 `last-modified: Wed, 05 Aug 2026 14:05:35 GMT`。

实测两者对同一期完全一致（2026-08-05）。上一年那份 PDF 的两个字段也一致（2026-05-06）。
建议 `evidence` 字段两句都写，像 `cme` 那行一样互证。

---

## 口径坑（按踩坑概率排序）

1. **数字会被 PDF 拆成两个 word，按 token 顺序解析会静默出错。**
   2025 年那份 PDF 里 `53,135` 的字距使 `pdfplumber.extract_words()` 返回
   `'5'` 和 `'3,135'` 两个词；`195` 返回 `'1'` + `'95'`。第一版解析器因此把
   Jan-25 的行业 ADV 写成 **3,135**（真值 53,135）、Pearl Equities ADV 写成
   **95**（真值 195）—— 全程不抛异常。
   **解法**：先按表头行每个 `Mon-YY` word 的 x 中心建列，再把整行所有落在数值区的
   word **按最近列分桶**、桶内按 x 拼串，最后才 `float()`。绝不能用
   `text.split()` 的顺序去对齐列。（2026 年那份 PDF 拆得比较温和 —— `7,359` → `'7'`+`',359'` ——
   所以「在最新一期上测通过」不代表在去年那份上也对，两份都要测。）

2. **同一个行标签在三个 section 里各出现一次，且标签本身会被脚注上标折行。**
   `Trading Days` / `Industry ADV` / `MIH ADV` / `MIH market share` /
   `Rolling three-month average RPC` 在 `Options (Equity and ETF)`、`U.S. Equities`、
   `Futures` 三段里重复。必须先用大标题切段再查行。
   另外 `Industry ADV(1) (contracts, thousands)` 里的上标 `(1)` 基线比正文高 1.4pt，
   行聚簇容差若 ≤2pt 会把 `ADV(1)` 单独切成一行，剩下的标签变成
   `Industry (contracts, thousands)` —— `startswith('Industry ADV')` 当场失配。
   容差取 **4pt**（行距 ~9pt），并把标签归一化（剥 `(1)`~`(5)` 与单位括号）后**全等**匹配。

3. **`indsum` API 对未来日期会静默返回错的月份。**
   `date=20261231` 返回的是 `01/08/2026 -> 05/08/2026`（当月 MTD），不是空、不是报错。
   同样地，把 `date` 给成月中某天就得到半个月的 MTD。
   **必须校验返回体的 `DATA_START_DATE` 是该月 1 号、`DATA_END_DATE` 是该月最后一个交易日**，
   不满足就当作「该月尚未收官」跳过。先打 `indsum/getDate?exchType=options`
   拿到官方最新可用交易日，比什么本地日历都可靠。

4. **API 的 MIAX 四所合计比 IR 报表**稳定**低 0.26%-0.32%，行业分母差得更多。**
   实测 2026 全部 7 个月：API 合计 / PDF = 0.9967 ~ 0.9976，方向一致、幅度稳定；
   而 API 的行业 equity 口径比 PDF 的 `Industry ADV` 低 3.4%-4.5%（PDF 分母更接近 OCC
   的 equity+ETF 分类，API 是 OPRA 挂牌代码分类，ETF 期权的归属不同）。
   **结论**：`adv_multilist_options_kcontracts` / `industry_adv_*` / `share_*`
   一律以 PDF 为准；API 只用来（a）2025-01 之前回补，（b）拆四所占比。
   2025-01 是唯一同时有两个源的月份，**必须在图上标结构性断点**，
   否则 2024-12 → 2025-01 会凭空出现一个 +0.3% 的假台阶。

5. **官方会重述，而且重述集中在 `industry_adv_equities_mnshares` 这一列。**
   2025 年那份 PDF 的脚注 4 白纸黑字写着 U.S. equities 行业 ADV 在
   2026 年 2 月和 2025 年若干月「因数据处理错误报错了」。实测同为 2025 年、
   两个不同发布日的 PDF 逐格比对，只有这一列变过：
   `2025-07` 17,648 → **18,033**（+2.2%）、`2025-05` 17,585 → 17,586、`2025-08` 16,379 → 16,380。
   10-K（2026-03 报送）给的 FY25 Market ADV 是 17,550，5 月那份 PDF 加权算出来是 17,585 —— 也对不上。
   仓库的「已有值永不覆盖」策略会把 17,648 永久冻住。
   **建议照 `fetch/spgi.py` 的做法**：重述不自动吞，但每次重解析都与库里比一遍，
   不同就打 warning（而不是静默跳过），否则这类修订永远发现不了。

6. **`ir.miaxglobal.com` 按 UA 拒绝，不是按 TLS 指纹。**
   默认 `Python-urllib/3.x` 对列表页与 PDF 直链都是 **HTTP 403**；
   换成常规 Chrome UA 立刻 200。不是 Cloudflare 挑战、不是 Akamai JA3
   （没有 HOOD 那种「连上但永不返回」的症状），`curl` 一行就能过。
   `www.miaxglobal.com` 的 `indsum` API 连 UA 都不校验。

7. **跨年那一期要下两份 PDF。**
   列表页同时挂当年与上一年两个链接，而且**上一年那份会被重新发布**：
   `MIH_Volume_and_RPC_Report_2025_05062026.pdf` 是 2026-05-06 才更新的，
   里面 Dec-25 的 RPC（$0.106）已经填上 —— 这一格在 2025-12-05 那份里还是空的。
   所以 MIAX **没有** Cboe 的「12 月 RPC 永久窟窿」问题，但代价是：
   **每次 `update()` 都要把当年和上一年两份都下下来解析并合并**，
   否则 12 月的 RPC 会一直留白，而且是那种下个月也补不上的留白。

8. **RPC / capture 滞后一个月，最新月天然为空 —— 这不是解析失败。**
   与 Cboe 完全一样：`2026-08-05` 那期里 Jul-26 的 ADV 有值，
   `rpc_multilist_options_usd` / `capture_equities_usd_per100shares` /
   `rpc_futures_*` 四格全空。`_validate()` 必须只对「最新 ADV 月」豁免 RPC 缺失，
   对更早的月份缺 RPC 一律抛异常。

9. **Futures 段的表结构 2025 → 2026 变过。**
   2025 那份只有一行 `MIH - ADV (contracts)`（当时只有农产品，没有子标题）；
   2026 那份分成 `Agricultural:` / `Financial:` 两个子标题各带一组行。
   解析器要能吃「Futures 段内 `sub is None` 时按 Agricultural 记账」。
   `adv_futures_fin_contracts` 在 2026-05 之前天然为空，不能因此报错。

10. **`capture_equities_usd_per100shares` 长期为负，而且它和 Cboe 的同位列分母不同。**
    MIAX Pearl Equities 走 inverted 定价，2025 全年在 -$0.028 ~ $0.000，
    2026 年才转正到 +$0.004 附近。**负数不是解析符号错**（PDF 里写成 `($0.028)`）。
    与 `cboe.csv` 的 `rpc_us_equities_usd_per100shares` 并排画时必须注明：
    Cboe 是 per 100 **touched** shares、MIAX 是 per 100 shares，分母不同。

---

## 实测证据

脚本：`/tmp/exch_recon/scratch/miax/parse_miax.py`（PDF 解析）、
`backfill.py`（API 全量回补）、`crosscheck.py`（三方核对）。

### 1) 下载：4 期 PDF 全部 200，普通 curl 即可

```
HTTP 200 size=228079 MIH_Volume_and_RPC_Report_08052026.pdf        last-modified: Wed, 05 Aug 2026 14:05:35 GMT
HTTP 200 size=233533 MIH_Volume_and_RPC_Report_2025_05062026.pdf   last-modified: Wed, 06 May 2026 16:26:28 GMT
HTTP 200 size=141521 MIH_Volume_and_RPC_Report_12052025.pdf        last-modified: Tue, 02 Dec 2025 15:54:53 GMT
HTTP 200 size=225963 (filecache) MIH_Volume_and_RPC_Report_07072026.pdf
默认 urllib UA：ir.miaxglobal.com 两个地址均 HTTP 403；换 Chrome UA 全部 200。
```

### 2) 解析最新一期（2026-08-05 发布，2026 年）—— 14 列 × 7 个月全中

```
title      : Miami International Holdings Volume & Revenue Per Contract/Capture Report - 2026
updated_on : 2026-08-05

month    trad_d  industry_adv  MIH_adv  share%   RPC$   ind_eq_mn  MIH_eq_mn  eq_share%  capture$  ag_adv  ag_RPC$  fin_adv  fin_RPC$
2026-01    20       63025      11100    17.6    0.107     19436       161       0.8       0.004     7359    2.291      -        -
2026-02    19       63264      10812    17.1    0.107     19999       174       0.9       0.006    14944    2.104      -        -
2026-03    22       61770      10696    17.3    0.110     20471       194       0.9       0.005    10394    1.982      -        -
2026-04    21       62496      10593    16.9    0.116     17815       177       1.0       0.004    12421    1.977      -        -
2026-05    20       67186      11060    16.5    0.120     19398       188       1.0       0.000    10111    2.075     5897   -1.441
2026-06    21       69896      11318    16.2    0.124     23383       192       0.8      -0.001    16203    2.262     5740   -1.766
2026-07    22       64394      11019    17.1     ---      17437       117       0.7        ---     12123     ---      4194     ---
```

（最右四格空白 = RPC 滞后一个月，见口径坑 8。）

### 3) 解析一期较早的（2026-05-06 发布，2025 全年）

```
updated_on : 2026-05-06
month    trad_d  industry_adv  MIH_adv  share%   RPC$   ind_eq_mn  MIH_eq_mn  eq_share%  capture$   ag_adv  ag_RPC$
2025-01    20       53135       8870    16.7    0.100     15438       195       1.3      -0.028    15577    2.481
2025-02    19       54563       8625    15.8    0.103     15618       170       1.1      -0.024    24316    2.452
2025-03    21       53182       8268    15.5    0.106     16008       163       1.0      -0.020    14715    2.426
2025-04    21       55340       9099    16.4    0.116     19318       206       1.1      -0.014    17861    2.469
2025-05    21       51352       8957    17.4    0.115     17586       192       1.1      -0.014    13291    2.393
2025-06    20       50576       8218    16.2    0.117     18245       187       1.0      -0.014    23531    1.983
2025-07    22       51516       8607    16.7    0.112     18033       191       1.1      -0.014     6954    1.829
2025-08    21       54909       9525    17.3    0.109     16380       169       1.0      -0.013    11190    1.837
2025-09    21       61299      10787    17.6    0.103     18309       205       1.1      -0.015     5973    2.369
2025-10    23       67193      13057    19.4    0.100     20996       218       1.0      -0.011     7286    2.289
2025-11    19       62132      10915    17.6    0.103     18794       181       1.0      -0.007    13153    2.277
2025-12    22       53703       9201    17.1    0.106     15879       120       0.8       0.000     4843    2.281
```

### 4) 交叉核对 A —— 2026-08-05 新闻稿（PRNewswire 原文表格）逐格比对，**9/9 全等**

```
OK  trading_days_options              pdf=22.0      pr=22
OK  industry_adv_options_kcontracts   pdf=64394.0   pr=64394
OK  adv_multilist_options_kcontracts  pdf=11019.0   pr=11019
OK  share_multilist_options_pct       pdf=17.1      pr=17.1
OK  industry_adv_equities_mnshares    pdf=17437.0   pr=17437
OK  adv_equities_mnshares             pdf=117.0     pr=117
OK  share_equities_pct                pdf=0.7       pr=0.7
OK  adv_futures_ag_contracts          pdf=12123.0   pr=12123
OK  adv_futures_fin_contracts         pdf=4194.0    pr=4194
```

### 5) 交叉核对 B —— 2025 年 12 个月按交易日加权 vs 10-K「Key Business Metrics」

10-K 出处：EDGAR CIK 0001438472，`miax-20251231.htm`（2026-03-06 报送）。

```
adv_multilist_options_kcontracts   加权=  9537.9   10-K= 9538    差 -0.00%
industry_adv_options_kcontracts    加权= 55797.6   10-K=55798    差 -0.00%
adv_equities_mnshares              加权=   183.2   10-K=  183    差 +0.11%
adv_futures_ag_contracts           加权= 12989.6   10-K=12989    差 +0.00%
```

（10-K 原文：`MIH ADV – Equity and ETF (in thousands) 9,538` / `MIH market share 17.1%` /
`Total Options revenue per contract $0.108` / `Agricultural products ADV 12,989` /
`Agricultural products RPC $2.241` —— 全部与 PDF 的 FY'25 列一致。）

### 6) 交叉核对 C —— 官方重述实证（两期 2025 年 PDF 逐格 diff）

```
2025-05  industry_adv_equities_mnshares   旧=17585.0  新=17586.0
2025-07  industry_adv_equities_mnshares   旧=17648.0  新=18033.0
2025-08  industry_adv_equities_mnshares   旧=16379.0  新=16380.0
（其余 100+ 格全部逐字节相同）
```

### 7) 交叉核对 D —— indsum API 四所拆分 vs PDF 合计

```
2026-01  API合计=11067.7k (MIAX 4926307 / PEARL 1989431 / EMERALD 2305745 / SAPPHIRE 1846234)  PDF=11100.0k  差 -0.29%
2026-04  API合计=10558.7k (MIAX 4868204 / PEARL 1213897 / EMERALD 2065636 / SAPPHIRE 2410933)  PDF=10593.0k  差 -0.32%
2026-07  API合计=10990.7k (MIAX 5814421 / PEARL 1217249 / EMERALD 1631901 / SAPPHIRE 2327131)  PDF=11019.0k  差 -0.26%
```

股票口径同样对上：API `PEARLEQ (H)` 2026-07 `EXCHANGE_AVERAGE_TRADE_VOLUME = 116,811,747`
（= 116.8 百万股/日），新闻稿 `MIAX Pearl ADV (Millions) 117`；
份额 `0.67%` vs 新闻稿 `0.7%`。notional 口径 `EXCHANGE_AVERAGE_NOTIONAL_VALUE = $4,058,114,391`
（$4.06bn/日，占在所成交名义额 0.39%）。

### 8) API 全量回补 —— 136 个月零断档

```
DONE months 136  bad []  secs 114        （2015-04 → 2026-07，逐月请求，无一失败）
各所首个非零月：MIAX 2015-04 / PEARL 2017-02 / EMERALD 2019-03 / SAPPHIRE 2024-08

month      MIAX    PEARL  EMERALD SAPPHIRE    合计   行业(equity)  份额%
2015-04  1015.6      0.0      0.0      0.0   1015.6    13773.8    7.37
2016-01  1067.4      0.0      0.0      0.0   1067.4    16868.0    6.33
2017-02   963.4     32.3      0.0      0.0    995.7    14623.0    6.81
2019-03   721.3    939.0     54.0      0.0   1714.3    16997.0   10.09
2020-03   997.9   1106.9    967.1      0.0   3071.9    26382.5   11.64
2022-06  2027.8   1727.3   1060.1      0.0   4815.2    35019.9   13.75
2024-08  2767.6   1386.3   1764.3     68.5   5986.6    42602.6   14.05
2025-01  3693.6   1667.8   2467.1   1015.1   8843.6    51406.9   17.20
2026-07  5814.4   1217.2   1631.9   2327.1  10990.7    61472.8   17.88
（单位：千手/日）
```

### 9) 无人值守可行性

| 检查项 | 结果 |
|---|---|
| Cloudflare / Akamai 挑战 | 无。无 403-with-challenge、无「连上不返回」的 JA3 症状 |
| JS 渲染 | 列表页是静态 HTML，PDF 直链在源码里；API 是纯 JSON |
| 登录墙 | 无 |
| UA 校验 | `ir.miaxglobal.com` 需要浏览器 UA（默认 urllib UA → 403）；`www.miaxglobal.com/indsum` 不校验 |
| 限流 | 136 次连续请求 114 秒，无 429、无封禁 |
| `robots.txt` | `/indsum/` 未被 Disallow；`ir.miaxglobal.com` 无 robots.txt |
| 需不需要 nscurl / curl_cffi | **不需要**，标准库 `urllib` 加 UA 即可 |

---

## 属于哪些竞争池

### 地理池

| 池 | 属于? | 可比字段（跨家逐字同口径的那个） |
|---|---|---|
| **北美期权** | ✅ **核心** | `adv_multilist_options_kcontracts` —— 与 `cboe.csv` **同名同义**（都是 equity & ETF 多重挂牌期权日均手数，千手）。份额用 `share_multilist_options_pct`，但两家分母不同（MIAX 用自报行业 ADV、Cboe 用 OCC），横截面页建议**自己用同一个分母重算**：从 `indsum` API 的 `TOTAL` 行取全行业 ADV，两家同除，才是真·可比份额 |
| **北美现货** | ✅ | `adv_equities_mnshares`（MIAX Pearl Equities）vs `cboe.csv` 的 `adv_us_equities_matched_shares_bn` —— 量纲差 1000 倍，横截面页统一到 mn shares。MIAX 只有 1 家股票所、份额 0.7-1.3%，是这个池里的**尾部玩家对照** |
| 欧洲现货 / 欧洲衍生品 | ❌ | MIAX 的国际业务是 BSX（百慕大）与 TISE（根西），两家都是上市地不是成交场，月度成交量不披露 |
| 亚太现货 / 亚太衍生品 | ❌ | 无 |
| 单一市场垄断对照 | ❌ | MIAX 是彻头彻尾的多方混战参与者，正好是 HKEX 那种垄断结构的**反面对照** |

### 标的池

| 池 | 属于? | 可比字段 |
|---|---|---|
| **单股与 ETF 期权** | ✅ **本仓最有价值的一组** | ADV 用 `adv_multilist_options_kcontracts`，take rate 用 **`rpc_multilist_options_usd`**。这是全仓唯一一对**逐字同定义**的美股期权 RPC（两家的 RPC 定义都写着 “transaction and clearing fees less liquidity payments, brokerage, clearing and exchange fees, and Section 31 fees, divided by total contracts”）。实测量级：MIAX $0.107→$0.124（2026 逐月上行），Cboe multi-list ~$0.06 —— **差近一倍，且方向相反**，这条线单独就值得一张图 |
| 股指衍生品 | 🔶 边缘 | `adv_futures_fin_contracts`（Bloomberg 股指期货，2026-05-18 上线）。日均 4-6k 手 vs CME `adv_equity_kcontracts` 的数百万手，**差 3 个数量级，不能进份额图**，只能做「新产品爬坡曲线」。同理 MIAX 四所的 `INDEX_OPTION_TOTAL_AVERAGE_VOLUME` 实测恒为 0 —— MIAX **完全不做指数期权**，这本身就是与 Cboe 最大的结构差异（Cboe 的 index options 是它的利润中枢），值得在护城河叙事里写明 |
| 利率衍生品 | ❌ | 无 |
| 能源商品 | ❌ | 无 |
| **农产品商品**（现有池表里没有这一桶） | ✅ | `adv_futures_ag_contracts` + `rpc_futures_ag_usd` vs `cme.csv` 的 `adv_ag_kcontracts`。量纲差 1000（MIAX 记手、CME 记千手），量级差 ~300 倍（MIAX 12k 手/日 vs CME ~4,000k 手/日）。**建议把「能源商品」池改名成「大宗商品」并容纳农产品**，否则 MIAX Futures 无处安放 |
| FX | ❌ | 无（Cboe 有 FX，MIAX 没有） |
| 加密 | ❌ | 曾有 MIAXdx，**2025-11-25 已宣布卖给 Robinhood**，2026 年报表里已无此段。做历史图时若回溯到 2025 及以前要注意这条业务线的消失 |

### 一句话总结它在横截面里的位置

MIAX 是**北美多重挂牌期权池里唯一一家把 RPC 按月披露、且定义与 Cboe 逐字一致的挑战者**：
份额从 2015 年的 7.4% 一路做到 2026-07 的 17.9%，同期 RPC 还在往上走。
它同时是**北美现货池的尾部对照**（Pearl Equities 0.7% 份额、capture 常年为负）
和**大宗商品池的微型玩家**（农产品 12k 手/日）。
把「份额上行 + take rate 上行」这个组合与 Cboe「份额稳、multi-list take rate 低位」
并排放，是这次扩容里信息密度最高的一张横截面图。
