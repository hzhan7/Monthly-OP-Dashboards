# -*- coding: utf-8 -*-
"""东亚三家（JPX / SGX / HKEX）pool_product 篮子常数 —— 第二轮，走「方法①：官方直接发名义额」。

    python3 build/basefill/eastasia2.py              # 全流程（联网），写 part CSV
    python3 build/basefill/eastasia2.py --no-net     # 只用 cache/basefill/，不发请求

━━ 本轮结论一句话 ━━
    JPX ✅ 填出来了（8,818,555.107376 JPY/张）；SGX ❌ / HKEX ❌ 官方根本不发名义额，
    实测确认「方法①在这两家不存在」，不是抓取失败。

━━ 方法①在三家的实测结果 ━━
第一轮在 Eurex 上发现：官方月度统计同时给 Traded Contracts 与 Capital Volume EUR，
两者相除直接就是篮子常数（基期恰为 2019-01，成交量加权已内含）。本轮逐家验证：

  JPX   ✅ **有**。宽表 tv_ts{YYYYMM}.xls 每个产品同时给「取引高」与「取引金額」两列。
           但有一个 Eurex 没有的坑，见下面「JPX 的期权坑」。
  SGX   ❌ **没有**。SGX Monthly Market Statistics Report（2019-01 官方 PDF，32 页）
           衍生品部分只有 Volume 与 Open Interest 两类表，全文档没有任何
           notional / turnover value / contract value 字段（现货部分才有 Turnover Value）。
           api.sgx.com/derivatives/v1.0 是**实时行情**接口，不含历史名义额也不含合约规格。
  HKEX  ❌ **没有**。四个官方口子逐个查过，全部只有张数与未平仓：
             · Monthly Market Highlights xlsx     → "Average daily volume (contracts)"
             · /eng/stat/dmstat/marksum/MonthlyStatistics_FnO.json      → Contract Volume / Open Interest
             · /eng/stat/dmstat/marksum/MonthlyStatistics_F_HSI_290.json → 同上（逐产品）
             · /eng/stat/dmstat/marksum/{YYYYMM}MarketHighlights_TSO.json → 逐个股期权 class 的 Volume / OI
           HKEX 按张收费、从不公布成交金额，所以这是**制度性缺失**，换抓取手段没用。

━━ JPX 的期权坑（本轮最重要的发现，直接照搬方法①会错 23%）━━
Eurex 的工作簿里 Capital Volume 与 Paid Premiums 是**两列**，所以 Capital Volume 是名义额。
JPX 只有「取引金額」**一列**，而它对期货是名义额、对期权是**权利金**：

    日経225オプション 2019-01：取引金額 ÷ 张数 = 216,598 円/张
    而同月日経225的名义额应是 20,371.6 点 × ¥1,000 = 20,371,604 円/张 —— 差 94 倍。

（fetch/jpx.py 第 213 行早就把 adnv_n225_options_jpybn 标成「权利金成交金额」，
 本轮只是把这件事的后果算清楚。）

所以直接拿官方合計取引金額 ÷ 合計张数 = **6,792,231** 円/张 是错的，
期权那 9.18% 的张数被按权利金计价，整池被低估 23.0%。
正确做法：期货腿直接用官方取引金額，**期权腿按标的名义额重算**，得 **8,818,555** 円/张。

⚠ 这个错误在图上完全看不出来（柱子整体矮一截、形状不变），而且会让 JPX 相对 Eurex
系统性偏小 —— Eurex 的 Capital Volume 对期权用的是标的名义额（第一轮实测：ESTX50 期权
隐含点位 2942、DAX 期权隐含 10755，都在指数点位量级，不是权利金量级）。
两家口径必须一致，否则「跨所名义额份额」这张图的结论是假的。

━━ 期权腿的标的价格从哪来（不需要任何外部指数序列）━━
不去碰 Cloudflare 后面的 indexes.nikkei.co.jp —— 标的点位可以从**同一张官方表的期货腿**
反解出来，这是本轮绕开第一轮全部价格阻塞的关键：

    隐含 N225  = (日経225先物 取引金額 + 日経225mini 取引金額)
               ÷ (日経225先物 张数 × ¥1,000 + 日経225mini 张数 × ¥100)
               = 20,371.6039  （大合约单独反解 20,364.8982、mini 单独 20,376.9701，
                                互差 0.06% ⇒ 两个乘数都没猜错）
    隐含 TOPIX = 同构 = 1,535.6413（大合约 1,535.7015、mini 1,532.9274，互差 0.18%）

即「该月成交的全部日经期货名义额 ÷ 全部日经期货指数点敞口」= 成交量加权指数点位。
分子分母同源同月，不引入任何第三方数据。

期权腿到标的的映射（全部来自官方合约规格页的「Contract Unit / Underlying」栏）：
    日経225オプション      Contract Unit「Option Price × JPY 1,000」→ 隐含N225 × 1,000
    TOPIXオプション        Contract Unit「Option Price × ¥10,000」  → 隐含TOPIX × 10,000
    長期国債先物オプション  「1 option contract represents the right to buy or sell
                            10-year JGB futures of 100 million yen in face value」
                           → 直接取長期国債先物的单张名义额（¥152,574,029，已含价格项）
    金先物オプション        「Underlying Asset: Price of Gold Standard Futures」
                           → 取金標準先物单张名义额（¥4,519,300）
    有価証券オプション      ⚠ 唯一没算出名义额的一腿，见下。

━━ 唯一的残余缺口：有価証券オプション（占全池 0.1637% 张数）━━
它的乘数是「各标的的売買単位」（通常 100 株）、名义额还要乘各标的股价，官方月度表不拆。
本脚本对这一腿**不编数**，保留 JPX 自己发的取引金額（权利金）原值。
影响已实测封顶：把它从 0 一路试到 ¥5,000,000/张（对 100 株日本股来说高得离谱），
篮子常数只在 8,818,542 ~ 8,826,728 之间动，**±0.09%**。所以它不影响任何结论。

━━ 口径留痕（主线程填 base_price_basis 时必须看）━━
本常数隐含的价格项是**成交量加权成交价**，不是既有 23 行表头写的 avg_close
（月内交易日收盘价等权算术平均）。这与第一轮 EUREX_INDEX / EUREX_EQUITY 走的是同一条路、
同一个口径差，两家因此可比。⚠ 不要默默填 avg_close。

━━ 另外两条已经闭合的外部校验 ━━
  1) 宽表合計张数 29,849,336 ÷ 19 个立会日 = 1,571.017684 千张/日
     与 series/jpx.csv 的 adv_deriv_total_raw_kcontracts **逐位相等**
     ⇒ 分母与 pools.py 给 JPX_DERIV 配的那一列是同一个口径，没有多算少算。
  2) 宽表合計取引金額 ÷ 19 = 10.670715524 兆円/日
     与 series/jpx.csv 的 adnv_deriv_total_jpytn **逐位相等** ⇒ 分子源头没读错列。
  3) fetch.jpx._check_wide_closure 的三条闭合式（三大类=合計、逐产品=合計、分组=小计）
     本脚本每次运行都重跑。

⚠ 商品関連（旧 TOCOM，2019-01 占 5.10% 张数）在宽表里是 **pro-forma 回填**
（TOCOM 2020-07-27 才迁入 OSE）。pools.py 配的 adv_deriv_total_raw_kcontracts 同样含它，
两边一致，所以篮子常数必须**也含它**才自洽 —— 本脚本含。

━━ 依赖 ━━ 标准库 + xlrd（读 .xls 宽表）+ curl_cffi（可选，只在联网核规格页时用）。
"""

