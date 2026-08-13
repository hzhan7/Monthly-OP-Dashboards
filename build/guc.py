# -*- coding: utf-8 -*-
"""创意电子（GUC，3443.TW）月度营收看板 —— **指向共用底座的薄壳**。

    图列 / 图注 / 口径规矩 / 版式判据 → build/mrbase.py（底座，不认得任何一家）
    窗口左端与排版的裁决             → build/mrwin.py（可单测：python3 build/mrwin.py）
    GUC 自己的数据源、单位与精度、
    分部拆分、可加总凭据、
    为什么没有汇率腿与指引桥         → build/mrspecs/guc.py

━━ 这个壳是「图列归属」的落地，不是一层转发 ━━━━━━━━━━━━━━━━━━━━━━━━
`monthly_run.py:389` 的 `builder(t)` 按**文件在不在**解析生成器：先找 `build/<t>.py`，
再找下划线版，最后才退到 `build/single.py` + `build/specs/<t>.py`。
本文件一落地，`data/guc.js` 就归本底座，每月 cron 也走这条路 —— 底座的
`owned_elsewhere()` 认得本壳里的 `mrbase` 字样，因此不再拦写 `data/`。

⚠️ `build/specs/guc.py` 仍在仓库里，但**已经不再被调用**（本壳优先级高于它）。
   留着它是为了保留旧图列的口径记录（Note 17b 那两个地区占比就转录自它），
   不是为了继续生成页面；要清理请单独一轮做。
   两份文件对同一页并存期间，**改口径请改 `build/mrspecs/guc.py`**。
   （与 tsm / ase / mtk / umc / alchip 五家同一处置。）

━━ 与旧图列（build/single.py + build/specs/guc.py）相比，换来什么、丢了什么 ━━
换来：Ex1 汇总表（月营收 / Turnkey / NRE & Others / 3MMA / QTD / YTD / 占 TTM 比重
      + 3Y 分位列）、月营收柱 + 12 个月滚动合计同比、月→季桥（未满季浅色 +
      y/y 置 null）、环比、115 个月全历史（合并线 + 两条分部线）、逐年×逐月
      **单月**同比矩阵、近 13 个月核对表（官方原始单位、多两列分部），
      以及页尾整套现算的口径说明（七期查核／核阅数对账、逐月分部恒等式、
      2026-01 分部并行不是断点、为什么没有美元腿与指引桥、
      「公司其实是报同比的、只是没落库」这条更正）。
丢掉：旧页的 decomp / ttm_yoy / seasonality 三张（本底座不产出）。
      季节性改由热力矩阵承担；分部构成改由全历史图的两条线 + 汇总表两行承担。
"""
import sys

import mrbase


def main():
    return mrbase.build_one('guc')


if __name__ == '__main__':
    sys.exit(main())
