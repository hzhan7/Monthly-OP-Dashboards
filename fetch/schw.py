# -*- coding: utf-8 -*-
"""Charles Schwab (SCHW) —— 月度经营指标抓取模块。

================================ 数据源 ================================
官方只有一个真源：Schwab Monthly Activity Report 随附的 Excel 附表，走 Akamai CDN 直链，
文件名完全可推导，因此不需要爬列表页、不需要登录态、不需要浏览器：

    月报附表   https://content.schwab.com/web/retail/public/about-schwab/excels/
               schw_<mon><yyyy>_table.xlsx        例：schw_may2026_table.xlsx
    月报正文   https://content.schwab.com/web/retail/public/about-schwab/
               schw_<mon><yyyy>_press_release.pdf （数值不从这里取，只取电头日期，见下）
    季报附表   https://content.schwab.com/web/retail/public/about-schwab/excels/
               schw_q<n>_<yyyy>_earnings_tables.xlsx  例：schw_q2_2026_earnings_tables.xlsx
    季报正文   https://content.schwab.com/web/retail/public/about-schwab/
               schwab_q<n>_<yyyy>_earnings_release.pdf（同上，只取电头日期）

<mon> 是小写三字母英文月份缩写（jan…dec），<yyyy> 四位年。
注意两份 PDF 的**文件名前缀不一样**：月报是 schw_、季报是 schwab_（xlsx 两个都是 schw_）。
照着 xlsx 的写法推季报 PDF 的名字必 404，这不是笔误，是官方自己就不一致。

—— 为什么不用别的源 ——
· www.aboutschwab.com（IR 站正文页）在 Akamai 后面，会按 TLS/HTTP2 指纹拦截：
  python urllib 无论带什么 UA/Sec-Fetch 头都是 403，只有真浏览器栈（curl --http2 带全套
  浏览器头也行）能过。所以**不能**把落地页解析放进无人值守主路径。
  content.schwab.com 这个 CDN 域宽松得多：urllib + 普通 Chrome UA 即可 200。
· SEC EDGAR **是可选源**（2026-08-16 更正了两遍，把过程写下来，免得第三次又绕回去）。
  实测 CIK 0000316709 的季度 8-K：**每一期**的 EX-99.1 正文里都嵌着「The Charles Schwab
  Corporation Monthly Activity Report For <月> <年>」那张 13 个月滚动表 —— 2014 年的有，
  2026 年的也有。相邻两期锚点差 3 个月、窗口重叠 10 个月，可逐期接续。
    - 原始 docstring 写「想靠 EDGAR 拿月度数据是走不通的」→ **错**。
    - 第一次更正写「2017-04 起表就不随 8-K 附了，只剩一句脚注引用」→ **也错**，
      而且错得更隐蔽：那是**解析器**的毛病不是官方的改动。两代版式放标题的位置不同 ——
      2017-03 及更早，标题在表的第一行**里**；之后，标题在表**上方的 <div> 里**。
      而正文另有一句「…please see the Monthly Activity Report.」的脚注，位置比真表靠前。
      当时的解析器锚在「monthly activity report」这个词上再往回找 <table>，于是
      新版式必然捞到上面某张不相干的表，**静默**返回空 —— 97 份里只读出 15 份，
      看上去就像「2017-04 之后官方不附表了」。
      教训：解析器读不到，和源里没有，长得一模一样；分辨这两者只能去看原文。
    - 第二次更正（2026-09-16）写「2014 年那三份整份返回 {} 是因为 _TITLE_RE 不认
      "Monthly **Market** Activity Report"」→ **只说对了三分之一**。那三份（报送
      2014-01-16 / 2014-04-15 / 2014-07-16，报告月 2013-12 / 2014-03 / 2014-06，
      DFIN 排版）身上叠着**三个各自独立的病因**，每一个单独都足以让整份静默返回 {}：
        (1) 标题正则不认 "Monthly **Market** Activity Report"；
        (2) 这三份的 HTML 标签**全大写**（<TABLE> / <TR> / <TD>），而定表尾的
            `html.find('</table>')` 和抠行、抠格的两个 `re.findall` 都是大小写敏感的 ——
            同一个函数里定表**头**用的是 `html.lower()`，唯独这三处漏了大小写。
            季频腿那边（_q_rows 一带）早就带着 re.I，月频这边一直没有；
        (3) 那一版把**行标签单独占一行**，值落在下一行的单位说明格后面
            （'Total Client Assets' 自己一行，下一行才是
            '(at month end, in billions of dollars)' '1,951.6' …）。`row_of()` 取到
            标签行发现没有值就跳过，锚点行 _anchor_money 因此返回 None → 整份 {}。
      **最值得记的不是这三条本身，而是它们叠在一起的样子**：修好 (1) 之后，症状
      （整份返回 {}）**一个字都没变** —— 此时最顺手的结论正是「那就是源里真没有」，
      而那是错的。一个症状可以叠着好几个独立病因，症状不变 ≠ 修的地方不对。
      三层都修完，50 份 EX-99.1 全部解析出结果（此前 47 份），原先能解析的 47 份
      **逐字未变**；三份 DFIN 件彼此重叠 10 / 7 / 10 个月逐值相等，与 series/schw.csv
      既有 42 个 (月,列) 也逐值相等 —— 「读的是对的那张表」靠的是这个，不是肉眼看版式。
  现在的做法见 parse_edgar_monthly()：锚在**标题正则**上，再按标题落在表内还是表外
  决定往前还是往后找 <table>。实测 871 个与 series/schw.csv 重叠的 (月,指标) 全部相等，
  含 2019-04 那个 core NNA = -0.3（会计负号的右括号被拆进独立 <td>，见 _glue）。
  月度活动报告**本身**确实从不单独发 8-K，原文这半句没错。
  取 EDGAR 要在 User-Agent 里带联系方式，否则 403（见 _EDGAR_UA），这是它明文的使用条款。
· 新闻稿 PDF 里的数字和 xlsx 完全一致，但 PDF 要 OCR/文本抽取，没必要，xlsx 是结构化的。

================================ 发布节奏 ================================
· 非季末月：次月**第 10 个美股交易日**（NYSE 日历）发月报，附表当天上线。换成日历日：
  次月 1 号是周一 → 12 日、周日 → 13 日、周二至周六 → 14 日；**9 月例外**：劳动节（9 月第一个周一，
  必在 1-7 日）顺延成 15 日（1 号周一至周五）/ 16 日（周日）/ 17 日（周六，下一次是 2029 年）。
  其余有独立月报的发布月（2/3/5/6/8/11/12 月）前 14 天没有 NYSE 例行休市，不会超过 14 日；
  临时休市（国丧日一类，如 2018-12-05）会再顺延，不在这张推算里。退伍军人节 NYSE 照常开市、要计为
  交易日 —— 按联邦假日数会多推一个工作日（2025 年推到 11-17），而 oct2025 / oct2024 两期电头都是 11-14。
· 季末月（3/6/9/12）：**没有独立月报**，对应 URL 直接 404（已实测 mar2026 / jun2026 /
  dec2025 全 404）。季末月的数值有两条路可拿，本模块两条都走：
    (a) 当季**季报附表**的 "ER SMART" 页 —— 季报次月中下旬发（Q2-2026 是 7/21），最快；
    (b) 下一个月报附表的 13 个月滚动表 —— 例如 jul2026 月报的表里会带上 jun2026，
        但要等到 8 月中，比 (a) 慢一个月。
  所以「季末月漏掉」这个坑的正确解法不是特判某几个月，而是：**两个源都抓，取并集**。
· 实测发布日（月末后第几天）：月报 13 期 12 / 13 / 13 / 14 / 14 / 14 / 14 / 15 / 15 / 15 / 15 / 16 / 16，
  季报 4 期 16 / 16 / 21 / 21。月报 13 期电头逐期数过，**13/13 都是次月第 10 个美股交易日**：
    may2026→06-12  jan2026→02-13  nov2019→12-13  apr2026→05-14  jul2026→08-14  oct2025→11-14
    oct2024→11-14  aug2025→09-15  aug2023→09-15  aug2022→09-15  aug2020→09-15  aug2024→09-16
    aug2019→09-16
  2019/2020 年电头是 SAN FRANCISCO，其余 WESTLAKE。第 17 天那一档（9/1 周六）**没有样本**：
  aug2018 用 schw_ / schwab_ 两种前缀回源都是 404，那一档是按日历推的。
  样本来自 series/source_dates.csv、cache 里的新闻稿与 2026-09-14 回源取的历年电头，随时可复核。
· _LAG_DAYS 与 build/roster.py 的 LAG['schw'] 都是 (17, 21)（2026-09-14 由 (14, 21) 改来）：
  常规月取**规则上界** 17、不取实测最坏 16 —— 理由同 build/roster.py LAG['spgi'] 那条：17 有出处，
  按 n=13 的最大值定，等于当还没轮到的排列不存在。原先的 14 只是「9 月以外」的上界，9 月每年越线 1-3 天。
  季末月的 21 是季报 4 期实测最坏，**正好顶到**，所以任何拿 _LAG_DAYS 当红线的判断都必须另加余量，
  见 _crosscheck_due_month 与 _OVERDUE_MARGIN_DAYS。

========================== 官方发布日（source_dates）==========================
页面抬头「官方发布于 X」要的是**源头自己说出来的那一天**，所以只认新闻稿正文的电头：

    月报 PDF 第 1 页  "WESTLAKE, Texas, June 12, 2026 – The Charles Schwab Corporation
                      released its Monthly Activity Report today."   → 2026-05 发布于 6/12
    季报 PDF 第 1 页  "WESTLAKE, Texas, July 21, 2026 – The Charles Schwab Corporation
                      reported net income for the second quarter…"   → 2026-06 发布于 7/21
                      （季末月的数值来自季报，所以它的发布日就是季报的发布日）

**不能用 HTTP Last-Modified**：实测 q2_2026 那份 PDF 的 Last-Modified 是 7/20 17:11 GMT，
而电头写的是 7/21 —— 官方前一天晚上先把文件挂上 CDN、次日盘前才对外发布。
用 Last-Modified 会系统性地早一天，而早一天的日期看上去完全正常，没人会发现。
mtime、下载日、构建日同理，一律不用。

只有当某个月是从**它自己那期**报告里读到时才记发布日。同一个月也会出现在后续几期的
13 个月滚动表里，那些文件的电头是后来那期的日子，不是这个月首次公布的日子；
分不清就宁可让这半句话缺席（见仓库根 source_dates.py 的 docstring）。

================================ 口径坑 ================================
1. **单位在两种文件里不一样**，这是最容易静默算错的地方：
   · 月报附表：客户资产/融资余额已经是 $bn（13135.3），账户数/DATs 已经是千（461 / 11813）。
   · 季报附表：同样的行是**原始单位**（13135300000000 美元 / 490000 个账户 / 13615000 笔）。
   所以不能写死除数。本模块用「基准行反推倍率」：用 Total Client Assets 定金额倍率、用
   Active Brokerage Accounts 定计数倍率，再把倍率套到同一单位块里的其它行，并对结果做
   量级断言。硬编码 /1e9 迟早会在某次版式微调后炸掉。
2. **行标签会变**，不能按行号取数：
   · 2026-02 那期把 "Net Market Gains (Losses)" 写成 "Net Market (Losses) Gains"（词序颠倒）。
   · sheet 名月报是 'SMART'、2019 年的老文件是 'Smart'、季报是 'ER SMART'。
   所以一律按标签前缀 + 大小写无关匹配。
3. **四列是 2026-01 那期才新增的**：Client Daily Average Trades (DATs)、Margin Balances
   at month end、Transactional Sweep Cash (at month end)、Total Money Market Funds
   (at month end)。同一期把老的 "Average Margin Balances"（月均口径，单位 $mn）删掉了。
   series/schw_avg_margin.csv 就是那条已停更的老序列，它**永远停在 2025-12**，
   本模块绝不去追加它 —— 追加只会把两种口径（月均 vs 月末）混成一条假序列。
   新增的四列在 2026-01 期的 13 个月滚动表里回填到了 2025-01，所以 series 里这四列从
   2025-01 起才有值，这是**月报这条源**的边界，不是解析漏了 —— 但别一锅端成「Schwab
   2025-01 前不披露这四个量」：
   · dats_k 与 margin_balances_usdbn **已被季报附表证伪**：季度口径的同名量回得到
     2012Q4（本模块季频腿 series/schw_q.csv 现取 2016Q1 起，见文件下半部「季频腿」）。
     月频边界是真的，**量**的边界不是。
   · sweep_cash_usdbn 与 mmf_usdbn 在季报的 `Growth in Client Assets and Accounts`
     表里**查无此行**，对它们说「2025-01 是披露边界」目前仍然成立。
   另：`Margin Balances at month end` **只含 margin loans、不含 short credits**。
   月报脚注 (4) 是它与 `Transactional Sweep Cash (4,7)` **两行共用**的，两个半句各归各行，
   整条读给融资余额那行就会读出反的结论；short credits 由脚注 (7) 归给 sweep 那行。
   完整证据链（含 2026Q2 的逐项对账）写在季频腿「坑 2」，两条腿是同一个口径。
8. **平均生息资产（avg_interest_earning_assets_usdbn）有三个各自独立的坑。**
   这一列 2026-09-16 才补进来，而它在月报里**逐月印了至少十二年**（回得到 2013-09）——
   漏抓的原因全部在解析器这一侧，与官方披露无关。这是本文件记下的**第四**次同一种病
   （ab70cd7 → 47710ce → 963dc76 → 本次），前三次的病名都写在各自的 commit message 里。
   · **坑 a：老版式标签行没有数。** 2019 年及更早的 13 份附表（以及 EDGAR 上每一份
     EX-99.1）把 `Average Interest-Earning Assets (N)` 印成独占一行的分节标题，数值落在
     紧邻下一行，那一行第一列写的是 `(in millions of dollars)`（还见过带 1 个、2 个
     前导空格的写法）。而 `_row_values` 对「标签命中、本行无数」的处理是继续往下扫、
     最后返回 None，`parse_table` 又把 None 当「这期没这行」跳过 —— **整列静默缺席**。
     解法是 `_row_values(..., unit_row=True)`，判据是**下一行长什么样**（_UNIT_ROW_RE），
     不是「无脑往下顺一行」：这张表通篇是「标题行 + 明细行」的堆叠，无条件下顺会把
     隔壁指标的数当成本行的，而且图上完全看不出来。
   · **坑 b：单位有三档，而且在相邻两期之间来回跳。** 同一行在 cache 的 25 份 xlsx 里
     出现过 $mn（242584）、$bn（453）与**原始美元**（187933000000）三种量纲：
     schwab_q1_2017 是 $mn、schwab_q2_2017 是原始美元、schwab_q3_2017 又退回 $mn；
     schw_q2_2018 是 $mn、schw_q3_2018 是原始美元。按年份或按「月报 vs 季报」都推不出来。
   · **坑 c：它和客户资产不在同一个单位块，所以不能挂 _MONEY。** 块头逐字：2025-11 及
     更早是 `Selected Average Balances (in millions of dollars)`，2026-01 那期起改成
     `Selected Balances (in billions of dollars)`；而锚点行 Total Client Assets 一直坐在
     `Client Assets (in billions of dollars)` 里。套锚点倍率在 2026-01 之前整整错 1000 倍。
     解法是 `_SELF_SCALED` + `_SELF_CANDS`：拿**自己这一行**的值反推倍率，由 _SANE 的
     区间挑出唯一那一档。
   与季频腿的关系：series/fee_rates.csv 里 SCHW 的 avg_interest_earning_assets（USD_mn，
   2013-Q4 起，fetch/rates_schw.py 抓）是**同一个量的季频版**，两条腿由
   `_crosscheck_quarter_iea` 逐季对账（**日历日加权**，不是算术平均，理由写在那个函数上方）。

7. **「Schwab 不披露客户现金」是句流传过的假话，别再写进任何图注。** 月报的
   "Selected Balances" 块里逐月印着 Transactional Sweep Cash 与 Total Money Market
   Funds 两条月末 $bn（脚注 (7) 给了 sweep 的定义），而 "Client Activity" 块下面还有
   一行 **Client Cash as a Percentage of Client Assets**（脚注 (8)：Schwab One、若干
   现金等价物、银行存款、第三方银行存款账户与货基余额占客户总资产的比重）——
   后者自 2013-09 起每期都印（2015-04-15 报送及更早那一行**没有 Client 前缀**，
   见 _CASH_PCT_FROM）。三者互相咬得住：(sweep + MMF) / Total Client Assets
   逐月复现官方印的那个占比，2025-01…2026-08 共 20 个重叠月最大偏差 0.054pp
   （2025-12；就是 0.1pp 印刷精度）。
   （2026-08-19 首次写这条时是 19 个月 / 0.05pp，此后每月自然增加一个月，容差仍是 0.07。）
   本模块以前抓不到它们，只是因为 COLS 里没写这三行，不是公司没披露。
4. **core NNA ≠ NNA**。序列取的是 Core Net New Assets（剔除单笔巨额流入/流出 + 表外
   Schwab Bank Retail CD 流量）。2025 年起「巨额」的门槛从 $10bn 提到 $25bn，
   所以 2025 年前后的 core NNA 严格说不完全可比 —— 这是官方口径变更，不是数据错。
5. **「月报附表不重述历史」是句被证伪的话，2026-09-16 订正 —— 两条互不知情的支线
   各自独立证伪，证据不同、结论一致。** 原话是「apr2026 与 may2026 两期文件里 12 个
   重叠月份的数值逐个相同」—— 那个观察本身没错，错在从**两期、一列**的相同推出了
   「月报从不重述」这条全称命题，而且这条假话被下游 build/schw.py 抄成了图注与释义板里的
   口径依据（详见那边）。**拿两份文件相等就断定整条管道不重述，是这个坑本身。**

   反例甲（avg_interest_earning_assets_usdbn）：官方在 2025-12 改了平均生息资产的口径
   （月报脚注逐字：`Represents average total interest-earning assets on the Company's
   balance sheet. Beginning in December 2025, average balances of client margin loans
   and short credits related to certain client long/short strategies from which the
   Company earns a fixed net yield are excluded from average interest-earning assets.
   Prior period amounts have been adjusted accordingly.`），并**逐月改写了 2025-01…2025-11
   已经发布过的数**。实测（旧基 → 新基，$bn）：
     2025-01 431.5→431.4  02 424.8→424.6  03 425.2→424.9  04 430.9→430.4  05 419.6→418.7
     06 417.8→416.5  07 418.6→416.7  08 417.2→414.4  09 423.6→419.8  10 433.6→428.3
     11 436.3→429.1   —— 幅度逐月单调放大，最大 −7.2bn。
   **2024-12 及更早未被改动**（431,177 在 Q3-2025 与 Q4-2025 两份里逐字相同），所以
   拼出来的序列在 2024-12/2025-01 之间没有台阶；但这是这一次变更碰巧的性质，不是规律。

   反例乙（client_cash_pct）：2026-09-16 用 84 份出版物（51 份 8-K EX-99.1 + 33 份 CDN
   附表）逐月建过全量矩阵，这一列在 2022-12…2023-06 共 **7 个月**被官方明示重述过
   （brokered CD 剔除，脚注原文与逐格数字见第 8 条）；同一次普查里**其余 7 列跨 97 份
   来源逐月对照 0 处不符**。

   落地后果：`backfill_columns` 的源顺序从此**必须**把人工核对过的重述源排最前、其余按
   报告期从新到旧（见 _col_sources 的 docstring），并把跨报告期打架记进 COLRESTATEMENTS
   打印出来。正确的表述是**逐列**的：core_nna_usdbn 的 $10bn→$25bn 门槛变更官方确实没有
   回填，client_cash_pct 与平均生息资产这两次都是回填的 —— 三列三种行为，没有一句话能
   同时罩住。所以既不能写「不重述」，也不能写「重述了就一定能看见」：重述**罕见、且官方
   会在脚注里说**，但那条脚注官方 2024-10-15 起已撤（见第 8 条），今天拿一份近期文件回填
   的人看不到任何提示。
   另：季报附表口径上是「最终版」，万一和月报打架，本模块以季报为准（见 _SOURCE_RANK）——
   注意 _SOURCE_RANK 只在 _collect() 里生效，backfill_columns() 那条路**没有**引用它。
6. 2020-10 的 new_brokerage_accounts_k = 14718 是 TD Ameritrade 并表的一次性搬账，
   不是当月开户量。build_schw.py 已经单独处理，这里原样入库、不做清洗。
8. **client_cash_pct 的口径立场：取「官方现行口径」。**（2026-09-16 定；本条是这一列
   唯一的判据，改它之前先读完。）

   —— 规则 ——
   默认取**当期原值**（该月自己那期印的数）；官方**明示重述**过的月份，经人工逐格核对后
   采纳重述值，登记进 _RECAST（见那张表）。两句话都要，缺一句就会退回 2026-08-19 到
   2026-09-16 之间那个状态：同一列前半段当期原值、后半段重述值，图上看不出来。

   —— 唯一的一次重述 ——
   2023-08-14 发的 **Jul-2023 月报**第一次印新口径，行标签脚注从 (5) 变成 (5,6)，新增：

       (6) Beginning July 2023, client cash as a percentage of client assets excludes
           brokered CDs issued by Charles Schwab Bank. Prior periods have been recast
           to reflect this change.

   脚注措辞自相矛盾（既说 "Beginning July 2023" 又说 "Prior periods have been recast"），
   **以数字为准**：实测回改范围精确是 2022-12…2023-06 共 7 个月，幅度 −0.1 → −0.6pp
   （brokered CD 余额 2023 年爬坡，楔子随之放大）；同一份文件里 2022-07…2022-11 五个月
   两版**逐值相同**，分母 total_client_assets_usdbn 与其余 24 行也一格未动 —— 官方动的
   只有这一行的分子。**因此「先看脚注说它管哪一段」是错的做法，要去比数字。**
   这条脚注只在 4 份申报里出现过（2023-10-16 / 2024-01-17 / 2024-04-15 / 2024-07-16），
   **2024-10-15 起官方把它撤了**并入主定义脚注。今天拿一份近期文件回填的人看不到任何提示，
   这就是 2026-08-19 那次没人发现的原因 —— 别指望下次还能从脚注上看出来。

   —— 为什么不取纯「当期原值」（fetch/rates_schw.py 对季度 NIM 的做法）——
   纯原值的线在 2023-06（首印 11.0）→ 2023-07（10.2）之间有 −0.8pp 的台阶，其中约 0.5pp
   是纯口径（同口径下是 10.5 → 10.2）。那是一道**真**口径断点，按 build/CONTRACT.md §5.2
   必须在 wealth 页 Exhibit 13 上画 break_at 竖线。而采纳重述之后整条线单口径、无断点。
   NIM 那边选原值有它自己的理由（并进 fee_rates.csv 现有 12 行不让老行跳变，且那边的重述
   是 1bp 量级）；这边是 0.6pp 打在 11 上，不是一回事。**同一家公司两列两个立场是有意的，
   不是漏改** —— fetch/cost_sec.py 里 cost_seg_q（原值）与 cost_fy（最新值）也是这样分的。

   —— 为什么也不写成纯「最终重述版」——
   够不着。13 个月滚动窗 + 首份新口径出版物 Jul-2023（窗 2022-07…2023-07）意味着
   **2013-09…2022-06 共 106 个月从未落进任何新口径出版物的窗口**，它们不存在重述后的值。
   （本条原写「2014-06…2022-06 共 97 个月」，那是按当时这一列的起点算的；起点 2014-06 在
   2026-09-16 同日被另一条支线证明是**管道边界不是披露边界**、已回补到 2013-09
   （见 _CASH_PCT_FROM），够不着的月份因此多了 9 个。结论方向不变，数字跟着走。）
   所以「整列都是最终版」是句做不到的话。能做到的是「官方改过的都跟上」，而官方只改过
   那 7 个月 —— 边界上最近的 5 个月（2022-07…2022-11）已实测两版相同，再往前是外推。

   —— 与 _col_sources() 排序的关系（2026-09-16 合并两条支线时定）——
   代码里实际跑的是「_RECAST 绝对优先 + 其余报告期从新到旧」，措辞上与本条的「默认取当期
   原值」是两条规矩。今天**同解**：官方只重述过上面那 7 个月（已进 _RECAST），其余 7 列跨
   97 份来源逐月 0 处不符，也就没有「无脚注的跨版本差异」这种样本。真出现那种样本时两条
   规矩会分道扬镳（排序取新、本条取原值）：**以本条为准，按 COLRESTATEMENTS 的日志人工
   裁决。** 排序之所以不能改回升序，是平均生息资产那一列需要它（见第 5 条反例甲）。

   —— 采纳的代价（要一起知道）——
   拼接点从 2023-05|06 挪到 2022-11|2022-12，残差从 0.6pp 降到 ≤0.1pp（2022-11 未被重述，
   它自己那点 brokered CD 含量在 0.1pp 印刷精度下是 0）。**不是零，是小到看不见。**

============ series/schw_backfill.csv：出处已查明，不进图，只留历史留痕 ============
那个文件是一次做了一半、从未接上的回填：表头承诺 dats_k 与 margin_balances_usdbn 两列，
dats_k 整列是空的，实际只有 2018-12…2024-12 共 7 个年末的月末融资余额。
2026-08-05 评估过要不要把它接进 build/schw.py，**结论仍是不接**，但当时写的四条理由里
有两条在 2026-09-16 被推翻 —— 连同「不要删它」那几句一起订正如下，原话逐条留着：

(a) 原写「**来历不可复现**，只可能来自 10-K / 年报或某个外部源，连出处都指不出来」
    → **全错**。出处是季度业绩 8-K 的 EX-99.1、`Growth in Client Assets and Accounts`
    表、`Margin loans outstanding` 行（原表印成负数，入库取的是绝对值）——
    正是**本模块季频腿自己在抓的那批文件**（cache/schw_rates/，见下方「季频腿」）。
    与 series/schw_q.csv 的对应季末值 **7/7 逐值相等**：2018-12=19.3 / 2019-12=19.5 /
    2020-12=60.9 / 2021-12=87.4 / 2022-12=63.1 / 2023-12=62.6 / 2024-12=83.8。
    当年查的是 cache/schw_may2019_table.xlsx（**月报**附表）——「月报里没有这行」是真的，
    但那只说明它不来自月报，不说明它不来自本管道。这次推错的形态与本文件开头 EDGAR
    那段自嘲的**一模一样**：解析器/管道读不到，和源里没有，长得一模一样；分辨这两者
    只能去看原文，靠「能证明它不可能来自本管道」这种推理推不出来。算上 EDGAR 那两次，
    同一类错误本文件已经记了第三笔。
(b) 原写「**边际信息只有 2 个点**」→ **不再成立**。同一个源可取 42+ 个季末点
    （series/schw_q.csv 现有 2016Q1…2026Q2 共 42 季，源本身到 2012Q4）。要季末融资余额
    就走季频腿，这个 7 点文件在信息量上已经没有任何边际贡献。
(c) **这 2 个点落在 TD Ameritrade 并购的另一侧 —— 仍然完全准确，别改。** 并购 2020-10
    完成，19.5 → 60.9 是资产负债表搬账不是融资需求，和第 6 条的 14,718k 是同一类假象。
    这条现在有了新用处：它就是 build/schw.py 里季频 Exhibit 10/11 那条 TDA 断点线
    （BRK_Q_TDA = 2020Q4）的依据 —— 台阶是并表，不是杠杆周期，跨断点不可直读。
(d) **年末单点混不进月度轴 —— 对这份 7 点文件仍成立，但只管它。** 7 个点之间是 6 段
    12 个月的空档，直接塞进月度融资余额那张图（今天的 Exhibit 9）会造出 66 个空月，
    违反 CONTRACT §5.3
    （不可比的相邻期不得画成连续序列）。**本条不管季频序列**：schw_q.csv 逐季连号、
    画在自己的季度轴上（Exhibit 10/11），不受这条约束。

**下次做孤儿文件盘点的人：** 原写「不要删它 / 全仓独一份 / 管道抓不回来 / 删了就永久
丢失」→ **三句全错**。它现在是 series/schw_q.csv 的**真子集**（7 个值 7/7 命中），那 7 个
数一条命令就能从源重放成季末点（`python3 fetch/schw.py --quarterly-backfill`），删了不丢数。
保留它只有一个理由：**历史留痕** —— 让下次再想「这数管道抓不回来」的人先看见 (a)。
它当初给自己开的两个解封条件（在文件里写清每个数的出处 + 在 fetch 侧写出可复现的抓取
路径）**现在都已满足**，但解封之后该走的路是季频腿，不是把这 7 个点接进图。

========================== 历史回填（backfill）==========================
主流程 update() 只探最近 8 个月 / 3 个季度 —— 那是「每月往后走一格」该有的开销。
把**存量**历史一次性补齐是另一件事，走 `python3 fetch/schw.py --backfill`：
它扫 _HIST_XLSX 里那份写死的老附表清单（文件名有两处不成规律的历史变体：前缀
`schwab_`、扩展名大写 `.XLSX`，推不出来所以写死）+ 上面说的 EDGAR 那条路，
把 2013-09…2018-04 共 56 个月补进 series/schw.csv。

三条铁律：**已存在的月份一个字符都不改**；**重叠月必须逐值相等**（不等就整次失败，
要人去看是解析取错了还是官方重述了）；**回填后月份必须仍然逐月连号**（缺口会让
下游 assets.diff() 把两个月的变动记到一个月上）。首次跑通时 39 个重叠值 0 处不符，
第二次跑 166 个重叠值 0 处不符、新增 0 个月（幂等）。

回填**不改变各列自己的披露边界**：core_nna_usdbn 仍然从 2017-02 起（_CORE_NNA_FROM），
dats_k / margin_balances_usdbn 仍然从 2025-01 起。补出来的只是客户总资产与新开经纪账户。
（这说的是**月频**这条路径；这两个量的**季频**历史回得到 2016Q1 甚至更早，走的是另一条腿
series/schw_q.csv，不经过 --backfill，见下方「季频腿」。）

⚠️ **2026-09-16 起 `--backfill` 能多拿 9 个月，但故意还没去拿。** 解析器这次学会了
2013/2014 那代 DFIN 版式（三层病因见上面「第二次更正」），于是那三份件里的
total_client_assets_usdbn 与 new_brokerage_accounts_k 变得可读，窗口最左到 **2012-12**。
真跑一次 `--backfill`，series/schw.csv 会从现在的 2013-09 往前长出 **2012-12…2013-08
共 9 行**（与现起点连号、不留洞；三份件彼此重叠 10/7/10 个月逐值相等，与既有 42 个
(月,列) 也逐值相等，数据本身是干净的）。**没跑，是因为这不是数据问题而是版式问题**：
schw 页与 wealth 页多张图的左缘由各自序列的首个非空月决定，加 9 行就会再挪一次 ——
这类可见的版式变更属页面所有者的决定（页面所有者 2026-09-16 的裁定是「只修解析器、
不动数据」）。下次要动它的人：数已经验过了，你要问的是「这 9 个月该不该上图」，
不是「这 9 个月的数对不对」。

========================= 季频腿（series/schw_q.csv）=========================
本文件还维护**第二张 CSV**：series/schw_q.csv，键是**季**不是月，两列
q_dats_k（季报附表 Clients' Daily Average Trades 的 Total 行，千笔/日）与
q_margin_eop_usdbn（Growth in Client Assets and Accounts 表里 Margin loans
outstanding 行，$bn，季末）。源只有 SEC EDGAR 的季度业绩 8-K（item 2.02）EX-99.1，
与 fetch/rates_schw.py 读的是**同一批文件、同一份缓存**（cache/schw_rates/）。

入口是月频那三条的季频对应物：update_quarterly() / backfill_quarterly()（CLI
`--quarterly` / `--quarterly-backfill`，后者带 `--offline` 可只用本地缓存重放）。
口径、两种版式、`Margin loans outstanding` 那个行名的坑（**只含 margin loans、不含
short credits**；本文件 2026-09-15 那版把它写反过，订正链条写在季频腿「坑 2」）、
窗口 2016Q1 与源能到 2012Q4、2020Q4 TDA 并表那一段的**措辞红线**，
以及「季频止于上一个已报季度，比月频短一到两个月」，全写在文件下半部
「季频腿」那一节的开头，别在这里找。

================================ 落盘 ================================
所有下载文件只写 cache/（已 gitignore），文件名与官方一致，便于事后复核。
季频腿写 cache/schw_rates/（文件名带 accession 前缀，与 fetch/rates_schw.py 一致，
两条腿共用）；tools/prune_cache.py 把 cache/*_rates/ 列为 PROTECTED，不会清它。
"""
from __future__ import annotations

