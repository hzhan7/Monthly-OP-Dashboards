# -*- coding: utf-8 -*-
"""联华电子（UMC，2303.TW / NYSE: UMC）单公司页配置。

台湾《证券交易法》要求上市公司次月 10 日前公告上月营收，所以「有没有月度数据」
在台股不是问题。这一页的全部难点在**哪一段月度数据可以当同一个东西读**，逐条实测：

  · **主源是 SEC 6-K，不是公司 IR。** UMC 是 NYSE 上市的外国私人发行人，每月把台湾
    那份营运情形公告原文作为 Exhibit 99.x 附在 6-K 里报到 SEC（EDGAR CIK 1033767）。
    一份附件同时给齐当月 / 去年同月 / 本年累计 / 去年同期累计四个数，带申明用途的
    User-Agent 时 data.sec.gov 与 Archives 实测 100% 成功（一次性拉 372 份零失败）。
    公司自己的 IR 月营收年表挂在 Cloudflare 后面，实测单次成功率 7%–30%，
    只配做偶发回补；IR 上挂的 xlsx 是过期年度快照，不用。

  · **口径连续起点是 2013-01，不是「最早可得」。** EDGAR 上能翻到 2002-02，但 2012 及
    以前那批公告是旧口径：2012 年自己那 12 份公告加总 NT$105,998,159 千元，而 2013 年
    那 12 份公告里印的「去年同期」加总是 NT$115,674,763 千元 —— 后者才是 FY2013 20-F
    审计过的 2012 年合并比较数。差额 9.7% 全部落在同比的分母上，见下面的图注。

  · **月度可加总，逐年 diff 恒为 0。** 13 个完整年度（2013–2025）的月度加总与官方
    年度数逐年相等，11 个季度的月度加总在季报正文里逐字命中，最新月与 TWSE OpenAPI
    逐字相等。UMC 功能货币与表达货币均为新台币，月营收是原生记账数不是折算值 ——
    这一点与世芯-KY（3661）相反，那家十二个月相加与官方本年累计差 +0.378%。
    ⇒ 季度聚合、YTD、TTM 同比在本页全部**合法**。

  · **2019-10 USJC 并表是真断点**，登记进 `breaks`：数据本身没错（合并数就是这么多），
    不可比的是那 12 个月的同比。

本页**不做美元折算腿**：UMC 月度公告只有新台币，20-F 里那一列美元是**便利折算**
（全年一个汇率整列除下来，2025 年是 237,553,199 ÷ 7,572,623 = 31.37），
不是逐月计价，折出来的月度美元营收只能是分析师构造值，没有官方数可以对账。
本页也**没有指引桥**：UMC 法说会给的是 wafer shipments / ASP / 毛利率的环比指引，
不是营收区间，折不成一条能与月度实绩对账的线。
"""

import csv
import os

_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'series', 'umc.csv')

# 官方年度合并营业收入（NT$ 千元）。2013/2014 取自 FY2013、FY2014 20-F 合并综合损益表
# 正文，2015–2024 取自 data.sec.gov XBRL companyfacts 的 ifrs-full:Revenue，
# 2025 取自 FY2025 20-F（2026-04-30 报送）正文。**这是外部对照常量，不是本序列的数**；
# 序列那一侧一律在下面从 CSV 现算，CSV 改了图注跟着改。
_OFFICIAL_FY = {
    2013: 123_811_636, 2014: 140_012_076, 2015: 144_830_421, 2016: 147_870_124,
    2017: 149_284_706, 2018: 151_252_571, 2019: 148_201_641, 2020: 176_820_914,
    2021: 213_011_018, 2022: 278_705_264, 2023: 222_533_000, 2024: 232_302_584,
    2025: 237_553_199,
}
# 2012 年的两个口径（NT$ 千元）：当年自己 12 份公告的加总 vs 2013 年公告里印的比较数
_FY2012_AS_ANNOUNCED = 105_998_159      # 旧口径
_FY2012_RESTATED = 115_674_763          # FY2013 20-F 审计过的合并比较数

# USJC（原三重富士通半导体 MIFS）交割日 2019-10-01，自 2019-10 起 100% 并表
_BREAK_MONTH = '2019-10'


