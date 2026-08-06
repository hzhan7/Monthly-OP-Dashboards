# -*- coding: utf-8 -*-
"""build/ 下各生成器共用的仓库定位 + 发布日台账入口。

## 它解决的是一个纯机械的重复

`build/<t>.py` 是以 `python3 build/<t>.py` 跑的，`sys.path[0]` 只有 `build/`，
所以**裸 `import source_dates` 必挂** —— 台账模块在仓库根，不在 `build/` 下。
于是 12 个生成器各自抄了一份同样六行的 `spec_from_file_location` 样板，
而且抄出了六个名字：`_source_dates()`（cost/schw/hood/cboe/spgi）、
`source_dates()`（hkex）、`load_source_dates()`（exchanges/wealth）、
模块级裸写的 `_sd_spec` / `_spec`（cme/ibkr）、藏在取值函数里的（lpla/tsm）。

`source_dates.py` 里本来就有一个 `load(root)` 想干这件事，但它自己在仓库根 ——
要调它得先把它 import 进来，正是它要解决的问题，所以 12 个调用点一个都没用上它
（零调用者）。放不对位置的公共函数等于没有：这个模块在 `build/` 下，
生成器可以直接 `import repo`。

## 为什么顺带把 series 目录也收进来

台账查询要传 series 目录，而那个目录同一个值被写出了三种形态：`SERIES`、
`SERIES_DIR`、以及调用点上现拼的 `os.path.join(ROOT, 'series')`。
查台账是**一件事**，不该让 12 个调用点各自回答「series 在哪」。
所以对外只暴露 `source_date(ticker, month)` 与 `latest_source_date(...)`，
路径由这里回答；要更底层的东西再拿 `source_dates()` 去调原模块。

各生成器**自己的** `SERIES` / `OUT` 常量保持原样不动 —— 那是它读哪张 CSV、
写哪个文件的声明，属于「这一家的口径」，把它藏进公共模块只会让下次改一家更难找。
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
DATA = os.path.join(ROOT, 'data')

_sd = None


def source_dates():
    """按路径加载仓库根的 source_dates.py（理由见模块 docstring）。

    加载一次就缓存：同一个进程里 12 个调用点各 exec 一遍同一个文件没有意义，
    而且那样每次拿到的是**不同的模块对象**，将来若在台账模块里放进程级状态就会踩坑。
    """
    global _sd
    if _sd is None:
        spec = importlib.util.spec_from_file_location(
            'source_dates', os.path.join(ROOT, 'source_dates.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _sd = mod
    return _sd


def source_date(ticker, month):
    """台账里 (ticker, month) 的官方发布日，'YYYY-MM-DD'；没记录返回 None。

    调用方**必须容忍 None** —— 台账这个月还没记上时，页面按 CONTRACT.md §1
    自动省掉抬头那半句，这比印一个编出来的日期好得多。
    """
    return source_dates().lookup(SERIES, ticker, month)


def latest_source_date(tickers, months):
    """横截面页用：成员里最晚的那个发布日；缺任何一个成员则返回 None。

    口径在 source_dates.latest_of()（缺一个成员就整体省略，理由写在那里），
    这里只负责回答「series 在哪」。
    """
    return source_dates().latest_of(SERIES, tickers, months)
