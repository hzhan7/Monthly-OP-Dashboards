# 复核报告 — NDAQ 月度数据源侦察

复核日期 2026-08-06 · 复核员独立复现 · 工作目录 `/tmp/exch_recon/verify_ndaq/`
被复核文件 `/tmp/exch_recon/ndaq.md`（原判定 **B**）

**我没有读原 agent 的解析脚本**（`scratch/ndaq_parse.py` / `ndaq_verify.py`），
全部数字用我自己写的解析器从我自己重新下载的文件里重算。

---

## 最终判定

**B（维持原判）** — 但原文有 **2 个实质错误** 和 **4 个次要错误**，实现前必须改。

维持 B 而不是降级的理由：四类虚报（a 历史造假 / b 第三方源 / c 需登录态 / d 口径写错）**一个都不成立**，
且原文对自己最大的短板（三条腿只有 19 个月）是**主动披露**而非掩盖。

> **2026-08-19 追记**：那个「三条腿只有 19 个月」的短板**已经补掉两条**，而且走的是
> 本文没核过的另外两条链路（不是那份滚动替换的 IR PDF）：
> `vol_nordic_derivs_mmcontracts` 用 Nasdaq Nordic **交易所公告档案**回到 **2013-01（163 个月）**，
> 19 个重叠月逐月全等；`vol_us_cash_matched_mnsh` 用 B 组三盘口（Nasdaq+BX+PSX）之和
> 回到 **2010-10（190 个月）**，19 个重叠月里 18 个 \|差\| ≤ 0.0101%。
> **仍是 19 个月的只剩两条**：`vol_us_options_mmcontracts` 与 `vol_nordic_cash_value_usdbn`。
> 本文其余核查针对的是 IR PDF 与 marketshare xlsx 两条链路，**结论全部不受影响**。
维持 B 而不是升到 A 的理由：原文自己给的理由成立，另加我发现的 E1。

---

## 一、独立复现结果：全部通过

### 1.1 抓取（我自己抓的，不是看它的日志）

| URL | 我的实测 | 与原文一致 |
|---|---|---|
| `ir.nasdaq.com/financials/volume-statistics` | 200 · 103,179B · 0.58s | ✅ 字节数完全一致 |
| `ir.nasdaq.com/static-files/465d2157-c476-4546-a9f7-8d7ad0c9be77` | 200 · 352,432B · 1.72s | ✅ 字节数完全一致 |
| ↑ `Content-Disposition` | `Monthly Reporting Sheet - July 2026 Final.pdf` | ✅ |
| ↑ `Last-Modified` | `Wed, 05 Aug 2026 18:28:01 GMT` | ✅ 秒级一致 |
| `nasdaqtrader.com/.../2026/marketshare26.xlsx` | 200 · 266,892B · 免 UA | ✅ |
| ↑ `Last-Modified` | `Mon, 13 Jul 2026 19:11:15 GMT` | ✅ 秒级一致 |
| `.../2025/marketshare25.xlsx` | 200 · 259,110B | ✅ |
| `.../2026/msoption26.xlsx` | 200 · 17,153B | ✅ |

落地页正则只抽到**一条** `/static-files/<uuid>`，在 `<div class="blueHeading">Monthly Volumes</div>`
下的 `<a>Monthly Metrics</a>` 里 —— 与原文描述逐字吻合。

### 1.2 UA 敏感性（原文 口径坑 5）—— 复现且更精确

```
带浏览器 UA  urllib  → 200 352,432B 1.72s
裸 urllib 默认 UA    → FAIL RemoteDisconnected  32.1s
裸 urllib 落地页     → FAIL TimeoutError        35.2s
curl 空 UA (-A '')   → 000（连接被吃掉）
curl 默认 UA (curl/8)→ 403  440B  0.17s      ← 原文没测到这一条
curl 浏览器 UA       → 200  352,432B 0.98s
```

原文结论「拦的是 UA 不是 TLS 指纹、不需要 curl_cffi/nscurl」**成立**：
同一个 TLS 栈（curl）换 UA 就从 403 变 200，证明与 JA3 无关。
补充一条原文没写的：**`curl` 默认 UA 是干脆利落的 403，而 `urllib` 默认 UA 是挂住 30 秒**
—— 无人值守要设 timeout，否则一旦 UA 配错，cron 会卡住而不是快速失败。

