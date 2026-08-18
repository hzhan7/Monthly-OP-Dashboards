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

━━ 有意不上页面的列，以及理由 ━━
· contracts_spi200_futures / oi_spi200_futures / contracts_3y_bond_futures /
  oi_3y_bond_futures / contracts_10y_bond_futures / oi_10y_bond_futures /
  contracts_90d_bankbill_futures / oi_90d_bankbill_futures
  —— **series 里目前只有 2026-06 与 2026-07 两个月**，两个点画不出任何时序图，
  放上页面只会让人以为「ASX 的国债期货是 2026 年才有的」。
  ⚠️ **理由到此为止 —— 「不可回补」那句已被实测推翻，别再拿它当结论。**
  旧注释（与 docs/verify/asx.md 口径坑 8）说「官方只保留最近 2 期，更早的直链一律 404」。
  2026-08 实测：MAR 正文里印的那条链接，2020-06…2026-07 共 74 期**全部 200 +
  application/pdf**，且用未改动的 `asx.parse_sfe` 全部解析成功。真正卡住的是抓取器 ——
  `fetch/asx.py:_SFE_LINK` 的文件名日期写死了 8 位数字，而官方 2020-06…2026-05
  一直用 6 位（YYMMDD 与 DDMMYY 交替），只有 2026-06 起才是 8 位。
  ⇒ 这 8 列是 **fetcher_window，不是 source_hard**；官方源的天花板是 2020-06
  （2016-10…2020-05 只在 Wayback 有，属第三方存档，是否破例要用户拍板；
  2016-01…2016-09 官方与 Wayback 都没有，那几期 MAR 正文本就没印分品种链接）。
  回补这 8 列的工作**本轮没做**（本轮的目标是主体回到 2016-01，而这 8 列无论如何
  到不了 2016-01，起点会与全页差 53 个月）。谁来做都要连带重写 build/pools.py:1292
  把 asx 排除出利率衍生品池的那条理由。
  ⇒ 在此之前，本页的期货口径只到 ASX 24 合计（adv_futures_contracts）。
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
    """本页真正上图的列（headline + groups + decomp + ttm_yoy 里出现过的 col）。

    SPEC 还没构造出来，所以不能从 SPEC 里读；但也不该手抄一份清单 —— 手抄的清单
    与 groups 分家的那天，图注就开始说另一张图的事。折中：**在 SPEC 组装完之后**
    由 `_scan_spec_cols()` 回填，本函数只在那之前给个空清单用。
    """
    return _PAGE_COLS


_PAGE_COLS = []