import csv
import datetime as _dt
import json
import os
import re
import time as _time
import urllib.error
import urllib.request
from html import unescape as _unescape

import openpyxl

# ── 常量 ────────────────────────────────────────────────────────────────
CDN = 'https://content.schwab.com/web/retail/public/about-schwab'
MONTHLY_URL = CDN + '/excels/schw_{mon}{year}_table.xlsx'
QUARTER_URL = CDN + '/excels/schw_q{q}_{year}_earnings_tables.xlsx'
# 新闻稿正文：只为取电头日期。前缀 schw_ / schwab_ 不一致是官方的，别按 xlsx 的写法改。
PR_MONTHLY_URL = CDN + '/schw_{mon}{year}_press_release.pdf'
PR_QUARTER_URL = CDN + '/schwab_q{q}_{year}_earnings_release.pdf'
IR_PAGE = 'https://www.aboutschwab.com/financial-reports'

# CDN 只看 UA，给个普通 Chrome UA 就放行；不带 UA 或带 Python-urllib 会 403。
_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

_MON = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
        'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
_MON_FULL = ['January', 'February', 'March', 'April', 'May', 'June',
             'July', 'August', 'September', 'October', 'November', 'December']

# 新闻稿电头。锚在 "WESTLAKE, Texas," 上而不是只找「月 日, 年」——正文里还有一大堆日期
# （"as of May 31, 2026"、脚注里的往期口径变更日），只匹配日期格式会抓到其中任意一个。
_DATELINE = re.compile(
    r'WESTLAKE,\s*Texas,\s*(' + '|'.join(_MON_FULL) + r')\s+(\d{1,2}),\s*(20\d{2})',
    re.IGNORECASE)

SERIES = 'schw.csv'
COLS = ['core_nna_usdbn', 'total_client_assets_usdbn',
        'new_brokerage_accounts_k', 'dats_k', 'margin_balances_usdbn',
        'client_cash_pct', 'sweep_cash_usdbn', 'mmf_usdbn',
        'avg_interest_earning_assets_usdbn']

# 标签前缀（小写、去空白后前缀匹配）。用前缀而不是全等，是因为官方在标签尾部挂脚注号，
# 脚注号每期都在变（"(1,2)" → "(1,2,3)"），全等匹配必挂。
# 一个列可以写**一串**前缀（元组）：官方给同一个 line item 改过名时，新旧写法都要认。
# 与 fetch/rates_schw.py 的 _DEPOSIT_LABELS 同一个写法，判定见 _pfx()。
_LABEL = {
    'core_nna_usdbn':           'core net new assets',
    'total_client_assets_usdbn': 'total client assets',
    'new_brokerage_accounts_k': 'new brokerage accounts',
    'dats_k':                   'client daily average trades',
    'margin_balances_usdbn':    'margin balances at month end',
    # 客户现金三行。前缀要写全 'total money market funds'：同一张表里还有一行
    # 'Money Market Funds'（净买卖流量，$mn），前缀写短了会取到那一行。
    # 占比那一行历史上有**三种写法**，互不为前缀，所以三个都得列上（判据见 _CASH_PCT_FROM）：
    #   'Cash as a Percentage of Client Assets'          2015-04-15 报送及更早
    #   'Client Cash as a Percentage of Client Assets'   2015-07-16 报送起，至今
    #   'Client Cash as Percentage of Client Assets'     少一个 "a"，只见于 2017-Q1 那一档
    #                                                    （2017-04 报送的 EX-99.1 与
    #                                                     schwab_q1_2017_earnings_tables.xlsx）
    'client_cash_pct':          ('client cash as a percentage of client assets',
                                 'client cash as percentage of client assets',
                                 'cash as a percentage of client assets'),
    'sweep_cash_usdbn':         'transactional sweep cash',
    'mmf_usdbn':                'total money market funds',
    # 平均生息资产。写法在 25 份 xlsx + 48 份 EX-99.1 上**只有这一种**（title-case、
    # 带连字符、尾部挂脚注号），所以不需要像 fetch/rates_schw.py 的 _DEPOSIT_LABELS
    # 那样并列多个前缀。无连字符的 'Average Interest Earning Assets' 与小写的
    # 'Average interest-earning assets' 只出现在**正文散文**里（前者 1 处：4Q20 的
    # 脚注；后者 2 处：1Q26/2Q26 的 bullet），从来不是行标签 —— 为散文兜底只会
    # 把前缀放宽到能命中别的东西。
    'avg_interest_earning_assets_usdbn': 'average interest-earning assets',
    # 下面两行只用来定单位倍率，不入库
    '_anchor_money':            'total client assets',
    '_anchor_count':            'active brokerage accounts',
}
# 金额类 / 计数类 / 比率类分组：决定用哪个锚点行的倍率
_MONEY = {'core_nna_usdbn', 'total_client_assets_usdbn', 'margin_balances_usdbn',
          'sweep_cash_usdbn', 'mmf_usdbn'}
_COUNT = {'new_brokerage_accounts_k', 'dats_k'}
# 比率类不跟锚点走 —— 它和金额/计数不在同一个单位块里：xlsx 里印的是**分数**
# （0.101），EDGAR 的 HTML 里印的是**百分点字符串**（'10.1%'）。两边都归一到百分点。
_RATIO = {'client_cash_pct'}
# 自锚类：也不跟锚点走，但候选倍率是金额那一套 —— 拿**自己这一行**的值反推。
# 为什么不能挂 _MONEY：锚点行 Total Client Assets 坐在 `Client Assets (in billions
# of dollars)` 那个块里，而平均生息资产坐在另一个块里，两个块的单位**长期不同**：
#   · 2025-11 及更早：`Selected Average Balances (in millions of dollars)`（老版式更早
#     是标签下面单挂一行 `(in millions of dollars)`）—— 与客户资产差 1000 倍；
#   · 2026-01 那期起：块头改成 `Selected Balances (in billions of dollars)`，才与客户资产同档。
# 套锚点倍率在 2026-01 之前会整整错 1000 倍，而且是**静默**错（量级断言若忘了配就直接落盘）。
# 三档候选是实测出来的，不是留余量：同一行在 25 份 xlsx 里出现过 $mn（242584）、
# $bn（453）与**原始美元**（187933000000）三种量纲，且在 2017Q1↔Q2、2018Q2↔Q3 这种
# **相邻两期**之间来回跳，按年份/按月报-季报都推不出来。1e-6（千）没有任何一份用过，
# 不列 —— 候选越少，_scale 那道「只有一档满足」的唯一性判据越硬。
_SELF_SCALED = {'avg_interest_earning_assets_usdbn'}
_SELF_CANDS = (1.0, 1e-3, 1e-9)

# 合理量级断言。core NNA 会是负数、也可能接近 0（2019-04 是 -0.3），无法用量级判，
# 所以它不做独立断言，只跟着锚点倍率走。
_SANE = {
    'total_client_assets_usdbn': (1_000.0, 100_000.0),    # $1tn – $100tn
    'margin_balances_usdbn':     (1.0, 5_000.0),          # $bn
    'sweep_cash_usdbn':          (1.0, 5_000.0),          # $bn
    'mmf_usdbn':                 (1.0, 5_000.0),          # $bn
    # 百分点。历史区间实测 8.6–13.0，给到 3–30 —— 这个下界同时兼任「分数还是百分点」
    # 的判据：0.086 这种分数落不进 3–30，倍率只有 100 那一档能过（见 _scale 的 cands）。
    'client_cash_pct':           (3.0, 30.0),
    # $bn。实测区间 135（2013-09）– 588（2021Q4 峰）。给到 50–2000 有两个作用：
    # 一是量级断言，二是**替 _SELF_CANDS 挑档**——三档候选套上去只有一档落得进这个区间
    # （453×1=453 ✓ / ×1e-3=0.45 ✗；242584×1e-3=242.6 ✓ / ×1=242584 ✗；
    # 187933000000×1e-9=187.9 ✓ / ×1e-3=1.88e8 ✗），所以区间放宽一个数量级都还是唯一解，
    # 但**不能**把下界压到 0.5 以下：那样 $mn 与 $bn 两档会同时满足，_scale 直接抛歧义。
    'avg_interest_earning_assets_usdbn': (50.0, 2_000.0),
    'new_brokerage_accounts_k':  (10.0, 100_000.0),       # 千（含 2020-10 那个 14718）
    'dats_k':                    (100.0, 1_000_000.0),    # 千笔/日
    '_anchor_count':             (5_000.0, 500_000.0),    # 千个活跃账户
}

