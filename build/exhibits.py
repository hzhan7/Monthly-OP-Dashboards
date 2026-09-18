# -*- coding: utf-8 -*-
"""图号：每张图一个固定 id，每页一张顺序表，正文里引用图号一律写占位符。

## 怎么用（改页的人只需要读这一节）

    ORDER = ['nna', 'nna-q', 'og', 'bridge', ...]        # 页头：图的先后，就这一张表
    ex.append({'id': 'nna', 'kind': 'gs_bar', ...})      # 不写 'n'
    note = '按季汇总见 Exhibit ⟨ex:nna-q⟩'               # 本页图号：只替换成数字
    note = '/exchanges12/ 的 Exhibit ⟨ex:exchanges12/notional-yoy⟩'   # 别的页
    payload['order'] = ORDER                             # 交给 write_dash，写盘前拿掉

**把 X 图挪到 Y 图后面 = 只改 ORDER 这一张表**，然后 `python3 tools/rebuild.py`。
图头编号、核对表编号、正文里所有 ⟨ex:…⟩ 全部跟着变；别的页指过来的跨页引用由
rebuild.py 的第二轮补齐。

  · id：页内唯一的英文短名，从图的内容起（所有者按标题找图，id 要让人一眼对得上）。
    小写字母 / 数字 / `-` / `_`；`table` 留给末尾核对表（`⟨ex:table⟩` = 核对表的号）。
  · ORDER 里的一项也可以是一组 id（tuple / list）：同一个号带 a/b 后缀（cboe 的 8a / 8b）。
  · ORDER 里列了、本轮没生成的 id 直接跳过（按数据可得性跳图的页）；
    页面上有、ORDER 里没列的 id，以及重复的 id → 构建失败并点名。
  · 编号从 2 起（Exhibit 1 是汇总表，assets/page.js 写死），核对表接在最后一张图之后。
  · 占位符只替换成**数字**，所以「Exhibit ⟨ex:x⟩」「Ex⟨ex:x⟩」「图 ⟨ex:x⟩」都能写。
    一组图写成 `⟨ex:a,b,c⟩`：按号排序，连续三张及以上并成「13–15」，其余用「、」隔开；
    `⟨ex:a,b,c|-⟩` 用半角连字符「13-15」。别写 `⟨ex:a⟩–⟨ex:c⟩` —— 挪走中间那张之后
    它会静默少算一张。
  · 占位符找不到 id → 构建失败。payload 里所有字符串都替换（brief / headline / notes /
    title / glossary / 表格注 / hub_line ……），不用记哪些字段能写。
  · 跨页引用在 payload 里另记一份 `xref`（{'页/id': 号}）：页面不读它，
    `tools/rebuild.py` 靠它找出「指向的页改了号、自己还没重建」的页补建一轮，
    `build/verify_pages.py` 靠它报残留的过期引用（WARN，不拦发布）。
  · 生成器自己要在写盘前用到号（按号登记的护栏、报错信息），可以先调
    `number(ex, ORDER, '<页>')`：就地排好顺序、写上 n，写盘时按同一张表再算一遍必须一致。
    但**正文里的号一律写占位符**，不要 f'Exhibit {e["n"]}' —— 那样的号查不到来源，
    `tools/exhibit_check.py audit` 会把它当成漏改的字面量报出来。
  · 外部文件的图号（「Goldman Sachs … Exhibit 2」）与记录旧编号的改版说明（「原 Exhibit 9」）
    照写字面量，它们本来就不该跟着本页重排变。

没有 ORDER、也没有任何 id 与占位符的老生成器，经过这里**零变化**。

## 为什么不是各页自己一套

cboe / cme / ibkr / hkex / wealth 各自发明过一套「先写占位符、画完再回填」的 ⟨nav:…⟩，
回填的多是**别的图的号**，解决的正是「挪图之后手写的 Exhibit N 成假话」。这里把「号」
这一半收成全站一份；那几套里按内容现算的导航句（「本页哪几张图是单月口径」「mrwin 改了
哪几张的版式」）仍然留在各页，只是它们拼出来的号改成本模块的占位符。

## 两个测试钩子（只在环境变量里生效，正式构建不设）

  EXHIBITS_DRILL=<页>:<id1>,<id2>   重排演习：把该页顺序表里这两项对调（= 临时改 ORDER）
  EXHIBITS_DRILL=<页>:reverse        整张顺序表倒过来（每个号都变，漏改的字面量无处可藏）
  EXHIBITS_AUDIT=<目录>              另写一份「每个替换出来的数字两侧加标记」的 payload 到
                                     <目录>/<页>.json，供 tools/exhibit_check.py audit 找出
                                     没有经过占位符的图号字面量
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), 'data')

FIRST = 2               # Exhibit 1 是汇总表（assets/page.js 写死 'Exhibit 1: '）
TABLE_ID = 'table'      # 末尾核对表（payload['table']）的保留 id

_ID = re.compile(r'[a-z0-9][a-z0-9_-]*\Z')
_PAGE = re.compile(r'[a-z0-9][a-z0-9-]*\Z')
PH = re.compile(r'⟨ex:([^⟩]*)⟩')

# 审计标记（见模块头 EXHIBITS_AUDIT）：私用区字符，不可能出现在正文里。
# 一处替换写成 开标记 + 占位符原文 + MARK_SEP + 兑出来的号 + 闭标记。
MARK_L = ('\ue000', '\ue001')      # 本页
MARK_X = ('\ue002', '\ue003')      # 跨页
MARK_SEP = '\ue004'


class ExhibitsError(SystemExit):
    """既是异常也是非零退出，与 payload_guard.PayloadGuardError 同一种行为。"""


def _die(where, msg):
    raise ExhibitsError(f'{where}: {msg}' if where else msg)


def _ok_id(i):
    return isinstance(i, str) and bool(_ID.match(i)) and i != TABLE_ID


def _members(item):
    return list(item) if isinstance(item, (list, tuple)) else [item]


# ─────────────────────────────── 顺序表 ───────────────────────────────
def _flat(order, where):
    """ORDER → {id: (位置, 组内序号或 None)}，顺带查形状与重复。"""
    if not isinstance(order, (list, tuple)):
        _die(where, f'顺序表应当是 list，现在是 {type(order).__name__}')
    pos = {}
    for p, item in enumerate(order):
        group = isinstance(item, (list, tuple))
        for k, i in enumerate(_members(item)):
            if not _ok_id(i):
                _die(where, f'顺序表第 {p + 1} 项里的 {i!r} 不是合法 id'
                            f'（小写字母/数字/-/_，且不能叫 {TABLE_ID!r}）')
            if i in pos:
                _die(where, f'顺序表里 {i!r} 出现了两次')
            pos[i] = (p, k if group else None)
    return pos


def _drill(order, page):
    """重排演习钩子（见模块头）：只在 EXHIBITS_DRILL 指到本页时生效。"""
    spec = os.environ.get('EXHIBITS_DRILL', '')
    if not spec or not page or spec.split(':', 1)[0] != page:
        return order
    how = spec.split(':', 1)[1] if ':' in spec else ''
    order = list(order)
    if how == 'reverse':
        return order[::-1]
    a, _, b = how.partition(',')
    hit = [i for i, x in enumerate(order) if a in _members(x)]
    hit2 = [i for i, x in enumerate(order) if b in _members(x)]
    if not hit or not hit2:
        _die(page, f'EXHIBITS_DRILL={spec}：顺序表里找不到 {a!r} 或 {b!r}')
    i, j = hit[0], hit2[0]
    order[i], order[j] = order[j], order[i]
    return order


def _put_first(d, key, val):
    """把 key 放到 dict 的第一个位置（就地改，保住别处对这个 dict 的引用）。

    图号一直是每张 exhibit 的第一个键；迁移前后的 data/*.js 逐字可比，靠的就是这个。"""
    rest = [(k, v) for k, v in d.items() if k != key]
    d.clear()
    d[key] = val
    d.update(rest)


def number(exs, order, page=None, first=FIRST):
    """按顺序表就地排序、就地写 n，返回 {id: n}。

    可以在生成器里提前调（要在写盘前用到号的页）；write_dash 会按同一张表再算一遍，
    两次必须一致 —— 所以提前调之后不要再手动改任何一张图的 'n'。"""
    where = f'build/{page}' if page else 'exhibits.number'
    pos = _flat(_drill(order, page), where)

    ids = []
    for e in exs:
        if not _ok_id(e.get('id')):
            _die(where, f'有一张图没有合法 id（标题：{e.get("title", "")!r}，id={e.get("id")!r}）'
                        f'—— 用了顺序表的页，每张图都要有 id')
        ids.append(e['id'])
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        _die(where, f'id 重复：{dup}')
    missing = [i for i in ids if i not in pos]
    if missing:
        _die(where, f'这些图生成了、顺序表里却没有：{missing} —— 加进 ORDER 决定它排在哪')

    exs.sort(key=lambda e: (pos[e['id']][0], pos[e['id']][1] or 0))

    # 一组（tuple）里本轮实际生成了几张：两张以上才带 a/b 后缀，只剩一张就是普通号。
    present = {}
    for e in exs:
        p, k = pos[e['id']]
        present.setdefault(p, []).append(k)
    out, nxt, last_pos, base = {}, first, None, first
    for e in exs:
        p, k = pos[e['id']]
        if p != last_pos:
            base, last_pos = nxt, p
            nxt += 1
        grp = present[p]
        n = (f'{base}{"abcdefghijklmnopqrstuvwxyz"[grp.index(k)]}'
             if k is not None and len(grp) > 1 else base)
        old = e.get('n')
        if old is not None and old != n:
            _die(where, f'图 {e["id"]!r} 已经带着 n={old!r}，顺序表算出来是 {n!r} —— '
                        f'用了顺序表就不要再手写图号')
        _put_first(e, 'n', n)
        out[e['id']] = n
    return out


# ─────────────────────────────── 占位符 ───────────────────────────────
_CACHE = {}


def load_page(page, data_dir=None):
    """读 data/<page>.js → {id: n}（含核对表 'table'）。跨页引用与跨页体检共用这一份。"""
    path = os.path.join(data_dir or DATA, f'{page}.js')
    if not os.path.exists(path):
        raise KeyError(f'data/{page}.js 不存在')
    key = (path, os.path.getmtime(path), os.path.getsize(path))
    if key in _CACHE:
        return _CACHE[key]
    with open(path, encoding='utf-8') as f:
        txt = f.read()
    body = txt.split('\n', 1)[1].strip() if '\n' in txt else txt
    pre = 'window.DASH = '
    if not body.startswith(pre):
        raise KeyError(f'data/{page}.js 不是 window.DASH 格式')
    d = json.loads(body[len(pre):].rstrip(';'))
    m = {e['id']: e.get('n') for e in d.get('exhibits') or [] if e.get('id')}
    if (d.get('table') or {}).get('n') is not None:
        m[TABLE_ID] = d['table']['n']
    _CACHE[key] = m
    return m


def _int_part(n):
    m = re.match(r'\d+', str(n))
    return int(m.group()) if m else None


def _ranges(ns, dash):
    """[13, 14, 15, 17] → '13–15、17'。只有纯整数参与并段，带后缀的号（8a）原样列出。"""
    ints = sorted(n for n in ns if isinstance(n, int))
    rest = sorted((str(n) for n in ns if not isinstance(n, int)),
                  key=lambda s: (_int_part(s) or 0, s))
    parts, i = [], 0
    while i < len(ints):
        j = i
        while j + 1 < len(ints) and ints[j + 1] == ints[j] + 1:
            j += 1
        if j - i >= 2:
            parts.append(f'{ints[i]}{dash}{ints[j]}')
        else:
            parts.extend(str(x) for x in ints[i:j + 1])
        i = j + 1
    return '、'.join(parts + rest)


class _Resolver:
    def __init__(self, page, local, data_dir, mark):
        self.page, self.local, self.data_dir, self.mark = page, local, data_dir, mark
        self.errors, self.xref = [], {}

    def _wrap(self, txt, ref, cross=False):
        if not self.mark:
            return txt
        a, b = MARK_X if cross else MARK_L
        return f'{a}{ref}{MARK_SEP}{txt}{b}'

    def one(self, ref, path):
        if '/' in ref:
            pg, _, i = ref.partition('/')
            if pg == self.page:
                return self.one(i, path)
            if not _PAGE.match(pg) or not _ID.match(i):
                self.errors.append((path, f'⟨ex:{ref}⟩ 的写法不对（应为 ⟨ex:页/id⟩）'))
                return None
            try:
                n = load_page(pg, self.data_dir).get(i)
            except (KeyError, ValueError) as e:
                self.errors.append((path, f'⟨ex:{ref}⟩：{e}'))
                return None
            if n is None:
                self.errors.append((path, f'⟨ex:{ref}⟩：data/{pg}.js 里没有 id={i!r} 的图'
                                          f'（那一页还没迁移、id 拼错、或那张图被删了）'))
                return None
            self.xref[ref] = n
            return self._wrap(str(n), ref, cross=True)
        if ref not in self.local:
            self.errors.append((path, f'⟨ex:{ref}⟩：本页没有 id={ref!r} 的图'
                                      f'（现有 {sorted(self.local)}）'))
            return None
        return self._wrap(str(self.local[ref]), ref)

    def group(self, body, path):
        ids, _, style = body.partition('|')
        if style not in ('', '-'):
            self.errors.append((path, f'⟨ex:{body}⟩：样式只认 |-'))
            return None
        ns = []
        for i in ids.split(','):
            i = i.strip()
            if i not in self.local:
                self.errors.append((path, f'⟨ex:{body}⟩：{i!r} 不是本页的 id'
                                          f'（一组图只能是本页的）'))
                return None
            ns.append(self.local[i])
        return self._wrap(_ranges(ns, style or '–'), body)

    def sub(self, s, path):
        def rep(m):
            body = m.group(1).strip()
            r = self.group(body, path) if ',' in body else self.one(body, path)
            return m.group(0) if r is None else r
        return PH.sub(rep, s)

    def walk(self, node, path=''):
        if isinstance(node, dict):
            for k in list(node):
                node[k] = self.walk(node[k], f'{path}.{k}' if path else str(k))
            return node
        if isinstance(node, list):
            for j in range(len(node)):
                node[j] = self.walk(node[j], f'{path}[{j}]')
            return node
        if isinstance(node, str) and '⟨ex:' in node:
            return self.sub(node, path)
        return node


def _has_ph(node):
    if isinstance(node, dict):
        return any(_has_ph(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_ph(v) for v in node)
    return isinstance(node, str) and '⟨ex:' in node


def resolve(payload, page, data_dir=None):
    """write_dash 在写盘前调：按顺序表编号、替换占位符、记跨页引用。就地改 payload。

    page = data/<page>.js 的页名（跨页引用 ⟨ex:page/id⟩ 用的也是这个名字）。
    老生成器（没有 order、没有 id、没有占位符）原样返回。"""
    where = f'data/{page}.js'
    order = payload.pop('order', None)
    exs = payload.get('exhibits') or []
    if order is None and not any('id' in e for e in exs) and not _has_ph(payload):
        return payload

    T = payload.get('table')
    if order is not None:
        local = number(exs, order, page)
        if T:
            ints = [_int_part(n) for n in local.values()]
            tn = max([i for i in ints if i is not None], default=FIRST - 1) + 1
            if T.get('n') is not None and T['n'] != tn:
                _die(where, f'核对表带着 n={T["n"]!r}，按顺序表应为 {tn} —— 用了顺序表就别手写')
            _put_first(T, 'n', tn)
    else:
        # 没有顺序表、但图带了 id（只为了让别的页能指过来）：号照生成器自己写的。
        local = {}
        for e in exs:
            if 'id' not in e:
                continue
            if not _ok_id(e['id']):
                _die(where, f'Exhibit {e.get("n")} 的 id={e["id"]!r} 不合法')
            if e['id'] in local:
                _die(where, f'id 重复：{e["id"]!r}')
            if e.get('n') is None:
                _die(where, f'图 {e["id"]!r} 没有 n，又没有顺序表')
            local[e['id']] = e['n']
    if T and T.get('n') is not None:
        local[TABLE_ID] = T['n']

    audit = os.environ.get('EXHIBITS_AUDIT')
    if audit:
        marked = json.loads(json.dumps(payload, ensure_ascii=False))
        _Resolver(page, local, data_dir, mark=True).walk(marked)
        os.makedirs(audit, exist_ok=True)
        with open(os.path.join(audit, f'{page}.json'), 'w', encoding='utf-8') as f:
            json.dump(marked, f, ensure_ascii=False)

    r = _Resolver(page, local, data_dir, mark=False)
    r.walk(payload)
    if r.errors:
        lines = '\n'.join(f'  · {p} → {m}' for p, m in r.errors[:20])
        more = f'\n  …… 另有 {len(r.errors) - 20} 处' if len(r.errors) > 20 else ''
        _die(where, f'图号占位符兑现不了，共 {len(r.errors)} 处：\n{lines}{more}')
    if r.xref:
        payload['xref'] = dict(sorted(r.xref.items()))
    return payload


# ─────────────────────────────── 跨页体检 ───────────────────────────────
def stale_xrefs(data_dir=None):
    """→ [(页, '页/id', 记下的号, 现在的号)]：跨页引用写进正文之后，被指向的页改了号。

    tools/rebuild.py 用它决定第二轮重建谁；build/verify_pages.py 用它报 WARN。"""
    d = data_dir or DATA
    out = []
    for f in sorted(os.listdir(d)):
        if not f.endswith('.js') or f == 'roster.js':
            continue
        page = f[:-3]
        try:
            with open(os.path.join(d, f), encoding='utf-8') as fh:
                txt = fh.read()
            if '"xref"' not in txt:
                continue
            body = txt.split('\n', 1)[1].strip()
            xref = json.loads(body[len('window.DASH = '):].rstrip(';')).get('xref') or {}
        except (IndexError, ValueError):
            continue
        for ref, n in xref.items():
            pg, _, i = ref.partition('/')
            try:
                now = load_page(pg, d).get(i)
            except (KeyError, ValueError):
                now = None
            if now != n:
                out.append((page, ref, n, now))
    return out
