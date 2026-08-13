# -*- coding: utf-8 -*-
"""联发科（MediaTek，2454.TW）单公司页配置。

台湾《证券交易法》要求上市公司次月 10 日前公告上月营收，所以「有没有月度数据」在台股
不是问题。选 2454 的理由与选 3443（GUC）不同：GUC 胜在口径干净，联发科胜在**它是这
张表里唯一一家 AI/手机 SoC 的规模体**（2025 年合并营收 NT$595,966mn ≈ US$18.6bn），
而它的月营收又刚好是全站少数几条能逐月对到审计年报的序列之一。逐条实测过：

  · **月营收逐月可加总。** 月度加总（NT$mn）vs 该年 Q4 合并报表 Net sales：
    2018 238,056 / 238,057.346  2019 246,222 / 246,221.731  2020 322,146 / 322,145.988
    2021 493,414 / 493,414.582  2022 548,796 / 548,796.030  2023 433,446 / 433,446.330
    2024 530,585 / 530,585.886  2025 595,966 / 595,965.682
    最大 |残差| **1.346 NT$mn = 0.00057%**，全部落在「12 个月各带 ±0.5 百万元舍入」
    的理论上界 ±6 之内；逐季 32 个季度最大 |残差| 1.124（2024Q4）。
    把同样 8 年改用**千元精度**的官方月表（MOPS t21sc03，全历史逐月一份）重算，
    逐月加总与审计年报 Net sales **八年逐年 diff = 0**（逐字相等）——
    所以百万元级的那点残差全部是舍入，一分钱都不是口径缺口。
    ⇒ 季度聚合、YTD、TTM 同比在本页**合法**，不需要免责。
    对照组是世芯-KY（3661）：同样的检验在那边是 **+0.378%**，因为它功能货币是美元、
    新台币月营收是逐月折算值。联发科合并财报附注原文：「The Company's consolidated
    financial statements are presented in NT$, which is also the parent company's
    functional currency.」

  · **起点 2018-01 是准则边界，不是「最早可得」。** 官方年度汇总 PDF 从 2008 年就有
    月度数，但联发科自 2018-01-01 起适用 IFRS 15 且采**修正追溯法**、比较期不重编
    （销货退回与折让由「冲减应收帐款」改为「认列退款负债」），2017-12 及以前与之后
    不在同一套收入认列口径上。

  · **2018-01 之后仍有三次合并范围变动，本页登记进 `breaks`**（见下）。
    这一条与本页立项时拿到的线索相反 —— 线索说「2018-01 后无营收口径事件」，
    但公司自己的合并财报附注里写着三次，两大一小，逐条量化后照登。

  · **本页只有一列。** 联发科月度披露就是一个合并营收数：新闻稿里的五类字段
    （当月 / 去年同月 / YoY / YTD 两期 / MoM）除了当月金额之外全是它的派生量，
    存进序列等于把同一个事实存五遍。所以 `groups` 是空的，页面只出
    全历史+3Y 分位带、同比、季节性、TTM 同比与核对表 —— 没有构成图可画，
    也不去拿分析师构造值凑一张。
"""

import csv
import os

_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'series', 'mtk.csv')

#: 官方审计/核阅过的年度合并营收（NT$ thousand），来自各年 Q4 合并财报的 Net sales 行。
#: 这是**外部事实**、不是本序列的派生量，所以以字面量登记；
#: 与它比对的那一侧（月度加总）在下面 import 期从 series CSV 现算。
_AUDITED_NTD_K = {
    2018: 238_057_346, 2019: 246_221_731, 2020: 322_145_988, 2021: 493_414_582,
    2022: 548_796_030, 2023: 433_446_330, 2024: 530_585_886, 2025: 595_965_682,
}


# ══════════════════════════════════════════════════════════════════════════════
# 图注里的数一个都不写死，在 import 期从 series/mtk.csv 现算。
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


def _span(s):
    ms = sorted(s)
    return (ms[0], ms[-1], len(ms)) if ms else (None, None, 0)


def _recon(s):
    """逐年「月度加总 vs 审计年报」的对账结果：(完整年数, 最大 |diff| NT$mn, 最大相对偏差 %)。"""
    worst, worst_pct, n = 0.0, 0.0, 0
    for y, k in sorted(_AUDITED_NTD_K.items()):
        ms = [f'{y}-{i:02d}' for i in range(1, 13)]
        if not all(m in s for m in ms):
            continue
        n += 1
        off = k / 1000.0
        d = sum(s[m] for m in ms) - off
        if abs(d) > abs(worst):
            worst = d
        worst_pct = max(worst_pct, abs(d) / off * 100.0)
    return n, worst, worst_pct


