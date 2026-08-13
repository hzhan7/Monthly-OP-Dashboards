# -*- coding: utf-8 -*-
"""世芯-KY（Alchip，3661.TW）单公司页配置。

台湾《证券交易法》要求上市公司次月 10 日前公告上月营收，所以「有没有月度数据」在台股
不是问题。世芯特殊在**它的功能货币是美元**：MOPS 那张月营收表有两栏，
「新台幣」与「功能性貨幣(美金)」，官方自己在页脚写明

    註1: 本月新台幣營業收入淨額＝本月功能性貨幣營業收入淨額×本月換算匯率

也就是说，**新台币那一栏是逐月折算出来的**，不是原生记账数。三个后果，逐条实测过：

  · **新台币月值不可加总。** 各月用各月的汇率，12 个月相加 ≠ 官方「本年累计」
    （后者 = 累计美元 × 累计换算汇率）。2025 年这个缺口是 +0.378%，2022 年 +0.719%。
    同一检验在美元列上是 0（151 个月里全年残差不超过 ±0.02 US$仟元 = ±$20）。
    ⇒ **主序列、头条、滚动同比全部走美元列**；新台币列留在页面上只为了跟 TWSE
    与媒体报的那个数逐格对账。本文件的图注把这两条实测数在 import 期从 CSV 现算。

  · **对照组是创意 GUC（3443）**：那家合并财报附注写明功能货币与表达货币都是新台币，
    月营收是原生记账数，逐月加总与审计年报 diff 恒为 0（见 build/specs/guc.py）。
    同一张台股月营收表，两家能不能加总是相反的 —— 这不是精度问题，是记账货币问题。

  · **不做美元折算腿，也不做汇率贡献拆解。** 本页的美元数是**公司自己申报的功能货币
    实绩**，不是拿外部牌价折出来的；反过来把新台币除以 H.10 / 台银月均汇率会得到一个
    对不上官方任何一个数的第四口径。汇率在这里是恒等式的一条腿，不是可归因的驱动因子。

━━ 📌 序列从 2014-01 起，不是「最早可得」━━━━━━━━━━━━━━━━━━━━━━━━━━━
MOPS 的 IFRS 接口能查到 2013-01，旧接口能查到 2011-07。不取的理由是**美元栏的精度**：
2013 及以前美元值被舍入到整数仟元，于是 12 个月相加与官方累计差 +330 ppm；
2014 起是两位小数，同一检验是 −0.065 ppm，相差 5,000 倍 —— 本页最核心的那句
「美元列可加总」在 2013 段落上就不成立了。换算汇率同期也从 2–3 位小数变成 4 位。
再往前 2013-01 还压着 ROC GAAP → Taiwan-IFRSs 的准则断点，而准则之前那一段有真重述
（2011-12 当时申报 NT$336,689，一年后被列成 NT$328,443，−2.4%）。
断点落在序列第 0 格，底座对第 0 格断点不画线，所以这里**不设 `breaks`**，改写进页尾。

━━ 📌 本页没有公告日，也不该有 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
世芯**不发月营收新闻稿**（官网新闻中心只有季报与公司新闻）、MOPS 重大讯息
（t187ap04_L）里 3661 零条、月营收接口本身不带申报时间戳。t21sc03 静态页的
HTTP `Last-Modified` 是 MOPS 批量重生成历史文件的时刻，不是公告日。
⇒ `series/source_dates.csv` 没有 alchip 行，抬头就不印「官方发布于 X」。
这是一等状态，不是待补的缺口 —— **不要**拿 TWSE OpenAPI 的「出表日期」或抓取时刻顶上。

━━ 📌 本页没有指引桥 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
世芯只在季度法说会给定性展望，不公布数字财测。同 GUC，这里是对象不存在，不是数据缺失。
"""

import csv
import os

_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'series', 'alchip.csv')


# ══════════════════════════════════════════════════════════════════════════════
# 图注里的数一个都不写死，在 import 期从 series/alchip.csv 现算。
# 读不到就退回不含数字的定性版本 —— 缺文件不许在 import 期抛异常，
# 否则 monthly_run 会因为一张页的配置炸掉整批（同 build/specs/guc.py）。
# ══════════════════════════════════════════════════════════════════════════════
def _rows():
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _f(r, col):
    try:
        return float((r[col] or '').strip())
    except (KeyError, AttributeError, TypeError, ValueError):
        return None


