# -*- coding: utf-8 -*-
"""中国神华（China Shenhua Energy，601088.SH / 1088.HK）单公司页配置。

━━ 这份文件的全部职责 ━━
声明「series/shenhua.csv 的哪些列、按什么中文名、什么单位、什么格式器上页面」。
数据怎么来、怎么核对见 fetch/shenhua.py 的模块 docstring 与 docs/verify/shenhua.md。
整份文件可以直接删掉：删了 /shenhua/ 页就没了，别的页一行都不受影响。

━━ 本页最要紧的一件事：公司反复「追溯调整上年同期」，自算同比与官方同比会打架 ━━
神华每逢资产注入都重述上年同期（2012-04、2015-10、2020-01、2025-02、2026-04 …，
清单在 series/shenhua_breaks.csv，每条带公告原文出处）。重述之后，
「当月 ÷ 去年同月那份公告印的数 − 1」（底座的单月同比）≠ 官方公布的同比。
全站规矩是「页面上的数一律用官方值」，所以本页的三条约定：

  1. **头条列是自有铁路运输周转量，不是商品煤产量。** 头条列要画单月同比柱、进汇总表的 y/y、
     画季节性 —— 三处都是底座自算的同比。商品煤产量 / 煤炭销售量在最近 21 个月里有两次重述
     （2025-02 杭锦能源、2026-04 国家能源集团注入资产），自算同比在 2025-02..2026-01 与
     2026-04..2027-03 都会偏离官方（2026-09 当月自算 +61%，官方 +3.2%）。铁路周转量在本页
     窗口内（2016 起）从未被重述，自算同比与官方逐月相等（舍入以内，`_yoy_gap()` 现算）。
  2. **其余水平值一律画「同单位多列折线」，不画「柱 + 次轴同比」。** 底座只在单列柱图上画自算同比；
     两列以上画折线，不画同比。增速改由「官方公布同比」那几张图给 —— 那几列是公告表格里
     「同比变化（%）」一栏的原文，不是本页算的（fetch 逐格核过它落在两数舍入的可行区间里）。
  3. **2026-04 那次重述把受影响的指标切成两列**（`<列>` 旧口径，止于 2026-03；`<列>_s2604` 新口径）。
     新口径列 = 2026-04 起每期的当月值 + 那几期公告「上年同月（已重述）」回填到 2025 年同月。
     两类都是官方印出来的数，所以新口径列的「当月 ÷ 12 个月前」逐格等于官方同比 ——
     汇总表 y/y 那一格因此是对的；旧口径列本月为「—」（它止于 2026-03，不是还没发）。
     2026-04 之前那几次重述**没有切列**：那些窗口里的自算同比本页一张图都不画（第 2 条），
     汇总表只看当月，也碰不到它们。

━━ 有意不上页面的列（都在 series/shenhua.csv 里，核对表也不列）━━
· coal_export_mt / coal_import_mt —— 出口 2016-03 止、进口 2012-02 至 2016-03，进 2016 窗口的只有 3 个月。
· coal_self_mt / coal_purch_mt —— 自产煤 / 外购煤只在 2016-04..12 印过 9 期。
· polyolefin_sales_kt —— 2020-01、02 两期把聚乙烯 + 聚丙烯合并报成「聚烯烃产品」（千吨），
  那两个月聚乙烯 / 聚丙烯两列因此空着；它与 2026-06 起的「聚烯烃销售量（万吨）」口径不同，不拼接。
· rail_yoy_pct / pe_yoy_pct / pp_yoy_pct —— 铁路的官方同比与自算相同（头条那张同比柱就是它）；
  聚乙烯 / 聚丙烯的官方同比被检修停车月份拉到 +695% / −85%，同轴画会把其余月份压扁，
  而截轴（spike_cap）要页面所有者点名才开，所以不画，水平值那两张图已经讲清楚了停车月份。
"""

import csv
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CSV = os.path.join(_ROOT, 'series', 'shenhua.csv')
_ANN = os.path.join(_ROOT, 'series', 'shenhua_ann.csv')
_WIN = '2016-01'          # 与底座 WIN_FROM 同值；只用于页尾现算的「本页窗口内」计数


