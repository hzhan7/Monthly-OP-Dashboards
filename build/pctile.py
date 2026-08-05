# -*- coding: utf-8 -*-
"""汇总表 3Y %ile 的**唯一**实现。14 个生成器一律调这里，不要各写各的。

## 为什么收敛成一份

分位这一列的判据前后改过三版，而每一版都是在各自的生成器里各写各的，结果是：
同一条序列（LPL total client assets）在 /lpla/ 被判成噪音留空、在 /wealth/ 却印成
绿色 100，两页互相矛盾；schw 的 margin balances、ibkr 的客户现金、hood 的 margin book、
tsm 的三月均线全都漏网。判据本身是**口径**，口径只能有一处定义。

## 判据：看「这一列在过去两年里有没有区分度」，而不是看序列形状

旧判据是「过去 36 个月里 ≥90% 的月环比不降 → 留空」，它假设「只增不减 ⇔ 分位没信息」。
这个代理不成立：一条上下波动但整体上行的序列（客户现金、margin book）环比降的月份
不少，过得了 90% 那关，可它的分位照样常年钉在 100 —— 因为分位比的是**水平值**，
不是变化。

所以直接测真正关心的东西：**把这一列在过去 24 个月里逐月回放一遍，看它取过几个不同的值。**
若 ≥70% 的月份都钉在同一个极值（100 或 0），这一列对这一行就是死的，留空。

阈值 0.70 的依据（实测各页现状）：
  死列样本   schw margin 24/24 钉 100 · ibkr 客户现金 21/24 · hood margin book 18/24
             tsm 三月均线 17/24 · lpla 现金占比 24 个月里 16 个月 ≤3
  活列样本   cme ADV 分位在 17–88 之间移动，最多 4/24 钉极值
最紧的死列 17/24 = 0.708，最松的活列 4/24 = 0.167，中间是空的 —— 0.70 落在空档里，
不是拍脑袋，也不是为了凑某一页的结果。
"""

WINDOW = 36        # 分位取近 36 个月（= 3Y）
REPLAY = 24        # 回放近 24 个月判断这一列有没有区分度
DEAD_FRAC = 0.70   # 回放里钉在极值的比例超过它 → 该行留空


def _rank(hist, cur):
    """cur 在 hist 里的百分位（0-100）。hist 不含 cur，且至少 2 个点。"""
    below = sum(1 for v in hist if v < cur)
    return below / (len(hist) - 1) * 100.0


def pctile(series, i, window=WINDOW):
    """series[i] 在它之前 window 个月里的百分位；样本不足返回 None。

    series 是一个按月升序的 float 列表（允许 None，会被跳过）。
    """
    lo = max(0, i - window)
    hist = [v for v in series[lo:i + 1] if v is not None]
    if len(hist) < 8:                      # 样本太少，分位没有意义
        return None
    cur = series[i]
    return None if cur is None else _rank(hist, cur)


def is_dead(series, window=WINDOW, replay=REPLAY, dead_frac=DEAD_FRAC):
    """这一行的分位列在近 `replay` 个月里是不是死列（钉在 100 或 0）。

    判据见模块 docstring。样本不足以回放时返回 False —— 宁可显示一个短样本的分位，
    也不要因为「历史太短」就把整列抹掉；短样本本身由 pctile() 的 len<8 挡。
    """
    n = len(series)
    start = max(0, n - replay)
    vals = [pctile(series, i, window) for i in range(start, n)]
    vals = [v for v in vals if v is not None]
    if len(vals) < 6:
        return False
    pinned = sum(1 for v in vals if v >= 99.5 or v <= 0.5)
    return pinned / len(vals) >= dead_frac


def cell(series, i=-1, inverse=False, window=WINDOW):
    """算好一行的分位单元格，返回 (显示字符串, 颜色类)。死列返回 ('', '')。

    inverse=True 用于「越低越好」的指标（逾期率、坏账率）：
    数值分位照算不变，**只有颜色反过来** —— 高分位对反向指标是坏消息。
    """
    if i < 0:
        i += len(series)
    if is_dead(series, window):
        return '', ''
    p = pctile(series, i, window)
    if p is None:
        return '', ''
    good = (100 - p) if inverse else p
    cls = 'hi' if good >= 66 else ('lo' if good <= 33 else '')
    return f'{p:.0f}', cls


def why_blank(series, window=WINDOW):
    """给表注用：这一行为什么留空。没留空返回 None。"""
    if is_dead(series, window):
        return '该行分位在近两年里几乎恒定在区间端点，对这一行没有区分度'
    lo = max(0, len(series) - window)
    if len([v for v in series[lo:] if v is not None]) < 8:
        return '样本不足 8 个月'
    return None