def _span():
    ms = [r['month'] for r in _rows() if _f(r, 'revenue_usd_mn') is not None]
    return (ms[0], ms[-1], len(ms)) if ms else (None, None, 0)


def _identity():
    """官方页脚那条恒等式的实测残差：(最大偏差 bp, 出现在哪个月, 样本数)。"""
    worst, at, n = 0.0, None, 0
    for r in _rows():
        ntd, usd, fx = _f(r, 'revenue_ntd_mn'), _f(r, 'revenue_usd_mn'), _f(r, 'fx_ntd_per_usd')
        if not (ntd and usd and fx):
            continue
        n += 1
        bp = abs(ntd - usd * fx) / ntd * 1e4
        if bp > worst:
            worst, at = bp, r['month']
    return worst, at, n


def _additivity():
    """逐个完整年度：12 个月相加 vs 官方「本年累计」。

    返回 (年度明细 list[(年, 新台币缺口%, 美元残差 ppm)], 新台币缺口最大的那一年,
          美元残差绝对值最大的 ppm)。年内缺月的年度直接跳过。
    """
    by = {}
    for r in _rows():
        m = r.get('month') or ''
        if len(m) != 7:
            continue
        by.setdefault(m[:4], []).append(r)
    rows = []
    for y, rs in sorted(by.items()):
        if len(rs) != 12:
            continue
        dec = rs[-1]
        off_u, off_n = _f(dec, 'ytd_revenue_usd_mn'), _f(dec, 'ytd_revenue_ntd_mn')
        su = sum(_f(r, 'revenue_usd_mn') or 0.0 for r in rs)
        sn = sum(_f(r, 'revenue_ntd_mn') or 0.0 for r in rs)
        if not (off_u and off_n):
            continue
        rows.append((y, (sn - off_n) / off_n * 100.0, (su - off_u) / off_u * 1e6))
    if not rows:
        return [], None, 0.0
    worst_n = max(rows, key=lambda t: abs(t[1]))
    worst_u = max(abs(t[2]) for t in rows)
    return rows, worst_n, worst_u


def _fx_span():
    xs = [_f(r, 'fx_ntd_per_usd') for r in _rows()]
    xs = [x for x in xs if x]
    return (min(xs), max(xs)) if xs else (None, None)


def _mom_vs_ttm(col):
    """这一列的单月同比 vs 12 个月滚动合计同比：符号相反的月份数、总样本、差得最远的那个月。

    只用来给「为什么这张图偏离默认口径」那段图注现算数字（CONTRACT §6.1 第 2 条要求
    理由由**本序列自己**实测，不许引别家的例子）。算法与 build/yoy.py 同口径：
    滚动同比 = 近 12 个月合计 ÷ 上一个 12 个月合计 − 1。
    """
    rs = _rows()
    xs = [(r['month'], _f(r, col)) for r in rs]
    xs = [(m, v) for m, v in xs if v is not None]
    if len(xs) < 25:
        return 0, 0, None, None, None
    vals = [v for _, v in xs]
    flip, n, worst = 0, 0, (0.0, None, None, None)
    for i in range(24, len(xs)):
        b = vals[i - 12]
        if not b:
            continue
        mom = (vals[i] / b - 1) * 100.0
        cur = sum(vals[i - 11:i + 1])
        pre = sum(vals[i - 23:i - 11])
        if not pre:
            continue
        ttm = (cur / pre - 1) * 100.0
        n += 1
        if mom * ttm < 0 and abs(mom) > 0.5 and abs(ttm) > 0.5:
            flip += 1
            if abs(mom - ttm) > worst[0]:
                worst = (abs(mom - ttm), xs[i][0], mom, ttm)
    return flip, n, worst[1], worst[2], worst[3]


def _latest_mom(col):
    """最新月的单月同比（%）—— 就是 MOPS 表里「去年同月增減(%)」那一格。"""
    xs = [(r['month'], _f(r, col)) for r in _rows()]
    xs = [(m, v) for m, v in xs if v is not None]
    if len(xs) < 13 or not xs[-13][1]:
        return None, None
    return xs[-1][0], (xs[-1][1] / xs[-13][1] - 1) * 100.0


