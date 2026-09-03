# -*- coding: utf-8 -*-
"""台积电 TSMC（2330.TW / NYSE: TSM）月度营收页配置。

从 `build/tsm.py`（1130 行全硬编码 'tsm'）迁上通用底座 `mrbase.py`。
本文件只有**数据与本家专属的事实**，没有图型逻辑。

━━ 本家与另外六家的三处结构差别 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. **汇率腿**。TSMC 以美元计价、以新台币入账，所以 Ex5（NT$ vs US$ 单月同比）、
   Ex6（汇率贡献）、Ex8（NTD/USD 月均汇率）三张图对它成立。
   ⚠️ 但本页这三张的**证据等级并不一样**，别当成一件事读 —— 底座本轮把它拆成了
   两个独立标志：本页的**美元腿是我们拿本币 ÷ FRED 外部牌价折出来的推导值**
   （`fx.implied` 取默认 True，图例印「推导值(Implied)」），**Ex8 那条汇率线也不是
   公司申报的换算汇率**（`fx.rate_filed` 随之为 False，图上印 "monthly average"）。
   两者在本页恰好同时为「否」，但**它们不是同一个事实**（见世芯 / 日月光两页的反例）。

   ⚠️ **另外六家不是「都没有这条腿」，也不是「`fx` 留空」** —— 上一版这里这么写，
   本轮起逐条都不成立，请按家分：
   · **世芯（alchip）**：MOPS 月营收申报表直接给官方「功能性貨幣(美金)」栏与
     「本月換算匯率」栏 ⇒ 三张图全出，且**两条腿与汇率线都是官方值**
     （`implied=False` ⇒ `rate_filed` 默认为 True，图上印 "as filed"）。
   · **日月光（ase）**：月度新闻稿自印美元营收实绩（`series/ase.csv` 的
     `revenue_usd_mn` / `revenue_atm_usd_mn` 两列），美元腿是官方值 ——
     底座为这一形态开的是 `fx.fgn_col`（见 `mrbase._FX` 的注释）。但公司从不披露
     所用汇率，它的 Ex8 仍挂 FRED 牌价 ⇒ `implied=False` 而 `rate_filed=False`，
     这正是那两个标志本轮必须劈开的原因。
   · **联电 / 联发科 / 南亚科 / 创意**：确实没有官方月度美元实绩 —— 月度公告只有
     新台币，年报里那列美元是「便利折算」（联电那份是按**年末单一即期牌价**整列折的，
     不是全年均价，见 `mrspecs/umc.py` ⑤），拿本币 ÷ 外部牌价折出来的只能是分析师
     构造值，没有官方数可以对账。
   ⇒ 但这四家的 `fx` **同样不留空**：汇率线本身是一条宏观序列，画它不需要公司披露
   任何东西。它们照挂 `fx` + 显式 `skip: ['fx_lines', 'fx_contrib']`，底座只跳这两张
   （判据 `usd_leg_shown()`），**不跳汇率线**（判据 `fx_used()`），后面的编号顺次前移。
   ⚠️ 前移几格**逐页不同**，别在任何地方写死：有 `segments` 的家（日月光 / 创意）
   还多一张 `mix`。要引用编号一律走底座算好的 `EX[slug]` 查表。

2. **「约七成营收以美元计价」这句话是 TSMC 自己的事实，不可继承。**
   `build/tsm.py` 把它写死在两处（:875 英文的 Exhibit source、:1046 中文页尾），
   搬到另外六家就是六条事实错误陈述。这里做成 `fx.usd_share_note`，
   带出处；底座对有汇率腿却没给这个字段的 spec **硬失败**。
   ⚠️ 那个「约七成」是需要**每年跟着 20-F 重新核对**的口径数（TSMC 在市场风险一章
   披露以美元计价的销售占比），不是一次写完就永远对的常数。核对不上就把措辞改回
   「多数销售以美元计价」这种不带数字的定性版本，不要留一个过期的百分比在页上。

3. **指引桥**。TSMC 每季法说会给美元营收区间 + 假设汇率，`series/tsm_guidance.csv`
   六列填得满，所以 brief 的第 5 句是指引桥。另外六家一列都填不满
   （联电给 wafer shipments/ASP/毛利率的环比指引、世芯与创意只给定性展望），
   ⇒ 那六家不给 `brief_extra`，底座自动退回「三月均值同比 vs 单月同比」的趋势位置句。

━━ 断点 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`breaks` 为空，且**连 `continuity` 都不给**。**为什么**两个都不给，见下面 SPEC 里
`format_source` 上方那整段注释 —— 底座没有 `breaks_absent_zh` 这个字段（上一版这里
引的就是这个名字，`mrbase._SPEC` 的白名单里根本没有它，本页 SPEC 里也没有），
不给 `continuity` 时页面只印「本页 spec 未登记断点」这个中性事实。
底座不替任何一家断言「口径连续、未发生并表或重述」，那句话在联电（2019-10 USJC 并表、
2015-06 新事业退出合并）等至少四家上是假话。
"""
import numpy as np
import pandas as pd