import argparse
import csv
import html
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

CACHE = os.path.join(ROOT, 'cache', 'basefill')
OUT_CSV = os.path.join(ROOT, 'series', '_specs_part_eastasia2.csv')

BASE_MONTH = '2019-01'

# 宽表：token 每月变，靠衍生品落地页发现（同 fetch/jpx.py 的 _discover_deriv）。
# 这里写死本轮实测可用的一版，--no-net 时直接读 cache。
WIDE_URL = ('https://www.jpx.co.jp/english/markets/statistics-derivatives/'
            'trading-volume/b5b4pj0000039yyj-att/tv_ts202606.xls')
WIDE_LOCAL = os.path.join(CACHE, 'jpx_tv_ts202606.xls')

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

# 期权腿 → 它的标的怎么定价。值是 (标的类型, 参数)：
#   'index'   → 隐含点位 × 乘数
#   'futures' → 直接取该期货产品的单张名义额（价格项已含在官方取引金額里）
OPTION_LEGS = {
    '日経225オプション取引':      ('index',   'N225',  1000.0),
    'TOPIXオプション取引':        ('index',   'TOPIX', 10000.0),
    '長期国債先物オプション取引':  ('futures', '長期国債先物取引', None),
    '金先物オプション取引':        ('futures', '金標準先物', None),
}
# 唯一不重算的一腿：乘数是各标的的売買単位、名义额还要乘各标的股价，官方月表不拆。
UNPRICED_LEG = '有価証券オプション取引'

