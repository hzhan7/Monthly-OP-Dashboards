# -*- coding: utf-8 -*-
"""南亚科技（Nanya Technology，2408.TW）月度营收看板 —— **指向共用底座的薄壳**。

    图列 / 图注 / 口径规矩 / 版式判据 → build/mrbase.py（底座，不认得任何一家）
    窗口左端与排版的裁决             → build/mrwin.py（可单测：python3 build/mrwin.py）
    南亚科自己的数据源、单位、可加总凭据、
    2014-01 断点、为什么没有汇率腿 /
    热力矩阵 / 截轴                   → build/mrspecs/nanya.py

━━ 这个壳是「图列归属」的落地，不是一层转发 ━━━━━━━━━━━━━━━━━━━━━━━━
`monthly_run.py:389` 的 `builder(t)` 按**文件在不在**解析生成器：先找 `build/<t>.py`，
再找下划线版，最后才退到 `build/single.py` + `build/specs/<t>.py`。
本文件一落地，`data/nanya.js` 就归本底座，每月 cron 也走这条路 —— 底座的
`owned_elsewhere()` 认得本壳里的 `mrbase` 字样，因此不再拦写 `data/`。

⚠️ `build/specs/nanya.py` 仍在仓库里，但**已经不再被调用**（本壳优先级高于它）。
   与 mtk / ase / alchip 三家本轮的落法一致：留着它是为了保留旧图列的口径记录，
   不是为了继续生成页面；要清理请单独一轮做（`build/make_shells12.py` 会扫
   `build/specs/` 枚举单公司页，删文件是另一件事的连锁，不该顺手做）。
   两份文件对同一页并存期间，**改口径请改 `build/mrspecs/nanya.py`**。

⚠️ 那份旧配置里有两条本轮已被证伪、别再从它那里抄的说法：
   ① 「断点在 2013-09，比较基期被重述、水平值没有」—— 位置与性质都不对。
      水平值确实没被改写，但那正是问题：2013 整年的水平值留在一个公司自己已作废的
      口径上。回 MOPS 核过：FY2014 报表里的 2013 比较数是 45,224,061（FY2013 自报
      46,975,291，−3.73%），13 个年度里只有这一处「上年比较数 ≠ 上一年自报数」；
      而 2014Q1 合并损益表 11,691,512 = 本序列 2014 年 1-3 月加总（逐位相等），
      同一份报表的 2013Q1 比较数 8,878,000 vs 本序列 2013 年 1-3 月加总 9,245,771
      （+4.14%）。⇒ 断点在 **2014-01**。2013-09 只是公司**月度公告**换基期的那个月
      （晚了八个月），是症状不是断点。
   ② 「2025-08 MemoLead 新设并表」被登记成断点 —— `break_at` 的语义是「从这一期起
      与左侧不可比」，而本页 2025 年 12 个月加总与 FY2025 审计营业收入 diff 恰为 0，
      营收侧没有可辨识台阶。新配置把它降级成页尾说明、不画线。

━━ 与旧图列（build/single.py + build/specs/nanya.py）相比，换来什么、丢了什么 ━━
换来：Ex1 汇总表（月营收 / 3MMA / QTD / YTD / 占 TTM 比重 + 3Y 分位列）、
      月营收柱 + 12 个月滚动合计同比、月→季桥（未满季浅色 + y/y 置 null）、
      环比、163 个月全历史、近 13 个月核对表（改成 3 位小数，与申报的 NT$ 千元
      逐位对得上），以及页尾整套现算的口径说明。
      顺带消掉旧页 visual_qa 的 4 条 🟡（断点整句当竖排标签横穿数值标签）。
丢掉：旧页的 3 年分位带与 seasonality 两张（本底座不产出）；
      热力矩阵本页**主动不出**（理由见 spec 的 `skip_note`，构建期现算）。
      分位没有全丢 —— 汇总表逐行仍有「3Y %ile」列。

⚠️ 接管的一处外溢：`data/roster.js` 里这一行的 headline 由本页 payload 的 hub_line
   生成，文案会从「月合并营收 43,868 NT$mn（+719.6% y/y）」变成
   「Jul-26 营收 NT$44bn，+720% y/y；YTD +661% y/y」。roster 由主线程统一重建，本轮没碰。

落地后校验：
    python3 build/nanya.py && python3 build/verify_pages.py \
        && python3 tools/check_yoy_caliber.py && python3 build/check_specs.py \
        && python3 tools/visual_qa.py --page nanya
"""
import sys

import mrbase


def main():
    return mrbase.build_one('nanya')


if __name__ == '__main__':
    sys.exit(main())
