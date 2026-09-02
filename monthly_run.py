# -*- coding: utf-8 -*-
"""总仓月度 routine —— 逐家检查新数据 → 重生成看板 → 一次性提交推送。

用法:
    python3 monthly_run.py                    # 正常执行（有新数据才提交推送）
    python3 monthly_run.py --only cme,cboe    # 只跑指定几家
    python3 monthly_run.py --dry-run          # 抓取与生成都做，但不 commit/push
    python3 monthly_run.py --force            # 数据没变也重新生成并推送（改了图表代码后用）

跑的东西分三类，删一家只动第一类的一行（完整清单见 docs/CRON_WIRING.md）：
    TICKERS   28 家有自己数据源的公司（11 家其它 + 7 家台湾半导体 + 10 家新交易所），
              逐家抓 → 逐家生成
    公共表    三张，都**不是 ticker**、都不进 TICKERS，各自一步：
              fee_rates    季度费率，六个单公司页共用 → 有新季度就重跑那六页
              mops_remarks MOPS 備註原文，七个半导体页共用 → 有新月份就重跑那七页
              fx           月度汇率，横截面页共用     → 不重跑任何页（build_cross 紧随其后）
    CROSS     6 张横截面页，没有自己的数据源，等成员更新完之后无条件重生成

输出：每家一行 "<ticker> <状态> <说明>"，stdout **最后一行**是总状态，供调度任务判断：
    NOTHING_TO_DO                 所有家都没有新数据（正常，等下次）
    PUBLISHED <sha> <n> <月份串>  有 n 家更新并已推送
    PARTIAL <sha> <n> ok / <m> fail   有更新也有失败，已推送成功的那部分
    FAILED <why>                  一家都没成功，或工作树不干净 / push 失败

每家的状态（第二列）:
    NEW <月>        抓到新月份并已重生成
    NOCHANGE        官方还没发新数据，或数据与线上一致
    FAIL <原因>     抓取或解析失败；该家保持线上旧数据不动

## 为什么一家失败不中止全局

单公司仓库的老脚本是「一有问题就整体退出」，那时候只有一家，退出=什么都不做，代价为零。
扩到 28 家后同样的写法意味着：TSMC 官网当天抽风，CME、Cboe、HKEX 三家已经抓到的新数据也一起
不发布 —— 一家的故障惩罚了另外二十七家。所以这里改成**逐家隔离**：失败的那家跳过（线上仍是它
自己的旧数据，不会变成错数据），成功的照常发布，失败清单打在总状态里让人看得见。
10 家新交易所随时可能被用户删掉，这条隔离对它们尤其要紧：删剩的残渣最多让一家 FAIL，
不会让另外二十七家停发。

三张公共表走的是**同一条原则的另一半**：它们不属于任何一家，失败时也不阻断本轮
（否则一张附表就能让 34 张页面全部不发），但失败必须计入末行的 PARTIAL ——
它们的故障在页面上是**看不见**的（fx 只让换算偏一点、mops_remarks 只让七页少一句
引文与一列），末行是唯一的故障信号。

## 四道体检闸门（2026-09 补接了后三道；任何一道不过 = 整轮不发，末行 FAILED）

preflight（跑在下载之前，查的都是**配置与代码**，与本轮数据无关）:
    build/check_specs.py    定基名义额的常数表（原本就接着）
    build/test_guards.py    payload_guard / brief 两条护栏的单元测试
收尾（34 页全部生成完、commit 之前，查的是**产物** `data/*.js`）:
    build/verify_pages.py         页面壳取得到、payload 合法且自洽
    tools/check_yoy_caliber.py    同比口径（CONTRACT §6.6）—— 🔴 才算不过，🟡 只打印

分界线是「查配置/代码」还是「查产物」：后两道在 preflight 阶段只能看到**上一轮**的
`data/*.js`，在那儿跑证明不了这一轮。逐条理由与代价写在各自的调用处。
仓库里还有三个自测/校验脚本**没有**接进来，别把上面那四道读成「全站闸门都自动跑了」:
`build/verify_base_prices.py`（联网下 4MB 官方文件，它自己的文件头就明写「不进 cron」）、
`tools/visual_qa.py`（每页都要用 headless Chrome 真渲染一遍；本轮没量过它的耗时）、
`build/test_pools.py`（纯标准库、实测 0.06s，位置和 test_guards 一模一样，接得进来 ——
接后三道那一轮只改了这三个调用点，它就仍然只能靠人手敲）。

护栏保持不变，且仍然是「宁可不发也不发错」:
  · 提交范围只有 `data/` 与 `series/`；这两个目录以外有未提交改动就直接 FAILED 退出（见 guard_dirty_tree）
  · 任何一家的 fetch 解析出缺列 / 月份对不上，由该家的 fetch 模块抛异常 → 记 FAIL，不写数据
  · 页面的新鲜度只绑 payload 的 data_through（构建日期只写 data/*.js 首行注释，不进 payload）。
    抓取失败那家不写 series、不重生成，data_through 原地不动，首页按 roster 的 LAG + GRACE
    给它打红点 —— 旧数据看得出是旧的，不会被当成新的
"""
import argparse
import csv
import datetime
import glob
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
SERIES = os.path.join(HERE, 'series')
CACHE = os.path.join(HERE, 'cache')
REQUIREMENTS = os.path.join(HERE, 'requirements.txt')
# 缺了不算故障的包：有代码级回落通道，理由写在 requirements.txt 对应那段。
OPTIONAL_DEPS = {'curl_cffi'}

# 10 家新增交易所（2026-08 接入）—— **一行一条，删掉一家就删掉它这一行**。
#
# 用户明说「非美国交易所维护成本太高就会选择性删除」，所以这里不许出现任何一家的
# 专属逻辑：它们没有 build/<t>.py，页面由通用底座 build/single.py 读 build/specs/<t>.py
# 生成，由下面的 builder() 按「文件在不在」自动认出来 —— 本文件里没有一处写着某家的
# 特殊分支，删掉这一行 + 它的 spec，剩下的代码自洽。完整删除清单见 docs/CRON_WIRING.md。
#
# 行内顺序按发布日排（快的在前），纯为日志好读：一轮跑下来，先动的总是先发的那几家。
EXCHANGES = [
    'db1',     # Deutsche Börse   次月 1-5 日（Eurex 快腿）
    'ice',     # ICE              次月第 3 个美股交易日（实测 3-6 号）
    'tmx',     # TMX Group        次月第 1-4 个工作日（MX 腿）
    'miax',    # MIAX             次月第 3-5 个工作日
    'jpx',     # JPX              次月第 5 个营业日
    'asx',     # ASX              次月第 3-8 天
    'lseg',    # LSEG             次月第 2-8 天，中位第 5（头条 Tradeweb 腿）
    'enx',     # Euronext         次月第 3-13 天，中位第 7
    'sgx',     # SGX              次月第 6-13 天，中位第 9
    'ndaq',    # Nasdaq           份额腿次月第 10 个工作日（IR 腿第 2-6 天）
]
# 顺序 = 首页与导航的展示顺序，也是这里的执行顺序（无依赖，纯为日志好读）
TICKERS = ['cost', 'ibkr', 'schw', 'lpla', 'hood', 'cme', 'cboe', 'hkex',
           'msci', 'spgi', 'axp', 'nanya', 'guc', 'alchip', 'mtk', 'umc', 'ase',
           'tsm'] + EXCHANGES
# 横截面页没有自己的数据源，等成员都更新完之后再生成。
# 这里的名字是**目录名 / data 文件名**（连字符）；生成器文件名是下划线的
# build/exchanges_na.py —— 两者的对应由 builder() 负责，不在这张表里体现。
CROSS = ['wealth',
         'exchanges12',      # 12 家总览（定基名义额）
         'exchanges-na',     # 北美：ICE / Cboe / MIAX / Nasdaq（TMX 对照）
         'exchanges-eu',     # 欧洲现货：Euronext / Cboe Europe / Deutsche Börse
         'exchanges-apac',   # 亚太：HKEX / JPX / SGX / ASX
         'exchanges-products']  # 标的轴：利率 / 股指 / 单股ETF期权 / 能源 / 农产品 / FX 即期
# （`exchanges-intl` 欧亚合页已于 2026-08-06 删除：它是 -eu / -apac 拆分前的旧版，
#   内容与那两张页重叠。删除的完整步骤与实测结果见 docs/DELIVERY.md §4.4。）

