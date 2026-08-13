# -*- coding: utf-8 -*-
"""日月光投控（ASEH，3711.TW / NYSE: ASX）单公司页配置。

⚠️ **slug 是 `ase`。`asx` 在本仓已经是 ASX Limited（澳交所）**，
   而日月光的 NYSE ADR 恰好也叫 ASX —— 写串两张页会同时错，而且静默。

台湾《证券交易法》要求上市公司次月 10 日前公告上月营收，所以「有没有月度数据」
在台股不是问题。选 ASEH 的理由，也是这一页唯一值得做的理由，是**它的合并月营收
读不出封测的景气**：

  · ASEH 是「封测（ATM）＋ 电子代工（EMS，即环旭 USI）」两块业务拼起来的控股公司。
    EMS 常年占三分之一上下，两块的周期与客户完全不同 —— 一块跟着 AI/HPC 的先进
    封装走，一块跟着消费电子与车用组装走。把两块加在一起算出来的同比，
    在任何一块单边走强的时候都是错的。
  · 公司**自己按月把 ATM 单独披露**（月度新闻稿的第二张表），
    所以这不是分析师拆的，是官方口径。本序列因此有三列。

━━ 📌 第三列叫 `revenue_nonatm_ntd_mn` 而不是 `revenue_ems_ntd_mn`，是刻意的 ━━
月度新闻稿只给两个数：合并总额与 **ATM 分部**营收（含分部间交易）。
第三列 = 合并 − ATM，是个**残差**，等于「官方 EMS 分部 + Others − ATM 分部间抵销」，
**不等于**合并利润表里的 EMS 行。实测 2026Q2：残差（本表三个月加总）64,914 /
合并利润表 EMS 65,411 / EMS 分部基础 65,789，三个数互不相等
（用官方季度口径 191,064 − 126,148 算残差是 64,916，与月加总差 2 是四舍五入）。
三十二个季度里残差与官方合并 EMS 差
126 ~ 3,016 百万（0.2% ~ 3.8%）。把它叫「EMS」省事，但那是在口径上说谎，
所以列名与图例一律写「非 ATM」。

━━ 📌 月度可加总，季度/年度聚合合法（已实测）━━━━━━━━━━━━━━━━━━━━━━━━
ASEH 功能货币是新台币，月营收是原生记账数不是折算值。月加总与官方季度逐季对账
（2018Q3~2026Q2，32 个季度）差 −1 ~ +1 百万，全是四舍五入残差；与官方年度差 ≤ 2。
ATM 月加总与公司自印的季度 ATM，32 个季度全部差 ≤ 2（多数为 0/±1）。
注意要拿**最晚一版**的 Q 表比：2019-06 期印的 Q2-2019 ATM 是重述前的 59,790，
与月加总差 196；2019-09 期把它重述成 59,594 后 diff=0（本序列存的就是重述后值）。
同理 2018Q4 ATM 旧版 64,127 / 新版 64,120，本序列 64,120。
再与**另一份文件**（法说会 deck 的 `ATM Statements of Income`）对：
2025Q2 92,564 vs 92,565、2026Q1 112,434 vs 112,434、2026Q2 126,149 vs 126,148。

━━ 📌 本页没有美元腿，也不该有 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
月度新闻稿确实印了 US$ 表，但那是公司拿**当月平均汇率**折出来的展示值，
不是以美元计价的销售。ASEH 记账与报表货币都是新台币，把美元列画成一条腿，
读者会以为看到了汇率贡献 —— 实际上看到的是「新台币营收 × 一个未披露的月度汇率」。
底座也没有折算腿与汇率贡献拆解，本页不实现。

━━ 📌 本页没有指引桥 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASEH 每季法说会给的是「下一季 ATM 新台币营收环比 +11%~+13%、EMS 环比约 +40%」
这种**季度环比百分比区间**，没有绝对金额、没有月度分解、没有折算汇率假设。
`/tsm/` 那条指引桥依赖 `series/tsm_guidance.csv` 的六列（美元绝对区间 + 折算汇率
+ 美元实绩），这六列在 ASEH 逐列无源。形态对不上就不做 —— 底座也没有这张图。
"""

