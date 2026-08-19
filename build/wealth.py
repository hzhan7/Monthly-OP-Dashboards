# -*- coding: utf-8 -*-
"""财富 / 券商组横截面：SCHW / LPLA / IBKR（+ HOOD，仅在口径可比的图上）。

移植自 build/build_group_wealth.py（matplotlib → PDF），产出 data/wealth.js。

## 横截面页与单票页的三条不同规矩

1. **发布门槛取「共同最新月」，不是各家自己的最新月。**
   各家披露节奏散在次月 1–20 日：IBKR 次月首个交易日、SCHW 次月 12–14 日、
   LPLA 次月中下旬。若每家都画到自己的最新月，同一张图上 IBKR 到 7 月、LPL 到 5 月，
   末端那两个月的「谁强谁弱」全是披露时点造成的假象。所以整页统一截到
   **成员中最慢的那一家**，页脚点名短板是谁、它自己更新到哪个月 ——
   不写这一条，读者会以为整页都是最新的。

2. **共同最新月算不出来时，不写半张页。** 有成员还没建好（CSV 缺失 / 缺列 / 全空）
   就打印说明并**以退出码 0 正常结束**：monthly_run.py 的 build_cross() 会在成员齐了
   之后重跑，这不是失败。

3. **不可比就不入图。** 一张图里少一家，图注必须写清楚为什么少 ——
   横截面页的全部价值就在「这几个数真的能并排放」，硬塞一个口径不同的数比缺一家更糟。

## HOOD 的取舍（本次新增成员）

入图（口径确实可比）：
  · 客户资产 —— HOOD total platform assets ⇄ SCHW/LPL total client assets ⇄ IBKR client equity
  · 净流入   —— HOOD net deposits ⇄ SCHW core NNA ⇄ LPL organic NNA（都是客户净转入，
                都按「当月流量 x 12 / 上月末资产」年化，HOOD 自家披露口径也是这个）
  · 日均交易 —— HOOD DATs（股票+期权+加密之和）⇄ SCHW DATs ⇄ IBKR total client DARTs
                （IBKR 披露的总量口径，含未在 IBKR 清算的客户 —— 与另两家的客户总成交
                笔数可比；IBKR 单页那条 implied cleared DARTs 是另一个更窄的推导口径）
  · 融资余额 —— HOOD margin book ⇄ SCHW month-end margin ⇄ IBKR margin loans

不入图：
  · 客户现金 —— HOOD 把客户现金拆成 cash sweep（扫到合作银行，表外）与 cash and
                deposits（留在券商）两条线，不发布同一口径的合计；取任一条与 LPL 的
                client cash（ICA + MMF + DCA 合计）、IBKR 的 client credits 并排，
                不是漏计就是重复计。故该图只缺它一家。

⚠ **Schwab 曾以「月报不单列客户现金」为由被排除在客户现金两张图之外 —— 那句话是错的**
（2026-08-19 回原件核掉）。月报 Selected Balances 块里逐月印着 Transactional Sweep Cash
与 Total Money Market Funds 两条月末 $bn，Client Activity 块下面还有一行
Client Cash as a Percentage of Client Assets（自 2014-06 起每期都印）。抓不到只是因为
`fetch/schw.py` 的 `COLS` 里没写这三行。三列已补进 `series/schw.csv`
（`python3 fetch/schw.py --columns`），两张图都已把 Schwab 接进来。
  · 三家的长历史重定基图 —— HOOD 的月度经营指标最早只到 2021-01（天花板的举证见下），
                够不到 SCHW/LPL/IBKR 共同的 2016-01 基期；另出一张四家同基期的图。

## 窗口：一图一个左端，由数据现算，**没有统一的起点**（2026-08-19 改）

本页原先所有近期多线图都写死 `win=25`（照搬原 deck 的 `win=25`），而各家的序列
早已回补到 2016-01（IBKR / LPL）与 2013-09（SCHW）。回补了却只画近两年，等于回补给谁看。
现在窗口一律由**数据自己**定：左端取「本图各条线里最早那条的首个有值月」，右端是共同最新月。

⚠ 不要在这里、图注里或页尾写「本页一律从 20XX 起」——**那句话是假的**，而且是本页
自己造出来的假：左端既然逐图现算，各图就必然不同（本轮实际落在 Jun-14 到 Feb-21
之间的好几个月上，逐图清单由页尾说明现算印出）。写全称断言之前先真的去数一遍。

一张图能不能带前导 null，由**图型**决定，不由写图的人挑：`lines_endlabels` 属
`mrwin.DENSE`（Catmull-Rom 平滑 + 无条件取 `values[0]` 做左端标签），数组里有一个 null
就画出假线并抛异常；`lines` 走 `doSmooth=false` 的那一支，null 是断笔、末点标签走
`lastFinite`，可以带前导 null。所以：

  · 各线**起点相同**（Ex9 / Ex13：LPL 与 IBKR 都从 2016-01 起）→ 保留 `lines_endlabels`；
  · 各线**起点不同**（Ex4 / Ex5 / Ex7 / Ex8 / Ex10 / Ex12）→ 换成 `lines` + `end_label`，
    短的那家前段留 null、线从它自己的首月起画。

**不为了迁就短的那条去砍长的那条**：Schwab 的月末融资余额只有 2025-01 起，若照旧按
「各线都有值的连续末段」取窗口，IBKR 那条 2016-01 起的 125 个月就被砍成 17 个月 ——
把缺口的成本转嫁给了完整序列（同一条理由与判法见 build/hkex.py 的 Exhibit 5）。

数据源：series/{schw,lpla,ibkr,hood}.csv，均由各家自己的 fetch 模块维护，本脚本只读不写。
所有数值与格式化都在这里算完，页面不做任何计算。构建日期只写文件首行注释，不进 payload。
"""
import ast
import datetime
import json
import math
import os
import re
import sys

import numpy as np
import pandas as pd

import axisfmt                      # 引擎 ticks() 的 Python 复算，只调用不修改（Exhibit N_ORG 截轴用）
import brief as B                   # 顶部 brief 的规则库（R1-R6），只算事实、不产文字
import mrwin                        # 窗口/排版的边界裁决，只调用不修改（DENSE 集合、layout_all）
import payload_guard
import pctile                       # 3Y %ile 的唯一实现，各页不许各写各的（CONTRACT §2）
import yoy                          # 同比口径的唯一实现（build/yoy.py），本页不另写一份

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')


