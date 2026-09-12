# -*- coding: utf-8 -*-
"""series/sgx.csv 的 `vol_iron_ore_contracts`：把 2025-09 ~ 2026-08 那 12 格少加的
Lump Premium 补回去 —— 一次性，是「已有值永不覆盖」的一次**有据可查**的例外。

用法
    python3 build/basefill/sgx_iron_ore_lump.py                  # 只扫、只核、只打印（不写）
    python3 build/basefill/sgx_iron_ore_lump.py --write          # 核对全过才改写那几格（幂等）
    python3 build/basefill/sgx_iron_ore_lump.py --cache-dir <路径>  # 原件在哪（默认 <仓库根>/cache）

════════════════════════════════════════════════════════════════════════════
一、出了什么事
════════════════════════════════════════════════════════════════════════════
fetch/sgx.py 的 vol_iron_ore_contracts =「各成交量小节里行名含 "Iron Ore" 的行之和」。
2025-09 那期起官方把 `Iron Ore Lump Premium Futures` / `Swaps` 改名为
`SGX Platts Iron Ore CFR China (Lump Premium) Index Futures` / `... Swaps`。新名字折成两行、
数字夹在中间；_parse_page 当时只把下半截接回数值行，标签读成 `Index Futures`，而 "Iron Ore"
恰好在丢掉的上半截里 —— 这一行从此没被加进来。每月少 8,023 ~ 36,473 张，数字看上去完全正常，
商品合计（按小节 Total 取）不受影响，所以「商品 ≥ 铁矿石」那道自检也管不到。
解析器已修（fetch/sgx.py 口径坑 19）。本脚本只管**已经入库**的那 12 格。

════════════════════════════════════════════════════════════════════════════
二、为什么「已有值永不覆盖」在这里可以破例
════════════════════════════════════════════════════════════════════════════
那条规矩（fetch/sgx.py 口径坑 9、update() 的 docstring）防的是**官方重述**：证券成交额是暂定数，
官方会在后续报告里顺延调整；改写历史必须由人决定，不能让抓取器自动吞进来。本次不是那一类：

  ① **不是重述，是本仓误读。** 更正值取自当初入库时读的**同一份 PDF 的同一列**（该期报告的
     M0 列），那个数当时就印在那里。库里那格从来不是「官方的旧值」。同一个数还被下一期报告的
     M-1 列原样重印（2026-08 除外，尚无下一期），两个 vintage 一致。
  ② **由人决定。** 页面所有者 2026-09-12 拿 2026-08 期官方 PDF 逐行手加核实后下令更正。
  ③ **窄到只能改这一种错。** 一格要被改写，必须同时满足：
       · 库里的字符**逐字节等于**「修之前的解析器读同一份 PDF 会得到的值」
         （把 _parse_page 补上的上半截剥掉再算一遍，靠行上的 `lab_head`）；
       · 差额**全部**来自「"Iron Ore" 只出现在补上的那半截里」的行；
       · 月份在下面的 LEDGER 里，且重算出来的新旧两个数与登记的逐位相同。
     库里是任何别的值（官方重述、有人手改、旧版解析器口径不同）一律拒绝，而且**全有或全无**：
     有一处对不上就一格都不写。
  ④ **幂等。** 改完之后库里等于新值，再跑一次什么都不做，文件字节级不变。
  ⑤ **不改会每月误报。** update() 的 _crosscheck_prev_month 每月拿本期报告的上月列对库；
     修好的解析器读 2026-09 期的 Aug-2026 列会得到 4,749,207，库里却是 4,714,191 ——
     每个月都会喊一次假的「官方重述？」，真的重述反而淹没在里面。

**为什么不进 _ERRATA、也不焊进 update()**：_ERRATA 装的是**官方错印**（PDF 本身是错的，
要另一期作证）；这里 PDF 是对的，错在本仓解析器。update() 从不重新解析已入库的月份，
光修解析器治不好这 12 格；为一次性的 12 格在无人值守链路里留一条永久分支又是纯负担 ——
照 build/basefill/hood_2021.py「补完就永远关上」的先例放在这里。

════════════════════════════════════════════════════════════════════════════
三、哪些月份受影响、为什么恰好是这 12 个
════════════════════════════════════════════════════════════════════════════
Lump Premium 从 2015-08 起有量。**受不受影响只看行名折没折行，不看有没有量**：
  · 2015-08 ~ 2025-08 行名是单行（`OTC Iron Ore Lump Premium` / `SGX Iron Ore Lump Premium
    Futures` / `Iron Ore Lump Premium Futures` / `Swaps`），标签里本来就有 "Iron Ore"，
    一直都算进去了。2024-07 ~ 2025-08 连续 14 期缓存 PDF 逐期确认；更早的有缓存的期次
    （2015-01 ~ 2018-04、2018-09、2019-06、2020-01、2021-05、2022-11、2023-07）也全部重算过，
    修前修后逐位相同。
  · 2025-09 ~ 2026-08 共 12 期全是折行的新名字，全部受影响，原件全在缓存里、逐期重算。

2026-09-12 实测的逐格清单（Swaps 那一行 12 期全是 0，差额全部是 Index Futures 那一行的 M0 列）：

    月份      库里（旧）   更正后（新）   差额 = 当期 Lump Premium Index Futures
    2025-09   6,892,804    6,900,827      8,023
    2025-10   5,970,671    5,979,521      8,850
    2025-11   4,782,724    4,792,312      9,588
    2025-12   5,373,102    5,395,972     22,870
    2026-01   6,072,415    6,089,845     17,430
    2026-02   4,671,490    4,690,620     19,130
    2026-03   7,110,182    7,146,655     36,473
    2026-04   5,227,211    5,251,609     24,398
    2026-05   4,884,570    4,897,320     12,750
    2026-06   5,354,979    5,383,753     28,774
    2026-07   5,053,553    5,082,944     29,391
    2026-08   4,714,191    4,749,207     35,016

2026-08 那一格与所有者手加的结果相同：SGX IODEX Iron Ore Futures 4,127,939
+ SGX Options On IODEX Iron Ore Futures 552,512 + Lump Premium Index Futures 35,016
+ Iron Ore 65% Futures 33,740（其余铁矿石行为 0）= 4,749,207。

════════════════════════════════════════════════════════════════════════════
四、没有缓存的 68 个月（2018-05 ~ 2024-06 之间）凭什么说不受影响
════════════════════════════════════════════════════════════════════════════
tools/prune_cache.py 只给 sgx PDF 留最近 24 期（外加早年留下的一批），那 68 期本地没有原件。
它们全落在单行行名那一代里；另有两条独立的数值证据（2026-09-12 实测）：
  · **跨期重印**：有缓存的 PDF 的 M-1 / M-2 / 去年同月列覆盖其中 28 个月，
    修好的解析器读出来与库里逐位相同；
  · **季度与年累计列**：有缓存的 PDF 的 FYxxxxQn / FYTD / CYTD 列里，窗口触及未缓存月份的共 29 个，
    **全部**与库里对应月份逐月求和逐位相等 —— 那些窗口里 Lump Premium 都不为 0，
    库里要是漏了它就对不上。
两条合起来覆盖 57 个月。剩下 11 个月（2020-02 / 03 / 04 / 06、2021-06 ~ 10、2021-12、2022-12）
只有「前后抽查到的期次都是单行行名」这条版式证据，没有逐位的数值证据。要把它们也核死，
把那几期 PDF 下回缓存（fetch/sgx.py 的 _report_index + _fetch_report）再跑本脚本 ——
它扫的是缓存里有的全部期次，受影响的月份若不在 LEDGER 里会拒写并点名。

依赖：pymupdf（经 fetch/sgx.py），与抓取器相同。解析**只有一处定义**：本脚本不自带解析器。
"""
import argparse
import csv
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CSV_PATH = os.path.join(ROOT, 'series', 'sgx.csv')
FETCH = os.path.join(ROOT, 'fetch', 'sgx.py')
COL = 'vol_iron_ore_contracts'