from . import _facts
from . import _tsm_extra

# ── 图注里的数**一个都不写死**：下面这两句在 import 期从 CSV 现算，
#    读不到源就退回不带数字的定性版本（`_facts` 里每个函数拿不到都返回 None，不抛异常）。
#    原来这一段写死着「回归斜率 1.47」「0.84 vs 0.91」——今天算出来仍是这几个数，
#    但明年多 12 个月数据它们就会变，而写死的版本会静默过期。
_D = _facts.days_effect('tsm.csv', 'revenue_ntd_mn')
_DAYS_NOTE = (
    '<b>本页不做日均化</b>：晶圆厂 24/7 连续生产，每个日历日都是生产日，'
    '看上去正该按天数归一化；但这个假设被本页数据自己否掉 —— '
    + (f'<code>(m/m) ~ (天数变化%)</code> 在本序列 {_D["n"]} 个月上的回归斜率是 '
       f'{_D["slope"]:.2f} 而不是 1，'
       f'2 月对 1、3 月均值的实际比值 {_D["feb"]:.2f}（{_D["feb_n"]} 个年度平均）、'
       f'天数比值却是 {_D["feb_days"]:.2f}。'
       if _D else
       '按天数归一化要求「多一天 ≈ 多一天的产出」，而本序列的月度波动幅度'
       '远大于天数差本身能解释的部分（本次未能从 CSV 现算出斜率，故只作定性表述）。')
    + '天数只是农历年与季末拉货日历的<b>代理变量</b>，不是产出的线性驱动；'
      '按天数除一遍会把农历年效应算成「经营性走弱」。季节性改用同月对同月定位。')


# ══════════════════════════════════════════════════════════════════════════════
# 名词释义要用到的三个**结构性**常量 —— 全部在 import 期从源文件现算
# ══════════════════════════════════════════════════════════════════════════════
# 三个都不是「当月读数」：发行条件（币别 / 票面 / 年期 / 分次还本）在发行那天就定死了，
# 法定门槛写在申报表脚注里。但**一个都不许写死在释义正文里** —— 将来再发一檔宝岛债、
# 或再发一批分次还本的券，写死的那句话会静默变成假话，而页面上看不出来。
# 读不到源就退回不带数字的定性版本（同 `_facts` 的规矩：import 期不抛异常）。

def _formosa_terms():
    """宝岛债的发行条件，逐檔登记簿现算。返回可直接插进句子的短语，或 None。

    判据是 `currency != TWD`，与 `_tsm_extra._ladder()` 过滤在外券用的是同一条
    （那边 `btr['currency'] == 'TWD'`）—— 两处若各写各的，到期墙与这句话会在
    「哪几檔算宝岛债」上分家。
    """
    rows = _facts._rows('tsm_bonds_tranches.csv')      # 同包私有小工具，读不到返回 None
    if not rows:
        return None
    f = [r for r in rows if (r.get('currency') or '').strip() not in ('', 'TWD')]
    if not f:
        return None
    try:
        ccy = sorted({r['currency'].strip() for r in f})
        amt = [float(r['issue_amount_k']) / 1e6 for r in f]             # 千 → bn
        # ⚠️ 票面与年期**必须逐檔成对取**，不能各自 sorted(set()) 再并排印。
        #    本仓这两檔正好是 2.70%/40 年 与 3.10%/30 年：两个集合各自排序后并排
        #    印成「票面 2.70%／3.10%、30／40 年期」，读者按位次读得到的是**反的**
        #    配对。用 set 还会在两檔同票面时把 3 檔印成 2 个数。
        legs = sorted((float(r['coupon_pct']), float(r['tenor_years'])) for r in f)
    except (KeyError, TypeError, ValueError):
        return None
    if len(ccy) != 1:                    # 将来真出现第二种外币就不写这句，别硬拼
        return None
    # 'USD' → 'US$'：登记簿存的是 ISO 代码，页面上其余各处写的都是 US$。
    sym = 'US$' if ccy[0] == 'USD' else ccy[0] + ' '
    size = (f'各 {sym}{amt[0]:.1f}bn' if len({round(a, 6) for a in amt}) == 1
            else f'合计 {sym}{sum(amt):.1f}bn')
    return (f'{len(f)} 檔、{size}、逐檔票面／年期 '
            + '、'.join(f'{c:.2f}%／{t:.0f} 年' for c, t in legs))


def _amort_terms():
    """50/50 分次还本的檔数与期別 —— 到期墙那一条要用。读不到返回 None。"""
    rows = _facts._rows('tsm_bonds_tranches.csv')
    if not rows:
        return None
    a = [r for r in rows if (r.get('repayment_type') or '').strip() == 'amort_50_50']
    if not a:
        return None
    qb = sorted({(r.get('qibie') or '').strip() for r in a} - {''})
    # 不带括号：调用处已经在一层括号里，再套一层读起来是嵌套的。
    return f'{len(a)} 檔' + (f'，期別 {"／".join(qb)}' if qb else '')


