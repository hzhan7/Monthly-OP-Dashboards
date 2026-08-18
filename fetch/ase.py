# -*- coding: utf-8 -*-
r"""日月光投控（ASEH，3711.TW / NYSE: ASX）月度营收 —— 无人值守抓取模块。

对应 build/specs/ase.py（页面由通用底座 build/single.py 生成），维护一个序列文件：

  series/ase.csv    month, revenue_ntd_mn, revenue_atm_ntd_mn, revenue_nonatm_ntd_mn,
                    revenue_usd_mn, revenue_atm_usd_mn

后两列是**公司自印的美元实绩**，不是折算值 —— ASEH 是本仓七家月营收里唯一
逐月公告官方美元数的一家（见口径坑 12）。两列一律取 PDF 正文印的整数，
**不由 NT$ ÷ 汇率补算、不补差**：公司自己不披露所用汇率，任何折算都是造第二个答案。

⚠️ **本页 slug 是 `ase`，不是 `asx`。** `asx` 在本仓已经是 ASX Limited（澳交所）
   的 ticker（series/asx.csv、fetch/asx.py、build/specs/asx.py、asx/ 目录、
   source_dates.csv 里上百行）。日月光的 NYSE ADR 代码恰好也叫 ASX，
   两边写串会同时污染两张页，而且是静默污染 —— 图照出、数全错。

────────────────────────────────────────────────────────────────────────
数据源
────────────────────────────────────────────────────────────────────────
1) 落地页（发现用，**不当数值源**）
   https://ir.aseglobal.com/html/ir_revenues.php?year=YYYY
   一年一张表：Month / Net Revenues (NT$ million) / Press Release，
   最后一列的 <a href> 指向该月英文新闻稿 PDF
   （https://media-aseholdco.todayir.com/<14~16 位时间戳><随机串>_en.pdf）。
   年份下拉框里只有 2018~本年 —— 2017 及更早在 `<!-- -->` 注释里，取不到，
   这正好与 ASEH 控股 2018-04-30 成立、2018-05 起才有合并月报吻合。

   ⚠️ **落地页表格里的金额有错，一律以 PDF 正文为准**（口径坑 2）。

2) 数值源：月度新闻稿 PDF（英文版）
   正文**每期印四张月表**，是「两个分部 × 两种货币」的笛卡尔积：
     CONSOLIDATED NET REVENUES (UNAUDITED)   → (NT$ Million) 一张、(US$ Million) 一张
     (IC-)ATM NET REVENUES (UNAUDITED)       → (NT$ Million) 一张、(US$ Million) 一张
   （`IC-ATM` 是 2018-05~2018-12 的旧名；2018-05 那期还把 ATM 标题写成
     `ATM NET REVENUES (UNAUDITED)*` 带星号 —— 所以 section 判据是**前缀匹配**。）
   每张表三列：当月 / 上月 / 去年同月，所以**一份 PDF 同时给出三个月的读数** ——
   重述体检就靠这个（口径坑 6）。
   ⚠️ **「三列」只对 2019-05 期及以后成立**，头 12 期不是（口径坑 14）。
   四张表的列头逐字相同、月份键逐份完全一致（2026-08-18 全量实测，当时 99 期：
   C/A × NT/US 各 284 个月读数 = 99 自期 + 98 上月 + 87 去年同月，四者一个不差，
   四表键不一致 0 期）—— 三个数之间的关系比它们本身耐久：
     自期 = 期数、上月 = 期数 − 1、去年同月 = 期数 − 12（口径坑 14 解释这个 12 从哪来）。
   `_pdf_tables()` 把「四表月份键逐字相同」当**硬不变量**校验，不齐就抛异常，
   因为那正是列错位（口径坑 8）在解析结果上的样子。
   ⚠️ 它校验的是**四表之间一致**，不是「每份都有三个月」——
   后者对头 12 期本来就是假的，写成硬校验会让 2018 年那批全部抓不进来。
   季末月（3/6/9/12）的 PDF 另有 Q 表、12 月另有 FY 表，**Q 表与 FY 表同样
   NT$/US$ 各一张**，本模块只取月列（口径坑 8）。

3) 交叉校验源（只读不写，失败只告警不阻断）
   TWSE OpenAPI https://openapi.twse.com.tw/v1/opendata/t187ap05_L
   全市场当期一份 JSON，单位新台币千元。3711 是**本国**上市公司，在 _L 里；
   外国发行人（世芯-KY 3661 那类）走 TPEx 的 _O 端点，不在这张表。
   只有最新一期、没有历史，所以只用来验「最新月是哪个月 + 合并金额对不对」。

4) 全历史第三源（本模块不调，落库时人工对过一次，见文件末「对账实测」）
   https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_<民国年>_<月>_0.html
   MOPS 全市场当月营收表，big5 编码，一月一张 400KB HTML，可回溯到 2018。
   **单张耗时 20~60 秒**，全历史（2026-08 时 99 张）要跑近一小时，不适合放进每月例行；
   例行只跑上面第 3 条。

────────────────────────────────────────────────────────────────────────
发布节奏（2026-08-13 全量实测，当时 99 期；取自 PDF 正文电头日期，不是 URL 时间戳）
────────────────────────────────────────────────────────────────────────
· 台湾《证券交易法》要求次月 10 日前公告。ASEH 全部期次的「月末后第几天」分布
  （2026-08-13 重测，当时 99 期 —— 下面的绝对期数是那一天的快照，会随每期增长；
   耐久的是结论「≤11 天覆盖 96%」与由它定出的 LAG，不是这几个计数）：
    第 8 天 9 期 / 第 9 天 42 期 / 第 10 天 34 期 / 第 11 天 10 期 /
    第 12 天 1 期 / 第 13 天 1 期 / 第 15 天 1 期 / 第 40 天 1 期
  累计覆盖：≤10 天 85 期、≤11 天 95 期、≤13 天 97 期、≤15 天 98 期。
  最慢的常规一期是 2024-01 → 2024-02-15（农历年，主管机关准予延后）；
  第 40 天那期是 2022-12 的**改版重发**，见下条。
  → roster LAG 取 **(15, 15)**：季末月**没有**例外，3/6/9/12 与常规月同一天发
    （季度表是同一份 PDF 里多印两张表，不另择日），所以两个数相同不是偷懒。
· URL 里的时间戳**不能当公告日**：2026-03 那期 URL 是 `20260508…`，
  正文电头却是 APRIL 10, 2026 —— 官网 5 月批量重传过一次。
  2022-12 那期是**另一回事，别混为一谈**：官网现挂的那份 PDF 标题是
  `REVISED: ASE Technology Holding Co., Ltd. Announces Monthly Net Revenues`、
  正文写 `announces its revised unaudited consolidated net revenues for
  December, 4th quarter and full year of 2022`，电头 FEBRUARY 9, 2023 ——
  它是一次**真实的改版重发**，不是重传，原始 1 月那份已被官网替换掉。
  所以 press_date() 对这一期给出的 2023-02-09 是「改版稿的发布日」，
  当 LAG 统计样本要剔除（月末后第 40 天），当「这份文件几时发的」是对的。
  **电头日期才是公告日。**

────────────────────────────────────────────────────────────────────────
口径坑（踩过的，别再踩）
────────────────────────────────────────────────────────────────────────
1. **PDF 主机对裸 UA 返 403 + 118 字节 HTML，状态码不是 403 就是 200。**
   media-aseholdco.todayir.com 挂在 awselb 后面，不带浏览器 UA 时返回
   `HTTP/2 403` + 118 字节 `<html>…403 Forbidden…</html>`；openpyxl / fitz
   拿到它会报「不是 zip / 不是 PDF」这种与真实原因毫无关系的错。
   → `_get_pdf()` **同时**校验：非 3xx、体长 ≥ 20,000、首 5 字节 `%PDF-`。
     三条缺一不可。落地页 `_get_html()` 同理校验体长 ≥ 50,000
     （真页 108KB，WAF/错误页远小于此）+ 正文含 `revenues-table`。

2. **落地页表格里的金额有错，且错得很像真的。**
   2026-01 那一格印的是 `$59,589`，PDF 正文与 MOPS 都是 **59,989**（差 400）。
   验伪三处一致：① 2026Q1 官方合并 173,662，用 59,989 加出来 173,663（差 1 是
   四舍五入），用 59,589 加出来 173,263（差 399）；② TWSE OpenAPI 2026-07 期的
   「累計營業收入-當月累計營收」438,509,375 千元 = 438,509 百万，
   用 59,989 加出来 438,510、用 59,589 是 438,110；③ MOPS 2026-01 全市场表
   3711 行是 59,988,631 千元。
   → **落地页只用来发现 PDF 链接**；金额从 PDF 取。两者不一致时打印告警
     （`_html_amount_check`），不改写、不阻断 —— 这是上游的排版错误，不是本模块的。

3. **2019-07 那份 PDF 全篇用 NBSP（U+00A0）当空格。**
   `(NT$\xa0Million)`、`Net\xa0Revenues`，任何按普通空格切词的解析器都会静默
   跳过整份文件（不是报错，是解析出 0 个月）。同一批还混着 U+2010 连字符当负号。
   → `_pdf_tokens()` 先做 `replace(' ', ' ')` 再 `\s+` 归一。
     全量实测（2026-08-14，当时 99 份）：修掉这一条之前 98/99，之后 99/99。

4. **「ATM」的口径是 ATM **分部**基础（含分部间交易），不是合并利润表的
   Packaging + Testing + Others。** 两者不是一回事，实测差 126~3,016 百万：
     2026Q2 月加总 ATM 126,149；合并利润表 Packaging 99,387 + Testing 23,665
     + Others 2,601 = 125,653；而当季法说会 deck 的
     `ATM Statements of Income → Total Net Revenues` = **126,148**。
   月度 PDF 的 ATM = deck 的 ATM 分部合计，逐季逐字对得上（见文末对账）。
   → 因此 `revenue_nonatm_ntd_mn`（= 合并 − ATM）**不是官方 EMS 分部营收**，
     它是「合并总额减 ATM 分部营收」的残差 = EMS + Others − ATM 分部间交易抵销。
     2026Q2：残差（本序列 4~6 月加总）64,914；官方合并 EMS 65,411；
     EMS 分部基础 65,789。（拿官方季度口径算残差是 191,064 − 126,148 = 64,916，
     与月加总差 2 是四舍五入，别把两者混着引。）
     列名故意不叫 `revenue_ems_ntd_mn` —— 叫了就是在口径上说谎。

5. **ATM 有过一次追溯重述，合并没有。**
   2019-09 期的脚注：「The ATM results presented have been retrospectively
   adjusted to exclude a portion of the results related to manufacturing
   integrated circuits from an acquired subsidiary consolidated since May 2019.」
   受影响的月份与调整额（旧 → 新）：
     2018-12  20,194 → 20,187   （−7，**不是**这次重述：2019-01 期就已经改过来了，
                                  是更早的一次小修，与 2019-09 那次无关）
     2019-05  20,248 → 20,148   （−100）
     2019-06  20,700 → 20,605   （−95）
     2019-07  21,763 → 21,668   （−95）
     2019-08  22,974 → 22,884   （−90）
   验：重述后 2019Q2 ATM = 18,841+20,148+20,605 = 59,594，与 2019-09 期印的
   重述后 Q2 逐字相等（原口径是 59,789）；2019Q3 = 21,668+22,884+23,349
   = 67,901，同样逐字相等（原口径 68,086）。
   → 落库一律取**最晚一次公布的读数**。合并口径**每一个月**（2026-08-14 全量重扫，
     当时 99 个月）× 最多 3 次独立观测（自己那期 / 次月那期 / 次年同月那期）
     **零分歧**。⚠️ 「3 次」是上限不是常数 —— 2018-05~2019-04 那 12 个月只有
     2 次（没有「次年同月那期」可看，见口径坑 14），2018-05 只有 1 次。

   ⚠️ **美元侧那次重述已实测，结论是「月度同步、季度不同步」—— 不能照抄新台币侧。**
   2026-08-14 全量重扫（当时 99 期 × 4 表 × 每月最多 3 次观测）实测：
     · `revenue_usd_mn`（合并 US$）：全部 99 个月**零分歧**，与 NT$ 合并同。
     · `revenue_atm_usd_mn`（ATM US$）：分歧月与 NT$ 侧**同为那 5 个月**，
       但**调整额不是按汇率等比缩放**，逐月是各自独立四舍五入到整数百万的结果：
         2018-12  656 → 655   （NT$ −7    ⇒ 折约 −0.23，本该舍掉，却跨过了进位边界）
         2019-05  655 → 652   （NT$ −100  ⇒ 折约 −3.2）
         2019-06  659 → 656   （NT$ −95   ⇒ 折约 −3.0）
         2019-07  702 → 699   （NT$ −95   ⇒ 折约 −3.0）
         2019-08  734 → 731   （NT$ −90   ⇒ 折约 −2.9）
     · **到了季度就分岔了**：2019Q2 ATM 美元跟着改（1,926 → 1,920，−6），
       而 **2018Q4 ATM 美元三版全是 2,083、一个字没动**，同期 NT$ 却从
       64,127 改成 64,120（−7）。也就是说「NT$ 改了 ⇒ US$ 一定改」是**假的**，
       −7 百万新台币在美元上被四舍五入吃掉了。
       → 所以重述体检必须**对五列各自独立比对**，不能拿新台币侧的结论去推美元侧，
         也不能反过来。`update()` 就是这么写的。
     · 落库口径与新台币侧一致：**取最晚一次公布的读数**。这五个月的美元值
       同样来自后续期次（2019-05~07 那三个月的重述值，最早出现在 2020 年
       同月那期的「去年同月」列上 —— 2019-09 那期只重印了 Q 表与上月列）。

6. **重述体检**：每份新 PDF 自带上月与去年同月两列，**四张表都有**，
   所以美元两列与新台币两列一样每月拿得到 3 次独立观测。
   ⚠️ 这句话对 **2019-05 期及以后**成立；头 12 期没有去年同月列（口径坑 14），
   那 12 个月只有 2 次观测。写体检时别把「3 次」当成不变量去断言。本模块把这些读数与
   已入库值**逐格比对，五列全覆盖**（新台币 3 列 + 美元 2 列），
   任一格不一致就**抛异常、本次不写入**，由人判断是重述还是解析变形 ——
   不悄悄改写、不追加第二行。同 fetch/tsm.py 口径坑 6、fetch/guc.py drift 检查。
   （上面第 5 条那次重述，正是这套检查在历史上会抓到的东西。）
   ⚠️ 五列**各自独立**判定：第 5 条实测过 2018Q4「NT$ 改了而 US$ 没改」，
   所以不许写成「新台币对上了就跳过美元」那种省事写法。
   派生列 `revenue_nonatm_ntd_mn` 参与比对是免费的（它由 C−A 定义），
   但美元侧**故意不建 nonatm 列**：两个各自四舍五入到整数百万的数相减，
   残差上界 ±1 落在一个只有 300~800 的量级上，相对误差比新台币侧大两个数量级，
   画出来是噪声不是分部。要非 ATM 美元请自己承担这层误差，别让本模块假装它精确。

7. **不许把 `Pro Forma Basis**` 那几张表当实际数。** 2022-01~2022-12 的每一期
   都多印一组「排除已处分中国四厂」的 pro forma 表，版式与实际表**完全相同**，
   只多一行 `Pro Forma Basis**` 标题。按 `Net Revenues` 硬找会先撞上实际表、
   再撞上 pro forma 表，取错一次就把 2022 全年拉低 8~10%。
   → `_pdf_tables()` 见到 `Pro Forma` 就把当前 section 置空，直到下一个
     section 标题为止。
   ⚠️ **pro forma 组同样是 NT$/US$ 成对印的，美元侧一步不落。** 2022-03 期实测：
   实际组去年同月 US$1,490，pro forma 组同一格印 US$1,419（NT$ 侧对应 42,002 vs
   40,009）—— 当月那一格两组相同（都是 1,843），**分歧只出现在去年同月列上**，
   所以取错了不会当场露馅，会静默把 2022 全年同比抬高。标题 token 实测有两种
   写法（`Pro Forma Basis**` 20 次、`Pro Forma Basis (unaudited)**` 4 次），
   判据用 `startswith('Pro Forma')` 两种都盖得住；脚注里的
   `** Pro forma basis excludes …` 以 `**` 开头，不会误触发。

8. **季末月与 12 月的 PDF 里还有 Q 表与 FY 表**，列头是 `Q1`/`FY` 而不是月份缩写，
   而且 **Q 表、FY 表也都是 NT$/US$ 各一张**（2026-08-14 全量实测，当时 99 期：
   Q 表四表各 91 个读数、年度表四表各 6 个读数）。本模块按列头是不是月份缩写来筛，Q/FY 列直接丢掉
   （但**保留位置对齐**，否则 2018-09 那期的 `Q21 / Q22 / Q23`
   （SPIL 并购的三种 pro forma 口径）会把后面的列错位一格）。
   ⚠️ **年度表的列头有两种写法，`_PERIOD_RE` 只认得其中一种 —— 这是刻意的**：
   2021-12 / 2022-12 两期印 `FY`，2023-12 / 2024-12 / 2025-12 三期改印
   `Full Year`（一个 token，中间是普通空格），2018-12 / 2019-12 / 2020-12
   三期**根本没有年度表**。`Full Year` 不匹配 `_PERIOD_RE` ⇒ 向回收列头的循环
   在它上面就停住 ⇒ `periods` 为空 ⇒ 整张年度表被丢掉，与 `FY` 的结局相同。
   所以这两种写法都是安全的，**但理由不一样**（一个是「匹配上了、再按不是月份
   缩写丢掉」，另一个是「压根没匹配上」）。谁哪天想「顺手」把 `Full Year` 加进
   `_PERIOD_RE`，必须同时确认它仍会被月份缩写那一关挡住 —— 别让年度值以
   `2023-01` 之类的键混进月序列。

9. **电头格式不止一种**。2023-04 / 2023-05 两期是 `TAIPEI, MAY 9, 2023 –`
   （没有 `TAIWAN, R.O.C.,`），同期还把 `TAIEX: 3711` 改成 `TWSE: 3711`。
   按 `TAIPEI, TAIWAN, R\.O\.C\.,` 硬匹配会在这两期上拿不到公告日。
   → `press_date()` 的正则把中段做成可选。

10. **`aseglobal.com` 与 `ir.aseglobal.com` 是两套站**。
    `https://www.aseglobal.com/en/investors/` 是 **404**（不是重定向），
    月营收只在 `ir.aseglobal.com/html/ir_revenues.php`。
    ir 站本身没有 WAF，裸 urllib 直接 200；有 WAF 的是 PDF 那台（坑 1）。

11. **落地页里埋着一张注释掉的假表，月份与真表重叠。**
    `ir_revenues.php` 的 HTML 里有一段 `<!-- … -->` 版式样板，内容是
    `January 23,591 / February 19,003 / March 11,352 / April 33,231`，
    每个 `<td>` 结构与真表**完全一样**，只有 href 是 `#`。
    不剥注释就直接跑行正则，任何年份都会多出这 4 行；2019 年以后 1~4 月是真月份，
    假行排在真行**之后**，只要哪天换成「后写的覆盖先写的」就会静默污染 4 个月。
    实测：不剥注释时 `_year_rows(2018)` 返回 12 行（真表只有 8 行），
    `_year_rows(2027)`（还不存在的年份）返回 4 行而不是 0 行。
    → `_year_rows()` 先 `_COMMENT_RE.sub('', html)`。

12. **美元两列是官方实绩，不是折算值 —— 而「折算值」正是最像真的那种污染。**
    ASEH 不披露它自己用的折算汇率。拿入库的两列反解隐含汇率（NT$ ÷ US$），
    全序列落在 **27.5989（2022-01）~ 32.8371（2025-04）**（2026-08-14 全量，当时 99 个月），与 `series/tsm_fx.csv`
    那条外部月均牌价逐月偏离 **−2.07% ~ +2.22%**（均值 −0.12%、中位 −0.20%、
    标准差 0.64%，29 个月为正 70 个月为负）—— **符号在变，不是常数偏移**，
    所以两者互相折算不出对方。这就是 build/mrspecs/ase.py 里
    `_FX_RATE_NOTE` 那几段的实测底稿。（`_SKIP_FX_LINES` 已删：本轮起日月光
    拿到官方月度美元实绩，Ex6／Ex7 由「跳过」改为出图，那条理由不再存在。）
    → 反过来，隐含汇率是一条**极灵敏的解析护栏**：一旦 US$ 槽里混进 NT$ 值，
      隐含汇率立刻掉到 1.0；反向错配则冲到 1000 上下。`_fx_sanity()` 因此
      **硬失败**在 [20, 45] 之外（实测区间 27.6~32.8，留了足够余量给真实汇率波动），
      并在 [26, 34] 之外只告警。它挡的不是汇率异动，是**列错位**。

13. **`series/*.csv` 是 CRLF，不是 LF。** 本仓的序列文件由 `csv.writer` 写出
    （`open(..., newline='')` + 默认 `\r\n`），ase.csv 100 行全是 CRLF。
    落库美元两列时若图省事按文本读进来再 `'\n'.join(...)` 写回去，
    **三列新台币数一个字没改，git diff 照样是 100 行全量重写** ——
    行尾变了。本次落库因此是**按字节逐行追加**（`b'\r\n'.join`），
    校验方式也相应地做成「把新文件截到前 4 列，md5 必须等于旧文件全文的 md5」，
    实测两者同为 `7e0f91bb3528ea5b129ac9dbe3f5dddc`。
    `update()` 继续走 `csv.writer`，行尾天然一致，这条只对**手工补列**成立。

14. **头 12 期没有「去年同月」列 —— 表头有那一栏，格子是空的。**
    2026-08-18 把当时全部 99 期 PDF 重抓一遍、逐期读版式（不是抽查）实测：
      · 月表表头模板**从第一期起就带 `YoY Change`** —— 位子公司一直留着；
      · **2018-05 ~ 2019-04 整整 12 期**，去年同月那一列与 YoY% 那一格**全空**：
        `_pdf_tables()` 在这 12 期只解析出 **2 个月键**；
      · **2018-05 期只解析出 1 个月键**（电头 2018-06-08）—— 连上月列都没有，
        Sequential 与 YoY 两个百分比格都空着。本主体那时连上一个月都还不存在。
      · 第一次印出去年同月是 **2019-05 期（电头 2019-06-10）**：
        `May 2019 / Apr 2019 / May 2018` = 30,118 / 29,051 / 30,982，YoY −2.8%。
        此后无一缺席（复核当时已连续 87 期）。
      · 每期月表印出的百分比个数：2018-05 印 0 个、2018-06~2019-04 各 1 个、
        2019-05 起 2 个。四张表（C/A × NT/US）逐期一致，键不一致 0 期。
    **为什么值得单列一条**：
      → 解析上，任何「每份 PDF 必有三个月」的硬断言都会让 2018 年那批全军覆没；
        `_pdf_tables()` 只校验「四表之间键一致」，就是为了避开这个。
      → 口径上，这 12 期的空白**不是 ASEH 漏印**，是它没有同口径的去年同月可比
        （控股 2018-04-30 才成立）。这条实测因此是 `build/mrspecs/ase.py` 文件头
        【12】「为什么不拼前身」里最硬的一条证据：连公司自己都不肯印那 12 个同比。
    复核方式：`_discover(range(2018, 当年+1))` → `_get_pdf()` → `_pdf_tables()`，
    看 `out['C']` 的键数（1 / 2 / 3）。PDF 原件落 `cache/ase_pdf/`，只读不写库。

━━ 依赖 ━━ pymupdf（import 名 fitz，仓里已有）。不依赖 requests / pandas。

────────────────────────────────────────────────────────────────────────
对账实测（2026-08 落库时跑的，写死在这里当回归基准）
────────────────────────────────────────────────────────────────────────
· 合并 vs 官方季度（IR「Historical data」xlsx `Consolidated IS` sheet 的
  Total 行）：2018Q3~2026Q2 共 32 个季度，月加总与官方逐季差 **−1 ~ +1 百万**
  （四舍五入残差），无一季超过 1。
· 合并 vs 官方年度：2019 FY 413,182 / 2020 476,978（xlsx 印 476,979，公司自己
  两处差 1）/ 2021 569,997 / 2022 670,873 / 2023 581,914 / 2024 595,410 /
  2025 645,388 —— 月加总逐年差 ≤ 2。
· ATM vs 公司自印的季度 ATM（同一份月度 PDF 的 Q 表）：32 个季度**全部**差 ≤ 2。
  ⚠ 必须拿**最晚一版**的 Q 表比。用「季末那期自己印的 Q 表」会踩两处旧口径：
    2019Q2 旧版 59,790（2019-06 期）vs 月加总 59,594 → 差 196；
           2019-09 期重述后印 59,594，diff=0。
    2018Q4 旧版 64,127（2019-01 期）vs 月加总 64,120 → 差 7；
           2019-12 期印 64,120，diff=0。
  2019Q3 两版都是 67,901（2019-09 期与 2020-09 期逐字相同），与月加总相等 ——
  它**不是**例外。
· ATM vs **另一份文件**（2026 Q2 法说会 deck `ATM Statements of Income`）：
  2025Q2 92,564 vs 92,565、2026Q1 112,434 vs 112,434、2026Q2 126,149 vs 126,148。
· 第三源 MOPS 全市场月表（t21sc03，big5）：2018-05~2026-07 共 99 个月，
  逐月与本序列 `revenue_ntd_mn` 相符（MOPS 单位千元，除以 1000 后四舍五入到
  百万，最大绝对差 < 0.5 百万 —— 纯千元→百万的四舍五入残差）。
· 第三源 TWSE OpenAPI t187ap05_L（2026-08-12 出表、資料年月 11507）：
  營業收入-當月營收 73,783,701 千元 = 73,784 百万，与 2026-07 入库值相等；
  累計 438,509,375 千元 = 438,509，与本序列 2026 年 1~7 月加总 438,510 差 1。

────────────────────────────────────────────────────────────────────────
美元两列的对账实测（2026-08-14 落库时跑的，写死在这里当回归基准）
────────────────────────────────────────────────────────────────────────
⚠️ **舍入残差的上界必须自己算，别把新台币侧的「≤2 百万」当通用标准。**
   两侧月值都是**整数百万**，所以 n 个月加总与官方自印的 n 月合计相比，
   残差上界都是 ±(n × 0.5 + 0.5)：季度 ±2、年度 ±6.5。
   绝对上界两侧相同，**相对上界差了约 30 倍**（月值量级 NT$ 5 万 vs US$ 2 千）——
   所以「差 2」在新台币侧是 4e-5 的噪声，在美元侧是 1e-3，含义完全不同；
   判合格看的是**有没有越过 ±2 / ±6.5 这条线**，不是看绝对值大小。

· 季度对账（月加总 vs **最晚一版** Q 表，32 个季度 2018Q3~2026Q2）：
    合并 US$：|差| 最大 **1**（27 季差 0、3 季 −1、2 季 +1）—— 全部在 ±2 内。
    ATM  US$：|差| 最大 **1**（22 季差 0、10 季 +1）—— 全部在 ±2 内。
    同批跑的新台币侧：合并 |差| 最大 1、ATM |差| 最大 1，与既有基准一致。
  ⚠ 必须用**最晚一版** Q 表，美元侧同样会踩旧口径（口径坑 5）：
    2019Q2 ATM US$ 旧版（2019-06 期）1,926 vs 月加总 1,920 → 差 **−6**，
      超出季度 ±2 的舍入上界三倍，一眼就是重述而不是舍入；
      最晚一版（2019-09 期起）印 1,920，diff=0。
    2018Q4 ATM US$ 三版**全是 2,083**，用哪一版 diff 都是 0 ——
      同一个季度在新台币侧却有旧版 64,127 vs 月加总 64,120 的 −7。
      **这就是「美元侧不与新台币侧同步」的直接证据。**

· 年度对账（月加总 vs 12 月那期的 `FY` / `Full Year` 表；只有 2021-12 起的
  五期印年度表，2021-12 那期同时印 2020 与 2021 两列，故可比年份 = 2020~2025）：
    合并 US$：2020 +0 / 2021 −1 / 2022 −1 / 2023 +0 / 2024 +0 / 2025 +0
    ATM  US$：2020 +0 / 2021 +2 / 2022 +0 / 2023 +1 / 2024 +2 / 2025 +0
  最大 |差| **2**，年度上界是 ±6.5 ⇒ 全部在界内，且离界还有三倍余量。
  （同批新台币侧：合并 −1~+2、ATM 0~+2，与文件上半段那组年度数一致。）

· 重述扫描（99 个月 × 3 次独立观测 = 每张表 284 个读数，四表齐跑）：
    `revenue_usd_mn`（合并 US$）  分歧 **0** 个月
    `revenue_atm_usd_mn`（ATM US$）分歧 **5** 个月，全部是**真重述**不是印刷错误 ——
      与 NT$ 侧同月、同方向、同一份 2019-09 期脚注所述的那次追溯调整
      （2018-12 −1、2019-05/06/07 各 −3、2019-08 −3），逐条见口径坑 5。
    对照：`revenue_ntd_mn` 分歧 0 个月、`revenue_atm_ntd_mn` 分歧 5 个月。
    四张表 284×4 个读数逐一比对，**没有第六个分歧月，也没有任何一处印刷错误**。

· 隐含汇率反解（NT$ ÷ US$，99 个月）：合并 27.5989 ~ 32.8371、ATM 27.5918 ~ 32.8562，
  **无一月落在 27~33 之外**。合并与 ATM 的隐含汇率逐月差最大 0.023
  （2024-06），量级与「两条腿各自四舍五入到整数百万」预期的一致。
  月环比 |Δ|>3% 的只有 4 个月，且**每一个都对得上外部牌价的同向大动**：
    2022-10 隐含 +3.35% / 牌价 +2.18%；2022-12 −3.80% / −2.48%；
    2025-05 −5.92% / −7.42%（新台币急升那波）；2025-06 −3.51% / −1.98%。
  ⇒ 跳变来自汇率本身，不是解析变形。
· 与 build/mrspecs/ase.py 已写死的三个引证独立复现（该文件是人工从 PDF 抄的，
  本模块是自动解析的，两条路互不相干）：隐含汇率对外部牌价的偏离
  2025-06 **+0.63%**、2026-06 **−0.55%**、2026-07 **−0.81%** —— 三个数逐位相符；
  该文件引的 2026-07 期「合并 US$2,309mn、ATM US$1,487mn」也与入库值相等。
"""

