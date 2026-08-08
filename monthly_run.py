# -*- coding: utf-8 -*-
"""总仓月度 routine —— 逐家检查新数据 → 重生成看板 → 一次性提交推送。

用法:
    python3 monthly_run.py                    # 正常执行（有新数据才提交推送）
    python3 monthly_run.py --only cme,cboe    # 只跑指定几家
    python3 monthly_run.py --dry-run          # 抓取与生成都做，但不 commit/push
    python3 monthly_run.py --force            # 数据没变也重新生成并推送（改了图表代码后用）

跑的东西分三类，删一家只动第一类的一行（完整清单见 docs/CRON_WIRING.md）：
    TICKERS   21 家有自己数据源的公司（12 家其它 + 9 家新交易所），逐家抓 → 逐家生成
    公共表    fee_rates（季度费率，六页共用）与 fx（月度汇率，横截面页共用）
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
扩到 21 家后同样的写法意味着：TSMC 官网当天抽风，CME、Cboe、HKEX 三家已经抓到的新数据也一起
不发布 —— 一家的故障惩罚了另外二十家。所以这里改成**逐家隔离**：失败的那家跳过（线上仍是它
自己的旧数据，不会变成错数据），成功的照常发布，失败清单打在总状态里让人看得见。
9 家新交易所随时可能被用户删掉，这条隔离对它们尤其要紧：删剩的残渣最多让一家 FAIL，
不会让另外二十家停发。

护栏保持不变，且仍然是「宁可不发也不发错」:
  · 提交范围只有 `data/` 与 `series/`；这两个目录以外有未提交改动就直接 FAILED 退出（见 guard_dirty_tree）
  · 任何一家的 fetch 解析出缺列 / 月份对不上，由该家的 fetch 模块抛异常 → 记 FAIL，不写数据
  · 页面的新鲜度只绑 payload 的 data_through（构建日期只写 data/*.js 首行注释，不进 payload）。
    抓取失败那家不写 series、不重生成，data_through 原地不动，首页按 roster 的 LAG + GRACE
    给它打红点 —— 旧数据看得出是旧的，不会被当成新的
"""
import argparse
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
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
SERIES = os.path.join(HERE, 'series')
CACHE = os.path.join(HERE, 'cache')
REQUIREMENTS = os.path.join(HERE, 'requirements.txt')
# 缺了不算故障的包：有代码级回落通道，理由写在 requirements.txt 对应那段。
OPTIONAL_DEPS = {'curl_cffi'}

# 9 家新增交易所（2026-08 接入）—— **一行一条，删掉一家就删掉它这一行**。
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
           'msci', 'spgi', 'axp', 'tsm'] + EXCHANGES
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
    # 只有下面这四家的 LAG−5 会**晚于**最早发布日，非单独给不可。

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


# 本脚本自己会写、也自己会提交的路径。护栏与提交范围必须用同一份清单 ——
# 两者一旦不一致，本脚本就会亲手把工作树弄脏，然后被自己的护栏拦死。
# （曾经只写 data：fetch 往 series/*.csv 追加新月份，而 series 是 tracked 的，
#  于是「第一次成功发布」这件事本身留下 ` M series/xxx.csv`，下一次跑必被拦，
#  且不是拦某一家，是 12 家一起停 —— 无人值守管道只能成功发布一次。）
PUBLISH = ['data', 'series']


def guard_dirty_tree():
    """返回**本脚本管辖范围之外**的未提交改动（porcelain 文本），干净时为空串。

    这个仓库是手写手改的：charts.js / page.js / index.html 经常处于改到一半的状态。
    没有这道检查时，cron 会把半成品连同数据一起 commit 成「更新 YYYY-MM 数据」推到
    公开 Pages —— 页面变半成品，而 commit message 完全看不出发生了什么。
    所以提交范围收窄成 PUBLISH 里那几条显式路径，并在此之外拒绝脏树。
    """
    return sh(['git', 'status', '--porcelain', '--', '.'] + [f':!{p}' for p in PUBLISH])