# DATs / 月末融资余额 / 月末 Transactional Sweep Cash / 月末 Total Money Market Funds
# 这四列自 2026-01 期起披露，那一期的 13 个月滚动表回填到 2025-01。更早的月份本就没有。
# （客户现金**占比**那一行不在此列 —— 它自 2013-09 起每期都印，见 _CASH_PCT_FROM。）
_DATS_MARGIN_FROM = (2025, 1)
# **Core** Net New Assets 这一行是 2018 年初才出现在滚动表里的：实测最早带它的一份是
# schwab_feb2018_table.XLSX（表窗 2017-02…2018-02），而 2017 年的几份季报附表（q1/q2/q3
# 2017）与 2016 年及更早的全部来源里，同一位置只有未剔除的 "Net New Assets"。
# 两者不是一条序列（2017-06 官方同时给过 37.7 与 22.1），所以**不拼接**：
# 2017-02 之前 core_nna_usdbn 一律留空，由 build 侧按各自序列起点画图。
_CORE_NNA_FROM = (2017, 2)
# 客户现金**占比**这一行的官方起点：**2014-10-15 报送的 Sep-2014 月报**（8-K EX-99.1）
# 第一次印它，那张 13 个月滚动表最左是 2013-09（13.5%）。再往前的三期实测整张表确实
# 没有这一行 —— 2014-01-16 / 2014-04-15 / 2014-07-16 三份（DFIN 报送、标题是
# "Monthly **Market** Activity Report"）里 'percentage of client assets' / 'cash as a'
# 两个字符串命中数都是 0，整表 dump 也只有客户资产、新开账户、DATs 那几行。
#
# 2026-09-16 更正。同 ab70cd7 那条先例的同一类错误 —— 病名写在它自己的 commit message 里
# （「两处真回填，都是同一种病 —— 把工具的边界当成了世界的边界」），**不在 README**；
# 讽刺的是**这段错话就是那一条 commit 写下的**，同一次改动一边治病一边又犯了一遍。
# 原注释写「2015-07-16 那期第一次印它，最左是 2014-06；再往前三期整张表没有这一行 ——
# 连 "Client Cash as a Percentage" 这个字符串都搜不到」。**搜不到是因为搜的是新写法。**
# 这一行官方改过名（见 _LABEL）：2015-04-15 报送及更早印的是 "Cash as a Percentage of
# Client Assets"（**没有 Client 前缀**），2015-07-16 报送起才改成 "Client Cash as a
# Percentage of Client Assets"。老写法过不了原来那条单前缀，于是 2014-10-15 与
# 2015-01-16 两期的这一行被**静默丢掉**，看上去就像官方 2015-07 才开始披露。
# 实证（cache/schw_rates/，逐值核对）：
#   · 000031670914000029（2014-10-15，窗 2013-09…2014-09）"Cash as a Percentage of
#     Client Assets (3)" = 13.5 13.2 13.0 13.1 13.2 12.7 12.7 12.4 12.2 11.9 12.1 11.9 12.2
#   · 000031670915000005（2015-01-16，窗 2013-12…2014-12）同一写法，重叠 10 个月逐值相等
#   · 000031670915000018（2015-04-15，窗 2014-03…2015-03）仍是老写法，重叠 10 个月逐值相等
#   · 000031670915000036（2015-07-16，窗 2014-06…2015-06）起换成新写法，重叠月同样逐值相等
# 改名**卡死在 2015-04-15 与 2015-07-16 两期之间**（相邻两期，中间再无别的申报）。
# 2026-09-16 补记：上一版写「只界定得到 2015-01-16…2015-07-16 这个区间，因为夹在中间的
# 2015-04-15 那期本地 cache 里没有」—— 那句话在当时**属实**，但「本地没有」不等于
# 「拿不到」：它在 EDGAR 上一直都在（0000316709-15-000018），一条 `_edgar_get` 就取回来了，
# 现在已落进 cache/schw_rates/。教训与本文件反复记的那条同源、只是换了一层皮：
# **「我这儿没有」和「它不存在」也长得一模一样**；上一版已经躲过了「把没查写成实测」，
# 却停在「本地没有所以钉不到」，而那一步本来还可以再往前走一格。
# 两种写法是同一条序列：脚注定义同义（Schwab One®/现金等价物/银行存款/货基余额 ÷ 客户总资产），
# 跨期重叠月无一处打架，切换前后相邻月平滑（2015-06 = 11.7%）。所以**拼接**，不像
# _CORE_NNA_FROM 那样分家。
#
# 边界取 2013-09 的两重含义，别再混为一谈：
#   · 官方侧 —— 这一行被印出来的最早月份就是 2013-09（首次刊印那期滚动表的最左列）；
#   · 序列侧 —— series/schw.csv 本来就从 2013-09 起，再往前也无处可写。
# 天花板已经查到 2006-06，不再是「没查过」：2026-09-16 顺着 `_edgar_8k()` 的 156 份清单
# 把 2015-09 之前能解析的历次 EX-99.1 全取了回来，其中**没有这一行的共 12 份**
# （报告月 Jun-2007 / Jun-2008 / Jun-2009 / Sep-2009 / Jun-2012 / Dec-2012 / Mar-2013 /
# Jun-2013 / Sep-2013 / Dec-2013 / Mar-2014 / Jun-2014），剥标签归一空白后
# 'percentage of client assets' 命中数**逐份都是 0**，而同样这 12 份都能被
# parse_edgar_monthly 正常解析出 13 个月 × 2 列 —— 即「读得进来，读出来的里面没有」。
# 12 份的窗口并起来覆盖 **77 个月**，但**不是一整条**，两段中间有个洞，照实记下来：
#     2006-06 … 2009-09（40 个月）
#     〔空档 2009-10 … 2011-05，20 个月 —— 这一段没有任何一份被取回来〕
#     2011-06 … 2014-06（37 个月）
# 所以能说的是：**2014-10-15 那期是首次刊印**（它之前每一份读得到的申报都没有这一行），
# 而不是「2006-06 以来每个月都验过」。那 20 个月的空档与 2006-06 之前都仍未查 ——
# 真要往前推还是老规矩：去看原件有没有这一行，**不要**照着这个常数反推「官方那时没披露」。
#
# 2026-09-16 追记：天花板那几期当初是**整份解析不出来**的，「没有这一行」只能靠手工搜
# 字符串得到。现在 parse_edgar_monthly() 认得这一代版式了（三层病因见模块 docstring），
# 12 份全都能解析出 13 个月 × 2 列（total_client_assets_usdbn 与 new_brokerage_accounts_k），
# 而解析结果里**确实没有** client_cash_pct —— 于是这条天花板反证从「手工搜不到」升级成
# 「管道读得进来、读出来的东西里就是没有这一行」，两条互相独立的证据而不是一条。
_CASH_PCT_FROM = (2013, 9)
# 平均生息资产这一行的月频起点。**这不是披露边界，是本仓能回溯到的边界**，两者的区别
# 正是这一列被漏抓七年的教训（同 ab70cd7 / 47710ce / 963dc76 那三次先例）：它在**每一期**
# 月报与每一份业绩 8-K 的 EX-99.1 里都印着，回得到 2013-09 是因为 EDGAR 上最早那份
# （2014-10-15 报送的 Sep-2014 月报）的 13 个月滚动表最左就是 2013-09 —— 再往前的申报
# 本仓没有取，**不是查过没有**。哪天有人把 EDGAR 窗口往左挪，这个常数就该跟着往左挪。
_AVG_IEA_FROM = (2013, 9)

# 同一个月同时来自月报和季报时谁说了算：季报是最终版。
_SOURCE_RANK = {'monthly': 0, 'quarterly': 1}


class FetchError(RuntimeError):
    """抓不到 / 解析不出 / 缺列，一律抛这个，绝不静默降级。"""