def _trigger_pct():
    """MOPS 備註栏的法定触发门槛，读 `fetch/mops_remarks.py` 的 `TRIGGER_PCT`。

    出处是月营收申报表脚注第 6 条：「上市櫃及興櫃公司，本月營收或本年累計營收較去年
    同期增減變動達50％以上者，需於備註欄位說明增減變動原因」——`達…以上` 是闭区间。
    这是官方定义里的常数，本可以写死；不写死是因为**判定这七页那两列的就是那个常量**，
    两处各写一份、哪天法规改了只改一处，页面上不会有任何提示。
    加载方式抄 `build/specs/db1.py` 的 `_slow_universe()`（本仓没有 __init__.py，
    只能走 spec_from_file_location）；任何失败都退回法规原文里的 50。
    """
    import os as _os
    path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__)))), 'fetch', 'mops_remarks.py')
    try:
        import importlib.util
        sp = importlib.util.spec_from_file_location('_mops_remarks_for_spec', path)
        mod = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(mod)
        return float(mod.TRIGGER_PCT)
    except Exception:
        return 50.0


_FORMOSA = _formosa_terms()
_AMORT = _amort_terms()
_TRIG = _trigger_pct()


# ══════════════════════════════════════════════════════════════════════════════
# 名词释义（SPEC 的 `glossary`，排在所有 exhibit 之前）
#
# ━━ 与 brief / 页尾 notes / 图注的分工 ━━
# brief 与图注说的是「这个月这组读数该怎么读」（含当月读数、当月实测的口径差），每月重写；
# 这一块说的是「这些词是什么意思」，一年到头是同一段 ⇒ 这里**不写当月读数**。
# 出现的数只有上面那三个结构性常量（发行条件、分次还本檔数、法定门槛），全部现算。
#
# ━━ 为什么是这 14 个词（选词判断）━━
# 判据只有一条：这个词出现在本页的图题 / 序列名 / 纵轴 / 汇总表行头 / 核对表列头里，
# 而且**不看定义就会读错**。按「读错会出什么事」分五类：
#   ① 主序列本身的口径   合并营收、季度值（月加总）、占 TTM 比重 —— 全页 Ex2–Ex9 都
#      长在同一个官方字段上，而由它轧出来的三个派生量各自有一个坑：季度值不等于季报
#      营收（季报含月营收公告以外的收入项）、占 TTM 比重的分母跟着规模一起长。
#   ② 汇率腿（本页最独有的一块，另外六家的形态各不相同）   月均汇率、
#      美元营收（推导值）、汇率贡献 —— 这三条**都不是公司披露的数**：汇率是外部牌价、
#      美元营收是本币除牌价折出来的、汇率贡献是两条同比之差且单位是百分点。
#      不点破，读者会把 Exhibit 5 的美元线当成公司自印的美元实绩去和同业对表。
#   ③ 台湾申报制度的产物   觸發腿 —— 核对表最后两列不是「公司想说什么」，是一条有
#      ±50% 触发条件的法定披露栏。空 ≠ 沉默，这个误读在表上完全看不出来。
#   ④ 授权 vs 存量（Exhibit 10–17 那一整块最密集的坑）   董事會核准資本支出、
#      背書保證、遠期外匯未平倉 —— 这三张读的是公司**另外几张**月度申报表，
#      而它们分别是「往前看的授权」「在外余额 vs 核准数两套并存」「月底存量而不是
#      当月成交量」。混着读的代价是把授权额度当成 capex、或把存量当流量累加。
#   ⑤ 债券那三张图的派生口径   避险强度、边际成本 / 平均成本、宝岛债、到期墙 ——
#      每一个都是本页**自己轧出来**的量：比值的分母是 TTM÷12、边际成本是阶梯不是月度
#      报价、序列有意剔除了外币券、到期墙按实际还本时程而不是到期日排。
# **有意不收**：
#   · m/m、y/y、3Y %ile、pp / bp —— 全站通用的读图约定，每页 summary.note 已逐条讲过。
#     单月 vs 滚动 vs 季度这三种同比的分工也不收：页尾 notes 第 3 条逐处点名列过一遍，
#     释义板再讲一遍就是两处各写一份，而两份迟早会不一致。
#   · 3MMA / QTD / YTD —— 名字本身就是算法（3 个月均值、期内累计），本页对它们没有
#     特殊口径；它们那两列为什么留空是**分位与环比的性质**，summary.note 讲的就是这个。
#   · 口径断点、截轴 —— 页尾 notes 第 8 条由 payload 现读生成，会自己改口，
#     这里再写一段固定文字反而会有一天与它打架。
#   · 营收、市值、票面利率这类本页没有特殊口径的常识词。
# ══════════════════════════════════════════════════════════════════════════════
_GLOSSARY = [
    ('合并营收',
     '本页的主序列：公司月度营收公告里的<b>合并</b>口径当月净营收（含全部纳入合并的'
     '子公司），NT$mn，<b>未经会计师查核</b>，台湾法规要求次月 10 日前公布。'
     '汇总表上半张、Exhibit 2–9（Exhibit 8 是汇率线除外）与核对表的金额列<b>全部由它'
     '这一个披露字段</b>（加一条月均汇率序列）派生，不引入任何券商预测或外部估计。'
     '⚠️ Exhibit 10–17 与汇总表下半张<b>不在此列</b>：它们读的是公司另外几张'
     '月度申报表，与月营收<b>没有派生关系</b> —— <b>唯一的例外</b>是 Exhibit 13 与'
     '汇总表 <code>Hedge book / avg. monthly revenue</code> 一行，'
     '它们的<b>分母</b>取的正是本页月营收的 12 个月均值。'
     '（公告同时给出一个同比原值，本页凡标「公告同比」的地方用的都是它，不是我们除出来的。）'),

    ('季度值（月加总）',
     'Exhibit 3 的柱：该季<b>已公布月份</b>的新台币月营收直接相加，<b>不做任何调整</b>。'
     '⚠️ 它<b>不等于</b>公司季报的营收 —— 季报口径含月营收公告以外的收入项，'
     '所以这张图能用来抢跑季报的是<b>方向</b>，不是替代季报的数。'
     '右轴是严格的 3 个月比 3 个月：分子分母任何一边不满 3 个月就留空，'
     '末季未满 3 个月时柱另画成浅蓝。'),

    ('占 TTM 比重',
     '汇总表 Seasonality 那一行：<code>当月营收 ÷ 最近 12 个月合计 × 100</code>'
     '（TTM = trailing twelve months，滚动 12 个月合计）。'
     '⚠️ 它是<b>季节性定位</b>，不是增长：分母跟着规模一起长，'
     '所以这一行回答的是「这个月在最近一年里占多大分量」，'
     '<b>不回答</b>「比去年多了多少」，高低也只能与<b>同月</b>比。'),

    ('月均汇率',
     'Exhibit 8 那条线与核对表 <code>NTD per USD</code> 那一列：美联储 H.10 台湾地区'
     '日度牌价在该月<b>全部有报价营业日</b>上的算术平均（落库脚本 <code>fetch/tsm.py'
     '</code>）。⚠️ 它<b>不是公司申报的换算汇率</b> —— <b>月度</b>营收公告与月营收申报表'
     '都<b>不带</b>换算汇率栏（对照世芯的官方「本月換算匯率」栏），'
     '所以图与列头印的是 monthly average 而不是 as filed。'
     '本页凡是<b>由新台币折出来</b>的美元数（Exhibit 5 的美元线、核对表 '
     '<code>Implied revenue</code>、Exhibit 17 的两条腿、汇总表 Arizona 那一行）'
     '都建立在这条<b>外部</b>牌价上；'
     '⚠️ 但 Exhibit 10／11 的 US$ 是董事会 6-K 的<b>申报原值</b>，<b>不经</b>这条牌价。'),

    ('美元营收（推导值）',
     '<code>新台币月营收 ÷ 当月平均汇率</code>，<b>不是公司披露的美元营收</b>'
     '（月度公告只有新台币）。假设全部营收按当月平均汇率<b>一次性</b>折算，'
     '忽略月内汇率路径、对冲与递延收款 ⇒ 这条腿只能看<b>方向与量级</b>，'
     '不能拿去和公司自印美元实绩的同业逐格对表。'
     'Exhibit 5 的美元线与核对表的 <code>Implied revenue (US$mn)</code> 都是它。'),

    ('汇率贡献',
     'Exhibit 6 的柱：<code>新台币同比 − 美元同比</code>，单位是<b>百分点</b>，'
     '不是百分比。正值 = 新台币贬值把公司报出来的增速<b>抬高</b>了。'
     '⚠️ 它是两条同比<b>之差</b>，不是「营收里有多少来自汇率」；'
     '而且它的两条腿一条取公告值、一条是自算值（公司不公告美元同比），'
     '差额里含公司口径的四舍五入。'),

    ('觸發腿',
     '核对表最后两列（觸發腿 / 本月備註）说的是 MOPS 月营收申报表的'
     '「備註／營收變化原因說明」栏。那<b>不是</b>公司想写就写的自由备注栏，'
     '是一条有触发条件的<b>法定</b>披露：申报表脚注第 6 条要求本月营收<b>或</b>本年'
     f'累计营收较去年同期增减变动达 {_TRIG:.0f}% 以上者才须说明原因，'
     '「觸發腿」标的就是哪条腿越了线（單月／累計／兩者）。'
     '⚠️ 这一栏<b>空不等于公司没解释</b>，只等于当月两条腿都没到门槛；'
     '反过来<b>没触发却填了字</b>的，是常设的口径注，不能当增减原因引用。'),

    ('董事會核准資本支出',
     '<b>这不是 capex</b>：董事会当次会议核准的是未来资本项目的<b>授权额度</b>，'
     '钱在其后若干年才花出去。⚠️ 一次会议批的额度横跨多年、落在哪一年由<b>会议日期</b>'
     '决定 ⇒ 年度合计本身就是跳的，<b>不能</b>拿它与同年的现金资本支出对比，'
     '更不能按年换算。Exhibit 10 是逐次会议、Exhibit 11 是同一批额度的年内累计，'
     '两张都是<b>往前看的授权</b>，既不是已经花掉的钱，也不是月底存量。'
     '它来自董事会当日的 Form 6-K，比复述同一件事的月末 6-K 早约 40–45 天，'
     '所以它的最新点可以比月营收更靠前一个月。'),

    ('背書保證',
     '母公司为子公司自借自发的债务出具的担保，因此这条线是<b>海外建厂融资规模的代理'
     '变量</b>。本页有<b>两套数并存、永远不可拼接</b>：<b>在外余额</b>（来自月度 '
     'Form 6-K）是眼下实际还挂着的担保，Exhibit 16 与汇总表画的是它；'
     '<b>董事會核准數</b>（MOPS 的「至本月份累計餘額」）是董事会批出的<b>额度</b>，'
     '含尚未动用的部分 —— 两者<b>不是同一个东西</b>，'
     '缺口有多大是随月变的读数，见 Exhibit 16 图注与汇总表。Exhibit 17 把亚利桑那那一腿的两套数<b>折成美元</b>并排画'
     '（不折的话新台币升值会被读成「撤回担保」），两线之差就是已批准但还没动用的额度。'),

    ('遠期外匯未平倉',
     'MOPS 衍生性商品申报表「未沖銷契約」的契約總金額：<b>月底仍未平仓</b>的远期外汇'
     '合约<b>名目</b>金额，是一个<b>存量</b>。⚠️ <b>既不是当月成交量，也不是年初至今'
     '累计</b> —— 同一张表里紧挨着的「已沖銷契約」才是年初至今、每年一月归零，'
     '而两栏同名相邻，读错一栏整条序列作废。'
     '台积电以美元卖货、以新台币入账，柱高就是它已经提前卖成新台币的那部分美元。'),

    ('避险强度',
     '<code>遠期外匯未平倉名目 ÷ 月均营收</code>，读作「覆盖月数」。'
     '分母用 <b>TTM ÷ 12</b> 而不是当月营收：当月营收带着农历年与季末拉货的锯齿，'
     '拿一个月底存量去除一个锯齿状流量，等于把分母的噪声灌进比值。'
     '⚠️ <b>这是标尺，不是覆盖率</b>：远期避的是账上<b>已存在</b>的美元货币性资产'
     '（应收、美元现金），不是未来的销售 —— 读成「未来 N 个月的销售已锁定」是错的。'),

    ('边际成本 / 平均成本',
     'Exhibit 14 两条线的分工。<b>边际成本</b> = 最近一档新发 5 年期公司债的票面'
     '（今天再借要多少钱），它是一条<b>阶梯</b>：保持上一档的票面直到下一档发行，'
     '<b>不是月度报价</b> —— 长期不发债时它只是一个旧报价被拖着走，'
     '<b>不代表那些年都能按这个价借到钱</b>。'
     '<b>平均成本</b> = 在外新台币公司债的加权平均票面（历史存量的实际负担）。'
     '⚠️ 平均成本的升降不一定是利率在动：短券先到期、长券留下，'
     '光是这个<b>幸存者效应</b>就能把它抬上去，而期间没有任何一檔债被重定价。'
     '⚠️ 两条线与汇总表 <code>NT$ bond funding</code> 那两行画的都是<b>在外余额</b>，'
     '而且绝大部分月份<b>不是公司披露值</b>：MOPS 公司債月報表只留<b>滚动 3 个月</b>'
     '窗口，只有最近 3 个月直接来自月报表本身，更早的月份由逐檔发行辦法登记簿与'
     '还本时程<b>重建</b>，是推导值（年末以 Form 20-F 的逐檔表对账）。'),

    ('宝岛债',
     '在台湾发行、以<b>外币</b>计价的债券。本页的债券口径（Exhibit 14 的两条线、'
     'Exhibit 15 的到期墙与汇总表 NT$ bond funding 那两行）'
     '<b>一律只含新台币券，宝岛债全部剔除</b>'
     + (f'（现算：{_FORMOSA}）' if _FORMOSA else '')
     + '。剔除是因为它们在 20-F 的 domestic 那一行里与新台币券混在一起，'
       '并进来会同时打歪在外余额与加权平均票面；代价是 2020 年起的年末对账'
       '只能做到「残差 = 宝岛债名目 × 年末即期」这一步。'),

    ('到期墙',
     'Exhibit 15：把某一个月末的在外新台币本金按<b>实际还本时程</b>排进日历年。'
     '⚠️ <b>不是按到期日排</b> —— '
     + (f'那批 50/50 分次还本的券（现算 {_AMORT}）' if _AMORT else '分次还本的那几檔')
     + '在到期日<b>前一年</b>先还一半，只看到期日会把这一半记到晚一年的柱上。'
       '⚠️ 它<b>不是月度序列</b>，是那一份存量快照的前瞻切片：切分口径锚在<b>快照月</b>'
       '本身，不随月营收往前走而变；快照当年那根柱只含该年的<b>剩余</b>月份。'),
]


