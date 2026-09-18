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
  · 「下一张图」「上一张」这种**按位置说话**的词，挪图之后会静默指错（里面没有数字，
    audit 也抓不到）。写成 `⟨ex:x@+1:下一张图⟩`（x 是那张图的 id，+1 = 紧跟在本图之后，
    -1 = 紧挨在本图之前；一组写 `⟨ex:a,b@+1:下两张⟩`）：真挨着就原样印那个词，
    挪开了就印成「Exhibit N」。「上面那张」「下面那张」这种不要求紧挨的写 `@<` / `@>`
    （`⟨ex:x@<:上面那张⟩` = x 在本图之前任意位置）。只能写在图自己的字段里（图注、
    标题……）——「下一张」是相对那张图说的。
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
    """把 key 放到 dict 的第一个位置、id（有的话）紧随其后（就地改，保住别处对这个 dict
    的引用）。

    图号一直是每张 exhibit 的第一个键；迁移前后的 data/*.js 逐字可比，靠的就是这个。"""
    rest = [(k, v) for k, v in d.items() if k not in (key, 'id')]
    i = d.get('id')
    d.clear()
    d[key] = val
    if i is not None:
        d['id'] = i
    d.update(rest)


def final_ids(ids, order, page=None):
    """生成了的这几张图（ids）按顺序表（含演习钩子）排出来的最终先后。不碰任何 dict。

    给「正文里有按位置说话的句子」的底座用：它要在编号之前就知道谁挨着谁。"""
    where = f'build/{page}' if page else 'exhibits.final_ids'
    pos = _flat(_drill(order, page), where)
    missing = [i for i in ids if i not in pos]
    if missing:
        _die(where, f'这些图生成了、顺序表里却没有：{missing} —— 加进 ORDER 决定它排在哪')
    return sorted(ids, key=lambda i: (pos[i][0], pos[i][1] or 0))


class Seq(int):
    """「一路 n += 1」写法的生成器（build/single.py 那种底座）里的图号计数。

    值照常参与加减、比较、当字典键；**印进正文时是临时占位符 ⟨ex:#k⟩**。等全部图画完、
    每张图有了 id，`bind_seq()` 把它换成 ⟨ex:id⟩，写盘时再按顺序表兑成最终图号。
    这样底座里几十处 f'Exhibit {n}' 一个字不用改，挪图之后照样指对。
    只能用 str() / f'{n}' 印它：'%d' % n 与 int(n) 会绕过占位符，印出建图时的临时号。
    加一个数还是图号（计数器 n += 1）；**两个号相减得到的是位移（普通 int）**，
    印出来就是那个数（sgx 的历史账「前移 4 号」就是这么算的）。"""
    __slots__ = ()

    def __new__(cls, k):
        return super().__new__(cls, int(k))

    def __add__(self, o):
        return Seq(int(self) + int(o))

    __radd__ = __add__

    def __sub__(self, o):
        return int(self) - int(o)

    def __str__(self):
        return f'⟨ex:#{int(self)}⟩'

    __repr__ = __str__

    def __format__(self, spec):
        return str(self) if not spec else format(int(self), spec)


def tag(e, i):
    """给一张已经建好的图补 id，放在 'n' 后面（没有 'n' 就放第一位）。就地改。"""
    rest = [(k, v) for k, v in e.items() if k not in ('n', 'id')]
    n = e.get('n')
    had_n = 'n' in e
    e.clear()
    if had_n:
        e['n'] = n
    e['id'] = i
    e.update(rest)
    return e


def bind_ids(payload, ids, table_seq=None, where=''):
    """「建图时的号是 Seq、正文里是 ⟨ex:#k⟩」的生成器，写盘前的收口：
    ids = {Seq: id}（每张图建图时的号 → 它的 id）。给每张图补 id、把正文换成 ⟨ex:id⟩；
    编号留给 write_dash（它按 payload['order'] 把 Seq 就地换成最终号）。"""
    tab = {int(k): v for k, v in ids.items()}
    for e in payload.get('exhibits') or []:
        k = int(e['n'])
        if k not in tab:
            _die(where, f'建图时的号 {k} 没有登记 id（标题：{e.get("title", "")!r}）')
        tag(e, tab[k])
    if table_seq is not None:
        tab[int(table_seq)] = TABLE_ID
    return bind_seq(payload, tab, where)


_SEQ = re.compile(r'⟨ex:#(\d+)⟩')


def console(text, ids, payload):
    """只给控制台打印用：正文之外那几行自检里拼进去的 ⟨ex:#k⟩ 换成最终号。
    ids = {Seq: id}，payload 是 write_dash 之后（已编号）的那份。"""
    fin = {e.get('id'): e.get('n') for e in payload.get('exhibits') or []}
    k2n = {int(k): fin.get(i) for k, i in ids.items()}
    return _SEQ.sub(lambda m: str(k2n.get(int(m.group(1)), m.group(0))), str(text))


