# -*- coding: utf-8 -*-
"""日月光投控 ASEH（3711.TW / NYSE: ASX）月度营收页配置 —— 共用底座 `mrbase`。

放置位置：`build/mrspecs/ase.py`；薄壳 `build/ase.py`（不留薄壳，`monthly_run.py`
的 `builder()` 会继续走 `build/single.py` + `build/specs/ase.py`，两套图列分叉）。

⚠️ **slug 是 `ase`。`asx` 在本仓已经是 ASX Limited（澳交所）**，日月光的 NYSE ADR
   恰好也叫 ASX —— 写串会同时污染两张页，而且是静默污染：图照出、数全错。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
核源清单（每条都在 2026-08-13 现抓复核过，出处可点开）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【1】序列起点 2018-05 是**口径起点**，不是「最早可得」
    SEC EDGAR 公司档案（CIK 0001122411）的更名记录：
      2018-04-30  ADVANCED SEMICONDUCTOR ENGINEERING INC → ASE Industrial Holding
      2018-06-08  → ASE Technology Holding Co., Ltd.
    控股公司 2018-04-30 才成立，2018-05 是第一个合并月报。SEC XBRL 里
    2015/2016/2017 的 `ifrs-full:Revenue`（283,303 / 274,884 / 290,441 NT$mn）
    属于**前身 ASE Inc.**，主体不同、不可前接。
    ⇒ `window.x_from = None`（显式声明「用序列自己的起点」）。
      **不要写 '2016-01'**：那是 TSM 的窗口。两种写法在本家产出完全相同
      （`_first_at_or_after` 会把它夹到 2018-05），但 spec 是给人读的 ——
      写 '2016-01' 等于声明「本页选了一个短窗口」，而事实是「本主体没有更早的月报」。

【2】可加总性是**实测**，不是推定（`value.summable = True` 的依据）
    `data.sec.gov/api/xbrl/companyconcept/CIK0001122411/ifrs-full/Revenue.json`
    的 20-F 年度值 vs 本序列逐月加总（NT$mn）：
      FY2019 413,182.2 / 413,182 · FY2020 476,978.7 / 476,980 ·
      FY2021 569,997.1 / 569,997 · FY2022 670,872.6 / 670,874 ·
      FY2023 581,914.5 / 581,916 · FY2024 595,409.6 / 595,409 ·
      FY2025 645,387.7 / 645,389
    七个完整年、最大绝对差 < 2 百万（基数 41~67 万百万），全是百万位四舍五入残差。
    ⇒ 季度桥 / QTD / YTD / 12 个月滚动同比这四道加总只在这一列上合法。

【3】第三列叫「非 ATM」而不是「EMS」，这是口径不是措辞
    月度新闻稿只给两个数：合并总额 + **ATM 分部**营收（分部基础，含分部间交易）。
    `revenue_nonatm_ntd_mn` = 合并 − ATM = 「EMS 分部 + Others − ATM 分部间抵销」，
    **不等于**合并利润表的 EMS 行，也不等于 EMS 分部基础数。官方分部数不在
    `series/ase.csv` 里，构建期读不到 ⇒ 页面只作定性陈述，**不印写死的差额**。

【4】「合并含 33–36% EMS」这句话（任务书原话）两处不准，页面按实测写
    (a) 那是**非 ATM 残差**不是 EMS（见【3】）；
    (b) 33–36% 只是最近约 12 个月。99 个月实测非 ATM 占比 24.4%~52.1%、
        中位 41.4%（最新月 35.6%），跨越 2020-12 并入与 2021-12 处分两次结构变化。
    页面上这些数一律 `_facts.share_range()` 构建期现算。

【5】**没有汇率腿，但理由不是「营收不以美元计价」——那句话与 20-F 直接冲突**
    ASEH 2025 年度 Form 20-F（2026-04-01 报送，accession 0001193125-26-135585）：
      · Item 5「Pricing and Revenue Mix」：
        "The majority of our prices and revenues is denominated in U.S. dollars."
      · Item 11「Exchange Rate Risk」：
        "Currently, the majority of our revenues and a significant portion of our
         capital expenditures are denominated in U.S. dollars."，并明写
        "against the NT dollar, our functional currency"。
    ⇒ ASEH 与 TSMC 是**同一种结构**：功能货币新台币、多数营收以美元计价。
      `build/specs/ase.py` 里那句「那不是以美元计价的销售」本轮**不继承**。
    真正拦住汇率腿的是另外两条，都是本轮实测（见 `_NO_FX_NOTE`）：
      (a) 公司**每月自印 US$ 表**（2026-07 期：合并 US$2,309mn、ATM US$1,487mn），
          却不披露所用汇率；底座的汇率腿只会做「本币 ÷ 外部牌价」，
          于是页面会印出第二个「美元营收」，与我们引为数据源的同一份 PDF 打架。
      (b) 用公司自印的两个数反解隐含汇率，与 FRED EXTAUS 月均（series/tsm_fx.csv）
          逐月不一致且**符号在变**：2025-06 +0.63%、2026-06 −0.55%、2026-07 −0.81%
          （不是一个可校准掉的常数偏移）。传导到「汇率贡献 pp」那张图上：
          2026-07 公司口径 +12.6pp vs FRED 推导 +12.8pp（差 0.2pp）；
          2026-06 公司口径 +6.9pp vs FRED 推导 +8.4pp（差 **1.5pp**）。
          整幅量程只有十几个点的图，误差能到 1.5pp，而正确答案就印在源文件上。
    ⇒ 不给 `fx`，Ex5/Ex6/Ex8 由底座自动跳过并把编号顺次前移。
    ⇒ **接管后第一顺位待办**：把新闻稿那两列美元落进 `series/ase.csv`
      （`revenue_usd_mn` / `revenue_atm_usd_mn`）。ASEH 是本仓七家里唯一有官方
      月度美元实绩的一家，落库后它的汇率腿会比 TSM 的推导值更硬；届时
      `fx.usd_share_note` 的出处就是上面两句 20-F 原文（**定性版本**，20-F 说的是
      "the majority"，没有数字，不许自己编一个「约七成」式的百分比）。

【6】断点：**两条画线，三条登记但不画线**（门槛见 `BREAK_DRAW_MIN_PCT`）
    画线的两条，月份一律取**控制权转移当月**、不取签约日：
      · 2020-12 FAFG（Asteelflash）并入 —— 2021 年度 20-F（accession
        0001193125-22-087341）："On December 1, 2020, the transaction was completed
        and as a result, USI acquired 100% of FAFG's total issued shares"；同份文件
        「Impact of acquisitions」表：FAFG 自 2020-12-01 至 2020-12-31 计入合并的
        operating revenue = NT$2,043,440 千元 ≈ 2,043 百万 = 当月合并 50,298 的
        **4.1%**。影响合并 + 非 ATM，**ATM 不受影响**。
      · 2021-12 中国四厂处分 —— 同份 20-F："The transaction completed on
        **December 16, 2021**"（SPA 签于 2021-12-01，对价 NT$36,939.1 百万）。
        月中交割 ⇒ 2021-12 是半个月的过渡月，2022-01 才是第一个干净月。
        公司**自己认这条断点**：2022 全年每期月报多印一组 Pro Forma 表。
        本轮现抓 2022-01 期 PDF（电头 FEBRUARY 10, 2022）读到：
          合并 Dec-2021 报告 59,665 → pro forma 57,376（−2,289，−3.8%）
          ATM  Dec-2021 报告 31,011 → pro forma 28,722（−2,289）
        两侧减项分毫相同 ⇒ **减项全部落在 ATM，非 ATM 未动**，与【3】的残差定义自洽。
        y/y 被污染的幅度也是公司自己印的：Jan-2022 合并报告 +18.9% vs pro forma
        +24.7%（5.8pp）；ATM 报告 +10.7% vs pro forma +19.8%（**9.1pp**）。
    登记但不画线的三条（都 < 1%，画上去只会稀释掉真正 −3.8% 的那条）：
      · 2020-10 SF（Siliconware Electronics (Fujian)）处分完成（2021 年度 20-F
        Note 30：2020-09 董事会决议、2020-10 完成并转移控制权，对价 RMB966,000 千元）。
        ⚠️ **20-F 未单独披露 SF 的营收贡献** ⇒ 它落在门槛之下是**推断**（依据只有
        对价量级），不是实测。哪天查到 SF 的月营收量级 ≥ 门槛，这条要补画红线。
      · 2023-10-27 Hirschmann/HCC 并入（2025 年度 20-F Note 29「Impact of
        acquisitions」）：自并购日至 2023-12-31 计入合并 NT$1,017,423 千元
        ≈ 473 百万/月 ≈ 当时合并的 0.9%。
      · 2024-08-01 ASEPCAYMAN（菲律宾）+ CHE（韩国天安）并入（同表）：
        2024-08~12 合计 518,026 + 825,216 = 1,343 百万 ≈ 269 百万/月 ≈ 0.5%。
      量级交叉印证：同一份 20-F 的 pro forma —— 视同期初完成，FY2023 营收会是
      586,489,731 千元（实际 581,914，+0.79%）、FY2024 会是 597,015,838 千元
      （实际 595,410，+0.27%）。

【7】**ATM 被追溯重述过一次，合并没有**（本轮现抓 4 期 2019 年 PDF 复现）
      2019-07-09 期：ATM May-19 印 20,248（序列 20,148，−100）、
                     Jun-19 印 20,700（序列 20,605，−95）
      2019-08-09 期：ATM Jul-19 印 21,763（序列 21,668，−95）
      2019-09-10 期：ATM Aug-19 印 22,974（序列 22,884，−90）
      2019-10-09 期：ATM 表标题带星号，脚注 "The ATM results presented have been
                     retrospectively adjusted…"，三个月全中（重述后值），
                     季度 Q2-2019 由 59,790 重述成 59,594。
    同 4 期里**合并列 12/12 全中** ⇒ 合并没被重述。
    这直接支持把**合并**设为 `value`：主序列该是没有重述史的那条。

【8】`continuity` **不给**：底座要求「要么带 URL 出处、要么整个不给」。本家不但给不出
    「口径连续」的出处，事实还相反（【6】五条结构变化 + 【7】一次 ATM 重述）。

【9】`official_yoy` **不给**：`series/ase.csv` 没有 y/y 列。公司确实公告 y/y
    （新闻稿印到一位小数），底座退回 `build/yoy.py` 自算 —— 两者的差只来自
    「先四舍五入到百万再相除」，见 `_YOY_SOURCE_NOTE`（不印写死的差值）。

【10】没有指引桥：ASEH 每季法说会给的是「下季 ATM 新台币营收环比 +x%~+y%、EMS 环比
    约 +z%」这种**季度环比百分比区间**，没有绝对金额、没有月度分解、没有折算汇率假设。
    `mrspecs/tsm.py` 那条桥依赖 `tsm_guidance.csv` 的六列，在本家逐列无源。

━━ 本轮同时修掉的两处底座缺陷（不是 ASE 专属补丁）━━━━━━━━━━━━━━━━━━━━━
· `build_exhibits` 的 Ex9 原本走 `push('heat', …)`，而 `push()` 无条件调
  `apply_breaks()` ⇒ 热力矩阵拿到 `break_at`（99 个月轴上的下标，这张 8×12 的矩阵
  没有那条轴），并被追加一段「本图上的红色竖虚线是口径断点…」，正好顶撞它上一句
  「heat_matrix 没有连续横轴，因此不画断点竖线」；页尾清单也会跟着自相矛盾。
  画面一直是对的（`charts.js` 的 `drawHeat()` 提前 return），错的是 payload 与文字。
  TSM 的 breaks 为空走不到，联电/联发科/南亚科接管时都会踩到。已在底座改掉。
· 底座原来对任何没有 `fx` 的 spec 印「该家的月度公告只有新台币，没有官方美元实绩」
  —— 那是一句 per-ticker 的事实断言，对 ASEH 是**假话**（见【5】(a)）。
  底座已改成只陈述本页状态、把「公司有没有披露」留给 spec 说。
"""
import csv
import os

