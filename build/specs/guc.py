# -*- coding: utf-8 -*-
"""创意电子（GUC，3443.TW）单公司页配置。

台湾《证券交易法》要求上市公司于次月 10 日前公告上月营收，所以「有没有月度数据」
在台股不是问题 —— 206 家半导体业公司全部按月披露。选 GUC 的理由是**口径最干净**，
逐条实测过（见下）：

  · **月营收逐月可加总，diff 恒为 0。** 官方 xlsx 逐月加总 vs 审计年报 Net revenue：
    2017 12,160,606 / 2024 25,044,192 / 2025 34,140,978，三年全部 diff=0；
    2026 前 7 月 31,113,539 在 IR xlsx 加总、MOPS t21sc03_115_7_**0**、
    TWSE OpenAPI t187ap05_L 三处逐字相等。
    ⇒ 季度聚合、YTD、TTM 同比在本页全部**合法**，不需要任何免责。
    对照组是世芯-KY（3661）：同样的检验在那边是 **+0.378%**，因为它功能货币是美元、
    新台币月营收是逐月折算值。GUC 合并财报附注原文：「The functional currency of GUC
    and the presentation currency of the consolidated financial statements are both
    New Taiwan Dollars (NT$).」—— 原生 NT$ 记账，无折算噪声。

  · **无并购、无处分、无重述。** 合并财报子公司表全是自设分支（GUC-NA / Japan /
    Europe / Nanjing / Korea / Vietnam），Note 里搜不到任何 acquisition / disposal /
    business combination；官方年度表的 2014(Adjusted) 重述列与原列同为 6,952,281。
    ⇒ 本文件不设 `breaks`。（唯一的会计准则断点是 2013-01 的 ROC GAAP → Taiwan-IFRSs，
    在本序列起点 2017-01 之前，够不着。）

  · **官方逐月给业务拆分**，这是 TSMC 月报里没有的一层：Turnkey（量产/晶圆）与 NRE
    （委托设计）。年度加总与审计过的 Note 17b 逐字相等（2025 Turnkey 25,735,801 /
    NRE 8,032,384 / Others 372,793）。这是本页真正的差异化信息 —— GUC 月营收的
    lumpy 不是噪声，是 NRE 里程碑确认，月度 NRE 占比在 6.3%~68.8% 之间摆动、中位 27.0%。

━━ 📌 落库时**必须对分项求和，不许读 Total 行** ━━━━━━━━━━━━━━━━━━━━━━━━━
官方 xlsx 的 Total 行 **115 个单元格里 61 个是活公式**（`=SUM(B23:B25)` 这种，
2018~2022 整年全是），只有 54 个是字面值。`openpyxl` 默认 `data_only=False` 会静默
读到公式串；`data_only=True` 能读到值，靠的是 Excel 写入的**缓存**，而缓存是发布者
保存工具的副产品 —— 上游某月改用 LibreOffice 或脚本另存，缓存就没了，整块变 None
静默漏年。实测 115 个月的 Total 与分项和无一例外相等，所以对
Turnkey + NRE(&Others) 求和可以完全绕开缓存依赖。这条写在 `fetch/guc.py` 里。

━━ 📌 `NRE & Others` 的合并是真断点，但本序列已经抹平 ━━━━━━━━━━━━━━━━━━━
xlsx 里 2017~2025 每个年份块是 `Turnkey / NRE / Others / Total` 四行，**2026 年起
变成 `Turnkey / NRE & Others / Total` 三行**（IR deck 里同一口径又叫 'NRE & IP'）。
若照 2017-2025 的三列建表，2026 起会一列全空、一列偏高，任何跨 2026-01 的 NRE 占比
时序都会出现假跳变。本序列因此**只存两列**：`revenue_turnkey_ntd_mn` 与
`revenue_nre_other_ntd_mn`（2017-2025 的 NRE+Others 已在落库时合并），口径逐月连续，
所以这里同样不需要 `breaks`。

━━ 📌 本页没有指引桥，也不该有 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`/tsm/` 页顶那句「当季 QTD 已实现 X、距指引中值还差 Y」依赖 `series/tsm_guidance.csv`
的六列（美元绝对区间 + 折算汇率 + 美元实绩）。GUC 六列**逐列无源**，而且不是数据缺失
是对象不存在：2026-01-30 的 4Q25 法说会上管理层明确宣布**停止提供数字财测**，理由是
具体预测「容易被市場過度解讀或誤解」。2026 年三份 IR deck 全文 grep
guidance / outlook / next quarter / forecast 零命中。
其中 `guide_fx_ntd_per_usd` 一列在概念上都不存在 —— TSMC 需要它是因为用美元指引、
用新台币记账，必须公布桥接汇率假设；GUC 功能货币就是新台币，没有这个对象。

同理，本页**不做美元折算腿**。TSMC 每季自报美元营收、还用美元给指引，那条线有官方
实绩可以对账；GUC 从不披露美元营收金额或占比（Note 17 净营收五个维度拆分零美元行），
折出来的只能是分析师构造值。Note 17b 的美国地区占比（2025 年 68.0%、2024 年 31.9%）
是**销售地区**不是**计价货币**，一年之内从 32% 跳到 68% 本身就说明不能当计价货币代理。
"""

