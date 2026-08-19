# -*- coding: utf-8 -*-
"""联华电子（UMC，2303.TW / NYSE: UMC）月度营收看板 —— **指向共用底座的薄壳**。

    图列 / 图注 / 口径规矩 / 版式判据 → build/mrbase.py（底座，不认得任何一家）
    窗口左端与排版的裁决             → build/mrwin.py（可单测：python3 build/mrwin.py）
    联电自己的数据源、单位、可加总凭据、两条断点、
    为什么有汇率线、却没有美元营收腿   → build/mrspecs/umc.py

━━ 这个壳是「图列归属」的落地，不是一层转发 ━━━━━━━━━━━━━━━━━━━━━━━━
`monthly_run.py` 的 `builder(t)`（按函数名 grep，不写行号：行号一改动就漂成假话）按**文件在不在**解析生成器：先找 `build/<t>.py`，
再找下划线版，最后才退到 `build/single.py` + `build/specs/<t>.py`。
本文件一落地，`data/umc.js` 就归本底座，每月 cron 也走这条路 —— 底座的
`owned_elsewhere()` 认得本壳里的 `mrbase` 字样，因此不再拦写 `data/`。

⚠️ `build/specs/umc.py` **已经不在仓库里**：它在 4b0f201（新增本壳的同一个提交）
   里连同另外五家一起被删除。改口径一律改 `build/mrspecs/umc.py`，没有第二份配置。
   要看旧图列的口径记录只能回那个提交之前的历史
   （`git log --diff-filter=D -- build/specs/umc.py` 一查便知），
   别再照这段去 `build/specs/` 里找文件。
   顺带一条机制更正：`owned_elsewhere()` 之所以不拦本页的写入，**首要原因是
   `build/specs/umc.py` 已经不存在**（它先看这个文件在不在），壳里的 `mrbase` 字样
   只是两份文件并存时才用得上的第二道判据。

━━ 与旧图列（build/single.py + build/specs/umc.py）相比，换来什么、丢了什么 ━━
换来：Ex1 汇总表（月营收 / 3MMA / QTD / YTD / 占 TTM 比重 + 3Y 分位列）、
      月营收柱 + 12 个月滚动合计同比、月→季桥（未满季浅色 + y/y 置 null）、
      环比、163 个月全历史、NTD/USD 月均汇率线（**汇率本身**，不是任何营收量）、
      逐年×逐月**单月**同比矩阵、近 13 个月核对表，
      以及页尾整套现算的口径说明（可加总凭据、2012 不入库、两条断点、
      为什么没有美元腿与指引桥、公告确实带 y/y 列但没落库）。
丢掉：旧页的 3 年分位带与 seasonality 两张（本底座不产出）。
      分位没有全丢 —— 汇总表逐行仍有「3Y %ile」列；季节性改由热力矩阵承担。
"""
import sys

import mrbase


def main():
    return mrbase.build_one('umc')


if __name__ == '__main__':
    sys.exit(main())