### 1.3 PDF 解析 —— 逐格比对，零差异

我用自己的 `fitz` 文本流解析器重算，与原文声称的数字**逐个比对**：

- 第 1 页四条序列 × 19 个月（2025-01..2026-07）：**76 个数字全部一致**，无一例外。
  含原文列出的 `us_options` 2026 = 384/373/393/382/389/428/402、
  `eu_derivs` 2025 = 5.3/4.8/…/6.0、`us_matched` 2026-06 = 72,547、`eu_equity` 2026-07 = 88.0。
- 第 2 页季度面板 21 行 × 14 季：原文摘录的 7 行**全部一致**
  （`q_us_options` 811…1200、`q_us_options_capture` $0.13…$0.10、`q_us_matched_share_of_total` 16.7%…14.7%、
  `q_us_equity_capture` $0.64…$0.69、`q_eu_equity_mktshare` 69.4%…74.5%、
  `q_etp_aum` $366…$1,114、`q_listed_total` 5,413…5,768）。
- PDF metadata：`creationDate = D:20260805140952-04'00'`、`producer = Microsoft® Excel® for Microsoft 365`
  —— ✅ 与原文一致。

**口径来自 PDF 自己的段落标题，我逐字抄下来核对，不存在 (d) 类口径写错：**

```
U.S. equity options volume (millions of contracts)
European options and futures volume (millions of contracts)
U.S. matched equity volume (millions of shares)
European equity volume (value of shares traded, $ billion)
```

张数就是张数、金额就是金额、月度就是月度、美元就是美元 —— 原文四个列名的单位后缀全对。
「官方给的是月度总量不是 ADV」（口径坑 1）也由标题证实（没有 "average daily" 字样）。

### 1.4 交叉核对 A（IR vs nasdaqtrader）—— 完全复现

18 个重叠月逐月比 `IR us_matched` vs `NASDAQ+NTX+PSX`：

```
2025-01  IR=43,688  trader=43,688.090  +0.0002%   days=20
2025-06  IR=49,572  trader=49,567.017  -0.0101%   days=20   ← 最大偏差
2025-12  IR=52,388  trader=52,386.493  -0.0029%   days=22
2026-03  IR=68,730  trader=68,729.714  -0.0004%   days=22
2026-06  IR=72,547  trader=72,546.039  -0.0013%   days=21
max |diff| = 0.0101%   18/18 通过
```

与原文**逐位一致**，含 `trading_days` 五个值。对照源真实存在、数字对得上。

### 1.5 交叉核对 B（季度市占率）—— 复现并**扩展到全部 14 个季度**

原文只给了 3 个季度。我跑了全部 14 个：

```
2023-Q1 trader 16.6715% / IR 16.7%      2025-Q4 trader 14.4090% / IR 14.4%
2024-Q4 trader 14.4081% / IR 14.4%      2026-Q1 trader 15.0726% / IR 15.1%
2025-Q2 trader 13.8840% / IR 13.9%      2026-Q2 trader 14.7239% / IR 14.7%
max 成交量偏差 0.0047%   max 市占率偏差 0.0477pp
```

原文引用的三个季度（14.4090 / 15.0726 / 14.7239）与我算的**小数点后四位全同**。
且 14/14 全过 —— 比原文声称的还稳。

### 1.6 交叉核对 C（PDF 自闭合）—— 完全复现

24 组（4 序列 × 6 季度）月度求和 vs 官方季度：

```
max |diff| = 0.397%  at eu_equity 2026-Q2 (月和 278.1 vs 官方 277)
```

与原文声称的**最大偏差值和所在格完全一致**。阈值建议 0.6% 合理。

### 1.7 重述体检 —— 完全复现

`ms25.xlsx`(2025-12 定格) vs `ms26.xlsx`(2026-06 版)，重叠 **244 月**（2005-09..2025-12），
`consolidated / nasdaq / second / psx / days` 五字段逐格比：**不一致数 = 0**。
「Nasdaq 不重述美股月度成交量」成立。

