# -*- coding: utf-8 -*-
"""端到端校验：页面壳能不能取到、data/*.js 是不是合法且自洽。

分两段，都不依赖浏览器：

**A. HTTP 段** —— 起一个 `python3 -m http.server`（绑 127.0.0.1 的空闲端口，跑完就杀），
用 urllib 抓每张页的 `index.html`，再把页面里 `<script src>` / `<link href>` 引到的
每个静态文件各抓一遍。`file://` 打开时相对路径的坑（大小写、目录名带连字符、
data 文件名与目录名不一致）在这一段全部现形，而且现形方式就是 404，不用人眼看。

**B. payload 段** —— 逐个 `data/*.js`：
  1. `node --check` 判合法 JS（有 node 才做；没有就降级为「能不能被当 JSON 解析」）
  2. 掐掉 `window.DASH = ` 前后缀后 `json.loads`，`parse_constant` 顶掉 NaN/Infinity
  3. 顶层字段齐不齐（CONTRACT.md §1）
  4. 每个 exhibit：kind 在 17 种白名单内、必填对象在不在、所有数据数组长度是不是都等于
     该图 xlabels 的长度、heat_matrix 的 matrix 维度对不对、格式器名与颜色名认不认得、
     以及「不容忍 null」的四种图型里有没有 null（见 docs/CHART_KINDS.md §1.2）

**为什么长度检查值得单独跑一遍**：引擎的绘图循环是 `for i < xlabels.length`，
数组长了的部分画不出来**但仍然参与纵轴量程**——图被一个看不见的点压扁，没有任何提示；
数组短了则是尾部静默变缺失。两种都不报错、不影响退出码，只能靠外部校验抓。

退出码：有 ERROR 返回 1（可进 CI / monthly_run）；只有 WARN 返回 0。

用法:
    python3 build/verify_pages.py
    python3 build/verify_pages.py --pages exchanges12,exchanges-na,exchanges-eu
    python3 build/verify_pages.py --data-only
"""
import argparse
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, 'data')

# assets/charts.js 认得的全部 kind。多一个少一个都要在这里同步（引擎是唯一真源）。
KINDS = {
    'bar_line', 'bar_line_dual', 'bars_labeled', 'bridge_bar', 'diverging_bars',
    'grouped_bars', 'gs_bar', 'gs_line', 'gs_line_avg', 'heat_matrix', 'lines',
    'lines_endlabels', 'qtr_bar', 'range_band', 'seasonality', 'stacked_dual', 'year_lines',
}
FMTS = {'f0', 'f1', 'f2', 'f3', 'f0c', 'int', 'pct0', 'pct1', 'pct2', 'pct0z',
        'pp0', 'pp1', 'x0', 'usd0', 'usd1', 'usd2', 'usd3', 'usd4'}
COLORS = {'NAVY', 'BLUE', 'MBLUE', 'GRAY', 'GREEN', 'RED', 'GOLD',
          'WHITE', 'GRID', 'AXIS', 'INK'}
TOP_REQUIRED = ['ticker', 'tracker', 'title', 'data_through', 'through_label',
                'subtitle', 'headline', 'source', 'xlabels', 'summary', 'exhibits', 'notes']
# 平滑类图型：null 会被 JS 当 0 参与 Catmull-Rom，画出一条塌到零的假线（还不报错）。
DENSE = {'gs_line', 'gs_line_avg', 'lines_endlabels', 'stacked_dual'}
# page.js 用 textContent 灌的字段（set()）。里面写 HTML 标签不会加粗，只会把
# `<b>` 三个字符原样印在抬头上 —— 静默、不报错，只有截图才看得见。
TEXT_ONLY = ['tracker', 'title', 'subtitle', 'headline', 'through_label']
TAG = re.compile(r'</?(?:b|i|em|strong|br|code|span|sup|sub|u)\b[^>]*>', re.I)

ERRORS, WARNS = [], []


