# -*- coding: utf-8 -*-
"""cache/ 的分级清理器 —— 白名单制，只动逐个核过读取语义的文件族。

用法:
    python3 tools/prune_cache.py                # dry-run：只报告，不删
    python3 tools/prune_cache.py --apply        # 真删
    python3 tools/prune_cache.py --keep 12      # 覆盖所有族的保留期数
    python3 tools/prune_cache.py --only sgx     # 只处理某一族

━━ 为什么是白名单而不是「按 mtime 一刀切」 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

cache/ 里 711 MB 不是一堆同质的垃圾，它有四种性质完全不同的东西，
判据是**谁会再读它**，不是**它有多老**：

  1. 不可重下 —— cache/basefill/。里面有只存在于 archive.org 的 CME 规则手册、
     CME 7 年前的每日 SPAN 存档（同期 Settlements API 对 2019 已返回 empty、
     HTTPS 镜像恒 400，那条 FTP 是唯一还活着的通道，见 build/basefill/cme2.py 模块头）、
     以及 ICE reCAPTCHA 墙后只能人工导出的报表（build/basefill/ice_enx2.py）。
     ⇒ 永不清理。它该做的是备份，不是清理。

  2. 热工作集 —— cache/axp/ 与 cache/*_rates/。EDGAR 归档件本身不可变，但
     fetch/rates_*.py 的 rows() **每次运行都要遍历全部申报**做重述对账
     （见 fetch/rates_schw.py:rows() 的 RESTATEMENTS 逻辑）。删掉不丢数据，
     但下一次 cron 要重打几百个 SEC 请求（每个 sleep 0.25s）。
     ⇒ 永不清理。

  3. 删了也会回来 —— lseg_primary_*.xlsx。fetch/lseg_primary.py:843 每次跑
     `for month in _months_between(start, end)` 全区间，走 _cached_download：
     本地有就跳过，没有就重下。删 39 MB，明天早上原样长回来。
     ⇒ 清理没有意义，不做。

  4. 冷档 —— 下面 POLICY 里登记的那些。owner 的 update() 只处理「series CSV 里
     还没有的期次」，历史档在常规运行里再也不会被读到，删了也不会自己回来。
     ⇒ 按期次保留最近 N 期。

保留 N 期而不是全删，是因为还有三种回头用得上它的场合：手工 --backfill、
ASX 那 8 列对上一月的回补、以及发现解析 bug 后就地重解（比重下 138 个 PDF 快得多）。

⚠ 新增数据源之后，它的 cache 文件族默认**不在**这张表里，所以不会被动。
报告末尾会把「未登记的体积」单列出来，就是给这种情况看的 —— 看见它涨了，
就去核一遍那个 fetcher 的读取语义，再决定要不要登记进来。
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, 'cache')

# 永不进入清理逻辑的子目录（性质 1 与 2）。
PROTECTED_DIRS = {
    'basefill':       '不可重下：archive.org 快照 / CME SPAN 2019 FTP 存档 / ICE 人工导出',
    'axp':            'EDGAR 归档，fetch/axp.py 全量重放',
    '_orig_backup':   '人工备份',
    '_series_backup': '人工备份',
}
PROTECTED_SUFFIX = ('_rates',)     # schw_rates / msci_rates / cme_rates / lpla_rates / hkex_rates

# 白名单：文件族 -> (匹配正则含具名组 p=可排序的期次, 默认保留期数, 依据)
# 依据一栏写的是「凭什么断定历史档不会再被读」，改这张表前先把那句话重新验一遍。
POLICY = [
    ('sgx',       re.compile(r'^sgx_(?P<p>\d{4}-\d{2})\.pdf$'), 24,
     'fetch/sgx.py update(): 「已在 CSV 里的月份不重新下载、不重新解析、不重写」'),
    ('asx_mar',   re.compile(r'^asx_mar_(?P<p>\d{4}-\d{2})(?P<sfx>_correction)?\.pdf$'), 24,
     'fetch/asx.py update(): todo = index 里 CSV 还没有的月份 + 最新月的前一月'),
    ('lpla_hist', re.compile(r'^lpla_hist_(?P<p>[\dQ-]+)\.pdf$'), 24,
     'fetch/lpla.py _fetch_latest_historical(): 每次只下 entries[0]，历史档不回读'),
    ('jpx_inv',   re.compile(r'^jpx_stock_val_1_(?P<p>\d{6})\.xls$'), 52,
     'fetch/jpx.py update_investors(): 「只下载 src_file 台账里没有的那些文件」，'
     '台账在 series/jpx_investors.csv 而不是 cache'),
]

# 明确登记「不清理」的族，写在这里是为了让报告能解释它们，而不是落进「未登记」
KNOWN_NO_PRUNE = [
    (re.compile(r'^lseg_primary_(AIM|MM)_'),
     'fetch/lseg_primary.py:843 每次跑全月份区间，_cached_download 本地没有就重下 —— 删了明天回来'),
]


def human(n):
    for u in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or u == 'GB':
            return '%.1f %s' % (n, u) if u != 'B' else '%d B' % n
        n /= 1024.0


def scan():
    """把 cache/ 顶层散文件分成 三堆：可清理的族、已知不清理的族、未登记的。"""
    fams, no_prune, unknown = {}, {}, []
    for name in sorted(os.listdir(CACHE)):
        path = os.path.join(CACHE, name)
        if not os.path.isfile(path):
            continue
        size = os.path.getsize(path)
        for fam, rx, keep, why in POLICY:
            m = rx.match(name)
            if m:
                fams.setdefault(fam, {'keep': keep, 'why': why, 'files': []})
                fams[fam]['files'].append((m.group('p'), name, size))
                break
        else:
            for rx, why in KNOWN_NO_PRUNE:
                if rx.match(name):
                    k = rx.pattern
                    no_prune.setdefault(k, {'why': why, 'n': 0, 'size': 0})
                    no_prune[k]['n'] += 1
                    no_prune[k]['size'] += size
                    break
            else:
                unknown.append((name, size))
    return fams, no_prune, unknown


def protected_report():
    out = []
    for name in sorted(os.listdir(CACHE)):
        path = os.path.join(CACHE, name)
        if not os.path.isdir(path):
            continue
        why = PROTECTED_DIRS.get(name)
        if why is None and name.endswith(PROTECTED_SUFFIX):
            why = 'EDGAR 归档，fetch/rates_*.py 的 rows() 每次全量重放做重述对账'
        total = sum(os.path.getsize(os.path.join(dp, f))
                    for dp, _, fs in os.walk(path) for f in fs)
        out.append((name, total, why))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='真删（默认只报告）')
    ap.add_argument('--keep', type=int, help='覆盖所有族的保留期数')
    ap.add_argument('--only', help='只处理指定族（POLICY 里的第一列）')
    a = ap.parse_args()

    if not os.path.isdir(CACHE):
        print('没有 cache/，无事可做')
        return 0

    fams, no_prune, unknown = scan()
    victims, freed = [], 0

    print('══ 可清理的族 ' + '═' * 52)
    for fam, rx, _, _ in POLICY:
        if fam not in fams or (a.only and a.only != fam):
            continue
        d = fams[fam]
        keep = a.keep if a.keep is not None else d['keep']
        # 期次 token 全部是零填充的，字典序 == 时间序
        rows = sorted(d['files'], key=lambda t: t[0], reverse=True)
        kept, drop = rows[:keep], rows[keep:]
        dsz = sum(s for _, _, s in drop)
        freed += dsz
        victims += [n for _, n, _ in drop]
        print('  %-10s %3d 个 → 保留最近 %d 期，删 %d 个（%s）'
              % (fam, len(rows), keep, len(drop), human(dsz)))
        if drop:
            print('             最旧保留 %s，删除区间 %s … %s'
                  % (kept[-1][0], drop[-1][0], drop[0][0]))
        print('             依据：%s' % d['why'])

    print('\n══ 登记为不清理 ' + '═' * 50)
    for _, d in no_prune.items():
        print('  %d 个 / %s —— %s' % (d['n'], human(d['size']), d['why']))
    for name, total, why in protected_report():
        print('  %-14s %9s —— %s' % (name + '/', human(total), why or '⚠ 未登记的子目录'))

    usz = sum(s for _, s in unknown)
    print('\n══ 未登记的散文件 ' + '═' * 48)
    print('  %d 个 / %s —— 未核过读取语义，不动。' % (len(unknown), human(usz)))
    if usz > 50 * 1024 ** 2:
        print('  ⚠ 已超过 50 MB：去核一遍这些源的 fetcher，该登记的登记进 POLICY。')
    for name, s in sorted(unknown, key=lambda t: -t[1])[:5]:
        print('       %9s  %s' % (human(s), name))

    print('\n══ 结论 ' + '═' * 58)
    print('  可释放 %s（%d 个文件）' % (human(freed), len(victims)))
    if not a.apply:
        print('  这是 dry-run。加 --apply 才真删。')
        return 0

    for name in victims:
        os.remove(os.path.join(CACHE, name))
    print('  已删除 %d 个文件，释放 %s' % (len(victims), human(freed)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