### 1.8 发布日 —— 9 条逐个打开验证（含 2016 / 2019）

| 数据月 | 我读到的 GLOBE NEWSWIRE 电头 | 原文 | |
|---|---|---|---|
| 2026-07 | NEW YORK, Aug. 05, 2026 | 08-05 | ✅ |
| 2026-06 | NEW YORK, July 08, 2026 | 07-08 | ✅ |
| 2026-03 | NEW YORK, April 08, 2026 | 04-08 | ✅ |
| 2026-01 | NEW YORK, Feb. 04, 2026 | 02-04 | ✅ |
| 2019-01 | NEW YORK, Feb. 04, 2019 | 02-04 | ✅ |
| 2019-07 | NEW YORK, Aug. 06, 2019 | 08-06 | ✅ |
| 2019-11 | NEW YORK, Dec. 02, 2019 | 12-02 | ✅ |
| 2016-01 | NEW YORK, Feb. 04, 2016 | 02-04 | ✅ |
| 2016-10 | NEW YORK, Nov. 03, 2016 | 11-03 | ✅ |

slug 三套命名成立：2025+ 用 `nasdaq-reports-{m}-{y}-volumes`，2024 及更早用 `nasdaq-{m}-{y}-volumes`。
季末月变体 `nasdaq-june-2019-volumes-and-2q19-statistics` 我实测 **404** —— 印证口径坑 12。

**LAG (6,9) 复核通过**：按仓库 `build/roster.py` 的「月末后第几天」口径，
实测常规月最晚第 6 天（2019-07→8/6），季末月最晚第 8 天（2026-03→4/8、2026-06→7/8）。
(6,9) 留了 1 天余量，与仓库 GRACE=5 叠加后安全。

### 1.9 msoption 陷阱（口径坑 6）—— 完全复现

```
msoption26 "Combined Nasdaq Equity Options Volume (in contracts)" 2026-06 = 214,471,257
  = NTX 19,062,753 + NOM 36,578,367 + PHLX 158,830,137   （只有三家，无 ISE/GEMX/MRX）
IR 同月 = 428 百万张 → 确实差一半
三个月快照：2026-06 / 2026-05 / 2025-06，非历史序列
```

数字**逐位一致**。这条坑是真的，很重要。

### 1.10 sheet 混淆陷阱（口径坑 10）—— 复现且比原文更严重

5 张 sheet 的**表头逐字相同**，取错 sheet 静默出错：

```
2026-06  US Equities      consolidated=491,030,721,181  nasdaq_matched=70,830,986,796  ← 正确
         NASDAQ           consolidated=253,864,108,057  nasdaq_matched=51,531,386,408  ← 少 27%
         NYSE             consolidated=129,663,478,468  nasdaq_matched=11,444,790,665
         Amex + Regional  consolidated=107,503,134,656  nasdaq_matched= 7,854,809,723
         US_ETF           consolidated=112,203,459,141  nasdaq_matched=10,959,594,784
```

底部说明行也确认（row 253/256/259）。`US_ETF` 与 `US Equities` 的 `max_row` 都是 259，
**不能用 max_row 区分 sheet**。

---

## 二、四类虚报专项检查：全部不成立