def err(where, msg):
    ERRORS.append((where, msg))


def warn(where, msg):
    WARNS.append((where, msg))


# ────────────────────────────── A. HTTP 段 ──────────────────────────────
def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def serve():
    """起 http.server，等它真的能连上再返回 (proc, base_url)。"""
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1'],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            c = http.client.HTTPConnection('127.0.0.1', port, timeout=0.5)
            c.request('HEAD', '/')
            c.getresponse()
            c.close()
            return proc, f'http://127.0.0.1:{port}'
        except OSError:
            time.sleep(0.05)
    proc.terminate()
    raise SystemExit('起不来 http.server')


def fetch(url):
    """→ (status, body_text)。取不到时 status 为 0 并把原因放进 body。"""
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception as e:                                    # 连接层面的失败
        return 0, str(e)


REF = re.compile(r'<(?:script[^>]*\ssrc|link[^>]*\shref)=["\']([^"\']+)["\']', re.I)


def orphan_dirs(pages):
    """扫仓库根下所有「长得像页面目录」的东西，找出不在名单里的孤儿页。

    并行开发时最容易留下的垃圾就是改名后没删掉的旧目录（如 exchanges_na/），
    它仍然是一张能打开的页，只是 data src 指向一个已经不存在的文件 —— 404 之后
    页面显示「缺少 data/*.js」，看起来像「这页坏了」而不是「这页该删了」。
    """
    known = set(pages) | {'assets', 'data', 'series', 'build', 'fetch', 'cache', 'docs'}
    for d in sorted(os.listdir(ROOT)):
        p = os.path.join(ROOT, d, 'index.html')
        if d.startswith('.') or d in known or not os.path.exists(p):
            continue
        with open(p, encoding='utf-8') as f:
            html = f.read()
        for ref in REF.findall(html):
            if not ref.startswith('../data/') or ref.endswith('roster.js'):
                continue
            if not os.path.exists(os.path.join(ROOT, 'data', os.path.basename(ref))):
                err(f'{d}/', f'孤儿页面目录：它引用的 {ref[3:]} 不存在 —— '
                             f'多半是改名后没删掉的旧壳，确认后 rm -rf {d}/')


def check_pages(base, pages):
    """抓每张页 + 页面引用的每个静态文件。返回「引用了但 404 的 data 文件」列表。"""
    missing_data = []
    orphan_dirs(pages)
    for t in pages:
        url = f'{base}/{t}/'
        st, body = fetch(url)
        if st != 200:
            err(f'{t}/', f'GET {url} → {st or "连接失败"} {body[:80]}')
            continue
        refs = REF.findall(body)
        if not refs:
            err(f'{t}/', 'index.html 里一个 <script src> / <link href> 都没有')
        print(f'  {t}/index.html  200  ({len(body)} bytes, {len(refs)} 个引用)')
        for ref in refs:
            ru = urllib.parse.urljoin(url, ref)
            rst, _ = fetch(ru)
            path = urllib.parse.urlparse(ru).path
            flag = 'OK ' if rst == 200 else f'{rst or "ERR"}'
            print(f'      {flag:>4}  {path}')
            if rst == 200:
                continue
            if path.startswith('/data/') and path.endswith('.js'):
                missing_data.append((t, path))
                warn(f'{t}/', f'引用的 {path} 还不存在（{rst}）—— 页面会显示「缺少 data/*.js」')
            else:
                err(f'{t}/', f'引用的 {path} 取不到（{rst}）')
    return missing_data


# ────────────────────────────── B. payload 段 ──────────────────────────────
BAD_LIT = re.compile(r'(?<![A-Za-z0-9_$."])(NaN|Infinity|undefined)(?![A-Za-z0-9_$])')


