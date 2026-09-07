#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸门表体检 —— `docs/CRON_WIRING.md` §2.2 / §2.3 的表格 vs 代码里的真值。

    python3 tools/check_doc_gates.py             # 人读报告，有分歧退 1
    python3 tools/check_doc_gates.py --selftest  # 判据自测（见文件末）

真值只有两处，本脚本都读源码、不 import（见下面「为什么不 import」）：

    build/roster.py   LAG       = {t: (常规月, 季末月)}   月末后第几天发布
    monthly_run.py    EARLY     = 5                        默认提前量
                      EARLY_BY  = {t: (常规月, 季末月)}   逐家例外
                      FACT_GATE = {t: 理由}                不吃日历闸门的家

    闸门（月末后第几天）= max(0, LAG − EARLY)，EARLY 取 EARLY_BY.get(t, (EARLY, EARLY))

`FACT_GATE` 里的家**没有**日历闸门（每轮真去问一次源），表里闸门那一格写「事实闸门」
而不是数字 —— 本脚本对这两种写法双向对账：在 `FACT_GATE` 里却写了数字、不在里面却
写「事实闸门」，都算分歧。`LAG` / `EARLY_BY` 两列它们照常参与并照常核（`LAG` 删不得，
它另外喂着首页红点与 `audit_stale_cols()`，见 CRON_WIRING.md §2.3 msci 那一段）。

这三行与 `monthly_run.not_due()` 里 `_due_month((lag[0]-early[0], lag[1]-early[1]))`
的算法同源；`not_due` 的 `- 1` 偏移是「`end` 已经是月末 + 1 天」的实现细节，不改变
「闸门开在月末后第 (LAG − EARLY) 天」这个对外口径，所以本脚本只比对差值。

━━ 为什么要有这个脚本 ━━
那张表是**手抄的代码常量**，改了 `EARLY_BY` 而忘了改表，页面上看不出任何异常 ——
与 `build/check_specs.py` 守的是同一类「错了看不出来」的问题。已经漂过两次：

  · 2026-08-14  `EARLY_BY 现有 … 四家` 漏了 lseg（`docs/DELIVERY.md` §4.1 有订正记录）
  · 2026-08-30  b3e9a15 给 umc / ase 加了 `EARLY_BY`，两处表格与两处「五家」
                都没跟着改，2026-09-07 订正 —— 本脚本就是那次订正的产物

━━ 为什么放在 tools/ 而不是接进 preflight ━━
`build/test_guards.py` 与 `build/check_specs.py` 是 `monthly_run.py` 的 **preflight
硬闸**（:1502-1534），它们红一次就是「那天 28 家都不更新」。那个代价换的是「护栏
坏了还继续发」这类**会污染产物**的事故，值。而一张 markdown 表格过期**不影响任何
一页的产出**，拿整轮发布去赌它，方向是反的 —— 与 `monthly_run.check_registry()`
（:405-448）选择只告警不退出的理由一样：「一个忘掉的名字不该让另外二十页今天不发布」。

所以这里走 README「改过生成器或引擎之后」那三条手工校验的同一条路：改 `EARLY_BY` /
`LAG` 就是改引擎，跑那一组的时候顺手把这条也跑了。要更硬的话，正确的接法是照
`report_registry()` 在 monthly_run 收尾处**只打印不退出**，不是塞进 preflight。

