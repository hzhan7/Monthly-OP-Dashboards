# -*- coding: utf-8 -*-
"""Interactive Brokers (IBKR) 月度经营指标抓取。

═══ 源 ═══
IBKR 官网 IR：
  · Historical Brokerage Metrics PDF（11 页，逐年逐月，每月更新）—— 全部存量指标
  · 各月 Metrics 新闻稿 PDF —— 佣金与产品明细，历史 PDF 里没有

下载与解析走同目录的 `fetch/ibkr_source.py`（`curl` / `parse_hist_page` /
`parse_pr` / `LABELS`）。那份文件搬自已删除的 `/IBKR月度指标` skill 的
`build_report.py`，逐字复制、注释照留。**本模块不重写解析逻辑**：解析口径只能有
一处定义，各写一份迟早分叉，而分叉的表现是「两处对同一个月给出不同的 DARTs」
——最难发现的那种错。

═══ 数据落在哪 ═══
`cache/ibkr/`（hist_latest.pdf + 各月 pr_YYYYMM.pdf，gitignored）是原始件。本模块另把
历史指标表解析成 `series/ibkr.csv`（与其余十一家同构，tracked），排查时不必开 PDF。

═══ 发布节奏 ═══
每月第一个美股交易日（美东 ~16:00 = SGT 次日凌晨），遇假日顺延。

═══ 口径坑 ═══
1. **单位**：历史指标表首个区块标注 "(in Thousands, except Trading Days)"，故账户数、
   净新增、DARTs、期权/期货合约数、股票成交股数以**千**为单位；客户权益、现金、
   融资余额区块标注 "(in Billions)"。series/ibkr.csv 保持官方原始单位，不做换算。
2. **账户口径调整**：历史指标 PDF 的 Notes 段披露过一次性调整（escheat、introducing
   broker 撤出、Total Accounts 下调）。本模块只负责把披露值原样入库；还原真实增长是
   build/ibkr.py 的事，它每月重抓这段 Notes，**出现未登记的调整会直接让构建失败**。
3. 历史 PDF **不含佣金数据**，佣金图只覆盖本地已缓存的月度新闻稿区间。
"""
import csv
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.join(HERE, 'ibkr_source.py')
# 缓存目录只在 ibkr_source.CACHE 定义一处（build/ibkr.py 也指向它）——
# 这里不再复制一份常量：两处各写各的正是「fetch 下到 A、build 去 B 找」的来源。

_MOD = None


class IbkrFetchError(RuntimeError):
    """本模块所有失败路径统一抛它，调度器只需 catch 一种。"""


