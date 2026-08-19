# -*- coding: utf-8 -*-
"""日月光投控 ASEH（3711.TW / NYSE: ASX）月度营收页配置 —— 共用底座 `mrbase`。

放置位置：`build/mrspecs/ase.py`；薄壳 `build/ase.py`。
（薄壳非留不可：`monthly_run.py` 的 `builder()` 先找 `build/<t>.py`。
  ⚠️ 上一版这里写「不留薄壳会继续走 `build/single.py` + `build/specs/ase.py`」——
  那条退路本轮已经不存在了：`build/specs/ase.py` 在 4b0f201 里被删除，
  没有薄壳的后果是 `builder()` 退到 `single.py` 却找不到 spec，不是「两套图列分叉」。）

⚠️ **slug 是 `ase`。`asx` 在本仓已经是 ASX Limited（澳交所）**，日月光的 NYSE ADR
   恰好也叫 ASX —— 写串会同时污染两张页，而且是静默污染：图照出、数全错。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
核源清单（每条都在 2026-08-13 现抓复核过，出处可点开）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【1】序列起点 2018-05 是**口径起点**，不是「最早可得」
    SEC EDGAR 公司档案（CIK 0001122411）的更名记录：
      2018-04-30  ADVANCED SEMICONDUCTOR ENGINEERING INC → ASE Industrial Holding
      2018-06-08  → ASE Technology Holding Co., Ltd.
    控股公司 2018-04-30 才成立，2018-05 是第一个合并月报。SEC XBRL 里
    2015/2016/2017 的 `ifrs-full:Revenue`（283,303 / 274,884 / 290,441 NT$mn）
    属于**前身 ASE Inc.**，主体不同、不可前接。
    ⇒ `window.x_from = None`（显式声明「用序列自己的起点」）。
      **不要写 '2016-01'**：那是 TSM 的窗口。两种写法在本家产出完全相同
      （`_first_at_or_after` 会把它夹到 2018-05），但 spec 是给人读的 ——
      写 '2016-01' 等于声明「本页选了一个短窗口」，而事实是「本主体没有更早的月报」。
    ⚠️ 「不可前接」这四个字本轮**被质疑过一次并复核成立** —— 前身的月营收其实在
      EDGAR 上拿得到（同一个 CIK），所以「取不到」不是理由，理由是接上去的代价。
      全部证据、代价的量化、以及「日月光自己都不印那 12 个月同比」这条实测，
      写在【12】；页面上对应 `_PRE2018_NOTE` 那一条。

【2】可加总性是**实测**，不是推定（`value.summable = True` 的依据）
    `data.sec.gov/api/xbrl/companyconcept/CIK0001122411/ifrs-full/Revenue.json`
    的 20-F 年度值 vs 本序列逐月加总（NT$mn）：
      FY2019 413,182.2 / 413,182 · FY2020 476,978.7 / 476,980 ·
      FY2021 569,997.1 / 569,997 · FY2022 670,872.6 / 670,874 ·
      FY2023 581,914.5 / 581,916 · FY2024 595,409.6 / 595,409 ·
      FY2025 645,387.7 / 645,389
    七个完整年、最大绝对差 < 2 百万（基数 41~67 万百万），全是百万位四舍五入残差。
    ⇒ 季度桥 / QTD / YTD / 12 个月滚动同比这四道加总只在这一列上合法。

【3】第三列叫「非 ATM」而不是「EMS」，这是口径不是措辞
    月度新闻稿只给两个数：合并总额 + **ATM 分部**营收（分部基础，含分部间交易）。
    `revenue_nonatm_ntd_mn` = 合并 − ATM = 「EMS 分部 + Others − ATM 分部间抵销」，
    **不等于**合并利润表的 EMS 行，也不等于 EMS 分部基础数。官方分部数不在
    `series/ase.csv` 里，构建期读不到 ⇒ 页面只作定性陈述，**不印写死的差额**。

【4】「合并含 33–36% EMS」这句话（任务书原话）两处不准，页面按实测写
    (a) 那是**非 ATM 残差**不是 EMS（见【3】）；
    (b) 33–36% 只是最近约 12 个月。**全序列**实测的区间宽得多，跨越 2020-12 并入与
        2021-12 处分两次结构变化（2026-08-18 快照，当时 99 个月：24.4%~52.1%、
        中位 41.4%、最新月 35.6%）。
    页面上这些数一律 `_facts.share_range()` 构建期现算 —— 上面括号里那组是**快照**，
    序列每长一格就会与页面差一点，别拿它去核页面。

【5】**汇率线与美元营收腿都出，但它们始终是两件事（底座 §1.5 的两个判据）**
      · 汇率线（本页 Ex9）画的是 **NTD/USD 本身**，一条宏观序列 —— 挂同一份
        `series/tsm_fx.csv` 的每一页上它逐点相同，不需要日月光披露任何东西。
      · 美元腿（本页 Ex6／Ex7）画的是**公司自己每月印在新闻稿上的 US$ 表**
        （`fx.fgn_col = 'revenue_usd_mn'`），**不是**「本币 ÷ 外部牌价」折出来的
        构造值。⚠️ 措辞要准：本家是七家里唯一**以本币入账、却另外自印官方美元实绩**
        的一家；**不是**「唯一有官方美元数」—— 世芯-KY 的功能货币就是美元，那是
        `local_col` 那种形态（美元是计量本身、新台币栏是官方按申报汇率折出来的，
        两栏由恒等式绑定）。三种形态的分工写在 `_FX_LINES_NOTE` 里。
    ⚠️ 三个字段缺一不可，漏任何一个都不会报错、只会让页面说谎：
      · `'fgn_col': 'revenue_usd_mn'` —— 外币腿改读官方申报列（不给就退回除法）；
      · `'implied': False`            —— 那条腿不是我们折的。给了 `fgn_col` 却不给它，
        底座 `validate()` **硬失败**（否则页面会一边读官方列、一边印
        「Implied revenue」「(converted)」与一句折算假设，三处全是假话）；
      · `'rate_filed': False`         —— **最容易漏的一个**。`rate_filed` 是在问
        「Ex9 那条汇率线本身是不是公司申报的换算汇率」，与 `implied` **是两件事**；
        底座默认 `rate_filed = not implied`，本家不显式写就会在 Ex9 的线名、图脚与
        核对表表头印出 `as filed` —— 等于替公司申报了一个它从没申报过的汇率。
        日月光每月自印美元营收，却**从不披露所用汇率**。
    ⚠️ 由此而来：**`本币 ≡ 外币 × 汇率` 对本家不成立**（底座 §2 已写明并单列一支）。
      两条腿是公司在同一份新闻稿里的**两次独立披露**，而 Ex9 那条线是外部牌价；
      反解出的隐含汇率与 H.10 月均逐月偏离、符号还在翻（实测见【11】）。
      任何依赖这条恒等式的算式都不许套到本家上 —— 包括「拿 Ex9 乘 NT$ 柱还原美元线」。
    汇率对本家要紧，这句话有 20-F 原文兜底（**不是**「营收不以美元计价」）：
    ASEH 2025 年度 Form 20-F（2026-04-01 报送，accession 0001193125-26-135585）：
      · Item 5「Pricing and Revenue Mix」：
        "The majority of our prices and revenues is denominated in U.S. dollars."
      · Item 11「Exchange Rate Risk」：
        "Currently, the majority of our revenues and a significant portion of our
         capital expenditures are denominated in U.S. dollars."，并明写
        "against the NT dollar, our functional currency"。
    ⇒ ASEH 与 TSMC 是**同一种结构**：功能货币新台币、多数营收以美元计价。
      已删除的旧配置 `build/specs/ase.py`（只在 git 历史里）那句
      「那不是以美元计价的销售」本轮**不继承**。
    ⇒ `fx.usd_share_note` 用上面两句 20-F 原文的**定性版本**：20-F 说的是
      "the majority"，没有数字，**不许自己编一个「约七成」式的百分比**
      （底座 `validate()` 对 `src` 只硬性要求 URL，编不编数字它拦不住，靠这里自律）。
      URL 于 2026-08-13 现抓复核：HTTP 200，两句原文均在文内逐字命中。
    ⇒ 与 TSM 那页的分工由此定死：TSM 的美元线是 `本币 ÷ 外部牌价` 的**推导值**，
      本页的美元线是**公司披露值**。两页的 Ex6／Ex7 长得像，读法不一样。

【6】断点：**两条画线，三条登记但不画线**（门槛见 `BREAK_DRAW_MIN_PCT`）
    画线的两条，月份一律取**控制权转移当月**、不取签约日：
      · 2020-12 FAFG（Asteelflash）并入 —— 2021 年度 20-F（accession
        0001193125-22-087341）："On December 1, 2020, the transaction was completed
        and as a result, USI acquired 100% of FAFG's total issued shares"；同份文件
        「Impact of acquisitions」表：FAFG 自 2020-12-01 至 2020-12-31 计入合并的
        operating revenue = NT$2,043,440 千元 ≈ 2,043 百万 = 当月合并 50,298 的
        **4.1%**。影响合并 + 非 ATM，**ATM 不受影响**。
      · 2021-12 中国四厂处分 —— 同份 20-F："The transaction completed on
        **December 16, 2021**"（SPA 签于 2021-12-01，对价 NT$36,939.1 百万）。
        月中交割 ⇒ 2021-12 是半个月的过渡月，2022-01 才是第一个干净月。
        公司**自己认这条断点**：2022 全年每期月报多印一组 Pro Forma 表。
        本轮现抓 2022-01 期 PDF（电头 FEBRUARY 10, 2022）读到：
          合并 Dec-2021 报告 59,665 → pro forma 57,376（−2,289，−3.8%）
          ATM  Dec-2021 报告 31,011 → pro forma 28,722（−2,289）
        两侧减项分毫相同 ⇒ **减项全部落在 ATM，非 ATM 未动**，与【3】的残差定义自洽。
        y/y 被污染的幅度也是公司自己印的：Jan-2022 合并报告 +18.9% vs pro forma
        +24.7%（5.8pp）；ATM 报告 +10.7% vs pro forma +19.8%（**9.1pp**）。
    登记但不画线的三条（都 < 1%，画上去只会稀释掉真正 −3.8% 的那条）：
      · 2020-10 SF（Siliconware Electronics (Fujian)）处分完成（2021 年度 20-F
        Note 30：2020-09 董事会决议、2020-10 完成并转移控制权，对价 RMB966,000 千元）。
        ⚠️ **20-F 未单独披露 SF 的营收贡献** ⇒ 它落在门槛之下是**推断**（依据只有
        对价量级），不是实测。哪天查到 SF 的月营收量级 ≥ 门槛，这条要补画红线。
      · 2023-10-27 Hirschmann/HCC 并入（2025 年度 20-F Note 29「Impact of
        acquisitions」）：自并购日至 2023-12-31 计入合并 NT$1,017,423 千元
        ≈ 473 百万/月 ≈ 当时合并的 0.9%。
      · 2024-08-01 ASEPCAYMAN（菲律宾）+ CHE（韩国天安）并入（同表）：
        2024-08~12 合计 518,026 + 825,216 = 1,343 百万 ≈ 269 百万/月 ≈ 0.5%。
      量级交叉印证：同一份 20-F 的 pro forma —— 视同期初完成，FY2023 营收会是
      586,489,731 千元（实际 581,914，+0.79%）、FY2024 会是 597,015,838 千元
      （实际 595,410，+0.27%）。

【7】**ATM 被追溯重述过一次，合并没有**（本轮现抓 4 期 2019 年 PDF 复现）
      2019-07-09 期：ATM May-19 印 20,248（序列 20,148，−100）、
                     Jun-19 印 20,700（序列 20,605，−95）
      2019-08-09 期：ATM Jul-19 印 21,763（序列 21,668，−95）
      2019-09-10 期：ATM Aug-19 印 22,974（序列 22,884，−90）
      2019-10-09 期：ATM 表标题带星号，脚注 "The ATM results presented have been
                     retrospectively adjusted…"，三个月全中（重述后值），
                     季度 Q2-2019 由 59,790 重述成 59,594。
    同 4 期里**合并列 12/12 全中** ⇒ 合并没被重述。
    这直接支持把**合并**设为 `value`：主序列该是没有重述史的那条。
    **美元侧同一批重述也发生了**（本轮落 `revenue_atm_usd_mn` 时逐期复核）：
      ATM US$ 2018-12 656→655、2019-05 655→652、2019-06 659→656、
              2019-07 702→699、2019-08 734→731，落库一律取重述后值。
      合并侧美元与新台币各 0 处分歧。
    ⚠️ **「NT$ 变了 ⇒ US$ 也跟着变」不成立**，别拿一侧去推另一侧：2018Q4 的 ATM
      新台币由 64,127 重述成 64,120（−7），而同三版的 ATM 美元都是 2,083。
      两侧是两次独立的四舍五入，不是一个数的两种写法。

【8】`continuity` **不给**：底座要求「要么带 URL 出处、要么整个不给」。本家不但给不出
    「口径连续」的出处，事实还相反（【6】五条结构变化 + 【7】一次 ATM 重述）。

【9】`official_yoy` **不给**：`series/ase.csv` 没有 y/y 列。公司确实公告 y/y
    （新闻稿印到一位小数），底座退回 `build/yoy.py` 自算 —— 两者的差只来自
    「先四舍五入到百万再相除」，见 `_YOY_SOURCE_NOTE`（不印写死的差值）。

【10】没有指引桥：ASEH 每季法说会给的是「下季 ATM 新台币营收环比 +x%~+y%、EMS 环比
    约 +z%」这种**季度环比百分比区间**，没有绝对金额、没有月度分解、没有折算汇率假设。
    `mrspecs/tsm.py` 那条桥依赖 `tsm_guidance.csv` 的六列，在本家逐列无源。

【11】新落库的两列美元（`revenue_usd_mn` / `revenue_atm_usd_mn`）：来源、复核、陷阱
    **来源**：公司月度英文新闻稿正文的 `US$ Million` 表（与两张 NT$ 表同一份 PDF、
    同一页），公司自印的**整数**，不是任何人折出来的。**零缺失**（落库时 99 个月）。
    **复核**：两个独立 agent 各写一套解析器抽取，全表逐格 0 分歧
    （落库时 99 个月 × 5 个数值列 = 495 格）；对照组明确表示「没能证伪对方任何一格」。
    页面上那句话里的格数走 `_SPAN` 现算，这里的数是落库当时的快照。
    **它们不是 NT$ 那两列的函数**（这条最要紧，见【5】末与【7】末）：
      · 反解隐含汇率（NT$ ÷ US$）落在 27.60（2022-01）~ 32.84（2025-04）之间，
        中位 30.68，**全序列无一逸出 27–33**（落库时 99 个月）—— 量级对，
        所以**看上去**像可以互推；
      · 但它与 H.10 月均（`series/tsm_fx.csv`）的逐月偏离是 −2.07% ~ +2.22%、
        均值 −0.12%、**29 正 70 负、符号在翻**，绝大多数月份远超两个整数四舍五入
        能解释的量级 —— 不是一个可以校准掉的常数偏移。
      · 页面上这些数**一律构建期现算**（`_implied_fx()` / `_contrib_gap()`），
        本文件里不留写死的百分数。
    **陷阱（2022 年那批 pro forma 表）**：2022 全年每期月报多印一组「排除已处分中国
    四厂」的 pro forma 表，**美元侧也印**。当月那一格的实际值与 pro forma **完全相同**，
    只有 **YoY 那一格**不同 —— 所以真正会取错的不是当月，而是**经 2022 各期的 YoY 列
    反推出来的 2021 年**：取错会让合并 US$ 偏低 3.7%~5.0%、ATM US$ 偏低 7.2%~8.0%。
    （早先流传的「把 2022 全年拉低 8~10%」这个说法**不成立**，别再引。）
    本轮落库取的是实际表、不是 pro forma 表。

【12】**为什么不拼前身**（本轮的决定；页面上对应 `_PRE2018_NOTE` 那一条）
    上一版这里只写了「主体不同、不可前接」。那句话把两件事合成了一句，而它们的
    后果相反：「取不到」是暂时的（谁哪天抓到了就该补），「代价太大」是判断
    （补上去是**倒退**）。本轮把两件事拆开核了一遍，结论是**后者**。

    ── 前身在哪（都能点开）──────────────────────────────────────────
    · SEC 那边 ADR 按 Rule 12g-3 继受，**前身与本主体共用同一个 CIK
      0001122411**，EDGAR 只记了一次更名（`submissions.json` 的 `formerNames`：
      ADVANCED SEMICONDUCTOR ENGINEERING INC → 2018-04-30 ASE Industrial Holding
      → 2018-06-08 ASE Technology Holding）。所以「换了一家公司所以 EDGAR 上没有」
      是错的 —— 就在同一个抽屉里。
    · 该 CIK 的 6-K 序列最早 **2000-10-30**（accession 0000950103-00-001184）。
      ⚠️ **但那一份是 2000Q3 财报，不是月营收公告** —— 「6-K 回到 2000-10」这句话
      要是被读成「月营收回到 2000-10」就错了。逐份核过的实况：
        2000-10-30 2000Q3 财报 / 2000-12-27 台北地院判决公告（正文无 "net
        revenues" 字样）/ 2001-02-26 FY2000 财报 / 2001-04-26 2001Q1 财报 /
        **2001-05-09 第一份月营收公告**（2001 年 4 月数，
        accession 0000950103-01-500934，标题 "ANNOUNCES APRIL 2001 NET REVENUES"）。
      EDGAR 全文检索（efts，覆盖 2001+）在该 CIK 下命中 "monthly net revenues"
      的最早一份也是这一份，与逐份核对一致。
    · 2018 年那几份前身月报的形态（2026-08-18 现抓）：
        6-K 2018-04-10 acc 0000950103-18-004622 → Mar-2018 与 2018Q1
        6-K 2018-03-07 acc 0000950103-18-003093 → Feb-2018
        6-K 2018-01-09 acc 0000950103-18-000261 → Dec-2017
      版式与今天的 ASEH 月报同源 —— 2018-04-10 那份逐字读过：合并表
      `Mar 2018 / Feb 2018 / Mar 2017` + Sequential/YoY Change，NT$ 与 US$
      各一张，另有 Q 表，第二张分部表就叫 "atm net revenues"。
      （2018-03-07 与 2018-01-09 两份只核到标题与合并行，没有逐格读。）
      **所以真要拼，工程上是拼得动的 —— 拦路的从来不是抓取。**

    ── 代价一：+30% 的真实水平台阶，来自并表不是经营 ──────────────────
    前身 6-K 2018-04-10 印的 2018Q1：合并 **64,966**、ATM **37,072**（NT$ 百万；
    同表 Mar-18 22,371 / Q4-17 83,986 / Q1-17 66,551）。
    ASEH 2018 年 9 月号（电头 2018-10-09）对**同一个 2018Q2** 印了三个数，
    脚注 1／2／3 逐条定义（原文照录）：
      Q2¹ **62,015** — "only reflect operations of ASE Technology Holding Co., Ltd
                        starting from April 30, 2018"
      Q2² **84,501** — "Legal entity reporting: … and operations of ASE Inc. and
                        its subsidiaries in April 2018"
      Q2³ **91,757** — "Pro forma … and operations of SPIL and its subsidiaries
                        in April 2018"
    同一个季度自己就有 62,015~91,757（+48.0%）的跨度。对前身 Q1 的台阶：
      合并 64,966 → 84,501 = **+30.1%**（→ 91,757 则 +41.2%）
      ATM  37,072 → 54,534 = **+47.1%**（→ 61,790 则 +66.7%）
    验：Q2¹ 62,015 与本序列 5+6 月加总 62,016 差 1（四舍五入）；ATM Q2¹ 42,010
    与本序列 20,901+21,109 **逐字相等** ⇒ 这三个数与本序列同源，不是别处抄的。
    反解出的矽品 2018-04 单月：合并 7,256、ATM **也是 7,256**（Q2³−Q2² 两侧相同）
    —— 矽品是纯封测、没有 EMS 那一侧，这条自洽也顺带证实台阶就是矽品。

    ── 代价二：公司自己空着那 12 个月的同比 ───────────────────────────
    **这是最有力的一条，本轮自己动手复核过**：2026-08-18 把当时全部 99 期新闻稿 PDF
    重抓一遍（原件在 `cache/ase_pdf/`），逐期读版式而不是抽查。实测：
      · 月表表头模板**从第一期起就带 `YoY Change` 这一栏** —— 位子一直留着；
      · **2018-05 ~ 2019-04 整整 12 期**，去年同月那一列与 YoY% 那一格**全是空的**；
        `_pdf_tables()` 在这 12 期只解析出 2 个月键（2018-05 那期只有 1 个）。
      · **2018-05 期（电头 2018-06-08）连上月列都没有**，Sequential 与 YoY
        两个百分比格都空着 —— 本主体那时连上一个月都还没有。
      · 第一次印出去年同月是 **2019-05 期（电头 2019-06-10）**：
        `May 2019 / Apr 2019 / May 2018` = 30,118 / 29,051 / 30,982，YoY −2.8%。
        此后 87 期无一缺席。
      · 四张表（合并／ATM × NT$／US$）逐期一致，99 期里键不一致的 0 期。
    合计：四表各 284 个月读数 = 99 自期 + 98 上月 + 87 去年同月（与 `fetch/ase.py`
    「数据源」第 2 条那三个数逐字对上 —— 那三个数原本就是这条实测，只是上一版没写
    它意味着什么）。
    ⇒ 页面若印出那 12 个月的同比，等于比日月光自己披露得还「勇」。
    **怎么复核**（不动序列、不写库，PDF 落 cache/）：
      `_discover(range(2018, 当年+1))` 拿 URL → `_get_pdf()` → `_pdf_tables()`，
      看 `out['C']` 的键数：1 = 只有自期（仅 2018-05）、2 = 无去年同月、3 = 有。
      要连「YoY% 那一格空不空」一起看，就往 `Net Revenues` 后面数百分比 token：
      2018-05 印 0 个、2018-06~2019-04 各印 1 个（只有 Sequential）、2019-05 起 2 个。

    ── 代价三：分部那一列接不上，而且本轮没核完 ───────────────────────
    前身的 ATM 不含矽品、ASEH 的含（见代价一的 37,072 vs 54,534）。
    再往前退：2001-05-09 那份月报单位是 NT$ **千元**，第二张表叫
    "packaging operations in Kaohsiung" 而不是 ATM。
    "ATM net revenues" 这个写法在 EDGAR 全文检索（efts，**只覆盖 2001+**）里
    该 CIK 下最早命中 **2010-04-07** 的 6-K，2001~2009 逐段查询 0 命中 ——
    ⚠️ 这只说明「2001 年起的 EDGAR 全文里没有更早的」，2000 年那几份不在索引内，
      而且换名不等于换口径、同名也不等于同口径。**这两头都还没核。**
    **逐年的分部口径对照本轮没有做完** —— 所以本页不声称 `revenue_atm_ntd_mn`
    能接，也不拿「大概同义」当理由把它接上。

    ── 接了会坏掉哪几格（算式，`_splice_damage()` 现算）────────────────
    断点 = 本序列首月。单月同比 12 个点跨口径（2018-05~2019-04，牵动
    2017-05~2019-04 的读数）；12 个月滚动合计同比 23 个点跨口径
    （2018-05~2020-03，牵动 2016-06~2020-03）。换来的是 2016-01~2018-04 的 28 格柱。
    ⚠️ 上面这四个日期与两个计数**页面上不写死**：`yoy.TTM_WIN` 或序列首月一变，
      写死的版本会当场说谎而没有任何校验拦得住。

    ⇒ 本轮结论：**不拼**，`window.x_from` 保持 `None`（【1】），
      不建 `series/ase_pre2018.csv`。谁将来想推翻这个决定，请先把「代价三」
      的分部口径逐年核完，并想清楚 12 期空白的 YoY 列该怎么向读者交代。

━━ 上一轮同时修掉的两处底座缺陷（不是 ASE 专属补丁）━━━━━━━━━━━━━━━━━━
· `build_exhibits` 的 Ex9 原本走 `push('heat', …)`，而 `push()` 无条件调
  `apply_breaks()` ⇒ 热力矩阵拿到 `break_at`（**月份轴上的下标**，这张 8×12 的矩阵
  没有那条轴），并被追加一段「本图上的红色竖虚线是口径断点…」，正好顶撞它上一句
  「heat_matrix 没有连续横轴，因此不画断点竖线」；页尾清单也会跟着自相矛盾。
  画面一直是对的（`charts.js` 的 `drawHeat()` 提前 return），错的是 payload 与文字。
  TSM 的 breaks 为空走不到，联电/联发科/南亚科接管时都会踩到。已在底座改掉。
· 底座原来对任何没有 `fx` 的 spec 印「该家的月度公告只有新台币，没有官方美元实绩」
  —— 那是一句 per-ticker 的事实断言，对 ASEH 是**假话**（见【5】）。
  底座已改成只陈述本页状态、把「公司有没有披露」留给 spec 说。

━━ 本轮的图序（编号是底座算出来的，改动 skip / segments 会整体前移）━━━━━━━
  1 汇总表 · 2 rev_bar（分部堆叠）· 3 qtr · 4 mom · 5 mix（分部占比，新）·
  6 fx_lines（本币 vs 美元，两条都是官方值）· 7 fx_contrib（汇率贡献 pp）·
  8 hist（全历史，含两条分部线）· 9 fx_rate（NTD/USD）· 10 heat · 11 核对表
本文件里凡是要点名某张图，一律写「Ex6 那张」这种**中文散文里的相对指代**要避开，
改说图名（「本币 vs 美元那张」）—— 编号是底座现算的，写死会在下一次增删图时变成假话。
"""
import csv
import os

