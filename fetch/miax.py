# -*- coding: utf-8 -*-
"""Miami International Holdings（NYSE: MIAX）月度成交量、市占与 RPC —— 无人值守抓取。

━━ 数据源 ━━
本模块有两个源，**口径不同、起点不同、绝不可混为一谈**，所以列名上用 `_api` 后缀分开。

【源 A】IR 站「Volume & RPC/Capture Report」PDF —— 口径权威，含 RPC，2025-01 起
  列表页 : https://ir.miaxglobal.com/volume-rpc-reports
  链接文字: "<年份> Historical Volumes RPC File (PDF)"，页面上恰好挂两条（当年 + 上一年）
  直链   : https://ir.miaxglobal.com/image/MIH_Volume_and_RPC_Report_{MMDDYYYY}.pdf
           上一年那份多一段年份：..._2025_05062026.pdf
           302 跳到 filecache.investorroom.com/mr5ir_miaxglobal/{n}/<同名>.pdf，
           `{n}` 每次抓可能不同（同一个文件实测拿到过 252 / 253），**必须走 302，不可拼**。
  文件名里的 MMDDYYYY 是**发布日不是数据月**，所以只能解析列表页拿链接，不能按月拼 URL
  （与 fetch/cboe.py 同理）。
  UA：`ir.miaxglobal.com` 对默认 `Python-urllib/3.x` 一律 **403**，换常规浏览器 UA 立刻 200。
  不是 Cloudflare 挑战、不是 Akamai JA3（没有 HOOD 那种「连上但永不返回」的症状）。

【源 B】miaxglobal.com 市占看板 JSON API —— ADV 深历史，无 RPC，2015-04 起
  https://www.miaxglobal.com/indsum/getDate?exchType=options
  https://www.miaxglobal.com/indsum/detail?tid=1&exchType=options&date=YYYYMMDD
  https://www.miaxglobal.com/indsum/detail?tid=1&exchType=equities&sumType=volume&date=YYYYMMDD
  https://www.miaxglobal.com/indsum/detail?tid=1&exchType=equities&sumType=notional&date=YYYYMMDD
  `tid=1` = MTD Average；date 给成**该月最后一个日历日**（周末也行，见口径坑 4），
  返回的就是该自然月每家交易所的日均量 + 一行 TOTAL。无鉴权、无 UA 校验。
  这是 **MIAX 自家官网**发布的数据，不是 FIA / investing.com 之类聚合商，符合仓库硬约束。
  ⚠ 它同时报出 Cboe / Nasdaq / NYSE / BOX / MEMX 各家的量 —— **那部分对别家而言是第三方，
  只入库 MIAX 自己的四家 + 全市场分母，绝不许倒灌进 series/cboe.csv**。

两个源都不需要浏览器登录态、不需要 curl_cffi / nscurl，标准库 urllib 加 UA 即可 —— 满足无人值守。

━━ 每一列的确切口径（下游换算定基名义额全靠这一节，写错比抓错更难发现）━━
月份键 `month` = 'YYYY-MM'，指**数据所属自然月**，不是发布月。
以下 ADV 一律是「期内总量 ÷ 期内交易日数」（PDF 脚注 1 原文），**日均、单边计一次**
（OPRA / 交易所自报成交量的行业惯例是每笔成交计一次，不是买卖双边各计一次）。

▍PDF 段（2025-01 起，官方口径权威）
  trading_days_options              当月美股**期权**交易日数（整数）。PDF 里 Options 段与
                                    U.S. Equities 段共用同一行值，本模块只取 Options 段那一行。
  industry_adv_options_kcontracts   **全行业**（全美 OPRA 挂牌）equity & ETF 期权 ADV，
                                    单位千张/日。这是 MIH 自报的行业分母，
                                    与 API 的 TOTAL 行差 3.1%-4.5%（见口径坑 3）。
  adv_multilist_options_kcontracts  MIAX 四所**合计** equity & ETF 期权 ADV，千张/日。
                                    **与 series/cboe.csv 的同名列逐字同口径**
                                    （Cboe 侧源标签 'Multiply-listed options (Equities & ETPs)'）。
  share_multilist_options_pct       MIH 官方自报份额（百分数，如 17.1 表示 17.1%）。
                                    官方只给 1 位小数；要更高精度请用 adv/industry 自算。
  rpc_multilist_options_usd         **滚动三月平均** RPC，美元/张。PDF 脚注 2 定义：
                                    交易与清算费 − 流动性返还 − 经纪/清算/交易所费 − Section 31 费，
                                    除以期内总张数。**与 cboe.csv 的 rpc_multilist_options_usd
                                    同名同义**（两边脚注逐字一致）。滞后一个月，见口径坑 6。
  industry_adv_equities_mnshares    **全美股票市场** ADV，百万股/日，**含 TRF 场外**。
                                    官方承认这一列出过数据处理错误并重述过，见口径坑 7。
  adv_equities_mnshares             MIAX Pearl Equities ADV，百万股/日。
                                    cboe.csv 那边是 adv_us_equities_matched_shares_bn（十亿股），
                                    横截面换算 1 : 1000。
  share_equities_pct                MIAX Pearl Equities 份额（百分数），分母含 TRF。
  capture_equities_usd_per100shares 每 100 股捕获，美元，滚动三月平均。**长期为负**
                                    （inverted / taker-rebate 定价），PDF 里写成 ($0.028)。
                                    ⚠ Cboe 同位列 rpc_us_equities_usd_per100shares 的分母是
                                    per 100 **touched** shares，MIAX 脚注 3 是
                                    "divided by one-hundredth of total shares" ——
                                    **名字像，分母不同，不能相减、不能同轴。**
  trading_days_futures              MIAX Futures 交易日数（与期权差 0-1 天）。
  adv_futures_ag_contracts          农产品期货 ADV，**张/日（不是千张）**。
                                    实质是 Minneapolis Hard Red Spring Wheat 一个品种。
  rpc_futures_ag_usd                农产品期货滚动三月 RPC，美元/张（$1.8-2.5 量级）。
  adv_futures_fin_contracts         金融期货（Bloomberg 股指期货系列）ADV，张/日。
                                    产品 2026-05-17 上线（trade date 05-18），**2026-05 才有**。
  rpc_futures_fin_usd               金融期货滚动三月 RPC，美元/张，**目前为负**（新品促量返还）。

▍API 段（`_api` 后缀 = 源 B，口径与 PDF 不同，2015-04 起）
  adv_miax_options_api_kcontracts      MIAX Options（代码 M）单所 equity & ETF 期权 ADV，千张/日
  adv_pearl_options_api_kcontracts     MIAX Pearl Options（P），2017-02 起
  adv_emerald_options_api_kcontracts   MIAX Emerald（D），2019-03 起
  adv_sapphire_options_api_kcontracts  MIAX Sapphire（S），2024-08 起
      以上四列 = 各所 EQUITY_OPTION_TOTAL_AVERAGE_VOLUME ÷ 1000。
      **四列之和 ≠ adv_multilist_options_kcontracts**，实测（两源重叠的 19 个月）
      低 0.02%-0.78%，见口径坑 3。
      某所尚未开业的月份，API 返回体里根本没有那一行 —— 本模块留空而不是写 0，
      因为我们没有观测到官方说「零」，只是它不在表里。下游求四所合计时按缺失即 0 处理。
  adv_index_options_api_kcontracts     MIAX 四所**合计**指数期权 ADV，千张/日。
      这是本模块唯一一个求和列：拆成四列会多出三列永远为 0 的噪音。
      **当前为 0，但不是恒为 0** —— 实测 2019-02 … 2024-12 共 **57 个月**非零，
      **全部挂在 MIAX (M) 一所**，峰值 2019-12 日均 10,208 张、2020-01 日均 5,248 张。
      别写 assert == 0（见口径坑 8）。
      与 Cboe 的 adv_index_options_kcontracts（数百万张/日、利润中枢）并排即见结构差异。
  industry_adv_options_api_kcontracts  **全行业** equity & ETF 期权 ADV，千张/日，
      取 API 的 TOTAL 行。它是 OPRA 挂牌代码分类，PDF 的 Industry ADV 更接近 OCC 的
      equity+ETF 分类，两者差 3.1%-4.5%，**不可互换**。
      这一列还兼任「本月 API 已入库」的哨兵（TOTAL 行每月必在），见 update()。
  adv_equities_api_mnshares            MIAX Pearl Equities ADV，百万股/日，2020-12 起。
      = PEARLEQ (H) 行 EXCHANGE_AVERAGE_TRADE_VOLUME ÷ 1e6。与 PDF 的 adv_equities_mnshares
      同口径：两源重叠的 19 个月里最大绝对差 0.47（2025-09，PDF 205 vs API 204.53），
      纯粹是 PDF 四舍五入到整数的痕迹。API 这一列精度更高。
  adnv_equities_api_usdbn              MIAX Pearl Equities **日均名义额**，十亿美元/日，2020-12 起。
      = PEARLEQ (H) 行 EXCHANGE_AVERAGE_NOTIONAL_VALUE ÷ 1e9（sumType=notional）。
      **本仓 MIAX 唯一的金额口径列**，其余全是张数/股数。
  industry_adv_equities_api_mnshares   全美股票市场 ADV，百万股/日，含 TRF，2020-12 起。
      取交易所行的 TOTAL_MARKET_AVERAGE_TRADE_VOLUME（见口径坑 5 的陷阱字段）。
  industry_adnv_equities_api_usdbn     全美股票市场日均名义额，十亿美元/日，含 TRF，2020-12 起。
      取交易所行的 TOTAL_MARKET_AVERAGE_NOTIONAL_VALUE。
      这一列兼任「本月股票 API 已入库」的哨兵。

**本模块不做任何口径换算**：官方发张数就存张数、发金额就存金额并在列名注明币种。
唯一做的是**量纲对齐**（÷1000 / ÷1e6 / ÷1e9），因为列名后缀已经把单位写死了。
张数 × 乘数 × 基期价格那一层是 build/notional.py 的事，不在这里。

━━ 发布节奏 ━━
次月第 3-5 个工作日，与月度新闻稿同一天发（PDF 与 PR 同步更新）。实测（按 PDF 自述 Updated on）：
  2025-11 数据 → 2025-12-05（次月第 5 个工作日 / 月末后第 5 个日历日）
  2026-05 数据 → 2026-06-03（第 3）
  2026-06 数据 → 2026-07-07（第 4；7/3 因独立日休市，= 月末后第 7 个日历日）
  2026-07 数据 → 2026-08-05（第 3）
月度报表**独立于季报**（2026-08-05 当天既发 7 月数据也发 Q2 财报，但 6 月数据早在 7/7 就发了），
所以 build/roster.py 的 LAG 不需要为季末月单独开一档。

**source_date 只认 PDF 第 2 行自述的 `Updated on <Month D, YYYY>`。**
HTTP Last-Modified **不是**权威字段：实测 5 份里 3 份与 PDF 自述不一致，且一律**早 1-3 天**
（文件先上传、通稿后挂）——
  08052026.pdf  Updated on August 5, 2026    last-modified Wed, 05 Aug 2026  一致
  2025_05062026 Updated on May 6, 2026       last-modified Wed, 06 May 2026  一致
  12052025.pdf  Updated on December 5, 2025  last-modified Tue, 02 Dec 2025  **早 3 天**
  06032026.pdf  Updated on June 3, 2026      last-modified Tue, 02 Jun 2026  **早 1 天**
  07072026.pdf  Updated on July 7, 2026      last-modified Mon, 06 Jul 2026  **早 1 天**
拿 last-modified 当发布日会把 2025-11 那期记成 12-02（官方标注 12-05）。
本模块把 last-modified 写进 evidence 当**辅助线索**，权威值取 PDF 自述那一行。

━━ 口径坑（按踩坑概率排序）━━
1. **PDF 里的数字会被拆成两个 word，按 token 顺序解析会静默出错。**
   2025 年那份里 `53,135` 的字距使 pdfplumber.extract_words() 返回 '5' + '3,135'；
   `195` 返回 '1' + '95'。用 text.split() 的顺序对齐列，会把 Jan-25 行业 ADV 写成 3,135
   （真值 53,135，**差 17 倍**）、Pearl Equities 写成 95（真值 195）—— 全程不抛异常。
   2025-12-05 那份更狠，连 `Trading Days` 整行都拆成 '2' '0' '1' '9' '2' '1'…
   **解法**：按表头行每个 Mon-YY 的 x 中心建列桶，整行数值区的 word 按最近桶分组、
   桶内按 x 拼串，最后才 float()。见 _parse_page。
   「在最新一期上测通过」不代表在去年那份上也对 —— 两份都要测。
2. **同一个行标签在三个 section 里各出现一次，且标签会被脚注上标折行。**
   'Trading Days' / 'MIH market share' / 'Rolling three-month average RPC' 在
   Options (Equity and ETF) / U.S. Equities / Futures 三段里重复，必须先切段再查行。
   `Industry ADV(1) (contracts, thousands)` 的上标 (1) 基线比正文高约 1.4pt，
   行聚簇容差 ≤2pt 会把 'ADV(1)' 单独切成一行、标签变成 'Industry (contracts, thousands)'，
   当场失配。容差取 **4pt**（行距约 9pt），并把 (1)~(9) 脚注号剥掉后**全等**匹配。
3. **API 的 MIAX 四所合计比 PDF 低，行业分母差得更多。**
   实测两源重叠的全部 19 个月（2025-01…2026-07）：
     四所合计/PDF = 0.9922~0.9998（低 0.02%-0.78%；2026 那 7 个月收窄到 0.9967~0.9976）
     行业 API/PDF = 0.9546~0.9758（低 2.4%-4.5%）
   方向始终一致（API 更小），是分类口径差（PDF 更接近 OCC 的 equity+ETF 分类，API 是 OPRA
   挂牌代码分类，ETF 期权归属不同），不是抓错。所以两套列并存、名字分开，
   **画图时 2024-12 → 2025-01 换源那一格必须标结构性断点**，否则会凭空冒出一个假台阶。
4. **indsum API 对未来日期与月中日期会静默返回错的月份。**
   date=20261231（未来）返回的是 01/08/2026 → 05/08/2026（当月 MTD），不是空、不是报错；
   date=20260715（月中）返回半个月。所以：
   （a）先打 getDate 拿官方最新可用交易日，只请求**已经整月过完**的月份；
   （b）再校验返回体的 DATA_START_DATE 是该月 1 号、DATA_END_DATE 落在该月且距月末 ≤4 天
        （月末逢周末会正确回落到最后交易日，例如 2021-01 返回 29/01）。
   日期格式是 **DD/MM/YYYY，不是美式**。传该月最后一个**日历日**即可，不需要交易日历。
5. **TOTAL 行有个陷阱字段。** 股票端交易所行的 TOTAL_MARKET_AVERAGE_TRADE_VOLUME
   = 17,441,439,632（真·全市场），但 **TOTAL 行自己**的同名字段 = 331,387,353,008
   （≈19 倍，等于按行数重复累加）；notional 端同病（1,028bn vs 19,540bn）。
   所以全市场分母只取**交易所行**的 TOTAL_MARKET_*，本模块还断言各交易所行取值一致。
6. **RPC / capture 滞后一个月，最新月天然为空 —— 这不是解析失败。**
   与 Cboe 完全一样：2026-08-05 那期里 Jul-26 的 ADV 有值，rpc_multilist_options_usd /
   capture_equities_usd_per100shares / rpc_futures_* 四格全空。
   _validate_pdf 只对「该份 PDF 里最新的有数月」豁免 RPC 缺失，更早的月缺 RPC 一律抛异常。
7. **官方会重述，而且不止一列。** 2025 年那份 PDF 的脚注 4 白纸黑字承认
   U.S. equities 行业 ADV 在 2026-02 和 2025 若干月「因数据处理错误报错了」。
   两期 2025 年 PDF 逐格 diff：2025-07 17,648 → 18,033（+2.2%）、2025-05 17,585 → 17,586、
   2025-08 16,379 → 16,380。**但重述不止 industry_adv_equities_mnshares** ——
   两期 2026 年 PDF 逐格 diff 还抓到 rpc_futures_ag_usd 2026-04 从 1.981 改成 1.977。
   所以本模块照 fetch/spgi.py 的做法：已有值**永不覆盖**，但每次重解析都与库内
   **全部 14 个 PDF 列**逐格比对，不同就打 warning（不是静默跳过），
   否则这类修订永远发现不了。要真刷历史请人工决定。
8. **别写 `assert index_options == 0`。** 实测 136 个月里有 **57 个月**指数期权非零
   （2019-02 至 2024-12，全部挂在 MIAX (M) 一所），峰值 2019-12 日均 10,208 张、
   2020-01 日均 5,248 张。当前为 0 是事实，恒为 0 不是；回补时那个 assert 会当场炸。
9. **跨年那一期要下两份 PDF，而且上一年那份会被重新发布。**
   MIH_Volume_and_RPC_Report_2025_05062026.pdf 是 2026-05-06 才更新的，里面 Dec-25 的
   RPC（$0.106）已经填上 —— 这一格在 2025-12-05 那份里还是空的。
   所以 MIAX **没有** Cboe 那种「12 月 RPC 永久窟窿」，代价是每次 update() 都要把
   当年 + 上一年两份都下下来解析并合并，否则 12 月 RPC 会一直留白。
10. **选链必须要求年份前缀。** 列表页上有 **5 条**相关链接，含一整块 2025-12-05 的陈旧区块，
    其中一条 PDF 链接的文字是**没有年份的** 'Historical Volumes RPC File (PDF)'
    （指向 2025-11 那份旧文件）。取第一个匹配 = 拿到旧 PDF。
    只接受 `^(20\\d{2}) Historical Volumes RPC File \\(PDF\\)$` 并断言恰好命中 2 条。
11. **旧期 PDF 是「部分存活」不是「全死」，而且存活与否不可预测。**
    实测 MIH_Volume_and_RPC_Report_ 后接 MMDDYYYY 的七个历史文件名：
      06032026 → 200 / 420,187 bytes    07072026 → 200 / 225,963 bytes
      12052025 → 200 / 141,521 bytes
      04072026 → 404   09052025 → 404   05062026 → 404（活着的是带年份前缀的
                                        `..._2025_05062026.pdf`，两个文件名不是一回事）
      02032026 → 404
    所以可以机会性回补，但**回补不能是必要路径**，也不能因为某一期 404 就让 update() 失败。
    本模块因此**只用列表页上挂着的那两份**，不去猜历史文件名 —— 猜中了也补不出新信息
    （那两份已覆盖 2025-01 至今全部月份），猜不中反倒让每月的 cron 多打一串 404。
12. **Futures 段的表结构 2025 → 2026 变过。** 2025 那份只有一行 MIH - ADV (contracts)
    （当时只有农产品，没有子标题）；2026 那份分成 Agricultural: / Financial: 两个子标题。
    所以 agricultural 的行查不到时回落到「无子标题」那一份，见 _pdf_cell。
    2026 那份的 Financial 段还多两行 'Trading days from launch' 与
    'MIH - ADV from launch trade date (contracts)'（金融期货首月的另一种 ADV 定义：
    分母只算上线后的交易日，2026-05 是 13,105 而非 5,897）。**同一格两个数**，
    入库会制造永久的解释负担，本模块只取主行，把这件事写在这里。
13. **股票端 API 的历史比期权端短得多。** 期权 2015-04 起（2015-03 返回 []），
    股票 2020-12 起（2020-11 返回 []）—— Pearl Equities 2020 年才开业，这就是它的全生命周期。
    两条线起点不同，不要混为一谈；RPC 更是只有 2025-01 起。
14. **单所线会被内部导流搞出假信号。** 实测 Emerald 上线放量的 2019-03：MIAX (M) 单所
    721.3k 张/日，比 2018-03 的 797.2k 低 9.5%，而集团四所合计跳到 1,714.2k。
    单所量下滑是**集团内部导流**，不是丢份额 —— 画单所线必须标注，
    否则「MIAX Options 单所量下台阶」会被读成竞争力恶化。
    同理 Sapphire 2024-08 上线、Pearl 2026 年量的转移，都属于这一类。
15. **跨年时可能出现「空模板」PDF —— 一份没数据不能拖垮另一份。**（未实测，防御性设计）
    每份 PDF 的月份列是一整年 12 列，未来月份天然全空（2026-08-05 那份的 Aug-Dec 就是空的）。
    所以年初挂出新一年的文件时，它有可能 12 列全空。若把「解析后没有任何有数的月份」
    当成错误抛出，同一次 update() 里**另一份有数据的** PDF（12 月的数据正在里面）
    会被一起拖垮，白等一个月。本模块因此把空模板当作合法状态跳过，
    只有两份都空才报错。放行的前提是表头与全部 14 个行标签都还在（缺任何一个仍然抛异常）。
    另外「至少跑成一条闭合检验」这条要求只在有 ≥2 个有数月时才生效 ——
    年初只填一个月、且版式恰好没有 Year to Date 列时，季度/年度列一个都凑不齐。

━━ 交叉核对（建库时实测，出处均为一手披露）━━
· 2026-08-05 新闻稿 https://ir.miaxglobal.com/2026-08-05-Miami-International-Holdings-
  Reports-July-2026-Trading-Results（PRNewswire 原表）：Jul-26 / Jul-25 / Jun-26 三列
  共 **32 格与 series/miax.csv 逐字全等**（含 Trading Days 两段、行业与 MIH 的期权与股票
  ADV、两个份额、农产品与金融期货 ADV）。
· 10-K miax-20251231.htm（EDGAR CIK 0001438472，2026-03-06 报送）「Key Business Metrics」，
  拿 2025 年 12 个月按交易日加权回算：
    交易日 250（期权）/ 251（期货）—— 与 10-K 完全相同
    Market ADV Equity&ETF 55,797.6 vs 55,798（-0.00%）
    MIH ADV Equity&ETF     9,537.9 vs  9,538（-0.00%）
    MIH ADV equities         183.2 vs    183（+0.11%）
    Agricultural ADV      12,989.6 vs 12,989（+0.00%，10-K 另给总张数 3,260,353/251=12,989.5）
  **唯一对不上的是 industry_adv_equities_mnshares：加权 17,584.3 vs 10-K 17,550（+0.20%）。**
  这不是解析错 —— PDF 自己的 FY'25 列写的就是 17,585，是两份官方文件互相打架
  （正是脚注 4 承认出过数据处理错误的那一列）。**别把这一列对 10-K 设成硬断言。**
· PDF 的 FY'25 聚合列同时核到 10-K 的三个 RPC/capture 年度值：
  Total Options RPC $0.108、Equities capture $(0.012)、Agricultural RPC $2.241 —— 全部一致。
  （年度 RPC 不是月度滚动 RPC 的加权平均，只能这样核，所以聚合列不入库、只做校验。）

━━ 依赖 ━━ pdfplumber（读 PDF，requirements.txt 已有）。不依赖 pandas。
"""

