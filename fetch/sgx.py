# -*- coding: utf-8 -*-
"""Singapore Exchange (SGX) 月度市场统计 —— 无人值守抓取。

━━ 数据源 ━━
三步发现链，全程 plain urllib，无浏览器、无登录态、无 Cloudflare/PerimeterX：

  ① GET https://www.sgx.com/config/appconfig.json
     → {"CMS_VERSION": "<40 位 hash>", ...}   实测 200 / 4,999 bytes
  ② GET https://api2.sgx.com/content-api/
          ?queryId=<CMS_VERSION>:market_statistics_reports_list
          &variables={"lang":"EN","limit":1000}
     → JSON，data.list.count = 197，每期一条 {title, reportDate, report.data.{name,date,file.data.url}}
       实测 200 / 82,363 bytes。**这一步同时就是「官方当前最新月」的答案**
       （数组第 0 条的 title），所以 latest_month() 只花这两个请求、不下 PDF。
  ③ GET 上一步给出的 file.url（api2.sgx.com/sites/default/files/YYYY-MM/*.pdf）
     → 48 页 PDF，带 HTTP Last-Modified。

**为什么必须走 ② 拿 URL，不能按模板拼 PDF 直链**：同一份东西官方用过至少四种命名 ——
  `SGX Monthly Market Statistics Report - Feb 2010.pdf`
  `SGX+Monthly+Market+Statistics+Report+Jun+2018.pdf`
  `SGX Monthly Statistics Report Update (For the month of Apr 2026)_FA.pdf`
  `SGX MONTHLY STATISTICS UPDATE (FOR THE MONTH OF JUN 2026)_260703_FA.pdf`
最后这个文件名里的 `260703` 与真实上线日 07-10 差 7 天，目录段 `YYYY-MM/` 也不总等于次月。
**别从文件名或路径解析任何日期**：月份一律取 CMS 的 title，发布日一律取 HTTP Last-Modified。

顺带澄清一条会误导后人的传闻：`api.sgx.com/announcements/v1.1/*`（SGXNet 公告，本模块**不用**）
不带 token 返回 **HTTP 401**、带 `authorizationToken` 返回 **200**，就是普通 token 鉴权。
plain curl 全程可用，不需要 curl_cffi、不需要 nscurl。本模块压根不碰这个端点 ——
新闻稿广播日比网站上线晚 1~3 天，而本仓 source_dates 的语义是「数据第一次可得那天」。

━━ 发布节奏 ━━
次月上旬，中位数第 9 天。把 197 期里**发布日可信的 95 个月**（2018-08 之后，见口径坑 3）
按「次月第 N 天」统计：

    第 6 天  5 次 | 第 7 天  6 次 | 第 8 天 10 次 | 第 9 天 21 次 | 第 10 天 18 次
    第 11 天 10 次 | 第 12 天  8 次 | 第 13 天  7 次 | 更晚 10 次（最晚 2020-10 拖到次年 01-22，第 83 天）

⇒ `build/roster.py` 的 LAG 填 **(13, 13)**（红点上界；SGX 月报不随季报节奏走，
   财年 6 月末那期照常在 7 月上旬发，实测 2025-06→07-09、2026-06→07-10）。
⇒ `monthly_run.EARLY_BY['sgx']` 必须填 **(7, 7)**，不能吃默认的 EARLY=5。
   理由：默认闸门 = LAG-5 = 第 8 天，而最近 35 个月里有 **8 个月（23%）在第 6~7 天就发了**
   （2024-04/05/07/10/11、2025-02/03/05）—— 那 8 次公开页面会挂 1~2 天陈旧数据，
   正是 README 说的「闸门晚开一天」的代价。改成 EARLY=7 后闸门落在第 6 天，无一迟到，
   代价只是每月多几个「还没发」的空请求。

━━ 口径坑（按踩坑概率排序）━━
1. **PDF 文字层里，章节标题排在它自己的表格「后面」，而且同一份文档两种顺序混用。**
   实测 2026-06 那期：p20/p21/p27/p29 是标题在前，p22~p26/p30~p38/p39~p40 是标题在后 ——
   crypto 的 `Total 337,175` 先吐出来，然后才吐 `Cryptocurrency Derivatives Volume`，
   接着 SICOM 的 Total，再吐 `SICOM Volume`。
   任何「找到标题→读下面的行」的解析器都会把每一个 Total 静默错配一个小节，
   而商品档有 **6 行都叫 Total**，错位之后数字依然「像模像样」。
   ⇒ 本模块**不按阅读顺序解析，按 y 坐标重排**（_page_lines 的 sort）。标题在版面上永远
     在自己表格的上方，重排后「标题在前」就恒成立，这个坑从根上消失。
2. **同名产品在两个小节里数字不同 —— GIFT Nifty。**
   `Equity Index Futures Volume` 里的 `GIFT Nifty 50 Index Futures` 是 SGX-ICI 成交、
   SGX 自己清算的量（FY2026 = 20,699,069）；`GIFT Nifty Futures Volume` 那一节同名行
   是 NSE-IX 整个市场的量（FY2026 = 24,357,137），差 18%，后者不全归 SGX。
   ⇒ 查行**必须先定位 section**，绝不能全表 grep 产品名。本模块所有取数都带 section 白名单。
3. **HTTP Last-Modified 只对 2018-08 及之后的数据月可信。**
   2018-07 及更早的约 102 期返回的都是 2018 年站点迁移的时间戳
   （实测 2010-02 / 2012-06 / 2015-01 / 2016-06 四期全返回 2018-08-21，2017-06 返回 2018-08-14，
   2018-06 返回 2018-08-08），而 2018-12→2019-01-09、2019-06→2019-07-09、2026-06→2026-07-10
   都是真发布日。无条件拿它回填会写出一百多条假 source_date，且**假日期看上去完全正常**。
   ⇒ 见 _LASTMOD_TRUSTED_FROM：早于该月的一律不记 source_dates（宁缺勿错）。
4. **CMS 的 `title` 不是统一格式，`%B %Y` 会静默丢掉 92 期。**
   197 条里 92 条用缩写月（`Jun 2018`，2018-06 及更早全是），另有 `' Jan 2015'`（前导空格）、
   `'Feb 2017\t'` / `'Aug 2016\t'` / `'Feb 2014\t'`（尾部 tab）、`'Feb  2011'`（双空格）。
   而 `count` 仍报 197，丢了也不报错。⇒ strip + 折叠空白 + `%B %Y` 与 `%b %Y` 都试，
   解析完断言条数与 count 相等。
5. **`CMS_VERSION` 会随站点发版轮换，且失效时返回 HTTP 200 + `{"errors":[...]}`，不是 4xx。**
   更阴的是：**名字完全合法的 query 也会瞬时这样失败**（本模块开发时实测：同一个
   `we_chat_qr_validator` 第一次 200+errors、立刻重试就正常）。
   ⇒ 每次运行都重读 appconfig.json（写死 hash = 某天开始静默返回空列表，
     而 latest_month() 会以为「官方还没发」）；且必须显式检查 `errors` 键 + 带退避重试。
   另：`variables` 不写 `limit` 时默认只回 10 条，而 `count` 照样是 197。
6. **`Derivatives Volume ÷ Number of Trading Days ≠ Derivatives Daily Average Volume`。**
   实测 2026-06：34,315,225 / 21 = 1,634,058，而官方 DDAV 是 1,619,444（隐含 21.19 天）。
   `Number of Trading Days` 那行括号里写着 `(Stock Market)` / `(Securities)` ——
   它是**证券市场**的交易日数，衍生品的假期表与夜盘归属日都不一样。
   ⇒ 月总量与日均**两个都入库**，谁也不许从谁反推。
   （反过来，证券侧是自洽的：44,639/21 = 2,126 = SDAV，本模块拿它当解析自检，见 _crosscheck。）
7. **官方的 `YoY%` 列会算错。** 实证：2025-06 期 p38 `Fund Raised ($ million)` 行
   Jun 2025 = 15,362、Jun 2024 = 20,306，官方印的是 **-4944%**（正确是 -24%）；
   同页上一行 New Bond Listings 的 -50% 又是对的。⇒ 一概不入库 YoY / FYTD / CYTD 列。
8. **重述标记 `(#)` 既污染数值也污染表头。** 2013-06 那期有 13 处，既有 `62,084(#)`
   这样的数值，也有 `May 2013(#)` 这样的**表头单元格**。
   ⇒ _norm() 在任何解析动作之前先剥 `(#)`，否则那几期认不出列、也读不出数。
9. **证券成交额是暂定数，官方明说会跨月顺延调整**（p3 脚注：月末附近的撤销交易可能来不及
   计入，调整后的数字并进下个月那期）。⇒ 照 cboe / hkex 的做法：**已有值永不覆盖，只填空**。
10. **跨世代改名 + 结构性断点，画图时要打断点线：**
    · `Nifty 50` →（2023-07 GIFT Connect 迁移）`GIFT Nifty 50`。官方脚注写明 2023-06 之前
      按买卖腿取大者计量、之后改成买卖双边合计 —— **这是量纲变化不是增长**，2023-06/07 之间
      必须打结构性断点。2016 那代还叫 `SGX Nifty 50 Index Futures`。
    · 台湾指数期货换过指数供应商：`MSCI Taiwan Index Futures` → `FTSE Taiwan Index Futures`，
      **是两个不同合约，不是改名**，所以本模块拆成两列各存各的，绝不接成一条线。
    · `Iron Ore 62% Futures` → `SGX IODEX Iron Ore Futures`；
      `Iron Ore Options On Futures` → `SGX Options On IODEX Iron Ore Futures`。
    · `INR_USD FX FFutures`（2016 年那代的拼写错误，两个 F）→ `INR_USD FX Futures`。
    · At-A-Glance 行名改过两轮：`(Securities)` → `(Stock Market)`、
      `Securities Market Turnover Value` → `Stock Market Turnover Value`，
      还夹着 `Securities market Turnover Value`（market 小写）与 `($million)` / `($Million)`。
    ⇒ 行标签一律 casefold + 剥脚注后按**别名表**匹配，绝不按位置数行。
11. **列数随年份与页面变**（现代主表 9 列、GIFT 全市场 7 列、月末 OI 5 列、
    Issuer Services 6 列、At-A-Glance 2 列），且 2022 那几期有单元格与行标签**粘在同一行**
    （`FM Cobalt ... Futures 0`），按位置数列必错位。
    ⇒ 本模块**不数列**：表头单元格与数值单元格都取 x 坐标，数值按 x 就近归到表头列，
      归不上的留空。列数怎么变都不影响。
12. **「Commodities」的官方定义不含 crypto。** 2026-07-13 新闻稿说 FY2026 商品总量 78.8M lots；
    SICOM 3,895,114 + Energy 493,152 + Metal&DryBulk 73,586,973 + Dairy 期货 688,923 +
    Dairy 期权 104,742 + Energy Metals 2,640 = **78,771,544** ✅；加上 Crypto 的 337,175
    就变成 79,108,719，对不上。⇒ vol_commodities_contracts 按前者，crypto 单开一列。
13. **Issuer Services 那页的文字层是列优先**（先连着吐 5 个标签，再每列吐 5 个数）。
    按阅读顺序解析必错；按 y 坐标聚行则完全无感 —— 本模块用后者，所以这页不需要特判。
14. **官方会漏印某一行的行标签，导致该行往下「标签相对数字整体上移一格」。**
    实测 2020-03 期 p15 外汇期货表：`Total` 这个标签落在了 USD_SGD 那行的数字上
    （Mar-2020 = 26,604），真正的合计 2,972,857 变成「有数字没标签」的孤儿行。
    用 2020-04 期的 Mar-2020 列可以逐位证实（USD_SGD = 26,604、Total = 2,972,857）。
    错位后的值本身完全合法，**按标签取数会把外汇期货合计写小 112 倍且不报错**。
    ⇒ 取任何小节合计都过 _total_is_shifted：合计小于同块任一分项即判定错位、返回 None，
      再由 _fill_from_next 用下一期报告补回。全 138 期只有这一处命中，零误杀。
      （全书扫描确认：其余「无标签数值行」都落在 Turnover Velocity / CDP SBL /
      债券占比这些**本模块根本不取数**的图表小节里，不影响入库字段。）
    ⚠ **补充（2026-08-07 全缓存重扫发现）：这次错位不只咬到 Total，还咬到了 USD_CNH。**
      2020-03 期缺的那个标签在 `TWD_USD FX Futures` 处 —— 官方那期把
      `TWD_USD (Full-Sized)` / `TWD_USD (Mini)` 两行并成了一个标签，于是从那里往下
      每个标签都比自己的数字**低一行**：
        2020-03 期印的                     2020-04 期印的（标签正确）
        `USD_CNH FX Futures`      1,990    `TWD_USD (Mini) FX Futures`   1,990
        `USD_CNH FlexC FX Futures` 1,255,507 `USD_CNH FX Futures`      1,255,507
        `Total`                   26,604   `USD_SGD FX Futures`         26,604
        （无标签孤儿行）        2,972,857   `Total`                   2,972,857
      `vol_usdcnh_futures_contracts` 因此被写小 **631 倍**（1,255,507 → 1,990），
      而 1,990 本身是个完全合法的月度张数，_total_is_shifted 也管不到它（它不是合计）。
      两道新护栏都能抓住它：量级判据（见 _scale_typo_guard）与上月列交叉校验
      （见 _crosscheck_prev_month —— 2020-04 期印的 Mar-2020 列是 1,255,507）。
      已确证的更正进 _ERRATA。
15. **官方会把千分位逗号排版成小数点，数值当场缩小 1000 倍且完全合法。**
    实测 2020-01 期 p2 At-A-Glance：`Total Market Capitalisation ($Million)` 那行印的是
    `937,830 | 923.134` —— 真值 923,134，逗号被排成了点。2020-02 期的上月列**照抄同一处错印**
    （`923.134 | 899,575`），所以这一处**指望不上 _fill_from_next**：下一期给的是同一个错值。
    同类错印全书共两处命中入库字段，另一处是 2016-07 期 p38 债券募资
    （`Fund Raised ($ million)` 的 Jul 2016 列印成 `18.995`，真值 18,995 ——
    同一行的 FYTD 2017 列印的就是 `18,995`，且 2016-08 / 2016-09 两期的 Jul 2016 列也都是
    `18,995`，三处独立互证）。
    错印后的 923.134 / 18.995 本身是完全合法的数，`_num()` 静默 float 解析，
    写进 CSV 后只是「这个月市值突然只有 923 百万」—— 图上是一根扎到底的针，没有任何异常。
    ⇒ 见 _cell_num：小数点右边**正好一个三位组**、且整数部分本身就是合法千分位分组时，
      判定为错印的逗号，按去掉分隔符的整数入库，并打 stderr 警告（不静默）。
      判据之所以够窄：全书三处**真小数**没有一处符合这个形状 ——
      2020-09 期 p10 分国别市值 `354.7167965`（7 位小数）、2021-09 期 CDP SBL
      `59,557,635.87`（2 位）、2018-08 期债券 YoY `-31.4%`（带 % 号天然免疫）。
      另有 _validate 自检 5 兜底：入库字段一律必须是整数，换个形状的错印会当场炸掉。
16. **同样「小三个数量级」的错也可以由标签错行造成，那时 token 完全正常。**
    _cell_num 认的是 token 形状，形状正常它就无话可说 —— 2020-03 期把 USD_CNH
    写成 `1,990`（真值 1,255,507，口径坑 14 的补充）正是这样，静默写小 631 倍。
    ⇒ 见 _validate 自检 6 / _scale_typo_guard：与上月比出现 ~1000 倍跳变即
      **拒绝入库并点名**，绝不自动修正（形状不能唯一确定读法时就没有资格猜，
      理由与两种处置的分界线写在该函数里）。人工核实后进 _ERRATA 显式更正表。
17. **每期都印「上月」列，这是白送的、覆盖全部 32 列的交叉校验，必须每次抓取都核。**
    第 M 期的 M-1 列理应等于第 M-1 期的 M0 列。全 138 期实测 78 处不等：
    绝大多数是官方顺延调整（口径坑 9），但真问题也全被它第一时间抓住 ——
    2016-07 的千分位错印、2020-03 的标签错行、2021-01 期 p14/p15
    **表头没跟着数据一起更新**（数据已是 11/12/1 月，表头还写着 Oct/Nov/Dec 2020）。
    ⇒ 见 _crosscheck_prev_month：照 fetch/spgi.py 的既有做法**只告警、不拒绝、不覆盖**
      （官方重述是合法行为，改写历史必须人工决定），但任何不等都点名到具体格子。
18. **换手率有两处官方来源，早年只有其中一处 —— 只认 p2 会白丢 38 个月历史。**
    p2 的 At-A-Glance 从 **2018-03** 那期起才多出 `Overall Turnover Velocity` 这一行；
    在此之前这份文档**照样印换手率**，只是印在 p8 的 `Turnover Velocity (5)` 表里
    （首行 `SGX Overall`，与 Mainboard / Catalist 两行同表，带 M-2 / M-1 / M0 三个月度列）。
    本模块 2026-08 之前只读 p2，于是 2015-01~2018-02 那 38 个月的这一列一直是空的，
    而**空得毫无痕迹** —— FIRST_MONTH 里写着「2018-03 才开始有」，缺列护栏因此放行。
    ⇒ 两处**逐格等价**，已闭合验证：2018-03 期 p2 印 Feb 55% / Mar 43%，同期 p8 的
      `SGX Overall` 印 Jan 41% / Feb 55% / Mar 43%，两页同月逐格相同；跨 vintage 也相同
      （2018-01 期 p8 给的 Jan 2018 = 41%、2018-02 期给的 Feb 2018 = 55%，与 2018-03 期
      p2 的同月值一致）。所以往回读 38 个月**不产生接缝**，不必画断点。
    ⇒ 处置：p2 取不到时回落到 p8（见 parse_report 的 velocity 那一格）。
      **顺序不能反** —— 2018-03 起两处等价，继续优先 p2 就保证既有入库值一格不动。
    ⚠ 脚注措辞在 2018-03 换过一次（旧：`(5) Includes Ordinary Shares, Investment Funds,
      SDR, Stapled Securities and Unit Trusts.`；新：`(5) Turnover velocity calculated
      based on primary listed securities for both market capitalisation and turnover
      value.`），但两个 vintage 在接缝上给同一个数，是措辞细化不是口径换代。
    ⚠ p8 那张表最右边那列是**去年同月**，官方偶尔会在那一列上印一个与当年 M0 列差 1pp
      的数（38 个月里 3 处：Feb-2015 39 vs 40、Aug-2015 57 vs 58、Sep-2015 44 vs 45）。
      本模块一律只取 M0 列（_row_value 的既有约定），那三处与入库值无关。

━━ series/sgx.csv 每一列的确切口径 ━━
月份 `month` = **数据月**（YYYY-MM），不是发布月。所有「本月」值取该期报告里表头等于数据月
的那一列（M0 列），FYTD / CYTD / 上年同月 / YoY% 一概不取。
**币种一律新元 S$**（SGX 报告里的 `$` 就是 S$，见报告封底与新闻稿 "S$44.6 billion" 对照）。
**张数一律「张」原值，不是千张** —— 官方就是这么印的，本模块不做任何换算
（定基名义额的换算是 build/notional.py 那层的事）。
计数口径：SGX 的成交量是**单边**（一手买+一手卖记 1 张），与 CME/HKEX 惯例一致；
唯一例外是 Nifty，2023-06 及之前那段按买卖腿取大者、之后改双边合计（见口径坑 10）。

| 列名 | 口径 |
|---|---|
| `sec_trading_days`                  | 当月**证券市场**交易日数（整数）。衍生品市场不是这个数，见口径坑 6 |
| `sec_turnover_mnshares`             | 当月证券市场成交**股数**，百万股，月总量。含 Mainboard(S$/非S$)、Catalist、Global Quote、ETF、结构化权证、DLC、公司权证 |
| `sec_turnover_sgdmn`                | 当月证券市场成交**金额**，S$ 百万，月总量。**暂定数，会跨月顺延调整**（口径坑 9） |
| `sdav_sgdmn`                        | Securities Daily Average：当月证券成交金额的**日均**，S$ 百万/日。SGX 财报与新闻稿引用最多的单一数字（= sec_turnover_sgdmn / sec_trading_days） |
| `listed_securities`                 | **月末**上市证券只数（**存量**）。官方脚注：不含 GDR、对冲基金、债券 |
| `mktcap_sgdmn`                      | **月末**总市值，S$ 百万（**存量**，原表就是 $Million，未做任何缩放） |
| `turnover_velocity_pct`             | Overall Turnover Velocity（年化换手率），百分数去掉 % 号后的数值（49% → 49）。**两处等价来源**，见口径坑 18 |
| `deriv_vol_contracts`               | 当月衍生品成交**总张数**（期货+期权+掉期），月总量，张 |
| `ddav_contracts`                    | Derivatives Daily Average Volume：衍生品**日均**成交，张/日。**这是与 CME/Cboe/HKEX 跨家可比的那个字段**（HKEX 的 derivatives_adv_contracts 同为张/日，可直接同轴） |
| `deriv_futures_vol_contracts`       | 当月期货成交，张，月总量 |
| `deriv_options_vol_contracts`       | 当月期权成交，张，月总量 |
| `deriv_swaps_vol_contracts`         | 当月掉期成交，张，月总量。2018 及之前官方叫 "Total AsiaClear Cleared Swaps Volume"，同一格 |
| `deriv_oi_contracts`                | **月末**总未平仓（期货+期权+掉期），张（**存量**，不是流量） |
| `vol_equity_index_futures_contracts`| 股指期货合计（`Equity Index Futures Volume` 小节的 Total），张，月总量 |
| `vol_a50_futures_contracts`         | FTSE China A50 Index Futures，张，月总量。SGX 头号单品 |
| `vol_nikkei225_futures_contracts`   | Nikkei 225 Index Futures（**不含** Mini / USD / Micro / TR / ESG-REIT，它们各自单列），张，月总量 |
| `vol_nifty50_futures_contracts`     | Nifty 50 指数期货，**SGX-ICI 成交并由 SGX 清算**的口径（≠ NSE-IX 全市场，见口径坑 2），张，月总量。跨 2023-06/07 有量纲断点（口径坑 10） |
| `vol_msci_singapore_futures_contracts` | MSCI Singapore Index Futures，张，月总量 |
| `vol_msci_taiwan_futures_contracts` | MSCI Taiwan Index Futures，张，月总量。**2020 年底停用**，之后为空 —— 与下一列是两个不同合约，不可接成一条线 |
| `vol_ftse_taiwan_futures_contracts` | FTSE Taiwan Index Futures，张，月总量。2020 年才上线，之前为空 |
| `vol_fx_futures_contracts`          | 外汇**期货**合计（`Foreign Exchange Futures Volume` 小节的 Total），张，月总量。**不含 FX 期权** |
| `vol_usdcnh_futures_contracts`      | USD_CNH FX Futures（标准合约，**不含** Mini / FlexC），张，月总量 |
| `vol_inrusd_futures_contracts`      | INR_USD FX Futures（**不含** FlexC；2016 那代官方拼成 `INR_USD FX FFutures`），张，月总量 |
| `vol_rates_futures_contracts`       | 利率期货合计（`Interest Rates Futures Volume` 小节的 Total），张，月总量。量级很小 |
| `vol_iron_ore_contracts`            | 铁矿石衍生品合计，张，月总量 = **所有成交量小节里行名含 "Iron Ore" 的行之和**（62%/65%/58%/IODEX/Lump Premium，期货+期权+掉期，含 OTC 清算腿）。跨世代都成立：2016-01 期算出的 Dec-2015 = **988,532**，与 SGX 自己的新闻稿 "Iron Ore Derivatives volume was 988,532" 逐位相同 |
| `vol_commodities_contracts`         | 商品合计，张，月总量 = 商品类成交量小节的 Total 之和（现代：SICOM+Energy+Metal&DryBulk+Dairy期货+Dairy期权+EnergyMetals；2018 之前：Agri-Commodities+Energy+AsiaClear 三节）。**不含 crypto**（口径坑 12） |
| `vol_crypto_contracts`              | Bitcoin / Ethereum Perpetual Futures 合计，张，月总量。**2025-11 才上线**，之前官方没有这一节 |
| `ipos_count`                        | 当月新上市**家数** = Mainboard IPOs + Catalist IPOs（**不含** RTO，RTO 官方单列一行） |
| `delistings_count`                  | 当月退市**家数** = Mainboard + Catalist |
| `ipo_funds_sgdmn`                   | 当月 IPO 与 RTO 募资额，S$ 百万 = Mainboard + Catalist。官方脚注：不含超额配售权（若行使） |
| `new_bond_listings`                 | 当月新债券挂牌**只数** |
| `bond_funds_sgdmn`                  | 当月债券募资额，S$ 百万 |

不入库的：官方 YoY% 列（会算错，口径坑 7）、FYTD / CYTD 列（SGX 财年是 7 月—6 月，
与看板的日历年逻辑打架；真要年度数就从月度序列自己滚）。

━━ 历史起点 ━━
CMS 列表覆盖 2010-02 ~ 2026-06 共 197 期、**零断档**，但本模块只从 **2015-01** 起：
2010-02~2010-11 是 Excel 打印稿、文字层行列关系全靠坐标碎片；2011~2014 表头位置不稳。
2015-01 起 At-A-Glance 与分产品表全部稳定可解析（实测 138 期全通）。

━━ 依赖 ━━ pymupdf（fitz）。不依赖 pandas / curl_cffi / nscurl。
"""

