# -*- coding: utf-8 -*-
"""联华电子（UMC，2303.TW / NYSE: UMC）月度营收页配置 —— TSM 图列底座 `mrbase.py` 侧。

放置位置：`build/mrspecs/umc.py`（与 `build/mrspecs/tsm.py` 并列）。
配套薄壳：`build/umc.py`（见同目录 shell_umc.py）。

━━ 本文件里每一条口径事实的一手出处 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
下面的事实**不是从 build/specs/umc.py（已删除，只在 git 历史里）抄来的**，
是本轮逐条回到 SEC EDGAR
（CIK 1033767，data.sec.gov / www.sec.gov/Archives，带申明用途 UA）核过的。
与仓库现有描述不一致的两处，在对应的 `_*_NOTE` 里点了名（见 ② 与 ⑤）。

  ① **月营收公告的官方单位是 NT$ 千元，不是 NT$ 百万。**
     2026-08-06 那份 6-K 的 Exhibit 99.1 原文（逐字）：
       "1) Sales volume (NT$ Thousand)
        Period Items 2026 2025 Changes %
        July      Net sales 23,844,045 20,040,049 3,803,996 18.98%
        Year-to-Date Net sales 153,614,609 136,656,663 16,957,946 12.41%"
     ⇒ `value.raw_label` 必须把这件事说出来。核对表的标题是「官方原始单位，未换算」，
       若把 NT$mn 舍到 0 位小数印成 23,844，那三位小数**恰好就是官方公告的千元位**，
       等于一边宣称未换算一边丢掉三位官方数字。故 `raw_dec = 3`（无损）。

  ② **公告带 y/y 百分比列（"Changes %"），但本序列没有落库这一列。**
     四份不同年份的公告（2013-01 / 2013-11 / 2016-05 / 2026-07）都有这一列。
     `series/umc.csv` 只有 month / revenue_ntd_mn / revenue_ytd_ntd_mn 三列，
     所以本 spec **不能**给 `official_yoy`（给了会在 DataSet 加载期硬失败）。
     ⚠️ 后果要说清楚：底座在 `official_yoy` 缺席时会印一句
        「该家的月度公告不带 y/y 列」——**这句话对联电是错的**。
        底座那句是**通用退路**，它说的其实是「本 spec 没给 official_yoy」，
        只是措辞替公司下了断言 —— 这不是 UMC 一家的问题，改它要连着「怎么表达
        『有这一列但没落库』」一起改，属于底座 schema 的事（⑧ 那两处是纯 bug，
        改了对任何一家的产出都不会变义，所以本轮顺手修了；这一处不是）。
        ⇒ 由本 spec 在页尾用 `_YOY_SRC_NOTE` 点名纠正（notes 追加在底座各条之后）。
     不落库这一列**是对的选择**，理由见 ③：公告的「去年同期」栏印的是**重述后**的
     比较数，那个数不在本库里；把公告的 % 落库等于让页上出现一个页内任何两格
     都乘不出来的同比。

  ③ **口径连续起点 2013-01，且 2012 不入库。**
     2013-01-25 报送的 6-K（2012-12 营收）逐字：
       "December Invoice amount 6,028,844 ... December Net sales 7,796,821
        2012 Net sales 105,998,159 105,879,723 118,436 0.11 %"
       （注意 2012 及以前那批公告还同时印 Invoice amount 与 Net sales 两行，
        2013 起只剩 Net sales —— 版式本身就换过。）
     2014-01-28 报送的 6-K（2013-12 营收）逐字：
       "December Net sales 9,905,479 8,711,595 1,193,884 13.70 %
        2013 Net sales 123,811,636 115,674,763 8,136,873 7.03 %"
     ⇒ 2012 全年**当年公告口径** 105,998,159 千元，而 2013 年公告里印的
       2012 比较数是 115,674,763 千元，差 9,676,604 千元。
     ⚠️ **纠正一处仓库现有描述**：`fetch/umc.py` 的口径坑 1 写着「公司在 2013 年那
       12 份公告里印出来的同比是『合并数 ÷ 旧口径数』…= +16.81%」。**不是**。
       公司自己印的是 +7.03%（= 除以重述后的 115,674,763），它没有踩这个坑。
       +16.81% 是**我们**把 2012 按当年公告值入库之后会算出来的数 —— 坑在库里，
       不在公告里。本 spec 的 `_START_NOTE` 按这个更严的版本写。

  ④ **月营收 = 合并数**（不是母公司数），可加总，逐季逐年对得上：
     季报 6-K 的分部附注「Wafer Fabrication + New Business = Consolidated」：
       2014Q2  32,547,453 + 3,321,898 = 35,869,351  ← 本表 4+5+6 月 = 35,869.351 ✓
       2015Q2  36,513,180 + 1,498,374 = 38,011,554  ← 本表 4+5+6 月 = 38,011.554 ✓
       1H2014  61,244,176 + 6,318,760 = 67,562,936  ← 本表 1–6 月 = 67,562.936 ✓
       1H2015  72,490,733 + 3,170,465 = 75,661,198  ← 本表 1–6 月 = 75,661.198 ✓
     年度：SEC XBRL companyfacts 的 `ifrs-full:Revenue`(TWD) 2015–2024 十年，
     加 FY2013/FY2014 20-F 正文与 FY2025 20-F 正文，共 13 个完整年度 —— 见 `_ADDITIVE_NOTE`
     （逐年 diff 在**构建期现算**，不写死）。
     ⇒ `value.summable = True` 有实测撑着，季度桥 / YTD / TTM 同比在本页全部合法。

  ⑤ **没有<u>美元营收腿</u>（Ex5/Ex6）—— 注意这一条<u>不</u>等于「没有汇率线」，
     两者本轮已拆开，见 ⑤b / ⑤c。** 这一条本轮拿到了比「便利折算」更硬的两句原文。
     FY2025 20-F（2026-04-30 报送）附注 4(7) 逐字：
       "Translations of amounts from NTD into U.S. dollars (USD) for the reader's
        convenience were calculated at the rate of USD 1.00 to NTD 31.37 on
        December 31, 2025 released by Board of Governors of the Federal Reserve
        System. No representation…"
     ⇒ 20-F 那列美元是**按 12/31 单一即期牌价**整列折的（不是全年均价、更不是逐月）。
       XBRL 里 8 个年度的 TWD/USD 商逐年验证了这一点，全是干净的年末牌价：
       2017 29.64 / 2018 30.61 / 2019 29.91 / 2020 28.08 / 2021 27.74 /
       2022 30.73 / 2023 30.62 / 2024 32.79。
       （仓库现有描述写作「全年一个汇率整列除下来」，方向对但不够准：是**年末**牌价。）
     同一份 20-F「Foreign Currency Risk」一节逐字：
       "Although the majority of our transactions are in NT dollars, some
        transactions are based in other currencies."
     ⚠️ **这句话讲的是 transactions（交易笔数/结算币别），不是 revenue（营收计价币别），
       不能拿它去与 TSMC「约七成营收以美元计价」对举说「正好相反」** —— 晶圆厂完全
       可以用美元开票，同时多数交易笔数（本地薪资、资本支出、供应商付款）以新台币结算，
       两者不互斥。本轮审计判定这条推理不成立，故删。

  ⑤b **营收计价币别：公司自己有一句直说的，本轮补上（本页 `fx` 因此不再留空）。**
     同一份 FY2025 20-F 的 Item 3.D「Risk Factors」，风险因子标题
     "Currency fluctuations could increase our costs relative to our revenues,
      which could adversely affect our profitability" 项下逐字：
       "More than half of our operating revenues are denominated in currencies
        other than New Taiwan dollars, primarily in U.S. dollars. On the other
        hand, more than half of our costs of direct labor, raw materials and
        overhead are incurred in New Taiwan dollars."
     出处（本轮实抓核对，不是照抄）：
       https://www.sec.gov/Archives/edgar/data/1033767/000119312526193757/d91630d20f.htm
     同一句在 FY2023（d448612d20f.htm）与 FY2024（d846836d20f.htm）两份 20-F 里
     **逐字相同**，是公司的常设表述，不是某一年的偶然措辞。
     ⚠️ 公司**只给这句定性表述、不给百分比** —— 页上因此不许出现任何「联电 X% 营收
       以美元计价」的数字。底座 `validate()` 里针对 `SPEC[fx].usd_share_note.src`
       的那段校验明写了这条退路（按符号 grep；上一版写的 `mrbase.py:380-385` 本轮
       复核已指偏 —— 那几行是 `_VALUE` / `_ALT` 的字段集合，不是 `validate()`）：
       给不出可核的百分比就把措辞改成不带数字的定性版本。本页走的正是这一支。
     ⇒ 这句话解释的是「为什么这条汇率线该画」（本币计价的报表被一条外币汇率推着走），
       它**不能**解释「美元营收线该画」—— 那需要官方月度美元实绩，联电没有。

  ⑤c **两件事拆开：汇率线（Ex8）画，美元营收腿（Ex5/Ex6）不画。**
     Ex8 画的是 `ds.fx` 本身 —— 一条宏观序列，挂同一份 `series/tsm_fx.csv` 的每一页上
     逐点相同，不需要联电披露任何东西；本轮之前它是被底座和 Ex5/Ex6 捆在一起跳掉的
     （旧 `mrbase.py:1076` 那一行把「有没有 fx 序列」与「该不该画美元腿」混在一起），
     底座本轮已按 §1.5 拆成两个判据，本 spec 于是改成 `fx` 照给 +
     `skip: ['fx_lines', 'fx_contrib']`（逐条理由见 `_SKIP_FX_LINES` / `_SKIP_FX_CONTRIB`）。
     Ex5/Ex6 不画的理由**只有一条**：联电不按月披露美元营收，20-F 里那一列是年末牌价的
     convenience translation（2024 用 32.79），拿它或外部牌价折出来的美元线没有任何
     官方月度数可以对账 —— 与 ⑤b 那句自述不矛盾：**「多数营收以美元计价」是真的，
     「公司按月公布过美元营收」是假的**，能画的只有前者对应的那条汇率线。
     数据前提也在本轮才成立：`series/tsm_fx.csv` 原先自 2016-01 起，而本页序列自
     2013-01 起，底座对汇率缺月是硬失败（`mrbase.DataSet.__init__` 里那句
     `SpecError('series/… 缺月份 …')`，按这句 grep，**不写行号**：
     上一版的 `mrbase.py:700` 本轮复核已指偏）；该文件本轮已回补到 2013-01，
     与本页营收逐月对齐（⚠️ 不写「共 N 个月」：那个数每月都长一格，写死下个月就错）。
     对齐与否不靠本文件断言，底座自己会查。

  ⑥ **分部只按季披露，且 FY2025 起只剩一个分部。**
     FY2025 20-F 附注 12 逐字："The Company only has wafer fabrication operating
     segment as the single reporting segment."
     月度公告从来只有一个数（Net sales），分部拆分只出现在季报/年报。
     ⇒ `segments` 留空；这不是「懒得填」，是月度粒度上不存在这个字段。

  ⑦ **没有指引桥。** 联电法说会给的是下一季 wafer shipments 环比、ASP（美元）环比、
     毛利率与产能利用率，**不给营收区间**（对照 TSMC 每季给美元营收区间 + 假设汇率）。
     ⇒ 不给 `guidance` / `brief_extra`，底座第 5 句自动退回「三月均值同比 vs 单月同比」。

━━ 本页撞出来的两处底座缺陷（本轮已在 `mrbase.py` 里修掉，各一行）━━━━━━━━━━
  ⑧ `build_exhibits()` 对热力矩阵走 `push('heat', d, ALL)`，而 `push()` 一律调
     `apply_breaks()` ⇒ heat_matrix 的 payload 被塞进 `break_at`/`break_label`，
     图注末尾也被追加「本图上的红色竖虚线是口径断点…」；而 `assets/charts.js` 的绘图
     入口对 heat_matrix **提前 return**（转 drawHeat），那两条线一根也画不出来。
     同一段图注于是前后打架，页尾「口径断点与截轴」还会把热力矩阵列进「已画成红色
     竖虚线」的名单，紧接着声称「本页不会出现『图注说画了断点线、图上其实没有』这种
     自相矛盾」。**本轮之前没人撞到，是因为底座只迁了 TSM，而 TSM 的 `breaks` 是空的
     —— 这段代码一次都没执行过。联电是第一家带断点上底座的页。**
     ⇒ 本轮已在底座修掉（两道：heat 那一路不再走 `push()`，`apply_breaks()` 本身
     也对 `kind == 'heat_matrix'` 直接 no-op）。这是本批次几家（联电 / 联发科 /
     日月光 / 南亚科）共同撞出来的同一处，谁先到谁修。
     修在底座而不是在页尾写一条「上面那句话是错的」——**一条自我否定的图注仍然是
     一个自相矛盾的页面**；而这两处对 TSM 的产出逐字节无影响（TSM 无断点）。
  ⑧b `_window_note()` 里「本页把 Ex2–Ex6 的时间轴统一拉到 …」的 `Ex2–Ex6` 是写死的。
     对 TSM 成立（短窗口图正好五张），对本页不成立：本页短窗口图只有 Ex2–Ex4，
     其后各图（全历史 / 汇率线 / 热力矩阵）都是全序列，而同一句话后面自己列出的恰恰
     只有 Exhibit 2/3/4。⇒ 本轮已在底座改成按实际入列的图现算首尾编号
     （`_window_note()`，对 TSM 仍渲染成 Ex2–Ex6）。

  ⑨ `tools/visual_qa.py --page umc` 在两个视口各报 1 条 🟡 TEXT_OVERLAP（🔴 0）：
     Ex3 末柱的柱顶标签「24」压到右轴 y/y 的点标签「17%」（本轮实测 1280px 44.5px²／
     占小者 35%，768px 29.4px²／31%）。**不是窗口选择造成的，也不写进页面** ——
     反事实做过三遍（两份独立配置各一遍 + 整合时复跑一遍），结论一致：
       · 把本配置的 x_from 换成 None（55 季）重跑 visual_qa：仍是 🔴0/🟡2，
         1280px 逐字相同（44.5px²／35%），768px 是 20.6px²／21%
         ⇒ 缺陷与季度个数、与窗口起点都无关，只有量级随版面高度微动；
       · 把序列截到 2026-06（末季满 3 个月）或 2026-05（末季 2 个月）：🟡 0
         ⇒ 是「末季只有 1 个月、残柱只有满季约三分之一高」这一个形状造成的，
           下个月柱一长就自己消失。
     根因在引擎：`qtr_bar` 的柱顶标签与右轴点标签之间没有互避流程。
     真要修在 charts.js，不在本 spec。一个下个月自己消失的 44px² 重叠不该写成永久图注。

━━ 窗口：`x_from = '2016-01'`（本轮任务书口径）━━━━━━━━━━━━━━━━━━━━━━━━
短窗口图（Ex2 月营收柱 / Ex3 季度桥 / Ex4 环比）统一自 2016 起，**但不得早于本家的
口径连续起点**；联电的口径连续起点是 2013-01（见 `_START_NOTE`），2016-01 晚于它，
所以这里取 2016-01，不触发「窗口比 2016 更晚 ⇒ 要在图注写明这是数据边界」那一支。
底座 `validate()` 对漏写 x_from 硬失败，就是为了逼这个决定显式化。

⚠️ 这个起点会**藏起**一件仍在影响画面的事：2015-06 那条断点落在窗口之外，短窗口图上
不会有红线，而窗口内最早那几格派生同比的**分母**仍站在断点左侧。底座只知道「断点月
在不在窗口里」，知道不了「断点在窗口外但影子还在窗口里」——所以由 `_WINDOW_BREAK_NOTE`
现算三个口径各自的「两边都干净」的第一期写进页尾。
副标题里的「覆盖 Jan-13 – … 共 163 个月」说的是**数据覆盖**（真话，全历史图就是 163 点），
每张图**实际**的窗口由底座的 `_window_note` 逐图现算声明，两者不冲突。
"""
import csv
import os

