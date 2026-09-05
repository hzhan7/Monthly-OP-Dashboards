# -*- coding: utf-8 -*-
"""ASX（澳大利亚证券交易所）单公司页配置。

━━ 这份文件的全部职责 ━━
声明「series/asx.csv 的哪些列上页面」。不算数、不画图、不碰公共代码。
整份文件可以直接删掉，别的页一行都不受影响。

━━ 本页有两处「同一指标换了口径」，必须画成两段而不是一条 ━━
ASX 的月度经营报告（MAR）在两个地方换过定义，series/asx.csv 如实分成了两组列：

    上市融资   capital_initial_raised_audmn          2016-01 → 2023-09（旧口径：IPO 实际募资额）
              capital_total_raised_incl_other_audmn 2016-01 → 2023-09
              mktcap_new_listings_audmn             2023-10 → 至今（新口径：新上市实体的挂牌市值）
              capital_new_quoted_audmn              2023-10 → 至今
    保证金     margin_cash_onbs_audbn                2019-10 → 2024-07（旧口径：表内现金保证金）
              margin_total_audbn                    2024-08 → 至今（新口径：保证金总额）

（这里写的月份只是给人读的路标；**页面上的组标题与断点月一律由 `_span()` / `_first_present()`
在 import 期从 CSV 现算**，改不改这段注释都不影响图。2026-08 回补到 2016-01 之后逐列实测：
上市融资旧口径 93 个月、新口径 34 个月、保证金旧口径 58 个月、新口径 24 个月，四段各自零空洞。
保证金比现货晚三年半才有，是因为 MAR 到 2019-10 才开始印这一行，不是解析漏了。
⚠ 上市融资的口径断点**只有 2023-10 一处**。曾有一份笔记说「Listings 段在 2016/2017 之间
也换过定义」，那是误记：回补的 2016-01…2017-09 这 21 期里，旧口径两列 21/21 期期都有、
新口径列一期都没有，所以 2016/2017 之间没有任何断点。）

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

━━ 分解图按**日历年 Jan–Dec + 当年 YTD** 分桶（2026-08-07 按用户指令改），FY 对账基准保留 ━━
分解图原按 ASX 财年（Jul–Jun）分 7 根柱，2026-08-07 按用户指令改为 4 个完整日历年
+ 当年 YTD（YTD 的同比基期由底座逐月对齐到去年同期月份，见 build/single.py 的 `_ytd`）。
**FY 口径与官方新闻稿的对账证据保留在本文件里，不删**：ASX 自家财年按**结束**年命名
（FY26 = 2025-07 … 2026-06），验法是拿 CSV 自己去撞官方 FY26 新闻稿 —— 把那 12 个月的
`capital_secondary_audmn` 加起来（`_fy_probe()` 现算），得到的正是官方 FY26 新闻稿
引用的那个二次融资读数（窄口径 A$37.8bn / 含换股对价 A$58.4bn，见下方 notes 第 4 条）。
这条基准留着有两个用处：① 图注据此提醒读者「日历年柱对不上官方 FY 新闻稿里的年度数字」；
② 将来若改回 FY 分桶，`year_label='end'` 的判据现成（同 SGX，与 JPX 的 'start' 相反），
不必重新验。图已按用户指令改日历年，FY 对账基准见本节与 `_fy_probe()`。

━━ ASX 24 分品种那 8 列来自**另一份官方文件**，所以起点比全页主体晚 ━━
contracts_spi200_futures / oi_spi200_futures / contracts_3y_bond_futures /
oi_3y_bond_futures / contracts_10y_bond_futures / oi_10y_bond_futures /
contracts_90d_bankbill_futures / oi_90d_bankbill_futures 的源不是 MAR，而是
ASX 24 的 **Monthly SFE Trading Report**（MAR 本身只给期货合计，不拆品种），
链接逐期印在 MAR 正文的期货段末尾。

2026-08 之前这 8 列**只有 2026-06 / 2026-07 两个月**，当时写的理由是「官方只保留最近
2 期、历史不可回补」。那句话已被逐期实发 HTTP 推翻：卡住的是抓取器 ——
`fetch/asx.py:_SFE_LINK` 把文件名里的日期写死成 8 位数字，而官方在 YYMMDD / DDMMYY /
DDMMYYYY 之间来回换（见 fetch/asx.py 口径坑 22）。正则改成不解释日期之后，
`python3 fetch/asx.py --sfe-backfill 2020-06 2026-05` 一次补齐 72 个月，
**这 8 列因此上了页面**，起点由 `_span_zh()` 现算，不写死。

⚠️ 起点那个月是**辅源在官网上的存档天花板，不是产品上线时间** —— SPI 200 与
3/10 年期国债期货在 2016 年之前很久就在跑了。2020-05 及更早那批 MAR 指向的是老站点
路径 `/data/market-reports/…`，该路径今天整体 302 到 404 页（200 + text/html 的
soft-404）；2020-06 那一期起改指 DAM，从此一直在。
⚠️ 这 8 列有了数据，**并不意味着 ASX 能进 `build/pools.py` 的 interest_rate 池** ——
2026-08-19 实测过了，进不去，而且原因恰恰就是上面那个天花板：全仓基期是 2019-01，
而这 8 列最早只到 2020-06。该池的合计按「任一成员缺值该月即缺」求交集，ASX 一进来
池窗口就从 2014-12 收到 2020-06、基期那一格变成 nan，定基指数直接算不出来
（页面按设计会 skip 整页）。走 ICE 那条 contracts_only 也躲不开 —— 增长图同样以
2019-01 = 100 定基。理由已按这个实测结论写进 pools.py 的 `excluded`，
两处口径若有出入，以 pools.py 那条为准。

━━ 有意不上页面的列，以及理由 ━━
· trading_days_cash / trading_days_futures / trading_days_eto —— 三套分母（有多少个月
  三者不全相同、最近一次是哪个月，由 `_tradingday_split()` 现算并印在图注上；这里
  **不再抄一个月份当例子** —— 上一版抄的是「2026-04 实测 19 / 20 / 19」，而 CSV 里
  2026-04 三列都是 20，举的例子恰好是三者相等的一个月），ADV 已经除过了；
  上页面只会诱导别人拿错的那套去反推月总量。
· contracts_futures_total / contracts_options_on_futures_total /
  contracts_futures_and_options_total / contracts_single_stock_options_total /
  contracts_index_options_total —— 月总量，= ADV × 对应交易日，与 adv_* 重复。
  ⚠ 这条**不适用于**上面那 8 列分品种：官方那份分品种报告只印月度总量，
  不印分品种 ADV，所以分品种图只能画月总量 —— 那不是重复，那是唯一形态。
  也正因如此，分品种图与 ASX 24 合计那张图（contracts/day）**单位不同、不能对读**，
  要比就先各自除以 trading_days_futures。
"""

import csv
import math
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


def _last_present(col):
    """最后一个有值的月份；读不到返回 None。与 `_first_present` 成对。"""
    out = None
    try:
        with open(_CSV, encoding='utf-8') as fh:
            for r in csv.DictReader(fh):
                if col in r and r[col].strip():
                    out = r['month']
    except OSError:
        pass
    return out


