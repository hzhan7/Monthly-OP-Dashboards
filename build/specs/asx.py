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

━━ 量价分解：这一家只能做「笔数 × 每笔均值」，做不了「股数 × 均价」━━
series/asx.csv 里**没有成交股数列**（官方 MAR 不发），能配成对的只有
`value_cash_total_audbn`（当月成交额）与 `trades_cash_total`（当月成交笔数）。
所以派生量是**每笔平均成交额**，`kind` 必须写 `per_trade`：
它衡量的是**订单碎片化程度**，把它叫「价」是错的 —— 同一笔母单被切成更多子单，
笔数上升、每笔金额下降，而成交额与股价一点没变。

⚠ **分子必须用 total 口径（含场外报告），不能用 onmarket。**
判据不是文字而是对账：本文件 `_per_trade_check()` 在 import 期拿两种分子各算一遍
「自算每笔均值 ÷ 官方 avg_value_per_trade_aud − 1」，total 口径的相对差中位数是
万分之零点几（官方那一列自己的取整），换成 onmarket 立刻跳到两位数百分比 ——
说明官方的 `trades_cash_total` 数的是**含场外报告**的全部成交笔数。
配错分子，「每笔均值」会整条系统性偏低，而图形完全正常。

━━ 财年按**结束**年命名，这一条是验出来的不是猜的 ━━
`year_label` 猜错会让整排柱标签集体偏一年，而图看上去完全正常、没有任何自动判据抓得到。
本页的验证办法是拿 CSV 自己去撞官方 FY26 新闻稿：把 2025-07 … 2026-06 这 12 个月的
`capital_secondary_audmn` 加起来（`_fy_probe()` 现算），得到的正是官方 FY26 新闻稿
引用的那个二次融资读数（窄口径 A$37.8bn / 含换股对价 A$58.4bn，见下方 notes 第 4 条）。
⇒ **2025-07 起头的那一年，ASX 自己叫它 FY26** ⇒ `year_label='end'`（同 SGX，与 JPX 相反）。

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