from . import _facts


# ── 「本仓几家里唯一有官方外币实绩列」这句话现算 ─────────────────────────────
# 它是一句跨文件的普查断言：家数会变、别家哪天也落一列官方美元数，句子就成了假话，
# 而没有任何东西会报错。判据就是同目录下谁的 spec 挂了 `fx.fgn_col`（= 直接读一列
# 官方外币实绩，不做折算）。**读文本、不 import** —— import 会连带跑同级模块的
# 构建期计算，那份代价与副作用不该由这一句话来承担。
def _fgn_peers():
    here = os.path.dirname(os.path.abspath(__file__))
    fam, hit = [], []
    for fn in sorted(os.listdir(here)):
        if not fn.endswith('.py') or fn.startswith('_'):
            continue
        fam.append(fn[:-3])
        with open(os.path.join(here, fn), encoding='utf-8') as fh:
            if "'fgn_col'" in fh.read():
                hit.append(fn[:-3])
    return fam, hit


_MR_FAM, _MR_FGN = _fgn_peers()
if 'ase' not in _MR_FGN:
    raise SystemExit('本 spec 自己就该挂 fx.fgn_col，现在扫不到 —— '
                     '页上那句「有官方外币实绩列」会指着一个不存在的字段说话')
_FGN_OTHERS = [t for t in _MR_FGN if t != 'ase']
_FGN_TXT = ('<b>「以新台币入账、却另外自印官方美元实绩」的公司：'
            + (f'本仓共用这套图列的 {len(_MR_FAM)} 家里只有 ASEH 一家'
               if not _FGN_OTHERS else
               f'本仓共用这套图列的 {len(_MR_FAM)} 家里有 {len(_MR_FGN)} 家 —— '
               + '、'.join(f'<code>{t}</code>' for t in _MR_FGN)
               + '，ASEH 是其中之一')
            + '。</b>')

# build/ 在 sys.path 上（mrbase.load_spec 会 insert HERE）⇒ yoy 直接 import。
# 同比口径的唯一实现是 build/yoy.py，本文件一行 pct_change(12) 都不写。
try:
    import pandas as pd
    import yoy as _Y
except Exception:                    # noqa: BLE001 —— import 期不许抛，见 _facts 文件头
    pd = _Y = None

_CSV = 'ase.csv'
_COL_TOT = 'revenue_ntd_mn'
_COL_ATM = 'revenue_atm_ntd_mn'
_COL_NON = 'revenue_nonatm_ntd_mn'
#: 公司自印的美元两列（见文件头【11】）。合并那条喂 `fx.fgn_col`；
#: ATM 那条目前只在核算隐含汇率时用得到 —— 底座的外币腿只有一条，画不了分部美元。
_COL_USD = 'revenue_usd_mn'
_COL_ATM_USD = 'revenue_atm_usd_mn'
#: 外部牌价（H.10 月均）所在文件与列。与 SPEC['fx'] 用的是同一份，
#: 这里再引一次是为了让图注里的偏离统计与页面画的那条线**同源**。
_FX_CSV = 'tsm_fx.csv'
_FX_COL = 'ntd_per_usd'

#: 画红色断点竖线的门槛：并表/处分对**单月合并营收**的影响 ≥ 这个比例才画线。
#: 低于门槛的仍然登记进图注（见 `_M_AND_A_NOTE`）。一页红线画满等于告诉读者
#: 「什么都不可比」，反而盖掉真正 −3.8% 的那一条。
BREAK_DRAW_MIN_PCT = 3.0


