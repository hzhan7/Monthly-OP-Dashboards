# -*- coding: utf-8 -*-
"""SGX（新加坡交易所）单公司页配置。

━━ 这份文件的全部职责 ━━
声明「series/sgx.csv 的哪些列上页面」。不算数、不画图、不碰公共代码。
整份文件可以直接删掉，别的页一行都不受影响。

━━ 本页的看点：SGX 卖的是「别人家的标的」━━
SGX 衍生品的头部产品全部是**离岸挂牌的他国标的**，与 JPX / HKEX 是同标的头对头：

    2026-06 实测（占当月 SGX 衍生品总成交 34,315,225 张的比重）
      FTSE 中国 A50 期货    11,724,378 张   34.2%   ← 与 HKEX 的 A 股衍生品同赛道
      外汇期货合计          10,268,040 张   29.9%   （USD/CNH + INR/USD 为主）
      铁矿石衍生品           5,354,979 张   15.6%
      日経225 期货              748,048 张    2.2%   ← 与 JPX 的旗舰合约同标的

所以 A50 与日経225 两条线在本页必须单列、不许并进「股指期货合计」里看不见 ——
它们是判断 SGX 竞争位置的直接读数。

━━ 为什么按「共同起点」分组 ━━
本页四档起点：2015-01（主体）、2018-03（换手率）、2020-07（FTSE 台湾）、2025-11（加密）。
同组混起点会逼底座二选一：砍成最短窗口，或给平滑类图型喂 null
（gs_line 会 null.toFixed() 抛 TypeError，整张卡片之后的 exhibit 全不渲染，
见 docs/CHART_KINDS.md §1.2）。所以起点不同的列一律各成一组。

━━ 量价分解的口径核查（2026-08-07，结论：✅ 同口径，可分解）━━
恒等式 `成交额 ≡ 成交股数 × 加权平均成交价`，均价 = sec_turnover_sgdmn ÷ sec_turnover_mnshares。
这是定义式，没有假设、没有误差；**唯一要证的是分子分母同口径**。四条证据：

1. **同表同段相邻两行**。两列都出自月报 p2 的 SGX Statistics At A Glance，
   实测 2026-06 与 2015-01 两期的行序完全一样：
   `Turnover Volume (Million Shares)` 在第 7 行、`Turnover Value ($Million)` 在第 10 行
   （中间夹的是各自的上月/本月两个数）。两行都**没有脚注记号**，官方没有给它们不同的覆盖口径。
2. **改名逐代同步**。把 138 期 PDF 的这两行标签全扫一遍，共 9 个世代
   （大小写反复横跳 + 2025-12 起 `Securities Market` → `Stock Market`），
   **每一代都是两行一起改**，没有任何一期出现「一行改了另一行没改」——
   覆盖范围若变过，只会同时作用于分子与分母，比值不受污染。
3. **粒度一致，且金额那一行可反算验证**。两列都是**当月总量**（不是日均）。
   金额列满足 `sec_turnover_sgdmn / sec_trading_days = sdav_sgdmn`，
   全 138 个月最大相对误差 0.051%（= SDAV 取整到 S$mn 的舍入）。
   ⚠ 对照组：衍生品那一侧这个恒等式**不成立**（见下方 notes 第 3 条），所以证券侧成立是有信息量的。
4. **12 个月滚动块可与官方 FYTD 对账**。用月度序列自己滚 FY2026（Jul-25–Jun-26）
   得 455,679 S$mn，官方报告 p3 的 FYTD = 455,677、新闻稿写 "S$455.7 billion" ——
   差 2（12 个整数月度值的舍入），相对差 0.0004%。衍生品 FYTD 更是逐位相同
   （363,489,920）。说明月度序列完整无缺、可安全聚合成年度块。

**均价序列有没有口径跳变？没有。** 逐月对数变动只有 2016-03 一个月 |z|>3（-44.7%），
而那一个月是**分母在动**（成交股数 22,750 → 46,539 百万股翻倍，金额只涨 13%），
是仙股放量、不是口径换代；把跳变前后各 6 个月的几何均价一比，前五大跳变全部回归、不留台阶。
唯一留下台阶的是 2024-05 之后（前 6 月均价 0.749 → 后 6 月 1.011），
但那不是某一个月的断点，而是 2024-2026 大盘股行情驱动的**连续 12 个月的爬升**
（12 个月滚动中位数 0.75 → 0.94 → 1.08 逐级抬升，不是一次跃迁），
且与 2025-12 的官方改名相差 19 个月，时间对不上。

⚠ **「价」是什么、不是什么**：这里的均价 = 成交额 ÷ 成交股数 = **成交量加权平均成交价**，
它同时含（a）市场涨跌与（b）成交结构变化（仙股 vs 大盘股的成交占比此消彼长）。
本仓没有 STI 点位序列，**分不开 a 与 b**，所以任何图注都不许把它说成指数收益率。
（对照：TMX 的 series 里有 `tsx_composite_close`，那一家才拆得开。）

━━ 有意不上页面的列，以及理由 ━━
· sec_trading_days —— 分母。而且它是**证券市场**的交易日数，
  拿去除衍生品月量得不到 DDAV（实测 2026-06 反推 21.19 天、官方写 21），
  上页面只会诱导别人做错误的除法。
· deriv_swaps_vol_contracts —— 掉期，2026-06 = 7,662 张，占总量 0.02%，
  与期货同框会被压成一条贴地线。
· vol_msci_taiwan_futures_contracts —— **已停发的死列**：2021-11 之后无值，
  2021-01 还有一个内部空洞，2021-02 起全是 0。既不能进平滑图型，
  留在页面上也只是一条归零线。台湾敞口改看 FTSE 那条（2020-07 起）。
"""

