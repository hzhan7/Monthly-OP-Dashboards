# -*- coding: utf-8 -*-
"""季度费率总入口 —— 把六家的 rates_*.py 合并进 series/fee_rates.csv。

接口与其余 fetch/<t>.py 一致（只是键从「月」换成「季」）：

    latest_period(cache_dir) -> 'YYYY-Qn'      各家最新季里**最老**的那个
    update(series_dir, cache_dir) -> [(company, period), ...]   新增/更新的格

════════ 为什么 latest_period 取 min 而不是 max ════════
这张表是横着用的：build/cme.py 拿 CME 的 RPC、build/hkex.py 拿 HKEX 的费率，
但**下一轮**要做的「费率过期披露」是一句面向读者的话 ——「本页费率截至 20XX-Qn」。
只要有一家还停在上个季度，整张表就只能算到那一家为止：说 2026-Q2 而 HKEX 只有
2026-Q1，等于对着 HKEX 那几张图撒谎。所以 max 是「最乐观的说法」，min 才是
「全表都成立的说法」。这也是为什么它叫 latest_period 而不是 latest_quarter ——
它回答的是「这张表整体有效期到哪」，不是「谁最新」。

    实测 2026-08-05：AXP/CME/LPLA/MSCI/SCHW 都到 2026-Q2，HKEX 只到 2026-Q1
    （HKEX 的 Q2 数字要等 8 月中下旬的中期业绩公告）→ latest_period = 2026-Q1。

════════ 合并规则 ════════
按 **(company, period, metric)** 三元组合并，与各消费方读这张表的方式一致
（build/*.py 一律 `d[(d.company==X) & (d.metric==Y)]` 再按 period 建索引）。

1. **已有行默认不覆盖。** 官方会重述（AXP 2019 的三个季度、SCHW 2025-Q2 的
   平均生息资产都实测改过数），而重述不是「新数据」，是「对旧数据的改口」。
   自动改写历史会让「这个数昨天还不是这样」发生在无人值守的深夜且无人知晓，
   所以重刷历史必须显式 `update(..., overwrite=True)`（CLI `--overwrite`）。
   默认模式下这些分歧不是被丢掉了 —— `--check` 会逐条列出来给人看。
2. **新增行追加**，不重排、不重写既有行。
3. 一家解析失败不影响其余各家：记下来继续跑，成功的照常写盘，最后把失败清单
   一并抛出（异常对象带 `.added` / `.failures`，别让已写盘的成果在异常里丢掉）。
4. **一家要么全写要么不写**：先把该家 rows() 全量解析 + 校验完，再决定落盘。
   半份数据比没有数据更坏 —— 图上会画出一段真的、一段缺的，而缺的那段被
   ffill 成直线，看上去完全正常。

════════ 为什么不整表重写 ════════
这份 CSV 是 CRLF、列序 company,period,metric,value,unit,source_url。
用 `csv.writer` 默认参数重写会把 372 行全换成 LF（或反过来），于是「本季新增 6 行」
这个唯一有信息量的改动被 372 行行尾变更淹没，git diff 完全看不出发生了什么。
fetch/ibkr.py 和 fetch/cost.py 都为同一件事写过防御，这里第三次写：
**既有行按原始字节原样保留，新行追加在末尾**，行尾从文件里探出来而不是猜。
副作用是全表不再按 (company, period) 全局有序 —— 无所谓，六个消费方
（build/{axp,cme,hkex,lpla,msci,schw}.py + build/bridge.py）读进来都自己
`sort_index()`，没有一个依赖文件内的行序。

写盘走临时文件 + os.replace（原子替换）：中途崩掉时 series/fee_rates.csv
要么是旧的、要么是新的，不会是半截的。

════════ 各家解析器的分工 ════════
本模块**不解析任何东西**，只做合并与落盘。谁去哪个网站、怎么认表头、哪个季度
该用哪份文件，全在各自的 fetch/rates_<company>.py 里，那里也是踩坑记录的所在地。
本模块对它们的唯一要求是 `rows(cache_dir) -> list[dict]`，每条含
period / metric / value / unit / source_url（company 可给可不给，不给由这里补）。
"""
import argparse
import csv
import importlib.util
import io
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CSV_NAME = 'fee_rates.csv'
# 列序即文件里的列序。对不上就拒绝写 —— 按列名重排会把整表重写一遍（见模块 docstring），
# 按位置硬写则会把 value 写进 unit 列，两种都是灾难。
HEADER = ['company', 'period', 'metric', 'value', 'unit', 'source_url']