from __future__ import annotations

import csv
import datetime
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

IR_ORIGIN = 'https://ir.aseglobal.com'
IR_PAGE = IR_ORIGIN + '/html/ir_revenues.php'
TWSE_API = 'https://openapi.twse.com.tw/v1/opendata/t187ap05_L'
TWSE_CODE = '3711'

START_MONTH = '2018-05'          # ASEH 控股 2018-04-30 成立，2018-05 是第一个合并月
COLUMNS = ['month', 'revenue_ntd_mn', 'revenue_atm_ntd_mn', 'revenue_nonatm_ntd_mn',
           'revenue_usd_mn', 'revenue_atm_usd_mn']

# 隐含汇率护栏（口径坑 12）。挡的是**列错位**不是汇率异动：
# NT$ 混进 US$ 槽 ⇒ 比值 1.0；反向错配 ⇒ 约 1000。全序列实测落在 27.60~32.84
# （2026-08-14，当时 99 个月）。
_FX_HARD = (20.0, 45.0)          # 越界 = 解析坏了，抛异常
_FX_SOFT = (26.0, 34.0)          # 越界 = 汇率真的走远了，只告警

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')

_MIN_HTML = 50_000               # 真落地页 ~108KB；WAF / 错误页远小于此
_MIN_PDF = 20_000                # 真新闻稿 118~192KB；403 壳页 118 字节

