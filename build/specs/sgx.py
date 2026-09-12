# -*- coding: utf-8 -*-
"""SGX（新加坡交易所）单公司页配置。

━━ 这份文件的全部职责 ━━
声明「series/sgx.csv 的哪些列上页面」。不算数、不画图、不碰公共代码。
整份文件可以直接删掉，别的页一行都不受影响。

━━ 本页的看点：SGX 卖的是「别人家的标的」━━
SGX 衍生品的头部产品全部是**离岸挂牌的他国标的**，与 JPX / HKEX 是同标的头对头：

    2026-06 实测（占当月 SGX 衍生品总成交 34,315,225 张的比重）
      FTSE 中国 A50 期货    11,724,378 张   34.2%   ← 与 HKEX 的 A 股衍生品同赛道
      外汇期货合计          10,268,040 张   29.9%   （USD/CNH + INR/USD 为主）
      铁矿石衍生品           5,354,979 张   15.6%
      日経225 期货              748,048 张    2.2%   ← 与 JPX 的旗舰合约同标的

所以 A50 与日経225 在本页必须**各自成段**（「股指期货」那组的 100% 占比堆叠里各占一段），
不许并进最上面那段残差「其他股指期货」里看不见 —— 它们是判断 SGX 竞争位置的直接读数。
（2026-09-12 之前这里写的是「两条线必须单列」：那时它们是一张多条折线里的两条线。
页面所有者把那张改成了占比堆叠，图上的读数从「张数」变成「占股指期货合计的份额」，
张数本身只留在汇总表与末尾核对表里 —— 见页尾那条本轮历史账。）

━━ 2026-09-12 改版：页面所有者的四条指令 ━━
① 删掉开篇四张（SDAV / DDAV 各一张「全历史与近 3 年分位带」、各一张「单月同比」）
   ⇒ `headline_style='none'`。两条头条列照旧定数据月、页顶数据条、汇总表头条两行与季节性，
   它们的水平值与单月同比只画在各自组里那张柱上。
② 四张多条折线（衍生品成交 / 股指期货 / 外汇期货 / 商品与利率）改成 `groups[].mix`：
   合计柱 + 100% 占比堆叠，凑不齐合计的那一块画成最上面一段并起名
   （名字集中在下面 `_RESID_*` 那几个常数）。利率期货不是商品合计的分项，拆成自己一组。
③ 月末未平仓紧跟衍生品成交那几张出（`stock_inline`），不再排到季节性之后。
④ 新增「按资产类别的占比」：衍生品当月成交合计的第二种切法（`mix.alt_splits`）。
   指标为什么是张数、而不是现货金额 / 名义额 / 收入，见 `_NOTE_ASSET` 上方那段。
页尾那条历史账（`_note_2609_12`）逐项向读者交代为什么，以及旧图号怎么对应。

━━ 为什么按「共同起点」分组 ━━
本页三档起点：2015-01（主体，含换手率）、2020-07（FTSE 台湾）、2025-11（加密）。
（换手率原本是第四档「2018-03 起」，那不是源的边界而是解析的边界：官方 2018-03 之前
把它印在月报 p8 的 `Turnover Velocity` 表里而不是 p2 的 At-A-Glance，抓取器只读 p2。
2026-08 给 fetch/sgx.py 加了 p8 兜底后回补 38 个月，这一列与主体同起点 ——
两处来源逐格等价、接缝不产生断点，证据见 fetch/sgx.py 口径坑 18。）
同组混起点会逼底座二选一：砍成最短窗口，或给平滑类图型喂 null
（gs_line 会 null.toFixed() 抛 TypeError，整张卡片之后的 exhibit 全不渲染，
见 docs/CHART_KINDS.md §1.2）。所以起点不同的列一律各成一组。

━━ 量价分解的口径核查（2026-08-07，结论：✅ 同口径，可分解）━━
恒等式 `成交额 ≡ 成交股数 × 加权平均成交价`，均价 = sec_turnover_sgdmn ÷ sec_turnover_mnshares。
这是定义式，没有假设、没有误差；**唯一要证的是分子分母同口径**。四条证据：

1. **同表同段相邻两行**。两列都出自月报 p2 的 SGX Statistics At A Glance，
   实测 2026-06 与 2015-01 两期的行序完全一样：
   `Turnover Volume (Million Shares)` 在第 7 行、`Turnover Value ($Million)` 在第 10 行
   （中间夹的是各自的上月/本月两个数）。两行都**没有脚注记号**，官方没有给它们不同的覆盖口径。
2. **改名逐代同步**。把 138 期 PDF 的这两行标签全扫一遍，共 9 个世代
   （大小写反复横跳 + 2025-12 起 `Securities Market` → `Stock Market`），
   **每一代都是两行一起改**，没有任何一期出现「一行改了另一行没改」——
   覆盖范围若变过，只会同时作用于分子与分母，比值不受污染。
3. **粒度一致，且金额那一行可反算验证**。两列都是**当月总量**（不是日均）。
   金额列满足 `sec_turnover_sgdmn / sec_trading_days = sdav_sgdmn`，
   全 138 个月最大相对误差 0.051%（= SDAV 取整到 S$mn 的舍入）。
   ⚠ 对照组：衍生品那一侧这个恒等式**不成立**（见下方 notes 里「衍生品的 DDAV 不能用
   当月总量 ÷ 交易日数反推」那一条 —— 按内容点名，不写第几条：页尾条目一增一删就错位），
   所以证券侧成立是有信息量的。
4. **12 个月滚动块可与官方 FYTD 对账**。用月度序列自己滚 FY2026（Jul-25–Jun-26）
   得 455,679 S$mn，官方报告 p3 的 FYTD = 455,677、新闻稿写 "S$455.7 billion" ——
   差 2（12 个整数月度值的舍入），相对差 0.0004%。衍生品 FYTD 更是逐位相同
   （363,489,920）。说明月度序列完整无缺、可安全聚合成年度块。

**均价序列有没有口径跳变？没有。** 逐月对数变动只有 2016-03 一个月 |z|>3（-44.7%），
而那一个月是**分母在动**（成交股数 22,750 → 46,539 百万股翻倍，金额只涨 13%），
是仙股放量、不是口径换代；把跳变前后各 6 个月的几何均价一比，前五大跳变全部回归、不留台阶。
唯一留下台阶的是 2024-05 之后（前 6 月均价 0.749 → 后 6 月 1.011），
但那不是某一个月的断点，而是 2024-2026 大盘股行情驱动的**连续 12 个月的爬升**
（12 个月滚动中位数 0.75 → 0.94 → 1.08 逐级抬升，不是一次跃迁），
且与 2025-12 的官方改名相差 19 个月，时间对不上。

⚠ **「价」是什么、不是什么**：这里的均价 = 成交额 ÷ 成交股数 = **成交量加权平均成交价**，
它同时含（a）市场涨跌与（b）成交结构变化（仙股 vs 大盘股的成交占比此消彼长）。
本仓没有 STI 点位序列，**分不开 a 与 b**，所以任何图注都不许把它说成指数收益率。
（对照：TMX 的 series 里有 `tsx_composite_close`，那一家才拆得开。）

━━ 有意不上页面的列，以及理由 ━━
· sec_trading_days —— 分母。而且它是**证券市场**的交易日数，
  拿去除衍生品月量得不到 DDAV（实测 2026-06 反推 21.19 天、官方写 21），
  上页面只会诱导别人做错误的除法。
· deriv_swaps_vol_contracts —— 掉期这一列**本身**不声明。「衍生品成交与未平仓」那张
  「按期货 / 期权 / 掉期」的占比堆叠里有一段叫「掉期」，但那一段是**减出来的**
  （合计 − 期货 − 期权），装着掉期 + 三桶相加的印刷差，不是这一列
  （差在哪几个月由 `_swaps_gap()` 现算、印在那张图的 share_note 里）。
  也不能把这一列当第三个分项：有月份「期货 + 期权 + 掉期」比合计**多**，
  底座会按「分项之和超过合计」硬失败；减出来的那一段逐月非负。
· vol_msci_taiwan_futures_contracts —— **已停发的死列**：2021-11 之后无值，
  2021-01 还有一个内部空洞，2021-02 起全是 0。既不能进平滑图型，
  留在页面上也只是一条归零线。台湾敞口改看 FTSE 那条（2020-07 起）。
"""

import csv
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CSV = os.path.join(_ROOT, 'series', 'sgx.csv')


# ── 占比堆叠里「残差段」的名字（2026-09-12 起）────────────────────────────────
# 本页每张 100% 占比堆叠最上面那段都是**减出来的**（合计 − 各分项）。底座只知道它是
# 减出来的，不知道里面装着哪些合约 —— 名字由本页起，也由本页负责说对。
# 集中在这里而不是散写进 SPEC：「每一段残差里到底是官方哪几行」要拿官方 PDF 逐节核，
# 核出来的结论可能要回调这几个名字；改这一处，SPEC、share_note、释义里引用它的地方
# 全部跟着走，不会出现图例叫一个名字、图注叫另一个名字。
_RESID_SWAPS_ZH = '掉期'
# 「按资产类别」那一刀的残差段**点名加密**（2026-09-12 审稿后改）。
# 上一版名字里没有加密，理由是「加密永续算不算在 deriv_vol_contracts 里，本仓没有逐位对过账」。
# 这件事已经对过：拿 2026-08 期官方月报（cache/sgx_2026-08.pdf）逐节核，
#   · SGX 自己的 21 个成交量小节相加恰好等于 Derivatives Overall Market Volume 27,099,103
#     （p39 那节 "GIFT Nifty Overall Market Volume (Source: NSE-IX)" 不在其中）；
#   · 合计 − 股指期货 13,162,434 − 外汇期货 8,144,918 − 商品 5,439,594 = 352,157，
#     逐位等于 利率期货 127,195 ＋ 股指期权 115,054 ＋ 个股期货（Equity Futures）57,720
#     ＋ 加密 36,413 ＋ 外汇期权 11,756 ＋ 股息指数期货 4,019 ＋ 利率期权 0。
# ⇒ 加密**在**合计里，个股期货也在。那一期的逐项数写在 `_DERIV_OTHER_2608`，由 import 期守卫钉在 CSV 上。
# 名字里的顺序按**全窗口**的量级排，不按 2026-08 一期（审稿后改；上一版把利率期货排第一）：
# 逐期核 2016-01 / 2024-07 两期（`_DERIV_OTHER_ERAS`），最大的一块都是股指期权，个股期货次之；
# 利率期货占这一段过三成的只有 2026-06 起那几个月。其余用「等」收住
# （股息指数期货这一类以后可能变大，「等」字让名字在那种月份也不是假话）。
_RESID_DERIV_ASSET_ZH = '其他（股指 / 外汇期权、个股期货、利率期货、加密等）'
# 上一版叫「其他股指期货（含 GIFT Nifty、FTSE 台湾）」—— 图窗 Jan-16 起，而 FTSE 台湾 2020-07
# 才上线：前 54 个月这个名字点着一个还不存在的合约，却漏了那几年与 GIFT Nifty 一样大的
# MSCI 台湾期货（2026-09-12 审稿，逐期核见 `_eqix_share` 的 docstring）。
# 「台湾指数期货」两个时代都成立（MSCI 台湾 → FTSE 台湾），具体换在哪个月由图注现算点名。
_RESID_EQIX_ZH = '其他股指期货（含 GIFT Nifty、台湾指数期货）'
# 上一版叫「其他外汇期货（Mini / FlexC 合约与其他货币对）」，把变体排在前面、读起来像这一段
# 主要是两条单列的 Mini / FlexC。2026-08 期官方月报逐行核下来正相反：915,026 张里
# USD/CNH (Mini) 只有 3,533、USD_CNH FlexC 90，最大的一块是**别的货币对** KRW/USD (Mini)
# 748,352（逐项见 `_FX_OTHER_2608`）⇒ 货币对在前，变体在后。
_RESID_FX_ZH = '其他外汇期货（其他货币对与合约变体）'
# 上一版叫「铁矿石以外的商品」—— 那是假话：「其中：铁矿石」这一列在 2026-08 期漏收了
# 一行铁矿石（Lump Premium 指数期货，见 `_IRON_2608` 那段），漏掉的量正落在这一段里。
# 解析器修好之前这一段不能叫「铁矿石以外」，只能叫「其他」。
_RESID_COMM_ZH = '其他商品'


# ── 断点能读 CSV 就读 ──────────────────────────────────────────────────
# 内联而不抽公共函数：本页要能整份删掉不留残渣。这个函数只做
# 「列 → 第一个有值的月份」的字典查询，不含统计口径。
# 读不到就返回 None —— 缺文件不许在 import 期抛异常。
def _first_present(col):
    try:
        with open(_CSV, encoding='utf-8') as fh:
            for r in csv.DictReader(fh):
                if col in r and r[col].strip():
                    return r['month']
    except OSError:
        pass
    return None


# GIFT Nifty 的计数口径断点月。这一条**只能写死** —— CSV 里没有任何标记列能
# 指出它，依据是官方报告脚注「For periods prior to June 2023, volumes are
# computed based on higher of buy and sell lots」（见 docs/verify/sgx.md 口径坑 3）。
# 抽成常数：_breaks() 与页尾口径说明里的污染期算术都从它推，不各写一份。
_NIFTY_BREAK = '2023-07'


def _madd(m, k):
    """'YYYY-MM' + k 个月。断点月的衍生日期（+11 / +23）用它算，不手写第二份日期。"""
    y, mo = int(m[:4]), int(m[5:7]) + k
    return f'{y + (mo - 1) // 12:04d}-{(mo - 1) % 12 + 1:02d}'