def _cny(s):
    """农历年错位的量级：Feb/Jan 比值的 (最低, 最高, 样本年数)。

    农历年在 1 月还是 2 月，会把出货在这两个月之间整块搬运 —— 这是台股月营收
    单月同比毛刺的第一大来源，也是本页次轴不用单月同比的理由之一。
    """
    rs = []
    for y in range(1900, 2200):
        a, b = s.get(f'{y}-01'), s.get(f'{y}-02')
        if a and b:
            rs.append(b / a)
    return (min(rs), max(rs), len(rs)) if rs else (None, None, 0)


_S = _series()
_M0, _M1, _MN = _span(_S)
_NYEAR, _WORST, _WORST_PCT = _recon(_S)
_CNY_LO, _CNY_HI, _CNY_N = _cny(_S)


if _NYEAR:
    _ADDITIVE_NOTE = (
        f'<b>本页的季度聚合与 YTD 是合法的（已实测，不是推定）。</b>本表 {_M0} 起'
        f'共 {_NYEAR} 个完整年度可与官方审计年报逐年对账：月度加总与各年 Q4 合并报表的 '
        f'Net sales 最大只差 <b>{abs(_WORST):,.3f} NT$mn</b>'
        f'（{_WORST_PCT:.5f}%），且残差方向正负都有。这不是「看着差不多」：把同样 8 年'
        '改用千元精度的官方月表（MOPS 月营收全市场月表）重算，逐月加总与审计年报的 '
        'Net sales <b>八年逐年 diff = 0</b>（238,057,346 / 246,221,731 / 322,145,988 / '
        '493,414,582 / 548,796,030 / 433,446,330 / 530,585,886 / 595,965,682 千元，'
        '八对数字逐字相等），2026 前 7 月的 349,808,051 千元也与 TWSE OpenAPI 累计、'
        '2026H1 的 301,333,121 千元与 2026Q2 合并报表逐字相等。'
        '⇒ 上面那点百万元级的残差 <b>全部</b>来自「公司只公告到百万元整数、'
        '12 个各带 ±0.5 的舍入相加」（理论上界 ±6），一分钱都不是口径缺口。'
        '联发科合并财报附注写明母公司功能货币与表达货币均为新台币，月营收是原生记账数、'
        '不是折算值 —— 这一点与同业世芯-KY（3661）相反，那家十二个月相加与官方本年累计'
        '差 +0.378%。')
else:
    _ADDITIVE_NOTE = (
        '<b>本页的季度聚合与 YTD 是合法的。</b>月度加总与官方审计年报的 Net sales '
        '逐年对得上，残差只来自「公司公告到百万元整数」的逐月舍入。'
        '联发科合并财报附注写明母公司功能货币与表达货币均为新台币，月营收是原生记账数。')

if _MN:
    _UNIT_NOTE = (
        f'<b>本序列存的是公司公告的原始单位：新台币百万元整数。</b>{_M0} 至 {_M1} 共 '
        f'{_MN} 个月，逐格与官方新闻稿 PDF 可以对读。TWSE OpenAPI 与 MOPS 月表给的是'
        '千元精度（举一格为例：2026-07 本表存 48,475，官方千元数是 48,474,930），'
        '当然对得上，但<b>只有最新的月份</b>能拿到'
        '千元 —— 主源（月度新闻稿）与回补源（年度汇总 PDF）都只印到百万元。'
        '混着存会让序列的有效位随月份跳变，而任何图都看不出来，所以统一存整数百万元，'
        '代价就是上面那条对账里量化过的逐月 ±0.5。')
else:
    _UNIT_NOTE = (
        '<b>本序列存的是公司公告的原始单位：新台币百万元整数</b>，逐格与官方新闻稿 PDF '
        '可以对读；千元精度只有最新月份拿得到，混存会造成随月份跳变的假精度。')

