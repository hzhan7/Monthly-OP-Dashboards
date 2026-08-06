# -*- coding: utf-8 -*-
"""CME Group (CME) 月度成交量抓取 —— series/cme.csv 的无人值守更新器。

────────────────────────────────────────────────────────────────────────────
源
────────────────────────────────────────────────────────────────────────────
  https://cmegroupinc.gcs-web.com/monthly-volume

  这个地址**本身就是 xlsx**（Content-Type: application/vnd.openxml…sheet），
  不是一个还要再解析出下载链接的落地页。之所以特意写死这个「无扩展名」的路径，
  是因为它是 IR 站上的**稳定别名**：每月发布时后端把它指向新文件，URL 不变，
  真实文件名只在 Content-Disposition 里给出（如
  `cme_group_adv-rpc-oi_trend_Jul26 incl cash markets.xlsx`）。
  所以千万不要去猜带月份的文件名直链 —— 那种链接每月都变，猜错就是 404，
  而这个别名永远指向最新一期。文件名里的月份反过来可以当作「官方最新月」的
  旁证，但真值仍以表内数据为准（见 latest_month 的实现）。

  站点走 Akamai，但**没有** JS challenge / 验证码：普通 urllib + 常规 UA
  即可直取，无需浏览器登录态。因此本模块可无人值守运行。

────────────────────────────────────────────────────────────────────────────
发布节奏
────────────────────────────────────────────────────────────────────────────
  次月第 1-2 个工作日随月度成交量新闻稿一起更新（2026-07 数据的文件
  Last-Modified 为 2026-08-03，即次月第 1 个工作日）。
  建议调度：每月 3 日起每天跑一次，直到 latest_month() 前进为止。

  **工作簿里没有自述发布日**（找过：'Latest Month Summary' 的表头只写
  "Summary as of July 2026" —— 那是数据月；全部 1,936 条 sharedStrings 里唯一的
  完整日期是 "As of September 19, 2022, daily totals exclude Event Contracts" 这条
  口径脚注；批注、docProps/custom.xml 也都没有）。Cboe 那种 "Updated on August 5, 2026"
  在 CME 这里不存在，别再找了。所以发布日只能取上面那个 Last-Modified，
  再拿工作簿自己的保存时间戳对齐 —— 细节见 _publish_date()。

────────────────────────────────────────────────────────────────────────────
口径坑（这些是踩过才知道的，不要「优化」掉）
────────────────────────────────────────────────────────────────────────────
1. **ADV 与 OI 是两组完全不同的口径，不能互相推导。**
   ADV = 当月日均成交合约数（千张，已按交易日数归一），是「流量」；
   OI  = 月末未平仓合约数（张，绝对数不是千张），是「存量」。
   两者在 xlsx 里放在不同 sheet，单位差 1000 倍。build_cme.py 里
   `oi_total_contracts / 1e6` 而 `adv_total_kcontracts / 1000`，就是这个原因。

2. **月度总成交量必须自己乘交易日数，xlsx 不直接给。**
   官方只给 ADV，总量 = ADV x trading_days。Barclays 那套 day-count 调整
   之所以有意义，就是因为总量口径会被交易日数放大/掩盖真实趋势。
   trading_days 行在 'F&O ADV-RPC' 每个年份块的顶部，**没有自己的日期表头**，
   它借用同块下方 ADV 段的列位置 —— 所以解析时必须先缓存这一行，
   等拿到 ADV 段的列→月份映射之后再回填对齐，不能按固定列号硬编。

3. **资产类别 ADV 要取 'Average Daily Volume by Asset Class' 段，
   不要取 venue 段的分类小计。**
   同一 sheet 的 'F&O Asset Class ADV by Venue' 里也有 "Total Equities"，
   但那是三个 venue 四舍五入后再相加，与官方公布的分类 ADV 差 1-3 千张
   （例：2026-01 Equities 官方 7287，venue 加总 7290）。series/cme.csv
   历史上取的是前者，混用会在图上留下毛刺。

4. **ClearPort 自 2014 年起被并入 'Privately Negotiated'，官方不再单列。**
   xlsx 里 2013 及以前的年份块 venue 段有 'ClearPort' 行，2014 起整行消失。
   所以 adv_clearport_kcontracts 只有 2008-01..2013-12 有值，之后**天然为空**
   —— 这是唯一允许缺失的列，不算解析失败。别把它塞进必填校验，
   也别用 0 去填（0 会被图当成「ClearPort 归零」而不是「不再披露」）。

5. **日期表头里的「日」是脏的，只有年月可信。**
   2026 年块表头是 2026-01-01、2026-02-01…，但 2025 年块是 2025-01-20、
   2025-02-20…，2013 年块是 2013-01-01、2013-02-11…。日号是排版残留，
   解析一律只取 (year, month)。

6. **年份块的行距不是固定的**（2008-2013 有 ClearPort 行，行数多；
   2008 的 rolling 段整段为空）。所以只能靠段落标题文本扫描定位，
   不能假设「每年 N 行」按 stride 跳。

7. **官方会重述前月。** xlsx 里 2026-05 起的数值带三位小数（如 33205.291），
   而更早的月份是整数 —— CME 换过精度口径，且偶尔回改历史月。本模块的
   update() 只**追加**新月份，不改写已有行；若怀疑重述，用 verify() 对账
   后人工决定是否覆盖。

8. **venue 段的数字不能照抄，必须和分类 ADV 合计交叉验。**
   官方 xlsx 自己有错格：2021-04 的整个 venue 列被填成了「滚动 3 个月」的值
   （Globex 19485 + Pit 695 + PN 659 = 20839，而当月分类 ADV 合计只有 16484
   —— 20839 恰好是 Feb21-Apr21 的滚动合计）。series/cme.csv 里 2021-04 的
   三个 venue 列是空的，就是前人踩过这个坑手工剔掉的。
   本模块用 VENUE_TOL_REL 自动拦截：venue 分项之和与分类合计相对偏差超阈值
   就把该月 venue 置空（而不是让整月作废 —— 分类 ADV 和 OI 仍然是好的）。
   注意 2011-05 是另一种情形：官方「Total Venue」格写错了，但分项是对的，
   偏差 0.58%，在容忍范围内，照收。

────────────────────────────────────────────────────────────────────────────
接口
────────────────────────────────────────────────────────────────────────────
  latest_month(cache_dir) -> "YYYY-MM"      官方源当前最新完整月；抓不到抛异常
  update(series_dir, cache_dir) -> [str]    追加新月份，返回新增月份列表（幂等）
  verify(series_dir, cache_dir, n=3)        对账：重算最后 n 个月并逐列比对
"""
from __future__ import annotations

