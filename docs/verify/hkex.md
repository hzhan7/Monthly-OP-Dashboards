# HKEX（slug: hkex）—— 成交股数与成交笔数补抓核查

核查日期 **2026-08-07**。本文里每一个 URL、数字、HTTP 头都是本机当天实测所得，
不引用任何上游 agent 的结论、不使用它的缓存。抓取代码落在 `fetch/hkex.py`，
数据落在 `series/hkex.csv` 末尾新增的 7 列。

---

## 结论

**官方一直在发，只是本仓一直没抓。** 而且它与本仓既有的 `adt_hkdbn` 是**同一套逐日底稿**，
不是"另一份口径相近的数据"——90 个月逐位重现，见下面的闭合 ③。

- 成交股数与成交笔数**不在** hkexgroup.com 的 Monthly Market Highlights xlsx 里
  （现货段只有 ADT、市值、新上市三行，本机全表扫过确认）。
- 它们在 HKEX 的**另一份刊物 Monthly Bulletin**（月报），栏目原文
  `Turnover volume (mil shares)` 与 `No. of deals`，两行都同时给「当月合计」和「- Daily average」。
- 逐日底稿在 **Securities Statistics Archive → Trading value, volume and number of deals**，
  主板最老一册标签 `1986-1989`、GEM `1999-2003`。
- 全链路 plain `urllib`（连 UA 都不用设）即可 200，无 Cloudflare / Akamai 挑战、
  无登录墙、无 JS 渲染门、无验证码。**没有遇到任何需要绕过的东西。**

---

## 数据源

两个端点都在 `https://www.hkex.com.hk/eng/stat/smstat/mthbull/` 下。

### B1 逐日档案（历史主力）

```
索引  rpt_data_statistics_archive_trading_data.json        主板
      rpt_data_statistics_archive_trading_data_gem.json    GEM
```

索引是一个数组，每条 `{"label": "2020-2024", "url": "/eng/stat/smstat/mthbull/…_2020_2024.json"}`。
实测索引内容：

| 板块 | 分册（label） |
|---|---|
| 主板 | 2025-2026 (up to the end of previous month) / 2020-2024 / 2015-2019 / 2010-2014 / 2005-2009 / 2000-2004 / 1995-1999 / 1990-1994 / **1986-1989** |
| GEM | 2024-2026 (up to the end of previous month) / 2019-2023 / 2014-2018 / 2009-2013 / 2004-2008 / **1999-2003** |

每册是一张**逐日**表，表头原文：

```
Year/Month/Day │ (空列) │ Total trading value<br/>(HKD) │ Total trading volume<br/>(Shares) │ Number of deals
```

- 落地页：`/Market-Data/Statistics/Consolidated-Reports/Securities-Statistics-Archive/Trading_Value_Volume_And_Number_Of_Deals?sc_lang=en`
  （GEM 同路径把 `Securities-Statistics-Archive` 换成 `Securities-Statistics-Archive-GEM`）
- 那个夹在中间的空列放的是**半日市标记 `*`**。实测打星的日子：
  `2025/01/28`（年三十）、`2025/12/24`、`2025/12/31`、`2026/02/16`（年三十）、
  `2020/01/24`、`2020/08/19`、`2021/02/11`、`2021/06/28`、`2021/12/24`、`2021/12/31`、
  `2022/01/31`、`2022/08/25`、`2023/10/09`、`2024/02/09`、`2024/12/24`、`2024/12/31`
  —— 圣诞前夕 / 除夕 / 年三十，加上台风黑雨缩短交易时段的那几天。
- 表体**只有日期行**，没有小计行、没有脚注行（2019-2026 共 21,390 个数值格全量扫过，
  且**全部是整数**，无小数、无 `-`、无 `N/A`）。

### B2 Monthly Bulletin — Stock market highlights（最新月 + 交叉核对）

```
rpt_Stock_market_highlights_{YYMM}.json       主板
rpt_Stock_market_highlights_GEM_{YYMM}.json   GEM
```

