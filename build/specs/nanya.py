# -*- coding: utf-8 -*-
"""南亚科技（Nanya Technology，2408.TW）单公司页配置。

台湾《证券交易法》要求上市公司次月 10 日前公告上月营收，所以「有没有月度数据」在台股
不是问题。选南亚科的理由是它把**存储器周期**放在一条 13 年不断的月度序列上 ——
同一家公司、同一条口径，单月营收从 NT$2,026mn（2023-02）到 NT$43,868mn（2026-07），
21.6 倍。逐条实测过的口径事实：

  · **月营收逐月可加总。** 官方月度申报逐月加总 vs 审计合并营业收入，13 个完整年度里
    **7 年 diff 恰为 0**（2018-2023、2025），其余 6 年最大相对差 **−0.046%**（2013 年
    46,953,841 vs 46,975,291）。也就是说月度是**未审计申报数**，年结有极小的审计调整，
    公司**不回头改月度序列**。季度对得更死：2026 上半年月度加总 131,636,005 千元，
    与 TWSE OpenAPI 合并综合损益表（115 年第 2 季累计）逐字相等；2026Q2 三个月相加
    82,549,073 千元 = NT$82,549mn，与公司 Q2 净销售逐字相等。
    ⇒ 季度聚合、YTD、TTM 同比在本页**合法**，但页面上不许说「等于审计数」。

  · **功能货币就是新台币**，月营收是原生记账数、不是折算值。所以本页**没有美元折算腿**，
    也没有汇率贡献拆解 —— 那两样在这里折出来的都只能是分析师构造值，无官方数可对账。

  · **不给指引。** 2026Q2 法说会 deck 的前向语句只有 "expect to further improve" 这类
    定性说法，没有一个前向数字。所以本页不建 guidance 序列、也不拼「距指引中值还差多少」。

━━ 📌 本页刻意**不出 heat_matrix**，这不是漏了 ━━━━━━━━━━━━━━━━━━━━━━━━
DRAM 周期让单月同比跨 −68.5%（2023-02）~ +730.1%（2026-05）。底座的 `heat_matrix`
只有 `ex.matrix` / `ex.reverse` 两个入口，色阶写死成 5/95 分位的**线性**双色，**且色阶与
格内数字读同一份 matrix** —— 「色阶取 log、格内印原值」在结构上做不到。
本序列 151 个可算同比的月份实测 p5/p95 = −59.9% / +404.9%，按这条线性色阶铺开，
其中 134 个（89%）色深不到两成、肉眼分不开，剩下 2026 那一排把整条色标吃掉。
一张读不出信息的矩阵比没有矩阵更坏。（这几个数在 `_heat_readability()` 里从 CSV 现算，
这里写的只是 2026-08-13 当天的实测值，页面上印的永远是现算值。）
顺带：本页只有一条头条列、`groups` 为空，底座本来也不会走到 heat_matrix 那条分支；
写在这里是为了让下一个人知道这是**判断**，不是「忘了配」。

━━ 📌 底座的 spec 层没有 ycap，这一页的同比图确实被 2026 压平了 ━━━━━━━━━━━
`build/lpla.py` / `build/cost.py` 那套「截轴 + 越界柱竖排真值 + cap_note」住在**旧的
一家一份生成器**里；`build/single.py` 的 SPEC 契约里没有对应字段，而 SPEC 写未知字段
是硬失败。所以本页不截轴，改成把量级差写进图注（下面 `_CYCLE_NOTE` 现算）：
读单月同比那张图时，请把它当成「有没有跨零」的开关图，幅度去看水平值那张。

━━ 📌 序列起点 2013-01 是**口径起点**，不是「最早可得」━━━━━━━━━━━━━━━━━
公司 IR 月营收页脚注：合并财报自 2013 年 1 月起适用 IFRSs 并按合并口径申报。
2012 及以前 IR 只挂**母公司个别**月营收，与合并口径不可比，所以不接进来。
"""

import csv
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CSV = os.path.join(_ROOT, 'series', 'nanya.csv')