import csv
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

APPCONFIG_URL = 'https://www.sgx.com/config/appconfig.json'
CONTENT_API_FALLBACK = 'https://api2.sgx.com/content-api'
LIST_QUERY = 'market_statistics_reports_list'

START_MONTH = '2015-01'

# HTTP Last-Modified 从哪个**数据月**起可信，见口径坑 3。
# 2018-07 及更早的那批返回的是 2018-08-08 ~ 2018-08-21 的站点迁移戳。
_LASTMOD_TRUSTED_FROM = '2018-08'

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')


class SgxFetchError(RuntimeError):
    """源站结构变化 / 下载失败 / 解析结果不完整。一律炸掉，绝不静默写 NaN。"""


# ══ 网络 ═════════════════════════════════════════════════════════════════
def _http_get(url, timeout=90):
    """返回 (bytes, headers)。失败抛 SgxFetchError。"""
    req = urllib.request.Request(url, headers={
        'User-Agent': _UA,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), dict(r.headers)
    except Exception as e:                                # noqa: BLE001
        raise SgxFetchError('下载失败 %s: %r' % (url, e)) from e


def _cms_config(cache_dir):
    """每次运行都重读 appconfig.json，拿当前 CMS_VERSION 与 content-api 地址。

    绝不缓存/写死 hash：它随站点每次发版轮换，而失效时服务端回的是
    HTTP 200 + {"errors":[...]}（见口径坑 5）—— 写死的后果不是报错，
    是某天开始静默返回空列表，latest_month() 以为「官方还没发」，看板悄悄停更。
    """
    raw, _h = _http_get(APPCONFIG_URL, timeout=30)
    os.makedirs(cache_dir, exist_ok=True)
    with open(os.path.join(cache_dir, 'sgx_appconfig.json'), 'wb') as f:
        f.write(raw)                                      # 改版时可事后取证
    try:
        cfg = json.loads(raw)
    except ValueError as e:
        raise SgxFetchError('appconfig.json 不是合法 JSON：%r' % (raw[:200],)) from e
    ver = cfg.get('CMS_VERSION')
    if not (isinstance(ver, str) and re.fullmatch(r'[0-9a-f]{40}', ver)):
        raise SgxFetchError('appconfig.json 里的 CMS_VERSION 形状不对：%r' % (ver,))
    api = (cfg.get('endpoints') or {}).get('CMS_API_URL') or CONTENT_API_FALLBACK
    return ver, api.rstrip('/')


def _graphql(api, ver, query, variables, attempts=4):
    """带退避重试的 persisted query。

    为什么必须重试：这个端点对**名字完全合法**的 query 也会瞬时返回
    HTTP 200 + {"errors":[{"message":"The persisted query loader must return
    query string ... but got: null."}]}（开发时实测：同一个查询第一次这样、
    立刻重试就正常）。不重试的话，一次网络抖动会被当成「官方还没发这个月」
    而静默跳过一整月 —— 没有任何异常，红点也要等到超期才亮。
    """
    url = '%s/?%s' % (api, urllib.parse.urlencode({
        'queryId': '%s:%s' % (ver, query),
        'variables': json.dumps(variables, separators=(',', ':')),
    }))
    last = None
    for i in range(attempts):
        raw, _h = _http_get(url, timeout=60)
        try:
            doc = json.loads(raw)
        except ValueError:
            last = '返回的不是 JSON：%r' % (raw[:200],)
        else:
            if doc.get('errors'):
                last = 'HTTP 200 但带 errors：%r' % (doc['errors'],)
            elif not doc.get('data'):
                last = 'HTTP 200 但没有 data 键：%r' % (list(doc),)
            else:
                return doc['data']
        time.sleep(1.5 * (2 ** i))
    raise SgxFetchError('%s 连续 %d 次失败：%s' % (query, attempts, last))


_TITLE_MONTH_FMTS = ('%B %Y', '%b %Y')


def _title_month(title):
    """CMS title -> 'YYYY-MM'；认不出返回 None。

    197 条里 92 条是缩写月，还有前导空格 / 尾部 tab / 双空格（见口径坑 4）。
    只写 strptime(title, '%B %Y') 会静默丢掉 92 期，而 count 照样报 197。
    """
    s = re.sub(r'\s+', ' ', (title or '')).strip()
    for fmt in _TITLE_MONTH_FMTS:
        try:
            d = datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue
        return '%04d-%02d' % (d.year, d.month)
    return None


def _report_index(cache_dir):
    """{'YYYY-MM': {'url','name'}}，覆盖官方列出的全部期数（实测 197 期，零断档）。"""
    ver, api = _cms_config(cache_dir)
    data = _graphql(api, ver, LIST_QUERY, {'lang': 'EN', 'limit': 1000})
    lst = data.get('list') or {}
    results = lst.get('results')
    count = lst.get('count')
    if not isinstance(results, list) or not results:
        raise SgxFetchError('%s 返回里没有 list.results：%r' % (LIST_QUERY, list(data)))
    # limit 不生效时只会回 10 条，而 count 照样是 197 —— 不断言就静默少 187 期
    if count is not None and len(results) != count:
        raise SgxFetchError('CMS 说有 %r 期、实际只返回 %d 期（limit 没生效？）'
                            % (count, len(results)))
    out = {}
    bad = []
    for item in results:
        d = item.get('data') or {}
        mon = _title_month(d.get('title'))
        if not mon:
            bad.append(d.get('title'))
            continue
        rep = ((d.get('report') or {}).get('data')) or {}
        url = (((rep.get('file') or {}).get('data')) or {}).get('url')
        if not url:
            bad.append(d.get('title'))
            continue
        out.setdefault(mon, {'url': url, 'name': rep.get('name') or ''})
    if bad:
        raise SgxFetchError('%d 条报告的 title/URL 认不出来（title 格式又变了？）：%r'
                            % (len(bad), bad[:5]))
    if len(out) != len(results):
        raise SgxFetchError('%d 期里有重复月份，解析出 %d 个月'
                            % (len(results), len(out)))
    return out


def _fetch_report(cache_dir, mon, meta):
    """下载某期 PDF 到 cache_dir，返回 (本地路径, Last-Modified 原文或 None)。

    Last-Modified 落一份 .lastmod 边车文件：cache/ 是 gitignore 的可以随时删，
    但只要文件还在就不必为了拿一个日期重下 800KB。
    """
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, 'sgx_%s.pdf' % mon)
    side = path + '.lastmod'
    if os.path.exists(path) and os.path.exists(side):
        with open(side, encoding='utf-8') as f:
            return path, (f.read().strip() or None)
    raw, headers = _http_get(meta['url'])
    if not raw.startswith(b'%PDF'):
        raise SgxFetchError('%s 拿到的不是 PDF（前 16 字节 %r）：%s'
                            % (mon, raw[:16], meta['url']))
    with open(path, 'wb') as f:
        f.write(raw)
    lm = headers.get('Last-Modified') or ''
    with open(side, 'w', encoding='utf-8') as f:
        f.write(lm)
    return path, (lm or None)