_M0, _M1, _MN = _span()
_ID_BP, _ID_AT, _ID_N = _identity()
_ADD_ROWS, _ADD_WORST, _ADD_USD_PPM = _additivity()
_FX_LO, _FX_HI = _fx_span()
_FLIP, _FLIP_N, _FLIP_AT, _FLIP_MOM, _FLIP_TTM = _mom_vs_ttm('revenue_ntd_mn')
_LAST_M, _LAST_MOM = _latest_mom('revenue_ntd_mn')


# ── note 1：为什么主序列是美元 ────────────────────────────────────────────
if _ADD_ROWS:
    _yrs = '、'.join(f'{y} {gap:+.3f}%' for y, gap, _ in _ADD_ROWS[-4:])
    # 「小几个数量级」不写死：新台币最大缺口（%→ppm）÷ 美元最大残差（ppm）现算。
    # _ADD_USD_PPM 恰好为 0 时不做除法（import 期不许抛异常）。
    _ADD_RATIO = (f'量级上比新台币那边小 {abs(_ADD_WORST[1]) * 1e4 / _ADD_USD_PPM:,.0f} 倍'
                  if _ADD_USD_PPM else '新台币那边的缺口则大它若干个数量级')
    _CCY_NOTE = (
        '<b>本页的主口径是美元，不是新台币 —— 因为新台币月值不可加总。</b>'
        '世芯的功能货币是美元，MOPS 月营收表里的新台币栏是逐月折算值，官方页脚写明'
        '「本月新台幣營業收入淨額＝本月功能性貨幣營業收入淨額×本月換算匯率」。'
        f'各月用各月的汇率，于是把 12 个月的新台币相加不等于官方的「本年累计」：'
        f'本表 {len(_ADD_ROWS)} 个完整年度里缺口最大的是 <b>{_ADD_WORST[0]} 年 '
        f'{_ADD_WORST[1]:+.3f}%</b>，最近四年分别是 {_yrs}。'
        f'同一检验在<b>美元列</b>上，{len(_ADD_ROWS)} 年里残差最大的一年也只有 '
        f'<b>{_ADD_USD_PPM:.3f} ppm</b>（百万分之零点几，纯粹是官方累计栏两位小数的舍入 —— '
        f'{_ADD_RATIO}）。'
        '所以头条、全历史图、季节性与 12 个月滚动同比全部走美元列；'
        '新台币列只画在下面那张对账图上。')
else:
    _CCY_NOTE = (
        '<b>本页的主口径是美元，不是新台币 —— 因为新台币月值不可加总。</b>'
        '世芯的功能货币是美元，MOPS 月营收表里的新台币栏是逐月折算值，'
        '各月用各月的汇率，12 个月相加不等于官方的「本年累计」；美元列则逐年相等。'
        '所以头条与滚动同比走美元列，新台币列只用于与官方披露对账。')

# ── note 2：恒等式 ────────────────────────────────────────────────────────
if _ID_N:
    _IDENTITY_NOTE = (
        '<b>三列之间是一条恒等式，不是三条独立估计。</b>'
        '<code>revenue_ntd_mn ≡ revenue_usd_mn × fx_ntd_per_usd</code> —— '
        f'本表 {_ID_N} 个月逐月核过，最大偏差 <b>{_ID_BP:.4f} 个基点</b>'
        f'（{_ID_AT}），机理是官方换算汇率只给 4 位小数（0.5×10⁻⁴ ÷ 30 ≈ 0.17bp），'
        '不是数据分歧。抓取模块把这条恒等式当硬护栏：超过 1 个基点就抛异常、当月不写入，'
        '因为「解析串位」「MOPS 改版把两栏对调」这类故障恰好会在这里露出来。'
        f'汇率本身在本表区间内从 {_FX_LO:.2f} 走到 {_FX_HI:.2f} NT$/US$。')
else:
    _IDENTITY_NOTE = (
        '<b>三列之间是一条恒等式，不是三条独立估计。</b>'
        '<code>revenue_ntd_mn ≡ revenue_usd_mn × fx_ntd_per_usd</code>，'
        '由官方在月营收表页脚给出；抓取模块逐月核验，超过 1 个基点就抛异常、当月不写入。')

