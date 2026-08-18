# -*- coding: utf-8 -*-
"""DB1 现货成交额的**历史回填**：把 series/db1.csv 的 10 条 FWB 现货列
从 2024-01 / 2024-12 起推到 2016-01 起。

用法:
    python3 build/basefill/db1_spot_2016.py            # 取数 + 核对 + 写 CSV
    python3 build/basefill/db1_spot_2016.py --dry      # 只打印，不写文件
    python3 build/basefill/db1_spot_2016.py --refresh  # 强制重下（忽略 cache）
    python3 build/basefill/db1_spot_2016.py --cache DIR  # 指定 cache 目录

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
这个文件为什么存在，以及为什么**不**把它塞进 fetch/db1.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
fetch/db1.py 的 FWB 腿只认官方 CMS 挂着的那批工作簿，而官方**只挂 20 期**
（本轮实测：4090756!search 翻到 pageNum=1 就 blocks=0，共 20 条，最老 20241231）。
每期「Total View」底部有一块「本年度逐月」，所以 20 期能白捡到 2024-01 —— 那已经是
那条链路的物理天花板，抓取器不是瓶颈，官方就只挂这么多。

再往回只剩两条路，**两条都不属于「官方 live 源 + 当前版式」**，所以都不进 fetch/：

  腿 A · web.archive.org 上那批**官方工作簿的存档副本**（旧域名
        deutsche-boerse-cash-market.com）。文件本身是官方原件、版式与今天同构
        （只多一列 Tradegate 在第 3 列，`_parse_fwb` 一行不用改就能吃），
        但**源站已经把它们清库了**：实测拼 2016-06 那期的 blob 2637934 直链 → HTTP 404
        （对照组 2024-12 的 blob 4247566 → 200）。CDX 命中是**固定的 32 期**，
        不会再长；把一段永远走不到新东西的 archive.org 分支焊进无人值守的抓取器，
        等于让它每月都带着一段死代码。

  腿 B · 同站**月度现货新闻稿**。它是 live 的，但对抓取器毫无价值：新闻稿给的是
        四舍五入过的 €bn，而抓取器每月都能从官方工作簿拿到满精度原值。
        这条腿只在「工作簿够不到的那 55 个月」上有用，一次用完就再也用不上。

  ⚠ 与 mtk 那次不同：mtk 的历史是**同一个源、同一种版式**，只是抓取器的窗口没开，
    所以那次是改 update() 让它自己长得回去；这里两条腿都是**另一个源**
    （archive.org 副本 / HTML 新闻稿），腿 B 还是**另一种版式**，
    一次性脚本才是对的。别把两种情形套用同一个结论。

fetch/db1.py 这次只改两处，都不是取数逻辑：
  · `_parse_fwb()` 多一个 `self_tol` 形参（默认值不变，见下方「腿 A 的一个坑」）；
  · `_META` 的 first_month 与 docstring 跟着新的覆盖范围更新。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
腿 A：archive.org 上的官方工作簿（满精度）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CDX 查询（本轮实测 32 期 200 OK，四个域名里只有旧域名有命中；
cashmarket.deutsche-boerse.com / deutsche-boerse.com / xetra.com / boerse-frankfurt.de
全部 0 命中）：

    http://web.archive.org/cdx/search/cdx?url=deutsche-boerse-cash-market.com
        &matchType=domain&filter=original:.*FWB_Monthly_Cash_Market_Statistics.*
        &filter=statuscode:200&output=json

报告月：2016-06、2016-08~2016-12、2017-01~2017-05、2022-05~2023-04、
2023-08~2023-10、2023-12、2024-01~2024-05（2023-11 那期只有非 200 的 capture）。

每期带出两批数：
  · 报告月自己的 5×2 分资产类别块 → 8 条分类列（满精度）；
  · 「本年度逐月」块 → 场所级总额，所以 20161231 那期一次给出 2016 全年 12 个月。
    合计 **46 个月**的场所级总额：2016-01~2017-05、2022-01~2024-05。
    46 个月里凡是被多期文件同时覆盖的，本轮**逐位比对零分歧**（硬校验，见 `_leg_wayback`）。

⚠ 腿 A 的一个坑：2016/2017 那批老文件里，「本年度逐月」块的法兰克福数与顶部
  分类块 Total 有极小的不一致（最大 2017-02 的 6.7e-5 €bn = €66,825，最小
  2016-08 的 1.0e-6 €bn = €1,005），5 期会撞上 `_parse_fwb` 那道 1e-6 €bn 的
  自洽检验。这不是解析错行 —— 两块数的**量级、场所、月份全都对**，是官方自己
  两块表的尾数不同步。所以这里给 `_parse_fwb` 传一个放宽到 1e-3 €bn 的 `self_tol`，
  **只对这批存档文件放宽**，抓取器每月跑的那条路一个字节都不改。
  报告月自己的值一律取顶部分类块（那一块与 5 个 instrument group 逐位闭合）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
腿 B：同站月度现货新闻稿（四舍五入值）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
列表页用的是**本模块已经在用的同一套翻页接口**（4091716!search，与 3848!search /
4090756!search 完全同构），95 页 4,745 条回到 2008-12。fetch/db1.py 的 docstring 原来
写着「现货月度新闻稿 URL 里的 id 不可预测」，那句话本轮实测**为假**，已在该文件里更正。

两种版式：
  · 2018-05 起（2018-06-01 那篇）正文里有一张 <table>，表头
    ['', 'Xetra', 'Frankfurt', ('Tradegate',) 'In total'|'Total'|'Gesamt']，
    行是 Equities / ETFs-ETCs-ETNs / Bonds / Funds / Certificates(或 Other Instruments)
    + 「{月} in total」行（2022 起官方把 Tradegate 整列去掉了）。
  · 2018-04 及更早只有散文，句式换过四种，只给得出两个场所总额，
    **拿不到分场所的分类拆分**（那时正文里的分类数是 Xetra+法兰克福+Tradegate
    三场所合计：2016-01 equities 112.9 / ETP 18.5 / bonds 0.5 / structured 1.5 /
    funds 0.2，合 133.6 ≈ 三场所总额 133.7，与本仓两条场所列不是一个口径）。

标题逐年换（"Turnover at Deutsche Börse's cash markets at 133.7 billion euros in
January" → "Cash markets achieve turnover of …" → "Cash market trading volumes in …"
→ "Deutsche Börse Trading Volumes in July 2026"），所以**不按标题匹配**：
按「发布日落在次月 1–10 日」+ 关键词粗筛出候选，再靠下面第 1 道闸门（台账闭合）
确认到底是不是那一篇。筛错篇会被闸门挡下来，不会静默写进 CSV。

四个月官方**没发**月度稿（2017-12、2018-06、2018-07、2019-12，列表页逐日翻过，
确实没有）。这四个月改用**次年同月那篇的「去年同月」对照行**（2018-12 那篇的
"Dec. '17 in total"、2019-06 的 "Jun 2018 in total"、2019-07 的 "July 2018 in total"、
2020-12 的 "Dec '19 in total"），同样过台账闭合闸门。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
精度分层 —— 本次回填的**主要风险**（不是口径变了，是有效数字变了）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
新闻稿 2018-05~2022-07 是 1 位小数 €bn，2022 年三季度起转 2 位小数（同一张表里
偶尔混用，如 2022-08 的 Xetra equities 写 80.40 而法兰克福 equities 写 1.2）。
对 Xetra 场所总额（~100 €bn）1 位小数只有 ±0.05%，无所谓；但对法兰克福 funds
（0.04 €bn）就是 ±125%。所以入库前过一道**精度闸门**：

    按 (列, 该单元格印了几位小数) 分组，只有整组里**最小的那个值**都满足
    「四舍五入半宽 ≤ 3% × 值」时，整组才入库。

分组而不是逐格判，是为了让「哪些月有、哪些月没有」按精度时代成段，
不要在同一列里跳着有跳着无。3% 的依据：这些序列的正常月环比在 ±10~40%，
把四舍五入噪声压到环比信号的十分之一以下，它就不会翻转任何一个月的方向。

闸门的实测结论（脚本每次跑都会重新打印，不是写死的）：
  · Xetra 两条分类列与两条场所总额：1 位小数时代也过得了，全程入库；
  · 法兰克福的 equities / etp / bonds / funds / structured：1 位小数时代整组不入库，
    2 位小数时代 funds 仍不入库（0.03~0.06 €bn 上 ±0.005 是 8~17%）。
⇒ 法兰克福那几条分类列的连续史因此只到 2022 年三季度，**到不了 2016-01**；
  更早只有腿 A 那 11 个存档月（2016-06、2016-08~2017-05）是满精度的孤岛。
  这不是懒得补，是官方在那段时间就没有更细的公开数。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
五道机器闸门（都会 print；不过就丢掉那个月/那一格，或者直接抛）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. **台账闭合**：`|Xetra + 法兰克福 − turnover_cash_total_eurbn| ≤ 两格的四舍五入
   半宽之和 + 0.01 €bn`。turnover_cash_total_eurbn 是集团 IR 台账口径的现货合计
   （满精度、2010-01 起、慢腿），是一条**完全独立于 FWB 那条产线**的证据。
   本轮实测：46 个工作簿月残差 ≤6.7e-5 €bn（2022 年起逐位相等，2016/2017 那批
   老文件是尾数不同步）；123 个新闻稿月最大残差 0.0947 €bn（2020-11），
   全部落在四舍五入界内。这道闸门同时挡住四类错：粗筛筛错了篇、正则抓到了年度句
   （2016-12 那篇先讲全年 "€43.9 billion to Börse Frankfurt" 再讲当月 "€4.2 billion"）、
   Tradegate 被当成第二个场所、以及官方把合计行标签印错月份。
   ⚠ 这也是**不能再往 2016-01 以前走**的原因：台账合计列只到 2010-01，
   新闻稿本身能一路翻到 2008-12，但那之前没有第二条证据能核，宁可不要。
2. **跨文件一致**：同一个月被多期存档工作簿覆盖时逐位比对，超过 XFILE_TOL 就抛。
3. **新闻稿 vs 满精度参照**：新闻稿值 vs CSV 已有值（或腿 A 给出的存档件值），
   差超过四舍五入半宽就报 —— 这是唯一能发现「解析错行但恰好也过了台账闭合」的办法。
   本轮比对 405 格，越界 7 格，两簇都不是解析错：2025-12 那 6 格是官方重发工作簿
   造成的重述（见 KNOWN_RESTATEMENTS），2022-05 法兰克福 bonds 那 1 格是官方
   新闻稿自己印错了位（0.242953 印成 0.3），而那一格早被精度闸门整组丢掉了。
3b. **腿 A vs CSV 逐位相等**：存档件与 live 件是同一条产线出的同一份文件，
   重叠格必须逐位相等（不是「界内」）。首次回填时重叠 10 格，0 例不一致 ——
   这是「archive.org 上那份到底是不是官方原件」唯一的机器答案。
4. **表内分类闭合**：新闻稿表里每个场所的 5 个 instrument group 之和 ≡ 该场所合计行。
   这是「行标签认对了没有」的判据（'Certificates' ↔ 'Other Instruments' ↔
   'Structured Products and Other Instruments' 三种写法）。本轮 186 个 (月, 场所) 全过。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
写盘规矩
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
· **只填空，永不覆盖**（与 fetch/db1.py 口径坑 3 同一条规矩）。已有单元格一个不动，
  所以 2024-01 起那 31 个月的满精度值不会被新闻稿的四舍五入值盖掉。
· 不新建列、不改列序、不动别的行；未触碰的单元格按原字符串搬运。
· `_fmt` 直接复用 fetch/db1.py 的，保证与抓取器写出来的字节一致。
· 不写 series/source_dates.csv（回补月份不记发布日，理由见 fetch/db1.py 口径坑 3）。
· 抓下来的原始档案落 cache/（gitignore）：存档工作簿在 cache/basefill/，
  新闻稿在 cache/db1_pr/，列表页在 cache/db1_pr_pN.html。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
本轮跑完的结果（2026-08-18，脚本每次跑都会重新打印，这里只是留个底）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    turnover_xetra_eurbn             2024-01 → 2016-01   31 → 127 个月（无空洞）
    turnover_fwb_eurbn               2024-01 → 2016-01   31 → 127 个月（无空洞）
    turnover_xetra_equities_eurbn    2024-12 → 2016-06   20 → 107 个月
    turnover_xetra_etp_eurbn         2024-12 → 2016-06   20 → 107 个月
    turnover_fwb_equities_eurbn      2024-12 → 2016-06   20 →  62 个月
    turnover_fwb_bonds_eurbn         2024-12 → 2016-06   20 →  62 个月
    turnover_fwb_structured_eurbn    2024-12 → 2016-06   20 →  62 个月
    turnover_fwb_etp_eurbn           2024-12 → 2016-06   20 →  52 个月
    turnover_fwb_funds_eurbn         2024-12 → 2016-06   20 →  52 个月
    turnover_xetra_structured_eurbn  2025-10 → 2016-06    5 →  21 个月

两条场所总额列 96 个新月份的出处：腿 A 存档工作簿 41 个月、腿 B 当月新闻稿 51 个月、
腿 B「去年同月」对照行 4 个月（2017-12 / 2018-06 / 2018-07 / 2019-12，官方那四个月
没发月度稿）。分类列 380 格：腿 A 240 格、腿 B 140 格。
一格既有值都没被覆盖（改动前后逐格 diff：10 列 572 格，原本非空的 0 格）。

━━ 依赖 ━━ xlrd（读 BIFF .xls，与 fetch/db1.py 同一份）。不依赖 pandas / bs4。
"""