# (CSV 里的 company 值, fetch/ 下的模块名)。company 由这里指定而不是信解析器 ——
# 解析器里有三家根本不产出 company 字段（约定「由上层补」），
# 另外三家产出了，两边不一致时以这里为准并直接抛错。
COMPANIES = (
    ('AXP', 'rates_axp'),
    ('CME', 'rates_cme'),
    ('HKEX', 'rates_hkex'),
    ('LPLA', 'rates_lpla'),
    ('MSCI', 'rates_msci'),
    ('SCHW', 'rates_schw'),
)

_PERIOD_RE = re.compile(r'^\d{4}-Q[1-4]$')


class FeeRatesError(RuntimeError):
    """本模块所有失败路径统一抛它。

    `.added` 带上**异常发生前已经成功写盘**的 (company, period)，`.failures` 带
    [(company, 原因)]。调度器把异常转成 FAIL 时至少能把这两样打进日志 ——
    否则「五家成功一家失败」在日志里看起来和「六家全失败」一模一样。
    """

    def __init__(self, msg, added=None, failures=()):
        super().__init__(msg)
        self.added = list(added or [])
        self.failures = list(failures)


# ══════════════════════ 各家解析器 ══════════════════════

_MODS = {}


def _load(modname):
    """按文件路径加载 fetch/rates_*.py。

    不用 `import rates_xxx`：本模块会被 monthly_run.py 用
    spec_from_file_location 加载，那时 fetch/ 根本不在 sys.path 上，
    裸 import 会 ModuleNotFoundError。
    """
    if modname in _MODS:
        return _MODS[modname]
    path = os.path.join(HERE, modname + '.py')
    if not os.path.exists(path):
        raise FeeRatesError(f'缺解析器 {path}')
    spec = importlib.util.spec_from_file_location(f'fee_rates__{modname}', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, 'rows'):
        raise FeeRatesError(f'{modname} 没有 rows(cache_dir)')
    _MODS[modname] = mod
    return mod


_MEMO = {}


def company_rows(company, modname, cache_dir):
    """跑一家的 rows() 并做全量校验，返回规范化后的列表。

    同一进程里按 (company, cache_dir) 记忆结果：latest_period() 和 update() 都要
    全量解析，连着调两次会把六家的网络+解析重跑一遍（HKEX 一次 30 秒）。
    """
    ck = (company, os.path.abspath(cache_dir))
    if ck in _MEMO:
        return _MEMO[ck]
    raw = _load(modname).rows(cache_dir)
    out = _validate(company, modname, raw)
    _MEMO[ck] = out
    return out


def forget():
    """清掉本进程的解析结果记忆（长驻进程里想重抓时用）。"""
    _MEMO.clear()


