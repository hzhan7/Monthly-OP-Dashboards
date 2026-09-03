#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同比口径的自动判据 —— 扫 `data/*.js`，判每一张含同比的图口径对不对。

    python3 tools/check_yoy_caliber.py                    # 人读报告
    python3 tools/check_yoy_caliber.py --json out.json    # 顺带写机器可读结果
    python3 tools/check_yoy_caliber.py --page cme --verbose
    python3 tools/check_yoy_caliber.py --selftest         # 判据自测（见文件末）
    python3 tools/check_yoy_caliber.py --audit            # 当场重算几道闸门的代价

退出码：有 🔴 → 1；只有 🟡 或全过 → 0。
`--json` 不给就**不写文件** —— 判据不往仓库里丢产物，免得 `git status` 长草。

## `--audit`：注释里那几个「放开这道闸门会多出多少」的数，一律现算

本文件里每一道闸门（图型豁免、存量 / 比率豁免、回源容差、登记门槛）都配着一句
「放开它会多出多少条」。**那种数随 `data/` 快照变，写死必过期** —— 而且已经翻过车：
2026-09 有一次编辑订正了上一版的过期数（69/37/26/6 → 68/36/26/6），
可就在**同一次编辑**里，`values` 路径的收窄把 `bridge_bar` 那一档打成了 0，
于是刚订正的数当场又过期了。所以现在的规矩是：**这些数一个都不写死**，
注释只说「跑 `--audit` 当场重算」，`--audit` 用与被引用处逐字相同的分母去数。
（契约 §6.3 给的重跑方法是「复制一份到仓外、`EXEMPT_KINDS` 置空、重扫、数多出来的
`R4_mom_not_in_title`、按 kind 分档」—— `--audit` 把那套程序内建了一份，分母逐字
相同，省掉「改仓里那份跑」这一步的风险。）

## 为什么是独立脚本，而不是接进 build/payload_guard.py

`payload_guard` 被**每一个** builder import，写文件之前跑。现在（2026-08-07）有 10 个
agent 同时在改 builder，往那个文件里加规则，任何一个 bug 都会让 10 条构建同时炸，
而且炸在别人的改动上、排查成本全落在别人头上。所以先做成独立脚本，跑通、看清它在
真实 payload 上报什么，再接。**接进去的建议改法写在文件末尾 `HOW_TO_WIRE_IN`。**

## 它怎么知道一张图画的是哪种口径 —— 不看文字，回源复算

文字声明是**被检查的对象**，不能同时当证据。所以判据反过来做：

  1. 从 exhibit 的 `xlabels`（`Jul-26` / `7/26` / `2026-07`）解出月份；
  2. 把 `series/*.csv` 每一个数值列都按两种口径算一遍同比（`build/yoy.py` 的
     `mom_yoy` / `ttm_yoy_unchecked`），索引到月份上；
  3. 拿图上那条同比序列的**数值**去比对，命中哪一种口径就是哪一种。

比对的是数字不是名字，所以改标题骗不过它；反过来，凡是**派生量**的同比
（ADV × 交易日、多列相加、FX 换算过的）都匹配不上任何原始列 → 判为「未确定」，
**只计数不报错**。这是有意的：宁可漏报也不要制造噪声（本仓规矩）。

## 规则一览（编号排到 R8，R6 空着；`R0_*` 那两条查的是判据与管道自己，不查页面）
##   R1 在 2026-09 随契约翻面重写；R5 / R7 / R8 是那之后三轮对抗普查各补的一条。

  🔴 R1 画的是 **12 个月滚动口径的同比**，而这张图不在 CONTRACT §6.2 的例外名单里
       —— 全站单月是页面所有者定的（§6 抬头引了原话），页上不该再出现滚动线。
  🔴 R2 存量序列（OI / AUM / 市值 / 余额）的同比被**称作**「12 个月滚动合计」
       —— 数值恒等于滚动均值同比（没错），但「合计」对存量不指代任何真实的量。
  🟡 R3 §6.2 例外所在的页混用两种口径，而页尾「口径与方法说明」没有逐处点名。
  🟡 R4 用了单月同比但标题里没写明（CONTRACT.md §6 要求写进标题）。
  🟡 R5 §6.2 名单上的图不见了，或者**不再自称**滚动口径 —— 见 `check_whitelist()`；
  🔴 R5 名单上的**整页**这一轮没查过 —— 页文件被删、页名改了、或者**页在而整页
       解析失败**（第三种 2026-09 才补上，见 `scan_pages()`）。见
       `check_whitelist_pages()`：那一半必须在扫完所有页之后做，
       嵌在逐页检查里就等于没做（2026-09 补）。
       ⚠️ **同为 R5，两半的等级不同，那是契约定的**：整页那一条给 🔴（要能让整轮
       停机），逐图那两条维持 🟡。理由见 `check_whitelist_pages()` 的 docstring。
  🟡 R7 比率列的同比被画成「百分比的百分比」，而不是百分点差（§6.1 第 4 条）。
       编号跳过 R6：CONTRACT §6.6 已经把 `R6_` 这个前缀留给它建议的
       `R6_mom_cost_not_printed`（§6.1 第 3 条的覆盖，本文件还没做）。
       ⚠️ 引用契约要记时点，它正被并行修改：这一条读于 2026-09-02 21:4x，
       2026-09-02 深夜本轮又读了一次，`R6_` 那句仍在。
  🟡 R8 近零基数上画着同比，而这张图既没截轴、图注也没点名近零月（§6.1 第 5 条）。
       见 `check_near_zero()`。它是第一条查 §6.1 第 5 条的规则 —— 在它之前
       R0–R7 **没有任何一条**碰过那一条，坏了不会响。
  🟡 R0_page_unreadable 某个 `data/*.js` 根本解析不了 —— 「这页很干净」与「这页没读
       进来」必须分得开。⚠️ 它**不是** R5 那条 🔴 的替代品：页文件还在、只是解析失败
       时，这一条响、退出码仍是 0，而名单上的图这一轮一条规则都没跑过。
       两条一起才封得住，见 `scan_pages()` 里那张三形态对照表。
  🟡 R0_scanner_blind_field 判据自己读不到某张图上的一个数据字段（见 `data_like_keys()`）。
       这一条与口径无关，是**判据的自体检**，与 `R0_page_unreadable` 同一族：
       「这页很干净」与「这页判据没看全」必须在退出通道上也分得开，不能只印一行。

R1/R2 只在口径**已确定**（回源复算命中）时才报 —— 判据自己拿不准就不喊。
图型豁免（`EXEMPT_KINDS`，§6.3）**只关掉 R4**，不再整条跳过规则循环 ——
从前它是无条件放行，把一张画滚动同比的 bridge_bar 放在任何一页上都静默通过。
R5 恰恰补的是那个「拿不准」：名单上的五张全是横截面图，回源对不齐、R1 一次都跑不到，
所以白名单曾经是彻头彻尾的死代码（2026-09 对抗普查抓出来的）。R5 判自述不判数，
弱，但它让「白名单被静默架空」变成会响的。

## 「看文字」的两类用法，界限在这里划清（新加规则的人先读这一段）

本文件的立身之本是**不看文字判口径**。但那句话管的是「这条线画的是哪种同比」，
不是「这张图有没有把该说的话说出来」。后者本身就是契约给页面派的**声明义务**
（§6.1 第 1 条要求单月写进标题、§6.2 要求页尾逐处点名、§6.1 第 5 条要求近零基数
必须让读者看得见），而义务履行没履行，除了读文字没有别的判法。所以：

  · **口径**（R1 / R2 / R7 的那一票，R3 的两侧）—— 一律回源复算或契约名单，
    不许拿文字作证；
  · **声明义务**（R3 的「点名」那一步、R4、R5、R8 的「点名近零月」那一步）——
    读文字，但读的是**被检查的那句话本身在不在**，不是拿它推断口径。

区别落到代码上有一条可操作的检验：把文字全删光，前一类的结论**一个字都不会变**，
后一类必然从「履行了」翻成「没履行」。R8 的构造刻意让这条检验成立 ——
「哪几个月是近零月」由 `yoy.near_zero_base()` 从数值算出来，文字只回答
「图注里有没有指着那几个月里的某一个说话」。

## 判据自己的两个盲区，2026-09 第二轮对抗普查补掉（都是「失明长得像干净」）

  · **序列名闸门**：图题写着 y/y，但只要序列**有名字**、名字里没有 y/y 字样，
    整张图就一条序列都不登记 —— 每一条规则都够不到，而 census 记成 `n_series=0`，
    与「这张图根本没有同比」在输出上一模一样。修法见 `yoy_series()` 的 docstring
    （放宽到什么程度是量出来的：加轴单位判别器 +10 条 0 误报，不加 +21 条 11 条误报）。
  · **R5 只对被扫到的页跑**：`data/exchanges12.js` 删掉或改名，R5 与 R1 一起失明，
    输出「🔴 0 🟡 0 / 无硬错，退出码 0」。修法见 `check_whitelist_pages()`。

### R1 为什么整条换了方向

上一版的 R1 是「未声明口径的**单月**同比，与滚动对应口径符号相反」—— 它成立的前提
是「滚动是默认、单月是需要辩护的偏离」。2026-09 页面所有者把默认翻成单月，那条规则
就变成了**对全站每一条线报警**，等于失效。新的 R1 判反方向：滚动线现在才是那个需要
被点名的偏离，而且它的合法位置只有 §6.2 那张名单上的几处。