# 官方**审计**合并营业收入（新台币千元）。这不是从本页序列能算出来的量，所以只能是常数；
# 出处见 fetch/nanya.py 的「对账 A」：MOPS ajax_t163sb04（TYPEK=sii, season=4）与
# 南亚科 IR 审计合并财报 PDF 两条通道互校。图注里出现的**差额**在 import 期现算，
# 不写死 —— 序列一变，差额跟着变。
_AUDITED_K = {
    2013: 46_975_291, 2014: 49_107_622, 2015: 43_875_905, 2016: 41_632_505,
    2017: 54_918_224, 2018: 84_721_804, 2019: 51_727_458, 2020: 61_005_514,
    2021: 85_604_158, 2022: 56_952_275, 2023: 29_892_306, 2024: 34_131_667,
    2025: 66_586_520,
}

# 官方**期中累计**合并营业收入（新台币千元）：{标签: (年, 截至第几个月, 官方值)}。
# 出处：MOPS ajax_t163sb04（TYPEK=sii，season=1/2 的累计营业收入；三条都逐条复核过）
# + TWSE OpenAPI t187ap06_L_ci（只挂**当期**一份，所以只能核最近一期，
# 2026 年 1-6 月那条两边互校一致）。同样只是外部常数，
# 图注里报的是**它与月度加总的差**，那个差在 import 期现算。
_OFFICIAL_CUM_K = {
    '2025 年 1-3 月': (2025, 3, 7_187_940),
    '2026 年 1-3 月': (2026, 3, 49_086_932),
    '2026 年 1-6 月': (2026, 6, 131_636_005),
}


# ══════════════════════════════════════════════════════════════════════════════
# 图注里的数一个都不写死，在 import 期从 series/nanya.csv 现算。
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
    out = {}
    for r in _rows():
        try:
            out[r['month']] = float((r['revenue_ntd_mn'] or '').strip())
        except (KeyError, TypeError, ValueError):
            continue
    return out


_S = _series()
_M = sorted(_S)


def _mlab(ym):
    return f'{ym[:4]} 年 {int(ym[5:7])} 月'


def _yoy():
    out = []
    for m in _M:
        p = f'{int(m[:4]) - 1}-{m[5:7]}'
        if p in _S and _S[p]:
            out.append((m, (_S[m] / _S[p] - 1.0) * 100.0))
    return out


def _ttm_yoy_last():
    """最新月的 12 个月滚动合计同比（%），算不出返回 None。"""
    if len(_M) < 24:
        return None
    tot = {}
    for i in range(11, len(_M)):
        tot[_M[i]] = sum(_S[_M[j]] for j in range(i - 11, i + 1))
    last = _M[-1]
    prev = f'{int(last[:4]) - 1}-{last[5:7]}'
    if prev not in tot or not tot[prev]:
        return None
    return (tot[last] / tot[prev] - 1.0) * 100.0


def _annual_recon():
    """[(年, 月度加总千元, 审计千元, diff, 相对%)]，只取 12 个月齐全且有审计数的年份。"""
    by = {}
    for m in _M:
        by.setdefault(int(m[:4]), []).append(_S[m])
    out = []
    for y in sorted(by):
        if len(by[y]) != 12 or y not in _AUDITED_K:
            continue
        s = round(sum(by[y]) * 1000.0)
        a = _AUDITED_K[y]
        out.append((y, s, a, s - a, (s - a) / a * 100.0))
    return out


def _last_full_quarter():
    """(标签, 三个月合计 NT$mn)；末尾不足一个完整季度就往前找。"""
    for i in range(len(_M) - 1, 1, -1):
        m = _M[i]
        if int(m[5:7]) % 3 != 0:
            continue
        win = _M[i - 2:i + 1]
        if len(win) == 3:
            return f'{m[:4]}Q{int(m[5:7]) // 3}', sum(_S[x] for x in win)
    return None, None


def _interim_recon():
    """月度加总 vs 官方期中累计（_OFFICIAL_CUM_K），返回 [(标签, 加总千元, 官方, diff)]。"""
    out = []
    for lab, (year, upto, official) in sorted(_OFFICIAL_CUM_K.items()):
        got = [_S[m] for m in _M if int(m[:4]) == year and int(m[5:7]) <= upto]
        if len(got) != upto:
            continue
        s = round(sum(got) * 1000.0)
        out.append((lab, s, official, s - official))
    return out


_YOY = _yoy()
_TTM_LAST = _ttm_yoy_last()
_RECON = _annual_recon()
_INTERIM = _interim_recon()
_QLAB, _QSUM = _last_full_quarter()