def _body(text):
    """去掉 data/*.js 首行的构建日期注释，只留数据正文。"""
    return text.split('\n', 1)[1].strip() if '\n' in text else ''


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

    有了这个判断，本脚本可以每天跑而不是挑几天跑：12 家的披露日从次月 1 号散到 20 号，
    要覆盖全部窗口就得天天跑；但天天把 12 个源全下一遍纯属浪费（也给对方站点添堵）。
    所以先用本地已有的 data_through 对照 LAG 表，够新的直接跳过，一个字节都不下。
    --force 会绕过它（改了图表代码后要全量重建）。

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
    r = load(os.path.join(HERE, 'build', 'roster.py'), 'roster_due')
    lag = r.LAG.get(t)
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
    today = datetime.date.today()
    for k in range(6):
        n = today.year * 12 + today.month - 1 - k      # 候选月的下个月（k=0 即本月）
        y, m = n // 12, n % 12 + 1
        end = datetime.date(y, m, 1)                   # 候选月月末 + 1 天
        cy, cm = (y, m - 1) if m > 1 else (y - 1, 12)  # 候选月本身
        qe = cm % 3 == 0
        days = lag[1] if qe else lag[0]
        early = EARLY_BY.get(t, (EARLY, EARLY))[1 if qe else 0]
        # end 已是「月末后第 1 天」，故偏移量减 1，闸门才真的落在月末后第 (days-early)
        # 天（理由与实测见 docstring 末节）。max(0,…) 仍把下界钉在次月 1 号。
        if today >= end + datetime.timedelta(days=max(0, days - early - 1)):
            return through >= f'{cy}-{cm:02d}'
    return False


def builder(t):
    """→ 重新生成 `data/<t>.js` 的命令行；三种写法都找不到时返回 None。

    仓库里同时存在三种生成器，按下面的顺序试，**判据一律是「文件在不在」，
    不是「这个 ticker 叫什么名字」**：

      1. `build/<t>.py`            既有 14 页，一家一份手写生成器
      2. `build/<t 下划线版>.py`    横截面页：目录名 `exchanges-na` ↔ 生成器
                                   `build/exchanges_na.py`（连字符不能做模块名）
      3. `build/single.py <t>`     9 家新交易所：通用底座 + `build/specs/<t>.py`

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
        return 'NOCHANGE', '未到披露期，跳过下载'
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

    # ── preflight：规格表体检（工作树检查之后、下载之前）────────────────────
    # series/contract_specs.csv 是定基名义额的**唯一常数源**，而它的失效方式是
    # 「填错了图上完全看不出来」（乘数错一位，柱子整体高一截，看上去完全像真的）。
    # build/check_specs.py 就是为这件事写的，但在此之前它没有任何调用方 ——
    # 一道没人跑的闸门等于没有闸门。放在下载之前：抓完 12 家再发现常数表坏了，
    # 那一轮抓取全白费，且已写进 series/ 的部分还要人工回滚。
    sys.path.insert(0, os.path.join(HERE, 'build'))
    import check_specs                                   # noqa: PLC0415
    if check_specs.main([]) != 0:
        print('FAILED specs 规格表体检未通过（逐条错误见上），拒绝在这个状态下发布')
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

    # 季度费率表：AXP / CME / LPLA / HKEX / MSCI / SCHW 六页靠它反解「隐含收入」与
    # 「有效费率」。它是**季度**的，不该每天下；但也不能不管 —— 没人维护的那阵子它冻在
    # 2026-Q2，月度数字照常更新而费率那一层是死的，页面上完全看不出来。
    # 所以顺带查一次（几个 HTTP 请求），有新季度才写。失败只记一条，不拖累 12 家月度更新。
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
        # 必须和上面那个用同一套口径 —— 否则 --force 跑时 12 家全挂，末行仍是 NOTHING_TO_DO。
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
