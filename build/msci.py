# -*- coding: utf-8 -*-
"""MSCI Inc. —— 挂钩 MSCI 指数的 ETF 月度 AUM：网页看板的数据生成器。

把 build/build_msci.py（matplotlib → PDF）里的每一张 exhibit 逐张移植成
window.DASH 的一个 exhibit 对象，写出 data/msci.js。图序、编号、标题、图注、
口径断点全部照搬原 deck；标题里的当期数字随最新月重算，不写死。

数据源（只读 series/，不读 build/data/）：
    series/msci.csv       month, aum_eop_usdbn, aum_avg_usdbn（2008-12 起）
    series/fee_rates.csv  MSCI 的 asset_based_fee_effective_rate_annualized（bp，季度）
                          与 asset_based_fee_revenue / disclosed_period_end_basis_point_fee_etf

口径提示（与原 deck 的模块 docstring 同源）：
    这是第三方 ETF 的资产规模（客户端产品），不是 MSCI 自身营收；但它由 MSCI 官方
    按月披露，且直接决定 asset-based fee 收入 —— 该收入近似 = 季度平均 AUM x 基点费率，
    故 Exhibit 5 用季度平均而非期末值。

幂等：payload 里不放构建日期（只写文件首行注释），窗口只由数据本身决定 ——
      短窗口图钉 2016-01 这个日历起点、右端到数据最新月，长历史图取全序列，
      核对表从最新月倒推 13 个月；不用随机数、不依赖当前时间决定内容
      —— 重复跑除首行外逐字节相同。
"""
import csv
import datetime
import json
import os
import re

import axisfmt
import brief as B    # 顶部 brief 的规则库（R1-R6），只算事实、不出文字
import numpy as np   # 只用于口径对照那一段的统计量（标准差 / 相邻月跳变）
import payload_guard
import pctile        # 3Y %ile 的唯一实现，全站共用（各写各的正是同一序列两页判定相反的原因）
import yoy as Y      # 同比口径的唯一实现（build/yoy.py）：本页的口径选择要拿它实测出来

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')

SRC = ('Source: MSCI IR, AUM in ETFs linked to MSCI equity indexes; '
       'format after Goldman Sachs GIR')

MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# ────────────────────────────── 月份/季度小工具 ──────────────────────────────
def mi(ym):
    """'YYYY-MM' → 绝对月序号，方便做加减与差分。"""
    y, m = ym.split('-')
    return int(y) * 12 + int(m) - 1


def ym(i):
    return f'{i // 12:04d}-{i % 12 + 1:02d}'


def mlab(s):
    """'2026-06' → 'Jun-26'（同 gsx.mlab 的 %b-%y）。"""
    y, m = s.split('-')
    return f'{MON[int(m) - 1]}-{y[2:]}'


def qof(s):
    """'2026-06' → '2026Q2'（同 pandas Period 的 str）。"""
    y, m = s.split('-')
    return f'{y}Q{(int(m) - 1) // 3 + 1}'


def qi(q):
    """'2026Q2' → 绝对季序号。"""
    y, k = q.split('Q')
    return int(y) * 4 + int(k) - 1


def qname(j):
    """绝对季序号 → '2026Q2'（qi 的逆运算，用来现算「缺哪几个季度」）。"""
    return f'{j // 4:04d}Q{j % 4 + 1}'


def qlab_month(q):
    """'2023Q3' → 该季末月份 '2023-09'（原 deck 把季度费率挂在季末月上）。"""
    y, k = q.split('Q')
    return f'{int(y):04d}-{int(k) * 3:02d}'


# ────────────────────────────── 格式化（一律 Python 侧） ──────────────────────────────
# 负零（'-0.0%'、'-0'、'-$0.0'）是四舍五入的产物而不是数据：一整片两位数里冒出一个
# 「-0」，读者会停下来想这是不是缺失值（tsm Ex12、exchanges Ex8 都被人眼审查挑出来过）。
# 本页当前数据没有命中，但格式化口径应当先立在这里，不等下个月的数据来触发。
_NEGZERO = re.compile(r'^-(\$?)(0(?:[.,]0+)?)(\D*)$')


def nz(s):
    """把「四舍五入后等于零却带负号」的展示串去掉负号；其余原样返回。"""
    m = _NEGZERO.match(s)
    return m.group(1) + m.group(2) + m.group(3) if m else s


def f(v, d=1):
    return nz(f'{v:,.{d}f}')


def sgn_pct(v, d=1):
    """带正负号的百分比；同 gsx 的 f'{v:+.1f}%'。"""
    return nz(f'{v:+.{d}f}%')


def pp_txt(v):
    """gsx._pp：绝对值 < 2 用一位小数，否则整数。"""
    return nz(f'{v:+.1f}%' if abs(v) < 2 else f'{v:+.0f}%')


def R(x, nd=6):
    return None if x is None else round(float(x), nd)


def RL(a, nd=6):
    return [R(v, nd) for v in a]


# ────────────────────────────── 读数据 ──────────────────────────────
def read_msci():
    path = os.path.join(SERIES, 'msci.csv')
    months, eop, avg = [], {}, {}
    with open(path, encoding='utf-8') as fh:
        for row in csv.DictReader(fh):
            k = row['month'].strip()
            if not k:
                continue
            months.append(k)
            eop[k] = float(row['aum_eop_usdbn'])
            avg[k] = float(row['aum_avg_usdbn'])
    months.sort()
    # 逐月连续是后面所有 y/y、m/m、季度汇总的前提；不连续就直接失败，不静默补洞
    for a, b in zip(months, months[1:]):
        if mi(b) - mi(a) != 1:
            raise SystemExit(f'series/msci.csv 月份不连续：{a} → {b}')
    return months, eop, avg


def read_rates():
    """MSCI 的季度费率与季度实际 asset-based fee 收入（供图注引用）。"""
    path = os.path.join(SERIES, 'fee_rates.csv')
    bp, rev, disc = {}, {}, {}
    with open(path, encoding='utf-8') as fh:
        for row in csv.DictReader(fh):
            if row['company'] != 'MSCI':
                continue
            q = row['period'].replace('-', '')
            m, v, u = row['metric'], float(row['value']), row['unit']
            if m == 'asset_based_fee_effective_rate_annualized':
                if u != 'bp_of_etf_aum':
                    raise SystemExit(f'MSCI 费率单位意外：{u}')
                bp[q] = v
            elif m == 'asset_based_fee_revenue':
                if u != 'USD_mn':
                    raise SystemExit(f'MSCI ABF 收入单位意外：{u}')
                rev[q] = v
            elif m == 'disclosed_period_end_basis_point_fee_etf':
                disc[q] = v
    if not bp:
        raise SystemExit('series/fee_rates.csv 里没有 MSCI 的有效费率')
    return bp, rev, disc


