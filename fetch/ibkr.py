# -*- coding: utf-8 -*-
"""Interactive Brokers (IBKR) 月度经营指标抓取 —— 复用 /IBKR月度指标 skill 的解析管道。

═══ 源 ═══
IBKR 官网 IR：
  · Historical Brokerage Metrics PDF（11 页，逐年逐月，每月更新）—— 全部存量指标
  · 各月 Metrics 新闻稿 PDF —— 佣金与产品明细，历史 PDF 里没有

下载与解析都走 skill 的 `~/.claude/skills/IBKR月度指标/build_report.py`
（`curl` / `parse_hist_page` / `parse_pr` / `LABELS`）。**本模块不重写解析逻辑**：
那份代码是 skill 与本看板共用的，各写一份迟早分叉，而分叉的表现是
「skill 的 PDF 和网页看板对同一个月给出不同的 DARTs」——最难发现的那种错。

═══ 数据落在哪 ═══
skill 的 `cache/`（hist_latest.pdf + 各月 pr_YYYYMM.pdf）是真值。本模块另把历史指标表
解析成 `series/ibkr.csv`（与其余十一家同构），让总仓自成体系、排查时不用翻到 skill 里去。

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

SKILL = os.path.expanduser('~/.claude/skills/IBKR月度指标')
SKILL_CACHE = os.path.join(SKILL, 'cache')


class IbkrFetchError(RuntimeError):
    """本模块所有失败路径统一抛它，调度器只需 catch 一种。"""


def _skill():
    p = os.path.join(SKILL, 'build_report.py')
    if not os.path.exists(p):
        raise IbkrFetchError(f'找不到 skill 解析管道: {p}')
    spec = importlib.util.spec_from_file_location('ibkr_br', p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hist(br, refresh=True):
    """下载并解析历史指标 PDF，返回 {'YYYY-MM': {列: 值}}。

    每次都重下：这个 PDF 是判断「官方发新数据了没有」的唯一依据，
    吃缓存等于永远看不到新月份。
    """
    os.makedirs(SKILL_CACHE, exist_ok=True)
    path = os.path.join(SKILL_CACHE, 'hist_latest.pdf')
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
    return max(_hist(_skill()))


def update(series_dir, cache_dir=None):
    """把官方还没入库的月份写进 series/ibkr.csv 并补下该月新闻稿，返回新增月份列表。

    幂等：已有的月份不重复追加，也不改写（官方极少重述，真要重刷历史请手工全量重建）。
    """
    br = _skill()
    data = _hist(br)
    csv_path = os.path.join(series_dir, 'ibkr.csv')
    if not os.path.exists(csv_path):
        raise IbkrFetchError(f'series/ibkr.csv 不存在: {csv_path}')
    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    head, body = rows[0], rows[1:]
    have = {r[0] for r in body}

    cols = head[1:]
    unknown = [c for c in cols if c not in {k for k, _ in br.LABELS}]
    if unknown:
        raise IbkrFetchError(f'series/ibkr.csv 有 skill LABELS 里没有的列 {unknown}，'
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
            w = csv.writer(f)
            w.writerow(head)
            w.writerows(body)

    # 补下最新月的 Metrics 新闻稿（佣金与订单规模来源，历史 PDF 里没有）。
    # 下不到不算失败：新闻稿偶尔比历史表晚几小时，build/ibkr.py 会自动只用
    # 已缓存的连续区间画佣金图，缺口不会被画成直线。
    newest = max(data)
    ym = newest.replace('-', '')
    pr = os.path.join(SKILL_CACHE, f'pr_{ym}.pdf')
    if not os.path.exists(pr):
        try:
            br.curl(br.PR_URL.format(ym=ym), pr)
        except Exception as e:
            print(f'[ibkr] {newest} 新闻稿暂时下不到（佣金图会少一个月）: {e}')

    return added


if __name__ == '__main__':
    print('latest:', latest_month())