_MONTH_NAME = {'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5,
               'June': 6, 'July': 7, 'August': 8, 'September': 9,
               'October': 10, 'November': 11, 'December': 12}
_MONTH_ABBR = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
               'June': 6, 'Jul': 7, 'July': 7, 'Aug': 8, 'Sep': 9, 'Sept': 9,
               'Oct': 10, 'Nov': 11, 'Dec': 12}
_MONTH_UPPER = {k.upper(): v for k, v in _MONTH_NAME.items()}

_PERIOD_RE = re.compile(r'^(Q\d{1,2}|FY|YTD|Jan|Feb|Mar|Apr|May|Jun|June|Jul|'
                        r'July|Aug|Sep|Sept|Oct|Nov|Dec)$')
# 货币行。**只认这两种**，且必须是整行精确匹配：它同时是「这是一张金额表」的
# 判据与「这张表是哪种货币」的判据。2026-08-14 全量实测（当时 99 期）各出现 310 次，
# 写法零变体。
# 注意别放宽成子串匹配 —— 正文别处也出现 "million"，一放宽就会把散文当表头。
_CURRENCY_RE = re.compile(r'^\((NT\$|US\$) Million\)$')
_TABLES = ('C', 'A', 'C_USD', 'A_USD')
_NUM_RE = re.compile(r'^[\d,]+$')
_ROW_RE = re.compile(
    r"<tr>\s*<td>([A-Za-z]+)</td>\s*<td>([^<]*)</td>\s*<td>(.*?)</td>\s*</tr>", re.S)