| 指控 | 结论 | 证据 |
|---|---|---|
| **(a) 只抓最新一期却声称多年历史** | ❌ 不成立 | 我实抓 `marketshare26.xlsx`：250 个月、2005-09..2026-06、**零断档**。**2019 与 2020 全部 12 个月逐月实测存在**，我打印了 2019-01 / 2019-12 / 2020-03 / 2020-12 的原始值（见 §三 E1 表）。且原文**主动声明** A 组只有 19 个月、不能回溯 —— 这是自曝其短，不是虚报。（2026-08-19：「不能回溯」对 IR PDF 那条链路仍然成立，但其中两条序列后来由**另外两条官方链路**回补到了 2013-01 / 2010-10，见文首追记） |
| **(b) 拿第三方聚合站当官方源** | ❌ 不成立 | 全部三个域名均为 Nasdaq 自营：`ir.nasdaq.com`（IR）、`www.nasdaqtrader.com`（Nasdaq 美国市场官方数据站）、`api.news.eu.nasdaq.com`（Nasdaq Nordic 官方 news API）。**全文未出现 FIA / investing.com / wikipedia / 任何数据聚合站**。符合 README 第 4 行硬约束「数据全部来自公司官网 IR 或 SEC 申报的原始披露」 |
| **(c) 靠浏览器登录态或手工点击** | ❌ 不成立 | 我全程用 `urllib` + 一个静态 UA 字符串，**零浏览器、零 cookie、零登录、零 JS**，全部 200。落地页 → 正则抓 uuid → 下 PDF 三步纯脚本可完成。cron 可跑 |
| **(d) 字段口径写错** | ❌ 不成立 | PDF 段落标题原文逐字核对（见 §1.3），张数/金额、月度/季度、USD/EUR、总量/ADV 四个维度全对。原文还**主动**用 口径坑 1 和 11 提醒 ADV 与量纲问题 |
| **(e) 声称 A 但关键字段缺失** | ❌ 不成立 | 它声称的是 B，不是 A |

---

## 三、发现的错误

### E1（实质）—— 「五个字段零空值」是**假的**，且会让实现当场崩

原文 §7 与「历史深度」表两处断言：

> `consolidated / nasdaq_matched / second_matched / psx_matched / trading_days` 五个字段空值均为 0
> **无**（250 个月连续，5 个字段零空值）

**这是只检查了 `is None` 的产物。实际缺失值是字符串 `'n/a'`，不是 `None`。**
我的实测：

```
consolidated     None=0  'n/a'=0
nasdaq_matched   None=0  'n/a'=0
trading_days     None=0  'n/a'=0
NTX/BX_matched   None=0  'n/a'=40   ← 2005-09 .. 2008-12
PSX_matched      None=0  'n/a'=61   ← 2005-09 .. 2010-09

五字段同时为数值的月份 = 189 / 250，最早 2010-10（不是 2005-09）
```

后果有两层，都很硬：

1. **崩**：我第一版脚本照原文口径写 `nasdaq + ntx + psx`，在 2010-09 及更早的行上
   直接 `TypeError: unsupported operand type(s) for +: 'int' and 'str'`。
   这不是理论风险 —— 是我实际踩到的。
2. **历史深度要改口**：原文把「B 组能回溯到 2005-09」当作扣分项的**对冲**写进判定理由。
   但 IR 口径的 `us_matched = Nasdaq + NTX + PSX` 这条**复合**序列，
   在 2010-10 之前根本不存在（三个盘口没同时有数）。
   - `us_nasdaq_matched` 单列：2005-09 起 ✅
   - `us_ntx_matched`：2009-01 起
   - `us_psx_matched`：2010-10 起
   - 复合 `us_matched`（IR 可比口径）：**2010-10 起**

对「≥2019」的硬要求毫无影响（2010-10 远早于 2019），所以**不降级**。
但「250 个月零空值」这句话必须从交付物里删掉，否则实现会照抄进 docstring。

### E2（实质）—— 欧洲池的可比性建议**方向反了**，会画出误导图

原文「地理池 · 欧洲现货」写：

> 建议横截面页上只比**市占率**（Nasdaq 季度 `q_eu_equity_mktshare` 74.5% vs Cboe 的欧洲份额），别比绝对值

**这条恰好把唯一能比的和唯一不能比的搞反了。** 我用算术证明：

```
Nasdaq 2026-Q2 欧洲现货 = $277bn，官方市占率 74.5%
  ⇒ 隐含的分母（可寻址市场）= 277 / 0.745 = $372bn/季 = $124bn/月

Cboe 2026-06 adv_eu_equities_adnv_eurbn = 14.95  (来自 series/cboe.csv)
  ⇒ Cboe 一家 ≈ EUR 329bn/月 ≈ $382bn/月
```

**Cboe 一家的欧洲月成交额，就是 Nasdaq 整个「欧洲市场」分母的 3 倍。**
说明 Nasdaq 的 74.5% 是**北欧/波罗的海本地市场**的份额（PDF 脚注 5：
"portion of on-exchange and MTF total volumes"，语境是 Nordic/Baltic），
而 Cboe Europe 的份额是**泛欧**份额（约 20–25%）。两者分母是两个不同的宇宙。
把 74.5% 和 25% 叠在一张图上 = 严重误导读者「Nasdaq 是 Cboe 的 3 倍强」。

