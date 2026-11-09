# -*- coding: utf-8 -*-
r"""中国神华（China Shenhua Energy，601088.SH / 1088.HK）月度主要运营数据 —— 无人值守抓取模块。

对应 build/specs/shenhua.py（页面由通用底座 build/single.py 生成），维护两张表：

  series/shenhua_ann.csv   台账，一份公告一指标一行：公告表格里**印出来的每一格原样**
                           （当月 / 累计 / 上年同月 / 上年累计 / 当月同比 / 累计同比，
                           以及该格的原文行名、原文单位、表格版式、文件号、上载时刻）。只增不改。
                           「上年同期被重述了多少」「官方同比与自算同比差多少」两笔账的唯一底稿。
  series/shenhua.csv       宽表，一月一行，由台账**确定性推出**（`build_wide()`）。页面只读这一张：
                           · 每条指标的当月值（该月自己那份公告印的数）；
                           · 最近一次「重述」断点（SCOPE_SPLITS，目前 2026-04）处切出的新口径列
                             `<列>_s2604`：断点起的当月值 + 断点后各期公告「上年同月（已重述）」回填到 M−12；
                           · 官方「当月同比（%）」原文 `<ind>_yoy_pct`（YOY_IND 那几条）。

宽表每一格都是**官方公告原值**，唯一的变换是一处无损换单位：2007-09..2008-06 的中文版把
发电量 / 售电量印成「亿千瓦时」（61.6），宽表统一落「十亿千瓦时」（6.16）—— ÷10，小数点挪一位，
有效数字一位不丢（台账里保留原文单位与原数）。

────────────────────────────────────────────────────────────────────────
数据源
────────────────────────────────────────────────────────────────────────
公司每月一份「主要运营数据公告」，同一天出三份官方文本：
  ① 上交所 601088 的 A 股公告（简体中文 PDF）
  ② 港交所披露易 01088 的「海外監管公告」中文版（繁体中文 PDF，表格内文常是简体）
  ③ 同一份的英文版（ANNOUNCEMENT ON THE MAJOR OPERATIONAL DATA OF <MONTH YYYY>）

**主源是 ②（披露易中文版），③ 是逐格交叉核对源。** 选它的理由逐条实测过（2026-11-09）：
  · 上交所的**列表接口**能程序化列出全部 229 期（query.sse.com.cn 的
    queryCompanyBulletin.do，标题一律「中国神华YYYY年M月份主要运营数据公告」），
    但**PDF 本体**（static.sse.com.cn）对脚本一律回 200 + 7 KB 的 JS 反爬挑战页（acw_sc__v2
    cookie），不是 PDF。不去破解反爬 —— 这个源只能当「这一期存不存在」的旁证，取不到数。
  · 公司官网 csec.com 的 HTTPS 握手失败（SSLV3_ALERT_HANDSHAKE_FAILURE，curl / curl_cffi
    都一样），HTTP 能开首页但没有可程序化的公告列表。
  · 披露易的标题检索接口（下面的 HK_SEARCH）一次请求就能列出一个日期窗口内 01088 的全部
    文件，JSON、无鉴权、普通浏览器 UA 的 urllib 直连 200（实测单次 1-2 秒）；PDF 直链同样直连。
    中英两版都在：同一份公告中文版的文件号通常是英文版 +1，`_c.pdf` 结尾。
  · 港交所版本的落款写着「如中英文版本有任何差异，以中文版为准」（2010 年起的英文版
    逐期印着这句），所以主源取中文、英文只做核对。

  HK_SEARCH  https://www1.hkexnews.hk/search/titleSearchServlet.do
             ?stockId=9124&fromDate=YYYYMMDD&toDate=YYYYMMDD&title=&lang=ZH|E&rowRange=…
             （stockId 9124 是披露易内部编号，由 /search/prefix.do?name=01088 查得，不是股票代码）
  PDF        https://www1.hkexnews.hk/listedco/listconews/sehk/YYYY/MMDD/<文件号>[_c].pdf

⚠ **标题不可全信，要开 PDF 认月份。** 229 期里有 6 期在披露易上的标题只是泛称
「海外監管公告 / OVERSEAS REGULATORY ANNOUNCEMENT」，标题里没有「運營數據」：
2009-08、2009-11、2018-06、2019-04、2019-05、2026-01。只按标题筛会静默漏掉这 6 个月
（2026-01 那期还会被误读成「1、2 月合并发布」—— 实测不是，那期单独发了，只是标题泛称）。
所以 `discover()` 对「上载月里没有任何带运营数据标题的公告」的那几个月，把泛称公告下载下来，靠 PDF 正文第一屏的
「YYYY年M月份主要運營數據公告」认月份；英文版同理认 "MAJOR OPERATIONAL DATA OF <MONTH> YYYY"。

────────────────────────────────────────────────────────────────────────
历史深度与表格版式（229 期全量实测，2007-09 .. 2026-09）
────────────────────────────────────────────────────────────────────────
第一期是 **2007 年 9 月**（2007-10-15 发，A 股 2007-10-09 上市之后的第一个完整月）。
披露易上 01088 在此之前没有任何运营数据公告（2005-06 H 股上市起逐年列全清单核过）。
229 期逐月连续、无一缺期，**没有一期是 1、2 月合并发布**（每年 1 月都单独发了一份）。

表格版式按「一行几个数」分七种，`_LAYOUTS` 逐一登记了列序；**列序不由标题推断**：
  M6  当月 / 累计 / 上年当月 / 上年累计 / 当月同比 / 累计同比      —— 2009-03 起绝大多数月份
  M3  当月 / 上年当月 / 同比                                      —— 1 月、2008-2011 的常规月
  M4  当月 / 累计 / 上年当月 / 上年累计（**不印同比**）             —— 2016-04、05、06 三期
  A6  **全年** / 12 月 / 上年全年 / 上年 12 月 / 全年同比 / 12 月同比 —— 2008-12 至 2011-12 四个年末月
  D4  12 月 / 全年 / 上年全年 / 全年同比（**没有上年 12 月**）        —— 2007-12
  Q3  一季度 / 上年一季度 / 同比（**没有 3 月单月**）                —— 2008-03
  R3  当月 / 2006 年**月均参考值** / 变化（不是同比）                 —— 2007-09、10、11
A6 与 M6 都是一行 6 个数、列序相反，靠表头的「年度同比」认（`_detect_layout()`）；
认错了也逃不掉 —— 每一行都过「官方同比 vs 本行两数自算」的区间核对（口径坑 3）。

**2008-03 没有单月数**：那一期只发了一季度合计（「2008年一季度主要運營數據公告」），
3 月当月值官方从未单独公布。宽表 2008-03 整行留空，**不拿一季度减 1、2 月去拆**；
一季度合计原样记在台账里。这是全序列唯一一个当月空洞。

────────────────────────────────────────────────────────────────────────
发布节奏（229 期实测，披露易上载时间）
────────────────────────────────────────────────────────────────────────
见 `fetch/shenhua.py --cadence` 现印的全表。统计口径 = 披露易上载日 − 数据月末（天），
上载时间几乎都在当天 16:00-19:00（收市后）。
  · 全样本（n=229）最早第 10 天（2012-08 → 09-10），中位第 16 天，最晚第 30 天（2011-12 → 2012-01-30，春节）。
  · 12 月数据（1 月发）普遍晚：19 期中位第 21 天、最晚第 30 天；2020 年起这一档最晚第 22 天（2020-12）。
  · 2020 年起（n=81）最早第 11 天、中位第 15 天、最晚第 22 天；季末月（3/6/9，n=21）最晚第 20 天、
    其余常规月（n=54）最晚第 21 天 —— 季末月不随季报走，没有额外延迟。2016-2019 有过第 25 天。
roster LAG = (22, 22) 取 2020 年以来全部 81 期的最晚值；EARLY_BY = (12, 12) 让闸门开在第 10 天
（= 全样本最早发布日），见 build/roster.py 与 monthly_run.EARLY_BY 那两行注释。
（上面这几个数是建库那天的实测，**以 `--cadence` 现印的为准**。）

────────────────────────────────────────────────────────────────────────
口径坑（踩过的，别再踩）
────────────────────────────────────────────────────────────────────────
1. **「-」的意思不固定**：有时是「无 / 零」（2014-03 出口量当月「-」、累计 0.6，同比印「不適用」），
   有时是「不适用」（2012 年进口量的上年列，中文版印「-」、英文版同一格印「N/A」；2020-08 的「--」同理）。
   台账原样存成 `-` / `NA`，宽表一律**留空**、不写 0 —— 宽表只放公告里印成数字的格子。

2. **繁简混排**：表格行名有时是简体（2014 年那批）、有时是繁体；早年 PDF 还把每个字拆开
   （「商 品 煤 產 量」）。`_norm()` 先删全部空白、再做一张最小繁→简映射，然后按关键词认行。
   「其中：黃驊港」里的「黃」是繁体 U+9EC3，不在映射里就会整行认不出（建库时踩过）。

3. **每一行都过一道区间核对，版式认错 / 串列会当场炸**：官方同比印到 0.1%，当月值与上年值
   印到 0.1（或 0.01），所以「本行两数自算的同比」有一个由舍入决定的**可行区间**
   [(cur−h)/(py+h)−1, (cur+h)/(py−h)−1]（h = 末位半格）。官方同比 ± 0.05pp 必须与这个区间相交，
   否则判「这一行的列序 / 数字不对」并抛异常。229 期全部过（例外清单见 `_YOY_KNOWN`）。

4. **PDF 字距会把一个数拆碎**（pdfplumber 的 layout 文本；pdftotext 读得出完整的数）：
   2010-03 中英两版的总发电量上年累计都抽成「2 1 .1 7」（=21.17），2017-12 英文版聚丙烯同比抽成
   「(10. 5)」。`_defrag()` 只认这两种实测形态、在取数前整行替换；修完仍对不上版式的行
   （中文版）退回英文版同一行并在台账 `src` 列记 `en`（建库时 0 行），两版都对不上就报问题。
   修错了也逃不掉：中英逐格比 + 口径坑 3 的区间核对。

4b. **「--」也是空值**（2020-08 发电两行的上年累计）。它曾让整行被当成纯行名行静默跳过 ——
   中英两版一起漏，逐格核对看不出。现在 `parse_zh()` 有一道护栏：表格行范围内认出了某个指标的
   行名、却没有读到那一行数字 → 抛异常。

5. **重述只存在于「上年」那几列**：公司每逢资产注入都追溯调整上年同期（见 docs/verify/shenhua.md
   的断点表），新公告的「上年同月」不等于去年那份公告印的「当月」。宽表**从不改写**任何一期
   自己那份公告印的当月值；最近一次重述（2026-04）用切列吸收（见 SCOPE_SPLITS 上方的注释）。
   `update()` 遇到新一期的「上年同月」≠ 宽表 M−12（又一次重述，且不在已切的那段里）时，
   数据照落、经 `DEGRADED` 报腿级警报（计入 monthly_run 末行失败清单），要人去加一段切列 ——
   不抛，因为数仍是官方原值；不只打印，因为不切列的话汇总表自算同比要错 12 个月。

6. **重述体检（已入库值被官方改了）**：宽表里已有的月份，若同一份公告（同一文件号）重抓出来
   的数变了，抛异常、不写入 —— 那是解析器变了或源件被替换了，要人看。台账只增不改、宽表由台账
   推出，所以 `update()` 还逐格比「重推前后的宽表」：已有的格子变了就抛，只许新增空格子。
   2014-03 那期披露易上有两份（16:27 与 19:01 各一份，中英各两份，表格数字逐格相同，建库时比过）；
   取先上载的那份。

7. **列名里的单位是官方原文的单位，不做「统一成吨」之类的换算**：煤化工 2026-06 起从
   聚乙烯 / 聚丙烯（千吨）改报聚烯烃 / 油品 / 甲醇 / 乙二醇（万吨），是两组不同的列，
   不是同一列换了单位；「千吨 ×0.1 = 万吨」那种拼接不做。
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import os
import unicodedata
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TICKER = 'shenhua'
HK_ORIGIN = 'https://www1.hkexnews.hk'
HK_SEARCH = HK_ORIGIN + '/search/titleSearchServlet.do'
HK_STOCK_ID = 9124                 # 披露易内部编号（/search/prefix.do?name=01088 查得）
START_MONTH = '2007-09'
_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
_MIN_PDF = 20_000                   # 229 期最小的一份 17 KB 是英文版；中文版最小 ~60 KB

# ── 指标：台账键 → (宽表列名, 宽表单位, 认行关键词正则（繁简归一之后）) ─────────────
# 顺序 = 认行时的优先级（更具体的在前：「黄骅港」行的行名里也有「下水煤」）。
IND = [
    ('pe',          'pe_sales_kt',          '千吨',     r'聚乙烯'),
    ('pp',          'pp_sales_kt',          '千吨',     r'聚丙烯'),
    ('polyolefin',  'polyolefin_sales_10kt', '万吨',    r'聚烯烃'),
    # 2020-01/02 两期印的是「聚烯烴產品銷售量（千噸）」（聚乙烯 + 聚丙烯合并报），
    # 认行时先认成 polyolefin、再按单位改判成这一条（见 parse_zh）。这里的正则永不先命中。
    ('polyolefin_kt', 'polyolefin_sales_kt', '千吨',   r'(?!)'),
    ('oil',         'oil_sales_10kt',       '万吨',     r'油品'),
    ('methanol',    'methanol_sales_10kt',  '万吨',     r'甲醇'),
    ('meg',         'meg_sales_10kt',       '万吨',     r'乙二醇'),
    ('huanghua',    'huanghua_mt',          '百万吨',   r'黄骅'),
    ('tianjin',     'tianjin_mt',           '百万吨',   r'天津'),
    ('seaborne',    'seaborne_mt',          '百万吨',   r'港口装煤量|下水煤'),
    ('ship_vol',    'ship_vol_mt',          '百万吨',   r'航运货运量'),
    ('ship_tnm',    'ship_tnm_bn',          '十亿吨海里', r'航运周转量'),
    ('rail',        'rail_tkm_bn',          '十亿吨公里', r'铁路'),
    ('power_gen',   'power_gen_bnkwh',      '十亿千瓦时', r'总发电量'),
    ('power_sold',  'power_sold_bnkwh',     '十亿千瓦时', r'总售电量'),
    ('coal_prod',   'coal_prod_mt',         '百万吨',   r'商品煤产量'),
    ('export',      'coal_export_mt',       '百万吨',   r'出口'),
    ('import',      'coal_import_mt',       '百万吨',   r'进口'),
    ('self_coal',   'coal_self_mt',         '百万吨',   r'自产煤'),
    ('purch_coal',  'coal_purch_mt',        '百万吨',   r'外购煤'),
    ('coal_sales',  'coal_sales_mt',        '百万吨',   r'煤炭销售量'),
]
IND_COL = {k: c for k, c, _, _ in IND}
IND_UNIT = {k: u for k, _, u, _ in IND}
# 宽表列序（页面读它；按业务排，与公告 2019-03 起的四段同序）
COL_ORDER = ['coal_prod', 'coal_sales', 'self_coal', 'purch_coal', 'export', 'import',
             'rail', 'seaborne', 'huanghua', 'tianjin', 'ship_vol', 'ship_tnm',
             'power_gen', 'power_sold',
             'pe', 'pp', 'polyolefin_kt', 'polyolefin', 'oil', 'methanol', 'meg']

# ── 口径分段（重述断点）────────────────────────────────────────────────────
# 公司在资产注入后**追溯调整上年同期**（重述），于是「当月 ÷ 去年同月那份公告印的数 − 1」
# 与官方同比不再是一回事。宽表因此在**最近一次**这类断点处把受影响的指标切成两列：
#   <列>         断点之前每一期公告印的当月值（旧口径，断点前一个月止）
#   <列>_sYYMM   断点起的新口径：断点起每一期的当月值 + 断点之后各期公告「上年同月（已重述）」
#                那一格回填到 M−12 —— 两类都是官方印出来的数，同一个口径。
# 这样新口径那一列里「当月 ÷ 12 个月前」逐格等于官方同比（舍入以内），页面的汇总表与任何
# 自算同比都不会再拿新口径去除旧口径。断点之前那几次重述（2012-04、2015-10、2025-02 …）
# 没有切列：那些窗口的自算同比页面上一处都不画（见 build/specs/shenhua.py 文件头）。
# ⚠ 切列只登记**有重述**的指标：2026-04 那次，铁路周转量与两港装船量的「上年同月」与原值逐格相同
#   （未重述），不切。
SCOPE_SPLITS = [
    ('2026-04', 's2604', {'coal_prod', 'coal_sales', 'ship_vol', 'ship_tnm',
                          'power_gen', 'power_sold', 'pe', 'pp'}),
]
# 断点之后才出现的指标（整列本来就是新口径）：「上年同月（已重述）」同样回填进本列。
POST_SPLIT_BORN = {'polyolefin', 'oil', 'methanol', 'meg'}
# 官方「当月同比（%）」原样入宽表的指标（页面「官方公布同比」几张图读它们）
YOY_IND = ['coal_prod', 'coal_sales', 'rail', 'huanghua', 'tianjin', 'ship_vol', 'ship_tnm',
           'power_gen', 'power_sold', 'pe', 'pp']


def yoy_col(ind):
    return f'{ind}_yoy_pct'


def split_col(ind, sfx):
    return f'{IND_COL[ind]}_{sfx}'


def target_col(ind, month):
    """这一期公告的当月值落宽表哪一列。"""
    for m0, sfx, inds in reversed(SCOPE_SPLITS):
        if ind in inds and month >= m0:
            return split_col(ind, sfx)
    return IND_COL[ind]


def py_fill_col(ind, month):
    """这一期公告的「上年同月」回填到 M−12 的哪一列；不回填返回 None。"""
    for m0, sfx, inds in reversed(SCOPE_SPLITS):
        if ind in inds and month >= m0:
            return split_col(ind, sfx)
    if ind in POST_SPLIT_BORN:
        return IND_COL[ind]
    return None


def _columns():
    out = ['month']
    for k in COL_ORDER:
        out.append(IND_COL[k])
        for _m0, sfx, inds in SCOPE_SPLITS:
            if k in inds:
                out.append(split_col(k, sfx))
    return out + [yoy_col(k) for k in YOY_IND]


COLUMNS = _columns()
ANN_COLUMNS = ['month', 'ind', 'label_pub', 'unit_pub', 'layout', 'cur', 'cum', 'py', 'py_cum',
               'yoy', 'yoy_cum', 'ref', 'src', 'doc', 'hk_posted']

# 原文单位 → (宽表单位, 换算系数)。只有发电那一处要换，其余必须与宽表单位逐字相同。
UNIT_CONV = {'亿千瓦时': ('十亿千瓦时', 0.1)}
_UNITS = ['十亿吨海里', '十亿吨公里', '十亿千瓦时', '亿千瓦时', '百万吨', '万吨', '千吨']

# 表格版式：一行的数从左到右各是什么（见模块 docstring）
_LAYOUTS = {
    'M6': ('cur', 'cum', 'py', 'py_cum', 'yoy', 'yoy_cum'),
    'M4': ('cur', 'cum', 'py', 'py_cum'),
    'M3': ('cur', 'py', 'yoy'),
    'A6': ('cum', 'cur', 'py_cum', 'py', 'yoy_cum', 'yoy'),
    'D4': ('cur', 'cum', 'py_cum', 'yoy_cum'),
    'Q3': ('cum', 'py_cum', 'yoy_cum'),
    'R3': ('cur', 'ref', 'ref_chg'),
}

# 区间核对（口径坑 3）的已知例外：{(月份, 指标, 字段): 原因}。只收**官方自己印错 / 口径不同**
# 的格子，解析问题不许进这张表。
_YOY_KNOWN = {}


class ShenhuaFetchError(RuntimeError):
    pass


# ── 文本工具 ─────────────────────────────────────────────────────────────
_T2S = str.maketrans({
    '產': '产', '産': '产', '銷': '销', '鐵': '铁', '運': '运', '輸': '输', '週': '周',
    '轉': '转', '驊': '骅', '黃': '黄', '碼': '码', '頭': '头', '裝': '装', '貨': '货',
    '發': '发', '電': '电', '總': '总', '烴': '烃', '噸': '吨', '萬': '万', '億': '亿',
    '時': '时', '進': '进', '計': '计', '標': '标', '單': '单', '變': '变', '適': '适',
    '購': '购', '數': '数', '據': '据', '內': '内', '統': '统', '結': '结', '華': '华',
    '營': '营', '舊': '旧', '並': '并', '幷': '并', '經': '经', '長': '长', '參': '参',
    '稱': '称', '項': '项', '後': '后', '來': '来', '對': '对', '於': '于', '為': '为',
    '（': '(', '）': ')', '：': ':', '，': ',', '％': '%', '－': '-', '—': '-', '–': '-',
    '−': '-', '　': ' ',
})


def _norm(s):
    # NFKC 先行：个别期次的 PDF 把「數」抽成兼容区字形 U+F969，不归一就认不出「運營數據」
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', s).translate(_T2S))


def _dedup4(s):
    """粗体被渲染成四遍叠印的那几期（2011-07 的「運運運運營營營營指指指指標標標標」）→ 去叠印。
    只用于认表头 / 认标题，不用于取数（数字里 1111 这种是真值）。"""
    return re.sub(r'(.)\1{3}', r'\1', s)


# PDF 字距把一个数拆碎的两种实测形态（口径坑 4）。只在取数前对整行做这两处替换：
#   「2 1 .1 7」= 21.17（2010-03 中文、英文两版同一格）、「(10. 5)」= (10.5)（2017-12 英文版）。
_FRAG = [
    (re.compile(r'(?<![\d.,])(\d) (\d) \.(\d) (\d)(?![\d.,])'), r'\1\2.\3\4'),
    (re.compile(r'(\d)\. (\d+\))'), r'\1.\2'),
]


def _defrag(line):
    for rx, to in _FRAG:
        line = rx.sub(to, line)
    return line


_NUM_RE = re.compile(r'^\(?-?\d[\d,]*\.?\d*\)?%?$')
_NA_TOK = {'不适用': 'NA', 'N/A': 'NA', 'N.A.': 'NA', 'NA': 'NA', '-': '-', '—': '-', '--': '-'}


def _clean_tok(t):
    # NFKC：「不適用」的「不」在部分期次里是兼容区字形 U+F967（口径坑 2）
    return unicodedata.normalize('NFKC', t).translate(_T2S).rstrip('注*').strip()


def _is_num(t):
    t2 = _clean_tok(t)
    return t2 in _NA_TOK or bool(_NUM_RE.match(t2))


def _canon(t):
    """一个数字格 → 规范字符串：'(2.3)' → '-2.3'，'1,200.' → '1200'，'17.5%' → '17.5'，
    '-' / '不適用' → '-' / 'NA'。保留原文小数位（区间核对要用末位）。"""
    t2 = _clean_tok(t)
    if t2 in _NA_TOK:
        return _NA_TOK[t2]
    neg = t2.startswith('(') and t2.endswith(')')
    t2 = t2.strip('()').replace(',', '').rstrip('%')
    if t2.endswith('.'):
        t2 = t2[:-1]
    if t2.startswith('-'):
        neg, t2 = True, t2[1:]
    float(t2)                                   # 不是数就让它炸
    return ('-' + t2) if neg and float(t2) != 0 else t2


def _val(s):
    return None if s in ('', '-', 'NA', None) else float(s)


def _half(s):
    """末位半格：'26.8' → 0.05，'24.69' → 0.005，'1100' → 0.5。"""
    if s in ('', '-', 'NA', None):
        return None
    d = len(s.split('.')[1]) if '.' in s else 0
    return 0.5 * 10 ** (-d)


def _split_row(line):
    toks = line.split()
    k = len(toks)
    while k > 0 and _is_num(toks[k - 1]):
        k -= 1
    return ' '.join(toks[:k]), toks[k:]


def _find(rx_list, lab):
    for k, _, _, rx in rx_list:
        if re.search(rx, lab):
            return k
    return None


def _label(labn):
    """行名原文（繁简归一、去序号、去单位）—— 台账里留着它，指标改名 / 改口径一眼看得出。"""
    s = re.sub(r'^[\d.、]+|^\([一二三四]\)', '', labn)
    s = re.sub(r'\(?(' + '|'.join(_UNITS) + r')\)?', '', s)
    return re.sub(r'注\d?$|\d$', '', s)


def _find_unit(lab):
    for u in _UNITS:
        if u in lab:
            return u
    return None


# ── 网络 ─────────────────────────────────────────────────────────────────
def _get(url, *, tries=3, min_bytes=0):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': _UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read()
            if len(b) < min_bytes:
                raise ShenhuaFetchError(f'{url} 只有 {len(b)} 字节（下限 {min_bytes}）')
            return b
        except Exception as e:                                   # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise ShenhuaFetchError(f'GET {url} 失败：{last!r}')


def hk_list(d0, d1, lang):
    """披露易 01088 在 [d0, d1] 内的全部文件（不按标题筛）。lang='ZH' | 'E'。"""
    q = {'sortDir': 0, 'sortByOptions': 'DateTime', 'category': 0, 'market': 'SEHK',
         'stockId': HK_STOCK_ID, 'documentType': -1, 'fromDate': d0.strftime('%Y%m%d'),
         'toDate': d1.strftime('%Y%m%d'), 'title': '', 'searchType': 0, 't1code': -2,
         't2Gcode': -2, 't2code': -2, 'rowRange': 2000, 'lang': lang}
    raw = _get(HK_SEARCH + '?' + urllib.parse.urlencode(q))
    d = json.loads(raw.decode('utf-8'))
    res = d.get('result')
    if not res or res == 'null':
        return []
    out = json.loads(res)
    for x in out:
        x['posted'] = _dt.datetime.strptime(x['DATE_TIME'], '%d/%m/%Y %H:%M')
    return out


def _is_candidate(doc, lang):
    t = re.sub(r'\s+', ' ', doc['TITLE']).upper()
    if not doc['FILE_LINK'].lower().endswith('.pdf'):
        return False
    if lang == 'ZH':
        return ('運營數據' in doc['TITLE'] or '运营数据' in doc['TITLE']
                or doc['TITLE'].strip() in ('海外監管公告', '海外监管公告'))
    return 'OPERATIONAL DATA' in t or t.strip() == 'OVERSEAS REGULATORY ANNOUNCEMENT'


def pdf_path(cache_dir, link):
    return os.path.join(cache_dir, TICKER, link.rsplit('/', 1)[-1])


def fetch_pdf(cache_dir, link):
    p = pdf_path(cache_dir, link)
    if os.path.exists(p) and os.path.getsize(p) >= _MIN_PDF // 2:
        return p
    b = _get(HK_ORIGIN + link, min_bytes=10_000)
    if not b.startswith(b'%PDF'):
        raise ShenhuaFetchError(f'{link} 不是 PDF（开头 {b[:16]!r}）')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as f:
        f.write(b)
    return p


def pdf_text(path):
    """PDF 全文（pdfplumber 的 layout 文本）。抽取结果按 PDF 的 sha256 缓存在旁边的 .txt，
    回填时 460 份不必每次重抽；PDF 一变（源件被替换）哈希就变，旧 .txt 不会被误用。"""
    import hashlib
    with open(path, 'rb') as f:
        h = hashlib.sha256(f.read()).hexdigest()[:16]
    tp = f'{path}.{h}.txt'
    if os.path.exists(tp):
        with open(tp, encoding='utf-8') as f:
            return f.read()
    import pdfplumber                          # 延迟 import：报错更好定位
    with pdfplumber.open(path) as pdf:
        t = '\n'.join((pg.extract_text(layout=True) or '') for pg in pdf.pages)
    with open(tp, 'w', encoding='utf-8') as f:
        f.write(t)
    return t


# ── 认月份 ───────────────────────────────────────────────────────────────
_EN_MON = {m: i + 1 for i, m in enumerate(
    ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST',
     'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'])}


def zh_month(text):
    """中文版正文第一屏 → ('YYYY-MM', 期别)。不是运营数据公告返回 (None, None)。

    期别：'m' 单月（含「12月份及全年」「9月份及前三季度」这类带累计的）、'q1' 只有一季度、
    'h1' 只有上半年（2008-06 的标题「2008年上半年」实际表里有 6 月单月，按 'm' 处理）。
    """
    head = _dedup4(_norm('\n'.join(text.splitlines()[:40])))
    # 「月」字有时被排到上一行（2023-07：「月 / 2023 年 7 份」），有时标题写「11月」不写「11月份」：
    # 先删掉全部「月」再认。
    h2 = head.replace('月', '')
    m = re.search(r'(\d{4})年(\d{1,2})份?(?:及[^主]{0,10})?主要运营数据公告', h2)
    if m:
        return f'{int(m.group(1))}-{int(m.group(2)):02d}', 'm'
    m = re.search(r'(\d{4})年(一季度|上半年)主要运营数据公告', head)
    if m:
        return (f'{m.group(1)}-03', 'q1') if m.group(2) == '一季度' else (f'{m.group(1)}-06', 'h1')
    return None, None


def en_month(text):
    # 去掉全部空白再认：早年英文版标题常被抽成「MAJOROPERATIONALDATAOF」一串
    head = re.sub(r'\s+', '', '\n'.join(text.splitlines()[:40])).upper()
    if 'MAJOROPERATIONALDATA' not in head:
        return None
    i = head.index('OPERATIONALDATA')
    tail = head[i:i + 120]
    yr = re.search(r'(20\d\d)', tail)
    mon = re.search(r'(' + '|'.join(_EN_MON) + r')', tail.replace(' ', ''))
    if yr and mon:
        return f'{yr.group(1)}-{_EN_MON[mon.group(1)]:02d}'
    m = re.search(r'(FIRSTQUARTER|FIRSTHALF)', tail)
    if yr and m:
        return f'{yr.group(1)}-' + ('03' if 'QUARTER' in m.group(1) else '06')
    return None


# ── 解析 ─────────────────────────────────────────────────────────────────
def _table_lines(text):
    lines = [l for l in text.splitlines() if l.strip()]
    start = next((i for i, l in enumerate(lines) if '运营指标' in _dedup4(_norm(l))), None)
    if start is None:
        raise ShenhuaFetchError('找不到「運營指標」表头')
    return lines, start


def _detect_layout(header_n, ntok, period):
    if '月均参考值' in header_n:
        return 'R3'
    if ntok == 6:
        return 'A6' if '年度同' in header_n else 'M6'
    if ntok == 4:
        return 'D4' if '全年' in header_n or re.search(r'\d{4}年\d{4}年增长', header_n) else 'M4'
    if ntok == 3:
        return 'Q3' if period == 'q1' else 'M3'
    raise ShenhuaFetchError(f'一行 {ntok} 个数，没有对应的版式')


def parse_zh(text, hint=None):
    """中文版公告 → {'month', 'layout', 'rows': {ind: {字段: 规范字符串}}, 'units': {ind: 原文单位},
    'bad': [行名…]（数字个数对不上版式的行，交给英文版补）, 'numrows': [[tok…]…]}。"""
    month, period = zh_month(text)
    if month is None and hint and '主要运营数据公告' in _norm('\n'.join(text.splitlines()[:40])):
        # 标题字形被 PDF 排乱（2023-08「年月份主要運營數據公告2023」、2023-10「年月202310份」）：
        # 正文确认是运营数据公告，月份取披露易标题（hint 来自 zh_month(标题)）。
        month, period = hint
    if month is None:
        raise ShenhuaFetchError('正文里认不出「YYYY年M月份主要運營數據公告」')
    lines, start = _table_lines(text)
    raw, pending, header = [], [], []
    named = []             # 表格区里出现过行名的指标（护栏：认出了行名却没读到数 → 抛）
    last_row = -1
    for i in range(max(0, start - 4), len(lines)):
        l = lines[i]
        n = _norm(l)
        if raw and (n.startswith('注') or '内部统计' in n or '内部结算统计' in n):
            break
        lab, nums = _split_row(_defrag(l))
        if i >= start and len(nums) >= 3:
            labn = _norm(lab)
            ind = _find(IND, labn)
            if ind is None:
                ind = _find(IND, _norm(''.join(pending)) + labn)
            unit = _find_unit(labn) or _find_unit(_norm(''.join(pending)))
            if unit is None and i + 1 < len(lines):
                # 行名折行、单位落在下一行（「（ 十 億 噸 公 里）」）：只认**纯行名行**，
                # 下一行若自带数字或指标关键词，那是下一个指标，不是这一行的尾巴
                nl, nn = _split_row(lines[i + 1])
                if len(nn) < 3 and _find(IND, _norm(nl)) is None:
                    unit = _find_unit(_norm(nl))
            if ind == 'polyolefin' and unit == '千吨':
                ind = 'polyolefin_kt'          # 2020-01/02 那两期的「聚烯烴產品銷售量（千噸）」
            raw.append((ind, unit, nums, l.strip(), _label(labn if _find(IND, labn) else
                                                          _norm(''.join(pending)) + labn)))
            pending = []
            last_row = i
        else:
            if not raw:
                header.append(n)
            pending = (pending + [lab or l])[-3:]
            if i > start and ',' not in n and not re.match(r'^\d{4}年', n):   # 说明段的句子不算行名
                k = _find(IND, n)
                if k:
                    named.append((i, k))
    if not raw:
        raise ShenhuaFetchError(f'{month}: 表里一行数字都没读到')
    from collections import Counter
    ntok = Counter(len(x[2]) for x in raw).most_common(1)[0][0]
    labels = {x[0]: x[4] for x in raw}
    layout = _detect_layout(''.join(header), ntok, period)
    fields = _LAYOUTS[layout]
    rows, units, bad, numrows = {}, {}, [], []
    for ind, unit, nums, line, _lab in raw:
        if ind is None:
            raise ShenhuaFetchError(f'{month}: 认不出这一行是什么指标：{line!r}')
        if ind in rows:
            raise ShenhuaFetchError(f'{month}: 指标 {ind} 出现两次：{line!r}')
        toks = list(nums)
        # 行名末尾的脚注号（「（十億噸公里）1」）会被当成第一个数：恰好多一个、且是不带小数的
        # 个位整数时剥掉。别的多余一律不猜。
        if len(toks) == len(fields) + 1 and re.fullmatch(r'\d', _clean_tok(toks[0])):
            toks = toks[1:]
        numrows.append([_canon(t) for t in toks])
        if len(toks) != len(fields):
            bad.append(ind)
            rows[ind] = {}
        else:
            rows[ind] = dict(zip(fields, (_canon(t) for t in toks)))
        units[ind] = unit
    # 只看表格行范围内（最后一行数字之后再宽一行，给折行的单位）的行名；表后的说明段
    # （「…外購煤銷量下降…」「…聚烯烴…」）提到指标名不算
    named = {k for i, k in named if i <= last_row + 1}
    lost = named - set(rows) - ({'polyolefin'} if 'polyolefin_kt' in rows else set())
    if lost:
        # 2020-08 的「--」曾经就这样把整行发电数据静默吞掉（那时 '--' 不认作空值，行尾一个数都
        # 剥不出来，这一行被当成纯行名行跳过 —— 中英两版一起漏，交叉核对也看不出来）
        raise ShenhuaFetchError(f'{month}: 行名认出了 {sorted(lost)}，却一行数字都没读到')
    return {'month': month, 'layout': layout, 'rows': rows, 'units': units, 'labels': labels,
            'bad': bad, 'numrows': numrows, 'order': [x[0] for x in raw]}


def numstream_en(text):
    """英文版 → 表里全部数字格，按阅读顺序摊平成一条流（规范字符串）。只用于与中文版逐格对照：
    两版是同一张表，格序相同，所以不认行名。

    为什么摊平而不按行：英文版行名长，pdfplumber 常把一行数字拆在两行上
    （2008-02「…self-owned 10.4」下一行才是「9.7 7.2」），按行切会把行数对错。
    摊平之后按中文版的版式宽度切段即可。丢掉三类不是表格数据的数字：
    孤立的个位整数（页码、行名后的脚注号「1」）、表头年份（「2009 2008」，2009-12 那期还有
    带脚注号粘连的「20082」）、
    以及「100 million kwh」里的 100。
    """
    lines = [l for l in text.splitlines() if l.strip()]
    start = next((i for i, l in enumerate(lines)
                  if 'indicators' in l.lower().replace(' ', '')), None)
    if start is None:
        raise ShenhuaFetchError('英文版找不到 Operational Indicators 表头')
    out = []
    for l in lines[start:]:
        low = l.lower()
        if out and ('internal statistic' in low or 'internal settled' in low
                    or re.match(r'^\s*notes?\s*[:：1(]', low)):
            break
        l2 = _defrag(re.sub(r'100\s*million', '', l, flags=re.I))
        _, nums = _split_row(l2)
        for t in nums:
            c = _clean_tok(t)
            # 表头年份（「2009」，或带脚注号粘连成「20082」）
            if re.fullmatch(r'\d', c) or re.fullmatch(r'(19|20)\d\d\d?', c):
                continue
            out.append(_canon(t))
    return out


def _same_cell(z, e, factor):
    """中文版一格与英文版同一格是否相等。'-' 与 'NA' 互认（两版对「无 / 不适用」的写法不同，
    2012 年进口量上年列中文印「-」、英文印「N/A」）；数值按数值比，中文版若是「亿千瓦时」
    则先 ×0.1 再比（英文版 2007-10 起印 billion kwh）。"""
    if z in ('-', 'NA') or e in ('-', 'NA'):
        return z in ('-', 'NA') and e in ('-', 'NA')
    zf, ef = float(z), float(e)
    return abs(zf - ef) < 1e-9 or abs(zf * factor - ef) < 1e-9


# ── 区间核对（口径坑 3） ─────────────────────────────────────────────────
def yoy_feasible(cur, py, yoy):
    """官方同比 yoy（%，字符串）与 cur/py 的舍入可行区间相交 → True。算不了 → None。"""
    c, p, y = _val(cur), _val(py), _val(yoy)
    if c is None or p is None or y is None:
        return None
    hc, hp, hy = _half(cur), _half(py), _half(yoy)
    if p - hp <= 0:
        return None
    lo = ((c - hc) / (p + hp) - 1) * 100
    hi = ((c + hc) / (p - hp) - 1) * 100
    return not (y + hy + 1e-9 < lo or y - hy - 1e-9 > hi)


def check_doc(doc):
    """单份公告内部的核对：每一行的当月同比、累计同比都要落在舍入可行区间里。返回问题清单。"""
    probs = []
    for ind, r in doc['rows'].items():
        for a, b, y in (('cur', 'py', 'yoy'), ('cum', 'py_cum', 'yoy_cum')):
            if y not in r:
                continue
            ok = yoy_feasible(r.get(a), r.get(b), r.get(y))
            if ok is False and (doc['month'], ind, y) not in _YOY_KNOWN:
                probs.append(f"{doc['month']} {ind} {y}: 官方 {r[y]}% vs {r.get(a)}/{r.get(b)}")
    return probs


# ── 台账 / 宽表读写 ──────────────────────────────────────────────────────
def _read_csv(p, cols):
    if not os.path.exists(p):
        return []
    with open(p, newline='', encoding='utf-8') as f:
        rd = csv.DictReader(f)
        if rd.fieldnames != cols:
            raise ShenhuaFetchError(f'{p} 列不对：{rd.fieldnames} != {cols}')
        return list(rd)


def _write_csv(p, cols, rows):
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator='\n')
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, '') for c in cols})


def _wide_cell(ind, unit_pub, s):
    """台账一格（原文单位）→ 宽表一格（宽表单位）。"""
    if s in ('', '-', 'NA', None):
        return ''
    want = IND_UNIT[ind]
    if unit_pub == want or unit_pub is None:
        return s
    if unit_pub in UNIT_CONV and UNIT_CONV[unit_pub][0] == want:
        f = UNIT_CONV[unit_pub][1]
        d = (len(s.split('.')[1]) if '.' in s else 0) + 1
        return f'{float(s) * f:.{d}f}'
    raise ShenhuaFetchError(f'{ind} 原文单位 {unit_pub!r} 与宽表单位 {want!r} 对不上，也没有登记换算')


def ann_rows(doc, src_link, posted):
    out = []
    for ind in doc['order']:
        r = doc['rows'][ind]
        out.append({'month': doc['month'], 'ind': ind, 'label_pub': doc['labels'].get(ind, ''),
                    'unit_pub': doc['units'].get(ind) or '',
                    'layout': doc['layout'], 'cur': r.get('cur', ''), 'cum': r.get('cum', ''),
                    'py': r.get('py', ''), 'py_cum': r.get('py_cum', ''), 'yoy': r.get('yoy', ''),
                    'yoy_cum': r.get('yoy_cum', ''), 'ref': r.get('ref', ''),
                    'src': r.get('_src', 'zh'), 'doc': src_link.rsplit('/', 1)[-1],
                    'hk_posted': posted.strftime('%Y-%m-%d %H:%M')})
    return out


def _shift(month, k):
    y, m = int(month[:4]), int(month[5:]) + k
    y += (m - 1) // 12
    return f'{y}-{(m - 1) % 12 + 1:02d}'


def build_wide(ann):
    """台账 → 宽表（确定性推导，宽表里没有一格不是从台账来的）。返回 (行列表, 冲突清单)。

    三类格子：
      · 当月值   每期公告的「当月」落 target_col()（新口径段落 <列>_sYYMM）；
      · 回填值   新口径段内各期公告的「上年同月（已重述）」落 py_fill_col() 那一列的 M−12；
      · 官方同比 YOY_IND 那几条的「当月同比」原样落 <ind>_yoy_pct。
    冲突 = 回填值撞上那一格已有的、不一样的数（同一口径段内又被重述了一次）。不覆盖，记下来。
    """
    months = sorted({r['month'] for r in ann})
    rows = {m: {'month': m} for m in months}
    for r in ann:
        ind, m = r['ind'], r['month']
        if ind not in IND_COL:
            continue
        v = _wide_cell(ind, r['unit_pub'] or None, r['cur'])
        if v:
            rows[m][target_col(ind, m)] = v
        if ind in YOY_IND and r['yoy'] not in ('', '-', 'NA'):
            rows[m][yoy_col(ind)] = r['yoy']
    conflicts = []
    for r in sorted(ann, key=lambda r: r['month']):
        ind, m = r['ind'], r['month']
        col = py_fill_col(ind, m) if ind in IND_COL else None
        pm = _shift(m, -12)
        if not col or pm not in rows:
            continue
        v = _wide_cell(ind, r['unit_pub'] or None, r['py'])
        if not v:
            continue
        old = rows[pm].get(col)
        if old and float(old) != float(v):
            conflicts.append(f'{m} 公告的上年同月 {ind}={v}，而宽表 {col}@{pm} 已是 {old}')
        elif not old:
            rows[pm][col] = v
    return [rows[m] for m in months], conflicts


def restatements(ann, wide):
    """「上年同月」≠ 宽表里同一列 M−12 的当月值的全部格子（只比**不回填**的那些列）。
    返回 [(月份, 指标, 原值, 公告印的上年同月)]。"""
    w = {r['month']: r for r in wide}
    out = []
    for r in ann:
        ind, m = r['ind'], r['month']
        if ind not in IND_COL or py_fill_col(ind, m):
            continue
        base = w.get(_shift(m, -12), {}).get(target_col(ind, m), '')
        py = _wide_cell(ind, r['unit_pub'] or None, r['py'])
        if base and py and float(base) != float(py):
            out.append((m, ind, base, py))
    return out


# ── 一份公告：下载中英两版 → 解析 → 交叉核对 ─────────────────────────────
def _title_hint(zh_doc):
    t = zh_doc['TITLE']
    if '運營數據' not in t and '运营数据' not in t:
        return None
    m = zh_month(t if '公告' in t else t + '主要運營數據公告')
    return m if m[0] else None


def load_announcement(cache_dir, zh_doc, en_doc):
    """返回解析好的 doc（rows 里坏行已由英文版补齐），以及交叉核对的问题清单。"""
    zt = pdf_text(fetch_pdf(cache_dir, zh_doc['FILE_LINK']))
    hint = _title_hint(zh_doc)
    doc = parse_zh(zt, hint)
    if hint and hint[0] != doc['month']:
        raise ShenhuaFetchError(f"披露易标题说是 {hint[0]}，正文认出 {doc['month']}")
    probs = []
    stream = None
    if en_doc is not None:
        et = pdf_text(fetch_pdf(cache_dir, en_doc['FILE_LINK']))
        em = en_month(et)
        if em != doc['month']:
            probs.append(f"{doc['month']}: 英文版认出的月份是 {em}")
        stream = numstream_en(et)
    fields = _LAYOUTS[doc['layout']]
    w = len(fields)
    if stream is not None:
        n = len(doc['order'])
        # 表后的英文叙述段偶尔以数字结尾（「…increased by 10.1%」），会被摊进流的末尾；
        # 只取前 n×w 格。表**中间**混进杂数的话，后面每一格都会错位，逐格比对当场就响。
        if len(stream) < n * w:
            probs.append(f"{doc['month']}: 中文版 {n} 行 × {w} 格 = {n * w}，英文版摊平后只有 {len(stream)} 格")
        else:
            stream = stream[:n * w]
            for k, ind in enumerate(doc['order']):
                er = stream[k * w:(k + 1) * w]
                zr = doc['numrows'][k]
                factor = UNIT_CONV.get(doc['units'].get(ind), (None, 1.0))[1]
                if ind in doc['bad']:
                    doc['rows'][ind] = dict(zip(fields, er))
                    doc['rows'][ind]['_src'] = 'en'
                    continue
                pct = {i for i, f in enumerate(fields) if f.startswith('yoy') or f == 'ref_chg'}
                for i, (z, e) in enumerate(zip(zr, er)):
                    if not _same_cell(z, e, 1.0 if i in pct else factor):
                        probs.append(f"{doc['month']} {ind} {fields[i]}: 中文版 {z} ≠ 英文版 {e}")
    for ind in doc['bad']:
        if not doc['rows'][ind]:
            probs.append(f"{doc['month']} {ind}: 中文版这一行数字个数对不上版式，英文版也没补上")
    probs += check_doc(doc)
    return doc, probs


def _pair_en(zh_doc, en_docs):
    """同一份公告的英文版：同一上载时刻（分钟）、文件号相邻的那份。"""
    same = [e for e in en_docs if e['DATE_TIME'] == zh_doc['DATE_TIME']]
    if not same:
        return None
    zn = re.sub(r'\D', '', zh_doc['FILE_LINK'].rsplit('/', 1)[-1])
    return min(same, key=lambda e: abs(int(re.sub(r'\D', '', e['FILE_LINK'].rsplit('/', 1)[-1]) or 0)
                                       - int(zn or 0)))


def discover(cache_dir, d0, d1):
    """[d0, d1] 内全部运营数据公告 → {月份: (zh_doc, en_doc)}；泛称标题的开 PDF 认月份。
    同一月份有两份时取先上载的（口径坑 6）。"""
    zh = [x for x in hk_list(d0, d1, 'ZH') if _is_candidate(x, 'ZH')]
    en = [x for x in hk_list(d0, d1, 'E') if _is_candidate(x, 'E')]
    titled = [x for x in zh if '運營數據' in x['TITLE'] or '运营数据' in x['TITLE']]
    # 泛称标题（「海外監管公告」）一年几十份，逐份开 PDF 太重：只开**上载月里没有任何一份
    # 带「運營數據」标题公告**的那几个月的泛称公告。一期公告固定在次月上载、一个月只上载一期，
    # 所以「这个上载月已经有带标题的那份」⇒ 本月那期已找到，泛称的那些不可能再是它。
    covered = {(x['posted'].year, x['posted'].month) for x in titled}
    generic = [x for x in zh if x not in titled
               and (x['posted'].year, x['posted'].month) not in covered]
    found = {}
    for x in sorted(titled + generic, key=lambda x: x['posted']):
        if x in titled:
            m, _ = zh_month(x['TITLE'] if '公告' in x['TITLE'] else x['TITLE'] + '主要運營數據公告')
        else:
            m = None
        if m is None:
            m, _ = zh_month(pdf_text(fetch_pdf(cache_dir, x['FILE_LINK'])))
        if m is None or m in found:
            continue
        found[m] = (x, _pair_en(x, en))
    return found


# ── 对外接口 ─────────────────────────────────────────────────────────────
def _source_dates():
    import importlib.util
    spec = importlib.util.spec_from_file_location('source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def latest_month(cache_dir):
    """披露易上最新一期运营数据公告的数据月。只列清单、只在泛称标题时才开 PDF。"""
    today = _dt.date.today()
    found = discover(cache_dir, today - _dt.timedelta(days=75), today)
    if not found:
        raise ShenhuaFetchError('披露易近 75 天里没有任何一期运营数据公告（接口改版？）')
    return max(found)


# 腿级报警（协议见 monthly_run.LEG_ALERTS）：本家只有一条腿，用它报「数照常落库、但要人看」
# 的那一类事 —— 新一期的「上年同月」与宽表 M−12 对不上（公司又重述了），或回填撞上已有值。
# 数据照样发布（宽表里的每一格仍是官方原值），但汇总表的自算同比在之后 12 个月会拿新口径
# 除旧口径，所以必须响：要人去 SCOPE_SPLITS 加一段（见上方那段注释）。
DEGRADED = {}


def _doc_date(zh_doc):
    return (zh_doc['posted'].strftime('%Y-%m-%d'),
            f'披露易 01088 中文版 {zh_doc["FILE_LINK"].rsplit("/", 1)[-1]} '
            f'上载于 {zh_doc["DATE_TIME"]}（「{zh_doc["TITLE"].strip()}」）')


def update(series_dir, cache_dir):
    """把新月份追加进 series/shenhua_ann.csv（台账）并由台账重推 series/shenhua.csv，
    返回新增月份（升序）。

    幂等：没有新月份时两张表一个字节都不写。宽表里已有的格子一格都不许变（台账只增不改，
    宽表由台账推导 —— 变了就是解析器或推导规则变了，抛异常要人看）；允许新增的只有
    「新口径段回填 M−12」那一类空格子。重述只报警不阻断（见 DEGRADED 上方的说明）。
    """
    DEGRADED.clear()
    wide_p = os.path.join(series_dir, 'shenhua.csv')
    ann_p = os.path.join(series_dir, 'shenhua_ann.csv')
    wide = _read_csv(wide_p, COLUMNS)
    ann = _read_csv(ann_p, ANN_COLUMNS)
    if not wide or not ann:
        raise ShenhuaFetchError('series/shenhua*.csv 是空的 —— 本模块只做增量，'
                                '冷启动跑 `python3 fetch/shenhua.py --backfill --write`')
    last = max(r['month'] for r in ann)
    d0 = (_dt.date(int(last[:4]), int(last[5:]), 1) + _dt.timedelta(days=32)).replace(day=1)
    found = discover(cache_dir, d0, _dt.date.today())

    # 体检（口径坑 6）：最后一个已入库月份的那份中文版重解析一遍，逐格比台账
    old_last = [r for r in ann if r['month'] == last]
    p = os.path.join(cache_dir, TICKER, old_last[0]['doc'])
    if os.path.exists(p):
        redo = parse_zh(pdf_text(p), (last, 'm'))
        for r in old_last:
            got = redo['rows'].get(r['ind'], {})
            if r['src'] == 'zh' and any(got.get(f, '') != r[f] for f in ('cur', 'py', 'yoy')):
                raise ShenhuaFetchError(f'{last} {r["ind"]}: 台账与重解析不一致（{r} vs {got}）'
                                        ' —— 解析器变了？本次不写入')

    new = sorted(m for m in found if m > last)
    if not new:
        return []
    expect, add_ann, dates, warns = _shift(last, 1), [], {}, []
    for m in new:
        if m != expect:
            raise ShenhuaFetchError(f'新一期是 {m}，而台账最新是 {last}：中间缺 {expect}（漏抓？）')
        zh_doc, en_doc = found[m]
        doc, pr = load_announcement(cache_dir, zh_doc, en_doc)
        if en_doc is None:
            warns.append(f'{m}: 披露易上没找到同一时刻上载的英文版，本期没有逐格交叉核对')
        if pr:
            raise ShenhuaFetchError('新一期没过核对，本次不写入：\n  ' + '\n  '.join(pr))
        unknown = [k for k in doc['rows'] if k not in IND_COL]
        if unknown:
            raise ShenhuaFetchError(f'{m}: 公告里出现了宽表没有的指标 {unknown}（新增列要人工接）')
        add_ann += ann_rows(doc, zh_doc['FILE_LINK'], zh_doc['posted'])
        dates[m] = _doc_date(zh_doc)
        expect = _shift(m, 1)

    all_ann = ann + add_ann
    new_wide, conflicts = build_wide(all_ann)
    old = {r['month']: r for r in wide}
    for r in new_wide:
        o = old.get(r['month'])
        if not o:
            continue
        for c in COLUMNS:
            if o.get(c, '') and o.get(c, '') != r.get(c, ''):
                raise ShenhuaFetchError(f'宽表 {r["month"]} {c} 会从 {o[c]} 变成 {r.get(c, "")!r} '
                                        '—— 已入库的格子不许变，本次不写入')
    rest = [x for x in restatements(add_ann, new_wide) if x[0] in new]
    for m, ind, base, py in rest:
        DEGRADED[f'重述 {m} {ind}'] = (f'{m} 公告的上年同月 {py} ≠ {_shift(m, -12)} 自己那份公告的 {base}：'
                                      f'公司重述了上年同期，汇总表自算同比将拿新口径除旧口径 —— '
                                      f'在 fetch/shenhua.py 的 SCOPE_SPLITS 加一段')
    for c in [c for c in conflicts if any(c.startswith(m) for m in new)]:
        DEGRADED[f'回填冲突 {c[:7]}'] = c
    for w_ in warns:
        print(f'[shenhua][warn] {w_}')
    _write_csv(ann_p, ANN_COLUMNS, all_ann)
    _write_csv(wide_p, COLUMNS, new_wide)
    sd = _source_dates()
    for m in new:
        sd.record(series_dir, TICKER, m, dates[m][0], dates[m][1])
    return new


# ── 冷启动：全历史回填（不进 monthly_run） ──────────────────────────────────
def backfill(series_dir, cache_dir, d0=_dt.date(2007, 1, 1)):
    """列出 2007 年至今披露易上的全部运营数据公告，逐期解析、中英逐格核对、区间核对，
    返回 (月份, 宽表, 台账, 问题清单, 发布日)。"""
    today = _dt.date.today()
    found = {}
    for y in range(d0.year, today.year + 1):
        a, b = _dt.date(y, 1, 1), min(_dt.date(y, 12, 31), today)
        for m, v in discover(cache_dir, a, b).items():
            if m not in found or v[0]['posted'] < found[m][0]['posted']:
                found[m] = v
        time.sleep(0.5)
    months = sorted(found)
    all_ann, probs, dates = [], [], {}
    for m in months:
        zh_doc, en_doc = found[m]
        try:
            doc, pr = load_announcement(cache_dir, zh_doc, en_doc)
            if en_doc is None:
                pr.append(f'{m}: 没有配上英文版')
            probs += pr
            all_ann += ann_rows(doc, zh_doc['FILE_LINK'], zh_doc['posted'])
            dates[m] = _doc_date(zh_doc)
        except ShenhuaFetchError as e:
            probs.append(f'{m}: {e}')
    for a, b in zip(months, months[1:]):
        if _shift(a, 1) != b:
            probs.append(f'月份不连续：{a} 之后是 {b}')
    wide, conflicts = build_wide(all_ann)
    probs += [f'回填冲突：{c}' for c in conflicts]
    return months, wide, all_ann, probs, dates


def cadence(series_dir=None):
    """按 source_dates.csv 现印发布节奏（月末后第几天）。"""
    series_dir = series_dir or os.path.join(ROOT, 'series')
    with open(os.path.join(series_dir, 'source_dates.csv'), newline='', encoding='utf-8') as f:
        rows = [r for r in csv.DictReader(f) if r['ticker'] == TICKER]
    out = []
    for r in rows:
        y, m = int(r['month'][:4]), int(r['month'][5:])
        end = _dt.date(y, m, 1) + _dt.timedelta(days=32)
        end = end.replace(day=1) - _dt.timedelta(days=1)
        d = _dt.date.fromisoformat(r['source_date'])
        out.append((r['month'], (d - end).days))
    return out


if __name__ == '__main__':
    sdir, cdir = os.path.join(ROOT, 'series'), os.path.join(ROOT, 'cache')
    if '--backfill' in sys.argv:
        months, wide, ann, probs, dates = backfill(sdir, cdir)
        for p in probs:
            print('PROBLEM', p)
        print(f'{len(months)} 期：{months[0]} .. {months[-1]}，问题 {len(probs)} 条')
        if '--out' in sys.argv:                  # 只落两张表到别处（排查用），不碰 series/
            od = sys.argv[sys.argv.index('--out') + 1]
            os.makedirs(od, exist_ok=True)
            _write_csv(os.path.join(od, 'shenhua.csv'), COLUMNS, wide)
            _write_csv(os.path.join(od, 'shenhua_ann.csv'), ANN_COLUMNS, ann)
            with open(os.path.join(od, 'dates.json'), 'w', encoding='utf-8') as f:
                json.dump(dates, f, ensure_ascii=False, indent=0)
        if '--write' in sys.argv:
            if probs and '--force' not in sys.argv:
                raise SystemExit('有问题，不写（看完确认是已登记的例外再加 --force）')
            _write_csv(os.path.join(sdir, 'shenhua.csv'), COLUMNS, wide)
            _write_csv(os.path.join(sdir, 'shenhua_ann.csv'), ANN_COLUMNS, ann)
            sd = _source_dates()
            for m in months:
                sd.record(sdir, TICKER, m, dates[m][0], dates[m][1])
            print('已写入 series/shenhua.csv、series/shenhua_ann.csv、series/source_dates.csv')
    elif '--cadence' in sys.argv:
        for m, d in cadence(sdir):
            print(m, d)
    else:
        print('latest_month =', latest_month(cdir))
        print('added =', update(sdir, cdir))