from . import _facts

_CSV = 'umc.csv'
_COL = 'revenue_ntd_mn'
_YTD_COL = 'revenue_ytd_ntd_mn'

# ══════════════════════════════════════════════════════════════════════════════
# 外部对照常量。**只有这些是写死的**，因为它们不在 series/umc.csv 里 —— 它们是
# 官方申报里的另一侧读数，本序列这一侧的每一个数都在下面从 CSV 现算。
# 每条都标出处，改数时必须连出处一起改。
# ══════════════════════════════════════════════════════════════════════════════
# 官方年度合并营业收入（NT$ 千元）。
# 2013/2014：FY2015 20-F 分部附注的 Consolidated 栏（同一份文件内两栏，可比）；
# 2015–2024：data.sec.gov XBRL companyfacts 的 ifrs-full:Revenue（unit TWD，10 个年度）；
# 2025：FY2025 20-F（accession 0001193125-26-193757）正文。
_OFFICIAL_FY = {
    2013: 123_811_636, 2014: 140_012_076, 2015: 144_830_421, 2016: 147_870_124,
    2017: 149_284_706, 2018: 151_252_571, 2019: 148_201_641, 2020: 176_820_914,
    2021: 213_011_018, 2022: 278_705_264, 2023: 222_533_000, 2024: 232_302_584,
    2025: 237_553_199,
}
# 2012 的两个口径（NT$ 千元），两个数都是**公司公告原文**里印出来的：
_FY2012_AS_ANNOUNCED = 105_998_159   # 2013-01-25 报送的 6-K：「2012 Net sales」
_FY2012_RESTATED = 115_674_763       # 2014-01-28 报送的 6-K：2013 那一行的「2012」栏

