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
import importlib.util
import json
import os
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
SERIES = os.path.join(HERE, 'series')
CACHE = os.path.join(HERE, 'cache')

# 顺序 = 首页与导航的展示顺序，也是这里的执行顺序（无依赖，纯为日志好读）
TICKERS = ['cost', 'ibkr', 'schw', 'lpla', 'hood', 'cme', 'cboe', 'hkex',
           'msci', 'spgi', 'axp', 'tsm']
# 横截面页没有自己的数据源，等成员都更新完之后再生成
CROSS = ['exchanges', 'wealth']


def sh(cmd, cwd=HERE, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f'{" ".join(cmd)} 失败: {r.stderr[-400:]}')
    # 只去尾部空白：`git status --porcelain` 的首字符是索引状态位，`.strip()` 会把
    # 第一行的前导空格吃掉，脏树清单打出来对不齐、也看不出 staged/unstaged。
    return r.stdout.rstrip()


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
    所以先用本地已有的 data_through 对照 DUE 表，够新的直接跳过，一个字节都不下。
    --force 会绕过它（改了图表代码后要全量重建）。
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
    # 与首页红点同一套规则（LAG = 该月结束后第几天发布，季末月单独给值）：
    # 从上个日历月往回找第一个「已过发布期 + 宽限」的月，那就是今天本该有的月份。
    today = datetime.date.today()
    for k in range(6):
        n = today.year * 12 + today.month - 1 - k      # 候选月的下个月（k=0 即本月）
        y, m = n // 12, n % 12 + 1
        end = datetime.date(y, m, 1)                   # 候选月月末 + 1 天
        cy, cm = (y, m - 1) if m > 1 else (y - 1, 12)  # 候选月本身
        days = lag[1] if cm % 3 == 0 else lag[0]
        if today >= end + datetime.timedelta(days=days + r.GRACE):
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
