# -*- coding: utf-8 -*-
"""ASX Limited（澳大利亚证券交易所，ASX:ASX）月度经营指标 —— 无人值守抓取。

━━ 数据源 ━━
主源：**ASX Group Monthly Activity Report（MAR）**，ASX 按澳洲持续披露义务同时发给
ASIC 与自家 Market Announcements Office 的市场公告，地位等同美股 8-K Item 7.01。
首页抬头逐字写着 "ASX GROUP MONTHLY ACTIVITY REPORT – JULY 2026 /
Release of market announcement authorised by: Andrew Tobin, Chief Financial Officer"。

  索引页（cron 唯一入口）
      https://www.asx.com.au/about/media-centre
      一次 GET 拿到整页 494 条 PDF href（服务端渲染，无分页、无 JS），其中 80 条是 MAR，
      覆盖 2020-02 → 至今 78 个月 + 2 份更正稿。
  PDF 直链（同域 DAM，无中转页）
      https://www.asx.com.au/content/dam/asx/about/media-releases/{YYYY}/{...}-{month}-{YYYY}.pdf

历史回补源（**cron 不走**，见下）：ASX 自家公告存档
      列表  .../asx/v2/statistics/announcements.do?by=asxCode&asxCode=asx&timeframe=Y&year=YYYY
      中转  .../asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId={idsId}
      直链  https://announcements.asx.com.au/asxpdf/{YYYYMMDD}/pdf/{hash}.pdf
实测 2009-12 → 2026-07 共 211 个月、只缺 2009-05。技术上纯 GET 可通（中转页的
`<input name="pdfURL">` 隐藏字段直接写出真实直链，不需要 POST、不需要 cookie），
但那一页是一张**「点击即接受使用条款」的同意表单**——让 cron 每月自动穿过它是策略问题，
不是技术问题。所以本模块把两条路分开：

  · `update()` / `latest_month()`（cron 跑的）**只走媒体中心**，全程不碰同意页；
  · 历史一次性回补走 `python3 fetch/asx.py --backfill 2016-01 2020-01`，**人工跑**。
    series/asx.csv 里 2020-01 及更早的行就是这样来的，之后再没人需要跑它。
    （2026-08：起点由 2017-10 前推到 2016-01，跑的就是 `--backfill 2016-01 2017-09`
    这一次；理由与实测记录见下方 `SERIES_START`。）

裸 `urllib`（默认 Python-urllib UA、零 header）对三个入口全部 200：无 Cloudflare、
无 Akamai、无 JS 渲染、无登录墙、不校验 UA。满足无人值守。

辅源（分品种）：Monthly SFE Trading Report，**官方一直留着，可回补到 2020-06**
      https://www.asx.com.au/content/dam/asx/documents/unlinked-docs/…（命名见口径坑 22）
这份报告的链接**印在 MAR 正文的期货段末尾**（第 3–4 页，"Volume of futures trading by
individual contract is available at the following link:"），所以不用猜文件名，跟着 MAR 走。
它是 SPI 200 / 3 年期国债 / 10 年期国债 / 90 日银行票据分品种月度成交与未平仓的
唯一官方月度来源（MAR 本身只给期货合计，不拆品种）。
**天花板 2020-06**，判据是**链接指向哪个目录**，不是「多久以前」：
  · 2019-12…2020-05 的 MAR 指向老站点路径 `/data/market-reports/…`，
    该路径今天整体 302 到 `content/asx/404.html`（200 + text/html，soft-404，口径坑 2）；
  · 2020-06 起指向 DAM（`/content/dam/asx/documents/unlinked-docs/…`），2026-08 逐月实发
    72/72（2020-06…2026-05）全部 200 + application/pdf + `%PDF-`，且用**未改动的**
    `parse_sfe` 全部解析成功；
  · 2016-09…2019-11 的 MAR 也印链接，同样是老站点路径 ⇒ 同样 soft-404；
    2016-01…2016-08 的 MAR 正文里根本没有这条链接。
「只有最近 2 期 / 历史不可回补」是 2026-08 之前记在这里的结论，**已被上面这轮实发推翻**，
成因见口径坑 22 —— 它是抓取器的文件名正则太窄，不是官方撤了历史。
`update()` 只对 `mon >= SFE_START` 的月份发这一次请求；历史一次性回补走
`python3 fetch/asx.py --sfe-backfill 2020-06 2026-05`（**同样只走媒体中心，不碰同意页**）。

━━ 发布节奏 ━━
次月第 3–8 个日历日，众数第 5–6 日，悉尼时间 8:30–9:30 am 上市场。
211 期公告时间戳的日分布（本模块开发时从存档页统计）：
    第 3 天 33 ｜ 第 4 天 40 ｜ 第 5 天 58 ｜ 第 6 天 63 ｜ 第 7 天 13 ｜ 第 8 天 3
另有 1 期落在第 20 天，那是 2022-06 的**更正稿**，不是首发。
**没有季末月特殊性**：ASX 财年 6 月底结束，但 6 月的月报照常次月初发
（2025-06 → 2025-07-04；2026-06 → 2026-07-06）。⇒ `build/roster.py` 的 LAG 两档同为 (8, 8)。

发布日只认**PDF 首页正文第一行 ASX 自己写的那个日期**（"6 August 2026"），记进
series/source_dates.csv。不用 HTTP Last-Modified：DAM 副本比公告晚约 30 分钟上传
（公告 8:40 am，DAM 9:10 am AEST），跨日就会错一天；也不用文件名里的日期，
2020–2021 那批文件名根本不带发布日，2021 起带的那个前缀数字是**日历年内公告序号**
（`43-06-august-2026-…` 的 43 与数据月无关）。

━━ 口径坑（按踩坑概率排序）━━
1. **同名诱饵：ASX Compliance Monthly Activity Report。** 2010-08 → 2016-06 共 71 个月，
   ASX 每月同一天发两份标题几乎相同的公告，idsId 相邻：
       01754741  ASX Group      Monthly Activity Report - June 2016   7 pages
       01754742  ASX Compliance Monthly Activity Report - June 2016   5 pages   ← 诱饵
   Compliance 版里有 "Listed entities at month end 2,204" 这种**完全合法、看上去正确**
   的数字，但整份**没有任何成交数据**。按 `'Monthly Activity' in title` 匹配必然中招，
   而中招的表现是「上市实体数对，成交全空」，不报错。⇒ 发现逻辑一律 `'compliance' not in
   title.lower()`（见 `_ARCHIVE_SKIP`），且解析后断言必填列齐全（见 `_validate`）。
   媒体中心那条路天然不含 Compliance 版，但存档回补那条路每个月都会撞上。

2. **soft-404：HTTP 200 + text/html 的假成功。** 2024 年代 MAR 正文里印的旧版分品种直链
   `https://www.asx.com.au/data/market-reports/MonthlyFuturesMarketsReport{YYMMDD}.pdf`
   返回 **200 + text/html + 恒定 136,750 字节的错误页**，不是 404。实测 `200228` /
   `190228` / `160630` / `170428` / `240731` 五个日期字节数完全相同。
   任何 `if status == 200: save()` 都会把 HTML 错误页当 PDF 存下来，然后在解析阶段
   报一个跟真实原因毫无关系的错。⇒ `_http_pdf()` **同时**校验 Content-Type 为
   application/pdf 且首 5 字节为 `%PDF-`，两条缺一不可。
   （新版 `unlinked-docs/monthly-futures-markets-report-*.pdf` 是真 404，行为不一样，
   所以「我试过没问题」这种经验在这里是靠不住的。）

3. **绝不能按 `Average daily contracts` 的出现序号取值。** 同一份 PDF 里这个行名出现
   5 次（2020 版起：期货 / 期货期权 / 期货合计 / 单股期权 / 指数期权）或 **6 次**
   （2015-09 – 2017 版多一行 `Total options volume` 的合计 ADV，实测 2016-06 = 418,112
   ≈ 347,474 + 70,639）。次数会变，序号法必然在某一代版式上整体串位，而**串出来的每个数
   都是合法数字**。⇒ 一律先用大标题（`Trading – Futures` / `Trading – Equity Options`）
   切 section，再用小标题（`Futures volume` / `Options on futures volume` / …）切 subsection，
   最后才查行名。见 `_SECTIONS` / `_SUBSECTIONS` / `COLUMN_SPEC`。

4. **列数按行变，不按报告变。** 8 月至次年 6 月的报告，流量行有 4 列
   `[本月, 去年同月, 本财年 YTD, 去年同期 YTD]`；时点行（listed entities / CHESS / margins）
   只有 2 列；而 **7 月**那一期因为财年 YTD ≡ 本月，官方直接把后两列删掉，整份只有 2 列。
   实测同一份 2016-06 报告：`Secondary capital raised` → [1726, 5083, 45299, 38787]，
   `Total Listed entities` → [2204, 2220]。
   ⇒ 只能取「值列里从左数第 1 个数字」。「取最后一列」「按列数判断版式代际」都会在某个月炸。

5. **竖排水印 "For personal use only" 会污染标签。** pymupdf 把这四个词按 y 坐标并进
   任意一行的词流，实测把 `Total notional cleared value ($billion)¹` 变成
   `For Total notional cleared value ($billion)¹`，前缀锚定的正则直接失配。
   ⇒ `_page_rows()` 按词过滤 `for|personal|use|only`（`_WATERMARK`）。

6. **标签里有数字，所以不能全行扫数字。** `S&P/ASX 200 VIX (average daily value) 11.3 11.3`
   全行扫会把「本月值」读成 200；夹在标签与数值之间的括号说明同样含数字
   （`(includes interest rate, ASX SPI 200, commodities and energy contracts)`），
   所以连「跳过无数字的行」都救不了。⇒ 按**页宽比例**切值列左边界：`_NUMCUT = 0.47`。
   实测 2015–2026 全部版式都成立（值列 x 起点：2016 版 ~287，2024/2026 版 ~426；
   标签词 x 起点最远 ~262）。

7. **标签与数值经常不在同一「阅读顺序行」上，得靠 y 坐标聚类 + 续行前瞻。** 三种实测形态：
     · 2016 版：`Total trading days` 单独一行，值挂在下一行的括号说明上
       （`(Cash market includes … market  21  21  254  254`）；
     · 2016 版：`Value of CHESS holdings – period end` / 值 / `($billion)` 三行，值在中间那行；
     · 2024 版：`Total trading days` 行自带值，括号说明在**下面**。
   ⇒ 标签行没有值时，向下前瞻至多 2 行，且只接受「标签区为空 / 以 `(` 开头 / 以小写字母
   开头」的续行——正文行与下一个指标的标签都是大写开头，不会被误吃。

8. **脚注标记有三种形态，还会出现在标签中段。** 2026 版是上标 Unicode `¹`，2024 版是
   **普通 ASCII 数字直接粘在标签后**（`Total notional cleared value ($billion)1`），
   2016 版是 `*` 且在中段（`Total notional cleared value* ($billion)`）。
   只剥尾部记号救不了 2016 版。⇒ `_key()` 全串删 `*¹²³†‡`，再剥尾部 ASCII 数字。

9. **单位后缀会换行掉队，所以它不能参与匹配。** 同一个指标，131 个月里 13 个月的标签是
   `Total billable cash market value cleared`、118 个月是 `…cleared ($billion)`
   （`($billion)` 换到了下一行，落在标签区之外）。CHESS 22/109、Austraclear 34/97、
   `Other capital raised including scrip-for-scrip` 12/119 都是同一回事。
   ⇒ `_key()` 统一剥掉尾部单位括号 `($billion)` `($million)` `($)` `(million)`
   `(at end of month)`，剥完两边才对得上。

10. **Listings 段在 2023-10 换过定义，不是换名字 —— 两套口径必须分列存。**
      · …2023-09：`Initial capital raised ($million)`（IPO **实际募资额**）
                  `Total capital raised including other ($million)`
      · 2023-10 ：`Quoted market capital of new listings`（**无 -isation**，仅此一月）
                  `Total initial and secondary capital quoted`（第三种写法，2023-10/11 两月）
      · 2023-11+：`Quoted market capitalisation of new listings ($million)`
      · 2023-12+：`Total new capital quoted ($million)`
    「IPO 募到多少钱」与「新上市实体挂牌市值多少」差 6 倍（FY26 官方新闻稿同时给出
    IPO capital raised $5.6bn 与 new listings added $32.6bn in quoted market capitalisation）。
    ⇒ 本模块给它们**两组独立列**：`capital_initial_raised_audmn` /
    `capital_total_raised_incl_other_audmn`（老口径，2023-09 止）与
    `mktcap_new_listings_audmn` / `capital_new_quoted_audmn`（新口径，2023-10 起）。
    画图时在 2023-10 打结构性断点红线；**同一列里连起来画就是编数据**。

11. **`Total secondary capital raised` ≠ 新闻稿说的 follow-on。**
    MAR 里 `Total secondary = Secondary capital raised + Other capital raised including
    scrip-for-scrip`。FY26 实测：窄口径 $37.849bn（新闻稿 "raised $37.8 billion in
    follow-on capital during FY26" ✅），含换股对价 $58.428bn。
    ⇒ 三列都存（`capital_secondary_audmn` / `capital_other_scrip_audmn` /
    `capital_secondary_total_audmn`），只存合计必然对不上任何一份官方文本。

12. **OTC 名义额是双边计数。** 官方脚注逐字写着 "Cleared notional value is double sided"。
    与 CME / LCH 的单边惯例不同，跨家比之前必须先统一，否则 ASX 凭空大一倍。
    `otc_notional_cleared_audbn` 是**当月流量**，`otc_open_notional_audbn` 是**月末存量**，
    两者都是双边。

13. **三套交易日数经常不等**：cash / futures / ETO。2026-04 实测 19 / 20 / 19。
    用 `ADV × 交易日` 反推月度总量时配错就整月偏 5%。所以三个都存
    （`trading_days_cash` / `trading_days_futures` / `trading_days_eto`），
    而且**每一类的月度总张数本模块也照原样存**，下游根本不需要自己乘。

14. **ASX 现货 ≠ 澳洲现货全市场。** Cboe Australia（原 Chi-X）的成交不在 MAR 里。
    本仓横截面页若只用 MAR，口径是「ASX 自身经营量」而不是「澳洲市场量」，图注要写明。
    另外 `value_tradereport_audbn` 是**场外成交事后向 ASX 报告**的金额，不是 ASX 撮合量；
    `adt_cash_onmarket_audbn`（不含它）才是与 HKEX `adt_hkdbn` 同概念的那个数。

15. **`On-market value` 这一行 2017-10 才出现，早期是真缺失，不是解析失败。**
    2015-09 – 2017-09 的现货段行名与现在**全部不同**（纯改名，定义没变，已用
    Open+Auctions+CentrePoint+TradeReporting = Total 的恒等式验证）：
        `Total value ($billion)`                → `Total cash market value ($billion)`
        `Average daily value on-market ($bn)`   → `On-market average daily value ($bn)`
        `Average daily value ($billion)`        → `Total average daily value ($billion)`
    唯独 `On-market value`（当月 on-market 成交额）2017-10 之前**官方没印过**。
    2026-08 复核：2016-01…2017-09 共 21 期缓存 PDF 逐期扫过行名，`On-market value`
    一次都没出现，而同期 `Total value` / `Average daily value on-market` 21/21 都在
    ⇒ **是源头没印，不是解析器没认出来**，`since='2017-10'` 是对的。
    另外 `Total cash margins held on balance sheet` 行 **2019-10** 才出现
    （2019-09 及更早只逐项印 `- ASX Clear` / `- ASX Clear (Futures)` /
    `Cash equivalents…`，没有合计行，44 期逐期核过），
    `Entities de-listed` 等三行 **2024-05** 才出现（旧行一行没停 ⇒ 是新增不是切换），
    上市融资在 **2023-10**、保证金在 **2024-08** 是**旧列停印 + 新列开印**的同期切换
    （2023-09/2023-10 与 2024-07/2024-08 四期逐期核过）。
    ⇒ 每一列都带 `since`/`until` 月份边界（`COLUMN_SPEC`），越界为空是合法的，
    界内为空一律抛异常。
    2026-08 起点前推到 2016-01 之后，这些 `since` 全都落在 series 内部，于是**同一张图上
    会出现起点不同的两条线**：现货成交额那张图里「含场外报告」自 2016-01、「仅场内」自
    2017-10；参与者数那两列自 2016-07 —— 2016-01…2016-06 的 MAR 正文到 SETTLEMENT 段
    就结束了（共 6 页），**整个 PARTICIPANTS 段都不存在**，那时参与者数印在**另发的
    ASX Compliance activity report** 里（2016-02…2016-05 期 MAR 末页明写
    "A separate ASX Compliance activity report … has also been released today"）；
    2016-07 那一期起 MAR 并入 LISTINGS COMPLIANCE ACTIVITY / PARTICIPANTS /
    ENFORCEMENT 三段，这一行才有。6 期逐期核过，不只抽查 2016-01 / 2016-06。
    这是官方披露起点的差异，**不是数据缺失**，更不许用 open+auctions+centre point
    相加去把 `value_cash_onmarket_audbn` 倒推补齐（2017-09 实测能算出 80.829，与官方
    2017-10 的 80.296 量级一致 —— 但那是派生量，写进 series 就分不清哪个是官方印的）。
    ⚠ **`vix_asx200_avg` 是这条规矩的例外，而且是唯一的例外** —— 那个数在 2019-10
    之前虽然不是表行，却**印在同一份公告的正文要点里**，所以它不属于「源头未印」，
    见下面口径坑 21。别把「表里没这一行」直接当成「官方没发这个数」。

16. **2017-04 那一期 PDF 的期货期权小块整体错行 —— 值印在纸上，但挂在了错误的标签上。**
    实测该页（第 3 页）逐条基线，是**官方排版**错了，不是 pymupdf 的阅读顺序问题：
        y=374.23  `Options on futures volume`（小标题）＋ 124,649 / 144,826 / 1,142,509 / 1,589,153
        y=387.55  `Total contracts`                  ＋ -14% / -28%
        y=400.99  `Change on pcp`                    ＋ 6,925 / 6,896 / 5,415 / 7,461
        y=414.43  `Average daily contracts`          ＋ 什么都没有
    四行的值整体落在自己标签的**上一行**。对照 2017-03 / 2017-05 同一段：小标题行空、
    `Total contracts` 带值 —— 版式没变，是这一期排的。
    **本模块把它还原，但只搬不算。** `_shifted_blocks()` 认签名（两条都要满足）：
      ① 小标题行**带值** —— 小标题在健康报告里永远是纯文字，带值本身就是物证。
         实测 127 期全段扫描只此 1 处（另有 `Change on pcp` 带值 610 处，2024-11 起
         那一代版式去掉了百分号，是**常态**，所以单靠 ② 判会误伤，必须 ① 打头）；
      ② 本该带值的末行 `Average daily contracts` **整行为空**。
    认出后把值搬回它本该挂的标签，搬回来的每一格**先过 `_identity_gate()` 再入库**，
    撞的是官方在同一张表里自己印出来的合计：
        8,901,810 + 124,649 = 9,026,459 ✔（残差 0）
          494,545 +   6,925 =   501,470 ✔（残差 0）
    ⇒ **入库的是官方原值，不是恒等式反推值**：124,649 与 6,925 就印在上面那两条基线上，
    恒等式在这里当验钞机（证明搬对了标签），不当计算器。闸门任一条不过就退回留空、
    打印原因，绝不硬写；`_KNOWN_SOURCE_GAPS` 里那两条登记保留为兜底，所以退回时
    `_validate` 不会炸整月。回归实测：127 期 × 逐格 5,210 格，改动前后只有这 2 格变化。
    另注：错行错到值列直接落空时（本期还原前就是这样），拦下它的是 `_validate` 的缺列
    异常而不是恒等式 —— 恒等式管的是另一种病：**每个格子都有数、但装错了格子**
    （见 `_check_identities`）。两道闸门各守一边。

17. **同月有更正稿时必须用更正稿，且要跳过第 1 页。** 更正稿第 1 页是
    「Incorrect figure / Correct figure」对照表，**错值就印在第 1 页上**
    （2025-01 的 `Centre Point ($billion) 9.548` 是错值，正确值 8.852）。
    不跳第 1 页就会把错值当本月值读进去。实测同月存在多份 Group 文档的月份共 4 个：
    2011-01 / 2015-04 / 2022-06 / 2025-01。用原版 2025-01 加总 FY25 会让 Centre Point
    偏 +0.48%、trade reporting 偏 +1.18%、总成交额偏 +0.22%；换更正版后与年报逐项 0 偏差。

18. **存档页的标题变体极多**，回补时的匹配必须宽松：大小写不敏感（2026-04 起整体转小写）、
    "Group" 不能强求（2016-07…2016-10、2017-04 是 `ASX Monthly Activity Report`）、
    月份支持缩写（`… - Jan 2025`）、**标题不带年份时数据月 = 发布月 − 1**
    （2017-10、2017-11、2018-02/03/08/11 等期标题只有月名）。

19. **官方会把千分位逗号与小数点印反，错值本身完全合法。**
    ⚠ 这条原先写的是「2016–2018 那一代排版」—— **那个窗口假设是错的**，
    2026-09 在 2020-01 与 2025-08 各抓到一例（口径坑 23）。这不是某一代版式的
    历史遗留，是随时会复发的排版事故，所以判据不能按年份写。
    早期实测两例，方向相反，所以也不是「早期版本都要 ×1000」这种能一刀切的东西：
        2016-09 本期列 `Average value per trade ($)` = `4.852`（真值 4,852）
        2018-01 的 pcp 列同一行         = `4.433`（那是 2017-01 的值，真值 4,433）
    底层字符是真的 U+002E，不是渲染成句点的逗号 ⇒ 解析没错，是官方印错了。
    这种错**过不了任何一条加总恒等式**（这一行不参与任何加总），也不会让 `_validate`
    报缺列 —— 它就是一个安安静静小一千倍的数，画在图上是一根扎到零的刺。
    （口径坑 23 补了两道判据：同一行小数点风格自证 + `ADV × 交易日 = 月总量` 乘法恒等式。）
    ⇒ 靠**跨期自证**抓：t 期报告的第 2 个值列就是 t−12 月的值，拿它撞 series 里已有的
    那一行。本次回补用这条把 2016-01…2017-09 的 776 格全撞了一遍，760 格一致，
    16 格不一致里 13 格是精度（见下）、2 格是后期报告自己印错、1 格就是 2016-09 这个。
    **不给它写替代值**（恒等式反推 4,851.6、2017-09 的 pcp 列印着 4852，两个都不是
    当期原值），列进 `_KNOWN_SOURCE_GAPS` 留空。

20. **`Dominant settlement messages` 的印刷精度 2017-10 换过：1 位小数 → 3 位小数。**
    实测 2017-09 期印 `1.5`、2017-10 期印 `1.433`；后期报告回看同一个月时给的是
    3 位数（2018-09 期的 pcp 列把 2017-09 印成 `1.453`）。
    **定义没变，只是印得细了**，所以不算口径断点、不打红线；但 2016-01…2017-09 那段
    被量化到 0.1（约 ±3% 的格），单月环比 / 同比在那一段有一层纯粹的取整噪声。
    入库一律用**当期公告原值**（1.5），不拿后期报告的 3 位数去盖 —— 那是重述值。
    同理还有两处后期报告自己印错、而当期是对的，都以当期为准：
    2018-05 期把 pcp(2017-05) 的 `Open notional` 印成 `2903990`（真值 2,903.990，
    夹在 2017-04 的 2,695.544 与 2017-06 的 2,924.287 中间）；
    2018-01 期把 pcp(2017-01) 的参与者数印成 122，而 2017-01 当期印的是 121
    （2016-07…2017-05 连续 11 个月都是 121）。

21. **`S&P/ASX 200 VIX` 在 2019-10 之前不是表行，而是正文要点里的一句话 —— 同一个数。**
    这一列 2026-08 之前从 2019-10 才起，看着像「官方那时没发」，实际是**抓取器只认表行**：
        2019-09 及更早：只有正文 "…(as measured by the S&P/ASX 200 VIX) in September
                        was an average of 12.7…"（2017-02 起句式）／
                        "…increased in January to an average of 22.1 (compared to 18.0
                        in December)."（2016-01…2017-01 句式）
        2019-10 起    ：正文那句照写，**同时**多了表行 `S&P/ASX 200 VIX (average daily value)`
    两处一致性是实测出来的，不是假设：26 期两者同时存在（2019-10 / 2019-11 /
    2024-09…2026-07），**26/26 逐位相同**，精度同为 1 位小数。
    ⇒ `_vix_from_prose()` 在表里取不到时从正文取，`since` 因此是 2016-01 而不是 2019-10；
    两处都取到时**必须相等，否则抛异常**（把上面那条实测钉成永久闸门，官方哪天改口径
    就当场炸，而不是让两种数悄悄混进同一列）。回补进 series 的 45 格（2016-01…2019-09）
    仍然是**当期官方公告原值**：同一份 PDF、同一个月、官方自己印的数字，
    既不是换算也不是派生，更不是拿后期报告的重述值倒填。
    ⚠ 抓正文那句时**必须校验句子里的英文月名 = 数据月**：2016-01…2017-01 那种句式里
    句尾还挂着一个 pcp 数（"compared to 18.0 in December"），两个数字同在一句，
    位置不能当判据，只有月名能。

22. **分品种报告的直链有 5 代命名、日期段 3 种写法，还会在正文里换行断开 ——
    所以一个字符都不许自己拼，也不许解释里面的数字。** 2026-08 之前这里写的是
    `monthly-futures-markets-report-(\\d{8})\\.pdf`，8 位那个量词把 2020-06…2026-05
    共 72 期**全部**挡在门外，表现是「那 8 列只有最近 2 个月有值」，于是被写成
    「官方只保留最近 2 期」。当时的「实测 404」也是这么来的：拿数据月最后一天
    **自己拼**出 `31052026`，而官方那一期的真名是 `290526`。逐期实测的五代命名：
        2019-12…2020-01  /data/market-reports/MonthlySfeMarketsReport{YYMMDD}.pdf
        2020-02…2020-05  /data/market-reports/MonthlyFuturesMarketsReport{YYMMDD}.pdf
        2020-06          …/unlinked-docs/MonthlyFuturesMarketsReport{YYMMDD}.pdf
        2020-07…2022-02  …/unlinked-docs/finance-reports[/{YYYY}]/monthly-futures-markets-report-{YYMMDD}.pdf
        2022-03 至今     …/unlinked-docs/monthly-futures-markets-report-{日期}.pdf
    日期段：2025-07 之前 YYMMDD、2025-08…2026-05 改 DDMMYY（**2026-02 那一期又写回
    YYMMDD 的 `260227`**，所以连「哪一代用哪种」都不能当规则）、2026-06 起 DDMMYYYY。
    主机名 www / www2 与 http / https 也随期乱换（www2 与 http 都 302 到 https://www，
    正常跟随重定向即可）。
    ⇒ `_SFE_LINK` 只认文件名词干，**日期段写成 `\\S*`，一个数字都不解释**。
    两条取链路径都要，因为**两条各自都有坏掉的月份**：
      · 正文文本：URL 会在 `-` 处**换行断开**（2020-08 断在 `…report-\n200831.pdf`、
        2020-10 断在 `…markets-\nreport-201031.pdf`），所以搜之前要先把
        「以 `-` 或 `/` 结尾的行」与下一行接回去（`_URL_WRAP`）；
      · PDF 链接注解（`page.get_links()`）：2022-04…2022-10 与 2023-12 共 8 期**没有注解**；
        2021-01 / 2021-02 的注解把句号也吃进了 URL（`…210131.pdf.`）；
        **2024-11 与 2024-12 的注解是陈的，两期都指向 9 月那一份 `240930.pdf`**，
        而正文印的是对的（`241129` / `241231`）。
    ⇒ `_sfe_urls()` 两条都收、正文优先、注解兜底，逐条试；
    最终判官是 `parse_sfe()` 的首页抬头校验（"Monthly SFE Trading Report for
    November 2024"）—— 陈注解下回来的是一份**完全合法的 9 月报告**，
    只有抬头能把它认出来，字节数、Content-Type、`%PDF-` 一律正常。
    ⇒ 2026-08 回补 2020-06…2026-05 那 72 期时，除抬头外还逐月核了两条独立判据，
      都是「官方自己在别处印的同一个数」，不是我们算的：
        · **跨期自证**（同口径坑 19 的手法）：t 期报告的第 2 / 第 6 个数字列就是
          t−12 月的当月量 / 月末 OI，拿它撞 series 里已有的那一行 —— **495/496 格一致**。
          唯一不一致的那格是官方**后期重述**：2025-03 期把 2024-03 的 `3 Year Bonds / YT`
          当月量印成 5,378,144（YTD 同步差同样的 1,362），而 2024-03 当期印的是
          **5,379,506**。按本模块的规矩入库用**当期原值**，重述值不写。
        · **与 MAR 对账**：该期报告页尾 `Total Exchange` 的当月量 = 同月 MAR 的
          `contracts_futures_and_options_total`，**74/74 全等**。这一条同时证明
          「文件配对到了正确的月份」与「值列没有整体串行」。

23. **口径坑 19 的错印在 2020-01 与 2025-08 各复发一次，方向互为镜像。**
    2026-09 用本模块现成的媒体中心索引下载两期原件、PyMuPDF `rawdict` 逐字符核对，
    两处都是**官方排版错误**，不是 `_num()` 的问题：
        2020-01 `Index options volume / Average daily contracts` 本月列印 `43.485`
            （`.` 是真 U+002E，Calibri，同行另外三列 `35,544`/`36,901`/`46,281`
            用的都是千分位逗号）。同表 `Total contracts` 913,176 ÷ 本节交易日 21
            = 43,484.57 ⇒ 真值应为 43,485。
        2025-08 `Total billable cash market value cleared ($billion)` 本月列印
            `166,019`（`,` 是真 U+002C，ArialMT，同行另外三列 `142.742`/`316.749`/
            `271.170` 都是三位小数）⇒ 真值应为 166.019。
    **两格一律留空，不写替代值** —— 反推用的都是「同一张表里另外两个数相除/相加」，
    与坑 19 已经明令拒绝的 108.913e9 ÷ 22,449,067 = 4,851.6 是同一类反推。
    这条线一旦因为「这次反推更准」就松动，就再没有客观标准了。两条登记见
    `_KNOWN_SOURCE_GAPS`。

    ⇒ 补了两道判据，都不需要历史数据、不需要猜量级阈值：
    · **同一行小数点风格自证**（`_decimal_style_check()`）。`_num()` 把千分位逗号吃掉
      之后，「这个字符串里有没有 `.`」原样留在解析结果里。同一个指标的
      「本月 / 去年同月 / 本财年 YTD / 去年同期 YTD」四列出自同一次排版，理应用同一种
      记数习惯；混用就是官方把两个符号印反了的物证。回溯三次已知事故
      （2016-09 / 2020-01 / 2025-08）三次命中。
      ⚠ 已在 `_KNOWN_SOURCE_GAPS` 登记过的格**跳过**，让它照旧走
      `_drop_source_errors()` 的「先核对错值再删」那条路 —— 否则官方哪天重发修正版，
      这道判据会先一步把整月拦死，那条核对就永远跑不到了。
    · **`ADV × 交易日 = 月总量` 乘法恒等式**（`_RATE_IDENTITIES`）。官方在同一张表里
      同时印日均与月总量，这层关系此前一条都没查过 —— 而现有 5 条恒等式清一色是加法，
      从设计上就不管单个数的小数点位置。实测 128 个月 × 5 组配对，合法残差最大
      1.02e-3（官方把 ADV 四舍五入到整张），2020-01 那格是 0.999，
      容差取 `_RATE_TOL = 5e-3`（合法侧 5 倍余量，错值侧差两个数量级）。

━━ 依赖 ━━ pymupdf（import 名 fitz）。不依赖 pandas / requests。
"""

