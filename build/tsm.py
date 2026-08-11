# -*- coding: utf-8 -*-
"""TSMC (2330.TW) 月度营收 —— 网页看板数据生成器（data/tsm.js）。

移植自 build/build_tsm.py（matplotlib / PDF 版）；沿用 deck 的图型、窗口与图注口径，但顺序、编号与选图自 2026-08 起有意分家（见下）。
数据全部来自 series/tsm.csv、series/tsm_fx.csv、series/tsm_guidance.csv 三个文件，
不引入任何外部估计。

**顺序与编号自 2026-08 起有意与 deck 不同**（按阅读动线重排）：
月营收→汇率两条→环比→季度桥→长历史→指引两张→汇率→热力矩阵；
deck 的「滚动 12 个月营收」整张移除（页内 TTM 只剩汇总表的占比行）；
deck 的「逐年 YTD 累计」整张移除：把季内进度画成「相对指引中值的落点」之后，
前两个月那两点与全季落点符号相反 7/14 季、相关系数 −0.19，读不出方向，2026-08 删除。

口径（与 PDF 版同源）：
  · 唯一的官方披露字段是「合并营收（NT$mn，未经查核）」，台湾法定次月 10 日前公告。
    月营收 NT$bn / 3 个月移动平均 / QTD / YTD / 占 TTM 比重全部由它派生。
  · **同比口径本页并存两种，页尾「口径与方法说明」里逐处点名**（CONTRACT.md §6）：
    Exhibit 2 的右轴金线是 **12 个月滚动合计同比**（营收是流量、可加总，这个「合计」
    指代的是真实的一年营收）；其余每一处 —— Ex3 季度、Ex5、Ex6、Ex9 热力矩阵、
    汇总表与核对表的 y/y 列，以及页顶 brief 里标明「单月」的读数 —— 都是**单月同比**。
    理由逐条不同，写在那条说明里，
    不在这里重复；要紧的是**不要拿 Ex2 的金线去和 Ex5 的深藏青线对读**。
  · 单月同比又有两个来源：公司随营收一并公告的 yoy_pct（用于热力矩阵与核对表），
    以及本脚本自算的 y/y（用于 Ex3 / Ex5）。两者极小差异来自公司口径的四舍五入，
    不做人工对齐，差多少由运行时现算并印在口径说明里。
  · 同比的算式一律走 build/yoy.py（全站唯一实现），本文件不再自己写 pct_change(12)：
    同比曾在 15+ 个 builder 里各实现一遍，那正是全站口径出错的根因。
  · 美元口径一律是**推导值（Implied）**：NT$ 营收 ÷ 当月平均 NTD/USD 汇率，
    不是公司披露的美元营收。汇率贡献 = NT$ y/y − US$ y/y（百分点）。
  · 季度指引表自 2026-08 起只喂页顶 brief 的指引桥，页内不再有指引图（Ex8/Ex9 已删）。

⚠️ 断点：TSMC 月营收自 2016-01 起口径连续，未发生并表/重述，故全站未设 break_at，
   也未设截轴 ycap/yfloor —— 不是忘了设，是确实没有。这句话不是写死的散文：
   末尾 notes 里那条声明由 payload 现读（_BRK_DRAWN / _CAP_DRAWN），
   哪天真加了断点或截轴，注释会自己跟着改，不会变成「图注说有、图上没有」。

Deck（build/build_tsm.py）对齐记录 —— 这一轮补回三处「deck 有、网页一直没有」的信息：
  · Exhibit 2 改用 kind='gs_bar' + 次轴 y/y（金色）：bar_line_dual 在引擎里没有柱值标签
    分支，deck 的 rev_bar_yoy 每隔一根柱标 NT$bn、并在 y/y 末点标 +68%，这些以前全丢了。
  · Exhibit 7 / 8 打开 end_label（deck 的 long_line n_label），Ex7 另开 zero_base。
  · Exhibit 6 补回 deck 的次轴同比线（gsx.lvl_bar 的 pct_series=True → 百分点差，
    季度序列 lag=4、月度序列 lag=12）。这两张仍用 grouped_bars 而不是 gs_bar：
    gs_bar 纵轴强制自 0 起，会把 −14.1pp 那根负柱画到画布外（详见各图 note）。

用法：python3 build/tsm.py
"""
import datetime
import json
import os

import numpy as np
import pandas as pd

import axisfmt
import brief as B      # 页顶 brief 的规则库（R1-R6），只算事实、不出文字；句子在本文件里拼
import payload_guard
import pctile          # 汇总表 3Y %ile 的唯一实现，各页不再各写各的（见该模块 docstring）
import yoy as Y        # 同比口径的唯一实现（build/yoy.py）。本页不再自己写 pct_change(12)：
#                        同比曾在 15+ 个 builder 里各实现一遍，那正是全站口径出错的根因。
#                        Y 的 kind 是必填参数，传错会抛 CaliberError 而不是静默给错数。

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
DATA = os.path.join(ROOT, 'data')

SRC = 'Source: TSMC monthly revenue reports; format after Goldman Sachs GIR'
SRC_FX = 'Exhibit source: monthly average NTD/USD (FRED series EXTAUS).'
ASSUMP = ('Assumption: NT$ converted at the month average NTD/USD rate — an approximation')

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
CN_MONTH = None


def mlab(p):
    """与 gsx.mlab 同：'Jun-26'。"""
    return p.strftime('%b-%y')


ALIGN_WASTE_MAX = 0.38      # 与 assets/charts.js 的 ALIGN_WASTE_MAX 同值


def align_sim(ex):
    """复算引擎「两轴零点画在同一高度」之后，这张图的左轴与浪费掉的画布比例。

    返回 dict（单轴图或右轴无值返回 None）：
      lo/hi     引擎**实际**用的左轴上下界
      alo/ahi   假如对齐，左轴会被扩到哪（不对齐分支下就是「代价有多大」的具体数）
      waste     对齐要浪费掉的量程比例
      aligned   引擎最终有没有对齐（waste > ALIGN_WASTE_MAX 就不对齐并在图上标红字）

    为什么要在生成端复算一遍：图注里那句「对齐扩出来的空白约占左轴量程的 X%、
    低于 38% 的兜底阈值所以仍然对齐」是一句**关于渲染结果的声称**，而 X 随每月新数据变。
    原文把它写成常量 29%，实测本轮是 28.6% —— 今天恰好对得上，下个月不一定。
    本仓的规矩是「一个数字都不许写死在文案里」，何况这个数还决定后半句的结论
    （对齐 or 不对齐）说得对不对。

    零件全部来自 build/axisfmt.py（引擎那套量程/刻度算法的 Python 复算），
    这里只是把 charts.js:690 起那段对齐分支按同一顺序走一遍，不另写一套算法。
    ⚠️ 本函数与 build/axp.py 里的同名函数逐字相同 —— 它该住在 axisfmt.py 里供全站共用，
    但那个文件本轮不归本任务改，所以先各放一份，注释互相点名以免日后只改一处。
    """
    rng = axisfmt._left_range(ex)
    rc = axisfmt._rhs(ex)
    k = ex.get('kind')
    dual = k in ('bar_line_dual', 'stacked_dual') or \
        (k in ('qtr_bar', 'grouped_bars', 'gs_bar') and rc is not None)
    if rng is None or not (dual and rc):
        return None
    y0, y1 = rng
    rv = axisfmt._fin(rc.get('values'))
    if not rv:
        return None
    rtk = axisfmt.ticks(min(rv + [0.0]), max(rv), 9)
    r0, r1 = rtk[0], rtk[-1]
    f = max(axisfmt._zero_frac(y0, y1), axisfmt._zero_frac(r0, r1))
    if f <= 1e-9:                      # 两轴都不含负值：零点本来就同高，没有代价
        return {'lo': y0, 'hi': y1, 'alo': y0, 'ahi': y1, 'waste': 0.0, 'aligned': False}
    la0, la1 = axisfmt._align_zero(y0, y1, f)
    ra0, ra1 = axisfmt._align_zero(r0, r1, f)
    w1 = 1 - (y1 - y0) / (la1 - la0) if (la1 - la0) else float('nan')
    w2 = 1 - (r1 - r0) / (ra1 - ra0) if (ra1 - ra0) else float('nan')
    waste = max(w1, w2)
    ok = not (waste > ALIGN_WASTE_MAX)     # 超阈值 → 引擎改为不对齐并在图上标红字
    return {'lo': la0 if ok else y0, 'hi': la1 if ok else y1,
            'alo': la0, 'ahi': la1, 'waste': waste, 'aligned': ok}