# 断点月。每条都由一次可指认、可查证的公司行为唯一确定。
_BRK_NEWBIZ = '2015-06'   # Topcell Solar 并入 Motech，2015-06-01 起不再合并
_BRK_USJC = '2019-10'     # MIFS→USJC 100% 并表，交割日 2019-10-01

# 分部对外营收（NT$ 千元）。**按申报文件分组**，不跨文件拼一条时间序列 ——
# FY2016 20-F 把 2014/2015 的分部划分重述过（2015 的 New Business 由 3,685,289
# 改到 3,125,225），跨年报串起来会得到一条不存在的曲线。
_SEG_FY2015_20F = {   # accession 0001193125-16-543756，附注「Net revenue from external customers」
    2013: (116_781_465, 7_030_171),
    2014: (129_448_927, 10_563_149),
    2015: (141_145_132, 3_685_289),
}
_SEG_FY2016_20F = {   # accession 0001193125-17-122107，同一附注
    2014: (129_953_847, 10_058_229),
    2015: (141_705_196, 3_125_225),
    2016: (147_444_265, 425_859),
}
# 晶圆代工分部同比只能取**同一份 20-F 内**的相邻两栏：
_WAFER_YOY = (
    (2015, _SEG_FY2015_20F[2014][0], _SEG_FY2015_20F[2015][0], 'FY2015 20-F'),
    (2016, _SEG_FY2016_20F[2015][0], _SEG_FY2016_20F[2016][0], 'FY2016 20-F'),
)

# 页面窗口起点。允许 None（= 用序列自己的起点）；下面每一处用到它的地方都**先判 None
# 再比大小** —— `str < None` 在 Python 3 是 TypeError，而这里是 import 期，
# 一个 TypeError 能把 `--all` 整批构建炸掉。
_X_FROM = '2016-01'
# 热力矩阵的行数。TSM 图列的基准是 9，本页沿用：矩阵覆盖最近 9 个年度，
# 与本页 2016 起的窗口口径同侧（取 13 会让矩阵回到 2014，比页面窗口还早两年）。
_HEAT_YEARS = 9


