# -*- coding: utf-8 -*-
"""回归护栏：重生成全部 data/*.js，与 HEAD **逐字节**比对。

    python3 scripts/verify_build.py              # 全量，比对 HEAD
    python3 scripts/verify_build.py --only cme,cboe
    python3 scripts/verify_build.py --against worktree   # 比对当前工作树的 data/
    python3 scripts/verify_build.py -v           # 打印每家生成器的 stdout

退出码 0 = 全部逐字节一致；非 0 = 有差异或有生成器没跑成（差异明细打在 stdout）。

## 为什么需要它

这个仓 3 万行 Python、0 个测试。build 层的性质本来极适合做回归：**纯函数**
（`series/*.csv` → `data/<t>.js`，不联网、不看时钟、不用随机数，窗口一律从数据最新月
倒推），所以「同一份 CSV 重复跑，输出逐字节相同」是可断言的。以前每次改生成器只能靠
肉眼看 diff，而 payload 是一行压缩 JSON —— 「看起来一样」根本不是验证。

判据照 README 的搬迁验收标准：**逐字节**，唯一允许的差异是首行那句构建日期注释
（`// 由 build/<t>.py 生成于 YYYY-MM-DD`，它不是数据，见 CONTRACT.md 的写法一节）。

## 为什么在沙箱里跑，而不是就地重生成

就地跑会把工作树的 `data/*.js` 全部改写。那不至于触发 `monthly_run.guard_dirty_tree`
（`data/` 在 PUBLISH 白名单里），但它会让「我现在手上改了什么」这件事变得看不清 ——
而这个仓是手写手改的，人随时在看 `git diff`。所以这里造一个临时仓：
`build/` 与 `source_dates.py` 拷进去（要验的正是它们，必须是当前版本），
`series/` 与 `cache/` **只读软链**（是入库真值与过程物，一个字节都不该被本脚本碰）。
生成器用 `os.path.dirname(os.path.abspath(__file__))` 定位仓库根，`abspath` 不解析
软链，所以它们会老老实实把 `data/` 写进沙箱。

## cache/ 缺失不静默跳过

`build/ibkr.py` 是 14 家里唯一要读 `cache/`（`cache/ibkr/hist_latest.pdf` 的 Notes 段
文字）的生成器。cache 是 gitignore 的，克隆一份新仓就没有它。这时本脚本**报失败**，
不是打一句「跳过」就给绿灯 —— 「14 家里悄悄少验了一家」和「14 家全过」长得一样，
而前者正是回归护栏最该防的东西。

在没有 cache 的机器上（新克隆、CI）确实需要一个出口，那就显式写出来：
`--allow-missing-cache` 以 0 退出，但把跳过的家逐个列出来、并在末行写明「本次只验了
n/14 家」。**默认必须是严格的** —— 宽松模式得有人主动打字才生效。
"""
import argparse
import concurrent.futures
import difflib
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 顺序照 monthly_run.TICKERS + CROSS（无依赖，纯为日志好读）。roster 必须排在最后：
# 它是从已生成的 data/<t>.js 里读回月份与数据条的，前面各家没写完它就无从算起。
TICKERS = ['cost', 'ibkr', 'schw', 'lpla', 'hood', 'cme', 'cboe', 'hkex',
           'msci', 'spgi', 'axp', 'tsm']
CROSS = ['exchanges', 'wealth']
ROSTER = 'roster'

# 拷进沙箱的（要验的就是它们，必须取当前版本）/ 只读软链进去的（真值与过程物，不许碰）
# fetch/ 也要拷：build/ibkr.py 把 fetch/ibkr_source.py 当解析管道按路径加载
# （唯一一个 build 反过来依赖 fetch 的地方），少了它 ibkr 会以「找不到解析管道」跑挂，
# 而 roster 读不到 data/ibkr.js 就会跟着不一致 —— 一个缺件报成两处失败。
COPY = ['build', 'fetch', 'source_dates.py']
LINK = ['series', 'cache']


def body(text):
    """去掉首行构建日期注释，只留数据正文。口径与 monthly_run._body 一致。"""
    return text.split('\n', 1)[1] if '\n' in text else ''


def sandbox(tmp):
    """造一个临时仓：build/ 与 source_dates.py 是拷贝，series/ 与 cache/ 是只读软链。"""
    for name in COPY:
        src = os.path.join(ROOT, name)
        dst = os.path.join(tmp, name)
        if os.path.isdir(src):
            # __pycache__ 不拷：里面是上一次跑留下的 .pyc，拷过去只是噪音
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        else:
            shutil.copy2(src, dst)
    for name in LINK:
        src = os.path.join(ROOT, name)
        if os.path.exists(src):
            os.symlink(src, os.path.join(tmp, name))
    os.makedirs(os.path.join(tmp, 'data'), exist_ok=True)