# ══════════════════════════════════════════════════════════════════════════════
# 图注里的数一个都不写死，在 import 期从 series/umc.csv 现算。
# 读不到就退回不含数字的定性版本 —— 缺文件不许在 import 期抛异常，
# 否则 monthly_run 会因为一张页的配置炸掉整批（同 build/specs/guc.py）。
# ══════════════════════════════════════════════════════════════════════════════
def _rows():
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _series():
    """{'YYYY-MM': NT$mn}，只保留读得出数的月份。"""
    out = {}
    for r in _rows():
        try:
            out[r['month']] = float((r['revenue_ntd_mn'] or '').strip())
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _shift(month, k):
    y, m = int(month[:4]), int(month[5:])
    t = y * 12 + m - 1 + k
    return f'{t // 12}-{t % 12 + 1:02d}'


def _annual_check(s):
    """完整年度的月度加总 vs 官方年度：(核过几年, 最大绝对 diff 千元, 最早年, 最晚年)。"""
    ok, worst, yrs = 0, 0.0, []
    for y, official in sorted(_OFFICIAL_FY.items()):
        ms = [f'{y}-{m:02d}' for m in range(1, 13)]
        if not all(m in s for m in ms):
            continue
        got = sum(s[m] for m in ms) * 1000.0          # NT$mn → NT$K
        ok += 1
        yrs.append(y)
        worst = max(worst, abs(got - official))
    return ok, worst, (yrs[0] if yrs else None), (yrs[-1] if yrs else None)


def _yoy_mean(s, start, n=12):
    """从 start 起 n 个月的单月同比均值（%）。样本不齐返回 None。"""
    xs = []
    for k in range(n):
        m = _shift(start, k)
        b = _shift(m, -12)
        if m not in s or b not in s or s[b] <= 0:
            return None
        xs.append((s[m] / s[b] - 1.0) * 100.0)
    return sum(xs) / len(xs)


def _span(s):
    ms = sorted(s)
    return (ms[0], ms[-1], len(ms)) if ms else (None, None, 0)


_S = _series()
_M0, _M1, _MN = _span(_S)
_NYR, _WORST, _Y0, _Y1 = _annual_check(_S)


# ── ① 可加总 / 对账 ────────────────────────────────────────────────────────────
if _NYR:
    _ADDITIVE_NOTE = (
        f'<b>本页的季度聚合、YTD 与 TTM 同比都是合法的（已实测，不是推定）。</b>'
        f'本表 {_M0} 至 {_M1} 共 {_MN} 个月，其中 <b>{_NYR}</b> 个完整年度'
        f'（{_Y0}–{_Y1}）的月度加总与官方年度合并营业收入'
        + (f'<b>逐年 diff = 0</b>' if _WORST < 0.5 else
           f'最大差 {_WORST:,.0f} 千元')
        + '（2013/2014 取自 20-F 正文，2015–2024 取自 SEC XBRL 的 '
          'ifrs-full:Revenue，2025 取自 FY2025 20-F）；抽查 2023Q1–2026Q2 共 11 个季度，'
          '月度加总在对应季报 6-K 正文里逐字命中；最新月与 TWSE OpenAPI '
          't187ap05_L 的「當月營收 / 累計營業收入」逐字相等。'
          'UMC 合并财报的功能货币与表达货币均为新台币，月营收是原生记账数、'
          '不是折算值 —— 与世芯-KY（3661）相反，那家十二个月相加与官方本年累计差 '
          '+0.378%。')
else:
    _ADDITIVE_NOTE = (
        '<b>本页的季度聚合、YTD 与 TTM 同比都是合法的。</b>UMC 的功能货币与表达货币'
        '均为新台币，月营收是原生记账数、不是折算值，月度加总与官方年度、季度可对账。')

# ── ② 起点为什么是 2013-01（2013 那 12 个月公司自己公布的同比是伪值）──────────
_S2013 = sum(_S[f'2013-{m:02d}'] for m in range(1, 13)) * 1000.0 \
    if all(f'2013-{m:02d}' in _S for m in range(1, 13)) else None