def js_check(path):
    """node --check：只解析不执行，判 JS 合法性。没装 node 就返回 None（跳过）。"""
    node = shutil.which('node')
    if not node:
        return None
    r = subprocess.run([node, '--check', path], capture_output=True, text=True)
    return (r.returncode == 0, (r.stderr or r.stdout).strip().splitlines()[:3])


def load_payload(path, tag):
    with open(path, encoding='utf-8') as f:
        txt = f.read()

    first = txt.split('\n', 1)[0]
    if not first.startswith('// 由 build/'):
        warn(tag, f'首行不是「// 由 build/… 生成于 …」的构建注释：{first[:60]!r}')
    if not txt.rstrip().endswith(';'):
        warn(tag, '文件末尾不是 “;”，与 payload_guard.write_dash 的写法不一致')
    if 'window.DASH' not in txt:
        err(tag, '文件里没有 window.DASH 赋值')
        return None

    for m in BAD_LIT.finditer(txt):
        # 只报正文里的裸字面量；JSON 字符串里出现的英文单词由 payload_guard 另行管
        s = max(0, m.start() - 30)
        err(tag, f'出现 JS 字面量 {m.group(1)}：…{txt[s:m.end() + 30]}…')
        break

    body = txt[txt.index('{'):txt.rindex('}') + 1]

    def boom(x):
        raise ValueError(f'JSON 里出现 {x}')
    try:
        return json.loads(body, parse_constant=boom)
    except Exception as e:
        err(tag, f'payload 不是合法 JSON：{e}')
        return None


def arrays_of(ex):
    """→ [(字段路径, 数组)]，该 exhibit 里全部「按 x 轴逐点」的数组。"""
    out = []

    def take(name, obj, key='values'):
        if isinstance(obj, dict) and isinstance(obj.get(key), list):
            out.append((f'{name}.{key}', obj[key]))

    for k in ('values', 'lo', 'hi', 'actual'):
        if isinstance(ex.get(k), list):
            out.append((k, ex[k]))
    for k in ('bar', 'line', 'net', 'yoy', 'base'):
        take(k, ex.get(k))
    if isinstance(ex.get('actual'), dict):          # seasonality 的 actual 是对象
        take('actual', ex['actual'])
    for grp in ('series', 'stacks', 'groups'):
        for i, s in enumerate(ex.get(grp) or []):
            take(f'{grp}[{i}]', s)
    return out


def endlabel_collision(ex, nlab):
    """复算 charts.js 的几何，判断 `lines` 的末点标签会不会被 spreadY 收成一摞贴右上角。

    不是「height < 325 就报」——那条经验值只对**末点恰好是全图最大值**的图成立
    （build/exchanges.py 的 LINE_H_ENDLABEL 注释就是这么推的），照它一刀切会把 14 张
    已验收页里 23 张末点不在顶部的图全部误报。这里按引擎的真实公式算一遍：

      spreadY 的兜底条件是 `arr[0].y < M.t + 7`，arr[0].y = Y(最高末点) − 7。

    → 返回 (是否命中, 最高末点距顶的像素数)。
    """
    ser = ex.get('series') or []
    vals = [v for s in ser for v in (s.get('values') or []) if isinstance(v, (int, float))]
    if not vals:
        return False, None
    mn, mx = min(vals), max(vals)
    inc0 = bool(ex.get('zero_line'))
    dmn, dmx = (min(mn, 0), max(mx, 0)) if inc0 else (mn, mx)
    rg = (dmx - dmn) or 1
    if ex.get('zero_base'):
        rz = (mx - mn) or abs(mx) or 1
        y0 = mn - rz * 0.08 if mn < 0 else 0
        y1 = mx * 1.16 if mx > 0 else rz * 0.08
    else:
        y0, y1 = dmn - rg * 0.05, dmx + rg * 0.05
    cap_on = ex.get('ycap') is not None or ex.get('yfloor') is not None
    if ex.get('ycap') is not None:
        y1 = ex['ycap']
    if ex.get('yfloor') is not None:
        y0 = ex['yfloor']
    if y1 <= y0:
        return False, None

    mt = 30 if cap_on else 14
    ph = max(80, (ex.get('height') or 248) - mt)
    tops = []
    for s in ser:
        fin = [v for v in (s.get('values') or []) if isinstance(v, (int, float))]
        if not fin:
            continue
        v = fin[-1]
        if v > y1 or v < y0:          # 末点被截时真值走 capLabel 竖排，不进 spreadY
            continue
        tops.append(ph - (v - y0) / (y1 - y0) * ph)     # = Y(v) − M.t
    if not tops:
        return False, None
    top = min(tops)
    return (top - 7) < 7, round(top, 1)