def source_date(month):
    """该月营收公告的官方发布日（抬头「官方发布于 …」那半句），查不到返回 None。

    台账模块在仓库根，而 `python3 build/tsm.py` 的 sys.path 上只有 build/，
    所以按路径加载（见 source_dates.py 的 load()）。
    读不到不算构建失败：这半句缺席只是少一条信息，为它把整页判挂不划算。
    """
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'source_dates', os.path.join(ROOT, 'source_dates.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.lookup(SERIES, 'tsm', month)
    except Exception as e:
        print(f'[tsm][warn] 读 series/source_dates.csv 失败，本次不写 source_date：{e!r}')
        return None


def num(v, nd=6):
    """写进 payload 的数值：非有限一律 None，有限的统一定点舍入，保证幂等。"""
    if v is None:
        return None
    f = float(v)
    if not np.isfinite(f):
        return None
    return round(f, nd)


def L(seq, nd=6):
    return [num(v, nd) for v in seq]


def f(v, dec=1, pct=False, money=''):
    """与 gsx._fmt 同：千分位 + 固定小数位；非有限返回 '—'。"""
    if v is None or not np.isfinite(float(v)):
        return '—'
    s = f'{float(v):,.{dec}f}'
    return (money + s + '%') if pct else (money + s)


def sgn(v, dec=1, suffix='%'):
    if v is None or not np.isfinite(float(v)):
        return '—'
    return f'{float(v):+,.{dec}f}{suffix}'


# ────────────────────────────── 读数据 ──────────────────────────────
def load():
    p = os.path.join(SERIES, 'tsm.csv')
    df = pd.read_csv(p)
    for c in ('month', 'revenue_ntd_mn', 'yoy_pct'):
        if c not in df.columns:
            raise SystemExit(f'series/tsm.csv 缺列 {c}')
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    df = df.set_index('month').sort_index()
    if df.index.has_duplicates:
        raise SystemExit('series/tsm.csv 有重复月份')
    # 月份必须逐月连续 —— 断档会让相隔数月的柱画成相邻柱（假时间轴）
    gaps = [(df.index[i] - df.index[i - 1]).n for i in range(1, len(df))]
    if any(g != 1 for g in gaps):
        bad = [str(df.index[i]) for i in range(1, len(df)) if (df.index[i] - df.index[i - 1]).n != 1]
        raise SystemExit(f'series/tsm.csv 月份不连续，断在 {bad}')

    fxp = os.path.join(SERIES, 'tsm_fx.csv')
    fx = pd.read_csv(fxp)
    fx['month'] = pd.PeriodIndex(fx['month'], freq='M')
    fx = fx.set_index('month').sort_index()['ntd_per_usd'].astype(float)

    g = pd.read_csv(os.path.join(SERIES, 'tsm_guidance.csv'))
    return df, fx, g


def compose_brief(ALL, rev, yoy, fx_al, fx, mom_all, qsum_bn, qcnt, fxq, g, g_mid, g_act):
    """TSMC 页顶部的 ~300 字数据总结（payload 的 `brief` 字段）。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R3 日历护栏 / R4 单位恒等 /
    R5 标注 / R6 有效位），那边只算事实，句子在这里拼 —— 措辞是口径的一部分。
    每个数字都当场从序列算，**没有一处硬编码**：排名、连续几个同月、峰值停在哪个月、
    指引缺口，下月重跑都会自己变。

    ═══ TSMC 独有，别家不能照抄 ═══
      · **R3（日历护栏）在这里不成立，且不是「没有交易日列」这么简单。** 晶圆厂 24/7
        连续生产，每个日历日都是生产日，看上去正该按天数归一化；但把天数当线性驱动的
        假设被本页数据自己否掉：`(m/m) ~ (天数变化%)` 的回归斜率是 1.47 而不是 1，
        二月对 1、3 月均值的实际比值多年平均 0.84、天数比值却是 0.91 —— 天数只是农历年
        与季末拉货日历的**代理变量**，不是产出的线性驱动。按天数除一遍会把农历年效应
        算成「经营性走弱」，正是 brief.py 警告的那种假修正。所以本页不做日均化，
        季节性改用**同月对同月**（下面 s2 的「前 N 个 6 月」）来定位。
      · **汇率贡献不能按 pp 直读**，这是 TSMC 特有的读错点。页面各处印的
        「汇率贡献 = NT$ y/y − US$ y/y」是**百分点差**，恒等于
        `汇率同比 ×（1 + 美元同比）` —— 同一幅新台币贬值，在高增速期印出来的 pp 数会被
        放大 (1+美元同比) 倍。R4 的单位恒等（US$ 营收 = NT$ 营收 ÷ 汇率，其同比是两个
        同比之**商**而非差）正是拆这个的工具，别家没有双计价口径，用不上。
      · **指引桥是本页独有的跨源推导**：指引是**美元**、主序列是**新台币**，
        全页从不把两者接起来（自 2026-08 起指引表只喂这一段，页内没有指引图）。这里用公司自己披露的指引中值 × 公司自己假设的汇率，
        折出「本季剩余月份月均还需多少 NT$bn」——两个输入都是披露值、乘积是推导值（R5），
        所以正文带「（推导值）」，并另给一个按已实现汇率重算的版本，让读者看见这个缺口
        里有多少是汇率假设、多少是量。
        重算用的参照汇率**优先取落在该季之内的已实现月份**，而且必须从原始 `fx` series 取，
        不能用 `fx_al`：FRED 的月均汇率比营收早一个月发布（本轮 fx 已有 2026-07 = 32.22，
        营收还停在 2026-06），`fx_al = fx.reindex(rev.index)` 恰好把这唯一一个**落在指引季
        之内的已实现观测**截掉。用被截掉后的「近三月」（那其实是上一季）去评价 32.0 的假设，
        会得出「假设偏保守、缺口被高估」，而 7 月实测 32.22 高于假设，方向正好相反。
        季内一个月都还没实现时才回落到最近三个月，并在句子里注明取的是哪几个月
        （不用 `fxq[tq]`：它按营收月份轴分组，同一个断层下算出来的是个残缺季度均值）。

    ═══ 与本页 2026-08 同比口径改造的关系（移植时的口径适配）═══
      远端写这一段时全页还是单月同比；本地 Exhibit 2 的右轴金线已改
      **12 个月滚动合计同比**，页尾点名条把两种口径的当期读数并排现算
      （本轮：单月 +67.9% vs 滚动 +30.6% 那一条）。适配照 CONTRACT §6 与
      cboe / ibkr 的先例：brief 引用的同比一律标「单月」（与汇总表、Exhibit 5
      同口径，可逐格对上），只作**位置与基数**陈述；s3 的名次陈述把滚动读数
      并排印出并点名 Exhibit 2 口径 —— 单月 +67.9% 的「历史第几」若不带滚动
      读数，读者会拿它去对 Exhibit 2 的金线（+30.6% 量级），对不上还以为哪边
      算错了。s4 的单位恒等必须留在单月口径：它讲的是「公司这个月报出来的
      增速里有多少是汇率」，换成滚动口径就不再是公司报的那个数。滚动同比走
      全站唯一实现 `build/yoy.py`，本函数不自己写 pct_change。
    """
    i = len(ALL) - 1
    n_all = len(ALL)
    KEYS = [str(p) for p in ALL]                    # brief.py 的月份口径是 'YYYY-MM' 串
    rv = rev.values.astype(float)                   # NT$mn
    cur_bn = rv[i] / 1000.0

    def cnq(v):
        """量词位上的 2 在中文里读「两」不读「二」（B.cn 只管数词，不能改它）。"""
        return '两' if v == 2 else B.cn(v)

    # ── R1：水平序列的峰值扫描。四条都是「水平/存量」口径的营收规模，不是流量之外的东西；
    #    skip_monotonic 保持默认 True（T3：只增不减的列「又创新高」每月都成立，是噪音）。
    lv = [('月营收', rv),
          ('美元营收', (rev / fx_al).values.astype(float)),
          ('三月均值', rev.rolling(3).mean().values.astype(float)),
          ('滚动12个月', rev.rolling(12).sum().values.astype(float))]
    pk = B.peak_scan(KEYS, lv, i)
    n_lv = len(pk['at_peak']) + len(pk['off_peak'])
    mth = ALL[i].month

    # ── s1（规模）：当月读数 + 它在全样本的位置 + 其余水平序列见没见顶。
    #    名次当场算，不写死「最高」—— 下个月这里可能就是第 3 名。
    mrank = B.rank_of(rv, i)
    lead = (f'{mth}月合并营收<b>NT${B.num(cur_bn)}bn</b>'
            + (f'为{n_all}个月最高' if mrank == 1 else f'在{n_all}个月里排第{mrank}'))
    # 「只有 / 有 / 多达」必须跟着占比走，不能写死：本月四条全见顶走的是第一分支，
    # 但按月回放里 19 个月落在混合分支，其中 2024-09 是 4 条里 3 条见顶 —— 写死的「只有」
    # 会把普遍现象说成稀缺。量词一律交给 B.quant（brief.py 就是为这个 bug 加的）。
    if not n_lv:
        s1 = lead + '。'
    elif not pk['off_peak']:
        s1 = f'{lead}，{cnq(n_lv)}条水平序列同时见顶，靠「创新高」分不出高下。'
    elif not pk['at_peak']:
        s1 = (f'{lead}，{cnq(n_lv)}条水平序列一条都没见顶，'
              f'峰值停在{B.peak_months_txt(pk["off_peak"])}月。')
    else:
        # 量词位上的 2 同样要读「两」；B.quant 只管「只有/有/多达」跟着占比走，
        # 数词是 B.cn 出的「二」，在「二条」这个位置上是错的中文，就地换掉。
        q = B.quant(len(pk['at_peak']), n_lv, '条').replace('二条', '两条')
        s1 = (f'{lead}，{cnq(n_lv)}条水平序列里{q}见顶：{"、".join(pk["at_peak"])}，'
              f'其余停在{B.peak_months_txt(pk["off_peak"])}月。')

    # ── s2：R2 基数护栏（m/m 一侧）+ 同月对同月的季节定位（替代被否掉的 R3 日均化，
    #    理由见 docstring）。上月自身在全样本排第几，决定这个环比是被基数顶出来的还是真步进；
    #    措辞必须跟着环比的方向走：上月是历史高点时，负环比正是高基数造成的，
    #    写成「不靠低基数」就把因果说反了（首轮回放 2026-04 就撞上了这一条）。
    be = B.base_effect(rv, i)
    mm = be['mm']
    same = [(p.year, float(mom_all[p])) for p in ALL
            if p.month == mth and np.isfinite(float(mom_all.get(p, np.nan)))]
    if mm is None:                       # 序列只有一个月：环比、上月排名都不存在，这句不写
        s2 = ''
    else:
        up = mm > 0
        streak = 0
        for _, v in reversed(same[:-1]):
            if (v > 0) == up:
                break
            streak += 1
        j = len(same) - 2 - streak       # 上一个同号年份；j < 0 表示样本内没有同号过
        if streak >= 2 and j >= 0:
            # same[j] 是**上一次同号**的年份，不是「以来第一个」的起点：2021-06 自己就是
            # 正的，写「2021 年以来第一个环比转正的 6 月」按字面指的是 2021-06，差一位。
            seas = (f'前{cnq(streak)}个{mth}月全为{"负" if up else "正"}，'
                    f'上一次转{"正" if up else "负"}还是{same[j][0]}年')
        elif len(same) >= 3:
            # 第 1 名写「最高」而不是「排第1」（同 s1 的 lead 与 s3 的 head，全篇一个口径）。
            r = sorted((v for _, v in same), reverse=True).index(same[-1][1]) + 1
            seas = f'在{len(same)}个{mth}月里{"最高" if r == 1 else f"排第{r}"}'
        else:                            # 同月样本还不够，退回全样本的环比名次
            mr = B.rank_of(mom_all.values.astype(float), i)
            seas = (f'{mth}月还没有可比样本，'
                    f'在{n_all}个月里{"最高" if mr == 1 else f"排第{mr}"}')
        pr = be['prev_rank']
        top = f'全样本{"最高月" if be["prev_is_max"] else f"第{pr}高月"}'
        if pr and pr <= 3:
            base = (f'；上月是{top}，这个环比不靠低基数。' if up
                    else f'；上月是{top}，这个跌主要是高基数。')
        else:
            base = f'；上月在全样本排第{pr}，环比的基数不算极端。'
        s2 = f'环比{B.pct(mm)}，{seas}{base}'

    # ── R2 的 y/y 一侧：同比排名用公司公告的 yoy_pct（页面各处引的就是它）。
    #    口径适配（本地 Exhibit 2 已改滚动）：名次说的是**单月**同比，措辞按 CONTRACT §6
    #    标明，并把滚动读数并排印出、点名 Exhibit 2 口径（理由见 docstring 末段）。
    #    反事实基数 = 去年同月**前后两个月**的均值（i-13 与 i-11），不含去年同月自己 ——
    #    要量的就是「去年同月这个凹坑有多深」，把凹坑月放进它自己的平滑窗口会系统性低估它
    #    （本轮：三月均值口径算出 dip −12.8%、gap 22pp；剔掉自己后是 −18.1%、30pp）。
    #    更要紧的是措辞与算式必须同口径：前半句说「前后两月」、后半句说「这三月均值」，
    #    并排读就是两个基数，读者按字面根本还原不出 46.4% 这个数。
    #    这个差额**可正可负**，首轮回放里 2026-05 是 −4pp（去年同月其实偏高），
    #    所以整句必须双向成立。符号上恒等：凹坑（dip < 0）⇔ gap > 0。
    yd = yoy.values.astype(float)
    n_y = int(np.isfinite(yd).sum())
    yrank = B.rank_of(yd, i)
    # 滚动同比走全站唯一实现（build/yoy.py），Y.ttm_yoy 返回 %，B.pct 吃小数。
    r12 = float(Y.ttm_yoy(rev, Y.FLOW).values.astype(float)[i])
    roll_tag = (f'（{Y.TTM_WIN}个月滚动口径是{B.pct(r12 / 100)}，Exhibit 2）'
                if B.need(r12) else '')
    if yrank is None:
        s3 = ''
    else:
        head = (f'单月同比在{n_y}个月里{"最高" if yrank == 1 else f"排第{yrank}"}'
                + roll_tag)
        # 需要去年同月及其前后各一月都在样本内；不足 14 个月时这半句不写（B.need：该句不写，
        # 而不是整页构建失败）。
        if i >= 13 and B.need(rv[i - 13], rv[i - 12], rv[i - 11], yd[i]):
            m2 = (rv[i - 13] + rv[i - 11]) / 2               # 去年同月前后两月的均值
            dip = rv[i - 12] / m2 - 1
            cf = rv[i] / m2 - 1                              # 基数换成这两个月均值后的同比
            gap = yd[i] - cf * 100
            if gap >= 3:
                mid = f'但分母塌了：去年同月比前后两月均值低{abs(dip) * 100:.1f}%'
                tail = (f'换成这两月作基只剩{B.pct(cf, sign=False)}，'
                        f'<b>约{gap:.0f}个百分点是低基数给的</b>')
            elif gap <= -3:
                mid = f'而且基数并不低：去年同月比前后两月均值高{abs(dip) * 100:.1f}%'
                tail = (f'换成这两月作基反而是{B.pct(cf, sign=False)}，'
                        f'<b>高基数压掉了约{-gap:.0f}个百分点</b>')
            else:
                mid = f'分母也干净：去年同月与前后两月均值只差{abs(dip) * 100:.1f}%'
                tail = f'换成这两月作基仍有{B.pct(cf, sign=False)}，不是基数造出来的'
            s3 = f'{head}，{mid}；{tail}。'
        else:
            s3 = f'{head}，去年同月的前后两月还不在样本里，基数效应暂时还原不了。'

    # ── R4：单位恒等。US$ 营收 = NT$ 营收 ÷ 汇率（推导值），其同比是两个同比之**商**；
    #    页面各处的「汇率贡献」是两者之**差**（pp），恒等于 汇率同比 ×（1+美元同比）。
    #    口径适配：本段同比全部是**单月**（与 Exhibit 5 同一张脸），措辞逐处标明 ——
    #    它讲的是「公司这个月报出来的增速里有多少是汇率」，换成 Exhibit 2 右轴的滚动
    #    口径就不再是公司报的那个数（页尾点名条对 Ex5/6 的豁免理由，同一条）。
    pu = B.per_unit(rv, fx_al.values.astype(float), i)
    dy, uy = pu.get('den_yoy'), pu.get('yoy')
    # R5：「（推导值）」要挂在真正推导出来的那个量上 —— 是**美元营收**（NT$ ÷ 月均汇率），
    # 不是汇率本身（汇率是 FRED 的披露值）。
    if B.need(dy, uy):
        # 分子用**自算**的新台币同比而不是公告的 yoy_pct：印出来同样是 +67.9%，但只有同源的
        # 两个数相除才恰好等于印出来的美元同比，读者拿页面上的三个数当场验算才对得上。
        # 取 R4 自己算好的 num_yoy（brief.py 同一实现里同源），不在本文件手写 rv[i]/rv[i-12]：
        # 本页今天刚立的规矩是同比算式只许一处实现（见文件头），brief 不能自己开例外。
        nt = float(pu['num_yoy'])
        amp = 1 + uy                                     # pp ≡ 汇率同比 × amp
        amt = abs(dy) * 100
        # 负零是格式化产物不是数据（同 B.pct 的处理）。
        pps = f'{(nt - uy) * 100:+.1f}'
        if float(pps) == 0:
            pps = f'{0.0:.1f}'
        if amt < 0.05:
            # 汇率几乎没动：再说「除以汇率贬幅 0.0% 的商」是句废话，整句改口。
            s4 = (f'美元营收（推导值）单月同比{B.pct(uy)}几乎等于新台币{B.pct(nt)}，'
                  f'本月汇率基本没动，汇率贡献{pps}pp 可以忽略。')
        else:
            band = f'汇率{"贬" if dy > 0 else "升"}幅{amt:.1f}%'
            # 倍数四舍五入到 1.0（|uy| < 5%）时，「相当于汇率幅度的 1.0 倍」自己就是矛盾句，
            # 回放里 2017-08/09 正是这种月份；此时 pp 与汇率幅度几乎相等，改口不给倍数。
            # 这里只写「汇率幅度」不重复 band：同一句前半已经印过贬/升幅的数值，
            # 再印一遍就是同一个数在一句里出现两次。
            rel = ('与汇率幅度几乎相等' if abs(amp - 1) < 0.05
                   else f'本月相当于汇率幅度的{amp:.1f}倍')
            s4 = (f'美元营收（推导值）单月同比{B.pct(uy)}，是新台币单月{B.pct(nt)}除以'
                  f'{band}的商；汇率贡献{pps}pp 只是两者之差，{rel}。')
    elif i >= 1 and B.need(rv[i - 1], fx_al.values[i], fx_al.values[i - 1]):
        # 不足 12 个月：同比不存在，但同一个「相除不是相减」在环比上照样成立。
        fm = float(fx_al.values[i]) / float(fx_al.values[i - 1]) - 1
        um = float(pu['series'][i]) / float(pu['series'][i - 1]) - 1
        s4 = (f'美元营收（推导值）环比{B.pct(um)}，是新台币{B.pct(be["mm"])}除以汇率'
              f'{"贬" if fm > 0 else "升"}幅{abs(fm) * 100:.1f}%的商；同比要满 12 个月才有。')
    else:
        s4 = ''

    # ── s5：R5 指引桥。两个输入都是公司披露值，乘积是推导值，必须标。
    lo, hi = g['guide_low_usdbn'].astype(float), g['guide_high_usdbn'].astype(float)
    gfx = g['guide_fx_ntd_per_usd'].astype(float)
    tq = next((q for q in g.index if not np.isfinite(float(g_act.get(q, np.nan)))), None)
    if not len(g.index) or (tq is not None and not B.need(g_mid.get(tq), gfx.get(tq))):
        s5 = ''
    elif tq is not None:
        qp = pd.Period(tq, freq='Q-DEC')
        k = int(qcnt.get(qp, 0))
        qtd = float(qsum_bn.get(qp, 0.0))
        need = float(g_mid[tq]) * float(gfx[tq])                 # 指引中值折成 NT$bn
        gf = float(gfx[tq])
        # 参照汇率**优先取落在 tq 之内的已实现月份**，且从原始 fx 取（理由见 docstring：
        # 汇率比营收早发一个月，fx_al 会把该季唯一一个已实现月截掉，用上一季均值去评价
        # 本季假设会把结论说反）。季内一个月都没有时才回落到最近三个月，并注明月份。
        inq = [(p, float(v)) for p, v in fx.items()
               if p.asfreq('Q-DEC') == qp and np.isfinite(float(v))]
        if inq:
            rfx = float(np.mean([v for _, v in inq]))
            ref = f'当季{"、".join(str(p.month) for p, _ in inq)}月已实现{rfx:.2f}'
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
            # 「高/低」必须由 rfx 与 gf 当场比出来：新台币实现值比假设弱（NTD/USD 更高）时
            # 缺口更大，方向跟着翻面。两者相差不到 0.05 时印出来根本是同一个数（假设一位
            # 小数、实现两位），这时再把同一个百分比印第二遍就是自己跟自己打架（回放 2025-09）。
            if abs(rfx - gf) < 0.05:
                s5 = head5 + '，与假设基本持平。'
            else:
                s5 = f'{head5}，按它算需{"高" if d2 >= 0 else "低"}{abs(d2) * 100:.1f}%。'
        else:
            der = qtd / float(fxq[qp])
            l_, h_ = float(lo[tq]), float(hi[tq])
            band = f'{B.usd(l_, 1)}–{B.usd(h_, 1)}bn'
            # 「高出上沿」这类定性词也得跟着算出来的幅度走：折出来的美元只比上沿高万分之几时，
            # 印「高出上沿0.0%」就是一句自己打自己的话（early-build 回放的 2026-06 正是这样）。
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
            s5 = (f'与{tq}指引对表：三个月已全部公布，按月营收折出的美元合计'
                  f'<b>{B.usd(der, 1)}bn</b>（推导值，用该季实现均汇率{float(fxq[qp]):.2f}），'
                  f'{where}。')
    else:
        lq = [q for q in g.index if np.isfinite(float(g_act.get(q, np.nan)))][-1]
        a_, l_, h_ = float(g_act[lq]), float(lo[lq]), float(hi[lq])
        # 「落在区间的 N% 位置」只有 N 在 0-100 之间才是句人话：实际值冲过上沿时它会印出
        # 「落在指引区间的209%位置」（回放 2025-06 正是这样），自己就把「落在区间内」推翻了。
        # 越界改用与上面 k>=3 那支同一套措辞（高出上沿 / 低于下沿），不另造词。
        if h_ > l_ and l_ <= a_ <= h_:
            where = f'落在指引区间的{(a_ - l_) / (h_ - l_):.0%}位置'
        elif a_ >= h_:
            where = f'高出指引区间上沿{(a_ / h_ - 1) * 100:.1f}%'
        else:
            where = f'低于指引区间下沿{(1 - a_ / l_) * 100:.1f}%'
        s5 = (f'指引侧本轮无新区间可对：最近一个有实际值的{lq}{where}，'
              f'下季区间要等业绩会才有。')

    if not s5:
        # 指引整段拿不到时（源表 2023Q1 之前根本没有区间）不能只是留白：少这一句，
        # 整页会撞上 render 的字数下限而发不出去 —— 那是拿页面的可发布性换一段解读。
        # 换一条不依赖指引的位置判断：三月均值同比把单月噪音抹平，它与单月同比的差
        # 就是「这个月是把趋势往上拐还是往下拐」。方向词由差值当场定，不预设。
        m3s = rev.rolling(3).mean().values.astype(float)
        if i >= 14 and B.need(m3s[i], m3s[i - 12], yd[i]) and m3s[i - 12]:
            t3 = m3s[i] / m3s[i - 12] - 1
            d = yd[i] - t3 * 100
            s5 = (f'再看趋势位置：三月均值同比{B.pct(t3)}把单月噪音抹平，'
                  f'单月同比比它{"高" if d >= 0 else "低"}{abs(d):.1f}pp，'
                  f'本月把均值往{"上" if d >= 0 else "下"}拐。')

    return B.render([s1, s2, s3, s4, s5])


def main():
    df, fx, g = load()

    rev = df['revenue_ntd_mn'].astype(float)
    LATEST = rev.index[-1]

    # ── 派生序列（逐行对齐 build_tsm.py）──
    rev_bn = rev / 1000.0
    rev_3ma = rev.rolling(3).mean() / 1000.0
    ytd_bn = rev.groupby(rev.index.year).cumsum() / 1000.0
    qkey = rev.index.asfreq('Q')
    qtd_bn = rev.groupby(qkey).cumsum() / 1000.0
    ttm = rev.rolling(12).sum()
    share_ttm = rev / ttm * 100          # ttm 只剩这一个用途：汇总表的「占 TTM 比重」行
    yoy = df['yoy_pct'].astype(float)                    # 公司公告的 y/y

    fx_al = fx.reindex(rev.index)
    if fx_al.isna().any():
        miss = [str(p) for p in fx_al.index[fx_al.isna()]]
        raise SystemExit(f'series/tsm_fx.csv 缺月份 {miss}')
    rev_usdmn = rev / fx_al                              # 假设：按当月平均汇率折算
    # 口径全部走 build/yoy.py。营收是流量（可加总），故 kind=FLOW。
    yoy_usd = Y.mom_yoy(rev_usdmn, Y.FLOW)
    fx_contrib = yoy - yoy_usd                           # 同比之差 = 汇率贡献（pp）

    # 本脚本自算的单月同比（Ex5 的 NT$ 线、Ex9 校验用）与 12 个月滚动合计同比（Ex2 右轴）
    yoy_self = Y.mom_yoy(rev, Y.FLOW)
    yoy_ttm = Y.ttm_yoy(rev, Y.FLOW)

    # ── 季度指引 vs 实际 ──
    g['qlabel'] = [x[:4] + 'Q' + x[-1] for x in g['quarter']]
    g = g.set_index('qlabel')
    g_mid = (g['guide_low_usdbn'].astype(float) + g['guide_high_usdbn'].astype(float)) / 2
    g_act = pd.to_numeric(g['actual_rev_usdbn'], errors='coerce')
    # 季度平均汇率：指引桥按已实现汇率重算那一版要用（brief 里唯一的用途）。
    fxq = fx_al.groupby(qkey).mean()

    # ── x 轴标签 ──
    ALL = list(rev.index)
    XL_LONG = [mlab(p) for p in ALL]
    XL13 = [mlab(p) for p in ALL[-13:]]

    def win_labels(n):
        return [mlab(p) for p in ALL[-n:]]

    # ══════════════════ Exhibit 1：汇总表 ══════════════════
    cur, prv, yag = ALL[-1], ALL[-1] - 1, ALL[-1] - 12
    heads = [mlab(cur), mlab(prv), mlab(yag), 'm/m', 'y/y', '3Y %ile']

    def pctile_cell(s, inv=False):
        """3Y %ile 单元格 + 留空原因；判据与算法全部走 build/pctile.py，本页不再自己实现。

        原来这里是一版本地代理判据「近 36 个月里 diff>=0 占比 ≥90% 就留空」，它拦不住
        3-month moving avg. 那一行：平滑序列上下都在动（代理只算出 77%，过不了 90% 那关），
        可它的分位照样常年钉在 100 —— 回放最近 24 个月是 [100×17、97×3、94×2、91×2]，
        17/24 钉在 100、整段区间只有 91–100。分位比的是水平值不是变化，所以形状代理必然漏。
        新判据直接测「这一列在过去两年里有没有区分度」：≥70% 的月份钉在极值就留空。
        分位是**口径**，口径只能有一处定义（同一条序列在两页判成两个结果正是各写各的后果）。
        """
        vals = [None if v is None or not np.isfinite(float(v)) else float(v) for v in s.values]
        txt, cls = pctile.cell(vals, inverse=inv)
        if not txt:
            return {'v': ''}, pctile.why_blank(vals)
        return {'v': txt, 'cls': cls}, None

    def chg(a, b, mode):
        if not (np.isfinite(a) and np.isfinite(b)):
            return None
        if mode == 'pp':
            return float(a - b)
        if b == 0 or a * b < 0:
            return None
        return float(a / b - 1) * 100

    def chg_txt(v, mode, inv=False):
        """比率类用 pp/bp（|v|<1 用 bp），其余用百分比变化。返回 (文本, cls)。"""
        if v is None:
            return '', ''
        good = (v < 0) if inv else (v > 0)
        cls = 'pos' if good else ('neg' if v != 0 else '')
        if mode == 'pp':
            txt = f'{v * 100:+.0f}bp' if abs(v) < 1 else f'{v:+.2f}pp'
        else:
            txt = f'{v:+.1f}%'
        return txt, cls

    # 末位 cum = True 标记「周期内累计」序列（QTD/YTD）—— 跨期归零的锯齿序列，
    # 它的 m/m 与 3Y %ile 两列在结构上就没有信息，一律留空（详见循环里的注释）。
    SUM_ROWS = [
        ('group', 'Revenue', None, None, None, None, None, False),
        ('row', 'Monthly revenue (NT$bn)', rev_bn, 1, False, 'ratio', False, False),
        ('row', '3-month moving avg. (NT$bn)', rev_3ma, 1, False, 'ratio', False, False),
        ('group', 'Cumulative', None, None, None, None, None, False),
        ('row', 'Quarter-to-date (NT$bn)', qtd_bn, 1, False, 'ratio', False, True),
        ('row', 'Year-to-date (NT$bn)', ytd_bn, 1, False, 'ratio', False, True),
        ('group', 'Seasonality', None, None, None, None, None, False),
        ('row', '% of trailing-12-month revenue', share_ttm, 2, True, 'pp', False, False),
    ]
    srows, blanked, short_blanked, cum_blanked = [], [], [], []
    for kind, lab, s, dec, pct, mode, inv, cum in SUM_ROWS:
        if kind == 'group':
            srows.append({'kind': 'group', 'label': lab})
            continue
        c = float(s.get(cur, np.nan))
        p1 = float(s.get(prv, np.nan))
        p12 = float(s.get(yag, np.nan))
        mm, yy = chg(c, p1, mode), chg(c, p12, mode)
        mtx, mcls = chg_txt(mm, mode, inv)
        ytx, ycls = chg_txt(yy, mode, inv)
        if cum:
            # 周期内累计行的两列结构性噪音，一并留空：
            #  · m/m：同期内分子分母只差一个月，恒等于「上月累计 + 当月营收」
            #    （Jun-26：827.7 + 442.7 = 1,270.4 → +53.5%），跨期时又变成 1 个月比
            #    3/12 个月（Jan-26 会印 QTD −61.6%、YTD −89.5% 并涂红，而当月 y/y 是 +36.8%）。
            #    两种情形都不可比，且符号由日历位置决定 —— 算出来再上色只会误导。
            #  · 3Y %ile：分位池混装 1/2/3 个月量纲的累计值，读数由「本月是期内第几个月」
            #    决定 —— 实测季内第 1/2/3 月分别锚在 29–43 / 77–89 / 97–100，组间差碾压组内差。
            #    （pctile36 的单调判据抓不住这种带周期重置的锯齿：YTD diff>=0 占比 0.914 会留空，
            #    QTD 只有 0.686 就漏过去了 —— 漏过去纯粹因为它归零更频繁，不是因为更有信息。）
            # 可比的口径是 y/y：QTD 是 3 个月 vs 3 个月、YTD 是 6 个月 vs 6 个月，保留。
            mtx, mcls = '', ''
            cum_blanked.append(lab)
        if cum:
            pcell = {'v': ''}
        else:
            pcell, why = pctile_cell(s, inv)
            if why:
                (short_blanked if '样本不足' in why else blanked).append(lab)
        srows.append({'label': lab, 'cells': [
            {'v': f(c, dec, pct), 'cls': 'cur'},
            {'v': f(p1, dec, pct)},
            {'v': f(p12, dec, pct)},
            {'v': mtx, 'cls': mcls},
            {'v': ytx, 'cls': ycls},
            pcell,
        ]})

    summary = {
        'title': f'TSMC monthly revenue summary — {mlab(cur)}',
        'heads': heads,
        'sep': 3,
        'rows': srows,
        'note': ('All figures derived from the single officially disclosed field: consolidated '
                 'net revenue (NT$mn, unaudited)。'
                 '「3Y %ile」= 当月读数在最近 36 个月中高于多少百分比的观测，分位越高越极端；'
                 '比率行（占 TTM 比重）的 m/m、y/y 一律用百分点差（|差|&lt;1pp 时改用 bp），'
                 '不用「百分比的百分比变化」。'
                 + (f'周期内累计的行（{"、".join(cum_blanked)}）的 m/m 与 3Y %ile 已一并留空：'
                    'm/m 的分子分母在同一期内只差一个月（本期累计 = 上月累计 + 当月营收），'
                    '跨期时又变成 1 个月比 3／12 个月，两种情形都不可比，正负号只反映日历位置；'
                    '分位则由「本月是期内第几个月」决定 —— 季内第 1／2／3 个月分别锚在约 '
                    '30／80／100，与经营好坏无关。这两行的可比读数是 y/y'
                    '（QTD 为 3 个月 vs 3 个月、YTD 为 6 个月 vs 6 个月），已保留。'
                    if cum_blanked else '')
                 + '分位判据统一走 <code>build/pctile.py</code>（全站一份实现，避免同一条序列'
                   '在两页判成两个结果）：把该行的分位在最近 24 个月里逐月回放一遍，'
                   '若 ≥70% 的月份钉在 100 或 0，这一列对这一行就没有区分度，留空。'
                 + (f'本轮据此留空的行：{"、".join(blanked)}'
                    '（平滑序列比原始月度序列更单调，分位常年在 91–100 之间，'
                    '看着像「又创新高」，其实只是三个月均值本来就很少回落）。'
                    if blanked else '本轮无行触发该判据。')
                 + (f'另有 {"、".join(short_blanked)} 因可用样本不足 8 个月，分位算不出可信读数，'
                    '一并留空。' if short_blanked else '')),
    }

    # ══════════════════ Exhibit 2..9 ══════════════════
    ex = []

    # ── Exhibit 2：GS 台股月营收核心图（Hon Hai / Wistron Exhibit 1 版式），win=20 ──
    W2 = 20
    # 右轴口径从单月改成 12 个月滚动合计（CONTRACT.md §6 对流量的默认）。
    # 差多少不引用别页的例子，用**本序列自己**实测；caliber_diff 先把两种口径对齐到
    # 「都有值」的月份再统计，否则「滚动少 12 个月历史」这个样本效应会被读成口径效应。
    CAL2 = Y.caliber_diff(rev, Y.FLOW, win=W2)
    ex.append({
        'n': 2, 'kind': 'gs_bar', 'height': 300,
        'title': f'TSMC monthly revenues（右轴 = {Y.TTM_WIN} 个月滚动合计同比）',
        'xlabels': win_labels(W2), 'xrot': 90,
        'ylab': 'NT$bn', 'ylab2': f'% y/y（{Y.TTM_WIN}M 滚动合计）',
        'legend': 'Reported', 'fmt': 'f0', 'label_fmt': 'f0',
        'values': L(rev_bn.iloc[-W2:].values),
        # deck 的 rev_bar_yoy 就是「柱 + 次轴金色 y/y + 末点 +68%」，没有均线；
        # 给了 yoy 之后引擎不画 12 个月均线，正好对上。
        'yoy': {'name': f'{Y.TTM_WIN} 个月滚动合计的同比（RHS）', 'color': 'GOLD',
                'values': L(yoy_ttm.iloc[-W2:].values), 'yfmt': 'pct0'},
        'src_extra': (f'Gold line = {Y.TTM_WIN}-month rolling-sum y/y (RHS)。'
                      'PDF 版这条线画的是单月同比，网页版按 CONTRACT.md §6 改用滚动口径。'),
        'note': ('<b>柱与线是两种口径，这不是笔误</b>：柱是公司公告的<b>单月</b>合并营收'
                 '（NT$mn，此处换算成 NT$bn 显示）；右轴金线是'
                 f'<b>{Y.TTM_WIN} 个月滚动合计的同比</b>（最近 {Y.TTM_WIN} 个月营收合计 ÷ '
                 f'上一个 {Y.TTM_WIN} 个月合计 − 1）。'
                 '<b>所以不要拿相邻两根柱去除，除出来的是单月同比、跟这条线不是一个数。</b>'
                 '单月同比仍在页内可读：汇总表的 y/y 列、Exhibit 5 的深藏青线、'
                 'Exhibit 9 的热力矩阵，以及页顶 brief 里标明「单月」的读数。' + Y.describe(CAL2)
                 + '台湾月营收的单月同比同时被三件事推着走 —— 当月天数、农历年在 1 月还是 '
                 '2 月、以及去年同月那一个数本身的高低；任意连续 '
                 f'{Y.TTM_WIN} 个月覆盖同样的日历，这三件事在滚动口径里自己抵消掉了，'
                 '代价是转折点晚半年才显形。'
                 f'滚动同比要 {Y.TTM_WIN} 个月填窗 + {Y.TTM_WIN} 个月比较才有第一个点，'
                 f'本图窗口 {W2} 个月里有 '
                 f'{int(yoy_ttm.iloc[-W2:].notna().sum())} 个月画得出线'
                 f'（序列自 {mlab(ALL[0])} 起共 {len(ALL)} 个月，够长）。'
                 '本图从 <code>bar_line_dual</code> 换成 <code>gs_bar</code>：前者在引擎里'
                 '没有柱值标签分支，而 PDF 版每隔一根柱竖排标了 NT$bn 整数、并在 y/y 线末点'
                 '标了当月读数，换图型是为了把这两组数值补回来（窄屏上标签会自动抽稀，'
                 '被抽掉的值在「表格」视图里一个不少）。代价是柱色由深藏青变成 gs_bar 固定的'
                 '浅蓝 —— 那仍是本套色板里的柱色，只是与 PDF 的深藏青不同，是本图唯一的偏离。'),
    })

    # ── Exhibit 3：月度 → 季度桥（当季未满月份浅色），win=14 ──
    W5 = 14
    qsum = (rev_bn.groupby(qkey).sum())
    qcnt = rev_bn.groupby(qkey).count()
    qv = qsum.values
    qyoy = np.array([(qv[i] / qv[i - 4] - 1) * 100 if i >= 4 and qv[i - 4] else np.nan
                     for i in range(len(qv))])
    n_in_last = int(qcnt.iloc[-1])
    qd = qsum.iloc[-W5:]
    ex5 = {
        'n': 3, 'kind': 'qtr_bar',
        'title': 'Monthly revenue aggregated to quarters',
        'xlabels': [str(p) for p in qd.index], 'xrot': 90,
        'values': L(qd.values), 'fmt': 'f0c', 'label_fmt': 'f0c',
        'ylab': 'NT$bn', 'legend': 'Complete quarter',
        'partial_months': n_in_last, 'qtr_months': 3,
        'line': {'name': 'y/y (RHS)', 'color': 'GREEN',
                 'values': L(pd.Series(qyoy, index=qsum.index).iloc[-W5:].values), 'yfmt': 'pct0'},
        'note': ('季度值 = 该季已公布月份的 NT$ 营收直接相加，不做任何调整。'
                 + (f'本期 {qd.index[-1]} 已满 3 个月，是完整季度；'
                    if n_in_last >= 3 else
                    f'本期 {qd.index[-1]} 只公布了 3 个月中的 {n_in_last} 个月，末柱画成浅蓝，'
                    f'且右轴 y/y 的最后一点已被图表引擎强制作废（{n_in_last} 个月累计'
                    '对上年完整 3 个月不可比）；')
                 + '这张图是「用月营收抢跑季报」的核心图，但季报口径含其他收入项，与本表不完全相等。'),
    }
    # 「左轴被拉到负区、代价多大、引擎到底对没对齐」这三件事全部由 align_sim 现算 ——
    # 原文写死「约占左轴量程的 29%」，那是某一轮的读数，随每月新数据变；更要命的是
    # 后半句的结论（对齐 or 不对齐）由这个数与 38% 阈值的大小关系决定，
    # 数变了而话不变，就会出现「图注说对齐了、图上其实没对齐」。
    _a5 = align_sim(ex5)
    if _a5 is None or _a5['waste'] <= 1e-9:
        ex5['note'] += ('本图右轴 y/y 在窗口内不跨零，两轴零点本来就同高，'
                        '左轴自 0 起，与 PDF 一致。')
    elif _a5['aligned']:
        ex5['note'] += (
            f'右轴 y/y 跨零，按引擎「两轴零点必须同高」的硬规矩，左轴被迫向下扩到 '
            f'{_a5["lo"]:,.0f}（NT$bn），柱因此压在画布上半张 —— '
            f'与 PDF（matplotlib 不对齐零点）观感不同，数值一致。'
            f'这一处是<b>明知的取舍</b>：对齐扩出来的无数据区占左轴量程的 {_a5["waste"]:.0%}，'
            f'低于引擎「浪费 >{ALIGN_WASTE_MAX:.0%} 就改为不对齐并标注」的兜底阈值，'
            f'所以这里仍然对齐。宁可空掉这一段画面也要对齐，是因为读者的默认假设就是'
            f'「柱在零线之上、点在零线之下」同号 —— 零点错位而不说明，比留白更容易读错。')
    else:
        ex5['note'] += (
            f'右轴 y/y 跨零，但对齐两轴零点要把左轴一路扩到 {_a5["alo"]:,.0f}（NT$bn）、'
            f'浪费掉量程的 {_a5["waste"]:.0%}（超过引擎 {ALIGN_WASTE_MAX:.0%} 的兜底阈值），'
            f'<b>所以本图两轴各自缩放、零点不同高</b>，引擎已在绘图区左上角标出。'
            f'读柱与读点时不要假设「都在零线同一侧就是同号」。')
    ex.append(ex5)

    # ── Exhibit 4：环比变化率（与 Ex2 成对），win=25 ──
    W4 = 25
    mom_all = rev.pct_change(1) * 100
    ex.append({
        'n': 4, 'kind': 'gs_line', 'fmt': 'pct1',
        'title': 'Month-on-month revenue change',
        'xlabels': win_labels(W4), 'xrot': 90,
        'ylab': '% m/m', 'zero_line': True,
        'values': L(mom_all.iloc[-W4:].values),
        'note': ('环比不做季节调整。台湾半导体的月营收有很强的日历效应（2 月天数少、'
                 '农历年错位），单月 m/m 不能当趋势读；季内进度请看汇总表的 '
                 'Quarter-to-date 一行，那是实测累计，不是外推。'),
    })

    # ── Exhibit 5：汇率贡献拆分 —— NT$ vs US$ 增速，win=25 ──
    W8 = 25
    # 本图保留单月口径，但**理由要拿数据说**（不是「存量不能滚动」那类一般性说辞）：
    # 下面这一次实测直接印进图注，读者能看到放弃滚动口径的代价有多大。
    CAL8 = Y.caliber_diff(rev, Y.FLOW, win=W8)
    ex.append({
        'n': 5, 'kind': 'lines_endlabels', 'fmt': 'pct0',
        'title': 'Revenue growth: NT$ vs. US$（单月同比 / single-month y/y）',
        'xlabels': win_labels(W8), 'xrot': 90, 'ylab': '% y/y（单月）',
        'series': [
            {'name': 'NT$ revenue y/y (as reported)', 'color': 'NAVY', 'values': L(yoy.iloc[-W8:].values)},
            {'name': 'US$ revenue y/y (converted)', 'color': 'MBLUE', 'values': L(yoy_usd.iloc[-W8:].values)},
        ],
        'src_extra': 'The gap between the two lines is the currency contribution. ' + ASSUMP,
        'note': ('US$ 线是<b>推导值（Implied）</b>：NT$ 月营收 ÷ 当月平均 NTD/USD，'
                 '不是公司披露的美元营收。假设：全部营收按当月平均汇率一次性折算，'
                 '忽略月内汇率路径、对冲与递延收款，因此这条线只能看方向与量级。'
                 f'<b>本图两条线都是单月同比</b>，与 Exhibit 2 右轴的 {Y.TTM_WIN} 个月滚动口径'
                 '<b>不是一个数</b>：本图讲的是「公司这个月报出来的增速里有多少是汇率」，'
                 'NAVY 线的线名写着 as reported，换成滚动口径它就不再是公司报的那个数了。'
                 f'口径差异用本序列自己实测（{CAL8["n"]} 个两种同比都有值的月份）：'
                 f'NT$ 单月同比逐月标准差 {CAL8["std_mom"]:.1f}pp、'
                 f'{Y.TTM_WIN} 个月滚动 {CAL8["std_ttm"]:.1f}pp，'
                 f'相邻月跳变中位 {CAL8["medjump_mom"]:.1f}pp vs {CAL8["medjump_ttm"]:.1f}pp，'
                 f'窗口内两者<b>符号相反的月份 {CAL8["opposite_n"]} 个</b>'
                 + ('（'
                    + '；'.join(f'{m} 单月 {a:+.1f}% vs 滚动 {b:+.1f}%'
                               for m, a, b in CAL8['opposite'][:3]) + '）。'
                    if CAL8['opposite_n'] else '。')
                 + f'当期并排：单月 {sgn(float(yoy.iloc[-1]))}、滚动 '
                 f'{sgn(float(yoy_ttm.iloc[-1]))}。'),
    })

    # ── Exhibit 6：汇率对报表增速的贡献，win=25 ──
    W9 = 25
    fcd = fx_contrib.iloc[-W9:]
    # 口径同 deck 的 lvl_bar：pct_series 的同比是百分点差，月度序列 ⇒ lag = 12。
    # 走 yoy.mom_yoy(kind=RATIO)：比率序列的同比是 a − b（百分点），不是 (a/b−1)。
    # 自己写 .diff(12) 也得同一个数，但口径判断从此只有一处定义。
    fcd_yoy = Y.mom_yoy(fx_contrib, Y.RATIO).iloc[-W9:]
    ex.append({
        'n': 6, 'kind': 'grouped_bars',
        'title': 'Currency contribution to reported growth（单月同比之差）',
        'xlabels': win_labels(W9), 'xrot': 90,
        'groups': [{'name': 'Currency contribution', 'color': 'BLUE', 'values': L(fcd.values)}],
        'line': {'name': 'y/y change (pp, RHS)', 'color': 'GOLD',
                 'values': L(fcd_yoy.values), 'yfmt': 'pp0'},
        # 25 根柱在半栏卡片上 band 只有 20px、窄屏更掉到 10px 出头，而「+10.6pp」实测宽
        # 22px —— 逐柱标签必然连成一串（人眼审查把「+6.3pp+6.4pp」列为整页最扎眼的一处）。
        # 引擎的标签抽稀只对「一个 x 一个标签」的图型生效，并排柱图型按步长抽不掉，
        # 所以这里按 PDF 版的做法收手：deck 在 win>14 时本来也只标每隔一根，
        # 网页版「25 根全标」是它自己加的，正是压字的来源。数值改由 tooltip 与「表格」视图给全。
        'bar_labels': False, 'fmt': 'pp1', 'label_fmt': 'pp1',
        'ylab': 'pp of y/y', 'ylab2': 'pp y/y',
        'src_extra': ('NT$ y/y less US$ y/y. Positive = a weaker NT dollar flattered the reported '
                      'number. ' + ASSUMP),
        'note': ('本图是 Exhibit 5 两条线之差，单位是百分点，不是百分比；'
                 '<b>两条线都是单月同比，所以本图也是单月口径</b>'
                 f'（与 Exhibit 2 右轴的 {Y.TTM_WIN} 个月滚动口径不可直接对读）。'
                 '右轴金线是 PDF 版就有的次轴同比，本轮补回 —— 柱本身已是比率之差，'
                 '所以它的同比同样取<b>百分点差</b>（当月贡献 − 去年同月贡献），'
                 f'读作「汇率这条腿比一年前多贡献/少贡献了几个点」（本月 {sgn(float(fcd_yoy.iloc[-1]), 1, "pp")}）。'
                 '柱顶不再逐根标数值：25 根柱的 band 只有 20px 上下，'
                 '而「+10.6pp」这样的标签就有 22px 宽，全标必然叠字；'
                 'PDF 版在窗口超过 14 期时也只标每隔一根。'
                 '逐月读数请点右上角「表格」，或把鼠标停在任意一列上。'
                 'PDF 版同样是 gsx.lvl_bar；网页 gs_bar 纵轴自 0 起会把 −14.1pp 那根柱'
                 '画到画布外，故柱仍用单组 grouped_bars（含负值）。'),
    })

    # ── Exhibit 7：GS HKEX 式超长历史层 ──
    ex.append({
        'n': 7, 'kind': 'lines', 'full': True, 'height': 300, 'x': 'long',
        'title': 'Full monthly revenue history since 2016',
        'fmt': 'f0', 'ylab': 'NT$bn', 'xstep': 9, 'xrot': 90,
        'zero_base': True, 'end_label': True,
        'series': [{'name': 'Monthly revenue (NT$bn)', 'color': 'NAVY', 'values': L(rev_bn.values)}],
        'src_extra': (f'Full disclosed history since {mlab(ALL[0])}（共 {len(ALL)} 个月）。'
                      'PDF 版在末端画了一个红色虚线椭圆圈出最近 3 个月，网页引擎无此图元，已省略。'),
        'note': ('纵轴自 0 起（<code>zero_base</code>，同 PDF 的 ylim(0, max×1.16)），'
                 '所以看得出的是量级台阶而不是月度噪音；月度波动请看 Exhibit 2。'
                 '末点加粗标出最新一个月的读数 —— 长历史图上刻度间隔上百，'
                 '这是全图唯一的绝对水平锚点（PDF 版的 n_label 同此，网页版原先漏掉了）。'),
    })

    # ── Exhibit 8：NTD/USD 月均汇率（超长历史层）──
    ex.append({
        'n': 8, 'kind': 'lines', 'full': True, 'height': 300, 'x': 'long',
        'title': 'NTD per USD, monthly average',
        'fmt': 'f1', 'ylab': 'NTD per USD', 'xstep': 9, 'xrot': 90, 'end_label': True,
        'series': [{'name': 'NTD per USD (monthly avg.)', 'color': 'NAVY', 'values': L(fx_al.values)}],
        'src_extra': ('本图与 TSMC 的月营收公告无关，'
                      + SRC_FX
                      + ' Roughly 70% of TSMC revenue is US-dollar denominated but reported '
                        'in NT$, so this rate moves the headline.'),
        'note': ('纵轴按数据范围自适应，未照 PDF 那样自 0 起 —— 28~34 的汇率压在 0 起点的轴上'
                 '会变成一条直线，看不出 2025 年那波急升。这是本页唯一一处刻意偏离 PDF 的轴设置；'
                 '正因为轴不自 0 起，末点的绝对读数已按 PDF 的 n_label 标出，'
                 '免得只能靠刻度目测水平。'),
    })

    # ── Exhibit 9：同比热力矩阵（n_years=9）──
    NH = 9
    hyrs = sorted({p.year for p in yoy.dropna().index})[-NH:]

    def heat_cell(v):
        """格内按 f0 显示，|v| < 0.5 的月份统一写成正零。

        原来 2018-12 的 −0.1% 会被 toFixed(0) 印成「-0」：在一整片两位整数里，
        负零是个纯格式化产物，读者会停下来判断它是不是缺失值（缺失格本来是浅灰空格）。
        这里只把落在同一个显示档位里的负号抹掉 —— ±0.4 本来就都印 0，
        所以显示口径没变；真值仍在 series/tsm.csv 与公司公告里。
        """
        f = float(v)
        return 0.0 if abs(f) < 0.5 else f

    matrix = []
    for y in hyrs:
        row = [None] * 12
        for p, v in yoy.dropna().items():
            if p.year == y:
                row[p.month - 1] = num(heat_cell(v), 4)
        matrix.append(row)
    ex.append({
        'n': 9, 'kind': 'heat_matrix', 'full': True,
        'title': 'Monthly revenue y/y growth (%)',
        'rows': [str(y) for y in hyrs], 'cols': MONTHS, 'matrix': matrix,
        'fmt': 'f0', 'legend': 'Revenue y/y (%)', 'row_head': '年', 'cell_h': 21,
        'src_extra': ('Green = faster y/y growth, red = slower; blanks are months not yet reported. '
                      '色标取全部有限值的 5/95 分位。'),
        'note': ('格内是公司随月营收公告的 y/y 原值（series/tsm.csv 的 yoy_pct），'
                 '不是本脚本算的。空格是尚未公布的月份。'
                 '数值四舍五入到整数；|y/y| 不足 0.5pp 的月份一律写 0，不写「−0」'
                 f'（本表命中 {sum(1 for p, v in yoy.dropna().items() if p.year in hyrs and abs(v) < 0.5)} 格）。'),
    })

    # ══════════════════ 轴刻度收口（必须排在 notes 之前）══════════════════
    # 轴刻度小数位：引擎默认格式器把 2.5 印成「3」、把 0.25 步长整列印成重复/错值，
    # 判据与算法见 build/axisfmt.py（与 build/single.py 共用同一份）。
    # **位置很要紧**：axisfmt 除了改格式器，还会给「柱图型出现负值」的图补 ycap/yfloor
    # （否则柱会画到画布外）。而下面 BRK_NOTE 那句「本页有没有截轴」是**现读 payload**
    # 生成的 —— 若 fix_all 排在它后面，某个月一旦真触发那条兜底，图上有截轴而图注说没有，
    # 又是一处「图注声称的与图上画的对不上」。所以先收口，再让文案去读最终结果。
    axisfmt.fix_all(ex)

    # ══════════════════ 末尾核对表 ══════════════════
    T = 13
    trows = []
    for p in ALL[-T:]:
        trows.append({
            'xl': mlab(p),
            'rev': f(rev.get(p), 0),
            'yoy': f(yoy.get(p), 1),
            'fx': f(fx_al.get(p), 4),
            'usd': f(rev_usdmn.get(p), 0),
        })
    table = {
        'n': 10,
        'title': f'近 {T} 个月核对表（官方原始单位，未换算）',
        'idx': '月份',
        'cols': [['Consolidated revenue (NT$mn)', 'rev'],
                 ['y/y (%) — as disclosed', 'yoy'],
                 ['NTD/USD (monthly avg.)', 'fx'],
                 ['Implied revenue (US$mn)', 'usd']],
        'rows': trows,
    }

    # ══════════════════ 抬头 ══════════════════
    cur_rev_bn = float(rev_bn.iloc[-1])
    cur_yoy = float(yoy.iloc[-1])
    cur_mom = float(mom_all.iloc[-1])
    cur_q = qsum.index[-1]
    cur_q_bn = float(qsum.iloc[-1])
    # 抬头的当季 y/y 必须与 Exhibit 1 的 Quarter-to-date 行同口径：当季已公布的 n 个月，
    # 比上年同季的**同样前 n 个月**（qtd_bn 是季内逐月累计，同一日历月天然是同一个 n，
    # n=3 时退化成整季比整季，与 qyoy[-1] 相等）。qyoy[-1] 在季内第 1/2 个月是
    # 「n 个月 vs 上年完整 3 个月」，会把 +44.7% 的 Jul-26 印成 −53% 并涂红，
    # 与同页表格自相矛盾 —— Ex3 右轴末点早已因此被图表引擎作废，抬头当时漏了同样处理。
    q_now, q_yag = float(qtd_bn.get(cur, np.nan)), float(qtd_bn.get(yag, np.nan))
    cur_q_yoy = (q_now / q_yag - 1) * 100 if np.isfinite(q_yag) and q_yag else float('nan')
    ytd_now = float(ytd_bn.iloc[-1])
    ytd_prev = float(ytd_bn.get(ALL[-1] - 12, np.nan))
    ytd_yoy = (ytd_now / ytd_prev - 1) * 100 if np.isfinite(ytd_prev) and ytd_prev else float('nan')
    cur_usd_yoy = float(yoy_usd.iloc[-1])
    cur_fx_pp = float(fx_contrib.iloc[-1])
    cur_ttm_yoy = float(yoy_ttm.iloc[-1])
    # 「公司原值 vs 本脚本自算」差多少：写死「±0.1pp」会在某个月变成假话，这里现算。
    _self_d = (yoy - yoy_self).dropna().abs()
    SELF_N, SELF_MAXD, SELF_MEDD = len(_self_d), float(_self_d.max()), float(_self_d.median())

    headline = (f'{mlab(cur)} 合并营收 NT${cur_rev_bn:,.1f}bn（{sgn(cur_yoy)} y/y、{sgn(cur_mom)} m/m）'
                f' · {cur_q} 累计 NT${cur_q_bn:,.0f}bn（{sgn(cur_q_yoy, 0)} y/y，'
                f'{n_in_last} of 3 months' + ('' if n_in_last >= 3 else '，比上年同季前同样月数') + '）'
                f' · YTD NT${ytd_now:,.0f}bn（{sgn(ytd_yoy, 0)} y/y）'
                f' · 美元口径 y/y {sgn(cur_usd_yoy, 0)}，汇率贡献 {sgn(cur_fx_pp, 1, "pp")}')
    hub_line = f'{mlab(cur)} 营收 NT${cur_rev_bn:,.0f}bn，{sgn(cur_yoy, 0)} y/y；YTD {sgn(ytd_yoy, 0)} y/y'

    # 页顶 ~300 字数据总结：headline 给读数，brief 给「这个读数该怎么读」，
    # 因此刻意不复述 headline 与 Exhibit 1 已经印过的数字（见 build/brief.py 头部）。
    brief_html = compose_brief(ALL, rev, yoy, fx_al, fx, mom_all, qsum, qcnt, fxq, g, g_mid, g_act)

    # 「本页有没有断点线 / 截轴」这句话现读 payload，不写死散文。
    # 全站复查报过 7 条「图注声称画了断点线、图上其实没有」的自相矛盾，根因都是
    # 注释是手写常量、而 break_at 会随窗口往前滚而消失。这里让文案跟着数据走：
    # 哪天真给某张图加了 break_at / ycap，这一段自己改口；改不动就说明没加成。
    _BRK = [str(e['n']) for e in ex if e.get('break_at') is not None]
    _CAP = [str(e['n']) for e in ex if e.get('ycap') is not None or e.get('yfloor') is not None]
    BRK_NOTE = (
        '⚠️ <b>口径断点与截轴</b>：TSMC 月营收自 2016-01 起口径连续，未发生并表或重述，'
        + ('本页因此没有任何 <code>break_at</code> 红色虚线'
           if not _BRK else
           f'本页在 Exhibit {"、".join(_BRK)} 上画了 <code>break_at</code> 红色虚线')
        + '，'
        + ('也没有 <code>ycap</code>／<code>yfloor</code> 截轴。'
           if not _CAP else
           f'另有 Exhibit {"、".join(_CAP)} 设了 <code>ycap</code>／<code>yfloor</code> 截轴。')
        + '这一句由本页 payload 现读生成，不是写死的说明文字 —— '
          '哪天真加了断点或截轴，它会自己改口，'
          '所以本页不会出现「图注说画了断点线、图上其实没有」这种自相矛盾。'
        # 这句括注原先写死成「Ex3 左轴扩到负区是零点对齐的结果」，可 align_sim 现在算出
        # waste=50%（超过引擎 38% 兜底），引擎早已改走两轴各自缩放那一支 —— 与 Ex3 自己
        # 那条现读生成的图注正好打架。既然上一句刚说过「不写死」，这里也跟着 payload 走。
        + ('（Exhibit 3 左轴向下扩到负区是双轴零点对齐的结果，不是截轴：没有任何点被截掉，'
           '所以图上也不该出现断轴符号或红色空心圈。）' if _a5['aligned'] else
           f'（Exhibit 3 的两轴零点<b>没有</b>对齐：对齐要把左轴一路扩到 '
           f'{_a5["alo"]:,.0f}、浪费掉 {_a5["waste"]:.0%} 量程，超过引擎兜底阈值，'
           '故两轴各自缩放，引擎已在绘图区左上角标出 —— 这同样不是截轴，没有任何点被截掉。）'))

    notes = [
        ('<b>数据源</b>：主线是 TSMC 官网 IR 月度营收公告（合并营收，NT$mn，未经会计师查核，'
         '台湾法定次月 10 日前公布）—— 除 Exhibit 8 外，本页各图与两张表全部由这一个字段'
         '加一条月均汇率序列派生，不引入任何券商预测或外部估计。'
         '例外的那一张在图脚第二行写明了自己的来源：Exhibit 8 来自 FRED EXTAUS 的月均 NTD/USD。'
         '季度业绩说明会的指引区间与假设汇率只在页顶 brief 的指引桥里出现一次，页内没有指引图。'
         '每张图共用的第一行 <i>Source:</i> 是页面级出处行（含版式出处），不是那三张图的数据源。'),
        ('<b>版式出处</b>：Goldman Sachs GIR「Hon Hai (2317.TW)」与「Wistron (3231.TW)」两份台股'
         '月营收报告的 Exhibit 1-2，外加 GS HKEX 深度的超长历史层与 JPM AXP 的季节性剥离图型。'),
        ('<b>同比口径：本页并存两种，逐处点名</b>（CONTRACT.md §6 要求）。'
         f'<b>{Y.TTM_WIN} 个月滚动合计同比</b>只有一处 —— <b>Exhibit 2</b> 的右轴金线'
         f'（最近 {Y.TTM_WIN} 个月营收合计 ÷ 上一个 {Y.TTM_WIN} 个月合计 − 1）；'
         '营收是流量、可加总，这个「合计」指代的是真实的一年营收，所以对它合法。'
         '<b>单月同比</b>（当月 ÷ 去年同月 − 1）用在 <b>Exhibit 3</b>（季度口径，3 个月比 3 个月）、'
         '<b>Exhibit 5</b>（NT$ 与 US$ 两条线）、'
         '<b>Exhibit 6</b>（两者之差，取百分点）、'
         '<b>Exhibit 9</b> 热力矩阵，汇总表与核对表的 y/y 列，'
         '以及页顶「本月读数怎么读」一段（brief）里标明「单月」的读数 —— '
         'brief 与汇总表同口径、可逐格对上，它引用的滚动读数已在句内点名 Exhibit 2 口径。'
         '这几处保留单月<b>不是漏改</b>，理由逐条不同：Exhibit 5／6 回答的是'
         '「公司这个月报出来的那个增速里有多少是汇率」，线名写着 as reported，'
         '换成滚动口径印出来的就不再是公司报的那个数；Exhibit 9 是热力矩阵、'
         'Exhibit 3 是季度对照，逐格与逐季的波动本身就是题眼；'
         '两张表的 y/y 列必须恒等于「本月 ÷ 去年同月」的表内算术 —— '
         '读者拿第一列除第三列得到的必须是同一个数，表内自相矛盾比口径混用更糟。'
         f'两种口径的当期读数并排在这里，省得跨图对：{mlab(cur)} 单月 {sgn(cur_yoy)}、'
         f'{Y.TTM_WIN} 个月滚动 {sgn(cur_ttm_yoy)}，差 {sgn(cur_yoy - cur_ttm_yoy, 1, "pp")}。'),
        ('<b>单月 y/y 有两个来源，数值上几乎重合</b>：Exhibit 9 热力矩阵与核对表用公司随公告'
         '给出的 <code>yoy_pct</code> 原值；Exhibit 3／5 由本脚本按序列自算'
         '（口径实现统一走 <code>build/yoy.py</code>，本页不再自己写 <code>pct_change(12)</code>）。'
         f'两者在 {SELF_N} 个可比月份上最大差 {SELF_MAXD:.2f}pp、中位差 {SELF_MEDD:.2f}pp，'
         '来自公司口径的四舍五入，未做人工对齐。'),
        ('<b>美元口径全部是推导值（Implied）</b>：US$ 营收 = NT$ 营收 ÷ 当月平均 NTD/USD。'
         '假设全部营收按当月平均汇率一次性折算，忽略月内汇率路径、对冲与递延收款。'
         '汇率贡献（Exhibit 6）= NT$ y/y − US$ y/y，单位是百分点。'),
        ('<b>汇率序列口径</b>：月均 NTD/USD，等价于 FRED 的 EXTAUS（该月全部营业日美联储 H.10 '
         '台湾牌价的算术平均）。TSMC 约七成营收以美元计价却以新台币入账，所以这条线直接推动报表增速。'),
        ('<b>指引区间只在页顶 brief 出现</b>：那里的美元指引来自季度业绩说明会，'
         '季度营收口径含非月营收项，与月营收累加值之间的差额同时含汇率与口径差，'
         '不可直接相减 —— 所以指引桥只报「剩余月份月均还需多少 NT$bn」，不与页内任何图对读。'
         '原先画指引区间与偏离的 Exhibit 8／9 于 2026-08 按用户要求删除。'),
        ('<b>未满季提示</b>：Exhibit 3 的末季不足 3 个月时会画成浅蓝柱，且右轴 y/y 会被图表引擎强制'
         '作废 —— 拿 2 个月累计去比上年完整 3 个月必然砸出一个假坑。'
         f'本期 {cur_q} 已含 {n_in_last} 个月，'
         + ('为完整季度，无此标记。' if n_in_last >= 3 else '故末柱与末点按上述规则处理。')),
        BRK_NOTE,
        ('<b>网页版与 PDF 版的已知差异</b>：(1) PDF 长历史图（Exhibit 7／8）末端有一个红色'
         '虚线椭圆圈出最近 3 个月，网页引擎无此图元，已省略 —— 两张图改为按 PDF 的 n_label '
         '在末点标出读数，绝对水平不至于只能靠刻度目测；(2) Exhibit 2 由 '
         '<code>bar_line_dual</code> 换成 <code>gs_bar</code>，为的是把 PDF 有、网页一直没有的'
         '柱值标签与 y/y 末点读数补回来，代价是柱色从深藏青变成 gs_bar 固定的浅蓝；'
         '(3) Exhibit 6 在 PDF 里是 <code>gsx.lvl_bar</code>，网页对应的 '
         '<code>gs_bar</code> 纵轴强制自 0 起会把负值柱画到画布外（2025-07 是 −14.1pp），'
         '故柱仍用单组 <code>grouped_bars</code>，PDF 版的次轴同比线保留；'
         '(4) Exhibit 6 的柱顶不逐根标数值'
         '（25 根柱必然叠字，PDF 版在窗口 >14 期时同样只标每隔一根），读数走「表格」视图。'
         '此外 y/y 线的金色 GOLD #BF9000 已经在网页色板里，Exhibit 2 用回金色，'
         '早前那句「网页没有金色、改用绿色」已不成立，一并更正。'),
        ('<b>汇总表的分位与累计行</b>：「3Y %ile」= 当月读数在最近 36 个月中高于多少百分比的观测，'
         '判据统一走 <code>build/pctile.py</code>（全站一份实现）：把该行的分位在最近 24 个月里'
         '逐月回放，≥70% 的月份钉在 100 或 0 就说明这一列对这一行没有区分度，留空。'
         '本页据此留空的是 <b>3-month moving avg.</b> —— 三月均值把月度波动磨平之后，'
         '分位近两年有 17／24 个月钉在 100、整段只在 91–100 之间动，'
         '印成绿色的 100 会被读成「又创新高」，其实只是平滑序列很少回落。'
         '（旧的本地判据「≥90% 月环比不降」对这一行只算出 77%，拦不住 —— 分位比的是水平值，'
         '不是变化，用形状做代理必然漏。）'
         '另外，周期内累计的序列（QTD／YTD）的 <b>m/m 与分位两列一律留空</b>，那是本页自己的'
         '口径原因、与上面的通用判据无关：分位由「本月是期内第几个月」决定'
         '（季内第 1／2／3 个月锚在约 30／80／100），m/m 则只是「上月累计 + 当月营收」的算术'
         '恒等式、跨季跨年时又变成 1 个月比 3／12 个月。这两行看 y/y'
         '（3 个月 vs 3 个月、6 个月 vs 6 个月，口径可比）。'
         '比率行的 m/m、y/y 一律用百分点（|差|&lt;1pp 时改用 bp）。'),
    ]

    payload = {
        'ticker': 'tsm',
        'tracker': 'TSMC Monthly Revenue Tracker',
        'title': f'台积电 TSMC (2330.TW / TSM)：月度营收跟踪 — {cur.year} 年 {cur.month} 月',
        'data_through': str(cur),
        'through_label': f'{cur.year} 年 {cur.month} 月',
        'subtitle': (f'数据源：TSMC 官网 IR 月度营收公告（次月 10 日前）· '
                     f'覆盖 {mlab(ALL[0])} – {mlab(ALL[-1])} 共 {len(ALL)} 个月 · '
                     f'版式仿 Goldman Sachs GIR 台股月营收报告（charts only, no commentary）'),
        'headline': headline,
        'brief': brief_html,
        'hub_line': hub_line,
        'source': SRC,
        'xlabels': XL13,
        'xlabels_long': XL_LONG,
        'summary': summary,
        'exhibits': ex,          # 已在上面过完 axisfmt.fix_all（幂等，这里不重复调）
        'table': table,
        'notes': notes,
        'footer': ('图表与派生算法源自本机 <code>monthly-op-dashboards</code> 项目，'
                   '与 <code>build/build_tsm.py</code>（PDF 版）同源 · '
                   '仅供个人研究，不构成投资建议'),
    }

    # 抬头的「官方发布于 …」：查得到才加这个字段，查不到整个字段省掉 ——
    # 渲染端（assets/page.js）判的是字段在不在，写 None 会印出「官方发布于 None」。
    sdate = source_date(str(cur))
    if sdate:
        payload['source_date'] = sdate

    # 上线前的自检：payload 里不许有 NaN / Infinity（json.dump 会写成裸字面量，
    # 浏览器 JSON 解析不了；而 window.DASH = 是 JS 求值，NaN 会被静默吞进图里）。
    # 原来这里是本地一段大小写敏感的 `'NaN' in txt` 子串检查，已并入
    # build/payload_guard.py 统一实现 —— 那版漏掉了已被 f-string 格式化进展示串的
    # 小写 nan（`f'{nan:+.1f}%'` → `'nan%'`），共用版按词边界一并抓。
    path = os.path.join(DATA, 'tsm.js')
    payload_guard.write_dash(path, payload, 'tsm')

    print(f'窗口 {ALL[0]} → {ALL[-1]}（{len(ALL)} 个月）· 季度 {qsum.index[0]} → {qsum.index[-1]}')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张）+ Exhibit {table["n"]} 核对表')
    print(headline)
    print(f'写出 data/tsm.js ({os.path.getsize(path) / 1024:.1f} KB)')


if __name__ == '__main__':
    main()