import argparse
import csv
import datetime
import html
import importlib.util
import json
import os
import re
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SERIES_CSV = os.path.join(ROOT, 'series', 'db1.csv')

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

CDX = ('http://web.archive.org/cdx/search/cdx?url=deutsche-boerse-cash-market.com'
       '&matchType=domain&filter=original:.*FWB_Monthly_Cash_Market_Statistics.*'
       '&filter=statuscode:200&output=json&limit=500&collapse=urlkey')
WB_URL = 'http://web.archive.org/web/%sid_/%s'

PR_HOST = 'https://www.cashmarket.deutsche-boerse.com'
PR_SEARCH = (PR_HOST + '/cash-en/Stay-Informed/newsroom/press-releases/'
             '4091716!search?pageNum=%d&hitsPerPage=50&sort=sDate%%20desc')

TARGET_FROM = '2016-01'          # 回填目标起点；再往前台账合计列（闸门 1）就没有了
LEDGER = 'turnover_cash_total_eurbn'

#: 精度闸门：四舍五入半宽 ≤ 这个比例 × 该 (列, 小数位) 分组里最小的值，整组才入库。
#: 见 docstring「精度分层」那节。
PRECISION_MAX_REL = 0.03
#: 闸门 3 的已知例外：**官方重发过工作簿、把当月数改了**的月份。
#: 2025-12 是 fetch/db1.py 口径坑 3 已经写明的那一个：那期 FWB 文件的 Cover
#: 「Created on」= 2026-01-29，列表页却写 Jan 01, 2026，是被重发过的证据；
#: 本轮独立复现了它的后果 —— CSV（重发件）法兰克福 3.687969 €bn，
#: 而当月新闻稿（2026-01-02 发）与集团 IR 台账**互相一致**地给 3.33 / 116.317714，
#: 三者里只有重发的工作簿不同（Xetra 那一格 113.00 三方完全一致）。
#: 差额 +0.371576 €bn 与该 docstring 记的 €371.6m 逐位吻合。
#: ⇒ 这是官方重述，不是解析错行。已有值不覆盖，证据写进 cache/db1_restatements.csv。
#: **只放行这一个月**：再出现新的不一致就应该停下来查，而不是继续写盘。
KNOWN_RESTATEMENTS = {'2025-12'}