# ══════════════════════════════════════════════════════════════════════════════
# 图注里要报的数**一个都不写死**：全部在 import 期从 series/asx.csv 现算，
# 再用 f-string 拼进 _NOTE_*（照 build/specs/jpx.py 的 _wedges()）。
# 任何一步算不出来就退回**不含数字的定性版本** —— 缺文件不许在 import 期抛异常，
# 否则 monthly_run 会因为一张页的配置炸掉整批。
# ══════════════════════════════════════════════════════════════════════════════
def _rows():
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _num(r, col):
    """CSV 里一格 → float；空格子 / 非数返回 None（不拿 0 冒充缺失）。"""
    try:
        v = r[col].strip()
    except (KeyError, AttributeError):
        return None
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _median(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def _per_trade_check():
    """两种分子各与官方 `avg_value_per_trade_aud` 对账 —— 「必须用 total 口径」的判据。

    官方自己发布了每笔均值那一列，所以「我算的对不对」不需要靠推理：
      total    口径：value_cash_total_audbn    × 1e9 ÷ trades_cash_total
      onmarket 口径：value_cash_onmarket_audbn × 1e9 ÷ trades_cash_total
    哪一个能对上官方那一列，就说明官方的笔数列数的是哪一口径的成交。

    返回 (月份数, total 相对差中位%, total 相对差最大%, onmarket 相对差中位%)；
    算不出全部返回 None。
    """
    tot, onm = [], []
    for r in _rows():
        off = _num(r, 'avg_value_per_trade_aud')
        n = _num(r, 'trades_cash_total')
        vt = _num(r, 'value_cash_total_audbn')
        vo = _num(r, 'value_cash_onmarket_audbn')
        if not off or not n:
            continue
        if vt is not None:
            tot.append(abs(vt * 1e9 / n / off - 1.0) * 100.0)
        if vo is not None:
            onm.append(abs(vo * 1e9 / n / off - 1.0) * 100.0)
    if not tot:
        return (None,) * 4
    return len(tot), _median(tot), max(tot), _median(onm) if onm else None


def _fy_probe():
    """最近一个完整 7 月制年度（Jul–Jun）里二次融资的两个口径合计 —— 验 year_label。

    这不是装饰性的数字：`year_label='end'` 猜错会让整排柱标签集体偏一年，
    而图形完全正常。拿这两个数去撞官方 FY26 新闻稿引用的读数，对上了才敢写 'end'。

    返回 (起始月, 结束月, 该年标签, 窄口径合计, 含换股对价合计)；算不出全部返回 None。
    """
    buckets = {}
    for r in _rows():
        m = (r.get('month') or '').strip()
        if len(m) != 7 or m[4] != '-':
            continue
        y, mo = int(m[:4]), int(m[5:])
        buckets.setdefault(y if mo >= 7 else y - 1, []).append(r)
    best = None
    for y in sorted(buckets):
        rows = buckets[y]
        if len(rows) != 12:
            continue
        a = [_num(r, 'capital_secondary_audmn') for r in rows]
        b = [_num(r, 'capital_secondary_total_audmn') for r in rows]
        if any(x is None for x in a) or any(x is None for x in b):
            continue
        best = (rows[0]['month'], rows[-1]['month'], f'FY{(y + 1) % 100:02d}',
                sum(a), sum(b))
    return best if best else (None,) * 5


def _tradingday_spread():
    """现货交易日数的最小/最大值与相对差（%）—— 单月同比毛刺的来源之一，现算不写死。"""
    v = [d for d in (_num(r, 'trading_days_cash') for r in _rows()) if d]
    if not v:
        return None, None, None
    return min(v), max(v), (max(v) / min(v) - 1.0) * 100.0


_PTN, _PTMED, _PTMAX, _PTONM = _per_trade_check()
_FY0, _FY1, _FYL, _FYA, _FYB = _fy_probe()
_DMIN, _DMAX, _DSPR = _tradingday_spread()


_NOTE_DECOMP = (
    '<b>这一家做不了「股数 × 均价」。</b><code>series/asx.csv</code> 里没有成交股数列'
    '（官方月度活动报告 MAR 不发），唯一能配成对的是当月成交额与当月成交笔数，'
    '所以派生量只能是<b>每笔平均成交额</b>。'

    '<b>分子为什么必须用 total（含场外报告）口径。</b>官方自己发布了 '
    '<code>avg_value_per_trade_aud</code>，所以「配得对不对」不靠推理、直接对账：'
    + ((f'用 <code>value_cash_total_audbn</code> 当分子，自算值与官方那一列的相对差'
        f'中位数只有 <b>{_PTMED:.4f}%</b>、最大 {_PTMAX:.4f}%（{_PTN} 个月，'
        f'差异量级就是官方那一列自己的取整）；换成仅场内的 '
        f'<code>value_cash_onmarket_audbn</code>，相对差中位数立刻跳到 '
        f'<b>{_PTONM:.1f}%</b>。' if _PTMED is not None and _PTONM is not None else
       '两种分子各算一遍与官方那一列对账，只有含场外报告的口径对得上。')
       )
    + '⇒ 官方的 <code>trades_cash_total</code> 数的是<b>含场外成交事后报告</b>的全部笔数，'
      '配仅场内的金额就是分子分母不同口径，「每笔均值」会整条系统性偏低而图形完全正常。'

      '<b>财年按结束年命名，是验出来的。</b>'
    + ((f'把 {_FY0} … {_FY1} 这 12 个月的二次融资加起来，窄口径 '
        f'<b>A${_FYA:,.0f}mn</b>、含换股对价 <b>A${_FYB:,.0f}mn</b> —— '
        f'正是官方 {_FYL} 新闻稿引用的那两个读数（见页尾口径说明）。'
        f'⇒ {_FY0} 起头的这一年 ASX 自己叫它 {_FYL}，所以本图 '
        f"<code>year_label='end'</code>（同 SGX，与 JPX 的 'start' 相反）。"
        if _FYA is not None else
        '本页财年按结束年命名（同 SGX，与 JPX 相反），依据是官方新闻稿对同一段 '
        '12 个月的称呼；本次未能从 CSV 复算那两个对账数。'))
    + '猜错这个字段会让整排柱标签集体偏一年，而图形完全正常、没有任何自动判据抓得到，'
      '所以本页宁可多跑一遍对账。'
)

_NOTE_TTM = (
    '<b>柱与线的口径不同是有意的。</b>柱是 <code>adt_cash_trades</code>（当月<b>日均</b>笔数，'
    '官方直接发布，已经把交易日数除掉了），线的滚动合计取自 '
    '<code>trades_cash_total</code>（当月<b>合计</b>笔数，同样官方直接发布）——'
    '两者谁也不从谁推，所以这里没有「日均乘回交易日」这一步，也就不会把交易日序列'
    '自己的误差引进来。'
    + (f'<b>为什么非要滚动不可。</b>本序列覆盖期内每月 {_DMIN:.0f}–{_DMAX:.0f} 个交易日，'
       f'两端相差 {_DSPR:.0f}% —— 「当月合计笔数」的单月同比里有一大截只是'
       f'「今年这个月比去年多开 / 少开了几天市」。任意连续 12 个月覆盖同一套日历，'
       f'这一层被整个消掉。' if _DSPR is not None else
       '<b>各月交易日数不同</b>，「当月合计」的单月同比里有一截只是日历差；'
       '任意连续 12 个月覆盖同一套日历，这一层被整个消掉。')
    + '⚠️ 澳洲的假期集中在 1 月（澳洲日）、4 月（复活节 + ANZAC）与 12 月，'
      '所以毛刺在这几个月最明显。'
)


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

        # 三列三个单位（trades/day、trades/month、A$/trade）⇒ 三个单桶 ⇒ 三张 gs_bar，
        # 次轴都是**单月同比**，而本表里没有同单位的第四条列可以同轴。
        # 契约允许用单月同比，条件是标题里声明（CONTRACT.md §6），所以口径写进组名 ——
        # 这一组三张图全都适用，不会误标到别的组上。
        # 笔数的滚动同比另有专图（见末尾 ttm_yoy），两者并列正是要让读者看见差多少。
        {'zh': '成交笔数与单笔金额（三列各成一图，次轴：单月同比）', 'cols': [
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

        # 存量单列一组：点对点同比正是期末口径唯一合法的读法。
        # 新上市家数搬到下面「新上市与退市」组 —— 它原先在这里是**单桶独苗**，
        # 底座对单桶画 gs_bar + 单月同比，而 tools/check_yoy_caliber.py 实测这条
        # 有 7 个月与 12 个月滚动口径**符号相反**（2024-08 单月 −100.0% vs 滚动 +7.3%）。
        # 与退市家数同轴之后这张变成 lines，不再有次轴同比。
        {'zh': '上市实体（月末在册，存量）', 'cols': [
            {'col': 'listed_entities_total', 'zh': '月末在册实体数',
             'unit': 'entities', 'fmt': 'f0c', 'stock': True},
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

        # 家数进出同轴：两列同为 entities、同一个量级（新上市个位到几十家、
        # 退市 −40…−4 家），画在一起才读得出「净进出」，也让两列都摆脱单桶 gs_bar
        # 的单月同比。起点不同（新上市 2017-10、退市 2024-05）由底座的 lines 断笔处理，
        # **不会**把缺口连成直线。
        {'zh': '上市与退市实体数（新上市自 2017-10、退市自 2024-05）', 'cols': [
            {'col': 'new_listed_entities', 'zh': '当月新上市实体数',
             'unit': 'entities', 'fmt': 'f0'},
            {'col': 'delisted_entities', 'zh': '当月退市实体数（负值）',
             'unit': 'entities', 'fmt': 'f0'},
        ]},

        # 2024-05 起才有的两列金额（含负值，见 notes）。
        {'zh': '挂牌资本净增与退市市值（2024-05 起）', 'cols': [
            {'col': 'capital_net_new_quoted_audmn', 'zh': '扣除退市后的净增挂牌资本',
             'unit': 'A$mn', 'fmt': 'f0c'},
            {'col': 'mktcap_delisted_audmn', 'zh': '退市实体市值（负值）',
             'unit': 'A$mn', 'fmt': 'f0c'},
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

    # ══ 量价分解：成交额 ≡ 成交笔数 × 每笔平均成交额 ═══════════════════════════
    # 恒等式是定义式，零假设零误差；唯一能出错的是分子分母不同口径，
    # 核查过程与全部实测数字见 _NOTE_DECOMP（import 期从 CSV 现算）。
    'decomp': [{
        'zh': '现货成交额',
        # ⚠ 派生量是**每笔平均成交额**，衡量订单碎片化程度，不是价。
        #   写成 share_price 会让底座印出「成交量加权平均成交价」那一套措辞 ——
        #   而本表根本没有成交股数列，那句话从头到尾是假的。
        'kind': 'per_trade',
        # 两列本身就是当月合计（value_* / trades_* 前缀；日均是另外的 adt_* 两列）。
        # ⇒ 不给 weight_col：声明 monthly_total 又给 weight_col 是硬失败，
        #   而真乘上去会把年度合计放大二十几倍，图形却照常画得出来。
        #   也不给 *_total_col：这两列自己就是 total。
        'granularity': 'monthly_total',
        'value': {'col': 'value_cash_total_audbn', 'zh': '当月成交额（含场外报告）',
                  'unit': 'A$bn/month', 'fmt': 'f1'},
        'qty': {'col': 'trades_cash_total', 'zh': '当月成交笔数',
                'unit': 'trades/month', 'fmt': 'f0c'},
        # A$bn ÷ 笔 = 1e-9 × (A$/笔) ⇒ price_scale=1e9 换回 A$/笔。
        # 纯单位换算，对增长率没有任何影响，只决定图注里报出来的水平值读数；
        # 那个读数可以与官方 avg_value_per_trade_aud 直接对账（见 _NOTE_DECOMP）。
        'price_zh': '每笔平均成交额',
        'price_unit': 'A$/trade',
        'price_fmt': 'f0c', 'price_scale': 1e9,
        # 澳洲财年 7 月—次年 6 月，且 ASX 自己按**结束**年命名（FY26 = 2025-07…2026-06）。
        # ⚠ 这一条是撞官方 FY26 新闻稿验出来的，不是按「澳洲惯例」推的 —— 见 _fy_probe()。
        'year_start_month': 7,
        'year_label': 'end',
        # 序列自 2017-10 起 ⇒ 完整财年 FY19…FY26 共 8 个 ⇒ 7 根柱。
        # 2017-07…2018-06 那一桶只有 9 个月，底座会自己丢掉（不按 9 个月折算成 12 个月）。
        'years': 7,
        'note': _NOTE_DECOMP,
    }],

    # ══ 水平值 + 12 个月滚动同比 ═════════════════════════════════════════════
    # 画分解式里的「量」那一侧（笔数）。柱用日均、线用当月合计，两列都是官方直接发布。
    'ttm_yoy': [{
        'zh': '现货成交笔数',
        'granularity': 'daily_avg',      # adt_ 前缀 = 当月日均
        'level': {'col': 'adt_cash_trades', 'zh': '日均成交笔数',
                  'unit': 'trades/day', 'fmt': 'f0c'},
        'total_col': 'trades_cash_total',
        # 不给 weight_col：官方已经发布了当月合计，没必要用「日均 × 交易日」去还原，
        # 那样只会把 trading_days_cash 自己的误差引进来。
        'note': _NOTE_TTM,
    }],

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