# 下载闸门比 roster 的 LAG 提前几天开（见 not_due 的 docstring）。
# 单位与 LAG 一致 = **该月结束后第几天**；开闸日 = 月末后第 (LAG − EARLY) 天。
# 5 天是照实测发布日反推的：LAG 是给红点用的、刻意给宽，减 5 天之后各家的开闸日
# 落在实测发布日当天或之前（COST LAG 7 → 月末后第 2 天开闸，实测 2026-08-05 发布
# 7 月数据 = 月末后第 5 天，提前 3 天；21 家逐家核算见 docs/DELIVERY.md 的闸门表）。
# **别为了「更精确」把它调小**：LAG 是给红点用的上界，
# 各家实测发布日普遍落在 LAG 前 1-4 天（HKEX 差 4 天、TSM 差 0 天），而多数家只有
# 一两次观测 —— 在 n=1 的样本上做逐家微调，等于把噪音当规律。宁可整体给宽：
# 早开闸一天的成本是一个「还没发」的 HTTP 请求，晚开闸一天的成本是公开页面挂旧数据一天。
EARLY = 5
# 例外：LAG 与实测发布日差得离谱的，减 5 天还是会迟到。格式同 LAG = (常规月, 季末月)。
EARLY_BY = {
    # SPGI 季末月**根本没有稳定节奏**，三次实测（见 fetch/spgi.py docstring）：
    #     2026-06 → 第 14 天   2025-06 → 第 31 天   2025-12 → 第 41 天
    # 跨度 27 天，而且最快的那次跟常规月一样快、完全没等季报。
    # LAG[1]=46 是照最慢那次定的 —— 红点要的正是这个上界，不能动。
    # 闸门只能照**最早**的第 13 天开（46-33），否则像 2026-06 那种快的一季要漏 17 天。
    # 代价是慢的那一季空跑将近一个月，那只是一天一个「还没发」的请求。
    'spgi': (5, 33),

    # ── 四家默认闸门会迟到的交易所 ──────────────────────────────────────────
    # 判据统一：**LAG 照实测最晚那期定（红点的上界），EARLY 照实测最早那期定**，
    # 于是开闸日 = LAG − EARLY = 实测最早发布日。窗口窄的家吃默认 EARLY=5 就够
    # （db1/ice/tmx/miax/jpx/asx 的 LAG−5 都已经等于或早于它们的实测最早日），
    # 这四家的 LAG−5 会**晚于**最早发布日，非单独给不可。
    # （交易所之外还有两家台系半导体同病，见本表末尾那一组。）

    # Euronext：90 个数据月逐月实测，第 3-13 天，中位第 7；LAG=13 是最晚那次
    # （2024-04 数据 → 05-13）。13−11 = 第 2 天开闸，比实测最早的第 3 天再早一天 ——
    # 第 3 天出现过 4 次不是孤例，零余量迟早漏一次。
    # ⚠ 必须写成**元组**：取值处是 EARLY_BY.get(t, (EARLY, EARLY))[1 if qe else 0]，
    #    写成裸整数 11 会在下标那一步 TypeError，崩掉的是**整轮** monthly_run。
    'enx': (11, 11),

    # SGX：95 个可信月实测，中位第 9 天，LAG=13。默认闸门 = 13−5 = 第 8 天，
    # 而近 35 个月里有 8 个月（23%）在第 6-7 天就发了（2024-04/05/07/10/11、
    # 2025-02/03/05）—— 那 8 次公开页面会挂 1-2 天陈旧数据。13−7 = 第 6 天开闸，无一迟到。
    'sgx': (7, 7),

    # LSEG：头条走 Tradeweb 腿（LAG=8）。88 期实测落在次月第 2-11 天，2021 起 n=65
    # 收敛到第 2-8 天、中位第 5，其中第 3 天出现 17 次、第 2 天出现 1 次
    # （2023-01 数据 → 2023-02-02）。默认闸门 = 8−5 = 第 3 天，正踩在最密的那一档上
    # 零余量，且必然漏掉第 2 天那一次。8−7 = 第 1 天开闸，比实测最早再早一天。
    # 另三条腿（LSE 订单簿约 +21 天、Main Market/AIM +1~9、LCH +3~4）填的不是头条列，
    # 不推进 data_through，靠下一轮回补 —— 它们的滞后不进这里，也不进 LAG。
    'lseg': (7, 7),

    # Nasdaq：**两条腿差一个多星期**，闸门与红点必须各跟各的腿。
    # 红点跟慢腿（LAG=16，见 build/roster.py：头条列 share_us_cash_matched_* 来自
    # Monthly Market Activity，官方自述次月第 10 个工作日）；闸门跟快腿
    # （IR Monthly Reporting Sheet，实测次月第 2-6 天）：16−14 = 第 2 天开闸。
    # 闸门要跟快腿是因为快腿那一行**先落库**（update() 建行、慢腿的 9 列留空，
    # 下一轮回补）—— 闸门等到第 11 天才开，快腿的数就要在源站上白挂九天。
    'ndaq': (14, 14),

    # ── 两家台系半导体（2026-08-30 新增）────────────────────────────────────
    # 与上面四家同病同治：LAG 是照**最坏**那期定的红点上界，减默认 5 天之后仍晚于
    # 实测最早发布日，于是多数月数据都已公开、闸门还没开（umc 12/12，ase 51/99）。
    # 判据同上：EARLY 照实测
    # 最早那期定 ⇒ 开闸日 = LAG − EARLY = 实测最早发布日。
    #
    # ⚠ **只动闸门、不动 LAG。** 闸门只经由差值 (LAG − EARLY) 进 _due_month，改哪一边
    #   对闸门完全等价；但 LAG 还独自喂着另外两处护栏 —— index.html:78 的首页红点
    #   （月末后第 LAG+GRACE+1 天）与 audit_stale_cols() 的 due 基线（本文件那个函数，
    #   传的是**裸 LAG**、不减 EARLY；此处刻意不写行号 —— 上一版写了 :746，被本次
    #   改动自己插入的 45 行顶成了 DEAD_COLS 里的一条字符串）。
    #   把 LAG 改小会连带压薄红点余量：两家现在都是 6 天（红点日 − 实测最坏发布日），
    #   压到与本表等效的闸门后 umc 只剩 1 天（LAG 9 → 红点第 15 天 vs 最坏第 14 天）、
    #   ase 剩 4 天（LAG 13 → 红点第 19 天 vs 最坏第 15 天）。umc 那 1 天尤其危险：
    #   它的 LAG=14 正是照 6-K 上 EDGAR 的最坏滞后留的（build/roster.py:48-53 与
    #   fetch/umc.py:63-70：2024-10 那期 14 天，2025-05 之前攒批最长 33 天），
    #   一旦 UMC 恢复攒批就当天假红。EARLY_BY 不碰红点，是这里唯一的外科修法。
    #
    # ⚠ 同样必须写成**元组**（理由见上面 enx 那条）。

    # UMC：主源是 SEC EDGAR 的 6-K（fetch/umc.py:16-27），**逐公司申报、不等全市场
    # 汇总**，所以 filingDate 到货即可抓。近 12 期实测公告日（fetch/umc.py:54-57）
    # 换算成月末后第几天 = 4/7/6/4/7/5/5/8/8/5/6/6，最早第 4 天（出现 2 次）。
    # 默认闸门 = 14−5 = 第 9 天 ⇒ **12/12 期全部迟到**，最坏迟 5 天。
    # 14−10 = 第 4 天开闸 = 实测最早发布日（零余量，同 sgx 那条的取法；若日后出现
    # 第 3 天的一期，按 enx/lseg「比实测最早再早一天」的取法应改成 (12, 12)，
    # 不是 (11, 11) —— 后者给出的闸门恰好等于新的最早日，仍是零余量）。
    'umc': (10, 10),

    # ASEH：数值源是公司自家月度新闻稿 PDF（fetch/ase.py:31；PDF 由 todayir 托管，
    # 域名见同文件 :25 落地页那节），
    # 同样逐公司发布。99 期实测（fetch/ase.py:69-71）第 8 天 9 期 / 第 9 天 42 期 /
    # 第 10 天 34 期 / 第 11 天 10 期 / 第 12·13·15 天各 1 期 / 第 40 天 1 期
    # （第 40 天那期是 2022-12 的改版重发，不算节奏）。最早第 8 天，出现 9 次。
    # 默认闸门 = 15−5 = 第 10 天 ⇒ 51/99 期（约 52%）迟 1-2 天。
    # 15−7 = 第 8 天开闸 = 实测最早发布日。LAG=15 照的是农历年那期
    # （2024-01 数据 → 2024-02-15），红点要的正是那个上界，不动。
    'ase': (7, 7),

    # ⚠ **nanya 不在这里，是刻意的**（2026-08-30 实测撤案，别再加回来）：
    # 它的头条序列 series/nanya.csv 进料口是 MOPS 全市场月档 t21sc03（fetch/nanya.py
    # 源 1），**事实闸门**探针 latest_month()（docs/CRON_WIRING.md 2.4 的用词，与本表
    # 这种日历闸门对举）走 TWSE OpenAPI t187ap05_L（源 2，:701 明写「与 MOPS 月档
    # 同步」）—— 那是一份**证交所全市场汇总档，整份一起翻页**：2026-08-30 实拉
    # 1,085 条记录，`資料年月` 全为 11507、`出表日期` 全为 1150817，不同值个数 = 1。
    # 承重的不是那个日期而是这条结构性事实：全市场档要等整个市场申报完才翻
    # `資料年月`，而台湾法定申报期限是次月 10 日 ⇒ 翻页 ≥ 第 10 天。
    # ⚠ 别拿 `出表日期` 去反推发布日：它是 TWSE **重生成**该档的时间戳，只给上界 ——
    #   同一期 11507 先后被读到 1150812 / 1150813 / 1150817 三个值（fetch/nanya.py:195-198、
    #   fetch/alchip.py:80-81、fetch/mops_remarks.py:543、本文件「2026-07 那期…第 13 天」
    #   那条注释）。能确证的是第 12 天已在，不是「第 17 天才出」。
    # nanya 默认闸门 = 13−5 = 第 8 天 < 第 10 天，**本来就早于源头**，不存在迟开。
    # series/nanya_notes.csv 里那 24 期「第 2-8 天」是**新闻稿日期**，写它的
    # update_notes() 压根没接进本文件（fetch/nanya.py:352），与闸门无关 —— 拿它
    # 反推闸门是比错了事件。
}


# ── 慢腿登记表 ────────────────────────────────────────────────────────────────
# 上面那张 EARLY_BY 管的是**头条腿**：头条一落地，data_through 就跳月，not_due 判
# 「追平」，整家从此不再下载。对单腿源这没问题；对多腿源，慢腿当月晚几天发的数据
# 就此没人去取，要等下个月 1 号闸门重开才顺带回补 —— 结构性晚一整个发布周期。
#
# 2026-08-17 实测的四个实例（逐列扫 series/<t>.csv 的最后非空月）：
#   tmx  17 条现货列停 2026-06 / 28 条 MX 列 2026-07   官方 2026-08-07 就发了
#   db1  20 条集团台账列停 2026-06 / 43 列 2026-07     上游 xlsx 字节已变
#   lseg 17 条订单簿列停 2026-06 / 63 列 2026-07       官方 2026-08-11 就发了
#   jpx   2 条 IPO 列停 2026-06 / 39 列 2026-07
# 三家在首页都是**绿点 + 印着 2026-07**，用户看不出慢腿差了一个月。
#
# 值 = (列名前缀元组, (常规月开闸日, 季末月开闸日))，开闸日单位同 LAG =「该月结束
# 后第几天」。列名用**前缀**匹配，因为慢腿的列名天然共享前缀；写全名也可以。
#
# ⚠ 开闸日不必取该腿实测的**最早**到货日。慢腿闸门要防的是「拖到下月」这种整月丢
#   失，只要闸门在当月内开，那个月的数据当月就能进来。lseg 订单簿近 30 期跨度是
#   +2~+24 天，按 +2 开闸等于每月多 20 天下载，而它每轮要打 67 次检索 API
#   （fetch/lseg_orderbook.py 的逐月 _search，各 sleep 0.25s）—— 取中段即可。
#
# ⚠ **不要为「永久停发」的列建登记**：它们永远追不平，闸门会被顶成天天下载。
#   实测存量：jpx 的 cmdty_proforma 停在 2020-07（停发六年）、lseg 的 6 条
#   repoclear_* 停在 2026-05（另一条更慢的腿，节奏未实测）。两者都**不**登记。
SLOW_LEGS = {
    # 现货 CTS 新闻稿：数据月结束后第 2–8 天、中位第 5、139 期最坏第 14
    # （fetch/tmx.py:63-65）。该 docstring 自己的结论就是「闸门次月 2 日开」。
    'tmx':  (('tmx_all_', 'tsx_', 'tsxv_', 'alpha_', 'alphax_drk_'), (2, 2)),

    # 集团 IR 台账 xlsx：次月约第 10 天（fetch/db1.py:4、:62 的节奏表）。
    # 按 not_due docstring 的 EARLY 原则提前 2 天，宁可多打两个空请求。
    # 后三条不共享前缀，只能点名；漏了它们闸门会在台账只到一半时提前关，而
    # turnover_cash_total_eurbn 还是 build/exchanges12.py 的门槛列，漏它等于把
    # exchanges-eu / exchanges-products 两张横截面页一起钉住。
    'db1':  (('trading_days_cash', 'vol_fd_', 'vol_power_', 'vol_gas_', 'otc_',
              'auc_', 'settle_', 'adv_360t_', 'cash_balances_', 'gsf_',
              'turnover_cash_total_eurbn', 'aum_stoxx_dax_etf_eurbn',
              'vol_licensed_index_contracts'), (8, 8)),

    # LSE 订单簿月报：近 30 期 +2~+24 天，2026 中位 +21
    # （fetch/lseg_orderbook.py:76-86，节奏 2024 年起明显变慢）。
    # 取第 12 天是成本折中：比中位早 9 天，又不至于把 67 次/轮的检索 API 打 20 天。
    'lseg': (('lse_orderbook_', 'lse_trading_days_', 'lse_lit_uk_share_',
              'turquoise_integrated_', 'turquoise_dark_', 'turquoise_paneuropean_',
              'turquoise_trading_days_', 'gbp_eur_rate'), (12, 12)),

    # 资金調達額 historical-sikin.xls：这条腿只填 2 列，比头条腿（次月第 7 天）
    # 晚半个月。实测到货日两点 —— 2026-06 期 07-17、2026-07 期 08-19（后者由
    # HTTP Last-Modified "Wed, 19 Aug 2026 06:13:35 GMT" 实测），与 fetch/jpx.py
    # 表格里那句「每月中旬」一致。取第 15 天开闸：比两次实测都早 2 天留余量，
    # 又只在第 15 天到到货日之间多打两三次请求。
    #
    # 本条 2026-08-17 立案时**刻意留空**过，理由是「没有实测到货日分布」。但按上面
    # 那条 ⚠：开闸日不必取实测最早到货日，只要闸门在当月内开即可 —— 两个实测点
    # 已经够定「中段」。留空的实际代价是 2026-07 那期在上游挂了 7 天没人取
    # （08-19 发，闸门要等 09-03 才开），而首页仍是绿点、印着 2026-07。
    #
    # ⚠ 只登记这 2 列。同文件的 cmdty_proforma 停在 2020-07（停发六年）属「永久停发」，
    #   登记它会把闸门顶成天天下载 —— 见上面第二条 ⚠。列名写全名不写前缀，免得将来
    #   新增的 ipo_* 快腿列被前缀误收进来、把闸门钉死在一条本不该等的腿上。
    'jpx':  (('ipo_public_offerings', 'ipo_funds_jpybn'), (15, 15)),
}


