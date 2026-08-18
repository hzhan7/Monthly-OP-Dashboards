# -*- coding: utf-8 -*-
"""日月光投控 ASEH（3711.TW / NYSE: ASX）月度营收看板 —— **薄壳，与 build/tsm.py 同形**。

    图列 / 图注 / 口径规矩 / 版式判据 → build/mrbase.py（底座，不认得任何一家）
    窗口左端与排版的裁决           → build/mrwin.py（可单测：python3 build/mrwin.py）
    ASEH 自己的数据源、单位、分部列、
    断点与门槛、为什么没有汇率腿   → build/mrspecs/ase.py
    为什么序列从 2018-05 起、
    为什么**不**把前身（2311）接上来 → build/mrspecs/ase.py 文件头【1】与【12】，
                                     页面上是最后一条页尾说明 `_PRE2018_NOTE`

⚠️ 「起点 2018-05」是**决定**不是缺口。前身的月营收在 SEC EDGAR 上拿得到
   （前身与本主体共用 CIK 0001122411），本仓仍然不接 —— 三条理由与量化代价写在
   【12】。想「顺手补齐历史」的人请先读那一条：接缝是 +30% 的并表台阶，
   而且日月光自己都空着那 12 个月的去年同月列。

━━ 为什么必须留这层壳 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`monthly_run.py` 的 `builder(t)` 按**文件在不在**解析生成器：先找 `build/<t>.py`，
再找下划线版，最后才退到 `build/single.py` + `build/specs/<t>.py`。
本轮明令不许碰 `monthly_run.py`，所以让新底座接上 cron 的唯一办法就是放这个壳 ——
不放，每月 cron 会用 `build/single.py` 把 `data/ase.js` 覆盖回老图列
（decomp / ttm_yoy / seasonality），「同一页两套图列」当月就会发生。

`build/specs/ase.py` **留在原地不动**：`mrbase.owned_elsewhere()` 的判据是
「specs/ 里有没有这个文件」加「壳里有没有 mrbase」，本壳存在即归本底座管；
那份老 spec 里的抓取口径注释与 `fetch/ase.py` 是配套的，删它是另一件事。
"""
import sys

import mrbase


def main():
    return mrbase.build_one('ase')


if __name__ == '__main__':
    sys.exit(main())
