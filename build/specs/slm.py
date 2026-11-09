# -*- coding: utf-8 -*-
"""SLM（Sallie Mae）单公司页配置 —— SMB 私人学生贷 ABS 信托的月度表现，按日历月合起来。

数据：series/slm.csv（fetch/slm.py 从官网「Trust Performance」xlsx 自算），
     series/slm_trusts.csv（每个信托的交割日池余额与现验记录），
     series/slm_breaks.csv（清仓赎回退出的月份）。
口径、映射证据与回源核对全文：docs/verify/slm.md。

本页与其余 30 页最不一样的一点：**页面上没有一个数是官方直接发布的合计**。
官方只发逐信托的比率（41 个信托 × 19 个指标块），本页每一列都是把当月仍在报告的
信托按各比率**自己的分母**还原成金额、相加、再除出来的（公式在 notes 第一条）。
所以：
  · 合计值带账龄结构：新信托（池子年轻、多数借款人还在校）不断加入、老信托清偿 /
    赎回退出，合计比率会随结构漂移，与「同一批贷款变好变坏」不是一回事 ——
    本页给了一张「池余额加权的发行后期数」专门交代这层结构（「账龄结构」组第二张）。
  · 不画「同账龄对比」：底座（build/single.py）只出日历月横轴的图，按发行后第 k 期
    对齐的横截面图型（bars_labeled 等）引擎里有、底座不产出，为一张图改手写生成器不划算。
⚠ 本文件不写死任何会随月份变的数：页尾那条「当月有几个信托」由 _n_trusts_note 现算。
"""
import csv
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _trusts():
    """series/slm_trusts.csv → [dict]；文件不在返回 []（import 期不许抛）。"""
    try:
        with open(os.path.join(_ROOT, 'series', 'slm_trusts.csv'), encoding='utf-8', newline='') as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _n_trusts_note(page):
    """页尾一条：本页数据月有几个信托在报告、表内 / 表外各几个、哪些已赎回退出、序列从哪个月起。"""
    df = page.df
    m = page.latest
    n = int(df.loc[m, 'n_trusts']) if 'n_trusts' in df.columns else None
    tr = _trusts()
    mm = str(m)
    live = [r for r in tr if r['first_month'] <= mm <= r['last_month']]
    on = sum(r['bs'] == 'on' for r in live)
    gone = [r for r in tr if r['retired'] == '1']
    first = min((r['first_month'] for r in tr), default='?')
    newest = max(tr, key=lambda r: r['first_month'])['trust'] if tr else '?'
    s = (f'<b>范围。</b>{mm} 这个月有 <b>{n}</b> 个信托在报告（表内 {on} / 表外 {len(live) - on}），'
         f'官方文件累计列了 {len(tr)} 个（最早一个 {first} 起报，最新一个是 {newest}）。')
    if gone:
        s += ('已行使清仓赎回退出的：' + '、'.join(f'{r["trust"]}（末期 {r["last_month"]}）' for r in gone)
              + ' —— 退出次月起画成口径断点。')
    s += ('来源页另列的 2020-PT-A / 2020-PT-B（pass-through）与 2024-R1（repackaging）'
          '不在这份文件里，也不进本页的任何合计。')
    return s


_U_POOL = '% of pool balance'
_U_PI = '% of P&I repayment'