_HREF_RE = re.compile(r"""href=['"]([^'"]+\.pdf)['"]""", re.I)
_COMMENT_RE = re.compile(r'<!--.*?-->', re.S)


class AseFetchError(RuntimeError):
    """本模块的故障出口。抓不到 / 认不出来一律抛它，不返回 None 掩盖故障。"""


# ══════════════════════════════════════════════════════════════════════════════
# HTTP —— 状态码从来不是成功的证据（口径坑 1）
# ══════════════════════════════════════════════════════════════════════════════
def _open(url, *, referer=None, tries=3, timeout=120):
    """取 URL，3xx 一律判失败（软 404 会被当成真内容）。"""
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise AseFetchError(f'{url} 重定向到 {newurl}（{code}）—— 该资源不存在')

    opener = urllib.request.build_opener(_NoRedirect)
    headers = {'User-Agent': _UA}
    if referer:
        headers['Referer'] = referer
    last = None
    for _ in range(tries):
        try:
            return opener.open(urllib.request.Request(url, headers=headers),
                               timeout=timeout).read()
        except AseFetchError:
            raise
        except Exception as exc:                                   # noqa: BLE001
            last = exc
    raise AseFetchError(f'{url} 取不到：{last!r}')


def _get_html(url):
    body = _open(url)
    if len(body) < _MIN_HTML:
        raise AseFetchError(f'{url} 只有 {len(body)} 字节（<{_MIN_HTML}），疑似 WAF / 错误页')
    text = body.decode('utf-8', 'ignore')
    if 'revenues-table' not in text:
        raise AseFetchError(f'{url} 里没有 revenues-table（落地页改版？）')
    return text