def _yoy_gap(col):
    """一列的单月同比 vs 12 个月滚动合计同比，全期逐月对比（全部从 CSV 现算）。

    页尾口径说明引用的分歧数字都出自这里，一个数字不写死。本页的月总量列都是
    当月合计口径，滚动合计 = 12 个月直加，无需交易日权重。「符号相反」与
    tools/check_yoy_caliber.py 同一条死区：两侧 |同比| ≥ 0.5pp 才计
    （贴零的正负是舍入不是方向分歧）。
    返回 (可比月数, 符号相反月数, 分歧最大的月份, 该月单月%, 该月滚动%,
          最新有滚动同比的月份, 该月滚动%, 不设死区时的符号相反月数)；算不出返回 (None,) * 8。
    最后一格（2026-09-12 审稿补）：各图图注里底座印的「符号相反的月份」是**不设死区**的计法
    （贴零的正负也算），同一个样本两种计法差几个月。页尾只印带死区的那个数，读者会看到
    同一件事两个数（例如 21 vs 24）而无从对上 —— 所以两个数一起印、各自说明计法。
    """
    try:
        with open(_CSV, encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return (None,) * 8
    months = [r['month'] for r in rows]           # series/*.csv 按月升序、逐月连续
    vals = []
    for r in rows:
        v = (r.get(col) or '').strip()
        try:
            vals.append(float(v) if v else None)
        except ValueError:
            vals.append(None)
    mom, ttm = {}, {}
    for i, m in enumerate(months):
        a = vals[i]
        if i >= 12 and a is not None and vals[i - 12] not in (None, 0.0) \
                and a * vals[i - 12] > 0:
            mom[m] = (a / vals[i - 12] - 1) * 100.0
        if i >= 23 and all(v is not None for v in vals[i - 23:i + 1]):
            s1, s0 = sum(vals[i - 11:i + 1]), sum(vals[i - 23:i - 11])
            if s0 != 0 and s1 * s0 > 0:
                ttm[m] = (s1 / s0 - 1) * 100.0
    both = sorted(m for m in mom if m in ttm)
    if not both:
        return (None,) * 8
    flips = [m for m in both
             if mom[m] * ttm[m] < 0 and abs(mom[m]) >= 0.5 and abs(ttm[m]) >= 0.5]
    flips_all = [m for m in both if mom[m] * ttm[m] < 0]
    worst = max(both, key=lambda m: abs(mom[m] - ttm[m]))
    last = max(ttm)
    return (len(both), len(flips), worst, mom[worst], ttm[worst], last, ttm[last], len(flips_all))


# 页尾口径说明用的两组实测（FTSE 台湾、新债券挂牌）。GIFT Nifty 不算这组数 ——
# 它的全期 mom/ttm 对比会跨 2023-07 计数断点，两种口径都被污染，
# 算出来的「分歧」混着断点效应，不能当口径论据（那张的理由是污染期算术，见 notes）。
_GT = _yoy_gap('vol_ftse_taiwan_futures_contracts')
_GB = _yoy_gap('new_bond_listings')


# ══ 名词释义与占比图注要用的几组结构性实测（全部从 series/sgx.csv 现算）══════════
# 与上面那两组同一条规矩：释义与图注里出现的数一个都不写死。这几个函数只做算术，
# 不含任何当月判断 —— 释义是「这些词是什么意思」，一年到头是同一段。
def _rows():
    """series/sgx.csv 的全部行；读不到返回空表（import 期不许因缺文件抛异常）。"""
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _num(r, c):
    v = (r.get(c) or '').strip()
    try:
        return float(v) if v else None
    except ValueError:
        return None


def _med(s):
    """中位数；空表返回 None。本文件所有「中位」一律走这一个函数。

    偶数个时取**中间两个的均值**（2026-09-12 审稿后改）。上一版取排序后的第 len//2 个
    （上中位数），140 个月的样本上就是第 71 个 —— 分布是双峰时差得很远：
    「GIFT Nifty ＋ FTSE 台湾占股指残差段」恰好 70 个月 < 80%、70 个月 ≥ 85%，
    上中位数印成 89%，真中位是 83%；另有几处差一个舍入档（95% vs 97%、11.5% vs 11.6%）。
    """
    s = sorted(s)
    if not s:
        return None
    k = len(s) // 2
    return s[k] if len(s) % 2 else (s[k - 1] + s[k]) / 2.0


def _sdav_identity():
    """证券侧恒等式 `当月成交额 ÷ 当月证券交易日数 = SDAV` 的实测偏差。

    返回 (可算月数, 最大相对差%)；算不出返回 (None, None)。
    这条是 fetch/sgx.py 的解析自检（_crosscheck）用的同一条恒等式。
    """
    e = []
    for r in _rows():
        t, d, s = (_num(r, 'sec_turnover_sgdmn'), _num(r, 'sec_trading_days'),
                   _num(r, 'sdav_sgdmn'))
        if t and d and s:
            e.append(abs(t / d / s - 1) * 100.0)
    return (len(e), max(e)) if e else (None, None)


def _ddav_days():
    """衍生品侧那条恒等式**不成立**的实测（fetch/sgx.py 口径坑 6）。

    用官方两个数反算隐含交易日数 `当月成交合计 ÷ DDAV`，再与当月**证券市场**
    交易日数比。返回 (可算月数, 与证券交易日不等的月数, 隐含天数下界, 上界,
    误用证券交易日的相对差中位%, 最大%)；算不出返回 (None,) * 6。
    """
    imp, ne, rel = [], 0, []
    for r in _rows():
        v, dd, d = (_num(r, 'deriv_vol_contracts'), _num(r, 'ddav_contracts'),
                    _num(r, 'sec_trading_days'))
        if v and dd and d:
            x = v / dd
            imp.append(x)
            if abs(x - d) > 0.005:            # 官方交易日是整数，半天以内算相等
                ne += 1
            rel.append(abs(v / d / dd - 1) * 100.0)
    if not imp:
        return (None,) * 6
    return (len(imp), ne, min(imp), max(imp), _med(rel), max(rel))


def _swaps_gap():
    """「当月成交合计 = 期货 + 期权 + 掉期」这条恒等式，与占比堆叠里「掉期」那一段装着什么。

    掉期那一列不上页面（见文件抬头），「按期货 / 期权 / 掉期」那张占比堆叠里的
    「掉期」段是**减出来的**：合计 − 期货 − 期权 ＝ 掉期 ＋ 三桶相加的印刷差
    （「期权」是本仓的桶，2022 年之前含总表第四行场外清算期权，见 `_OPT4_*`）。
    释义与那张图的 share_note 都要把这件事点破，不然读者会拿掉期列去对那一段。
    返回 (可算月数, 三项逐位相加等于合计的月数, 最大残差张数,
          「掉期」段占合计中位%, 最大%, [(月份, 「掉期」段 − 掉期列 的张数), …],
          样本首月)；算不出返回 (None,) * 7。
    样本首月给图注写「YYYY-MM 起全期中位」用：底座在同一段图注里印的是「窗口内」区间，
    两种样本不写明就会被读成同一个。
    """
    sh, exact, res, off, m0 = [], 0, [], [], None
    for r in _rows():
        tot, fu, op, sw = (_num(r, 'deriv_vol_contracts'),
                           _num(r, 'deriv_futures_vol_contracts'),
                           _num(r, 'deriv_options_vol_contracts'),
                           _num(r, 'deriv_swaps_vol_contracts'))
        if tot and None not in (fu, op, sw):
            m0 = m0 or r['month']
            seg = tot - fu - op
            sh.append(seg / tot * 100.0)
            d = seg - sw
            res.append(abs(d))
            if abs(d) < 0.5:
                exact += 1
            else:
                off.append((r['month'], d))
    if not sh:
        return (None,) * 7
    return (len(sh), exact, max(res), _med(sh), max(sh), off, m0)


def _asset_share():
    """「按资产类别」那一切（2026-09-12 指令四）：三类各占衍生品当月成交合计多少。

    返回 (可算月数, 股指期货中位%, 外汇期货中位%, 商品中位%, 其他中位%,
          利率期货占「其他」段的中位%, 样本首月, 利率期货占「其他」段 ≥30% 的月份表)；
    算不出返回 (None,) * 8。
    四个中位各自独立取，相加不必等于 100 —— 图注里照实这么说。
    「其他」段里只拿利率期货算全期中位，不拿加密：加密**在**合计里（2026-08 期官方月报
    逐节核过，见 `_RESID_DERIV_ASSET_ZH` 上方那段），但它 2025-11 才有，放进一个 2015-01 起的
    全期中位里只会是一串 0；股指 / 外汇期权、个股期货、股息指数期货本仓没有列。
    那几块只在 `_DERIV_OTHER_2608` / `_DERIV_OTHER_ERAS` 里按单期官方数给出。
    ≥30% 的月份表用来说明「利率期货是这一段最大一块」只是近几个月的事（残差段名字的排序依据）。
    """
    e, f, c, o, ra, hi, m0 = [], [], [], [], [], [], None
    for r in _rows():
        tot = _num(r, 'deriv_vol_contracts')
        p = [_num(r, x) for x in ('vol_equity_index_futures_contracts',
                                  'vol_fx_futures_contracts',
                                  'vol_commodities_contracts')]
        if not tot or any(x is None for x in p):
            continue
        m0 = m0 or r['month']
        rest = tot - sum(p)
        e.append(p[0] / tot * 100.0)
        f.append(p[1] / tot * 100.0)
        c.append(p[2] / tot * 100.0)
        o.append(rest / tot * 100.0)
        rt = _num(r, 'vol_rates_futures_contracts')
        if rest > 0 and rt is not None:
            ra.append(rt / rest * 100.0)
            if rt / rest >= 0.30:
                hi.append(r['month'])
    if not e:
        return (None,) * 8
    return (len(e), _med(e), _med(f), _med(c), _med(o), _med(ra), m0, hi)


def _eqix_share():
    """本页点名的指数产品占「股指期货合计」多少，以及残差段里装着什么（全部从 CSV 现算）。

    「股指期货」那张 100% 占比堆叠只把 A50 / 日経225 / MSCI 新加坡各画一段，其余并进
    残差段 —— 释义与 share_note 要说清那一段里装着什么，这里给数。
    ⚠️ 残差段里最大的两块是 GIFT Nifty 与**台湾指数期货**，而台湾那一块换过合约：
    FTSE 台湾 `_TW0`（实测 2020-07）才有，在那之前是 MSCI 台湾期货
    （`vol_msci_taiwan_futures_contracts`，页面上不画的死列）。上一版只拿 FTSE 台湾算、
    上线之前「按 0 计」，于是把 2020-07 之前将近一半的残差段说成了「本页没有列的指数合约」
    （2026-09-12 审稿逐期核：cache/sgx_2016-01.pdf 里 MSCI Taiwan Index Futures 1,725,417 张，
    与 SGX Nifty 50 的 1,757,524 张几乎一样大）。所以台湾那一块按 MSCI ＋ FTSE 两列相加算。
    返回 (三条的中位占比%, 三条 ＋ GIFT Nifty ＋ 台湾指数期货的中位占比%,
          GIFT Nifty ＋ 台湾指数期货占残差段的中位%, 同一比值的最低%, 可算月数, 样本首月,
          FTSE 台湾上线之前 MSCI 台湾占残差段的中位%, 那一段的月数,
          那一段里 MSCI 台湾比 GIFT Nifty 还大的月数)；算不出返回 (None,) * 9。
    缺值按 0 计（那几条各有自己的起止，缺的月份本就没有量）。
    """
    a, b, q, pre, big, m0 = [], [], [], [], 0, None
    for r in _rows():
        tot = _num(r, 'vol_equity_index_futures_contracts')
        if not tot:
            continue
        p3 = [_num(r, c) for c in ('vol_a50_futures_contracts',
                                   'vol_nikkei225_futures_contracts',
                                   'vol_msci_singapore_futures_contracts')]
        if any(x is None for x in p3):
            continue
        m0 = m0 or r['month']
        nif, mtw, ftw = (_num(r, c) or 0.0 for c in ('vol_nifty50_futures_contracts',
                                                     'vol_msci_taiwan_futures_contracts',
                                                     'vol_ftse_taiwan_futures_contracts'))
        a.append(sum(p3) / tot * 100.0)
        b.append((sum(p3) + nif + mtw + ftw) / tot * 100.0)
        rest = tot - sum(p3)
        if rest > 0:
            q.append((nif + mtw + ftw) / rest * 100.0)
            if _TW0 and r['month'] < _TW0:
                pre.append(mtw / rest * 100.0)
                big += int(mtw > nif)
    if not a:
        return (None,) * 9
    return (_med(a), _med(b), _med(q), min(q) if q else None, len(a), m0,
            _med(pre), len(pre), big)


def _velocity_stats():
    """换手率：印刷精度，以及「拿本页两列反推」为什么不成立。

    返回 (月数, 整数月数, 读数下界, 上界, 与「当月成交额 ÷ 月末总市值」之比的
          下界 / 中位 / 上界)；算不出返回 (None,) * 7。
    倍数不是常数正是论据本身：官方脚注说明分子分母都只取 primary listed
    securities，而本页那两列是全市场口径。
    """
    v, mult = [], []
    for r in _rows():
        x = _num(r, 'turnover_velocity_pct')
        t, m = _num(r, 'sec_turnover_sgdmn'), _num(r, 'mktcap_sgdmn')
        if x:
            v.append(x)
            if t and m:
                mult.append(x / (t / m * 100.0))
    if not v or not mult:
        return (None,) * 7
    return (len(v), sum(1 for x in v if x == int(x)), min(v), max(v),
            min(mult), _med(mult), max(mult))


def _rto_only_months():
    """家数 = 0 而募资额 > 0 的月数 —— 「募资额含 RTO、家数不含」的直接证据。"""
    n = 0
    for r in _rows():
        c, f = _num(r, 'ipos_count'), _num(r, 'ipo_funds_sgdmn')
        if c == 0 and f and f > 0:
            n += 1
    return n


def _fx_share():
    """本页单列的两条外汇产品占「外汇期货合计」多少 —— 同 `_eqix_share()` 的用途。

    「外汇期货」那张 100% 占比堆叠只把 USD/CNH 与 INR/USD 各画一段，其余并进残差段。
    那一段里装两类：**别的货币对**（2026-08 期最大的是 KRW/USD (Mini)），与两条单列
    **同一货币对的其他合约**（USD/CNH 的 Mini / FlexC；INR/USD 的 FlexC 与行名带 (USD) 的
    USD/INR 期货 —— 列边界见 fetch/sgx.py 的列口径表）。后一类 2026-08 期不到 1%，
    2021-05 期却占三成多（逐项见 `_FX_OTHER_2608` / `_FX_2105`），不许写成「量很小」的常态。
    那一段有多厚由这里现算。
    （2026-09-12 之前这里的理由是「合计与两条分项画在同一根轴上，读者会去相加对账」，
    那张三条折线已经改成占比堆叠。）
    返回 (可算月数, 占比下界%, 中位%, 上界%, 样本首月)；算不出返回 (None,) * 5。
    """
    s, m0 = [], None
    for r in _rows():
        tot = _num(r, 'vol_fx_futures_contracts')
        a, b = (_num(r, 'vol_usdcnh_futures_contracts'),
                _num(r, 'vol_inrusd_futures_contracts'))
        if tot and a is not None and b is not None:
            m0 = m0 or r['month']
            s.append((a + b) / tot * 100.0)
    if not s:
        return (None,) * 5
    return (len(s), min(s), _med(s), max(s), m0)


def _iron_share():
    """「其中：铁矿石」这一列占「商品合计」的中位比重与样本首月；算不出返回 (None, None)。

    是**这一列**的占比，不是官方全部铁矿石合约的占比 —— 这一列 `_IRON_WRAP0`（2025-09）起
    每期漏收一行（见 `_IRON_LUMP_MISSED`，之前缓存的各期逐位相等）。2015-01 起的全期中位里只有
    最后十几个月受影响，而且每期只低 1% 以内，所以印出来的整数中位不受影响；但这不是「官方口径」的中位。
    """
    hit = [(r['month'], _num(r, 'vol_iron_ore_contracts') / _num(r, 'vol_commodities_contracts')
            * 100.0)
           for r in _rows()
           if _num(r, 'vol_commodities_contracts') and _num(r, 'vol_iron_ore_contracts')]
    return (_med([v for _m, v in hit]), hit[0][0]) if hit else (None, None)


def _price_range():
    """加权平均成交价（当月成交额 ÷ 当月成交股数）的全期区间；算不出返回 (None, None)。"""
    p = [_num(r, 'sec_turnover_sgdmn') / _num(r, 'sec_turnover_mnshares')
         for r in _rows()
         if _num(r, 'sec_turnover_mnshares') and _num(r, 'sec_turnover_sgdmn')]
    return (min(p), max(p)) if p else (None, None)


# 加密永续那一节的首月（实测 2025-11）。同 _breaks() 的做法：能读 CSV 就读，不写死。
_CRYPTO0 = _first_present('vol_crypto_contracts')
# FTSE 台湾那条的首月（实测 2020-07），_breaks() 与股指期货占比图的图注共用。
# 排在 `_eqix_share()` 之前：那里要拿它切「MSCI 台湾时代 / FTSE 台湾时代」。
_TW0 = _first_present('vol_ftse_taiwan_futures_contracts')
_SD = _sdav_identity()
_DD = _ddav_days()
_SW = _swaps_gap()
_AS = _asset_share()
_EQ = _eqix_share()
_FX = _fx_share()
_VE = _velocity_stats()
_RTO = _rto_only_months()
_IO = _iron_share()
_PR = _price_range()


# ══ 2026-08 期官方月报逐节核对（单期官方数，不随月份走）══════════════════════════
# 四张占比图的残差段「里面装着什么」，CSV 回答不了（残差本来就是 CSV 没有列的那些合约），
# 只能拿官方 PDF 逐行抄。下面四组是 2026-08 期官方月报（cache/sgx_2026-08.pdf，
# pdftotext 抽出后逐节加总）的原值，与文件里另外几个官方字面常数同一种身份：
# 印在报告里的数，不随本仓的月份走。图注里一律带着「2026-08 期」的戳，不写成常态。
#
# ⚠️ 每组配一道 import 期守卫：series/sgx.csv 的 2026-08 那一行按同一条算式现算，
#    必须逐位等于这里官方分项之和（各组的「分项和 = 残差」也顺带挡住抄写错位）。
#    对不上 = 那一行被回补 / 重述过、或解析器口径改了 ⇒ 图注引用的官方拆分已经不是
#    这份 CSV 的拆分。抛异常不发页，不让一组旧数去解释一段新残差。
#    CSV 读不到、没有 2026-08 那一行、或其中某列缺值时不响（同 `_rows()`：缺文件不许在
#    import 期抛异常）。
# ⚠️ 异常类继承 ValueError 而**不是** SystemExit（本文件 `_HistMismatch` 的做法）：
#    build/test_guards.py 的 `test_all_live_specs_still_construct` 在循环里逐页 load_spec、
#    不接 SystemExit —— import 期漏出一个 SystemExit 会把整个 preflight 进程带走，一条结果都不留。
_STAMP_M = '2026-08'
_STAMP_SRC = 'cache/sgx_2026-08.pdf'


class _StampMismatch(ValueError):
    """2026-08 期官方逐节核对的引用数与 series/sgx.csv 对不上。"""


def _stamp_row(m=_STAMP_M):
    """series/sgx.csv 里 `m`（缺省 2026-08）那一行；没有返回 None。"""
    return next((r for r in _rows() if r.get('month') == m), None)


def _stamp_resid(total, parts, m=_STAMP_M):
    """`m` 那一行的 total − Σparts；那一行不在或任一列缺值返回 None。缺列按缺值算。"""
    r = _stamp_row(m)
    if r is None:
        return None
    v = [_num(r, c) for c in (total,) + tuple(parts)]
    if any(x is None for x in v):
        return None
    return v[0] - sum(v[1:])


def _stamp_guard(what, items, total, got, formula, m=_STAMP_M):
    """官方分项 `items` 必须加总到 `total`，CSV 现算的 `got` 必须等于 `total`（got 为 None 不查）。

    `m` 是引用的是哪一期（缺省 2026-08）：几处图注还引了更早的单期官方拆分来交代
    「这一段在别的年代装着什么」，出处 PDF 一律是 `cache/sgx_<m>.pdf`，守卫照同一条算式对 CSV。
    """
    src = f'cache/sgx_{m}.pdf'
    s = sum(n for _zh, n in items)
    if s != total:
        raise _StampMismatch(
            f'[sgx] {what}：build/specs/sgx.py 里抄的 {m} 期官方分项加总是 {s:,}，'
            f'与同处写的合计 {total:,} 不等 —— 抄写错位，拿 {src} 重抄')
    if got is not None and abs(got - total) > 0.5:
        raise _StampMismatch(
            f'[sgx] {what}：图注引用的是 {m} 期官方月报（{src}）逐节核出来的拆分，'
            f'分项合计 {total:,} 张；而 series/sgx.csv 的 {m} 行按「{formula}」现算是 '
            f'{got:,.0f} 张 —— 引用的官方拆分与 CSV 已经对不上（那一行被回补 / 重述过，'
            '或解析器口径改了），图注会拿旧拆分去解释新残差。拿官方 PDF 重新逐节核，'
            '更新 build/specs/sgx.py 里这组常数与引用它的图注；不许只把守卫的目标数改成新值')


# ── 「按资产类别」那一刀的残差段「其他」（合计 − 股指期货 − 外汇期货 − 商品）─────────
# 同一期还核过两件事（写在 `_RESID_DERIV_ASSET_ZH` 上方）：SGX 自己的 21 个成交量小节
# 相加恰好 = Derivatives Overall Market Volume 27,099,103；p39 那节 NSE-IX 口径的
# "GIFT Nifty Overall Market Volume" 不在其中。所以下面这 7 项就是这一段的全部。
# 第三格是 CSV 里对应的列（有才填）：那两项顺带逐位对 CSV。
_DERIV_OTHER_2608_TOTAL = 352157
_DERIV_OTHER_2608 = (
    ('利率期货', 127195, 'vol_rates_futures_contracts'),
    ('股指期权', 115054, None),
    ('个股期货（官方 Equity Futures 一节）', 57720, None),
    ('加密永续', 36413, 'vol_crypto_contracts'),
    ('外汇期权', 11756, None),
    ('股息指数期货', 4019, None),
    ('利率期权', 0, None),
)
_stamp_guard('「按资产类别」占比图里「其他」段的逐项构成',
             [(z, n) for z, n, _c in _DERIV_OTHER_2608], _DERIV_OTHER_2608_TOTAL,
             _stamp_resid('deriv_vol_contracts', ('vol_equity_index_futures_contracts',
                                                  'vol_fx_futures_contracts',
                                                  'vol_commodities_contracts')),
             '当月成交合计 − 股指期货合计 − 外汇期货合计 − 商品合计')
for _z, _n, _c in _DERIV_OTHER_2608:
    if _c and _stamp_row() is not None and _num(_stamp_row(), _c) is not None \
            and _num(_stamp_row(), _c) != _n:
        raise _StampMismatch(
            f'[sgx] 「其他」段逐项构成里的「{_z}」抄的是 {_STAMP_M} 期官方数 {_n:,}，'
            f'series/sgx.csv 的 {_c} 在 {_STAMP_M} 却是 {_num(_stamp_row(), _c):,.0f} —— '
            '引用的官方拆分与 CSV 已经对不上，拿官方 PDF 重新逐节核')

# 这一段装着什么**随年代换过**（2026-09-12 审稿逐期核）：2026-08 期利率期货最大，但那只是
# 近三个月的事（利率期货占这一段 ≥30% 的月份只有 2026-06 起那几个，`_asset_share` 现算）——
# 更早每一期里最大的一块都是股指期权，2019 年起个股期货也上来了。所以残差段的名字按全窗口的
# 量级排序，图注另引两期官方拆分：窗口起点 2016-01 与 2024-07。同一条算式、同一种守卫。
# （2016-01 那一代官方还没有个股期货与外汇期权两节；两期逐项加总都恰好等于 CSV 现算的残差。）
_DERIV_OTHER_ERAS = (
    ('2016-01', 610882, (('股指期权', 563006), ('利率期货', 28207), ('股息指数期货', 19669),
                         ('利率期权', 0))),
    ('2024-07', 444277, (('股指期权', 209077), ('个股期货', 191307), ('利率期货', 38680),
                         ('股息指数期货', 3497), ('外汇期权', 1716), ('利率期权', 0))),
)
for _m, _t, _items in _DERIV_OTHER_ERAS:
    _stamp_guard(f'「按资产类别」占比图里「其他」段在 {_m} 期的逐项构成', _items, _t,
                 _stamp_resid('deriv_vol_contracts', ('vol_equity_index_futures_contracts',
                                                      'vol_fx_futures_contracts',
                                                      'vol_commodities_contracts'), m=_m),
                 '当月成交合计 − 股指期货合计 − 外汇期货合计 − 商品合计', m=_m)

# ── 「期权」那一桶在 2022 年之前还收着一行场外清算期权（2026-09-12 审稿逐期核）─────────
# 官方总表 Derivatives Overall Market Volume 在 2022 年之前是四行不是三行：Total Futures /
# Total Options / 掉期 / 另一行场外清算期权 —— 2018-08 及之前叫 "Total AsiaClear Cleared Options
# Volume"，之后叫 "Total Options On Swaps Volume"（三代行名见 fetch/sgx.py 的 `_read_deriv_split`，
# 它按行名语义把这一行并进期权桶）。本仓缓存的各期里：2015-01–2018-04 多数月份非零（图窗内
# 最大是 2016-01 的 20,760 张），2018-09 至 2021-05 缓存的各期都是 0，2022-11 期起总表不再印这一行。
# ⇒ 「其中：期权」在那几年 ≠ 官方 Total Options 那一行；官方三行 Total 相加也凑不齐合计，
#   差的是这一行，不是印刷差。释义「当月成交合计」与 `_NOTE_SPLIT_DERIV` 照实交代。
_OPT4_M = '2016-01'
_OPT4_TOTAL_OPTIONS = 723665       # 官方 Total Options Trading Volume
_OPT4_ROW = 20760                  # 官方 Total AsiaClear Cleared Options Volume
if _stamp_row(_OPT4_M) is not None \
        and _num(_stamp_row(_OPT4_M), 'deriv_options_vol_contracts') not in (
            None, _OPT4_TOTAL_OPTIONS + _OPT4_ROW):
    raise _StampMismatch(
        f'[sgx] 释义「当月成交合计」引的是 {_OPT4_M} 期官方 Total Options {_OPT4_TOTAL_OPTIONS:,} ＋ '
        f'场外清算期权 {_OPT4_ROW:,}（cache/sgx_{_OPT4_M}.pdf），series/sgx.csv 的 '
        f'deriv_options_vol_contracts 在 {_OPT4_M} 却是 '
        f'{_num(_stamp_row(_OPT4_M), "deriv_options_vol_contracts"):,.0f} —— 期权桶的口径变了，重核')

# ── 「股指期货」占比图的残差段里，本页没有列的那几行 ────────────────────────────
# 残差段 = 合计 − A50 − 日経225 − MSCI 新加坡；其中 GIFT Nifty 50 与 FTSE 台湾本页有列，
# 再扣掉它俩剩下的是官方 Equity Index Futures 小节里其余**非零**的 9 行（该期其余行全是 0）。
_EQIX_OTHER_2608_TOTAL = 257161
_EQIX_OTHER_2608 = (
    ('FTSE Micro Taiwan', 92124),
    ('FTSE China H50', 48959),
    ('Straits Times Index', 33931),
    ('FTSE Indonesia', 29370),
    ('FTSE Vietnam 30', 26346),
    ('Micro Nikkei 225', 22970),
    ('GIFT Nifty Bank', 3266),
    ('FTSE Japan Blossom', 194),
    ('USD Nikkei 225', 1),
)
_stamp_guard('「股指期货」占比图残差段里本页没有列的那几行',
             _EQIX_OTHER_2608, _EQIX_OTHER_2608_TOTAL,
             _stamp_resid('vol_equity_index_futures_contracts',
                          ('vol_a50_futures_contracts', 'vol_nikkei225_futures_contracts',
                           'vol_msci_singapore_futures_contracts',
                           'vol_nifty50_futures_contracts', 'vol_ftse_taiwan_futures_contracts')),
             '股指期货合计 − A50 − 日経225 − MSCI 新加坡 − GIFT Nifty 50 − FTSE 台湾')

# ── 「外汇期货」占比图的残差段（合计 − USD/CNH − INR/USD）──────────────────────────
# 官方 Foreign Exchange Futures 小节该期其余**非零**的 13 行。行名照官方原文（只把 "_" 换成 "/"），
# 不译：Full Sized / Mini / Micro / FlexC 是合约规格的名字，译了反而对不回报告。
_FX_OTHER_2608_TOTAL = 915026
_FX_OTHER_2608 = (
    ('KRW/USD (Mini)', 748352),
    ('BRL/USD', 93121),
    ('TWD/USD (Full Sized)', 44078),
    ('TWD/USD (Micro)', 16893),
    ('KRW/USD (Full Sized)', 4972),
    ('USD/CNH (Mini)', 3533),
    ('USD/SGD', 1235),
    ('HKD/USD', 966),
    ('THB/USD', 911),
    ('USD/JPY (Standard)', 445),
    ('USD/SGD (Full-Sized)', 310),
    ('HKD/CNH', 120),
    ('USD/CNH FlexC', 90),
)
_stamp_guard('「外汇期货」占比图残差段的逐行构成',
             _FX_OTHER_2608, _FX_OTHER_2608_TOTAL,
             _stamp_resid('vol_fx_futures_contracts',
                          ('vol_usdcnh_futures_contracts', 'vol_inrusd_futures_contracts')),
             '外汇期货合计 − USD/CNH − INR/USD')

# 同一段在更早的年代还装着**同一货币对的其他合约**，不只是别的货币对（2026-09-12 审稿逐期核）：
# 「INR/USD 期货」这一列只认官方 `INR_USD FX Futures` 那一行（fetch/sgx.py 的 P_INRUSD 全等匹配），
# 行名带 (USD) 的 USD/INR 期货官方另行分列（2021-05 期叫 "USD/INR (USD) Futures"、
# 2022-11 期叫 "USD/INR (USD) Month-end Futures"），计在这一段里 —— 2021-05 期它一行就占三成多。
# 上一版图注写「两条单列自己的合约变体也计在这一段，但量很小」，在那几年是假话。
_FX_2105_M = '2021-05'
_FX_2105_TOTAL = 122194
_FX_2105 = (
    ('USD/INR (USD)', 44565),
    ('KRW/USD (Mini)', 35844),
    ('USD/SGD (Full-Sized)', 32987),
    ('USD/SGD', 3816),
    ('USD/CNH (Mini)', 3315),
    ('KRW/USD (Full Sized)', 625),
    ('TWD/USD (Mini)', 425),
    ('TWD/USD (Full Sized)', 380),
    ('EUR/CNH', 218),
    ('CNY/USD', 19),
)
_stamp_guard(f'「外汇期货」占比图残差段在 {_FX_2105_M} 期的逐行构成', _FX_2105, _FX_2105_TOTAL,
             _stamp_resid('vol_fx_futures_contracts',
                          ('vol_usdcnh_futures_contracts', 'vol_inrusd_futures_contracts'),
                          m=_FX_2105_M),
             '外汇期货合计 − USD/CNH − INR/USD', m=_FX_2105_M)
# 两期里「两条单列同一货币对的其他合约」各是哪几行 —— 图注按它们现算占比，不手写。
_FX_SAME_PAIR = ('USD/CNH (Mini)', 'USD/CNH FlexC', 'USD/INR (USD)')

# ── 「其中：铁矿石」这一列漏收的那一行（解析器缺陷，修复另有任务）─────────────────────
# 官方 Metal And Dry Bulk 小节里行名含 "Iron Ore" 的非零行，该期共 4 行、4,749,207 张；
# 而 vol_iron_ore_contracts 在 2026-08 是 4,714,191 —— 差的正是
# "SGX Platts Iron Ore CFR China (Lump Premium) Index Futures" 35,016 张：这一行的行名在 PDF 里
# 折成两行，解析器读到的行名只剩 "Index Futures"，匹配不上 "Iron Ore"。
# 同一份 PDF 并排印着 Jun / Jul 2026 两列，拿来核 CSV 的 2026-06 / 07 也是恰好少这一行
# （5,354,979 / 5,053,553 = 不含 Lump Premium 的三行之和）。
# 本轮**不动** fetch/ 与 series/（修复另起任务），所以页面文字照实交代漏收，不许说含 Lump Premium。
# ⚠️ 修复落地之后这一列会变，下面的守卫就会响：那时删掉 `_NOTE_COMM` 里那段 caveat、
#    释义「铁矿石」里那段 ⚠️、以及这一整段常数与守卫。
_IRON_COL_2608 = 4714191
_IRON_LUMP_2608 = 35016
_IRON_OFFICIAL_2608 = (
    ('SGX IODEX Iron Ore Futures', 4127939),
    ('SGX Options On IODEX Iron Ore Futures', 552512),
    ('SGX Platts Iron Ore CFR China (Lump Premium) Index Futures', _IRON_LUMP_2608),
    ('Iron Ore 65% Futures', 33740),
)
_IRON_OFFICIAL_2608_TOTAL = 4749207
_stamp_guard('铁矿石 caveat 引用的官方铁矿石行', _IRON_OFFICIAL_2608,
             _IRON_OFFICIAL_2608_TOTAL, None, '')
if _IRON_OFFICIAL_2608_TOTAL - _IRON_LUMP_2608 != _IRON_COL_2608:
    raise _StampMismatch('[sgx] 铁矿石 caveat 的三个常数自相矛盾：官方合计 − Lump Premium ≠ 本列值')
if _stamp_row() is not None and _num(_stamp_row(), 'vol_iron_ore_contracts') is not None \
        and _num(_stamp_row(), 'vol_iron_ore_contracts') != _IRON_COL_2608:
    raise _StampMismatch(
        f'[sgx] 铁矿石列已变 —— 若 Lump Premium 修复已落地，删掉这段 caveat 与本守卫'
        f'（series/sgx.csv 的 vol_iron_ore_contracts 在 {_STAMP_M} 现为 '
        f'{_num(_stamp_row(), "vol_iron_ore_contracts"):,.0f}，caveat 写的是 {_IRON_COL_2608:,}；'
        '要删的是 build/specs/sgx.py 里 `_NOTE_COMM` 的 caveat、释义「铁矿石」的 ⚠️ 与 `_IRON_*` 这段）')

# ── 这一行从哪一期开始漏（2026-09-12 第二轮审稿逐期核）───────────────────────────
# 拿本仓缓存的全部官方 PDF 逐期把行名含 "Iron Ore" 的行（折行的那一行也算上）加总、对 CSV：
#   · 2025-08 及之前缓存的 60 期（2015-01–2018-04 连续；2018-09、2019-06、2020-01、2021-05、
#     2022-11、2023-07；2024-07–2025-08 连续）**逐位相等** —— 那些期里这一行叫
#     "SGX Iron Ore Lump Premium Futures" / "Iron Ore Lump Premium Futures"，行名不折行，解析器收得到；
#   · 2025-09 起官方改名为折成两行的 "SGX Platts Iron Ore CFR China (Lump Premium) Index Futures"，
#     之后缓存的 12 期每期都恰好少这一行（下表第二格）。
# 所以上一版 caveat 的「更早的月份待修复时逐期核」「有这一行成交的月份系统性偏低」都说大了：
# 页面只许说 2025-09 起偏低。表的第三格是 CSV 在那一期的值，守卫逐期对 —— 解析器修好、回补之后
# 这一列会变，守卫就响（与上面 2026-08 那一道同进同出）。
_IRON_WRAP0 = '2025-09'
_IRON_CACHED_OK = 60
_IRON_LUMP_MISSED = (          # (月份, 漏收的 Lump Premium 张数, CSV 那一期的列值)
    ('2025-09', 8023, 6892804),
    ('2025-10', 8850, 5970671),
    ('2025-11', 9588, 4782724),
    ('2025-12', 22870, 5373102),
    ('2026-01', 17430, 6072415),
    ('2026-02', 19130, 4671490),
    ('2026-03', 36473, 7110182),
    ('2026-04', 24398, 5227211),
    ('2026-05', 12750, 4884570),
    ('2026-06', 28774, 5354979),
    ('2026-07', 29391, 5053553),
    ('2026-08', 35016, 4714191),
)
_IRON_BY_M = {m: (lump, col) for m, lump, col in _IRON_LUMP_MISSED}
if _IRON_LUMP_MISSED[0][0] != _IRON_WRAP0 or _IRON_BY_M.get(_STAMP_M) != (_IRON_LUMP_2608, _IRON_COL_2608):
    raise _StampMismatch('[sgx] 铁矿石 caveat 的逐期表自相矛盾：首月不是 _IRON_WRAP0，'
                         '或 2026-08 那一格与 _IRON_LUMP_2608 / _IRON_COL_2608 不等')
for _m, _lump, _col in _IRON_LUMP_MISSED:
    _r = _stamp_row(_m)
    if _r is not None and _num(_r, 'vol_iron_ore_contracts') is not None \
            and _num(_r, 'vol_iron_ore_contracts') != _col:
        raise _StampMismatch(
            f'[sgx] 铁矿石列已变 —— series/sgx.csv 的 vol_iron_ore_contracts 在 {_m} 现为 '
            f'{_num(_r, "vol_iron_ore_contracts"):,.0f}，caveat 的逐期表写的是 {_col:,}'
            f'（该期漏收 Lump Premium {_lump:,} 张）。若 Lump Premium 修复已落地，删掉 '
            '`_NOTE_COMM` 的 caveat、释义「铁矿石」的 ⚠️、notes 里「SGX 的头部衍生品」那条中'
            '2026-06 铁矿石后面的括号，以及 `_IRON_*` 这两段常数与守卫')
_IRON_LUMP_LO = min(l for _m, l, _c in _IRON_LUMP_MISSED)
_IRON_LUMP_HI = max(l for _m, l, _c in _IRON_LUMP_MISSED)
# 漏收量占「这一列 + 漏收量」的比例区间（= 这条线比官方口径低多少），给图注一个量级。
_IRON_GAP_PCT = [l / (c + l) * 100.0 for _m, l, c in _IRON_LUMP_MISSED]
# notes 里「SGX 的头部衍生品」那条引的是 2026-06 一期的铁矿石：那一期也在漏收表里，
# 所以那半句要带着括号交代（审稿 2026-09-12）。分母是那一期的衍生品当月成交合计（官方原值，
# 同一条 note 与 DDAV 那条 note 都引它），守卫对 CSV。
_DERIV_2606 = 34315225
_IRON_LUMP_2606, _IRON_COL_2606 = _IRON_BY_M['2026-06']
if _stamp_row('2026-06') is not None \
        and _num(_stamp_row('2026-06'), 'deriv_vol_contracts') not in (None, _DERIV_2606):
    raise _StampMismatch(
        f'[sgx] notes 引的 2026-06 衍生品当月成交合计是 {_DERIV_2606:,}，series/sgx.csv 却是 '
        f'{_num(_stamp_row("2026-06"), "deriv_vol_contracts"):,.0f} —— 那一行被回补 / 重述过，'
        '重核「SGX 的头部衍生品」与 DDAV 两条 note 里的读数')


def _zh_items(items):
    """[(名字, 张数), …] → 「名字 1,234、名字 56」。"""
    return '、'.join(f'{z} {n:,}' for z, n in items)


def _breaks():
    out = []
    # 台指授权换手：MSCI Taiwan 合约到期不再续约，SGX 改挂 FTSE Taiwan。
    # 从 CSV 读 FTSE 那条的首月（实测 2020-07），不写死。
    if _TW0:
        out.append({'month': _TW0, 'zh': '台指授权由 MSCI 换为 FTSE，两条序列不可直连'})
    # GIFT Nifty：GIFT Connect 迁移，同时改了计数口径（月份常数的依据见其定义处）。
    out.append({'month': _NIFTY_BREAK,
                'zh': 'GIFT Connect 迁移，Nifty 计数由「买卖孰高」改为双边合计'})
    # 底座画红虚线时按索引取月份，乱序会让标签配错断点 —— 统一按月份排。
    return sorted(out, key=lambda b: b['month'])


# ══ groups[].mix 那几张 100% 占比堆叠的图注（share_note，2026-09-12 起）══════════
# 底座在每张占比图的图注里已经现算了：各段最新值与窗口内极值、残差段最大占多少、
# 残差段薄到画不出来时的警告、右轴线是哪一段、同一个合计的另一种切法在哪一张
# （见 build/single.py 的 ex_mix_share）。所以下面这几段只补底座**算不出来**的那一半：
# 残差段里装着什么、分项本身是什么口径。
# 出现的数两类：从 CSV 现算的，与带「2026-08 期」戳的官方逐节核对（常数与守卫见上面那段）。
# ⚠️ 现算的中位 / 最大一律写明样本「YYYY-MM 起全期」：底座在同一段图注里印的是图窗
#    （Jan-16 起）内的区间，两种样本不写明就会被读成同一组数（例如「掉期」段底座印
#    窗口内最大 0.28%，这里的全期最大是 0.31%，看上去就像两处打架）。
def _swaps_off_zh():
    """「掉期」段与掉期列不相等的那几个月 → 「2018-08 +5 张、…」；一个都没有返回空串。"""
    if not _SW[0] or not _SW[5]:
        return ''
    return '、'.join(f'{m} {d:+,.0f} 张' for m, d in _SW[5])


# 2026-09-12 审稿后删掉了末尾那句「右轴那条线重画的是『其中：期权』那一段，不是掉期」——
# 那条线本身删了（理由见 SPEC 里这一组上方的注释）。
_NOTE_SPLIT_DERIV = (
    f'<b>「{_RESID_SWAPS_ZH}」这一段是减出来的，不是掉期那一列</b>：'
    '它 ≡ 当月成交合计 − 期货 − 期权，也就是官方掉期那一行的 Total '
    '<b>再加上</b>三桶（期货 / 期权 / 掉期）相加与合计之间的印刷差。'
    # 2026-09-12 第二轮审稿补：「期权」是本仓的桶，2022 年之前含总表第四行（`_OPT4_*`）。
    # 那一行在期权段里、不在这一段 —— 不点破，读者会拿官方 Total Options 去对「其中：期权」。
    '（「期权」按本仓的桶算：直到 2022 年官方总表另有一行场外清算期权，并在期权那一段、'
    '不在这一段，见释义「当月成交合计」。）'
    + ((f'series/sgx.csv {_SW[6]} 起全部 {_SW[0]} 个月里，{_SW[1]} 个月「期货 ＋ 期权 ＋ 掉期」'
        '与合计逐位相等'
        + (f'；其余 {len(_SW[5])} 个月「这一段 − 掉期列」分别是 {_swaps_off_zh()}'
           if _SW[5] else '')
        + f'。这一段占合计 {_SW[6]} 起全期中位 {_SW[3]:.3f}%、全期最大 {_SW[4]:.2f}%。')
       if _SW[0] else '')
    # 「当分项会超过合计」只在真有那种月份时才印 —— 哪天官方把印刷差修平了，这句自己消失。
    + ('⚠️ 所以<b>不把掉期列当第三个分项</b>：有月份三项相加比合计<b>多</b>，'
       '当分项画会让各段之和超过 100%（底座对此硬失败）；减出来的这一段没有这个问题。'
       if _SW[0] and any(d < 0 for _m, d in _SW[5]) else '')
)

# ── 指令四：业务占比图为什么用「衍生品张数按资产类别切」──────────────────────
# 页面所有者 2026-09-12 要一张 SGX 的业务占比图。候选指标逐个过了一遍：
#   · 证券成交额（S$）：单位是钱，与衍生品的张数进不了同一个堆叠；
#   · 名义额：本仓没有 SGX 任何一条合约的乘数（series/contract_specs.csv 的
#     SGX_DERIV 一行「乘数零个实测」，build/notional.py 因此换不出 SGX 的名义额）；
#   · 按业务分部的收入：SGX 半年报口径，本仓没有这组数。
# ⇒ 剩下唯一站得住的是衍生品当月成交张数按资产类别切：分母 = deriv_vol_contracts，
#   三段 = 股指期货合计 / 外汇期货合计 / 商品合计（不含加密），其余是残差。
#   它是「衍生品成交与未平仓」那个合计的**第二种切法**，所以挂在那组 mix 的
#   alt_splits 上（底座只画一次合计柱），不另起一组去再画一遍同一个合计。
# ⚠️ 这张图的三个坑必须印在它自己的图注里（不是只写在这段注释里）：
#   单位是张不是钱；现货不在里面；三段覆盖范围不对称（股指 / 外汇只取 Futures 小节，
#   商品按官方定义含期权与掉期）。
_NOTE_ASSET = (
    '<b>这张是 SGX 衍生品按资产类别的业务结构（页面所有者 2026-09-12 要的业务占比图），'
    '读之前先把三件事说清：</b>'
    '① <b>单位是张</b>，不是名义额、也不是收入。各类合约一张的大小差得很远，'
    '所以<b>张数份额 ≠ 金额份额 ≠ 收入份额</b>：换成名义额要走 '
    '<code>build/notional.py</code>，而本仓没有 SGX 任何一条合约的乘数实测'
    '（<code>series/contract_specs.csv</code> 的 SGX_DERIV 一行）；'
    '按业务分部的收入是半年报口径，本仓没有。'
    '② <b>现货不在里面</b>：证券成交是 S$ 金额，与张数进不了同一个堆叠，'
    '现货规模看「证券市场成交」那一组。'
    '③ <b>三段的覆盖范围不对称</b>：股指、外汇两段只取官方 <u>Futures</u> 小节的 Total，'
    '而商品一段按官方定义含期货、期权与掉期（不含加密）⇒ '
    f'凡是计入合计、又不在这三段里的合约都落进最上面那段「{_RESID_DERIV_ASSET_ZH}」。'
    f'<b>{_STAMP_M} 期官方月报逐节核对</b>（<code>{_STAMP_SRC}</code>）：'
    'SGX 自己的各成交量小节相加恰好等于当月成交合计'
    '（报告里 NSE-IX 口径的 GIFT Nifty 全市场量那一节不在其中），'
    f'这一段 {_DERIV_OTHER_2608_TOTAL:,} 张逐位等于 '
    + _zh_items([(z, n) for z, n, _c in _DERIV_OTHER_2608])
    + ' 张 ⇒ <b>加密永续与个股期货都计在合计里</b>，落在这一段。'
    # 2026-09-12 审稿后补：这一段的构成随年代换过，名字的排序依据要印在图上（常数与守卫见
    # `_DERIV_OTHER_ERAS`）。每期只点最大的两块，占比由常数现算。
    + '⚠️ <b>这一段装着什么随年代换过</b>（名字按全窗口的量级排序，不按最新一期）：'
    + '；'.join(f'{m} 期（<code>cache/sgx_{m}.pdf</code>）{t:,} 张里'
                + '、'.join(f'{z} {n / t * 100:.0f}%'
                           for z, n in sorted(items, key=lambda x: -x[1])[:2])
                for m, t, items in _DERIV_OTHER_ERAS)
    + f'；{_STAMP_M} 期是'
    + '、'.join(f'{z} {n / _DERIV_OTHER_2608_TOTAL * 100:.0f}%'
               for z, n, _c in sorted(_DERIV_OTHER_2608, key=lambda x: -x[1])[:2])
    + '。'
    + (f'利率期货占这一段 {_AS[6]} 起全期中位 {_AS[5]:.1f}%'
       + (f'，≥30% 的只有 {"、".join(_AS[7])} 这 {len(_AS[7])} 个月' if _AS[7] else '')
       + '（其余几类本仓没有列、或上线太晚，给不出全期中位）。'
       if _AS[0] and _AS[5] is not None else '')
    + (f'{_AS[6]} 起全期 {_AS[0]} 个月各段的中位：股指期货 {_AS[1]:.1f}%、'
       f'外汇期货 {_AS[2]:.1f}%、商品 {_AS[3]:.1f}%、其他 {_AS[4]:.1f}%'
       '（四个中位各自独立取，相加不必等于 100）。' if _AS[0] else '')
)

_NOTE_EQIX = (
    f'<b>最上面那段「{_RESID_EQIX_ZH}」</b> ≡ 股指期货合计 − A50 − 日経225 − MSCI 新加坡。'
    '里面最大的两块是 <b>GIFT Nifty 50</b> 与<b>台湾指数期货</b>，而台湾那一块换过合约：'
    + (f'{_TW0} 起是 FTSE 台湾（它与 GIFT Nifty 50 在本页各有自己的柱图），'
       '在那之前是 MSCI 台湾期货（授权到期后停发，本页不画那一列）'
       if _TW0 else
       'FTSE 台湾（本页有自己的柱图）接的是停发的 MSCI 台湾期货（本页不画那一列）')
    + (f' —— FTSE 台湾上线之前的 {_EQ[7]} 个月里，MSCI 台湾占这一段中位 {_EQ[6]:.0f}%'
       + (f'，其中 {_EQ[8]} 个月比 GIFT Nifty 还大' if _EQ[8] else '')
       if _EQ[7] else '')
    + (f'。GIFT Nifty 50 与台湾指数期货（MSCI ＋ FTSE 两列相加）合计占这一段 {_EQ[5]} 起'
       f'全期中位 {_EQ[2]:.0f}%、最低 {_EQ[3]:.0f}%（series/sgx.csv {_EQ[4]} 个月现算）'
       if _EQ[4] and _EQ[2] is not None else '')
    + '；其余是官方另行分列、本页没有列的指数合约'
      '（例如日経225 的 Mini / USD / Micro 等变体就不在「日経225 期货」那一段里）。'
    f'<b>{_STAMP_M} 期官方月报逐行核对</b>（<code>{_STAMP_SRC}</code>）：'
    f'扣掉 GIFT Nifty 50 与 FTSE 台湾之后这一段还剩 {_EQIX_OTHER_2608_TOTAL:,} 张，'
    f'是官方股指期货小节里其余非零的 {len(_EQIX_OTHER_2608)} 行 —— '
    + _zh_items(_EQIX_OTHER_2608) + ' 张。'
    f'⚠️ GIFT Nifty 在 {_NIFTY_BREAK} 改了计数口径（「买卖腿孰高」→ 买卖双边合计），'
    '它计在这一段里、也就计在分母里 ⇒ <b>这一段连同分母在断点两侧都不是同一把尺子</b>，'
    'A50 等三段的占比跨断点比较时同样要扣掉这一层。'
)

# 「最大的一块」与「两条单列同一货币对的其他合约合起来多大」都从常数现算，不再手写一遍。
# 2026-09-12 审稿后改写：上一版说「两条单列自己的合约变体……量很小」—— 2026-08 一期是这样，
# 2021-05 期光 USD/INR (USD) 一行就占这一段三成多（`_FX_2105`）。两期都印，不把一期当常态。
_FX_TOP = max(_FX_OTHER_2608, key=lambda x: x[1])
_FX_OWN_VARIANTS = [x for x in _FX_OTHER_2608 if x[0] in _FX_SAME_PAIR]
_FX_OWN_2105 = [x for x in _FX_2105 if x[0] in _FX_SAME_PAIR]
_FX_USDINR_2105 = dict(_FX_2105)['USD/INR (USD)']
_NOTE_FX = (
    f'<b>最上面那段「{_RESID_FX_ZH}」</b> ≡ 外汇期货合计 − USD/CNH − INR/USD。'
    '里面装两类：<b>本页没有列的其他货币对</b>，与<b>两条单列同一货币对的其他合约</b>'
    '（「USD/CNH 期货」不含 Mini 与 FlexC，「INR/USD 期货」不含 FlexC，出处 fetch/sgx.py 的列口径表；'
    '「INR/USD 期货」也不含行名带 (USD) 的 USD/INR 期货，那几行官方另行分列）。'
    '<b>两类谁大随年代换过</b>，下面两期都是官方月报逐行核对。'
    f'<b>{_STAMP_M} 期</b>（<code>{_STAMP_SRC}</code>）：'
    f'这一段 {_FX_OTHER_2608_TOTAL:,} 张是官方外汇期货小节里其余非零的 {len(_FX_OTHER_2608)} 行 —— '
    + _zh_items(_FX_OTHER_2608) + ' 张；'
    f'最大的一块是 {_FX_TOP[0]}，占这一段 {_FX_TOP[1] / _FX_OTHER_2608_TOTAL * 100:.0f}%，'
    '同一货币对的其他合约（' + '、'.join(z for z, _n in _FX_OWN_VARIANTS)
    + f'）合起来只占 {sum(n for _z, n in _FX_OWN_VARIANTS) / _FX_OTHER_2608_TOTAL * 100:.1f}%。'
    f'<b>{_FX_2105_M} 期</b>（<code>cache/sgx_{_FX_2105_M}.pdf</code>）：'
    f'这一段 {_FX_2105_TOTAL:,} 张里，同一货币对的其他合约（'
    + _zh_items(_FX_OWN_2105)
    + f' 张）合起来占 {sum(n for _z, n in _FX_OWN_2105) / _FX_2105_TOTAL * 100:.0f}%，'
      f'光 USD/INR (USD) 一行就占 {_FX_USDINR_2105 / _FX_2105_TOTAL * 100:.0f}%。'
    + (f'USD/CNH 与 INR/USD 两段合计占外汇期货合计 {_FX[4]} 起全期中位 {_FX[2]:.1f}%'
       f'（series/sgx.csv {_FX[0]} 个月现算，全期区间 {_FX[1]:.1f}–{_FX[3]:.1f}%）。'
       if _FX[0] else '')
    + '分母只含<b>期货</b>：官方 FX 期权另起一节，不在这张图里。'
)

# 2026-09-12 审稿后改写。上一版说残差段「即官方商品各节里行名不含 "Iron Ore" 的那些合约」——
# 假话：这一列在 2026-08 期漏收了一行行名含 "Iron Ore" 的合约（`_IRON_2608` 那段），
# 那一行的量就在残差段里。caveat 与 `_IRON_*` 守卫同进同出：修复落地、守卫一响，两样一起删。
_NOTE_COMM = (
    '<b>「其中：铁矿石」是本仓自己汇总的一条</b>，不是官方某一行的 Total：'
    '按设计是各成交量小节里行名含 "Iron Ore" 的行（期货 ＋ 期权 ＋ 掉期，含 OTC 清算腿）全部相加，'
    '<code>fetch/sgx.py</code> 拿 SGX 新闻稿逐位核过 Dec-2015 那一期（＝ 988,532）。'
    f'<b>最上面那段「{_RESID_COMM_ZH}」</b> ≡ 商品合计 − 「其中：铁矿石」这一列'
    + (f'；这一列占商品合计 {_IO[1]} 起全期中位 {_IO[0]:.0f}%' if _IO[0] else '')
    + '。'
    # 第二轮审稿（2026-09-12）把 caveat 收窄到 `_IRON_WRAP0` 起：更早的缓存各期逐位相等，
    # 「更早的月份待核」「有这一行成交的月份系统性偏低」都说大了（逐期表与守卫见 `_IRON_LUMP_MISSED`）。
    f'⚠️ <b>这一列 {_IRON_WRAP0} 起漏收一行铁矿石</b>：{_STAMP_M} 期官方月报（<code>{_STAMP_SRC}</code>）里'
    f'行名含 "Iron Ore" 的非零行共 {len(_IRON_OFFICIAL_2608)} 行、合计 '
    f'{_IRON_OFFICIAL_2608_TOTAL:,} 张，这一列却是 {_IRON_COL_2608:,} 张 —— 差的 '
    f'{_IRON_LUMP_2608:,} 张正是 "SGX Platts Iron Ore CFR China (Lump Premium) Index Futures" 那一行。'
    f'拿本仓缓存的各期官方 PDF 逐期核过（2026-09-12）：{_IRON_WRAP0} 之前缓存的 {_IRON_CACHED_OK} 期'
    '这一列与官方逐位相等（那时这一行叫 "Iron Ore Lump Premium Futures"，行名不折行，解析器收得到）；'
    f'{_IRON_WRAP0} 起官方改成上面那个在 PDF 里折成两行的行名，解析器没认出来，'
    f'之后 {len(_IRON_LUMP_MISSED)} 期每期都恰好少这一行'
    f'（{_IRON_LUMP_LO:,}–{_IRON_LUMP_HI:,} 张，这条线因此比官方口径低 '
    f'{min(_IRON_GAP_PCT):.1f}–{max(_IRON_GAP_PCT):.1f}%）。'
    f'<b>所以 {_IRON_WRAP0} 起、修复落地之前，这一行的量画在「{_RESID_COMM_ZH}」里</b>，'
    '「其中：铁矿石」那一段相应偏薄 —— 最上面那段不能读成「铁矿石以外的商品」。'
    '分母按官方定义<b>不含加密</b>（加密永续另成一组，页尾有逐项对账）。'
)


# ── 页尾原来有两张「水平值 + 12 个月滚动同比」，2026-09 全部删掉 ────────────
# 那两张画的是 `sec_turnover_mnshares` 与 `sec_turnover_sgdmn`，用途是「一整年在不在
# 长」，与「证券市场成交」组图里同名的两张（单月同比）分工。全站同比按页面所有者的
# 指令统一成单月之后，两边变成**同一列、同一窗口、同一口径** —— 组图那三列各占一个
# 单位桶（S$mn/day、S$mn/month、mn shares/month），底座本来就把它们各画成一张
# gs_bar + 次轴单月同比，页尾再画一遍是一字不差的重复。
# 底座对此有硬护栏（build/single.py 的 `ex_level_yoy`：撞上 SpecError），
# 所以 `_TTM_YOY`、`_ttm_names_zh()`、`_ttm_deriv_zh()` 三样一并删除，不留死代码。
# 「衍生品那一侧一张滚动图都没有」那句提醒也随之作废：现在全页只有一种口径，
# 证券与衍生品两侧读的是同一种同比。


# ══════════════════════════════════════════════════════════════════════════════
# 名词释义（SPEC 的 `glossary`，排在所有 exhibit 之前）
#
# ━━ 与页尾 notes / 图注的分工 ━━
# notes 与图注说的是「这一张图这个月该怎么读」（含当月读数、当月实测的毛刺量）；
# 这一块说的是「这些词是什么意思」，一年到头是同一段 ⇒ 这里**不写当月读数**。
# 出现的数只有两类：把定义钉住的结构性量（恒等式的实测偏差、「掉期」段占多大、
# 单列产品占合计多少、换手率反推倍数的浮动区间）与恒等式本身；**一个都不写死**，
# 全部在 import 期从 series/sgx.csv 现算（同本文件其余图注的做法）。
# 唯一的两个字面常数是官方文件里的：GIFT Nifty 两处口径的 FY2026 读数
# （20,699,069 / 24,357,137，出处 fetch/sgx.py 口径坑 2 与 docs/verify/sgx.md，
# 那两个数印在报告里、不随本仓的月份走）与铁矿石的 Dec-2015 对账值 988,532
# （SGX 新闻稿原文 "Iron Ore Derivatives volume was 988,532"，同一处出处）。
#
# ━━ 为什么是这几个词（选词判断）━━
# **这里不写词数**：上一版这块写着「14 个」、SPEC 里 'glossary' 上方写着「13 个」，
# 两处当场对不上。要当期数字就现数 `len(_GLOSSARY)`。
# 判据只有一条：这个词出现在本页的图题 / 序列名 / 纵轴 / 汇总表行头里，而且
# **不看定义就会读错**。按「读错会出什么事」分四类：
#   ① 缩写与它的分母   SDAV / DDAV / 张（contracts）—— 本页两条头条都是「日均」，
#      而证券侧的恒等式成立、衍生品侧**不成立**（交易日那一行是证券市场口径）。
#      不点破，读者会拿交易日去反推衍生品月量；张数不点破，读者会拿本页的
#      日経225 张数直接去比 JPX 的日経225 张数 —— 那正是 build/notional.py 与
#      series/contract_specs.csv 明文说不可比的那种比法（根因是合约乘数）；
#      2026-09-12 起还多一处：「按资产类别的占比」是**张数**份额，不是金额份额。
#   ② 「合计」与单列分项之间隔着一块残差   当月成交合计（期货 / 期权之外是掉期与印刷差）、
#      股指期货合计（单列三条之外还有 GIFT Nifty、台湾指数期货 —— 2020-07 之前是 MSCI 台湾、
#      之后是 FTSE 台湾 —— 与其它指数合约）、
#      外汇期货合计（不含 FX 期权；单列两条之外主要是别的货币对，两条自己的
#      Mini / FlexC 变体只是很小一块 —— 2026-08 期逐行核过，见 `_FX_OTHER_2608`）——
#      2026-09-12 之前这几组是「合计 + 分项」同轴的多条折线，相加对不上最容易被当成
#      「数据错了」；改成 100% 占比堆叠之后，那块残差是每张图最上面的一段，
#      不看释义就不知道那一段里装的是什么，会被读成「一块查不到的业务」。
#   ③ 同名不同数 / 派生量   GIFT Nifty 50（官方另一节同名行是 NSE-IX 全市场口径）、
#      铁矿石（本仓跨小节自己汇总的一条）、加权平均成交价（分解图里轧出来的，
#      不是公司披露的数）—— 读串的代价是整条线系统性偏高或偏低而图形完全正常。
#   ④ 口径边界   换手率（官方只算 primary listed securities，且只印整数 pp）、
#      上市证券只数（不含债券，且数的是证券不是公司）、上市家数 / 募资额
#      （家数不含 RTO、募资额含 RTO）、未平仓（OI，月末截面）、永续期货
#      （无到期日，且不计入商品合计）。
# **有意不收**：
#   · m/m、y/y、3Y %ile、pp/bp —— 全站通用读图约定，summary.note 已逐条讲过；
#   · 「口径断点」「慢腿」「存量 vs 流量」的**总则**、按千 / 按百万的显示缩放、
#     单月同比的代价 —— 页尾 notes 里「口径断点」「存量与流量分开读」「同比口径」
#     「图上的显示缩放」那几条（按标题点名，不写第几条：页尾条目一增一删就错位；
#     本页没有慢腿，底座那一条不出）与逐张图注讲的就是这几件事在本页的落点，
#     释义板再讲一遍就是两处各写一份（未平仓单列一条是因为 OI 这个**词**本身要解释：
#     它含掉期、是月末截面，总则不重复）；
#   · 成交额 / 市值 / IPO 这类本页没有特殊口径的常识词；
#   · 「残差段」「100% 占比堆叠」这类图型词 —— 底座在每张占比图的图注里逐张讲过；
#   · 页面上根本不出现的列（sec_trading_days、掉期那一列本身、MSCI 台湾）——
#     它们只在真正用得上的那一条释义里被顺带点名，不各占一条。
# ══════════════════════════════════════════════════════════════════════════════
_GLOSSARY = [
    ('SDAV',
     '官方缩写 Securities Daily Average：证券市场当月成交<b>金额</b>的日均值'
     '（S$mn/day），是 SGX 财报与新闻稿引用最多的那个数，本页头条第一格与'
     '「日均成交额 SDAV」画的都是它。证券这一侧恒等式成立：'
     '<code>当月成交额 ÷ 当月证券市场交易日数 = SDAV</code>'
     + (f'（{_SD[0]} 个月现算，最大相对差 {_SD[1]:.3f}%，量级就是 SDAV 取整到 '
        f'S$mn 的舍入）' if _SD[0] else '')
     + ' ⇒ 「当月成交额」与「日均成交额 SDAV」<b>不是两个指标</b>，'
       '只差一个当月开市天数。⚠️ 这条恒等式<b>只在证券侧成立</b>，衍生品侧见下一条。'),

    ('DDAV',
     '官方缩写 Derivatives Daily Average Volume：衍生品当月成交的日均<b>张数</b>'
     '（contracts/day），也是与 HKEX / CME 跨所可比的那一条。'
     '⚠️ <b>不能</b>用「当月成交合计 ÷ 交易日数」反推：官方那一行交易日数括号里写的是 '
     '(Stock Market) / (Securities)，是<b>证券市场</b>的交易日，'
     '衍生品的假期表与夜盘归属日都不一样'
     + (f' —— 用官方两个数反算出来的隐含天数在 {_DD[2]:.1f}–{_DD[3]:.1f} 天之间，'
        f'{_DD[0]} 个月里<b>没有一个月</b>等于当月证券交易日数'
        f'（硬拿证券交易日去除，相对差中位 {_DD[4]:.1f}%、最大 {_DD[5]:.1f}%）'
        if _DD[0] else '')
     + '。所以本页月总量与日均两条都直接取官方值，谁也不从谁推。'),

    # 「不做千张换算」的主语是**入库**（出处 fetch/sgx.py：「本模块不做任何换算」），
    # 不是「本页」—— 本页的图大多做了按千 / 按百万的**显示**缩放（页尾「图上的显示缩放」
    # 那一条），写成「本页」就与那一条打架。
    # ⚠️ 指那一条**按标题点名，不写第几条**：上一版这里写的是「页尾说明第 7 条」，
    # 而底座那一段在页尾实际排第 8（前面多了一条断点说明）—— 条目一增一删就错位。
    # 「单边计数」出处 fetch/sgx.py 的列口径表；**计数惯例一致 ≠ 张数可比**：
    # 张数跨所不可比的根因是合约乘数，见 build/notional.py 的模块 docstring 与
    # series/contract_specs.csv（JPX_N225_MINI 一行：JPX 官方产品页写明 mini 是
    # 大板的 1/10、micro 是 1/100；CME_EQUITY_INDEX 一行：ES $50/点 vs MES $5/点）。
    # 本仓连 SGX 一条合约的乘数都没有实测（同表 SGX_DERIV 一行「乘数零个实测」），
    # 更无从断言它与 JPX / HKEX 的同标的合约等大。
    ('张（contracts）',
     '衍生品各列的单位，官方新闻稿里写作 "lots"，与本页的「张」是同一个东西。'
     '<b>入库、汇总表与末尾核对表</b>一律用官方原值、不做千张 / 万张换算'
     '（图上另有按千 / 按百万的<b>显示</b>缩放，只作用于图、不作用于表，'
     '见页尾「图上的显示缩放」那一条）。'
     'SGX 的成交张数按<b>单边</b>计（一手买 ＋ 一手卖记 1 张），与 CME / HKEX 是'
     '同一种计数惯例 —— 同一笔成交在哪一家都不会被记两次。'
     '⚠️ 但<b>计数惯例一致不等于张数能直接比大小</b>：那还要看合约乘数'
     '（JPX 的日経225 mini 是大板的 1/10、micro 是 1/100，CME 的 ES 是 $50/点、'
     'MES 是 $5/点），本仓也没有 SGX 任何一条合约的乘数实测。'
     '⇒ 跨所比规模走 <code>build/notional.py</code> 的定基美元名义额，<b>不比张数</b>；'
     '同一个原因，本页「按资产类别的占比」画的是<b>张数份额</b>，不是金额份额。'
     '<b>单边计数本身还有一个例外是 GIFT Nifty</b>：'
     f'{_NIFTY_BREAK} 之前官方按「买卖腿孰高」计量、之后才改成买卖双边合计，'
     '断点两侧不是同一把尺子（见下面那条与页尾口径说明）。'),

    ('换手率',
     '官方行名 Overall Turnover Velocity（年化换手率）。本页原样入库，'
     '只保留官方印出的<b>整数百分点</b>'
     # 全是整数与「有几个不是」两种说法都留着：官方哪天开始印小数，这句会自己改口。
     + ((f'（{_VE[0]} 个月全部是整数，读数区间 {_VE[2]:.0f}–{_VE[3]:.0f}%）'
         if _VE[1] == _VE[0] else
         f'（{_VE[0]} 个月里 {_VE[1]} 个是整数，读数区间 {_VE[2]:.0f}–{_VE[3]:.0f}%）')
        if _VE[0] else '')
     + ' ⇒ 这一行的变化一律是整 pp。⚠️ 它<b>算不出来</b>：官方脚注写明分子（成交额）'
       '与分母（市值）都只取 primary listed securities，而本页的「当月成交额」与'
       '「月末总市值」是全市场口径 —— 拿这两列相除去反推'
     + (f'，倍数在 {_VE[4]:.1f}–{_VE[6]:.1f} 之间浮动（中位 {_VE[5]:.1f}），'
        f'<b>不是一个常数</b>。' if _VE[0] else '，得不到官方那条线。')),

    ('上市证券只数',
     '月末在册的上市<b>证券只数</b>（存量），官方脚注<b>不含</b> GDR、对冲基金与'
     '<b>债券</b>。两处别接错：① 它数的是<b>证券</b>、不是公司，'
     '与「当月新上市家数 / 当月退市家数」（companies）不是同一套计数，'
     '两者不能相减去对账；② 「当月新债券挂牌数」再多也<b>不会</b>加进这一条 —— '
     '债券本来就不在它的口径里。'),

    # 2026-09-12 改写：上一版说「本页只画前两条（期货 / 期权），掉期不上页面 ⇒ 两条
    # 『其中』相加比合计少的那一点就是掉期」—— 那是三条折线时代的读法。改成占比堆叠之后
    # 那一点是图上最上面一段，要说清的变成「那一段是减出来的、不等于掉期列」。
    # 2026-09-12 第二轮审稿改：上一版写「期货 ＋ 期权 ＋ 掉期（官方三节各自的 Total）」——
    # 2022 年之前官方总表是四行，第四行场外清算期权被本仓并进期权桶（常数与守卫见 `_OPT4_*`）。
    ('当月成交合计',
     '衍生品当月成交总张数（官方总表 Derivatives Overall Market Volume 的 Total Trading Volume），'
     '本仓按总表的行名拆成<b>期货 ＋ 期权 ＋ 掉期</b>三桶。'
     '⚠️ 「其中：期权」这一桶<b>不一定等于</b>官方 Total Options 那一行：直到 2022 年，'
     '总表还另有一行场外清算的期权（2018-08 及之前叫 Total AsiaClear Cleared Options Volume、'
     '之后叫 Total Options On Swaps Volume），本仓把它并进期权桶'
     f'（{_OPT4_M} 期官方 Total Options {_OPT4_TOTAL_OPTIONS:,} 张 ＋ 这一行 {_OPT4_ROW:,} 张 ＝ '
     f'本页「其中：期权」{_OPT4_TOTAL_OPTIONS + _OPT4_ROW:,} 张；本仓缓存的 2018-09 至 2021-05 各期'
     '这一行都是 0，2022-11 期起总表不再印它）。'
     '本页拿合计当分母画两种切法的 100% 占比堆叠：按期货 / 期权 / 掉期，与按资产类别。'
     f'⚠️ 前一种里那段「{_RESID_SWAPS_ZH}」<b>不是直接取自掉期那一列</b>，'
     '而是减出来的（合计 − 期货 − 期权）⇒ 它 ＝ 掉期 ＋ 官方自己的印刷差'
     + (f'（{_SW[0]} 个月现算：{_SW[1]} 个月三项相加与合计逐位相等，'
        f'其余最大差 {_SW[2]:.0f} 张）' if _SW[0] else '')
     + ((f'；这一段占合计 {_SW[6]} 起全期中位 {_SW[3]:.3f}%、全期最大 {_SW[4]:.2f}%'
         + ('，在堆叠里几乎没有高度 ⇒ 图上找不到它<b>不是漏了数</b>'
            if _SW[4] < 1 else ''))
        if _SW[0] else '')
     + '。两种切法的段<b>不能跨图相加减</b>：「期货」那一段里就含着股指、外汇与商品三类的期货。'),

    ('未平仓（OI）',
     'open interest：<b>月末</b>仍未了结的合约张数，产品范围与「当月成交合计」相同'
     '（同样含掉期），但<b>不是同一类量</b> —— 成交是当月累计发生的流量，'
     '未平仓是某一天的<b>截面（存量）</b>。⇒ 两者不能相加、也不宜直接比大小；'
     '把 12 个月末快照加起来不指代任何真实的量，所以它的同比只能走点对点'
     '（月末 vs 去年同月月末）。'),

    # 2026-09-12 改写：上一版的结尾是「别拿它们相加去凑合计、也别把它们当成合计的
    # 分部拆解」—— 占比堆叠恰恰就是把它们当成合计的分部画（残差段显式画出来），
    # 那半句在新页面上是假话。
    ('股指期货合计',
     '官方 Equity Index Futures 小节的 <code>Total</code>（只含<b>期货</b>），'
     '<b>不是</b>本页点名的那几条产品之和：'
     + (f'A50 ＋ 日経225 ＋ MSCI 新加坡三条 {_EQ[5]} 起全期中位只占它 {_EQ[0]:.0f}%，'
        '再把 GIFT Nifty 与台湾指数期货'
        + (f'（{_TW0} 之前是 MSCI 台湾、之后是 FTSE 台湾）' if _TW0 else '')
        + f'也算进来是 {_EQ[1]:.0f}%，'
        if _EQ[4] else '')
     + '剩下的是官方另行分列的其它指数合约。'
       '⇒ 「股指期货」那张 100% 占比堆叠只把前三条各画一段，其余全部并进最上面那段'
     + f'「{_RESID_EQIX_ZH}」—— 那一段里装的是 GIFT Nifty、台湾指数期货与其它指数合约'
       '（本页给 GIFT Nifty 与 FTSE 台湾各画了一张柱图，停发的 MSCI 台湾那一列不画），'
       '<b>不是</b>一块查不到的业务。'
       '⚠️ 另一处：「日経225 期货」只含标准合约，<b>不含</b> Mini / USD / Micro / TR / '
       'ESG-REIT 那几个变体（官方各自单列）。'),

    ('GIFT Nifty 50',
     '本页这一条是 <b>SGX-ICI 成交、SGX 自己清算</b>的口径。'
     '⚠️ 官方同一份报告里<b>另有一节</b>（GIFT Nifty Overall Market Volume）印着'
     '同名的一行，那是 NSE-IX <b>整个市场</b>的量、不全归 SGX：'
     '官方 FY2026 两处分别是 20,699,069 与 24,357,137 张，差 18% —— '
     '拿错那一节会把本页这条整体抬高。'
     f'另：{_NIFTY_BREAK} 起计数口径由「买卖腿孰高」改为买卖双边合计，'
     '断点两侧不可直连（页尾口径说明里有断点两侧水平差为什么不做归因）。'),

    # 与「股指期货合计」同一形状的坑，出处 fetch/sgx.py 的列口径表三行：
    # vol_fx_futures_contracts「不含 FX 期权」、vol_usdcnh「不含 Mini / FlexC」、
    # vol_inrusd「不含 FlexC」。2026-09-12 之前「外汇期货」那组是合计与两条分项同轴的
    # 三条折线，相加对不上是本页第二处最容易被当成「数据错了」的地方（第一处是掉期）；
    # 改成占比堆叠之后，要说清的变成最上面那段残差里装着什么。
    ('外汇期货合计',
     '官方 Foreign Exchange <u>Futures</u> Volume 小节的 <code>Total</code>，'
     '<b>不含 FX 期权</b> ⇒ 它<b>不是</b> SGX 全部外汇衍生品的量，'
     '跨所对外汇业务规模时先看对面那个数含不含期权。'
     '与「股指期货合计」同一个坑：本页单列的两条（USD/CNH、INR/USD）加起来<b>不是</b>它'
     # 上界给一位小数：整数会印成「100%」，读成「有的月份两条就是全部」，
     # 而实测最大 99.5%，never 到 100 —— 那一位小数正是这条释义的论据。
     + (f' —— 两条相加占合计 {_FX[4]} 起全期中位 {_FX[2]:.1f}%（{_FX[0]} 个月现算，'
        f'全期区间 {_FX[1]:.1f}–{_FX[3]:.1f}%）' if _FX[0] else '')
     # 2026-09-12 审稿后改写：上一版先讲两条单列各自去掉的 Mini / FlexC、再说「剩下的是
     # 其它货币对与合约变体」，读起来像残差主要是那几个变体。2026-08 期官方逐行核下来，
     # 残差里最大的是别的货币对（`_FX_OTHER_2608`），两条单列的变体合起来不到 1%。
     # 第二轮审稿再改：「变体量很小」只是 2026-08 一期的事 —— 2021-05 期行名带 (USD) 的
     # USD/INR 期货一行就占这一段三成多（`_FX_2105`），所以不写成常态。
     + '。剩下的是两类：<b>本页没有列的其他货币对</b>'
     + f'（{_STAMP_M} 期最大的一块是 {_FX_TOP[0]}），与两条单列<b>同一货币对的其他合约</b> —— '
       '「USD/CNH 期货」只含标准合约、<b>不含</b> Mini 与 FlexC，'
       '「INR/USD 期货」<b>不含</b> FlexC、也不含行名带 (USD) 的 USD/INR 期货（官方各自单列）。'
     + f'后一类 {_STAMP_M} 期合起来很小，但 {_FX_2105_M} 期光 USD/INR (USD) 一行就占这一段 '
       f'{_FX_USDINR_2105 / _FX_2105_TOTAL * 100:.0f}%。'
     + f'⇒ 「外汇期货」那张 100% 占比堆叠把这一块画成最上面那段「{_RESID_FX_ZH}」，'
       '它<b>不是</b>漏了数，也不是一块查不到的业务。'),

    # 2026-09-12 审稿后改写：上一版写「62% / 65% / 58% / IODEX / Lump Premium」全部相加、
    # 「口径与官方对得上」。2026-08 期官方月报逐行核下来，Lump Premium 那一行没收进来
    # （常数与守卫见 `_IRON_*` 那段）。Dec-2015 那一次逐位核对是真的，但它管不到后来新增的行。
    # 这段 ⚠️ 与 `_NOTE_COMM` 的 caveat、`_IRON_*` 守卫同进同出。
    ('铁矿石',
     '<b>本仓自己汇总的一条</b>，不是官方某一行的 Total：按设计是把各成交量小节里行名含 '
     '"Iron Ore" 的行（62% / 65% / 58% / IODEX 等，'
     '<b>期货 ＋ 期权 ＋ 掉期</b>，含 OTC 清算腿）全部相加，'
     '<code>fetch/sgx.py</code> 拿 SGX 新闻稿逐位核过 Dec-2015 那一期（＝ 988,532）。'
     f'⚠️ <b>但它 {_IRON_WRAP0} 起漏收一行</b>：官方从那一期起把 Lump Premium 那一行改名为 '
     '"SGX Platts Iron Ore CFR China (Lump Premium) Index Futures"，行名在 PDF 里折成两行，'
     f'解析器没认出来（{_STAMP_M} 期那一行 {_IRON_LUMP_2608:,} 张：官方行名含 "Iron Ore" 的行合计 '
     f'{_IRON_OFFICIAL_2608_TOTAL:,} 张，这一列是 {_IRON_COL_2608:,} 张）。'
     f'拿本仓缓存的官方 PDF 逐期核过：{_IRON_WRAP0} 之前缓存的 {_IRON_CACHED_OK} 期逐位相等'
     f'（那时这一行不折行、解析器收得到），{_IRON_WRAP0} 起缓存的 {len(_IRON_LUMP_MISSED)} 期每期都恰好少这一行。'
     f'⇒ 修复落地之前，这条线 {_IRON_WRAP0} 起<b>逐月偏低</b>'
     f'（每期少 {_IRON_LUMP_LO:,}–{_IRON_LUMP_HI:,} 张，比官方口径低 '
     f'{min(_IRON_GAP_PCT):.1f}–{max(_IRON_GAP_PCT):.1f}%），'
     f'漏掉的量画在「商品」那张占比图的「{_RESID_COMM_ZH}」段里'
     '（「商品合计」本身取官方各节 Total，不受影响）。它落在「商品合计」里面'
     + (f'，是那一档里最大的一块（{_IO[1]} 起全期中位占 {_IO[0]:.0f}%）。' if _IO[0] else '。')),

    ('永续期货',
     'perpetual futures：<b>没有到期日</b>、不按月 / 按季到期换月的期货合约。'
     '本页这一列 ＝ Bitcoin ＋ Ethereum 两只永续期货的合计，'
     + (f'官方从 {_CRYPTO0} 那期起才印这一节' if _CRYPTO0 else '官方近年才新增这一节')
     + '（左边那一大段空白是产品还没上线，<b>不是 0</b>）。'
       '⚠️ 它<b>不计入</b>「商品合计」—— 官方的 Commodities 定义里没有加密，'
       '页尾口径说明里有逐项对账。'),

    ('上市家数 / 募资额',
     '发行那一组的几行<b>分母互不相同</b>：「当月新上市家数」＝ Mainboard ＋ Catalist 的 '
     'IPO 家数，<b>不含</b> RTO（借壳上市，官方单列一行）；而「IPO / RTO 募资额」'
     '<b>含</b> RTO，且官方脚注写明不含超额配售权（若行使）。'
     '⇒ 两行相除得不到「平均每家募到多少」'
     + (f' —— 实测有 {_RTO} 个月家数是 0、募资额却大于 0（那几个月只有 RTO）'
        if _RTO else '')
     + '。「当月退市家数」同样只数 Mainboard ＋ Catalist。'),

    ('加权平均成交价',
     '<b>不是公司披露的数</b>，是量价分解那张图里本页自己轧出来的派生量：'
     '<code>当月成交额 ÷ 当月成交股数</code>（S$/股'
     + (f'，全期实测 {_PR[0]:.2f}–{_PR[1]:.2f}' if _PR[0] else '')
     + '）。它同时含两件事：市场本身的涨跌，以及<b>成交结构变化</b>'
       '（单价高的标的成交占比上升，即使每只票都没涨，这个数也会被抬高）。'
       '⇒ 它<b>不是</b>股价指数的收益率，本仓也没有 STI 点位序列可以把两者分开。'),
]


# ══ 2026-09-12 改版的历史账（一条 note 覆盖页面所有者的全部四条指令）══════════════
#: 改版前那一版的图题，**逐字**从改版前最后一次提交的产物取
#: （`git show f334d10:data/sgx.js` 的 `exhibits[].title`，2026-09-12 动手之前的 HEAD）。
#: 冻结的历史事实，**一个字都不许跟着底座改**：它们的全部用处是让手里还留着上一版的
#: 读者按题对上号，并让 `_note_2609_12` 逐张核「这一版里哪张还在、排到了哪」。
_OLD_TITLES = {
    2: '证券市场 SDAV：全历史与近 3 年分位带',
    3: '衍生品 DDAV：全历史与近 3 年分位带',
    4: '证券市场 SDAV：单月同比',
    5: '衍生品 DDAV：单月同比',
    6: '证券市场成交（次轴：单月同比）：日均成交额 SDAV',
    7: '证券市场成交（次轴：单月同比）：当月成交额',
    8: '证券市场成交（次轴：单月同比）：当月成交股数',
    9: '换手率：整体换手率',
    10: '衍生品日均成交（次轴：单月同比）：日均成交 DDAV',
    11: '衍生品成交与未平仓：当月成交合计 / 其中：期货 / 其中：期权',
    12: '股指期货：与 HKEX / JPX 的头对头：4 条序列对比',
    13: 'GIFT Nifty 50 期货（2023-07 计数口径断点；次轴：单月同比）：GIFT Nifty 50 期货',
    14: 'FTSE 台湾指数期货（2020-07 起；次轴：单月同比）：FTSE 台湾期货',
    15: '外汇期货：3 条序列对比',
    16: '商品与利率：商品合计（不含加密） / 其中：铁矿石 / 利率期货',
    17: '加密货币永续期货（2025-11 起）：BTC / ETH 永续期货',
    18: '发行与上市：当月新上市家数 / 当月退市家数',
    19: '发行与上市：IPO / RTO 募资额 / 债券募资额',
    20: '当月新债券挂牌数（次轴：单月同比）：当月新债券挂牌数',
    21: '证券市场 SDAV：与同月常态比',
    22: '衍生品 DDAV：与同月常态比',
    23: '市值与上市证券数：月末总市值（存量，期末口径）',
    24: '市值与上市证券数：月末上市证券只数（存量，期末口径）',
    25: '衍生品成交与未平仓：月末未平仓（存量，期末口径）',
    26: '证券市场成交额：增长的量价分解（一格 = 一个完整年度，末格 = 当年 YTD）',
}
#: 改版前末尾核对表的号（同一份产物的 `table.n`）。
_OLD_TABLE_N = 27
#: 指令一删掉的四张。
_OLD_DROPPED = (2, 3, 4, 5)
#: 指令二改成「合计柱 + 占比堆叠」的四张 → 接替它的那条 mix 的 total 列名。
#: 按**列名**而不是组名找接替者：组名本轮就改了一个（商品与利率 → 商品；
#: 中间还短暂叫过「商品（不含加密）」，审稿时改短 —— 「不含加密」留在列名里），
#: 列名是 series/sgx.csv 的表头，改名要动抓取器，稳得多。
_OLD_BLOCKS = {
    11: 'deriv_vol_contracts',
    12: 'vol_equity_index_futures_contracts',
    15: 'vol_fx_futures_contracts',
    16: 'vol_commodities_contracts',
}
_OLD_DERIV_N = 11
_OLD_COMM_N = 16
#: 指令三前移的那张（月末未平仓）。
_OLD_OI_N = 25
#: 从「商品与利率」拆出来单独成组的那一列。
_RATES_COL = 'vol_rates_futures_contracts'
#: 上一版页尾那段 dup_yoy 说明的标题与结尾半句，**逐字**取自同一份产物
#: （生成处是 build/single.py 的 `dup_yoy_zh()`）。引号里只放逐字的原文。
_OLD_DUP_HEAD = '同一条同比出现在不止一张图上'
_OLD_DUP_TAIL = '要不要并成一张由页面所有者定'


class _HistMismatch(SystemExit):
    """本轮历史账与这一版页面对不上。

    继承 SystemExit，与底座的 SpecError 同一种退场：打印原因、退出码 1、
    旧的 data/sgx.js 原地不动。本文件不 import 底座（整份要能删干净），所以自己起一个。
    """


def _shift_zh(k, many=True):
    """相对位移 → 「各前移 N 号」/「号不动」/「各后移 N 号」（`many=False` 去掉「各」）。

    同 build/specs/tmx.py 的同名函数（不 import：别家的 spec 不是本页的依赖）。
    只做一件事：让措辞跟着符号走 —— 手写「前移 / 后移」最容易在某一行写反，
    而写反了页面上不会有任何东西响。
    """
    if k == 0:
        return '号不动'
    ge = '各' if many else ''
    return f'{ge}前移 {-k} 号' if k < 0 else f'{ge}后移 {k} 号'


def _spec_col_zh(col):
    """SPEC 的 groups 里 `col` 那一列的中文名（要恰好声明一次）。"""
    hit = [c['zh'] for g in SPEC['groups'] for c in g['cols'] if c['col'] == col]
    if len(hit) != 1:
        raise _HistMismatch(f'[sgx] 页尾「本轮历史账」：{col} 在 SPEC 的 groups 里声明了 '
                            f'{len(hit)} 次（要恰好 1 次，才拼得出它在图题里的名字）')
    return hit[0]


def _spec_group(pred, what):
    """SPEC 的 groups 里满足 `pred` 的那一组（要恰好一组）。"""
    hit = [g for g in SPEC['groups'] if pred(g)]
    if len(hit) != 1:
        raise _HistMismatch(f'[sgx] 页尾「本轮历史账」：SPEC 里{what}的组有 '
                            f'{len(hit)} 个（要恰好 1 个）')
    return hit[0]


def _note_2609_12(page):
    """页尾那条「2026-09-12 这一轮改了什么」的历史账。**写成 callable。**

    ⚠️ **为什么不整条写死成散文。**本轮四件事描述的都是「这一版页面长什么样」，
    而页面长什么样有一部分是底座每次构建现判的：mix 的合计柱会不会被折叠
    （`Page.total_drawn_wider`）、占比图的窗口够不够 24 个月、`headline_style`
    哪天被人改回去。写死的对照表在那些情形下会指着不存在的图说话，而四道闸门
    一道都不响（同一条教训 build/specs/tmx.py 的 `_note_2609` docstring 记过）。

    所以这里拿冻结的旧图题 `_OLD_TITLES` 与这一版建好之后的 exhibits（底座在
    `notes()` 里挂到 `page._ex` 上）逐张核：
      · 删掉的四张，旧图题必须真的不在；
      · 改成占比堆叠的四张，旧图题必须不在，接替它们的那几张必须**各恰好一张、
        号连续、按声明顺序排**（图题前缀从 SPEC 的组名 / 列名 / split 名现拼，不抄字面量）；
      · 其余每张旧图题必须**恰好出现一次**，位移按新旧号现算；
      · 这一版的每一张图都必须被上面三类认领到 —— 多出一张没交代的图，对照表就不完整；
      · 正文里另外两句断言也现核：月末未平仓紧跟接替原 Exhibit 11 的那几张；
        被 mix 吃掉的分项不再有自己的图。
    任何一条核不上就**抛异常、整页不出**（`_HistMismatch`），不降级成一句含糊的话：
    这条 note 的核心是那张对照表，印一张指错的表比不印更糟。

    ⚠️ 本条里**一个当前图号都不写**（图号由底座按渲染顺序现算）：只用「原 Exhibit N」
    （冻结的改版前编号）与现算的相对位移。同理不含任何当月读数。
    """
    try:
        return _note_2609_12_zh(page)
    except _HistMismatch as e:
        # ⚠️ 退场的异常要**同时是底座自己的 SpecError**：build/test_guards.py 的
        #    TestSgxOwnerLayout 在 setUpClass 里只接 `single.SpecError`，一个裸 SystemExit
        #    会越过 unittest 的 `except Exception`，把整个 preflight 进程带走、一条结果都不留。
        #    本文件不 import 底座（整份要能删干净），所以从调用方 page 所在的模块现取那个类
        #    —— `python3 build/single.py` 下是 `__main__`，测试里是 `single`，两处都认得；
        #    取不到（例如拿一个假 page 单测这条 note）就原样抛 `_HistMismatch`。
        import sys
        se = getattr(sys.modules.get(type(page).__module__), 'SpecError', None)
        if isinstance(se, type) and issubclass(se, SystemExit):
            raise type('_HistMismatch', (se, _HistMismatch), {})(*e.args) from None
        raise


def _note_2609_12_zh(page):
    """`_note_2609_12` 的本体：逐张核对旧→新图号，再拼正文。核不上一律抛 `_HistMismatch`。"""
    ex = getattr(page, '_ex', None)
    if not ex:
        raise _HistMismatch(
            '[sgx] 页尾「本轮历史账」要读建好之后的 exhibits（page._ex），这一次没有拿到 —— '
            '底座的 notes() 应当在调用 spec 的 callable 之前把它挂到 page 上')
    ns = [e.get('n') for e in ex]
    if ns != list(range(2, 2 + len(ex))):
        raise _HistMismatch(
            f'[sgx] 页尾「本轮历史账」：这一版 exhibits 的图号不是从 2 起逐张连续的（{ns}），'
            '按新旧号现算的位移会整张算错')
    titles = [str(e.get('title') or '') for e in ex]

    def _find(test, what):
        hit = [e for e in ex if test(str(e.get('title') or ''))]
        if len(hit) != 1:
            det = '；'.join(f'Exhibit {e.get("n")}「{e.get("title")}」' for e in hit)
            raise _HistMismatch(
                f'[sgx] 页尾「本轮历史账」对不上这一版页面：{what}应当恰好 1 张，'
                f'实际 {len(hit)} 张' + (f'（{det}）' if det else '') + ' —— '
                '这条 note 的核心是一张旧→新图号对照表，核不上就不发页，免得印一张指错的表。'
                '底座改了图题措辞 ⇒ 更新 build/specs/sgx.py 里 `_note_2609_12` 的核对规则；'
                '页面结构又改了一轮 ⇒ 把这条历史账整条换成新一轮的')
        return hit[0]['n']

    # ── 接替者：每条 mix 该出的那几张，按出图顺序 ─────────────────────────────
    blocks = {}
    for o, col in _OLD_BLOCKS.items():
        g = _spec_group(lambda g, col=col: (g.get('mix') or {}).get('total') == col,
                        f' mix.total = {col} ')
        m, gz, tz = g['mix'], g['zh'], _spec_col_zh(col)
        items = [('合计柱', lambda t, p=f'{gz}：{tz} —— ': t.startswith(p))]
        for lb in [m.get('split_zh')] + [a['zh'] for a in (m.get('alt_splits') or [])]:
            p = f'{gz}：{lb or "各分项占比"}（分母 = {tz}'
            items.append((f'「{lb}」' if lb else '100% 占比堆叠',
                          lambda t, p=p: t.startswith(p)))
        blocks[o] = (g, items)
    g_r = _spec_group(lambda g: [c['col'] for c in g['cols']] == [_RATES_COL],
                      f'只声明 {_RATES_COL} 一列')
    blocks[_OLD_COMM_N][1].append(
        (f'拆出来单独成组的「{g_r["zh"]}」柱图',
         lambda t, p=f'{g_r["zh"]}：{g_r["cols"][0]["zh"]}': t == p))

    # ── 逐张旧图核新位置 ─────────────────────────────────────────────────────
    plan, claimed = {}, {}
    for o, t in sorted(_OLD_TITLES.items()):
        if (o in _OLD_DROPPED or o in _OLD_BLOCKS) and t in titles:
            raise _HistMismatch(
                f'[sgx] 页尾「本轮历史账」说原 Exhibit {o}「{t}」'
                + ('已删' if o in _OLD_DROPPED else '已改成占比堆叠')
                + '，这一版页面上却还有这张图 —— 那句话是假的，不发页')
        if o in _OLD_DROPPED:
            plan[o] = ('drop',)
            continue
        if o in _OLD_BLOCKS:
            got = [_find(test, f'接替原 Exhibit {o} 的{name}')
                   for name, test in blocks[o][1]]
            if got != list(range(got[0], got[0] + len(got))):
                raise _HistMismatch(
                    f'[sgx] 页尾「本轮历史账」：接替原 Exhibit {o} 的几张不是按声明顺序'
                    f'逐张连续出的（{got}），「由连续几张接替」那句会是假话')
            for n in got:
                claimed[n] = o
            plan[o] = ('block', got, [name for name, _test in blocks[o][1]])
            continue
        n = _find(lambda x, t=t: x == t, f'原 Exhibit {o}「{t}」')
        if n in claimed:
            raise _HistMismatch(f'[sgx] 页尾「本轮历史账」：Exhibit {n} 被两张旧图同时认领')
        claimed[n] = o
        plan[o] = ('same', n - o)
    left = [f'Exhibit {e.get("n")}「{e.get("title")}」' for e in ex if e.get('n') not in claimed]
    if left:
        raise _HistMismatch(
            '[sgx] 页尾「本轮历史账」：这一版有图没被对照表认领 —— ' + '；'.join(left)
            + ' —— 旧→新对照不完整，不发页')
    oi_new = _OLD_OI_N + plan[_OLD_OI_N][1]
    if oi_new != plan[_OLD_DERIV_N][1][-1] + 1:
        raise _HistMismatch(
            f'[sgx] 页尾「本轮历史账」说月末未平仓（原 Exhibit {_OLD_OI_N}）紧跟接替'
            f'原 Exhibit {_OLD_DERIV_N} 的那几张，这一版却不挨着 —— '
            'groups「衍生品成交与未平仓」的 stock_inline 没有生效？')

    # ── （二）那句「分项不再单独画图」也现核 ──────────────────────────────────
    shown = []
    for o in sorted(_OLD_BLOCKS):
        for p in blocks[o][0]['mix']['parts']:
            zh = _spec_col_zh(p)
            shown.append(zh)
            for e in ex:
                if e.get('kind') == 'stacked_dual':
                    continue
                names = {str(e.get('legend') or '')} | {
                    str(s.get('name') or '') for s in (e.get('series') or [])
                    if isinstance(s, dict)}
                if zh in names or str(e.get('title') or '').endswith('：' + zh):
                    raise _HistMismatch(
                        f'[sgx] 页尾「本轮历史账」说「{zh}」的张数不再单独画图，而 '
                        f'Exhibit {e.get("n")}「{e.get("title")}」画着它 —— 那句话是假的')
    resid = [blocks[o][0]['mix']['residual_zh'] for o in sorted(_OLD_BLOCKS)]
    m11 = blocks[_OLD_DERIV_N][0]['mix']
    alts = m11.get('alt_splits') or []
    if not alts or not m11.get('split_zh'):
        raise _HistMismatch('[sgx] 页尾「本轮历史账」的（四）讲的是「衍生品成交合计的第二种切法」，'
                            'SPEC 里那组 mix 却没有 split_zh / alt_splits')
    g_comm = blocks[_OLD_COMM_N][0]
    tz11 = _spec_col_zh(_OLD_BLOCKS[_OLD_DERIV_N])

    # ── （五）的对照表：连续、同类、同位移的旧号并成一段 ─────────────────────────
    segs, olds, i = [], sorted(_OLD_TITLES), 0
    while i < len(olds):
        o, k = olds[i], plan[olds[i]]
        if k[0] == 'block':
            first = k[1][0] - o
            segs.append(f'原 Exhibit {o} 由连续 {len(k[1])} 张接替（{"、".join(k[2])}），'
                        + ('头一张落在原号上' if first == 0 else
                           f'头一张{_shift_zh(first, many=False)}'))
            i += 1
            continue
        j = i
        while (o != _OLD_OI_N and j + 1 < len(olds) and olds[j + 1] == olds[j] + 1
               and olds[j + 1] != _OLD_OI_N and plan[olds[j + 1]] == k):
            j += 1
        a, b = o, olds[j]
        who = (f'原 Exhibit {a}' if a == b else
               f'原 Exhibit {a} 与原 Exhibit {b}' if b == a + 1 else
               f'原 Exhibit {a} 至原 Exhibit {b}')
        if k[0] == 'drop':
            segs.append(f'{who} 已删')
        elif o == _OLD_OI_N:
            segs.append(f'{who} {_shift_zh(k[1], many=False)}'
                        f'（就是（三）里前移的月末未平仓，紧跟接替原 Exhibit {_OLD_DERIV_N} 的那几张）')
        else:
            segs.append(f'{who} {_shift_zh(k[1], many=(a != b))}')
        i = j + 1

    t = _OLD_TITLES
    return (
        '<b>2026-09-12：本页按页面所有者的四条指令改版 —— 删掉开篇四张、'
        '四张多条折线改成「合计柱 + 100% 占比堆叠」、月末未平仓前移到衍生品成交之后、'
        '新增一张按资产类别的业务占比图。</b>'
        '本条逐项交代改了什么、为什么，以及旧图号对应到哪里。'
        '<b>它是历史账，不随每月新数据变</b>；各图自己的实测数在各图图注里，'
        '这里只点名、不复述。下面的图号对照是构建时拿上一版的图题逐张核出来的，'
        '核不上这一页就不发布。'

        # ── 一、删开篇四张 ─────────────────────────────────────────────────
        + f'（一）<b>删掉开篇四张</b>：原 Exhibit 2 / 3（「{t[2]}」「{t[3]}」）'
          f'与原 Exhibit 4 / 5（「{t[4]}」「{t[5]}」）。'
          '后两张与各自组里那张柱图画的是<b>同一列、同一条单月同比</b>：'
          f'上一版页尾那段「{_OLD_DUP_HEAD}」由构建期逐图比对现算，写明两对横轴逐格相同、'
          f'两条线逐点相等，末尾是「{_OLD_DUP_TAIL}」—— 这一轮所有者定了。'
          '<b>SDAV 与 DDAV 本身一个读数都没丢</b>：两列照旧是本页的头条列，'
          '决定数据月与发布门槛、页顶数据条与汇总表的头条两行，两张季节性图照旧；'
          f'水平值与单月同比画在「{t[6]}」与「{t[10]}」这两张柱图上'
          '（原 Exhibit 6 / 10，新位置见（五））。'
          '随之从页面上消失的是前两张的<b>近 3 年 P10/P90 分位带</b>：'
          '汇总表「3Y %ile」那一列照旧（同一个 <code>build/pctile.py</code>），'
          '只是不再有一张图把带画出来。'

        # ── 二、折线 → 占比堆叠 ───────────────────────────────────────────
        + '（二）<b>四张多条折线改成「合计柱 + 100% 占比堆叠」</b>：'
        + '、'.join(f'原 Exhibit {o}（「{t[o]}」）' for o in sorted(_OLD_BLOCKS)) + '。'
          '旧图把合计与几条分项画在同一根轴上，而分项相加<b>凑不齐</b>合计 —— '
          '上一版的释义为此专门用了三条来交代合计不等于页上那几条之和。'
          '新图把凑不齐的那一块画成每张堆叠最上面那段、并给它起了名字（'
        + '、'.join(f'「{z}」' for z in resid) + '），'
          '各段之和由底座逐月复算，对不上就不发页；那三条释义随之改成交代那一段里装着什么。'
          '<b>换掉的是分项的张数走势</b>：' + '、'.join(f'「{z}」' for z in shown)
        + '不再单独画线，张数只留在汇总表与末尾核对表里，图上读到的是它们<b>占合计的份额</b>。'
          '「利率期货」不是商品合计的分项（官方另起一节），原来与商品挤在同一张折线里，'
          f'这一轮<b>拆成自己一组</b>（「{g_r["zh"]}」）：单列一桶 ⇒ 柱 + 次轴单月同比，'
          f'口径写进组名；原「商品与利率」那组随之改名「{g_comm["zh"]}」。'

        # ── 三、未平仓前移 ────────────────────────────────────────────────
        + f'（三）<b>月末未平仓前移</b>（原 Exhibit {_OLD_OI_N}，「{t[_OLD_OI_N]}」）：'
          f'上一版存量图一律排在两张季节性图之后，它与同组的成交那张之间隔着 '
          f'{_OLD_OI_N - _OLD_DERIV_N - 1} 张图；这一轮按所有者的指令紧跟衍生品成交那几张出，'
          '「成交 → 未平仓」连着读。它仍是<b>单独成图的存量柱</b>'
          '（点对点同比，标题里写着「存量，期末口径」），不与任何流量共轴、也不能与成交相加。'

        # ── 四、新增业务占比图 ────────────────────────────────────────────
        + '（四）<b>新增' + '、'.join(f'「{a["zh"]}」' for a in alts) + '</b>，'
          f'紧跟「{m11["split_zh"]}」那张，分母同样是「{tz11}」—— 同一个合计的第二种切法。'
          '所有者要一张 SGX 的业务占比图，本仓里站得住的指标只有一个：'
          '<b>衍生品当月成交张数按资产类别切</b>（股指期货 / 外汇期货 / 商品 / 其他）。'
          '另外三个都排除了：证券成交额是 S$ 金额，与张数进不了同一个堆叠；'
          '名义额算不出来（本仓没有 SGX 任何一条合约的乘数实测，'
          '<code>series/contract_specs.csv</code> 的 SGX_DERIV 一行、'
          '<code>build/notional.py</code>）；按业务分部的收入是半年报口径，也不在本仓。'
          '<b>两张占比图之间的段不能相加减</b>'
          '（「其中：期货」那一段里就含着股指、外汇与商品三类的期货）；'
          '张数份额 ≠ 金额份额、三段覆盖范围不对称这两件事写在那张图自己的图注里。'

        # ── 五、编号 ──────────────────────────────────────────────────────
        + '（五）<b>编号怎么动。</b>原 Exhibit 1（汇总表）不动；'
        + '；'.join(segs)
        + f'；末尾核对表（原 Exhibit {_OLD_TABLE_N}）'
          f'{_shift_zh(ns[-1] + 1 - _OLD_TABLE_N, many=False)}。'
          '<b>本页每一个图号都是底座按渲染顺序现算的</b>，正文、图注与本条里没有写死'
          '任何一个新号，所以下一次增删同样只会移动号，不会造出一句指错图的话。'
    )


SPEC = {
    'ticker': 'sgx',
    'name': 'Singapore Exchange',
    'title': '新加坡交易所（SGX）月度经营指标',
    'csv': 'sgx.csv',
    'ccy': 'SGD',
    'source': ('Source: SGX Monthly Statistics Report (official PDF, via SGX CMS API); '
               'format after Goldman Sachs GIR'),

    # 头条：证券与衍生品各一条。两者同出一份 PDF、同一天发布，
    # 2015-01 起逐月无洞（写这句时实测 138/138；当期月数见页尾「数据源与口径」那条）。
    # SDAV 是 SGX 自家财报与新闻稿引用最多的单一数字；DDAV 是跨所可比的那条。
    'headline': [
        {'col': 'sdav_sgdmn', 'zh': '证券市场 SDAV',
         'unit': 'S$mn/day', 'fmt': 'f0c'},
        {'col': 'ddav_contracts', 'zh': '衍生品 DDAV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
    ],

    # ── 开篇不出图（页面所有者 2026-09-12 指令一：删掉原 Exhibit 2–5）────────────
    # 上一版开篇四张 = SDAV / DDAV 各一张「全历史折线 + 近 3 年分位带」、各一张「单月同比」。
    # 后两张与「证券市场成交」「衍生品日均成交」两组里那两张柱图是同一列、同一条单月同比、
    # 横轴逐格相同（上一版页尾那段 dup_yoy 说明逐图比对过），所有者定了删；
    # 前两张的分位带随之离开页面，汇总表的「3Y %ile」列不受影响。
    # 'none' 只拿掉开篇图：两条头条列照旧决定数据月 / 发布门槛、页顶数据条、
    # 汇总表头条两行与 ④ 季节性；SDAV / DDAV 的水平值与单月同比只画在各自组里那张柱上。
    # ⚠️ 所以两条头条列必须各在某个 group 里声明过 —— 不然它们在页面上一张图都没有
    #    （底座对此只在构建日志里告警、不停机）。
    'headline_style': 'none',

    'groups': [
        # 三列三个单位 ⇒ 三个单桶 ⇒ 三张 gs_bar，次轴都是**单月同比**（全站唯一口径）。
        # 代价照实说：tools/check_yoy_caliber.py 实测当月成交额 / 成交股数各有 2 / 6
        # 个月与 12 个月滚动口径符号相反（如 2024-07 成交额单月 +23.3% vs 滚动 −3.6%）。
        # 契约要求单月口径写进标题（CONTRACT.md §6）⇒ 口径写进组名。
        # 当月总量两张是**对账视图**（官方月报 At-A-Glance 的原样数字）。
        # SDAV 那张在 2026-09-12 之后是 SDAV 单月同比在本页的唯一一张图（开篇那张已删）。
        # ⚠️ 2026-09 之前页尾另有两张同列的 12 个月滚动同比图回答「一整年在不在长」；
        # 改单月口径后与这里的后两张完全重复，已删（见本文件上方那段说明）。
        {'zh': '证券市场成交（次轴：单月同比）', 'cols': [
            {'col': 'sdav_sgdmn', 'zh': '日均成交额 SDAV',
             'unit': 'S$mn/day', 'fmt': 'f0c'},
            {'col': 'sec_turnover_sgdmn', 'zh': '当月成交额',
             'unit': 'S$mn/month', 'fmt': 'f0c'},
            {'col': 'sec_turnover_mnshares', 'zh': '当月成交股数',
             'unit': 'mn shares/month', 'fmt': 'f0c'},
        ]},

        {'zh': '市值与上市证券数', 'cols': [
            {'col': 'mktcap_sgdmn', 'zh': '月末总市值',
             'unit': 'S$mn', 'fmt': 'f0c', 'stock': True},
            {'col': 'listed_securities', 'zh': '月末上市证券只数',
             'unit': 'listings', 'fmt': 'f0', 'stock': True},
        ]},

        # 与主体同起点（2015-01），但单位是 % —— 与任何一组都不同桶，
        # 合进别的组也只会自己一张图，所以仍旧单列一组。
        # （2026-08 之前这里写「2018-03 起」，是解析边界不是数据边界，见文件抬头。）
        {'zh': '换手率', 'cols': [
            {'col': 'turnover_velocity_pct', 'zh': '整体换手率',
             'unit': '%', 'fmt': 'pct0'},
        ]},

        # DDAV 从「衍生品成交与未平仓」拆出来单独成组，理由与新债券挂牌数那一组同型：
        # 它是原组里唯一的 contracts/day 列，天然单桶 ⇒ gs_bar + 次轴**单月同比**，
        # 而 CONTRACT §6.6 的自动判据要求单月同比写进标题（R4，不写就报 🟡）、
        # ex_single 的标题 = 组名 + 列名
        # ⇒ 只能写进组名。原组的组名不能加那句话：那一组出的图里有**不带同比**的
        # （2026-09-12 起是两张 100% 占比堆叠；之前是三条折线）和**点对点同比**的
        # （月末未平仓那张存量柱），加上去对它们是假话。那一组的合计柱不靠组名 ——
        # 底座给 mix 合计柱的标题里自己就写着「单月同比」。
        # 拆组那一轮没有改图号：contracts/day 桶本来就排在 contracts/month 与存量桶之前
        # （当时改完复跑 single.py 逐图核过）。2026-09-12 这一轮的号怎么动，见页尾历史账。
        # 2026-09-12 起它也是 DDAV 单月同比在本页的唯一一张图（开篇那张已删）。
        {'zh': '衍生品日均成交（次轴：单月同比）', 'cols': [
            {'col': 'ddav_contracts', 'zh': '日均成交 DDAV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
        ]},

        # ── 衍生品成交与未平仓：一个合计、两种切法、紧跟一张存量柱（2026-09-12 改版）──
        # 上一版这一组画的是「当月成交合计 / 其中：期货 / 其中：期权」三条折线，
        # 月末未平仓排在季节性之后。页面所有者 2026-09-12 的指令二、三、四都落在这一组：
        #   · 指令二：三条折线 → `mix`。合计柱（水平值 + 次轴单月同比）+ 100% 占比堆叠。
        #     残差段 = 合计 − 期货 − 期权，本页叫它「掉期」（`_RESID_SWAPS_ZH`）——
        #     它装着掉期 + 官方印刷差，不是 deriv_swaps_vol_contracts 那一列
        #     （差在哪几个月由 `_swaps_gap()` 现算，写在 `_NOTE_SPLIT_DERIV`）。
        #     ⚠️ 不把掉期列当第三个分项：有月份三项相加比合计**多**，底座会按
        #     「分项之和超过合计」硬失败；减出来的那一段逐月非负。
        #     **不给 `rhs_share`**（2026-09-12 审稿后删掉了期权那条右轴线）。判据是所有者已经立过的
        #     判例 —— docs/SINGLE_SPEC.md §1.5 第 5 条：tmx「加拿大现货成交额」那张的 Alpha 段常年
        #     3%–12%，所有者判「在堆叠里量得出来」、删了线。期权这一段与它同一量级：写这句时实测
        #     （2026-08 数据，图窗 Jan-16–Aug-26）1.81%–9.77%，在 0–100 的堆叠里读得出来
        #     （当期区间由底座印在那张图自己的图注里）⇒ 那条线只是同一段换个刻度再画一遍。
        #     `_NOTE_SPLIT_DERIV` 末尾那句「右轴那条线重画的是…」同时删了（那句写死在 share_note 里，
        #     不跟着开关走）。以后要加回来，先证明那一段在堆叠里读不出来 —— §1.5 第 5 条的判据是
        #     「读不读得出来」，不是「有没有人想看它」。build/test_guards.py 的 TestSgxOwnerLayout 守着。
        #   · 指令四：业务占比图 → `alt_splits`，同一个合计的第二种切法（按资产类别）。
        #     底座只画一次合计柱，两张占比堆叠紧挨着、都指回这张合计柱。
        #     为什么选张数而不是现货金额 / 名义额 / 收入，见 `_NOTE_ASSET` 上方那段。
        #     那三列是**跨组引用**（各自在后面的组里声明、各是那一组 mix 的 total），
        #     不算被这一组吃掉 —— 它们自己那组的合计柱照常出。
        #   · 指令三：`stock_inline` → 月末未平仓紧跟本组的流量图出，不再排到 ④ 季节性之后
        #     （仍是单独成图的存量柱，点对点同比）。
        # 期货 / 期权两列被 mix 吃掉，不再单独画；张数留在汇总表与末尾核对表。
        {'zh': '衍生品成交与未平仓', 'cols': [
            {'col': 'deriv_vol_contracts', 'zh': '当月成交合计',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'deriv_futures_vol_contracts', 'zh': '其中：期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'deriv_options_vol_contracts', 'zh': '其中：期权',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'deriv_oi_contracts', 'zh': '月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
         ], 'stock_inline': True, 'mix': {
            'total': 'deriv_vol_contracts',
            'parts': ['deriv_futures_vol_contracts', 'deriv_options_vol_contracts'],
            'residual_zh': _RESID_SWAPS_ZH,
            # 不给 'rhs_share'：期权段在堆叠里读得出来，理由见上方注释（§1.5 第 5 条）。
            # 有第二种切法时主切法必须自己起名（底座：split_zh 与 alt_splits 同给同不给），
            # 不然两张占比图的标题一张叫「各分项占比」、一张叫「按资产类别」，读不出是并列的两切。
            'split_zh': '按期货 / 期权 / 掉期的占比',
            'share_note': _NOTE_SPLIT_DERIV,
            'alt_splits': [{
                'zh': '按资产类别的占比',
                # 顺序 = 自下而上：最大的股指在最下，与「股指期货」那组的堆叠同一条阅读习惯。
                'parts': ['vol_equity_index_futures_contracts',
                          'vol_fx_futures_contracts',
                          'vol_commodities_contracts'],
                'residual_zh': _RESID_DERIV_ASSET_ZH,
                'share_note': _NOTE_ASSET,
            }],
         }},

        # 头对头的两个产品必须在这里被看见（见文件抬头）。
        # 2026-09-12 指令二：四条折线 → `mix`（合计柱 + 100% 占比堆叠）。A50 / 日経225 /
        # MSCI 新加坡各占一段，GIFT Nifty、台湾指数期货（2020-07 之前 MSCI 台湾、之后 FTSE 台湾）
        # 与其它指数合约并进残差段（GIFT Nifty 与 FTSE 台湾本页各有自己的柱图；
        # 残差里装着多少由 `_eqix_share()` 现算、写在 share_note）。
        # 不给 `rhs_share`：底座只许一条右轴线，而这张要读的是 A50 这一段的进退，
        # 它在堆叠里本来就读得出来；要给哪一段加线由页面所有者点名。
        {'zh': '股指期货：与 HKEX / JPX 的头对头', 'cols': [
            {'col': 'vol_equity_index_futures_contracts', 'zh': '股指期货合计',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_a50_futures_contracts', 'zh': 'FTSE 中国 A50 期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_nikkei225_futures_contracts', 'zh': '日経225 期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_msci_singapore_futures_contracts', 'zh': 'MSCI 新加坡期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
         ], 'mix': {
            'total': 'vol_equity_index_futures_contracts',
            'parts': ['vol_a50_futures_contracts', 'vol_nikkei225_futures_contracts',
                      'vol_msci_singapore_futures_contracts'],
            'residual_zh': _RESID_EQIX_ZH,
            'share_note': _NOTE_EQIX,
         }},

        # GIFT Nifty 有 2023-07 的计数口径断点，单列一组便于配断点线。
        # 单桶 ⇒ gs_bar + 次轴**单月同比**，口径写进组名（CONTRACT.md §6）。
        # 这张**特意不换滚动口径**：断点让滚动的污染期比单月长将近一倍
        # （单月只有断点后 12 次比较跨口径，滚动要 23 个月后两窗才都落进新口径），
        # 算术写在页尾口径说明，日期由 _NIFTY_BREAK 推导。
        {'zh': 'GIFT Nifty 50 期货（2023-07 计数口径断点；次轴：单月同比）', 'cols': [
            {'col': 'vol_nifty50_futures_contracts', 'zh': 'GIFT Nifty 50 期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        # 2020-07 起（起点与主体差 66 个月），单独一组。单桶 ⇒ 次轴**单月同比**，
        # 口径写进组名；与滚动口径的分歧实测和「方向以滚动为准」的现算读数
        # 都在页尾口径说明（_GT，从 CSV 现算）。
        {'zh': 'FTSE 台湾指数期货（2020-07 起；次轴：单月同比）', 'cols': [
            {'col': 'vol_ftse_taiwan_futures_contracts', 'zh': 'FTSE 台湾期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        # 2026-09-12 指令二：三条折线 → `mix`。残差段装着本页没有列的其他货币对，与两条单列
        # 同一货币对的其他合约；两类谁大随年代换过（2026-08 期逐行构成见 `_FX_OTHER_2608`，
        # 2021-05 期见 `_FX_2105`；`_fx_share()` 现算两条单列合计占多少，都写在 share_note）。
        {'zh': '外汇期货', 'cols': [
            {'col': 'vol_fx_futures_contracts', 'zh': '外汇期货合计',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_usdcnh_futures_contracts', 'zh': 'USD/CNH 期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_inrusd_futures_contracts', 'zh': 'INR/USD 期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
         ], 'mix': {
            'total': 'vol_fx_futures_contracts',
            'parts': ['vol_usdcnh_futures_contracts', 'vol_inrusd_futures_contracts'],
            'residual_zh': _RESID_FX_ZH,
            'share_note': _NOTE_FX,
         }},

        # 2026-09-12：原「商品与利率」→「商品」，mix = 「其中：铁矿石」这一列 vs 其他商品。
        # （改版初稿叫「商品（不含加密）」，审稿时改短：图题是「组名：列名」，列名里已经带着
        # 「不含加密」，组名再写一遍就是同一句话在一行标题里出现两次。）
        # 残差段叫「其他商品」而不是「铁矿石以外的商品」：铁矿石那一列在 2026-08 期漏收一行
        # 铁矿石合约（Lump Premium），那一行的量正落在残差段里 —— 见 `_IRON_*` 那段与 `_NOTE_COMM`。
        # 利率期货不是商品合计的分项（官方另起一节），进不了这条 mix，拆到下一组。
        # 列名「商品合计（不含加密）」没跟着组名改：汇总表与末尾核对表的行头只印列名、
        # 不印组名，「不含加密」这半句在那两处只能靠列名自己带着。
        {'zh': '商品', 'cols': [
            {'col': 'vol_commodities_contracts', 'zh': '商品合计（不含加密）',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_iron_ore_contracts', 'zh': '其中：铁矿石',
             'unit': 'contracts/month', 'fmt': 'f0c'},
         ], 'mix': {
            'total': 'vol_commodities_contracts',
            'parts': ['vol_iron_ore_contracts'],
            'residual_zh': _RESID_COMM_ZH,
            'share_note': _NOTE_COMM,
         }},

        # 利率期货从「商品与利率」拆出来单独成组（2026-09-12）。理由与 DDAV、新债券挂牌数
        # 两次拆组同型，外加一条这一轮才有的：
        #   · 它不是商品合计的分项，进不了上一组的 mix；
        #   · 留在上一组会落进单列桶走 ex_single，图题 = 组名 + 列名 =
        #     「商品：利率期货」—— 组名把它说成了商品，
        #     而且标题里没有单月同比（CONTRACT §6.1 第 1 条，check_yoy_caliber R4 报 🟡）。
        # ⇒ 单独一组，口径写进组名。与主体同起点（2015-01），不另标起点。
        {'zh': '利率期货（次轴：单月同比）', 'cols': [
            {'col': 'vol_rates_futures_contracts', 'zh': '利率期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        # 2025-11 才上线，单独一组。
        {'zh': '加密货币永续期货（2025-11 起）', 'cols': [
            {'col': 'vol_crypto_contracts', 'zh': 'BTC / ETH 永续期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        {'zh': '发行与上市', 'cols': [
            {'col': 'ipos_count', 'zh': '当月新上市家数',
             'unit': 'companies', 'fmt': 'f0'},
            {'col': 'delistings_count', 'zh': '当月退市家数',
             'unit': 'companies', 'fmt': 'f0'},
            {'col': 'ipo_funds_sgdmn', 'zh': 'IPO / RTO 募资额',
             'unit': 'S$mn', 'fmt': 'f0c'},
            {'col': 'bond_funds_sgdmn', 'zh': '债券募资额',
             'unit': 'S$mn', 'fmt': 'f0c'},
        ]},

        # 新债券挂牌数从「发行与上市」拆出来单独成组：它是原组里唯一的
        # listings/month 列，天然单桶 ⇒ gs_bar + 次轴**单月同比**，契约要求单月
        # 口径写进标题（CONTRACT.md §6），而 ex_single 的标题 = 组名 + 列名
        # ⇒ 口径写进组名。拆组不改图号：原组的 companies / S$mn 两桶在前、
        # listings 桶在后，与拆之前的出图顺序逐张一致。
        {'zh': '当月新债券挂牌数（次轴：单月同比）', 'cols': [
            {'col': 'new_bond_listings', 'zh': '当月新债券挂牌数',
             'unit': 'listings', 'fmt': 'f0'},
        ]},
    ],

    # 本页所有列出自同一份月报 PDF，同一天发布 —— 没有慢腿。
    'slow_cols': [],

    'breaks': _breaks(),

    # ── 量价分解：成交额 ≡ 成交股数 × 加权平均成交价 ──────────────────────
    # SGX 有真正「金额 × 股数」同口径的一对，所以这张走 kind='share_price'。
    # ⚠️ **别在这里写「build/specs/ 里有几家、哪几家也有 decomp」** —— 那句话已经错过两轮：
    # 先是「八家里唯一的一家」（自己带着反例「TMX / MIAX 也有」，还漏了 jpx），
    # 后是「10 家里 4 家 share_price」（当天是对的，但目录里加一个 spec 就少一个）。
    # 本文件管不到别家，写在这里的任何家数都只能靠人肉维护。要看当期实况就现跑：
    #   for f in build/specs/*.py; do python3 -c "import importlib.util as u,sys; \
    #     s=u.spec_from_file_location('m','$f'); m=u.module_from_spec(s); \
    #     s.loader.exec_module(m); \
    #     print('$f', [d.get('kind') for d in (m.SPEC.get('decomp') or [])])"; done
    # 口径核查见文件抬头「量价分解的口径核查」一节 —— 那四条证据是这张图成立的全部前提。
    'decomp': [{
        'zh': '证券市场成交额',
        # 派生量是**成交量加权平均成交价**，不是每笔均额、也不是费率。
        # 底座据 kind 生成「它不是什么」那段话，spec 不许自己改措辞。
        'kind': 'share_price',
        # 两列本身就是当月合计（月报 p2 At-A-Glance 的相邻两行），不是日均。
        # ⇒ 不给 weight_col：声明 monthly_total 又给 weight_col 是硬失败，
        #   而且真乘上去会把年度合计放大二十几倍，图形却照常画得出来。
        'granularity': 'monthly_total',
        'value': {'col': 'sec_turnover_sgdmn', 'zh': '当月成交额',
                  'unit': 'S$mn/month', 'fmt': 'f0c'},
        'qty': {'col': 'sec_turnover_mnshares', 'zh': '当月成交股数',
                'unit': 'mn shares/month', 'fmt': 'f0c'},
        # 价 = 金额 ÷ 数量，由底座算。**不许另找一列冒充价** —— series/sgx.csv 里
        # 没有任何一列是成交价，turnover_velocity_pct 是换手率、不是价。
        # S$百万 ÷ 百万股 = S$/股，两边的 1e6 自己抵掉 ⇒ price_scale 用缺省 1.0。
        'price_zh': '加权平均成交价',
        'price_unit': 'S$/share',
        'price_fmt': 'f3',          # 实测区间 0.44–1.49，f2 在低位只剩两位有效数字
        # ━━ 图已按用户指令（2026-08-07）改**日历年**，FY 对账基准见本注释 ━━
        # 改日历年的理由：四家分解图统一 Jan–Dec、4 根完整年柱 + 1 根当年 YTD，
        # 跨页可比；「用日历年会丢掉 2026 上半年」的旧顾虑由 YTD 桶补上
        # （底座自动追加，两侧月份对齐去年同期）。
        # 原财年选择的**对账证据保留如下**（它仍是「月度序列可安全聚合成年度块」的
        # 证明，与横轴用哪种年无关，详见文件抬头口径核查第 4 条）：
        #   · SGX 财年 = Jul–Jun，按**结束**年命名（FY2026 = 2025-07…2026-06）；
        #     财年制下这里曾写 'year_start_month': 7, 'year_label': 'end', 'years': 10。
        #   · 用月度序列自己滚 FY2026（Jul-25–Jun-26）得 455,679 S$mn，
        #     官方报告 p3 的 FYTD = 455,677、新闻稿写 "S$455.7 billion" ——
        #     差 2（12 个整数月度值的舍入），相对差 0.0004%；
        #     衍生品 FYTD 更是逐位相同（363,489,920）。
        #   · docs/SINGLE_SPEC.md 的回归基准仍按财年配置写（FY2021/FY2025/FY2026
        #     三组读数）——那是**底座**的回归测试口径，拿本 spec 临时改回上面三个
        #     字段即可复现，不影响本页按日历年出图。
        # 日历年下 year_label 只能留空或 'start'（底座对日历年 + 'end' 硬失败）。
        'year_start_month': 1,
        # 4 根完整年柱（数据允许时取最近 4 个）+ 1 根 YTD，同 JPX / TMX / MIAX。
        'years': 4,
    }],

    # 名词释义：排在所有 exhibit 之前。选词的判断与「有意不收哪些词」写在 _GLOSSARY
    # 上面那一段注释里（为什么是这几个词、按「读错会出什么事」分的四类）。
    # 这里不写词数：上一版写着「13 个」而那块注释写着「14 个」，要当期数就现数 len(_GLOSSARY)。
    'glossary': _GLOSSARY,

    # ── 量本身：水平值 + 次轴同比（2026-09 起本页已无 level_yoy，见上面那段）──
    'notes': [
        # ── 本轮的历史账（页面所有者 2026-09-12 的四条指令，一条 note 覆盖全部四件事：
        #    删开篇四张 / 四张折线改占比堆叠 / 未平仓前移 / 新增按资产类别的业务占比图）──
        # 判例第 4 条（asx / cme / cboe / tmx 几轮都照这条办）：删图与重排必须在页面上
        # 向读者交代。读者手里可能还留着上一版的图号，不写明白就只剩「怎么少了四张、
        # 后面的号还全变了」。
        # ⚠️ 本页是声明式 spec 页，**图号由底座按渲染顺序现算** —— 这一条里一个新号都
        #    不许写死，只用「原 Exhibit N」（冻结的上一版编号）与相对位移。
        # ⚠️ 位移本身也**不手算**：整条写成 `callable(page)`，拿冻结的旧图题逐张在这一版
        #    exhibits 里核新位置，核不上就抛异常不发页 —— 理由见 `_note_2609_12` 的 docstring。
        # ⚠️ 排在 spec 条目的**第一条**：spec 里其余条目若按「第几条」互相指就会整体错一位，
        #    所以本文件里指页尾条目一律按标题 / 内容点名，不写第几条。
        _note_2609_12,

        'SGX 的头部衍生品产品全部是离岸挂牌的他国标的。2026-06 实测：'
        'FTSE 中国 A50 期货 11,724,378 张（占当月衍生品总成交 34.2%）、'
        '外汇期货合计 10,268,040 张（29.9%）、'
        # 2026-09-12 审稿后补括号：那一期的铁矿石列漏收 Lump Premium 一行（`_IRON_LUMP_MISSED`），
        # 引列值就要把漏的量与含上之后的读数一起给出，否则与「商品」占比图注当场打架。
        f'铁矿石 {_IRON_COL_2606:,} 张（{_IRON_COL_2606 / _DERIV_2606 * 100:.1f}%；'
        f'这是本仓那一列的值，它 {_IRON_WRAP0} 起漏收 Lump Premium 那一行，这一期漏 '
        f'{_IRON_LUMP_2606:,} 张，含上是 {_IRON_COL_2606 + _IRON_LUMP_2606:,} 张、'
        f'{(_IRON_COL_2606 + _IRON_LUMP_2606) / _DERIV_2606 * 100:.1f}%，见「商品」占比图注）、'
        '日経225 期货 748,048 张（2.2%）。A50 与日経225 分别对着 HKEX 与 JPX 的同标的合约，'
        # 2026-09-12 改写：上一版是「本页把两者单列而不是并进『股指期货合计』」——
        # 那时它们是折线里的两条线；现在是占比堆叠里的两段，并进去的反面是残差段。
        '本页在「股指期货」那张 100% 占比堆叠里把两者各画成一段，'
        f'而不是并进最上面那段「{_RESID_EQIX_ZH}」。',

        'GIFT Nifty 在 2023-07 有计数口径断点。官方报告脚注写明 "For periods prior to '
        'June 2023, volumes are computed based on higher of buy and sell lots"，'
        '之后改为买卖双边合计。**本页不对断点两侧的水平差做任何归因**：'
        'series/sgx.csv 里 2023-06 = 1,696,663 张、2023-07 = 1,330,907 张，'
        '是降不是升，说明同期还有 GIFT Connect 迁移的量在动，'
        '单看这条序列分不出「口径变了」和「份额丢了」。',

        '衍生品的 DDAV 不能用「当月总量 ÷ 交易日数」反推。sec_trading_days 那一行'
        '官方括号里写的是 (Stock Market) / (Securities)，是**证券市场**的交易日；'
        '实测 2026-06 用 34,315,225 ÷ 1,619,444 反推得 21.19 天，而官方写的交易日是 21。'
        '所以本页月总量与日均两条都直接取官方值，谁也不从谁推。',

        '「商品合计」按官方定义**不含加密**。实测口径校验：SICOM 3,895,114 + Energy 493,152 '
        '+ Metal&DryBulk 73,586,973 + Dairy 期货 688,923 + Dairy 期权 104,742 + '
        'Energy Metals 2,640 = 78,771,544 张，恰好等于官方新闻稿的 FY2026 "78.8 million lots"；'
        '把 Crypto 加进去就对不上。所以加密单列一组。',

        '台湾指数敞口在 2020-07 换了授权方：MSCI Taiwan 停发（series/sgx.csv 里该列 '
        '2021-11 之后无值、2021-02 起全是 0、2021-01 还有一个内部空洞），改挂 FTSE Taiwan。'
        '本页只画 FTSE 那条，MSCI 那条不上页面 —— 一条带空洞的归零序列进平滑类图型会画出假线。',

        '证券成交额是暂定数：官方脚注写明月末临近的撤单可能来不及计入、'
        '调整顺延到下个月的报告。fetch/sgx.py 按「已有值永不覆盖、只填空」处理，'
        '差异另记 cache。实测 2026-04/05/06 三期的重叠月 8 个数据点逐位相同，'
        '近月重述不是常态。',

        '本页全部金额为新元。跨币种比较由 build/notional.py 统一换算：'
        '流量（SDAV、成交额、募资额）配月均汇率，存量（月末市值、月末未平仓）配月末汇率。',

        # 2026-09-12 改写：上一版这里写「deriv_swaps_vol_contracts（2026-06 = 7,662 张，
        # 占总量 0.02%）」—— 那时掉期在页面上一点痕迹都没有；现在占比堆叠里有一段叫「掉期」，
        # 不说破就会被当成「这一列上页面了」。
        '未上页面的月频列：sec_trading_days（分母，且是证券市场口径）、'
        'deriv_swaps_vol_contracts（掉期这一列本身不声明 —— '
        f'「衍生品成交与未平仓」那张按期货 / 期权 / 掉期切的占比堆叠里那段「{_RESID_SWAPS_ZH}」'
        '是合计减期货、期权减出来的，含官方印刷差，不是这一列；两者差在哪几个月写在那张图的图注里）、'
        'vol_msci_taiwan_futures_contracts（已停发的死列，见上）。',

        # 逐图的一句话交代（2026-09 之前这是 §6.1 第 2 条要的「用单月必须说明为什么」；
        # 全站统一成单月之后那条要求整个消失，新 §6.1 第 3 条要的是**代价**，
        # 所以下面这条注的重心从「为什么用单月」挪到了「这几张单月线各自有多毛刺」）。
        # 逐图的口径分类由底座的「同比口径」自动条目从 yoy_log 现算点名，本条只补
        # 底座给不出的那半。分歧数字全部现算
        # （_GT / _GB / _madd），没有一个写死的数据数字。
        #
        # ⚠️ **本条一律按图的标题点名，不写 Exhibit 号。**
        # 图号是分组顺序的函数：往中间插一组，后面所有图号整体位移，而这条注不会跟着动。
        # 上一版这里写死了 6、7、8、13、14、20 —— 底座那条自动条目现算出来是
        # 4、5、6、7、8、10、13、14、20，两处当场对不上（漏的那张 DDAV 当时既没有理由、
        # 组名里也没有单月声明）。这一轮把 DDAV 拆成自己一组、并把漏掉的几张补进下面，
        # 同时把图号换成标题：标题印在图上，读者按名字找得到，而且不会因为加一组图就失效。
        # 加图 / 拆组之后仍请重跑 single.py，拿页面上那条自动条目逐张对一遍**有没有漏**
        # （对号靠的是图名，不是图号）。
        # 2026-09-12 这一轮：开篇两张头条同比图删了（原来那句「头条同比图 … 是页顶数据条
        # 与汇总表 y/y 列的图形版」随之删掉）；四组 mix 的合计柱与「利率期货」那张是
        # 新出现的单月同比图，补在下面；「跨年趋势请回到那张当月合计的折线图上看」
        # 改指合计柱（折线没了）；FTSE 台湾那句的「GIFT、A50 那两条线」改成现在的图形。
        '<b>单月口径为什么保留（逐图的口径分类以上文「同比口径」那条为准，'
        '它由底座从口径账本现算；本条补的是「为什么」）。</b>'
        '逐张交代 —— <b>按图的标题点名，不写 Exhibit 号</b>'
        '（图号会随分组增删整体位移，标题不会）：'
        '<b>「证券市场成交」那一组的三张</b>（日均成交额 SDAV / 当月成交额 / 当月成交股数）'
        '画的是官方月报 At-A-Glance 的<b>原样数字</b>（SDAV 是日均，后两条是当月总量），'
        '本页拿它与官方披露逐格对账，单月同比与柱逐月对得上。'
        'SDAV 那张同时是页顶数据条第一格的图形版 —— 开篇那张「证券市场 SDAV：单月同比」'
        '2026-09-12 已删（与这张次轴上的金线是同一条序列，见本轮历史账），'
        'SDAV 的单月同比现在只画在这张图上。'
        '⚠️ <b>页尾原来还有两张同列的 12 个月滚动同比图（当月成交额、当月成交股数），'
        '2026-09 已删</b> —— 改单月口径之后它们与这一组的后两张完全重复。'
        '<b>「衍生品日均成交」那张（DDAV）</b>与 SDAV 那张同型：'
        '官方月报 At-A-Glance 印的日均数，与页顶数据条第二格同一条序列、同一个读数'
        '（开篇那张「衍生品 DDAV：单月同比」同一天删掉，理由相同）。'
        '跨年的规模请看「衍生品成交与未平仓」那张当月成交合计的柱（月总量，不是日均）。'
        '<b>「衍生品成交与未平仓」「股指期货」「外汇期货」「商品」四组的合计柱，'
        '以及「利率期货」那张</b>：2026-09-12 由多条折线改出来（见本轮历史账）。'
        '合计的<b>规模</b>要有一张柱来交代（结构交给紧跟着的占比堆叠），'
        '柱旁的次轴走全站统一的单月同比，与本页其余柱图同一把尺子；'
        '各张的毛刺代价由底座印在各自的图注里，本条不复述。'
        f'<b>「GIFT Nifty 50 期货」那张</b>：{_NIFTY_BREAK} 有计数口径断点'
        f'（"买卖孰高" 改成买卖双边合计）。单月口径在这里反而是较干净的一侧 —— '
        f'跨断点的比较只有 {_NIFTY_BREAK} 至 {_madd(_NIFTY_BREAK, 11)} 这 12 个月，'
        f'而 12 个月滚动合计要到 {_madd(_NIFTY_BREAK, 23)} 起两个窗口才都落进新口径，'
        f'污染期长将近一倍。'
        + (f'<b>「FTSE 台湾指数期货」那张</b>：本页把它与「GIFT Nifty 50 期货」那张、'
           f'以及「股指期货」占比堆叠里 A50 那一段对照着读，读的是逐月的竞争动态。'
           f'⚠️ 单月口径毛刺大 —— 全期实测有 {_GT[1]} 个月'
           f'（{_GT[0]} 个可比月；不设死区、贴零的正负也算是 {_GT[7]} 个月）'
           f'与 12 个月滚动口径符号相反，分歧最大的 {_GT[2]} '
           f'单月 {_GT[3]:+.1f}% vs 滚动 {_GT[4]:+.1f}%；'
           f'对照读数：{_GT[5]} 的滚动同比 {_GT[6]:+.1f}%（现算，页上不画）。'
           if _GT[0] else
           '<b>「FTSE 台湾指数期货」那张</b>：与同页「GIFT Nifty 50 期货」那张、'
           '「股指期货」占比堆叠里 A50 那一段对照着读，读的是逐月的竞争动态。')
        + (f'<b>「当月新债券挂牌数」那张</b>：逐月的发行事件计数，单月同比天生毛刺最大 —— '
           f'全期实测与滚动口径符号相反 {_GB[1]} 个月（{_GB[0]} 个可比月；'
           f'不设死区、贴零的正负也算是 {_GB[7]} 个月）；'
           f'对照读数：{_GB[5]} 的滚动同比 {_GB[6]:+.1f}%（现算，页上不画）。'
           if _GB[0] else
           '<b>「当月新债券挂牌数」那张</b>：逐月的发行事件计数，单月同比毛刺最大。')
        + '<b>这两处的滚动读数只作对照、页上一张滚动图都没有</b>'
          '（全站单月口径，页面所有者指定）—— 引在这里是为了让读者知道'
          '自己在读的这条线有多毛刺，不是让人拿它去改结论。'
          '「符号相反」的统计与 tools/check_yoy_caliber.py 同一条死区：'
          '两侧 |同比| ≥ 0.5pp 才计；括号里「不设死区」的那个数是同一个样本的另一种计法，'
          '两者差的正是贴零的那几个月 —— 两个数说的是同一件事，不是两处算得不一样。',
    ],
}