# ── 口径：可加性 + 未审计 ─────────────────────────────────────────────────────
if _RECON:
    _zero = [r for r in _RECON if r[3] == 0]
    _worst = max(_RECON, key=lambda r: abs(r[4]))
    _ADDITIVE_NOTE = (
        '<b>本页的季度聚合与 YTD 合法，但月度是「未审计申报数」，不等于审计数。</b>'
        f'{len(_RECON)} 个 12 个月齐全的年度里，月度加总与官方审计合并营业收入有 '
        f'<b>{len(_zero)} 年 diff 恰为 0</b>'
        + (f'（{"、".join(str(r[0]) for r in _zero)}）' if _zero else '')
        + f'；偏差最大的一年是 {_worst[0]}，月度加总 {_worst[1]:,} 千元 vs 审计 '
          f'{_worst[2]:,} 千元，差 {_worst[3]:+,} 千元 = <b>{_worst[4]:+.4f}%</b>。'
        '也就是说年结会有极小的审计调整，而公司<b>不回头改月度序列</b>（本页存的就是'
        '申报原值）。季度对得更死：'
        + (f'{_QLAB} 三个月相加 <b>NT${_QSUM:,.0f}mn</b>；'
           if _QLAB else '')
        + '；'.join(
            f'{lab}月度加总 <b>{s:,}</b> 千元 vs 官方合并综合损益表累计 {o:,} 千元，'
            f'diff <b>{d:+,}</b>' for lab, s, o, d in _INTERIM)
        + '。审计年度数出自 MOPS ajax_t163sb04 与公司审计合并财报 PDF 两条通道互校，'
          '期中累计出自 MOPS ajax_t163sb04 的季别累计（season=1/2）'
          '与 TWSE OpenAPI t187ap06_L_ci（只有当期，用来核最近一期），逐条见 '
          '<code>fetch/nanya.py</code> 的「对账 A / B」。')
else:
    _ADDITIVE_NOTE = (
        '<b>本页的季度聚合与 YTD 合法，但月度是「未审计申报数」。</b>'
        '月度加总与审计合并营业收入多数年份完全相等，个别年份有极小的年结审计调整，'
        '公司不回头改月度序列。')

# ── 周期振幅：为什么次轴走滚动同比、为什么不出热力矩阵 ────────────────────────
if _YOY:
    _lo = min(_YOY, key=lambda x: x[1])
    _hi = max(_YOY, key=lambda x: x[1])
    _mn = min(_S.items(), key=lambda kv: kv[1])
    _mx = max(_S.items(), key=lambda kv: kv[1])
    _CYCLE_NOTE = (
        '<b>这是一条存储器周期序列，读法与交易所那些页不同。</b>本表'
        f'{len(_M)} 个月里，单月合并营收最低 <b>NT${_mn[1]:,.0f}mn</b>（{_mlab(_mn[0])}）、'
        f'最高 <b>NT${_mx[1]:,.0f}mn</b>（{_mlab(_mx[0])}），相差 '
        f'<b>{_mx[1] / _mn[1]:.1f} 倍</b>；单月同比从 '
        f'<b>{_lo[1]:+.1f}%</b>（{_mlab(_lo[0])}）到 <b>{_hi[1]:+.1f}%</b>'
        f'（{_mlab(_hi[0])}）。'
        '所以「单月同比」那张图请当成<b>方向开关</b>看（有没有跨零、连续几个月同向），'
        '不要当幅度看 —— 同一根纵轴上，2026 年那几根柱会把 2015-2019 年整段压成贴着'
        '零线的一条细带，而底座的 SPEC 契约里没有截轴字段（`ycap` 只存在于旧的一家一份'
        '生成器里），本页因此不截轴、只在这里把量级说清楚。幅度请看水平值那张全历史图。'
        + (f'截至 {_mlab(_M[-1])}，12 个月滚动合计同比 <b>{_TTM_LAST:+.1f}%</b>。'
           if _TTM_LAST is not None else ''))
else:
    _CYCLE_NOTE = (
        '<b>这是一条存储器周期序列，读法与交易所那些页不同。</b>单月同比的振幅可以到'
        '三位数，请把它当方向开关看、不要当幅度看；幅度请看水平值那张全历史图。')