from . import _facts

# build/ 在 sys.path 上（mrbase.load_spec 会 insert HERE）⇒ yoy 直接 import。
# 同比口径的唯一实现是 build/yoy.py，本文件一行 pct_change(12) 都不写。
try:
    import pandas as pd
    import yoy as _Y
except Exception:                    # noqa: BLE001 —— import 期不许抛，见 _facts 文件头
    pd = _Y = None

_CSV = 'ase.csv'
_COL_TOT = 'revenue_ntd_mn'
_COL_ATM = 'revenue_atm_ntd_mn'
_COL_NON = 'revenue_nonatm_ntd_mn'

#: 画红色断点竖线的门槛：并表/处分对**单月合并营收**的影响 ≥ 这个比例才画线。
#: 低于门槛的仍然登记进图注（见 `_M_AND_A_NOTE`）。一页红线画满等于告诉读者
#: 「什么都不可比」，反而盖掉真正 −3.8% 的那一条。
BREAK_DRAW_MIN_PCT = 3.0


# ══════════════════════════════════════════════════════════════════════════════
# 构建期现算。每个函数拿不到就返回 None，调用方退回不含数字的定性版本。
# import 期抛异常 = 整批构建挂在「少一句话」上，不划算（同 mrspecs/_facts.py）。
# ══════════════════════════════════════════════════════════════════════════════
def _series(col):
    """series/ase.csv 的一列 → pandas Series（月度 PeriodIndex）。拿不到返回 None。"""
    if pd is None:
        return None
    try:
        with open(os.path.join(_facts.SERIES, _CSV), encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
        idx = pd.PeriodIndex([r['month'] for r in rows], freq='M')
        return pd.Series([float(r[col]) for r in rows], index=idx).sort_index()
    except Exception:                # noqa: BLE001
        return None


def _identity():
    """核一条恒等式：ATM + 非 ATM ≡ 合并。

    差不为 0 就说明第三列不是残差 —— 那样「非 ATM」这个列名本身就要重写，
    页面上「合并 ≡ 各分部之和」那句话也不能再说。
    """
    tot, atm, non = _series(_COL_TOT), _series(_COL_ATM), _series(_COL_NON)
    if tot is None or atm is None or non is None:
        return None
    try:
        return {'max': float((atm + non - tot).abs().max()), 'n': int(len(tot))}
    except Exception:                # noqa: BLE001
        return None


def _split_gap():
    """「合并线替封测说了多少假话」的实测 —— 口径全部走 build/yoy.py。

    返回「ATM 同比 − 合并同比」（pp）在两种口径下的分布。**不假设符号**：
    本序列全历史上这个差是双向的（合并有时反而更快），把它写成「每个月都低估」
    在全历史上是假的，所以这里逐项报正负计数，措辞由数据决定。
    """
    if _Y is None:
        return None
    tot, atm = _series(_COL_TOT), _series(_COL_ATM)
    if tot is None or atm is None or len(tot) < 30:
        return None
    try:
        gt = (_Y.ttm_yoy(atm, _Y.FLOW) - _Y.ttm_yoy(tot, _Y.FLOW)).dropna()
        gm = (_Y.mom_yoy(atm, _Y.FLOW) - _Y.mom_yoy(tot, _Y.FLOW)).dropna()
        if not len(gt) or not len(gm):
            return None
        return {
            't_n': len(gt), 't_lo': float(gt.min()), 't_hi': float(gt.max()),
            't_pos': int((gt > 0).sum()),
            't12_n': len(gt[-12:]), 't12_lo': float(gt[-12:].min()),
            't12_hi': float(gt[-12:].max()), 't12_pos': int((gt[-12:] > 0).sum()),
            'm_n': len(gm), 'm_lo': float(gm.min()), 'm_hi': float(gm.max()),
            'm12_lo': float(gm[-12:].min()), 'm12_hi': float(gm[-12:].max()),
            'ttm_tot': float(_Y.ttm_yoy(tot, _Y.FLOW).dropna().iloc[-1]),
            'ttm_atm': float(_Y.ttm_yoy(atm, _Y.FLOW).dropna().iloc[-1]),
            'mom_tot': float(_Y.mom_yoy(tot, _Y.FLOW).dropna().iloc[-1]),
            'mom_atm': float(_Y.mom_yoy(atm, _Y.FLOW).dropna().iloc[-1]),
        }
    except Exception:                # noqa: BLE001
        return None


def _days_dispersion():
    """`_facts.days_effect()` 只给斜率点估计，这里补上标准误与 R²。

    **为什么非补不可**：`mrspecs/tsm.py` 那条「不做日均化」的论证靠的是「斜率 1.47
    而不是 1」。本家斜率 1.10，只报点估计会让人以为同一句话在这里也成立；补上标准误
    之后才看得见 1.10 与 1 在统计上分不开，于是本页的理由**必须换一条**。
    照抄 TSM 的措辞就是编数据。
    """
    import calendar
    try:
        with open(os.path.join(_facts.SERIES, _CSV), encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
        ms = [r['month'] for r in rows]
        vs = [float(r[_COL_TOT]) for r in rows]
    except Exception:                # noqa: BLE001
        return None

    def dm(m):
        return calendar.monthrange(int(m[:4]), int(m[5:7]))[1]

    xs, ys = [], []
    for i in range(1, len(vs)):
        if not vs[i - 1]:
            continue
        xs.append((dm(ms[i]) / dm(ms[i - 1]) - 1) * 100)
        ys.append((vs[i] / vs[i - 1] - 1) * 100)
    n = len(xs)
    if n < 24:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0 or n <= 2:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    sse = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys))
    se = (sse / (n - 2) / sxx) ** 0.5
    if se <= 0:
        return None
    return {'slope': b, 'se': se, 't1': (b - 1) / se, 'r2': 1 - sse / syy, 'n': n}