def _get_pdf(url):
    """PDF 三重校验：非 3xx（由 _open 保证）、体长、魔数。缺一不可（口径坑 1）。"""
    body = _open(url, referer=IR_PAGE)
    if len(body) < _MIN_PDF:
        raise AseFetchError(
            f'{url} 只有 {len(body)} 字节（<{_MIN_PDF}）—— '
            f'媒体主机对裸 UA 返 403 + 118 字节 HTML，见 fetch/ase.py 口径坑 1')
    if not body.startswith(b'%PDF-'):
        raise AseFetchError(f'{url} 首 5 字节是 {body[:5]!r}，不是 %PDF-')
    return body


# ══════════════════════════════════════════════════════════════════════════════
# 落地页 —— 只用来发现 PDF 链接与月份，金额一概不信（口径坑 2）
# ══════════════════════════════════════════════════════════════════════════════
def _year_rows(year):
    """返回 [(month 'YYYY-MM', 落地页印的金额 float|None, PDF 绝对 URL|None), …]。

    ⚠️ 必须先剥掉 HTML 注释（口径坑 11）。
    """
    html = _COMMENT_RE.sub('', _get_html(f'{IR_PAGE}?year={year}'))
    out = []
    for name, amount, cell in _ROW_RE.findall(html):
        if name not in _MONTH_NAME:
            continue
        href = _HREF_RE.search(cell)
        raw = amount.replace('$', '').replace(',', '').replace('﻿', '').strip()
        try:
            val = float(raw)
        except ValueError:
            val = None
        out.append((f'{year}-{_MONTH_NAME[name]:02d}', val,
                    urllib.parse.urljoin(IR_ORIGIN, href.group(1)) if href else None))
    return out