def _validate(company, modname, raw):
    """把 rows() 的输出校验成可以直接落盘的形状。任何一条不合格 → 整家不写。

    校验的是「会静默毁掉这张表」的那几类错，不是形式主义：
      · period 写成 '2026Q2' / '2026-06' → 消费方的 PeriodIndex 会解析成别的季度；
      · value 是 NaN → CSV 里落成 'nan'，pandas 读回来是 NaN，图上被 ffill 成直线；
      · source_url 空 → 下一轮的「费率过期披露」拿不到出处，只能编；
      · 同一家自己给出重复的 (period, metric) → 后写的赢，而谁后写取决于字典序。
    """
    if not isinstance(raw, list):
        raise FeeRatesError(f'{modname}.rows() 返回 {type(raw).__name__}，应为 list')
    if not raw:
        raise FeeRatesError(f'{modname}.rows() 返回空列表 —— 官方源大概率改版了')

    out, seen = [], {}
    for i, r in enumerate(raw):
        where = f'{modname}.rows()[{i}]'
        if not isinstance(r, dict):
            raise FeeRatesError(f'{where} 不是 dict')
        got = r.get('company')
        if got is not None and got != company:
            raise FeeRatesError(f'{where} company={got!r}，与登记的 {company!r} 不符')

        period = r.get('period')
        if not isinstance(period, str) or not _PERIOD_RE.match(period):
            raise FeeRatesError(f'{where} period={period!r} 不是 YYYY-Qn')

        rec = {'company': company, 'period': period}
        for col in ('metric', 'unit', 'source_url'):
            v = r.get(col)
            if not isinstance(v, str) or not v.strip() or v != v.strip():
                raise FeeRatesError(f'{where} {col}={v!r} 为空或带首尾空白')
            rec[col] = v
        if not rec['source_url'].startswith(('http://', 'https://')):
            raise FeeRatesError(f'{where} source_url={rec["source_url"]!r} 不是 URL')

        v = r.get('value')
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise FeeRatesError(f'{where} value={v!r} 不是数字')
        if isinstance(v, float) and not math.isfinite(v):
            raise FeeRatesError(f'{where} value={v!r}（NaN/Inf 一律拒收）')
        rec['value'] = v

        key = (period, rec['metric'])
        if key in seen:
            raise FeeRatesError(
                f'{modname} 自己给出重复的 {key}：{seen[key]} 与 {rec["value"]}')
        seen[key] = rec['value']
        out.append(rec)
    return out


# ══════════════════════ CSV 读写 ══════════════════════

def _read_csv(path):
    """读 series/fee_rates.csv，返回 (整份原文, 行尾, 逻辑行列表)。

    行尾从文件里探出来。这份文件目前是 CRLF；混合行尾一律拒绝 ——
    混着时无论追加哪一种都会在 diff 里制造噪音，而人只会以为是自己编辑器干的。
    """
    if not os.path.exists(path):
        raise FeeRatesError(f'{path} 不存在（本模块只增量合并，不负责从零建表）')
    with open(path, newline='', encoding='utf-8') as f:
        text = f.read()
    if not text.strip():
        raise FeeRatesError(f'{path} 是空文件')

    if '\r\n' in text:
        term = '\r\n'
        if text.count('\n') != text.count('\r\n') or text.count('\r') != text.count('\r\n'):
            raise FeeRatesError(f'{path} 行尾 CRLF/LF 混用，拒绝写入（先统一行尾）')
    else:
        term = '\n'
        if '\r' in text:
            raise FeeRatesError(f'{path} 含裸 CR，拒绝写入')

    rows = list(csv.reader(io.StringIO(text, newline='')))
    if rows[0] != HEADER:
        raise FeeRatesError(f'{path} 表头是 {rows[0]}，期望 {HEADER}')
    return text, term, rows


def _split_lines(text, term, n_rows, path):
    """按行尾切成物理行，并断言「一条逻辑行 = 一条物理行」。

    这条断言是「按行号原地替换既有行」的前提。字段里若真出现换行（会被 csv 加引号），
    行号就对不上了，那时宁可拒绝写，也不能按错位的行号去改别人的行。
    """
    lines = text.split(term)
    trailing = lines and lines[-1] == ''
    if trailing:
        lines.pop()
    if len(lines) != n_rows:
        raise FeeRatesError(
            f'{path} 有 {n_rows} 条逻辑行但 {len(lines)} 条物理行'
            f'（字段里含换行？），拒绝写入')
    return lines, trailing


def _encode(fields):
    """按 csv 规则编成一行（不含行尾）。目前没有任何字段需要引号，但不自己拼逗号。"""
    buf = io.StringIO()
    csv.writer(buf, lineterminator='').writerow(fields)
    return buf.getvalue()


