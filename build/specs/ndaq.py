# -*- coding: utf-8 -*-
"""Nasdaq（NDAQ）单公司页配置。

口径以 docs/verify/verify_ndaq.md（复核稿，判定 B）为准。侦察稿 docs/verify/ndaq.md
的两条已被复核证伪，本文件按复核稿写：
  · E1「五个字段 250 个月零空值」是假的 —— 缺失值是字符串 'n/a' 不是 None，
    复合 matched 口径实际从 **2010-10** 起（NTX 2009-01、PSX 2010-10）。
  · E2「欧洲只比份额不比绝对值」方向反了 —— Nasdaq 的欧洲份额是**北欧+波罗的海**分母，
    与 Cboe 的泛欧份额不是同一个宇宙；可比的是绝对值，不可比的是份额。
    所以本文件里两列一律写明「北欧与波罗的海」，且不给份额列（CSV 里也没有）。

列名全部对着 `head -1 series/ndaq.csv` 逐字核过（14 列，251 个月，2005-09..2026-07）。
注意：侦察稿里的 vol_us_matched_shares_mm / us_trading_days / us_*_shares_bn 等名字
**都不是最终列名**，fetcher 落库时改过；docs/verify/_design.md 里引用的也是旧名。以 CSV 为准。
"""

# ── 本页最要命的一件事：两组数据的发布节奏差一周多 ─────────────────────────
# A 组（IR Monthly Reporting Sheet PDF，4 列）：次月第 6~8 个日历日发布，只有 19 个月，
#     因为那份 PDF 每月**原地替换**同一个 uuid，历史不可回溯（Wayback 本机硬禁）。
# B 组（nasdaqtrader.com marketshare{YY}.xlsx，9 列）：可回溯到 2005-09，
#     但发布晚得多 —— 2026-06 那份的 Last-Modified 是 07-13，而 IR 的 07 月数据 08-05 就发了。
# ⇒ 直觉是「头条取 A 组、B 组进 slow_cols」，但实测行不通：底座要求头条有 ≥24 个月
#   共同历史，A 组只有 19 个月，这一页要等到 2026-12 才发得出来。
#   所以本页反过来 —— **以慢而长的 B 组为脊梁**，A 组当「发布更快的腿」。
#   代价是本页数据月比 Nasdaq IR 官方晚一期（见 headline 处的完整推理）。
#   等 A 组攒够 24 个月（2026-12）应当翻回来，那时 B 组九列才填进 slow_cols。