import datetime as _dt
import email.utils
import os
import re
import urllib.request
import zipfile
from zoneinfo import ZoneInfo

import pandas as pd

# ── 源与落盘 ────────────────────────────────────────────────────────────────
SRC_URL = 'https://cmegroupinc.gcs-web.com/monthly-volume'
CACHE_NAME = 'cme_monthly_volume.xlsx'

# 常规桌面 UA。Akamai 对默认的 Python-urllib UA 不友好，换成浏览器 UA 即可，
# 不需要 cookie / referer / 登录态。
_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36')

SHEET_ADV = 'F&O ADV-RPC'
SHEET_OI = 'F&O OI by Asset Class'

# 发布是 CME 的动作，「哪天发的」要按 CME 自己的日历算。实测两条时间证据都落在
# 芝加哥时间下午（2026-08-03 16:47 / 15:53 CDT），此刻按 UTC 取日期碰巧也对，
# 但只要哪期晚发两小时就会跨过 UTC 零点 —— 那时错的是日期本身，而且毫无迹象。
_TZ = ZoneInfo('America/Chicago')

# xlsx 行标签 → series/cme.csv 列名。
# 注意 xlsx 用 'Equities'，CSV 列名用 equity；'Pit' 对应 openoutcry。
_CLASS_MAP = {
    'interest rates': 'rates',
    'equities': 'equity',
    'energy': 'energy',
    'fx': 'fx',
    'agricultural': 'ag',
    'metals': 'metals',
    'total': 'total',
}
_VENUE_MAP = {
    'globex': 'adv_globex_electronic_kcontracts',
    'pit': 'adv_openoutcry_kcontracts',
    'privately negotiated': 'adv_privately_negotiated_kcontracts',
    'clearport': 'adv_clearport_kcontracts',
}

