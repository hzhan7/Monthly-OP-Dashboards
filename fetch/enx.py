# -*- coding: utf-8 -*-
"""Euronext（ENX）月度经营指标 —— 无人值守抓取。

Euronext 是本仓唯一一家「多国合并体」：一个法人实体下面挂着 8 个市场 ——
官方月度新闻稿的电头逐字写着 "Amsterdam, Athens, Brussels, Dublin, Lisbon, Milan,
Oslo and Paris"（2026-06 那期实测原文）。每一列数字都是若干个市场之和，
而**这个和的成员随时间变**。所以这份 docstring 里「每一列含哪些市场、从哪个月起含」
比数字本身更要紧 —— 数字抓错下个月就露馅，口径写错可以安静地错三年。

━━ 数据源 ━━
落地页 : https://www.euronext.com/en/investor-relations         锚点 <h2 id="monthly-volumes">
直链   : https://live.euronext.com/sites/default/files/statistics/ir/
         euronext_monthly_historical_volumes.xlsx
         5 个 sheet，Period 行自 2012-01 起逐月往下长。
         ⚠ 字节数与月数**每月都变**，下面这组是快照不是常量：
           220,465 bytes、2012-01 → 2026-07 共 175 个月（2026-08-18 对 cache 副本实测；
           上一次记录是 2026-08-06 的 219,581 bytes / 到 2026-06 / 174 个月）。
         要当前值就自己数：`openpyxl.load_workbook(...)['Equity Markets']` 的 Period 列。
伴生   : .../euronext_latest_month_volumes.xlsx
         47,476 bytes（2026-08-18 实测，同样每月变），只有最新月/上月/去年同月/本季/YTD
         五档，**并且给出官方算好的 ADV**。
         本模块只拿它做「最新月」这一列的对表自检，绝不拿它核对历史（理由见口径坑 6）。
发布日 : https://www.euronext.com/en/investor-relations/financial-information/news?page=N
         月度新闻稿列表，每行一个 <time datetime="2026-07-06T15:45:00Z">06/07/2026</time>。

**文件名固定、不带月份**，每月原地覆盖，永远指向最新一期 —— 与 CME 的 monthly-volume
别名同类。别去猜带月份的直链，那种链接这里根本不存在。

为什么还要先取落地页：不是为了拿文件名（文件名是写死的），是为了确认这个文件**还挂在
官方 IR 页上**。哪天 Euronext 换了文件名，直链多半还能下到一个再也不更新的孤儿文件 ——
那种故障不会报错，只会让序列悄悄停在某个月。落地页正则找不到这条 href 时打醒目警告
但仍然继续（直链本身也可能只是页面模板改了），真正的护栏是下面那一堆结构与恒等式校验。

抓取方式：`urllib.request` 裸奔即可。实测无 Cloudflare / Akamai 挑战、无 JS 渲染、
无登录墙、无 JA3 指纹拦截，`server: CloudFront`。**满足无人值守**。
唯一要注意的是 `www.euronext.com`（Drupal 主站，取新闻列表页用）**连续快速请求会掐连接**，
抛 RemoteDisconnected —— 所以列表页那条路径带 retry + backoff + 请求间隔；
`live.euronext.com` 的 CDN 静态文件没有这个问题。

依赖只有 openpyxl（仓里已有）。

━━ 发布节奏 ━━
每月都发，**没有季末月例外**（不像 SCHW / LPLA 要等季报）。下面这组是一次性普查的结果
（2026-08-06 那次跑）：把新闻列表页翻了 22 页（440 条稿件），
对 **2019-01 → 2026-06 共 90 个数据月逐月找它自己那期稿子，命中 90/90**：

    发布日落在次月第 3 至第 13 天，中位数第 7 天。
    最晚：2024-04 数据 → 2024-05-13（第 13 天，**90 期里仅此一次**）
    最早：第 3 天出现过 4 次（2020-03 / 2020-06 / 2020-08 / 2021-12 的数据月）

给 build/roster.py 的建议是 `LAG = (13, 13)`（两值相同）。
⚠ 闸门提前量必须写成**元组** `EARLY_BY['enx'] = (11, 11)` —— monthly_run.py 的取值处是
`EARLY_BY.get(t, (EARLY, EARLY))[1 if qe else 0]`，写成裸整数 `11` 会在下标那一步
TypeError，**崩掉的是整轮 monthly_run，不只是 enx 这一家**。
为什么是 11 不是 10：13−11 = 次月第 2 天开闸，比实测最小值（第 3 天）早一天；
第 3 天出现过 4 次，不是孤例，零余量迟早会漏。代价只是每月多一两个「还没发」的
HTTP 请求，对方是 220KB 的 CDN 静态文件。

发布日只认**新闻稿列表页的 `<time datetime>`**，记进 series/source_dates.csv。
⚠ 不要去详情页找 JSON-LD 的 `datePublished`：**那个字段在页面上根本不存在**
（详情页只有一个 ld+json 块，内容是面包屑导航）。页面上真正存在的是 <time datetime>。
详情页正文电头（"Amsterdam, Athens, Brussels, Dublin, Lisbon, Milan, Oslo and Paris
– 6 July 2026 –"）作为第二处佐证写进 evidence，取不到就不写，不猜。

━━ 口径坑（按踩坑概率排序）━━

**1. 2025-11 起并入雅典交易所（ATHEX），全表主列在这一个月同时发生断点。**
   并购时间线（本机从 IR 新闻列表页 22 页 440 条标题里逐条读出来的，不是转述）：
   2025-07-31 宣布将发起换股要约 → 2025-10-06 要约启动 → 2025-11-14 拿到希腊资本市场
   委员会批准 → **2025-11-19 宣布要约成功**。所以并表落在 2025-11，与官方脚注写死的
   "…and Euronext Athens since November 2025" 一致；月度稿电头也是从 2025-11 那期
   （2025-12-05 发）起出现 "Athens" 的。
   📌 未找到：「2026-04 完成改名 Euronext Athens」这个日期本机**没能核实**。
   检索路径：IR 新闻列表页 `?page=0..21`（440 条标题）按 rebrand / renam / becomes /
   "Euronext Athens" / integration / migrat 六个关键词过滤 2026 年稿件，**零命中**。
   本模块不依赖这个日期（口径断点只认 2025-11），所以不写进代码，也不要有人回头补上
   一个没核过的日子。
   官方同时在**每一个主指标右侧**配了一列
   表头写死为 `Athex` 的备注列，语义随月份翻转：

     · 2025-10 及以前：主列**不含** Athex，备注列 = Athex 单独数
       ⇒ 主列 + 备注列 = 官方口径的 pro-forma（可比口径）
     · 2025-11 及以后：主列**已含** Athex，备注列 = 主列里属于 Athex 的那一块
       ⇒ 主列 − 备注列 = legacy Euronext（旧口径）

   本模块把主列与 Athex 备注列**都写进 CSV**（`athex_*` 前缀），让 build 层自己决定
   画哪条。只写主列 = 把断点焊死在数据里，之后谁也修不回来。
   跨 2025-11 的同比**不可直接比**，图上必须画红色断点竖线。
   ⚠ 唯一的例外是股票清算量（adv_shares_cleared_kcontracts）。2026-08 版起官方把雅典按新计数
   口径 pro-forma 并进了这一列有数的**全部**月份（2022-01 起，证据链见 ACCEPTED_RESTATEMENTS），
   它的备注列在每个月都是「主列里属于雅典的那一块」，语义不翻转，2025-11 也不是这一列的断点。
   但 Equity Markets 脚注 (3) 挂在整个现货分组头上、仍写着 "since November 2025"，
   series/enx_breaks.csv 照抽不误 —— 不画这一条红线是页面那一侧（build/specs/enx.py）的事。

   验证（本机实测，非引用）：官方 Q2 2026 业绩稿第 13 页明写 "Q2 2025 volumes are
   including Euronext Athens on a pro forma basis"，其 Q2 2025 备考值
   股指 10,796,110 / 单股 22,791,315，与 xlsx「主列+备注列」**一位不差**；
   Q2 2026 主列本身 10,212,541 / 25,104,143，与官方当期**一位不差**。两个方向都能精确重建。

**2. 单股衍生品是全表最危险的一列：Athex 占并表后的 90-98%，且有季度换月脉冲。**
   实测主列 Individual Equity Futures 月合计张数：2025-10 = 35,573 → 2025-11 = 836,511
   （其中 Athex 781,183，占 93.4%）→ 2026-06 = 5,057,868（其中 Athex 4,958,445，占 98.0%）。
   两件事同时成立：(a) 2025-11 那一格是 **20 倍以上的口径断点**，不是业务增长；
   (b) 并表后这条线在 3/6/9/12 月出现 5-7 倍脉冲（希腊单股期货被当作融券/回购替代品
   按季滚动），不是成交活跃度信号。⇒ 同比一律用 pro-forma（主+备注）口径；
   与 Cboe 的 multilist options 对比必须先取 legacy（主−备注）；year_lines 类图对它无意义。
   相比之下 Athex 单股**期权**可忽略（几百到 1 万张/月）。

**3. 三个更早的并表断点，且现货/衍生品/上市统计三套序列的断点月份各不相同。**
   官方脚注原文（从 xlsx 直接读的，不是转述）：

     现货     (Equity Markets 脚注 3)：Dublin since January 2017, Oslo since January 2018,
              Borsa Italiana since May 2021, Euronext Athens since November 2025
     衍生品   (Equity Markets 脚注 5)：Oslo since July 2019, Borsa Italiana since May 2021,
              Euronext Athens since November 2025
     上市统计 (Capital Markets 脚注 1)：Dublin and Oslo since January 2019,
              Borsa Italiana since May 2021, Euronext Athens since November 2025
     商品     (FICC 脚注 3)：Oslo Bors since July 2019
     固收现券 (FICC 脚注 2)：同现货那一套
     CSD      (Securities Services 脚注 1)：Euronext Athens since November 2025

   ⇒ 现货 ADV 图的断点竖线是 **2017-01 / 2018-01 / 2021-05 / 2025-11**；
     衍生品是 **2019-07 / 2021-05 / 2025-11**（外加电力衍生品首月 2026-03）；
     上市统计是 **2019-01 / 2021-05 / 2025-06 / 2025-11**。
     三套不要混用同一组竖线 —— 把 2019-01 当成现货断点是常见错误，现货那年没有断点。

**4. 这份 xlsx 是「按今天口径重述过的」序列，与当年新闻稿印出来的数字对不上，方向还会翻。**
   实测同一指标三个时点：2019-01 现货 ADV xlsx 7,140.4 €m vs 当年稿 6,708.1 €m（+6.4%，
   往上重述：xlsx 把 Oslo 从 2018-01 就算进去了，而 Oslo Børs 2019-06 才完成收购）；
   2020-06 现货月成交额 xlsx 234,385.7 €m vs 当年稿 244,406.7 €m（−4.1%，往下重述）。
   同一次测试里**衍生品张数一格不差**（2020-06 六个 futures/options 单元格全部完全相等）。
   ⇒ 结论不是「xlsx 错了」，而是 xlsx 内部自洽、当年新闻稿之间不自洽。本仓只认 xlsx，
   且**绝不能**把某一期新闻稿的数字手工补进序列 —— 那会插进一个 4-6% 的假台阶。
   本模块因此对已入库的值**永不覆盖**，冲突写 cache/enx_restatements.csv 供人工判断。
   唯一的出口是 ACCEPTED_RESTATEMENTS：人核过一批冲突之后，把「列 × 月份区间」连同逐格
   「旧值 → 新值」的指纹登记进去，update() 整批对上才覆盖，差一格都不动。
   最大的一条是 **2026-08 版的股票清算量整列重述**（官方把雅典换成新的计数口径并
   pro-forma 回填到 2022-01，adv_shares_cleared_kcontracts 与其 athex 备注列 2022-01..2026-06
   共 108 格）。它与上面那种「按今天口径重述、与当年稿子对不上」是同一类事，区别在范围：
   这回是整列，不采纳就是同一列里新旧两套口径拼接：拼接处有一个约 5% 的口径台阶，
   其后 12 个月的同比都是新口径比旧口径。
   另外几条是小批：次月更正（2026-06 基金只数 / CSD 结算指令；绿鞋补记进上市月的新上市募资额；
   雅典再融资按配股实募改记）与市值去重（并表头五个月补剔布鲁塞尔、雅典双重挂牌的三家）。人核过但没采纳的冲突也列在
   那张表的文末，免得下一个人再从头核一遍。
   只差浮点表示的格子（官方单元格在 ULP 级别变了）不算冲突，见 _same_number。

**5. FX 那一列的表头单位是错的。**
   FICC Markets 第 9 行写 `Volume (in M$, single counted)`，但格子里 2026-06 是
   `671602324739`。若真是百万美元，日均就成了 30 万亿美元。拿 2019-01 新闻稿的
   "$20,050 million" 反推：441,099,188,988.6 / 22 / 1e6 = 20,049.96 → **该列是绝对美元**。
   Q2 2026 再验：/65/1e9 = 28.9816 $bn vs 官方 "ADV Euronext FX 28,982 $m"，相对差 1.25e-05。
   ⇒ 除以 1e9 得 $bn。不要相信表头。（同一序列在伴生的 latest 文件里**真的是 M$**，见坑 6。）

**6. 伴生的 `euronext_latest_month_volumes.xlsx` 只能核对「最新月」这一列，不能核对历史。**
   两个官方文件对 Athens 并表用**不同基准**：latest 的脚注写
   "Includes figures from Euronext Athens since January 2025"，hist 写 "since November 2025"。
   实测 2025-06：latest 的单股衍生品 6,908,289 = hist「主列+Athex」，而 hist 主列只有
   5,630,914（差 22.7%）。拿 latest 去核对 2025-11 之前的月份会看到最高 23% 的假失配，
   然后很可能去「修」一个没坏的解析器。
   ⇒ 本模块的 `_crosscheck_latest_month()` **只比最新月那一列**，且先核对文件自报的月份。
   另外同一个 FX 序列 latest 是 M$、hist 是绝对 $，两文件绝不共用单位常量。
   latest 的第 5 张 sheet `Nord Pool` 是 2020 年的死残留（格子里写字面量 "xxx" / "xx%"），
   本模块根本不碰它。

**7. 「Commodity」是农产品，不是能源；电力是另一套，且分两层、三个不同的日数分母。**
   Euronext 的 commodity derivatives = 巴黎 MATIF 的小麦/玉米/菜籽。
   能源侧是 Nord Pool，拆成 **现货电力**（Day-ahead / Intraday，单位 TWh，**买卖双边计**，
   2020-01 起，分母是**自然日** 30/31）与 **电力衍生品**（Notional Volume/OI，单位 GWh，
   **2026-03-16 才全面上线**，分母是交易日，2026-03 只有 12 天）两块。
   ⇒ 跨家比价时 `adv_commodity_*_kcontracts` 的对手是 CME 的 `adv_ag_kcontracts`，
   **不是** `adv_energy_kcontracts`。

**8. 同一张表里混着单边计与双边计，每引用一列都要回表头看分组行。**
   现货金额 `Trading volume (single counted)`；现货笔数 `Transactions (buy and sell)`
   （**双边**，且含 reported trades，官方 Q2 稿原文 "reported trades included"）；
   股权清算 `Clearing volume (single counted)`；债券清算 `Clearing volume (double counted)`；
   Nord Pool 电力 `Volume (in TWH, buy and sell)`（**双边**）。
   本模块给每一列都在下面 COLUMN_SPEC 的注释里标了单双边，CSV 列名不带这个信息，
   查列名 → 回这里查口径。

**9. 表结构是「两层表头 + 合并单元格 + 同名标签重复出现」，必须按分组 + 标签定位。**
   `Futures` / `Options` / `Athex` / `Nb of trading days` / `Total` / `Equities`
   这些标签在同一张 sheet 里各出现 2-8 次，只有靠上面的分组行才能区分是股指还是单股、
   是成交量还是 OI。本模块的做法：用**合并单元格范围**还原每一列头上盖着的分组文字，
   拼成 (分组, 小节, 标签) 三元组去唯一定位，**绝不写死列号、也绝不全表 grep 标签**。
   分组标题带脚注编号（`Commodity derivatives (3)`、`Turnover Equities (1)`、`Period (1)`），
   `_lab()` 只剥**结尾**的 `(数字)` / `(R)` —— 不能全剥，`TA(1) MTS Repo` 的括号在中间，
   `Bonds wholesale (in EUR bln)` 的括号是单位。

**10. `Nb of trading days` 有 7 个，各管各的分母，且其中一个根本不是交易日。**
   Equity Markets 两个（现货 C3 / 股权衍生品 C16，2026-08-18 实测全部 175 个月两列相等，
   但官方保留成
   两列，本模块也存两列，不做「反正相等」的偷懒）；FICC 五个（固收 C3 / 商品 C13 /
   电力 C19 / 电力衍生品 C23 / FX C28）。其中**电力那个是自然日**（2026-04=30、
   2026-05=31，Q2 合计 91 = 30+31+30），官方 Q2 稿也印 91；FX 那个与现货不同
   （2026-04 现货 20 天、FX 22 天）。
   定位规则：某个分组的日数列 = **紧邻该分组左侧的那个 `Nb of trading days` 列**。
   这条规则也顺带解释了为什么单股衍生品没有自己的日数列 —— 它左边最近的那个就是 C16。

**11. 四张 sheet 的 Period 语义不一致，必须按 (年, 月) 归并。**
   Equity / FICC / Securities Services 的 Period 是每月 1 日；
   **Capital Markets 不是** —— 实测 2018-01-05、2018-02-02、2018-03-02…（像是每月首个周五），
   到 2026 年才变成月初。按精确日期 join 会整段对不上。

**12. `Capital Markets` 的 `Funds` 列 2018 全年是字面量字符串 `'NA'`。**
   这是整个工作簿里除死 sheet 之外**唯一**的非数值污染。`float(cell)` 会 ValueError，
   或者把 "NA" 原样写进 CSV。⇒ `listed_funds` 的起始月是 **2019-01**，不是 2018-01。

**13. 两张 sheet 是死残留，解析到会炸或写出垃圾 —— 所以白名单四张 sheet，不 for-each-sheet。**
   hist 的第 5 张 `Checkup`：唯一的数据列整列是 `#REF!` 字符串（117 行），
   表头却写着 "Euronext Cash / Turnover in millions euros"，看上去像正经数据。
   latest 的第 5 张 `Nord Pool`：字面量 "xxx" / "xx%"，停在 2020-01。

**14. 官方对上市统计做过两次口径扩大，且已回溯重述。**
   脚注 (3)：2025-06 起 `Bonds` 计入 Euronext ABM，2024 与 2025 已重述；
   脚注 (4)：2025-06 起 `Nb of Listings` 改为「所有类型的挂牌」（含私募配售、直接上市、
   市场间转板、反向并购、de-SPAC、二次上市）；脚注 (2)：2021-05 改过发行人家数的计算方法。
   三条都是「已重述」，序列内部自洽，但与 2024 年当时读到的家数/募资额对不上，
   且 `new_listings_equities` 在 2025-06 有一次口径抬升，同比要注意。

**15. 文件的 Last-Modified 不是发布日，会被重述推后。**
   实测 `Last-Modified: Thu, 16 Jul 2026 08:20:12 GMT`，而 2026-06 那期新闻稿是
   **2026-07-06** 发的 —— 文件在发布 10 天后被原地重传过。
   ⇒ source_dates 只认新闻稿的 <time datetime>，且**首次摄入某月时记一笔、事后永不覆盖**。

**16. 新闻稿标题不遵守模板，按模板拼 slug 或做全等匹配必漏。**
   2023-03 那期的标题是 "Euronext announces highest cash volumes in a year in March 2023"，
   slug 是 `euronext-announces-highest-cash-volumes-year-march`；
   拼出来的 `...-for-march-2023` 与 `...-for-march-2023-0` **双双 404**。
   市场部随时会为「创纪录」的月份改标题。⇒ 一律从**列表页**拿真 href 与真日期，
   标题用宽松匹配（announces … volume … <月> <年>），**且允许某个月取不到发布日而不抛异常**
   （仓库 source_dates.py 的原则：拿不到就让它缺席，缺席远好过印一个像模像样的错日期）。

**17. 月度新闻稿从 2020 年起正文里已经没有任何数字了。**
   2019-01 那期有完整正文数字；2020-07-03 那期正文只剩一句
   "Monthly and historical volumes table are available at this address"（统计数字在一个
   独立的附件 PDF 里）；2022 年以后连附件都没有。
   ⇒ **不要**把新闻稿当数据源去解析，它在本模块里的唯一价值就是发布日。

**18. 序列长度不齐：市值 / CSD 只到 2022-01，比主序列短十年。**
   不是断档，是官方本来就只提供这么长。逐列起始月见 COLUMN_SPEC 的 since 字段
   （那是本机实测出来的，不是抄的）。画在同一张图里会出现左半边空白，
   要么单独成图、要么图注写明起点。
   ⚠ **这些起点没有一个是抓取窗口** —— 本模块只下一份滚动全历史 xlsx 并遍历它的
   全部 Period 行，压根没有窗口这个概念。起点全部是业务史（复核过的日期）：
     · 2020-01 Nord Pool 现货电力 —— 2020-01-15 完成收购 66% 股权，自 01-16 并表，
       这是唯一一处「起点 = 交割月」；
     · 2020-01 MTS —— MTS 随 Borsa Italiana Group 进来，那笔交易 2021-04-29 才交割，
       序列却回填到 2020-01（早 15 个月）⇒ 是官方回填，不是并表日；
     · 2013-01 Euronext FX —— 前身 FastMatch，2017-08-14 完成收购约 90% 股权，回填到
       被收购方自己的历史；
     · 2021-01 athex_* 备注列 —— 雅典换股要约 2025-11-19 宣告成功（接纳期 11-17 截止、
       11-24 交割），官方把备注列回填到 2021-01；
     · 2022-01 清算 / 市值 / CSD —— **披露起点，不是事件日期**。业务前提是 2021-04-29
       Borsa Italiana Group 交割带来 Euronext Clearing（原 CC&G）与米兰 CSD Monte Titoli；
       在那之前只有波尔图 Interbolsa、奥斯陆 VPS（2019-06-18 交割）与哥本哈根
       VP Securities（2020-08-04 交割），米兰缺位 ⇒ 四家齐备最早只能到 2021-05，
       官方却从 2022-01 才按月发。CSD 的 Total 列到 2025-11 才含雅典（脚注 (1) 原文）。
     · 2026-03 电力衍生品 —— 脚注 (5) 原文写死 "fully operational on 16 March 2026"。
   ⇒ 这些起点**不需要回补**：更早的官方**月度**数据不存在。Fact Book / 年报里那些年度数
   的成员范围与定义与本表都不是一回事，硬接上去只会在 2018-01 或 2022-01 造出假台阶 ——
   要接必须先逐项证明口径相同，没证明就不接。

━━ 产出的两个文件 ━━
· `series/enx.csv` —— 72 个字段（month + 71 个数据列）× 每月一行，2012-01 起
  （2026-08-18 实测 175 行、到 2026-07；行数随每月更新增长，别把它当常量）。列序是
  交易日 → 主列（按官方表的顺序）→ 全部 `athex_*` 备注列。每一列的确切口径写在
  下面 COLUMN_SPEC 的行末注释里（张数/金额、日均/月总/月末时点、单边/双边、币种）。
· `series/enx_breaks.csv` —— 口径断点台账，**由本模块从官方脚注原文自动抽取**，
  92 行，列是 `column, break_month, footnote, athex_memo_column, official_footnote`。
  它回答的是「哪一列在哪个月与左侧不可比、以及有没有备注列能把断点消掉」。
  2025-11 那一批 26 行就是 Athens 并表影响到的全部列。
  这个文件**是 build 的输入**：`build/specs/enx.py` 的 `_read_breaks()` 每次 import 都读它，
  取出 (column, break_month) 逐列挂断点 —— 页上那些红色竖线的月份与「画在哪张图上」
  全部由这张表决定，spec 里只留一张「月份 → 中文说法」的翻译表，**月份一个都不写死**。
  ⇒ 删了它，2025-11 那条红线该画在哪几张图上就只剩人脑记忆，而人脑记不住 26 列。
  它同时也是「官方又并购了一家」的探测器 —— 官方改脚注，这张表下次跑就跟着变，
  git diff 里看得见。

━━ 没有入库的列（写清楚免得后人以为漏了）━━
· CSD 的五地分拆（Athens / Copenhagen / Milan / Oslo / Porto）：只入了 Total 与 Athens
  （Athens 是断点备注列，必须有），另外四地是地理明细，与本仓的横截面叙事无关。
· `Money Raised - Bonds`：官方季报有这一行，**月度 xlsx 里没有**，无法逐月入库。
· `Total Euronext` 这个历史概念：2020 年的稿子里它 = 三大类 + 一个已经不存在的
  `TM Derivatives` 桶（Oslo 的一个衍生品桶，2020-06 那期 254,784 张）。
  今天的官方季报附录里也没有这一行了 ⇒ 不要用它去校验本模块算出的衍生品总量。
"""