def _discover(years):
    """扫若干年的落地页，返回 {month: (落地页金额, PDF URL)}，只保留有 PDF 的月。"""
    found = {}
    for year in years:
        try:
            rows = _year_rows(year)
        except AseFetchError as exc:
            print(f'[ase][warn] {year} 年落地页跳过：{exc}')
            continue
        for month, val, url in rows:
            if url and month >= START_MONTH:
                found[month] = (val, url)
    if not found:
        raise AseFetchError(f'{years} 这几年的落地页一个 PDF 链接都没抓到（改版？）')
    return found


# ══════════════════════════════════════════════════════════════════════════════
# PDF 解析 —— token 流，不依赖列坐标
# ══════════════════════════════════════════════════════════════════════════════
def _pdf_tokens(blob):
    """PyMuPDF 的阅读顺序文本 → 逐行 token。NBSP 必须先归一（口径坑 3）。"""
    try:
        import fitz
    except ImportError as exc:                                     # pragma: no cover
        raise AseFetchError('需要 pymupdf（fitz）才能解析 ASEH 的新闻稿 PDF') from exc
    with fitz.open(stream=blob, filetype='pdf') as doc:
        raw = '\n'.join(page.get_text() for page in doc)
    toks = []
    for line in raw.split('\n'):
        s = re.sub(r'\s+', ' ', line.replace(' ', ' ')).strip()
        if s:
            toks.append(s)
    return toks