# ══ PDF 解析 ══════════════════════════════════════════════════════════════
# 剥尾部脚注记号：'Derivatives Overall Market Volume (6)'、'Turnover Velocity (5)'、
# 'Total Trading Volume (9)'。只剥「尾部括号里全是数字」的，
# 'Iron Ore 62% Futures'、'KRW_USD FX Futures (Mini)' 这类括号里有字母的不动。
_FOOTNOTE = re.compile(r'\s*\(\s*\d+\s*\)\s*$')
_NUMERIC = re.compile(r'^-?[\d,]+(\.\d+)?$')
_MON_HDR = re.compile(r'^([A-Za-z]{3})[a-z]*[\s\-]+(\d{2}|\d{4})$')
_PAGENO = re.compile(r'\d{1,3}')


def _norm(s):
    """统一空白、统一标点，并**在一切解析动作之前**剥掉重述标记 `(#)`。

    `(#)` 既出现在数值上（'62,084(#)'）也出现在**表头单元格**上（'May 2013(#)'）——
    不在这里剥，2013 那几期既认不出列、也读不出数（口径坑 8）。
    """
    s = (s or '').replace('’', "'").replace('\xa0', ' ').replace('–', '-')
    s = s.replace('(#)', '')
    return re.sub(r'\s+', ' ', s).strip()


def _lab(s):
    """行标签 / 小节标题归一化，再 casefold。做四件事：

    1. 剥尾部脚注记号 `(n)` / `*` / `#` / `†` —— 官方挂过也去过
       （'Dairy Futures Volume #'、'Total Trading Volume (9)'、'Turnover Velocity (5)'），
       用全等匹配会在某个月突然全表失配。
    2. 剥**前导** `*` —— GIFT 迁移之后官方给活着的那一行加了前导星号
       （'* GIFT Nifty 50 Index Futures'，脚注说明该行是「经 SGX-ICI 成交并由 SGX 清算」），
       同一行在 2026 年又把星号去掉了。
    3. 统一金额后缀的空格：'($ Million)' / '($Million)' / '($million)' 一律写成 '($million)'。
       债券募资那一行 2017-06 起就是靠这个才认得出来（官方在 $ 和 Million 之间多打了个空格，
       而这一行只有一处、没有别名可依）。
    4. casefold —— 2015 那代是 '($million)' 小写、2019 那代是 'Securities market'（market 小写）。
    """
    s = _norm(s)
    prev = None
    while prev != s:
        prev = s
        s = _FOOTNOTE.sub('', s).rstrip(' *#†').lstrip('* ')
    s = s.casefold()
    return re.sub(r'\(\s*(s?\$)\s*millions?\s*\)', r'(\1million)', s)


def _hdr_month(t):
    """表头单元格 -> 'YYYY-MM'；不是月份形状返回 None。'Jun 2026' / 'Jun-26' 都认。"""
    m = _MON_HDR.match(_norm(t))
    if not m:
        return None
    for fmt in ('%b %Y', '%b %y'):
        try:
            d = datetime.datetime.strptime('%s %s' % (m.group(1)[:3], m.group(2)), fmt)
        except ValueError:
            continue
        return '%04d-%02d' % (d.year, d.month)
    return None


def _is_hdr_cell(t):
    t = _norm(t)
    if _hdr_month(t):
        return True
    if re.match(r'^FY\d{4}\s?Q[1-4]$', t):
        return True
    if re.match(r'^(FYTD|CYTD)\s?\d{2,4}$', t):
        return True
    if re.match(r'^(YoY|MoM)\s?%$', t, re.I):
        return True
    return False


def _page_lines(page):
    """页面上的文字行，**按 y 坐标（而非 PDF 阅读顺序）排序** —— 这一行就是口径坑 1 的解药。

    版面上标题永远画在自己表格的上方，只是 InDesign 把它写进文字层的顺序时前时后。
    按 y 重排之后「标题在前」恒成立，不需要任何「这一页是哪种顺序」的判断，
    也就不存在把 6 个同名 Total 错配一节的可能。
    """
    W, H = page.rect.width, page.rect.height
    out = []
    for b in page.get_text('dict')['blocks']:
        if b['type'] != 0:
            continue
        for ln in b['lines']:
            t = _norm(''.join(sp['text'] for sp in ln['spans']))
            if not t:
                continue
            x0, y0, x1, y1 = ln['bbox']
            # 页码只按**位置**认（页脚右下 / 页眉左上），绝不按「是不是纯数字」认：
            # At-A-Glance 的交易日 21、上市证券只数 601 都是纯数字，
            # 按内容过滤会把它们连同页码一起吃掉，而那两行随后会被当成小节标题，
            # 表面上一切正常，只是永远解析不出这两个字段。
            if _PAGENO.fullmatch(t) and (x0 > W - 90 or x1 < 90) and (y1 > H - 45 or y0 < 60):
                continue
            out.append({'t': t, 'x0': x0, 'yc': (y0 + y1) / 2.0})
    out.sort(key=lambda r: (round(r['yc'], 1), r['x0']))
    return out