# ── HTTP ───────────────────────────────────────────────────────────────
def _get(url: str, timeout: int = 60) -> bytes | None:
    """404 返回 None（季末月月报本来就不存在，属正常）；其它错误抛异常。"""
    req = urllib.request.Request(url, headers={'User-Agent': _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise FetchError(f'HTTP {e.code} on {url}') from e
    except Exception as e:                      # 网络层问题必须炸出来，不能当没数据
        raise FetchError(f'{type(e).__name__} on {url}: {e}') from e


def _download(url: str, cache_dir: str, reuse: bool = True,
              magic: bytes = b'PK') -> str | None:
    """下载到 cache/，返回本地路径；404 返回 None。

    reuse=True 时复用已落盘的文件。老月份的附表官方从不重发（已核对 apr/may 两期 12 个
    重叠月逐值相同），复用是安全的；但**最近两个月的文件可能被官方重新上传更正**，
    所以调用方对新文件传 reuse=False，强制重取。

    magic 是文件头的前几个字节：xlsx 是 zip 所以 b'PK'，新闻稿 PDF 是 b'%PDF'。
    要判它是因为 CDN 偶尔用 200 返回一张「找不到页面」的 HTML，长度够大、内容全错。
    """
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, url.rsplit('/', 1)[-1])
    if reuse and os.path.exists(path) and os.path.getsize(path) > 10_000:
        return path
    blob = _get(url)
    if blob is None:
        return None
    if len(blob) < 10_000 or not blob.startswith(magic):
        raise FetchError(f'{url} 返回的不是 {magic.decode()} 文件（{len(blob)} bytes）')
    with open(path, 'wb') as f:
        f.write(blob)
    return path


def release_date(kind: str, report_ym: tuple[int, int], cache_dir: str):
    """某一期报告的官方发布日 → ('YYYY-MM-DD', 出处描述)；拿不到返回 (None, 原因)。

    发布日只从新闻稿正文第 1 页的电头读（见模块 docstring 的「官方发布日」一节）。
    PDF 一律 reuse：电头是印在正文里的，官方就算把文件重新上传一遍也不会改那一行，
    所以这里不像 xlsx 那样对新月份强制重取。
    """
    y, m = report_ym
    if kind == 'monthly':
        url = PR_MONTHLY_URL.format(mon=_MON[m - 1], year=y)
    else:
        url = PR_QUARTER_URL.format(q=(m - 1) // 3 + 1, year=y)
    name = url.rsplit('/', 1)[-1]

    path = _download(url, cache_dir, magic=b'%PDF')
    if path is None:
        return None, f'{name} 在 CDN 上是 404'
    try:
        import fitz                       # 延迟 import：同 openpyxl 的处理，缺它只该让
    except ImportError:                   # 发布日缺席，不该把整家的数据摄入一起拖挂
        return None, 'pymupdf(fitz) 未安装，读不了新闻稿 PDF'
    try:
        # 先把换行/不间断空格压成单空格：PDF 抽出来的电头经常被折行成两段，
        # 不压的话正则里的 \s+ 也救不了「Texas,\nJuly」中间夹的软连字符之类。
        txt = re.sub(r'\s+', ' ', fitz.open(path)[0].get_text().replace('\xa0', ' '))
    except Exception as e:
        return None, f'{name} 第 1 页读不出文本：{type(e).__name__}'
    hit = _DATELINE.search(txt)
    if not hit:
        return None, f'{name} 第 1 页找不到 "WESTLAKE, Texas, <月> <日>, <年>" 电头'
    mon = _MON_FULL.index(hit.group(1).capitalize()) + 1
    return (f'{int(hit.group(3)):04d}-{mon:02d}-{int(hit.group(2)):02d}',
            f'{name} 第 1 页电头 "{hit.group(0)}"')


def _ir_page_links(cache_dir: str) -> list[str]:
    """兜底诊断用：万一 CDN 命名规则变了，从 IR 落地页把真实链接捞出来。

    www.aboutschwab.com 拦 urllib（Akamai 按 TLS 指纹拦），只能借 curl 的 HTTP/2 栈，
    所以这条路**不进主流程**，只在主流程全 404 时被 update() 调用来生成有用的报错。
    """
    import subprocess
    hdr = [
        '-H', 'User-Agent: ' + _UA,
        '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        '-H', 'Accept-Language: en-US,en;q=0.9',
        '-H', 'Sec-Fetch-Dest: document', '-H', 'Sec-Fetch-Mode: navigate',
        '-H', 'Sec-Fetch-Site: none', '-H', 'Sec-Fetch-User: ?1',
        '-H', 'Upgrade-Insecure-Requests: 1',
    ]
    try:
        out = subprocess.run(['curl', '-sSL', '--compressed', '--http2', *hdr, IR_PAGE],
                             capture_output=True, timeout=90).stdout.decode('utf-8', 'replace')
    except Exception:
        return []
    with open(os.path.join(cache_dir, '_schw_ir_financial_reports.html'), 'w') as f:
        f.write(out)
    # 扩展名大小写都收：官方历史上真发过 .XLSX（见 _HIST_XLSX），而这个函数是
    # _crosscheck_due_month 的判官 —— 判官只认小写，官方哪天改回大写它就当作
    # 「落地页上没有更新的表」，护栏又变回静默。
    return sorted(set(re.findall(r'https://content\.schwab\.com/[^"\']+\.[xX][lL][sS][xX]', out)))


# ── 解析 ───────────────────────────────────────────────────────────────
def _sheet(wb):
    for name in wb.sheetnames:
        if name.strip().lower().endswith('smart'):     # 'SMART' / 'Smart' / 'ER SMART'
            return wb[name]
    raise FetchError(f'找不到 SMART 页，sheet 有：{wb.sheetnames}')


def _month_columns(ws, report_ym: tuple[int, int]) -> dict[tuple[int, int], int]:
    """定位 13 个月滚动表的列。

    不信任表头上方那行稀疏的年份标签（它只在每年第一列出现，一次版式微调就会错位），
    改成：找到月份缩写那一行，认定**最右一个数据列就是报告月**，然后按月倒推。
    倒推完再和表里写的月份缩写逐个核对，对不上直接抛 —— 这样版式变了会立刻炸，
    而不是悄悄把数据错位一格。
    """
    abbr = {m: i + 1 for i, m in enumerate(_MON)}
    hdr_row = hdr_cols = None
    for row in ws.iter_rows(min_row=1, max_row=15):
        cols = [(c.column, str(c.value).strip().lower()[:3]) for c in row
                if isinstance(c.value, str) and str(c.value).strip().lower()[:3] in abbr]
        if len(cols) >= 6:
            hdr_row, hdr_cols = row[0].row, cols
            break
    if hdr_cols is None:
        raise FetchError('找不到月份表头行')

    y, m = report_ym
    out: dict[tuple[int, int], int] = {}
    for k, (col, tag) in enumerate(reversed(hdr_cols)):     # 从最右（=报告月）往左
        yy, mm = y, m - k
        while mm <= 0:
            mm += 12
            yy -= 1
        if abbr[tag] != mm:
            raise FetchError(
                f'表头月份与报告月对不上：第 {hdr_row} 行第 {col} 列写的是 {tag}，'
                f'按报告月 {y}-{m:02d} 倒推应为 {mm:02d}。版式可能变了，人工核对后再跑。')
        out[(yy, mm)] = col
    return out


def _pfx(want) -> tuple[str, ...]:
    """把 _LABEL 的值归一成给 str.startswith 用的前缀元组（写一个字符串也收）。

    只做归一，**不改前缀匹配的语义**：单标签的列行为与改动前逐字相同。
    """
    return (want,) if isinstance(want, str) else tuple(want)


# 「标签占一行、数值在下一行」那种老版式里，下一行第一列写的就是单位说明。
# 三种写法都见过（0 / 1 / 2 个前导空格），归一去空白后只剩这一个正则。
# **判据必须是这一行长什么样，不能是「往下找一行」**：Schwab 的 SMART 页整张表都是
# 「标题行 + 明细行」的堆叠（`Net Buy (Sell) Activity` 下面就跟着三行基金流量），
# 无条件往下顺一行，会把隔壁指标的数当成本行的，而且看上去完全正常。
_UNIT_ROW_RE = re.compile(r'^\(in (?:millions|billions|thousands) of dollars\)$')


def _row_values(ws, prefix, cols: dict, unit_row: bool = False) -> dict | None:
    """按标签前缀找行，返回 {(y,m): 原始数值}；找不到该行返回 None。

    prefix 可以是一个前缀，也可以是一串前缀（见 _LABEL / _pfx），命中任意一个即算。

    unit_row=True 时多认一种版式：标签行**一个数值格都没有**、数值落在紧邻的
    「单位说明行」上（见 _UNIT_ROW_RE）。这不是可有可无的兼容 —— 平均生息资产在
    2019 年及更早的 13 份附表里全是这种版式，而本函数对「标签匹配上、但这一行没有
    数」的处理是**继续往下扫、最终返回 None**，调用方 parse_table 又把 None 当
    「这一期没有这一行」`continue` 掉。于是整列**静默缺席**，日志里一个字都不会有。
    这正是这一列被漏抓七年的机制：不是官方不披露，是解析器只看标签那一行 ——
    与 _pfx 那次（老写法过不了单前缀）是同一种病的两种长相。
    默认 False，既有 8 列的行为与改动前逐字相同。
    """
    pfx = _pfx(prefix)
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
        lab = row[0].value
        if not isinstance(lab, str):
            continue
        lab = re.sub(r'\s+', ' ', lab).strip().lower()
        if not lab.startswith(pfx):
            continue
        for r in ([row[0].row, row[0].row + 1] if unit_row else [row[0].row]):
            if r != row[0].row:
                nxt = ws.cell(row=r, column=1).value
                if not (isinstance(nxt, str)
                        and _UNIT_ROW_RE.match(re.sub(r'\s+', ' ', nxt).strip().lower())):
                    break
            vals = {}
            for ym, col in cols.items():
                v = ws.cell(row=r, column=col).value
                if isinstance(v, (int, float)):
                    vals[ym] = float(v)
            if vals:
                return vals
    return None


def _scale(anchor: dict, lo: float, hi: float, what: str, cands=None) -> float:
    """用锚点行反推单位倍率。金额/计数的候选是 1 / 1e-3 / 1e-6 / 1e-9 四档，
    比率行传 cands=(1.0, 100.0)（分数 vs 百分点）。
    要求**所有**锚点值套上倍率后都落进合理区间，且只有一档满足 —— 有歧义就抛。"""
    ok = [s for s in (cands or (1.0, 1e-3, 1e-6, 1e-9))
          if all(lo <= abs(v) * s <= hi for v in anchor.values())]
    if len(ok) != 1:
        raise FetchError(f'{what} 单位倍率判不定（候选 {ok}，样值 {list(anchor.values())[:3]}）')
    return ok[0]


def parse_table(path: str, report_ym: tuple[int, int]) -> dict:
    """把一个 xlsx 解析成 {(year, month): {列名: 值}}。缺关键行直接抛。"""
    ws = _sheet(openpyxl.load_workbook(path, data_only=True, read_only=False))
    cols = _month_columns(ws, report_ym)

    a_money = _row_values(ws, _LABEL['_anchor_money'], cols)
    a_count = _row_values(ws, _LABEL['_anchor_count'], cols)
    if not a_money or not a_count:
        raise FetchError(f'{os.path.basename(path)}: 找不到单位锚点行')
    s_money = _scale(a_money, *_SANE['total_client_assets_usdbn'], 'money')
    s_count = _scale(a_count, *_SANE['_anchor_count'], 'count')

    # unit_row 与 _SELF_SCALED 用的是同一个集合，不是图省事：两者是**同一个事实**的
    # 两个后果 —— 这一行坐在自己的单位块里，所以（a）老版式要把单位单独印一行（那一行
    # 才有数），（b）它的倍率不能跟客户资产那个锚点走。将来若出现只占其中一条的列，
    # 这里就该拆成两个集合，别硬塞进来。
    raw = {c: _row_values(ws, _LABEL[c], cols, unit_row=c in _SELF_SCALED) for c in COLS}
    out: dict[tuple[int, int], dict] = {ym: {} for ym in cols}
    for c in COLS:
        if raw[c] is None:
            continue
        if c in _RATIO:
            s = _scale(raw[c], *_SANE[c], f'{c}', cands=(1.0, 100.0))
        elif c in _SELF_SCALED:
            s = _scale(raw[c], *_SANE[c], f'{c}', cands=_SELF_CANDS)
        else:
            s = s_money if c in _MONEY else s_count
        for ym, v in raw[c].items():
            x = v * s
            lo_hi = _SANE.get(c)
            if lo_hi and not (lo_hi[0] <= abs(x) <= lo_hi[1]):
                raise FetchError(f'{os.path.basename(path)} {ym} {c}={x} 超出合理区间 {lo_hi}')
            out[ym][c] = round(x, 6)
    return out


def _required(ym: tuple[int, int]) -> list[str]:
    """该月**必须**解析出来的列。缺任何一列 → 抛，绝不写 NaN。

    三段**月频**披露边界（是月报这条源的边界，不是解析能力的边界）：
      · 2025-01 起才有 dats_k / margin_balances_usdbn / sweep_cash_usdbn / mmf_usdbn
        （2026-01 那期月报一次新增这四列并回填到 2025-01）
      · 2017-02 起才有 core_nna_usdbn（见 _CORE_NNA_FROM）
      · 2013-09 起才有 client_cash_pct（见 _CASH_PCT_FROM；也是本序列的第一个月）
      · 再往前只剩客户总资产与新开经纪账户两列

    **别把第一段读成「公司 2025-01 前不披露这四个量」**：dats_k 与 margin_balances_usdbn
    的季度口径在季报附表里回得到 2012Q4（见 series/schw_q.csv 与「季频腿」那一节），
    那是**月报**的边界不是**量**的边界；sweep_cash_usdbn / mmf_usdbn 在季报里查无此行，
    对它们「2025-01 是披露边界」目前仍成立。
    """
    out = list(COLS)
    if ym < _AVG_IEA_FROM:
        out = [c for c in out if c != 'avg_interest_earning_assets_usdbn']
    if ym < _DATS_MARGIN_FROM:
        out = [c for c in out if c not in ('dats_k', 'margin_balances_usdbn',
                                           'sweep_cash_usdbn', 'mmf_usdbn')]
    if ym < _CORE_NNA_FROM:
        out = [c for c in out if c != 'core_nna_usdbn']
    if ym < _CASH_PCT_FROM:
        out = [c for c in out if c != 'client_cash_pct']
    return out


# ── 源枚举 ─────────────────────────────────────────────────────────────
def _today_ym() -> tuple[int, int]:
    t = _dt.date.today()
    return (t.year, t.month)


def _shift(ym: tuple[int, int], k: int) -> tuple[int, int]:
    y, m = ym
    m += k
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return (y, m)


def _candidates(back: int = 8):
    """按时间倒序给出待探的 (kind, url, report_ym)。

    月报探最近 back 个月；季报探最近 3 个季度。都探是因为季末月只有季报有，
    而季报又比「下一期月报」早一个月出来。
    """
    y, m = _today_ym()
    for k in range(back):
        yy, mm = _shift((y, m), -k)
        if mm % 3 == 0:          # 季末月没有独立月报，别浪费一次请求
            continue
        yield 'monthly', MONTHLY_URL.format(mon=_MON[mm - 1], year=yy), (yy, mm)
    q = (m - 1) // 3 + 1
    for k in range(3):
        qq, yy = q - k, y
        while qq <= 0:
            qq += 4
            yy -= 1
        yield 'quarterly', QUARTER_URL.format(q=qq, year=yy), (yy, qq * 3)


def _template_url(ym: tuple[int, int]) -> str:
    """本模块**推**出来的那个 URL。和 _candidates 给的是同一套写法，只是按月点名取一个。"""
    y, m = ym
    if m % 3 == 0:                       # 季末月没有独立月报，值在当季季报附表里
        return QUARTER_URL.format(q=(m - 1) // 3 + 1, year=y)
    return MONTHLY_URL.format(mon=_MON[m - 1], year=y)


# ── 逾期对账：拦「文件名模板过期了」这一类不出声的失败 ──────────────────
# _candidates() 给的是**推**出来的文件名，不是**发现**的。官方哪天改了命名规则，
# 新一期的 URL 就 404 —— 而 404→None（_get）与 continue（_collect）都是**设计如此**：
# 当月月报还没发之前那个 URL 本来就该 404，季末月的月报更是永远 404。
# 于是坏掉的样子是这样的：最新一期永远抓不到，老月份照旧从 cache 里读得出来，
# `if not got` 那道护栏（它要求 ~11 个候选**全部** 404）永远轮不到，update() 每天
# 干干净净返回 []、报 NOCHANGE。**连续坏十天和正常十天，日志里长得一模一样。**
# 而这不是假想：本模块自己的 _HIST_XLSX 就记着官方已经改过两次名（季报附表前缀
# schwab_ / 扩展名大写 .XLSX），且改名是**只往前改**的 —— 老文件至今仍 200。
# 只往前改，恰恰是让 got 一直为 True、让上面那道护栏永远沉默的那种改法。
#
# 所以这里补 README「第四类：不出声的失败」要的那道：拿一个**独立于文件名模板**的
# 判据来对账 —— 官方 IR 落地页上真实挂着的链接（_ir_page_links）。形状照
# fetch/cboe.py 的 _crosscheck_report_month、fetch/ice.py 的 _crosscheck_workbook_month。

# (常规月, 季末月)：某个月的数据**最晚**在该月结束后第几天发布（常规月 = 规则上界，季末月 = 实测最坏，
# 出处见模块 docstring「发布节奏」）。build/roster.py 的 LAG['schw'] 是它的抄件（那张表的表头注释写着「数值取自各
# fetch/<t>.py docstring 里的实测发布日」）—— 哪天节奏变了，这里、roster 与 docs/CRON_WIRING.md §2.3 那一行要一起改。
# 季末月单独一个数不是可有可无的讲究：季末月（3/6/9/12）没有独立月报，数值随当季
# 季报走，晚一周。拿常规月的日子去判季末月，这道护栏会**每个季度误报一次**，
# 而每季度假一次的警报，人很快就学会无视（README「新鲜度红点」讲的是同一件事）。
_LAG_DAYS = (17, 21)
# 红线再往后推的余量。红点用的是 roster.GRACE = 5，这里刻意给到它的近三倍。
# 两者方向相反：红点早响一天，是首页多一个红圆点、cron 把这一家记进失败清单
# （monthly_run.audit_overdue_headline）；这道护栏早响一天，是把一家本来健康的
# fetcher 变成每日 FAIL。次序必须是「红点先红、人先看见，本护栏远远跟在后面才开口」。
# 余量不能按 GRACE 那个量级给：季报实测第 16/16/21/21 天**正好顶到** _LAG_DAYS[1]，撞一次假日
# 顺延就越线（_LAG_DAYS[0] 的 17 是规则上界；2026-09-14 之前写 14，9 月每年越线 1-3 天）。
_OVERDUE_MARGIN_DAYS = 14

# 从 URL 里认报告月：判官要**容错**，因为它存在的理由就是「命名规则变了」。
# 全称与三字母缩写都认（还额外认 sept 这个常见写法），分隔符可有可无，大小写无关。
# 刻意不把 'table' / 'earnings' 写进条件：那正是可能被改掉的那部分词。
# 但也刻意**不**做成「月份三字母后面随便跟什么」—— 那样 marketdata2026.xlsx 会被
# 读成 2026-03，而这道护栏一旦误判就是 FAIL，宁可少认一种写法也不能凭空造一个月份。
_URL_MONTH_RE = re.compile(
    r'(?<![a-z])(' + '|'.join([f.lower() for f in _MON_FULL] + ['sept'] + _MON)
    + r')[-_ ]?(20\d{2})(?![0-9])', re.IGNORECASE)
_URL_QUARTER_RE = re.compile(r'(?<![a-z0-9])q([1-4])[-_ ]?(20\d{2})(?![0-9])', re.IGNORECASE)
_URL_QUARTER_RE2 = re.compile(r'(?<![0-9])(20\d{2})[-_ ]?q([1-4])(?![0-9])', re.IGNORECASE)


def _month_end(ym: tuple[int, int]) -> _dt.date:
    """该月最后一天。用「下月 1 号减一天」算，省得为了闰年再引一个 calendar。"""
    ny, nm = _shift(ym, 1)
    return _dt.date(ny, nm, 1) - _dt.timedelta(days=1)


def _overdue_deadline(ym: tuple[int, int]) -> _dt.date:
    """这个报告月的红线：过了这一天还没有它，就该有人来看一眼。"""
    lag = _LAG_DAYS[1] if ym[1] % 3 == 0 else _LAG_DAYS[0]
    return _month_end(ym) + _dt.timedelta(days=lag + _OVERDUE_MARGIN_DAYS)


def _due_ym(today: _dt.date | None = None) -> tuple[int, int]:
    """截至今天，**最新一个已经越过红线**的报告月。

    从上个月往回数，第一个红线已过的就是它（当月永远不可能越线，所以从 -1 起步）。
    参数 today 只为可测：生产路径一律用系统日期。
    """
    today = today or _dt.date.today()
    ym = _shift((today.year, today.month), -1)
    for _ in range(24):                  # 正常两三步就返回；24 只是防死循环的上界
        if _overdue_deadline(ym) <= today:
            return ym
        ym = _shift(ym, -1)
    return ym


def _url_report_ym(url: str):
    """从一个 xlsx 链接里认出它是哪一期 → (y, m)；认不出返回 None。

    季报按季末月记（q2_2026 → 2026-06），和 _candidates 对季报的记法一致，
    这样它和月报可以放在同一根时间轴上比大小。
    先只看文件名，认不出再看整条 URL —— 路径里常有「/2026/」这类年份噪音。
    """
    for text in (url.rsplit('/', 1)[-1], url):
        hit = _URL_MONTH_RE.search(text)
        if hit:
            return (int(hit.group(2)), _MON.index(hit.group(1).lower()[:3]) + 1)
        hit = _URL_QUARTER_RE.search(text)
        if hit:
            return (int(hit.group(2)), int(hit.group(1)) * 3)
        hit = _URL_QUARTER_RE2.search(text)
        if hit:
            return (int(hit.group(1)), int(hit.group(2)) * 3)
    return None


def _crosscheck_due_month(merged: dict, cache_dir: str) -> None:
    """拿到的最新月 vs 按发布节奏早该有的月，落后了就去问 IR 落地页这个外部判官。

    **抛不抛，只由判官说了算，绝不由日期单独说了算。** 这是这道护栏能进无人值守
    主路径的全部理由：官方晚发几天是常有的事（季报 4 期实测正好顶着 _LAG_DAYS[1]），
    光凭「过了红线」就 FAIL，等于每逢一次假日顺延就把一家健康的 fetcher 判死。
    而「落地页上明明挂着比我们拿到的更新的表」不是晚发能造出来的状态 —— 那只可能
    是我们推的文件名不对了。

    落地页这条路平时**不进主流程**（www.aboutschwab.com 在 Akamai 后面按 TLS 指纹
    拦人，见模块 docstring），所以只在越线那一天才问它一次，正常日子零额外请求。

    判官自己哑了（curl 被拦、落地页改版捞不到链接）时**只喊不抛**：一道连自己的
    探针都失灵了的护栏，不能反过来把数据摄入判死。但那一声必须喊出来 —— 否则这道
    护栏就悄悄退化成它本来要消灭的那个形状（静默）。
    """
    newest, due = max(merged), _due_ym()
    if newest >= due:
        return
    due_key = f'{due[0]:04d}-{due[1]:02d}'
    newest_key = f'{newest[0]:04d}-{newest[1]:02d}'
    line = _overdue_deadline(due)

    links = _ir_page_links(cache_dir)
    if not links:
        print(f'  [overdue] {due_key} 已过红线 {line} 仍未拿到（手上最新是 {newest_key}），'
              f'而 IR 落地页这次一个 xlsx 链接都没捞到（{IR_PAGE}，curl 被 Akamai 拦？）。'
              f'判官自己哑了，本次不判失败 —— 请人工打开落地页核一眼命名规则。')
        return

    advertised = [(ym, u) for ym, u in ((_url_report_ym(u), u) for u in links) if ym]
    if not advertised:
        print(f'  [overdue] {due_key} 已过红线 {line} 仍未拿到（手上最新是 {newest_key}）；'
              f'IR 落地页捞到 {len(links)} 个 xlsx 链接，却没有一个能解析出报告月：'
              f'{links[:5]}。命名规则可能变得连判官也认不出了，请人工核对。')
        return

    # 只认「比手上新、且自己也已经越过红线」的那一档：落地页上偶尔会先挂出还没到
    # 发布期的下一期链接，拿那种未来期当证据就是自己造一个假警报。
    newer = sorted((ym, u) for ym, u in advertised if newest < ym <= due)
    if not newer:
        print(f'  [overdue] {due_key} 已过红线 {line} 仍未出现；IR 落地页上也没有比 '
              f'{newest_key} 更新的表，判定为**官方晚发**，不是抓取故障。')
        return

    ym, real = newer[-1]
    raise FetchError(
        '逾期对账失败：IR 落地页上挂着 %s 的附表，我们按文件名模板推出来的 URL 却没拿到它。\n'
        '  落地页上的真实链接：%s\n'
        '  本模块推出来的 URL：%s\n'
        '  手上最新月 %s，红线 %s（= 月末 + %s 天节奏 + %d 天余量）。\n'
        'CDN 的命名规则或路径多半变了（史上改过：季报附表前缀 schwab_、扩展名大写 .XLSX，'
        '见 _HIST_XLSX）。这时候静默返回 NOCHANGE，页面会一直挂着旧数据而日志上看不出'
        '任何异常，所以这里拒绝写入：请照落地页上的真名改 MONTHLY_URL / QUARTER_URL，'
        '再跑一次。'
        % (f'{ym[0]:04d}-{ym[1]:02d}', real, _template_url(ym), newest_key, line,
           _LAG_DAYS[1] if due[1] % 3 == 0 else _LAG_DAYS[0], _OVERDUE_MARGIN_DAYS))


# ── 历史回填源（2013-09 … 2018-04）─────────────────────────────────────
# 主流程 _candidates() 只探最近 8 个月 / 3 个季度 —— 那是「每月增量」该有的样子，
# 不该为了追历史每次多打几十个请求。但 2026-08-16 的一次历史考古发现，官方手上
# **还留着**一批更老的表，主流程碰不到它们只是因为文件名有两处变体：
#
#   (a) **前缀**：2017 年及更早的季报附表叫 `schwab_`，不是 `schw_`
#       （schw_q1_2017…=404，schwab_q1_2017…=200）；
#   (b) **扩展名大写**：2017Q3–2018Q4 的几份是 `.XLSX`
#       （schw_q2_2018_earnings_tables.xlsx=404，同名 .XLSX=200）。
#
# 这两条都不是规律，是历史遗留的手工命名，推不出来 —— 所以这里**写死一份清单**而不是
# 拼 URL。清单里的每一份都实测过 200 且解析通过；哪天官方撤下某一份，backfill() 会
# 在 stdout 上点名说它没了，而不是静默少几个月（已经落盘的历史行不受影响）。
#
# 再往前（2013-09 … 2016-12）CDN 上一份都不剩了，但 **SEC EDGAR 上有**：Schwab 把
# 「月度活动报告」原样作为季度 8-K 的 EX-99.1 附上去，正文里就是那张 13 个月滚动表。
# 这条路对**每一期**都有效（不止老年份），详见上方 docstring 里关于两代版式的那一段。
_HIST_XLSX = [
    # (报告月, URL 文件名) —— 报告月 = 该表最右一列，parse_table 按它倒推整张表
    ((2016, 9),  'schw_q3_2016_earnings_tables.xlsx'),
    ((2016, 12), 'schw_q4_2016_earnings_tables.xlsx'),
    ((2017, 3),  'schwab_q1_2017_earnings_tables.xlsx'),
    ((2017, 6),  'schwab_q2_2017_earnings_tables.xlsx'),
    ((2017, 9),  'schwab_q3_2017_earnings_tables.XLSX'),
    ((2018, 2),  'schwab_feb2018_table.XLSX'),
    ((2018, 3),  'schw_q1_2018_earnings_tables.XLSX'),
    ((2018, 6),  'schw_q2_2018_earnings_tables.XLSX'),
    ((2018, 9),  'schw_q3_2018_earnings_tables.xlsx'),
    ((2018, 12), 'schw_q4_2018_earnings_tables.XLSX'),
    ((2019, 1),  'schwab_jan2019_table.xlsx'),
    ((2019, 2),  'schwab_feb2019_table.xlsx'),
    ((2019, 4),  'schwab_apr2019_table.xlsx'),
    ((2019, 5),  'schw_may2019_table.xlsx'),
]
EDGAR_CIK = '0000316709'
EDGAR_SUB = 'https://data.sec.gov/submissions/CIK{cik}.json'
EDGAR_DIR = 'https://www.sec.gov/Archives/edgar/data/316709/{acc}'
# EDGAR 要求 UA 里带得到人的联系方式，否则 403。这不是反爬，是它明文写的使用条款。
_EDGAR_UA = 'monthly-op-dashboards research (hzhan7@gmail.com)'
# 扫到哪一期为止。**不是**因为之后就没有表了（2026 年那期 EX-99.1 里照样有），
# 而是 2018-05 起 series/schw.csv 本来就有值，再扫下去只是拿同样的数对一遍账。
# 留一年余量：往后多扫一点，重叠对账的样本就多一点，那是这条路唯一的自检。
_EDGAR_UNTIL = '2020-01-01'


def _edgar_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': _EDGAR_UA,
                                               'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(req, timeout=60) as r:
        blob = r.read()
    if blob[:2] == b'\x1f\x8b':
        import gzip
        blob = gzip.decompress(blob)
    return blob


def _edgar_8k(limit_before: str = _EDGAR_UNTIL) -> list:
    """CIK 的 8-K 清单（含历史分片），只留 limit_before 之前的。→ [(date, acc, [docs])]"""
    j = json.loads(_edgar_get(EDGAR_SUB.format(cik=EDGAR_CIK)))
    rows = []
    packs = [j['filings']['recent']]
    for f in j['filings'].get('files', []):
        _time.sleep(0.15)
        packs.append(json.loads(_edgar_get(
            'https://data.sec.gov/submissions/' + f['name'])))
    for p in packs:
        rows += [(d, a) for a, fm, d in
                 zip(p['accessionNumber'], p['form'], p['filingDate'])
                 if fm.startswith('8-K') and d < limit_before]
    return sorted(set(rows))


_HTML_TAG = re.compile(r'<[^>]+>')
_TITLE_RE = re.compile(
    r'Monthly\s+(?:Market\s+)?Activity\s+Report\s+For\s+([A-Za-z]+)\s+(\d{4})', re.I)


def _cell_text(c: str) -> str:
    t = _HTML_TAG.sub('', c)
    t = (t.replace('&#xFEFF;', '').replace('&#x2019;', "'").replace('&amp;', '&')
          .replace('&#160;', ' ').replace('&nbsp;', ' '))
    return re.sub(r'&#\d+;', '', t).strip()


def _glue(cells: list) -> list:
    """把被拆进独立 <td> 的「零件」粘回它前面那个数，再丢掉空单元格。

    这一步**不能省，也不能放在丢空格之后**。EDGAR 的表把会计负号的右括号、百分号
    单独放进一个 <td>：`(0.3` `)` 是两格。先丢空格再配对的话，`(0.3` 过不了 float()
    变成 None，那一行就**少一个 token**，于是 zip(months, vals) 之后**整行往后错一格** ——
    错位的每个值都是「上个月的数」，看着完全正常，只有跨源对账才抓得到。
    （实测：只改锚点不加这一步，2019-07…2020-07 那批文件里 core NNA 一列错出 44 个值，
    全部等于前一个月 —— 病根就是 2019-04 的 core NNA 是 -0.3。）
    """
    out: list = []
    for c in cells:
        if c in (')', '%', ')%', 'bp', ')bp') and out:
            out[-1] += c
        elif c != '':
            out.append(c)
    return out


def _html_num(x: str):
    """'2,556.7' → 2556.7；'(0.3)' → -0.3；'10.1%' → 10.1；'-'/'' → None。

    括号是会计负号。尾部的 '%' 要剥掉：`_glue` 会把独立 <td> 里的百分号粘回数值后面，
    不剥的话 float() 失败 → 整行返回 None → 「这份文件没有这一行」，与真的没有长得一样
    （客户现金占比那一行 2013 年至今每期都印，就是这么被静默丢掉的）。
    百分点与分数的归一交给 _RATIO 那条倍率判定，这里只负责把字符串变成数。
    """
    t = x.replace(',', '').replace('$', '').strip()
    if t.endswith('%'):
        t = t[:-1].strip()
    neg = t.startswith('(') and t.endswith(')')
    if neg:
        t = t[1:-1].strip()
    if t in ('', '-', '\u2014', 'N/A', '*'):
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def parse_edgar_monthly(html: str) -> dict:
    """8-K EX-99.1 里的月度活动报告表 → {(y, m): {col: 值}}；不是这种文件返回 {}。

    与 xlsx 那条路共用同一套规矩：**按标签前缀取行、按锚点行反推单位倍率、
    表头月份与标题月倒推逐个核对**。核对不上就整份丢掉（返回 {}）而不是猜 ——
    这批文件跨 4 年、版式改过好几次，错位一格在图上看不出来。

    **一共要认三代版式**（全大写标签那一代是 2026-09-16 才补上的，经过见模块 docstring
    「第二次更正」那条）：
      · 2013-12 … 2014-06（DFIN 报送，3 份）：标题是 "Monthly **Market** Activity
        Report"、HTML 标签**全大写**、行标签与值**分两行**（值在 '(单位说明)' 那行）。
      · 2014-09 … 2017-03：标题在表的**第一行里**，标签与值同一行，小写标签。
      · 2017-04 起至今：标题在表**上方的 <div> 里**，其余同上。
    所以本函数里凡是按位置找 <table>/<tr>/<td> 的地方**一律走 lower() 或 re.I** ——
    这不是洁癖：漏一处的表现不是报错，而是**静默**返回 {}，与「官方没印这张表」同形。
    """
    # ── 锚点：必须锚在**标题**上，不能锚在「monthly activity report」这个词上 ──
    # 正文里另有一句脚注「…please see the Monthly Activity Report.」，位置比真表更靠前。
    # 锚错了还不止是找不到表：老版式（2017-03 及更早）标题在表的**第一行里**，
    # 所以要往回找 <table>；新版式标题在表**上方的 <div> 里**，要往后找。
    # 一律往回找的话，新版式会捞到上面某张毫不相干的表 —— 而且**静默**返回 {}。
    # 本文件 2026-08-16 首版就踩了这个坑：97 份 EX-99.1 只读出 15 份，
    # 于是得出了「2017-04 起表就不随 8-K 附了」这个**错误**结论（docstring 已更正）。
    hits = list(_TITLE_RE.finditer(html))
    if not hits:
        return {}
    hit = hits[-1]                       # 一份文件里标题只出现一次；取最后一个最稳
    i = hit.start()
    a_back = html.lower().rfind('<table', 0, i)
    if a_back >= 0 and html.lower().find('</table>', a_back) > i:
        a = a_back                       # 老版式：标题落在这张表内部
    else:
        a = html.lower().find('<table', i)   # 新版式：标题在表上方
    b = html.lower().find('</table>', a) if a >= 0 else -1
    if a < 0 or b < 0:
        return {}
    rows = []
    for r in re.findall(r'<tr[^>]*>(.*?)</tr>', html[a:b + 8], re.S | re.I):
        cells = [_cell_text(c) for c in
                 re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.S | re.I)]
        rows.append(_glue(cells))
    ay, am = int(hit.group(2)), _MON.index(hit.group(1).lower()[:3]) + 1
    hdr = next(([c.lower()[:3] for c in r if c.lower()[:3] in _MON]
                for r in rows if sum(c.lower()[:3] in _MON for c in r) >= 12), None)
    if not hdr:
        return {}
    yms = []
    y, m = ay, am
    for _ in hdr:
        yms.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    yms.reverse()
    if [_MON[mm - 1] for _, mm in yms] != hdr:      # 表头与标题月倒推对不上 → 版式变了
        return {}

    def row_of(prefix, skip_core=False):
        # 「标签独占一行、值在下一行」这件事在 EX-99.1 里是**无条件**兜的（下面 cands
        # 那一段），与 xlsx 那条路的 _row_values(unit_row=True) 只对指定列开是**有意**
        # 的差别：这里连锚点行都需要它（2013/2014 那版 DFIN 排版把 Total Client Assets
        # 也印成这种两行），不兜就是整份返回 {}；xlsx 那边 8 个老列的标签行一直自带值，
        # 无条件兜只会多出误配的风险而换不来任何一格数据。
        # 平均生息资产在这条路上同样是两行版式（2014-10-15 报送的 Sep-2014 那份：标签行
        # 整行只有 1 个 cell、值行 15 个 = 13 个月 + 环比/同比两格，r[1:1+len(yms)] 正好
        # 切到 13 个月），所以它不必再单独开关。
        pfx = _pfx(prefix)
        for idx, r in enumerate(rows):
            lab = re.sub(r'\s+', ' ', r[0]).strip().lower() if r else ''
            if not lab.startswith(pfx):
                continue
            if skip_core and lab.startswith('core'):
                continue
            # 先在本行取值（2015 年至今的版式，标签与值同一行）。取不到再往下看一行：
            # 2013/2014 那版 DFIN 排版把标签单独占一行，值落在下一行的**单位说明**格
            # 后面（'Total Client Assets' / '(at month end, in billions of dollars)'
            # '1,951.6' …）。只在本行取不到、且下一行以 '(' 开头时才接受这种配对 ——
            # 不加这个括号条件就会把**下一条指标**的值安到本行头上，而错位的值看着完全正常。
            cands = [r]
            nxt = rows[idx + 1] if idx + 1 < len(rows) else None
            if nxt and nxt[0].strip().startswith('('):
                cands.append(nxt)
            for rr in cands:
                vals = [_html_num(x) for x in rr[1:1 + len(yms)]]
                if sum(v is not None for v in vals) >= len(yms) - 2:
                    return {ym: v for ym, v in zip(yms, vals) if v is not None}
        return None

    a_money = row_of(_LABEL['_anchor_money'])
    a_count = row_of(_LABEL['_anchor_count'])
    if not a_money or not a_count:
        return {}
    s_money = _scale(a_money, *_SANE['total_client_assets_usdbn'], 'edgar money')
    s_count = _scale(a_count, *_SANE['_anchor_count'], 'edgar count')

    out: dict = {ym: {} for ym in yms}
    for col in COLS:
        vals = row_of(_LABEL[col])
        if vals is None:
            continue
        if col in _RATIO:
            s = _scale(vals, *_SANE[col], f'edgar {col}', cands=(1.0, 100.0))
        elif col in _SELF_SCALED:
            s = _scale(vals, *_SANE[col], f'edgar {col}', cands=_SELF_CANDS)
        else:
            s = s_money if col in _MONEY else s_count
        for ym, v in vals.items():
            x = v * s
            lo_hi = _SANE.get(col)
            if lo_hi and not (lo_hi[0] <= abs(x) <= lo_hi[1]):
                raise FetchError(f'EDGAR {ym} {col}={x} 超出合理区间 {lo_hi}')
            out[ym][col] = round(x, 6)
    return {ym: v for ym, v in out.items() if v}


RESTATEMENTS: list = []      # 上一次 _collect 发现的跨源/跨期数值打架，供调用方审计
# 上一次 _collect 里每个月的数值最终由哪份文件说了算：{(y,m): (kind, 报告月)}。
# update() 靠它判断这个月是「自己那期报告」发的还是从后续滚动表里补来的 —— 只有前者
# 才有资格把那期的电头日期当成这个月的发布日。
ORIGIN: dict = {}


def _collect(cache_dir: str, back: int = 8) -> dict:
    """下载 + 解析所有能拿到的源，合并成 {(y,m): {col: val}}。

    _candidates 是「新→旧」序，所以合并规则是：**先写者胜**（越新的文件越权威），
    唯一的例外是季报——季报是该季末月的最终版，rank 更高，可以覆盖月报的同月值。
    覆盖时如果新旧值不等，说明官方重述了，记进 RESTATEMENTS 让人看得见，不静默吞掉。
    """
    merged: dict[tuple[int, int], dict] = {}
    origin = ORIGIN
    origin.clear()
    RESTATEMENTS.clear()
    got = False
    for kind, url, ym in _candidates(back):
        fresh = ym >= _shift(_today_ym(), -2)          # 最近两个月的文件不吃缓存
        path = _download(url, cache_dir, reuse=not fresh)
        if path is None:
            continue
        got = True
        for m_ym, vals in parse_table(path, ym).items():
            prev_rank = _SOURCE_RANK.get(origin.get(m_ym, (None,))[0], -1)
            slot = merged.setdefault(m_ym, {})
            for c, v in vals.items():
                if c in slot:
                    if _differs(c, slot[c], v):
                        RESTATEMENTS.append((m_ym, c, slot[c], v, os.path.basename(path)))
                    if _SOURCE_RANK[kind] <= prev_rank:
                        continue                       # 先写者胜
                slot[c] = v
            if _SOURCE_RANK[kind] > prev_rank:
                origin[m_ym] = (kind, ym)
            else:
                origin.setdefault(m_ym, (kind, ym))
    if not got:
        links = _ir_page_links(cache_dir)
        raise FetchError(
            '最近 %d 个月的月报附表和最近 3 个季度的季报附表**全部** 404 —— 整个目录或'
            '域名搬家了。（只改命名规则走不到这里：官方改名是只往前改的，老文件照旧 200，'
            '这个 got 就一直是 True。那种坏法由 _crosscheck_due_month 负责，别再指望这一条。）'
            'IR 落地页上当前的 xlsx 链接：%s'
            % (back, links[:10] or '（落地页也取不到）'))
    # 上面那道只管「一个都没拿到」。真正常见的是「老的都拿到了、最新一期没拿到」——
    # 那种没有任何 404 计数、没有任何异常，得靠外部判官对账。见该函数 docstring。
    _crosscheck_due_month(merged, cache_dir)
    return merged


# ── 对外接口 ───────────────────────────────────────────────────────────
def latest_month(cache_dir) -> str | None:
    """官方源当前最新月，"YYYY-MM"。抓不到抛 FetchError。"""
    data = _collect(cache_dir)
    ok = [ym for ym, v in data.items() if all(c in v for c in _required(ym))]
    if not ok:
        raise FetchError('源文件解析出来了，但没有任何一个月凑齐必需列')
    y, m = max(ok)
    return f'{y:04d}-{m:02d}'


def _differs(col: str, a, b) -> bool:
    """两个源给同一格的值，**按落盘精度**判是不是真的不一样。

    不用 `abs(a-b) > 1e-6`：那是原精度比较，会在 CSV 里根本体现不出来的地方报警。
    实例（2026-08-19）：client_cash_pct 的 2019-01，月报 xlsx 里是 0.1174（浮点原值），
    EDGAR 的 HTML 印的是 "11.7%" —— 两者落盘都是 11.7，CSV 一个字符都不差，
    原精度比较却每次 --backfill 都吐三行 RESTATEMENTS。这类噪音的代价不是刷屏，
    是让人学会忽略这张表，于是真的官方重述来的那天也被一起忽略掉。
    """
    return _fmt(col, a) != _fmt(col, b)


def _fmt(col: str, v) -> str:
    if v is None:
        return ''
    if col in ('new_brokerage_accounts_k', 'dats_k'):
        return str(int(round(v)))
    s = f'{round(v, 1):.1f}'
    return s


def _record_source_dates(series_dir, added: list, cache_dir) -> None:
    """给刚写进 series 的月份记下官方发布日。**只在数据确实落盘之后调**。

    这里一律不抛：发布日只影响页面抬头那半句话，抓不到就让它缺席（source_dates.py 的
    docstring 讲了为什么缺席好过瞎猜），把整月数据的摄入连坐掉是本末倒置。
    但每一次拿不到都要在 stdout 上说清楚是哪一期、卡在哪 —— 静默才是不能接受的。
    """
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(root, 'source_dates.py'))
    sd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sd)

    for ym in added:
        key = f'{ym[0]:04d}-{ym[1]:02d}'
        kind, report_ym = ORIGIN.get(ym, (None, None))
        if report_ym != ym:
            # 这个月是从后面某一期的 13 个月滚动表里补来的（季末月缺季报时会走到这），
            # 那期的电头是它自己的发布日，套到这个月上就是编造。
            print(f'  [source_date] {key} 跳过：数值来自 {kind} {report_ym} 那一期的滚动表，'
                  f'不是这个月自己的报告')
            continue
        try:
            date, why = release_date(kind, report_ym, cache_dir)
        except FetchError as e:
            date, why = None, str(e)
        if not date:
            print(f'  [source_date] {key} 未记录：{why}')
            continue
        try:
            sd.record(series_dir, 'schw', key, date, why)
            print(f'  [source_date] {key} → {date}（{why}）')
        except ValueError as e:      # record 的三道护栏拦下来了，说明解析取错了东西
            print(f'  [source_date] {key} 拒收 {date}：{e}')