def check_exhibit(tag, ex, short, long_):
    n = ex.get('n')
    where = f'{tag} Exhibit {n}'
    kind = ex.get('kind')
    if kind not in KINDS:
        err(where, f'kind={kind!r} 不在 17 种白名单内')
        return
    if not ex.get('title'):
        err(where, '没有 title')

    for key in ('fmt', 'yfmt', 'label_fmt'):
        v = ex.get(key)
        if v is not None and v not in FMTS:
            err(where, f'{key}={v!r} 不是引擎认得的格式器名（会静默退回 f1）')
    for path, obj in [(k, ex.get(k)) for k in ('bar', 'line', 'net', 'yoy', 'base', 'actual')] + \
                     [(f'{g}[{i}]', s) for g in ('series', 'stacks', 'groups')
                      for i, s in enumerate(ex.get(g) or [])]:
        if not isinstance(obj, dict):
            continue
        c = obj.get('color')
        if c is not None and c not in COLORS and not str(c).startswith('#'):
            err(where, f'{path}.color={c!r} 不是引擎认得的色名（会静默退回 NAVY）')
        yf = obj.get('yfmt')
        if yf is not None and yf not in FMTS:
            err(where, f'{path}.yfmt={yf!r} 不是引擎认得的格式器名')

    # ── 必填对象：缺了就是 TypeError，整页后续 exhibit 全部不渲染 ──
    need = {
        'bar_line': ['bar', 'line'], 'bar_line_dual': ['bar', 'line'],
        'lines': ['series'], 'lines_endlabels': ['series'], 'year_lines': ['series'],
        'seasonality': ['base', 'actual'], 'grouped_bars': ['groups'],
        'bridge_bar': ['stacks'], 'stacked_dual': ['stacks', 'line'],
        'gs_bar': ['values'], 'gs_line': ['values'], 'gs_line_avg': ['values', 'avg12'],
        'qtr_bar': ['values'], 'diverging_bars': ['values'], 'bars_labeled': ['values'],
        'range_band': ['lo', 'hi', 'actual'],
        'heat_matrix': ['rows', 'matrix'],
    }.get(kind, [])
    for f in need:
        if ex.get(f) is None:
            err(where, f'{kind} 缺必填字段 {f}（引擎会抛 TypeError，本页此图之后的 exhibit 全丢）')
    if kind == 'gs_bar' and ex.get('avg12') is None and not ex.get('yoy'):
        err(where, 'gs_bar 既没有 avg12 也没有 yoy —— 12 个月均线会静默消失，图例却仍写着它')
    # ── gs_bar 的分部堆叠（ex.stacks）──
    # 引擎**不替 payload 求和**：它照着 ex.values 画轴与柱顶数值，照着 stacks 分段填色。
    # 两者对不上时画面不报错 —— 各段之和比总额少一块，就是柱顶留一截空白（看着像
    # 「这个月分部数据只有一部分」，其实是漏了一整块业务）；多一块则最上面那段
    # 溢出柱顶、盖住数值标签。所以恒等式必须在这里硬校验，不能在引擎里兜底。
    if kind == 'gs_bar' and ex.get('stacks'):
        stk = ex['stacks']
        # `yfloor` 与 `ycap` 走的是同一个 clampY —— 漏掉它，被下界钳住的柱会静默
        # 退回单色 #9DC3E6，而那个颜色在图例里根本不存在。
        if (ex.get('ycap') is not None or ex.get('yfloor') is not None
                or ex.get('bar_marks')):
            err(where, 'gs_bar 同时给了 stacks 与 ycap/yfloor/bar_marks —— 引擎对这些柱会'
                       '退回单色，而图例仍列着各分部，读者看到的柱与图例对不上'
                       '（见 charts.js 绘制处注释）')
        # ⚠️ 撞色要连**次轴那条线**一起查，不能只查 stacks 内部：那条线是无描边纯色、
        #    画在柱之后，与某一段同色时它穿过那一段就整段消失（实测创意 92 个月里
        #    15 个、日月光 76 个里 14 个，金线正落在金色段内）。图上看不出、也不报错。
        scols = [s.get('color') for s in stk]
        ycol = ((ex.get('yoy') or {}).get('color')) or ('GOLD' if ex.get('yoy') else None)
        allc = scols + ([ycol] if ycol else [])
        if None in scols or len(set(scols)) < len(scols):
            err(where, f'gs_bar 的 stacks 配色 {scols} 有缺省或重复 —— 同色的两段在一根柱里'
                       f'连不出分界，图例也指不到具体哪一段')
        elif ycol and len(set(allc)) < len(allc):
            err(where, f'gs_bar 的次轴 y/y 线用了 {ycol}，与某一分部段同色 —— '
                       f'折线画在柱之后且无描边，穿过同色段时整段看不见（图例里却有两条 {ycol}）')
        vals = ex.get('values') or []
        # 负的段值：引擎 `Math.max(0, …)` 会把它静默吞成零高，并把它上面那一段整体
        # 抬高 —— 而 `Σ段 ≡ values` 这条恒等式**照样成立**，所以下面那条检查抓不到。
        # 页面上看到的是「某个月某一段凭空消失、另一段变胖」，一个字的提示都没有。
        neg = [(k, i, s['values'][i]) for k, s in enumerate(stk)
               if isinstance(s.get('values'), list)
               for i in range(len(s['values']))
               if isinstance(s['values'][i], (int, float)) and s['values'][i] < 0]
        if neg:
            k0, i0, v0 = neg[0]
            err(where, f'gs_bar 的 stacks 有 {len(neg)} 个负段值（首个在 stacks[{k0}] idx {i0}：'
                       f'{v0!r}）—— 引擎会把它削成零高并抬高上面那一段，而各段之和仍等于'
                       f'总额，恒等式检查抓不到。残差型分部列（合并 − 某分部）最容易踩这条')
        miss, off = [], []
        for i in range(len(vals)):
            if vals[i] is None:
                continue
            parts = [s['values'][i] for s in stk
                     if isinstance(s.get('values'), list) and i < len(s['values'])
                     and s['values'][i] is not None]
            if len(parts) != len(stk):
                miss.append(i)
                continue
            tot = sum(parts)
            if abs(tot - vals[i]) > max(1e-6, abs(vals[i]) * 1e-6):
                off.append((i, tot, vals[i]))
        if miss:
            err(where, f'gs_bar 的 stacks 在 {len(miss)} 个位置有分段缺值（首个在 idx {miss[0]}）'
                       f'—— 那根柱会短一截，看着像那个月分部数据不全')
        if off:
            i0, t0, v0 = off[0]
            err(where, f'gs_bar 的 stacks 有 {len(off)} 个位置各段之和 ≠ values'
                       f'（首个在 idx {i0}：各段和 {t0!r} vs 总额 {v0!r}）—— '
                       f'柱高照总额画、填色照各段画，差额会变成柱顶一截空白或溢出')

    # ── heat_matrix 走自己的维度规则，不吃 xlabels ──
    if kind == 'heat_matrix':
        rows, cols = ex.get('rows') or [], ex.get('cols') or list(range(12))
        m = ex.get('matrix') or []
        if len(m) != len(rows):
            err(where, f'matrix 有 {len(m)} 行，rows 有 {len(rows)} 个 —— 对不上的行画不出来')
        for i, r in enumerate(m):
            if not isinstance(r, list) or len(r) != len(cols):
                err(where, f'matrix[{i}] 长 {len(r) if isinstance(r, list) else "非数组"}，'
                           f'cols 有 {len(cols)} 个 —— 缺的格子会画成浅灰，看着像那个月没数据')
                break
        if ex.get('xlabels'):
            warn(where, 'heat_matrix 不吃 xlabels（它用 rows/cols），这个字段是死的')
        # 12 列的月 × 年矩阵在半栏里是既有页的既定版式（字号自动收缩仍读得出）；
        # 超过 13 列（如 24 个月的动量矩阵）才必须通栏。
        if not ex.get('full') and len(cols) > 13:
            warn(where, f'heat_matrix 有 {len(cols)} 列却没开 full：'
                        f'半栏里每格不到 20px，格内数字会缩到 4.6px 下限')
        return

    # ── 其余 kind：所有数组长度必须等于本图 xlabels 的长度 ──
    lab = ex.get('xlabels') or (long_ if ex.get('x') == 'long' else short)
    if not lab:
        err(where, 'x 轴标签为空（既没有自带 xlabels，DASH 那边也没有）→ 渲染成「无数据」')
        return
    for path, arr in arrays_of(ex):
        if len(arr) != len(lab):
            err(where, f'{path} 长 {len(arr)}，x 轴标签 {len(lab)} 个 —— '
                       + ('多出的点画不出来但仍撑纵轴量程' if len(arr) > len(lab)
                          else '尾部会静默变成缺失'))
        if kind in DENSE and any(v is None for v in arr):
            bad = [i for i, v in enumerate(arr) if v is None]
            err(where, f'{kind} 的 {path} 有 {len(bad)} 个 null（首个在 idx {bad[0]}）——'
                       f'平滑会把 null 当 0，画出一条塌到零的假线'
                       + ('，且逐点标数值时会抛 TypeError' if kind != 'lines_endlabels'
                          else ('，首尾为 null 时抛 TypeError' if 0 in bad or len(arr) - 1 in bad
                                else '（首尾有值，不抛异常，只是画错）')))
    # 多线图的可辨识度：判据是**颜色有没有真的撞上**，不是「线数 > 5」。
    # 数据色恰好有 6 个（NAVY/BLUE/MBLUE/GRAY/GREEN/GOLD），6 条各占一个色是可读的；
    # 早先按 >5 一刀切，会把「5 家 + 其余合计(GRAY)」这种正好用满 6 色的横截面图误报，
    # 而真正的缺陷 —— 两条线同色、读者根本分不开 —— 反倒不在判据里。
    # year_lines 不查：它的颜色由引擎按年份明度阶自动分配，payload 给不给都不算数。
    if kind in ('lines', 'lines_endlabels'):
        ser = ex.get('series') or []
        cols = [s.get('color') for s in ser if s.get('color')]
        dup = sorted({c for c in cols if cols.count(c) > 1})
        if dup:
            warn(where, f'{kind} 有 {len(ser)} 条线，颜色 {dup} 各被用了多次 —— '
                        f'同色的两条线在图上分不开，图例也指不到具体哪条')
        if len(ser) > 6:
            warn(where, f'{kind} 有 {len(ser)} 条线，数据色只有 6 个 —— '
                        f'必然有线同色，该换 heat_matrix（身份靠行标签，不靠颜色）')
    if kind == 'grouped_bars' and len(ex.get('groups') or []) > 4:
        # 只有依赖缺省配色时才是问题：每组显式给了 color 且互不相同，5-6 组是合法的
        # （年份色阶就是这种用法）。数据色一共 6 个，超过 6 组连显式配色也救不了。
        gcols = [g.get('color') for g in ex['groups']]
        if None in gcols or len(set(gcols)) < len(gcols):
            warn(where, f'grouped_bars 有 {len(ex["groups"])} 组，缺省色只有 4 个，第 5 组起重色')
        elif len(ex['groups']) > 6:
            warn(where, f'grouped_bars 有 {len(ex["groups"])} 组，数据色只有 6 个，显式配色也必然重复')
    if kind == 'diverging_bars':
        warn(where, 'diverging_bars 的图例与表格列名在引擎里写死成 COST 的'
                    '「Reported > Core（油汇顺风）」，交易所页会印出「油汇」字样'
                    '（见 docs/CHART_KINDS.md §3.4）')
    if kind == 'lines' and ex.get('end_label'):
        bad, top = endlabel_collision(ex, len(lab))
        if bad:
            err(where, f'lines 开了 end_label，最高末点距绘图区顶只有 {top}px（< 14px）——'
                       f'spreadY 会把整列末点标签收成一摞贴右上角，读数被安到别的线上；'
                       f'把 height 提到 ≥325（现 {ex.get("height") or 248}）')
    if kind == 'stacked_dual' and not ((ex.get('line') or {}).get('ymax')):
        warn(where, 'stacked_dual 没给 line.ymax，右轴按缺省 0..60 画')
    if kind in ('bar_line_dual', 'stacked_dual') and not ex.get('ylab2'):
        warn(where, f'{kind} 是双轴但没给 ylab2，右轴没有标题')


