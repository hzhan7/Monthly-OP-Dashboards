# -*- coding: utf-8 -*-
"""IBKR 月度新闻稿口径（CPT / 平均订单规模 / 期货费用比例）的**历史回填**：
把 `series/ibkr_pr.csv` 从空文件补到 2016-02 起逐月。

用法:
    python3 build/basefill/ibkr_pr_2016.py                    # 下载 + 解析 + 核对 + 写 CSV
    python3 build/basefill/ibkr_pr_2016.py --dry              # 只核对、只打印，不写
    python3 build/basefill/ibkr_pr_2016.py --refresh          # 强制重下（版式排查用）
    python3 build/basefill/ibkr_pr_2016.py --cache-dir <路径> # 原件落在哪（默认 cache/ibkr）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
这个文件为什么存在
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CPT（单笔清算订单平均佣金）与 Average Order Size **只印在月度新闻稿上**，官方那份
Historical Brokerage Metrics 表（= `series/ibkr.csv` 的全部内容）里没有这两列。
在此之前这两个数是 `build/ibkr.py` **每次构建现场解析 `cache/ibkr/*.pdf`** 得到的，
而 `cache/` 是 gitignore 的：换一台机器、清一次缓存，佣金那几张图就静默缩回一两个月，
一声不响。这与 `source_dates.py` docstring 里写下的同一条原则冲突 ——
「cache/ 是 gitignore 的、随时可以删……**这和 series/ 是唯一真值、cache/ 只是过程物
是同一条原则**」。所以数值搬进 `series/ibkr_pr.csv`（tracked），`cache/` 只留原件。

`fetch/ibkr.py::update()` 每月往右追一行（并回看几个月补漏），**往左走是另一件事**：
一次性、补完就永远关上，且要处理三种历史版式。照 `build/basefill/hood_2021.py`、
`cboe_2016.py`、`tmx_ciro_2015.py` 的先例放在这里，不焊进无人值守链路。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
天花板是 2016-02，不是 2016-01；中间只有 2021-10 一个洞
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
下载端点 `getFileNew.php?file=<token>` 对**不存在的文件返回 HTTP 200 +
Content-Type: application/pdf + 0 字节**，从不 404 —— 所以「下不到」与「不存在」在
HTTP 层分不开，只能靠反复实测。2026-09-02 全量扫过 2016-01…2026-08 共 128 个月：

  · **2016-01**：`…MetricsPressRelease.pdf` 与 `…MetricsPressRelease1.pdf` 以及
    2/3/4/5/_1/-1/a/A/v1/R1/Final/New/b/.PDF 共 16 种 token 全部 0 字节 → **官方没有**。
  · **2021-10**：同样 16 种 token 全部 0 字节 → **官方没有**（序列中间的一个洞）。
  · **2016-02…2016-09 与 2017-12 / 2020-03** 这 10 个月：规范 token 是 0 字节，但
    **`{YYYYMM}MetricsPressRelease1.pdf`（词尾多一个 1）有文件**。核对过电头与正文：
    2017-12 那份的电头是 "January 2, 2018"、开篇 "699 thousand DARTs"，与
    `series/ibkr.csv` 的 `2017-12,…,699.0,…` 逐字对上；2020-03 那份 1,964 同样对上。
    所以**下载要带后缀回落**（`fetch/ibkr_source.PR_TOKENS`），只试规范 token 会
    白白丢掉 10 个月。

结论：126 个月有稿（2016-02…2026-08 减去 2021-10），2 个月官方没有。**缺月不写行**，
由 `build/ibkr.py` 在连续月份轴上重建成 null —— 不补 0、不插值、不拿邻月顶上。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
解析只有一处定义
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
本脚本**不自带解析器**，一律调 `fetch/ibkr_source.py` 的 `parse_pr` /
`parse_pr_fut_fee`（理由同 `build/ibkr.py` 顶部那段：口径只能有一处定义，各写一份
迟早分叉，而分叉的表现是「回填时算出来的 CPT 与每月例行追加的对不上同一个月」）。

写盘前有一道回归闸：CSV 里**已有的行**重新解析一遍，逐值必须相同，不同就停机。
已有值永不覆盖（同 `hood_2021.py` 的「已有值永不覆盖」）。
"""
import argparse
import csv
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CSV_PATH = os.path.join(ROOT, 'series', 'ibkr_pr.csv')
PIPELINE = os.path.join(ROOT, 'fetch', 'ibkr_source.py')

# 列名带单位后缀，照 series/cboe.csv（rpc_us_options_usd 等）与 series/hood.csv 的写法。
# series/ibkr.csv 自己没有后缀，是因为它的列名被 fetch/ibkr.py 的护栏钉死在
# ibkr_source.LABELS 的键上；新文件没有这条约束。
HEAD = ['month', 'cpt_all_usd', 'cpt_basis',
        'order_size_stocks_shares', 'cpt_stocks_usd',
        'order_size_options_contracts', 'cpt_options_usd',
        'order_size_futures_contracts', 'cpt_futures_usd',
        'fut_fee_pct']


