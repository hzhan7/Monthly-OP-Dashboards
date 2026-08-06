# -*- coding: utf-8 -*-
"""Costco 月度销售新闻稿的查找与解析 —— GlobeNewswire 通道，curl 可达无需 Chrome。

本文件搬自 skill「COST月度销售」的 `monthly_update.py`（原在 `~/.claude` 的 skills 目录下），
原 skill 已删除，本仓库不再引用它 —— 别再把路径写回去，那是删了就断的引用。
搬进来的是 `curl` / `find_release` / `pct` / `parse_release` 四个函数与它们用到的常量，
搬的时候逐字复制、一行没改（连注释一起搬 —— 那些注释记的是踩过的坑，见下）。
**搬进来之后改过一次**：2026-08 修 comp 表解析（坑 6、坑 7、坑 8），原 skill 已不存在、
无处分叉，所以是单向修改，不用回写任何地方。除此之外仍与当初搬进来的那份一致。
没搬的是 skill 里出 PDF 的部分（`main()` 的 CSV 回写与 build_report.py 调用、
`build_report.py`、`parse_dump.py`、`dump_all.json`）：总仓不出 PDF，一行也没引用过。

调用方只有 `fetch/cost.py`。CSV 的读写、幂等、缺列检查全在那边，本文件不碰磁盘。

═══ 这里面记着的坑（都在函数内的注释里，改代码前先读）═══
1. `parse_release` 的净销售额句有**三种句式**，Costco 换过写法；第三种没给百分比，
   要自己用「本月 vs 去年同月」算 y/y。
2. pandas 3.0 的 `astype(str)` 不再把 NaN 转成字符串 'nan'（仍是 float），
   comp 表必带空单元格 → `' '.join` 必抛 TypeError。已用 `.fillna('nan')` 修好，
   2.x/3.x 双向兼容。**别搬回旧版本**。
3. comp 表的 4 列表候选不能用 `'4 Weeks' in header` 子串匹配 —— 「24 Weeks」也命中，
   季度表会被当成月表，把 12 周的 comp 写进单月。
4. `find_release` 要做发布年校验：12 月的稿子发在次年 1 月。
5. 电商行的标签 Costco 已经改过一次名（E-commerce → Digitally-Enabled），
   正则两个都认；但**缺列不由本文件负责报错**，由 fetch/cost.py 在写 CSV 前统一检查。
6. GlobeNewswire 2026-07 起把 comp 表的**数值列整列复制**（月列 ×2、YTD 列 ×2 或 ×3），
   行 token 数从 2 变成 4/5，分支判据全部落空 → 调整值被报告值静默覆盖。
   `_drop_dup_cols` 在分支判断前按列还原。**按列去重，不要改成按 token 去重** ——
   token 级会误伤「4 周与 YTD 恰好同值」的正常行。
7. 去重之后 token 数才等于真实期间列数，`month_tabs` 因此收 1/2/3 列
   （单期间稿 / 月+YTD / 月+季度+财年），4 列是 2 月合并稿专属、走 four_col。
   旧代码只认 2，单期间稿（如 2020-09）全靠 GNW 的重复列凑出两个 token 才碰巧过关。
8. 2016-02 / 2017-02 的合并稿排了**四张**表（季度报告/季度调整/月报告/月调整），
   四张都是 2 期间列、全落进 month_tabs，直接取 [0][1] 会取成 12 周季度值 ——
   与坑 3 是同一个坑的另一条路径，所以 month_tabs 也要过 `_mo` 判据。

═══ 改这个文件之后怎么验 ═══
坑 6 的表现是**不抛异常但值全错**，所以「跑通了」不是验收标准，逐格比对才是。
2026-08 修完是这样验的：把 GNW 搜索页上能找到的每一篇销售稿重跑一遍 parse_release，
逐字段比对 series/cost.csv 已入库的值 ——
    series/cost.csv 覆盖的 124 个月**全部逐格一致，0 项不符**；
    新的 2026-07 解析出 tc_r=8.9 / tc_a=6.6，与新闻稿原文两张表逐格相符。
（2015-12 之前的稿子解析不了：那时的 comp 表没有 Canada 行，parser 从来没为它写过，
 而 CSV 也从 2015-12 起，所以不影响向前运行。别把它当回归失败。）

依赖：pandas（`pd.read_html`）+ lxml（read_html 的 HTML parser 后端，本机没装 html5lib，
      lxml 掉了没有后备，报错信息是「Import html5lib failed」，跟 Costco 毫无关系）。
"""
import io, re, sys, subprocess
import pandas as pd

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'
SEARCH = 'https://www.globenewswire.com/en/search/organization/Costco%2520Wholesale%2520Corporation'
GNW = 'https://www.globenewswire.com'
MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December']
WORDNUM = {'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12}

def curl(url):
    r = subprocess.run(['curl', '-sL', '--retry', '2', '--max-time', '40', '-A', UA, url],
                       capture_output=True, text=True)
    if r.returncode != 0 or len(r.stdout) < 3000:
        raise RuntimeError(f'curl failed ({r.returncode}, {len(r.stdout)}B): {url}')
    return r.stdout

def find_release(target):
    """在 GNW 搜索页找目标零售月的销售稿链接。target=(year, month 1-12)。"""
    y, m = target
    mname = MONTHS[m-1].lower()
    html = curl(SEARCH)
    links = re.findall(r'href="(/news-release/\d{4}/\d{2}/\d{2}/[^"]+?\.html)"', html)
    for l in links:
        slug = l.rsplit('/', 1)[-1]
        if 'sales-results' not in slug: continue
        if f'-{mname}-sales-results' in slug:
            # 发布年校验: 12月稿发于次年1月, 其余发于当月末或次月初
            rel_y = int(l.split('/')[2])
            if rel_y in (y, y+1):
                return GNW + l
    return None

def pct(tok):
    neg = tok.strip().startswith('(') or tok.strip().startswith('-')
    v = float(tok.strip().strip('()%-'))
    return -v if neg else v

def _drop_dup_cols(s):
    """丢掉与左邻「保留列」逐格完全相同的列，把 GNW 改版后整列复制的 comp 表还原成原形状。

    2026-07 起 GlobeNewswire 把 comp 表的每个数值列整列复制（月列 ×2、YTD 列 ×2 或 ×3），
    行 token 数从 2 变成 4 或 5，见 parse_release 里的说明。这里按**列**去重而不是按 token 去重：
    必须整列（含表头行）逐格相同才丢。逐 token 去重会误伤「4 周与 YTD 恰好同值」的正常行，
    整列相同则要求所有地区 + 表头全部撞上，2 月合并稿的 [报告, 调整] 两列数值不同，不会被误伤。
    """
    keep, prev = [], None
    for i in range(s.shape[1]):
        col = s.iloc[:, i].tolist()
        if col == prev:
            continue
        keep.append(i)
        prev = col
    return s.iloc[:, keep]

def parse_release(html):
    """返回 rec dict（不含 ym）+ (year, month)。失败抛异常。"""
    text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))
    rec = {}
    # --- 净销售额句（三种句式）---
    # 结束日期后的逗号要可选：2023-12 与 2024-01 两篇稿子写成「December 31, 2023 an increase」，
    # 少了那个逗号（后来的稿子又加回来了）。原来的 `\d{4}), an?` 硬吃逗号，这两个月直接抛
    # 「net sales sentence not found」。与 comp 表改版无关，是稿件本身的笔误。
    ns = re.search(r'net sales of \$([\d.,]+)\s*(billion|million) for the (?:retail )?month of (\w+),? the (four|five) weeks? ended ([A-Za-z]+\.? \d{1,2}, \d{4}),? an? (increase|decrease) of ([\w.]+) percent', text)
    if not ns:
        ns = re.search(r'For the (four|five)-week reporting month of (\w+), ended ([A-Za-z]+\.? \d{1,2}, \d{4}), the Company reported net sales of \$([\d.,]+) (billion|million), an? (increase|decrease) of ([\w.]+) percent', text)
        if ns:
            g = ns.groups()
            ns_t = (g[3], g[4], g[1], g[0], g[2], g[5], g[6])
        else:
            ns2 = re.search(r'net sales of \$([\d.,]+)\s*(billion|million) for the (?:retail )?month of (\w+),? the (four|five) weeks? ended ([A-Za-z]+\.? \d{1,2}, \d{4}), compared to \$([\d.,]+) (billion|million)', text)
            if not ns2: raise RuntimeError('net sales sentence not found')
            g = ns2.groups()
            cur, prev = float(g[0].replace(',','')), float(g[5].replace(',',''))
            yoy = round((cur/prev-1)*100, 1)
            ns_t = (g[0], g[1], g[2], g[3], g[4], 'increase' if yoy>=0 else 'decrease', str(abs(yoy)))
    else:
        ns_t = ns.groups()
    amt, unit, mname, weeks, ended, direction, p = ns_t
    p = float(p) if re.match(r'^[\d.]+$', p) else float(WORDNUM[p.lower()])
    rec['net_sales_bn'] = round(float(amt.replace(',','')) / (1000 if unit=='million' else 1), 3)
    rec['weeks'] = 4 if weeks == 'four' else 5
    rec['ns_yoy'] = p if direction == 'increase' else -p
    if mname not in MONTHS: raise RuntimeError(f'bad month name {mname}')
    mnum = MONTHS.index(mname) + 1
    em = re.match(r'([A-Za-z]+)\.? (\d{1,2}), (\d{4})', ended)
    ey = int(em.group(3))
    ym = (ey - 1, mnum) if (mnum == 12 and em.group(1) == 'January') else (ey, mnum)
    # --- comp 表 ---
    tabs = pd.read_html(io.StringIO(html))
    comp_tabs = []
    for t in tabs:
        # pandas >= 3.0 起 astype(str) 产出 StringDtype(na_value=nan)，**NaN 仍是 float**，
        # 不再像 2.x 那样被转成字符串 'nan'。而 GlobeNewswire 的 comp 表必然带合并/空单元格，
        # 于是下一行的 ' '.join 必抛 TypeError（sequence item N: expected str, float found）——
        # 与月份、与官网改版都无关，纯粹是依赖大版本升级踩的，本机升到 3.0.5 后 100% 复现。
        # 补 'nan' 而不是 ''：下面的 `c != 'nan'` 过滤本来就按 'nan' 写的，这样改动语义为零。
        s = t.astype(str).fillna('nan')
        # 2026-07 起 GNW 把 comp 表的每个数值列**整列复制**：
        #   ['U.S.', '10.3%', '10.3%', nan, '8.1%', '8.1%']        ← 月列/YTD 列各 ×2
        # 于是每行 toks 从 2 个变成 4 个，month_tabs（len==2）筛空，控制流掉进下面为
        # 2 月合并稿写的 four_col 分支——那个分支拿 toks[0]/toks[1] 当「报告/调整」，
        # 而这里 toks[0] 和 toks[1] 是**同一列报告值的两份拷贝**，调整值被报告值悄悄覆盖。
        # 危险在于列一个不缺、只是值全错，fetch/cost.py 的缺列检查抓不到，会直接发上公开看板。
        # 先按列还原成改版前的形状，后面的分支判断就跟改版前完全一致。
        s = _drop_dup_cols(s)
        joined = ' '.join(s.values.flatten().tolist())
        if 'Total Company' not in joined: continue
        rows = {}
        for _, row in s.iterrows():
            cells = [c for c in row.tolist() if c and c != 'nan']
            if not cells: continue
            lab = cells[0]
            toks = re.findall(r'\(?-?[\d.]+\)?\s*%', ' '.join(cells[1:]))
            if not toks: continue
            for key, pat in [('us', r'^U\.?S'), ('ca', r'^Canada'), ('oi', r'^Other International'),
                             ('tc', r'^Total Company'), ('ec', r'^(E-?commerce|Digitally)')]:
                if re.match(pat, lab): rows[key] = toks
        if rows: comp_tabs.append({'rows': rows, 'header': joined[:200]})
    # 去重之后 token 数 == 该表真实的**期间列数**，分支判断才第一次有确定含义：
    #   1 列  = 只有零售月（2020-09 这类单期间稿）
    #   2 列  = 零售月 + YTD（最常见）
    #   3 列  = 零售月 + 季度 + 财年（8/9/11 月与季报合并的稿）
    #   4 列  = 2 月合并稿，[4wk报告, 4wk调整, YTD报告, YTD调整] 挤在**同一张表**里
    # 前三种都是「报告值/调整值分成两张表、月值恒在 toks[0]」，只有 4 列那种是一张表里横排。
    # 旧写法只认 2，1 列稿全靠 GNW 的重复列凑出两个 token 才碰巧过关（2020-09 就是这样），
    # 去重后那份侥幸没了，必须按真实列数收全 1/2/3。
    month_tabs = [t for t in comp_tabs if len(t['rows'].get('tc', [])) in (1, 2, 3)]
    # 4 列表候选：'4 Weeks' 不能用子串匹配——「24 Weeks」也会命中，季度表因此可能
    # 排在月表前面被 four_col[0] 选走，把 12 周季度 comp 当成单月 comp 写进 CSV。
    # 先按「真·月表」严格筛（\d 前瞻排除 24 Weeks，且不含季度周数）；筛空才回退旧口径并告警。
    _mo = lambda h: re.search(r'(?<!\d)[45] Weeks', h) and '12 Weeks' not in h and '24 Weeks' not in h
    _any = lambda h: '4 Weeks' in h or '5 Weeks' in h
    # 同一个「别把季度表当月表」的坑，month_tabs 这条路也踩得到：2016-02 / 2017-02 的合并稿
    # 排了**四张**表（季度报告 / 季度调整 / 月报告 / 月调整），每张都是 2 期间列，
    # 全部落进 month_tabs，取 [0][1] 就取成了 12 周季度值。用同一个 _mo 判据挑真·月表。
    # 只在筛得出 ≥2 张时才替换：8/9/11 月与季报合并的稿子，月表自己就带 12 Weeks 季度列，
    # 严格筛会把它们清空，这时保持旧口径（该稿只有月报告/月调整两张表，顺序本来就对）。
    _mo_tabs = [t for t in month_tabs if _mo(t['header'])]
    if len(_mo_tabs) >= 2:
        month_tabs = _mo_tabs
    _c4 = [t for t in comp_tabs if len(t['rows'].get('tc', [])) == 4]
    four_col = [t for t in _c4 if _mo(t['header'])]
    if not four_col:
        four_col = [t for t in _c4 if _any(t['header'])]
        if four_col:
            print('WARN: 未找到严格匹配的月表(4/5 Weeks 且不含 12/24 Weeks)，'
                  '回退旧口径——请核对 comp 是否误取了季度值', file=sys.stderr)
    if len(month_tabs) >= 2:      # 普通月: 表1=报告值, 表2=调整值
        for suf, t in [('r', month_tabs[0]), ('a', month_tabs[1])]:
            for k, toks in t['rows'].items(): rec[f'{k}_{suf}'] = pct(toks[0])
    elif four_col:                # 2月合并稿: 月表4列 [4wk报告, 4wk调整, YTD报告, YTD调整]
        t = four_col[0]
        for k, toks in t['rows'].items():
            rec[f'{k}_r'] = pct(toks[0]); rec[f'{k}_a'] = pct(toks[1])
    else:
        raise RuntimeError(f'comp tables not recognized ({len(comp_tabs)} candidates)')
    for k in ['us_r','ca_r','oi_r','tc_r','us_a','ca_a','oi_a','tc_a']:
        if k not in rec: raise RuntimeError(f'missing {k}')
    # --- 仓库数 ---
    w = re.search(r'operates? ([\d,]+) warehouses,? including ([\d,]+) in the United States', text)
    if w:
        rec['wh_total'] = int(w.group(1).replace(',','')); rec['wh_us'] = int(w.group(2).replace(',',''))
    return rec, ym