import csv
import os

_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'series', 'guc.csv')


# ══════════════════════════════════════════════════════════════════════════════
# 图注里的数一个都不写死，在 import 期从 series/guc.csv 现算。
# 读不到就退回不含数字的定性版本 —— 缺文件不许在 import 期抛异常，
# 否则 monthly_run 会因为一张页的配置炸掉整批（同 build/specs/ndaq.py）。
# ══════════════════════════════════════════════════════════════════════════════
def _rows():
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _f(r, col):
    try:
        v = (r[col] or '').strip()
    except (KeyError, AttributeError):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _nre_share():
    """月度 NRE(&Others) 占当月营收的比重：(最低, 最高, 中位, 样本数)。"""
    xs = []
    for r in _rows():
        tot, nre = _f(r, 'revenue_ntd_mn'), _f(r, 'revenue_nre_other_ntd_mn')
        if tot and nre is not None and tot > 0:
            xs.append(nre / tot * 100.0)
    if not xs:
        return None, None, None, 0
    xs.sort()
    n = len(xs)
    med = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
    return xs[0], xs[-1], med, n


def _span():
    ms = [r['month'] for r in _rows() if _f(r, 'revenue_ntd_mn') is not None]
    return (ms[0], ms[-1], len(ms)) if ms else (None, None, 0)


_LO, _HI, _MED, _N = _nre_share()
_M0, _M1, _MN = _span()

if _N:
    _MIX_NOTE = (
        f'<b>月营收的 lumpy 来自 NRE，不是噪声。</b>本表 {_N} 个月里，NRE（委托设计，'
        f'2026 起官方口径为 NRE &amp; Others）占当月营收的比重在 '
        f'<b>{_LO:.1f}% ~ {_HI:.1f}%</b> 之间摆动、中位 <b>{_MED:.1f}%</b> —— 同一家公司，'
        '某些月份三分之二的营收来自一次性委托设计里程碑，某些月份几乎全是量产晶圆。'
        '所以读本页的环比时应当先看下面这张构成图：尖刺通常能直接归到 NRE 那一块，'
        '给环比加平滑只会把这层信息抹掉。')
else:
    _MIX_NOTE = ('<b>月营收的 lumpy 来自 NRE，不是噪声。</b>NRE（委托设计）按里程碑确认，'
                 '占比逐月摆动很大；读环比时应先看构成图，不要给环比加平滑。')

_ADDITIVE_NOTE = (
    '<b>本页的季度聚合与 YTD 是合法的（已实测，不是推定）。</b>官方 xlsx 逐月加总与'
    '审计年报 Net revenue 三年全部 diff=0（2017 12,160,606 / 2024 25,044,192 / '
    '2025 34,140,978）；2026 前 7 月 31,113,539 在 IR xlsx 加总、MOPS 全市场月表、'
    'TWSE OpenAPI 三处逐字相等。GUC 合并财报附注写明功能货币与表达货币均为新台币，'
    '月营收是原生记账数、不是折算值 —— 这一点与同业世芯-KY（3661）相反，'
    '那家十二个月相加与官方本年累计差 +0.378%。')