_SHARE_ATM = _facts.share_range(_CSV, _COL_ATM, _COL_TOT)
_SHARE_NON = _facts.share_range(_CSV, _COL_NON, _COL_TOT)
_GAP = _split_gap()
_ID = _identity()
_D = _facts.days_effect(_CSV, _COL_TOT)
_FIT = _days_dispersion()
_HEAT = _facts.yoy_extremes(_CSV, _COL_TOT)


# ══════════════════════════════════════════════════════════════════════════════
# 图注。凡是随数据变的数一律来自上面几个现算结果，拿不到就退回定性版本；
# 凡是引用某份**具名、有日期**的官方文件里的数（公司自印的 pro forma、20-F 的
# 并购贡献额）不随本页窗口变，属于**引证**不属于统计量，照引并标出处。
# ══════════════════════════════════════════════════════════════════════════════

# ── ① 主线为什么是「合并」——任务点名要写进**这张图自己的图注**（note_extra）─────
_MAIN_LINE_NOTE = (
    '<b>这张图的柱与右轴金线取的是「合并」那一列，不是 ATM —— 这是一个有代价的选择，'
    '代价也写在下面。</b>选合并的四条理由，每条都可复核：'
    '① 合并是台湾《证券交易法》强制公告项，在<b>三个互相独立的源</b>上都取得到并对得上'
    '（公司新闻稿 PDF、MOPS 全市场月表、TWSE OpenAPI <code>t187ap05_L</code>）；'
    'ATM 只出现在公司自己的新闻稿里，没有第二个源可以核。'
    '② 合并逐月加总<b>无需任何调整</b>就等于 20-F 的年度合并营收'
    '（SEC XBRL <code>ifrs-full:Revenue</code>，FY2019–FY2025 七个完整年最大绝对差'
    '不到 2 百万，全是百万位四舍五入）—— 本页的季度桥、QTD、YTD、'
    f'{_Y.TTM_WIN if _Y else 12} 个月滚动同比这四道加总，只有在这一列上才是合法的。'
    '③ ATM 是<b>分部基础</b>（含分部间交易），对不上合并利润表里任何一行；'
    '而且它被<b>追溯重述</b>过（2019-05~08 每月 −90 ~ −100 百万，2019-09 期落地，'
    '当期 ATM 表标题带星号说明），合并列在同批新闻稿里一处都没变。'
    '主序列应当是没有重述史的那条。'
    '④ 底座只有一条主序列，QTD／YTD／TTM／热力矩阵全部由它派生；把两块业务的口径'
    '混进同一条派生链，出来的数没有一个说得清是谁的。'
    + (f'<b>代价：合并读不出封测景气。</b>最新月两条口径的差已经很大 —— '
       f'{_Y.TTM_WIN if _Y else 12} 个月滚动同比合并 {_GAP["ttm_tot"]:+.1f}%、'
       f'ATM {_GAP["ttm_atm"]:+.1f}%，单月同比合并 {_GAP["mom_tot"]:+.1f}%、'
       f'ATM {_GAP["mom_atm"]:+.1f}%；'
       if _GAP else '<b>代价：合并读不出封测景气。</b>')
    + '全历史的差距分布（含它<b>什么时候反过来</b>）在页尾「合并线与 ATM 线的差距」'
    '一条里现算列出。ATM 并没有从页上消失：汇总表逐行、全历史图的三条线、'
    '核对表的分部列都在，要读封测就读那三处。')