import calendar
import csv
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from urllib.parse import urljoin

LISTING_URL = 'https://ir.miaxglobal.com/volume-rpc-reports'
API_BASE = 'https://www.miaxglobal.com/indsum/'

# ir.miaxglobal.com 对默认 Python-urllib UA 返回 403（口径坑：见 docstring 数据源节）。
_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# 逐月打 API 时的间隔。实测 136 次连续请求 114 秒（~0.84 s/次）无 429、无封禁，
# 这里主动放慢一点纯粹是礼貌 —— 首次建库要打约 270 次，之后每月只有 1-3 次。
_API_DELAY = 0.15

# 两条历史起点，都是实测边界（再往前一个月返回空数组），不是猜的。
API_OPTIONS_START = '2015-04'      # 2015-03 → []
API_EQUITIES_START = '2020-12'     # 2020-11 → []
FIN_FUTURES_START = '2026-05'      # PDF 脚注 4：金融期货 2026-05-17 上线（trade date 05-18）

# ── PDF 表结构：(csv 列名, section, sub, 归一化后的行标签) ────────────────────
# section / sub 用表里的小标题定位，见「口径坑 2」。同名标签在三段里各出现一次。
_S_OPT, _S_EQ, _S_FUT = 'options', 'equities', 'futures'
_SECTION_TITLES = {
    'Options (Equity and ETF)': _S_OPT,
    'U.S. Equities': _S_EQ,
    'Futures': _S_FUT,
}
_SUB_TITLES = {'Agricultural:': 'agricultural', 'Financial:': 'financial'}

