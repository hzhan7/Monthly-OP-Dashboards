# -*- coding: utf-8 -*-
"""图号机制（build/exhibits.py）的三件验收工具：对比、字面量审计、重排演习。

    python3 tools/exhibit_check.py snapshot DIR              # 把 data/*.js 拷一份当基线
    python3 tools/exhibit_check.py compare DIR [页 …]        # 与基线逐页比 payload
    python3 tools/exhibit_check.py audit [页 …]              # 找没走占位符的图号字面量
    python3 tools/exhibit_check.py drill 页 [id1,id2|reverse] # 重排演习（默认对调头两张）

末行是总状态（…OK / …FAILED），与 rebuild / gate 同一种读法。

## compare —— 迁移一页之前 snapshot，迁移之后重建再 compare

判据：两边各自去掉新增的键（每张图与核对表的 `id`、顶层的 `xref`）之后，**按原键序**
序列化必须逐字相同 —— 不只是「字典相等」，连键的先后都一样（exhibits.number 把 n
放回每张图的第一个键，就是为了这一条）。不同就印出前几处不同的路径。

## audit —— compare 证明不了「改全了」

没改成占位符的「Exhibit 7」在迁移前后印出来一模一样，compare 照样全绿；要到哪天挪图才会
变成假话。所以 audit 让生成器在 EXHIBITS_AUDIT 模式下另写一份「每个替换出来的号两侧加标记」
的 payload，把带标记的号抹掉之后，正文里还长得像图号的（Exhibit N / Ex N / 图 N）逐条印出来。
剩下的应当只有三种，逐条过目：汇总表「Exhibit 1」、外部文件的图号（GS 报告的 Exhibit 2）、
改版说明里的旧编号（「原 Exhibit 9」）。另外两类假阳性一眼可辨：「图 25 个月」「图 2026-09」。

## drill —— 所有者要的那种演习

EXHIBITS_DRILL 让生成器以为顺序表里两项对调了（等于临时改 ORDER，不动任何文件），然后：
  ① 图头：被对调的两张号互换，其余不动（reverse 时整页倒序、仍从 2 连号）；
  ② 正文：把每个带标记的号换回它的 id 之后，演习前后逐字相同 —— 换句话说，
     变的只有占位符兑出来的数字，而这些数字各自等于演习后那张图的号；
  ③ 跨页：xref 指向本页的那些页用演习后的产物重建一遍，它们兑出来的号跟着变；
  ④ 收尾：去掉演习环境变量把本页与那些页重建回来，data/*.js 必须与演习前逐字相同。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import monthly_run as mr                                    # noqa: E402
sys.path.append(os.path.join(HERE, 'build'))
import exhibits as X                                        # noqa: E402
from payload_guard import body_of                           # noqa: E402

DATA = os.path.join(HERE, 'data')


def pages_all():
    return sorted(f[:-3] for f in os.listdir(DATA) if f.endswith('.js') and f != 'roster.js')


def load(path):
    with open(path, encoding='utf-8') as f:
        txt = f.read()
    body = txt.split('\n', 1)[1].strip()
    return json.loads(body[len('window.DASH = '):].rstrip(';'))


def strip_new(p):
    """去掉迁移新增的键：每张图与核对表的 id、顶层的 xref。就地改并返回。"""
    p.pop('xref', None)
    for e in p.get('exhibits') or []:
        e.pop('id', None)
    if isinstance(p.get('table'), dict):
        p['table'].pop('id', None)
    return p


def _diff_paths(a, b, path='', out=None, cap=8):
    out = [] if out is None else out
    if len(out) >= cap:
        return out
    if type(a) is not type(b):
        out.append(f'{path}: 类型 {type(a).__name__} → {type(b).__name__}')
    elif isinstance(a, dict):
        if list(a) != list(b):
            ka, kb = list(a), list(b)
            if set(ka) != set(kb):
                out.append(f'{path}: 键 −{sorted(set(ka) - set(kb))} +{sorted(set(kb) - set(ka))}')
            else:
                out.append(f'{path}: 键序不同')
        for k in a:
            if k in b:
                _diff_paths(a[k], b[k], f'{path}.{k}' if path else k, out, cap)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f'{path}: 长度 {len(a)} → {len(b)}')
        for i, (x, y) in enumerate(zip(a, b)):
            _diff_paths(x, y, f'{path}[{i}]', out, cap)
    elif a != b:
        if isinstance(a, str):
            i = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            s = max(0, i - 30)
            out.append(f'{path}: …{a[s:i + 40]!r}\n{" " * (len(path) + 4)}→ …{b[s:i + 40]!r}')
        else:
            out.append(f'{path}: {a!r} → {b!r}')
    return out


# ─────────────────────────────── snapshot / compare ───────────────────────────────
def cmd_snapshot(argv):
    if not argv:
        print('用法：snapshot DIR')
        return 2
    os.makedirs(argv[0], exist_ok=True)
    n = 0
    for f in os.listdir(DATA):
        if f.endswith('.js'):
            shutil.copy2(os.path.join(DATA, f), os.path.join(argv[0], f))
            n += 1
    print(f'SNAPSHOT OK {n} 个文件 → {argv[0]}')
    return 0


def cmd_compare(argv):
    if not argv:
        print('用法：compare DIR [页 …]')
        return 2
    base, pages = argv[0], argv[1:] or pages_all()
    bad = []
    for pg in pages:
        a_p, b_p = os.path.join(base, f'{pg}.js'), os.path.join(DATA, f'{pg}.js')
        if not os.path.exists(a_p):
            print(f'  ?  {pg:<20} 基线里没有这一页')
            bad.append(pg)
            continue
        a, b = strip_new(load(a_p)), strip_new(load(b_p))
        ja = json.dumps(a, ensure_ascii=False, separators=(',', ':'))
        jb = json.dumps(b, ensure_ascii=False, separators=(',', ':'))
        if ja == jb:
            ids = sum(1 for e in load(b_p).get('exhibits') or [] if 'id' in e)
            print(f'  ✓  {pg:<20} 一致（{ids} 张图带 id）')
            continue
        bad.append(pg)
        print(f'  ✗  {pg:<20} 不一致：')
        for d in _diff_paths(a, b):
            print(f'       {d}')
    if bad:
        print(f'COMPARE FAILED {len(bad)}/{len(pages)}：{" ".join(bad)}')
        return 1
    print(f'COMPARE OK {len(pages)}/{len(pages)}')
    return 0


# ─────────────────────────────── build helpers ───────────────────────────────
def build(pg, env_extra=None):
    cmd = mr.builder(pg)
    if cmd is None:
        raise SystemExit(f'找不到 {pg} 的生成器')
    env = dict(os.environ)
    env.pop('EXHIBITS_DRILL', None)
    env.pop('EXHIBITS_AUDIT', None)
    env.update(env_extra or {})
    r = subprocess.run(cmd, cwd=HERE, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()
        raise SystemExit(f'{pg} 构建失败：' + '\n'.join(tail[-12:]))


# ─────────────────────────────── audit ───────────────────────────────
REF = re.compile(r'(Exhibits?|Ex\.?|EX|图)\s*(\d+[a-z]?)(?:\s*(?:、|,|，|/|–|-|与|和|及|and)\s*\d+[a-z]?)*')
# exhibits.py 审计模式的一处替换：开标记 + 占位符原文 + MARK_SEP + 兑出来的号 + 闭标记
_MARK_ID = re.compile('([\ue000\ue002])([^\ue004]*)\ue004([^\ue001\ue003]*)([\ue001\ue003])')
_MARKED = _MARK_ID


def _strings(node, path=''):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, f'{path}.{k}' if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, f'{path}[{i}]')
    elif isinstance(node, str):
        yield path, node


def literal_refs(payload):
    """→ [(路径, 命中, 上下文)]：抹掉带标记的号之后，正文里还长得像图号的地方。"""
    out = []
    for path, s in _strings(payload):
        t = _MARKED.sub('#', s)
        for m in REF.finditer(t):
            a, b = max(0, m.start() - 36), min(len(t), m.end() + 30)
            out.append((path, m.group(0), t[a:b].replace('\n', ' ')))
    return out


def cmd_audit(argv):
    pages = argv or pages_all()
    tmp = tempfile.mkdtemp(prefix='exhibit_audit_')
    total = 0
    try:
        for pg in pages:
            build(pg, {'EXHIBITS_AUDIT': tmp})
            mp = os.path.join(tmp, f'{pg}.json')
            if os.path.exists(mp):
                with open(mp, encoding='utf-8') as f:
                    pay = json.load(f)
                tag = '已迁移'
            else:
                pay, tag = load(os.path.join(DATA, f'{pg}.js')), '未迁移（全部是字面量）'
            hits = literal_refs(pay)
            total += len(hits)
            print(f'== {pg}（{tag}）：{len(hits)} 处字面量')
            for path, hit, ctx in hits:
                print(f'   {path:<34} {hit!r:<16} …{ctx}…')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'AUDIT DONE {len(pages)} 页，{total} 处字面量待过目')
    return 0


# ─────────────────────────────── drill ───────────────────────────────
def _idspace(pay, nums):
    """把带标记的号换回 ⟨占位符原文⟩，并逐个核对它兑出来的号 = 该页此刻的号。

    → (新 payload, 错误)。跨页的号不归本页演习管（③ 另查），只换回原文。"""
    errs = []

    def rep(m):
        ref, got = m.group(2), m.group(3)
        if m.group(1) == '\ue000':
            if ',' in ref:
                ids, _, style = ref.partition('|')
                want = X._ranges([nums.get(i.strip()) for i in ids.split(',')], style or '–')
            else:
                want = str(nums.get(ref))
            if got != want:
                errs.append(f'⟨ex:{ref}⟩ 兑成 {got!r}，该页此刻应为 {want!r}')
        return f'⟨{ref}⟩'
    out = json.loads(json.dumps(pay, ensure_ascii=False))

    def walk(node):
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str):
            return _MARK_ID.sub(rep, node)
        return node
    return walk(out), errs


def _by_id(pay):
    """把 exhibits 换成按 id 排序的 dict（演习前后图序不同，按位置比没有意义）。"""
    q = dict(pay)
    q['exhibits'] = {e.get('id', f'#{i}'): {k: v for k, v in e.items() if k != 'n'}
                     for i, e in sorted(enumerate(pay.get('exhibits') or []),
                                        key=lambda t: str(t[1].get('id', f'#{t[0]}')))}
    if isinstance(q.get('table'), dict):
        q['table'] = {k: v for k, v in q['table'].items() if k != 'n'}
    return q


# 一串并列的占位符（「⟨a⟩、⟨b⟩、⟨c⟩」「⟨a⟩ / ⟨b⟩」）：生成器按最终图序串，演习之后先后会变，
# 那是**应该**变的（号仍是升序）。比较前把每一串里的占位符排个序，分隔符原位不动。
_RUN = re.compile(r'⟨[^⟩]+⟩(?:\s*(?:、|,|，|/|与|和|及|and)\s*⟨[^⟩]+⟩)+')
_TOK = re.compile(r'⟨[^⟩]+⟩')


def _sort_runs(node):
    if isinstance(node, dict):
        return {k: _sort_runs(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_sort_runs(v) for v in node]
    if isinstance(node, str):
        def one(m):
            toks = sorted(_TOK.findall(m.group(0)))
            it = iter(toks)
            return _TOK.sub(lambda _m: next(it), m.group(0))
        return _RUN.sub(one, node)
    return node


def cmd_drill(argv):
    if not argv:
        print('用法：drill 页 [id1,id2|reverse]')
        return 2
    pg = argv[0]
    path = os.path.join(DATA, f'{pg}.js')
    with open(path, encoding='utf-8') as f:
        before_txt = f.read()
    base = load(path)
    ids = [e.get('id') for e in base.get('exhibits') or []]
    if not all(ids):
        print(f'DRILL FAILED {pg} 还没迁移（有图不带 id）')
        return 1
    how = argv[1] if len(argv) > 1 else f'{ids[0]},{ids[1]}'
    n0 = {e['id']: e['n'] for e in base['exhibits']}
    if (base.get('table') or {}).get('n') is not None:
        n0[X.TABLE_ID] = base['table']['n']
    # 谁在跨页指向本页
    fans = []
    for other in pages_all():
        if other == pg:
            continue
        xr = load(os.path.join(DATA, f'{other}.js')).get('xref') or {}
        refs = {k: v for k, v in xr.items() if k.startswith(pg + '/')}
        if refs:
            fans.append((other, refs))
    # 横截面页（monthly_run.CROSS）读成员页的 payload：有的按标题认图、现读别页的号
    # （build/wealth.py 的 _xnum），不走 xref，上面那张名单抓不到它们 —— 一并重建来看。
    cross = [c for c in mr.CROSS if c != pg and c not in {o for o, _ in fans}]
    fan_txt = {o: open(os.path.join(DATA, f'{o}.js'), encoding='utf-8').read()
               for o in [o for o, _ in fans] + cross}

    tmp_m, tmp_d = tempfile.mkdtemp(prefix='drill_m_'), tempfile.mkdtemp(prefix='drill_d_')
    fails = []
    try:
        build(pg, {'EXHIBITS_AUDIT': tmp_m})
        with open(os.path.join(tmp_m, f'{pg}.json'), encoding='utf-8') as f:
            marked_m = json.load(f)
        build(pg, {'EXHIBITS_AUDIT': tmp_d, 'EXHIBITS_DRILL': f'{pg}:{how}'})
        drilled = load(path)
        with open(os.path.join(tmp_d, f'{pg}.json'), encoding='utf-8') as f:
            marked_d = json.load(f)
        n1 = {e['id']: e['n'] for e in drilled['exhibits']}
        if (drilled.get('table') or {}).get('n') is not None:
            n1[X.TABLE_ID] = drilled['table']['n']

        # ① 图头
        if how == 'reverse':
            want_ids = [e['id'] for e in base['exhibits']][::-1]
            got_ids = [e['id'] for e in drilled['exhibits']]
            ok = got_ids == want_ids or sorted(got_ids) == sorted(want_ids)
            seq = [e['n'] for e in drilled['exhibits']]
            if not ok or seq != list(range(2, 2 + len(seq))):
                fails.append(f'① 倒序后图序/编号不对：{list(zip(got_ids, seq))}')
            moved = [i for i in n0 if n0[i] != n1[i]]
            print(f'  ① 图头：倒序后 {len(moved)}/{len(seq)} 张改了号（2..{seq[-1]} 连号）')
        else:
            a, b = how.split(',')
            ch = {i: (n0[i], n1[i]) for i in n0 if n0[i] != n1[i]}
            want = {a: (n0[a], n0[b]), b: (n0[b], n0[a])} if isinstance(n0[a], int) \
                and isinstance(n0[b], int) else None
            if want is not None and ch != want:
                fails.append(f'① 图头：应当只有 {want}，实际 {ch}')
            print(f'  ① 图头：{a} {n0[a]}→{n1[a]}，{b} {n0[b]}→{n1[b]}；'
                  f'其余 {len(n0) - len(ch)} 张不动' + ('' if want is None or ch == want
                                                     else f'（异常：{ch}）'))
        tn0, tn1 = (base.get('table') or {}).get('n'), (drilled.get('table') or {}).get('n')
        if tn0 != tn1:
            fails.append(f'① 核对表号变了：{tn0} → {tn1}')

        # ② 正文（id 空间逐字相同 + 兑出来的号 = 演习后的号）
        m_id, e1 = _idspace(marked_m, n0)
        d_id, e2 = _idspace(marked_d, n1)
        fails += [f'② 演习前：{e}' for e in e1] + [f'② 演习后：{e}' for e in e2]
        a_, b_ = _by_id(m_id), _by_id(d_id)
        raw = _diff_paths(a_, b_, cap=10 ** 6)
        diffs = _diff_paths(_sort_runs(a_), _sort_runs(b_), cap=12)
        cnt = sum(len(_MARK_ID.findall(s)) for _, s in _strings(marked_d))
        changed = sum(1 for (_, s0), (_, s1) in zip(_strings(_by_id(marked_m)),
                                                   _strings(_by_id(marked_d))) if s0 != s1)
        print(f'  ② 正文：{cnt} 处占位符兑出来的号{"全部" if not e2 else "并非全部"}等于演习后的图头；'
              f'{changed} 个字符串因此变了'
              + (f'（其中 {len(raw) - len(diffs)} 处是并列的一串图号按新图序重排）'
                 if len(raw) > len(diffs) else '')
              + ('；把号换回 id 之后，其余文字演习前后逐字相同' if not diffs else ''))
        # 换回 id 之后仍然不同的，只可能是「按位置说话」的句子（「排在前一张之后」这种，
        # 生成器按最终图序现算出不同的 id）—— 那是该变的，但要人看一眼变得对不对，不判失败。
        for d in diffs:
            print(f'  △ 按位置现算、演习后指向了别的图（请看一眼是否正确）：\n       {d}')

        # ③ 跨页
        for other, refs in fans:
            build(other)
            xr = load(os.path.join(DATA, f'{other}.js')).get('xref') or {}
            for ref, old in refs.items():
                new = xr.get(ref)
                want_n = n1.get(ref.split('/', 1)[1])
                flag = '✓' if new == want_n else '✗'
                print(f'  ③ 跨页 {flag} {other} → {ref}：{old} → {new}（演习后该图是 {want_n}）')
                if new != want_n:
                    fails.append(f'③ {other} 的 {ref} 兑成 {new}，应为 {want_n}')
        if not fans:
            print('  ③ 跨页：没有别的页用 ⟨ex:' + pg + '/…⟩ 指向本页')
        for c in cross:
            before_c = strip_new(json.loads(json.dumps(
                load(os.path.join(DATA, f'{c}.js')), ensure_ascii=False)))
            build(c)
            dd = _diff_paths(before_c, strip_new(load(os.path.join(DATA, f'{c}.js'))), cap=6)
            if dd:
                print(f'  ③ 横截面 {c} 跟着变了（它现读本页的号，请看一眼指得对不对）：')
                for d in dd:
                    print(f'       {d}')
    finally:
        # ④ 收尾
        build(pg)
        for other in [o for o, _ in fans] + cross:
            build(other)
        # 比的是正文（首行是构建日期注释，演习那一轮会把它刷成今天）；正文逐字相同就把
        # 原文件整份写回去，连首行日期一起复原 —— 演习不该在工作区留下任何改动。
        for p_, t0 in [(path, before_txt)] + [(os.path.join(DATA, f'{o}.js'), fan_txt[o])
                                               for o in [o for o, _ in fans] + cross]:
            with open(p_, encoding='utf-8') as f:
                back = f.read()
            if body_of(back) != body_of(t0):
                fails.append(f'④ {os.path.basename(p_)} 重建回来与演习前不一致')
            elif back != t0:
                with open(p_, 'w', encoding='utf-8') as f:
                    f.write(t0)
        shutil.rmtree(tmp_m, ignore_errors=True)
        shutil.rmtree(tmp_d, ignore_errors=True)
    print(f'  ④ 收尾：{pg}' + ''.join(f'、{o}' for o, _ in fans) + ' 已重建回演习前'
          + ('' if not any(f.startswith('④') for f in fails) else '（有出入，见下）'))
    if fails:
        for f in fails:
            print(f'  ✗ {f}')
        print(f'DRILL FAILED {pg} {how}（{len(fails)} 项）')
        return 1
    print(f'DRILL OK {pg} {how}')
    return 0


def main(argv):
    cmds = {'snapshot': cmd_snapshot, 'compare': cmd_compare, 'audit': cmd_audit,
            'drill': cmd_drill}
    if not argv or argv[0] not in cmds:
        print(__doc__)
        return 2
    return cmds[argv[0]](argv[1:])


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
