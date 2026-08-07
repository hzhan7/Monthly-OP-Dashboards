# -*- coding: utf-8 -*-
"""ASX（澳大利亚证券交易所）单公司页配置。

━━ 这份文件的全部职责 ━━
声明「series/asx.csv 的哪些列上页面」。不算数、不画图、不碰公共代码。
整份文件可以直接删掉，别的页一行都不受影响。

━━ 本页有两处「同一指标换了口径」，必须画成两段而不是一条 ━━
ASX 的月度经营报告（MAR）在两个地方换过定义，series/asx.csv 如实分成了两组列：

    上市融资   capital_initial_raised_audmn          2017-10 → 2023-09（旧口径：IPO 实际募资额）
              capital_total_raised_incl_other_audmn 2017-10 → 2023-09
              mktcap_new_listings_audmn             2023-10 → 至今（新口径：新上市实体的挂牌市值）
              capital_new_quoted_audmn              2023-10 → 至今
    保证金     margin_cash_onbs_audbn                2019-10 → 2024-07（旧口径：表内现金保证金）
              margin_total_audbn                    2024-08 → 至今（新口径：保证金总额）

（起止月份是本次从 series/asx.csv 逐列实测出来的：上市融资旧口径 72 个月、新口径 34 个月、
保证金旧口径 58 个月、新口径 24 个月，四段各自零空洞。保证金旧口径比现货晚两年才有，
是因为 MAR 到 2019 年才开始披露这一行，不是解析漏了。）

「IPO 募资额」和「新上市挂牌市值」差着一个数量级（官方 FY26 新闻稿同时给出
IPO capital raised A$5.6bn 与 new listings added A$32.6bn in quoted market cap），
连成一条线就是凭空造出一次六倍增长。所以新旧口径各成一组，中间打断点。

旧口径那几列**最新月天生留空**，因此全部进 slow_cols —— 否则它们会把整页的
发布门槛永久卡死在 2023-09 / 2024-07。

━━ 有意不上页面的列，以及理由 ━━
· contracts_spi200_futures / oi_spi200_futures / contracts_3y_bond_futures /
  oi_3y_bond_futures / contracts_10y_bond_futures / oi_10y_bond_futures /
  contracts_90d_bankbill_futures / oi_90d_bankbill_futures
  —— **只有 2026-06 与 2026-07 两个月**，且不可回补：这些数来自 ASX 24 Monthly SFE
  Trading Report（monthly-futures-markets-report-{DDMMYYYY}.pdf），官方只保留最近 2 期，
  更早的直链一律 404（docs/verify/asx.md 口径坑 8 实测）。两个点画不出任何时序图，
  放上页面只会让人以为「ASX 的国债期货是 2026 年才有的」。
  ⇒ 本页的期货口径只到 ASX 24 合计（adv_futures_contracts）。分品种要等自然攒够月份。
· trading_days_cash / trading_days_futures / trading_days_eto —— 三套分母（2026-04 实测
  分别是 19 / 20 / 19），ADV 已经除过了；上页面只会诱导别人拿错的那套去反推月总量。
· contracts_futures_total / contracts_options_on_futures_total /
  contracts_futures_and_options_total / contracts_single_stock_options_total /
  contracts_index_options_total —— 月总量，= ADV × 对应交易日，与 adv_* 重复。
"""

import csv
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CSV = os.path.join(_ROOT, 'series', 'asx.csv')


# ── 断点从 CSV 读，不写死 ──────────────────────────────────────────────
# 内联而不抽公共函数：本页要能整份删掉不留残渣。只做「列 → 第一个有值的月份」
# 的字典查询，不含统计口径。读不到就返回 None —— 缺文件不许在 import 期抛异常。
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
    """两处口径换代。**每条断点必须绑定它真正涉及的列**。

    不写 `col` 的断点会被底座画到本页每一张图上（`Page.breaks_for()` 里
    `b['col']` 为空就对所有列放行）：实测「保证金口径换代」曾出现在 31 张图里的
    27 张 —— 现货成交额、退市实体数、OTC 清算、托管结算全被标上一条跟保证金
    毫无关系的红线，图注还跟着写「红色竖虚线 = 口径断点（保证金口径换代…）」。
    断点线的语义是「这张图上这条序列从这一期起与左侧不可比」，标错比不标更糟。

    一条断点涉及多列时按列各登记一份（`_load_breaks` 的去重键是 (month, col)，
    同月不同列不会被吞掉；同一张图同时画了其中两列时由 `breaks_for` 去重）。
    """
    out = []
    # 新口径列的首月就是断点（语义 = 从这一期起与左侧不可比）。实测 2023-10。
    # 涉及上市融资的新旧两组四列：旧组在这一期停发，新组从这一期起头。
    m = _first_present('capital_new_quoted_audmn')
    if m:
        for c in ('capital_initial_raised_audmn', 'capital_total_raised_incl_other_audmn',
                  'mktcap_new_listings_audmn', 'capital_new_quoted_audmn'):
            out.append({'month': m, 'col': c,
                        'zh': '上市融资口径换代：IPO 募资额 → 新上市实体挂牌市值'})
    # 实测 2024-08。只涉及保证金新旧两列，与本页其余任何序列都无关。
    m = _first_present('margin_total_audbn')
    if m:
        for c in ('margin_cash_onbs_audbn', 'margin_total_audbn'):
            out.append({'month': m, 'col': c,
                        'zh': '保证金口径换代：表内现金保证金 → 保证金总额'})
    # 底座画红虚线时按索引取月份，乱序会让标签配错断点 —— 统一按月份排。
    return sorted(out, key=lambda b: b['month'])