def update(series_dir, cache_dir) -> list:
    """把新月份追加进 series/schw.csv，返回新增月份 ["YYYY-MM", ...]。

    幂等：已存在的月份一律跳过（不覆盖、不重排、不改动已有行的任何字符）。
    """
    path = os.path.join(series_dir, SERIES)
    with open(path, newline='') as f:
        rows = list(csv.reader(f))
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    if header != ['month'] + COLS:
        raise FetchError(f'{SERIES} 列名与预期不符：{header}')
    have = {r[0] for r in body}

    data = _collect(cache_dir)
    added = []
    for ym in sorted(data):
        key = f'{ym[0]:04d}-{ym[1]:02d}'
        if key in have:
            continue
        vals = data[ym]
        missing = [c for c in _required(ym) if c not in vals]
        if missing:
            raise FetchError(f'{key} 解析结果缺列 {missing}，拒绝写入（不写 NaN）')
        body.append([key] + [_fmt(c, vals.get(c)) for c in COLS])
        added.append(ym)

    if not added:
        return []
    body.sort(key=lambda r: r[0])
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)
    os.replace(tmp, path)

    _record_source_dates(series_dir, added, cache_dir)
    return [f'{y:04d}-{m:02d}' for y, m in added]


def backfill(series_dir, cache_dir, verbose: bool = True) -> list:
    """把 2013-09 … 2018-04 的历史月份补进 series/schw.csv，返回新增月份。

    与 update() 的关系：update() 管**增量**（每月往后走一格，只探最近几期），
    backfill() 管**存量**（一次性把官方还留着的老表全扫一遍）。两者写同一个 CSV，
    都遵守同一条铁律：**已存在的月份一个字符都不改**。

    重叠月是这里最重要的一道自检 —— 老表与仓里现有的 99 个月有大量重叠，两边**必须**
    逐值相等。不等只有两种可能：解析取错了行/列，或者官方重述过。两种都不能静默：
    对不上的行会被打印出来并让整次回填失败（`FetchError`），要人去看。
    （2026-08-16 首次跑通时：57 个重叠 (月,指标) 全部相等，0 处不符。）

    幂等：跑第二遍不会有任何新增，也不会改动任何已有行。
    """
    def log(*a):
        if verbose:
            print(*a)

    merged: dict[tuple[int, int], dict] = {}
    origin: dict[tuple[int, int], str] = {}

    def absorb(vals: dict, src: str):
        """先写者胜。这里的「先」= 调用顺序：CDN 的表比 EDGAR 的新，先扫 CDN。"""
        for ym, cols in vals.items():
            slot = merged.setdefault(ym, {})
            for c, v in cols.items():
                if c in slot:
                    if _differs(c, slot[c], v):
                        RESTATEMENTS.append((ym, c, slot[c], v, src))
                    continue
                slot[c] = v
                origin.setdefault(ym, src)

    for ym, name in _HIST_XLSX:
        url = f'{CDN}/excels/{name}'
        try:
            path = _download(url, cache_dir)
        except FetchError as e:
            log(f'  [hist] {name} 下载失败：{e}')
            continue
        if path is None:
            log(f'  [hist] {name} 已从 CDN 撤下（404）—— 已落盘的历史行不受影响')
            continue
        absorb(parse_table(path, ym), name)
        log(f'  [hist] {name} ok')

    # EDGAR：2017-03 之前的月度表嵌在季度 8-K 的 EX-99.1 里
    try:
        fils = _edgar_8k()
    except Exception as e:
        log(f'  [edgar] 清单取不到（{type(e).__name__}: {e}），本轮只用 CDN 的历史表')
        fils = []
    for date, acc in fils:
        base = EDGAR_DIR.format(acc=acc.replace('-', ''))
        try:
            idx = json.loads(_edgar_get(base + '/index.json'))
        except Exception:
            continue
        _time.sleep(0.15)
        # 附件命名两代都有：`schw-20141015ex99157591b.htm` 与 `exhibit991093018.htm`。
        # 只筛 'ex99' 会**静默漏掉后者**（'exhibit991…' 里没有 ex99 这个连续子串），
        # 而漏掉的表现是「这期没有月度表」，与「真的没有」长得一模一样。
        # 一份 8-K 通常只挂 3–6 个文档，全试一遍的代价可以忽略，比猜命名规律稳。
        docs = [it['name'] for it in idx['directory']['item']
                if it['name'].lower().endswith(('.htm', '.html'))]
        for d in docs:
            try:
                html = _edgar_get(f'{base}/{d}').decode('utf-8', 'replace')
            except Exception:
                continue
            _time.sleep(0.15)
            got = parse_edgar_monthly(html)
            if got:
                absorb(got, f'EDGAR {acc}/{d}')
                log(f'  [edgar] {date} {d} → {min(got)}…{max(got)}')
                break

    if not merged:
        raise FetchError('历史回填一个月份都没解析出来 —— CDN 与 EDGAR 两条路都空了，'
                         '不要当成「没有历史数据」，先人工核对 _HIST_XLSX 里的链接。')

    # ── 与现有 CSV 对账 ──
    path = os.path.join(series_dir, SERIES)
    with open(path, newline='') as f:
        rows = list(csv.reader(f))
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    if header != ['month'] + COLS:
        raise FetchError(f'{SERIES} 列名与预期不符：{header}')
    have = {r[0]: r for r in body}

    clash, checked = [], 0
    for ym, vals in merged.items():
        key = f'{ym[0]:04d}-{ym[1]:02d}'
        if key not in have:
            continue
        for c, v in vals.items():
            cur = have[key][1 + COLS.index(c)]
            if cur == '':
                continue
            checked += 1
            if abs(float(cur) - v) > max(0.05, abs(float(cur)) * 1e-6):
                clash.append((key, c, float(cur), v))
    log(f'  [对账] 重叠 {checked} 个 (月,指标)，不符 {len(clash)} 个')
    if clash:
        for c in clash[:20]:
            log('    MISMATCH', c)
        raise FetchError(f'历史表与仓里现有值有 {len(clash)} 处不符，拒绝写入。'
                         '要么解析取错了行，要么官方重述过 —— 两种都得人去看。')

    added = []
    for ym in sorted(merged):
        key = f'{ym[0]:04d}-{ym[1]:02d}'
        if key in have:
            continue
        vals = merged[ym]
        missing = [c for c in _required(ym) if c not in vals]
        if missing:
            log(f'  [跳过] {key} 缺 {missing}')
            continue
        body.append([key] + [_fmt(c, vals.get(c)) for c in COLS])
        added.append(key)

    if not added:
        return []
    body.sort(key=lambda r: r[0])
    # 连续性自检：回填后月份必须仍然逐月连号（build/schw.py 的 assert_monthly 也查这条，
    # 但在写盘之前就拦住，比让下游构建失败要好定位得多）。
    for i in range(1, len(body)):
        py, pm = int(body[i - 1][0][:4]), int(body[i - 1][0][5:])
        cy, cm = int(body[i][0][:4]), int(body[i][0][5:])
        if (cy, cm) != _shift((py, pm), 1):
            raise FetchError(f'回填后月份不连续：{body[i - 1][0]} → {body[i][0]}。'
                             '缺口会让 assets.diff() 把两个月的变动记到一个月上，拒绝写入。')
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)
    os.replace(tmp, path)
    log(f'  [回填] 新增 {len(added)} 个月：{added[0]} … {added[-1]}')
    return added


# ═════════════════ 列回填：给**已有的行**补上新增列（--columns）═════════════════
# 与 backfill() 的分工要说清楚，否则下一个人会把两者混成一个：
#   · update()           —— 往后走一格，**加行**（新月份）。
#   · backfill()         —— 往前补历史，**加行**（2013-09…2018-04）。
#   · backfill_columns() —— **一个行都不加**，只把新增的列填进已经存在的行里。
#
# 为什么必须单独有这一条路：前两条都只在「这个月不在 CSV 里」时才写盘，
# 于是 COLS 里新加一列时，历史行的那一格会**永远**空着 —— 加列的人跑一遍 update()
# 看见「新增 0 个月」，会以为没事。2026-08-19 加 client_cash_pct 三列时就是这样发现的。
#
# 铁律（与另两条一致）：**非空单元格一个字符都不改**；重叠值不符就整次失败。
_NEW_COLS = ('avg_interest_earning_assets_usdbn',)

# 列回填时同一个月拿到两套值（不同报告期给的数不一样）。与 _collect 的 RESTATEMENTS
# 同一个用途：官方重述过就让人看见，不静默取其一。
COLRESTATEMENTS: list = []

# ── 已采纳的官方重述（口径坑第 8 条的实现）──────────────────────────────────
# 每一条 = 一份**发布于重述之后**的附表，排在 _col_sources() 最前面，靠 absorb() 的
# 「先写者胜」压过默认采样里那份当期原值的附表。判据写在这里而不是只留在 CSV diff 里，
# 是因为 backfill_columns() 每次重跑都要重新裁决一遍：登记不在代码里，下一次跑就会把
# 重述值算回原值，然后撞上「非空格不许改」整次失败。
#
# 往这里加一条之前，先走完同一套证据链（与 fetch/enx.py 的 ACCEPTED_RESTATEMENTS 同规矩）：
#   ① 官方**明示**重述（脚注/表头原文，逐字抄进注释，不要转述）；
#   ② 回改范围用**数字**量清，不要信脚注自己说的区间（Schwab 这次就写错了，见口径坑 8）；
#   ③ 确认同一份文件里**没被重述的那些行**逐值相同 —— 排除「我们换了一份文件、于是别的
#      列也跟着变了」这种把两件事混在一起的改动；
#   ④ 逐格「旧值 → 新值」写进 commit message（这会覆盖既有非空单元格，属回填三条铁律
#      里「官方重述了」那一支，必须留痕）。
_RECAST = [
    # 2023 年 brokered CD 剔除。首份新口径出版物 = Jul-2023 月报（新闻稿电头
    # "WESTLAKE, Texas, August 14, 2023"），窗 2022-07…2023-07，脚注 (5,6) 原文见口径坑 8。
    # 逐格（2026-09-16 实测 may2023 vs july2023，两份都从 CDN 现取）：
    #   2022-12  12.3 → 12.2      2023-03  11.6 → 11.2
    #   2023-01  11.6 → 11.5      2023-04  11.3 → 10.8
    #   2023-02  11.7 → 11.6      2023-05  11.5 → 10.9
    #   2023-06  首印 11.0（q2_2023 8-K）→ 10.5；这一格 2026-08-19 入库时就已经是重述值。
    # 同期未被重述的对照：2022-07…2022-11 五个月两版逐值相同（12.0/12.1/12.9/12.2/11.5），
    # 分母 total_client_assets_usdbn 与其余 24 行一格未动 —— 官方只动了这一行的分子。
    #
    # ⚠ 文件名是 'july' 不是 'jul'：官方 2019-2025 的七月档都叫 schw_july<y>_table.xlsx
    #   （2026 年才改成 jul2026）。_MON[6] = 'jul' 拼不出它，实测 jul2023 / jul2025 都是 404、
    #   july2023 / july2025 都是 200。这份文件一度被当成「已从 CDN 撤下」，其实只是拼错了名字
    #   —— 与本模块 docstring 里 EDGAR 那条「解析器读不到，和源里没有，长得一模一样」同源。
    #   _template_url() 至今仍只拼三字母缩写，所以历史上**每一个七月**它都取不到。
    ((2023, 7), CDN + '/excels/schw_july2023_table.xlsx'),
]


