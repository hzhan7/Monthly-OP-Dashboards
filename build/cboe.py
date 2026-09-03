# -*- coding: utf-8 -*-
"""Cboe Global Markets (CBOE) 月度成交量与 RPC —— 网页看板数据生成器。

把 build/build_cboe.py（matplotlib / PDF）的每一张 exhibit 逐张移植成 data/cboe.js 里的
payload 对象。图的顺序、编号、标题文案、窗口长度、图注全部照搬原 deck；数值全部来自
series/cboe.csv，页面不做任何计算。

模版来源：Goldman Sachs「IBKR Monthly」的成对图法与 Exhibit 6-9 的「量 x 价」处理 ——
          GS 对券商永远同时画「量」(DARTs) 与「单位价格」(CPT)，再用二者乘积画收入/日。
          Cboe 是全清单里唯一官方同时披露 ADV 与 RPC 的标的，因此这套量价框架可以
          完整复刻：ADV x RPC = 每日交易净收入的直接估算。
数据源：Cboe 官网 Monthly volume and revenue per contract (RPC) reports，次月第 3 个工作日。

⚠️ 口径断点与已知坑（详见 payload 的 notes）：
  · RPC 是**三个月滚动平均、滞后一个月发布**，不是单月数 —— 空白 RPC 不是数据缺口。
  · 2017 年数字是 Bats pro-forma combined（Cboe 2017-02 完成收购 Bats），与其后不完全可比。
  · Implied options transaction revenue 是推导值（当月 ADV × 三个月滚动 RPC），不是披露值。

与原 deck 的**有意差异**（图表引擎能力所限或可读性权衡，已在 notes 里逐条写明）：
  · Exhibit 7 原 deck 用对数轴（log=True），charts.js 只有线性轴 → 改线性 + yfloor=0。
  · Exhibit 6 原 deck 在末 3 个月画红色虚线椭圆（circle=3），charts.js 无此元件 → 不画。
  · Exhibit 9 原 deck 把三种单位画在同一根轴上 → 拆成 9a / 9b 两张单序列图
    （第三条欧股 ADNV 与 Exhibit 11 同序列同窗口，不重画）。

用法: python3 build/cboe.py     （可重复跑，除首行日期外逐字节相同）
"""
import datetime
import json
import os
import re

import numpy as np
import pandas as pd

import brief as B
import glossary as gloss                # 名词释义的版式层与护栏，全站共用
import mrwin                            # 通栏 / x 标签抽稀的裁决层，与 single.py 共用
import payload_guard
import pctile
import yoy as YOY                       # 同比口径的唯一实现，见 build/yoy.py 的模块头

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CSV = os.path.join(ROOT, 'series', 'cboe.csv')
OUT = os.path.join(ROOT, 'data', 'cboe.js')

SRC = 'Source: Cboe monthly volume and RPC reports; format after Goldman Sachs GIR'

#: 时序图窗口的左端。2026-08-18 从「近 25 个月」改成「2016-01 起」，与 build/single.py
#: 的 `WIN_FROM` 同一个口径、同一个理由：数据回补到 2016 而窗口停在近两年，等于回补给谁看。
#: 序列比它短就用序列自己的起点（只往右让、不往左借）。
WIN_FROM = '2016-01'
#: **末尾核对表**的行数 —— 这是表的窗口，不是任何一张图的窗口，也不是任何历史事实。
#: 表是拿着它和公司披露逐行对的，全序列一百多行没人对得完，所以它留在 13 行。
#: 这个常量**只**给核对表用。2026-08-19 之前 Exhibit 5 的图注也吃它（拿它当「原 deck
#: 的 13 个月窗口只看得到多少」的对照）—— 于是核对表行数一改，Exhibit 5 就会跟着宣称
#: deck 原来的窗口变了。沙盒实测（WIN_TABLE=15 跑一次）：Exhibit 5 印「原来的 15 个月
#: 窗口」，而同页「窗口长度」条里那句写的还是字面量 13，同一页两句当场打架。
#: deck 的窗口是历史事实，已挪到下面的 DECK_WIN_*，与本页的活配置分开放。
WIN_TABLE = 13
#: 原 PDF deck 的三个窗口：时序图 25 个月、堆叠占比图（Exhibit 5）13 个月、季度柱
#: （Exhibit 8）14 个季度。这些是**历史事实** —— 那份 deck 就是这么画的，不随数据变、
#: 也不随本页任何配置变，所以它们既不该写成字面量散在各处（改一处漏一处），也不该借
#: 用 WIN_TABLE 这类会动的常量。页内凡说「deck 原来是多长」一律走这三个名字。
DECK_WIN_LINE, DECK_WIN_STACK, DECK_WIN_QTR = 25, 13, 14
#: 2026-08-19：`WIN_QTR`（原 deck 的 qtr_bar 窗口）作为**窗口**已删除 —— Exhibit 8 的
#: 季度柱改吃 `Q_FROM`（= WIN_FROM 换算到季度），与 Exhibit 2/4/5/… 同一个左端。它作为
#: 历史事实活在 `DECK_WIN_QTR` 里，只进文案、不进任何切片。
HEAT_YEARS = 10     # 原 deck 的 heat_matrix n_years

# 13 是后加的一张（收入的量费分解），**追加在末尾**，原 deck 那 11 张图的编号一个都没动；
# 核对表因此由 13 顺延到 14 —— 它本来就排在所有图之后，号跟着走才不会出现
# 「12、14、13」这种读者以为漏图的序列。全文引用一律走这两个常量，不写字面量。
#
# 2026-09 删掉了原 Exhibit 14（U.S. options volume, trailing 12-month average），
# EX_TABLE 因此由 15 收回 14。理由见页尾「口径与方法说明」里那一条：那张图的金线是它自己
# 那排 12 个月均值柱的同比，而「12 个月均值的同比」逐点就等于 12 个月滚动合计同比，新口径
# 下无路可走；要保住「柱与线同源」这个它存在的唯一理由，柱只能一起换成当月值 —— 一换，
# 它就与 Exhibit 2 是**同一条序列、同一个窗口、同一个单位**（都是 series/cboe.csv 的
# adv_us_options_kcontracts ÷ 1000，Jan-16 起 127 期），金色线也是同一条单月同比。
# 复算：两边都过一遍 L() 的 round(…, 6) 之后 127 期逐点全等（最大差 0）；未舍入的重算值
# 对已舍入的 payload 值最大差 5e-7（Apr-24，就是那一次舍入），不是「相似」，是同一张图。
# 本页没有交易日数列，拿不出「当月合计张数」这个能把两张分开的口径，所以删掉而不是重画。
EX_DECOMP, EX_TABLE = 13, 14

#: 图注里凡是讲「**别的**图是什么样」的句子，写这张图的时候后面的图还没画出来，落笔的
#: 只能是作者脑子里的枚举 —— 本页因此连着三轮埋进假的全称断言（「各图」「其余各图」
#: 「各 gs_bar」）。所以这类句子一律先放占位符，等 exhibit 全部画完再现读 payload 回填；
#: 回填不到、或者回填完还剩占位符，一律停机。照抄 build/cme.py 的 `_NAV_*` 那一套。
_NAV_YOY_AX = '⟨nav:yoy-axis⟩'      # 「哪几张图的次轴走单月同比」
# 顶部 brief 用：RPC 的滚动口径。公司自己写明是 three-month rolling average（见 notes），
# 但没说是哪三个月。用「(w 三个月成交量加权的指数占比) x 指数 RPC + 余下 x 多重挂牌 RPC」
# 去复原披露的混合 RPC，对齐窗口实测只有 M-2..M 一个解：
#   M-2..M 平均绝对误差 0.10%（最大 0.72%）｜M-1..M+1 2.28%｜M..M+2 4.01%｜单月 3.42%
# 相差一个量级，不是调参调出来的。compose_brief 每次重跑都会重算这个误差并卡阈值。
RPC_WIN = 3
BRIEF_HI = 330      # brief 去标签字数的自压上界（B.render 的护栏是 230-380）。贴着上界发布
                    # 等于把「下个月名次多一位数」当成停更风险；压法见 compose_brief 末尾
RPC_FIT_TOL = 2.0   # 复原误差上限（%）。实测 0.10%，留 20 倍余量：这道闸只拦「口径变了」
                    # 那种量级的事故，不拦月度噪音（拦太紧会让整页因为一个数据毛刺永久停更）

# brief 的 R1 峰值扫描扫哪几条产品线。只放**公司单列披露的成交量**，不放派生比值
# （占比、implied 收入那些各自有图）；每条都是「越高越好」的量，故 peak_scan 不传 inverse。
# 不放美国期权总量与自有指数期权总量：它们是下面九条里若干条的合计，放进来等于把同一件事
# 数两遍，「九条里只有一条创新高」这句就不成立了。
BRIEF_LINES = [
    ('SPX 期权', 'adv_spx_options_kcontracts'),
    ('XSP 期权', 'adv_xsp_options_kcontracts'),
    ('VIX 期权', 'adv_vix_options_kcontracts'),
    ('VIX 期货', 'adv_vix_futures_kcontracts'),
    ('CFE 期货', 'adv_futures_kcontracts'),
    ('美股撮合', 'adv_us_equities_matched_shares_bn'),
    ('欧股 ADNV', 'adv_eu_equities_adnv_eurbn'),
    ('全球外汇', 'adv_fx_adnv_usdbn'),
    ('多重挂牌期权', 'adv_multilist_options_kcontracts'),
]