# ── ② 代价的量化（页尾）—— 措辞由数据决定，不假设符号 ────────────────────────
if _GAP and _SHARE_ATM:
    _both_ways = _GAP['t_pos'] not in (0, _GAP['t_n'])
    _SPLIT_NOTE = (
        f'<b>合并线与 ATM 线的差距有多大 —— 现算，不是印象。</b>本序列 '
        f'{_SHARE_ATM["n"]} 个月里 ATM（封测及材料）占合并 '
        f'<b>{_SHARE_ATM["min"]:.1f}% ~ {_SHARE_ATM["max"]:.1f}%</b>、'
        f'中位 {_SHARE_ATM["med"]:.1f}%，最新月 {_SHARE_ATM["cur"]:.1f}%。'
        f'把两列各自的 <b>{_Y.TTM_WIN if _Y else 12} 个月滚动同比</b>相减'
        f'（口径统一走 <code>build/yoy.py</code>），{_GAP["t_n"]} 个可比月份上'
        f'「ATM − 合并」落在 <b>{_GAP["t_lo"]:+.1f}pp ~ {_GAP["t_hi"]:+.1f}pp</b>，'
        f'其中 {_GAP["t_pos"]}/{_GAP["t_n"]} 个月为正。'
        + (f'<b>注意这个差是双向的</b>：ATM 并非总是跑得更快，'
           f'历史上合并口径最多曾高出 ATM {abs(_GAP["t_lo"]):.1f}pp'
           f'（EMS 侧强、封测弱的那几年）—— 所以「把合并线当封测读一定会低估」'
           f'这句话在全历史上是假的，只在当下这一段成立。'
           if _both_ways and _GAP['t_lo'] < 0 else '')
        + f'当下这一段是单边的：最近 {_GAP["t12_n"]} 个月里 '
          f'{_GAP["t12_pos"]}/{_GAP["t12_n"]} 个月 ATM 更快，'
          f'差 {_GAP["t12_lo"]:+.1f}pp ~ {_GAP["t12_hi"]:+.1f}pp；'
          f'换成单月口径同一段窗口差 {_GAP["m12_lo"]:+.1f}pp ~ {_GAP["m12_hi"]:+.1f}pp，'
          f'全历史 {_GAP["m_n"]} 个月则宽到 {_GAP["m_lo"]:+.1f}pp ~ {_GAP["m_hi"]:+.1f}pp。'
          '<b>结论：本页的同比读数是「日月光投控这家控股公司」的增速，不是封测的增速。</b>'
          '要读封测，请看全历史图上的 ATM 线、汇总表的 ATM 行，或核对表的 ATM 列。')