import csv
import os
import re
import time
import urllib.request
from datetime import datetime

import fitz

MEDIA_CENTRE_URL = 'https://www.asx.com.au/about/media-centre'
ASX_HOST = 'https://www.asx.com.au'
ARCHIVE_LIST_URL = (ASX_HOST + '/asx/v2/statistics/announcements.do'
                    '?by=asxCode&asxCode=asx&timeframe=Y&year=%d')
ARCHIVE_ITEM_URL = (ASX_HOST + '/asx/v2/statistics/displayAnnouncement.do'
                    '?display=pdf&idsId=%s')

# 带常规浏览器 UA：asx.com.au 目前完全不校验（裸 urllib 也 200），
# 但带上是零成本的保险，且出问题时对方日志里能看出是谁在打。
_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# series/asx.csv 的第一行数据月。
#
# 2026-08 由 2017-10 改为 2016-01（全站短窗口图的共同起点，见 build/single.py 的
# `WIN_FROM`）。原先定在 2017-10 的两条理由**逐条实测后都不成立**：
#   · 「再往前那 21 个月要第二套标签映射」—— 不需要。COLUMN_SPEC 里那几条老口径别名
#     （`total value` / `average daily value on-market` / `average daily value`）本来
#     就把 2015-09 起那一代行名覆盖住了，2016-01…2017-09 这 21 期用**未改动的**
#     `parse_mar` 全部解析成功，34 列 21/21 期期有值（本次逐期实发 HTTP 复核）。
#     零改动的天花板其实是 2015-10（2015-10/11/12 三期 `_validate` 直接过），
#     2015-09 及更早才要第二套映射 —— 与 2016-01 这个目标无关。
#   · 「2017-04 那期 PDF 错行」—— 属实，但只影响该月的两格，不影响另外 20 期。
#     那两格由 `_shifted_blocks()` 按签名搬回原标签、过 `_identity_gate()` 后入库
#     （口径坑 16），入的是官方原值；`_KNOWN_SOURCE_GAPS` 里的登记退为兜底。
# 顺带纠正一条记在 docs/verify/asx.md 里的误记：「Listings 段在 2016/2017 之间换过
# 定义」是错的。`capital_initial_raised_audmn` 与 `capital_total_raised_incl_other_audmn`
# 在这 21 期里 21/21 都有，`mktcap_new_listings_audmn` 一期都没有 ⇒ 上市融资的口径断点
# 只有 2023-10 一处（口径坑 10），回补 2016 不新增断点。
#
# 改这个常量不会让 cron 凭空多抓：`update()` 的 index 来自媒体中心，实测最早 2019-12，
# todo 取 `m >= SERIES_START and m not in have`，够不着的月份根本不在 index 里。
# 2016-01…2019-11 只能由人跑一次 `--backfill`（走公告存档，要过同意页，见 docstring）。
SERIES_START = '2016-01'

