# -*- coding: utf-8 -*-
r"""联发科（MediaTek，2454.TW）月度营收 —— 无人值守抓取模块。

对应 build/specs/mtk.py（页面由通用底座 build/single.py 生成），维护一个序列文件：

  series/mtk.csv    month, revenue_ntd_mn

单位是**新台币百万元的整数**，与公司自己公告的单位逐字相同（见口径坑 1）。

────────────────────────────────────────────────────────────────────────
数据源
────────────────────────────────────────────────────────────────────────
落地页（一个页面同时挂着下面 1) 2) 两类 PDF，一次请求全拿到）
  https://www.mediatek.com/investor-relations/financial-information
  注：旧域名 corp.mediatek.com 的同名路径 301 到 www.mediatek.com；
  corp.mediatek.com/investors 则是 **HTTP 404 + 137,108 字节的通用壳页**，
  状态码与体积两个判据方向相反，只有内容判据靠得住（见口径坑 4）。

1) 主源 —— 月度营收新闻稿 PDF，一月一份
   .../hubfs/MediaTek Assets/Pdfs/Monthly Reports/<YYYY>/Monthly Sales Revenue <Month>, <YYYY>.pdf
   命名从 2021-01 到 2026-07 **67 个月一字未变**（实测逐月下载解析，无一例外）。
   正文含五类字段，本模块把它们全部当作互相印证的护栏用（口径坑 2）：
     ① 电头日期      "Hsinchu, Taiwan, August 10, 2026– MediaTek Inc. (TWSE: 2454)…"
     ② 头条句        "net sales for July 2026 totaled NT$48,475 million."
     ③ 当月/去年同月/YoY   "July  48,475  43,220  12.16%"
     ④ YTD 两期/YoY       "January through July  349,808  346,901  0.84%"
     ⑤ 上月/MoM           "Net Sales  48,475  58,012  -16.44%"
   其中 ⑤ 的「上月」一格是**白送的重述体检**：它必须与库里上一个月逐字相等。

2) 回补源 —— 年度汇总 PDF，一年一份，含该年全部 12 个月
   .../hubfs/MediaTek Assets/Pdfs/Monthly Reports/<YYYY>/<YYYY>-Conslolidated-financial-details.pdf
   （"Conslolidated" 是上游自己的拼写错误，别"顺手修好"，改了就 404。）
   2021-01 之前没有单月新闻稿，series 的 2018-01…2020-12 共 36 个月全部由它回补。
   **每年 1 月改一次命名**（口径坑 3），所以它只当回补与交叉核对，不当主源。

3) 交叉校验源（只读不写，失败只告警不阻断）
   TWSE OpenAPI https://openapi.twse.com.tw/v1/opendata/t187ap05_L
   全市场当期一份 JSON，单位新台币千元，只有最新一期、没有历史。
   2454 是本国公司，在 t187ap05_L 里（外国发行人走 TPEx 的 _O 端点）。
   实测 2026-07：OpenAPI 48,474,930 千元 → 48,475 百万元，与新闻稿逐字相等；
   累计 349,808,051 千元 → 349,808，与新闻稿 YTD 逐字相等。

4) 全历史第三源（本模块不调用，只在对账时手工用过，记在这里省得下一个人再找）
   MOPS 月营收全市场月表 —— **主机名是 mopsov**，不是 mops：
     https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_<民國年>_<月>_0.html
   mops.twse.com.tw 的同一路径返回 404（431 字节 Tomcat 页）。
   编码 Big5，单位新台币千元，逐月一份、有全历史；单次响应 ~40 万字节、耗时约 20 秒。
   建库时用它把 2018-01…2026-07 全部 103 个月逐月拉过一遍：
   **103/103 个月与本序列（百万元整数）四舍五入后逐格相等**，最大偏差 0.494 百万元
   （2019-09），全部 < 0.5 —— 即本序列的每一格都恰好是官方千元数的四舍五入。
   不进 update()：一次全量要 103 个请求 / 40MB / 半小时，护栏价值不抵这个代价，
   月度增量用第 3) 条的 OpenAPI 就够。

────────────────────────────────────────────────────────────────────────
发布节奏
────────────────────────────────────────────────────────────────────────
台湾《证券交易法》要求次月 10 日前公告上月营收，联发科的实际惯例就是**踩着次月 10 日**，
10 日撞周末/假日时顺延到 11 或 12 日。67 份新闻稿电头日期的实测分布：

    次月第 7 天  2 次 │ 第 8 天  9 次 │ 第 9 天  9 次
    次月第 10 天 42 次 │ 第 11 天 4 次 │ 第 12 天 1 次

  · 常规月最晚第 11 天（2022-01→2022-02-11、2022-03→04-11、2022-09→10-11、
    2023-09→10-11）。
  · 季末月最晚第 12 天（2021-03→2021-04-12，唯一一次）。
  → 调度：roster LAG 取 (12, 12)，刚好盖住两侧的最坏情形。
  → 但**不要拿「次月 10 日」外推公告日**，顺延不规律，公告日一律从新闻稿电头现读。

────────────────────────────────────────────────────────────────────────
口径坑（踩过的，别再踩）
────────────────────────────────────────────────────────────────────────
1. **公司公告的单位就是新台币百万元的整数，本序列照存，不去凑千元精度。**
   新闻稿与年度汇总 PDF 都只给到百万元整数（48,475）；TWSE OpenAPI / MOPS 给的是
   千元（48,474,930）。两者当然对得上，但**混着存会造成假精度**：主源只能给整数，
   回补源也只能给整数，唯独最新一个月能拿到千元 —— 序列的有效位随月份跳变，
   而任何图都看不出来。所以统一存整数百万元，代价是逐月各带 ±0.5 的舍入。
   这个代价已经量化过（下面第 5 条），比假精度小得多，也让页尾核对表可以与官方 PDF
   **逐格逐字**对读。

2. **一份新闻稿里五类字段互相咬合，全部拿来当护栏。** 只认「HTTP 200」等于没有护栏。
   本模块对每一份新闻稿要求：标题月份 = 头条句月份 = 表头月份；头条句金额 = 当月行
   金额 = MoM 行当月格；YoY / MoM 两个百分比与金额倒算的结果偏差 ≤ 0.02pp；
   MoM 行的「上月」格与库内上一月**必须逐字相等**。任何一条不过就抛异常。
   （PDF 是文本层 PDF，`fitz` 抽出来是逐格一行，不依赖 `-layout` 的列对齐。）

3. **年度汇总 PDF 每年 1 月改一次命名，且落地页上挂的那个 href 可能就是死链。**
   实测 2026-08-13：
     2018–2024：`<YYYY>-Conslolidated-financial-details.pdf`（连字符）→ 200
     2025：落地页 href 写的是 `2025 Conslolidated financial details.pdf`（空格）→ **404**；
           只有连字符版 `2025-Conslolidated-financial-details.pdf` → 200（146,352 字节）
     2026：只有空格版 `2026 Conslolidated financial details.pdf` → 200；
           连字符版 → 404
   两种拼写与两种 hubfs 前缀（`/hubfs/MediaTek Assets/…` 与
   `/hubfs/728015/MediaTek Assets/…`，两者都可用）组合共 4 个候选，本模块逐个试。
   → 而且这条正是「年度 PDF 不能当主源」的理由：它每年有一个月是薛定谔的。
   → 取不到时**只告警不抛异常**：主源（月度新闻稿）与第 2 条的护栏仍然独立成立。

4. **HTTP 状态码与响应体积在这个站上会同时骗人，只有内容判据可信。**
   · `corp.mediatek.com/investors` → **404 但 137,108 字节**（HubSpot 通用壳页），
     按「体积够大就是真页」判会当场吃进一个壳页。
   · hubfs 上不存在的 PDF → 404 + **102 字节**，按「状态码 200 才失败」判倒是能拦住，
     但拦不住上面那种。
   → 本模块两道都要：`min_bytes` + `must_contain` 内容标记。落地页要求 ≥200,000 字节
     **且**含 'Monthly Sales Revenue'；PDF 要求 ≥20,000 字节**且**抽出的文本含
     'MediaTek Inc. Monthly Sales Report'（月报）/ 'Unit: NTD Million'（年报）。

5. **月度加总与官方年度/季度对得上，残差纯粹来自第 1 条的百万元舍入。**
   逐年（月度加总 NT$mn vs 该年 Q4 合并报表 Net sales）：
     2018 238,056 vs 238,057.346  (−1.346)   2022 548,796 vs 548,796.030  (−0.030)
     2019 246,222 vs 246,221.731  (+0.269)   2023 433,446 vs 433,446.330  (−0.330)
     2020 322,146 vs 322,145.988  (+0.012)   2024 530,585 vs 530,585.886  (−0.886)
     2021 493,414 vs 493,414.582  (−0.582)   2025 595,966 vs 595,965.682  (+0.318)
   最大 |残差| 1.346 百万元 = 该年营收的 0.00057%，且 12 个各带 ±0.5 的舍入相加的
   理论上界正是 ±6。逐季 32 个季度最大 |残差| 1.124 百万元（2024Q4）。
   把同样 8 年改用**千元精度**的 MOPS 月表重算，逐月加总与审计年报 Net sales
   **八年逐年 diff = 0**（238,057,346 / 246,221,731 / 322,145,988 / 493,414,582 /
   548,796,030 / 433,446,330 / 530,585,886 / 595,965,682 千元，八对逐字相等）；
   2026 前 7 月 349,808,051 千元 = TWSE OpenAPI 累计，2026H1 301,333,121 千元 =
   2026Q2 合并报表。⇒ 百万元级的那点残差 100% 是舍入，不是口径缺口。
   ⇒ 本页的季度聚合、YTD、TTM 同比全部合法，**不需要「月度不可加总」那类免责**。
   对照组是同为台股半导体的世芯-KY（3661），那家十二个月相加与官方本年累计差 +0.378%，
   因为它功能货币是美元、新台币月营收是逐月折算值。联发科合并财报附注原文：
   「The Company's consolidated financial statements are presented in NT$, which is also
   the parent company's functional currency.」 —— 母公司功能货币即新台币。
   （MOPS 上 2454 那行的备注写着「海外子公司之營收係以當月平均匯率換算之」，
   说的是海外子公司这一层用当月平均汇率折算；上面八年的对账说明这层折算**不产生**
   月度与年度之间的口径缺口。这是实测结论，不是推定。）

6. **序列起点 2018-01。**（原文写的是「理由是会计准则」——
   ⚠️ **2026-08-13 更正：这条理由站不住，别再往下传。** 联发科确实自 2018-01-01 起适用
   IFRS 15 并采修正追溯法、比较期不重编，但 FY2018 合并财报的转换附注原文是
   「IFRS 15 has **no impact** on the Company's revenue recognition from sale of goods」：
   影响只有（a）预收款重分类到合约负债 NT$1,058mn（纯资产负债表科目搬家）、
   （b）劳务收入按完工比例的差异使期初保留盈余减少 NT$211mn（≈ 一年营收 0.09%，
   且进的是权益不是营收）；2017 与 2018 的 Net sales 并排列在同一张表上、未重编，
   逐月营收的口径没有断。
   同一条更正已写进 build/mrspecs/mtk.py 的页尾说明与 build/mtk.py 的壳注释；
   build/specs/mtk.py 里的旧说法**已废弃**。）

   ⚠️ **2026-08-18 再更正：START_MONTH 已从 2018-01 前推到 2016-01。**
   上一版把 2018-01 的理由改成了「2016–2017 有合并范围变动，而确切月份没从官方原文核到」。
   那两个月份**这一轮核到了**，全部取自 MOPS 电子书的申报原件（不是新闻转述）：
     · 立錡科技并表 = **2015-10-07**，不是媒体说的 2016 年第 2 季。FY2015 合并财报
       附注六.21 原文：「本公司於民國一○四年十月七日取得立錡科技51%之股權，
       **並自該日起**將立錡科技列入合併財務報表編製主體。」2016-04-29 的股份轉換只是
       51%→100%，FY2016 附注定性为「權益交易」「對立錡科技之控制力並無影響」。
       ⇒ 它落在 2016-01 起点**之前**，窗口内没有台阶，只影响同比（见 mrspecs 的 _N_START）。
     · 傑發科技（AutoChips）出表 = **2017-03**（买方四維圖新 002405 公告钉在 2017-03-02
       完成过户并自该日起并表；卖方联发科四份财报都只写到「一○六年三月」，没有给日）。
   同一轮另外挖出两条**原任务书没提**的合并范围变动，都在新窗口内、都已登记进
   mrspecs 的 breaks：奕力科技 2016-06-01 并表（基准日就是月首，整月台阶，≈FY2016 的 2.85%）、
   絡達科技 2017-03-14 并表（≈FY2017 的 2.73%，与傑發出表**同月且方向相反**）。
   ⇒ 「2016–2017 口径不明」这条理由**已经不成立**，别再拿它挡回补。

   往前还能到 **2013-01**（MOPS t21sc03 的档案地板，实测 102_1 有档、101_12 无档；
   年度汇总 PDF 2013/2014/2015 三份也都是 200 且 `_parse_annual` 各解出 12/12）。
   没有一并做，是因为 2013–2015 那三年至少还有曜鵬科技（2015-05 并表）与常憶科技
   （2015-09-10 取得 100%）两条合并范围变动**本轮没核**，而且要按本页规矩逐条核到
   官方原文才能登记。要往前接就先补这一步，别只改 START_MONTH。

7. **2018-01 之后仍有三次并表/出表，任务书里"无口径事件"那句是错的，逐条核过：**
   · **2020-12：奕力科技（ILI Technology）出表。** 2020-07-31 董事会决议以 US$138mn
     出售 ILI Technology Holding Corporation，**2020-11-30 完成股权移转**，
     处分利益 NT$206,451 千元。规模：ILI Technology Corporation 2019 年营业收入
     **NT$10,695,950 千元**（2019 年报「关系企业营运概况」表），约当联发科 2019 年
     合并营收的 **4.3%**。→ 2020-12 起的月营收不含 ILI，登记进 breaks。
   · **2021-02：星宸科技（Sigmastar）出表。** 2020-09 处分股权至 50%，
     **2021-02 丧失控制**转列关联企业。规模：厦门星宸 2020 年营业收入
     **NT$6,645,994 千元**（2020 年报同一张表），约当联发科 2020 年合并营收的 **2.1%**。
     → 2021-02 起的月营收不含星宸，登记进 breaks。
   · **2024-07：IC PLUS（IC+）并表。** 络达科技持股 29.26% + 联发科 13.61%、
     过半董事席次，**自 2024-07-01 取得实质控制**并入合并个体。规模：
     2024-07-01 至 2024-12-31 贡献营收 **NT$338,827 千元**（2024 年报企业合并附注），
     约当同期月营收的 **0.13%**；同附注给的 2024 全年备考营收 530,891,100 千元 vs
     实际 530,585,886 千元，差 305,214 千元。→ 量级只有前两者的三十分之一，
     但仍登记进 breaks（断点标签里直接写出 +0.13%，读者不会把它误读成大事）。
   这三次都是**当期起生效、比较期不重编**，所以受影响的是跨断点那 12 个月的同比，
   不是水平值。

8. **重述体检**：与已入库值不一致时**抛异常**，不悄悄改写、不追加 —— 同
   fetch/tsm.py 口径坑 6 与 fetch/guc.py 的 drift 检查。三条互相独立的检查同时跑：
   ① 当年年度汇总 PDF 的每一个月 vs 库内同月；
   ② 每份新增新闻稿 MoM 行的「上月」格 vs 库内上一月；
   ③ 库内最近 `RECHECK_MONTHS` 个月各自重新下载新闻稿逐月比对（2021-01 起才有稿）。
   ①③ 任何一条对不上就整次不写入，由人判断是重述还是解析变形。

9. **幂等**：没有新月份时 update() 不打开写句柄，series CSV 字节级不变（验收项）。

10. **www.mediatek.com 没有 WAF**，裸 urllib 带一个普通 UA 直接 200。
   但 hubfs 路径里的空格与逗号必须 percent-encode（`%20` / `%2c`），
   直接把带空格的 URL 丢给 urllib 会抛 InvalidURL。

11. **公告日走 series/source_dates.csv，不许拿构建日或次月 10 日外推。**
   页面抬头那句「官方发布于 YYYY-MM-DD」是一句关于外部世界的事实断言，
   只能来自新闻稿正文电头（"Hsinchu, Taiwan, August 10, 2026–"）。
   顺延不规律（第 7 天到第 12 天都出现过），按「次月 10 日」外推会印出错日期，
   而错日期看上去完全正常。重述体检 ③ 每次都会重下最近 `RECHECK_MONTHS` 份稿，
   电头日是白送的，所以台账**每跑一次自动补齐最近三个月**、不依赖「这次有没有新月份」。
"""