import csv
import os

_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'series', 'ase.csv')


# ══════════════════════════════════════════════════════════════════════════════
# 图注里的数一个都不写死，在 import 期从 series/ase.csv 现算。
# 读不到就退回不含数字的定性版本 —— 缺文件不许在 import 期抛异常，
# 否则 monthly_run 会因为一张页的配置炸掉整批（同 build/specs/guc.py）。
# ══════════════════════════════════════════════════════════════════════════════
def _rows():
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except Exception:        # noqa: BLE001 —— 文件缺失/编码坏/行超长都只能退回定性版本
        return []            #    import 期一旦抛异常，monthly_run 会整批炸掉


def _col(rows, name):
    out = []
    for r in rows:
        try:
            out.append(float((r[name] or '').strip()))
        except (KeyError, TypeError, ValueError):
            out.append(None)
    return out


def _ttm_yoy(x):
    """12 个月滚动合计的同比（%）。任何一格缺就整段留 None。"""
    tot = []
    for i in range(len(x)):
        win = x[i - 11:i + 1] if i >= 11 else []
        tot.append(sum(win) if len(win) == 12 and None not in win else None)
    out = []
    for i in range(len(tot)):
        if i < 12 or tot[i] is None or not tot[i - 12]:
            out.append(None)
        else:
            out.append((tot[i] / tot[i - 12] - 1.0) * 100.0)
    return out


def _mom_yoy(x):
    out = []
    for i in range(len(x)):
        if i < 12 or x[i] is None or not x[i - 12]:
            out.append(None)
        else:
            out.append((x[i] / x[i - 12] - 1.0) * 100.0)
    return out