#: 台账闭合闸门在两格四舍五入半宽之和上再给的松量（€bn）。
#: 本轮 120 个新闻稿月的最大残差 0.0947，恰好卡在 1 位小数的理论界 0.100 上，
#: 不给这一点松量的话浮点误差就能把它挤出去。
CLOSURE_SLACK = 0.01

VENUE_COLS = ['turnover_xetra_eurbn', 'turnover_fwb_eurbn']
GROUP_COLS = ['turnover_xetra_equities_eurbn', 'turnover_xetra_etp_eurbn',
              'turnover_xetra_structured_eurbn', 'turnover_fwb_equities_eurbn',
              'turnover_fwb_etp_eurbn', 'turnover_fwb_bonds_eurbn',
              'turnover_fwb_funds_eurbn', 'turnover_fwb_structured_eurbn']
ALL_COLS = VENUE_COLS + GROUP_COLS


class BasefillError(RuntimeError):
    """源站结构变了 / 闸门炸了。一律抛，绝不静默写半截数据。"""


# ── 复用 fetch/db1.py ───────────────────────────────────────────────────────
def _load_fetch():
    """按路径加载 fetch/db1.py —— 本仓没有 __init__.py，monthly_run.py 也是这么干的。"""
    path = os.path.join(ROOT, 'fetch', 'db1.py')
    spec = importlib.util.spec_from_file_location('_db1_fetch_for_basefill', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


F = _load_fetch()


# ── 网络 ────────────────────────────────────────────────────────────────────
def _get(url, timeout=120, retries=3, binary=False):
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={
            'User-Agent': _UA, 'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.9'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            return data if binary else data.decode('utf-8', 'replace')
        except Exception as e:                        # noqa: BLE001
            last = e
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    raise BasefillError('下载失败（%d 次重试后）%s: %r' % (retries, url, last))


def _cached(path, url, refresh, binary=False, min_bytes=1):
    if not refresh and os.path.exists(path) and os.path.getsize(path) >= min_bytes:
        mode = 'rb' if binary else 'r'
        with open(path, mode, **({} if binary else {'encoding': 'utf-8'})) as f:
            return f.read()
    data = _get(url, binary=binary)
    if len(data) < min_bytes:
        raise BasefillError('%s 只有 %d 字节，不像是完整档案' % (url, len(data)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = 'wb' if binary else 'w'
    with open(path, mode, **({} if binary else {'encoding': 'utf-8'})) as f:
        f.write(data)
    time.sleep(0.25)
    return data


# ── 腿 A：archive.org 上的官方工作簿 ────────────────────────────────────────
#: 闸门 2（跨文件一致）的容差，€bn。同一个月被多期存档工作簿覆盖时逐位比对。
#: 2022 年以后的文件是**逐位相等**的；2016/2017 那批老文件的「本年度逐月」块与
#: 报告月自己的「顶部分类块」尾数不同步（与 `self_tol` 同一个成因，最大 1.0e-6 €bn
#: = €1,005），所以给 1e-3 €bn 的容差，并把实测最大分歧打出来让人看见。
XFILE_TOL = 1e-3


def _leg_wayback(cache_dir, refresh):
    """返回 ({'YYYY-MM': {列: 值}}, 出处说明)。满精度，做跨文件一致性硬校验。

    同一个月出现在多期文件里时**先到先得**，而遍历按文件时间戳升序 —— 于是
    报告月自己那一期（顶部分类块，与 5 个 instrument group 逐位闭合）总是先写，
    后来那些文件的「本年度逐月」块只用来核对，不覆盖。
    """
    rows = json.loads(_get(CDX))
    if not rows or rows[0][:3] != ['urlkey', 'timestamp', 'original']:
        raise BasefillError('CDX 返回的表头不认识，接口可能变了：%r' % (rows[:1],))
    caps = {}
    for r in rows[1:]:
        stamp = r[2].rsplit('.', 2)[-2]               # …Statistics.20161231.xls
        if not re.fullmatch(r'\d{8}', stamp):
            continue
        caps.setdefault(stamp, (r[1], r[2]))          # 同一份只取第一个 capture
    if len(caps) < 30:
        raise BasefillError('CDX 只命中 %d 期存档工作簿，比本轮实测的 32 期少太多' % len(caps))

    out, src, seen = {}, {}, {}
    worst = (0.0, None)
    for stamp, (ts, orig) in sorted(caps.items()):
        mon = F._month_of(stamp)
        dst = os.path.join(cache_dir, 'basefill', 'db1_fwb_wb_%s.xls' % stamp)
        _cached(dst, WB_URL % (ts, orig), refresh, binary=True, min_bytes=50000)
        # self_tol 放宽到 1e-3 €bn：2016/2017 那批老文件两块表的尾数不同步，
        # 最大 6.7e-5 €bn。放宽只影响这里，抓取器那条路仍是默认的 1e-6。
        recs, _created = F._parse_fwb(dst, mon, self_tol=1e-3)
        for m2, rec in recs.items():
            for col, v in rec.items():
                if v is None or col not in ALL_COLS:
                    continue
                prev = seen.get((m2, col))
                if prev is not None:
                    d = abs(prev[1] - v)
                    if d > XFILE_TOL:
                        raise BasefillError(
                            '闸门 2 不过：%s 的 %s 在 %s 里是 %.9f，在 %s 里是 %.9f'
                            % (m2, col, prev[0], prev[1], stamp, v))
                    if d > worst[0]:
                        worst = (d, '%s %s（%s vs %s）' % (m2, col, prev[0], stamp))
                    continue
                seen[(m2, col)] = (stamp, v)
                out.setdefault(m2, {})[col] = v
                src.setdefault(m2, {})[col] = (
                    'FWB_Monthly_Cash_Market_Statistics.%s.xls（web.archive.org 存档副本）'
                    % stamp)
    return out, src, worst


# ── 腿 B：月度现货新闻稿 ────────────────────────────────────────────────────
_PR_BLOCK = re.compile(
    r'<a class="teasable-search-result-link\s*" href="([^"]+)">.*?'
    r'<p class="search-result-date">([^<]+)</p>.*?'
    r'<h1 class="search-result-description\s*">(.*?)</h1>', re.S)

_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
           'July', 'August', 'September', 'October', 'November', 'December']
_ABBR = {m[:3].lower(): i + 1 for i, m in enumerate(_MONTHS)}
_ABBR['sept'] = 9

# 粗筛：标题里有这些词的才可能是月度现货稿；有 _PR_BAD 的一定不是。
# 粗筛只负责把候选压到个位数，真正拍板的是台账闭合闸门。
_PR_KEY = re.compile(r'cash market|turnover|trading volumes|order ?book', re.I)
_PR_BAD = re.compile(r'ETF and ETP Listings|Figures at Eurex|Eurex|STOXX|ISE Holdings'
                     r'|Photography|Clearstream|Xetra-?\s?Gold|EEX|Q[1-4]/', re.I)


def _pr_index(cache_dir, refresh):
    """翻 4091716!search 的全部页，返回 [(发布日 date, 标题, href)]，按日期升序。"""
    out, page = [], 0
    while page < 120:
        path = os.path.join(cache_dir, 'db1_pr_p%d.html' % page)
        h = _cached(path, PR_SEARCH % page, refresh, min_bytes=5000)
        hits = _PR_BLOCK.findall(h)
        if not hits:
            if page == 0:
                raise BasefillError('新闻稿列表页第 0 页解析不到任何条目，源站可能改版')
            break
        for href, day, title in hits:
            try:
                p = day.split()
                d = datetime.date(int(p[2].rstrip(',')), _ABBR[p[0][:3].lower()],
                                  int(p[1].rstrip(',')))
            except (KeyError, ValueError, IndexError):
                continue
            t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', title))).strip()
            out.append((d, t, href))
        page += 1
    return sorted(out)


def _pr_candidates(index):
    """{'YYYY-MM': [(date, title, href)]} —— 发布日落在次月 1–10 日的粗筛候选。"""
    cand = {}
    for d, t, href in index:
        if d.day > 10 or not _PR_KEY.search(t) or _PR_BAD.search(t):
            continue
        y, m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
        cand.setdefault('%04d-%02d' % (y, m), []).append((d, t, href))
    return cand


def _text(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'(?s)<[^>]+>', ' ', s))).strip()


_STRICT_NUM = re.compile(r'^-?[\d,]+\.\d+$|^-?[\d,]+$')


def _cell(s):
    """'1,324.6' -> (1324.6, 1)；'-' / '<0.1' / '0,1' -> (None, None)。

    第三种是官方的排版事故（2021-12 那张表里 Tradegate 的 bonds 印成 '0,1'），
    宽松解析会把它读成 1 或 0.1，两个都是错的 —— 认不出就当没有。
    """
    s = (s or '').replace('\xa0', ' ').strip()
    if not _STRICT_NUM.match(s.replace(' ', '')):
        return None, None
    s = s.replace(' ', '')
    return float(s.replace(',', '')), (len(s.split('.')[1]) if '.' in s else 0)


_PR_GROUP = {
    'equities': 'equities', 'equity': 'equities',
    'etf/etc/etn': 'etp', 'etfs/etcs/etns': 'etp', 'etfs, etcs, etns': 'etp',
    'etf/etc/etns': 'etp', 'etfs, etcs and etns': 'etp',
    'bonds': 'bonds', 'funds': 'funds',
    # 官方三种写法指同一个 instrument group：工作簿里叫
    # 'Structured Products and Other Instruments'，新闻稿 2018–2021 叫 'Certificates'、
    # 2021 起叫 'Other Instruments'。本轮拿 21 个重叠月逐格比对过（腿 A 满精度 vs
    # 新闻稿四舍五入值），三种写法对应的都是同一列，零例外。
    'certificates': 'structured', 'other instruments': 'structured',
    'structured products and other instruments': 'structured',
    'certificates/warrants': 'structured',
}


def _norm_lbl(s):
    return re.sub(r'\s+', ' ', s.replace('’', "'").replace('‘', "'")
                  .strip().lower()).strip('.: ')


def _total_row_month(lbl):
    """"Dec. '18 in total" / "Grand Total May 2018" / "June 2019 in total" -> (y, m)。

    年度行（"2021 in total"）里没有月份名，返回 None —— 12 月那两篇有两张表，
    靠这一条把年度表整张跳过。
    """
    s = _norm_lbl(lbl)
    if 'in total' not in s and 'grand total' not in s:
        return None
    m = re.search(r"([a-zä]{3,9})\.?\s*'?\s*(\d{2,4})", s)
    if not m:
        return None
    mi = _ABBR.get(m.group(1)[:4]) or _ABBR.get(m.group(1)[:3])
    if not mi:
        return None
    y = int(m.group(2))
    return (y + 2000 if y < 100 else y), mi


def _pr_tables(h):
    out = []
    for tb in re.findall(r'(?s)<table[^>]*>(.*?)</table>', h):
        rows = [[_text(td) for td in re.findall(r'(?s)<t[dh][^>]*>(.*?)</t[dh]>', tr)]
                for tr in re.findall(r'(?s)<tr[^>]*>(.*?)</tr>', tb)]
        if rows:
            out.append(rows)
    return out


def _parse_pr_table(h):
    """解析新闻稿正文里的场所 × 资产类别表。

    返回 (groups, totals) 或 None：
      groups = {('xetra'|'fwb', 组名): (值, 小数位)}   —— 只属于报告月
      totals = [((y, m), {'xetra': (值, 小数位), 'fwb': (…)})]，按表内顺序

    **只认合计行标签里带月份名的表。**12 月那几篇正文里有两张同构的表，第一张是
    「2021 in total / 2020 in total」的年度表，第二张才是当月表；年度表的合计行
    解析不出月份，于是整张被跳过 —— 这比按位置取第一张稳，也顺带把
    「Deutsche Börse to publish cash market annual statistics …」那种纯年度稿挡在外面。

    「报告月是哪个月」**按位置定**（第一条合计行），不按行标签 —— 官方标错过：
    2020-03-02 那篇（2020-02 数据）的合计行印的是 "Jan '20 in total"，
    表里的数却是二月的（正文与「去年同月」行都对得上二月）。按标签走会把二月的数
    写到一月头上，而两个月都过不了台账闭合闸门，等于白丢两个月。
    """
    for rows in _pr_tables(h):
        hdr = None
        for r in rows[:2]:
            low = [c.strip().lower() for c in r]
            if 'xetra' in low and 'frankfurt' in low:
                hdr = {'xetra': low.index('xetra'), 'fwb': low.index('frankfurt')}
                break
        if not hdr:
            continue
        groups, totals = {}, []
        for r in rows:
            if not r:
                continue
            key = _PR_GROUP.get(_norm_lbl(r[0]))
            if key:
                for v, ci in hdr.items():
                    if ci < len(r):
                        groups[(v, key)] = _cell(r[ci])
            lab = _total_row_month(r[0])
            if lab:
                totals.append((lab, {v: _cell(r[ci])
                                     for v, ci in hdr.items() if ci < len(r)}))
        if groups and totals:
            return groups, totals
    return None


_BILL = r'(\d[\d,]*\.?\d*)\s*billion'
_X_PAT = [re.compile(r'€\s*' + _BILL +
                     r'\s+(?:were|was)\s+attributable\s+to\s+(?:the\s+)?Xetra', re.I)]
_F_PAT = [re.compile(r'€\s*' + _BILL +
                     r'\s+(?:were|was)\s+attributable\s+to\s+B[öo]rse\s+Frankfurt', re.I),
          re.compile(r'€\s*' + _BILL + r'\s+to\s+B[öo]rse\s+Frankfurt', re.I),
          re.compile(r'on\s+B[öo]rse\s+Frankfurt\s+(?:total(?:l)?ed|was)\s+€\s*' + _BILL,
                     re.I)]


def _parse_pr_prose(h):
    """2018-04 及更早的散文版式，只取两个场所总额。

    法兰克福那一格取**离 Xetra 那一格最近**的匹配，不取第一个 —— 2016-12 那篇
    先讲全年（"€43.9 billion to Börse Frankfurt"）再讲当月（"€4.2 billion"），
    取第一个会拿到年度数（台账闸门也会挡下来，但那样就白丢一个月）。
    """
    body = ' '.join(_text(p) for p in re.findall(r'(?s)<p[^>]*>(.*?)</p>', h))
    xm = None
    for p in _X_PAT:
        xm = p.search(body)
        if xm:
            break
    if not xm:
        return None
    cands = [m for p in _F_PAT for m in p.finditer(body)]
    if not cands:
        return None
    fm = min(cands, key=lambda m: abs(m.start() - xm.start()))
    return {'xetra': _cell(xm.group(1)), 'fwb': _cell(fm.group(1))}


def _leg_press(cache_dir, refresh, ledger, need_months):
    """返回 ({'YYYY-MM': {列: (值, 小数位)}}, 出处说明)，已过台账闭合闸门。"""
    index = _pr_index(cache_dir, refresh)
    cand = _pr_candidates(index)
    raw, src, rejected = {}, {}, []

    def closes(mon, x, f):
        """闸门 1：Xetra + 法兰克福 ≡ 台账现货合计（在两格的四舍五入界内）。"""
        L = ledger.get(mon)
        if L is None or x[0] is None or f[0] is None:
            return False, None
        tol = 0.5 * 10 ** -x[1] + 0.5 * 10 ** -f[1] + CLOSURE_SLACK
        d = x[0] + f[0] - L
        return abs(d) <= tol, d

    def groups_close(groups, tot):
        """闸门 4：表内每个场所的 5 个 instrument group 之和 ≡ 该场所的合计行。

        这是「行标签认对了没有」的机器判据：'Certificates' / 'Other Instruments'
        哪一个漏进 GROUP 映射、或者 Xetra 那一列取错了列号，和就对不上。
        容差按各格自己印的小数位算（1 位小数、6 个格，界就是 0.30 €bn）。
        本轮 186 个 (月, 场所) 全部闭合，0 越界。
        """
        for venue in ('xetra', 'fwb'):
            cells = [v for (vn, _k), v in groups.items() if vn == venue and v[0] is not None]
            if not cells or tot[venue][0] is None:
                continue
            s = sum(v for v, _d in cells)
            half = sum(0.5 * 10 ** -d for _v, d in cells) + 0.5 * 10 ** -tot[venue][1]
            if abs(s - tot[venue][0]) > half + 1e-9:
                return False, '%s 分类和 %.4f vs Total %.4f' % (venue, s, tot[venue][0])
        return True, None

    for mon in sorted(cand):
        if mon < TARGET_FROM:
            continue
        for i, (d, title, href) in enumerate(cand[mon]):
            path = os.path.join(cache_dir, 'db1_pr', '%s_%d.html' % (mon, i))
            h = _cached(path, PR_HOST + href, refresh, min_bytes=10000)
            got = _parse_pr_table(h)
            hit = None
            if got:
                groups, totals = got
                ok, diff = closes(mon, totals[0][1]['xetra'], totals[0][1]['fwb'])
                gok, gwhy = groups_close(groups, totals[0][1])
                if ok and not gok:
                    raise BasefillError('闸门 4 不过：%s 那篇的表内分类不闭合（%s），'
                                        '行标签映射多半错了' % (mon, gwhy))
                if ok:
                    hit = {'turnover_xetra_eurbn': totals[0][1]['xetra'],
                           'turnover_fwb_eurbn': totals[0][1]['fwb']}
                    for (venue, key), val in groups.items():
                        col = 'turnover_%s_%s_eurbn' % (venue, key)
                        if col in GROUP_COLS:
                            hit[col] = val
                    # 「去年同月」对照行：只在官方那个月压根没发稿时才用得上
                    prev = '%04d-%02d' % (int(mon[:4]) - 1, int(mon[5:7]))
                    for lab, vals in totals[1:]:
                        if lab != (int(prev[:4]), int(prev[5:7])):
                            continue
                        ok2, _ = closes(prev, vals['xetra'], vals['fwb'])
                        if ok2 and prev not in raw and prev in need_months:
                            raw[prev] = {'turnover_xetra_eurbn': vals['xetra'],
                                         'turnover_fwb_eurbn': vals['fwb']}
                            src[prev] = ('%s（%s 那篇的「去年同月」对照行）'
                                         % (title, mon))
                else:
                    rejected.append((mon, title, 'table', diff))
            if hit is None:
                pr = _parse_pr_prose(h)
                if pr:
                    ok, diff = closes(mon, pr['xetra'], pr['fwb'])
                    if ok:
                        hit = {'turnover_xetra_eurbn': pr['xetra'],
                               'turnover_fwb_eurbn': pr['fwb']}
                    else:
                        rejected.append((mon, title, 'prose', diff))
            if hit:
                raw[mon] = hit
                src[mon] = '%s（%s 发布）' % (title, d.isoformat())
                break
    return raw, src, rejected


# ── 精度闸门 ────────────────────────────────────────────────────────────────
def _precision_gate(raw):
    """按 (列, 小数位) 分组判「这一组够不够精确」，返回 (通过的值, 决策表)。"""
    groups = {}
    for mon, rec in raw.items():
        for col, (v, dec) in rec.items():
            if v is None:
                continue
            groups.setdefault((col, dec), []).append((mon, v))
    decisions, keep = [], {}
    for (col, dec), items in sorted(groups.items()):
        half = 0.5 * 10 ** -dec
        lo = min(v for _m, v in items)
        rel = half / lo if lo > 0 else float('inf')
        ok = rel <= PRECISION_MAX_REL
        decisions.append((col, dec, len(items), lo, rel, ok,
                          min(m for m, _v in items), max(m for m, _v in items)))
        if ok:
            for mon, v in items:
                keep.setdefault(mon, {})[col] = v
    return keep, decisions


# ── CSV ─────────────────────────────────────────────────────────────────────
def _read_csv():
    with open(SERIES_CSV, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    return rows[0], [r for r in rows[1:] if r and r[0].strip()]


def _write_csv(header, body):
    with open(SERIES_CSV, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        w.writerows(sorted(body, key=lambda r: r[0]))


def _months_between(a, b):
    return F._months_between(a, b)


# ── 主流程 ──────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true', help='只打印，不写文件')
    ap.add_argument('--refresh', action='store_true', help='忽略 cache，强制重下')
    ap.add_argument('--cache', default=os.path.join(ROOT, 'cache'), help='cache 目录')
    args = ap.parse_args()
    cache_dir = os.path.abspath(args.cache)
    os.makedirs(cache_dir, exist_ok=True)

    header, body = _read_csv()
    idx = {c: i for i, c in enumerate(header)}
    missing = [c for c in ALL_COLS + [LEDGER] if c not in idx]
    if missing:
        raise BasefillError('series/db1.csv 里没有这些列：%s' % missing)
    have = {r[0]: r for r in body}
    ledger = {}
    for m, r in have.items():
        v = r[idx[LEDGER]].strip()
        if v:
            ledger[m] = float(v)

    def blank(col, mon):
        return not (have.get(mon) or [''] * len(header))[idx[col]].strip()

    before = {c: sorted(m for m in have if not blank(c, m)) for c in ALL_COLS}

    print('== 腿 A：web.archive.org 上的官方工作簿存档副本 ==')
    wb_vals, wb_src, wb_worst = _leg_wayback(cache_dir, args.refresh)
    print('   %d 个月带出场所级/分类值，%s → %s' % (len(wb_vals), min(wb_vals), max(wb_vals)))
    print('   闸门 2（跨文件一致，容差 %.0e €bn）最大分歧 %.2e €bn %s'
          % (XFILE_TOL, wb_worst[0], wb_worst[1] or '（无重叠月分歧）'))

    # 闸门 1 也要罩住腿 A：存档件同样可能被我们解析错场所列
    for mon in sorted(wb_vals):
        x = wb_vals[mon].get('turnover_xetra_eurbn')
        f = wb_vals[mon].get('turnover_fwb_eurbn')
        L = ledger.get(mon)
        if x is None or f is None or L is None:
            continue
        if abs(x + f - L) > 1e-4:
            raise BasefillError('闸门 1 不过（腿 A）：%s Xetra %.6f + FFM %.6f = %.6f，'
                                '台账 %.6f，差 %.6f' % (mon, x, f, x + f - 0, L, x + f - L))

    # 闸门 3b：腿 A 与 CSV 已有满精度值逐格比对。存档件与 live 件是同一条产线出的
    # 同一份文件，重叠格必须**逐位相等**（不是「四舍五入界内」）——
    # 这是「archive.org 上那份到底是不是官方原件」唯一的机器答案。
    # 首次回填时重叠 10 格（2024-01~2024-05 的两条场所列，来自 20240531 那期的
    # 「本年度逐月」块 vs live 20241231 那期的同一块），本轮 0 例不一致。
    print('== 闸门 3b：腿 A vs CSV 已有满精度值 ==')
    n3b = bad3b = 0
    for mon in sorted(wb_vals):
        for col, v in sorted(wb_vals[mon].items()):
            if blank(col, mon):
                continue
            n3b += 1
            cur = float(have[mon][idx[col]])
            if abs(cur - v) > 1e-9:
                bad3b += 1
                print('   × %s %s CSV %.9f vs 存档件 %.9f' % (mon, col, cur, v))
    print('   重叠 %d 格，逐位不一致 %d 格' % (n3b, bad3b))
    if bad3b:
        raise BasefillError('闸门 3b 不过：存档件与既有值逐位对不上，先查再写盘')

    need = [m for m in _months_between(TARGET_FROM, max(have))
            if blank('turnover_xetra_eurbn', m) and m not in wb_vals]
    print('== 腿 B：同站月度现货新闻稿 ==')
    pr_raw, pr_src, pr_rej = _leg_press(cache_dir, args.refresh, ledger, set(need))
    print('   %d 个月过了台账闭合闸门；%d 篇候选被闸门挡下'
          % (len(pr_raw), len(pr_rej)))
    for mon, title, kind, diff in pr_rej:
        print('     × %s %-6s %-58s 残差 %s'
              % (mon, kind, title[:58], '—' if diff is None else '%+.4f' % diff))

    pr_vals, decisions = _precision_gate(pr_raw)
    print('== 精度闸门（半宽 ≤ %.0f%% × 组内最小值）==' % (PRECISION_MAX_REL * 100))
    print('   %-34s %3s %4s %10s %8s %s  %s'
          % ('列', '小数', '月数', '组内最小值', '相对半宽', '判定', '覆盖'))
    for col, dec, n, lo, rel, ok, m0, m1 in decisions:
        print('   %-34s %3d %4d %10.4f %7.2f%% %s  %s→%s'
              % (col, dec, n, lo, rel * 100, '入库' if ok else '丢弃', m0, m1))

    # 闸门 3：新闻稿的四舍五入值 vs **任何一个满精度参照**（CSV 里已有的值，
    # 或腿 A 存档件给出的值）。这是唯一能发现「解析错行但恰好也过了台账闭合」
    # 的办法 —— 相当于拿一百多个月做了一次独立复核。
    #
    # 只有「精度闸门放行、真的会写进 CSV」的格子才有资格让脚本停下来；
    # 已经被精度闸门丢掉的格子照样打印（它仍是解析健康度的信号），但不拦。
    # 首次回填时唯一一例就是这种：2022-05 的法兰克福 bonds 存档件写 0.242953，
    # 而当月新闻稿那一格印 0.3（四舍五入应该是 0.2）—— 官方自己两处不一致，
    # 而这一格属于「1 位小数的法兰克福 bonds」，早就被精度闸门整组丢掉了。
    print('== 闸门 3：新闻稿值 vs 满精度参照 ==')
    bad3, conflicts, today = [], [], datetime.date.today().isoformat()
    n3 = 0
    for mon, rec in sorted(pr_raw.items()):
        for col, (v, dec) in rec.items():
            if v is None:
                continue
            if blank(col, mon):
                ref = wb_vals.get(mon, {}).get(col)
                where = '存档件'
            else:
                ref, where = float(have[mon][idx[col]]), 'CSV'
            if ref is None:
                continue
            n3 += 1
            if abs(ref - v) <= 0.5 * 10 ** -dec + 1e-9:
                continue
            kept = pr_vals.get(mon, {}).get(col) is not None
            bad3.append((mon, col, kept))
            print('   %s %s %-32s %s %.6f vs 新闻稿 %s（差 %+.6f）%s'
                  % ('×' if kept and mon not in KNOWN_RESTATEMENTS else '△',
                     mon, col, where, ref, v, v - ref,
                     '' if kept else '  ← 该格已被精度闸门丢弃，仅记录'))
            conflicts.append([mon, col, F._fmt(ref), str(v),
                              '月度现货新闻稿（build/basefill/db1_spot_2016.py）', today])
    unknown = sorted({m for m, _c, kept in bad3 if kept} - KNOWN_RESTATEMENTS)
    print('   比对 %d 格，超出四舍五入界 %d 格；已知重述月 %s，未知 %s'
          % (n3, len(bad3),
             sorted({m for m, _c, _k in bad3} & KNOWN_RESTATEMENTS) or '无', unknown or '无'))
    if conflicts and not args.dry:
        F._record_conflicts(cache_dir, conflicts)
        print('   证据已写 %s' % os.path.join(cache_dir, F.RESTATEMENT_LOG))
    if unknown:
        raise BasefillError('闸门 3 不过：%s 与满精度参照对不上且不在已知重述名单里，'
                            '先查解析再写盘' % unknown)

    # ── 合并：腿 A（满精度）优先，腿 B 只填腿 A 够不到的空 ──
    merged, prov = {}, {}
    for mon in sorted(set(wb_vals) | set(pr_vals)):
        for col in ALL_COLS:
            v = wb_vals.get(mon, {}).get(col)
            s = wb_src.get(mon, {}).get(col)
            if v is None:
                v, s = pr_vals.get(mon, {}).get(col), pr_src.get(mon)
            if v is None or not blank(col, mon):
                continue
            merged.setdefault(mon, {})[col] = v
            prov.setdefault(mon, {})[col] = s

    print('== 待写入 ==')
    for col in ALL_COLS:
        ms = sorted(m for m in merged if col in merged[m])
        print('   %-34s +%3d 个月  %s' % (col, len(ms), '%s→%s' % (ms[0], ms[-1]) if ms else '—'))

    if args.dry:
        print('\n--dry：不写文件')
        return merged, prov

    for mon in sorted(merged):
        row = have.get(mon)
        if row is None:
            raise BasefillError('%s 这一行在 CSV 里不存在 —— 本脚本只填空，不建行' % mon)
        for col, v in merged[mon].items():
            row[idx[col]] = F._fmt(v)
    _write_csv(header, body)
    print('\n写入 %s' % SERIES_CSV)

    header2, body2 = _read_csv()
    have2 = {r[0]: r for r in body2}
    for col in ALL_COLS:
        now = sorted(m for m in have2 if have2[m][idx[col]].strip())
        was = before[col]
        print('   %-34s %s → %s（%d → %d 个月）'
              % (col, was[0] if was else '—', now[0] if now else '—', len(was), len(now)))
    return merged, prov


if __name__ == '__main__':
    main()