正确做法与原文相反：
- **绝对值可比**（都换成 USD 月度总额或都换成 ADV）：Nasdaq ≈ EUR 80bn/月 vs Cboe ≈ EUR 329bn/月，
  这是真实的量级关系 —— Nasdaq 欧洲现货只有 Cboe 的 1/4。
- **市占率不可比**，除非明确标注两条线的分母不同、且分开画两个 panel。

### E3（次要但要改）—— Nordic API 的 URL 模板**不能复现**

原文「降级/旁证源」给：

```
https://api.news.eu.nasdaq.com/news/query.action?...&freeText=Statistics from Nasdaq Nordic Exchange
→ 附件 PDF Statistics_{Month}_{Year}_summary.pdf，可回溯到 2017-09
```

我实测：API 本身可用（200、JSON、免 UA 免登录），但**这个 freeText 检索不出任何统计稿**。
我翻了 200 条结果 × 3 种检索词（原模板 / `Statistics from Nasdaq` / `Nordic Exchanges monthly statistics`），
命中的统计稿数 = **0 / 0 / 0**，返回的全是 Verkkokauppa、Tokmanni、Lundin Mining 之类的公司公告
—— freeText 是按词打分排序，不是短语匹配。

那份 PDF 本身是真的（我读了 `scratch/ndaq_nordic_stats_2026-07.pdf`，
"EUR 3.3 billion"、"202,060"、"Vilnius had 22 trading days, and all other exchanges had 23 trading days"
逐字都在，交叉核对 D 的算术成立）。**但拿到它的路径不是原文写的那条**，
且「可回溯到 2017-09」这句我**无法验证**，应视为未经证实。

影响有限（原文自己标了「不做主数据，只备注」），但实现时别照抄这个 URL。

### E4（次要）—— 期权对标字段自相矛盾

- 「地理池 · 北美期权」说：与 Cboe `adv_us_options_kcontracts`（总数）比，**不要**用 multilist。✅ 正确
- 「标的池 · 单股与ETF期权」说：跨家可比对象是 Cboe **`adv_multilist_options_kcontracts`**。❌ 与上条打架

正确的是前者。理由有二：(1) Nasdaq 那个数含指数期权（PDF 脚注 1），拿去比 Cboe 的 multilist（不含指数）是苹果比橘子；
(2) 仓库 `build/exchanges.py` 第 77/227 行实际用的横截面字段就是 `adv_us_options_kcontracts`。

### E5（次要）—— 四处事实性小错

1. **msoption 标题不是「写死 BX」**。原文口径坑 6 说「标题写死 `Nasdaq Stock Market and Nasdaq BX Volumes`」。
   实测：`msoption25.xlsx` 是 `…Nasdaq BX Volumes`，但 **`msoption26.xlsx` 已改成 `…Nasdaq NTX Volumes`**。
   这个文件也跟着改名了 —— 不能用标题里的 "BX" 做判据。
2. **旋转侧标 bbox 不是「恒为」**。原文说 `bbox 恒为 x0=30.9, x1=40.3`。
   实测第 1 页确为 x0=30.9/x1=40.3，但**第 2 页是 x0≈28.6–28.8 / x1≈34.2–34.5**（字号不同）。
   写死这两个数会漏掉第 2 页的 4 个侧标（Index / Listings / Equity Derivatives / Cash Equities）。
3. **它推荐的旋转判据有假阳性**。`len(word) > 2 and (x1-x0) < (y1-y0)` 在第 2 页会误伤脚注词
   **`all`**（x0=326.2 x1=330.8 y0=394.1 y1=399.0，宽 4.6 < 高 4.9，长度 3 > 2）。
   对纯数值提取无害（脚注不参与解析），但这条规则**没有它声称的那么干净**，别当成已验证。
4. **底部说明行第 1 列是字符串不是数字**。原文说「第 1 列是数字 `4`」，实测是 `'2'` / `'3'` / `'4'` 三个**字符串**。
   它推荐的「按第 1 列是 datetime 筛行」是对的，但理由描述错了。