def _guidance_bridge(c):
    """brief 的第 5 句：季度指引桥。**TSMC 独有的跨源推导**。

    指引是**美元**、主序列是**新台币**，全页从不把两者接起来（页内没有指引图）。
    这里用公司自己披露的指引中值 × 公司自己假设的汇率，折出「本季剩余月份月均还需
    多少 NT$bn」—— 两个输入都是披露值、乘积是推导值（brief.py 的 R5），
    所以正文带「（推导值）」，并另给一个按已实现汇率重算的版本。

    重算用的参照汇率**优先取落在该季之内的已实现月份**，而且必须从原始 fx series 取，
    不能用对齐到营收月份的 fx_al：FRED 的月均汇率比营收早一个月发布，
    `fx.reindex(rev.index)` 恰好把这唯一一个「落在指引季之内的已实现观测」截掉，
    用被截掉后的「近三月」（那其实是上一季）去评价假设，会把结论说反。
    """
    import os
    ds, B, spec = c['ds'], c['B'], c['spec']
    i, cnq, mth, cur_bn = c['i'], c['cnq'], c['mth'], c['cur_bn']
    ALL, fx, fx_al = ds.all, ds.fx_raw, ds.fx
    qsum_bn, qcnt, fxq = ds.qsum, ds.qcnt, ds.fxq

    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'series')
    # series/ 在仓库根，spec 文件可能被放在 build/ 下 —— 走底座算好的路径最稳。
    import mrbase
    g = pd.read_csv(os.path.join(mrbase.SERIES, spec['guidance']['csv']))
    g['qlabel'] = [x[:4] + 'Q' + x[-1] for x in g['quarter']]
    g = g.set_index('qlabel')
    g_mid = (g['guide_low_usdbn'].astype(float) + g['guide_high_usdbn'].astype(float)) / 2
    g_act = pd.to_numeric(g['actual_rev_usdbn'], errors='coerce')
    lo, hi = g['guide_low_usdbn'].astype(float), g['guide_high_usdbn'].astype(float)
    gfx = g['guide_fx_ntd_per_usd'].astype(float)

    tq = next((q for q in g.index if not np.isfinite(float(g_act.get(q, np.nan)))), None)
    if not len(g.index) or (tq is not None and not B.need(g_mid.get(tq), gfx.get(tq))):
        return ''
    if tq is not None:
        qp = pd.Period(tq, freq='Q-DEC')
        k = int(qcnt.get(qp, 0))
        qtd = float(qsum_bn.get(qp, 0.0))
        need = float(g_mid[tq]) * float(gfx[tq])
        gf = float(gfx[tq])
        inq = [(p_, float(v)) for p_, v in fx.items()
               if p_.asfreq('Q-DEC') == qp and np.isfinite(float(v))]
        if inq:
            rfx = float(np.mean([v for _, v in inq]))
            ref = f'当季{"、".join(str(p_.month) for p_, _ in inq)}月已实现{rfx:.2f}'
        else:
            w = fx_al.values.astype(float)[max(0, i - 2):i + 1]
            rfx = float(np.nanmean(w))
            ref = f'当季暂无已实现月，{ALL[max(0, i - 2)].month}–{mth}月均值{rfx:.2f}'
        if k < 3:
            rem = (need - qtd) / (3 - k)
            alt = (float(g_mid[tq]) * rfx - qtd) / (3 - k)
            d1, d2 = rem / cur_bn - 1, alt / cur_bn - 1
            head5 = (f'与{tq}指引对表：中值按公司假设汇率{gf:.1f}折算，'
                     f'剩余{cnq(3 - k)}个月{"月均" if k < 2 else ""}需'
                     f'<b>NT${B.num(rem)}bn</b>（推导值），'
                     f'比本月{"高" if d1 >= 0 else "低"}{abs(d1) * 100:.1f}%；{ref}')
            # 两者相差不到 0.05 时印出来根本是同一个数（假设一位小数、实现两位），
            # 这时再把同一个百分比印第二遍就是自己跟自己打架。
            if abs(rfx - gf) < 0.05:
                return head5 + '，与假设基本持平。'
            return f'{head5}，按它算需{"高" if d2 >= 0 else "低"}{abs(d2) * 100:.1f}%。'
        der = qtd / float(fxq[qp])
        l_, h_ = float(lo[tq]), float(hi[tq])
        band = f'{B.usd(l_, 1)}–{B.usd(h_, 1)}bn'
        if h_ > l_ and l_ <= der <= h_:
            where = f'落在指引区间{band}的{(der - l_) / (h_ - l_):.0%}位置'
        elif der > h_:
            ov = (der / h_ - 1) * 100
            where = (f'贴着指引区间{band}上沿' if ov < 0.05
                     else f'高出指引区间{band}上沿{ov:.1f}%')
        else:
            un = (1 - der / l_) * 100
            where = (f'贴着指引区间{band}下沿' if un < 0.05
                     else f'低于指引区间{band}下沿{un:.1f}%')
        return (f'与{tq}指引对表：三个月已全部公布，按月营收折出的美元合计'
                f'<b>{B.usd(der, 1)}bn</b>（推导值，用该季实现均汇率{float(fxq[qp]):.2f}），'
                f'{where}。')
    lq = [q for q in g.index if np.isfinite(float(g_act.get(q, np.nan)))][-1]
    a_, l_, h_ = float(g_act[lq]), float(lo[lq]), float(hi[lq])
    if h_ > l_ and l_ <= a_ <= h_:
        where = f'落在指引区间的{(a_ - l_) / (h_ - l_):.0%}位置'
    elif a_ >= h_:
        where = f'高出指引区间上沿{(a_ / h_ - 1) * 100:.1f}%'
    else:
        where = f'低于指引区间下沿{(1 - a_ / l_) * 100:.1f}%'
    return (f'指引侧本轮无新区间可对：最近一个有实际值的{lq}{where}，'
            f'下季区间要等业绩会才有。')