else:
    _SPLIT_NOTE = (
        '<b>合并线与 ATM 线的差距。</b>ASEH 的合并营收由 ATM（封测及材料）与'
        '非 ATM（环旭 USI 的电子代工及其他）两块拼成，两块的客户与周期完全不同，'
        '合并同比因此读不出封测景气。本次未能从 CSV 现算出两条线的同比差，'
        '故只作定性表述 —— 请直接对读全历史图上的两条分部线。')

# ── ③ 第三列是残差，不是官方 EMS 分部 ───────────────────────────────────────
_CALIBER_NOTE = (
    '<b>第三列写「非 ATM」而不是「EMS」，是口径不是措辞。</b>'
    '月度新闻稿只给两个数：合并总额与 <b>ATM 分部</b>营收（分部基础，含分部间交易）。'
    '本表第三列 = 合并 − ATM'
    + (f'（在全部 {_ID["n"]} 个月上与这个减法<b>逐月恒等</b>，现算最大绝对差 '
       f'{_ID["max"]:.0f} NT$mn）' if _ID else '')
    + '，等于「EMS 分部 + Others − ATM 分部间抵销」，<b>不等于</b>合并利润表里的 EMS 行，'
      '也不等于公司季度附注里的 EMS 分部基础数；同理 ATM 那一列也不等于合并利润表的 '
      'Packaging + Testing + Others。官方分部数不在 <code>series/ase.csv</code> 里，'
      '本页构建期读不到，所以这里<b>只作定性陈述、不印一个写死的差额</b> —— '
      '要逐季对差额请自行取 20-F 或法说会 deck 的分部表。'
      '叫它「EMS」省事，但那是在口径上说谎。')

# ── ④ 构成随年份变化很大 ────────────────────────────────────────────────────
if _SHARE_NON:
    _MIX_NOTE = (
        f'<b>「EMS 大约占三分之一」这句话对本序列的多数年份是错的。</b>'
        f'非 ATM 残差占合并的实测区间是 '
        f'<b>{_SHARE_NON["min"]:.1f}% ~ {_SHARE_NON["max"]:.1f}%</b>'
        f'（中位 {_SHARE_NON["med"]:.1f}%，最新月 {_SHARE_NON["cur"]:.1f}%，'
        f'{_SHARE_NON["n"]} 个月）—— 三分之一上下只是最近这一段的情形。'
        f'区间这么宽是有结构原因的：2020-12 FAFG 并入把非 ATM 抬上去一级，'
        f'2021-12 处分中国四厂把 ATM 削下去一块，两次都改写了配比。'
        f'跨年比较「日月光的营收增速」之前，先看这一行占比走到哪了。')
else:
    _MIX_NOTE = (
        '<b>营收构成随年份变化很大</b>：2020-12 FAFG 并入抬高非 ATM 侧，'
        '2021-12 处分中国四厂削减 ATM 侧，两次都改写了两块业务的配比。'
        '跨年比较增速之前先看构成。（本次未能从 CSV 现算出占比区间，故只作定性表述。）')

# ── ⑤ 全历史图上的红线只对合并线成立（挂在那张图自己的图注上）───────────────
_SEG_LINE_NOTE = (
    '<b>本图上那两条红色竖虚线只对合并线（NAVY）成立。</b>底座把断点画在每一张有连续'
    '时间轴的图上，而本图除合并线外还有两条分部线 —— 实测两条断点各只落在一侧：'
    '2020-12 的 FAFG（Asteelflash）并入影响合并与非 ATM，<b>ATM 那条线不受影响</b>；'
    '2021-12 的中国四厂处分影响合并与 ATM，<b>非 ATM 那条线不受影响</b>'
    '（公司自印的 pro forma 里合并与 ATM 两侧减项分毫相同，残差未动）。'
    '引擎没有「只标某一条线」的图元，所以这件事只能写在这里。')

# ── ⑥ 并购门槛：红线是判断，不是穷举 ────────────────────────────────────────
_M_AND_A_NOTE = (
    f'<b>红色竖虚线是<u>按门槛</u>画的，不是并购事件的穷举 —— 门槛写在这里供复核。</b>'
    f'判据：并表／处分对<b>当月合并营收</b>的影响 ≥ <b>{BREAK_DRAW_MIN_PCT:.0f}%</b> 才画线。'
    f'过线因而已画的两条：'
    f'<b>2020-12</b> FAFG（Asteelflash）并入 —— 20-F 披露该主体自 2020-12-01 至月末'
    f'计入合并的营收 NT$2,043 百万，约当月合并的 4.1%；'
    f'<b>2021-12</b> 中国四厂（ASEN／ASEKS／ASEWH／Advanced Shanghai）处分'
    f'（2021-12-16 交割）—— 公司自印的 pro forma 显示当月合并 −2,289 百万（−3.8%），'
    f'且减项<b>全部落在 ATM</b>，非 ATM 分毫未动。'
    f'<b>未过线、因此不画线但在此登记</b>的三条：'
    f'<b>2023-10-27</b> Hirschmann（HCC）并入，20-F 披露自并购日至年末营收 '
    f'NT$1,017 百万，折合约当时月度合并的 0.9%；'
    f'<b>2024-08-01</b> ASEPCAYMAN（菲律宾）与 CHE（韩国天安）并入，同期合计 '
    f'NT$1,343 百万，折合约 0.5%；'
    f'<b>2020-10</b> SF（Siliconware Electronics (Fujian)）处分完成 —— '
    f'⚠️ 这一条的营收贡献 <b>20-F 没有单独披露</b>，把它放在门槛之下是依对价量级'
    f'（RMB966 百万）作的<b>推断</b>，不是实测；日后若查到它的月营收量级过线，'
    f'这条要补画红线。'
    f'量级可交叉印证：同一份 20-F 的 pro forma 显示，把上述并购视同期初完成，'
    f'FY2023 营收会高 0.79%、FY2024 高 0.27%。'
    f'把 0.3%~0.9% 的事件也画成红线，页面会变成「什么都不可比」，反而盖掉真正 −3.8% '
    f'的那一条 —— <b>所以这是判断，不是遗漏</b>。出处：ASEH 2021 年度 Form 20-F'
    f'（Note 29／Note 30／Item 4）、2025 年度 Form 20-F（Note 29「Impact of '
    f'acquisitions」表），以及公司 2022-01 期月度新闻稿的 Pro Forma Basis 表。')