⚠️ 换向丢掉的东西要说清楚：上一版 R1 顺带在盯「这条单月线毛刺大到与趋势反向」。
那件事没有不管，只是换了地方 —— §6.1 第 3 条要求**每张图自己**把符号相反的月份数
印进图注（由 `yoy.describe()` 现算）。判据这一侧不再把它**报成 finding**，否则全站
每张图都会响。`sign_flips()` 还留着，但只在「判据猜它是存量」那张诊断清单上印一个
月份数，供人排先看哪条 —— 是旁证，不是规则，不进 🔴/🟡。
"""
import argparse
import contextlib
import glob
import json
import os
import re
import sys
import tempfile

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, 'build'))
import yoy as Y  # noqa: E402  —— 共享实现，口径只有这一份
# `unit_is_ratio()`：「这个量纲配不配用百分点差表示变化」的白名单，R7 要用。
# **不抄一份到本文件**，理由与 `yoy` 逐字相同：这个判断在本仓只该有一份。
# 抄一份的后果是两份正则各自漂移，判据按一份报错、页面按另一份画图 —— 那正是
# §6.2 那张表与 `ROLLING_OK` 两份副本闹冲突时踩过的坑（本轮又踩了一次，见下）。
# 代价是判据从此依赖 `build/single.py` 能被 import；那是有意的：底座 import 不进去
# 的时候，判据报出来的东西本来也不该信。
import single as SG  # noqa: E402  —— 只取 unit_is_ratio()，见 R7
# 早绑一次：底座哪天把这个函数改名或挪走，判据在**启动时**就炸，报的是
# `AttributeError: module 'single' has no attribute 'unit_is_ratio'`。
# 不早绑的话它要等到某条序列真的走到 R7 才炸，而那时异常被 `scan_pages()` 的
# per-page try/except 接住，输出会变成「34 页同时读不出来」—— 一个假装成数据问题的
# 依赖问题，正是本文件最忌讳的那种误导性输出。
unit_is_ratio = SG.unit_is_ratio

# ── CONTRACT §6.2 的例外名单：保留滚动口径的几处 ──────────────────────────────
# 名单上的每一张都**不是折线**。两级要分开记（详见 CONTRACT §6.2 抬头）：
# `exchanges-apac` Ex5 与 `exchanges12` Ex4/7/8 是所有者改口径那一轮直接点名的；
# `exchanges-apac` Ex15 是由那个回答**推出来的**（它是 Ex5 那根柱的量价分解，
# 两侧与被分解的总量必须同口径），所以它是名单上最先该被重新审的一条。
# 写成 (页, exhibit 号) 的白名单而不是「凡是 grouped_bars / range_band 就放行」——
# 图型不是理由：同样是 grouped_bars，别的页画滚动同比仍然该报。
# 名单要跟着 CONTRACT §6.2 那张表走，改一处要改两处；漏改的后果是判据放行一张
# 不该放行的图（假阴性），所以宁可写窄。
#
# ⚠️ **「两个副本」这件事本轮当场翻过车，记在这里。** Ex15 那一行的行尾注释原来写着
# 「窗口逐字相同、**菱形就是那根柱**」，而 §6.2 那张表逐字写着「**菱形不等于 Ex5
# 那根柱**……别在别处写成『菱形就是那根柱』」—— 同一份名单的两个副本，在同一件事上
# 正面对立，而且判据这一份是漏网的第三处（`build/exchanges_apac.py` 那一份先改对了）。
# 复算过（2026-09-02 21:4x 的 `data/exchanges-apac.js`）：Ex5 最新那根柱（`groups[2]`
# 「Jul-26 止 12 个月 y/y」）与 Ex15 的 `net` 逐家相减，JPX / SGX / ASX 三家都不为零，
# HKEX 在 Ex15 上是空的（月度披露只有成交金额，拆不出量价）。差的不是窗口是**底料**：
# Ex15 为了让分子分母同口径换了更窄的列。**差多少不写在这里** —— 它随每月数据变，
# 由 Ex15 图注现算逐家列出（`build/exchanges_apac.py`），这里只说「不相等」。
ROLLING_OK = {
    ('exchanges-apac', 5),      # 三年连排的分组柱，「一整年 vs 前一整年」
    ('exchanges-apac', 15),     # Ex5 最新那根柱的量价分解桥：窗口逐字相同，但**菱形不等于那根柱**
    ('exchanges12', 4),         # 定基名义额的滚动合计同比 + 区间带
    ('exchanges12', 7),         # 张数 vs 名义额，两侧必须同口径
    ('exchanges12', 8),         # 张数 − 名义额的差值，同上
}


# ── 判据参数（每一个都有理由，见下）──────────────────────────────────────────

# 回源比对的**基础**容差（百分点）。payload 里的同比多数是 Python 侧算完直接
# json.dump 的原始浮点，理论上逐位相等；0.02pp 是留给浮点噪声与「round 到 3 位
# 以上再写」的余量。给大了会把无关列拉进候选 —— 同比是尺度无关的，两条形状相近的
# 序列很容易在 1pp 内互相冒充。**一刀切放大的代价跑 `--audit` 当场看**（它把这个
# 常数与下面那个上限一起设成 0.05 / 0.5 重扫，逐条比对判出的口径怎么变）。
#
# ⚠️ **这里原先举的例子是编的**（2026-09 对抗普查抓出来，留痕）：那句「一刀切提到
# 0.05，`tmx` Ex23 的成交股数会认到 `enx.csv:athex_mktcap_eurtn` 头上」复现不出来
# —— 0.02 / 0.05 / 0.5 三档下 `tmx` Ex23 一律命中 `tmx.csv:alphax_drk_volume_shares`
# （误差 ~5e-07、没有第二个候选），而 `athex_mktcap_eurtn` 在任何一档上都没当过
# 任何一条序列的最佳匹配。**没跑过的例子不许写**，这条规矩就是被它换来的。
#
# ⚠️ **2026-09 修一句关于它自己的假话。** 这里原本写的是「给 0.02pp 是留给『先
# round 再写』的少数生成器」—— 那句话不成立：本仓同比的展示精度是 `pct1`
# （一位小数），round 到一位小数的最大误差是 **0.05pp > 0.02pp**，0.02 的容差
# 根本接不住它，回源直接对不上。实测代价不是零：`tsm` Ex5 的
# 「NT$ revenue y/y (as reported)」整条写成一位小数（8.1 / 19.9 / 17.5 …），
# 与 `tsm.csv:revenue_ntd_mn` 的单月同比差 0.0495pp，一直判成「口径未确定」。
#
# 修法不是把常数调大（那会把上面那个巧合放进来），而是**按每条序列自己的刻度给
# 容差**：一条全部写成 k 位小数的序列，round-then-write 的误差上界就是
# 0.5×10⁻ᵏ，比这个还大的差就不是舍入造成的。见 `_write_quantum()` / `_tol_for()`。
MATCH_TOL_PP = 0.02

# 自适应容差的上限。k=1（一位小数）→ 0.05pp，正好接住本仓 `pct1` 的展示精度。
# 不让它再大：k=0（整数）时公式给 0.5pp，而 0.5pp 这个量级的容差会凭空造出巧合匹配
# —— 跑 `--audit`，它把两个常数一起设成 0.5 重扫，当场印出「新命中的列」与「从命中
# 退成歧义的条数」。整数刻度的同比序列因此仍然判不出口径 —— 这是**有理由的沉默**：
# 判据认不出它，而不是假装认出了。
#
# ⚠️ 这个上限**今天一条序列都没约束到**，说清楚免得被当成有代价的选择：能吃到这个
# 上限的只有写成整数刻度（k=0）的序列，`--audit` 第 ③ 段把它们逐条印出来 —— 今天
# 那几条要么本来就 err≈0 命中、要么本来就判不出，把上限单独提到 0.5 一条都不变。
# 它是**预防性**的：一刀切实验已经说明 0.5pp 会造出巧合候选，不该让哪条序列凭
# 「碰巧写成整数」拿到那么松的容差。
#
# ⚠️ 这里原先举的两个例子，一半是编的（2026-09 对抗普查，留痕）：「0.5pp 会让
# `enx` Ex20 的雅典 ADV 认到 `ice.csv:rpc_energy_usd`」复现不出来 —— 0.5 下 enx Ex20
# 仍然命中 `enx.csv:athex_adv_cash_adnv_eurbn`（误差 ~5e-07），只多出一个同文件的
# 候选列。另一半（`msci` Ex9 的 bp 差在 0.5 下认到 `fx.csv:fx_eom_cadusd`，误差 0.465）
# **逐字复现得出来**，所以「别一刀切调大」这个结论站得住，错的只是举错了例子。
MAX_ROUND_TOL_PP = 0.05

# 至少要有这么多个月同时有值才认一次**回源匹配**。
# 6 的理由：一条 13 个月的窗口里，随便两条无关序列在 ≤6 个点上偶然对齐到 0.02pp
# 的概率可以忽略；再少就开始出现巧合匹配。
#
# ⚠️ **降到 3 今天一条都不多认**（2026-09-02 21:5x 全站重跑：判出口径 285 条，
# 与门槛 6 时逐条相同、没有一条改判）。这不是「门槛没用」，是**它的作用面换了位置**：
# 会被这道门槛卡住的只剩横截面图（4 根柱、横轴是交易所名），而那种图 `lab2month()`
# 一个月份都认不出来 ⇒ `pairs` 恒为空 ⇒ 连 3 个点都凑不齐，降门槛救不了它们
# （救它们的是 R5，见 `check_whitelist()`）。所以这个常数今天是**预防性**的：
# 哪天有生成器写出一条只有四五个月的月度同比，它仍然拦着不让判据瞎猜。
# 这里原先写着「降到 3 匹配数只多 4 条、其中 3 条明显与图题无关」——
# 那是更早一次快照上的读数，今天复现不出来，所以换成上面这段现测的。
MIN_MATCH_PTS = 6

# ⚠️ **「登记一条序列」与「回源匹配得上」是两个门槛，2026-09 拆开。**
#
# 拆之前两处都用 `MIN_MATCH_PTS = 6`，后果是一个**静默的失明**：横截面图的序列长度
# 就是成员数 —— `exchanges-apac` Ex5 与 Ex15、`exchanges12` Ex7 与 Ex8 都只有 **4** 根柱，
# 于是 `yoy_series()` 在登记阶段就把它们整条丢掉，`check_payload` 的规则循环一次都
# 没在它们身上跑过。而这四张恰好正是 §6.2 白名单 `ROLLING_OK` 上的图 ——
# **白名单从来没有压制过任何一条 finding，它一直是死代码**；反过来说，这几张图哪天
# 被改成错的口径，R1 也不会响。「查过了没问题」与「根本没查」在输出上长得一模一样，
# 这正是本文件开头那句话说的情形，而它自己踩了进去。
# 同一道门槛也让 `data_like_keys()` 的失明清单一路报 0（两层护栏同时瞎）。
# 把登记门槛调回 6 今天会丢掉多少条序列 —— **跑 `--audit`**，它按 kind 分档印，
# 并顺带数出其中有几张在 §6.2 名单上（那正是「白名单是死代码」的成因）。
# （2026-09-02 21:5x 的读数是 40 条，全在 bridge_bar 与横截面 grouped_bars 上；
# 那是一次读数，会随 payload 变，所以引用前重跑，别把它当常量抄走。）
#
# 拆开之后：登记门槛降到 1（凡是 `{name, values}` 且签名像同比就登记，进 census、
# 进规则循环、进白名单判断），回源匹配仍然要 `MIN_MATCH_PTS` 个点 —— 点数不够时
# `identify()` 照旧回 `caliber=None`（判不出，不下结论），巧合匹配的风险一点没放大。
MIN_SERIES_PTS = 1

# 判「符号相反」时忽略贴着零的读数：±0.5pp 以内的正负不是方向分歧，是舍入。
# 0.5pp 的来处：本仓同比的展示精度是 `pct0`（整数百分点）与 `pct1`（一位小数），
# 前者的舍入半径就是 0.5pp —— 图上印出来根本区分不了的差别，不该报成方向相反。
SIGN_DEADBAND_PP = 0.5

# 图型豁免（CONTRACT.md §6.3）：格内 / 柱高本来就是单月读数，或者横轴根本不是月。
#
# ⚠️ **豁免的效力 2026-09 收窄了：它只关掉 R4，不再整条跳过规则循环。**
# 收窄之前这里是 `if exempt: continue`，也就是**无条件放行** —— 与 §6.2 末段那句
# 「同样是 bridge_bar，别的页若拿它画月度刻度的同比，仍然要改；同样是 grouped_bars，
# 别的页画滚动同比仍然报 🔴」正面冲突。实测把同一张画 12 个月滚动同比的假图放在
# sgx 页上：`kind='gs_bar'` → 🔴 R1；改成 bridge_bar / range_band / heat_matrix /
# seasonality / qtr_bar → 五种全部静默放行，输出里连一行都没有。
#
# 豁免的**本意**是「横轴不是月、回源无从对齐」，但那件事 `identify()` 自己就会办
# （对不齐就回 `caliber=None`，不下结论），不需要图型再包一层。所以现在：
#   · R1 / R2 照常跑 —— 它们本来就只在**回源确定命中 ttm** 时才报；
#   · R4（单月没写进标题）不适用 —— 这一类图的标题本来就不该念口径（§6.3）。
# 于是豁免图型上的沉默从此是「回源判不出，或判出来不是滚动」，
# 而不再是「压根没查」。这两件事从前在输出上长得一模一样，正是本文件反对的那种。
#
# 这次收窄新增的 🔴/🟡 是 **0 条**，而且那个 0 是**有理由的**：R1/R2 只对「回源确定
# 命中 ttm」那一档开口，而豁免图型上命中 ttm 的条数 —— 每次全站扫描的第五行现印
# （`豁免图型的 N 条里，回源确定命中滚动 X 条…`）。**看那一行，别在这里存一个副本。**
#
# 反过来「若当初连 R4 也一起放开会多出多少条 🟡」：**跑 `--audit`**，它把
# `EXEMPT_KINDS` 置空重扫一遍，按 rule / kind / 图张数分档印出来（分母与 CONTRACT
# §6.3 规定的重跑方法逐字相同：数多出来的 `R4_mom_not_in_title`，按 kind 分档）。
#
# ⚠️ **这里为什么一个数都不写了 —— 本轮的教训，值得记死。** 上一版这段先是写着
# 69/37/26/6（更早的快照），一次编辑把它订正成 68/36/26/6；可就在**同一次编辑**里，
# `values` 路径加了 `ratio_axis()` 闸门，`bridge_bar` 那 26 条随之归零 ——
# **订正了一个过期数，同一次编辑又让新数过期了**。两处副本（这里与 §6.3）逐个相同
# 也救不了：它们只是同一时刻的两份快照，下一次改动照样一起漂。
# 契约那一侧现在的规矩是「指向这份副本，不复述它」；这一侧的规矩是「不存副本，
# 现算」。合起来才是闭环：没有第二份数可抄，也就没有第二份数会过期。
EXEMPT_KINDS = {'heat_matrix', 'seasonality', 'qtr_bar', 'bridge_bar', 'range_band'}

# ── 结构性守卫：判据读得到哪些字段 ──────────────────────────────────────────
# 2026-08-07 修的那个盲区就死在这里：`yoy_series()` 只认六个字段，`grouped_bars`
# 的 `groups[]` 一个都没读过。整张图**静悄悄地**不进任何一条规则 —— 输出里既不报
# 违规，也不报「我没看」，看上去和「这页很干净」一模一样。
#
# 所以现在反过来做：不再维护「我会读哪些字段」，而是每张图逐字段问一句「你长得像
# 不像一条数据序列」，凡是像、而 `yoy_series()` 又没碰过的，**当成判据的缺陷报出来**。
# 下一次有人加一种 kind、带一个新字段名，判据会当场喊，而不是再瞎三个月。
_META_KEYS = {
    'n', 'kind', 'title', 'fmt', 'yfmt', 'label_fmt', 'ylab', 'ylab2', 'note',
    'src_extra', 'x', 'xlabels', 'xlabels_long', 'xstep', 'xrot', 'full', 'height',
    'legend', 'annot', 'zero_line', 'ycap', 'yfloor', 'cap_note', 'break_at',
    'break_label', 'bar_marks', 'mark_note', 'bar_labels', 'rows', 'cols', 'names',
    'row_head', 'row_lab_w', 'cell_h', 'reverse', 'highlight', 'avg12', 'avg_label',
    'yoy_txt', 'mom_txt', 'markers', 'zero_base', 'end_label', 'ovals_at_bottom',
    'net_color', 'actual_color', 'partial_months', 'qtr_months', 'qtd', 'qtd_at',
    'caliber', 'caliber_src', 'color',
}

# `yoy_series()` 声称自己读过的字段。两者对不上就是判据的盲区。
SCANNED_FIELDS = {'yoy', 'line', 'bar', 'series', 'stacks', 'values',
                  'groups', 'net', 'base', 'actual', 'lo', 'hi', 'matrix'}


def data_like_keys(ex):
    """这个 exhibit 上「长得像一条数据序列」的字段名（不看白名单，看形状）。

    三种形状算数：裸数值列表、`{'values': [...]}`、`[{'values': [...]}, ...]`；
    外加 `matrix` 的二维表。`xlabels` / `break_at` / `rows` 这些排版字段先按名字排除
    —— 它们也是列表，但不承载被判的量。
    """
    def numeric_list(v):
        return (isinstance(v, list) and len(v) >= MIN_SERIES_PTS
                and any(isinstance(x, (int, float)) and not isinstance(x, bool)
                        for x in v))

    out = set()
    for k, v in (ex or {}).items():
        if k in _META_KEYS:
            continue
        if numeric_list(v):
            out.add(k)
        elif isinstance(v, dict) and isinstance(v.get('values'), list):
            out.add(k)
        elif (isinstance(v, list) and v
              and all(isinstance(x, dict) and isinstance(x.get('values'), list)
                      for x in v)):
            out.add(k)
        elif isinstance(v, list) and v and all(isinstance(x, list) for x in v):
            out.add(k)                      # heat_matrix 的 matrix[][]
    return out

# ── 文字识别 ────────────────────────────────────────────────────────────────
# 「这条序列是不是同比」只看**结构位**（名字 / 轴标题 / 图题 / 图例 / 数值格式），
# 不看 note —— note 里提一句「同比」不代表这条线是同比，那样会把一堆水平值图
# 误判进来。note 只用来判「有没有声明口径」。
_IS_YOY = re.compile(r'y\s*/\s*y|yoy|同比|变化率|growth\s*%|% *chg', re.I)
_ROLL_DECL = re.compile(
    r'12\s*个月滚动|滚动合计|滚动同比|12M\s*滚动|\bTTM\b|12M\s*roll|'
    r'12[-\s]?month\s+rolling|rolling\s+12', re.I)
# ⚠️ 2026-09 收紧：「单月」必须**修饰同比**才算声明口径。
# 从前这里有一条裸的 `单月`，而 `declarations()` 是把 title / 序列名 / ylab2 /
# legend 拼成一整串再搜的 —— 于是标题里任何一个「单月成交额」「单月吞吐」「当月
# 单月合计」都能让 R4 闭嘴，哪怕那两个字修饰的是水平值、跟金线的口径毫无关系。
# R4 的全部用处是「让读者知道这条线是拿柱子直接除出来的」（§6.1 第 1 条），
# 一个修饰水平值的「单月」没有告诉读者这件事。
#
# 收紧的办法是**相邻性**：`单月` 与同比类词之间的空隙里不许有汉字（`_MOM_GAP`）。
# 本仓实际在用的写法全部照认 —— `单月同比`、`y/y (单月, RHS)`、`% y/y（单月）`、
# `y/y (pp, 单月, RHS)`、`单月口径`、`single-month y/y`（空隙是空格 / 括号 / 逗号
# / `pp`，都不是汉字）；被挡掉的是 `单月` 与同比之间隔着名词的那种。
# 实测（2026-09-02 全站快照）：收紧前后**没有一条**序列因此失去「标题写明单月」的
# 资格 —— 0 条新 🟡，纯粹是把洞堵上。`--selftest` 里那一对用例证明它真的会响。
_MOM_GAP = r'[^一-鿿]{0,10}'          # 空隙里不许夹汉字
_YOY_W = r'(?:同比|y\s*/\s*y|yoy|变化率|growth)'
_MOM_DECL = re.compile(
    r'单月同比|单月口径|单月[的]?[y／/]|single[-\s]?month|'
    rf'单月{_MOM_GAP}{_YOY_W}|{_YOY_W}{_MOM_GAP}单月|'
    # 描述式声明也算「声明过」—— 页面用大白话把口径说清楚了，只是没用契约的
    # 关键词。这类降级到 R4（标题里没写明），不进 R1（完全没线索）。
    r'同月对去年同月|当月对去年同月|与去年同月相比|水平值同比|点对点同比', re.I)

# 「滚动**合计**」与「滚动**均值**」在算术上给出同一个数（Σ12/Σ12′ ≡ 均值比，
# 除数约掉），但对存量只有后者是真话：12 个月末市值相加不指代任何真实的量。
# 所以 R2 判的是**措辞**，两个正则必须分开。
_ROLL_SUM_DECL = re.compile(r'滚动合计|合计的同比|rolling\s+sum|12\s*个月合计|TTM\s*sum', re.I)
_ROLL_MEAN_DECL = re.compile(r'滚动均值|滚动平均|rolling\s+(average|mean)|均值的同比', re.I)

# 「这张图画的是存量」的文字标记。本仓的图题已经在自报了（`（存量，期末口径）`、
# `Month-end total open interest`），所以这是**页面自己的声明**，不是我猜的。
# 用途有两个，方向相反：
#   · 存量 → R1（单月同比该不该报）整条豁免，因为点对点同比正是存量的合法口径；
#   · 存量 → R2（被做成滚动合计）加一道确认，避免只凭列名正则就下硬结论。
_STOCK_TXT = re.compile(
    r'存量|期末口径|月末|期末|未平仓|市值|托管资产|在外量|余额|'
    r'month-?end|end[-\s]?of[-\s]?period|open interest|outstanding|'
    r'market cap|assets under', re.I)

# ── R8 的「声明义务」那一票：图注里有没有指着近零月说话 ──────────────────────
# ⚠️ 这两个正则**不判口径**，判的是「这张图有没有履行 §6.1 第 5 条的告知义务」——
# 与 R3 的「点名」、R4 的「标题里有没有写单月」同类，界限见文件抬头那一段。
# 哪几个月是近零月由 `yoy.near_zero_base()` 从**数值**算出来，文字只回答
# 「有没有指着其中某一个月说话」，所以这里绝不会出现「文字说它不近零就当它不近零」。
_NEAR_ZERO_DECL = re.compile(
    r'近零基数|基数近零|基期近零|基期为零|基期为 ?0(?![\d.])|'
    r'基期(?:绝对值)?(?:很小|太小|接近零|贴着零|近于零)|'
    r'near[-\s]?zero(?:\s*base)?', re.I)
# 一个「月份标签长什么样」的粗筛。命中之后一律再过 `lab2month()`，真正定夺的是
# 那一步；这里宁可多筛几种写法（多筛的代价只是多调一次 lab2month）。
_MONTH_TOKEN = re.compile(
    r'[A-Za-z]{3}[-/. ]\d{2,4}|\d{2,4}[-/. ][A-Za-z]{3}|\d{4}[-/]\d{1,2}|\d{1,2}/\d{2,4}')
# 「同一句」的切法。R8 要求近零声明与被点名的月份落在**同一句**里，理由与 R3 的
# `named` 逐字相同：本仓图注是几百字一整段，跨句并起来等于「这段话里出现过一个月份」
# —— 而每张长历史图的图注里都印着「相邻月最大跳变 …pp（Mar-21 → Apr-21）」这种
# 月份，那句话讲的是跳变不是近零基数。实测（2026-09-02 的 `data/jpx.js` Ex14）：
# 它图注里印着「相邻月最大跳变 9245pp（Mar-21 → Apr-21）」，而 **Apr-21 正是
# `near_zero_base()` flag 出来的近零月**（还是 `worst` 那一个，基期 0.254 ¥bn）；
# Mar-21 不是。只按「这段话里出现过某个近零月」判，这张图会被当成已经声明过 ——
# 而它整段图注一个字都没提基期近零。所以「同一句」这条约束是承重的，不是洁癖。
_SENT_SPLIT = re.compile(r'[。；;!?！？\n]|<br\s*/?>')

# 列名本身就无歧义的存量前缀 —— 这几个不需要文字确认也能下 R2 的硬结论。
# 与「需要文字确认」的那些（accounts / listed_ / advisors / holdings）区别在于：
# 这些词在本仓 500+ 列里**没有一个**是流量，而 accounts 就有反例
# （`new_brokerage_accounts_k` 是当月新开户数，是流量）。
_STOCK_UNAMBIGUOUS = re.compile(
    r'(^|_)(oi|aum|auc|mktcap)(_|$)|open_interest|open_notional|'
    r'_balances?(_|$)|outstanding', re.I)


def _txt(*xs):
    return ' '.join(str(x) for x in xs if x)


# ── 轴的单位：这条序列画在「比率 / 百分点」轴上，还是画在水平值轴上 ──────────
# 这不是「口径证据」（口径只由回源复算判），是**登记时的判别器**：图题说了 y/y，
# 但图上哪几条序列才是那条 y/y 线？靠轴的单位分 —— `%` / `pp` / `pct0` 那一侧是
# 同比，`NT$bn` / `contracts/day` / `listings` 那一侧是水平值。
# 2026-09 加这一对正则，是为了同时修 `yoy_series()` 两个方向相反的毛病（见那里）。
_RATIO_FMT = re.compile(r'(pct|pp)\d[a-z]*', re.I)
_RATIO_LAB = re.compile(
    r'(^|[^A-Za-z])[%％]|(^|[^A-Za-z])(pp|bp|bps)([^A-Za-z]|$)|个百分点|'
    r'y\s*/\s*y|yoy|同比|percent', re.I)


def ratio_axis(series_fmt, ex_fmt, axis_lab):
    """这条序列所在的轴是不是比率 / 百分点单位。

    三个来源，任一命中即可：序列自己的 `yfmt`、**exhibit 级的 `yfmt`**（不少页把
    `yfmt='pct0'` 写在图上而不是序列上 —— 那是主轴的缺省格式，是一条强信号，
    2026-09 之前 `yoy_series()` 一次都没读过它）、以及该轴的轴标题。

    ⚠️ `ex_fmt` 只对**主轴**序列有意义（它就是主轴的缺省格式），所以次轴那几路
    （`yoy`、以及 `ylab2` 非空时的 `line`）传 None —— 拿主轴的格式去给次轴作证
    是一句关于别人的话。
    """
    for f in (series_fmt, ex_fmt):
        if f and _RATIO_FMT.fullmatch(str(f).strip()):
            return True
    return bool(axis_lab and _RATIO_LAB.search(str(axis_lab)))


# ── 月份标签 ────────────────────────────────────────────────────────────────
_MON = {m: i + 1 for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])}


def lab2month(s):
    """月份标签 → `'2026-07'`；认不出就 None。

    认这几种：`Jul-26` / `Jul 26` / `Jul-2026` / `26-Jul` / `7/26` / `07/2026` /
    `2026-07` / `2026/07`。

    ⚠️ **认不出的代价是整张图静默退出判据**，所以这里宁可多认几种写法：
    `page_months()` 认不出月份 → `identify()` 的 pairs 为空 → `caliber=None` →
    R1/R2/R3 全部够不到，而输出上与「这张图的口径判不出来」一模一样。
    2026-09 之前只认前三种里的 `Jul-26` / `7/26` / `2026-07`，换成带空格的
    `Jul 26`、`2026/07`、`26-Jul` 一律回 None —— 那不是「有理由的沉默」，
    是等着下一个生成器换个分隔符就整页失明。

    多认写法**不放大误配风险**：这些都是无歧义的月份写法，认错一个月份只会让回源
    对不齐（→ 判不出），不会造出假的命中。真正拦着巧合匹配的是 `MIN_MATCH_PTS`
    与 `MATCH_TOL_PP`，不是这里认得少。

    仍然不认（本来就不该进这个判据）：季度标签 `2023Q1` / `3Q20`、seasonality 的
    裸月名 `Jan`、横截面的公司名。也不认 `26-07` 这种两头都是数字的 ——
    到底是「2026 年 7 月」还是「26 日 7 月」没法判，猜错就是错位对齐。
    """
    s = str(s).strip()
    # Jul-26 / Jul 26 / Jul.26 / Jul-2026
    m = re.fullmatch(r'([A-Za-z]{3})[-/. ](\d{2}|\d{4})', s)
    if m and m.group(1).title() in _MON:
        y = m.group(2)
        return f'{y if len(y) == 4 else "20" + y}-{_MON[m.group(1).title()]:02d}'
    # 26-Jul / 2026-Jul（年在前的倒装）
    m = re.fullmatch(r'(\d{2}|\d{4})[-/. ]([A-Za-z]{3})', s)
    if m and m.group(2).title() in _MON:
        y = m.group(1)
        return f'{y if len(y) == 4 else "20" + y}-{_MON[m.group(2).title()]:02d}'
    # 7/26 —— 月在前、两位年在后
    m = re.fullmatch(r'(\d{1,2})/(\d{2})', s)
    if m and 1 <= int(m.group(1)) <= 12:
        return f'20{m.group(2)}-{int(m.group(1)):02d}'
    # 07/2026 —— 月在前、四位年在后
    m = re.fullmatch(r'(\d{1,2})/(\d{4})', s)
    if m and 1 <= int(m.group(1)) <= 12:
        return f'{m.group(2)}-{int(m.group(1)):02d}'
    # 2026-07 / 2026/07 —— 年在前
    m = re.fullmatch(r'(\d{4})[-/](\d{2})', s)
    if m and 1 <= int(m.group(2)) <= 12:
        return f'{m.group(1)}-{m.group(2)}'
    return None


# ── 回源：把 series/*.csv 每一列的两种口径预算一遍 ────────────────────────────
def build_index(root):
    """{(csv, col): {'kind', 'mom', 'ttm', 'mompp', 'lvl'}}。耗时 <1s
    （2026-09-02 加了 `lvl` 那一档之后复测 0.6s；这个数随 `series/` 长，别抄走）。

    进索引的列数**不写在这里** —— 它随数据源增减，而报告抬头每次都现印一行
    「回源索引：N 列」。（这里原先写着「约 580 列」，2026-09-02 21:5x 复算是 778 列，
    那种数写进注释就只会烂在里面。）

    `ttm` 走 `yoy.ttm_yoy_unchecked` —— 对**存量列也算**。这不是违反口径规矩，
    恰恰相反：只有把存量列的滚动同比也算出来，才能判断「有没有人把存量做成了
    滚动合计」（R2 要报的就是这个）。

    `lvl` 是**水平值原列**本身（不是同比）。它只有一个用途：R8 要拿
    `yoy.near_zero_base()` 判「这条线的分母有几个月贴着零」，而那个判据吃的是
    水平值，从三张同比矩阵里反推不出来。存在这里而不是用到时再读一次 CSV，
    是为了让「回源命中的是哪一列」与「拿哪一列去判近零」**必然是同一列** ——
    分头读两次就会在「重复月怎么去重、缺值怎么补」上悄悄分叉。
    """
    keys, meta, frames = [], {}, {'mom': [], 'ttm': [], 'mompp': [], 'lvl': []}
    for f in sorted(glob.glob(os.path.join(root, 'series', '*.csv'))):
        try:
            head = open(f, encoding='utf-8').readline().strip().split(',')
            if 'month' not in head:
                continue
            df = pd.read_csv(f)
        except Exception:
            continue
        df = df.set_index('month').sort_index()
        df = df[~df.index.duplicated(keep='last')]
        for c in df.columns:
            s = pd.to_numeric(df[c], errors='coerce')
            if np.isfinite(s.values.astype(float)).sum() < 15:
                continue
            k = (os.path.basename(f), c)
            keys.append(k)
            # `classify()` 的最后一行是 `return STOCK  # 拿不准判存量`。对生成器那是
            # 安全的默认（少画一条线），但在**判据**里方向正好相反：kind==STOCK 会让
            # legal_mom 成立，把 R1/R4 整条关掉 —— 一个「我不知道」被当成了「它合法」。
            # 所以这里记下这次分类到底是**正则命中**还是**兜底猜的**，好把后者单列出来。
            classified = bool(Y._RATIO_PAT.search(c) or Y._NEW_FLOW_PAT.search(c)
                              or Y._STOCK_PAT.search(c) or Y._FLOW_PAT.search(c))
            meta[k] = {'kind': Y.classify(c),
                       'kind_fallback': not classified,
                       'strong_stock': bool(Y._STOCK_PAT.search(c))
                                       and not Y._NEW_FLOW_PAT.search(c),
                       'unambiguous_stock': bool(_STOCK_UNAMBIGUOUS.search(c))}
            frames['mom'].append(Y.mom_yoy(s, Y.FLOW).rename(k))
            frames['ttm'].append(Y.ttm_yoy_unchecked(s).rename(k))
            frames['mompp'].append(Y.mom_yoy(s, Y.RATIO).rename(k))
            frames['lvl'].append(s.rename(k))          # 水平值原列，R8 用
    # 一次性拼成三张宽表（月 × 列）。identify() 因此只需一次 reindex + 一次
    # 向量化比对，而不是「239 条 × 580 列 × 3 口径」次 pandas 调用 —— 15s → <1s。
    return {'keys': keys, 'meta': meta,
            'mat': {k: pd.concat(v, axis=1).sort_index() for k, v in frames.items()}}


def _write_quantum(vals):
    """这批数写进 payload 时的最小小数刻度 k（全部满足 `v == round(v, k)` 的最小 k）。

    判不出（超过 6 位，即多半是原始浮点）→ None。这不看文字、不看 `yfmt` 声明，
    只看数字自己 —— `yfmt` 是展示格式，说的是「怎么印」，不是「怎么存」。
    """
    vs = [float(v) for v in vals
          if isinstance(v, (int, float)) and not isinstance(v, bool)
          and v is not None and np.isfinite(float(v))]
    if not vs:
        return None
    for k in range(0, 7):
        if all(abs(v - round(v, k)) < 1e-9 for v in vs):
            return k
    return None


def _tol_for(values):
    """这条序列该用多大的回源容差（百分点）。

    基础是 `MATCH_TOL_PP`；若这条序列整条都写成 k 位小数，说明生成器是「先 round
    再写」，其误差上界为 0.5×10⁻ᵏ，容差放宽到那个上界（封顶 `MAX_ROUND_TOL_PP`）。
    只对**这一条**序列放宽，不动全局 —— 这正是一刀切调大常数与本做法的区别：
    全精度写出来的序列一律仍按 0.02pp 比，巧合匹配的风险一点没放大。

    实测（2026-09-02 21:5x 全站快照，分母 = 回源判出口径的 285 条）：把上限从 0.02
    放宽到 0.05 只多认出 **1 条**，就是上面注释里那条 `tsm` Ex5，认到它自己那一页的
    `tsm.csv:revenue_ntd_mn`（误差 0.0495pp）；**0 条改判**、**0 条新增歧义**
    （逐条比对 `match.ambiguous`，没有一条从 False 翻成 True）。
    这三个数随快照变，重跑方法就是把 `MAX_ROUND_TOL_PP` 设成 0.02 再扫一遍对比。
    """
    k = _write_quantum(values)
    if k is None:
        return MATCH_TOL_PP
    return max(MATCH_TOL_PP, min(MAX_ROUND_TOL_PP, 0.5 * 10 ** (-k)))


def identify(values, months, idx):
    """拿图上的同比数值回源复算，判它是哪种口径。

    返回 {'caliber': 'mom'|'ttm'|None, 'col', 'csv', 'kind', 'err', 'n',
          'ambiguous': bool, 'alts': [...]}。
    caliber=None 表示**没判出来**（派生量、跨源合成、或历史太短）—— 不报错。
    """
    pairs = [(m, float(v)) for m, v in zip(months, values)
             if m and v is not None and isinstance(v, (int, float))
             and np.isfinite(float(v))]
    out = {'caliber': None, 'col': None, 'csv': None, 'kind': None, 'err': None,
           'n': len(pairs), 'ambiguous': False, 'strong_stock': False,
           'unambiguous_stock': False, 'kind_fallback': False, 'tol': MATCH_TOL_PP,
           'alts': []}
    if len(pairs) < MIN_MATCH_PTS:
        return out
    ms = [m for m, _ in pairs]
    want = np.array([v for _, v in pairs])[:, None]
    # 容差按**这条序列自己**的书写刻度定，不吃全局常数（见 `_tol_for()`）
    tol = _tol_for([v for _, v in pairs])
    out['tol'] = tol

    hits = []
    for cal, key in (('mom', 'mom'), ('ttm', 'ttm'), ('mom', 'mompp')):
        got = idx['mat'][key].reindex(ms).values.astype(float)
        # 只在「窗口内每个月都有值」的列上比 —— 缺一个月就没法确认口径，
        # 拿 nanmax 去凑会把一条只重叠 2 个月的列当成命中。
        ok = np.isfinite(got).all(axis=0)
        err = np.full(got.shape[1], np.inf)
        if ok.any():
            err[ok] = np.abs(got[:, ok] - want).max(axis=0)
        for j in np.flatnonzero(err <= tol):
            hits.append((float(err[j]), cal, idx['keys'][j], key == 'mompp'))
    if not hits:
        return out
    hits.sort(key=lambda t: t[0])
    err, cal, k, is_pp = hits[0]
    cals = {h[1] for h in hits}
    out.update(caliber=cal, csv=k[0], col=k[1], err=err, pp=is_pp, **idx['meta'][k],
               # 同一条同比可能同时命中多列（同比是尺度无关的，一列和它的换算列
               # 读数完全一样）。只要命中的**口径**唯一，就不算歧义 —— 我们要判的
               # 是口径不是列名。口径都不唯一才是真拿不准，那就不下结论。
               ambiguous=len(cals) > 1)
    out['alts'] = sorted({(h[2][0], h[2][1], h[1]) for h in hits[:8]})
    if len(cals) > 1:
        out['caliber'] = None
    return out


# ── payload 遍历 ────────────────────────────────────────────────────────────
def load_page(path):
    s = open(path, encoding='utf-8').read()
    i = s.index('window.DASH =')
    j = s.rindex(';')
    return json.loads(s[i + len('window.DASH ='):j])


def page_months(payload, ex):
    """这张图的 x 轴月份。优先图自己的 xlabels，其次按 `x` 字段取页级标签。"""
    xl = ex.get('xlabels') or (payload.get('xlabels_long') if ex.get('x') == 'long'
                               else payload.get('xlabels')) or []
    return [lab2month(x) for x in xl]


def heat_series(ex):
    """`heat_matrix` 的 `matrix[][]` 摊平成「序列 + 它自己的月份轴」。

    两种排版都在用，必须分开处理 —— 认错一种就会把值和月份错位对齐：

      A. **列是月标签**（`cols=['Jul-24', …]`，行是不同标的，如 exchanges-eu Ex13）
         → 一行一条序列，月份取自 `cols`。
      B. **行是年、列是月名**（`rows=['2017', …]`, `cols=['Jan', …]`，如 cme Ex18）
         → 整张矩阵在日历上本来就是一条连续序列，摊平成一条（最多 120 个点，
            比逐行 12 个点更容易在回源里认出口径）。

    两种都不是（季度矩阵 exchanges-apac Ex7 的 `cols=['3Q20', …]`）→ 返回空。
    这是**真的读不出月份**，与「没写代码去读」是两件事，census 里分开记。
    """
    mat = ex.get('matrix')
    if not isinstance(mat, list) or not mat:
        return []
    rows = ex.get('rows') or []
    cols = ex.get('cols') or list(_MON)          # 缺省 Jan..Dec（hkex Ex17 就没给）

    col_m = [lab2month(c) for c in cols]
    if any(col_m):                                # 排版 A
        out = []
        for i, r in enumerate(mat):
            if isinstance(r, list) and len(r) >= MIN_MATCH_PTS:
                nm = str(rows[i]) if i < len(rows) else f'row{i}'
                out.append((nm, list(r), col_m))
        return out

    idx = [_MON.get(str(c).strip()[:3].title()) for c in cols]   # 排版 B
    if not cols or not all(idx):
        return []
    flat_m, flat_v = [], []
    for i, r in enumerate(mat):
        y = str(rows[i]).strip() if i < len(rows) else ''
        if not re.fullmatch(r'\d{4}', y) or not isinstance(r, list):
            return []
        for j, v in enumerate(r[:len(idx)]):
            flat_m.append(f'{y}-{idx[j]:02d}')
            flat_v.append(v)
    return [(str(ex.get('legend') or ''), flat_v, flat_m)] if len(flat_v) >= MIN_MATCH_PTS else []


def yoy_series(ex):
    """从一个 exhibit 里挑出「画的是同比」的那些序列。

    只认结构位上的证据（序列名 / 该序列所在轴的轴标题 / 图题 / 图例 / yfmt），
    因为「有没有在文字里声明口径」是被检查项，不能拿来当识别依据。

    返回的每条可带 `months` —— 该序列**自己的**月份轴（目前只有 `heat_matrix` 需要，
    它不吃 `xlabels`，月份藏在 `rows`×`cols` 里）。不给就用页/图的 `xlabels`。

    ── 2026-09 第三轮修：图题在**有序列名**时也作数，判别器换成轴的单位 ─────────

    从前的登记条件是 `_IS_YOY.search(sig) or (not nm and _IS_YOY.search(title…))` ——
    `not nm` 那一半意味着**只要序列有名字，图题就永远够不到**。后果是一整张图静默
    退出全部规则，而 census 把它记成 `n_series=0`，与「这张图根本没有同比」在
    输出上一模一样 —— 正是本文件开头反对的那种失明，它自己踩了进去。
    实测（2026-09-02 快照）：`data/cost.js` 的头条图与四张分地区 / 电商 comp 图都是 `bar_line`，
    图题写着 `…, y/y`、`yfmt='pct0'` 写在 **exhibit 级**，而两条序列都有名字
    （`'Reported Comp'` / `'Core Comp (ex. gas & FX)'`）—— 十条真同比序列一条都没登记。

    反方向的同一个毛病在下面 `values` 那条兜底路径上：它只看图题、不看轴，于是
    `gs_bar` 的**水平值柱**被图题里那句「次轴：单月同比」一路登记成同比序列。
    实测这条路径登记 85 条，其中 **81 条是水平值**（2026-09-02 复算逐字相同：
    85 / 81 / 4；`ylab` 是 `NT$bn` /
    `contracts/day` / `listings` 之类，回源同比口径 **81 条全是 `None`**）。

    两个毛病同一个根因：**图题只说明「这张图上有同比」，没说明「哪几条序列是」。**
    所以补的不是「放开图题」，是补一个判别器 —— `ratio_axis()`，看这条序列所在的
    轴是不是 % / pp 单位。图题说了 y/y **且**这条序列画在比率轴上 → 登记。

    ── 放宽到这个程度是量出来的，不是拍的 ───────────────────────────────────

    ⚠️ **分母先说清楚**：下表三行的「新登记」都是**相对修改前那一版**（`not nm` 那个
    条件还在的那一版）数的，不是相对上一行。三行都是 2026-09-02 21:5x 在同一份
    `data/` 快照上跑出来的读数 —— 换一份快照就会变，别当常量抄走。
    （第三行原先写的是 +214，两个分母都对不上：相对修改前是 +234，相对采用档是
    +224。一个没写分母的数，读的人只能猜它在数什么 —— 这正是 §6.5 那条通用教训。）

    | 方案 | 新登记（vs 修改前） | 其中轴是水平值单位的 | 回源确认是同比的 |
    |---|---|---|---|
    | 只删 `not nm`、不加判别器 | +21 | **11**（52%）| 0 |
    | **删 `not nm` + `ratio_axis()` 判别器（采用）** | **+10** | **0** | 0 |
    | 再放开一档：连图题都不要，只要轴是比率单位 | +234（= 采用档再 +224）| — | **0** |

    多出来的那 11 条一条不落全是主轴水平值，单位写在轴标题或序列名里：
    `ase` Ex2 / `guc` Ex2 的 `stacks`（`ylab='NT$bn'` / `'NT$mn'`）、`axp` Ex12 的
    `bar`（`'$bn'`）与 `cost` Ex4 的 `bar`（`ylab` 为空，单位在序列名
    `'Net sales ($bn, LHS)'` 里）、`exchanges-eu` Ex16 的 `bar`（`'百万笔/月（当月
    合计）'`）、`lseg` Ex18 / Ex23 的 `series`（`'issues/month'` / `'USD bn/day'`）。
    判别器把这 11 条全部挡掉，而**一条真同比都没挡掉**（+10 条与不加判别器时是同一批）。
    所以取判别器这一档：放宽的收益一分不少，误报是 0 而不是 52%。

    **为什么不再往下放一档**（「图题都不要，凡是比率轴就算同比」）：实测在采用档上
    **再多登记 224 条**，回源确认是同比的 **0 条** —— 全是比率的**水平值**（`axp` 的
    逾期率 / 核销率 / 组合收益率、`ase` Ex5 的营收占比堆叠…），轴是 `%` 但画的不是同比。
    那一档买不到任何规则覆盖，只买到两百多行 census 噪声。本仓的规矩是宁可漏报不
    制造噪声，所以停在「图题说了同比 **且** 轴是比率单位」这里：图题负责说明
    「这张图上有同比」，轴单位负责说明「是哪几条」，**两个条件各管一半，缺一不可**。

    ⚠️ 新登记的 10 条回源口径全是 `None`（cost 的 comp 是公司自己披露的百分数，
    `series/cost.csv` 里没有可以除出它的水平列）—— 也就是说**今天它们一条 finding
    都不会产生**。那不是白改：census 从「n_series=0，这张图没有同比」变成
    「n_series=2，有同比但口径判不出」，前者是结构性失明，后者是有理由的沉默；
    而且 R1 从此**够得到**这几张图 —— 哪天有人把 cost 的线换成某条能回源的滚动口径，
    它会当场响。`--selftest` 里 `R1…[cost 形状]` 那一对用例证明的就是这件事。

    ⚠️ 判别器认的是**单位**，不是口径。`% of UK lit order book`、`bp of average
    ETF AUM` 这种「比率的水平值」也会被它放行（实测 `values` 路径上留下的 4 条正是
    这种）。那是有意的：判据分不出「比率水平值」与「百分点差同比」靠轴标题 ——
    分它们要靠回源，而回源本来就会跑。登记一条判不出口径的序列，代价只是 census
    多一行「未确定」；漏登记一条真同比，代价是整条规则链够不到它。
    """
    title, ylab, ylab2 = ex.get('title', ''), ex.get('ylab', ''), ex.get('ylab2', '')
    ex_fmt = ex.get('yfmt')                  # 主轴的缺省格式，只给主轴那几路作证
    found = []

    def take(obj, where, axis_lab, name_hint=None, months=None, force=False,
             ax_fmt=None):
        # 裸列表形态（range_band 的 lo/hi/actual 是 `[…]` 而不是 `{values: […]}`）
        if isinstance(obj, list):
            obj = {'values': obj}
        if not isinstance(obj, dict):
            return
        vals = obj.get('values')
        # 登记门槛 = MIN_SERIES_PTS（1），不是回源匹配门槛 —— 见 MIN_SERIES_PTS 上方
        # 那段：用匹配门槛登记会把 4 根柱的横截面图整条丢掉，而白名单正管着那几张。
        if not isinstance(vals, list) or len(vals) < MIN_SERIES_PTS:
            return
        nm = obj.get('name') or name_hint or ''
        sig = _txt(nm, obj.get('legend'), axis_lab, obj.get('yfmt'))
        # 次轴序列（yoy / line）默认继承 ylab2；只有主轴序列才需要图题来判定。
        # force=True 只给 heat_matrix 用：那种图的口径写在图级签名上，行标签是标的名
        # （'Euronext'）或年份（'2017'），拿行标签去搜「同比」永远搜不到。
        #
        # 图题兜底两条路（见 docstring 的表）：
        #   · 序列没名字 → 照旧只看图题（保持原行为，不动）；
        #   · 序列有名字 → 图题说了 y/y **且** 这条序列画在比率 / 百分点轴上。
        if force or _IS_YOY.search(sig) or (
                _IS_YOY.search(_txt(title, axis_lab))
                and (not nm or ratio_axis(obj.get('yfmt'), ax_fmt, axis_lab))):
            found.append({'where': where, 'name': nm or ex.get('legend') or '',
                          'values': vals, 'yfmt': obj.get('yfmt'), 'months': months})

    # `ax_fmt` = 这条序列所在轴的缺省格式。次轴（yoy / ylab2 非空时的 line）传
    # None —— exhibit 级 `yfmt` 说的是主轴，拿它给次轴作证是一句关于别人的话。
    take(ex.get('yoy'), 'yoy', ylab2)                    # gs_bar 的次轴金线
    take(ex.get('line'), 'line', ylab2 or ylab,          # bar_line_dual / stacked_dual / grouped_bars 的误差线
         ax_fmt=None if ylab2 else ex_fmt)               # ylab2 为空时 line 在主轴上
    take(ex.get('bar'), 'bar', ylab, ax_fmt=ex_fmt)
    for i, s in enumerate(ex.get('series') or []):
        take(s, f'series[{i}]', ylab, ax_fmt=ex_fmt)
    for i, s in enumerate(ex.get('stacks') or []):
        take(s, f'stacks[{i}]', ylab, ax_fmt=ex_fmt)

    # ── 以下五类曾经一条都没读过（2026-08-07 补）────────────────────────────
    # grouped_bars 的并排柱。**这一类不在豁免名单里**，所以补上之后是真的会进
    # R1/R3/R4 —— 全站 38 张 grouped_bars 里有一批标题就写着「：同比」。
    for i, g in enumerate(ex.get('groups') or []):
        take(g, f'groups[{i}]', ylab, ax_fmt=ex_fmt)

    take(ex.get('net'), 'net', ylab, ax_fmt=ex_fmt)      # bridge_bar 的净额菱形
    take(ex.get('base'), 'base', ylab, ax_fmt=ex_fmt)    # seasonality 的同月常态灰柱
    take(ex.get('actual'), 'actual', ylab, ax_fmt=ex_fmt,  # seasonality 蓝柱 / range_band 菱形
         name_hint=(ex.get('names') or {}).get('actual'))
    for f in ('lo', 'hi'):                               # range_band 的区间上下缘
        take(ex.get(f), f, ylab, ax_fmt=ex_fmt,
             name_hint=(ex.get('names') or {}).get(f))

    # heat_matrix：一整张图只有一个口径，语义写在图题/图例上而不是行标签上
    # （行标签是标的名 'Euronext'、或年份 '2017'），所以这里查的是**图级**签名。
    if _IS_YOY.search(_txt(ex.get('legend'), title, ylab)):
        for nm, vals, mm in heat_series(ex):
            take({'name': nm, 'values': vals}, 'matrix', ylab,
                 name_hint=nm or ex.get('legend'), months=mm, force=True)

    # `values`：图级的那一条裸序列（`gs_bar` 的主轴柱就走这里）。
    # ⚠️ 这条路径同样要过 `ratio_axis()` —— 它是 ① 那个毛病的**反面**：只看图题不看轴，
    # 于是 `gs_bar` 标题里那句「（次轴：单月同比）」把**主轴的水平值柱**登记成了同比。
    # 实测挡掉 81 条（`ylab` 是 `NT$bn` / `contracts/day` / `listings` / `$bn` 之类），
    # 留下 4 条（`% annualised`、`% of UK lit order book`、`bp of average ETF AUM`
    # 这种比率轴）。**一条 finding 都不会丢**：这 81 条回源口径全是 `None`
    # （水平值当然匹配不上任何一条同比），R1/R2/R4 本来就没在它们身上响过，
    # 它们只在 census 里冒充同比。
    #
    # ⚠️ 这里原先还挂着一句「其中 24 条能逐点匹配上 `series/*.csv` 的原始水平列」——
    # **删掉了，因为它没有判据、取不到那个数**：把 payload 上的数直接与原始水平列
    # 逐点比，81 条里能匹配上的条数完全取决于比对阈值（2026-09-02 21:5x 实测，
    # 相对误差 ≤1e-9 / ≤1e-6 / ≤1e-4 三档分别是 18 / 26 / 27 条），24 在任何一档上
    # 都取不到。一个不写分母、不写阈值的子计数没法被复核，正是 §6.5 那条通用教训要防
    # 的形状 —— 而上面那句「回源口径全是 None」是承重的那句，它的判据就是 `identify()`。
    if isinstance(ex.get('values'), list) \
            and _IS_YOY.search(_txt(title, ylab, ex.get('legend'))) \
            and ratio_axis(None, ex_fmt, ylab):
        found.append({'where': 'values', 'name': ex.get('legend') or '',
                      'values': ex['values'], 'yfmt': ex.get('yfmt'), 'months': None})
    return found


def declarations(ex, s):
    """这条同比在文字里声明了什么口径。分「标题里」与「任意位置」两级 ——
    CONTRACT.md §6 要求单月口径写进**标题**，图注补理由。"""
    title = _txt(ex.get('title'), s['name'], ex.get('ylab2'), ex.get('legend'))
    body = _txt(title, ex.get('note'), ex.get('src_extra'), ex.get('ylab'), ex.get('annot'))
    return {
        'roll_in_title': bool(_ROLL_DECL.search(title)),
        'mom_in_title': bool(_MOM_DECL.search(title)),
        'roll_anywhere': bool(_ROLL_DECL.search(body)),
        'mom_anywhere': bool(_MOM_DECL.search(body)),
        'sum_wording': bool(_ROLL_SUM_DECL.search(body)),
        'mean_wording': bool(_ROLL_MEAN_DECL.search(body)),
    }


# ── 规则 ────────────────────────────────────────────────────────────────────
def check_page(path, idx):
    return check_payload(load_page(path), os.path.basename(path)[:-3], idx)


def check_payload(payload, page, idx):
    findings, items, census = [], [], []

    for ex in payload.get('exhibits') or []:
        n, kind_, title = ex.get('n'), ex.get('kind'), ex.get('title', '')
        months = page_months(payload, ex)
        exempt = kind_ in EXEMPT_KINDS
        # 这张图是不是存量图 —— 用**页面自己写的**标记判，不是靠列名正则猜
        says_stock = bool(_STOCK_TXT.search(_txt(title, ex.get('ylab'), ex.get('legend'))))

        found = yoy_series(ex)
        # 逐张图记账，**与「找到几条同比序列」无关**。老版本只在找到序列时才记，
        # 于是「豁免图型 N 条」统计的是「豁免图里被读到的序列数」而不是豁免图数量；
        # 一张图一条都没读到时，它在输出里彻底不存在 —— 失明长得和干净一模一样。
        blind_keys = sorted(data_like_keys(ex) - SCANNED_FIELDS)
        census.append({'page': page, 'n': n, 'kind': kind_, 'title': title,
                       'exempt': exempt, 'n_series': len(found),
                       'blind': blind_keys})
        # ── 失明清单从「只印一行」升成 🟡（2026-09）—— 理由与代价都写在这里 ────
        #
        # **升级的理由**：这个装置的全部意义是「让失明能被看见」，而它从前只进
        # `print`、不进 `findings`、不改退出码 —— 比 🟡 还弱一档。后果是：判据漏读
        # 一个字段（= 一整张图的某条序列从来没进过任何一条规则）与「这一页很干净」
        # 在**退出通道上**长得一模一样，只在一段谁也不读的日志中段差一行。
        # 那正是本文件反复在防的形状，而这个反失明装置自己踩了进去。
        #
        # **为什么是 🟡 而不是 🔴**：按 CONTRACT §6.6 给 🔴 定的两条门槛
        # （不会误报 + 别的规则接不住），第二条成立、第一条不成立 ——
        # `data_like_keys()` 是**形状**判断，谁往 payload 上加一个新的排版字段
        # （只要它是个数值列表、又还没进 `_META_KEYS`）就会命中一次，而那不是失明，
        # 是没登记。误报的修法是往 `_META_KEYS` 里加一行，代价一分钟；
        # 停机的代价是整轮构建打红。会误报的规则不该有停机权，所以 🟡。
        #
        # **升级之后仍然剩着的那层失明，说清楚**：`data_like_keys()` 认的是四种
        # 形状（裸数值列表 / `{'values': [...]}` / `[{'values': [...]}]` / 二维表）。
        # 换一种容器就认不出 —— 比如 `{'v': [...]}`、或者 `{'a': [...], 'b': [...]}`
        # 这种「字典里挂着几条列」。**这一层没有在本轮扩**：放宽形状会把
        # 一大批配置字典也判成数据序列，用噪声换一个今天并不存在的召回
        # （2026-09-02 全站快照上 `blind` 是空的 —— 那是**今天**的读数，不是「永远为空」）。
        # 要扩的人先量误报率再动，
        # 别顺手放宽 —— 这个装置的价值全在「它响的时候必定是真的漏读」。
        if blind_keys:
            findings.append(dict(
                lvl='🟡', rule='R0_scanner_blind_field', page=page, n=n, title=title,
                msg=(f'这张图上有 `{blind_keys}` 这样长得像数据序列、而 '
                     f'`yoy_series()` **一次都没读过**的字段（kind={kind_}）。'
                     f'**这是判据自己的缺陷，不是页面的问题**：那些字段里若有一条'
                     f'同比，R1–R8 一条都够不到它，而输出会和「这张图没有同比」'
                     f'一模一样。两种改法 —— 它确实承载一条序列：把字段名加进 '
                     f'`SCANNED_FIELDS` 并在 `yoy_series()` 里 `take()` 一次；'
                     f'它只是排版参数：把字段名加进 `_META_KEYS`。'
                     f'两种都要改，别只改一处就当它没了。')))

        for s in found:
            d = declarations(ex, s)
            # heat_matrix 的月份藏在 rows×cols 里，不在 xlabels 上，所以序列可自带月份轴
            ms = s.get('months') or months
            m = identify(s['values'], ms, idx)
            is_stock = says_stock or m['kind'] == Y.STOCK or m['unambiguous_stock']
            is_ratio = m['kind'] == Y.RATIO or m.get('pp')
            # 「单月是这条序列唯一合法的口径」—— 存量（点对点）与比率（百分点差）。
            # 对这两类报「你怎么不用滚动」是把规矩用反了，R4 一律豁免（R1/R2/R7 照跑）。
            # 拿掉这条豁免会多出多少条 R4、分别是哪几张图：**跑 `--audit`**，
            # 它按「比率 / 存量」两档逐条印。（`ice` Ex12/Ex15 的 RPC、`sgx` Ex9 换手率、
            # `axp` Ex8 的 excess spread 是这一档里长期都在的几条：它们的滚动同比
            # 在数学上根本不存在。条数随快照变，所以这里只举例、不记数。）
            legal_mom = is_stock or is_ratio
            # 这条豁免是**猜**出来的吗 —— 存量身份既没有列名正则支持、页面也没自称
            # 存量，只是 classify() 的兜底返回了 STOCK。这种豁免会静默关掉一条规则，
            # 与「判据读不到这个字段」是同一类失明，所以也要在输出里露头。
            weak_exempt = bool(legal_mom and m['caliber'] == 'mom' and not is_ratio
                               and m.get('kind_fallback') and not says_stock
                               and not m['unambiguous_stock'] and not m['strong_stock'])
            # ── 另一条会静默关掉 R4 的路：`says_stock` 独木桥（2026-09 补报表）───
            #
            # `legal_mom` 有三个来源：列名正则判存量、列名无歧义存量、**图题里出现
            # 存量词根**（`_STOCK_TXT`：市值 / 月末 / 余额 / 期末 / 未平仓…）。
            # 最后那一条是纯文字，而它关掉的 R4 **也是一条查文字的规则** ——
            # 「标题里有没有写单月」。同一段标题里的另一个词把这条规则整个关掉，
            # 就是拿被检查的对象当证据，文件抬头那条硬规矩在这里被绕开了。
            #
            # ⚠️ **影响面先量再说**（2026-09-02 全站快照，分母 = 登记到的 421 条
            # 同比序列）：走这条独木桥的 **9 条** —— 其中回源命中了列的 4 条，
            # 那 4 条的列名 `yoy.classify()` **全判成 FLOW**（`db1` Ex13 结算笔数、
            # `enx` Ex34 挂牌基金只数、`jpx` Ex13/Ex14 当月公开募集件数与募资额）；
            # 另外 5 条回源判不出列（`hkex` Ex9、`lseg` Ex51–54）。
            # 逐条读过标题：`jpx` 两张的「市值」来自图组名「东证市值与上市融资」，
            # 讲的是**同页另一张图**；`db1` Ex13 的「现金余额」同理。
            # 而 `enx` Ex34 的标题里写着完整的「（存量，期末口径）」——
            # 那一张的文字是对的，反倒是 `classify()` 把 `listed_funds` 判成了流量。
            #
            # ── 为什么这一轮**只进报表、不收紧** ────────────────────────────
            # 收紧（`says_stock` 不再单独成立）在今天这份快照上会新报 4 条 🟡，
            # 其中 `enx` Ex34 按上面那段是**误报**（它的口径真是存量，点对点是它唯一
            # 合法的口径，标题不必写「单月」）。四分之一的误报率买一条 🟡 规则，
            # 按本仓「宁可漏报不制造噪声」的规矩不划算 —— 而且漏掉的这几条 R4
            # 只是**标题措辞**，页上的数一个都没错，读者不会被误导。
            # 所以处置是：把这条通道**印出来**，并逐条标出「回源说它是流量」的那几条，
            # 让人能去看一眼。要收紧的人手上就有名单和误报率，别再从零量一遍。
            text_only_stock = bool(legal_mom and says_stock and not is_ratio
                                   and m['kind'] != Y.STOCK
                                   and not m['unambiguous_stock'])
            # 「文字说存量、而回源命中的列名说流量」—— 两侧正面冲突的那一档。
            # 冲突不等于文字错（enx Ex34 就是列名错），所以这里只标记，不下结论。
            stock_contradicted = bool(text_only_stock and m['kind'] == Y.FLOW)
            # 只有「拿掉这条豁免就真会响一条规则」的才值得人工看 —— 其余那些图早就
            # 在标题里写了单月，豁免与否结果一样，列出来只是噪声。
            #
            # ⚠️ 这里**只可能是 R4**（2026-09 修）。原来还有一条分支在
            # `sign_flips()` 非空时把它标成 `R1`，那是照着**上一版** R1（未声明口径
            # 的单月同比与滚动对应口径符号相反）写的；新 R1 判的是「回源命中滚动」，
            # 而 `weak_exempt` 的前提就是 `caliber == 'mom'` —— 单月线永远碰不到新
            # R1。实测（2026-09-02 21:5x 快照）：印出来的 7 条里有 5 条 `sign_flips`
            # 非空、旧分支会把它们标成 `[R1?]`，而逐条复算实际会响的都只有 R4 ——
            # 那五个标签是假的；而且 `R1` 分支在前，还把这 5 条的 R4 判断整个跳过了。
            # （7 与 5 是那一刻的读数，随快照变；结论「单月线碰不到新 R1」不随快照变。）
            hidden = 'R4' if (weak_exempt and not d['mom_in_title']) else ''
            # 与滚动口径符号相反的月份数：**不是规则**，是给人看的旁证 ——
            # 「这条线到底像不像流量」难判时，方向分歧多的那几条更值得先看一眼。
            # 判据这一侧不拿它报 finding（那件事归 §6.1 第 3 条，由每张图的图注自己印）。
            flips = len(sign_flips(m, ms, idx)) if weak_exempt else 0
            it = {'page': page, 'n': n, 'chart_kind': kind_, 'title': title,
                  # 这条序列写进 payload 时的小数刻度（`_write_quantum()`）——
                  # `_tol_for()` 拿它定容差，`--audit` 拿它印刻度分布。存下来是为了
                  # 让「谁写成了整数刻度」可核对，而不是又一个只活在注释里的数。
                  'write_k': _write_quantum(s['values']),
                  'where': s['where'], 'name': s['name'], 'exempt': exempt,
                  'says_stock': says_stock, 'is_stock': is_stock,
                  'is_ratio': is_ratio, 'legal_mom': legal_mom,
                  'text_only_stock': text_only_stock,
                  'stock_contradicted': stock_contradicted,
                  'weak_exempt': weak_exempt, 'hidden_rule': hidden,
                  'sign_flips': flips,
                  'declared': d, 'match': {k: v for k, v in m.items() if k != 'alts'},
                  'alts': m.get('alts', [])}
            items.append(it)

            # ⚠️ 这里从前是 `if exempt: continue`（无条件放行整个规则循环）。
            # 2026-09 收窄成「豁免只关掉 R4」—— 理由与实测见 EXEMPT_KINDS 上方那段。

            # R2 存量被称作「滚动合计」。先判这条，它比 R1 更硬（图在说一句关于
            # 自己算术的假话）。三个条件同时成立才报，逐条都是为了压噪声：
            #   ① 列名正则命中存量，**且**（列名无歧义 或 图题自己说是存量）——
            #      只凭列名会误伤 `new_brokerage_accounts_k`（当月新开户数是流量，
            #      名字里却有 accounts）；
            #   ② 文字里确实写了「滚动**合计**」。写「滚动均值」的这一条不报 ——
            #      但那**不是因为它对**：新 §6.1 第 2 条把存量的口径定死成点对点，
            #      滚动均值那条线同样撤了。它不报 R2 只是因为 R2 判的是「措辞在说
            #      自己算术的假话」，而「均值」对 Σ12/Σ12′ 是真话（数值完全一样，
            #      实测 hkex 市值两者的最大差在 1e-14 量级，即纯浮点噪声 ——
            #      这里不写死那个位数，它随 pandas 的求和顺序都会变）。
            #      **口径本身不合规由下面的 R1 接手**
            #      —— 实测：把这张假图的措辞从「合计」改成「均值」，R2 关掉、
            #      R1 当场报 🔴。这条判据判的是措辞，不是数字。
            if m['caliber'] == 'ttm' and m['strong_stock'] \
                    and (m['unambiguous_stock'] or says_stock) \
                    and d['sum_wording'] and not d['mean_wording']:
                findings.append(dict(
                    lvl='🔴', rule='R2_stock_called_rolling_sum', page=page, n=n, title=title,
                    msg=(f'{s["where"]}「{s["name"]}」回源命中**存量列** '
                         f'{m["csv"]}:{m["col"]}，而图上/图注把这条线称作'
                         f'「12 个月滚动**合计**的同比」。数值本身没错 —— 12 个月合计比'
                         f'恒等于 12 个月均值比 —— 但对存量，「合计」（12 个月末快照相加）'
                         f'不指代任何真实的量，那是一句关于自己算术的假话。'
                         f'改法只有一条：改用**点对点同比** '
                         f'<code>yoy.mom_yoy(s, yoy.STOCK)</code>（当月末 ÷ 去年同月末 '
                         f'− 1），CONTRACT §6.1 第 2 条。'
                         f'⚠️ 不要只把措辞改成「12 个月滚动**均值**同比」—— 那句话对 '
                         f'Σ12/Σ12′ 是真的，但线还是滚动的，§6.1 第 2 条已经把存量的'
                         f'滚动均值线一并撤了（`ttm_mean_yoy` 现在只在图注里当对照量）。'
                         f'改措辞会让这条 R2 关掉、R1 当场接手报 🔴。')))
                continue

            # R1 画的是滚动口径，而这张图不在 §6.2 的例外名单里。
            # 判的是**回源复算命中的口径**，不是文字 —— 改标题骗不过它。
            # 存量列走 ttm_mean_yoy 时数值与滚动合计同比逐点相等（Σ12/Σ12′ ≡ 均值比），
            # 所以这里会连存量的「12 个月滚动均值同比」一起命中。那也该报：
            # §6.1 第 2 条把存量的默认口径定成**点对点**，滚动均值那条线同样撤了。
            if m['caliber'] == 'ttm' and (page, n) not in ROLLING_OK:
                findings.append(dict(
                    lvl='🔴', rule='R1_rolling_outside_exception_list', page=page, n=n,
                    title=title,
                    msg=(f'{s["where"]}「{s["name"]}」回源命中的是 **12 个月滚动口径**'
                         f'（{m["csv"]}:{m["col"]}，误差 {m.get("err", float("nan")):.2g}pp），'
                         f'而 ({page}, Exhibit {n}) 不在 CONTRACT §6.2 的例外名单里。'
                         f'全站同比一律单月（§6 抬头引了页面所有者的原话），'
                         f'页上不该再出现滚动线。'
                         f'改法：把这条线换成 <code>yoy.mom_yoy(s, kind)</code>，'
                         f'并按 §6.1 第 3 条把单月口径的代价印进图注'
                         f'（<code>yoy.describe(yoy.caliber_diff(...))</code> 现成可用）。'
                         f'确实该保留滚动的，先改 CONTRACT §6.2 那张表，再把 '
                         f'({page!r}, {n}) 加进本文件的 ROLLING_OK。')))
                continue

            # R4 用了单月但标题没写明（存量 / 比率同样豁免，理由同 R1）。
            # 这里的 `not exempt` 是图型豁免起作用的地方之一：热力矩阵 / 季节性 /
            # 季度柱 / 桥 / 区间带的标题本来就不该念口径（§6.3），放开这一条会凭空
            # 多出几十条 🟡 —— **具体几条、分在哪几种 kind 上，跑 `--audit`**。
            # （这个数在本文件里写死过两次、过期过两次，第二次是在订正第一次的
            # 同一个编辑里过期的。所以现在只留指针，不留数。）
            # ⚠️ **不是「唯一」的一处** —— 2026-09 一次对抗普查指出这里原来写着
            # 「`not exempt` 是图型豁免**唯一还起作用**的地方」，那句话是假的：
            # `check_page_mix()` 里还有一处 `if it['exempt'] or it['legal_mom']:
            # continue`，把豁免图整条排除在 R3 的混用之争外。两处的作用不一样，
            # 都得算：这一处关掉 R4，那一处把豁免图从 R3 的分子里拿掉。
            if not exempt \
                    and (m['caliber'] == 'mom'
                         or (d['mom_anywhere'] and not d['roll_anywhere'])) \
                    and not legal_mom and not d['mom_in_title']:
                findings.append(dict(
                    lvl='🟡', rule='R4_mom_not_in_title', page=page, n=n, title=title,
                    msg=(f'{s["where"]}「{s["name"]}」是单月同比'
                         + (f'（回源命中 {m["csv"]}:{m["col"]}）' if m['caliber'] else '（据图注）')
                         + '，但标题里没有「单月 / single-month」。'
                           'CONTRACT.md §6：要用单月同比必须在标题里写明。')))

            # R7 比率列的同比被画成「百分比的百分比」。放在 R4 之后、不带 continue：
            # 它与 R1/R2 互斥（那两条只在 caliber=='ttm' 时开口，R7 只在 'mom' 时），
            # 与 R4 不互斥但也不重叠（R7 命中的都是 legal_mom，R4 早被豁免掉了）。
            findings += check_ratio_pp(page, ex, s, m)
            # R8 近零基数上画着同比而没有任何提示。同样不带 continue：它与 R4 / R7
            # 讲的是三件不同的事（标题措辞 / 比率的单位 / 这个读数根不根本可读），
            # 一张图同时犯两条就该同时报两条。
            findings += check_near_zero(page, ex, s, m, ms, idx)

    findings += check_page_mix(payload, page, items)
    findings += check_whitelist(payload, page)
    return findings, items, census


def on_second_axis(where, ex):
    """这条序列画在**次轴**上吗 —— 与 `yoy_series()` 分派轴标题的规则逐字同一套。

    `yoy` 那一路恒是次轴，`line` 只有在 `ylab2` 非空时才在次轴上（否则
    `yoy_series()` 传给它的轴标题就是 `ylab`）；其余各路都在主轴。
    与引擎对得上：`assets/charts.js` 里那句「谁在右轴上：gs_bar 是可选的 `ex.yoy`，
    其余双轴图型都是 `ex.line`」。两处一旦分叉，R7 就会拿主轴的量纲去给次轴序列作证。
    """
    return where == 'yoy' or (where == 'line' and bool(ex.get('ylab2')))


def check_ratio_pp(page, ex, s, m):
    """R7：比率列的同比被画成「百分比的百分比」，而不是百分点差（§6.1 第 4 条）。

    ── 为什么要有这一条 ──────────────────────────────────────────────────────

    2026-09 一次对抗普查在页面上抓出 5 张这种图（`ice` Ex12 印 −20.0%、`miax` Ex12
    印 −36.4%、`miax` Ex13 连基期为负都照印 −92.9%），而 R1–R5 **从头到尾报的都是
    🟡 0** —— 这一整类错误当时判据完全不管。RPC 从 0.05 掉到 0.04 是 **−1bp**，
    写成「−20%」不是精度问题，是换了一个量在说话。

    ── 判据：口径由数值定死，「是不是比率」要两票 ────────────────────────────

    ① **命中的是相对变化矩阵，不是百分点差矩阵**（`m['caliber']=='mom'` 且
       `not m['pp']`）。`identify()` 把每一列的两种单月同比都算了：`mom_yoy(s, FLOW)`
       走相对变化、`mom_yoy(s, RATIO)` 走百分点差，两条曲线对同一列差得很远，
       命中哪条是**数值**说了算 —— 这一票不看任何文字。
    ② `yoy.classify(命中的列名) == RATIO` —— 列名词根这一票。
    ③ 这条同比所在图的**主轴量纲**是比率量纲（`single.unit_is_ratio(ex['ylab'])`）。

    ②③ 就是 `build/single.py` `col_is_ratio()` 的第 ③ 级，逐字同一套证据；两票
    **必须同时**成立，理由与那边逐字相同：只信 ② 会误伤利率**产品**的成交量与未平仓
    （`oi_rates_kcontracts`、`adv_rates_kcontracts`）、保证金**余额**
    （`margin_total_audbn`）—— 列名里有 `rate` / `margin`，量却是张数和金额；
    只信 ③ 会误伤 `A$/trade` 这种「量纲长得像 RPC、同比却只能是百分比变化」的列。
    2026-09-02 21:5x 全站实测（分母 = 回源判出「单月」口径的全部序列）：单靠 ② 会挑出
    **11 条**画相对变化的序列，其中落在 R7 射程（次轴那一路）内的 **9 条**；③ 把这
    9 条**全部**挡掉，最终报 **0 条**（那 11 条的主轴分别是 `A$bn` / `k contracts` /
    `$bn` / `EUR per GBP` 之类，一个比率量纲都不是）；而 R7 够得到的
    真比率序列 —— 次轴那一路的 9 条：`axp` Ex8、`ice` Ex12/15、`lseg` Ex10/11、
    `miax` Ex8/12/13、`sgx` Ex9 —— 今天全都规规矩矩画着百分点差。
    所以这条规则今天**报 0 条，且那个 0 是有理由的**：不是没查，是查过、每一张都对。
    （`ice` Ex9 那张 RPC 热力矩阵也是真比率、也画着百分点差，但它的格子就是同比本身、
    没有「主轴量纲」可读，按下一段的规矩本来就不在 R7 的射程内。）

    ── 为什么只在次轴那几路上开口 ────────────────────────────────────────────

    ③ 读的是 `ex['ylab']`，那是**主轴**的量纲；只有当这条同比画在**次轴**上时，
    主轴上放的才是水平值、`ylab` 才是「这一列本身的量纲」。同比自己画在主轴上时
    （`values` / `matrix` / `bar` 那几路），`ylab` 描述的是同比而不是那一列，
    拿它去判「这一列是不是比率」就是一句关于别人的话。那几路因此**漏报**，
    是有意的：本仓宁可漏报不制造噪声。（现成的反例：`exchanges-products` Ex4 是
    热力矩阵，格子本身就是同比、`fmt='pct0'`，而它回源命中的
    `adv_rates_kcontracts` 是流量 —— 拿 `fmt`/`ylab` 当比率证据，这张图会被误报。）

    ── 判据这一侧拿不到的那一票，以及它的后果 ────────────────────────────────

    `col_is_ratio()` 的第 ① 级是 spec 里显式写的 `'ratio': True/False`。判据读的是
    payload、不是 spec，**这一票永远拿不到**：
      · 显式 `ratio: True` 而 ②③ 认不出的真比率列 → R7 漏报（判据不知道它是比率）；
      · 显式 `ratio: False` 而 ②③ 都命中的列 → R7 会误报一次。
    今天全仓没有任何一个 spec 写过 `'ratio'`（`build/specs/ice.py` 只在注释里把它
    留作后路），所以第二种情形现在不存在。真出现了，别改这条规则的判据去将就它 ——
    在这里加一份 `(页, 图号)` 的例外名单，并像 `ROLLING_OK` 那样在 CONTRACT 里留一份
    对应的表；无名单的沉默和有名单的沉默，在输出上要分得开。
    """
    if m['caliber'] != 'mom' or m.get('pp') or m['kind'] != Y.RATIO:
        return []
    if not on_second_axis(s['where'], ex) or not unit_is_ratio(ex.get('ylab')):
        return []
    return [dict(
        lvl='🟡', rule='R7_ratio_yoy_as_pct_change', page=page, n=ex.get('n'),
        title=ex.get('title', ''),
        msg=(f'{s["where"]}「{s["name"]}」回源命中 {m["csv"]}:{m["col"]}，'
             f'而且命中的是**相对变化**那一档（<code>yoy.mom_yoy(s, yoy.FLOW)</code>，'
             f'误差 {m.get("err", float("nan")):.2g}pp）—— 不是百分点差。'
             f'这一列有两票说它是比率：列名走 <code>yoy.classify()</code> 判成 RATIO，'
             f'主轴量纲「{ex.get("ylab")}」也是比率量纲'
             f'（<code>single.unit_is_ratio()</code>）。'
             f'比率列的同比画成「百分比的百分比」是 CONTRACT §6.1 第 4 条点名禁止的：'
             f'RPC 从 0.05 掉到 0.04 是 −1bp，不是 −20%；基期为负或接近零时'
             f'那个百分数连符号都读不出意思。'
             f'改法：这条线换成 <code>yoy.mom_yoy(s, yoy.RATIO)</code>（当月 − 去年同月，'
             f'单位 pp/bp），次轴标题与图注跟着改口径词。'
             f'⚠️ 若这一列其实**不是**比率（<code>classify()</code> 会把利率**产品**的'
             f'张数、保证金**余额**按词根误判成比率），改法在 spec 那一侧：'
             f'显式写 <code>&#39;ratio&#39;: False</code>，或者把 <code>unit</code> 写成'
             f'量纲白名单认不出的写法 —— 判据读不到 spec，那时把 '
             f'({page!r}, {ex.get("n")}) 记进本文件的例外名单并同步 CONTRACT。'))]


def rhs_series(ex):
    """引擎认定的「右轴上那条序列」—— 与 `assets/charts.js` 的 `rhsOf()` 逐字同一套：
    `gs_bar` 是 `ex.yoy`，其余双轴图型是 `ex.line`。

    R8 要拿它读**右轴的**截轴字段 `ymax`。两处一旦分叉，R8 就会去问错一条序列
    有没有被截 —— 与 `on_second_axis()` 那条注释担心的是同一件事。
    """
    if ex.get('kind') == 'gs_bar':
        y = ex.get('yoy')
        return y if isinstance(y, dict) and y.get('values') else None
    ln = ex.get('line')
    return ln if isinstance(ln, dict) and ln.get('values') else None


def axis_capped(ex, where):
    """这条序列**所在那根轴**上截轴了没有。

    ⚠️ **左右两轴的截轴字段不是同一个，这一点最容易写错**：
      · 左轴（主轴）看 exhibit 级的 `ycap` / `yfloor`；
      · 右轴（次轴）看**右轴那条序列自己的** `ymax` —— `assets/charts.js` 里
        `_rhsCap = rhsOf(ex).ymax`，那段注释写得很清楚：「左轴早就有 ycap 解决
        同一个问题，右轴缺这半边」，后来补的就是 `ymax`。
    本仓的同比线绝大多数画在**右轴**，所以拿 `ycap` 去判一条右轴金线有没有被截，
    是一句关于**另一根轴**的话 —— 与 `ratio_axis()` 不肯拿 exhibit 级 `yfmt` 给次轴
    作证、R7 不肯拿主轴 `ylab` 给主轴同比作证，是同一条规矩。

    `heat_matrix` 的 `matrix` 那一路两边都够不到（格子本身就是同比，没有轴可截）：
    这里对它恒回 False，也就是说那种图只剩「图注点名」这一条路。这是实情不是缺陷 ——
    给一张热力矩阵加 `ycap` 引擎根本不读，判据要是认了它，就等于承认了一个不存在的补救。
    """
    if on_second_axis(where, ex):
        r = rhs_series(ex)
        return bool(r) and r.get('ymax') is not None
    return ex.get('ycap') is not None or ex.get('yfloor') is not None


def names_near_zero_month(ex, nz_months):
    """图注里有没有**指着近零月**说话 —— 声明义务那一票（不是口径证据）。

    判据：这张图**自己的**文字（title / note / src_extra / cap_note / mark_note /
    annot）里，存在**同一句**同时满足两件事：
      ① 命中 `_NEAR_ZERO_DECL`（这句话在谈基期近零）；
      ② 出现一个 `lab2month()` 解得出、且**落在 `nz_months` 里**的月份标签。

    ② 的集合来自 `yoy.near_zero_base()` 的数值计算，不是文字 —— 所以这一票问的是
    「你有没有指着我算出来的那几个月说话」，不是「你说了什么口径」。

    为什么两件事缺一不可：
      · 只要 ① —— 一句「本列有若干个月基期近零」没有告诉读者**哪几个读数不能读**，
        而 §6.1 第 5 条要防的正是「读者把 +9,865% 当成量涨了 98 倍」。
      · 只要 ② —— 见 `_SENT_SPLIT` 上方那段实测：jpx Ex14 的图注印着
        「最大跳变 9245pp（Mar-21 → Apr-21）」，Apr-21 正好是近零月，
        而那句话讲的是跳变。

    页尾的 `payload['notes']` **不算**：§6.1 第 5 条的警告要出现在读者看那个数的
    地方。这与 R3 的方向不同是有意的 —— R3 查的本来就是「页尾口径说明」这件事。
    """
    txt = _txt(ex.get('title'), ex.get('note'), ex.get('src_extra'),
               ex.get('cap_note'), ex.get('mark_note'), ex.get('annot'))
    want = set(nz_months)
    for sent in _SENT_SPLIT.split(txt):
        if not _NEAR_ZERO_DECL.search(sent):
            continue
        for tok in _MONTH_TOKEN.findall(sent):
            if lab2month(tok) in want:
                return True
    return False


def check_near_zero(page, ex, s, m, months, idx):
    """R8：近零基数上画着同比，而这张图既没截轴、图注也没点名近零月（§6.1 第 5 条）。

    ── 为什么必须有这一条 ────────────────────────────────────────────────────

    §6.1 第 5 条（近零基数别画同比）是**唯一一条 R0–R7 一条都没碰过**的口径规矩：
    坏了不会响，而它坏起来的样子是页面上印着四位数的同比 —— 2026-09-02 的
    `data/jpx.js` Ex14 次轴最大 **+9,865.0%**、`data/db1.js` Ex29 次轴最大
    **+1,958.6%**（两个数都是从 payload 里取的窗口内最大值，跑
    `python3 -c "…max(ex['yoy']['values'])…"` 可复核；数会随下个月的数据变）。
    读者读到的不是「量涨了」，是分母掉到零附近。契约给的例子（`db1` EURIBOR
    在近零基数上相邻月跳 40,609pp）说的就是这个量级。
    ⚠️ **这条规则的命中数在写它的那两个小时里就从 10 掉到 0，值得把两次读数一起记下**
    （连时刻、连分母，规矩见 §6.5）：
      · 2026-09-02 23:5x：`near_zero_base(该列, win=图窗)['flag']` 为真的图 **10 张**
        （db1 Ex12/29/35、enx Ex13/26、jpx Ex13/14、miax Ex6、tmx Ex22/23），
        **10 张里截轴 0、图注点名 0** → R8 报 10 条 🟡。
      · 2026-09-03 00:0x：底座那一侧（页面所有者拍板的「保留线，加截轴 + 图注警告」）
        落地了 —— 同样这 10 张，9 张的次轴加了 `ymax`，`miax` Ex6 那张热力矩阵
        没有轴可截、改成在图注里点名 Aug-25 → R8 报 **0 条**。
    **别把这里的 10 或 0 抄走**：它随底座与数据一起动。今天几条，跑一次全站扫描，
    或 `--json` 数 `findings` 里 rule 为 `R8_near_zero_base_undeclared` 的条数。
    今天这个 0 是**可核对的 0**：`--selftest` 里那条正例（同一列、同一窗口、
    把 `ymax` 拿掉）证明它照样会响。

    ── 三个条件，两个证据来源 ────────────────────────────────────────────────

    ① **口径与列由回源定**：只在 `caliber == 'mom'` 且回源命中了具体一列时才开口。
       判不出列就不喊（本仓规矩），命中滚动的那一档已经是 R1 的 🔴、
       而且 `near_zero_base()` 量的是**单月**基期（`shift(12)`），
       拿它去说一条滚动线是一句关于别人的话。
    ② **近零由数值定**：`yoy.near_zero_base(水平值原列, win=这张图画出来的月份)`。
       窗口必须是图窗 —— 那个函数的 docstring 明写「有几个月不可读只能数图上画出来
       的那些月」，拿全历史数会让一条早年近零、如今正常的序列永远背着标签。
    ③ **补救有没有做，两条路任选其一**：
         · 截轴（`axis_capped()`，注意左右两轴字段不同）；
         · 图注点名近零月（`names_near_zero_month()`）。
       两条都没有才报。两条路是页面所有者拍板的那个方案的两半，不是我发明的档次。

    ── 它够不到的地方（有意留的漏报，说清楚免得被当成「查过了」）──────────────

    条件 ① 意味着**回源判不出列的同比一条都进不了这条规则** —— 派生量（ADV × 交易日、
    多列相加、FX 换算过的）永远匹配不上任何原始列，而它们同样可能画在近零基数上。
    这不是能顺手补的：没有那一列就没有基期，`near_zero_base()` 无从算起。
    要覆盖那一档，得走 `HOW_TO_WIRE_IN` 第 1 条那条路 —— 让生成器把
    `caliber_src` 写进 payload，判据照着它回源。今天有多少条落在这个盲区里：
    跑全站扫描看抬头那行「未确定 N 条」。

    ── 为什么是 🟡 而不是 🔴 ─────────────────────────────────────────────────

    按本仓给 🔴 的两条门槛（CONTRACT §6.6：不会误报 + 别的规则接不住）：第二条成立，
    第一条不成立 —— 「补救做没做」那一票里有一半是读文字的，而文字能用判据认不出的
    方式把话说对（比如把警告写进页尾而不是图注、或者用一句不含关键词的大白话）。
    会误报的规则不该有停机的权力，所以 🟡。

    ⚠️ 图型豁免（§6.3 / `EXEMPT_KINDS`）**不关掉这一条**，与 R1/R2/R7 一致：
    §6.3 豁免的是「标题该不该念口径」，不是「不可读的读数要不要提醒」。
    `heat_matrix` 的格子照样会印出四位数的同比，读者一样会误读。
    """
    if m['caliber'] != 'mom' or not m.get('csv'):
        return []
    k = (m['csv'], m['col'])
    if k not in idx['meta']:                     # 理论上不会发生；发生了就别猜
        return []
    win = [x for x in months if x]
    if not win:
        return []
    nz = Y.near_zero_base(idx['mat']['lvl'][k], win=win)
    if not nz['flag'] or axis_capped(ex, s['where']) or names_near_zero_month(ex, nz['months']):
        return []
    w = nz['worst']
    worst_txt = ''
    if w:
        # ⚠️ 基期正好是 0 时单月同比算不出来（除以零），`worst[2]` 是 NaN。
        # 那不是「同比等于 nan%」—— 图上那一格是**空的**，读者看到的是一个缺口。
        # 把 NaN 直接格式化进句子会印出「+nan%」，那是一句字面上的假话，
        # 而且恰好出现在本判据要防的那种「读者被数字误导」的位置上。
        worst_txt = (f'窗口内最极端的一个月是 {w[0]}：基期 {w[1]:.4g}，'
                     + (f'这一格印出来的同比是 {w[2]:+,.1f}%。'
                        if np.isfinite(w[2]) else
                        '基期正好是 0，同比根本除不出来 —— 这一格在图上是空的，'
                        '折线在那里断开。'))
    return [dict(
        lvl='🟡', rule='R8_near_zero_base_undeclared', page=page, n=ex.get('n'),
        title=ex.get('title', ''),
        msg=(f'{s["where"]}「{s["name"]}」回源命中 {m["csv"]}:{m["col"]}，'
             f'而这一列在**本图画出来的窗口**上是近零基数序列：'
             f'{len(nz["months"])} / {nz["n_base"]} 个有基期的月份里，基期绝对值小于'
             f'本列 |值| 中位数的 {Y.NEAR_ZERO_BASE_FRAC:.0%}'
             f'（占 {nz["share"]:.1%} ≥ 阈值 {Y.NEAR_ZERO_SERIES_SHARE:.1%}，'
             f'<code>yoy.near_zero_base()</code> 的 flag 为真）。{worst_txt}'
             f'这种月份的同比读的不是量在变，是分母在变 —— CONTRACT §6.1 第 5 条。'
             f'而这张图**既没有截轴、图注里也没有一句指着近零月说话**：'
             + (f'`heat_matrix` 的格子本身就是同比，**没有轴可截** —— '
                f'这张图只剩「图注点名」这一条路。'
                if s['where'] == 'matrix' else
                f'{"次轴" if on_second_axis(s["where"], ex) else "主轴"}的截轴字段是 '
                f'<code>{"该序列自己的 ymax" if on_second_axis(s["where"], ex) else "ycap / yfloor"}</code>，'
                f'现在是空的。')
             + ('改法只有一条（这张图没有轴可截）：'
                if s['where'] == 'matrix' else
                '改法二选一（页面所有者拍板的是「保留线 + 两样都上」）：'
                '给这条线所在的轴加截轴，超界的点会钳到边界、画红圈、真值竖排标出'
                '（<code>assets/charts.js</code>，截轴不删点）；再') +
             f'在**本图图注**里用一句话点名近零月 —— 判据认的是「**同一句**里既说了'
             f'基期近零、又出现了这 {len(nz["months"])} 个月里的某一个」'
             f'（前几个：{"、".join(nz["months"][:3])}；月份写成 '
             f'<code>lab2month()</code> 认得的任何一种都行，`Jan-17` / `2017-01` / '
             f'`1/17` 都算），页尾那段不算（读者是在图旁边读那个数的）。'
             f'⚠️ 这一条查的是「有没有把话说出来」，不是口径：哪几个月近零由数值算，'
             f'文字只回答有没有点名。'))]


def check_whitelist_pages(scanned_pages):
    """R5 的**全局**那一半：`ROLLING_OK` 上的**页**，这一轮到底**查过**没有。

    ⚠️ `scanned_pages` 收的是「**成功解析并跑完规则**的页名」（`scan_pages()` 的第四个
    返回值），**不是**「`data/` 下存在的页文件」。2026-09 之前收的是后者，于是名单页
    丢失的三种形态里只有两种会响 —— 三种的实测对照表见 `scan_pages()` 的 docstring，
    `--selftest` 里第三种由 `expect_broken` 那一对用例钉住。

    ⚠️ 这是 2026-09 第二次对抗普查抓出来的 blocker，与它旁边那个函数是同一个病的
    两种形态。`check_whitelist()` 嵌在 `check_page` 里，开头就是 `if pg != page:
    continue` —— 它只对**当前被扫到的那一页**跑。而 `main()` 遍历 `data/*.js`：
    **页文件没了，就没有哪一次调用会轮到它**，于是 R5 与 R1 一起失明。

    构造验证（把 `data/` 整个复制到临时 root、`series/` 软链回仓库）：
      · 删掉 `data/exchanges12.js`（这一页带着 §6.2 名单五张里的三张 Ex4/7/8）
        → 旧版输出「🔴 0 🟡 0 / 无硬错，退出码 0」，一条 `R5_whitelist_exhibit_missing`
        都没有；
      · 改名成 `data/exchanges-12.js`（页还在、图也都还在，只是那三张滚动图现在挂在
        一个**不在 `ROLLING_OK`** 的页名下）→ 同样「🔴 0 🟡 0」。
    两种情形 R1 也接不住：那三张是横截面图（4 根柱 / 横轴是交易所名），
    `identify()` 恒回 `caliber=None`。
    （`--selftest` 里 `expect_pages` 那三条用例把这两种情形连同反例一起钉住了，
    喂的是「这一轮扫到了哪些页」而不是 payload —— 页文件没了就没有 payload 可喂。）

    而「图被删了、还是图号整体位移了」**正是隔壁那条 docstring 自称要防的那一类**。
    CONTRACT §6.2 也只写了「名单要跟着表走，改一处要改两处」，防的是名单条目被删，
    没防**页名变**。所以覆盖检查必须提到全局来做：扫完所有页之后，拿「名单上出现过
    的页」减去「这一轮实际扫到的页」。

    ⚠️ **这一条是 🔴，另外两条 R5 维持 🟡 —— 等级是 CONTRACT §6.6 定的**
    （读于 2026-09-02 21:4x：「`R5_whitelist_page_missing`（名单上的整页没扫到）
    定为 🔴，要能让整轮停机」）。判据这一侧 2026-09 之前给的是 🟡，而 🟡 不改退出码
    ——`monthly_run` 只看 `returncode != 0`，于是这一条从「无人知晓」只挪到了
    「印在没人读的日志中段」，离「会响」还差一步。给它停机权的两条门槛在契约里写着：
    **不会误报**（它是集合相减：名单上的页名 − 这一轮实际扫到的页名，既不靠回源也不靠
    文字；`--page` 划范围时本来就不跑，读不出来的页走 `R0_page_unreadable` 那条 🟡），
    **而且别的规则接不住**（页一没，R1 在横截面图上恒回「判不出」，R5 的逐图那一半
    连调用都轮不到）。⚠️ 改等级要两边一起改：这里降回 🟡 而契约不改，就又是一处
    「同一份规矩的两个副本互相矛盾」。

    ⚠️ 只在**全量扫描**时调用（`main()` 里 `--page` 没给的那一支）。`--page cme`
    是使用者自己划的范围，拿它来喊「exchanges12 不见了」是噪声不是信号。
    """
    out = []
    for pg in sorted({p for p, _ in ROLLING_OK} - set(scanned_pages)):
        ns = sorted(n for p, n in ROLLING_OK if p == pg)
        out.append(dict(
            lvl='🔴', rule='R5_whitelist_page_missing', page=pg, n=None,
            title='（CONTRACT §6.2 名单）',
            msg=(f'`ROLLING_OK` 与 CONTRACT §6.2 的名单上有 `{pg}` 页的 '
                 f'Exhibit {ns}，但这一轮**整页都没扫到** —— `data/{pg}.js` 不存在。'
                 f'页被删了、还是页名改了（本轮扫到的是 {sorted(scanned_pages)}）？'
                 f'两种都要把名单跟着改。'
                 f'⚠️ 这一条不响的话，那几张图的口径**没有任何东西看着**：'
                 f'R5 的逐图检查只对被扫到的页跑，而 R1 在横截面图上回源对不齐、'
                 f'恒回「判不出」。名单指着一整页不存在的图，等于那几处滚动口径的'
                 f'豁免凭空落到了别处。'
                 f'（这一条是 🔴、会让退出码变 1 —— CONTRACT §6.6 定的：'
                 f'它不误报，而且别的规则接不住，所以给它停机的权力。'
                 f'停机之后要做的事本来就是必做的：§6.2 那张表与 `ROLLING_OK` '
                 f'是同一份名单的两个副本，页没了两边都得改。）')))
    return out


def check_whitelist(payload, page):
    """R5：`ROLLING_OK` 名单上的图，必须**还在自称**滚动口径，而且必须还存在。

    为什么需要这一条 —— 这是 2026-09 一次对抗普查抓出来的：R1 判口径靠**回源复算**，
    而名单上那五张全是横截面图，序列长度就是成员数（apac Ex5/Ex15、exchanges12
    Ex7/Ex8 各 4 根柱；exchanges12 Ex4 的横轴是交易所名不是月）。回源对不齐 ⇒
    `identify()` 一律回 `caliber=None` ⇒ **R1 在它们身上一次都跑不到**，
    于是白名单从来没有压制过任何一条 finding，也就从来没被测试过。
    后果不是「多了一行死代码」，是：这几张图哪天被改成别的口径、或者被删掉、
    或者图号位移到别的图上，**没有任何东西会响**。

    这一条判不了数（回源对不齐是客观的），所以它退一步判**自述**：
      · 名单上的 (页, 图号) 在 payload 里找不到  → 🟡（图被删了或图号移了，名单该更新）
      · 找得到，但 title / ylab / ylab2 / 各序列名里**再没有一处**声明滚动 → 🟡
        （口径可能被改了，也可能只是措辞掉了 —— 两种都要人去看一眼）

    ⚠️ **这个函数只管「页在、图不在」，管不了「页不在」** —— 它开头就 `if pg !=
    page: continue`，而它的调用方 `check_page` 只在页被扫到时才跑。整页删掉或改名
    时它一次都不会被调用。那一半归 `check_whitelist_pages()`（见那里的构造验证），
    由 `main()` 在扫完全部页之后调一次。两个函数缺一个，R5 就有一整类改动看不见。

    ⚠️ **这里这两条是 🟡，隔壁那条整页的是 🔴** —— CONTRACT §6.6 明写这两条不跟着升：
    它们判的是**自述**（图还在不在、还念不念滚动口径），自述会因为无关的改写而变，
    更要紧的是这两种情形下**页还在被扫**，R3 的滚动侧注入照常工作，白名单不至于指着
    一片虚空。（`exhibit_missing` 该不该也升 🔴 没定论；要升的人先按契约那两条门槛
    ——「不会误报 + 别的规则接不住」—— 把误报率量出来。）

    自述能被改坏，所以这不是强判据；但它把「白名单被静默架空」这件事变成了**会响的**。
    与 R1 的关系：R1 管「不该滚动的画了滚动」，R5 管「该滚动的还在不在滚动」——
    两个方向，缺一个就有一整类改动没人看着。
    """
    out = []
    ns = {ex.get('n'): ex for ex in (payload.get('exhibits') or [])}
    for pg, n in sorted(ROLLING_OK):
        if pg != page:
            continue
        ex = ns.get(n)
        if ex is None:
            out.append(dict(
                lvl='🟡', rule='R5_whitelist_exhibit_missing', page=page, n=n,
                title='（CONTRACT §6.2 名单）',
                msg=(f'`ROLLING_OK` 与 CONTRACT §6.2 的名单上有 ({page}, Exhibit {n})，'
                     f'但本页 payload 里没有这个图号（现有 {sorted(x for x in ns if x)}）。'
                     f'图被删了、还是图号整体位移了？两种都要把名单跟着改 —— '
                     f'名单指着一张不存在的图，等于对某个口径的豁免落在了别的图上。')))
            continue
        sig = _txt(ex.get('title'), ex.get('ylab'), ex.get('ylab2'), ex.get('legend'),
                   *[str((x or {}).get('name') or '') for x in (ex.get('series') or [])],
                   *[str((x or {}).get('name') or '') for x in (ex.get('groups') or [])],
                   str((ex.get('yoy') or {}).get('name') or ''),
                   str((ex.get('line') or {}).get('name') or ''),
                   str((ex.get('net') or {}).get('name') or ''))
        if not _ROLL_DECL.search(sig):
            out.append(dict(
                lvl='🟡', rule='R5_whitelist_no_longer_declares_rolling', page=page, n=n,
                title=ex.get('title', ''),
                msg=(f'({page}, Exhibit {n}) 在 CONTRACT §6.2 的名单上（页面所有者点名'
                     f'保留 12 个月滚动口径的几处之一），但它的标题 / 轴标题 / 图例 / '
                     f'各序列名里**一处都没有再声明滚动口径**。'
                     f'要么口径真的被改了（那就把它从名单与 `ROLLING_OK` 里拿掉），'
                     f'要么只是措辞掉了（那就把声明加回去 —— 名单上的图必须逐处点名，'
                     f'§6.2 末段）。判据在这几张图上回源对不齐、判不了数，'
                     f'所以只判得了自述，这一条响就得有人去看一眼。')))
    return out


def sign_flips(m, months, idx):
    """这条单月同比与它的滚动对应口径，在窗口内哪些月符号相反。

    死区 ±SIGN_DEADBAND_PP：贴着零的正负是舍入不是方向分歧，报出来是噪声。

    ⚠️ `idx` 是**参数**，不是模块全局（2026-09 改）。原来这里读的是 `_IDX`，
    而 `_IDX` 只有 `main()` 会赋值 —— 于是 `check_page(path, idx)` 收下了 `idx`
    却不用它，任何外部调用方（包括文件末 `HOW_TO_WIRE_IN` 打算接的 payload_guard）
    一进到 `weak_exempt` 那条分支就 `NameError: name '_IDX' is not defined`。
    「函数签名收了一个依赖」本身就是一句关于自己的话，它当时是假的。
    """
    k = (m['csv'], m['col'])
    if k not in idx['meta']:
        return []
    ms = [x for x in months if x]
    a = idx['mat']['mom'][k].reindex(ms).values.astype(float)
    b = idx['mat']['ttm'][k].reindex(ms).values.astype(float)
    out = []
    for i, mm in enumerate(ms):
        if not (np.isfinite(a[i]) and np.isfinite(b[i])):
            continue
        if abs(a[i]) < SIGN_DEADBAND_PP or abs(b[i]) < SIGN_DEADBAND_PP:
            continue
        if a[i] * b[i] < 0:
            out.append((mm, float(a[i]), float(b[i])))
    return out


def check_page_mix(payload, page, items):
    """R3：同页混用口径而页尾「口径与方法说明」没有逐处点名。

    「点名」= notes 里**同一条** note 同时提到滚动口径（`_ROLL_DECL`）和 `Exhibit N`。

    ⚠️ **2026-09 点名的方向翻了**：契约的默认现在是单月（§6），所以要求点名的是
    **滚动**那一侧 —— 偏离默认的才需要逐张点名，默认口径不必，否则一页 20 张单月图
    就要念 20 遍。翻面之后这条规则实际只会作用在 `exchanges-apac` 一页上：
    全站只有它同时有单月折线（Ex17）和 §6.2 保留的滚动图（Ex5 / Ex15）。
    `exchanges12` 整页都是滚动、没有单月图，混不起来，所以不会命中。

    ── 两侧的证据来源（2026-09 第二轮修，把这条规则从「死的 0」救回来）──────────

    **单月那一侧只认回源复算**，判不出就 `continue`，不猜。原来这里有一段文字回退
    （回源判不出 → 看 `roll_in_title` / `mom_in_title`），那段是错的，而且错法很隐蔽：

      · 收窄前它看的是 `roll_anywhere`（标题 + 图注 + src_extra + ylab + annot）。
        新契约 §6.1 第 3 条要求**每一张流量同比图**都印出与滚动口径对比的代价，
        于是全站几乎每张图的图注里都提到滚动。**分母先写清楚**（2026-09-02 21:5x
        全站快照，序列级、分母 = 登记到的全部同比序列 421 条）：`roll_anywhere`
        命中 183 条，其中 **182 条同时 `mom_anywhere`**；唯一的例外是
        `exchanges-apac` Ex15 —— §6.2 名单上那张桥，它本来就是滚动的。
        照它判，一张标准的单月图会被判成滚动。
        ⚠️ **换个分母这两个数就不一样**，所以这里把分母写在前面：只数非豁免序列是
        174 / 174，按 exhibit 去重是 161 / 160。（这里原先写着「160 条里 159 条」，
        三种分母下一个都对不上 —— 一个不写分母的数没法被复核，复核者只能三种都试一遍
        然后报「取不到」。写死的数会过期，写死又不写分母的数连过期都判不出来。）
      · 收窄到 `roll_in_title`（只看 title / ylab2 / legend / 序列名四处）仍然没修干净：
        全站还剩 3 张被误判成滚动 —— `lseg` Ex10 / Ex11 / Ex30。它们的标题里写的是
        「比率列不做滚动合计也不做滚动均值」「滚动窗口正好把它抹平」——
        **提滚动是为了否认它**，而 `_ROLL_DECL` 只认关键词、不认否定。

    这不是「正则再收紧一点」能解决的：本文件开头那条硬规矩说得很清楚 ——
    **文字声明是被检查的对象，不能同时当证据**。所以整段回退删掉。

    **滚动那一侧补一个非文字的来源：`ROLLING_OK`**（= CONTRACT §6.2 那张表的副本）。
    这不是页面的自述，是契约点名的名单 —— 外部权威，不违反上面那条硬规矩。
    补它的理由是结构性的：名单上那五张全是横截面图（4 根柱 / 横轴是交易所名），
    回源永远对不齐、`identify()` 一律回 `caliber=None`，所以**只靠回源，滚动那一侧
    恒为空、R3 恒不响** —— 那正是 R5 当初要补的同一类失明，R3 这边也有一份。
    只取本页 payload 里**确实存在**的图号（不存在的那种由 R5 单独报 missing，
    塞进这里只会让 R3 对着一张不存在的图喊「你没点名」）。

    ── `named` 为什么要逐条 note 判 ────────────────────────────────────────────

    原来是「把所有提到口径关键词（滚动**或**单月）的 note 里出现过的 Exhibit 号
    全部并起来」。本仓页尾的标准写法恰恰是「Exhibit 2、Exhibit 3、…：单月同比」
    这种长列表，于是**滚动那一侧会被自己那句「我是单月」点了名**。实测
    （2026-09-02 21:5x）`cme` named={2,3,5…21} 共 19 个、`lseg` named 30 个（含
    10/11/30）、`tmx` named 23 个 —— 三处都是「单月那句话替滚动图点了名」。
    改成：只有**同一条 note 里既声明了滚动口径、又出现了这个图号**才算点名。

    ⚠️ 这两处缺陷各自都能让 R3 闭嘴，而且**任一处单独修都还是 0**：实测只修 `named`
    （保留文字回退）时，`lseg` 的 ttm 侧仍是 {10,11,30}，但 `missing` 依旧为空 ——
    因为 lseg 那条「同比口径（全页只有一种：单月）。Exhibit 4、…」的 note 自己
    也命中 `_ROLL_DECL`（它在**否认**滚动时提到了「12 个月滚动」），照样把 10/11/30
    点了名。所以不能只修一处然后拿「还是 0」当证据 —— 「恒为 0」最难分辨的就是
    这种形态：看不出是没错，还是没查。

    ⚠️ 两处都修完，R3 在当前快照上**仍然恒为 0** —— 唯一真正并存两种口径的
    `exchanges-apac` 确实逐处点了名。⚠️ **点名的是哪一条 note 要说准**（2026-09
    对抗普查更正）：这里原先记的是「Exhibit 5 连排的是三个 12 个月滚动合计的同比」
    那一条，**它不是**。那条是 `notes[10]`（下标从 0 数，2026-09-02 21:5x 复算），
    只出现了 Exhibit 5 与 Exhibit 3 两个图号，**Ex15 一次都没出现**；
    只靠它，`missing` 会留下 15，R3 反而该响。
    真正让 R3 闭嘴的是 `notes[9]`（「本页并存两种同比口径，逐处点名」那一条，
    同样下标从 0 数 —— 原先这里写「第 9 / 第 10 条」，按中文习惯读会整体差一位）：
    它同时声明滚动口径、又点齐了 5 / 15 / 17。记错了 note 的后果不是笔误 ——
    照着错的那条去理解，会以为「只要有一句说清 Ex5 的话就够了」，
    而 §6.2 要求的是名单上的**每一张**都点到。那是**诚实的 0**，不是死代码：
    `--selftest` 里有四个 R3 用例，证明它在「回源判出滚动」与「§6.2 名单注入」
    两条证据路径上都会响、在「note 点了图号但那一条没声明滚动」时也会响，
    并反向证明一张写对了的页不会响。

    ⚠️ 还留着一个**已知的漏报**，是有意留的。一条 note 只要在**任何意义上**提到
    滚动就算「在谈滚动口径」，包括在否认它 —— 而 §6.1 第 3 条要求写的那段代价文案
    正是这个形状。实测（2026-09-02 21:5x）`lseg` 的 `notes[5]` 一条就列了 30 个图号，
    而它命中 `_ROLL_DECL` 靠的是「毛刺比 12 个月滚动口径大得多（**那种口径本页一条线
    都不画**）」这半句 —— 一句标准的、契约要求的代价说明，提到滚动是为了**否认**它。
    于是那 30 个图号全部算「被点名」。要分辨「声明」与「否认」得去理解句子，
    那不是判据该做的事。
    代价可控：滚动那一侧现在只有回源复算与 `ROLLING_OK` 两个来源，都不是文字，
    所以这个漏报最多让一张**真的**画了滚动、且页尾恰好用这种句式提过它的图
    逃掉一次 🟡，不会造出假阳性。本仓的规矩是宁可漏报不制造噪声，这一条按规矩走。
    """
    mom_ns, ttm_ns = set(), set()
    for it in items:
        # 图型豁免（§6.3）不进混用之争：那些图的格内 / 柱高本来就是单月读数，
        # 不是一次口径选择。真画了滚动的豁免图由 R1 直接报 🔴，比这条硬。
        # 存量 / 比率同理不进：它们的口径是被数学定死的。
        # 一页上有几张 OI 图就喊一次「你混用口径」，那是噪声不是信号。
        if it['exempt'] or it['legal_mom']:
            continue
        c = it['match']['caliber']          # 只认回源；判不出就不猜（见 docstring）
        if c == 'mom':
            mom_ns.add(it['n'])
        elif c == 'ttm':
            ttm_ns.add(it['n'])
    present = {ex.get('n') for ex in (payload.get('exhibits') or [])}
    ttm_ns |= {n for pg, n in ROLLING_OK if pg == page and n in present}
    if not (mom_ns and ttm_ns):
        return []
    named = set()
    for x in (payload.get('notes') or []):
        x = str(x)
        if not _ROLL_DECL.search(x):        # 这条 note 得先自己在谈滚动口径
            continue
        for k in re.findall(r'(?:Exhibit|Ex\.?)\s*(\d+)', x):
            named.add(int(k))
    missing = sorted(n for n in ttm_ns if n not in named)
    if not missing:
        return []
    return [dict(lvl='🟡', rule='R3_mixed_caliber_unnamed', page=page, n=None,
                 title='（页尾口径与方法说明）',
                 msg=(f'本页混用两种同比口径：单月 Exhibit {sorted(mom_ns)}'
                      f'（回源复算判定）、12 个月滚动 Exhibit {sorted(ttm_ns)}'
                      f'（回源复算判定，或在 CONTRACT §6.2 的名单上）；'
                      f'但页尾 notes 里**没有任何一条同时**声明滚动口径并点名 '
                      f'Exhibit {missing}。'
                      f'CONTRACT.md §6.2 末段：全站默认单月，保留滚动的那几处必须在'
                      f'页尾口径说明里写成「Exhibit 5、Exhibit 15：12 个月滚动合计的'
                      f'同比」这种可核对的形式，并明写不要跨口径比高低。'
                      f'⚠️ 光在「单月同比在：Exhibit …」那句长列表里出现不算点名 —— '
                      f'那是把滚动图声明成了单月图。'),
                 missing=missing, mom=sorted(mom_ns), ttm=sorted(ttm_ns))]


# ── 判据自测：证明每一条规则都还活着 ─────────────────────────────────────────
def selftest(idx):
    """用真实序列拼出一批**故意写错**的假图，逐条确认规则会响。

    为什么需要这个：判据在真实快照上的命中数会随页面被修好而归零
    （实测 hkex Ex8 就在本次开发过程中被另一个 agent 改对了，R2 当场从 1 变 0）。
    「今天没报错」和「规则坏了」在输出上长得一模一样 —— 只有对着已知的错例跑一遍
    才能分开这两件事。这是判据的判据。

    **两种用例形态**（2026-09 加了后一种）：

      · `expect(rule, payload[, page])`  —— 这个 payload **必须**报出 `rule`。
        证明规则还会响。
      · `expect_silent(rule, payload, page, why)` —— 这个 payload **必须不**报
        `rule`。证明「压制」也还活着：白名单、图型豁免这类东西的全部作用就是让
        某条规则闭嘴，而「闭嘴」在输出上和「规则坏了」长得一模一样，只有配一个
        反例（换个页名就该响）才分得开。⚠️ 一条 `expect_silent` 单独立不住，
        必须与它的正例配对写，否则一个恒不响的判据也能把它测过。
    """
    def yoy_ex(n, csv, col, cal, months, **kw):
        k = (csv, col)
        v = idx['mat'][cal][k].reindex(months)
        ex = {'n': n, 'kind': 'gs_bar', 'fmt': 'f1',
              'xlabels': [f'{["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(m[5:7]) - 1]}-{m[2:4]}' for m in months],
              'values': [1.0] * len(months),
              'yoy': {'name': kw.pop('yname', 'y/y (RHS)'), 'color': 'GOLD',
                      'yfmt': 'pct0',
                      'values': [None if not np.isfinite(x) else float(x) for x in v]}}
        ex.update(kw)
        return ex

    ms = sorted(set(idx['mat']['mom'].index))[-40:]
    cases = []

    # `lvl` 可选：给了就连**等级**一起断言。等级不是装饰 —— 🔴 改退出码、进而让
    # monthly_run 那一轮 FAILED，🟡 只是印一行。有条规则的等级是契约点名定死的
    # （`R5_whitelist_page_missing` 要 🔴），那种就必须钉住：只断言「响了」的话，
    # 谁把它降回 🟡 都测不出来，而降级之后它就又变回「印在没人读的日志里」。
    def expect(rule, payload, page='_selftest', lvl=None):
        cases.append({'mode': 'must', 'rule': rule, 'payload': payload,
                      'page': page, 'why': '', 'lvl': lvl})

    def expect_silent(rule, payload, page, why):
        cases.append({'mode': 'must_not', 'rule': rule, 'payload': payload,
                      'page': page, 'why': why, 'lvl': None})

    def expect_pages(rule, pages, must, why, lvl=None):
        """第三种用例形态（2026-09 加）：不喂 payload，喂**这一轮扫到了哪些页**。

        R5 的全局那一半判的就是这个（`check_whitelist_pages()`），它天生够不到
        `check_payload` —— 页文件没了，就没有 payload 可喂。用 payload 形态的用例
        测它，测出来的永远是「不响」，而那正是它要防的失明。
        """
        cases.append({'mode': 'must' if must else 'must_not', 'rule': rule,
                      'pages': sorted(pages), 'page': '(扫到的页)', 'why': why,
                      'lvl': lvl})

    def expect_broken(rule, broken_page, must, why, lvl=None):
        """第四种用例形态（2026-09 加）：不喂 payload、也不喂页名集合，**造一个
        临时的 `data/` 目录跑整条管道**，其中一页故意写成解析不了的样子。

        为什么前三种形态都测不到它：`expect_pages` 喂的是「扫到了哪些页」，
        而这个洞恰恰在于**谁来决定那个集合** —— 页文件还在、路径还在，
        `{basename(p) for p in paths}` 里有它，只是 payload 解析炸了。
        要测这一层就必须让 `scan_pages()` 真的去读一次坏文件。

        `broken_page=''` 表示一页都不坏（反例）。
        """
        cases.append({'mode': 'must' if must else 'must_not', 'rule': rule,
                      'broken': broken_page,
                      'page': f'(整页解析失败: {broken_page or "无"})',
                      'why': why, 'lvl': lvl})

    # R1：一张画滚动口径、又不在 §6.2 例外名单里的图。
    # 用 sgx（一个不在 ROLLING_OK 里的页名）+ 一条真实的流量列，口径喂 'ttm'。
    w = [m for m in ms if np.isfinite(idx['mat']['mom'][('sgx.csv', 'sec_turnover_sgdmn')].get(m, np.nan))][-25:]
    wt = [m for m in ms if np.isfinite(idx['mat']['ttm'][('sgx.csv', 'sec_turnover_sgdmn')].get(m, np.nan))][-25:]
    def rolling_sgx_ex(n):
        return yoy_ex(n, 'sgx.csv', 'sec_turnover_sgdmn', 'ttm', wt,
                      title='证券市场成交额：水平值与 12 个月滚动同比',
                      yname='12 个月滚动合计的同比（RHS）',
                      note='金线 = 12 个月滚动合计的同比。')

    expect('R1_rolling_outside_exception_list',
           {'exhibits': [rolling_sgx_ex(2)], 'notes': []})

    # ── R1 的白名单一正一反（2026-09 补）────────────────────────────────────
    # 上面那条只证明「不在名单上的滚动图会被报」。`ROLLING_OK` 的全部作用是让
    # **名单上的**滚动图不被报，而「不被报」和「R1 整条坏了」在输出上一模一样 ——
    # 所以再要一对：同一张图，页名 / 图号在名单内 → 必须**不**报；挪到名单外的
    # 页名（sgx）→ 必须报。少了任何一半，这个白名单都可能是死的而没人知道。
    # 用 ('exchanges12', 4)：Ex7 / Ex8 也在名单上，补两个自称滚动的桩件，
    # 免得 R5 顺带报 missing 把输出搅浑（R5 自己另有专门的用例）。
    def _wl_stub(n, name):
        return {'n': n, 'kind': 'grouped_bars', 'xlabels': ['CME', 'ICE'],
                'title': f'{name}（12 个月滚动合计的同比）', 'ylab': '% y/y',
                'groups': [{'name': f'{name} y/y（12 个月滚动合计）',
                            'values': [1.0, 2.0]}]}

    wl_payload = {'exhibits': [rolling_sgx_ex(4), _wl_stub(7, 'Two units'),
                               _wl_stub(8, 'Contract-shrink')],
                  'notes': []}
    expect_silent('R1_rolling_outside_exception_list', wl_payload, 'exchanges12',
                  why='(exchanges12, Ex4) 在 ROLLING_OK 上 → 白名单必须压住 R1')
    expect('R1_rolling_outside_exception_list', wl_payload, 'sgx')  # 同一张图，名单外

    # R2：存量 + 滚动窗口同比 + 文字自称「滚动合计」
    w2 = [m for m in ms if np.isfinite(idx['mat']['ttm'][('hkex.csv', 'mktcap_hkdtn')].get(m, np.nan))][-13:]
    expect('R2_stock_called_rolling_sum', {
        'exhibits': [yoy_ex(8, 'hkex.csv', 'mktcap_hkdtn', 'ttm', w2,
                            title='Securities market capitalisation',
                            yname='12M rolling y/y (RHS)',
                            note='次轴 = 12 个月滚动合计的同比（最近 12 个月合计 ÷ 上一个 12 个月合计 − 1）。')],
        'notes': []})

    # ── R3 的两个用例：两条证据路径各测一条 ─────────────────────────────────
    # 路径 A：滚动那一侧由**回源复算**判出来。页名用 '_selftest'，理由只有一条 ——
    # 让这个用例不依赖任何真实页在 ROLLING_OK 上的状态；R1 会一起响是预期的，
    # 不影响 R3（`items.append(it)` 在 R1 的 `continue` 之前，`check_page_mix`
    # 读的是 `items` 不是 `findings`；实测把 ('_selftest', 3) 加进 ROLLING_OK
    # 之后 R1 不再响，R3 照样报）。
    expect('R3_mixed_caliber_unnamed', {
        'exhibits': [
            yoy_ex(2, 'sgx.csv', 'sec_turnover_sgdmn', 'mom', w,
                   title='当月成交额（单月同比）', note='本图用单月同比。'),
            yoy_ex(3, 'hkex.csv', 'adt_hkdbn', 'ttm',
                   [m for m in ms if np.isfinite(idx['mat']['ttm'][('hkex.csv', 'adt_hkdbn')].get(m, np.nan))][-13:],
                   title='现货 ADT（12 个月滚动合计同比）', note='12 个月滚动合计同比。')],
        'notes': ['<b>同比口径。</b>本页混用单月与 12 个月滚动合计两种口径。']})

    # 路径 B：滚动那一侧由 **§6.2 名单注入**（`ROLLING_OK`）。这条路径是真实快照上
    # 唯一走得通的那条 —— 名单上那五张全是横截面图，回源永远对不齐。少了这个用例，
    # 注入那几行就是没测过的代码。下面三条共用同一张页，只换页尾 notes，
    # 把「点名」的两个条件拆开各测一次，再加一条写对了的反例。
    def apac_mix(notes):
        return {'exhibits': [
            yoy_ex(17, 'sgx.csv', 'sec_turnover_sgdmn', 'mom', w,
                   title='量的增速（单月同比）', note='本图用单月同比。'),
            _wl_stub(5, 'Three years'), _wl_stub(15, 'Price-volume bridge')],
            'notes': notes}

    # B-1：note 谈了滚动，但一个图号都没点 → 必须报
    expect('R3_mixed_caliber_unnamed',
           apac_mix(['<b>同比口径。</b>本页并存单月与 12 个月滚动合计两种口径。']),
           'exchanges-apac')
    # B-2：note 点齐了图号，但那一条自己**没有**声明滚动（它说的是「单月」）——
    # 这正是本仓页尾那种长列表的形状，也正是松 `named` 会被骗过去的地方 → 必须报。
    expect('R3_mixed_caliber_unnamed',
           apac_mix(['<b>同比口径（全页只有一种：单月）。</b>'
                     'Exhibit 5、Exhibit 15、Exhibit 17：单月同比（当月对去年同月）。']),
           'exchanges-apac')
    # B-3 反例：同一条 note 既声明滚动、又点齐了图号 —— 页面写对了 → 必须不报。
    # 少了这一条，上面两条也可能是被一个「恒响」的判据测过的。
    expect_silent('R3_mixed_caliber_unnamed',
                  apac_mix(['<b>同比口径。</b>本页并存两种，逐处点名，不要跨口径比高低：'
                            'Exhibit 17 走单月同比；'
                            'Exhibit 5、Exhibit 15 走 12 个月滚动合计的同比。']),
                  'exchanges-apac',
                  why='同一条 note 既声明了滚动、又点名了 Ex5 / Ex15 → 页面写对了，'
                      'R3 必须闭嘴（上面 B-1 / B-2 证明它并不是恒不响）')

    # R4：单月，图注声明了但标题里没写
    mom_untitled = {
        'exhibits': [yoy_ex(2, 'sgx.csv', 'sec_turnover_sgdmn', 'mom', w,
                            title='证券市场成交：当月成交额',
                            note='次轴是单月同比，因为本图讲的就是单月的事。')],
        'notes': []}
    expect('R4_mom_not_in_title', mom_untitled)

    # ── 图型豁免一正一反（2026-09 补，配合 EXEMPT_KINDS 那次收窄）─────────────
    # 收窄后豁免只关掉 R4，不再整条跳过规则循环。两半都要测：
    #   · 豁免图型画滚动 → R1 照报（收窄之前这里是静默放行，五种图型全都逃掉）；
    #   · 豁免图型画单月而标题没写「单月」→ R4 仍然不报（放开会多出的那几十条 🟡
    #     是噪声；具体几条跑 `--audit` 第 ① 段，这里不抄数）。
    # 反例就是上面那条 `mom_untitled`：同一张图 kind=gs_bar 时 R4 是响的。
    expect('R1_rolling_outside_exception_list',
           {'exhibits': [dict(rolling_sgx_ex(2), kind='bridge_bar')], 'notes': []},
           'sgx')
    expect_silent('R4_mom_not_in_title',
                  {'exhibits': [dict(mom_untitled['exhibits'][0], kind='heat_matrix')],
                   'notes': []}, '_selftest',
                  why='heat_matrix 在 §6.3 的图型豁免里 → 豁免必须压住 R4'
                      '（同一张图 kind=gs_bar 时上一条用例证明 R4 是响的）')

    # ── R5 的两个用例 ──────────────────────────────────────────────────────
    # 它们的**页名必须是 ROLLING_OK 上真有的页**，否则 R5 直接跳过、永远不响 ——
    # 而「不响」正是这条规则要防的那种失明，用例自己踩进去就白写了。
    # R5 判的是自述不是数值，所以这两个用例里的 values 是什么无关紧要。
    expect('R5_whitelist_no_longer_declares_rolling', {
        'exhibits': [{'n': 4, 'kind': 'range_band', 'xlabels': ['CME', 'ICE'],
                      'title': 'Constant-basis notional, y/y — all 12',
                      'ylab': '% y/y', 'actual': [1.0, 2.0],
                      'note': '口径见页尾。'},
                     {'n': 7, 'kind': 'grouped_bars', 'xlabels': ['CME', 'ICE'],
                      'title': 'Two units, y/y', 'ylab': '% y/y',
                      'groups': [{'name': '张数口径 y/y', 'values': [1.0, 2.0]}]},
                     {'n': 8, 'kind': 'grouped_bars', 'xlabels': ['CME', 'ICE'],
                      'title': 'Contract-shrink effect, y/y', 'ylab': 'pp',
                      'groups': [{'name': '差值', 'values': [1.0, 2.0]}]}],
        'notes': []}, 'exchanges12', lvl='🟡')
    # 逐图那两条钉 🟡（与上面整页那条的 🔴 成对）：契约明写这两条不跟着升 ——
    # 它们判的是自述，而且那两种情形下页还在被扫，证据链没断。
    expect('R5_whitelist_exhibit_missing', {
        'exhibits': [{'n': 17, 'kind': 'lines', 'xlabels': ['Jan-25', 'Feb-25'],
                      'title': '量的增速：单月同比',
                      'series': [{'name': 'JPX y/y（单月）', 'values': [1.0, 2.0]}]}],
        'notes': []}, 'exchanges-apac', lvl='🟡')

    # ── ① 序列名闸门：图题在**有序列名**时也要作数（2026-09 补，一正一反）──────
    # 形状照抄真实的 `cost` Ex2：`bar_line`，图题写着「…, y/y」，`yfmt='pct0'` 在
    # **exhibit 级**，两条序列都有名字且名字里没有一个 y/y 字样。
    # 修之前：整张图 `n_series=0`，规则一条都跑不到，census 记成「这张图没有
    # 同比」—— 与真的没有同比在输出上一模一样。
    #
    # 两条用例喂的是**同一批滚动口径的真值、同一个图题、同样有名字的序列**，
    # 只差一个轴单位：比率轴 → 必须报 R1；水平值轴 → 必须不报。
    # 少了反例，判别器就可能已经退化成「图题说了同比就全登记」而没人知道 ——
    # 那会把 gs_bar 的水平值柱一并登记进来（实测那条路径上有 81 条水平值）。
    def cost_shaped(ylab, yfmt):
        return {'n': 2, 'kind': 'bar_line', 'yfmt': yfmt, 'ylab': ylab,
                'xlabels': [f'{["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(m[5:7]) - 1]}-{m[2:4]}' for m in wt],
                'title': 'SGX Securities Turnover, y/y',
                'bar': {'name': 'Core turnover (ex. block)',
                        'values': [None if not np.isfinite(x) else float(x)
                                   for x in idx['mat']['ttm'][('sgx.csv', 'sec_turnover_sgdmn')].reindex(wt)]},
                'line': {'name': 'Reported turnover', 'values': [1.0] * len(wt)}}

    expect('R1_rolling_outside_exception_list',
           {'exhibits': [cost_shaped(None, 'pct0')], 'notes': []}, 'sgx')
    expect_silent('R1_rolling_outside_exception_list',
                  {'exhibits': [cost_shaped('S$mn/month', None)], 'notes': []}, 'sgx',
                  why='同一批滚动真值、同样有名字的序列、同一个图题，只是轴是水平值'
                      '单位（S$mn/month）→ 判别器必须认定「图题说的同比不是这两条」，'
                      '不登记、不报（上一条证明换成比率轴时 R1 是响的）')

    # ── ② R5 的全局那一半：名单上的**页**这一轮扫到没有（2026-09 补，两正一反）──
    # 这两种情形从前 R1 与 R5 一起失明，输出是「🔴 0 🟡 0 / 无硬错，退出码 0」。
    # 与 `main()` 扫的那一批逐字相同（`roster.js` 是首页索引、没有 exhibits，那边
    # 也剔掉了）—— 不然这几条用例喂的页名集合与真实扫描集合对不上，反例里印出来的
    # 页数会与报告抬头的「页 N 张」互相打架。
    _all_pages = {os.path.basename(p)[:-3]
                  for p in glob.glob(os.path.join(_ROOT, 'data', '*.js'))
                  if not p.endswith('roster.js')}
    expect_pages('R5_whitelist_page_missing', _all_pages - {'exchanges12'}, True,
                 lvl='🔴',
                 why='名单上的 exchanges12 一页（带着 §6.2 五张里的三张 Ex4/7/8）'
                     '整页没扫到 —— 页文件被删掉就是这个形状；'
                     '等级必须是 🔴（CONTRACT §6.6：这一条要能让整轮停机，'
                     '🟡 不改退出码，等于只印在没人读的日志里）')
    expect_pages('R5_whitelist_page_missing',
                 (_all_pages - {'exchanges12'}) | {'exchanges-12'}, True, lvl='🔴',
                 why='页还在、图也还在，只是页名改成了 exchanges-12 —— 那三张滚动图'
                     '现在挂在一个不在 ROLLING_OK 的页名下，白名单指了个空')
    expect_pages('R5_whitelist_page_missing', _all_pages, False,
                 why=f'{len(_all_pages)} 页全扫到 → 必须闭嘴'
                     f'（上面两条证明它并不是恒不响）')

    # ── ④ 月份标签：换个分隔符不该让整张图退出判据（2026-09 补，一正一反）───────
    # `lab2month` 认不出月份 ⇒ pairs 为空 ⇒ caliber=None ⇒ R1/R2/R3 全部够不到，
    # 而输出与「口径判不出来」一模一样。这一对证明新写法认得出、且没有滥认。
    def relabel(fmt):
        ex = dict(rolling_sgx_ex(2))
        ex['xlabels'] = [fmt(m) for m in wt]
        return {'exhibits': [ex], 'notes': []}

    expect('R1_rolling_outside_exception_list',
           relabel(lambda m: f'{m[:4]}/{m[5:7]}'), 'sgx')          # 2026/07
    expect_silent('R1_rolling_outside_exception_list',
                  relabel(lambda m: f'{m[:4]}Q{(int(m[5:7]) - 1) // 3 + 1}'), 'sgx',
                  why='季度标签 2026Q3 不是月份 → lab2month 必须回 None、整张图判不出'
                      '口径（上一条证明它认得出 2026/07 这种没见过的月份写法）')

    # ── ⑤ R4 的「单月」必须修饰同比（2026-09 补，一正一反）─────────────────────
    # 收紧前：标题里任何一个「单月成交额」都能让 R4 闭嘴，哪怕那两个字修饰的是
    # 水平值。R4 的用处是告诉读者金线是拿柱子直接除出来的，一个修饰水平值的
    # 「单月」没说这件事。
    def mom_titled(title):
        return {'exhibits': [yoy_ex(2, 'sgx.csv', 'sec_turnover_sgdmn', 'mom', w,
                                    title=title, yname='y/y (RHS)',
                                    note='次轴是同比。')],
                'notes': []}

    expect('R4_mom_not_in_title', mom_titled('证券市场单月成交额'), 'sgx')
    expect_silent('R4_mom_not_in_title',
                  mom_titled('证券市场成交额（次轴：单月同比）'), 'sgx',
                  why='「单月」这次真的修饰了同比 → R4 必须闭嘴'
                      '（上一条证明「单月成交额」那种修饰水平值的写法不再算数）')

    # ── ⑥ R7：比率列的同比被画成「百分比的百分比」（2026-09 新增，两正两反）───────
    # 两对用例，每一对只差**一件事**，好让「它为什么不响」有答案：
    #   · 第一对差**口径**：同一列（真比率）、同一根轴，画相对变化 → 必报；
    #     画百分点差 → 必不报。这一票是数值证据（命中哪个矩阵）。
    #   · 第二对差**量纲**：同一列（`oi_rates_kcontracts`，`classify()` 的现成假阳性
    #     —— 名字里有 `rates`，量却是张数）、同一批相对同比，轴写 `k contracts（千）`
    #     → 必不报；把轴改成 `USD/contract` → 必报。这一票挡的正是 classify() 的
    #     词根误判：少了它，`classify()` 单独命中的 11 条里、落在 R7 射程（次轴）内的
    #     9 条「保证金余额 / OI 张数 / 利率产品 ADV / 汇率」会一起被误报成
    #     「百分比的百分比」（2026-09-02 21:5x 实测；条数随快照变，结论不变）。
    def ratio_ex(col, cal, ylab, csv='miax.csv'):
        mm = [m for m in ms if np.isfinite(idx['mat'][cal][(csv, col)].get(m, np.nan))][-24:]
        return {'exhibits': [yoy_ex(12, csv, col, cal, mm, ylab=ylab, ylab2='pp y/y',
                                    title=f'{col}（次轴：单月同比）',
                                    yname='y/y (pp, RHS)')],
                'notes': []}

    expect('R7_ratio_yoy_as_pct_change',
           ratio_ex('share_equities_pct', 'mom', '%'), 'miax', lvl='🟡')
    expect_silent('R7_ratio_yoy_as_pct_change',
                  ratio_ex('share_equities_pct', 'mompp', '%'), 'miax',
                  why='同一列、同一根 % 轴，这次画的是**百分点差** → R7 必须闭嘴'
                      '（上一条证明画成相对变化时它是响的；两条的差别只有口径本身，'
                      '文字一个字没改）')
    expect('R7_ratio_yoy_as_pct_change',
           ratio_ex('oi_rates_kcontracts', 'mom', 'USD/contract', csv='ice.csv'), 'ice')
    expect_silent('R7_ratio_yoy_as_pct_change',
                  ratio_ex('oi_rates_kcontracts', 'mom', 'k contracts（千）', csv='ice.csv'),
                  'ice',
                  why='同一列、同一批相对同比，只把主轴量纲换回它真实的 '
                      '`k contracts（千）` → 量纲这一票投「不是比率」，R7 必须闭嘴'
                      '（上一条把轴改成 USD/contract 就会响，证明它不是恒不响）；'
                      '这就是 classify() 把 `rates` 判成比率时唯一挡着它的那道闸')

    # ── ⑦ R8：近零基数上画同比而不声明（2026-09 新增，一正三反）─────────────────
    # 用真实的近零基数列 `jpx.csv:ipo_funds_jpybn`（当月 IPO 募资额，大量取 0 的月份），
    # 窗口取它自己全部算得出单月同比的月 —— 与真实页面 jpx Ex14 同一列同一段窗口。
    # 四条用例只差**一件事**，好让每一次沉默都有答案：
    #   正 ：没截轴、图注没提近零 → 必报；
    #   反1：给次轴那条线加 `ymax`（= 引擎认的右轴截轴，见 `axis_capped()`）→ 必不报；
    #   反2：图注里用一句话点名一个**现算出来的**近零月 → 必不报；
    #   反3：换一条不近零的列（sgx 成交额）、其余一模一样 → 必不报。
    # 反 3 是防「R8 退化成恒响」的那一条；反 1/反 2 各测一条补救通道。
    _NZ = ('jpx.csv', 'ipo_funds_jpybn')
    nzw = [m for m in sorted(set(idx['mat']['mom'].index))
           if np.isfinite(idx['mat']['mom'][_NZ].get(m, np.nan))]

    def nz_ex(csv, col, months, **kw):
        return yoy_ex(14, csv, col, 'mom', months,
                      title='当月募资额（次轴：单月同比）', ylab='¥bn', ylab2='% y/y',
                      **kw)

    expect('R8_near_zero_base_undeclared',
           {'exhibits': [nz_ex(*_NZ, nzw)], 'notes': []}, 'jpx', lvl='🟡')

    _capped = nz_ex(*_NZ, nzw)
    _capped['yoy'] = dict(_capped['yoy'], ymax=200.0)
    expect_silent('R8_near_zero_base_undeclared', {'exhibits': [_capped], 'notes': []},
                  'jpx',
                  why='同一列同一窗口，只给次轴那条线加了 ymax（右轴的截轴字段，'
                      '不是左轴的 ycap）→ 截轴这条补救通道必须压住 R8'
                      '（上一条证明不截轴时它是响的）')

    # 点名用的月份**现算**，不写死 —— 数据一变，写死的那个月就会悄悄不再是近零月，
    # 这条「期望不报」的用例就会变成一个测不到东西的空壳。
    _nzm = Y.near_zero_base(idx['mat']['lvl'][_NZ], win=nzw)['months'][-1]
    _nzlab = f'{list(_MON)[int(_nzm[5:7]) - 1]}-{_nzm[2:4]}'
    expect_silent('R8_near_zero_base_undeclared',
                  {'exhibits': [nz_ex(*_NZ, nzw,
                                      note=f'⚠️ 本列多个月份**基期近零**，'
                                           f'{_nzlab} 那一格尤其读不出意思：'
                                           f'分子分母都贴着零，同比读的是分母不是量。')],
                   'notes': []}, 'jpx',
                  why=f'图注里同一句既说了「基期近零」、又点名了现算出来的近零月 '
                      f'{_nzlab} → 声明义务履行了，R8 必须闭嘴')

    expect_silent('R8_near_zero_base_undeclared',
                  {'exhibits': [nz_ex('sgx.csv', 'sec_turnover_sgdmn', w)], 'notes': []},
                  'sgx',
                  why='换成一条不近零的列（sgx 证券成交额），图与文字一个字没改 → '
                      'near_zero_base 的 flag 为假，R8 必须闭嘴 —— 它认的是数值，'
                      '不是「这张图长得像不像会出事」')

    # ── ⑧ 失明清单升成 🟡（2026-09，一正一反）──────────────────────────────────
    # 正：图上挂一个 `yoy_series()` 从来没读过、又长得像数据序列的字段 → 必报 🟡。
    # 反：同一张图，把那个字段名换成 `_META_KEYS` 里已有的排版字段 → 必不报。
    # 少了反例，这条规则可能已经退化成「凡是图上有列表就喊」而没人知道。
    def blind_ex(field):
        e = dict(yoy_ex(2, 'sgx.csv', 'sec_turnover_sgdmn', 'mom', w,
                        title='证券市场成交额（次轴：单月同比）'))
        e[field] = [1.0, 2.0, 3.0]
        return {'exhibits': [e], 'notes': []}

    expect('R0_scanner_blind_field', blind_ex('shadow_line'), 'sgx', lvl='🟡')
    expect_silent('R0_scanner_blind_field', blind_ex('bar_labels'), 'sgx',
                  why='同一张图，字段名换成 `_META_KEYS` 里登记过的排版字段 '
                      '`bar_labels` → 判据知道自己不必读它，必须闭嘴'
                      '（上一条证明换成没登记过的字段名它是响的）')

    # ── ⑨ R5 停机条件的第三种形态：页在、整页解析失败（2026-09 补，一正一反）──────
    # 前面 `expect_pages` 那三条测的是「页名集合」这一层，测不到 `main()` 把**哪个**
    # 集合喂进来。三种形态里前两种（删文件 / 改文件名）从页名集合上就看得出来，
    # 第三种看不出来 —— 文件还在、路径还在，只有 payload 解析失败。
    # 所以这一对用例走**整条管道**：临时造一个只有 `data/` 的 root，把名单上那一页
    # 写成解析不了的样子，再跑 `scan_pages` + `check_whitelist_pages`。
    expect_broken('R5_whitelist_page_missing', 'exchanges12', True, lvl='🔴',
                  why='`data/exchanges12.js` 文件还在、只是整页解析失败 —— '
                      '这一轮它一条规则都没跑过，而名单上的 Ex4/7/8 就在这一页上。'
                      '修改前喂进 check_whitelist_pages 的是「文件存在」的集合，'
                      '这一页被算成「扫到了」，输出只有一条 🟡 R0_page_unreadable、'
                      '退出码 0；现在喂的是「真的解析成功并跑完规则」的集合')
    expect_broken('R5_whitelist_page_missing', '', False,
                  why='同一批临时页文件，只是没有一页坏掉 → 必须闭嘴'
                      '（上一条证明它并不是恒响）')

    print('判据自测 —— 对着已知错例跑，确认规则没死')
    print('  标「期望不报」的用例测的是**压制**还活着：白名单（§6.2）、图型豁免'
          '（§6.3）、R7 的量纲这一票，全部作用都是让某条规则闭嘴，\n'
          '  而「闭嘴」和「规则坏了」在输出上长得一样 —— 所以每条都配了一条'
          '「换个页名 / 换个 kind / 换个轴标题就该响」的正例。')
    ok = True
    for c in cases:
        if 'broken' in c:                      # 整条管道：临时 root + 一页坏文件
            with tempfile.TemporaryDirectory() as td:
                os.makedirs(os.path.join(td, 'data'))
                for pg in sorted(_all_pages):
                    body = ('window.DASH = {"exhibits": [], "notes": []};'
                            if pg != c['broken'] else
                            'window.DASH = {"exhibits": [ 这里被截断了')
                    with open(os.path.join(td, 'data', pg + '.js'), 'w',
                              encoding='utf-8') as fh:
                        fh.write(body)
                pp = scan_paths(td)
                # 与 `main()` 的接法逐字相同：喂 `checked`（真的解析成功并跑完规则
                # 的页），不是 `{basename(p) for p in pp}`。用例的价值全在这一行 ——
                # 换回后者，这条正例当场变成「不响」。
                bf, _, _, checked = scan_pages(pp, idx)
                found = bf + check_whitelist_pages(checked)
        elif 'pages' in c:                     # R5 全局那一半：喂页名集合，不喂 payload
            found = check_whitelist_pages(c['pages'])
        else:
            payload = dict(c['payload'], xlabels=c['payload']['exhibits'][0]['xlabels'])
            found, _, _ = check_payload(payload, c['page'], idx)
        rules = [x['rule'] for x in found]
        must = c['mode'] == 'must'
        hit = (c['rule'] in rules) if must else (c['rule'] not in rules)
        # 等级断言：只对「期望报」的用例做，而且只在用例明写了 lvl 时做。
        if must and hit and c.get('lvl'):
            got = {x['lvl'] for x in found if x['rule'] == c['rule']}
            if got != {c['lvl']}:
                hit = False
                c['why'] = (c['why'] + '；' if c['why'] else '') + \
                    f'⚠️ 等级不符：期望 {c["lvl"]}，实报 {sorted(got)}'
        ok &= hit
        # 「期望不报」的用例必须和「期望报」的一样逐条印出来 —— 悄悄跳过的断言
        # 等于没有断言，那正是这个文件反复在防的那种失明。
        print(f'  {"✅" if hit else "❌"} {"期望报  " if must else "期望不报"} '
              f'{c["rule"]:42s} [{c["page"]}]'
              + (f' {c["lvl"]}' if c.get('lvl') else '')
              + f' 实报 {rules or "（无）"}'
              + (f'\n        └ {c["why"]}' if c['why'] else ''))
    print(f'  {len(cases)} 个用例（期望报 {sum(1 for c in cases if c["mode"] == "must")}、'
          f'期望不报 {sum(1 for c in cases if c["mode"] == "must_not")}）：'
          + ('全部通过' if ok else '**失败** —— 有规则不再触发、压制失效、'
                                  '或等级被改动了，先修判据再看报告'))
    return 0 if ok else 1


# ── 扫描 ────────────────────────────────────────────────────────────────────
def scan_paths(root, only=None):
    """这一轮要扫的页文件。`only` = `--page` 给的页名（不带 .js）。"""
    paths = sorted(glob.glob(os.path.join(root, 'data', '*.js')))
    paths = [p for p in paths if not p.endswith('roster.js')]  # 首页索引，无 exhibits
    if only:
        want = set(only)
        paths = [p for p in paths if os.path.basename(p)[:-3] in want]
    return paths


def scan_pages(paths, idx):
    """扫一批页 → (findings, items, census, **checked**)。
    **`main()` 与 `--audit` 共用这一条路径** —— 两边各写一遍循环，就会在
    「哪一页算数、坏页怎么办」上分头漂，而 `--audit` 的全部意义就是
    「与被引用处用同一个分母」。

    ⚠️ **第四个返回值 `checked` 是 2026-09 补的，它修的是 R5 停机条件的一个洞。**
    从前 `main()` 拿 `{basename(p) for p in paths}` 去喂 `check_whitelist_pages()`
    —— 那是**文件存在**的集合，不是**这一轮真的查过**的集合。名单页丢失有三种形态，
    从前只有两种会响（构造验证见 `check_whitelist_pages()` 的 docstring 与
    `--selftest` 里那三条 `expect_pages` / 一条 `expect_broken`）：

      | 形态 | 从前 | 现在 |
      |---|---|---|
      | 页文件被删          | 🔴 响（不在 paths 里）      | 🔴 响 |
      | 页文件被改名        | 🔴 响（页名变了）            | 🔴 响 |
      | **页在、整页解析失败** | **不响**：路径还在 paths 里，被算成「扫到了」，只报一条 🟡 `R0_page_unreadable`，退出码 0 | 🔴 响 |

    第三种才是最危险的一种：文件还躺在那里，`git status` 干净，人不会怀疑；
    而 `ROLLING_OK` 名单上那几张图这一轮**一条规则都没跑过**。
    R5 那条 🔴 的全部理由是「除了它没有任何东西会响」（CONTRACT §6.6），
    而它自己当时挂在一个答非所问的条件上 —— 挂「文件在不在」，答的却该是
    「这一页的 payload 这一轮进没进过规则循环」。

    `checked` 只收**成功解析并跑完规则**的页名（不带 `.js`），与 findings 里
    每一条的 `page` 字段同一种写法。
    """
    allf, alli, allc, checked = [], [], [], set()
    for p in paths:
        page = os.path.basename(p)[:-3]
        try:
            f, i, c = check_page(p, idx)
        except Exception as e:                    # 一页坏掉不该拖垮整次扫描
            # ⚠️ `page` 这里从前写的是 `os.path.basename(p)`（**带 .js**），
            # 与其余每一条 finding 的写法都不一样；任何按 page 去对账的代码
            # （包括下面 `checked` 的相减）都会因此对不上。2026-09 统一。
            allf.append(dict(lvl='🟡', rule='R0_page_unreadable', page=page,
                             n=None, title='', msg=f'读不出来：{type(e).__name__}: {e}'))
            continue
        allf += f
        alli += i
        allc += c
        checked.add(page)
    return allf, alli, allc, checked


@contextlib.contextmanager
def _rebound(**kw):
    """临时改几个模块常量再改回去 —— `--audit` 的「如果那道闸门不在」靠它。

    规则体读的都是模块全局（调用时才取值），所以重新绑定就够了；`finally` 保证
    审计跑完之后常量恢复原样，本次进程里后续的扫描不受影响。
    """
    old = {k: globals()[k] for k in kw}
    globals().update(kw)
    try:
        yield
    finally:
        globals().update(old)


def audit(paths, idx):
    """当场重算注释里那几个「放开这道闸门会多出多少」的数。

    **为什么要有这个模式**：本文件每一道闸门都配着一句「放开它会多出多少条」，
    而那种数随 `data/` 快照变。写死过两次、过期过两次 —— 第二次是在**订正第一次的
    同一个编辑里**过期的（`values` 路径加了 `ratio_axis()` 闸门，`bridge_bar`
    那一档当场归零，而刚写下的 68 = 36+26+6 还带着那 26）。所以现在注释里一个数都
    不留，只留「跑 `--audit`」；分母写在代码里，比写在注释里难漂。

    印的四段，对应四处注释：
      ① `EXEMPT_KINDS`（§6.3 图型豁免）—— 分母与契约 §6.3 规定的重跑方法逐字相同：
         置空之后多出来的 finding，按 rule / kind / 图张数分档。
      ② `legal_mom`（存量与比率的 R4 豁免）—— 从 items 直接算，不必重扫：
         把 `not legal_mom` 这一项从 R4 的条件里拿掉，会多报哪几条。
      ③ 回源容差一刀切放大（`MATCH_TOL_PP` 与 `MAX_ROUND_TOL_PP` 同时设成 0.05 / 0.5）
         —— 判出口径的条数怎么变、谁从命中退成歧义、谁新认到一列。
      ④ 登记门槛 `MIN_SERIES_PTS` 调回 `MIN_MATCH_PTS` —— 会丢掉哪些序列。
    """
    base_f, base_i, base_c, _ = scan_pages(paths, idx)
    kinds = {(c['page'], c['n']): c['kind'] for c in base_c}
    key = lambda x: (x['page'], x['n'], x['where'], x['name'])          # noqa: E731
    fkey = lambda f: (f['rule'], f['page'], f.get('n'), f.get('msg', '')[:40])  # noqa: E731

    print('=' * 86)
    print(f'判据闸门审计 —— {len(paths)} 页 / exhibit {len(base_c)} 张 / '
          f'登记到的同比序列 {len(base_i)} 条 / 回源索引 {len(idx["keys"])} 列')
    print('这些数**都是这一刻的读数**，不是常量：注释里引用它们的地方一律只写'
          '「跑 --audit」，不抄数。')
    print('=' * 86)

    def delta(tag, findings, note=''):
        base = {fkey(f) for f in base_f}
        new = [f for f in findings if fkey(f) not in base]
        gone = [f for f in base_f if fkey(f) not in {fkey(x) for x in findings}]
        by_rule, by_kind = {}, {}
        for f in new:
            by_rule[f['rule']] = by_rule.get(f['rule'], 0) + 1
            k = kinds.get((f['page'], f.get('n')), '(页级)')
            by_kind[k] = by_kind.get(k, 0) + 1
        print(f'\n【{tag}】新增 finding {len(new)} 条、消失 {len(gone)} 条'
              + (f'  —— {note}' if note else ''))
        if by_rule:
            print('   按 rule： ' + ' / '.join(f'{k} {v}' for k, v in sorted(by_rule.items())))
            print('   按 kind： ' + ' / '.join(f'{k} {v}' for k, v in sorted(by_kind.items())))
            print(f'   影响的图 {len({(f["page"], f.get("n")) for f in new})} 张')
        for f in new[:6]:
            print(f'     · {f["lvl"]} {f["rule"]} {f["page"]} Ex{f.get("n")}')
        if len(new) > 6:
            print(f'     …（其余 {len(new) - 6} 条同形；要逐条看就把这道闸门'
                  f'在一份仓外副本里关掉、再跑一次带 --json 的全量扫描）')

    # ① 图型豁免
    with _rebound(EXEMPT_KINDS=set()):
        delta('① EXEMPT_KINDS 置空（§6.3 图型豁免全放开）', scan_pages(paths, idx)[0],
              note='豁免今天只关掉 R4，所以多出来的应当全是 R4')

    # ② 存量 / 比率豁免（legal_mom）—— 不必重扫，条件就在 items 里
    would = [x for x in base_i
             if x['legal_mom'] and not x['exempt'] and not x['declared']['mom_in_title']
             and (x['match']['caliber'] == 'mom'
                  or (x['declared']['mom_anywhere'] and not x['declared']['roll_anywhere']))]
    print(f'\n【② legal_mom 豁免（存量点对点 / 比率百分点差）】拿掉它会多报 '
          f'{len(would)} 条 R4：比率 {sum(1 for x in would if x["is_ratio"])} 条、'
          f'存量 {sum(1 for x in would if x["is_stock"] and not x["is_ratio"])} 条')
    # 比率那一档逐条印（就那么几条，而且注释里点名举例的正是它们）；存量那一档
    # 是几十条同形的 OI / AUM / 余额，印头几条示形，其余只给条数。
    ratio_side = [x for x in would if x['is_ratio']]
    stock_side = [x for x in would if not x['is_ratio']]
    for x in ratio_side + stock_side[:4]:
        print(f'     · {x["page"]} Ex{x["n"]} {x["where"]}「{x["name"]}」'
              f'回源 {x["match"]["csv"]}:{x["match"]["col"]}'
              f'（{"比率" if x["is_ratio"] else "存量"}）')
    if len(stock_side) > 4:
        print(f'     …（存量那一档其余 {len(stock_side) - 4} 条同形：OI / AUM / '
              f'托管量 / 余额，点对点同比是它们唯一合法的口径）')

    # ③ 回源容差一刀切放大
    print('\n【③ 回源容差一刀切放大】自适应容差按每条序列的书写刻度定'
          '（见 `_tol_for()`）；这里把两个常数同时钉成一个值，看代价：')
    b = {key(x): x for x in base_i}
    q = {}
    for x in base_i:
        q[x['write_k']] = q.get(x['write_k'], 0) + 1
    print('   序列的书写刻度分布（k 位小数，None = 多于 6 位即原始浮点）：'
          + ' / '.join(f'k={k} {v}' for k, v in
                       sorted(q.items(), key=lambda t: (t[0] is None, t[0]))))
    # k=0（整数刻度）的那几条是 `MAX_ROUND_TOL_PP` 唯一约束得到的序列 —— 逐条印出来，
    # 好让那条注释里「今天一条都没约束到」这句话可核对。
    ints = [x for x in base_i if x['write_k'] == 0]
    print(f'   其中写成整数刻度（k=0，容差会被放宽到上限 {MAX_ROUND_TOL_PP}pp）的 '
          f'{len(ints)} 条：'
          + ('；'.join(f'{x["page"]} Ex{x["n"]}「{x["name"]}」→ '
                       + (f'{x["match"]["csv"]}:{x["match"]["col"]}'
                          f'（误差 {x["match"]["err"]:.2g}pp）'
                          if x['match']['caliber'] else '判不出')
                       for x in ints) or '（无）'))
    for tol in (0.05, 0.5):
        with _rebound(MATCH_TOL_PP=tol, MAX_ROUND_TOL_PP=tol):
            cur = {key(x): x for x in scan_pages(paths, idx)[1]}
        newly = [(k, v) for k, v in cur.items()
                 if v['match']['caliber'] and k in b and not b[k]['match']['caliber']]
        lost = [(k, b[k]) for k, v in cur.items()
                if not v['match']['caliber'] and k in b and b[k]['match']['caliber']]
        moved = [k for k, v in cur.items()
                 if k in b and v['match']['caliber'] and b[k]['match']['caliber']
                 and v['match']['col'] != b[k]['match']['col']]
        print(f'   tol={tol}pp：判出口径 '
              f'{sum(1 for v in cur.values() if v["match"]["caliber"])} 条'
              f'（原 {sum(1 for v in b.values() if v["match"]["caliber"])}）；'
              f'新认出 {len(newly)}、退成判不出 {len(lost)}、换了列 {len(moved)}')
        for k, v in newly[:4]:
            print(f'       + {k[0]} Ex{k[1]} {k[2]}「{k[3]}」→ '
                  f'{v["match"]["csv"]}:{v["match"]["col"]}（误差 {v["match"]["err"]:.3g}pp）')
        for k, v in lost[:4]:
            print(f'       − {k[0]} Ex{k[1]} {k[2]}「{k[3]}」原命中 '
                  f'{v["match"]["csv"]}:{v["match"]["col"]}，现在多列候选、判不出')

    # ④ 登记门槛
    with _rebound(MIN_SERIES_PTS=MIN_MATCH_PTS):
        tight = {key(x) for x in scan_pages(paths, idx)[1]}
    dropped = [x for x in base_i if key(x) not in tight]
    by_kind = {}
    for x in dropped:
        by_kind[x['chart_kind']] = by_kind.get(x['chart_kind'], 0) + 1
    print(f'\n【④ 登记门槛调回 MIN_MATCH_PTS={MIN_MATCH_PTS}】会丢掉 {len(dropped)} 条'
          f'已登记的同比序列：' + ' / '.join(f'{k} {v}' for k, v in sorted(by_kind.items())))
    print(f'   其中在 §6.2 名单（ROLLING_OK）上的图 '
          f'{len({(x["page"], x["n"]) for x in dropped if (x["page"], x["n"]) in ROLLING_OK})} 张'
          f' —— 这正是当初「白名单是死代码」的成因。')
    print('\n审计只读不写，退出码恒 0（它不是判据，是判据的度量衡）。')
    return 0


# ── 报告 ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description='同比口径判据（CONTRACT.md §6）')
    ap.add_argument('--root', default=_ROOT)
    ap.add_argument('--page', action='append', help='只查某几页（不带 .js）')
    ap.add_argument('--json', help='机器可读结果写到这个路径；不给就不写文件'
                                   '（默认不往仓库里丢产物）。`-` = 打到 stdout')
    ap.add_argument('--verbose', action='store_true', help='逐条列出口径未确定的图')
    ap.add_argument('--selftest', action='store_true',
                    help='只跑判据自测（对着已知错例确认每条规则都还会响，并反向确认'
                         '白名单 / 图型豁免 / 量纲这几处压制没失效），不扫 data/')
    ap.add_argument('--audit', action='store_true',
                    help='当场重算注释里那几个「放开这道闸门会多出多少」的数'
                         '（图型豁免 / 存量·比率豁免 / 回源容差 / 登记门槛），不写文件')
    a = ap.parse_args()

    idx = build_index(a.root)
    if a.selftest:
        return selftest(idx)

    paths = scan_paths(a.root, a.page)
    if a.audit:
        return audit(paths, idx)

    allf, alli, allc, checked = scan_pages(paths, idx)

    # R5 的全局那一半：名单上的**页**这一轮**真的查过没有**。必须在这里做而不是在
    # `check_page` 里 —— 页文件没了就没有哪一次 `check_page` 会轮到它（见
    # `check_whitelist_pages()` 的构造验证）。`--page` 划了范围时不跑：那是使用者
    # 自己缩的圈，不是名单坏了。
    # ⚠️ 喂进去的是 `checked`（成功解析并跑完规则的页）而不是
    # `{basename(p) for p in paths}`（文件存在的页）。差别只在一种形态上，
    # 而那一种正是最不容易被人发现的：页文件还在、整页解析失败。见 `scan_pages()`。
    if not a.page:
        allf += check_whitelist_pages(checked)

    red = [x for x in allf if x['lvl'] == '🔴']
    yel = [x for x in allf if x['lvl'] == '🟡']
    live = [x for x in alli if not x['exempt']]
    det = [x for x in live if x['match']['caliber']]
    print('=' * 86)
    print('同比口径判据 —— data/*.js 快照')
    print('=' * 86)

    # ── 图数量的账，按 exhibit 记（不是按「读到了几条序列」记）─────────────────
    # 这三行是 2026-08-07 补的。老版本只有「同比序列 N 条（豁免 M 条）」一行，
    # 而 M 是**豁免图里被读到的序列数** —— 一张图一条都没读到时它就凭空消失了，
    # 于是「判据没读」被印成了「豁免 0 条」。现在豁免 / 读到 / 没读到分三栏印。
    ex_all, ex_ex = len(allc), [c for c in allc if c['exempt']]
    ex_ex_read = [c for c in ex_ex if c['n_series']]
    ex_kinds = {}
    for c in ex_ex:
        ex_kinds.setdefault(c['kind'], [0, 0])
        ex_kinds[c['kind']][0] += 1
        ex_kinds[c['kind']][1] += bool(c['n_series'])
    blind = [c for c in allc if c['blind']]
    print(f'页 {len(paths)} 张；exhibit {ex_all} 张，其中豁免图型 {len(ex_ex)} 张'
          f'（{" / ".join(f"{k} {v[0]}" for k, v in sorted(ex_kinds.items()))}）')
    # 回源索引的规模现印一行 —— 从前它写在 `build_index()` 的 docstring 里
    # （「约 580 列」），等 series/ 一扩容就成了假话，而没人会去重跑一遍确认。
    print(f'回源索引 {len(idx["keys"])} 列（`series/*.csv` 里够长的数值列，'
          f'每列按单月 / 12 个月滚动 / 百分点差三种口径各算一遍）')
    print(f'  └ 豁免图里读出同比序列的 {len(ex_ex_read)} 张、'
          f'一条也读不出的 {len(ex_ex) - len(ex_ex_read)} 张'
          f'（横轴不是月，回源无从对齐 —— 与「判据不认识这个字段」不是一回事）')
    print(f'同比序列 {len(alli)} 条（其中图型豁免 {len(alli) - len(live)} 条 —— '
          f'豁免只关掉 R4，R1/R2 照跑，见 §6.3 与 EXEMPT_KINDS 上方那段）')
    print(f'口径回源确定 {len(det)} 条'
          f'（滚动 {sum(1 for x in det if x["match"]["caliber"] == "ttm")} / '
          f'单月 {sum(1 for x in det if x["match"]["caliber"] == "mom")}）；'
          f'未确定 {len(live) - len(det)} 条 —— 派生量 / 跨源合成，判据不下结论')
    # 豁免图型那一侧单印一行。R1/R2 只对「回源确定命中滚动」的那一档开口，所以
    # 这一行的第一个数字就是「豁免图型里现在会不会响」的全部答案 ——
    # 印出来，好让「今天 0 条」是可核对的 0，而不是又一个看不见的静默。
    exm = [x for x in alli if x['exempt']]
    print(f'  └ 豁免图型的 {len(exm)} 条里，回源确定命中滚动 '
          f'{sum(1 for x in exm if x["match"]["caliber"] == "ttm")} 条（R1/R2 只对这一档开口）'
          f'、命中单月 {sum(1 for x in exm if x["match"]["caliber"] == "mom")} 条'
          f'、判不出 {sum(1 for x in exm if not x["match"]["caliber"])} 条')
    if blind:
        print(f'\n⚠ 判据读不到的数据字段 {len(blind)} 张图 —— **这是判据自己的缺陷，'
              f'不是页面的问题**，先补 yoy_series() 再看下面的结论'
              f'（2026-09 起同时进 🟡 `R0_scanner_blind_field`，'
              f'不再只印这一段 —— 理由见 `check_payload` 里那段注释）：')
        for c in blind[:20]:
            print(f'    {c["page"]} Ex{c["n"]}（{c["kind"]}）未扫描字段 {c["blind"]} '
                  f'— {c["title"][:48]}')
    else:
        print('判据未扫描到的数据字段：0 —— 每张图上长得像数据序列的字段都进过 '
              'yoy_series()（这个 0 是会响的：非空时报 🟡 R0_scanner_blind_field，'
              '`--selftest` 里有一正一反两条用例钉着）')

    # 「因为判据猜它是存量而被关掉 R1/R4」的单月同比。不计入 🔴/🟡（判据自己拿不准
    # 就不该硬判），但必须印出来 —— 否则它和「这张图合规」在输出上又长得一样了。
    weak = [x for x in live if x.get('weak_exempt')]
    hid = [x for x in weak if x.get('hidden_rule')]
    if weak:
        print(f'\n⚠ 单月同比被「判据猜它是存量」挡掉 R4 的 {len(weak)} 条 —— '
              f'yoy.classify() 对这些列名四条正则一条都没命中，走的是最后一行的兜底 '
              f'`return STOCK`。对生成器那是安全默认，在判据里方向相反：'
              f'一个「我不知道」被当成了「它合法」。')
        print(f'  （藏不住 🔴：这些序列回源命中的都是**单月**口径，而 R1/R2 只对'
              f'滚动口径开口。但它关掉的不止 R4 —— `legal_mom` 同样把这条序列从 '
              f'R3 的**单月那一侧**踢出去（check_page_mix 的 '
              f'`if it["exempt"] or it["legal_mom"]: continue`），'
              f'所以一页上若只剩这类序列充当单月侧，R3 也会跟着闭嘴。）')
        print(f'  其中 {len(hid)} 条一旦确认是流量就会当场变成 🟡 R4'
              f'（其余 {len(weak) - len(hid)} 条标题里已写明单月，豁免与否结果一样）。'
              f'「符号相反 N 月」是旁证不是规则：它说这条线换成滚动口径会差多少，'
              f'差得多的更值得先看：')
        for x in sorted(hid, key=lambda z: -z.get('sign_flips', 0)):
            print(f'    [R4?] {x["page"]} Ex{x["n"]} {x["where"]}'
                  f'「{x["name"]}」回源 {x["match"]["csv"]}:{x["match"]["col"]}'
                  f'（符号相反 {x.get("sign_flips", 0)} 月）'
                  f' — {x["title"][:44]}')

    # ── 另一条会静默关掉 R4 的路：图题里出现存量词根（`says_stock` 独木桥）────────
    # 与上面那一段是同一类事（一条豁免悄悄关掉一条规则），但成因相反：上面那条是
    # `classify()` 兜底猜了存量，这一条是**文字说自己是存量**，而被它关掉的 R4
    # 恰恰是一条查文字的规则 —— 拿被检查的对象当证据，而且从前完全看不见。
    # （判据里读文字的地方不止这一处，但别处读的都是「被判的那句话本身」：
    # R2 判措辞、R5 判自述、R4 的降级回退只加不减、R8 判有没有点名。
    # 这一处不一样 —— 它拿标题里**另一个**词，去关掉一条查这段标题的规则。）
    # 收紧与否的取舍写在 `check_payload` 里 `text_only_stock` 上方；
    # 这里负责让它不再静默。
    tos = [x for x in live if x.get('text_only_stock')]
    if tos:
        contra = [x for x in tos if x.get('stock_contradicted')]
        print(f'\n⚠ R4 被「图题里出现存量词根」单独关掉的 {len(tos)} 条 —— '
              f'`_STOCK_TXT`（市值 / 月末 / 余额 / 期末 / 未平仓…）命中图题，'
              f'而列名正则与「无歧义存量」两票都没投。')
        print(f'  这一处是**拿被检查的对象当证据**：R4 查的就是「这段标题里写没写'
              f'单月」，而同一段标题里的另一个词把它整条关掉了。'
              f'不报 🟡 是因为收紧会误伤（详见代码注释里逐条读过的名单）；'
              f'印出来是因为它不该继续静默。')
        print(f'  其中 {len(contra)} 条**回源命中的列名说它是流量**'
              f'（两侧正面冲突，最值得先看一眼；冲突不等于文字错 —— '
              f'也可能是 `yoy.classify()` 的词根判错了）：')
        for x in contra:
            print(f'    [文字存量 vs 回源流量] {x["page"]} Ex{x["n"]} {x["where"]}'
                  f'「{x["name"]}」回源 {x["match"]["csv"]}:{x["match"]["col"]}'
                  f' — {x["title"][:52]}')
        rest = [x for x in tos if not x.get('stock_contradicted')]
        for x in rest:
            print(f'    [回源判不出列，无从对质] {x["page"]} Ex{x["n"]} {x["where"]}'
                  f'「{x["name"]}」 — {x["title"][:52]}'
                  if not x['match']['caliber'] else
                  f'    [文字存量，回源不反对] {x["page"]} Ex{x["n"]} {x["where"]}'
                  f'「{x["name"]}」回源 {x["match"]["csv"]}:{x["match"]["col"]}'
                  f' — {x["title"][:52]}')
    print(f'🔴 {len(red)}   🟡 {len(yel)}')
    if not red:
        # 「今天没报错」与「规则坏了」在输出上长得一样，必须能分开。
        print('（无 🔴。规则是否还活着请跑 --selftest —— 它对着已知错例逐条验规则，'
              '并且反向验白名单 / 图型豁免 / R7 的量纲这几处「压制」也没失效；'
              '几道闸门各自的代价跑 --audit 当场重算）')

    for lvl, rows in (('🔴', red), ('🟡', yel)):
        if not rows:
            continue
        print('\n' + '-' * 86)
        print(f'{lvl} {len(rows)} 条')
        print('-' * 86)
        for r in rows:
            head = f'{r["page"]}' + (f' Ex{r["n"]}' if r['n'] else '')
            print(f'{lvl} [{r["rule"]}] {head} — {r["title"][:70]}')
            print(f'     {r["msg"]}')

    if a.verbose:
        und = [x for x in live if not x['match']['caliber']]
        print('\n' + '-' * 86)
        print(f'口径未确定的 {len(und)} 条（只列不报 —— 宁可漏报不制造噪声）')
        print('-' * 86)
        for x in und:
            print(f'   {x["page"]} Ex{x["n"]} {x["where"]}「{x["name"]}」'
                  f'（{x["match"]["n"]} 个可比点）— {x["title"][:56]}')

    payload = {'summary': {'pages': len(paths), 'pages_parsed': len(checked),
                           'series': len(alli),
                           'exempt': len(alli) - len(live), 'determined': len(det),
                           'exhibits': ex_all, 'exhibits_exempt': len(ex_ex),
                           'exhibits_exempt_read': len(ex_ex_read),
                           'exhibits_unscanned_fields': len(blind),
                           # 「R4 被图题里的存量词根单独关掉」的条数。进 summary 是为了
                           # 让这条通道在**机器可读的输出**里也有一行 —— 只印在 stdout
                           # 的东西，下游拿 --json 的人看不见（③ 的教训就是这个形状）。
                           'text_only_stock': sum(1 for x in live
                                                  if x.get('text_only_stock')),
                           'stock_contradicted': sum(1 for x in live
                                                     if x.get('stock_contradicted')),
                           'red': len(red), 'yellow': len(yel)},
               'census': allc,
               'params': {'MATCH_TOL_PP': MATCH_TOL_PP, 'MIN_MATCH_PTS': MIN_MATCH_PTS,
                          'MAX_ROUND_TOL_PP': MAX_ROUND_TOL_PP,
                          'MIN_SERIES_PTS': MIN_SERIES_PTS,
                          'SIGN_DEADBAND_PP': SIGN_DEADBAND_PP,
                          'EXEMPT_KINDS': sorted(EXEMPT_KINDS)},
               'findings': allf, 'items': alli}
    if a.json == '-':
        print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
    elif a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=1, default=str)
        print(f'\n机器可读结果 → {a.json}')

    print('\n' + ('🔴 有硬错，退出码 1' if red else '无硬错，退出码 0'))
    return 1 if red else 0


HOW_TO_WIRE_IN = """
接进 build/payload_guard.py 的建议改法（等 10 个 agent 的改动落定后再做）
─────────────────────────────────────────────────────────────────────────
1. 不要在 payload_guard 里 import 本文件。payload_guard 现在只依赖 json/re/os，
   本文件依赖 pandas + numpy + `build/yoy.py` + `build/single.py`（R7 要用它的
   `unit_is_ratio()`），还要全量读 series/*.csv（2026-09-02 复测：建索引 0.6s、
   全站一轮 3.7s；这两个数随 `series/` 与页数长，引用前重跑，别当常量）。
   让**每一个** builder 在写文件时都付这笔开销、并且多背两个第三方依赖，不划算。
   ⚠️ 尤其是 `single` 这一条：payload_guard 被 builder import，而 `single` 自己就是
   底座 —— 反向 import 会绕出一个环。判据在仓外跑，没有这个问题。
   改法：把 `identify()` 需要的东西前移 —— 让 builder 在算同比时就走
   `build/yoy.py`，并把口径以**结构化字段**写进 payload：

       ex['caliber'] = 'ttm' | 'mom'        # 必填，来自 yoy.py 的哪个函数
       ex['caliber_src'] = 'db1.csv:oi_bund_contracts'   # 可选，回源用

   有了这个字段，payload_guard 侧的检查退化成纯字符串/结构判断，零依赖、零耗时：
     · 有 yoy 序列却没有 caliber 字段 → 报错（堵住「又抄了一份」）
     · caliber == 'mom' 而 title 里没有「单月 / single-month」→ 报错
     · caliber == 'ttm' 而 caliber_src 命中 yoy._STOCK_PAT → 报错
     · 同页出现两种 caliber，而 notes 里没有逐个 Exhibit 点名 → 报错
   本文件（回源复算那一半）保留为**离线校验**：CI / monthly_run 收尾各跑一次，
   负责验证 `ex['caliber']` 这个自述字段没有说谎。自述字段能被改坏，回源复算不能。

2. 挂在哪：`payload_guard.write_dash()` 里 `check(payload)` 之后、`json.dumps` 之前，
   加一句 `check_caliber(payload, gen)`，沿用 `PayloadGuardError`（它已经是
   SystemExit 子类，monthly_run 那边看到的仍是「returncode != 0 → FAIL」）。

3. 灰度：先只对 `ex['caliber']` 缺失**且**页面已经出现过两种口径的页报错，
   其余只 warn（stderr）。等 28 页全部补上 caliber 字段，再把 warn 提成 error。
   一次性全量报错会把 28 页同时打成 FAIL，那天谁也别想 build。

4. 本文件的规则里，**R1 / R2 / R3 / R7 都不要**搬进 payload_guard：
   R1（回源复算命中 12 个月滚动口径）与 R2（存量列被称作「滚动合计」）都要先读全量
   `series/*.csv` 把两种口径算一遍才判得了，属于离线校验的活；R3 的滚动那一侧同样
   一半来自回源复算（另一半来自 `ROLLING_OK`）；**R8 同理搬不动** —— 它要拿
   `yoy.near_zero_base()` 在**水平值原列**上算「窗口内有几个月基期贴着零」，
   guard 侧手上只有 payload 那条同比线，反推不出基期；R7（比率列画成「百分比的百分比」）
   更是只能离线判 —— 它要拿图上的数去比对**同一列的两种单月同比**（相对变化 vs
   百分点差），命中哪一条是数值说了算，guard 侧没有那两条曲线可比。
   （guard 侧真要管这一类，方向不是搬 R7，是让底座**别算错**：`build/single.py` 的
   `col_is_ratio()` 已经是全底座唯一的比率判据，guard 能查的是「比率列的同比字段
   有没有走那条路」，那是结构检查，不是回源。）
   能搬的是 R4（`caliber == 'mom'` 而标题没写「单月」，纯字符串）与 R5 的**逐图**
   那一半（`ROLLING_OK` 上的图还在不在、还自不自称滚动，纯结构 + 字符串）。
   ⚠️ R5 的**全局**那一半（`check_whitelist_pages()`：名单上的整页扫到没有）
   **搬不进 payload_guard** —— 它判的是「这一轮扫完之后，名单上还有哪一页没出现过」，
   而 guard 是逐页调用的，天生看不到全局。那一半只能留在这个离线判据里，
   由 CI / monthly_run 收尾那次全量扫描来跑。这正是它当初失明的同一个原因，
   别再把它塞回逐页的循环里。
   若照第 1 条把 `ex['caliber']` 写进 payload，R1/R2/R3 也能在 guard 侧退化成
   纯字符串判断 —— 但那时判的是**自述**，本文件这一份（回源复算）必须继续跑，
   它的职责恰恰是验证那个自述字段没有说谎。

5. 调用约定：`check_page(path, idx)` / `check_payload(payload, page, idx)` /
   `sign_flips(m, months, idx)` 的 `idx` 都是**参数**，`build_index(root)` 建一次
   传下去就行，不依赖任何模块全局。（2026-09 之前 `sign_flips` 读的是只有 `main()`
   才赋值的 `_IDX`，外部调用方一进 `weak_exempt` 分支就 NameError —— 那是这里
   本来就打算接的调用方式，所以那条依赖当时是坏的。）
"""

if __name__ == '__main__':
    sys.exit(main())