def _parse_page(page, running_head):
    """把一页切成若干 block：{'title', 'cols': {'YYYY-MM': x}, 'rows': [{'lab','vals'}]}。

    切法：一行里过半单元格是表头形状（月份 / FYxxQn / FYTD / YoY%）就当表头行，
    它开启一个新 block；紧邻其上、且不属于任何数据行的文字行就是这个 block 的标题。

    数值不按「第几个」认列，按 **x 坐标就近**归到表头列（见 _row_values）——
    列数 9/7/6/5/2 怎么变都无所谓，2022 那几期「标签和第一个数字粘在同一行」
    也只会让那一列留空，而不会整行错位。
    """
    lines = [l for l in _page_lines(page) if l['t'] != running_head]
    rows = []
    for l in lines:
        if rows and abs(l['yc'] - rows[-1][-1]['yc']) < 3.0:
            rows[-1].append(l)
        else:
            rows.append([l])

    blocks = []
    cur = None
    pending = []
    for r in rows:
        hdrs = [c for c in r if _is_hdr_cell(c['t'])]
        if len(hdrs) >= 2 and len(hdrs) >= len(r) - 1:
            # 只拿**表头形状**的单元格定列位。有些页把小节名和表头排在同一行
            # （'Listings by Securities Type' 和 FY2019 Q3 同 y），
            # 把它也算进列位会让左边界左移，随后真正的标题被误判成数值单元格。
            cur = {'title': pending[-1] if pending else None,
                   'hcells': [(c['x0'], c['t']) for c in hdrs],
                   'rows': []}
            blocks.append(cur)
            pending = []
            continue
        if cur is None:
            pending.append(' '.join(c['t'] for c in r))
            continue
        xmin = min(x for x, _t in cur['hcells']) - 6
        labs = [c for c in r if c['x0'] < xmin]
        vals = [c for c in r if c['x0'] >= xmin]
        if vals:
            cur['rows'].append({'y': r[0]['yc'],
                                'lab': ' '.join(c['t'] for c in labs),
                                'vals': [(c['x0'], c['t']) for c in vals]})
        else:
            txt = ' '.join(c['t'] for c in r)
            # 折行的行标签（'SGX FTSE 10-Year Indonesia Government' / 'Bond Futures'
            # 分两行，数字排在两行中间）与「下一小节的标题」都表现为「一整行没有数值」。
            # 区别是距离：行距约 17pt，折行的两半离数值行 5~6pt；标题离最近的数据行
            # 有一整个表头的距离（26pt 以上）。
            if cur['rows'] and abs(r[0]['yc'] - cur['rows'][-1]['y']) < 9:
                cur['rows'][-1]['lab'] = (cur['rows'][-1]['lab'] + ' ' + txt).strip()
            else:
                pending.append(txt)
    return blocks


def _load_blocks(path):
    """整份 PDF 的全部 block。"""
    import fitz                       # 延迟 import：没装时报错点明确，不拖累别家
    doc = fitz.open(path)
    try:
        running = None
        for l in _page_lines(doc[min(1, doc.page_count - 1)]):
            if l['t'].startswith('SGX Monthly Market Statistics'):
                running = l['t']       # 每页页眉，剔掉免得被当成小节标题
        out = []
        for pno in range(doc.page_count):
            for b in _parse_page(doc[pno], running):
                b['page'] = pno + 1
                out.append(b)
    finally:
        doc.close()
    return out


def _num(t):
    """'1,619,444' -> 1619444.0；'49%' -> 49.0；'N.A.' / '-' / '' -> None。"""
    s = _norm(t).replace(',', '')
    if s.endswith('%'):
        s = s[:-1]
    if not s or not _NUMERIC.match(s):
        return None
    return float(s)


# 「千分位分组」的形状：首组 1~3 位，其后每个分隔符都恰好带三位数字。
# 分隔符写成 [.,] 是**故意的** —— 官方偶尔把某一个逗号排版成小数点（口径坑 15），
# 这个字符类就是用来把那种错印一起认下来的。
_GROUPED_INT = re.compile(r'^-?\d{1,3}(?:[.,]\d{3})+$')


def _cell_num(text, block, row, mon):
    """单元格取数，顺手修掉官方「千分位逗号排版成小数点」的错印（口径坑 15）。

    判据只认一种形状：整个 token 是合法的千分位分组，而其中**恰好一个**分隔符是小数点
    （`923.134`、`18.995`、`1,234.567`）。这时那个点占的正是千分位的位置，
    只能是逗号排错，去掉分隔符按整数入库。

    为什么敢修而不是抛：
      · 官方在**下一期的上月列里照抄同一个错印**（2020-01 那处实测如此），
        所以 _fill_from_next 这条既有的回补路在这里是死的 —— 抛异常等于这个月**永远**
        进不来，一个错格拖掉另外 31 个好格，与本模块「无人值守」的定位相悖；
      · 本模块对**读法唯一确定**的官方错印一贯是直接修的，不是新开的先例 ——
        `(#)` 重述标记（_norm）、`INR_USD FX FFutures` 拼错（P_INRUSD）、
        `Energy Metals` 漏了 "Volume"（T_COMMODITY）、A50 的 `Future` 单数（P_A50）
        都是同一类处置；
      · 修出来的值可独立复核：923,134 夹在 2019-12 的 937,830 与 2020-02 的 899,575 之间；
        18,995 与同期 FYTD 列、以及 2016-08 / 2016-09 两期的 Jul 2016 列逐位相同。

    「不静默」由三件事共同保证：每修一处打一条 stderr 警告（照 spgi / miax 的 `[模块] ⚠` 格式）、
    判据窄到全书三处真小数无一命中（口径坑 15 列了那三处）、以及 _validate 自检 5
    对入库字段的整数兜底 —— 换一种形状的错印在那里会当场炸掉，而不是缩水 1000 倍写进库。
    """
    t = _norm(text)
    if _GROUPED_INT.match(t) and t.count('.') == 1:
        fixed = float(t.replace('.', '').replace(',', ''))
        sys.stderr.write(
            '[sgx] ⚠ %s p%s 小节「%s」行「%s」：官方把千分位逗号排成了小数点 '
            '(%s)，按 %d 入库（口径坑 15）\n'
            % (mon, block.get('page'), block.get('title') or '?',
               row['lab'], t, int(fixed)))
        return fixed
    return _num(text)


def _row_value(block, row, mon):
    """按 x 坐标把数值归到目标月那一列，取不到返回 None。

    不用「第几个数值」定位：见口径坑 11。列间距约 55-70pt，取最近且距离 < 25pt 的，
    归不上就当空 —— 宁可这一格为空被上层的缺列护栏抓住，也不要偏移一列后
    写进一个来自隔壁列的、看上去完全合理的数字。

    ⚠ 表头里同一个月份**会出现两次**：官方偶尔把最右边那列「去年同月」印错成本月。
    全语料 138 期里有 22 个 block 中招，其中真正咬人的三处是
    2016-12 的 IPO 募资表（`... Nov 2016 | Dec 2016 | FYTD 2017 | CYTD 2016 | Dec 2016 | YoY%`，
    最后那个应是 Dec 2015）、2022-11 与 2022-12 的利率期货表（同样是最右列印错）。
    表头顺序是固定的 `[FYQ, FYQ, M-2, M-1, M0, FYTD, CYTD, 去年同月, YoY%]`，
    本月列永远在 FYTD 左边、错印的那列永远在最右，所以**重复时取最左那个**。
    """
    hx = [x for x, t in block['hcells'] if _hdr_month(t) == mon]
    if not hx:
        return None
    hx = min(hx)
    best, bestd = None, 25.0
    for x, t in row['vals']:
        d = abs(x - hx)
        if d < bestd:
            best, bestd = t, d
    # 走 _cell_num 而不是 _num：所有入库数值都从这里过一遍，
    # 官方把千分位逗号排成小数点的错印在这一道统一修掉（口径坑 15）。
    return _cell_num(best, block, row, mon) if best is not None else None


def _blocks_titled(blocks, titles):
    return [b for b in blocks if _lab(b['title'] or '') in titles]


def _total_is_shifted(block, mon, total):
    """块里的 Total 值是否**小于同块某个分项** —— 官方漏印一个行标签的签名。

    官方偶尔会漏印表格里某一行的标签，于是从那一行往下**标签相对数字整体上移一格**：
    `Total` 这个标签落到了最后一个产品行上，而真正的合计行变成「有数字、没标签」。
    实测 2020-03 期 p15 外汇期货表正是如此 ——
      官方印的 `Total` 位置：14,891 | 52,210 | 3,524 | 22,082 | **26,604** | ...
      下面那行（无标签）  ：5,800,823 | 7,753,990 | 2,340,737 | 2,440,396 | **2,972,857** | ...
    用 2020-04 期的 Mar-2020 列核实：`USD_SGD FX Futures` = 26,604、`Total` = 2,972,857，
    与上面两行**逐位吻合**，证明错位的是标签而不是数字。
    错位后的 26,604 是个完全合法的月度张数，没有这道检查就会把外汇期货合计写小 112 倍，
    而且全程不报错 —— 正是本模块最忌讳的那类「静默错配」。

    判据用的是恒等式「合计不可能小于自己的分项」，全部 138 期实测只有 2020-03 一处命中，
    零误杀。命中时返回 None 而不是抛异常：交给 _fill_from_next 用下一期报告
    （那一期同一列印的是正确值）补上，只损失这一格、而不是整月 32 个字段。
    """
    if total is None:
        return False
    for r in block['rows']:
        if _lab(r['lab']) in _TOTAL:
            continue
        v = _row_value(block, r, mon)
        if v is not None and v > total + 0.5:
            return True
    return False


def _pick_row(blocks, titles, labels, mon, what, reject=None, is_total=False):
    """在指定小节里找唯一一行匹配 labels 的行，返回它在 mon 那列的值；找不到返回 None。

    命中多行一律抛异常：那意味着官方在同一节里同时留下了新旧两个名字
    （改名过渡月），该由人来决定取哪个，而不是让代码随手挑一个。

    reject: 一个「行标签前缀」集合，**整块**里只要有一行命中就跳过这一块。
    用来对付官方把标题写错的情形（见 REJECT_SSF）。

    is_total: 取的是小节合计行时置真，额外过一道 _total_is_shifted 的错位检查。
    """
    hits = []
    for b in _blocks_titled(blocks, titles):
        if reject and any(_lab(r['lab']).startswith(p)
                          for r in b['rows'] for p in reject):
            continue
        for r in b['rows']:
            if _lab(r['lab']) in labels:
                hits.append((b, r))
    if not hits:
        return None
    if len(hits) > 1:
        raise SgxFetchError('%s：%r 在小节 %r 里命中 %d 行，无法判定取哪一行'
                            % (what, sorted(labels), sorted(titles), len(hits)))
    val = _row_value(hits[0][0], hits[0][1], mon)
    if is_total and _total_is_shifted(hits[0][0], mon, val):
        return None
    return val


def _sum_rows(blocks, titles, labels, mon, what):
    """在指定小节里把所有匹配 labels 的行加起来（一行都没匹配上返回 None）。

    与 _pick_row 的区别：这里**允许**多行命中。只在「同一个产品被官方拆成新旧两行、
    而且两行本就该相加」时使用，目前只有 Nifty 一处，理由写在 P_NIFTY 那里。
    """
    del what                             # 只为调用点可读，出错交给缺列护栏统一报
    total = None
    for b in _blocks_titled(blocks, titles):
        for r in b['rows']:
            if _lab(r['lab']) not in labels:
                continue
            v = _row_value(b, r, mon)
            if v is not None:
                total = v if total is None else total + v
    # 「行找到了但那一列读不出来」与「行根本没找到」在这里一律返回 None：
    # 两者都由 _missing_columns 统一拦，而且都可能被 _fill_from_next 用下一期补上
    # （2021-01 的陈旧页正是前一种）。在这里提前抛异常会把回补路堵死。
    return total


# ── 小节标题白名单（全部是 _lab() 之后的形态）─────────────────────────────
T_GLANCE = {'sgx statistics at a glance'}
T_DERIV = {'derivatives overall market volume'}
T_EQIDX_FUT = {'equity index futures volume'}
T_FX_FUT = {'foreign exchange futures volume'}
T_RATES_FUT = {'interest rates futures volume'}
T_CRYPTO = {'cryptocurrency derivatives volume'}
# 换手率的**第二处**来源（口径坑 18）。2017-06 那期官方印成 `Turnover Velocity(5)`
# （少一个空格），_lab() 的脚注正则不要求前置空白，所以两种写法都归到同一个键。
T_VELOCITY = {'turnover velocity'}
T_LISTINGS = {'number of listings (month-end)'}
T_BONDS = {'number of new bond listings'}
# IPO 募资那一节的标题在 2017-06 ~ 2020-10 共 41 期里排版异常拿不到，
# 所以那段改用「行标签正好是 SGX Mainboard + SGX Catalist 的两行块」兜底，见 _read_issuer。
T_IPOFUNDS = {'funds raised through ipos and rtos ($million)',
              'fund raised through ipos and rtos ($million)',
              'funds raised through ipos ($million)'}

# 商品类**成交量**小节（不含月末未平仓）。两代口径都已用官方新闻稿验过：
#   现代（2026-06 期）FYTD 六节相加 = 78,771,544 = 新闻稿 "78.8 million lots" ✅
#   旧代（2016-01 期）Dec-2015 五节相加 = 1,071,178 = 新闻稿 "1.1 million"，
#         且 mom = +8.4% 与新闻稿 "up 8% month on month" 吻合 ✅
# crypto 不在其中，是官方口径本身就不含（口径坑 12）。
T_COMMODITY = {
    'sicom volume', 'energy volume', 'metal and dry bulk volume',
    'dairy futures volume', 'dairy options volume',
    'energy metals volume', 'energy metals',           # 2022-09~2023-02 官方漏了 "Volume"
    'agri-commodities volume', 'agri-commodities futures volume',
    'energy futures volume', 'metal futures volume',
    'sgx asiaclear cleared swaps volume', 'sgx asiaclear futures volume',
    'sgx asiaclear cleared options volume',
}

_TOTAL = {'total'}