def _col_sources(cache_dir: str):
    """列回填要覆盖 2013-09 至今**每一个月**，所以源的排法和 backfill() 不同。

    月报的 13 个月滚动表意味着「每 12 个月取一份」就够铺满，不必逐月下载：
      · _RECAST → 已采纳的官方重述，必须排最前（见那张表）
      · CDN 月报 schw_may<y>_table.xlsx（y=2019…今年）→ 2018-05 … 最新一期的 5 月
      · CDN 季报附表 schw_q4_<y>_earnings_tables.xlsx → 与上一条错开半年的第二相位
      · CDN 最近 8 个月 / 3 个季度（_candidates）→ 补上最新一期 5 月之后的月份
      · CDN 历史附表 _HIST_XLSX → 2015-09 … 2018-12
      · 再往前只有 SEC EDGAR（见下方 EDGAR 那一段）

    ⚠ **顺序即口径，改这个函数的排序等于改数据口径。** absorb() 是「先写者胜」，排在
    前面的源赢。现行排法两段：**_RECAST 绝对排最前**，其余**按报告期从新到旧**。

    ── 为什么 _RECAST 必须在 sorted() 之外 ──
    它是人工逐格核对过的官方重述源（口径坑 8），权威性不来自报告期新旧；混进 sorted()
    就会被报告期更新、但未经核对的文件顶掉，那张表也就白登记了。

    ── 为什么其余是从新到旧 ──
    2026-09-16 之前这里**没有排序**：may<y> 那个循环是 `range(2019, y_now+1)`、**升序**，
    最老的 may2019 第一个写，于是默认赢家是覆盖该月的**最老**那份文件。三列老列碰巧没被
    这个顺序咬到（官方没重述过它们），平均生息资产一加进来就咬：2025-12 起的口径变更
    追溯调整了 2025-01…2025-11（脚注原文见本模块 docstring 第 5 条），升序会让 may2025
    先写下旧基的 2025-01…2025-05，再让 2026 年的文件补上新基的 2025-06…2025-11 ——
    同一条序列里混两个基，接缝在 5/6 月之间，且**不报错**。

    q4_<y> 这一相位不是为了「多一层保险」，是为了让**重述后的那一份**能覆盖全部被改过的
    月份：schw_q4_2025_earnings_tables.xlsx 的滚动表正好是 2024-12…2025-12，而 may<y>
    这一相位在 2025 年只有 may2025（重述**之前**发的）。少了它，2025-01 会落回旧基。

    ⚠ **这与口径坑 8 写的「默认取当期原值」在措辞上是两条规矩，今天同解、将来可能不同解。**
    今天同解，是因为官方只重述过 client_cash_pct 那 7 个月（已进 _RECAST）、其余 7 列跨
    97 份来源逐月 0 处不符 —— 没有「无脚注的跨版本差异」这种样本存在。真出现那种样本时
    两条规矩会分道扬镳（这里取新、坑 8 取原值）：**那一天以坑 8 为准，按 COLRESTATEMENTS
    的日志人工裁决，不要默默让排序替你决定。**

    ⚠ **「每 12 个月取一份」铺满的是月份，不是版本 —— 排序修不了这件事。** may 瓦片首尾
    各压一个 5 月、相邻两份只重叠 1 个月，所以 13 个月里有 12 个月在整个源序列里**只有
    唯一一个源**，absorb() 的优先级规则对它们是空转 —— 官方后来落在瓦片内部的重述在这个
    采样密度下**结构性不可见**。2026-08-19 那次 2022-12…2023-05 六格取到重述前的值，
    根子就在这里，不在排序。_RECAST 是对已知那一次的点名补丁，**不是**通用的检测手段：
    下一次官方重述若不落在瓦片边界上，这条管道照样看不见。真要能自动发现，得把采样加密到
    每月两份（例如 may + nov），让每个月都有 ≥2 个互相独立的见证人，那是另一件事，
    别顺手在这里做。
    """
    y_now = _today_ym()[0]
    out = []
    for y in range(2019, y_now + 1):
        out.append(((y, 5), MONTHLY_URL.format(mon='may', year=y)))
    for y in range(2016, y_now + 1):
        out.append(((y, 12), QUARTER_URL.format(q=4, year=y)))
    for _kind, url, ym in _candidates(back=8):
        out.append((ym, url))
    for ym, name in _HIST_XLSX:
        out.append((ym, CDN + '/excels/' + name))
    # _RECAST 排在 sorted() 之外、永远最前（理由见上）；其余报告期新的排前面，
    # 同一报告期内保持原有相对次序（sorted 是稳定的）。
    return list(_RECAST) + sorted(out, key=lambda t: t[0], reverse=True)


# ═══════ 恒等式自检 2：月度平均生息资产 ↔ series/fee_rates.csv 的季度腿 ═══════
# 两条腿是**同一个量**的两种频率：月频取自月报附表 SMART 页的
# `Average Interest-Earning Assets`，季频取自季度业绩 8-K EX-99.1 的
# `Net Interest Revenue Information` 表（fetch/rates_schw.py 抓，metric 名
# avg_interest_earning_assets，单位 USD_mn）。两张表、两个解析器、两条抓取路径，
# 所以这道自检真正在核的是「我们有没有把行取对、单位判对、月份对齐对」。
#
# ── 为什么是**日历日加权**而不是算术平均 ──
# 派工单要求的是「按季取算术平均」，实测过，**那样写这道闸就是个摆设**：
# 月度值是该月**日均**、季度值是该季**日均**，严格关系是按当月日历天数加权
#     Q = (d1·M1 + d2·M2 + d3·M3) / (d1 + d2 + d3)
# 算术平均等于把 1/3 当权重，误差项 = (1/3 − di/Σd) 与月序列曲率的乘积。51 个季度实测：
#     口径        自身噪声(2018Q4 起，剔已知断点)      「三个月整体错位一格」的最小信号
#     算术平均    max 289 $mn / 987 ppm                617 ppm
#     日加权      max 5.79 $mn / 21 ppm                617 ppm
# 算术平均的噪声**盖过**了它要抓的最小信号，信噪比 < 1；日加权约 29×。
# 最干净的一刀是闰年季 2020-Q1（2 月只有 29 天）：算术平均差 −289 $mn，日加权差 −0.35 $mn。
# 派工单给的参照（2026-Q2 算术平均 445.00 vs 季报 444.982，差 0.018 $bn）两种口径都过
# （日加权 444.967，差 −0.015），所以那组数**分不出**高下，不能拿它当选型依据。
# 下一个想把它改回算术平均的人：先把上面这张表复算一遍。
_IEA_CHECK_FROM = (2018, 4)         # 从 2018-Q4 起核。更早**不是**不能核，是官方自己对不上：
# 2013-Q4…2018-Q3 共 20 季的日加权残差全是同号正偏（中位 +94 $mn、最大 +214 / 1484 ppm），
# 而月度与季度取自**同一份申报**，排除了解析错/重述/单位错三种可能 —— 只能是那一代官方
# 自己的口径或舍入差。2018-Q4 起残差塌到 ≤ 5.79 $mn（21 ppm），分界干净，所以窗口定在这里。
# 把窗口往左挪的人：挪之前先看这一段，别把官方自己的偏差当成本模块的 bug 去「修」。
_IEA_CHECK_SKIP = {
    (2020, 4): 'TD Ameritrade 并表 2020-10-06 落在季中，月度日均与季度日均不是同一个口径'
               '（残差 +941 $mn / 2033 ppm，全样本唯一越过硬闸的正常季）'
               '—— 与 build/schw.py 的 BRK_Q_TDA 是同一个断点',
    (2025, 1): 'fee_rates.csv 存的是**原报值**，而 2025-Q1…Q3 的原报发生在 2025-12 那次口径变更'
               '之前（旧基），本表的月度值取自变更后的滚动表（新基）—— 两边不是同一个口径',
    (2025, 2): '同上（旧基原报 422,729，重述后 421,845；新基月度日加权 421,832）',
    (2025, 3): '同上（旧基原报 419,780；新基月度日加权 416,937，差 −6,775 ppm，纯假警报）',
}
# 容差两级，都是「绝对下限 + 相对」取大者，同 backfill() 里 max(0.05, |cur|*1e-6) 的写法。
# 硬闸 1000 ppm：纳入窗口内实测最大残差 375 ppm（2019-Q2），留 2.7× 余量；同时低于
#   62 个「整体错位一格」场景里 60 个的信号强度（p5 = 2139 ppm），单位错档、口径混基、
#   TDA 式结构断点全部在这一档之外。绝对下限 120 $mn 只在季均 < 120,000 $mn 时才生效
#   （≈2013 年那一段，本来就在窗口外），留着是防窗口哪天左移时相对腿塌成个位数。
# 软闸 150 ppm：窗口内「正常」季的残差 ≤ 21 ppm（p95 = 1.6 ppm），留 7× 余量；
#   三个已知的官方毛刺（2019-Q2 375 / 2024-Q2 293 / 2019-Q3 167 ppm）正好落在软硬之间 ——
#   它们月度季度同源同文件、无重述、无单位切换，是官方自身的不一致（旁证：2Q24 那份
#   EX-99.1 自己印的 Q1+Q2 均值 427,833 与同页的 H1-2024 428,020 也差 187），
#   29 个在窗口内的季度里出现 3 次，做成硬失败会每年误报一两次，人很快学会无视。
# 绝对下限 30 $mn：2026 起月报只印到 0.1 $bn，单月半档 50 $mn，三月同向偏最坏使加权均偏
#   50 $mn（实测 2026-Q1 3.9、2026-Q2 15.0）；季均 ≈445,000 时相对腿给出 66.8 $mn 已罩住它。
#   **要把软闸改成硬闸的人：绝对下限必须 ≥ 60 $mn，否则 2026 起每季都被印刷精度顶穿。**
_IEA_HARD = (120.0, 0.0010)
_IEA_SOFT = (30.0, 0.00015)


def _fee_rates_iea(series_dir: str) -> dict:
    """series/fee_rates.csv 里 SCHW 的季度平均生息资产 → {(y, q): USD_mn}。

    取不到就返回 {}（调用方只喊不抛）：这道自检的判官是**另一条腿**，判官不在场时
    不能反过来把数据摄入判死 —— 与 _crosscheck_due_month 的「判官哑了只喊不抛」同一条规矩。
    """
    path = os.path.join(series_dir, 'fee_rates.csv')
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, newline='') as f:
        for row in csv.DictReader(f):
            if row.get('company') != 'SCHW' or row.get('metric') != 'avg_interest_earning_assets':
                continue
            if row.get('unit') != 'USD_mn':          # 单位名变了就别猜，当判官不在场
                return {}
            m = re.fullmatch(r'(20\d{2})-Q([1-4])', (row.get('period') or '').strip())
            if m:
                out[(int(m.group(1)), int(m.group(2)))] = float(row['value'])
    return out


def _crosscheck_quarter_iea(body: list, series_dir: str, log) -> None:
    """月度平均生息资产按日历日加权折成季均，与季度腿逐季对账。见上方那一大段。"""
    col = 'avg_interest_earning_assets_usdbn'
    q_ref = _fee_rates_iea(series_dir)
    if not q_ref:
        log('  [恒等式2] 跳过：series/fee_rates.csv 里取不到 SCHW 的季度平均生息资产'
            '（判官不在场，只喊不抛）')
        return
    i = 1 + COLS.index(col)
    mon = {}
    for r in body:
        if r[i] != '':
            mon[(int(r[0][:4]), int(r[0][5:]))] = float(r[i])

    hard, soft, n = [], [], 0
    for (y, q), ref in sorted(q_ref.items()):
        if (y, q) < _IEA_CHECK_FROM or (y, q) in _IEA_CHECK_SKIP:
            continue
        yms = [(y, (q - 1) * 3 + k) for k in (1, 2, 3)]
        if any(ym not in mon for ym in yms):
            continue                      # 缺月一律跳过，缺值不当失败（同本模块其它几道）
        days = [_month_end(ym).day for ym in yms]
        got = sum(d * mon[ym] for d, ym in zip(days, yms)) / sum(days) * 1_000  # $bn → $mn
        d = abs(got - ref)
        n += 1
        if d > max(_IEA_HARD[0], _IEA_HARD[1] * ref):
            hard.append((f'{y}-Q{q}', round(got, 1), ref, round(d / ref * 1e6)))
        elif d > max(_IEA_SOFT[0], _IEA_SOFT[1] * ref):
            soft.append((f'{y}-Q{q}', round(got, 1), ref, round(d / ref * 1e6)))
    log(f'  [恒等式2] 月度日加权季均 vs fee_rates 季度腿：核了 {n} 个季度，'
        f'超硬闸 {len(hard)} 个、超软闸 {len(soft)} 个'
        + (f'（跳过 {len(_IEA_CHECK_SKIP)} 个已记名的断点季）' if n else ''))
    for x in soft:
        log(f'    [软闸] {x[0]} 月度折算 {x[1]} vs 季报 {x[2]} $mn，差 {x[3]} ppm —— '
            '官方自身的不一致，记一笔，不拦')
    if hard:
        for x in hard[:10]:
            log(f'    MISMATCH {x[0]} 月度折算 {x[1]} vs 季报 {x[2]} $mn，差 {x[3]} ppm')
        raise FetchError(
            f'月度平均生息资产折成季均，与 series/fee_rates.csv 的季度腿有 {len(hard)} 个季度'
            f'超硬闸（{_IEA_HARD[1] * 1e6:.0f} ppm），拒绝写入。三种可能：月度行取错了'
            '（老版式标签行没有数、值在下面那行单位说明行上，见 _row_values 的 unit_row）、'
            '单位倍率判错了一档（_SELF_CANDS 那三档相差 1e3/1e6），'
            '或者官方又做了一次追溯重述而两条腿不同步（那就往 _IEA_CHECK_SKIP 里记名并写清理由）。'
            '三种都得人去看，绝不静默取其一。')


def backfill_columns(series_dir, cache_dir, cols=_NEW_COLS,
                     dry_run: bool = False, verbose: bool = True) -> dict:
    """把 cols 里的列补进 series/schw.csv 已有的行。返回 {列: 填了几格}。"""
    log = (lambda *a: print(*a)) if verbose else (lambda *a: None)
    path = os.path.join(series_dir, SERIES)
    with open(path, newline='') as f:
        rows = list(csv.reader(f))
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]

    # ── 表头迁移：老表没有这几列，按 COLS 的顺序在每一行末尾补空格 ──
    old_header = ['month'] + [c for c in COLS if c not in cols]
    if header == ['month'] + COLS:
        pass
    elif header == old_header:
        log(f'  [迁移] 表头补 {len(cols)} 列：{", ".join(cols)}')
        header = ['month'] + COLS
        body = [r + [''] * len(cols) for r in body]
    else:
        raise FetchError(f'{SERIES} 列名与预期不符：{header}')
    want = {r[0] for r in body}

    # ── 采集 ──
    merged: dict[tuple[int, int], dict] = {}
    # 逐格记出处（不是逐月）：同一个月的三列可能来自不同的源，记成逐月会把落败方的
    # 出处安到别的列头上，那种日志比没有更坏。
    prov: dict[tuple[tuple[int, int], str], str] = {}
    RESTATEMENTS.clear()

    def absorb(got: dict, src: str):
        for ym, vals in got.items():
            keep = {c: v for c, v in vals.items() if c in cols}
            if not keep:
                continue
            # 先写者胜。**赢家由 _col_sources() 的排序决定，那个排序就是口径**，
            # 判据见那个函数的 docstring 与口径坑第 8 条，不要在这里改规矩。
            # 落败的值不能吞掉：它要么是官方重述、要么是我们取错行，两者都得有人看见。
            # （_collect() 与 backfill() 的 absorb 一直都在记，只有这一条路以前没记，
            #   于是 2023 年那次官方重述在 2026-08-19 入库时一行日志都没有。）
            merged.setdefault(ym, {})
            for c, v in keep.items():
                if c not in merged[ym]:
                    merged[ym][c], prov[(ym, c)] = v, src
                elif _differs(c, merged[ym][c], v):
                    COLRESTATEMENTS.append((ym, c, merged[ym][c], v,
                                            prov[(ym, c)], src))

    def need() -> set:
        return {k for k in want
                if any(c not in merged.get(tuple(int(x) for x in k.split('-')), {})
                       for c in cols)}

    seen = set()
    for ym, url in _col_sources(cache_dir):
        name = url.rsplit('/', 1)[-1]
        if name in seen:
            continue
        seen.add(name)
        try:
            fp = _download(url, cache_dir)
        except FetchError as e:
            log(f'  [cdn] {name} 取不到：{e}')
            continue
        if fp is None:
            # 404。**必须说话**：这里同时盖着两种事 ——「当季季报还没发/季末月本来就没有
            # 月报」（正常，_col_sources 里今天就有一份：当季的 schw_q<n>_<年>）与「本该
            # 存在的历史附表被撤下或改名」（故障）。原先这一支一行日志都没有，于是两者在
            # 日志里完全同形，README §5.5 那句判据「失败十天和成功十天日志一样吗」答案是
            # 「一样」。措辞沿用 backfill() 里的同类分支。
            log(f'  [cdn] {name} 取不到（404）—— 已落盘的历史行不受影响')
            continue
        try:
            absorb(parse_table(fp, ym), name)
        except FetchError as e:
            log(f'  [cdn] {name} 解析失败：{e}')
            continue
        log(f'  [cdn] {name} ok')

    # ── 先吃本地已有的 EX-99.1：季频腿与 fetch/rates_schw.py 抓下来的那批就落在
    # cache/schw_rates/，是**同一批文件**（模块 docstring「落盘」那一节写着两条腿共用）。
    # 它们能盖住 2013-09 至今的每一个月，而下面那条网络 EDGAR 腿要先拉 submissions
    # 清单、再逐份 index.json + 逐个 .htm 试解析，几百个请求。本地有现成的还去打几百个
    # 请求，既慢又会撞 SEC 的速率限制（10 req/s），而撞上之后的 403 会被那条路
    # `except Exception: continue` 静默吞掉 —— 于是「回填不全」看上去就像「源里没有」。
    rates_dir = os.path.join(cache_dir, 'schw_rates')
    if need() and os.path.isdir(rates_dir):
        n0 = len(need())
        for name in sorted(os.listdir(rates_dir), reverse=True):
            if not name.lower().endswith(('.htm', '.html')):
                continue
            try:
                with open(os.path.join(rates_dir, name), encoding='utf-8',
                          errors='replace') as f:
                    got = parse_edgar_monthly(f.read())
            except FetchError as e:
                log(f'  [本地edgar] {name} 解析失败：{e}')
                continue
            if got:
                absorb(got, f'cache/schw_rates/{name}')
        log(f'  [本地edgar] 扫 cache/schw_rates/，还缺的月份 {n0} → {len(need())}')

    # ── EDGAR：CDN 上 2015-09 之前一份都不剩，只能走 8-K 的 EX-99.1 ──
    # 按**从新到旧**走，每份只解析到「还缺的月份都齐了」为止就停 —— 全量扫 160 份
    # 8-K 要几百个请求，而这里真正缺的只有 2013-09…2015-08 那二十来个月。
    if need():
        try:
            fils = sorted(_edgar_8k('2016-06-01'), reverse=True)
        except Exception as e:
            log(f'  [edgar] 清单取不到（{type(e).__name__}: {e}）')
            fils = []
        for date, acc in fils:
            if not need():
                break
            base = EDGAR_DIR.format(acc=acc.replace('-', ''))
            try:
                idx = json.loads(_edgar_get(base + '/index.json'))
            except Exception:
                continue
            _time.sleep(0.15)
            docs = [it['name'] for it in idx['directory']['item']
                    if it['name'].lower().endswith(('.htm', '.html'))]
            for d in docs:
                try:
                    html = _edgar_get(f'{base}/{d}').decode('utf-8', 'replace')
                except Exception:
                    continue
                _time.sleep(0.15)
                got = parse_edgar_monthly(html)
                if got:
                    absorb(got, f'EDGAR {acc}/{d}')
                    log(f'  [edgar] {date} {d} → {min(got)}…{max(got)}')
                    break

    # ── 对账：已有的非空格子必须逐值相等（重跑幂等；不等说明解析取错了行）──
    idx_of = {c: 1 + COLS.index(c) for c in cols}
    clash, checked, filled = [], 0, {c: 0 for c in cols}
    for r in body:
        ym = tuple(int(x) for x in r[0].split('-'))
        vals = merged.get(ym, {})
        for c in cols:
            v = vals.get(c)
            if v is None:
                continue
            cur = r[idx_of[c]]
            if cur != '':
                checked += 1
                if cur != _fmt(c, v):
                    clash.append((r[0], c, cur, _fmt(c, v)))
                continue
            r[idx_of[c]] = _fmt(c, v)
            filled[c] += 1
    log(f'  [对账] 重叠 {checked} 个 (月,指标)，不符 {len(clash)} 个')
    if clash:
        for x in clash[:20]:
            log('    MISMATCH', x)
        raise FetchError(f'列回填与仓里现有值有 {len(clash)} 处不符，拒绝写入。')

    # ── 恒等式自检：(sweep + MMF) / 客户资产 应当复现官方自己印的占比 ──
    # 三个数都是官方同一张表上印的，这一步不是「算出」占比，是**核对**我们把三行
    # 各自取对了没有。容差 0.07pp：占比印到 0.1pp、两个分量各印到 0.1bn。
    # 下标一律按 COLS 取，**不要**走 idx_of —— idx_of 只含本次要填的 cols，
    # `idx_of.get('sweep_cash_usdbn', 0)` 在 cols 不含该列时会退化成 0，取到的是 month
    # 那一格（'2013-09'），既过不了 `'' in (...)` 那道跳过，又会在 float() 上炸。
    # 这四列都是 COLS 的常驻成员，跟本次填哪几列无关。2026-09-16 把 _NEW_COLS 换成
    # 别的列时才暴露出来。
    isw, imm, ipc = (1 + COLS.index(c) for c in
                     ('sweep_cash_usdbn', 'mmf_usdbn', 'client_cash_pct'))
    ia = 1 + COLS.index('total_client_assets_usdbn')
    bad, cash_n = [], 0
    for r in body:
        sw, mm, pc, ta = r[isw], r[imm], r[ipc], r[ia]
        if '' in (sw, mm, pc, ta):
            continue
        cash_n += 1
        d = abs((float(sw) + float(mm)) / float(ta) * 100 - float(pc))
        if d > 0.07:
            bad.append((r[0], round(d, 3)))
    log(f'  [恒等式] (sweep+MMF)/资产 vs 官方占比：核了 {cash_n} 个月，超差 {len(bad)} 个')
    if bad:
        raise FetchError(f'(sweep+MMF)/资产 与官方印的客户现金占比对不上：{bad[:10]}')

    # ── 恒等式自检 2：月度平均生息资产按季折算，应复现季报腿印的季均 ──
    _crosscheck_quarter_iea(body, series_dir, log)

    log('  [填充] ' + '、'.join(f'{c} {n} 格' for c, n in filled.items()))
    keys = [r[0] for r in body]
    for c in cols:
        miss = sorted(k for k in want if not body[keys.index(k)][idx_of[c]])
        if miss:
            log(f'  [仍缺] {c} 有 {len(miss)} 个月没填上：{miss[:6]}…{miss[-3:]}')
    if dry_run:
        log('  [dry-run] 不写盘')
        return filled
    if not any(filled.values()):
        return filled
    body.sort(key=lambda r: r[0])
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)
    os.replace(tmp, path)
    return filled



