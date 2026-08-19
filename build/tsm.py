# -*- coding: utf-8 -*-
"""TSMC（2330.TW / NYSE: TSM）月度营收看板 —— **本文件已迁到共用底座，只剩一层薄壳**。

    图列 / 图注 / 口径规矩 / 版式判据 → build/mrbase.py（底座，不认得任何一家）
    窗口左端与排版的裁决       → build/mrwin.py（可单测：python3 build/mrwin.py）
    TSMC 自己的数据源、单位、汇率腿、
    外币计价的官方表述、断点、指引桥 → build/mrspecs/tsm.py

━━ 为什么留这层壳，而不是让调用方改命令 ━━━━━━━━━━━━━━━━━━━━━━━━━━━
`monthly_run.py` 的 `builder(t)`（按函数名 grep，不写行号：行号一改动就漂成假话）按**文件在不在**解析生成器：
先找 `build/<t>.py`，再找下划线版，最后才退到 `build/single.py`。
本轮明令不许碰 `monthly_run.py`，所以让新底座接上 cron 的唯一办法就是
**把这个文件换成壳**——而不是把原来那 1,129 行留在原地。
留着它的后果是每月 cron 用老生成器把 `data/tsm.js` 覆盖回 20 个月的窗口，
「同一套图列立刻分叉成两份实现」这件事就真的发生了。

原来的 1,129 行去哪了：
  · 图注措辞、align_sim、负零处理、cum 行留空判据、「图注声称的必须现读 payload」
    那一整套 —— 搬进底座，逐条对着旧产物验过（见下）；
  · 硬编码 'tsm' 的三十余处（csv 名、列名、NT$/US$、"Roughly 70% of TSMC revenue…"、
    断点声明的前半句、指引表）—— 搬进 spec，底座里一处家名都没有。

迁移前后 `data/tsm.js` 逐 exhibit 比过（scratch 的 exdiff.py，判据是**逐点相等**，
不是首尾对得上）：Ex2-Ex9 的每一个数值数组，老窗口的每一格都原位不动地留在新数组的
尾段；汇总表 8 行、核对表 13 行逐格相同；headline / brief / hub_line 逐字相同。
差异只有三类，全部说得清：
  ① 本轮要的窗口变化（Ex2/3/4/5/6 拉到 2016 起，各图实际首点由自己的 lag 决定）；
  ② CONTRACT §6 要求补进标题的「单月 / single-month」（Ex6、Ex9 原来漏了）；
  ③ Ex3 末季（未满 3 个月）的 y/y 由「payload 给值、引擎渲染时作废」改成
     **payload 里就是 null** —— 画面一模一样，但 payload 里不再躺着一个
     「1 个月比 3 个月」的数等着被谁读走。
"""
import sys

import mrbase


def main():
    return mrbase.build_one('tsm')


if __name__ == '__main__':
    sys.exit(main())