GROUPS = [
    # ── G1 规模：池余额 = 表内 + 表外（逐月恒等，底座复算）。全是存量（月末口径）──
    # abs_stack：只出一张绝对值堆叠柱（柱高 = 合计、两段 = 表内 / 表外），不出「合计柱 + 次轴同比」
    # 与 100% 占比两张 —— 证券化池余额的同比主要读的是「这一年交割了几笔」，没有信息量；
    # 规模与构成一张图同时答。⚠ 也因此 build/test_guards.py 的 TestStockInline 借活 spec 时
    # 不会借到本页（它跳过 abs_stack 的组，而本组又已开 stock_inline，借了必挂）。
    {'zh': '证券化池余额', 'section': '规模与账龄结构', 'stock_inline': True, 'cols': [
        {'col': 'pool_bal_usdbn', 'zh': '池余额合计', 'unit': '$bn', 'fmt': 'f1', 'stock': True},
        {'col': 'pool_bal_onbs_usdbn', 'zh': '表内信托', 'unit': '$bn', 'fmt': 'f1', 'stock': True},
        {'col': 'pool_bal_offbs_usdbn', 'zh': '表外信托', 'unit': '$bn', 'fmt': 'f1', 'stock': True},
    ], 'mix': {
        'total': 'pool_bal_usdbn',
        'parts': ['pool_bal_onbs_usdbn', 'pool_bal_offbs_usdbn'],
        'abs_stack': True,
        'note': ('池余额 = 本金 + 待资本化利息（服务报告第 VIII 节的定义）。逐信托'
                 '「池因子 × 交割日池余额」再相加 —— <b>自算</b>，官方不发合计。'
                 '新信托交割的那个月合计会跳一级（每个 $0.2–2.6bn），那是证券化规模的真实增加，'
                 '不是断点；清仓赎回退出的月份画了红虚线。'
                 '表内 / 表外按<b>当期文件</b>的归属回溯整条历史 —— 官方只给当前归属；'
                 '2025-09 / 2026-03 / 2026-08 / 2026-09 四期文件的归属逐个相同。'),
    }},
    {'zh': '账龄结构', 'stock_inline': True, 'cols': [
        {'col': 'pi_bal_usdbn', 'zh': 'P&I 还款余额合计', 'unit': '$bn', 'fmt': 'f1', 'stock': True},
        {'col': 'age_wavg_periods', 'zh': '池余额加权的发行后期数', 'unit': 'months', 'fmt': 'f1',
         'stock': True},
    ]},

    # ── G2 借款人状态：两个比率同分母（当期池余额）──
    {'zh': '借款人状态（占池余额）', 'section': '借款人状态', 'cols': [
        {'col': 'pi_share_pct', 'zh': 'P&I 还款', 'unit': _U_POOL, 'fmt': 'pct1'},
        {'col': 'anyrepay_share_pct', 'zh': '任意还款状态', 'unit': _U_POOL, 'fmt': 'pct1'},
    ]},
    {'zh': 'Forbearance（暂停还款）', 'cols': [
        {'col': 'forbearance_pct', 'zh': '占 P&I + forbearance', 'unit': '% of P&I + forbearance',
         'fmt': 'pct1'},
    ]},
    {'zh': 'Deferment（延期还款）', 'cols': [
        {'col': 'deferment_pct', 'zh': '占 P&I + forbearance + deferment',
         'unit': '% of P&I + forb. + deferment', 'fmt': 'pct1'},
    ]},

    # ── G3 信用：分母一律是 P&I 还款余额（不含 forbearance）──
    {'zh': '逾期分档（占 P&I 还款余额）', 'section': '逾期、违约与贷款修改', 'cols': [
        {'col': 'dq30_59_pct', 'zh': '30–59 天', 'unit': _U_PI, 'fmt': 'pct2'},
        {'col': 'dq60_89_pct', 'zh': '60–89 天', 'unit': _U_PI, 'fmt': 'pct2'},
        {'col': 'dq90p_pct', 'zh': '90 天以上', 'unit': _U_PI, 'fmt': 'pct2'},
    ]},
    {'zh': '当期违约本金（gross，全部信托合计；次轴：单月同比）', 'cols': [
        {'col': 'defaults_usdmn', 'zh': '当期违约本金', 'unit': '$mn', 'fmt': 'f1'},
    ]},
    {'zh': '贷款修改', 'cols': [
        {'col': 'loan_mod_pct', 'zh': '修改中余额占 P&I', 'unit': '% of P&I in modification',
         'fmt': 'pct1'},
    ]},
]