def _pipeline():
    """按路径加载 fetch/ibkr_source.py。

    不用裸 `import ibkr_source`：本模块被 monthly_run.py 用 spec_from_file_location
    加载，那时 fetch/ 根本不在 sys.path 上（fetch/fee_rates.py 同一个坑）。
    加载结果缓存住 —— latest_month() 与 update() 会先后各叫一次。
    """
    global _MOD
    if _MOD is not None:
        return _MOD
    if not os.path.exists(PIPELINE):
        raise IbkrFetchError(f'找不到解析管道: {PIPELINE}')
    spec = importlib.util.spec_from_file_location('ibkr_source', PIPELINE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MOD = mod
    return mod


def _hist(br, refresh=True):
    """下载并解析历史指标 PDF，返回 {'YYYY-MM': {列: 值}}。

    每次都重下：这个 PDF 是判断「官方发新数据了没有」的唯一依据，
    吃缓存等于永远看不到新月份。
    """
    os.makedirs(br.CACHE, exist_ok=True)
    path = os.path.join(br.CACHE, 'hist_latest.pdf')
    if refresh:
        try:
            br.curl(br.HIST_URL, path)
        except Exception as e:
            raise IbkrFetchError(f'历史指标 PDF 下载失败: {e}') from e
    if not os.path.exists(path):
        raise IbkrFetchError('历史指标 PDF 不存在且未下载')

    import fitz
    doc = fitz.open(path)
    out, year0 = {}, None
    for i in range(doc.page_count):
        year, rows = br.parse_hist_page(doc[i])
        # 有些页码没印年份，靠「第 i 页 = 首页年份 - i」推 —— 这是 PDF 的固定排版，
        # 首页是最新年，逐页往前推一年。
        if year is None:
            year = (year0 - i) if year0 else None
        if i == 0:
            year0 = year
        if year is None:
            continue
        for m in range(12):
            td = rows.get('trading_days') or []
            if m >= len(td) or not td[m]:
                continue                       # 未来月份的空格
            key = f'{year}-{m + 1:02d}'
            out[key] = {k: (rows.get(k) or [None] * 12)[m] for k, _ in br.LABELS}
    if not out:
        raise IbkrFetchError('历史指标 PDF 解析不出任何月份，疑似排版变更或下到了拦截页')
    return out


def latest_month(cache_dir=None):
    """官方源当前最新月 'YYYY-MM'（以有 trading_days 的最后一月为准）。"""
    return max(_hist(_pipeline()))


def update(series_dir, cache_dir=None):
    """把官方还没入库的月份写进 series/ibkr.csv 并补下该月新闻稿，返回新增月份列表。

    幂等：已有的月份不重复追加，也不改写（官方极少重述，真要重刷历史请手工全量重建）。
    """
    br = _pipeline()
    data = _hist(br)
    csv_path = os.path.join(series_dir, 'ibkr.csv')
    if not os.path.exists(csv_path):
        raise IbkrFetchError(f'series/ibkr.csv 不存在: {csv_path}')
    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    head, body = rows[0], rows[1:]
    have = {r[0] for r in body}
    # 照抄既有行尾。csv.writer 默认写 \r\n，而这份文件是纯 LF —— 直接用默认值会把
    # 整份 128 行重写成 CRLF，于是「本月新增 1 行」的真实改动被 128 行行尾变更淹没，
    # git diff 完全看不出发生了什么。fetch/tsm.py 早就踩过并防住了这条。
    with open(csv_path, 'rb') as f:
        term = '\r\n' if b'\r\n' in f.read(4096) else '\n'

    cols = head[1:]
    unknown = [c for c in cols if c not in {k for k, _ in br.LABELS}]
    if unknown:
        raise IbkrFetchError(f'series/ibkr.csv 有 ibkr_source.LABELS 里没有的列 {unknown}，'
                             f'两边口径已分叉，拒绝写入')

    added = []
    for key in sorted(data):
        if key in have:
            continue
        rec = data[key]
        missing = [c for c in cols if rec.get(c) is None]
        if missing:
            # 缺列一律失败，绝不静默写空 —— 空值会一路画成 null 点上线而全程无报错。
            raise IbkrFetchError(f'{key} 解析缺列 {missing}')
        body.append([key] + [rec[c] for c in cols])
        added.append(key)

    if added:
        body.sort(key=lambda r: r[0])
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f, lineterminator=term)
            w.writerow(head)
            w.writerows(body)

    # 补下最新月的 Metrics 新闻稿（佣金与订单规模来源，历史 PDF 里没有）。
    # 下不到不算失败：新闻稿偶尔比历史表晚几小时，build/ibkr.py 会自动只用
    # 已缓存的连续区间画佣金图，缺口不会被画成直线。
    newest = max(data)
    ym = newest.replace('-', '')
    pr = os.path.join(br.CACHE, f'pr_{ym}.pdf')
    # 判有效而不只判存在。只判 exists 时，一个 0 字节残骸就等于「已经有了」→ 永不重试，
    # 而 build/ibkr.py 会崩在 EmptyFileError → 该家每次 FAIL；等 series 里已经写进这个月
    # 之后，fetch 又会认为「没有新月份」而返回 NOCHANGE ——
    # 于是 IBKR **永久**停在旧月份，调度器每天读到的却是 NOTHING_TO_DO。
    if not os.path.exists(pr) or os.path.getsize(pr) < 5000:
        if os.path.exists(pr):
            os.remove(pr)                       # 残骸先清掉，否则下面这次成功也覆盖不干净
        try:
            br.curl(br.PR_URL.format(ym=ym), pr)
        except Exception as e:
            print(f'[ibkr] {newest} 新闻稿暂时下不到（佣金图会少一个月）: {e}')

    return added


if __name__ == '__main__':
    print('latest:', latest_month())
