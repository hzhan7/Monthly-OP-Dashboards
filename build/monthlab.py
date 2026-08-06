# -*- coding: utf-8 -*-
"""x 轴月份标签 `Jul-26` 的**唯一**实现。12 个生成器一律调这里。

## 收敛前的状况

同一个 `Jul-26` 被写成三套机械变体，散在 12 个文件里（349 个调用点）：

    p.strftime('%b-%y')                            schw lpla hood hkex axp wealth cboe tsm
    f'{MONTHS[p.month-1]}-{p.year%100:02d}'        cme exchanges
    y, m = s.split('-'); f'{MON[int(m)-1]}-{y[2:]}'    msci spgi

三套的输出在本机完全一样，所以它不是「口径不同」，纯粹是同一件事被抄了三遍 ——
每份 docstring 都写着「与 gsx.mlab 一致」，也就是说三处都在追同一个基准，
而基准自己没有一个可 import 的落点。

## 顺带修掉的一个隐患：strftime('%b-%y') 是跟着 locale 变的

`%b` 取当前 `LC_TIME` 的月份缩写。这套页面的 x 轴标签、热力矩阵列头、核对表首列
全都是英文版式（照 GS GIR exhibit），一旦哪天在非英文 locale 的机器或容器里跑
月度管道，那 8 家的标签会跟着变成本地语言，另外 4 家（用显式月份表的）不变 ——
同一个站里一半页面换语言，而没有任何东西会报错。

所以这里统一用**显式月份表**，不用 strftime：口径不该跟着环境变量走。
本机（LC_TIME 为英文）两种写法逐字节相同，verify_build.py 15/15 一致可证。

## 为什么各页的 MONTHS / MON 常量没有一起收进来

它们是 payload 内容（`year_lines` 的 xlabels、`heat_matrix` 的 cols），不只是格式，
而且**这个名字在本仓是重载的**：`spgi.MONTHS` 根本不是月份名表，是该页的数据月份
列表（`'2026-07'` 那种）。把 12 条 `['Jan', …]` 收进公共模块，就得让 spgi 同时面对
两个叫 MONTHS 的东西 —— 省 20 行字面量，换一个真会咬人的同名陷阱，不值得。
"""

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def mlab(m):
    """月份 → `Jul-26`。接受 pandas Period 或 `'YYYY-MM'` 字符串。

    两种入参都得收：单票页大多把月份当 PeriodIndex 拿在手里（有 .year / .month），
    而 msci / spgi 两页全程用 `'YYYY-MM'` 字符串当键。硬要统一成一种，
    就得在 349 个调用点上做转换 —— 那是为了让这个函数好看而把成本推给调用方。
    """
    if hasattr(m, 'month'):                  # pandas Period / Timestamp / datetime.date
        y, mo = m.year, m.month
    else:                                    # 'YYYY-MM'（多余的日部分一律忽略）
        s = str(m)
        y, mo = int(s[:4]), int(s[5:7])
    return f'{MONTHS[mo - 1]}-{y % 100:02d}'