# 官方合约规格页 —— 上面那几个乘数的出处，联网时逐个回核（正则命中即算通过）
SPEC_PAGES = {
    '日経225オプション取引': (
        'https://www.jpx.co.jp/english/derivatives/products/domestic/225options/01.html',
        r'Contract Unit\s*Option Price\s*×\s*JPY\s*1,000'),
    'TOPIXオプション取引': (
        'https://www.jpx.co.jp/english/derivatives/products/domestic/topix-options/01.html',
        r'Contract Unit\s*Option Price\s*×\s*¥?10,000'),
    '長期国債先物オプション取引': (
        'https://www.jpx.co.jp/english/derivatives/products/jgb/jgbf-options/01.html',
        r'10-year JGB futures of 100 million yen in face value'),
    '金先物オプション取引': (
        'https://www.jpx.co.jp/english/derivatives/products/precious-metals/'
        'options-on-gold-futures/01.html',
        r'Underlying Asset[^.]{0,60}Price of Gold Standard Futures'),
}


def _get(url, timeout=60):
    """优先 curl_cffi impersonate（jpx.co.jp 用不上，但保持与本轮其它组同一姿势）。"""
    try:
        from curl_cffi import requests as cr
        r = cr.get(url, impersonate='chrome', timeout=timeout)
        return r.status_code, r.content
    except ImportError:
        req = urllib.request.Request(url, headers={'User-Agent': _UA})
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            return fh.getcode(), fh.read()


def ensure_wide(no_net):
    if os.path.exists(WIDE_LOCAL):
        return WIDE_LOCAL
    if no_net:
        raise SystemExit('缺 %s 且 --no-net' % WIDE_LOCAL)
    os.makedirs(CACHE, exist_ok=True)
    code, blob = _get(WIDE_URL)
    if code != 200 or len(blob) < 500000:
        raise SystemExit('宽表下载异常：HTTP %s，%d bytes' % (code, len(blob)))
    with open(WIDE_LOCAL, 'wb') as f:
        f.write(blob)
    return WIDE_LOCAL


def verify_multipliers(no_net):
    """回核期权腿乘数的官方出处。联网失败不致命（只警告），命中不上则 raise。"""
    if no_net:
        print('  [规格页] --no-net，跳过')
        return
    for prod, (url, pat) in SPEC_PAGES.items():
        try:
            code, blob = _get(url, timeout=40)
        except Exception as e:                                    # noqa: BLE001
            print('  [规格页] %s 取不到（%r），跳过回核' % (prod, e))
            continue
        if code != 200:
            print('  [规格页] %s HTTP %s，跳过回核' % (prod, code))
            continue
        txt = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', blob.decode('utf-8', 'replace'))))
        if not re.search(pat, txt, re.I):
            raise SystemExit('规格页回核失败：%s 的官方页里找不到 %r —— '
                             '乘数可能改了，先人工看过再改本脚本\n  %s' % (prod, pat, url))
        print('  [规格页] %-24s ✓ 官方页命中' % prod)