# 分品种辅源（Monthly SFE Trading Report）的官方天花板 —— 见 docstring 辅源节与口径坑 22。
# 2020-05 及更早的 MAR 指向老站点 `/data/market-reports/…`，那条路径今天整体 soft-404；
# 2020-06 那一期起指向 DAM，2026-08 实发 72/72 全部 200 + 真 PDF。
# 它只用来**省掉必然失败的请求**：`update()` 与 `--sfe-backfill` 都不对更早的月份发请求。
# 真要复核这条天花板，把它改早再跑 `--sfe-backfill`，失败原因会逐月印出来。
SFE_START = '2020-06'

_MONTHS = {m.lower(): i for i, m in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June', 'July',
     'August', 'September', 'October', 'November', 'December'], 1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_MONTHS['sept'] = 9

# 媒体中心 href 里的 MAR。文件名末尾的 {month}-{YYYY} 是**数据月**，
# 中间那段是发布日、开头那个数字是日历年内公告序号 —— 都不能拿来当数据月（口径坑：发布节奏节）。
_MAR_HREF = re.compile(
    r'href="(/content/dam/asx/[^"]*monthly[-%20]*activity[-%20]*report[^"]*\.pdf)"', re.I)
# 分隔符要写成可有可无：2019-12 与 2020-01 两期的文件名是驼峰无分隔的
# `ASXGroupMonthlyActivityReportJanuary2020.pdf`，其余 80 期是 `…-january-2020.pdf`。
# 锚在 `$` 上，所以文件名中段那个「发布月」（`43-06-august-2026-…`）抢不到。
_TAIL_MONTH = re.compile(
    r'[-_ ]?(january|february|march|april|may|june|july|august|september|october|'
    r'november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)[-_ ]?(\d{4})\.pdf$', re.I)
# 从 PDF 正文抬头读它自称的数据月，用来反证文件名没读错（见 _fetch_one）
_SELF_TITLE = re.compile(
    r'monthly\s+activity\s+report\s*(?:for\s+|[-‐-―]\s*)?'
    r'(january|february|march|april|may|june|july|august|september|october|'
    r'november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{4})', re.I)

# 存档列表页的一行：日期 / 时刻 / idsId / 标题
_ARCHIVE_ROW = re.compile(
    r'<tr>\s*<td>\s*(\d{2}/\d{2}/\d{4})\s*<br>\s*<span class="dates-time">\s*([^<]+?)\s*'
    r'</span>.*?idsId=(\d+)"[^>]*>\s*(.*?)<br>', re.S)
# 诱饵与噪声：Compliance 版（口径坑 1）；"and Fee and Rebate Changes" 那种完全没有月份的公告
_ARCHIVE_SKIP = ('compliance',)
_TITLE_MONTH = re.compile(
    r'\b(january|february|march|april|may|june|july|august|september|october|'
    r'november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b\.?\s*(\d{4})?', re.I)
_CORRECTION = re.compile(r'correct|update', re.I)

# 首页正文第一行的发布日，例 "6 August 2026"（口径坑：发布节奏节）
_PUB_DATE = re.compile(
    r'^(\d{1,2})\s+(January|February|March|April|May|June|July|August|'
    r'September|October|November|December)\s+(\d{4})$')

# 分品种辅源：链接印在 MAR 正文里，直接从 PDF 文本里抠。
# 只认**文件名词干**（五代命名见口径坑 22），日期段一律 `\S*` —— 官方在 YYMMDD /
# DDMMYY / DDMMYYYY 之间来回换，写死任何一种长度都会静默丢掉几十期。
# 非贪婪到第一个 `.pdf`，所以注解里多出来的句号（`…210131.pdf.`）不会被吃进来。
_SFE_LINK = re.compile(
    r'https?://\S*'
    r'(?:monthly-futures-markets-report-|monthlyfuturesmarketsreport|monthlysfemarketsreport)'
    r'\S*?\.pdf', re.I)
# 正文里的 URL 会在 `-` / `/` 处换行断开（口径坑 22）。只接「行尾是 - 或 /」这一种，
# 且只用于抠链接的那份临时文本 —— 不碰任何参与数值解析的文本。
_URL_WRAP = re.compile(r'(?<=[-/])[ \t]*\n[ \t]*(?=\S)')

# 口径坑 21：`S&P/ASX 200 VIX` 的月内日均值在 **2019-10 之前不是表行，而是正文要点里的一句话**。
# 两种句式（实测就这两种，2016-01…2026-07 共 71 期 PDF 逐期跑过）：
#     "…(as measured by the S&P/ASX 200 VIX) increased in January to an average of 22.1
#      (compared to 18.0 in December)."      2016-01…2017-01
#     "…(as measured by the S&P/ASX 200 VIX) in September was an average of 12.7…"
#                                            2017-02 起
# `mid` 那一段**必须含数据月的英文月名**，这是防止抓到句尾 "(compared to 18.0 in December)"
# 那个 pcp 数的唯一屏障 —— 两个数字都在同一句里，位置不能当判据。
# `[^.]` 顺带保证不会跨句：两种句式里，月名与 "average of" 之间从来没有句点。
_VIX_PROSE = re.compile(
    r'S&P\s*/\s*ASX\s*200\s*VIX\s*\)'
    r'(?P<mid>[^.]{0,120}?)'
    r'\baverage(?:d|\s+of)\s+(?P<v>\d+(?:\.\d+)?)', re.I)


class AsxFetchError(RuntimeError):
    """源站结构变化 / 下载失败 / 解析结果不完整。一律炸掉，绝不静默写 NaN。"""