_NO_USD_NOTE = (
    '<b>本页没有美元腿，是刻意的。</b>GUC 从不披露美元营收金额或占比（合并财报 Note 17 '
    '净营收五个维度拆分零美元行），把新台币除以外部汇率得到的是分析师构造值，'
    '没有任何官方数可以对账 —— 与 <code>/tsm/</code> 页不同，那边公司每季自报美元营收。'
    'Note 17b 的美国地区占比（2025 年 68.0%、2024 年 31.9%）是<b>销售地区</b>'
    '不是<b>计价货币</b>，一年之内从 32% 跳到 68%，不能拿来当计价货币的代理。')

_NO_GUIDANCE_NOTE = (
    '<b>本页没有指引桥。</b>GUC 已于 2026-01-30 的 4Q25 法说会上明确停止提供数字财测，'
    '理由是具体预测「容易被市場過度解讀或誤解」；2026 年三份 IR deck 全文检索 '
    'guidance / outlook / next quarter / forecast 零命中。这不是数据缺失而是对象不存在，'
    '所以本页不建 guidance 序列、也不拼「距指引中值还差多少」那类句子。')

_SRC_NOTE = (
    '<b>数据源与落库口径。</b>历史取 GUC 投资人关系页「Historical Monthly revenue」'
    '官方 xlsx（单 sheet <code>revenue breakdown</code>，单位 NT$K）。'
    '该文件的 Total 行有 61/115 个单元格是活公式而非字面值，'
    '所以落库一律对 Turnkey 与 NRE(&amp;Others) 两个分项求和，不读 Total 行 —— '
    '实测 115 个月分项和与 Total 无一例外相等。每月发布后 xlsx 的下载 URL 会变'
    '（路径含上传日），因此链接每次从落地页现抓，不写死。')

SPEC = {
    'ticker': 'guc',
    'name':   'GUC',
    'title':  '创意电子（GUC，3443.TW）月度营收',
    'csv':    'guc.csv',
    'ccy':    'TWD',
    'source': 'Source: GUC investor relations monthly revenue disclosure '
              '(guc-asic.com), cross-checked against TWSE MOPS and TWSE OpenAPI; '
              'format after Goldman Sachs GIR',

    # 头条只有一列：台股月营收披露就是一个数。115 个月（2017-01 起）远超底座要求的
    # 24 个月共同历史，同比与 3Y 分位都算得出来。
    'headline': [
        {'col': 'revenue_ntd_mn', 'zh': '月营收', 'unit': 'NT$mn', 'fmt': 'f0c'},
    ],

    'groups': [
        # 两列同单位 ⇒ 同一个桶 ⇒ 一张图上对比。这是本页相对 /tsm/ 多出来的一层，
        # 也是把「月营收波动大」变成「波动可拆」的唯一钥匙。
        {'zh': '营收构成：量产 vs 委托设计（官方逐月拆分）', 'cols': [
            {'col': 'revenue_turnkey_ntd_mn', 'zh': '量产（Turnkey）',
             'unit': 'NT$mn', 'fmt': 'f0c'},
            {'col': 'revenue_nre_other_ntd_mn', 'zh': '委托设计（NRE & Others）',
             'unit': 'NT$mn', 'fmt': 'f0c'},
        ]},
    ],

    # 次轴走 12 个月滚动同比而不是单月同比：台股月营收受工作日数、农历年错位与
    # NRE 里程碑三重推动，单月同比的毛刺可以大到与趋势符号相反。
    # granularity='monthly_total' —— 这一列本身就是当月合计，不是日均。
    'ttm_yoy': [{
        'zh': '月营收',
        'granularity': 'monthly_total',
        'level': {'col': 'revenue_ntd_mn', 'zh': '月营收',
                  'unit': 'NT$mn', 'fmt': 'f0c'},
    }],

    'notes': [_ADDITIVE_NOTE, _MIX_NOTE, _NO_USD_NOTE, _NO_GUIDANCE_NOTE, _SRC_NOTE],
}