if _S2013:
    _fake = (_S2013 / _FY2012_AS_ANNOUNCED - 1.0) * 100.0
    _true = (_S2013 / _FY2012_RESTATED - 1.0) * 100.0
    _START_NOTE = (
        f'<b>序列从 2013-01 起，不是从「最早可得」起 —— 这是刻意的。</b>'
        f'EDGAR 上 UMC 的月营收 6-K 能一直翻到 2002-02，但 2012 及以前那批公告与 2013 起'
        f'不是同一个口径：2012 年当年那 12 份公告加总 NT${_FY2012_AS_ANNOUNCED:,} 千元，'
        f'而 2013 年公告里印的「去年同期」加总是 NT${_FY2012_RESTATED:,} 千元 —— '
        f'后者才是 FY2013 20-F 审计过的合并比较数（2013 起改按合并口径并重述了比较数）。'
        f'后果很具体：本表 2013 年加总 NT${_S2013:,.0f} 千元，'
        f'除当年公布的旧口径基数得 <b>{_fake:+.1f}%</b>，'
        f'除重述后的同口径基数得 <b>{_true:+.1f}%</b>，两者差 '
        f'{abs(_fake - _true):.1f} 个百分点。'
        f'把 2012 直接接上去就是<b>把伪同比当官方值入库</b>，所以本页库里没有 2012，'
        f'页面上 2013 那 12 个月的同比因此是空的 —— 这正是想要的结果。')
else:
    _START_NOTE = (
        '<b>序列从 2013-01 起，不是从「最早可得」起 —— 这是刻意的。</b>'
        '2012 及以前的月度公告是旧口径，2013 起改合并口径并重述了比较数；'
        '直接接上去会把「合并数 ÷ 旧口径数」这个伪同比当成官方值入库。')

# ── ③ USJC 并表断点 ──────────────────────────────────────────────────────────
_IN = _yoy_mean(_S, _BREAK_MONTH)                     # 2019-10 ~ 2020-09
_BEFORE = _yoy_mean(_S, _shift(_BREAK_MONTH, -12))    # 2018-10 ~ 2019-09
_AFTER = _yoy_mean(_S, _shift(_BREAK_MONTH, 12))      # 2020-10 ~ 2021-09
if _IN is not None and _BEFORE is not None and _AFTER is not None:
    _BREAK_NOTE = (
        f'<b>2019-10 起 USJC 并表，那 12 个月的同比含一块无机增量。</b>'
        f'UMC 于 2019-09-25 公告已取得全部政府核准、交割日 2019-10-01，'
        f'三重富士通半导体（MIFS，更名 United Semiconductor Japan Co.）自 2019-10 起 '
        f'100% 并表，公司同期新闻稿自述此举「enhance company’s market share by 10%」。'
        f'本表实测：并表前 12 个月（{_shift(_BREAK_MONTH, -12)} 起）单月同比均值 '
        f'<b>{_BEFORE:+.1f}%</b>，并表当年 12 个月（{_BREAK_MONTH} 起）'
        f'<b>{_IN:+.1f}%</b>，翻过基数之后的 12 个月（{_shift(_BREAK_MONTH, 12)} 起）'
        f'<b>{_AFTER:+.1f}%</b>。数据本身没有问题（合并数就是这么多），'
        f'不可比的是中间那 12 个月的同比 —— 图上的红色竖虚线画在 {_BREAK_MONTH} 的左缘，'
        f'语义是「从这一期起与左侧不可比」。')
else:
    _BREAK_NOTE = (
        '<b>2019-10 起 USJC 并表，那 12 个月的同比含一块无机增量。</b>'
        'UMC 2019-09-25 公告取得全部核准、交割日 2019-10-01，三重富士通半导体（MIFS，'
        '更名 USJC）自 2019-10 起 100% 并表。数据本身没有问题，不可比的是同比。')

# ── ④ 没有美元腿 / 没有指引桥 ─────────────────────────────────────────────────
_NO_USD_NOTE = (
    '<b>本页没有美元腿，是刻意的。</b>UMC 的月度公告只有新台币一个口径；20-F 里那一列'
    '美元是<b>便利折算</b>（全年一个汇率整列除下来：2025 年 237,553,199 ÷ 7,572,623 = '
    '31.37），不是逐月计价，也不是公司按月披露的量。拿月度新台币去除外部汇率得到的'
    '只能是分析师构造值，没有任何官方月度美元数可以对账 —— 与 <code>/tsm/</code> 页不同，'
    '那边公司每季自报美元营收、还用美元给指引。同理，本页不做汇率贡献拆解。')