from __future__ import annotations

import csv
import datetime
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ORIGIN = 'https://www.mediatek.com'
IR_PAGE = ORIGIN + '/investor-relations/financial-information'
TWSE_API = 'https://openapi.twse.com.tw/v1/opendata/t187ap05_L'
TWSE_CODE = '2454'

START_MONTH = '2016-01'
COLUMNS = ['month', 'revenue_ntd_mn']

#: 每次 update() 额外重新下载几个**已入库**月份的新闻稿做重述体检。
#: 3 份 ≈ 300KB，换一次与年度 PDF 命名轮盘无关的独立护栏，值。
RECHECK_MONTHS = 3

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')

# 落地页实测 630,811 字节；壳页 137,108 字节。阈值取两者之间偏低处，
# 但**体积从来不是唯一判据**，永远配一个内容标记（口径坑 4）。
_MIN_HTML = 200_000
_MIN_PDF = 20_000
#: 年度汇总 PDF 的体积下限单列，比月度新闻稿低。
#: 不是放松把关，是因为**这两类文件的体积分布本来就不同**：月度新闻稿有固定抬头 + 三张表，
#: 实测都在 20KB 以上；年度汇总只有一张 12 行的表，2015 那份 19,201 字节、2016 那份
#: **18,776 字节**，都在 _MIN_PDF 之下。共用 20,000 的直接后果是 2016 年那份永远取不到，
#: 而 update() 的重述体检①对往年是 `required=True` —— 也就是说只要 2016 进了库，
#: 每个月的例行跑都会在这一步硬失败，把整家打成 FAIL（不是少一个月，是整家不更新）。
#: 体积从来不是唯一判据（口径坑 4）：真正把关的是内容标记 _ANN_MARK，它在这三份里都在。
_MIN_ANN_PDF = 15_000

