# -*- coding: utf-8 -*-
"""总仓月度 routine —— 逐家检查新数据 → 重生成看板 → 一次性提交推送。

用法:
    python3 monthly_run.py                    # 正常执行（有新数据才提交推送）
    python3 monthly_run.py --only cme,cboe    # 只跑指定几家
    python3 monthly_run.py --dry-run          # 抓取与生成都做，但不 commit/push
    python3 monthly_run.py --force            # 数据没变也重新生成并推送（改了图表代码后用）

输出：每家一行 "<ticker> <状态> <说明>"，stdout **最后一行**是总状态，供调度任务判断：
    NOTHING_TO_DO                 12 家都没有新数据（正常，等下次）
    PUBLISHED <sha> <n> <月份串>  有 n 家更新并已推送
    PARTIAL <sha> <n> ok / <m> fail   有更新也有失败，已推送成功的那部分
    FAILED <why>                  一家都没成功，或工作树不干净 / push 失败

每家的状态（第二列）:
    NEW <月>        抓到新月份并已重生成
    NOCHANGE        官方还没发新数据，或数据与线上一致
    FAIL <原因>     抓取或解析失败；该家保持线上旧数据不动

## 为什么一家失败不中止全局

单公司仓库的老脚本是「一有问题就整体退出」，那时候只有一家，退出=什么都不做，代价为零。
扩到 12 家后同样的写法意味着：TSMC 官网当天抽风，CME、Cboe、HKEX 三家已经抓到的新数据也一起
不发布 —— 一家的故障惩罚了另外十一家。所以这里改成**逐家隔离**：失败的那家跳过（线上仍是它
自己的旧数据，不会变成错数据），成功的照常发布，失败清单打在总状态里让人看得见。

护栏保持不变，且仍然是「宁可不发也不发错」:
  · 提交范围只有 `data/`；`data/` 以外有未提交改动就直接 FAILED 退出（见 guard_dirty_tree）
  · 任何一家的 fetch 解析出缺列 / 月份对不上，由该家的 fetch 模块抛异常 → 记 FAIL，不写数据
  · 页面的新鲜度只绑 payload 的 data_through（构建日期只写 data/*.js 首行注释，不进 payload）。
    抓取失败那家不写 series、不重生成，data_through 原地不动，首页按 roster 的 LAG + GRACE
    给它打红点 —— 旧数据看得出是旧的，不会被当成新的
"""
import argparse
import datetime
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

# 顺序 = 首页与导航的展示顺序，也是这里的执行顺序（无依赖，纯为日志好读）
TICKERS = ['cost', 'ibkr', 'schw', 'lpla', 'hood', 'cme', 'cboe', 'hkex',
           'msci', 'spgi', 'axp', 'tsm']
# 横截面页没有自己的数据源，等成员都更新完之后再生成
CROSS = ['exchanges', 'wealth']

# 下载闸门比 roster 的 LAG 提前几天开（见 not_due 的 docstring）。
# 3 天是照实测发布日反推的：LAG 是给红点用的、刻意给宽，减 3 天之后各家的开闸日
# 正好落在实测发布日当天或前一天（cost LAG 7 → 第 4 天开闸，实测 8/5 发布 = 第 4 天）。
# 5 天是照实测发布日反推的。**别为了「更精确」把它调小**：LAG 是给红点用的上界，
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
        if today >= end + datetime.timedelta(days=max(0, days - early)):
            return through >= f'{cy}-{cm:02d}'
    return False


def one(t, force):
    """跑一家：抓取 → 有新月份（或 --force）就重生成 data/<t>.js。

    返回 (状态串, 说明)。异常一律在这里吃掉转成 FAIL —— 调用方要保证一家的故障
    不影响其余各家。
    """
    if not force and not_due(t):
        return 'NOCHANGE', '未到披露期，跳过下载'
    fp = os.path.join(HERE, 'fetch', f'{t}.py')
    bp = os.path.join(HERE, 'build', f'{t}.py')
    if not os.path.exists(bp):
        return 'FAIL', f'缺 build/{t}.py'

    added = []
    if os.path.exists(fp):
        try:
            added = load(fp, f'fetch_{t}').update(SERIES, CACHE) or []
        except Exception as e:
            return 'FAIL', f'{type(e).__name__}: {e}'
    else:
        return 'FAIL', f'缺 fetch/{t}.py（无法自动更新，需人工补数据）'

    if not added and not force:
        return 'NOCHANGE', ''
    try:
        out = sh([sys.executable, bp])
    except Exception as e:
        return 'FAIL', f'build 失败: {e}'
    return 'NEW' if added else 'REBUILT', (','.join(added) if added else out.splitlines()[-1][:60])


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


def build_cross(force):
    """横截面页：成员齐了才生成。返回**失败**的页面清单，交给 main() 计入总状态。

    返回失败而不是成功清单，是因为这两页没有自己的披露节奏 —— roster 给它们 lag=None，
    首页永远不给它们判红点。末行总状态是它们唯一的故障信号，吞掉就等于没有信号。
    （「成员没齐」不算失败：两个 builder 都会打印原因并以退出码 0 正常结束，
      等成员齐了下次自然会生成。）
    """
    failed = []
    for t in CROSS:
        bp = os.path.join(HERE, 'build', f'{t}.py')
        if not os.path.exists(bp):
            continue
        try:
            sh([sys.executable, bp])
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

    # 横截面页失败必须计入 fails。它们没有自己的披露节奏（roster 给 lag=None，
    # 首页永远不给它们判红点），末行总状态是这两页唯一的故障信号 ——
    # 在这里吞掉，两页会无声停在旧月份，而调度器读到的仍是 PUBLISHED。
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
    print('已推送：https://hzhan7.github.io/monthly-op-dashboards/')
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