# ── note 3：起点 ──────────────────────────────────────────────────────────
_START_NOTE = (
    f'<b>序列从 {_M0 or "2014-01"} 起，是口径连续的最早月份，不是最早可得。</b>'
    'MOPS 的 IFRS 接口能查到 2013-01、旧接口能查到 2011-07，不取的理由是美元栏的精度：'
    '2013 及以前美元值被舍入到整数仟元，12 个月相加与官方累计差 +330 ppm，'
    '2014 起是两位小数、同一检验差 −0.065 ppm；换算汇率同期也从 2–3 位小数变成 4 位。'
    '再往前 2013-01 压着 ROC GAAP → Taiwan-IFRSs 的准则断点，而准则之前那一段有真重述'
    '（2011-12 当时申报 NT$336,689 仟元，一年后在 2012-12 那期被列成 NT$328,443，−2.4%）。'
    '2012-01 起「去年同期」与上一年「本月」逐月相等，本序列范围内零重述。'
    '这个断点落在序列第 0 格，底座对第 0 格断点不画线，所以本页不设断点竖线。')

# ── note 4：年度口径有三个数 ──────────────────────────────────────────────
_ANNUAL_NOTE = (
    '<b>年度数有三个，别混着用。</b>①「12 个月相加」（本页核对表可以自己加出来的那个）；'
    '②「官方本年累计」= 累计美元 × 累计换算汇率，实测逐年与①差几十个基点；'
    '③ 审计年报的「營業收入合計」，与②再差 −0.14% ~ +0.02%（2025 年 −0.0054%、'
    '2024 年 +0.0158%、2023 年 −0.0058%），因为财报按实际交易汇率逐笔换算、'
    '月报按平均汇率换算。三者都对，指代的量不同。'
    '审计年报层面无重述：2019–2025 每一年的「去年度」比较列与上一年自己的数逐字相等。'
    '本页只画月度，不做季度聚合与 YTD —— 那两样在新台币口径上会把上面那个缺口放大成结论。')

# ── note 5：没有公告日、没有指引 ──────────────────────────────────────────
_NO_DATE_NOTE = (
    '<b>本页抬头没有「官方发布于 X」，是刻意留白。</b>世芯不发月营收新闻稿'
    '（官网新闻中心只有季报与公司新闻）、MOPS 重大讯息里 3661 零条、月营收接口本身'
    '不带申报时间戳；t21sc03 静态页的 HTTP <code>Last-Modified</code> 是 MOPS 批量重生成'
    '历史文件的时刻（2013-01 那张显示 2026-08-12），不是公告日。'
    '公告日缺席在这里是一等状态，不是待补的缺口，所以不拿「出表日期」或抓取时刻顶上。'
    '另外，公司只在季度法说会给定性展望、不公布数字财测，所以本页也没有指引桥。')

# ── note 6：两张图为什么偏离默认口径用单月同比 ────────────────────────────
_MOM_NOTE = (
    '<b>两张图的次轴刻意用单月同比，理由不是「更灵敏」。</b>本页默认口径是 12 个月滚动'
    '同比（CONTRACT §6.1 第 1 条），偏离的两处都已写进图题：'
    '① <b>新台币折算值那张</b>的命题就是「与官方披露逐格对账」，而 MOPS 月营收表自己印的'
    '「去年同月增減(%)」就是单月数'
    + (f'（{_LAST_M} 那格是 {_LAST_MOM:+.2f}%）' if _LAST_MOM is not None else '')
    + '，改成滚动口径这张图就对不上它要对的那张表了；'
      '② <b>换算汇率那张</b>画的是价格型序列，把 12 个月的汇率相加不指代任何真实存在的量'
      '（同 CONTRACT §6.1 第 4 条对存量的论证），点对点同比是它唯一的合法口径。'
    + (f'单月毛刺是真的：新台币列 {_FLIP_N} 个可比月里有 <b>{_FLIP} 个月</b>'
       f'与滚动口径<b>符号相反</b>，差得最远的是 {_FLIP_AT}'
       f'（单月 {_FLIP_MOM:+.1f}% vs 滚动 {_FLIP_TTM:+.1f}%）。' if _FLIP else '')
    + '所以趋势判断请看本页最后一张图的金色滚动折线，不要拿这两张的次轴去比增速。')