def _stats():
    rows = _rows()
    if not rows:
        return None
    months = [r.get('month', '') for r in rows]
    tot = _col(rows, 'revenue_ntd_mn')
    atm = _col(rows, 'revenue_atm_ntd_mn')
    if None in tot or None in atm or not months:
        return None
    share = [a / t * 100.0 for a, t in zip(atm, tot) if t]
    if not share:
        return None
    srt = sorted(share)
    n = len(srt)
    med = srt[n // 2] if n % 2 else (srt[n // 2 - 1] + srt[n // 2]) / 2.0

    tc, ta = _ttm_yoy(tot), _ttm_yoy(atm)
    mc, ma = _mom_yoy(tot), _mom_yoy(atm)
    tgap = [(m, a - c) for m, c, a in zip(months, tc, ta)
            if c is not None and a is not None]
    mgap = [(m, a - c) for m, c, a in zip(months, mc, ma)
            if c is not None and a is not None]
    if not tgap or not mgap:
        return None
    tail_t, tail_m = tgap[-12:], mgap[-12:]
    return {
        'm0': months[0], 'm1': months[-1], 'n': len(months),
        'sh_lo': min(share), 'sh_hi': max(share), 'sh_med': med,
        'sh_last': share[-1],
        'tgap_lo': min(g for _, g in tail_t), 'tgap_hi': max(g for _, g in tail_t),
        'tgap_pos': sum(1 for _, g in tail_t if g > 0), 'tgap_n': len(tail_t),
        'tgap_m0': tail_t[0][0], 'tgap_m1': tail_t[-1][0],
        'mgap_lo': min(g for _, g in tail_m), 'mgap_hi': max(g for _, g in tail_m),
        'mgap_n': len(tail_m),
        'ttm_c': tc[-1], 'ttm_a': ta[-1], 'mom_c': mc[-1], 'mom_a': ma[-1],
    }


_S = _stats()

if _S:
    _SPLIT_NOTE = (
        f'<b>合并同比读不出封测，这是本页存在的理由。</b>本表 {_S["n"]} 个月里，'
        f'ATM（封测及材料）占合并营收 <b>{_S["sh_lo"]:.1f}% ~ {_S["sh_hi"]:.1f}%</b>、'
        f'中位 <b>{_S["sh_med"]:.1f}%</b>（最新月 {_S["sh_last"]:.1f}%），'
        f'其余是 EMS（电子代工，环旭 USI）与少量其他业务 —— 两块的客户与周期完全不同。'
        f'最近 {_S["tgap_n"]} 个月（{_S["tgap_m0"]} ~ {_S["tgap_m1"]}）的 '
        f'<b>12 个月滚动同比</b>，ATM 每一个月都高于合并口径，'
        f'差 <b>{_S["tgap_lo"]:+.1f}pp ~ {_S["tgap_hi"]:+.1f}pp</b>'
        f'（{_S["tgap_pos"]}/{_S["tgap_n"]} 个月为正）；'
        f'最新月滚动同比合并 {_S["ttm_c"]:+.1f}%、ATM {_S["ttm_a"]:+.1f}%。'
        f'换成单月同比差距更大：同一段窗口 <b>{_S["mgap_lo"]:+.1f}pp ~ '
        f'{_S["mgap_hi"]:+.1f}pp</b>，最新月合并 {_S["mom_c"]:+.1f}% 而 ATM '
        f'{_S["mom_a"]:+.1f}%。<b>读这一页时，把合并那条线当封测景气用，'
        f'每个月都会低估。</b>')
else:
    _SPLIT_NOTE = (
        '<b>合并同比读不出封测，这是本页存在的理由。</b>ASEH 的合并营收里常年有三分之一'
        '上下来自 EMS（电子代工，环旭 USI），与 ATM（封测及材料）的客户与周期完全不同；'
        '公司按月单独披露 ATM，本页把两条线并排画，就是为了不让合并数替封测说话。')

_CALIBER_NOTE = (
    '<b>第三列是「非 ATM」残差，不是官方 EMS 分部营收。</b>月度新闻稿只给两个数：'
    '合并总额与 <b>ATM 分部</b>营收（含分部间交易）。本表第三列 = 合并 − ATM，'
    '等于「EMS 分部 + Others − ATM 分部间抵销」。实测 2026Q2 三个数互不相等：'
    '残差（本表 4~6 月加总）64,914 / 合并利润表 EMS 行 65,411 / EMS 分部基础 65,789；'
    '三十二个季度里残差与合并利润表 EMS 差 126 ~ 3,016 百万（0.2% ~ 3.8%）。'
    '所以列名与图例一律写「非 ATM」——「EMS」这个词省事，但会把口径说错。'
    '同理，ATM 那一列也<b>不等于</b>合并利润表的 Packaging + Testing + Others：'
    '2026Q2 前者 126,149、后者 125,653，差的是分部间交易。')

_ADDITIVE_NOTE = (
    '<b>本页的季度聚合与 YTD 是合法的（已实测，不是推定）。</b>ASEH 功能货币与报表货币'
    '均为新台币，月营收是原生记账数、不是折算值。月加总与官方季度逐季对账'
    '（2018Q3 ~ 2026Q2 共 32 个季度）差 <b>−1 ~ +1 百万</b>，全部是四舍五入残差；'
    '与官方年度差 ≤ 2（2019 FY 413,182 / 2021 569,997 / 2023 581,914 / '
    '2024 595,410 / 2025 645,388）。ATM 月加总与公司自印的季度 ATM，'
    '32 个季度<b>全部</b>差 ≤ 2 —— 前提是拿<b>最晚一版</b>的 Q 表比：'
    '2019-06 期印的 Q2-2019 ATM 是重述前的 59,790，与月加总差 196，'
    '2019-09 期重述成 59,594 后 diff=0；2018Q4 同理（旧版 64,127 / 新版 64,120）。'
    '本序列一律存最晚公布值。')

_BREAK_NOTE = (
    '<b>两处并表/处分断点，红色竖虚线<u>只画在真正受影响的那张图上</u>。</b>'
    '① <b>2020-12</b>：环旭（USI）于 2020-12-01 完成对 Asteelflash（FAFG）100% 股权的'
    '收购，自当月起并入 EMS —— 影响的是合并与非 ATM 两条线，ATM 那条线不受影响。'
    '② <b>2021-12</b>：中国四厂（苏州 ASEN、昆山 ASEKS、威海 ASEWH、上海 Advanced '
    'Shanghai）出售予智路资本（Wise Road），协议 2021-12-01 签署、'
    '<b>2021-12-16 交割</b>，所以 2021-12 是半个月的过渡月、2022-01 才是第一个干净月 —— '
    '影响的是合并与 ATM，非 ATM 那侧不受影响（Dec-2021 公司自印的 pro forma：'
    '合并 59,665→57,376、ATM 31,011→28,722，两边都是 −2,289，残差分毫未动）。'
    '公司自己也认这条断点：2022 全年 12 期月报每期都多印一组'
    '「排除已处分中国四厂」的 pro forma 表。因此 Exhibit 2（合并）画两条红线、'
    'Exhibit 3（ATM）只画 2021-12 那条。'
    '<b>跨这两个月的同比都是伪同比</b>，本序列不做追溯调整（官方从未按月重述），'
    '只把断点登记出来。')

_SRC_NOTE = (
    '<b>数据源与落库口径。</b>数值全部取自 ASEH 官方英文月度新闻稿 PDF 正文的两张 NT$ 表'
    '（<code>CONSOLIDATED NET REVENUES</code> 与 <code>ATM NET REVENUES</code>，'
    '2018-05 ~ 2018-12 叫 <code>IC-ATM</code>），链接每次从 IR 落地页现抓。'
    '<b>落地页表格里印的金额不作数</b>：2026-01 那一格印的是 59,589，'
    'PDF 正文、MOPS 全市场月表与 TWSE OpenAPI 的当年累计三处都指向 <b>59,989</b>。'
    '第三源全历史对账：MOPS <code>t21sc03</code> 全市场月表 2018-05 ~ 2026-07 共 99 个月'
    '逐月与本序列相符（最大绝对差 0.5 百万，来自千元 → 百万的四舍五入）；'
    'TWSE OpenAPI <code>t187ap05_L</code> 当期 73,783,701 千元 = 73,784 百万，'
    '与 2026-07 入库值相等。序列起点 2018-05 是口径起点不是「最早可得」：'
    'ASEH 控股 2018-04-30 才成立，2018-05 是第一个合并月报。')

_NO_USD_NOTE = (
    '<b>本页没有美元腿，是刻意的。</b>月度新闻稿确实印了一张 US$ 表，但那是公司拿当月'
    '平均汇率折出来的展示值，不是以美元计价的销售，公司也没有披露所用汇率。'
    '把它画成一条腿，读者会以为看到了汇率贡献，实际看到的是「新台币营收 × '
    '一个未披露的月度汇率」。底座也没有折算腿与汇率贡献拆解，本页不实现。')

_NO_GUIDANCE_NOTE = (
    '<b>本页没有指引桥。</b>ASEH 每季法说会给的是「下一季 ATM 新台币营收环比 '
    '+11%~+13%、EMS 环比约 +40%」这种<b>季度环比百分比区间</b>，'
    '没有绝对金额、没有月度分解、没有折算汇率假设。<code>/tsm/</code> 那条指引桥依赖'
    '美元绝对区间 + 折算汇率 + 美元实绩六列，在 ASEH 逐列无源 —— 形态对不上就不做。')

SPEC = {
    'ticker': 'ase',
    'name':   'ASE',
    'title':  '日月光投控（ASEH，3711.TW）月度营收',
    'csv':    'ase.csv',
    'ccy':    'TWD',
    'source': 'Source: ASE Technology Holding monthly net revenue press releases '
              '(ir.aseglobal.com), cross-checked against TWSE MOPS t21sc03 and '
              'TWSE OpenAPI t187ap05_L; format after Goldman Sachs GIR',

    # 两条头条：合并与 ATM 同源同日发布（同一份 PDF 的两张表），不会互相拖住门槛。
    # 并排放进头条，是为了让「全历史 + 3Y 分位」「同比」「季节性」三组图各出两张，
    # 读者能逐张对着看合并口径在哪些时候替封测说了假话。
    'headline': [
        {'col': 'revenue_ntd_mn', 'zh': '合并月营收', 'unit': 'NT$mn', 'fmt': 'f0c'},
        {'col': 'revenue_atm_ntd_mn', 'zh': 'ATM 月营收（封测及材料）',
         'unit': 'NT$mn', 'fmt': 'f0c'},
    ],

    'groups': [
        # 两列同单位 ⇒ 同一个桶 ⇒ 一张图上对比。ATM + 非 ATM 逐月恒等于合并总额。
        {'zh': '营收构成：ATM vs 非 ATM（官方逐月拆分）', 'cols': [
            {'col': 'revenue_atm_ntd_mn', 'zh': 'ATM（封测及材料）',
             'unit': 'NT$mn', 'fmt': 'f0c'},
            {'col': 'revenue_nonatm_ntd_mn', 'zh': '非 ATM（EMS 及其他，残差）',
             'unit': 'NT$mn', 'fmt': 'f0c'},
        ]},
    ],

    # 次轴走 12 个月滚动同比而不是单月同比：台股月营收受工作日数、农历年错位
    # （1/2 月之间可以差一整周产能）与季末拉货三重推动，单月同比的毛刺可以大到
    # 与趋势符号相反。granularity='monthly_total' —— 这两列本身就是当月合计。
    'ttm_yoy': [
        {'zh': '合并月营收',
         'granularity': 'monthly_total',
         'level': {'col': 'revenue_ntd_mn', 'zh': '合并月营收',
                   'unit': 'NT$mn', 'fmt': 'f0c'}},
        {'zh': 'ATM 月营收（封测及材料）',
         'granularity': 'monthly_total',
         'level': {'col': 'revenue_atm_ntd_mn', 'zh': 'ATM 月营收',
                   'unit': 'NT$mn', 'fmt': 'f0c'}},
    ],

    # 断点**按列**登记，不登记成全局 —— 两条断点各只打在真正受影响的那几列上：
    #   · 2020-12 Asteelflash 并入的是 EMS 侧 ⇒ 合并 + 非 ATM，**ATM 不受影响**；
    #     登记成全局会在 Ex3（ATM 全历史）上画一条假的「此处不可比」红线。
    #   · 2021-12 卖掉的中国四厂全是 ATM 厂 ⇒ 合并 + ATM，**非 ATM 不受影响**
    #     （实测 Dec-2021 pro forma：合并 −2,289、ATM −2,289，残差分毫未动）。
    # 底座 breaks_for() 对「同一断点按列登记好几份」自带去重，Ex2 上不会画成两条重线。
    'breaks': [
        {'month': '2020-12', 'col': 'revenue_ntd_mn',
         'zh': 'USI 完成收购 Asteelflash（FAFG），自本月起并入 EMS'},
        {'month': '2020-12', 'col': 'revenue_nonatm_ntd_mn',
         'zh': 'USI 完成收购 Asteelflash（FAFG），自本月起并入 EMS'},
        {'month': '2021-12', 'col': 'revenue_ntd_mn',
         'zh': '中国四厂出售予智路资本，2021-12-16 交割'},
        {'month': '2021-12', 'col': 'revenue_atm_ntd_mn',
         'zh': '中国四厂出售予智路资本，2021-12-16 交割'},
    ],

    'notes': [_SPLIT_NOTE, _CALIBER_NOTE, _ADDITIVE_NOTE, _BREAK_NOTE,
              _SRC_NOTE, _NO_USD_NOTE, _NO_GUIDANCE_NOTE],
}