# 2026-09-12 核定的更正清单：{月份: (库里的旧值, 更正值)}，与 docstring 第三节那张表同源。
# 写盘一律要求**当场从 PDF 重算**出同样两个数；原件已被 prune 时只拿它核对「是不是已经改过」，
# 绝不凭它写盘。
LEDGER = {
    '2025-09': (6892804, 6900827),
    '2025-10': (5970671, 5979521),
    '2025-11': (4782724, 4792312),
    '2025-12': (5373102, 5395972),
    '2026-01': (6072415, 6089845),
    '2026-02': (4671490, 4690620),
    '2026-03': (7110182, 7146655),
    '2026-04': (5227211, 5251609),
    '2026-05': (4884570, 4897320),
    '2026-06': (5354979, 5383753),
    '2026-07': (5053553, 5082944),
    '2026-08': (4714191, 4749207),
}


def pipeline():
    """按路径加载 fetch/sgx.py（basefill/ 不在 sys.path 上）。"""
    spec = importlib.util.spec_from_file_location('sgx_fetch', FETCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def strip_heads(blocks):
    """修之前的 _parse_page 会读出的标签：把补上的上半截（`lab_head`）剥掉。

    下半截原先就接得上，所以剥掉上半截正好还原旧标签。浅拷贝，不动传进来的 blocks。
    """
    out = []
    for b in blocks:
        rows = []
        for r in b['rows']:
            h = r.get('lab_head')
            if h:
                if not r['lab'].startswith(h):
                    raise SystemExit('lab_head 不是标签的前缀：%r / %r —— _parse_page 的拼接规则变了，'
                                     '先核本脚本的还原逻辑' % (r['lab'], h))
                r = dict(r, lab=r['lab'][len(h):].strip())
            rows.append(r)
        out.append(dict(b, rows=rows))
    return out


def volume_rows(sgx, blocks):
    """成交量小节里的全部行（与 _read_iron_ore 同一条小节判据）。"""
    for b in blocks:
        t = sgx._lab(b['title'] or '')
        if t.endswith('volume') and 'open interest' not in t:
            for r in b['rows']:
                yield b, r


def head_only_iron(sgx, blocks, mon):
    """"Iron Ore" 只出现在补上的上半截里的行 —— 修之前会被跳过的那几行。"""
    out = []
    for b, r in volume_rows(sgx, blocks):
        h = r.get('lab_head')
        if (h and 'iron ore' in sgx._lab(r['lab'])
                and 'iron ore' not in sgx._lab(r['lab'][len(h):])):
            out.append((r['lab'], sgx._row_value(b, r, mon)))
    return out


def lump_cells(sgx, blocks, mon):
    """Lump Premium 期货 / 掉期两腿的 M0 值（张），供打印「哪些月份有量」。

    掉期腿按行名认两种写法：2018 起叫 `... Lump Premium Swaps`，2015/2016 那代在
    `SGX AsiaClear Cleared Swaps Volume` 节里叫 `OTC Iron Ore Lump Premium`（行名里没有 swap）。
    """
    fut = swp = None
    for b, r in volume_rows(sgx, blocks):
        lab = sgx._lab(r['lab'])
        if 'iron ore' not in lab or 'lump premium' not in lab:
            continue
        v = sgx._row_value(b, r, mon) or 0.0
        if 'swap' in lab or lab.startswith('otc '):
            swp = (swp or 0.0) + v
        else:
            fut = (fut or 0.0) + v
    return fut, swp


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--cache-dir', default=os.path.join(ROOT, 'cache'))
    a = ap.parse_args(argv)
    sgx = pipeline()

    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    idx = {c: i for i, c in enumerate(header)}
    by_month = {r[0]: r for r in body if r and r[0].strip()}

    loaded = {}

    def blocks_of(mon):
        if mon not in loaded:
            p = os.path.join(a.cache_dir, 'sgx_%s.pdf' % mon)
            loaded[mon] = sgx._load_blocks(p) if os.path.exists(p) else None
        return loaded[mon]

    fmt = sgx._fmt
    fixes, problems, uncached = [], [], []
    print('── 逐期重算（只列有缓存原件的期次）──')
    print('  月份     库里        修前重算    修后重算    Lump期货  Lump掉期  状态')
    for mon in sorted(by_month):
        cell = by_month[mon][idx[COL]].strip()
        bl = blocks_of(mon)
        if bl is None:
            uncached.append(mon)
            if mon in LEDGER:
                old, new = LEDGER[mon]
                if cell == fmt(new):
                    print('  %s  原件已不在缓存；库里已是登记的更正值 %s' % (mon, cell))
                else:
                    problems.append('%s 在更正清单里但原件不在缓存，库里是 %s —— 无法当场重算，'
                                    '先把 cache/sgx_%s.pdf 下回来' % (mon, cell, mon))
            continue
        new = sgx._read_iron_ore(bl, mon)
        pre = sgx._read_iron_ore(strip_heads(bl), mon)
        missed = head_only_iron(sgx, bl, mon)
        gap = sum(v or 0.0 for _lab, v in missed)
        if abs((new or 0.0) - (pre or 0.0) - gap) > 0.5:
            raise SystemExit('%s：修后 %s − 修前 %s ≠ 折行行之和 %s —— 本脚本的选行规则与 '
                             '_read_iron_ore 走散了，先对齐再跑' % (mon, fmt(new), fmt(pre), fmt(gap)))
        fut, swp = lump_cells(sgx, bl, mon)
        if cell == fmt(new):
            status = '一致' if new == pre else '已更正'
        elif cell == fmt(pre) and new != pre:
            status = '待更正 +%s' % fmt(new - pre)
            if mon not in LEDGER:
                problems.append('%s 修前修后不同（%s → %s），但不在更正清单里 —— 先人工核实，'
                                '再补进 LEDGER' % (mon, fmt(pre), fmt(new)))
            elif LEDGER[mon] != (int(pre), int(new)):
                problems.append('%s 重算得 %s → %s，与更正清单登记的 %s → %s 不符'
                                % (mon, fmt(pre), fmt(new), *map(fmt, LEDGER[mon])))
            comm = float(by_month[mon][idx['vol_commodities_contracts']])
            if new > comm + 0.5:
                problems.append('%s 更正后铁矿石 %s 大于商品合计 %s（_validate 自检 3）'
                                % (mon, fmt(new), fmt(comm)))
            nb = blocks_of(sgx._next_month(mon))
            alt = sgx._read_iron_ore(nb, mon) if nb is not None else None
            fixes.append((mon, cell, fmt(new), missed, alt))
        else:
            status = '对不上'
            problems.append('%s 库里是 %s，既不是修前重算的 %s 也不是修后的 %s —— '
                            '官方重述或有人手改过，本脚本不替人决定' % (mon, cell, fmt(pre), fmt(new)))
        print('  %s  %-10s  %-10s  %-10s  %-8s  %-8s  %s'
              % (mon, cell, fmt(pre), fmt(new), fmt(fut), fmt(swp), status))

    print('\n  无缓存原件、未重算的 %d 个月：%s ~ %s（见 docstring 第四节）'
          % (len(uncached), uncached[0], uncached[-1]) if uncached else '')

    print('\n── 待更正 %d 格 ──' % len(fixes))
    for mon, old, new, missed, alt in fixes:
        cross = ('下一期报告的上月列 = %s %s' % (fmt(alt), '✓' if alt is not None and fmt(alt) == new
                                                   else '⚠ 不同（官方重述？只提示不拦）')
                 if alt is not None else '下一期报告不在缓存')
        print('  %s  %s → %s   漏加的行：%s；%s'
              % (mon, old, new, '；'.join('%s = %s' % (lab, fmt(v)) for lab, v in missed), cross))

    if problems:
        print('\n✗ %d 处对不上，一格都不写：' % len(problems))
        for p in problems:
            print('  · ' + p)
        return 1
    if not fixes:
        print('  无事可做（库里已全部是更正后的值）')
        return 0
    if not a.write:
        print('\n  未加 --write：**未**写入')
        return 0

    for mon, _old, new, _missed, _alt in fixes:
        by_month[mon][idx[COL]] = new
    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')        # series/ 一律 LF，与 fetch/sgx.py 同
        w.writerow(header)
        w.writerows(body)
    print('\n✓ 改写 %s 的 %s 列 %d 格' % (os.path.relpath(CSV_PATH, ROOT), COL, len(fixes)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