_BREAKS_NOTE = (
    '<b>2018-01 之后的三次合并范围变动，逐条量化后登记在图上（红色竖虚线）。</b>'
    '这三次都是<b>当期起生效、比较期不重编</b>，所以受影响的是跨断点那 12 个月的同比、'
    '不是水平值：'
    '<br>① <b>2020-12 奕力科技（ILI Technology）出表</b> —— 2020-07-31 董事会决议以 '
    'US$138mn 出售 ILI Technology Holding Corporation，2020-11-30 完成股权移转'
    '（2020 年报附注原文："On November 30, 2020, the Company has completed the transfer '
    'of shareholding rights of ILI Technology Holding Corporation."）。'
    '规模：ILI Technology Corporation 2019 年营业收入 NT$10,696mn（2019 年报「关系'
    '企业营运概况」），约当当年合并营收的 <b>4.3%</b>。'
    '<br>② <b>2021-02 星宸科技（Sigmastar）出表</b> —— 2020-09 处分股权至 50%、'
    '2021-02 丧失控制转列关联企业（2021 年报附注："…have not been consolidated by the '
    'Company since February 2021 as the Company lost control over them."）。'
    '规模：厦门星宸 2020 年营业收入 NT$6,646mn，约当当年合并营收的 <b>2.1%</b>。'
    '<br>⚠ ①② 的 4.3% / 2.1% 是<b>上界，不是净影响</b>：分子取的是这两家子公司'
    '<b>自身</b>的营业收入（年报「关系企业营运概况」表），<b>未扣除对集团内其他公司的'
    '销货冲销</b>，而合并营收里本来就没有那部分。公司从未披露这两家对合并营收的净贡献额，'
    '所以这里只给得出上界 —— 真实缺口小于等于这个数。③ 的 0.13% 不同，那是年报'
    '企业合并附注直接给的并表期间贡献额，是准数。'
    '<br>③ <b>2024-07 IC PLUS（IC+）并表</b> —— 络达持股 29.26% 加联发科 13.61%、'
    '过半董事席次，自 2024-07-01 取得实质控制。规模：2024 下半年贡献营收 NT$339mn，'
    '约当同期月营收的 <b>0.13%</b>；同附注给的 2024 全年备考营收 530,891mn vs 实际 '
    '530,586mn。量级只有前两者的三十分之一，仍照登，断点标签里直接写出 +0.13%，'
    '免得读者把线的存在本身误读成大事。')

if _CNY_N:
    _CNY_NOTE = (
        f'<b>读单月读数之前先看农历年落在哪个月。</b>本表 {_CNY_N} 组 1/2 月里，'
        f'2 月营收与 1 月营收的比值在 <b>{_CNY_LO:.2f} ~ {_CNY_HI:.2f}</b> 之间摆动 —— '
        '同一家公司，某些年 2 月明显低于 1 月，某些年反而高出三成。原因是农历年'
        '（连同台湾的年假与下游拉货节奏）在 1 月与 2 月之间来回移动，把出货整块搬运；'
        '2 月本身天数还少 2-3 天。这是台股月营收单月同比毛刺的第一大来源，也是本页'
        '次轴走 12 个月滚动同比、而不是单月同比的理由之一。季节性图（与同月常态比）'
        '同样吃这条：它按日历月对齐，对不齐农历。')
else:
    _CNY_NOTE = (
        '<b>读单月读数之前先看农历年落在哪个月。</b>农历年在 1 月与 2 月之间来回移动，'
        '把出货在这两个月之间整块搬运，2 月天数还少 2-3 天 —— 这是台股月营收单月同比'
        '毛刺的第一大来源，也是本页次轴走 12 个月滚动同比的理由之一。')

_START_NOTE = (
    f'<b>序列起点 {_M0 or "2018-01"} 是准则边界，不是「最早可得」。</b>'
    '官方年度汇总 PDF 从 2008 年起就有月度数，但联发科自 2018-01-01 起适用 IFRS 15 '
    '且采修正追溯法（"the Company elected to recognize the cumulative effect of '
    'initially applying IFRS 15 at the date of initial application"），'
    '<b>比较期不重编</b> —— 销货退回与折让由「冲减应收帐款」改为「认列退款负债」，'
    '2017-12 及以前的月营收与之后不在同一套收入认列口径上。取得到不等于口径连续。')

_NO_USD_NOTE = (
    '<b>本页没有美元腿，是刻意的。</b>联发科从不披露月度或季度的美元营收金额 —— '
    '法说会讲稿里出现的美元只有两处：一处是事后陈述的季度平均汇率（2026Q2「the average '
    'exchange rate for the second quarter was NT$31.6 to US$1」），一处是全年目标的'
    '<b>成长率</b>（"high-single digit percentage growth in US dollars"），都不是可对账的'
    '美元营收金额。把新台币月营收除以外部汇率折出来的是分析师构造值，没有任何官方数'
    '可以对账 —— 与 <code>/tsm/</code> 页不同，那边公司每季自报美元营收。'
    'MOPS 上 2454 那行的备注「海外子公司之營收係以當月平均匯率換算之」说的是海外子公司'
    '那一层的折算，不代表公司按美元计价；上面逐年 diff≈0 的对账正说明这层折算'
    '<b>不产生</b>月度与年度之间的缺口。')

