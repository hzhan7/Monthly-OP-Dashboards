# -*- coding: utf-8 -*-
"""世芯-KY（Alchip，3661.TW）月度营收看板 —— **指向共用底座的薄壳**。

    图列 / 图注 / 口径规矩 / 版式判据 → build/mrbase.py（底座，不认得任何一家）
    窗口左端与排版的裁决             → build/mrwin.py（可单测：python3 build/mrwin.py）
    世芯自己的数据源、单位、功能货币、
    折算腿、汇率腿、断点             → build/mrspecs/alchip.py

━━ 这个壳是「图列归属」的落地，不是一层转发 ━━━━━━━━━━━━━━━━━━━━━━━━
`monthly_run.py` 的 `builder(t)`（按函数名 grep，不写行号：行号一改动就漂成假话）按**文件在不在**解析生成器：先找 `build/<t>.py`，
再找下划线版，最后才退到 `build/single.py` + `build/specs/<t>.py`。
本文件一落地，`data/alchip.js` 就归本底座（十张图列），每月 cron 也走这条路
—— 底座的 `owned_elsewhere()` 认得这个壳里的 `mrbase` 字样，因此不再拦写 `data/`。

⚠️ `build/specs/alchip.py` **已经不在仓库里**：它在 4b0f201（新增本壳的同一个提交）
   里连同另外五家一起被删除。本壳落地后 `data/alchip.js` 只有一个生成路径。
   要看旧图列的口径记录只能回那个提交之前的历史
   （`git log --diff-filter=D -- build/specs/alchip.py` 一查便知），
   别再照这段去 `build/specs/` 里找文件。
   顺带一条机制更正：`owned_elsewhere()` 之所以不拦本页的写入，**首要原因是
   `build/specs/alchip.py` 已经不存在**（它先看这个文件在不在），壳里的 `mrbase` 字样
   只是两份文件并存时才用得上的第二道判据。
   旧图列里本页没有的两张图（新台币折算值的水平线、月度分组对账）已在迁移时
   逐张比过；要复核请从被删提交的父提交里取回那份文件。

━━ 与旧图列（build/single.py）相比，这一页换来什么、丢了什么 ━━━━━━━━━━━━
换来：Ex1 汇总表、季度桥、m/m、**NT$ vs US$ 单月同比（两条线都是官方申报值）**、
      汇率贡献、逐年×逐月同比矩阵、近 13 个月核对表，以及页尾整套口径说明。
丢掉：旧页那条「新台币折算值」的水平序列线（新台币仍在核对表里逐月可读，
      且它的同比就是 Ex5 的 NAVY 线）与 seasonality 图。
      「MOPS 当月换算汇率」那张图没丢，它就是本页的 Exhibit 8。
"""
import sys

import mrbase


def main():
    return mrbase.build_one('alchip')


if __name__ == '__main__':
    sys.exit(main())