def _int_styles(rows):
    """{(company, metric): 该指标现有行是否清一色不带小数点}。

    只为让追加的新行与同一列已有的写法一致：LPLA 的 client_cash_revenue 现有行
    写成 377782，而解析器返回的是 float，直接 repr 会写出 377782.0 —— 同一列里
    两种写法，读的人第一反应是「这两行口径不一样吗」。反过来 AXP 的
    net_interest_yield_newbasis 现有行是 8.0，收敛成 8 同样刺眼。
    所以不定规矩，跟着文件里已有的写法走；没有先例时保留解析器给的类型。
    """
    style = {}
    for r in rows[1:]:
        k = (r[0], r[2])
        style[k] = style.get(k, True) and ('.' not in r[3])
    return style


def _fmt(value, style_int):
    """数值 → CSV 字符串。int 直出；float 用 repr（最短往返表示，不引入假精度）。"""
    if isinstance(value, int):
        return str(value)
    f = float(value)
    if style_int and f.is_integer():
        return str(int(f))
    s = repr(f)
    if 'e' in s or 'E' in s:
        # 科学计数法在这张表里没出现过，真出现了说明某家的单位换挡了，
        # 与其写一个 pandas 读得懂但人读不懂的 1e-05，不如炸。
        raise FeeRatesError(f'value={value!r} 会被写成科学计数法 {s}，先查单位')
    return s


def _atomic_write(path, text):
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)


# ══════════════════════ 对外接口 ══════════════════════

def latest_periods(cache_dir):
    """{company: 该家官方当前可得的最新季度}。任何一家失败即抛。"""
    latest, failures = {}, []
    for company, modname in COMPANIES:
        try:
            rs = company_rows(company, modname, cache_dir)
        except Exception as e:                                   # noqa: BLE001
            failures.append((company, f'{type(e).__name__}: {e}'))
            continue
        latest[company] = max(r['period'] for r in rs)
    if failures:
        raise FeeRatesError(
            '无法确定全表有效期，这几家没跑通：'
            + '；'.join(f'{c}: {m}' for c, m in failures), failures=failures)
    return latest


def latest_period(cache_dir):
    """全表有效期 = 各家最新季度里**最老**的那个（'YYYY-Qn' 可直接字典序比较）。"""
    return min(latest_periods(cache_dir).values())


def update(series_dir, cache_dir, overwrite=False):
    """合并六家的 rows() 进 series/fee_rates.csv，返回新增/更新的 (company, period)。

    · 新 (company, period, metric) → 追加。
    · 已有的 → 默认原样不动；overwrite=True 时若 value/unit/source_url 有任何一项
      不同就整行改写（官方重述、或某家换了更权威的出处时才该开）。
    · 幂等：没有任何新增/改动时不碰文件，返回 []。连跑两次第二次必然是 []。
    · 某家失败 → 其余各家照常写盘，最后一并抛 FeeRatesError（.added 里有已写的）。

    返回值按 (company, period) 去重排序 —— 一个季度动了 16 个 metric 时，
    上层要的是「HKEX 2026-Q1 有新数据」这一条，不是 16 条。
    """
    path = os.path.join(series_dir, CSV_NAME)
    text, term, rows = _read_csv(path)
    lines, trailing = _split_lines(text, term, len(rows), path)
    style = _int_styles(rows)

    # (company, period, metric) → (物理行下标, 该行字段)
    index = {(r[0], r[1], r[2]): (i + 1, r) for i, r in enumerate(rows[1:])}

    failures, touched = [], set()
    appended, replaced = [], {}

    for company, modname in COMPANIES:
        try:
            parsed = company_rows(company, modname, cache_dir)
        except Exception as e:                                   # noqa: BLE001
            failures.append((company, f'{type(e).__name__}: {e}'))
            continue

        # ↓ 这一段是「要么全写要么不写」的落点：整家先在暂存区里算完，
        #   中途任何一条出错都在 except 里整家跳过，不会有半份进 stage。
        try:
            stage_add, stage_rep = [], {}
            for r in parsed:
                key = (company, r['period'], r['metric'])
                fields = [company, r['period'], r['metric'],
                          _fmt(r['value'], style.get((company, r['metric']), False)),
                          r['unit'], r['source_url']]
                hit = index.get(key)
                if hit is None:
                    stage_add.append((key, _encode(fields)))
                    continue
                i, old = hit
                if not overwrite or list(old) == fields:
                    continue
                stage_rep[i] = (key, _encode(fields), list(old))
        except Exception as e:                                   # noqa: BLE001
            failures.append((company, f'{type(e).__name__}: {e}'))
            continue

        appended.extend(stage_add)
        replaced.update(stage_rep)
        for key, _line in stage_add:
            touched.add((key[0], key[1]))
        for key, _line, _old in stage_rep.values():
            touched.add((key[0], key[1]))

    if appended or replaced:
        for i, (_key, line, _old) in replaced.items():
            lines[i] = line
        # 追加行按 (company, period, metric) 排一次序，让新增块本身可读；
        # 既有行一个字节都没动，git diff 就是纯粹的「多了这些行」。
        appended.sort(key=lambda kv: kv[0])
        lines.extend(line for _key, line in appended)
        _atomic_write(path, term.join(lines) + (term if trailing else ''))

    added = sorted(touched)
    if failures:
        raise FeeRatesError(
            f'{len(failures)} 家没跑通（其余各家已写入 {len(appended)} 新行 / '
            f'改写 {len(replaced)} 行）：'
            + '；'.join(f'{c}: {m}' for c, m in failures),
            added=added, failures=failures)
    return added


