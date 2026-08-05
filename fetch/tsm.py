# -*- coding: utf-8 -*-
"""TSMC (2330.TW) 月度营收 —— 无人值守抓取模块。

对应 build/build_tsm.py，维护三个序列文件中的两个：

  series/tsm.csv        month, revenue_ntd_mn, yoy_pct      ← 本模块自动维护
  series/tsm_fx.csv     month, ntd_per_usd                  ← 本模块自动维护
  series/tsm_guidance.csv                                   ← 本模块**不碰**，见下文「口径坑 5」

────────────────────────────────────────────────────────────────────────
数据源
────────────────────────────────────────────────────────────────────────
1) 营收（tsm.csv）
   落地页 https://investor.tsmc.com/english/monthly-revenue
   页面上挂着一份官方 xlsx，文件名每月变（.../encrypt_file/mr/Historical_Monthly_Revenue_<Month>_<n>.xlsx），
   所以 URL **必须每次从落地页 HTML 里现抓**，不能写死 —— 写死的那一刻就注定了下个月 404。
   xlsx 的 "Consolidated" sheet 是「年 × 12 月」的矩阵，单位 NT$mn，与 build 脚本口径一致。

   为什么用 xlsx 而不是页面上那张 HTML 表：页面表只有「当年」12 个月，
   而算 yoy 需要去年同月；xlsx 一份文件就带全 2006-04 至今的完整历史，
   既能算 yoy，又能对账历史、又能在序列断档多个月时一次补齐。

2) 汇率（tsm_fx.csv）
   build 脚本注释写的是 FRED 的 EXTAUS。**FRED 在本机（含 cron 环境）连不通**：
   fred.stlouisfed.org 的 fredgraph.csv 在 curl 和 urllib 下都是静默超时（不是 403，是连接层挂死），
   所以不能作为无人值守源。
   改用 EXTAUS 的**上游原始数据**：美联储 H.10 台湾地区历史日度牌价
   https://www.federalreserve.gov/releases/h10/hist/dat00_ta.htm
   EXTAUS 的定义就是「该月所有营业日 H.10 牌价的算术平均」，本模块按同一定义重算。
   实测 2016-01 ~ 2026-07 共 127 个月，重算值与现有 tsm_fx.csv 最大偏差 4.8e-05
   （纯 4 位小数舍入残差），可以认定口径完全一致。

3) 交叉校验源（只读不写）
   台湾证交所 OpenAPI https://openapi.twse.com.tw/v1/opendata/t187ap05_L
   「每月营业收入汇总表」，全市场当期一份 JSON，单位是**新台币千元**。
   只有最新一期、没有历史，所以只拿来验证「官方最新月是哪个月 + 金额对不对」。
   MOPS 公开资讯观测站是同一份数据的网页版，需要 POST + 会话，无人值守下不如 OpenAPI 干净，故不用。

────────────────────────────────────────────────────────────────────────
发布节奏
────────────────────────────────────────────────────────────────────────
· 台湾《证券交易法》要求上市公司于**次月 10 日前**公告上月营收。
  TSMC 惯例是 10 日当天（遇假日提前）盘后发布，同日更新 IR 页与 xlsx。
  → 调度建议：每月 10-14 日每天跑一次；10 日之前跑必然拿到上个月的旧数，不是故障。
· 美联储 H.10 每周一更新（含上周日度值），月度平均在次月第 1 个营业日即可算全，
  所以汇率永远不会拖累营收：营收 M 月的数在 M+1 月 10 日才有，那时 M 月汇率早已齐。
· TWSE OpenAPI 的「资料年月」是 ROC 年 + 月（11506 = 2026-06），换算要 +1911。

────────────────────────────────────────────────────────────────────────
口径坑（踩过的，别再踩）
────────────────────────────────────────────────────────────────────────
1. **investor.tsmc.com 有 WAF，认 UA 指纹**：curl 带浏览器 UA 也一律 403，
   Python urllib 带同样的 UA 反而 200。所以本模块统一走 urllib，不要「顺手改成 requests/curl」。
   （requests 未验证；改之前先自己跑一次。）
2. **xlsx 有两个 sheet**：Unconsolidated（1999-2012，单体）和 Consolidated（2006-04 起，合并）。
   2013 起 TIFRS 只披露合并数，build 脚本用的是合并数。写死读 "Consolidated"，
   不要用 wb.worksheets[0] —— 那是单体表，2013 年以后全空。
3. **yoy_pct 是「用 NT$mn 整数重算再四舍五入到 1 位」**，不是官方公告里的百分比。
   官方是拿千元精度算的（如 2026-06 官方 67.86685%，用 mn 算是 67.8672%），
   两者到小数点后 1 位都是 67.9，实测 2016-01~2026-06 共 126 个月零分歧。
   但这是巧合不是保证 —— 若某月两者在第 1 位小数上劈叉，以 xlsx（mn 口径）为准，保持序列内部自洽。
4. **xlsx 早期年份带小数**（2007/2008 行是浮点），2013 年以后都是整数。
   写 CSV 时按 build 脚本的既有格式落整数，早期年份不在 series 范围内（series 从 2016-01 起），不受影响。
5. **tsm_guidance.csv 本模块不写**。它的 actual_rev_usdbn = 当季三个月 NT$ 合计 / 公司自己在
   季报里披露的当季汇率，而**那个汇率不等于三个月月均汇率的简单平均**：
   2025Q2 公司口径 31.054 vs 月均简单平均 30.8295，折出来 30.07 vs 30.29，差 0.7%。
   也就是说，拿月度数据去「自动补」季度指引表会系统性写错，且错得不显眼。
   → 季度指引 + 实际值维持人工从季报新闻稿录入，每季一次。update() 只在发现该文件落后于
      已完结季度时打印提醒，绝不代笔。
6. **重述**：TSMC 极少重述月营收，但 xlsx 是全量覆盖式文件，一旦上游改数，
   本模块会检测到与已入库值不一致并**抛异常**，而不是悄悄改写或追加 —— 由人来判断是口径变更还是解析出错。
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request

# ── 常量 ────────────────────────────────────────────────────────────────
IR_PAGE = 'https://investor.tsmc.com/english/monthly-revenue'
IR_ORIGIN = 'https://investor.tsmc.com'
H10_TAIWAN = 'https://www.federalreserve.gov/releases/h10/hist/dat00_ta.htm'
TWSE_API = 'https://openapi.twse.com.tw/v1/opendata/t187ap05_L'
TWSE_CODE = '2330'

# WAF 认这个；见口径坑 1
_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
_HEADERS = {'User-Agent': _UA, 'Accept-Language': 'en-US,en;q=0.9'}

REV_CSV = 'tsm.csv'
FX_CSV = 'tsm_fx.csv'
GUIDANCE_CSV = 'tsm_guidance.csv'

SERIES_START = '2016-01'          # build 脚本的历史起点，早于此不入库

# 对账容差：营收是整数应当完全相等；yoy 允许 1 位小数的舍入方向差；汇率 4 位小数
TOL_REV = 0.51
TOL_YOY = 0.051
TOL_FX = 5e-4


# ── 底层 IO ─────────────────────────────────────────────────────────────
def _ssl_ctx():
    # 某些 cron 环境下证书链不全，且这些源都是公开只读数据、无凭证，
    # 校验失败时宁可拿到数据也不要静默停摆。
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _get(url, timeout=90, referer=None, tries=4):
    """带退避重试的 GET。

    investor.tsmc.com 的 WAF 有**突发速率限制**：短时间内连打两次同一页，
    第二次直接 403（不是永久封，隔几秒就恢复）。无人值守下必须自己扛掉这个抖动，
    否则「先 latest_month() 再 update()」这种最自然的调用序列必然随机失败。
    """
    h = dict(_HEADERS)
    if referer:
        h['Referer'] = referer
    last = None
    for i in range(tries):
        if i:
            time.sleep(3 * (3 ** (i - 1)))          # 3s / 9s / 27s
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (403, 429, 500, 502, 503, 504):
                raise                                # 404 之类是真错，别浪费时间重试
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
    raise RuntimeError('GET %s 连续 %d 次失败，最后一次：%r' % (url, tries, last))


def _cache_write(cache_dir, name, data):
    os.makedirs(cache_dir, exist_ok=True)
    p = os.path.join(cache_dir, name)
    mode = 'wb' if isinstance(data, (bytes, bytearray)) else 'w'
    with open(p, mode) as f:
        f.write(data)
    return p


def _mkey(y, m):
    return '%04d-%02d' % (y, m)


# ── 源 1：TSMC 官方 xlsx ────────────────────────────────────────────────
def _discover_xlsx_url(cache_dir):
    """从 IR 落地页现抓 xlsx 链接。文件名每月变，写死必死（见模块头）。"""
    html = _get(IR_PAGE).decode('utf-8', 'replace')
    _cache_write(cache_dir, 'tsm_ir_monthly_revenue.html', html)
    m = re.search(r'href="([^"]*encrypt_file/mr/[^"]*\.xlsx)"', html, re.I)
    if not m:
        raise RuntimeError(
            'TSMC IR 页面上找不到 Historical Monthly Revenue 的 xlsx 链接；'
            '页面改版或被 WAF 挡了。缓存已落 %s' % os.path.join(cache_dir, 'tsm_ir_monthly_revenue.html'))
    href = m.group(1)
    return href if href.startswith('http') else IR_ORIGIN + href


def _parse_xlsx(path):
    """解析 Consolidated sheet → {'YYYY-MM': NT$mn(float)}。"""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    if 'Consolidated' not in wb.sheetnames:
        # 见口径坑 2：绝不退化成「拿第一个 sheet」
        raise RuntimeError('xlsx 里没有 Consolidated sheet，实际 sheet=%s' % wb.sheetnames)
    ws = wb['Consolidated']
    out = {}
    for row in ws.iter_rows(values_only=True):
        y = row[0]
        if not isinstance(y, int) or not (1990 < y < 2100):
            continue
        for i in range(1, 13):                      # 第 1..12 列 = Jan..Dec，第 13 列是 Total，不要
            v = row[i]
            if v is None or v == '':
                continue
            out[_mkey(y, i)] = float(v)
    if not out:
        raise RuntimeError('Consolidated sheet 解析出 0 行，版式可能变了：%s' % path)
    return out


def fetch_revenue(cache_dir):
    """下载并解析官方 xlsx，返回 {'YYYY-MM': NT$mn}（全历史，未裁剪）。"""
    url = _discover_xlsx_url(cache_dir)
    blob = _get(url, referer=IR_PAGE)
    if not blob[:2] == b'PK':                       # xlsx 是 zip；拿到 HTML 说明被挡了
        raise RuntimeError('从 %s 下下来的不是 xlsx（前 2 字节 %r），大概率是 WAF 拦截页' % (url, blob[:2]))
    p = _cache_write(cache_dir, 'tsm_historical_monthly_revenue.xlsx', blob)
    return _parse_xlsx(p), url


def _with_yoy(rev, months):
    """给定月份列表算 yoy。缺去年同月 → 抛异常，绝不写 NaN。"""
    rows = []
    for m in months:
        y, mo = int(m[:4]), int(m[5:])
        prev = rev.get(_mkey(y - 1, mo))
        if prev is None or prev == 0:
            raise ValueError('月份 %s 缺去年同月(%s)基数，无法算 yoy_pct；拒绝写入残缺行' % (m, _mkey(y - 1, mo)))
        rows.append((m, int(round(rev[m])), round((rev[m] / prev - 1) * 100, 1)))
    return rows


# ── 源 2：美联储 H.10 台湾日度牌价 → 月均 ────────────────────────────────
def fetch_fx(cache_dir):
    """返回 {'YYYY-MM': (月均汇率, 该月计入的营业日天数)}。"""
    html = _get(H10_TAIWAN, timeout=120).decode('utf-8', 'replace')
    _cache_write(cache_dir, 'tsm_h10_taiwan.htm', html)
    buckets = {}
    for tr in re.findall(r'<tr.*?</tr>', html, re.S | re.I):
        cells = [re.sub(r'<[^>]+>', '', c).replace('&nbsp;', ' ').strip()
                 for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S | re.I)]
        if len(cells) < 2 or not re.match(r'^\d{1,2}-[A-Za-z]{3}-\d{2}$', cells[0]):
            continue
        d = _dt.datetime.strptime(cells[0].upper(), '%d-%b-%y')
        v = cells[1].replace(',', '')
        if v.upper() in ('ND', 'NA', 'N/A', ''):    # 美方假日/停牌，H.10 写 ND；跳过不当 0
            continue
        buckets.setdefault(_mkey(d.year, d.month), []).append(float(v))
    if not buckets:
        raise RuntimeError('H.10 台湾页面解析出 0 条日度牌价，版式变了或被 Cloudflare 挡了')
    return {k: (sum(v) / len(v), len(v)) for k, v in buckets.items()}


# ── 源 3：TWSE OpenAPI，仅交叉校验 ──────────────────────────────────────
def _twse_check(cache_dir):
    """返回 (最新月 'YYYY-MM', 当月营收 NT$mn) 或 None（拿不到就算了，不阻塞主流程）。"""
    try:
        blob = _get(TWSE_API, timeout=90)
        _cache_write(cache_dir, 'tsm_twse_t187ap05_L.json', blob)
        for r in json.loads(blob):
            if r.get('公司代號') == TWSE_CODE:
                roc = str(r['資料年月'])                       # 11506 → 2026-06
                y = int(roc[:-2]) + 1911
                mo = int(roc[-2:])
                # OpenAPI 单位是新台币千元
                return _mkey(y, mo), float(r['營業收入-當月營收']) / 1000.0
    except Exception:
        return None
    return None


# ── CSV 读写 ────────────────────────────────────────────────────────────
def _read_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        rd = csv.DictReader(f)
        return rd.fieldnames, list(rd)


def _line_terminator(path):
    """series/*.csv 是 CRLF 落盘的。追加时若用 '\\n'，文件会变成半 CRLF 半 LF，
    git diff 会把整份文件标成改动，把「本月新增 1 行」淹掉。所以照抄既有行尾。"""
    with open(path, 'rb') as f:
        head = f.read(4096)
    return '\r\n' if b'\r\n' in head else '\n'


def _append_rows(path, fieldnames, rows):
    """只追加，不重写既有行。保持文件原有列名/列序/行尾。"""
    term = _line_terminator(path)
    with open(path, 'rb') as f:                      # 末行没有换行符时先补一个，否则会粘行
        f.seek(0, os.SEEK_END)
        n = f.tell()
        f.seek(max(0, n - 2))
        tail = f.read()
    with open(path, 'a', newline='', encoding='utf-8') as f:
        if n and not tail.endswith(b'\n'):
            f.write(term)
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator=term)
        for r in rows:
            w.writerow(r)


# ── 公开接口 ────────────────────────────────────────────────────────────
def latest_month(cache_dir):
    """官方源当前最新已公告月，'YYYY-MM'。抓不到抛异常。

    以 TSMC 官方 xlsx 为准（它就是 series 的真值来源）；
    TWSE OpenAPI 只做交叉校验，不一致时打印告警但不改变返回值 ——
    两边发布有几十分钟到几小时的时差，硬对齐反而会制造假故障。
    """
    rev, _ = fetch_revenue(cache_dir)
    latest = max(rev)
    chk = _twse_check(cache_dir)
    if chk:
        tm, tv = chk
        if tm != latest:
            print('[warn] TWSE OpenAPI 最新月 %s ≠ TSMC xlsx 最新月 %s（发布时差，通常几小时内收敛）' % (tm, latest))
        elif abs(tv - rev[latest]) > 1.0:
            print('[warn] %s 金额分歧：TWSE %.0f vs xlsx %.0f (NT$mn)' % (latest, tv, rev[latest]))
    return latest


def update(series_dir, cache_dir):
    """把新月份写进 series/tsm.csv 与 series/tsm_fx.csv，返回新增月份列表（两文件并集，已排序）。

    幂等：已有月份一律不重复追加。
    任何一列解析不出来（如缺去年同月基数、缺当月汇率）→ 抛异常，绝不写 NaN。
    发现上游重述（已入库月份的值对不上）→ 抛异常，交人判断。
    """
    rev_path = os.path.join(series_dir, REV_CSV)
    fx_path = os.path.join(series_dir, FX_CSV)

    rev_src, xlsx_url = fetch_revenue(cache_dir)
    fx_src = fetch_fx(cache_dir)

    # ── 营收 ──
    rev_fields, rev_rows = _read_csv(rev_path)
    have_rev = {r['month'] for r in rev_rows}
    for r in rev_rows:                                   # 重述检测
        m = r['month']
        if m in rev_src:
            if abs(rev_src[m] - float(r['revenue_ntd_mn'])) > TOL_REV:
                raise ValueError('上游重述：%s 官方 %.0f vs 已入库 %s (NT$mn)。'
                                 '本模块拒绝改写既有行，请人工确认后再决定。'
                                 % (m, rev_src[m], r['revenue_ntd_mn']))

    new_rev_months = sorted(m for m in rev_src if m >= SERIES_START and m not in have_rev)
    new_rev_rows = [{'month': m, 'revenue_ntd_mn': v, 'yoy_pct': y}
                    for m, v, y in _with_yoy(rev_src, new_rev_months)]

    # ── 汇率 ──
    fx_fields, fx_rows = _read_csv(fx_path)
    have_fx = {r['month'] for r in fx_rows}
    for r in fx_rows:
        m = r['month']
        if m in fx_src and abs(fx_src[m][0] - float(r['ntd_per_usd'])) > TOL_FX:
            raise ValueError('汇率重述/口径漂移：%s 重算 %.4f vs 已入库 %s'
                             % (m, fx_src[m][0], r['ntd_per_usd']))

    # 只收「已经走完」的月份：当月还没结束时月均是半截数，写进去下次就得改
    today = _dt.date.today()
    cur = _mkey(today.year, today.month)
    new_fx_months = sorted(m for m in fx_src
                           if m >= SERIES_START and m not in have_fx and m < cur)
    # H.10 一个月至少有 15 个营业日；明显偏少说明该月数据还没灌全
    for m in new_fx_months:
        if fx_src[m][1] < 15:
            raise ValueError('H.10 %s 只有 %d 个日度观测，月均不可信，本次不写入'
                             % (m, fx_src[m][1]))
    new_fx_rows = [{'month': m, 'ntd_per_usd': '%.4f' % fx_src[m][0]} for m in new_fx_months]

    # ── 一致性闸门：build 脚本要用汇率折美元，营收月必须都有汇率 ──
    all_rev = have_rev | set(new_rev_months)
    all_fx = have_fx | set(new_fx_months)
    missing = sorted(all_rev - all_fx)
    if missing:
        raise ValueError('这些月份有营收但没有汇率，写进去会让 build_tsm.py 折出 NaN：%s' % missing)

    if new_rev_rows:
        _append_rows(rev_path, rev_fields, new_rev_rows)
    if new_fx_rows:
        _append_rows(fx_path, fx_fields, new_fx_rows)

    _guidance_reminder(series_dir, max(all_rev))

    print('[tsm] xlsx=%s' % xlsx_url)
    print('[tsm] tsm.csv +%d %s | tsm_fx.csv +%d %s'
          % (len(new_rev_rows), new_rev_months, len(new_fx_rows), new_fx_months))
    return sorted(set(new_rev_months) | set(new_fx_months))


def _guidance_reminder(series_dir, latest_rev_month):
    """季度指引表只能人工录（见口径坑 5），这里只提醒，不代笔。"""
    p = os.path.join(series_dir, GUIDANCE_CSV)
    if not os.path.exists(p):
        return
    try:
        _, rows = _read_csv(p)
        y, mo = int(latest_rev_month[:4]), int(latest_rev_month[5:])
        curq = '%dQ%d' % (y, (mo - 1) // 3 + 1)
        have = {r['quarter'] for r in rows}
        blank_actual = [r['quarter'] for r in rows
                        if not (r.get('actual_rev_usdbn') or '').strip() and r['quarter'] < curq]
        if curq not in have:
            print('[tsm][人工] tsm_guidance.csv 缺 %s 的指引区间，需从季报新闻稿录入' % curq)
        if blank_actual:
            print('[tsm][人工] tsm_guidance.csv 这些已完结季度还没填 actual：%s'
                  '（actual_fx 必须用公司季报披露的汇率，不能拿月均汇率凑）' % blank_actual)
    except Exception as e:
        print('[tsm][warn] 指引表检查失败（不影响月度更新）：%s' % e)


if __name__ == '__main__':
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sd = os.path.join(root, 'series')
    cd = os.path.join(root, 'cache')
    if len(sys.argv) > 1 and sys.argv[1] == 'latest':
        print(latest_month(cd))
    else:
        print(update(sd, cd))