# ────────────────────────── 顶部 brief（headline 之下、Exhibit 1 之上） ──────────────────────────
def compose_brief(months, EOP, AVG, brk):
    """MSCI 页顶部的 ~300 字数据总结（payload 的 `brief` 字段）。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R3 日历护栏 / R4 单位恒等 /
    R5 标注 / R6 有效位），那边只算事实，句子在这里拼 —— 措辞是口径的一部分，属于各家自己。
    每个数字都当场从序列算，**一处硬编码都没有**：读数、排名、出现次数下个月重跑都会自己变。

    ═══ 分寸 ═══
    以 `build/ibkr.py::compose_brief()` 为准：四句话四个层次，每句一个意思。本页的四层是
    规模（两条口径各自的位置）/ 基数（上月读数把这个环比顶成了什么样）/ 口径背离（月末快照
    与月均积分劈叉，费基跟的是后者）/ 标注（新高含金量 + 推导值 + 口径断点）。
    回撤深度、收复用时、「第几快」、组合出现次数这类统计**已经越线**，不写 —— 它们让这段
    读起来像研究报告摘要而不是一段导读。

    ═══ 与本页 2026-08 同比口径改造的关系（移植时的口径适配）═══
    远端写这一段时页尾还没有「同比口径逐处点名」那条 note；本地已把全页定为
    **每一处都是点对点（单月）同比**（理由在页尾 note 里逐条实测，没有一张图用
    12 个月滚动口径）。适配照 schw / ibkr 的先例：
      · s2 引用的同比标「单月」（§6.1 第 2 条的正文版）—— 本页图上、汇总表、核对表
        全是同一口径，标注不是为了区分两种口径，是让 brief 与全页措辞统一，
        读者拿它对 Exhibit 2 的金线与汇总表 y/y 列能逐格对上。
      · 「只看环比会误读成趋势反转」说的是**环比的读法**（R2 的本职），不是拿单月
        同比另立一条趋势 —— 对存量序列，点对点同比就是本页实测选定的口径
        （页尾 note ①：滚动均值只在拐点上滞后半年，把窗口拉到 2016 之后实测出的
        反号月份全部落在 2018 / 2020 那几个拐点上，不改变本页对存量用点对点的判定）。
      · 本页核心算术「费收 ≈ 平均 AUM × 有效费率」已判定**费收不改滚动口径**
        （换了口径，Exhibit 11 的缺口会把口径差读成费率压缩）。本段引的只有
        AUM 两列的水平、排名与单月环比同比，**不引隐含费收与费率的任何读数** ——
        哪天要引，三者必须同口径（全部点对点），否则同一段里就会出现
        `single.caliber_audit` 专拦的那种互斥断言。

    ═══ MSCI 独有，别家不能照抄 ═══
      · 本页只有两列，且**两列都是水平值**：月末时点（eop）与当月月均（avg）。它们不是
        「当月合计量」，所以 **R3 日历护栏在这里根本不成立** —— 再除一次交易日会造出一个
        不存在的修正（brief.py 头部列的第一个坑）。同理这页没有任何分子/分母对，R4 也不用。
      · 这一家真正的口径背离是**同一个量的两种时间口径**：月末是快照、月均是月内积分，
        而 asset-based fee 计提在**月均**那条线上（页尾 notes 第 2 条）。只读 headline 里
        月末那半句会把一个仍在扩张的费基读成收缩。别家的背离是「总量涨/单位量跌」，
        这里不是，句子不能照搬。这一层占的是模板里「日历」那一格 —— 本页没有日历效应。
      · **两条口径的差只能说到「月内节奏」为止**：这是第三方 ETF 的资产规模，环比里同时
        含市场涨跌与净流入两部分，而本序列不拆分（Exhibit 3 的图注就是这么写的）。所以
        「不是资金掉头 / 不是净流出」这类话本段一律不许出现 —— 两列水平值推不出资金流向，
        写了就是替读者拆了一次它自己声明不拆的东西。措辞上也要绕开「掉头」这类会被读成
        资金流向的词：句子只说「趋势反转」这种关于**读数本身**怎么读的话。
      · 口径断点：AUM 是随市值走的第三方资产规模，没有交易日、没有公司重述，唯一的历史
        断点是 2019-04 的数据供应商切换（Bloomberg → Refinitiv），而全样本排名跨在它两侧
        —— 所以末句必须点出「更早月份不完全同口径」，这句话是本页专有（断点滚出序列时
        该从句自动消失）。「（推导值）」同理：排名与次数都是本站按公司披露的两列水平值
        算的，为省字删掉标注不是精简，是不诚实。
      · T3 的处理：两列都**不是**单调序列（逐月上升占比约 0.65 / 0.70，低于 is_monotonic
        的 0.9 阈值），故「创新高」在这里是信息不是噪音；但含金量要按当场算出的新高月占比
        折价（≤1/3 才叫稀缺），而不是把「又创新高」当结论、也不是写死「要打折」。
        「创新高」的判据全段只有一处：`pos_txt()` 里的 `rank == 1`（rank_of 只数严格大于者，
        故它与末句 nh 计数的 `>=` running-max 是同一个约定）。**不再走 peak_scan**：它的
        skip_monotonic 会在早期截断段把月均整列跳过，于是 at_peak 说「没创新高」而同页
        rank==1 说「创新高」—— 一页两个「峰值」定义，正是 brief.py 警告的那种漂移。
      · 反向指标（T2）在本页没有：AUM 与费基都是越高越好，故各处排名一律正向。
      · 「所处区间」为什么用**全样本排名**而不是分位：Exhibit 1 的 3Y %ile 只看近 36 个月，
        且这两行常被 `pctile.py` 判为「近两年恒定在区间端点、无区分度」而留空 —— 于是整页
        没有任何一处给出位置。排名（第几高、`B.top_pct` 的前百分之几）与「新高月占比」
        是本页唯一可用的取位工具。
      · 与 headline / Exhibit 1 的重叠：读数与环比同比允许出现，但只能作为**这一句的论据**
        （样板 ibkr 的第二句就是这么写的：「环比从 6 月 190.3 千户跌 30.7%…同比 +42.6%」）。
        禁的是无论据的罗列 —— 把表里的格子逐个念一遍那叫复述式摘要，不叫导读。
    """
    n, i = len(months), len(months) - 1
    eop = [EOP[k] for k in months]
    avg = [AVG[k] for k in months]

    # ── R2：两条口径各自的基数护栏。conflict=True 时必须说基数，否则一个由上月极值造出来的
    #    环比会被读成趋势反转 —— 本页 headline 印的正是那个环比。
    be, ba = B.base_effect(eop, i), B.base_effect(avg, i)

    def pos_txt(rank):
        """名次 → 位置措辞。全段唯一的「创新高」判据（见 docstring 的 T3 段）：rank == 1。

        「创新高」与「第 1（前 1%）」是同一件事，两种说法并存就是一页两个定义；
        名次一律走 B.top_pct（向上取整，不能四舍五入到一个更好看的档）。
        """
        return '创全样本新高' if rank == 1 else f'居{n}个月第{rank}（{B.top_pct(rank, n)}）'

    # ── s1：规模。两条口径各自的位置并排给 —— 「月末没创、月均创了」本身就是本月的信息，
    #    谁高谁低一律由 rank 决定，不预设方向。
    #    月末那条线后面挂一个位置补语，两种情形互斥、只占一个槽：
    #      没创新高 → 峰值停在哪（样板 ibkr 第一句的「峰值停在 5、6 月」）。峰值就是上月时
    #                 不写 —— 下一句的基数说明会点名同一个月，写两遍是冗余。
    #      创了新高 → 已经连着创了几个月（连续 1 个月不算「连续」，不写）。
    #    两者都由 rank==1 这**同一个判据**分流，argmax 与 hi_flag 的 running-max 是同一个
    #    约定（`>=`），不是第二个「峰值」定义。
    hi_flag, rm0 = [], eop[0] - 1
    for v in eop:
        rm0 = max(rm0, v)
        hi_flag.append(v >= rm0)
    streak = 0
    for f in reversed(hi_flag):
        if not f:
            break
        streak += 1
    pk = max(range(n), key=lambda j: eop[j])
    if be['rank'] == 1:
        tail = f'（连续第{streak}个月）' if streak >= 2 else ''
    else:
        tail = '' if pk == i - 1 else f'，峰值停在{mlab(months[pk])}'
    s1 = (f'{mlab(months[i])}月末 AUM <b>{B.usd(eop[i], 1)}bn</b>，{pos_txt(be["rank"])}{tail}；'
          f'当月平均 AUM {B.usd(avg[i], 1)}bn，{pos_txt(ba["rank"])}。')

    # ── s2：基数护栏（R2）。上月的**读数与名次**就是基数说明本身，故先给它再给本月环比；
    #    「只看环比会误读」这半句只在 conflict（环比同比反号）时出现，不是每月都挂。
    #    同比标「单月」：见 docstring「口径适配」一段 —— 与汇总表 y/y 列、Exhibit 2 金线同口径。
    # 「全样本」而不是再写一遍 {n} 个月：s1 刚给过样本长度，同一段里重复报基数是噪音。
    hi = '全样本最高月' if be['prev_is_max'] else f'全样本第{be["prev_rank"]}高月'
    if not B.need(be['mm']):
        s2 = ''
    else:
        s2 = (f'{mlab(months[i - 1])}的{B.usd(eop[i - 1], 1)}bn是{hi}，'
              f'本月环比{"跌" if be["mm"] < 0 else "涨"}{abs(be["mm"]) * 100:.1f}%'
              + ('。' if not B.need(be['yy']) else
                 f'，单月同比{B.pct(be["yy"])}，<b>只看环比会误读成趋势反转</b>。'
                 if be['conflict'] else f'，单月同比{B.pct(be["yy"])}。'))

    # ── s3：本页的口径背离（占模板里「日历」那一格）。月末是时点快照、月均是月内积分，
    #    费基计提在月均那条线上，所以两者反号的月份必须点名。
    #    分母是**有环比的**月份数 n-1，不是 n —— 首月无环比，可发生的机会只有 n-1 次。
    #    结论只能收到「月内节奏」为止：两列水平值不含资金流，说资金去向是越界。
    #    两支的结构必须对称：**方向 → 落点 → 基准频次**。落点（读不读得反）是这一句真正
    #    要讲的事，不能只在反向那一支有；频次垫底，是给读者判断「每月要不要检查这件事」的
    #    基准，不是结论。写「本月是/不是其中之一」这类话没必要 —— 方向词已经说完了。
    mm_n = n - 1
    opps = [k for k in range(1, n)
            if (eop[k] < eop[k - 1]) != (avg[k] < avg[k - 1])]
    if mm_n <= 0 or not B.need(be['mm'], ba['mm']):
        # 首月没有环比，「背离/同向」无从谈起 —— 只报前提，不报关系。
        s3 = '费基计提在月均那条线上，不在月末快照上。'
    elif (be['mm'] < 0) != (ba['mm'] < 0):
        s3 = (f'费基计提的是月均那条线：<b>当月平均环比{B.pct(ba["mm"])}、与月末反向</b>，'
              f'只读月末会把仍在{"扩张" if ba["mm"] > 0 else "收缩"}的费基读反；'
              f'这样反向的月份在有环比的{mm_n}个月里共{len(opps)}次'
              f'（占{B.pct(len(opps) / mm_n, sign=False)}）。')
    else:
        s3 = (f'费基计提的是月均那条线：当月平均环比{B.pct(ba["mm"])}、与月末同向，'
              f'读月末快照不会读反；这样反向的月份在有环比的{mm_n}个月里共{len(opps)}次'
              f'（占{B.pct(len(opps) / mm_n, sign=False)}）。')

    # ── s4：给「新高」打折（T3），并标推导值与口径断点（R5）。
    #    「打折 / 稀缺」由当场算出的新高月占比决定，阈值与 B.quant 的 1/3 对齐，
    #    否则会出现「只有 5 个月是新高」配「要打折」这种自相矛盾。
    #    计数直接数 s1 那张 hi_flag，不另起一个 running-max 循环 —— 同一页两处「新高」
    #    各算各的，正是 brief.py 警告的那种定义漂移。
    nh = sum(hi_flag)
    s4 = (f'另注：序列随市值走，{n}个月里{B.quant(nh, n, "个月")}是当时新高，'
          f'「新高」{"要打折" if nh / n > 1 / 3 else "确实稀缺"}；'
          '排名与次数均为本站按 MSCI 披露的月末/月均两列推算（推导值）'
          # 判据是 `brk in months`（本段描述的那条序列）而不是 `brk in EOP`（整本字典）：
          # 两者在正常构建时重合，但断点若还没进入序列，用字典判会印出一句凭空的口径警告。
          + (f'，且跨{mlab(brk)}数据源切换，更早月份不完全同口径。'
             if brk in months else '。'))

    return B.render([s1, s2, s3, s4])