# ══════════════════════ CLI ══════════════════════

def _check(series_dir, cache_dir):
    """只读对账：现有表 vs 六家解析器，把差异分类打出来，一个字节都不写。"""
    path = os.path.join(series_dir, CSV_NAME)
    _text, _term, rows = _read_csv(path)
    style = _int_styles(rows)
    cur = {(r[0], r[1], r[2]): r for r in rows[1:]}

    n_add = n_same = 0
    val_d, url_d, unit_d, fails = [], [], [], []
    for company, modname in COMPANIES:
        try:
            parsed = company_rows(company, modname, cache_dir)
        except Exception as e:                                   # noqa: BLE001
            fails.append((company, f'{type(e).__name__}: {e}'))
            continue
        for r in parsed:
            key = (company, r['period'], r['metric'])
            old = cur.get(key)
            if old is None:
                n_add += 1
                continue
            v = _fmt(r['value'], style.get((company, r['metric']), False))
            if old[3] != v:
                val_d.append((key, old[3], v))
            elif old[4] != r['unit']:
                unit_d.append((key, old[4], r['unit']))
            elif old[5] != r['source_url']:
                url_d.append((key, old[5], r['source_url']))
            else:
                n_same += 1

    print(f'现有 {len(cur)} 行；完全一致 {n_same} / 待新增 {n_add} / '
          f'值不同 {len(val_d)} / 单位不同 {len(unit_d)} / 仅出处不同 {len(url_d)}')
    for tag, lst in (('值', val_d), ('单位', unit_d)):
        for key, a, b in lst:
            print(f'  {tag}不同  {key[0]:5} {key[1]} {key[2]}: 表内 {a} / 解析器 {b}')
    for key, a, b in url_d:
        print(f'  出处不同 {key[0]:5} {key[1]} {key[2]}: '
              f'{a.rsplit("/", 1)[-1]} → {b.rsplit("/", 1)[-1]}')
    for c, m in fails:
        print(f'  解析失败 {c}: {m}')
    print('（以上「值/单位/出处不同」默认都不会被改写，要改跑 --overwrite）')
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description='合并六家季度费率到 series/fee_rates.csv')
    ap.add_argument('--series', default=os.path.join(ROOT, 'series'))
    ap.add_argument('--cache', default=os.path.join(ROOT, 'cache'))
    ap.add_argument('--overwrite', action='store_true',
                    help='连已有行的 value/unit/source_url 一起刷新（默认不覆盖）')
    ap.add_argument('--check', action='store_true', help='只对账不写盘')
    a = ap.parse_args()

    if a.check:
        return _check(a.series, a.cache)

    for c, p in sorted(latest_periods(a.cache).items()):
        print(f'  {c:5} 最新 {p}')
    print(f'全表有效期 latest_period = {latest_period(a.cache)}')

    added = update(a.series, a.cache, overwrite=a.overwrite)
    print(f'新增/更新 {len(added)} 个 (company, period)')
    for c, p in added:
        print(f'  {c} {p}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