- 落地页：`/Market-Data/Statistics/Consolidated-Reports/Monthly-Bulletin?sc_lang=en`
  与 `…/Monthly-Bulletin-GEM?sc_lang=en`
- **只挂最近 13 个月**。实测 `2412` / `2312` / `2212` / `2505` 全部 **HTTP 404**，
  `2606` / `2607` 200。所以它当不了历史来源。
- 表头是 `June 2026` / `June 2025`（本月 vs 去年同月两列）。
  代码按**月份名**认列，不按列号 —— 认错一列就是把去年同月当本月入库。
- 2026-06 主板原文（`rpt_Stock_market_highlights_2606.json`，逐字）：

  | 行 | 当月合计 | - Daily average |
  |---|---|---|
  | `Turnover value (HK$mil)` | 6,698,704 | 318,986 |
  | `Turnover volume (mil shares)` | 7,370,724 | 350,987 |
  | `No. of deals` | 100,533,281 | 4,787,299 |
  | `Market capitalisation (HK$mil)` | 43,256,811 | — |

---

## 我复核的闭合证据

### 闭合 ①　逐日档案汇总 ≡ Monthly Bulletin（2026-06，主板）

我自己把 21 个交易日逐行加起来：

```
Total trading value  合计 6,698,704,112,075 HKD  ÷1e6 = 6,698,704.112075 HK$mil  ÷21 = 318,986 HK$mil/日
Total trading volume 合计 7,370,724,218,440 股    ÷1e6 = 7,370,724.218440 mil sh  ÷21 = 350,986.868 mil sh/日
Number of deals      合计       100,533,281 笔                                    ÷21 =  4,787,299.095 笔/日
```

Monthly Bulletin 2606 主板印的是 `6,698,704 / 318,986`、`7,370,724 / 350,987`、`100,533,281 / 4,787,299`。
**六个数逐位相同**（日均那三个按官方的整数位四舍五入后相同）。

GEM 同月（`rpt_Stock_market_highlights_GEM_2606.json`）：档案汇总
`1,886,925,475 HKD / 6,309,593,626 股 / 121,511 笔`，21 个交易日，
→ `1,887 / 90`、`6,310 / 300`、`121,511 / 5,786`；Bulletin GEM 原文一字不差就是这六个数。

### 闭合 ②　主板 + GEM ≡ 仓里已有的 `adt_hkdbn`（2026-06）

```
主板日均成交额 318.986 HK$bn
GEM 日均成交额   0.090 HK$bn
                ───────────
合计            319.076 HK$bn
series/hkex.csv 2026-06 的 adt_hkdbn = 319.076   ← 逐位相同
```

### 闭合 ③　把 ② 推广到全序列：90 / 90 全中

这一条是我加做的，也是整份核查里分量最重的一条：
`series/hkex.csv` 里有 `adt_hkdbn` 的月份共 **90 个（2019-01 ~ 2026-06）**，
我用 B1 逐日档案（主板+GEM）逐月重算日均成交额，与仓里的值在 **3 位小数上逐位相同，90/90，零例外**。

最早那个月的完整算式（2019-01，22 个交易日）：

```
主板  1,938,184,872,026 HKD / 22 =  88.099 HK$bn      GEM  6,048,135,137 / 22 = 0.275 HK$bn
合计 88.099 + 0.275 = 88.374  =  series/hkex.csv 2019-01 的 adt_hkdbn 88.374   ← 逐位相同
```

⇒ 新列与既有金额列**不是"口径相近"，是同一套逐日底稿的不同列**。这也是"不一致就不要合成"
这条要求的答案：一致，可以合成。

### 闭合 ③ 的副产品：半日市**按整天算**

含半日市的月份（2025-01 有 01/28、2024-02 有 02/09、2021-02 有 02/11 …）
如果把打星的那天按 0.5 天折算，日均就对不上官方数了；按整天算才 90/90 全中。
所以**这是实测反推出来的事实，不是假设**：HKEX 自己的日均分母就是把半日市算一整天。
本模块因此也不折算。