import csv
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CSV = os.path.join(_ROOT, 'series', 'sgx.csv')


# ── 断点能读 CSV 就读 ──────────────────────────────────────────────────
# 内联而不抽公共函数：本页要能整份删掉不留残渣。这个函数只做
# 「列 → 第一个有值的月份」的字典查询，不含统计口径。
# 读不到就返回 None —— 缺文件不许在 import 期抛异常。
def _first_present(col):
    try:
        with open(_CSV, encoding='utf-8') as fh:
            for r in csv.DictReader(fh):
                if col in r and r[col].strip():
                    return r['month']
    except OSError:
        pass
    return None


def _breaks():
    out = []
    # 台指授权换手：MSCI Taiwan 合约到期不再续约，SGX 改挂 FTSE Taiwan。
    # 从 CSV 读 FTSE 那条的首月（实测 2020-07），不写死。
    m = _first_present('vol_ftse_taiwan_futures_contracts')
    if m:
        out.append({'month': m, 'zh': '台指授权由 MSCI 换为 FTSE，两条序列不可直连'})
    # GIFT Nifty：2023-07 GIFT Connect 迁移，同时改了计数口径。
    # 这一条**只能写死** —— CSV 里没有任何标记列能指出它，
    # 依据是官方报告脚注「For periods prior to June 2023, volumes are computed
    # based on higher of buy and sell lots」（见 docs/verify/sgx.md 口径坑 3）。
    out.append({'month': '2023-07',
                'zh': 'GIFT Connect 迁移，Nifty 计数由「买卖孰高」改为双边合计'})
    # 底座画红虚线时按索引取月份，乱序会让标签配错断点 —— 统一按月份排。
    return sorted(out, key=lambda b: b['month'])