def _rows(p=_CSV):
    try:
        with open(p, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _span(col):
    """该列有值的首月与末月（'YYYY-MM'）；整列为空返回 (None, None)。"""
    ms = [r['month'] for r in _rows() if r.get(col, '').strip()]
    return (ms[0], ms[-1]) if ms else (None, None)


def _n_months():
    rs = _rows()
    return len(rs), (rs[0]['month'] if rs else None), (rs[-1]['month'] if rs else None)


def _shift(m, k):
    y, mm = int(m[:4]), int(m[5:]) + k
    y += (mm - 1) // 12
    return f'{y}-{(mm - 1) % 12 + 1:02d}'


def _half(s):
    return 0.5 * 10 ** (-(len(s.split('.')[1]) if '.' in s else 0))


def _feasible(cur, py, yoy):
    """官方同比 yoy 与 cur/py 的舍入可行区间相交 → True（与 fetch/shenhua.yoy_feasible 同一判据）。"""
    c, p, y = float(cur), float(py), float(yoy)
    hc, hp, hy = _half(cur), _half(py), _half(yoy)
    if p - hp <= 0:
        return None
    lo, hi = ((c - hc) / (p + hp) - 1) * 100, ((c + hc) / (p - hp) - 1) * 100
    return not (y + hy + 1e-9 < lo or y - hy - 1e-9 > hi)


def _yoy_gap(col, ycol, since=_WIN):
    """`since` 起，宽表里「本列当月 ÷ 本列 12 个月前 − 1」（底座的自算同比）与官方同比
    对不上（超出两数舍入的可行区间）的月份。返回 (可比月数, [对不上的月份…])。"""
    w = {r['month']: r for r in _rows()}
    n, bad = 0, []
    for m, r in w.items():
        if m < since:
            continue
        cur, base, off = r.get(col, ''), w.get(_shift(m, -12), {}).get(col, ''), r.get(ycol, '')
        if not (cur and base and off):
            continue
        ok = _feasible(cur, base, off)
        if ok is None:
            continue
        n += 1
        if not ok:
            bad.append(m)
    return n, bad


def _restated_n():
    """台账里「上年同月」≠ 去年那份公告当月值的格子数（全历史），以及涉及的公告期数。"""
    ann = _rows(_ANN)
    cur = {(r['month'], r['ind']): r['cur'] for r in ann}
    cells, months = 0, set()
    for r in ann:
        py, base = r['py'], cur.get((_shift(r['month'], -12), r['ind']), '')
        if py in ('', '-', 'NA') or base in ('', '-', 'NA'):
            continue
        f = 0.1 if r['unit_pub'] == '亿千瓦时' else 1.0
        b0 = [x for x in ann if x['month'] == _shift(r['month'], -12) and x['ind'] == r['ind']]
        fb = 0.1 if b0 and b0[0]['unit_pub'] == '亿千瓦时' else 1.0
        if abs(float(py) * f - float(base) * fb) > 1e-9:
            cells += 1
            months.add(r['month'])
    return cells, len(months)


def _runs(ms):
    """['2016-01','2016-02','2016-03','2025-02'] → '2016-01..2016-03、2025-02'（连续月份并成一段）。"""
    out = []
    for m in ms:
        if out and _shift(out[-1][1], 1) == m:
            out[-1][1] = m
        else:
            out.append([m, m])
    return '、'.join(a if a == b else f'{a}..{b}' for a, b in out)


def _src_counts():
    """台账里中文版取数 / 英文版补格的行数。"""
    ann = _rows(_ANN)
    return sum(1 for r in ann if r['src'] == 'zh'), sum(1 for r in ann if r['src'] == 'en')


# ── 列配置 ───────────────────────────────────────────────────────────────
def _c(col, zh, unit, fmt='f1', **kw):
    return dict({'col': col, 'zh': zh, 'unit': unit, 'fmt': fmt}, **kw)


_MT, _TKM, _TNM, _KWH, _KT, _10KT = '百万吨', '十亿吨公里', '十亿吨海里', '十亿千瓦时', '千吨', '万吨'
_YOY = '%'


def _off(col, zh):
    return _c(col, zh, _YOY, 'pct1', ratio=True)


_SEC_COAL, _SEC_TRANS, _SEC_POWER, _SEC_CHEM = '煤炭', '运输', '发电', '煤化工'

# ── 名词释义 ─────────────────────────────────────────────────────────────
_GLOSSARY = [
    ('官方同比',
     '公告表格里「同比变化（%）」一栏的<b>原文</b>，不是本页算的。公司重述上年同期后，'
     '它用的是<b>重述后的上年基数</b>，所以可能不等于「当月 ÷ 去年那份公告印的当月 − 1」。'
     '本页凡写「官方同比」的图都画这一栏；两者冲突时以它为准。'),
    ('重述',
     '资产注入后，公司在新公告里把「上年同期」那几格按新口径重算一遍（公告原话「追溯调整」'
     '「进行了重述」）。去年那份公告的数不会改 —— 同一个月于是有两个官方数：'
     '当时印的（旧口径）与一年后重述的（新口径）。'),
    ('新口径',
     '图例里带「2026-04 起新口径」的那几条线：2026-04 起每期的当月值，加上这几期公告'
     '<b>重述后的上年同月</b>（回填在 2025 年对应月份）。它与「2026-03 及以前口径」那条线'
     '在 2025 年有几个月是同一个月的两个官方数，差额就是新并入资产的业务量。'),
    ('自有铁路运输周转量',
     '公司自有铁路完成的货物周转量，单位十亿吨公里 = 吨数 × 运距。'
     '它是本页头条，因为本页窗口内它<b>从未被重述</b>，自算同比与官方同比逐月一致'
     '（2026-04 那次注入资产，公告里它的上年同月与原值逐格相同）。'),
    ('装船量',
     '黄骅港、天津煤码头两个港口当月的装船量（2020-01 起的口径）。'
     '2019 年及以前印的是「港口下水煤（销）量」中经这两个港口的部分，属于<b>销量</b>口径 —— '
     '2019-01 公告说明那个月销量（含下水煤量）因春节前「已发运但尚未完成结算」而下降。'
     '两种口径在 2020-01 处不可比（图上红线），2020 年各期公告的上年同月已按装船量重述。'),
    ('航运周转量',
     '自有船队完成的货物周转量，单位十亿吨海里 = 吨数 × 海运里程；航运货运量是同一船队的吨数。'
     '两者之比是平均运距，航线结构一变（例如近海 / 远洋占比）周转量就与货运量背离。'),
    ('总售电量',
     '电厂对外销售的电量；公告里与总发电量并列、口径同步变化，两条线一般同涨同跌。'
     '2019-02 起神华把一批火电资产投入与国电电力的合资公司、不再并表，发电两条线在那里断一档。'),
]


def _note_source(page):
    n, m0, m1 = _n_months()
    zh, en = _src_counts()
    src = (f'{zh} 行全部取自中文版' if not en else f'{zh} 行取自中文版、{en} 行中文版字距拆碎而取英文版同一格')
    return (f'<b>数据源与核对。</b>中国神华每月一份「主要运营数据公告」，本页取港交所披露易（01088）上的'
            f'<b>中文版</b>逐期解析，{m0} 至 {m1} 共 {n} 期、逐月连续（2007-09 是 A 股上市后的第一期）；'
            f'台账 {src}，同一份公告的<b>英文版</b>逐格对照、数值全部相等'
            '（早年中文版的「亿千瓦时」按十亿千瓦时换算后比；中文「-」与英文「N/A」互认），'
            f'每一行的官方同比还要落在「当月 ÷ 上年同月」两数舍入的可行区间里，{n} 期无一例外。'
            '上交所版本（601088）只用作「这一期存不存在」的旁证：它的 PDF 对脚本返回反爬挑战页，本页不去破解。'
            '2007-09 至 2008-06 中文版的发电量印成「亿千瓦时」，本页统一除以 10 落成「十亿千瓦时」（只挪小数点）。')


def _note_headline(page):
    parts = []
    for col, ycol, zh in (('rail_tkm_bn', 'rail_yoy_pct', '自有铁路运输周转量'),
                          ('coal_prod_mt', 'coal_prod_yoy_pct', '商品煤产量（旧口径列）'),
                          ('coal_sales_mt', 'coal_sales_yoy_pct', '煤炭销售量（旧口径列）'),
                          ('power_gen_bnkwh', 'power_gen_yoy_pct', '总发电量（旧口径列）'),
                          ('huanghua_mt', 'huanghua_yoy_pct', '黄骅港'),
                          ('coal_prod_mt_s2604', 'coal_prod_yoy_pct', '商品煤产量（新口径列）')):
        n, bad = _yoy_gap(col, ycol)
        if not n:
            continue
        parts.append(f'{zh} {n} 个可比月里 {len(bad)} 个对不上' + (f'（{_runs(bad)}）' if bad else ''))
    cells, months = _restated_n()
    return ('<b>为什么头条是铁路周转量、而增速看「官方同比」那几张图。</b>'
            f'公司历次资产注入后都追溯调整上年同期：全历史 {cells} 格「上年同月」与去年那份公告印的当月值不同，'
            f'分布在 {months} 期公告里（断点与原文出处见页尾断点清单）。于是底座的单月同比'
            '（本列当月 ÷ 本列 12 个月前）在重述窗口里会拿新口径除旧口径。'
            f'{_WIN} 起逐月复算「自算 vs 官方」（超出两数舍入的可行区间才算对不上）：'
            + '；'.join(parts) + '。'
            '所以只有自算同比与官方逐月一致的铁路周转量做头条（它的同比柱、汇总表 y/y、季节性都是自算的），'
            '其余指标的水平值画多列折线（底座不在折线上画同比），增速改看各业务那张「官方公布同比」。'
            '2026-04 那次重述还把受影响的指标切成了两列，新口径列的汇总表 y/y 逐格等于官方同比。')


def _note_hidden(page):
    def sp(c):
        a, b = _span(c)
        return f'{a}..{b}' if a else '整列为空'
    return ('<b>公告里有、本页不画的列</b>（都在 series/shenhua.csv 里）：'
            f'煤炭出口量（{sp("coal_export_mt")}）、进口量（{sp("coal_import_mt")}）、'
            f'自产煤 / 外购煤销量（{sp("coal_self_mt")}）、'
            f'聚烯烃产品销售量（千吨，{sp("polyolefin_sales_kt")}，那两个月聚乙烯 / 聚丙烯合并报）'
            '—— 进本页窗口的不足一年；聚乙烯 / 聚丙烯的官方同比被检修停车月份拉到几百个百分点，'
            '同轴会把其余月份压扁，也不画。'
            '汇总表里本月一格是「—」的几行不是「还没发」：旧口径列止于 2026-03，'
            f'港口下水煤量止于 {_span("seaborne_mt")[1]}（2020-01 起停报），'
            f'聚乙烯 / 聚丙烯止于 {_span("pe_sales_kt_s2604")[1]}（2026-06 起改报聚烯烃 / 油品 / 甲醇 / 乙二醇四项）。')


def _note_gaps(page):
    return ('<b>空格的来历（都是公告没印，不是没抓到）。</b>'
            '2008-03 只发了一季度合计、没有 3 月单月数（整行空，本页不拿一季度减 1、2 月去拆）；'
            '2007-09 至 2007-11 的对比栏是「2006 年月均参考值」不是上年同月，2007-12 只给全年对比，'
            '2016-04 至 2016-06 三期表格不印同比 —— 这几期的官方同比都是空的；'
            '2020-01 公司以合资公司出表为由不再列示 2019-01 的发、售电量（公告原话「为免误导」），'
            '那一期发电两条的官方同比也是空的。')


SPEC = {
    'ticker': 'shenhua',
    'name':   'China Shenhua Energy',
    'title':  '中国神华（601088.SH / 1088.HK）月度主要运营数据',
    'csv':    'shenhua.csv',
    'ccy':    'CNY',
    'source': 'Source: China Shenhua Energy monthly announcements on major operational data, '
              'HKEXnews 01088 Chinese version (English version cross-checked cell by cell); '
              'format after Goldman Sachs GIR',

    'headline': [
        _c('rail_tkm_bn', '自有铁路运输周转量', _TKM),
    ],
    'headline_section': '头条：自有铁路运输周转量',
    'season_section': '季节性',

    'groups': [
        # ── 煤炭 ──
        {'zh': '商品煤产量', 'section': _SEC_COAL, 'cols': [
            _c('coal_prod_mt', '商品煤产量（2026-03 及以前口径）', _MT),
            _c('coal_prod_mt_s2604', '商品煤产量（2026-04 起新口径）', _MT),
        ]},
        {'zh': '煤炭销售量', 'cols': [
            _c('coal_sales_mt', '煤炭销售量（2026-03 及以前口径）', _MT),
            _c('coal_sales_mt_s2604', '煤炭销售量（2026-04 起新口径）', _MT),
        ]},
        {'zh': '煤炭：官方公布同比', 'cols': [
            _off('coal_prod_yoy_pct', '商品煤产量官方同比'),
            _off('coal_sales_yoy_pct', '煤炭销售量官方同比'),
        ]},
        # ── 运输（铁路是头条，在页首）──
        {'zh': '港口', 'section': _SEC_TRANS, 'cols': [
            _c('seaborne_mt', '港口下水煤量（2019-12 止）', _MT),
            _c('huanghua_mt', '黄骅港', _MT),
            _c('tianjin_mt', '天津煤码头', _MT),
        ]},
        {'zh': '航运货运量', 'cols': [
            _c('ship_vol_mt', '航运货运量（2026-03 及以前口径）', _MT),
            _c('ship_vol_mt_s2604', '航运货运量（2026-04 起新口径）', _MT),
        ]},
        {'zh': '航运周转量', 'cols': [
            _c('ship_tnm_bn', '航运周转量（2026-03 及以前口径）', _TNM),
            _c('ship_tnm_bn_s2604', '航运周转量（2026-04 起新口径）', _TNM),
        ]},
        {'zh': '运输：官方公布同比', 'cols': [
            _off('huanghua_yoy_pct', '黄骅港官方同比'),
            _off('tianjin_yoy_pct', '天津煤码头官方同比'),
            _off('ship_vol_yoy_pct', '航运货运量官方同比'),
            _off('ship_tnm_yoy_pct', '航运周转量官方同比'),
        ]},
        # ── 发电 ──
        {'zh': '总发电量', 'section': _SEC_POWER, 'cols': [
            _c('power_gen_bnkwh', '总发电量（2026-03 及以前口径）', _KWH, 'f2'),
            _c('power_gen_bnkwh_s2604', '总发电量（2026-04 起新口径）', _KWH, 'f2'),
        ]},
        {'zh': '总售电量', 'cols': [
            _c('power_sold_bnkwh', '总售电量（2026-03 及以前口径）', _KWH, 'f2'),
            _c('power_sold_bnkwh_s2604', '总售电量（2026-04 起新口径）', _KWH, 'f2'),
        ]},
        {'zh': '发电：官方公布同比', 'cols': [
            _off('power_gen_yoy_pct', '总发电量官方同比'),
            _off('power_sold_yoy_pct', '总售电量官方同比'),
        ]},
        # ── 煤化工 ──
        {'zh': '聚乙烯销售量', 'section': _SEC_CHEM, 'cols': [
            _c('pe_sales_kt', '聚乙烯销售量（2026-03 及以前口径）', _KT),
            _c('pe_sales_kt_s2604', '聚乙烯销售量（2026-04 起新口径）', _KT),
        ]},
        {'zh': '聚丙烯销售量', 'cols': [
            _c('pp_sales_kt', '聚丙烯销售量（2026-03 及以前口径）', _KT),
            _c('pp_sales_kt_s2604', '聚丙烯销售量（2026-04 起新口径）', _KT),
        ]},
        {'zh': '煤化工（2026-06 起改报的四项）', 'cols': [
            _c('polyolefin_sales_10kt', '聚烯烃销售量', _10KT),
            _c('oil_sales_10kt', '油品销售量', _10KT),
            _c('methanol_sales_10kt', '甲醇销售量', _10KT),
            _c('meg_sales_10kt', '乙二醇销售量', _10KT),
        ]},
    ],

    'breaks': 'shenhua_breaks.csv',
    'glossary': _GLOSSARY,
    'notes': [
        _note_source,
        _note_headline,
        _note_gaps,
        _note_hidden,
    ],
}
