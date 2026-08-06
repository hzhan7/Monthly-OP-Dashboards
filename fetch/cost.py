# -*- coding: utf-8 -*-
"""Costco (COST) 月度销售抓取 —— GlobeNewswire 新闻稿。

═══ 源 ═══
GlobeNewswire 上的 Costco 月度销售新闻稿。查找与解析在 `fetch/cost_release.py`
（`find_release` / `curl` / `parse_release`），那份代码原本在 skill「COST月度销售」的
`monthly_update.py` 里、由 skill 与本看板共用；skill 删除时**逐字搬进了本仓库**，
所以总仓现在自包含，不再读 `~/.claude` 的 skills 目录下的任何东西。
（当初共用是为了避免分叉 —— 分叉的表现是「skill 的 PDF 和网页看板对同一个月给出不同的
comp」，最难发现的那种错。skill 没了，分叉的对象也没了。）

curl 通道，不需要 Chrome。

═══ 数据落在哪 ═══
真值就是本仓库的 `series/cost.csv`（原先是 skill 的 `cost_monthly.csv`，本模块只镜像；
skill 删除后镜像的上游没了，历史内容原样成为真值，逐字节未改）。本模块只往它追加，
不改结构、不重排、不重新格式化已有行。

历史行是 pandas 写出来的（`5.0` / `698.0`），本模块新追加的行是 csv.writer 写 int（`5`）。
两种写法并存是既有状态，**别为了统一而重写整表** —— 那会把「本月新增 1 行」淹没在
128 行改动里，review 时根本看不出这个月的数据是什么。

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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
CSV_NAME = 'cost.csv'


class CostFetchError(RuntimeError):
    """本模块所有失败路径统一抛它，调度器只需 catch 一种。"""


_MOD = None


def _release():
    """加载 fetch/cost_release.py（新闻稿的查找与解析）。

    不用 `import cost_release`：本模块会被 monthly_run.py 用
    spec_from_file_location 加载，那时 fetch/ 根本不在 sys.path 上，
    裸 import 会 ModuleNotFoundError。与 fetch/fee_rates.py 的 _load 同规则。
    """
    global _MOD
    if _MOD is not None:
        return _MOD
    p = os.path.join(HERE, 'cost_release.py')
    if not os.path.exists(p):
        raise CostFetchError(f'找不到解析管道: {p}')
    spec = importlib.util.spec_from_file_location('cost_release', p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MOD = mod
    return mod


def _csv(series_dir=None):
    return os.path.join(series_dir or SERIES, CSV_NAME)


def _read_csv(series_dir=None):
    path = _csv(series_dir)
    if not os.path.exists(path):
        raise CostFetchError(f'series/cost.csv 不存在: {path}')
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        raise CostFetchError('series/cost.csv 没有数据行')
    return rows[0], rows[1:]


# 报告口径 ⇄ 除油汇口径 的五组配对。两套口径同时出现在同一张 comp 表里，
# 解析器要靠「表 1 = 报告、表 2 = 调整」把它们分开。
_CALIBER_PAIRS = [('us_r', 'us_a'), ('ca_r', 'ca_a'), ('oi_r', 'oi_a'),
                  ('tc_r', 'tc_a'), ('ec_r', 'ec_a')]


def _guard_two_calibers(key, rec, url):
    """两套口径完全相同 → 判定解析走错分支，拒绝入库。

    **现有的缺列护栏挡不住这一类**：2026-07 那期 GlobeNewswire 改了表格 markup
    （每个值列重复一遍，(8,4) 变 (8,6)），于是「表 1/表 2」的月表判据全部落空，
    控制流掉进为 2 月合并稿准备的那个分支，从**同一张表**里取 toks[0] 当报告、
    toks[1] 当调整 —— 而那两个 token 是被复制的同一列。
    结果是 16 列一列不缺、只是「除油汇核心 comp」被写成了报告口径，
    Exhibit 里最关键的那条线整条错，而全程不抛异常、静默入库、直接上公开页。

    判据的依据是实测而不是直觉：series/cost.csv 里 103 个有完整两套口径的月份，
    **五个地区同时相等的一次都没有**（最多 3 个地区相等，仅出现过 1 次）。
    所以「全部相等」是解析走错分支的可靠信号，不会误伤真实数据。
    """
    same, avail = [], []
    for a, b in _CALIBER_PAIRS:
        va, vb = rec.get(a), rec.get(b)
        if va is None or vb is None:
            continue
        avail.append(a)
        if va == vb:
            same.append(f'{a}={va}')
    if len(avail) >= 4 and len(same) == len(avail):
        raise CostFetchError(
            f'{key} 的报告口径与除油汇口径逐个相等（{", ".join(same)}）—— '
            f'几乎可以确定是 comp 表解析走错了分支（历史 103 个月里从未出现过全部相等）。'
            f'拒绝入库。请核对新闻稿的表格结构：{url}')


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
    mu = _release()
    y, m = _next_month(last)
    try:
        url = mu.find_release((y, m))
    except Exception as e:
        raise CostFetchError(f'GlobeNewswire 查询失败: {e}') from e
    return f'{y}-{m:02d}' if url else last


def update(series_dir, cache_dir=None):
    """把官方还没入库的零售月写进 series/cost.csv，返回新增月份列表。

    幂等：已有的月份不重复追加，重复跑第二遍返回 []。
    解析结果缺任何一个已有列 → 抛异常，绝不静默写 NaN。
    """
    path = _csv(series_dir)
    head, rows = _read_csv(series_dir)
    have = {r[0] for r in rows}
    last = rows[-1][0]
    mu = _release()
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
        _guard_two_calibers(key, rec, url)
        # 照抄既有行尾：csv.writer 默认写 \r\n，而 cost.csv 是纯 LF，
        # 用默认值会往全 LF 的文件里插一条孤立的 CRLF 行。
        with open(path, 'rb') as f:
            term = '\r\n' if b'\r\n' in f.read(4096) else '\n'
        with open(path, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f, lineterminator=term).writerow([key] + [rec[c] for c in head[1:]])
        added.append(key)
        have.add(key)
        last = key

    return added


if __name__ == '__main__':
    print('latest:', latest_month())