def _pdf_tables(blob):
    """解析一份新闻稿，返回四张月表：

        {'C': {month: NT$mn}, 'A': {month: NT$mn},
         'C_USD': {month: US$mn}, 'A_USD': {month: US$mn}}

    C = CONSOLIDATED NET REVENUES，A = (IC-)ATM NET REVENUES；
    `_USD` 后缀那两张是**公司自印的美元实绩**，不是本模块折算的（口径坑 12）。
    一份 PDF 通常给三个月（当月 / 上月 / 去年同月）。
    Q 表、FY 表、Pro Forma 表全部剔除（口径坑 7、8）。

    分部与货币是**两个正交的维度**：section 由表标题切换、货币由
    `(NT$ Million)` / `(US$ Million)` 那一行切换，两者不互相重置 ——
    美元表紧跟在同一分部的新台币表之后，中间没有新的 section 标题。
    """
    toks = _pdf_tokens(blob)
    out = {'C': {}, 'A': {}, 'C_USD': {}, 'A_USD': {}}
    section = None
    for i, tok in enumerate(toks):
        if tok.startswith('CONSOLIDATED NET REVENUES'):
            section = 'C'
            continue
        if re.match(r'^(IC-)?ATM NET REVENUES', tok):
            section = 'A'
            continue
        if tok.startswith('Pro Forma'):          # 口径坑 7：pro forma 不是实际数
            section = None
            continue
        if section is None:
            continue
        m_cur = _CURRENCY_RE.match(tok)
        if not m_cur:
            continue
        # 落到哪张表：分部 × 货币。美元走 `_USD` 后缀，与新台币表同一套解析路径 ——
        # 两条路径分家写过一次就会分叉，而这四张表的版式逐字相同。
        bucket = section if m_cur.group(1) == 'NT$' else section + '_USD'
        # 往回取列头（月份 / Q1 / FY …），往前取年份与数值
        j = i - 1
        while j >= 0 and toks[j] in ('Sequential', 'YoY'):
            j -= 1
        periods = []
        while j >= 0 and _PERIOD_RE.match(toks[j]):
            periods.append(toks[j])
            j -= 1
        periods.reverse()
        k = i + 1
        years = []
        while k < len(toks) and re.fullmatch(r'\d{4}', toks[k]):
            years.append(toks[k])
            k += 1
        while k < len(toks) and toks[k] == 'Change':
            k += 1
        if k >= len(toks) or not toks[k].startswith('Net Revenues'):
            continue
        k += 1
        values = []
        while k < len(toks) and _NUM_RE.match(toks[k]):
            values.append(toks[k])
            k += 1
        # 位置对齐后再筛月份列：Q21/Q22/Q23 这类列必须占位，否则整行错位（口径坑 8）
        for c, period in enumerate(periods):
            if period not in _MONTH_ABBR or c >= len(years) or c >= len(values):
                continue
            key = f'{years[c]}-{_MONTH_ABBR[period]:02d}'
            out[bucket].setdefault(key, float(values[c].replace(',', '')))
    empty = [k for k in _TABLES if not out[k]]
    if empty:
        raise AseFetchError(
            '新闻稿解析出 ' + '、'.join(f'{k}={len(out[k])} 个' for k in _TABLES)
            + f' 月份，{empty} 是空的 —— 版式变了？'
            '（若四张全是 0，先怀疑 NBSP，见口径坑 3）')
    # 四表月份键必须逐字相同（2026-08-18 全量实测，当时 99 期，无一例外；
    # 见「数据源」第 2 条）。⚠️ 校验的是四表**彼此**一致，不是「必有三个月」——
    # 头 12 期只有 2 个月键、2018-05 只有 1 个（口径坑 14）。
    # 不齐 = 某一张表的列跟其余三张对不上，而列错位正是这样露头的（口径坑 8）——
    # 这时任何一张表的数都不可信，整份作废，不做「取交集凑合用」。
    keysets = {k: frozenset(out[k]) for k in _TABLES}
    if len(set(keysets.values())) != 1:
        raise AseFetchError(
            '同一份新闻稿的四张表月份键不一致：'
            + '；'.join(f'{k}={sorted(keysets[k])}' for k in _TABLES)
            + ' —— 疑似列错位（口径坑 8），本份作废')
    return out


def press_date(blob):
    """从正文电头取公告日 'YYYY-MM-DD'。取不到返回 None（口径坑 9）。"""
    flat = ' '.join(_pdf_tokens(blob))
    m = re.search(r'TAIPEI,\s*(?:TAIWAN,\s*R\.O\.C\.,\s*)?([A-Z]+)\s+(\d{1,2}),\s*(\d{4})',
                  flat)
    if not m or m.group(1) not in _MONTH_UPPER:
        return None
    return datetime.date(int(m.group(3)), _MONTH_UPPER[m.group(1)],
                         int(m.group(2))).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# 交叉校验（只告警，不阻断）
# ══════════════════════════════════════════════════════════════════════════════
def _twse_latest():
    """TWSE OpenAPI 里 3711 的 (月份, 当月营收 NT$mn, 当年累计 NT$mn)。"""
    try:
        blob = _open(TWSE_API, tries=2, timeout=90)
        if len(blob) < 100_000:
            raise AseFetchError(f'TWSE OpenAPI 只有 {len(blob)} 字节，疑似壳页')
        for rec in json.loads(blob.decode('utf-8', 'ignore')):
            if rec.get('公司代號') == TWSE_CODE:
                roc = str(rec['資料年月'])                    # 11507 = 2026-07
                month = f'{int(roc[:-2]) + 1911}-{int(roc[-2:]):02d}'
                return (month,
                        float(rec['營業收入-當月營收']) / 1000.0,
                        float(rec['累計營業收入-當月累計營收']) / 1000.0)
    except Exception as exc:                                       # noqa: BLE001
        print(f'[ase][warn] TWSE OpenAPI 交叉校验跳过：{exc!r}')
    return None, None, None


def _html_amount_check(month, html_val, pdf_val):
    """落地页表格 vs PDF 正文。不一致只告警 —— 上游排版错误不该拖住抓取（口径坑 2）。"""
    if html_val is None or pdf_val is None:
        return
    if abs(html_val - pdf_val) > 0.5:
        print(f'[ase][warn] {month} 落地页表格印 {html_val:,.0f}、PDF 正文 {pdf_val:,.0f} '
              f'—— 以 PDF 为准（2026-01 有过同样的排版错，见口径坑 2）')


def _fx_sanity(month, ntd, usd, what):
    """隐含汇率护栏（口径坑 12）。**它挡的是列错位，不是汇率异动。**

    这两列本来就是各自从 PDF 抄下来的整数，没有任何算式把它们绑在一起 ——
    所以「NT$ ÷ US$ 落在合理区间」是一条**独立**的结构性证据：
    一旦哪天版式变了让 NT$ 值流进美元槽，比值当场变 1.0；反向错配约 1000。
    两种都远在硬区间之外，抓得住；而真实汇率再怎么走也到不了那儿。
    硬区间越界抛异常（数一定是坏的），软区间越界只告警（汇率可能真走远了）。
    """
    if usd <= 0:
        raise AseFetchError(f'{month} {what} 美元值是 {usd:,.0f} —— 非正数，解析坏了')
    rate = ntd / usd
    if not _FX_HARD[0] <= rate <= _FX_HARD[1]:
        raise AseFetchError(
            f'{month} {what} 反解隐含汇率 {rate:.3f} NTD/USD，落在硬区间 '
            f'{_FX_HARD} 之外（NT$ {ntd:,.0f} / US$ {usd:,.0f}）—— '
            f'这不是汇率异动，是新台币与美元两列串了，见 fetch/ase.py 口径坑 12。'
            f'本次不写入')
    if not _FX_SOFT[0] <= rate <= _FX_SOFT[1]:
        print(f'[ase][warn] {month} {what} 隐含汇率 {rate:.3f} NTD/USD 落在 '
              f'{_FX_SOFT} 之外（历史实测 27.60~32.84）—— 数照收，但值得看一眼')
    return rate