import collections
import csv
import datetime
import hashlib
import io
import json
import os
import re
import time
import urllib.request

import openpyxl

# ══════════════════════════════════════════════════════════════════════
# 源地址
# ══════════════════════════════════════════════════════════════════════
LANDING_URL = 'https://www.euronext.com/en/investor-relations'
STATS_BASE = 'https://live.euronext.com/sites/default/files/statistics/ir/'
HIST_NAME = 'euronext_monthly_historical_volumes.xlsx'
LATEST_NAME = 'euronext_latest_month_volumes.xlsx'
NEWS_URL = ('https://www.euronext.com/en/investor-relations/'
            'financial-information/news?page=%d')
SITE_ROOT = 'https://www.euronext.com'

# live.euronext.com 实测连默认的 python-urllib UA 都放行；带常规 UA 是零成本的保险。
_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# 白名单四张 sheet，见口径坑 13。绝不 for-each-sheet。
SHEETS = ('Equity Markets', 'FICC Markets', 'Capital Markets',
          'Securities Services')


# ══════════════════════════════════════════════════════════════════════
# 表结构
# ══════════════════════════════════════════════════════════════════════
S_EQ, S_FICC, S_CAP, S_SEC = SHEETS

# 分组行（合并单元格）的文字，已按 _lab() 剥掉尾部脚注编号
G_CASH = 'Cash Markets (Fixed Income excluded)'
G_IDX = 'Equity Index derivatives'
G_SS = 'Individual Equity derivatives'
G_FI = 'Fixed Income Markets'
G_COM = 'Commodity derivatives'
G_PWR = 'Power trading'
G_PWRD = 'Power trading derivatives'
G_FX = 'FX trading'
G_CSD = 'Central Securities Depositary'

# 小节行（第二层表头）的文字 —— 单双边计数就写在这里，见口径坑 8
U_TRADES = 'Transactions (buy and sell)'          # 双边
U_TURNOVER = 'Trading volume (single counted)'    # 单边，Equity Markets，单位 €m
U_CLEAR1 = 'Clearing volume (single counted)'     # 单边
U_LOTS = 'Volume (in lots)'
U_OI = 'Open Interest (in lots)'
U_FI_TV = 'Trading volume (in M€, single counted)'  # 单边，FICC，单位 €m
U_CLEAR2 = 'Clearing volume (double counted)'     # 双边
U_TWH = 'Volume (in TWH, buy and sell)'           # 双边
U_GWH_V = 'Notional Volume (in GWH)'
U_GWH_OI = 'Notional Open Interest (in GWH)'
U_FX = 'Volume (in M$, single counted)'           # 表头单位是错的，见口径坑 5
U_AUC = 'AuC (in EUR bln)'
U_SETTLE = 'Nb of Settlement instructions'

# 交易日列：key -> 用来定位它的分组（该分组左邻的那个 Nb of trading days 列），见口径坑 10
DAYS_ANCHOR = {
    'cash': (S_EQ, G_CASH),
    'eqderiv': (S_EQ, G_IDX),
    'fixedincome': (S_FICC, G_FI),
    'commodity': (S_FICC, G_COM),
    'power': (S_FICC, G_PWR),
    'powerderiv': (S_FICC, G_PWRD),
    'fx': (S_FICC, G_FX),
}

# (csv 列名, days key, 起始月)。起始月是本机对当前这份 xlsx 逐列实测出来的首个有数月。
DAYS_SPEC = [
    ('trading_days_cash', 'cash', '2012-01'),
    ('trading_days_eqderiv', 'eqderiv', '2012-01'),
    ('trading_days_fixedincome', 'fixedincome', '2012-01'),
    ('trading_days_commodity', 'commodity', '2012-01'),
    ('days_power_calendar', 'power', '2020-01'),      # 自然日，不是交易日
    ('trading_days_powerderiv', 'powerderiv', '2026-03'),
    ('trading_days_fx', 'fx', '2013-01'),
]

Col = collections.namedtuple(
    'Col', 'name sheet heads label days scale since memo memo_since')


def _c(name, sheet, heads, label, days, scale, since, memo=None, memo_since=None):
    return Col(name, sheet, tuple(heads), label, days, float(scale), since,
               memo, memo_since)