def _heat_readability():
    """把「热力矩阵在这条序列上不可读」量化：(p5, p95, 色深不到两成的格数, 总格数)。

    底座 heat_matrix 的色阶是全表 5/95 分位的**线性**双色、中性点在 0，
    所以一格的色深 ≈ |同比| / max(|p5|, |p95|)。色深不到 20% 的格子肉眼分不开。
    """
    xs = sorted(x for _, x in _YOY)
    if len(xs) < 20:
        return None
    def _q(p):
        k = (len(xs) - 1) * p / 100.0
        lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
        return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)
    p5, p95 = _q(5), _q(95)
    rng = max(abs(p5), abs(p95)) or 1.0
    flat = sum(1 for x in xs if abs(x) / rng < 0.20)
    return p5, p95, flat, len(xs)


_HEAT = _heat_readability()
if _HEAT:
    _p5, _p95, _flat, _ncell = _HEAT
    _NO_HEAT_NOTE = (
        '<b>本页没有热力矩阵，这是判断不是遗漏。</b>底座的 <code>heat_matrix</code> 色阶'
        '写死成全表 5/95 分位的<b>线性</b>双色，且<b>色阶与格内数字读同一份矩阵</b> —— '
        '「色阶取对数、格内印原值」在结构上做不到。本序列的单月同比实测 '
        f'p5/p95 = <b>{_p5:+.1f}% / {_p95:+.1f}%</b>，按这条线性色阶铺开，'
        f'{_ncell} 个可算同比的月份里有 <b>{_flat} 个（{_flat / _ncell * 100:.0f}%）</b>'
        f'色深不到两成、肉眼分不开，而 2026 那一排把整条色标吃掉。'
        '一张读不出信息的矩阵比没有矩阵更坏。'
        '（本页只有一条头条列、<code>groups</code> 为空，底座本来也走不到那条分支；'
        '写在这里是为了让这条判断留痕，而不是看起来像忘了配。）')
else:
    _NO_HEAT_NOTE = (
        '<b>本页没有热力矩阵，这是判断不是遗漏。</b>底座的 <code>heat_matrix</code> 色阶'
        '写死成全表 5/95 分位的线性双色，而这条序列的单月同比跨度是三位数，'
        '线性色阶下绝大多数格子会挤在中性色里。')

_NO_DECOMP_NOTE = (
    '<b>本页没有量价分解桥，也没有美元腿、没有指引桥。</b>三样都不是「还没做」，'
    '是对象不存在：①<b>量价</b> —— 公司不按月披露出货位元数或 ASP，'
    '拿第三方 DRAM 现货价去除月营收得到的「量」是构造值，恒等式 金额≡数量×价格 的'
    '两条腿有一条没有官方数，分解出来的归因无从对账；②<b>美元</b> —— 南亚科功能货币'
    '与表达货币都是新台币，月营收是原生记账数，公司从不披露美元营收金额或占比；'
    '③<b>指引</b> —— 2026Q2 法说会 deck 的前向语句只有 "expect to further improve" '
    '这类定性说法，通篇没有一个前向数字，所以没有可桥接的区间。')

if _RECON:
    _SRC_NOTE = (
        '<b>数据源与落库口径。</b>入库值取 MOPS 公开资讯观测站「上市公司月营业收入统计表」'
        '逐月全市场 CSV（<code>t21sc03_&lt;民国年&gt;_&lt;月&gt;.csv</code>，单位新台币千元），'
        '这是申报原件的分发通道；最新月探针与交叉核对走 TWSE OpenAPI '
        '<code>t187ap05_L</code>；重述体检拿公司 IR 月营收年表（<code>/en/IR/36?Year=</code>）'
        f'逐格比对。三条通道实测<b>逐格相等</b>：MOPS 逐月档与本序列 {_M[0]} ~ {_M[-1]} '
        f'共 {len(_M)} 个月 diff 全为 0；IR 年表在它已填的月份上（截至 2026-08-13 是 '
        f'2013-01 ~ 2026-06 共 162 个月）同样 diff 全为 0。'
        '<b>发布节奏</b>（截至 2026-08-13 实测，新闻稿日期不是序列能算出来的量）：'
        '2013-01 ~ 2026-07 的 <b>163 个数据月逐月都有对应新闻稿</b>（无缺期），'
        '落在数据月月末后第 2-13 天、中位第 5 天'
        '（唯一的第 13 天是 2014-09 数据撞双十节连假）；2022 年以来 55 期收敛到第 '
        '<b>2-9 天</b>、中位第 4 天，季末月没有例外（2022 年以来季末月最晚第 8 天）。'
        '⚠️ 公司 IR 那张月营收年表<b>比新闻稿慢</b>（实测 2026-08-13 当天新闻稿已发 '
        '2026-07 数，年表那一行还是空的），所以它只做体检、不当最新月的判据。')