_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
           'July', 'August', 'September', 'October', 'November', 'December']
#: 年度汇总 PDF 的行首月份标签 —— 6/7/9 月是缩写与全称混用的，照抄上游
_ANN_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'June',
               'July', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

_PR_MARK = 'MediaTek Inc. Monthly Sales Report'
_ANN_MARK = 'Unit: NTD Million'


class MtkFetchError(RuntimeError):
    """本模块的故障出口。抓不到 / 认不出来一律抛它，不返回 None 掩盖故障。"""


# ══════════════════════════════════════════════════════════════════════════════
# HTTP
# ══════════════════════════════════════════════════════════════════════════════
def _get(url, *, tries=3, min_bytes=0, quiet=False):
    """取 URL。体积不够直接判失败；内容判据由调用方在解析层再加一道。

    `quiet=True` 用于「预期可能不存在」的候选 URL（年度 PDF 的四种拼写），
    抛出的异常由调用方吞掉。
    """
    safe = urllib.parse.quote(url, safe=':/?=&%')
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(safe, headers={'User-Agent': _UA})
            body = urllib.request.urlopen(req, timeout=120).read()
            if len(body) < min_bytes:
                raise MtkFetchError(
                    f'{url} 只有 {len(body)} 字节（<{min_bytes}）—— '
                    '疑似壳页或错误页，HTTP 状态码在这个站上不可信')
            return body
        except MtkFetchError:
            raise
        except Exception as exc:                                   # noqa: BLE001
            last = exc
    raise MtkFetchError(f'{url} 取不到：{last!r}' if not quiet else f'{url}: {last!r}')