SPEC = {
    'ticker': 'sgx',
    'name': 'Singapore Exchange',
    'title': '新加坡交易所（SGX）月度经营指标',
    'csv': 'sgx.csv',
    'ccy': 'SGD',
    'source': ('Source: SGX Monthly Statistics Report (official PDF, via SGX CMS API); '
               'format after Goldman Sachs GIR'),

    # 头条：证券与衍生品各一条。两者同出一份 PDF、同一天发布，
    # 2015-01 起逐月无洞（实测 138/138）。
    # SDAV 是 SGX 自家财报与新闻稿引用最多的单一数字；DDAV 是跨所可比的那条。
    'headline': [
        {'col': 'sdav_sgdmn', 'zh': '证券市场 SDAV',
         'unit': 'S$mn/day', 'fmt': 'f0c'},
        {'col': 'ddav_contracts', 'zh': '衍生品 DDAV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
    ],

    'groups': [
        {'zh': '证券市场成交', 'cols': [
            {'col': 'sdav_sgdmn', 'zh': '日均成交额 SDAV',
             'unit': 'S$mn/day', 'fmt': 'f0c'},
            {'col': 'sec_turnover_sgdmn', 'zh': '当月成交额',
             'unit': 'S$mn/month', 'fmt': 'f0c'},
            {'col': 'sec_turnover_mnshares', 'zh': '当月成交股数',
             'unit': 'mn shares/month', 'fmt': 'f0c'},
        ]},

        {'zh': '市值与上市证券数', 'cols': [
            {'col': 'mktcap_sgdmn', 'zh': '月末总市值',
             'unit': 'S$mn', 'fmt': 'f0c', 'stock': True},
            {'col': 'listed_securities', 'zh': '月末上市证券只数',
             'unit': 'listings', 'fmt': 'f0', 'stock': True},
        ]},

        # 2018-03 才有，单独一组（起点与主体差 38 个月）。
        {'zh': '换手率（2018-03 起）', 'cols': [
            {'col': 'turnover_velocity_pct', 'zh': '整体换手率',
             'unit': '%', 'fmt': 'pct0'},
        ]},

        {'zh': '衍生品成交与未平仓', 'cols': [
            {'col': 'ddav_contracts', 'zh': '日均成交 DDAV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'deriv_vol_contracts', 'zh': '当月成交合计',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'deriv_futures_vol_contracts', 'zh': '其中：期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'deriv_options_vol_contracts', 'zh': '其中：期权',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'deriv_oi_contracts', 'zh': '月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        ]},

        # 头对头的两个产品必须在这里被看见（见文件抬头）。
        {'zh': '股指期货：与 HKEX / JPX 的头对头', 'cols': [
            {'col': 'vol_equity_index_futures_contracts', 'zh': '股指期货合计',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_a50_futures_contracts', 'zh': 'FTSE 中国 A50 期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_nikkei225_futures_contracts', 'zh': '日経225 期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_msci_singapore_futures_contracts', 'zh': 'MSCI 新加坡期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        # GIFT Nifty 有 2023-07 的计数口径断点，单列一组便于配断点线。
        {'zh': 'GIFT Nifty 50 期货（2023-07 计数口径断点）', 'cols': [
            {'col': 'vol_nifty50_futures_contracts', 'zh': 'GIFT Nifty 50 期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        # 2020-07 起（起点与主体差 66 个月），单独一组。
        {'zh': 'FTSE 台湾指数期货（2020-07 起）', 'cols': [
            {'col': 'vol_ftse_taiwan_futures_contracts', 'zh': 'FTSE 台湾期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        {'zh': '外汇期货', 'cols': [
            {'col': 'vol_fx_futures_contracts', 'zh': '外汇期货合计',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_usdcnh_futures_contracts', 'zh': 'USD/CNH 期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_inrusd_futures_contracts', 'zh': 'INR/USD 期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        {'zh': '商品与利率', 'cols': [
            {'col': 'vol_commodities_contracts', 'zh': '商品合计（不含加密）',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_iron_ore_contracts', 'zh': '其中：铁矿石',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_rates_futures_contracts', 'zh': '利率期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        # 2025-11 才上线，单独一组。
        {'zh': '加密货币永续期货（2025-11 起）', 'cols': [
            {'col': 'vol_crypto_contracts', 'zh': 'BTC / ETH 永续期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        {'zh': '发行与上市', 'cols': [
            {'col': 'ipos_count', 'zh': '当月新上市家数',
             'unit': 'companies', 'fmt': 'f0'},
            {'col': 'delistings_count', 'zh': '当月退市家数',
             'unit': 'companies', 'fmt': 'f0'},
            {'col': 'ipo_funds_sgdmn', 'zh': 'IPO / RTO 募资额',
             'unit': 'S$mn', 'fmt': 'f0c'},
            {'col': 'new_bond_listings', 'zh': '当月新债券挂牌数',
             'unit': 'listings', 'fmt': 'f0'},
            {'col': 'bond_funds_sgdmn', 'zh': '债券募资额',
             'unit': 'S$mn', 'fmt': 'f0c'},
        ]},
    ],

    # 本页所有列出自同一份月报 PDF，同一天发布 —— 没有慢腿。
    'slow_cols': [],

    'breaks': _breaks(),

    # ── 量价分解：成交额 ≡ 成交股数 × 加权平均成交价 ──────────────────────
    # SGX 是 build/specs/ 八家里**唯一**有真正「金额 × 股数」同口径对的一家
    # （TMX / MIAX 也有，但那两家不归本文件；ASX / ENX 只有「笔数 × 每笔均值」，
    #  派生量得走 kind='per_trade'；NDAQ / DB1 / ICE 压根没有可配对的列）。
    # 口径核查见文件抬头「量价分解的口径核查」一节 —— 那四条证据是这张图成立的全部前提。
    'decomp': [{
        'zh': '证券市场成交额',
        # 派生量是**成交量加权平均成交价**，不是每笔均额、也不是费率。
        # 底座据 kind 生成「它不是什么」那段话，spec 不许自己改措辞。
        'kind': 'share_price',
        # 两列本身就是当月合计（月报 p2 At-A-Glance 的相邻两行），不是日均。
        # ⇒ 不给 weight_col：声明 monthly_total 又给 weight_col 是硬失败，
        #   而且真乘上去会把年度合计放大二十几倍，图形却照常画得出来。
        'granularity': 'monthly_total',
        'value': {'col': 'sec_turnover_sgdmn', 'zh': '当月成交额',
                  'unit': 'S$mn/month', 'fmt': 'f0c'},
        'qty': {'col': 'sec_turnover_mnshares', 'zh': '当月成交股数',
                'unit': 'mn shares/month', 'fmt': 'f0c'},
        # 价 = 金额 ÷ 数量，由底座算。**不许另找一列冒充价** —— series/sgx.csv 里
        # 没有任何一列是成交价，turnover_velocity_pct 是换手率、不是价。
        # S$百万 ÷ 百万股 = S$/股，两边的 1e6 自己抵掉 ⇒ price_scale 用缺省 1.0。
        'price_zh': '加权平均成交价',
        'price_unit': 'S$/share',
        'price_fmt': 'f3',          # 实测区间 0.44–1.49，f2 在低位只剩两位有效数字
        # SGX 财年就是 Jul–Jun，且末月 Jun-26 恰好是财年收官月：
        # FY2026 是完整年，还能与官方报告 p3 的 FYTD 逐位对账。
        # 用日历年会丢掉 2026 上半年，而「价的贡献塌下去、量接棒」正好发生在那半年。
        'year_start_month': 7,
        # ⚠ 'end' 不是笔误也不是缺省值能糊过去的：SGX 管 2025-07…2026-06 这一年叫
        # FY2026（按**结束**年命名），JPX 按起始年。写错会让整排标签集体偏一年，
        # 而图形完全正常、没有任何自动判据抓得到。
        'year_label': 'end',
        # 11 个完整财年（FY2016…FY2026）⇒ 10 根柱。序列起点 2015-01，
        # 2014-07…2015-06 那一桶只有 6 个月，底座会自己丢掉。
        'years': 10,
    }],

    # ── 量本身：水平值 + 12 个月滚动同比 ──────────────────────────────────
    'ttm_yoy': [{
        'zh': '证券市场成交股数',
        'granularity': 'monthly_total',
        'level': {'col': 'sec_turnover_mnshares', 'zh': '当月成交股数',
                  'unit': 'mn shares/month', 'fmt': 'f0c'},
        # 不给 total_col / weight_col：level 那一列本身就是当月合计，
        # 底座直接拿它滚 12 个月，柱与线同口径。
    }],

    'notes': [
        'SGX 的头部衍生品产品全部是离岸挂牌的他国标的。2026-06 实测：'
        'FTSE 中国 A50 期货 11,724,378 张（占当月衍生品总成交 34.2%）、'
        '外汇期货合计 10,268,040 张（29.9%）、铁矿石 5,354,979 张（15.6%）、'
        '日経225 期货 748,048 张（2.2%）。A50 与日経225 分别对着 HKEX 与 JPX 的同标的合约，'
        '本页把两者单列而不是并进「股指期货合计」。',

        'GIFT Nifty 在 2023-07 有计数口径断点。官方报告脚注写明 "For periods prior to '
        'June 2023, volumes are computed based on higher of buy and sell lots"，'
        '之后改为买卖双边合计。**本页不对断点两侧的水平差做任何归因**：'
        'series/sgx.csv 里 2023-06 = 1,696,663 张、2023-07 = 1,330,907 张，'
        '是降不是升，说明同期还有 GIFT Connect 迁移的量在动，'
        '单看这条序列分不出「口径变了」和「份额丢了」。',

        '衍生品的 DDAV 不能用「当月总量 ÷ 交易日数」反推。sec_trading_days 那一行'
        '官方括号里写的是 (Stock Market) / (Securities)，是**证券市场**的交易日；'
        '实测 2026-06 用 34,315,225 ÷ 1,619,444 反推得 21.19 天，而官方写的交易日是 21。'
        '所以本页月总量与日均两条都直接取官方值，谁也不从谁推。',

        '「商品合计」按官方定义**不含加密**。实测口径校验：SICOM 3,895,114 + Energy 493,152 '
        '+ Metal&DryBulk 73,586,973 + Dairy 期货 688,923 + Dairy 期权 104,742 + '
        'Energy Metals 2,640 = 78,771,544 张，恰好等于官方新闻稿的 FY2026 "78.8 million lots"；'
        '把 Crypto 加进去就对不上。所以加密单列一组。',

        '台湾指数敞口在 2020-07 换了授权方：MSCI Taiwan 停发（series/sgx.csv 里该列 '
        '2021-11 之后无值、2021-02 起全是 0、2021-01 还有一个内部空洞），改挂 FTSE Taiwan。'
        '本页只画 FTSE 那条，MSCI 那条不上页面 —— 一条带空洞的归零序列进平滑类图型会画出假线。',

        '证券成交额是暂定数：官方脚注写明月末临近的撤单可能来不及计入、'
        '调整顺延到下个月的报告。fetch/sgx.py 按「已有值永不覆盖、只填空」处理，'
        '差异另记 cache。实测 2026-04/05/06 三期的重叠月 8 个数据点逐位相同，'
        '近月重述不是常态。',

        '本页全部金额为新元。跨币种比较由 build/notional.py 统一换算：'
        '流量（SDAV、成交额、募资额）配月均汇率，存量（月末市值、月末未平仓）配月末汇率。',

        '未上页面的月频列：sec_trading_days（分母，且是证券市场口径）、'
        'deriv_swaps_vol_contracts（2026-06 = 7,662 张，占总量 0.02%）、'
        'vol_msci_taiwan_futures_contracts（已停发的死列，见上）。',
    ],
}
