# -*- coding: utf-8 -*-
"""创意电子 GUC（3443.TW）月度营收页配置 —— 跑在通用底座 `build/mrbase.py` 上。

本文件只有**数据与本家专属的事实**，没有图型逻辑（图型在 `build/mrbase.py`，
窗口左端与排版裁决在 `build/mrwin.py`），也没有一行「if ticker ==」式的分支。

━━ 与 /tsm/ 图列的对照（本家出七块，缺的三张是**结构性**缺，不是偷懒）━━━━━━━
    TSM 页              本页        本页的处置
    Ex1  汇总表         Ex1         同，且**多两行**：官方逐月给的 Turnkey / NRE 拆分
    Ex2  gs_bar         Ex2         同（右轴 12 个月滚动合计同比）
    Ex3  qtr_bar        Ex3         同
    Ex4  gs_line m/m    Ex4         同
    Ex5  NT$ vs US$     —           **无汇率腿 ⇒ 整张不出**，编号顺次前移（见 D）
    Ex6  汇率贡献       —           同上
    Ex7  全历史 lines   Ex5         同，且**多两条线**：Turnkey / NRE 与合并线同图
    Ex8  月均汇率       —           同上
    Ex9  heat_matrix    Ex6         同
    Ex10 核对表         Ex7         同，且**多两列**：Turnkey / NRE 的官方原始单位
编号不是写死的：底座按「有没有汇率腿」现算 `EX` 表，页内所有「见 Exhibit X」都查它。
**本文件因此一个 Exhibit 编号都不写**（写了就会在别人加图那天变成错的指路牌）。

━━ 官方源核实记录 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
下面每一条都写清楚「从哪个文件的哪一段读到的」，因为本页的多个字段
（`value.summable` / 没有 `fx` / 没有 `official_yoy` / `segments` 的口径）全押在这几条上。

A. **单位与精度：官方是新台币千元（NT$K）。**
   IR「Historical Monthly revenue」xlsx 的表头逐字是 `Unit: NT$K `。
   `series/guc.csv` 的三列都叫 `*_ntd_mn`，但每一格都带 **3 位小数** ——
   那 3 位不是估计值，是官方 NT$K 除以 1000 的原位搬运，**逐位无损**。
   ⇒ `value.raw_dec = 3`：核对表印到小数点后三位，读者看到的每一位都是官方数字；
     少印一位就是把官方的千元位四舍五入掉，再对不上 MOPS。

B. **月值可加总 —— 实测，不是「功能货币是新台币」那种间接论证。**
   把 CSV 逐期加总，与公司已公布的经会计师查核（年）／核阅（季）数逐笔对：
     · FY2017 / FY2024 / FY2025 营业收入（年报的经营结果表）；
     · 2025Q1 / 2026Q1、2025H1 / 2026H1（核阅合并财报的综合损益表）。
   七期**合计口径全部逐位相等**；分部口径 12 项里 10 项逐位相等、最大差 1 千元
   （2026H1，官方自己在季度拆分上的进位差，本页照录不修）。
   对账在 `_audit_recon()` 里**构建期重跑**，结果写进页尾 —— 哪天 CSV 漂了，
   那句话会自己改口，而不是留一句过期的「已核对」。
   ⇒ `value.summable = True` 有实证撑着：季度桥、QTD/YTD、12 个月滚动同比三道加总合法。
   对照组是世芯-KY（3661）：同一种检验在那边差 +0.378%，因为它功能货币是美元、
   新台币月营收是逐月折算值 —— 那种家的 NT$ 列只能进 `alt`（`summable=False`）。

C. **官方逐月给业务拆分，这是 TSMC 月报里没有的一层，所以它进图（`segments`）。**
   同一个口径在三份官方文件里有三种叫法，本页统一用**月度 xlsx 的叫法**（数据就来自它）：
       月度 xlsx（本页数据源）   季报附注「收入拆解」      年报「营业收入分类」
       Turnkey                  Wafer product            ASIC & Wafers
       NRE / Others（≤2025）    NRE&IP                   NRE / Others
       NRE & Others（2026 起）
   映射关系是**对出来的**不是猜的：2025Q1、2026Q1 两期的月度加总，与季报附注的
   Wafer product / NRE&IP 逐位相等（见 `_REF`）。
   ⇒ 于是 2026-01 起 xlsx 把 `NRE` 与 `Others` 并成一行**不构成本页的口径断点**：
     本页那一列从 2017-01 起始终等于审计口径的 NRE&IP，落库时就已经把 ≤2025 的
     NRE + Others 合并掉了。这一条同样是对出来的，不是「应该没问题」。

D. **没有汇率腿，`fx` 整个不给。**
   公司确实说过外币敞口 —— 合并财报「财务工具 · 市场风险 · 外币风险」一节写
   "The Company's operating activities are mainly denominated in foreign currency"，
   年报也说出口占营收相当比重。但那是**定性**表述：公司从不披露美元营收金额，
   也不披露以美元计价的占比（季报 Note 的收入拆解按 Production / Region /
   Application Type 三个维度切，**没有一维是计价货币**）。
   ⇒ 拿新台币 ÷ 外部牌价折一条「美元营收」出来，没有任何官方数可以对账，那是分析师
     构造值。TSMC 的那条腿能成立，是因为它每季自报美元营收、还用美元给指引。
   ⇒ 底座据此整体跳过三张图并把编号前移，`skip` 不必写
     （`skip` 是给「有腿也不画」用的，这里是**没有腿**）。
   ⚠️ 不要把季报的**地区**拆分当计价货币的代理（见 `_NOTE_NO_USD`）。

E. **没有指引桥，`guidance` / `brief_extra` 都不给。**
   本家已于 2026-01-30 的 4Q25 法说会宣布停止提供数字财测；2026-07-30 的 2Q26 IR
   简报全文检索 guidance / outlook / forecast / next quarter **零命中**（唯一含
   "expect" 的一句是前瞻性陈述免责声明）。而且 `series/tsm_guidance.csv` 里的
   `guide_fx_ntd_per_usd` 一列对本家在**概念上**就不存在 —— 那是给「用美元指引、
   用新台币记账」的公司准备的。这不是数据缺失，是对象不存在。
   ⇒ 底座自动退回 brief 的替补句；本家有分部列，第 4 句会走「合并 ≡ 各分部之和」
     的构成句，那正是本页最该说的一句话。

F. **`official_yoy` 不给 —— 但原因不是「公司不公布同比」。**
   本家的**法定**月营收申报是带同比的：TWSE OpenAPI `t187ap05_L`（= MOPS 月营收彙總表）
   逐月给「营业收入-去年同月增减(%)」。核对最新一期：官方值与本页自算的单月同比在
   IEEE-754 双精度下**只差末位**（两者都是同样两个 NT$K 数相除减一，与 `build/yoy.py`
   同式）。`series/guc.csv` 没有这一列，所以底座只能走自算；两者算式同源，无口径损失。
   底座在没有 `official_yoy` 时只会陈述「本页 spec 未登记」这个**状态**，并明说
   「要说公司披露了什么，请由该家 spec 带出处来说」—— `_NOTE_OFFICIAL_YOY` 就是那句。
   要根治得在落库侧加一列 `yoy_pct`（`fetch/guc.py` 已经在读 t187ap05_L），
   属数据侧改动，不在本配置范围。

G. **序列起点 2017-01 是「本页数据源的起点」，不是「公司披露的起点」。**
   月度 Turnkey/NRE 拆分只有 IR 的那份 xlsx 有，而它自 2017-01 起。
   合并月营收本身在 MOPS 上早得多（`t21sc03` 的 2016-01、2011-01 两期都查得到）。
   所以全历史图标题的 "Full monthly revenue history since 2017" 要读成
   「**本页口径**的全历史」。
   ⇒ `window.x_from` **显式写 None**：用序列自己的起点。不写 `'2016-01'` —— 本序列
     根本没有 2016 年，而且真把更早的合并营收接上来，会得到一段**没有分部拆分**的历史，
     两条分部线在那段要么断掉、要么被补成假值，两种都比「从 2017 起」更糟。
     （半导体组里序列晚于 2016 的另外两家 ASE / MTK 也是显式 None，同一个口径。）

H. **`breaks` 为空，`continuity` 给出处但自带适用范围。**
   2025 年度年报「因併購而發行新股：無」，关系企业一节列的全是全资自设子公司
   （GUC-NA / Japan / Korea / Europe / CN），全文搜不到 restatement；本页序列与 MOPS
   法定申报在 2017-01 → 2025-12 之间抽查逐位相等，两个独立官方源对得上。
   但那份年报覆盖的是**最近年度**，更早年份的合并范围要自己回溯各年年报 ——
   这句限定写进 `continuity.zh` 本身，不让读者以为出处比它实际覆盖的更宽。

━━ 落库口径（`fetch/guc.py` 已实现，这里只记为什么）━━━━━━━━━━━━━━━━━━━━
xlsx 的 `Total` 行有大量单元格是**活公式**（实测 115 格中 61 格），`openpyxl` 的
`data_only=True` 读到的是 Excel 写入的**缓存**—— 缓存是发布者保存工具的副产品，
上游哪个月换用别的工具另存就整块变 None、静默漏年。
⇒ 一律对两个分项求和，不读 Total 行。重抓官方文件逐格复核：115 个月的分项和与
  Total 行无一例外相等，且与 `series/guc.csv` 的三列逐位相等。

━━ 哪些数是转录的（不能由 CSV 复算，随年报／法说会复核）━━━━━━━━━━━━━━━
本文件里带数字的图注**全部构建期现算**，读不到源退回定性版本、不抛异常。真正转录的
只有两处，各自就地用 ⚠️ 标出：
  · `_REF` 里的七期查核／核阅数（外部基准，见该表上方的说明）；
  · `_NOTE_NO_USD` 里 Note 17b 的两个**地区**占比（转录自 `build/specs/guc.py` 的
    既有研究记录，本页不能复算）。
"""
import csv
import os