# 2025-11 那期官方把个股期货那张表的标题也写成了 `Equity Index Futures Volume`
# （正常应是 `Equity Futures Volume`），于是同一页同一个标题下出现两个 Total：
# 17,395,074 量级的股指期货合计，和 617,817 量级的个股期货合计。
# 取股指期货 Total 时，凡是含 `Single Stock Futures ...` 行的块一律排除 ——
# 按标题信任官方在这一期会拿到小 20 倍的数字，而那个数字本身完全合理，没人看得出来。
REJECT_SSF = {'single stock futures'}

# ── 行标签别名（_lab() 之后）──────────────────────────────────────────────
G_TRADING_DAYS = {'number of trading days (securities)',
                  'number of trading days (stock market)'}
G_TURNOVER_VOL = {'securities market turnover volume (million shares)',
                  'stock market turnover volume (million shares)'}
G_TURNOVER_VAL = {'securities market turnover value ($million)',
                  'stock market turnover value ($million)'}
G_SDAV = {'securities daily average ($million)',
          'stock market daily average ($million)'}
G_LISTED = {'total number of listed securities'}
G_MKTCAP = {'total market capitalisation ($million)'}
G_VELOCITY = {'overall turnover velocity'}
# p8 `Turnover Velocity` 表的首行。同表另有 `SGX Mainboard` / `SGX Catalist` 两行，
# 全等匹配天然把它们排除 —— 要的是**全所**口径，与 p2 的 At-A-Glance 那一行同义。
P_SGX_OVERALL = {'sgx overall'}
G_DERIV_VOL = {'derivatives volume'}
G_DDAV = {'derivatives daily average volume'}

D_TOTAL_VOL = {'total trading volume'}
D_OI = {'total open interest'}

# A50 有一期把 Futures 印成了单数 Future（2016-06）。
P_A50 = {'ftse china a50 index futures', 'ftse china a50 index future'}
# 只要标准合约；Mini / Micro / USD / Total Return / Climate PAB 各自单列，全等匹配自然排除。
P_NIKKEI = {'nikkei 225 index futures'}
# Nifty 一族：**必须相加，不能挑一行**。演变实测如下（全在 Equity Index Futures Volume 节内）：
#   2015-01~2015-10  `SGX CNX Nifty Index Futures`（指数 2015-11 由 S&P CNX Nifty 更名 Nifty 50）
#   2015-11~2022-06  `SGX Nifty 50 Index Futures` / `Nifty 50 Index Futures`（两种写法不同期出现）
#   2022-11~2023-06  SGX 那行仍是主力，同表另起一行极小的 `NSE IFSC Nifty 50 Index Futures`
#   2023-07~2024-06  GIFT Connect 迁移完成：**SGX 那行变成全 0**，量全在
#                    `* NSE IFSC/IX Nifty 50 Index Futures`、2024-05 起改叫 `* GIFT Nifty 50 …`
#   2024-07~         只剩 GIFT 一行
# 挑一行的写法在 2024-04~2024-06 会挑中那条全 0 的旧行（看上去完全正常，只是把
# 一百多万张写成 0）；相加则在任何一期都等于「SGX 清算的 Nifty 50 总量」，
# 因为重叠期里必有一行是 0 或极小的过渡量。
P_NIFTY = {'sgx cnx nifty index futures', 'sgx nifty 50 index futures',
           'nifty 50 index futures', 'gift nifty 50 index futures',
           'nse ifsc nifty 50 index futures', 'nse ix nifty 50 index futures',
           'nse ixnifty 50 index futures'}
P_MSCI_SG = {'msci singapore index futures'}
P_MSCI_TW = {'msci taiwan index futures'}
P_FTSE_TW = {'ftse taiwan index futures'}
P_USDCNH = {'usd_cnh fx futures'}
P_INRUSD = {'inr_usd fx futures', 'inr_usd fx ffutures'}   # 2016 那代官方拼错，两个 F


def _velocity(blocks, mon, g):
    """Overall Turnover Velocity —— p2 优先、p8 兜底（口径坑 18）。

    **顺序不能反。** 2018-03 起两处逐格等价（同期 p2 的 Feb 55% / Mar 43% 与 p8 的
    `SGX Overall` 逐格相同），继续优先 p2 就保证 2018-03 及之后**已入库的值一格不动**；
    2018-02 及更早 p2 根本没有这一行，兜底那一支把 38 个月的历史接了回来 ——
    p8 的 `Turnover Velocity` 表 2015-01 起每期都在，且每期给 M-2 / M-1 / M0 三个月度列，
    所以同一个数据月天然有三期报告互证（实测 38/38 三重逐格相同）。

    p8 那张表最右列是**去年同月**，官方偶尔在那一列印一个差 1pp 的数；
    这里走的是 _row_value 的既有约定「只认表头等于 mon 的那一列」，取的永远是 M0。
    """
    v = g(G_VELOCITY, 'turnover velocity')
    if v is not None:
        return v
    return _pick_row(blocks, T_VELOCITY, P_SGX_OVERALL, mon,
                     'turnover velocity (p8 SGX Overall)')


def parse_report(path, mon):
    """解析一期报告，返回 {csv 列名: float|None}。mon 是这期的**数据月**。"""
    blocks = _load_blocks(path)

    glance = _blocks_titled(blocks, T_GLANCE)
    if len(glance) != 1:
        raise SgxFetchError('%s：找到 %d 个 "SGX Statistics At A Glance" 小节（应为 1）'
                            % (mon, len(glance)))
    if not any(_hdr_month(t) == mon for _x, t in glance[0]['hcells']):
        raise SgxFetchError('%s：At-A-Glance 表头里没有 %s 这一列（拿到 %r）'
                            % (mon, mon, [t for _x, t in glance[0]['hcells']]))

    def g(labels, what):
        return _pick_row(blocks, T_GLANCE, labels, mon, what)

    rec = {
        'sec_trading_days':       g(G_TRADING_DAYS, 'trading days'),
        'sec_turnover_mnshares':  g(G_TURNOVER_VOL, 'turnover volume'),
        'sec_turnover_sgdmn':     g(G_TURNOVER_VAL, 'turnover value'),
        'sdav_sgdmn':             g(G_SDAV, 'SDAV'),
        'listed_securities':      g(G_LISTED, 'listed securities'),
        'mktcap_sgdmn':           g(G_MKTCAP, 'market cap'),
        'turnover_velocity_pct':  _velocity(blocks, mon, g),
        'deriv_vol_contracts':    g(G_DERIV_VOL, 'derivatives volume'),
        'ddav_contracts':         g(G_DDAV, 'DDAV'),

        'deriv_oi_contracts': _pick_row(blocks, T_DERIV, D_OI, mon, 'total OI'),

        'vol_equity_index_futures_contracts':
            _pick_row(blocks, T_EQIDX_FUT, _TOTAL, mon, 'equity index futures total',
                      reject=REJECT_SSF, is_total=True),
        'vol_a50_futures_contracts':     _pick_row(blocks, T_EQIDX_FUT, P_A50, mon, 'A50'),
        'vol_nikkei225_futures_contracts': _pick_row(blocks, T_EQIDX_FUT, P_NIKKEI, mon, 'Nikkei'),
        'vol_nifty50_futures_contracts': _sum_rows(blocks, T_EQIDX_FUT, P_NIFTY, mon, 'Nifty'),
        'vol_msci_singapore_futures_contracts':
            _pick_row(blocks, T_EQIDX_FUT, P_MSCI_SG, mon, 'MSCI Singapore'),
        'vol_msci_taiwan_futures_contracts':
            _pick_row(blocks, T_EQIDX_FUT, P_MSCI_TW, mon, 'MSCI Taiwan'),
        'vol_ftse_taiwan_futures_contracts':
            _pick_row(blocks, T_EQIDX_FUT, P_FTSE_TW, mon, 'FTSE Taiwan'),

        'vol_fx_futures_contracts':
            _pick_row(blocks, T_FX_FUT, _TOTAL, mon, 'FX futures total', is_total=True),
        'vol_usdcnh_futures_contracts': _pick_row(blocks, T_FX_FUT, P_USDCNH, mon, 'USD_CNH'),
        'vol_inrusd_futures_contracts': _pick_row(blocks, T_FX_FUT, P_INRUSD, mon, 'INR_USD'),
        'vol_rates_futures_contracts':
            _pick_row(blocks, T_RATES_FUT, _TOTAL, mon, 'rates futures total', is_total=True),
        'vol_crypto_contracts':
            _pick_row(blocks, T_CRYPTO, _TOTAL, mon, 'crypto total', is_total=True),
    }
    rec.update(_read_deriv_split(blocks, mon))
    rec['vol_iron_ore_contracts'] = _read_iron_ore(blocks, mon)
    rec['vol_commodities_contracts'] = _read_commodities(blocks, mon)
    rec.update(_read_issuer(blocks, mon))
    return rec


def _read_deriv_split(blocks, mon):
    """把 `Derivatives Overall Market Volume` 那一节拆成期货 / 期权 / 掉期三桶。

    **不能按固定行名取**：这一节的分项行名跨三代换过两次，而且分项个数都不一样 ——
      2015-01 ~ 2018-08：Total Futures / Total Options / **Total AsiaClear Cleared Swaps**
                         / **Total AsiaClear Cleared Options**   （四项）
      2018-09 ~ 2022 中：Total Futures / Total Options / **Total Swaps Volume**
                         / **Total Options On Swaps Volume**     （四项）
      2022 中 ~ 至今：   Total Futures / Total Options / Total Swaps Trading Volume（三项）
    按行名硬编码的后果不是报错，是**少加一项**：那几年 OTC 清算的期权（每月一两万张）
    会凭空消失，而 deriv_options 仍然是个像模像样的数。

    所以这里按语义分桶：行名里带 option 的进期权桶（`Options On Swaps` 也是期权，
    所以先判 option 再判 swap），带 swap 的进掉期桶，带 futures 的进期货桶。
    分完之后 _validate 会核「三桶之和 == 官方自己印的 Total Trading Volume」——
    全语料 138 期逐位相等，任何一行漏进桶或错进桶都会当场炸掉。
    """
    fut = opt = swp = None
    total = _pick_row(blocks, T_DERIV, D_TOTAL_VOL, mon, 'derivatives total volume')
    for b in _blocks_titled(blocks, T_DERIV):
        for r in b['rows']:
            lab = _lab(r['lab'])
            if not lab.startswith('total ') or 'open interest' in lab:
                continue
            if lab in D_TOTAL_VOL:
                continue
            v = _row_value(b, r, mon)
            if v is None:
                continue
            if 'option' in lab:
                opt = v if opt is None else opt + v
            elif 'swap' in lab:
                swp = v if swp is None else swp + v
            elif 'futures' in lab:
                fut = v if fut is None else fut + v
            else:
                raise SgxFetchError('%s：Derivatives Overall 里出现认不出的分项行 %r'
                                    % (mon, r['lab']))
    return {'deriv_futures_vol_contracts': fut,
            'deriv_options_vol_contracts': opt,
            'deriv_swaps_vol_contracts': swp,
            'deriv_vol_total_check': total}


def _read_iron_ore(blocks, mon):
    """铁矿石合计 = 所有**成交量**小节里行名含 "Iron Ore" 的行之和（不含 Total 行）。

    为什么按名字扫而不是按固定行清单：这个品类跨三代改过名也换过归属 ——
    2015/2016 在 `SGX AsiaClear (Cleared Swaps|Futures|Cleared Options) Volume` 三节里
    叫 `OTC Iron Ore 62%` / `SGX Iron Ore 62 %Futures` / `OTC Iron Ore Options On Swaps`；
    2018 起并进 `Metal And Dry Bulk Volume` 叫 `Iron Ore 62% Futures`；
    2025 起又改叫 `SGX IODEX Iron Ore Futures` / `SGX Options On IODEX Iron Ore Futures`。
    固定清单每换一次名就静默少加一块，而少加之后的数字看上去仍然合理。

    必须限定在「小节标题以 Volume 结尾」的成交量节里：同名产品在
    `... Month-End Open Interest` 节里也有一行，混进来就是把存量加进流量。

    口径已用官方新闻稿验过：2016-01 那期算出的 Dec-2015 = 988,532，
    与 SGX 2016-01-07 新闻稿 "Iron Ore Derivatives volume was 988,532" **逐位相同**。
    """
    total = None
    for b in blocks:
        t = _lab(b['title'] or '')
        if not t.endswith('volume') or 'open interest' in t:
            continue
        for r in b['rows']:
            lab = _lab(r['lab'])
            if 'iron ore' not in lab or lab in _TOTAL:
                continue
            v = _row_value(b, r, mon)
            if v is not None:
                total = v if total is None else total + v
    return total