# ══════════════════════════════════════════════════════════════════════════════
# 对外的两个函数
# ══════════════════════════════════════════════════════════════════════════════
def latest_month(cache_dir):                                       # noqa: ARG001
    """官方源当前最新月 'YYYY-MM'。抓不到一律抛 AseFetchError。"""
    today = datetime.date.today()
    # 跨年那几天当年页可能还是空的，往回多看一年
    found = _discover([today.year, today.year - 1])
    newest = max(found)
    tables = _pdf_tables(_get_pdf(found[newest][1]))
    if newest not in tables['C']:
        raise AseFetchError(
            f'落地页说最新月是 {newest}，但那份 PDF 里没有 {newest} 的合并列 '
            f'（PDF 里有 {sorted(tables["C"])}）—— 落地页与 PDF 不同步')
    return newest


def _fmt(v):
    return f'{v:.0f}'


def _row(month, official):
    """按 COLUMNS 的列序拼一行。**建行与体检共用它** —— 两处各拼一次就会分叉。

    五个数据列里只有 `revenue_nonatm_ntd_mn` 是派生的（合并 − ATM，口径坑 4）；
    其余四列都是 PDF 正文印的原值，一个都不折算、不补差。
    美元侧**故意不建 nonatm 列**，理由见口径坑 6。
    顺手在这里过一遍隐含汇率护栏：它是唯一能把「两种货币串了」当场抓出来的判据，
    放在拼行处才能保证建行与体检两条路都走到（口径坑 12）。
    """
    c, a = official['C'][month], official['A'][month]
    cu, au = official['C_USD'][month], official['A_USD'][month]
    _fx_sanity(month, c, cu, '合并')
    _fx_sanity(month, a, au, 'ATM')
    if a > c:
        raise AseFetchError(
            f'{month} ATM NT$ {a:,.0f} > 合并 NT$ {c:,.0f} —— ATM 是合并的一个分部，'
            f'不可能更大，两张表串了')
    if au > cu:
        raise AseFetchError(
            f'{month} ATM US$ {au:,.0f} > 合并 US$ {cu:,.0f} —— 同上，美元两张表串了')
    return [month, _fmt(c), _fmt(a), _fmt(c - a), _fmt(cu), _fmt(au)]


def update(series_dir, cache_dir):                                 # noqa: ARG001
    """把新月份追加进 series/ase.csv，返回新增月份列表（升序）。

    幂等：已入库的月份不重写；既有行原样搬运，没有新月份时**文件字节级不变**。
    已有值永不覆盖 —— 与官方值不一致时**抛异常**（口径坑 6），由人判断。
    """
    csv_path = os.path.join(series_dir, 'ase.csv')
    with open(csv_path, newline='', encoding='utf-8') as fh:
        rows = list(csv.reader(fh))
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    if header != COLUMNS:
        raise AseFetchError(f'series/ase.csv 列不对：{header} != {COLUMNS}')
    have = {r[0]: r for r in body}

    today = datetime.date.today()
    last = max(have) if have else START_MONTH
    years = sorted({int(last[:4]), today.year - 1, today.year})
    found = _discover(years)

    missing = sorted(m for m in found if m >= START_MONTH and m not in have)
    if not missing:
        # 没有新月份也照样做一次交叉校验，但**绝不写文件**（幂等是验收项）
        _crosscheck(have)
        return []

    # 四张表各收一份。键是月份，值是官方印的整数（新台币 / 美元都不折算）。
    official = {k: {} for k in _TABLES}
    seen_html = {}
    for month in missing:
        html_val, url = found[month]
        tables = _pdf_tables(_get_pdf(url))
        # 四张表都得有当月那一列 —— 少任何一张都说明链接串行或版式变了。
        # （_pdf_tables 已经保证四表月份键相同，这里再点名当月是为了报错能指到月份。）
        absent = [k for k in _TABLES if month not in tables[k]]
        if absent:
            raise AseFetchError(
                f'{month} 的新闻稿里没有 {month} 那一列，缺表 {absent}'
                f'（C={sorted(tables["C"])}）—— 链接串行了？')
        seen_html[month] = html_val
        # 一份 PDF 顺带给出上月与去年同月，四张表全部收进来供重述体检
        for k in _TABLES:
            official[k].update(tables[k])

    # ── 重述体检：已入库月份逐格比对，不一致抛异常而不是改写（口径坑 6）──────────
    #    **五列一起比**。不许写成「新台币对上了就跳过美元」——
    #    2018Q4 实测过 NT$ 改了而 US$ 没改（口径坑 5），两侧各自独立。
    drift = []
    for month, row in sorted(have.items()):
        if any(month not in official[k] for k in _TABLES):
            continue
        want = _row(month, official)
        if row != want:
            drift.append((month, row, want))
    if drift:
        raise AseFetchError(
            'ASEH 新闻稿与已入库值不一致（疑似重述或解析变形），本次不写入：\n  '
            + '\n  '.join(f'{m}: 库内 {old} vs 官方 {new}' for m, old, new in drift[:5])
            + f'\n  （共 {len(drift)} 个月不一致；列序 {COLUMNS}）'
            + '\n  （2019 年那次 ATM 追溯重述就是这个形状，新台币与美元两侧都会动，'
              '但**动的月份可以不一样**，见 fetch/ase.py 口径坑 5）')

    added = []
    for month in missing:
        _html_amount_check(month, seen_html.get(month), official['C'][month])
        body.append(_row(month, official))
        have[month] = body[-1]
        added.append(month)

    body.sort(key=lambda r: r[0])
    with open(csv_path, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(body)

    _crosscheck(have)
    return added


def _crosscheck(have):
    """与 TWSE OpenAPI 当期对账。只告警，不阻断 —— 第三源挂掉不该拖住本页。"""
    month, val, ytd = _twse_latest()
    if not month:
        return
    newest = max(have) if have else None
    if newest and month > newest:
        print(f'[ase][warn] TWSE 已有 {month}，但 IR 落地页最新只到 {newest} —— 下次再跑')
    if month in have:
        mine = float(have[month][1])
        if abs(mine - val) > 1.0:
            print(f'[ase][warn] {month} 入库 {mine:,.0f} vs TWSE {val:,.0f} NT$mn 不符')
    if ytd:
        year = month[:4]
        mine_ytd = sum(float(r[1]) for m, r in have.items() if m[:4] == year and m <= month)
        if abs(mine_ytd - ytd) > 2.0:
            print(f'[ase][warn] {year} 年 1~{month[5:]} 月入库加总 {mine_ytd:,.0f} '
                  f'vs TWSE 累计 {ytd:,.0f} NT$mn 不符')


if __name__ == '__main__':                                         # pragma: no cover
    print('latest_month =', latest_month(None))
    print('added =', update(os.path.join(ROOT, 'series'), None))
