# -*- coding: utf-8 -*-
"""月度营收看板的**通用底座** —— 一家一份 `mrspecs/<ticker>.py`，底座不认得任何一家。

    python3 mrbase.py tsm
    python3 mrbase.py --all

产物与既有 `data/<t>.js` 同构（`assets/page.js` + `assets/charts.js` 渲染），
图列复刻 `build/tsm.py` 的十张：

    Ex1  汇总表（月营收 / 3MMA / QTD / YTD / 占 TTM 比重，可选分部行）
    Ex2  gs_bar          月营收柱 + 右轴 12 个月滚动合计同比
    Ex3  qtr_bar         月度聚合到季（当季未满月份浅色）
    Ex4  gs_line         环比 m/m
    Ex5  lines_endlabels 本币同比 vs 美元同比（单月口径）  【需 fx + 页上有美元腿】
    Ex6  grouped_bars    汇率对报表增速的贡献（之差，pp）  【需 fx + 页上有美元腿】
    Ex7  lines           全历史（可叠分部）
    Ex8  lines           月均汇率                                【只需 fx】
    Ex9  heat_matrix     逐年 × 逐月热力（口径见 `window.heat_metric`）
    Ex10 核对表          近 N 个月，官方原始单位未换算

**编号是算出来的，不是写死的**：画不出来的图整体跳过，后面的图**顺次前移**，
页内所有互指（图注里的「见 Exhibit X」）都走 `EX[slug]` 查表，不会指到不存在的图。

━━ Ex8 与 Ex5/Ex6 要的**不是同一件事**，不许捆在一起跳（§1.5）━━━━━━━━━━━
Ex8 画的是**汇率本身**（`ds.fx`）—— 一条宏观序列，挂了同一份汇率的每一页上逐点相同，
不需要公司披露任何东西。Ex5/Ex6 画的是**这家公司的美元营收**，那需要公司真有官方
美元数；没有就只能拿本币 ÷ 外部牌价折一条分析师构造值出来冒充官方值，所以那两张该跳。
⇒ 「有汇率线、没有美元腿」的家，正确写法是 `fx` 照给 +
`skip: ['fx_lines', 'fx_contrib']`（附 `skip_note` 理由），Ex8 照出。

⚠️ 由此而来的硬规矩：**页上任何一处关于「美元营收 / 汇率贡献」的措辞、数字、表列，
判据一律是 `usd_leg_shown(EX)`（那两张图在不在），不是 `ds.fx is not None`。**
本文件里曾有七处写成后者（brief 的 s1 峰值扫描与 s4 恒等句、页尾的两条汇率说明与
数据源一条、核对表的 Implied 列、抬头的「美元口径 y/y」），在只出 Ex8 的家上会
`KeyError: 'fx_contrib'`，或印出一个页面根本没画、也没有官方数可核的推导值。

━━ 现状：迁上来的只有 TSM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`build/mrspecs/` 下现在只有 `tsm.py`，`build/tsm.py` 是指向本底座的薄壳。
另外六家（联电 / 联发科 / 日月光 / 南亚科 / 世芯 / 创意）目前仍由
`build/single.py` + `build/specs/<t>.py` 生成，那套图列带 `decomp` / `ttm_yoy` /
`seasonality` 等本底座**不产出**的图 —— **「两套图列谁赢」是产品决定，不是构建决定**，
所以本底座默认拒绝往 `data/<t>.js` 写这六家（`owned_elsewhere()`，判据是文件在不在）。
六家的 spec 已在本轮验证过写得出来（scratch 里 `--all` 七家全建得出、三道闸门全过），
接管时把 spec 放进 `mrspecs/`、给每家留一个同样的 `build/<t>.py` 薄壳即可。

━━ 铁律（docs/SINGLE_SPEC.md §0）━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
本文件里**没有、也不许有 `if ticker == 'xxx'`**。任何一家的差异只有两个去处：
写进它自己的 spec（字段能表达的部分），或者由 spec 提供一个 callable 钩子
（`brief_extra`，字段表达不了的部分）。想往这里加分支之前先想想：
「删掉某一家还能不能只删三个文件」。

━━ 为什么另起炉灶而不是原地改 build/tsm.py ━━━━━━━━━━━━━━━━━━━━━━━━━
那 1130 行里 TSMC 专属的事实被写成了**散文常量**，而不是数据：

  · `'Roughly 70% of TSMC revenue is US-dollar denominated…'`（:875 英文、:1046 中文）
    —— 对另外六家全部是**事实错误陈述**，而且各家的官方表述逐家不同、不可继承。
    本底座把它做成 `fx.usd_share_note`（per-ticker + 出处），**缺了就硬失败**。
  · `'TSMC 月营收自 2016-01 起口径连续，未发生并表或重述'` —— 那半句在 UMC（2019-10
    USJC 并表、2015-06 新事业退出合并）等至少四家上是假话。本底座的断点段落**整段**
    由 payload + spec 生成：没有断点时只写「本页 spec 未登记断点」这个**中性事实**，
    并明说它不等于「历史上没发生过并表或重述」—— 后者是关于公司历史的事实断言，
    只有 spec 给了 `continuity={'zh', 'url'}`（带得住的出处）时才印，
    给不出出处就整个不说。**收回一句无源断言不是信息损失。**
  · 主序列写死 `revenue_ntd_mn ÷ 1000 → NT$bn`、写死「新台币可加总」——
    世芯（3661）的功能货币是美元，NT$ 列是逐月折算值，十二个月相加与官方本年累计
    差 +0.378%（美元列差 0.000000%）。本底座把「主序列取哪一列、哪一列不可加总」
    做成 `value` / `alt` 两个字段，`alt.summable=False` 的列**在结构上进不了**
    季度桥、YTD、TTM 与滚动同比。

━━ 口径规矩（build/CONTRACT.md）━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  · 同比只有一处实现：`build/yoy.py`。本文件不写 `pct_change(12)`。
  · 一页并存两种同比：Ex2 右轴是 **12 个月滚动合计**（营收是流量、可加总）；
    其余（Ex3 / Ex5 / Ex6 / Ex9、两张表、brief）是**单月**同比。
    §6 要求单月同比写进标题，Ex5 / Ex6 的标题里都有「单月 / single-month」。
  · 图注里的数一个都不写死，构建期现算；读不到源退回定性版本，不抛异常。

━━ 时间窗与数据边界（本轮的核心）━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`window.x_from` 给的是**页面希望的**短窗口起点（本轮 TSM 用 '2016-01'）。
每张图**实际**能从哪一格起画，由它自己的派生口径决定，底座逐图现算：

    图         派生量            需要的历史        实际首点
    Ex2 柱     月营收            0                 x_from
    Ex2 右轴   12M 滚动合计同比  24 个月           x_from + 23
    Ex3 柱     季度合计          0                 x_from 所在季
    Ex3 右轴   季度同比          4 个季            +4 季
    Ex4        环比              1 个月            x_from + 1
    Ex5/Ex6    单月同比          12 个月           x_from + 12
    Ex6 右轴   贡献的同比(pp 差) 24 个月           x_from + 23

处理方式**分两类，由图型的 null 容忍度决定**（docs/CHART_KINDS.md §1.2），
不是随口选的：

  · `gs_line` / `lines_endlabels` 走 Catmull-Rom 平滑，`null` 会被 JS 当 0，
    画出一条**塌到零的假线**，首尾为 null 还直接抛 TypeError 让整页后续图全丢。
    ⇒ 这两种图型（Ex4 / Ex5）**显式截断**到首个有值点，窗口比 x_from 短多少写进图注。
  · `gs_bar.yoy` / `qtr_bar.line` / `grouped_bars.line` 走非平滑 polyline，
    前导 null 只是「笔还没落下」，不画假值。
    ⇒ 这几处（Ex2 / Ex3 / Ex6 的右轴）**保留 null**，让派生线自己晚起，
    并在图注里现算出「线比柱短几个月、为什么」。

**不许**的第三条路（既没做也不会做）：往前补零、补去年同值、或把首点拉平。

窗口一长（TSM 2016 起 = 127 个月）就会撞上引擎的值相关排版冲突：半栏卡片上
band 掉到 3.6px，逐点数值标签的首点有一半宽度伸进左轴刻度栏。对策不在本文件里 ——
`build/mrwin.py` 按 `build/chartscale.py` 的几何模型在构建期复算 band 与标签预算，
决定 `full` 与 `xstep`，并把实测数交回来写进图注。`build/CONTRACT.md` 的 `full`
字段那一行原文就是「127 根柱塞进半栏每根不到 3px，必须通栏」，所以这一步是照章办事，
不是版式偏好。
"""
import argparse
import datetime
import importlib
import os
import sys

import numpy as np
import pandas as pd

# 下面这批是仓库既有的公共零件，一个都不重新实现。
import axisfmt
import brief as B
import chartscale
import mrwin                       # 窗口左端与排版的裁决层（可单测：python3 build/mrwin.py）
import payload_guard
import pctile
import yoy as Y

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == 'build' else HERE
SERIES = os.path.join(ROOT, 'series')
DATA = os.path.join(ROOT, 'data')

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

ALIGN_WASTE_MAX = 0.38      # 与 assets/charts.js 的 ALIGN_WASTE_MAX 同值

# ── 窗口左端与排版（通栏 / x 标签抽稀）的**规则不在本文件**，在 build/mrwin.py。
#    那个文件里没有一句图注文案、没有任何一家的知识，并且可以单独跑自检
#    （`python3 build/mrwin.py`，对着 6 类已知错例 11 项）。本文件只负责
#    「把腿喂给它」和「把它算出来的实测数写进图注」。
#
#    图型的 null 容忍度（docs/CHART_KINDS.md §1.2）同样住在那边：`mrwin.DENSE`
#    与 build/verify_pages.py:61 的 DENSE 集合逐字相同 —— 本文件不再存第二份副本，
#    要判「这个 kind 吃不吃得了 null」请直接问 `mrwin.DENSE`。


class SpecError(Exception):
    """配置写错了。**硬失败**：拼错的字段被静默忽略比报错危险得多。"""


# ══════════════════════════════════════════════════════════════════════════════
# 小工具（与 build/tsm.py / build/gsx.py 同名同义，行为逐字相同）
# ══════════════════════════════════════════════════════════════════════════════
def mlab(p):
    return p.strftime('%b-%y')


def num(v, nd=6):
    """写进 payload 的数值：非有限一律 None，有限的统一定点舍入，保证幂等。"""
    if v is None:
        return None
    fv = float(v)
    if not np.isfinite(fv):
        return None
    return round(fv, nd)


def L(seq, nd=6):
    return [num(v, nd) for v in seq]


def f(v, dec=1, pct=False, money=''):
    if v is None or not np.isfinite(float(v)):
        return '—'
    s = f'{float(v):,.{dec}f}'
    return (money + s + '%') if pct else (money + s)


def sgn(v, dec=1, suffix='%'):
    if v is None or not np.isfinite(float(v)):
        return '—'
    return f'{float(v):+,.{dec}f}{suffix}'


_MD_B = None


def md2b(s):
    """`**…**` → `<b>…</b>`。图注走 innerHTML，Markdown 的星号会原样印在页面上。

    与 build/single.py 的同名处理同义（docs/SINGLE_SPEC.md 的 `notes` 一行写明底座会换）。
    本文件的图注是长中文，作者顺手写 `**` 的概率是 100%，所以在**写出前**统一过一遍，
    而不是指望每一处都记得写 <b>。换了几处会在跑的时候打印出来。
    """
    global _MD_B
    import re as _re
    if _MD_B is None:
        _MD_B = _re.compile(r'\*\*(.+?)\*\*', _re.S)
    if not isinstance(s, str) or '**' not in s:
        return s, 0
    n = len(_MD_B.findall(s))
    return _MD_B.sub(r'<b>\1</b>', s), n


def md2b_deep(obj, counter):
    """递归把 payload 里所有字符串过一遍 md2b（只有图注/说明会命中）。"""
    if isinstance(obj, str):
        t, n = md2b(obj)
        counter[0] += n
        return t
    if isinstance(obj, list):
        return [md2b_deep(x, counter) for x in obj]
    if isinstance(obj, dict):
        return {k: md2b_deep(v, counter) for k, v in obj.items()}
    return obj