_NO_GUIDANCE_NOTE = (
    '<b>本页没有指引桥。</b>UMC 法说会给的是下一季的 wafer shipments 环比、ASP（美元）'
    '环比、毛利率与产能利用率，<b>不是营收区间</b>；把三条环比指引乘起来折成营收要先'
    '假设产品结构与汇率，折出来的数没有官方值可以对账。这不是数据缺失而是对象不存在，'
    '所以本页不建 guidance 序列，也不拼「当季 QTD 距指引中值还差多少」那类句子。')

# ── ⑤ 数据源与落库口径 ───────────────────────────────────────────────────────
_SRC_NOTE = (
    '<b>数据源与落库口径。</b>主源是 SEC EDGAR 上 UMC 的 6-K 附件（CIK 1033767），'
    '即台湾月度营运情形公告的英文原文；序列存两列：当月净销售额与<b>公司自己公布的'
    '本年累计</b>。存累计不是冗余 —— 公司印错过单月数：2016-05 那份公告印的是 '
    '17,705,227 千元，而本年累计差（57,873,709 − 45,168,482 = 12,705,227）、'
    '同一行的变动额（−225,827）、以及一年后公告里的「去年同月」栏三路一致指向 '
    '12,705,227，印出来那个数是把 1 打成 7 的手误。因此本页所有月份的金额一律由'
    '<b>累计差反算</b>，并用变动额栏仲裁；163 个月里只此一处四路读数不一致。'
    '同类的还有月份标签本身：2015-02 那份的行标签印成 “January”、2016-01 那份印成 '
    '“December”、2021-12 与 2022-12 两份的抬头年份各少写一年 —— 所以判月只认累计链，'
    '不认标签。')

SPEC = {
    'ticker': 'umc',
    'name':   'UMC',
    'title':  '联华电子（UMC，2303.TW）月度营收',
    'csv':    'umc.csv',
    'ccy':    'TWD',
    'source': 'Source: UMC monthly net sales announcements filed with the SEC on '
              'Form 6-K (EDGAR CIK 1033767), reconciled to 20-F consolidated '
              'statements and cross-checked against TWSE OpenAPI t187ap05_L; '
              'format after Goldman Sachs GIR',

    # 头条只有一列：台股月营收披露就是一个数，UMC 月度不拆制程、不拆地区、不拆客户。
    # 163 个月（2013-01 起）远超底座要求的 24 个月共同历史。
    'headline': [
        {'col': 'revenue_ntd_mn', 'zh': '月营收', 'unit': 'NT$mn', 'fmt': 'f0c'},
    ],

    # 刻意留空：本页只有一条真序列。CSV 里的 revenue_ytd_ntd_mn 是「本年累计」，
    # 与月营收同源同量纲，画出来是一条每年 1 月归零的锯齿 —— 它的用途是让
    # fetch/umc.py 用累计差反算单月并逐月自检（见 _SRC_NOTE），不是给人看的图。
    # 把它塞进 groups 只会多一张没有信息的图，外加一条口径可疑的次轴同比。
    'groups': [],

    # 次轴走 12 个月滚动同比而不是单月同比：台股月营收同时受工作日数、农历年错位
    # （1/2 月之间每年摆动）与晶圆代工出货节奏推动，单月同比的毛刺可以大到与趋势
    # 符号相反。granularity='monthly_total' —— 这一列本身就是当月合计，不是日均。
    'ttm_yoy': [{
        'zh': '月营收',
        'granularity': 'monthly_total',
        'level': {'col': 'revenue_ntd_mn', 'zh': '月营收',
                  'unit': 'NT$mn', 'fmt': 'f0c'},
    }],

    # 断点写成字面量而不是指向 series/umc_breaks.csv：本家只有一条断点，
    # 而且它由一次公司行为（2019-10-01 交割）唯一确定，不会跟着数据长。
    'breaks': [{'month': _BREAK_MONTH,
                'zh': 'USJC（原三重富士通半导体 MIFS）100% 并表，'
                      '2019-10~2020-09 的同比含无机增量'}],

    'notes': [_ADDITIVE_NOTE, _START_NOTE, _BREAK_NOTE,
              _NO_USD_NOTE, _NO_GUIDANCE_NOTE, _SRC_NOTE],
}