---

## 发布节奏与滞后（实测 Last-Modified，GMT）

| 文件 | Last-Modified | 覆盖到 |
|---|---|---|
| `rpt_Stock_market_highlights_2606.json` | Thu, 02 Jul 2026 14:02:45 | 2026-06 |
| `rpt_data_statistics_archive_trading_data_2025_2029.json` | Thu, 02 Jul 2026 14:59:37 | 2026/06/30 |
| `rpt_data_statistics_archive_trading_data_gem_2024_2028.json` | Thu, 02 Jul 2026 14:59:36 | 2026/06/30 |
| `rpt_Stock_market_highlights_2607.json` | Mon, 03 Aug 2026 14:04:32 | 2026-07 |
| （对照）链路 A 的 Monthly Highlights xlsx，2026-06 档 | Tue, 07 Jul 2026 | 2026-06 |

两条结论：

1. **Monthly Bulletin 比本仓原有的 xlsx 还早 ~5 天**（07-02 vs 07-07）。
2. **逐日档案会掉队。** 到本核查日 2026-08-07，2607 的 Bulletin 已经上线 4 天，
   而逐日档案仍停在 `2026/06/30`。我带 `Cache-Control: no-cache` + 随机 query 重取过，
   返回同一个 `last-modified: Thu, 02 Jul 2026 14:59:37` 与同样 365 行 —— **不是 CDN 缓存，是真没更新**。
   ⇒ 最新月必须留 Bulletin 兜底，否则这两列会比 `adt_hkdbn` 晚整整一个月。

> HEAD 请求不可用：`www.hkex.com.hk` 对 `HEAD` 一律回 **503**（content-length 282）。
> 探新鲜度只能用 `GET` + `Range: bytes=0-0`，或者直接 GET 全文。

---

## 入库的列（`series/hkex.csv` 末尾追加 7 列）

| 列名 | 口径 | 单位 | 来源栏目原文 |
|---|---|---|---|
| `trading_days_cash` | 现货交易日数，**主板日历**，半日市算整天 | 天 | 逐日档案行数 |
| `vol_shares_mb_mn` | 当月成交股数合计 · **主板** | 百万股 | `Turnover volume (mil shares)` |
| `vol_shares_gem_mn` | 当月成交股数合计 · **GEM** | 百万股 | 同上（GEM 分册） |
| `trades_mb_total` | 当月成交笔数合计 · **主板** | 笔 | `No. of deals` |
| `trades_gem_total` | 当月成交笔数合计 · **GEM** | 笔 | 同上（GEM 分册） |
| `adv_shares_mn` | 日均成交股数 · **主板+GEM** | 百万股 | `Turnover volume (mil shares) - Daily average` |
| `adt_trades` | 日均成交笔数 · **主板+GEM** | 笔 | `No. of deals - Daily average` |

命名跟仓里既有构词法：`vol_*` = 期内总量（jpx `vol_cash_dom_shares_mn`）、
`adv_*` = 日均量（jpx `adv_cash_dom_shares_mn`）、`adt_*_trades` = 日均笔数（asx `adt_cash_trades`）、
`trades_*_total` = 期内笔数（asx `trades_cash_total`）、`trading_days_cash`（asx 同名）。
HKEX 原文说 deals，仓里的通用词是 trades，列名从仓、口径注从源。

**可用起止月：2019-01 ~ 2026-07，91 个月，零断档。**
（2019-01 ~ 2026-06 来自 B1 逐日档案；2026-07 来自 B2 Bulletin，档案尚未覆盖。）

### 三条不能动的规矩

1. **忠实入库，不做换算。** 逐日 → 逐月只做**求和与计数**；
   股→百万股是**换单位刻度**（与既有列把 HK$mil ÷1000 存成 HK$bn 同类），不换口径、不引外部参数。
   日均那两列不是本模块算出来的口径，是官方 `- Daily average` 这一行**自己就印的数**
   （闭合 ① 已证明档案汇总 ÷ 交易日 = 官方印的日均，逐位相同）。
   FX、定基名义额、速率之类一概不在 fetch 层做。