# ── ⑦ 跨断点的同比是伪同比，幅度公司自己印过 ────────────────────────────────
_BREAK_YOY_NOTE = (
    '<b>跨断点的同比是伪同比，幅度由公司自己印出来过。</b>'
    '公司在 2022 全年每期月报里多印一组「排除已处分中国四厂」的 Pro Forma 表，'
    '就是因为知道这件事：以 2022-01 期为例，合并 y/y 报告值 <b>+18.9%</b>、'
    'pro forma（可比口径）<b>+24.7%</b>，差 5.8 个百分点；'
    'ATM 侧报告 +10.7% vs pro forma <b>+19.8%</b>，差 <b>9.1 个百分点</b>。'
    '本序列<b>不做追溯调整</b>（官方从未按月重述月营收，自己调一版会得到一条外部'
    '无法复核的序列，那比留着断点更糟），只把断点登记出来 —— '
    '读 2021 与 2022 那两列同比时，请自行把这个量级放在心里。'
    '出处：ASEH 2022-01 期月度新闻稿（电头 2022-02-10）Pro Forma Basis 表。')

# ── ⑧ 没有汇率腿（底座只说本页状态，「为什么」由这里说）─────────────────────
_NO_FX_NOTE = (
    '<b>接着上面那条「本页没有美元折算腿」说完：本家的月度公告<u>不是</u>只有新台币。</b>'
    'ASEH 的月度新闻稿逐月印一张 <code>US$ Million</code> 表（合并与 ATM 各一张，'
    '2026-07 期：合并 US$2,309mn、ATM US$1,487mn），那是<b>公司披露的美元数</b>，'
    '不是谁折出来的。本页仍然不出「本币 vs 美元」「汇率贡献」「月均汇率」三张图，'
    '理由是另外两条：'
    '① 公司印了美元数，却<b>不披露所用汇率</b>，而底座的汇率腿只会做「本币 ÷ 外部牌价」'
    '—— 那会在页上印出第二个「美元营收」，与我们引为数据源的同一份 PDF 打架；'
    '② 这个分歧已实测且不是四舍五入：用公司自印的两个数反解隐含汇率，与 FRED 的 '
    'NTD/USD 月均逐月不一致，<b>而且符号在变</b>（2025-06 +0.63%、2026-06 −0.55%、'
    '2026-07 −0.81%），不是一个可以校准掉的常数偏移。传导到本该画的那张「汇率贡献」上：'
    '2026-07 公司口径 +12.6pp vs 外部牌价推导 +12.8pp（差 0.2pp），'
    '2026-06 公司口径 +6.9pp vs 推导 +8.4pp（<b>差 1.5pp</b>）—— '
    '一张整幅量程只有十几个点的图，误差能到一个半点，而正确答案本来就印在源文件上。'
    '在源文件已经给了答案的地方再折一条自己的线，是造第二个答案。'
    '<b>正确的修法不是画，是把新闻稿那两列美元落进 <code>series/ase.csv</code></b>：'
    'ASEH 是本仓唯一有官方月度美元实绩的一家，落库之后它的美元线会是公司披露值，'
    '比 TSM 的推导值更硬。'
    '另需说明：ASEH 的营收<b>确实主要以美元计价</b>（2025 年度 Form 20-F，Item 11 '
    'Exchange Rate Risk："the majority of our revenues … are denominated in U.S. '
    'dollars"，功能货币为新台币；'
    'https://www.sec.gov/Archives/edgar/data/1122411/000119312526135585/d50802d20f.htm）'
    '—— 所以汇率对本家报表增速的影响是真的，只是本页目前没有可靠的口径去量它。'
    '（页上任何一处都不会出现「本币 ÷ 外部牌价」折出来、冒充官方值的美元线。）')

# ── ⑨ 不做日均化：判据与台积电那页不同，特意没照抄 ──────────────────────────
if _FIT and _D:
    _sig = ('与 1 <b>在统计上分不开</b>' if abs(_FIT['t1']) < 2 else
            '与 1 <b>有显著差距</b>')
    _DAYS_NOTE = (
        '<b>本页不做日均化 —— 但本家的理由与台积电那一页<u>不同</u>，别照搬。</b>'
        f'把 <code>(m/m %) ~ (当月天数变化 %)</code> 在本序列 {_FIT["n"]} 个月上回归，'
        f'斜率 <b>{_FIT["slope"]:.2f}</b>（标准误 {_FIT["se"]:.2f}，对 1 的 t 值 '
        f'{_FIT["t1"]:+.2f}）—— 斜率{_sig}，也就是说「多一天多一天的产出」这个假设'
        f'在本家<b>没有被数据否掉</b>（台积电那页能否掉，本家不能，'
        f'所以那边「斜率 1.47 而不是 1」的措辞搬到这里就是编数据）。'
        f'不做日均化的理由换成下面三条：'
        f'① 天数只解释了月度波动的一部分 —— 这条回归的 R² 是 <b>{_FIT["r2"]:.2f}</b>，'
        f'剩下的 {1 - _FIT["r2"]:.0%} 与日历长短无关，除一遍天数并不会让这条线变干净。'
        + (f'② 除不掉的那部分里有农历年：2 月营收对相邻 1、3 月均值的实际比值是 '
           f'<b>{_D["feb"]:.2f}</b>（{_D["feb_n"]} 个年度平均），天数比值却有 '
           f'{_D["feb_days"]:.2f} —— 2 月比「短了几天」该有的样子还要弱约 '
           f'{(_D["feb_days"] - _D["feb"]) * 100:.0f} 个百分点。按天数除一遍，'
           f'会把这段农历年停工原样记成「经营性走弱」。'
           if _D else '② 除不掉的那部分里有农历年错位，按天数归一化会把它记成经营性走弱。')
        + '③ 还有一条与统计无关：本页各图印的是<b>公司公告的原值</b>，'
          '任何归一化都会让柱高不再等于新闻稿上的那个数。'
          '季节性请改用同月对同月定位（热力矩阵那一张）。')