SPEC = {
    'ticker': 'ndaq',
    'name':   'Nasdaq',
    'title':  '纳斯达克（NDAQ）月度经营指标',
    'csv':    'ndaq.csv',
    'ccy':    'USD',
    'source': 'Source: Nasdaq IR Monthly Reporting Sheet (ir.nasdaq.com) and '
              'nasdaqtrader.com monthly market share files; format after Goldman Sachs GIR',

    # ── 头条为什么不是 A 组：这家的两条腿是「快而短」对「慢而长」，只能二选一。
    # 底座的门槛要求头条列有 ≥24 个月的共同历史（同比与 3Y 分位算不出来就不该发页）。
    # A 组（IR PDF，最新月更快）只有 19 个月 —— 拿它当头条，这一页要等到 2026-12
    # 才够 24 个月，现在根本出不来（实测：底座打印「共同历史只有 19 个月」并退出码 0）。
    # 所以头条取 B 组的份额列：share_us_cash_matched_group 有 189 个月（2010-10 起）、
    # share_us_cash_matched_nasdaq 有 250 个月（2005-09 起），共同历史 189 个月，够。
    # 代价是本页数据月跟着 B 组走（比 IR 晚一期）；A 组因此变成「发布更快的腿」，
    # 在核对表尾部会多出一行、其余列显示「—」，这是底座内建的正常形态。
    # ⇒ slow_cols 因此为空：没有任何一列比头条更晚。
    'headline': [
        {'col': 'share_us_cash_matched_group', 'zh': '美股 matched 市占率（三盘口合计）',
         'unit': '%', 'fmt': 'pct1', 'scale': 100},
        {'col': 'share_us_cash_matched_nasdaq', 'zh': 'The Nasdaq Stock Market 市占率',
         'unit': '%', 'fmt': 'pct1', 'scale': 100},
    ],

    'groups': [
        # ── A 组：IR 月报口径，权威值，但只有 2025-01 起 19 个月。
        {'zh': '美国市场（IR 月报口径，当月总量）', 'cols': [
            {'col': 'vol_us_options_mmcontracts', 'zh': '美股期权成交量（六所合计，含指数期权）',
             'unit': 'mn contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_us_cash_matched_mnsh', 'zh': '美股 matched 成交股数（Nasdaq+NTX+PSX）',
             'unit': 'mn shares/month', 'fmt': 'f0c'},
        ]},

        # ── 北欧与波罗的海：**不是泛欧**。本机用仓内数据实算 2026-06：
        #    本列 Nasdaq = $93.2bn/月，而 Cboe Europe = 14.95 EURbn/日 × 22 个观察日
        #    × EURUSD 1.1518 ≈ $379bn/月 —— Cboe 是 Nasdaq 的 4.1 倍。
        #    Nasdaq 自报的「欧洲份额 74.5%」是北欧/波罗的海本地分母，与 Cboe 的泛欧份额
        #    不是同一个市场。所以只放绝对值，不放份额（CSV 里也没有份额列）。
        {'zh': '北欧与波罗的海市场（Nordic + Baltic 口径，当月总量）', 'cols': [
            {'col': 'vol_nordic_cash_value_usdbn', 'zh': '北欧+波罗的海现货成交额',
             'unit': 'USD bn/month', 'fmt': 'f1'},
            {'col': 'vol_nordic_derivs_mmcontracts', 'zh': '北欧+波罗的海期权与期货成交量',
             'unit': 'mn contracts/month', 'fmt': 'f1'},
        ]},

        # ── B 组份额：本页历史最长的一组，也是这家真正的看点。
        #    合成口径 2010-10 起（PSX 是最后一个凑齐的盘口）；
        #    单盘口 Nasdaq 一列可回到 2005-09，NTX 回到 2009-01。
        #    这四列在 CSV 里是**分数**（0.1477 = 14.77%），所以一律 scale=100 + pct1。
        #    本机用算术验过：share ÷（matched ÷ consolidated）中位比值 = 1.000。
        {'zh': '美股 matched 市占率（nasdaqtrader 口径，本页脊梁）', 'cols': [
            {'col': 'share_us_cash_matched_group', 'zh': '三盘口合计（2010-10 起）',
             'unit': '%', 'fmt': 'pct1', 'scale': 100},
            {'col': 'share_us_cash_matched_nasdaq', 'zh': 'The Nasdaq Stock Market（2005-09 起）',
             'unit': '%', 'fmt': 'pct1', 'scale': 100},
            # NTX / PSX 是尾部盘口（历史最大 4.52% / 1.43%）。这两条用 f2 而不是 pct2：
            # 底座的比率量纲体检对 pct* 列要求「缩放后最大值 > 1.5」，PSX 缩放后最大只有
            # 1.428（那是它真实的份额上限，不是没缩放），配 pct2 会被硬失败挡下。
            # 换 f2 后数值仍是百分数刻度（scale=100），单位由 unit 写明，读数不变。
            {'col': 'share_us_cash_matched_ntx', 'zh': 'Nasdaq NTX（原 BX，2009-01 起）',
             'unit': '%', 'fmt': 'f2', 'scale': 100},
            {'col': 'share_us_cash_matched_psx', 'zh': 'Nasdaq PSX（2010-10 起）',
             'unit': '%', 'fmt': 'f2', 'scale': 100},
        ]},

        # ── B 组的四列绝对量（vol_us_cash_*_sh）**故意不上页**。
        #    它们的单位是裸股数/月，量级 1e11（2026-06 全美 consolidated = 491,030,721,182），
        #    唯一能读的显示方式是 ×1e-9 换成「十亿股/月」；
        #    但底座给 scale 列生成的表注文案写死成「源表是 0–1 的小数比率，本页统一按百分数显示」
        #    （build/single.py:1143），对非比率列会在页面上印出一句假话。
        #    ⇒ 信息没有丢：上面四条份额列就是这四列除出来的，且历史一样长。
        #      等底座把那句表注一般化之后，这四列可以一行一条加回来（scale: 1e-9）。

        # ── 交易日：把 A 组的「当月总量」换成 ADV 的唯一钥匙，但它在 B 组里，
        #    比 A 组晚一期 —— 所以 A 组最新那一期**换不出 ADV**，要等交易日跟上。
        {'zh': '美股交易日（换算 ADV 用）', 'cols': [
            {'col': 'trading_days_us_equities', 'zh': '当月交易日数',
             'unit': 'days/month', 'fmt': 'f0'},
        ]},
    ],

    # 空：头条已经是发布最慢的那条腿（B 组 nasdaqtrader），没有任何一列比它更晚。
    # A 组四列反过来比头条**早**一期 —— 那不是慢腿，是快腿，底座会让它们在核对表
    # 尾部多出一行、其余列显示「—」。若将来 IR 那份 PDF 攒够 24 个月历史，
    # 应把头条换回 A 组，届时这里要填上 B 组的五列。
    'slow_cols': [],

    # 无口径断点。复核实测：2025-12 定格的 marketshare25.xlsx 与 2026-06 版的
    # marketshare26.xlsx 在 244 个重叠月 × 5 字段上逐格比对，不一致数 = 0 ——
    # Nasdaq 不重述美股月度成交量。NTX 只是 BX 的改名，不是换盘口。
    # 各列不同的起点（2005-09 / 2009-01 / 2010-10 / 2025-01）是序列起点不是断点，
    # 写成断点会在 187 个月的图上画出四条与口径无关的红线。
    'breaks': [],

    'notes': [
        '本页有两个数据源、两种发布节奏。<b>A 组</b>（美国期权、美股 matched、北欧两列）来自 Nasdaq IR 的 '
        'Monthly Reporting Sheet PDF，次月第 6~8 个日历日发布，是官方权威值；'
        '<b>B 组</b>（成交股数、份额、交易日）来自 nasdaqtrader.com 的月度市占率 xlsx，'
        '历史深但发布晚一周多（2026-06 那份的 Last-Modified 是 2026-07-13，而 IR 的 07 月数据 08-05 就发了）。'
        '<b>本页以 B 组为脊梁</b> —— 只有它够 24 个月历史、过得了发布门槛，'
        '因此页面数据月比 Nasdaq IR 官方晚一期；A 组反而是「发布更快的腿」，'
        '在末尾核对表里会多出一行、其余列显示「—」。这是刻意的取舍，不是抓取失败。',

        '<b>A 组只有 2025-01 起 19 个月，且不可回补。</b>那份 PDF 每月原地替换同一个 static-file uuid，'
        'IR 站不保留历史版本（老路径 302 回同一个 uuid，?year= 参数无效，2016/2019 的新闻稿正文里一个数字都没有）。'
        '⇒ 2026-12 之前这四列做不了同比。',

        '<b>A 组给的是「当月总量」不是日均。</b>官方 PDF 段落标题原文是 '
        '"U.S. equity options volume (millions of contracts)" / "U.S. matched equity volume (millions of shares)"，'
        '没有 average daily 字样。要与 CME / Cboe 的 ADV 比必须先除交易日 —— '
        '而交易日在 B 组、比 A 组晚一期，所以 A 组最新那一期换不出 ADV。'
        '换算后量级已验证合理：2026-06 美股 3.455bn 股/日（Cboe 2.185）、期权 20,381k 张/日（Cboe 22,977）。',

        '<b>vol_us_options_mmcontracts 含指数期权</b>（PDF 脚注 1 的 capture 口径明说含）。'
        '跨家对比时对应的是 Cboe 的 adv_us_options_kcontracts（总数），'
        '<b>不是</b> adv_multilist_options_kcontracts（不含指数）—— 拿 multilist 去比是苹果比橘子。',

        '<b>北欧两列是「北欧 + 波罗的海」口径，不是泛欧 —— 这是本页最容易画出误导图的一处。</b>'
        'Nasdaq 季报自报的欧洲现货市占率约 74.5%，那是北欧/波罗的海本地市场的份额；'
        'Cboe Europe 报的是泛欧份额（约 20–25%）。两者分母不是同一个市场，叠在一张图上会让读者以为 '
        'Nasdaq 是 Cboe 的三倍强。本机用仓内数据实算（Cboe adv_eu_equities_adnv_eurbn × series/fx.csv 的 '
        'obs_days 与 fx_avg_eurusd）：2026-06 Cboe Europe 约 $379bn/月，本列 Nasdaq 为 $93.2bn/月，'
        '<b>Cboe 是 Nasdaq 的 4.1 倍</b>（2026-05 为 3.6 倍、2026-07 为 4.2 倍）。'
        '⇒ <b>欧洲份额禁止跨家对比；可比的只有绝对值</b>，且量级关系与份额给人的印象正好相反。'
        '本页因此只放绝对额，不放欧洲份额（CSV 里也没有这一列）。',

        '<b>美股 matched 的合成口径从 2010-10 起，不是 2005-09。</b>三个盘口凑齐的时间不同：'
        'The Nasdaq Stock Market 2005-09、Nasdaq NTX（2026 年起的名字，之前叫 BX）2009-01、PSX 2010-10。'
        '更早的行在官方 xlsx 里是字符串 "n/a" 而不是空格，只判 None 会在求和时抛 TypeError。',

        '<b>share_us_cash_matched_* 四列在官方原表里是 0–1 的小数比率</b>（0.1477 = 14.77%），'
        '本页统一乘 100 按百分数显示。这一点用算术核过而不是照抄文档：'
        'share ÷（matched 股数 ÷ consolidated 股数）的中位比值 = 1.000。'
        '注意 series/miax.csv 的 share_*_pct 存的是百分数，两家形态相反。',

        '官方文件里还有四列绝对成交股数（全美 consolidated 与三个盘口的 matched，2005-09 起 250 个月），'
        '<b>本页故意不放</b>：它们的单位是裸股数/月、量级 1e11（2026-06 全美 consolidated = '
        '491,030,721,182 股），按裸数显示读不动。信息没有丢 —— 上面四条份额线正是这四列除出来的，'
        '历史一样长。另外同一个行业分母在 ICE 页上有可读形态（三个 tape 的 consolidated ADV，'
        '百万股/日，2011-01 起）。',

        '<b>Nasdaq 不重述美股月度成交量。</b>2025-12 定格版与 2026-06 版在 244 个重叠月 × 5 字段上'
        '逐格比对，不一致数 = 0。（例外在季度面板的 revenue capture 四列，那四列当期是估计值会被改，'
        '但不在本 CSV 里。）',

        '本 CSV 不含 IR PDF 第 2 页的季度面板（期权/现货 capture、ETP AUM、上市家数、'
        '跟踪 Nasdaq 指数的股指期货量等 21 行）。其中 q_index_futures 是**别家撮合、Nasdaq 只收授权费**的量，'
        '与 CME 的股指合约有重合，两家分别记账，任何情况下都不能同柱比「谁成交大」。',
    ],
}