### E6（提示级）—— 自闭合表格的选择性摘录

原文 §4 列了 US 期权的 2025-Q1 / 2025-Q4 / 2026-Q2 三格，
没提 **2025-Q2（月和 958 vs 官方 957，+0.104%）** —— 那是期权里第二大的偏差。
结论（max 0.397%、阈值 0.6%）不受影响，但摘录有挑好看的倾向。

---

## 四、能不能和 cme / cboe / hkex 放进同一个竞争池

**结论：北美两条腿可比且量级合理；欧洲两条腿不可比（细节见 E2）。**

先确认仓库口径：`series/cme.csv`、`cboe.csv`、`hkex.csv` **全部是 `adv_*` / `adt_*`（日均）**，
`build/exchanges.py` 的横截面也全建在 ADV 与 y/y 指数化上。
Nasdaq 给的是**月度总量** —— 不换算就进池，会比同行大 ~20 倍。这是本家最大的接入风险，
原文口径坑 1 已正确识别。

我实算了换算后的结果（`vol ÷ trading_days`），验证量级是否合理：

| 月份 | NDAQ 美股 bn股/日 | Cboe 美股 bn股/日 | NDAQ 期权 k张/日 | Cboe 期权 k张/日 |
|---|---|---|---|---|
| 2026-01 | 2.844 | 1.872 | 19,200 | 19,569 |
| 2026-03 | 3.124 | 2.048 | 17,864 | 21,079 |
| 2026-06 | 3.455 | 2.185 | 20,381 | 22,977 |

两条腿都落在同一量级、且方向符合已知事实（Nasdaq matched 份额 ~14–15% vs Cboe ~9–11%）
—— **换算口径正确，可以直接进 `/exchanges/` 横截面。**

| 池 | 可比 | 判断 |
|---|---|---|
| **北美现货** | ✅ | `vol_us_matched_shares_mm ÷ us_trading_days ÷ 1000` ↔ Cboe `adv_us_equities_matched_shares_bn`。已实算验证。交易日 250 个月全有且全为数值 |
| **北美期权** | ✅ | `vol_us_options_mmcontracts × 1000 ÷ us_trading_days` ↔ Cboe `adv_us_options_kcontracts`（总数）。已实算验证。注意用**美股交易日**近似期权交易日（两者一致） |
| **欧洲现货** | ⚠️ 仅绝对值 | 市占率**禁止**跨家比（E2）。绝对值可比但需 FX + 欧洲交易日，而**欧洲交易日 IR 不给**，只能从 Nordic 统计稿 OCR 正文取（"23 trading days"）—— 那个源的检索路径本身还没跑通（E3）。⇒ 实操上建议**只画 Nasdaq 自己的月度总额时间序列，不进横截面** |
| **欧洲衍生品** | ⚠️ 无对标 | 4–8mm 张/月。仓库 12 家里**没有 Eurex / Euronext**，原文推荐的对标对象在本仓不存在。只能单独画或做指数化 |
| **股指衍生品** | ✅ 原文判断正确 | `q_index_futures_mmcontracts` 是**别家撮合、Nasdaq 只收授权费**的量（PDF 脚注 6 证实：跟踪 Nasdaq 指数的期货+期货期权+指数期权）。**不能**与 CME `adv_equity_kcontracts` 同柱比「谁成交大」—— 两者有重合部分，是同一批合约被两家分别记账。原文这条警告是全文最有价值的一条，务必保留 |
| **亚太 / 利率 / FX / 加密** | ❌ | Nasdaq 无相关业务，原文判断正确 |
| **上市与指数 AUM（新池）** | ✅ 值得开 | `q_listed_*` / `q_etp_aum_usdbn` 对 HKEX `new_listings` / `mktcap_hkdtn` 与 MSCI AUM。原文这条建议合理，且正确指出是**季度**、须进 `series/ndaq_q.csv` |

---

## 五、给实现阶段的具体警告