def _read_commodities(blocks, mon):
    """商品合计 = 商品类成交量小节的 Total 之和（**不含 crypto**，见口径坑 12）。

    白名单是刻意的：官方那份「Commodities」口径就是这几节，不是「所有非金融的东西」。
    白名单外冒出新的商品节时，本函数只会漏加而不会加错 —— 所以
    _validate 里另有一道「商品合计不得小于铁矿石合计」的下界检查兜底。
    """
    total = None
    for b in _blocks_titled(blocks, T_COMMODITY):
        for r in b['rows']:
            if _lab(r['lab']) not in _TOTAL:
                continue
            v = _row_value(b, r, mon)
            if v is None:
                continue
            # 任何一节的合计一旦是错位的标签（见 _total_is_shifted），整个商品合计
            # 就不可信了 —— 少加一节的结果同样「像模像样」。整格返回 None，
            # 交给 _fill_from_next 用下一期报告补，而不是写一个偏小的数。
            if _total_is_shifted(b, mon, v):
                return None
            total = v if total is None else total + v
    return total


def _read_issuer(blocks, mon):
    """新上市 / 退市家数、IPO 募资、新债券挂牌与债券募资。

    `Number of Listings (month-end)` 那一页的**文字层是列优先**（先连着吐
    `SGX Mainboard / - Primary Listings / - Secondary Listings / - IPOs / - Delistings`
    五个标签，再一列一列地吐数）。按阅读顺序解析必须为这页单写一个块解析器；
    本模块按 y 聚行、按 x 归列，这页跟别的页没有任何区别，所以这里不需要特判。

    `- IPOs` / `- Delistings` 在这一节里各出现两次（Mainboard 一次、Catalist 一次），
    要的正是两者之和，所以这里不能用 _pick_row（它命中多行会抛异常）。
    条数一律断言等于 2：官方哪天多加一个板块（比如给 Global Quote 也开 IPO 行），
    静默多加一块比报错难发现得多。
    """
    out = {}
    for key, label in (('ipos_count', '- ipos'), ('delistings_count', '- delistings')):
        vals = []
        for b in _blocks_titled(blocks, T_LISTINGS):
            for r in b['rows']:
                if _lab(r['lab']) == label:
                    vals.append(_row_value(b, r, mon))
        if not vals:
            out[key] = None
            continue
        if len(vals) != 2 or any(v is None for v in vals):
            raise SgxFetchError('%s：Number of Listings 小节里 %r 拿到 %r（应为 2 个数）'
                                % (mon, label, vals))
        out[key] = sum(vals)

    ipo_blocks = _blocks_titled(blocks, T_IPOFUNDS)
    if not ipo_blocks:
        # 2017-06 ~ 2020-10 共 41 期：标题行与上一张表的表头排在同一 y 上，
        # 拿不到标题。按「行标签正好是 SGX Mainboard + SGX Catalist 的两行块」兜底 ——
        # 全书只有这一张表长这样（Number of Listings 那张的这两行下面还挂着子行）。
        ipo_blocks = [b for b in blocks
                      if [_lab(r['lab']) for r in b['rows']] == ['sgx mainboard', 'sgx catalist']]
    if len(ipo_blocks) != 1:
        raise SgxFetchError('%s：IPO 募资小节找到 %d 个（应为 1）' % (mon, len(ipo_blocks)))
    vals = [_row_value(ipo_blocks[0], r, mon) for r in ipo_blocks[0]['rows']]
    if any(v is None for v in vals):
        raise SgxFetchError('%s：IPO 募资小节读不出 %s 那一列：%r' % (mon, mon, vals))
    out['ipo_funds_sgdmn'] = sum(vals)

    out['new_bond_listings'] = _pick_row(
        blocks, T_BONDS, {'new bond listings'}, mon, 'new bond listings')
    # 债券募资那一行 2019-07 ~ 2019-12 改叫 `Amount Issued ($ Million)`，之后又改回
    # `Fund Raised ($ million)`。确认是同一行不是新口径：2019-07 那期的 `Amount Issued`
    # 在 Jun-2019 列上是 26,832，与 2019-06 那期 `Fund Raised` 的 Jun-2019 逐位相同。
    out['bond_funds_sgdmn'] = _pick_row(
        blocks, T_BONDS,
        {'fund raised ($million)', 'funds raised ($million)', 'amount issued ($million)'},
        mon, 'bond funds raised')
    return out


# ══ 校验 ═════════════════════════════════════════════════════════════════
# 各列**最早**应该有值的月份。早于此天然为空（官方那时根本没这个产品/没印这一行），
# 不算解析失败；晚于此还为空就是解析出问题了，一律抛异常拒绝写入。
# 这张表是拿 2015-01 ~ 2026-06 全部 138 期实测出来的，不是估的。
FIRST_MONTH = {
    # 换手率**全期都有**（口径坑 18）。这里原来写的是 '2018-03'（= p2 的 At-A-Glance
    # 多出这一行的那期），于是 2015-01~2018-02 那 38 个月的空值被缺列护栏放行、
    # 一直没人发现官方其实在 p8 印着。加上 p8 兜底之后这一列与主体同起点。
    'turnover_velocity_pct':                START_MONTH,
    # 实际首月是 **2020-07**（2020-06 期 PDF 全文无 'FTSE Taiwan'，2020-07 期才出现，
    # 首月 82,048 张与 2020-07-20 挂牌吻合）。原来写 '2020-08' 差了一个月 ——
    # 数据是对的，但那一个月的护栏是瞎的：万一哪天 2020-07 解析失败，
    # _missing_columns 会认为「那个年代还没这个产品」而放行。
    'vol_ftse_taiwan_futures_contracts':    '2020-07',
    'vol_crypto_contracts':                 '2025-11',
    'vol_equity_index_futures_contracts':   START_MONTH,
    'vol_rates_futures_contracts':          START_MONTH,
}
# 这两列是「产品存在期」而非「从某月起一直有」，单独列出：
# MSCI Taiwan 2020 年底停用，之后官方不再印这一行。
LAST_MONTH = {
    'vol_msci_taiwan_futures_contracts':    '2020-12',
}

DATA_COLUMNS = [
    'sec_trading_days', 'sec_turnover_mnshares', 'sec_turnover_sgdmn', 'sdav_sgdmn',
    'listed_securities', 'mktcap_sgdmn', 'turnover_velocity_pct',
    'deriv_vol_contracts', 'ddav_contracts',
    'deriv_futures_vol_contracts', 'deriv_options_vol_contracts',
    'deriv_swaps_vol_contracts', 'deriv_oi_contracts',
    'vol_equity_index_futures_contracts', 'vol_a50_futures_contracts',
    'vol_nikkei225_futures_contracts', 'vol_nifty50_futures_contracts',
    'vol_msci_singapore_futures_contracts', 'vol_msci_taiwan_futures_contracts',
    'vol_ftse_taiwan_futures_contracts',
    'vol_fx_futures_contracts', 'vol_usdcnh_futures_contracts',
    'vol_inrusd_futures_contracts', 'vol_rates_futures_contracts',
    'vol_iron_ore_contracts', 'vol_commodities_contracts', 'vol_crypto_contracts',
    'ipos_count', 'delistings_count', 'ipo_funds_sgdmn',
    'new_bond_listings', 'bond_funds_sgdmn',
]


def _missing_columns(mon, rec):
    """该有值却为空的列。空得**理所应当**的（那个年代没这个产品）不算。"""
    missing = []
    for c in DATA_COLUMNS:
        if rec.get(c) is not None:
            continue
        if mon < FIRST_MONTH.get(c, START_MONTH):
            continue                     # 那个年代官方根本没有这一行
        if c in LAST_MONTH and mon > LAST_MONTH[c]:
            continue                     # 产品已停用
        missing.append(c)
    return missing


# ══ 已确证的官方错印更正表 ═══════════════════════════════════════════════
# {(数据月, 列名): (库里/解析出的错值, 更正值, 证据)}
#
# **进这张表的门槛：更正值必须能在官方 PDF 里直接读到，或由官方自己印的恒等式闭合。**
# 「相邻月看着不像」不够格 —— 那只能触发护栏点名，不能决定填什么。
# 每加一条都要把证据写进 evidence 字符串：日后复查的人不必重跑一遍扫描。
#
# 为什么需要这张表，而不是靠解析器修：这里装的是**解析器原则上修不了**的那一类 ——
# 官方把标签和数字错开了行，PDF 的文字层里没有任何信息能指出哪一行才是对的，
# 只有**另一期报告**才能作证。_cell_num 那种「token 形状唯一确定读法」的错印不进这张表。
_ERRATA = {
    ('2020-03', 'vol_usdcnh_futures_contracts'): (1990.0, 1255507.0, """\
2020-03 期 p15 外汇期货表漏印了一个行标签（口径坑 14 的补充），从 TWD_USD 那行起
标签整体比数字低一行，于是 `USD_CNH FX Futures` 这个标签落到了 TWD_USD (Mini) 的
数字上。证据链三条，互相独立：
  ① 2020-04 期 p15 同一张表标签正确，Mar-2020 列 `USD_CNH FX Futures` = 1,255,507，
     而 `TWD_USD (Mini) FX Futures` = 1,990 —— 与 2020-03 期错位后的两行逐位对应；
  ② 2020-03 期自己那张表里，1,255,507 就印在紧接着的 `USD_CNH FlexC FX Futures`
     标签上，即「真值在，只是标签低了一行」；
  ③ 同一处错位在 Feb-2020 列上留下同样的痕迹：2020-03 期把 Feb 的 USD_CNH 印成 1,047，
     而 2020-02 期自己印的是 962,032、2020-04 期印的也是 962,032。
错位后的 1,990 是个完全合法的月度张数，_total_is_shifted 管不到它（它不是合计行），
所以在两道新护栏之前它是**静默**写小 631 倍的。"""),
}


def _apply_errata(mon, rec):
    """把更正表应用到刚解析出来的记录上（只在错值与表里登记的完全一致时才动）。

    错值对不上就不动、只告警：说明官方改版重发了这一期（那是好事，本来就该用官方的），
    或者这条更正已经失效。**绝不能闷头写更正值** —— 那等于让一张过期的表悄悄篡改新数据。
    """
    for (m, col), (bad, good, _why) in _ERRATA.items():
        if m != mon or col not in rec:
            continue
        v = rec.get(col)
        if v is not None and abs(v - bad) < 0.5:
            rec[col] = good
            sys.stderr.write('[sgx] ⚠ %s %s：按更正表把官方错印 %s 改为 %s（见 _ERRATA）\n'
                             % (mon, col, _fmt(bad), _fmt(good)))
        elif v is not None and abs(v - good) >= 0.5:
            sys.stderr.write('[sgx] ⚠ %s %s：更正表登记的错值是 %s，本次解析却得到 %s —— '
                             '官方可能已重发这一期，请人工复核 _ERRATA 这一条是否还成立\n'
                             % (mon, col, _fmt(bad), _fmt(v)))
    return rec


def _repair_errata(body, idx):
    """把更正表应用到**已经在库**的行上，返回改动清单。

    为什么必须有这一步：update() 的既定契约是「已在 CSV 里的月份不重新下载、不重新解析」，
    所以光在解析层修好是不够的 —— 那几个月早就入库了，永远不会再被解析一次，
    错值会一直躺在台账里。这里是唯一能把它们改过来的地方。

    幂等：只在单元格**逐字节等于**登记的错值时才改写；改过之后它等于更正值，
    第二次跑就什么都不做，文件字节级不变。
    既不是错值也不是更正值时不动、只告警 —— 有人手工改过，或者官方重述了，
    两种情况都该由人来决定，不该让一张更正表去覆盖。
    """
    by_month = {r[0]: r for r in body}
    fixed = []
    for (mon, col), (bad, good, _why) in sorted(_ERRATA.items()):
        row = by_month.get(mon)
        if row is None or col not in idx:
            continue
        cell = (row[idx[col]] or '').strip()
        if cell == _fmt(bad):
            row[idx[col]] = _fmt(good)
            fixed.append('%s %s: %s -> %s' % (mon, col, _fmt(bad), _fmt(good)))
            sys.stderr.write('[sgx] ⚠ %s %s：按更正表把已入库的官方错印 %s 改为 %s'
                             '（见 _ERRATA 的证据链）\n'
                             % (mon, col, _fmt(bad), _fmt(good)))
        elif cell not in ('', _fmt(good)):
            sys.stderr.write('[sgx] ⚠ %s %s：库里是 %s，更正表登记的错值是 %s、更正值是 %s '
                             '—— 三者都对不上，本模块不动它，请人工确认这条更正是否还成立\n'
                             % (mon, col, cell, _fmt(bad), _fmt(good)))
    return fixed


# ══ 量级跳变护栏 ═══════════════════════════════════════════════════════════
# 千分位错印的倍数恒等于 1000。但这道判据拿**上一个月**当参照，而上一个月自己也在动，
# 所以观测到的倍数 = 1000 × (上月 / 本月真值)。全 138 期实测：除 ipo_funds_sgdmn 外，
# **任何一列的历史最大月环比倍数只有 7.8 倍**（bond_funds_sgdmn 2022-07→08）。
# 于是真值落在 [1000/7.8, 1000×7.8] ≈ [128, 7800]，取 [100, 10000] 全覆盖，
# 而离最近的合法环比（7.8 倍）还有 13 倍空隙 —— 实测零误杀。
_SCALE_LO, _SCALE_HI = 100.0, 10000.0