# series/cme.csv 的列顺序（不许改；build_cme.py 按名取用）
COLUMNS = [
    'month',
    'adv_total_kcontracts', 'adv_rates_kcontracts', 'adv_equity_kcontracts',
    'adv_energy_kcontracts', 'adv_ag_kcontracts', 'adv_fx_kcontracts',
    'adv_metals_kcontracts',
    'adv_globex_electronic_kcontracts', 'adv_openoutcry_kcontracts',
    'adv_privately_negotiated_kcontracts', 'adv_clearport_kcontracts',
    'oi_total_contracts', 'oi_rates_contracts', 'oi_equity_contracts',
    'oi_energy_contracts', 'oi_ag_contracts', 'oi_fx_contracts',
    'oi_metals_contracts',
    'trading_days',
]
# 坑 4：ClearPort 2014 起停止披露，是唯一天然允许为空的列。
OPTIONAL = {'adv_clearport_kcontracts'}

VENUE_COLS = [
    'adv_globex_electronic_kcontracts', 'adv_openoutcry_kcontracts',
    'adv_privately_negotiated_kcontracts', 'adv_clearport_kcontracts',
]
# CORE = 决定「这个月到底有没有数」的列。venue 单独判（见坑 8）。
CORE_REQUIRED = [c for c in COLUMNS
                 if c != 'month' and c not in OPTIONAL and c not in VENUE_COLS]
REQUIRED = [c for c in COLUMNS if c != 'month' and c not in OPTIONAL]

# 坑 8 的阈值：venue 三/四项之和 vs 分类 ADV 合计的相对偏差容忍度。
# 实测全 223 个月里，120 个月完全相等，次差是 2011-05 的 0.58%（官方
# 「Total Venue」格自己写错、但分项是对的，series/cme.csv 历史上采纳了分项），
# 最差是 2021-04 的 26.4%（整列被污染，必须丢弃）。2% 卡在两者之间。
VENUE_TOL_REL = 0.02


class FetchError(RuntimeError):
    """源不可达 / 结构变了 / 数据不完整 —— 一律显式抛，绝不静默写 NaN。"""