# ────────────────────────────── 通用零件 ──────────────────────────────
def _source_dates():
    """按路径加载仓库根的 source_dates.py —— 本文件是 `python3 build/cboe.py` 跑的，
    sys.path 上只有 build/，裸 import 会 ModuleNotFoundError。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def mlab(p):
    """与 gsx.mlab 一致：Period('2026-06') → 'Jun-26'。"""
    return p.strftime('%b-%y')


def nz(v, dec):
    """消掉负零。round(-0.04, 1) 是 -0.0，f-string 会照实印成「-0.0」/「-0」——
    读者看到的是一个不存在的负数（复查在 exchanges 热力矩阵与 tsm 上都抓到过）。
    四舍五入到展示精度之后若等于 0，就把符号去掉。"""
    if v is None or not np.isfinite(v):
        return v
    r = round(float(v), dec)
    return 0.0 if r == 0 else float(v)


def comma(v, dec=0, money=''):
    """与 gsx._fmt 一致的数值格式化（千分位 + 固定小数位 + 货币前缀）。"""
    if v is None or not np.isfinite(v):
        return ''
    return f'{money}{nz(v, dec):,.{dec}f}'


def pctf(x, dec=0):
    """百分比变化，带显式正号（负值由 f-string 自带负号）。"""
    if x is None or not np.isfinite(x):
        return ''
    return f'{nz(x * 100, dec):+.{dec}f}%'


def pp(x):
    """与 gsx._pp 一致：小变化给 1 位小数，大变化给 0 位。"""
    if x is None or not np.isfinite(x):
        return ''
    v = x * 100
    return f'{nz(v, 1):+.1f}%' if abs(v) < 2 else f'{nz(v, 0):+.0f}%'


def L(a):
    """序列 → JSON 数组，非有限值写 null（图与表都会画成断点／—）。"""
    return [None if (v is None or not np.isfinite(v)) else round(float(v), 6) for v in a]


def yoy(v, i=-1, lag=12):
    """同比。基数缺失／为 0／异号时返回 nan（与 gsx.lvl_bar 的判据一致）。"""
    v = np.asarray(v, float)
    i = i % len(v)
    j = i - lag
    if j < 0 or not (np.isfinite(v[i]) and np.isfinite(v[j])) or v[j] == 0 or v[i] * v[j] < 0:
        return np.nan
    return v[i] / v[j] - 1


def mom(v, i=-1):
    return yoy(v, i, lag=1)


def prior12(v):
    """Prior 12mo Avg. —— 最新月之前的 12 个月均值（gs_bar 的虚线）。"""
    v = np.asarray(v, float)
    return float(np.nanmean(v[-13:-1]))


# ══════════════════ 同比口径：次轴一律画**单月**同比 ══════════════════
# 单月同比 = 当月 ÷ 去年同月 − 1。**页面所有者要求全站统一成单月口径**（原话：
# 「我就需要直接的月度数据 yoy 同比折线图，不要给我搞 12 月滚动合计同比」），本页
# 2026-09 据此把 Exhibit 2/4/10/11 次轴的金色折线由 12 个月滚动合计同比改回单月同比。
# 这是一条**指令**，不是一条统计结论 —— CONTRACT §6 已按它整节重写：§6.1 第 1 条把
# 流量序列的同比定成**单月**，第 3 条要求每一张画**流量**同比的图用本序列自己实测把
# 代价印出来（本页画同比的四张全是流量，所以这一条在本页落到每一张上）。
# 口径仍要写进 ylab2 与图例名：那是 tools/check_yoy_caliber.py 的 R4 认的四处
# （title / ylab2 / legend / yoy.name）之一，图注里写了不算。
#
# 代价必须一起印出来，否则等于把话说了一半：单月同比把「去年那**一个**月碰巧是什么样」
# 整个塞进分母，去年同月若是异常低点，今年一个平淡的月份也能印出三位数增速；后果不只是
# 「噪声大一点」，而是**方向会反**。这个代价由 yoy_cal_zh() **逐图现算**
# （见各图图注与 notes 的口径条），一个数字都没有写死；对照那一侧的滚动口径**本页不画**，
# 只作量差异用。
#
# ⚠️ **「逐图」是字面意思 —— 2026-09 之前这里做错过一次，留档。** 那一版把代价写成一个
# 页级常量 `YOY_CAL`，四张图共用一段，量的全是**美国期权 ADV**，而那段话的字面写着
# 「代价用本页序列自己实测」。跨页确实没引错，跨**图**引错了：Exhibit 10（CFE 期货 ADV）
# 的读者被告知这条线逐月标准差 17.7pp、与滚动口径方向相反的月份 17 个（16%），
# 而它自己那条线实测是 **32.1pp、43 个（41%）**；Exhibit 11（欧股 ADNV）是 26.3pp / 29 个，
# Exhibit 4（隐含收入）是 20.2pp / 16 个。契约 §6.1 第 3 条的原话是「它拿**这条序列自己**
# 实测，不引别家的例子」，并且「『逐图』是字面意思，页级不算数」—— 现在每张图各算各的。
#
# 交易日加权：**做不到**。Cboe 的月度披露里没有交易日数这一列（cme.csv 有，cboe.csv
# 没有），所以本页拿不出「当月合计张数」这个口径，也不去别处凑一个交易日序列。
# 这里明写出来，是为了防止下一个人以为漏了一步。


def mom_yoy_ser(s):
    """单月同比（%），当月 ÷ 去年同月 − 1。委托给 build/yoy.py，本文件不自己实现。

    前 12 个点必然 NaN（要有去年同月当分母）。
    本页 gs_bar 画的四条序列（美国期权 ADV、隐含收入/日、CFE 期货 ADV、欧股 ADNV）
    全是流量，所以本文件没有存量分支；真要加存量图（如未平仓合约），
    口径同样是点对点同比 YOY.mom_yoy(s, YOY.STOCK)，见 build/yoy.py 的模块头。
    """
    return YOY.mom_yoy(pd.Series(s), YOY.FLOW)


def caliber_diff_win(s, win, kind=YOY.FLOW):
    """`yoy.caliber_diff` 的本页入口：**索引换成横轴标签、统计范围限定成图窗**。

    两件事都是 CONTRACT §6.4 点名的坑，所以放在一个地方做完，调用点不许各写一遍：

    · **统计范围 = 这张图真画出来的那段窗口。** 图注里报的月份若落在图窗之外，
      读者在图上根本找不到（§6.4 举的例子就是 `ndaq` Ex14 在一张 127 期的图上印
      2008 年的跳变）。所以 `win` 是必填的，不给默认值。
    · **索引先换成 `Jan-16` 这种横轴标签**（照 `build/single.py` 的 `mom_cost_zh()`）——
      于是 `describe()` 点到的每一个月份都能在本图 x 轴上原样找到。

    真正的统计（样本对齐、相邻月跳变、符号相反的月份）一格都不在本文件里做，
    全部走 build/yoy.py 的 caliber_diff —— 那是全站唯一实现，各页各写一份正是同一条
    序列在两页被判定相反的原因。样本对齐这一步尤其不能自己重写：滚动同比比单月同比少
    12 个月历史，不取交集就会把「样本不同」读成「口径不同」。
    """
    s = pd.Series(s)
    s = s.set_axis([mlab(p) for p in s.index])
    return YOY.caliber_diff(s, kind, win=[mlab(p) for p in win])


def caliber_stats(s, win, kind=YOY.FLOW):
    """`caliber_diff_win` 的键名适配层（页尾那段与汇总表注引用的字段名沿用旧写法）。

    本页画的是单月同比，滚动那一侧**只作对照、一条都不画** —— 它存在的唯一目的是
    把「换成单月口径要付多大代价」量出来印给读者。
    `first` / `last` / `jump_m_at` 与 `opp` 的索引现在都已经是横轴标签（`Dec-17` 这种），
    调用点**不要**再套一层 `mlab()`。
    """
    d = caliber_diff_win(s, win, kind)
    opp = pd.DataFrame([{'m': m, 'r': r} for _, m, r in d['opposite']],
                       index=[p for p, _, _ in d['opposite']])
    return {'n': d['n'], 'first': d['months'][0], 'last': d['months'][-1],
            'sd_m': d['std_mom'], 'sd_r': d['std_ttm'],
            'jump_m': d['maxjump_mom'][0], 'jump_m_at': d['maxjump_mom'][2],
            'jump_r': d['maxjump_ttm'][0] if d['maxjump_ttm'] else float('nan'),
            'n_opp': d['opposite_n'], 'opp': opp}


#: 逐图代价的最低样本量，照抄 `build/single.py` 的 `Page.MOM_COST_MIN`（全站同一次改
#: 口径，门槛不该各定一个）。它比 `yoy.MIN_DIAG_MONTHS`（12）严一档：12 个月只够
#: caliber_diff 出一个数，24 个月才够让「符号相反的月份占 X%」这个比例不是样本噪声。
#: 不足这个数就照实说「量不出来」，**不许换一条别的序列顶上去凑格式**。
MOM_COST_MIN = 24

#: 逐图代价的账本：{图号: {'label': 点名, 'd': caliber_diff 的结果}}。
#: 页尾那段口径条现读它点名与排序，不写死图号、也不写死条数 ——
#: 哪张图不再画同比、或新增一张，页尾那段会自己跟着变。
COST_LOG = {}


def yoy_cal_zh(n, s_full, win, label):
    """Exhibit n 的「口径 + 代价」图注段 —— 拿**这张图自己那条序列、自己那段窗口**实测。

    CONTRACT §6.1 第 3 条：每一张画<u>流量</u>同比的图都要印出单月口径的代价，
    「它拿**这条序列自己**实测，不引别家的例子」，而且「**『逐图』是字面意思，
    页级不算数**」。2026-09 之前本页四张图共用一段页级常量，量的全是美国期权 ADV
    （错法与实测差多少，见文件上半部口径段那条 ⚠️）。

    措辞照 `build/single.py` 的 `mom_cost_zh()`：口径抬头 → 窗口那一句 → `yoy.describe()`。
    三样必报的东西全在 `describe()` 里：逐月标准差、相邻月最大跳变（带月份）、
    两种口径符号相反的月份数。

    `label` 是这条序列的中文点名，进图注 —— 读者要能一眼看出这段数是**这张图**的，
    不是别处搬来的。
    """
    d = caliber_diff_win(s_full, win, YOY.FLOW)
    COST_LOG[n] = {'label': label, 'd': d}
    xl = [mlab(p) for p in win]
    head = (f'<b>次轴 = <u>单月</u>同比</b>（当月 ÷ 去年同月 − 1），不是 12 个月滚动合计同比。'
            f'理由：<b>页面所有者要求全站统一成单月口径</b> —— 这是一条指令，不是统计结论'
            f'（CONTRACT §6.1 第 1 条据此把流量序列的同比定成单月）。好处只有一个，'
            f'但是决定性的：<b>柱与线取自同一列</b> —— 拿这根柱除以 12 根柱之前那根，'
            f'就是线上这一点，读者可以自己核对。')
    tail = ('折线要等 12 个月才有第一个点（要有去年同月当分母），窗口左端因此没有线。')
    if d['n'] < MOM_COST_MIN:
        return (head +
                f'代价（§6.1 第 3 条）本该在这里用<b>本图这条序列（{label}）</b>自己实测，'
                f'但本图窗口 {xl[0]} 至 {xl[-1]}（{len(win)} 个月）内两种口径都算得出的'
                f'月份只有 {d["n"]} 个（不足 {MOM_COST_MIN} 个，分母太小、报出来的比例是'
                f'样本噪声不是结构），此处不报差异；这本身也是一句该看见的提醒：'
                f'这条线的可比月很少，斜率不要外推。' + tail)
    return (head +
            f'<b>代价（§6.1 第 3 条）用<u>本图这条序列</u>（{label}）自己实测</b>，'
            f'而且<b>只统计本图画出来的这段窗口</b> —— {xl[0]} 至 {xl[-1]}'
            f'（{len(win)} 个月）：图外的历史读者看不到，报出来对不上；'
            f'别的图的线毛刺多大与这条线无关，各图的数各自印在各自图注里。'
            + YOY.describe(d) + tail)


def yoy_line(s_full, win):
    """次轴折线：**单月同比**（理由见上方那段：页面所有者要求全站统一）。

    引擎不替这一步做判断（engine_kinds.md §8 明写「口径判断由 Python 侧完成」），
    所以放弃的期一律写 null，图上断开、表格视图里是「—」。
    """
    return mom_yoy_ser(s_full).reindex(win).values


def yoy_rhs(s_full, win, name='Single-month y/y (RHS)'):
    """gs_bar 的次轴 y/y 折线 payload（给了它引擎就不画 12 个月均线）。

    2026-09 改口径：折线由 12 个月滚动合计同比改回单月同比，图例名一并改掉 ——
    只改数不改名，读者会拿一条毛刺全在的线当已被平滑的滚动线读，那比不改更糟。
    图例名里必须留着「Single-month」：tools/check_yoy_caliber.py 的 R4 只认
    title / ylab2 / legend / yoy.name 四处，图注里写了不算。
    """
    return {'name': name, 'color': 'GOLD', 'yfmt': 'pct0', 'values': L(yoy_line(s_full, win))}


# ────────────────────────────── 读数据 ──────────────────────────────
def load():
    if not os.path.exists(CSV):
        raise SystemExit(f'找不到数据文件: {CSV}')
    df = pd.read_csv(CSV)
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    df = df.set_index('month').sort_index()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    need = ['adv_us_options_kcontracts', 'rpc_us_options_usd', 'adv_futures_kcontracts',
            'adv_us_equities_matched_shares_bn', 'adv_eu_equities_adnv_eurbn',
            'adv_fx_adnv_usdbn', 'adv_multilist_options_kcontracts',
            'rpc_multilist_options_usd', 'adv_index_options_kcontracts',
            'rpc_index_options_usd', 'adv_spx_options_kcontracts',
            'adv_vix_options_kcontracts', 'adv_xsp_options_kcontracts']
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise SystemExit(f'series/cboe.csv 缺列: {missing}')

    # 月份必须逐月连续 —— 否则时序窗口、同比与季度合计全部错位（CONTRACT §5.3/§5.5）
    idx = list(df.index)
    bad = [(str(idx[i - 1]), str(idx[i])) for i in range(1, len(idx))
           if (idx[i] - idx[i - 1]).n != 1]
    if bad:
        raise SystemExit(f'月份序列不连续: {bad}')

    # ── 派生列（逐行照抄 build_cboe.py）──
    df['opt_rev_day_usdmn'] = df['adv_us_options_kcontracts'] * df['rpc_us_options_usd'] / 1000.0
    df['adv_us_options_mn'] = df['adv_us_options_kcontracts'] / 1000.0
    df['adv_index_options_mn'] = df['adv_index_options_kcontracts'] / 1000.0
    df['adv_spx_mn'] = df['adv_spx_options_kcontracts'] / 1000.0
    df['adv_vix_opt_mn'] = df['adv_vix_options_kcontracts'] / 1000.0
    df['adv_xsp_mn'] = df['adv_xsp_options_kcontracts'] / 1000.0
    df['adv_multilist_mn'] = df['adv_multilist_options_kcontracts'] / 1000.0
    df['index_share'] = df['adv_index_options_kcontracts'] / df['adv_us_options_kcontracts'] * 100
    return df


# ────────────────────── Exhibit 1：汇总表（gsx.summary_table）──────────────────────
def summary_block(df, cur, prv, yag):
    """本月 | 上月 | 去年同月 ‖ m/m | y/y | 3Y %ile。

    格式化与着色规则全部在这里定死（CONTRACT §2）：页面只贴字符串。
    """
    ROWS = [
        ('group', 'U.S. options ADV (k contracts/day)', None, 0, ''),
        ('row', 'Total U.S. options', 'adv_us_options_kcontracts', 0, ''),
        ('row', 'Index options (proprietary)', 'adv_index_options_kcontracts', 0, ''),
        ('row', '　of which SPX', 'adv_spx_options_kcontracts', 0, ''),
        ('row', '　of which VIX options', 'adv_vix_options_kcontracts', 0, ''),
        ('row', 'Multiply-listed options', 'adv_multilist_options_kcontracts', 0, ''),
        ('group', 'Other franchises', None, 0, ''),
        ('row', 'Futures ADV (k contracts/day)', 'adv_futures_kcontracts', 0, ''),
        ('row', 'U.S. equities matched (bn shares/day)', 'adv_us_equities_matched_shares_bn', 2, ''),
        ('row', 'European equities ADNV (EUR bn/day)', 'adv_eu_equities_adnv_eurbn', 1, ''),
        ('row', 'Global FX ADNV ($bn/day)', 'adv_fx_adnv_usdbn', 1, ''),
        ('group', 'Revenue per contract ($)', None, 0, ''),
        ('row', 'U.S. options RPC', 'rpc_us_options_usd', 3, '$'),
        ('row', 'Index options RPC', 'rpc_index_options_usd', 3, '$'),
        ('row', 'Multiply-listed options RPC', 'rpc_multilist_options_usd', 3, '$'),
    ]

    # 分位一律走 build/pctile.py：判据（回放近 24 个月、≥70% 钉在极值就留空）是**口径**，
    # 口径只能有一处定义。本文件原来自己写的「diff>=0 占比 ≥90% 就留空」拦不住
    # 「上下波动但分位常年钉 100」的行，且与其他 13 个生成器各写各的、同一条序列在
    # 两页可以判定相反。
    i_cur = list(df.index).index(cur)

    rows, blanks = [], []
    for kind, lab, col, dec, money in ROWS:
        if kind == 'group':
            rows.append({'kind': 'group', 'label': lab})
            continue
        s = df[col].dropna()
        g = lambda p: (float(s.loc[p]) if p in s.index else np.nan)
        c, p1, p12 = g(cur), g(prv), g(yag)

        def chg(a, b):
            # 比率模式：分母为 0 或两期异号时百分比变化无意义（同 gsx.summary_table）
            if not (np.isfinite(a) and np.isfinite(b)) or b == 0 or a * b < 0:
                return None
            return (a / b - 1) * 100

        cells = [{'v': comma(c, dec, money), 'cls': 'cur'},
                 {'v': comma(p1, dec, money)},
                 {'v': comma(p12, dec, money)}]
        for v in (chg(c, p1), chg(c, p12)):
            if v is None:
                cells.append({'v': ''})
            else:
                v = nz(v, 1)
                cells.append({'v': f'{v:+.1f}%',
                              'cls': 'pos' if v > 0 else ('neg' if v < 0 else '')})

        ser = [None if not np.isfinite(x) else float(x) for x in df[col].values]
        qv, qcls = pctile.cell(ser, i_cur)
        cells.append({'v': qv, 'cls': qcls} if qv else {'v': ''})
        if not qv:
            # 留空必须给得出理由，否则读者只会当成「这一格忘了填」
            why = pctile.why_blank(ser) or ('最新月尚未披露，RPC 滞后一个月发布'
                                            if ser[i_cur] is None else '样本不足')
            blanks.append((lab.strip('　'), why))
        rows.append({'label': lab, 'cells': cells})

    return {
        'title': f'Cboe monthly volume and RPC summary — {mlab(cur)}',
        'heads': [mlab(cur), mlab(prv), mlab(yag), 'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': rows,
        'blank_why': blanks,        # 供 notes 生成表注，不进页面渲染
    }


# ─────────────────────── 顶部 ~300 字数据总结（payload 的 brief）───────────────────────
def compose_brief(ALL, i0, tot, ix, ru, ri, rm, lines):
    """Cboe 页顶部的 ~300 字数据总结。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R3 日历护栏 / R4 单位恒等 /
    R5 标注 / R6 有效位），那边只算事实，句子在这里拼——措辞是口径的一部分，属于各家自己。
    每个数字都是当场从序列算的，**没有一处硬编码**：排名、滚出窗口的是哪个月、峰值停在
    哪一年，下个月重跑都会自己变。**每个定性词也一样**——「只有 N 条」「与总数反向」
    「同比全为正」「最高」全部由当场算出的量决定分支（`B.quant()` / `B.need()` /
    `B.top_pct()`）。写死的措辞配算出来的数字是这一段返工过的主因，别再往回写。

    ═══ Cboe 独有，别家不能照抄 ═══
      · **R3（日历护栏）在这里不成立，而且用了就是错的。** cboe.csv 的 adv_* 列公司披露
        的本来就是 ADV（每日平均），不是当月合计；再除一次交易日会造出一个根本不存在的
        修正。全站只有 IBKR / COST 那种「当月合计」列才轮得到 R3。
      · **RPC 是三个月滚动平均、滞后一个月发布**，这两条合起来造出一个别家没有的基数陷阱：
        混合 RPC 的环比可以整段由「三个月窗口换掉了哪个月」决定，而与本月的定价、本月的
        成交完全无关。本段的主句讲的就是这件事，其余 13 家没有一家的单价序列是滚动的。
      · Cboe 是全清单里唯一官方**同时**按月披露量（ADV）与单位价（RPC）、且按两本账
        （自有指数 / 多重挂牌）分别披露的标的，所以「动的是结构还是单价」可以真的算出来
        并回验；其余各家只有量，价得靠季度费率去凑。
      · 排名一律从 `i0`（首个非 pro-forma 月）起算，与 Exhibit 6 那条红色断点虚线同一个
        下标。2017 年是 Bats pro-forma combined 口径，混进分母会把一次并表算成历史区间。
        同一个理由使 `B.regime_ratio()` 在本页不可用——它的基期写死取序列首年，那正好是
        pro-forma 的 2017 年（T4/R4 因此整条跳过，不是忘了写）。**环比同样受这条约束**：
        上一期 RPC 落在 i0 之前时两期不可比，那一句宁可不写。
      · 本页没有反向指标（RPC、ADV 都是越高越好），故 `peak_scan` 不传 inverse；
        九条产品线经 `B.is_monotonic()` 判定无一单调，「创新高」在这里是信息不是噪音。

    ═══ 与本页 2026-09 同比口径改造的关系（移植时的口径适配）═══
      本页各图次轴的同比已由 12 个月滚动合计同比**改回单月同比**（见文件头那段：
      页面所有者要求全站统一），而 brief 引用的 m/m / y/y 读数本来就是**单月**口径、
      与汇总表逐格对得上 —— 所以这一轮 brief 一个字都不用改口径，反倒是原先那句
      「不得与下方各图的 TTM 折线读数混淆」失效了：页面上已经没有 TTM 折线。
      措辞规矩保留：凡出现同比措辞一律按 CONTRACT §6 写明「单月」，因为本页同时还有
      Exhibit 8 的季度同比与 Exhibit 13 的日历年同比，那两档不是月度口径。
      RPC 的「单月同比」比的是两个三个月滚动值，天然比流量的单月同比平滑，这也是 s3
      那个判断在本页站得住的原因。单月读数只作**位置与基数**陈述（排名 / 反号 /
      窗口换月），不作趋势断言——趋势要跨月看，一个月的读数撑不住。

    ═══ R5 的标记挂在哪（核验退回过一次：方向挂反了）═══
      两条分账 RPC（指数 / 多重挂牌）与九条 ADV 都是**公司披露列**，所以「拆开两本账」
      本身不是推导，不能挂（推导值）——挂在那里等于把公司自己发的数标成我们算的。真正的
      推导值是：三个月成交量加权权重、结构/单价分解、指数占比，标记跟着这几个走。分解虽然
      不再逐项印数，但「跌的是结构不是单价」这个判断整个建在它上面，所以标记不跟着数字走、
      跟着**依据**走，留在那句判断后面。
      另外「M-2 至 M」这个对齐窗口是**拟合**出来的（公司只说 three-month rolling，没说
      是哪三个月，见文件头 RPC_WIN 的注释），故单标「拟合口径」，与「推导值」不是一回事。

    ═══ 分解印到哪一层（2026-08 收窄）═══
      分解照算，正文**只印结论**：「跌的是结构不是单价」。此前印的是「结构 -1.46¢、
      费率合计 -0.22¢、复原余项 -0.06¢」三项带余项——读者要先做一次三项加法才跟得上，
      比样板（build/ibkr.py 的二元恒等式 + 一句落点）深一档。洞察保留，层数收掉。
      随之作废的还有余项那套倒算逻辑：分解对**复原**序列 wn·ri+(1−wn)·rm 是恒等式，
      而 d_rpc 用的是**披露**的 ru，两者差一个复原残差，所以当时得把余项按印出来的两位
      小数倒算出来才能让三个数相加等于总数。不印分项就没有加不平的问题，这一层一并删掉。
      复原误差仍然每次重算，但只作 RPC_FIT_TOL 那道闸的判据，不进正文。

    ═══ 字数 ═══
      `B.render()` 的护栏是 230-380，那是拦「模板拼坏了」用的。这里自己压到 BRIEF_HI
      以内：贴着上界发布等于把「下个月排名多一位数」当成停更风险。压法不是删限定语
      （推导值 / 拟合口径 / 滞后一期），而是先试最小的删法，见函数末尾。
    """
    i = len(ALL) - 1
    y0 = ALL[i0][:4]                       # 排名区间的起点年（= pro-forma 之后）
    fin = np.where(np.isfinite(np.asarray(ru, float)))[0]
    fin = fin[fin >= i0]
    # RPC 最新可得月（比成交量晚一期）。断点之后一个都还没披露时为 None——此时整块 RPC
    # 叙述不写，页面照发（B.need 的规矩：缺值是「该句不写」，不是整页构建失败）。
    j = int(fin[-1]) if len(fin) else None

    def m(k, ref):
        """月份标签。与参照月同年时只写「6 月」，跨年才补年份。

        RPC 的三个月窗口每年有两次跨年（12 月那一档含 10、11、12 月，1 月那一档含
        11、12、1 月）。恒不写年份，1 月的页面上「11 月换成 1 月」会被读成同一年往前退；
        恒写年份则一句话里塞四个「2026 年」。所以按需补。"""
        return (f'{ALL[k][:4]} 年 {int(ALL[k][5:7])} 月' if ALL[k][:4] != ALL[ref][:4]
                else f'{int(ALL[k][5:7])} 月')

    def ordinal(rk, n, unit='高'):
        """排名措辞。第 1 名写「最高」——「第 1 高」不是中文。"""
        return f'{n} 个月里最{unit}' if rk == 1 else f'{n} 个月里第 {rk} {unit}'

    def fold(names, cap=2, count=True):
        """名字最多列 cap 条，其余折成「等 N 条」（count=False 时只写「等」）。

        并列条数是当场算的：回放到 2019 年会有六七条线并列停在同一个月，全列出来一句话
        就撑破字数护栏。cap 从 3 收到 2，是因为三条并列 + 三个排名恰好卡在护栏上界附近，
        再多一条就发不出去——折叠省下的字必须够抵掉后面多出来的排名项。"""
        head = '、'.join(names[:cap])
        if len(names) <= cap:
            return head
        return head + (f'等{B.cn(len(names))}条' if count else '等')

    def w3(k):
        """三个月滚动的量加权指数占比（推导值）。

        分子分母必须取**同一批月份**：各自 nansum 时，哪天 ix 与 tot 在窗口内的不同月
        缺值，比值会静默混月（当前 115 行两列全无 NaN，未触发，但这道掩码是白拿的）。
        窗口不足 RPC_WIN 个月时按现有月份算——负下标会把序列尾巴卷进来。"""
        a = max(0, k - RPC_WIN + 1)
        x = np.asarray(ix[a:k + 1], float)
        t = np.asarray(tot[a:k + 1], float)
        msk = np.isfinite(x) & np.isfinite(t)
        s = float(t[msk].sum())
        return float(x[msk].sum() / s) if msk.any() and s else float('nan')

    # ── 「披露的混合 RPC 能不能被两本账复原」的当场回验。误差每次重算：口径哪天变了
    #    （比如改成两个月滚动）这道闸会响，而不是静默印错话。样本为空（序列只有两三个月、
    #    或断点后还没攒够一个窗口）时不响——那不是口径变了，是还没数可拟合，此时下面的
    #    分解整块不写。
    j_hi = j if j is not None else i0 - 1
    fit = [abs((w3(k) * ri[k] + (1 - w3(k)) * rm[k]) / ru[k] - 1)
           for k in range(max(i0, RPC_WIN - 1), j_hi + 1)
           if B.need(ru[k], ri[k], rm[k], w3(k)) and ru[k]]
    if fit and float(np.mean(fit)) * 100 > RPC_FIT_TOL:
        raise SystemExit(
            f'brief: 混合 RPC 用「三个月滚动量加权 x 两本账 RPC」复原的平均误差 '
            f'{float(np.mean(fit)) * 100:.2f}% 超过 {RPC_FIT_TOL}%，RPC 的滚动口径可能变了。'
            f'先重新拟合 RPC_WIN 与对齐窗口，不要让 compose_brief 照旧印那句分解。')

    sh = ix / tot * 100                     # 单月指数占比（%，推导值）
    n_sh = int(np.isfinite(sh[i0:]).sum())  # 量口径的样本月数：比 RPC 多一个月（RPC 滞后一期）
    n_ri = int(np.isfinite(ri[i0:]).sum())
    n_ru = int(np.isfinite(ru[i0:]).sum())

    # ── 两道闸，决定 RPC 这一块能写到哪一层。写不动的部分由量口径那句顶上，页面照发。
    have_chg = (j is not None and j - 1 >= i0
                and B.need(ru[j], ru[j - 1], ri[j], ri[j - 1], rm[j], rm[j - 1]))
    have_dec = have_chg and bool(fit) and B.need(w3(j), w3(j - 1))

    rk_ri = B.rank_of(ri[i0:], j - i0) if j is not None else None
    hi_txt = f'指数期权 RPC 是 {y0} 年以来 {ordinal(rk_ri, n_ri)}' if rk_ri else ''

    # ── s1：本期变动 + 贵的那本账在历史里的位置 + 动的是结构还是单价。一句三段，都是读数
    #    或由读数直接比出来的判断，不含中间步骤。
    head1 = punch = ''
    if have_chg:
        # ── mix vs rate 分解（推导值）。各项都用**分**表示，不做除法：RPC 走平的月份
        #    「mix 占跌幅百分之几」会除出一个爆炸的数，而分是它本来的差异单位（CONTRACT §2：
        #    比率类指标的差异不写百分比变化；RPC 以美元计价，其差异形式就是 ¢/张）。
        d_rpc = (ru[j] - ru[j - 1]) * 100                                # ¢/张
        flat = round(d_rpc, 2) == 0
        w_dn = '变动' if flat else ('跌' if d_rpc < 0 else '涨')
        # 「滞后一期」是口径标注，但它也得由数据说：j == i 的月份 RPC 并不滞后。
        lag = '（滞后一期）' if j < i else ' '
        chg = '环比几乎持平' if flat else f'环比{w_dn} {abs(d_rpc):.2f}¢'

        punch = ''
        if have_dec:
            # 分解照算，但**只印结论不印分项**：谁在动是这句话的信息，三个带余项的数是
            # 读者要自己做一遍加法才跟得上的中间步骤（分寸见 docstring「印到哪一层」）。
            wn, wp = w3(j), w3(j - 1)
            d_mix = (wn - wp) * (ri[j - 1] - rm[j - 1]) * 100            # 结构效应 ¢/张
            d_rate = (wn * (ri[j] - ri[j - 1])
                      + (1 - wn) * (rm[j] - rm[j - 1])) * 100            # 两本账单价效应合计
            # 「跌的是结构不是单价」是**判断**不是读数，三个分支全部由这两项当场比出来：
            # 回放 101 个可比月里结构主导 76 个月、单价主导 25 个月、两者量级相当 34 个月，
            # 写死任何一句都会在别的月份变成假话。判据分两道——
            #   ① 方向：主导项必须与总变动同向，否则「跌的是 X」会把一个在往上顶的分项
            #      说成下跌的原因（2019-10 就是这种月：总数 -0.02¢，两项 ∓0.4¢ 互相抵消）
            #   ② 量级：主导项至少是另一项的 2 倍才配说「不是」，否则只说两头都在动
            m2, r2 = round(d_mix, 2), round(d_rate, 2)
            drv, oth = ((m2, r2) if abs(m2) >= abs(r2) else (r2, m2))
            lead = '结构' if abs(m2) >= abs(r2) else '单价'
            if flat:
                # 总数持平时没有方向可归因，能说的只是两项互相抵消（同号则连这句也不成立）
                punch = ('<b>结构与单价互相抵消</b>'
                         if m2 and r2 and (m2 < 0) != (r2 < 0) else '')
            elif drv and (drv < 0) == (d_rpc < 0) and abs(drv) >= 2 * abs(oth):
                punch = (f'<b>{w_dn}的是{lead}不是'
                         f'{"单价" if lead == "结构" else "结构"}</b>（推导值，三个月成交量加权）')
            else:
                punch = '<b>结构与单价都在动</b>（推导值，三个月成交量加权）'
        head1 = f'{m(j, i)} RPC{lag}{chg}'
    elif j is not None:
        head1 = f'{m(j, i)} RPC 与上一期不可比（上一期落在 {y0} 年前的 pro-forma 口径里）'
        punch = ''
    else:
        head1 = punch = ''

    # ── s2：R2 的基数。上面那个「结构」在 Cboe 有一半是机械的——三个月窗口换掉了哪个月，
    #    与本月定价无关。这是 Cboe 独有的基数陷阱，别家的单价序列都不是滚动的。
    s2, swap = '', ''
    if have_dec:
        k_out = j - RPC_WIN                 # 滚出窗口的那个月；落在 i0 之前就不写这一句
        if k_out >= i0 and B.need(sh[k_out], sh[j]):
            rk_out = B.rank_of(sh[i0:], k_out - i0)
            # 第二个月份挂在**滚出月**上做参照，不挂在本月：1 月的页面上两头都是去年，
            # 挂本月会印成「2020 年 9 月换成 2020 年 12 月」，年份白写两遍。
            # 占比是 load() 里的派生列（指数 ADV ÷ 美国期权总 ADV），R5 要求正文带标记；
            # 上一句那个（推导值）挂的是分解与权重，管不到这里，所以这里自己再挂一次。
            swap = (f'RPC 按 M-2 至 M 滚动（拟合口径），这一档把指数占比（推导值）'
                    f'{sh[k_out]:.1f}%（{ordinal(rk_out, n_sh)}）的 {m(k_out, i)}'
                    f'换成 {sh[j]:.1f}% 的 {m(j, k_out)}')
        # 一句话一个意思：s1 说清是结构还是单价在动，这一句只说滚动窗口换掉了哪个月。
        s2 = swap + '。' if swap else ''

    # ── s2b：没有上面那句窗口换月时（断点后的头几个月、RPC 缺值月），指数占比的位置就
    #    没人交代了。改从量口径直接给——tot 与 ix 两列没有缺口，任何截止月都算得出。
    #    m/m 与 y/y 都是**单月**口径（B.base_effect），与 Exhibit 1 汇总表、以及各图次轴
    #    的金色折线同口径、可逐格对上。措辞仍按 CONTRACT §6 标「单月」：本页另有
    #    Exhibit 8 的季度同比与 Exhibit 13 的日历年同比，不标会被拿去和那两档对读。
    s2b = ''
    if not swap:
        # 量口径的窗口同样从 i0 起：2017 是 Bats pro-forma combined，环比与排名都不能
        # 跨过断点去比（与上面 RPC 那句同一条规矩，不是两套）。
        beq = B.base_effect(np.asarray(tot, float)[i0:], i - i0)
        rk_sh = B.rank_of(sh[i0:], i - i0)
        bits = [f'{m(i, i)}指数占比 {sh[i]:.1f}%（{ordinal(rk_sh, n_sh)}）'] if rk_sh else []
        if beq['mm'] is not None:
            bits.append('美国期权总 ADV 环比 ' + B.pct(beq['mm'])
                        + (f'、单月同比 {B.pct(beq["yy"])}' if beq['yy'] is not None else ''))
        if beq['rank']:
            bits.append(f'总 ADV 排 {ordinal(beq["rank"], n_sh)}')
        # 自有指数期权这条线是本页的主角，RPC 讲不动的月份至少把它的量交代掉
        bix = B.base_effect(np.asarray(ix, float)[i0:], i - i0)
        if bix['mm'] is not None:
            bits.append('指数期权 ADV 环比 ' + B.pct(bix['mm'])
                        + (f'（{ordinal(bix["rank"], n_sh)}）' if bix['rank'] else ''))
        s2b = ('量口径（推导值：占比 = 指数 ADV ÷ 美国期权总 ADV）：'
               + '，'.join(bits) + '。') if bits else ''

    # ── s3：R2 的落点。分四种，都由数据挑：变动小于历史月变动中位数时它本身就不是信号
    #    （回放里 0.01¢ 的月份确实出现过，照印「会读成费率战」等于给噪音配一段解读）；
    #    反号才轮得到窗口效应那句；同向时是真下行，说成误读就把事实讲反了；同比还没有
    #    （断点后不足 12 个月）时三种都判不出来，那就不下这个判断——原来这里会印「同向」，
    #    在没有同比的月份那是假话。
    #    这里的同比同样是**单月**口径（B.base_effect，比的是两个三个月滚动 RPC 值），
    #    措辞随之标「单月」；「不只是窗口效应」的依据在句内点名，理由见 docstring
    #    「与本页 2026-08 同比口径改造的关系」。
    s3 = ''
    if j is not None:
        be = B.base_effect(ru[i0:], j - i0)
        dif = np.abs(np.diff(np.asarray(ru[i0:j + 1], float)))
        noise = float(np.nanmedian(dif)) * 100 if np.isfinite(dif).any() else None
        head3 = '环比与单月同比反号，' if be['yy'] is not None and be['conflict'] else ''
        rank3 = ''
        if be['rank']:
            # 分母写出来：RPC 口径比量口径少一个月，两处名次不是同一个分母（核验点名）。
            # 名次本身还不够——「跌完还在前 7%」才是与 headline 相反的那半句，故带 top_pct；
            # 但只在前半区带：排在后半区时「前 96%」是句废话，那时只给分母。R2 要的上月
            # 名次同理，只有上月真的在前三高（基数效应的触发条件）才占这几个字。
            prev = f'上月第 {be["prev_rank"]}、' if (be['prev_rank'] or 99) <= 3 else ''
            # 全文的数字与汉字之间留一个空格，B.top_pct 返回的「前7%」不带，这里补上
            where = ('的' + re.sub(r'(\d)', r' \1', B.top_pct(be['rank'], n_ru), count=1)
                     if be['rank'] * 2 <= n_ru else '中')
            rank3 = f'混合 RPC {prev}本月第 {be["rank"]}（{n_ru} 个月{where}）'
        end3 = ''
        if have_chg and B.need(noise) and abs(d_rpc) < noise:
            end3 = f'<b>这一{w_dn}小于历史月变动中位数 {noise:.2f}¢，本身不算信号</b>'
        elif have_chg and be['yy'] is not None:
            end3 = (f'<b>只看这一{w_dn}会读成费率{"战" if d_rpc < 0 else "回升"}</b>'
                    if be['conflict'] else
                    f'<b>这一{w_dn}与单月同比同向，不只是窗口效应</b>')
        body3 = head3 + rank3 + ('——' + end3 if rank3 and end3 else end3)
        s3 = body3 + '。' if body3 else ''

    # ── s4：R1 产品线峰值扫描。谁停在自己的最高点，谁的峰值还停在很多年前。
    #    九条 ADV 全部非单调（B.is_monotonic 判定），所以「创新高」在这里是信息不是噪音；
    #    真有单调列被 skip_monotonic 剔掉时，「N 条」跟着用实际扫过的条数，不写死 len(lines)。
    pk = B.peak_scan(ALL[i0:], [(nm, a[i0:]) for nm, a in lines], i - i0)
    n_scan = len(pk['at_peak']) + len(pk['off_peak'])
    # 「只有一条」是定性词，必须跟着比例走：回放里最多 4/9 条同时停在峰值，那时写「只有」
    # 就是把普遍现象说成稀缺。B.quant() 按 k/n 挑「只有／有／多达」。
    # 条数已经在「只有 N 条」里给过，括号里再写一遍「等四条」是同一个数说两次
    top = (f'{B.quant(len(pk["at_peak"]), n_scan, "条")}停在自己的峰值'
           f'（{fold(pk["at_peak"], count=False)}）' if pk['at_peak']
           else '没有一条停在自己的峰值')
    tone = pos = grp_txt = ''
    if pk['off_peak']:
        old = min(k for _, k in pk['off_peak'])          # 最早的那个峰值月
        all_grp = [nm for nm, k in pk['off_peak'] if k == old]
        grp, srs = all_grp[:2], dict(lines)
        rk = [(B.rank_of(srs[nm][i0:], i - i0), int(np.isfinite(srs[nm][i0:]).sum()))
              for nm in grp]
        # 同比方向当场算（写死「两位数正增长」下个月就可能变成假话），且必须覆盖
        # **被这句话点到的全部**产品线（含折进「等 N 条」的那几条），不能只看列名的两条。
        # 一条都算不出来（不足 12 个月）时不写方向——「涨跌互见」在没有同比的月份是假话。
        # 这里的同比也是**单月**口径（本月 ÷ 去年同月），措辞标「单月」（CONTRACT §6）：
        # 它陈述的是这几条线**当下相对去年同月的位置**，不是趋势——单月读数撑不起趋势
        # 判断，而本页（按所有者的口径要求）已经没有任何一条平滑过的同比线可以替它背书。
        yy = [srs[nm][i] / srs[nm][i - 12] - 1 for nm in all_grp
              if i >= 12 and B.need(srs[nm][i], srs[nm][i - 12]) and srs[nm][i - 12]]
        tone = ('单月同比全为正' if all(v > 0 for v in yy) else
                ('单月同比已全部转负' if all(v < 0 for v in yy)
                 else '单月同比涨跌互见')) if yy else ''
        # 分母相同就只写一次；哪天组里混进历史更短的产品（如 XSP 从 2019 起）再逐条写
        dn = {n for _, n in rk if n}
        if all(r for r, _ in rk):
            pos = (f'{dn.pop()} 个月里排第 ' + '、'.join(str(r) for r, _ in rk) + ' 位'
                   if len(dn) == 1 else '排第 ' + '、'.join(f'{r}/{n}' for r, n in rk) + ' 位')
        # 「的」不是可省的虚字：产品线名可能以拉丁字母收尾（欧股 ADNV），直接接汉字会
        # 印成「ADNV峰值」，与全页「字母数字与汉字之间留空」的排版不一致。
        grp_txt = f'{fold(all_grp)}的峰值仍停在 {m(ALL.index(old), i)}'

    def assemble(drop=()):
        # 「但」要同时满足两个条件才成立，缺一个都会印出一句假转折：
        #   (1) 前半句真的给了一个跌／涨（不可比的月份没有转折可转）；
        #   (2) 分账 RPC 的名次真的在**前半区** —— 否则「RPC 跌了，但分账排第 11 高」
        #       里的「但」无处落脚。重放到 2019-03 至 2019-07 会印「但…15 个月里第 11 高」，
        #       正是这种假转折。判据当场算，不写死名次门槛。
        hi_is_high = rk_ri is not None and n_ri and rk_ri * 2 <= n_ri
        hi = '' if 'hi' in drop else (
            ('但' + hi_txt) if have_chg and hi_txt and hi_is_high else hi_txt)
        s1 = '，'.join(x for x in [head1, hi, punch] if x)
        tail = '；' + '，'.join(x for x in [grp_txt,
                                          '' if 'tone' in drop else tone,
                                          '' if 'pos' in drop else pos] if x) if grp_txt else ''
        s4 = f'量这边{B.cn(n_scan)}条产品线{top}{tail}。'
        return [s1 + '。' if s1 else '', s2, s2b, s3, s4]

    # ── 字数：render 的 230-380 是拦「模板拼坏了」的，贴着上界发布是可预见的停更风险
    #    （名次多一位数、产品线改名都会撞破，整页就 SystemExit 发不出去）。所以在这里自己
    #    压到 BRIEF_HI 以内，压法是省可省项，而不是删任何限定语（推导值 / 拟合口径 /
    #    滞后一期）——那些是口径的一部分，删了就是另一句话。可省的三项：
    #      tone 峰值停在多年前那几条的同比方向（5 个字，最便宜）
    #      pos  那几条今天的名次（约 18 个字）
    #      hi   指数 RPC 自己的名次（最后才动：它是 s1 那个转折的依据）
    #    顺序按「先试最小的删法」排，不是固定优先级：只超 3 个字时省掉 tone 就够了，
    #    没必要连名次一起砍掉。三项都省完还超，说明真的拼坏了，交给 render 的护栏去响。
    for drop in ((), ('tone',), ('pos',), ('pos', 'tone'), ('pos', 'tone', 'hi')):
        body = assemble(drop)
        if len(re.sub(r'<[^>]+>', '', ''.join(x for x in body if x))) <= BRIEF_HI:
            break
    return B.render(body)


# ══════════════════════════════════════════════════════════════════════════════
# 名词释义（payload 的 `glossary`，排在所有 exhibit 之前）
#
# ━━ 与 brief / 页尾 notes / 图注的分工 ━━
# brief 说「这个月这组读数该怎么读」、每月重写；notes 与图注说「这一张图该怎么读」
# （含当月读数、本图自己实测的毛刺量）。这一块只说「这些词是什么意思」，
# 一年到头是同一段 ⇒ 这里**不写当月读数、不写「最新一期」**。
# 出现的数只有两类：把定义钉住的结构性量（两本账 RPC 的倍数、两块相加的恒等残差、
# XSP 的披露起点）与恒等式本身；且**一个都不写死** —— 全部在 compose_glossary()
# 里从 series/cboe.csv 现算，与本文件其余图注同一个做法。
#
# ━━ 为什么是这 12 个词（选词判断）━━
# 判据只有一条：这个词出现在本页的图题 / 序列名 / 纵轴 / 汇总表行头 / 图注里，
# 而且**不看定义就会读错**。按「读错会出什么事」分五类：
#   ① 分母与单位   ADV / ADNV / 美股撮合成交 —— 本页三种量纲并存（合约张数、
#      成交金额、成交股数），原 deck 甚至把其中三条画在同一根轴上。更要紧的是
#      ADV 是官方**直接印的日均**，而 Cboe 的月度披露里没有交易日数这一列 ⇒
#      本页拿不出「当月合计张数」。不点破，读者会去反推月总量、或跨量纲相除凑均价。
#   ② 同一件事的两个口径、或「分母到底是谁」  RPC（三个月滚动 + 滞后一月发布，
#      整整一批图因此短一期、汇总表最新一格因此是空的）、指数期权占比（分母是
#      **Cboe 自己**的美国期权 ADV，不是全美市场 ⇒ 它是 mix 不是市占率）、
#      VIX 期权 / VIX 期货（同一个标的分属两张图，相加就是重复计算）、
#      CFE 期货（这一行的外延 2025Q2 变宽过一次）。这一类的代价最隐蔽：
#      读串了整条线系统性偏高或偏低，而图形完全正常，看不出来。
#   ③ 本页轧出来、不是公司披露的  隐含期权交易收入、量费分解 —— 必须点明
#      「推导值」，以及分的是**收入**而不是成交额（RPC 是费率，不是标的价格）。
#   ④ 主体划分  自有指数期权 / 多重挂牌期权 —— 本页的美国期权只分这两块，
#      两块 RPC 差一个数量级，所以 mix 位移比总量更能解释收入。
#   ⑤ 可能没装满的桶  季度至今 / YTD —— 季度柱的末格（未满 3 个月时）与量费分解的
#      末柱只覆盖部分月份，拿它去比完整桶就是拿 1–2 个月比 3 个月、6 个月比 12 个月。
#      ⚠️ 这一条必须写成**条件式**：Exhibit 8 的图注自己是分支的（满 3 个月就照常报
#      同比），无条件的定义在 3/6/9/12 月会与同页图注正面打架。
# **有意不收**：
#   · m/m、y/y、3Y %ile、pp/bp —— 全站通用的读图约定，summary.note 与「汇总表读法」
#     那条已经逐条讲过，释义板再讲一遍就是两处各写一份。
#   · 「Bats pro-forma combined 口径断点」与「单月同比 vs 12 个月滚动同比」——
#     页尾 notes 第 2、3、4 条加十条图注讲的正是这两件事在本页的**具体落点与实测**，
#     而实测数逐图不同（毛刺 17.7pp 到 32.1pp 差 1.8 倍）；把其中一套抄进一条
#     「一年不变」的定义里，必然与另外几张图打架。定义层解决不了的事就留在图注里。
#   · 成交量、市值这类本页没有特殊口径的常识词。
#   · 已删的原 Exhibit 14 里的词（页面上不存在的词一律不收）。
# ══════════════════════════════════════════════════════════════════════════════
def compose_glossary(df):
    """/cboe/ 页最上方的「名词释义」（payload 的 `glossary` 字段）。

    写成函数而不是模块级常量，理由只有一个：三个结构性量必须**现算**——
      · 自有指数期权 RPC ÷ 多重挂牌 RPC 的倍数（逐月中位与区间）；
      · 「两块相加 = 美国期权总 ADV」这条恒等式的实测最大残差；
      · XSP 这一列的披露起点。
    写死的那一天就是它开始变旧的那一天（CSV 每月多一行）。

    返回 `[(词, 释义), …]`，顺序即页面上的顺序；拼装与四道护栏在 build/glossary.py。
    释义里只能用行内标签，强调一律 `<b>…</b>` —— page.js 走 innerHTML，
    Markdown 的星号会原样印在整页第一段上。
    """
    # ── ① 两本账 RPC 的倍数：mix 那一串结论的唯一依据 ────────────────────────
    # 页尾 notes 与 Exhibit 3、5、13 图注里的那个倍数是**最新一期**的读数，由
    # `ratio = rpc_ix[-1] / rpc_ml[-1]` 每次构建现算（build/cboe.py 的 Exhibit 3 处），
    # 逐月都在动 —— 所以这里**不许把它的当期取值抄成一个引号里的常数**：抄了下个月
    # 页尾印的就是另一个数，而释义还让读者去找一句页面上不存在的话（实测：126 个月里
    # 只有 17 个月的 {:.0f} 取整是 15）。这里要的是不随月份变的那个量，
    # 所以取全窗口逐月比值的中位与区间，现算；对页面那个数只做**指代**、不复述取值。
    _r = (df['rpc_index_options_usd'] / df['rpc_multilist_options_usd']).replace(
        [np.inf, -np.inf], np.nan).dropna()
    mult = (f'在窗口内逐月是多重挂牌的 <b>{_r.median():.1f} 倍</b>'
            f'（区间 {_r.min():.1f}–{_r.max():.1f} 倍，{len(_r)} 个月现算；'
            f'页尾与图注里那个倍数说的是<b>最新一期那一个月</b>的读数，会随月份变）'
            if len(_r) else '一直高出多重挂牌一个数量级')

    # ── ② 恒等式「自有指数 + 多重挂牌 = 美国期权总 ADV」的实测残差 ───────────
    # 官方在同一张表里印出这三列，本页两张图（堆叠、占比）都吃这条恒等式。
    # 残差不写死：它只反映官方那三列自己的取整，回补历史或改精度都会让它变。
    _res = (df['adv_index_options_kcontracts'] + df['adv_multilist_options_kcontracts']
            - df['adv_us_options_kcontracts']).abs().dropna()
    # 残差按「张/日」印（CSV 那三列的单位是 k 张/日），免得读者被 1e-06 的量级卡住。
    ident = (f'（{len(_res)} 个月逐月核过，两块之和与总量的最大差 '
             f'{_res.max() * 1000:.3f} 张/日，就是官方那三列自己的取整）' if len(_res) else '')

    # ── ③ XSP 的披露起点：图上左边那段空白是披露史，不是 0 ───────────────────
    _xsp = df['adv_xsp_options_kcontracts'].dropna()
    xsp0 = (f'（XSP 自 {mlab(_xsp.index[0])} 才有数，图上更早的空白是<b>披露史</b>、'
            f'不是 0）' if len(_xsp) else '')

    return [
        ('ADV',
         '<b>日均</b>成交张数（average daily volume）：公司月度披露里<b>直接印的就是'
         '日均</b>，不是当月合计 —— 本页汇总表与各图的单位一律是「k 张/日」或'
         '「mn 张/日」。⚠️ Cboe 的月度披露<b>没有交易日数这一列</b>，本页也不去别处凑'
         '一个 ⇒ 本页<b>拿不出</b>「当月合计张数」这个口径；页上所有同比比的都是两个'
         '<b>日均</b>数，<b>不含</b>「今年这个月比去年多几个交易日」那一层。'),

        ('RPC',
         '每张收入（revenue per contract）：交易所每成交一张期权向客户<b>净收到的费用</b>，'
         '<b>不是</b>标的资产的成交价格。⚠️ 是<b>净额</b>而不是毛费 —— 工作簿里这一段的'
         '官方段标题原文是 <code>Rolling Three-Month Average RPC/Net Capture</code>'
         '（报告抬头 <code>Monthly Volume &amp; Revenue Per Contract/Net Revenue Capture '
         'Report</code>），返佣等已经扣掉，页尾把由它推出的收入也称作<b>净</b>交易收入。'
         '官方口径还有两件事必须先记住：它是<b>三个月'
         '滚动平均</b>，而且<b>滞后一个月发布</b>。⇒ 汇总表最新一列的 RPC 单元格是空的，'
         '那<b>不是</b>数据缺口；凡是用到 RPC 的图都被它牵制 —— RPC 本身与隐含期权'
         '交易收入那两张比成交量那批<b>短一个月</b>，量费分解的 YTD 柱也只能截到 RPC '
         '齐的那个月。因为已被三个月平滑，'
         '用它算出来的月度波动主要来自量、不来自价。'),

        ('ADNV',
         '平均每日成交<b>金额</b>（average daily notional value）：欧股那一条以'
         '<b>欧元</b>计价、全球外汇那一条以<b>美元</b>名义额计价，<b>不是</b>合约张数、'
         '也不是股数。⇒ 它与 ADV、与美股撮合股数<b>不是一个量纲</b>（原 deck 把美股撮合'
         '与这两条 ADNV 画在同一根轴上，本页为此拆成各自成轴）；两条 ADNV 之间币种也不同，'
         '同样不能直接比高低。'),

        ('自有指数期权',
         '工作簿里的官方行名只有 <code>Index options</code>：Cboe 自有指数上的期权，'
         '本页单列 SPX、VIX 期权与 XSP（Mini-SPX）三个产品' + xsp0 +
         '。⚠️ <b>本页汇总表</b>把这一行写作 <code>Index options (proprietary)</code>，'
         '「(proprietary)」是<b>本页加的限定语、不在官方行名里</b> —— 官方那一层区分'
         '走的是<b>标的类型</b>（指数 vs 个股与 ETP，见「多重挂牌期权」），'
         '不是「有没有在别家交易所同时挂牌」。它的 RPC ' + mult +
         '，所以<b>产品结构（mix）位移对收入的杠杆大于总量本身</b>。'),

        ('多重挂牌期权',
         '官方行名 <code>Multiply-listed options (Equities &amp; ETPs)</code>：'
         '<b>个股与 ETP（ETF）上的期权</b>那一块 —— 括号里那半句才是它的外延，'
         '「多重挂牌」只是名称的字面意思（同一份合约在<b>多家</b>美国期权交易所同时挂牌），'
         '<b>不是</b>本页两块划分的判据，划分走的是<b>标的类型</b>。'
         '它与「自有指数期权」两块<b>相加即美国期权总 ADV</b>' + ident +
         ' —— Cboe 的美国期权只分这两块。它的 RPC 比自有指数期权低一个数量级，'
         '所以读「总量涨了」之前先看涨的是哪一块。'),

        ('指数期权占比',
         '<code>自有指数期权 ADV ÷ <b>Cboe 自己的</b>美国期权总 ADV</code>，'
         '即堆叠图右轴与热力矩阵格子里的那个百分数。⚠️ 分母是上面那两块之和，'
         '<b>不是全美期权市场的成交量</b> ⇒ 这条线画的是<b>产品结构（mix）</b>，'
         '<b>不是市场份额</b>。（官方那份文件里另有一节市占率，本页一格都没取用，'
         '<code>series/cboe.csv</code> 里也没有这一列。）'),

        ('VIX 期权 / VIX 期货',
         '同一个标的的<b>两类合约，在本页分属两处</b>：VIX <b>期权</b>计入美国期权 ADV'
         '（在「自有指数期权」那一块里，汇总表还单列一行）；VIX <b>期货</b>与 Mini-VIX '
         '期货属期货，在 CFE 期货 ADV 里。⇒ 两处<b>不能相加</b>，也不能用其中一处的'
         '走势去说另一处；看到「VIX」三个字先确认说的是哪一类。'),

        ('隐含期权交易收入',
         '<b>推导值，不是公司披露的数</b>：<code>当月美国期权 ADV（k 张/日）× 同月三个月'
         '滚动 RPC（$/张）÷ 1,000</code>，单位 $mn/<b>日</b>。两条腿都是官方按月披露的，'
         '所以不必像别的标的那样假设一个季度费率；代价是 RPC 已被三个月平滑。'
         '它是<b>每日</b>净交易收入的估算，要得到月度总额还得再乘当月交易日数 —— '
         '而那一列 Cboe 不披露（见 ADV）。'),

        ('量费分解',
         '本页那张桥形图分的是<b>收入</b>，恒等式是「隐含期权交易收入 = 成交<b>张数</b>'
         ' × 每张收入(RPC)」——「费」指的是<b>交易所收的费率</b>，<b>不是</b>标的的成交'
         '价格。⇒ 它与别的页上真正的「成交额 = 成交量 × <b>均价</b>」<b>不是一回事</b>，'
         '不要并读。另注：RPC 那一块里同时装着<b>结构</b>（mix 位移）与<b>定价</b>两件事，'
         '它不是一个纯粹的价格变量。'),

        ('CFE 期货',
         'Cboe Futures Exchange 的<b>合计</b>，主体是 VIX 期货；汇总表的「Futures ADV」'
         '一行与那张期货图都只有它，<b>不含</b>美国期权那两块。⚠️ 这一行的<b>外延变过'
         '一次</b>：数字资产期货（Digital futures）自 2025Q2 起并入 CFE 合计，此前'
         '<b>不含</b>（出处：<code>fetch/cboe.py</code> 的口径坑第 4 条）—— 跨 2025Q2 '
         '读同比时，涨的有一部分是口径本身变宽。'),

        ('美股撮合成交',
         '官方行名 <code>U.S. Equities - Exchange - ADV (matched shares, billions)</code>：'
         '在 Cboe <b>自家</b>美股交易所撮合成交的<b>股数</b>（bn 股/日），既不是金额，'
         '也不是全美市场的成交量。⚠️ Cboe <b>不披露</b>与它对应的成交<b>金额</b> ⇒ '
         '美股这一块的量价分解在本页<b>不具备数据条件</b>；也<b>不能</b>拿欧股 ADNV 去除'
         '它凑「均价」—— 那是欧洲市场的金额除以美国市场的股数，跨法域跨市场，'
         '商没有经济含义。'),

        ('季度至今 / YTD',
         '本页两处<b>可能装不满</b>的桶。季度柱画的是该季<b>已发布月份的月度 ADV 均值</b>'
         '（不是季度合计 —— ADV 本身已是每日口径，加总没有意义）；最新一格在该季'
         '<b>未满 3 个月时</b>就是<b>季度至今</b>，拿不满 3 个月去比上年完整的 3 个月'
         '不成立，所以<b>那一格不报同比</b>（数据正好截在 3 / 6 / 9 / 12 月、该季已满 '
         '3 个月时它就是完整季，照常报同比）。'
         '量费分解图的末柱是当年 <b>YTD</b>：覆盖到张数与 RPC 两条腿在两侧都齐的那个月，'
         '基期取去年<b>同一组月份</b>（两侧月份集合逐月相同，不是拿几个月去比 12 个月）。'
         '⇒ 未装满的那一格回答的是「到目前为止 vs 去年同期」，<b>不能</b>与完整桶比大小。'),
    ]


# ────────────────────────────── 主流程 ──────────────────────────────
def main():
    df = load()
    LATEST = df.index[-1]
    LATEST_RPC = df['rpc_us_options_usd'].dropna().index[-1]
    ALL = list(df.index)

    # 所有窗口一律从**数据最新月**倒推，绝不依赖运行当天的日期（幂等要求）
    # W13 现在只给末尾核对表用（表是拿着逐行核对的，127 行没人对得完）。
    # 2026-08-19 之前 Exhibit 5 的堆叠柱也吃这个窗口，见该处的说明。
    W13 = ALL[-WIN_TABLE:]
    _i0 = next((i for i, p in enumerate(ALL)
                if f'{p.year}-{p.month:02d}' >= WIN_FROM), 0)
    W25 = ALL[_i0:]
    XL13 = [mlab(p) for p in W13]
    XL25 = [mlab(p) for p in W25]
    XL_LONG = [mlab(p) for p in ALL]
    # 季度刻度那张（Exhibit 8）的左端：与 WIN_FROM 同一个月份换算到季度（'2016-01' →
    # 2016Q1）。写成换算而不是写死 '2016Q1'，WIN_FROM 哪天再动季度图跟着一起动。
    Q_FROM = pd.Period(WIN_FROM, freq='M').asfreq('Q')

    # 口径断点：2017 年为 Bats pro-forma combined，2018-01 起才是实际口径。
    # break_at 语义是「从这一期起与左侧不可比」，边界落在**首个 2018 月的左缘**。
    # 取「首个 year>=2018 的下标」而不是硬编码 12、也不是数首年的月数：源文件若哪天
    # 回补到 2016，数首年月数会把虚线错画到 Jan-17。首月已晚于 2017 则不画（=None）。
    I_2018 = next((i for i, p in enumerate(ALL) if p.year >= 2018), None)
    BREAK_PF = I_2018 if I_2018 else None       # 0 也视作无断点（左缘无意义）
    # pro-forma 的**年份集合**，从数据现推，不写死。2026-08-18 回补 2016 全年之后
    # 它是 {2016, 2017} —— 那一册的脚注原文：「the operating statistics for these
    # periods are presented on a combined basis to reflect information pertaining to
    # Bats Global Markets, Inc., which was acquired by CBOE Holdings, Inc. on
    # February 28, 2017.」两年是同一种口径，所以断点线位置不动（仍是首个 2018 月的左缘），
    # 变的只是「线左边那段」有多长。写死 2017 会让图上画了两年、图注只认一年。
    PF_YEARS = sorted({p.year for p in ALL if p.year < 2018})
    PF_YEAR = PF_YEARS[-1] if PF_YEARS else None      # 热力矩阵只关心最后（最新）那一年
    PF_ZH = ('—' if not PF_YEARS else
             f'{PF_YEARS[0]} 年' if len(PF_YEARS) == 1 else
             f'{PF_YEARS[0]}–{str(PF_YEARS[-1])[2:]} 年')

    # RPC 与 implied revenue 的窗口以 LATEST_RPC 结尾：末点为 null 时 lines_endlabels
    # 会对 null 调 toFixed 而崩，且一个空的末点也不带信息
    i_rpc = ALL.index(LATEST_RPC)
    W25R = ALL[_i0:i_rpc + 1]
    XL25R = [mlab(p) for p in W25R]

    # 断点在**月度图**横轴上的下标。走 draw_break() 的月度图左端都是 _i0（Exhibit 3/4
    # 只是右端提前一个月，左端相同），所以下标一律是 BREAK_PF − _i0，一处算完各图共用。
    # 例外是 Exhibit 7：它的左端由 mrwin 裁到 Jan-19，已经在断点右边，压根不画断点线。
    BRK_I = None if BREAK_PF is None or BREAK_PF <= _i0 else BREAK_PF - _i0

    #: 本页的断点线一律**只画线、不挂竖排标签**（`break_at` 给、`break_label` 不给）。
    #:
    #: 竖排标签是 rotate(-90) 从绘图区顶端沿断点线挂下来的一条长条（assets/charts.js 里
    #: `ex.break_label` → `brks.push` 那一段）。它与柱值标签按构造垂直相交。引擎有一道
    #: 避让（同文件「断点标签避让」那一段，`brks.forEach`）：沿同一条竖线上下找一段够长
    #: 的空白挪过去，找不到就原地不动 —— 于是标签直接印穿数字。
    #: （这里原来写的是两个 charts.js 行号。charts.js 是 34 页共用、每轮都在动的文件，
    #:  行号必漂 —— 上一轮就是照着漂掉的行号去核对，反手又写下两条对不上的新行号。
    #:  所以本文件一律改用搜得到的标识符/原句当锚点，不写行号，也不写「原来那行现在
    #:  是什么」—— 后半句同样要人肉复核，而它正是上一轮写错的那一句。）
    #: 2026-08-19 实测（tools/visual_qa.py --page cboe）：窗口放到 2016-01 之后，
    #: 「2016–17 年 = Bats pro-forma」这 23 个字压出 6 处 🔴 —— Ex2 压 7.4、Ex4 压 $1.6、
    #: Ex5 压 29.1%、Ex8 压 7.0、Ex10 压 302/267（重叠面积 56.9–86.3px²，🔴 门槛 60px²
    #: 一带；另有 5 处 🟡，含 Ex10 压住「左右轴零点不同高」那句轴注）。
    #:
    #: 为什么不改文案长度或换个位置：那条竖直带上有没有一段够长的空档，是**渲染期**的
    #: 几何问题（柱值标签钉在各自柱顶，高低由数据决定），build 期算不出来；引擎已经在
    #: 找了、找不到。build 期能做的只有赌一个字数，赌错就是一条 🔴，赌对也只是把图注
    #: 已经说过的话再竖着写一遍。所以不赌。
    #:
    #: 去掉标签不丢信息 —— 三处都还在说同一件事：
    #:   ① 每张图自己的图注（draw_break / ex6 / exq 里那句「⚠️ 红色竖虚线左侧…」）；
    #:   ② 页尾 notes 的 `_brk_note`，按 payload 现读，逐个点名画了线的 Exhibit；
    #:   ③ Exhibit 1 表注。
    #: 竖线本身保留：CONTRACT §5.2 要的是「口径断点必须画出来」，画的是线不是字。
    #: 同一处置已在 build/single.py:BREAK_LABEL_MAX 落地（enx/jpx/sgx/tmx/miax 的
    #: payload 现在都是有 break_at、无 break_label）；那边按窗口期数卡 60，本页不能照抄
    #: —— Exhibit 8 是季度轴，只有 43 期，照 60 卡会放行，而它恰恰是压穿 7.0 的那张。
    #: 下面三处（draw_break / Exhibit 6 / Exhibit 8）都只给 break_at，各自留了回指。

    def draw_break(e, extra=''):
        """给一张跨过 pro-forma 断点的**月度**图挂上红色竖虚线 + 图注说明。

        CONTRACT §5.2：口径断点必须画出来，不能靠图注文字提一句就算数。2026-08-18 把
        月度图从「近 25 个月」放到 2016-01 之后，Exhibit 2/3/4/9a/9b/10/11 全都跨过了
        2016–17 那段 Bats pro-forma，但只有 Exhibit 5/6 画了线 —— 同一页上同一个断点，
        有的画有的不画，读者会以为没画线的那几张不受影响。这里统一收口。

        一类图**故意不走这个函数**，理由写在图注里，不是漏了：Exhibit 12 是热力矩阵，
        没有连续横轴，引擎画不出 break_at。
        （2026-09 之前还有一张：原 Exhibit 14 的 TTM 滚动柱，它的「不可比」是一段 12 个月
        的渐变区间而不是一条线。那张图已删 —— 全页改单月口径后它与 Exhibit 2 完全重复，
        详见页尾「口径与方法说明」。）
        """
        if not BRK_I:
            return e
        e['break_at'] = BRK_I
        # 只给线、不给 break_label（理由见上面那段）：走这个函数的图里，gs_bar /
        # stacked_dual 逐柱标数值，那条竖带上一个空档都没有，标签会直接印穿柱值；
        # lines_endlabels 那几张（Ex3/9a/9b）本来挂得住，但同一页上不能一半挂一半不挂。
        # 口径由下面这句图注交代。
        # 「次轴同比也跨了口径」这半句只对**真有次轴同比**的图成立 —— 现读 payload
        # 判断，不按图号写死（Exhibit 3/9a/9b 是单纯的曲线，没有次轴）。
        # 改单月口径之后这句的机制变了：滚动窗口会把断点两侧「拌」在一起（一个点里同时
        # 含两种口径的月份），单月同比不拌 —— 它是干净的两个点相除，但其中**分母**那个点
        # 落在虚线左侧。受影响的月数一样是 12 个，第一个分子分母都在实际口径里的点晚一个月。
        _roll = (f'次轴那条单月同比更要留神：它比的是当月与去年同月，虚线右侧头 12 个月的点'
                 f'分子在实际口径、<b>分母仍落在虚线左侧的 pro-forma 月份上</b>，是跨口径相除；'
                 f'第一个两端都在实际口径里的同比点是 {mlab(ALL[BREAK_PF] + 12)}。'
                 if e.get('yoy') else '')
        e['note'] = (e.get('note') or '') + (
            f'⚠️ 红色竖虚线左侧（{PF_ZH}，{BRK_I} 期）为 Bats pro-forma combined 口径'
            f'（Cboe 2017-02 完成收购 Bats），与其后各年不完全可比 —— 跨线读水平值只当'
            f'量级看，跨线的同比与环比同样受影响。' + _roll + extra)
        return e

    def col(name, win):
        return df[name].reindex(win).values.astype(float)

    # ── 单月口径的代价实测：**逐图**现算，数字一个都不写死（理由见文件头那一段）──
    # CONTRACT §6.1 第 3 条：一张图一段，拿**它自己那条序列 + 它自己那段窗口**实测。
    # 页级常量在这里曾经存在过（四张图共用美国期权 ADV 的一份数），那是跨图引错，
    # 已删；下面 yoy_cal_zh(图号, 序列, 窗口, 点名) 逐张调，账本进 COST_LOG。
    # 理由那一句写的是**一句可核对的事实**（页面所有者的指令），不写「看着更灵敏」这类
    # CONTRACT §6.1 明令禁止的说法。
    #
    # CALIB 仍然留着，但它现在只有一个身份：**Exhibit 2 那条线**（美国期权 ADV）的实测，
    # 供汇总表注与页尾口径条引用；引用它的每一处都必须点名「这是 Exhibit 2 那条线」，
    # 不许再写成「本页序列」。窗口与 Exhibit 2 逐格相同（W25）。
    CALIB = caliber_stats(df['adv_us_options_kcontracts'], W25)
    #: CALIB 量的是哪一张图那条线。写成常量而不是散在文案里的字面量，是因为下面有一条
    #: 构建期断言拿它去和 COST_LOG 对数 —— 图号哪天变了，是当场停机而不是印出假话。
    _CAL_EX = 2

    ex = []

    # ── Exhibit 2：Total U.S. options ADV（gsx.lvl_bar → gs_bar）──
    adv = col('adv_us_options_mn', W25)
    adv_all = df['adv_us_options_mn'].values.astype(float)
    ex.append({
        'n': 2, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': XL25,
        'title': 'Total U.S. options ADV',
        'ylab': 'mn contracts / day', 'ylab2': '% y/y, single-month', 'legend': 'Monthly',
        'values': L(adv),
        'yoy': yoy_rhs(df['adv_us_options_mn'], W25),
        # 2026-08 那一版这里写的是「口径与 deck 有意不同 —— deck 画单月同比，本页画
        # 12 个月滚动合计同比」。2026-09 改回单月之后那句当场为假：现在两边同口径了。
        'note': f'{XL25[0]} 至 {XL25[-1]}（{len(W25)} 个月）。次轴金色折线是同比而不是 12 个月'
                f'滚动均线（均线只是把柱子再平滑一遍、不带新信息），这一点与 deck 一致；'
                f'<b>口径也与 deck 相同</b>（都是单月同比）—— 2026-08 至 2026-09 之间本页曾'
                f'改画 12 个月滚动合计同比，现按所有者要求改回。{mlab(LATEST)} '
                f'{comma(adv[-1], 1)} mn/日，'
                f'单月同比 {pctf(yoy(adv_all))}、环比 {pp(mom(adv_all))}。'
                + yoy_cal_zh(2, df['adv_us_options_mn'], W25, '美国期权 ADV'),
    })
    draw_break(ex[-1])

    # ── Exhibit 3：Revenue per contract by book（gsx.multi_line → lines_endlabels）──
    # 单位与原 deck 一致：美元/张、3 位小数。原先这里改成「美分/张」是因为引擎的格式器
    # 最细只到 usd2（$0.07 → 多重挂牌那条线剩不到两位有效数字）；引擎补上 usd3/f3 之后
    # 这个绕道没必要了，换回美元还能与汇总表、核对表、图注的 $0.072 逐字对上。
    rpc_us = col('rpc_us_options_usd', W25R)
    rpc_ix = col('rpc_index_options_usd', W25R)
    rpc_ml = col('rpc_multilist_options_usd', W25R)
    ratio = rpc_ix[-1] / rpc_ml[-1]
    ex.append({
        # yfloor=0：RPC 是单价，不可能为负，而线图默认下界会掉到 −$0.12。
        'n': 3, 'kind': 'lines_endlabels', 'fmt': 'usd3', 'yfmt': 'usd2', 'yfloor': 0,
        'xlabels': XL25R,
        'title': 'Revenue per contract by book',
        'ylab': '$ per contract',
        'series': [
            {'name': 'All U.S. options', 'color': 'NAVY', 'values': L(rpc_us)},
            {'name': 'Index (proprietary)', 'color': 'MBLUE', 'values': L(rpc_ix)},
            {'name': 'Multiply-listed', 'color': 'BLUE', 'values': L(rpc_ml)},
        ],
        # 「roughly 10x」是照搬 deck 的一句口语化倍数，早就不成立了：同一张卡片的中文
        # 图注现算出来是 ratio 倍（2026-08-19 实测 14.8），英文来源行却还印着 10，
        # 读者两句都看得到。倍数随 mix 每月都在动，所以这里也现算，不再写死。
        'src_extra': f'RPC is a three-month rolling average published on a one-month lag, '
                     f'not a single-month figure. Index options carry roughly '
                     f'{ratio:.0f}x the RPC of multiply-listed',
        'note': f'窗口以 RPC 的最新可得月 {mlab(LATEST_RPC)} 结尾（成交量已到 {mlab(LATEST)}，'
                f'RPC 滞后一个月发布），不是数据缺口。{mlab(LATEST_RPC)}：全美股期权 '
                f'{comma(rpc_us[-1], 3, "$")}、自有指数期权 {comma(rpc_ix[-1], 3, "$")}、'
                f'多重挂牌 {comma(rpc_ml[-1], 3, "$")} —— 指数期权是多重挂牌的 '
                f'{ratio:.1f} 倍，所以 mix（Exhibit 5）对收入的杠杆远大于总量。',
    })
    # RPC 同样是「口径月」序列：2016–17 的分子分母都是 pro-forma combined 的收入与张数。
    draw_break(ex[-1])

    # ── Exhibit 4：Implied options transaction revenue per day（gsx.lvl_bar → gs_bar）──
    rev = col('opt_rev_day_usdmn', W25R)
    rev_all = df['opt_rev_day_usdmn'].dropna().values.astype(float)
    ex.append({
        # 柱顶标签用 usd1：25 根柱塞进半栏时 "$4.41" 这样的 5 字标签会互相压字。
        # 表格视图会自动回到 usd2（charts.js 的 PRECISE 映射），两位小数一点即得。
        'n': 4, 'kind': 'gs_bar', 'fmt': 'usd1', 'xlabels': XL25R,
        'title': 'Implied options transaction revenue per day',
        'ylab': '$mn / day', 'ylab2': '% y/y, single-month', 'legend': 'Monthly',
        'values': L(rev),
        'yoy': yoy_rhs(df['opt_rev_day_usdmn'], W25R),
        'src_extra': 'Current-month ADV x three-month rolling RPC. Cboe is the only name in '
                     'this set where BOTH inputs are officially disclosed monthly, so no '
                     'quarterly rate has to be assumed — but the RPC is a three-month average, '
                     'so the result is smoothed.',
        'note': f'<b>推导值，非公司披露。</b>= 当月美国期权 ADV（k 张/日）× 同月三个月滚动 RPC'
                f'（$/张）÷ 1,000 → $mn/日。假设：RPC 的三个月滚动口径可以直接套在单月成交量上；'
                f'因 RPC 已被平滑，本图的月度波动主要来自量而不是价。'
                f'{mlab(LATEST_RPC)} 为 {comma(rev[-1], 2, "$")}mn/日，'
                f'单月同比 {pctf(yoy(rev_all))}、环比 {pp(mom(rev_all))}。'
                f'柱顶标签取 1 位小数（{len(W25)} 根柱，'
                f'2 位小数会压字），点右上角「表格」可看 2 位小数。'
                f'这条收入线的量与价各贡献多少，见 Exhibit {EX_DECOMP} 的分解。'
                # 派生列：代价拿**本图真画出来的那条隐含收入序列**自己跑，不拿它的
                # 任一分量（ADV 或 RPC）顶替 —— 两个因子的同比不等于乘积的同比，
                # 而读者读的是这条乘出来的线。
                + yoy_cal_zh(4, df['opt_rev_day_usdmn'], W25R, '隐含期权交易收入/日，= ADV × RPC'),
    })
    # 隐含收入 = ADV × RPC，两个因子在 2016–17 都是 pro-forma combined 口径。
    draw_break(ex[-1])

    # ── Exhibit 5：U.S. options mix（gsx.stack_share → stacked_dual）──
    # 2026-08-19 窗口由 13 个月放到 WIN_FROM 起，与本页月度图统一的左端一致
    # （「其余时序图」不成立：Exhibit 7 起于 Jan-19、Exhibit 13 的年度桥起于 2022）。
    # 13 个月不是数据下限：这两列在 series/cboe.csv 里 2016-01 起 127 期全满
    # （Exhibit 2 与 Exhibit 6 画的就是它们的和），13 是画的时候截的。
    # stacked_dual 属 mrwin.DENSE：占比线走 Catmull-Rom，窗口内一个 null 都不能有 ——
    # 下面显式校验，日后源文件缺一个月要在构建期响，而不是在页面上画出一条塌到零的假线。
    ix13 = col('adv_index_options_kcontracts', W25)
    ml13 = col('adv_multilist_options_kcontracts', W25)
    if np.isnan(ix13).any() or np.isnan(ml13).any():
        raise SystemExit('Exhibit 5 是平滑图型，窗口内不许有缺值：'
                         f'index 缺 {int(np.isnan(ix13).sum())} 期、'
                         f'multi-list 缺 {int(np.isnan(ml13).sum())} 期')
    share13 = ix13 / (ix13 + ml13) * 100
    # 右轴上界：原来是「上取整到 10 的倍数再加 10」，占比只在 25–33% 之间动却把轴拉到
    # 0–50%，这条线的振幅被压掉近一半（原 deck 的 stack_share 把它压进画布上 1/3，
    # 右轴实际只有约 8–36%）。引擎的 stacked_dual 强制右轴从 0 起，能调的只有上界，
    # 所以取「刚好罩住最大值的那一档」——留 2% 余量免得最高点顶在画布边线上。
    ymax = int(np.ceil(np.nanmax(share13) * 1.02 / 10.0) * 10)
    # ⚠️ 已知残留，别拿 ymax 去调它：本图末点的两个标签会各压住一根右轴刻度
    # （visual_qa 记 4 条 —— 「30% × 27.6%」与「20% × 15,687」，两个视口各一对；
    # 768 下 15.9px² 记 🟡，1280 下 11.8/11.0px² 记 🔵）。
    # 2026-08-19 实测几何（headless Chrome 量 getBBox，viewBox 1172 宽）：
    #   band = pw/127 = 7.8u，末柱中心距绘图区右缘只有 band/2 = 3.9u；
    #   右轴刻度栏起点在右缘 + fscale(6) = 10.2u 处；
    #   而末点标签宽 31.8u（27.6%）/ 34.3u（15,687），居中挂在末柱上，
    #   于是各有 1.8u / 3.1u 探进刻度栏 —— 是**横向溢出**，与右轴上界无关。
    # 换 ymax 不解决且会更糟：刻度间距 = 10/ymax×ph，标签与刻度的垂直间隙同比缩放，
    # ymax 调大间隙更小；调小到 30 才躲得开，可 30 < max(share) 会把线截掉。
    # 引擎对这一类冲突本来就有裁决（charts.js 里「末点读数是真实数据、刻度只是标尺，
    # 冲突时让刻度让位」那条，实现是 draw 末尾的 dropClashingTicks），只是它只对
    # priorityLabs 生效，而 stacked_dual 一个都没往里塞：现搜 `priorityLabs.push` 共三处，
    # 分别落在 gs_bar / qtr_bar / grouped_bars 三个分支里（原注写的是「bar_line_dual /
    # qtr_bar / grouped_bars」加三个行号 —— 行号全漂了，bar_line_dual 那一项也是错的，
    # 那个分支一处都没塞）。
    # 真正的修法是在 charts.js 里把 stacked_dual 的末点标签也登记进 priorityLabs，
    # 那是 34 页共用的引擎文件，得单开一轮回归，不在本页的改动范围内。
    ex.append({
        'n': 5, 'kind': 'stacked_dual', 'fmt': 'f0c', 'xlabels': XL25,
        'title': 'U.S. options mix: proprietary index vs. multiply-listed',
        'ylab': 'k contracts / day', 'ylab2': '% index',
        'stacks': [
            # label_color 不能给 WHITE：引擎给所有数值标签加了 2.4px 的**白色**描边
            # （为了不被均线/折线划穿），白字 + 白描边在 6.6px 下会糊成一个白方块，
            # 13 个月窗口下深蓝段上的四个数字全部读不出（改之前的渲染实测如此）。
            # 改成深色 INK：白描边此时正好当成描白边的深字用，在深蓝底上反而读得出来。
            # 窗口放到 127 期后段内数值不会挤成一片：charts.js 的 stacked_dual 分支
            # 逐段调 thinLabels()，按实测 bbox 抽到不相交为止（一段一抽，见 charts.js 的
            # stacked_dual 分支里那次 `thinLabels(labst)`；原注写的行号 1473 已经漂到别处）。
            {'name': 'Index options (proprietary)', 'color': 'NAVY',
             'values': L(ix13), 'label': True, 'label_color': 'INK'},
            {'name': 'Multiply-listed options', 'color': 'BLUE',
             'values': L(ml13), 'label': True, 'label_color': 'INK'},
        ],
        'line': {'name': '% index (RHS)', 'color': 'GREEN', 'values': L(share13), 'ymax': ymax},
        'note': f'两段之和即 Total U.S. options ADV（Exhibit 2 × 1,000）—— Cboe 的美国期权只分这两块。'
                f'右轴 = 自有指数期权占比：{XL25[0]} {share13[0]:.1f}% → {XL25[-1]} {share13[-1]:.1f}%'
                f'（{nz(share13[-1] - share13[0], 1):+.1f}pp），窗口内（{len(W25)} 个月）在 '
                f'{np.nanmin(share13):.1f}–{np.nanmax(share13):.1f}% 之间 —— '
                # deck 的窗口走 DECK_WIN_STACK（历史事实），**不**借 WIN_TABLE（核对表
                # 行数，会动）。两者今天同为 13，但耦合在一起时核对表一改行数，这句就会
                # 悄悄改口说 deck 原来的窗口变了 —— 沙盒实测 WIN_TABLE=15 时这里印
                # 「原来的 15 个月窗口」，而页尾窗口条里同一件事写的还是 13。
                f'原来的 {DECK_WIN_STACK} 个月窗口只看得到 '
                f'{np.nanmin(share13[-DECK_WIN_STACK:]):.1f}–'
                f'{np.nanmax(share13[-DECK_WIN_STACK:]):.1f}% 这一小段，'
                f'这条比重线摆动的真实幅度要看满窗口才读得出。'
                f'这条线比总量更值钱：指数期权的 RPC 约为多重挂牌的 {ratio:.0f} 倍。',
    })
    # 窗口放宽之后本图第一次跨过 pro-forma 断点，所以断点线必须画在图上 ——
    # CONTRACT §5.2：口径断点不能只靠图注文字提一句。下标由 draw_break 统一算
    # （BREAK_PF − _i0），走 draw_break() 的月度图共用同一处，不再各写一份。
    draw_break(ex[-1],
               extra=(f'上面那句「{XL25[0]} → {XL25[-1]}」的占比变动因此是跨口径读的；'
                      f'纯实际口径的起点是 {XL25[BRK_I]}（当时 {share13[BRK_I]:.1f}%）。'
                      if BRK_I else ''))

    # ── Exhibit 6：Full U.S. options ADV history（gsx.long_line → lines，通栏）──
    ex6 = {
        # zero_base / end_label 对应原 deck 的 long_line：set_ylim(0, max*1.16) + n_label。
        # 不给 zero_base 时引擎走的是 y0 = min − 极差×5%，那是一次没有标注的隐性截轴，
        # 在这张「约 3.5 倍」的全历史图上会把增长幅度凭空放大（也正是原来纵轴刻度出现
        # 7.5/12.5 这种半档、还被轴格式器印成 8/13 的根因）。
        'n': 6, 'kind': 'lines', 'fmt': 'f1', 'label_fmt': 'f1',
        'zero_base': True, 'end_label': True,
        'xlabels': XL_LONG, 'xstep': max(1, len(ALL) // 14),
        'full': True, 'height': 300,
        'title': f'Full U.S. options ADV history since {ALL[0].year}',
        'ylab': 'mn contracts / day',
        'series': [{'name': 'Total U.S. options ADV', 'color': 'NAVY', 'values': L(adv_all)}],
        'src_extra': 'Full disclosed history; zero-based axis',
        'note': f'{XL_LONG[0]} → {XL_LONG[-1]} 共 {len(ALL)} 个月，无缺月。'
                f'{comma(adv_all[0], 1)} mn/日 → {comma(adv_all[-1], 1)} mn/日，'
                f'约 {adv_all[-1] / adv_all[0]:.1f} 倍。最近 3 个月：'
                + '、'.join(f'{XL_LONG[i]} {adv_all[i]:.1f}' for i in (-3, -2, -1))
                + '。纵轴从 0 起（同原 deck），末点标出最新读数。',
    }
    if BREAK_PF:
        ex6['break_at'] = BREAK_PF
        # 本图是 lines + end_label，断点线那条竖直带上其实是空的，标签挂得住 ——
        # 但全页只此一张挂字、其余五张光秃秃，读者会以为那是两种不同的断点。
        # 同一个断点在同一页上只能有一种画法，所以跟着一起去掉（理由见上面那段）。
        # 「异口径的是虚线**左边**那段」这句话原来靠标签点明（lpla/msci 的先例里变口径
        # 的是断点右侧，方向相反），现在由下面这句图注和页尾 _brk_note 各说一遍。
        # 断点滚出窗口（源文件哪天只保留 2018 起）时这一整句必须跟着消失，
        # 否则就成了「图注说画了线、图上没有」的自相矛盾。
        ex6['note'] += (f'⚠️ 红色竖虚线左侧（{PF_ZH}）为 Bats pro-forma combined 口径'
                        '（Cboe 2017-02 完成收购 Bats），与其后年份不完全可比，'
                        '读长期趋势应从虚线右侧起算；倍数一句是端点对端点，同样受此影响。')
    ex6['note'] += ('（另注：原 deck 在末 3 个月画了一个红色虚线椭圆做强调，'
                    '网页图表引擎没有这个元件。）')
    ex.append(ex6)

    # ── Exhibit 7：Proprietary index options ADV by product（gsx.multi_line → lines_endlabels）──
    # 单位用「千张/日」而不是原 deck 的「百万张/日」：百万张口径下 XSP 只剩两位有效
    # 数字（2026-08-19 实测 0.24mn），而三条线共用一个格式器。引擎后来补了 f2/f3，但
    # 两位有效数字仍不如千张口径下的三位整数好读，故维持千张；数值与 deck 一致（× 1,000）。
    # ⚠ 本图是 `lines_endlabels`，属 `mrwin.DENSE`：引擎把整条 values 交给 Catmull-Rom
    # 平滑，null 参与插值就是一条塌到零的假线，首尾为 null 时还会在逐点标数值那步抛
    # TypeError、让该卡片之后的 exhibit 全不渲染（build/verify_pages.py 有专门一条规则拦它）。
    # 窗口从「近 25 个月」拉到 2016-01 之后这一条第一次咬人：XSP 2019-01 才单列，
    # 前面 36 个月全是 null。所以左端由 mrwin 按「所有线都已经有值」裁决，
    # **不是补 0、也不是补上一期的值** —— 那是画一个数据里不存在的点。
    _legs = [mrwin.Leg('spx', 'SPX options', col('adv_spx_options_kcontracts', W25), 'primary'),
             mrwin.Leg('vix', 'VIX options', col('adv_vix_options_kcontracts', W25), 'primary'),
             mrwin.Leg('xsp', 'XSP options（Mini-SPX）',
                       col('adv_xsp_options_kcontracts', W25), 'primary',
                       'Cboe 自 2019-01 才单列 XSP')]
    _w7 = mrwin.resolve('lines_endlabels', _legs, XL25, 0)
    W7, XL7 = W25[_w7.start:], XL25[_w7.start:]
    spx, vix, xsp = (_w7.cut(l.vals) for l in _legs)
    # yfloor=0 到底挡掉了多大一块，现算：lines_endlabels 的默认 y 轴留白式是
    # y0 = min − 极差×0.20、y1 = max + 极差×0.18（assets/charts.js 的 lines_endlabels
    # 分支，搜 `r2 * 0.20`）。原注写死的「−1,000 千张/日」「约 1/9 的画布」是旧窗口下的
    # 实测，窗口一动两个都不对（2026-08-19 实测 −1,059 / 14%）—— 换一个新的写死数字
    # 只是把过期时间往后推一轮，所以两个都改成每次构建自己算。
    _e7lo = min(float(np.nanmin(v)) for v in (spx, vix, xsp))
    _e7hi = max(float(np.nanmax(v)) for v in (spx, vix, xsp))
    _e7r = (_e7hi - _e7lo) or 1.0
    _e7_floor = _e7lo - _e7r * 0.20
    _e7_waste = -_e7_floor / (_e7hi + _e7r * 0.18 - _e7_floor) * 100
    ex.append({
        # yfloor=0：合约张数恒正，而 lines_endlabels 的默认下界是 min − 极差×20%
        # （上面的 _e7_floor），画布有 _e7_waste 那么一块在展示一个不存在的量纲区间。
        # 没有任何点落在 0 以下，所以这不是截轴（不会出现红圈与断口），只是把轴归零。
        'n': 7, 'kind': 'lines_endlabels', 'fmt': 'f0c', 'yfloor': 0, 'xlabels': XL7,
        'title': 'Proprietary index options ADV by product',
        'ylab': 'k contracts / day',
        'series': [
            {'name': 'SPX options', 'color': 'NAVY', 'values': L(spx)},
            {'name': 'VIX options', 'color': 'RED', 'values': L(vix)},
            {'name': 'XSP options (Mini-SPX)', 'color': 'GREEN', 'values': L(xsp)},
        ],
        'src_extra': 'The only three index option products Cboe breaks out (XSP from Jan-2019). '
                     'Deck used a log scale: XSP is a fraction of SPX in absolute terms but has '
                     'grown fastest — here the axis is linear and zero-based, so read XSP/VIX '
                     'in the table view',
        'note': f'Cboe 单列的三个指数期权产品（VIX / Mini-VIX 期货属期货，不在此图）。'
                f'{mlab(LATEST)}：SPX {comma(spx[-1], 0)}k、VIX options {comma(vix[-1], 0)}k、'
                f'XSP {comma(xsp[-1], 0)}k 张/日。窗口内 XSP 增长最快'
                f'（{XL7[0]} {comma(xsp[0], 0)}k → {XL7[-1]} {comma(xsp[-1], 0)}k，'
                f'{pctf(xsp[-1] / xsp[0] - 1)}），但绝对量只有 SPX 的 '
                f'{xsp[-1] / spx[-1] * 100:.0f}%。'
                f'<b>与原 deck 的差异：</b>原 deck 用对数轴把三条线拉开，'
                f'网页图表引擎只有线性轴，XSP 与 VIX 在图上被压得很扁 —— '
                f'要读它们自己的走势请切「表格」视图。纵轴从 0 起（张数不可能为负），'
                f'单位由「百万张/日」改为「千张/日」，数值本身不变。' + _w7.why,
    })

    # ── Exhibit 8：U.S. options ADV by quarter（gsx.qtr_bar → qtr_bar）──
    sq = df['adv_us_options_mn'].dropna()
    q = sq.groupby(sq.index.asfreq('Q')).agg(['mean', 'count'])
    qv = q['mean'].values.astype(float)
    qi = list(q.index)
    n_in_last = int(q['count'].iloc[-1])
    qyoy = np.array([(qv[i] / qv[i - 4] - 1) * 100 if i >= 4 and qv[i - 4] else np.nan
                     for i in range(len(qv))])
    # 2026-08-19：左端由「末 WIN_QTR = 14 个季度」（照搬原 deck）改成本页月度图统一的
    # WIN_FROM，换算到季度即 Q_FROM（不是「其余时序图」—— Exhibit 7 起于 Jan-19、
    # Exhibit 13 的年度桥起于 2022）。判据与 Exhibit 2/5/14 那批一模一样 ——
    # 14 个季度不是数据下限，本页月度序列自 WIN_FROM 起 127 期全满，季度轴上一季不缺
    # （下面现验，不靠人眼数）。同门的 build/cme.py 的季度柱同一天同样处理。
    q0 = next((i for i, p in enumerate(qi) if p >= Q_FROM), 0)
    _qhole = [str(p) for p, c in zip(qi[q0:-1], q['count'].values[q0:-1]) if c != 3]
    if _qhole:
        raise SystemExit(f'Exhibit 8：{Q_FROM} 起有未满 3 个月的季度 {_qhole}，'
                         f'季内均值不可比，请先补月度数据再放宽窗口')
    qw = slice(q0, len(qv))
    # 同比要上年同季当分母，窗口左端头几季因此没有线。留 null（不掐头、不补零），
    # 下面的图注把「空几格、第一个有值的是哪一季」写出来 —— 空白必须有出处。
    _qlead = next((i for i, v in enumerate(qyoy[qw]) if v == v), len(qv) - q0)
    exq = {
        'n': 8, 'kind': 'qtr_bar', 'fmt': 'f1', 'label_fmt': 'f1',
        'xlabels': [str(p) for p in qi[qw]],
        'title': 'U.S. options ADV by quarter',
        'ylab': 'mn contracts / day', 'legend': 'Complete quarter',
        'values': L(qv[qw]),
        'line': {'name': 'y/y (RHS)', 'color': 'GREEN', 'values': L(qyoy[qw]), 'yfmt': 'pct0'},
        'qtr_months': 3,
    }
    if n_in_last < 3:
        exq['partial_months'] = n_in_last
        exq['src_extra'] = ('Latest bar is quarter-to-date and not comparable to full quarters')
    # notes 走 innerHTML，markdown 的 ** ** 不会被渲染，只会原样印出四个星号 —— 强调
    # 一律用 <b>。（页尾 notes 里还有同一条注释。原文这里写的是「见本文件第 N 行」，
    #   行号早漂走了；上一轮改的时候顺手写下「第 N 行现在是什么」，那句也是错的。
    #   本文件不写行号，也不写行号的回溯 —— 要找同一条规矩就 grep「四个星号」。）
    exq['note'] = (f'柱为季内<b>月度 ADV 的均值</b>（不是季度合计）—— ADV 本身已是「每日」口径，'
                   f'加总没有意义。y/y 与上年同季比。'
                   # ⚠️ 未满季**不报同比**。这里原来无条件印「同比 +N%」，而那个数正是
                   #    引擎在画图时强制丢掉的那一点（assets/charts.js 的 `lineVals`：
                   #    末季未满就把线的最后一个值置 null），页尾也白纸黑字写着它「由图表
                   #    引擎强制作废」—— 页面一边声明它无效、一边把它印在图注里，读者
                   #    只会当它是真的。要说的话没少说：未满几个月、水平值多少、为什么
                   #    不给同比、上一个报得出同比的完整季是多少，逐句都在。
                   f'最新季 {qi[-1]} 已含 {n_in_last} 个月'
                   + (f'（完整季），{qv[-1]:.1f} mn/日，同比 {qyoy[-1]:+.0f}%。'
                      if n_in_last >= 3 else
                      f'，为季度至今、与完整季不可比：{qv[-1]:.1f} mn/日，'
                      f'<b>这一季不报同比</b> —— 拿 {n_in_last} 个月的均值去比上年完整的 '
                      f'3 个月，季内月份构成都不一样，那不是同比；右轴绿线的最后一点'
                      f'同样由图表引擎强制作废，<b>图上根本没有这个点</b>。'
                      + (f'最近一个报得出同比的完整季是 {qi[qw][-2]}：{qyoy[qw][-2]:+.0f}%。'
                         if len(qi[qw]) >= 2 and qyoy[qw][-2] == qyoy[qw][-2] else ''))
                   # 「与其余各图不同」「各 gs_bar 次轴」都是手写全称 —— Exhibit 8 建
                   # 起来的时候后面的图还没画，这两句落笔的只能是脑内枚举，而同门的
                   # build/cme.py 正是这么栽的（那页 Exhibit 9 是存量 gs_bar、次轴保留
                   # 单月同比，图注却说「各 gs_bar 都已改滚动」）。现在：外延收到**本图
                   # 自己**（「与柱同期」是本图的构造，自明），要点名别的图就走占位符，
                   # 由 ex 建完后现读 payload 回填，回填不到就停机。
                   + f'<b>右轴走的是与柱同期的季度同比</b>：「本季 3 个月 vs 上年同季 3 个月」，'
                     f'不是 {_NAV_YOY_AX}。'
                     f'柱是季度口径，线只能与柱同期，否则线讲的是另一段时间。'
                     f'一格是三个月的聚合、不是一个月，两者数出来的东西不同期，'
                     f'跨图比高低没有意义。'
                   # 左端一律报**本图横轴上真有的那一格**（qi[qw][0]），不报常量 WIN_FROM：
                   # 序列比 WIN_FROM 短时 _i0 回落到 0，轴其实从序列自己的起点开始，而
                   # 常量会印出一个页面上根本不存在的左端 —— 沙盒实测（series 截到
                   # 2017-07）原文印「本页窗口左端 2016-01 换算到季度（2016Q1）」，同一句
                   # 后半段的实测范围却是「2017Q3 – 2026Q3」，一句话自己打自己。
                   # 「各图的实际左端并不都等于它，逐图见页尾窗口条」那句已删：它是导航句，
                   # 括号里的机制（「序列本身更短的只往右让」）同页当场两个反例
                   # （Exhibit 12 首行 2017、Exhibit 13 起于 2022，都是画法约定不是数据
                   # 下限），而它指向的页尾那条当时压根没提 Exhibit 13。逐图枚举归页尾
                   # 那一条（现已现算 + 断言全覆盖），本图只说本图。
                   + f'本图的左端不是 deck 的末 {DECK_WIN_QTR} 个季度，而是本页月度窗口的'
                     f'左端换算到季度，只是刻度是季度不是月'
                     f'（{qi[qw][0]} – {qi[qw][-1]}，共 {len(qi[qw])} 个季度）。'
                   + (f'<b>左端头 {_qlead} 个季度的绿线是空的，那不是缺数</b>：同比要拿'
                      f'上年同季当分母，本页季度序列自 {qi[qw][0]} 起，第一个算得出来的'
                      f'季度因此是 {qi[qw][_qlead]}。柱本身一根不缺 —— qtr_bar 的右轴走'
                      f'非平滑 polyline，前几格留 null 就是断笔，不补零、不掐头'
                      f'（掐了左端，这根轴就不再起于 {qi[qw][0]}）。'
                      if _qlead else ''))
    # 季度轴上的断点下标要在**季度**里数，不能借用月度图的 BRK_I。
    _qbrk = next((i - q0 for i, p in enumerate(qi[qw], q0) if p.year >= 2018), None)
    if _qbrk:
        exq['break_at'] = _qbrk
        # 同样只给线、不给 break_label（理由见 draw_break 上面那段）：本图期数比月度图
        # 少得多，但每根柱头上都钉着数值，2026-08-19 实测竖排标签仍压穿柱值 7.0。
        # 「跨线的是哪几季」现算，不写死：同比点落在虚线右侧、而它的分母（上年同季）
        # 还在左侧，即下标 i 满足 _qbrk <= i < _qbrk + 4 且该点真有值（左端头几季没有
        # 分母、绿线是空的）。写死一个 4 只在「绿线在断点之前就已起线、且断点不动」时
        # 才成立 —— pro-forma 段一缩短，跨线的季数就少于 4，而写死的数不会跟着变。
        _qy = qyoy[qw]
        _qcross = [i for i in range(_qbrk, min(_qbrk + 4, len(_qy))) if _qy[i] == _qy[i]]
        _qcross_lab = ('' if not _qcross else
                       str(qi[qw][_qcross[0]]) if len(_qcross) == 1 else
                       f'{qi[qw][_qcross[0]]} – {qi[qw][_qcross[-1]]}')
        exq['note'] += (f'⚠️ 红色竖虚线左侧（{PF_ZH}，{_qbrk} 个季度）为 Bats pro-forma '
                        f'combined 口径（Cboe 2017-02 完成收购 Bats），与其后各年不完全'
                        f'可比'
                        + (f'；右轴同比跨线的那 {len(_qcross)} 个季度（{_qcross_lab}）'
                           f'同样是跨口径比出来的。' if _qcross else
                           '。虚线右侧头几季的绿线本来就没有值，不存在跨口径的同比点。'))
    ex.append(exq)

    # ── Exhibit 9a/9b：Non-options franchises（gsx.multi_line → 拆成两张单序列图）──
    # 原 deck 把「十亿股/日」「EUR bn/日」「$bn/日」三种单位画在同一根轴上，标题写
    # mixed units。三条线的量级差着一到两个数量级，最小的那条（美股撮合）几乎贴在
    # 零线上，读者看不出它有没有在动 —— 那条线是白画的。
    # 「量级」与「振幅占画布多少」两个数都现算（_no_mag / _no_flat，就在下面）：
    # 原文写死的是「2 : 15 : 64」与「0.9%」，那是 25 个月窗口下的实测；窗口放到
    # WIN_FROM 之后两个都对不上了（2026-08-19 实测窗口均值 1.5 : 10 : 39、振幅 2.1%）。
    # 换一个新的写死数字只是把过期时间往后推一轮，所以改成每次构建自己算。
    # 处理办法不是截轴：截轴的前提是「主体在轴内、个别离群点出界」，这里是三个不同
    # 量纲，整条 FX 序列会全部出界。不同量纲本来就不该同轴，所以拆开，各用各的轴与单位。
    # 只拆出两张：第三条（欧股 ADNV）与 Exhibit 11 是同一条序列、同一个窗口，
    # 再画一张就是把同一份数据在同一页上画两遍，改为在图注里指过去。
    us_eq = col('adv_us_equities_matched_shares_bn', W25)
    eu_eq = col('adv_eu_equities_adnv_eurbn', W25)
    fx = col('adv_fx_adnv_usdbn', W25)
    # 量级 = 三条线在窗口内的均值；「振幅占画布」= 若三条同轴（0 起、上界取三条的
    # 最大值），最小那条的极差占轴高的比例。两个量都只依赖当前窗口的数据，不依赖渲染。
    _no_mag = (f'{np.nanmean(us_eq):.1f} : {np.nanmean(eu_eq):.0f} : '
               f'{np.nanmean(fx):.0f}')
    _no_top = max(np.nanmax(us_eq), np.nanmax(eu_eq), np.nanmax(fx))
    _no_flat = (np.nanmax(us_eq) - np.nanmin(us_eq)) / _no_top * 100
    # yfmt 必须显式给：轴刻度的默认格式器按步长取小数位，步长落在 2.5 这一档时会把
    # 7.5 / 12.5 印成 8 / 13（Exhibit 6 原来就是这么错的），按标签量线会系统性偏半档。
    NONOPT = [
        ('9a', 'U.S. equities matched volume', 'bn shares / day', 'NAVY', us_eq, 'f2', 'f1',
         'Matched shares on Cboe U.S. equities exchanges',
         'adv_us_equities_matched_shares_bn'),
        ('9b', 'Global FX ADNV', '$bn / day', 'GREEN', fx, 'f1', 'f0',
         'Average daily notional value, USD', 'adv_fx_adnv_usdbn'),
    ]
    for nn, ttl, unit, colr, vv, ff, yf, sx, cname in NONOPT:
        ex.append({
            # yfloor=0：成交量/成交金额恒正，默认下界会掉到零轴以下（同 Exhibit 7）。
            'n': nn, 'kind': 'lines_endlabels', 'fmt': ff, 'yfmt': yf,
            'yfloor': 0, 'xlabels': XL25,
            'title': ttl, 'ylab': unit,
            'series': [{'name': ttl, 'color': colr, 'values': L(vv)}],
            'src_extra': sx,
            'note': f'原 deck 的 Exhibit 9 把美股撮合（十亿股/日）、欧股 ADNV（EUR bn/日）、'
                    f'全球外汇 ADNV（$bn/日）三种单位画在同一根轴上，窗口内的均值量级是 '
                    f'{_no_mag}，最小的那条被压得与横轴分不开。三种量纲不该同轴，故拆开各自成轴'
                    f'（窗口、线型、数值均未改）；第三条欧股 ADNV 就是 Exhibit 11 的那条'
                    f'序列（同一个 {len(W25)} 个月窗口），不再重画。'
                    f'{XL25[0]} {comma(vv[0], 2 if ff == "f2" else 1)} → '
                    f'{XL25[-1]} {comma(vv[-1], 2 if ff == "f2" else 1)}（{unit}），'
                    f'单月同比 {pctf(yoy(df[cname].values.astype(float)))}、'
                    f'环比 {pp(mom(df[cname].values.astype(float)))}。'
                    # 9a 是**美国**市场的成交股数，Exhibit 11 是**欧洲**市场的成交金额。
                    # 两者看着像一对「数量 + 金额」，其实分属两个法域、两套市场，相除得到的
                    # 「均价」不对应任何真实价格 —— 所以本页不做美股的量价分解，见 notes。
                    + ('<b>本页不拿它去除欧股 ADNV（Exhibit 11）凑均价</b>：那是美国市场的'
                       '股数除以欧洲市场的金额，跨法域跨市场，商没有经济含义。'
                       'Cboe 不披露美股撮合的成交<b>金额</b>，所以美股的量价分解在本页'
                       '<b>不具备数据条件</b>，本页也没有假装做到；能做的是期权的'
                       f'「收入 = 张数 × 费率」分解，见 Exhibit {EX_DECOMP}。'
                       if cname == 'adv_us_equities_matched_shares_bn' else ''),
        })
        # 美股撮合与全球外汇同样跨 2016–17 的 pro-forma 段（Bats 的 BZX/BYX 与
        # Bats Hotspot FX 正是被并进来的那部分），断点线照画。
        draw_break(ex[-1])

    # ── Exhibit 10：Futures (CFE) ADV（gsx.lvl_bar, show_mom=True → gs_bar）──
    fut = col('adv_futures_kcontracts', W25)
    fut_all = df['adv_futures_kcontracts'].values.astype(float)
    ex.append({
        'n': 10, 'kind': 'gs_bar', 'fmt': 'f0c', 'xlabels': XL25,
        'title': 'Futures (CFE) ADV',
        'ylab': 'k contracts / day', 'ylab2': '% y/y, single-month', 'legend': 'Monthly',
        'values': L(fut),
        'yoy': yoy_rhs(df['adv_futures_kcontracts'], W25),
        'note': f'CFE（Cboe Futures Exchange）合计，主体是 VIX 期货。'
                f'本图的同比跨零、柱又全为正，两轴零点若强行'
                f'对齐会浪费掉约一半画布，引擎因此改成两轴各自缩放并在图内左上角标出'
                f'「左右轴零点不同高」——<b>柱与折线的零线不在同一高度，不要按同一条水平线读</b>。'
                # 这里原来写「网页版的气泡箭头为 13 个月窗口写死、127 根柱下会指错柱」。
                # 那是假的：assets/charts.js 的气泡与箭头按**窗口末端**定位
                # （oval 落在 Xc(n−4)、箭头指 Xc(n−2)），源码那段注释写的就是
                # 「不能写死 Xc(9)/Xc(11)……n=13 时 n-4/n-2 正好还原原值」——
                # 窗口多长它都指末尾第二根，不会指错。本页不画它的真实理由只是
                # 「同一个环比数在图注、抬头、汇总表 m/m 列里都有」，就说这个。
                f'原 deck 对本图额外开了环比气泡（show_mom=True）：同比已经饱和时，'
                f'月度动能只能从环比看 —— 本页不给这个气泡，环比直接写在下一句里'
                f'（抬头与汇总表的 m/m 列同为单月口径，同一个数不必在图上再占一块）。'
                f'{mlab(LATEST)} {comma(fut[-1], 0)}k 张/日，'
                f'单月同比 {pctf(yoy(fut_all))}、环比 {pp(mom(fut_all))}。'
                + yoy_cal_zh(10, df['adv_futures_kcontracts'], W25, 'CFE 期货 ADV'),
    })
    draw_break(ex[-1])

    # ── Exhibit 11：European equities ADNV（gsx.lvl_bar → gs_bar）──
    eu_all = df['adv_eu_equities_adnv_eurbn'].values.astype(float)
    ex.append({
        'n': 11, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': XL25,
        'title': 'European equities ADNV',
        'ylab': 'EUR bn / day', 'ylab2': '% y/y, single-month', 'legend': 'Monthly',
        'values': L(eu_eq),
        'yoy': yoy_rhs(df['adv_eu_equities_adnv_eurbn'], W25),
        'note': f'Cboe Europe 的平均每日成交金额（ADNV，欧元计价，非合约张数）。'
                f'{mlab(LATEST)} €{eu_eq[-1]:.1f} bn/日，'
                f'单月同比 {pctf(yoy(eu_all))}、环比 {pp(mom(eu_all))}。'
                f'原 deck 的 Exhibit 9 里那条欧股线就是本图的序列'
                f'（同一个 {len(W25)} 个月窗口），拆图时没有再单画一张。'
                # 这条是**成交金额**，本页另有一条**成交股数**（Exhibit 9a，美股撮合）。
                # 两者看着像一对「金额 + 数量」，其实分属欧洲与美国两个法域、两套市场，
                # 相除得到的「均价」没有任何经济含义 —— 本页明写禁止，见 notes 的口径条。
                f'<b>不要拿它去除 Exhibit 9a 的成交股数</b>：那是欧洲市场的金额除以美国市场的'
                f'股数，跨法域跨市场，商出来的「均价」不对应任何真实价格。'
                + yoy_cal_zh(11, df['adv_eu_equities_adnv_eurbn'], W25, '欧股 ADNV'),
    })
    draw_break(ex[-1])

    # ── Exhibit 12：Index options share heat matrix（gsx.heat_matrix → heat_matrix，通栏）──
    share_all = df['index_share']
    years = sorted({p.year for p in share_all.dropna().index})[-HEAT_YEARS:]
    M = [[None] * 12 for _ in years]
    for p, v in share_all.dropna().items():
        if p.year in years:
            M[years.index(p.year)][p.month - 1] = round(float(v), 6)
    # heat_matrix 不支持 break_at（矩阵没有连续 x 轴），口径警告只能落在图注上；
    # 但那一句必须跟着「pro-forma 那一年还在不在矩阵里」走，否则 2027 年 2017 滚出
    # 10 年窗口之后，这句话会把 2018 年错说成 pro-forma 口径。
    pf_in_heat = PF_YEAR in years
    # 「更早的已滚出」要真的有滚出去的年份才能说，年数也照 HEAT_YEARS 走 —— 原文写死
    # 了一个 10，且不管矩阵里到底还剩几年 pro-forma 都照说「更早的已滚出」。
    _pf_out = [y for y in PF_YEARS if y not in years]
    heat_pf = (f'⚠️ {PF_YEAR} 年（首行）为 Bats pro-forma combined 口径，与其后年份不完全可比'
               + ((f'（{PF_ZH}同为 pro-forma'
                   + (f'，更早的已滚出这个 {HEAT_YEARS} 年矩阵）。' if _pf_out else '）。'))
                  if len(PF_YEARS) > 1 else '。')
               if pf_in_heat else '')
    ex.append({
        'n': 12, 'kind': 'heat_matrix', 'full': True,
        'title': 'Index options share of U.S. options ADV (%)',
        'rows': [str(y) for y in years],
        'cols': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug',
                 'Sep', 'Oct', 'Nov', 'Dec'],
        'matrix': M, 'fmt': 'f0', 'legend': 'Index options share of U.S. options ADV (%)',
        'row_head': '年',
        'src_extra': 'Green = richer mix (index options earn far higher RPC)',
        'note': f'格内为「自有指数期权 ADV ÷ 美国期权总 ADV」的百分数，色标取全部有限值的 '
                f'5/95 分位（与原 deck 的 RdYlGn 一致，绿=高、红=低）。' + heat_pf +
                f'{years[0]} 均值 {np.nanmean([v for v in M[0] if v is not None]):.0f}% → '
                f'{years[-1]} 年至今均值 '
                f'{np.nanmean([v for v in M[-1] if v is not None]):.0f}%。',
    })

    # ══ Exhibit EX_DECOMP：期权收入增长的「量 / 费率」分解（**不是成交额的量价分解**）══
    # 恒等式：期权交易收入 ≡ 成交张数 × 每张收入(RPC)。这是 Cboe 页上唯一做得成的分解 ——
    # 两个因子都是公司**按月官方披露**的，本页不必假设任何一个季度费率。
    #
    # 但它分的是**收入**，不是成交额。RPC 是交易所向客户收的每张费用，不是标的资产的成交
    # 价格；把它和别的页上真正的「成交额 = 成交量 × 均价」并读，会得出完全错误的结论。
    # 标题里写死「a revenue split」，图注第一句也写死，这一点不许含糊。
    #
    # 为什么美股/欧股那两块做不了：cboe.csv 里的成交**金额**列是欧洲的
    # （adv_eu_equities_adnv_eurbn），成交**股数**列是美国的
    # （adv_us_equities_matched_shares_bn）—— 跨法域跨市场，相除得到的「均价」不对应
    # 任何真实价格。宁可不做，也不拿口径不一致的分子分母凑一个均价。
    #
    # 2026-08 改横轴：由「近 13 个月的 TTM 滚动端点」改成「4 个完整日历年 + 1 根当年
    # YTD」，方法与护栏对齐全站其余 decomp（build/single.py 的 ex_decomp），跨页可比：
    # （1）**桶**：一格 = 一个完整日历年（Jan–Dec vs 上一年同 12 个月）；末格 = 当年 YTD，
    #      基期取去年**同一组月份**，两侧月份集合逐月相同 —— 不对齐就是拿 6 个月比
    #      12 个月，柱高毫无意义。
    #      ⚠ RPC 是三个月滚动平均、**滞后一个月发布**（最新月天然为空），所以 YTD 窗口取
    #      「张数与 RPC 两条腿在两侧都齐」的连续前缀，实际截至月由代码算出写进 x 标签与
    #      图注，不写死。
    # （2）**年度桶怎么聚合**：Cboe 不披露每月交易日数，ADV / 收入两列都是**日均值**，
    #      年度桶取 12 个月日均的等权合计（granularity = daily_avg 的既定语义，除以月数
    #      即回到日均口径，比值不受影响）；年度 RPC = Σ(当月 ADV × 当月 RPC) ÷ Σ当月 ADV
    #      （合计 ÷ 合计），费率不做二次平均 —— 「逐月 RPC 的简单平均」对每月等权而各月量
    #      差着一倍以上，且均值之积 ≠ 积之均值，分解会不闭合。
    # （3）**图上画对数分解按总增长重标定后的两块**：w = g_V ÷ ln(V₁/V₀)，
    #      贡献_量 = w·ln(Q₁/Q₀)、贡献_价 = w·ln(P₁/P₀)，两块相加逐格 = 算术总增长，
    #      纵轴回到 %。对数分解天然可加、无交叉项；算术分解的交叉项在量价对冲的年份能
    #      大到净增长的数倍，堆叠柱画出来就是错的 —— 算术版照算，只进图注。
    # （4）|ln(V₁/V₀)| < DEC_LN_MIN 的那一格**整根留空**：重标定权重 w 数值上是 0/0
    #      （解析上 → 1），算出来的两块没有有效位，不印一个算不准的数。
    # （5）分解是恒等式不是近似：算术闭合、对数闭合、重标定闭合三道检查残差 > DEC_EPS
    #      一律 raise —— 「两块加起来不等于总数」的分解图，读者是看不出来的。
    DEC_EPS = 1e-9      # 残差硬上限（与 build/single.py 的 DECOMP_EPS 同值同义）
    DEC_LN_MIN = 1e-6   # |ln(V₁/V₀)| 低于它整根柱留空（重标定权重 w 数值上是 0/0）

    _vol_m = df['adv_us_options_kcontracts']   # 日均张数（千张/日）
    _rev_m = df['opt_rev_day_usdmn']           # 日均收入（$mn/日）= ADV × 三个月滚动 RPC

    def _dec_bucket(months):
        """一组月份 → (Σ日均收入, Σ日均张数)；任一月任一腿缺值、或合计非正 → None。"""
        v = _rev_m.reindex(months).astype(float)
        q = _vol_m.reindex(months).astype(float)
        if len(v) == 0 or v.isna().any() or q.isna().any():
            return None
        V, Q = float(v.sum()), float(q.sum())
        return (V, Q) if (V > 0 and Q > 0) else None

    # 完整日历年：本桶与基期桶（上一年同 12 个月）都齐才画得出柱；数据允许时取最近 4 个。
    _YTD_Y = LATEST.year
    _dec_bars = []                          # (柱标签, 本期月份, 基期月份)
    for _y in sorted({p.year for p in df.index}):
        if _y >= _YTD_Y:
            continue
        _m1 = pd.period_range(f'{_y}-01', f'{_y}-12', freq='M')
        if _dec_bucket(_m1) and _dec_bucket(_m1 - 12):
            _dec_bars.append((str(_y), list(_m1), list(_m1 - 12)))
    _dec_bars = _dec_bars[-4:]
    if not _dec_bars:
        raise SystemExit(f'Exhibit {EX_DECOMP}：没有任何一个「本年与上一年都齐」的完整'
                         f'日历年，一根柱都画不出来')

    # 当年 YTD：今年 1 月起、两侧（今年该月与去年同月）两条腿都齐的**连续前缀** ——
    # 跳月拼出来的「YTD」两侧月份集合就不再是「1–N 月」。RPC 滞后一个月发布，
    # 所以 YTD 的实际截至月通常比成交量的最新月早一个月，由数据自己决定。
    _ytd1 = []
    for _p in [q for q in df.index if q.year == _YTD_Y]:
        if _dec_bucket([_p]) and _dec_bucket([_p - 12]):
            _ytd1.append(_p)
        else:
            break
    if not _ytd1:
        raise SystemExit(f'Exhibit {EX_DECOMP}：{_YTD_Y} 年没有一个两侧都齐的月份，'
                         f'YTD 柱画不出')
    _ytd_cov = (f'{_ytd1[0].month}–{_ytd1[-1].month} 月' if len(_ytd1) > 1
                else f'{_ytd1[0].month} 月')
    # RPC 滞后 ⇒ 覆盖月份写进 x 标签本身（统一口径的要求：截至月由代码算出，不写死）
    YTD_LAB = f'{_YTD_Y} YTD（{_ytd_cov}）'
    _dec_bars.append((YTD_LAB, _ytd1, [p - 12 for p in _ytd1]))

    _dxl, _dq, _dp, _dnet, _drows, _dblanks = [], [], [], [], [], []
    for _lab, _m1, _m0 in _dec_bars:
        _V1, _Q1 = _dec_bucket(_m1)
        _V0, _Q0 = _dec_bucket(_m0)
        _P1, _P0 = _V1 / _Q1 * 1000.0, _V0 / _Q0 * 1000.0    # $mn/日 ÷ 千张/日 × 1000 = $/张
        _gV, _gQ, _gP = _V1 / _V0 - 1, _Q1 / _Q0 - 1, _P1 / _P0 - 1
        _crs = _gQ * _gP
        _lV = float(np.log(_V1 / _V0))
        _lQ = float(np.log(_Q1 / _Q0))
        _lP = float(np.log(_P1 / _P0))
        # 硬护栏①：算术分解闭合（三项，含交叉项）。残差只应是 float64 舍入（~1e-16）。
        if not abs(_gV - (_gQ + _gP + _crs)) <= DEC_EPS:
            raise SystemExit(f'Exhibit {EX_DECOMP} {_lab} 算术分解不闭合：'
                             f'残差 {_gV - (_gQ + _gP + _crs):+.3e} > {DEC_EPS:.0e}')
        # 硬护栏②：对数分解闭合（本来就该零残差，没有交叉项）。
        if not abs(_lV - (_lQ + _lP)) <= DEC_EPS:
            raise SystemExit(f'Exhibit {EX_DECOMP} {_lab} 对数分解不闭合：'
                             f'残差 {_lV - (_lQ + _lP):+.3e} > {DEC_EPS:.0e}')
        _dxl.append(_lab)
        _row = {'lab': _lab, 'V1': _V1, 'Q1': _Q1, 'P1': _P1,
                'V0': _V0, 'Q0': _Q0, 'P0': _P0,
                'gV': _gV, 'gQ': _gQ, 'gP': _gP, 'cross': _crs,
                'cq': np.nan, 'cp': np.nan}
        if abs(_lV) < DEC_LN_MIN:
            # 整根柱留空：w = g_V/ln(V₁/V₀) 此时是 0/0，算出来的两块没有有效位。
            _dblanks.append(_lab)
            _dq.append(np.nan)
            _dp.append(np.nan)
            _dnet.append(np.nan)
        else:
            _w = _gV / _lV
            _cq, _cp = _w * _lQ * 100, _w * _lP * 100
            # 硬护栏③：**画在图上的那两块**相加 == 总增长。
            if not abs(_gV * 100 - (_cq + _cp)) <= DEC_EPS:
                raise SystemExit(f'Exhibit {EX_DECOMP} {_lab} 重标定后不闭合：'
                                 f'残差 {_gV * 100 - (_cq + _cp):+.3e} > {DEC_EPS:.0e}')
            _row['cq'], _row['cp'] = _cq, _cp
            _dq.append(_cq)
            _dp.append(_cp)
            _dnet.append(_gV * 100)
        _drows.append(_row)

    if not any(np.isfinite(x) for x in _dnet):
        raise SystemExit(f'Exhibit {EX_DECOMP}：{len(_dxl)} 根柱全部落在 |ln(V₁/V₀)| < '
                         f'{DEC_LN_MIN:.0e} 的留空区间，没有一根画得出来')

    # 「算术分解里交叉项占净增长多大」正是不用算术分解的理由，数字现算，不照抄别页
    _x_sh = [abs(r['cross'] / r['gV']) * 100 for r in _drows if r['gV'] != 0]
    if not _x_sh:
        raise SystemExit(f'Exhibit {EX_DECOMP}：所有柱的净增长都恰为零，交叉项占比没有定义')
    CROSS_MED, CROSS_MAX = float(np.median(_x_sh)), float(max(_x_sh))
    _fin_rows = [r for r in _drows if np.isfinite(r['cq'])]
    _lgap = max(abs(r['gQ'] * 100 - r['cq']) for r in _fin_rows)
    _lgap_at = max(_fin_rows, key=lambda r: abs(r['gQ'] * 100 - r['cq']))['lab']

    # 硬护栏④：**写进 payload 的那组数**（round 到 6 位后）也要闭合；留空柱两段必须同空。
    for _i, (_xn, _xq, _xp) in enumerate(zip(L(_dnet), L(_dq), L(_dp))):
        if _xn is None:
            if _xq is not None or _xp is not None:
                raise SystemExit(f'Exhibit {EX_DECOMP} {_dxl[_i]} 净额留空但堆叠段有值 —— '
                                 f'菱形不见了、柱子还在，读者会当成「净额为 0」')
            continue
        if not abs((_xq + _xp) - _xn) <= 2e-6:
            raise SystemExit(f'Exhibit {EX_DECOMP} {_dxl[_i]} 写进 payload 的两块相加 '
                             f'{_xq + _xp:.9f} ≠ 净额 {_xn:.9f}')

    _ytd_row = _drows[-1]
    decomp_check = (f'Exhibit {EX_DECOMP} 量价分解：柱 = {"、".join(_dxl)}；'
                    f'YTD 覆盖 {_YTD_Y} 年 {_ytd_cov}（vs {_YTD_Y - 1} 年同月组，'
                    f'RPC 滞后一个月故截至 {mlab(_ytd1[-1])}，成交量已到 {mlab(LATEST)}）；'
                    f'YTD 日均收入 Σ={_ytd_row["V1"]:.4f} vs {_ytd_row["V0"]:.4f} $mn/日、'
                    f'日均张数 Σ={_ytd_row["Q1"]:,.0f} vs {_ytd_row["Q0"]:,.0f} k/日、'
                    f'RPC ${_ytd_row["P1"]:.4f} vs ${_ytd_row["P0"]:.4f}；'
                    f'三道闭合残差 ≤ {DEC_EPS:.0e} 全过'
                    + (f'；留空柱 {"、".join(_dblanks)}' if _dblanks else ''))

    _last = _drows[-1]
    ex.append({
        'n': EX_DECOMP, 'kind': 'bridge_bar', 'fmt': 'pct1', 'yfmt': 'pct0',
        'xlabels': _dxl, 'xrot': 0,
        'title': 'Implied options revenue growth split by calendar year: contracts vs. RPC '
                 '(a revenue split, NOT a turnover split)',
        'ylab': '% y/y',
        'stacks': [
            {'name': 'Contracts (ADV)', 'color': 'NAVY', 'values': L(_dq)},
            {'name': 'Revenue per contract (RPC)', 'color': 'GOLD', 'values': L(_dp)},
        ],
        'net': {'name': 'Implied revenue growth', 'values': L(_dnet)},
        'net_color': 'INK',
        'src_extra': 'Identity: options transaction revenue = contracts x revenue per contract. '
                     'Both legs are officially disclosed monthly — Cboe is the only name in this '
                     'set where that is true. Log-weight decomposition, one bar = one calendar '
                     'year (last bar = YTD vs. same months a year ago). This decomposes REVENUE, '
                     'not notional turnover',
        'note': (f'<b>这是收入的量费分解，不是成交额的量价分解。</b>恒等式是「隐含期权交易收入 = '
                 f'成交张数 × 每张收入(RPC)」。RPC 是 Cboe 向客户收的<b>每张费用</b>，'
                 f'不是标的资产的成交价格 —— 不要和别的页上真正的「成交额 = 成交量 × 均价」'
                 f'并读。Cboe 是本站清单里唯一把「量」与「每张收入」都按月官方披露的标的，'
                 f'所以这张分解不必假设任何季度费率。'
                 f' <b>美股与欧股那两块做不了</b>：本页的成交<b>金额</b>列是欧洲的'
                 f'（Exhibit 11），成交<b>股数</b>列是美国的（Exhibit 9a），跨法域跨市场，'
                 f'相除得到的「均价」不对应任何真实价格 —— <b>不具备数据条件</b>，本页不做。'
                 f' <b>横轴一格 = 一个完整日历年</b>（该年 12 个月 vs 上一年同 12 个月），'
                 f'共 {len(_dxl) - 1} 格（{_dxl[0]} … {_dxl[-2]}）；末柱 <b>{YTD_LAB}</b> '
                 f'覆盖 {_YTD_Y} 年 <b>{_ytd_cov}</b>（{mlab(_ytd1[0])} – {mlab(_ytd1[-1])}），'
                 f'基期是 {_YTD_Y - 1} 年<b>同一组月份</b> —— 两侧月份集合逐月相同，'
                 f'不是拿 {len(_ytd1)} 个月去比 12 个月。实际截至月是 {mlab(_ytd1[-1])} '
                 f'而不是成交量的最新月 {mlab(LATEST)}：RPC 是三个月滚动平均、'
                 f'<b>滞后一个月发布</b>，YTD 窗口只取张数与 RPC 两条腿在两侧都齐的月份。'
                 f'<b>{_YTD_Y} YTD 柱与完整年柱不可直接比大小</b>（覆盖月数不同）：'
                 f'它回答的是「今年到目前为止 vs 去年同期」，不是「{_YTD_Y} 全年会怎样」。'
                 f' <b>年度桶的聚合</b>：Cboe 不披露每月交易日数，ADV 与收入两列都是日均值，'
                 f'年度桶取月度日均的等权合计；年度 RPC = Σ(当月 ADV × 当月 RPC) ÷ Σ当月 ADV'
                 f'（合计 ÷ 合计），费率不做二次平均 —— 逐月 RPC 的简单平均对每月等权而'
                 f'各月量差着一倍以上，均值之积 ≠ 积之均值，分解会不闭合。'
                 f'RPC 进桶时保持公司披露的三个月滚动口径，不再另做平滑。'
                 f' <b>图上画的是对数分解按总增长重标定后的两块</b>：ln(V₁/V₀) = ln(Q₁/Q₀)'
                 f' + ln(P₁/P₀) 天然可加、无交叉项；再乘 w = g<sub>收入</sub> ÷ ln(V₁/V₀) '
                 f'换算回百分点，深蓝 + 金色<b>逐格等于</b>菱形标的总增长（三道闭合检查残差'
                 f'上限 {DEC_EPS:.0e}，超了本页直接不出图）。w 对量与价一视同仁，'
                 f'不含分配假设。'
                 f' <b>算术分解只进图注</b>：g<sub>收入</sub> = g<sub>张数</sub> + '
                 f'g<sub>RPC</sub> + 交叉项，而交叉项不是可忽略的余项 —— 本窗口实测交叉项'
                 f'占净增长中位 {CROSS_MED:.1f}%、最大 {CROSS_MAX:.0f}%，量价对冲的年份'
                 f'堆叠柱画出来就是错的。{_dxl[-1]} 的算术读数：张数 {pctf(_last["gQ"], 1)}、'
                 f'RPC {pctf(_last["gP"], 1)}、交叉项 {nz(_last["cross"] * 100, 1):+.1f}pp，'
                 f'合计 {pctf(_last["gV"], 1)}；两种口径对「量」贡献的读数最大差 '
                 f'{_lgap:.1f}pp（{_lgap_at}）。'
                 + (f' <b>留空的柱</b>：{"、".join(_dblanks)} 的 |ln(V₁/V₀)| < '
                    f'{DEC_LN_MIN:.0e}（两期几乎持平），重标定权重 w 是 0/0、算出来没有'
                    f'有效位，整根留空而不是印一个假的分解。' if _dblanks else '')
                 + f' <b>RPC 那一块读的是「结构 + 定价」</b>：自有指数期权的 RPC 约为'
                 f'多重挂牌的 {ratio:.0f} 倍（Exhibit 3），所以总量不变、只要 mix 位移'
                 f'（Exhibit 5 / 12），这一段就会动，它不是一个纯粹的价格变量。'),
    })

    # ── Exhibit EX_TABLE：核对表（官方原始单位，不做任何换算）──
    TCOLS = [
        ('U.S. options ADV (k)', 'us', 'adv_us_options_kcontracts', 0, ''),
        ('Index options (k)', 'ix', 'adv_index_options_kcontracts', 0, ''),
        ('SPX (k)', 'spx', 'adv_spx_options_kcontracts', 0, ''),
        ('VIX options (k)', 'vix', 'adv_vix_options_kcontracts', 0, ''),
        ('XSP (k)', 'xsp', 'adv_xsp_options_kcontracts', 0, ''),
        ('Multiply-listed (k)', 'ml', 'adv_multilist_options_kcontracts', 0, ''),
        ('Futures ADV (k)', 'fut', 'adv_futures_kcontracts', 0, ''),
        ('U.S. equities (bn shares)', 'useq', 'adv_us_equities_matched_shares_bn', 2, ''),
        ('EU equities ADNV (EURbn)', 'eueq', 'adv_eu_equities_adnv_eurbn', 2, ''),
        ('Global FX ADNV ($bn)', 'fx', 'adv_fx_adnv_usdbn', 1, ''),
        ('RPC U.S. options ($)', 'rus', 'rpc_us_options_usd', 3, '$'),
        ('RPC index options ($)', 'rix', 'rpc_index_options_usd', 3, '$'),
        ('RPC multiply-listed ($)', 'rml', 'rpc_multilist_options_usd', 3, '$'),
    ]
    trows = []
    for p in W13:
        r = {'xl': mlab(p)}
        for _, key, cname, dec, money in TCOLS:
            v = df[cname].get(p, np.nan)
            r[key] = comma(v, dec, money) if np.isfinite(v) else None
        trows.append(r)
    table = {
        'n': EX_TABLE,
        'title': f'近 {WIN_TABLE} 个月月度指标核对表（官方原始单位，未换算）',
        'idx': '月份',
        'cols': [[c[0], c[1]] for c in TCOLS],
        'rows': trows,
    }

    # ── 抬头与一行数据条 ──
    adv_l = float(df['adv_us_options_mn'].iloc[-1])
    ix_l = float(df['adv_index_options_mn'].iloc[-1])
    sh_l = float(df['index_share'].iloc[-1])
    rpc_l = float(df['rpc_us_options_usd'].loc[LATEST_RPC])
    rev_l = float(df['opt_rev_day_usdmn'].loc[LATEST_RPC])
    fut_l = float(df['adv_futures_kcontracts'].iloc[-1])

    # 抬头一律**同比与环比都写**：只写同比的话，同比在高位、环比在跌的月份会给出一个
    # 纯正面的印象，读者要翻到 Exhibit 1 才知道环比掉了多少（hkex / msci 两页本来就
    # 两个都写，cme / cboe 原来只写同比，同一套页面口径不一致）。
    # Implied 收入与 RPC 同口径月（滞后一期），月份标记不能省 —— 卡片头写的是 LATEST，
    # 不标月份读者会把它当成最新月的数。
    # 抬头是全页曝光最高的一行。2026-08 那一版在这里同时印 TTM 与单月两个口径，理由是
    # 「只放单月、不给对照最容易被读反」；口径改回单月之后那个对照没有了 —— 页面上已经
    # 不存在 TTM 折线，抬头再印一个页面上任何一张图都画不出的 TTM 读数，就是给读者一个
    # 对不上的数。所以这里只留单月，并**逐处标名**「单月」，代价由各图图注与页尾交代。
    headline = (f'美国期权 ADV {adv_l:.1f}mn/日'
                f'（单月 {pctf(yoy(adv_all))} y/y、{pp(mom(adv_all))} m/m）· '
                f'自有指数期权 {ix_l:.1f}mn/日、占比 {sh_l:.0f}% · '
                f'美国期权 RPC {comma(rpc_l, 3, "$")}（{mlab(LATEST_RPC)}，三个月滚动）· '
                f'Implied 期权交易收入 {comma(rev_l, 2, "$")}mn/日（{mlab(LATEST_RPC)}，'
                f'单月 {pctf(yoy(rev_all))} y/y）· '
                f'CFE 期货 ADV {fut_l:,.0f}k/日'
                f'（单月 {pctf(yoy(fut_all))} y/y、{pp(mom(fut_all))} m/m）')
    # 首页卡片把 through_label（=LATEST 月）紧贴这一行渲染，读者会把三个指标一并归到
    # 最新月；RPC 却滞后一期（口径月 = LATEST_RPC）。口径月必须留在卡片上，否则与本页
    # Exhibit 1「最新月 RPC 单元格为空」直接冲突。「三个月滚动」这半句舍在子页 headline
    # 与 notes 里 —— 一并写进来会到 66 字，破 CONTRACT 的 hub_line ≤60 字上限。
    hub_line = (f'美国期权 ADV {adv_l:.1f}mn/日（单月 {pctf(yoy(adv_all))} y/y）· '
                f'指数期权占比 {sh_l:.0f}% · RPC {comma(rpc_l, 3, "$")}'
                + (f'（{mlab(LATEST_RPC)}）' if LATEST_RPC != LATEST else ''))

    # 「图注说画了断点线，图上就必须真有」：本页唯一的结构性断点是 2017 pro-forma，
    # 只有 Exhibit 6 是连续 x 轴、画得出 break_at；Exhibit 12 是热力矩阵，引擎不支持
    # break_at，只能靠文字。这里从 payload 现读「谁真的画了线」，而不是写死编号 ——
    # 源文件哪天回补/裁剪到 2018 起，断点滚出全历史窗口，这段话要跟着消失。
    summary = summary_block(df, LATEST, LATEST - 1, LATEST - 12)
    _blank_why = summary.pop('blank_why')      # 只用来生成表注，不进页面 payload

    # ── 各图横轴的分类：一律现读 payload，不写死图号 ──────────────────────
    # 页尾的「窗口长度」条、断点条、同比口径条都要点名「哪几张图怎么样」。写死名单
    # 正是前三轮反复埋雷的那一步：上一轮窗口条漏了 Exhibit 13（年度桥），而 Exhibit 8
    # 的图注又写着「逐图见页尾窗口条」，读者按指引翻过去恰好找不到左端最扎眼的那张。
    # 所以这里按**横轴的推进单位**分类，下面再用 _win_miss 断言兜底 —— 新增一张图而
    # 没被任何一类接住、窗口条因此没交代到它，构建期直接停机。
    _MO_LABS = {mlab(p) for p in ALL}
    _LAB2P = {mlab(p): p for p in ALL}

    def _axis(e):
        """这张图横轴（热力矩阵则是行）上真正印出来的那一串刻度。"""
        return e.get('rows') or e.get('xlabels') or []

    def _is_month(e):
        a = _axis(e)
        return bool(a) and str(a[0]) in _MO_LABS

    def _left_p(e):
        """横轴左端对应的 Period（按月归一）。月刻度查表、季度刻度解析 'YYYYQn'；
        年度刻度（热力矩阵、年度桥）没有连续横轴，返回 None —— 它们的口径问题由
        文字交代，不参与「跨不跨断点」的判定。"""
        a = _axis(e)
        lab = str(a[0]) if a else ''
        if lab in _LAB2P:
            return _LAB2P[lab].asfreq('M', 'start')
        if re.fullmatch(r'\d{4}Q[1-4]', lab):
            return pd.Period(lab, freq='Q').asfreq('M', 'start')
        return None

    # 「跨断点却有意不画线」的名单现算，不写死图号：判据两条，都在 payload 里 ——
    # 横轴左端早于断点月（它真的跨过去了），且没有 break_at（它真的没画线）。
    # 2026-09 删掉原 Exhibit 14 之后这张名单当前是**空的**（下面那句因此整段不印）；
    # 日后再加一张这样的图，这句会自己把它算进来。
    _span_nobreak = ([str(e['n']) for e in ex
                      if e.get('break_at') is None and _left_p(e) is not None
                      and _left_p(e) < ALL[BREAK_PF].asfreq('M', 'start')]
                     if BREAK_PF else [])

    _brk_drawn = [str(e['n']) for e in ex if e.get('break_at') is not None]
    if _brk_drawn:
        _brk_note = (f'<b>⚠️ 口径断点：{PF_ZH}为 Bats pro-forma combined。</b>'
                     f'Cboe 于 2017-02 完成对 Bats Global Markets 的收购，{PF_ZH}的数字'
                     f'是合并模拟口径，与其后年份不完全可比。红色竖虚线画在 Exhibit '
                     + '、'.join(_brk_drawn) + f'（{mlab(ALL[BREAK_PF])} 的左缘，'
                     f'线左边那段才是异口径的一侧）；'
                     # 「线上怎么没字」要在这里回答一次，否则读者只会当成漏标。
                     # 这几句一个数字都不写死：条数现读 payload，压穿了几处柱值是上一版
                     # 的实测、随窗口与数据变，写进图注只会过期，所以只讲机理。
                     f'这 {len(_brk_drawn)} 条线上都<b>不挂竖排文字标签</b>：那条标签沿'
                     f'虚线从图顶垂下来，与图上的数值标签按构造相交，窗口拉长之后同一条'
                     f'竖带上再没有空档可挪，只会印穿数值（逐柱标数的那几张最严重）；'
                     f'同一个断点在同一页上只能有一种画法，所以一张不挂 —— 它要说的话'
                     f'本条与各图图注都已经说了；'
                     + (f'Exhibit 12 的热力矩阵首行同受影响，但矩阵没有连续横轴、'
                        f'画不出断点线，只能靠图注交代。' if pf_in_heat else '')
                     # 「唯一」现在由 _span_nobreak 的长度说了算，不再手写。名单当前是空的
                     # （原先唯一入选的 TTM 滚动柱已删），所以这一段整个不印 —— 不能替一群
                     # 还不存在的图预写理由，那正是「把一张图的机制安到一群图头上」的走法。
                     + ('' if not _span_nobreak else
                        '<b>Exhibit ' + '、'.join(_span_nobreak) + ' 跨断点却有意不画线</b>'
                        + ('（本页只有这一张）：' if len(_span_nobreak) == 1
                           else f'（本页共 {len(_span_nobreak)} 张）：')
                        + '理由见各该图图注。')
                     + '读长期趋势应从 2018 年起算。')
    else:
        # 断点已滚出所有窗口：不再声称画了线，也不再提它 —— 硬失败退出会让整页永久停更。
        _brk_note = (f'<b>口径断点已滚出所有窗口。</b>{PF_ZH}的 Bats pro-forma combined '
                     f'口径不在当前任何一张图的横轴范围内，故本页不画断点线。')

    # 页尾「窗口长度」那一条要报的期数与左端一律从**已经画好的 payload** 现读，
    # 不另写一份字面量 —— 换一个写死的新数字只是把过期时间往后推一轮。
    _win_full = [str(e['n']) for e in ex
                 if (e.get('xlabels') or [''])[0] == XL25[0]
                 and len(e['xlabels']) == len(W25)]
    # 其余各类同样现读。分完之后 _win_acct 必须盖住每一张图，否则停机（见下）。
    # 全历史那张先摘出去（横轴对象就是 XL_LONG 本身 —— 身份比较，不是值比较：今天 XL25
    # 与 XL_LONG 恰好等长等值，值比较会把满窗口那批全认成「全历史」）。
    _win_hist = [e for e in ex if e.get('xlabels') is XL_LONG]
    _hist_n = {str(e['n']) for e in _win_hist}
    _win_rpc = ([str(e['n']) for e in ex
                 if _is_month(e) and str(e['n']) not in _hist_n
                 and _axis(e)[0] == XL25[0] and len(_axis(e)) == len(W25R)]
                if len(W25R) != len(W25) else [])
    # 左端比窗口**晚**的（序列本身更短，mrwin 只往右让）。判据必须比日期，不能只判
    # 「不等于窗口左端」—— 负例实测：把 series 回补到 2015（2016 那 12 行复制成 2015
    # 前置）之后 Exhibit 6 的左端变成 Jan-15，只判不等于就会把它扫进这一类、印成
    # 「序列本身更短」，而它恰恰是全页最长的那张（139 期 vs 窗口 127 期）。
    _win_late = [e for e in ex if _is_month(e) and str(e['n']) not in _hist_n
                 and _LAB2P[_axis(e)[0]] > _LAB2P[XL25[0]]]
    # 左端比窗口**早**又不是那张全历史的：今天没有，留着是为了下一张这样的图出现时
    # 不会掉进 _win_late 被说反，也不会掉出 _win_acct 让整条注释漏掉它。
    _win_early = [e for e in ex if _is_month(e) and str(e['n']) not in _hist_n
                  and _LAB2P[_axis(e)[0]] < _LAB2P[XL25[0]]]
    _win_qtr = [e for e in ex if e.get('kind') == 'qtr_bar']
    # 年度刻度：热力矩阵按行、年度桥按格，都没有连续的月度横轴，上面那句「统一钉在
    # 左端」对它们根本不适用 —— 上一轮漏的就是这一类，所以连它们真实的范围一起印给
    # 读者（只喂给断言、不印出来，正是 cme 上一版翻车的地方）。
    # 判据必须是**正面的**（每一格都以四位年份打头），不能写成「既不是月也不是季」的
    # 兜底类 —— 那样它会把任何一种新刻度（周、期、事件轴）都吞进来，然后对读者宣称
    # 它「按年推进」，而下面的 _win_miss 断言也就永远不会响。负例实测：往 ex 里塞一张
    # xlabels=['W1','W2'] 的图，兜底版本照常出图（exit=0）、把它印成年度刻度；
    # 改成正面判据后同一个负例停机（见 _win_miss）。
    _YR_WORD = {'heat_matrix': '行', 'bridge_bar': '格'}

    def _is_year(e):
        # 每一格都必须是「四位年份」，后面最多跟一段以空格分隔的说明（末柱那种
        # '2026 YTD（1–6 月）'）。判据写松一点就又变回兜底类：负例实测 —— 用
        # `^\d{4}` 开头匹配时，一张 xlabels=['2026W01','2026W02'] 的周刻度图会被
        # 当成年度刻度收下（exit=0，印成「2026W01 – 2026W02，2 格」），断言不响。
        a = _axis(e)
        return bool(a) and all(re.fullmatch(r'\d{4}( .*)?', str(x)) for x in a)

    _win_yr = [e for e in ex
               if not _is_month(e) and e.get('kind') != 'qtr_bar' and _is_year(e)]
    _win_yr_txt = '、'.join(
        f'Exhibit {e["n"]}（{_axis(e)[0]} – {_axis(e)[-1]}，'
        f'{len(_axis(e))} {_YR_WORD.get(e.get("kind"), "格")}）' for e in _win_yr)
    # 全历史那张今天恰好也满窗口（序列自窗口左端起），所以它写在「满窗口」那句的括号
    # 里；一旦序列回补到更早的月份，它就比窗口长、掉出 _win_full —— 那时括号里那句
    # 「其中…」会指到一个不在前面名单里的图号，且「与满窗口那批一样长」当场为假
    # （负例实测：回补到 2015 后 Exhibit 6 是 139 期、满窗口那批仍是 127 期）。
    # 所以这里判一次「它到底在不在名单里」，两种情形各给各的话。
    _hist_in_full = bool(_win_hist) and all(n in _win_full for n in _hist_n)
    _win_long = _win_hist + _win_early           # 左端比窗口还早的那一类
    _win_long_txt = '、'.join(
        f'Exhibit {e["n"]}（{_axis(e)[0]} – {_axis(e)[-1]}，{len(_axis(e))} 期）'
        for e in _win_long)
    # 「哪几张图的次轴是单月同比」同样现读 payload，不写死图号：判据就在 ylab2 里
    # （'% y/y, single-month' vs 别的）。写死一份图号清单，等哪天某张图的次轴换了口径
    # （或新增一张）就会变成一句当场可证伪的假话 —— 同门的 build/cme.py 正是这么栽的：
    # 那页有一张存量 gs_bar 的次轴不同口径，图注却写了一句「各 gs_bar 都一样」的全称。
    # 判据跟着 ylab2 的字面走：改 ylab2 的人必须同时看这里，否则名单会静默变空。
    _yoy_ex = [str(e['n']) for e in ex
               if e.get('yoy') and 'single-month' in (e.get('ylab2') or '')]
    _yoy_other = [str(e['n']) for e in ex
                  if e.get('yoy') and 'single-month' not in (e.get('ylab2') or '')]
    if not _yoy_ex:
        raise SystemExit('本页没有一张次轴同比图的 ylab2 写着 single-month —— '
                         '要么口径被改回去了、要么 ylab2 的字面变了，而页尾的口径条、'
                         '⟨nav:yoy-axis⟩ 的回填、tools/check_yoy_caliber.py 的 R4 '
                         '全都吃这个字面。先对齐再重跑，不要把这道断言删掉。')
    # 图号一律写成「Exhibit 2、Exhibit 4、…」而不是「Exhibit 2、4、…」：
    # tools/check_yoy_caliber.py 的 R3 用 `(?:Exhibit|Ex\.?)\s*(\d+)` 认「逐处点名」，
    # 顿号后面那几个数字它一个都收不到 —— 缩写形式下页面看着点了名，判据认为没点。
    # 多打几个「Exhibit」换判据能真的读到，值。
    _exs = lambda ns: '、'.join(f'Exhibit {n}' for n in ns)      # noqa: E731

    # ── 兜底：每一张画流量同比的图都必须**自己**印过一段代价（§6.1 第 3 条）──────
    # 判据两侧都现读：左边是 payload 里真有次轴单月同比的图号（`_cost_due`），
    # 右边是 yoy_cal_zh() 登记的账本（`COST_LOG`）。**两个方向都要对**：
    #
    #   · 漏印（该印没印）→ 页尾那句「每一张…都印了」静默变假。这正是 2026-09
    #     之前那一版犯的错（四张图共用一段页级文字，跨图引错了数）。
    #   · 多印（账本里有、payload 里没有那张同比图）→ 页尾那段「逐图代价」小结
    #     `_cost_rows` 是**现读 COST_LOG** 生成的，于是页尾会替一张不存在、
    #     或者已经不画单月同比的图背书，印出一行带图号带数字的代价，而读者会
    #     照着那个图号去找。触发它不需要谁写错代码：把某张图的 `ylab2` 从
    #     'single-month' 改掉（口径换了）、或者图号整体位移一格，`_cost_due`
    #     当场变小而 COST_LOG 还带着旧图号 —— 从前这种情形退出码是 0。
    #
    # 同门的 build/cme.py 早就是两个方向都查的（`_COST_MISSING` / `_COST_EXTRA`）；
    # 本页只查了漏印那一半，2026-09 补齐。两边的判据形状要一样，
    # 否则「cme 会响、cboe 不会响」这件事本身就是下一个人踩的坑。
    _cost_due = set(int(n) for n in _yoy_ex)
    _cost_missing = sorted(_cost_due - set(COST_LOG))
    if _cost_missing:
        raise SystemExit(
            f'这些图画了单月同比却没有逐图代价段：Exhibit {_cost_missing} —— '
            f'CONTRACT §6.1 第 3 条要求每一张画流量同比的图都用**它自己那条序列**'
            f'实测把代价印在图注里，「逐图」是字面意思，页级那段不算数。'
            f'补一句 yoy_cal_zh(图号, 序列, 窗口, 点名)。')
    _cost_extra = sorted(set(COST_LOG) - _cost_due)
    if _cost_extra:
        raise SystemExit(
            f'这些图号进了代价账本却不在「该印代价」的名单里：Exhibit {_cost_extra} '
            f'（本页真有次轴单月同比的是 Exhibit {sorted(_cost_due)}）—— '
            f'账本是页尾那段「逐图代价」小结点名与排序的唯一依据，多一个图号就等于'
            f'替一张不存在、或者已经不画单月同比的图背书，还带着数。'
            f'两种改法：那张图确实还画着单月同比，就把它的 ylab2 改回带 '
            f'single-month 的写法；确实不画了，就把对应那句 yoy_cal_zh() 一起删掉。')
    # 页尾口径条里那张「逐图代价」小结的正文：现读账本，一张一行，不写死图号也不写死数。
    # 它的用途不是顶替逐图那一段（契约明说顶替不了），而是把「四条线毛刺差多少」并排
    # 摆一次 —— 只有并排摆才看得出「拿一条线的数替另一条说话」错得有多离谱。
    _cost_rows = '；'.join(
        f'<b>Exhibit {n}</b>（{v["label"]}）{v["d"]["std_mom"]:.1f}pp／'
        f'最大跳变 {v["d"]["maxjump_mom"][0]:.0f}pp（{v["d"]["maxjump_mom"][2]}）／'
        f'符号相反 {v["d"]["opposite_n"]} 个月'
        f'（{v["d"]["opposite_n"] / v["d"]["n"] * 100:.0f}%，共 {v["d"]["n"]} 个可比月）'
        for n, v in sorted(COST_LOG.items()))
    _cost_sd = {n: v['d']['std_mom'] for n, v in COST_LOG.items()}
    _cost_hi = max(_cost_sd, key=_cost_sd.get)
    _cost_lo = min(_cost_sd, key=_cost_sd.get)
    # CALIB（页尾与汇总表注引用的那一份）声称自己就是 _CAL_EX 那条线的实测。现验：
    # 两边同列同窗口，逐个统计量必须逐位相同，否则那句点名是假的。
    _cal_ref = COST_LOG.get(_CAL_EX, {}).get('d')
    if (_cal_ref is None
            or _cal_ref['n'] != CALIB['n']
            or abs(_cal_ref['std_mom'] - CALIB['sd_m']) > 1e-9
            or _cal_ref['opposite_n'] != CALIB['n_opp']):
        raise SystemExit(
            f'页尾口径条把 CALIB 点名成「Exhibit {_CAL_EX} 那条线」，但两边对不上'
            f'（COST_LOG 有的图号：{sorted(COST_LOG)}）—— 先改点名再改数。')
    _cal_a = (f'（a）{_exs(_yoy_ex)} 的次轴金色折线：单月同比；'
              if not _yoy_other else
              f'（a）{_exs(_yoy_ex)} 的次轴金色折线：单月同比'
              f'（{_exs(_yoy_other)} 也有次轴同比，但不是这个口径，'
              f'以该图图注为准）；')
    # ── 回填跨图导航占位符：占位符是空头支票，这里兑现，兑不出来就停机 ──────
    # （照 build/cme.py 的 `_NAV_*` 那一套。cboe 的 notes 是在 ex 全部建完之后才拼的，
    #  所以只有**图注**里那些提到别的图的句子需要占位符；notes 里直接吃 _yoy_ex。）
    _nav_yoy_txt = f'Exhibit {"、".join(_yoy_ex)} 次轴的单月同比'
    _NAV = {_NAV_YOY_AX: _nav_yoy_txt}
    _nav_used = {k: 0 for k in _NAV}
    for _e in ex:
        if not _e.get('note'):
            continue
        for _k, _v in _NAV.items():
            if _k in _e['note']:
                _nav_used[_k] += 1
                _e['note'] = _e['note'].replace(_k, _v)
    _nav_miss = [k for k, c in _nav_used.items() if not c]
    _nav_left = sorted({str(e['n']) for e in ex for k in _NAV if k in (e.get('note') or '')})
    if _nav_miss or _nav_left:
        raise SystemExit(f'跨图导航句没有兑现：占位符 {_nav_miss} 没有任何图用到，'
                         f'Exhibit {_nav_left} 的图注里还留着没回填的占位符。')
    # 上面那两道只认 _NAV 里**注册过**的占位符。负例实测：往图注里写一个没注册的
    # ⟨nav:whatever⟩，两道全放行、占位符原样进 payload 印给读者（exit=0）。所以写出
    # 之前还要按**模式**再扫一遍整个 payload —— 见 main() 末尾的 _NAV_RE 那道。

    # 「左端被裁短的那几张」逐图报自己的范围，不写死 Exhibit 7 —— 哪天第二条序列也
    # 起得晚，这句会自己把它算进来。
    _win_late_txt = '、'.join(
        f'Exhibit {e["n"]}（{_axis(e)[0]} 起，{len(_axis(e))} 期）' for e in _win_late)
    _win_qtr_txt = '、'.join(
        f'Exhibit {e["n"]}（{_axis(e)[0]} – {_axis(e)[-1]}，{len(_axis(e))} 个季度）'
        for e in _win_qtr)

    # ── 兜底：页尾「窗口长度」条必须把每一张图都归到某一类 ─────────────────
    # 上一轮那条漏了 Exhibit 13，读者按 Exhibit 8 图注的指引翻过去扑空 —— 名单是人肉
    # 维护的，漏一张没有任何东西会响。现在改成：分类没接住的图直接停机。停机比出一页
    # 「看起来逐图交代了、其实少一张」的注释便宜得多，而且下一个人一跑就知道要补哪。
    _win_acct = (set(_win_full) | set(_win_rpc) | _hist_n
                 | {str(e['n']) for e in _win_late + _win_early + _win_qtr + _win_yr})
    _win_miss = [str(e['n']) for e in ex if str(e['n']) not in _win_acct]
    if _win_miss:
        raise SystemExit(
            f'页尾「窗口长度」条没有交代到 Exhibit {"、".join(_win_miss)}：'
            f'这几张图的横轴既不是本页月度窗口、也不是季度或年度刻度中的任何一类。'
            f'先给它们加一类（连同真实范围一起印给读者），再重跑 —— '
            f'不要把断言删掉了事，那正是上一轮漏掉 Exhibit {EX_DECOMP} 的走法。')

    notes = [
        f'<b>数据源与节奏。</b>全部数值来自本仓 <code>series/cboe.csv</code>，'
        f'解析自 Cboe 官网 Monthly volume and revenue per contract (RPC) reports；'
        f'上月数据通常在次月第 3 个工作日发布。当前覆盖 {XL_LONG[0]} – {XL_LONG[-1]}，'
        f'共 {len(ALL)} 个月，逐月连续无缺口（生成脚本会对断月直接抛异常）。',

        f'<b>⚠️ RPC 是三个月滚动平均，且滞后一个月发布。</b>不是单月数。当前成交量已到 '
        f'{mlab(LATEST)}，RPC 只到 {mlab(LATEST_RPC)} —— 汇总表里空白的 RPC 单元格'
        f'（本月一列）不是数据缺口。'
        # 「哪几张图跟着 RPC 短一期」现读 payload（_win_rpc），不写死 3 与 4。
        # 「左端与其余各图相同」也是假的：Exhibit 7 起得晚、年度桥按年推进。真正要说的
        # 只是「与满窗口那批图相同」，那批图号 _win_full 上面已经现读算好了，直接点名。
        f'Exhibit {"、".join(_win_rpc)} 的横轴同样以 {mlab(LATEST_RPC)} '
        f'结尾：<b>左端与满窗口那批图相同</b>（Exhibit {"、".join(_win_full)}，都是 '
        f'{XL25[0]}），只是右端少最新的那一个月，'
        f'所以是 {len(W25R)} 期而不是 {len(W25)} 期'
        f'（{XL25R[0]} – {XL25R[-1]} vs 满窗口那批 {XL25[0]} – {XL25[-1]}）。'
        f'（这句在 2026-08-18 之前写的是「窗口等长、整体前移一个月」—— 那时窗口是'
        f' deck 的「近 {DECK_WIN_LINE} 个月」滚动窗，左端会跟着右端一起前移；'
        f'改成固定左端之后左端不再动，两张图就只是短一期。）',

        _brk_note,

        # ── 同比口径：本页最容易被读反的一条，放在前面 ──
        # 名单走 _yoy_ex（判据在 ylab2 的字面里），不写全称、不写死图号：哪张图的次轴
        # 换了口径，这句会自己少一个号。理由那一句写的是**可核对的事实**（所有者的指令），
        # 不写「看着更灵敏」这类 CONTRACT §6.1 明令禁止的说法；代价用本页序列自己实测。
        f'<b>{_exs(_yoy_ex)} 的次轴同比用<u>单月</u>口径</b>'
        f'（当月 ÷ 去年同月 − 1）<b>，不是 12 个月滚动合计。</b>'
        f'<b>理由：页面所有者要求全站统一成单月口径</b> —— 这是一条指令，不是一条统计结论。'
        f'（本页 2026-08 至 2026-09 之间曾把这几条线画成 12 个月滚动合计同比，现已全部改回；'
        f'页面上因此<b>不再有任何一条滚动同比线</b>。）'
        f'代价必须说清楚：单月同比把「去年那<b>一个</b>月碰巧是什么样」整个塞进分母，'
        f'去年同月若是异常低点，今年一个平淡的月份也能印出三位数增速；后果不只是噪声大一点，'
        f'而是<b>方向会反</b>。'
        f'<b>代价是逐图的，每一张图的图注里印的都是<u>那条线自己</u>的实测</b>'
        f'（CONTRACT §6.1 第 3 条：「逐图」是字面意思，页尾这一段顶替不了）—— '
        f'四条线的毛刺差得很远，所以并排摆一次'
        f'（逐月标准差／相邻月最大跳变／与 12 个月滚动口径符号相反的月份数，'
        f'统计范围都是各图自己画出来的那段窗口；滚动那一侧只作对照，本页一条都不画）：'
        + _cost_rows + '。'
        + f'最毛的是 <b>Exhibit {_cost_hi}</b>（{_cost_sd[_cost_hi]:.1f}pp），'
        f'最稳的是 <b>Exhibit {_cost_lo}</b>（{_cost_sd[_cost_lo]:.1f}pp），'
        f'相差 {_cost_sd[_cost_hi] / _cost_sd[_cost_lo]:.1f} 倍 —— '
        f'<b>不要拿其中一条线的数去读另一条</b>。'
        + (f'（本页 2026-09 之前就是这么错的：四张图共用一段文字，印的全是 '
           f'{_exs([_CAL_EX])} 那条线的数；毛刺最大的 {_exs([_cost_hi])} 的读者因此被告知 '
           f'{CALIB["sd_m"]:.1f}pp / {CALIB["n_opp"]} 个反向月，'
           f'而它自己那条线是 {_cost_sd[_cost_hi]:.1f}pp / '
           f'{COST_LOG[_cost_hi]["d"]["opposite_n"]} 个。）'
           if _cost_hi != _CAL_EX else '')
        + (('Exhibit 2 那条线最近几个方向相反的月份：' + '、'.join(
            f'{p}（单月 {r["m"]:+.1f}%／滚动 {r["r"]:+.1f}%）'
            for p, r in CALIB['opp'].tail(3).iterrows()) + '。')
           if CALIB['n_opp'] else '')
        + f'读任何一条金色折线时请记住它自己那个数：<b>光是挑月份就能把结论说成两个方向</b>。'
        f'第一个有值的点要等 12 个月（要有去年同月当分母），所以窗口左端头 12 个月没有折线，'
        f'那不是缺数。基数为 0 或两期异号的月份留空，不硬算一个几百个百分点的假同比。'
        f'<b>不乘交易日数</b>：Cboe 的月度披露里没有交易日数这一列，本页也不去别处凑一个。'
        f'本页所有源列本来就是<b>日均</b>（ADV / ADNV / 收入每日），交易日数在「日均」里'
        f'已经除掉了，所以这条单月同比比的是两个日均数，<b>不含</b>「这个月比去年同月多几个'
        f'交易日」那部分效应 —— 它的毛刺来自基期那一个月本身的高低，不来自日历。'
        f'反过来，也正因为没有交易日数，本页拿不出「当月合计张数」这个口径。',

        f'<b>本页有三种同比口径，已逐处点名，不要跨口径比高低。</b>'
        f'三者的差别是<b>期长</b>（一个月 / 一个季度 / 一个日历年），不是同一段时间的两种算法：'
        f'{_cal_a}'
        f'（b）Exhibit 8 的绿线：本季 3 个月 vs 上年同季（柱是季度的，线只能与柱同期）；'
        f'（c）Exhibit {EX_DECOMP}：日历年合计同比 —— 整年 12 个月 vs 上一年同 12 个月，'
        f'末柱为当年 YTD（{_YTD_Y} 年 {_ytd_cov}）vs 去年<b>同一组月份</b>，一格 = 一年，'
        f'不要拿 YTD 柱去比完整年柱（覆盖月数不同）。'
        f'汇总表（Exhibit 1）的 y/y 列、顶部抬头与「本月读数怎么读」一段里标「单月」的读数、'
        f'以及各图图注括号里的同比读数，<b>全部与（a）的金色折线同口径</b>（单月），'
        f'可以逐格对上 —— 这是本轮改口径的直接结果：改之前汇总表是单月、折线是滚动，'
        f'同一页的表和线对同一件事给的是两个数。',

        # 删图必须在页面上交代，否则读者只会看到图号从 12 跳到 13 再到 14 而不知道发生了什么。
        # 「为什么柱也得跟着换」这一步不能含糊：所有者的指令说的是折线，柱是被那条线牵着走的
        # —— 12 个月均值的单月同比逐点等于 12 个月滚动合计同比（实测差 2e-14，除以 12 是
        # 同一个常数），所以那条金线在新口径下无路可走，柱与线同源这个唯一卖点跟着塌。
        # 数字是拿改口径前那一版 data/cboe.js 里两张图的柱逐点复算的一次性实测（历史事实，
        # 不随数据变）：同样经 L() 的 round(…, 6) 之后 127 期逐点全等；未舍入的重算值对
        # payload 里已舍入的数最大差 5e-7（Apr-24 那一期），那 5e-7 就是那一次舍入本身。
        f'<b>原 Exhibit 14（U.S. options volume, trailing 12-month average）已删。</b>'
        f'那张图的柱是「截至该月的近 12 个月平均 ADV」，金线是这些柱自己的同比 —— 而'
        f'「12 个月均值的同比」逐点就等于 12 个月滚动合计同比（除以 12 是同一个常数）。'
        f'所以全页改单月口径之后，那条金线只剩两条路：留在已经停画的滚动口径上，'
        f'或者换成当月序列的单月同比、从此与自己的柱<b>不同源</b> —— 而柱与线同源'
        f'正是那张图当初存在的唯一理由。两条都保住的做法只有一个：把柱也换成<b>当月</b>值。'
        f'一换，它就与 Exhibit 2 完全重合：同一列源数据'
        f'（<code>adv_us_options_kcontracts</code> ÷ 1,000）、同一个窗口（{XL25[0]} – '
        f'{XL25[-1]}，{len(W25)} 期）、同一个单位（百万张/日）、同一条单月同比金线。'
        f'复算（把原 Exhibit 14 的柱按当月值重算一遍，与改口径前那一版 payload 里 '
        f'Exhibit 2 的柱逐点相比）：两边都过一遍写出前的 round 到 6 位小数之后，'
        f'{len(W25)} 期<b>逐点全等、最大差 0</b>；拿未舍入的重算值直接对 payload 里已舍入的'
        f'数，最大差也只有 5×10⁻⁷（Apr-24），那就是那一次舍入本身 —— 不是「相似」，'
        f'是同一张图。'
        f'本页<b>没有交易日数这一列</b>，所以拿不出「当月合计张数」这个能把两张图分开的口径'
        f'（cme 那边可以，靠乘当月交易日数把日均还原成月度合计；cboe 不披露交易日数）。'
        f'同一份数据在同一页上画两次不是信息，所以删掉而不是重画；'
        f'末尾核对表的编号因此由 15 收回 {EX_TABLE}，图号 2 – {EX_DECOMP} 一个都没动。',

        f'<b>Exhibit {EX_DECOMP} 分的是收入，不是成交额；本页做不了成交额的量价分解。</b>'
        f'恒等式「期权交易收入 = 成交张数 × 每张收入(RPC)」两边都是公司按月官方披露的，'
        f'所以这张分解做得成 —— 但 RPC 是交易所向客户收的<b>每张费用</b>，不是标的资产的'
        f'成交价格，不能与别的页上真正的「成交额 = 成交量 × 均价」并读。'
        f'而真正的量价分解在本页<b>不具备数据条件</b>：cboe.csv 里的成交<b>金额</b>列是'
        f'欧洲的（欧股 ADNV，EUR bn/日），成交<b>股数</b>列是美国的（美股撮合，bn 股/日），'
        f'两者分属不同法域、不同市场、不同货币，相除得到的「均价」不对应任何真实价格，'
        f'方向与大小都不可知而图上完全看不出来 —— 宁可不做。'
        f'横轴是「{len(_dxl) - 1} 个完整日历年 + 当年 YTD」（与全站其余 decomp 同口径）：'
        f'整年 12 个月对'
        f'上一年同 12 个月；YTD 柱对去年<b>同一组月份</b>（{_YTD_Y} 年 {_ytd_cov}，'
        f'RPC 滞后一个月发布，实际截至月由数据算出写在柱标签上），两侧月份集合逐月相同，'
        f'且 YTD 柱与完整年柱不可直接比大小。年度 RPC = Σ(当月 ADV × 当月 RPC) ÷ '
        f'Σ当月 ADV，费率不做二次平均。'
        f'分解本身是恒等式而非估算：图上两块相加逐格等于总增长，生成脚本对算术闭合、'
        f'对数闭合、重标定闭合三道检查都设了 1e-9 的硬门槛，超了直接退出、不出图。'
        f'图上画对数分解按总增长重标定后的两块（w = g<sub>收入</sub> ÷ ln(V₁/V₀)，'
        f'纵轴回到 %），算术分解只进图注 —— 算术版必须把交叉项整段压进 RPC 那一块，'
        f'本页实测交叉项占净增长中位 {CROSS_MED:.1f}%、最大 {CROSS_MAX:.0f}%。',

        '<b>Implied options transaction revenue（Exhibit 4）是推导值，不是披露值。</b>'
        '= 当月美国期权 ADV × 同月三个月滚动 RPC ÷ 1,000（$mn/日）。Cboe 是本站清单里'
        '唯一官方同时按月披露「量」与「单位价格」的标的，因此不必像其他券商那样假设一个'
        '季度费率；代价是 RPC 已被三个月平滑，本图的月度波动主要来自量而非价，'
        # notes 走 innerHTML，markdown 的 ** ** 不会被渲染，只会原样印出四个星号
        '且它是<b>每日</b>净交易收入的估算，要得到月度总额还需再乘当月交易日数。',

        f'<b>Mix 比总量更值钱。</b>自有指数期权（SPX / VIX / XSP）的 RPC 约为多重挂牌期权的 '
        f'{ratio:.0f} 倍（{mlab(LATEST_RPC)}：{comma(rpc_ix[-1], 3, "$")} vs '
        f'{comma(rpc_ml[-1], 3, "$")}），所以 Exhibit 5 的占比线与 Exhibit 12 的热力矩阵'
        f'对收入的解释力大于 Exhibit 2 的总量。',

        '<b>Exhibit 9 已拆开。</b>原 deck 把美股撮合（十亿股/日）、欧股 ADNV（EUR bn/日）、'
        f'全球外汇 ADNV（$bn/日）三条线画在同一根轴上，窗口内的均值量级是 {_no_mag}，'
        f'最小的那条（美股撮合）的极差只占画布的 {_no_flat:.1f}%'
        f'（三条同轴、0 起、上界取三条的最大值）、完全贴在零线上，等于白画。'
        f'三种量纲本来就不该同轴，也不能靠截轴救'
        '（截轴的前提是主体在轴内、个别点出界，这里是整条 FX 序列会全部出界），所以拆成 '
        f'Exhibit 9a（美股撮合）与 9b（全球外汇）各自成轴；第三条欧股 ADNV 与 Exhibit 11 '
        f'是同一条序列、同一个 {len(W25)} 个月窗口，不再重画一张。窗口、线型、数值一概未改。',

        '<b>Exhibit 8 的季度柱是月度 ADV 的均值，不是合计。</b>ADV 本身已经是「每日平均」'
        '口径，把三个月加起来没有意义。末季未满 3 个月时该柱会变浅蓝并在图例标出，'
        '同时右轴 y/y 的最后一点由图表引擎强制作废（拿不满 3 个月的均值去比上年完整的 '
        '3 个月，季内月份构成不一样，必然砸出假坑）——<b>那一季的图注也一并不报同比</b>，'
        '页面不能一边声明这个数无效、一边把它印出来。',

        '<b>与原 PDF deck 的四处有意差异（都只影响画法，不影响数值）。</b>'
        '(1) Exhibit 7 原 deck 用对数轴把 SPX / VIX / XSP 三条量级差很大的线拉开，'
        '网页图表引擎只有线性轴，XSP 与 VIX 在图上被压扁 —— 要读它们自己的走势请点右上角「表格」。'
        f'该图的纵轴已改为从 0 起：合约张数不可能为负，而线图的默认下界会掉到 '
        f'−{abs(_e7_floor):,.0f} 千张/日（约占画布 {_e7_waste:.0f}%）。'
        '(2) Exhibit 6 原 deck 在末 3 个月画了一个红色虚线椭圆，网页版没有这个元件，'
        '改在图注里点名最近 3 个月的读数；纵轴与 deck 一样从 0 起、末点标数值。'
        f'(3) Exhibit 7 的纵轴单位由「百万张/日」改为「千张/日」：百万张口径下 XSP 只剩'
        f'「{xsp[-1] / 1000:.2f}」两位有效数字，而三条线共用一个格式器。数值本身不变（× 1,000）。'
        'Exhibit 3 曾因同样理由改成美分，引擎补上 3 位小数格式器后已换回原 deck 的「美元/张」。'
        '(4) Exhibit 9 拆成 9a/9b（见上一条）。'
        '除此之外图的顺序、编号与标题均照搬原 deck。'
        '<b>窗口长度与图注不是</b>：窗口是本页对 deck 最大的一处偏离，单列在下一条；'
        '图注是网页版重写的 —— deck 的要点保留，另加本页在构建期现算的实测数'
        '（期数、px 预算、同比口径的标准差与跳变等），deck 里没有这些。',

        # ⚠️ 这一条是 2026-08-19 补的。在此之前页尾唯一提到窗口的地方是上一条那句
        #    「窗口长度……均照搬原 deck」，而窗口早在 2026-08-18 就不照搬了 ——
        #    全页唯一一处对读者做「窗口照搬 deck」承诺的句子，恰好是唯一一句假话。
        #    对照组是 build/cme.py：那页有专门的「与原 PDF 版的有意差异」把窗口写清楚了。
        #    各图的期数一律现算，不写死 —— 写死只是把过期时间往后推一轮。
        f'<b>窗口长度与原 PDF deck 有意不同（本页最大的一处偏离）。</b>'
        f'deck 的时序图是「近 {DECK_WIN_LINE} 个月」，堆叠占比图与季度柱另有自己的 '
        f'{DECK_WIN_STACK} 个月 / {DECK_WIN_QTR} 个季度窗口。本页把<b>月度时序图的窗口'
        f'左端统一钉在 {XL25[0]}</b>（{XL25[0]} – {XL25[-1]}，{len(W25)} 期；序列本身更短的'
        f'只往右让、不往左借，所以「统一」说的是窗口不是每一张图的实际左端）。'
        f'下面把<b>每一张图</b>归到一类，一张不漏（漏一张构建期就停机）：'
        f'满窗口的是 Exhibit {"、".join(_win_full)}'
        # 全历史那张：在名单里就写进括号，不在（序列已回补到窗口左端以左）就单列一类，
        # 连它真实的范围一起印出来 —— 两种情形都不许出现「其中 X」而 X 不在名单里。
        + (f'（其中 Exhibit {"、".join(sorted(_hist_n))} 画的是全历史 —— 本页序列恰好自 '
           f'{XL_LONG[0]} 起、与窗口左端同月，所以它与满窗口那批一样长）'
           if _hist_in_full else '')
        + (f'；比窗口左端还往左的是 {_win_long_txt} —— 画的是全历史，本页序列自 '
           f'{XL_LONG[0]} 起，早于窗口左端 {XL25[0]}'
           if _win_long and not _hist_in_full else '')
        + (f'；Exhibit {"、".join(_win_rpc)} 同一个左端、右端早一个月'
           f'（{len(W25R)} 期，理由见上面第 2 条）' if _win_rpc else '')
        + (f'；{_win_late_txt}的左端由 <code>build/mrwin.py</code> 按「线都已经有值」'
           f'裁决，不是窗口不同而是序列本身更短' if _win_late else '')
        + (f'；{_win_qtr_txt}是季度刻度，同一个左端换算到季度'
           f'（deck 是末 {DECK_WIN_QTR} 个季度）' if _win_qtr else '')
        # 年度刻度那一类上一轮整个漏掉了（热力矩阵只提了一句「仍是 10 年」，年度桥
        # 一个字都没有），而 Exhibit 8 的图注还写着「逐图见页尾窗口条」。现在按 kind
        # 现算，连各自真实的范围一起印出来。
        + (f'；按年推进、上面那句左端对它们不适用的是 {_win_yr_txt}' if _win_yr else '')
        + f'；末尾核对表 {WIN_TABLE} 行（表是拿着逐行核对的，{len(ALL)} 行没人对得完）。'
        f'放宽的理由是数据一直都在：series/cboe.csv 自 {XL_LONG[0]} 起 {len(ALL)} 期'
        f'逐月连续无缺口，deck 那三个窗口都是<b>画的时候截的</b>，不是数据下限。'
        # 这里的 13 是 build/CONTRACT.md §5.4 的**逐字引文**，故意写成字面量：它是那份
        # 文件里的数，与本页的 DECK_WIN_STACK / WIN_TABLE 只是碰巧同值。拿本页的常量去
        # 渲染别人文件里的引文，就是 Exhibit 5 那个 WIN_TABLE 串味 bug 换了个地方 ——
        # 契约哪天改成 15，这句会照旧引 13（引文本来就该跟着契约走，不跟着我们走）。
        f'契约 <code>build/CONTRACT.md</code> §5.4 的原文是「近期图<b>固定</b> 13 个月」'
        f'—— 本页是<b>有意不照它办</b>，不是把「固定」读成了'
        f'「至少」；该条该不该改由那份契约的持有者裁决，本页不动它，只在这里把冲突写明。'
        f'代价是 {len(W25)} 期塞不进半栏卡片：哪几张升通栏、x 轴标签隔几期标一个，'
        f'由 <code>build/mrwin.py</code> 按 <code>assets/charts.js</code> 的量边距算式在'
        f'构建期算出来，各图图注里写着实测的 px 数。'
        f'另一处代价是断点：窗口一放宽，好几张图就跨过了{PF_ZH}那段 Bats pro-forma，'
        f'现在画着红色竖虚线的是 Exhibit {"、".join(_brk_drawn)}，详见上面的口径断点条。',

        f'<b>柱图的单月次轴同比（Exhibit {"、".join(_yoy_ex)}；'
        f'Exhibit 8 的季度绿线是另一档，见上面「本页有三种同比口径」那条）。</b>'
        '这些图画的是同比折线而不是 12 个月滚动均线（均线只是把柱子再平滑一遍、不带新信息），'
        '这一点与原 deck 一致；<b>口径也与 deck 相同</b> —— 两边都是<b>单月</b>同比。'
        '（2026-08 至 2026-09 之间本页曾改画 12 个月滚动合计同比，现按所有者要求改回，'
        '理由与代价实测见上面的同比口径条。）'
        '基数近零或两期异号时该点留空，不硬算一个几百个百分点的假同比。'
        '双轴图的规矩是两轴零点画在同一高度，代价过大时引擎改为两轴独立缩放并在图内注明 —— '
        '本页 Exhibit 10 命中这一条，读它的柱与线时不要按同一条零线对齐。',

        '<b>汇总表读法。</b>「3Y %ile」= 当月读数在最近 36 个月里高于多少比例的观测'
        '（≥66 绿、≤33 红），由全站统一的 <code>build/pctile.py</code> 计算：'
        '把这一行的分位在近 24 个月里逐月回放，若 ≥70% 的月份都钉在 100 或 0，'
        '说明这一列对该指标没有区分度，留空。'
        + (('本月留空的行：' + '；'.join(f'{lab}（{why}）' for lab, why in _blank_why) + '。')
           if _blank_why else '本月没有留空的行。')
        + '<b>本表的 y/y 是单月同比</b>（本月 ÷ 去年同月 − 1），'
        f'与 Exhibit {"、".join(_yoy_ex)} 次轴金色折线<b>同口径、可逐格对上</b> —— '
        '本表三列写死的就是「本月 / 上月 / 去年同月」这三个具名月份，放一个滚动值进去'
        '与列头自相矛盾，而现在整页的月度同比都是这个口径，不再需要在表和线之间换算。'
        f'单月同比有多毛，上面的同比口径条已把四条线<b>逐图</b>的实测并排印出来'
        f'（毛刺最大的 {_exs([_cost_hi])}：{_cost_sd[_cost_hi]:.1f}pp、'
        f'{COST_LOG[_cost_hi]["d"]["n"]} 个可比月里 '
        f'{COST_LOG[_cost_hi]["d"]["opposite_n"]} 个月与滚动口径符号相反；'
        f'最稳的 {_exs([_cost_lo])} 是 {_cost_sd[_cost_lo]:.1f}pp）'
        f'——<b>本表与那些折线一样，'
        f'回答的是「本月相对上月与去年同月的水平」，不是趋势</b>；'
        f'要判趋势请横着看整条折线，不要只读末点。'
        'm/m 与 y/y 对分母为 0 或两期异号的情形留空。'
        f'末尾核对表（Exhibit {EX_TABLE}）保持官方原始单位'
        '（k 张/日、bn 股/日、EUR bn/日、$bn/日、$/张），'
        '不做任何换算，便于与公司披露逐条对账；列数较多，在窄屏上需要左右滚动。',
    ]

    # 127 点的图放不进半栏卡片 —— 逐张按 charts.js 的量边距算式判通栏与抽稀。
    mrwin.layout_all(ex)

    payload = {
        'ticker': 'cboe',
        'tracker': 'Cboe Monthly Volume & RPC Tracker',
        'title': f'Cboe Global Markets (CBOE)：月度成交量与 RPC 跟踪 — '
                 f'{LATEST.year} 年 {LATEST.month} 月',
        'data_through': str(LATEST),
        'through_label': f'{LATEST.year} 年 {LATEST.month} 月',
        'subtitle': f'数据源：Cboe 官网 Monthly volume and revenue per contract (RPC) reports'
                    f'（次月第 3 个工作日）· 覆盖 {XL_LONG[0]} – {XL_LONG[-1]}（{len(ALL)} 个月）'
                    f'· 版式沿用 Goldman Sachs GIR monthly-metrics note · 只出图，不带观点',
        'headline': headline,
        # headline 之下、Exhibit 1 之上的 ~300 字解读。职责与 headline 互补：
        # 那一行给读数，这一段给「读数该怎么读」。见 compose_brief 的 docstring。
        # i0 传 BREAK_PF（首个非 pro-forma 月），与 Exhibit 6 的断点虚线同一个下标 ——
        # 排名的分母不能混进 2017 年的 Bats pro-forma combined 口径。
        # ALL 在本文件里是 pandas Period 的列表，brief.py 的月份口径是 'YYYY-MM' 字符串
        # （`B.mo()` 直接切片），所以在边界上转一次，不让 Period 漏进规则库。
        'brief': compose_brief(
            [str(p) for p in ALL], BREAK_PF or 0,
            df['adv_us_options_kcontracts'].values.astype(float),
            df['adv_index_options_kcontracts'].values.astype(float),
            df['rpc_us_options_usd'].values.astype(float),
            df['rpc_index_options_usd'].values.astype(float),
            df['rpc_multilist_options_usd'].values.astype(float),
            [(nm, df[c].values.astype(float)) for nm, c in BRIEF_LINES]),
        # 名词释义：排在所有 exhibit 之前。选词判断与「有意不收哪些词」写在
        # compose_glossary() 上面那块注释里；三个结构性量在那里现算，一个都不写死。
        'glossary': gloss.render(compose_glossary(df), where='cboe glossary'),
        'hub_line': hub_line,
        'source': SRC,
        'xlabels': XL13,
        'xlabels_long': XL_LONG,
        'summary': summary,
        'exhibits': ex,
        'table': table,
        'notes': notes,
        'footer': 'Cboe Global Markets (CBOE) · monthly volume and RPC reports · '
                  'charts only, no commentary · 个人研究用，不构成投资建议',
    }
    # 表注只说这张表里的数说得着的事。原来这里还有一句「2017 figures are Bats pro-forma
    # combined」—— 本表只有本月/上月/去年同月三列 + 36 个月分位，窗口最早也只到 2023，
    # 2017 的口径与表里任何一个数都无关，那句话留着只会让人以为表里混了 pro-forma 数。
    payload['summary']['note'] = (
        f'Volume through {mlab(LATEST)}; RPC through {mlab(LATEST_RPC)} — RPC is a three-month '
        f'rolling average published on a one-month lag, so blank RPC cells are not a data gap. '
        f'3Y %ile = 当月读数在最近 36 个月中的分位（口径见下方「汇总表读法」）。'
    )

    # 抬头右侧「官方发布于 X」。台账按月钉死（fetch 入库时从 xlsx 的 "Updated on …" 记下），
    # 所以只查 LATEST 这一个月：cache/ 里可能躺着比 LATEST 更新的一期，现解析会把新一期的
    # 发布日安到旧月份的数据上。查不到就**整个字段不写** —— 渲染端判的是字段在不在，
    # 给它 None 或空串会印出一句没有内容的断言。
    src_day = _source_dates().lookup(os.path.join(ROOT, 'series'), 'cboe', str(LATEST))
    if src_day:
        payload['source_date'] = src_day

    # 写出前按**模式**扫一遍整个 payload：任何 ⟨nav:…⟩ 都不许活着走到读者面前。
    # 上面那道只认注册过的 key，写一个没注册的占位符它会放行（实测 exit=0、占位符
    # 原样印在图注里）。这一道不认名字只认形状，所以新占位符忘了注册也逃不掉。
    _NAV_RE = re.compile(r'⟨nav:[^⟩]*⟩')
    _nav_raw = sorted(set(_NAV_RE.findall(json.dumps(payload, ensure_ascii=False))))
    if _nav_raw:
        raise SystemExit(f'payload 里还留着没回填的跨图导航占位符：{_nav_raw}。'
                         f'把它注册进 _NAV 并给出现读 payload 的回填文案，不要直接删占位符'
                         f'——占位符在那里就是因为那句话讲的是别的图。')

    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(OUT, payload, 'cboe')

    print(f'数据 {ALL[0]} → {LATEST}（{len(ALL)} 个月）；RPC 至 {LATEST_RPC}')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）'
          f' + Exhibit {table["n"]} 核对表')
    print(f'写出 {OUT}  ({os.path.getsize(OUT) / 1024:.1f} KB)')
    print(decomp_check)
    print(headline)


if __name__ == '__main__':
    main()