def _pdf_text(blob, mark, what):
    """PDF → 纯文本，并校验内容标记。`fitz` 抽出来是逐格一行。"""
    try:
        import fitz
    except ImportError as exc:                                     # pragma: no cover
        raise MtkFetchError('需要 PyMuPDF(fitz) 才能解析联发科的 PDF') from exc
    try:
        with fitz.open(stream=blob, filetype='pdf') as doc:
            txt = '\n'.join(page.get_text() for page in doc)
    except Exception as exc:                                       # noqa: BLE001
        raise MtkFetchError(f'{what}：PDF 解不开（{exc!r}）') from exc
    if mark not in txt:
        raise MtkFetchError(
            f'{what}：PDF 里找不到内容标记 {mark!r}（{len(blob)} 字节）—— '
            '拿到的多半不是这份文件，别按状态码放行')
    return txt


# ══════════════════════════════════════════════════════════════════════════════
# 落地页：把两类 PDF 的链接一次抓齐
# ══════════════════════════════════════════════════════════════════════════════
def _ir_html():
    html = _get(IR_PAGE, min_bytes=_MIN_HTML).decode('utf-8', 'ignore')
    # 页面上这串是 percent-encode 过的（`Monthly%20Sales%20Revenue%20April%2c%202021.pdf`），
    # 拿解码后的字面量当内容标记会一个都匹配不到，然后误判成「页面改版了」。
    if 'Monthly%20Sales%20Revenue' not in html:
        raise MtkFetchError('落地页里没有 Monthly%20Sales%20Revenue 链接（改版？）')
    return html