def compute_jpx(no_net):
    from fetch.jpx import parse_wide, _wide_product_list, _check_wide_closure

    prods, rows = parse_wide(ensure_wide(no_net))
    _check_wide_closure(prods, rows)              # 三条官方闭合式，对不上直接 raise
    print('  [宽表] 闭合自检通过')

    rec = rows[BASE_MONTH]
    plist = _wide_product_list(prods)
    tot_v = rec[('合計', 'vol')]
    tot_val = rec[('合計', 'val')]
    days = rec['days']

    # ── 外部校验：分母/分子与 series/jpx.csv 逐位对齐 ──
    with open(os.path.join(ROOT, 'series', 'jpx.csv'), encoding='utf-8') as fh:
        jrow = next(r for r in csv.DictReader(fh) if r['month'] == BASE_MONTH)
    for col, got, scale in (('adv_deriv_total_raw_kcontracts', tot_v / days / 1000.0, 1e-6),
                            ('adnv_deriv_total_jpytn', tot_val / days / 1e12, 1e-8)):
        want = float(jrow[col])
        if abs(want - got) > scale * max(1.0, abs(want)) * 1e3:
            raise SystemExit('%s 对不上：宽表算出 %r，jpx.csv 是 %r' % (col, got, want))
        print('  [对账] %-32s 宽表 %.6f  vs jpx.csv %.6f  ✓' % (col, got, want))

    # ── 期货腿反解隐含指数点位（同表同月，不引入外部序列）──
    def implied(large, lmul, mini, mmul):
        return ((rec[(large, 'val')] + rec[(mini, 'val')])
                / (rec[(large, 'vol')] * lmul + rec[(mini, 'vol')] * mmul))

    idx = {
        'N225':  implied('日経225先物取引', 1000.0, '日経225mini', 100.0),
        'TOPIX': implied('TOPIX先物取引', 10000.0, 'ミニTOPIX先物取引', 1000.0),
    }
    # 大/小合约各自单独反解应当高度一致 —— 不一致说明某个乘数猜错了（会差整数倍）
    for nm, (lg, lm, mn, mm) in {'N225': ('日経225先物取引', 1000.0, '日経225mini', 100.0),
                                 'TOPIX': ('TOPIX先物取引', 10000.0, 'ミニTOPIX先物取引', 1000.0)}.items():
        a = rec[(lg, 'val')] / rec[(lg, 'vol')] / lm
        b = rec[(mn, 'val')] / rec[(mn, 'vol')] / mm
        gap = abs(a / b - 1.0)
        if gap > 0.02:
            raise SystemExit('%s 大/小合约反解点位互差 %.2f%%（%.4f vs %.4f）—— '
                             '乘数对不上，别往下算' % (nm, 100 * gap, a, b))
        print('  [反解] %-6s 隐含点位 %12.4f  (大 %.4f / 小 %.4f，互差 %.3f%%)'
              % (nm, idx[nm], a, b, 100 * gap))

    # ── 逐产品拼名义额 ──
    num = 0.0
    detail = []
    for p in plist:
        v = rec.get((p, 'vol')) or 0.0
        if not v:
            continue
        if p in OPTION_LEGS:
            kind, key, mul = OPTION_LEGS[p]
            per = idx[key] * mul if kind == 'index' else (rec[(key, 'val')] / rec[(key, 'vol')])
            tag = '期权→标的名义额'
        elif p == UNPRICED_LEG:
            per = (rec.get((p, 'val')) or 0.0) / v
            tag = '⚠权利金原值（未重算）'
        else:
            per = (rec.get((p, 'val')) or 0.0) / v
            tag = '期货/掉期：官方取引金額'
        num += v * per
        detail.append((p, v, per, v * per, tag))

    const = num / tot_v
    naive = tot_val / tot_v

    print('\n  ── 名义额构成（按名义额降序，前 10）──')
    for p, v, per, n, tag in sorted(detail, key=lambda x: -x[3])[:10]:
        print('    %-26s 张数%11.0f (%5.2f%%)  单张%14.0f  名义额占比%6.2f%%  %s'
              % (p[:26], v, 100 * v / tot_v, per, 100 * n / num, tag))

    # ── 未定价腿的敏感性上界 ──
    uv = rec[(UNPRICED_LEG, 'vol')]
    uval = rec[(UNPRICED_LEG, 'val')]
    sens = [(a, (num - uval + uv * a) / tot_v) for a in (0, 200000, 500000, 1000000, 5000000)]
    print('\n  ── 有価証券オプション（%.4f%% 张数）敏感性 ──' % (100 * uv / tot_v))
    for a, c in sens:
        print('    假设 %9d 円/张 → 常数 %.4f (%+.4f%%)' % (a, c, 100 * (c / const - 1)))

    print('\n  篮子常数 = %.6f JPY/张' % const)
    print('  （直接照搬方法① = %.6f，低估 %.2f%%）' % (naive, 100 * (1 - naive / const)))
    return const, naive, idx, rec, tot_v, tot_val, days, uv