# ── note 7：数据源 ────────────────────────────────────────────────────────
_SRC_NOTE = (
    '<b>数据源与交叉核对。</b>三列全部来自 MOPS 公开资讯观测站「采用 IFRSs 后之月营业'
    '收入资讯」（<code>t05st10_ifrs</code>）的同一张表，一次一个月，原值 ÷1000 换单位、'
    '不做任何自算换算。<b>「功能性貨幣(美金)」这一栏全网只有这里有</b> —— TWSE OpenAPI、'
    'TPEx OpenAPI、MOPS 全市场汇总表与公司官网一律只给新台币。'
    '新台币列每月与两个独立源交叉核对：TWSE OpenAPI <code>t187ap05_L</code>（当期一份'
    '全市场 JSON，3661 在里面）与 MOPS 全市场月报静态页 <code>t21sc03_&lt;民國年&gt;_'
    '&lt;月&gt;_1.html</code>（后缀 <code>_1</code> = 外國公司 93 家，'
    '<code>_0</code> = 國內公司 983 家；世芯是开曼注册的 KY 外国发行人，'
    '用错后缀会整家静默漏掉；文件是 big5 编码）。')


SPEC = {
    'ticker': 'alchip',
    'name':   'Alchip',
    'title':  '世芯-KY（Alchip，3661.TW）月度营收',
    'csv':    'alchip.csv',
    'ccy':    'USD',                 # 功能货币；新台币在本页是折算腿，不是本币
    'source': 'Source: Taiwan MOPS monthly revenue filing for Alchip Technologies '
              '(3661.TW), functional-currency (USD) column; cross-checked against '
              'TWSE OpenAPI t187ap05_L and MOPS market-wide t21sc03 (foreign issuers); '
              'format after Goldman Sachs GIR',

    # 头条只有一列：台股月营收披露就是一个数，而对世芯来说那个数应当用美元读。
    # 151 个月（2014-01 起）远超底座要求的 24 个月，同比与 3Y 分位都算得出来。
    'headline': [
        {'col': 'revenue_usd_mn', 'zh': '月营收（美元）', 'unit': 'US$mn', 'fmt': 'f1'},
    ],

    'groups': [
        # 新台币折算值单独成图：它与头条不同单位，本来就不该共轴；
        # 更重要的是它是**对账用**的一列 —— 读者拿它去对 TWSE 与媒体报的那个数。
        #
        # 这两张图的次轴都是**单月同比**，与本页默认的滚动口径相反，所以按 CONTRACT §6.1
        # 第 2 条把「单月同比」写进组名（组名 = 图题前半段）。理由各不相同，见 _MOM_NOTE：
        # 前者是要跟官方表上那个单月百分比逐格对上，后者是汇率不能做滚动合计。
        {'zh': '新台币折算值：与 TWSE / MOPS 官方披露逐格对账（次轴为单月同比，同官方表口径）',
         'cols': [
             {'col': 'revenue_ntd_mn', 'zh': '月营收（新台币）',
              'unit': 'NT$mn', 'fmt': 'f0c'},
         ]},
        # 恒等式的第三条腿。放上来是为了让「为什么新台币不可加总」在页面上看得见，
        # 而不是只在图注里说一句。
        {'zh': 'MOPS 当月换算汇率：新台币月营收 ≡ 美元月营收 × 它（次轴为单月同比）',
         'cols': [
             {'col': 'fx_ntd_per_usd', 'zh': '当月换算汇率',
              'unit': 'NT$/US$', 'fmt': 'f2'},
         ]},
    ],

    # 次轴走 12 个月滚动同比而不是单月同比：台股月营收受工作日数、农历年错位与
    # ASIC 量产/NRE 里程碑三重推动，单月同比的毛刺可以大到与趋势符号相反。
    # 本列（revenue_usd_mn）实测：2026-02 单月 −76.1%（滚动 −47.1%）、
    # 2026-07 单月 +156.4% 而滚动 −37.3% —— 同一条业务线，两种口径符号相反。
    # （注意别把新台币列的 +181.8% 记到这一列头上，那是折算腿的数。）
    # granularity='monthly_total' —— 这一列本身就是当月合计，不是日均。
    'ttm_yoy': [{
        'zh': '月营收（美元）',
        'granularity': 'monthly_total',
        'level': {'col': 'revenue_usd_mn', 'zh': '月营收（美元）',
                  'unit': 'US$mn', 'fmt': 'f1'},
    }],

    'notes': [_CCY_NOTE, _IDENTITY_NOTE, _START_NOTE, _ANNUAL_NOTE,
              _MOM_NOTE, _NO_DATE_NOTE, _SRC_NOTE],
}
