# -*- coding: utf-8 -*-
"""Costco (COST) 月度销售抓取 —— 复用 /COST月度销售 skill 的解析管道。

═══ 源 ═══
GlobeNewswire 上的 Costco 月度销售新闻稿。查找与解析都走 skill 的
`~/.claude/skills/COST月度销售/monthly_update.py`（`find_release` / `curl` / `parse_release`），
**本模块不重写解析逻辑**：那份代码是 skill 与本看板共用的，各写一份迟早会分叉，
而分叉的表现是「skill 的 PDF 和网页看板对同一个月给出不同的 comp」——最难发现的那种错。

curl 通道，不需要 Chrome。

═══ 数据落在哪 ═══
真值仍是 skill 的 `cost_monthly.csv`（/COST月度销售 skill 自己也在读它，
本模块只追加不改结构）。同时镜像一份到 `series/cost.csv`，让总仓自成体系
——十二家里只有它一家的数据在仓库外，排查问题时会格外费劲。
两份内容始终一致，以 skill 那份为准。

═══ 发布节奏 ═══
每零售月结束后首个周三美东盘后（≈SGT 次日凌晨）。

═══ 口径坑 ═══
1. **4-4-5 零售日历**：零售月为 4 周或 5 周（周日截止），净销售额绝对值不可直接环比。
2. **53 周财年**造成个别 1 月周数与上年同月不同（2018-01 / 2019-01 / 2024-01 / 2025-01）。
3. `parse_release` 只在净销售额句与 comp 表**整体**缺失时抛异常；单个地区行或电商行
   匹配不上（Costco 已经把 E-commerce 改名成 Digitally-Enabled 一次了）只会让那两列缺席，
   而按列名对齐写入会让缺的列静默变 NaN，一路写到公开页面上而全程没有任何报错。
   所以本模块在写 CSV **之前**做缺列检查，缺一列就抛异常。
"""
import csv
import importlib.util
import os

SKILL = os.path.expanduser('~/.claude/skills/COST月度销售')
CSV = os.path.join(SKILL, 'cost_monthly.csv')


class CostFetchError(RuntimeError):
    """本模块所有失败路径统一抛它，调度器只需 catch 一种。"""


def _skill():
    p = os.path.join(SKILL, 'monthly_update.py')
    if not os.path.exists(p):
        raise CostFetchError(f'找不到 skill 解析管道: {p}')
    spec = importlib.util.spec_from_file_location('cost_mu', p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read_csv():
    if not os.path.exists(CSV):
        raise CostFetchError(f'skill 的 cost_monthly.csv 不存在: {CSV}')
    with open(CSV, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        raise CostFetchError('cost_monthly.csv 没有数据行')
    return rows[0], rows[1:]


def _next_month(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return (y + 1, 1) if m == 12 else (y, m + 1)


def latest_month(cache_dir=None):
    """官方源当前最新的**已发布**零售月 'YYYY-MM'。

    Costco 不提供「最新月是几月」的接口，只能拿下一个月去 GlobeNewswire 试探：
    查得到新闻稿就说明已发布。查不到不是故障，是还没发。
    """
    _, rows = _read_csv()
    last = rows[-1][0]
    mu = _skill()
    y, m = _next_month(last)
    try:
        url = mu.find_release((y, m))
    except Exception as e:
        raise CostFetchError(f'GlobeNewswire 查询失败: {e}') from e
    return f'{y}-{m:02d}' if url else last


def _mirror(series_dir):
    """把 skill CSV 原样镜像到 series/cost.csv（逐字节复制，不做任何重新格式化）。

    不用 pandas 读写：那会把浮点重新渲染一遍（35879.42523809524 → 35879.425238），
    等于悄悄改了历史数据，而 diff 看上去只是「格式变了」。
    """
    with open(CSV, 'rb') as src, open(os.path.join(series_dir, 'cost.csv'), 'wb') as dst:
        dst.write(src.read())


def update(series_dir, cache_dir=None):
    """把官方还没入库的零售月写进 skill 的 cost_monthly.csv，返回新增月份列表。

    幂等：已有的月份不重复追加，重复跑第二遍返回 []。
    解析结果缺任何一个已有列 → 抛异常，绝不静默写 NaN。
    """
    head, rows = _read_csv()
    have = {r[0] for r in rows}
    last = rows[-1][0]
    mu = _skill()
    added = []

    # 一次最多补 6 个月：正常只差 1 个月，差很多说明前面漏跑了很久，
    # 与其一口气拉一年不如让它跑几次、每次都能看到进度。
    for _ in range(6):
        y, m = _next_month(last)
        key = f'{y}-{m:02d}'
        if key in have:
            last = key
            continue
        try:
            url = mu.find_release((y, m))
        except Exception as e:
            raise CostFetchError(f'GlobeNewswire 查询 {key} 失败: {e}') from e
        if not url:
            break                                  # 还没发，正常结束
        try:
            rec, ym = mu.parse_release(mu.curl(url))
        except Exception as e:
            raise CostFetchError(f'解析 {key} 失败 ({url}): {e}') from e
        got = f'{ym[0]}-{ym[1]:02d}'
        if got != key:
            raise CostFetchError(f'月份不符: 期望 {key} 实得 {got} ({url})')
        missing = [c for c in head[1:] if c not in rec]
        if missing:
            raise CostFetchError(f'{key} 解析缺列 {missing} ({url})')
        # 照抄既有行尾：csv.writer 默认写 \r\n，而 cost_monthly.csv 是纯 LF，
        # 用默认值会往全 LF 的文件里插一条孤立的 CRLF 行，再被 _mirror 逐字节搬进 series/。
        with open(CSV, 'rb') as f:
            term = '\r\n' if b'\r\n' in f.read(4096) else '\n'
        with open(CSV, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f, lineterminator=term).writerow([key] + [rec[c] for c in head[1:]])
        added.append(key)
        have.add(key)
        last = key

    _mirror(series_dir)
    return added


if __name__ == '__main__':
    print('latest:', latest_month())