def _pr_links(html):
    """{'YYYY-MM': 绝对 URL}，来自落地页上的月度新闻稿 href。"""
    out = {}
    pat = re.compile(
        r'href="([^"]*Monthly%20Sales%20Revenue%20([A-Za-z]+)%2c?,?%20?(\d{4})\.pdf)"',
        re.I)
    for href, mon, year in pat.findall(html):
        mon = mon.capitalize()
        if mon not in _MONTHS:
            continue
        out[f'{int(year)}-{_MONTHS.index(mon) + 1:02d}'] = urllib.parse.urljoin(
            ORIGIN, urllib.parse.unquote(href))
    if not out:
        raise MtkFetchError('落地页里一个月度新闻稿链接都没解析出来（改版？）')
    return out


def _pr_url(month):
    """按命名规则拼出某月新闻稿 URL —— 只在落地页没挂那一月时兜底。

    落地页只挂 2021 年起的稿，且偶尔漏挂；命名 67 个月没变过，可以拼，
    但拼出来的 URL 仍然要过 `_pdf_text` 的内容标记（口径坑 4）。
    """
    y, m = int(month[:4]), int(month[5:])
    return (f'{ORIGIN}/hubfs/MediaTek Assets/Pdfs/Monthly Reports/{y}/'
            f'Monthly Sales Revenue {_MONTHS[m - 1]}, {y}.pdf')


def _annual_urls(html, year):
    """年度汇总 PDF 的候选 URL，按可信度排序：落地页 href 优先，其余四种拼写兜底。

    每年 1 月改一次命名，而且落地页上挂的那个 href 本身可能就是死链（口径坑 3）。
    """
    cands = []
    for href in re.findall(r'href="([^"]*Conslolidated[^"]*\.pdf)"', html, re.I):
        url = urllib.parse.unquote(href)
        if f'/{year}/' in url:
            cands.append(urllib.parse.urljoin(ORIGIN, url))
    base = '/hubfs/{p}MediaTek Assets/Pdfs/Monthly Reports/{y}/{f}'
    for prefix in ('', '728015/'):
        for fname in (f'{year}-Conslolidated-financial-details.pdf',
                      f'{year} Conslolidated financial details.pdf'):
            cands.append(ORIGIN + base.format(p=prefix, y=year, f=fname))
    seen, out = set(), []
    for u in cands:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 解析
# ══════════════════════════════════════════════════════════════════════════════
def _num(s):
    return int(s.replace(',', ''))


def _rel_ok(new, old, pct, tol=0.02):
    """倒算的变动率与 PDF 印出来的百分比是否一致（PDF 只印两位小数）。"""
    if old == 0:
        return True
    return abs((new - old) / old * 100.0 - pct) <= tol


def _parse_press_release(txt, month):
    """解析一份月度新闻稿，返回 dict。五类字段互相咬合，任一不过就抛（口径坑 2）。

    返回 {'month', 'value', 'prev_value', 'ly_value', 'ytd', 'ytd_ly', 'date'}
    ——单位一律新台币百万元整数，`date` 是电头日 'YYYY-MM-DD'。
    """
    y, m = int(month[:4]), int(month[5:])
    mon = _MONTHS[m - 1]
    prev_y, prev_m = (y, m - 1) if m > 1 else (y - 1, 12)

    def need(pat, what, flags=0):
        hit = re.search(pat, txt, flags)
        if not hit:
            raise MtkFetchError(f'{month} 新闻稿里认不出{what}（版式变了？）')
        return hit

    need(rf'Monthly Sales Report\s*[–\-—]\s*{mon}\s+{y}\b', '标题月份')
    # 头条句在 PDF 里会被换行切开（"…consolidated net \nsales for July 2026…"），
    # 所以词间一律 \s+，不能写死空格。
    head = need(rf'net\s+sales\s+for\s+{mon}\s+{y}\s+totaled\s+NT\$([\d,]+)\s+million',
                '头条句金额')
    need(rf'Consolidated Sales Report of\s+{mon}\s+{y}\b', '表头月份')

    row = need(rf'\n\s*{mon}\s*\n\s*([\d,]+)\s*\n\s*([\d,]+)\s*\n\s*(-?[\d.]+)%',
               '当月/去年同月/YoY 行')
    ytd = need(rf'January through {mon}\s*\n\s*([\d,]+)\s*\n\s*([\d,]+)\s*\n\s*'
               r'(-?[\d.]+)%', 'YTD 行')
    mom = need(rf'{mon}\s+{y}\s*\n\s*{_MONTHS[prev_m - 1]}\s+{prev_y}\s*\n\s*'
               r'MoM Change%\s*\n\s*Net Sales\s*\n\s*([\d,]+)\s*\n\s*([\d,]+)\s*\n\s*'
               r'(-?[\d.]+)%', 'MoM 行')
    date = need(r'Hsinchu,\s*Taiwan,\s*([A-Z][a-z]+\s+\d{1,2}),?\s*(\d{4})', '电头日期')

    val, ly = _num(row.group(1)), _num(row.group(2))
    if _num(head.group(1)) != val:
        raise MtkFetchError(
            f'{month} 新闻稿自相矛盾：头条句 {head.group(1)} vs 当月行 {row.group(1)}')
    if _num(mom.group(1)) != val:
        raise MtkFetchError(
            f'{month} 新闻稿自相矛盾：当月行 {row.group(1)} vs MoM 行 {mom.group(1)}')
    if not _rel_ok(val, ly, float(row.group(3))):
        raise MtkFetchError(
            f'{month} YoY 对不上：{val} / {ly} 倒算 vs PDF 印的 {row.group(3)}%')
    prev = _num(mom.group(2))
    if not _rel_ok(val, prev, float(mom.group(3))):
        raise MtkFetchError(
            f'{month} MoM 对不上：{val} / {prev} 倒算 vs PDF 印的 {mom.group(3)}%')

    try:
        d = datetime.datetime.strptime(
            f'{date.group(1)} {date.group(2)}'.replace(',', ''), '%B %d %Y').date()
    except ValueError as exc:
        raise MtkFetchError(f'{month} 电头日期解析失败：{date.group(0)!r}') from exc
    if not (datetime.date(y, m, 28) < d < datetime.date(y, m, 28)
            + datetime.timedelta(days=60)):
        raise MtkFetchError(f'{month} 电头日期 {d} 不在该月次月的合理区间内')

    return {'month': month, 'value': val, 'prev_value': prev, 'ly_value': ly,
            'ytd': _num(ytd.group(1)), 'ytd_ly': _num(ytd.group(2)),
            'date': d.isoformat()}


