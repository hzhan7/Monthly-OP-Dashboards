# -*- coding: utf-8 -*-
"""monthlab.mlab 的等价性测试：`python3 build/test_monthlab.py`（无依赖，不用 pytest）。

这个仓没有 pytest（requirements.txt 里没钉，本机也没装），而且整套东西的立场是
零依赖零构建 —— 所以测试就写成一个能直接跑的脚本，assert 挂了就非 0 退出。

**要证的是什么**：`mlab` 收敛之前，同一个 `Jul-26` 有三套机械变体散在 12 个文件里。
`scripts/verify_build.py` 已经证明「在当前这一份 series 数据上」输出逐字节没变，
但那只覆盖了各页窗口里实际出现的那些月份（最早 2008-01）。这里补的是另一半：
把三套旧写法原样搬过来，在一个**远大于任何页面窗口**的月份区间上逐月比对 ——
证的是函数等价，不是「这批数据上碰巧一样」。
"""
import locale
import sys

import pandas as pd

from monthlab import mlab

# ── 三套旧写法，逐字照搬收敛前的实现 ───────────────────────────────────
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def old_strftime(p):
    """schw / lpla / hood / hkex / axp / wealth / cboe / tsm 的写法。"""
    return p.strftime('%b-%y')


def old_table(p):
    """cme / exchanges 的写法。"""
    return f'{MONTHS[p.month - 1]}-{p.year % 100:02d}'


def old_split(s):
    """msci / spgi 的写法（入参是 'YYYY-MM' 字符串）。"""
    y, m = s.split('-')
    return f'{MONTHS[int(m) - 1]}-{y[2:]}'


def main():
    fails = []

    # 1) 三套旧写法 vs 新实现，2000-01 … 2039-12 逐月（480 个月，远超任何页面窗口）
    months = pd.period_range('2000-01', '2039-12', freq='M')
    for p in months:
        s = str(p)                       # 'YYYY-MM'
        got = mlab(p)
        for name, want in (('strftime', old_strftime(p)),
                           ('table', old_table(p)),
                           ('split', old_split(s))):
            if got != want:
                fails.append(f'{s}: mlab(Period)={got!r} != old_{name}={want!r}')
        if mlab(s) != got:
            fails.append(f'{s}: mlab(str)={mlab(s)!r} != mlab(Period)={got!r}')

    # 2) 几个手写的定点值 —— 世纪边界与个位数年份的 2 位补零最容易写错
    for src, want in [('2026-07', 'Jul-26'), ('2026-01', 'Jan-26'),
                      ('2026-12', 'Dec-26'), ('1999-12', 'Dec-99'),
                      ('2000-01', 'Jan-00'), ('2008-09', 'Sep-08')]:
        for arg in (src, pd.Period(src, freq='M')):
            if mlab(arg) != want:
                fails.append(f'定点值 {src} ({type(arg).__name__}): {mlab(arg)!r} != {want!r}')

    # 3) 收敛顺带修掉的那个隐患：新实现不跟 locale 走，旧的 strftime 写法跟着走。
    #    找一个本机装了的非英文 LC_TIME 试；一个都没有就跳过并说清楚（不假装验过）。
    p = pd.Period('2026-07', freq='M')
    before = mlab(p)
    tried = None
    for loc in ('de_DE.UTF-8', 'fr_FR.UTF-8', 'zh_CN.UTF-8', 'es_ES.UTF-8'):
        try:
            locale.setlocale(locale.LC_TIME, loc)
        except locale.Error:
            continue
        tried = loc
        if mlab(p) != before:
            fails.append(f'{loc} 下 mlab 变了：{mlab(p)!r} != {before!r} —— 不该跟 locale 走')
        locale.setlocale(locale.LC_TIME, 'C')
        break

    if fails:
        print(f'FAIL {len(fails)} 处：')
        for f in fails[:20]:
            print(f'  · {f}')
        return 1
    print(f'OK  {len(months)} 个月 x 3 套旧写法逐月等价；定点值 6 组；'
          + (f'locale 不变性已在 {tried} 下验过' if tried
             else 'locale 不变性未验（本机没装非英文 LC_TIME，跳过）'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