def _late_starts():
    """上页面的列里，起点晚于全页首月的那些 —— (列名, 首月, 晚了几个月)。

    回补一次历史，这张清单就会变长：2026-08 之前只有 3 列晚于首月，回补到 2016-01
    之后变成 9 列。写死一句「VIX 起点比主体晚 24 个月」那样的话必然过期，所以现算。
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


_PTN, _PTMED, _PTMAX, _PTONM = _per_trade_check()
_FY0, _FY1, _FYL, _FYA, _FYB = _fy_probe()
_DMIN, _DMAX, _DSPR = _tradingday_spread()
_MSG_STEP = _msg_precision_step()


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
    # 自 series 首月起逐月无洞（2026-08 回补到 2016-01 后实测 127/127，
    # 「无洞」这个断言由 build/verify_pages.py 每次构建复核，这里不再抄写月数），
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

        # 官方到 2019-10 才开始印这一行，起点比页面主体晚 45 个月（现算，见 _span_zh）。
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
        '的月度序列 —— series/asx.csv 里目前只有 2026-06 与 2026-07 两个月，画不出时序。'
        '过去这里写的理由是「官方只保留最近 2 期、更早的一律 404 且不可回补」，'
        '**那句话 2026-08 已被逐期实发 HTTP 证伪**：分品种报告 2020-06 至今共 74 期'
        '全部可下载并解析，卡住的是抓取器里写死 8 位日期的文件名正则'
        '（官方 2020-06…2026-05 用的是 6 位）。回补这 8 列是待办事项，不是不可能；'
        '官方源的天花板是 2020-06，仍比本页主体晚 53 个月，所以补上之后也要单独标起点。',

        '本页全部金额为澳元。跨币种比较由 build/notional.py 统一换算：'
        '流量（ADT、成交额、融资额、当月清算额）配月均汇率，'
        '存量（月末未平仓名义额、托管市值、保证金、实体数）配月末汇率。',

        '未上页面的月频列：trading_days_cash / trading_days_futures / trading_days_eto'
        '（三套分母，2026-04 实测分别是 19 / 20 / 19）、'
        '以及五条 contracts_*_total 月总量列（= ADV × 对应交易日，与 adv_* 重复）。',

        # ⚠️ 另有两条随 CSV 现算的图注（「起点不齐的列」与「界内空格」）在 SPEC
        #    组装完之后追加，见文件末尾 —— 它们要先知道本页到底上了哪些列。

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
# 得先知道 groups / decomp / ttm_yoy 里到底出现了哪些 col。手抄一份列清单是可以，
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
    for t in spec.get('ttm_yoy', []):
        add((t.get('level') or {}).get('col'))
        add(t.get('total_col'))
    return out


_PAGE_COLS[:] = _scan_spec_cols(SPEC)
_FIRST, _LATE = _late_starts()
_HOLES = _interior_holes()

if _LATE:
    _NOTE_STARTS = (
        f'<b>本页各图的窗口都自 {_FIRST} 起，但线不都从左边缘开始。</b>'
        f'ASX 是逐年往月报里加行的，所以有 {len(_LATE)} 列的官方披露起点晚于本页首月，'
        f'在图上表现为「同一张图里两条线起点不同」或「左边一段没有柱」——'
        f'那是<b>官方当时没印这一行</b>，不是我们漏抓，更不能拿别的列相加去补：'
        + '；'.join(f'<code>{c}</code> 自 {a} 起（晚 {n} 个月）' for c, a, n in _LATE)
        + '。其中 <code>value_cash_onmarket_audbn</code>（仅场内成交额）最容易被误会：'
          '它可由「连续竞价 + 集合竞价 + Centre Point」三项相加倒推'
          '（2017-09 算出来 80.829，与官方 2017-10 首次印出的 80.296 量级一致），'
          '但那是派生量，写进 series 就再也分不清哪个数是 ASX 印的、哪个是我们算的，'
          '所以留空。<b>要看不受起点影响的现货口径，用「含场外报告」那条线。</b>')
else:
    _NOTE_STARTS = ('本页各图的窗口自序列首月起，且每一列都从窗口左边缘就有值。')

if _HOLES:
    _NOTE_HOLES = (
        f'<b>有 {len(_HOLES)} 处「界内空格」：线在中间断一格，是官方那一期 PDF 自己坏了。</b>'
        + '；'.join(f'<code>{c}</code> 缺 {m}' for c, m in _HOLES)
        + '。两处的病因都在 <code>fetch/asx.py</code> 的 <code>_KNOWN_SOURCE_GAPS</code> '
          '里逐格记着：2017-04 那一期的期货期权小块<b>值列整体上移了一行</b>（值落空）；'
          '2016-09 那一期把每笔均值的千分位逗号<b>印成了小数点</b>（4.852 应为 4,852）。'
          '两格的真值都能算出来（前者由官方同表的合计相减、后者由成交额 ÷ 笔数或'
          '看下一年同期报告的 pcp 列），但那都不是<b>当期官方公告原值</b>，'
          '所以一律留空。<b>断一格远好过一个看不出来的错数</b> —— '
          '尤其 2016-09 那个错值只有真值的千分之一，画上去是一根扎到零的刺。')
else:
    _NOTE_HOLES = None

SPEC['notes'].append(_NOTE_STARTS)
if _NOTE_HOLES:
    SPEC['notes'].append(_NOTE_HOLES)