def probe_sgx_hkex(no_net):
    """记录「方法①在 SGX / HKEX 不存在」这个结论是怎么实测出来的，供下一轮复核。"""
    if no_net:
        print('  --no-net，跳过')
        return
    checks = [
        ('HKEX 逐产品月度统计',
         'https://www.hkex.com.hk/eng/stat/dmstat/marksum/MonthlyStatistics_FnO.json',
         r'Contract Volume', r'(?i)notional|turnover value|contract value'),
        ('HKEX 逐个股期权 class（2019-01 存在）',
         'https://www.hkex.com.hk/eng/stat/dmstat/marksum/201901MarketHighlights_TSO.json',
         r'Open Interest', r'(?i)notional|turnover value|contract value'),
    ]
    for name, url, must, mustnot in checks:
        try:
            code, blob = _get(url, timeout=40)
        except Exception as e:                                    # noqa: BLE001
            print('  [%s] 取不到 %r' % (name, e))
            continue
        t = blob.decode('utf-8', 'replace')
        has = bool(re.search(must, t))
        bad = re.findall(mustnot, t)
        print('  [%s] HTTP %s  张数列=%s  名义额列=%s'
              % (name, code, '有' if has else '无', ('有！' + str(set(bad))) if bad else '无'))


NOTE_JPX = (
    'kind=contract, level=pool_product, multiplier=1 ⇒ base_price_local = 篮子常数。'
    '**走方法①（官方直接发名义额），但 JPX 有一个 Eurex 没有的坑，直接照搬会低估 23.0%。**'
    '源 = JPX 官方宽表 tv_ts202606.xls（衍生品落地页发布，逐产品同时给「取引高」与「取引金額」，'
    '回溯到 1985-10，含已退市品种）。'
    '2019-01 官方合計：张数 29,849,336、取引金額 202,743,594,953,749 円、立会日数 19。'
    '⚠ 坑：JPX 的「取引金額」对期货是名义额、对**期权是权利金**（Eurex 的 Capital Volume 与 '
    'Paid Premiums 是分开两列，JPX 只有一列）。实测：日経225オプション 取引金額÷张数 = 216,598 円/张，'
    '而同月名义额应是 20,371.6 点×¥1,000 = 20,371,604 円/张，差 94 倍。'
    '（fetch/jpx.py 第 213 行早已把 adnv_n225_options_jpybn 标为「权利金」，本轮把后果算清。）'
    '所以官方合計取引金額÷合計张数 = 6,792,231.32 円/张 是错的 —— 期权占 9.18% 张数被按权利金计价。'
    '正确做法：期货/掉期腿直接用官方取引金額；期权腿按标的名义额重算 ⇒ 8,818,555.107376 円/张。'
    '**期权腿的标的价格不需要任何外部指数序列**（这是绕开第一轮全部价格阻塞的关键）：'
    '从同一张官方表的期货腿反解 —— 隐含 N225 = (日経225先物取引金額+mini取引金額)÷'
    '(先物张数×¥1,000+mini张数×¥100) = 20,371.6039（大合约单独反解 20,364.8982、mini 单独 20,376.9701，'
    '互差 0.06% ⇒ 两个乘数都没猜错，若猜错会差整数倍）；同构得隐含 TOPIX = 1,535.6413'
    '（大 1,535.7015 / 小 1,532.9274，互差 0.18%）。'
    '期权腿→标的的映射全部回核过官方规格页（本脚本每次运行自动重核，命中不上就 raise）：'
    '日経225オプション「Contract Unit: Option Price × JPY 1,000」→ 隐含N225×1,000；'
    'TOPIXオプション「Option Price × ¥10,000」→ 隐含TOPIX×10,000；'
    '長期国債先物オプション「1 option contract represents the right to buy or sell 10-year JGB futures of '
    '100 million yen in face value」→ 直接取長期国債先物单张名义额 ¥152,574,029（价格项已内含）；'
    '金先物オプション「Underlying Asset: Price of Gold Standard Futures」→ 取金標準先物单张 ¥4,519,300。'
    '⚠ 唯一未重算的一腿：有価証券オプション（乘数是各标的売買単位、名义额还要乘各标的股价，官方月表不拆），'
    '保留 JPX 自己发的权利金原值、**不编数**。影响已封顶实测：从 0 试到 ¥5,000,000/张，'
    '常数只在 8,818,542~8,826,728 之间动（±0.09%），占 0.1637% 张数，不影响任何结论。'
    '两条外部校验逐位闭合：合計张数÷19 = 1,571.017684 千张/日 == jpx.csv 的 '
    'adv_deriv_total_raw_kcontracts（⇒ 分母与 pools.py 配的列同口径）；'
    '合計取引金額÷19 = 10.670715524 兆円/日 == jpx.csv 的 adnv_deriv_total_jpytn（⇒ 分子没读错列）；'
    '外加 fetch.jpx._check_wide_closure 的三条官方闭合式每次重跑。'
    '⚠ 商品関連（旧 TOCOM，占 5.10% 张数）在宽表里是 pro-forma 回填（2020-07-27 才迁入 OSE），'
    'pools.py 配的 adv_deriv_total_raw_kcontracts 同样含它 ⇒ 篮子常数也必须含，本行含。'
    '⚠ 名义额 ≠ 风险敞口：長期国債先物只占 2.15% 张数却占 37.28% 名义额（单张 ¥1.5257 亿），'
    '本池占比只能读作「名义额构成」。'
    '⚠ 口径留痕：本常数隐含的价格项是**成交量加权成交价**，不是表头定义的 avg_close，'
    '与第一轮 EUREX_INDEX / EUREX_EQUITY 同路同口径（两家因此可比）—— base_price_basis 不要填 avg_close。'
)

