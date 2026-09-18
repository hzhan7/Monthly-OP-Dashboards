# -*- coding: utf-8 -*-
"""一条命令跑完全部闸门，约 30 秒。改完生成器 / 引擎 / 数据之后跑它就够了。

    python3 tools/gate.py            # 全部
    python3 tools/gate.py --fast     # 跳过整站截图（visual_qa），约 10 秒

每道闸门一行，最后一行是总状态：
    GATE OK 7/7（28s）
    GATE FAILED 1/7：test_guards（…末行…）

判据就是各脚本自己的退出码 —— 本文件不重新定义「什么算过」：
    check_specs        spec 契约（build/specs/*.py 与 mrspecs）
    test_guards        生成器护栏的单测
    verify_pages       payload 契约 + 页面引用（0 ERROR 才算过；WARN 不拦）
    check_yoy_caliber  同比口径（CONTRACT §6）
    test_slow_legs     monthly_run 慢腿登记表不变式
    check_doc_gates    CRON_WIRING §2 闸门表 vs 代码常量
    visual_qa          整站截图 + 机器判据（只有 🔴 算失败；🟡 是提示）

visual_qa 的输出目录按进程隔离（/tmp/visual_qa_gate_<pid>）：默认目录 /tmp/visual_qa
是全机共用的，两个会话同时跑会互相覆盖报告，拿到别人的结论当自己的闸门结果。
"""
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def gates(fast):
    g = [
        ('check_specs', [PY, 'build/check_specs.py']),
        ('test_guards', [PY, 'build/test_guards.py']),
        ('verify_pages', [PY, 'build/verify_pages.py']),
        ('check_yoy_caliber', [PY, 'tools/check_yoy_caliber.py']),
        ('test_slow_legs', [PY, 'test_slow_legs.py']),
        ('check_doc_gates', [PY, 'tools/check_doc_gates.py']),
    ]
    if not fast:
        out = f'/tmp/visual_qa_gate_{os.getpid()}'
        g.append(('visual_qa', [PY, 'tools/visual_qa.py', '--all', '--no-shots', '--out', out]))
    return g


def run(name, cmd):
    t0 = time.time()
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    lines = [ln for ln in (r.stdout + '\n' + r.stderr).strip().splitlines() if ln.strip()]
    return name, r.returncode, time.time() - t0, (lines[-1] if lines else '')[:160]


def main(argv):
    fast = '--fast' in argv
    t0 = time.time()
    todo = gates(fast)
    with ThreadPoolExecutor(max_workers=len(todo)) as pool:
        res = list(pool.map(lambda x: run(*x), todo))
    bad = []
    for name, rc, dt, last in res:
        ok = rc == 0
        print(f'  {"✓" if ok else "✗"} {name:<18}{dt:5.1f}s  {"" if ok else last}')
        if not ok:
            bad.append((name, last))
    total = time.time() - t0
    if bad:
        print(f'GATE FAILED {len(bad)}/{len(res)}：' +
              '；'.join(f'{n}（{l}）' for n, l in bad))
        return 1
    print(f'GATE OK {len(res)}/{len(res)}（{total:.0f}s）')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