# 每一列的确切口径写在行末注释里：张数还是金额、日均还是月总还是月末、单边还是双边、
# 本币还是美元、含哪些市场。下游 build/notional.py 的换算全靠这些注释，写错比数字错更难发现。
#
# 「含哪些市场」的通则（逐列不再重复）：主列 = 巴黎 + 阿姆斯特丹 + 布鲁塞尔 + 里斯本
#   + 都柏林（现货 2017-01 起 / 上市 2019-01 起）+ 奥斯陆（现货 2018-01 起 /
#   衍生品与商品 2019-07 起 / 上市 2019-01 起）+ 米兰（2021-05 起）
#   + 雅典（**2025-11 起**）。`athex_*` 备注列见口径坑 1。
COLUMN_SPEC = [
    # ── 现货（Equity Markets / Cash Markets）────────────────────────────
    # 日均成交笔数（千笔/日）。**买卖双边计**，含 reported trades。
    _c('adv_cash_trades_k', S_EQ, (G_CASH, U_TRADES), 'Total number of trades',
       'cash', 1e3, '2012-01', 'athex_adv_cash_trades_k', '2021-01'),
    # 日均成交名义额（€bn/日）。**单边计**。含股票+投资基金+ETF+结构化产品。
    _c('adv_cash_adnv_eurbn', S_EQ, (G_CASH, U_TURNOVER), 'Total Turnover',
       'cash', 1e3, '2012-01', 'athex_adv_cash_adnv_eurbn', '2021-01'),
    # 同上，只含股票与投资基金。**与 Cboe Europe 的 adv_eu_equities_adnv_eurbn 对比用这一列**
    # （Cboe 那列不含结构化产品），是全仓最干净的一对同口径可比字段。
    _c('adv_cash_equities_adnv_eurbn', S_EQ, (G_CASH, U_TURNOVER),
       'Turnover Equities', 'cash', 1e3, '2012-01',
       'athex_adv_cash_equities_adnv_eurbn', '2021-01'),
    # ETF 现货日均成交额（€bn/日，单边）。2015-01 起 ETC 从结构化产品挪进这一列。
    _c('adv_cash_etf_adnv_eurbn', S_EQ, (G_CASH, U_TURNOVER), 'Turnover ETF',
       'cash', 1e3, '2012-01', 'athex_adv_cash_etf_adnv_eurbn', '2021-01'),
    # 结构化产品现货（€bn/日，单边）。入库不是为了画图，是为了每月撞恒等式
    # Total ≡ Equities + ETF + Structured（见 _validate），撞得上说明四列一格没错行。
    # 撞不上也可能是官方工作簿自己不平：2026-08 就是（多 €600），靠 IDENTITY_UPSTREAM_GAPS 逐值登记放行。
    _c('adv_cash_structured_adnv_eurbn', S_EQ, (G_CASH, U_TURNOVER),
       'Turnover Structured Products', 'cash', 1e3, '2012-01'),
    # Euronext Clearing 清算的股票交易笔数/手数（千/日，**单边**）。官方标签
    # "Shares (nb of contracts)"，季报里叫 "number of transactions and lots cleared"，
    # 与成交额不是同一层；值带小数（例：2026-06 月合计 27,358,633.5，8 月版），不是纯计数。
    # ⚠ 2026-08 版起全程含雅典（官方 pro-forma 回填到 2022-01，备注列语义不随并表月翻转），
    #   库里 2022-01..2026-06 是按 ACCEPTED_RESTATEMENTS 采纳后的新口径；见口径坑 1 的例外。
    _c('adv_shares_cleared_kcontracts', S_EQ, (G_CASH, U_CLEAR1),
       'Shares (nb of contracts)', 'cash', 1e3, '2022-01',
       'athex_adv_shares_cleared_kcontracts', '2022-01'),

    # ── 股指衍生品（CAC 40 / AEX / BEL 20 / FTSE MIB / OBX / ATHEX 等）──
    # 日均张数（千张/日）。乘数各不相同（CAC 40 期货 €10/点），跨家只能指数化比。
    _c('adv_index_futures_kcontracts', S_EQ, (G_IDX, U_LOTS), 'Futures',
       'eqderiv', 1e3, '2012-01', 'athex_adv_index_futures_kcontracts', '2021-01'),
    _c('adv_index_options_kcontracts', S_EQ, (G_IDX, U_LOTS), 'Options',
       'eqderiv', 1e3, '2012-01', 'athex_adv_index_options_kcontracts', '2021-01'),
    # 月末未平仓（千张，**月末时点，不除交易日**）
    _c('oi_index_futures_kcontracts', S_EQ, (G_IDX, U_OI), 'Futures',
       None, 1e3, '2012-01', 'athex_oi_index_futures_kcontracts', '2021-01'),
    _c('oi_index_options_kcontracts', S_EQ, (G_IDX, U_OI), 'Options',
       None, 1e3, '2012-01', 'athex_oi_index_options_kcontracts', '2021-01'),

    # ── 单股衍生品 ⚠ 全表最危险的一列，见口径坑 2 ──────────────────────
    _c('adv_singlestock_futures_kcontracts', S_EQ, (G_SS, U_LOTS), 'Futures',
       'eqderiv', 1e3, '2012-01',
       'athex_adv_singlestock_futures_kcontracts', '2021-01'),
    _c('adv_singlestock_options_kcontracts', S_EQ, (G_SS, U_LOTS), 'Options',
       'eqderiv', 1e3, '2012-01',
       'athex_adv_singlestock_options_kcontracts', '2021-01'),
    _c('oi_singlestock_futures_kcontracts', S_EQ, (G_SS, U_OI), 'Futures',
       None, 1e3, '2012-01', 'athex_oi_singlestock_futures_kcontracts', '2021-01'),
    _c('oi_singlestock_options_kcontracts', S_EQ, (G_SS, U_OI), 'Options',
       None, 1e3, '2012-01', 'athex_oi_singlestock_options_kcontracts', '2021-01'),

    # ── 固收（FICC / Fixed Income Markets）─────────────────────────────
    # MTS 现券：欧洲主权债电子交易，日均成交额 €bn/日，**单边**。
    _c('adv_mts_cash_eurbn', S_FICC, (G_FI, U_FI_TV), 'MTS Cash',
       'fixedincome', 1e3, '2020-01'),
    # MTS 回购**未经期限调整**的日均量（€bn/日，单边）。官方主口径是下面那条 TAADV，
    # 两条都在表里，别混。
    _c('adv_mts_repo_eurbn', S_FICC, (G_FI, U_FI_TV), 'MTS Repo',
       'fixedincome', 1e3, '2020-01'),
    # Term Adjusted 回购日均量（€bn/日，单边）—— 官方季报印的就是这条（TAADV MTS Repo）。
    _c('taadv_mts_repo_eurbn', S_FICC, (G_FI, U_FI_TV), 'TA(1) MTS Repo',
       'fixedincome', 1e3, '2020-01'),
    # MTS 以外的债券成交（Euronext 各地债券市场，2025-11 起含 Athex），量级小，留 €m/日。
    _c('adv_other_fixed_income_eurm', S_FICC, (G_FI, U_FI_TV), 'Bonds',
       'fixedincome', 1, '2012-01', 'athex_adv_other_fixed_income_eurm', '2021-01'),
    # 债券批发清算名义额（€bn/日，**双边计**）
    _c('adv_bonds_wholesale_cleared_eurbn', S_FICC, (G_FI, U_CLEAR2),
       'Bonds wholesale (in EUR bln)', 'fixedincome', 1, '2022-01'),
    # 债券零售清算（千张/日，**双边计**）
    _c('adv_bonds_retail_cleared_kcontracts', S_FICC, (G_FI, U_CLEAR2),
       'Bonds retail (nb of contracts)', 'fixedincome', 1e3, '2022-01',
       'athex_adv_bonds_retail_cleared_kcontracts', '2022-01'),

    # ── 商品衍生品 = 巴黎 MATIF 农产品（小麦/玉米/菜籽），**不是能源**，见口径坑 7 ──
    _c('adv_commodity_futures_kcontracts', S_FICC, (G_COM, U_LOTS), 'Futures',
       'commodity', 1e3, '2012-01'),
    _c('adv_commodity_options_kcontracts', S_FICC, (G_COM, U_LOTS), 'Options',
       'commodity', 1e3, '2012-01'),
    _c('oi_commodity_futures_kcontracts', S_FICC, (G_COM, U_OI), 'Futures',
       None, 1e3, '2012-01'),
    _c('oi_commodity_options_kcontracts', S_FICC, (G_COM, U_OI), 'Options',
       None, 1e3, '2012-01'),

    # ── Nord Pool 现货电力：日均 TWh，**买卖双边计**，分母是自然日不是交易日 ──
    _c('adv_power_dayahead_twh', S_FICC, (G_PWR, U_TWH), 'Day-ahead',
       'power', 1, '2020-01'),
    _c('adv_power_intraday_twh', S_FICC, (G_PWR, U_TWH), 'Intraday',
       'power', 1, '2020-01'),

    # ── Nord Pool 电力衍生品：2026-03-16 全面上线，序列因此从 2026-03 才起 ────
    #    （官方 FICC Markets 脚注 (5) 原文："Power derivatives market became fully
    #     operational on 16 March 2026"。有几个月随每月更新增长，不写死。）
    # 日均名义量（GWh/日）
    _c('adv_power_systemprice_futures_gwh', S_FICC, (G_PWRD, U_GWH_V),
       'System price futures', 'powerderiv', 1, '2026-03'),
    _c('adv_power_epad_futures_gwh', S_FICC, (G_PWRD, U_GWH_V),
       'EPADs futures', 'powerderiv', 1, '2026-03'),
    # **月末名义未平仓（GWh，时点值，不除天数）** —— 官方 Q2 2026 季报印的就是这条
    _c('oi_power_deriv_notional_gwh', S_FICC, (G_PWRD, U_GWH_OI),
       'Total Notional Open interest', None, 1, '2026-03'),

    # ── Euronext FX（原 FastMatch）即期外汇：$bn/日，**单边**。原始单元格是绝对美元 ──
    _c('adv_fx_spot_usdbn', S_FICC, (G_FX, U_FX), 'Spot volume', 'fx', 1e9, '2013-01'),

    # ── 上市与募资（Capital Markets）───────────────────────────────────
    # 月末股票发行人家数（时点值）。2021-05 改过计算方法（脚注 2）。
    _c('issuers_equities', S_CAP, ('Nb of Issuers',), 'Equities',
       None, 1, '2018-01', 'athex_issuers_equities', '2021-01'),
    # 月末上市债券只数。2025-06 起含 Euronext ABM，官方已重述 2024-2025（脚注 3）。
    _c('listed_bonds', S_CAP, ('Nb of Listed Instruments',), 'Bonds',
       None, 1, '2018-01', 'athex_listed_bonds', '2021-01'),
    _c('listed_etfs', S_CAP, ('Nb of Listed Instruments',), 'ETFs',
       None, 1, '2018-01', 'athex_listed_etfs', '2021-01'),
    # ⚠ 2018 全年是字面量 'NA'，起始月 2019-01，见口径坑 12。官方无 Athex 备注列。
    _c('listed_funds', S_CAP, ('Nb of Listed Instruments',), 'Funds',
       None, 1, '2019-01'),
    # **当月**新增挂牌家数（月度总量，不是时点也不是日均）。
    # 2025-06 起口径扩大到「所有类型的挂牌」（脚注 4），跨那个月的同比不可直接比。
    _c('new_listings_equities', S_CAP, ('Nb of Listings',), 'Equities',
       None, 1, '2018-01', 'athex_new_listings_equities', '2023-01'),
    # **当月**新上市募资额（€m，月度总量，含超额配售）
    _c('money_raised_new_listings_eurm', S_CAP, ('Money Raised (mln of €)',),
       'Equities - New Listings', None, 1, '2018-01',
       'athex_money_raised_new_listings_eurm', '2023-01'),
    # **当月**股票再融资募资额（€m，月度总量）
    _c('money_raised_followon_eurm', S_CAP, ('Money Raised (mln of €)',),
       'Equities - Follow-ons', None, 1, '2018-01',
       'athex_money_raised_followon_eurm', '2023-01'),
    # 月末总市值（万亿欧元，时点值）。**只到 2022-01**，比主序列短十年。
    _c('mktcap_eurtn', S_CAP, ('Market cap. (trillion of €)',),
       'Total end of month', None, 1, '2022-01', 'athex_mktcap_eurtn', '2022-01'),

    # ── 结算与托管（Securities Services，五家 CSD）─────────────────────
    # 月末托管资产（€bn，时点值）。**只到 2022-01**。备注列表头是 'Athens' 不是 'Athex'。
    _c('csd_auc_eurbn', S_SEC, (G_CSD, U_AUC), 'Total',
       None, 1, '2022-01', 'athex_csd_auc_eurbn', '2022-01'),
    # **当月**结算指令笔数（百万笔，月度总量）。**只到 2022-01**。
    _c('csd_settlement_instructions_m', S_SEC, (G_CSD, U_SETTLE), 'Total',
       None, 1e6, '2022-01', 'athex_csd_settlement_instructions_m', '2022-01'),
]

# CSV 列序：交易日 → 主列（按源表顺序）→ 全部 athex_* 备注列。
# 备注列集中放在末尾而不是紧跟各自的主列，是为了让「主序列」那一段能一眼读完；
# 代价是与 xlsx 逐列对照时要跳一下，这个代价由 COLUMN_SPEC 里的成对定义抵消。
COLUMNS = ([n for n, _k, _s in DAYS_SPEC]
           + [c.name for c in COLUMN_SPEC]
           + [c.memo for c in COLUMN_SPEC if c.memo])

# 每一列的起始月（校验用）。晚于起始月还为空 = 解析出错，抛异常；早于起始月为空 = 官方就没有。
SINCE = dict([(n, s) for n, _k, s in DAYS_SPEC]
             + [(c.name, c.since) for c in COLUMN_SPEC]
             + [(c.memo, c.memo_since) for c in COLUMN_SPEC if c.memo])

# 「这个月真的有数据」的锚：现货 ADNV。官方有时会把下个月的行先开出来只填交易日
# （HKEX 教训的同类问题），所以不能用「表里最后一行」当最新月。
ANCHOR = 'adv_cash_adnv_eurbn'

# 结构性口径断点，写在这里供 build 层取用（画红色竖线），也供人查。见口径坑 1、3。
BREAKS = {
    'cash': ['2017-01', '2018-01', '2021-05', '2025-11'],
    'derivatives': ['2019-07', '2021-05', '2025-11'],
    'listing': ['2019-01', '2021-05', '2025-06', '2025-11'],
    'power_derivatives': ['2026-03'],
}


class EnxFetchError(RuntimeError):
    """源站结构变化 / 下载失败 / 解析结果不完整 / 内部恒等式不成立。

    一律炸掉。宁可整月不更新（线上留着自己的旧数据），也绝不静默写空列或 NaN。
    """