else:
    _DAYS_NOTE = (
        '<b>本页不做日均化</b>：本页各图印的是公司公告的原值，任何归一化都会让柱高'
        '不再等于新闻稿上的那个数；而月度波动里农历年错位的部分远大于天数差本身，'
        '按天数除一遍会把停工记成经营性走弱。'
        '（本次未能从 CSV 现算出回归斜率与 R²，故只作定性表述。）')

# ── ⑩ 热力矩阵：跨断点那几行 + 可读性自检（挂在那张图自己的图注上）──────────
_HEAT_EXTRA = (
    '<b>这张图上没有断点红线，但跨断点的那几格同比一样不可比。</b>'
    '受影响的是 <b>2021 与 2022 两整行</b>外加 <b>2020 年 12 月那一格</b>：'
    '2020-12 起合并范围多了 FAFG（分子有、分母没有），2021-12 起少了中国四厂'
    '（分子没有、分母有）—— 这些格子是<b>伪同比</b>，'
    '格子照样按色标上色，'
    '<b>颜色深浅不代表那几格可比</b>；幅度见页尾「跨断点的同比是伪同比」一条。'
    + ((f'<b>另：颜色只用来找极值，不用来排序。</b>引擎的色阶是<b>线性</b>的'
        f'（把全部有限值的 5/95 分位拉直）：本序列 {_HEAT["n"]} 个同比读数的分位区间是 '
        f'{_HEAT["p5"]:+.1f}% ~ {_HEAT["p95"]:+.1f}%（极值 {_HEAT["min"]:+.1f}% ~ '
        f'{_HEAT["max"]:+.1f}%），最宽的 20% 色带里最多挤进 <b>{_HEAT["dull"]} 格</b>'
        f'（占 {_HEAT["dull_share"]:.0f}%）—— 这些格子彼此色差不到两成，肉眼分不开，'
        f'读它们请看格内数字。')
       if _HEAT else
       '<b>另：颜色是线性色阶</b>（5/95 分位拉直），中间那一大片色差很小，'
       '逐格比较请读格内数字而不是颜色。'))

# ── ⑪ 同比来源 ──────────────────────────────────────────────────────────────
_YOY_SOURCE_NOTE = (
    '<b>公司确实公告同比，只是本序列没存那一列。</b>月度新闻稿与 TWSE OpenAPI 都给 '
    'y/y（新闻稿印到一位小数，OpenAPI 给到小数点后十几位）。本页的单月同比是按'
    '<b>已四舍五入到百万</b>的金额自算的，与公司口径的差只来自这一步四舍五入，'
    '在新闻稿的一位小数上看不出来。把它记在这里是为了说明：'
    '本页的同比<b>不是</b>与公司口径互相独立的第二意见，它就是同一个数的重算 —— '
    '要拿它去挑公司公告的错，先把口径这一层想清楚。')

# ── ⑫ 没有指引桥 ────────────────────────────────────────────────────────────
_NO_GUIDANCE_NOTE = (
    '<b>本页没有指引桥。</b>ASEH 每季法说会给的是「下季 ATM 新台币营收环比 +x%~+y%、'
    'EMS 环比约 +z%」这种<b>季度环比百分比区间</b>：没有绝对金额、没有月度分解、'
    '没有折算汇率假设。台积电那一页的指引桥依赖「美元绝对区间 + 公司假设汇率 + '
    '美元实绩」六列，在 ASEH 逐列无源 —— 形态对不上就不做，'
    '不拿一个环比区间硬折成月度绝对值来凑一句话。')

# ── ⑬ 数据源与落库口径 ──────────────────────────────────────────────────────
_SRC_NOTE = (
    '<b>数据源与落库口径。</b>数值取自 ASEH 官方英文月度新闻稿 PDF <b>正文</b>的两张 '
    'NT$ 表（<code>CONSOLIDATED NET REVENUES</code> 与 <code>ATM NET REVENUES</code>，'
    '2018-05~2018-12 叫 <code>IC-ATM</code>）。'
    '<b>IR 落地页表格里印的金额不作数</b>：本轮（2026-08-13）现抓复现 —— '
    '落地页 2026 年那张表的 January 印的是 59,589，而同一网站挂的当期新闻稿 PDF 正文写 '
    '59,989，TWSE 的当年累计口径也指向 59,989。落地页只用来发现 PDF 链接。'
    '每份 PDF 同时印当月／上月／去年同月三个读数，所以每期都能给已入库的两个月做一次'
    '复核；本轮抽查 2019 年 4 期与 2022-01、2026-07 两期，共 18 个印出来的合并月值'
    '与本序列逐个相符。'
    '序列起点 2018-05 是<b>口径起点</b>不是「最早可得」：ASEH 控股 2018-04-30 才成立'
    '（SEC EDGAR 公司档案的更名记录），2018-05 是第一个合并月报；更早年份的年度营收'
    '属于前身 ASE Inc.，主体不同、不可前接 —— 所以短窗口图的左端是<b>数据边界</b>'
    '而不是窗口选择。')