PDF_SPEC = [
    ('trading_days_options',              _S_OPT, None, 'Trading Days'),
    ('industry_adv_options_kcontracts',   _S_OPT, None, 'Industry ADV (contracts, thousands)'),
    ('adv_multilist_options_kcontracts',  _S_OPT, None, 'MIH ADV (contracts, thousands)'),
    ('share_multilist_options_pct',       _S_OPT, None, 'MIH market share'),
    ('rpc_multilist_options_usd',         _S_OPT, None, 'Rolling three-month average RPC'),
    ('industry_adv_equities_mnshares',    _S_EQ,  None, 'Industry ADV (shares, millions)'),
    ('adv_equities_mnshares',             _S_EQ,  None, 'MIH ADV (shares, millions)'),
    ('share_equities_pct',                _S_EQ,  None, 'MIH market share'),
    ('capture_equities_usd_per100shares', _S_EQ,  None,
     'Rolling three-month average capture - per 100 shares'),
    ('trading_days_futures',              _S_FUT, None, 'Trading Days'),
    ('adv_futures_ag_contracts',          _S_FUT, 'agricultural', 'MIH - ADV (contracts)'),
    ('rpc_futures_ag_usd',                _S_FUT, 'agricultural',
     'Rolling three-month average RPC'),
    ('adv_futures_fin_contracts',         _S_FUT, 'financial', 'MIH - ADV (contracts)'),
    ('rpc_futures_fin_usd',               _S_FUT, 'financial', 'Rolling three-month average RPC'),
]
PDF_COLS = [c for c, _s, _b, _l in PDF_SPEC]