_GLOSSARY = [
    ('池余额（Pool Balance）',
     '信托里全部贷款的<b>本金 + 待资本化利息</b>（服务报告第 VIII 节的定义）。'
     '在校、宽限期、deferment 的贷款利息不付现、到期并进本金，所以年轻信托的池余额'
     '里有一块是「还没发生的本金」。'),
    ('池因子',
     '当期池余额 ÷ <b>交割日</b>池余额。⚠ 分母不是官方 Orig 表里「统计截止日」的池余额 —— '
     '截止日那个数比交割日高 0.2%–2.3%（中间有还款、剔除不合格贷款）。'),
    ('发行后期数',
     '信托第几个月度收款期：第 1 期是首个收款期所在的月（不一定是交割月）。'
     '官方 xlsx 有一半指标按期数、一半按日历月排，本页全部换成日历月。'),
    ('P&I 还款',
     'Borrower status = P&I Repayment：已进入全额本息还款期的贷款（当期 + 三档逾期），'
     '<b>不含</b> forbearance。逾期率、年化违约率、贷款修改率的<b>分母</b>都是它。'),
    ('任意还款状态',
     'Repayment status = Repayment：只要当月有应付款就算 —— 除了全额本息，'
     '还含在校期<b>只付利息</b>与<b>每月固定付 $25</b> 的借款人。所以它比 P&I 还款大一截。'),
    ('Forbearance',
     '暂停还款：因求职、经济困难等临时免付。本页比率 = forbearance ÷ (P&amp;I + forbearance)。'),
    ('Deferment',
     '延期还款：通常因为重返校园。本页比率 = deferment ÷ (P&amp;I + forbearance + deferment)。'),
    ('年化当期违约率',
     '当月违约（gross principal realized loss）× 12 ÷ 当月末 P&amp;I 还款余额。'
     '「违约」是核销口径：SLM 服务的信托逾期 120 天核销，2014-A（Navient 子服务）212 天。'),
    ('贷款修改',
     '修改中余额（临时降息、延长期限等）÷ P&amp;I 还款余额。'),
    ('表内 / 表外信托',
     'SLM 合并报表里的信托（贷款与 ABS 都在 SLM 资产负债表上）/ 已出表的信托'
     '（贷款连同剩余权益卖给了第三方，SLM 只做服务商）。'),
    ('清仓赎回',
     'Optional Purchase（clean-up call）：池余额降到交割日的 10% 以下后，'
     '可以一次性买回全部剩余贷款、清偿全部债券，信托就此终止、不再报告。'),
]