━━ 为什么读源码而不是 import ━━
`build/roster.py` 能 import（`check_registry()` 就是这么干的），`monthly_run.py`
不能 —— 它是入口，import 它等于把整套 fetch 依赖拖进来。两边用同一种取法（`ast`
读模块级字面量赋值）才不会出现「roster 那半是真值、monthly_run 那半是抄的」。
代价是 `LAG` / `EARLY_BY` 一旦不再是字面量就读不到 —— 那时本脚本会明说读不到并退 1，
不会假装通过。
"""

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, 'docs', 'CRON_WIRING.md')

DASHES = '—–-'          # 表里「无 EARLY_BY」那一格用的破折号，几种都认
FACT_CELL = '事实闸门'   # 走 FACT_GATE 的家，闸门那一格认这三个字（前后可带强调号）


def rel(path):
    """报错里一律印仓库相对路径（`docs/CRON_WIRING.md`），可直接点开。"""
    r = os.path.relpath(path, ROOT)
    return os.path.basename(path) if r.startswith('..') else r


# ── 真值侧 ────────────────────────────────────────────────────────────────────

def literals(path, names):
    """读模块级 `NAME = <字面量>` 赋值，返回 {name: value}；不 import、无副作用。"""
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read(), filename=path)
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id in names:
                try:
                    out[t.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass                  # 不是字面量了 —— 交给下面的缺项检查报错
    return out


def truth():
    """{ticker: (lag, early, gate, override, fact)}。

    前三项都是 (常规月, 季末月) 二元组；`override` = 这家在 `EARLY_BY` 里有没有
    自己的一条。**必须单独带出来**，不能靠「early == 默认值」倒推 —— 那样一条
    显式写成 `(5, 5)` 的例外会被当成「吃默认」，表里写「—」就查不出来了。
    `fact` = 这家在 `FACT_GATE` 里。为真时 `gate` 那个数照旧算得出来，但**不是对外
    口径**（没人用它），表里那一格该写「事实闸门」—— 同理不能靠 gate 倒推。
    """
    r = literals(os.path.join(ROOT, 'build', 'roster.py'), {'LAG'})
    m = literals(os.path.join(ROOT, 'monthly_run.py'),
                 {'EARLY', 'EARLY_BY', 'FACT_GATE'})
    missing = [n for n, d in (('LAG', r), ('EARLY', m), ('EARLY_BY', m),
                              ('FACT_GATE', m)) if n not in d]
    if missing:
        raise SystemExit('FAIL 读不到代码里的 %s —— 它们不再是模块级字面量赋值了，'
                         '本脚本的真值来源已断，请改 literals() 或改回字面量'
                         % ' / '.join(missing))
    lag_t, early, early_by = r['LAG'], m['EARLY'], m['EARLY_BY']
    fact_gate = m['FACT_GATE']
    out = {}
    for t, lag in lag_t.items():
        e = early_by.get(t, (early, early))
        out[t] = (tuple(lag), tuple(e),
                  (max(0, lag[0] - e[0]), max(0, lag[1] - e[1])),
                  t in early_by, t in fact_gate)
    return out


# ── 文档侧 ────────────────────────────────────────────────────────────────────

def cells(line):
    """markdown 表格行 → 单元格列表（去掉首尾空格与首尾那对竖线）。"""
    return [c.strip() for c in line.strip().strip('|').split('|')]


def parse_pair(cell, what, where, errs):
    """`(14, 14)` → (14, 14)；破折号 → None；其余记一条错误并返回 False。"""
    if cell.strip('`').strip() and all(ch in DASHES for ch in cell.strip('`').strip()):
        return None
    m = re.fullmatch(r'`?\((\d+),\s*(\d+)\)`?', cell.strip())
    if not m:
        errs.append('%s 第 %d 行 %s 这一格读不动：%r' % (where[0], where[1], what, cell))
        return False
    return (int(m.group(1)), int(m.group(2)))


def parse_gate(cell, where, errs):
    """`0（次月 1 号）` → (0, 0)；`8 / 25` → (8, 25)；`**事实闸门**（见下）` → 'FACT'。

    「只认行首」是刻意的：`0（次月 1 号）` 里那个 1 是说明文字，正则若贪心去抓
    整格里的所有数字，就会把它当成季末月的值。同理「事实闸门」必须判在数字正则
    **之前**：那一格现在的「（见下）」不带数字，但将来写成「（见 §2.4）」就会被
    行首正则抓空、写成「事实闸门 12」更会被读成闸门 12。
    """
    if FACT_CELL in cell:
        return 'FACT'
    m = re.match(r'\s*`?(\d+)`?(?:\s*/\s*`?(\d+)`?)?', cell)
    if not m:
        errs.append('%s 第 %d 行 闸门 这一格读不动：%r' % (where[0], where[1], cell))
        return False
    a = int(m.group(1))
    return (a, int(m.group(2)) if m.group(2) else a)


def doc_rows(path):
    """扫出所有「同时有 LAG 与 EARLY_BY 两列」的表格，逐行解析。

    按**表头名字**定位列号而不是写死下标 —— §2.2 与 §2.3 的列数不同（前者多一列
    「官方节奏」），写死下标的话给任一张表加一列注释就会静默错位。
    """
    with open(path, encoding='utf-8') as f:
        lines = f.read().splitlines()
    rows, errs, tables = [], [], 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('|'):
            head = cells(line)
            if 'LAG' in head and 'EARLY_BY' in head:
                tables += 1
                ci = {'t': 0, 'lag': head.index('LAG'), 'early': head.index('EARLY_BY')}
                gate = [k for k, h in enumerate(head) if h.startswith('闸门')]
                if not gate:
                    errs.append('%s 第 %d 行 表头里没有「闸门」列' % (rel(path), i + 1))
                    i += 1
                    continue
                ci['gate'] = gate[0]
                i += 2                    # 跳过表头与 |---| 分隔行
                n = 0
                while i < len(lines) and lines[i].startswith('|'):
                    c = cells(lines[i])
                    where = (rel(path), i + 1)
                    if len(c) <= max(ci.values()):
                        errs.append('%s 第 %d 行 单元格数不够（%d 个）' % (where + (len(c),)))
                    else:
                        rows.append({
                            'ticker': c[ci['t']].strip('`').strip(),
                            'lag':   parse_pair(c[ci['lag']], 'LAG', where, errs),
                            'early': parse_pair(c[ci['early']], 'EARLY_BY', where, errs),
                            'gate':  parse_gate(c[ci['gate']], where, errs),
                            'where': where,
                            'table': tables,
                        })
                        n += 1
                    i += 1
                if n == 0:
                    errs.append('%s 第 %d 行 这张表一行数据都没扫到' % (rel(path), i + 1))
                continue
        i += 1
    return rows, errs, tables


# ── 对账 ──────────────────────────────────────────────────────────────────────

def compare(rows, tru, tables, expect_tables=2):
    errs = []

    def fmt(v):
        if v is None:
            return '—'
        if v == 'FACT':
            return '「%s」' % FACT_CELL
        return '(%d, %d)' % v

    for r in rows:
        t, where = r['ticker'], r['where']
        if t not in tru:
            errs.append('%s 第 %d 行 `%s` 不在 build/roster.py 的 LAG 表里 —— '
                        '要么这家已被删、表没跟着删，要么 ticker 拼错了' % (where + (t,)))
            continue
        lag, early, gate, override, fact = tru[t]
        if r['lag'] is not False and r['lag'] != lag:
            errs.append('%s 第 %d 行 `%s` LAG：表写 %s，roster.py 是 %s'
                        % (where + (t, fmt(r['lag']), fmt(lag))))
        # 吃默认 EARLY 的家表里写「—」，代码里是 (5, 5)：两种写法等价，都放行
        doc_e = r['early']
        if doc_e is not False:
            if doc_e is None and override:
                errs.append('%s 第 %d 行 `%s` EARLY_BY：表写「—」（吃默认），'
                            'monthly_run.py 里其实有一条 %s'
                            % (where + (t, fmt(early))))
            elif doc_e is not None and not override:
                errs.append('%s 第 %d 行 `%s` EARLY_BY：表写 %s，'
                            'monthly_run.py 的 EARLY_BY 里没有这一家（吃默认 %s）'
                            % (where + (t, fmt(doc_e), fmt(early))))
            elif doc_e is not None and doc_e != early:
                errs.append('%s 第 %d 行 `%s` EARLY_BY：表写 %s，monthly_run.py 是 %s'
                            % (where + (t, fmt(doc_e), fmt(early))))
        # 闸门这一格有两种合法写法，按 FACT_GATE 双向对账（写反了哪个方向都要报）
        if r['gate'] is not False:
            if fact and r['gate'] != 'FACT':
                errs.append('%s 第 %d 行 `%s` 闸门：表写 %s，但它在 monthly_run.py 的 '
                            'FACT_GATE 里 —— 不吃日历闸门，这一格该写「%s」'
                            % (where + (t, fmt(r['gate']), FACT_CELL)))
            elif not fact and r['gate'] == 'FACT':
                errs.append('%s 第 %d 行 `%s` 闸门：表写「%s」，但 monthly_run.py 的 '
                            'FACT_GATE 里没有这一家 —— 按 max(0, LAG − EARLY) 应为 %s'
                            % (where + (t, FACT_CELL, fmt(gate))))
            elif not fact and r['gate'] != gate:
                errs.append('%s 第 %d 行 `%s` 闸门：表写 %s，按 max(0, LAG − EARLY) 应为 %s'
                            % (where + (t, fmt(r['gate']), fmt(gate))))

    # 覆盖率兜底：漏扫比算错更隐蔽 —— 表格改了格式、正则一行都没匹配上，
    # 逐行对账会「全过」。所以名单必须双向对齐。
    seen = [r['ticker'] for r in rows]
    dup = sorted({t for t in seen if seen.count(t) > 1})
    if dup:
        errs.append('%s 这几家在表里出现不止一次：%s' % (rel(DOC), ', '.join(dup)))
    absent = sorted(set(tru) - set(seen))
    if absent:
        errs.append('%s 这几家在 roster.py 的 LAG 表里有、两张闸门表里都没有：%s'
                    % (rel(DOC), ', '.join(absent)))
    if tables != expect_tables:
        errs.append('%s 只扫到 %d 张闸门表（应为 %d 张：§2.2 / §2.3）—— '
                    '表格结构变了，本判据可能已经在空转'
                    % (rel(DOC), tables, expect_tables))
    return errs


def check_headcount(path, rows, tru):
    """§2.3 那句「13（§2.2）+ 15（本节）= 28 家」也是手抄的数，一起核。"""
    errs = []
    with open(path, encoding='utf-8') as f:
        text = f.read()
    m = re.search(r'(\d+)（§2\.2）\s*\+\s*(\d+)（本节）\s*=\s*\*\*(\d+)\s*家\*\*', text)
    if not m:
        return ['%s 找不到「N（§2.2）+ N（本节）= N 家」那句话 —— 它被改写了，'
                '本判据这一条已经在空转' % rel(path)]
    a, b, total = (int(x) for x in m.groups())
    n1 = sum(1 for r in rows if r['table'] == 1)
    n2 = sum(1 for r in rows if r['table'] == 2)
    if (a, b) != (n1, n2):
        errs.append('%s 家数那句话：写「%d + %d」，实际两张表是 %d + %d 行'
                    % (rel(path), a, b, n1, n2))
    if total != len(tru):
        errs.append('%s 家数那句话：写「= %d 家」，roster.py 的 LAG 表实际 %d 家'
                    % (rel(path), total, len(tru)))
    if a + b != total:
        errs.append('%s 家数那句话自己都不平：%d + %d ≠ %d'
                    % (rel(path), a, b, total))
    return errs


def main(argv):
    if '--selftest' in argv:
        return 0 if selftest() else 1
    tru = truth()
    rows, errs, tables = doc_rows(DOC)
    errs += compare(rows, tru, tables)
    errs += check_headcount(DOC, rows, tru)
    if errs:
        print('FAIL %d 条：' % len(errs))
        for e in errs:
            print('  · %s' % e)
        print('\n真值在 build/roster.py 的 LAG 与 monthly_run.py 的 EARLY / EARLY_BY '
              '/ FACT_GATE；闸门 = max(0, LAG − EARLY)，FACT_GATE 里的家写「%s」。'
              '改表别忘了 docs/DELIVERY.md §4.1 那份删除清单。' % FACT_CELL)
        return 1
    print('OK %d 家逐行核过（§2.2 / §2.3 两张表），LAG / EARLY_BY / 闸门与代码一致'
          % len(rows))
    return 0


# ── 自测 ──────────────────────────────────────────────────────────────────────
# 判据自己必须先是有效的：这里拿合成表格喂 compare()，确认三种分歧一条都不漏。
# 光靠「跑真表全过」证明不了什么 —— 正则一行都没匹配上时它同样全过。

def selftest():
    #                lag        early     gate       override  fact
    tru = {'aaa': ((7, 7),   (5, 5), (2, 2),   False,    False),
           'bbb': ((15, 15), (7, 7), (8, 8),   True,     False),
           'ccc': ((13, 30), (5, 5), (8, 25),  False,    False)}

    def rows_from(md):
        rows, errs, tables = doc_rows_text(md)
        return rows, errs, tables

    ok = True

    def case(name, md, want):
        nonlocal ok
        rows, perr, tables = rows_from(md)
        # 合成表只有一张，所以 expect_tables=1
        got = len(perr) + len(compare(rows, tru, tables, expect_tables=1))
        if (got > 0) != want:
            print('  ✗ %s：期望%s，实际 %d 条' % (name, '报错' if want else '全过', got))
            ok = False
        else:
            print('  ✓ %s' % name)

    head = '| ticker | LAG | EARLY_BY | 闸门 |\n|---|---|---|---|\n'
    good = (head
            + '| `aaa` | (7, 7) | — | 2 |\n'
            + '| `bbb` | (15, 15) | (7, 7) | 8 |\n'
            + '| `ccc` | (13, 30) | — | 8 / 25 |\n')
    case('全对时不误报', good, False)
    case('闸门算错', good.replace('| (7, 7) | 8 |', '| (7, 7) | 10 |'), True)
    case('EARLY_BY 该有却写「—」', good.replace('| (15, 15) | (7, 7) |',
                                                '| (15, 15) | — |'), True)
    case('EARLY_BY 该无却写了值', good.replace('| `aaa` | (7, 7) | — |',
                                                '| `aaa` | (7, 7) | (5, 5) |'), True)
    case('LAG 抄错', good.replace('(13, 30)', '(13, 31)'), True)
    case('季末月那一档漏抄', good.replace('| 8 / 25 |', '| 8 |'), True)
    case('少一家（漏扫兜底）', head + '| `aaa` | (7, 7) | — | 2 |\n', True)
    case('多一家不在 LAG 表里', good + '| `zzz` | (1, 1) | — | 0 |\n', True)
    # 不在 FACT_GATE 里却写「事实闸门」—— 反方向也必须报
    case('闸门写「事实闸门」但代码里不是',
         good.replace('| `aaa` | (7, 7) | — | 2 |',
                      '| `aaa` | (7, 7) | — | **事实闸门**（见下） |'), True)

    # FACT_GATE 里的家：写「事实闸门」放行、写数字要报（LAG / EARLY_BY 两列照常核）
    fact = {'eee': ((17, 17), (5, 5), (12, 12), False, True)}
    for name, cell, want in (('事实闸门那一格放行', '**事实闸门**（见下）', False),
                             ('FACT_GATE 里的家却写了数字', '12', True)):
        rows, _, tb = rows_from(head + '| `eee` | (17, 17) | — | %s |\n' % cell)
        got = len(compare(rows, fact, tb, expect_tables=1))
        if (got > 0) != want:
            print('  ✗ %s：期望%s，实际 %d 条' % (name, '报错' if want else '全过', got))
            ok = False
        else:
            print('  ✓ %s' % name)

    # 「0（次月 1 号）」那一格：说明文字里的 1 不许被当成季末月的值
    one = {'ddd': ((2, 2), (5, 5), (0, 0), False, False)}
    rows, _, tables = rows_from(head + '| `ddd` | (2, 2) | — | 0（次月 1 号） |\n')
    got = len(compare(rows, one, tables, expect_tables=1))
    if got:
        print('  ✗ 「0（次月 1 号）」被读成两档')
        ok = False
    else:
        print('  ✓ 「0（次月 1 号）」只取行首那个 0')

    print('\n%s' % ('OK 自测通过' if ok else 'FAIL 自测未通过'))
    return ok


def doc_rows_text(md):
    """selftest 专用：把一段 markdown 文本当文件喂给 doc_rows()。"""
    import tempfile
    with tempfile.NamedTemporaryFile('w', suffix='.md', encoding='utf-8',
                                     delete=False) as f:
        f.write(md)
        p = f.name
    try:
        return doc_rows(p)
    finally:
        os.unlink(p)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