# ══════════════════════════════════════════════════════════════════════════════
# 序列侧的每一个数都在 import 期从 series/umc.csv 现算。
# 读不到 / 算不出 → 每个 _NOTE 退回不带数字的定性版本，**不抛异常**
# （spec 是被 import 的，import 期抛异常会把 `--all` 整批打死）。
# ══════════════════════════════════════════════════════════════════════════════
def _series():
    try:
        p = os.path.join(_facts.SERIES, _CSV)
        with open(p, encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
    except Exception:                                            # noqa: BLE001
        return {}
    out = {}
    for r in rows:
        try:
            out[r['month']] = float((r[_COL] or '').strip())
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _shift(month, k):
    y, m = int(month[:4]), int(month[5:7])
    t = y * 12 + m - 1 + k
    return f'{t // 12}-{t % 12 + 1:02d}'


def _fy(s, year):
    """完整年度的月度加总（NT$ 千元）。月份不齐返回 None。"""
    ms = [f'{year}-{m:02d}' for m in range(1, 13)]
    if not all(m in s for m in ms):
        return None
    return sum(s[m] for m in ms) * 1000.0


def _fy_yoy(s, year):
    """本表口径的整年同比（%）。"""
    a, b = _fy(s, year), _fy(s, year - 1)
    return None if not (a and b) else (a / b - 1.0) * 100.0


def _yoy_mean(s, start, n=12):
    """自 start 起 n 个月的**单月**同比均值（%）。样本不齐返回 None。"""
    xs = []
    for k in range(n):
        m = _shift(start, k)
        b = _shift(m, -12)
        if m not in s or b not in s or s[b] <= 0:
            return None
        xs.append((s[m] / s[b] - 1.0) * 100.0)
    return sum(xs) / len(xs)


def _annual_check(s):
    """(核过几年, 最大绝对 diff 千元, 最早年, 最晚年)。"""
    ok, worst, yrs = 0, 0.0, []
    for y, official in sorted(_OFFICIAL_FY.items()):
        got = _fy(s, y)
        if got is None:
            continue
        ok += 1
        yrs.append(y)
        worst = max(worst, abs(got - official))
    return ok, worst, (yrs[0] if yrs else None), (yrs[-1] if yrs else None)


_S = _series()
_MS = sorted(_S)
_M0, _M1, _MN = (_MS[0], _MS[-1], len(_MS)) if _MS else (None, None, 0)
_NYR, _WORST, _Y0, _Y1 = _annual_check(_S)
# 「12 个月相加 vs 公司自己公布的本年累计」——第二条独立的加总证据，
# 与上面那条对的是不同的东西（那条对官方年报，这条对公告自带的累计列）。
_GAPS = _facts.additivity_gap(_CSV, _COL, _YTD_COL)
_GAP_MAX = max(abs(v) for v in _GAPS.values()) if _GAPS else None

# 反例一侧（世芯-KY 3661）也**现算**，不写死。底座 validate() 的报错文案里写死着
# 「+0.378%」，那其实只是**最近一个完整年度**的缺口；逐年跑一遍会看到它在 −0.3% ~
# +0.7% 之间摆动 —— 摆动本身才是「这一列不可加总」的证据，一个定值反而像是舍入误差。
# 读不到 series/alchip.csv 就整句退回定性版本（下面 `if _AL_GAPS` 分支）。
_AL_GAPS = _facts.additivity_gap('alchip.csv', 'revenue_ntd_mn', 'ytd_revenue_ntd_mn')
if _AL_GAPS:
    _AL_YRS = sorted(_AL_GAPS)
    _AL_TXT = (f'逐年在 {min(_AL_GAPS.values()):+.2f}% ~ {max(_AL_GAPS.values()):+.2f}% 之间'
               f'摆动（{_AL_YRS[0]}–{_AL_YRS[-1]} 共 {len(_AL_YRS)} 个完整年度，'
               f'最近一个完整年度 {_AL_YRS[-1]} 是 {_AL_GAPS[_AL_YRS[-1]]:+.3f}%）')
else:
    _AL_TXT = '在这一项上对不上'


# ── ① 可加总 ──────────────────────────────────────────────────────────────────
if _NYR and _GAP_MAX is not None:
    _ADDITIVE_NOTE = (
        f'<b>本页的季度聚合、YTD 与 TTM 滚动同比都有实测撑着，不是推定。</b>'
        f'本表 {_M0} 至 {_M1} 共 {_MN} 个月，两条独立的加总证据都在构建期现算：'
        f'（1）<b>{_NYR}</b> 个完整年度（{_Y0}–{_Y1}）的月度加总对官方年度合并营业收入，'
        + ('<b>逐年 diff = 0</b>' if _WORST < 0.5 else f'最大差 {_WORST:,.0f} 千元')
        + '（2013/2014 取自 FY2015 20-F 分部附注的 Consolidated 栏，2015–2024 取自 '
          'SEC XBRL <code>ifrs-full:Revenue</code>，2025 取自 FY2025 20-F 正文）；'
          '（2）同样这些年度的 12 个月相加对<b>公司自己在公告里印的本年累计</b>'
        + (f'，最大相对缺口 {_GAP_MAX:.0e}%（浮点噪音量级）。'
           if _GAP_MAX < 1e-6 else f'，最大相对缺口 {_GAP_MAX:.4f}%。')
        + '第二条不是第一条的重复：它对的是公告自带的累计列，能抓到「逐月折算导致相加'
          '不等于累计」那类问题 —— 同一把尺子量世芯-KY（3661）的新台币列，缺口'
        + _AL_TXT
        + '，因为那家的功能货币不是新台币，各月按各月汇率折算，相加自然不等于'
          '「累计外币 × 累计换算汇率」；<b>会摆动</b>才是判据，一个定值反而像舍入误差。'
          '联电的功能货币与表达货币均为新台币'
          '（FY2025 20-F 附注 4(5)：「The Company’s consolidated financial statements '
          'are presented in New Taiwan Dollars (NTD), which is also the parent company’s '
          'functional currency.」），月营收是原生记账数、不是折算值。'
          '季度一侧另有直接命中：季报 6-K 分部附注的 '
          '「Wafer Fabrication + New Business = Consolidated」栏，'
          '2015Q2 = 36,513,180 + 1,498,374 = 38,011,554 千元，与本表 4/5/6 三个月相加'
          '逐字相等（2014Q2、1H2014、1H2015 同样命中）—— 这同时证明月营收是<b>合并数</b>，'
          '不是母公司数。')
else:
    _ADDITIVE_NOTE = (
        '<b>本页的季度聚合、YTD 与 TTM 滚动同比都是合法的。</b>联电的功能货币与表达货币'
        '均为新台币（FY2025 20-F 附注 4(5)），月营收是原生记账数、不是折算值，'
        '月度加总与官方年度、季度可对账。（本次未能从 CSV 现算出逐年 diff，'
        '故此处只作定性表述。）')

# ── ② 起点 2013-01，2012 不入库 ───────────────────────────────────────────────
_S2013 = _fy(_S, 2013)
if _S2013:
    _fake = (_S2013 / _FY2012_AS_ANNOUNCED - 1.0) * 100.0
    _true = (_S2013 / _FY2012_RESTATED - 1.0) * 100.0
    _START_NOTE = (
        f'<b>序列自 {_M0} 起，且 2012 刻意不入库 —— 坑在库里，不在公告里。</b>'
        f'EDGAR 上联电的月营收 6-K 能翻到 2002-02，但 2012 及以前那批公告与 2013 起不是'
        f'同一个东西：2012 年当年那 12 份公告加总 NT${_FY2012_AS_ANNOUNCED:,} 千元'
        f'（那批公告还同时印 Invoice amount 与 Net sales 两行，2013 起只剩 Net sales），'
        f'而 2013 年公告里印的「去年同期」加总是 NT${_FY2012_RESTATED:,} 千元 —— '
        f'后者才是重述后的合并比较数，两者差 '
        f'NT${_FY2012_RESTATED - _FY2012_AS_ANNOUNCED:,} 千元。'
        f'本表 2013 年加总 NT${_S2013:,.0f} 千元：除旧口径基数得 <b>{_fake:+.2f}%</b>，'
        f'除重述后的同口径基数得 <b>{_true:+.2f}%</b>，两者差 {abs(_fake - _true):.1f} 个百分点。'
        f'<b>公司自己印的是后者</b>（2014-01-28 报送的 6-K 逐字：'
        f'「2013 Net sales 123,811,636 115,674,763 8,136,873 7.03 %」）—— 也就是说 '
        f'{_fake:+.2f}% 这个伪同比不是公司印的，而是<b>我们</b>把 2012 按当年公告值入库'
        f'之后会自己算出来的。要躲开它只有一个办法：不入库 2012。'
        f'代价是页面上 2013 那 12 个月的同比是空的 —— 这正是想要的结果，'
        f'空格是「本库没有可比分母」，比一个错 {abs(_fake - _true):.1f}pp 的数诚实。'
        f'（把公告里那个重述后的比较数补进来在算术上也自洽，但那是「比较栏」不是当期公告，'
        f'与「入库值必须是当期官方公告原值」的规矩冲突，故不做。）')
else:
    _START_NOTE = (
        f'<b>序列自 {_M0 or "2013-01"} 起，且 2012 刻意不入库。</b>'
        '2012 及以前的月度公告是旧口径，2013 起改合并口径并重述了比较数；'
        '把 2012 按当年公告值接上去，会让本页自己算出一个公司从未印过的伪同比。')


# ── ②b 窗口起点藏起来的那个断点（本页 x_from='2016-01' 才需要的一条）─────────────
#
# 底座只知道「断点月在不在这张图的窗口里」。它知道不了「断点在窗口外，但它的影子
# 经由派生同比的分母还留在窗口内最早那几格」。x_from 一旦晚于某条断点，这句话就得有人说。
def _first_clean(break_month):
    """给一个断点月，算出各口径「分子分母两边都落在断点右侧」的第一期。

    单月同比 = 当月 ÷ 去年同月           ⇒ 分母 ≥ 断点 ⇒ m ≥ 断点 + 12；
    12 个月滚动合计同比 = 近 12 ÷ 上一个 12 ⇒ 分母首月 = m − 23 ⇒ m ≥ 断点 + 23；
    季度同比 = 3 个月比 3 个月、去年同季   ⇒ 断点所在季 + 4 个季。
    """
    y, m = int(break_month[:4]), int(break_month[5:7])
    t = y * 4 + (m - 1) // 3 + 4
    return {'yoy': _shift(break_month, 12),
            'ttm': _shift(break_month, 23),
            'qtr': f'{t // 4}Q{t % 4 + 1}'}


# **先判 None 再比大小**：`str < None` 是 TypeError，而这是 import 期。
_C = _first_clean(_BRK_NEWBIZ) if (_X_FROM and _BRK_NEWBIZ < _X_FROM) else None
if _C:
    _WINDOW_BREAK_NOTE = (
        f'⚠️ <b>{_BRK_NEWBIZ} 那条断点落在页面窗口（{_X_FROM} 起）之外，所以短窗口图上'
        f'看不到它的红线 —— 但它的影子还在窗口里。</b>'
        '断点线画在断点期的左缘，语义是「从这一期起与左侧不可比」；而<b>派生同比的分母'
        '站在更左边</b>，所以窗口内最早那几格的分母仍然含着 Topcell 除列之前的合并数。'
        '分子分母两边都落在断点右侧的第一期，按口径各不相同：'
        f'单月同比 <b>{_C["yoy"]}</b>、12 个月滚动合计同比 <b>{_C["ttm"]}</b>、'
        f'季度同比 <b>{_C["qtr"]}</b>（分母分别要回溯 12 个月、23 个月和 4 个季）。'
        f'也就是说，把窗口抬到 {_X_FROM} 只是把这条断点<b>移出画面</b>，'
        '并没有把它移出算式。'
        f'{_BRK_USJC} 那条断点在窗口内，图上有红线，底座已逐图标出；'
        '全历史那张图用的是完整序列，两条红线在那张上都画得出来。')
else:
    _WINDOW_BREAK_NOTE = (
        '<b>本页登记的断点与页面窗口的关系</b>：本轮的窗口起点不晚于任何一条断点，'
        '所以每条断点都落在图上（第 0 格除外，那里左缘就是画布边线）。'
        '需要提醒的只有一件事：即使断点画得出来，派生同比的<b>分母</b>仍站在断点左侧 —— '
        '单月同比要回溯 12 个月、12 个月滚动合计同比要回溯 23 个月、季度同比要回溯 4 个季。')

# ── ③ 2015-06 新事业分部（Topcell）退出合并 ──────────────────────────────────
_NB_ROWS = []
for _y, _w0, _w1, _src in _WAFER_YOY:
    _c = _fy_yoy(_S, _y)
    if _c is None:
        _NB_ROWS = []
        break
    _NB_ROWS.append((_y, _c, (_w1 / _w0 - 1.0) * 100.0, _src))

_NB_HEAD = (
    f'<b>{_BRK_NEWBIZ} 起 Topcell Solar 退出合并，2015–2016 的同比里有一块口径缩减。</b>'
    '月营收公告是<b>合并数</b>，2015 年 6 月以前一直含着与晶圆代工无关的「新事业」'
    '（New Business）分部。可指认的公司行为与日期由公司原话给定 —— 2Q15 法说新闻稿'
    '（2015-08-26 报送的 6-K）逐字：「Topcell Solar Inc. officially merged into Motech '
    'Industries Inc. on June 1, 2015, resulting in UMC owning approximately 9% of Motech '
    'equity shares. As such, we will no longer consolidate its operating performance into '
    'UMC’s financial statements.」')
_NB_SEG = (
    '分部对外营收（NT$ 千元）按<b>申报文件</b>分组列，不跨年报串成一条曲线：'
    'FY2015 20-F 的三栏是 '
    + '、'.join(f'{y} 晶圆代工 {w:,} / 新事业 {n:,}'
                for y, (w, n) in sorted(_SEG_FY2015_20F.items()))
    + '；FY2016 20-F 把 2014/2015 的分部划分重述过，同一附注里是 '
    + '、'.join(f'{y} {w:,} / {n:,}' for y, (w, n) in sorted(_SEG_FY2016_20F.items()))
    + '。两份文件对 2015 年新事业的读数分别是 '
      f'{_SEG_FY2015_20F[2015][1]:,} 与 {_SEG_FY2016_20F[2015][1]:,} —— '
      '把它们接成一条「新事业逐年营收」是把重述当成经营变化，本页不这么做。')
if _NB_ROWS:
    _NEWBIZ_NOTE = (
        _NB_HEAD + _NB_SEG
        + '后果落在同比上（合并侧由本表现算，分部侧取<b>同一份</b> 20-F 的相邻两栏）：'
        + '；'.join(
            f'{y} 年本表合并同比 <b>{c:+.2f}%</b>，同期晶圆代工分部 <b>{w:+.2f}%</b>'
            f'（{src}），差 {abs(c - w):.1f}pp'
            for y, c, w, src in _NB_ROWS)
        + '。数据本身没有问题（合并数就是这么多），不可比的是这两年的同比。'
          f'图上 {_BRK_NEWBIZ} 的红色竖虚线语义是「从这一期起与左侧不可比」。'
          '⚠️ 这条断点只对应 <b>Topcell（太阳能电池）</b>一家子公司的除列，'
          '不是「整个新事业分部在这一个月消失」：'
          f'新事业分部在 2016 年仍有 {_SEG_FY2016_20F[2016][1]:,} 千元对外营收，'
          '剩下的收缩是 2015–2016 年太阳能/LED 业务自身的萎缩，'
          '不该一并算到这条线的账上。')
else:
    _NEWBIZ_NOTE = (
        _NB_HEAD + _NB_SEG
        + '数据本身没有问题，不可比的是 2015–2016 那两年的同比。'
          '（本次未能从 CSV 现算出合并侧的年度同比，故此处不并列两侧读数。）')

# ── ④ 2019-10 USJC 并表 ──────────────────────────────────────────────────────
_IN = _yoy_mean(_S, _BRK_USJC)                     # 2019-10 ~ 2020-09
_BEFORE = _yoy_mean(_S, _shift(_BRK_USJC, -12))    # 2018-10 ~ 2019-09
_AFTER = _yoy_mean(_S, _shift(_BRK_USJC, 12))      # 2020-10 ~ 2021-09
_USJC_HEAD = (
    f'<b>{_BRK_USJC} 起 USJC 并表，那 12 个月的同比含一块无机增量。</b>'
    '2019-09-25 报送的 6-K 逐字：「All relevant government approvals were obtained on '
    '2019.09.25. As a result, the scheduled transaction date will be 2019.10.01 and the '
    'total shares acquired are 97,800,000 shares and the consideration is about JPY54.4 '
    'billion.」—— 三重富士通半导体（Mie Fujitsu Semiconductor，MIFS，更名 United '
    'Semiconductor Japan Co., Ltd. / USJC）自 2019-10-01 起 100% 并表。'
    '同一份 6-K 的 Exhibit 99.2 是公司新闻稿，标题逐字为「UMC Receives Final Approval '
    'for 100% Acquisition of Mie Fujitsu Semiconductor」，正文自述已满足全部交割条件、'
    'MIFS 原为联电与富士通的 300mm 合资晶圆厂。'
    '（坊间流传的「enhance company’s market share by 10%」那句<b>不在这份申报里</b>，'
    '本页不引。）')
if None not in (_IN, _BEFORE, _AFTER):
    _USJC_NOTE = (
        _USJC_HEAD
        + f'本表现算：并表前 12 个月（{_shift(_BRK_USJC, -12)} 起）单月同比均值 '
          f'<b>{_BEFORE:+.1f}%</b>，并表当年 12 个月（{_BRK_USJC} 起）<b>{_IN:+.1f}%</b>，'
          f'翻过基数之后的 12 个月（{_shift(_BRK_USJC, 12)} 起）<b>{_AFTER:+.1f}%</b>。'
          '数据本身没有问题（合并数就是这么多），不可比的是中间那 12 个月的同比 —— '
          f'图上的红色竖虚线画在 {_BRK_USJC} 的左缘。'
          '⚠️ 这三个均值是<b>并排的事实</b>，不是「无机增量 = 中间减两边」：'
          '同期还叠着 2020 年的行业上行与 2019 年的下行基数，'
          '本页不把它们拆开，也不声称拆得开。')
else:
    _USJC_NOTE = (
        _USJC_HEAD
        + '⇒ 2019-10 ~ 2020-09 共 12 个月的同比与前后不可比。数据本身没有问题，'
          '不可比的是同比。（本次未能从 CSV 现算出三段均值，故此处不并列读数。）')

# ── ⑤ 汇率线出、美元营收腿不出 ───────────────────────────────────────────────
#
# 这两件事本轮才被拆开（见文件头 ⑤b / ⑤c）。下面三段分工明确，**不重复底座已经说过的**：
#   · `_SKIP_FX_LINES` / `_SKIP_FX_CONTRIB` → 底座渲染成「本页不出「…」那张图：…」
#   · `_FX_LEG_NOTE`   → **只**放对本页上一版那句错误推理的更正（一手证据都在上面两条里，
#                        不在这里重印）
#   · `_FX_RATE_EXTRA` → 追加到 Ex8 自己的图注：这条线在本页覆盖期内的现算读数
# 「页上有汇率线但没有美元腿」这句总述、以及那句公司自述本身，由底座按 §1.5 印一次，
# 这里不再印第二遍（同一件事印两遍，改口径时必然只改得动一遍）。
_FX_CSV = 'tsm_fx.csv'
_FX_COL = 'ntd_per_usd'


def _fx_series():
    """series/tsm_fx.csv → {month: rate}。读不到返回 {}，**不抛异常**（import 期）。"""
    try:
        p = os.path.join(_facts.SERIES, _FX_CSV)
        with open(p, encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
    except Exception:                                            # noqa: BLE001
        return {}
    out = {}
    for r in rows:
        try:
            out[r['month']] = float((r[_FX_COL] or '').strip())
        except (KeyError, TypeError, ValueError):
            continue
    return out


_FX = _fx_series()
# 与本页营收序列的交集 —— 图上画的就是这一段（底座把 fx reindex 到营收月份，
# 缺一格就在 DataSet 加载期硬失败，所以这里算出来的覆盖与图上一致，不是另一套口径）。
_FXO = {m: _FX[m] for m in _MS if m in _FX} if (_FX and _MS) else {}

# ── 跳掉 Ex5 / Ex6 的理由（两张图各一条，底座要求逐 slug 给）──────────────────
_SKIP_WHY_CORE = (
    '联电<b>不按月披露美元营收</b>：月度公告只有新台币一个口径（公告抬头逐字：'
    '「1) Sales volume (NT$ Thousand)」）。20-F 里那一列美元是<b>便利折算</b>，'
    '而且是按<b>年末单一即期牌价</b>整列折的 —— FY2025 20-F 附注 4(7) 逐字：'
    '「Translations of amounts from NTD into U.S. dollars (USD) for the reader’s '
    'convenience were calculated at the rate of USD 1.00 to NTD 31.37 on December 31, '
    '2025 released by Board of Governors of the Federal Reserve System. No representation…」；'
    'SEC XBRL 里 2017–2024 八个年度的 TWD ÷ USD 商也逐年是干净的年末牌价'
    '（29.64 / 30.61 / 29.91 / 28.08 / 27.74 / 30.73 / 30.62 / 32.79）—— '
    '<b>年末一个点的牌价，不是逐月</b>，与本页任何一个月的营收都对不上。')
_SKIP_FX_LINES = (
    _SKIP_WHY_CORE
    + '拿本页的月度新台币去除外部月均牌价，折得出一条「US$ 营收」曲线，但它是'
      '<b>分析师构造值</b>，没有任何官方月度美元数可以对账 —— 而这张图的全部意义'
      '正是「两条官方腿并排」。⇒ 不画。'
      '⚠️ 这与公司自述「超过一半营收以美元计价」<b>不矛盾</b>：'
      '「多数营收以美元计价」是真的，「公司按月公布过美元营收」是假的，'
      '前者只撑得起一条汇率线（见本页的 NTD/USD 那张），撑不起一条美元营收线。')
_SKIP_FX_CONTRIB = (
    '汇率贡献 = 本币 y/y − 美元 y/y，它是<b>上一条那张图两条腿的代数差</b>：'
    '美元腿既然是构造值，两者的差就是「构造值的同比」减出来的第二层构造值，'
    '量级正常、正负号也对，图上看不出毛病 —— 正是最难被发现的一类错。'
    '⇒ 不画。本页对汇率只做一件事：把<b>汇率本身</b>画出来（NTD/USD 那张），'
    '不与营收线相乘、也不相除。')

# ── 对上一版一句错误推理的更正 ──────────────────────────────────────────────
# **只写这一件事**：该画汇率线的出处由底座印一次（usd_share_note），不该画美元腿的
# 逐条理由由 skip_note 印一次（上面两条），这里再印第三遍就是同一段话三份、
# 而改口径时只改得动一份。这条 note 的唯一内容是「上一版错在哪、据什么撤回」。
# （上一版的错误陈述已经上过线，所以更正留在页上；等页面滚过几个月、主线程认为
#  不再需要时可以整条删掉，删它不影响页上任何一个数。）
_FX_LEG_NOTE = (
    '<b>更正本页上一版的一句推理 —— 它把汇率线整张挡在了页外。</b>'
    '上一版引 FY2025 20-F「Foreign Currency Risk」一节的'
    '「Although the majority of our transactions are in NT dollars…」，'
    '据此写成「与 TSMC『约七成营收以美元计价』正好相反」，并顺手跳掉了汇率图。'
    '<b>那句推理不成立</b>：该句讲的是 transactions（结算/交易币别），不是 revenue'
    '（计价币别）—— 晶圆厂完全可以用美元开票，同时多数交易笔数（本地薪资、资本支出、'
    '供应商付款）以新台币结算，两者不互斥。同一份 20-F 的 Item 3.D 风险因子一节对 '
    'revenue 讲得很直接：「More than half of our operating revenues are denominated in '
    'currencies other than New Taiwan dollars, primarily in U.S. dollars.」'
    '（逐字出处见上面「本页有汇率线，但没有美元营收腿」一条）。'
    '⇒ 本页撤回「正好相反」这个结论，把<b>汇率线</b>放回页上；'
    '<b>美元营收腿仍然不画</b>，理由与那句自述无关，见「本页不出「fx_lines」/'
    '「fx_contrib」那张图」两条。')

# ── Ex8 图注的本页补注：这条线在本页覆盖期内的现算读数 ────────────────────────
if _FXO:
    _FXM = sorted(_FXO)
    _LO_M = min(_FXM, key=lambda m: _FXO[m])
    _HI_M = max(_FXM, key=lambda m: _FXO[m])
    _LAST = _FXO[_FXM[-1]]
    _Y_AGO = _shift(_FXM[-1], -12)
    _FX_YOY = ((_LAST / _FXO[_Y_AGO] - 1.0) * 100.0) if _Y_AGO in _FXO else None
    _FX_RATE_EXTRA = (
        f'<b>本页覆盖期内的现算读数</b>：这条线在 {_FXM[0]}–{_FXM[-1]} 共 {len(_FXM)} 个月上'
        f'与本页营收<b>逐月对齐</b>（底座把汇率序列 reindex 到营收月份，缺一格就在加载期'
        f'硬失败，所以这里的覆盖就是图上的覆盖）；区间低点 {_FXO[_LO_M]:.2f}（{_LO_M}）、'
        f'高点 {_FXO[_HI_M]:.2f}（{_HI_M}）、末月 {_FXM[-1]} 为 {_LAST:.2f}'
        + (f'，较 12 个月前{"贬" if _FX_YOY > 0 else "升"}值 {abs(_FX_YOY):.1f}%'
           if _FX_YOY is not None else '')
        + '。⚠️ 这几个数说的都是<b>汇率自己</b>（NTD 兑 USD，数字变大 = 新台币贬值），'
          '<b>不是联电的任何营收量</b>，本页也没有把它与营收线相乘或相除。'
          '同理，<b>本图上没有红色竖虚线</b>：本页登记的两个口径断点'
          '（Topcell 除列 / USJC 并表）是<b>联电自己</b>的合并范围变化，'
          '而这条汇率是宏观序列，不因任何一家公司的并表或除列而换口径，'
          '<b>它在那两个月的两侧完全可比</b> —— 所以底座不把断点画到这张图上。'
          '页尾那句「从这一期起与左侧不可比」说的是本页的营收口径，不是这条线。'
          f'序列文件是 <code>series/{_FX_CSV}</code>，本站挂同一份汇率的每一页共用它 —— '
          f'其中 2013-01 至 2015-12 那 36 个月是本轮从美联储 H.10 历史页回补的'
          f'（口径与既有段同一个函数，2016-01 起一格未改），补的原因就是本页营收自 '
          f'{_MS[0]} 起、比原先的汇率下界早三年。')
else:
    _FX_RATE_EXTRA = (
        '<b>本页覆盖期内的读数本次未能从 CSV 现算</b>，故此处只作定性表述：'
        '这条线是 NTD 兑 USD 的月均牌价（数字变大 = 新台币贬值），'
        '与本页营收逐月对齐（缺月会在底座加载期硬失败），'
        '<b>它不是联电的任何营收量</b>，本页也没有把它与营收线相乘或相除。')

_NO_GUIDANCE_NOTE = (
    '<b>本页没有指引桥，也没有分部线。</b>'
    '（1）联电法说会给的是下一季 wafer shipments 环比、ASP（美元）环比、毛利率与产能'
    '利用率，<b>不是营收区间</b>（对照 TSMC 每季给美元营收区间 + 假设汇率，那才折得出'
    '「本季剩余月份月均还需多少」）。把三条环比指引乘成营收要先假设产品结构与汇率，'
    '折出来的数没有官方值可以对账 —— 这不是数据缺失，是对象不存在。'
    '（2）分部拆分只出现在季报与年报，月度公告从来只有一个数；'
    '而且 FY2025 20-F 附注 12 已经写明「The Company only has wafer fabrication operating '
    'segment as the single reporting segment.」—— '
    '在月度粒度上这个字段不存在，所以汇总表与长历史图上都没有分部行/分部线。')

# ── ⑥ 单月 y/y 的来源：把底座留白的那一半补上（**不是**纠正底座）─────────────
#
# 底座只说得出「本页 spec 未登记 official_yoy」，并明说这不等于「公司没披露」——
# 后者是一句关于公司公告内容的事实断言，底座读不到，要说得由本 spec 带出处来说。
# 这一条就是把那句断言补上，方向与底座相反：**公司披露了，是我们没落库**。
# （早先底座那句写的是「该家的月度公告不带 y/y 列」，对联电是事实错误；本轮批次里
#  已改成现在这句中性的措辞，所以这条 note 不再需要「更正」的口气。）
_YOY_SRC_NOTE = (
    '<b>补一句底座说不出口的事实：联电的月度公告<u>是</u>带 y/y 百分比列的，'
    '本页不用它是我们的选择，不是公司没披露。</b>'
    '页内上面那条只说得出「本页 spec 未登记 <code>official_yoy</code>」，'
    '并明说那不等于「公司没披露」—— 这里补上后半句。'
    '公告表格逐字是「Period Items 2026 2025 Changes %」，2026-07 那份印的是 '
    '<code>23,844,045 / 20,040,049 / 3,803,996 / 18.98%</code>'
    '（该期的申报值与本页序列一致；核对表是滚动 13 行，这一期未必总在末行）。'
    '跨年份抽查的四份 6-K —— '
    '2012-12（2013-01-25 报送）、2013-12（2014-01-28）、2019-08（2019-09-25）、'
    '2026-07（2026-08-06）—— 都有这一列。'
    '<b>本页仍然全部自算，是刻意的</b>：<code>series/umc.csv</code> 只落库 month / '
    '当月净销售额 / 公司公布的本年累计三列，没有落 % 列，因为公告的「去年同期」栏'
    '印的是<b>重述后</b>的比较数（见「序列自 2013-01 起」一条），'
    '而重述后的 2012 不在本库里 —— 落进来就会在页上留一个「用页内任何两格都乘不出来」'
    '的同比。自算值口径统一走 <code>build/yoy.py</code>。'
    '两者在有共同分母的月份上应当只差公司侧的四舍五入'
    '（如 2026-07：公告 18.98%，本页自算同一对数）；'
    '本页不并列这个差值，因为并列需要把公告的 % 也落库一份，那正是上面拒绝做的事。')

# ── ⑥b 热力矩阵覆盖的年度（heat_years）与两条断点的关系 ──────────────────────
#
# 矩阵没有连续横轴，画不了断点竖线（底座本轮已改成对 heat_matrix 不写 break_at，
# 见文件头 ⑧），所以「哪几格不可比」只能由这一条说。
# 首行年份**现算**，跟着 _HEAT_YEARS 与数据一起走，不写死 —— 底座的取法是
# 「所有算得出单月同比的年度里取最近 NH 个」。
_YOY_YEARS = sorted({int(m[:4]) for m in _S if _shift(m, -12) in _S})
_HEAT_Y0 = _YOY_YEARS[-_HEAT_YEARS] if len(_YOY_YEARS) >= _HEAT_YEARS else (
    _YOY_YEARS[0] if _YOY_YEARS else None)
if _HEAT_Y0:
    _HEAT_SPAN_NOTE = (
        f'<b>热力矩阵只放最近 {_HEAT_YEARS} 个年度（{_HEAT_Y0}–{_YOY_YEARS[-1]}）</b>'
        '，与 <code>/tsm/</code> 页同一个基准。更早的年份不是算不出来，是没印在这张图上；'
        f'全部 {_MN} 个月的绝对水平在全历史那张图上是完整的。'
        '矩阵的横轴是 1–12 月、纵轴是年份，<b>没有一条能承载「从这一期起与左侧不可比」的'
        '连续时间轴，所以这张图上没有、也不会有红色竖虚线</b>'
        '（引擎对 <code>heat_matrix</code> 走的是 <code>drawHeat</code>，不读 '
        '<code>break_at</code>）。读这张图请按本页登记的断点对号入座：'
        f'{_BRK_USJC} 起的 12 个月（{_BRK_USJC} 到 {_shift(_BRK_USJC, 11)}）那 12 格'
        '含 USJC 并表的无机增量；'
        + (f'{_BRK_NEWBIZ} 那条断点早于矩阵首行（{_HEAT_Y0}），它影响的 2015/2016 两年'
           '不在这张图上，要看那两年请看全历史图与页尾对应的那一条。'
           if int(_BRK_NEWBIZ[:4]) < _HEAT_Y0 else
           f'{_BRK_NEWBIZ} 起的 12 个月（{_BRK_NEWBIZ} 到 {_shift(_BRK_NEWBIZ, 11)}）'
           '那 12 格含 Topcell 除列造成的口径缩减。'))
else:
    _HEAT_SPAN_NOTE = (
        '<b>热力矩阵没有连续横轴，因此这张图上没有、也不会有断点红线</b>'
        '（引擎对 <code>heat_matrix</code> 走 <code>drawHeat</code>，不读 '
        '<code>break_at</code>）。读它时请按页尾登记的两条断点对号入座。')

# ── ⑦ 数据源与落库口径 ───────────────────────────────────────────────────────
_SRC_NOTE = (
    '<b>数据源与落库口径。</b>主源是 SEC EDGAR 上联电的 6-K 附件（CIK 1033767），'
    '即台湾《证券交易法》要求次月 10 日前公告的「营运情形公告」英文原文；'
    '一份附件同时给齐当月、去年同月、本年累计、去年同期累计四个数与变动额、变动率。'
    '序列存两列：当月净销售额与<b>公司自己公布的本年累计</b>。存累计不是冗余 —— '
    '公司印错过单月数：2016-06-24 那份 6-K 印的 5 月单月是 17,705,227 千元，'
    '而（a）本年累计差 57,873,709 − 45,168,482 = 12,705,227、'
    '（b）同一行的变动额 −225,827 = 12,705,227 − 12,931,054、'
    '（c）同一行的变动率 −1.75% 同样只对 12,705,227 成立、'
    '（d）一年后那份公告的「去年同月」栏 = 12,705,227 —— 四路里三路指向 12,705,227，'
    '印出来那个数是把 1 打成 7 的手误。因此本页所有月份的金额一律由<b>累计差反算</b>。'
    '同类的还有标签本身：2015-02 那份的行标签印成 “January”、2016-01 那份印成 '
    '“December”，而 “for the period of …” 那句在 2013-09 ~ 2014-01 连着六份都卡在 '
    '“July 2013” 没改（2016-06 那份也写着 “March 2016” 却在报 5 月）—— '
    '所以判月只认累计链，不认标签。'
    '交叉校验源是 TWSE OpenAPI <code>t187ap05_L</code>（只有最新一期，'
    '2303 是本国公司故在这张表里），与 6-K 逐字相等。')

# ── ⑧ 不做日均化（结论与 TSMC 同、理由与 TSMC 相反，必须自己算，不能照抄）────
_D = _facts.days_effect(_CSV, _COL)
# 对照组也现算：底座与 /tsm/ 页那边的 1.47 / 0.84 / 0.91 同样不写死。
# 读不到 series/tsm.csv 就整句不提对照 —— 不留一个没人能核的旁证。
_DT = _facts.days_effect('tsm.csv', 'revenue_ntd_mn')
if _D:
    _norm = _D['feb'] / _D['feb_days'] if _D['feb_days'] else None
    _cmp = ((f'（同一把尺子量 <code>/tsm/</code> 那条序列是斜率 {_DT["slope"]:.2f}、'
             f'2 月比值 {_DT["feb"]:.2f} vs 天数比值 {_DT["feb_days"]:.2f} —— '
             f'那边 2 月<u>低于</u>天数比值，与本页恰好相反。）')
            if _DT else '')
    _DAYS_NOTE = (
        '<b>本页不做日均化。</b>晶圆厂 24/7 连续生产，每个日历日都是生产日，'
        '看上去正该按天数归一化；这个假设被本序列自己否掉，而且<b>否掉的方向与 '
        '<code>/tsm/</code> 页相反，所以这段话不能跨家照抄</b>：'
        f'<code>(m/m) ~ (天数变化%)</code> 在本序列 {_D["n"]} 个月上的回归斜率是 '
        f'<b>{_D["slope"]:.2f}</b>（不是 1）—— 天数每变动 1%，实际环比只跟着走 '
        f'{_D["slope"]:.2f}%，按比例归一化会<b>过度修正</b>。'
        f'2 月更直接：本序列 2 月对相邻 1、3 月均值的实际比值是 {_D["feb"]:.2f}'
        f'（{_D["feb_n"]} 个年度平均），而天数比值是 {_D["feb_days"]:.2f} —— '
        f'<b>实际比值反而<u>高于</u>天数比值</b>'
        + (f'，除完天数之后 2 月的日均是 1、3 月日均的 {_norm:.2f} 倍：'
           '一个原本看得见的 2 月凹坑会被归一化翻成「2 月日均最强」。'
           if _norm else '。')
        + _cmp
        + '两家共同的结论只有一条：天数是农历年与季末拉货日历的<b>代理变量</b>，'
          '不是产出的线性驱动，按天数除一遍只会把日历效应重新分配到别处'
          '（联电这边是把 2 月的坑推平，TSMC 那边是把 2 月的坑挖深）。'
          '季节性改用同月对同月定位（页顶 brief 与 heat_matrix 都是这么读的）。')
else:
    _DAYS_NOTE = (
        '<b>本页不做日均化。</b>按天数归一化要求「多一天 ≈ 多一天的产出」，'
        '而本序列的月度波动幅度远大于天数差本身能解释的部分；'
        '天数只是农历年与季末拉货日历的代理变量。'
        '（本次未能从 CSV 现算出斜率与 2 月比值，故只作定性表述。）')


SPEC = {
    'ticker': 'umc',
    'name': 'UMC',
    'tracker': 'UMC Monthly Revenue Tracker',
    'title': '联华电子 UMC (2303.TW / NYSE: UMC)：月度营收跟踪',
    'source': 'Source: UMC monthly net sales announcements filed with the SEC on Form 6-K '
              '(EDGAR CIK 1033767), reconciled to 20-F consolidated statements and '
              'cross-checked against TWSE OpenAPI t187ap05_L; format after Goldman Sachs GIR',
    'source_zh': '联电报送 SEC 的 6-K 附件（台湾月度营运情形公告原文，合并净销售额，'
                 'NT$ 千元，未经会计师查核，台湾法定次月 10 日前公布）',
    'csv': _CSV,

    # 唯一的官方披露字段。月营收 / 3MMA / QTD / YTD / 占 TTM 比重全部由它派生。
    'value': {
        'col': _COL,
        'div': 1000.0, 'label': 'NT$bn', 'sym': 'NT$', 'unit': 'bn', 'dec': 1,
        # 公告原文的单位是 NT$ **千元**（"1) Sales volume (NT$ Thousand)"）。
        # 核对表的标题写着「官方原始单位，未换算」，所以这里必须把真实单位与那一次
        # 除法说出来，并把三位小数留住 —— 它们就是公告的千元位，舍掉就不叫「未换算」。
        'raw_label': 'NT$mn = 公告 NT$ 千元 ÷ 1,000',
        'raw_dec': 3,
        'zh': 'NT$ 营收',
        'ccy_zh': '新台币',
        # 13 个完整年度对官方年报 diff = 0，且 12 个月相加 = 公告的本年累计。
        # 功能货币与表达货币均为新台币（FY2025 20-F 附注 4(5)），月值是原生记账数。
        'summable': True,
    },

    # 不给 official_yoy：公告**有** "Changes %" 列，但 series/umc.csv 没有落库这一列
    # （落库的原因见 _YOY_SRC_NOTE）。硬填一个不存在的列名会在 DataSet 加载期硬失败。

    # ── 汇率：**给 fx，但显式跳掉两张美元腿的图**（见文件头 ⑤b / ⑤c）─────────
    # 「有没有 fx 序列」与「该不该画美元腿」是两件事，底座 §1.5 已把判据拆开：
    # Ex8 画的是 ds.fx 本身（一条宏观序列，挂同一份汇率的每一页逐点相同，不需要
    # 联电披露任何东西），Ex5/Ex6 画的是这家公司的美元营收（联电没有官方月度值）。
    # ⇒ fx 照给 + skip 那两张。skip 掉之后底座不会在抬头、brief、核对表、页尾
    #   任何一处印出美元营收数字（判据是 usd_leg_shown(EX)，不是 ds.fx）。
    'fx': {
        'csv': _FX_CSV, 'col': _FX_COL, 'quote': 'NTD per USD',
        # 与 /tsm/ 页共用同一个文件、同一个口径 —— 这条序列是宏观数据，不是本家数据。
        'src': '美联储 H.10 台湾地区日度牌价的月度算术平均（该月全部营业日的算术平均，'
               '美方假日的 ND 不计入；与 FRED 的 EXTAUS 同源同口径），'
               f'序列文件 series/{_FX_CSV}，本站挂汇率的各页共用',
        # ⚠️ per-ticker，**不可继承**：底座对有 fx 却没给这个字段的 spec 硬失败。
        #    联电官方只给定性表述、**不给百分比** —— 底座 validate() 明写的退路
        #    （底座 `validate()` 对 `usd_share_note.src` 的那段：核不动的百分比就改成
        #    不带数字的定性版本。按符号 grep，不写行号）。
        #    这里走的正是那一支：一个字的百分比都不编。
        'usd_share_note': {
            'en': 'UMC states that more than half of its operating revenues are '
                  'denominated in currencies other than NT dollars, primarily in U.S. '
                  'dollars, while revenues are reported in NT$ — so this rate moves the '
                  'reported growth rate. The company gives no percentage, and none is '
                  'implied here. This exhibit plots the exchange rate itself; UMC does '
                  'not disclose monthly U.S. dollar revenues.',
            'zh': '联电自述「超过一半的营业收入以新台币以外的币别计价，主要是美元」'
                  '（<b>公司只给这句定性表述、没有给百分比</b>，本页也不编一个），'
                  '而报表以新台币列报，所以这条汇率线直接推动本页的头条增速；'
                  '但联电<b>不按月披露美元营收</b>，页上因此只有汇率本身，没有美元营收腿',
            'src': 'UMC FY2025 Form 20-F（2026-04-30 报送，accession 0001193125-26-193757）'
                   'Item 3.D「Risk Factors」项下「Currency fluctuations could increase our '
                   'costs relative to our revenues…」一条，逐字「More than half of our '
                   'operating revenues are denominated in currencies other than New Taiwan '
                   'dollars, primarily in U.S. dollars.」（同句在 FY2023 / FY2024 两份 20-F '
                   '里逐字相同）；'
                   'https://www.sec.gov/Archives/edgar/data/1033767/000119312526193757/'
                   'd91630d20f.htm',
        },
    },

    # 两张要「本币 ÷ 汇率」这条构造腿的图，显式跳掉（底座要求逐 slug 给理由）。
    'skip': ['fx_lines', 'fx_contrib'],
    'skip_note': {
        'fx_lines': _SKIP_FX_LINES,
        'fx_contrib': _SKIP_FX_CONTRIB,
    },

    # 追加到 Ex8 自己的图注末尾：这条线在本页覆盖期内的现算读数（数不写死）。
    'note_extra': {'fx_rate': _FX_RATE_EXTRA},

    # 不给 segments：分部只按季/按年披露，月度公告只有一个数；
    # 且 FY2025 20-F 附注 12 已写明只剩单一分部。

    # 不给 alt：本家没有第二计价列 —— 月度公告只有新台币一个口径。
    # ⚠️ 别把这句写成「NT$/US$ 双列是世芯-KY 独有的」：日月光（ase）的 series 里
    #    同样有 NT$/US$ 两列。区别不在「有没有两列」，在**第二列是什么**：
    #    世芯的 NT$ 列是官方按自报汇率折出来的**折算值**（不可加总 ⇒ 走 `alt`），
    #    日月光的 US$ 列是公司另一次**独立官方披露**（走底座的 `fx.fgn_col`，不是
    #    `alt`）。联电两者都没有，所以 `alt` 与 `fgn_col` 都不给。

    'window': {
        # 本轮任务书口径：短窗口图统一自 2016 起，但不得早于本家的口径连续起点。
        # 联电的口径连续起点是 2013-01（_START_NOTE），2016-01 晚于它 ⇒ 取 2016-01。
        # **显式写**（底座对漏写硬失败）：「用全序列」与「用 2016」都是决定，
        # 不该由「忘了写」来表达。副标题说的是数据覆盖（163 个月，全历史图就是 163 点），
        # 各图实际窗口由底座 _window_note 逐图现算声明，两者不冲突。
        # 被这个起点藏起来的 2015-06 断点见 _WINDOW_BREAK_NOTE。
        'x_from': _X_FROM,
        # 与 TSM 图列同一个基准（NH=9），覆盖最近 9 个年度。
        # 取 13 会让矩阵回到 2014 —— 比本页窗口起点还早两年，与「本页自 2016 起」这个
        # 口径反着走；2015/2016 那两年的口径缩减由全历史图 + 页尾两条说明承担，
        # 矩阵的行数由 _HEAT_SPAN_NOTE 现算写明，读者不会以为矩阵就是全部历史。
        'heat_years': _HEAT_YEARS,
        'check_rows': 13,
    },

    # 断点写成字面量而不是 series/umc_breaks.csv：本家只有两条，每条都由一次可查证的
    # 公司行为唯一确定（2015-06-01 Topcell 并入茂迪除列 / 2019-10-01 USJC 交割），
    # 不会跟着数据长。图上只挂月份，整句理由由底座的 break_note() 放进图注。
    'breaks': [
        {'month': _BRK_NEWBIZ,
         'zh': 'Topcell Solar 并入茂迪 Motech（合并基准日 2015-06-01）后不再合并，'
               '2015/2016 的同比含口径缩减'},
        {'month': _BRK_USJC,
         'zh': 'USJC（原三重富士通半导体 MIFS）100% 并表（交割日 2019-10-01），'
               '2019-10~2020-09 的同比含无机增量'},
    ],

    # 不给 continuity：本页有两条已登记的断点，「口径连续」这句断言在本家为假。
    # （底座只在 breaks 为空时才会用到 continuity。）

    'format_source':
        '版式仿 Goldman Sachs GIR 台股月营收报告（「Hon Hai (2317.TW)」与 '
        '「Wistron (3231.TW)」的 Exhibit 1-2，外加 GS HKEX 深度的超长历史层）',

    'notes': [
        _ADDITIVE_NOTE,
        _START_NOTE,
        _WINDOW_BREAK_NOTE,
        _NEWBIZ_NOTE,
        _USJC_NOTE,
        _FX_LEG_NOTE,
        _NO_GUIDANCE_NOTE,
        _YOY_SRC_NOTE,
        _HEAT_SPAN_NOTE,
        _SRC_NOTE,
        _DAYS_NOTE,
    ],
}