_NOTES = [
    ('<b>全部是自算值。</b>官方「SMB Private Education Loan ABS Trusts Static Pool Information '
     'and Monthly Performance」xlsx 只发<b>逐信托</b>的比率，没有任何合计或加权数。'
     '本页对每个日历月、只对当月仍在报告的信托：池余额<sub>i</sub> = 池因子<sub>i</sub> × '
     '交割日池余额<sub>i</sub>；P&amp;I<sub>i</sub> = P&amp;I 占比<sub>i</sub> × 池余额<sub>i</sub>；'
     'Forb<sub>i</sub> = f<sub>i</sub>·P&amp;I<sub>i</sub> ÷ (1 − f<sub>i</sub>)；'
     'Defer<sub>i</sub> = d<sub>i</sub>·(P&amp;I<sub>i</sub> + Forb<sub>i</sub>) ÷ (1 − d<sub>i</sub>)；'
     '各档逾期、修改中余额 = 比率 × P&amp;I<sub>i</sub>；当期违约 = 年化违约率 × P&amp;I<sub>i</sub> ÷ 12；'
     '任意还款 = 比率 × 池余额<sub>i</sub>。合计比率 = Σ 分子 ÷ Σ 分母 —— '
     '每个比率按<b>它自己的分母</b>加权，不按池余额。'
     '交割日池余额取自各信托的月度服务报告（xlsx 里没有），'
     '逐信托「因子 × 交割日池余额」与最新服务报告的池余额 41/41 相等到分。'),
    ('<b>读法上的大前提：合计值带账龄结构。</b>每年有 1–6 个新信托加入（2021 年起每年 3–6 个；池子年轻、多数借款人还在校、'
     'P&amp;I 占比低），老信托逐月清偿、最终清仓赎回退出。合计比率的变化因此有两个来源 —— '
     '同一批贷款的表现变化，与「哪几批贷款在分母里」的结构变化 —— 本页分不开。'
     '规模与账龄结构那一节的「池余额加权的发行后期数」是专门给这层结构的读数：'
     '它跳水的月份（新信托交割）合计比率跟着跳，不是信用拐点。'),
    ('<b>口径断点只画清仓赎回。</b>信托被买回的次月起合计里少一个高账龄信托，画成红虚线'
     '（来自 series/slm_breaks.csv，由抓取模块按文件里的 * 标记现生成）。'
     '新信托加入是常态，不画断点。'),
    ('<b>2014-A 的口径与其余信托不同。</b>它由 Navient 子服务，逾期 212 天才核销（其余 120 天），'
     '所以它的「90 天以上逾期」含 120–212 天那一段、违约确认也更晚（官方 Static Pool Information 脚注 1）。'
     '2014-08 至 2015-04 合计里只有它一家；之后权重越来越小，照原样并入。'
     '它的服务报告也没有 Borrower Status 表，P&amp;I / 逾期 / forbearance / deferment / 修改只有 xlsx 一个来源。'),
    ('<b>贷款修改的历史值照当期 xlsx。</b>2026-08 / 2026-09 的 xlsx 比率与当月服务报告的'
     '「Loans in Modification」逐分相等；抽查 2020-04 / 2023-06，xlsx 比当年报告原文高约 0.1%（相对），'
     '合计层面约 0.01pp —— 官方对历史的修改口径与当年报告不完全一样，本页照 xlsx 出，差异记在 docs/verify/slm.md。'),
    ('<b>没上页的指标与理由。</b>Since-issued CPR、累计违约、累计回收都是「自发行以来」的累计量，'
     '跨不同账龄的信托相加没有指称；债券余额与超额抵押的债券口径不统一（2014-A 报告只按 A/B 级 rated 债券算 OC），'
     '反推的合计会少算 —— 误差不可控，都不做合计。'),
    ('<b>官方重述。</b>官方每期整表重出全部历史，偶尔改旧格（实测量级 1e-6，低于本页写盘精度）。'
     '已入库的月份不覆盖，差异进抓取模块的重述台账。'),
    ('<b>发布节奏。</b>xlsx 没有自述发布日；按 HTTP Last-Modified，2025-09 至 2026-09 共 13 期落在'
     '数据月后第 8–27 天、中位第 13 天（被重传过的期次会显得更晚）。各信托的服务报告每月 15 日分发，'
     '与这份 xlsx 不是同一个发布动作。'),
    _n_trusts_note,
]

SPEC = {
    'ticker': 'slm',
    'name': 'Sallie Mae',
    'title': 'Sallie Mae（SLM）SMB 私人学生贷 ABS 信托月度表现',
    'csv': 'slm.csv',
    'ccy': 'USD',
    'source': ('Source: Sallie Mae Bank, SMB Private Education Loan ABS Trusts Static Pool Information '
               'and Monthly Performance (xlsx) 与各信托 Monthly Servicing Report; '
               '全部合计 / 加权值为本页自算; format after Goldman Sachs GIR'),

    # 头条：两条信用读数。全部列同源（同一份 xlsx），没有慢腿。
    # 'line_only'：开篇只出全历史折线（2014-08 起），不画近 3 年分位带、不出单月同比柱 ——
    # 两条都是比率，分位带在账龄结构一直在变的合计上没有「正常区间」的含义。
    'headline_style': 'line_only',
    'headline_section': '信用读数全历史',
    'headline': [
        {'col': 'dq30p_pct', 'zh': '30 天以上逾期（占 P&I 还款余额）', 'unit': _U_PI, 'fmt': 'pct2'},
        {'col': 'ann_default_pct', 'zh': '年化当期违约率（占 P&I 还款余额）',
         'unit': '% of P&I, annualized', 'fmt': 'pct2'},
    ],
    'season_section': '季节性',
    'groups': GROUPS,
    'slow_cols': [],
    'breaks': 'slm_breaks.csv',
    'glossary': _GLOSSARY,
    'notes': _NOTES,
}