# 「必须有值」与「允许最新月为空」两组，见口径坑 6。
_PDF_LAGGED = ('rpc_multilist_options_usd', 'capture_equities_usd_per100shares',
               'rpc_futures_ag_usd', 'rpc_futures_fin_usd')
_PDF_FIN = ('adv_futures_fin_contracts', 'rpc_futures_fin_usd')

# ── API 列 ──────────────────────────────────────────────────────────────
# EXCHANGE_GROUP == 'MIAX' 的四家期权所。出现表里没有的第五家 → 抛异常，
# 绝不静默丢掉（新开一家所而我们不知道 = 四所合计从此偏低）。
API_OPT_EXCH = {
    'MIAX (M)':     'adv_miax_options_api_kcontracts',
    'PEARL (P)':    'adv_pearl_options_api_kcontracts',
    'EMERALD (D)':  'adv_emerald_options_api_kcontracts',
    'SAPPHIRE (S)': 'adv_sapphire_options_api_kcontracts',
}
# 股票端 MIAX 只有一家场内：MIAX Pearl Equities。同样地，冒出第二家就抛异常。
API_EQ_EXCH = ('PEARLEQ (H)',)

API_OPT_COLS = list(API_OPT_EXCH.values()) + [
    'adv_index_options_api_kcontracts', 'industry_adv_options_api_kcontracts']
API_EQ_COLS = ['adv_equities_api_mnshares', 'adnv_equities_api_usdbn',
               'industry_adv_equities_api_mnshares', 'industry_adnv_equities_api_usdbn']

# 「这个月的 API 已经入库了」的哨兵：TOTAL 行每月必在，所以这两列一旦有值就代表抓全了。
# 不能用四所里的任何一列当哨兵 —— 未开业的月份它们天然为空，会导致每次重跑都重抓。
_SENTINEL_OPT = 'industry_adv_options_api_kcontracts'
_SENTINEL_EQ = 'industry_adnv_equities_api_usdbn'

COLUMNS = ['month'] + PDF_COLS + API_OPT_COLS + API_EQ_COLS