# ═════════════ 季频腿：Clients' DATs 与季末融资余额（series/schw_q.csv）═════════════
# 与上面三条月频入口（update / backfill / backfill_columns）的分工：
#   · 它们写 series/schw.csv，键是**月**，源是 content.schwab.com 的 xlsx（+ EDGAR 兜底）。
#   · 这一条写 series/schw_q.csv，键是**季**，源只有 SEC EDGAR 的季度业绩 8-K EX-99.1。
# 为什么必须另开一张 CSV 而不是往 schw.csv 加两列：两条序列的**时间轴不同**（季 vs 月），
# 塞进月度轴会造出每季 2 个空月，正好撞上 backfill() 那条「缺口会让下游 assets.diff()
# 把两个月的变动记到一个月上」。
#
# ============================== 口径 ==============================
# q_dats_k            季报附表 `Clients' Daily Average Trades` 的 **Total** 行，单位千笔/日。
#                     注意它是**该季的日均**，不是季末值，也不是月度 dats_k 的三月平均
#                     （官方按交易日加权，两者不会逐季相等，别拿来互相校验）。
# q_margin_eop_usdbn  `Growth in Client Assets and Accounts` 表里 `Margin loans outstanding`
#                     行，单位 $bn，**季末时点值**。
#
# ---------- 坑 1：DATs 有两种版式，取错会拿到「Revenue trades」那一行 ----------
# · 2019 及以前：`Clients' Daily Average Trades (in thousands)` 是**小标题行**（本行没有
#   数值），下面跟着 `Revenue trades` / `Asset-based trades` / `Other trades` / `Total`
#   四行 —— 要取 **Total**。取到小标题下面第一行会拿到 Revenue trades，那是 Total 的一个
#   零头（2017Q1：Revenue 305 vs Total 585），画出来是一条完全合理的曲线。
# · 2020Q1 起：塌成单行 `Clients' Daily Average Trades (DATs) (in thousands)`，值直接在
#   本行，下面没有明细。
# 所以判据不是版本号也不是行号，而是「本行能不能取出 5 个数值格」：能，就是新版式；
# 不能，本行只是小标题，往下找 `Total`（见 parse_edgar_quarterly）。
# 那次塌行官方**没给任何脚注**（同一期另新增了 `Number of Trading Days` 行），所以不能
# 指望源里有话告诉你版式换了。两种版式能直接接续是**逐值验过的**、不是假设：2020Q1 那份
# 单行版印的历史比较数逐字等于旧 Total —— Q4-19 785 / Q3-19 718 / Q2-19 716 / Q1-19 777。
#
# ---------- 坑 2：`Margin loans outstanding` 这个行名 ----------
# 一、**表里印成负数**（`(165.1)`）。它坐在「客户资产与账户增长」这张**流量口径**表里，
#     融资余额对客户净资产是减项，所以带会计负号 —— 数值本身没有符号含义，落盘取绝对值。
# 二、**这一行只含 margin loans，不含 short credits。** 本文件 2026-09-15 那版写反了
#     （原话：「行名写的是 loans，但 2026 起这一行的内容含负债端的 short credits」），
#     2026-09-16 逐项对账推翻。把订正链条留在这里，免得第三次又推回去：
#     · **推错的根因是月报脚注 (4) 被两行共用**：`Margin Balances at month end (4)` 与
#       `Transactional Sweep Cash (4,7)` 挂的是同一个 (4)，脚注正文的两个半句各归各行。
#       把整条 (4) 读给融资余额那一行，就会读出「含 short credits」这个假结论。
#     · short credits 归的是 sweep 那一行：脚注 (7) 明写 `Transactional sweep cash
#       includes … short credits related to certain client long/short strategies`。
#     · 2026Q2 逐项对账：季末 165.1 −（与客户 long/short 策略相关的）margin loans 42.1
#       = 123.0，与同期资产负债表 `Receivables from brokerage clients — net` 的 122.8
#       吻合；若照错版本再减掉 short credits 43.7，得 79.3，差一个数量级。
#     · 2Q26 新闻稿正文也单独写了 "Margin loan balances increased 30% quarter-over-quarter
#       to $165.1 billion"。
#     → 图注/页面文案不许把它写成「融出资金 / margin lending」，只能照抄官方行名
#       "Margin loans outstanding"；**也不许再写「含 short credits」**。真要提短仓贷记
#       余额，它在 sweep cash 那条里（月度腿的 sweep_cash_usdbn），不在这条里。
#     → 与月度腿的 margin_balances_usdbn（月报 "Margin Balances at month end"）是**同一个
#       口径**（期末 margin loans），实测 6 个重叠季末（2025-03…2026-06）逐值相等。
#       本模块仍不写「必须相等」的硬断言（两条出自不同表、不同发布节奏，季报是最终版而
#       月报不重述，官方也可能只改一边），但某季不等**是**要人看一眼的信号 —— 不能再拿
#       「本来就是两个口径」搪塞过去。
#
# ---------- 坑 3：表头行号不固定 ----------
# 每份申报给 **5 个季度**（本季 + 前 4 季），表头形如 `Q4-16 % change` / `Q2-26 % Change`
# （大小写官方自己都不统一）。它落在**第 1 行**还是**第 7 行**没有规律：2018Q1–2019Q2
# 那 6 份在第 7 行，其余在第 1 行。所以扫表的前 12 行，取第一个 `Q([1-4])-(\d{2})` 命中。
#
# ---------- 坑 4：% change 列有三种印法，所以不能按列位置取值 ----------
# `23%`（粘一起）/ 裸数 `46`（`%` 在独立单元格里，被 _q_cells 丢掉）/ 拆成 `(19` + `)%`
# 两格。三种印法在同一份文件里混着出现，按「第 N 列」取值必错位。判据换成
# **「本行末 5 个数字格」**：% change 永远排在 5 个季度值**前面**，取末 5 个就绕开了它。
#
# ================= 2020Q4 TD Ameritrade 并表：措辞红线 =================
# 并表当季就是 2020Q4（2020-10-06 完成），本腿两列在那一季都有台阶：季度 DATs 1460 → 5796
# （近 4 倍），季末融资余额 23.6 → 60.9。本腿**照官方原值入库、不做任何拼接调整**；
# 画不画断点是下游的事（build/schw.py 的 BRK_Q_TDA = 2020Q4，Exhibit 10/11）。
# 红线：**官方从来没有「前期不重述」这句明文**，别写成「官方明说不重述」。稿里用的是前瞻
# 纳入式措辞 —— "Results of operations and metrics are inclusive of TD Ameritrade beginning
# October 6, 2020."，并把 TDA 当成 Q4-20 的**流入**处理（那份稿自己的脚注 (5) 记 $890.7bn
# 资产流入、脚注 (7) 记 14.5mn 新开户；这套编号是季报稿的，与坑 2 里月报的 (4)/(7) 无关）。
# 同一份稿里真做了重述的三处都明写着 "Prior periods have been reclassified to reflect this
# change."，TDA 这两条**刻意没有**这句 —— 所以「前期未重述」是从这个反差**推**出来的结论
# （推得很稳，可以照此画断点），但它是推断、不是引文，写进图注时不许挂在官方名下。
#
# ============================== 窗口 ==============================
# CSV 从 **2016Q1** 起，按 README「全站窗口取 max(序列首月, 2016-01)，只往右让不往左借」。
# **源本身能到 2012Q4**（本机 50 份缓存实测 2012Q4 → 2026Q2 逐季无缺口），更早的 8-K
# EDGAR 上还有。窗口往左挪时**不需要改这里的解析**，只需要处理一件事：
#   2013–2014 年 Schwab 把 DATs 从一位小数改成整数千笔，于是同一个季度在新旧两份申报里
#   印成 497.2 与 497.0 —— 实测 2013Q2 / 2013Q3 / 2013Q4 / 2014Q1 四个季度有此冲突，
#   而 **2016Q1 起没有任何冲突**。挪窗口的人要先决定「同一季两个官方值取哪个」，
#   再把结论写进这里，而不是让 _q_conflicts 那道闸随便放行。
#
# ============================== 节奏 ==============================
# 季频腿**止于上一个已报季度**，所以它天生比月频腿短一到两个月：业绩 8-K 在季末后
# 2–3 周发（Q2-2026 是 7/21），而月频腿那时已经有季末月之后一两个月的数了。
# 举例：2026-09 中旬这一天，series/schw.csv 到 2026-08（月），series/schw_q.csv 到
# 2026Q2（= 2026-06）。**这不是掉期**，别拿两张表的末行去互相判新鲜度。
#
# ============================== 三条铁律 ==============================
# 与 backfill() 那三条逐字相同，因为坏法也相同：
#   1. **已存在的季度一个字符都不改**（_q_merge_into_csv 只往 body 里 append）；
#   2. **重叠季必须逐值相等**：相邻申报重叠 4 个季度，不等就**整次失败**，要人去看是
#      解析取错了行还是官方重述了 —— 绝不静默取其一（窗口外的冲突记进 QRESTATEMENTS
#      并打印，不落盘所以不拦；见「窗口」那一段）；
#   3. **回填后季度必须仍逐季连号**：缺口会让下游把两个季度的变动记到一个季度上。
#
# ============================== 落盘与缓存 ==============================
# 下载走本文件已有的 _edgar_get（UA 带邮箱是 EDGAR 明文条款，不是反爬），落
# cache/schw_rates/，**文件名与 fetch/rates_schw.py 完全一致**（accession 前缀 + 原名）：
# 两条腿读的是同一批 EX-99.1 正文（1MB 级），共用一份缓存就不必各下一遍。
# 前缀不能省 —— 官方老申报里一堆同名的 dex991.htm，不加前缀会互相覆盖
# （fetch/rates_schw.py 的落盘那一节记过：2010-2011 五个季度全被覆盖成同一份）。
SERIES_Q = 'schw_q.csv'
QCOLS = ['q_dats_k', 'q_margin_eop_usdbn']

# 窗口左端（见上方「窗口」）。改它之前先读那一段。
_Q_FROM = (2016, 1)

# 回溯到哪一份申报为止。与 fetch/rates_schw.py 的 EARLIEST_FILING_DATE 同值同理由：
# 2014-01-16 起（= 2013Q4）每一份都实测解析通过；更早的版式没有逐份核对过，
# 不纳入无人值守路径。窗口左端 2016Q1 只需要 2016-01 那份，留两年余量是为了
# 让重叠对账有足够样本 —— 那是这条路唯一的自检。
_Q_EARLIEST_FILING = '2014-01-01'
_Q_CACHE_SUBDIR = 'schw_rates'

# 合理量级断言：同月频那两列共用一套上下界，理由见 _SANE 上方那段（为的是官方换单位
# 或版式错位时立刻炸，而不是静默算错）。
_Q_SANE = {
    'q_dats_k': _SANE['dats_k'],                       # 千笔/日
    'q_margin_eop_usdbn': _SANE['margin_balances_usdbn'],   # $bn
}

# 行标签。DATs 用正则是因为撇号有两种（ASCII ' 与 U+2019 ’，官方两种都用过）；
# 尾部还挂着 "(in thousands)" / "(DATs) (in thousands)"，所以是前缀匹配不是全等。
_Q_DAT_RE = re.compile(r"clients[’']\s*daily average trades")
_Q_MARGIN_PREFIX = 'margin loans outstanding'
_Q_TOTAL_LABEL = 'total'
# 表头 `Q4-16 % change`。只认 `Q<1-4>-<两位年>`，两种大小写都过。
_Q_HDR_RE = re.compile(r'\bQ([1-4])-(\d{2})\b')
# 数字格。故意收得宽（允许 `(19` 这种被拆开的半截 % change）—— 真正把 % change 挡在
# 外面的是「取末 5 个」那一步，不是这条正则（见坑 4）。
_Q_NUM_RE = re.compile(r'^\(?\$?-?[\d,]+\.?\d*\)?$')
_Q_HDR_SCAN_ROWS = 12

# 上一次 _collect_quarterly 发现的、**窗口外**的跨申报数值打架（窗口内一律抛）。
# 每条 ((y, q), 列名, {文件: 值}) —— 目前已知的全部四条就是 2013–2014 那次小数位变更。
QRESTATEMENTS: list = []


class _QFetchOffline(FetchError):
    """offline=True 时缺缓存文件。单独一个类型，免得被当成「EDGAR 挂了」。"""


# ── HTML 表格（与 fetch/rates_schw.py 的 _table_rows 同一套写法）─────────────
# 不用 BeautifulSoup：bs4 不在 requirements.txt 里（全仓只有 fetch/tmx.py 依赖它），
# 而这批文件实测**没有嵌套 <table>**（50 份缓存全扫过，最大嵌套深度 1、开闭标签数相等），
# 所以非贪婪切表是安全的。若哪天官方改用嵌套表格，切出来的行会缺，parse 返回 {}，
# _collect_quarterly 会点名那份文件抛错 —— 不会静默少几个季度。
def _q_cells(tr_html: str) -> list[str]:
    """一行 <tr> → 非空单元格文本。

    丢掉 ''、'$'、'%' 三种噪音格：官方把货币符号和百分号各放进独立 <td>，留着它们会让
    「末 5 个数字格」那条规则要多绕一层。**不要在这里丢 ')%'**：它是 `(19` + `)%` 那种
    拆开印法的后半截，_Q_NUM_RE 本来就不认它，留着反而是一条「这行有 % change」的线索。
    """
    out = []
    for td in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr_html, re.S | re.I):
        v = _unescape(re.sub(r'<[^>]+>', ' ', td)).replace('﻿', '').replace('\xa0', ' ')
        v = re.sub(r'\s+', ' ', v).strip()
        if v not in ('', '$', '%'):
            out.append(v)
    return out


def _q_tables(html: str) -> list[str]:
    return re.findall(r'<table.*?</table>', html, re.S | re.I)


def _q_rows(table_html: str) -> list[list[str]]:
    return [_q_cells(tr) for tr in re.findall(r'<tr.*?</tr>', table_html, re.S | re.I)]


def _q_flat(table_html: str) -> str:
    return re.sub(r'\s+', ' ', _unescape(re.sub(r'<[^>]+>', ' ', table_html)))


def _q_num(s: str):
    """'11,920' → 11920.0；'(165.1)' → -165.1；'—'/'-' → None。

    与 _html_num 的差别只有一处：这里**不剥尾部的 '%'**。月频那条路要剥，是因为 _glue
    会把独立 <td> 里的百分号粘回数值；这条路不粘（见 _q_cells），% change 靠「取末 5 个」
    甩开，所以带 % 的格一律不该被当成数字格 —— 剥了反而会把 % change 混进候选。
    """
    neg = s.startswith('(') and s.endswith(')')
    t = s.strip('()$').replace(',', '')
    if not t or t in ('-', '—', '–'):
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _q_last5(cells: list[str]) -> list[str] | None:
    """本行末 5 个数字格 = 5 个季度值（本季 + 前 4 季）。不足 5 个返回 None。

    为什么是「末 5 个」而不是「第 k 列」：见坑 4。
    """
    nums = [c for c in cells[1:] if _Q_NUM_RE.fullmatch(c)]
    return nums[-5:] if len(nums) >= 5 else None


def _q_header(rows: list[list[str]]):
    """从 `Q4-16 % change` 这种表头取本期季度 → (year, quarter)；没有返回 None。"""
    for r in rows[:_Q_HDR_SCAN_ROWS]:
        for c in r:
            m = _Q_HDR_RE.search(c)
            if m:
                return 2000 + int(m.group(2)), int(m.group(1))
    return None


def _q_prev(y: int, q: int, k: int) -> tuple[int, int]:
    """(y, q) 往前 k 个季度。"""
    i = y * 4 + (q - 1) - k
    return i // 4, i % 4 + 1


def _q_spread(vals: list[str], y: int, q: int, col: str, out: dict) -> None:
    """把一行的 5 个季度值按「最左 = 本季、往右倒推」摊进 out。"""
    for k, raw in enumerate(vals):
        n = _q_num(raw)
        if n is None:
            continue
        if col == 'q_margin_eop_usdbn':
            n = abs(n)                      # 会计负号，见坑 2 第一条
        lo, hi = _Q_SANE[col]
        if not (lo <= n <= hi):
            raise FetchError(f'{y}Q{q} 往前第 {k} 季 {col}={n} 超出合理区间 ({lo}, {hi})')
        out.setdefault(_q_prev(y, q, k), {})[col] = n


def parse_edgar_quarterly(html: str) -> dict:
    """季度业绩 8-K EX-99.1 → {(y, q): {col: 值}}；不是这种文件返回 {}。

    一份申报给 5 个季度。两张表（DATs 那张、客户资产增长那张）在不同年份的版面里有时是
    同一张、有时分开，所以这里对**每一张**含目标行的表各自读表头、各自摊值，不假设它们
    共用一个表头。
    """
    out: dict = {}
    for tb in _q_tables(html):
        flat = _q_flat(tb)
        has_dat = 'Daily Average Trades' in flat
        has_mar = 'Margin loans outstanding' in flat
        if not (has_dat or has_mar):
            continue
        rows = _q_rows(tb)
        hq = _q_header(rows)
        if not hq:                      # 没有 Q<n>-<yy> 表头 → 不是那张 5 季对比表
            continue
        y, q = hq
        if has_dat:
            subtitle = False
            for cells in rows:
                if not cells:
                    continue
                lab = cells[0]
                if _Q_DAT_RE.match(lab.lower()):
                    vals = _q_last5(cells)
                    if vals:            # 2020Q1 起的单行版式：值就在本行
                        _q_spread(vals, y, q, 'q_dats_k', out)
                        subtitle = False
                        break
                    subtitle = True     # 老版式：本行只是小标题，往下找 Total
                    continue
                if subtitle and lab.strip().lower() == _Q_TOTAL_LABEL:
                    vals = _q_last5(cells)
                    if vals:
                        _q_spread(vals, y, q, 'q_dats_k', out)
                    break
        if has_mar:
            for cells in rows:
                if cells and cells[0].strip().lower().startswith(_Q_MARGIN_PREFIX):
                    vals = _q_last5(cells)
                    if vals:
                        _q_spread(vals, y, q, 'q_margin_eop_usdbn', out)
                    break
    return out