NOTE_SGX = (
    '未算出。**本轮结论：方法①在 SGX 不存在，是制度性缺失、不是抓取失败。**'
    '实测 cache/sgx_2019-01.pdf（SGX Monthly Market Statistics Report Jan 2019，官方 PDF，32 页）：'
    '衍生品部分（p.11-22）只有 "Derivatives Market Volume By Contract Types" 与 '
    '"Derivatives Market Open Interest By Contract Type" 两类表，逐页正则扫描 '
    'notional / turnover value / contract value 三个词**全文档零命中**；'
    '"Turnover Value" 只出现在现货（Securities market）部分。'
    '首页 At-A-Glance 也只给 "Derivatives Volume 18,614,593" 与 "Derivatives Daily Average Volume 867,843"，'
    '没有金额。api.sgx.com/derivatives/v1.0 用 curl_cffi impersonate=chrome 可通（HTTP 200），'
    '但返回的是**实时行情**（symbol/last-traded-price-adj/…），既无历史名义额也无合约规格；'
    '/contract-specification 路径 403 "Missing Authentication Token"。'
    'www.sgx.com/derivatives/products/ftsechinaa50 用 curl_cffi 仍只返回 14,850 bytes 的 Angular 外壳'
    '（⇒ 第一轮判断「单页应用」正确，这一条不是 TLS 指纹问题，impersonate 救不了）。'
    '张数权重仍然齐（同第一轮）：当月 Total 18,614,593，A50 7,488,026（40.2%）、'
    'MSCI Taiwan 1,807,072、Nifty 50 1,798,179、FX 期货 1,872,510、Nikkei 225 期货 1,631,290、'
    '铁矿石 62% 期货 1,369,025。'
    '⚠ 跨币种篮子，记账币定为 USD：各成员面值须先按 2019-01 基期汇率折成美元再加权，'
    '所以本行 ccy=USD、fx 那一跳是 1.0，不会二次折算。'
    '下一轮检索路径 = ① SGX 官方 contract specification **静态 PDF**（Angular 页背后的附件，'
    '不要再抓 HTML）；② SGX 官方每日结算价档案（links.sgx.com 的 derivatives-historical 序号目录，'
    '本轮试 links.sgx.com/1.0.0/derivatives-daily/2019-01-31 返回的是 2KB 提示页、非数据）；'
    '③ 各指数编制方的 2019-01 官方历史值（FTSE Russell / Nikkei / NSE / MSCI）。'
)