_MONTH_HDR = re.compile(r"^[A-Z][a-z]{2}-\d{2}$")
_QTR_HDR = re.compile(r"^Q([1-4])'(\d{2})$")
_FY_HDR = re.compile(r"^FY'(\d{2})$")
_FOOTNOTE_ROW = re.compile(r'^\d\)$')
_UPDATED_ON = re.compile(r'Updated\s+on\s+([A-Z][a-z]{2,8}\.?\s+\d{1,2},\s+\d{4})')
_TITLE_YEAR = re.compile(r'Report\s*-\s*(20\d{2})\s*$')
_YEAR_LINK_TITLE = re.compile(r'^(20\d{2}) Historical Volumes RPC File \(PDF\)$')
_ANCHOR = re.compile(r'<a\b[^>]*\bhref="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
_TAGS = re.compile(r'<[^>]+>')

# 行聚簇容差：行距约 9pt，脚注上标基线比正文高约 1.4pt，取 4pt 两头都够（口径坑 2）。
_ROW_TOL = 4.0
# 数值 word 落到月份桶里时，允许的最大偏移（列间距的倍数）。
# 数字右对齐、表头居中，天然有个稳定的右偏；五份不同期次的 PDF 实测最差 0.386
# （08052026 / 2025_05062026 / 12052025 / 06032026 / 07072026），取 0.45 留余量。
# 超过就说明版式漂了，宁可炸 —— 但这只是第二道网，主力是 _closure_check。
_BUCKET_TOL = 0.45


class MiaxFetchError(RuntimeError):
    """源站结构变化 / 下载失败 / 解析结果不完整。一律炸掉，绝不静默写 NaN。"""


# ── 网络 ────────────────────────────────────────────────────────────────
def _http_get(url, timeout=60):
    """返回 (bytes, headers)。失败一律抛 MiaxFetchError，不返回空内容。"""
    req = urllib.request.Request(url, headers={
        'User-Agent': _UA,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), dict(r.headers)
    except Exception as e:                                  # noqa: BLE001
        raise MiaxFetchError('下载失败 %s: %r' % (url, e)) from e


def _write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def _discover_pdfs(cache_dir):
    """解析列表页，返回 [(year:int, url:str)]，恰好两条（当年 + 上一年），按年份降序。

    为什么必须要求年份前缀（口径坑 10）：列表页上有 5 条相关链接，其中一整块是
    2025-12-05 的陈旧区块，它那条 PDF 链接的文字是**没有年份的**
    'Historical Volumes RPC File (PDF)'，指向 2025-11 那一期。
    用 endswith('Historical Volumes RPC File (PDF)') 或「取第一个匹配」都会拿到旧文件，
    而旧文件解析得出来、数字也对 —— 只是少了最近 8 个月，**不报错**。
    """
    html, _hdr = _http_get(LISTING_URL)
    html = html.decode('utf-8', 'replace')
    # 存一份原始页面：源站改版时可以事后取证
    _write_bytes(os.path.join(cache_dir, 'miax_listing.html'), html.encode('utf-8'))

    hits = []
    for href, inner in _ANCHOR.findall(html):
        txt = re.sub(r'\s+', ' ', _TAGS.sub('', inner)).strip()
        m = _YEAR_LINK_TITLE.match(txt)
        if m:
            hits.append((int(m.group(1)), urljoin(LISTING_URL, href), txt))
    if len(hits) != 2:
        raise MiaxFetchError(
            '列表页上「<年份> Historical Volumes RPC File (PDF)」应恰好 2 条'
            '（当年 + 上一年），实际命中 %d 条：%s。源站可能改版 —— %s'
            % (len(hits), [(y, t) for y, _u, t in hits], LISTING_URL))
    hits.sort(reverse=True)
    if hits[0][0] - hits[1][0] != 1:
        raise MiaxFetchError('列表页上两份 PDF 的年份不连续：%s'
                             % [y for y, _u, _t in hits])
    for _y, url, _t in hits:
        if not url.lower().endswith('.pdf'):
            raise MiaxFetchError('年份前缀的链接指向的不是 PDF：%s' % url)
    return [(y, u) for y, u, _t in hits]


def _fetch_pdfs(cache_dir):
    """下载列表页上挂着的两份 PDF，返回 [(year, 本地路径, last_modified 原文或 None)]。

    只下列表页给的这两份，不去猜历史文件名 —— 旧期是「部分存活」，
    猜到的 404 会把 update() 拖垮，而它们本来就补不出新信息（口径坑 11）。
    """
    out = []
    for year, url in _discover_pdfs(cache_dir):
        data, hdr = _http_get(url)
        if not data.startswith(b'%PDF'):
            raise MiaxFetchError('%s 返回的不是 PDF（前 16 字节 %r）' % (url, data[:16]))
        path = os.path.join(cache_dir, os.path.basename(url))
        _write_bytes(path, data)
        lm = hdr.get('Last-Modified') or hdr.get('last-modified')
        out.append((year, path, lm))
    return out


# ── PDF 解析 ────────────────────────────────────────────────────────────
def _norm(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def _lab(words):
    """把一行的标签 word 拼成归一化标签：剥脚注号 (1)~(9)，压空白。

    官方在行名里挂上标脚注 —— 'Industry ADV(1) (contracts, thousands)'、
    'Rolling three-month average RPC(2)'。脚注号历史上加过也挪过位置，
    留着它做全等匹配会在某个月突然全表失配；而约定的标签里没有一处真的写着 (数字)，
    所以直接剥掉是安全的。
    """
    return _norm(re.sub(r'\(\d\)', '', ' '.join(w['text'] for w in words)))


def _num(s, where):
    """'53,135' → 53135.0；'($0.028)' → -0.028；'17.6%' → 17.6；'-' / 'n/a' → None。

    认不出来的一律抛异常。静默返回 None 会变成 CSV 里一个空格，
    而空格看上去和「官方本来就没填」一模一样 —— 那正是本仓最忌讳的失败模式。
    """
    t = s.replace(',', '').replace('$', '').replace('%', '').strip()
    neg = t.startswith('(') and t.endswith(')')
    t = t.strip('()').strip()
    if t in ('', '-', '—', '–', 'n/a', 'N/A', 'NA'):
        return None
    try:
        v = float(t)
    except ValueError:
        raise MiaxFetchError('%s 解析不出数字：%r' % (where, s))
    return -v if neg else v


def _rows(page):
    """把 page 的 word 按 y 聚成行（容差 4pt），行内按 x 升序。"""
    ws = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    ws.sort(key=lambda w: (w['top'], w['x0']))
    out, cur = [], []
    for w in ws:
        if cur and abs(w['top'] - cur[0]['top']) > _ROW_TOL:
            out.append(sorted(cur, key=lambda x: x['x0']))
            cur = []
        cur.append(w)
    if cur:
        out.append(sorted(cur, key=lambda x: x['x0']))
    return out


def _parse_page(page, fname):
    """解析单页宽表，返回 (title, updated_on_str, months, aggs)。

    months: {(section, sub, label): {'YYYY-MM': float|None}}
    aggs  : {(section, sub, label): {agg_key: float|None}}，agg_key 形如
            'Q1-2026' / 'FY-2025' / 'YTD'，只用于闭合检验（_closure_check），不入库。

    为什么必须按 x 坐标分桶而不是按 token 顺序（口径坑 1）：
      官方 PDF 的字距会把 '53,135' 拆成 '5' 和 '3,135' 两个 word。
      按顺序对齐列时这一行会多出一个 token，后面所有列整体错位，
      而 float('3,135'.replace(',','')) 完全合法 —— **不抛异常，只是数量级错 17 倍**。
      按 x 中心分桶后，'5' 和 '3,135' 落进同一个桶、按 x 拼回 '53,135'，天然免疫。
    """
    rows = _rows(page)
    if not rows:
        raise MiaxFetchError('%s 第一页没有可提取的文字（扫描件？）' % fname)

    title = _norm(' '.join(w['text'] for w in rows[0]))
    updated = None
    for r in rows[:4]:
        m = _UPDATED_ON.search(_norm(' '.join(w['text'] for w in r)))
        if m:
            updated = m.group(1)
            break

    # 表头行：至少 6 个 Mon-YY 形状的 word
    hdr_i = next((i for i, r in enumerate(rows)
                  if len([w for w in r if _MONTH_HDR.match(w['text'])]) >= 6), None)
    if hdr_i is None:
        raise MiaxFetchError('%s 找不到含 ≥6 个 Mon-YY 的表头行，官方版式可能已变' % fname)
    hdr = rows[hdr_i]

    # 表尾：第一条脚注行（'1)' '2)' …）。脚注正文横跨整页，会污染标签/数值分区。
    stop_i = next((i for i in range(hdr_i + 1, len(rows))
                   if _FOOTNOTE_ROW.match(rows[i][0]['text'])), len(rows))

    # 表头 word 先按「词间空隙」合并成列。
    # 为什么必须合并（血的教训）：'Year to Date(4)' 是三个 word，若各算一个列中心，
    # 'Year' 那个中心（x≈743）会插到 Q3 列（x≈715）和真正的 YTD 列（x≈753）之间，
    # 把 Q3 列右半边的数字吸走。2025-12-05 那份 PDF 里 Trading Days 的 Q3 值 '64'
    # 被拆成 '6' 和 '4' 两个 word，'4' 就被 'Year' 抢走，Q3 变成 6 —— 幸亏被
    # _closure_check 当场抓住（月度求和 64 ≠ 6）。列内词距约 1.2pt、列间距 ≥16pt，
    # 阈值取 8pt 两头都够。
    groups, cur = [], [hdr[0]]
    for w in hdr[1:]:
        if w['x0'] - cur[-1]['x1'] > 8.0:
            groups.append(cur)
            cur = []
        cur.append(w)
    groups.append(cur)

    centers = []            # [(x_center, kind, key)]，kind ∈ {'month','agg','other'}
    for g in groups:
        cx = (g[0]['x0'] + g[-1]['x1']) / 2.0
        t = _lab(g)
        if _MONTH_HDR.match(t):
            d = datetime.strptime(t, '%b-%y')
            centers.append((cx, 'month', '%04d-%02d' % (d.year, d.month)))
        elif _QTR_HDR.match(t):
            q, yy = _QTR_HDR.match(t).groups()
            centers.append((cx, 'agg', 'Q%s-20%s' % (q, yy)))
        elif _FY_HDR.match(t):
            centers.append((cx, 'agg', 'FY-20%s' % _FY_HDR.match(t).group(1)))
        elif t == 'Year to Date':
            centers.append((cx, 'agg', 'YTD'))
        else:
            centers.append((cx, 'other', t))    # 认不出的表头：只用来吸走杂散 word

    mcx = [c for c, k, _ in centers if k == 'month']
    if len(mcx) < 6:
        raise MiaxFetchError('%s 表头月份列不足 6 个' % fname)
    spacing = min(mcx[i + 1] - mcx[i] for i in range(len(mcx) - 1))
    # 标签区 / 数值区的分界：第一个月份列中心往左半个列宽。
    # 实测富余量很大（2026 那份标签最右 143.3、数值最左 183.5、分界 161.3）。
    bound = mcx[0] - spacing / 2.0

    months, aggs = {}, {}
    section, sub = None, None
    for r in rows[hdr_i + 1:stop_i]:
        txt = _norm(' '.join(w['text'] for w in r))
        if txt in _SECTION_TITLES:
            section, sub = _SECTION_TITLES[txt], None
            continue
        if txt in _SUB_TITLES:
            sub = _SUB_TITLES[txt]
            continue
        if section is None:
            continue
        lab_ws = [w for w in r if w['x1'] <= bound]
        val_ws = [w for w in r if w['x0'] >= bound]
        straddle = [w['text'] for w in r if w['x0'] < bound < w['x1']]
        if straddle:
            raise MiaxFetchError(
                '%s 有 word 横跨标签/数值分界线 %.1f：%s —— 版式变了，拒绝猜'
                % (fname, bound, straddle))
        if not lab_ws:
            continue
        label = _lab(lab_ws)

        buckets = {}
        for w in val_ws:
            cx = (w['x0'] + w['x1']) / 2.0
            ci = min(range(len(centers)), key=lambda i: abs(centers[i][0] - cx))
            _c, kind, key = centers[ci]
            if kind == 'month' and abs(_c - cx) > _BUCKET_TOL * spacing:
                raise MiaxFetchError(
                    '%s 行 %r 的 word %r 距最近月份列 %s 有 %.1fpt（列间距 %.1f），'
                    '超过 %.0f%% —— 分桶可能已经错位，拒绝写入'
                    % (fname, label, w['text'], key, abs(_c - cx), spacing,
                       _BUCKET_TOL * 100))
            buckets.setdefault(ci, []).append(w)

        key = (section, sub, label)
        mrow, arow = {}, {}
        for i, (_c, kind, ckey) in enumerate(centers):
            if kind == 'other':
                continue
            txt_i = ''.join(w['text'] for w in sorted(buckets.get(i, []),
                                                      key=lambda x: x['x0']))
            v = _num(txt_i, '%s %s 列 %s' % (fname, key, ckey))
            (mrow if kind == 'month' else arow)[ckey] = v
        months.setdefault(key, mrow)
        aggs.setdefault(key, arow)
    return title, updated, months, aggs


def _pdf_cell(table, section, sub, label):
    """按 (section, sub, label) 取一行；agricultural 查不到时回落到「无子标题」。

    2025 那份 PDF 的 Futures 段只有一行 MIH - ADV (contracts)，没有
    Agricultural: / Financial: 子标题（当时只有农产品）；2026 那份才分段。
    回落只对 agricultural 开口子 —— financial 在 2025 那份里是**真的没有这项业务**，
    悄悄回落到无子标题那行会把农产品的数字写进金融期货列。
    """
    if (section, sub, label) in table:
        return table[(section, sub, label)]
    if sub == 'agricultural' and (section, None, label) in table:
        return table[(section, None, label)]
    return None


def _assemble(months_tbl, fname, has_month_ge_fin_start):
    """把行表转成 {'YYYY-MM': {csv列名: float|None}}。缺行一律抛异常。"""
    missing = []
    for col, sec, sub, lab in PDF_SPEC:
        if _pdf_cell(months_tbl, sec, sub, lab) is None:
            # 金融期货 2026-05 才上线，之前的 PDF 里根本没有 Financial: 那一段。
            # 但只要这份 PDF 覆盖到了 2026-05 及以后，那两行就必须在。
            if col in _PDF_FIN and not has_month_ge_fin_start:
                continue
            missing.append((col, sec, sub, lab))
    if missing:
        raise MiaxFetchError('%s 缺行标签，官方表结构可能已变：%s' % (fname, missing))

    all_months = set()
    for col, sec, sub, lab in PDF_SPEC:
        row = _pdf_cell(months_tbl, sec, sub, lab)
        if row:
            all_months |= set(row)

    out = {}
    for mon in sorted(all_months):
        rec = {}
        for col, sec, sub, lab in PDF_SPEC:
            row = _pdf_cell(months_tbl, sec, sub, lab)
            rec[col] = row.get(mon) if row else None
        if all(v is None for v in rec.values()):
            continue                       # 未来月份的占位列
        out[mon] = rec
    return out


_AGG_SPAN_COLS = [
    # (被检列, 加权用的交易日列)。份额与 RPC 不参与：季度份额不是月度份额的交易日加权，
    # 而 'Year to Date' 那一列 ADV 算到 7 月、RPC 只算到 6 月（PDF 脚注 5），跨度都不同。
    ('industry_adv_options_kcontracts',  'trading_days_options'),
    ('adv_multilist_options_kcontracts', 'trading_days_options'),
    ('industry_adv_equities_mnshares',   'trading_days_options'),
    ('adv_equities_mnshares',            'trading_days_options'),
    ('adv_futures_ag_contracts',         'trading_days_futures'),
]


def _closure_check(data, months_tbl, aggs_tbl, fname):
    """用季度 / 年度列反查月度列 —— 抓 x 分桶整体错位的唯一有效手段。

    为什么需要它：口径坑 1 的分桶法能防住「数字被拆成两个 word」，但防不住
    **整列平移**（所有行一起右移一格，Jan 的值被写进 Feb）。平移之后每一行内部仍然
    自洽，share = adv/industry 照样对得上，肉眼和单行校验都看不出来。
    但季度列不会跟着平移 —— Q1'26 的行业 ADV 必须等于 Jan/Feb/Mar 三个月按交易日的加权平均。
    实测：(63025×20 + 63264×19 + 61770×22) / 61 = 62646.8 → 官方 62,647，闭合。

    交易日用**求和**校验（Q1'26 = 20+19+22 = 61，整数全等）；
    ADV 用交易日加权平均校验，容差 1.5 —— 月度值与季度值都是四舍五入到整数发布的，
    加权后的舍入误差上界略大于 1，取 1.5 留一点余量而不至于放过真正的错位
    （错位一格的偏差通常在数百到数千）。
    """
    def span(agg_key, newest):
        if agg_key == 'YTD':
            y = int(newest[:4])
            return ['%04d-%02d' % (y, m) for m in range(1, int(newest[5:]) + 1)]
        kind, year = agg_key.split('-')
        y = int(year)
        if kind == 'FY':
            return ['%04d-%02d' % (y, m) for m in range(1, 13)]
        q = int(kind[1])
        return ['%04d-%02d' % (y, m) for m in range((q - 1) * 3 + 1, q * 3 + 1)]

    real = sorted(m for m, r in data.items()
                  if r['adv_multilist_options_kcontracts'] is not None)
    if not real:
        return
    newest = real[-1]
    checked = 0

    for col, dcol in [('trading_days_options', None), ('trading_days_futures', None)] + \
                     _AGG_SPAN_COLS:
        spec = next(s for s in PDF_SPEC if s[0] == col)
        agg_row = _pdf_cell(aggs_tbl, spec[1], spec[2], spec[3])
        if agg_row is None:
            continue
        for agg_key, agg_val in sorted(agg_row.items()):
            if agg_val is None:
                continue
            mons = span(agg_key, newest)
            if any(m not in data or data[m][col] is None for m in mons):
                continue
            if dcol is None:                       # 交易日：求和，必须整数全等
                got = sum(data[m][col] for m in mons)
                if abs(got - agg_val) > 1e-9:
                    raise MiaxFetchError(
                        '%s 闭合检验失败：%s 的 %s = %s，但月度求和 = %s（%s）'
                        % (fname, col, agg_key, agg_val, got, mons))
            else:
                if any(m not in data or data[m][dcol] is None for m in mons):
                    continue
                dsum = sum(data[m][dcol] for m in mons)
                if dsum <= 0:
                    continue
                got = sum(data[m][col] * data[m][dcol] for m in mons) / dsum
                if abs(got - agg_val) > 1.5:
                    raise MiaxFetchError(
                        '%s 闭合检验失败：%s 的 %s = %s，但按 %s 加权的月度值 = %.3f'
                        '（%s）—— x 分桶可能整体错位' % (fname, col, agg_key, agg_val,
                                                       dcol, got, mons))
            checked += 1
    if checked == 0 and len(real) >= 2:
        # 只在有 ≥2 个有数月时才要求「至少跑成一条」：年初那份只填了一个月、
        # 且版式恰好没有 Year to Date 列时，季度/年度列一个都凑不齐，那不是版式变了。
        raise MiaxFetchError(
            '%s 一条季度/年度闭合检验都没跑成 —— 表里应有 Q1/Q2/FY/Year to Date 列，'
            '一条都对不上说明版式已变' % fname)


def _share_check(data, fname):
    """MIH ADV ÷ Industry ADV 应约等于官方自报份额 —— 抓「查错 section」的独立一网。

    与闭合检验互补：闭合检验管的是列（月份）方向，这条管的是行（section）方向。
    官方份额只给 1 位小数，加上 ADV 本身也是整数四舍五入，实测偏差最大 0.05pp，
    容差取 0.15pp：真错行时（比如把 Futures 的数字读进 Options 段）偏差是几个百分点级别。
    """
    for mon, rec in sorted(data.items()):
        for adv, ind, sh in (('adv_multilist_options_kcontracts',
                              'industry_adv_options_kcontracts',
                              'share_multilist_options_pct'),
                             ('adv_equities_mnshares',
                              'industry_adv_equities_mnshares',
                              'share_equities_pct')):
            a, i, s = rec[adv], rec[ind], rec[sh]
            if a is None or i is None or s is None or i <= 0:
                continue
            if abs(a / i * 100.0 - s) > 0.15:
                raise MiaxFetchError(
                    '%s %s 份额自洽检验失败：%s/%s = %.3f%%，官方自报 %.1f%% —— '
                    '多半是查错了 section' % (fname, mon, a, i, a / i * 100.0, s))


def parse_pdf(path):
    """解析一份官方 PDF，返回 (data, updated_on 'YYYY-MM-DD'|None, updated_on 原文|None)。

    data = {'YYYY-MM': {csv列名: float|None}}（按月升序，只含有数的月）。
    任何一个约定的行标签找不到、任何一格解析不出数字、任何一条闭合检验不过 —— 一律抛异常。
    宁可整月不更新，也不要写出一列悄悄错位的 CSV。
    """
    import pdfplumber                              # 延迟 import：报错更好定位

    fname = os.path.basename(path)
    try:
        pdf = pdfplumber.open(path)
    except Exception as e:                          # noqa: BLE001
        # 缓存里躺着一份被截断/被换成 404 页面的文件时，pdfminer 抛的是它自己的异常类型。
        # 统一翻译成本模块的异常，调用方（monthly_run 逐家隔离）才有一致的判据。
        raise MiaxFetchError('%s 打不开，不是有效 PDF：%r' % (fname, e)) from e
    try:
        if not pdf.pages:
            raise MiaxFetchError('%s 是空 PDF' % fname)
        title, upd_raw, months_tbl, aggs_tbl = _parse_page(pdf.pages[0], fname)
    finally:
        pdf.close()

    m = _TITLE_YEAR.search(title)
    if not m:
        raise MiaxFetchError('%s 抬头里读不出报告年份：%r' % (fname, title))
    year = m.group(1)

    # 先粗看一遍有没有 2026-05 及以后的月份，用来决定金融期货那两行是不是必须存在
    seen = set()
    for row in months_tbl.values():
        seen |= {k for k, v in row.items() if v is not None}
    data = _assemble(months_tbl, fname, any(k >= FIN_FUTURES_START for k in seen))

    bad_year = [k for k in data if k[:4] != year]
    if bad_year:
        raise MiaxFetchError('%s 抬头写着 %s，却解析出别的年份的月份：%s'
                             % (fname, year, bad_year))
    # data 为空是**合法**的：跨年那几天官网会先把新一年的空模板挂上去（12 列全空）。
    # 这里不抛异常，交给调用方跳过 —— 抛了的话，同一次 update() 里另一份**有数据的**
    # PDF（12 月那个月的数据就在里面）也会被一起拖垮，白白晚一个月上线。
    # 能这么放行的前提是：表头行找到了（≥6 个 Mon-YY）、约定的 14 个行标签一个不少都找到了
    # （_assemble 会抛），只是数值格全空 —— 这种形状只可能是空模板，不可能是解析崩了：
    # 数值 word 是按 x 位置从**行标签所在的同一行**取的，标签在而数值凭空消失没有物理路径。

    _closure_check(data, months_tbl, aggs_tbl, fname)
    _share_check(data, fname)

    upd = None
    if upd_raw:
        for fmt in ('%B %d, %Y', '%b %d, %Y', '%b. %d, %Y'):
            try:
                upd = datetime.strptime(upd_raw, fmt).strftime('%Y-%m-%d')
                break
            except ValueError:
                continue
    return dict(sorted(data.items())), upd, upd_raw


def _validate_pdf(data, fname):
    """返回这份 PDF 里最新的有数月。ADV 必须齐；RPC 只允许在最新月为空（官方滞后一月）。"""
    real = sorted(m for m, r in data.items()
                  if r['adv_multilist_options_kcontracts'] is not None)
    if not real:
        raise MiaxFetchError('%s 里没有任何一个月有 MIH Options ADV' % fname)
    newest = real[-1]
    for mon in real:
        rec = data[mon]
        for col in PDF_COLS:
            if rec[col] is not None:
                continue
            if col in _PDF_FIN and mon < FIN_FUTURES_START:
                continue                       # 金融期货 2026-05 才上线
            if col in _PDF_LAGGED and mon == newest:
                continue                       # RPC/capture 滞后一个月（口径坑 6）
            raise MiaxFetchError(
                '%s %s 缺列 %s —— 解析异常或官方口径变了，拒绝写入' % (fname, mon, col))
    return newest


# ── indsum API ──────────────────────────────────────────────────────────
def _api_json(url, cache_path=None):
    raw, _hdr = _http_get(url, timeout=45)
    if cache_path:
        _write_bytes(cache_path, raw)
    try:
        return json.loads(raw.decode('utf-8', 'replace'))
    except ValueError as e:
        raise MiaxFetchError('%s 返回的不是 JSON：%r' % (url, raw[:120])) from e


def _api_latest_complete_month():
    """官方最新可用交易日所在月的**上一个月** —— 即「已经整月过完」的最后一个月。

    先问 getDate 而不是看本机日历：本机时区、交易所假期、官方回补延迟都可能让
    「上个月」这个判断错一天，而 API 对未来日期是**静默返回当月 MTD**（口径坑 4），
    错一天不会报错，只会悄悄写进去一个半截月。
    """
    d = _api_json(API_BASE + 'getDate?exchType=options')
    s = (d or {}).get('date')
    if not (isinstance(s, str) and len(s) == 8 and s.isdigit()):
        raise MiaxFetchError('getDate 返回体不认识：%r' % (d,))
    y, m = int(s[:4]), int(s[4:6])
    return '%04d-%02d' % (y - 1, 12) if m == 1 else '%04d-%02d' % (y, m - 1)


def _check_span(rows, month, url):
    """校验返回体确实覆盖整个 month。不满足直接炸 —— 见口径坑 4。"""
    y, mo = int(month[:4]), int(month[5:])
    last = calendar.monthrange(y, mo)[1]
    # TOTAL 行的 DATA_START_DATE / DATA_END_DATE **恒为空串**（实测 2015-04 / 2020-12 /
    # 2026-07 三个月都一样），所以只拿交易所行的区间做判据；一条都没有才是真出事。
    spans = {(r.get('DATA_START_DATE'), r.get('DATA_END_DATE')) for r in rows
             if r.get('DATA_START_DATE')}
    if len(spans) != 1:
        raise MiaxFetchError('%s 返回体里的数据区间不唯一：%s' % (url, sorted(spans)))
    s, e = spans.pop()
    try:
        ds = datetime.strptime(s, '%d/%m/%Y')       # DD/MM/YYYY，不是美式
        de = datetime.strptime(e, '%d/%m/%Y')
    except (TypeError, ValueError) as ex:
        raise MiaxFetchError('%s 的数据区间格式不认识：%r → %r' % (url, s, e)) from ex
    ok = (ds.year == y and ds.month == mo and ds.day == 1
          and de.year == y and de.month == mo and last - de.day <= 4)
    if not ok:
        raise MiaxFetchError(
            '%s 要的是 %s 整月，实际返回 %s → %s —— API 对未来/月中日期会静默给 MTD'
            % (url, month, s, e))


def _api_options(month, cache_dir):
    """取某月四所 + 行业的期权 ADV（千张/日）。返回 {csv列名: float|None}。"""
    y, mo = int(month[:4]), int(month[5:])
    day = '%04d%02d%02d' % (y, mo, calendar.monthrange(y, mo)[1])
    url = API_BASE + 'detail?tid=1&exchType=options&date=' + day
    rows = _api_json(url, os.path.join(cache_dir, 'miax_indsum',
                                       'options_%s.json' % day))
    if not rows:
        raise MiaxFetchError('%s 返回空数组 —— %s 应在 %s 之后，历史起点判断错了？'
                             % (url, month, API_OPTIONS_START))
    _check_span(rows, month, url)

    rec = {c: None for c in API_OPT_COLS}
    idx_sum, seen = 0.0, False
    for r in rows:
        name = r.get('EXCHANGE_DESCRIPTION')
        if r.get('EXCHANGE_GROUP') == 'MIAX':
            if name not in API_OPT_EXCH:
                raise MiaxFetchError(
                    '%s 里出现没见过的 MIAX 期权所 %r —— 新开了一家而我们不知道，'
                    '四所合计会从此偏低，拒绝静默跳过' % (url, name))
            rec[API_OPT_EXCH[name]] = float(
                r['EQUITY_OPTION_TOTAL_AVERAGE_VOLUME']) / 1000.0
            idx_sum += float(r['INDEX_OPTION_TOTAL_AVERAGE_VOLUME'])
            seen = True
        elif name == 'TOTAL':
            rec['industry_adv_options_api_kcontracts'] = float(
                r['EQUITY_OPTION_TOTAL_AVERAGE_VOLUME']) / 1000.0
    if not seen:
        raise MiaxFetchError('%s 里一家 EXCHANGE_GROUP=MIAX 的所都没有' % url)
    if rec['industry_adv_options_api_kcontracts'] is None:
        raise MiaxFetchError('%s 里没有 TOTAL 行 —— 行业分母取不到' % url)
    rec['adv_index_options_api_kcontracts'] = idx_sum / 1000.0
    return rec


def _api_equities(month, cache_dir):
    """取某月 MIAX Pearl Equities 的股票 ADV 与日均名义额，外加全市场分母。"""
    y, mo = int(month[:4]), int(month[5:])
    day = '%04d%02d%02d' % (y, mo, calendar.monthrange(y, mo)[1])
    rec = {c: None for c in API_EQ_COLS}
    for sum_type, exch_field, mkt_field, exch_col, mkt_col, scale in (
            ('volume', 'EXCHANGE_AVERAGE_TRADE_VOLUME',
             'TOTAL_MARKET_AVERAGE_TRADE_VOLUME',
             'adv_equities_api_mnshares', 'industry_adv_equities_api_mnshares', 1e6),
            ('notional', 'EXCHANGE_AVERAGE_NOTIONAL_VALUE',
             'TOTAL_MARKET_AVERAGE_NOTIONAL_VALUE',
             'adnv_equities_api_usdbn', 'industry_adnv_equities_api_usdbn', 1e9)):
        url = (API_BASE + 'detail?tid=1&exchType=equities&sumType=%s&date=%s'
               % (sum_type, day))
        rows = _api_json(url, os.path.join(cache_dir, 'miax_indsum',
                                           'equities_%s_%s.json' % (sum_type, day)))
        if not rows:
            raise MiaxFetchError('%s 返回空数组 —— %s 应在 %s 之后'
                                 % (url, month, API_EQUITIES_START))
        _check_span(rows, month, url)

        for r in rows:
            name = r.get('EXCHANGE_DESCRIPTION')
            if r.get('EXCHANGE_GROUP') == 'MIAX':
                if name not in API_EQ_EXCH:
                    raise MiaxFetchError(
                        '%s 里出现没见过的 MIAX 股票所 %r，拒绝静默跳过' % (url, name))
                rec[exch_col] = float(r[exch_field]) / scale
        if rec[exch_col] is None:
            raise MiaxFetchError('%s 里没有 MIAX 的股票所（PEARLEQ）行' % url)

        # 全市场分母只取**交易所行**的 TOTAL_MARKET_*：TOTAL 行自己的同名字段是
        # 按行数重复累加出来的垃圾（实测 331,387,353,008 vs 真值 17,441,439,632），
        # 见口径坑 5。顺手断言各交易所行取值一致 —— 不一致说明这个字段的含义变了。
        vals = {r[mkt_field] for r in rows if r.get('EXCHANGE_DESCRIPTION') != 'TOTAL'
                and r.get(mkt_field) is not None}
        if len(vals) != 1:
            raise MiaxFetchError('%s 各交易所行的 %s 不一致：%s'
                                 % (url, mkt_field, sorted(vals)[:4]))
        rec[mkt_col] = float(vals.pop()) / scale
        time.sleep(_API_DELAY)
    return rec


# ── 发布日 ───────────────────────────────────────────────────────────────
def _source_dates():
    """按路径加载仓库根的 source_dates.py（本模块被 spec_from_file_location 加载，
    那时 sys.path 上既没有 fetch/ 也没有仓库根，不能裸 import）。"""
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(root, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── CSV ─────────────────────────────────────────────────────────────────
def _fmt(v):
    """整数写成整数、其余写最短往返表示。

    官方发布的 ADV / 交易日大多是整数，写成 '63025' 比 '63025.0' 好读，
    而且与 series/cme.csv、series/hkex.csv 的既有风格一致。repr(float) 保证无损往返。
    """
    if v is None:
        return ''
    v = float(v)
    return str(int(v)) if v == int(v) else repr(v)


def _month_range(start, end):
    """['2015-04' … end]，闭区间。end < start 时返回空。"""
    y, m = int(start[:4]), int(start[5:])
    out = []
    while True:
        cur = '%04d-%02d' % (y, m)
        if cur > end:
            return out
        out.append(cur)
        m += 1
        if m == 13:
            y, m = y + 1, 1


def _read_csv(path):
    if not os.path.exists(path):
        raise MiaxFetchError(
            'series/miax.csv 不存在。本模块只追加、不从零建库 —— 请先手工建好表头：\n'
            + ','.join(COLUMNS))
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    if not rows:
        raise MiaxFetchError('series/miax.csv 是空文件')
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        raise MiaxFetchError('series/miax.csv 里没有这些列：%s' % missing)
    return header, body


def _restatement_audit(body, idx, pdf_data):
    """拿本期 PDF 重算库内**全部 14 个 PDF 列**，不一致就告警（不改历史）。

    为什么必须覆盖全部列，而不是只盯 industry_adv_equities_mnshares：
      侦察阶段只 diff 过两份 2025 年的 PDF，结论是「只有这一列变过」。
      复核阶段 diff 了两份 2026 年的 PDF，抓到 rpc_futures_ag_usd 的 2026-04
      从 1.981 被改成 1.977 —— **重述不止一列**。只监控一列 = 其余 13 列的修订永远发现不了。
    本模块「已有值永不覆盖」，所以这里只告警不改；真要刷历史请人工决定。
    """
    have = {r[0]: r for r in body}
    for mon in sorted(pdf_data):
        row = have.get(mon)
        if row is None:
            continue
        for col in PDF_COLS:
            old = row[idx[col]].strip()
            new = _fmt(pdf_data[mon][col])
            if old and new and old != new:
                sys.stderr.write(
                    '[miax] ⚠ %s 的 %s 官方数值与库内不一致（库内 %s → 本期 PDF %s），'
                    '疑似重述；本模块不改历史，请人工确认\n' % (mon, col, old, new))


# ── 对外接口 ─────────────────────────────────────────────────────────────
def latest_month(cache_dir):
    """官方源当前最新月 'YYYY-MM'（以 PDF 的 ADV 口径为准，RPC 比它再滞后一个月）。

    只下列表页与两份 PDF，不打 indsum API —— API 的可用月份从不领先 PDF，
    而 monthly_run 的闸门只需要知道「有没有新的一期报表」。
    抓不到 / 解析不出来一律抛 MiaxFetchError，不返回 None 掩盖故障。
    """
    newest = None
    for _year, path, _lm in _fetch_pdfs(cache_dir):
        data, _upd, _raw = parse_pdf(path)
        if not data:
            continue                       # 新一年的空模板，见 parse_pdf 里的说明
        m = _validate_pdf(data, os.path.basename(path))
        newest = m if newest is None else max(newest, m)
    if newest is None:
        raise MiaxFetchError('列表页上那两份 PDF 都没有任何有数的月份')
    return newest


def update(series_dir, cache_dir):
    """把新月份写进 series/miax.csv，返回新增月份列表（升序）。

    幂等保证：
      · 已存在的月份不重复追加；
      · 已经有值的单元格**永不覆盖**（官方会重述，重述不由本模块自动吞进来，
        只在 _restatement_audit 里告警）；
      · 只对既有行里**原本为空**的格做回补 —— 不做的话，因 RPC 滞后一个月而留白的
        那一格会永久为空，「ADV × RPC」图就没数据了；
      · 未被触碰的单元格是原样字符串搬运，所以「什么都没变」时文件字节级不变。

    两个源分头走：
      PDF —— 每次都把列表页上的**两份都**下下来（口径坑 9：上一年那份会被重发，
             12 月的 RPC 只在重发版里才有）。19 个月，成本固定且很小。
      API —— 只抓库里**哨兵列为空**的月份。首次建库约 270 次请求（2015-04 起 136 个月
             的期权 + 2020-12 起 68 个月的股票 × volume/notional 两条），
             之后每月只有 1-3 次。已入库的月份从不重抓，所以 API 侧没有重述基线，
             重述体检只覆盖 PDF 那 14 列 —— 这是明知的取舍，不是遗漏。
    """
    csv_path = os.path.join(series_dir, 'miax.csv')
    header, body = _read_csv(csv_path)
    idx = {name: i for i, name in enumerate(header)}
    have = {r[0]: r for r in body}

    # ── 1) PDF ────────────────────────────────────────────────────────
    pdf_data, pub = {}, {}
    for _year, path, last_mod in _fetch_pdfs(cache_dir):
        fname = os.path.basename(path)
        data, upd, upd_raw = parse_pdf(path)
        if not data:
            sys.stderr.write('[miax] 提醒：%s 是一张空模板（新一年的文件已挂出、'
                             '数据尚未填），本轮跳过它\n' % fname)
            continue
        newest = _validate_pdf(data, fname)
        for mon, rec in data.items():
            pdf_data.setdefault(mon, rec)
        if upd:
            # evidence 里同时写上 last-modified，但只当**辅助线索**：实测 5 份里 3 份
            # 与 PDF 自述不一致（一律早 1-3 天，文件先上传、通稿后挂），
            # 拿它当权威值会把发布日记早，而记早的日期看上去完全正常。
            pub[newest] = (upd, '%s 第 2 行 "Updated on %s"（权威）；'
                                '辅助线索：HTTP Last-Modified %s'
                                % (fname, upd_raw, last_mod or '（无）'))

    if not pdf_data:
        raise MiaxFetchError('列表页上那两份 PDF 都没有任何有数的月份')

    # 只拿「MIH Options ADV 有值」的月份建行。年初那份文件可能已经把 Jan 的 Trading Days
    # 填上、ADV 还空着 —— 照单入库会造出一行只有交易日的空壳，而下游看不出它是空壳。
    # 判据用 ADV 而不是「整行非空」：ADV 是这份报表的主键指标，它有值这个月才算发布了。
    pdf_real = {m: r for m, r in pdf_data.items()
                if r['adv_multilist_options_kcontracts'] is not None}
    if not pdf_real:
        raise MiaxFetchError('列表页上那两份 PDF 里没有任何一个月有 MIH Options ADV')
    pdf_newest = max(pdf_real)

    # 重述体检拿**全部**解析结果去比（包括非 real 月），因为它只比库里已有的行。
    _restatement_audit(body, idx, pdf_data)

    # ── 2) API：只补哨兵为空的月份 ──────────────────────────────────────
    api_last = _api_latest_complete_month()
    api_data = {}
    for mon in _month_range(API_OPTIONS_START, api_last):
        row = have.get(mon)
        need_opt = row is None or not row[idx[_SENTINEL_OPT]].strip()
        need_eq = (mon >= API_EQUITIES_START
                   and (row is None or not row[idx[_SENTINEL_EQ]].strip()))
        if not (need_opt or need_eq):
            continue
        rec = {}
        if need_opt:
            rec.update(_api_options(mon, cache_dir))
            time.sleep(_API_DELAY)
        if need_eq:
            rec.update(_api_equities(mon, cache_dir))
        api_data[mon] = rec

    # ── 3) 合并落盘：只填空，不覆盖 ─────────────────────────────────────
    added = []
    for mon in sorted(set(pdf_real) | set(api_data)):
        rec = dict(pdf_real.get(mon) or {})
        rec.update(api_data.get(mon) or {})
        if all(v is None for v in rec.values()):
            continue
        row = have.get(mon)
        if row is None:
            row = [''] * len(header)
            row[0] = mon
            have[mon] = row
            body.append(row)
            added.append(mon)
        for col, val in rec.items():
            if val is None:
                continue
            if not row[idx[col]].strip():
                row[idx[col]] = _fmt(val)

    body.sort(key=lambda r: r[0])
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        w.writerows(body)

    # ── 4) 发布日入台账（落盘之后：写盘失败就没有「这个月官方发过了」这条断言）──
    #
    # 只为**整体最新的那一期**作证。上一年那份 PDF 是**重发版**（2025 那份的
    # Updated on 是 2026-05-06），拿它给 2025-12 盖章 = 断言「12 月数据是次年 5 月发的」，
    # 与事实差半年。历史月份的真实发布日要么去翻当时的 PR，要么就让它缺席 ——
    # 缺席远好过印一个像模像样的错日期。
    sd = _source_dates()
    if pdf_newest in pub and pdf_newest in have:
        day, evidence = pub[pdf_newest]
        if not sd.lookup(series_dir, 'miax', pdf_newest):
            sd.record(series_dir, 'miax', pdf_newest, day, evidence)
    return sorted(added)


if __name__ == '__main__':
    _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print('latest:', latest_month(os.path.join(_here, 'cache')))
    print('added :', update(os.path.join(_here, 'series'),
                            os.path.join(_here, 'cache')))