# ══════════════════════════════════════════════════════════════════════
# 网络
# ══════════════════════════════════════════════════════════════════════
def _http_get(url, timeout=90):
    req = urllib.request.Request(url, headers={
        'User-Agent': _UA,
        'Accept': '*/*',
        'Accept-Language': 'en-AU,en;q=0.9',
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            # 返回 r.headers 本体而不是 dict(r.headers)：前者查名字**不分大小写**。
            # 转成 dict 会把大小写钉死，服务器一旦发 `content-type`（HTTP/2 一律小写）
            # 而不是 `Content-Type`，_http_pdf 的 Content-Type 校验就会读到空串，
            # 于是**每一个正常的 PDF 都被当成 soft-404 拒收**。实测这台源站两种写法都出现过。
            return r.read(), r.headers
    except Exception as e:                                # noqa: BLE001
        raise AsxFetchError('下载失败 %s: %r' % (url, e)) from e


def _http_pdf(url, timeout=90):
    """下载并**证明它真的是 PDF**。

    只看 HTTP 200 是不够的：ASX 有一条路径（口径坑 2）在文件不存在时返回
    200 + text/html + 恒定 136,750 字节的错误页。存下来之后 pymupdf 会报一个
    「文件损坏」之类跟真实原因毫无关系的错，排查成本极高。
    Content-Type 与 `%PDF-` 魔数两条都校验：前者防对方改错误页大小，后者防对方
    把错误页的 Content-Type 也标成 application/pdf。
    """
    body, hdrs = _http_get(url, timeout)
    ctype = (hdrs.get('Content-Type') or '').split(';')[0].strip().lower()
    if ctype != 'application/pdf' or body[:5] != b'%PDF-':
        raise AsxFetchError(
            '%s 返回的不是 PDF（Content-Type=%r, 前 5 字节=%r, %d 字节）——'
            '多半是 soft-404 错误页，见模块 docstring 口径坑 2'
            % (url, ctype, body[:5], len(body)))
    return body


def _write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


# ══════════════════════════════════════════════════════════════════════
# 发现：媒体中心（cron 唯一入口）
# ══════════════════════════════════════════════════════════════════════
def _discover_media_centre(cache_dir):
    """返回 {'YYYY-MM': {'orig': url|None, 'corr': url|None}}。

    原版与更正稿**两个都留着**，不是二选一：数值要用更正稿（口径坑 17），
    但「官方哪天发的这个月」要用**原版**的日期。2022-06 的更正稿抬头写的是
    20 July 2022，原版是 6 July 2022；把 20 号记进 source_dates.csv，
    等于告诉 LAG 审计「ASX 有时候拖到次月 20 号才发」，那张表就白记了。
    """
    html, _ = _http_get(MEDIA_CENTRE_URL)
    _write_bytes(os.path.join(cache_dir, 'asx_media_centre.html'), html)
    text = html.decode('utf-8', 'replace')
    hits = _MAR_HREF.findall(text)
    if not hits:
        raise AsxFetchError('媒体中心找不到任何 Monthly Activity Report 链接，'
                            '源站可能改版：' + MEDIA_CENTRE_URL)
    out = {}
    for href in hits:
        name = href.rsplit('/', 1)[-1]
        if 'compliance' in name.lower():          # 媒体中心目前不挂 Compliance 版，但白挡不亏
            continue
        m = _TAIL_MONTH.search(name.replace('%20', ' '))
        if not m:
            # 文件名不带数据月 = 命名规则变了。宁可炸，也不要按发布月猜一个数据月。
            raise AsxFetchError('媒体中心 MAR 文件名读不出数据月：%s' % name)
        mon = '%s-%02d' % (m.group(2), _MONTHS[m.group(1).lower()])
        slot = 'corr' if _CORRECTION.search(name) else 'orig'
        out.setdefault(mon, {'orig': None, 'corr': None})[slot] = ASX_HOST + href
    return out


def _discover_archive(year):
    """存档列表页 → [(数据月, idsId, 标题, 发布日 'YYYY-MM-DD', 是否更正稿)]。

    **只在 --backfill 里用**：该页本身是纯 HTML 表格，但拿 PDF 要经过一页
    「点击即接受条款」的同意表单（见模块 docstring）。
    """
    html, _ = _http_get(ARCHIVE_LIST_URL % year)
    text = html.decode('utf-8', 'replace')
    out = []
    for d, _tm, ids, title in _ARCHIVE_ROW.findall(text):
        title = re.sub(r'\s+', ' ', title).strip()
        low = title.lower()
        if 'monthly activity report' not in low:
            continue
        if any(s in low for s in _ARCHIVE_SKIP):          # 口径坑 1：Compliance 诱饵
            continue
        dd, mm, yy = (int(x) for x in d.split('/'))
        m = _TITLE_MONTH.search(low)
        if not m:
            continue                                       # "…and Fee and Rebate Changes"：无月份
        mo = _MONTHS[m.group(1).lower()]
        if m.group(2):
            mon = '%s-%02d' % (m.group(2), mo)
        else:
            # 口径坑 18：标题不带年份时，数据月 = 发布月 − 1
            py, pm = (yy - 1, 12) if mm == 1 else (yy, mm - 1)
            if mo != pm:
                continue                                   # 对不上就别猜
            mon = '%04d-%02d' % (py, pm)
        out.append((mon, ids, title, '%04d-%02d-%02d' % (yy, mm, dd),
                    bool(_CORRECTION.search(title))))
    return out


def _archive_pdf_url(ids_id):
    """从同意页里读出真实 PDF 直链（隐藏字段，纯 GET，不 POST 那张表单）。"""
    html, _ = _http_get(ARCHIVE_ITEM_URL % ids_id)
    m = re.search(r'name="pdfURL"[^>]*value="([^"]+)"',
                  html.decode('utf-8', 'replace'))
    if not m:
        raise AsxFetchError('存档中转页读不出 pdfURL 隐藏字段：idsId=%s' % ids_id)
    return m.group(1)


# ══════════════════════════════════════════════════════════════════════
# PDF → 行（y 坐标聚类 + 水印过滤 + 值列左边界）
# ══════════════════════════════════════════════════════════════════════
_WATERMARK = {'for', 'personal', 'use', 'only'}     # 口径坑 5：竖排水印
_NUMCUT = 0.47                                      # 口径坑 6：值列左边界 / 页宽
_YTOL = 3.0                                         # 同一视觉行的 y 容差（磅）

_DASH = re.compile(r'[‐‑‒–—―−]')
_FOOTNOTE = re.compile(r'[*¹²³†‡]')
_UNIT_SUFFIX = re.compile(
    r'\s*\((?:\$billion|\$million|\$|million|billion|at end of month|period end)\)\s*$', re.I)
_NUM_TOKEN = re.compile(r'^\(?-?[\d,]+(?:\.\d+)?\)?$')


def _norm(s):
    """统一破折号、删脚注记号、压空白。破折号有 7 种 Unicode 变体在同一批 PDF 里混用。"""
    return re.sub(r'\s+', ' ', _FOOTNOTE.sub('', _DASH.sub('-', s))).strip()


def _section_of(k):
    """行标签键 -> 它是不是某个大标题；不是就返回 None。见 _SECTIONS 上方的注释。"""
    for s in _SECTIONS:
        if k == s or k.startswith(s + ' ('):
            return s
    return None


def _key(label):
    """行标签 → 匹配键：小写、剥前导项目符号、剥尾部 ASCII 脚注数字、剥尾部单位括号。

    三件事各自对应一个实测的坑：
      · 前导 '-'：2018-05/06/07 与 2019-07 的 `-Total secondary capital raised ($million)`
        比别的月份多一个前导破折号（口径坑 8 的同类）；
      · 尾部 ASCII 数字：2024 版把脚注标记写成 `($billion)1`（口径坑 8）；
      · 尾部单位括号：`($billion)` 经常换行掉队到标签区之外，同一个指标 131 个月里
        13 个月没有它、118 个月有（口径坑 9）。
    剥完之后没有任何两个约定标签会撞车 —— COLUMN_SPEC 里的别名就是按剥完的形态写的。
    """
    s = _norm(label).lstrip('-•● ').strip()
    s = s.rstrip('0123456789 ').strip()
    prev = None
    while prev != s:                       # `($billion) (at end of month)` 要剥两次
        prev = s
        s = _UNIT_SUFFIX.sub('', s).strip()
    return s.lower()


def _num(tok):
    """'1,234' -> '1234'；'(964)' -> '-964'；'24%' / 'na' -> None。

    返回**字符串**而不是 float：入库要与官方印出来的写法一模一样
    （`635.499` 不写成 `635.499000001`，`2045` 不写成 `2045.0`），
    这样重跑时 CSV 字节级不变，幂等判断才干净。
    """
    t = tok.strip()
    neg = t.startswith('(') and t.endswith(')')
    t = t.strip('()').replace(',', '')
    if not re.fullmatch(r'-?\d+(?:\.\d+)?', t):
        return None
    return ('-' + t) if (neg and not t.startswith('-')) else t


def _decimal_style_mixed(vals):
    """同一行的值列里小数点风格不一致 -> 说明字符串；一致返回 None。

    `_num()` 已经把千分位逗号吃掉，但**有没有 `.`** 这个信息原样留在它返回的字符串里。
    同一个指标的「本月 / 去年同月 / 本财年 YTD / 去年同期 YTD」四列出自**同一次排版**，
    理应用同一种记数习惯：要么都是三位小数的金额，要么都是不带小数的张数。
    混用是官方把千分位逗号与小数点印反了的物证（口径坑 19 / 23）。

    为什么用这条而不是「跟前后月比量级」：这条不需要历史数据、不需要猜阈值，而且
    上市融资、上市数变动这些列本来就会真实地大起大落（口径坑 10 / 11），量级判据
    在那些列上必然与真实业务尖峰打架。回溯三次已知事故三次命中：
        2016-09 ['4.852', '5710', '4.701', '5784']
        2020-01 ['43.485', '35,544', '36,901', '46,281']
        2025-08 ['166,019', '142.742', '316.749', '271.170']
    """
    dotted = [v for v in vals if v and '.' in v]
    plain = [v for v in vals if v and '.' not in v]
    if dotted and plain:
        return '带小数点的 %s，不带的 %s' % (dotted, plain)
    return None


def _page_rows(page):
    """一页 → [(标签, [值字符串…])]，按视觉行自上而下。

    为什么按 y 坐标聚类而不用 `page.get_text()` 的阅读顺序：2024 版把括号说明排在
    标签与数值之间（阅读顺序里是 标签 / 说明 / 说明 / 23 / 21），2016 版把值排在
    标签与单位之间 —— 阅读顺序两边都对不上，但**视觉行**永远是对的。
    """
    width = page.rect.width
    cut = width * _NUMCUT
    words = [w for w in page.get_text('words')
             if w[4].strip() and w[4].strip().lower() not in _WATERMARK]
    words.sort(key=lambda w: (round(w[1], 1), w[0]))
    buckets = []
    for w in words:
        y = (w[1] + w[3]) / 2.0
        for b in buckets:
            if abs(b['y'] - y) <= _YTOL:
                b['w'].append(w)
                b['y'] = (b['y'] * (len(b['w']) - 1) + y) / len(b['w'])
                break
        else:
            buckets.append({'y': y, 'w': [w]})
    rows = []
    for b in sorted(buckets, key=lambda b: b['y']):
        ws = sorted(b['w'], key=lambda w: w[0])
        label = _norm(' '.join(w[4] for w in ws if w[0] < cut))
        vals = []
        for w in ws:
            if w[0] >= cut:
                v = _num(w[4])
                if v is not None:
                    vals.append(v)
        rows.append((label, vals))
    return rows


# ══════════════════════════════════════════════════════════════════════
# MAR 解析
# ══════════════════════════════════════════════════════════════════════
# section：大标题。破折号已归一成 '-'，全部小写比较。
#
# **只认整行相等，或 `大标题 + " ("` 开头**，不能用宽松的前缀匹配。
# 前缀匹配踩过一次实测的坑：`settlement` 是个很短的词，正文里
# "…resigned as ASX Settlement Participants." 这种句子换行后正好以它开头，
# 于是在 Participants 段中间把 section 悄悄改回 `settlement`，
# 结果 2020-10 与 2023-03 两个月的参与者数解析为空 —— 而其余 129 个月都正常，
# 属于「大部分月份看着没问题」的那种最难发现的错。
# 之所以还要留 `+ " ("` 这条口子：现货段的大标题自带括号说明，且说明本身改过词
#   TRADING - CASH MARKETS (INCLUDING EQUITIES, INTEREST RATE AND WARRANTS TRADES)  2016 版
#   Trading - Cash Markets (including equities, interest rate and ETP trades)       现行
_SECTIONS = [
    'listings and capital raisings',
    'trading - cash markets',
    'trading - futures',
    'trading - equity options',
    'clearing - otc markets',
    'clearing - exchange-traded markets',
    'settlement',
    'participants',
]
# subsection：小标题。只有它能把 5–6 次的 `average daily contracts` 分开（口径坑 3）。
_SUBSECTIONS = [
    'cash market volume', 'cash market value',
    'futures volume', 'options on futures volume',
    'total futures and options on futures volume',
    'single stock equity options volume', 'equity options volume',
    'index options volume', 'total options volume',
    'austraclear settlement and depository',
]

# (csv 列名, section, subsection|None, [标签别名…], since, until)
#   subsection=None 表示该标签在整个 section 内唯一，不需要再切一层。
#   since/until 是**实测**的官方起止月（口径坑 15）；越界为空合法，界内为空抛异常。
COLUMN_SPEC = [
    # ── 现货（Cash Markets）──────────────────────────────────────────
    ('trading_days_cash', 'trading - cash markets', None,
     ['total trading days'], None, None),
    ('trades_cash_total', 'trading - cash markets', 'cash market volume',
     ['total trades'], None, None),
    ('adt_cash_trades', 'trading - cash markets', 'cash market volume',
     ['average daily trades'], None, None),
    ('value_open_trading_audbn', 'trading - cash markets', 'cash market value',
     ['open trading'], None, None),
    ('value_auctions_audbn', 'trading - cash markets', 'cash market value',
     ['auctions trading'], None, None),
    ('value_centrepoint_audbn', 'trading - cash markets', 'cash market value',
     ['centre point'], None, None),
    ('value_tradereport_audbn', 'trading - cash markets', 'cash market value',
     ['trade reporting'], None, None),
    ('value_cash_onmarket_audbn', 'trading - cash markets', 'cash market value',
     ['on-market value'], '2017-10', None),
    ('value_cash_total_audbn', 'trading - cash markets', 'cash market value',
     ['total cash market value', 'total value'], None, None),
    ('adt_cash_onmarket_audbn', 'trading - cash markets', 'cash market value',
     ['on-market average daily value', 'average daily value on-market'], None, None),
    ('adt_cash_total_audbn', 'trading - cash markets', 'cash market value',
     ['total average daily value', 'average daily value',
      # 2017-07 那一期独有的写法，只此一月
      'average daily value on-market and trade reporting'], None, None),
    ('avg_value_per_trade_aud', 'trading - cash markets', 'cash market value',
     ['average value per trade'], None, None),
    # 表行 2019-10 才有；2016-01…2019-09 由 `_vix_from_prose` 从正文要点取同一个数
    # （口径坑 21），所以 since 是 2016-01 而不是 2019-10 —— 界内为空照样炸。
    # 2016-01 这个下界是**实测下界**：本仓 SERIES_START 就是 2016-01，再往前没验过。
    ('vix_asx200_avg', 'trading - cash markets', 'cash market value',
     ['s&p/asx 200 vix (average daily value)'], '2016-01', None),
    # ── ASX 24 期货与期货期权 ────────────────────────────────────────
    ('trading_days_futures', 'trading - futures', None,
     ['futures and options total trading days'], None, None),
    ('contracts_futures_total', 'trading - futures', 'futures volume',
     ['total contracts'], None, None),
    ('adv_futures_contracts', 'trading - futures', 'futures volume',
     ['average daily contracts'], None, None),
    ('contracts_options_on_futures_total', 'trading - futures',
     'options on futures volume', ['total contracts'], None, None),
    ('adv_options_on_futures_contracts', 'trading - futures',
     'options on futures volume', ['average daily contracts'], None, None),
    ('contracts_futures_and_options_total', 'trading - futures',
     'total futures and options on futures volume', ['total contracts'], None, None),
    ('adv_futures_and_options_contracts', 'trading - futures',
     'total futures and options on futures volume',
     ['average daily contracts'], None, None),
    # ── 股票期权（ASX Clear ETO）─────────────────────────────────────
    ('trading_days_eto', 'trading - equity options', None,
     ['exchange-traded options total trading days'], None, None),
    ('contracts_single_stock_options_total', 'trading - equity options',
     'single stock equity options volume', ['total contracts'], None, None),
    ('adv_single_stock_options_contracts', 'trading - equity options',
     'single stock equity options volume', ['average daily contracts'], None, None),
    ('contracts_index_options_total', 'trading - equity options',
     'index options volume', ['total contracts'], None, None),
    ('adv_index_options_contracts', 'trading - equity options',
     'index options volume', ['average daily contracts'], None, None),
    # ── 上市与融资 ───────────────────────────────────────────────────
    ('listed_entities_total', 'listings and capital raisings', None,
     ['total listed entities'], None, None),
    ('new_listed_entities', 'listings and capital raisings', None,
     ['new listed entities', 'new listed entities admitted'], None, None),
    ('delisted_entities', 'listings and capital raisings', None,
     ['entities de-listed'], '2024-05', None),
    ('capital_initial_raised_audmn', 'listings and capital raisings', None,
     ['initial capital raised'], None, '2023-09'),
    ('mktcap_new_listings_audmn', 'listings and capital raisings', None,
     ['quoted market capitalisation of new listings',
      'quoted market capital of new listings'], '2023-10', None),
    ('capital_secondary_audmn', 'listings and capital raisings', None,
     ['secondary capital raised'], None, None),
    ('capital_other_scrip_audmn', 'listings and capital raisings', None,
     ['other capital raised including scrip-for-scrip'], None, None),
    ('capital_secondary_total_audmn', 'listings and capital raisings', None,
     ['total secondary capital raised'], None, None),
    ('capital_total_raised_incl_other_audmn', 'listings and capital raisings', None,
     ['total capital raised including other'], None, '2023-09'),
    ('capital_new_quoted_audmn', 'listings and capital raisings', None,
     ['total new capital quoted', 'total initial and secondary capital quoted'],
     '2023-10', None),
    ('mktcap_delisted_audmn', 'listings and capital raisings', None,
     ['quoted market capitalisation of entities de-listed'], '2024-05', None),
    ('capital_net_new_quoted_audmn', 'listings and capital raisings', None,
     ['total net new capital quoted'], '2024-05', None),
    # ── 清算 / 结算 ──────────────────────────────────────────────────
    ('otc_notional_cleared_audbn', 'clearing - otc markets', None,
     ['total notional cleared value'], None, None),
    ('otc_open_notional_audbn', 'clearing - otc markets', None,
     ['open notional cleared value'], None, None),
    ('billable_cash_cleared_audbn', 'clearing - exchange-traded markets', None,
     ['total billable cash market value cleared'], None, None),
    ('margin_cash_onbs_audbn', 'clearing - exchange-traded markets', None,
     ['total cash margins held on balance sheet'], '2019-10', '2024-07'),
    ('margin_total_audbn', 'clearing - exchange-traded markets', None,
     ['total margins held'], '2024-08', None),
    ('chess_holdings_audbn', 'settlement', None,
     ['value of chess holdings - period end'], None, None),
    ('settlement_msgs_mn', 'settlement', None,
     ['dominant settlement messages'], None, None),
    ('austraclear_holdings_audbn', 'settlement', 'austraclear settlement and depository',
     ['austraclear securities holdings - period end'], None, None),
    ('participants_asx_total', 'participants', None,
     ['market/clearing/settlement participants at month end',
      # 这一行在 2016–2017 那一代版式里会被 pymupdf 按视觉行切断，断点有两个位置，
      # 两种都要认。**别名按「长→短」排**：完整形态先匹配，短形态只在长的取不到时兜底。
      #   · 2017-01…2017-06：'…Participants at month' / 'end'（断在 month 之后）
      #   · 2016-09…2016-12：'…Participants at' / '' / 'month end'（断在 at 之后，
      #     值挂在中间那行的空标签上，靠 `_values_for` 的向下前瞻取到；
      #     实测 2016-09 rows[212]='…Participants at' 空值、rows[213]=('', ['121','120'])）
      # 都是纯断行，不是官方换了行名 —— 2016-08 与 2017-07 的同一行是完整的。
      # 三种形态互不包含（`table` 的键是整串相等），不会与别的标签撞车。
      'market/clearing/settlement participants at month',
      'market/clearing/settlement participants at'], '2016-07', None),
    ('participants_asx24_total', 'participants', None,
     ['trading/clearing participants at month end'], '2016-07', None),
]

MAR_COLUMNS = [c for c, *_ in COLUMN_SPEC]

# 辅源 SFE 分品种：(csv 列名, section, 合约代码, 取哪一列)
# 代码（AP/YT/XT/IR）比品名稳定，且同一个 `3 Year Bonds / YT` 在
# `Interest Rates - Futures` 与 `Interest Rates - Options` 两段各出现一次 ——
# 与口径坑 3 同一类错误，所以这里同样先切 section 再查代码。
SFE_SPEC = [
    ('contracts_spi200_futures', 'equity indices - futures', 'AP', 'month'),
    ('oi_spi200_futures', 'equity indices - futures', 'AP', 'oi'),
    ('contracts_3y_bond_futures', 'interest rates - futures', 'YT', 'month'),
    ('oi_3y_bond_futures', 'interest rates - futures', 'YT', 'oi'),
    ('contracts_10y_bond_futures', 'interest rates - futures', 'XT', 'month'),
    ('oi_10y_bond_futures', 'interest rates - futures', 'XT', 'oi'),
    ('contracts_90d_bankbill_futures', 'interest rates - futures', 'IR', 'month'),
    ('oi_90d_bankbill_futures', 'interest rates - futures', 'IR', 'oi'),
]
SFE_COLUMNS = [c for c, *_ in SFE_SPEC]

CSV_COLUMNS = ['month'] + MAR_COLUMNS + SFE_COLUMNS


def _values_for(rows, i):
    """取第 i 行标签对应的值列表；本行没有就向下前瞻至多 2 行（口径坑 7）。

    只接受「标签区为空 / 以 '(' 开头 / 以小写字母开头」的续行 —— 正文段落与下一个
    指标的标签都是大写字母开头（`Change on pcp`、`Total contracts`、`Cash market value`），
    所以不会把别人的数字吃过来。碰到不合格的行立即停，宁可空着让 _validate 炸。
    """
    if rows[i][1]:
        return rows[i][1]
    for j in (i + 1, i + 2):
        if j >= len(rows):
            break
        lab, vals = rows[j]
        if lab and not (lab.startswith('(') or lab[0].islower()):
            break
        if vals:
            return vals
    return []


# 量块的固定形态：小标题 / `Total contracts` / `Change on pcp` / `Average daily contracts`。
# 2016 版与 2024/2026 版都是这四行（实测 127 期，期货 / 期货期权 / 合计 / 单股期权 /
# 指数期权五个块一律如此），所以「下移一行」这种病可以按形态认。
_SHIFTED_SHAPE = ('total contracts', 'change on pcp', 'average daily contracts')


def _shifted_blocks(rows):
    """认出「值列相对标签整体上移一行」的量块 -> [(小标题键, {标签键: 值列表})]（口径坑 16）。

    ━━ 签名（两条判据 + 一条形状约束，**全部**满足才算，缺一不认）━━
      ① **小标题行带值**。小标题（`Options on futures volume` 那种）在健康的报告里
         永远是一行纯文字 —— 它带值本身就是排版坏了的物证，而不是推断。
         实测 127 期全段扫描，这种行**只有 1 处**：2017-04 的期货期权块。
      ② 本该带值的末行 `Average daily contracts` **整行为空**。
      ③（形状）块要逐行对上 `_SHIFTED_SHAPE`，且中间的 `Total contracts` 行也整行为空
         —— 「值整体上移一行」必然长这样：i 行的值属于 i+1 行的标签，i+1 行自己空掉。

    ⚠ 本函数**只搬运，不计算**：把 PDF 上印着的那串数字挪到它本该挂的标签上，
    一个数都不加不减不四舍五入。搬回来的值还要逐格过 `_identity_gate` 才准入库
    （见 `parse_mar`），过不了就当没看见。

    ⚠ 不能只靠 ② 判：`Change on pcp` 行带值在 2024-11 起的版式里是**常态**
    （官方那一代把百分号去掉了，实测 127 期共 610 处），只有 ① 能把病态与常态分开。
    """
    out = []
    for i, (label, vals) in enumerate(rows):
        k = _key(label)
        if k not in _SUBSECTIONS or not vals:
            continue                                  # ① 小标题必须带值
        if i + 3 >= len(rows):
            continue
        shape = [_key(rows[j][0]) for j in (i + 1, i + 2, i + 3)]
        if tuple(shape) != _SHIFTED_SHAPE:
            continue                                  # ③ 形态必须逐行对上
        if rows[i + 1][1] or rows[i + 3][1]:
            continue                                  # ②③ 这两行必须整行为空
        if not rows[i + 2][1]:
            continue                                  # 没东西可搬
        out.append((k, {_SHIFTED_SHAPE[0]: vals,
                        _SHIFTED_SHAPE[2]: rows[i + 2][1]}))
    return out


def _vix_from_prose(doc, month, skip_first_page=False):
    """正文要点里的 `S&P/ASX 200 VIX` 月内日均值 -> 值字符串；读不出返回 None（口径坑 21）。

    2019-10 起这个数**同时**印在表里和正文里，2019-09 及更早**只印在正文里**。
    两处从来没有不一致过：实测 26 期两者都在（2019-10 / 2019-11 / 2024-09…2026-07），
    26/26 逐位相同、精度同为 1 位小数。所以正文那句话给出的不是「近似」也不是
    「另一种口径」，就是同一个数的另一处印刷 —— 拿它入库仍然是**当期官方公告原值**，
    不是换算、不是派生、也不是后期重述。

    `parse_mar` 只在表里取不到时才调它，且两边都取到时会撞一次（见 `parse_mar`）：
    那道撞法把上面这 26 期的实测结论钉成了一条永久闸门，官方哪天让两处不一致就当场炸。

    month 为 None（有人只想看表行解析结果）时直接返回 None —— 没有数据月就无法
    校验句子说的是不是本月，宁可不给值。
    """
    if not month:
        return None
    text = re.sub(r'\s+', ' ', '\n'.join(
        doc[i].get_text() for i in range(doc.page_count)
        if not (skip_first_page and i == 0)))
    want = datetime.strptime(month, '%Y-%m').strftime('%B').lower()
    for m in _VIX_PROSE.finditer(text):
        if want in m.group('mid').lower():
            return _num(m.group('v'))
    return None


def parse_mar(path, skip_first_page=False, month=None):
    """解析一份 MAR PDF，返回 {csv 列名: 值字符串}（缺的键就不出现）。

    skip_first_page：更正稿专用（口径坑 17）。更正稿第 1 页是「错误值 / 正确值」
    对照表，**错误值就印在那一页**，不跳过就会把错值当本月值读走。

    month（'YYYY-MM'，可选）：只被正文要点里的 VIX 用到（口径坑 21）——
    要靠英文月名确认那句话说的是本月而不是 pcp。不给就不取正文 VIX。
    """
    doc = fitz.open(path)
    try:
        rows = []
        for pi in range(doc.page_count):
            if skip_first_page and pi == 0:
                continue
            rows.extend(_page_rows(doc[pi]))
        vix_prose = _vix_from_prose(doc, month, skip_first_page)
    finally:
        doc.close()

    # (section, subsection, 标签键) -> 值；同键只认第一次出现
    table = {}
    section = sub = None
    for i, (label, vals) in enumerate(rows):
        k = _key(label)
        if not k:
            continue
        hit = _section_of(k)
        if hit and not vals:
            section, sub = hit, None
            continue
        if k in _SUBSECTIONS and not vals:
            sub = k
            continue
        v = _values_for(rows, i)
        if v:
            table.setdefault((section, sub, k), v)

    out, raw_cols = {}, {}
    for name, sec, want_sub, aliases, _since, _until in COLUMN_SPEC:
        for alias in aliases:
            if want_sub is not None:
                v = table.get((sec, want_sub, alias))
            else:
                # subsection 不限定：section 内该标签唯一（已逐月核过），
                # 但 subsection 会一直沿用到下一个小标题，所以要跨 subsection 找。
                cand = [vv for (s, _sb, lab), vv in table.items()
                        if s == sec and lab == alias]
                v = cand[0] if len(cand) == 1 else (None if not cand else cand[0])
            if v:
                out[name] = v[0]        # 口径坑 4：永远取值列从左数第 1 个
                raw_cols[name] = v      # 口径坑 23 的判据要看**整组**值列，不止第 1 个
                break

    # 口径坑 16：极少数期的量块「值列相对标签整体上移一行」（实测 127 期只有 2017-04）。
    # `_shifted_blocks` 用一条很窄的签名认出这种块并把值搬回原标签，搬回来的每一格
    # **先过 `_identity_gate` 再入库**：官方在同一张表里印的加总撞得上才算数，
    # 撞不上就当没看见（保持留空、打印原因），绝不硬写。已有值一律不覆盖。
    _who = month or os.path.basename(path)
    for sub, fixed in _shifted_blocks(rows):
        for name, _sec, want_sub, aliases, _since, _until in COLUMN_SPEC:
            if want_sub != sub or name in out:
                continue
            v = next((fixed[a] for a in aliases if a in fixed), None)
            if not v:
                continue
            ok, why = _identity_gate(dict(out, **{name: v[0]}), name)
            print('%s %s：排版错行还原值 %s —— %s，%s'
                  % (_who, name, v[0], why, '入库' if ok else '不入库，保持留空'))
            if ok:
                out[name] = v[0]

    # 口径坑 23：同一行小数点风格自证。放在这里（out 已建齐）而不是行循环里，
    # 是为了拿得到 CSV 列名 —— 判据要按 (数据月, 列名) 去查黑名单。
    #
    # ⚠ 已登记的格**跳过，不拦**：让它照旧流到 `_fetch_one` 里的 `_drop_source_errors()`，
    #   由那边「先核对错值还是那个错值，再删」。官方哪天重发修正版，那条核对会当场炸出来；
    #   如果在这里就把整月拦死，那条核对永远跑不到，我们就再也发现不了官方已经修好了。
    # month 为 None（不经 `_fetch_one` 的裸调用）时查不了黑名单，整条判据跳过。
    if month is not None:
        for name, v in raw_cols.items():
            if (month, name) in _KNOWN_SOURCE_GAPS:
                continue
            bad = _decimal_style_mixed(v)
            if bad:
                raise AsxFetchError(
                    '%s 的 %s 一行里小数点风格不一致：%s —— 几乎总是官方把千分位逗号'
                    '与小数点印反了（见模块 docstring 口径坑 19 / 23，2016-09 / 2020-01 / '
                    '2025-08 三次实测都是这个签名）。真值即使反推得出也不写替代值：'
                    '核对之后把这一格登记进 `_KNOWN_SOURCE_GAPS` 留空。拒绝写入'
                    % (month, name, bad))

    # 口径坑 21：VIX 在 2019-10 之前只印在正文要点里。
    # 两处都有时**必须逐位相同** —— 这条撞法是把「正文那句话就是表里那个数」
    # 从 26 期实测结论升格成永久闸门：官方哪天让两处不一致（换了口径、
    # 或正文改印月末值），这里当场炸，而不是让两种数悄悄混在同一列里。
    if vix_prose is not None:
        got = out.get('vix_asx200_avg')
        if got is None:
            out['vix_asx200_avg'] = vix_prose
        elif float(got) != float(vix_prose):
            raise AsxFetchError(
                '%s 的 S&P/ASX 200 VIX 表行印 %s、正文要点印 %s —— 两处不一致，'
                '说明官方把其中一处改了口径（见模块 docstring 口径坑 21），拒绝写入'
                % (month or os.path.basename(path), got, vix_prose))
    return out


def _assert_self_month(path, month):
    """核对 PDF 抬头自称的数据月与我们打算入库的月份一致。

    数据月是从**文件名**（媒体中心）或**公告标题**（存档）推出来的，两个来源都出过花样：
    文件名有驼峰无分隔的写法、中段还带着一个发布月；标题有不带年份的（那时靠
    「发布月 − 1」倒推）。推错了不会报错，只会把某个月的数字写到另一个月名下 ——
    而月份错位在图上看起来完全正常。这里让 PDF 自己作证，把那条路堵死。
    """
    doc = fitz.open(path)
    try:
        text = re.sub(r'\s+', ' ', '\n'.join(
            doc[i].get_text() for i in range(min(2, doc.page_count))))
    finally:
        doc.close()
    m = _SELF_TITLE.search(text)
    if not m:
        raise AsxFetchError('%s 抬头里找不到 "Monthly Activity Report <月> <年>"，'
                            '无法自证数据月' % os.path.basename(path))
    got = '%s-%02d' % (m.group(2), _MONTHS[m.group(1).lower()])
    if got != month:
        raise AsxFetchError('%s 自称是 %s 的月报，但我们按 %s 入库 —— '
                            '数据月推错了，拒绝写入'
                            % (os.path.basename(path), got, month))


def _pub_date(path):
    """PDF 首页正文第一行的发布日 -> ('YYYY-MM-DD', 出处文字)；读不出返回 (None, None)。

    这是 ASX 自己写在公告抬头上的日期，是「官方发布于 X」唯一合法的来源。
    读不出就让这半句缺席，绝不用下载时间 / Last-Modified / 按节奏推算的日子顶替
    —— 那些看上去一样体面，但都是我们编的。
    """
    doc = fitz.open(path)
    try:
        for label, _vals in _page_rows(doc[0]):
            m = _PUB_DATE.match(label)
            if m:
                d = datetime(int(m.group(3)), _MONTHS[m.group(2).lower()],
                             int(m.group(1)))
                return d.strftime('%Y-%m-%d'), (
                    '%s 第 1 页抬头 "%s"' % (os.path.basename(path), label))
    finally:
        doc.close()
    return None, None


def _sfe_urls(path):
    """从 MAR 里抠出当期分品种报告直链，**按可信度排序的列表**（可能为空）。

    不自己按「数据月最后一天」拼 URL：官方五年里换过 5 代命名、日期段 3 种写法
    （口径坑 22），拼出来的名字在 72 期里只有 2 期碰巧对。跟着官方印的走，
    官方哪天再改命名也不用改代码。

    正文文本与 PDF 链接注解**两条都收**，因为两条各自都有坏掉的月份：正文里的 URL 会
    换行断开（先用 `_URL_WRAP` 接回去），注解则有 8 期缺失、2 期多带句号、
    **2 期是陈的（2024-11 / 2024-12 都指向 240930）**。正文排在前面，注解兜底；
    哪一条是真的由 `parse_sfe()` 的首页抬头校验当场判定 —— 陈注解取回来的是一份
    合法但月份不对的 PDF，只有抬头认得出来。
    """
    out = []

    def add(u):
        u = (u or '').strip()
        if u and u not in out:
            out.append(u)

    doc = fitz.open(path)
    try:
        for pi in range(doc.page_count):
            for m in _SFE_LINK.finditer(_URL_WRAP.sub('', doc[pi].get_text())):
                add(m.group(0))
        for pi in range(doc.page_count):
            for lnk in doc[pi].get_links():
                m = _SFE_LINK.search(lnk.get('uri') or '')
                if m:
                    add(m.group(0))
    finally:
        doc.close()
    return out


# ══════════════════════════════════════════════════════════════════════
# 辅源解析：Monthly SFE Trading Report（分品种）
# ══════════════════════════════════════════════════════════════════════
_SFE_NUMCUT = 0.30          # 值列 x 起点 ~188，合约代码在 ~156，页宽 595
_SFE_SECTION = re.compile(
    r'^(equity indices|interest rates|commodities|nz interest rates|nz commodities)'
    r' - (futures|options)$', re.I)


def parse_sfe(path, month):
    """解析分品种报告，返回 {csv 列名: 值字符串}。

    列序固定为 [本月量, 去年同月量, %, 年初至今量, 去年同期量, %, 月末 OI, 去年月末 OI, %]，
    百分比与 'na' 不是数字会被 `_num` 丢掉，所以纯数字序列稳定是 6 个：
    index 0 = 本月量，index 4 = 月末未平仓。**不取 YTD**：这份报告的 YTD 是
    **日历年**（表头 "YTD 2026 (149-Days)"），而 MAR 的 YTD 是**财年**（7 月起算），
    两者混用即错（这里根本不入库，从源头断掉这个可能）。
    """
    doc = fitz.open(path)
    try:
        first = doc[0].get_text()
        head = 'Monthly SFE Trading Report for %s' % datetime.strptime(
            month, '%Y-%m').strftime('%B %Y')
        if head not in first:
            raise AsxFetchError('%s 首页抬头不是 %r —— 抓到的可能是别的月份'
                                % (os.path.basename(path), head))
        found = {}
        for pi in range(doc.page_count):
            page = doc[pi]
            cut = page.rect.width * _SFE_NUMCUT
            words = [w for w in page.get_text('words') if w[4].strip()]
            words.sort(key=lambda w: (round(w[1], 1), w[0]))
            buckets = []
            for w in words:
                y = (w[1] + w[3]) / 2.0
                for b in buckets:
                    if abs(b['y'] - y) <= _YTOL:
                        b['w'].append(w)
                        break
                else:
                    buckets.append({'y': y, 'w': [w]})
            section = None
            for b in sorted(buckets, key=lambda b: b['y']):
                ws = sorted(b['w'], key=lambda w: w[0])
                left = [w[4] for w in ws if w[0] < cut]
                nums = [n for n in (_num(w[4]) for w in ws if w[0] >= cut)
                        if n is not None]
                label = _norm(' '.join(left))
                if _SFE_SECTION.match(label):
                    section = label.lower()
                    continue
                if not left or not nums:
                    continue
                code = left[-1]
                if section and re.fullmatch(r'[A-Z]{2}', code):
                    found.setdefault((section, code), nums)
    finally:
        doc.close()

    out = {}
    for name, sec, code, which in SFE_SPEC:
        nums = found.get((sec, code))
        if not nums:
            raise AsxFetchError('分品种报告里找不到 %s / %s（%s）——'
                                '官方表结构可能已变' % (sec, code, name))
        if len(nums) != 6:
            raise AsxFetchError('分品种报告 %s / %s 一行取到 %d 个数字（应为 6 个：'
                                '本月/去年同月/YTD/去年YTD/OI/去年OI）：%s'
                                % (sec, code, len(nums), nums))
        out[name] = nums[0] if which == 'month' else nums[4]
    return out


# ══════════════════════════════════════════════════════════════════════
# 校验
# ══════════════════════════════════════════════════════════════════════
def _f(rec, name):
    v = rec.get(name)
    return None if v in (None, '') else float(v)


# (说明, 加数列名…, 合计列名, 容差)。官方自己在同一张表里印出来的加总关系。
# 这张表有两个用处，**必须是同一张表**，否则两处会各自漂移：
#   · `_check_identities()` —— 事后体检，不成立就炸；
#   · `_identity_gate()`    —— 事**前**闸门，排版错行还原出来的格子过不了就不许入库。
_IDENTITIES = [
    ('期货 + 期货期权 = 合计（总张数）',
     ['contracts_futures_total', 'contracts_options_on_futures_total'],
     'contracts_futures_and_options_total', 0.0),
    ('期货 + 期货期权 = 合计（ADV）',
     ['adv_futures_contracts', 'adv_options_on_futures_contracts'],
     'adv_futures_and_options_contracts', 1.5),              # 官方各自四舍五入到整张
    ('open + auctions + centre point + trade reporting = 现货总成交额',
     ['value_open_trading_audbn', 'value_auctions_audbn',
      'value_centrepoint_audbn', 'value_tradereport_audbn'],
     'value_cash_total_audbn', 0.002),
    ('open + auctions + centre point = on-market 成交额',
     ['value_open_trading_audbn', 'value_auctions_audbn',
      'value_centrepoint_audbn'], 'value_cash_onmarket_audbn', 0.002),
    ('二次融资 + 换股对价 = 二次融资合计',
     ['capital_secondary_audmn', 'capital_other_scrip_audmn'],
     'capital_secondary_total_audmn', 0.5),
]

# (说明, ADV 列, 交易日列, 月总量列)。官方在同一张表里**同时**印日均与月总量，
# 这层关系是乘法，与上面清一色的加法恒等式形状不同，所以单独一张表、单独一个相对容差：
# 加法那边的绝对容差随量级走不动（合计张数容差 0.0、成交额 0.002），乘法这边的残差
# 天生正比于量级（官方把 ADV 四舍五入到整张），只能按相对值判。
#
# 这张表是口径坑 23 补的。此前 `_IDENTITIES` 五条全是加法，**从设计上就不管单个数的
# 小数点位置**——2020-01 `adv_index_options_contracts` 印成 43.485（真值 43,485）
# 因此一路畅通到页面上，画成一根扎到零的刺。
#
# 容差 5e-3 的来历（实测，不是拍的）：128 个月 × 下面 5 组配对，合法残差最大
# 1.021e-3（2023-09 的期货期权），2020-01 那一格是 9.990e-1。合法侧留 5 倍余量，
# 与错值差两个数量级。
_RATE_TOL = 5e-3
_RATE_IDENTITIES = [
    ('期货 ADV × 交易日 = 期货月总张数',
     'adv_futures_contracts', 'trading_days_futures', 'contracts_futures_total'),
    ('期货期权 ADV × 交易日 = 期货期权月总张数',
     'adv_options_on_futures_contracts', 'trading_days_futures',
     'contracts_options_on_futures_total'),
    ('期货与期货期权 ADV × 交易日 = 合计月总张数',
     'adv_futures_and_options_contracts', 'trading_days_futures',
     'contracts_futures_and_options_total'),
    ('单股期权 ADV × 交易日 = 单股期权月总张数',
     'adv_single_stock_options_contracts', 'trading_days_eto',
     'contracts_single_stock_options_total'),
    ('指数期权 ADV × 交易日 = 指数期权月总张数',
     'adv_index_options_contracts', 'trading_days_eto',
     'contracts_index_options_total'),
]


def _check_identities(month, rec):
    """用官方自己在同一张表里印出来的加总关系做体检。

    这不是「算出缺的那一格」——缺的格一律留给 _validate 去炸；这是**证明我们没有串行**。
    口径坑 3 那类错误（section 切错、行错位）的特征是「每个数都合法，但装错了格子」，
    只有加总恒等式能当场发现。2017-04 那一期 PDF 值列整体上移一行（口径坑 16），
    就是被第 1 条抓出来的。
    """
    for desc, parts, total, tol in _IDENTITIES:
        pv = [_f(rec, p) for p in parts]
        tv = _f(rec, total)
        if tv is None or any(v is None for v in pv):
            continue                     # 该月官方没印这几行，交给 _validate 判
        if abs(sum(pv) - tv) > tol:
            raise AsxFetchError(
                '%s 加总恒等式不成立：%s —— %s 之和 %.6f，官方印的 %s = %.6f。'
                '这是解析串行的典型症状（见模块 docstring 口径坑 3 / 16），拒绝写入'
                % (month, desc, parts, sum(pv), total, tv))

    # 乘法一族（口径坑 23）：抓的不是「装错格子」，是**单个数的小数点位置错了**。
    # 加法恒等式对这类错天生无感 —— 错的那一格根本不参与任何加法。
    for desc, adv, days, total in _RATE_IDENTITIES:
        av, dv, tv = _f(rec, adv), _f(rec, days), _f(rec, total)
        if None in (av, dv, tv) or tv == 0:
            continue                     # 该月官方没印齐这三行，交给 _validate 判
        rel = abs(av * dv - tv) / abs(tv)
        if rel > _RATE_TOL:
            raise AsxFetchError(
                '%s 乘法恒等式不成立：%s —— %s=%s × %s=%s = %.6f，官方印的 %s = %.6f，'
                '相对残差 %.3e > 容差 %.0e。几乎总是官方把千分位逗号与小数点印反了'
                '（见模块 docstring 口径坑 19 / 23），拒绝写入'
                % (month, desc, adv, av, days, dv, av * dv, total, tv, rel, _RATE_TOL))


def _identity_gate(rec, name):
    """`name` 这一格能不能入库 -> (True|False, 说明)。**先验后写**专用（口径坑 16）。

    只被排版错行的还原路径调用。与 `_check_identities` 的区别是**举证责任反过来**：
    那边「成员不齐就跳过」（缺格交给 _validate），这边「成员不齐就否决」——
    还原值是我们从错行里搬回来的，没有独立证据就不许进 CSV。三条否决：
      · 这一列不参与任何加总恒等式  ⇒ 没有闸门可用，不放行；
      · 它参与的某条恒等式成员不齐  ⇒ 验不了，不放行；
      · 任何一条不成立              ⇒ 搬错了，不放行。
    """
    used = []
    for desc, parts, total, tol in _IDENTITIES:
        if name not in parts:
            continue
        pv = [_f(rec, p) for p in parts]
        tv = _f(rec, total)
        if tv is None or any(v is None for v in pv):
            return False, '「%s」成员不齐（%s / %s），无法验证' % (desc, parts, total)
        if abs(sum(pv) - tv) > tol:
            return False, ('「%s」不成立：%s 之和 %.6f，官方印的 %s = %.6f'
                           % (desc, parts, sum(pv), total, tv))
        used.append('「%s」%.6f = %.6f ✔' % (desc, sum(pv), tv))
    if not used:
        return False, '%s 不参与任何加总恒等式，无从验证' % name
    return True, '；'.join(used)


def _in_window(month, since, until):
    return (since is None or month >= since) and (until is None or month <= until)


# 单格黑名单：{(数据月, 列名): (官方那一期印的原样字符串 | None, 理由)}。
#
# 这张表**只登记「官方那一期 PDF 自己坏了」的单格**，不登记「本模块还没写好解析」的。
# 判据是能不能指出坏在哪一行 —— 指不出来就说明是我们的解析有问题，该去修解析。
# 两种坏法，用第一个元素区分：
#   · None       = 那一格在 PDF 里**取不到值**（排版错行，值列落空）。`_validate` 放行空。
#   · '4.852' 等 = 那一格**取得到，但官方印错了**。`_drop_source_errors()` 先核对我们
#                  解析出来的确实就是这个错值，再**删掉它**，于是也走上面那条放行。
#
# 一律**留空，不写替代值**。恒等式能反推、后一期报告的 pcp 列也印着正确值，但那两种
# 都不是「当期官方公告原值」：写进去就再也分不清哪些数是 ASX 印的、哪些是我们凑的。
# 空格在图上是断笔（一个月），比一个看不出来的错数好得多。
# ⚠ 「不写替代值」管的是**我们算出来的数**。2017-04 那两格现在有值了，走的不是替代值 ——
#   `_shifted_blocks` 把官方印在纸上的那两个数搬回了它们本该挂的标签（口径坑 16），
#   入库的仍是当期公告原值。那两条登记因此降级为**兜底**：签名哪天认不出来、
#   或还原值过不了 `_identity_gate`，这一格退回留空而不是让整月炸。
#
# 黑名单只处理这几格，不放行「值可疑但没登记」—— 未登记的格照常走 `_check_identities`。
_KNOWN_SOURCE_GAPS = {
    # 口径坑 16：2017-04 那一期官方 PDF 的期货期权小块**值列整体上移一行**。
    # 实测行流（未改动的 `_page_rows`）：
    #     rows[96] 'Options on futures volume'（小标题）挂着 ['124649','144826',…]
    #     rows[97] 'Total contracts'            空
    #     rows[98] 'Change on pcp'              挂着 ['6925','6896',…]
    #     rows[99] 'Average daily contracts'    空
    # 对照 2017-03 同一段：rows[96] 小标题空、rows[97] 'Total contracts' 带值 —— 版式没变，
    # 是这一期排版坏了。
    #
    # ⇒ **2026-08 起这两格不再留空**：`_shifted_blocks()` 用「小标题带值 + Average daily
    #   contracts 整行为空」这条签名认出错行块，把值搬回原标签（只搬不算），
    #   再由 `_identity_gate()` 拿官方同表印的合计做**准入闸门**，两条都撞上才入库：
    #       8,901,810 + 124,649 = 9,026,459 ✔（残差 0）
    #         494,545 +   6,925 =   501,470 ✔（残差 0；该式容差 1.5 是官方各自舍入的余量）
    #   入库的 124,649 / 6,925 是官方印在第 3 页 y=374.23 / y=400.99 两条基线上的原值，
    #   不是恒等式反推出来的数 —— 恒等式在这里只当验钞机，不当计算器。
    # 下面这两条登记保留为**兜底**：签名认不出或闸门不放行时，这一格退回留空，
    # `_validate` 照旧放行（打印原因，不炸整月）。
    ('2017-04', 'contracts_options_on_futures_total'):
        (None, '官方 PDF 值列错行（口径坑 16）；已由签名检测搬回原标签、'
               '两条恒等式已验 ⇒ 正常情况下有值，此条仅兜底'),
    ('2017-04', 'adv_options_on_futures_contracts'):
        (None, '官方 PDF 值列错行（口径坑 16）；已由签名检测搬回原标签、'
               '两条恒等式已验 ⇒ 正常情况下有值，此条仅兜底'),

    # 口径坑 19：2016-09 那一期把千分位逗号印成了小数点。
    #     'Average value per trade ($)'  ['4.852', '5710', '4.701', '5784']
    # 四列里两列带点、两列不带 —— 同一行同一个单位，不可能既是 4.852 又是 5710。
    # 底层字符实测是真的 U+002E（不是渲染成句点的逗号），所以解析没错，是印错了。
    # 两条独立证据指向真值 4,852：
    #   ① 官方在同一张表里印的成交额与笔数：108.913e9 ÷ 22,449,067 = 4,851.6；
    #   ② 2017-09 那一期的「去年同月」列印的是 4852（同一家、同一个月、印对了）。
    # 但这两个都不是**当期公告原值**，所以这一格留空。
    ('2016-09', 'avg_value_per_trade_aud'):
        ('4.852', '官方 2016-09 期把千分位逗号印成小数点（口径坑 19），真值 4,852 '
                  '只能由别处佐证 ⇒ 留空'),

    # 口径坑 23：同一类错印在 2020-01 与 2025-08 各复发一次，方向互为镜像。
    # 2026-09 用媒体中心索引下载两期原件、PyMuPDF `rawdict` 逐字符核过，坏字符是真的
    # U+002E / U+002C（Calibri / ArialMT 正文字体，与同行其余数字同字号同字体），
    # 既不是渲染伪影，也不是 `_num()` 解析错 —— 是官方自己印错：
    #     2020-01 ['43.485', '35,544', '36,901', '46,281']  本月列印成小数点
    #     2025-08 ['166,019', '142.742', '316.749', '271.170']  本月列印成千分位逗号
    # 两条反推都精确到底（913,176 ÷ 21 = 43,484.57；FY YTD 316.749 − 上月 150.730
    # = 166.019），**但仍然不写替代值** —— 它们与坑 19 已经明令拒绝的
    # 108.913e9 ÷ 22,449,067 = 4,851.6 是同一类反推（同一张表里另外两个数相除/相加）。
    # 若因为「这两例反推更准」就破例，那条纪律就变成了「反推不够准才不许填」，
    # 从此没有客观标准。⇒ 一律留空。
    ('2020-01', 'adv_index_options_contracts'):
        ('43.485', '官方 2020-01 期把指数期权 ADV 的千分位逗号印成小数点（口径坑 23），'
                   '真值 43,485 只能由同表 913,176 ÷ 21 反推 ⇒ 留空'),
    ('2025-08', 'billable_cash_cleared_audbn'):
        ('166019', '官方 2025-08 期把可计费现货清算额的小数点印成千分位逗号'
                   '（口径坑 23，与坑 19 方向相反），真值 166.019 只能由同表 FY YTD 列'
                   '316.749 − 上月 150.730 反推 ⇒ 留空'),
}

# 列名写错的黑名单条目会**静默失效**（那一格照旧被 `missing` 拦下，而黑名单那条谁也没在用），
# 所以在 import 期就撞一次。
_bad_gap = [k for k in _KNOWN_SOURCE_GAPS if k[1] not in MAR_COLUMNS]
if _bad_gap:
    raise AsxFetchError('_KNOWN_SOURCE_GAPS 里有不存在的列名：%s' % _bad_gap)


def _drop_source_errors(month, rec):
    """删掉黑名单里「官方印错了」的那几格，删之前先核对错值还是那个错值。

    为什么要核对而不是闷头删：官方随时可能重发一份修好的 PDF（口径坑 17 就发生过 4 次），
    到那天这一格会变成正确值，而闷头删会把**已经修好的官方数据**继续扔掉，
    并且永远没人发现。核对不上就炸，逼人来看一眼那一期到底变成什么样了。
    """
    for (mon, name), (printed, why) in _KNOWN_SOURCE_GAPS.items():
        if mon != month or printed is None:
            continue
        got = rec.get(name)
        if got is None:
            continue                    # 本来就没取到，交给 `_validate` 按空处理
        if got != printed:
            raise AsxFetchError(
                '%s 的 %s：黑名单登记的官方错值是 %r，这次解析出来的是 %r —— '
                '要么官方重发了修正版（那就把这条从 _KNOWN_SOURCE_GAPS 删掉、'
                '让真值入库），要么本模块的解析变了。两种都得人来看，拒绝写入。'
                '（登记理由：%s）' % (month, name, printed, got, why))
        del rec[name]


def _validate(month, rec):
    """界内为空一律炸。宁可整月不更新，也不要写出一列悄悄全空的 CSV。"""
    missing = [name for name, _s, _sb, _a, since, until in COLUMN_SPEC
               if _in_window(month, since, until) and not rec.get(name)
               and (month, name) not in _KNOWN_SOURCE_GAPS]
    if missing:
        raise AsxFetchError(
            '%s 解析缺列 %s —— 官方表结构可能已变，或抓到的是 ASX Compliance 版'
            '（见模块 docstring 口径坑 1），拒绝写入' % (month, missing))
    stray = [name for name, _s, _sb, _a, since, until in COLUMN_SPEC
             if not _in_window(month, since, until) and rec.get(name)]
    if stray:
        raise AsxFetchError(
            '%s 解析出了本不该存在的列 %s —— 官方要么恢复了旧行名、要么本模块的'
            'since/until 边界记错了，两种都得人来看，拒绝写入' % (month, stray))
    _check_identities(month, rec)


# ══════════════════════════════════════════════════════════════════════
# 单月抓取
# ══════════════════════════════════════════════════════════════════════
def _download_mar(month, url, is_correction, cache_dir):
    path = os.path.join(cache_dir, 'asx_mar_%s%s.pdf'
                        % (month, '_correction' if is_correction else ''))
    if not os.path.exists(path):
        _write_bytes(path, _http_pdf(url))
    _assert_self_month(path, month)
    return path


def _fetch_one(month, urls, cache_dir, want_sfe=True):
    """下载并解析某一个月，返回 (记录 dict, 发布日, 出处文字)。

    urls = {'orig': url|None, 'corr': url|None}。
    **数值取更正稿，发布日取原版** —— 理由见 _discover_media_centre 的 docstring。
    """
    os.makedirs(cache_dir, exist_ok=True)
    if not (urls.get('orig') or urls.get('corr')):
        raise AsxFetchError('%s 既没有原版也没有更正稿的链接' % month)
    corr_path = (_download_mar(month, urls['corr'], True, cache_dir)
                 if urls.get('corr') else None)
    orig_path = (_download_mar(month, urls['orig'], False, cache_dir)
                 if urls.get('orig') else None)

    path = corr_path or orig_path
    rec = parse_mar(path, skip_first_page=bool(corr_path), month=month)
    # 先剔掉「官方那一期自己印错」的单格（口径坑 19），再校验 —— 顺序不能反：
    # 错值留在 rec 里会让 `_check_identities` 报一条与真实原因无关的恒等式失败。
    _drop_source_errors(month, rec)
    _validate(month, rec)
    day, evidence = _pub_date(orig_path or corr_path)

    # 分品种（辅源）：抓不到不让整月失败 —— 那 8 列在 series 里留空，_validate 不管它们。
    if want_sfe:
        rec.update(fetch_sfe(month, path, cache_dir)[0])
    return rec, day, evidence


def fetch_sfe(month, mar_path, cache_dir):
    """下载并解析当月分品种报告 -> ({列: 值}, [失败说明])；拿不到返回 ({}, 原因列表)。

    MAR 里印的候选链接逐条试，**第一条能解析出当月数据的胜出**。判定「能解析」靠
    `parse_sfe()` 的首页抬头校验，不是 HTTP 状态 —— 2024-11 / 2024-12 的陈注解会
    200 回来一份完全合法的 9 月报告（口径坑 22），只有抬头能把它挡掉。

    先落临时文件再 `os.replace`：解析失败的那份**不会**盖掉 cache 里已有的原件。
    """
    spath = os.path.join(cache_dir, 'asx_sfe_%s.pdf' % month)
    why = []
    if os.path.exists(spath):
        try:
            return parse_sfe(spath, month), why
        except AsxFetchError as e:                        # 缓存里那份不对，重下
            why.append('缓存 %s：%s' % (os.path.basename(spath), e))
    for url in _sfe_urls(mar_path):
        tmp = spath + '.new'
        try:
            _write_bytes(tmp, _http_pdf(url))
            out = parse_sfe(tmp, month)
        except AsxFetchError as e:
            if os.path.exists(tmp):
                os.remove(tmp)
            why.append('%s：%s' % (url, e))
            continue
        os.replace(tmp, spath)
        return out, why
    if not why:
        why.append('MAR 正文与链接注解里都没有分品种报告直链')
    return {}, why


# ══════════════════════════════════════════════════════════════════════
# 发布日台账
# ══════════════════════════════════════════════════════════════════════
def _source_dates():
    """按路径加载仓库根的 source_dates.py。

    不能裸 import：本模块被 monthly_run 用 spec_from_file_location 加载，
    那时 sys.path 上既没有 fetch/ 也没有仓库根。
    """
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(root, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ══════════════════════════════════════════════════════════════════════
# 对外接口
# ══════════════════════════════════════════════════════════════════════
def latest_month(cache_dir):
    """官方源当前最新的数据月 'YYYY-MM'。

    只读媒体中心索引，不下载 PDF —— 「本月发了没有」这个问题索引页就能回答。
    抓不到 / 读不出一律抛 AsxFetchError，不返回 None 掩盖故障。
    """
    os.makedirs(cache_dir, exist_ok=True)
    return max(_discover_media_centre(cache_dir))


def _read_csv(csv_path):
    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    header = rows[0]
    body = [r for r in rows[1:] if r and r[0].strip()]
    return header, body


def _write_csv(csv_path, header, body):
    body.sort(key=lambda r: r[0])
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        w.writerows(body)


def update(series_dir, cache_dir):
    """把新月份追加进 series/asx.csv，返回新增月份列表（升序）。

    幂等保证：
      · 已存在的月份不重复追加；
      · 已经有值的单元格**永不覆盖** —— ASX 会在同一天补发更正稿改数（口径坑 17），
        也偶尔在后续月报的 pcp 列里体现重述。让自动流程去改历史，等于把「官方悄悄
        改过数」这件事永久掩盖掉；要重刷历史请人工重跑 `--backfill`。
      · 只在既有行**原本为空**的格子上回补。目前唯一会用到的是分品种那 8 列：
        MAR 与分品种报告偶尔不同时上线，上个月那行可能还空着 —— 顺手补一次。
        （更早的空洞不在 cron 的职责里，人工跑 `--sfe-backfill`：那条源官方一直留着，
        补一次就固化进 CSV，见 docstring 辅源节。）
      · 未被触碰的单元格是原样字符串搬运，所以「什么都没变」时文件字节级不变。
    """
    csv_path = os.path.join(series_dir, 'asx.csv')
    header, body = _read_csv(csv_path)
    idx = {name: i for i, name in enumerate(header)}
    unknown = [c for c in CSV_COLUMNS if c not in idx]
    if unknown:
        raise AsxFetchError('series/asx.csv 里没有这些列：%s' % unknown)

    index = _discover_media_centre(cache_dir)
    have = {r[0]: r for r in body}
    newest = max(index)

    # 要处理的月份：CSV 里还没有的（不早于 SERIES_START），
    # 外加最新那一个月的前一月 —— 后者是为了给分品种那 8 列留一次回补机会。
    todo = sorted(m for m in index if m >= SERIES_START and m not in have)
    prev = _month_shift(newest, -1)
    if prev in have and prev in index and not have[prev][idx[SFE_COLUMNS[0]]].strip():
        todo.append(prev)

    pub = {}
    added = []
    for mon in sorted(set(todo)):
        # 分品种辅源在 SFE_START 之前一条必然失败（老站点路径整体 soft-404），
        # 挨个去敲既拖慢自己也是给对方站点添堵 —— 所以按天花板挡掉。
        rec, day, evidence = _fetch_one(
            mon, index[mon], cache_dir, want_sfe=(mon >= SFE_START))
        if day:
            pub[mon] = (day, evidence)
        if mon in have:
            row = have[mon]
            for name in CSV_COLUMNS[1:]:            # 只填空，不覆盖
                if not row[idx[name]].strip() and rec.get(name):
                    row[idx[name]] = rec[name]
            continue
        row = [''] * len(header)
        row[0] = mon
        for name in CSV_COLUMNS[1:]:
            row[idx[name]] = rec.get(name, '')
        have[mon] = row
        body.append(row)
        added.append(mon)

    _write_csv(csv_path, header, body)

    # 记发布日放在落盘之后：写盘失败就不该在台账上留下「这个月官方发过了」这条断言。
    sd = _source_dates()
    for mon in sorted(pub):
        if mon in have and not sd.lookup(series_dir, 'asx', mon):
            sd.record(series_dir, 'asx', mon, pub[mon][0], pub[mon][1])
    return sorted(added)


def _month_shift(month, delta):
    y, m = int(month[:4]), int(month[5:])
    m += delta
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return '%04d-%02d' % (y, m)


def _month_range(start, end):
    out = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur = _month_shift(cur, 1)
    return out


# ══════════════════════════════════════════════════════════════════════
# 历史回补（**人工跑，cron 不碰**）
# ══════════════════════════════════════════════════════════════════════
def _backfill(series_dir, cache_dir, start, end):
    """用公告存档把 [start, end] 补进 series/asx.csv。

    走这条路是因为媒体中心只到 2020-02，再往前只有公告存档有。存档取 PDF 要经过
    一页「点击即接受使用条款」的同意表单 —— 技术上纯 GET 就能读到隐藏字段里的真实直链
    （不 POST、不带 cookie），但让 cron 每月自动穿过它是策略决定，所以这条路
    **只由人显式调用一次**，结果固化进 CSV 之后再也不需要跑。
    """
    csv_path = os.path.join(series_dir, 'asx.csv')
    header, body = _read_csv(csv_path)
    idx = {name: i for i, name in enumerate(header)}
    have = {r[0]: r for r in body}

    index = {}
    titles = {}
    for year in range(int(start[:4]), int(end[:4]) + 2):
        for mon, ids, title, _day, corr in _discover_archive(year):
            if not (start <= mon <= end):
                continue
            index.setdefault(mon, {})['corr' if corr else 'orig'] = ids
            titles.setdefault(mon, []).append(title)

    missing = [m for m in _month_range(start, end) if m not in index]
    if missing:
        raise AsxFetchError('公告存档里找不到这些月份的 MAR：%s' % missing)

    sd = _source_dates()
    added = []
    for mon in _month_range(start, end):
        urls = {k: _archive_pdf_url(v) for k, v in index[mon].items()}
        title = ' + '.join(titles[mon])
        rec, pubday, evidence = _fetch_one(mon, urls, cache_dir, want_sfe=False)
        if mon in have:
            row = have[mon]
            for name in CSV_COLUMNS[1:]:
                if not row[idx[name]].strip() and rec.get(name):
                    row[idx[name]] = rec[name]
        else:
            row = [''] * len(header)
            row[0] = mon
            for name in CSV_COLUMNS[1:]:
                row[idx[name]] = rec.get(name, '')
            have[mon] = row
            body.append(row)
            added.append(mon)
        if pubday and not sd.lookup(series_dir, 'asx', mon):
            sd.record(series_dir, 'asx', mon, pubday, evidence)
        print('  %s  %s  (%s)' % (mon, pubday or '发布日读不出', title))
    _write_csv(csv_path, header, body)
    return sorted(added)


def _sfe_backfill(series_dir, cache_dir, start, end):
    """把**分品种那 8 列**补进 series/asx.csv（人工跑一次，cron 不碰）。

    与 `_backfill()` 的区别：这条路 **只走媒体中心**（MAR 在那里从 2019-12 起齐全），
    再从 MAR 正文里印的直链取分品种报告 —— **全程不碰公告存档的那张同意页**。
    只填既有行里**原本为空**的格子，一格已有值都不覆盖；CSV 里没有的月份跳过并报出来
    （那 8 列是辅源，不该由它去新建行）。
    """
    csv_path = os.path.join(series_dir, 'asx.csv')
    header, body = _read_csv(csv_path)
    idx = {name: i for i, name in enumerate(header)}
    missing_cols = [c for c in SFE_COLUMNS if c not in idx]
    if missing_cols:
        raise AsxFetchError('series/asx.csv 里没有这些列：%s' % missing_cols)
    have = {r[0]: r for r in body}
    index = _discover_media_centre(cache_dir)

    filled, skipped = [], []
    for mon in _month_range(max(start, SFE_START), end):
        row = have.get(mon)
        if row is None:
            skipped.append((mon, 'series 里没有这一行（先跑 update / --backfill）'))
            continue
        blanks = [c for c in SFE_COLUMNS if not row[idx[c]].strip()]
        if not blanks:
            continue                                   # 已有值：永不覆盖
        if mon not in index:
            skipped.append((mon, '媒体中心索引里没有这个月的 MAR'))
            continue
        urls = index[mon]
        mar = (_download_mar(mon, urls['corr'], True, cache_dir) if urls.get('corr')
               else _download_mar(mon, urls['orig'], False, cache_dir))
        rec, why = fetch_sfe(mon, mar, cache_dir)
        # 只在这条**人工一次性**路径上限速：一轮要敲七十几份 PDF，
        # cron 那条路每月只发 1 次请求，不需要也不该被这半秒拖住。
        time.sleep(0.5)
        if not rec:
            skipped.append((mon, '；'.join(why)))
            continue
        for c in blanks:
            if rec.get(c):
                row[idx[c]] = rec[c]
        filled.append(mon)
        print('  %s  %s' % (mon, '  '.join('%s=%s' % (c, rec[c]) for c in SFE_COLUMNS)))
    _write_csv(csv_path, header, body)
    for mon, reason in skipped:
        print('  跳过 %s：%s' % (mon, reason))
    return filled


if __name__ == '__main__':
    import sys
    _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _series, _cache = os.path.join(_here, 'series'), os.path.join(_here, 'cache')
    if len(sys.argv) >= 2 and sys.argv[1] == '--backfill':
        print('backfilled:', _backfill(_series, _cache, sys.argv[2], sys.argv[3]))
    elif len(sys.argv) >= 2 and sys.argv[1] == '--sfe-backfill':
        print('sfe filled:', _sfe_backfill(_series, _cache, sys.argv[2], sys.argv[3]))
    else:
        print('latest:', latest_month(_cache))
        print('added :', update(_series, _cache))