def _span_zh(col, tail='起', dead=False):
    """组标题里那半句「自 YYYY-MM 起」/「YYYY-MM → YYYY-MM，已停发」，现算不写死。

    这些月份 2026-08 之前是**手打在组标题字符串里**的（「2017-10 → 2023-09」
    「新上市自 2017-10」…），于是回补一次历史就集体过期，而过期的表现是
    「图上第一根柱在 2016-01、标题却说 2017-10」—— 没有任何检查会报错。
    现算之后，series 每长一个月标题自己跟着走。

    读不到 CSV 就返回空串（缺文件不许在 import 期抛异常），标题退化成不含月份的版本。
    """
    a = _first_present(col)
    if not a:
        return ''
    if dead:
        b = _last_present(col)
        return f'{a} → {b}，已停发' if b else f'{a} 起'
    return f'{a} {tail}'


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
    """最近一个完整 7 月制年度（Jul–Jun）里二次融资的两个口径合计 —— FY 口径对账基准。

    分解图已按用户指令改成日历年分桶（year_start_month=1，此时底座硬约束 year_label
    只能留空/'start'），这个探针**不再决定任何图上字段，但保留不删**：
    ① 它是「ASX 财年按结束年命名」的对账证据 —— 两个合计对得上官方 FY26 新闻稿
      引用的读数，将来改回 FY 分桶时 year_label='end' 的判据现成，不必重验；
    ② 图注引用它现算的数，提醒读者本图的日历年柱对不上官方 FY 新闻稿里的年度数字。

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


def _page_cols():
    """本页真正上图的列（headline + groups + decomp + level_yoy 里出现过的 col）。

    SPEC 还没构造出来，所以不能从 SPEC 里读；但也不该手抄一份清单 —— 手抄的清单
    与 groups 分家的那天，图注就开始说另一张图的事。折中：**在 SPEC 组装完之后**
    由 `_scan_spec_cols()` 回填，本函数只在那之前给个空清单用。
    """
    return _PAGE_COLS


_PAGE_COLS = []


# ── 每一列的起点各自对应什么事，逐列写死理由（月份仍然现算）─────────────────────
#
# 为什么要有这张表：`_late_starts()` 能算出「哪一列晚了几个月」，算不出「为什么」。
# 没有理由那一半，图上左边那片空白只能被读成「数据缺失」——而它其实是**披露史**：
# ASX 每隔几年往月报里加行 / 换行，加之前那几年官方根本没印过这个数。
#
# 三类理由，措辞固定，别再发明第四类：
#   源头未印  官方那时的 MAR 里没有这一行（别处也没有，或在另一份文档里）；
#   口径切换  同一件事换了定义，旧列在同一期停发、新列在同一期开印 —— 必须打断点；
#   披露扩充  官方那一期新增了行，旧行照常继续（不是断点，只是左边没有）。
#   辅源天花板 这一列不出自 MAR，而出自另一份官方文件，那份文件**官网上只存到某月**；
#            更早的那批链接指向已下线的老站点路径（今天整体 soft-404）。
#            官方当年**印过**这些数，是站点后来把它们撤了 —— 与「源头未印」不是一回事。
#            2026-08 新增这一类（分品种那 8 列），此前只有前三类。
# 「产品那时没上线」这一类在 ASX **一条都没有**：本页所有列的起点差异全是文档变更或
# 站点存档边界，SPI 200、国债期货、Centre Point 在 2016-01 之前很久就都在跑了。
# 有人以后想拿「产品新上线」解释某条线的起点，先回来看这里。
#
# 每条理由后面的月份与行名都是 2026-08 逐期打开官方 PDF 核出来的（缓存在 cache/）。
_START_WHY = {
    'participants_asx_total': (
        '源头未印',
        '2016-06 及更早的 MAR 正文到 SETTLEMENT 段就结束了（共 6 页），'
        '没有 PARTICIPANTS 段 —— 参与者数当时印在**另发的 ASX Compliance activity '
        'report** 里（2016-02…2016-05 期 MAR 末页明写「A separate ASX Compliance '
        'activity report … has also been released today」）。'
        '2016-07 那一期把 LISTINGS COMPLIANCE ACTIVITY / PARTICIPANTS / ENFORCEMENT '
        '三段并进 MAR，这一行才出现。不是那时没有参与者，是这份文档那时不登它'),
    'participants_asx24_total': ('同上', '与上一列同一段、同一期并入'),
    'value_cash_onmarket_audbn': (
        '源头未印',
        '2016-01…2017-09 的现货段只印 <code>Total value</code>（含场外报告）与 '
        '<code>Average daily value on-market</code>，**没有**「当月仅场内成交额」这一行；'
        '2017-10 那一期现货段改版，三行同时改名并新增 <code>On-market value</code>。'
        '21 期缓存 PDF 逐期核过行名，一次都没出现过 ⇒ 是官方没印，不是解析器没认出来'),
    'margin_cash_onbs_audbn': (
        '源头未印',
        '2019-09 及更早的 Collateral Balances 表只逐项印 <code>- ASX Clear</code> / '
        '<code>- ASX Clear (Futures)</code> / <code>Cash equivalents…</code>，'
        '没有合计行；<code>Total cash margins held on balance sheet</code> '
        '自 2019-10 那一期才开始印（44 期缓存 PDF 逐期核过）。'
        '三项相加确实等于正文要点里说的那个总额，但那是我们加的，不入库'),
    'mktcap_new_listings_audmn': (
        '口径切换',
        '2023-10 那一期同时做了两件事：停印 <code>Initial capital raised</code> 与 '
        '<code>Total capital raised including other</code>，改印 '
        '<code>Quoted market cap of new listings</code> 与 '
        '<code>Total new capital quoted</code>。'
        '旧列的最后一期与新列的第一期严丝合缝，所以是换口径不是加行 ⇒ 页面打断点'),
    'capital_new_quoted_audmn': ('同上', '与上一列同一期切换'),
    'delisted_entities': (
        '披露扩充',
        '2024-05 那一期新增三行（<code>Entities de-listed</code>、'
        '<code>Quoted market capitalisation of entities de-listed</code>、'
        '<code>Total net new capital quoted</code>），旧行一行没停 ⇒ 不是断点，'
        '只是 2024-04 及更早官方没把退市侧的数披露出来'),
    'mktcap_delisted_audmn': ('同上', '与上一列同一期新增'),
    'capital_net_new_quoted_audmn': ('同上', '与上一列同一期新增'),
    'margin_total_audbn': (
        '口径切换',
        '2024-08 那一期停印 <code>Total cash margins held on balance sheet</code>、'
        '改印 <code>Total margins held</code>（由「表内现金保证金」扩到「保证金总额」）。'
        '两列首尾相接，2024-07 是旧口径最后一期 ⇒ 页面打断点'),
    # ── 分品种那 8 列：同一个原因，写在第一列上，其余引它 ────────────────────────
    # 顺序跟着 _PAGE_COLS 走（`_late_starts()` 按首月排序，首月相同的保持出现顺序），
    # 而 SPEC 里成交量组在未平仓组之前、SPI 200 在每组之首 ⇒ 下面这条一定排在最前。
    'contracts_spi200_futures': (
        '辅源天花板',
        'MAR 只给 ASX 24 的期货合计，**不拆品种**；分品种的月度成交与未平仓出自另一份'
        '官方文件 —— ASX 24 的 <b>Monthly SFE Trading Report</b>，链接逐期印在 MAR 正文里。'
        '这份文件在官网上的存档只回到本列的首月：更早那批 MAR 印的链接指向老站点路径 '
        '<code>/data/market-reports/…</code>，今天整体 302 到 404 页'
        '（HTTP 200 + text/html 的 soft-404），拿不到原件。'
        '<b>不是那时没有这些合约</b> —— SPI 200 与国债期货在本页首月之前很久就在跑了，'
        'ASX 24 的期货合计（本页另有其图）也一直有数'),
    'contracts_3y_bond_futures': ('同上', '与上一列同源同一份文件'),
    'contracts_10y_bond_futures': ('同上', '与上一列同源同一份文件'),
    'contracts_90d_bankbill_futures': ('同上', '与上一列同源同一份文件'),
    'oi_spi200_futures': ('同上', '与上一列同源同一份文件（未平仓侧，同一张表的另一列）'),
    'oi_3y_bond_futures': ('同上', '与上一列同源同一份文件'),
    'oi_10y_bond_futures': ('同上', '与上一列同源同一份文件'),
    'oi_90d_bankbill_futures': ('同上', '与上一列同源同一份文件'),
}


def _late_starts():
    """上页面的列里，起点晚于全页首月的那些 —— (列名, 首月, 晚了几个月)。

    回补一次历史，这张清单就会变长：2026-08 之前只有 3 列晚于首月，回补到 2016-01
    之后变成 10 列。写死一句「VIX 起点比主体晚 24 个月」那样的话必然过期，所以现算。
    （VIX 曾经在这张清单里，2026-08 起不在了 —— 它的正文口径已回补到 2016-01，
    见 fetch/asx.py 口径坑 21。这正是「月份现算」的价值：清单自己缩短了。）
    """
    rows = _rows()
    if not rows:
        return None, []
    first = rows[0]['month']

    def mi(m):
        return int(m[:4]) * 12 + int(m[5:])

    out = []
    for c in _page_cols():
        a = _first_present(c)
        if a and a > first:
            out.append((c, a, mi(a) - mi(first)))
    return first, sorted(out, key=lambda x: x[1])


def _interior_holes():
    """列的首末月之间的空格 —— (列名, 月份)。**页面上的列才算**。

    「界内空格」在本仓是异常状态，只有 fetch/asx.py:_KNOWN_SOURCE_GAPS 里登记过的
    才允许存在。这里把它们现算出来印进图注，是为了让图上那一处断笔有出处 ——
    否则读者只会看到一根线莫名其妙断了一个月。
    """
    rows = _rows()
    out = []
    for c in _page_cols():
        ms = [r['month'] for r in rows if (r.get(c) or '').strip()]
        if not ms:
            continue
        out += [(c, r['month']) for r in rows
                if ms[0] < r['month'] < ms[-1] and not (r.get(c) or '').strip()]
    return sorted(out, key=lambda x: x[1])


def _msg_precision_step():
    """`settlement_msgs_mn` 由 1 位小数改成 3 位小数的那一月；找不到返回 None。

    判据是**印刷位数**而不是数值：小数点后 >1 位的第一个月就是换代月。
    （官方定义没变，所以这不进 `_breaks()`，只进图注。）
    """
    for r in _rows():
        v = (r.get('settlement_msgs_mn') or '').strip()
        if '.' in v and len(v.split('.')[1]) > 1:
            return r['month']
    return None


_SFE_COLS = ('contracts_spi200_futures', 'oi_spi200_futures',
             'contracts_3y_bond_futures', 'oi_3y_bond_futures',
             'contracts_10y_bond_futures', 'oi_10y_bond_futures',
             'contracts_90d_bankbill_futures', 'oi_90d_bankbill_futures')


def _sfe_span():
    """分品种那 8 列的覆盖情况 —— (首月, 末月, 有值月数, 八列不齐的月份数)。

    八列同出一份文件、同一张表，所以正常情况下要么八列都有、要么八列都没有；
    「不齐的月数」不为 0 就是抓取出了岔子，图注会照实说。全部现算：这 8 列每多一个月，
    图注自己跟着走，不留一个会过期的手打数字。
    """
    ms = [r['month'] for r in _rows()
          if any((r.get(c) or '').strip() for c in _SFE_COLS)]
    if not ms:
        return None, None, 0, 0
    ragged = sum(1 for r in _rows()
                 if any((r.get(c) or '').strip() for c in _SFE_COLS)
                 and not all((r.get(c) or '').strip() for c in _SFE_COLS))
    return ms[0], ms[-1], len(ms), ragged


_TD_COLS = ('trading_days_cash', 'trading_days_futures', 'trading_days_eto')


def _tradingday_split():
    """三套交易日分母有几个月互不相同，外加**最近一个真的不相同的月**与那三个数。

    ⚠ 这条注 2026-08-19 之前写死成「2026-04 实测分别是 19 / 20 / 19」，而
    series/asx.csv 里 2026-04 三列都是 20 —— 举的例子恰恰是三者**相等**的一个月，
    正好把「三套分母不一样」这句话自己拆了。举例只能现举：随便钉死一个月份，
    官方重述一次或者窗口一动，例子与结论就分家，而没有任何检查会报警。

    返回 (可比月数, 三列互不全等的月数, 举例月, (三个读数))；算不出返回 (None,)*4。
    """
    n = diff = 0
    ex_m, ex_v = None, None
    for r in _rows():
        vs = [_num(r, c) for c in _TD_COLS]
        if any(v is None for v in vs):
            continue
        n += 1
        if len(set(vs)) > 1:
            diff += 1
            ex_m, ex_v = r['month'], vs          # 留最后一个 ⇒ 最近的那个月
    return (n, diff, ex_m, ex_v) if n else (None,) * 4


def _latest_pair(a, b):
    """最近一个 a、b 两列都有值的月：(月, a, b)；算不出返回 (None, None, None)。"""
    for r in reversed(_rows()):
        x, y = _num(r, a), _num(r, b)
        if x is not None and y is not None:
            return r['month'], x, y
    return (None,) * 3


def _range(col, nd=0):
    """一列的 (最小值, 最大值, 有值月数)，端点已按 nd 位小数**外扩**取整。

    下界向下取、上界向上取：印出来的是一对**边界**，四舍五入会把区间收窄，
    让某个真实读数落在自己声明的区间之外（enx 那边的「0.03–0.22」就是这么假的）。
    当前这两列在源数据里都是整数，nd=0 时外扩取整是恒等的 —— 这道保险是给
    「官方哪天开始发小数」准备的：那天到了，句子仍然自动成立。
    算不出返回 (None, None, 0)。
    """
    v = [x for x in (_num(r, col) for r in _rows()) if x is not None]
    if not v:
        return None, None, 0
    f = 10.0 ** nd
    return math.floor(min(v) * f + 1e-9) / f, math.ceil(max(v) * f - 1e-9) / f, len(v)


def _share_stats(num, den):
    """`num ÷ den` 的全历史中位与区间（%）—— 「两个口径差多远」的唯一诚实答案。

    名词释义要说清「含场外报告」与「仅场内」差在哪，光说「差一列」不够 ——
    差多少是个量级问题。这个量**现算**：写死一个百分比，下个月它就开始变旧，
    而释义板一年到头不重写。端点按 1 位小数**外扩**取整（同 `_range` 的理由：
    四舍五入会把区间收窄，让某个真实读数落在自己声明的区间之外）。

    返回 (中位%, 下界%, 上界%, 月数)；算不出全部返回 None。
    """
    v = []
    for r in _rows():
        a, b = _num(r, num), _num(r, den)
        if a is not None and b:
            v.append(100.0 * a / b)
    if not v:
        return (None,) * 4
    return (_median(v),
            math.floor(min(v) * 10 + 1e-9) / 10,
            math.ceil(max(v) * 10 - 1e-9) / 10,
            len(v))


def _count_before(col, month):
    """col 在 month **之前**有几个有值的月，以及那一段的首末月。

    「VIX 左边那 45 个月来自正文要点」那句话的算术底：45 与起点月必须同源，
    否则起点一现算、45 一写死，同一句话里两个数就会互相打架。
    """
    ms = [r['month'] for r in _rows()
          if _num(r, col) is not None and r['month'] < month]
    return (len(ms), ms[0], ms[-1]) if ms else (0, None, None)


_PTN, _PTMED, _PTMAX, _PTONM = _per_trade_check()
_FY0, _FY1, _FYL, _FYA, _FYB = _fy_probe()
_DMIN, _DMAX, _DSPR = _tradingday_spread()
_MSG_STEP = _msg_precision_step()
_SFE0, _SFE1, _SFEN, _SFERAG = _sfe_span()
_TDN, _TDDIFF, _TDM, _TDV = _tradingday_split()
_OTCM, _OTCC, _OTCO = _latest_pair('otc_notional_cleared_audbn',
                                   'otc_open_notional_audbn')
_DEMIN, _DEMAX, _DEN = _range('delisted_entities')
_DMMIN, _DMMAX, _DMN = _range('mktcap_delisted_audmn')
#: VIX 那一列在 MAR 把它排进现货表（2019-10）之前有多少个月只印在正文要点里。
_VIXN, _VIX0, _VIX1 = _count_before('vix_asx200_avg', '2019-10')
#: 场外成交事后报告占「含场外报告」口径的比重 —— 两套现货口径差多远，现算不写死。
_TRMED, _TRMIN, _TRMAX, _TRN = _share_stats('value_tradereport_audbn',
                                            'value_cash_total_audbn')
#: 「仅场内」那一列官方从哪个月才开始印（早于此月是官方没印，不是解析漏了）。
#: ⚠️ 本页有**两条**「仅场内」，披露起点不同，释义里必须分开说（2026-09 审出来的错：
#: 原文把「2017-10 才开始印」写成对整个词头成立，而那只对**月合计**那一列成立）：
#:   · `value_cash_onmarket_audbn`（当月成交额·仅场内，官方行 `On-market value`）
#:     —— COLUMN_SPEC 里 since='2017-10'，图上左边确实有一段空白；
#:   · `adt_cash_onmarket_audbn`（日均成交额·仅场内，官方行 `Average daily value
#:     on-market`）—— since=None，本页首月起就有，那张图上**没有**这段空白。
#: 两个起点都现算，谁也不写死。
_ONM0 = _first_present('value_cash_onmarket_audbn')
_ONM_ADT0 = _first_present('adt_cash_onmarket_audbn')


_NOTE_SFE = (
    '<b>分品种那两组图（SPI 200 / 3 年期国债 / 10 年期国债 / 90 日银行票据）'
    '不出自月度活动报告 MAR，而出自另一份官方文件。</b>'
    'MAR 只给 ASX 24 的期货合计，从不拆品种；拆品种的是 ASX 24 自家的 '
    '<b>Monthly SFE Trading Report</b>，链接逐期印在 MAR 正文的期货段末尾。'
    + ((f'本页这 8 列覆盖 <b>{_SFE0} 至 {_SFE1}</b>，共 {_SFEN} 个月'
        + ('，八列逐月同齐。' if not _SFERAG else
           f'，其中 <b>{_SFERAG} 个月八列不齐</b>（同一张表的列不该有这种事，'
           f'值得回头查抓取）。'))
       if _SFE0 else '本页这 8 列当前没有数据。')
    + '<b>左边那一大段空白是那份文件的存档边界，不是产品那时不存在。</b>'
      '更早的 MAR 同样印了链接，但指向已下线的老站点路径 '
      '<code>/data/market-reports/…</code>，今天整体 302 到官网 404 页'
      '（HTTP 200 + text/html 的 soft-404，不是干净的 404）；'
      '首月那一期起改指 DAM，从此一直在。SPI 200 与国债期货本身在本页首月之前很久'
      '就在跑了 —— 想看那段时间的期货活动，用同页的「ASX 24 期货与期货期权 ADV」。'
      '<b>入库时每一期都过两道独立闸门</b>：① PDF 首页抬头必须逐字写着该数据月'
      '（防止取到隔壁月份 —— 官方有两期 MAR 的 PDF 链接注解是陈的，指着三个月前那一份，'
      '而那一份本身完全合法，只有抬头认得出来）；'
      '② 该期报告的 <code>Total Exchange</code> 当月量必须等于同月 MAR 的'
      '期货 + 期权合计（回补时逐月核过，零例外）—— 这一条同时证明了「文件对上了月份」'
      '与「我们没有把哪一行读串」。'
      '<b>口径两处要留神</b>：成交量那组是<b>当月总张数</b>（官方那份报告只印月总量、'
      '不印分品种 ADV），与「ASX 24 期货与期货期权 ADV」那张图的 contracts/day '
      '<b>不是一个单位</b>，要比先各自除以当月期货交易日数；未平仓那四张是'
      '<b>月末快照</b>（存量），同比走点对点。'
      '<b>后期报告回看同一个月时偶尔会给出与当期不同的数</b>'
      '（实测一例：2025-03 期把 2024-03 的 3 年期国债成交印成 5,378,144，'
      '而 2024-03 当期印的是 5,379,506，差 0.03%）—— 本页一律用<b>当期原值</b>，'
      '不拿后期重述值盖历史。')


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

      '<b>本图按日历年（Jan–Dec）分桶，与 ASX 自家的报告年度不是一套日历。</b>'
      'ASX 的财年是 7 月制、按<b>结束</b>年命名'
    + ((f'：把 {_FY0} … {_FY1} 这 12 个月的二次融资加起来，窄口径 '
        f'<b>A${_FYA:,.0f}mn</b>、含换股对价 <b>A${_FYB:,.0f}mn</b> —— '
        f'正是官方 {_FYL} 新闻稿引用的那两个读数（见页尾口径说明），'
        f'⇒ {_FY0} 起头的那一年 ASX 自己叫它 {_FYL}。'
        if _FYA is not None else
        '（同 SGX，与 JPX 相反），依据是官方新闻稿对同一段 12 个月的称呼；'
        '本次未能从 CSV 复算那两个对账数。')
       )
    + '⇒ <b>本图任何一根日历年柱都对不上官方 FY 新闻稿里的年度读数</b> —— '
      '两套日历各覆盖不同的 12 个月，谁也不是谁的近似。要与官方 FY 文本对账，'
      '按上面那条「12 个月直接加总」的算法自己按 7 月制重加一遍即可。'
)

# ⚠️ **本页原来有一条 `ttm_yoy`（现货成交笔数：水平值 + 12 个月滚动同比），
# 2026-09 连同它的 `_NOTE_TTM` 一起删掉。** 全站同比按页面所有者的指令统一成单月之后，
# 那张图与下面「成交笔数与单笔金额」组里的第一张（`adt_cash_trades` 自己占一个单位桶，
# 底座画成 gs_bar + 次轴单月同比）变成同列、同窗口、同口径 —— 画出来一字不差。
# 底座为此加了硬护栏（build/single.py 的 `ex_level_yoy`：撞上就 SpecError），
# 所以这条不能只是注释掉了事，得真删。
#
# 它原来负责的那半句话（日均 vs 当月合计的差别）没有丢，见那一组的组注：
# `adt_cash_trades`（日均）与 `trades_cash_total`（当月合计）在同一组里各有一张图，
# 两条金线之差就是「今年这个月比去年多开 / 少开了几天市」那一层。


# ══════════════════════════════════════════════════════════════════════════════
# 名词释义（SPEC 的 `glossary`，排在所有 exhibit 之前）
#
# ━━ 与页尾 notes / 图注的分工 ━━
# notes 与图注说的是「这一张图这个月该怎么读」（含当月读数、当月实测的毛刺量）；
# 这一块说的是「这些词是什么意思」，一年到头是同一段 ⇒ 这里**不写当月读数**。
# 出现的数只有两类：把定义钉住的结构性量（场外报告占多大、三套交易日有几个月不等、
# 自算每笔均值与官方那一列差多少）与恒等式本身 —— 且**一个都不写死**，
# 全部在 import 期从 series/asx.csv 现算（同本文件其余图注的做法）。
#
# ━━ 为什么是这 18 个词（选词判断）━━
# 判据只有一条：这个词出现在本页的图题 / 序列名 / 纵轴 / 汇总表行头里，而且
# **不看定义就会读错**。按「读错会出什么事」分五类：
#   ① 分母与单位   ADT / ADV —— 本页有三套交易日数（现货 / ASX 24 / ETO），
#      而分品种那两组图画的是 contracts/month、不是 ADV 的 contracts/day。
#      不点破，读者会拿一套天数去反推另一套的月总量，或把两组直接比大小。
#   ② 同一件事的两个口径   含场外报告 / 仅场内、场外成交事后报告、Centre Point、
#      平均每笔金额、双边计数、挂牌市值 / 募资额、换股对价等、
#      表内现金 / 保证金总额 —— 本页最密集的坑全在这一类：两条口径都在页面上，
#      读串的代价是整条线系统性偏高或偏低，而图形完全正常，看不出来。
#   ③ 存量 vs 流量   未平仓（OI）—— 与同一份辅源里的「月度成交」并排画，
#      两者不能相加、同比也只能走点对点。
#   ④ 这一页的主体划分与数据源   ASX 24、ETO（股票期权）、参与者、
#      MAR / SFE 报告、S&P/ASX 200 VIX —— 两个市场、两份官方文件、两处印刷。
#      不点破，读者会以为 ETO 的指数期权里含着 SPI 200 期货期权、
#      或者反过来拿两者当同一个「指数期权」口径比大小；
#      也会把分品种那 8 列左边的空白当成「那时没有这些合约」。
#   ⑤ 同图不同物   可计费现货清算额、CHESS / Austraclear ——
#      这两处是**画在同一张图/编在同一组里，却不是同一件事**：
#      「可计费现货清算额」编在「OTC 利率衍生品清算（双边计数）」那一组里，
#      但它出自 clearing - exchange-traded markets 段、是现货清算额、不走双边计数；
#      CHESS 与 Austraclear 量级相近又并排出现，最容易被相加成「总托管市值」
#      或被当成包含关系。组标题与图注都说不了这一层（它们讲的是当月读数），
#      只能在这里说。
# **有意不收**：m/m、y/y、3Y %ile、pp/bp（全站通用读图约定，summary.note 已逐条讲过）、
# 「口径断点」与「慢腿」这两个**读图约定词本身**（页尾 notes 第 2、3 条讲的是这两件事
# 在本页的具体落点，释义板再讲一遍就是两处各写一份）、以及成交量 / 市值这类本页没有
# 特殊口径的常识词。
# ⚠️ 但断点**两侧那两个具名口径**要各收一条（挂牌市值 / 募资额、
# 表内现金 / 保证金总额）：收的是「这两个官方行名各指什么、外延差在哪」，
# 不是断点机制本身 —— notes 第 3、11 条只点了名字，没说改的是名字还是外延，
# 而读串的代价正是整段系统性偏高或偏低。两处口径换代按同一条标准处理，
# 不许一处收、一处不收（2026-09 审出来的：原来只收了上市融资那一处）。
# ══════════════════════════════════════════════════════════════════════════════
_GLOSSARY = [
    ('ADT',
     '现货<b>日均成交额</b>（average daily value）：<code>当月成交额 ÷ 当月现货交易日数'
     '</code>，官方直接印，本页不自算（两者逐月相符，差在官方自己的取整内）。'
     '本页头条与「日均成交额」那两行都是它；「当月成交额」那两行是<b>同一件事的月合计'
     '口径</b>，两者只差一个当月开市天数，不是两个指标。'),

    ('ADV',
     '<b>日均成交张数</b>（average daily contracts）：<code>当月总张数 ÷ 该市场当月'
     '交易日数</code>。⚠️ 分母<b>按市场各算一套</b>：现货、ASX 24、股票期权三套交易日数'
     + ((f'在本页 {_TDN} 个月里有 <b>{_TDDIFF} 个月不全相同</b>'
         if _TDN and _TDDIFF else '并不总是相同')
        )
     + '，所以不能拿其中一套去反推另一个市场的月总量。'
       '⚠️ 另一处：「ASX 24 分品种」那两组图画的是<b>当月总张数</b>（contracts/month，'
       '官方那份分品种报告只印月总量、不印分品种 ADV），与 ADV 的 contracts/day '
       '<b>不是一个单位</b>，要比先各自除以 ASX 24 的当月交易日数。'),

    ('含场外报告 / 仅场内',
     '现货成交额的两套官方口径，本页日均与月合计<b>各一对</b>、四条都上：'
     '<b>仅场内</b>＝ 连续竞价 ＋ 集合竞价 ＋ Centre Point；<b>含场外报告</b>'
     '（<code>Total cash market value</code>）＝ 仅场内 ＋ 场外成交事后报告。'
     '这两条恒等式是官方在同一张表里自己印出来的（核的是<b>月合计</b>那一对，'
     '日均是同一件事再除以当月现货交易日数），<code>fetch/asx.py</code> 逐月核过。'
     '⇒ 两者之差就是「场外成交事后报告」那一列'
     + ((f'（占含场外口径：全历史中位 <b>{_TRMED:.1f}%</b>，区间 '
         f'{_TRMIN:.1f}–{_TRMAX:.1f}%，{_TRN} 个月现算）'
         if _TRMED is not None else '')
        )
     + '。'
     + ((f'⚠️ 本页有<b>两条</b>「仅场内」，披露起点<b>不同</b>：'
         f'<b>当月成交额（仅场内）</b>（官方行名 <code>On-market value</code>）'
         f'<b>{_ONM0} 才开始印</b>，更早官方没有这一行 —— 月合计那张图左边的空白'
         f'是披露史，<b>不是 0</b>，也不许拿另外三列相加去补；'
         if _ONM0 else '')
        + (f'而<b>日均成交额（仅场内）</b>（官方行名 <code>Average daily value '
           f'on-market</code>）自本页首月 {_ONM_ADT0} 起官方一直在印，'
           f'日均那张图上<b>没有</b>这一段空白。'
           if _ONM_ADT0 else ''))),

    ('场外成交事后报告',
     '官方行名 <code>Trade reporting</code>：在 ASX 撮合<b>之外</b>达成、事后向 ASX '
     '申报的成交金额。它计入「含场外报告」口径，<b>不计入</b>「仅场内」。'
     '⚠️ 别与 Centre Point 混为一谈 —— 那一条是 ASX <b>自家</b>的撮合，算在仅场内里。'
     '本页的成交笔数（以及由它算出的平均每笔金额）数的是<b>含</b>这部分在内的全部成交。'),

    ('Centre Point',
     'ASX <b>自家</b>的匿名 / 中点撮合场所（本页序列名写作「自家暗池」）。'
     '它是 ASX 撮合的一部分，<b>算在「仅场内」里</b>'
     '（官方恒等式：连续竞价 ＋ 集合竞价 ＋ Centre Point ＝ 仅场内成交额）—— '
     '不要因为「暗池」两个字把它归进场外那一列。'),

    ('ASX 24',
     'ASX 集团的<b>衍生品市场</b>（官方那份分品种报告至今叫 Monthly SFE Trading '
     'Report，SFE 即原悉尼期货交易所），与现货市场分开统计：交易日数、参与者、'
     '报告都各自一套。本页凡带「ASX 24」的行与图只含这个市场的<b>期货与期货期权</b>；'
     '股票期权（ETO）是另一处，<b>不在里面</b>。'),

    ('ETO（股票期权）',
     'Exchange-Traded Options，在 <b>ASX Clear</b> 清算的交易所交易期权，本页分单股期权'
     '与指数期权两条，都是 ADV（contracts/day），分母是 ETO <b>自己</b>的交易日数。'
     '⚠️ 指数期权这一列<b>不含 SPI 200 期货期权</b> —— 那部分在「ASX 24 期货与期货期权 '
     'ADV」里（官方两份不同的小节，各自还有自己的合计恒等式，<code>fetch/asx.py</code> '
     '逐月核过）。两者是<b>两个市场、两套交易日分母</b>的不同产品：不能互相替代，'
     '也不能当成同一个「指数期权」口径去比大小。要合成一个「ASX 全部期权」的口径倒是'
     '<b>可以直接相加</b> —— 两列互斥，不会有哪一张合约被算两遍。'),

    ('未平仓（OI）',
     'open interest：月末<b>仍未了结</b>的合约张数，是某一天的<b>截面（存量）</b>，'
     '不是当月累计（流量）。⇒ 与同源的「分品种月度成交」<b>不能相加</b>、也不能比大小；'
     '同比只能走点对点（月末 vs 去年同月月末）—— 把 12 个月末快照加起来'
     '不指代任何真实的量。'),

    ('平均每笔金额',
     '官方直接印的一列（<code>Average value per trade</code>）＝ 当月成交额 ÷ '
     '当月成交笔数。<b>分子必须是「含场外报告」口径</b>：官方的成交笔数数的是含场外'
     '成交事后报告在内的全部笔数（含股票、ETP 与利率产品三类），配「仅场内」的金额'
     '会让整条线系统性偏低而图形完全正常'
     + ((f'（页尾那张量价分解图把同一个量自算了一遍对账：用含场外口径当分子，'
         f'与官方这一列的相对差中位数只有 {_PTMED:.4f}%，就是官方那一列自己的取整）'
         if _PTMED is not None else '')
        )
     + '。⚠️ 它衡量的是<b>订单碎片化</b>（一笔母单被拆成多少笔成交），<b>不是价</b>：'
       '算法把大单拆细就会让它一路走低，而标的价格完全可以同时在涨。'),

    ('双边计数',
     'OTC 利率衍生品清算名义额的官方口径（脚注原文 "Cleared notional value is double '
     'sided"）：<b>一笔清算按两个对手方各计一次</b>。本页「当月清算名义额」与'
     '「月末未平仓名义额」两条都是它。与 CME / LCH 的口径不同，跨家比较前必须先统一，'
     '否则 ASX 会被系统性放大一倍。⚠️ 同一组里的第三条「可计费现货清算额」'
     '<b>不走这个口径</b>（见下条）。'),

    ('可计费现货清算额',
     '官方行名 <code>Total billable cash market value cleared</code>，出自 MAR 的 '
     '<b>clearing - exchange-traded markets</b> 段：<b>现货</b>市场当月清算、'
     '且按可计费口径计入的成交额。⚠️ 它<b>不是</b> OTC 利率衍生品的名义额，'
     '也<b>不走双边计数</b> —— 它与「当月清算名义额」只是单位相同（A$bn/month）'
     '才画在同一根轴上，<b>两条不可相加</b>，那一组标题里的「双边计数」不管它。'
     '「可计费」是<b>计费口径</b>而不是成交口径（官方在这一段里没有另印'
     '「不可计费」的那部分），⇒ 也别拿它去替代「当月成交额」那两条现货口径。'),

    ('挂牌市值 / 募资额',
     '上市融资在本页有<b>新旧两套口径，不是同一件事</b>：旧口径「IPO 实际募资额」'
     '（<code>Initial capital raised</code>）是新上市公司这一次<b>募到的现金</b>；'
     '新口径「新上市实体挂牌市值」（<code>Quoted market capitalisation of new '
     'listings</code>）是这些实体<b>全部挂牌股份的市值</b>，含没有募集的存量股。'
     '两者差着一个数量级（页尾口径说明里引了官方同一份 FY 新闻稿同时给出的两个读数）'
     '⇒ 本页画成两组、中间打断点，<b>绝不连成一条线</b>。'),

    ('换股对价等',
     '官方行名 <code>Other capital raised including scrip-for-scrip</code>：以'
     '<b>自家股份作对价</b>而新增的挂牌资本（典型是换股并购），<b>不是</b>向市场'
     '募到的现金。官方同表印出、逐月核过的恒等式：窄口径 ＋ 换股对价等 ＝ 二次融资合计；'
     '官方新闻稿里说的 follow-on 指的是<b>窄口径</b>那一列。'),

    ('CHESS / Austraclear',
     'ASX 的<b>两套不同</b>的结算 / 托管系统，本页各出一条月末托管证券市值（存量）：'
     '<b>CHESS</b>（Clearing House Electronic Subregister System）是 ASX '
     '<b>上市证券</b>的电子登记与结算系统，官方行名 <code>Value of CHESS holdings '
     '- period end</code>；<b>Austraclear</b> 是<b>债务证券与货币市场工具</b>的'
     '托管与结算系统，在 MAR 里自成一小节（<code>Austraclear settlement and '
     'depository</code>），行名 <code>Austraclear securities holdings - period '
     'end</code>。⚠️ 两者是<b>并列</b>、不是包含：谁都不是谁的子集，官方也没有印过'
     '两者的合计，⇒ <b>不要相加</b>当成「ASX 总托管市值」，也不要拿其中一条去算'
     '另一条的占比。同组第三条「结算报文量」（<code>Dominant settlement '
     'messages</code>）数的是<b>报文条数</b>、不是市值，与这两条不同量纲，单独成图。'),

    ('表内现金 / 保证金总额',
     '参与者保证金在本页有<b>新旧两套官方行名</b>：旧口径「表内现金保证金」＝'
     '<code>Total cash margins held on balance sheet</code>'
     + ((f'（{_span_zh("margin_cash_onbs_audbn", dead=True)}）'
         if _first_present('margin_cash_onbs_audbn') else '')
        )
     + '，行名自带<b>「现金」与「表内」两个限定</b>；新口径「保证金总额」＝'
       '<code>Total margins held</code>'
     + ((f'（{_span_zh("margin_total_audbn")}）'
         if _first_present('margin_total_audbn') else '')
        )
     + '，这两个限定<b>一个都没有</b>。⇒ 这是<b>换代不是改名</b>，'
       '新行名在字面上更宽；而官方从没印过两个口径的对照读数，宽多少本页给不出，'
       '⇒ 断点左右<b>绝不可连读</b>，跨断点的落差不是业务变化。'),

    ('参与者',
     '月末在册的持牌机构<b>家数</b>（存量），两个市场各一条、<b>口径并不相同</b>：'
     '现货侧官方行名是 <code>Market/Clearing/Settlement Participants</code>'
     '（交易 / 清算 / 结算三类许可），ASX 24 侧是 <code>Trading/Clearing '
     'Participants</code>（只有交易与清算两类）。⇒ 两条不能相加，也不宜直接比高低。'),

    ('MAR / SFE 报告',
     '本页主源是 ASX 的<b>月度活动报告</b>（Monthly Activity Report，MAR）。'
     '但「ASX 24 分品种」那 8 列（SPI 200 / 3 年期国债 / 10 年期国债 / 90 日银行票据的'
     '月度成交与月末未平仓）<b>不在 MAR 里</b> —— MAR 只给 ASX 24 的期货合计、'
     '从不拆品种；分品种出自另一份官方文件 <b>Monthly SFE Trading Report</b>'
     + ((f'，它在官网上的存档只回到 {_SFE0}' if _SFE0 else '')
        )
     + '。⇒ 那 8 列左边的大段空白是<b>那份文件的存档边界</b>，'
       '不是产品那时不存在（同期的 ASX 24 期货合计本页另有其图，一直有数）。'),

    ('S&P/ASX 200 VIX',
     '官方行名 <code>S&P/ASX 200 VIX (average daily value)</code>：本页这条画的是'
     '<b>月内每日读数的平均</b>，不是月末值，也不是月内最高。'
     + ((f'其中最早的 {_VIXN} 个月（{_VIX0}–{_VIX1}）这个数只印在 MAR <b>正文</b>的'
         f'波动率要点里、不在现货表内 —— 两处是<b>同一个数</b>'
         if _VIXN else '早年这个数只印在 MAR 正文的波动率要点里、不在现货表内'))
     + '（<code>fetch/asx.py</code> 里有逐期闸门：两处都取到时必须相等，否则拒绝入库）'
       '⇒ 左边那一段仍是<b>当期官方原值</b>，不是换算、派生或后期重述值。'),
]


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
    # 自 series 首月起逐月无洞（「无洞」这个断言由 build/verify_pages.py 每次构建复核；
    # 月数这里**一个都不抄** —— 它每个月加一，抄下来的那份先烂），
    # 且 ASX 是本仓最快的一家之一
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
        # 单月是全站唯一口径（CONTRACT §6.1 第 1 条），而 §6.6 的自动判据要求它
        # 写进标题（R4，不写就报 🟡），所以口径写进组名 ——
        # 这一组三张图全都适用，不会误标到别的组上。
        # ⚠️ 前两张是同一件事的两种单位：日均笔数（已把交易日数除掉）与当月合计笔数
        # （含交易日数）。**两条金线之差就是当月开市天数的同比** —— 本页「一个月多开
        # 几天市」这一层就是这么读出来的。
        # 2026-09 之前页尾另有一张「现货成交笔数：水平值与 12 个月滚动同比」专图；
        # 全站改单月口径后它与本组第一张完全重复，已删。
        {'zh': '成交笔数与单笔金额（三列各成一图，次轴：单月同比）', 'cols': [
            {'col': 'adt_cash_trades', 'zh': '日均成交笔数',
             'unit': 'trades/day', 'fmt': 'f0c'},
            {'col': 'trades_cash_total', 'zh': '当月成交笔数',
             'unit': 'trades/month', 'fmt': 'f0c'},
            {'col': 'avg_value_per_trade_aud', 'zh': '平均每笔金额',
             'unit': 'A$/trade', 'fmt': 'f0c'},
        ]},

        # 官方到 2019-10 才把这个数排进现货**表**；在那之前它只印在正文的波动率要点里，
        # 是同一个数的另一处印刷（26 期重叠逐位相同，见 fetch/asx.py 口径坑 21）。
        # 2026-08 起两处都取，这一列因此与页面主体同起点 —— 起点仍现算，不写死。
        {'zh': f'S&P/ASX 200 VIX（{_span_zh("vix_asx200_avg")}）', 'cols': [
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

        # ── ASX 24 分品种：源是另一份官方文件（Monthly SFE Trading Report）──────────
        # 四条同为 contracts/month、量级同在百万级，同轴可比。起点现算写进组名 ——
        # 那是**辅源的存档天花板**，不是产品上线时间（理由见 _START_WHY，页面上会印出来）。
        # 单位与上面那组 ASX 24 合计（contracts/day）不同，底座按单位分桶，不会画到一根轴上。
        # 前面几十个月为空：底座 `ex_lines` 见到窗口内有 null 会自动降级成不平滑的
        # `lines`（平滑图型把 null 当 0，会画出一条塌到零的假线），这里不需要也不该
        # 自己去裁窗口 —— 左端那片空白正是「辅源从哪个月才有」的如实呈现。
        {'zh': f'ASX 24 分品种月度成交（{_span_zh("contracts_spi200_futures")}）', 'cols': [
            {'col': 'contracts_spi200_futures', 'zh': 'SPI 200 股指期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'contracts_3y_bond_futures', 'zh': '3 年期国债期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'contracts_10y_bond_futures', 'zh': '10 年期国债期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'contracts_90d_bankbill_futures', 'zh': '90 日银行票据期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        # 未平仓是**月末快照**，与上面的当月成交量是两件事（成交量是流量、OI 是存量），
        # 所以四列一律 stock=True：底座会把它们各自拆成一张期末口径的图、
        # 次轴同比走点对点（月末 vs 去年同月月末），而不是按流量口径算。
        {'zh': f'ASX 24 分品种月末未平仓（{_span_zh("oi_spi200_futures")}）', 'cols': [
            {'col': 'oi_spi200_futures', 'zh': 'SPI 200 股指期货',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_3y_bond_futures', 'zh': '3 年期国债期货',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_10y_bond_futures', 'zh': '10 年期国债期货',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_90d_bankbill_futures', 'zh': '90 日银行票据期货',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
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

        # 旧口径：最新月天生留空 ⇒ 已进 slow_cols。起止月现算。
        {'zh': f'上市融资·旧口径（{_span_zh("capital_initial_raised_audmn", dead=True)}）',
         'cols': [
            {'col': 'capital_initial_raised_audmn', 'zh': 'IPO 实际募资额',
             'unit': 'A$mn', 'fmt': 'f0c'},
            {'col': 'capital_total_raised_incl_other_audmn', 'zh': '募资总额（含其他）',
             'unit': 'A$mn', 'fmt': 'f0c'},
        ]},

        # 新口径：起点现算（= 上市融资那条断点的月份）。
        {'zh': f'上市融资·新口径（{_span_zh("capital_new_quoted_audmn")}）', 'cols': [
            {'col': 'mktcap_new_listings_audmn', 'zh': '新上市实体挂牌市值',
             'unit': 'A$mn', 'fmt': 'f0c'},
            {'col': 'capital_new_quoted_audmn', 'zh': '新增挂牌资本合计',
             'unit': 'A$mn', 'fmt': 'f0c'},
        ]},

        # 家数进出同轴：两列同为 entities、同一个量级（新上市个位到几十家、
        # 退市 −40…−4 家），画在一起才读得出「净进出」，也让两列都摆脱单桶 gs_bar
        # 的单月同比。起点不同（新上市 2017-10、退市 2024-05）由底座的 lines 断笔处理，
        # **不会**把缺口连成直线。
        {'zh': f'上市与退市实体数（新上市自 {_first_present("new_listed_entities")}、'
               f'退市自 {_first_present("delisted_entities")}）', 'cols': [
            {'col': 'new_listed_entities', 'zh': '当月新上市实体数',
             'unit': 'entities', 'fmt': 'f0'},
            {'col': 'delisted_entities', 'zh': '当月退市实体数（负值）',
             'unit': 'entities', 'fmt': 'f0'},
        ]},

        # 官方 2024-05 才开始印的两列金额（含负值，见 notes）。起点现算。
        {'zh': f'挂牌资本净增与退市市值（{_span_zh("capital_net_new_quoted_audmn")}）',
         'cols': [
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

        # 旧口径：最新月天生留空 ⇒ 已进 slow_cols。起止月现算。
        {'zh': f'参与者保证金·旧口径（{_span_zh("margin_cash_onbs_audbn", dead=True)}）',
         'cols': [
            {'col': 'margin_cash_onbs_audbn', 'zh': '表内现金保证金',
             'unit': 'A$bn', 'fmt': 'f1', 'stock': True},
        ]},

        {'zh': f'参与者保证金·新口径（{_span_zh("margin_total_audbn")}）', 'cols': [
            {'col': 'margin_total_audbn', 'zh': '保证金总额',
             'unit': 'A$bn', 'fmt': 'f1', 'stock': True},
        ]},

        # 参与者两列自 2016-07 起（2016-01…2016-06 的 MAR 里根本没有这一行，
        # 见 fetch/asx.py 口径坑 15），起点比页面主体晚半年 —— 标题现算说明。
        {'zh': f'参与者数（{_span_zh("participants_asx_total")}）', 'cols': [
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
        # ── 日历年 Jan–Dec（2026-08-07 按用户指令从 FY Jul–Jun 改来）────────────
        # 日历年的起始年 = 结束年，底座硬约束此时 year_label 只能留空或写 'start'
        # （写 'end' 直接 SpecError），所以这里**不写 year_label**，柱标签就是年份本身。
        # ASX 自家财年（7 月制、按结束年命名）的对账基准保留在 _fy_probe()，
        # 图注据此提醒读者：日历年柱对不上官方 FY 新闻稿数字。
        'year_start_month': 1,
        # 4 根完整日历年柱：底座取 years+1 个完整年，首年只当基期不出柱；
        # 当年不满 12 个月时底座自动追加一根 YTD 柱，同比基期逐月对齐去年同期月份
        # （build/single.py 的 _ytd，任一侧缺值即止、首月不齐则不出 YTD 桶）。
        # 哪些年入选、YTD 覆盖到哪个月，都由底座按 CSV 现算并在自检行打印，
        # 这里不写死任何年份 —— 数据每多一个月，柱的构成自己滚动。
        'years': 4,
        'note': _NOTE_DECOMP,
    }],

    # ══ 没有 'level_yoy' 段 ══════════════════════════════════════════════════
    # 2026-09 之前这里有一条「现货成交笔数：水平值 + 12 个月滚动同比」（柱用日均、
    # 线用当月合计）。全站改单月口径后它与「成交笔数与单笔金额」那一组的第一张
    # 同列、同窗口、同口径，画出来一字不差 ⇒ 连同 `_NOTE_TTM` 一起删掉。
    # 底座的 `ex_level_yoy` 对这种重复硬失败（build/single.py），别再加回来。
    # 名词释义：排在所有 exhibit 之前。选词的判断与「有意不收哪些词」写在 _GLOSSARY
    # 上方的注释块里（判据：本页图题 / 序列名 / 纵轴 / 行头里出现过，且不看定义就会读错）。
    'glossary': _GLOSSARY,

    'notes': [
        'OTC 利率衍生品清算名义额是**双边计数**（官方脚注 "Cleared notional value is '
        'double sided"）。与 CME / LCH 的口径不同，跨家比较前必须先统一，'
        '否则 ASX 会被系统性放大一倍。'
        # 读数取「两列都有值的最新一个月」现算 —— 写死一个月份，下个月这句话
        # 报的就不再是最新一期，而页头的抬头行照常往前走。
        + ((f'实测 {_OTCM}：当月清算 A${_OTCC:,.1f}bn、月末未平仓 A${_OTCO:,.1f}bn。')
           if _OTCM else ''),

        '上市融资在 2023-10 换了口径：旧口径是 IPO 实际募资额，新口径是新上市实体的'
        '挂牌市值，两者差着一个数量级（官方 FY26 新闻稿同时给出 IPO capital raised '
        'A$5.6bn 与 new listings added A$32.6bn in quoted market capitalisation）。'
        '本页把新旧口径画成两组，中间打断点，**绝不连成一条线**。'
        '保证金同理，在 2024-08 由「表内现金保证金」换成「保证金总额」。'
        '两个断点的月份都是从 series/asx.csv 里新口径列的首月读出来的，没有写死。',

        # ⚠️ 这里按**组名原文**点名，不写「退市与净增」那种页面上根本不存在的简称 ——
        #    读者拿它去页面上找会一张也找不到。两条列分属两张图，各自的组名如下。
        '「上市与退市实体数」与「挂牌资本净增与退市市值」两组里的 delisted_entities '
        '与 mktcap_delisted_audmn **在源数据里就是负值**'
        + ((f'（现算区间分别是 {_DEMIN:,.0f}…{_DEMAX:,.0f} 家、'
            f'{_DMMIN:,.0f}…{_DMMAX:,.0f} A$mn）')
           if _DEMIN is not None and _DMMIN is not None else '')
        + '，'
        '是「从总数中减去」的记号，不是数据错误。'
        '⇒ 这两组都不能用强制零基线的图型（bars_labeled 会把负柱画到画布外，'
        '见 docs/CHART_KINDS.md §3.3）。',

        '「二次融资合计」= 窄口径 + 换股对价等。官方新闻稿说的 follow-on 是**窄口径**：'
        'FY26 窄口径 A$37.849bn 对上新闻稿的 A$37.8bn，含换股对价的口径是 A$58.428bn。'
        '两列都上页面，只放一列必然对不上任何一份官方文本。',

        'ASX 现货 ≠ 澳洲现货全市场。Cboe Australia（原 Chi-X）的成交不在 MAR 里，'
        '所以本页的现货口径是「ASX 自身经营量」，不是「澳洲市场量」，'
        '不能用来算 ASX 的市场份额。',

        '上市实体数含批发/零售债券发行人、LIC/LIT 与订书式实体，**不含 ETF 与 mFund**。'
        '与 HKEX 的 new_listings（主板 + GEM 股票）口径不同，横截面页放一起要标注。',

        _NOTE_SFE,

        '本页全部金额为澳元。跨币种比较由 build/notional.py 统一换算：'
        '流量（ADT、成交额、融资额、当月清算额）配月均汇率，'
        '存量（月末未平仓名义额、托管市值、保证金、实体数）配月末汇率。',

        '未上页面的月频列：trading_days_cash / trading_days_futures / trading_days_eto'
        + ((f'（三套分母，{_TDN} 个月里有 {_TDDIFF} 个月三者不全相同；'
            f'最近一次是 {_TDM}，三列分别 '
            + ' / '.join('%.0f' % v for v in _TDV) + '）')
           if _TDM else '（三套分母，别拿其中一套去反推另一套的月总量）')
        + '、以及五条 contracts_*_total 月总量列（= ADV × 对应交易日，与 adv_* 重复）。',

        # ⚠️ 另有两条随 CSV 现算的图注（「起点不齐的列」与「界内空格」）在 SPEC
        #    组装完之后追加，见文件末尾 —— 它们要先知道本页到底上了哪些列。

        # ⚠ 「45 个月」与它前面那个起点月必须同源：起点是现算的（回补一次就左移），
        #   月数原先是写死的 —— 一左移，同一句话里两个数就自己打架。
        #   「26 期两者同时存在」那半句更糟：括号里枚举的 2019-10 / 2019-11 /
        #   2024-09…2026-07 只有 25 期，与 26 对不上；而且末月每个月往前走一格，
        #   期数却不会跟着变。两处并存与否记在 fetch/asx.py 的闸门里、不在 CSV 里，
        #   **现算不了** ⇒ 不报期数，只说这条闸门是什么、逐期都在跑。
        '<b>VIX 那张图左边那一段的数来自官方正文要点，不是表行 —— 同一个数，'
        '两处印刷。</b>ASX 的 MAR 到 <b>2019-10</b> 那一期才把 '
        '<code>S&P/ASX 200 VIX (average daily value)</code> 排进现货表；'
        + ((f'在那之前（{_VIX0}…{_VIX1}，共 {_VIXN} 个月）')
           if _VIXN else '在那之前')
        + '这个数只印在正文的波动率要点里'
          '（"…as measured by the S&P/ASX 200 VIX… was an average of 12.7"）。'
          '<b>两处从来没有不一致过</b>：凡是表行与正文同时给出这个数的月份，'
          '两者逐位相同、精度同为 1 位小数 —— 这条已经在 <code>fetch/asx.py</code> '
          '里固化成<b>逐期闸门</b>（两处都取到时必须相等，否则当场拒绝入库），'
          '所以它不是一次抽查的结论，而是每期都在复验的约束。'
        + ((f'所以左边那 {_VIXN} 个月') if _VIXN else '所以左边那一段')
        + '<b>仍然是当期官方公告原值</b>，不是换算、不是派生、'
          '也不是拿后期报告的重述值倒填。'
          '（这一列 2026-08 之前从 2019-10 才起 —— 那不是官方没发，是抓取器只认表行。）',

        '<b>结算报文量在 ' + (_MSG_STEP or '2017-10') + ' 之前只印到 1 位小数。</b>'
        'ASX 的 MAR 从那一期起把 <code>Dominant settlement messages (million)</code> '
        '由 1 位小数改成 3 位（实测前一期印 1.5、该期印 1.433）。'
        '<b>定义没变、只是印得细了，所以这不是口径断点、页面上不打红线</b>；'
        '但左边那一段被量化到 0.1（约 ±3% 的格），单月环比与同比在那一段有一层'
        '纯粹的取整噪声，读的时候别把它当成业务波动。'
        '入库一律用<b>当期公告原值</b>：后期报告回看同一个月时会给 3 位数'
        '（2018-09 期把 2017-09 印成 1.453，而 2017-09 当期印的是 1.5），'
        '那是重述值，不拿来盖历史。',
    ],
}


# ══════════════════════════════════════════════════════════════════════════════
# SPEC 组装完之后：把「本页上了哪些列」扫出来，再拼两条只有现算才不会过期的图注。
#
# 为什么放在最后而不是写进上面的 notes 列表：这两条讲的是**本页这些列**的起点与空格，
# 得先知道 groups / decomp / level_yoy 里到底出现了哪些 col。手抄一份列清单是可以，
# 但清单与 groups 分家的那天图注就开始说另一张图的事 —— 那种错不报警。
# ══════════════════════════════════════════════════════════════════════════════
def _scan_spec_cols(spec):
    """SPEC → 本页真正上图的列名（去重，保持出现顺序）。"""
    out = []

    def add(c):
        if c and c not in out:
            out.append(c)

    for h in spec.get('headline', []):
        add(h.get('col'))
    for g in spec.get('groups', []):
        for c in g.get('cols', []):
            add(c.get('col'))
    for d in spec.get('decomp', []):
        for k in ('value', 'qty'):
            add((d.get(k) or {}).get('col'))
    for t in spec.get('level_yoy', []):
        add((t.get('level') or {}).get('col'))
    return out


_PAGE_COLS[:] = _scan_spec_cols(SPEC)
_FIRST, _LATE = _late_starts()
_HOLES = _interior_holes()

if _LATE:
    # 每一列都要给出理由。给不出的（有人新加了列、或改了列名）**不许静默略过** ——
    # 直接把「本页还没给它写理由」印在图注上，比让读者以为那是数据缺失强得多。
    _bullets = []
    for c, a, n in _LATE:
        why = _START_WHY.get(c)
        if why:
            _bullets.append(f'<li><code>{c}</code> 自 <b>{a}</b> 起（晚 {n} 个月）'
                            f'—— <b>{why[0]}</b>：{why[1]}。</li>')
        else:
            _bullets.append(f'<li><code>{c}</code> 自 <b>{a}</b> 起（晚 {n} 个月）'
                            f'—— <b>本页还没给它写理由</b>，请补 '
                            f'<code>build/specs/asx.py:_START_WHY</code>。</li>')
    _NOTE_STARTS = (
        f'<b>本页各图的窗口都自 {_FIRST} 起，但线不都从左边缘开始 —— 左半边的空白是'
        f'披露史，不是数据缺失。</b>'
        f'ASX 每隔几年往月度活动报告（MAR）里加行 / 换行，另有几列的源根本不是 MAR '
        f'而是另一份官网上只存到某月的文件，所以有 {len(_LATE)} 列的'
        f'可取起点晚于本页首月，在图上表现为「同一张图里两条线起点不同」或'
        f'「左边一段没有柱」。逐列的起点各自对应什么事（月份现算，理由逐列核过官方 PDF）：'
        # 内联 style 是刻意的：assets/style.css 只给 `.prose ol` 定了 padding-left: 19px，
        # 嵌套的 ul 会吃浏览器默认的 40px，缩进比外层还深一倍。样式表是**共用文件**，
        # 为一页图注去动它不划算，所以就地写死这两条。
        '<ul style="margin:6px 0 0;padding-left:17px">' + ''.join(_bullets) + '</ul>'
        '<b>四类理由的区别要紧：</b>「源头未印」是官方那时根本没发这个数，'
        '「口径切换」是同一件事换了定义（旧列同期停发、页面必须打断点），'
        '「披露扩充」是新增行、旧行照常，'
        '「辅源天花板」是这一列不出自 MAR 而出自另一份官方文件、'
        '而那份文件官网上只存到某月（官方当年<b>印过</b>，是站点后来把更早的撤了 ——'
        '与「源头未印」不是一回事）。'
        f'<b>没有任何一列属于「产品那时才上线」</b>——'
        f'SPI 200、国债期货、Centre Point 在 {_FIRST} 之前很久就在跑了，'
        '起点差异要么来自文档本身的变更，要么来自站点的存档边界。'
        '<b>一律不许拿别的列相加去补左边那段。</b>最容易被误会的是 '
        '<code>value_cash_onmarket_audbn</code>（仅场内成交额）：它可由'
        '「连续竞价 + 集合竞价 + Centre Point」三项相加倒推'
        '（2017-09 算出来 80.829，与官方 2017-10 首次印出的 80.296 量级一致），'
        '但那是派生量，写进 series 就再也分不清哪个数是 ASX 印的、哪个是我们算的，'
        '所以留空。<b>要看不受起点影响的现货口径，用「含场外报告」那条线。</b>')
else:
    _NOTE_STARTS = ('本页各图的窗口自序列首月起，且每一列都从窗口左边缘就有值。')

# 每一处界内空格的病因，一格一句。**这张表与 `_HOLES` 必须一一对应** —— 下面那道
# 断言就是干这个的：本仓踩过太多次「句子是静态的、页面是现算的」（见 commit 0fc24f5，
# 一轮清掉 107 条假话）。空格数是现扫出来的，病因是手写的，两边一旦走散，页面就会
# 印出「有 3 处」却只解释得清 1 处，读者看不出另外两处是什么、为什么留空。
#
# 三处都是同一类事故：官方把千分位逗号与小数点印反了（fetch/asx.py 口径坑 19 / 23）。
# 三处的真值**都反推得出来**，但反推用的都不是「当期官方公告原值」，所以一律留空 ——
# 这条线一旦因为「这次反推更准」就松动，就再没有客观标准了。
_HOLE_WHY = {
    ('avg_value_per_trade_aud', '2016-09'):
        '把每笔均值的千分位逗号<b>印成了小数点</b>（4.852 应为 4,852）。真值算得出来'
        '（同表的成交额 ÷ 笔数 = 4,851.6，下一年同期报告的 pcp 列也印着 4852）',
    ('adv_index_options_contracts', '2020-01'):
        '把指数期权日均张数的千分位逗号<b>印成了小数点</b>（43.485 应为 43,485；'
        '同行另外三列 35,544 / 36,901 / 46,281 用的都是逗号）。真值算得出来'
        '（同表月总张数 913,176 ÷ 当月 21 个交易日 = 43,484.57）',
    ('billable_cash_cleared_audbn', '2025-08'):
        '<b>方向反过来</b>：把可计费现货清算额的小数点<b>印成了千分位逗号</b>'
        '（166,019 应为 166.019；同行另外三列 142.742 / 316.749 / 271.170 都是三位小数）。'
        '真值算得出来（同表本财年累计 316.749 − 上月 150.730 = 166.019）',
}
_hole_gap = [k for k in _HOLES if k not in _HOLE_WHY]
_hole_extra = [k for k in _HOLE_WHY if k not in _HOLES]
if _hole_gap or _hole_extra:
    raise SystemExit(
        'asx spec：界内空格与病因表对不上 —— CSV 里扫出来却没写病因的 %s；'
        '写了病因却在 CSV 里不存在的 %s。'
        '前者会让图注宣称「逐格记着」却漏掉一格，后者会替一个不存在的空格背书。'
        '两种都得人来看：先去 fetch/asx.py 的 _KNOWN_SOURCE_GAPS 核对，再改这张表。'
        % (_hole_gap, _hole_extra))

if _HOLES:
    _NOTE_HOLES = (
        f'<b>有 {len(_HOLES)} 处「界内空格」：线在中间断一格，是官方那一期 PDF 自己坏了。</b>'
        + '；'.join(f'<code>{c}</code> 缺 {m}' for c, m in _HOLES)
        + '。病因在 <code>fetch/asx.py</code> 的 <code>_KNOWN_SOURCE_GAPS</code> 里逐格记着，'
          '三处是同一类事故 —— 官方把千分位逗号与小数点印反了：'
        + '；'.join(f'<b>{m}</b> {_HOLE_WHY[(c, m)]}' for c, m in _HOLES)
        + '。<b>但那都不是当期官方公告原值</b>，所以三处一律留空 —— 反推得出就写进去，'
          '往后就再也分不清哪些数是 ASX 印的、哪些是我们凑的。'
          '<b>断一格远好过一个看不出来的错数</b> —— 印错那一格与真值差着一千倍，'
          '画上去要么是一根扎到零的刺，要么把同一张图上别的线整条压平。'
          '<b>上面列出的就是全表仅有的界内空格</b>（这一行不是手写的，是每次出图时'
          '拿 <code>series/asx.csv</code> 逐列现扫出来的）。'
          '<b>另有一处曾经的空格已经补上，值得说清补的是什么：</b>'
          '2017-04 那一期的期货期权小块<b>值列相对标签整体上移了一行</b> —— '
          '已用 PDF 字符坐标坐实是<b>官方排版</b>而非解析顺序问题：那 4 个数与小标题 '
          '<code>Options on futures volume</code> 共处 y=374.23 这条基线，而本该有数的 '
          '<code>Average daily contracts</code>（y=414.43）整行为空。'
          '<b>值印在纸上，只是挂错了标签</b>，所以 2026-08 起由 '
          '<code>fetch/asx.py:_shifted_blocks()</code> 按签名'
          '（小标题行带值 ＋ <code>Average daily contracts</code> 整行为空；'
          # 「只此一处」的判据是拿 fetch 去扫全部 PDF，不是扫 series/asx.csv，
          # 所以现算不了 ⇒ 写成带日期的一次性实测，别让它冒充一个会自己更新的数。
          '2026-08 实测：截至 2026-07 的全段扫描只命中这一处）把值搬回它本该挂的标签，'
          '再拿官方同表印的合计当<b>准入闸门</b>验过才入库：'
          '8,901,810 + 124,649 = 9,026,459、494,545 + 6,925 = 501,470，两条残差都是 0。'
          '<b>入库的 124,649 与 6,925 是官方原值，不是恒等式反推值</b> —— '
          '恒等式在这里当验钞机，不当计算器；验不过就退回留空，不硬写。')
else:
    _NOTE_HOLES = None

SPEC['notes'].append(_NOTE_STARTS)
if _NOTE_HOLES:
    SPEC['notes'].append(_NOTE_HOLES)