# ipo_funds_sgdmn 不参加这道判据：它本质是「这个月有没有 IPO」的开关量，
# 实测合法环比最大 314 倍（2021-02 的 S$1mn → 2021-03 的 S$314mn），
# 与 1000 倍在统计上分不开，硬套只会制造假警报。
# 它并没有失去保护：_cell_num 的形状判据、_validate 自检 5 的整数兜底、
# 以及 _crosscheck_prev_month 的上月列核对都照常覆盖这一列。
_SCALE_EXEMPT = {'ipo_funds_sgdmn'}


def _scale_typo_guard(mon, rec, prev_vals):
    """与上一个月相比出现 ~1000 倍量级跳变 —— 一律**拒绝入库并点名**，不自动修正。

    这道判据补的是 _cell_num 看不见的那一类：_cell_num 认的是 **token 的形状**
    （`923.134` 一眼就知道该读成 923,134），凡是形状能自证的它当场修掉；
    但同样「小了三个数量级」的错也可以由别的根因造成，而那时 token 本身完全正常 ——
    2020-03 外汇表把 USD_CNH 写成 1,990（真值 1,255,507，见 _ERRATA）就是这样，
    `1,990` 是个再普通不过的数字，形状判据永远看不出问题。

    **为什么这里选「拒绝入库」而不是「自动修正」**（本模块两种处置并存，分界线就在这里）：
      · _cell_num 敢修，是因为 token 的形状把读法**唯一确定**了 —— 千分位分组里
        出现一个小数点，除了「逗号排成了点」没有第二种解释，修出来的数不是猜的。
      · 这里不敢修，是因为判据只给出「差了大约 1000 倍」，方向和倍数都得靠赌：
        是除了 1000 还是乘了 1000？是 1000 还是 631（USD_CNH 那处的真实倍数）？
        赌错的产物是一个**编出来的、看上去完全正常的数字**，
        而这正是本模块从头到尾最忌讳的那类错误。
      · 更要紧的是「真的塌了 1000 倍」并非不可能：合约停做、产品线迁走、口径拆分，
        都能让某一列在一个月里掉三个数量级。自动修正会把这种**真实的**断崖
        悄悄抹成一条平滑的线，事后谁也无法从数据里看出发生过什么。
      · 拒绝入库的代价只是「这个月没进来、红点亮着、日志点了名」，
        一次人工核对就了结；而核对的结论会以 _ERRATA 的形式**带着证据留在代码里**，
        下次任何人都能复查。宁可停更一个月，不可静默写错一格。
    """
    if not prev_vals:
        return
    for c in DATA_COLUMNS:
        if c in _SCALE_EXEMPT:
            continue
        v, u = rec.get(c), prev_vals.get(c)
        if not v or not u:                   # 0 与 None 都没有比值可言
            continue
        r = u / v
        if not (_SCALE_LO <= r <= _SCALE_HI or _SCALE_LO <= 1 / r <= _SCALE_HI):
            continue
        raise SgxFetchError(
            '%s %s = %s，与上月的 %s 差 %.0f 倍 —— 这个量级的月环比在全部 138 期里'
            '从未出现过（除 ipo_funds_sgdmn 外历史最大环比只有 7.8 倍），'
            '几乎肯定是官方把千分位排错了位、或表格标签错开了行。'
            '本模块不猜真值：请人工核对官方 PDF，确认后把这一格连同证据写进 _ERRATA，'
            '再重跑。拒绝写入。' % (mon, c, _fmt(v), _fmt(u), max(r, 1 / r)))


def _prev_month(mon):
    y, m = int(mon[:4]), int(mon[5:])
    return '%04d-%02d' % (y - 1, 12) if m == 1 else '%04d-%02d' % (y, m - 1)


def _row_floats(row, idx):
    """CSV 的一行 -> {列名: float}。空格与认不出的写法一律略过（缺参照只是少一次核对，
    不该让护栏自己变成失败点）。"""
    out = {}
    for c in DATA_COLUMNS:
        s = (row[idx[c]] or '').strip()
        if not s:
            continue
        try:
            out[c] = float(s)
        except ValueError:
            continue
    return out


def _backfill_gaps(body, idx, index, cache_dir):
    """把**已经在库**的行里「该有值却是空格」的列补上。只填空，绝不覆盖。

    为什么必须有这一段（而不是把 FIRST_MONTH 一改就完事）：`update()` 的既定契约是
    「已在 CSV 里的月份不重新下载、不重新解析」，所以 FIRST_MONTH 往前挪、
    或者新加一条兜底解析路（口径坑 18 的 p8）之后，**老月份永远不会被再看一眼** ——
    改了跟没改一样，而且看上去像是生效了。这里是唯一能让那些空格长回来的地方。
    照 fetch/mtk.py 的「历史回补分支」办：让抓取器自己能长回去，
    而不是靠一次性脚本手工贴数（手工贴的数下个月没人能复算）。

    判据完全复用 `_missing_columns`：一格该不该有值由 FIRST_MONTH / LAST_MONTH 说了算，
    这里不另立一套。于是**下一次有人把某列的 FIRST_MONTH 往前挪，这条路自动生效**。

    三条硬约束：
      · **只填空**。CSV 里已经有字符的格一律不动 —— 官方顺延调整（口径坑 9）
        与重述由人决定，不由这段代码代劳。
      · **整月过 _validate 才落一格**。补进来的值来自一次完整的重新解析，
        所以顺手让它过一遍全套自检（分项和、跨页核对、整数兜底…）；不过就整月放弃、
        只告警。**这道自检失败绝不能把整次 update 拖垮** —— 它是补历史的，
        而当月增量才是主线。
      · **顺手做一次解析回归**：重新解析出来的值与库里已有值不等时点名。
        同一份 PDF、同一个解析器，理应逐格相同；不同就只有两种可能 ——
        官方重发了这一期，或者解析器变形了。两种都该有人看一眼，都不该静默。

    幂等：补完之后这些格不再为空，下次跑连 PDF 都不会下（`_fetch_report` 还有 cache）。
    """
    filled = []
    for row in body:
        mon = row[0]
        if mon < START_MONTH or mon not in index:
            continue
        known = _row_floats(row, idx)
        miss = _missing_columns(mon, {c: known.get(c) for c in DATA_COLUMNS})
        if not miss:
            continue
        path, _lm = _fetch_report(cache_dir, mon, index[mon])
        try:
            rec = _apply_errata(mon, parse_report(path, mon))
            rec = _fill_from_next(rec, mon, index, cache_dir)
            _validate(mon, rec)
        except SgxFetchError as e:
            sys.stderr.write('[sgx] ⚠ %s 的历史回补没跑通（%s）—— 这一行保持原样，'
                             '当月增量不受影响\n' % (mon, e))
            continue
        for c in DATA_COLUMNS:
            v, old = rec.get(c), known.get(c)
            if old is not None:
                if v is not None and abs(v - old) > max(0.5, 1e-9 * abs(old)):
                    sys.stderr.write(
                        '[sgx] ⚠ %s %s：重新解析得到 %s，库里是 %s —— 官方重发了这一期，'
                        '还是解析器变形了？本模块不覆盖已有值，请人工确认\n'
                        % (mon, c, _fmt(v), _fmt(old)))
                continue
            if c not in miss or v is None:
                continue
            row[idx[c]] = _fmt(v)
            filled.append('%s %s=%s' % (mon, c, _fmt(v)))
    if filled:
        sys.stderr.write('[sgx] 历史回补：填空 %d 格（只填空、不覆盖）——\n  %s\n'
                         % (len(filled), '\n  '.join(filled)))
    return filled


def _crosscheck_prev_month(path, mon, prev_mon, prev_vals):
    """常驻护栏：本期报告印的「上月」列，必须等于上一期报告印的「本月」列。

    每期 PDF 都白送一列上月数（表头固定是 `... M-2 | M-1 | M0 ...`），
    不核就是把一道免费的、覆盖全部 32 列的交叉校验扔掉。

    **只告警、不拒绝、更不覆盖** —— 照 fetch/spgi.py 那段重述体检的既有做法：
    官方事后小幅调整证券成交额是**明说过的合法行为**（口径坑 9，p3 脚注），
    改写历史必须由人决定，模块无权代劳；而「已有值永不覆盖」是本仓的硬规矩。
    但也绝不能静默 —— 不留痕的话，官方哪天把某一列整体重述，看板会在没人察觉的情况下
    同时挂着新旧两代口径。

    全 138 期实测 78 处不等，量级分布本身就是使用说明：
      · 绝大多数在 ±1 ~ ±1000，是官方顺延调整（成交额、募资额、上市/退市家数）；
      · 少数几处是真问题，且都被这道校验第一时间抓住 ——
        2016-07 债券募资的千分位错印（18.995 vs 18,995）、
        2020-03 外汇表的标签错位（USD_CNH 1,990 vs 1,255,507）、
        2021-01 期 p14/p15 表头没跟着数据一起更新（数据是 11/12/1 月，表头还写着 10/11/12 月）。
    所以判据不设阈值：**任何不等都点名**，把「这是重述还是错」的判断留给读日志的人。
    倍数达到 ~1000 的额外加一句提示 —— 那一类基本不可能是重述。

    自身失败也只告警：这是一道**监督**护栏，不能让它变成新的失败模式。
    上一期报告本来就可能有解析不了的小节（实测 2015-12 期读不出 2015-11 的上市家数）。
    """
    if not prev_vals:
        return []
    try:
        alt = parse_report(path, prev_mon)
    except SgxFetchError as e:
        sys.stderr.write('[sgx] ⚠ %s 期的「上月列」交叉校验没跑起来（%s）—— '
                         '本月数据照常入库，但这一次核对缺席\n' % (mon, e))
        return []
    hits = []
    for c in DATA_COLUMNS:
        a, b = alt.get(c), prev_vals.get(c)
        if a is None or b is None:
            continue
        if abs(a - b) <= max(0.5, 1e-9 * abs(b)):
            continue
        note = ''
        if a and b and (100 <= abs(b / a) <= 10000 or 100 <= abs(a / b) <= 10000):
            note = ' ←【差约 1000 倍，这不像重述，像千分位错印或标签错行，请优先核】'
        hits.append((c, b, a))
        sys.stderr.write('[sgx] ⚠ %s 期印的 %s 列 %s = %s，而 %s 期自己印的是 %s —— '
                         '官方重述？本模块不改历史，请人工确认%s\n'
                         % (mon, prev_mon, c, _fmt(a), prev_mon, _fmt(b), note))
    return hits