# ── 下载 ────────────────────────────────────────────────────────────────────
def download(cache_dir, max_age_hours=6.0):
    """把最新 xlsx 抓到 cache_dir，返回 (路径, 官方文件名)。

    带 max_age_hours 是为了让同一次调度里 latest_month() + update() + verify()
    共用一份文件 —— 否则三次下载可能跨越官方发布瞬间，拿到不一致的两份数据。
    """
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, CACHE_NAME)
    meta = path + '.name'
    lm_meta = path + '.lastmod'

    # 缓存命中还额外要求 .lastmod 在：它是发布日的证据（见 _publish_date），
    # 和 xlsx 本体来自同一个响应。缺了它就重下一次 —— 否则命中缓存的那几次跑
    # 取不到发布日，页面抬头那半句会时有时无，而这种「有时对」最难被发现。
    if os.path.exists(path) and max_age_hours is not None and os.path.exists(lm_meta):
        age = (_dt.datetime.now().timestamp() - os.path.getmtime(path)) / 3600.0
        if age < max_age_hours:
            name = ''
            if os.path.exists(meta):
                with open(meta, encoding='utf-8') as f:
                    name = f.read().strip()
            return path, name

    req = urllib.request.Request(SRC_URL, headers={
        'User-Agent': _UA,
        'Accept': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,'
                   'application/vnd.ms-excel,*/*'),
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            ctype = (r.headers.get('Content-Type') or '').lower()
            disp = r.headers.get('Content-Disposition') or ''
            lastmod = r.headers.get('Last-Modified') or ''
            blob = r.read()
    except Exception as e:                                    # noqa: BLE001
        raise FetchError(f'CME IR xlsx 下载失败: {SRC_URL} -> {e!r}') from e

    # 站点没挂验证码，但万一哪天挂了，返回的会是 HTML challenge 页而不是 xlsx。
    # 用魔数判定（xlsx 是 zip，PK\x03\x04）比看 Content-Type 更硬。
    if not blob.startswith(b'PK\x03\x04'):
        head = blob[:200].decode('utf-8', 'replace')
        raise FetchError(
            f'返回的不是 xlsx（Content-Type={ctype}）。很可能源站加了拦截页。'
            f' 开头 200 字节: {head!r}')

    name = ''
    m = re.search(r'filename="?([^";]+)"?', disp)
    if m:
        name = m.group(1).strip()

    with open(path, 'wb') as f:
        f.write(blob)
    with open(meta, 'w', encoding='utf-8') as f:
        f.write(name)
    # 原样存这一行响应头（不是解析后的日期）：日后有人怀疑某个发布日，
    # 要能拿到源头当时说的原话，而不是我们转述的结果。
    with open(lm_meta, 'w', encoding='utf-8') as f:
        f.write(lastmod)
    return path, name


# ── 解析 ────────────────────────────────────────────────────────────────────
def _is_date(v):
    return isinstance(v, _dt.datetime) or isinstance(v, _dt.date)


def _mkey(v):
    """坑 5：日期表头里的「日」是排版残留，只取年月。"""
    return f'{v.year:04d}-{v.month:02d}'


def _num(v):
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(',', '').strip())
    except ValueError:
        return None


def _colmap(row):
    """从表头行取 {列下标: 'YYYY-MM'}。"""
    return {i: _mkey(v) for i, v in enumerate(row) if _is_date(v)}


def _parse_adv(ws):
    """解析 'F&O ADV-RPC'：交易日数 + 分类 ADV + 分 venue ADV。

    坑 6：年份块行距不固定，只能顺序扫段落标题，不能按 stride 跳。
    坑 3：只认 'by Asset Class' 段，'Rolling 3 Month' 段（滚动均值/RPC）必须跳过。
    """
    out = {}
    section = None          # 'class' | 'venue' | None(=跳过)
    cmap = None
    pending_days = None     # 坑 2：Trading Days 行先于表头出现，暂存后回填

    for row in ws.iter_rows(values_only=True):
        a = str(row[0]).strip() if row[0] is not None else ''
        b = str(row[1]).strip() if isinstance(row[1], str) else ''

        if a.lower() == 'trading days':
            pending_days = row
            continue

        if b:
            low = b.lower()
            if low.startswith('rolling'):
                section, cmap = None, None       # 滚动段：整段丢弃
            elif 'average daily volume by asset class' in low:
                section, cmap = 'class', None
            elif 'average daily volume by venue' in low:
                section, cmap = 'venue', None
            elif 'rate per contract' in low:
                section, cmap = None, None

        if section and cmap is None and _is_date(row[1]):
            cmap = _colmap(row)
            if not cmap:
                raise FetchError(f'{SHEET_ADV}: 段 {section} 的日期表头解析不出月份')
            if section == 'class' and pending_days is not None:
                for i, mk in cmap.items():
                    d = _num(pending_days[i]) if i < len(pending_days) else None
                    if d is not None:
                        out.setdefault(mk, {})['trading_days'] = d
                pending_days = None
            continue

        if not section or cmap is None or not a:
            continue

        key = a.lower()
        if section == 'class' and key in _CLASS_MAP:
            col = f'adv_{_CLASS_MAP[key]}_kcontracts'
        elif section == 'venue' and key in _VENUE_MAP:
            col = _VENUE_MAP[key]
        else:
            continue                              # 'Exchange-traded Total'/'Total Venue' 等小计行不入库

        for i, mk in cmap.items():
            v = _num(row[i]) if i < len(row) else None
            if v is not None:
                out.setdefault(mk, {})[col] = v

    if not out:
        raise FetchError(f'{SHEET_ADV}: 一行都没解析出来，sheet 结构可能改了')
    return out