def bind_seq(node, table, where=''):
    """把正文里的 ⟨ex:#k⟩ 换成 ⟨ex:table[k]⟩（table：建图时的临时号 → id）。就地改。

    临时号对不上任何一张图 → 构建失败：那是正文指着一张最后没进页面的图。"""
    bad = []

    def rep(m):
        k = int(m.group(1))
        if k not in table:
            bad.append(k)
            return m.group(0)
        return f'⟨ex:{table[k]}⟩'

    def walk(x):
        if isinstance(x, dict):
            for k in list(x):
                x[k] = walk(x[k])
            return x
        if isinstance(x, list):
            for j in range(len(x)):
                x[j] = walk(x[j])
            return x
        if isinstance(x, str) and '⟨ex:#' in x:
            return _SEQ.sub(rep, x)
        return x
    walk(node)
    if bad:
        _die(where, f'正文里指着建图时的临时号 {sorted(set(bad))}，可那几号最后没有对应的图'
                    f'（现有 {sorted(table)}）—— 多半是图画不成被跳过了，而指它的那句话还在')
    return node


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
        if isinstance(old, Seq):
            # 底座建图时的临时号（mrbase 那种把 'n' 追加在 dict 末尾的写法）：就地换成最终号，
            # 键的位置不动 —— 迁移前后的 data/*.js 逐字可比。
            e['n'] = n
        else:
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


_POS = re.compile(r'([^@]+)@([+-]\d+|[<>]):(.+)\Z', re.S)


def _cjk(ch):
    """位置引用退回「Exhibit N」时两侧要不要补空格：紧挨着汉字 / 字母数字才补，标点不补。"""
    return '\u4e00' <= ch <= '\u9fff' or ch.isalnum()


class _Resolver:
    def __init__(self, page, local, data_dir, mark, index=None):
        self.page, self.local, self.data_dir, self.mark = page, local, data_dir, mark
        self.errors, self.xref = [], {}
        self.index = index or {}      # id → 在页面上的先后（0 起），位置引用用
        self.container = None         # 正在替换的是第几张图自己的字段（None = 页级字段）

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

    def pos(self, body, path, m):
        """⟨ex:x@+1:下一张图⟩：x 真在本图之后紧挨着就印那个词，否则印「Exhibit N」。"""
        g = _POS.match(body)
        if not g:
            self.errors.append((path, f'⟨ex:{body}⟩ 的写法不对（位置引用应为 ⟨ex:id@+1:下一张图⟩）'))
            return None
        ids = [i.strip() for i in g.group(1).split(',')]
        rel, word = g.group(2), g.group(3)
        k = int(rel) if rel not in '<>' else 0
        if self.container is None:
            self.errors.append((path, f'⟨ex:{body}⟩：位置引用只能写在图自己的字段里'
                                      f'（「下一张」是相对那张图说的，页级文字没有「本图」）'))
            return None
        bad = [i for i in ids if i not in self.index]
        if bad or (not k and rel not in '<>'):
            self.errors.append((path, f'⟨ex:{body}⟩：' + (f'{bad} 不是本页的图' if bad
                                                          else '位移不能是 0')))
            return None
        ps = [self.index[i] for i in ids]
        c = self.container
        if rel == '<':
            near = all(p < c for p in ps)
        elif rel == '>':
            near = all(p > c for p in ps)
        else:
            near = (all(b == a + 1 for a, b in zip(ps, ps[1:]))
                    and (ps[0] == c + k if k > 0 else ps[-1] == c + k))
        if near:
            txt = word
        else:
            ns = [self.local[i] for i in ids]
            txt = 'Exhibit ' + (_ranges(ns, '–') if len(ns) > 1 else str(ns[0]))
            s, a, b = m.string, m.start(), m.end()
            if a > 0 and _cjk(s[a - 1]):
                txt = ' ' + txt
            if b < len(s) and _cjk(s[b]):
                txt += ' '
        return self._wrap(txt, body)

    def sub(self, s, path):
        def rep(m):
            body = m.group(1).strip()
            if '@' in body:
                r = self.pos(body, path, m)
            else:
                r = self.group(body, path) if ',' in body else self.one(body, path)
            return m.group(0) if r is None else r
        return PH.sub(rep, s)

    def walk_payload(self, payload):
        """整份 payload：每张图的字段带着「本图是第几张」替换（位置引用要用），其余照常。"""
        for k, e in enumerate(payload.get('exhibits') or []):
            self.container = k
            self.walk(e, f'exhibits[{k}]')
        self.container = None
        for key in list(payload):
            if key != 'exhibits':
                payload[key] = self.walk(payload[key], key)
        return payload

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
            if isinstance(T.get('n'), Seq):
                T['n'] = tn                  # 底座建图时的临时号：就地换，键位不动（同上）
            else:
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

    index = {e.get('id'): k for k, e in enumerate(exs) if e.get('id')}
    audit = os.environ.get('EXHIBITS_AUDIT')
    # 已经兑过一次的 payload（底座在自己的 payload() 里先兑、write_dash 再过一遍）没有占位符，
    # 不许拿它覆盖掉第一次写下的那份带标记的审计副本。
    if audit and _has_ph(payload):
        marked = json.loads(json.dumps(payload, ensure_ascii=False))
        _Resolver(page, local, data_dir, mark=True, index=index).walk_payload(marked)
        os.makedirs(audit, exist_ok=True)
        with open(os.path.join(audit, f'{page}.json'), 'w', encoding='utf-8') as f:
            json.dump(marked, f, ensure_ascii=False)

    r = _Resolver(page, local, data_dir, mark=False, index=index)
    r.walk_payload(payload)
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