SPEC = {
    'ticker': 'tsm',
    'name': 'TSMC',
    'tracker': 'TSMC Monthly Revenue Tracker',
    'title': '台积电 TSMC (2330.TW / TSM)：月度营收跟踪',
    'source': 'Source: TSMC monthly revenue reports; format after Goldman Sachs GIR',
    'source_zh': 'TSMC 官网 IR 月度营收公告（合并营收，NT$mn，未经会计师查核，'
                 '台湾法定次月 10 日前公布）',
    'csv': 'tsm.csv',

    # 唯一的官方披露字段。月营收 / 3MMA / QTD / YTD / 占 TTM 比重全部由它派生。
    'value': {'col': 'revenue_ntd_mn', 'div': 1000.0, 'label': 'NT$bn', 'sym': 'NT$',
              'dec': 1, 'raw_label': 'NT$mn', 'raw_dec': 0, 'zh': 'NT$ revenue',
              'ccy_zh': '新台币',
              # 新台币是 TSMC 的功能货币与表达货币，月值是原生记账数，逐年加总与年报相等。
              'summable': True},
    'official_yoy': 'yoy_pct',

    'fx': {
        'csv': 'tsm_fx.csv', 'col': 'ntd_per_usd', 'quote': 'NTD per USD',
        # 纯出处短句，不带「Exhibit source:」前缀 —— 前缀由底座在图脚那一处加，
        # 页尾说明里引用同一个串时不该跟着印一遍。
        # ⚠️ **主位必须是 H.10，不是 FRED。** 本仓从来没有、也不能从 FRED 取数 ——
        #    `fetch/tsm.py` 模块头逐字写着「FRED 在本机（含 cron 环境）连不通…改用
        #    EXTAUS 的**上游原始数据**」，实际抓的是 `federalreserve.gov/releases/h10/
        #    hist/dat00_ta.htm`，全文没有一处 fred.stlouisfed.org 请求。
        #    这个串同时出现在 Ex8 图脚、页尾「数据源」条与「汇率序列口径」条三处，
        #    写成 FRED 就是三处出处不实。共用同一份 series/tsm_fx.csv 的另外五家
        #    （ase/guc/mtk/nanya/umc）早就是 H.10 主位，只有本页曾把 FRED 摆在
        #    `Exhibit source:` 那个槽里。
        #    （数值上两者零偏差 —— 163 个月逐月相同，含 2013–2015 那 36 个月回补；
        #    错的只是「从哪个渠道拿的」，所以这是出处问题不是数据问题。）
        'src': '美联储 H.10 台湾地区日度牌价按月算术平均（该月全部有报价营业日，'
               '落库脚本 fetch/tsm.py；与 FRED 的 EXTAUS 同定义、同上游，'
               '在本仓已入库区间逐月相同）',
        'assumption': 'Assumption: NT$ converted at the month average NTD/USD rate '
                      '— an approximation',
        # ⚠️ per-ticker，不可继承。见文件头第 2 条：这句话搬到别家就是事实错误陈述。
        'usd_share_note': {
            'en': 'Roughly 70% of TSMC revenue is US-dollar denominated but reported '
                  'in NT$, so this rate moves the headline.',
            'zh': 'TSMC 约七成营收以美元计价却以新台币入账，所以这条线直接推动报表增速',
            'src': 'TSMC Annual Report / Form 20-F，"Quantitative and Qualitative '
                   'Disclosures About Market Risk — Foreign Currency Risk" 一节；'
                   'https://investor.tsmc.com/english/annual-reports'
                   '（占比逐年披露，须随最新一份 20-F 复核）',
        },
    },

    'window': {
        # 本轮用户要求：Ex2/3/4/5/6 的时间轴统一拉到 2016 起。
        # 各图**实际**首点由自己的 lag 决定，底座逐图现算并写进图注。
        'x_from': '2016-01',
        'heat_years': 9,
        'check_rows': 13,
    },

    'guidance': {'csv': 'tsm_guidance.csv'},
    'brief_extra': _guidance_bridge,

    # ── 非营收月度披露板块（Exhibit 10 起）─────────────────────────────────
    # 台积电按月申报的不只有营收：另有背書保證、資金貸與、衍生性商品、董監持股／設質、
    # 公司債月報表五项，加上 SEC 侧董事会当日 6-K 的核准資本支出。
    # 这三个钩子的实现、口径与数据全在 `_tsm_extra.py`，底座只管往哪儿插、编号怎么续。
    # ⚠️ 另外六家台股页**不能**照抄：它们没有一家申报董事會核准資本支出的英文披露，
    #    衍生性商品与背書保證的表式也各不相同（联电填「無」的两项台积电填的是实数）。
    'summary_extra': _tsm_extra.summary_rows,
    'summary_note': _tsm_extra.summary_note,
    'extra_exhibits': _tsm_extra.exhibits,

    # `breaks` 为空，且**不给 `continuity`**。
    #
    # 原来的 build/tsm.py 在页尾写死了「TSMC 月营收自 2016-01 起口径连续，未发生并表或
    # 重述」。那是一句关于公司历史的事实断言，需要出处（年报合并范围附注 / 重述公告），
    # 而它当时既没有出处、也没有任何构建期检验撑着 —— 逐年月度加总与年报合并营业收入
    # 是否相等，这份 CSV 里没有年报数可比，算不出来。
    # 底座对 `continuity` 的要求是「要么带 URL 出处，要么整个不给」，所以这里不给：
    # 页面会只陈述「本页 spec 未登记断点」这个中性事实，并明说它不等于「没发生过」。
    # 这是本轮唯一一处**主动收回**的表述 —— 收回一句无源断言不是信息损失。
    #
    # ⚠️ 若日后核到出处（例如 20-F 的合并范围附注逐年确认无追溯重述），
    #    就把它写成 'continuity': {'zh': …, 'url': …}，页面会自动改口。

    'format_source':
        '版式仿 Goldman Sachs GIR 台股月营收报告（「Hon Hai (2317.TW)」与 '
        '「Wistron (3231.TW)」的 Exhibit 1-2，外加 GS HKEX 深度的超长历史层）',

    # 页顶「名词释义」。选词判断与「有意不收哪些词」写在 _GLOSSARY 上方那一段注释里。
    'glossary': _GLOSSARY,

    'notes': [
        '<b>指引区间只在页顶 brief 出现</b>：那里的美元指引来自季度业绩说明会，'
        '季度营收口径含非月营收项，与月营收累加值之间的差额同时含汇率与口径差，'
        '不可直接相减 —— 所以指引桥只报「剩余月份月均还需多少 NT$bn」，'
        '不与页内任何图对读。页内没有指引图。',
        _DAYS_NOTE,
        # ↓ 这一条从旧 data/tsm.js 的页尾原样带过来（只删掉两处会随窗口过期的实测数：
        #   「25 根柱的 band 20px」与「本月 +27.1pp」——band 现在由 mrwin 现算写进 Ex6 图注，
        #   当月读数现算在 headline 里）。
        #   它**只对 TSMC 成立**：PDF 版是 build/build_tsm.py（TSMC 专属的 matplotlib
        #   生成器），另外六家根本没有「PDF 版」这回事，所以这段话住在本 spec 里，
        #   一个字都不许回到底座 —— 回去就会印到六家页面上，凭空断言一个不存在的东西。
        '<b>网页版与 PDF 版的已知差异</b>：本页有一份同源的 PDF 版 '
        '（<code>build/build_tsm.py</code>，GS 台股月营收版式）。'
        '(1) PDF 长历史图末端有一个红色虚线椭圆圈出最近 3 个月，网页引擎无此图元，已省略 —— '
        '两张长历史图改为按 PDF 的 n_label 在末点标出读数，绝对水平不至于只能靠刻度目测；'
        '(2) 月营收柱图由 <code>bar_line_dual</code> 换成 <code>gs_bar</code>，'
        '为的是把 PDF 有、网页一直没有的柱值标签与 y/y 末点读数补回来，'
        '代价是柱色从深藏青变成 gs_bar 固定的浅蓝；'
        '(3) 汇率贡献图在 PDF 里是 <code>gsx.lvl_bar</code>，网页对应的 <code>gs_bar</code> '
        '纵轴强制自 0 起会把负值柱画到画布外，故柱仍用单组 <code>grouped_bars</code>；'
        '(4) 汇率贡献图的柱顶不逐根标数值（PDF 版在窗口 >14 期时同样只标每隔一根）。',

        '<b>汇率贡献不能按 pp 直读</b>：页面各处印的「汇率贡献 = NT$ y/y − US$ y/y」'
        '是<b>百分点差</b>，恒等于 <code>汇率同比 ×（1 + 美元同比）</code> —— '
        '同一幅新台币贬值，在高增速期印出来的 pp 数会被放大 (1+美元同比) 倍。',
    ],

    'footer': '图表与派生算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
              '仅供个人研究，不构成投资建议',
}