1. **必须把 `'n/a'` 当缺失处理，不能只判 `None`。**
   读 `marketshare{YY}.xlsx` 的每个数值格都要 `isinstance(v, (int, float))`，
   否则 2010-09 及更早的行会在 `nasdaq+ntx+psx` 处抛 `TypeError`。
   复合 `us_matched` 序列**从 2010-10 起**，不是 2005-09。
2. **列名要 fallback**：`'NTX Matched Volume' if in header else 'BX Matched Volume'`。
   同理 `msoption{YY}.xlsx` 的标题行也从 BX 改成了 NTX，**不要用标题文字做判据**。
3. **必须锁死 `wb['US Equities']`**。5 张 sheet 表头逐字相同、`US_ETF` 连 `max_row` 都一样（259），
   取错静默少 27%，永远不报错。
4. **筛行只认「第 1 列 isinstance datetime」**。底部有 `'2'/'3'/'4'` 开头的说明行（字符串，非数字）。
5. **静态浏览器 UA 是硬要求，且必须设 timeout。** `ir.nasdaq.com` 对 `Python-urllib` 是**挂 30 秒**
   而不是快速失败；`nasdaqtrader.com` 完全不挑 UA。别为了「统一」给 trader 也加 UA 逻辑。
   同域不同路径策略不同（新闻稿页裸 UA 能过，static-file 不能）—— 「有一条 URL 通」不等于「这个域没问题」。
6. **「最新月」只能解析 PDF 内容取「当年那行最后一个非空月」。**
   UUID 不含月份、每月原地替换；`Content-Disposition` 的 `filename` 可做交叉校验但不能做唯一判据。
   **绝对不要用 B 组（nasdaqtrader）当最新月判据** —— 它比 A 组晚一周多
   （2026-06 数据的 `Last-Modified` 是 07-13，而 IR 的 07 月数据 08-05 就发了）。
7. **旋转侧标的 bbox 不要写死坐标**（第 1 页 x0=30.9 / 第 2 页 x0≈28.6）。
   用「宽 < 高」判据，但要加长度或数值过滤 —— 它会误伤第 2 页脚注里的 `all`。
8. **欧洲市占率不得进横截面。** 见 E2。若一定要放，两条线必须分 panel 并标注分母不同。
9. **期权对标统一用 Cboe `adv_us_options_kcontracts`**（仓库 `build/exchanges.py` 用的就是它），
   不要用 `adv_multilist_options_kcontracts`。
10. **季度 revenue capture 当期格是估计值会被改**（PDF 脚注 1 原文已核实）。
    本轮无法实测重述幅度（历史版本拿不到）。除这四列外，Nasdaq 美股月度量**不重述**
    （244 个月逐格比，0 处不一致）—— `update()` 可以不做全量重述台账，但 capture 四列要留可覆盖口子。
11. **LAG (6, 9) 通过复核**，按仓库「月末后第几天」口径。实测常规月最晚第 6 天、季末月最晚第 8 天。
12. **发布日证人用新闻稿电头**（原文建议正确）。补一条它没说的：
    新闻稿页面的 HTTP `Last-Modified` **完全没用** —— 2016 和 2019 的老新闻稿返回的都是今天
    （`Thu, 06 Aug 2026 03:24:45 GMT`），是 CMS 渲染时间。只有 `static-files` 的 `Last-Modified` 有意义。
13. **季末月新闻稿 slug 回补要人工。** 我实测 `nasdaq-june-2019-volumes-and-2q19-statistics` = 404，
    印证原文口径坑 12。另外 `nasdaq-march-2020-volumes` 也 404，说明命名不止三套。
14. **Nordic API 的 freeText 模板不可用**（E3）。若确需这个 sanity check，得重新找检索路径。
15. **IR 历史确实回不去，已复核到底**：`http://ir.nasdaq.com/monthly-reporting/`（2016 新闻稿里的老路径）
    302 到同一个落地页、同一个 uuid；`?year=2019` 参数无效；
    2016 新闻稿附件 `92d76af2-…` = `NDAQ_News_2016_2_4_Financial.pdf`，正文只有一句
    「数据挂在 IR 网站」，**一个数字都没有**（2019 与 2026 的新闻稿同样如此，我逐条读了正文）。
    原文这一点没有虚报。