def run_one(tmp, t, verbose):
    """跑一家生成器。返回 (ticker, ok, 输出)。"""
    r = subprocess.run([sys.executable, os.path.join(tmp, 'build', f'{t}.py')],
                       cwd=tmp, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    if verbose and out:
        print(f'  [{t}] ' + out.replace('\n', f'\n  [{t}] '))
    return t, r.returncode == 0, out


def expected(against, rel):
    """基线正文：HEAD 里的那一版，或当前工作树里的那一版。"""
    if against == 'head':
        r = subprocess.run(['git', '-C', ROOT, 'show', f'HEAD:{rel}'],
                           capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None
    p = os.path.join(ROOT, rel)
    return open(p, encoding='utf-8').read() if os.path.exists(p) else None


def show_diff(rel, want, got):
    """payload 是一行压缩 JSON，整行 diff 打出来没法读 —— 所以先定位到第几行、
    第几个字符起不一样，再把那一段前后的上下文截出来。

    比的是 **body()**（已去掉首行构建日期），不是原文：拿原文比的话，只要不是同一天
    重跑，第一处差异永远是那句日期注释 —— 而它恰恰是判据明确允许不同的那一行，
    于是真正的差异被它挡在后面，报告指向一个假原因。
    """
    wl, gl = body(want).splitlines(), body(got).splitlines()
    print(f'    {rel}:')
    for ln, (a, b) in enumerate(zip(wl, gl), 1):
        if a == b:
            continue
        col = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        lo, hi = max(0, col - 90), col + 90
        print(f'      第 {ln} 行第 {col} 字符起不同：')
        print(f'        HEAD  …{a[lo:hi]}…')
        print(f'        本次  …{b[lo:hi]}…')
        break
    else:
        if len(wl) != len(gl):
            print(f'      行数不同：HEAD {len(wl)} 行，本次 {len(gl)} 行')
            for line in list(difflib.unified_diff(wl, gl, 'HEAD', '本次', n=0, lineterm=''))[2:8]:
                print(f'      {line[:200]}')


def main():
    ap = argparse.ArgumentParser(description='重生成 data/*.js 并与基线逐字节比对')
    ap.add_argument('--only', default='', help='只验这几家，逗号分隔')
    ap.add_argument('--against', choices=['head', 'worktree'], default='head',
                    help='基线取 HEAD（默认）还是当前工作树的 data/')
    ap.add_argument('--allow-missing-cache', action='store_true',
                    help='缺 cache/ 跑不了的家只列出、不判失败（新克隆 / CI 用）')
    ap.add_argument('-j', '--jobs', type=int, default=os.cpu_count() or 4)
    ap.add_argument('-v', '--verbose', action='store_true', help='打印各生成器的 stdout')
    a = ap.parse_args()

    todo = [t for t in a.only.split(',') if t] or (TICKERS + CROSS)
    unknown = [t for t in todo if t not in TICKERS + CROSS]
    if unknown:
        print(f'未知 ticker: {unknown}')
        return 2
    # roster 读的是各家已生成的 data/<t>.js，只有全量跑时它的输入才是完整的
    full = set(todo) == set(TICKERS + CROSS)

    tmp = tempfile.mkdtemp(prefix='verify-build-')
    try:
        sandbox(tmp)
        print(f'沙箱 {tmp}（series/ 与 cache/ 是只读软链）')

        # 12 家单票页彼此无依赖，并行跑；横截面页读的是 series/ 而不是别家的产物，
        # 其实也能并行，但它们本来就只有两个、且原管道是排在 12 家之后的，保持同序。
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
            for t, ok, out in pool.map(lambda t: run_one(tmp, t, a.verbose), todo):
                results[t] = (ok, out)

        if full:
            t, ok, out = run_one(tmp, ROSTER, a.verbose)
            results[ROSTER] = (ok, out)

        # 缺 cache 跑不动的，和真的跑挂了，要分开报：前者是环境不全，后者是代码坏了
        missing_cache = [t for t, (ok, out) in results.items()
                         if not ok and '找不到' in out and 'cache' in out]
        broken = [t for t, (ok, _) in results.items() if not ok and t not in missing_cache]

        same, diff = [], []
        for t in sorted(results):
            if not results[t][0]:
                continue
            rel = f'data/{t}.js'
            got = open(os.path.join(tmp, rel), encoding='utf-8').read()
            want = expected(a.against, rel)
            if want is None:
                diff.append((t, rel, '基线里没有这个文件', None, None))
            elif body(want) == body(got):
                same.append(t)
            else:
                diff.append((t, rel, '正文不一致', want, got))

        base = 'HEAD' if a.against == 'head' else '当前工作树'
        print(f'\n基线 = {base}；判据 = 忽略首行构建日期注释后逐字节相同\n')
        for t in sorted(results):
            if t in [d[0] for d in diff]:
                mark, note = '✗ 不一致', ''
            elif t in missing_cache:
                mark, note = '– 跳过  ', '（缺 cache/，见 --allow-missing-cache）'
            elif t in broken:
                mark, note = '✗ 跑挂  ', f'（{results[t][1].splitlines()[-1][:80] if results[t][1] else ""}）'
            else:
                mark, note = '✓ 一致  ', ''
            print(f'  {mark} data/{t}.js {note}')

        if diff:
            print(f'\n{len(diff)} 处不一致：')
            for t, rel, why, want, got in diff:
                if want is None:
                    print(f'    {rel}: {why}')
                else:
                    show_diff(rel, want, got)

        total = len(todo) + (1 if full else 0)
        print(f'\n{len(same)}/{total} 逐字节一致'
              + (f'；不一致 {len(diff)}' if diff else '')
              + (f'；跑挂 {len(broken)}' if broken else '')
              + (f'；缺 cache 跳过 {len(missing_cache)}' if missing_cache else ''))
        if not full:
            print('注意：本次是 --only 子集，roster 未验（它读全部 data/<t>.js）')

        if diff or broken:
            return 1
        if missing_cache:
            # 「少验了一家」与「全过」必须长得不一样，所以这里一定要把话说满
            print(f'缺 cache 跳过：{",".join(sorted(missing_cache))} —— '
                  f'本次只验了 {len(same)}/{total} 家，补上 cache/ 后重跑才算全绿')
            if not a.allow_missing_cache:
                print('（新克隆 / CI 上属正常，加 --allow-missing-cache 可放行）')
                return 1
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