def sh(cmd, cwd=HERE, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f'{" ".join(cmd)} 失败: {r.stderr[-400:]}')
    # 只去尾部空白：`git status --porcelain` 的首字符是索引状态位，`.strip()` 会把
    # 第一行的前导空格吃掉，脏树清单打出来对不齐、也看不出 staged/unstaged。
    return r.stdout.rstrip()


def check_deps():
    """核对已装依赖与 requirements.txt 的钉版，返回 (warn 清单, note 清单)。

    ## 为什么告警而不是拦

    这是无人值守的月度管道。因为一个版本号对不上就整月不发布，代价远大于「在一个没实测过
    的版本上跑一次」—— 何况绝大多数版本漂移根本不影响结果。所以这里只喊，不退出。

    反过来，也不能一声不吭：2026-08-04 本机 pandas 被静默升到 3.0.5，`astype(str)` 不再把
    NaN 转成 'nan'，COST 的 comp 表解析 100% 抛 TypeError；因为没有任何东西提示「脚底下换了
    地板」，故障第一时间被误诊成「Costco 官网改版了」，排查方向整个错。静默跑在未测过的版本
    上正是那次事故的成因，所以醒目告警是必须的。

    ## 为什么只读元数据

    只用 importlib.metadata（= 读几个 dist-info 里的纯文本），**不 import 任何被检查的包**。
    自检要是自己得先把 pandas / matplotlib / pymupdf 拉起来，那它比它要防的问题还贵，
    而且没装的包会在自检里就炸掉 —— 那就成了变相的阻断。
    """
    try:
        with open(REQUIREMENTS, encoding='utf-8') as f:
            txt = f.read()
    except OSError as e:
        return [f'读不到 requirements.txt（{e}）—— 本次跑没有核对过依赖版本'], []
    # 只认最朴素的 `包名==版本`；requirements.txt 里其余全是注释，没有 extras / marker / 范围。
    pins = re.findall(r'^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s#]+)', txt, re.M)
    if not pins:
        return ['requirements.txt 里没有任何 `包名==版本` 行 —— 本次跑没有核对过依赖版本'], []
    warn, note = [], []
    for name, want in pins:
        try:
            got = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            (note if name in OPTIONAL_DEPS else warn).append(
                f'{name} 未安装（requirements.txt 要求 {want}）'
                + ('，可选依赖、有回落通道，忽略' if name in OPTIONAL_DEPS else ''))
            continue
        if got != want:
            warn.append(f'{name} 实际 {got}，requirements.txt 实测版本是 {want}')
    return warn, note


def report_deps():
    """把 check_deps 的结果打出来。永远不 exit —— 见 check_deps 的 docstring。"""
    warn, note = check_deps()
    for n in note:
        print(f'依赖提示：{n}')
    if not warn:
        return
    bar = '=' * 78
    print(bar)
    # 标题要能同时盖住三种情况（版本不符 / 必需包没装 / requirements.txt 读不到），
    # 别写死成「版本不符」—— 后两种打出来会自相矛盾，读日志的人第一反应是自检自己坏了。
    print('⚠️  依赖与 requirements.txt 不一致 —— 仍继续执行，但下面这些没有被实测过：')
    for w in warn:
        print(f'    · {w}')
    print('    结果异常时先怀疑这里，别先怀疑数据源改版')
    print('    （pandas 3.0 的 astype(str) 不再把 NaN 转成 "nan"，2026-08-04 就是这么打死 COST 的）')
    print(bar)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_registry():
    """核对本文件的 TICKERS / CROSS 与 build/roster.py 的导航名单是否还对得上。

    删一家要动五个地方（见 docs/CRON_WIRING.md），漏掉任何一个都不会立刻炸，
    只会长期渗血，而且两个方向的症状都很难由现象反推回原因：

      · 这里留着、roster 删了 → 每天照常抓、照常写 series，但页面永远不在导航里，
        首页也不会给它判红点。数据在更新，没有人看得见。
      · roster 留着、这里删了 → 导航挂着一个再也不更新的入口，首页给它判红点，
        而日志里一个字都没有 —— 看上去像「抓取悄悄坏了」，实际是根本没人去抓。

    所以每轮开跑前对一次名单。**只告警不退出**：一个忘掉的名字不该让另外二十页
    今天不发布（与 report_deps 同一条原则）。
    """
    try:
        r = load(os.path.join(HERE, 'build', 'roster.py'), 'roster_reg')
        nav = {t for _k, _row, _lab, ts in r.GROUPS for t in ts}
    except Exception as e:                       # roster 坏了由末尾的 roster() 去炸
        return [f'读不到 build/roster.py 的导航名单（{type(e).__name__}: {e}）']
    mine = set(TICKERS) | set(CROSS)
    msg = []
    for t in sorted(mine - nav):
        msg.append(f'{t}：在 monthly_run 的名单里，但 build/roster.py 的 GROUPS 里没有 '
                   f'—— 每天照常抓取，页面却不在导航上')
    for t in sorted(nav - mine):
        msg.append(f'{t}：在 build/roster.py 的导航上，但 monthly_run 的名单里没有 '
                   f'—— 导航挂着一个再也不会更新的入口')
    return msg


def report_registry():
    """把 check_registry 的结果打出来。永远不 exit —— 见 check_registry 的 docstring。"""
    msg = check_registry()
    if not msg:
        return
    bar = '=' * 78
    print(bar)
    print('⚠️  注册名单对不上 —— 仍继续执行，但下面这些页处于「只抓不显示」或'
          '「只显示不抓」的状态：')
    for m in msg:
        print(f'    · {m}')
    print('    删一家要动五个地方，清单见 docs/CRON_WIRING.md')
    print(bar)


def run_gate(name, cmd, quiet_on_pass=False):
    """跑一道闸门子进程，把它的输出原样转印出来，返回它的退出码。

    ## 为什么是子进程，而不是像 check_specs 那样 import 着跑

    check_specs 能被 import 是因为它的 `main(argv)` 收参数、也不自己 exit。另外三道不行：
    `build/test_guards.py` 走 `unittest.main()`（自己 sys.exit），
    `build/verify_pages.py` 与 `tools/check_yoy_caliber.py` 的 `main()` 都直接读 `sys.argv`
    （在本进程里跑会吃到 monthly_run 自己的 --only / --dry-run）。隔进子进程还顺带买到
    一条：check_yoy_caliber 要拉起 pandas + numpy 并全量读 series/*.csv，
    它自己崩掉时带不走这一轮已经跑完的部分。

    ## 为什么不能用 sh()

    sh() 失败时只在异常里带 stderr 的末 400 字，而这三道闸门的**逐条诊断全打在 stdout**。
    用 sh() 接等于「拦是拦住了，但看不见拦在哪一条」—— 那正是本仓最忌讳的那种日志。

    ## quiet_on_pass

    通过时只印末尾三行（各闸门自己的计数汇总）。**只给「没有『不致命但要看』那一档」
    的闸门用**：verify_pages 的 WARN 与 check_yoy_caliber 的 🟡 都印在输出中段，
    对它们开这个开关就等于由调用方把那一档吞掉。
    """
    # 闸门脚本被删掉时**不静默跳过**：python3 找不到文件会以退出码 2 结束，调用方照样
    # 记 FAIL（实测输出就是那行 "can't open file ... No such file"）。这和 builder() 的
    # 「找不到生成器就跳过」刻意相反 —— 那边跳过是因为删一家是正常操作，
    # 这边一道闸门消失了必须响，「闸门被悄悄删掉」正是它自己要防的那类事。
    t0 = time.time()
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    lines = (r.stdout + r.stderr).rstrip().splitlines()
    if r.returncode == 0 and quiet_on_pass:
        lines = [x for x in lines if x.strip()][-3:]
    print(f'── 闸门 {name} —— 退出码 {r.returncode}，{time.time() - t0:.1f}s ──')
    for ln in lines:
        print(f'  {ln}')
    return r.returncode


# 本脚本自己会写、也自己会提交的路径。护栏与提交范围必须用同一份清单 ——
# 两者一旦不一致，本脚本就会亲手把工作树弄脏，然后被自己的护栏拦死。
# （曾经只写 data：fetch 往 series/*.csv 追加新月份，而 series 是 tracked 的，
#  于是「第一次成功发布」这件事本身留下 ` M series/xxx.csv`，下一次跑必被拦，
#  且不是拦某一家，是 28 家一起停 —— 无人值守管道只能成功发布一次。）
PUBLISH = ['data', 'series']


def guard_dirty_tree():
    """返回**本脚本管辖范围之外**的未提交改动（porcelain 文本），干净时为空串。

    这个仓库是手写手改的：charts.js / page.js / index.html 经常处于改到一半的状态。
    没有这道检查时，cron 会把半成品连同数据一起 commit 成「更新 YYYY-MM 数据」推到
    公开 Pages —— 页面变半成品，而 commit message 完全看不出发生了什么。
    所以提交范围收窄成 PUBLISH 里那几条显式路径，并在此之外拒绝脏树。
    """
    return sh(['git', 'status', '--porcelain', '--', '.'] + [f':!{p}' for p in PUBLISH])