SPEC = {
    'ticker': 'asx',
    'name': 'ASX Limited',
    'title': '澳大利亚证券交易所（ASX）月度经营指标',
    'csv': 'asx.csv',
    'ccy': 'AUD',
    'source': ('Source: ASX Group Monthly Activity Report (market announcement to ASIC / '
               'ASX Market Announcements Office); format after Goldman Sachs GIR'),

    # 头条：现货与期货各一条。两者同出一份 MAR、同一天发布，
    # 2017-10 起逐月无洞（实测 106/106），且 ASX 是本仓最快的一家之一
    # （次月第 3–8 个日历日，众数第 5–6 日；2026-07 数据于 2026-08-06 发布）。
    'headline': [
        {'col': 'adt_cash_total_audbn', 'zh': '现货 ADT（含场外报告）',
         'unit': 'A$bn/day', 'fmt': 'f2'},
        {'col': 'adv_futures_and_options_contracts', 'zh': 'ASX 24 期货与期货期权 ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
    ],

    'groups': [
        {'zh': '现货成交额', 'cols': [
            {'col': 'adt_cash_total_audbn', 'zh': '日均成交额（含场外报告）',
             'unit': 'A$bn/day', 'fmt': 'f2'},
            {'col': 'adt_cash_onmarket_audbn', 'zh': '日均成交额（仅场内）',
             'unit': 'A$bn/day', 'fmt': 'f2'},
            {'col': 'value_cash_total_audbn', 'zh': '当月成交额（含场外报告）',
             'unit': 'A$bn/month', 'fmt': 'f1'},
            {'col': 'value_cash_onmarket_audbn', 'zh': '当月成交额（仅场内）',
             'unit': 'A$bn/month', 'fmt': 'f1'},
        ]},

        {'zh': '现货成交构成', 'cols': [
            {'col': 'value_open_trading_audbn', 'zh': '连续竞价',
             'unit': 'A$bn/month', 'fmt': 'f1'},
            {'col': 'value_auctions_audbn', 'zh': '集合竞价',
             'unit': 'A$bn/month', 'fmt': 'f1'},
            {'col': 'value_centrepoint_audbn', 'zh': 'Centre Point（自家暗池）',
             'unit': 'A$bn/month', 'fmt': 'f1'},
            {'col': 'value_tradereport_audbn', 'zh': '场外成交事后报告',
             'unit': 'A$bn/month', 'fmt': 'f1'},
        ]},

        {'zh': '成交笔数与单笔金额', 'cols': [
            {'col': 'adt_cash_trades', 'zh': '日均成交笔数',
             'unit': 'trades/day', 'fmt': 'f0c'},
            {'col': 'trades_cash_total', 'zh': '当月成交笔数',
             'unit': 'trades/month', 'fmt': 'f0c'},
            {'col': 'avg_value_per_trade_aud', 'zh': '平均每笔金额',
             'unit': 'A$/trade', 'fmt': 'f0c'},
        ]},

        # 2019-10 才有此行，单独一组（起点与主体差 24 个月）。
        {'zh': 'S&P/ASX 200 VIX（2019-10 起）', 'cols': [
            {'col': 'vix_asx200_avg', 'zh': '月内日均值',
             'unit': 'index level', 'fmt': 'f1'},
        ]},

        {'zh': 'ASX 24 期货与期货期权 ADV', 'cols': [
            {'col': 'adv_futures_and_options_contracts', 'zh': '合计',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_futures_contracts', 'zh': '其中：期货',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_options_on_futures_contracts', 'zh': '其中：期货期权',
             'unit': 'contracts/day', 'fmt': 'f0c'},
        ]},

        {'zh': '股票期权（ASX Clear ETO）ADV', 'cols': [
            {'col': 'adv_single_stock_options_contracts', 'zh': '单股期权',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_index_options_contracts', 'zh': '指数期权',
             'unit': 'contracts/day', 'fmt': 'f0c'},
        ]},

        {'zh': '上市实体', 'cols': [
            {'col': 'listed_entities_total', 'zh': '月末在册实体数',
             'unit': 'entities', 'fmt': 'f0c', 'stock': True},
            {'col': 'new_listed_entities', 'zh': '当月新上市实体数',
             'unit': 'entities', 'fmt': 'f0'},
        ]},

        {'zh': '二次融资', 'cols': [
            {'col': 'capital_secondary_total_audmn', 'zh': '二次融资合计',
             'unit': 'A$mn', 'fmt': 'f0c'},
            {'col': 'capital_secondary_audmn', 'zh': '其中：窄口径（不含换股对价）',
             'unit': 'A$mn', 'fmt': 'f0c'},
            {'col': 'capital_other_scrip_audmn', 'zh': '其中：换股对价等',
             'unit': 'A$mn', 'fmt': 'f0c'},
        ]},

        # 旧口径：2017-10 → 2023-09，最新月天生留空 ⇒ 已进 slow_cols。
        {'zh': '上市融资·旧口径（2017-10 → 2023-09，已停发）', 'cols': [
            {'col': 'capital_initial_raised_audmn', 'zh': 'IPO 实际募资额',
             'unit': 'A$mn', 'fmt': 'f0c'},
            {'col': 'capital_total_raised_incl_other_audmn', 'zh': '募资总额（含其他）',
             'unit': 'A$mn', 'fmt': 'f0c'},
        ]},

        # 新口径：2023-10 起。
        {'zh': '上市融资·新口径（2023-10 起）', 'cols': [
            {'col': 'mktcap_new_listings_audmn', 'zh': '新上市实体挂牌市值',
             'unit': 'A$mn', 'fmt': 'f0c'},
            {'col': 'capital_new_quoted_audmn', 'zh': '新增挂牌资本合计',
             'unit': 'A$mn', 'fmt': 'f0c'},
        ]},

        # 2024-05 起才有的三列（含负值，见 notes）。
        {'zh': '退市与净增（2024-05 起）', 'cols': [
            {'col': 'capital_net_new_quoted_audmn', 'zh': '扣除退市后的净增挂牌资本',
             'unit': 'A$mn', 'fmt': 'f0c'},
            {'col': 'mktcap_delisted_audmn', 'zh': '退市实体市值（负值）',
             'unit': 'A$mn', 'fmt': 'f0c'},
            {'col': 'delisted_entities', 'zh': '当月退市实体数（负值）',
             'unit': 'entities', 'fmt': 'f0'},
        ]},

        {'zh': 'OTC 利率衍生品清算（双边计数）', 'cols': [
            {'col': 'otc_notional_cleared_audbn', 'zh': '当月清算名义额',
             'unit': 'A$bn/month', 'fmt': 'f0'},
            {'col': 'otc_open_notional_audbn', 'zh': '月末未平仓名义额',
             'unit': 'A$bn', 'fmt': 'f0c', 'stock': True},
            {'col': 'billable_cash_cleared_audbn', 'zh': '可计费现货清算额',
             'unit': 'A$bn/month', 'fmt': 'f0'},
        ]},

        {'zh': '托管与结算', 'cols': [
            {'col': 'chess_holdings_audbn', 'zh': 'CHESS 托管证券市值',
             'unit': 'A$bn', 'fmt': 'f0c', 'stock': True},
            {'col': 'austraclear_holdings_audbn', 'zh': 'Austraclear 托管证券市值',
             'unit': 'A$bn', 'fmt': 'f0c', 'stock': True},
            {'col': 'settlement_msgs_mn', 'zh': '结算报文量',
             'unit': 'mn messages/month', 'fmt': 'f2'},
        ]},

        # 旧口径：2019-10 → 2024-07，最新月天生留空 ⇒ 已进 slow_cols。
        {'zh': '参与者保证金·旧口径（2019-10 → 2024-07，已停发）', 'cols': [
            {'col': 'margin_cash_onbs_audbn', 'zh': '表内现金保证金',
             'unit': 'A$bn', 'fmt': 'f1', 'stock': True},
        ]},

        {'zh': '参与者保证金·新口径（2024-08 起）', 'cols': [
            {'col': 'margin_total_audbn', 'zh': '保证金总额',
             'unit': 'A$bn', 'fmt': 'f1', 'stock': True},
        ]},

        {'zh': '参与者数', 'cols': [
            {'col': 'participants_asx_total', 'zh': 'ASX（现货）参与者',
             'unit': 'entities', 'fmt': 'f0', 'stock': True},
            {'col': 'participants_asx24_total', 'zh': 'ASX 24（衍生品）参与者',
             'unit': 'entities', 'fmt': 'f0', 'stock': True},
        ]},
    ],

    # 这三列是**已停发的旧口径**，最新月留空是正常状态，不许参与门槛判定。
    # slow_cols 的语义（「最新月留空是正常的，不进门槛」）与它们完全吻合；
    # 不这么标，整页的发布门槛会被永久钉死在 2023-09 / 2024-07。
    'slow_cols': [
        'capital_initial_raised_audmn',
        'capital_total_raised_incl_other_audmn',
        'margin_cash_onbs_audbn',
    ],

    'breaks': _breaks(),

    'notes': [
        'OTC 利率衍生品清算名义额是**双边计数**（官方脚注 "Cleared notional value is '
        'double sided"）。与 CME / LCH 的口径不同，跨家比较前必须先统一，'
        '否则 ASX 会被系统性放大一倍。实测 2026-07：当月清算 A$635.5bn、'
        '月末未平仓 A$4,872.7bn。',

        '上市融资在 2023-10 换了口径：旧口径是 IPO 实际募资额，新口径是新上市实体的'
        '挂牌市值，两者差着一个数量级（官方 FY26 新闻稿同时给出 IPO capital raised '
        'A$5.6bn 与 new listings added A$32.6bn in quoted market capitalisation）。'
        '本页把新旧口径画成两组，中间打断点，**绝不连成一条线**。'
        '保证金同理，在 2024-08 由「表内现金保证金」换成「保证金总额」。'
        '两个断点的月份都是从 series/asx.csv 里新口径列的首月读出来的，没有写死。',

        '「退市与净增」那一组的 delisted_entities 与 mktcap_delisted_audmn '
        '**在源数据里就是负值**（实测区间分别是 −40…−4 家、−22,533…−20 A$mn），'
        '是「从总数中减去」的记号，不是数据错误。'
        '⇒ 这一组不能用强制零基线的图型（bars_labeled 会把负柱画到画布外，'
        '见 docs/CHART_KINDS.md §3.3）。',

        '「二次融资合计」= 窄口径 + 换股对价等。官方新闻稿说的 follow-on 是**窄口径**：'
        'FY26 窄口径 A$37.849bn 对上新闻稿的 A$37.8bn，含换股对价的口径是 A$58.428bn。'
        '两列都上页面，只放一列必然对不上任何一份官方文本。',

        'ASX 现货 ≠ 澳洲现货全市场。Cboe Australia（原 Chi-X）的成交不在 MAR 里，'
        '所以本页的现货口径是「ASX 自身经营量」，不是「澳洲市场量」，'
        '不能用来算 ASX 的市场份额。',

        '上市实体数含批发/零售债券发行人、LIC/LIT 与订书式实体，**不含 ETF 与 mFund**。'
        '与 HKEX 的 new_listings（主板 + GEM 股票）口径不同，横截面页放一起要标注。',

        '本页**没有** ASX 24 分品种（SPI 200 / 3 年期与 10 年期国债期货 / 90 日银行票据）'
        '的月度序列。分品种数据出自 ASX 24 Monthly SFE Trading Report，'
        '官方只保留最近 2 期、更早的直链一律 404 且不可回补，'
        'series/asx.csv 里目前只有 2026-06 与 2026-07 两个月。'
        '两个点画不出时序，只能从 2026-06 起逐月往后攒；攒够之后再加一组即可。',

        '本页全部金额为澳元。跨币种比较由 build/notional.py 统一换算：'
        '流量（ADT、成交额、融资额、当月清算额）配月均汇率，'
        '存量（月末未平仓名义额、托管市值、保证金、实体数）配月末汇率。',

        '未上页面的月频列：trading_days_cash / trading_days_futures / trading_days_eto'
        '（三套分母，2026-04 实测分别是 19 / 20 / 19）、'
        '以及五条 contracts_*_total 月总量列（= ADV × 对应交易日，与 adv_* 重复）。',
    ],
}