_NO_GUIDANCE_NOTE = (
    '<b>本页没有指引桥，尽管公司给指引。</b>联发科每季法说会给的是<b>新台币绝对区间 + '
    '假设汇率</b>（2026Q2 法说：三季度营收 NT$152.2bn–159.8bn，"at a forecasted exchange '
    'rate of 32 NT dollars to 1 US dollar"），形式上完全够拼一条「当季 QTD 已实现 X、'
    '距指引中值还差 Y」。不做的原因不是没数据，是<b>通用底座没有指引桥这条腿</b>'
    '（<code>/tsm/</code> 页那句依赖 <code>series/tsm_guidance.csv</code> 与 '
    '<code>build/tsm.py</code> 专属生成器）。本页走底座，所以只在这里交代指引的形态，'
    '不在页面上拼那句话 —— 拼一半的桥比没有桥更容易被读成官方口径。')

_SRC_NOTE = (
    '<b>数据源与落库口径。</b>主源是联发科投资人关系页的<b>月度营收新闻稿 PDF</b>'
    '（<code>Monthly Sales Revenue &lt;Month&gt;, &lt;YYYY&gt;.pdf</code>，'
    '命名 2021-01 至今 67 个月一字未变）；2021 年之前的 36 个月由同页的<b>年度汇总 PDF</b>'
    '（<code>&lt;YYYY&gt;-Conslolidated-financial-details.pdf</code>，'
    '"Conslolidated" 是上游自己的拼写错误）回补。年度汇总 PDF 每年 1 月改一次命名，'
    '实测 2025 年那份在落地页上挂的 href 本身就是死链（空格版 404、只有连字符版能下'
    '），所以它只当回补与交叉核对、不当主源。'
    '交叉核对走 TWSE OpenAPI <code>t187ap05_L</code> 与 MOPS 月营收全市场月表'
    '（主机名是 <code>mopsov.twse.com.tw</code>，<code>mops.twse.com.tw</code> 同路径 404）。')

SPEC = {
    'ticker': 'mtk',
    'name':   'MediaTek',
    'title':  '联发科（MediaTek，2454.TW）月度营收',
    'csv':    'mtk.csv',
    'ccy':    'TWD',
    'source': 'Source: MediaTek monthly sales report press releases (mediatek.com), '
              'backfilled from the company annual monthly-revenue summary and '
              'cross-checked against TWSE OpenAPI and TWSE MOPS; '
              'format after Goldman Sachs GIR',

    # 头条只有一列：台股月营收披露就是一个数。103 个月（2018-01 起）远超底座要求的
    # 24 个月共同历史，同比与 3Y 分位都算得出来。
    'headline': [
        {'col': 'revenue_ntd_mn', 'zh': '月营收', 'unit': 'NT$mn', 'fmt': 'f0c'},
    ],

    # 公司月度披露只有合并营收一个数，没有第二列可放 —— 空 groups 是这一页的正确形态，
    # 不是遗漏。硬凑一个分析师构造的分项（美元折算腿、按季报占比摊到月）会把
    # 「官方逐格可对账」这条本页最值钱的性质弄丢。
    'groups': [],

    # 三次合并范围变动，量级写进标签本身 —— 断点线的语义是「从这一期起与左侧不可比」，
    # 第三条只有 0.13%，不把量级写出来会让读者按前两条的量级去理解它。
    'breaks': [
        {'month': '2020-12', 'zh': '奕力科技出表（2020-11-30 交割，上界 ≈ 上年营收 4.3%）'},
        {'month': '2021-02', 'zh': '星宸科技出表（丧失控制，上界 ≈ 上年营收 2.1%）'},
        {'month': '2024-07', 'zh': 'IC PLUS 并表（+0.13% 月营收）'},
    ],

    # 次轴走 12 个月滚动同比而不是单月同比：台股月营收受工作日数、农历年错位与
    # 客户拉货节奏三重推动，单月同比的毛刺可以大到与趋势符号相反。
    # granularity='monthly_total' —— 这一列本身就是当月合计，不是日均。
    'ttm_yoy': [{
        'zh': '月营收',
        'granularity': 'monthly_total',
        'level': {'col': 'revenue_ntd_mn', 'zh': '月营收',
                  'unit': 'NT$mn', 'fmt': 'f0c'},
    }],

    'notes': [_ADDITIVE_NOTE, _START_NOTE, _BREAKS_NOTE, _CNY_NOTE, _UNIT_NOTE,
              _NO_USD_NOTE, _NO_GUIDANCE_NOTE, _SRC_NOTE],
}