def load_source_dates():
    """按路径加载仓库根的 source_dates.py（官方发布日台账）。

    不能裸 import：`python3 build/wealth.py` 跑起来时 sys.path 上只有 build/。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

SRC = ('Source: company monthly disclosures (Schwab Monthly Activity Report, '
       'LPL monthly activity report, IBKR brokerage metrics, Robinhood monthly operating data)')

# 成员定义：ticker → (显示名, 颜色, 该家「有没有数据」的判定列, 是否必需)
# 必需 = 缺了就不出页；HOOD 是后加的成员，缺了就退回原来的三家。
MEMBERS = [
    ('schw', 'Schwab',    'NAVY',  'total_client_assets_usdbn',   True),
    ('lpla', 'LPL',       'RED',   'total_assets_usdbn',          True),
    ('ibkr', 'IBKR',      'MBLUE', 'equity',                      True),
    ('hood', 'Robinhood', 'GREEN', 'total_platform_assets_usdbn', False),
]

# LPL 有机口径：官方在同一页披露的 Acquired NNA，与 build/lpla.py 的 ACQ 表逐条一致。
# 它不是 series/lpla.csv 的一列（月报正文里的一次性说明），所以两处都硬编码，改一处要改两处。
# ⚠ 2026-08-18 发现这两张表已分叉 12 条（lpla 回补到 2016-01 时新增的并购月，这边没跟上）。
#   当时零影响 —— 本页 Ex5 那时还是固定 25 个月窗口、够不到最早那条 2021-04；但那正是
#   「改一处要改两处」这类约定的失效方式：不同步不报错，只等窗口一放宽就冒出一个
#   未还原的并购尖峰（2021-04 会印 +73.8bn 而不是 +6.7bn）。已补齐。
# ⚠ 2026-08-19 窗口真的放宽到序列起点了，这三张表（ACQ / LPL_ACQ_BRK / LPL_CAL_BRK）
#   从此**每次构建都对着 build/lpla.py 的同名表机器复核**（见 _sync_lpla()）——
#   「改一处要改两处」这句话本身拦不住任何东西，能拦住的只有一段会失败的代码。
ACQ = {'2017-12': 34.1, '2018-01': 2.5, '2018-02': 29.8, '2018-03': 3.7, '2018-04': 2.2,
       '2019-08': 2.9, '2020-10': 1.5, '2020-11': 2.5, '2021-04': 67.1, '2021-06': 1.8,
       '2021-09': 2.3, '2023-01': 3.2, '2023-03': 0.5, '2024-04': 5.0, '2024-08': 0.3,
       '2024-09': 0.3, '2024-10': 88.3, '2024-11': 0.8, '2024-12': 0.3, '2025-01': 0.1,
       '2025-02': 0.7, '2025-03': 7.1, '2025-07': 0.1, '2025-08': 275.0, '2025-12': 2.0}

# ────────────────────────── 结构性断点登记表 ──────────────────────────
# 一条序列在哪个月换了口径 / 并了表，在这里登记一次；每张图按它画的是哪几条序列
# 引用对应的清单。CONTRACT.md §5.2：口径断点必须画出来，不能靠图注文字提一句就算数；
# 反过来也成立 —— **图注声称画了线，图上就必须真有线**，所以下面的图注文案也由同一个
# 登记表生成（brk_note），断点滚出窗口时线和文案一起消失，不会剩下一句假话。
#
# 标签点名公司：单票页上整幅红线天然只指那一家，横截面页上四条线并排，不点名会被读成
# 「四家在这里都换了口径」。竖排标签越短越好（引擎从画布顶往下排，字多会压住相邻标注）。
#
# ⚠ 这张表原先只有 Atria 与 Commonwealth 两条 —— 那不是判断，是**窗口只有 25 个月**的
#   副产品：另外两笔（NPH 2017-12、Waddell & Reed 2021-04）早就写在 build/lpla.py 的
#   ACQ_BREAKS 里，只是够不到本页的窗口，于是没人发现两页的登记表不一样。窗口一放宽到
#   2016-01，它们就进画面了 —— 不补上就等于在同一条 LPL as-reported 序列上，
#   /lpla/ 判「Apr-21 不可比」而 /wealth/ 判「可比」（这正是当年 Atria 那次两页打架的复发）。
#   登记判据在 build/lpla.py 的 ACQ_BREAKS 上方，一字不改照用：
#   **当月 Acquired NNA ≥ 当月末客户资产的 5%**。不属于这四笔的条目全在 1% 以下。
LPL_ACQ_BRK = [(pd.Period('2017-12', 'M'), 'LPL NPH'),            # 分批至 2018-04，合计 $72.3bn
               (pd.Period('2021-04', 'M'), 'LPL W&R'),            # +$67.1bn，约上月末资产 7.0%
               (pd.Period('2024-10', 'M'), 'LPL Atria'),          # +$88.3bn，约当月资产 5.3%
               (pd.Period('2025-08', 'M'), 'LPL Commonwealth')]   # +$275.0bn，约 12.1%
# LPL 的**口径**断点（不是并表）：官方改了定义。同 build/lpla.py 的 CAL_BREAKS，
# 两族分开 —— 把现金那条画到 NNA 图上等于告诉读者「这里不可比」而那条线一点没受影响。
# 这两条也是窗口放宽之后才第一次进到本页的图里。
LPL_NNA_CAL_BRK = [(pd.Period('2019-05', 'M'), 'LPL NNA 定义')]
LPL_CASH_CAL_BRK = [(pd.Period('2019-04', 'M'), 'LPL 现金口径')]
# Schwab core NNA：单一客户异常流入的剔除门槛 2025-01 起从 $10bn 提到 $25bn，月报不重述
# 历史（口径与月份同 build/schw.py 的 BRK，改一处要改两处）。
SCHW_NNA_BRK = [(pd.Period('2025-01', 'M'), 'SCHW $10→$25bn')]
# Robinhood：口径与月份同 build/hood.py 的 BK_ND / BK_CUST / BK_TPA。
HOOD_ND_BRK = [(pd.Period('2025-06', 'M'), 'HOOD Bitstamp'),
               (pd.Period('2026-03', 'M'), 'HOOD TradePMR'),
               (pd.Period('2026-06', 'M'), 'HOOD WonderFi')]
HOOD_CUST_BRK = [(pd.Period('2025-06', 'M'), 'HOOD Bitstamp'),
                 (pd.Period('2026-06', 'M'), 'HOOD WonderFi')]
HOOD_TPA_BRK = [(pd.Period('2026-06', 'M'), 'HOOD WonderFi')]

# 「客户资产」这一族图（重定基与 y/y）同时受 LPL 的两次并表与 Robinhood 的 WonderFi 影响，
# 所以三张图引用同一个合集，不各拼各的。
ASSET_BRK = LPL_ACQ_BRK + HOOD_TPA_BRK

# 每个断点在图注里的说法。键就是上面的 Period，保证「画了哪条线」与「图注说了哪条」
# 出自同一个来源。
BRK_TXT = {
    pd.Period('2017-12', 'M'): 'LPL 2017-12 起分批并入 NPH（至 2018-04，Acquired NNA 合计 '
                               '+$72.3bn；线画在第一笔落地的那个月，因为那根点本身就已含并表）',
    pd.Period('2021-04', 'M'): 'LPL 2021-04 并入 Waddell & Reed（Acquired NNA +$67.1bn）',
    pd.Period('2024-10', 'M'): 'LPL 2024-10 并入 Atria（Acquired NNA +$88.3bn）',
    pd.Period('2025-08', 'M'): 'LPL 2025-08 并入 Commonwealth（Acquired NNA +$275.0bn）',
    pd.Period('2019-05', 'M'): 'LPL 2019-05 起 Total NNA 改为「净流入 + 股息利息 − 投顾费」'
                               '（官方 2020-04 期脚注），左侧是只含净流入的老定义',
    pd.Period('2019-04', 'M'): 'LPL 2019-04 起客户现金改用 Total Client Cash Balances'
                               '（含 purchased money market funds），左侧是只含 ICA + DCA + MMA 的 '
                               'Total Cash Sweep Balances',
    pd.Period('2025-01', 'M'): 'Schwab 2025-01 起把单一客户流入的剔除门槛从 $10bn 提到 $25bn'
                               '（月报不重述历史）',
    pd.Period('2025-06', 'M'): 'Robinhood 2025-06 起把 Bitstamp 并入净流入与客户数',
    pd.Period('2026-03', 'M'): 'Robinhood 2026-03 起把 TradePMR 顾问资产的流量并入净流入',
    pd.Period('2026-06', 'M'): 'Robinhood 2026-06 并入 WonderFi（带进约 30 万 funded customers）',
}


def _periods_in(node):
    """AST 子树里所有 `pd.Period('YYYY-MM', 'M')` 的月份，按出现顺序。"""
    out = []
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Call) and getattr(sub.func, 'attr', None) == 'Period'
                and sub.args and isinstance(sub.args[0], ast.Constant)):
            out.append(sub.args[0].value)
    return out


def _sync_lpla():
    """把上面三张 LPL 表对着 build/lpla.py 的同名表逐条复核，不一致就停更。

    为什么读源码而不是 `import lpla`：build/lpla.py 是脚本式模块，import 会把整页
    重跑一遍（读 CSV、建 payload、写文件）。这里只要三个**字面量**，用 ast 取，
    不执行任何一行 lpla 的代码。

    为什么值得写：ACQ 表已经分叉过一次（12 条，见上方注释），而分叉的表现是
    **什么都不发生** —— 直到某天窗口一放宽，图上冒出一个没还原的并购尖峰。
    「改一处要改两处」是给人看的约定，这段是给机器执行的那一份。
    取不到 build/lpla.py（单跑本文件、或 lpla 被重构）就跳过而不是硬失败：
    复核是护栏，护栏不该成为本页停更的新理由。
    """
    p = os.path.join(HERE, 'lpla.py')
    if not os.path.exists(p):
        return
    src = open(p, encoding='utf-8').read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return
    lit = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        name = getattr(node.targets[0], 'id', None)
        if name not in ('ACQ', 'ACQ_BREAKS', 'CAL_BREAKS'):
            continue
        seg = ast.get_source_segment(src, node.value) or ''
        if name == 'ACQ':
            try:
                lit['ACQ'] = ast.literal_eval(node.value)
            except ValueError:
                return
        elif name == 'ACQ_BREAKS':
            # 有 pd.Period(...) 调用，literal_eval 吃不下；只取月份（标签文案两页本来就
            # 不同：本页要点名公司，单票页不用）。**按 AST 逐条取，不用正则扫整段** ——
            # 正则一遇上嵌套结构（CAL_BREAKS 是 dict of list）就会把两族的月份混成一堆。
            lit[name] = _periods_in(node.value)
        elif name == 'CAL_BREAKS' and isinstance(node.value, ast.Dict):
            lit['CAL_FAM'] = {k.value: _periods_in(v)
                              for k, v in zip(node.value.keys, node.value.values)
                              if isinstance(k, ast.Constant)}
    bad = []
    if 'ACQ' in lit and lit['ACQ'] != ACQ:
        bad.append(f'ACQ 表与 build/lpla.py 不一致：本页多 '
                   f'{sorted(set(ACQ) - set(lit["ACQ"]))}、少 {sorted(set(lit["ACQ"]) - set(ACQ))}、'
                   f'值不同 {sorted(k for k in set(ACQ) & set(lit["ACQ"]) if ACQ[k] != lit["ACQ"][k])}')
    if 'ACQ_BREAKS' in lit:
        mine = [str(p_) for p_, _l in LPL_ACQ_BRK]
        if sorted(mine) != sorted(lit['ACQ_BREAKS']):
            bad.append(f'并表断点登记不一致：本页 {sorted(mine)} vs '
                       f'build/lpla.py {sorted(lit["ACQ_BREAKS"])}')
    for fam, tbl in (('nna', LPL_NNA_CAL_BRK), ('cash', LPL_CASH_CAL_BRK)):
        want = lit.get('CAL_FAM', {}).get(fam)
        if want is None:
            continue
        mine = sorted(str(p_) for p_, _l in tbl)
        if mine != sorted(want):
            bad.append(f'口径断点（{fam} 族）不一致：本页 {mine} vs build/lpla.py {sorted(want)}')
    if bad:
        raise SystemExit('wealth 与 lpla 的断点/并购登记表已分叉：\n  ' + '\n  '.join(bad)
                         + '\n判据与原文在 build/lpla.py 的 ACQ_BREAKS / CAL_BREAKS 上方，'
                           '两边同步之后再跑。')


_sync_lpla()


def _hood_darts_until():
    """从 build/hood.py 读 `DARTS_UNTIL` 的字面量（AST，不 import、不执行那一页）。

    为什么要跨页读而不是在这里再写一个月份：hood 页的 dats_* 三列在这个月份及更早装的
    是 **DARTs**（Daily Average *Revenue* Trades），build/hood.py 在它上方明写这件事
    「必须写在图注里，不能让读者以为整条线一把尺子」，并把 DATS_CALIBER 挂在它自己的
    Exhibit 11 与页尾说明上。本页 Exhibit N_DATS 画的是同一条线 —— 旧窗口（Jan-25 起
    十几个月）整段都在 DATs 口径内，所以以前不漏；窗口一放宽就把 DARTs 那一段拖了进来，
    而图注一个字没提（落在窗口内的月数在图注里现算，这里不写死）。这正是 _sync_lpla() 拦下来的那种「两页对同一条序列给出不同
    可比性判断」，只是当时只给 LPL 做了机器复核，没给 HOOD 做。读不到就返回 None，
    图注里那半句缺席 —— 护栏不该成为本页停更的新理由（同 _sync_lpla 的处理）。
    """
    fp = os.path.join(HERE, 'hood.py')
    if not os.path.exists(fp):
        return None
    try:
        tree = ast.parse(open(fp, encoding='utf-8').read())
    except SyntaxError:
        return None
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and getattr(node.targets[0], 'id', None) == 'DARTS_UNTIL'):
            got = _periods_in(node.value)
            if got:
                return pd.Period(got[0], 'M')
    return None


HOOD_DARTS_UNTIL = _hood_darts_until()


def _hit(idx, events):
    """窗口内真正盖得到的断点：[(x 索引, 竖排标签, Period), …]，按 x 升序。"""
    lst = list(idx)
    return sorted(((lst.index(p), lab, p) for p, lab in events if p in lst),
                  key=lambda h: h[0])


def brks(idx, events):
    """把结构性断点映射到给定窗口的 x 索引，返回可直接展开进 exhibit dict 的片段。

    窗口盖不到的断点自动省略（各图窗口起点不同、dense_win 还会随披露变动，
    硬编码索引下个月就错位）；一个都盖不到就返回空 dict，图上不画、图注也不会声称画了。
    这是「优雅降级」而不是硬失败：断点终会滚出 25 个月窗口，那天页面要照常出
    （build/lpla.py 在同一处 raise SystemExit，2025-08 滚出窗口那天 LPLA 页会永久停更）。

    「哪几张图真的画了线」不在这里累计，由 drawn_for() 从建好的 payload 现读 ——
    累计器和图注各写一份，早晚会出现「图注说画了、图上没有」。"""
    h = _hit(idx, events)
    if not h:
        return {}
    return {'break_at': [i for i, _l, _p in h],
            'break_label': [lab for _i, lab, _p in h]}


def jump_txt(idx, events, cname, lead='并表当月的环比：', d=1):
    """断点当月这条序列跳了多少 —— 现算，不写死。

    「不可比」是个定性说法，读者真正需要的是量级；而写死的数字在补历史或修数之后
    就变成第二处口径谎言（本项目在 schw「过去 32 个季度单边降」上已经付过一次代价）。"""
    s = df[cname] if cname in df.columns else None
    if s is None:
        return ''
    out = []
    for _i, _l, p in _hit(idx, events):
        if p not in s.index or (p - 1) not in s.index:
            continue
        a, b = float(s.loc[p]), float(s.loc[p - 1])
        if not (np.isfinite(a) and np.isfinite(b)) or b == 0:
            continue
        out.append(f'{mlab(p)} {signed((a / b - 1) * 100, d, "%")}')
    return (lead + '、'.join(out) + '。') if out else ''


def dilution_txt(idx, events, cname):
    """比率图专用：断点当月这条比率掉了多少 bp，占全窗口总变动的多少。

    「不可比」对比率图还不够 —— 分子分母跳的幅度不同时，比率会**机械地**掉一截，
    读者会把它读成基本面。给出 bp 与占比，他才知道该把多少归给并购。"""
    s = df[cname] if cname in df.columns else None
    if s is None:
        return ''
    parts, jump = [], 0.0
    for _i, _l, p in _hit(idx, events):
        if p not in s.index or (p - 1) not in s.index:
            continue
        a, b = float(s.loc[p]), float(s.loc[p - 1])
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        parts.append(f'{mlab(p)} 单月 {signed((a - b) * 100, 0, "bp")}')
        jump += a - b
    if not parts:
        return ''
    lo, hi = float(s.reindex(idx).iloc[0]), float(s.reindex(idx).iloc[-1])
    txt = '、'.join(parts)
    if np.isfinite(lo) and np.isfinite(hi) and abs(hi - lo) > 1e-9:
        txt += (f'，{len(parts)} 个并表月合计 {signed(jump * 100, 0, "bp")}；'
                f'而全窗口 {mlab(idx[0])}→{mlab(idx[-1])} 一共才动了 '
                f'{signed((hi - lo) * 100, 0, "bp")} —— '
                f'并表这一块占了约 {abs(jump / (hi - lo)) * 100:.0f}%')
    return txt + '。'


def brk_note(idx, events, lead='<b>红色竖虚线 = 口径断点</b>：', tail=''):
    """图注里那句「红色竖虚线 = …」只在**真画出线**时才写，且逐条只列画出来的那几个。"""
    h = _hit(idx, events)
    if not h:
        return ''
    return lead + '；'.join(BRK_TXT[p] for _i, _l, p in h) + '。' + tail


def drawn_for(exhibits, events):
    """哪几张图上真的画了这一组断点 —— 从建好的 exhibit 列表现读，不另设累计器。"""
    labs = {lab for _p, lab in events}
    return sorted({e['n'] for e in exhibits if set(e.get('break_label') or []) & labs})


# ────────────────────────────── 读数据 + 发布门槛 ──────────────────────────────
def load(t, key):
    """读一家的 series CSV。缺文件 / 缺列 / 全空都返回 None —— 由门槛逻辑决定怎么办。"""
    p = os.path.join(SERIES, f'{t}.csv')
    if not os.path.exists(p):
        return None, f'series/{t}.csv 不存在'
    d = pd.read_csv(p)
    if 'month' not in d.columns or key not in d.columns:
        return None, f'series/{t}.csv 缺列 month/{key}'
    d['month'] = pd.PeriodIndex(d['month'], freq='M')
    d = d.set_index('month').sort_index()
    for c in d.columns:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    if not len(d[key].dropna()):
        return None, f'series/{t}.csv 的 {key} 全为空'
    return d, None


RAW, LATEST_EACH, blocked, skipped = {}, {}, [], []
for t, name, color, key, need in MEMBERS:
    d, why = load(t, key)
    if d is None:
        (blocked if need else skipped).append((t, why))
        continue
    RAW[t] = d
    LATEST_EACH[t] = d[key].dropna().index[-1]

if blocked:
    # 规矩 2：不写半张页。这不是失败 —— monthly_run 会在成员齐了之后重跑，故退出码 0。
    print('wealth 横截面页跳过：必需成员未就绪 —— ' + '；'.join(f'{t}（{w}）' for t, w in blocked))
    print('已就绪：' + (', '.join(f'{t} → {LATEST_EACH[t]}' for t in RAW) or '无'))
    print('共同最新月无法确定，不生成 data/wealth.js（成员齐了之后 monthly_run 会重跑）')
    sys.exit(0)

LATEST = min(LATEST_EACH.values())
NAME = {t: n for t, n, _c, _k, _q in MEMBERS}
COLOR = {t: c for t, _n, c, _k, _q in MEMBERS}
LAGGARDS = sorted(t for t, p in LATEST_EACH.items() if p == LATEST)
HAS = set(RAW)


def col(t, c):
    """取某家的一列并截到共同最新月；该家不在场时返回全 NaN。"""
    if t not in RAW or c not in RAW[t].columns:
        return None
    return RAW[t][c].loc[:LATEST]


# ────────────────────────────── 组装可比序列 ──────────────────────────────
IDX = pd.period_range(min(RAW[t].index[0] for t in RAW), LATEST, freq='M')
df = pd.DataFrame(index=IDX)


def put(name, s):
    df[name] = s.reindex(IDX) if s is not None else np.nan


put('schw_assets', col('schw', 'total_client_assets_usdbn'))
put('lpla_assets', col('lpla', 'total_assets_usdbn'))
put('ibkr_assets', col('ibkr', 'equity'))
put('hood_assets', col('hood', 'total_platform_assets_usdbn'))

put('schw_flow', col('schw', 'core_nna_usdbn'))
_lp_nna = col('lpla', 'nna_total_usdbn')
if _lp_nna is not None:
    _acq = pd.Series({pd.Period(k, 'M'): v for k, v in ACQ.items()}).reindex(_lp_nna.index).fillna(0.0)
    put('lpla_flow', _lp_nna - _acq)
    put('lpla_nna_raw', _lp_nna)
    put('lpla_acq', _acq)
else:
    put('lpla_flow', None)
put('hood_flow', col('hood', 'net_deposits_usdbn'))

put('lpla_cash', col('lpla', 'client_cash_usdbn'))
put('ibkr_cash', col('ibkr', 'credits'))
# Schwab 的客户现金 = 月报 "Selected Balances" 块里两条月末 $bn 之和
# （Transactional Sweep Cash + Total Money Market Funds）。**这不是估算**：官方在同一
# 张表上另印一行 Client Cash as a Percentage of Client Assets，(sweep + MMF) ÷ Total
# Client Assets 逐月复现它 —— 下面 _SCHW_CASH_ID 就地核，超差直接停建，不带着走。
# 两条分量 2026-01 那期月报才新增、回填到 2025-01（同 DATs / 月末融资余额，
# 见 fetch/schw.py 的 _DATS_MARGIN_FROM）；占比那一行则自 2014-06 起每期都印。
_schw_sweep, _schw_mmf = col('schw', 'sweep_cash_usdbn'), col('schw', 'mmf_usdbn')
put('schw_cash', (_schw_sweep + _schw_mmf)
    if (_schw_sweep is not None and _schw_mmf is not None) else None)

put('schw_margin', col('schw', 'margin_balances_usdbn'))
put('ibkr_margin', col('ibkr', 'margin'))
put('hood_margin', col('hood', 'margin_book_usdbn'))

put('schw_dats', col('schw', 'dats_k'))
put('ibkr_dats', col('ibkr', 'darts'))
# HOOD 官方单位是 mn trades/day，三条分市场线；这里换成 k 与另外两家同轴
_he, _ho, _hc = (col('hood', 'dats_equity_mn'), col('hood', 'dats_options_mn'),
                 col('hood', 'dats_crypto_mn'))
put('hood_dats', (_he + _ho + _hc) * 1000.0 if _he is not None else None)
put('hood_dats_mn', (_he + _ho + _hc) if _he is not None else None)

put('ibkr_accounts', col('ibkr', 'accounts'))
put('hood_accounts', col('hood', 'funded_customers_mn'))

# 派生：年化有机增速（当月净流入 x 12 / 上月末资产）、资产 y/y、账户 y/y、
#       融资余额与客户现金占客户资产的比重
for t in ('schw', 'lpla', 'hood'):
    df[f'{t}_org'] = df[f'{t}_flow'] * 12 / df[f'{t}_assets'].shift(1) * 100
    # 同一指标的**滚动 12 个月口径**：滚动 12 个月净流入 ÷ 12 个月前的月末资产。
    # 分子已是一整年的流量，不用再乘 12。这不是「把 12 个月的比率平均」（那对比率
    # 没有意义），而是分子分母各自滚动再相除 —— 出来的是真实的「过去一年的有机增速」。
    # 本页图上画的仍是单月年化（GS 的流量口径规矩，与各单票页的柱一致），
    # 这一列只用来在图注里给出对照读数与实测波动，见 Exhibit N_ORG / N_ORG_HOOD。
    df[f'{t}_org_roll'] = (df[f'{t}_flow'].rolling(12).sum()
                           / df[f'{t}_assets'].shift(12) * 100)
for t in ('schw', 'lpla', 'ibkr', 'hood'):
    df[f'{t}_yoy'] = df[f'{t}_assets'].pct_change(12) * 100
for t in ('ibkr', 'hood'):
    df[f'{t}_acct_yoy'] = df[f'{t}_accounts'].pct_change(12) * 100
for t in ('schw', 'ibkr', 'hood'):
    df[f'{t}_mgn_pct'] = df[f'{t}_margin'] / df[f'{t}_assets'] * 100
for t in ('lpla', 'ibkr'):
    df[f'{t}_cash_pct'] = df[f'{t}_cash'] / df[f'{t}_assets'] * 100
# Schwab 的现金占比**不现除**，取官方自己印的那一行：它自 2014-06 起每期都印，
# 比 sweep / MMF 两条分量（2025-01 起）长十年多。能拿到 as-reported 就不要自己算 ——
# 自己算只会把这条线砍到分量的起点，还多担一层口径解释的责任。
put('schw_cash_pct', col('schw', 'client_cash_pct'))

# 恒等式自检：(sweep + MMF) ÷ 客户资产 必须复现官方印的占比。三个数都出自同一张表，
# 这一步核的不是「算得对不对」，而是**三行有没有各自取对**（fetch 侧 COLS 的前缀
# 匹配一旦被官方改标签带偏，这里会立刻炸，而不是让图上多出一条静默错位的线）。
# 容差 0.07pp = 占比印到 0.1pp + 两个分量各印到 0.1bn 的印刷精度。
_SCHW_CASH_ID = df[['schw_cash', 'schw_assets', 'schw_cash_pct']].dropna()
if len(_SCHW_CASH_ID):
    _d = float((_SCHW_CASH_ID['schw_cash'] / _SCHW_CASH_ID['schw_assets'] * 100
                - _SCHW_CASH_ID['schw_cash_pct']).abs().max())
    if _d > 0.07:
        raise SystemExit(
            f'Schwab 客户现金三行对不上：(sweep+MMF)/资产 与官方印的占比最大差 {_d:.3f}pp '
            f'（容差 0.07pp，{len(_SCHW_CASH_ID)} 个重叠月）。'
            '先去 fetch/schw.py 核 _LABEL 的三个前缀是不是被官方改标签带偏了，'
            '不要把这条线画上去。')


# ────────────────────── Exhibit 编号：先排好，再让图注引用变量 ──────────────────────
# 写死编号的代价这一页已经付过：图注里的「见 Exhibit 5」「Exhibit 14 热力矩阵」
# 在中间插一张图之后会全部指错，而那种错没有任何自动检查拦得住。编号只在这里生成一次，
# 正文一律引用常量；成员或某条序列缺席时它那张图不出，编号往前接，不留空号。
def _live(cname):
    return cname in df.columns and bool(np.isfinite(df[cname].values.astype(float)).any())


_seq = iter(range(2, 99))
N_REB18 = next(_seq)                                  # 三家长历史重定基（基期现算）
N_REB23 = next(_seq)                                  # 四家同基期重定基（基期现算 = HOOD 首月）
N_YOY = next(_seq)                                    # 客户资产 y/y
N_ORG = next(_seq)                                    # 年化有机增速：Schwab vs LPL
N_ORG_HOOD = next(_seq) if _live('hood_org') else None   # 年化有机增速：Robinhood（另一量级）
N_ACCT = next(_seq)                                   # 账户增速
N_MGN = next(_seq)                                    # 融资余额
N_CASH = next(_seq)                                   # 客户现金
N_DATS = next(_seq)                                   # 日均交易
N_REB19 = next(_seq)                                  # 2019 基期资产负债表重定基
N_MGNPCT = next(_seq)                                 # 融资余额 / 客户资产
N_CASHPCT = next(_seq)                                # 客户现金 / 客户资产
# 热力矩阵：某家的 y/y 全空时那张图根本建不出来（heat() 返回 None），编号也不该占。
N_HEAT = {t: next(_seq) for t in ('schw', 'lpla', 'ibkr', 'hood')
          if t in HAS and _live(f'{t}_yoy')}
N_TABLE = next(_seq)                                  # 页尾核对表


# ────────────────────────────── 格式化零件 ──────────────────────────────
def mlab(p):
    return p.strftime('%b-%y')


def comma(v, d=0):
    return f'{_nz(v, d):,.{d}f}'


def _nz(v, d):
    """四舍五入到 d 位之后正好是 0 的负数回正 —— 否则印出「-0」「-0.0%」「-0bp」。

    Python 的 f-string 是先取符号再四舍五入的：f'{-0.004:+.1f}%' → '-0.0%'。
    读者看到的是一个带负号的零，会当成「跌了一点点」，而它其实是「没动」。"""
    v = float(v)
    return 0.0 if round(v, d) == 0 else v


def signed(v, d, suffix):
    """带正负号的数。四舍五入后正好是零时连符号一起去掉 —— 「+0bp」同样是假消息，
    它宣称的是一个方向，而这个数只是「没动」。"""
    v = _nz(v, d)
    return f'{v:+,.{d}f}{suffix}' if v else f'{0:,.{d}f}{suffix}'


def money(v, d=0):
    return '$' + comma(v, d)


def L(a):
    """序列 → JSON 数组；非有限值一律写 null（图与表都断开，不画假点）。"""
    return [None if v is None or not np.isfinite(float(v)) else round(float(v), 6) for v in a]


def has(name, idx=None):
    """该列在（指定窗口的）范围内是否真有值。没有就不入图，而不是画一条空线。"""
    s = df[name] if idx is None else df[name].reindex(idx)
    return bool(np.isfinite(s.values.astype(float)).any())


def sr(items, idx, dense):
    """把 (ticker, 列名, 图例名) 列表变成 series 数组。

    返回 (series, 入图公司名, 未入图公司名, 迟到的腿)。「迟到」= 该线在窗口左端还没有值，
    前段留 null；图注必须逐条点名它从哪个月起画 —— 不点名，读者会把一条从中间冒出来的线
    读成「这家在那之前是零」。

    `dense=True`（`lines_endlabels`）时窗口内缺一个点就整条不入图：那是引擎的硬约束，
    见 plan() 的 docstring。`dense=False`（`lines`）时只要窗口内有一个有效点就入图。
    """
    out, inc, exc, late = [], [], [], []
    for t, cname, legend in items:
        s = df[cname].reindex(idx) if (t in HAS and cname in df.columns) else None
        v = np.isfinite(s.values.astype(float)) if s is not None else None
        if s is None or not v.any() or (dense and not v.all()):
            exc.append(NAME.get(t, t.upper()))
            continue
        out.append({'name': legend, 'color': COLOR[t], 'values': L(s.values)})
        inc.append(NAME[t])
        if not v.all():
            late.append((legend, idx[int(np.argmax(v))], int(v.sum())))
    return out, inc, exc, late


def _cols(items):
    """入图候选列：该家在场、列在、且**在共同最新月有值**。

    在 LATEST 没有值的列一概不入图 —— 一条画到一半就停的线，读者分不清是「停发了」
    还是「本页截断了」。"""
    return [c for t, c, _ in items
            if t in HAS and c in df.columns and np.isfinite(df[c].loc[LATEST])]


def _first(cname):
    """某列首个有值月；整列全空返回 None。"""
    v = np.isfinite(df[cname].values.astype(float))
    return IDX[int(np.argmax(v))] if v.any() else None


def _dense_first(cname):
    """某列**末端连续段**的首月 —— 中段有洞时取洞右边的那一格。

    `lines_endlabels` 吃不了洞（不只是前导 null），所以判起点要按稠密段算，
    不能按首个有值点算（这一条与 mrwin._dense_first 同义）。"""
    v = np.isfinite(df[cname].values.astype(float))
    if not v.any():
        return None
    k = 0
    for i in range(len(v) - 1, -1, -1):
        if not v[i]:
            break
        k += 1
    return IDX[len(v) - k]


def plan(items):
    """给一组腿裁决「窗口 + 图型」，返回 (idx, kind, dense)。

    本页所有近期多线图原先都写死 `win=25`。那个 25 不是数据的边界，是原 deck 的排版
    习惯；各家序列早已回补到 2016-01（IBKR / LPL）与 2013-09（SCHW）。现在左端一律
    由数据定 = **本图各条线里最早那条的首个有值月**。

    图型由「各线起点齐不齐」决定，不由人挑：

      · 齐 → `lines_endlabels`（属 `mrwin.DENSE`：整条 values 交给 Catmull-Rom 平滑、
        两端无条件取 `values[0]` / `values[n-1]` 标数值，数组里有一个 null 就画出一条
        塌到零的假线并抛异常，该卡片之后的 exhibit 全不渲染）。
      · 不齐 → `lines` + `end_label`（走 `doSmooth=false` 那一支，null 是断笔；
        末点标签走 `lastFinite`）。短的那家前段留 null，**不补零、不前向填充、不外推**。

    为什么不像从前那样一律取「各线都有值的连续末段」：那等于**为了迁就短的那条去砍长的
    那条**。Schwab 的月末融资余额、DATs、月末 sweep cash 与月末货基都只有 2025-01 起
    （2026-01 期月报一次新增这四列并回填至此，见 fetch/schw.py 的 `_DATS_MARGIN_FROM`），
    照旧判法，凡是带这批列的图窗口就都只剩十几个月，而同图 IBKR 那条有十年、
    Robinhood 有五年，全被砍掉。
    同一条理由与判法见 build/hkex.py 的 Exhibit 5（南向停发 42 个月，不砍整体 ADT）。
    """
    cols = _cols(items)
    if not cols:
        return IDX[-1:], 'lines_endlabels', True
    lo = min(_first(c) for c in cols)
    dense = all(_dense_first(c) == lo for c in cols)
    return pd.period_range(lo, LATEST, freq='M'), ('lines_endlabels' if dense else 'lines'), dense


def win_note(idx, kind, late, nser=0):
    """窗口与图型的说明。左端为什么在这里、谁的线前段是空的，逐条现算。"""
    s = (f'<b>窗口 {mlab(idx[0])}–{mlab(idx[-1])}（{len(idx)} 个月）= 本图各条线合起来'
         f'覆盖到的最长历史</b>，不是「近 N 个月」—— 本页原先所有近期多线图都写死 25 个月，'
         '那是原 deck 的排版习惯，不是数据的边界。')
    if late:
        s += ('图上有线的前段是空的，<b>那是没有披露，不是零</b>：'
              + '；'.join(f'{nm} 自 {mlab(p)} 起画（{n} 个月）' for nm, p, n in late)
              + '。引擎在缺口处断笔，不补零、不前向填充、不外推 —— '
                '若把短的那条对齐到图的左缘，读者会把两条起点完全不同的线读成同期对比。')
        # 「最左那一段图上只有几条线」要直接说出来 —— 横截面页上一条孤零零的线跑很远，
        # 读者会以为另外几家那时是零 / 是我们漏画了，而不是「那时它们还没有披露」。
        gap = (min(p for _n, p, _c in late) - idx[0]).n
        full_at = max(p for _n, p, _c in late)
        if gap > 0 and nser:
            s += (f'合起来就是：图的最左 {gap} 个月只有 {nser - len(late)} 条线，'
                  f'要到 {mlab(full_at)} 才凑齐 {nser} 条（'
                  f'即全轴 {len(idx)} 期里的第 {(full_at - idx[0]).n + 1} 期）—— '
                  '左段的「谁高谁低」不成立，那里根本没有可比的对象。')
    if kind == 'lines':
        s += ('本图型是 <code>lines</code>（折线断笔 + 末点标数值）而不是本页多数图用的 '
              '<code>lines_endlabels</code>：后者属平滑图型，整条数组交给 Catmull-Rom 插值、'
              '两端无条件取首末值标数字，序列里有一个 null 就画出假线并抛异常。'
              '要保住起点不同的线，只能换图型 —— 换回去就得把长的那条砍到短的那条的起点。')
    return s


def firms_note(inc, exc, why=''):
    s = '本图含 ' + ' / '.join(inc) + '。'
    if exc:
        s += '未入图：' + ' / '.join(exc) + '。'
        if why:
            s += why
    return s


def xls(idx, step=None):
    return [mlab(p) for p in idx]


# ────────────────── 同比口径：数值实现一律走 build/yoy.py ──────────────────
# 本页画同比的图**全部是存量序列**（客户资产、客户权益、平台资产、账户/客户存量），
# 所以一张都没有改成 12 个月滚动合计 —— 那对存量是个假名字（12 个月末余额相加不指代
# 任何真实的量）。但要说清楚：存量**并非不能平滑**，合法的平滑口径是
# 12 个月滚动**均值**同比（去年一整年的平均资产 vs 前年），数值上等同于滚动合计比
# （Σ12/Σ12′ 的除数约掉）。本页仍用点对点，理由由**逐条实测**给出。
# ⚠ 不要在这里（或任何注释、docstring、页尾散文里）写死「哪一条最吵、差几倍」：
# 那个结论随窗口翻面。25 个月窗口下 IBKR 账户数是「均值口径反而更吵」，
# 113 个月窗口下同一条线变成「均值口径更稳」。现算的实现见 stock_caliber_note()
# 与 caliber_evidence()。
def stock_pair(cname, idx):
    """某条存量序列在给定窗口上「点对点同比 vs 12 个月均值同比」的实测对比。

    ⚠ **必须先对齐到两种口径都算得出的同一批月份**：均值口径天然少掉头 12 个月，
    不对齐就是拿两个不同样本比波动，样本效应会伪装成口径效应。
    """
    if cname not in df.columns:
        return None
    s = df[cname]
    A = yoy.mom_yoy(s, yoy.STOCK)
    B = yoy.ttm_mean_yoy(s, yoy.STOCK)
    keep = [p for p in idx if p in A.index and np.isfinite(A.loc[p]) and np.isfinite(B.loc[p])]
    if len(keep) < 3:
        return None
    a, b = A.loc[keep].astype(float), B.loc[keep].astype(float)
    jump = lambda x: float(np.abs(np.diff(x.values)).max()) if len(x) > 1 else float('nan')
    return {'n': len(keep), 'sd_m': float(a.std(ddof=0)), 'sd_r': float(b.std(ddof=0)),
            'jump_m': jump(a), 'jump_r': jump(b),
            'flips': [mlab(p) for p in keep if a.loc[p] * b.loc[p] < 0],
            'cur_m': float(a.iloc[-1]), 'cur_r': float(b.iloc[-1])}


def org_caliber_note(items, idx):
    """有机增速图的口径说明：画的是**单月年化**水平值，滚动口径的读数在这里给出。

    这类图画的不是同比而是一个**增长率的水平值**，所以「单月同比 vs 滚动同比」那套
    判据不直接适用；但「当月流量 x12」这一步同样会把一个月的噪音放大 12 倍，
    所以照样要把两种口径的读数与波动并排给出，让读者自己知道该信哪个。
    """
    rows = []
    for name, t in items:
        a, b = df.get(f'{t}_org'), df.get(f'{t}_org_roll')
        if a is None or b is None:
            continue
        keep = [p for p in idx if np.isfinite(a.loc[p]) and np.isfinite(b.loc[p])]
        if len(keep) < 3:
            continue
        A, B = a.loc[keep].astype(float), b.loc[keep].astype(float)
        jump = lambda x: float(np.abs(np.diff(x.values)).max())
        rows.append(f'{name} 当期单月年化 {A.iloc[-1]:.1f}% / 滚动 12 个月 {B.iloc[-1]:.1f}%'
                    f'（窗口内逐月标准差 {A.std(ddof=0):.1f}pp vs {B.std(ddof=0):.1f}pp，'
                    f'相邻月最大跳变 {jump(A):.1f}pp vs {jump(B):.1f}pp）')
    if not rows:
        return ''
    return ('<b>口径：本图画的是「当月净流入 x 12」的<u>单月</u>年化增速</b>，'
            '与各单票页柱子的口径一致（GS LPLA 的流量口径规矩）。'
            '它把一个月的流量乘 12，所以本身是条噪声很大的线；'
            '真要读趋势请看<b>滚动 12 个月有机增速</b>（滚动 12 个月净流入 ÷ 12 个月前的'
            '月末资产 —— 注意这是分子分母各自滚动再相除，不是把 12 个月的比率平均，'
            '后者对比率没有意义）。两种口径的当期读数与波动逐家并排：'
            + '；'.join(rows)
            + '。各单票页 Exhibit 3/4 的<b>次轴</b>画的正是滚动口径的同比。')


def stock_caliber_note(items, idx, lead=''):
    """存量类图注：为什么画点对点同比而不是 12 个月均值同比。逐家现算。

    items = [(显示名, 列名), …]。数字一律现算 —— 写死的话下个月就是假话。
    """
    rows = []
    for name, cname in items:
        st = stock_pair(cname, idx)
        if not st:
            continue
        r = st['sd_m'] / st['sd_r'] if st['sd_r'] else float('nan')
        rows.append(f'{name} {st["sd_m"]:.1f}pp vs {st["sd_r"]:.1f}pp（{r:.2f} 倍'
                    + ('，均值口径<b>反而更吵</b>' if r < 1 else '')
                    + f'；符号相反 {len(st["flips"])} 个月）')
    if not rows:
        return ''
    return (lead + '本图画的是<b>点对点（单月）同比</b>（本月末 ÷ 去年同月末 − 1）。'
            '存量并非不能平滑 —— 合法的平滑口径是 <b>12 个月滚动均值同比</b>'
            '（去年一整年的平均水平 vs 前年；数值上等同于滚动合计比，除数约掉了），'
            '<b>但不能叫「12 个月合计同比」</b>，因为 12 个月末余额相加不指代任何真实的量。'
            '本图不换的理由是实测（两种口径先对齐到同一批月份，逐月标准差）：'
            + '；'.join(rows)
            + '。均值口径按构造滞后约半年、回答的是「去年一整年的平均水平」而不是'
            '「现在相对去年此刻」，而横截面页要比的正是后者；'
            '存量的分子分母又都是时点数、不含日历效应，本来就不像流量那样被小分母放大。'
            '噪声用轴范围解决。')


def caliber_evidence(items):
    """本页各条存量序列「点对点 vs 12 个月均值同比」的逐月标准差之比，按比值升序。

    items = [(显示名, 列名, 该图窗口, 该图编号), …] → [(比值, 名, sd_单月, sd_均值, 图号), …]。
    比值 < 1 = 均值口径**反而更吵**。

    ⚠ 这个函数存在的唯一原因是：**这个结论会随窗口翻面，不能写死**。
    2026-08-19 就翻过一次 —— 25 个月窗口下 IBKR 账户数是 1.7pp vs 3.0pp（0.57 倍，
    均值口径更吵），窗口放宽到 113 个月之后变成 13.9pp vs 12.5pp（1.11 倍，均值口径
    更稳）。而页尾口径说明里那句写死的「最硬的一条在 Exhibit N_ACCT：IBKR 账户数换成
    均值口径标准差反而变大」一个字没跟，于是同一页上页尾说均值更吵、Exhibit N_ACCT
    自己印的数说均值更稳，读者滚一张图就能抓到。现在页尾那句由本函数现算生成。
    """
    rows = []
    for name, cname, idx, n in items:
        st = stock_pair(cname, idx)
        if not st or not st['sd_r']:
            continue
        rows.append((st['sd_m'] / st['sd_r'], name, st['sd_m'], st['sd_r'], n))
    return sorted(rows)


# 近期多线图不再有「默认窗口」这个概念：左端由 plan() 从数据现算（原来是写死的
# `WIN = 25`，照搬原 deck 的 win=25）。仍然写死的只剩两个，各有各的理由：
# 核对表 13 个月（跨公司逐月对数用，长了没人看）、热力矩阵最多 7 年（7 x 12 的格子）。
# `lines` 图的画布高：末点标签落在点上方 7px，`spreadY` 的兜底条件是「最高的那个标签
# 顶到画布上沿」—— 命中就把整列标签收成一摞贴在右上角，与各自的线脱钩。
# 本页新扩窗的这几张里，末点很可能就是全图最高点（融资余额、DATs 都在创新高），
# 所以取 build/single.py 的 LINE_H_ENDLABEL 同一个值 360 而不是重定基图那档 340
# （340 在「末点即最高点」时只剩 0.8px 余量，`build/verify_pages.py` 的
# `endlabel_collision()` 按引擎公式复算，余量多少它会算给你看）。
LINE_H = 360
XL = [mlab(p) for p in IDX[-13:]]
XL_LONG = [mlab(p) for p in IDX]
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# ────────────────────────────── Exhibit 1：汇总表 ──────────────────────────────
CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12


def acq_roll12(idx):
    """LPL 各月的滚动 12 个月 Acquired NNA（含当月），$bn。

    还原口径在本模块只有这一处定义：y/y 用它剔分子月的并购、客户现金占比用它剔分母 ——
    两处各写各的，就会出现「同一句话在两种还原约定下结论相反」而没人发现。
    """
    s = pd.Series({pd.Period(k, 'M'): v for k, v in ACQ.items()}).reindex(idx).fillna(0.0)
    return s.rolling(12, min_periods=1).sum()


def lp_yoy_ex(d, cur):
    """LPL 客户资产 y/y 的剔并购口径 →（y/y%, 该月滚动 12 个月 Acquired NNA）。

    传 d/cur 而不是读全局，是为了能把序列截到历史任一个月重放：t12 跟着那个月的
    12 个月窗口自己变，不是写死的 $277.0bn（并表滚出窗口那天它必须自己归零）。
    算不出来（缺月、分母为零）返回 (None, None)，由调用方决定这句写不写。
    """
    yag = cur - 12
    try:
        now, ago = float(d['lpla_assets'].loc[cur]), float(d['lpla_assets'].loc[yag])
    except (KeyError, TypeError, ValueError):
        return None, None
    if not B.need(now, ago) or ago == 0:
        return None, None
    t12 = sum(v for k, v in ACQ.items() if yag < pd.Period(k, 'M') <= cur)
    return ((now - t12) / ago - 1) * 100, t12


def _lp_rank_txt():
    """LPL as-reported y/y 与剔并购后的 y/y、以及它与 Schwab 的名次关系。

    断点线告诉读者「这里不可比」，但不告诉他不可比到什么程度。当期这两个数横跨
    Schwab 时，名次是反的 —— 这句话必须给出数字，否则读者只会照着端点标签读
    LPL +38% > Schwab +27%。算不出来（缺月、缺 Schwab）就返回空串，不写半句。"""
    try:
        lp_now, lp_ago = float(df['lpla_assets'].loc[CUR]), float(df['lpla_assets'].loc[YAG])
        sc = float(df['schw_yoy'].loc[CUR])
    except (KeyError, TypeError, ValueError):
        return '', None
    if not all(np.isfinite(v) for v in (lp_now, lp_ago, sc)) or lp_ago == 0:
        return '', None
    exq, t12 = lp_yoy_ex(df, CUR)
    raw = (lp_now / lp_ago - 1) * 100
    txt = (f'{mlab(CUR)} 的 LPL 读数为 <b>{raw:+.1f}%</b>，剔掉滚动 12 个月的 Acquired NNA'
           f'（${t12:,.1f}bn）之后是 <b>{exq:+.1f}%</b>，'
           + (f'<b>低于</b> Schwab 的 {sc:+.1f}% —— 名次是反的。'
              if exq < sc else f'仍高于 Schwab 的 {sc:+.1f}%。'))
    return txt, exq


LP_RANK_TXT, LP_YOY_EX = _lp_rank_txt()
_LP_YOY_S = df['lpla_yoy'].dropna() if 'lpla_yoy' in df.columns else pd.Series(dtype=float)
_LP_YOY_NOW = float(_LP_YOY_S.iloc[-1]) if len(_LP_YOY_S) else None


def cell(v, d, kind):
    """水平值单元格。三种 kind 都走 comma()，负零才不会从某一条支路漏出去。"""
    if v is None or not np.isfinite(v):
        return '—'
    return money(v, d) if kind == '$' else (comma(v, d) + ('%' if kind == '%' else ''))


def _v0(cname, d=1, kind=''):
    """某一列的当期读数（已格式化）。图注里引用别的图的数字时用它，别再手抄一遍。"""
    s = df[cname].dropna() if cname in df.columns else pd.Series(dtype=float)
    return '—' if not len(s) else cell(float(s.iloc[-1]), d, kind)


def chg(a, b, mode, d, kind):
    """m/m、y/y 单元格。比率类用 pp/bp（GS LPLA 规矩 2），不用百分比变化。"""
    if a is None or b is None or not (np.isfinite(a) and np.isfinite(b)):
        return {'v': ''}
    if mode == 'pp':
        v = a - b
        # CONTRACT §2：abs(v) < 1 用 bp，否则用 pp。分档看的是四舍五入前的真值。
        txt = signed(v * 100, 0, 'bp') if abs(v) < 1 else signed(v, 2, 'pp')
        shown = round(v * 100, 0) if abs(v) < 1 else round(v, 2)
    else:
        if b == 0 or a * b < 0:
            return {'v': ''}
        v = a / b - 1
        txt = signed(v * 100, 1, '%')
        shown = round(v * 100, 1)
    # 颜色跟着**印出来的那个数**走：印成 +0.0% 就不涂色，否则读者会看到一个
    # 绿色的零，以为是四舍五入吃掉了一个正数。
    return {'v': txt, 'cls': 'pos' if shown > 0 else ('neg' if shown < 0 else '')}


def pctile_cell(s):
    """3Y %ile 单元格。判据与全部 14 个生成器共用 build/pctile.py，本页不自己写。

    旧实现是「36 个月里 ≥90% 月环比不降就留空」的代理判据，拦不住「上下波动但分位
    常年钉 100」的行（Schwab margin balances、IBKR client credits、Robinhood margin
    book），也与 /lpla/ 对同一条 LPL total client assets 的判定相反。"""
    v, cls = pctile.cell(_ser(s))
    return {'v': v, 'cls': cls} if v else {'v': ''}


def _ser(s):
    """pandas Series → pctile.py 吃的 [float | None] 列表（按月升序，缺月写 None）。"""
    return [None if not np.isfinite(v) else float(v) for v in s.values]


# ── implied cleared DARTs 对披露总量的覆盖率：现算，不写死 ─────────────────
# 从前这里写死「约为本图数值的 85%」。那个 85% 是按旧的 17 个月窗口（Jan-25 起）调出来
# 的，窗口放宽到 125 个月之后它在区间里是 85%–93%；而这句话本身还点名要读者去对照
# IBKR 单页 Exhibit 4/18 —— 那一页的图注是**现算**的，印的正是「85%–93%（中位 89%）」。
# 于是两页对同一个量给出两种说法。推导式与 build/ibkr.py 的 cleared_all 逐字相同
# （年化人均 cleared DART ÷ 252 × 期初期末账户均值），序列也取 IBKR 的完整历史
# （RAW 未截到共同最新月），这样两页的区间恒等，不会因为本页截断而再次分叉。
_cv_ann, _cv_acc, _cv_drt = (RAW.get('ibkr', pd.DataFrame()).get(c)
                             for c in ('ann_dart_acct', 'accounts', 'darts'))
CLEARED_COV = None
if _cv_ann is not None and _cv_acc is not None and _cv_drt is not None:
    _cv = (_cv_ann / 252.0 * (_cv_acc + _cv_acc.shift(1)) / 2.0 / _cv_drt * 100.0).dropna()
    if len(_cv):
        CLEARED_COV = (float(_cv.min()), float(_cv.median()), float(_cv.max()),
                       _cv.index[0], _cv.index[-1])
CLEARED_TXT = (
    f'约为本图数值的 {CLEARED_COV[0]:.0f}%–{CLEARED_COV[2]:.0f}%'
    f'（{mlab(CLEARED_COV[3])}–{mlab(CLEARED_COV[4])} 全区间，中位 {CLEARED_COV[1]:.0f}%）'
    if CLEARED_COV else '低于本图数值')
# 汇总表那一行的「此值」指的是**当期单月读数**（表里印的就是 CUR 那一格），所以给
# 当期覆盖率，再把全区间挂在后面 —— 只给一个数，下个月就又是一句写死的话。
CLEARED_TXT_SUM = (
    f'约为此值的 {float(_cv.loc[LATEST]):.0f}%（{mlab(LATEST)} 当期读数；'
    f'全区间 {CLEARED_COV[0]:.0f}%–{CLEARED_COV[2]:.0f}%，中位 {CLEARED_COV[1]:.0f}%）'
    if CLEARED_COV and LATEST in _cv.index else '低于此值')


SUM_ROWS = [
    ('group', 'Client assets ($bn) —— 同一单位，直接可比'),
    ('row', 'schw', 'Schwab total client assets', 'schw_assets', 0, '$', 'ratio'),
    ('row', 'lpla', 'LPL total client assets（含并购转入）', 'lpla_assets', 0, '$', 'ratio'),
    ('row', 'ibkr', 'IBKR client equity', 'ibkr_assets', 0, '$', 'ratio'),
    ('row', 'hood', 'Robinhood total platform assets', 'hood_assets', 0, '$', 'ratio'),
    ('group', 'Organic growth（%，年化）'),
    ('row', 'schw', 'Schwab core NNA growth', 'schw_org', 2, '%', 'pp'),
    ('row', 'lpla', 'LPL organic NNA growth', 'lpla_org', 2, '%', 'pp'),
    ('row', 'hood', 'Robinhood net deposit growth', 'hood_org', 2, '%', 'pp'),
    ('row', 'ibkr', 'IBKR account growth, y/y', 'ibkr_acct_yoy', 1, '%', 'pp'),
    ('group', 'Balance sheet ($bn)'),
    ('row', 'schw', 'Schwab client cash（sweep + 货基）', 'schw_cash', 1, '$', 'ratio'),
    ('row', 'lpla', 'LPL client cash', 'lpla_cash', 1, '$', 'ratio'),
    ('row', 'ibkr', 'IBKR client credits', 'ibkr_cash', 1, '$', 'ratio'),
    ('row', 'schw', 'Schwab margin balances', 'schw_margin', 1, '$', 'ratio'),
    ('row', 'ibkr', 'IBKR margin loans', 'ibkr_margin', 1, '$', 'ratio'),
    ('row', 'hood', 'Robinhood margin book', 'hood_margin', 1, '$', 'ratio'),
    ('group', 'Activity（k trades / day）'),
    ('row', 'schw', 'Schwab DATs', 'schw_dats', 0, '', 'ratio'),
    ('row', 'ibkr', 'IBKR total client DARTs（含未清算）', 'ibkr_dats', 0, '', 'ratio'),
    ('row', 'hood', 'Robinhood DATs（股票+期权+加密）', 'hood_dats', 0, '', 'ratio'),
]

srows, PCT_BLANK = [], []       # PCT_BLANK：分位留空的行，表注里点名，免得被当成漏算
for r in SUM_ROWS:
    if r[0] == 'group':
        # 汇总表的 y/y 列**不换口径**：它恒等于表内算术「本月 ÷ 去年同月」，读者拿第一列
        # 除第三列就能验算。换口径之后这一步会得出另一个数，表内自相矛盾比口径混用更糟。
        srows.append({'kind': 'group', 'label': r[1] + '　·　y/y 列 = 单月口径（本月 ÷ 去年同月）'})
        continue
    _, t, lab, cname, d, kind, mode = r
    if t not in HAS or cname not in df.columns or not has(cname):
        continue
    s = df[cname]
    get = lambda p: (float(s.loc[p]) if p in s.index and np.isfinite(s.loc[p]) else None)
    c, p1, p12 = get(CUR), get(PRV), get(YAG)
    pc = pctile_cell(s)
    if not pc['v']:
        PCT_BLANK.append(lab)
    srows.append({'label': lab, 'cells': [
        {'v': cell(c, d, kind)}, {'v': cell(p1, d, kind)}, {'v': cell(p12, d, kind)},
        chg(c, p1, mode, d, kind), chg(c, p12, mode, d, kind), pc]})

LAG = ' / '.join(NAME[t] for t in LAGGARDS)      # 短板：共同最新月就等于它自己的最新月
summary = {
    'title': f'Wealth and brokerage group —— {mlab(LATEST)}（共同最新月）',
    'heads': [mlab(CUR), mlab(PRV), mlab(YAG), 'm/m', 'y/y 单月', '3Y %ile'],
    'sep': 3,
    'rows': srows,
    'note': (f'整张表统一截到<b>共同最新月 {mlab(LATEST)}</b>，由最慢的成员 {LAG} 决定；'
             + '；'.join(f'{NAME[t]} 自身已更新到 {mlab(LATEST_EACH[t])}'
                         for t in RAW if LATEST_EACH[t] != LATEST)
             + '，这些更新的月份本页一律不画（见页脚）。'
             'LPL 既不披露融资余额也不披露交易笔数、'
             'IBKR 不披露净新增资产（只披露净新增账户），故这些行只有披露该项的公司。'
             'Schwab client cash 是月报里 Transactional Sweep Cash 与 Total Money Market '
             'Funds 两条月末余额之和（两条分量自 2025-01 起才有，见页脚）；'
             'IBKR client credits 不含货基，与另两家的水平值有系统性差异。'
             '比率类指标（年化有机增速、账户增速）的差异用 pp/bp，不用百分比变化；'
             'Robinhood DATs 官方单位为 mn，此处 x1,000 换成 k 与另两家同轴（核对表仍保留 mn 原始单位）。'
             'IBKR 那行是公司披露的 <b>Total Client DARTs</b>（含通过 IBKR 执行但不在 IBKR 清算的客户），'
             '与 Schwab / Robinhood 的客户总成交笔数同口径；公司另披露的 Cleared Avg. DART per Account '
             f'推导出的 cleared DARTs {CLEARED_TXT_SUM}，见 IBKR 单页 Exhibit 4/18，两者不要混读。'
             '3Y %ile = 当月读数在最近 36 个月里高于多少个百分比的观测。'
             '判据同全站（<code>build/pctile.py</code>，14 个生成器共用一份）：'
             '把该行的分位在<b>近 24 个月里逐月回放</b>，若 ≥70% 的月份都钉在端点（100 或 0），'
             '这一列对这一行就没有区分度，留空。'
             + (f'本轮留空的是：{"、".join(PCT_BLANK)} —— 这几行的分位近两年几乎恒为 100，'
                '印出来只会让人误以为「刚刚创下新高」。' if PCT_BLANK else '本轮没有行触发留空。')
             + '仍显示 100 的行是回放里真的下过来过的，读到 100 时也只是说'
             '「当月是近三年最高」，不代表动能。'),
}


# ────────────────────────────── Exhibit 2..N ──────────────────────────────
ex = []
GATE = (f'本页所有图统一截到共同最新月 {mlab(LATEST)}；'
        f'{LAG} 是短板，其余各家更新更早的月份本页不画。')


# 重定基图的画布高度。不是审美选择：kind:'lines' 的末点标签画在点上方 7px，而引擎的
# 竖向避让在「最高的那个标签顶到画布上沿」时会把**整列**标签压到顶端顺排 —— 于是
# 三条线的指数值全叠在右上角、与各自的线脱钩（382 看着像在标 660 那条线）。
# 该分支的上留白恒为量程的 1/22（y1 = max + 5%×极差），与数据无关，所以只要绘图区
# 高度 ≥ 约 308px，最高的标签就够不到上沿。取 340 留出余量。
REB_H = 340


def rebase(cname, base):
    """重定基到 100。基期本身缺值时整条不画 —— 拿一个 NaN 当分母会造出一整条假线。"""
    s = df[cname]
    if base not in s.index or not np.isfinite(s.loc[base]):
        return None
    return s / float(s.loc[base]) * 100


# ── 重定基图的基期：由数据定，不写死 ──────────────────────────────────────
# 从前这两个基期是硬编码的 `2018-07` 与 `2023-04`，两个都是**别处的**数字：
#   · 2018-07 照搬原 deck（build/build_group_wealth.py 的 `base='2018-07'`，
#     标题就叫 "Client assets since 2018"），本仓从来没有理由把三家的历史砍在 2018；
#   · 2023-04 当年确实是 Robinhood 月度披露的首月，但 series/hood.csv 已由
#     build/basefill/hood_2021.py 回补到 **2021-01**（Q1'23 Earnings Supplement 那一版），
#     于是「基期 = Robinhood 首月」这句理由与它选出来的月份对不上了 —— 图注说的是
#     一件事，代码做的是另一件。
# 现在两个基期都现算：**基期 = 入图各家客户资产的首个有值月里最晚的那一个**。
# 重定基图的基期天然只能取这个月（更早的月份分母是 NaN，整条线画不出来），
# 所以这不是选择，是约束；写成算式之后，序列一回补它自己就跟着往前走。
def rebase_base(tickers):
    ms = [_first(f'{t}_assets') for t in tickers
          if t in HAS and f'{t}_assets' in df.columns and _first(f'{t}_assets') is not None]
    return max(ms) if ms else IDX[0]


# ── Exhibit N_REB18：客户资产重定基（三家长历史；Robinhood 够不到这个基期）──
LONG3 = ('schw', 'lpla', 'ibkr')
B18 = rebase_base(LONG3)
I18 = pd.period_range(B18, LATEST, freq='M')
s2, inc2, exc2 = [], [], []
for t in ('schw', 'lpla', 'ibkr', 'hood'):
    r = rebase(f'{t}_assets', B18) if t in HAS else None
    if r is None or not np.isfinite(r.reindex(I18).values.astype(float)).any():
        exc2.append(NAME.get(t, t.upper()))
        continue
    s2.append({'name': NAME[t], 'color': COLOR[t], 'values': L(r.reindex(I18).values)})
    inc2.append(NAME[t])
_HOOD_F = _first('hood_assets')
ex.append({
    'n': N_REB18, 'kind': 'lines', 'fmt': 'f0', 'xlabels': xls(I18),
    'end_label': True, 'height': REB_H,
    'title': f'Client assets since {mlab(B18)}, rebased to 100',
    'ylab': f'index, {mlab(B18)} = 100',
    'series': s2,
    **brks(I18, ASSET_BRK),
    'note': (firms_note(inc2, exc2,
                        (f'Robinhood 的月度经营指标最早只到 {mlab(_HOOD_F)}（天花板的举证见'
                         f'下一张图的图注），够不到 {mlab(B18)} 的基期 —— '
                         if _HOOD_F else 'Robinhood 的月度经营指标够不到这个基期 —— ')
                        + '把它从自己的首月当 100 起画，会与另外三家比出一个纯属基期不同的假斜率；'
                          '四家同基期的版本见下一张。')
             + f'<b>基期 {mlab(B18)} 是算出来的，不是挑的</b>：'
             + '、'.join(f'{NAME[t]} 自 {mlab(_first(f"{t}_assets"))} 起'
                         for t in LONG3 if t in HAS and _first(f'{t}_assets'))
             + '，三家都有值的最早一个月就是它，更早的月份分母是空值、整条线画不出来。'
               '（此前这里写死 2018-07，那个数照搬原 deck 的版式，与本仓的序列长度无关。）'
             + brk_note(I18, ASSET_BRK, tail='断点右侧那条线与左侧不可比，其余各家不受影响。'
                                          '重定基图上并购是<b>永久抬升</b>的 —— '
                                          '断点右侧的全部水平差里有一块不是自己长出来的。')
             + f'各条线右端的粗体数字是当期指数值（{mlab(B18)} = 100）。' + GATE),
})

# ── Exhibit N_REB23：客户资产重定基（四家同基期，基期 = Robinhood 的首月）──
B23 = rebase_base(('schw', 'lpla', 'ibkr', 'hood'))
I23 = pd.period_range(B23, LATEST, freq='M')
s3, inc3, exc3 = [], [], []
for t in ('schw', 'lpla', 'ibkr', 'hood'):
    r = rebase(f'{t}_assets', B23) if t in HAS else None
    if r is None or not np.isfinite(r.reindex(I23).values.astype(float)).any():
        exc3.append(NAME.get(t, t.upper()))
        continue
    s3.append({'name': NAME[t], 'color': COLOR[t], 'values': L(r.reindex(I23).values)})
    inc3.append(NAME[t])
ex.append({
    'n': N_REB23, 'kind': 'lines', 'fmt': 'f0', 'xlabels': xls(I23),
    'end_label': True, 'height': REB_H,
    'title': f'Client assets since {mlab(B23)}, rebased to 100 —— 四家同基期',
    'ylab': f'index, {mlab(B23)} = 100',
    'series': s3,
    **brks(I23, ASSET_BRK),
    'note': (firms_note(inc3, exc3)
             + f'基期取 {mlab(B23)}（Robinhood 月度经营指标的首月，四家里最晚的一个），'
             '四家从同一天起跑，斜率之差才是真的增长之差。'
             '<b>基期本轮从 Apr-23 前移到这里</b>：series/hood.csv 已由 '
             '<code>build/basefill/hood_2021.py</code> 从 Q1\'23 Earnings Supplement 回补到 '
             f'{mlab(B23)}，而旧基期 Apr-23 仍是按「Robinhood 首月」这条理由选的 —— '
             '理由没变，选出来的月份跟着数据往前走了。基期一动整条线的含义就变，'
             '所以标题、纵轴标签、页尾口径说明与本段引用的月份全部由同一个变量生成，'
             '不存在改一半的可能。'
             '<b>再往前没有了</b>：Robinhood 是 2022-04 的 8-K（0001783879-22-000088，'
             'Item 7.01 Reg FD）才宣布开始按月披露、首期回溯 12 个月，2021-01 / 2021-02 '
             '两个月是后来的 Earnings Supplement 补的；更早只存在于 S-1 与 10-Q，'
             '且不是月度粒度（举证见 build/basefill/hood_2021.py 的文件头）。'
             '口径：Schwab / LPL 为 total client assets，'
             'IBKR 为 client equity，Robinhood 为 total platform assets —— '
             '都是「客户放在这家平台上的资产总额」，可直接并排。'
             + brk_note(I23, ASSET_BRK, tail='断点右侧那条线与另外三家的斜率差里有一块是买来的，'
                                          '不是长出来的。')
             + f'右端粗体数字为当期指数值。有机口径见 Exhibit {N_ORG}。' + GATE),
})

# ── Exhibit N_YOY：客户资产 y/y（存量 → 点对点口径）──
_IT4 = [(t, f'{t}_yoy', NAME.get(t, t.upper())) for t in ('schw', 'lpla', 'ibkr', 'hood')]
_i4, _k4, _d4 = plan(_IT4)
s4, inc4, exc4, late4 = sr(_IT4, _i4, _d4)
_ST4 = stock_caliber_note(
    [(NAME[t], f'{t}_assets') for t in ('schw', 'lpla', 'ibkr', 'hood') if t in HAS], _i4)
ex.append({
    'n': N_YOY, 'kind': _k4, 'fmt': 'pct0', 'xlabels': xls(_i4),
    # 标题里写明「单月同比」：本站别的页上同名的 y/y 已经有画滚动口径的了
    # （schw Exhibit 2、hood Exhibit 3 …），不写口径读者会拿两页的数互相核而对不上。
    'title': 'Client asset growth, y/y（单月同比 / single-month）',
    'ylab': '% y/y（单月）', 'zero_line': True,
    # 四条线的末端各要标一个数，其中有两对本来就只差 1pp 上下。引擎的竖向避让有 9.6px
    # 的最小行距，画布越矮就越多标签被推到「刚好不叠字」的距离上，读者只能靠颜色反推
    # 是哪家。加高画布是唯一在 payload 侧能给的解药：同样的 1pp 在更高的画布上本来
    # 就占更多像素，避让根本不必启动。
    'height': LINE_H,
    **({'end_label': True} if _k4 == 'lines' else {}),
    'series': s4,
    **brks(_i4, ASSET_BRK),
    'note': (firms_note(inc4, exc4)
             + brk_note(_i4, ASSET_BRK,
                        tail='并进来的资产不是有机增长，跳升起的 12 个月里那条线的 y/y '
                             '与同图其余各家不可比。')
             + LP_RANK_TXT + f'有机口径见 Exhibit {N_ORG}。' + _ST4
             + win_note(_i4, _k4, late4, len(s4))
             + '同比要满 12 个月才有分母，所以每条线都比它自己的资产序列晚 12 个月起画 —— '
               '这是定义性的前置期，不是缺数据。' + GATE),
})

# ── Exhibit N_ORG：年化有机增速（Schwab vs LPL）──
# 原来这张图把 Robinhood 也放进来，纵轴被它的 20–49% 定死，Schwab（0.3–8%）与 LPL
# 近一年的读数全压在最底下那条带里，headline 写的「Schwab 4.8% / LPL 4.3%」在图上根本
# 读不出来。同一单位但差一个量级的序列不该共用一根轴，所以拆成两张（Robinhood 见下一张）。
# 拆完之后 LPL 那几个月的尖峰还是会把轴撑得很高，这一段用截轴处理 ——
# **截轴不删点**：超界的点画成空心红圈、真值竖排标在图上。上界、下界、越界的是哪几个月、
# 有几个，四样全部现算 —— 窗口从 25 个月放到序列起点这一轮里，四样全变了，
# 任何一个写死的数字或月份清单都会在下一次改窗口时当场变成假话。
_IT5 = [('schw', 'schw_org', 'Schwab core NNA'),
        ('lpla', 'lpla_org', 'LPL organic NNA')]
_i5, _k5, _d5 = plan(_IT5)
s5, inc5, exc5, late5 = sr(_IT5, _i5, _d5)

# 下界要现算。原来这里写死 `yfloor: 0.0` —— 那在 25 个月窗口里恰好没有负值月，
# 窗口一放到序列起点，LPL 有 5 个负值月（最低 −2.1%）、Schwab 最低 −1.4%，
# 写死的 0 会把它们**静默钳到零线上**画成红圈，而图注只列了「超上界」的那些月，
# 于是图上冒出一批没有任何文字解释的红圈。取「实测最小值往下取整」，一个点都不钳。
_min5 = min([v for nm in s5 for v in nm['values'] if v is not None] or [0.0])
EX5_FLOOR = float(math.floor(min(0.0, _min5)))

# ── 上界同样要现算，而且判据是**几何**，两条都得过 ────────────────────────────
# 上界原先写死 12.0。25 个月窗口下越界的只有 4 个月、彼此隔得远，看不出问题；
# 窗口放到序列起点后越界变 11 个月，其中 Dec-21 是两条线在**同一列**同时越界、
# Nov-24…Feb-25 是**连着四个月**，它们的竖排真值标注互相压字（visual_qa 实测
# 33.8px² 一处 + 16.7px² 三处，全站 QA 里本页原本那 🟡 四条就是这个）。
#
# 判据一（标注排得开）。压字是必然而不是巧合，两个宽度逐项都能算：
#   · 一格列宽 band = (W − M.l − M.r) / n。1280 视口下通栏卡片 W = 1172
#     （charts.js 的 W_WIDE，也正是 visual_qa 报的 canvas.w），该宽度对应 FS = 1.70
#     （charts.js 的 FS_MAX），本图给了 ylab ⇒ M.l = fscale(56)、M.r = fscale(14)。
#   · 竖排标注的**横向**墨迹宽 = 字号 7.2 × FS × getBBox 高/em(1.143)
#     × visual_qa 的墨迹系数 (1 − ink_top − ink_bot)。
#   本轮这两个数算出来是 8.97px vs 8.49px（下面 _CAP_INK / _BAND5 现算，别抄成常数）
#   —— 墨迹比列宽还宽，**相邻两列的标注必然叠**；同一列上的两个更糟：charts.js 的
#   capSlot 只按写死的 8px 排位（不随 FS 长），排完还差 0.97px。所以最小间隔
#   _MIN_SEP = ceil(墨迹宽 / 列宽) 列，本轮 = 2 列（16.98px）才干净。
#   768 视口那头反而没事：W=736 ⇒ FS≈1.52 ⇒ 墨迹 8.0px，恰好等于 capSlot 的 8px，
#   实测 0 条 —— 那是运气不是设计，所以判据只按最宽的那张卡片算，宽的过了窄的必过。
# 判据二（刻度印得准）。上界一改，charts.js 的 ticks() 就可能挑到 **2.5** 那一档步长，
#   而本图的轴格式器是 pct0（整数百分点）：2.5 / 7.5 / 12.5 / 17.5 会被印成
#   3 / 8 / 13 / 18 —— 网格线等距而标签不等差，按标签量线系统性偏半档
#   （visual_qa 的 AXIS_UNEVEN，🔴；只过判据一、上界停在 18% 时实测就是这个）。
#   所以要求步长是整数。步长算法不在本文件里另写一份，直接调 build/axisfmt.py 的
#   ticks()（引擎 ticks() 的逐行等价实现，全站共用）。
# charts.js 是 34 页共用的、这一轮不许动，payload 侧唯一的杠杆就是上界本身：
# **从原来的 12% 起按整数百分点逐档往上抬，抬到两条判据同时过为止**
# （轴本来就按整数百分点印，所以候选也只取整数）。抬到实测最大值都过不了就不截轴 ——
# 宁可让轴被尖峰撑高，也不要一排读不出来的糊字或一列错半档的刻度。
_QA_W, _QA_FS = 1172.0, 1.70          # charts.js: W_WIDE 与它对应的 FS_MAX
_QA_INK = 1.0 - 0.169 - 0.19          # tools/visual_qa.py: ink_top / ink_bot
_CAP_INK = 7.2 * _QA_FS * 1.143 * _QA_INK
_BAND5 = (_QA_W - round(56 * _QA_FS, 2) - round(14 * _QA_FS, 2)) / len(_i5)
_MIN_SEP = max(1, math.ceil(_CAP_INK / _BAND5))


def _cap_ok(c):
    """上界取 c 时，判据一与判据二过不过（两条都在上面的注释里推过）。"""
    ks = sorted(k for nm in s5
                for k, v in enumerate(nm['values']) if v is not None and v > c)
    if any(b - a < _MIN_SEP for a, b in zip(ks, ks[1:])):
        return False                  # 判据一：两个越界月挨得太近，标注要叠
    tk = axisfmt.ticks(EX5_FLOOR, c, 9)
    step = tk[1] - tk[0] if len(tk) > 1 else 1.0
    return abs(step - round(step)) < 1e-9      # 判据二：步长必须是整数百分点


EX5_CAP_BASE = 12.0                   # 起点 = 原来写死的那个上界；够用就一档都不抬
_max5 = max([v for nm in s5 for v in nm['values'] if v is not None] or [0.0])
EX5_CAP = next((float(c) for c in range(int(EX5_CAP_BASE), math.ceil(_max5) + 1)
                if _cap_ok(c)), None)
_over5 = [] if EX5_CAP is None else [
    (nm['name'], _i5[k], v) for nm in s5
    for k, v in enumerate(nm['values']) if v is not None and v > EX5_CAP]
ex.append({
    'n': N_ORG, 'kind': _k5, 'fmt': 'pct1', 'yfmt': 'pct0',
    # label_fmt 要显式给：截轴真值标注的格式器优先取 yfmt（pct0），会把 24.5% 印成
    # 25%，与本图注里逐个列出的真值差一位小数 —— 同一张图上两个数对不上。
    'label_fmt': 'pct1',
    'xlabels': xls(_i5),
    'title': 'Annualised organic growth: Schwab vs. LPL',
    'ylab': '% annualised', 'zero_line': True, 'height': LINE_H,
    **({'end_label': True} if _k5 == 'lines' else {}),
    'series': s5,
    # yfloor 必须与 ycap 一起给：默认下界是 mn − 0.20×极差，极差是按**未截轴的**
    # 数据算的，只给 ycap 会在零线下面留一大片空白。
    **({'ycap': EX5_CAP, 'yfloor': EX5_FLOOR,
        'cap_note': f'axis capped at {EX5_CAP:.0f}% — true values shown in red'}
       if _over5 else {}),
    **brks(_i5, SCHW_NNA_BRK + LPL_NNA_CAL_BRK),
    'note': (firms_note(inc5, exc5,
                        'IBKR 不披露净新增资产，只披露净新增账户，所以它的增速看 '
                        f'Exhibit {N_ACCT}；Robinhood 的量级差一档（当前 '
                        f'{_v0("hood_org", 1)}% vs Schwab {_v0("schw_org", 1)}% / '
                        f'LPL {_v0("lpla_org", 1)}%），与这两家同轴会把它们压成一条带，'
                        f'单独画在 Exhibit {N_ORG_HOOD}。' if N_ORG_HOOD else
                        'IBKR 不披露净新增资产，只披露净新增账户，所以它的增速看 '
                        f'Exhibit {N_ACCT}。')
             + '两家都是<b>当月净流入 x 12 ÷ 上月末客户资产</b>（GS LPLA 版式的流量口径规矩：'
             '流量类不算环比百分比，分母是上个月的流量、一个月的噪音会被放大成趋势）。'
             'LPL 已按官方同页披露的 Acquired NNA 剔除并购转入。'
             '<b>本图不画 LPL 的并表断点</b>：这条线是剔并购之后的有机口径，本来就没有台阶，'
             f'画一条「这里不可比」的红线反而是假话（as-reported 的那几张见 Exhibit '
             f'{N_YOY}）；画的是 LPL 自己改了 NNA 定义的那一条。'
             + (f'纵轴截在 {EX5_FLOOR:.0f}% 到 {EX5_CAP:.0f}%。'
                f'<b>上界现算，不是拍的</b>，要同时过两条几何判据：'
                f'①截轴真值是<b>竖排</b>标注，它的横向墨迹宽（{_CAP_INK:.1f}px）比这张图'
                f'一格列宽（{_BAND5:.1f}px）还宽，两个越界月只要落在同一列'
                f'（两条线同月越界）或相邻列，两条标注就互相压住、谁也读不出来 —— '
                f'所以越界的月彼此至少要隔 {_MIN_SEP} 列；'
                f'②轴刻度按整数百分点印，步长一旦挑到 2.5 那一档，2.5 / 7.5 / 12.5 就会'
                f'被印成 3 / 8 / 13，网格线等距而标签不等差，按标签量线会系统性偏半档 —— '
                f'所以步长必须是整数。上界从 {EX5_CAP_BASE:.0f}% 起按整数百分点逐档往上抬，'
                f'抬到两条判据同时过为止'
                + (f'（这一轮抬了 {EX5_CAP - EX5_CAP_BASE:.0f}pp，'
                   f'代价是主体那条带被压窄了约 '
                   f'{(EX5_CAP - EX5_CAP_BASE) / (EX5_CAP - EX5_FLOOR):.0%}，'
                   '换的是这几个尖峰的真值能读）'
                   if EX5_CAP > EX5_CAP_BASE else '（这一轮没用抬）')
                + f'。{len(_over5)} 个月越上界：'
                + '；'.join(
                    nm + ' ' + '、'.join(f'{mlab(p)} {v:.1f}%'
                                         for n2, p, v in _over5 if n2 == nm)
                    for nm in dict.fromkeys(n2 for n2, _p, _v in _over5))
                + '。这些月的 Acquired NNA 官方同页并未列出（列出的都已按 '
                '<code>ACQ</code> 表逐月扣掉了），所以它们留在有机口径里 —— '
                '<b>本图注不替公司解释这几个尖峰的成因</b>，公司没说，我们也不猜。'
                '不截轴的话其余月份会被压成贴零的一条平线。'
                '<b>截轴不删点</b> —— 超界的点画成空心红圈、真值竖排标在图上，'
                f'表格视图里也是真值；下界 {EX5_FLOOR:.0f}% 取自实测最小值往下取整，'
                '零线以下的月份一个都没有被钳。' if _over5 else '')
             + brk_note(_i5, SCHW_NNA_BRK + LPL_NNA_CAL_BRK,
                        tail='两家的剔除规则本来就各自不同，断点各标各的那条线'
                             '自己前后不可比的那个位置，不是说同图另一家也变了。')
             + org_caliber_note([('Schwab', 'schw'), ('LPL', 'lpla')], _i5)
             + win_note(_i5, _k5, late5, len(s5))
             + '年化有机增速要用<b>上月末</b>资产做分母，所以每条线比它自己的资产序列'
               '晚一个月起画 —— 序列首月没有上月，那一格在定义上就不存在，不补。' + GATE),
})

# ── Exhibit N_ORG_HOOD：年化有机增速（Robinhood，另一个量级）──
if N_ORG_HOOD:
    _IT6H = [('hood', 'hood_org', 'Robinhood net deposits')]
    _i6h, _k6h, _d6h = plan(_IT6H)
    s6h, inc6h, exc6h, late6h = sr(_IT6H, _i6h, _d6h)
    ex.append({
        'n': N_ORG_HOOD, 'kind': _k6h, 'fmt': 'pct1', 'yfmt': 'pct0',
        'xlabels': xls(_i6h),
        'title': 'Annualised organic growth: Robinhood',
        'ylab': '% annualised', 'zero_line': True, 'height': LINE_H,
        **({'end_label': True} if _k6h == 'lines' else {}),
        'series': s6h,
        **brks(_i6h, HOOD_ND_BRK),
        'note': ('口径与 Exhibit ' + str(N_ORG) + ' 完全相同（当月净流入 x 12 ÷ 上月末客户资产），'
                 '<b>只是纵轴不同</b>：Robinhood 这条线在 '
                 f'{min(v for v in s6h[0]["values"] if v is not None):.0f}–'
                 f'{max(v for v in s6h[0]["values"] if v is not None):.0f}% 之间，'
                 f'与 Schwab / LPL 的 {_v0("schw_org", 1)}% / {_v0("lpla_org", 1)}% 差一个量级，'
                 '同轴画会把那两条压成一条贴零的带（这正是拆图的原因）。'
                 '两张图的百分比可以直接比大小，但<b>不要把两张图的线形叠着看</b>。'
                 'net deposits 是客户净转入（含现金与证券转入），与 Schwab 的 core NNA、'
                 'LPL 的 organic NNA 是同一个经济含义，但三家的剔除规则各自不同。'
                 + brk_note(_i6h, HOOD_ND_BRK,
                            tail='并入的流量不是有机获客，断点右侧与左侧不可直读。')
                 + org_caliber_note([('Robinhood', 'hood')], _i6h)
                 + win_note(_i6h, _k6h, late6h, len(s6h))
                 + f'左端 {mlab(_i6h[0])} 是 Robinhood 月度披露首月 '
                   f'{mlab(_first("hood_assets"))} 的下一个月（年化增速要用上月末资产做分母），'
                   '再往前公司没有按月披露过 —— 举证见 Exhibit '
                 + str(N_REB23) + ' 的图注。' + GATE),
    })

# ── Exhibit N_ACCT：账户数增速（只有 IBKR 与 HOOD 披露存量账户数）──
_IT6 = [('ibkr', 'ibkr_acct_yoy', 'IBKR accounts'),
        ('hood', 'hood_acct_yoy', 'Robinhood funded customers')]
_i6, _k6, _d6 = plan(_IT6)
s6, inc6, exc6, late6 = sr(_IT6, _i6, _d6)
# 图注里「点对点 vs 12 个月均值同比」那一段的两个标准差与倍数**每次构建现算**
# （stock_caliber_note → stock_pair），不是写死的结论。
# 这一点在这张图上尤其要紧：25 个月窗口时它是全页最强的一条反例（IBKR 1.7pp vs
# 3.0pp，均值口径反而更吵），窗口放宽到 113 个月之后同一条线翻成 13.9pp vs 12.5pp
# ——「谁更吵」是窗口的函数，不是这条序列的性质。谁再想把某个倍数抄进注释里，
# 先看 caliber_evidence() 的 docstring。
_ST7 = stock_caliber_note([(NAME[t], f'{t}_accounts')
                           for t in ('ibkr', 'hood') if t in HAS], _i6)
ex.append({
    'n': N_ACCT, 'kind': _k6, 'fmt': 'pct1', 'yfmt': 'pct0',
    'xlabels': xls(_i6),
    'title': 'Account growth, y/y: IBKR vs. Robinhood（单月同比 / single-month）',
    'ylab': '% y/y（单月）', 'height': LINE_H,
    **({'end_label': True} if _k6 == 'lines' else {}),
    'series': s6,
    **brks(_i6, HOOD_CUST_BRK),
    'note': (firms_note(inc6, exc6,
                        'Schwab 只披露当月<b>新开</b>经纪账户（流量），不披露账户存量；'
                        'LPL 披露的是投顾人数（advisor count）而不是账户数 —— '
                        '两者都不能与「账户存量的 y/y」并排，所以不入图。')
             + 'IBKR 的口径是 total accounts，Robinhood 是 funded customers（有入金的客户数），'
             '一个数账户、一个数人，绝对水平不可比，但增速的方向与幅度可比。'
             + brk_note(_i6, HOOD_CUST_BRK,
                        tail='并进来的客户不是自然获客，断点之后的 12 个月里 Robinhood 的 y/y '
                             '含这块一次性增量，与 IBKR 不 like-for-like。')
             + _ST7 + win_note(_i6, _k6, late6, len(s6))
             + '两条线各比自己的存量序列晚 12 个月起画：同比要满 12 个月才有分母。' + GATE),
})

# ── Exhibit N_MGN：融资余额 ──
_IT7 = [('schw', 'schw_margin', 'Schwab month-end margin'),
        ('ibkr', 'ibkr_margin', 'IBKR margin loans'),
        ('hood', 'hood_margin', 'Robinhood margin book')]
_i7, _k7, _d7 = plan(_IT7)
s7, inc7, exc7, late7 = sr(_IT7, _i7, _d7)
_schw_mgn0 = df['schw_margin'].dropna()
ex.append({
    'n': N_MGN, 'kind': _k7, 'fmt': 'usd0', 'xlabels': xls(_i7),
    'title': 'Margin balances: Schwab vs. IBKR vs. Robinhood', 'ylab': '$bn',
    'height': LINE_H,
    # 长历史的 lines 图一律零基线（CONTRACT §3 的表格：不给 zero_base 等于隐性截轴）。
    # 本页这一组（N_MGN / N_CASH / N_DATS / N_MGNPCT / N_CASHPCT）都是非负的水平值或
    # 占比，从 17 期的 lines_endlabels 换成长历史 lines 那一刻就归这条规矩管；
    # 同族的 lpla Ex8/Ex17、ibkr Ex15/Ex16 也都是这么给的。
    # y/y 那几张（N_YOY / N_ORG / N_ACCT）不给：它们会转负，零基线在那里是错的判法。
    **({'end_label': True, 'zero_base': True} if _k7 == 'lines' else {}),
    'series': s7,
    'note': (firms_note(inc7, exc7, 'LPL 不披露融资余额。')
             + '三家都是客户融资余额（月末口径），但 Schwab 的数含 short credits、'
             '另两家不含。'
             + (f'<b>Schwab 那条只有 {mlab(_schw_mgn0.index[0])} 起</b>：'
                '公司自 2026-01 的月报才开始披露月末融资余额，那一期的 13 个月滚动表回溯到 '
                f'{mlab(_schw_mgn0.index[0])} 为止，更早的月份公司就没有印过'
                '（见 <code>fetch/schw.py</code> 的 <code>_DATS_MARGIN_FROM</code>）。'
                '<b>本图不因此把另外两条一起砍掉</b> —— 从前的判法是「取各线都有值的连续末段」，'
                '那会让 IBKR 这条 2016-01 起的线只剩十几个月，'
                '等于把一家的披露缺口转嫁成另一家的历史损失。' if len(_schw_mgn0) else '')
             + win_note(_i7, _k7, late7, len(s7)) + GATE),
})

# ── Exhibit N_CASH：客户现金（HOOD 口径不可比，故只三家）──
# 这两张图（N_CASH / N_CASHPCT）以前把 Schwab 排除在外，理由写的是「Schwab 月报根本
# 不单列客户现金」—— **那句话是错的**，2026-08-19 回原件核掉：月报 Selected Balances
# 块里逐月印着 Transactional Sweep Cash 与 Total Money Market Funds 两条月末 $bn，
# Client Activity 块下面还有一行 Client Cash as a Percentage of Client Assets
# （自 2014-06 起每期都印）。抓不到只是因为 fetch/schw.py 的 COLS 里没写这三行，
# 不是公司没披露。三列已补进 series/schw.csv（`python3 fetch/schw.py --columns`）。
# 纵轴被 Schwab 撑开多少倍 —— 现算。写「十几倍到二十几倍」这种话当场就错了一半
# （对 LPL 是二十倍，对 IBKR 只有六倍多），而且下个月还会变。
def _cash_axis_txt():
    if 'schw_cash' not in df.columns or not np.isfinite(df['schw_cash'].loc[LATEST]):
        return ''
    big = float(df['schw_cash'].loc[LATEST])
    oth = [(NAME[_t], float(df[_c].loc[LATEST])) for _t, _c in
           (('lpla', 'lpla_cash'), ('ibkr', 'ibkr_cash'))
           if _c in df.columns and np.isfinite(df[_c].loc[LATEST])]
    if not oth:
        return ''
    rs = sorted(big / v for _n, v in oth)
    return (f'<b>纵轴由 Schwab 定</b>：{mlab(LATEST)} 它的客户现金是另两家的 '
            + '、'.join(f'{big / v:.0f} 倍（{n}）' for n, v in
                        sorted(oth, key=lambda x: -x[1]))
            + '，所以那两条在这张图上必然贴着底部走。这张图回答的是「谁大」；'
            f'「同样一块客户资产上谁留了更多现金」要看 Exhibit {N_CASHPCT} —— '
            '归一化之后三家才在同一根轴上真的可比。本站没有对数轴，'
            '也不为了让小的那条好看去压缩坐标（页尾「纵轴」一节）。')


_CASH_AXIS_TXT = _cash_axis_txt()

_SCHW_CASH_WHY = (
    f'<b>Schwab 那条只有 {mlab(_first("schw_cash"))} 起</b>：两条分量'
    '（月末 sweep cash、月末货基）是 2026-01 那期月报新增的，那一期的 13 个月滚动表'
    f'只回溯到 {mlab(_first("schw_cash"))}，更早的月份公司没有印过月末的<b>金额</b>'
    f'（同 Exhibit {N_MGN} 的月末融资余额，是同一次改版新增的同一批列，'
    '见 <code>fetch/schw.py</code> 的 <code>_DATS_MARGIN_FROM</code>）。'
    f'<b>本图不因此把另外两条一起砍掉</b>，也<b>不</b>拿 Exhibit {N_CASHPCT} 那条'
    f'自 {mlab(_first("schw_cash_pct"))} 起的官方占比乘客户资产去倒推更早的金额 —— '
    '那是把一个印到 0.1pp 的比率反解成 $bn，等于凭空造出十年的精度。'
    '金额与占比是两条各自起止的线，本页不把它们接成一条。'
    if _first('schw_cash') is not None and _first('schw_cash_pct') is not None else '')

_IT8 = [('schw', 'schw_cash', 'Schwab client cash'),
        ('lpla', 'lpla_cash', 'LPL client cash'),
        ('ibkr', 'ibkr_cash', 'IBKR client credits')]
_i8, _k8, _d8 = plan(_IT8)
s8, inc8, exc8, late8 = sr(_IT8, _i8, _d8)
_BRK8 = LPL_ACQ_BRK + LPL_CASH_CAL_BRK
ex.append({
    'n': N_CASH, 'kind': _k8, 'fmt': 'usd0', 'xlabels': xls(_i8),
    'title': 'Client cash: Schwab vs. LPL vs. IBKR', 'ylab': '$bn', 'height': LINE_H,
    **({'end_label': True, 'zero_base': True} if _k8 == 'lines' else {}),
    'series': s8,
    # LPL 的 client cash 同样是并表转入的（2024-10 45.8→48.3、2025-08 49.5→52.7）——
    # 画 as-reported LPL 的图都要带断点线；窗口放宽之后还多了 2019-04 那条**口径**断点
    # （官方把 Total Cash Sweep Balances 改成 Total Client Cash Balances 并计入货基）。
    **brks(_i8, _BRK8),
    'note': (firms_note(inc8, exc8)
             + '<b>为什么少一家：</b>Robinhood 把客户现金拆成 cash sweep（扫到合作银行、'
             '表外）与 cash and deposits（留在券商）两条线，不发布同一口径的合计 —— '
             '取任一条与另外三家并排，不是漏计就是重复计，所以它不入图。'
             '<b>三家的「客户现金」各是什么：</b>Schwab 是月报 Selected Balances 块里的 '
             'Transactional Sweep Cash 与 Total Money Market Funds 两条月末余额之和'
             '（官方脚注：sweep 含银行扫款存款、券商现金余额、表内其它客户现金与'
             '第三方银行存款账户，不含自有与第三方 CD）；LPL 是 client cash'
             '（ICA + 货基 + DCA 合计）；IBKR 是 client credits（客户贷方余额，<b>不含货基</b>）。'
             '前两家的口径含货基、IBKR 不含，所以 IBKR 那条的水平值系统性偏低，'
             '要读的是各自的方向与拐点。这三条线都是净利息收入的核心驱动。'
             + _CASH_AXIS_TXT
             + _SCHW_CASH_WHY
             + brk_note(_i8, _BRK8,
                        tail='并表把被并方的客户现金一次性转入，那一跳不是客户在加现金 —— '
                             + jump_txt(_i8, LPL_ACQ_BRK, 'lpla_cash',
                                        lead='LPL client cash 在并表当月的环比为 '))
             + win_note(_i8, _k8, late8, len(s8)) + GATE),
})

# ── Exhibit N_DATS：日均交易笔数 ──
_IT9 = [('schw', 'schw_dats', 'Schwab DATs'),
        ('ibkr', 'ibkr_dats', 'IBKR total client DARTs'),
        ('hood', 'hood_dats', 'Robinhood DATs')]
_i9, _k9, _d9 = plan(_IT9)
s9, inc9, exc9, late9 = sr(_IT9, _i9, _d9)
# Robinhood 那条线自己就跨着一条口径缝：DARTS_UNTIL 及更早填的是官方当期印的 DARTs
# （Daily Average **Revenue** Trades），之后才是 DATs。build/hood.py 明写这件事
# 「必须写在图注里」。旧窗口（Jan-25 起 17 个月）整段都在 DATs 侧，所以以前不漏；
# 窗口一放宽就把那一段拖了进来。落在**本图窗口内**的月数现算 —— 窗口再变它自己跟着变。
_hd_seg = [p_ for p_ in _i9
           if HOOD_DARTS_UNTIL is not None and p_ <= HOOD_DARTS_UNTIL
           and 'hood_dats' in df.columns and np.isfinite(df['hood_dats'].loc[p_])]
_HOOD_DATS_CAL = (
    f'<b>口径提示（Robinhood 那条线内部）：</b>{mlab(HOOD_DARTS_UNTIL)} 及更早'
    f'（本图窗口内共 {len(_hd_seg)} 个月，{mlab(_hd_seg[0])}–{mlab(_hd_seg[-1])}）'
    '填的是官方当期印的 <b>DARTs</b>（Daily Average <i>Revenue</i> Trades，'
    '不含不产生收入的交易），之后才是 DATs。公司 2026-07 的 Q2\'26 Earnings Supplement '
    '才把这一节改名并重述历史，而重述只回溯到 Jan-25（equity 由 2.6 改成 3.3）—— '
    'Dec-24 及更早两种口径逐月逐位相同，所以两段接得上，但左段严格说是窄口径。'
    '同一提示挂在 Robinhood 单页 Exhibit 11 与该页页尾；本页的月份直接从 '
    '<code>build/hood.py</code> 的 <code>DARTS_UNTIL</code> 读，两页不会各写各的。'
    if _hd_seg else '')
ex.append({
    'n': N_DATS, 'kind': _k9, 'fmt': 'f0c', 'xlabels': xls(_i9),
    'title': 'Daily average trades: Schwab vs. IBKR vs. Robinhood',
    'ylab': 'k trades / day', 'height': LINE_H,
    **({'end_label': True, 'zero_base': True} if _k9 == 'lines' else {}),
    'series': s9,
    'note': (firms_note(inc9, exc9, 'LPL 不披露交易笔数。')
             + '<b>三家的「一笔」不是同一件事：</b>Schwab DATs 数客户成交笔数；'
             'IBKR 这条线用的是公司披露的 <b>Total Client DARTs</b>，'
             '含通过 IBKR 执行但不在 IBKR 清算的 introducing-broker 客户；'
             'Robinhood 是股票 + 期权 + 加密三个市场的 DATs 之和（官方单位 mn，此处 x1,000 换成 k）。'
             '所以水平值只能当量级读，方向与拐点才是可比的信息。'
             '<b>这里取总量是为了与另两家的客户总成交笔数可比</b> —— IBKR 另按 '
             'Cleared Avg. DART per Account 推导过一条更窄的 implied cleared DARTs'
             f'（见 IBKR 单页 Exhibit 4/18），{CLEARED_TXT}，两条线不要混读；'
             '「cleared」修饰的是账户（IBKR 自清算的账户），不是订单。'
             + _HOOD_DATS_CAL
             + (f'<b>Schwab 那条只有 {mlab(df["schw_dats"].dropna().index[0])} 起</b>：'
                'DATs 与月末融资余额是同一批新增列，自 2026-01 的月报才开始披露、'
                '那一期的 13 个月滚动表只回溯到这里，更早的月份公司没有印过。'
                '同 Exhibit ' + str(N_MGN) + '，不为它砍掉 IBKR 那条 2016-01 起的线。'
                if has('schw_dats') else '')
             # 首页把「IBKR 2025-01 DARTs 口径变更」列为断点示例，本图却不画 —— 不解释
             # 就是又一处「两页说法不一致」。理由要写在图上，不是留给读者猜。
             # ⚠ 原来这里还有第二条理由「本图窗口正好从 Jan-25 起、断点落在第一期」，
             #   窗口放宽之后那句话当场变成假话（现在左边有九年可比的部分），已删。
             #   剩下的第一条理由本身就足够，而且它与窗口无关。
             + '<b>关于 IBKR 单页那条 2025-01 断点：</b>它标在 IBKR 单页 Exhibit 18 上，'
             '指的是 cleared / non-cleared 这个<b>拆分比例</b>在 2025 年跳了一档'
             '（该页原文：疑似口径 / 分类变更，未经公司确认），而本图画的是'
             '<b>披露总量</b>那条线 —— 总量本身没有换口径，所以本图不画这条线，改在这里写明。'
             + win_note(_i9, _k9, late9, len(s9)) + GATE),
})

# ── Exhibit N_REB19：资产负债表项目重定基（基期同样现算，原先写死 2019-01）──
BS10 = [('ibkr', 'ibkr_margin', 'IBKR margin', 'MBLUE'),
        ('ibkr', 'ibkr_cash', 'IBKR credits', 'BLUE'),
        ('lpla', 'lpla_cash', 'LPL client cash', 'RED')]
_bs_first = [_first(c) for _t, c, _l, _col in BS10
             if _t in HAS and c in df.columns and _first(c) is not None]
B19 = max(_bs_first) if _bs_first else IDX[0]
I19 = pd.period_range(B19, LATEST, freq='M')
s10, inc10, exc10 = [], [], []
for t, cname, legend, c in BS10:
    r = rebase(cname, B19) if t in HAS else None
    if r is None or not np.isfinite(r.reindex(I19).values.astype(float)).any():
        exc10.append(legend)
        continue
    s10.append({'name': legend, 'color': c, 'values': L(r.reindex(I19).values)})
    inc10.append(legend)
_LPL_IN_10 = any(s['name'] == 'LPL client cash' for s in s10)
_BRK10 = LPL_ACQ_BRK + LPL_CASH_CAL_BRK
ex.append({
    'n': N_REB19, 'kind': 'lines', 'fmt': 'f0', 'xlabels': xls(I19),
    'end_label': True, 'height': REB_H,
    'title': f'Balance-sheet items since {mlab(B19)}, rebased to 100',
    'ylab': f'index, {mlab(B19)} = 100',
    'series': s10,
    # 这张图里有一条 as-reported 的 LPL client cash，重定基图上并购是永久抬升的
    # （本页 Exhibit 2 的图注自己就是这么论证的），断点必须画。
    **(brks(I19, _BRK10) if _LPL_IN_10 else {}),
    'note': (firms_note(inc10, exc10)
             + '融资余额是周期项、客户现金是利率敏感项，重定基之后能看出两者的相位差。'
             + f'<b>基期 {mlab(B19)} 现算</b>：三条线里最晚开始的那条的首月（'
             + '、'.join(f'{l} 自 {mlab(_first(c))} 起' for _t, c, l, _col in BS10
                         if _t in HAS and _first(c) is not None)
             + '）。此前写死 2019-01，同样是照搬原 deck 的 "since 2019" 版式，'
               '与本仓的序列长度无关。'
             + (f'Schwab 的月末融资余额与月末客户现金都只有 '
                f'{mlab(_schw_mgn0.index[0])} 起的历史（同一批新增列）、'
                if len(_schw_mgn0) else 'Schwab 的月末余额类历史很短、')
             + (f'Robinhood 只有 {mlab(_HOOD_F)} 起的历史，' if _HOOD_F else 'Robinhood 也是，')
             + f'都盖不到 {mlab(B19)} 的基期，硬画等于拿一个空值当分母，所以不入这张长历史图；'
             f'它们的近期水平见 Exhibit {N_MGN} 与 {N_CASH}'
             '（那两张图不重定基，短的线前段留 null 就行）。'
             + (brk_note(I19, _BRK10,
                         tail='只影响 LPL client cash 这一条线：重定基图上并购是'
                              '<b>永久抬升</b>的，断点右侧它与另外两条的水平差里有一块'
                              '是并进来的。'
                              + jump_txt(I19, LPL_ACQ_BRK, 'lpla_cash',
                                         lead='并表当月环比 '))
                if _LPL_IN_10 else '')
             + '右端粗体数字为当期指数值。' + GATE),
})

# ── Exhibit N_MGNPCT：融资余额 / 客户资产（杠杆强度，横截面归一化）──
_IT11 = [('schw', 'schw_mgn_pct', 'Schwab'),
         ('ibkr', 'ibkr_mgn_pct', 'IBKR'),
         ('hood', 'hood_mgn_pct', 'Robinhood')]
_i11, _k11, _d11 = plan(_IT11)
s11, inc11, exc11, late11 = sr(_IT11, _i11, _d11)
ex.append({
    'n': N_MGNPCT, 'kind': _k11, 'fmt': 'pct1',
    'xlabels': xls(_i11), 'height': LINE_H,
    **({'end_label': True, 'zero_base': True} if _k11 == 'lines' else {}),
    'title': 'Margin balances as % of client assets', 'ylab': '% of client assets',
    'series': s11,
    'note': (firms_note(inc11, exc11, 'LPL 不披露融资余额。')
             + '把融资余额按各自的客户资产归一化 —— 这是横截面页真正独有的读法：'
             '绝对额只说明谁大，占比说明<b>同样一块客户资产上，谁的客户加了更多杠杆</b>。'
             f'注意分母口径三家略有差异（见 Exhibit {N_REB23} 的说明），'
             '且 Schwab 的分子含 short credits，'
             '所以水平值有系统性偏差，趋势与相对位次才是要看的。'
             '<b>比率的可得区间是分子分母的交集</b>：本图三条线各自从「该家融资余额与'
             '客户资产都已披露」的那个月起画 —— 分母（客户资产）三家都比分子长，'
             f'所以卡住起点的一律是分子（Schwab '
             f'{mlab(_schw_mgn0.index[0]) if len(_schw_mgn0) else "—"}、'
             f'Robinhood {mlab(_first("hood_margin")) if _first("hood_margin") else "—"}、'
             f'IBKR {mlab(_first("ibkr_margin")) if _first("ibkr_margin") else "—"}）。'
             + win_note(_i11, _k11, late11, len(s11)) + GATE),
})

# ── Exhibit N_CASHPCT：客户现金 / 客户资产（利率敏感度，横截面归一化）──
_IT12 = [('schw', 'schw_cash_pct', 'Schwab'),
         ('lpla', 'lpla_cash_pct', 'LPL'),
         ('ibkr', 'ibkr_cash_pct', 'IBKR')]
_i12, _k12, _d12 = plan(_IT12)
s12, inc12, exc12, late12 = sr(_IT12, _i12, _d12)
_BRK12 = LPL_ACQ_BRK + LPL_CASH_CAL_BRK
ex.append({
    'n': N_CASHPCT, 'kind': _k12, 'fmt': 'pct1',
    'xlabels': xls(_i12), 'height': LINE_H,
    **({'end_label': True, 'zero_base': True} if _k12 == 'lines' else {}),
    'title': 'Client cash as % of client assets', 'ylab': '% of client assets',
    'series': s12,
    # 这张图的断点最不能省：分子（现金）与分母（客户资产）在并表月跳的幅度不同，
    # 占比会**机械地**掉一截，看上去像「客户把现金投出去了」，其实是并购摊薄。
    # 窗口放宽之后又多了 2019-04 那条现金口径断点（分子换了定义，比率整体抬一档）。
    **brks(_i12, _BRK12),
    'note': (firms_note(inc12, exc12)
             + '现金占比是净利息收入的敏感度指标：占比下行意味着客户把现金投出去了，'
             f'同样的利率环境下 NII 的基数在缩。少的那家与 Exhibit {N_CASH} 同因 —— '
             'Robinhood 的客户现金拆成两条不可合计的线。'
             + f'<b>Schwab 那条是官方自己印的数，不是本页现除的</b>：月报里就有一行 '
               'Client Cash as a Percentage of Client Assets（官方定义：Schwab One、'
               '若干现金等价物、银行存款、第三方银行存款账户与货基余额占客户总资产的比重），'
               f'自 {mlab(_first("schw_cash_pct"))} 起每期都印，'
               f'比 Exhibit {N_CASH} 里那两条分量（{mlab(_first("schw_cash"))} 起）长十年 —— '
               '所以这张图取 as-reported，那张图取分量之和。'
               '另两家的分子分母见下：LPL 是 client cash ÷ total client assets，'
               'IBKR 是 client credits ÷ client equity。'
               '<b>三家分子的口径不同</b>：Schwab 含货基，LPL 自 2019-04 起含'
               '（那条口径断点就画在图上），IBKR 的 client credits 始终不含 —— '
               '所以 IBKR 那条系统性低一档，可比的是各自的升降与拐点，不是水平值。'
             + '<b>比率的可得区间是分子分母的交集</b>：'
             + '；'.join(f'{lg} 自 {mlab(_first(cn))} 起'
                         for _t, cn, lg in _IT12 if _t in HAS and _first(cn) is not None)
             + '。'
             + brk_note(_i12, _BRK12,
                        tail='<b>并表月的占比下滑有一部分是机械的</b>：分子（客户现金）'
                             '与分母（客户资产）跳的幅度不同，占比自己就会掉一截 —— '
                             + dilution_txt(_i12, LPL_ACQ_BRK, 'lpla_cash_pct')
                             + '把这一段整个读成「客户把现金投出去了」是错的。'
                               '2019-04 那条是<b>口径</b>断点不是并表：分子换了定义'
                               '（开始计入 purchased money market funds），比率整体抬一档，'
                               '两侧不可直读。')
             + win_note(_i12, _k12, late12, len(s12)) + GATE),
})

# ── Exhibit N_HEAT：各家客户资产 y/y 的 月 x 年 热力矩阵（编号见 N_HEAT）──
def heat(n, t, title, extra=''):
    s = df[f'{t}_yoy'].dropna()
    if not len(s):
        return None
    yrs = sorted({p.year for p in s.index})[-7:]
    matrix = []
    for y in yrs:
        row = []
        for m in range(1, 13):
            p = pd.Period(f'{y}-{m:02d}', 'M')
            row.append(round(float(s.loc[p]), 6)
                       if p in s.index and np.isfinite(s.loc[p]) else None)
        matrix.append(row)
    return {
        'n': n, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pct0',
        'title': title, 'rows': [str(y) for y in yrs], 'cols': MONTHS,
        'matrix': matrix, 'legend': title, 'row_head': '年',
        'note': ('绿 = 增长更快。色标取全部有限值的 5/95 分位，一两个离群月不会把整表压平。'
                 '格内是<b>单月同比</b>（本月末 ÷ 去年同月末 − 1）—— 热力矩阵不换成滚动口径'
                 '是刻意的：逐格的月度波动与季节形状就是这张图的题眼，平滑掉等于把它'
                 '唯一的信息抹掉。'
                 + extra + GATE),
    }


for _t, _title, _extra in [
    # 标题一律带「单月同比」：热力矩阵按定义是逐格月度读数，豁免于「默认改滚动」那条
    # 规矩（逐格波动与季节形状就是它的题眼，平滑掉等于把唯一的信息抹掉），
    # 但豁免不等于可以不写口径 —— 不写，读者会拿格子里的数去核别页的滚动线。
    ('schw', 'Schwab client assets y/y — 单月同比 (%)', ''),
    ('lpla', 'LPL client assets y/y — 单月同比 (%)', '2024-10（Atria +$88.3bn）与 '
                                          '2025-08（Commonwealth +$275.0bn）起的 12 个格子带着并购转入，'
                                          '不是有机增长；热力矩阵这个图型画不了断点竖线，'
                                          f'带断点线的同口径图见 Exhibit {N_YOY}，'
                                          f'剔并购后的有机口径见 Exhibit {N_ORG}。'),
    ('ibkr', 'IBKR client equity y/y — 单月同比 (%)', ''),
    ('hood', 'Robinhood platform assets y/y — 单月同比 (%)',
     f'Robinhood 的月度披露自 {mlab(_HOOD_F)} 起（举证见 Exhibit {N_REB23} 的图注），'
     f'y/y 要满 12 个月才有分母，所以最早一格是 '
     f'{mlab(df["hood_yoy"].dropna().index[0]) if has("hood_yoy") else "—"}，'
     '矩阵行数少于另外三家。'),
]:
    if _t not in N_HEAT:
        continue
    _h = heat(N_HEAT[_t], _t, _title, _extra)
    if _h:
        ex.append(_h)

# 编号是图注的骨架：断一个号，「见 Exhibit N」就集体指错，而这种错人眼扫不出来。
# 这一条是**结构**不变量（只随成员与序列有无变化，不随窗口滚动），所以在这里硬拦。
_NS = [1] + [e['n'] for e in ex] + [N_TABLE]
if _NS != list(range(1, len(_NS) + 1)):
    raise SystemExit(f'Exhibit 编号不连续：{_NS} —— 有图被跳过而编号没跟着回收')

# ── 排版裁决：通栏 / x 标签抽稀，一律交给 mrwin ────────────────────────────
# 窗口从 25 个月放到 125 个月之后，「半栏放不放得下」不再是显然的：125 期塞进半栏卡片
# 每期只有 4.0px，x 标签 90° 旋转后横向固定占 9.6px（引擎在桌面不缩字号）。
# 这一步**不在本文件里自己算**：量边距的算式全站只有 build/chartscale.py 一份，
# 本仓已经因为「抄了三份」吃过亏。本页此前是手写 `xstep: 2` / `len(idx)//14`，
# 那两个数在 25 期窗口下碰巧不撞，放宽之后就成了一堵字墙。
# layout_all 会把实测说明（每期几 px、为什么通栏、为什么每 N 期标一个）追加进各自图注。
mrwin.layout_all(ex)

# DENSE 图型里出现 null = 引擎画出一条塌到零的假线并抛异常，该卡片之后一张都不渲染。
# verify_pages 会抓，但那要等构建完；这里当场拦，免得把一份坏 payload 写到磁盘上。
for _e in ex:
    if _e.get('kind') in mrwin.DENSE:
        for _s in _e.get('series') or []:
            if any(v is None for v in _s['values']):
                raise SystemExit(f'Exhibit {_e["n"]}（{_e["kind"]}，属 mrwin.DENSE）的 '
                                 f'{_s["name"]} 里有 null —— plan() 应当把它判成 lines，'
                                 f'或者这条腿根本不该入图')


# 汇总表画不了断点线（表格没有 x 轴），所以 LPL 那一行的并购口径只能写进表注。
# 放在这里而不是 summary 的字面量里，是因为 drawn_for 要等 exhibit 全部建完才读得到 ——
# 图注不能声称画了一条其实没画的线。
_LPL_DRAWN = drawn_for(ex, LPL_ACQ_BRK)
if LP_RANK_TXT:
    summary['note'] += (
        'LPL 那行是 as-reported 口径，含 Atria（2024-10 +$88.3bn）与 '
        'Commonwealth（2025-08 +$275.0bn）两次整体并表，表格画不出断点线：'
        + LP_RANK_TXT
        + (f'这两次并表在 Exhibit {"、".join(str(n) for n in _LPL_DRAWN)} 上都画了'
           '红色竖虚线（客户资产与客户现金两族图都受影响）；'
           if _LPL_DRAWN else '')
        + f'剔并购后的有机口径见 Exhibit {N_ORG}。')


# ────────────────────────────── 核对表 ──────────────────────────────
T13 = df.iloc[-13:]


def tcell(v, d=1):
    return None if v is None or not np.isfinite(v) else comma(float(v), d)


TCOLS = [
    ('schw', 'SCHW client assets ($bn)', 'sa', 'schw_assets', 1),
    ('lpla', 'LPL client assets ($bn)', 'la', 'lpla_assets', 1),
    ('ibkr', 'IBKR client equity ($bn)', 'ia', 'ibkr_assets', 1),
    ('hood', 'HOOD platform assets ($bn)', 'ha', 'hood_assets', 1),
    ('schw', 'SCHW core NNA ($bn)', 'sf', 'schw_flow', 1),
    ('lpla', 'LPL NNA total, as reported ($bn)', 'lf', 'lpla_nna_raw', 1),
    ('lpla', 'LPL acquired NNA ($bn)', 'lq', 'lpla_acq', 1),
    ('hood', 'HOOD net deposits ($bn)', 'hf', 'hood_flow', 1),
    ('schw', 'SCHW DATs (k)', 'sd', 'schw_dats', 0),
    ('ibkr', 'IBKR total client DARTs (k)', 'id', 'ibkr_dats', 0),
    ('hood', 'HOOD DATs (mn)', 'hd', 'hood_dats_mn', 1),
]
TCOLS = [c for c in TCOLS if c[0] in HAS and c[3] in df.columns and has(c[3])]

table = {
    'n': N_TABLE,
    'title': f'近 13 个月跨公司核对表（各家官方原始单位，未换算，统一截至 {mlab(LATEST)}）',
    'idx': '月份',
    'cols': [[c[1], c[2]] for c in TCOLS],
    'rows': [dict({'xl': mlab(p)},
                  **{c[2]: tcell(r[c[3]], c[4]) for c in TCOLS})
             for p, r in T13.iterrows()],
}


# ────────────────────────────── 口径与方法说明 ──────────────────────────────
_v = _v0                         # 同一件事只留一份实现


def _exl(ns):
    return '、'.join(str(n) for n in ns)


# 「本页各图的左端」从建好的 payload 现读。写死「本页一律从 2016-01 起」这类**全称断言**
# 是本轮抓到的一类错：左端既然逐图现算，各图就必然不齐（本轮 Jun-14 / Sep-14 / Feb-16 /
# Jan-16 / Jan-17 / Jan-21 / Feb-21 七个），而抬头那句话一个字没跟。
_LEFT: dict = {}
for _e in ex:
    if not _e.get('xlabels'):
        continue
    _LEFT.setdefault(
        pd.Period(datetime.datetime.strptime(_e['xlabels'][0], '%b-%y'), 'M'), []
    ).append(_e['n'])
_LEFT_MIN, _LEFT_MAX = (min(_LEFT), max(_LEFT)) if _LEFT else (LATEST, LATEST)
_LEFT_TXT = '；'.join(f'{mlab(_p)} → Exhibit {_exl(sorted(_ns))}'
                      for _p, _ns in sorted(_LEFT.items()))

# 「Schwab 那条线前段是空的」出现在哪几张图上 —— 同样现读，不手写编号。
# 本轮 Exhibit N_CASH 新增了一条 2025-01 起的 Schwab 客户现金线，手写的那个三图清单
# 当场就少一张；而 Exhibit N_CASHPCT 的 Schwab 反而是全图最长的一条（Jun-14 起），
# 手写清单也分不出这个差别。
_SCHW_LATE = sorted({_e['n'] for _e in ex
                     for _s in _e.get('series', [])
                     if _s['name'].startswith('Schwab') and _s.get('values')
                     and _s['values'][0] is None})


# 「本页哪些图上真的有红色竖虚线」一律从建好的 payload 现读，不手写编号 ——
# 断点会随窗口滚动进出，写死的那句话正是本轮复查抓到的第一类错（图注说画了、图上没有）。
_DRAWN = sorted({e['n'] for e in ex if e.get('break_at')})
_NO_BRK = sorted({e['n'] for e in ex
                  if e['kind'] in ('lines', 'lines_endlabels') and not e.get('break_at')})
_SCHW_DRAWN = drawn_for(ex, SCHW_NNA_BRK)
_HOOD_DRAWN = sorted(set(drawn_for(ex, HOOD_ND_BRK)) | set(drawn_for(ex, HOOD_CUST_BRK))
                     | set(drawn_for(ex, HOOD_TPA_BRK)))
_HEAT_NS = sorted(N_HEAT.values())
_others = [t for t in RAW if LATEST_EACH[t] != LATEST]


# 有机增速图上「单月年化 vs 滚动 12 个月」的当期读数 —— 现算，供页尾口径说明并排印出。
# 不并排印，读者拿本页 Exhibit N_ORG 的线去核各单票页 Exhibit 3/4 的次轴必然对不上。
def _org_now(t):
    a = df.get(f'{t}_org')
    b = df.get(f'{t}_org_roll')
    if a is None or b is None:
        return None
    a, b = a.dropna(), b.dropna()
    if not len(a) or not len(b):
        return None
    return float(a.iloc[-1]), float(b.iloc[-1])


_ORG_ROWS = []
for _t in ('schw', 'lpla', 'hood'):
    if _t not in HAS:
        continue
    # 变量名不要叫 _v —— 本文件下面把 _v 绑给了 _v0（取当期读数的那个函数），
    # 在这里覆盖掉它会让 headline 那几行报 'tuple' object is not callable。
    _og2 = _org_now(_t)
    if _og2:
        _ORG_ROWS.append(f'{NAME[_t]} 单月年化 {_og2[0]:.1f}% / 滚动 12 个月 {_og2[1]:.1f}%'
                         f'（差 {abs(_og2[0] - _og2[1]):.1f}pp）')
ORG_MIX_TXT = (
    f'<b>有机增速图（Exhibit {N_ORG}'
    + (f' / {N_ORG_HOOD}' if N_ORG_HOOD else '')
    + '）画的是<u>单月</u>年化水平值</b>（当月净流入 x 12 ÷ 上月末资产），'
    '与各单票页柱子的口径一致；而各单票页那几张图的<b>次轴</b>画的是滚动口径的同比 —— '
    '同一个指标在本页与单票页上以两种口径出现，所以这里把当期读数并排现算印出：'
    + '；'.join(_ORG_ROWS) + '。' if _ORG_ROWS else '')
# ── 页尾口径说明里「为什么不换滚动口径」那一段的实测，现算 ──────────────────
# 从前这里是一句写死的散文：「最硬的一条在 Exhibit N_ACCT：IBKR 账户数换成 12 个月
# 均值同比之后，逐月标准差反而变大」。窗口从 25 个月放宽到全历史之后那句话翻了面
# （见 caliber_evidence 的 docstring），而同一页 Exhibit N_ACCT 的图注是现算的，
# 于是页尾与图注当场自相矛盾。现在这一段由数据生成，翻面就跟着翻。
_CAL = caliber_evidence(
    [(NAME[_t], f'{_t}_assets', _i4, N_YOY) for _t in ('schw', 'lpla', 'ibkr', 'hood')
     if _t in HAS]
    + [(NAME[_t], f'{_t}_accounts', _i6, N_ACCT) for _t in ('ibkr', 'hood') if _t in HAS])
_CAL_NOISY = [r for r in _CAL if r[0] < 1]
_cal_one = (lambda r: f'{r[1]}（Exhibit {r[4]}，{r[2]:.1f}pp vs {r[3]:.1f}pp，{r[0]:.2f} 倍）')
if not _CAL:
    _CAL_TXT = ''
elif _CAL_NOISY:
    _CAL_TXT = (
        '<b>逐条实测（两种口径先对齐到同一批月份，再比逐月标准差）</b>：'
        + f'{len(_CAL)} 条存量序列里有 {len(_CAL_NOISY)} 条换成均值口径后<b>反而更吵</b> —— '
        + '、'.join(_cal_one(r) for r in _CAL_NOISY)
        + (f'；其余 {len(_CAL) - len(_CAL_NOISY)} 条是均值口径更稳'
           f'（比值 {_CAL[len(_CAL_NOISY)][0]:.2f}–{_CAL[-1][0]:.2f} 倍）。'
           if len(_CAL) > len(_CAL_NOISY) else '。')
        + '<b>所以「换成均值就一定更稳」不成立，但反过来也不成立</b> —— '
        '这一段是实测，不是本页选口径的全部理由，主因仍是上面那条结构性的。')
else:
    _CAL_TXT = (
        '<b>逐条实测（两种口径先对齐到同一批月份，再比逐月标准差）</b>：'
        + f'本轮 {len(_CAL)} 条存量序列<b>没有一条</b>在换成均值口径后变吵'
        + f'（比值 {_CAL[0][0]:.2f}–{_CAL[-1][0]:.2f} 倍，最接近翻面的是 {_cal_one(_CAL[0])}）。'
        + '<b>这一条与本站从前的说法相反，就照实印</b>：25 个月窗口下'
        f' {NAME.get("ibkr", "IBKR")} 账户数曾是 0.57 倍的强反例，窗口放宽之后翻了面。'
        '所以本页保留点对点的理由只剩上面那条结构性的 —— 「实测更稳」这半句已经不成立，'
        '不要再拿它当论据。')

notes = [
    f'<b>发布门槛：共同最新月，不是各家自己的最新月。</b>本页统一截到 <b>{mlab(LATEST)}</b>，'
    f'由成员中最慢的 {LAG} 决定。'
    + ('各家自身的最新月：'
       + '；'.join(f'{NAME[t]} {mlab(LATEST_EACH[t])}' for t in sorted(RAW)) + '。'
       if RAW else '')
    + ('其中 ' + '、'.join(f'{NAME[t]}（已到 {mlab(LATEST_EACH[t])}）' for t in _others)
       + ' 更新更早的月份<b>本页一律不画</b>——各家披露节奏散在次月 1–20 日，'
         '若每家都画到自己的最新月，末端那几个月的「谁强谁弱」全是披露时点造成的假象。'
       if _others else '本次四家的最新月一致，无短板。'),

    '<b>成员没齐就不出页。</b>必需成员（Schwab / LPL / IBKR）的 series CSV 缺失、缺列或全空时，'
    '本脚本打印说明并以退出码 0 正常结束，不写半张页 —— '
    '<code>monthly_run.py</code> 的 <code>build_cross()</code> 会在成员齐了之后重跑，这不是失败。'
    'Robinhood 是后加的成员，缺了会退回原来的三家，图注里会写明少了谁。',

    '<b>Robinhood 只进它口径真可比的图。</b>入图的四条轴：客户资产'
    '（total platform assets ⇄ Schwab/LPL 的 total client assets ⇄ IBKR 的 client equity）、'
    '净流入（net deposits ⇄ core NNA ⇄ organic NNA，都按「当月流量 × 12 ÷ 上月末资产」年化）、'
    '日均交易（股票+期权+加密 DATs 之和）、融资余额（margin book）。'
    '<b>不入图的：客户现金</b> —— Robinhood 把它拆成 cash sweep（扫到合作银行、表外）与 '
    'cash and deposits（留在券商）两条，不发布同一口径的合计，取任一条与 LPL 的 client cash、'
    'IBKR 的 client credits 并排都会错；<b>三家的长历史重定基图</b> —— 它的月度披露最早只到 '
    f'{mlab(_HOOD_F) if _HOOD_F else "2021-01"}，够不到另外三家共同的 {mlab(B18)} 基期，'
    f'另出一张四家同基期（{mlab(B23)}）的图（Exhibit {N_REB23}）。'
    + (f'<b>有机增速也单独占一张（Exhibit {N_ORG_HOOD}）</b>：它的年化净流入常年是另外两家的'
       '四到十倍，与它们同轴会把 Schwab 与 LPL 压成贴零的一条带（原来就是这样，'
       'headline 写的「Schwab / LPL 各几个点」在图上根本读不出来）。'
       '同一单位不等于同一量纲，拆图不是回避比较 —— 两张图的纵轴单位相同，'
       '数值可以直接比大小，只是不要把线形叠着看。' if N_ORG_HOOD else ''),

    '<b>「可比」不等于「相同」，各图注已逐条标出差异。</b>客户资产的三种叫法'
    '（client assets / client equity / platform assets）都是「客户放在这家平台上的资产」，'
    '可直接并排；但日均交易的「一笔」三家定义不同（Schwab 数成交笔数、'
    'IBKR 报的是 Total Client DARTs、含不在 IBKR 清算的客户、Robinhood 是三个市场之和），'
    '融资余额里 Schwab 含 short credits 而另两家不含，'
    '账户口径 IBKR 数账户、Robinhood 数「有入金的客户」。'
    '这些图的<b>水平值只能当量级读，方向与拐点才是可比的信息</b>。',

    '<b>流量类不算环比百分比。</b>净新增资产是流量，环比百分比的分母是上个月的流量，'
    '一个月的噪音会被放大成趋势。按 GS「LPLA monthly metrics」的规矩改用<b>年化有机增长率</b>'
    f'（当月净流入 × 12 ÷ 上月末客户资产），见 Exhibit {N_ORG}'
    + (f' 与 Exhibit {N_ORG_HOOD}' if N_ORG_HOOD else '') + '。'
    '比率序列的差异一律用<b>百分点（pp/bp）</b>，不是「百分比的百分比变化」；'
    '<code>abs(v) &lt; 1</code> 时用 bp，否则用 pp（CONTRACT §2）。'
    '四舍五入之后正好是零的负数一律回正 —— 不印「-0bp」「-0.0%」这种带负号的零。',

    # ── 同比口径：本页只有一种，但必须说清楚为什么与各单票页不同 ──
    f'<b>⚠ 同比口径：本页画同比的图<u>全部</u>用点对点（单月）口径，与各单票页不同，'
    f'原因逐图实测过。</b>本页画同比的是 Exhibit {N_YOY}（客户资产 y/y）、'
    f'Exhibit {N_ACCT}（账户 / 客户数 y/y）与 Exhibit {_exl(_HEAT_NS)} 四张热力矩阵，'
    '<b>它们画的都是存量序列</b>（客户资产 / 客户权益 / 平台资产 / 账户存量）。'
    '各单票页（/schw/、/hood/、/lpla/、/ibkr/）本轮把<b>流量</b>类图的同比改成了'
    '「12 个月滚动合计同比」，本页一张都没改 —— 不是漏了，是本页根本没有画流量同比的图'
    '（净流入在本页是以<b>年化有机增速</b>的形式出现的，那是水平值不是同比）。'
    '<b>这里要更正一句本站从前的说法</b>：「存量不能做滚动，所以只能点对点」是<b>错的</b> —— '
    'Σ12/Σ12′ 里的除数约掉，12 个月滚动合计比恒等于 12 个月滚动<b>均值</b>比，'
    '而「去年一整年的平均客户资产 vs 前年」是个真实存在、可以核对的量；'
    '假的只是<b>「合计」这个名字</b>（12 个月末余额相加不指代任何东西）。'
    '所以存量<b>可以</b>平滑。本页仍用点对点，<b>主因是结构性的</b>：'
    '均值口径按构造滞后约半年、回答的是「去年一整年的平均水平 vs 前年」，'
    '而横截面页要比的是「现在相对去年此刻谁快」；存量的分子分母又都是时点数、'
    '不含日历效应，本来就没有流量那种被小分母放大的毛病。'
    f'{_CAL_TXT}'
    f'另外，Exhibit {_exl(_HEAT_NS)} 的热力矩阵<b>永远不换口径</b>：'
    '逐格的月度波动与季节形状就是那类图的题眼，平滑掉等于把它唯一的信息抹掉，'
    '所以标题里直接写了「单月同比」。'
    'Exhibit 1 汇总表的 y/y 列同样是单月口径，且<b>刻意不改</b> —— '
    '它恒等于表内算术（第一列 ÷ 第三列），读者可以直接验算；'
    '换成别的口径这一步就会得出另一个数，表内自相矛盾比口径混用更糟。'
    f'页顶「{B.TITLE}」一段（brief）引用的客户资产 y/y、IBKR 现金/资产同比与'
    '有机增速名次<b>同样全部是单月口径</b>：与汇总表同口径、逐格可对，'
    '句中凡同比措辞均已标注「单月」，有机增速名次标注「单月年化」——'
    '单月读数在那一段只作位置与基数陈述（名次 / 齐备族数 / 峰值月），不作趋势断言。'
    f'{ORG_MIX_TXT}',

    '<b>口径断点：图注说画了，图上就必须真有。</b>本页登记在册的断点分四组 —— '
    'LPL 的<b>四次</b>整体并表（NPH 2017-12 起分批至 2018-04 合计 $72.3bn、'
    'Waddell & Reed 2021-04 $67.1bn、Atria 2024-10 $88.3bn、Commonwealth 2025-08 $275.0bn；'
    '登记判据是「当月 Acquired NNA ≥ 当月末客户资产的 5%」，写在 <code>build/lpla.py</code> 的 '
    '<code>ACQ_BREAKS</code> 上方，不属于这四笔的条目全在 1% 以下）、'
    'LPL 自己改定义的<b>两条口径断点</b>（2019-05 起 Total NNA 改为「净流入 + 股息利息 − 投顾费」，'
    '2019-04 起客户现金从 Total Cash Sweep Balances 改成含货基的 Total Client Cash Balances）、'
    'Schwab 2025-01 起把单一客户流入的剔除门槛从 $10bn '
    '提到 $25bn、Robinhood 的 Bitstamp（2025-06 起并入净流入与客户数）与 TradePMR / WonderFi。'
    '<b>其中前两组是本轮窗口放宽之后才第一次进到本页图里的</b>：'
    'NPH / Waddell & Reed 与那两条口径断点在 <code>build/lpla.py</code> 里早有登记，'
    '本页此前的 25 个月窗口够不到，于是两页对同一条 LPL as-reported 序列给出了不同的'
    '可比性判断。现在本脚本每次构建都把 <code>ACQ</code> / 并表断点 / 口径断点三张表'
    '对着 <code>build/lpla.py</code> 的同名表机器复核（<code>_sync_lpla()</code>），'
    '分叉就停更 —— 「改一处要改两处」这句话本身拦不住任何东西。'
    + (f'<b>本轮真正画出红色竖虚线的是 Exhibit {_exl(_DRAWN)}</b>'
       f'（其中 LPL 并表 {_exl(_LPL_DRAWN)}'
       + (f'、Schwab 门槛 {_exl(_SCHW_DRAWN)}' if _SCHW_DRAWN else '')
       + (f'、Robinhood {_exl(_HOOD_DRAWN)}' if _HOOD_DRAWN else '')
       + '），语义一律是「从这一期起<b>这一条线</b>与左侧不可比，同图的其他公司不受影响」。'
       if _DRAWN else '本轮没有任何断点落在各图窗口内，故一条竖虚线都不画。')
    + (f'没有断点线的折线图是 Exhibit {_exl(_NO_BRK)}：它们画的序列在各自窗口内没有登记在册的'
       '口径变化（或断点已滚出窗口）。' if _NO_BRK else '')
    + f'Exhibit 1 汇总表与 Exhibit {_exl(_HEAT_NS)} 热力矩阵的图型不支持断点线'
    '（表格与矩阵都没有连续 x 轴），改在各自的表注 / 图注里写明。'
    '断点一旦滚出窗口，线与图注文案会<b>一起</b>消失，不会剩下一句「红色竖虚线 = …」的空话。'
    + (f'LPL 当期的量级：{LP_RANK_TXT}' if LP_RANK_TXT else ''),

    f'<b>横截面页独有的两张归一化图。</b>Exhibit {N_MGNPCT}（融资余额 / 客户资产）与 '
    f'Exhibit {N_CASHPCT}（客户现金 / 客户资产）把余额按各自的客户资产归一化：'
    '绝对额只说明谁大，占比说明「同样一块客户资产上，谁的客户加了更多杠杆 / 留了更多现金」。'
    '分子分母的口径差异（见上）会造成系统性水平偏差，趋势与相对位次才是要看的。'
    f'并表月要特别小心：Exhibit {N_CASHPCT} 的分子与分母跳的幅度不同，占比会机械地掉一截，'
    '看着像「客户把现金投出去了」，其实是并购摊薄，图注里已给出 bp 与它占全窗口变动的比例。',

    '<b>缺的月份不补、不连。</b>Schwab 的月末融资余额、DATs、月末 sweep cash 与月末货基'
    '是 2026-01 那期月报<b>一次新增的同一批列</b>'
    f'（那一期的 13 个月滚动表回溯至 {mlab(_schw_mgn0.index[0]) if len(_schw_mgn0) else "2025-01"}，'
    f'更早的月份公司没有印过），所以 Schwab 那条线在 Exhibit {_exl(_SCHW_LATE)} 上'
    f'只占右端 {len(_i7) - (len(_i7) - len(_schw_mgn0)) if len(_schw_mgn0) else 0} 格，左段是空的；'
    f'Robinhood 同理，它的月度披露自 {mlab(_HOOD_F) if _HOOD_F else "2021-01"} 起 —— '
    '那是没有披露，不是余额为零。所有非有限值一律写 <code>null</code>，图与表都断开，不画假点。'
    f'<b>这几张图从前是把另外几条一起砍到 Schwab 的起点</b>（窗口 {len(_schw_mgn0)} 个月），'
    '本轮改掉了：一家的披露缺口不该变成另一家的历史损失。'
    f'<b>反例在 Exhibit {N_CASHPCT}</b>：那张图的 Schwab 用的是官方自己印的现金占比'
    f'（{mlab(_first("schw_cash_pct"))} 起），反而是全图最长的一条 —— '
    '「Schwab 的历史短」不是这家公司的性质，是逐列各自的披露边界。',

    f'<b>纵轴。</b>重定基图（Exhibit {N_REB18}、{N_REB23}、{N_REB19}）沿用 deck 的自适应量程，'
    '各条线右端标出当期指数值 —— 长历史图上那是唯一的绝对水平锚点，没有它只能靠网格线目测；'
    '各条线本来就都从基期的 100 起画（图的左缘就是基准），故不再另画一条 100 的水平参考线。'
    # 上下界都是现算的（判据见 Exhibit N_ORG 那段注释），所以这里只能引变量；
    # 连「用没用截轴」都不能写死 —— 两条几何判据一档都过不了时本图就不截轴了。
    + (f'Exhibit {N_ORG} 用了截轴（{EX5_FLOOR:.0f}% 到 {EX5_CAP:.0f}%，'
       f'上下界都按实测现算，判据见该图图注）：'
       '<b>截轴不删点</b> —— 超界的点画成空心红圈、真值竖排标在图上，表格视图里给的也是真值。'
       if _over5 else
       f'Exhibit {N_ORG} 本轮没有截轴 —— 实测没有哪个上界能同时让越界月的竖排标注排得开、'
       '又让轴刻度落在整数百分点上，那就宁可让轴被尖峰撑高。')
    + '本站没有对数轴，量级差太远的序列一律拆图而不是压缩坐标。',

    f'<b>窗口：逐图现算，既不是「近 N 个月」，也没有统一的起点。</b>'
    f'本页各图的左端一共 {len(_LEFT)} 个，最早 {mlab(_LEFT_MIN)}、最晚 {mlab(_LEFT_MAX)}：'
    f'{_LEFT_TXT}。原先所有近期多线图都写死 25 个月'
    '（照搬原 deck 的 <code>win=25</code>），而各家序列早已回补到 2016-01（IBKR / LPL）与 '
    f'2013-09（Schwab）—— 回补了却只画近两年，等于回补给谁看。现在左端一律由数据现算：'
    '<b>本图各条线里最早那条的首个有值月</b>，右端是共同最新月；'
    '所以「本页一律从某年起」这种话本页不会说，也说不出来。'
    '各线起点不齐时（Schwab 的融资余额 / DATs 只有 2025-01 起、Robinhood 只有 '
    f'{mlab(_HOOD_F) if _HOOD_F else "2021-01"} 起）'
    '<b>不为迁就短的那条去砍长的那条</b>，改用能吃 null 的 <code>lines</code> 图型、'
    '短的那条前段留空 —— 这一点在横截面页尤其要紧：把两条起点差好几年的线对齐到图的左缘，'
    '读者会把它们读成同期对比。'
    f'仍然写死的只有两个窗口：核对表 13 个月（跨公司逐月对数用）与热力矩阵最多 7 年。'
    '通栏与 x 标签抽稀由 <code>build/mrwin.py</code> 的 <code>layout_all()</code> 按 '
    '<code>assets/charts.js</code> 的量边距算式复算，不是目测，各图图注里附了实测的每期像素数。'
    '所有数值与格式化都在 Python 侧完成，页面不做任何计算 —— '
    '同一个数字在两个语言里各算一遍，迟早会出现图上与表里对不上而没人发现。'
    '汇总表的 3Y %ile 也一样：判据在 <code>build/pctile.py</code>，全站 14 个生成器共用一份 '
    '（回放近 24 个月，≥70% 的月份钉在端点就留空）。'
    '本页曾用「≥90% 的月环比不降」这个代理判据，结果同一条 LPL total client assets 在 '
    '/lpla/ 被判成噪音留空、在本页却印成绿色 100 —— 判据是口径，口径只能有一处定义。',
]

headline = (f'共同最新月 {mlab(LATEST)}（短板 {LAG}）'
            f' · 客户资产 Schwab {_v("schw_assets", 0, "$")}bn / LPL {_v("lpla_assets", 0, "$")}bn'
            f' / IBKR {_v("ibkr_assets", 0, "$")}bn'
            + (f' / Robinhood {_v("hood_assets", 0, "$")}bn' if 'hood' in HAS else '')
            + f' · 年化有机增速 Schwab {_v("schw_org", 1)}% / LPL {_v("lpla_org", 1)}%'
            + (f' / Robinhood {_v("hood_org", 1)}%' if 'hood' in HAS else '')
            # 头条只报 as-reported 的 LPL y/y 就是只报喜：那 +38% 里有一大块是买来的。
            # 有剔并购口径就把两个数一起给，没有（缺月）就一个都不给。
            # 口径写进标签：本站别的页上同名的 y/y 已经有画滚动口径的了，
            # 抬头里一个光秃秃的 y/y 会被拿去和那些数互相核，然后对不上。
            + (f' · LPL 客户资产 y/y·单月 {signed(_LP_YOY_NOW, 1, "%")}'
               f'（剔并购 {signed(LP_YOY_EX, 1, "%")}）'
               if _LP_YOY_NOW is not None and LP_YOY_EX is not None else ''))


# ── 这里原来有一个 `_lp_cash_clause()`：brief 里 LPL 客户现金占比的那一句 ──
# 整句撤了（理由见 compose_brief 的「分寸」一节），函数跟着删掉 —— 留一个没人调用的
# 生成器，下一个人只会照它把句子接回去，而接回去的正是本轮要收的那一层。
#
# 它当年修对的两件事记在这里，谁要重写这一句必须一并带上：
#   1. 占比的**分母**被 2025-08 并入 Commonwealth（Acquired NNA +$275.0bn）机械摊薄，
#      极值断言（「N 个月最低」）必须先用 `acq_roll12()` 还原再判，还原后仍是最低才
#      许写「最低」—— 与客户资产 y/y 的剔并购是同一条约定，口径只能有一处定义。
#   2. 不许用「亦然」承接 IBKR 那句：IBKR 那句里有「绝对额创新高」与「摊薄非撤资」，
#      而 LPL 的现金绝对额离 2022-06 的自身峰值还差一大截，承接过来就是假话。
# 并表当月对这条比率的一次性摊薄仍在 Exhibit N_CASHPCT 的图注里现算（dilution_txt），
# 没有随这一句消失。


def compose_brief(df, latest):
    """横截面页顶部的 ~300 字数据总结（payload 的 `brief` 字段）。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R3 日历护栏 /
    R4 单位恒等 / R5 标注 / R6 有效位），那边只算事实，句子在这里拼 ——
    措辞是口径的一部分，属于各家自己。每个数字都当场从序列算，**没有一处硬编码**：
    共同最新月、领先几个月、齐备几家、名次、「N 个月最高/最低」、峰值停在哪个月，
    下个月重跑全部自己变。

    ═══ 横截面页独有，单票页不能照抄 ═══
      · **第一句必须是「能不能比」，不是「谁更强」。** 单票页的读数就是那家的最新读数；
        本页统一定格在<b>共同最新月</b>（最慢的成员决定），各家自己往往已多披露 1-2 个月。
        不先说这一句，读者会拿本页的横比当「当下」，而它是一个被最慢那家钉住的旧截面。
      · **可比性是分层的，按指标族逐族点名。** 四家齐备的只有客户资产一族；客户现金
        少 Robinhood（它把现金拆成不可合计的两条），账户存量只剩两家（IBKR 数账户、
        Robinhood 数人；Schwab 只披露当月新开、LPL 披露的是投顾人数）。
        把一个缺员的族当成「四家横比」是本页最大的误读源 —— 齐备几家由
        `FAMS` 逐族现数，不写死（客户现金那一族 2026-08-19 刚从两家变成三家）。
      · **「谁创新高」在横截面上受序列长度左右**（R1 的横截面变体）。Schwab 的月末融资
        余额只有 2025-01 起的历史、Robinhood 只有 2021-01 起，IBKR 有 2016-01 起 ——
        在一条十几个月的序列上「停在峰值」与在 125 个月上「峰值停在 2017 年」根本不是
        同一件事。单票页没有这个问题，所以这句话别家写不出来。
        （窗口 2026-08-19 放宽到各条线自己的起点之后，这个长短差在图上直接看得见了：
        Exhibit 8 / 10 / 12 里 Schwab 那条只占右端十几格，另两条铺满全轴。）
      · **LPL 的名次要按还原口径报**：as-reported 的客户资产 y/y 含 Atria 与
        Commonwealth 两次整体并表，剔掉滚动 12 个月的 Acquired NNA（`acq_roll12()`）
        之后名次会掉，句子里必带「（还原口径）」（R5）。这条约定对**任何**以 LPL 客户
        资产为分母的比率同样成立：分母被并表机械摊薄，极值断言（「N 个月最低」）必须
        先还原再判，还原后不成立就不许写「最低」。现金占比那一句本轮整句撤了
        （见下方「分寸」），约定留着 —— 谁要把它写回来，得连着还原一起写回来。
      · **R3（日历护栏）在本页全程不适用**：本页没有任何「当月合计量」列 —— 客户资产 /
        现金 / 融资余额都是月末时点值，DATs/DARTs 三家披露的本来就是<b>日均</b>笔数。
        再除一次交易日会造出一个根本不存在的修正（brief.py 开头点名的那个坑）。

    ═══ 与本页 2026-08 同比口径改造的关系（移植时的口径适配）═══
      本页与 cboe/cme 那类页不同：**画同比的图本轮一张都没改滚动**（全是存量序列，
      理由与实测见页尾「⚠ 同比口径」与各图图注），所以 brief 引用的 y/y 与汇总表、
      与下方各图是**同一个口径（单月）**，不存在「brief 单月 vs 图上 TTM」的错位。
      但同名的客户资产 y/y 在各单票页（/schw/、/hood/ …）的次轴已是滚动口径，
      读者跨页核数会对不上，所以句中凡同比措辞仍按 CONTRACT §6 标「单月」。
      有机增速自本轮起两个口径并存（图上画单月年化、图注与页尾并印滚动 12 个月对照，
      `{t}_org_roll` 列），brief 引用其名次时点名「单月年化」——名次是在单月年化
      序列上排的，拿图注里的滚动读数去核对不上，那不是错，是两个口径。
      `{t}_org_roll` 这几列新派生列**不进** brief 的任何扫描：FAMS / ORG / 峰值扫描
      全部按显式列名白名单走，不遍历 df.columns，新列不会被静默卷入。
      单月读数在本段只作**位置与基数**陈述（名次 / 齐备族数 / 峰值月），不作趋势断言 ——
      趋势归下方各图。另外本页存量图注本轮刚更正过「存量不能滚动」的旧说法
      （滚动**均值**合法，假的只是「合计」这个名字），本段没有一句写「存量不能滚动」，
      也不许写回来。

    ═══ 措辞由当场算出的量决定分支，一个定性词都不许写死 ═══
      「只有 / 创新高 / 最低 / 却」这类词全部挂在当月算出的名次、占比、`peak_scan`
      的分组上：本月读着通顺的句子，下个月数字一变就会变成假话，而那种假话没有任何
      自动检查拦得住（历史重放是唯一能逮到它的手段）。同理，缺值月一律**该句不写**
      （`B.need`），不是让整页构建失败。

    ═══ 分寸：以 build/ibkr.py 的 compose_brief() 为准 ═══
    那一版是用户逐句验收过的标准，既是上限也是下限 —— 四句四层、一句一个意思、~300 字。
    本页此前是六句，且句句是三四个从句的串联：比样板花哨。收的办法不是砍字数，是砍层数。

    现在五句，比样板多的那一层是开头的「能不能比」（横截面页的身份，不能省）：

        能不能比（时点 + 覆盖）→ 谁领先（还原口径下名次会不会翻）
        → 基数（上月名次解释本月读数）→ 谁背离（绝对额与归一化占比同月一头一尾）
        → 峰值的可比性（「在自身峰值」在十几个月和 125 个月的序列上不是同一件事）

    撤掉的是「LPL 客户现金占比亦为全样本最低，降幅 X% 来自 Commonwealth 并表当月」
    那一句。它不是错的（「极值先还原再判」那一层是对的，约定见上），是**逐家展开**：
    紧接着 IBKR 现金那句再讲第二家的同一个指标，读者拿到的是第二个例子而不是第二个
    层次；句尾「降幅的 X% 来自并表当月」还多压了一层贡献度拆解。跨公司比较写到
    「谁领先谁背离 + 口径可比性的边界」就够，再往下就是把横截面页写成四份单票页。
      （旁证：历史重放里它在 2018-2020 一路印出「LPL 占比排倒数前100%」—— 序列还短的
      月份里「倒数前 100%」等于没说，一句自己就撑不住的话不值得占掉整整一句的篇幅。）

    口径标注（推导值 / 还原口径 / 并购并表）一个都不因为收篇幅而删：那不是花哨，
    是诚实。被撤的是整句，不是某句的标注。
    """
    i = len(df.index) - 1
    MO = [str(p) for p in df.index]
    # 「两个月 / 两家」这条中文量词规矩已经由 brief.cn() 统管（序数写「第二」时传
    # ordinal=True），本页不再自己包一层 —— 同一条规矩在两处定义，早晚会分叉。
    cn = B.cn
    fin = lambda a: int(np.isfinite(np.asarray(a, float)).sum())

    # ── 边界一（时点）：本页的读数不是各家自己的最新读数 ──────────────────
    # 只点名跑得最快的那一家 + 领先几个月：四家逐一列月份会把这一句撑到整段的三分之一，
    # 而页脚已经逐家列过。这里要读者记住的是「本页不是当下」这一件事。
    # 「本页定格在共同最新月」抬头已经印过（headline / subtitle 各一次），这里不复述，
    # 只写抬头给不出的那一半：领先的那家多披露了几个月、而本页不取。
    ahead = [(t, (LATEST_EACH[t] - latest).n) for t in RAW if LATEST_EACH[t] > latest]
    if ahead:
        t0, gap = max(ahead, key=lambda x: (x[1], x[0]))
        ahead_txt = f'本页不取 {NAME[t0]} 多出的{cn(gap)}个月'
    else:
        ahead_txt = '各家最新月一致'

    # ── 边界二（覆盖）：可比性是分层的，逐族点名齐备几家 ────────────────────
    # 列名是显式白名单：本轮新加的 {t}_org_roll 派生列刻意不在任何一族里 ——
    # 它是有机增速的滚动对照口径，不是一个新指标族。
    FAMS = [('客户资产', ['schw_assets', 'lpla_assets', 'ibkr_assets', 'hood_assets']),
            ('净流入', ['schw_flow', 'lpla_flow', 'hood_flow']),
            ('融资余额', ['schw_margin', 'ibkr_margin', 'hood_margin']),
            ('日均交易', ['schw_dats', 'ibkr_dats', 'hood_dats']),
            ('客户现金', ['schw_cash', 'lpla_cash', 'ibkr_cash']),
            ('账户存量', ['ibkr_accounts', 'hood_accounts'])]
    cnt = {nm: sum(1 for c in cs if c in df.columns and np.isfinite(df[c].loc[latest]))
           for nm, cs in FAMS}
    full = [nm for nm, k in cnt.items() if k == len(HAS)]
    kmin = min(cnt.values())
    # kmin == 成员数意味着六族全齐，那时「最窄的是谁」是个没有内容的句子，整句省掉
    narrow = [nm for nm, k in cnt.items() if k == kmin] if kmin < len(HAS) else []
    # 月份本身抬头已经印过（「共同最新月 May-26（短板 …）」），这里不再复述
    # 「只有」这类量词由 B.quant 按占比给：齐备的族数是当场数出来的，写死「只有」
    # 会在六族齐备的那个月印出「六族里齐备的只有六族」。
    if not full:
        s1 = f'能不能比：{ahead_txt}；{cn(len(FAMS))}族没有一族{cn(len(HAS))}家齐备。'
    else:
        s1 = (f'能不能比：{ahead_txt}；'
              f'{B.quant(len(full), len(FAMS), "族")}{cn(len(HAS))}家齐备'
              f'（<b>{"、".join(full)}</b>）'
              + (f'，{"、".join(narrow)}各{cn(kmin)}家。' if narrow else '。'))

    # ── 相对表现 + R5：名次一律按还原口径报 ─────────────────────────────
    # LP_YOY_EX 是当期的模块级常量，这里改成按 latest 现算 —— 否则把序列截到历史某月
    # 重放时，用的还是当期那个 t12，名次会算在一个不属于那个月的还原口径上。
    # 「y/y（单月）」的口径标注（CONTRACT §6）：本页图表全是单月口径、表内可直接验算，
    # 但各单票页同名 y/y 的次轴已是滚动口径，不标读者会拿这里的名次去核那边的线。
    yy = {NAME[t]: float(df[f'{t}_yoy'].loc[latest]) for t in ('schw', 'lpla', 'ibkr', 'hood')
          if t in HAS and f'{t}_yoy' in df.columns and np.isfinite(df[f'{t}_yoy'].loc[latest])}
    order = sorted(yy, key=yy.get, reverse=True)
    lp_ex, _t12 = lp_yoy_ex(df, latest)
    s2 = ''
    if len(order) >= 2 and lp_ex is not None and NAME['lpla'] in yy:
        adj = dict(yy, **{NAME['lpla']: lp_ex})
        order2 = sorted(adj, key=adj.get, reverse=True)
        r0, r1 = order.index(NAME['lpla']) + 1, order2.index(NAME['lpla']) + 1
        # 完整位次留给 Exhibit 1 与 Exhibit 4 的端点标签，「谁居首」也留给它们 ——
        # 位次表本身不是解读（本页第一句的职责是「能不能比」而不是「谁更强」），
        # 只有 LPL 那一处**名次会翻**才是。
        a0, a1 = cn(r0, ordinal=True), cn(r1, ordinal=True)   # 序数写「第二」不是「第两」
        s2 = '客户资产 y/y（单月）剔并购（还原口径）后 LPL '
        s2 += (f'从第{a0}掉到第{a1}、与 {order2[r1 - 2]} 换位。' if r1 > r0
               else f'仍居第{a1}。')
    else:
        # 早年的月份 y/y 根本凑不齐（各家资产序列的起点是 Schwab 2013-09、LPL 与 IBKR
        # 2016-01、HOOD 2021-01，各自要满 12 个月才有分母，所以 y/y 分别自 2014-09 /
        # 2017-01 / 2022-01 起）。那时这一句改说「谁还进不了这个横比」——
        # 这仍是「能不能比」，比硬凑一个两家的名次表有用。
        young = [NAME[t] for t in ('schw', 'lpla', 'ibkr', 'hood')
                 if t in HAS and NAME[t] not in yy]
        if young and yy:
            s2 = (f'客户资产 y/y（单月）这个月只有{cn(len(yy))}家算得出，{"、".join(young)} '
                  f'的 12 个月前分母还缺，横比先看水平值。')
        elif len(order) >= 2:
            # 还原口径算不出来（缺 LPL 的分母）时，只报能报的两端，不写半句还原
            s2 = f'客户资产 y/y（单月）里 {order[0]} 居首、{order[-1]} 垫底。'

    # ── R2 基数护栏：有机增速上月落在全样本底部，本月的环比要对着它读 ──────
    # 这里刻意不报环比（本页规矩：流量类不算环比百分比，比率类的 m/m 用 pp 且已在
    # Exhibit 1 里印过），只报**排名** —— 排名才是「环比看着猛」的解释。
    # 「跌到 / 回升」这类方向词一律不写：它们描述的是上上月→上月、上月→本月的走向，
    # 而句子里给的是名次，两者下个月未必同向（一家升一家跌时「同时跌到」就是假话）。
    # 名次排在 {t}_org（单月年化）上，不是 {t}_org_roll —— 本轮起两个口径并存，
    # 句子里点名「单月年化」，免得读者拿图注里的滚动读数来核名次。
    ORG = [(t, f'{t}_org') for t in ('schw', 'lpla')
           if t in HAS and f'{t}_org' in df.columns and np.isfinite(df[f'{t}_org'].loc[latest])]
    rows = []
    for t, c in ORG:
        a = df[c].values
        n = fin(a)
        be = B.base_effect(a, i)
        if be['prev_rank'] is None or be['rank'] is None or n < 2:
            continue                       # 上月缺值：这一家不进句子，而不是让整页失败
        rows.append((NAME[t], n, be['prev_rank'], be['rank']))
    s3 = ''
    if rows:
        # 「第 65/96」把名次与样本长度绑成一个自足的词 —— 各家序列长度不同，
        # 光给名次没法比。名次与年化与否无关（同一条序列同乘 12），故省掉「年化」两个字
        # 的旧做法本轮撤销：滚动口径上线后「有机增速」一个词对着两条序列，
        # 「单月年化」四个字就是消歧义的口径标注，不能省。
        #
        # 排法从「公司名一串、上月名次一串、本月名次一串」改成**一家一段**：原来的
        # 「Schwab、LPL … 上月同落全样本倒数第 7、4，本月仍只第 65/96、77/94」要读者
        # 在三串并列之间来回 zip 才知道哪个数属于谁，是全段最难读的一句。
        # 两个月都用同向的「第 x/n」（不再上月说倒数、本月说正数）：一句话里换一次
        # 方向，读者就得先判断这个名次是从哪头数起。
        #
        # 句尾那个 all() 算出来的「仍只」一并去掉：一个词同时替两家下结论，
        # 一升一降的月份必然对其中一家失真，而「第 65/96」本身已经把高低说清楚了。
        s3 = ('基数：有机增速（单月年化，推导值）的全样本名次，'
              + '；'.join(f'{nm} 上月第 {prv}/{n}、本月第 {cur}/{n}'
                          for nm, n, prv, cur in rows) + '。')

    # ── 口径背离（R1 + R4）：绝对额与归一化占比同月一个到顶、一个到底 ─────
    # 「创新高 / 却 / 最低」全部挂在当月名次上。绝对额未必每月都在最前、占比也未必
    # 每月都在最后，任何一个写死的方向词都会在某个月与它自己引用的数字打架。
    cash, ast = df['ibkr_cash'].values, df['ibkr_assets'].values
    cpct = df['ibkr_cash_pct'].values
    s4 = ''
    if i >= 12 and B.need(cash[i], cash[i - 12], ast[i], ast[i - 12], cpct[i]):
        pu = B.per_unit(cash, ast, i, scale=100.0)
        n_c, n_p = fin(cash), fin(cpct)
        r_hi, r_lo = B.rank_of(cash, i), B.rank_of(-cpct, i)
        # T3：绝对额若几乎只增不减，「N 个月最高」每月都成立，是噪音不是信息
        mono = B.is_monotonic(cash)
        top = f'创 {n_c} 个月新高' if (r_hi == 1 and not mono) else f'排{B.top_pct(r_hi, n_c)}'
        # 两条回溯长度相同才叫「同期」：那才准确说出「同一段历史里一个到顶、一个到底」
        bot = (('落到同期最低' if (r_hi == 1 and n_c == n_p and not mono)
                else f'落到 {n_p} 个月最低')
               if r_lo == 1 else f'在倒数{B.top_pct(r_lo, n_p)}')
        diverge = not mono and r_hi / n_c <= 1 / 3 and r_lo / n_p <= 1 / 3
        s4 = f'IBKR 现金绝对额{top}、占比{"却" if diverge else "则"}{bot}'
        # R4：只报两个增速之商，不做「一半分子一半分母」的比例拆分（那在数学上就是错的）
        if B.need(pu.get('yoy'), pu.get('num_yoy'), pu.get('den_yoy')):
            # 落点按**两个增速的大小关系**分支，不是只按分子的正负。
            # 原来写的是「分子涨就叫摊薄」：历史重放里 113 个可算月份中有 22 个
            # （2022 全年、2020-03/04 等）分母同比是负的，占比其实在升，句子却紧挨着
            # 「现金 +12.7% ÷ 资产 -18.9%」印出「摊薄非撤资」—— 定性词与它自己引用的
            # 两个数字打架。摊薄的定义就是分母跑得比分子快，判据只能是 den > num。
            n_yy, d_yy = pu['num_yoy'], pu['den_yoy']
            land = ('分子自己在缩' if n_yy <= 0 else
                    '摊薄非撤资' if d_yy > n_yy else '分子跑赢分母')
            s4 += (f'（推导值，单月同比：现金 {B.pct(n_yy)} ÷ 资产 {B.pct(d_yy)}，'
                   f'<b>{land}</b>）')
        s4 += '。'
        # 这里曾经再接一句 LPL 的现金占比（「亦为全样本最低，降幅 X% 来自 Commonwealth
        # 并表当月」）。撤掉的理由见本函数 docstring 的「分寸」：同一个指标换第二家讲
        # 是逐家展开，读者拿到的是第二个例子而不是第二个层次。
        # **要写回来就得连着还原一起写回来**：LPL 的占比分母被并表机械摊薄，
        # 极值断言必须先用 acq_roll12() 剔掉滚动 12 个月的 Acquired NNA 再判，
        # 还原后不成立就不许写「最低」。

    # ── R1 的横截面变体：「谁在峰值」受各家披露起点长短左右 ──────────────
    MG = [(NAME[t], f'{t}_mgn_pct') for t in ('schw', 'ibkr', 'hood')
          if t in HAS and f'{t}_mgn_pct' in df.columns and np.isfinite(df[f'{t}_mgn_pct'].loc[latest])]
    pk = B.peak_scan(MO, [(nm, df[c].values) for nm, c in MG], i)
    ln = {nm: fin(df[c].values) for nm, c in MG}
    at, off = pk['at_peak'], pk['off_peak']
    # 分母用**真扫过的条数**，不是 len(MG)：被 skip_monotonic 剔掉的那条既不在 at_peak
    # 也不在 off_peak，拿 len(MG) 当分母会让「三条里只有一条」的三与实际扫描数对不上。
    n_scan = len(at) + len(off)
    # 被剔掉的必须点名。否则某家一旦越过 is_monotonic 的 0.9 阈值（Schwab 实测 0.875，
    # 只差 0.025），它会静悄悄从扫描里消失，而句子仍在替它下结论。
    skip = f'（{"、".join(pk["skipped"])} 几乎只增不减，未入扫描）' if pk['skipped'] else ''
    s5 = ''
    if at and off:
        nm_at = min(at, key=lambda x: ln[x])           # 历史最短的那条：「在峰值」最不值钱
        ref, refm = max(off, key=lambda x: ln[x[0]])
        s5 = (f'{cn(n_scan)}条融资余额占比（推导值）'
              f'{B.quant(len(at), n_scan, "条")}在自身峰值：{nm_at} 仅 {ln[nm_at]} 个月，'
              f'{ref} 的 {ln[ref]} 个月峰值在 {refm}{skip}。')
    elif off and n_scan == 1:
        # 只剩一条时不写「一条里无一条」：那句话读起来像模板没拼好
        ref, refm = off[0]
        s5 = (f'融资余额占比（推导值）本月只有 {ref} 一条有数{skip}，'
              f'它也不在自身峰值 —— 峰值停在 {refm}。')
    elif off:
        ref, refm = max(off, key=lambda x: ln[x[0]])
        s5 = (f'{cn(n_scan)}条融资余额占比（推导值）里无一条在自身峰值{skip}，'
              f'历史最长的 {ref} 峰值停在 {refm}。')
    elif at:
        nm_at = min(at, key=lambda x: ln[x])
        s5 = (f'{cn(n_scan)}条融资余额占比（推导值）本月全部在自身峰值{skip}，'
              f'但最短的 {nm_at} 只有 {ln[nm_at]} 个月历史 —— 长短不同不是同一件事。')

    return B.render([s1, s2, s3, s4, s5])


BRIEF = compose_brief(df, LATEST)

payload = {
    'ticker': 'wealth',
    'tracker': 'Wealth & Brokerage Cross-Section',
    'title': ('财富与券商组横截面：'
              + ' / '.join(NAME[t] for t, *_ in [(m[0],) for m in MEMBERS] if t in HAS)
              + f' — {LATEST.year} 年 {LATEST.month} 月'),
    'data_through': str(LATEST),
    'through_label': f'{LATEST.year} 年 {LATEST.month} 月（共同最新月）',
    'subtitle': (f'{len(HAS)} 家月度披露的横截面 · 统一截至共同最新月 {mlab(LATEST)}'
                 f'（短板 {LAG}）· 版式沿用 Goldman Sachs GIR 的 monthly-metrics 体例 · '
                 '仅图表，无观点'),
    'headline': headline,
    # headline 之下、Exhibit 1 之上的 ~300 字解读。职责与 headline 互补：
    # 那一行给读数，这一段给「读数该怎么读」。见 compose_brief 的 docstring。
    'brief': BRIEF,
    'hub_line': (f'共同最新月 {mlab(LATEST)}（短板 {"/".join(NAME[t] for t in LAGGARDS)}）· '
                 f'{len(HAS)} 家 · {len(ex)} 张图'),
    'source': SRC,
    'xlabels': XL,
    'xlabels_long': XL_LONG,
    'summary': summary,
    'exhibits': ex,
    'table': table,
    'notes': notes,
    'footer': (f'<b>发布门槛：</b>本页统一截至共同最新月 <b>{mlab(LATEST)}</b>，'
               f'由最慢的成员 <b>{LAG}</b> 决定。各家自身最新月：'
               + '；'.join(f'{NAME[t]} <b>{mlab(LATEST_EACH[t])}</b>' for t in sorted(RAW))
               + '。' + ('更新更早的月份本页不画 —— 否则末端的强弱对比只是披露时点的错觉。'
                         if _others else '本次各家最新月一致。')
               + ' · 数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
                 '仅供个人研究，不构成投资建议'),
}

# 官方发布日：取**实际入选本页的成员**里最晚的那一个 —— 本页统一截到共同最新月，
# 所以「这一页什么时候成立」等于最后发布那一家的日子（当前是 LPL，每月中旬才发）。
# 查的是 LATEST 这个共同月而不是各家自己的最新月，否则会把某家更新月份的发布日
# 安到本页画的旧月份上。用 HAS 而不是 MEMBERS：还没就绪的成员根本没画进来，
# 把它算进 max 会让日期凭空推后。任何一家查不到就整个字段省略。
SOURCE_DATE = load_source_dates().latest_of(
    SERIES, sorted(HAS), {t: LATEST for t in HAS})
if SOURCE_DATE:
    payload['source_date'] = SOURCE_DATE


def main():
    out_dir = os.path.join(ROOT, 'data')
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'wealth.js')
    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(path, payload, 'wealth')
    print(f'共同最新月 {LATEST}（短板 {"/".join(NAME[t] for t in LAGGARDS)}）'
          f' | 各家: ' + ', '.join(f'{t}→{LATEST_EACH[t]}' for t in sorted(RAW))
          + (f' | 未就绪: {[t for t, _ in skipped]}' if skipped else ''))
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）'
          f' + Exhibit {table["n"]} 核对表')
    print(f'写出 data/wealth.js  ({os.path.getsize(path) / 1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