def sync_with_origin(dry_run):
    """把主 checkout 快进到 origin/main。**必须跑在任何抓取与构建之前。**

    ## 不加会怎样：不是「掉一天」，是卡死

    本函数之外，全脚本没有任何 fetch / pull / rebase，而 main() 末尾的发布段是
    **先 commit 后 push**（两句紧挨着，中间没有任何同步动作）。于是「主 checkout 落后 origin」会这样
    发展：commit 成功 → push 被 non-fast-forward 拒 → FAILED 退出，**而那个
    提交留在本地**。第二天仍然没有 fetch，于是在它上面再 commit 一个、再被
    拒……本地分支永远不会收敛。它每天安静地 FAILED 一次，直到有人手工介入，
    而且每天的 data_changed() 都为真（上一天的改动已经 commit 进去了，工作树
    反而干净），所以连「今天没数据」这种自愈都轮不到。

    这个仓有多个 session 并发直推 main，**落后是常态而不是意外**。

    ## 为什么放在这里，而不是发布段的 commit 之前

    两个理由，后一个更重要：

    1. 此刻工作树刚被 guard_dirty_tree() 验过是干净的，ff 能安全跑。到了
       发布段的时候，28 家的 data/*.js 已经全部重建完、躺在工作树里未提交，
       此时 `git merge --ff-only` 会被「Your local changes to the following
       files would be overwritten by merge」直接拒掉 —— 故障没修好，只是挪到
       了更晚、更难看懂的地方，还白跑了一整轮抓取和构建。
    2. 整轮抓取与构建因此建立在**最新基线**上。在旧基线上构建出来的 payload
       本身就可能是错的：别人刚推了一个生成器修正，这一轮还在用旧逻辑生成，
       推上去等于**静默回退**——那比 push 被拒难发现得多，因为它不报错。

    ## fetch 与 merge 的处理刻意不对称，不要把它们统一成一种

    · fetch 失败**只 warn**：无人值守下因为一次网络抖动就整月不发布，代价大于
      在旧基线上跑一轮 —— 后者至少还有 push 被拒兜底，前者是直接不干活。
    · merge --ff-only 失败**必须 FAILED**：非快进意味着本地有 origin 没有的
      提交，或工作树里有挡路的改动。无人值守下自动 rebase 数据提交，比不发布
      危险得多 —— 那会把别人的提交和本轮数据搅在一起，且无人复核。

    ## 已知副作用：ff 之后这一轮可能是「混版跑」——**接受，不要加自重启**

    如果快进带进来的那批提交里**包含 monthly_run.py 自己**，那么当前进程跑的
    仍是内存里的旧版本，而它接下来以子进程调起的 build/*.py、fetch/*.py 全是
    新版本。绝大多数时候无害（新旧生成器都能跑），但它会造出一类极难查的现象：
    **日志里的行为对不上文件里的代码**，而且只在 monthly_run.py 被更新的那一天
    出现一次，下一轮就自愈了。

    结论是**接受**。不加自重启：无人值守里进程自己 re-exec 一个刚拉下来、
    没人看过的版本，比混版跑一轮危险得多（新版本若在启动路径上就有 bug，
    自重启会把它变成无限重启，而混版最多错一轮）。
    写在这里是因为：不写的话，下一个人查到这里会以为是 bug，然后去加自重启。
    """
    # 先确认站对了分支。guard_dirty_tree() 只看有没有改动、**不看在哪条分支上**，
    # 所以「有人在主 checkout 上切了分支查东西、忘了切回来」能一路畅通地走到底：
    # 脏树检查过 → 这里若不拦，那条分支若恰是 origin/main 的祖先还会真 ff 成功 →
    # 整轮构建 → commit → 而 940 行是**裸 git push，推的是当前分支**。
    # 结果是数据提交推到一条不是 main 的分支上，全程零报错，而 Pages 从 main
    # 根目录发布，于是站点静默停更。和本函数防的那个雷是同一形状：
    # 不是「会失败」，是**失败了没人知道**。
    br = sh(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], check=False)
    if br != 'main':
        msg = ('主 checkout 当前在分支 %r 而不是 main —— 本脚本只在 main 上发布'
               '（Pages 从 main 根目录发），继续跑会把数据提交推到别的分支上，'
               '且全程不报错、站点静默停更。' % br)
        if dry_run:
            # 与 guard_dirty_tree 的处理保持一致：--dry-run 不 commit/push，
            # 此时正是要看「如果跑会发生什么」，故只告警不拦。
            print('警告：' + msg + '（--dry-run 不发布，故只告警）')
            return
        print('FAILED ' + msg + ' 请先切回 main 再重跑。')
        sys.exit(1)

    env = dict(os.environ, GIT_SSH_COMMAND='ssh -o BatchMode=yes')
    r = subprocess.run(['git', 'fetch', 'origin'], cwd=HERE,
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        # 只 warn（见 docstring 的不对称一节）
        print('警告：git fetch 失败，这一轮将在可能已过期的基线上跑：%s'
              % r.stderr.strip()[-200:])
        return

    # check=False：origin/main 引用缺失时 sh() 会抛裸 RuntimeError，那在日志里
    # 是个 traceback 而不是一行干净的 FAILED，值班的人得先读栈才知道发生了什么。
    behind = sh(['git', 'rev-list', '--count', 'HEAD..origin/main'], check=False)
    ahead = sh(['git', 'rev-list', '--count', 'origin/main..HEAD'], check=False)
    if not (behind.isdigit() and ahead.isdigit()):
        print('FAILED 读不出与 origin/main 的差距（fetch 成功但 origin/main 引用'
              '不可用，远端可能改了默认分支名或该引用被删）。拒绝在不知道基线'
              '新旧的情况下发布。')
        sys.exit(1)
    if behind == '0' and ahead == '0':
        return

    if dry_run:
        print('DRY_RUN 与 origin/main 相差：落后 %s / 领先 %s（正式跑会在此快进）'
              % (behind, ahead))
        return

    if behind == '0':
        # 只领先不落后：本地有还没推上去的提交（很可能就是上一轮 push 失败的
        # 残留）。这不用快进，末尾那次 push 会把它一起带上去；但要说出来，
        # 否则「今天推上去的东西比今天做的多」会让人对不上账。
        print('注意：本地领先 origin/main %s 个提交（尚未推送），'
              '本轮 push 会把它们一并推上去' % ahead)
        return

    r = subprocess.run(['git', 'merge', '--ff-only', 'origin/main'],
                       cwd=HERE, capture_output=True, text=True)
    if r.returncode != 0:
        print('落后 origin/main %s 个提交，但快进失败：' % behind)
        print((r.stderr or r.stdout).strip()[-400:])
        print('FAILED 无法快进到 origin/main，拒绝在过期基线上发布。两种可能：'
              '(a) 本地有 origin 没有的提交（上一轮 push 失败的残留，或有人直接'
              '在主 checkout 上改过）—— 本脚本刻意不自动 rebase 数据提交；'
              '(b) data/ 或 series/ 里有上一轮残留的未提交改动，git 因'
              '「would be overwritten by merge」拒绝快进（guard_dirty_tree 只管'
              'PUBLISH 之外的路径，管不到这两个目录）。'
              '两种都请人工处理后重跑，不要让脚本自己猜。')
        sys.exit(1)
    print('已快进到 origin/main（原落后 %s 个提交）' % behind)


# _body 的实现已下沉到 build/payload_guard.body_of()：写盘侧（write_dash /
# build/roster.py）要用同一套口径判断「正文有没有变、要不要落盘」。各写一份
# 一旦漂移，就是「构建器不写、data_changed 说变了」的漏发夹缝。
sys.path.insert(0, os.path.join(HERE, 'build'))          # 与 :995 幂等
from payload_guard import body_of as _body               # noqa: E402


def data_changed():
    """`data/` 相对 HEAD 是否有**实质**变化（忽略每个文件的首行）。

    首行是 `// 由 build 生成于 YYYY-MM-DD`，天天不同但它不是数据。若用
    `git status --porcelain data` 判断，只要不是同一天重跑就必然非空 →
    每次例行跑都产出一个内容完全相同、只有日期变了的 no-op commit，
    并把页面的新鲜度信号刷成当天，主动制造「页面是活的」的错觉。
    """
    tracked = set(sh(['git', 'ls-tree', '-r', '--name-only', 'HEAD', 'data/']).splitlines())
    live = {f'data/{n}' for n in os.listdir(DATA) if not n.startswith('.')}
    if tracked != live:
        return True                      # 新增或删除了数据文件，直接算变化
    for rel in sorted(live):
        with open(os.path.join(HERE, rel), encoding='utf-8') as f:
            if _body(f.read()) != _body(sh(['git', 'show', f'HEAD:{rel}'])):
                return True
    return False


def not_due(t):
    """线上数据是否已经追平「按该家披露节奏今天本应有的月份」。

    有了这个判断，本脚本可以每天跑而不是挑几天跑：28 家的披露日从次月 1 号散到 21 号，
    要覆盖全部窗口就得天天跑；但天天把 28 个源全下一遍纯属浪费（也给对方站点添堵）。
    所以先用本地已有的 data_through 对照 LAG 表，够新的直接跳过，一个字节都不下。
    --force 会绕过它（改了图表代码后要全量重建）。

    ## 两道判据，缺一条就会静默丢一整个发布周期

    `data_through` 只代表**头条腿**（build/single.py:resolve_through 只看头条列），
    所以它答的是「页面够不够新」。多腿源的慢腿晚几天发，头条一落地它就跳月、闸门
    随即关死，慢腿当月的数据要等下个月 1 号才顺带回补 —— 2026-08-17 实测 tmx /
    db1 / lseg 三家正卡在这上面，且首页全是绿点。所以这里是两道：

      1. 头条腿追平了今天本该有的月份（原判据，逐位未变）；
      2. **且** SLOW_LEGS 登记的慢腿也不欠货（slow_pending）。

    没登记慢腿的家，第 2 条恒为「不欠」，行为与改动前完全相同。

    ## 这道闸门与首页红点用的**不是**同一个阈值，别再合并回去

    两者共用 LAG 表，但方向相反，所以偏置必须相反：

    · **红点**要宽容 —— 早一天变红就是假警报，而每季度假一次的警报，人很快就学会
      无视它。所以红点是 `LAG + GRACE`（宽限 5 天）。
    · **下载闸门**要提前 —— 早开闸一天只多一个 HTTP 请求（源还没发就是 NOCHANGE，
      各家 fetch 都能干净返回）；晚开闸一天就是公开页面挂着旧数据一天。
      所以这里是 `LAG - EARLY`。

    这两个偏置原本都写成 `+ GRACE`，代价是实测量出来的：Costco 2026-08-05 就发了
    7 月数据，闸门却要等到 8-13 才开（月末 8-01 + LAG 7 + GRACE 5），公开页整整
    8 天挂着 6 月数据 —— 而 LAG 表本身就是按红点口径「宁可给宽一点」定的，再叠一层
    宽限等于把误差加了两次。

    `max(0, ...)` 是下界：LAG 小于 EARLY 的几家（cme/ibkr 都是 2）不能因此在候选月
    还没结束时就去下载，最早也要等到次月 1 号。

    ## `- 1` 不是凑数：`end` 已经是「月末 + 1 天」

    LAG 的单位是**该月结束后第几天**（见 roster.LAG 的表头注释），而循环里的 `end`
    取的是次月 1 号 —— 它本身已经等于「月末后第 1 天」。所以要让闸门落在「月末后第
    (LAG − EARLY) 天」，偏移量必须是 `days - early - 1`；写成 `days - early` 会整体
    晚开一天。这一天不是无害的：按 2026-08-06 实测，tmx / miax / asx / sgx / ndaq
    五家的开闸日都恰好落在各自实测**最早**发布日的后一天（例如 SGX 闸门第 7 天、
    实测最早第 6 天，近 35 个月里有 8 个月在第 6-7 天就发了），也就是每逢它们发得早
    的那个月，公开页面要多挂一天旧数据 —— 正是本函数开头那条「晚开闸一天就是公开
    页面挂着旧数据一天」要防的事。EARLY_BY 的三条逐家注释（enx / sgx / ndaq）算的
    也都是「LAG − EARLY = 实测最早发布日」，与这里的 `- 1` 同一口径。
    """
    lag = due_lag(t)
    if lag is None:
        return False
    p = os.path.join(DATA, f'{t}.js')
    if not os.path.exists(p):
        return False                      # 还没建过，必须跑
    with open(p, encoding='utf-8') as f:
        txt = f.read()
    through = json.loads(txt[txt.index('{'):txt.rindex('}') + 1]).get('data_through')
    if not through:
        return False
    # 共用 roster 的 LAG 表（= 该月结束后第几天发布，季末月单独给值），但偏置取 -EARLY
    # 而不是红点的 +GRACE（理由见上）。从本月往回找第一个「已开闸」的候选月，
    # 那就是今天本该已经有的月份。
    early = EARLY_BY.get(t, (EARLY, EARLY))
    due = _due_month((lag[0] - early[0], lag[1] - early[1]))
    if due is None or through < due:
        return False
    # 头条腿追平了，但多腿源可能还欠着慢腿的货 —— 那正是 data_through 看不见的部分。
    return not slow_pending(t)


def due_lag(t):
    """roster 的 LAG[t]（= 该月结束后第几天发布，(常规月, 季末月)）；没登记返回 None。

    单拎出来是因为 not_due 与「跳过原因」那句话都要用它，而它每次都要 load 一遍
    build/roster.py —— 两处各写一遍 load 迟早会漂。

    缓存一份：not_due 与「跳过原因」那句话各调一次，28 家就是 56 次 load，而 LAG
    是启动即定的常量表，一轮之内不会变。
    """
    if not _LAG_CACHE:
        _LAG_CACHE.update(load(os.path.join(HERE, 'build', 'roster.py'),
                               'roster_due').LAG)
    return _LAG_CACHE.get(t)


_LAG_CACHE = {}


def _due_month(open_days, today=None):
    """今天本该已经拿到的那个月（'YYYY-MM'）；6 个月内没有候选月开闸时返回 None。

    `open_days` = (常规月, 季末月)，单位与 LAG 一致 =「该月结束后第几天开闸」。
    从 not_due 里原样拆出来，只为让**每条腿各带各的开闸日**走同一份算术 ——
    日期这层只能有一份实现：`- 1` 那个偏移（end 已经是「月末后第 1 天」）是靠实测
    才发现的，抄第二份必然少写一次。循环体与拆分前逐行相同。

    `today` 只为测试留缝，生产路径一律走默认值。
    """
    today = today or datetime.date.today()
    for k in range(6):
        n = today.year * 12 + today.month - 1 - k      # 候选月的下个月（k=0 即本月）
        y, m = n // 12, n % 12 + 1
        end = datetime.date(y, m, 1)                   # 候选月月末 + 1 天
        cy, cm = (y, m - 1) if m > 1 else (y - 1, 12)  # 候选月本身
        off = open_days[1] if cm % 3 == 0 else open_days[0]
        # end 已是「月末后第 1 天」，故偏移量减 1；max(0,…) 把下界钉在次月 1 号。
        if today >= end + datetime.timedelta(days=max(0, off - 1)):
            return f'{cy}-{cm:02d}'
    return None


def slow_pending(t, today=None):
    """这一家是否「还欠着慢腿的货」→ 欠就返回 True，闸门必须开着。

    判据只用 series/<t>.csv 里逐列的最后非空月，**不碰 payload、不 import fetch
    模块**。两条都是刻意的：

      · data_through 是给**页面新鲜度**用的（build/single.py:resolve_through 只看
        头条列，slow_cols 一律排除 —— 那对页面是对的，一条天生晚发的腿不该拖住整
        页）。闸门问的是另一个问题「今天还欠不欠货」，欠一条腿也是欠。两个问题共
        用一个字段，正是 tmx / db1 / lseg 静默停更的全部成因。
      · import fetch 模块会把 openpyxl / fitz / pandas 这些重库拖进「已追平」这条
        今天完全不碰 fetch 的路径，28 家每天都要付一次。

    **失败一律 fail-open（当成「欠货」→ 去下载）**：这个方向错了只多几个 HTTP
    请求，反方向错了是整月静默丢数据 —— 而后者正是本函数要修的那个 bug。所以整个
    函数体裹在 except 里，异常只打 WARN，绝不让它把整轮 monthly_run 带走。
    """
    reg = SLOW_LEGS.get(t)
    if not reg:
        return False
    prefixes, open_days = reg
    try:
        due = _due_month(open_days, today)
        if due is None:                       # 这条腿今天还没开闸 → 不欠
            return False
        p = os.path.join(SERIES, f'{t}.csv')
        with open(p, encoding='utf-8', newline='') as f:
            rows = list(csv.reader(f))
        head = rows[0]
        idx = [i for i, c in enumerate(head)
               if i and any(c.startswith(x) for x in prefixes)]
        if not idx:
            print(f'  ⚠ {t}: 慢腿登记的列前缀在 series/{t}.csv 里一列都没匹配上 —— '
                  f'多半是上游改了列名，登记就此静默失效。按欠货处理（照常下载）。')
            return True
        # 一条腿 = 同一份上游文件、同一次到货 ⇒ 各列的最后非空月本应相同。
        # 取最小（最落后的那列）才是这条腿真实的进度。
        last = min((max((r[0] for r in rows[1:]
                         if i < len(r) and r[i].strip()), default='')
                    for i in idx), default='')
        return last < due
    except Exception as e:                    # noqa: BLE001 —— 见 docstring 的 fail-open
        print(f'  ⚠ {t}: 慢腿判定出错（{type(e).__name__}: {e}）—— 按欠货处理，照常下载。')
        return True


# ── 陈旧列审计 ────────────────────────────────────────────────────────────────
# README「第四类：不出声的失败」的判据是「连续失败十天和成功十天，在日志里长得一样
# 吗」。**逐家的 NOCHANGE 恰好就长得一样** —— 它只回答「今天没抓到新的」，不回答
# 「这一列还活着吗」。28 家绝大多数天都是 NOCHANGE，所以一条冻住的列可以在末行永远
# 是 NOTHING_TO_DO 的日志里躲无限久：闸门按 data_through 判「已追平」不再下载，
# fetch 干净返回，streaks 里没有 FAIL 可记。首页红点确实会变红，但那是**浏览器端按
# 打开页面那天现算的**，只有人去看站点才看得见；每天读 cron 输出的人什么也看不到。
#
# 所以这里补最后一道：不问「今天有没有新数据」，问「每一列离它本该有的月份差了多远」。
#
# ⚠ 判据必须能在稳态下**完全闭嘴**，否则就是又一个「每季度假一次的警报」，人很快
#   学会无视它，这道护栏就白加了。两条设计保证这一点：
#     · 永久停发的列写进 DEAD_COLS 白名单（下面每条都回过各模块自己的文档，
#       不是猜的），登记过的不再报；
#     · 其余列给 STALE_GRACE_MONTHS 个月宽限，盖住所有**按设计**就晚的慢腿
#       （lseg 的 RepoClear 官方月表本身滞后约两个月，见 build/specs/lseg.py）。
#
# ⚠ 白名单是**双向**的：登记为「已停发」的列若哪天又有了新数据，说明登记本身错了，
#   同样要出声 —— 否则这张表会慢慢变成掩盖真问题的地毯。
#
# ⚠ 本函数**不改末行总状态**。末行的文法（NOTHING_TO_DO / PUBLISHED / PARTIAL /
#   FAILED）是调度任务唯一读的那行，动它等于改对外契约；陈旧不等于本轮失败，
#   它是「该有人去看一眼」，不是「今天这轮跑挂了」。
DEAD_COLS = {
    'asx': {
        'capital_initial_raised_audmn':
            ('2023-09', '上市融资旧口径，官方改版后停发（build/specs/asx.py 标 dead=True）'),
        'capital_total_raised_incl_other_audmn':
            ('2023-09', '同上，与 capital_initial_raised_audmn 同一次改版'),
        'margin_cash_onbs_audbn':
            ('2024-07', '表内现金保证金旧口径，2024-08 起停发（同上 spec 的区间注释）'),
    },
    'cme': {
        'adv_clearport_kcontracts':
            ('2013-12', 'ClearPort 自 2014 起并入 Privately Negotiated，官方不再单列'
                        '（fetch/cme.py 的口径坑：2014 起整行从 xlsx 消失，之后天然为空）'),
    },
    'jpx': {
        'cmdty_proforma':
            ('2020-07', '商品関連 pro-forma 回填**标记位**，只在 TOCOM 迁入 OSE 之前有意义；'
                        '不是数据列，永远不会再有新值'),
    },
    'sgx': {
        'vol_msci_taiwan_futures_contracts':
            ('2021-11', 'MSCI Taiwan Index Futures 合约停用（fetch/sgx.py 明写「已停发的死列」，'
                        'build/specs/sgx.py 亦然）'),
    },
}

# 宽限月数：慢腿按设计就会晚，报它们等于制造假警报。取 3 是因为在册最慢的那条
# （lseg RepoClear，官方月表自身滞后约两个月）要能安静通过，再留一个月余量。
STALE_GRACE_MONTHS = 3


def _month_sub(a, b):
    """a - b，单位为月；a/b 形如 'YYYY-MM'。"""
    return (int(a[:4]) * 12 + int(a[5:7])) - (int(b[:4]) * 12 + int(b[5:7]))


def audit_stale_cols():
    """逐列体检：哪一列离它本该有的月份差得离谱，或哪一条死列诈尸了。

    整个函数体裹在 except 里：这是一道**观察**，不是护栏。它自己出错绝不能把
    已经成功的一轮 monthly_run 带走 —— 那就本末倒置了。
    """
    try:
        stale, risen = [], []
        for t in sorted(_LAG_CACHE or load(os.path.join(HERE, 'build', 'roster.py'),
                                           'roster_stale').LAG):
            lag = due_lag(t)
            p = os.path.join(SERIES, f'{t}.csv')
            if lag is None or not os.path.exists(p):
                continue              # 横截面页没有披露节奏，也没有自己的 series
            due = _due_month(lag)     # 红点口径（LAG 本身），问的是「本该发了没有」
            if due is None:
                continue
            with open(p, encoding='utf-8', newline='') as f:
                rows = list(csv.reader(f))
            if len(rows) < 2:
                continue
            head, dead = rows[0], DEAD_COLS.get(t, {})
            for i, col in enumerate(head):
                if not i:
                    continue
                ms = [r[0] for r in rows[1:] if i < len(r) and r[i].strip()]
                if not ms:
                    continue          # 整列空：不是「变陈旧」，是从来没有过
                last = max(ms)
                if len(last) < 7 or not last[:4].isdigit():
                    continue          # 季度表等非「YYYY-MM」口径，不归本函数管
                if col in dead:
                    if _month_sub(last, dead[col][0]) > 0:
                        risen.append((t, col, dead[col][0], last))
                    continue
                behind = _month_sub(due, last)
                if behind > STALE_GRACE_MONTHS:
                    stale.append((t, col, last, due, behind))
        if stale:
            print(f'  🔴 陈旧列 {len(stale)} 条（落后本该有的月份 >{STALE_GRACE_MONTHS} 个月，'
                  f'且不在 DEAD_COLS 白名单里）——「NOCHANGE」说明不了它们还活着：')
            for t, col, last, due, behind in stale:
                print(f'     {t:6s} {col:44s} 止于 {last}，本该 {due}（落后 {behind} 个月）')
            print('     处置：确认是上游永久停发 → 写进 monthly_run.DEAD_COLS；'
                  '否则是这一列的解析静默失效了，按 README「第四类」补护栏。')
        if risen:
            print(f'  ⚠ DEAD_COLS 白名单有 {len(risen)} 条对不上了（登记为已停发，却又有了新数据）：')
            for t, col, reg, last in risen:
                print(f'     {t:6s} {col:44s} 登记止于 {reg}，实际已到 {last}')
            print('     处置：上游恢复发布了 → 从 DEAD_COLS 删掉该条，否则它会一直被豁免。')
    except Exception as e:                    # noqa: BLE001 —— 见 docstring
        print(f'  ⚠ 陈旧列审计自身出错（{type(e).__name__}: {e}）—— 不影响本轮发布。')


def builder(t):
    """→ 重新生成 `data/<t>.js` 的命令行；三种写法都找不到时返回 None。

    仓库里同时存在三种生成器，按下面的顺序试，**判据一律是「文件在不在」，
    不是「这个 ticker 叫什么名字」**：

      1. `build/<t>.py`            18 张单公司页。这一路里其实有两种实现，但对本函数
                                   完全一样（都是「build/<t>.py 在不在」）：
                                     · 11 家非半导体 —— 一家一份手写生成器；
                                     · 7 家台湾半导体 —— 只是一层薄壳，图列在共用底座
                                       `build/mrbase.py` + `build/mrspecs/<t>.py`
                                       （壳必须留着：删了它，第 3 条会把 data/<t>.js
                                        覆盖回 build/specs/<t>.py 的老图列）
      2. `build/<t 下划线版>.py`    横截面页：目录名 `exchanges-na` ↔ 生成器
                                   `build/exchanges_na.py`（连字符不能做模块名）
      3. `build/single.py <t>`     10 家新交易所：通用底座 + `build/specs/<t>.py`

    这个函数是「删掉一家不留残渣」的关键：它不认得任何一家的名字，所以删掉
    `build/specs/sgx.py` 之后本文件立刻不再知道有 sgx 这回事，不需要同步改分支。
    反过来，如果这里写成 `if t in EXCHANGES: 用 single.py`，那 EXCHANGES 就成了
    第二处必须同步的名单 —— 而删除操作漏掉第二处的后果是每天一条 FAIL。
    """
    p = os.path.join(HERE, 'build', f'{t}.py')
    if os.path.exists(p):
        return [sys.executable, p]
    p = os.path.join(HERE, 'build', t.replace('-', '_') + '.py')
    if os.path.exists(p):
        return [sys.executable, p]
    if os.path.exists(os.path.join(HERE, 'build', 'specs', f'{t}.py')):
        return [sys.executable, os.path.join(HERE, 'build', 'single.py'), t]
    return None


def series_fingerprint(t):
    """这家全部 series CSV 的内容指纹；文件不存在时那一份记为空。

    为什么按内容 hash 而不是 mtime：每个 fetch 模块都保证「没有新东西时输出字节完全
    不变」（fetch/ndaq.py、fetch/cboe.py、fetch/db1.py 的 update() 都写明了这一点），
    所以内容变了就是真的变了，而 mtime 每次改写都会动，判不出来。

    glob 而不是写死 `<t>.csv`：ndaq 写两张、lseg 写五张。
    排除 source_dates.csv —— 它是全仓共用的发布日台账，任何一家记一条都会让它变，
    拿它当触发器等于每家每天都重建。
    """
    h = hashlib.sha256()
    for p in sorted(glob.glob(os.path.join(SERIES, f'{t}*.csv'))):
        if os.path.basename(p) == 'source_dates.csv':
            continue
        h.update(os.path.basename(p).encode())
        with open(p, 'rb') as f:
            h.update(f.read())
    return h.hexdigest()


def one(t, force):
    """跑一家：抓取 → series 内容变了（或 --force）就重生成 data/<t>.js。

    返回 (状态串, 说明)。异常一律在这里吃掉转成 FAIL —— 调用方要保证一家的故障
    不影响其余各家。

    ## 触发器为什么是「指纹变了」而不是「update() 返回了新月份」（2026-08-08 改）

    旧写法 `if not added` 有一个不出声的漏洞：**慢腿回补不算「新月份」**。
    两腿源（一腿早、一腿晚，同一行的不同列）在回补那一轮里只是把已存在行的空格填上，
    `update()` 返回空 list，于是这里 return NOCHANGE，页面不重建 —— 而数据已经在
    series 里了。fetch/ndaq.py:1053 与 fetch/db1.py:1114 都明写「回补不计入返回值」。

    实测当时的现场（2026-08-08）：series/ndaq.csv 的 2026-07 行已有四个 IR 快腿列
    （402 / 4.1 / 56161 / 88），九个 nasdaqtrader 慢腿列空着，data/ndaq.js 的
    data_through 停在 2026-06，而运行结果是 `ndaq NOCHANGE`。ndaq 尤其糟，因为
    build/specs/ndaq.py:141 把头条指标定在**慢腿**上（share_us_cash_matched_*），
    所以页面的月份是被慢腿推动的 —— 偏偏慢腿没有触发器。

    这类停更的可怕之处是它**长得和健康的安静日一模一样**：fetch 成功所以没有 FAIL，
    没有 FAIL 就没有 3 天连击推送，roster 的红点又要等 LAG+GRACE 才亮。
    fetch/lseg.py:454 早先遇到同一个坑，是在那个模块内部返回「新建行 ∪ 本轮被回补的行」
    解决的；放在这里是同一个修法的模块无关版本，一次覆盖 ndaq、db1 与以后任何双腿源。

    代价：多算一次全文件 hash（series 里最大的一家几百 KB，可忽略）。
    """
    if not force and not_due(t):
        # 这两种情况以前共用一句「未到披露期，跳过下载」，而 2026-08-17 实测那天被
        # 跳过的 25 家**没有一家**真的「未到披露期」—— 闸门早在 08-01~08-12 就开了，
        # 真实原因全是后一种。那句话最误导的地方在于它听着完全无害（「太早了，当然
        # 没数据」），于是 tmx / db1 / lseg 的慢腿停更就一直躲在它后面没人看见。
        lag = due_lag(t)
        early = EARLY_BY.get(t, (EARLY, EARLY))
        due = lag and _due_month((lag[0] - early[0], lag[1] - early[1]))
        return 'NOCHANGE', (f'线上已追平候选月 {due}' if due else '闸门未开，跳过下载')
    fp = os.path.join(HERE, 'fetch', f'{t}.py')
    cmd = builder(t)
    if cmd is None:
        return 'FAIL', f'缺生成器：build/{t}.py 与 build/specs/{t}.py 都不存在'

    before = series_fingerprint(t)
    added = []
    if os.path.exists(fp):
        try:
            added = load(fp, f'fetch_{t}').update(SERIES, CACHE) or []
        except Exception as e:
            return 'FAIL', f'{type(e).__name__}: {e}'
    else:
        return 'FAIL', f'缺 fetch/{t}.py（无法自动更新，需人工补数据）'
    touched = series_fingerprint(t) != before

    if not added and not touched and not force:
        return 'NOCHANGE', ''
    try:
        out = sh(cmd)
    except Exception as e:
        return 'FAIL', f'build 失败: {e}'
    if added:
        return 'NEW', ','.join(added)
    # 指纹变了但没有新月份 = 慢腿回补（或发布方改了历史值）。单独标一个状态，
    # 因为这两件事在运行日志里必须能分开看：一个是「本月数据到了」，
    # 一个是「上个月的数据后来才补齐」。
    return 'REBUILT', ('慢腿回补/历史改数' if touched else out.splitlines()[-1][:60])


def mops_remarks():
    """刷新 series/mops_remarks.csv（七家台湾半导体的 MOPS 備註原文），返回失败清单。

    ══ 为什么它不是 ticker、也不进 TICKERS ══
    既有 fetch 模块是「一个 ticker 一份 <ticker>.csv」，这个不是：**一份 CSV 装七家**
    （一行 = 一家 × 一个申报月），源也不是任何一家的公告，而是 MOPS 的**全市场**月档。
    塞进按 ticker 遍历的循环意味着七家各跑一次 → 同一份 200KB 的全市场档下七遍、
    打七次上游（源站会限流，见 fetch/mops_remarks.py 口径坑 2a），而后六次必然返回
    「无新月份」。挂到某一家名下更糟：那一家被删掉，另外六页的备注列跟着消失。
    所以它和 fee_rates / fx 同类 —— 公共表，独立一步，一轮跑一次。

    ══ 为什么不进 build/roster.py，也不给它 LAG ══
    roster 的 LAG / META 是**按页**登记的（导航目录 + 首页红点），而这条序列没有页、
    没有 data/<t>.js、没有 data_through。硬登记会有两个坏处，都是净负的：
      · 只加 LAG 不加 GROUPS —— 那一行谁都不读（LAG 只在 GROUPS 遍历与 not_due 里取），
        是一条骗人的死配置：下一个人会以为闸门归它管；
      · 连 GROUPS 一起加 —— roster.read() 找不到 data/mops_remarks.js，首页多一个
        永远空白的卡片；check_registry() 还要因为两张名单对不上天天告警。
    真正的闸门也不该由 LAG 来当：它的开闸条件是 TWSE OpenAPI 的 `資料年月` 翻页，
    而那是**证交所把全市场汇总完**才翻的（2026-07 那期 出表日期 1150813 = 月末后
    第 13 天），不是七家里任何一家的公告节奏 —— 七家全部申报完只是它的**下界**。
    这个条件模块自己每轮问一次（一条 ~600KB 的 JSON 请求，比 fx 的 10 条 SDMX 还便宜），
    问到的是官方事实，比照日历猜的 `LAG − EARLY` 严格更准。**用事实闸门就别再叠一层
    日历闸门**：叠上去只会在证交所翻早的那个月把页面卡住，而这正是 not_due 要防的事。

    ══ 为什么有新月份就要重跑那七页（**这一步不能省**）══
    与 fee_rates 同一个理由，而且更硬：读这张表的是**单公司页**，那七家这一轮很可能
    整轮都没被碰过。时序是错开的 —— 各家自己的月营收在次月第 2-15 天陆续到，
    而全市场汇总要等最后一家申报完（实测第 13 天），所以「A 家的 M 月数据到了」与
    「M 月的備註到了」几乎不在同一天。等到備註到的那天，七家的 not_due 早已判定
    「线上已追平 M 月」→ 全部 NOCHANGE、连 fetch 都不下，更不会重建页面。
    没有这一步，`series/mops_remarks.csv` 更新了而七页永远读不到，症状是
    **每个月的当月引文与核对表末行永久缺席**（上个月的却在，因为下个月重建时补上了）——
    一种看上去完全正常的静默停更，正是 one() 的 docstring 里那条「长得和健康的安静日
    一模一样」的老毛病。
    也因此**不能**用「这一轮已经建过就跳过」来省事：本函数跑在按家循环**之后**，
    循环里那次 build 读到的还是旧 CSV。要么全跑，要么这一轮的备注就是丢的。

    ══ 失败为什么计入 fails（PARTIAL），但不阻断 ══
    这条序列**只喂注脚**：brief 里一句引文 + 核对表一列，页面上没有任何数值、任何一张图、
    任何 data_through 依赖它。抓失败时 build/mrbase.py 的 _remark() 返回 None，
    七页**照发**，只是一个字都不说 —— 它刻意不退化成「公司没填」（那是一句我们读不到的
    事实断言）。所以降级后的页面是**残缺但诚实**的，不属于本仓「宁可不发也不发错」要拦的
    「错」；为一句注脚扣住七页 20 多张图的正确营收数据，代价明显更大。
    （何况这里也没有「只扣七页」这个选项：提交是整个 data/ 一起走的，抛异常等于 34 张页
      今天全部不发。）
    但**失败必须响**：页面缺一句话没有任何视觉异常，roster 也不会给它红点（它没有页），
    per-ticker 日志里更不会出现 —— 末行的 PARTIAL 是它唯一的故障信号，与 fx 同理。
    ⇒ 这套语义与 mrbase._remark() 现有的「读不到只告警不阻断」是自洽的，底座那侧不用改。

    `--only` 不跳过本步（沿用 fee_rates / fx / build_cross 的既有行为）：调试单家时
    仍会问一次 TWSE，有新月份时仍会重建那七页。
    """
    p = os.path.join(HERE, 'fetch', 'mops_remarks.py')
    if not os.path.exists(p):
        return []
    try:
        mod = load(p, 'fetch_mops_remarks')
        added = mod.update(SERIES, CACHE) or []
    except Exception as e:
        print(f'{"mops_remarks":<10} FAIL     {type(e).__name__}: {str(e)[:120]}')
        return ['mops_remarks']
    if not added:
        print(f'{"mops_remarks":<10} NOCHANGE 无新月份')
        return []
    print(f'{"mops_remarks":<10} NEW      {len(added)} 个月: {", ".join(added[-6:])}')
    bad = []
    # 消费者名单**只有一份**，就在 fetch 模块的 TICKERS 里（它已经是 slug → 台股代号的
    # 权威映射）。在这里另抄一份七家的清单，就等于给「删掉一家」多加一处必须同步的地方
    # —— 与 builder() 那条「不认得任何一家的名字」是同一条规矩。
    for t in mod.TICKERS:
        cmd = builder(t)
        if cmd is None:
            continue            # 这一页已被删掉：跳过，不记失败（同 build_cross 的处理）
        try:
            sh(cmd)
        except Exception as e:
            print(f'{t:<10} FAIL     备注更新后重建失败: {str(e)[:100]}')
            bad.append(t)
    return bad


def fee_rates():
    """刷新季度费率表 series/fee_rates.csv，返回失败清单（成功时空表）。

    它不是 ticker，所以不走 TICKERS 那条按家循环的路：一张表六家共用，
    由 fetch/fee_rates.py 内部逐家合并。它自己保证「要么这一家全写、要么这一家不写」。

    有新季度时 data/*.js 会跟着变（六个生成器读这张表），所以必须跑在 build_cross 与
    roster 之前 —— 否则本轮的费率更新要等下一次跑才会出现在页面上。
    """
    p = os.path.join(HERE, 'fetch', 'fee_rates.py')
    if not os.path.exists(p):
        return []
    try:
        added = load(p, 'fetch_fee_rates').update(SERIES, CACHE) or []
    except Exception as e:
        print(f'{"fee_rates":<10} FAIL     {type(e).__name__}: {str(e)[:120]}')
        return ['fee_rates']
    if not added:
        print(f'{"fee_rates":<10} NOCHANGE 无新季度')
        return []
    # 有新季度 → 六个用它的生成器都要重跑，否则 CSV 变了而页面还是旧费率
    print(f'{"fee_rates":<10} NEW      {len(added)} 条: {", ".join(f"{c} {p_}" for c, p_ in added[:6])}')
    bad = []
    for t in ['axp', 'cme', 'lpla', 'hkex', 'msci', 'schw']:
        try:
            sh([sys.executable, os.path.join(HERE, 'build', f'{t}.py')])
        except Exception as e:
            print(f'{t:<10} FAIL     费率更新后重建失败: {str(e)[:100]}')
            bad.append(t)
    return bad


def fx():
    """刷新公共汇率底座 series/fx.csv，返回失败清单（成功时空表）。

    和 fee_rates 一样**不是 ticker**，所以不走 TICKERS 那条按家循环的路：它不属于
    任何一家公司，是横截面页的公共底座 —— CME 报张数、HKEX 报港币金额、JPX 报日元，
    要放进同一张「谁在跑赢」的图，先得把币种统一到美元（定基名义额里的基期汇率项
    也取自这张表的 2019-01 行）。挂在某一家的 ticker 下面，那一家一旦被删掉，
    另外十一家的分母跟着消失。

    ══ 为什么**不**给它套 not_due 的下载闸门 ══
    那道闸门的前提是「M 月的数据要等 M+1 月才发」。ECB 恰恰不是：每个 TARGET2 营业日
    14:15 CET 定盘、约 16:00 CET 发布，M 月这一行在 **M 月最后一个营业日当天**就齐了
    （见 fetch/fx.py 的「发布节奏」节）。给它套闸门 = 让全仓唯一一条当月就能定稿的
    序列白等到次月，横截面页跟着晚一整轮。每天跑的代价是 10 条 SDMX 请求
    （实测 17-32 秒），没有新月份时返回 [] 且 CSV 逐字节不变。

    ══ 为什么失败不吞 ══
    汇率是**所有**跨市场图的换算层。它悄悄冻在上个月，页面上不会有任何异常表现 ——
    没有断笔、没有空值、没有红点（fx.csv 不上任何页面抬头），只是份额与增长整体
    偏一点点。所以这里返回 ['fx'] 让总状态变 PARTIAL：末行是它唯一的故障信号。

    ══ 为什么必须跑在 build_cross 之前 ══
    读这张表的是横截面页的生成器。fx 在后、生成器在前的话，本轮的汇率更新要等到
    下一次跑才会出现在页面上；而下一次跑时 fx.csv 已经没有新月份了（NOCHANGE），
    也就不会有人再去催那些生成器 —— 更新会永久停在「差一轮」的状态。
    """
    p = os.path.join(HERE, 'fetch', 'fx.py')
    if not os.path.exists(p):
        return []
    try:
        added = load(p, 'fetch_fx').update(SERIES, CACHE) or []
    except Exception as e:
        print(f'{"fx":<10} FAIL     {type(e).__name__}: {str(e)[:120]}')
        return ['fx']
    if not added:
        print(f'{"fx":<10} NOCHANGE 无新月份')
        return []
    # 这里**不**主动重跑任何生成器：读 fx 的只有横截面页，而 build_cross 每轮无条件
    # 全跑一遍（它没有 not_due 闸门），紧接在本函数之后 —— 再喊一次是重复劳动。
    # fee_rates 要自己重跑六家，是因为读它的是**单公司页**，那六家可能整轮都没被碰过。
    print(f'{"fx":<10} NEW      {len(added)} 个月: {", ".join(added[-6:])}')
    return []


def build_cross(force):
    """横截面页：成员齐了才生成。返回**失败**的页面清单，交给 main() 计入总状态。

    返回失败而不是成功清单，是因为这几页没有自己的披露节奏 —— roster 给它们 lag=None，
    首页永远不给它们判红点。末行总状态是它们唯一的故障信号，吞掉就等于没有信号。
    （「成员没齐」不算失败：每个 builder 都会打印原因并以退出码 0 正常结束，
      等成员齐了下次自然会生成。exchanges12 在基期常数补齐之前一直走这条路。）

    没有生成器的那一条**跳过而不是记失败**：CROSS 里的名字可以先于生成器登记，
    也可以在删页时先删生成器 —— 两种半成品状态都不该让整轮变 PARTIAL。
    """
    failed = []
    for t in CROSS:
        cmd = builder(t)
        if cmd is None:
            continue
        try:
            sh(cmd)
        except Exception as e:
            print(f'{t:<10} FAIL     {type(e).__name__}: {e}')
            failed.append(t)
    return failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()

    # 第一件事就是核对依赖版本：后面任何一步的怪异结果都可能是它引起的，
    # 所以这行必须打在所有 fetch/build 输出之前，让人一眼看到「地板换过了」。
    report_deps()
    # 紧接着核对注册名单。同样要打在所有 fetch/build 输出之前 —— 它解释的是
    # 「为什么日志里没有这一家」，而那正是一条**不会出现在日志里**的故障。
    report_registry()

    # --dry-run 不 commit/push，脏树时反而正是要看「如果跑会发生什么」，故只警告不拦。
    dirty = guard_dirty_tree()
    if dirty and not a.dry_run:
        print('data/ 以外有未提交改动：')
        print(dirty)
        print('FAILED 工作树有未提交改动，拒绝无人值守发布（请人工 commit 或还原后重跑）')
        sys.exit(1)
    if dirty:
        print('警告：data/ 以外有未提交改动，正式跑会被护栏拦下：')
        print(dirty)

    # 与 origin 对齐。位置很关键（工作树刚验过干净、且尚未开始构建），
    # 挪到末尾发布段里会引入一个新故障 —— 理由写在 sync_with_origin 的 docstring。
    sync_with_origin(a.dry_run)

    # ── preflight：规格表体检（工作树检查之后、下载之前）────────────────────
    # series/contract_specs.csv 是定基名义额的**唯一常数源**，而它的失效方式是
    # 「填错了图上完全看不出来」（乘数错一位，柱子整体高一截，看上去完全像真的）。
    # build/check_specs.py 就是为这件事写的，但在此之前它没有任何调用方 ——
    # 一道没人跑的闸门等于没有闸门。放在下载之前：抓完 28 家再发现常数表坏了，
    # 那一轮抓取全白费，且已写进 series/ 的部分还要人工回滚。
    sys.path.insert(0, os.path.join(HERE, 'build'))
    import check_specs                                   # noqa: PLC0415
    if check_specs.main([]) != 0:
        print('FAILED specs 规格表体检未通过（逐条错误见上），拒绝在这个状态下发布')
        sys.exit(1)

    # preflight 的第二道：build/test_guards.py —— payload_guard 与 brief 两条护栏的单元测试。
    # 它此前也没有任何自动调用方（与 check_specs 接进来之前一模一样的处境）。
    #
    # 为什么放在这里而不是收尾：它查的是**代码**，不是这一轮的数据。payload_guard 是每个
    # builder 写文件前必过的那一道，它的 nan/inf 正则一旦被改松，这一轮 28 家会把
    # `$nanbn` 之类的格式化残骸写进 data/*.js —— 浏览器照渲染、退出码照样 0。这种故障
    # 不该等抓完 28 家、生成完 34 页才发现；放在下载之前，人改完重跑的代价最小。
    #
    # 硬拦而不是告警，与 check_specs 同一条理由：护栏坏了还继续发，等于这一轮的每一页
    # 都没有护栏。代价是「那天 28 家都不更新」，但 preflight 阶段还没抓任何东西，
    # 没有半写的 series/ 要人工回滚。
    #
    # 两条已知边界，写下来免得下一个人以为它比实际强：
    #   · 它的 B 组（拿 data/*.js 里已发布的 brief 原文重过一遍 render()）与 D 组
    #     （series/mops_remarks.csv 的每条备注原文）都是语料驱动的，而 preflight 时那两份
    #     语料还是**上一轮**的 —— 本轮新抓到的备注要到下一轮 preflight 才被过一遍。
    #   · 也正因为语料驱动，某家公司填了一条越界的备注原文会在这里硬拦整轮。那不是误报
    #     （D 组那两条用例本来就是「该重新审视上限」的信号），但要知道它拦得住整轮。
    if run_gate('test_guards（payload_guard / brief 单元测试）',
                [sys.executable, os.path.join(HERE, 'build', 'test_guards.py')],
                quiet_on_pass=True) != 0:   # 通过时逐条 "ok" 是纯噪声，且它没有 🟡 那一档
        print('FAILED payload_guard / brief 护栏单元测试未通过（逐条见上），'
              '拒绝在护栏坏掉的状态下生成本轮页面')
        sys.exit(1)

    todo = [t for t in a.only.split(',') if t] or TICKERS
    bad = [t for t in todo if t not in TICKERS]
    if bad:
        print(f'FAILED 未知 ticker: {bad}')
        sys.exit(1)

    ok, fails, months = [], [], {}
    for t in todo:
        st, msg = one(t, a.force)
        print(f'{t:<10} {st:<8} {msg}')
        if st == 'FAIL':
            fails.append(t)
        elif st in ('NEW', 'REBUILT'):
            ok.append(t)
            if st == 'NEW':
                months[t] = msg

    # MOPS 備註原文：七家台湾半导体页的 brief 引文与核对表那一列共用一份 series，
    # 不是 ticker、不进 TICKERS（理由与失败语义全在 mops_remarks() 的 docstring 里）。
    # **必须跑在按家循环之后、roster 之前**：它的源是全市场汇总档，比各家自己的月营收
    # 晚到几天，那时七家的 not_due 早已全部 NOCHANGE —— 有新月份就由它自己去催那七页重建。
    fails += mops_remarks()

    # 季度费率表：AXP / CME / LPLA / HKEX / MSCI / SCHW 六页靠它反解「隐含收入」与
    # 「有效费率」。它是**季度**的，不该每天下；但也不能不管 —— 没人维护的那阵子它冻在
    # 2026-Q2，月度数字照常更新而费率那一层是死的，页面上完全看不出来。
    # 所以顺带查一次（几个 HTTP 请求），有新季度才写。失败只记一条，不拖累 28 家月度更新。
    fails += fee_rates()

    # 汇率底座：横截面页把张数 / 股数 / 本币成交额折成同一个美元口径全靠它。
    # **必须在 build_cross 之前**（否则本轮的汇率更新永远差一轮），且**不套下载闸门**
    # （ECB 在数据月之内就发完了）—— 两条理由都写在 fx() 的 docstring 里。
    fails += fx()

    # 横截面页失败必须计入 fails。它们没有自己的披露节奏（roster 给 lag=None，
    # 首页永远不给它们判红点），末行总状态是这几页唯一的故障信号 ——
    # 在这里吞掉，页面会无声停在旧月份，而调度器读到的仍是 PUBLISHED。
    fails += build_cross(a.force)
    roster(todo)

    # 陈旧列审计：这一轮唯一「即使 28 家全 NOCHANGE 也照样开口」的检查。
    # 上面每一家的 NOCHANGE 都只说明「今天没抓到新的」，说明不了「这一列还活着」。
    audit_stale_cols()

    # ── 收尾闸门：产物体检（34 页全部生成完之后、commit 之前）─────────────────
    # 这两道与 preflight 那两道的分界线是「查配置/代码」还是「查产物」：
    # check_specs 查常数表、test_guards 查护栏代码，都与本轮数据无关，所以能提前跑；
    # verify_pages 与 check_yoy_caliber 查的是 data/*.js 本身，preflight 阶段那些文件
    # 还是上一轮的产物 —— 在那儿跑只能证明上一轮没坏，证明不了这一轮。
    #
    # 放在 commit 之前而不是之后：它们要拦的两类缺陷都是「不报错、发得出去、看不出错」——
    # 数组比 xlabels 长的那几点画不出来但照样参与纵轴量程（图被压扁，没有任何提示），
    # 一条画着 12 个月滚动口径的同比线读者只会当成单月（CONTRACT §6 全站只认单月）。
    # 本仓第一条规矩是「宁可不发也不发错」，所以这两道报硬错时整轮不发。
    #
    # ⚠️ 代价说清楚：一页坏 → 当天 34 页都不更新，而不是只跳过那一页。这与上面「一家失败
    # 不中止全局」看着相反，其实是同一条原则的两侧：逐家隔离处理的是「某家的新数据没抓到」
    # （那家保持自己的旧数据，首页红点看得出旧），这里处理的是「已经生成出来的产物是错的」
    # （发出去看不出错）。没有做成逐页放行，是因为两道闸门给的都是整份报告，要按页拆结论
    # 就得解析它们的输出 —— 它们各有主、行文随时会改，那种耦合比它省下的可用性贵。
    #
    # ⚠️ 退出码分不出「判据报了硬错」与「判据自己崩了」（Python 未捕获异常也是 1）。
    # 所以上面 run_gate 把两道闸门的完整输出原样转印：崩了会有 traceback，读日志的人
    # 一眼分得开，但**脚本分不开**，调度器看到的都是 FAILED。
    #
    # 即使 28 家全 NOCHANGE 也照跑（与 audit_stale_cols 同一条理由）：NOCHANGE 只说明
    # 今天没抓到新数据，说明不了 data/*.js 此刻是对的 —— 有人手改过一页、或上一轮留下的
    # 错产物，只有每轮真跑一次才会被发现。实测两道合计约 5 秒（verify_pages 0.9s、
    # check_yoy_caliber 全站 4.0s），相对 28 家抓取可以忽略，不值得为省它做增量优化。
    #
    # check_yoy_caliber 跑全站而不是只跑本轮重建的那几页（它支持 `--page`，只跑一页
    # 0.7s、全站 4.0s，差 3.3 秒）：它的 R5 判的是 §6.2 白名单上那几张图还在不在、
    # 还自不自称滚动口径，而那几页这一轮多半根本没重建 —— 只扫重建过的页会让 R5 常年不响。
    # 两道都不传 `--json`，所以不会往仓库里落产物、不会弄脏 PUBLISH 之外的路径。
    #
    # --dry-run 也照拦（与 guard_dirty_tree / sync_with_origin 在 dry-run 下只告警**不同**）：
    # 那两处降级是因为它们查的是「发布这件事的前提」，而 dry-run 本来就不发布；
    # 这两道查的是产物，而产物在 dry-run 里是**真生成出来的** —— 试跑要能回答
    # 「正式跑会不会被拦」，降成告警就答不了了。
    gate_fail = []
    # verify_pages 不加参数 = 用它自己的默认：HTTP 段只抓它默认名单里那 5 张横截面页的壳
    # 与静态资源，payload 段扫全部 data/*.js。默认由它自己定，这里不替它挑。
    if run_gate('verify_pages（页面壳 + payload 结构）',
                [sys.executable, os.path.join(HERE, 'build', 'verify_pages.py')]) != 0:
        gate_fail.append('verify_pages')
    if run_gate('check_yoy_caliber（同比口径，CONTRACT §6.6）',
                [sys.executable, os.path.join(HERE, 'tools', 'check_yoy_caliber.py')]) != 0:
        gate_fail.append('check_yoy_caliber')
    # 两道都跑完再判，不在第一道失败时短路：一次跑出全部问题，人只需要修一遍、重跑一次。
    if gate_fail:
        print(f'FAILED 产物闸门未通过（{"、".join(gate_fail)}；逐条见上），'
              f'本轮生成的 data/*.js 不提交、不推送')
        sys.exit(1)

    def nothing():
        """「没有任何东西可发布」的统一出口 —— 有失败就必须让调度器看见。"""
        print('NOTHING_TO_DO' if not fails
              else f'FAILED 无更新且 {len(fails)} 家失败: {",".join(fails)}')

    if not data_changed() and not a.force:
        nothing()
        return
    if a.dry_run:
        print(sh(['git', 'diff', '--stat', '--'] + PUBLISH))
        print(f'DRY_RUN {len(ok)} 家有更新')
        return

    sh(['git', 'add'] + PUBLISH)          # 提交范围收窄为显式路径（见 PUBLISH 的注释）
    if not sh(['git', 'diff', '--cached', '--name-only']):
        # --force 会跳过上面的 data_changed()，所以这个兜底分支是 --force 路径的唯一出口，
        # 必须和上面那个用同一套口径 —— 否则 --force 跑时 28 家全挂，末行仍是 NOTHING_TO_DO。
        nothing()
        return
    label = ', '.join(f'{t} {m}' for t, m in months.items()) or f'{len(ok)} 家重建'
    sh(['git', 'commit', '-m', f'更新数据: {label}'])
    env = dict(os.environ, GIT_SSH_COMMAND='ssh -o BatchMode=yes')
    r = subprocess.run(['git', 'push'], cwd=HERE, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        print(f'FAILED push 失败: {r.stderr[-400:]}')
        sys.exit(1)
    sha = sh(['git', 'rev-parse', '--short', 'HEAD'])
    print('已推送：https://hzhan7.github.io/Monthly-OP-Dashboards/')
    if fails:
        print(f'PARTIAL {sha} {len(ok)} ok / {len(fails)} fail: {",".join(fails)}')
    else:
        print(f'PUBLISHED {sha} {len(ok)} {label}')


def roster(_todo):
    """重建 data/roster.js —— 首页与各页导航的目录，含各家数据月份与新鲜度。"""
    load(os.path.join(HERE, 'build', 'roster.py'), 'roster').main()


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        traceback.print_exc()
        print(f'FAILED {type(e).__name__}: {e}')
        sys.exit(1)