# ── EDGAR：季度业绩 8-K（item 2.02）────────────────────────────────────
def _q_cache(cache_dir: str, name: str) -> str:
    d = os.path.join(cache_dir, _Q_CACHE_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def _q_fetch(url: str, cache_dir: str, name: str,
             immutable: bool = True, offline: bool = False) -> bytes:
    """取一份 EDGAR 文件，落 cache/schw_rates/<name>。

    immutable=True 走缓存（Archives 里的历史申报永不变）；申报清单每天在变，传 False。
    offline=True 时**只读缓存**，缺文件就抛 _QFetchOffline —— 这是给「可复现性验收」用的
    显式开关（照着本地那 50 份重放一遍，逐字节比对 CSV），**不是**网络失败时的静默兜底。
    """
    p = _q_cache(cache_dir, name)
    if (immutable or offline) and os.path.exists(p) and os.path.getsize(p) > 200:
        with open(p, 'rb') as f:
            return f.read()
    if offline:
        raise _QFetchOffline(
            f'offline=True 但 cache/{_Q_CACHE_SUBDIR}/{name} 不在本地 —— '
            f'离线重放要求这一份已经缓存过，不会去拉 {url}')
    blob = _edgar_get(url)
    _time.sleep(0.15)                    # EDGAR 限速，与 backfill() 里那两处同一节拍
    with open(p, 'wb') as f:
        f.write(blob)
    return blob


def _q_earnings_8k(cache_dir: str, since: str = _Q_EARLIEST_FILING,
                   offline: bool = False) -> list[dict]:
    """季度业绩 8-K 清单，**新 → 旧**。→ [{'accession','date','primary'}, ...]

    只认 form='8-K' 且 items 含 '2.02'（Results of Operations）。这一条与 _edgar_8k()
    的差别就在 items 上：那个是「所有 8-K」，因为月度活动报告可以挂在任何一期后面；
    这里要的是**业绩稿**，而业绩稿一定带 2.02，用它筛掉四分之三的请求。
    历史分片文件名从 recent.files[] 里读，不硬编码（与 fetch/rates_schw.py 同规矩）。
    """
    top = json.loads(_q_fetch(EDGAR_SUB.format(cik=EDGAR_CIK), cache_dir,
                              'submissions.json', immutable=False, offline=offline))
    blocks = [top['filings']['recent']]
    for f in top['filings'].get('files', []):
        if f.get('filingTo', '9999') < since:      # 早到不需要就别下
            continue
        blocks.append(json.loads(_q_fetch(
            'https://data.sec.gov/submissions/' + f['name'], cache_dir, f['name'],
            offline=offline)))
    out = []
    for b in blocks:
        for i in range(len(b['form'])):
            if b['form'][i] != '8-K':
                continue
            if '2.02' not in (b['items'][i] or ''):
                continue
            if b['filingDate'][i] < since:
                continue
            out.append({'accession': b['accessionNumber'][i],
                        'date': b['filingDate'][i],
                        'primary': (b.get('primaryDocument') or [''] * (i + 1))[i]})
    if not out:
        raise FetchError('EDGAR 上没找到任何 item 2.02 的 8-K，CIK 或 API 形态可能变了')
    out.sort(key=lambda r: (r['date'], r['accession']), reverse=True)
    return out


def _q_exhibit(cache_dir: str, f: dict, offline: bool = False) -> tuple[str, str]:
    """挑出业绩新闻稿正文（Ex-99.1）→ (本地取到的 html, 它的 URL)。

    不按文件名猜（官方 10 年换了 5 种写法：exhibit991.htm / a2q26exhibit991.htm /
    schw-20161017xex99_1.htm / d758923dex991.htm …），按「排除法 + 体积」挑：去掉索引页、
    XBRL 渲染出来的 R*.htm、8-K 壳（primaryDocument），剩下的 .htm 里最大的那个。
    挑错了不会静默：_collect_quarterly 解析不出 5 个季度就点名抛。
    """
    accn = f['accession'].replace('-', '')
    base = EDGAR_DIR.format(acc=accn)
    idx = json.loads(_q_fetch(base + '/index.json', cache_dir, f'{accn}_index.json',
                              offline=offline))
    best, best_size = None, -1
    for item in idx['directory']['item']:
        name = item['name']
        low = name.lower()
        if not low.endswith(('.htm', '.html')):
            continue
        if 'index' in low or re.fullmatch(r'r\d+\.htm', low) or low == (f['primary'] or '').lower():
            continue
        try:
            size = int(item.get('size') or 0)
        except (TypeError, ValueError):
            size = 0
        if size > best_size:
            best, best_size = name, size
    if best is None:
        raise FetchError(f'{f["accession"]}: index.json 里没有可用的 htm 附件')
    url = f'{base}/{best}'
    html = _q_fetch(url, cache_dir, f'{accn}_{best}', offline=offline).decode('utf-8', 'replace')
    return html, url


def _collect_quarterly(cache_dir: str, filings: list, offline: bool = False,
                       verbose: bool = True) -> dict:
    """下载 + 解析给定的几份业绩 8-K，合并成 {(y, q): {col: val}}。

    **重叠季逐值相等**这道闸就在这里：相邻申报重叠 4 个季度，同一格来自几份文件时必须
    印成同一个字符串（按落盘精度比，理由同 _differs 的 docstring）。窗口内不等 → 整次
    失败；窗口外不等 → 记进 QRESTATEMENTS 并打印，取**最新那份申报**的值（它不落盘，
    所以取谁都不改变 CSV；记下来是为了窗口往左挪的人能一眼看见 2013–2014 那次小数位变更）。
    """
    def log(*a):
        if verbose:
            print(*a)

    QRESTATEMENTS.clear()
    seen: dict = {}                     # (y, q, col) -> {文件名: 值}，按 filings 的顺序写入
    for f in filings:
        html, url = _q_exhibit(cache_dir, f, offline=offline)
        name = url.rsplit('/', 1)[-1]
        got = parse_edgar_quarterly(html)
        if not got:
            raise FetchError(
                f'{f["date"]} {f["accession"]} ({name}) 里读不出季度 DATs / 融资余额表。'
                f'「解析器读不到」和「源里没有」长得一模一样（本文件 docstring 的 EDGAR 那段记过'
                f'同一个坑），所以这里拒绝静默跳过：请人工打开这份 EX-99.1 核对版式。')
        for qk, vals in got.items():
            for c, v in vals.items():
                seen.setdefault((qk, c), {})[name] = v
        log(f'  [q-edgar] {f["date"]} {name} → {min(got)}…{max(got)}')

    merged: dict = {}
    clash = []
    for (qk, c), by_file in sorted(seen.items()):
        pick = next(iter(by_file.values()))          # filings 是新→旧，第一份 = 最新
        if len({_qfmt(v) for v in by_file.values()}) > 1:
            if qk >= _Q_FROM:
                clash.append((qk, c, by_file))
            else:
                QRESTATEMENTS.append((qk, c, dict(by_file)))
        merged.setdefault(qk, {})[c] = pick
    if clash:
        for qk, c, by_file in clash[:10]:
            log(f'    MISMATCH {qk[0]}Q{qk[1]} {c}: '
                + '、'.join(f'{k}={v:g}' for k, v in by_file.items()))
        raise FetchError(
            f'窗口内有 {len(clash)} 处重叠季不等，拒绝写入。相邻申报重叠 4 个季度，'
            f'同一季必须逐值相等 —— 不等只有两种可能：解析取错了行，或者官方重述过。'
            f'两种都得人去看，绝不静默取其一。')
    if QRESTATEMENTS:
        log(f'  [q-窗口外重述] {len(QRESTATEMENTS)} 处（不落盘，仅记录）：'
            + '、'.join(f'{k[0]}Q{k[1]} {c}' for k, c, _ in QRESTATEMENTS[:6]))
    return merged


# ── 落盘 ───────────────────────────────────────────────────────────────
def _qfmt(v) -> str:
    """落盘格式：`%g`。

    这是 series/schw_q.csv 现有 42 行的写法（81 不是 81.0、616 不是 616.0），换成别的
    写法会让整表在 git diff 里一起翻新，真正的那一行新增被淹掉。
    与月频的 _fmt() 不同是刻意的：_fmt 把 dats_k 取整、把金额钉死一位小数，而这条腿
    2013–2014 的 DATs 带一位小数（见「窗口」那一段），取整会静默吞掉小数位变更这条线索。
    """
    return '' if v is None else f'{v:g}'


def _q_key(y: int, q: int) -> str:
    return f'{y}Q{q}'


def _q_parse_key(s: str) -> tuple[int, int]:
    return int(s[:4]), int(s[5:])


def _q_read(series_dir: str):
    path = os.path.join(series_dir, SERIES_Q)
    with open(path, newline='') as f:
        rows = list(csv.reader(f))
    if not rows:
        raise FetchError(f'{SERIES_Q} 是空文件')
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    if header != ['quarter'] + QCOLS:
        raise FetchError(f'{SERIES_Q} 列名与预期不符：{header}')
    return path, header, body


def _q_merge_into_csv(series_dir: str, merged: dict, verbose: bool = True) -> list:
    """把 merged 并进 series/schw_q.csv，返回新增季度 ['YYYYQn', ...]。

    三条铁律都在这里执行（见本节开头）：已有季度一个字符不改、重叠季逐值相等、
    写完必须逐季连号。没有新增时**一个字节都不写**（幂等，git 里看不到任何动静）。
    """
    def log(*a):
        if verbose:
            print(*a)

    path, header, body = _q_read(series_dir)
    have = {r[0]: r for r in body}

    # ── 铁律 2（对既有 CSV 的那一半）：重叠季必须逐值相等 ──
    clash, checked = [], 0
    for qk in sorted(merged):
        key = _q_key(*qk)
        if key not in have:
            continue
        for c, v in merged[qk].items():
            cur = have[key][1 + QCOLS.index(c)]
            if cur == '':
                continue
            checked += 1
            if cur != _qfmt(v):
                clash.append((key, c, cur, _qfmt(v)))
    log(f'  [q-对账] 重叠 {checked} 个 (季,指标)，不符 {len(clash)} 个')
    if clash:
        for x in clash[:20]:
            log('    MISMATCH', x)
        raise FetchError(f'解析结果与 series/{SERIES_Q} 现有值有 {len(clash)} 处不符，拒绝写入。'
                         '要么解析取错了行，要么官方重述过 —— 两种都得人去看。')

    # ── 追加 ──
    added = []
    for qk in sorted(merged):
        if qk < _Q_FROM:                 # 窗口外：源里有、但本站不画（见「窗口」）
            continue
        key = _q_key(*qk)
        if key in have:                  # 铁律 1：已存在的季度一个字符都不改
            continue
        missing = [c for c in QCOLS if merged[qk].get(c) is None]
        if missing:
            raise FetchError(f'{key} 解析结果缺列 {missing}，拒绝写入（不写 NaN）。'
                             '两列印在同一份申报的两张表里，缺一列就是版式变了。')
        body.append([key] + [_qfmt(merged[qk][c]) for c in QCOLS])
        added.append(key)

    if not added:
        return []
    body.sort(key=lambda r: r[0])        # 'YYYYQn' 字典序 = 时间序
    # ── 铁律 3：逐季连号 ──
    for i in range(1, len(body)):
        py, pq = _q_parse_key(body[i - 1][0])
        cy, cq = _q_parse_key(body[i][0])
        if (cy, cq) != _q_prev(py, pq, -1):
            raise FetchError(
                f'写入后季度不连续：{body[i - 1][0]} → {body[i][0]}。缺口会让下游把两个'
                f'季度的变动记到一个季度上，拒绝写入。掉得太远时先跑一次 '
                f'`python3 fetch/schw.py --quarterly-backfill`（它扫全部历史申报）。')
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)
    os.replace(tmp, path)
    log(f'  [q-写入] 新增 {len(added)} 季：{added[0]} … {added[-1]}')
    return added


# ── 对外接口（季频版，与 latest_month / update / backfill 一一对应）───────
def latest_quarter(cache_dir, offline: bool = False) -> str:
    """官方源当前最新季，"YYYYQn"。抓不到抛 FetchError。

    它**必然**落后于 latest_month() 一到两个月，见本节「节奏」那一段 —— 别拿两者
    互相判新鲜度。
    """
    fils = _q_earnings_8k(cache_dir, offline=offline)[:1]
    data = _collect_quarterly(cache_dir, fils, offline=offline, verbose=False)
    ok = [qk for qk, v in data.items() if all(c in v for c in QCOLS)]
    if not ok:
        raise FetchError('最新一份业绩 8-K 解析出来了，但没有任何一个季度凑齐两列')
    return _q_key(*max(ok))


def update_quarterly(series_dir, cache_dir, back: int = 3, verbose: bool = True) -> list:
    """把新季度追加进 series/schw_q.csv，返回新增季度 ['YYYYQn', ...]。**增量入口。**

    只探最近 `back` 份业绩 8-K —— 那是「每季往后走一格」该有的开销。每份给 5 个季度，
    所以 back=3 已经带着 7 个季度的重叠做自检；再往前不会有新东西，只是把同样的数对一遍账。
    网络开销：申报清单 1 个请求（每天都在变，不吃缓存）+ 每份新申报 2 个请求
    （index.json + 正文）。已经缓存过的申报 0 个请求。

    幂等：已存在的季度一律跳过（不覆盖、不重排、不改动已有行的任何字符）；
    没有新增时不写盘。

    ⚠ 掉得太远时（连着几个季度没人跑）back=3 覆盖不到缺口，`_q_merge_into_csv` 的连号
    自检会拦下并点名让你去跑 --quarterly-backfill。**不要为此调大 back** —— 那是把
    一次性的存量补齐摊到每一轮的开销里，正是 update()/backfill() 分家要避免的事。
    """
    fils = _q_earnings_8k(cache_dir)[:max(1, back)]
    merged = _collect_quarterly(cache_dir, fils, verbose=verbose)
    return _q_merge_into_csv(series_dir, merged, verbose=verbose)


def backfill_quarterly(series_dir, cache_dir, verbose: bool = True,
                       offline: bool = False) -> list:
    """把历史季度一次性补进 series/schw_q.csv，返回新增季度。**存量入口。**

    与 update_quarterly() 的关系，同 backfill() 与 update()：一个管「往后走一格」，
    一个管「把官方还留着的老申报全扫一遍」。两者写同一个 CSV、守同一套铁律。
    扫描范围是 _Q_EARLIEST_FILING 起的全部业绩 8-K（本机实测 50 份，覆盖 2012Q4 → 2026Q2），
    落盘只到窗口左端 _Q_FROM 为止。

    offline=True：只用 cache/schw_rates/ 里已有的申报重放一遍，**不打任何网络请求**，
    缺文件就抛。这是可复现性验收用的开关 —— 拿它往一张只有表头的 CSV 上重跑，产物应当
    与仓里的 series/schw_q.csv **逐字节相同**。
    """
    fils = _q_earnings_8k(cache_dir, offline=offline)
    if verbose:
        print(f'  [q-清单] {len(fils)} 份业绩 8-K：{fils[-1]["date"]} … {fils[0]["date"]}')
    merged = _collect_quarterly(cache_dir, fils, offline=offline, verbose=verbose)
    if not merged:
        raise FetchError('一个季度都没解析出来 —— 不要当成「没有历史数据」，'
                         '先人工核对 EDGAR 上 CIK 0000316709 的 item 2.02 8-K 清单。')
    if verbose:
        ks = sorted(merged)
        print(f'  [q-源范围] {_q_key(*ks[0])} … {_q_key(*ks[-1])}（共 {len(ks)} 季）；'
              f'落盘窗口自 {_q_key(*_Q_FROM)} 起')
    return _q_merge_into_csv(series_dir, merged, verbose=verbose)


# ══════════════ 为什么这条腿没有登记进 monthly_run.py ══════════════
# 2026-09-16 逐条查过 monthly_run.py 里的两张登记表，**两张都容不下它**：
#
# 1. `SLOW_LEGS`（慢腿闸门）—— 判据是 `slow_pending()` 逐列扫 **series/<t>.csv** 的最后
#    非空**月**。这条腿写的是另一个文件 series/schw_q.csv，`series/schw.csv` 里一列都没有：
#    硬登记的结果是「列前缀一列都没匹配上」→ 按 fail-open 当成欠货 → schw 天天整趟下载，
#    正好撞上那张表自己写的第二条 ⚠。而且 `_due_month()` 算的是月度应到月份，季度源一年
#    里有八个月会被判成欠货 —— 与 cost_sec() docstring 里第 2 条是同一个形状。
# 2. `LEG_ALERTS` / `DEGRADED`（腿级降级）—— 那是给「一家的几条腿共用一次 update()」用的
#    报警通道，本条腿根本不在 `update()` 的调用链里（见下），暴露 DEGRADED 也没人读。
#
# 它该待的地方是 main() 里 cost_sec() / tsm_6k() 那一类**按家名守门的第二源步**
# （`if 'schw' in todo: fails += schw_q()`），理由与那两条逐字相同：`one('schw')` 在
# import fetch 之前先问 `not_due('schw')`，而那个判断读的 data_through 由**月频腿**独家
# 推动 —— 月报一落地闸门就关死整月，而业绩 8-K 的到货日（季末后 2–3 周）**恰好全落在
# 月频腿已经追平的日子里**，塞进 update() 当慢腿的实际效果是「永远不跑」，且长得和健康
# 的安静日一模一样。好消息是触发器那一半已经现成：`series_fingerprint()` glob 的是
# `series/schw*.csv`，schw_q.csv 变了就会让 /schw/ 重建，不必另写催建逻辑。
# 那一步要改 monthly_run.py（main() + 模块 docstring 的「第二源」清单 + docs/CRON_WIRING.md），
# 与 build/schw.py 消费这张 CSV 是同一件事，**留给接线的人一起做**；在那之前这条腿靠
# `python3 fetch/schw.py --quarterly` 手动跑。



if __name__ == '__main__':
    import sys
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if '--check-iea' in sys.argv:
        # 只跑恒等式自检 2（月度平均生息资产 ↔ fee_rates 季度腿），一个字节都不写、
        # 一个请求都不发。改完解析或改完窗口常数之后拿它当闸门跑。
        _sd = os.path.join(_root, 'series')
        with open(os.path.join(_sd, SERIES), newline='') as _f:
            _rows = list(csv.reader(_f))
        _crosscheck_quarter_iea([r for r in _rows[1:] if r and r[0].strip()],
                                _sd, lambda *a: print(*a))
        raise SystemExit(0)
    if '--columns' in sys.argv:
        # 给已有的行补新增列（不加行）。加完新列后跑一次，之后是幂等的。
        print('backfill_columns:',
              backfill_columns(os.path.join(_root, 'series'),
                               os.path.join(_root, 'cache'),
                               dry_run='--dry-run' in sys.argv))
        # 跨源打架必须印出来。以前这里不印，于是 2023 年那次官方重述入库时无声无息。
        # **稳定态下这张表不是空的**，而且非空的行随 _NEW_COLS 当轮填哪几列而变：
        # 填 avg_interest_earning_assets_usdbn 时是 2025-01…2025-11 那 11 行（官方
        # 2025-12 的追溯调整）；把 client_cash_pct 放回 cols 再跑，_RECAST 会把当期原值
        # 那一份比下去，多出来的 6 行就是口径坑第 8 条的活证据。
        # 见到这两批之外的行，才是要去看的事。
        if COLRESTATEMENTS:
            print(f'官方跨报告期重述（赢家由 _col_sources 排序决定，此处仅记录）'
                  f'{len(COLRESTATEMENTS)} 处:')
            for ym, c, keep, drop, f1, f2 in COLRESTATEMENTS:
                print(f'   {ym[0]:04d}-{ym[1]:02d} {c}: 取 {_fmt(c, keep)}（{f1}）'
                      f'／弃 {_fmt(c, drop)}（{f2}）')
        raise SystemExit(0)
    if '--quarterly-backfill' in sys.argv:
        # 季频腿的一次性存量补齐（扫全部业绩 8-K）。--offline 只用本地缓存重放，
        # 一个网络请求都不打 —— 可复现性验收就跑它。
        print('backfill_quarterly:',
              backfill_quarterly(os.path.join(_root, 'series'),
                                 os.path.join(_root, 'cache'),
                                 offline='--offline' in sys.argv))
        if QRESTATEMENTS:
            print('窗口外跨申报数值打架（不落盘，仅记录）:')
            for r in QRESTATEMENTS:
                print('  ', r)
        raise SystemExit(0)
    if '--quarterly' in sys.argv:
        # 季频增量：只探最近 3 份业绩 8-K。季频止于上一个已报季度，比月频短一到两个月。
        print('latest_quarter  :', latest_quarter(os.path.join(_root, 'cache')))
        print('update_quarterly:',
              update_quarterly(os.path.join(_root, 'series'), os.path.join(_root, 'cache')))
        if QRESTATEMENTS:
            print('窗口外跨申报数值打架（不落盘，仅记录）:')
            for r in QRESTATEMENTS:
                print('  ', r)
        raise SystemExit(0)
    if '--backfill' in sys.argv:
        # 一次性的历史存量补齐，不进 monthly_run 的每日/每月主路径。
        print('backfill:', backfill(os.path.join(_root, 'series'),
                                    os.path.join(_root, 'cache')))
        if RESTATEMENTS:
            print('跨源数值打架（先写者胜，此处仅记录）:')
            for r in RESTATEMENTS:
                print('  ', r)
        raise SystemExit(0)
    print('latest_month:', latest_month(os.path.join(_root, 'cache')))
    print('update      :', update(os.path.join(_root, 'series'), os.path.join(_root, 'cache')))
    if RESTATEMENTS:
        print('官方重述（人工确认后再信新值）:')
        for r in RESTATEMENTS:
            print('  ', r)