def _parse_annual(txt, year):
    """解析年度汇总 PDF，返回 {'YYYY-MM': (当月, YTD)}，单位新台币百万元。

    只取本年度块；2013-2015 的旧版还带一个 Unconsolidated 块（2016 起已取消），
    这里仍然在遇到它时截断，免得将来有人拿旧年份跑本函数读串。
    """
    txt = txt.split('Unconsolidated')[0]
    out = {}
    for i, lab in enumerate(_ANN_LABELS, 1):
        hit = re.search(rf'\n\s*{lab}\s*\n\s*([\d,]+)\s*\n\s*(-?[\d.]+)%\s*\n\s*'
                        r'([\d,]+)\s*\n\s*(-?[\d.]+)%', txt)
        if hit:
            out[f'{year}-{i:02d}'] = (_num(hit.group(1)), _num(hit.group(3)))
    if not out:
        raise MtkFetchError(f'{year} 年度汇总 PDF 解析出 0 个月（版式变了？）')
    # YTD 自洽：逐月累加与印出来的 YTD 差不超过舍入上界（每月 ±0.5，n 个月 ±n/2）
    run = 0
    for i in range(1, 13):
        k = f'{year}-{i:02d}'
        if k not in out:
            break
        run += out[k][0]
        if abs(run - out[k][1]) > i / 2.0 + 1:
            raise MtkFetchError(
                f'{k} 年度汇总 PDF 内部对不上：逐月累加 {run} vs 印出的 YTD {out[k][1]}')
    return out


def _annual_months(html, year, *, required):
    """取某年的年度汇总 PDF 并解析。取不到时：required 就抛，否则告警返回 {}。"""
    errs = []
    for url in _annual_urls(html, year):
        try:
            txt = _pdf_text(_get(url, tries=2, min_bytes=_MIN_ANN_PDF, quiet=True),
                            _ANN_MARK, f'{year} 年度汇总')
        except Exception as exc:                                   # noqa: BLE001
            errs.append(f'{url.rsplit("/", 1)[-1]}: {exc}')
            continue
        return _parse_annual(txt, year)
    msg = f'{year} 年度汇总 PDF 四种拼写全部取不到（命名又改了？）：\n  ' + '\n  '.join(errs)
    if required:
        raise MtkFetchError(msg)
    print(f'[mtk][warn] {msg}')
    return {}


def _press(links, month):
    """取并解析某月新闻稿。落地页有 href 就用它，没有就按命名规则拼。"""
    urls = [links[month]] if month in links else []
    guess = _pr_url(month)
    if guess not in urls:
        urls.append(guess)
    errs = []
    for url in urls:
        try:
            txt = _pdf_text(_get(url, tries=2, min_bytes=_MIN_PDF, quiet=True),
                            _PR_MARK, f'{month} 月度新闻稿')
        except Exception as exc:                                   # noqa: BLE001
            errs.append(f'{url}: {exc}')
            continue
        return _parse_press_release(txt, month)
    raise MtkFetchError(f'{month} 月度新闻稿取不到：\n  ' + '\n  '.join(errs))


def _twse_latest():
    """TWSE OpenAPI 里 2454 的 (月份, 当月营收百万元, 累计营收百万元)。失败不阻断。"""
    try:
        blob = _get(TWSE_API, tries=2, min_bytes=100_000)
        for rec in json.loads(blob.decode('utf-8', 'ignore')):
            if rec.get('公司代號') == TWSE_CODE:
                roc = str(rec['資料年月'])                  # 11507 = 2026-07
                month = f'{int(roc[:-2]) + 1911}-{int(roc[-2:]):02d}'
                return (month,
                        round(float(rec['營業收入-當月營收']) / 1000.0),
                        round(float(rec['累計營業收入-當月累計營收']) / 1000.0))
    except Exception as exc:                                       # noqa: BLE001
        print(f'[mtk][warn] TWSE OpenAPI 交叉校验跳过：{exc!r}')
    return None, None, None