# ══════════════════════════════════════════════════════════════════════
# 网络
# ══════════════════════════════════════════════════════════════════════
def _http_get(url, timeout=90, tries=1, pause=1.5):
    """取一个 URL 的原始字节。tries>1 时带退避重试。

    www.euronext.com 是 Drupal 主站，实测连打约 20 个请求之后会
    `RemoteDisconnected: Remote end closed connection without response`
    —— 不是封禁，是连接被掐。所以走主站的调用方一律传 tries=3；
    live.euronext.com 的 CDN 静态文件没有这个毛病，用默认的 tries=1。
    """
    last = None
    for k in range(tries):
        req = urllib.request.Request(url, headers={
            'User-Agent': _UA,
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), dict(r.headers)
        except Exception as e:                            # noqa: BLE001
            last = e
            if k + 1 < tries:
                time.sleep(pause * (k + 1))
    raise EnxFetchError('下载失败 %s: %r' % (url, last)) from last


def _write_bytes(path, data):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def _check_landing(cache_dir):
    """确认历史 xlsx 还挂在官方 IR 页上；返回 True/False，**不抛异常**。

    文件名是写死的，所以这一步不是为了「发现文件名」，而是为了发现**文件名变了**：
    直链在改名之后多半还能下到一个再也不更新的孤儿文件，那种故障不报错、
    只会让序列悄悄停在某个月。这里查不到就打醒目警告继续跑 —— 真正的护栏是
    下面那一堆结构与恒等式校验，以及 latest 文件的当月对表。
    """
    try:
        html, _h = _http_get(LANDING_URL, tries=3)
    except EnxFetchError as e:
        print('[enx] 警告：落地页取不到（%r），跳过链接存在性检查' % e)
        return False
    _write_bytes(os.path.join(cache_dir, 'enx_ir_landing.html'), html)
    txt = html.decode('utf-8', 'replace')
    # 全局正则捞 href：<h2 id="monthly-volumes"> 与下载列表分处两个 Drupal container，
    # 中间隔着约 600 字符模板标记，按锚点作用域去扫会抓空。
    hits = set(re.findall(
        r'https://live\.euronext\.com/sites/default/files/statistics/ir/'
        r'[A-Za-z0-9_.-]+\.xlsx', txt))
    if any(h.endswith(HIST_NAME) for h in hits):
        return True
    print('[enx] ⚠ 落地页 %s 上找不到 %s 的链接（页面上的 xlsx 有 %s）—— '
          '官方可能改了文件名，本次仍按写死的直链下载，请人工确认'
          % (LANDING_URL, HIST_NAME, sorted(hits) or '零个'))
    return False


def _rawkeep():
    """按路径加载 fetch/rawkeep.py。

    不能裸 import：本模块被 monthly_run 用 spec_from_file_location 加载，
    那时 sys.path 上既没有 fetch/ 也没有仓库根（同 _source_dates 的坑）。
    """
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        'rawkeep', os.path.join(here, 'rawkeep.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _lm_month(last_modified):
    """把 Last-Modified 头折成 'YYYY-MM'，只给存证文件名当标签用；拿不到就 None。

    刻意用 Last-Modified 而不是数据月：本文件是**滚动全历史**，没有「属于哪个月」这回事，
    唯一有意义的标签是「这一版是什么时候挂上去的」。
    """
    if not last_modified:
        return None
    try:
        return datetime.datetime.strptime(
            last_modified, '%a, %d %b %Y %H:%M:%S %Z').strftime('%Y-%m')
    except (ValueError, TypeError):
        return None


def _download(cache_dir, name):
    os.makedirs(cache_dir, exist_ok=True)
    data, headers = _http_get(STATS_BASE + name)
    path = os.path.join(cache_dir, name)
    _write_bytes(path, data)
    last_modified = headers.get('Last-Modified')
    # ── 存证：模块 docstring 第 21 行已记「文件名固定、不带月份，每月原地覆盖」──
    # 上面这个 cache/<name> 是工作副本，下一期直接盖掉，历史版本官方一份都不留。
    # 按 <Last-Modified 月>-<sha256 前 12> 另存一份、永不覆盖，理由见 fetch/rawkeep.py。
    # 同一版重复下载只落一个文件（内容寻址），所以每天跑也不会膨胀。
    _rawkeep().keep('enx', data, 'xlsx', _lm_month(last_modified))
    return path, last_modified


# ══════════════════════════════════════════════════════════════════════
# 解析
# ══════════════════════════════════════════════════════════════════════
def _norm(v):
    return re.sub(r'\s+', ' ', str(v)).strip() if v is not None else ''


_FOOTNOTE_TAIL = re.compile(r'\s*\((?:\d+|R)\)\s*$')


def _lab(v):
    """表头文字归一化：只剥**结尾**的脚注编号 `(3)` 或修订标记 `(R)`。

    不能一律剥括号：`TA(1) MTS Repo` 的 (1) 在中间（它本身就是「Term Adjusted」的
    脚注，但剥掉之后标签会变成 'TA MTS Repo'，与表里对不上），
    `Bonds wholesale (in EUR bln)` 的括号是单位、`Cash Markets (Fixed Income excluded)`
    的括号是口径说明 —— 剥掉这些会让三元组失去区分力。
    """
    s = _norm(v)
    while True:
        t = _FOOTNOTE_TAIL.sub('', s)
        if t == s:
            return s
        s = t


def _cover_map(ws, upto_row):
    """{(row, col): 表头文字}，合并单元格里每一格都填成左上角那个值。

    两层表头 + 合并单元格是这份表的基本形态（口径坑 9）：分组标题只写在合并区左上角，
    直接读 ws.cell(8, 17) 会拿到 None。还原覆盖关系之后，每一列头上盖着哪些文字就是确定的，
    可以拼成 (分组, 小节, 标签) 三元组去唯一定位，不必写死列号。
    """
    out = {}
    for m in ws.merged_cells.ranges:
        if m.min_row > upto_row:
            continue
        v = ws.cell(m.min_row, m.min_col).value
        if v is None:
            continue
        for r in range(m.min_row, min(m.max_row, upto_row) + 1):
            for c in range(m.min_col, m.max_col + 1):
                out[(r, c)] = v
    return out


def _label_row(ws, sheet_name):
    """标签行 = A 列写着 'Period' 的那一行（Capital Markets 写成 'Period (1)'）。

    不写死行号：四张 sheet 的表头高度不一样（Equity/FICC 是第 10 行、
    Capital Markets 第 9 行、Securities Services 第 6 行），而且脚注一多就会整体下移。
    """
    for r in range(1, 25):
        if _lab(ws.cell(r, 1).value) == 'Period':
            return r
    raise EnxFetchError('sheet %s 前 25 行里找不到 A 列写 "Period" 的标签行，'
                        '官方表结构可能已变' % sheet_name)


class _Sheet(object):
    """一张 sheet 的表头索引：列 -> (分组链, 标签)，以及按三元组反查列号。"""

    def __init__(self, ws, name):
        self.ws = ws
        self.name = name
        self.lrow = _label_row(ws, name)
        cover = _cover_map(ws, self.lrow)

        def val(r, c):
            return cover.get((r, c), ws.cell(r, c).value)

        # raw_* 保留**没有剥掉脚注编号**的原文。剥过的用来定位列，没剥的用来回答
        # 「这一列挂着哪几条脚注」—— 官方的口径断点全写在脚注里，而哪些列受影响
        # 只有靠标签末尾那个 (3)/(5) 才认得出，剥早了这条信息就没了（见 breaks()）。
        self.label, self.heads = {}, {}
        self.raw_label, self.raw_heads = {}, {}
        self.raw_period = _norm(ws.cell(self.lrow, 1).value)
        for c in range(2, ws.max_column + 1):
            lab = _lab(val(self.lrow, c))
            if not lab:
                continue
            self.label[c] = lab
            self.raw_label[c] = _norm(val(self.lrow, c))
            self.heads[c] = tuple(
                _lab(val(r, c)) for r in range(1, self.lrow)
                if val(r, c) is not None)
            self.raw_heads[c] = tuple(
                _norm(val(r, c)) for r in range(1, self.lrow)
                if val(r, c) is not None)
        self._by_key = {}
        for c, lab in self.label.items():
            self._by_key.setdefault((self.heads[c], lab), []).append(c)

    def col(self, heads, label):
        """按 (分组链, 标签) 唯一定位一列；找不到或撞到多列都抛异常。

        撞到多列一定要炸，不能取第一个：`Athex` 在同一分组里就出现三次
        （Total Turnover / Turnover Equities / Turnover ETF 各配一个），
        取第一个等于把 ETF 的备注数当成整体的备注数写进 CSV，而且看上去完全正常。
        备注列不走这条路，走 memo_col()。
        """
        got = self._by_key.get((tuple(heads), label), [])
        if len(got) != 1:
            raise EnxFetchError(
                'sheet %s 里 (分组=%s, 标签=%r) 命中 %d 列（应为 1）—— '
                '官方表结构可能已变' % (self.name, list(heads), label, len(got)))
        return got[0]

    def memo_col(self, main_col):
        """Athex 备注列 = 主列**紧邻右侧**那一列，且标签是 Athex / Athens。

        为什么按位置而不按标签：备注列的 (分组, 小节, 标签) 三元组在同一分组里完全重复，
        三元组定位不了它。而「备注紧跟主列」是这张表真实的排版语义 ——
        官方在每一个配了备注的指标右边插一列，没配备注的（Structured Products、
        Bonds wholesale、Funds）右边就是下一个正经指标。所以这条位置规则同时也是
        「这个指标到底有没有备注列」的判据。
        """
        c = main_col + 1
        if self.label.get(c) in ('Athex', 'Athens'):
            return c
        return None

    def footnote_ids(self, col):
        """这一列挂着的脚注编号（含它头上分组的、以及整张表的 Period 那条）。

        `TA(1) MTS Repo` 这种括号在中间的也会被认成脚注 1 —— 无所谓：
        FICC 的脚注 1 是 "Term Adjusted"，里面没有月份，产不出断点行，自己就消化掉了。
        """
        txt = ' '.join((self.raw_period, self.raw_label.get(col, ''))
                       + self.raw_heads.get(col, ()))
        return sorted(set(re.findall(r'\((\d+)\)', txt)), key=int)

    def days_col(self, group):
        """某分组的日数列 = 紧邻该分组左侧的那个 `Nb of trading days` 列（口径坑 10）。

        `Nb of trading days` 在一张 sheet 里出现 2-5 次，标签本身没有区分力，
        而它们在表里的位置语义就是「我右边这一块用我当分母」。
        单股衍生品分组左边没有自己的日数列，按这条规则解析到的正是股权衍生品那个（C16）——
        与官方季报把两者放在同一个 "Number of trading days 62" 下面一致。
        """
        start = None
        for c, heads in self.heads.items():
            if heads and heads[0] == group:
                start = c if start is None else min(start, c)
        if start is None:
            raise EnxFetchError('sheet %s 里找不到分组 %r' % (self.name, group))
        cands = [c for c, lab in self.label.items()
                 if lab == 'Nb of trading days' and c < start]
        if not cands:
            raise EnxFetchError(
                'sheet %s 的分组 %r 左侧找不到 "Nb of trading days" 列'
                % (self.name, group))
        return max(cands)


_NULLS = {'', '-', '–', 'n/a', 'na', 'nd', 'n.a.'}


def _cell_num(ws, row, col, where):
    """单元格取数。空白与官方约定的空值记号返回 None，其余非数字一律抛异常。

    'NA' 必须进空值白名单：Capital Markets 的 `Funds` 列 2018 全年就是这个字面量字符串
    （口径坑 12），float() 会 ValueError。放进白名单不会掩盖问题 —— 该列的 SINCE 写的是
    2019-01，2019-01 之后再出现 'NA' 照样会被 _validate 当成缺值抓出来。
    """
    v = ws.cell(row, col).value
    if v is None:
        return None
    if isinstance(v, str):
        if v.strip().lower() in _NULLS:
            return None
        raise EnxFetchError('%s R%dC%d 不是数字：%r' % (where, row, col, v))
    if isinstance(v, datetime.datetime):
        raise EnxFetchError('%s R%dC%d 拿到日期而不是数字：%r' % (where, row, col, v))
    try:
        return float(v)
    except (TypeError, ValueError):
        raise EnxFetchError('%s R%dC%d 不是数字：%r' % (where, row, col, v))


def open_sheets(path):
    """打开历史 xlsx，返回 {sheet 名: _Sheet}。**白名单四张**，绝不 for-each-sheet。

    白名单不是洁癖：`Checkup` 那张 sheet 的唯一数据列是 117 个 `#REF!` 字符串，
    表头却写着 "Euronext Cash / Turnover in millions euros"（口径坑 13）—— 遍历式解析
    会把它当成正经数据去试，运气不好还真能试出一列垃圾。
    """
    wb = openpyxl.load_workbook(path, data_only=True, read_only=False)
    missing = [s for s in SHEETS if s not in wb.sheetnames]
    if missing:
        raise EnxFetchError('%s 里缺 sheet %s（拿到 %r）'
                            % (os.path.basename(path), missing, wb.sheetnames))
    return {s: _Sheet(wb[s], s) for s in SHEETS}


def parse_workbook(path, sheets=None):
    """解析历史 xlsx，返回 {'YYYY-MM': {csv列名: float|None}}（按月升序）。

    任何一个约定的 (分组, 标签) 找不到、或撞到多列 —— 说明官方改了表结构 ——
    直接抛异常。宁可整月不更新，也不要写出一列悄悄全空的 CSV。
    """
    sh = sheets if sheets is not None else open_sheets(path)

    # 结构自检：单股衍生品那一块解析到的日数列必须与股指那一块是同一列。
    # 这不是多余的 —— 哪天官方给单股插一个独立的日数列，days_col() 会安静地改指向，
    # 而 ADV 会整体错几个百分点，没有任何东西会报错。
    if sh[S_EQ].days_col(G_SS) != sh[S_EQ].days_col(G_IDX):
        raise EnxFetchError(
            '单股衍生品与股指衍生品解析到了不同的交易日列（C%d vs C%d）—— '
            '官方可能新增了独立的日数列，需人工确认口径'
            % (sh[S_EQ].days_col(G_SS), sh[S_EQ].days_col(G_IDX)))

    days_col = {k: sh[s].days_col(g) for k, (s, g) in DAYS_ANCHOR.items()}
    days_sheet = {k: s for k, (s, _g) in DAYS_ANCHOR.items()}

    # 每张 sheet 的 (year, month) -> 行号。Capital Markets 的 Period 不是月初
    # （2018-01-05 那种），必须按 (年, 月) 归并，见口径坑 11。
    rows = {}
    for s in SHEETS:
        ws, lrow = sh[s].ws, sh[s].lrow
        rows[s] = {}
        for r in range(lrow + 1, ws.max_row + 1):
            p = ws.cell(r, 1).value
            if not isinstance(p, datetime.datetime):
                continue
            mon = '%04d-%02d' % (p.year, p.month)
            if mon in rows[s]:
                raise EnxFetchError(
                    'sheet %s 里 %s 出现两行（R%d 与 R%d）—— 按 (年,月) 归并会丢数据，'
                    '需人工确认' % (s, mon, rows[s][mon], r))
            rows[s][mon] = r

    months = sorted(set().union(*[set(v) for v in rows.values()]))
    data = {}
    for mon in months:
        rec = dict.fromkeys(COLUMNS)
        # 交易日先取，后面的 ADV 都要用它当分母
        dv = {}
        for name, key, _since in DAYS_SPEC:
            s = days_sheet[key]
            r = rows[s].get(mon)
            v = (None if r is None else
                 _cell_num(sh[s].ws, r, days_col[key], '%s/%s' % (s, mon)))
            dv[key] = v
            rec[name] = v
        for c in COLUMN_SPEC:
            r = rows[c.sheet].get(mon)
            if r is None:
                continue
            sheet = sh[c.sheet]
            where = '%s/%s' % (c.sheet, mon)
            main_col = sheet.col(c.heads, c.label)
            rec[c.name] = _scale(_cell_num(sheet.ws, r, main_col, where),
                                 dv.get(c.days), c.scale, c, mon)
            if c.memo:
                mc = sheet.memo_col(main_col)
                if mc is None:
                    raise EnxFetchError(
                        '%s 的 %r 右侧不再是 Athex/Athens 备注列（拿到 %r）—— '
                        '并表口径的可回溯性依赖这一列，拒绝静默丢弃'
                        % (c.sheet, c.label, sheet.label.get(main_col + 1)))
                rec[c.memo] = _scale(_cell_num(sheet.ws, r, mc, where),
                                     dv.get(c.days), c.scale, c, mon)
        data[mon] = rec
    if not data:
        raise EnxFetchError('%s 解析后没有任何月份' % os.path.basename(path))
    return dict(sorted(data.items()))


def _scale(raw, days, scale, col, mon):
    """月度总量 → 入库值。col.days 为 None 表示这一列是时点值（OI / 家数 / 市值），不除天数。

    ADV 的算法是「月度总量 ÷ 该月交易日数」—— 这不是我们发明的口径：官方在伴生的
    latest 文件里给出算好的 ADV，与本算法的结果**逐位相同**（2026-06 现货
    17183.521449326818 双方完全相等，见 _crosscheck_latest_month）。

    「要不要除」只看 col.days（列的定义），**绝不看 days 这个值是不是 None**。
    两者混在一起写过一版，后果是：官方哪天把某个 Nb of trading days 格子留空而照常填量，
    这一列会被当成时点值原样入库 —— 一个 20 倍偏大的数字，静悄悄，没有任何报错。
    所以日数缺失必须炸，不能退化成「那就不除了」。
    """
    if raw is None:
        return None
    if col.days is None:
        return raw / scale
    if not days:
        raise EnxFetchError('%s 的 %s 该按 %s 交易日折算，但日数是 %r —— '
                            '拒绝把月度总量当成日均写进 CSV'
                            % (mon, col.name, col.days, days))
    return raw / days / scale


def _validate(data):
    """返回最新月；任何一处不达标立刻抛异常。

    ⚠ 每轮都把**全史**重扫一遍，不是只查最新月 —— hist 是滚动全历史文件，所以任何一个
    历史月在这里被拦下，挡住的是之后的每一个新月份：整条腿停更，不是扣发一个月。

    三道检查：
      1. 起始月之后不许有空格 —— 起始月是本机对当前 xlsx 逐列实测出来的，
         之后再为空只可能是解析错行或官方停发，两种都必须人来看。
      2. 恒等式 Total ≡ Equities + ETF + Structured（Athex 备注列同理，它没有
         结构化产品，所以是 Total ≡ Equities + ETF），tol=1e-9。2026-09-12 对 8 月版
         hist 实测（py3.12.12，与 _identity 一样用内置 sum() —— 3.12 起它对浮点做补偿求和 ——
         在入库的 ADV 空间量）：主恒等式 176 个月，除 2026-08 外最大相对差 3.414e-16（2024-09）；
         Athex 那道 68 个月最大 2.478e-16 —— 量级是浮点舍入（不随月数变；月数本身会变）。
         换成逐项 a+b+c（py<3.12 的 sum 语义）量，主恒等式是 3.738e-16（2021-01），41 个月
         两种求和结果不同；旧 docstring 的「3.7e-16」就是这么量的，两个数都对，别当成对不上。
         这道闸门要抓的是错行 —— 错行的数字全都「看上去很正常」。但撞不上不一定是错行：
         2026-08 主恒等式相对差 2.274e-09，是 Euronext 自己的工作簿里总量比三个分项之和
         多 €600（伴生 latest 工作簿三处独立旁证总量无误）。这类读数不靠放宽 tol 放行，
         只认 IDENTITY_UPSTREAM_GAPS 逐值登记，登记之外照样抛，理由见那张表上面的注释。
      3. 交易日必须是正数。
    """
    have = [m for m in sorted(data) if data[m][ANCHOR] is not None]
    if not have:
        raise EnxFetchError('解析结果里没有任何一个月有 %s，文件疑似空壳' % ANCHOR)
    newest = have[-1]

    for mon in have:
        rec = data[mon]
        bad = [c for c in COLUMNS
               if rec[c] is None and SINCE[c] and mon >= SINCE[c]]
        if bad:
            raise EnxFetchError(
                '%s 缺列 %s（这些列自 %s 起官方就有数）—— 解析异常，拒绝写入'
                % (mon, bad, [SINCE[c] for c in bad]))
        for name, key, _s in DAYS_SPEC:
            d = rec[name]
            if d is not None and not (d > 0):
                raise EnxFetchError('%s 的 %s = %r，不是正数' % (mon, name, d))
        _identity(mon, rec, 'adv_cash_adnv_eurbn',
                  ['adv_cash_equities_adnv_eurbn', 'adv_cash_etf_adnv_eurbn',
                   'adv_cash_structured_adnv_eurbn'])
        _identity(mon, rec, 'athex_adv_cash_adnv_eurbn',
                  ['athex_adv_cash_equities_adnv_eurbn',
                   'athex_adv_cash_etf_adnv_eurbn'])
    return newest


# ══════════════════════════════════════════════════════════════════════
# 口径断点台账 series/enx_breaks.csv
# ══════════════════════════════════════════════════════════════════════
_FOOTNOTE = re.compile(r'^\((\d+)\)\s*(.+)$')
_MONTH_YEAR = re.compile(
    r'\b(January|February|March|April|May|June|July|August|September|'
    r'October|November|December)\s+(\d{4})\b')

BREAKS_NAME = 'enx_breaks.csv'
BREAKS_FIELDS = ['column', 'break_month', 'footnote', 'athex_memo_column',
                 'official_footnote']


def _sheet_footnotes(sh):
    """{脚注编号: 原文}。脚注就写在标签行以上的 A 列，形如 "(3) Includes figures from…"。"""
    ws, out = sh.ws, {}
    for r in range(1, sh.lrow):
        v = ws.cell(r, 1).value
        if not isinstance(v, str):
            continue
        m = _FOOTNOTE.match(_norm(v))
        if m:
            out[m.group(1)] = m.group(2)
    return out


def breaks(sheets):
    """从**官方脚注原文**里抽出每一列的口径断点，返回可直接写 CSV 的行列表。

    为什么要落成 series/enx_breaks.csv，而不是在代码里写死一张断点表：
    Euronext 的断点全部来自并购（Dublin 2017、Oslo 2018/2019、Borsa Italiana 2021、
    **Athens 2025-11**），而并购是会继续发生的。写死的表在下一次并购时不会报错，
    只会安静地过时 —— 图上少画一条竖线，而少画的那条恰恰是最该画的那条。
    从脚注抽就不会：官方改脚注，这张表下次跑就跟着变，git diff 里看得见。

    「哪些列受哪条脚注影响」也不是猜的：官方把脚注编号挂在列标签与分组标题的末尾
    （`Cash Markets (Fixed Income excluded) (3)`、`Equity Index derivatives (5)`、
    `Turnover ETF (2)`、`Bonds (3)`），所以列 → 脚注 → 断点月这条链全程有据。

    只给主列出行，不给 `athex_*` 备注列出行 —— 备注列本身是连续的，它恰恰是**消除**
    2025-11 断点的那把钥匙，所以它以 `athex_memo_column` 一栏的形式挂在主列那一行上。
    """
    fns = {s: _sheet_footnotes(sh) for s, sh in sheets.items()}
    rows = []
    for c in COLUMN_SPEC:
        sh = sheets[c.sheet]
        col = sh.col(c.heads, c.label)
        for fid in sh.footnote_ids(col):
            text = fns[c.sheet].get(fid)
            if not text:
                continue
            seen = set()
            for m in _MONTH_YEAR.finditer(text):
                mon = '%s-%02d' % (
                    m.group(2), datetime.datetime.strptime(m.group(1), '%B').month)
                if mon in seen:
                    continue
                seen.add(mon)
                rows.append({
                    'column': c.name,
                    'break_month': mon,
                    'footnote': '%s (%s)' % (c.sheet, fid),
                    'athex_memo_column': c.memo or '',
                    'official_footnote': text,
                })
    rows.sort(key=lambda r: (COLUMNS.index(r['column']), r['break_month'],
                             r['footnote']))

    _check_athens_month(rows)
    return rows


# 一条脚注里往往并排写着好几次并购（"…Oslo since January 2018, Borsa Italiana since
# May 2021 and Euronext Athens since November 2025"），所以只能取**紧跟在 Athens 后面**
# 的那个月份，不能拿整条脚注里的任意月份去比 —— 那样每条脚注都会误报。
_ATHENS_SINCE = re.compile(
    r'Ath(?:ens|ex)\b[^.]{0,40}?\b(January|February|March|April|May|June|July|'
    r'August|September|October|November|December)\s+(\d{4})')


def _check_athens_month(rows, expect='2025-11'):
    """雅典并表月必须是 2025-11；不是就大声警告（但不抛异常）。

    并表月是本模块所有 `athex_*` 列语义翻转的那一天（口径坑 1）：
    这个月之前「主列 + 备注列 = pro-forma」，这个月起「主列 − 备注列 = legacy」。
    它要是变了（比如官方改成按 pro-forma 重述全历史），加减方向就反了，
    而算出来的数字仍然「看上去很正常」—— 这正是没人会发现的那类错。

    只警告不抛异常：官方重述并表基准是新闻，不是故障；数据本身还是好的，
    该停下来的是**读数的人**，不是管道。
    """
    seen = {}
    for r in rows:
        m = _ATHENS_SINCE.search(r['official_footnote'])
        if not m:
            continue
        mon = '%s-%02d' % (m.group(2),
                           datetime.datetime.strptime(m.group(1), '%B').month)
        seen[r['footnote']] = mon
    bad = sorted((k, v) for k, v in seen.items() if v != expect)
    if bad:
        print('[enx] ⚠ 官方脚注里的雅典并表月不再是 %s：%s —— '
              'athex_* 备注列的加减方向必须重新确认，跨该月的同比全部作废' % (expect, bad))
    elif not seen:
        print('[enx] ⚠ 四张 sheet 的脚注里一条都没提到 Euronext Athens —— '
              '官方可能改写了脚注，2025-11 并表断点是否还成立需人工确认')
    return bad


def _write_breaks(series_dir, rows):
    """落盘 series/enx_breaks.csv；内容没变就不动文件（保持字节级幂等）。"""
    path = os.path.join(series_dir, BREAKS_NAME)
    sio = io.StringIO()
    w = csv.DictWriter(sio, BREAKS_FIELDS, lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
    new = sio.getvalue()
    old = None
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            old = f.read()
    if old == new:
        return False
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(new)
    os.replace(tmp, path)
    return True


# ══════════════════════════════════════════════════════════════════════
# 恒等式闸门，以及「上游自己就对不平」的逐格登记
# ══════════════════════════════════════════════════════════════════════
# 为什么要有这张登记表 —— 而不是调大 tol，也不是把 raise 降成警告：
#
#   · 这道闸门被某一格挡住，冻住的是整条腿，不是一个月。_validate 每轮把**全史**重扫一遍
#     再逐月撞恒等式，hist 又是滚动全历史文件 ⇒ 那一格只要还在，之后每一个新月份都进不来。
#     2026-08 就是这么把 enx 冻住的：2026-09-08 起 monthly_run 连续 5 轮 FAIL，而 raise
#     在 update() 前段，latest 对表、停摆哨兵、断点表、重述落盘、发布日登记五步一并没跑。
#   · 调大 tol 不是调参，是二选一。2026-09-12 对 8 月版 hist（sha256 见登记项）逐月复算
#     （py3.12，与 _identity 同样用内置 sum() 在 ADV 空间量；逐项 a+b+c 量主恒等式是 3.738e-16 /
#     2021-01，结论不变）：主恒等式 176 个月，除 2026-08 的 2.274e-09 外最大 3.414e-16（2024-09），
#     相对差大于 1e-12 的有且只有 2026-08；Athex 备注那道 68 个月最大 2.478e-16。中间空着七个数量级
#     ⇒ 任何能放 2026-08 过去的 tol，都恰好丢掉这道闸门全史唯一一次浮点噪声以上的读数；
#     以后别的月份再冒出同量级的上游不平，就再也没人看得见。
#   · 降成警告：连这道闸门本来要抓的「某列错行」也一起放过。
#
# 所以放行判据刻意做窄：(月份, 总量列) 命中登记，**且**本轮读到的交易日与登记严格相等、
# 总量与分项之和折回官方原表单位后都与登记值相对差 ≤ _GAP_MATCH_REL —— 三条全满足才放行，
# 并且每轮在 stdout 打一行（fetch 模块的 print 会进 monthly_run 日志，09-12 日志里
# [lseg]/[nanya] 那些行就是这么来的）。同一格下一版要是换了个差额（改了但没改平），
# 读数对不上登记，照样 raise；上游哪天把它改平了（rel ≤ tol），打一行「登记可删」，不 raise。
#
# 不按 sha256 放行：hist 下个月一追加新行 sha 就变，按 sha 认等于下个月再冻一次。
# sha256 记在登记项里只是出处 ——「这两个数是从哪一版文件里读出来的」。
#
# ⚠ 往这里加一条之前，先把同一套证据链走一遍：至少要有一条**不经 hist 分项**的独立旁证
#   说明总量本身没错（2026-08 用的是伴生 latest 工作簿，见下）。拿不出旁证的不平，
#   正是闸门该拦的那种，不许登记。
# ⚠ 增删登记时同步改 build/specs/enx.py 页尾注「现货恒等式」那一条 —— 那句读者看得见，
#   里面点名了 2026-08 这个例外；只改这里，页面上就印着一句跟闸门对不上的话。
IDENTITY_UPSTREAM_GAPS = {
    ('2026-08', 'adv_cash_adnv_eurbn'): {
        # hist 'Equity Markets' R186（Period 2026-08-01）的原始单元格，单位 €m 月合计：
        #   C6  Total Turnover                 263866.89008645003
        #   C8  Turnover Equities              240425.60853173997
        #   C10 Turnover ETF                    20661.36798232
        #   C12 Turnover Structured Products     2779.91297239
        #   C3  Nb of trading days                 21
        'unit': '€m 月合计',
        'days': 21,
        'total': 263866.89008645003,
        'parts_sum': 263866.88948644995,     # C8 + C10 + C12，按此顺序浮点相加
        'gap': '€600.00006（Decimal 精确差 0.000600000061695 €m）',
        'rel': 2.2738739980062947e-09,       # _identity 实际比的 ADV 空间（÷21÷1000）的值
        'hist_sha256':
            '2b47522c3c5d882125ef2e9a46aa81684bccb6aa0c524947a88976cd848a99fb',
        # ↑ 223,390 B，Last-Modified: Mon, 07 Sep 2026 15:35:21 GMT
        #
        # 为什么认定是上游自己不平、不是我们读错（2026-09-12 活网重取两份官方文件实测）：
        #   ① 伴生 latest 工作簿（50,374 B，Last-Modified 07 Sep 2026 15:35:04 GMT，
        #      sha256 54bd1ee9…）Equity Markets R13C2「Total Cash Market」2026-08
        #      = 263866.89008645003，与 hist C6 逐位相等；分项之和那个数在 latest 里一格都没有。
        #   ② latest R14C2 官方自算「ADV Cash Market」= 12565.090004116668 = 总量 ÷ 21，
        #      逐位相等 —— 官方自己发布的 ADV 用的就是总量。
        #   ③ latest R13C7「Q3 2026」= 597094.9775615999 = hist 7 月 + 8 月总量（相对差
        #      2e-16）；拿分项之和去加就差这 €600。
        #   ④ parse_workbook 每个月只认一个行号（同月两行直接抛），四列同行读取，
        #      「某一列单独错行」在这里表达不出来；现货成交额分组（C6–C12）下除这四列外
        #      只有三列 Athex 备注，没有第四个分项漏在恒等式外。
        #   差额从哪来无从判断：月度新闻稿正文没有数字（口径坑 17）。对页面无影响：
        #   €600 ÷ 21 = €28.57/日，现货 ADV 线按 0.1 €bn 显示。
    },
}

# 登记值比对的相对容差。折回原表单位（× 交易日 × scale，即 _scale 的逆运算）2026-08 实测
# 与原始单元格逐位相等，1e-14 只是给乘除留约 45 个 ULP 的余量。折成钱：263,866.89 €m
# × 1e-14 ≈ €0.0026，不到 1 分钱 —— 这一格的差额只要变动 1 分钱以上就对不上登记
# （离线实测：总量 +€0.01 即 raise），而 1 个 ULP 的浮点抖动照样放行。
_GAP_MATCH_REL = 1e-14

# 折回原表单位要知道每列的交易日列与 scale（athex_* 备注列与主列同口径）。
_COL_BY_NAME = dict([(c.name, c) for c in COLUMN_SPEC]
                    + [(c.memo, c) for c in COLUMN_SPEC if c.memo])
_DAYS_COL = {key: name for name, key, _s in DAYS_SPEC}


def _gap_mismatch(rec, total, rhs, reg):
    """本轮读数与登记逐值比对，返回 (why, got)。

    why：全对得上是 None，否则是「哪个数变了、偏了多少」的一句话（方便对着新 vintage 重新登记）。
    got：本轮折回官方原表单位的 {'days', 'total', 'parts_sum'}（交易日就对不上时只有 days）——
    放行那行打印的是它，不是登记常量：出声行要是抄登记值，本轮读数真变了日志上也看不出来。

    比的是官方原表单位而不是入库的 ADV —— 登记值要能拿去 Excel 里逐位对照。
    交易日要求严格相等：天数一变 ADV 全变，那已经不是登记的那份读数了。
    「对得上」写成 `<=` 再取反，不写 `>`：NaN 参与的比较恒为 False，写成 `>` 时 NaN 读数
    会被判成逐值一致而放行（2026-09-12 复核实测：登记月的总量或结构化产品置 NaN，旧写法
    _validate 照样返回 2026-08）。生产路径今天产不出 NaN（openpyxl 3.1.5 读 'NaN' 直接抛），
    这里防的是以后换解析路径。
    """
    col = _COL_BY_NAME[total]
    got = {}
    k = col.scale
    if col.days:
        got['days'] = days = rec.get(_DAYS_COL[col.days])
        if days != reg['days']:
            return '交易日 %r，登记是 %r' % (days, reg['days']), got
        k = days * col.scale
    got['total'], got['parts_sum'] = rec[total] * k, rhs * k
    bad = []
    for lab, key in (('总量', 'total'), ('分项之和', 'parts_sum')):
        dev = abs(got[key] - reg[key])
        if not (dev <= _GAP_MATCH_REL * abs(reg[key])):
            bad.append('%s折回原表 %r，登记是 %r，相对偏差 %.3e'
                       % (lab, got[key], reg[key], dev / abs(reg[key])))
    return '；'.join(bad) or None, got


def _identity(mon, rec, total, parts, tol=1e-9):
    """total ≡ Σparts，相对差 > tol 就抛。

    tol=1e-9 是给浮点舍入留的（全史实测噪声最大 3.4e-16，py3.12 内置 sum() 量，见 _validate），
    不为任何一格上游残差放宽 —— 唯一的出口是 IDENTITY_UPSTREAM_GAPS 逐值登记过的格子，
    理由见那张表上面的注释。
    NaN 一律按不成立处理：rel 是 NaN 时 `rel <= tol` 为 False，未登记直接抛，登记过的
    由 _gap_mismatch 判成对不上再抛（旧写法 `rel > tol` 对 NaN 为 False，会静默放过）。
    """
    if rec.get(total) is None or any(rec.get(p) is None for p in parts):
        return
    lhs, rhs = rec[total], sum(rec[p] for p in parts)
    if lhs == 0:
        return
    rel = abs(lhs - rhs) / abs(lhs)
    reg = IDENTITY_UPSTREAM_GAPS.get((mon, total))
    if rel <= tol:
        if reg:
            print('[enx] 登记可删：%s %s 上游已经改平（本轮相对差 %.3e ≤ tol %.0e），'
                  'IDENTITY_UPSTREAM_GAPS 里这一条可以删了，build/specs/enx.py 页尾注里点名'
                  '这一格的那半句同步删。若该月已入库，官方改动的那一格'
                  '会进 cache/enx_restatements.csv（本模块不覆盖已入库值）'
                  % (mon, total, rel, tol))
        return
    msg = ('%s 恒等式不成立：%s=%r 与 %s 之和 %r 相对差 %.3e —— '
           % (mon, total, lhs, parts, rhs, rel))
    if reg is None:
        # 前半句与 2026-09-08~12 生产日志里那 5 行 FAIL 逐字相同，只在后面补一句：
        # 这道闸门撞不上的第一例（2026-08）恰恰不是错行，而是上游自己不平 —— 下一例
        # 要是也这样，读日志的人不该先去翻解析器。
        raise EnxFetchError(
            msg + '多半是某一列错行了。若不经 hist 分项的旁证（伴生 latest 工作簿的 Total/ADV、'
            '季度合计）说明 Total 本身无误，则可能是上游工作簿自己不平：按 fetch/enx.py '
            'IDENTITY_UPSTREAM_GAPS 上方注释逐值登记，不许放宽 tol')
    why, got = _gap_mismatch(rec, total, rhs, reg)
    if why:
        raise EnxFetchError(
            msg + '这一格在 IDENTITY_UPSTREAM_GAPS 有登记（上游自身不平），但本轮读数与'
            '登记对不上（%s）—— 官方改了这一格却没改平，或者这回真是错行。'
            '登记只认原来那份读数，拒绝放行' % why)
    print('[enx] 恒等式放行（上游自身不平，已登记）：%s %s 相对差 %.3e > tol %.0e；'
          '本轮折回原表（%s）交易日 %r、总量 %r vs 分项之和 %r，与 IDENTITY_UPSTREAM_GAPS '
          '登记逐值一致（相对偏差 ≤ %.0e；登记出处 hist sha256 %s…）。上游改平之前每轮都会打这一行'
          % (mon, total, rel, tol, reg['unit'], got.get('days'), got['total'],
             got['parts_sum'], _GAP_MATCH_REL, reg['hist_sha256'][:12]))


# ══════════════════════════════════════════════════════════════════════
# 对表自检：官方 latest 文件（**只比最新月这一列**，见口径坑 6）
# ══════════════════════════════════════════════════════════════════════
# latest 文件跑在 hist 文件前面，多少天之内还算「两份文件都在发布窗口里」。
#
# 依据是本模块 docstring「发布节奏」那一节的普查（2019-01 → 2026-06 共 90 个数据月，
# 逐月找到它自己那期新闻稿，命中 90/90）：发布日落在**次月第 3 至第 13 天**。
# 两份 xlsx 挂在同一个 CDN 目录下，所以最坏的**合法**背离就是 latest 走第 3 天、
# hist 走第 13 天 —— 10 天。这里取一倍余量 20 天：宁可晚十天发现，也绝不能在某个
# 发布日把一家本来好好的源打成 FAIL（每月假一次的警报，人很快就学会无视了）。
# 20 天同时短于一个发布周期，所以真的停摆会在下一期发出来之前就被喊出来。
_LATEST_AHEAD_GRACE_DAYS = 20
# 背离是从哪天开始的，记在 cache 里（gitignore，tools/prune_cache.py 可能清掉它）。
# 丢了这个文件只会让计时从头开始 = 晚一点发现，**永远不会**凭空造出一次 FAIL。
# 这个不对称是刻意的：护栏失效的代价是漏报一阵子，护栏误报的代价是整家停更。
_LATEST_SYNC_STATE = 'enx_latest_sync.json'


def _read_latest_sync(cache_dir):
    """读背离台账；读不到 / 读坏了一律当没有。绝不因为这个文件的毛病让抓取失败。"""
    try:
        with open(os.path.join(cache_dir, _LATEST_SYNC_STATE), encoding='utf-8') as f:
            st = json.load(f)
        return st if isinstance(st, dict) and st.get('first_seen') else None
    except Exception:                                     # noqa: BLE001
        return None


def _note_latest_sync(cache_dir, ahead, hist):
    """记（或清）「latest 跑在 hist 前面」这件事，返回本轮的台账；出错一律当没记上。

    ahead=None 表示两边同步、或 latest 反而落后、或判据本身没了 —— 三种都清台账：
    只有「latest 明确领先」才是需要计时的那件事。

    计时锚在 **hist 停在哪个月**，不是 latest 到了哪个月：hist 一直不动而 latest
    每月往前走时，按 latest 记会每个月把时钟清零，那样一次永久停摆永远等不到超时。
    """
    path = os.path.join(cache_dir, _LATEST_SYNC_STATE)
    try:
        if ahead is None:
            if os.path.exists(path):
                os.remove(path)
            return None
        today = datetime.date.today().isoformat()
        old = _read_latest_sync(cache_dir)
        first = old['first_seen'] if old and old.get('hist') == hist else today
        st = {'hist': hist, 'latest': ahead, 'first_seen': first, 'last_seen': today}
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(st, f, ensure_ascii=False, sort_keys=True)
        since = datetime.date(*map(int, first.split('-')))
        st['days'] = (datetime.date.today() - since).days
        return st
    except Exception:                                     # noqa: BLE001
        return None


def _guard_latest_stall(cache_dir, newest):
    """两份官方文件已经背离太久 → 抛。这是本模块唯一一道**带记忆**的护栏。

    没有它的时候，这件事长这样：官方改了 hist 的文件名，写死的直链还能下到一个再也
    不更新的孤儿副本（_check_landing 只打警告、按设计不阻断），parse_workbook 与
    _validate 在那份孤儿上照样全过（它结构好好的，只是永远停在某个月），update()
    一个新月份都加不出来，monthly_run 干干净净地报 enx NOCHANGE。而 latest 文件还在
    往前走，_crosscheck_latest_month 每天打一句「两边不同步，对表跳过」—— 那句话与
    发布窗口里那一两天的正常时间差**一字不差**。连续失败十天与成功十天在日志里长得
    一样，就是 README 说的第四类失败。加进来的那样东西是「这个背离已经站了多少天」。

    三个条件都成立才炸，任何一个存疑都放过（宁可漏报）：
      · 台账里记的 hist 月份就是这一轮解析出来的 newest —— 否则说明 hist 已经动过了；
      · last_seen 是今天 —— 也就是**这一轮亲眼确认过**背离还在。latest 下不下来、
        判据读不读得出，都会让这一条不成立，于是护栏自己让路，不会拿一条昨天的
        记录去炸今天；
      · 背离已经超过 _LATEST_AHEAD_GRACE_DAYS 天。
    """
    st = _read_latest_sync(cache_dir)
    if not st or st.get('hist') != newest:
        return
    if st.get('last_seen') != datetime.date.today().isoformat():
        return
    try:
        first = datetime.date(*map(int, st['first_seen'].split('-')))
    except (TypeError, ValueError):
        return
    days = (datetime.date.today() - first).days
    if days <= _LATEST_AHEAD_GRACE_DAYS:
        return
    raise EnxFetchError(
        '官方 latest 文件已经出到 %s，而历史文件 %s 从 %s 起就一直停在 %s —— '
        '第 %d 天了，超过 %d 天的宽限期。这个宽限期是按实测发布日（次月第 3–13 天）'
        '的两倍留的，所以这已经不像发布窗口的时间差，更像历史文件被改名之后直链下到了'
        '一个不再更新的孤儿副本（落地页检查按设计只警告不阻断）。拒绝写入，'
        '请人工打开 %s 确认 %s 这个文件名还在，然后删掉 cache/%s 让计时重来'
        % (st.get('latest'), HIST_NAME, st['first_seen'], newest, days,
           _LATEST_AHEAD_GRACE_DAYS, LANDING_URL, HIST_NAME, _LATEST_SYNC_STATE))


def _crosscheck_latest_month(data, newest, cache_dir):
    """拿官方算好的 ADV 撞我们自算的 ADV，返回一句人话说明。

    这是免费的第二意见：官方在 latest 文件里直接给出 ADV Cash Market，
    而我们是从历史文件的「月总量 ÷ 交易日」自己算的。两条完全独立的路径。

    ⚠ 只比**最新月**那一列，因为 latest 的同比/上年列用的是 pro-forma 含 Athens 的基准
    （它自己的脚注写 "since January 2025"），与历史文件主列的 "since November 2025"
    不是一个口径，2025-11 之前会看到最高 23% 的假失配。当月两个基准重合，才可比。

    差得离谱（>1e-3）才抛异常：那种量级只可能是取错列或用错单位。
    取不到文件、判据读不出来、或 latest 的月份还没跟上，本函数一律只返回一句话、
    不阻断 —— 主源自己的结构校验与恒等式才是护栏，辅助源不该有权卡住整月发布。

    ⚠ 唯一的例外由 _guard_latest_stall 单独执行，不在本函数里：**latest 领先 hist**
    这一支会把「背离从哪天开始」记进 cache（见 _note_latest_sync），站过宽限期才炸。
    本函数只负责记账与措辞，谁都不要把这里的 return 当成「这条路永远不会 FAIL」。
    """
    try:
        path, _lm = _download(cache_dir, LATEST_NAME)
        wb = openpyxl.load_workbook(path, data_only=True)
        if 'Equity Markets' not in wb.sheetnames:
            return '对表跳过：latest 文件里没有 Equity Markets sheet'
        ws = wb['Equity Markets']
        # 第 2 列固定是「最新月」。先核对它自报的月份，对不上就不比。
        mon_cell = None
        for r in range(1, 12):
            v = ws.cell(r, 2).value
            if isinstance(v, datetime.datetime):
                mon_cell = '%04d-%02d' % (v.year, v.month)
                break
        if mon_cell != newest:
            # 原来这三种情况共用一句「两边不同步」。方向不一样，处置就不该一样：
            if mon_cell is None:
                # 判据本身没了（官方挪了 latest 的月份格）。不阻断 —— 辅助源不该有权
                # 卡住整月发布 —— 但照 fetch/ice.py 的 _crosscheck_workbook_month
                # 明说一句「今天没人对过表」，别让它和「对过表且一致」长得一样。
                _note_latest_sync(cache_dir, None, newest)
                return ('⚠ 护栏失效：latest 文件的 Equity Markets 表头里读不出最新月，'
                        '这一轮没有独立于解析器的月份判据（官方可能挪了那一格）')
            if mon_cell > newest:
                # latest 跑在前面 = 历史文件可能卡住了。这一支要**计时**，
                # 超过宽限期由 _guard_latest_stall 抛，见那里的推理。
                st = _note_latest_sync(cache_dir, mon_cell, newest)
                if not st:
                    return ('对表跳过：latest 文件已到 %s，历史文件还停在 %s '
                            '（背离台账写不进 cache，本轮不计时）' % (mon_cell, newest))
                return ('对表跳过：latest 文件已到 %s，历史文件还停在 %s —— '
                        '这个背离自 %s 起，今天是第 %d 天，连续超过 %d 天就会抛异常'
                        % (mon_cell, newest, st['first_seen'], st['days'],
                           _LATEST_AHEAD_GRACE_DAYS))
            # latest 反而落后于历史文件：hist 领先不是「解析漏了月」的证据，
            # 只是 47KB 那份还没刷新。只提示，不计时，并把台账清掉。
            _note_latest_sync(cache_dir, None, newest)
            return ('对表跳过：latest 文件的最新月是 %s，反而落后于历史文件的 %s，'
                    '两边不同步' % (mon_cell, newest))
        _note_latest_sync(cache_dir, None, newest)        # 两边同步 → 清掉计时
        # 'ADV Cash Market' 在 latest 里出现两次（笔数区一次、金额区一次），
        # 取金额区那一个：先定位 'TRANSACTION VALUE' 小节标题，再往下找。
        sec = None
        for r in range(1, ws.max_row + 1):
            a = _norm(ws.cell(r, 1).value)
            if a.upper().startswith('TRANSACTION VALUE'):
                sec = r
                break
        if sec is None:
            return '对表跳过：latest 文件里找不到 TRANSACTION VALUE 小节'
        official = None
        for r in range(sec, min(sec + 8, ws.max_row) + 1):
            if _norm(ws.cell(r, 1).value) == 'ADV Cash Market':
                official = ws.cell(r, 2).value
                break
        if not isinstance(official, (int, float)):
            return '对表跳过：latest 文件的 ADV Cash Market 取不到数（%r）' % official
        mine = data[newest]['adv_cash_adnv_eurbn'] * 1e3      # €bn/日 → €m/日
        rel = abs(mine - official) / abs(official)
    except EnxFetchError as e:
        return '对表跳过：%r' % e
    except Exception as e:                                    # noqa: BLE001
        return '对表跳过（latest 文件解析异常，不阻断主流程）：%r' % e

    if rel > 1e-3:
        raise EnxFetchError(
            '%s 现货 ADV 自算 %.6f €m/日 与官方 latest 文件的 %.6f 相对差 %.3e —— '
            '这个量级只可能是取错列或用错单位，拒绝写入' % (newest, mine, official, rel))
    verdict = '完全一致' if mine == official else '相对差 %.3e' % rel
    return ('%s 现货 ADV 自算 %r €m/日 vs 官方 latest 文件 %r，%s'
            % (newest, mine, official, verdict))


# ══════════════════════════════════════════════════════════════════════
# 发布日
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


_TR = re.compile(r'<tr>(.*?)</tr>', re.S)
_TIME = re.compile(r'<time[^>]*datetime="([^"]+)"[^>]*>([^<]*)</time>')
_A = re.compile(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_TAGS = re.compile(r'<[^>]+>')
# 电头：'… Oslo and Paris – 6 July 2026 – Euronext, the …'
_DATELINE = re.compile(r'[–—-]\s*(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})\s*[–—-]')


def _news_rows(cache_dir, pages=3):
    """从新闻列表页抓 [(本地日期 YYYY-MM-DD, datetime 属性原文, href, 标题)]。

    从**列表页**取而不是按模板拼 slug —— 拼 slug 的真实代价是 2023-03 那期：
    它的标题是 "Euronext announces highest cash volumes in a year in March 2023"，
    slug 是 euronext-announces-highest-cash-volumes-year-march，
    两种模板拼法（…-for-march-2023 与 …-for-march-2023-0）实测**双双 404**。

    日期以 <time> 的**渲染文本**（DD/MM/YYYY，站点自己按巴黎时间渲染的日历日）为准，
    `datetime` 属性（UTC）由 _record_source_date 拿去互证：实测发布时刻在
    07:30Z–17:06Z 之间，UTC 日期与巴黎日期恒等，但与其把这条依赖写死在代码里，
    不如每次都让两个值互相印证、不一致就写进 evidence 让人看见。
    """
    out = []
    for p in range(pages):
        try:
            html, _h = _http_get(NEWS_URL % p, tries=3)
        except EnxFetchError as e:
            print('[enx] 警告：新闻列表页第 %d 页取不到（%r），发布日可能缺席' % (p, e))
            break
        _write_bytes(os.path.join(cache_dir, 'enx_news_p%d.html' % p), html)
        txt = html.decode('utf-8', 'replace')
        for m in _TR.finditer(txt):
            seg = m.group(1)
            t, a = _TIME.search(seg), _A.search(seg)
            if not (t and a):
                continue
            shown = t.group(2).strip()
            mm = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', shown)
            if not mm:
                continue
            local = '%s-%s-%s' % (mm.group(3), mm.group(2), mm.group(1))
            title = _unescape(_TAGS.sub('', a.group(2))).strip()
            out.append((local, t.group(1), a.group(1), title))
        time.sleep(0.8)             # 主站连打会掐连接，见 _http_get
    return out


def _unescape(s):
    import html as _html
    return _html.unescape(s)


def _month_end_next(month):
    y, m = int(month[:4]), int(month[5:7])
    return ('%04d-01-01' % (y + 1)) if m == 12 else '%04d-%02d-01' % (y, m + 1)


def _find_release(rows, month):
    """在列表页结果里找 month 的月度成交量稿，返回 (日期, datetime 属性, href, 标题) 或 None。

    宽松匹配：标题里同时出现 announces…volume 与「<英文月名> <年>」即可。
    这样才能同时命中标准模板与 2023-03 那种「创纪录」改写标题（口径坑 16）。
    再加一道时间窗（数据月结束后 1-60 天内），挡住把某篇回顾性文章误认成月报的情况。
    """
    y, m = int(month[:4]), int(month[5:7])
    mname = datetime.date(y, m, 1).strftime('%B')
    pat_kind = re.compile(r'announces\b.*\bvolume', re.I)
    pat_mon = re.compile(r'\b%s\s+%d\b' % (mname, y), re.I)
    lo = _month_end_next(month)
    hi = (datetime.date(*map(int, lo.split('-')))
          + datetime.timedelta(days=60)).isoformat()
    hit = [r for r in rows
           if pat_kind.search(r[3]) and pat_mon.search(r[3]) and lo <= r[0] <= hi]
    return min(hit) if hit else None


def _dateline(cache_dir, href, month):
    """从详情页正文电头取「6 July 2026」这种人可读的日期，取不到返回 None。

    只是佐证，不是主证 —— 主证是列表页的 <time datetime>。
    2023-03 那期的详情页 meta description 被联系人区块占掉，电头就抓不到；
    这种时候 evidence 少一句话，而不是整条发布日缺席。
    ⚠ 详情页**没有** JSON-LD 的 datePublished 字段（页面上唯一的 ld+json 块是面包屑），
    不要去那里找。
    """
    url = href if href.startswith('http') else SITE_ROOT + href
    try:
        html, _h = _http_get(url, tries=2)
    except EnxFetchError:
        return None
    _write_bytes(os.path.join(cache_dir, 'enx_pr_%s.html' % month), html)
    txt = html.decode('utf-8', 'replace')
    m = re.search(r'<meta name="description" content="([^"]*)"', txt)
    hay = _unescape(m.group(1)) if m else txt[:20000]
    d = _DATELINE.search(hay)
    return d.group(1) if d else None


def _record_source_date(series_dir, cache_dir, month):
    """给 month 记一条官方发布日；取不到就让它缺席，**绝不抛异常**。

    只给「本次真的新入库的那个最新月」记 —— 同一份 xlsx 里躺着全部历史月（现已一百七十多个），
    它的上线时刻只能证明最新月是这天发的，顺手给旧月份都盖上今天的日期就是造假。
    已有记录一律不覆盖：官方会重述并原地重传文件（口径坑 15），
    覆盖等于把当初那次真发布的日期改错，而页面照印不误。
    """
    sd = _source_dates()
    if sd.lookup(series_dir, 'enx', month):
        return None
    rows = _news_rows(cache_dir)
    hit = _find_release(rows, month)
    if not hit:
        print('[enx] 警告：新闻列表页里没找到 %s 的月度成交量稿，本月不记发布日'
              '（页面抬头会省掉「官方发布于」那半句）' % month)
        return None
    day, dt_attr, href, title = hit
    ev = ('新闻列表页 %s 的一行「%s」：<time datetime="%s">%s</time>'
          % (NEWS_URL % 0, title, dt_attr, _ddmmyyyy(day)))
    # UTC 属性与渲染出来的巴黎日期互证。两者不同 = 发布时刻跨了午夜，
    # 那种情况下「哪天发的」有歧义，必须让读 evidence 的人看见，而不是替他选一个。
    if dt_attr[:10] != day:
        ev += '（⚠ datetime 属性的 UTC 日期 %s 与渲染日期不同）' % dt_attr[:10]
    line = _dateline(cache_dir, href, month)
    if line:
        try:
            same = (datetime.datetime.strptime(line, '%d %B %Y').date().isoformat()
                    == day)
        except ValueError:
            same = False
        ev += '；详情页 %s%s 正文电头 "– %s –" %s' % (
            SITE_ROOT, href, line, '一致' if same else '⚠ 与列表页不一致')
    sd.record(series_dir, 'enx', month, day, ev)
    return day


def _ddmmyyyy(iso):
    return '%s/%s/%s' % (iso[8:10], iso[5:7], iso[:4])


def backfill_source_dates(series_dir, cache_dir, pages=8, months=None):
    """人工回补历史发布日（不由 update() 自动调用）。

    每个月的发布日来自**那个月自己的新闻稿**，所以批量回补并不违反「一份文件只为
    自己的最新月作证」——那条规矩管的是文件时间戳，不管逐月的新闻稿。
    但它会一次性往 series/source_dates.csv 里塞几十行，属于人工决策，
    所以留成显式入口：`python3 fetch/enx.py source-dates`。
    """
    sd = _source_dates()
    rows = _news_rows(cache_dir, pages=pages)
    if months is None:
        csv_path = os.path.join(series_dir, 'enx.csv')
        with open(csv_path, newline='', encoding='utf-8') as f:
            months = [r[0] for r in list(csv.reader(f))[1:] if r and r[0].strip()]
    done = []
    for mon in sorted(months):
        if sd.lookup(series_dir, 'enx', mon):
            continue
        hit = _find_release(rows, mon)
        if not hit:
            continue
        day, dt_attr, href, title = hit
        sd.record(series_dir, 'enx', mon, day,
                  '新闻列表页「%s」：<time datetime="%s">%s</time>（%s%s）'
                  % (title, dt_attr, _ddmmyyyy(day), SITE_ROOT, href))
        done.append((mon, day))
    return done


# ══════════════════════════════════════════════════════════════════════
# 对外接口
# ══════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════
# 采纳登记：人核过、逐格钉死的官方重述（口径坑 4「永不覆盖」的唯一出口）
# ══════════════════════════════════════════════════════════════════════
# 为什么要有这张表 —— 而不是把 update() 改成「重述即覆盖」，也不是继续一律不覆盖：
#
#   · 默认规矩不变：已入库值永不覆盖，冲突写 cache/enx_restatements.csv。一格对不上，
#     可能是官方改口径、官方更正，也可能是我们这边错行，机器分不清。
#   · 但官方把**一整列**按新口径重述时，「永不覆盖」本身就在造错数：新月份按新口径进来、
#     旧月份冻在旧口径，同一列两套口径拼在一起 —— 拼接处凭空一个口径台阶，其后一年的
#     同比都是新口径比旧口径，而且安安静静：提示只进 gitignore 掉的 cache，全仓没有代码读那个文件。
#   · 「重述即覆盖」又太宽：错行会被当成重述静默吞进 series，正是默认规矩要挡的事。
#
# 所以采纳做成**逐格钉死**。一条登记 = (列集合, 月份区间, 格数, 指纹)：本轮冲突里落在
# 「列集合 × 月份区间」内的格子，按 (月, 列, 库内旧值, 官方新值) 排序、逐行逗号拼接、
# 换行连接后取 sha256；格数与指纹都对上才整批覆盖，差一格、改一位都整批不采纳（照旧写
# 冲突文件并打一行说明）。于是：
#   · 登记只认人核过的那一次「旧值 → 新值」。官方以后再动这些格子，库内旧值已是新口径，
#     指纹必然对不上 —— 回到默认路径等人核，不会被这条登记顺手吞掉；
#   · 不按 hist 的 sha256 认：hist 每月追加新行 sha 就变（同 IDENTITY_UPSTREAM_GAPS 的理由），
#     sha 只记作出处；
#   · 采纳之后库内与官方一致，这条登记不再命中任何格子 —— 留着是出处，不是开关。
# 覆盖值照旧由本轮解析值经 _fmt 写回（不手改 CSV）。逐格前后值 = 该次提交里 series/enx.csv
# 的 diff；逐月前后对照表与官方出处链接见 docs/verify/enx.md「股票清算量整列重述（2026-08 版）」。
#
# ⚠ 往这里加一条之前，先走完同一套证据链：①逐列量清冲突（月数、幅度、与同表相邻列的算术
#   关系）；②至少一条**不经 hist 本身**的官方旁证说明新值是官方现行口径；③同步改
#   build/specs/enx.py 里描述这一列的释义与页尾注 —— 否则页面印着与数据对不上的话。
#   关于 ②：伴生 latest 工作簿的「上月」/ Q3 / YTD 列可以给 2025-11 之后的月份作旁证（雅典并表之后
#   两份文件的基准重合；更早的月份不行，见口径坑 6）。cache/raw/enx/ 里留着各版 latest 的存证。
#   但 latest 与 hist 出自同一套数据，它只能证明「官方现在是这个数」，证明不了这个数不是录错的 ——
#   录入层面的疑点要靠不走这套数据的出处（业绩稿、Cash 月报、发行人公告）去排除，排除不了就不采纳
#   （例子见文末「不采纳」清单里的债券零售清算）。
#   同一批冲突按「证据链」分条登记，每条的「列 × 月份区间」只圈人核过的格子：圈大了，以后官方在
#   圈内别的格子上再改一次，这一条会整批报「对不上」，读日志的人会以为是已采纳的那几格出了事。
ACCEPTED_RESTATEMENTS = [
    {
        'id': '2026-08 股票清算量：雅典换计数口径并 pro-forma 回填到 2022-01',
        'columns': ('adv_shares_cleared_kcontracts', 'athex_adv_shares_cleared_kcontracts'),
        'months': ('2022-01', '2026-06'),
        'cells': 108,
        'sha256': '303812a12f0a212a26f4f738f02e65cfb11c18636d7f57ba54f4cedcb24fee3c',
        # 出处：hist 'Equity Markets' C13「Shares (nb of contracts) (4)」与 C14「Athex」。
        #   7 月数据版（220,465 B，sha256 5f2fd7b0e696…）就已是新口径，库里 2026-07 那行（08-08 入库）
        #   与它一致；本登记核的是 8 月数据版（223,390 B，Last-Modified Mon, 07 Sep 2026 15:35:21 GMT，
        #   sha256 2b47522c3c5d882125ef2e9a46aa81684bccb6aa0c524947a88976cd848a99fb）。
        #
        # 冲突的形状（2026-09-12 对 8 月版逐月复算；库内旧值来自 2026-08-07 建表时的那一版）：
        #   · 主列 54 个月全部上修 +3.29% ~ +15.19%（中位 +5.45%）；备注列 54 个月全部 ×6.84 ~ ×11.78。
        #   · 2022-01..2025-10 共 46 个月：新主列 − 旧主列 ≡ 新备注列（相对差 < 1e-9）
        #     ⇒ 并表前的主列现在含雅典（pro-forma），旧主列是 legacy；
        #   · 2025-11..2026-05 共 7 个月：新主列 − 旧主列 ≡ 新备注列 − 旧备注列
        #     ⇒ legacy 那一块一格没动，换掉的只是雅典那一块；
        #   · 新备注列 ÷ 雅典现货成交笔数（双边计，athex_adv_cash_trades_k）在 2022-01..2026-08
        #     56 个月里是 0.49850–0.49998，旧备注列是 0.04239–0.07304 ⇒ 新口径 = 雅典单边成交笔数，
        #     与本列表头 "Clearing volume (single counted)" 自洽；
        #   · 2026-06 另有一处：8 月版在口径切换之外把 legacy 那一块又上修了 1.1274 千/日
        #     （×22 天 = 24,802.5，+0.09%），同一版里的数据更正，一并采纳。
        #   同一版里其余列的冲突（mktcap_eurtn 等）都是 2025-11 之后个别月份的更正或浮点表示差，不在这条登记里：
        #   人核之后另起了几条登记（见下），浮点表示差由 _same_number 滤掉，余下的列在文末「不采纳」清单。
        #
        # 为什么采纳（官方旁证，均不经 hist 本身；2026-09-12 读原文、本机复算）：
        #   ① 旧值当年是忠实的：Q4 2024 业绩稿「Shares (number of contracts – single counted)」
        #      FY2024 234,777,332 / FY2023 83,486,969，Q2 2026 业绩稿（07-30）Q2 2026 75,523,319，
        #      都等于旧主列逐月加总（差 ≤ 0.5，官方取整）；同稿 Q2 2025 备考 76,120,584 = 旧主列
        #      + 旧备注列 ⇒ 7 月底以前官方口径就是旧的，库里旧值不是我们抓错的。
        #   ② 官方现行口径是新的：伴生 latest 工作簿（50,374 B，Last-Modified 07 Sep 2026 15:35:04 GMT，
        #      sha256 54bd1ee92daa…）「CLEARING (nb of contracts - Single counted) / Shares」印的
        #      2025-08 = 18,858,349、Q3 2025 = 42,344,286、YTD 2025 = 200,872,961，与新主列逐位相等
        #      （旧口径分别低 5.5% / 5.1% / 4.0%）；它印的 8 月同比 +8.2426% 与新口径逐位相等，
        #      旧口径算出来是 +14.60%。
        #   ③ 新雅典数是 ATHEX 自己的数：ATHEX 年报 Cash Market「Number of trades」2022 = 7.5m、
        #      2023 = 9.2m；新备注列还原成年合计是 7.437m / 9.186m（−0.84% / −0.15%），旧备注列只有
        #      约 0.97m / 1.19m，本机在 ATHEX 年报与 FESE 年报里都没找到它对应的量。
        #   ④ 官方没有为这次切换写说明：两版 hist 表头与脚注逐字相同，脚注 (4) 仍只讲 2023-11
        #      清算扩容；Equity Markets 脚注 (3) 仍写 "Euronext Athens since November 2025"，与这一列的
        #      新口径矛盾 —— series/enx_breaks.csv 照抽不误，页面那一侧不画这一列的雅典红线
        #      （build/specs/enx.py `_read_breaks`，前提从 series 现算）。
        #   不采纳的后果：同一列 2026-07 起新口径、之前旧口径 —— 2026-07 那一格的环比与其后 12 个月
        #   的同比都是新口径比旧口径（汇总表 2026-07 同比印 +20.3%、同口径 +14.5%；2026-08 印 +14.6%、
        #   官方 +8.2%），水平上 2026-07 凭空一个约 5% 的台阶，且 2022-01 起的历史都少算了雅典。
    },
    {
        'id': '2026-07 版次月更正：2026-06 挂牌基金只数 −5、CSD 结算指令 +18 笔（全在雅典）',
        'columns': ('listed_funds', 'csd_settlement_instructions_m',
                    'athex_csd_settlement_instructions_m'),
        'months': ('2026-06', '2026-06'),
        'cells': 3,
        'sha256': 'b19d8327c29179e8221adbf649e76597508f2fe27b9d2a8cb948cf4be9b5b1b4',
        # 出处：hist 'Capital Markets'「Nb of Listed Instruments / Funds」与 'Securities Services'
        #   「Central Securities Depositary / Nb of Settlement instructions」的 Total、Athens 备注列。
        #   库内旧值来自 6 月数据版（2026-08-07 建表）；7 月数据版 hist（220,465 B，sha256 5f2fd7b0e696…）
        #   起就是新值，8 月数据版（sha256 2b47522c3c5d…）沿用。
        #
        # 冲突的形状：listed_funds 2178 → 2173；结算指令 Total 13,801,173 → 13,801,191（+18 笔），
        #   雅典备注 570,856 → 570,874（同样 +18）⇒ legacy（Total − 雅典）一笔没动，更正全在雅典那一块。
        # 定性：次月更正 —— 官方在下一期发布里改上一期的数。
        #
        # 为什么采纳（官方旁证，均不经 hist）：
        #   ① 7 月数据版 latest 工作簿（47,476 B，sha256 1143b9710d68…）「上月」列 2026-06：
        #      Funds = 2173、Nb of Settlement instructions = 13,801,191，与新值逐位相等；
        #   ② 旧值当年是忠实的：Q2 2026 业绩稿（2026-07-30）印 Nb of listed Funds 2,178、Q2 结算指令
        #      38,060,160（= 4、5 月 + 6 月旧值，docs/verify/enx.md 第 2 组）⇒ 官方是 07-30 之后才改的；
        #   ③ 雅典那 18 笔：Euronext Securities 的 key figures 工作簿（https://www.euronext.com/en/media/11654/download，
        #      不含雅典；2026-09-12 取的副本 sha256 ed046905f2d0…）2026-06 奥斯陆 1,921,495 + 哥本哈根 3,746,524
        #      + 波尔图 174,780 + 米兰 7,387,518 = 13,230,317 = 旧 Total − 旧雅典 = 新 Total − 新雅典
        #      ⇒ 四家一笔没动，+18 全在雅典（5 / 7 / 8 月同样逐位相等）。
        #   同类更正还在路上：8 月数据版 latest「上月」列印 2026-07 结算指令 13,287,660，hist 仍是
        #   13,287,622（+38）。hist 跟上那一版会冒出 2026-07 的冲突，不在本条月份区间内，走默认路径等人核。
    },
    {
        'id': '2026-07/08 版次月更正：新上市募资额补记超额配售（2026-06 +€15.11m、2026-07 +€4.43m）',
        'columns': ('money_raised_new_listings_eurm',),
        'months': ('2026-06', '2026-07'),
        'cells': 2,
        'sha256': '83d7d4964ff211132ede2ad3ce32446ab88c41003bdd6d4522059442f29c211d',
        # 出处：hist 'Capital Markets'「Money Raised (mln of €) / Equities - New Listings」，8 月数据版
        #   （sha256 2b47522c3c5d…）。库内旧值：2026-06 来自 6 月数据版、2026-07 来自 7 月数据版
        #   （2026-08-08 入库）。7 月数据版 hist 里 2026-06 还是旧值 —— latest 工作簿先改，hist 晚一期才跟上。
        #
        # 冲突的形状：2026-06 177.9021795393444 → 193.0097577893444（+15.10757825 €m，+8.49%）；
        #   2026-07 303.791169610157 → 308.22587511015706（+4.4347055 €m，+1.46%）。雅典备注（6 月 0、7 月 57.5）不动。
        # 定性：次月更正。本列含超额配售（官方行头 "incl over allotment"），绿鞋在上市后约 30 天内行使，
        #   官方在下一期发布里把它记回**上市那个月**。逐笔对得上（发行人行权公告，2026-09-12 检索代理读原文、
        #   本机复算乘积与合计）：
        #   · 6 月 = Bohus ASA（Oslo Børs，06-18 上市，07-05 公告全额行使 4,200,000 股 × NOK 31 = NOK 130.2m，
        #     按 0.09005 €/NOK 折 €11,724,510.00）+ Alia Mentis（Euronext Growth Milan，06-29 上市，07-09 公告
        #     979,021 股 × €3.25 = €3,181,818.25）+ OPT（Euronext Growth Milan，06-26 上市，07-24 公告 287,500 股
        #     × €0.70 = €201,250.00）= €15,107,578.25，与 +15.10757825 €m 逐分相等。0.09005 是 ECB 06-18 参考价
        #     1/11.1050 取 5 位 —— 汇率是反推出来的，另两笔是股数 × 价格直接乘；
        #   · 7 月 = Gens Aurea（Euronext Milan，07-14 上市，08-13 公告部分行使 276,818 股 × €10）+ Giunti
        #     Psychometrics（08-19，310,339 股 × €4.50）+ First Point（08-25，120,000 股 × €1.00）+ Dipietro Group
        #     （08-31，100,000 股 × €1.50）= €4,434,705.50，与 +4.4347055 €m 逐分相等；去掉 Gens Aurea 余
        #     €1,666,525.50，恰是 latest「SMEs」那一块 2026-07 的变动（202.791169610157 → 204.457695110157）。
        #
        # 为什么采纳（官方旁证，均不经 hist）：
        #   ① 7 月数据版 latest 工作簿（sha256 1143b9710d68…）「上月」列 2026-06 = 193.0097577893444，
        #      其 YTD 2026 = 4914.110985244195 = 库内 1–7 月加总 + 15.10757825；
        #   ② 8 月数据版 latest 工作簿（50,374 B，sha256 54bd1ee92daa…）「上月」列 2026-07 = 308.22587511015706，
        #      Q3 2026 与 YTD 2026 都等于新值加总（逐位）；
        #   ③ 旧值当年是忠实的：7 月数据版 latest「最新月」列 2026-07 = 303.791169610157 就是首发值；
        #      Q2 2026 业绩稿印 Q2 新上市募资 178（docs/verify/enx.md 第 2 组）= 6 月旧值。
        #   ⚠ 这是**每月都会发生**的结构性更正：只要最新月有带绿鞋的 IPO，下一版 hist 就会改它 ——
        #     库里最新月永远是首发值。本条只采纳人核过的这两格，以后的月份照默认路径进冲突文件等人核。
    },
    {
        'id': '2026-07 版次月更正：雅典 2026-06 再融资募资额 533 → 532.79（Interwood 配股按实募改记）',
        'columns': ('athex_money_raised_followon_eurm',),
        'months': ('2026-06', '2026-06'),
        'cells': 1,
        'sha256': '524d38bb5f01ed32652592fee78fb158e6c0e6b7129b80d17c52d24e2405d6d9',
        # 出处：hist 'Capital Markets'「Money Raised (mln of €) / Equities - Follow-ons」右侧的 Athex 备注列。
        #   库内旧值 533 来自 6 月数据版；7 月数据版 hist（sha256 5f2fd7b0e696…）起是 532.79，8 月数据版沿用。
        #   主列（集团合计）2026-06 = 1434.4866826325715，hist 两版都没动。
        #
        # 冲突的形状：533 → 532.79（−0.21 €m，−0.04%）。
        # 定性：次月更正（雅典那一块）。当月雅典再融资是两笔（发行人公告，2026-09-12 检索代理读原文、本机复算）：
        #   ADMIE Holding 增发 130,864,197 股 × €4.05 = €529,999,997.85（06-19 定价公告、06-23 获准上市）；
        #   Interwood 配股（06-26 除权，07-01..07-14 认购）现金部分上限 12,000,000 股 × €0.25 = €3,000,000，
        #   07-16 公告实募 €2,792,835.50。ADMIE + 上限 = €532,999,997.85 → 旧值 533；ADMIE + 实募 = €532,792,833.35
        #   → 新值 532.79 ⇒ 官方先按上限记，认购结果出来后按实募改。
        #
        # 为什么采纳（官方旁证，不经 hist）：
        #   ① 8 月数据版 latest 工作簿（sha256 54bd1ee92daa…）「Money Raised - Follow-ons on equities」YTD 2026
        #      = 20114.055633982607，比 7 月数据版 latest 的 YTD（19503.328424208412）+ 8 月（610.937207624192）
        #      少 0.209997849997 €m，而 Q3（7+8 月）与库内逐位相等 ⇒ 1–6 月里恰有一格被改小 0.20999785 €m，
        #      正是 532.99999785（ADMIE 精确值 + Interwood 上限）→ 532.79；
        #   ② 旧值当年也是忠实的：533 与 ADMIE + Interwood 上限对得上，不是我们抓错。
        #   latest 与 hist 同出一套数据，所以录入层面的疑点靠发行人公告那两笔排除（见上）。
        # ⚠ 集团合计还没跟上：hist 主列 2026-06 仍含旧的 532.99999785，latest 已按新值算 ⇒ hist 跟上那一版会冒出
        #   money_raised_followon_eurm 2026-06 −0.20999785 的冲突（不在本条列集合里，走默认路径等人核）。
        #   在那之前本库 2026-06 的「主列 − 雅典备注」比 legacy 多 0.21 €m（0.02%）。
    },
    {
        'id': '2026-08 版市值去重：2025-11..2026-03 剔除布鲁塞尔、雅典双重挂牌的 Titan / Viohalco / Cenergy',
        'columns': ('mktcap_eurtn',),
        'months': ('2025-11', '2026-03'),
        'cells': 5,
        'sha256': '296ae300e175db6a1ffcecdb55fb6fe9df5580fc4fc57d3ac62472194b715de9',
        # 出处：hist 'Capital Markets'「Market cap. (trillion of €) / Total end of month」，8 月数据版
        #   （sha256 2b47522c3c5d…）；6、7 月数据版都还是旧值（库内旧值来自 6 月数据版建表）。Athex 备注列一格没动。
        #
        # 冲突的形状（€m）：2025-11 −9,310.2、2025-12 −10,429.1、2026-01 −11,911.4、2026-02 −12,525.4、2026-03 −52.0
        #   （−0.136% / −0.152% / −0.169% / −0.171% / −7.7e-6）。
        # 定性：雅典并表带进来的重复计数，官方补做了去重。拿 Euronext 自己的 Cash 月报工作簿复算
        #   （live.euronext.com/sites/default/files/statistics/cash/monthly/Cash%20YYYYMM.xlsx，不含雅典；
        #   'PM - Overview' 的 Euronext 市值合计 + 'SM - Instrument level MTD' 的逐只市值；2026-09-12 取 2025-11..2026-08
        #   共 10 个月度版本，Cash 202608 那版 Last-Modified Wed, 09 Sep 2026 08:15:05 GMT，sha256 fe7d0bda230e…）：
        #   · 新值 = Cash 合计 + 雅典备注 − 布鲁塞尔主挂牌、同时在雅典挂牌的三家（Titan S.A.、Viohalco、Cenergy，
        #     取 Cash 表 XBRU 行）的市值，五个月逐月差 < €0.05m（Cash 表精确到 €1k）。三家合计（€m）：
        #     9,310.2 / 10,429.1 / 11,911.4 / 13,047.6 / 10,852.4；
        #   · 旧值 2025-11 / 12 / 2026-01 = Cash 合计 + 雅典备注，同样 < €0.05m ⇒ 三家算了两次；旧值 2026-02 比这个和
        #     少 €522.2m、2026-03 比新值多 €52.0m —— 旧版这两个月已是半截去重，原因不明，不影响新值；
        #   · Euronext N.V. 自己不在雅典挂牌（换股对价股只在阿姆斯特丹 / 布鲁塞尔 / 里斯本 / 巴黎上市），
        #     而且它的市值走势与差额对不上 —— 不是它。
        #
        # 为什么采纳（官方旁证，均不经 hist）：
        #   ① Cash 月报 'Methodology' sheet 原文 "For all euronext statistics the multi-listed instruments are computed
        #      once" —— 去重是官方写明的方法，新值合方法、旧值不合；
        #   ② 同一套复算，hist 的 2026-05 / 06 / 08 首发时就已去重（残差 +42.7 / −30.4 / −119.9 €m）⇒ 去重是官方
        #      现行口径，这一版是把并表头几个月补齐；
        #   ③ 这五个月的 Cash 合计在各月度版本里逐位不变 —— 改的是 hist 的加总方式，不是底层市值。
        #   不采纳的后果：并表头四个月多算 €93–125 亿（+0.14% ~ +0.17%），与 2026-05 起的去重口径拼在一起。
        #
        # ⚠ 没采纳 2026-04（+€2.9m）：Cash 合计 + 雅典备注逐位等于**旧值**，新值多出的 €2.9m 找不到出处；而且新旧两版
        #   2026-04 都还没去重（比去重口径多 €12,434.3m）—— 官方多半还会再改这一格，留在默认路径等人核。
        # ⚠ 读法后果：去重只动主列、没动雅典备注列（三家仍计在雅典的数里），所以去重过的月份「主列 − 雅典备注」
        #   比 legacy 少这三家 —— build/specs/enx.py 页尾注有一条专门说；增删这条登记时同步改那条。
    },
]

# ── 人核过、决定**不采纳**的冲突（照旧每轮写进 cache/enx_restatements.csv；官方以后再动，重新核）──────────
#   · adv_bonds_retail_cleared_kcontracts 2026-06：首发 827,199 张（×22 天）→ 7 月数据版起 987,654 张（+19.4%）。
#     latest 工作簿的「上月」列与两版 YTD 都是新值，但它们与 hist 出自同一套数据，只能证明「官方现在是这个数」。
#     987,654 是整本 hist 工作簿里唯一一格连续递减的整数（疑为占位数）；不走这套数据的官方出处只有 Q2 2026
#     业绩稿，印的 Q2 2,950,200 = 旧值；两条间接估算（Euronext Clearing CPMI-IOSCO Q2 披露的日均 × 天数、
#     Cash 月报米兰债券成交笔数 × 历史上约 2 倍的清算/成交比）落在约 88–96 万张，新旧都不像。拿不准，不采纳 ——
#     库内保留首发值（页面没画这一列、pools 也不读它，没有页尾注要改）。
#   · mktcap_eurtn 2026-04：+€2.9m 无出处，见上面市值那条登记的注释。


def _accept_registered(restated):
    """把本轮冲突格分成 (照旧只记账的, 按 ACCEPTED_RESTATEMENTS 采纳的) 两份。

    restated 每一项是 (月, 列, 库内旧值, 官方新值) 四个字符串，与 cache/enx_restatements.csv
    的行同形。判据见 ACCEPTED_RESTATEMENTS 上方注释：整批对上才采纳，否则整批留在冲突里。
    """
    keep, accepted = list(restated), []
    for reg in ACCEPTED_RESTATEMENTS:
        lo, hi = reg['months']
        hit = sorted(r for r in keep if r[1] in reg['columns'] and lo <= r[0] <= hi)
        if not hit:
            continue
        digest = hashlib.sha256(
            '\n'.join(','.join(r) for r in hit).encode('utf-8')).hexdigest()
        scope = '%s × %s..%s' % ('/'.join(reg['columns']), lo, hi)
        if len(hit) != reg['cells'] or digest != reg['sha256']:
            print('[enx] ⚠ 本轮 %d 格落在采纳登记「%s」的范围内（%s），但与登记（%d 格、'
                  '指纹 %s…）对不上（本轮指纹 %s…）—— 整批不采纳，照旧只写冲突文件。'
                  '官方又动了这些格子，或者这回是解析出错：人核过之后另起一条登记'
                  % (len(hit), reg['id'], scope, reg['cells'], reg['sha256'][:12],
                     digest[:12]))
            continue
        got = set(hit)
        keep = [r for r in keep if r not in got]
        accepted.extend(hit)
        print('[enx] 采纳登记「%s」：%d 格（%s）逐格指纹与登记一致，库内旧值改写为本轮官方值'
              % (reg['id'], len(hit), scope))
    return keep, accepted


def latest_month(cache_dir):
    """官方源当前最新月 'YYYY-MM'。

    以「现货 ADNV 非空的最后一个月」为准，不信文件里的最后一行 ——
    官方有时会把下个月的行先开出来只填交易日（HKEX 踩过的同类坑）。
    抓不到 / 解析不出来一律抛 EnxFetchError，不返回 None 掩盖故障。
    """
    _check_landing(cache_dir)
    path, _lm = _download(cache_dir, HIST_NAME)
    return _validate(parse_workbook(path))


def _fmt(v):
    """写回 CSV。整数写整数（交易日、家数、上市只数本来就是整数），其余用最短往返表示。

    不无脑 repr(float)：那会把 1844 写成 '1844.0'，与 cme.csv / hkex.csv 的风格不一致，
    也让人拿 CSV 与官方原表逐位对照时多一层心智负担。
    """
    if v is None:
        return ''
    f = float(v)
    return str(int(f)) if f.is_integer() and abs(f) < 1e15 else repr(f)


def _same_number(old, new):
    """库内字符串与本轮 _fmt 出来的字符串是不是同一个数（只差浮点表示）。解析不成数一律 False。

    只在「两个字符串不相等」之后用来判冲突，**不改写已有值** —— 已入库的字符串照旧原样搬运，
    重跑字节级幂等不受影响。容差 max(1e-9, 1e-12*|old|)，与 fetch/lseg.py 合流比对是同一个式子。

    为什么要有：官方工作簿里某一格有时只在 ULP 级别变了（多半是 Excel 重算换了求和顺序），
    _fmt 的最短往返表示随之变一两位，数值本身没变。2026-09-12 对 8 月版 hist（sha256 2b47522c…）
    实测 mktcap_eurtn 两格：2026-06 `7.39423611742153` → `7.3942361174215305`（1 个 ULP，相对 1.2e-16）、
    2026-07 `7.4328688714973` → `7.4328688714972975`（3 个 ULP，相对 3.6e-16）。不滤掉，它们就与
    真更正混在 cache/enx_restatements.csv 里，而那份文件是往 ACCEPTED_RESTATEMENTS 登记的底稿。
    同一版里最小的真更正是 mktcap_eurtn 2026-04 的 +2.9e-6（€2.9m），比容差大三个数量级以上。
    1e-9 这个绝对下限折成各列最小的钱：市值（万亿欧元）€1,000、托管资产（十亿欧元）€1、
    FX（十亿美元/日）约 $20/月 —— 都远在页面显示精度之下；错行、口径变更动辄百分之几，碰不到它。
    NaN / inf：比较恒为 False，照旧记冲突，不静默放过。
    """
    try:
        a, b = float(old), float(new)
    except ValueError:
        return False
    return abs(a - b) <= max(1e-9, 1e-12 * abs(a))


def update(series_dir, cache_dir):
    """把新月份写进 series/enx.csv，返回新增月份列表（升序）。

    幂等保证：
      · 已存在的月份不重复追加；
      · 已经有值的单元格**永不覆盖** —— 官方明确会回溯重述（口径坑 4，实测
        2019-01 现货 +6.4%、2020-06 现货 −4.1%），重述不由无人值守任务自动吞进来；
        官方与本仓不一致的格子写进 cache/enx_restatements.csv 供人工判断（每轮整份重写）；
        唯一例外是 ACCEPTED_RESTATEMENTS 里人核过、逐格钉死指纹的那几批 —— 整批对上才覆盖；
        覆盖只改值不加行，所以不进返回值（monthly_run 靠 series 指纹变化照样重建页面）；
      · 字符串不同、数值只差浮点表示的格子（_same_number，容差同 fetch/lseg.py）不算冲突，
        也不改写 —— 库内字符串照旧不动；
      · 只在既有行**原本为空**的格子上回补（正常情况下不会有：Euronext 一次给全所有列）；
      · 什么都没变时未被触碰的单元格是原样字符串搬运 ⇒ 文件字节级不变，重跑返回 []。

    首次调用时 series/enx.csv 不存在 —— 本模块会按 COLUMNS 建表并一次写满全历史
    （2012-01 起，工作簿有多少月就写多少月）。这不是「顺手做掉」：Euronext 的单一 xlsx 本来就带全序列，
    分两步（先手工 bootstrap 再增量）反而会留下「bootstrap 脚本与 fetch 解析器两套代码」
    的经典漂移，README 讲的 cost/ibkr 搬迁就是在治这个病。
    """
    csv_path = os.path.join(series_dir, 'enx.csv')
    if os.path.exists(csv_path):
        with open(csv_path, newline='', encoding='utf-8') as f:
            rows = list(csv.reader(f))
        header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
        if header != ['month'] + COLUMNS:
            raise EnxFetchError(
                'series/enx.csv 的列名与本模块不符；缺 %s，多 %s'
                % ([c for c in COLUMNS if c not in header],
                   [c for c in header[1:] if c not in COLUMNS]))
    else:
        header, body = ['month'] + COLUMNS, []
    idx = {name: i for i, name in enumerate(header)}

    _check_landing(cache_dir)
    path, last_modified = _download(cache_dir, HIST_NAME)
    sheets = open_sheets(path)
    data = parse_workbook(path, sheets)
    newest = _validate(data)

    # ── 哨兵：已入库的月份在官方文件里消失就抛（fetch/msci.py update() 哨兵② 同款）──
    # 这条查的是上面那道 latest 对表的**反侧**。对表从「官方另一份文件说到几月」那一侧
    # 查，够不着这种坏法：hist 文件照常更新、结构也没变，只是现货 ADNV 那一列的写法
    # 变了一点，最新那个月被 _cell_num 读成 None，于是 _validate 把 newest 往回退一个
    # 月 —— 而 latest 文件此时多半也还没更新，对表看到的是「两边同步」，一切正常。
    # 官方从不删已经发过的月份（口径坑 4 记的是**改数值**：cache/enx_restatements.csv
    # 至今全是值级冲突，没有一条是整月消失），所以「入库过的月份现在解析不出来了」
    # 只可能是我们这边读丢了。写成 max 对 max：官方真要缩短历史起点，那是老月份的事，
    # 不该由这条来管。
    stored_newest = max((r[0] for r in body), default='')
    if stored_newest and newest < stored_newest:
        raise EnxFetchError(
            'series/enx.csv 里已经有到 %s，官方 %s 这一轮却只解析出到 %s —— '
            '官方不删已发过的月份（重述只改数值，见口径坑 4），所以多半是 %s 那一列的'
            '写法变了、最新月被读成空值，_validate 于是往回退了一个月。'
            '拒绝写入，请对照 cache/%s 人工确认'
            % (stored_newest, HIST_NAME, newest, ANCHOR, HIST_NAME))

    print('[enx] %s' % _crosscheck_latest_month(data, newest, cache_dir))
    _guard_latest_stall(cache_dir, newest)

    # 断点台账每次都重算：它是从官方脚注原文抽的，官方一改脚注这里就跟着变。
    # 与 enx.csv 的落盘分开、且先写 —— 断点表是「怎么读这些数」的说明书，
    # 说明书比数据更不该滞后。
    if _write_breaks(series_dir, breaks(sheets)):
        print('[enx] series/%s 已更新（口径断点来自官方脚注原文）' % BREAKS_NAME)

    have = {r[0]: r for r in body}
    added, filled, restated, reprs = [], [], [], []
    for mon in sorted(data):
        rec = data[mon]
        if rec[ANCHOR] is None:
            # 官方把行开出来了但还没填数（或早于该 sheet 的起始月），不建行
            continue
        if mon in have:
            row = have[mon]
            for name in COLUMNS:
                if rec[name] is None:
                    continue
                new = _fmt(rec[name])
                if not row[idx[name]].strip():
                    row[idx[name]] = new
                    filled.append((mon, name, new))
                elif row[idx[name]] == new:
                    continue
                elif _same_number(row[idx[name]], new):
                    reprs.append((mon, name))      # 只差浮点表示：不改写、不记冲突
                else:
                    restated.append((mon, name, row[idx[name]], new))
            continue
        row = [''] * len(header)
        row[0] = mon
        for name in COLUMNS:
            row[idx[name]] = _fmt(rec[name])
        have[mon] = row
        body.append(row)
        added.append(mon)

    # 官方与本仓不一致的格子一律落盘、绝不自动覆盖 —— 是口径重述还是解析出错，
    # 只有人能判断（照 fetch/hkex.py 与 fetch/ice.py 的做法）。唯一的例外是
    # ACCEPTED_RESTATEMENTS 里人核过、逐格钉死的那几批，判据见那张表上面的注释。
    restated, accepted = _accept_registered(restated)
    for mon, name, _old, new in accepted:
        have[mon][idx[name]] = new
    # 冲突文件每轮整份重写，一格冲突都没有也写（只剩表头）：它是「这一轮官方与库内哪里
    # 不一致」的快照，也是往 ACCEPTED_RESTATEMENTS 登记时的底稿。旧写法只在有冲突时才写，
    # 冲突清空的那一轮会把上一轮的行原样留下，照着过期底稿算出来的指纹必然对不上。
    os.makedirs(cache_dir, exist_ok=True)
    rp = os.path.join(cache_dir, 'enx_restatements.csv')
    with open(rp, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['month', 'column', 'in_series_csv', 'in_official_xlsx'])
        w.writerows(restated)
    if restated:
        print('[enx] 官方源与 series 有 %d 处不一致，已写 %s（不在 ACCEPTED_RESTATEMENTS '
              '登记内，本模块不覆盖，请人工判断）' % (len(restated), rp))
    if reprs:
        print('[enx] 另有 %d 格与官方只差浮点表示（_same_number 容差内），不算冲突、库内值不动：%s'
              % (len(reprs), ', '.join('%s %s' % r for r in reprs[:6])))

    if not (added or filled or accepted):
        return []

    body.sort(key=lambda r: r[0])
    tmp = csv_path + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        w.writerows(body)
    os.replace(tmp, csv_path)          # 原子替换：中途挂掉不会留下半张表

    # 记发布日放在落盘之后：写盘失败就没有「这个月官方发过了」这条断言。
    if newest in added:
        _record_source_date(series_dir, cache_dir, newest)
    if filled:
        print('[enx] 补空 %d 格：%s' % (len(filled), filled[:12]))
    print('[enx] 源文件 %s（Last-Modified %s），最新月 %s'
          % (HIST_NAME, last_modified, newest))
    return sorted(added)


if __name__ == '__main__':
    import sys
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _series, _cache = os.path.join(_root, 'series'), os.path.join(_root, 'cache')
    if len(sys.argv) > 1 and sys.argv[1] == 'source-dates':
        print('source_dates 回补:', backfill_source_dates(_series, _cache))
    elif len(sys.argv) > 1 and sys.argv[1] == 'latest':
        print('latest:', latest_month(_cache))
    else:
        _added = update(_series, _cache)
        print('added : %d 个月 %s'
              % (len(_added), (_added[:3] + ['…'] + _added[-3:])
                 if len(_added) > 6 else _added))