def _validate(mon, rec, prev_vals=None):
    """缺列一律失败（README 护栏 2），再跑三道算术自检。

    这三道自检的价值在于：它们能抓住「解析没报错、但取到了隔壁一行/隔壁一页」这种
    最难发现的错误 —— 数字仍然是从官方 PDF 里读出来的真数字，只是配错了地方。

    容差不是「为了让它过」而设的，是照**官方自己的口径不一致幅度**定的，
    全语料 138 期实测：分项和 vs 同节 Total 有 136 期逐位相等，2018-08 差 5、2023-06 差 1；
    At-A-Glance vs 分节 Total 有 137 期逐位相等，2020-11 差 91（0.0005%，官方两页自己打架）。
    容差取得比这些偏差略大、又远小于「错一行/错一列」会造成的偏差（那是十万到百万量级），
    所以既不会误杀，也不会放过真错误。
    """
    missing = _missing_columns(mon, rec)
    if missing:
        raise SgxFetchError('%s 解析后仍为空的列：%s —— 官方表结构可能已变，拒绝写入'
                            % (mon, missing))

    # 自检 1：证券侧是自洽的（成交额 / 交易日 = SDAV，两者都是四舍五入到整数 $Million，
    # 所以允许 ±1）。取错行或错列时这个恒等式立刻破。
    val, days, sdav = rec['sec_turnover_sgdmn'], rec['sec_trading_days'], rec['sdav_sgdmn']
    if days and abs(val / days - sdav) > 1.0:
        raise SgxFetchError('%s 证券侧对不上：成交额 %s / 交易日 %s = %.1f，'
                            'At-A-Glance 的 SDAV 却是 %s —— 多半取错行或错列'
                            % (mon, val, days, val / days, sdav))
    # 自检 2：期货+期权+掉期 = 该节自己印的 Total Trading Volume（实测 138 期逐位相等），
    # 且它又必须等于 At-A-Glance 那一页的 Derivatives Volume —— 后者是**跨页**核对，
    # 能抓住「整节定位偏了一页」这种解析器最容易犯又最难看出来的错。
    # 注意**不能**拿 总量/交易日 去核 DDAV：交易日是证券市场的，见口径坑 6。
    parts = (rec['deriv_futures_vol_contracts'] + rec['deriv_options_vol_contracts']
             + rec['deriv_swaps_vol_contracts'])
    sect = rec['deriv_vol_total_check']
    if abs(parts - sect) > max(10.0, 1e-6 * sect):
        raise SgxFetchError('%s 衍生品分项对不上：期货+期权+掉期 = %.0f，'
                            '而同节的 Total Trading Volume = %s' % (mon, parts, sect))
    if abs(sect - rec['deriv_vol_contracts']) > max(100.0, 1e-5 * sect):
        raise SgxFetchError('%s 跨页对不上：Derivatives Overall 节的 Total Trading Volume = %s，'
                            '而 At-A-Glance 的 Derivatives Volume = %s'
                            % (mon, sect, rec['deriv_vol_contracts']))
    # 自检 3：商品合计是若干小节 Total 之和，铁矿石是其中一部分，前者不可能小于后者。
    # 官方哪天新开一个商品小节而白名单没跟上，这里会先炸，而不是悄悄少算。
    iron, comm = rec['vol_iron_ore_contracts'], rec['vol_commodities_contracts']
    if iron is not None and comm is not None and iron > comm + 0.5:
        raise SgxFetchError('%s 商品合计 %s 小于铁矿石合计 %s —— 商品小节白名单该更新了'
                            % (mon, comm, iron))
    # 自检 4：入库的单品不可能大于它自己所在小节的合计。
    # _total_is_shifted 已在解析层拦掉「Total 标签错位到某个分项上」的情形，
    # 但那道检查只在错位后的值**偏小**时成立；万一哪天错位落到一个更大的行上，
    # 这里是最后一道网。全部 138 期实测：修好 2020-03 之后无一命中（零误杀）。
    for total_col, sub_cols in (
        ('vol_fx_futures_contracts',
         ('vol_usdcnh_futures_contracts', 'vol_inrusd_futures_contracts')),
        ('vol_equity_index_futures_contracts',
         ('vol_a50_futures_contracts', 'vol_nikkei225_futures_contracts',
          'vol_nifty50_futures_contracts', 'vol_msci_singapore_futures_contracts',
          'vol_msci_taiwan_futures_contracts', 'vol_ftse_taiwan_futures_contracts')),
    ):
        tot = rec.get(total_col)
        subs = sum(v for c in sub_cols for v in [rec.get(c)] if v is not None)
        if tot is not None and subs > tot + 0.5:
            raise SgxFetchError('%s %s = %s，却小于它自己的分项之和 %s —— '
                                '多半是官方漏印行标签导致整列标签上移一格'
                                % (mon, total_col, tot, subs))
    # 自检 5：入库字段官方印的**全是整数**（张数、只数、家数、四舍五入到整数的 $Million），
    # 138 期逐格实测无一例外。_cell_num 已经修掉「千分位逗号排成小数点」那一种错印
    # （口径坑 15），这里是换个形状的错印落网的地方 —— 比如点落在别的位数上。
    # 这类值的特征是「本身完全合法、只是差了 10^n 倍」，图上就是一根扎到底的针，
    # 没有这道检查谁也看不出来。宁可整月拒收让人来看，也不要写一个缩水一千倍的数。
    # turnover_velocity_pct 例外：它是百分数，官方哪天印成 38.5% 是合法披露不是错印
    # （带 % 号的单元格也天然不会被 _cell_num 的错印判据命中）。
    for c in DATA_COLUMNS:
        v = rec.get(c)
        if v is None or c == 'turnover_velocity_pct':
            continue
        if float(v) != int(float(v)):
            raise SgxFetchError('%s %s = %r 不是整数 —— 官方这张表的入库字段一律是整数，'
                                '多半又是一处排版错印（见口径坑 15），拒绝写入'
                                % (mon, c, v))
    # 自检 6：与上一个月比的 ~1000 倍量级跳变。自检 5 认的是 token 形状，
    # 这一道认的是**量级**，两者互补 —— 形状正常但小了三个数量级的错（标签错行）
    # 只有这一道拦得住。拒绝入库而不自动修正，理由写在 _scale_typo_guard 里。
    _scale_typo_guard(mon, rec, prev_vals)
    return rec


# ══ 发布日 ═══════════════════════════════════════════════════════════════
def _next_month(mon):
    y, m = int(mon[:4]), int(mon[5:])
    return '%04d-%02d' % (y + 1, 1) if m == 12 else '%04d-%02d' % (y, m + 1)


def _fill_from_next(rec, mon, index, cache_dir):
    """本期报告里读不到的字段，拿**下一期**报告去补 —— 因为每期都带 M-2 / M-1 两列。

    为什么需要这条路：官方会发出**夹带上一期陈旧页**的报告。实测 2021-01 那期的
    第 14、15 页（股指期货表的后半截）整版还是 2020-12 那期的内容 ——
    表头写着 `Oct 2020 | Nov 2020 | Dec 2020`，根本没有 Jan 2021 这一列。
    受影响的是 Nikkei、MSCI Singapore、MSCI Taiwan 与股指期货合计四个字段；
    A50 在第 12 页（正常）、At-A-Glance 在第 2 页（正常）。
    没有这条回补路，整个 2021-01 会因为 4 个字段而丢掉另外 28 个好字段。

    补进来的仍然是**官方对同一个数据月的披露**，只是发布得晚一期 ——
    2021-02 那期的 Jan-2021 列给出 Nifty 1,898,333，与 2021-01 那期陈旧页上
    Dec-2020 位置印的数字**不是**同一个，说明补的确实是正确的那一列。

    只补「本期为空」的格，绝不覆盖本期已有的值：下一期报告里那两列可能已经被重述过，
    而本仓的规矩是已有值永不覆盖（口径坑 9）。
    下一期还没发布（当月）时什么都不做，让缺列护栏照常拦下 —— 数据确实还不存在。
    """
    miss = _missing_columns(mon, rec)
    nxt = _next_month(mon)
    if not miss or nxt not in index:
        return rec
    path, _lm = _fetch_report(cache_dir, nxt, index[nxt])
    alt = parse_report(path, mon)        # 用下一期的 PDF，读的仍是 mon 那一列
    for c in miss:
        if alt.get(c) is not None:
            rec[c] = alt[c]
    return rec


def _source_dates():
    """按路径加载仓库根的 source_dates.py（本模块被 spec_from_file_location 加载，
    那时 sys.path 上既没有 fetch/ 也没有仓库根，裸 import 会失败）。"""
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(root, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _publish_date(mon, lastmod, meta):
    """这一期的发布日，返回 ('YYYY-MM-DD', 出处文字)；取不到返回 (None, None)。

    报告 PDF **自己不写发布日**（48 页全文扫过，没有 Updated on / Published / As at
    之类的字符串，末页只有免责声明），所以不能照抄 cboe 的 A2「Updated on」那套。
    可用的最权威机器可核字段就是 PDF 直链的 HTTP Last-Modified —— 官方服务器自己盖的戳，
    与本仓 hkex 的做法同源。

    ⚠ 但它**只对 2018-08 及之后的数据月可信**：更早的约 102 期返回的都是 2018 年
    站点迁移的时间戳（2010-02 / 2012-06 / 2015-01 / 2016-06 全返回 2018-08-21）。
    那些日期形式上完全合法、也确实晚于数据月末，`source_dates.record()` 的护栏拦不住，
    所以只能在这里按数据月硬闸掉。宁可让这半句缺席，也不要印一个像模像样的错日期。

    语义选的是「公众第一次能拿到数据那天」（= 网站上线），与本仓既有条目一致。
    同一份报告作为附件挂上 SGXNet 通常还要再晚 1~3 天（2026-06 期：网站 07-10、
    SGXNet 07-13；2026-04 期：网站 05-12、SGXNet 05-13），evidence 里写明这一点，
    免得日后有人拿新闻稿日期来对、以为算错了。
    """
    if not lastmod or mon < _LASTMOD_TRUSTED_FROM:
        return None, None
    try:
        d = datetime.datetime.strptime(lastmod, '%a, %d %b %Y %H:%M:%S %Z')
    except ValueError:
        return None, None              # 认不出格式就宁缺勿猜
    name = meta.get('name') or os.path.basename(urllib.parse.urlparse(meta['url']).path)
    return d.strftime('%Y-%m-%d'), (
        'PDF 直链（官方文件名「%s」）的 HTTP Last-Modified "%s"，取 GMT 日历日；'
        '语义是网站上线日（= 数据第一次可得），同一份报告挂上 SGXNet 通常再晚 1-3 天'
        % (name, lastmod))


# ══ 对外接口 ═════════════════════════════════════════════════════════════
def latest_month(cache_dir):
    """官方源当前最新月 'YYYY-MM'。只花 ①② 两个请求（约 87 KB），不下 PDF。

    抓不到 / 认不出来一律抛 SgxFetchError，不返回 None 掩盖故障。
    """
    return max(_report_index(cache_dir))


def _fmt(v):
    """整数写成整数（官方印的就是整数），非整数保留完整精度。"""
    if v is None:
        return ''
    v = float(v)
    return str(int(v)) if v.is_integer() else repr(v)


def update(series_dir, cache_dir):
    """把新月份追加进 series/sgx.csv，返回新增月份列表（升序）。

    幂等保证：
      · 已在 CSV 里的月份**不重新下载、不重新解析、不重写**（官方明说证券成交额会跨月
        顺延调整，见口径坑 9；重述不由本模块自动吞进来）；
      · 既有行原样字符串搬运，所以「没有新月份、也没有空格可补」时重跑，
        文件**字节级不变**；
      · 已有值永不覆盖 —— 本模块只写空格与新行，不改任何已经有字符的格。
    真要重刷历史，删掉对应行手工重跑。

    「已有值永不覆盖」的**唯一例外**是 _ERRATA 那张更正表：它装的是已经用官方 PDF
    逐条证死了的错印（每条都带证据），且只在单元格逐字节等于登记的错值时才改写。
    第一次跑改掉那几格、之后每次跑都是空操作，所以幂等仍然成立。
    这不是「自动吞重述」的口子 —— 重述走 _crosscheck_prev_month，只告警不改。

    「不改老行」的**唯一例外**是 _backfill_gaps：老行里那些「按 FIRST_MONTH 该有值、
    实际却是空格」的格会被补上（口径坑 18 的 38 个月换手率就是这么回来的）。
    它同样只写空格、不覆盖任何已有值，补完即为空操作，幂等成立。

    首次运行会把 2015-01 起的 138 期一次性补齐（约 80 MB / 数分钟），
    之后每月只下一期。cache/ 里的 PDF 与 .lastmod 边车文件会被复用。
    """
    csv_path = os.path.join(series_dir, 'sgx.csv')
    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    idx = {name: i for i, name in enumerate(header)}
    unknown = [c for c in DATA_COLUMNS if c not in idx]
    if unknown:
        raise SgxFetchError('series/sgx.csv 里没有这些列：%s' % unknown)

    have = {r[0]: r for r in body}

    # 已确证的官方错印：先把**早就入库**的那几格修好。放在这里而不是解析层，
    # 是因为那些月份永远不会再被解析一次（见 _repair_errata）。幂等。
    _repair_errata(body, idx)

    index = _report_index(cache_dir)

    # 历史回补：已在库的行里「该有值却是空格」的列。放在增量之前，
    # 这样当月那一行进来时 _crosscheck_prev_month 拿到的上月参照是补全后的。
    _backfill_gaps(body, idx, index, cache_dir)

    need = [m for m in sorted(index) if m >= START_MONTH and m not in have]

    added, pub = [], {}
    for mon in need:
        path, lastmod = _fetch_report(cache_dir, mon, index[mon])
        rec = _fill_from_next(parse_report(path, mon), mon, index, cache_dir)
        rec = _apply_errata(mon, rec)
        prev_mon = _prev_month(mon)
        prev_vals = _row_floats(have[prev_mon], idx) if prev_mon in have else None
        rec = _validate(mon, rec, prev_vals)
        # 上月列交叉校验放在 _validate 之后：本月自己都没通过时，没必要再报上月的差异。
        _crosscheck_prev_month(path, mon, prev_mon, prev_vals)
        row = [''] * len(header)
        row[0] = mon
        for c in DATA_COLUMNS:
            row[idx[c]] = _fmt(rec[c])
        body.append(row)
        have[mon] = row
        added.append(mon)
        day, evidence = _publish_date(mon, lastmod, index[mon])
        if day:
            pub[mon] = (day, evidence)

    body.sort(key=lambda r: r[0])
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        w.writerows(body)

    # 记发布日放在落盘之后：写盘失败就不该在台账上多出一行说「这个月官方发过了」。
    sd = _source_dates()
    for mon in sorted(pub):
        if sd.lookup(series_dir, 'sgx', mon):
            continue                     # 已有记录一律不覆盖
        day, evidence = pub[mon]
        sd.record(series_dir, 'sgx', mon, day, evidence)
    return sorted(added)


if __name__ == '__main__':
    _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print('latest:', latest_month(os.path.join(_here, 'cache')))
    print('added :', update(os.path.join(_here, 'series'),
                            os.path.join(_here, 'cache')))