# ══════════════════════════════════════════════════════════════════════════════
# 构建期现算。每个函数拿不到就返回 None，调用方退回不含数字的定性版本。
# import 期抛异常 = 整批构建挂在「少一句话」上，不划算（同 mrspecs/_facts.py）。
# ══════════════════════════════════════════════════════════════════════════════
def _series(col):
    """series/ase.csv 的一列 → pandas Series（月度 PeriodIndex）。拿不到返回 None。"""
    if pd is None:
        return None
    try:
        with open(os.path.join(_facts.SERIES, _CSV), encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
        idx = pd.PeriodIndex([r['month'] for r in rows], freq='M')
        return pd.Series([float(r[col]) for r in rows], index=idx).sort_index()
    except Exception:                # noqa: BLE001
        return None


def _fx_ext():
    """外部牌价（H.10 月均）对齐到本序列的月份。拿不到返回 None。"""
    if pd is None:
        return None
    try:
        with open(os.path.join(_facts.SERIES, _FX_CSV), encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
        idx = pd.PeriodIndex([r['month'] for r in rows], freq='M')
        s = pd.Series([float(r[_FX_COL]) for r in rows], index=idx).sort_index()
        tot = _series(_COL_TOT)
        if tot is None:
            return None
        al = s.reindex(tot.index)
        return None if bool(al.isna().any()) else al
    except Exception:                # noqa: BLE001
        return None


def _implied_fx():
    """公司自印的 NT$ 与 US$ 反解出的**隐含汇率**，及它与外部牌价的逐月偏离。

    这是本页最要紧的一条实测：它同时支撑三句话 ——
      · 美元腿是官方申报值，不是我们折的（否则偏离恒为 0）；
      · Ex 那条外部牌价**不是**公司自己用的汇率（`rate_filed=False` 的实证）；
      · 拿外部牌价乘 NT$ 柱还原不出公司印的美元数（偏离量级就是还原误差）。
    **舍入噪声下界**：两列都是公司印的整数，一格最多各错 0.5 —— 相对误差上界
    `0.5/NT$ + 0.5/US$`。超过它的偏离不可能由四舍五入解释。
    """
    tot, usd, fx = _series(_COL_TOT), _series(_COL_USD), _fx_ext()
    atm, atm_usd = _series(_COL_ATM), _series(_COL_ATM_USD)
    if tot is None or usd is None or fx is None:
        return None
    try:
        imp = (tot / usd).dropna()
        dev = ((imp / fx) - 1.0).dropna() * 100
        noise = ((0.5 / tot + 0.5 / usd) * 100).reindex(dev.index)
        # 美元列本身是**整数百万**，所以它的单月同比也带一点舍入噪声。
        # ⚠️ 别把「比值的相对误差」当成「同比的百分点误差」——这两者差一个 a/b 因子：
        #     y/y(pp) = 100 × (a/b − 1)，∂ ⇒ 上界 = 100 × (a/b) × (0.5/a + 0.5/b)
        # 漏乘 a/b 的旧式子在 a>b 的月份上**不是上界**（本序列 87 个可比月里 62 个
        # a/b > 1）。实测：旧式 median 0.0640 / max 0.1119；正确式 0.0710 / 0.1266，
        # 最坏月 2021-02 的真值 0.1266 已经超过旧式给出的**全局最大** 0.112。
        # 对照：上面 `noise` 那一行**没有**这个问题 —— 它去比的 `dev` 本身就是相对 %，
        # 两边同量纲，别顺手一起「修」。
        # 这个数进 _YOY_SOURCE_NOTE —— 新台币那一列基数大约 31 倍（= 隐含汇率中位数），
        # 噪声可以忽略，美元那一列不能默认同样忽略，要把量级摆出来。
        _r = usd / usd.shift(12)
        yy_noise = ((_r * (0.5 / usd + 0.5 / usd.shift(12))) * 100).dropna()
        if len(dev) < 24 or not len(yy_noise):
            return None
        # ATM 那一组（NT$ 与 US$）反解出来的隐含汇率，与合并那一组差多少。
        # 差得极小 ⇒ 公司内部**确实有一个统一的换算汇率**，只是从不披露；
        # 于是「页上这条外部牌价 ≠ 公司用的那个汇率」就不再是猜测，而是双重实证：
        # 两组自印数彼此一致，却同时与外部牌价系统性地对不上。
        seg_gap = None
        if atm is not None and atm_usd is not None:
            try:
                seg_gap = float((imp - (atm / atm_usd)).abs().max())
            except Exception:        # noqa: BLE001
                seg_gap = None
        return {
            'n': int(len(imp)),
            'lo': float(imp.min()), 'lo_m': str(imp.idxmin()),
            'hi': float(imp.max()), 'hi_m': str(imp.idxmax()),
            'med': float(imp.median()),
            'd_lo': float(dev.min()), 'd_lo_m': str(dev.idxmin()),
            'd_hi': float(dev.max()), 'd_hi_m': str(dev.idxmax()),
            'd_mean': float(dev.mean()), 'd_medabs': float(dev.abs().median()),
            'pos': int((dev > 0).sum()), 'neg': int((dev < 0).sum()),
            'over50': int((dev.abs() > 0.5).sum()),
            'over_noise': int((dev.abs() > noise).sum()),
            'noise_med': float(noise.median()),
            'yy_noise_med': float(yy_noise.median()),
            'yy_noise_max': float(yy_noise.max()),
            'cur_m': str(dev.index[-1]), 'cur': float(dev.iloc[-1]),
            'cur_x': float(abs(dev.iloc[-1]) / noise.iloc[-1]),
            # 核对表上那两列并排，读者第一件想做的事就是相乘。把结果先算出来摆在页上：
            # 乘出来的数**不等于**左边那一列，差多少现算。
            'seg_gap': seg_gap,
            'cur_fx': float(fx.iloc[-1]), 'cur_usd': float(usd.iloc[-1]),
            'cur_tot': float(tot.iloc[-1]),
            'cur_prod': float(fx.iloc[-1] * usd.iloc[-1]),
        }
    except Exception:                # noqa: BLE001
        return None


def _contrib_gap():
    """「汇率贡献」的**公司口径** vs **外部牌价推导口径**之差（pp）。

    公司口径 = 新台币单月同比 − 公司自印美元的单月同比（页上画的就是这条）。
    推导口径 = 新台币单月同比 −（新台币 ÷ 外部牌价）的单月同比（本页**没画**，
    也正是别家没有官方美元时唯一画得出来的那条）。两者之差就是「没有官方美元
    实绩的家，那张汇率贡献图能错多少」—— 本页把它现算出来当作反例印在图注上。
    口径一律走 build/yoy.py。
    """
    if _Y is None:
        return None
    tot, usd, fx = _series(_COL_TOT), _series(_COL_USD), _fx_ext()
    if tot is None or usd is None or fx is None:
        return None
    try:
        loc_yoy = _Y.mom_yoy(tot, _Y.FLOW)
        c_filed = (loc_yoy - _Y.mom_yoy(usd, _Y.FLOW)).dropna()
        c_der = (loc_yoy - _Y.mom_yoy(tot / fx, _Y.FLOW)).dropna()
        d = (c_filed - c_der).dropna()
        if len(d) < 24:
            return None
        return {
            'n': int(len(d)),
            'cur_m': str(c_filed.index[-1]),
            'cur_f': float(c_filed.iloc[-1]), 'cur_d': float(c_der.iloc[-1]),
            'cur_gap': float(d.iloc[-1]),
            'prev_m': str(c_filed.index[-2]),
            'prev_f': float(c_filed.iloc[-2]), 'prev_d': float(c_der.iloc[-2]),
            'prev_gap': float(d.iloc[-2]),
            'maxabs': float(d.abs().max()), 'maxabs_m': str(d.abs().idxmax()),
            'medabs': float(d.abs().median()),
            'ge1': int((d.abs() >= 1.0).sum()),
            'lo': float(c_filed.min()), 'hi': float(c_filed.max()),
        }
    except Exception:                # noqa: BLE001
        return None


def _mops_remarks():
    """MOPS「備註／營收變化原因說明」栏：本家触发过几次、填过几次，以及同批各家对照。

    **为什么 spec 要读这张表**：底座只在「近 13 个月至少有一格非空」时才给核对表加
    「本月備註」那一列，brief 也只在当月有登记时才多一句。本家两处都空 ——
    页面于是**什么都不说**，而「什么都不说」在读者那里与「这页漏抓了」长得一模一样。
    这一段就是把那个空白解释成一个**可复核的事实**（0 次触发、0 次填报），
    并给出同一份库里别家的次数作对照。
    极值取该库自带的官方 `yoy_pct` / `ytd_yoy_pct` 两列 —— 门槛是官方按这两条腿判的，
    拿本页自算的累计同比去比会在序列首年撞上「2018 只有 8 个月」的口径产物。
    """
    try:
        with open(os.path.join(_facts.SERIES, 'mops_remarks.csv'), encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
    except Exception:                # noqa: BLE001
        return None
    if not rows:
        return None

    def _trig(r):
        return str(r.get('triggered', '')).strip() in ('1', 'True', 'true')

    mine = sorted((r for r in rows if r.get('ticker') == 'ase'),
                  key=lambda r: r['month'])
    if len(mine) < 6:
        return None
    # ⚠️ **横向清单必须现算、必须含全部 ticker（含 0 次的）**。
    #    手写名单错过两次：漏掉台积电（同窗口触发 2 次，原文印在 tsm 自己的核对表里），
    #    并且把「0 次」的家整个略去 —— 而「0 次触发」正是本页要解释的那件事，
    #    漏掉它们等于把本家写成孤例。次数逐月会变，写死下个月就是假话。
    roster, filled_by, same_txt = {}, {}, {}
    for r in rows:
        k = r.get('co_name') or r.get('ticker')
        roster[k] = roster.get(k, 0) + (1 if _trig(r) else 0)
        txt = (r.get('remark') or '').strip()
        if txt:
            filled_by[k] = filled_by.get(k, 0) + 1
            same_txt.setdefault(k, set()).add(txt)
    # 「0 次触发却月月填」的家：那种备注不是对增减的说明（法定填报只在过门槛时发生）。
    # 逐字相同才敢说「一字不变」—— 这里现算，不引底座注释里的结论。
    boiler = [(nm, filled_by[nm]) for nm in filled_by
              if roster.get(nm, 0) == 0 and len(same_txt.get(nm, ())) == 1]

    def _mx(col):
        xs = []
        for r in mine:
            try:
                xs.append(abs(float(r.get(col))))
            except (TypeError, ValueError):
                continue
        return max(xs) if xs else None

    return {
        'n': len(mine), 'first': mine[0]['month'], 'last': mine[-1]['month'],
        'me': mine[0].get('co_name') or 'ase',
        'trig': sum(1 for r in mine if _trig(r)),
        'filled': sum(1 for r in mine if (r.get('remark') or '').strip()),
        'max_yoy': _mx('yoy_pct'), 'max_ytd': _mx('ytd_yoy_pct'),
        # 全部家（含本家、含 0 次），按触发次数降序；同次数按名字定序，保证产出稳定。
        'roster': sorted(roster.items(), key=lambda kv: (-kv[1], kv[0])),
        'boiler': sorted(boiler, key=lambda kv: -kv[1]),
    }


def _span():
    """本序列的 (首月, 末月, 月数)。拿不到返回 None。

    ⚠️ **页面与注释里任何「N 个月」都必须走这里现算。** 本文件里曾有七处写死的
    「99 个月」（写于 2026-08，当时确实是 99）—— 序列每个月长一格，那七处从下一期
    起就同时变成假话，而且是**读起来完全正常**的假话：没有任何校验会拦它。
    """
    try:
        with open(os.path.join(_facts.SERIES, _CSV), encoding='utf-8') as fh:
            ms = sorted(r['month'] for r in csv.DictReader(fh) if r.get('month'))
        return (ms[0], ms[-1], len(ms)) if ms else None
    except Exception:                # noqa: BLE001
        return None


def _mshift(m, k):
    """'YYYY-MM' 往后挪 k 个月（k 可为负）。"""
    t = int(m[:4]) * 12 + int(m[5:7]) - 1 + k
    return f'{t // 12:04d}-{t % 12 + 1:02d}'


#: 拿来量化「拼前身能换到多少格」的**假想**窗口起点。本仓 TSM／联电／南亚科那几页
#: 用的就是它，所以拿它当参照系读者认得出。**它不是本页的 x_from**（本页显式 None）。
_HYPO_X0 = '2016-01'


def _splice_damage():
    """假如把前身（2311 单体合并）接到本序列之前，哪几个同比点会跨口径。

    **纯算式，不读任何数** —— 断点就是本序列首月，剩下的全由同比的定义决定：
      · 单月同比比的是 m 与 m−12 ⇒ m 落在 [首月, 首月+11] 这 12 个点跨断点；
      · N 个月滚动合计同比比的是 [m−N+1, m] 与 [m−2N+1, m−N]，
        只要任一窗口罩住断点两侧就跨口径 ⇒ [首月, 首月+2N−2] 这 2N−1 个点跨断点。
    「牵动的读数」= 这些点吃进去的最早那个月 ~ 最晚那个月，比失真点本身宽一倍。

    之所以要现算而不是写死：`yoy.TTM_WIN` 哪天从 12 改成别的，写死的「23 个点」
    与「2020-03」会一起变成假话，而它们出现在页面正文里。
    """
    sp = _span()
    if not sp:
        return None
    b = sp[0]
    n = getattr(_Y, 'TTM_WIN', 12) if _Y is not None else 12
    d = {
        'break': b,
        'mom_lo': b, 'mom_hi': _mshift(b, 11), 'mom_n': 12,
        'mom_src_lo': _mshift(b, -12), 'mom_src_hi': _mshift(b, 11),
        'ttm_win': n,
        'ttm_lo': b, 'ttm_hi': _mshift(b, 2 * n - 2), 'ttm_n': 2 * n - 1,
        'ttm_src_lo': _mshift(b, -(2 * n - 1)), 'ttm_src_hi': _mshift(b, 2 * n - 2),
    }
    # 「换来多少格」：假想窗口起点到断点前一个月。断点若早于假想起点就没得换。
    gain = (int(b[:4]) * 12 + int(b[5:7])) - (int(_HYPO_X0[:4]) * 12 + int(_HYPO_X0[5:7]))
    d['gain_n'] = max(gain, 0)
    d['gain_lo'], d['gain_hi'] = _HYPO_X0, _mshift(b, -1)
    return d


def _identity():
    """核一条恒等式：ATM + 非 ATM ≡ 合并。

    差不为 0 就说明第三列不是残差 —— 那样「非 ATM」这个列名本身就要重写，
    页面上「合并 ≡ 各分部之和」那句话也不能再说。
    """
    tot, atm, non = _series(_COL_TOT), _series(_COL_ATM), _series(_COL_NON)
    if tot is None or atm is None or non is None:
        return None
    try:
        return {'max': float((atm + non - tot).abs().max()), 'n': int(len(tot))}
    except Exception:                # noqa: BLE001
        return None


def _split_gap():
    """「合并线替封测说了多少假话」的实测 —— 口径全部走 build/yoy.py。

    返回「ATM 同比 − 合并同比」（pp）在两种口径下的分布。**不假设符号**：
    本序列全历史上这个差是双向的（合并有时反而更快），把它写成「每个月都低估」
    在全历史上是假的，所以这里逐项报正负计数，措辞由数据决定。
    """
    if _Y is None:
        return None
    tot, atm = _series(_COL_TOT), _series(_COL_ATM)
    if tot is None or atm is None or len(tot) < 30:
        return None
    try:
        gt = (_Y.ttm_yoy(atm, _Y.FLOW) - _Y.ttm_yoy(tot, _Y.FLOW)).dropna()
        gm = (_Y.mom_yoy(atm, _Y.FLOW) - _Y.mom_yoy(tot, _Y.FLOW)).dropna()
        if not len(gt) or not len(gm):
            return None
        return {
            't_n': len(gt), 't_lo': float(gt.min()), 't_hi': float(gt.max()),
            't_pos': int((gt > 0).sum()),
            't12_n': len(gt[-12:]), 't12_lo': float(gt[-12:].min()),
            't12_hi': float(gt[-12:].max()), 't12_pos': int((gt[-12:] > 0).sum()),
            'm_n': len(gm), 'm_lo': float(gm.min()), 'm_hi': float(gm.max()),
            'm12_lo': float(gm[-12:].min()), 'm12_hi': float(gm[-12:].max()),
            'ttm_tot': float(_Y.ttm_yoy(tot, _Y.FLOW).dropna().iloc[-1]),
            'ttm_atm': float(_Y.ttm_yoy(atm, _Y.FLOW).dropna().iloc[-1]),
            'mom_tot': float(_Y.mom_yoy(tot, _Y.FLOW).dropna().iloc[-1]),
            'mom_atm': float(_Y.mom_yoy(atm, _Y.FLOW).dropna().iloc[-1]),
        }
    except Exception:                # noqa: BLE001
        return None


def _days_dispersion():
    """`_facts.days_effect()` 只给斜率点估计，这里补上标准误与 R²。

    **为什么非补不可**：`mrspecs/tsm.py` 那条「不做日均化」的论证靠的是「斜率 1.47
    而不是 1」。本家斜率 1.10，只报点估计会让人以为同一句话在这里也成立；补上标准误
    之后才看得见 1.10 与 1 在统计上分不开，于是本页的理由**必须换一条**。
    照抄 TSM 的措辞就是编数据。
    """
    import calendar
    try:
        with open(os.path.join(_facts.SERIES, _CSV), encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
        ms = [r['month'] for r in rows]
        vs = [float(r[_COL_TOT]) for r in rows]
    except Exception:                # noqa: BLE001
        return None

    def dm(m):
        return calendar.monthrange(int(m[:4]), int(m[5:7]))[1]

    xs, ys = [], []
    for i in range(1, len(vs)):
        if not vs[i - 1]:
            continue
        xs.append((dm(ms[i]) / dm(ms[i - 1]) - 1) * 100)
        ys.append((vs[i] / vs[i - 1] - 1) * 100)
    n = len(xs)
    if n < 24:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0 or n <= 2:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    sse = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys))
    se = (sse / (n - 2) / sxx) ** 0.5
    if se <= 0:
        return None
    return {'slope': b, 'se': se, 't1': (b - 1) / se, 'r2': 1 - sse / syy, 'n': n}


_SPAN = _span()                      # (首月, 末月, 月数) —— 所有「N 个月」的唯一来源
_DMG = _splice_damage()              # 「接前身会坏掉哪几格」的算式结果
_SHARE_ATM = _facts.share_range(_CSV, _COL_ATM, _COL_TOT)
_SHARE_NON = _facts.share_range(_CSV, _COL_NON, _COL_TOT)
_GAP = _split_gap()
_IMP = _implied_fx()
_CG = _contrib_gap()
_MOPS = _mops_remarks()
_ID = _identity()
_D = _facts.days_effect(_CSV, _COL_TOT)
_FIT = _days_dispersion()
# 注：色阶拥挤度**不再**在这里算（原为 _facts.yoy_extremes(_CSV, _COL_TOT)）——
# 那是全序列的分位，而引擎的 5/95 只看热力矩阵那张图实际用的 matrix。底座已按
# matrix 现算并印在该图图注里，spec 侧再留一份只会在窗口滚动后与它对不上。
# 见 _HEAT_EXTRA 末尾。


# ══════════════════════════════════════════════════════════════════════════════
# 图注。凡是随数据变的数一律来自上面几个现算结果，拿不到就退回定性版本；
# 凡是引用某份**具名、有日期**的官方文件里的数（公司自印的 pro forma、20-F 的
# 并购贡献额）不随本页窗口变，属于**引证**不属于统计量，照引并标出处。
# ══════════════════════════════════════════════════════════════════════════════

# ── ① 主线为什么是「合并」——任务点名要写进**这张图自己的图注**（note_extra）─────
_MAIN_LINE_NOTE = (
    '<b>柱高与右轴金线仍然只由「合并」那一列决定，分色只是把它拆开给你看，'
    '没有换主序列 —— 这是一个有代价的选择，代价也写在下面。</b>'
    '（柱按 ATM／非 ATM 分色堆叠之后，页上的主序列<u>一格没变</u>：'
    '柱顶那个数、金线、汇总表的 QTD／YTD、季度桥、热力矩阵，'
    '取的都还是合并那一列。）'
    '<b>颜色分工</b>：柱上两段是蓝（ATM）与灰（非 ATM），'
    '<b>金色在本图只有一处</b> —— 右轴那条滚动同比线，它是比率不是金额，'
    '不属于任何一段柱。'
    '选合并的四条理由，每条都可复核：'
    '① 合并是台湾《证券交易法》强制公告项，在<b>三个互相独立的源</b>上都取得到并对得上'
    '（公司新闻稿 PDF、MOPS 全市场月表、TWSE OpenAPI <code>t187ap05_L</code>）；'
    'ATM 只出现在公司自己的新闻稿里，没有第二个源可以核。'
    '② 合并逐月加总<b>无需任何调整</b>就等于 20-F 的年度合并营收'
    '（SEC XBRL <code>ifrs-full:Revenue</code>，FY2019–FY2025 七个完整年最大绝对差'
    '不到 2 百万，全是百万位四舍五入）—— 本页的季度桥、QTD、YTD、'
    f'{_Y.TTM_WIN if _Y else 12} 个月滚动同比这四道加总，只有在这一列上才是合法的。'
    '③ ATM 是<b>分部基础</b>（含分部间交易），对不上合并利润表里任何一行；'
    '而且它被<b>追溯重述</b>过（2019-05~08 每月 −90 ~ −100 百万，2019-09 期落地，'
    '当期 ATM 表标题带星号说明），合并列在同批新闻稿里一处都没变。'
    '主序列应当是没有重述史的那条。'
    '④ 底座只有一条主序列，QTD／YTD／TTM／热力矩阵全部由它派生；把两块业务的口径'
    '混进同一条派生链，出来的数没有一个说得清是谁的。'
    + (f'<b>代价：合并读不出封测景气。</b>最新月两条口径的差已经很大 —— '
       f'{_Y.TTM_WIN if _Y else 12} 个月滚动同比合并 {_GAP["ttm_tot"]:+.1f}%、'
       f'ATM {_GAP["ttm_atm"]:+.1f}%，单月同比合并 {_GAP["mom_tot"]:+.1f}%、'
       f'ATM {_GAP["mom_atm"]:+.1f}%；'
       if _GAP else '<b>代价：合并读不出封测景气。</b>')
    + '全历史的差距分布（含它<b>什么时候反过来</b>）在页尾「合并线与 ATM 线的差距」'
    '一条里现算列出。ATM 并没有从页上消失，要读封测有<b>五处</b>：'
    '本图的蓝色堆叠段、分部占比那张图的 ATM 占比线、全历史图上的 ATM 线、'
    '汇总表的 ATM 行、核对表的 ATM 列。'
    '<b>但本图这两段不是两个对等的官方分部</b>：蓝段是公司披露的 ATM 分部，'
    '灰段是<b>合并 − ATM 的残差</b>（≈ EMS + Others − 分部间抵销），'
    '不是「EMS 分部」这个官方口径 —— 堆叠柱把两段并排画在一根柱里，'
    '很容易让人以为公司披露了对等的两块，实际只披露了其中一块。'
    '口径细节见页尾「第三列写「非 ATM」而不是「EMS」」一条。'
    '<b>另外，本页的美元腿只有合并那一条</b>：公司每月也印 ATM 的美元数，'
    '但底座的外币腿只有一条，所以 ATM 美元不在页上任何一张图里 —— '
    '别把美元那两张图上的读数按分部去拆。')

# ── ② 代价的量化（页尾）—— 措辞由数据决定，不假设符号 ────────────────────────
if _GAP and _SHARE_ATM:
    _both_ways = _GAP['t_pos'] not in (0, _GAP['t_n'])
    _SPLIT_NOTE = (
        f'<b>合并线与 ATM 线的差距有多大 —— 现算，不是印象。</b>本序列 '
        f'{_SHARE_ATM["n"]} 个月里 ATM（封测及材料）占合并 '
        f'<b>{_SHARE_ATM["min"]:.1f}% ~ {_SHARE_ATM["max"]:.1f}%</b>、'
        f'中位 {_SHARE_ATM["med"]:.1f}%，最新月 {_SHARE_ATM["cur"]:.1f}%。'
        f'把两列各自的 <b>{_Y.TTM_WIN if _Y else 12} 个月滚动同比</b>相减'
        f'（口径统一走 <code>build/yoy.py</code>），{_GAP["t_n"]} 个可比月份上'
        f'「ATM − 合并」落在 <b>{_GAP["t_lo"]:+.1f}pp ~ {_GAP["t_hi"]:+.1f}pp</b>，'
        f'其中 {_GAP["t_pos"]}/{_GAP["t_n"]} 个月为正。'
        + (f'<b>注意这个差是双向的</b>：ATM 并非总是跑得更快，'
           f'历史上合并口径最多曾高出 ATM {abs(_GAP["t_lo"]):.1f}pp'
           f'（EMS 侧强、封测弱的那几年）—— 所以「把合并线当封测读一定会低估」'
           f'这句话在全历史上是假的，只在当下这一段成立。'
           if _both_ways and _GAP['t_lo'] < 0 else '')
        + f'当下这一段是单边的：最近 {_GAP["t12_n"]} 个月里 '
          f'{_GAP["t12_pos"]}/{_GAP["t12_n"]} 个月 ATM 更快，'
          f'差 {_GAP["t12_lo"]:+.1f}pp ~ {_GAP["t12_hi"]:+.1f}pp；'
          f'换成单月口径同一段窗口差 {_GAP["m12_lo"]:+.1f}pp ~ {_GAP["m12_hi"]:+.1f}pp，'
          f'全历史 {_GAP["m_n"]} 个月则宽到 {_GAP["m_lo"]:+.1f}pp ~ {_GAP["m_hi"]:+.1f}pp。'
          '<b>结论：本页的同比读数是「日月光投控这家控股公司」的增速，不是封测的增速。</b>'
          '要读封测有五处：月营收柱图的蓝色堆叠段、分部占比那张图的 ATM 线、'
          '全历史图上的 ATM 线、汇总表的 ATM 行、核对表的 ATM 列。'
          '<b>五处都是新台币</b>：公司每月连 ATM 的美元数也印，但页上的美元腿只有'
          '合并那一条（底座的外币腿只有一条），所以美元那两张图不能按分部拆着读。')
else:
    _SPLIT_NOTE = (
        '<b>合并线与 ATM 线的差距。</b>ASEH 的合并营收由 ATM（封测及材料）与'
        '非 ATM（环旭 USI 的电子代工及其他）两块拼成，两块的客户与周期完全不同，'
        '合并同比因此读不出封测景气。本次未能从 CSV 现算出两条线的同比差，'
        '故只作定性表述 —— 请直接对读全历史图上的两条分部线。')

# ── ③ 第三列是残差，不是官方 EMS 分部 ───────────────────────────────────────
_CALIBER_NOTE = (
    '<b>第三列写「非 ATM」而不是「EMS」，是口径不是措辞。</b>'
    '月度新闻稿只给两个数：合并总额与 <b>ATM 分部</b>营收（分部基础，含分部间交易）。'
    '本表第三列 = 合并 − ATM'
    + (f'（在全部 {_ID["n"]} 个月上与这个减法<b>逐月恒等</b>，现算最大绝对差 '
       f'{_ID["max"]:.0f} NT$mn）' if _ID else '')
    + '，等于「EMS 分部 + Others − ATM 分部间抵销」，<b>不等于</b>合并利润表里的 EMS 行，'
      '也不等于公司季度附注里的 EMS 分部基础数；同理 ATM 那一列也不等于合并利润表的 '
      'Packaging + Testing + Others。官方分部数不在 <code>series/ase.csv</code> 里，'
      '本页构建期读不到，所以这里<b>只作定性陈述、不印一个写死的差额</b> —— '
      '要逐季对差额请自行取 20-F 或法说会 deck 的分部表。'
      '叫它「EMS」省事，但那是在口径上说谎。'
      '<b>本轮起这件事在图上更容易被读错，所以两张图的图注里各写了一遍</b>：'
      '月营收柱改成了 ATM／非 ATM 分色堆叠，分部占比那张图又把两条占比线并排画 —— '
      '两种画法都在<b>视觉上</b>把两段做成对等的两个官方分部，'
      '而事实是<b>公司只披露其中一段</b>，另一段是减出来的残差。'
      '残差这一侧的任何异动都可能只是 ATM 侧口径变了（含它被追溯重述的那几个月），'
      '与 EMS 的经营无关。')

# ── ④ 构成随年份变化很大 ────────────────────────────────────────────────────
if _SHARE_NON:
    _MIX_NOTE = (
        f'<b>「EMS 大约占三分之一」这句话对本序列的多数年份是错的。</b>'
        f'非 ATM 残差占合并的实测区间是 '
        f'<b>{_SHARE_NON["min"]:.1f}% ~ {_SHARE_NON["max"]:.1f}%</b>'
        f'（中位 {_SHARE_NON["med"]:.1f}%，最新月 {_SHARE_NON["cur"]:.1f}%，'
        f'{_SHARE_NON["n"]} 个月）—— 三分之一上下只是最近这一段的情形。'
        f'区间这么宽是有结构原因的：2020-12 FAFG 并入把非 ATM 抬上去一级，'
        f'2021-12 处分中国四厂把 ATM 削下去一块，两次都改写了配比。'
        f'跨年比较「日月光的营收增速」之前，先看这一行占比走到哪了。'
        f'本轮起这件事有了自己的一张图（分部占比时序），逐月的位移在那张图上直接可读，'
        f'不必再靠两条绝对量线目测。')
else:
    _MIX_NOTE = (
        '<b>营收构成随年份变化很大</b>：2020-12 FAFG 并入抬高非 ATM 侧，'
        '2021-12 处分中国四厂削减 ATM 侧，两次都改写了两块业务的配比。'
        '跨年比较增速之前先看构成。（本次未能从 CSV 现算出占比区间，故只作定性表述。）')

# ── ⑤ 断点竖线在「有分部的那几张图」上各自意味着什么（逐图挂，措辞不同）─────
#    ⚠️ 三张图上这条 caveat **不是同一句话**，不许复用一份：
#      · 全历史图（分部线）与月营收柱（堆叠段）：两条断点各只落在一侧，另一侧那条线
#        （那一段）根本不受影响 —— 所以红线在图上是「过度标注」。
#      · 分部占比图：占比 = 分部 ÷ 合并，**分母一动两条线都动** —— 同一条红线在那里
#        是「标得不够」，反过来了。把上面那句搬过去就是一句假话。
_SEG_LINE_NOTE = (
    '<b>本图上那两条红色竖虚线只对合并线（NAVY）成立。</b>底座把断点画在每一张有连续'
    '时间轴的图上，而本图除合并线外还有两条分部线 —— 实测两条断点各只落在一侧：'
    '2020-12 的 FAFG（Asteelflash）并入影响合并与非 ATM，<b>ATM 那条线不受影响</b>；'
    '2021-12 的中国四厂处分影响合并与 ATM，<b>非 ATM 那条线不受影响</b>'
    '（公司自印的 pro forma 里合并与 ATM 两侧减项分毫相同，残差未动）。'
    '引擎没有「只标某一条线」的图元，所以这件事只能写在这里。'
    '<b>同一句话不能搬到分部占比那张图上</b>：那里画的是「分部 ÷ 合并」，'
    '分母一动两条线一起动，红线在那边是标得不够而不是标得太多 —— '
    '措辞已在那张图自己的图注里另写了一份。')

_MIX_RESID_NOTE = (
    # 底座本轮把「分部列本身才是披露值」那句从 Ex5 图注里删了（对本页第二段是假话），
    # 改成指向「本注下方各家自己的说明」——**那就是这一段**。底座不再兜底，
    # 所以这一段必须自己把「哪一列是披露值、哪一列是残差」讲完，不能只讲后果。
    # ⚠️ 不写「接上一句」：断点样板句本轮起插在这一段之前，「上一句」已经不是那句了。
    #    指向**本图注开头那句**，与排版顺序无关。
    '<b>回答本图注开头那个问题（「哪一列是官方披露值、哪一列是残差」）：'
    '本页两条线不是两个对等的官方分部，只有 ATM 那条是公司披露的。</b>'
    '月度新闻稿逐月只印两个数 —— 合并总额与 ATM 分部营收；'
    '「非 ATM」是<b>减出来的残差</b>（合并 − ATM ＝ EMS 分部 + Others − 分部间抵销），'
    '不等于合并利润表的 EMS 行，也不等于公司季报附注里的 EMS 分部基础数。'
    '把两条占比线并排画在同一张图上，视觉上像是把一块蛋糕切成两块官方口径，'
    '<b>实际是「一块披露值 + 一块余数」</b>；余数那条线的任何异动，'
    '都可能只是 ATM 那一侧的口径动了（含 2019 年那次对 ATM 的追溯重述），'
    '与 EMS 的经营无关。<b>并且两条线互为镜像</b>（和恒为 100%），'
    '所以它们不是两个独立的观测，是同一个数的两种写法。')

_MIX_BREAK_NOTE = (
    # ⚠️ 底座本轮把断点样板句挪到了 note_extra **之前**（就是为了这一段）。所以这里
    #    必须**明写是在接哪一句**：样板句说的「ATM 不受影响 / 非 ATM 不受影响」讲的是
    #    **绝对金额**，在全历史图上成立；本图画的是占比，那两句要反过来读。
    #    不点名承接的话，读者刚读完样板句就撞上一句相反的话，会当成页面自相矛盾。
    '<b>⚠️ 上面那两条断点说明是全页通用的样板句，在本图上要反过来读。</b>'
    '它写的「ATM 不受影响」「非 ATM 不受影响」说的是那一块的<b>绝对金额</b> —— '
    '在全历史图（画金额）上确实如此：2020-12 的并入只动合并与非 ATM、'
    '2021-12 的处分只动合并与 ATM，所以那里两条红线各自只对其中一条分部线成立。'
    '但本图画的是<b>占比</b>（分部 ÷ 合并），<b>分母就是合并</b> —— '
    '合并一变，两条占比线<u>同时</u>被推着走，哪怕某个分部的绝对金额一格没动。'
    '举例：2020-12 起合并多了 FAFG，ATM 的绝对量完全没变，'
    '但它的占比当月就被摊薄了；2021-12 起合并少了中国四厂，非 ATM 绝对量没动，'
    '占比却被抬起来。<b>所以本图上跨这两条红线的位移，不能读成「哪一块在赢」</b>，'
    '要先回月营收柱图与全历史图看绝对量。')

# ── ⑥ 并购门槛：红线是判断，不是穷举 ────────────────────────────────────────
_M_AND_A_NOTE = (
    f'<b>红色竖虚线是<u>按门槛</u>画的，不是并购事件的穷举 —— 门槛写在这里供复核。</b>'
    f'判据：并表／处分对<b>当月合并营收</b>的影响 ≥ <b>{BREAK_DRAW_MIN_PCT:.0f}%</b> 才画线。'
    f'过线因而已画的两条：'
    f'<b>2020-12</b> FAFG（Asteelflash）并入 —— 20-F 披露该主体自 2020-12-01 至月末'
    f'计入合并的营收 NT$2,043 百万，约当月合并的 4.1%；'
    f'<b>2021-12</b> 中国四厂（ASEN／ASEKS／ASEWH／Advanced Shanghai）处分'
    f'（2021-12-16 交割）—— 公司自印的 pro forma 显示当月合并 −2,289 百万（−3.8%），'
    f'且减项<b>全部落在 ATM</b>，非 ATM 分毫未动。'
    f'<b>未过线、因此不画线但在此登记</b>的三条：'
    f'<b>2023-10-27</b> Hirschmann（HCC）并入，20-F 披露自并购日至年末营收 '
    f'NT$1,017 百万，折合约当时月度合并的 0.9%；'
    f'<b>2024-08-01</b> ASEPCAYMAN（菲律宾）与 CHE（韩国天安）并入，同期合计 '
    f'NT$1,343 百万，折合约 0.5%；'
    f'<b>2020-10</b> SF（Siliconware Electronics (Fujian)）处分完成 —— '
    f'⚠️ 这一条的营收贡献 <b>20-F 没有单独披露</b>，把它放在门槛之下是依对价量级'
    f'（RMB966 百万）作的<b>推断</b>，不是实测；日后若查到它的月营收量级过线，'
    f'这条要补画红线。'
    f'量级可交叉印证：同一份 20-F 的 pro forma 显示，把上述并购视同期初完成，'
    f'FY2023 营收会高 0.79%、FY2024 高 0.27%。'
    f'把 0.3%~0.9% 的事件也画成红线，页面会变成「什么都不可比」，反而盖掉真正 −3.8% '
    f'的那一条 —— <b>所以这是判断，不是遗漏</b>。出处：ASEH 2021 年度 Form 20-F'
    f'（Note 29／Note 30／Item 4）、2025 年度 Form 20-F（Note 29「Impact of '
    f'acquisitions」表），以及公司 2022-01 期月度新闻稿的 Pro Forma Basis 表。')

# ── ⑦ 跨断点的同比是伪同比，幅度公司自己印过 ────────────────────────────────
_BREAK_YOY_NOTE = (
    '<b>跨断点的同比是伪同比，幅度由公司自己印出来过。</b>'
    '公司在 2022 全年每期月报里多印一组「排除已处分中国四厂」的 Pro Forma 表，'
    '就是因为知道这件事：以 2022-01 期为例，合并 y/y 报告值 <b>+18.9%</b>、'
    'pro forma（可比口径）<b>+24.7%</b>，差 5.8 个百分点；'
    'ATM 侧报告 +10.7% vs pro forma <b>+19.8%</b>，差 <b>9.1 个百分点</b>。'
    '本序列<b>不做追溯调整</b>（官方从未按月重述月营收，自己调一版会得到一条外部'
    '无法复核的序列，那比留着断点更糟），只把断点登记出来 —— '
    '读 2021 与 2022 那两列同比时，请自行把这个量级放在心里。'
    '出处：ASEH 2022-01 期月度新闻稿（电头 2022-02-10）Pro Forma Basis 表。')

# ── ⑧ 汇率：三张图都出，四段分工如下 ────────────────────────────────────────
#    · _FX_LINES_NOTE   → 本币 vs 美元那张图的图注末尾：这两条线为什么<u>互推不出来</u>。
#    · _FX_CONTRIB_NOTE → 汇率贡献那张图的图注末尾：这根柱是观测值；顺带印出「若按别家
#                         那样用外部牌价折」会差多少 —— 那是本仓其余六家的处境。
#    · _FX_RATE_NOTE    → 汇率线那张图的图注末尾：这条线是什么、**不是**什么。
#    · _USD_FILED_NOTE  → 页尾：本家与其余六家不同的那件事实（有官方美元实绩）。
#
#    ⚠️ 这四段里的百分数**全部构建期现算**（`_implied_fx()` / `_contrib_gap()`）。
#      上一版里它们是写死的，理由是「那两列美元不在 series/ase.csv 里，读不到」——
#      现在读得到了，就没有任何写死的理由。对**具名、有日期**的官方文件的引证
#      （20-F 的并购贡献额、公司自印的 pro forma）不在此列，那不是随窗口滚动的统计量。
_FX_LINES_NOTE = (
    '<b>这两条线互相推不出来。</b>底座为这张图分了三支（<code>mrbase.legs()</code>），'
    '本页走的是第三支 —— 三支的差别正是「那条美元线是从哪来的」：'
    '① /tsm/：美元线是「新台币 ÷ 外部牌价」<u>折出来</u>的，两条线之间是一个'
    '<b>构造出来的</b>算术关系（美元线按定义就等于本币线除以那条汇率）。'
    '② /alchip/（世芯-KY）：两条线都是官方申报值，但由公司<b>自己申报的换算汇率</b>'
    '绑在一起 —— 官方页脚写明「本月新台幣 ＝ 本月功能性貨幣 × 本月換算匯率」，'
    '所以互推<b>精确成立</b>。'
    '③ <b>本页</b>：两条线背后的两列金额也都是官方值，'
    '但中间<b>没有任何一个汇率把它们绑起来</b> —— '
    '公司在同一份新闻稿里印了两次，却从不说自己用了什么汇率。'
    # ⚠️ **不要在这里手抄线名**，也不要说后缀讲的是「金额的来历」——两处都错过：
    #   ① 图上根本没有 `as filed` 这个线名。两条线实际叫
    #      `NT$ revenue y/y (computed)` 与 `US$ revenue y/y (computed from as-filed US$)`；
    #      印 `US$ revenue y/y (as filed)` 的是 /alchip/ 那一页。
    #   ② 底座的成文规矩是「`as filed` 说的是**这条同比**是不是公司报的，
    #      **不是那一列金额**」。按「金额来历」读，NAVY 线的 computed 就等于说
    #      「新台币那一列金额是我们算出来的」——与同页三处正面冲突。
    '（<b>线名要分开读</b>：两条线的后缀说的是<u>这条同比</u>是不是公司报的 —— '
    '本页没有登记 <code>official_yoy</code> 列，所以两条同比都由 '
    '<code>build/yoy.py</code> 现算，线名分别是 <code>NT$ revenue y/y (computed)</code> '
    '与 <code>US$ revenue y/y (computed from as-filed US$)</code>；后者括号里的 '
    '<code>as-filed</code> 指的是<u>它的分子分母</u>是公司自印的美元金额，'
    '不是说这条同比是公司报的。）'
    # ⚠️ 偏离的**统计量不在这里印**：本轮起底座把那条「公司自印两列之商」直接画进了
    #    汇率那张图，并在它自己的图注里现算出全套（偏离区间、正负计数、超出舍入上界的
    #    月份数）。同一组数在同一页上印两遍，读者会当成两个独立论证。这里只留
    #    **那边没有的**一个量：反解出来的比值本身落在哪个区间。
    + (f'那两列金额相除得到的比值（新台币 ÷ 美元）{_IMP["n"]} 个月落在 '
       f'<b>{_IMP["lo"]:.2f}</b>（{_IMP["lo_m"]}）到 <b>{_IMP["hi"]:.2f}</b>'
       f'（{_IMP["hi_m"]}）之间、中位 {_IMP["med"]:.2f} —— 量级像汇率，'
       f'但它与外部牌价<b>逐月对不上、符号还在翻</b>，'
       f'差多少、为什么连四舍五入都解释不掉，'
       f'见本页「外部月均牌价 vs 公司自印两列之商」那张图（红线就是这个比值）。'
       if _IMP else
       '（本次未能从 CSV 现算出这两列相除的区间，故此处只作定性表述。）')
    + '<b>所以上面那句「还原不出这条美元线」不是定性说法</b>，'
      '也不要反过来把那个比值当成「公司用的汇率」—— 它只是两个印出来的数之商，'
      '真值公司从不披露，本页也不假装知道。'
    + '<b>本图两条线都只讲合并口径</b>：公司每月连 ATM 的美元数也印，'
      '但底座的外币腿只有一条，页上没有分部美元线 —— 本图的差额不能按分部去拆。')

_FX_CONTRIB_NOTE = (
    '<b>这根柱是<u>观测值</u>，不是折算的产物。</b>它等于「新台币单月同比 − 美元单月同比」，'
    '两个同比都由 <code>build/yoy.py</code> 现算，而<b>喂给它的两列金额</b>'
    '各自印在公司<b>同一份月度新闻稿</b>的两张表上 —— '
    '页面没有引入任何汇率，也没有做任何折算：这根柱之所以是观测值，'
    '是因为两头的<u>金额</u>都是公司自己给的，不是因为同比是公司算的'
    '（本页没有公告同比列，同比一律自算）。'
    '<b>/tsm/ 那页的同一张图不是这么来的</b>：那边没有官方美元实绩，'
    '只能拿新台币 ÷ 外部牌价折一条美元线出来，柱高因此依赖'
    '「全部营收按当月平均汇率一次性折算」这个假设。'
    '（/alchip/ 那页是第三种：两条腿也都是官方值，但由公司自己申报的换算汇率绑定。）'
    + (f'<b>那个假设差多少 —— 本页把反例现算出来给你看</b>：把本家也按那种折法算一遍，'
       f'{_CG["cur_m"]} 的贡献会是 <b>{_CG["cur_d"]:+.1f}pp</b>，'
       f'而公司口径（本图画的）是 <b>{_CG["cur_f"]:+.1f}pp</b>，'
       f'折出来的那条{"高" if _CG["cur_gap"] < 0 else "低"}了 {abs(_CG["cur_gap"]):.1f}pp；'
       f'上一个月（{_CG["prev_m"]}）两者是 {_CG["prev_f"]:+.1f}pp（公司）'
       f'vs {_CG["prev_d"]:+.1f}pp（折算），相差 {abs(_CG["prev_gap"]):.1f}pp。'
       f'{_CG["n"]} 个可比月份上这个差的绝对值中位 {_CG["medabs"]:.2f}pp、'
       f'最大 <b>{_CG["maxabs"]:.2f}pp</b>（{_CG["maxabs_m"]}），'
       f'有 <b>{_CG["ge1"]} 个月</b>差到 1pp 以上 —— '
       f'而本图整幅量程也不过从 {_CG["lo"]:+.0f}pp 到 {_CG["hi"]:+.0f}pp。'
       f'<b>结论不是「/tsm/ 那张图错了」</b>（没有官方美元时那是唯一能画的），'
       f'而是：那种折法的误差量级在本家可以被<u>直接测出来</u>，就是上面这些数。'
       if _CG else
       '（本次未能从 CSV 现算出「公司口径 vs 外部牌价推导」的差，故此处只作定性表述。）')
    + '<b>另外，这根柱不是公司受到的汇率冲击。</b>它只说明「以新台币计的那个头条数'
      '被汇率抬高/压低了多少」；真正的暴露在成本端与对冲上，月营收公告看不见。')

_FX_RATE_NOTE = (
    # ⚠️ 本轮底座给这张图加了**第二条线**（红色，公司自印两列之商），并把偏离统计
    #    整段现算印在上面。所以这里**只写底座没写的**，不重复那组数：
    #      · 图上「红线」与其余各图上「红色竖虚线」是两回事 —— 必须先拆开，
    #        否则上一段刚说「红色是两列之商」，这里再说「本图没有红色竖虚线」就像打架；
    #      · ATM 那一组的交叉验证（底座只看合并那一组）；
    #      · 20-F 里「汇率为什么对本家要紧」的原文。
    # ⚠️ 图脚第一句是底座给 rate_filed=False 的家统一印的「本图与月营收公告无关」。
    #    那句话在**单线**的家上成立，在本图上只对深藏青那条成立 —— 红线整条都出自
    #    月营收公告。底座那句七页共用，不改它，在这里限定它的适用范围。
    '<b>图脚第一句「本图与月营收公告无关」说的是深藏青那条</b>（它是外部牌价，'
    '与本家披露什么无关）；<b>红线恰恰相反 —— 它整条都来自月营收公告</b>，'
    '就是公告里那两列金额相除。'
    '<b>另外先分清本图上的两种红。</b>图上那条红线是<u>数据</u>（就是上一段说的'
    '「公司自印两列之商」），<b>不是断点标注</b>；断点标注是<b>竖直的虚线</b>，'
    '<b>本图一条都没有，这是刻意的</b>：本页登记的两个断点是'
    '<b>日月光自己的并表与处分</b>（2020-12 FAFG 并入、2021-12 中国四厂处分），'
    '而新台币兑美元是一条<b>宏观序列</b>，不会因为哪一家公司的合并范围变了而断，'
    '所以底座不把它们画到这张图上。那两条竖线出现在本页其余各图上，'
    '那里它们才成立（见页尾「口径断点与截轴」）。'
    + ((f'<b>上一段说「每月一个统一汇率与数据相容、但相容不等于唯一」—— '
        f'本页还能给它一个交叉验证。</b>公司同一份新闻稿里还印了 <b>ATM 分部</b>的'
        f'新台币与美元；拿那一组也相除，得到的比值与本图这条红线'
        f'<b>逐月最大只差 {_IMP["seg_gap"]:.3f}</b>（NT$ per USD，'
        f'{_IMP["n"]} 个月现算，量级与两列取整本身的不确定相当）。'
        f'两个不同汇总层级得出同一个比值，说明公司内部<u>确实存在</u>一个每月统一的'
        f'换算口径；但这仍然<b>不能</b>把红线钉成牌价表上的某一个数 —— '
        f'营收加权的复合比率同样会在两个层级上一致，只要两块业务的币别结构接近。')
       if _IMP and _IMP.get('seg_gap') is not None else '')
    + '<b>所以深藏青那条只能读作「新台币兑美元的宏观走势」</b>：'
      '它是理解那两条营收线为什么分岔的<u>背景</u>，'
      '不是把其中一条换算成另一条的<u>算子</u> —— '
      '本页没有任何一个营收数是拿它折出来的。'
    '<b>那汇率对本家到底要紧吗 —— 要紧，而且公司自己这么说</b>：2025 年度 Form 20-F '
    'Item 5「Pricing and Revenue Mix」写 "The majority of our prices and revenues is '
    'denominated in U.S. dollars."，Item 11 又写 "against the NT dollar, '
    'our functional currency" —— 功能货币是新台币、多数营收以美元计价，'
    '所以这条线直接推动本页那些新台币柱的增速。'
    '<b>原文没有给百分比</b>（只说 "the majority"），本页也就不编一个。')

_USD_FILED_NOTE = (
    f'{_FGN_TXT}本轮已落库并上图。'
    '（<u>不是</u>「唯一有官方美元数」：世芯-KY 的功能货币本身就是美元，'
    '它那页的美元栏是计量本身、新台币栏才是官方折算 —— 那是另一种形态，'
    '两栏由公司申报的换算汇率绑定；本家是两次<b>互不绑定</b>的披露。）'
    '月度新闻稿逐月印一张 <code>US$ Million</code> 表（合并与 ATM 各一行），'
    f'现已作为 <code>{_COL_USD}</code> / <code>{_COL_ATM_USD}</code> 两列存进 '
    '<code>series/ase.csv</code>；页上的美元腿由 <code>fx.fgn_col</code> 直接读'
    '<b>合并</b>那一列，<u>没有做任何折算</u>。'
    '<b>本页因此比台积电那页硬在三处</b>：'
    '① 美元线是<b>公司披露值</b>，可以拿去和新闻稿逐格对，'
    '而 /tsm/ 那条是「本币 ÷ 外部牌价」的推导值，无官方数可核；'
    '② 汇率贡献那根柱是两次独立披露之差，是<b>观测</b>；'
    '/tsm/ 那根柱依赖「全部营收按当月平均汇率一次性折算」这个假设。'
    '③ 抬头与页顶 brief 里的「美元口径 y/y」，分子分母两头都是<b>公司印的美元金额</b>，'
    '不是任何折算值的同比。'
    '⚠️ 但那个<b>同比本身仍是本页自算的</b>（<code>build/yoy.py</code>；'
    # ⚠️ 线名照实抄，别写 `as filed` —— 那是 /alchip/ 那一页的线名。本页两条线的
    #    后缀都带 computed，因为**两条同比都是本页算的**（本家没有 official_yoy）。
    '本页没有登记 <code>official_yoy</code> 列，所以「本币 vs 美元」那张图的两条线名'
    '都带 <code>computed</code>：新台币线是 <code>NT$ revenue y/y (computed)</code>，'
    '美元线是 <code>US$ revenue y/y (computed from as-filed US$)</code> —— '
    '后者括号里的 <code>as-filed</code> 说的是<b>它的分子分母</b>是公司自印的美元金额，'
    '<u>同比本身仍是本页算的</u>）。'
    '与公司自己印在同一份新闻稿上的 y/y 之差只来自「先四舍五入到整数再相除」这一步，'
    '量级见页尾「公司确实公告同比」一条。'
    '<b>代价与边界也说清楚</b>：(a) 页上的美元腿只有<b>合并</b>一条，'
    'ATM 的美元列虽然落了库，但底座的外币腿只有一条，它<u>不在任何一张图上</u>；'
    '(b) NTD/USD 那张图上<b>深藏青</b>那条仍是<b>外部牌价</b>，公司从不披露自己用的汇率，'
    '所以 <code>fx.rate_filed</code> 显式为 <code>False</code>，'
    '页上任何一处都不会把<b>它</b>称作「公司申报的换算汇率」'
    '（同图那条<b>红线</b>是本页两条官方营收腿相除得到的比值，'
    '同样不是谁申报的汇率 —— 那张图自己的图注把能证明与不能证明的都写清楚了）；'
    '(c) 由此，<b>「本币 ≡ 美元 × 汇率」这条恒等式对本家不成立</b>，'
    '本页也没有任何一处算式依赖它；'
    # 注：页尾「数据源」那条现在把字段清单现算出来，且「非 ATM」那一项自带「残差」
    #    二字 —— 本页另外三处（月营收柱、分部占比、第三列口径那条）也都讲了这件事，
    #    所以这里**不再重复更正**，只说清单里「官方外币栏」指的是哪一列。
    '(d) 页尾「数据源」那条现算出来的字段清单里，「官方外币栏」指的就是这一列 —— '
    '它与合并、ATM 并列，<u>不是</u>从其中任何一列派生出来的。'
    + (f'<b>这件事在核对表上可以自己验一次</b>：那张表把 <code>NTD per USD</code> 与 '
       f'<code>Revenue (US$mn, as filed)</code> 两列并排放着，很难不去乘一乘 —— '
       f'{_IMP["cur_m"]} 是 {_IMP["cur_fx"]:.4f} × {_IMP["cur_usd"]:,.0f} = '
       f'<b>{_IMP["cur_prod"]:,.0f}</b>，而同一行左边公司印的合并营收是 '
       f'<b>{_IMP["cur_tot"]:,.0f}</b> NT$mn，差 {_IMP["cur_prod"] - _IMP["cur_tot"]:,.0f}'
       f'（{(_IMP["cur_prod"] / _IMP["cur_tot"] - 1) * 100:+.1f}%）。'
       f'<b>这不是哪一列印错了</b>，是这三列本来就不构成一个恒等式。'
       if _IMP else '')
    + '<b>落库口径</b>：取新闻稿正文的实际表，<u>不取</u> 2022 年那批「排除已处分中国四厂」'
    'pro forma 表 —— 那组表的美元侧也印，当月那一格与实际表完全相同、只有 y/y 那一格不同，'
    '所以真正会被污染的是经 2022 各期 y/y 反推出来的 2021 年（取错会偏低数个百分点）。'
    'ATM 的美元列有 5 个月被公司追溯重述（2018-12、2019-05~08），落库取重述后值；'
    '合并的美元与新台币两列在同批复核里 0 处重述。')

# ── ⑨ 不做日均化：判据与台积电那页不同，特意没照抄 ──────────────────────────
if _FIT and _D:
    _sig = ('与 1 <b>在统计上分不开</b>' if abs(_FIT['t1']) < 2 else
            '与 1 <b>有显著差距</b>')
    _DAYS_NOTE = (
        '<b>本页不做日均化 —— 但本家的理由与台积电那一页<u>不同</u>，别照搬。</b>'
        f'把 <code>(m/m %) ~ (当月天数变化 %)</code> 在本序列 {_FIT["n"]} 个月上回归，'
        f'斜率 <b>{_FIT["slope"]:.2f}</b>（标准误 {_FIT["se"]:.2f}，对 1 的 t 值 '
        f'{_FIT["t1"]:+.2f}）—— 斜率{_sig}，也就是说「多一天多一天的产出」这个假设'
        f'在本家<b>没有被数据否掉</b>（台积电那页能否掉，本家不能，'
        f'所以那边「斜率 1.47 而不是 1」的措辞搬到这里就是编数据）。'
        f'不做日均化的理由换成下面三条：'
        f'① 天数只解释了月度波动的一部分 —— 这条回归的 R² 是 <b>{_FIT["r2"]:.2f}</b>，'
        f'剩下的 {1 - _FIT["r2"]:.0%} 与日历长短无关，除一遍天数并不会让这条线变干净。'
        + (f'② 除不掉的那部分里有农历年：2 月营收对相邻 1、3 月均值的实际比值是 '
           f'<b>{_D["feb"]:.2f}</b>（{_D["feb_n"]} 个年度平均），天数比值却有 '
           f'{_D["feb_days"]:.2f} —— 2 月比「短了几天」该有的样子还要弱约 '
           f'{(_D["feb_days"] - _D["feb"]) * 100:.0f} 个百分点。按天数除一遍，'
           f'会把这段农历年停工原样记成「经营性走弱」。'
           if _D else '② 除不掉的那部分里有农历年错位，按天数归一化会把它记成经营性走弱。')
        + '③ 还有一条与统计无关：本页各图印的是<b>公司公告的原值</b>，'
          '任何归一化都会让柱高不再等于新闻稿上的那个数。'
          '季节性请改用同月对同月定位（热力矩阵那一张）。')
else:
    _DAYS_NOTE = (
        '<b>本页不做日均化</b>：本页各图印的是公司公告的原值，任何归一化都会让柱高'
        '不再等于新闻稿上的那个数；而月度波动里农历年错位的部分远大于天数差本身，'
        '按天数除一遍会把停工记成经营性走弱。'
        '（本次未能从 CSV 现算出回归斜率与 R²，故只作定性表述。）')

# ── ⑩ 热力矩阵：跨断点那几行 + 可读性自检（挂在那张图自己的图注上）──────────
_HEAT_EXTRA = (
    '<b>这张图上没有断点红线，但跨断点的那几格同比一样不可比。</b>'
    '受影响的是 <b>2021 与 2022 两整行</b>外加 <b>2020 年 12 月那一格</b>：'
    '2020-12 起合并范围多了 FAFG（分子有、分母没有），2021-12 起少了中国四厂'
    '（分子没有、分母有）—— 这些格子是<b>伪同比</b>，'
    '格子照样按色标上色，'
    '<b>颜色深浅不代表那几格可比</b>；幅度见页尾「跨断点的同比是伪同比」一条。'
    + '（<b>颜色只用来找极值，不用来排序</b>：分位区间、最挤的那条色带塞了几格、'
      '以及换个口径会不会更好读，都在本图注上面那一段里 —— 底座构建期从<b>本表实际'
      '用的那张 matrix</b> 现算。本 spec <u>不</u>再另印一份：早先这里印过一组同名的数，'
      '算的是<b>全序列</b>而不是这张矩阵，今天两者恰好重合只是因为本页 '
      '<code>heat_years</code> 覆盖了全部有同比的月份，窗口一滚就会分叉。）')

# ── ⑪ 同比来源 ──────────────────────────────────────────────────────────────
_YOY_SOURCE_NOTE = (
    '<b>公司确实公告同比，只是本序列没存那一列。</b>月度新闻稿与 TWSE OpenAPI 都给 '
    'y/y（新闻稿印到一位小数，OpenAPI 给到小数点后十几位）。本页的单月同比是按'
    '<b>已四舍五入到百万</b>的金额自算的，与公司口径的差只来自这一步四舍五入，'
    '在新闻稿的一位小数上看不出来。把它记在这里是为了说明：'
    '本页的同比<b>不是</b>与公司口径互相独立的第二意见，它就是同一个数的重算 —— '
    '要拿它去挑公司公告的错，先把口径这一层想清楚。'
    '<b>美元那条线同理，而且舍入更粗</b>：美元列是公司印的<b>整数百万</b>，'
    + (f'基数比新台币列小约 {_IMP["med"]:.0f} 倍（这个倍数就是隐含汇率本身），'
       if _IMP else '基数比新台币列小一个数量级，')
    + '所以「先四舍五入再相除」在它身上留下的噪声更大 —— '
    + (f'实测同比的舍入误差上界中位 {_IMP["yy_noise_med"]:.3f}pp、'
       f'最大 {_IMP["yy_noise_max"]:.3f}pp（现算，不是估的）。'
       '相对本页汇率贡献那张图十几个点的量程仍可忽略，但它不是零，'
       '拿本页的美元同比去和公司新闻稿印的那一位小数逐格对时会看得见。'
       if _IMP else '这一项本次未能现算，故不给数。'))

# ── ⑪b 官方备注栏：本页两处空白的**理由**（页面不说话时，读者只会当成漏抓）────
if _MOPS:
    _REMARK_NOTE = (
        f'<b>本页核对表没有「觸發腿」与「本月備註（MOPS 原文）」两列，'
        f'页顶 brief 也没有那句官方备注 —— 不是没抓到，是公司确实一格没填。</b>'
        f'MOPS 月营收申报表的备注栏是<b>达标才必填</b>：当月同比或本年累计同比的绝对值 '
        f'≥ 50%（门槛写在该表脚注第 6 条）。本仓登记了本家 <b>{_MOPS["n"]} 个月</b>'
        f'（{_MOPS["first"]}~{_MOPS["last"]}）：'
        f'<b>触发 {_MOPS["trig"]} 次、填报 {_MOPS["filled"]} 次</b>'
        # ⚠️ 这两个数印**两位小数**，不是一位。三条理由缺一不可：
        #   ① 它们是 MOPS 申报栏的原样两位小数（43.15 / 25.13），本来就该照原样引；
        #   ② `.1f` 会把 43.15 印成 **43.1** —— IEEE-754 下 float('43.15')=43.1499…，
        #      落进 half-even 的下侧。而同一页另外 8 处（抬头、brief、汇总表两行、
        #      Ex2 与 Ex6 图注、核对表 Jul-26 行、页尾第 3 条）印的都是本页自算的
        #      **43.2**。一位小数下这两个数看着同源却对不上，而 43.1 既不是申报值、
        #      也不是真值的正确渲染 —— 任何来源都不支持它；
        #   ③ 两位小数还顺带让读者看得出这是**另一条来源**（公司申报值 vs 本页自算）。
        + (f'；同期两条腿的最大绝对值是 {_MOPS["max_yoy"]:.2f}%（单月）与 '
           f'{_MOPS["max_ytd"]:.2f}%（累计，均为 MOPS 申报栏原值），都没到 50%'
           if _MOPS['max_yoy'] is not None and _MOPS['max_ytd'] is not None else '')
        + '。底座只在近 13 个月里至少有一格备注非空时，才给核对表加「觸發腿」与'
          '「本月備註」<b>那两列</b>，所以本页两列都没有。'
        + (('<b>同一份库、同一窗口的横向对照（触发月数，构建期现算、不是手写名单）</b>：'
            + '、'.join(f'{nm} {c}' for nm, c in _MOPS['roster'])
            + f'（共 {len(_MOPS["roster"])} 家）。'
            '<b>「0 次」不等于「不说话」</b>，它的意思是没到过法定门槛。')
           if _MOPS['roster'] else '')
        + (('⚠️ <b>触发次数与填报次数也不是一回事</b>：'
            + '、'.join(f'{nm} 0 次触发却 {c} 个月都填了' for nm, c in _MOPS['boiler'])
            + '，而且逐月一字不变 —— 那是常设的折算口径注，'
            '<b>不是</b>对当月增减的说明；本家两个数都是 0。')
           if _MOPS.get('boiler') else '')
        + '⚠️ <b>两件事别混</b>：「本页没有那两列」是关于<b>本页状态</b>的陈述；'
        '「公司从不解释增减」是一句关于公司行为的断言，本页<u>不作</u>这个断言 —— '
        '门槛之外公司本就没有填报义务，没填不等于没话说。')
else:
    _REMARK_NOTE = (
        '<b>本页没有「本月備註（MOPS 原文）」那一列。</b>那一列只在公司真的填过备注时才出现，'
        '而备注栏是「当月或累计同比绝对值 ≥ 50% 才必填」的达标项。'
        '本次未能读到 <code>series/mops_remarks.csv</code>，所以这里不给次数 —— '
        '「本页没这一列」是本页状态，不等于「公司没填过」。')

# ── ⑫ 没有指引桥 ────────────────────────────────────────────────────────────
_NO_GUIDANCE_NOTE = (
    '<b>本页没有指引桥。</b>ASEH 每季法说会给的是「下季 ATM 新台币营收环比 +x%~+y%、'
    'EMS 环比约 +z%」这种<b>季度环比百分比区间</b>：没有绝对金额、没有月度分解、'
    '没有折算汇率假设。台积电那一页的指引桥依赖「美元绝对区间 + 公司假设汇率 + '
    '美元实绩」六列，在 ASEH 逐列无源 —— 形态对不上就不做，'
    '不拿一个环比区间硬折成月度绝对值来凑一句话。')

# ── ⑬ 数据源与落库口径 ──────────────────────────────────────────────────────
_SRC_NOTE = (
    '<b>数据源与落库口径。</b>数值取自 ASEH 官方英文月度新闻稿 PDF <b>正文</b>：'
    '两张 NT$ 表（<code>CONSOLIDATED NET REVENUES</code> 与 '
    '<code>ATM NET REVENUES</code>，2018-05~2018-12 叫 <code>IC-ATM</code>），'
    '外加<b>同一份 PDF 同一页</b>的 <code>US$ Million</code> 表 —— '
    '后者是本页美元腿的唯一来源。'
    + (f'全表（{_SPAN[2]} 个月 × 5 个数值列 = {_SPAN[2] * 5} 格）'
       if _SPAN else '全表（每月 5 个数值列）')
    + '由两套互相独立写的解析器各抽一遍、'
    '逐格比对，<b>0 处分歧</b>；美元两列的落库细节见页尾'
    '「ASEH …官方美元实绩」一条。'
    '<b>IR 落地页表格里印的金额不作数</b>：本轮（2026-08-13）现抓复现 —— '
    '落地页 2026 年那张表的 January 印的是 59,589，而同一网站挂的当期新闻稿 PDF 正文写 '
    '59,989，TWSE 的当年累计口径也指向 59,989。落地页只用来发现 PDF 链接。'
    '每份 PDF 同时印当月／上月／去年同月三个读数，所以每期都能给已入库的两个月做一次'
    '复核；本轮抽查 2019 年 4 期与 2022-01、2026-07 两期，共 18 个印出来的合并月值'
    '与本序列逐个相符。'
    '序列起点 2018-05 是<b>口径起点</b>不是「最早可得」：ASEH 控股 2018-04-30 才成立'
    '（SEC EDGAR 公司档案的更名记录），2018-05 是第一个合并月报 —— 所以短窗口图的'
    '左端是<b>数据边界</b>而不是窗口选择。<b>前身的月营收其实拿得到</b>，'
    '本页仍然不接，理由与代价见下一条。')


# ── ⑭ 为什么不把 2018-05 之前的前身接上来 ────────────────────────────────────
# ⚠️ 这一条是**决定的记录**，不是背景介绍。它存在的理由：上一版页面只说了
#    「主体不同、不可前接」，读者（与下一个接手的 agent）无从判断那是「查过了、
#    代价太大」还是「没查」。差别很大 —— 后者会被人「顺手补上」。
#    所以三条理由每条都带**可点开的出处**，量化部分要么是官方文件里的原值、
#    要么由 `_splice_damage()` 现算，本文件里不写死。
_PRE2018_NOTE = (
    '<b>本页不接 2018-05 之前的前身数据 —— 这是一个决定，不是一次抓取失败。</b>'
    'ASEH（3711）是 2018-04-30 由日月光（2311）与矽品（2325）以股份转换新设的控股'
    '公司，2018-05 是本主体的第一个合并月报；MOPS 不留已下市公司的历史，'
    '所以 3711 这个代号本身回不到 2018-04 以前。'
    '<b>但前身的月营收并不是取不到</b>：SEC 那边 ADR 按 Rule 12g-3 继受，'
    'EDGAR 只记了一次更名，前身与本主体<b>共用同一个 CIK 0001122411</b> —— '
    'Advanced Semiconductor Engineering, Inc. 的 6-K 序列最早到 <b>2000-10-30</b>'
    '（那一份是 2000Q3 财报），其中<b>月营收公告</b>最早一份是 2001-05-09 报送的 '
    '2001 年 4 月数（accession 0000950103-01-500934）。'
    '<b>接是接得上的，不接是因为代价。</b>'

    '<b>① 接缝是一个真实的水平台阶，而且台阶来自并表、不是经营。</b>'
    '前身自己印的 2018Q1：合并 NT$64,966 百万、ATM NT$37,072 百万'
    '（6-K 2018-04-10，accession 0000950103-18-004622；同一张表还印 Mar-18 22,371 / '
    'Q4-17 83,986 / Q1-17 66,551）。而 ASEH 对<b>同一个 2018Q2</b> 印了三个数，'
    '并在脚注里逐条定义（2018 年 9 月号新闻稿，电头 2018-10-09，脚注 1／2／3）：'
    '只含 ASEH 自 4/30 起 = <b>62,015</b>；「法人报导口径」再加 ASE Inc. 的 4 月 = '
    '<b>84,501</b>；pro forma 再加矽品的 4 月 = <b>91,757</b>。'
    '同一个季度自己就有 62,015~91,757 的跨度（<b>+48.0%</b>）—— 公司印三个数，'
    '正是因为它知道这一格没有单一答案。拿最接近「拼起来会长什么样」的那个（84,501）'
    '比前身 Q1：合并 <b>+30.1%</b>、ATM <b>+47.1%</b>。'

    '<b>② 日月光自己都不印那 12 个月的「去年同月」列。</b>'
    '（2026-08-18 把当时全部 99 期新闻稿 PDF 重抓了一遍，逐期读版式，不是抽查）'
    '月表的表头模板从第一期起就带 <code>YoY Change</code> 这一栏，'
    '但 <b>2018-05（电头 2018-06-08）~2019-04（电头 2019-05-09）整整 12 期</b>，'
    '去年同月那一列与 YoY% 那一格<b>全是空的</b>；2018-05 那期连上月列都没有，'
    '两个百分比格都空着。第一次印出去年同月是 <b>2019-05 期</b>（电头 2019-06-10）：'
    'May-2019 30,118 / Apr-2019 29,051 / <b>May-2018 30,982</b>，YoY <b>−2.8%</b> —— '
    '正好是本主体攒够 12 个月自己的历史之后的那一期，此后<b>无一缺席</b>'
    '（复核当时已连续 87 期）。'
    '四张表（合并／ATM × NT$／US$）逐期一致，没有一张例外。'
    '本页若把那 12 个月的同比印出来，就是比公司自己披露得还「勇」。'

    '<b>③ 就算只接合并那一列，第二列也接不上。</b>'
    '前身的 ATM 是 ASE Inc. 自己的 ATM（不含矽品），ASEH 的 ATM 含矽品。'
    '用公司自己那三个 Q2 反解：矽品 2018 年 4 月贡献合并 <b>7,256</b>、'
    'ATM 也是 <b>7,256</b>（分毫相同 —— 矽品是纯封测，没有 EMS 那一侧）。'
    '所以 <code>revenue_atm_ntd_mn</code> 与由它派生的「非 ATM」在接缝两侧'
    '根本不是同一个东西。再往前还要退一层：2001 年那批月报的单位是 NT$ <b>千元</b>、'
    '第二张表叫「Kaohsiung 封装厂」而不是 ATM。'
    '<b>这一列的逐年口径对照本轮没有做完，所以本页也不声称它能接。</b>'
)
# 「接了会坏掉哪几格」——纯算式，写死会在 yoy.TTM_WIN 或序列首月变动时同时说谎。
if _DMG:
    _PRE2018_NOTE += (
        f'<b>接了会坏掉哪几格（算式，不是估计）</b>：断点在 <b>{_DMG["break"]}</b>。'
        f'单月同比比的是 m 与 m−12 ⇒ <b>{_DMG["mom_n"]} 个点</b>'
        f'（{_DMG["mom_lo"]}~{_DMG["mom_hi"]}）跨口径，牵动 '
        f'{_DMG["mom_src_lo"]}~{_DMG["mom_src_hi"]} 的读数；'
        f'{_DMG["ttm_win"]} 个月滚动合计同比两侧各要一个 {_DMG["ttm_win"]} 个月窗口 ⇒ '
        f'<b>{_DMG["ttm_n"]} 个点</b>（{_DMG["ttm_lo"]}~{_DMG["ttm_hi"]}）跨口径，'
        f'牵动 {_DMG["ttm_src_lo"]}~{_DMG["ttm_src_hi"]} 的读数。'
        + (f'换来的是 {_DMG["gain_lo"]}~{_DMG["gain_hi"]} 那 {_DMG["gain_n"]} 格柱子'
           f'（按本仓台积电那几页 {_HYPO_X0} 起的窗口算）。' if _DMG['gain_n'] else '')
        + '<b>本页选择不换。</b>')
_PRE2018_NOTE += (
    '前身数据本轮<b>没有</b>落库（不建 <code>series/ase_pre2018.csv</code>）：'
    '页上看到的每一格都出自 ASEH 本主体自己的公告。')


# ══════════════════════════════════════════════════════════════════════════════
SPEC = {
    'ticker': 'ase',
    'name': 'ASEH',
    'tracker': 'ASE Monthly Revenue Tracker',
    # 标题里写全「NYSE: ASX」：本仓的 `asx` 是 ASX Limited（澳交所），
    # 两者的 ticker 撞名，页面上必须一眼分得开。
    'title': '日月光投控 ASEH (3711.TW / NYSE: ASX)：月度营收跟踪',
    'source': 'Source: ASE Technology Holding monthly net revenue press releases '
              '(ir.aseglobal.com, PDF body — NT$ tables and the company-filed US$ '
              'table on the same page), cross-checked against TWSE MOPS t21sc03, '
              'TWSE OpenAPI t187ap05_L and SEC XBRL annual revenue; '
              'format after Goldman Sachs GIR',
    # ⚠️ 本轮起这里必须把 US$ 表也点出来：页上多了一条美元腿，而它**不是**从
    #    NT$ 那一列折出来的 —— 数据源一条若只写 NT$ 表，读者会以为美元线是页面折的。
    'source_zh': '日月光投控（ASEH）官网 IR 月度营收新闻稿 PDF 正文'
                 '（两张 NT$ 表：合并 / ATM 分部；加同一页公司自印的 US$ 表；'
                 '均未经会计师查核，台湾法定次月 10 日前公布），'
                 '并与 TWSE MOPS 全市场月表逐月对账',
    'csv': _CSV,

    # ── 主序列 = **合并**。四条理由见 _MAIN_LINE_NOTE（挂在 gs_bar 自己的图注上）。
    #    summable：新台币是 ASEH 的功能货币与表达货币，月值是原生记账数不是折算值；
    #    与 SEC XBRL 的 20-F 年度值逐年对过账（FY2019–FY2025，最大差 < 2 百万）。
    'value': {'col': _COL_TOT, 'div': 1000.0, 'label': 'NT$bn', 'sym': 'NT$',
              'dec': 1, 'raw_label': 'NT$mn', 'raw_dec': 0, 'zh': 'NT$ revenue',
              'ccy_zh': '新台币', 'summable': True},

    # `official_yoy` 不给：series/ase.csv 里没有 y/y 列（公司公告里有，但没落库）。
    # 底座退回 build/yoy.py 自算，并在页尾说明本页没有「公司原值 vs 自算值」的分歧。

    # 官方逐月拆分的两条分部列（第二条是残差）。底座拿它们喂：汇总表两行、
    # 全历史图两条线、核对表两列、brief 第 4 句的「合并 ≡ 各分部之和」。占比全部现算。
    'segments': [
        {'col': _COL_ATM, 'zh': 'ATM（封测及材料）',
         'label': 'ATM (packaging & test)'},
        # ⚠️ `disclosed: False` 不是装饰：月度新闻稿只印**两个**数（合并总额与 ATM
        #    分部），这一列是 `合并 − ATM` 减出来的。不给这个标志，底座会把它当成
        #    第三次官方披露，于是同一页会出现三处互斥说法 —— 汇总表下方那句
        #    「All figures derived from…」、页尾数据源条的「N 个官方披露字段」、
        #    以及核对表标题里「N 列不是公司披露值」那份清单。本轮终审逮到的就是这个。
        {'col': _COL_NON, 'zh': '非 ATM（EMS 及其他，残差）',
         'label': 'Non-ATM (EMS & others)', 'disclosed': False},
    ],

    # ── 汇率：三张图**全出**，但页面上的三种「汇率身份」互不相同（见文件头【5】）：
    #      · 汇率线那张画的是 NTD/USD **本身**，一条宏观序列 —— 挂同一份 tsm_fx.csv
    #        的每一页上逐点相同，不需要日月光披露任何东西。
    #      · 美元腿（本币 vs 美元 / 汇率贡献 两张）读的是 `fgn_col` 那一列，
    #        **公司自印的官方美元实绩**，不是「本币 ÷ 外部牌价」折出来的。
    #      · 这两者之间**没有恒等式**：公司不披露自己用的汇率。
    #    ⇒ 三个字段必须同时给，漏一个都不报错、只会让页面说谎（文件头【5】列了后果）：
    #        'fgn_col' = 官方美元列   / 'implied' = False（外币腿不是我们折的）
    #        'rate_filed' = False     （汇率线**不是**公司申报的换算汇率）
    #      `implied` 漏了会被 validate() 硬失败拦住；`rate_filed` **拦不住** ——
    #      它的默认值 `not implied` 在本家恰好是错的，只能靠这里显式写。
    'fx': {
        # 与 /tsm/ 共用同一份文件：它是一条宏观序列，不是 per-ticker 数据。
        # 覆盖 2013-01~，本序列自 2018-05 起，逐月无缺（缺月会被 DataSet 硬失败拦住）。
        'csv': 'tsm_fx.csv', 'col': 'ntd_per_usd', 'quote': 'NTD per USD',
        'src': '美联储 H.10 台湾地区日度牌价按月算术平均（该月全部有报价营业日，'
               '落库脚本 fetch/tsm.py；FRED 的 EXTAUS 是同一批日度值的官方月均，'
               '两者在本仓已入库区间逐月相同），存于 series/tsm_fx.csv —— '
               # ⚠️ 这里必须写「这条外部牌价线」而不是「这条线」：本轮起 Ex9 上有**两条**
               #    线（深藏青 = 外部牌价、红色 = 公司自印两列之商），而本串同时进
               #    Ex9 的图脚与页尾数据源条 —— 「这条线」在两处都会歧义，
               #    而且「每一页上逐点相同」只对深藏青那条成立（红线是本家独有的）。
               '本站挂同一份汇率的每一页上，这条外部牌价线逐点相同。'
               '它不是日月光申报的换算汇率（本家从不披露所用汇率），'
               '页上那两条营收腿都不由它折出（fx.rate_filed = False）',

        # ── 外币腿 = **公司自印的官方美元列**（文件头【5】【11】）。三个字段一组。
        'fgn_col': _COL_USD,
        # 外币腿不是我们折的 ⇒ 页面不许在任何一处印「Implied / (converted)」。
        # 给了 fgn_col 却漏掉这一行，底座 validate() 硬失败。
        'implied': False,
        # ⚠️ 与 implied **是两件事**：这一行说的是「汇率线本身是不是公司申报值」。
        #    日月光每月自印美元营收，却从不披露所用汇率 ⇒ 汇率线仍是外部牌价。
        #    不写这一行，底座默认 `not implied` = True，会在汇率线的线名、图脚与
        #    核对表表头印出 "as filed" —— 替公司申报了一个它没申报过的汇率。
        'rate_filed': False,
        # 这一句进「本币 vs 美元」「汇率贡献」两张图的英文图脚。
        # ⚠️ 台积电那句 "Assumption: NT$ converted at the month average rate" 在本家
        #    是**假话**：本页一次折算都没做，两条腿是两次独立披露。所以这里写的不是
        #    一个假设，而是「没有假设」这个事实 + 一句它带来的限制。
        'assumption': 'No conversion is performed: the NT$ and US$ series are two '
                      'separate figures the company prints in the same monthly '
                      'release. ASEH does not disclose the rate it used, so the '
                      'US$ line cannot be reproduced from the NT$ line and the '
                      'external rate shown on this page.',
        # ⚠️ per-ticker，**不可继承**。台积电那句「约七成营收以美元计价」搬到这里
        #    就是编数据：ASEH 的 20-F 只说 "the majority"，从不给百分比。
        #    所以这里用**不带数字的定性版本 + 可点开的出处**（底座 validate() 明写的退路）。
        'usd_share_note': {
            'en': 'ASEH reports in NT dollars, its functional currency, but states in '
                  'its Form 20-F that the majority of its prices and revenues is '
                  'denominated in U.S. dollars — so this rate moves the reported '
                  'growth rate. No percentage is disclosed; "the majority" is the '
                  "company's own wording.",
            'zh': 'ASEH 的功能货币是新台币，但 20-F 明写「多数定价与营收以美元计价」，'
                  '所以这条汇率线直接推动它报表上的增速（原文只说 "the majority"、'
                  '没有给百分比，本页也不编一个）',
            'src': 'ASEH 2025 年度 Form 20-F（2026-04-01 报送，accession '
                   '0001193125-26-135585）Item 5「Pricing and Revenue Mix」："The '
                   'majority of our prices and revenues is denominated in U.S. '
                   'dollars."，及 Item 11「Foreign Currency Exchange Rate Risk」："…'
                   'exchange rate movements against the NT dollar, our functional '
                   'currency. Currently, the majority of our revenues … are '
                   'denominated in U.S. dollars."；'
                   'https://www.sec.gov/Archives/edgar/data/1122411/'
                   '000119312526135585/d50802d20f.htm'
                   '（2026-08-13 现抓复核，两句均为文内原文；比例表述随每年 20-F 复核）',
        },
    },

    # `skip` / `skip_note` **两个键都不给**（本页十张图一张不跳）。
    # ⚠️ 上一版跳掉了 fx_lines / fx_contrib，理由是「没有官方美元实绩可对账」——
    #    那两列落库之后这条理由整条失效，所以两个键一起删。
    #    两个键必须一起删：底座页尾那段「本页不出「…」那张图」遍历的是 `skip_note`，
    #    只删 `skip` 会让它继续印，而那张图就在页上。
    #    （本轮起底座 `validate()` **两个方向都查**了：`skip_note` 里有而 `skip` 里
    #    没有的 slug 直接 SpecError，所以这个坑现在踩下去会当场硬失败，不再是静默。）

    'window': {
        # 显式 None = 用序列自己的起点（序列首月 2018-05）。**不是忘了写**：
        # ASEH 控股 2018-04-30 才成立，此前没有本主体的合并月报（文件头【1】）。
        # 本轮复核：确认这里就是 None，没被写成 '2016-01' 之类的常数。写了也看不出来
        # —— `_first_at_or_after()` 会把它夹回 2018-05，两种写法**产出逐字相同**，
        # 差别只在底座页尾那段「短窗口图的起点与数据边界」印哪一版：
        #   None      → 「不设短窗口，左端由序列自己决定」（本页事实）
        #   '2016-01' → 「spec 要 2016-01，被钳到 2018-05」（把没做过的选择说成做过）
        # 更早的月份为什么不接（前身其实拿得到）：文件头【12】＋ `_PRE2018_NOTE`。
        # ⚠️ 别顺手改成月份串来「省事对齐 TSM」—— 那一改就是在页面上撒谎。
        'x_from': None,
        # 自算单月同比自 2019-05 起才有值（本主体 2018-05 开张，头 12 个月没有可比
        # 基期 —— 与文件头【12】代价二说的是同一件事：公司自己也是从 2019-05 才印）。
        # ⚠️ 写 8 是**当时**的实数：2026-08 时可用年份正好是 2019~2026 共 8 年，
        #    写 9 与写 8 产出逐字相同（底座取 sorted(年份)[-NH:]），所以选了写实数的那个。
        #    **但这个 8 会随年份走**：跨到 2027 之后可用年份变 9，继续写 8 就成了
        #    「主动砍掉最早那一年」——那是个选择，不再是「照实写」。到时要么改成 9、
        #    要么把「只看最近 8 年」这个意图写进注释，别让它默默变成另一件事。
        'heat_years': 8,
        'check_rows': 13,
    },

    # ── 断点：只画过门槛的两条（门槛 BREAK_DRAW_MIN_PCT，未过线的三条登记在
    #    _M_AND_A_NOTE 里）。月份一律取**控制权转移当月**，不取签约日。
    #    **不写 'col'**：底座的 apply_breaks() 是整图标记，`col` 只参与去重 ——
    #    写了会造成「按列登记了红线」的错觉。哪条线受影响由 _SEG_LINE_NOTE 说清楚。
    'breaks': [
        # zh 只写「事件 + 日期 + 影响哪一侧」：这句会被底座**逐图重复**印进每一张有连续
        # 横轴的图注（本页 4 处）再加页尾一处。量化的部分（NT$2,043 百万 / −3.8% /
        # +18.9% vs +24.7%）放进只出现一次的 _M_AND_A_NOTE 与 _BREAK_YOY_NOTE。
        {'month': '2020-12',
         'zh': 'USI 完成收购 Asteelflash（FAFG），自 2020-12-01 起并入 EMS 侧'
               '（影响合并与非 ATM，ATM 不受影响）'},
        {'month': '2021-12',
         'zh': '中国四厂（ASEN／ASEKS／ASEWH／Advanced Shanghai）出售予智路资本，'
               '2021-12-16 交割，本月是半个月的过渡月'
               '（影响合并与 ATM，非 ATM 不受影响）'},
    ],

    # `continuity` 不给：给不出「口径连续」的出处，而且事实相反（五条结构变化
    # + 一次 ATM 追溯重述）。见文件头【8】。底座会只陈述中性事实并加免责句。

    'format_source': '版式仿 Goldman Sachs GIR 台股月营收报告（「Hon Hai (2317.TW)」与 '
                     '「Wistron (3231.TW)」的 Exhibit 1-2），与本仓 /tsm/ 同一套底座',

    # 逐图补注：口径判断挂在读者提问的那张图底下，而不是全都堆到页尾。
    # ⚠️ `mix` 与 `hist` 上那条「红线对谁成立」的 caveat **措辞相反**，各写各的
    #    （占比图的分母就是合并，断点一动两条线同时动）—— 别把两段合成一份复用。
    'note_extra': {
        'rev_bar': _MAIN_LINE_NOTE,
        'mix': _MIX_RESID_NOTE + _MIX_BREAK_NOTE,
        'fx_lines': _FX_LINES_NOTE,
        'fx_contrib': _FX_CONTRIB_NOTE,
        'hist': _SEG_LINE_NOTE,
        'fx_rate': _FX_RATE_NOTE,
        'heat': _HEAT_EXTRA,
    },

    'notes': [
        _SPLIT_NOTE,
        _CALIBER_NOTE,
        _MIX_NOTE,
        _M_AND_A_NOTE,
        _BREAK_YOY_NOTE,
        _USD_FILED_NOTE,
        _DAYS_NOTE,
        _YOY_SOURCE_NOTE,
        _REMARK_NOTE,
        _NO_GUIDANCE_NOTE,
        _SRC_NOTE,
        # 收尾这一条是**决定的记录**：为什么不把 2018-05 之前的前身接上来。
        # 排在 _SRC_NOTE 之后，因为它接的是那一条最后一句「理由与代价见下一条」。
        _PRE2018_NOTE,
    ],
}