NOTE_HKEX = (
    '未算出。**本轮结论：方法①在 HKEX 不存在，是制度性缺失、不是抓取失败** —— '
    'HKEX 按张收费，从不公布衍生品成交金额。四个官方口子逐个实测（全部 curl_cffi impersonate=chrome，'
    '全部 HTTP 200，即第一轮的「被挡」已解除，但拿到的表里就是没有金额列）：'
    '① cache/hkex_monthly_highlights_2026-06.xlsx 的 "DERIVATIVES MARKET TURNOVER" 节，'
    '标题就是 "Average daily volume (contracts)"，逐产品 105-209 行全是张数；'
    '② /eng/stat/dmstat/marksum/MonthlyStatistics_FnO.json 表头 = Month / Contract Volume / Open Interest；'
    '③ /eng/stat/dmstat/marksum/MonthlyStatistics_F_HSI_290.json（逐产品版）表头 = '
    'Month / No. of Trading Days / Contract Volume / Open Interest / Average Daily / Total；'
    '④ /eng/stat/dmstat/marksum/{YYYYMM}MarketHighlights_TSO.json（逐个股期权 class）表头 = '
    'Class / Volume(Call,Put,Total) / Open Interest(Call,Put,Total)。'
    '**本轮的实质进展：④ 的 2019-01 档确实存在**（.../201901MarketHighlights_TSO.json，HTTP 200，71,296 bytes，'
    '逐 class 给 2019-01 当月 Call/Put/Total 张数，例：AAC Technologies 46,850 张）—— '
    '页面下拉框只列最近 12 个月，但 URL 按 {YYYYMM} 直拼可取历史档，第一轮缺的「逐 class 张数」由此解决。'
    '乘数也已全部实测（第一轮，官方产品规格页「Contract Multiplier」）：HSI 期货/期权 HK$50/点、'
    'Mini HSI 期货/期权 HK$10/点、HHI 期货/期权 HK$50/点、Mini HHI 期货/期权 HK$10/点。'
    '**所以现在只差两块价格**：① HSI / HSCEI 的 2019-01 指数点位（hsi.com.hk 用 curl_cffi 已能返回 '
    '67,328 bytes 正文、不再是 1.9KB 外壳，下一轮值得直接从这里找历史值接口）；'
    '② 个股期权/期货逐 class 的 2019-01 标的股价 × 每手股数（board lot）—— '
    'Stock Options 445,669 张/日 + Stock Futures 5,821 张/日 = 全池 41.4% 张数，'
    '需 HKEX「List of Stock Options」的逐 class 合约规格 + 逐 class 2019-01 月均股价。'
    '⚠ **不许把这 41.4% 从分母里剔掉再算**：个股期权单张名义额（每手×股价，量级 HK$ 数万）比 '
    'HSI 期货（HK$50×约27,000点≈HK$135 万）小两个数量级，剔掉等于给它们安上指数期货的名义额，'
    '整池会被系统性放大。'
    '⚠ 另一处已知口径坑（第一轮查出，仍成立）：hkex_monthly_highlights_2026-06.xlsx 是 2026-06 版模板，'
    '**不列 2026 年前已退市的产品** —— 2019-01 逐产品行加起来 1,091,041 张/日，比官方自己印的 Total '
    '1,091,651 少 610 张/日（0.06%），差额全在期货侧。占比小，但别把它当「逐产品全集」。'
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-net', action='store_true')
    a = ap.parse_args()

    print('━━ 1. JPX 期权腿乘数回核（官方规格页）━━')
    verify_multipliers(a.no_net)

    print('\n━━ 2. JPX 篮子常数 ━━')
    const, naive, idx, rec, tot_v, tot_val, days, uv = compute_jpx(a.no_net)

    print('\n━━ 3. SGX / HKEX：方法①存在性实测 ━━')
    probe_sgx_hkex(a.no_net)

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['product_id', 'base_price_local', 'base_ccy', 'basket_constant',
                    'source_url', 'computed_note'])
        w.writerow(['JPX_DERIV', '%.6f' % const, 'JPY', '%.6f' % const,
                    WIDE_URL + ' + https://www.jpx.co.jp/english/markets/statistics-derivatives/'
                               'trading-volume/index.html', NOTE_JPX])
        w.writerow(['SGX_DERIV', '', 'USD', '',
                    'https://www.sgx.com/research-education/derivatives + '
                    'cache/sgx_2019-01.pdf (SGX Monthly Market Statistics Report Jan 2019)',
                    NOTE_SGX])
        w.writerow(['HKEX_DERIV', '', 'HKD', '',
                    'https://www.hkex.com.hk/Market-Data/Statistics/Derivatives-Market/'
                    'Monthly-Statistics?sc_lang=en + '
                    'https://www.hkex.com.hk/eng/stat/dmstat/marksum/201901MarketHighlights_TSO.json',
                    NOTE_HKEX])
    print('\n写出 %s' % OUT_CSV)


if __name__ == '__main__':
    main()