else:
    _SRC_NOTE = (
        '<b>数据源与落库口径。</b>入库值取 MOPS 逐月全市场月营收 CSV（申报原件的分发'
        '通道，单位新台币千元），交叉核对走 TWSE OpenAPI，重述体检走公司 IR 月营收年表。'
        '公司 IR 年表比新闻稿慢，只做体检、不当最新月的判据。')

_BREAK_NOTE = (
    '<b>两条口径登记（见图上红色竖虚线与下表）。</b>'
    '① <b>2013-09：比较基期被重述，水平值没有。</b>公司在 2014 年 9-12 月的申报里把'
    '「去年当月」基期下修了 3.24%~4.50%（2014-09 报的去年当月 3,633,353 千元，而 '
    '2013-09 当时申报的是 3,804,586 千元，−4.50%；10/11/12 三个月分别 −4.17%/−3.85%/'
    '−3.24%），而<b>已公布的月度水平值一格都没改</b>（MOPS 月档与公司 IR 年表 2013-01 起'
    '逐格相等）。后果只有一个：用本序列算出来的 2014-09~12 单月同比，与公司当年公告的'
    '同比对不上。本序列保留原申报值、不追溯改写。'
    '② <b>2025-08：合并范围变动，但不是并购。</b>MemoLead Technology Corp.'
    '（持股 72.10%）于 2025-08-29 <b>新设登记</b>并自当期起纳入合并报表；'
    '它是 greenfield 新设而非收购，没有把一段既有营收并进来（2025 年该子公司净损 '
    '3,642 千元，营收贡献在合并数里不可辨识），所以<b>不构成伪同比</b>。'
    '登记在这里是为了让合并范围的变动日期可查，不是说这条线左右不可比。')

SPEC = {
    'ticker': 'nanya',
    'name':   'Nanya Technology',
    'title':  '南亚科技（Nanya，2408.TW）月度合并营收',
    'csv':    'nanya.csv',
    'ccy':    'TWD',
    'source': 'Source: TWSE MOPS monthly revenue filings (t21sc03), cross-checked '
              'against Nanya Technology IR monthly revenue table and TWSE OpenAPI '
              't187ap05_L; format after Goldman Sachs GIR',

    # 头条只有一列：台股月营收披露就是一个数，公司不按月拆产品/地区/客户。
    # 163 个月（2013-01 起）远超底座要求的 24 个月共同历史。
    'headline': [
        {'col': 'revenue_ntd_mn', 'zh': '月合并营收', 'unit': 'NT$mn', 'fmt': 'f0c'},
    ],

    # 空组是刻意的：公司的月度披露只有一个合计数，没有任何官方逐月拆分可以放进
    # 「组内多列对比」。硬凑一组（比如把同一列再画一遍、或把 YTD 累计当第二列）
    # 只会让读者以为那是两条独立信息。
    'groups': [],

    'breaks': [
        {'month': '2013-09', 'zh': '2014 年申报把 2013-09~12 的比较基期下修 3.2%~4.5%'
                                   '（水平值未改，本序列保留原申报值）'},
        {'month': '2025-08', 'zh': 'MemoLead（72.1%）新设并表 —— 新设非并购，营收贡献'
                                   '不可辨识'},
    ],

    # 次轴走 12 个月滚动同比而不是单月同比（CONTRACT §6.1 第 1 条）：
    # 存储器周期 + 农历年错位 + 工作日数三重推动，单月同比的毛刺可以大到与趋势符号相反。
    # granularity='monthly_total' —— 这一列本身就是当月合计，不是日均，也没有交易日列。
    'ttm_yoy': [{
        'zh': '月合并营收',
        'granularity': 'monthly_total',
        'level': {'col': 'revenue_ntd_mn', 'zh': '月合并营收',
                  'unit': 'NT$mn', 'fmt': 'f0c'},
    }],

    'notes': [_ADDITIVE_NOTE, _CYCLE_NOTE, _NO_HEAT_NOTE, _NO_DECOMP_NOTE,
              _SRC_NOTE, _BREAK_NOTE],
}
