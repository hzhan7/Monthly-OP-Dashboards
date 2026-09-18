# -*- coding: utf-8 -*-
"""一条命令离线重建全站 data/*.js。**合并分支之后必跑**；不下载、不提交、不推送。

    python3 tools/rebuild.py              # 34 页 + roster
    python3 tools/rebuild.py schw ibkr    # 只重建指定页（仍会重建 roster）

最后一行是总状态，与 monthly_run 一样只读这一行就够：
    REBUILD OK 35 个生成物；有变化 2 个：data/schw.js data/ibkr.js
    REBUILD FAILED 1 个：ibkr（…stderr 末行…）

## 为什么合并之后必须重建，而不是解冲突

`data/*.js` 是生成物，正文只有一行 JSON（schw 约 100KB）。两条分支只要都重建过
同一页，这一行必然整行冲突，而手工挑「保留哪边」两边都是错的：两边各缺对方的改动。
正确答案只有一个：合并完源码（build/、series/）之后按新源码重新生成。
`.gitattributes` 把 `data/*.js` 设成内建的 `merge=binary`：冲突时不往文件里插
冲突标记、工作区保留本分支那份，但路径仍是 unmerged —— 于是你**提交不了**，
逼你跑本脚本、再 `git add data/`。（不用 `merge=ours`：那会一声不响地留下一侧的
旧产物，忘了重建就把旧数据推上线，而且不留任何痕迹。）

## 不另立名单

页面清单与「哪个页由哪个生成器生成」全部复用 monthly_run 的 TICKERS / CROSS /
builder()，本文件不认识任何一家的名字 —— 删掉一家时不会多出第二处要同步的名单。
横截面页（CROSS）读成员页的 series，所以在成员之后生成；roster 最后生成。

## worktree 里的 cache/

cache/ 不入库，新 worktree 里没有。目前只有 build/ibkr.py 读它（cache/ibkr/），
缺了会失败并在总状态里点名。补法：从主 checkout 克隆一份（APFS 上不占空间）：
    cp -cR ~/Projects/monthly-op-dashboards/cache/ibkr cache/
"""
import hashlib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import monthly_run as mr                                    # noqa: E402
sys.path.append(os.path.join(HERE, 'build'))
import exhibits                                             # noqa: E402

ROSTER = [sys.executable, os.path.join(HERE, 'build', 'roster.py')]


def _digest(path):
    try:
        with open(path, 'rb') as f:
            return hashlib.sha1(f.read()).hexdigest()
    except FileNotFoundError:
        return None


def _run(name, cmd):
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    if r.returncode == 0:
        return name, None
    tail = (r.stderr or r.stdout or '').strip().splitlines()
    return name, (tail[-1] if tail else f'退出码 {r.returncode}，无输出')[:200]


def main(argv):
    only = [a for a in argv if not a.startswith('-')]
    unknown = [t for t in only if t not in mr.TICKERS + mr.CROSS]
    if unknown:
        print(f'REBUILD FAILED 不认识的页：{" ".join(unknown)}（页名见 monthly_run.TICKERS / CROSS）')
        return 1
    members = [t for t in mr.TICKERS if not only or t in only]
    cross = [t for t in mr.CROSS if not only or t in only]

    data = os.path.join(HERE, 'data')
    before = {f: _digest(os.path.join(data, f)) for f in os.listdir(data) if f.endswith('.js')}

    fails = []
    missing = [t for t in members + cross if mr.builder(t) is None]
    fails += [(t, '找不到生成器（build/<t>.py、build/<t 下划线>.py、build/specs/<t>.py 都没有）')
              for t in missing]
    # 成员页互不依赖，可以并行；横截面页读成员的 series，按 CROSS 顺序串行在后。
    with ThreadPoolExecutor(max_workers=8) as pool:
        for name, err in pool.map(lambda t: _run(t, mr.builder(t)),
                                  [t for t in members if t not in missing]):
            if err:
                fails.append((name, err))
    for t in cross:
        if t in missing:
            continue
        name, err = _run(t, mr.builder(t))
        if err:
            fails.append((name, err))
    # 第二轮：跨页图号（build/exhibits.py 的 ⟨ex:页/id⟩）。成员页先于横截面页生成，
    # 指向横截面页的引用兑的是那一页**上一轮**的号；被指向的页这一轮改了号（重排了图），
    # 就把指过去的页再建一遍 —— 哪怕它不在本次点名的页里，否则它的正文就指错了图。
    # 判据是各页 payload 里的 xref 记录，不是名单；两轮之内必收敛（重建只改指出去的号）。
    for _ in range(2):
        stale = sorted({pg for pg, *_ in exhibits.stale_xrefs(data)} - {n for n, _ in fails})
        if not stale:
            break
        print(f'  跨页图号过期，补建：{" ".join(stale)}')
        for t in stale:
            name, err = _run(t, mr.builder(t))
            if err:
                fails.append((name, err))
    name, err = _run('roster', ROSTER)
    if err:
        fails.append((name, err))

    after = {f: _digest(os.path.join(data, f)) for f in os.listdir(data) if f.endswith('.js')}
    changed = sorted(f'data/{f}' for f in after if after[f] != before.get(f))
    for name, err in fails:
        print(f'  FAIL {name}: {err}')
    total = len(members) + len(cross) + 1
    if fails:
        print(f'REBUILD FAILED {len(fails)} 个：{" ".join(n for n, _ in fails)}'
              f'（其余 {total - len(fails)} 个已重建；有变化 {len(changed)} 个）')
        return 1
    print(f'REBUILD OK {total} 个生成物；有变化 {len(changed)} 个' +
          (f'：{" ".join(changed)}' if changed else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