def _parse_oi(ws):
    """解析 'F&O OI by Asset Class'：月末未平仓合约数（张，不是千张）。"""
    out = {}
    cmap = None
    for row in ws.iter_rows(values_only=True):
        if _is_date(row[1]):
            cmap = _colmap(row)
            continue
        if cmap is None or row[0] is None:
            continue
        key = str(row[0]).strip().lower()
        if key not in _CLASS_MAP:
            continue
        col = f'oi_{_CLASS_MAP[key]}_contracts'
        for i, mk in cmap.items():
            v = _num(row[i]) if i < len(row) else None
            if v is not None:
                out.setdefault(mk, {})[col] = v
    if not out:
        raise FetchError(f'{SHEET_OI}: 一行都没解析出来，sheet 结构可能改了')
    return out


def parse(xlsx_path):
    """xlsx -> DataFrame（index='YYYY-MM' 字符串，列同 series/cme.csv）。

    只保留 REQUIRED 全部齐备的月份 —— 当年剩余月份在表里是空列，
    OI 偶尔也会比 ADV 晚一天上线，半拉子月份一律不算「有」。
    """
    try:
        import openpyxl
    except ImportError as e:                       # noqa: BLE001
        raise FetchError('需要 openpyxl 才能解析 CME xlsx: pip install openpyxl') from e

    try:
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    except Exception as e:                         # noqa: BLE001
        # 缓存里躺着半截下载 / 拦截页时，openpyxl 会抛 BadZipFile 之类的底层异常。
        # 统一成 FetchError，调度器只需要 catch 一种。
        raise FetchError(f'打不开 {xlsx_path}（缓存损坏或不是 xlsx）: {e!r}') from e
    for sn in (SHEET_ADV, SHEET_OI):
        if sn not in wb.sheetnames:
            raise FetchError(f'xlsx 缺 sheet {sn!r}；现有: {wb.sheetnames}')

    rec = _parse_adv(wb[SHEET_ADV])
    for mk, d in _parse_oi(wb[SHEET_OI]).items():
        rec.setdefault(mk, {}).update(d)
    wb.close()

    df = pd.DataFrame.from_dict(rec, orient='index')
    for c in COLUMNS[1:]:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[COLUMNS[1:]].sort_index()
    df = df[df[CORE_REQUIRED].notna().all(axis=1)]

    # 坑 8：venue 段偶尔被官方写错，必须交叉验，不能照抄。
    vsum = df[VENUE_COLS].astype(float).sum(axis=1, min_count=1)
    tot = df['adv_total_kcontracts'].astype(float)
    bad = ((vsum - tot).abs() / tot.abs() > VENUE_TOL_REL) & vsum.notna()
    df.loc[bad, VENUE_COLS] = pd.NA
    df.attrs['venue_quarantined'] = list(df.index[bad])
    return df