def align_sim(ex):
    """复算引擎「两轴零点画在同一高度」之后，左轴与浪费掉的画布比例。

    ⚠️ 本函数与 `build/tsm.py` / `build/axp.py` 里的同名函数逐字相同 —— 它该住在
    `build/axisfmt.py` 里供全站共用，但那个文件本轮不归本任务改，所以先各放一份，
    注释互相点名以免日后只改一处。
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
    fr = max(axisfmt._zero_frac(y0, y1), axisfmt._zero_frac(r0, r1))
    if fr <= 1e-9:
        return {'lo': y0, 'hi': y1, 'alo': y0, 'ahi': y1, 'waste': 0.0, 'aligned': False}
    la0, la1 = axisfmt._align_zero(y0, y1, fr)
    ra0, ra1 = axisfmt._align_zero(r0, r1, fr)
    w1 = 1 - (y1 - y0) / (la1 - la0) if (la1 - la0) else float('nan')
    w2 = 1 - (r1 - r0) / (ra1 - ra0) if (ra1 - ra0) else float('nan')
    waste = max(w1, w2)
    ok = not (waste > ALIGN_WASTE_MAX)
    return {'lo': la0 if ok else y0, 'hi': la1 if ok else y1,
            'alo': la0, 'ahi': la1, 'waste': waste, 'aligned': ok}


def source_date(ticker, month):
    """该月营收公告的官方发布日；查不到返回 None（不算构建失败）。"""
    try:
        import importlib.util
        sp = importlib.util.spec_from_file_location(
            'source_dates', os.path.join(ROOT, 'source_dates.py'))
        mod = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(mod)
        return mod.lookup(SERIES, ticker, month)
    except Exception as e:
        print(f'[{ticker}][warn] 读 series/source_dates.csv 失败，本次不写 source_date：{e!r}')
        return None


# ══════════════════════════════════════════════════════════════════════════════
# §1 配置契约
# ══════════════════════════════════════════════════════════════════════════════
#   顶层字段。写了未知字段 → SpecError（拼错的字段被静默忽略比报错危险得多）。
_TOP = {
    # ── 身份 ──────────────────────────────────────────────────────────────
    'ticker',        # ✓ str  = 目录名 = data 文件名 = payload.ticker
    'name',          # ✓ str  英文短名（tracker 行、页脚）
    'title',         # ✓ str  页面大标题，底座自动接「 — YYYY 年 M 月」
    'tracker',       # ✓ str  抬头那行 tracker 名
    'source',        # ✓ str  图脚 Source: 行，全页共用
    'source_zh',     # ✓ str  副标题里的中文数据源短句
    'csv',           # ✓ str  series/ 下的主表文件名

    # ── 主序列 ────────────────────────────────────────────────────────────
    'value',         # ✓ dict 见 _VALUE：主序列取哪一列、怎么显示、可不可加总
    'alt',           #   dict 只用于核对表与页尾说明的第二计价列（世芯的 NT$）
    'official_yoy',  #   str  公司随公告给出的同比列名（有就用它喂热力矩阵与核对表）
    'segments',      #   list 分部列（日月光的 ATM / 非 ATM，创意的 turnkey / NRE）

    # ── 汇率腿（没有就整体跳过 Ex5 / Ex6 / Ex8）───────────────────────────
    'fx',            #   dict 见 _FX

    # ── 窗口与规模 ────────────────────────────────────────────────────────
    'window',        # ✓ dict 见 _WINDOW

    # ── 口径断点 ──────────────────────────────────────────────────────────
    'breaks',        #   list|str 断点字面量，或 series/ 下一张断点表的文件名
    'continuity',    #   dict {'zh', 'url'} 「本页口径连续」这句**事实断言**及其出处。
                     #        不给 = 页面只说「没有登记断点」这个中性事实，不做断言。

    # ── 跳过某张图（必须同时给理由）───────────────────────────────────────
    'skip',          #   list[str] slug；每个 slug 必须在 skip_note 里有一句理由
    'skip_note',     #   dict slug -> 理由（进页尾说明）

    # ── 可选钩子与自定义文案 ──────────────────────────────────────────────
    'guidance',      #   dict 指引桥的源表；只有能填满六列的家才有
    'brief_extra',   #   callable(ctx) -> str  brief 的第 5 句（字段表达不了的部分）
    'notes',         #   list[str] 追加到页尾说明末尾
    'note_extra',    #   dict slug -> str 追加到**那一张图自己的图注**末尾。
                     #        页尾说明是全页共用的，可「这张图的主序列为什么取这一列」
                     #        「这张图上的红线只对哪条线成立」是**逐图**的口径判断，
                     #        读者是在那张图底下问的，答案就该在那张图底下。
                     #        键必须是 _SLUGS 里的 slug，写错在 validate 里硬失败。
    'format_source', # ✓ str 版式出处
    'footer',        #   str
}

_VALUE = {'col', 'div', 'label', 'sym', 'dec', 'raw_label', 'raw_dec', 'summable',
          'zh', 'ccy_zh', 'unit'}
_ALT = {'col', 'label', 'dec', 'summable', 'zh', 'note_zh'}
_FX = {'csv', 'col', 'quote', 'src', 'usd_share_note', 'assumption', 'usd_label',
       # ── 「本币腿 ≠ 主序列」的家（功能货币不是本币，如 KY 股）──────────────
       # 底座原本假设：主序列就是本币腿，外币腿 = 主序列 ÷ 汇率。
       # 功能货币是美元的家把这个假设倒过来了：**可加总的主序列是美元**
       # （本币栏是逐月折算值，十二个月相加 ≠ 官方本年累计，不能当 value），
       # 而本币腿是**另外一列**。不区分这两者的话，`rev / fx` 会算出
       # 「美元 ÷（本币/美元）」这种没有指称的量 —— 量级正常、正负号也对，
       # 图上看不出毛病，正是最危险的一类错（世芯实测：与真值最大差 48.5pp）。
       'local_col',    # str 本币腿所在列。不给 = 本币腿就是 value（既有行为）
       'local_label',  # str 本币腿的英文线名（Ex5 的 NAVY 线）
       'local_zh',     # str 本币腿的中文短名
       'local_sym',    # str 本币腿的货币符号（Ex5 标题与 Ex6 的 src_extra）
       'implied',      # bool 非主序列的那条腿是不是**我们折出来的**。
                       #      默认 True（如 TSM：美元线是本币 ÷ 外部牌价的推导值）。
                       #      给 False = 两条腿都是官方申报值，页面不再印「推导值(Implied)」。
       }
_WINDOW = {'x_from', 'heat_years', 'check_rows',
           # 'heat_metric' —— Ex9 的格里画哪一个量（§1.6）：
           #   'yoy'（默认，单月同比）/ 'mom'（环比）/ 'log_yoy'（100×ln(1+y/y)）。
           #   ⚠️ 这是 **mrbase 的一个字段，不是 assets/charts.js 的改动**：引擎一格不动。
           #   加它的理由见 §1.6 —— 引擎的线性色阶限制属实，但「那就整张跳过」不成立，
           #   本仓对同类情况的既定做法是「照出 + 加告诫」。
           'heat_metric'}
_SEG = {'col', 'zh', 'label'}


def _chk(d, allowed, what):
    if not isinstance(d, dict):
        raise SpecError(f'{what} 必须是 dict，拿到 {type(d).__name__}')
    bad = set(d) - allowed
    if bad:
        raise SpecError(f'{what} 有未知字段 {sorted(bad)}；允许的是 {sorted(allowed)}')


def validate(spec):
    _chk(spec, _TOP, 'SPEC')
    for k in ('ticker', 'name', 'title', 'tracker', 'source', 'source_zh', 'csv',
              'value', 'window', 'format_source'):
        if not spec.get(k):
            raise SpecError(f'SPEC 缺必填字段 {k!r}')
    t = spec['ticker']
    if not t.replace('-', '').isalnum() or t != t.lower():
        raise SpecError(f'ticker {t!r} 只许小写字母/数字/连字符')

    _chk(spec['value'], _VALUE, 'SPEC[value]')
    for k in ('col', 'div', 'label', 'sym', 'raw_label'):
        if spec['value'].get(k) is None:
            raise SpecError(f'SPEC[value] 缺 {k!r}')
    if spec['value'].get('summable') is not True:
        # 世芯的教训：主序列若不可加总，季度桥 / YTD / TTM / 滚动同比全部非法。
        # 这不是「打个标记继续画」的事，是**换一列**。
        raise SpecError(
            'SPEC[value].summable 必须显式为 True —— 主序列要过季度合计、YTD、'
            '12 个月滚动同比三道加总。若该列不可加总（如功能货币非本币时的折算列，'
            '世芯 3661 的 NT$ 列十二个月相加与官方本年累计差 +0.378%），'
            '请把可加总的那一列设为 value，把折算列放进 alt（alt.summable=False）。')

    if spec.get('alt'):
        _chk(spec['alt'], _ALT, 'SPEC[alt]')
        if spec['alt'].get('summable') is not False:
            raise SpecError('SPEC[alt].summable 必须显式为 False —— alt 只进核对表，'
                            '不参与任何加总；若它可加总，它就该是 value。')
    for s in spec.get('segments') or []:
        _chk(s, _SEG, 'SPEC[segments][]')

    if spec.get('fx'):
        _chk(spec['fx'], _FX, 'SPEC[fx]')
        for k in ('csv', 'col', 'quote', 'src'):
            if not spec['fx'].get(k):
                raise SpecError(f'SPEC[fx] 缺 {k!r}')
        u = spec['fx'].get('usd_share_note')
        if not isinstance(u, dict) or not all(u.get(k) for k in ('en', 'zh', 'src')):
            raise SpecError(
                'SPEC[fx].usd_share_note 必填，且要有 en / zh / src 三键。'
                '「本币计价但外币结算」的官方表述**逐家不同、不可继承** —— '
                'build/tsm.py 把 "Roughly 70% of TSMC revenue is US-dollar denominated" '
                '写死在 :875 与 :1046 两处，那句话搬到另外六家全是事实错误陈述。'
                'src 请写能核对的出处（官方年报/20-F 章节 + URL）。')
        if 'http' not in str(u['src']):
            # 只要求「非空串」等于只要求作者写了点什么。这一句是**带百分比的事实断言**，
            # 会随每年 20-F 变，读者要能自己去核 —— 没有 URL 就核不动。
            raise SpecError(
                'SPEC[fx].usd_share_note.src 里没有 URL。这句话是一条带数字的事实断言'
                '（「约七成营收以美元计价」这类），必须给出**可点开复核**的出处；'
                '给不出出处就把措辞改成不带数字的定性版本，别在页上留一个没人能核的百分比。')

    _chk(spec['window'], _WINDOW, 'SPEC[window]')
    hm = spec['window'].get('heat_metric', _HEAT_DEFAULT)
    if hm not in _HEAT_TXT:
        # 拼错了**不许**静默退回默认：退回之后页面画的是同比、spec 作者以为是环比，
        # 而两张矩阵长得一模一样（同样 9×12 的格子），肉眼分不出来。
        raise SpecError(
            f'SPEC[window].heat_metric = {hm!r} 不认得；可选 '
            f'{sorted(_HEAT_TXT)}（不给 = {_HEAT_DEFAULT!r}）。'
            '换口径是**口径判断**：标题、图注、页尾的口径点名条都由底座跟着改，'
            '不要在 spec 里另写一份说法（两份说法迟早对不上）。')
    if 'x_from' not in spec['window']:
        # 显式 None 是合法的（= 用序列自己的起点）；**没写**才是漏了。
        # 这两者必须分开：这一轮有实现把六家的柱图悄悄砍到 2016-01，而它们的数据
        # 自 2013/2014 就有、副标题还写着「覆盖 Jan-13 … 共 163 个月」——
        # 那是没被要求也没被声明的口径收窄，页面自相矛盾。
        raise SpecError('SPEC[window] 缺 x_from。要短窗口就给月份串（如 "2016-01"）；'
                        '要用序列自己的起点就<b>显式写 None</b> —— '
                        '「用全序列」是一个决定，不该由「忘了写」来表达。')

    c = spec.get('continuity')
    if c is not None:
        if not isinstance(c, dict) or not all(c.get(k) for k in ('zh', 'url')) \
                or 'http' not in str(c['url']):
            raise SpecError(
                'SPEC[continuity] 要么不给，要么给 {"zh": …, "url": …} 且 url 是真出处。'
                '「本页月营收口径连续、未发生并表或重述」是一句**关于历史的事实断言**，'
                '不是「我没登记断点」的同义反复 —— 前者需要出处（年报合并范围附注、'
                '公司重述公告），后者只是本页 spec 的状态。'
                '给不出出处就整个不给：底座会只陈述后者，并明说两者不是一回事。')

    sk = set(spec.get('skip') or [])
    unknown = sk - set(_SLUGS)
    if unknown:
        raise SpecError(f'SPEC[skip] 有未知 slug {sorted(unknown)}；可选 {_SLUGS}')
    notes = spec.get('skip_note') or {}
    missing = sk - set(notes)
    if missing:
        raise SpecError(f'SPEC[skip] 里的 {sorted(missing)} 没有 skip_note 理由。'
                        '跳一张图是**口径判断**，必须留下能被复核的理由，'
                        '否则下一个人只看见「这家怎么少一张图」。')

    ne = spec.get('note_extra') or {}
    if not isinstance(ne, dict):
        raise SpecError('SPEC[note_extra] 必须是 dict：slug -> 追加到该图图注末尾的字符串。')
    bad = set(ne) - set(_SLUGS)
    if bad:
        # 拼错的 slug 静默丢掉 = 一段本该出现在图注上的口径说明凭空消失，
        # 而页面看上去完全正常。这类「少一句话」的错只能靠硬失败暴露。
        raise SpecError(f'SPEC[note_extra] 有未知 slug {sorted(bad)}；可选 {_SLUGS}')
    return spec


# 图的 slug（= 稳定标识）。编号 n 是**算出来的**，slug 才是页内互指的键。
_SLUGS = ['rev_bar', 'qtr', 'mom', 'fx_lines', 'fx_contrib', 'hist', 'fx_rate', 'heat']


# ══════════════════════════════════════════════════════════════════════════════
# §1.5 汇率的**两个**判据 —— 全文件唯一入口，别再写 `ds.fx is not None`
# ══════════════════════════════════════════════════════════════════════════════
# 本轮之前，「有 fx 序列」与「页上有美元腿」被当成同一件事，于是七处代码共用一个
# `ds.fx is not None`。它们其实是两件不同的事：
#
#   · **fx 序列**（`_FX_SLUGS`）—— series/*.csv 里那条 NTD/USD。它是一条**宏观**序列，
#     谁挂上它都是逐点相同的同一条线，不需要任何一家公司披露任何东西。
#     Ex8（`fx_rate`，汇率线本身）画的就是它。
#   · **美元腿**（`_USD_SLUGS`）—— 本币 ÷ 汇率折出来的那条**公司**序列。没有官方美元
#     实绩的家，这条线是分析师构造值：不许上图（Ex5/Ex6）、不许进 brief 的恒等式句、
#     不许进抬头、不许进核对表。
#
# 判据一律**看 EX 里有没有那张图**，不看 ds.fx：
#   · 看 ds.fx，「挂了 fx 但 skip 掉 Ex5/Ex6」的家会在 `R('fx_contrib')` 上 KeyError
#     （页尾两处），或印出一条页上根本不存在、也没有官方数可对账的美元线；
#   · 看 EX，则「哪几张图出不出」这个决定只有一份，跳图与没有 fx 两条路自动同解。
_USD_SLUGS = ('fx_lines', 'fx_contrib')                 # 要「本币 ÷ 汇率」这条构造腿
_FX_SLUGS = ('fx_lines', 'fx_contrib', 'fx_rate')       # 要 fx 序列（含只画汇率线本身）


def usd_leg_shown(EX):
    """页上是否真的出现了美元（外币）腿。**所有关于美元营收的话都问它。**"""
    return any(s in EX for s in _USD_SLUGS)


def fx_used(EX):
    """fx 序列是否在页上被用到（只画 Ex8 汇率线本身的家也算）。"""
    return any(s in EX for s in _FX_SLUGS)


# ══════════════════════════════════════════════════════════════════════════════
# §1.6 热力矩阵的口径（`window.heat_metric`）
# ══════════════════════════════════════════════════════════════════════════════
# 引擎的限制属实：`assets/charts.js` 的 `heatScale()` 只读 `matrix` / `reverse` 两个
# 入口，色标是**线性**的（t =（v − p5）/（p95 − p5），红→白→绿），而且**色阶与格内数字
# 读同一份 matrix** —— 「色阶取对数、格内印原值」在结构上做不到。
#
# 但「那就整张跳过」不成立。本仓对同类情况的既定做法是**照出 + 加告诫**
# （mrspecs/mtk.py 就是这么处理它 38% 拥挤度的：矩阵照出，图注写「请按格内数字读，
# 不要只看颜色排序」）。跳掉的是一整张按年 × 按月的季节性视图，而它读不出来的原因不在
# 图型上，在**喂给它的那个量**上：换一个在 t 轴上摊得开的口径，同一张图就活了。
#
# 三个口径都合法，各自回答不同的问题：
#   'yoy'      单月同比（%）      —— 默认。命题是「今年这个月 vs 去年这个月」。
#   'mom'      环比（%）          —— 命题是「季节性与转折点」。它同样是「一格 = 一个月的
#                                   读数」，没有违背 heat_matrix 的本性（CONTRACT §6.2
#                                   豁免该图型走滚动口径，正是因为这一点）。
#   'log_yoy'  同比的对数增速     —— **仍然是单月同比**，只是把倍数关系压成等距：
#              100×ln(1+g)         +69 ≈ 翻倍、−69 ≈ 腰斩，涨十倍与跌九成在色轴上对称。
#
# 选哪一个**不靠感觉**：`heat_crowding()` 拿实际进 payload 的那张 matrix 现算「最宽 20%
# 色带里塞了几格」，三个口径各算一遍，数直接写进图注（构建期现算，不写死）。
_HEAT_DEFAULT = 'yoy'


def heat_values(ds, metric):
    """metric → 喂进矩阵的那条序列。三条都由已有派生量出，本函数不新写口径。"""
    if metric == 'mom':
        return ds.mom
    if metric == 'log_yoy':
        # 100 × ln(1 + g)。g ≤ −100% 时无定义 —— 营收非负，只有分子为 0 才碰得到，
        # 那种月份留 NaN（= 空格），不许钳到一个假值上（−inf 会毒掉整条色阶）。
        r = 1.0 + ds.yoy.astype(float) / 100.0
        return np.log(r.where(r > 0)) * 100.0
    return ds.yoy


def heat_matrix_of(series, years):
    """(matrix, rows) —— 建矩阵**只有这一段代码**，口径对照现算也复用它。

    `|v| < 0.5` 的格子统一写成正零：`toFixed(0)` 会把 −0.1 印成「-0」，在一整片两位
    整数里那是个纯格式化产物，读者会停下来判断它是不是缺失值。
    """
    sv = series.dropna()
    if not len(sv):
        return [], []
    yrs = sorted({p.year for p in sv.index})[-int(years):]
    mat = []
    for y in yrs:
        row = [None] * 12
        for p, x in sv.items():
            if p.year == y:
                fv = float(x)
                row[p.month - 1] = num(0.0 if abs(fv) < 0.5 else fv, 4)
        mat.append(row)
    return mat, yrs


def heat_crowding(matrix):
    """把 `assets/charts.js` 的 `heatScale()` 在构建期复算一遍，量这张矩阵摊不摊得开。

    ⚠️ **必须拿实际进 payload 的那张 `matrix` 算，不能拿全序列算。** 引擎的 5/95 分位
    只看 `ex.matrix`（`heat_years` 截出来的那几年 × 12 列）。拿全序列算出来的分位与
    拥挤格数**不是引擎会得到的那一组数** —— 图注里引一个引擎算不出来的分位，读者照着
    去核会对不上，而页面看上去一切正常。

    返回 None（有限格 < 8，算不出可信分位）或
    `{n, lo, hi, p5, p95, dull, share}`：`dull` = 最宽 20% 色带里最多塞了几格。
    判据的依据：色标线性 ⇒ 两格的色差 ≈ 它们 t 值之差；t 差不到 0.20 就是「色差不到
    两成、肉眼分不开」。超出 p5/p95 的格子在引擎里钳到端点色，所以这里也钳。
    """
    fin = sorted(float(v) for row in matrix for v in row
                 if v is not None and np.isfinite(float(v)))
    n = len(fin)
    if n < 8:
        return None

    def q(p):
        k = (n - 1) * p
        lo, hi = int(k), min(int(k) + 1, n - 1)
        return fin[lo] + (fin[hi] - fin[lo]) * (k - lo)

    p5, p95 = q(0.05), q(0.95)
    span = (p95 - p5) or 1.0
    ts = sorted(min(max((v - p5) / span, 0.0), 1.0) for v in fin)
    best, j = 0, 0
    for i in range(n):
        while ts[i] - ts[j] > 0.20:
            j += 1
        best = max(best, i - j + 1)
    return {'n': n, 'lo': fin[0], 'hi': fin[-1], 'p5': p5, 'p95': p95,
            'dull': best, 'share': best / n * 100.0}


# 三个口径各自的措辞。**标题里的口径声明在这里，不在调用处** —— CONTRACT §6 第 2 条
# 要求单月同比写进标题，把这句话和「取哪条序列」放在同一张表里，换口径时不可能只改一半
# （图画了环比、标题还写着单月同比，那是最难发现的一类错）。
#
# `is_yoy` 回答的是「这张矩阵算不算单月同比」，页尾的同比口径点名条与 Ex2 图注的
# 「单月同比仍在页内可读：…」都用它判 —— 判据是**那张矩阵画的是不是单月同比**，
# 不是「页上有没有矩阵」。log_yoy 是同比的单调变换，仍然算；mom 不算。
_HEAT_TXT = {
    'yoy': {
        'title': 'Monthly revenue y/y growth (%)（单月同比 / single-month）',
        'legend': 'Revenue y/y (%)',
        'unit': '%',
        'zh': '单月同比',
        'zero': '|y/y| 不足 0.5pp',
        'is_yoy': True,
        'named_extra': '',
        'src_en': ('Green = faster y/y growth, red = slower; blanks are months not '
                   'yet reported. 色标取全部有限值的 5/95 分位。'),
        'caliber': '',                      # 默认口径不必为自己辩护
    },
    'mom': {
        'title': 'Monthly revenue m/m change (%)（环比 / month-on-month）',
        'legend': 'Revenue m/m (%)',
        'unit': '%',
        'zh': '环比（当月 ÷ 上月 − 1）',
        'zero': '|m/m| 不足 0.5pp',
        'is_yoy': False,
        'named_extra': '',
        'src_en': ('Green = a stronger month than the one before, red = weaker; '
                   'blanks are months not yet reported. 色标取全部有限值的 5/95 分位。'),
        'caliber': (
            '<b>本表是环比，不是同比 —— 这是本页唯一一处换过口径的地方。</b>'
            '换口径不改变这张图的本性：一格仍然是一个月的读数，按年 × 按月排布仍然读的是'
            '季节性与转折点（CONTRACT §6.2 豁免 <code>heat_matrix</code> 走滚动口径，'
            '正是因为「每一格就是一个月的读数」是它的题眼）。换掉的只是这个读数取哪一种'
            '增速。<b>代价要说清楚</b>：环比读不出「比去年同月好还是坏」，那个问题请看'
            '核对表的 y/y 列与汇总表的 y/y 行；而环比自己带着日历效应（2 月天数少、'
            '农历年错位），不做季节调整，同一列（同一个月份）上下逐年对读才是它的正确'
            '用法。'),
    },
    'log_yoy': {
        'title': ('Monthly revenue y/y growth, log scale — 100 × ln(1 + y/y)'
                  '（单月同比 / single-month）'),
        'legend': 'Revenue y/y, log (100 × ln(1+g))',
        'unit': ' 对数点',
        'zh': '单月同比的对数增速 100×ln(1+y/y)',
        'zero': '|100×ln(1+y/y)| 不足 0.5',
        'is_yoy': True,
        'named_extra': '（格内取 100×ln(1+y/y)，仍是单月同比，只是压成等距）',
        'src_en': ('Cells are 100 × ln(1 + y/y), not per-cent; green = faster, '
                   'red = slower; blanks are months not yet reported. '
                   '色标取全部有限值的 5/95 分位。'),
        'caliber': (
            '<b>格内不是百分比，是对数增速</b> 100×ln(1+y/y)（单位「对数点」）：'
            '<b>+69 ≈ 翻倍、−69 ≈ 腰斩</b>，+900%（涨十倍）印成 +230、'
            '−90%（跌九成）印成 −230，两者在色轴上对称。口径仍然是<b>单月同比</b>，'
            '只是把倍数关系压成等距 —— 这是一个<b>单调变换</b>，正负号与逐格排序与'
            '百分比口径完全一致，换回百分比不会改变任何一格的方向。'
            '<b>代价</b>：格内数字不能当百分比读，要百分比请看核对表的 y/y 列'
            '（那一列是原值，未做变换）。'),
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# §2 读数据
# ══════════════════════════════════════════════════════════════════════════════
class DataSet(object):
    """一家的全部序列。加载期做的三件检查与 build/tsm.py 的 load() 同义。"""

    def __init__(self, spec):
        t = spec['ticker']
        df = pd.read_csv(os.path.join(SERIES, spec['csv']))
        need = [spec['value']['col']]
        if spec.get('official_yoy'):
            need.append(spec['official_yoy'])
        if spec.get('alt'):
            need.append(spec['alt']['col'])
        need += [s['col'] for s in (spec.get('segments') or [])]
        if (spec.get('fx') or {}).get('local_col'):
            need.append(spec['fx']['local_col'])
        if 'month' not in df.columns:
            raise SpecError(f'series/{spec["csv"]} 缺列 month')
        for c in need:
            if c not in df.columns:
                raise SpecError(f'series/{spec["csv"]} 缺列 {c}')
        df['month'] = pd.PeriodIndex(df['month'], freq='M')
        df = df.set_index('month').sort_index()
        if df.index.has_duplicates:
            raise SpecError(f'series/{spec["csv"]} 有重复月份')
        gaps = [(df.index[i] - df.index[i - 1]).n for i in range(1, len(df))]
        if any(g != 1 for g in gaps):
            bad = [str(df.index[i]) for i in range(1, len(df))
                   if (df.index[i] - df.index[i - 1]).n != 1]
            # 断档会让相隔数月的柱画成相邻柱（假时间轴），比缺数更糟。
            raise SpecError(f'series/{spec["csv"]} 月份不连续，断在 {bad}')

        self.spec = spec
        self.df = df
        self.rev = df[spec['value']['col']].astype(float)
        self.all = list(self.rev.index)
        self.official_yoy = (df[spec['official_yoy']].astype(float)
                             if spec.get('official_yoy') else None)
        self.alt = df[spec['alt']['col']].astype(float) if spec.get('alt') else None
        self.segments = [(s, df[s['col']].astype(float)) for s in (spec.get('segments') or [])]

        # ── 汇率腿。**没有就是没有**：不拿本币 ÷ 外部牌价造一条美元线冒充官方值。
        self.fx = None
        if spec.get('fx'):
            fx = pd.read_csv(os.path.join(SERIES, spec['fx']['csv']))
            fx['month'] = pd.PeriodIndex(fx['month'], freq='M')
            fx = fx.set_index('month').sort_index()[spec['fx']['col']].astype(float)
            self.fx_raw = fx
            al = fx.reindex(self.rev.index)
            if al.isna().any():
                miss = [str(p) for p in al.index[al.isna()]]
                raise SpecError(f'series/{spec["fx"]["csv"]} 缺月份 {miss}')
            self.fx = al

        # ── 派生。全部走 build/yoy.py，本文件不写 pct_change(12)。营收是流量。
        v = spec['value']
        self.disp = self.rev / float(v['div'])                     # 显示口径（如 NT$bn）
        self.ma3 = self.rev.rolling(3).mean() / float(v['div'])
        self.ytd = self.rev.groupby(self.rev.index.year).cumsum() / float(v['div'])
        self.qkey = self.rev.index.asfreq('Q')
        self.qtd = self.rev.groupby(self.qkey).cumsum() / float(v['div'])
        self.ttm = self.rev.rolling(12).sum()
        self.share_ttm = self.rev / self.ttm * 100
        self.mom = self.rev.pct_change(1) * 100
        self.yoy_self = Y.mom_yoy(self.rev, Y.FLOW)
        self.yoy_ttm = Y.ttm_yoy(self.rev, Y.FLOW)
        # 「公告值」优先；没有官方同比列的家一律退回自算值（口径在页尾点名）。
        self.yoy = self.official_yoy if self.official_yoy is not None else self.yoy_self

        self.qsum = self.disp.groupby(self.qkey).sum()
        self.qcnt = self.disp.groupby(self.qkey).count()

        self.usd = self.usd_yoy = self.fx_contrib = None
        self.loc = self.loc_yoy = self.fgn = None
        if self.fx is not None:
            # 汇率腿有**两条**：本币腿 loc 与外币腿 fgn。恒等式永远是 loc ≡ fgn × fx。
            # 谁当主序列由「可不可加总」定（value.summable），与「谁是本币」无关 ——
            # 功能货币非本币的家（世芯 3661）这两件事落在不同的列上。
            lc = spec['fx'].get('local_col')
            if lc:
                # 主序列是外币腿（功能货币原值），本币腿在另一列（官方逐月折算栏）。
                self.loc = df[lc].astype(float)
                self.fgn = self.rev
                self.loc_yoy = Y.mom_yoy(self.loc, Y.FLOW)
            else:
                # 既有行为，一格不动：主序列就是本币腿，外币腿由它除汇率折出来。
                # 本币腿的同比仍走 self.yoy（有公告同比列的家用公告值）。
                self.loc = self.rev
                self.fgn = self.rev / self.fx
                self.loc_yoy = self.yoy
            self.usd = self.fgn
            self.usd_yoy = Y.mom_yoy(self.fgn, Y.FLOW)
            self.fx_contrib = self.loc_yoy - self.usd_yoy
            self.fxq = self.fx.groupby(self.qkey).mean()


# ══════════════════════════════════════════════════════════════════════════════
# §3 窗口与数据边界
# ══════════════════════════════════════════════════════════════════════════════
def _first_at_or_after(index, month_str):
    """x_from 落在序列之前就取序列首月（短序列的家不该被一个通用起点卡住）。

    `month_str is None` = spec 显式声明「用序列自己的起点」⇒ 下标 0。
    """
    if not month_str:
        return 0
    want = pd.Period(month_str, freq='M')
    for i, p in enumerate(index):
        if p >= want:
            return i
    return len(index) - 1


class Window(object):
    """一张图的窗口：从哪一格起、为什么是那一格、图注里那句话怎么写。

    **裁决本身在 `build/mrwin.py`**，本类只是个适配器：把 pandas 序列包成 `mrwin.Leg`
    喂进 `resolve()`，再把结果摊成本文件用得顺手的形状。规则住在那边的三个理由：
      · 它可以对着**已知错例**单测（`python3 build/mrwin.py`）—— 「今天没报错」与
        「规则坏了」在输出上长得一样，只有跑负例才分得开；
      · 它认得第三种情形：派生腿在窗口内一格都算不出来 ⇒ 整条 `drop`。留着一条全 null
        的次轴会让引擎印出一列没有线的右轴刻度（CONTRACT §6.3），而引擎只看字段在不在；
      · DENSE 图型的左端由构造保证（`start = max(所有腿的稠密首格)`），不靠逐图写对。

    「留前导 null 还是显式截断」**不在这里选**：由 `kind` 在不在 `mrwin.DENSE` 里决定，
    也就是由引擎的 `polyline(..., doSmooth)` 走哪一支决定。写图的人只需要把腿摆对
    （谁是 primary、谁是 derived、每条腿的 lag 用中文写清楚）。
    """

    def __init__(self, ds, i0, kind, legs):
        labels = [mlab(p) for p in ds.all]
        w = mrwin.resolve(kind, legs, labels, i0)
        self.res = w
        self.i0 = w.start
        self.kind = kind
        self.trim = w.start - i0
        self.why = w.why                    # 机读的「为什么这条线比那条短」，可直接进图注
        self.dropped = [l for l in w.legs if l.drop]
        self.months = ds.all[self.i0:]
        self.n = len(self.months)
        self.labels = [mlab(p) for p in self.months]
        # `full` 不在这里判：点数只是输入之一，判据（含 qtr_bar 的竖排标签下限）
        # 在 mrwin.layout()，它拿到的是画好的 exhibit，能同时看到 ylab/次轴/图型。
        self.full = None


def lay(d):
    """给一张画好的 exhibit 补 `full` / `xstep`，并把**实测数**接进它的图注。

    两件事都由 `build/mrwin.py` 按 `assets/charts.js` 的量边距算式（经 `build/chartscale.py`
    这一份唯一的几何模型）复算，不是目测：

      ① 通栏与抽稀 —— `mrwin.layout()`。127 点的柱图放半栏每格 3.6px，
         `build/CONTRACT.md` 的 `full` 字段那一行原文就写着「127 根柱塞进半栏
         每根不到 3px，必须通栏」，所以这不是审美取舍，是照章办事。
      ② 首/末点数值标签压轴刻度栏 —— `mrwin.label_clash()`，尺子是 `chartscale._budget`。
         这里**同时报半栏与通栏两个预算**：只报一个数没法回答「是拉长窗口引入的，
         还是本来就有」，而这一轮最容易犯的错就是把既有问题说成新问题、
         或者反过来把自己引入的问题说成既有的。
    """
    txt = mrwin.layout(d)
    c_half = mrwin.label_clash(d, full=False)
    c_full = mrwin.label_clash(d, full=True)
    if not (c_half and c_full):
        return txt
    if c_half['over'] > 0 and c_full['over'] <= 0:
        txt += (f'首点/末点的数值标签是<b>居中钉在自己那一格上</b>的，一宽就伸进左轴刻度栏：'
                f'本图最宽的那个标签 {c_half["w"]:.1f}px，'
                f'半栏时预算只有 {c_half["cap"]:.1f}px（= band {c_half["band"]:.1f}px + 12 − '
                f'2×{chartscale.LAB_GAP} 的最小间隙），超 {c_half["over"]:.1f}px；'
                f'通栏后 band {c_full["band"]:.1f}px、预算 {c_full["cap"]:.1f}px，'
                f'<b>冲突消失</b>。所以本图的通栏同时解掉了两件事，'
                f'不需要动用引擎「删一根刻度让位」的兜底。')
    elif c_full['over'] > 0:
        txt += (f'首点/末点的数值标签仍压左轴刻度栏：最宽 {c_full["w"]:.1f}px，'
                f'预算 {c_full["cap"]:.1f}px（band {c_full["band"]:.1f}px），'
                f'超 {c_full["over"]:.1f}px。引擎的 <code>dropClashingTicks</code> 会删掉'
                f'被压住的那一根刻度让位（至少留 2 根），所以画面不会糊，'
                f'但代价是<b>少一档刻度</b> —— 写在这里免得读者以为那一档本来就没有。')
    return txt


def _boundary_note(want_from, got_from, n, lag_desc, kind):
    """「本图为什么不是从 x_from 起」这句话 —— 数全部现算，一个都不写死。"""
    if str(want_from) == str(got_from):
        return ''
    gap = (pd.Period(str(got_from), freq='M') - pd.Period(str(want_from), freq='M')).n
    return (f'<b>本图从 {mlab(pd.Period(str(got_from), freq="M"))} 起，'
            f'比页面窗口起点 {want_from} 晚 {gap} 个月</b>：{lag_desc}。'
            f'<code>{kind}</code> 在引擎里走 Catmull-Rom 平滑曲线，'
            '<b>吃不了 null</b>（会被 JS 当 0，画出一条塌到零的假线，首尾为 null 还会抛 '
            'TypeError 让整页后续图全丢），所以这里**显式截断**而不是留空 —— '
            f'既不画空线，也不往前补零或补去年同值。截断后窗口 {n} 个月。')


# 「右轴那条线为什么比柱短」那句话不在本文件生成 —— `mrwin.resolve()` 返回的 `why`
# 就是它，而且它还覆盖本文件原来没有的第三种情形（整条腿窗口内无值 ⇒ drop）。


# ══════════════════════════════════════════════════════════════════════════════
# §4 断点
# ══════════════════════════════════════════════════════════════════════════════
def load_breaks(spec):
    """`breaks` 给列表就用列表，给字符串就当 series/ 下的文件名读。能读 CSV 就读。"""
    b = spec.get('breaks')
    if not b:
        return []
    if isinstance(b, str):
        import csv as _csv
        out = []
        with open(os.path.join(SERIES, b), encoding='utf-8') as fh:
            for row in _csv.DictReader(fh):
                m = row.get('month') or row.get('break_month')
                z = (row.get('zh') or row.get('footnote') or row.get('note')
                     or row.get('official_footnote'))
                if m and z:
                    out.append({'month': m.strip(), 'zh': z.strip()})
        b = out
    seen, out = set(), []
    for d in b:
        k = (d['month'], d.get('col'))
        if k in seen:
            continue
        seen.add(k)
        out.append(d)
    return sorted(out, key=lambda d: d['month'])


def apply_breaks(ex, months, breaks):
    """把落在本图窗口内的断点标到 `break_at`（第 0 格的不标：左缘就是画布边线）。

    **图上那条竖排标签只写月份，不写整句理由。** 引擎把 `break_label` 用 rotate(-90)
    从图顶往下挂，长度就是文字长度；把「USI 完成收购 Asteelflash（FAFG），自本月起并入
    EMS」这样一整句挂上去，在长窗口图上会横穿整片数值标签 ——
    实测（tools/visual_qa.py）mtk 7 处、ase 4 处、nanya 1 处 🔴 TEXT_OVERLAP，
    压的全是柱值/点值标签（「星宸科技出表（丧失控制…）」× 「35」，重叠 86.3px²）。
    数值标签是真实数据，断点的**理由**不是非得画在图上：
    ⇒ 图上留「红虚线 + 月份」，整句理由进图注（由下面的 break_note() 现读生成）。

    返回实际标上去的断点列表，供图注/页尾说明现读 —— **不写死**。

    ⚠️ `heat_matrix` 在这里**直接返回空**，规则与「不画断点线」这件事住在一起：
    引擎在 `assets/charts.js:717` 把 heat_matrix 短路给 `drawHeat()`，那条路径根本不读
    `break_at`，所以线一根都不画；而本函数除了写字段还会**追加 break_note() 那整段文字**。
    两件事不一致的后果是页面自相矛盾 —— 同一条图注里先写「heat_matrix 没有连续横轴，
    因此不画断点竖线」，紧接着又写「本图上的红色竖虚线是口径断点…」，页尾的
    「口径断点与截轴」还会把那张矩阵列进「已画成红色竖虚线」的名单。
    TSM 没有 breaks，所以这个坑到第一家有断点的页（联发科）才被踩到。
    """
    if ex.get('kind') == 'heat_matrix':
        return []
    idx = {str(p): i for i, p in enumerate(months)}
    hits = []
    for d in breaks:
        i = idx.get(d['month'])
        if i is None or i == 0:
            continue
        hits.append((i, d))
    if not hits:
        return []
    ex['break_at'] = [i for i, _ in hits]
    ex['break_label'] = [d['month'] for _, d in hits]
    ex['note'] = (ex.get('note') or '') + break_note([d for _, d in hits])
    return [d for _, d in hits]


def break_note(hits):
    """图上红虚线旁只有月份，整句理由在这里。"""
    if not hits:
        return ''
    body = '；'.join(f'<b>{d["month"]}</b> {d["zh"]}' for d in hits)
    return ('本图上的红色竖虚线是<b>口径断点</b>，语义是「从这一期起与左侧不可比」，'
            f'画在该期左缘：{body}。'
            '线旁只竖排月份、不写整句 —— 整句挂上去会横穿一整列数值标签，'
            '而数值标签是真实数据、断点的理由不是非画在图上不可。')


def legs(spec):
    """汇率腿的两条线怎么称呼，以及「非主序列那条腿」是不是我们折出来的。

    不给 `fx.local_col` 时**全部退回既有取值**，所以既有的家一个字都不变
    （TSM 打补丁前后 data/tsm.js 逐字节相同，本轮实测）。
    """
    v, fx = spec['value'], spec.get('fx') or {}
    lc = fx.get('local_col')
    return {
        'split': bool(lc),
        # 本币腿：另给一列时用 fx.local_* 命名，否则就是主序列自己
        'loc_label': fx.get('local_label') or v.get('zh', 'Local currency revenue'),
        'loc_zh': fx.get('local_zh') or v.get('ccy_zh', '本币'),
        'loc_sym': fx.get('local_sym') or v['sym'],
        # 外币腿
        'fgn_label': fx.get('usd_label') or 'US$ revenue',
        # 非主序列那条腿是不是推导值。默认 True = 既有行为。
        'implied': fx.get('implied', True),
    }


# ══════════════════════════════════════════════════════════════════════════════
# §5 brief（页顶 ~300 字数据总结）
# ══════════════════════════════════════════════════════════════════════════════
def compose_brief(ds, spec, EX):
    """规则库在 build/brief.py（R1-R6），那边只算事实、句子在这里拼。

    s1 规模 / s2 环比与季节定位 / s3 同比名次与基数护栏 —— 三句只用主序列，与家无关。
    s4 单位恒等（美元营收 = 本币 ÷ 汇率）**只在有汇率腿时才有**，没有汇率腿的家整句不写，
       而不是拿外部牌价折一条出来充数。
    s5 由 spec 的 `brief_extra` 钩子出（指引桥这种跨源推导，字段表达不了）；
       钩子没给或返回空串时，退回一条不依赖任何外部源的趋势位置判断。

    ⚠️ R3（按天数归一化的日历护栏）本底座**一律不做**：晶圆厂/封测厂 24/7 连续生产，
       看上去正该按天数归一化，但 TSMC 序列上实测 `(m/m) ~ (天数变化%)` 的回归斜率是
       1.47 而不是 1 —— 天数只是农历年与季末拉货日历的代理变量，不是产出的线性驱动。
       按天数除一遍会把农历年效应算成「经营性走弱」。季节性改用同月对同月定位。
    """
    ALL, rev = ds.all, ds.rev
    i = len(ALL) - 1
    n_all = len(ALL)
    KEYS = [str(p) for p in ALL]
    rv = rev.values.astype(float)
    v = spec['value']
    sym, div = v['sym'], float(v['div'])
    ccy_zh = v.get('ccy_zh', '本币')      # 「本币」是通用退路；给了中文名就用中文名
    unit = v.get('unit', 'bn')            # 显示单位后缀。写死 'bn' 会把 US$mn 的家印错
    # 规模数的小数位跟着 `value.dec` 走，不用 B.num() 的默认 1 位：抬头（headline）
    # 用的就是 `dec`，brief 另走一个默认值会让同一个月的同一个数在同一屏上印成两种
    # （GUC 的 dec=0：抬头 NT$5,769mn、brief NT$5,769.2mn）。dec=1 的家产出不变。
    dec = int(v.get('dec', 1))
    cur_bn = rv[i] / div

    def cnq(x):
        return '两' if x == 2 else B.cn(x)

    # ── s1：R1 峰值扫描。水平序列逐条列出；有汇率腿才多一条「外币营收」。
    lv = [('月营收', rv)]
    # ⚠️ 判据是 `usd_leg_shown(EX)` 而不是 `ds.usd is not None`（§1.5）：挂了 fx 只为画
    #    汇率线、页上并没有美元腿的家（Ex5/Ex6 被 skip 掉），这里若照旧按 ds.usd 判，
    #    第 1 句会去数一条页面上根本不存在的「美元营收」有没有见顶，还会改掉
    #    「几条水平序列同时见顶」这个计数的分母。
    if ds.usd is not None and usd_leg_shown(EX):
        _LG = legs(spec)
        if _LG['split']:
            # 主序列**就是**外币腿（功能货币非本币的家）。再列一遍 ds.usd 等于
            # 把同一条序列点两次名，「四条水平序列里有两条见顶」会把一条数成两条。
            # 该多出来的是**本币腿**：它被汇率推着走，见顶时点可以与主序列不同。
            lv.append((f'{_LG["loc_zh"]}营收', ds.loc.values.astype(float)))
        else:
            lv.append(('美元营收', ds.usd.values.astype(float)))
    lv += [('三月均值', rev.rolling(3).mean().values.astype(float)),
           ('滚动12个月', rev.rolling(12).sum().values.astype(float))]
    pk = B.peak_scan(KEYS, lv, i)
    n_lv = len(pk['at_peak']) + len(pk['off_peak'])
    mth = ALL[i].month
    mrank = B.rank_of(rv, i)
    lead = (f'{mth}月合并营收<b>{sym}{B.num(cur_bn, dec)}{unit}</b>'
            + (f'为{n_all}个月最高' if mrank == 1 else f'在{n_all}个月里排第{mrank}'))
    if not n_lv:
        s1 = lead + '。'
    elif not pk['off_peak']:
        s1 = f'{lead}，{cnq(n_lv)}条水平序列同时见顶，靠「创新高」分不出高下。'
    elif not pk['at_peak']:
        s1 = (f'{lead}，{cnq(n_lv)}条水平序列一条都没见顶，'
              f'峰值停在{B.peak_months_txt(pk["off_peak"])}月。')
    else:
        q = B.quant(len(pk['at_peak']), n_lv, '条').replace('二条', '两条')
        s1 = (f'{lead}，{cnq(n_lv)}条水平序列里{q}见顶：{"、".join(pk["at_peak"])}，'
              f'其余停在{B.peak_months_txt(pk["off_peak"])}月。')

    # ── s2：R2 基数护栏（m/m 一侧）+ 同月对同月的季节定位。
    be = B.base_effect(rv, i)
    mm = be['mm']
    mom_all = ds.mom
    same = [(p.year, float(mom_all[p])) for p in ALL
            if p.month == mth and np.isfinite(float(mom_all.get(p, np.nan)))]
    if mm is None:
        s2 = ''
    else:
        up = mm > 0
        streak = 0
        for _, val in reversed(same[:-1]):
            if (val > 0) == up:
                break
            streak += 1
        j = len(same) - 2 - streak
        if streak >= 2 and j >= 0:
            seas = (f'前{cnq(streak)}个{mth}月全为{"负" if up else "正"}，'
                    f'上一次转{"正" if up else "负"}还是{same[j][0]}年')
        elif len(same) >= 3:
            r = sorted((val for _, val in same), reverse=True).index(same[-1][1]) + 1
            seas = f'在{len(same)}个{mth}月里{"最高" if r == 1 else f"排第{r}"}'
        else:
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

    # ── s3：R2 的 y/y 一侧。名次说的是**单月**同比（CONTRACT §6 措辞），
    #    并把滚动读数并排印出、点名 Ex2 口径 —— 不带滚动读数，读者会拿它去对 Ex2 的金线。
    yd = ds.yoy.values.astype(float)
    n_y = int(np.isfinite(yd).sum())
    yrank = B.rank_of(yd, i)
    r12 = float(ds.yoy_ttm.values.astype(float)[i])
    roll_tag = (f'（{Y.TTM_WIN}个月滚动口径是{B.pct(r12 / 100)}，Exhibit {EX["rev_bar"]}）'
                if B.need(r12) else '')
    if yrank is None:
        s3 = ''
    else:
        head = (f'单月同比在{n_y}个月里{"最高" if yrank == 1 else f"排第{yrank}"}' + roll_tag)
        if i >= 13 and B.need(rv[i - 13], rv[i - 12], rv[i - 11], yd[i]):
            # 反事实基数 = 去年同月**前后两个月**的均值，不含去年同月自己 ——
            # 要量的就是「去年同月这个凹坑有多深」，把凹坑月放进它自己的平滑窗口会低估它。
            m2 = (rv[i - 13] + rv[i - 11]) / 2
            dip = rv[i - 12] / m2 - 1
            cf = rv[i] / m2 - 1
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

    # ── s4：R4 单位恒等。**只有美元腿真的画在页上才有这一句。**
    #    判据是 usd_leg_shown(EX)，不是 ds.fx（§1.5）：这一句整句在讲「美元营收 =
    #    本币 ÷ 汇率」，主语是一条**公司**序列。只挂了宏观汇率线（Ex8）的家页上没有那条
    #    序列，写这句等于凭空引入一个页面别处查不到、也不是公司披露的数。
    #    这一句落空之后，下面那两级替补（分部构成 / 季内进度）会自动接上，字数不会塌。
    s4 = ''
    if ds.fx is not None and usd_leg_shown(EX):
        LG = legs(spec)
        # 恒等式的分子永远是**本币腿**：本币 ÷ 汇率 = 外币。主序列已经是外币的家
        # （功能货币非本币）这里必须取 ds.loc，取 rv 会算成「外币 ÷ 汇率」。
        loc_zh = LG['loc_zh']            # 本币腿的中文名，可能不是 value 那一列的
        # 两条腿都是官方申报值的家，不许把外币腿说成「推导值」。
        _ut = '美元营收（推导值）' if LG['implied'] else '美元营收（官方申报）'
        locv = ds.loc.values.astype(float)
        pu = B.per_unit(locv, ds.fx.values.astype(float), i)
        dy, uy = pu.get('den_yoy'), pu.get('yoy')
        if B.need(dy, uy):
            nt = float(pu['num_yoy'])
            amp = 1 + uy
            amt = abs(dy) * 100
            pps = f'{(nt - uy) * 100:+.1f}'
            if float(pps) == 0:
                pps = f'{0.0:.1f}'
            if amt < 0.05:
                s4 = (f'{_ut}单月同比{B.pct(uy)}几乎等于{loc_zh}{B.pct(nt)}，'
                      f'本月汇率基本没动，汇率贡献{pps}pp 可以忽略。')
            else:
                band = f'汇率{"贬" if dy > 0 else "升"}幅{amt:.1f}%'
                rel = ('与汇率幅度几乎相等' if abs(amp - 1) < 0.05
                       else f'本月相当于汇率幅度的{amp:.1f}倍')
                s4 = (f'{_ut}单月同比{B.pct(uy)}，是{loc_zh}单月{B.pct(nt)}除以'
                      f'{band}的商；汇率贡献{pps}pp 只是两者之差，{rel}。')
        elif i >= 1 and B.need(locv[i - 1], ds.fx.values[i], ds.fx.values[i - 1]):
            fm = float(ds.fx.values[i]) / float(ds.fx.values[i - 1]) - 1
            um = float(pu['series'][i]) / float(pu['series'][i - 1]) - 1
            # 分子的环比也要取本币腿，不能用主序列的 be['mm']（主序列可能就是外币腿）。
            lm = float(locv[i]) / float(locv[i - 1]) - 1
            s4 = (f'{_ut}环比{B.pct(um)}，是{loc_zh}{B.pct(lm)}除以汇率'
                  f'{"贬" if fm > 0 else "升"}幅{abs(fm) * 100:.1f}%的商；同比要满 12 个月才有。')

    # ── s4 的替补：没有汇率腿的家，第 4 句的位置不能空着。
    #    这不是凑字数：brief 的模板是「规模 / 基数 / 分母 / 恒等式 / 位置」五层，
    #    第 4 层空掉之后（实测 ase 226 字）会撞上 brief.render 的 230 字下限、整页发不出去。
    #    替补必须仍然是一句**恒等式或构成**的陈述，不能换成形容词：
    #      · 有分部列的家 → 分部构成（合并 = 各分部之和，这就是本家的恒等式）；
    #      · 都没有的家   → 季内进度（QTD 相对上年同季前同样月数，纯表内算术）。
    if not s4 and ds.segments:
        parts = []
        for sd, ss in ds.segments:
            sh = float(ss.iloc[-1]) / rv[i] * 100
            sy = (float(ss.iloc[-1]) / float(ss.iloc[i - 12]) - 1) * 100 \
                if i >= 12 and float(ss.iloc[i - 12]) else float('nan')
            parts.append((sd, sh, sy))
        if all(np.isfinite(x[2]) for x in parts):
            txt = '、'.join(f'{sd["zh"]}占{sh:.0f}%（单月同比{sy:+.0f}%）' for sd, sh, sy in parts)
            s4 = (f'合并数按官方逐月拆分是{txt}；'
                  f'合并 ≡ 各分部之和，所以合并那个{B.pct(yd[i] / 100)}是这两条按权重加起来的结果，'
                  '不是一条业务线的读数。')
        else:
            txt = '、'.join(f'{sd["zh"]}占{sh:.0f}%' for sd, sh, _ in parts)
            s4 = f'合并数按官方逐月拆分是{txt}；合并 ≡ 各分部之和，同比要分开读。'
    if not s4:
        k = int(ds.qcnt.iloc[-1])
        qn = float(ds.qtd.get(ALL[i], np.nan))
        qy = float(ds.qtd.get(ALL[i] - 12, np.nan))
        if B.need(qn, qy) and qy:
            s4 = (f'季内进度：本季已公布{cnq(k)}个月，累计{sym}{B.num(qn, dec)}{unit}，'
                  f'比上年同季<b>前同样{cnq(k)}个月</b>{B.pct(qn / qy - 1)}；'
                  '这是表内算术（同一批日历月比同一批日历月），不是把未公布的月份外推出来的。')

    # ── s5：spec 的钩子（指引桥）。没有就退回趋势位置判断。
    s5 = ''
    hook = spec.get('brief_extra')
    if callable(hook):
        s5 = hook({'ds': ds, 'spec': spec, 'i': i, 'B': B, 'Y': Y,
                   'cur_bn': cur_bn, 'cnq': cnq, 'mth': mth}) or ''
    if not s5:
        # 少这一句整页会撞上 render 的字数下限而发不出去 —— 那是拿页面的可发布性换一段解读。
        m3s = rev.rolling(3).mean().values.astype(float)
        if i >= 14 and B.need(m3s[i], m3s[i - 12], yd[i]) and m3s[i - 12]:
            t3 = m3s[i] / m3s[i - 12] - 1
            d = yd[i] - t3 * 100
            s5 = (f'再看趋势位置：三月均值同比{B.pct(t3)}把单月噪音抹平，'
                  f'单月同比比它{"高" if d >= 0 else "低"}{abs(d):.1f}pp，'
                  f'本月把均值往{"上" if d >= 0 else "下"}拐。')

    return B.render([s1, s2, s3, s4, s5])


# ══════════════════════════════════════════════════════════════════════════════
# §6 Exhibit 1：汇总表
# ══════════════════════════════════════════════════════════════════════════════
def build_summary(ds, spec):
    ALL = ds.all
    cur, prv, yag = ALL[-1], ALL[-1] - 1, ALL[-1] - 12
    heads = [mlab(cur), mlab(prv), mlab(yag), 'm/m', 'y/y', '3Y %ile']
    v = spec['value']
    lab_bn = v['label']

    def pctile_cell(s, inv=False):
        vals = [None if x is None or not np.isfinite(float(x)) else float(x) for x in s.values]
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

    def chg_txt(x, mode, inv=False):
        if x is None:
            return '', ''
        good = (x < 0) if inv else (x > 0)
        cls = 'pos' if good else ('neg' if x != 0 else '')
        if mode == 'pp':
            txt = f'{x * 100:+.0f}bp' if abs(x) < 1 else f'{x:+.2f}pp'
        else:
            txt = f'{x:+.1f}%'
        return txt, cls

    dec = int(v.get('dec', 1))
    rows = [('group', 'Revenue', None, None, None, None, None, False),
            ('row', f'Monthly revenue ({lab_bn})', ds.disp, dec, False, 'ratio', False, False)]
    # 分部行（日月光的 ATM / 非 ATM，创意的 turnkey / NRE）——「合并含多少 EMS」这类
    # 事实由数据自己说，不写进散文。
    for sd, ss in ds.segments:
        rows.append(('row', f'{sd["label"]} ({lab_bn})', ss / float(v['div']),
                     dec, False, 'ratio', False, False))
    rows += [('row', f'3-month moving avg. ({lab_bn})', ds.ma3, dec, False, 'ratio', False, False),
             ('group', 'Cumulative', None, None, None, None, None, False),
             ('row', f'Quarter-to-date ({lab_bn})', ds.qtd, dec, False, 'ratio', False, True),
             ('row', f'Year-to-date ({lab_bn})', ds.ytd, dec, False, 'ratio', False, True),
             ('group', 'Seasonality', None, None, None, None, None, False),
             ('row', '% of trailing-12-month revenue', ds.share_ttm, 2, True, 'pp', False, False)]

    # QTD / YTD 的**月数现算**。原来图注里写死「QTD 为 3 个月 vs 3 个月、YTD 为 6 个月
    # vs 6 个月」—— 那只在季末月/半年末成立，数据到 2026-07 时实际是 1 vs 1 与 7 vs 7，
    # 而这一句正是在教读者「这两行里哪个读数可比」，说错了比不说更坏。7 页全带过这个错。
    _qm = (cur.month - 1) % 3 + 1          # 当季已过几个月
    _ym = cur.month                        # 当年已过几个月
    srows, blanked, short_blanked, cum_blanked = [], [], [], []
    for kind, lab, s, d, pct, mode, inv, cum in rows:
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
            # 周期内累计行的 m/m 与 3Y %ile 两列在结构上就没有信息：
            #  · m/m 恒等于「上月累计 + 当月营收」，跨期时又变成 1 个月比 3/12 个月；
            #  · 分位池混装 1/2/3 个月量纲，读数由「本月是期内第几个月」决定。
            mtx, mcls = '', ''
            cum_blanked.append(lab)
            pcell = {'v': ''}
        else:
            pcell, why = pctile_cell(s, inv)
            if why:
                (short_blanked if '样本不足' in why else blanked).append(lab)
        srows.append({'label': lab, 'cells': [
            {'v': f(c, d, pct), 'cls': 'cur'},
            {'v': f(p1, d, pct)},
            {'v': f(p12, d, pct)},
            {'v': mtx, 'cls': mcls},
            {'v': ytx, 'cls': ycls},
            pcell]})

    note = ('All figures derived from the single officially disclosed field: consolidated '
            f'net revenue ({v["raw_label"]}, unaudited)。'
            '「3Y %ile」= 当月读数在最近 36 个月中高于多少百分比的观测，分位越高越极端；'
            '比率行（占 TTM 比重）的 m/m、y/y 一律用百分点差（|差|&lt;1pp 时改用 bp），'
            '不用「百分比的百分比变化」。'
            + (f'周期内累计的行（{"、".join(cum_blanked)}）的 m/m 与 3Y %ile 已一并留空：'
               'm/m 的分子分母在同一期内只差一个月（本期累计 = 上月累计 + 当月营收），'
               '跨期时又变成 1 个月比 3／12 个月，两种情形都不可比，正负号只反映日历位置；'
               '分位则由「本月是期内第几个月」决定 —— 季内第 1／2／3 个月分别锚在约 '
               '30／80／100，与经营好坏无关。这两行的可比读数是 y/y'
               f'（QTD 为 {_qm} 个月 vs {_qm} 个月、YTD 为 {_ym} 个月 vs {_ym} 个月），已保留。'
               if cum_blanked else '')
            + '分位判据统一走 <code>build/pctile.py</code>（全站一份实现，避免同一条序列'
              '在两页判成两个结果）：把该行的分位在最近 24 个月里逐月回放一遍，'
              '若 ≥70% 的月份钉在 100 或 0，这一列对这一行就没有区分度，留空。'
            + (f'本轮据此留空的行：{"、".join(blanked)}'
               '（平滑序列比原始月度序列更单调，分位常年在高位，'
               '看着像「又创新高」，其实只是三个月均值本来就很少回落）。'
               if blanked else '本轮无行触发该判据。')
            + (f'另有 {"、".join(short_blanked)} 因可用样本不足 8 个月，分位算不出可信读数，'
               '一并留空。' if short_blanked else ''))

    return {'title': f'{spec["name"]} monthly revenue summary — {mlab(cur)}',
            'heads': heads, 'sep': 3, 'rows': srows, 'note': note}, blanked


# ══════════════════════════════════════════════════════════════════════════════
# §7 Exhibit 2..9
# ══════════════════════════════════════════════════════════════════════════════
def build_exhibits(ds, spec, breaks):
    """返回 (exhibits, EX, ctx)。EX 是 slug → 编号，页内互指全部查它。"""
    v = spec['value']
    sym, div, lab_bn = v['sym'], float(v['div']), v['label']
    ccy_zh = v.get('ccy_zh', '本币')
    ALL = ds.all
    x_from = spec['window']['x_from']
    i_x = _first_at_or_after(ALL, x_from)
    want_from = str(ALL[i_x])
    skip = set(spec.get('skip') or [])
    has_fx = ds.fx is not None

    # ── 哪些 slug 真的出图。编号在这里一次性算完，后面所有互指都查 EX。
    #
    # 这一行只回答一个问题：**画得出来吗**（没有 fx 序列，三张汇率图一格都没有）。
    # 「画得出来但不该画」是另一个问题，由 spec 的 `skip` 回答，两者不许混在一行里 ——
    # 原来这里把 Ex5/Ex6/Ex8 捆成一束，于是「没有官方美元营收实绩」的家连**汇率线本身**
    # 也一起跳掉了。但 Ex8 画的是 ds.fx（NTD/USD 这条宏观序列），不是任何营收量，
    # 公司披不披露美元营收与它无关（§1.5）。
    order = [s for s in _SLUGS
             if s not in skip
             and (has_fx or s not in _FX_SLUGS)]
    EX = {s: i + 2 for i, s in enumerate(order)}
    n_table = len(order) + 2

    def R(slug):
        return f'Exhibit {EX[slug]}'

    # 热力矩阵的口径（§1.6）。EX 里没有 heat 时也算得出来，页内几处点名都要用它判。
    HM_KEY = spec['window'].get('heat_metric', _HEAT_DEFAULT)
    HM = _HEAT_TXT[HM_KEY]
    heat_is_single_yoy = 'heat' in EX and HM['is_yoy']

    ex = []
    ctx = {'EX': EX, 'order': order, 'n_table': n_table, 'want_from': want_from,
           'brk_drawn': {},
           # 页尾要用的口径事实：矩阵画的是哪个量、算不算单月同比（§1.6）。
           'heat_txt': HM, 'heat_is_single_yoy': heat_is_single_yoy}

    # 画的**不是这家公司的量**的图，不许套这家公司的口径断点。
    # 目前只有一张：fx_rate（NTD/USD 汇率）是一条宏观序列，七页上逐点相同，
    # 与公司的并表/处分/重述没有任何关系。
    #
    # 这条为什么以前没暴露：现网唯二有 fx 的两页（tsm / alchip）breaks 都是空的，
    # apply_breaks 在这张图上一次都没真正执行过。本轮五家挂 fx 之后，
    # 其中四家（ase/mtk/nanya/umc）的 breaks 非空，实测汇率图当场拿到
    # break_at=[35,37,78] 之类，图注还把理由整句印上去 —— 页面等于声称
    # 「联发科的并购把新台币兑美元汇率的口径打断了」。
    # 它不报错、三道闸门全绿，属于「页面在说谎」那一类，必须在这里堵死。
    _NO_BREAKS = ('fx_rate',)

    def push(slug, d, months):
        d['n'] = EX[slug]
        if slug in _NO_BREAKS:
            ex.append(d)
            return
        hits = apply_breaks(d, months, breaks)
        if hits:
            ctx['brk_drawn'][slug] = hits
        ex.append(d)

    # ── Ex2：月营收柱 + 右轴 12 个月滚动合计同比 ─────────────────────────────
    if 'rev_bar' in EX:
        w = Window(ds, i_x, 'gs_bar', [
            mrwin.Leg('bar', '月营收柱', ds.disp.values, 'primary'),
            mrwin.Leg('ttm', f'右轴的 {Y.TTM_WIN} 个月滚动合计同比', ds.yoy_ttm.values,
                      'derived',
                      f'{Y.TTM_WIN} 个月填窗 + {Y.TTM_WIN} 个月比较 = '
                      f'{2 * Y.TTM_WIN} 个月历史')])
        bars = ds.disp.iloc[w.i0:]
        line = ds.yoy_ttm.iloc[w.i0:]
        CAL = Y.caliber_diff(ds.rev, Y.FLOW, win=w.n)
        lag = w.why
        d = {'kind': 'gs_bar', 'height': 300,
             'title': f'{spec["name"]} monthly revenues（右轴 = {Y.TTM_WIN} 个月滚动合计同比）',
             'xlabels': w.labels, 'xrot': 90,
             'ylab': lab_bn, 'ylab2': f'% y/y（{Y.TTM_WIN}M 滚动合计）',
             'legend': 'Reported', 'fmt': 'f0', 'label_fmt': 'f0',
             'values': L(bars.values),
             'yoy': {'name': f'{Y.TTM_WIN} 个月滚动合计的同比（RHS）', 'color': 'GOLD',
                     'values': L(line.values), 'yfmt': 'pct0'},
             'src_extra': f'Gold line = {Y.TTM_WIN}-month rolling-sum y/y (RHS).',
             'note': ('<b>柱与线是两种口径，这不是笔误</b>：柱是公司公告的<b>单月</b>合并营收'
                      # 原始单位与显示单位相同的家（div=1）不印「换算成…显示」——
                      # 那句话在它们身上会变成「US$mn 换算成 US$mn」这种空转。
                      + (f'（{v["raw_label"]}，此处换算成 {lab_bn} 显示）'
                         if v['raw_label'] != lab_bn else f'（{v["raw_label"]}）')
                      + '；右轴金线是'
                      f'<b>{Y.TTM_WIN} 个月滚动合计的同比</b>（最近 {Y.TTM_WIN} 个月营收合计 ÷ '
                      f'上一个 {Y.TTM_WIN} 个月合计 − 1）。'
                      '<b>所以不要拿相邻两根柱去除，除出来的是单月同比、跟这条线不是一个数。</b>'
                      '单月同比仍在页内可读：汇总表的 y/y 列'
                      + (f'、{R("fx_lines")} 的深藏青线' if 'fx_lines' in EX else '')
                      # ⚠️ 判据是「那张矩阵画的是不是单月同比」，不是「有没有矩阵」：
                      #    heat_metric 换成环比之后，把它列进「单月同比可读之处」就是
                      #    一句假话；对数口径仍是同比，但格内不是百分比，要加括注。
                      + (f'、{R("heat")} 的热力矩阵' + HM['named_extra']
                         if heat_is_single_yoy else '')
                      + '，以及页顶 brief 里标明「单月」的读数。' + Y.describe(CAL)
                      + '月营收的单月同比同时被三件事推着走 —— 当月天数、农历年在 1 月还是 '
                      '2 月、以及去年同月那一个数本身的高低；任意连续 '
                      f'{Y.TTM_WIN} 个月覆盖同样的日历，这三件事在滚动口径里自己抵消掉了，'
                      '代价是转折点晚半年才显形。' + lag)}
        d['note'] += lay(d)
        push('rev_bar', d, w.months)

    # ── Ex3：月度 → 季度桥 ──────────────────────────────────────────────────
    if 'qtr' in EX:
        q0 = ds.qkey[i_x]
        qsum = ds.qsum[ds.qsum.index >= q0]
        qcnt = ds.qcnt[ds.qcnt.index >= q0]
        qv_all = ds.qsum.values
        qc_all = ds.qcnt.values
        # 季度同比：**3 个月比 3 个月**。用全序列算再截窗口 —— 只截窗口会平白丢掉
        # 首 4 季本来算得出的值（窗口起点之前的季度是真实存在的分母）。
        #
        # ⚠️ 分子或分母只要有一边不满 3 个月，这个比值就不是季度同比，是「n 个月比 3 个月」。
        # 引擎的 `partial_months` 只管**末季**（charts.js 的 partialQ 判据是 i === n−1），
        # 管不了左缘：序列从季中开始的家（日月光 series/ase.csv 自 2018-05，2018Q2 只有
        # 5、6 两个月）会在 4 个季之后印出一个纯口径产物 —— 实测 2019Q2 = +46.3%，
        # 而同为 5+6 月的可比口径是 −0.53%，差 47 个百分点。
        # 页尾还印着「（季度口径，3 个月比 3 个月）」，等于页面自己为一个 3 比 2 的数背书。
        # ⇒ 两边都必须满 3 个月，否则这一格**一律置 null**（与引擎对末季的处置同义），
        #    并把柱一并从窗口里砍掉（不满季的柱留着而没有任何提示，比没有更糟）。
        qy_all = np.array([(qv_all[k] / qv_all[k - 4] - 1) * 100
                           if (k >= 4 and qv_all[k - 4]
                               and qc_all[k] >= 3 and qc_all[k - 4] >= 3)
                           else np.nan
                           for k in range(len(qv_all))])
        # 头部残季：末季由引擎画浅蓝 + 作废 y/y，头部没有这条路，只能不画。
        head_cut = 0
        while head_cut < len(qsum) - 1 and int(qcnt.iloc[head_cut]) < 3:
            head_cut += 1
        if head_cut:
            qsum, qcnt = qsum.iloc[head_cut:], qcnt.iloc[head_cut:]
        qy = pd.Series(qy_all, index=ds.qsum.index)[ds.qsum.index >= qsum.index[0]]
        n_in_last = int(qcnt.iloc[-1])
        d = {'kind': 'qtr_bar',
             'title': 'Monthly revenue aggregated to quarters',
             'xlabels': [str(p) for p in qsum.index], 'xrot': 90,
             'values': L(qsum.values), 'fmt': 'f0c', 'label_fmt': 'f0c',
             'ylab': lab_bn, 'legend': 'Complete quarter',
             'partial_months': n_in_last, 'qtr_months': 3,
             'line': {'name': 'y/y (RHS)', 'color': 'GREEN',
                      'values': L(qy.values), 'yfmt': 'pct0'},
             'note': (f'季度值 = 该季已公布月份的{sym}营收直接相加，不做任何调整。'
                      + (f'本期 {qsum.index[-1]} 已满 3 个月，是完整季度；'
                         if n_in_last >= 3 else
                         f'本期 {qsum.index[-1]} 只公布了 3 个月中的 {n_in_last} 个月，末柱画成浅蓝，'
                         f'且右轴 y/y 的最后一点<b>在 payload 里就是 null</b>'
                         f'（{n_in_last} 个月累计对上年完整 3 个月不可比；'
                         '引擎自己也会作废末季那一点，这里不指望它兜底 —— '
                         '一个 payload 里躺着的「1 个月比 3 个月」迟早会被谁读走）；')
                      + '这张图是「用月营收抢跑季报」的核心图，但季报口径含其他收入项，'
                        '与本表不完全相等。'
                      + f'窗口自 {qsum.index[0]} 起共 {len(qsum)} 个季度；'
                      + ('右轴季度同比在窗口内逐格都有值（季度同比要 4 个季历史，'
                         '本图用**全序列**算完再截窗口，所以窗口首格的分母来自窗口之外的真实季度）。'
                         if bool(np.isfinite(qy.values[0])) else
                         '右轴季度同比需要 4 个季历史，窗口首格之前的分母不在序列里，'
                         '故线的前几格留空 —— qtr_bar 的右轴走非平滑 polyline，'
                         '前导 null 只是「笔还没落下」，不会画出假值。')
                      + ('<b>右轴是严格的 3 个月比 3 个月</b>：分子或分母只要有一边不满 '
                         '3 个月，这一格一律留空，不印一个「n 个月比 3 个月」的数。'
                         if not head_cut else
                         f'<b>本序列自 {ds.all[0]} 开始，头 {head_cut} 个季度不满 3 个月，'
                         f'已整季不画</b>：引擎的未满季处理（浅蓝柱 + 作废 y/y）只管末季，'
                         f'管不了左缘；把一个 {int(ds.qcnt.iloc[0])} 个月的残季画成正常深蓝柱，'
                         f'四个季之后还会印出一个「{int(ds.qcnt.iloc[0])} 个月比 3 个月」的同比 —— '
                         f'那不是增速，是口径产物。右轴同样要求分子分母两边都满 3 个月。'))}
        _a = align_sim(d)
        if _a is None or _a['waste'] <= 1e-9:
            d['note'] += ('本图右轴 y/y 在窗口内不跨零，两轴零点本来就同高，左轴自 0 起。')
        elif _a['aligned']:
            d['note'] += (
                f'右轴 y/y 跨零，按引擎「两轴零点必须同高」的硬规矩，左轴被迫向下扩到 '
                f'{_a["lo"]:,.0f}（{lab_bn}），柱因此压在画布上半张。'
                f'这一处是<b>明知的取舍</b>：对齐扩出来的无数据区占左轴量程的 {_a["waste"]:.0%}，'
                f'低于引擎「浪费 >{ALIGN_WASTE_MAX:.0%} 就改为不对齐并标注」的兜底阈值，'
                f'所以这里仍然对齐。')
        else:
            d['note'] += (
                f'右轴 y/y 跨零，但对齐两轴零点要把左轴一路扩到 {_a["alo"]:,.0f}（{lab_bn}）、'
                f'浪费掉量程的 {_a["waste"]:.0%}（超过引擎 {ALIGN_WASTE_MAX:.0%} 的兜底阈值），'
                f'<b>所以本图两轴各自缩放、零点不同高</b>，引擎已在绘图区左上角标出。'
                f'读柱与读点时不要假设「都在零线同一侧就是同号」。')
        d['note'] += lay(d)
        ctx['qtr_align'] = _a
        ctx['n_in_last'] = n_in_last
        ctx['q_head_cut'] = head_cut
        ctx['cur_q'] = qsum.index[-1]
        ctx['qsum_win'] = qsum
        # 季度轴上的断点：横轴一格是一个季，逐月的断点月要映射到季。
        qidx = [str(p) for p in qsum.index]
        qbrk = []
        for b in breaks:
            qp = str(pd.Period(b['month'], freq='M').asfreq('Q'))
            if qp in qidx and qidx.index(qp) > 0:
                qbrk.append({'month': qp, 'zh': b['zh']})
        d['n'] = EX['qtr']
        hits = apply_breaks(d, list(qsum.index), qbrk)
        if hits:
            ctx['brk_drawn']['qtr'] = hits
        ex.append(d)

    # ── Ex4：环比（gs_line，平滑 → 必须截断）───────────────────────────────
    if 'mom' in EX:
        w = Window(ds, i_x, 'gs_line', [
            mrwin.Leg('mom', '环比', ds.mom.values, 'primary', '环比要 1 个月的 lag')])
        d = {'kind': 'gs_line', 'fmt': 'pct1',
             'title': 'Month-on-month revenue change',
             'xlabels': w.labels, 'xrot': 90,
             'ylab': '% m/m', 'zero_line': True,
             'values': L(ds.mom.iloc[w.i0:].values),
             'note': ('环比不做季节调整。台湾半导体的月营收有很强的日历效应（2 月天数少、'
                      '农历年错位），单月 m/m 不能当趋势读；季内进度请看汇总表的 '
                      'Quarter-to-date 一行，那是实测累计，不是外推。'
                      + _boundary_note(want_from, str(w.months[0]), w.n,
                                       '环比要一个月的 lag，窗口首月没有上月可比',
                                       'gs_line'))}
        d['note'] += lay(d)
        push('mom', d, w.months)

    # ── Ex5：本币 vs 美元单月同比（lines_endlabels，平滑 → 必须截断）────────
    if 'fx_lines' in EX:
        # ⚠️ 这一格最阴：NAVY 线走的是公司**公告**的 y/y（序列第一个月就有值，基于我们
        #    没有的上年数据），MBLUE 是自算的、要 12 个月 lag。按主腿定左端会让 series[1]
        #    首格是 null —— DENSE 图型一个 null 就是 verify_pages 的 ERROR，引擎那边
        #    则是 TypeError 让该卡片以下全不渲染。`resolve()` 对 DENSE 取所有腿的最大值，
        #    这是**由构造保证**的，不靠写图的人记得两条腿的 lag 不一样。
        LG = legs(spec)
        w = Window(ds, i_x, 'lines_endlabels', [
            mrwin.Leg('loc', f'{LG["loc_zh"]} 单月同比', ds.loc_yoy.values, 'primary',
                      '单月同比要 12 个月的 lag'),
            mrwin.Leg('usd', '美元口径单月同比', ds.usd_yoy.values, 'primary',
                      '单月同比要 12 个月的 lag')])
        CAL = Y.caliber_diff(ds.rev, Y.FLOW, win=w.n)
        # 两条线各自的名字与「谁是推导值」由 legs() 定：
        #   · 本币入账的家（TSM）：NAVY = 本币公告值，MBLUE = 我们折的美元（推导值）
        #   · 功能货币是外币的家（世芯）：NAVY = 官方折算的本币栏，MBLUE = 官方申报的
        #     外币栏，两条都是官方值，不能印「推导值（Implied）」
        _navy = (f'{LG["loc_label"]} y/y (as filed)' if LG['split']
                 else f'{LG["loc_label"]} y/y (as reported)')
        _mblue = (f'{LG["fgn_label"]} y/y (converted)' if LG['implied']
                  else f'{LG["fgn_label"]} y/y (as filed)')
        if LG['implied']:
            _leadin = (f'US$ 线是<b>推导值（Implied）</b>：{LG["loc_zh"]}月营收 ÷ 当月平均汇率，'
                       '不是公司披露的美元营收。假设：全部营收按当月平均汇率一次性折算，'
                       '忽略月内汇率路径、对冲与递延收款，因此这条线只能看方向与量级。')
        else:
            _leadin = ('<b>两条线都是官方申报值</b>：'
                       f'{LG["fgn_label"]} 是公司功能货币的原值，'
                       f'{LG["loc_zh"]}那条是官方按自己申报的「本月換算匯率」逐月折出来的，'
                       '两者由官方恒等式绑定，页面没有引入任何外部牌价，'
                       '也没有任何一条线是我们折出来的。'
                       f'因果方向要留意：这里是<b>{LG["loc_zh"]}被汇率决定</b>，'
                       '不是汇率去解释一个独立观测到的本币数。')
        d = {'kind': 'lines_endlabels', 'fmt': 'pct0',
             'title': f'Revenue growth: {LG["loc_sym"]} vs. US$'
                      '（单月同比 / single-month y/y）',
             'xlabels': w.labels, 'xrot': 90,
             'ylab': '% y/y（单月）',
             'series': [
                 {'name': _navy, 'color': 'NAVY',
                  'values': L(ds.loc_yoy.iloc[w.i0:].values)},
                 {'name': _mblue, 'color': 'MBLUE',
                  'values': L(ds.usd_yoy.iloc[w.i0:].values)}],
             'src_extra': ('The gap between the two lines is the currency contribution. '
                           + spec['fx'].get('assumption', '')),
             'note': (_leadin
                      + f'<b>本图两条线都是单月同比</b>，与 {R("rev_bar")} 右轴的 '
                      f'{Y.TTM_WIN} 个月滚动口径<b>不是一个数</b>：'
                      '本图讲的是「公司这个月报出来的增速里有多少是汇率」，'
                      f'NAVY 线的线名写着 {"as filed" if LG["split"] else "as reported"}，'
                      '换成滚动口径它就不再是公司报的那个数了。'
                      f'口径差异用本序列自己实测（{CAL["n"]} 个两种同比都有值的月份）：'
                      f'单月同比逐月标准差 {CAL["std_mom"]:.1f}pp、'
                      f'{Y.TTM_WIN} 个月滚动 {CAL["std_ttm"]:.1f}pp，'
                      f'相邻月跳变中位 {CAL["medjump_mom"]:.1f}pp vs {CAL["medjump_ttm"]:.1f}pp，'
                      f'窗口内两者<b>符号相反的月份 {CAL["opposite_n"]} 个</b>'
                      + ('（' + '；'.join(f'{m} 单月 {a:+.1f}% vs 滚动 {b:+.1f}%'
                                          for m, a, b in CAL['opposite'][:3]) + '）。'
                         if CAL['opposite_n'] else '。')
                      + f'当期并排：单月 {sgn(float(ds.yoy.iloc[-1]))}、滚动 '
                        f'{sgn(float(ds.yoy_ttm.iloc[-1]))}。'
                      + _boundary_note(want_from, str(w.months[0]), w.n,
                                       '单月同比要 12 个月的 lag，两条线在窗口首年都没有分母',
                                       'lines_endlabels')
                      + w.why)}
        d['note'] += lay(d)
        push('fx_lines', d, w.months)

    # ── Ex6：汇率贡献（grouped_bars，柱容忍 null 但前导空柱没意义 → 截到首个有值）──
    if 'fx_contrib' in EX:
        fc_yoy_all = Y.mom_yoy(ds.fx_contrib, Y.RATIO)
        w = Window(ds, i_x, 'grouped_bars', [
            mrwin.Leg('bar', '汇率贡献柱', ds.fx_contrib.values, 'primary',
                      '柱本身是两条单月同比之差，要 12 个月 lag'),
            mrwin.Leg('yoy', '右轴那条「贡献的同比」', fc_yoy_all.values, 'derived',
                      '柱本身先要 12 个月（单月同比），再比一年 = 24 个月历史')])
        fcd = ds.fx_contrib.iloc[w.i0:]
        # 柱本身已是比率之差，它的同比同样取百分点差（RATIO），不是 (a/b−1)。
        fcd_yoy = fc_yoy_all.iloc[w.i0:]
        lag = w.why
        d = {'kind': 'grouped_bars',
             'title': 'Currency contribution to reported growth（单月同比之差 / single-month）',
             'xlabels': w.labels, 'xrot': 90,
             'groups': [{'name': 'Currency contribution', 'color': 'BLUE',
                         'values': L(fcd.values)}],
             'line': {'name': 'y/y change (pp, RHS)', 'color': 'GOLD',
                      'values': L(fcd_yoy.values), 'yfmt': 'pp0'},
             # 并排柱的同 x 多标签用步长抽不掉（引擎的 thinLabels 只对「一个 x 一个标签」
             # 的图型生效），窗口一长必然连成一串，所以柱顶不逐根标数值。
             'bar_labels': False, 'fmt': 'pp1', 'label_fmt': 'pp1',
             'ylab': 'pp of y/y', 'ylab2': 'pp y/y',
             'src_extra': (f'{legs(spec)["loc_sym"]} y/y less US$ y/y. '
                           f'Positive = a weaker {legs(spec)["loc_sym"]} '
                           'flattered the reported number. '
                           + spec['fx'].get('assumption', '')),
             'note': (f'本图是 {R("fx_lines")} 两条线之差，单位是百分点，不是百分比；'
                      '<b>两条线都是单月同比，所以本图也是单月口径</b>'
                      f'（与 {R("rev_bar")} 右轴的 {Y.TTM_WIN} 个月滚动口径不可直接对读）。'
                      '右轴金线是柱本身的同比 —— 柱已是比率之差，'
                      '所以它的同比同样取<b>百分点差</b>（当月贡献 − 去年同月贡献），'
                      f'读作「汇率这条腿比一年前多贡献/少贡献了几个点」'
                      f'（本月 {sgn(float(fcd_yoy.iloc[-1]), 1, "pp")}）。'
                      '柱顶不逐根标数值：长窗口下 band 只有几个像素，'
                      '而「+10.6pp」这样的标签就有 22px 宽，全标必然叠字；'
                      '逐月读数请点右上角「表格」，或把鼠标停在任意一列上。'
                      '柱用单组 <code>grouped_bars</code> 而不是 <code>gs_bar</code>：'
                      '后者纵轴强制自 0 起，会把负的贡献柱画到画布外。'
                      # ⚠️ 这句**必须条件化**：原来无条件印「这里显式截断」，
                      # 但只有序列起点晚到「窗口首年算不出贡献」的家才真的截过。
                      # 世芯 alchip 的序列自 2014-01 起，比窗口早两年多，
                      # 127 格柱一个 null 都没有、2016 年的贡献全都算得出来并画了出来 ——
                      # 页面却自称截断过，是一句关于本图的假话。
                      # 判据用「柱的首期是不是晚于本页窗口起点」，不是硬写。
                      + (f'柱自 {w.months[0]} 起（单月同比要 12 个月 lag，'
                         f'窗口首年算不出贡献，这里显式截断而不是画一排空柱）。'
                         if w.trim > 0 else
                         f'柱自 {w.months[0]} 起，与本页其余短窗口图同起点：'
                         f'本序列早于窗口起点 12 个月以上，首年的贡献算得出来，没有截断。')
                      + lag)}
        d['note'] += lay(d)
        push('fx_contrib', d, w.months)

    # ── Ex7：全历史 ─────────────────────────────────────────────────────────
    if 'hist' in EX:
        series = [{'name': f'Monthly revenue ({lab_bn})', 'color': 'NAVY',
                   'values': L(ds.disp.values)}]
        seg_colors = ['MBLUE', 'GOLD', 'GREEN', 'GRAY']
        for k, (sd, ss) in enumerate(ds.segments):
            series.append({'name': f'{sd["label"]} ({lab_bn})',
                           'color': seg_colors[k % len(seg_colors)],
                           'values': L((ss / div).values)})
        d = {'kind': 'lines', 'full': True, 'height': 300, 'x': 'long',
             'title': f'Full monthly revenue history since {ALL[0].year}',
             'fmt': 'f0', 'ylab': lab_bn, 'xstep': 9, 'xrot': 90,
             'zero_base': True, 'end_label': True, 'series': series,
             'src_extra': f'Full disclosed history since {mlab(ALL[0])}（共 {len(ALL)} 个月）。',
             'note': ('纵轴自 0 起（<code>zero_base</code>），所以看得出的是量级台阶'
                      f'而不是月度噪音；月度波动请看 {R("rev_bar")}。'
                      '末点加粗标出最新一个月的读数 —— 长历史图上刻度间隔上百，'
                      '这是全图唯一的绝对水平锚点。'
                      + (('分部线与合并线同图：合并 = 各分部之和，'
                          f'最新月各分部占合并 '
                          + '、'.join(
                              f'{sd["label"]} {float(ss.iloc[-1]) / float(ds.rev.iloc[-1]) * 100:.1f}%'
                              for sd, ss in ds.segments) + '。')
                         if ds.segments else ''))}
        push('hist', d, ALL)

    # ── Ex8：汇率 ───────────────────────────────────────────────────────────
    if 'fx_rate' in EX:
        u = spec['fx']['usd_share_note']
        LG = legs(spec)
        # 汇率线的身份跟着 fx.implied 走：外部牌价（推导那条腿用的）是「月均」，
        # 而 implied=False 的家用的是公司**自己申报**的换算汇率 —— 它就来自月营收公告
        # 本身，「本图与月营收公告无关」在它身上是假话。
        _rk = 'monthly average' if LG['implied'] else 'as filed'
        _rk_s = 'monthly avg.' if LG['implied'] else 'as filed'
        _rk_zh = ('本图与月营收公告无关。' if LG['implied'] else
                  '本图的汇率是公司随月营收公告一并申报的换算汇率，'
                  '与页内两条营收腿同源、由官方恒等式绑定，不是外部牌价。')
        d = {'kind': 'lines', 'full': True, 'height': 300, 'x': 'long',
             'title': f'{spec["fx"]["quote"]}, {_rk}',
             'fmt': 'f1', 'ylab': spec['fx']['quote'], 'xstep': 9, 'xrot': 90,
             'end_label': True,
             'series': [{'name': f'{spec["fx"]["quote"]} ({_rk_s})', 'color': 'NAVY',
                         'values': L(ds.fx.values)}],
             'src_extra': (_rk_zh + 'Exhibit source: ' + spec['fx']['src']
                           + '. ' + u['en']),
             'note': ('纵轴按数据范围自适应，未自 0 起 —— 汇率的绝对水平压在 0 起点的轴上'
                      '会变成一条直线，看不出近年的急升。'
                      '正因为轴不自 0 起，末点的绝对读数已标出，免得只能靠刻度目测水平。'
                      # 只画汇率线、不画美元腿的家：这张图与本家的披露无关，说清楚，
                      # 免得读者以为页面在暗示某条美元营收线被藏起来了。
                      + ('' if usd_leg_shown(EX) else
                         '<b>本图画的是汇率本身，不是本家的任何营收量</b> —— 它是一条'
                         '宏观序列，本站挂了同一份汇率的每一页上逐点相同，公司披不披露'
                         '美元营收与它无关。本页没有「本币 vs 美元」「汇率贡献」两张图，'
                         '理由见页尾对应的<b>本页不出「…」那张图</b>条目；页上任何一处'
                         '都不会出现拿本币除以这条汇率折出来、冒充官方值的美元营收线。'))}
        push('fx_rate', d, ALL)

    # ── Ex9：热力矩阵（口径由 window.heat_metric 定，默认单月同比，见 §1.6）───
    if 'heat' in EX:
        NH = int(spec['window'].get('heat_years', 9))
        TX = HM                                  # = _HEAT_TXT[HM_KEY]
        hv = heat_values(ds, HM_KEY)
        matrix, hyrs = heat_matrix_of(hv, NH)
        n_zero = sum(1 for row in matrix for x in row if x == 0)

        # 「格内那个数是哪来的」跟着口径走：只有单月同比这一种可能取自公司公告的原值，
        # 环比在本仓的任何一份 series 里都没有登记列，一定是本脚本自算的。
        if HM_KEY == 'mom':
            src_zh = ('本脚本按序列自算的环比（当月 ÷ 上月 − 1）'
                      f'—— series/{spec["csv"]} 里只有水平值，环比与同比都由它派生')
        else:
            src_zh = ('公司随月营收公告的 y/y 原值（'
                      f'series/{spec["csv"]} 的 {spec["official_yoy"]}）'
                      if spec.get('official_yoy') else
                      '本脚本按序列自算的单月同比（<code>build/yoy.py</code>，'
                      f'series/{spec["csv"]} 里没有登记 y/y 列）')
            src_zh += '，再取 100×ln(1+g)' if HM_KEY == 'log_yoy' else ''

        # ⚠️ 这一段里凡是要点名别的图，都先问 EX 有没有那张 —— 直接 R('mom') 在跳掉
        #    环比线的家身上就是一个 KeyError（本轮修的正是这一类耦合）。
        _vs_mom = ('本表与逐月的环比线（' + R('mom') + '）是同一个量的两种排布：'
                   '那张按时间轴看趋势，本表按「年 × 月」摆开看季节位置'
                   '（同一列上下比，就是同一个日历月在不同年份的强弱）。'
                   if HM_KEY == 'mom' and 'mom' in EX else '')

        # ── 色阶实测：**拿刚刚建好的这张 matrix 算**，不是拿全序列算。三个口径在同一段
        #    窗口上各算一遍，好让「为什么用这个口径」有数撑着，而不是一句形容词。
        #    算不出来（格子太少）就整段不写，不退回写死的数。
        crowd = heat_crowding(matrix)
        alts = {}
        _keep = set(hyrs)
        for k in _HEAT_TXT:
            if k == HM_KEY:
                continue
            _m, _y = heat_matrix_of(heat_values(ds, k), NH)
            # 只留本表实际画出来的那几个年份 —— 三个口径的首个有值年可能差一年
            # （同比要 12 个月历史、环比只要 1 个），不对齐就不是「同一段窗口」了。
            c_k = heat_crowding([r for r, y in zip(_m, _y) if y in _keep])
            if c_k:
                alts[k] = c_k
        if crowd:
            _sh = crowd['share']
            verdict = ('⇒ 色阶铺得开，颜色排序可以直接读。' if _sh < 25 else
                       '⇒ 矩阵照出，但<b>请按格内数字读，不要只看颜色排序</b>。'
                       if _sh < 50 else
                       '⇒ <b>这张表的颜色几乎不携带信息，请只读格内数字。</b>')
            cmp_zh = ''
            if alts:
                _o = '；'.join(f'{_HEAT_TXT[k]["zh"]} {c["dull"]} 格（{c["share"]:.0f}%）'
                              for k, c in sorted(alts.items()))
                _best, _bc = min(list(alts.items()) + [(HM_KEY, crowd)],
                                 key=lambda kv: kv[1]['share'])
                # 「换个口径会不会更好读」只在差距**大到不是噪声**时才提。百来个格子上
                # 的色带占比本身有几个百分点的抖动，拿 33% vs 31% 去建议换口径，是把
                # 噪声说成结论 —— 而换口径要连带改标题、图注与页尾点名条，不是免费的。
                _MAT = 10.0                      # 百分点，材料性差距的门槛
                _gap = _sh - _bc['share']
                cmp_zh = (f'同一段窗口下另外两个口径实测：{_o}。'
                          + ('本表用的就是三者里最铺得开的那一个。' if _best == HM_KEY else
                             f'铺得最开的是{_HEAT_TXT[_best]["zh"]}'
                             f'（{_bc["share"]:.0f}%），比本表少 {_gap:.0f} 个百分点 —— '
                             '要换就把该家 spec 的 <code>window.heat_metric</code> 改成 '
                             f'<code>{_best}</code>，标题、本段与页尾的口径点名条会自己'
                             '跟着改。' if _gap >= _MAT else
                             f'铺得最开的是{_HEAT_TXT[_best]["zh"]}'
                             f'（{_bc["share"]:.0f}%），也只比本表少 {_gap:.0f} 个百分点，'
                             '属于同一档 —— 这点差距在百来个格子上是抖动不是结论，'
                             '换口径解决不了任何问题，本表照旧。'))
            crowd_zh = (
                '<b>这张表的色阶读不读得出来 —— 本段现算，不是写死的话。</b>'
                '引擎的色标是<b>线性</b>的（<code>assets/charts.js</code> 的 '
                '<code>heatScale</code>：t =（v − p5）/（p95 − p5），红→白→绿线性插值，'
                '<b>没有 log 入口</b>），而且<b>色阶与格内数字读同一份 matrix</b> —— '
                '「色阶取对数、格内印原值」在结构上做不到（引擎只有 <code>matrix</code> / '
                '<code>reverse</code> 两个入口）。所以读不读得出来只取决于这些格子在 t 轴上'
                f'摊不摊得开：本表 <b>{crowd["n"]} 格</b>实测跨 '
                f'{crowd["lo"]:+.0f} ~ {crowd["hi"]:+.0f}{TX["unit"]}、'
                f'p5/p95 = {crowd["p5"]:+.0f} / {crowd["p95"]:+.0f}{TX["unit"]}，'
                f'最宽 20% 的色带里塞了 <b>{crowd["dull"]} 格（{_sh:.0f}%）</b>—— '
                '它们彼此色差不到两成、肉眼分不开。' + verdict + cmp_zh
                + f'这几个数在构建期从<b>本表实际用的那张 matrix</b> 现算（{NH} 年 × 12 '
                  '列），不是从全序列算的 —— 引擎的 5/95 分位只看 matrix，拿全序列算出来'
                  '的分位读者照着核会对不上。')
        else:
            crowd_zh = ('（本表有限格不足 8 个，算不出可信的分位与拥挤度，'
                        '故本段不给实测数。）')

        d = {'kind': 'heat_matrix', 'full': True,
             'title': TX['title'],
             'rows': [str(y) for y in hyrs], 'cols': MONTHS, 'matrix': matrix,
             'fmt': 'f0', 'legend': TX['legend'], 'row_head': '年', 'cell_h': 21,
             'src_extra': TX['src_en'],
             # 换过口径的家：口径声明排在最前面 —— 这张图会被单独截图转发，
             # 「它不是同比」必须跟着图走，不能只写在页尾。
             'note': (TX['caliber'] + _vs_mom
                      + f'格内是{src_zh}，空格是尚未公布的月份。'
                      + '数值四舍五入到整数；' + TX['zero'] + ' 的月份一律写 0，不写「−0」'
                      + f'（本表命中 {n_zero} 格）。'
                      + crowd_zh
                      + 'heat_matrix 没有连续横轴，因此不画断点竖线；'
                        '本页登记的断点见页尾「口径断点与截轴」一条。')}
        # ⚠️ **不走 push()**：push() 无条件调 apply_breaks()，而 apply_breaks() 干两件事 ——
        #    往 payload 塞 `break_at`（99 个月轴上的下标，这张 8×12 的矩阵根本没有那条轴），
        #    并把「本图上的红色竖虚线是口径断点……」接到本图图注上，正好顶撞上一句
        #    「heat_matrix 没有连续横轴，因此不画断点竖线」；页尾那条现读 payload 生成的
        #    清单也会跟着把本图列进「已画成红色竖虚线」。
        #    画面一直是对的（assets/charts.js 的 drawHeat() 在读 break_at 之前就 return），
        #    错的是 payload 与文字 —— 与本轮已修的「Ex3 payload 里躺着一个 1 个月比 3 个月的数」
        #    同类：引擎兜住了，数却留在 payload 里等着被表格视图或别的读者读走。
        #    tsm 的 breaks 为空，走不到这条分支，所以三道闸门全绿也照样漏；
        #    日月光 / 联电 / 联发科 / 南亚科都有 breaks，都会踩到。
        d['n'] = EX['heat']
        ex.append(d)

    # ── 版面收口：两列网格里不许留「孤零零的半栏卡」──────────────────────
    #    `full` 是按点数逐图判的，判完之后同一页里通栏与半栏交替出现，
    #    夹在两张通栏之间的半栏卡会独占一整行的左半边、右半边整片空白
    #    （实测：Ex2/4/5/6 升通栏之后，43 个季度的 Ex3 正好落进这个坑，
    #     1280px 下卡片 571px、右侧 600px 全白）。这是**版面**问题不是数据问题，
    #    所以在这里按 CSS 的两列网格模拟一遍摆放，把落单的那张一并升通栏。
    # ── spec 的逐图补注（note_extra）：追加到那一张图自己的图注末尾。
    #    放在这里而不是各图内部，是为了让「哪一张图能补注」由 EX 一处决定：
    #    图没出（跳过 / 没有汇率腿）时补注也不会凭空掉到别的图上。
    _by_n = {n: s for s, n in EX.items()}
    for e in ex:
        _x = (spec.get('note_extra') or {}).get(_by_n.get(e.get('n')))
        if _x:
            e['note'] = (e.get('note') or '') + _x

    _pack_full(ex)
    return ex, EX, ctx


def _pack_full(ex):
    """模拟 `.grid { grid-template-columns: repeat(2, 1fr) }` 的摆放，落单的半栏升通栏。"""
    col, pending = 0, None
    for e in ex:
        if e.get('full'):
            if pending is not None:
                _promote(ex[pending])
            col, pending = 0, None
            continue
        if col == 0:
            col, pending = 1, ex.index(e)
        else:
            col, pending = 0, None
    if pending is not None:
        _promote(ex[pending])


def _promote(e):
    e['full'] = True
    e['note'] = (e.get('note') or '') + (
        '本图的 band 本来放得下半栏，但它在两列网格里夹在两张通栏卡之间、'
        '会独占一整行的左半边而右半边全白，所以一并升为通栏 —— '
        '这是版面收口，与数据无关。')


# ══════════════════════════════════════════════════════════════════════════════
# §8 页尾说明
# ══════════════════════════════════════════════════════════════════════════════
def build_notes(ds, spec, ex, EX, ctx, blanked):
    v = spec['value']
    cur = ds.all[-1]
    R = lambda s: f'Exhibit {EX[s]}'
    has = lambda s: s in EX

    # ── 断点与截轴：**整段**由 payload + spec 生成。
    #    底座绝不替任何一家断言「未发生并表或重述」—— 那句话在至少四家上是假话。
    brk = load_breaks(spec)
    drawn = ctx['brk_drawn']
    _CAP = [str(e['n']) for e in ex if e.get('ycap') is not None or e.get('yfloor') is not None]
    if brk:
        where = '；'.join(
            # 按 **Exhibit 编号** 排，不按 slug 的字母序 —— 后者会把这份清单写成
            # 「Exhibit 5、Exhibit 4、Exhibit 3、Exhibit 2」（hist < mom < qtr < rev_bar），
            # 读者要在页尾核对时逐条回跳，顺序乱掉毫无道理。
            f'{R(s)} 上 {"、".join(d["month"] for d in hits)}'
            for s, hits in sorted(drawn.items(), key=lambda kv: EX[kv[0]]))
        blist = '、'.join(f'{d["month"]}（{d["zh"]}）' for d in brk)
        brk_note = (f'⚠️ <b>口径断点与截轴</b>：本页 spec 登记了 {len(brk)} 个口径断点：{blist}。'
                    + (f'落在各图窗口内、且不在第 0 格的已画成 <code>break_at</code> 红色竖虚线：'
                       f'{where}。' if drawn else
                       '本轮没有一个落进任何一张图的窗口（或恰好落在第 0 格，'
                       '左缘就是画布边线、读不出来），所以图上看不到红线 —— '
                       '这不是漏画。')
                    + '断点线的语义是「从这一期起与左侧不可比」，画在该期的左缘；'
                      'heat_matrix 没有连续横轴，不画断点线。')
    else:
        # 「没有登记断点」与「历史上没发生过并表或重述」是两句话，页面必须分得开。
        # 前者是本页 spec 的状态（底座读得到），后者是关于公司历史的事实断言
        # （底座读不到，只能由 spec 带出处给出）。原来的 build/tsm.py 把后者写死在底座里，
        # 那句话搬到联电（2019-10 USJC 并表、2015-06 新事业退出合并）就是假话。
        c = spec.get('continuity')
        brk_note = ('⚠️ <b>口径断点与截轴</b>：本页 spec 未登记任何口径断点，'
                    '因此没有 <code>break_at</code> 红色竖虚线。'
                    '<b>「没有登记」不等于「历史上没发生过并表或重述」</b>：'
                    '后者是一句需要出处的事实断言，'
                    + (f'本页给出的出处是{c["zh"]}（{c["url"]}）。' if c else
                       'spec 没有给出处，所以本页<b>不做</b>这个断言 —— '
                       '要判断可比性，请自行核对该公司年报的合并范围附注。'))
    brk_note += ('，' if brk_note.endswith('。') is False else '')
    brk_note += (('本页也没有 <code>ycap</code>／<code>yfloor</code> 截轴。'
                  if not _CAP else
                  f'另有 Exhibit {"、".join(_CAP)} 设了 <code>ycap</code>／<code>yfloor</code> 截轴。')
                 + '这一段由本页 payload 现读生成，不是写死的说明文字 —— '
                   '哪天真加了断点或截轴，它会自己改口，'
                   '所以本页不会出现「图注说画了断点线、图上其实没有」这种自相矛盾。')
    if 'qtr_align' in ctx and ctx['qtr_align']:
        a = ctx['qtr_align']
        brk_note += (f'（{R("qtr")} 左轴向下扩到负区是双轴零点对齐的结果，不是截轴：'
                     '没有任何点被截掉。）' if a['aligned'] else
                     f'（{R("qtr")} 的两轴零点<b>没有</b>对齐：对齐要把左轴一路扩到 '
                     f'{a["alo"]:,.0f}、浪费掉 {a["waste"]:.0%} 量程，超过引擎兜底阈值，'
                     '故两轴各自缩放，引擎已在绘图区左上角标出 —— 这同样不是截轴。）')

    # ── 同比口径点名条（CONTRACT §6）
    #
    # ⚠️ 季度桥**不属于**单月同比，不许放进 single 里。
    # 原来它是 single 的第一项，于是渲染出来是「**单月同比**（当月 ÷ 去年同月 − 1）用在
    # Exhibit 3（季度口径，3 个月比 3 个月）…」—— 一句话里先定义单月、再点名一张
    # 3 个月比 3 个月的图，自相矛盾，而这恰恰是 §6.3 第 3 条要求「可核对」的那条点名。
    # 该错误曾复制到全部 7 页（只有 nanya 的 spec 自己加了一句更正）。
    # 本页存在的同比口径最多三种，各自点名：滚动 / 单月 / 季度。
    quarterly = f'<b>{R("qtr")}</b>（当季 3 个月合计 ÷ 去年同季 3 个月合计 − 1）' if has('qtr') else ''
    single = []
    if has('fx_lines'):
        single.append(f'<b>{R("fx_lines")}</b>（本币与美元两条线）')
    if has('fx_contrib'):
        single.append(f'<b>{R("fx_contrib")}</b>（两者之差，取百分点）')
    # 热力矩阵归哪一类由 `window.heat_metric` 定（§1.6）：'yoy' / 'log_yoy' 是单月同比
    # （后者只是取了对数，单调变换，仍然是同比）；'mom' 根本不是同比，硬塞进「单月同比
    # 用在……」那句话里就是一句假话 —— 与本轮已修的「季度桥被列进单月同比」同类错。
    # 换了口径的矩阵改由下面的 mom_named 单独点名（不点名，读者会默认它是单月同比，
    # 本仓的矩阵确实大多是）。
    HTX = ctx['heat_txt']
    mom_named = ''
    if has('heat'):
        if ctx['heat_is_single_yoy']:
            single.append(f'<b>{R("heat")}</b> 热力矩阵' + HTX['named_extra'])
        else:
            _mm = ([f'<b>{R("mom")}</b>'] if has('mom') else []) \
                + [f'<b>{R("heat")}</b> 热力矩阵']
            mom_named = ('<b>环比（m/m，当月 ÷ 上月 − 1）</b>用在 ' + '、'.join(_mm)
                         + '，以及汇总表的 m/m 列 —— <b>它既不是同比也不是滚动</b>，'
                         '不要与上面两种口径并排读。本页的热力矩阵改用环比是口径判断，'
                         f'理由（含本表实测的色阶拥挤度）写在 {R("heat")} 自己的图注里。')
    cur_yoy = float(ds.yoy.iloc[-1])
    cur_ttm = float(ds.yoy_ttm.iloc[-1])

    notes = []
    notes.append('<b>数据源</b>：主线是' + spec['source_zh'] + '。'
                 + ('除 ' + R('fx_rate') + ' 外，' if has('fx_rate') else '')
                 + '本页各图与两张表全部由这一个字段'
                 # 「月均」只对拿外部牌价折推导腿的家成立；implied=False 的家用的是
                 # 公司自己申报的换算汇率，叫它「月均汇率序列」是错的。
                 # 判据是 fx_used(EX)（§1.5）而不是 ds.fx：挂了 fx 却一张汇率图都不出的
                 # spec（三张全 skip）身上，「本页由这一个字段加一条汇率序列派生」是假话
                 # —— 那条序列一格都没进过页面。
                 + (('加一条月均汇率序列' if legs(spec)['implied'] else '加一条官方申报的换算汇率序列')
                    if fx_used(EX) else '')
                 + '派生，不引入任何券商预测或外部估计。'
                 + (f'例外的那一张在图脚第二行写明了自己的来源：{R("fx_rate")} 来自 '
                    + spec['fx']['src'] + '。' if has('fx_rate') else ''))
    notes.append('<b>版式出处</b>：' + spec['format_source'])
    notes.append(
        '<b>同比口径：本页并存两种，逐处点名</b>（CONTRACT.md §6 要求）。'
        f'<b>{Y.TTM_WIN} 个月滚动合计同比</b>只有一处 —— <b>{R("rev_bar")}</b> 的右轴金线'
        f'（最近 {Y.TTM_WIN} 个月营收合计 ÷ 上一个 {Y.TTM_WIN} 个月合计 − 1）；'
        '营收是流量、可加总，这个「合计」指代的是真实的一年营收，所以对它合法。'
        + ('<b>单月同比</b>（当月 ÷ 去年同月 − 1）用在 '
           + ('、'.join(single) + '，' if single else '')
           + '汇总表与核对表的 y/y 列，以及页顶 brief 里标明「单月」的读数。')
        + (f'<b>季度同比</b>只有一处 —— {quarterly}，'
           '它既不是单月也不是滚动，当季未满 3 个月时不画。' if quarterly else '')
        + mom_named
        + f'两种口径的当期读数并排在这里，省得跨图对：{mlab(cur)} 单月 {sgn(cur_yoy)}、'
          f'{Y.TTM_WIN} 个月滚动 {sgn(cur_ttm)}，差 {sgn(cur_yoy - cur_ttm, 1, "pp")}。')

    if spec.get('official_yoy'):
        d = (ds.official_yoy - ds.yoy_self).dropna().abs()
        notes.append(
            '<b>单月 y/y 有两个来源，数值上几乎重合</b>：'
            # 「热力矩阵用公告原值」只在矩阵画的就是单月同比时成立；换成环比之后它一格
            # 都不碰 official_yoy，这句话就得把它去掉（判据同 §1.6）。
            + ('热力矩阵与核对表' if ctx['heat_is_single_yoy'] else '核对表')
            + '用公司随公告'
            f'给出的 <code>{spec["official_yoy"]}</code> 原值；其余由本脚本按序列自算'
            '（口径实现统一走 <code>build/yoy.py</code>，本页不再自己写 '
            '<code>pct_change(12)</code>）。'
            f'两者在 {len(d)} 个可比月份上最大差 {float(d.max()):.2f}pp、'
            f'中位差 {float(d.median()):.2f}pp，来自公司口径的四舍五入，未做人工对齐。')
    else:
        # ⚠️「本页 spec 没登记」≠「公司没披露」。后者是一句关于该公司公告内容的**事实
        #    断言**，底座读不到（它只看得见 series/ 里有没有这一列）。世芯 3661 的 MOPS
        #    月营收表逐月印「增減百分比」两栏，只是没落进 CSV —— 旧措辞在它身上是假话。
        #    这与 continuity 的规矩是同一条：状态陈述与事实断言不许混为一谈。
        notes.append('<b>单月 y/y 全部由本脚本自算</b>（<code>build/yoy.py</code>）：'
                     '本页 spec 未登记 <code>official_yoy</code> 列'
                     f'（<code>series/{spec["csv"]}</code> 里没有这一列），'
                     '所以页内没有「公司原值 vs 自算值」的分歧。'
                     '<b>「本页没登记」不等于「公司没披露」</b>：后者是一句关于该公司'
                     '公告内容的事实断言，底座读不到，要说请由该家 spec 带出处来说。')

    # ── 货币腿这一段分**三种**页面形态，判据全在 §1.5 的两个函数上。
    #    原来只有两支（`ds.fx is not None` 与 else），于是「挂了 fx 只画汇率线」的家会走
    #    进第一支，撞上两处 R('fx_contrib') —— 那张图不在 EX 里，直接 KeyError。
    #    这不是「少一句话」，是整条构建挂掉。
    #      ① usd_leg_shown(EX)        —— 页上有美元腿：讲恒等式与汇率贡献
    #      ② fx_used(EX) 而无美元腿   —— 只画汇率线本身（Ex8）：讲清它是宏观序列
    #      ③ 都没有                   —— 页上一点汇率都没有
    _fx_contrib_txt = (f'汇率贡献（{R("fx_contrib")}）' if has('fx_contrib')
                       else '汇率贡献')       # 那张图没出就不点编号，只留概念名
    if usd_leg_shown(EX):
        u = spec['fx']['usd_share_note']
        LG = legs(spec)
        if LG['implied']:
            notes.append('<b>美元口径全部是推导值（Implied）</b>：'
                         f'US$ 营收 = {LG["loc_zh"]}营收 ÷ 当月平均汇率。'
                         '假设全部营收按当月平均汇率一次性折算，忽略月内汇率路径、对冲与递延收款。'
                         f'{_fx_contrib_txt}= {LG["loc_zh"]} y/y '
                         '− US$ y/y，单位是百分点。')
        else:
            notes.append('<b>本页两条货币腿都是官方申报值，没有一条是折出来的</b>：'
                         '公司的功能货币就是主序列那一种，'
                         f'{LG["loc_zh"]}栏由官方恒等式'
                         f'「{LG["loc_zh"]}营收 ≡ 功能货币营收 × 本月換算匯率」'
                         '逐月折算得到，換算匯率本身也是官方申报的格子，'
                         '不是 H.10 / FRED / 台银牌价。'
                         f'{_fx_contrib_txt}= {LG["loc_zh"]} y/y '
                         '− US$ y/y，单位是百分点 —— 它是这个恒等式的代数重排，'
                         f'读作「以{LG["loc_zh"]}计的那个头条数被汇率抬高/压低了多少」，'
                         '<b>不是公司受到的汇率冲击</b>（真正的暴露在成本端与对冲上，'
                         '月营收公告看不到）。')
        # ⚠️「外币计价占比」逐家不同，**不许继承**：per-ticker + 出处。
        notes.append(f'<b>汇率序列口径</b>：{spec["fx"]["src"]}。'
                     f'{u["zh"]}（出处：{u["src"]}）。')
    elif fx_used(EX):
        # ② 挂了 fx、但美元腿那两张图被显式跳掉：页上只有汇率线本身。
        #    这一支必须存在 —— 走上面那一支会 KeyError（R('fx_contrib') 查不到），
        #    走下面那一支则会说「本页没有汇率线」，而 Ex8 就在页上。
        #    它要说清楚的正是**这一页不是什么**：没有任何一处美元营收数字。
        u = spec['fx']['usd_share_note']
        notes.append(
            '<b>本页有汇率线，但没有美元营收腿</b>：'
            + (f'{R("fx_rate")} 画的是<b>汇率本身</b>，' if has('fx_rate') else
               '本页用到的汇率序列画的是<b>汇率本身</b>，')
            + '一条宏观序列 —— 挂同一份汇率的每一页上它逐点相同，与本公司披露什么无关。'
              '页上<b>没有</b>「本币 vs 美元」与「汇率贡献」两张图，也没有任何一处'
              '「美元营收」的数字（抬头、页顶 brief、核对表都没有）：那要拿本币除以这条'
              '外部牌价折出来，得到的是<b>分析师构造值</b>、不是公司披露值，'
              '没有任何官方数可以对账。'
              '两张图不出的逐条理由见页尾「本页不出「fx_lines」/「fx_contrib」那张图」。'
            + f'<b>那这条线为什么还在页上</b>：{u["zh"]}（出处：{u["src"]}）—— '
              '本币计价的报表被一条外币汇率推着走，这件事不需要公司披露美元营收也成立，'
              '所以汇率该画，折出来的美元营收不该画。')
        notes.append(f'<b>汇率序列口径</b>：{spec["fx"]["src"]}。')
    else:
        # ③ 同上：旧措辞把「本页没登记 fx」写成了「公司没披露官方美元实绩」。
        # 在 ccy_zh='美元' 的家（功能货币是美元）上它还会自相矛盾：
        # 「月度公告只有美元，没有官方美元实绩」。
        notes.append('<b>本页没有美元折算腿</b>：本页 spec 未登记 <code>fx</code>。'
                     '<b>「本页没登记」不等于「公司没披露官方外币实绩」</b> —— '
                     '后者是一句关于该公司公告内容的事实断言，底座读不到，'
                     '要说请由该家 spec 带出处来说。'
                     '拿本币除以外部牌价折一条「美元营收」出来，得到的是分析师构造值、'
                     '不是公司披露值，页上任何一处都不会出现那种冒充官方值的线，'
                     f'因此本页整体没有「本币 vs 美元」「汇率贡献」「月均汇率」这三张图。')

    if ds.alt is not None:
        a = spec['alt']
        notes.append(f'<b>{a["zh"]} 只出现在核对表，且不参与任何加总</b>：{a["note_zh"]}')

    if ds.segments:
        notes.append('<b>分部口径</b>：' + '；'.join(
            f'{sd["label"]} 最新月占合并 '
            f'{float(ss.iloc[-1]) / float(ds.rev.iloc[-1]) * 100:.1f}%、'
            f'近 12 个月占 {float(ss.iloc[-12:].sum()) / float(ds.rev.iloc[-12:].sum()) * 100:.1f}%'
            for sd, ss in ds.segments)
            + '。合并数含全部分部，跨家比「营收增速」之前先看这个构成。')

    if has('qtr'):
        notes.append(f'<b>未满季提示</b>：{R("qtr")} 的末季不足 3 个月时会画成浅蓝柱，'
                     '且右轴 y/y 会被图表引擎强制作废 —— 拿 2 个月累计去比上年完整 3 个月'
                     f'必然砸出一个假坑。本期 {ctx["cur_q"]} 已含 {ctx["n_in_last"]} 个月，'
                     + ('为完整季度，无此标记。' if ctx['n_in_last'] >= 3 else '故末柱与末点按上述规则处理。'))

    # ── 本轮的窗口改造，逐图现算写清楚
    notes.append(_window_note(ds, spec, ex, EX, ctx))

    for slug, why in (spec.get('skip_note') or {}).items():
        notes.append(f'<b>本页不出「{slug}」那张图</b>：{why}')

    notes.append(brk_note)

    notes.append('<b>汇总表的分位与累计行</b>：「3Y %ile」= 当月读数在最近 36 个月中高于多少'
                 '百分比的观测，判据统一走 <code>build/pctile.py</code>（全站一份实现）：'
                 '把该行的分位在最近 24 个月里逐月回放，≥70% 的月份钉在 100 或 0 就说明'
                 '这一列对这一行没有区分度，留空。'
                 + (f'本页据此留空的是 <b>{"、".join(blanked)}</b>。' if blanked else
                    '本页本轮没有行触发该判据。')
                 + '另外，周期内累计的序列（QTD／YTD）的 <b>m/m 与分位两列一律留空</b>，'
                   '那是口径原因：分位由「本月是期内第几个月」决定，m/m 则只是'
                   '「上月累计 + 当月营收」的算术恒等式。这两行看 y/y。')

    notes += list(spec.get('notes') or [])
    return notes


def _window_note(ds, spec, ex, EX, ctx):
    """「短窗口图从哪一格起、为什么」的**总账**，逐图现算。

    这一条是本轮窗口改造的可核对入口：读者不必逐图去点开图注，就能看到
    「同一个页面窗口起点下，五张图各自的首点差了多少、差在哪个 lag 上」。
    """
    want = ctx['want_from']
    rows, nums = [], []
    for e in ex:
        if e.get('x') == 'long' or e['kind'] == 'heat_matrix':
            continue
        xl = e.get('xlabels') or []
        if not xl:
            continue
        nums.append(int(e['n']))
        rows.append(f'Exhibit {e["n"]}（{e["kind"]}）自 {xl[0]} 起，{len(xl)} 格')
    # 「Ex2–Ex6」这个范围原来是写死的：TSM 有汇率腿，短窗口图正好是 Ex2…Ex6，
    # 但没有汇率腿的家只有 Ex2–Ex4，写死的那一段就把两张长历史/矩阵图算了进去。
    span = (f'Ex{nums[0]}' if len(nums) == 1 else
            f'Ex{min(nums)}–Ex{max(nums)}') if nums else '短窗口'
    # 「拉到 X 起」只有在 spec 真给了一个短窗口起点时才是实话。`x_from` 显式 None 的家
    # （= 用序列自己的起点）没有任何一张图被「拉」过，写成「统一拉到」是把一个不存在的
    # 动作说成发生过；而窗口起点落在序列之前被 `_first_at_or_after()` 钳到序列首月的家，
    # 页面窗口起点与实际左端是两个数，也不该只印钳位后的那一个。
    x0 = spec['window'].get('x_from')
    if not x0:
        head = ('<b>短窗口图的起点与数据边界</b>：本页 <code>window.x_from</code> 显式为 '
                f'None —— 不设短窗口，{span} 的左端就是<b>本序列自己的起点 {want}</b>，'
                '没有任何一张图被截短过。')
    elif str(x0) != str(want):
        head = (f'<b>短窗口图的起点与数据边界</b>：本页 spec 要的窗口起点是 <b>{x0}</b>，'
                f'但本序列自 <b>{want}</b> 才有数，底座按「窗口起点落在序列之前就取序列首月」'
                '钳到了序列首月 —— 差出来的那一段不是被截掉的，那几个月本序列一格都没有。')
    else:
        head = (f'<b>短窗口图的起点与数据边界</b>：本页把 {span} 的时间轴统一拉到 '
                f'<b>{want}</b> 起。')
    return (head
            + '每张图**实际**能从哪一格起画由它自己的派生口径决定，不是一个常数：'
            + '；'.join(rows) + '。'
            '差出来的那几格全部是 lag，不是缺数：环比要 1 个月、单月同比要 12 个月、'
            f'{Y.TTM_WIN} 个月滚动合计同比要 {2 * Y.TTM_WIN} 个月、季度同比要 4 个季。'
            '处理方式按图型的 null 容忍度分两类（docs/CHART_KINDS.md §1.2）：'
            '<code>gs_line</code>／<code>lines_endlabels</code> 走 Catmull-Rom 平滑，'
            'null 会被当 0 画出一条塌到零的假线（首尾 null 还会抛 TypeError 让整页后续图全丢），'
            '所以**显式截断**；<code>gs_bar</code> 的右轴、<code>qtr_bar</code>／'
            '<code>grouped_bars</code> 的右轴走非平滑 polyline，前导 null 只是「笔还没落下」，'
            '所以**保留 null**、让派生线自己晚起，线比柱短几格已写进各自图注。'
            '<b>页上没有任何一处是往前补零、补去年同值或把首点拉平得来的。</b>')


# ══════════════════════════════════════════════════════════════════════════════
# §9 主流程
# ══════════════════════════════════════════════════════════════════════════════
def build(spec, out_dir=None, quiet=False):
    validate(spec)
    ds = DataSet(spec)
    v = spec['value']
    sym, div = v['sym'], float(v['div'])
    ALL = ds.all
    cur = ALL[-1]

    breaks = load_breaks(spec)
    summary, blanked = build_summary(ds, spec)
    ex, EX, ctx = build_exhibits(ds, spec, breaks)

    # 轴刻度收口**必须排在 notes 之前**：axisfmt 除了改格式器，还会给「柱图型出现负值」
    # 的图补 ycap/yfloor，而页尾那句「本页有没有截轴」是现读 payload 生成的。
    axisfmt.fix_all(ex)

    # ── 核对表（官方原始单位，未换算）
    T = int(spec['window'].get('check_rows', 13))
    cols = [[f'Consolidated revenue ({v["raw_label"]})', 'rev']]
    trows = []
    rdec = int(v.get('raw_dec', 0))
    for p in ALL[-T:]:
        r = {'xl': mlab(p), 'rev': f(ds.rev.get(p), rdec)}
        trows.append(r)
    if spec.get('official_yoy'):
        cols.append(['y/y (%) — as disclosed', 'yoy'])
        for r, p in zip(trows, ALL[-T:]):
            r['yoy'] = f(ds.official_yoy.get(p), 1)
    else:
        cols.append(['y/y (%) — computed', 'yoy'])
        for r, p in zip(trows, ALL[-T:]):
            r['yoy'] = f(ds.yoy_self.get(p), 1)
    if ds.alt is not None:
        a = spec['alt']
        cols.append([a['label'], 'alt'])
        for r, p in zip(trows, ALL[-T:]):
            r['alt'] = f(ds.alt.get(p), int(a.get('dec', 0)))
    for sd, ss in ds.segments:
        key = 'seg_' + sd['col']
        cols.append([f'{sd["label"]} ({v["raw_label"]})', key])
        for r, p in zip(trows, ALL[-T:]):
            r[key] = f(ss.get(p), rdec)
    # 汇率列跟着 fx_used(EX) 走（§1.5）：只画 Ex8 的家也该给出那条线最近 13 个月的逐月
    # 读数 —— 核对表的作用就是让图上的点能被逐格核对；三张汇率图全跳掉的 spec 则一列都
    # 不印（表里多一列页面上没有任何图用到的数，读者无从判断它是干什么的）。
    if fx_used(EX):
        LG = legs(spec)
        cols.append([f'{spec["fx"]["quote"]} '
                     f'({"monthly avg." if LG["implied"] else "as filed"})', 'fx'])
        # 「Implied revenue」只在外币腿**确实是我们折出来的、而且真的画在页上**时才有
        # 意义。两道判据缺一不可：
        #   · fx.local_col 给了的家（主序列本身就是官方外币栏）：那一列已经是本表第一
        #     列，再印一遍还冠上 Implied，等于把官方申报值说成推导值，还印两遍同一个数；
        #   · 美元腿两张图被跳掉的家（§1.5）：页上根本没有这条构造序列，核对表却逐月印
        #     13 个「Implied revenue」出来 —— 那是把一个页面明确拒绝画的量塞回表里，
        #     还落进 payload、会被表格视图和下游读走。
        _usd_col = (not LG['split']) and usd_leg_shown(EX)
        if _usd_col:
            cols.append([('Implied revenue (US$mn)' if LG['implied']
                          else 'Revenue (US$mn, as filed)'), 'usd'])
        for r, p in zip(trows, ALL[-T:]):
            r['fx'] = f(ds.fx.get(p), 4)
            if _usd_col:
                r['usd'] = f(ds.usd.get(p), 0)
    table = {'n': ctx['n_table'],
             'title': f'近 {T} 个月核对表（官方原始单位，未换算）',
             'idx': '月份', 'cols': cols, 'rows': trows}

    # ── 抬头
    cur_bn = float(ds.disp.iloc[-1])
    cur_yoy = float(ds.yoy.iloc[-1])
    cur_mom = float(ds.mom.iloc[-1])
    cur_q = ds.qsum.index[-1]
    cur_q_bn = float(ds.qsum.iloc[-1])
    n_in_last = int(ds.qcnt.iloc[-1])
    # 抬头的当季 y/y 必须与汇总表 Quarter-to-date 行同口径：当季已公布的 n 个月，
    # 比上年同季的**同样前 n 个月**。
    q_now = float(ds.qtd.get(cur, np.nan))
    q_yag = float(ds.qtd.get(cur - 12, np.nan))
    cur_q_yoy = (q_now / q_yag - 1) * 100 if np.isfinite(q_yag) and q_yag else float('nan')
    ytd_now = float(ds.ytd.iloc[-1])
    ytd_prev = float(ds.ytd.get(cur - 12, np.nan))
    ytd_yoy = (ytd_now / ytd_prev - 1) * 100 if np.isfinite(ytd_prev) and ytd_prev else float('nan')

    dec = int(v.get('dec', 1))
    U = v.get('unit', 'bn')
    headline = (f'{mlab(cur)} 合并营收 {sym}{cur_bn:,.{dec}f}{U}'
                f'（{sgn(cur_yoy)} y/y、{sgn(cur_mom)} m/m）'
                f' · {cur_q} 累计 {sym}{cur_q_bn:,.0f}{U}（{sgn(cur_q_yoy, 0)} y/y，'
                f'{n_in_last} of 3 months'
                + ('' if n_in_last >= 3 else '，比上年同季前同样月数') + '）'
                f' · YTD {sym}{ytd_now:,.0f}{U}（{sgn(ytd_yoy, 0)} y/y）')
    # 抬头是全页最显眼的一行，报的是**美元腿**的两个读数（美元 y/y 与汇率贡献），不是
    # 汇率本身，所以判据是 usd_leg_shown(EX)（§1.5）。照旧按 ds.fx 判，只画 Ex8 的家会
    # 在这一行印出两个页内任何一处都查不到、也不是公司披露的数。
    if usd_leg_shown(EX):
        headline += (f' · 美元口径 y/y {sgn(float(ds.usd_yoy.iloc[-1]), 0)}，'
                     f'汇率贡献 {sgn(float(ds.fx_contrib.iloc[-1]), 1, "pp")}')
    hub_line = (f'{mlab(cur)} 营收 {sym}{cur_bn:,.0f}{U}，{sgn(cur_yoy, 0)} y/y；'
                f'YTD {sgn(ytd_yoy, 0)} y/y')

    brief_html = compose_brief(ds, spec, EX)
    notes = build_notes(ds, spec, ex, EX, ctx, blanked)

    payload = {
        'ticker': spec['ticker'],
        'tracker': spec['tracker'],
        'title': f'{spec["title"]} — {cur.year} 年 {cur.month} 月',
        'data_through': str(cur),
        'through_label': f'{cur.year} 年 {cur.month} 月',
        'subtitle': (f'数据源：{spec["source_zh"]} · '
                     f'覆盖 {mlab(ALL[0])} – {mlab(ALL[-1])} 共 {len(ALL)} 个月 · '
                     f'{spec["format_source"]}'),
        'headline': headline,
        'brief': brief_html,
        'hub_line': hub_line,
        'source': spec['source'],
        'xlabels': [mlab(p) for p in ALL[-T:]],
        'xlabels_long': [mlab(p) for p in ALL],
        'summary': summary,
        'exhibits': ex,
        'table': table,
        'notes': notes,
        'footer': spec.get('footer',
                           '图表与派生算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
                           '仅供个人研究，不构成投资建议'),
    }
    _c = [0]
    payload = md2b_deep(payload, _c)
    if _c[0] and not quiet:
        print(f'[{spec["ticker"]}] 图注里 {_c[0]} 处 Markdown `**…**` 已换成 <b>…</b>')

    sd = source_date(spec['ticker'], str(cur))
    if sd:
        payload['source_date'] = sd

    path = os.path.join(out_dir or DATA, f'{spec["ticker"]}.js')
    payload_guard.write_dash(path, payload, spec['ticker'])
    if not quiet:
        print(f'[{spec["ticker"]}] 窗口 {ALL[0]} → {ALL[-1]}（{len(ALL)} 个月）'
              f'· 季度 {ds.qsum.index[0]} → {ds.qsum.index[-1]}')
        print(f'[{spec["ticker"]}] Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}'
              f'（{len(ex)} 张）+ Exhibit {table["n"]} 核对表；'
              f'编号表 {EX}')
        print(f'[{spec["ticker"]}] {headline}')
        print(f'[{spec["ticker"]}] 写出 {path} ({os.path.getsize(path) / 1024:.1f} KB)')
    return payload


def load_spec(ticker):
    sys.path.insert(0, HERE)
    mod = importlib.import_module(f'mrspecs.{ticker}')
    return mod.SPEC


def all_tickers():
    d = os.path.join(HERE, 'mrspecs')
    return sorted(x[:-3] for x in os.listdir(d)
                  if x.endswith('.py') and not x.startswith('_'))


def owned_elsewhere(t):
    """这个 ticker 的 data/<t>.js 是不是**别的生成器**在负责。判据是文件在不在，不是名单。

    `monthly_run.py:389` 的 `builder()` 按 `build/<t>.py` → 下划线版 → `build/single.py`
    + `build/specs/<t>.py` 的顺序解析。所以：
      · `build/specs/<t>.py` 存在 ⇒ 每月 cron 会用 single.py 重新生成 data/<t>.js，
        而 single.py 那套图列带 decomp / ttm_yoy / seasonality 等本底座**不产出**的图。
        这时候本底座往 data/ 里写就是「两套图列打架」，下个月还会被盖回去。
      · `build/<t>.py` 存在但内容是指向本底座的薄壳（如 tsm）⇒ 归本底座管，正常写。
    「两套图列谁赢」是产品决定，不该由「谁最后跑」来决定，所以这里默认拦住，
    要写就显式 `--force`（或用 `--out` 写到别处）。
    """
    if os.path.exists(os.path.join(HERE, 'specs', f'{t}.py')):
        shell = os.path.join(HERE, f'{t}.py')
        if os.path.exists(shell):
            with open(shell, encoding='utf-8') as fh:
                if 'mrbase' in fh.read():
                    return None
        return f'build/specs/{t}.py（monthly_run 会走 build/single.py 重新生成）'
    return None


def build_one(ticker, out_dir=None, force=False, quiet=False):
    """给薄壳 `build/<t>.py` 用的单家入口。"""
    if out_dir is None and not force:
        who = owned_elsewhere(ticker)
        if who:
            print(f'[{ticker}] 拒绝写入 data/：这一页目前由 {who} 负责。'
                  f'要用本底座接管请先决定图列归属，然后 --force；'
                  f'只想看产物就用 --out 写到别处。')
            return 2
    build(load_spec(ticker), out_dir=out_dir, quiet=quiet)
    return 0


def main():
    ap = argparse.ArgumentParser(description='月度营收看板通用底座')
    ap.add_argument('tickers', nargs='*')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--out', default=None, help='输出目录（默认仓库 data/）')
    ap.add_argument('--force', action='store_true',
                    help='即使这一页目前由别的生成器负责，也照写 data/<t>.js')
    a = ap.parse_args()
    ts = all_tickers() if a.all else a.tickers
    if not ts:
        ap.error('给至少一个 ticker，或 --all')
    rc = 0
    for t in ts:
        try:
            rc = build_one(t, out_dir=a.out, force=a.force) or rc
        except BaseException as e:      # noqa: BLE001 —— SystemExit 也要接住，见下
            if isinstance(e, (KeyboardInterrupt,)):
                raise
            rc = 1
            # build/brief.py 的长度护栏抛的是 SystemExit（不是 Exception 的子类）。
            # 只 catch Exception 的话，一家 brief 短了 4 个字会把整批 --all 打死在半路，
            # 后面几家连跑都没跑。这里逐家隔离，退出码仍然非 0。
            print(f'[{t}] 失败：{type(e).__name__}: {e}')
    return rc


if __name__ == '__main__':
    sys.exit(main())