2. **不新增早于序列首月的行。** 逐日档案能回到 1986/1999，但往前加行会改变
   `build/hkex.py` 里 `df.index[0]` 与全部窗口函数的输入，那不归 fetch 层决定。
   本次只给 `series/hkex.csv` 已有的 91 行补格。真要往前铺，改法是放宽
   `_trading_stats` 的 `since_year` 并允许 append —— 但要连带确认 build 侧图注与窗口，属人工决策。
3. **档案的最后一个月必须过 Bulletin 确认才收。** 逐日档案自己不声明"这个月发完了没有"，
   一份月中快照看上去和整月合计一模一样。所以代码里 `_confirm_with_bulletin()` 拿同月
   Bulletin 的 6 项（两板 × 当月合计股数/笔数 + 主板日均股数/笔数）逐位对，
   容差 ±1 个末位；对不上就整月不写并打印原因。本轮运行输出：

   ```
   [hkex] 逐日档案最新月 2026-06：Monthly Bulletin 2026-06 逐位确认（6 项，容差 ±1 个末位）
   [hkex] 2026-07 逐日档案尚未覆盖，改用 Monthly Bulletin 当月合计
   ```

---

## 用这两列能算什么

成交额恒等式的三段分解（这是加这两列的全部意义）：

```
成交额  ≡  笔数  ×  每笔股数  ×  每股单价
        adt_trades   adv_shares_mn/adt_trades   adt_hkdbn/adv_shares_mn
```

三段各自对应一个完全不同的机制，混在 ADT 一个数里看不出来：
**笔数**≈参与度/拆单密度（也直接对应交易与结算的**按笔计费**基数），
**每笔股数**≈单笔规模与算法拆单，**单价**≈价格水平与低价股结构。

本仓实测（TTM 2025-07~2026-06 vs 2024-07~2025-06，主板+GEM，按交易日加权）：

| 分段 | 上一期 | 本期 | 变化 |
|---|---|---|---|
| 笔数（笔） | 723,828,100 | 1,024,159,921 | **+41.5%** |
| 每笔股数（股/笔） | 91,255.4 | 80,489.2 | **−11.8%** |
| 每股单价（HK$/股） | 0.7251 | 0.8044 | **+10.9%** |
| 成交额（HK$bn） | 47,897 | 66,313 | **+38.4%** |

恒等式闭合：`1.4150 × 0.8820 × 1.1094 = 1.38448912`，成交额比值 `66,313/47,897 = 1.38448912`，
到小数点后 8 位相同。

---

## 已知的、写在这里免得下一个人重踩

1. `www.hkex.com.hk` 与链路 A 的 `www.hkexgroup.com` 是**两个站**，
   一个挂 Monthly Bulletin，一个挂 Monthly Market Highlights xlsx。两边内容不重叠。
2. Bulletin 只留 13 个月，所以 2025-06 以前的月份**没有第二个官方口径可以逐位对**，
   只能靠闭合 ③（重现 `adt_hkdbn`）背书。这条背书本身很强（90/90），但要知道它是间接的。
3. 2026-07 这一行的 7 个值来自 Bulletin 的整数印刷值。等逐日档案补上 2026-07 之后，
   `adv_shares_mn` 可能在**末位差 1**（Bulletin 先四舍五入到整数百万股再相加，档案是先加再舍）。
   `_materially_differs` 对 0 位小数列的阈值就是 1 个末位，所以这种差**既不会被记成重述、
   也不会被覆盖**，序列稳定。
4. GEM 的交易日历与主板相同：2019-01~2026-06 共 90 个月，两边逐日行数**一次都没差过**。
   代码里仍留了警告分支（真差了就打印并以主板为准），因为 GEM 只占成交额的 ~0.03%，
   用主板日历不会改变任何结论。