# ── 发布日 ──────────────────────────────────────────────────────────────────
def _source_dates():
    """按路径加载仓库根的 source_dates.py（发布日台账）。

    不能裸 import：本模块被 monthly_run 用 spec_from_file_location 加载，
    那时 sys.path 上既没有 fetch/ 也没有仓库根。
    """
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(root, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _wb_saved_at(xlsx_path):
    """工作簿自己的保存时间戳 —— docProps/core.xml 的 dcterms:modified，原文与 UTC 时间。

    这是 CME 的人（core.xml 里 lastModifiedBy 那位）按下保存时 Excel 写进文件的，
    随文件走、和我们的下载行为无关，所以能当作独立于 HTTP 头的第二条证据。
    """
    try:
        with zipfile.ZipFile(xlsx_path) as z:
            core = z.read('docProps/core.xml').decode('utf-8', 'replace')
    except Exception:                                          # noqa: BLE001
        return None, None
    m = re.search(r'<dcterms:modified[^>]*>([^<]+)</dcterms:modified>', core)
    if not m:
        return None, None
    raw = m.group(1).strip()
    try:
        d = _dt.datetime.strptime(raw, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        return None, raw
    return d.replace(tzinfo=_dt.timezone.utc), raw


def _publish_date(cache_dir, xlsx_path, name):
    """这一期 xlsx 的发布日 ('YYYY-MM-DD', 出处文字)；判不准返回 (None, 原因)。

    工作簿里没有任何自述发布日（找过哪些地方见模块 docstring 的「发布节奏」节），
    所以退到本模块 docstring 从一开始就当作实测发布日的那个字段：HTTP Last-Modified。

    但单凭一个响应头不敢往页面上印 —— CDN 迁移、重新上传同一份文件都会把它推后，
    而推后之后它看上去和真发布日一模一样。所以要工作簿自己的保存时间戳来对齐：
    一条来自 CME 的 Excel、一条来自 IR 服务器，两条独立证据同一天才采信。
    实测 2026-07 那期是 20:53:17Z 保存、21:47:51Z 上线，差 54 分钟，同一天。
    对不上就返回 None 让抬头缺半句 —— 缺席远好过印一个看不出来是假的日期。
    """
    lm_meta = os.path.join(cache_dir, CACHE_NAME + '.lastmod')
    if not os.path.exists(lm_meta):
        return None, '没有 .lastmod 旁证文件（该文件由 download() 与 xlsx 一起落盘）'
    with open(lm_meta, encoding='utf-8') as f:
        lm_raw = f.read().strip()
    if not lm_raw:
        return None, '响应里没有 Last-Modified 头'
    try:
        http_at = email.utils.parsedate_to_datetime(lm_raw)
    except (TypeError, ValueError):
        return None, f'Last-Modified 读不懂: {lm_raw!r}'
    if http_at.tzinfo is None:                     # RFC 7231 要求带 GMT，缺了就按 UTC 读
        http_at = http_at.replace(tzinfo=_dt.timezone.utc)

    saved_at, saved_raw = _wb_saved_at(xlsx_path)
    if saved_at is None:
        return None, f'工作簿 docProps/core.xml 里取不到 dcterms:modified（原文 {saved_raw!r}）'

    d_http = http_at.astimezone(_TZ).date()
    d_saved = saved_at.astimezone(_TZ).date()
    if d_http != d_saved:
        return None, (f'两条证据不在同一天：Last-Modified {d_http}、'
                      f'工作簿保存 {d_saved}（芝加哥时间）')

    return d_http.strftime('%Y-%m-%d'), (
        f'{CACHE_NAME}（官方文件名 {name or "未给出"}）的 HTTP Last-Modified "{lm_raw}"，'
        f'与工作簿 docProps/core.xml 的 dcterms:modified {saved_raw} 互证，'
        f'换算到芝加哥时间同为 {d_http}')


def _name_month(name):
    """从官方文件名里的 'Jul26' 取出 'YYYY-MM'；认不出返回 None。

    只用来做发布日归属的校验（见 _record_publish_date），不参与取数 ——
    表内数据才是最新月的真值（见模块 docstring）。
    """
    m = re.search(r'_([A-Z][a-z]{2})(\d{2})(?![0-9])', name or '')
    if not m:
        return None
    try:
        mon = _dt.datetime.strptime(m.group(1), '%b').month
    except ValueError:
        return None
    return f'20{m.group(2)}-{mon:02d}'


def _record_publish_date(series_dir, cache_dir, xlsx_path, name, added, latest):
    """把这一期的发布日记进台账 —— 只记这个文件自己那一期（latest），且它确实刚落库。

    xlsx 是「一份文件滚动覆盖全历史」的形态：它的 Last-Modified 只证明**最新那个月**
    是这天发的。补历史时一次 update 可能追进好几个月，若给每个新月都盖上同一个日期，
    台账上就会长出「2026-05 的数据 2026-08-03 才发布」这种看着挺像真的假话 ——
    record() 的护栏只拦「发布日早于数据月」，拦不住晚三个月。

    再加一道文件名校验：官方文件名里的月份（Jul26）与表内最新完整月对不上时，
    说明这份文件已经是更新一期、而我们最新能收全的还是上一个月（例如 OI 晚上线），
    那么这个发布日属于文件里那个更新的月份，安到 latest 头上就是串月。
    """
    if latest not in added:
        return
    nm = _name_month(name)
    if nm and nm != latest:
        print(f'  发布日未记：官方文件名月份 {nm} 与表内最新完整月 {latest} 不一致')
        return
    day, evidence = _publish_date(cache_dir, xlsx_path, name)
    if not day:
        print(f'  发布日未记（{latest}）：{evidence}')
        return
    _source_dates().record(series_dir, 'cme', latest, day, evidence)


# ── 对外接口 ────────────────────────────────────────────────────────────────
def latest_month(cache_dir) -> str | None:
    """官方源当前最新完整月 "YYYY-MM"。抓不到 / 解析不出 -> 抛 FetchError。"""
    path, _ = download(cache_dir)
    df = parse(path)
    if df.empty:
        raise FetchError('xlsx 解析成功但没有任何完整月份')
    return str(df.index[-1])


def _read_series(series_dir):
    p = os.path.join(series_dir, 'cme.csv')
    if not os.path.exists(p):
        raise FetchError(f'找不到 {p}')
    cur = pd.read_csv(p, dtype={'month': str})
    if list(cur.columns) != COLUMNS:
        raise FetchError(f'series/cme.csv 列名与预期不符\n实际: {list(cur.columns)}')
    # series/cme.csv 现存是 CRLF。pandas 默认写 LF，会把整个文件变成 224 行全改的
    # git diff，把真正新增的那一两行埋掉 —— 所以沿用原文件的行尾，别硬编。
    with open(p, 'rb') as f:
        eol = '\r\n' if b'\r\n' in f.read(4096) else '\n'
    return p, cur, eol


def _fmt(v):
    """还原 CSV 现有的写法：整数不带 .0，其余用 Python 最短往返 repr。

    现存文件里同时有 `29581` 和 `35879.42523809524` 这两种形态，说明它当初就是
    「整数化 + float repr」写出来的。这里必须原样复刻 —— 若改用 f'{v:.6f}'
    之类的定长格式，新旧行的精度写法会不一致，且四舍五入会真的丢掉有效数字。
    """
    if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
        return ''
    f = float(v)
    if f.is_integer():
        return str(int(f))
    return repr(f)


def update(series_dir, cache_dir) -> list:
    """把官方源里比 series/cme.csv 更新的月份追加进去，返回新增月份列表。

    幂等：已有月份一概不动（含官方重述 —— 见坑 7，重述要人工确认后再覆盖）。
    任一必填列缺失就抛异常，绝不写 NaN。

    实现上刻意走**文本行级插入**而不是 pandas 读回再整表 to_csv：
    整表重写会把已有行的浮点精度按当前格式化规则重新渲染一遍
    （实测会把 35879.42523809524 写成 35879.425238），等于悄悄改了历史数据，
    而且 git diff 会变成整文件全改。行级插入保证已有行逐字节不动。
    """
    path, name = download(cache_dir)
    src = parse(path)
    csv_path, cur, eol = _read_series(series_dir)

    have = set(cur['month'].astype(str))
    new = [m for m in src.index if m not in have]
    if not new:
        return []

    quarantined = set(src.attrs.get('venue_quarantined', []))
    lines = []
    for m in new:
        r = src.loc[m]
        missing = [c for c in CORE_REQUIRED if pd.isna(r[c])]
        if missing:
            raise FetchError(f'{m}: 官方 xlsx 缺列 {missing}，拒绝写入（不写 NaN）')
        # venue 允许为空只有两种正当理由：ClearPort 已停披露（坑 4），
        # 或该月 venue 被一致性校验判为污染（坑 8）。其余情况说明解析出问题了。
        if m not in quarantined:
            vmiss = [c for c in VENUE_COLS
                     if c not in OPTIONAL and pd.isna(r[c])]
            if vmiss:
                raise FetchError(
                    f'{m}: venue 列 {vmiss} 缺失，且未被一致性校验标记为污染 —— '
                    f'多半是 {SHEET_ADV} 的 venue 段结构变了，拒绝写入')
        lines.append((m, ','.join([m] + [_fmt(r[c]) for c in COLUMNS[1:]])))

    with open(csv_path, 'r', encoding='utf-8', newline='') as f:
        raw = f.read()
    body = raw.split(eol)
    trailing = body.pop() if body and body[-1] == '' else None   # 末尾换行
    head, rest = body[0], body[1:]

    keyed = [(ln.split(',', 1)[0], ln) for ln in rest if ln]
    keyed.extend(lines)
    keyed.sort(key=lambda t: t[0])                    # 按 month 归位，稳定排序

    out = eol.join([head] + [ln for _, ln in keyed])
    if trailing is not None:
        out += eol
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        f.write(out)

    # 台账只在数据真的写进 series/cme.csv 之后才作证 —— 上面任何一步抛了，
    # 台账上就不该多出一行说「这个月官方发过了」。
    _record_publish_date(series_dir, cache_dir, path, name, set(new), str(src.index[-1]))
    return list(new)


def verify(series_dir, cache_dir, n=3):
    """对账：用本解析器重算 series/cme.csv 最后 n 个月，逐列比对。

    返回 [(month, column, csv值, 解析值, 相对偏差), ...]（只列不一致的）。
    对不上不代表解析错 —— 先看是不是官方重述（坑 7）。
    """
    path, _ = download(cache_dir)
    src = parse(path)
    _, cur, _eol = _read_series(series_dir)
    diffs = []
    for m in cur['month'].astype(str).tolist()[-n:]:
        if m not in src.index:
            diffs.append((m, '*', 'in csv', 'MISSING in xlsx', float('inf')))
            continue
        row = cur[cur['month'] == m].iloc[0]
        for c in COLUMNS[1:]:
            a, b = row[c], src.loc[m, c]
            if pd.isna(a) and pd.isna(b):
                continue
            if pd.isna(a) or pd.isna(b):
                diffs.append((m, c, a, b, float('inf')))
                continue
            a, b = float(a), float(b)
            if a == b:
                continue
            rel = abs(b - a) / abs(a) if a else float('inf')
            diffs.append((m, c, a, b, rel))
    return diffs


if __name__ == '__main__':
    import sys
    D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sd, cd = os.path.join(D, 'series'), os.path.join(D, 'cache')
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'latest'
    if cmd == 'latest':
        print(latest_month(cd))
    elif cmd == 'update':
        print('added:', update(sd, cd))
    elif cmd == 'verify':
        d = verify(sd, cd, int(sys.argv[2]) if len(sys.argv) > 2 else 3)
        print('MISMATCHES:', len(d))
        for x in d:
            print('  ', x)