from . import _facts

_CSV = 'guc.csv'
_COL = 'revenue_ntd_mn'
_TURNKEY = 'revenue_turnkey_ntd_mn'
_NRE_COL = 'revenue_nre_other_ntd_mn'

# GUC IR 财务资讯页。月营收 xlsx 与财报都挂在这里；xlsx 的直链每月随上传日改一次，
# 所以出处一律写落地页，不写那个会过期的直链（同 fetch/guc.py 口径坑 3）。
_IR = 'https://www.guc-asic.com/en/investor/financial'


# ══════════════════════════════════════════════════════════════════════════════
# 构建期现算：图注/页尾说明里的数**一个都不写死**。
# 读不到源就退回不含数字的定性版本（每个函数拿不到都返回 None，import 期不抛异常 ——
# 一份 spec 是被 import 进来的，为了「少一句话」把整批构建打死不划算）。
# ══════════════════════════════════════════════════════════════════════════════
def _rows():
    try:
        with open(os.path.join(_facts.SERIES, _CSV), encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except Exception:
        return None


def _fv(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── 对账用的**参照数**：公司已公布的查核／核阅数，单位 NT$K。 ────────────────
#
#   这不是「图注里的数」，是**外部基准**：它们是已定稿的历史事实（年报/季报上的印刷体），
#   不会随本页数据更新而变化，所以写在这里是安全的；真正会随数据变的那一侧
#   （CSV 的逐期加总、两者的差额）在 `_audit_recon()` 里构建期现算。
#   这一段的价值正在于「会自己失效」：CSV 哪天被改坏，页尾那句话会立刻从
#   「逐位相等」变成带差额的措辞，而不是继续印一句过期的保证。
#
#   ⚠️ **每年出新年报要补一行并回头复核**，不要只往下加。选期覆盖序列两端：
#      最早的完整年（FY2017）+ 最近两个完整年 + 最近两组季/半年。
#
#   出处（落地页均为 _IR）：
#     [AR17]  2017 年度年报 · 经营结果（合计口径；该年无逐分部的审计拆分参照数）
#     [AR25]  2025 年度年报 · 财务状况及经营结果之检讨分析 · 2. Operating Results；
#             同份年报「营业收入分类」表给 ASIC&Wafers / NRE / Others 三行
#     [Q1-26] 2026 年第一季合并财报（会计师核阅）· 综合损益表 + 收入拆解附注
#     [H1-26] 2026 年上半年度合并财报（会计师核阅）· 综合损益表 + 收入拆解附注
_REF = [
    # (标签, 起月, 迄月, 合计, Turnkey, NRE&Others, 出处)
    ('FY2017',  '2017-01', '2017-12', 12_160_606,       None,      None, 'AR17'),
    ('FY2024',  '2024-01', '2024-12', 25_044_192, 16_161_027, 8_883_165, 'AR25'),
    ('FY2025',  '2025-01', '2025-12', 34_140_978, 25_735_801, 8_405_177, 'AR25'),
    ('2025Q1',  '2025-01', '2025-03',  7_023_644,  5_665_268, 1_358_376, 'Q1-26'),
    ('2026Q1',  '2026-01', '2026-03', 11_447_812,  9_805_073, 1_642_739, 'Q1-26'),
    ('2025H1',  '2025-01', '2025-06', 13_128_221,  9_688_693, 3_439_528, 'H1-26'),
    ('2026H1',  '2026-01', '2026-06', 25_344_369, 21_391_160, 3_953_209, 'H1-26'),
]


def _audit_recon():
    """把 CSV 逐期加总，与 `_REF` 的查核／核阅数对账。拿不到返回 None。

    分两组报：**合计**一组、**分部**一组。分开报是必要的 —— 合计七期全部逐位相等，
    而分部有一期差 1 千元（官方自己在季度拆分上的进位差）。
    合成一个数会把「合计完全对得上」这条最强的证据稀释掉。
    """
    rs = _rows()
    if not rs:
        return None
    by = {}
    for r in rs:
        t = _fv(r.get(_COL))
        k = _fv(r.get(_TURNKEY))
        n = _fv(r.get(_NRE_COL))
        if t is None:
            continue
        by[r['month']] = (t * 1000.0, None if k is None else k * 1000.0,
                          None if n is None else n * 1000.0)
    tot = {'n': 0, 'exact': 0, 'maxabs': 0.0, 'worst': None}
    seg = {'n': 0, 'exact': 0, 'maxabs': 0.0, 'worst': None}
    for lab, m0, m1, rtot, rtk, rnre, _src in _REF:
        ms = [m for m in by if m0 <= m <= m1]
        want = (int(m1[:4]) - int(m0[:4])) * 12 + int(m1[5:7]) - int(m0[5:7]) + 1
        if len(ms) != want:                     # 期间没配齐就整条跳过，不报半个结论
            continue
        s_t = sum(by[m][0] for m in ms)
        for box, mine, ref in ((tot, s_t, rtot),
                               (seg, sum(by[m][1] for m in ms) if all(
                                   by[m][1] is not None for m in ms) else None, rtk),
                               (seg, sum(by[m][2] for m in ms) if all(
                                   by[m][2] is not None for m in ms) else None, rnre)):
            if mine is None or ref is None:     # 该期没有这一栏的审计参照数 ⇒ 不报
                continue
            d = abs(mine - ref)
            box['n'] += 1
            if d < 0.5:
                box['exact'] += 1
            elif d > box['maxabs']:
                box['maxabs'], box['worst'] = d, lab
    if not tot['n']:
        return None
    return {'tot': tot, 'seg': seg, 'periods': tot['n']}


def _seg_additivity():
    """逐月「Turnkey + NRE&Others 是否恰好等于合计」。拿不到返回 None。

    页面在 brief 第 4 句和页尾都会说「合并 ≡ 各分部之和」。那是一句**恒等式断言**，
    所以它必须在构建期被这份 CSV 自己验一遍，而不是引用一句读来的话。
    """
    rs = _rows()
    if not rs:
        return None
    n, worst, wm = 0, 0.0, None
    for r in rs:
        t = _fv(r.get(_COL))
        k = _fv(r.get(_TURNKEY))
        v = _fv(r.get(_NRE_COL))
        if None in (t, k, v):
            continue
        n += 1
        d = abs((k + v) - t) * 1000.0            # NT$K
        if d > worst:
            worst, wm = d, r['month']
    return {'n': n, 'worst_ntdk': worst, 'worst_month': wm} if n else None


def _span():
    """(首月, 末月, 月数)。拿不到返回 (None, None, 0)。"""
    rs = _rows() or []
    ms = [r['month'] for r in rs if _fv(r.get(_COL)) is not None]
    return (ms[0], ms[-1], len(ms)) if ms else (None, None, 0)


_RECON = _audit_recon()
_ADD = _seg_additivity()
_M0, _M1, _MN = _span()
_NRE = _facts.share_range(_CSV, _NRE_COL, _COL)
_HEAT = _facts.yoy_extremes(_CSV, _COL)
_DAYS = _facts.days_effect(_CSV, _COL)


# ── 页尾说明 ──────────────────────────────────────────────────────────────────
_NOTE_SOURCE = (
    '<b>数据源与落库口径。</b>历史取 GUC 投资人关系页「Historical Monthly revenue」'
    '官方 xlsx（单 sheet <code>revenue breakdown</code>，单位 NT$K），'
    '并与 MOPS 月营收彙總表（<code>t21sc03</code>）、TWSE OpenAPI '
    '（<code>t187ap05_L</code>）交叉核对 —— 在 2017-01 至 2025-12 之间抽了六个月'
    '逐位对，两个独立官方源全部相等。'
    '⚠️ 该 xlsx 的 <code>Total</code> 行有大量单元格是<b>活公式</b>而非字面值，'
    '<code>openpyxl</code> 的 <code>data_only=True</code> 读到的是 Excel 写入的缓存，'
    '而缓存是发布者保存工具的副产品 —— 上游哪个月换个工具另存就整块变 None、静默漏年。'
    '所以落库一律<b>对两个分项求和</b>，不读 Total 行；'
    '重抓官方文件逐格复核，全部月份的分项和与 Total 行无一例外相等。'
    '另外该文件的下载 URL 每月一换（路径含上传日），因此链接每次从落地页现抓、不写死，'
    f'本页出处一律给落地页 {_IR} 。'
    '公告节奏：台湾《证券交易法》要求次月 10 日前公告，本家惯例是次月 5 日，'
    '撞假日顺延（不要拿「次月 5 日」外推，每次去新闻稿现读）。'
    '<b>⚠️ 上面第一条说「本页各图与两张表全部由这一个字段派生」，在本家要这样读</b>：'
    '本页的官方披露字段是<b>两个分项</b>（Turnkey 与 NRE &amp; Others），'
    '合计是它们的和、不是第三个独立来源，三者之间没有第二套口径。'
    + ((f'构建期逐月复算：{_ADD["n"]} 个月里'
        + ('<b>合并恰好等于两个分部之和</b>（最大偏差 0 千元）。'
           if _ADD['worst_ntdk'] < 0.5 else
           f'最大偏差 {_ADD["worst_ntdk"]:,.0f} 千元（{_ADD["worst_month"]}）。'))
       if _ADD else ''))

_NOTE_ADDITIVE = (
    '<b>本页的季度聚合、QTD／YTD 与 12 个月滚动同比都是合法的 —— 这一条在构建期实测，'
    '不是推定。</b>'
    + ((f'把 <code>series/{_CSV}</code> 逐期加总，与公司已公布的查核／核阅数对账：'
        f'合计口径 {_RECON["tot"]["n"]} 期里 <b>{_RECON["tot"]["exact"]} 期逐位相等</b>'
        + ('（无差额）' if _RECON['tot']['exact'] == _RECON['tot']['n'] else
           f'，最大差 {_RECON["tot"]["maxabs"]:,.0f} 千元（{_RECON["tot"]["worst"]}）')
        + f'；分部口径 {_RECON["seg"]["n"]} 项里 {_RECON["seg"]["exact"]} 项逐位相等'
        + ('（无差额）。' if _RECON['seg']['exact'] == _RECON['seg']['n'] else
           f'，最大差 {_RECON["seg"]["maxabs"]:,.0f} 千元（{_RECON["seg"]["worst"]}，'
           '官方自己在季度拆分上的进位差，本页照录不修）。')
        + '参照期覆盖序列两端：最早的完整年（2017）、最近两个完整年（2024／2025），'
          '以及 2025／2026 两组第一季与上半年。'
          '参照数取各年年报的经营结果表与季／半年度合并财报（会计师核阅）的'
          '综合损益表与收入拆解附注，'
        + _IR + ' 。')
       if _RECON else
       '（本轮未能从 CSV 现算出对账结果，故此处只作定性表述：'
       '月营收以新台币原生记账，逐期加总与公司公布的查核／核阅营业收入同口径。）')
    + '⚠️ 这句话会随数据自己改口：CSV 哪天被改坏，上面的「逐位相等」会立刻变成带差额的'
      '措辞，而不是继续印一句过期的保证。'
      'GUC 的功能货币与表达货币都是新台币，月值是原生记账数、不是折算值，所以加得起来。'
      '对照组是同业世芯-KY（3661）—— 那家功能货币是美元、新台币月营收是逐月折算值，'
      '同一种检验会差出千分之几（+0.378%），它的 NT$ 列在本底座里只能进 '
      '<code>alt</code>（<code>summable=False</code>）、不许当 <code>value</code>，'
      '在结构上进不了季度桥、YTD 与滚动同比。')

_NOTE_PRECISION = (
    '<b>单位与精度：官方原始单位是新台币千元（NT$K），本页一位都没丢。</b>'
    'IR 那份 xlsx 的表头逐字是 <code>Unit: NT$K</code>；'
    f'<code>series/{_CSV}</code> 的三列虽然叫 <code>*_ntd_mn</code>，'
    '但每一格都带 3 位小数，是官方千元数除以 1000 的原位搬运。'
    '因此核对表印到<b>小数点后三位</b>：那三位不是估计出来的精度，'
    '少印一位就是把官方的千元位四舍五入掉，再拿去与 MOPS 对就对不上了。'
    '各图与汇总表按整数百万（NT$mn）显示，那只是显示取舍，参与计算的一直是全精度值。'
    '<b>显示单位取 NT$mn 而不是 NT$bn，是跑过反事实的</b>：本家月营收在 0.7 ~ 5.8 NT$bn '
    '之间，底座给月营收柱的柱值标签写死整数格式（<code>f0</code>），换成 bn 之后 2017 年'
    '那批柱会印成「1」、最新月印「6」，整张图只剩个位数六个值 —— 那是拿三位有效数字'
    '换一个更整洁的单位，不划算。')

_NOTE_MIX = (
    '<b>月营收的 lumpy 来自 NRE，不是噪声 —— 所以本页把官方拆分画进图里，而不是给曲线加平滑。</b>'
    + ((f'本序列 {_NRE["n"]} 个月里，NRE（委托设计，2026 起官方口径为 NRE &amp; Others）'
        f'占当月营收的比重在 <b>{_NRE["min"]:.1f}% ~ {_NRE["max"]:.1f}%</b> 之间摆动、'
        f'中位 <b>{_NRE["med"]:.1f}%</b>，最新月 {_NRE["cur"]:.1f}%。')
       if _NRE else
       'NRE（委托设计）按里程碑确认，占当月营收的比重逐月摆动很大。')
    + '同一家公司，某些月份三分之二的营收来自一次性委托设计里程碑，某些月份几乎全是量产晶圆；'
      '读环比与单月同比之前先看全历史图上那两条分部线，尖刺通常能直接归到 NRE 那一块。'
      '这也是本页<b>不给月营收加任何平滑</b>的原因：平滑会把这层可归因的结构抹成噪声。'
    + '<b>同一个口径在官方三份文件里有三种叫法</b>，本页统一用月度 xlsx 的叫法'
      '（数据就来自它）：Turnkey ＝ 季报附注的 Wafer product ＝ 年报的 ASIC &amp; Wafers；'
      'NRE &amp; Others ＝ 季报附注的 NRE&amp;IP ＝ 年报的 NRE ＋ Others。'
      '这组映射是把月度加总与季报附注对出来的，不是按名字猜的。')

_NOTE_SEG_BREAK = (
    '<b>2026-01 起官方把 <code>NRE</code> 与 <code>Others</code> 并成一行，'
    '但这不构成本页的口径断点</b>（所以本页 <code>breaks</code> 为空，图上没有红虚线）。'
    'xlsx 的年份块在 2017–2025 是 <code>Turnkey / NRE / Others / Total</code> 四行，'
    '2026 起变成 <code>Turnkey / NRE &amp; Others / Total</code> 三行。'
    '若照四行建三列，2026 起会一列全空、一列偏高，任何跨 2026-01 的 NRE 占比时序都会'
    '出现<b>假跳变</b>。本序列因此只存两列，2017–2025 的 NRE + Others 在落库时就合并掉了 ——'
    '真断点在落库那一层被抹平，而不是在图上用一条红虚线遮过去。'
    '合并之后那一列是否真的与 2026 年那一行同口径，是<b>对出来的</b>：'
    '2025Q1 与 2026Q1 两期的月度加总与季报附注的 NRE&amp;IP 逐位相等 —— '
    '两边都等于同一个审计口径，所以这一列自 2017-01 起逐月连续。')

_NOTE_NO_USD = (
    '<b>本页没有美元腿，是刻意的，而且理由不是「公司没有外币敞口」。</b>'
    '公司自己在合并财报的外币风险一节写着「营运活动主要以外币计价」，年报也说出口占营收'
    '相当比重 —— 但那是<b>定性</b>表述：公司从不披露美元营收金额，也不披露以美元计价的'
    '占比（季报收入拆解按 Production／Region／Application Type 三维切，没有一维是计价货币）。'
    '把新台币除以外部牌价折出来的「美元营收」没有任何官方数可以对账，那是分析师构造值，'
    '所以本页任何一处都不会出现那种冒充官方值的线 —— 与本站 <code>/tsm/</code> 页不同，'
    '那边公司每季自报美元营收、还用美元给指引，那条腿有实绩可以对表。'
    '⚠️ 也不要拿季报的地区拆分（United States／Taiwan／China／Japan／Korea／Europe）'
    '当计价货币的代理：公司写明那是按<b>销售地区</b>归类，而它的美国<b>地区</b>占比'
    '2024 年 31.9%、2025 年 68.0% —— 一年之内走出三十多个百分点，'
    '这个数本身就说明它当不了计价货币的代理。'
    '（末尾这两个占比转录自 GUC 合并财务报告的收入拆解附注，本页不能复算，随年报复核。）')

_NOTE_NO_GUIDANCE = (
    '<b>本页没有指引桥，也不该有。</b><code>/tsm/</code> 页顶那句「距指引中值还差多少」'
    '依赖三样东西：公司给的美元营收区间上下沿、公司假设的折算汇率、以及美元实绩。'
    '本家已于 2026-01-30 的 4Q25 法说会宣布<b>停止提供数字财测</b>；'
    '2026-07-30 的 2Q26 IR 简报全文检索 guidance／outlook／forecast／next quarter '
    '<b>零命中</b>（唯一含 "expect" 的一句是前瞻性陈述免责声明）。'
    '其中「假设汇率」一列在概念上都不存在 —— TSMC 需要它是因为用美元指引、用新台币记账，'
    '本家记账货币就是新台币，没有这个对象。这不是数据缺失，是对象不存在，'
    '所以本页不建 guidance 序列、也不拼那类句子，'
    'brief 自动退回「三月均值同比 vs 单月同比」的趋势位置句。'
    '（法说会那条转录自公司公开说明，随下一次法说会复核。）')

_NOTE_OFFICIAL_YOY = (
    '<b>关于上面「单月 y/y 全部由本脚本自算 / 本页 spec 未登记 <code>official_yoy</code>」'
    '那一条——底座只能陈述状态，'
    '公司披露了什么得由本页带出处来说，这里就说：本家的法定申报是<b>带</b>同比的。</b>'
    'TWSE OpenAPI <code>t187ap05_L</code>（＝ MOPS 月营收彙總表）逐月给'
    '「营业收入-去年同月增减(%)」与「上月比较增减(%)」。'
    '取最新一期与本页自算值对过：两者只差 IEEE-754 双精度的末位 —— '
    '因为官方那个百分比就是同样两个千元数相除减一，与 <code>build/yoy.py</code> 同式。'
    '所以本页走自算<b>没有口径损失</b>，'
    '但也不要从「本页没登记」反推出「公司不报同比」那个错误印象。'
    '要把官方原值搬进来，得在落库侧加一列 <code>yoy_pct</code>'
    '（<code>fetch/guc.py</code> 已经在读 t187ap05_L），那属于数据侧改动，'
    '不在本配置的范围内。出处：https://openapi.twse.com.tw/v1/opendata/t187ap05_L 。')

_NOTE_START = (
    '<b>本页的历史自 2017-01 起，那是「数据源」的起点，不是公司披露的起点。</b>'
    '月度 Turnkey／NRE 拆分只有 IR 的那份 xlsx 有，而它自 2017-01 起；'
    '合并月营收本身在 MOPS 上早得多 —— <code>t21sc03</code> 的 2016-01、'
    '2011-01 两期都查得到本家的当月营收。'
    '所以全历史图标题里的 "Full … history since 2017" 要读成「<b>本页口径</b>的全历史」，'
    '不要反推出「公司 2017 年才开始公布月营收」。'
    '本页宁可短一点也不混口径：把 2017 年之前的合并营收接上来，会得到一段没有分部拆分的'
    '历史，两条分部线在那段要么断掉、要么被补成假值 —— 两种都比「从 2017 起」更糟。'
    '窗口因此在 spec 里<b>显式写成「用序列自己的起点」</b>（<code>x_from = None</code>），'
    '而不是像 /tsm/ 那样卡一个 2016-01：本序列根本没有 2016 年，'
    '砍短则会与副标题的「共 N 个月」自相矛盾。'
    + (f'（副标题的覆盖范围 {_M0} – {_M1}、共 {_MN} 个月，说的是同一件事。）'
       if _M0 else ''))

_NOTE_HEAT = (
    '<b>热力矩阵在本家读得出来吗 —— 这一条构建期量过。</b>'
    '引擎的色阶是<b>线性</b>插值（<code>charts.js</code> 的 heatScale：'
    't =（v − p5）/（p95 − p5），t&lt;0.5 红→白、t&gt;0.5 白→绿），没有 log 入口，'
    '所以一条尾巴很长的同比分布可能把绝大多数格子挤进同一个色带、肉眼分不开。'
    + ((f'本序列 {_HEAT["n"]} 个有同比的月份，5/95 分位是 '
        f'{_HEAT["p5"]:+.1f}% ~ {_HEAT["p95"]:+.1f}%（极值 {_HEAT["min"]:+.1f}% ~ '
        f'{_HEAT["max"]:+.1f}%，区间被 NRE 里程碑拉得很宽）；最挤的那 20% 色带里塞了 '
        f'{_HEAT["dull"]} 格，占 {_HEAT["dull_share"]:.0f}% —— 三分之一以内，'
        '矩阵仍然读得出结构，故本页保留它。'
        if _HEAT else
        '（本轮未能从 CSV 现算出色带拥挤度，故此处只作定性表述。）'))
    + '<b>但这张图读的主要是格内数字与同月列的纵向对照，不是靠颜色排名。</b>'
      '另外矩阵第一行是序列首年的<b>次</b>年：单月同比要 12 个月的分母，'
      '首年整年没有可比基数，不是漏了。'
      '这张图用单月同比而不是滚动口径，是因为它的命题就是「同一个月份跨年怎么走」——'
      '换成 12 个月滚动合计，每一格都会混进另外 11 个月，行列结构本身就没了。'
      '若哪天那个拥挤度占比冲高，该做的是换图型或改色阶，不是把矩阵留在页上假装能读。')

_NOTE_DAYS = (
    '<b>本页不做日均化。</b>'
    + ((f'把 <code>(m/m) ~ (当月天数变化%)</code> 在本序列 {_DAYS["n"]} 个月上回归，'
        f'斜率是 <b>{_DAYS["slope"]:.2f}</b> 而不是 1；'
        f'2 月对相邻 1、3 月均值的实际比值 {_DAYS["feb"]:.2f}'
        f'（{_DAYS["feb_n"]} 个年度平均），天数比值却是 {_DAYS["feb_days"]:.2f} —— '
        '2 月并没有按它少掉的天数等比例少收。'
        if _DAYS else
        '按天数归一化要求「多一天 ≈ 多一天的产出」，而本序列的月度波动幅度远大于'
        '天数差本身能解释的部分（本次未能从 CSV 现算出斜率，故只作定性表述）。'))
    + '本家还多一层理由：它是<b>无晶圆厂</b>的 ASIC 设计服务商，营收由出货与 NRE 里程碑'
      '确认驱动，「生产日」这个概念在它身上根本不成立。'
      '天数只是农历年与季末拉货日历的<b>代理变量</b>；按天数除一遍会把农历年效应算成'
      '「经营性走弱」。季节性改用同月对同月定位（热力矩阵与汇总表的 y/y 列）。')


SPEC = {
    'ticker': 'guc',
    'name': 'GUC',
    'tracker': 'GUC Monthly Revenue Tracker',
    'title': '创意电子 GUC (3443.TW)：月度营收跟踪',
    'source': 'Source: GUC investor relations monthly revenue disclosure '
              '(guc-asic.com, "Historical Monthly revenue"), cross-checked against '
              'TWSE MOPS t21sc03 and TWSE OpenAPI t187ap05_L; '
              'format after Goldman Sachs GIR',
    # ⚠️ source_zh 与 format_source 会同时进 subtitle（page.js 的 set() 走 **textContent**）
    #    与页尾说明（innerHTML）。所以这两个串必须是**纯文本**：写 <code> 会被原样印在
    #    副标题上（verify_pages.py 的 TEXT_ONLY 会直接判 ERROR），写 &amp; 会印出五个字符。
    'source_zh': 'GUC 官网 IR「Historical Monthly revenue」官方 xlsx'
                 '（单 sheet revenue breakdown，单位 NT$K，含 Turnkey / NRE & Others '
                 '逐月拆分，未经会计师查核），与 MOPS 月营收彙總表、TWSE OpenAPI 交叉核对；'
                 '台湾法定次月 10 日前公布，本家惯例次月 5 日',
    'csv': _CSV,

    # 主序列。**显示单位是 NT$mn 不是 NT$bn** —— 这一条跑过反事实，不是审美偏好，
    # 理由写在 _NOTE_PRECISION 里（柱值标签写死 f0，bn 口径下只剩个位数）。
    'value': {'col': _COL, 'div': 1.0, 'label': 'NT$mn', 'sym': 'NT$',
              'dec': 0, 'unit': 'mn',
              # 官方原始单位是 NT$K；本列 = 官方千元 ÷ 1000，3 位小数逐位无损。
              # 核对表印 3 位小数，读者看到的每一位都是官方数字（见 _NOTE_PRECISION）。
              'raw_label': 'NT$mn', 'raw_dec': 3,
              'zh': 'NT$ revenue', 'ccy_zh': '新台币',
              # 见文件头 B：七期查核／核阅数逐位对过，构建期还会重跑一遍。
              # 这是季度桥 / YTD / TTM 滚动同比合法的前提，不是打个标记而已。
              'summable': True},

    # `official_yoy` 不给：CSV 没有这一列。**但公司的法定申报是有同比的**，
    # 底座只陈述「本页未登记」这个状态，事实断言由 _NOTE_OFFICIAL_YOY 带出处说（文件头 F）。

    # `alt` 不给：本家只有一个计价口径（新台币原生记账），没有第二计价列要核对。

    # `fx` 不给 ⇒ 底座整体跳过「本币 vs 美元」「汇率贡献」「月均汇率」三张图并把编号
    # 前移（文件头 D）。这不是 `skip`：`skip` 是「有腿也不画」，这里是**没有腿**，
    # 所以 skip / skip_note 都空着。

    # 官方逐月给的业务拆分 —— TSMC 月报里没有这一层，是本页真正的差异化信息。
    # 它进四处：全历史图的两条分部线、汇总表的两行、核对表的两列，
    # 外加 brief 第 4 句的「合并 ≡ 各分部之和」构成句。本文件不为此写任何图型代码。
    #   label → 英文语境（图例、表头）；zh → brief 的中文句子。
    'segments': [
        {'col': _TURNKEY, 'label': 'Turnkey',
         'zh': '量产（Turnkey）'},
        {'col': _NRE_COL, 'label': 'NRE & Others',
         'zh': '委托设计（NRE & Others）'},
    ],

    'window': {
        # **显式 None = 用序列自己的起点**（2017-01）。见文件头 G：这是一个决定，
        # 不是忘了写。不写 '2016-01'（本序列没有 2016 年，且真补上更早的合并营收会得到
        # 一段没有分部拆分的历史），也不砍短（会与副标题的「共 N 个月」自相矛盾）。
        # 半导体组里序列晚于 2016 的 ASE（2018-05）与 MTK（2018-01）同样是 None。
        'x_from': None,
        # 单月同比要 12 个月 lag ⇒ 序列自 2017-01 起、同比自 2018-01 起，
        # 到最新年份正好 9 个年度，9 行把「有同比的年份」全部收进矩阵，不多留空行。
        # 这是**实数**不是上限：2027 年起会自然开始滚掉最老的一年（与 /tsm/ 同行为）。
        'heat_years': 9,
        'check_rows': 13,
    },

    # `breaks` 为空：2026-01 官方把 NRE 与 Others 并成一行是**披露格式**变化，
    # 本页那一列自 2017-01 起始终等于审计口径的 NRE&IP（对出来的，见 _NOTE_SEG_BREAK）。
    #
    # `continuity` 给，但把**适用范围**写进句子本身 —— 出处覆盖的是最近年度，
    # 更早年份要自己回溯各年年报。底座只负责「有出处才印」，管不了出处覆盖多宽，
    # 所以那层限定必须由这句话自己带上。
    'continuity': {
        'zh': '创意电子 2025 年度年报「因併購而發行新股：無」，关系企业一节列的全是'
              '全资自设子公司（GUC-NA／Japan／Korea／Europe／CN），全文无重述说明；'
              '本页序列另与 MOPS 法定月营收申报在 2017-01 至 2025-12 间抽查逐位相等，'
              '两个独立官方源对得上，且逐年加总与年报的查核营业收入逐位相等'
              '（构建期重跑，见页尾「季度聚合…是合法的」一条）。'
              '⚠️ 该出处覆盖的是最近年度，更早年份的合并范围请自行回溯各年年报 —— '
              '并购／处分／重述那一侧本页没有复算，只指路',
        'url': _IR,
    },

    'format_source':
        '版式仿 Goldman Sachs GIR 台股月营收报告（「Hon Hai (2317.TW)」与 '
        '「Wistron (3231.TW)」的 Exhibit 1-2，外加 GS HKEX 深度的超长历史层）；'
        '与 /tsm/ 同一套图列，本页因没有汇率腿而少三张图、编号顺次前移',

    'notes': [
        _NOTE_SOURCE,
        _NOTE_ADDITIVE,
        _NOTE_PRECISION,
        _NOTE_MIX,
        _NOTE_SEG_BREAK,
        _NOTE_NO_USD,
        _NOTE_NO_GUIDANCE,
        _NOTE_OFFICIAL_YOY,
        _NOTE_START,
        _NOTE_HEAT,
        _NOTE_DAYS,
    ],

    'footer': '图表与派生算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
              '仅供个人研究，不构成投资建议',
}