def pipeline():
    """按路径加载 fetch/ibkr_source.py（basefill/ 不在 sys.path 上）。"""
    spec = importlib.util.spec_from_file_location('ibkr_source', PIPELINE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def months(first, last):
    y, m = int(first[:4]), int(first[5:7])
    out = []
    while f'{y}-{m:02d}' <= last:
        out.append(f'{y}-{m:02d}')
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def latest_series_month():
    """回填的右端 = series/ibkr.csv 的最新月（不去猜「今天是几号」）。"""
    path = os.path.join(ROOT, 'series', 'ibkr.csv')
    with open(path, newline='', encoding='utf-8') as f:
        return max(r['month'] for r in csv.DictReader(f) if r.get('trading_days'))


def read_csv():
    if not os.path.exists(CSV_PATH):
        return {}
    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    if not rows:
        return {}
    if rows[0] != HEAD:
        raise SystemExit(f'{CSV_PATH} 的表头与本脚本不一致：\n  盘上 {rows[0]}\n  期待 {HEAD}')
    return {r[0]: r for r in rows[1:] if r}


def row_of(br, month, path):
    """一份新闻稿 → 一行 CSV。解析不出直接抛（绝不静默写空行）。"""
    cpt, so, sc, oo, oc, fo, fc = br.parse_pr(path)
    basis = br.parse_pr_cpt_basis(path)
    fee = br.parse_pr_fut_fee(path)
    return [month, cpt, basis, so, sc, oo, oc, fo, fc, '' if fee is None else fee]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--refresh', action='store_true')
    ap.add_argument('--cache-dir', default=None)
    a = ap.parse_args(argv)

    br = pipeline()
    cache = a.cache_dir or br.CACHE
    os.makedirs(cache, exist_ok=True)
    have = read_csv()
    last = latest_series_month()
    todo = [m for m in months(br.PR_FIRST_MONTH, last) if m not in br.PR_ABSENT]
    print(f'── 目标区间 {br.PR_FIRST_MONTH} → {last}，'
          f'{len(todo)} 个月（已登记「官方没发」的 {len(br.PR_ABSENT)} 个月不在内：'
          f'{"、".join(sorted(br.PR_ABSENT))}）')

    parsed, failed = {}, []
    for m in todo:
        path = os.path.join(cache, f'pr_{m.replace("-", "")}.pdf')
        if a.refresh or not (os.path.exists(path) and os.path.getsize(path) >= 5000):
            try:
                br.download_pr(m, path)
            except Exception as e:
                failed.append((m, f'下载失败: {e}'))
                continue
        try:
            parsed[m] = row_of(br, m, path)
        except Exception as e:
            failed.append((m, f'解析失败: {e}'))
    if failed:
        # 静默跳过 = 悄悄少填几个月，而那正是本脚本要根治的病。
        for m, why in failed:
            print(f'  ✗ {m} {why}')
        raise SystemExit(f'{len(failed)} 个月取不到或解析不了，且它们不在 PR_ABSENT 登记表里。'
                         f'\n先确认是官方真的没发（各 token 都返回 0 字节）还是解析器版式失效：'
                         f'\n · 官方没发 → 补进 fetch/ibkr_source.PR_ABSENT 并写明实测依据；'
                         f'\n · 版式失效 → 改 fetch/ibkr_source.parse_pr，不要在这里另写一个解析器。')

    # ── 回归闸：已有行重新解析必须逐值相同 ──
    drift = [(m, have[m], parsed[m]) for m in sorted(have) if m in parsed
             and [str(x) for x in have[m]] != [str(x) for x in parsed[m]]]
    if drift:
        for m, old, new in drift[:5]:
            print(f'  ✗ {m}\n      盘上 {old}\n      重解 {new}')
        raise SystemExit(f'{len(drift)} 行与重新解析的结果不一致 —— 要么官方重述了历史，'
                         f'要么解析器改动改变了口径。两种都必须人工裁决，不许自动覆盖。')

    added = [m for m in sorted(parsed) if m not in have]
    out = dict(have)
    for m in added:
        out[m] = parsed[m]
    body = [out[m] for m in sorted(out)]
    blanks = sum(1 for r in body for v in r if v == '')
    print(f'── 写盘 ──\n  新增 {len(added)} 行、已有 {len(have)} 行、'
          f'重解一致 {len(have) - len(drift)} 行、空格 {blanks} 个')
    print(f'  区间 {body[0][0]} → {body[-1][0]}，共 {len(body)} 行；'
          f'轴上应有 {len(months(body[0][0], body[-1][0]))} 个月 —— '
          f'差额 {len(months(body[0][0], body[-1][0])) - len(body)} 个月由 PR_ABSENT 解释')
    if a.dry:
        print('  --dry：**未**写入')
        for r in body[:2] + [['…']] + body[-1:]:
            print('    ' + ','.join(str(x) for x in r))
        return 0
    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')       # series/ 一律 LF
        w.writerow(HEAD)
        w.writerows(body)
    print(f'✓ {CSV_PATH}')
    return len(added)


if __name__ == '__main__':
    sys.exit(0 if main() is not None else 1)