def check_payload(path):
    tag = os.path.basename(path)
    jc = js_check(path)
    if jc is not None and not jc[0]:
        err(tag, 'node --check 判定不是合法 JS：' + ' / '.join(jc[1]))
    d = load_payload(path, tag)
    if d is None:
        return
    stem = tag[:-3]
    for k in TOP_REQUIRED:
        if d.get(k) in (None, ''):
            err(tag, f'顶层缺 {k}')
    # 规范是「目录名 = data 文件名 = ticker」三者逐字相同：roster.py 生成的导航链接是
    # `../<ticker>/`，ticker 与目录名一分叉，导航就指向一个不存在的目录（404）。
    if d.get('ticker') != stem:
        err(tag, f'ticker={d.get("ticker")!r} 与文件名 {stem!r} 不一致 —— '
                 f'page.js 的导航高亮与 roster 的链接都判这个')
    elif not os.path.exists(os.path.join(ROOT, stem, 'index.html')):
        warn(tag, f'ticker={stem!r}，但仓库根下没有 {stem}/index.html —— '
                  f'这份 payload 目前没有页面壳装它')
    if not re.fullmatch(r'\d{4}-\d{2}', str(d.get('data_through', ''))):
        err(tag, f'data_through={d.get("data_through")!r} 不是 YYYY-MM')
    # 这几个字段 page.js 是用 textContent 灌的（set()），标签会被原样印成字面量。
    # 不报错只报 WARN 的东西在这里不合适 —— 它是页面上肉眼可见的 `<b>…</b>`，属于交付缺陷。
    for k in TEXT_ONLY:
        v = d.get(k)
        if isinstance(v, str) and TAG.search(v):
            err(tag, f'{k} 里有 HTML 标签 {TAG.search(v).group(0)!r} —— '
                     f'page.js 的 set() 用 textContent，标签会原样印在页面上；'
                     f'允许 HTML 的是 note / notes / summary 的 cell 与 label')

    # note / notes / summary 走 innerHTML，所以 Markdown 的 `**粗体**` 不会加粗，
    # 而是把四个星号原样印出来。写 note 时手滑用 Markdown 是最常见的一种，
    # 而且只在截图里看得见 —— 页面不报错、payload 也合法。
    def _md(where, s):
        if isinstance(s, str) and '**' in s:
            i = s.index('**')
            warn(where, f'正文里有 Markdown 的 `**`（innerHTML 不解析，会原样印出星号）：'
                        f'…{s[max(0, i - 25):i + 35]}…')
    for i, nt in enumerate(d.get('notes') or []):
        _md(f'{tag} notes[{i}]', nt)
    _md(f'{tag} summary.note', (d.get('summary') or {}).get('note'))
    for e in d.get('exhibits') or []:
        for f_ in ('note', 'src_extra', 'title', 'ylab'):
            _md(f'{tag} Exhibit {e.get("n")}.{f_}', e.get(f_))

    S = d.get('summary') or {}
    if S:
        heads = S.get('heads') or []
        for i, r in enumerate(S.get('rows') or []):
            if r.get('kind') == 'group':
                continue
            if len(r.get('cells') or []) != len(heads):
                err(tag, f'summary.rows[{i}]（{r.get("label")}）有 '
                         f'{len(r.get("cells") or [])} 个 cell，heads 有 {len(heads)} 个')
    T = d.get('table')
    if T:
        keys = [c[1] for c in T.get('cols') or []]
        for i, r in enumerate(T.get('rows') or []):
            miss = [k for k in keys if k not in r]
            if miss:
                err(tag, f'table.rows[{i}] 缺列键 {miss} → 渲染成「—」')
                break

    short, long_ = d.get('xlabels') or [], d.get('xlabels_long') or []
    exs = d.get('exhibits') or []
    ns = [e.get('n') for e in exs]
    if len(set(ns)) != len(ns):
        err(tag, f'exhibit 编号有重复：{ns}')
    # 编号允许 '9a'/'9b' 这种拆图后缀，只要整数部分不倒退即可（页面按数组顺序渲染，
    # 读者按编号读 —— 倒序会让人以为漏了图）。
    seq = [int(re.match(r'\d+', str(x)).group()) for x in ns if re.match(r'\d+', str(x))]
    if seq != sorted(seq):
        warn(tag, f'exhibit 编号不是递增的：{ns} —— 页面按数组顺序渲染，读者按编号读')
    for ex in exs:
        check_exhibit(tag, ex, short, long_)
    kinds = sorted({e.get('kind') for e in exs})
    print(f'  {tag:<22} {len(exs):>2} 张图 · x轴 {len(short)}/{len(long_)} · '
          f'{d.get("data_through")} · {" ".join(kinds)}')