def main():
    months, EOP, AVG = read_msci()
    BP_Q, REV_Q, DISC_Q = read_rates()
    LATEST = months[-1]
    li = mi(LATEST)

    # ── 派生序列 ──
    diff = {k: EOP[k] - AVG[k] for k in months}          # 期末 − 月均：月内走势方向
    mom = {}                                             # 月末 AUM 的 m/m（%）
    for k in months[1:]:
        p = ym(mi(k) - 1)
        mom[k] = (EOP[k] / EOP[p] - 1) * 100

    # ── 量→收入桥：asset-based fee = 平均 AUM x 有效基点费率 / 12 ──
    # 季度费率 → 月度：当季各月用该季费率；最新已知季之后沿用最后一个值（这是假设，写进图注）。
    qs = sorted(BP_Q, key=qi)
    last_q, last_bp = qs[-1], BP_Q[qs[-1]]
    rate_m = {}
    for k in months:
        q = qof(k)
        if q in BP_Q:
            rate_m[k] = BP_Q[q]
        elif qi(q) > qi(last_q):
            rate_m[k] = last_bp                          # ffill：最新季之后沿用
    abf = {k: AVG[k] * 1000.0 * rate_m[k] / 10000.0 / 12.0 for k in rate_m}
    abf_months = sorted(abf)
    # 有几个月落在最新已知季度之后（那几个月的费率是沿用值 = 真估计），本次是几就写几
    n_ffill = sum(1 for k in abf_months if qof(k) not in BP_Q)
    BR_NOTE = ('Assumption: monthly asset-based fee = month average AUM x the effective rate / 12 '
               f'({last_q} = {last_bp:.3f}bp, held flat after). The rate is back-solved from '
               'reported revenue, so closed quarters are an allocation, not an estimate.')

    # ── 费率的期间披露（Exhibit 7 / 8 / 10 / 11 与核对表的「有效费率」列共用）──
    # AUM 每月往前走、费率每季才更新一次，所以「最新一两个月用的是上一季费率」是这页的
    # 常态口径而不是 bug —— 但图上看不出来，读者有权知道当期到底吃的哪一季。
    # 整段全部从数据现算：季度号写死的话，下个季度这句话就变成假话。
    DQ = qof(LATEST)                                     # 本页数据最新月所在季度
    lag_q = qi(DQ) - qi(last_q)                          # 费率落后数据月所在季度几个季度
    # 沿用段的起点：第一个「所在季度还没有披露费率」的月份（n_ffill=0 时为 None）
    ffill_from = next((k for k in abf_months if qof(k) not in BP_Q), None)
    # 过期判据：季报总在季末之后才发，故「费率落后 1 个季度」是正常节奏（本季末月的费率
    # 要等下季才披露）；比上一季还老才算过期，此时必须显式说，不能让读者自己去数。
    STALE = lag_q > 1
    miss_qs = [qname(j) for j in range(qi(last_q) + 1, qi(DQ) + 1)]
    FEE_Q_BODY = (
        f'费率取 <b>{last_q}</b> 的公司披露值（{last_bp:.3f}bp），'
        f'本页 AUM 数据截至 {mlab(LATEST)}（{DQ}）—— 费率按季披露、AUM 按月披露，两者天然错位。'
        + (f'因此 {mlab(ffill_from)} 起的 {n_ffill} 个月沿用 {last_q} 的费率，'
           '这一段的隐含值是估计而不是分摊。'
           if n_ffill else
           f'本轮费率已覆盖到最新月所在的 {DQ}，没有任何月份沿用更早季度的费率。')
        + (f' ⚠️ <b>费率已过期</b>：尚未更新至 {"、".join(miss_qs)}，本图仍用 {last_q} '
           f'的费率，落后本页数据月所在季度 {lag_q} 个季度（正常节奏是落后 1 季以内）。'
           if STALE else ''))
    FEE_Q_CN = '<b>费率期间</b>：' + FEE_Q_BODY          # 图注里用，自带小标题
    FEE_Q_EN = (
        f'Quarterly fee rate: latest disclosed is {last_q} at {last_bp:.3f}bp, while AUM here runs '
        f'through {mlab(LATEST)} ({DQ})'
        + (f'; the {n_ffill} month(s) from {mlab(ffill_from)} carry the {last_q} rate forward.'
           if n_ffill else
           f' — the rate already covers {DQ}, so no month carries an older quarter’s rate.')
        + (f' WARNING: the rate has not been updated to {"/".join(miss_qs)}; it lags the data '
           f'quarter {DQ} by {lag_q} quarters.' if STALE else ''))

    # ── 窗口 ──────────────────────────────────────────────────────────────
    # 短窗口图的起点钉在 2016-01（日历常量），右端跟着数据最新月走。
    #
    # 为什么从「最新月倒推 25 个月 / 14 个季度」改成钉一个日历起点：25 个月装不下一个
    # 完整的市场周期 —— 2018 的回撤、2020 的疫情坑、2022 的熊市全在窗口之外，读者拿到的
    # 「+37% YoY」没有任何可比的历史坐标。钉 2016 之后这一层全部进图，与 Exhibit 4
    # 的全历史图构成「十年 vs 全样本」两个尺度，而不是「两年 vs 全样本」的断层。
    #
    # 它是**日历常量而不是相对偏移**：窗口随时间自然变长，这是口径本身要求的
    # （用户指定「从 2016 年开始」），不是忘了倒推。核对表仍是 13 个月的相对窗口 ——
    # 那是「最近一年逐月核对」的工具，不是趋势图。
    #
    # 不适用本口径的两张：Exhibit 4 本来就画全历史（2008-12 起），
    # Exhibit 9 是逐年路径图（x 轴是 Jan..Dec，窗口由「最近 6 年」定义，没有连续时间轴）。
    #
    # 费率派生的四张（Exhibit 7 / 8 / 10 / 11）以前够不到 2016 —— 有效费率序列只回溯到
    # 2019Q1。2026-08 把 fetch/rates_msci.py 的抓取起点从 2020-04 下压到 2016-04 并补上
    # 老版式解析（Table 5 三列收入 + Table 7 老 AUM 表），费率序列现已自 2015Q1 起，
    # 这四张因此和其余各图一样真的从 2016 起。2015 那四季不是多余的：Exhibit 8 / 10 的
    # 同比要往前借 4 个季度、Exhibit 11 的同比要借 12 个月，没有它们 2016 年会是空的。
    WIN0 = '2016-01'                                     # 短窗口图的起点（含）
    QWIN0 = qof(WIN0)                                    # 同一个起点的季度写法（'2016Q1'）
    if WIN0 < months[0]:
        raise SystemExit(f'series/msci.csv 起于 {months[0]}，晚于窗口起点 {WIN0}')
    WM = [k for k in months if k >= WIN0]                # 月度图窗口：2016-01 → 最新月
    XLM = [mlab(k) for k in WM]
    # x 轴标签步长：127 个月逐月标必然叠成一团，取 12 → 每年 1 月一个刻度，读起来就是年轴。
    # 季度图同理取 4（每年 Q1 一个刻度）。两者都对齐窗口首格，故首格必被标出。
    MSTEP, QSTEP = 12, 4
    W13 = [ym(li - k) for k in range(12, -1, -1)]        # 核对表 13 个月
    XL13 = [mlab(k) for k in W13]
    XL_LONG = [mlab(k) for k in months]

    def yoy(d, k):
        p = ym(mi(k) - 12)
        return (d[k] / d[p] - 1) * 100 if p in d else None

    # ══════════════════════════ Exhibit 1：汇总表 ══════════════════════════
    cur, prv, yag = LATEST, ym(li - 1), ym(li - 12)

    # 3Y %ile 一律走 build/pctile.py：判据（回放近 24 个月，≥70% 钉在极值就留空）是**口径**，
    # 口径只能有一处定义。本页原来那份「逐月差 ≥0 占比 ≥90% 就留空」的本地实现拦不住
    # 月末 / 月均这两行 —— 它们上下波动过得了 90% 那关，可分位常年钉 100，印出来是噪音。
    blank_why = []

    def sum_row(label, d, keys, dec=1, money='$', mode='ratio'):
        c, p1, p12 = d[cur], d[prv], d[yag]
        cells = [{'v': money + f(c, dec)}, {'v': money + f(p1, dec)}, {'v': money + f(p12, dec)}]
        for a, b in ((c, p1), (c, p12)):
            if mode == 'abs':
                v = a - b
                # 负号写在货币符号外面（$-59.5 读起来像负的货币单位）
                cells.append({'v': ('+' if v >= 0 else '-') + money + f'{abs(v):,.{dec}f}',
                              'cls': 'pos' if v > 0 else 'neg'})
            elif b == 0 or a * b < 0:                     # 分母为 0 / 两期异号 → 比率无意义
                cells.append({'v': ''})
            else:
                v = (a / b - 1) * 100
                cells.append({'v': sgn_pct(v), 'cls': 'pos' if v > 0 else 'neg'})
        ser = [d[x] for x in keys]                     # 按月升序的整条序列，cur 是最后一格
        txt_, cls_ = pctile.cell(ser, keys.index(cur))
        cells.append({'v': txt_, 'cls': cls_} if txt_ else {'v': ''})
        if not txt_:
            blank_why.append((label, pctile.why_blank(ser)))
        return {'label': label, 'cells': cells}

    # 先把行算出来（sum_row 会往 blank_why 里登记留空原因），表注再引用它 ——
    # 靠 dict 字面量的求值顺序来保证「先 rows 后 note」太脆，显式分两步。
    srows = [
        {'kind': 'group', 'label': 'ETF AUM linked to MSCI indexes'},
        sum_row('Month-end AUM ($bn)', EOP, months),
        sum_row('Average AUM for the month ($bn)', AVG, months),
        # 期末−月均会在零附近变号，百分比变化没有意义 —— 这一行的差异用绝对额（$bn）
        sum_row('Month-end less monthly average ($bn)', diff, months, mode='abs'),
    ]
    blank_txt = ('本轮留空：'
                 + '；'.join(f'{lab}（{why}）' for lab, why in blank_why) + '。'
                 ) if blank_why else '本轮各行均未触发留空，分位照算。'
    summary = {
        'title': f'MSCI-linked ETF AUM summary — {mlab(LATEST)}',
        'heads': [mlab(cur), mlab(prv), mlab(yag), 'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': srows,
        'note': ('Average AUM is the fee-relevant measure: asset-based fees accrue on average assets, '
                 'not the month-end snapshot. All figures are MSCI estimates and include linked ETNs '
                 '(&lt;1% of AUM). 3Y %ile = 当月读数在最近 36 个月里高于多少百分比的观测，'
                 '判据与留空规则由全站唯一实现 <code>build/pctile.py</code> 给出：'
                 '回放最近 24 个月，若 ≥70% 的月份分位都钉在 100 或 0，说明这一列对该行没有区分度，留空。'
                 + blank_txt +
                 '「期末 − 月均」一行会在零附近变号，故 m/m 与 y/y 用绝对额（$bn）而非百分比变化。'),
    }

    ex = []

    # ══════════════════════ 口径断点（2019-04 数据供应商切换） ══════════════════════
    # 定义提到这里、排在所有 exhibit 之前：窗口拉到 2016 之后，这条断点第一次落进**短窗口图**
    # 的窗口里（原来 25 个月 / 14 个季度的窗口整段都在断点右侧，所以从来不用画）。
    # 规矩 6：跨口径的序列不许画成一条连续的线。
    BRK = '2019-04'
    BRK_Q = qof(BRK)                # '2019Q2' —— 季度图上缝合月落在这一季
    brk_i = months.index(BRK) if BRK in EOP else None
    BRK_LAB = '数据源切换'          # 整页中文，断点标签不再写英文 'data provider switch'
    # 线画在 2019-04，语义是「从这一期起与左侧不可比」，而 2019-04 本身就是缝合月 ——
    # 原文案写「May-19 起改用 Refinitiv」，把 2019-04 排除在两侧之外，与线的位置自相矛盾。
    BRK_SRC = ('Apr-2019 is the stitched month: the month-end figure is already Refinitiv while the '
               'monthly average splices 4/1-4/25 Bloomberg with 4/26-4/30 Refinitiv. Earlier months '
               'are MSCI estimates built on Bloomberg data; from May-2019 the series is fully Refinitiv.')
    BRK_CN = ('⚠️ 红色虚线画在 <b>2019-04</b>，语义是「从这一期起与左侧不可比」：MSCI 的数据供应商在 '
              '2019 年 4–5 月由 Bloomberg 换成 Refinitiv，而 <b>2019-04 这一格本身就是缝合月</b> —— '
              '月末值已是 Refinitiv，月均值是 4/1–4/25 Bloomberg 加 4/26–4/30 Refinitiv 拼出来的，'
              '2019-05 起才全程 Refinitiv。线左侧、线上这一格、线右侧是三段口径，不可直读为一条连续序列。')
    # 短窗口图上的简版（长历史图 Exhibit 4 仍用上面的全文，它是这条断点的主场）
    BRK_CN_M = ('⚠️ 红色虚线是 <b>2019-04</b> 的数据供应商切换（Bloomberg → Refinitiv），'
                '语义是「从这一期起与左侧不可比」。2019-04 本身是缝合月：月末值已是 Refinitiv、'
                '月均值由两家拼出，2019-05 起才全程 Refinitiv。跨线读趋势请记得左右不同源。')
    BRK_CN_Q = (f'⚠️ 红色虚线是 <b>{BRK_Q}</b>（含 2019-04 那个缝合月）的数据供应商切换'
                '（Bloomberg → Refinitiv），语义是「从这一季起与左侧不可比」。')
    NO_BRK_CN = ('（口径断点 2019-04 已不在本图窗口内，故本图没有画断点线；'
                 '数据供应商切换的说明见页尾「口径与方法说明」。）')

    def add_brk(exd, keys, at, cn):
        """窗口 keys 跨过断点 at 时，给这张图挂上断点线与说明；否则原样返回。

        判据是「断点两侧在窗口里都有数据」—— `keys.index(at) == 0` 说明窗口正好从断点
        那一期开始，左侧一格都没有，画出来只是一条贴着左边框的装饰线，没有信息
        （Exhibit 11 自 2020-01 起，连 at 都不在窗口里，同样跳过）。
        src_extra 用**追加**：Exhibit 7 / 8 / 10 自己已经有一段费率期间说明，覆盖会丢。
        """
        if at not in keys or keys.index(at) == 0:
            return exd
        exd['break_at'] = keys.index(at)
        exd['break_label'] = BRK_LAB
        exd['src_extra'] = (exd.get('src_extra', '') + ' ' + BRK_SRC).strip()
        exd['note'] = exd.get('note', '') + cn
        return exd

    # ══════════════════════════ Exhibit 2：月末 AUM 水平柱 ══════════════════════════
    v2 = [EOP[k] for k in WM]
    yoy2, mom2 = yoy(EOP, LATEST), (EOP[LATEST] / EOP[ym(li - 1)] - 1) * 100
    # 次轴同比取代 12 个月均线：原 deck 这张图走 gsx.lvl_bar，其 docstring 明写
    # 「次轴画的是同比而不是滚动均线 —— 均线只是把柱子再平滑一遍、不带新信息」。
    yoy2_s = [yoy(EOP, k) for k in WM]                  # 窗口内各月的 y/y（%）
    ex.append(add_brk({
        # 通栏：窗口拉到 2016 之后是 127 根柱，半栏（≈455px 绘图区）每根不到 2.1px，
        # 柱图退化成一片竖纹。通栏（≈1056px）每根 5px 上下，柱高才重新读得出来。
        # 同页 Exhibit 3 跟着通栏，它俩是「柱看水平 / 线看动能」的一对，不能一宽一窄。
        'n': 2, 'kind': 'gs_bar', 'fmt': 'f0c', 'label_fmt': 'f0c', 'xlabels': XLM,
        'full': True, 'xstep': MSTEP, 'xrot': 90,
        'title': (f'Month-end AUM in MSCI-linked ETFs — ${f(EOP[LATEST], 0)}bn in {mlab(LATEST)}, '
                  f'{pp_txt(yoy2)} YoY and {pp_txt(mom2)} MoM'),
        'ylab': '$bn', 'ylab2': '% y/y', 'legend': 'Month-end AUM',
        'values': RL(v2),
        'yoy': {'name': 'y/y (RHS)', 'color': 'GOLD', 'values': RL(yoy2_s), 'yfmt': 'pct0'},
        # 原来这里有 'mom_txt'：GS deck 的 m/m 椭圆气泡。窗口拉到 127 根柱之后它必须去掉 ——
        # 引擎按 Xc(n-4) 定位气泡、Xc(n-2) 定位箭头（charts.js:1286），那是照短窗口设的：
        # 25 根柱时气泡离右边框还有 16% 的画布，127 根柱时只剩 3%，实测直接压在右轴的
        # 「80%」刻度上。这不是配一个偏移量能治的（band 会随窗口继续变），而气泡说的
        # 「-0.1% m/m」本页已经有三处：本图标题末句、页顶 headline、以及 Exhibit 3 整条 m/m
        # 曲线。删的是重复，不是信息。engine 侧不动 —— ibkr / schw 的 gs_bar 还走这条路径。
        'note': ('第三方 ETF 的资产规模（客户端产品），不是 MSCI 自身营收；由 MSCI 官方按月披露。'
                 '金色线是<b>右轴同比</b>（%），不是 12 个月均线 —— 均线只是把柱子再平滑一遍、'
                 '不带新信息，同比才回答「相对去年这个月是好是坏」（同原 deck 的 gsx.lvl_bar）。'
                 '数值为 MSCI 估算，含挂钩 ETN（&lt;1% of AUM）。'),
    }, WM, BRK, BRK_CN_M))

    # ══════════════════════════ Exhibit 3：月末 AUM m/m ══════════════════════════
    ex.append(add_brk({
        'n': 3, 'kind': 'gs_line', 'fmt': 'pct1', 'xlabels': XLM,
        'full': True, 'xstep': MSTEP, 'xrot': 90,     # 与 Exhibit 2 同宽，见那里的说明
        'title': (f'Month-end AUM, m/m change — {mlab(LATEST)} {sgn_pct(mom[LATEST])}, '
                  f'{XLM[0]} 以来 {len(WM)} 个月里 {sum(1 for k in WM if mom[k] > 0)} 个月为正'),
        'ylab': '% m/m', 'values': RL([mom[k] for k in WM]),
        'note': ('与 Exhibit 2 成对：柱看水平、线看动能。'
                 '月末快照的环比含市场涨跌与净流入两部分，本序列不拆分。'),
    }, WM, BRK, BRK_CN_M))

    # ══════════════════════════ Exhibit 4：全历史（月末） ══════════════════════════
    # 断点滚出窗口就优雅降级：brk_i = None → 不给 break_at，图注里也不提那条线。
    # 本页这张长历史图画的是**全序列**，2019-04 只要还在 CSV 里就一定在窗口内；
    # 会滚出去的是取尾窗的图（lpla 就是在这种守卫上硬失败的），所以这里不抛异常。
    ex4 = {
        'n': 4, 'kind': 'lines', 'x': 'long', 'full': True, 'height': 300,
        'fmt': 'f0c', 'label_fmt': 'f0c', 'xstep': max(1, len(months) // 14), 'xrot': 90,
        # zero_base：不给的话引擎走 y0 = min − 极差×5%，那是一次没有标注的隐性截轴，
        #   在长历史图上会凭空放大增幅（同 gsx.long_line 的 set_ylim(0, max*1.16)）。
        # end_label：deck 的 n_label —— 长历史图上唯一的绝对水平锚点。这张图原来
        #   一个数据标签都没有，读者只能对着几百 $bn 一格的刻度目测。
        'zero_base': True, 'end_label': True,
        'title': (f'Full AUM history since {mlab(months[0])} — from ${f(EOP[months[0]], 0)}bn to '
                  f'${f(EOP[LATEST], 0)}bn ({EOP[LATEST] / EOP[months[0]]:.1f}x over '
                  f'{(li - mi(months[0])) / 12:.0f} years)'),
        'ylab': '$bn',
        'series': [{'name': 'Month-end AUM', 'color': 'NAVY', 'values': RL([EOP[k] for k in months])}],
        'note': BRK_CN if brk_i is not None else NO_BRK_CN,
    }
    if brk_i is not None:
        ex4['break_at'] = brk_i
        ex4['break_label'] = BRK_LAB
        ex4['src_extra'] = BRK_SRC
    ex.append(ex4)

    # ══════════════════════════ Exhibit 5：季度平均 AUM ══════════════════════════
    qmap = {}
    for k in months:
        qmap.setdefault(qof(k), []).append(AVG[k])
    qkeys = sorted(qmap, key=qi)
    qavg = {q: sum(qmap[q]) / len(qmap[q]) for q in qkeys}
    QW = [q for q in qkeys if q >= QWIN0]
    q_yoy = []
    for q in QW:
        p = qkeys[qkeys.index(q) - 4] if qkeys.index(q) >= 4 else None
        q_yoy.append((qavg[q] / qavg[p] - 1) * 100 if p and qavg[p] else None)
    n_last_q = len(qmap[QW[-1]])
    ex.append(add_brk({
        'n': 5, 'kind': 'qtr_bar', 'fmt': 'f0c', 'label_fmt': 'f0c', 'xlabels': QW,
        'xstep': QSTEP, 'xrot': 90,
        'title': (f'Quarterly average AUM (fee-relevant basis) — {QW[-1]} ${f(qavg[QW[-1]], 0)}bn, '
                  f'{q_yoy[-1]:+.0f}% YoY'),
        'ylab': '$bn', 'legend': 'Quarterly average AUM',
        'values': RL([qavg[q] for q in QW]),
        'partial_months': n_last_q, 'qtr_months': 3,
        'line': {'name': 'y/y (RHS)', 'color': 'GREEN', 'values': RL(q_yoy), 'yfmt': 'pct0'},
        'src_extra': ('Quarterly mean of the monthly average-AUM series; '
                      'drives asset-based fee revenue'),
        'note': ('asset-based fee 按平均资产计提，故这里用季度平均而非期末值。'
                 f'末季 {QW[-1]} 已含 {n_last_q} 个月'
                 + ('（已满季，可与往季直读）。' if n_last_q >= 3 else
                    '（未满季，柱为浅蓝，右轴 y/y 已作废，不可与完整季直读）。')),
    }, QW, BRK_Q, BRK_CN_Q))

    # ══════════════════════════ Exhibit 6：月末 vs 月均 ══════════════════════════
    ex.append(add_brk({
        'n': 6, 'kind': 'lines_endlabels', 'fmt': 'f0c', 'xlabels': XLM,
        'xstep': MSTEP, 'xrot': 90,
        'title': (f'Month-end vs. average AUM — {mlab(LATEST)} 月末 ${f(EOP[LATEST], 0)}bn '
                  f'高于月均 ${f(AVG[LATEST], 0)}bn ${f(diff[LATEST], 1)}bn'
                  if diff[LATEST] >= 0 else
                  f'Month-end vs. average AUM — {mlab(LATEST)} 月末 ${f(EOP[LATEST], 0)}bn '
                  f'低于月均 ${f(AVG[LATEST], 0)}bn ${f(-diff[LATEST], 1)}bn'),
        'ylab': '$bn',
        'series': [
            {'name': 'Month-end AUM', 'color': 'NAVY', 'values': RL([EOP[k] for k in WM])},
            {'name': 'Average AUM for month', 'color': 'MBLUE', 'values': RL([AVG[k] for k in WM])},
        ],
        'note': ('两条线的差（期末 − 月均）是月内走势的方向指示：正 = 月末高于月均（月内上行）。'
                 'asset-based fee 计提在月均那条线上，不是月末那条。'
                 f'窗口拉到 {XLM[0]} 之后两条线在多数月份贴在一起（{len(WM)} 个月里，'
                 f'差额中位数占月末值的 '
                 f'{sorted(abs(EOP[k] - AVG[k]) / EOP[k] for k in WM)[len(WM) // 2] * 100:.1f}%），'
                 '要看这个差本身请读 Exhibit 1 汇总表的「月末 − 月均」一行与核对表同名列 ——'
                 '本图给的是「差在什么水平上发生」的背景，不是差的读数。'),
    }, WM, BRK, BRK_CN_M))

    # ══════════════════════════ Exhibit 7：隐含 asset-based fee（月） ══════════════════════════
    # 窗口口径同 Exhibit 2（2016 起）。费率序列现已自 qs[0] = 2015Q1 起（抓取起点下压后
    # 补齐，见窗口那一段的说明），所以这条隐含序列在 2016-01 之前也有值，切窗口切得实。
    WMa = [k for k in abf_months if k >= WIN0]
    XLMa = [mlab(k) for k in WMa]
    yoy7 = (abf[LATEST] / abf[ym(li - 12)] - 1) * 100
    # 同 Exhibit 2：次轴同比取代 12 个月均线（原 deck 走 gsx.lvl_bar）
    yoy7_s = [((abf[k] / abf[ym(mi(k) - 12)] - 1) * 100) if ym(mi(k) - 12) in abf else None
              for k in WMa]
    ex.append(add_brk({
        # 91 根柱：半栏每根约 3.1px，与 Exhibit 2 同一个问题，同样走通栏。
        'n': 7, 'kind': 'gs_bar', 'fmt': 'f1', 'label_fmt': 'f1', 'xlabels': XLMa,
        'full': True, 'xstep': MSTEP, 'xrot': 90,
        'title': (f'Implied asset-based fee revenue — {mlab(LATEST)} ${abf[LATEST]:.1f}mn, '
                  f'{yoy7:+.0f}% YoY'),
        'ylab': '$mn / month', 'ylab2': '% y/y', 'legend': 'Implied asset-based fee',
        'values': RL([abf[k] for k in WMa]),
        'yoy': {'name': 'y/y (RHS)', 'color': 'GOLD', 'values': RL(yoy7_s), 'yfmt': 'pct0'},
        'src_extra': BR_NOTE + ' ' + FEE_Q_EN,
        'note': ('<b>Implied</b>：不是公司披露的月度值。' + BR_NOTE +
                 f' 本图与本页其余短窗口图同起点（{mlab(WMa[0])}）：费率序列自 {qs[0]} 起，'
                 f'隐含序列因此覆盖 {mlab(abf_months[0])} 起共 {len(abf_months)} 个月，'
                 '够得到窗口起点。'
                 '金色线是<b>右轴同比</b>（%），不是滚动均线。' + FEE_Q_CN),
    }, WMa, BRK, BRK_CN_M))

    # ══════════════════════════ Exhibit 8：有效费率（季度） ══════════════════════════
    # 窗口口径同 Exhibit 5（2016Q1 起）。费率全序列自 qs[0] = 2015Q1 起，比窗口还早
    # 4 个季度 —— 正好够下面 bp_yoy() 给窗口第一格算出同比，不会开头空一年。
    QS8 = [q for q in qs if q >= QWIN0]
    bpq = [BP_Q[q] for q in QS8]
    XLbp = [mlab(qlab_month(q)) for q in QS8]
    # 序列本身的刻度就是 bp（CSV unit=bp_of_etf_aum），所以两个 bp 相减得到的同比差额
    # 单位仍是 bp，不是 pp。标成 pp 会把幅度放大 100 倍（-0.49bp 读成 -49bp）。
    def bp_yoy(q):
        j = qs.index(q)
        return BP_Q[q] - BP_Q[qs[j - 4]] if j >= 4 else None
    yoy8_s = [bp_yoy(q) for q in QS8]                     # 逐季基点差（bp），次轴用
    yoy8 = yoy8_s[-1]
    ex.append(add_brk({
        # 原 deck 用 dec=2，本页原来退到 f1，理由是「FMT 里没有 f2」—— 那条注释早已过时
        # （assets/charts.js:105 有 f2）。f1 会把 3.984/4.022/3.995/3.956 四个季度全印成
        # 「4.0」、3.747/3.722 全印成「3.7」，而这张图的全部信息量就是这 0.7bp 的压缩。
        'n': 8, 'kind': 'gs_bar', 'fmt': 'f2', 'label_fmt': 'f2', 'xlabels': XLbp,
        'xstep': QSTEP, 'xrot': 90,
        'title': (f'Effective asset-based fee rate — {last_q} {last_bp:.3f}bp, '
                  f'{yoy8:+.2f}bp YoY（近 {len(QS8)} 个季度 {bpq[0]:.2f}bp → {bpq[-1]:.2f}bp）'),
        'ylab': 'bp of average ETF AUM', 'ylab2': 'y/y（基点差，bp）',
        'legend': 'Effective rate (quarterly)',
        'values': RL(bpq),
        # pct_series 型序列的同比是基点差；右轴刻度就是 bp，故 yfmt 用 f2 而不是 pp/pct
        'yoy': {'name': 'y/y（bp 差，RHS）', 'color': 'GOLD', 'values': RL(yoy8_s), 'yfmt': 'f2'},
        'note': ('Reported asset-based fee revenue / average MSCI-linked ETF AUM. '
                 'This is the bridge\'s real uncertainty: AUM compounded but the rate compressed from '
                 f'{bpq[0]:.2f}bp to {bpq[-1]:.2f}bp over the {len(QS8)} quarters shown. '
                 f'The period-end ETF fee of {DISC_Q[last_q]:.2f}bp is lower as it also covers '
                 f'non-ETF licensing. 本图窗口同本页其余短窗口图，自 {QS8[0]} 起共 {len(QS8)} 季'
                 f'（费率全序列自 {qs[0]} 起共 {len(qs)} 季，窗口外的 {qi(QWIN0) - qi(qs[0])} 季'
                 '不画，但右轴的同比要借它们才算得出窗口第一格）。'
                 '柱子从 0 起（柱图不许截基线），所以 4.1bp → 3.4bp 这段压缩在柱高上看不出来 —— '
                 '要看压缩请读<b>金色的右轴线</b>：它画的是逐季基点差，'
                 f'最近一季 {yoy8:+.2f}bp。y 轴刻度就是 bp，故同比用<b>基点差（bp）</b>，'
                 '不是「百分比的百分比变化」，也不是百分点（1pp = 100bp）；'
                 'x 轴标的是各季末月份。逐季精确值（bp）：'
                 + '、'.join(f'{q} {BP_Q[q]:.3f}' for q in QS8) + '。' + FEE_Q_CN
                 + f'本图最右一根柱就是 {last_q}，右侧没有画到的月份不是数据缺失，'
                 '而是该季费率还没披露。'),
        'src_extra': FEE_Q_EN,
    }, QS8, BRK_Q, BRK_CN_Q))

    # ══════════════════════════ Exhibit 9：逐年 AUM 路径 ══════════════════════════
    years = sorted({k[:4] for k in months})[-6:]
    yseries = []
    for y in years:
        vals = [EOP.get(f'{y}-{m:02d}') for m in range(1, 13)]
        yseries.append({'name': y, 'values': RL(vals)})
    cy = years[-1]
    cy_last = max(int(k[5:]) for k in months if k[:4] == cy)
    ex.append({
        'n': 9, 'kind': 'year_lines', 'fmt': 'f0c', 'label_fmt': 'f0c',
        'xlabels': MON, 'series': yseries, 'highlight': len(years) - 1,
        'title': (f'AUM path by year — {cy} 年 {cy_last} 月末 ${f(EOP[LATEST], 0)}bn，'
                  f'较 {years[-2]} 年同月 {pp_txt(yoy(EOP, LATEST))}'),
        'ylab': '$bn',
        'note': ('画的是月末水平值本身（不是年初至今累计），红线 = 当年。'
                 f'{cy} 年只到 {MON[cy_last - 1]}（{cy_last} 月），其后为空。'
                 '2019-04 的数据供应商切换落在图外的早期年份，这 6 年内不含断点。'),
    })

    # ══════════════════════════ Exhibit 10：隐含 ABF（季度） ══════════════════════════
    aq = {}
    for k in abf_months:
        aq.setdefault(qof(k), []).append(abf[k])
    aqk = sorted(aq, key=qi)
    aqsum = {q: sum(aq[q]) for q in aqk}
    AQW = [q for q in aqk if q >= QWIN0]      # 同 Ex8：2016Q1 起 ∩ 可得 = 全序列
    aq_yoy = []
    for q in AQW:
        j = aqk.index(q)
        p = aqk[j - 4] if j >= 4 else None
        aq_yoy.append((aqsum[q] / aqsum[p] - 1) * 100 if p and aqsum[p] else None)
    n_last_aq = len(aq[AQW[-1]])
    ex.append(add_brk({
        'n': 10, 'kind': 'qtr_bar', 'fmt': 'f0c', 'label_fmt': 'f0c', 'xlabels': AQW,
        'xstep': QSTEP, 'xrot': 90,
        'title': (f'Implied asset-based fee by quarter — {AQW[-1]} ${f(aqsum[AQW[-1]], 0)}mn'
                  + (f'，实际披露 ${REV_Q[AQW[-1]]:.0f}mn'
                     if AQW[-1] in REV_Q else '，该季尚未披露实际值')),
        'ylab': '$mn / quarter', 'legend': 'Implied asset-based fee',
        'values': RL([aqsum[q] for q in AQW]),
        'partial_months': n_last_aq, 'qtr_months': 3,
        'line': {'name': 'y/y (RHS)', 'color': 'GREEN', 'values': RL(aq_yoy), 'yfmt': 'pct0'},
        'src_extra': ('Quarterly sum of the monthly bridge; the latest bar is quarter-to-date '
                      'if the quarter is incomplete. ' + FEE_Q_EN),
        'note': ('<b>Implied</b>：月度桥的季度合计。已收官季度可与公司披露的 asset-based fee 收入对表 —— '
                 + '；'.join(f'{q} 隐含 ${aqsum[q]:.0f}mn vs 实际 ${REV_Q[q]:.0f}mn'
                             f'（差 {(aqsum[q] / REV_Q[q] - 1) * 100:+.1f}%）'
                             for q in AQW[-4:] if q in REV_Q)
                 + '。差异来自月均 AUM 与公司季均口径的细微出入，不是费率错。' + FEE_Q_CN),
    }, AQW, BRK_Q, BRK_CN_Q))

    # ── 原 Exhibit 11「Average AUM since Dec-08」已删（2026-08）────────────────────
    # 它与 Exhibit 4 画的是同一个量的两种时间口径（月末 vs 月均），在**全历史尺度上是同一张图**：
    # 实测两条 path 的垂直距离中位数 0.74px、p90 3.44px、最大 8.17px，而绘图区高 230px、
    # 线宽本身就 1.6px —— 过半的月份两条线连线宽都拉不开（相关系数 0.9993，18 年 21.4x vs 22.0x）。
    # 月末与月均的差是**月度分辨率上的信息**（Exhibit 6 + 汇总表「月末 − 月均」行 + 核对表在讲），
    # 不是十八年尺度上的信息，占两个通栏位置画同一条曲线是重复而不是双口径。
    # 留月末不留月均：本页所有长视角图（Exhibit 2 / 3 / 9 / 12）与 headline、汇总表都以月末打头，
    # 且月均恰是被 2019-04 缝合污染更重的一条；费基的长视角已由 Exhibit 5 的 43 个季度承担。
    # 也没有合并成一张双线全历史图 —— 按上面的像素数，画出来会是一条线却声称两条，比删掉更糟。
    # 其后各图顺延一号（原 12 → 11、原 13 → 12、核对表原 14 → 13）。

    # ══════════════════════════ Exhibit 11：隐含费收 y/y ══════════════════════════
    # 原 deck 用 win=25，但 y/y 在窗口第一格（比 12 个月前）无值，matplotlib 那边就是空点；
    # 网页的 gs_line 走平滑曲线，吃不了 null，所以直接取 24 个有值的点 —— 画面内容一致。
    yw = [k for k in abf_months if ym(mi(k) - 12) in abf and k >= WIN0]
    yv = [(abf[k] / abf[ym(mi(k) - 12)] - 1) * 100 for k in yw]
    # 平均 AUM 的同比要**画在同一张图上**：本图标题说的是「费收增速慢于平均 AUM 增速」，
    # 只画费收那一条，读者没有任何办法验证这句话，也看不出缺口是在扩大还是在收敛 ——
    # 而那个缺口正是本页的核心算术（费收 ≈ 平均 AUM × 有效费率）里费率压缩的那一项。
    # 同窗口、同口径（都是点对点单月同比），所以两条线可以逐格相减。
    av = [yoy(AVG, k) for k in yw]
    aum_yoy = yoy(AVG, LATEST)
    gap = [a_ - b_ for a_, b_ in zip(yv, av)]          # 缺口（pp）= 费率压缩那一项
    # 费率序列补到 2015Q1 之后，abf 自 2015-01 起，同比让掉 12 个月仍落在 2016-01，
    # 所以本图窗口与其余短窗口图对齐，2019-04 的断点也回到了窗口内（add_brk 会画）。
    ex.append(add_brk({
        # 改成双线（原来是单线 gs_line）：见上面 av 那段的理由。
        # 换 kind 的代价是没有了 gs_line 的逐点数值标签 —— 两条线各标一遍 127 个点本来
        # 也读不了，而 lines_endlabels 给的两端读数正好回答「起点什么样、现在什么样」。
        # 附带好处：gs_line 的首点标签居中落在 Xc(0)、band 一小就压进左轴刻度栏
        # （实测半栏下「10.5%」压刻度「20」5.9px），而 lines_endlabels 的端点标签有
        # 自己的一列（引擎给 M.l 多留了 30px），这条冲突从结构上就没有了。
        # 通栏保留：127 个点 × 2 条线，半栏挤不开。
        'n': 11, 'kind': 'lines_endlabels', 'fmt': 'pct1',
        'xlabels': [mlab(k) for k in yw],
        'full': True, 'xstep': MSTEP, 'xrot': 90,
        'title': (f'Implied fee revenue vs. average AUM, y/y — {mlab(LATEST)} 费收 '
                  f'{sgn_pct(yv[-1])} vs 平均 AUM {sgn_pct(aum_yoy)}，'
                  f'缺口 {gap[-1]:+.1f}pp'),
        'ylab': '% y/y',
        'series': [
            # 颜色沿用 Exhibit 6 的分工：NAVY = 本图主角，MBLUE = 平均 AUM。
            # 平均 AUM 在这一页从头到尾都是 MBLUE，两张图可以对着看。
            {'name': 'Implied fee revenue (y/y)', 'color': 'NAVY', 'values': RL(yv)},
            {'name': 'Average AUM (y/y)', 'color': 'MBLUE', 'values': RL(av)},
        ],
        'src_extra': ('Both lines are point-to-point y/y on the same window, so the vertical '
                      'distance between them is the effective-rate effect. '
                      + FEE_Q_EN),
        'note': ('<b>两条线的垂直距离就是有效费率那一项</b>：本页的核心算术是'
                 '「费收 ≈ 平均 AUM × 有效费率」，所以深蓝（费收同比）低于中蓝（平均 AUM 同比）'
                 '多少，就是费率压缩吃掉了多少增长（费率本身见 Exhibit 8）。'
                 '两条线同窗口、同口径（都是点对点单月同比），可以逐格相减。'
                 f'{mlab(LATEST)}：费收 {sgn_pct(yv[-1])} vs 平均 AUM {sgn_pct(aum_yoy)}，'
                 f'缺口 {gap[-1]:+.1f}pp。'
                 # 「差额就是费率压缩」这句原文案不精确，改这张图时一并纠正：
                 # abf = AVG × rate ⇒ (1+费收同比) = (1+AUM同比) × (1+费率同比)，
                 # 精确的费率同比是两条曲线的**比值**，不是差。两者在增速大的时候差得不小
                 # （本轮 -10.9pp vs -8.0%），印错一个读者会拿去对 Exhibit 8 却对不上。
                 f'注意<b>缺口（pp）不等于费率的同比</b>：由 abf = 平均 AUM × 费率 得'
                 f'（1 + 费收同比）=（1 + AUM 同比）×（1 + 费率同比），'
                 f'精确的费率同比是两条曲线的<b>比值</b>而不是差 —— {mlab(LATEST)} 为 '
                 f'{((1 + yv[-1] / 100) / (1 + av[-1] / 100) - 1) * 100:+.1f}%，'
                 f'而图上看到的垂直缺口是 {gap[-1]:+.1f}pp。缺口用来看趋势（在扩大还是收敛），'
                 '要精确的费率读数请看 Exhibit 8。'
                 f'窗口内缺口从 {gap[0]:+.1f}pp 走到 {gap[-1]:+.1f}pp，'
                 f'{sum(1 for g in gap if g < 0)}/{len(gap)} 个月为负（即费收跑输 AUM）。'
                 f'本图自 {mlab(yw[0])} 起，与本页其余短窗口图同起点：隐含序列自 '
                 f'{mlab(abf_months[0])} 起（费率覆盖 {qs[0]} 起），同比让掉 12 个月之后仍够得到。'
                 + FEE_Q_CN),
    }, yw, BRK, BRK_CN_M))

    # ══════════════════════════ Exhibit 12：m/m 热力矩阵 ══════════════════════════
    # 行窗口同页面口径：2016 年起。原来写的是「最近 11 个年度」，本轮数据下恰好也是
    # 2016–2026 —— 但那是巧合，明年就会滑成 2017 起，与其余各图不再对齐。
    hyears = [y for y in sorted({k[:4] for k in mom}) if y >= WIN0[:4]]
    matrix = [[R(mom.get(f'{y}-{m:02d}')) for m in range(1, 13)] for y in hyears]
    ex.append({
        'n': 12, 'kind': 'heat_matrix', 'full': True,
        'title': (f'Month-end AUM m/m change (%) — {mlab(LATEST)} {sgn_pct(mom[LATEST])}；'
                  f'{hyears[0]}–{hyears[-1]} 共 '
                  f'{sum(1 for r in matrix for v in r if v is not None and v > 0)} 个月为正、'
                  f'{sum(1 for r in matrix for v in r if v is not None and v < 0)} 个月为负'),
        'rows': hyears, 'cols': MON, 'matrix': matrix,
        'fmt': 'pct1', 'reverse': False, 'legend': 'Month-end AUM m/m (%)',
        'row_head': '年', 'cell_h': 19,
        'src_extra': 'Green = AUM rose, red = AUM fell',
        'note': ('色标取全部有限值的 5–95 分位，一两个离群月不会把整表压平。'
                 '2019-04 的供应商切换落在矩阵内部，但热力矩阵没有连续 x 轴，画不了断点线 —— '
                 '读 2019 那一行时请记得左右两侧口径不同。'),
    })

    # ══════════════════════════ 核对表 ══════════════════════════
    trows = []
    for k in W13:
        trows.append({
            'xl': mlab(k),
            'eop': f(EOP[k], 1),
            'avg': f(AVG[k], 1),
            'diff': nz(f'{diff[k]:+,.1f}'),
            'mom': sgn_pct(mom[k]) if k in mom else None,
            'rate': f'{rate_m[k]:.3f}' if k in rate_m else None,
            'abf': f(abf[k], 1) if k in abf else None,
        })
    table = {
        'n': 13, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）', 'idx': '月份',
        'cols': [['月末 AUM（$bn）', 'eop'], ['当月平均 AUM（$bn）', 'avg'],
                 ['月末 − 月均（$bn）', 'diff'], ['月末 AUM m/m（%）', 'mom'],
                 ['有效费率（bp，季度值）', 'rate'], ['隐含 ABF（$mn，推导）', 'abf']],
        'rows': trows,
    }

    # ══════════════════════════ 口径与方法说明 ══════════════════════════
    # ── 轴刻度收口（必须排在 notes 之前）────────────────────────────────────
    # 轴刻度小数位：引擎默认格式器把 2.5 印成「3」、把 0.25 步长整列印成重复/错值，
    # 判据与算法见 build/axisfmt.py（与 build/single.py 共用同一份）。
    # **位置很要紧**：axisfmt 还会给「柱图型出现负值」的图补 ycap/yfloor，
    # 而下面的口径说明里有若干句是现读 payload 的 —— 要读到最终结果，不能读中间态。
    axisfmt.fix_all(ex)

    # ── 同比口径盘点：本页全部用点对点同比，理由要拿本页自己的序列实测 ──────────
    # ⚠️ 不许写「存量不能做滚动」这种一般性说辞：12 个月滚动**均值**同比对存量在数值上
    # 完全正确（Σ12/Σ12′ ≡ 均值比），不能说的只是把它叫「合计」（12 个月末快照相加不指代
    # 任何东西）。所以这里真的把两种口径都算出来、对齐月份后比一遍，再决定用哪个。
    def _cal(seq_map, keys, kind, win):
        """两种同比在**共同月份**上的统计。

        `keys` 给的是图上那个窗口，但同比必须在**全历史**上算完再切窗 —— 切完再算的话
        窗口最前 12（滚动是 24）期永远是空的，量出来的是切法不是口径。
        `win` 因此只切统计范围，不切算法输入。
        """
        allk = sorted(seq_map)
        s = [seq_map[k] for k in allk]
        a = Y.mom_yoy(s, kind).values.astype(float)
        b = (Y.ttm_mean_yoy(s, kind) if kind == Y.STOCK else Y.ttm_yoy(s, kind)) \
            .values.astype(float)
        inwin = np.array([k in set(win) for k in allk])
        m = np.isfinite(a) & np.isfinite(b) & inwin
        aa, bb = np.where(m, a, np.nan), np.where(m, b, np.nan)
        def sd(x):
            return float(np.nanstd(x, ddof=1)) if np.isfinite(x).sum() >= 2 else float('nan')
        def mj(x):
            d = np.abs(np.diff(x))
            return float(np.nanmax(d)) if np.isfinite(d).any() else float('nan')
        return {'n': int(m.sum()), 'sd_mom': sd(aa), 'sd_ttm': sd(bb),
                'mj_mom': mj(aa), 'mj_ttm': mj(bb),
                'opp': [(allk[i], float(a[i]), float(b[i]))
                        for i in np.flatnonzero(m & (a * b < 0))]}

    _CAL_AUM = _cal(EOP, WM, Y.STOCK, WM)       # Exhibit 2 画出来的那个窗口
    _CAL_ABF = _cal(abf, WMa, Y.FLOW, WMa)      # Exhibit 7 画出来的那个窗口（隐含费收是流量）

    notes = [
        '<b>这不是 MSCI 的营收。</b>本页画的是<b>第三方</b>挂钩 MSCI 指数的 ETF 资产规模（客户端产品）；'
        '它由 MSCI 官方按月披露，且直接决定 asset-based fee 收入，故可用作月度抢跑季报的高频量。',
        'Average AUM 才是费率相关口径：asset-based fee 按<b>平均</b>资产计提，不是月末快照。'
        'Exhibit 5 因此用季度平均而非期末值。'
        # 原 Exhibit 11 是月均的全历史线，已删（与 Exhibit 4 在全历史尺度上是同一张图，
        # 两条线的垂直距离中位数不到 1px）。删了之后要告诉读者月均这条线现在在哪儿看，
        # 否则会当成漏掉了一张图。
        f'<b>月均这条口径去哪儿看</b>：Exhibit 6 的浅蓝线（{mlab(WM[0])} 起 {len(WM)} 个月，'
        f'与月末逐月对照）、Exhibit 5 的季度平均（{QW[0]} 起 {len(QW)} 季），'
        '以及汇总表与核对表的「当月平均 AUM」列。'
        '本页不再单画一张月均的全历史线 —— 在十八年的尺度上它与 Exhibit 4 的月末线'
        '几乎完全重合（两条线的垂直距离中位数不到 1px，相关系数 0.999），'
        '两条口径的差是<b>月度分辨率上的信息</b>，不是长历史尺度上的信息。',
        '所有数字均为 MSCI 估算值，且包含挂钩 ETN（占 AUM &lt;1%）；MSCI 每月中旬发布上一月数据。',
        '⚠️ <b>口径断点 2019-04（数据供应商切换）</b>：MSCI 在 2019 年 4–5 月把数据供应商从 Bloomberg '
        '换成 Refinitiv，<b>2019-04 这一格本身就是缝合月</b> —— 月末值已是 Refinitiv，'
        '月均值是 4/1–4/25 Bloomberg 加 4/26–4/30 Refinitiv 拼的，2019-05 起才全程 Refinitiv。'
        + ('断点线因此画在 2019-04（引擎语义：从这一期起与左侧不可比）。'
           '短窗口图的起点钉到 2016 之后，这条断点第一次落进它们的窗口里 —— 凡是窗口跨过它的图'
           '<b>都画了这条红色竖虚线</b>：月度图 Exhibit 2 / 3 / 6 / 7 画在 2019-04，'
           f'季度图 Exhibit 5 / 8 / 10 画在 {BRK_Q}（缝合月所在的季度），'
           '外加全历史图 Exhibit 4。'
           'Exhibit 11 自 2020-01 起、整段在断点右侧，故不画（判据只有一处：'
           '窗口两侧都要有数据才画，不是逐图人肉判断）；'
           if brk_i is not None else
           '该月已不在任何一张图的窗口内，本次没有画出断点线；')
        + 'Exhibit 12 的热力矩阵没有连续 x 轴，画不了这条线，读 2019 那一行请自行留意。',
        '<b>桥的假设（Exhibit 7 / 10 / 11）</b>：月度 asset-based fee = 当月平均 AUM × 有效费率 ÷ 12。'
        f'有效费率是从季报披露的 asset-based fee 收入反解出来的，所以<b>已收官季度是分摊而不是估计</b>；'
        f'最新已知季度（{last_q} = {last_bp:.3f}bp）之后的月份沿用该值，那一段才是真正的估计 —— '
        + (f'本次有 {n_ffill} 个月落在这一段。' if n_ffill else
           f'本次费率已覆盖到最新月 {mlab(LATEST)}，沿用段为空，桥全程是分摊。')
        + f'隐含序列自 {mlab(abf_months[0])} 起共 {len(abf_months)} 个月（费率覆盖 {qs[0]} 起'
        f'共 {len(qs)} 季）——'
        f'2026-08 把 SEC 8-K 的抓取起点从 2020-04 下压到 2016-04 并补上老版式解析'
        f'（Table 5 三列收入表 + Table 7 老 AUM 表），费率序列因此由 30 季扩到 {len(qs)} 季，'
        '这四张桥图才和同页其余各图一样从 2016 起。'
        '新补的季度逐季与 MSCI 官网月度 AUM 页的季度均值对过账（46 季全部落在 ±0.35% 内，'
        '典型 ±0.05%），既有季度的数值一格未动。',
        # 核对表（Exhibit 13）的渲染器只吃 cols/rows，挂不上 note；它的「有效费率」列
        # 里同一季的三个月是同一个数，读者最容易把它误读成月度披露值 —— 所以这条必须在。
        '<b>费率的期间口径（Exhibit 7 / 8 / 10 / 11 与核对表的「有效费率」列）</b>：' + FEE_Q_BODY
        + f'Exhibit 8 的最右一根柱就是 {last_q}；核对表里同属一个季度的月份填的是<b>同一个</b>'
        '费率值（季度值下挂到月，不是月度披露）。判据本身也是现算的：费率最新可得季度比'
        '「数据月所在季度的上一季」还老，就在上面这段里加一句过期提示。',
        f'<b>桥的真实不确定性在费率而不是 AUM。</b>{qs[0]}–{last_q} 这 {len(qs)} 个季度里 AUM 复利上行，'
        f'但有效费率从 {BP_Q[qs[0]]:.2f}bp 压到 {BP_Q[qs[-1]]:.2f}bp（Exhibit 8 画的就是这 {len(QS8)} 季，'
        f'即 {QS8[0]} 的 {bpq[0]:.2f}bp → {QS8[-1]} 的 {bpq[-1]:.2f}bp）；'
        f'公司另行披露的期末 ETF 基点费率 '
        f'{DISC_Q[last_q]:.2f}bp 更低，因为它还覆盖非 ETF 的授权收入，两个口径不可互换。',
        '凡标题带 <b>Implied</b> 的都不是公司披露值（Exhibit 7 / 10 / 11）。Exhibit 10 的图注里逐季列了'
        '「隐含 vs 实际披露」的偏差，用来看桥搭得准不准 —— 看那组数，不看嘴上说。',
        f'<b>窗口：短窗口图一律自 {WIN0} 起</b>（日历常量，右端跟着数据最新月走，'
        f'所以窗口随时间自然变长，不是忘了倒推）。本轮月度图 {mlab(WM[0])} – {mlab(LATEST)} 共 '
        f'{len(WM)} 个月，季度图 {QW[0]} – {QW[-1]} 共 {len(QW)} 季。'
        '改这个口径的理由：25 个月装不下一个完整周期 —— 2018 回撤、2020 疫情坑、2022 熊市'
        '全在旧窗口之外，读者拿到的同比没有可比的历史坐标。'
        '<b>两张不适用</b>：Exhibit 4 本来就画全历史（'
        f'{mlab(months[0])} 起 {len(months)} 个月），Exhibit 9 是逐年路径图（x 轴是 Jan–Dec，'
        '窗口由「最近 6 年」定义，没有连续时间轴）。'
        f'<b>费率派生的四张也够到了</b>：Exhibit 7 / 8 / 10 / 11 由有效费率派生，费率序列原先'
        f'只回溯到 2019Q1，这四张只能从 2019 起。本轮把 SEC 8-K 的抓取起点下压到 2016-04 并'
        f'补上老版式解析，费率序列现自 {qs[0]} 起共 {len(qs)} 季，于是 Exhibit 7 自 '
        f'{mlab(WMa[0])}、Exhibit 8 / 10 自 {QS8[0]}、Exhibit 11 自 {mlab(yw[0])} 起 —— '
        f'与其余各图同起点。{qs[0]}–{qname(qi(QWIN0) - 1)} 那几季不画但要留着：'
        'Exhibit 8 / 10 的同比往前借 4 季、Exhibit 11 的同比借 12 个月，'
        '没有它们窗口开头会空一年。'
        f'热力矩阵（Exhibit 12）同口径取 {hyears[0]}–{hyears[-1]} 共 {len(hyears)} 个年度行；'
        '核对表仍是最近 13 个月的相对窗口 —— 它是「最近一年逐月核对」的工具，不是趋势图。'
        f'月度图的 x 轴每 {MSTEP} 格标一次（每年 1 月）、季度图每 {QSTEP} 格标一次（每年 Q1），'
        '逐格标必然叠成一团。',
        # ── 同比口径（CONTRACT.md §6）：本页每一处都是点对点，理由逐条实测 ──
        (f'<b>同比口径：本页每一处都是点对点同比</b>（当月对去年同月；费率那条取基点差），'
         f'<b>没有一张图用 {Y.TTM_WIN} 个月滚动口径</b> —— Exhibit 2 / 5 / 7 / 10 / 11 的同比线、'
         f'Exhibit 8 的基点差、Exhibit 3 / 12 的 m/m 与汇总表、核对表，以及页顶 brief 段的'
         f'环比与同比（句中同比已标「单月」）全部同口径，'
         f'所以本页任意两处的读数可以直接互相对读。理由如下，'
         f'<b>都不是「存量不能做滚动」那句一般性说辞</b>'
         f'（{Y.TTM_WIN} 个月滚动<b>均值</b>同比对存量在数值上完全正确 —— '
         f'Σ12 ÷ Σ12′ 恒等于均值比 —— 不许说的只是把它叫「合计」：'
         f'12 个月末的 AUM 快照相加不指代任何真实的量）：<br>'
         f'① <b>月末／月均 AUM（Exhibit 2 / 5 / 6 / 9）是期末存量</b>。'
         f'两种口径在 Exhibit 2 画出来的那 {_CAL_AUM["n"]} 个共同月份上实测：'
         f'点对点逐月标准差 {_CAL_AUM["sd_mom"]:.2f}pp、'
         f'{Y.TTM_WIN} 个月均值同比 {_CAL_AUM["sd_ttm"]:.2f}pp'
         f'（放大 {_CAL_AUM["sd_mom"] / _CAL_AUM["sd_ttm"]:.2f} 倍），'
         f'相邻月最大跳变 {_CAL_AUM["mj_mom"]:.2f}pp vs {_CAL_AUM["mj_ttm"]:.2f}pp，'
         f'符号相反的月份 {len(_CAL_AUM["opp"])} 个'
         + (f'（{_CAL_AUM["opp"][0][0]} 点对点 {_CAL_AUM["opp"][0][1]:+.1f}% vs '
            f'均值 {_CAL_AUM["opp"][0][2]:+.1f}%）' if _CAL_AUM['opp'] else '')
         + '。'
         # 「更平滑」这个结论必须由数据说了算，不能写死：本页 AUM 处在一段单边上行里，
         # 换个行情这个倍数会翻上去，那时候还印「远低于」就是一句假话。
         + (f'放大倍数确实到了全站流量序列的中位水平（2.08 倍），'
            f'但窗口内没有一个月方向相反 —— 也就是说滚动均值只会让转折点晚半年显形，'
            f'并不会把结论说反；'
            if _CAL_AUM['sd_mom'] >= _CAL_AUM['sd_ttm'] * 2.0 and not _CAL_AUM['opp'] else
            f'放大倍数低于全站流量序列的中位（2.08 倍）且窗口内没有一个月方向相反；'
            if not _CAL_AUM['opp'] else
            # ⚠️ 这一支是窗口拉到 2016 之后第一次触发的（旧的 25 个月窗口实测 0 个）。
            # 必须点明「窗口变长」这个来源：否则读者会把它读成本月新出现的口径漂移，
            # 而这些月份一直在数据里，只是从前不在窗口内 —— 那是假警报。
            f'⚠️ 窗口内有方向相反的月份（{len(_CAL_AUM["opp"])} 个，最早 '
            f'{_CAL_AUM["opp"][0][0]}）。这不是本月新出现的漂移：窗口从 25 个月拉到 '
            f'{_CAL_AUM["n"]} 个月之后，2018 回撤与 2020 疫情坑这类拐点第一次进入实测区间，'
            f'滚动均值在拐点上滞后半年、于是与点对点反号 —— 恰恰是不换口径的理由；')
         + f'存量比的是两个时点的资产，不含「今年这个月比去年多开几天市」这类日历效应，'
         f'而本页真正要回答的是「AUM 相对去年这个月是多少」；'
         f'噪声用轴范围解决，不换口径。<br>'
         f'② <b>隐含费收（Exhibit 7 / 10 / 11）是流量</b>，按契约默认本该用 '
         f'{Y.TTM_WIN} 个月滚动合计。这里仍用点对点，理由是<b>它必须与 AUM 同口径</b>：'
         f'本页的核心算术是「费收 ≈ 平均 AUM × 有效费率」，而 Exhibit 11 把费收同比与'
         f'平均 AUM 同比<b>画在同一张图上</b>（{mlab(LATEST)} {sgn_pct(yv[-1])} vs '
         f'{sgn_pct(aum_yoy)}，缺口 {gap[-1]:+.1f}pp），两条线的垂直距离就是这条算术的读数 ——'
         f'读者要能逐格相减，前提就是两条线同口径。'
         f'把费收换成滚动、AUM 留在点对点，这个缺口立刻变成两种口径相减，'
         f'读者按字面理解会把「口径差」读成「费率压缩」。'
         f'代价可以量出来：那 {_CAL_ABF["n"]} 个共同月份上，费收点对点同比标准差 '
         f'{_CAL_ABF["sd_mom"]:.2f}pp、滚动 {_CAL_ABF["sd_ttm"]:.2f}pp'
         f'（放大 {_CAL_ABF["sd_mom"] / _CAL_ABF["sd_ttm"]:.2f} 倍），'
         f'相邻月最大跳变 {_CAL_ABF["mj_mom"]:.2f}pp vs {_CAL_ABF["mj_ttm"]:.2f}pp，'
         f'符号相反 {len(_CAL_ABF["opp"])} 个月 —— '
         + ('点对点确实更吵，但没有一个月方向相反，'
            '换来的「与 AUM 同口径」比那点平滑更值。<br>'
            if not _CAL_ABF['opp'] else
            # 同上：这一支也是窗口变长带来的，来源要写出来。
            f'⚠️ 有 {len(_CAL_ABF["opp"])} 个月方向相反，同样是窗口拉长后拐点进了实测区间'
            f'（最早 {_CAL_ABF["opp"][0][0]}），不是本月的新情况；'
            '「与 AUM 同口径」这个取舍不变。<br>')
         + f'③ <b>有效费率（Exhibit 8）是比率</b>，同比只能是基点差；'
         f'滚动合计与滚动均值对比率都没有意义（要「一年的平均费率」得用 AUM 加权，'
         f'即 Σ费收 ÷ Σ平均 AUM，那要两条序列）。<br>'
         f'④ <b>Exhibit 12 是热力矩阵</b>，按 §6 本就豁免（逐格波动正是这类图的题眼）；'
         f'<b>两张表的 y/y 列</b>必须恒等于表内算术，读者拿相邻两列去除要能得到同一个数。'),
        '<b>柱图的右轴金色线是同比，不是滚动均线</b>（Exhibit 2 / 7 / 8）：均线只是把柱子再平滑一遍、'
        '不带新信息，同比才回答「相对去年这个月是好是坏」，这也是原 deck（gsx.lvl_bar）的画法。'
        '开了同比线的图不再画那条 12 个月均线虚线，也不再另给同比气泡。'
        'Exhibit 8 的右轴单位是<b>基点差（bp）</b>而不是百分比：该序列的刻度本身就是 bp。',
        '标题里的当期数字（YoY / MoM / 倍数 / 分位）全部随最新月重算，没有写死的字面量；'
        '有效费率（Exhibit 8）以 bp 为刻度，其同比一律用<b>基点差（bp）</b>的绝对差，'
        '不用「百分比的百分比变化」，也不写成百分点（1pp = 100bp）。'
        '四舍五入后等于零的负数一律写成 0（不写「-0」，那是格式化产物不是数据）。',
        '汇总表的「月末 − 月均」一行会在零附近变号，百分比变化无意义，故其 m/m 与 y/y 用绝对额（$bn）；'
        '3Y %ile 的算法与留空判据由全站唯一实现 <code>build/pctile.py</code> 提供'
        '（回放近 24 个月，≥70% 的月份分位钉在 100 或 0 就留空），本页不再自带一份分位逻辑 —— '
        '同一条序列在两页判定相反，根因就是各写各的。',
        '<b>与原 deck 仍有的两处差距（网页引擎的能力缺口，不是笔误）</b>：一是数值标签的 '
        '「$ + 千分位」这一档格式器 charts.js 没有，所以 Exhibit 2 / 6 / 7 / 9 与 Exhibit 4 的'
        '末点标签写作 <code>2,818</code> 而非 <code>$2,818</code>，单位由纵轴标题（$bn / $mn）交代；'
        '二是 deck 在 Exhibit 4 的最近 3 个点外圈了一个红色虚线椭圆（"最近三个月在这里"），'
        '网页没有这个图元，改由末点数值标注承担「最新一点在哪」的作用。',
    ]

    payload = {
        'ticker': 'msci',
        'tracker': 'MSCI Monthly ETF AUM Tracker',
        'title': f'MSCI Inc. (MSCI)：挂钩 MSCI 指数的 ETF 月度 AUM — {LATEST[:4]} 年 {int(LATEST[5:])} 月',
        'data_through': LATEST,
        'through_label': f'{LATEST[:4]} 年 {int(LATEST[5:])} 月',
        'subtitle': ('数据源：MSCI IR「AUM in ETFs Linked to MSCI Equity Indexes」（每月中旬更新上月）'
                     f' · 覆盖 {mlab(months[0])} – {mlab(LATEST)}（{len(months)} 个月）'
                     ' · 版式仿 Goldman Sachs GIR monthly-metrics'),
        'headline': (f'月末 AUM ${f(EOP[LATEST], 1)}bn（{sgn_pct(yoy(EOP, LATEST))} YoY，'
                     f'{sgn_pct(mom[LATEST])} MoM） · 当月平均 AUM ${f(AVG[LATEST], 1)}bn'
                     f'（{sgn_pct(aum_yoy)} YoY） · 隐含 asset-based fee ${abf[LATEST]:.1f}mn/月'
                     # 抬头不能只报喜：费率是这页唯一往下走的量，同比压缩幅度要一起写出来。
                     # 「起沿用」只在真有沿用月份时才说（n_ffill=0 时那句话是假的）。
                     f'（{sgn_pct(yv[-1])} YoY） · 有效费率 {last_bp:.3f}bp'
                     f'（{last_q}，{yoy8:+.2f}bp YoY'
                     + (f'，其后 {n_ffill} 个月沿用该值）' if n_ffill else '，已覆盖到最新月）')),
        # headline 之下、Exhibit 1 之上的 ~300 字解读。职责与 headline 互补：那一行给读数，
        # 这一段给「读数该怎么读」（基数效应 / 口径背离 / 所处区间）。见 compose_brief 的 docstring。
        'brief': compose_brief(months, EOP, AVG, BRK),
        'hub_line': (f'月末 AUM ${f(EOP[LATEST], 0)}bn，{pp_txt(yoy(EOP, LATEST))} YoY；'
                     f'有效费率压到 {last_bp:.2f}bp'),
        'source': SRC,
        'xlabels': XL13,
        'xlabels_long': XL_LONG,
        'summary': summary,
        'exhibits': ex,          # 已在上面过完 axisfmt.fix_all（幂等，这里不重复调）
        'table': table,
        'notes': notes,
        'footer': ('数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
                   '仅供个人研究，不构成投资建议'),
        # 这一页没有 source_date，而且**永远不会有**：MSCI 的 AUM 页是一张「活页面」，
        # 每月悄悄改表，页面正文、meta、Drupal 设置、RSS、email-alerts、download-library、
        # sitemap 全查过，没有任何自述发布日；也不为此发新闻稿。唯一的机器时间戳
        # HTTP Last-Modified 是边缘渲染时刻不是数据时刻（见 fetch/msci.py docstring）。
        # 季报 8-K 的 Table 7 虽然有确定申报日，但一年只覆盖 4 个季末月、口径只有整数十亿的
        # 季末值（本页画的月均它证明不了），而且多半晚于 IR 页实际上线的日子 ——
        # 拿它当发布日就是一个看不出来是假的、系统性偏晚的日期。所以宁可明说没有。
        # 若哪天 MSCI 在页面上加了 "Updated" 行：_download() 每天都存快照
        # cache/msci_aum_YYYYMMDD.html，到时候解析很容易补上。
        'source_date_note': '官方未标注发布日',
    }

    out = os.path.join(ROOT, 'data', 'msci.js')
    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(out, payload, 'msci')

    print(f'数据最新月 {LATEST}｜月度序列 {months[0]} → {months[-1]}（{len(months)} 个月）')
    print(f'费率季度 {qs[0]} → {qs[-1]}（{len(qs)} 季）｜隐含 ABF 覆盖 {abf_months[0]} → {abf_months[-1]}')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）+ Exhibit {table["n"]} 核对表')
    print(f'写出 {out}（{os.path.getsize(out) / 1024:.1f} KB）')
    print(payload['headline'])


if __name__ == '__main__':
    main()
