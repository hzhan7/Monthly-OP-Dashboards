# -*- coding: utf-8 -*-
"""世芯-KY（Alchip，3661.TW）月度营收看板 —— **指向共用底座的薄壳**。

    图列 / 图注 / 口径规矩 / 版式判据 → build/mrbase.py（底座，不认得任何一家）
    窗口左端与排版的裁决             → build/mrwin.py（可单测：python3 build/mrwin.py）
    世芯自己的数据源、单位、功能货币、
    折算腿、汇率腿、断点             → build/mrspecs/alchip.py

━━ 这个壳是「图列归属」的落地，不是一层转发 ━━━━━━━━━━━━━━━━━━━━━━━━
`monthly_run.py:389` 的 `builder(t)` 按**文件在不在**解析生成器：先找 `build/<t>.py`，
再找下划线版，最后才退到 `build/single.py` + `build/specs/<t>.py`。
本文件一落地，`data/alchip.js` 就归本底座（十张图列），每月 cron 也走这条路
—— 底座的 `owned_elsewhere()` 认得这个壳里的 `mrbase` 字样，因此不再拦写 `data/`。

⚠️ `build/specs/alchip.py` 仍在仓库里，但**已经不再被调用**（本壳的优先级高于它）。
   留着它是为了保留旧图列的口径记录，不是为了继续生成页面；要清理请单独一轮做，
   顺带把旧图列里本页没有的两张图（新台币折算值的水平线、月度分组对账）
   与新图列逐张比过再删。

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