# ══════════════════════════════════════════════════════════════════════════════
# 对外的两个函数
# ══════════════════════════════════════════════════════════════════════════════
def _record_source_dates(series_dir, dates):
    """把新闻稿电头日记进全仓共用的 series/source_dates.csv（口径坑 11）。

    只写 mtk 自己的行，其余行由 source_dates.record 原样保留 + flock。
    **已经一致的月份不重写**：那张表是全仓共用的，每跑一次就重排一次文件
    等于把别家的行也搅进 git diff 里。写失败只告警 —— 少一句「官方发布于」
    远好过整条链 FAIL。
    """
    if not dates:
        return
    try:
        mod = _load_source_dates()
        for month, day in sorted(dates.items()):
            if mod.lookup(series_dir, 'mtk', month) == day:
                continue
            mod.record(series_dir, 'mtk', month, day,
                       f'月度营收新闻稿 "Monthly Sales Revenue '
                       f'{_MONTHS[int(month[5:]) - 1]}, {month[:4]}.pdf" 正文电头 '
                       f'"Hsinchu, Taiwan, ..." 解析所得（{day}）')
    except Exception as exc:                                       # noqa: BLE001
        print(f'[mtk][warn] source_dates 记录失败（不阻断入库）：{exc!r}')


def _load_source_dates():
    """按路径加载仓库根的 source_dates.py —— 本模块被 monthly_run 以
    spec_from_file_location 加载，那时 sys.path 上既没有 fetch/ 也没有仓库根。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def latest_month(cache_dir):                                       # noqa: ARG001
    """官方源当前最新月 'YYYY-MM'。抓不到 / 认不出来一律抛 MtkFetchError。

    判据是**新闻稿本身解析得开**，不是「落地页上挂了这个链接」—— 落地页有时先挂链接
    后传文件，只看 href 会把一个还没上传的月份报成最新月。
    """
    links = _pr_links(_ir_html())
    # 最多往前退 3 个月：再退下去说明整个源塌了，那时候该响的是异常而不是一个
    # 半年前的「最新月」—— 后者会让 monthly_run 安安静静地把页面钉在旧数据上。
    for month in sorted(links, reverse=True)[:3]:
        try:
            return _press(links, month)['month']
        except MtkFetchError as exc:
            print(f'[mtk][warn] {month} 挂了链接但取不到/认不出，往前退一个月：{exc}')
    raise MtkFetchError('落地页上最近 3 个月的月度新闻稿都取不到')


def update(series_dir, cache_dir):                                 # noqa: ARG001
    """把新月份追加进 series/mtk.csv，返回新增月份列表（升序）。

    幂等：已入库的月份不重写；既有行原样搬运；没有新月份时**不打开写句柄**，
    文件字节级不变。已有值永不覆盖 —— 与官方值不一致时抛异常（口径坑 8），由人判断。
    """
    csv_path = os.path.join(series_dir, 'mtk.csv')
    with open(csv_path, newline='', encoding='utf-8') as fh:
        rows = list(csv.reader(fh))
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    if header != COLUMNS:
        raise MtkFetchError(f'series/mtk.csv 列不对：{header} != {COLUMNS}')
    have = {r[0]: int(r[1]) for r in body}
    if not have:
        raise MtkFetchError('series/mtk.csv 是空的 —— 本模块只做增量，历史见 docstring')

    html = _ir_html()
    links = _pr_links(html)
    newest = max(links)

    # ── 重述体检 ①：**全历史**逐年年度汇总 PDF vs 库内同月 ─────────────────────
    # 一年一份、每份 ~150KB，今天 9 份、以后每年多一份 —— 换的是「上游改了 2019 年的
    # 某个月」这类静默重述也能当场撞上。只查当年会漏掉它（实测：把 2019-03 改成
    # 99999，只查当年时一声不吭地放过去了）。
    # 年份区间从 **START_MONTH 那一年**起，不是从「库里已有的最早年」起 ——
    # 后者会让 START_MONTH 往前挪时什么都不发生：新窗口那几年的年度 PDF 根本不去取，
    # 于是既没有历史可回补（见下面的回补分支），那几年的重述也永远查不到。
    years = list(range(int(START_MONTH[:4]), int(newest[:4]) + 1))
    official = {}
    for year in years:
        # 只有「今年」这一份每年 1 月玩命名轮盘，取不到只告警；往年的消失了是真信号（口径坑 3）
        official.update(_annual_months(html, year, required=(year != years[-1])))
    drift = [(m, have[m], v[0]) for m, v in sorted(official.items())
             if m in have and have[m] != v[0]]

    # ── 重述体检 ③：库内最近几个月各自重下新闻稿逐月比对 ───────────────────────
    recheck = [m for m in sorted(have, reverse=True)
               if m >= '2021-01'][:RECHECK_MONTHS]
    seen_dates = {}
    for m in recheck:
        pr = _press(links, m)
        # 电头日顺手留下：这几份稿本来就已经下载并解析过了，公告日是白送的
        # （口径坑 11 —— 页面抬头那句「官方发布于」全靠它）。
        seen_dates[m] = pr['date']
        if pr['value'] != have[m]:
            drift.append((m, have[m], pr['value']))
    if drift:
        raise MtkFetchError(
            '联发科官方值与已入库值不一致（疑似重述或解析变形），本次不写入：\n  '
            + '\n  '.join(f'{m}: 库内 {old} vs 官方 {new}'
                          for m, old, new in sorted(set(drift))[:8]))

    # ── 历史回补：年度汇总 PDF 里有、库里没有的月份 ──────────────────────────────
    # 为什么需要这一段：月度新闻稿只回溯到 2021-01（`_pr_links` 的物理边界），所以
    # 下面那个增量循环**补不了 2021 之前的任何月份**。2018-01…2020-12 那 36 行当初是
    # 人工回补进来的，`update()` 自己复算不出来 —— 也就是说 START_MONTH 是个「改了也
    # 不会生效」的常量，而看上去它像是生效的。这一段把那条路补上：`official` 本来就是
    # 为重述体检①下载的全历史年度 PDF，顺手拿它回补是零额外请求。
    #
    # ⚠️ 这样进来的月份**只有一个源**（年度汇总 PDF），没有月度新闻稿可交叉。把关的是
    #    `_parse_annual` 自己的 YTD 自洽校验（逐月累加 vs 印出的 YTD，容差 ±(n/2+1)），
    #    以及下一轮起它照样进重述体检①。**2016-01…2017-12 这 24 个月**在入库前另外做过
    #    一次独立双源核对（TWSE MOPS t21sc03 的 2454 行，24/24 逐格相等；FY2017 十二个月
    #    相加 = 238,216,318 千元 = FY2018 财报的 2017 年比较数，逐位相等），过程见
    #    build/mrspecs/mtk.py 的 _N_START。再往前（2013-01 起 MOPS 还有档）没有做这层核对，
    #    所以 START_MONTH 停在 2016-01，不是停在源的边界。
    back = sorted(m for m, v in official.items()
                  if m >= START_MONTH and m not in have and v[0] is not None)
    added, dates = [], {}
    for month in back:
        have[month] = official[month][0]
        body.append([month, str(official[month][0])])
        added.append(month)
    # 这里**不打印** —— 打印统一放在写盘成功之后那个循环里。
    # 在写盘前打印 "+2016-01 …" 会在写失败时留下一屏「补上了」的假象。

    # ── 增量 ──────────────────────────────────────────────────────────────────
    for month in sorted(links):
        # 只按「库里有没有」判，不按「比末月新不新」判 —— 后者会让历史中间的空洞
        # 永远补不上（本次交付的 CSV 无空洞，但补洞能力不该靠这个前提维持）。
        if month < START_MONTH or month in have:
            continue
        pr = _press(links, month)
        # 重述体检 ②：MoM 行的「上月」格必须与库内上一月逐字相等（白送的护栏）
        y, m = int(month[:4]), int(month[5:])
        prev = f'{y}-{m - 1:02d}' if m > 1 else f'{y - 1}-12'
        known = have.get(prev)
        if known is not None and pr['prev_value'] != known:
            raise MtkFetchError(
                f'{month} 新闻稿里的上月值 {pr["prev_value"]} 与库内 {prev} '
                f'的 {known} 不符 —— 疑似重述，本次不写入')
        # 与年度汇总 PDF 交叉：两份独立文件必须逐字相等
        if month in official and official[month][0] != pr['value']:
            raise MtkFetchError(
                f'{month} 新闻稿 {pr["value"]} 与年度汇总 PDF '
                f'{official[month][0]} 不符 —— 本次不写入')
        have[month] = pr['value']
        # YTD 交叉：本年 1..m 全在库里时才比（容忍每月 ±0.5 的百万元舍入）
        ymonths = [f'{y}-{i:02d}' for i in range(1, m + 1)]
        if all(k in have for k in ymonths):
            run = sum(have[k] for k in ymonths)
            if abs(run - pr['ytd']) > m / 2.0 + 1:
                raise MtkFetchError(
                    f'{month} YTD 对不上：逐月累加 {run} vs 新闻稿 {pr["ytd"]}')
        dates[month] = pr['date']
        body.append([month, str(pr['value'])])
        added.append(month)

    if added:
        body.sort(key=lambda r: r[0])
        with open(csv_path, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(body)
        for m in added:
            # 回补进来的月份没有新闻稿、因而没有电头日；`dates` 里查不到不是异常。
            # 原来这里写死 `dates[m]`，第一次跑历史回补时会在**写盘之后**抛 KeyError，
            # 于是 CSV 已经补上了、调度器却把这一家记成 FAIL。
            src = f'新闻稿电头 {dates[m]}' if m in dates else '年度汇总 PDF 回补，无新闻稿可交叉'
            print(f'[mtk] +{m} {have[m]:,} NT$mn（{src}）')

    # ── 公告日台账：新增月份 + 重述体检顺手带回来的最近几个月 ────────────────────
    # 写失败不阻断入库 —— 少一句「官方发布于」远好过整条链 FAIL。
    _record_source_dates(series_dir, {**seen_dates, **dates})

    # ── 交叉校验：TWSE OpenAPI（只告警，不阻断）────────────────────────────────
    tw_month, tw_val, tw_ytd = _twse_latest()
    if tw_month:
        if tw_month != newest:
            print(f'[mtk][warn] TWSE 最新月 {tw_month} 与 IR 新闻稿最新月 {newest} 不一致')
        elif tw_val is not None and abs(have.get(newest, 0) - tw_val) > 1:
            print(f'[mtk][warn] {newest} IR {have.get(newest)} vs '
                  f'TWSE {tw_val} NT$mn 不符')
        if tw_ytd is not None and tw_month == newest:
            run = sum(v for k, v in have.items() if k[:4] == newest[:4])
            if abs(run - tw_ytd) > 12:
                print(f'[mtk][warn] {newest[:4]} 逐月累加 {run} vs '
                      f'TWSE 累计 {tw_ytd} NT$mn 差得超出舍入上界')

    return added


if __name__ == '__main__':                                         # pragma: no cover
    print('latest_month:', latest_month(None))
    print('added:', update(os.path.join(ROOT, 'series'), None))