# ────────────────────────────── main ──────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pages',
                    default=('exchanges12,exchanges-na,exchanges-eu,exchanges-apac'
                             ',exchanges-products'),
                    help='逗号分隔的页面目录名')
    ap.add_argument('--data-only', action='store_true', help='跳过 HTTP 段')
    a = ap.parse_args()
    pages = [p for p in a.pages.split(',') if p]

    if not a.data_only:
        print('── A. HTTP 段（python3 -m http.server + urllib）──')
        proc, base = serve()
        try:
            check_pages(base, pages)
        finally:
            proc.terminate()
            proc.wait(timeout=5)
        print()

    print('── B. payload 段（data/*.js）──')
    files = sorted(f for f in os.listdir(DATA) if f.endswith('.js') and f != 'roster.js')
    for f in files:
        check_payload(os.path.join(DATA, f))
    for t in pages:
        if not os.path.exists(os.path.join(DATA, f'{t}.js')):
            warn(f'data/{t}.js', '尚未生成 —— 本页只有壳，打开会显示「缺少 data/*.js」')
    print()

    print(f'── 结果：{len(ERRORS)} 个 ERROR，{len(WARNS)} 个 WARN ──')
    for w, m in ERRORS:
        print(f'  ERROR  {w}: {m}')
    for w, m in WARNS:
        print(f'  WARN   {w}: {m}')
    return 1 if ERRORS else 0


if __name__ == '__main__':
    sys.exit(main())