# ══════════════════════════════════════════════════════════════════════════════
SPEC = {
    'ticker': 'ase',
    'name': 'ASEH',
    'tracker': 'ASE Monthly Revenue Tracker',
    # 标题里写全「NYSE: ASX」：本仓的 `asx` 是 ASX Limited（澳交所），
    # 两者的 ticker 撞名，页面上必须一眼分得开。
    'title': '日月光投控 ASEH (3711.TW / NYSE: ASX)：月度营收跟踪',
    'source': 'Source: ASE Technology Holding monthly net revenue press releases '
              '(ir.aseglobal.com, PDF body), cross-checked against TWSE MOPS t21sc03, '
              'TWSE OpenAPI t187ap05_L and SEC XBRL annual revenue; '
              'format after Goldman Sachs GIR',
    'source_zh': '日月光投控（ASEH）官网 IR 月度营收新闻稿 PDF 正文的两张 NT$ 表'
                 '（合并 / ATM 分部，未经会计师查核，台湾法定次月 10 日前公布），'
                 '并与 TWSE MOPS 全市场月表逐月对账',
    'csv': _CSV,

    # ── 主序列 = **合并**。四条理由见 _MAIN_LINE_NOTE（挂在 gs_bar 自己的图注上）。
    #    summable：新台币是 ASEH 的功能货币与表达货币，月值是原生记账数不是折算值；
    #    与 SEC XBRL 的 20-F 年度值逐年对过账（FY2019–FY2025，最大差 < 2 百万）。
    'value': {'col': _COL_TOT, 'div': 1000.0, 'label': 'NT$bn', 'sym': 'NT$',
              'dec': 1, 'raw_label': 'NT$mn', 'raw_dec': 0, 'zh': 'NT$ revenue',
              'ccy_zh': '新台币', 'summable': True},

    # `official_yoy` 不给：series/ase.csv 里没有 y/y 列（公司公告里有，但没落库）。
    # 底座退回 build/yoy.py 自算，并在页尾说明本页没有「公司原值 vs 自算值」的分歧。

    # 官方逐月拆分的两条分部列（第二条是残差）。底座拿它们喂：汇总表两行、
    # 全历史图两条线、核对表两列、brief 第 4 句的「合并 ≡ 各分部之和」。占比全部现算。
    'segments': [
        {'col': _COL_ATM, 'zh': 'ATM（封测及材料）',
         'label': 'ATM (packaging & test)'},
        {'col': _COL_NON, 'zh': '非 ATM（EMS 及其他，残差）',
         'label': 'Non-ATM (EMS & others)'},
    ],

    # ── 没有 fx ⇒ 底座整体跳过 Ex5／Ex6／Ex8 并把编号顺次前移。
    #    **理由不是「营收不以美元计价」**（20-F 说的恰好相反），见 _NO_FX_NOTE 与文件头【5】。
    #    也不用 skip/skip_note：那两个字段是给「有数据却决定不画」的图用的，
    #    本家是**没有可靠的汇率口径**，不是有而不画。

    'window': {
        # 显式 None = 用序列自己的起点（2018-05，99 个月）。**不是忘了写**：
        # ASEH 控股 2018-04-30 才成立，此前没有本主体的合并月报（文件头【1】）。
        'x_from': None,
        # 自算单月同比自 2019-05 起有值 ⇒ 可用年份 2019~2026 共 8 年。
        # 写 9 与写 8 产出完全相同（底座取 sorted(年份)[-NH:]），但写 8 才是写实数。
        'heat_years': 8,
        'check_rows': 13,
    },

    # ── 断点：只画过门槛的两条（门槛 BREAK_DRAW_MIN_PCT，未过线的三条登记在
    #    _M_AND_A_NOTE 里）。月份一律取**控制权转移当月**，不取签约日。
    #    **不写 'col'**：底座的 apply_breaks() 是整图标记，`col` 只参与去重 ——
    #    写了会造成「按列登记了红线」的错觉。哪条线受影响由 _SEG_LINE_NOTE 说清楚。
    'breaks': [
        # zh 只写「事件 + 日期 + 影响哪一侧」：这句会被底座**逐图重复**印进每一张有连续
        # 横轴的图注（本页 4 处）再加页尾一处。量化的部分（NT$2,043 百万 / −3.8% /
        # +18.9% vs +24.7%）放进只出现一次的 _M_AND_A_NOTE 与 _BREAK_YOY_NOTE。
        {'month': '2020-12',
         'zh': 'USI 完成收购 Asteelflash（FAFG），自 2020-12-01 起并入 EMS 侧'
               '（影响合并与非 ATM，ATM 不受影响）'},
        {'month': '2021-12',
         'zh': '中国四厂（ASEN／ASEKS／ASEWH／Advanced Shanghai）出售予智路资本，'
               '2021-12-16 交割，本月是半个月的过渡月'
               '（影响合并与 ATM，非 ATM 不受影响）'},
    ],

    # `continuity` 不给：给不出「口径连续」的出处，而且事实相反（五条结构变化
    # + 一次 ATM 追溯重述）。见文件头【8】。底座会只陈述中性事实并加免责句。

    'format_source': '版式仿 Goldman Sachs GIR 台股月营收报告（「Hon Hai (2317.TW)」与 '
                     '「Wistron (3231.TW)」的 Exhibit 1-2），与本仓 /tsm/ 同一套底座',

    # 逐图补注：口径判断挂在读者提问的那张图底下，而不是全都堆到页尾。
    'note_extra': {
        'rev_bar': _MAIN_LINE_NOTE,
        'hist': _SEG_LINE_NOTE,
        'heat': _HEAT_EXTRA,
    },

    'notes': [
        _SPLIT_NOTE,
        _CALIBER_NOTE,
        _MIX_NOTE,
        _M_AND_A_NOTE,
        _BREAK_YOY_NOTE,
        _NO_FX_NOTE,
        _DAYS_NOTE,
        _YOY_SOURCE_NOTE,
        _NO_GUIDANCE_NOTE,
        _SRC_NOTE,
    ],
}
