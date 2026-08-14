# -*- coding: utf-8 -*-
r"""MOPS 月营收申报表「備註／營收變化原因說明」原文 —— 七家台湾半导体的序列化模块。

维护一个序列文件（**本模块独占，不碰任何 fetch/<ticker>.py 的序列**）：

  series/mops_remarks.csv
      month, ticker, co_id, remark, triggered, trigger_leg, yoy_pct, ytd_yoy_pct, co_name

一行 = 一家公司的一个申报月。七家 × 最近 24 个月 = 168 行。

────────────────────────────────────────────────────────────────────────
这个字段是什么 —— **先读这一节，不然一定会用错**
────────────────────────────────────────────────────────────────────────
MOPS「采用 IFRSs 后之月营业收入资讯」那张表的最后一栏叫「備註／營收變化原因說明」。
它**不是**公司想写就写的自由备注栏，是一条有触发条件的法定披露栏。触发规则逐字写在
同一张表的脚注第 6 条（2026-08-14 从 ajax_t05st10_ifrs 的 2330/113-08 回应体里抄下来）：

    6.上市櫃及興櫃公司，本月營收或本年累計營收較去年同期增減變動達50％以上者，
      需於備註欄位說明增減變動原因。

由此得到两条**必须写进任何引用这份数据的 brief 里**的语义，两条都在下面 168 行实测里
拿到了证据：

  ① **空（`-`）不等于「公司没解释」，只等于「未触发 50% 门槛」。**
     台积电 24 个月里 22 个月是 `-`，不是台积电惜字如金 —— 是那 22 个月的单月同比与
     累计同比都没到 ±50%，法规没要求它说。把「備註为空」读成「公司拒绝说明」是纯粹的
     误读，而这个误读在一张热力图上看起来完全正常。

  ② **有话不等于是「增减原因」。** 联发科 2454 这 24 个月**每一个月**都填了同一句
     `海外子公司之營收係以當月平均匯率換算之`，而它这 24 个月**一次都没触发**门槛
     （单月同比 −15.63% ~ +30.96%，累计同比 −11.70% ~ +29.89%，全在 ±50% 以内）。
     那是一条**常设的换算口径注**，跟当月增减一点关系都没有。把它当「联发科解释了
     营收变化」来引用，是把一句会计口径说明伪造成了经营评论。

  ⇒ 所以本序列**不只存一个字符串**。`triggered` 是「这句话是不是法定增减说明」的唯一
    判据，由当月同比与累计同比**现算**（`abs(yoy) >= 50 or abs(ytd_yoy) >= 50`），
    两个百分比就在同一份 JSON/CSV 里，不需要第二次请求、也不用信任任何缓存的结论。
    下游的判读规则只有一句：**`triggered=0` 而 `remark` 非空 ⇒ 常设口径注 / 自愿披露，
    不得当作增减原因引用。**

`trigger_leg` 再往下切一刀，说明是哪条腿越了线（`month` / `ytd` / `both` / `-`）。
它有用是因为**公司自己的措辞跟着腿走**：世芯 3661 触发的 15 个月里，措辞在
「本月營收較去年同期…」与「本年營收較去年同期…」之间来回换，和 `trigger_leg` 逐月对得上
（例：2026-03 单月 −46.57% 没越线、累计 −60.08% 越线，公司写的就是「本年營收…減少」）。

────────────────────────────────────────────────────────────────────────
数据源（三处，2026-08-14 全部实测过）
────────────────────────────────────────────────────────────────────────
1) **入库通道（历史 + 当期）** —— MOPS 全市场月营收 CSV
   POST https://mopsov.twse.com.tw/server-java/FileDownLoad
        step=9 & functionName=show_file2 & filePath=/t21/sii/
        & fileName=t21sc03_<民国年>_<月>.csv
   一个月一份**全市场**档，UTF-8 with BOM。实测 2024-08 ~ 2026-07 这 24 份：
   193,086 ~ 206,330 字节、1,064 ~ 1,087 家。最后一栏就是 `備註`。
   这条路 `fetch/nanya.py` 的 `_mops_csv()` 已经走通了，本模块照它写（含限流退避），
   区别只在：nanya 取一行，本模块取七行，并且额外落 `備註` 与两个百分比栏。

   ⚠ **这条 CSV 通道是全市场统一档，不按发行人国籍分档，含 KY 公司** —— 实测结论，
     见下面「口径坑 3」。这一点和静态 HTML 页（`_0`/`_1` 分档）**不一样**，
     而那个不一样正是这个仓库出过事故的地方。

2) **最新期探针 + 交叉核对** —— TWSE OpenAPI
   https://openapi.twse.com.tw/v1/opendata/t187ap05_L
   全市场**当期**一份 JSON（实测 597,803 字节 / 1,074 家 / 資料年月 与 出表日期
   全表唯一：11507 与 1150813），字段名与源 1 的 CSV 表头逐字相同，末栏同样是 `備註`。
   只有最新一期、没有历史，所以只用来回答两件事：
     · 官方最新月是哪个月（`latest_month()`）；
     · 已入库的最新月那 7 行的备注原文与两个百分比，有没有被上游改过（重述体检）。
   **七家全在 `_L` 里**，包括世芯-KY 3661（上市 KY）—— 见口径坑 4。

3) **单公司复核（只读不写，不进 series）** —— MOPS 单公司月营收明细
   POST https://mopsov.twse.com.tw/mops/web/ajax_t05st10_ifrs
        co_id=<代号> & year=<民国年> & month=<MM> & TYPEK=all & queryName=co_id & …
   表单其余字段见 `fetch/alchip.py` 的 `_FORM`。这一页把 `備註／營收變化原因說明`
   和「增減百分比」（本月 / 本年累計，两位小数）一起印出来，是与源 1 完全独立的
   第三条通道 —— 下面「对账」那节 168 格逐格核对走的就是它。
   ⚠ 两种版式，解析时都得认：
     · 国内公司（2330/2303/2454/2408/3443）：項目 =「營業收入淨額」，单栏新台币，
       備註 标签印全称「備註 / 營收變化原因說明」，**备注为空时后面直接接脚注 1.…6.**；
     · 上市 KY（3661）：項目 =「合併營業收入淨額」，双栏（新台币 + 功能性貨幣(美金)），
       備註 后面接「註1:」「註2:」。
     只按「合併營業收入淨額」认页会在台积电身上直接失败（实测踩过）。

────────────────────────────────────────────────────────────────────────
为什么只回补最近 24 个月（2024-08 ~ 2026-07）
────────────────────────────────────────────────────────────────────────
· 源 1 是**全市场**档：一个月一份 ~200KB / 1,000+ 家，而本模块只要其中 7 行。
  实测单份耗时 2.0 ~ 53.5 秒（含限流退避），24 份跑一轮约 5 分钟。
  按 2013-01 起全历史算是 163 份、~32MB、半小时以上，只为了多拿 139 × 7 个字符串。
· 而这个字段的用途是**给当下的月度看板做注脚**：读者在看 2026 年这几个月为什么暴增，
  不会去问 2015 年某个月公司写了什么。回补深度按用途定，不按「能抓多少」定。
· 24 个月正好覆盖两个完整的同比年，也就是每一格的 `yoy` 都有对应的去年同月在库内，
  下游要画「触发月 vs 未触发月」的对照时不缺基期。
· **首次落库 24 个月，之后每月只追加一行月份（7 行公司）；库会自然长过 24 个月，
  本模块不回删**。`_WINDOW_MONTHS` 只约束「首次/断档时最多往回补多深」。

────────────────────────────────────────────────────────────────────────
口径坑（踩过的，别再踩）
────────────────────────────────────────────────────────────────────────
1. **域名必须是 `mopsov`.twse.com.tw，而且按状态码判成功在这里完全无效。**
   `mops.twse.com.tw` 同路径会 302 到错误页，跟随后 **HTTP 200 + 65 字节**，
   或者直接 404。同一条坑 `fetch/alchip.py` 已经写过一遍。
   本模块所有校验一律是「体长下限 + 目标标记串在体内」，没有一处看 HTTP 状态码。

2. **源 1 有三种「HTTP 200 的失败」，三种都得单独认，长度判据挡不住第三种。**
   实测三种形态：
     a. **限流页 564 字节**：正文是「Overrun - 查詢過於頻繁,請稍後再試!!」。
        并发拉档必触发。→ 退避 `_MOPS_BACKOFF` 秒重试，且**顺序取档**，不并发。
     b. **未来月 / 尚未开放申报的月：HTTP 200 + 344 字节的「空表」**。
        实测 2026-08-14 当天请求 `t21sc03_115_8.csv` 与 `t21sc03_115_9.csv`，
        两次都是 200 + **344 字节，正文是一行合法的 CSV 表头、零条数据行**。
        ⚠ 这一种最阴：它**能通过「正文里有 `公司代號` 表头」这条护栏**，
        `csv.DictReader` 也能干干净净解析出 0 行，然后模块会得出
        「这个月七家一家都没申报」——一句看上去完全正常的假话。
        → 所以表头护栏**不够**，必须再加一条数据行数下限（见口径坑 5）。
     c. 网络层异常 → `_get()` 重试后抛 `MopsRemarksFetchError`。

3. **「CSV 通道含不含 KY 公司」—— 实测结论：含，而且不分档。**
   本仓的静态 HTML 页 `t21sc03_<roc>_<m>_0.html` / `_1.html` 是**按发行人国籍分档**的
   （`_0` = 國內公司 ~980 家、`_1` = 外國公司 ~93 家，世芯只在 `_1`），
   `fetch/alchip.py` 写得很清楚。**但源 1 那条 CSV 通道不是这样**：
   `t21sc03_<roc>_<m>.csv`（无后缀）是**一份统一的全市场档**，国内 + 外国合并在一起。
   证据（2024-08 ~ 2026-07 逐月实测，24/24 成立）：
     · 每份档 1,064 ~ 1,087 家，与「国内 ~983 + 外国 ~93」的量级吻合，
       而不是任何一个单独分档的量级；
     · 每份档里 `公司名稱` 含 `-KY` 的行 84 ~ 92 家，24 个月单调递增（新 KY 股陆续挂牌）；
     · **世芯-KY 3661 在 24 份档里一份不缺**，備註原文与源 3 单公司页逐格相同；
     · 每份档只有一行表头（`出表日期` 开头的行仅出现 1 次）、公司代号无重复、
       `資料年月` 全表唯一 —— 不是「国内档 + 外国档拼接」的结构。
   ⇒ 本模块七家全部走同一条 CSV 通道，不需要第二个端点，也不需要按国籍分支。

4. **世芯-KY 3661 在 `t187ap05_L` 里。** `fetch/guc.py` docstring 那句「KY 公司不在 `_L`、
   走 TPEx 的 `_O`」对**上柜**的 KY 成立，对**上市**的世芯不成立；`fetch/alchip.py`
   已经明写「别照抄那句」。本模块实测 2026-07 那期 1,074 家里七家齐全，一家不缺。

5. **行数护栏的阈值必须按「实际走的那张表」定 —— 这个仓库为此出过事故。**
   仓里曾有一条 `len(rows) < 200` 的护栏，是照 ~980 行的**国内**表定的，
   结果把 127 个**成功**的**外国**表响应（那张表只有 49 ~ 93 行）全判成失败，
   世芯整整 127 个月静默变 0。
   → 本模块的 `_MIN_ROWS = 800` 的来历，逐条写在这里：
     · 本模块走的是口径坑 3 那张**统一全市场档**，不是分国籍的任何一张；
     · 该档 2024-08 ~ 2026-07 逐月实测数据行数 **1,064 ~ 1,087**，最小值 1,064；
     · 800 = 在实测最小值下方再留约 25% 余量，够挡口径坑 2b 那张 0 行的空表
       （以及任何被截断的半截档），又远离真实档的下沿；
     · 它**不是**照 `_0` / `_1` 分档表定的。谁要把本模块改去读分档表，
       必须连这个阈值一起重定，否则就是把同一场事故再演一遍。

6. **`-` 是 MOPS 的「没填」占位符，不是内容 —— 但它不是唯一的占位符。**
   本模块把 `-`（及全角 `－`、纯空白）落成**空字符串**，其余一律原文逐字搬运。
   ⚠ 全市场范围内公司还会自己打字填「没有」：2026-07 那份档里 `備註` 长度 ≤2 的值
   分布是 `'-'` 791 家、`'無'` 6 家、`'無。'` 1 家。本模块**不**把 `無` 归一成空
   （那是公司实际填进去的字，归一就毁了「原文逐字」这条承诺），
   但七家里一旦出现 `無`/`無。`，`update()` 会打印一条 warn 提醒下游别把它当解释读。
   实测 24 个月 × 7 家里**没有出现过** —— 七家要么留 `-`，要么写完整句子。

7. **繁体不转简、标点不规整、句号有就留。**
   同一家公司同一件事的措辞逐月都在变，本模块**一个字都不动**。实测 24 个月里
   创意 3443 的 11 条备注有 **7 种**不同写法（`主要為晶圓產品收入增加` /
   `主要為晶圓產品收入增加所致` / `主要為晶圓產品(Wafer production)增加` /
   `晶圓產品(Wafer production)銷售增加` / … 有的带句号有的不带、有的夹英文括注）。
   这些差异本身就是信息（换了填表的人 / 换了口径），做任何规整都是在替公司改口。

8. **`triggered` 用未取整的原值算，落库的百分比是两位小数。**
   源 1 的百分比栏是长浮点串（`18.98196955506446`），源 3 的单公司页印的是**两位小数**
   （`增減百分比 -46.57`）。本模块落库取两位（与官方人眼可见的那个数对齐，
   168 格复核就是按两位小数对上的），但 `triggered` 用**原始未取整值**判，
   免得 49.996 这种数被四舍五入到 50.00 之后与 `triggered=0` 自相矛盾。
   实测 24 个月里最贴线的四格，两条判法结论一致、也和公司实际填没填对得上：
     2025-08 alchip 单月 −49.69% / 累计 −26.91% → 未触发，備註确实是 `-`
     2024-11 alchip 单月 +50.92%              → 触发，備註有话
     2026-05 alchip 累计 −50.05%（单月才 −33.45%）→ 触发，備註有话
     2025-10 nanya  累计 +49.30%，靠单月 +262.37% 触发 → 備註有话
   `update()` 会在任何一格的原值落进 ±50 的 ±0.005 邻域时打印 warn（`_EPS_50`），
   因为那一格的「落库两位小数」与 `triggered` 会看上去打架，需要人看一眼。

9. **`資料年月` 两条通道格式不同**：CSV 里是 `115/7`（斜杠、月份不补零），
   OpenAPI 里是 `11507`（五位、月份补零）。两种都得认，不然「取到了别的月份的档」
   这条护栏会在其中一条通道上永远误报。

────────────────────────────────────────────────────────────────────────
对账（2026-08-14 实测；数字就是数字，"看起来对"不算）
────────────────────────────────────────────────────────────────────────
A. **168 格逐格 vs 独立第三源。** 24 个月 × 7 家，每一格的 `備註` 原文与两个
   「增減百分比」都拿源 3（单公司 `ajax_t05st10_ifrs`）重新取了一遍逐字比对
   —— 见 `selfcheck()` 复算的那张表与本模块交付报告。当期那个月（2026-07）
   另外再走源 2（TWSE OpenAPI）核了一遍，七家的 `備註` 与源 1 逐字相同。

B. **`triggered` 现算 × `備註`非空 的交叉表**（24 个月 × 7 家 = 168 格）：

       triggered=1 且 備註非空   41 格   ← 法定增减说明，可当经营评论引用
       triggered=1 但 備註为空    0 格   ← 上游合规缺口；七家里一例都没有
       triggered=0 但 備註非空   24 格   ← **全部 24 格都是联发科 2454 那条常设口径注**
       triggered=0 且 備註为空  103 格

   逐家（24 个月里填了备注的月数 / 触发的月数）：
       tsm    2330    2 / 2      ase  3711    0 / 0      mtk 2454   24 / 0
       nanya  2408   13 / 13     umc  2303    0 / 0      guc 3443   11 / 11
       alchip 3661   15 / 15
   ⇒ 除联发科外的六家，「填了备注」与「触发门槛」**逐月完全等价**（0 例外）；
     联发科则是 24/24 填、0/24 触发。也就是说这张表上的「例外」只有一个形状，
     而且它恰好就是最容易被误引的那一条。

────────────────────────────────────────────────────────────────────────
幂等
────────────────────────────────────────────────────────────────────────
没有新月份时 `update()` **一个字节都不写**（既有行连重排都不做）。
已入库的行永不覆盖 —— 上游把备注原文或百分比改了，抛异常，由人判断。

━━ 依赖 ━━ 只用标准库。
━━ 接线 ━━ **本模块尚未接进 `monthly_run.py` / `build/roster.py`**，
   两个文件都不归本模块改。要接线请看文件末尾 `WIRING` 那段说明。
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

MOPS_DL = 'https://mopsov.twse.com.tw/server-java/FileDownLoad'
TWSE_API = 'https://openapi.twse.com.tw/v1/opendata/t187ap05_L'

# 本仓 slug → 台股代号。**slug 是本仓的 ticker，不是公司代号**；co_id 也落库，
# 留着和 MOPS 原表对账时不用再查一次映射。顺序 = build/roster.py 半导体组的顺序。
TICKERS = {
    'tsm': '2330',
    'ase': '3711',
    'mtk': '2454',
    'nanya': '2408',
    'umc': '2303',
    'alchip': '3661',
    'guc': '3443',
}
CO_ID_TO_TICKER = {v: k for k, v in TICKERS.items()}

COLUMNS = ['month', 'ticker', 'co_id', 'remark', 'triggered',
           'trigger_leg', 'yoy_pct', 'ytd_yoy_pct', 'co_name']

# 法定触发门槛：脚注第 6 条的「達50％以上」。`達…以上` 是闭区间，所以是 >=。
TRIGGER_PCT = 50.0
# 原值落进 ±50 的这个邻域时，落库的两位小数会与 triggered 看上去打架（口径坑 8）
_EPS_50 = 0.005

# 首次 / 断档时最多往回补多深。24 = 两个完整同比年，理由见「为什么只回补 24 个月」。
# 之后每月只追加一个月，库会长过 24 个月，本模块不回删。
_WINDOW_MONTHS = 24
MAX_BACKFILL = 24

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')

# 真档实测 193,086 ~ 206,330 字节；限流页 564 字节；未来月空表 344 字节（口径坑 2）
_MIN_CSV = 100_000
# 见口径坑 5：阈值按**统一全市场档**定，实测 1,064 ~ 1,087 行，下方留 ~25% 余量。
# **不是**照分国籍的 _0/_1 分档表定的 —— 那正是本仓出过事故的定法。
_MIN_ROWS = 800
_MIN_JSON = 100_000         # t187ap05_L 实测 597,803 字节
_MOPS_BACKOFF = 20          # 秒；命中限流页后的退避
_MOPS_GAP = 1.5             # 秒；顺序取档之间的间隔，别并发（口径坑 2a）

# MOPS 的「没填」占位符（口径坑 6）。**只归一这几个**：`無`/`無。` 是公司自己打的字，
# 归一了就毁掉「原文逐字」这条承诺，只打 warn。
_BLANK_MARKS = {'-', '－', '—', ''}
# 公司自己打字填的「没有」。不归一，只提醒。
_SELF_TYPED_NONE = {'無', '無。', '無.', 'N/A', 'NA'}

_COL_CUR = '營業收入-當月營收'
_COL_YOY = '營業收入-去年同月增減(%)'
_COL_YTD_YOY = '累計營業收入-前期比較增減(%)'
_COL_REMARK = '備註'
_COL_ID = '公司代號'
_COL_NAME = '公司名稱'
_COL_YM = '資料年月'


class MopsRemarksFetchError(RuntimeError):
    """本模块的故障出口。抓不到 / 认不出来 / 与官方对不上，一律抛它，不返回 None。"""


# ── 月份小工具（本仓不许引 dateutil，手算）────────────────────────────────
def _next_month(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return f'{y + 1}-01' if m == 12 else f'{y}-{m + 1:02d}'


def _prev_month(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return f'{y - 1}-12' if m == 1 else f'{y}-{m - 1:02d}'


def _roc_to_month(raw):
    """MOPS 的民国年月 → 公元 'YYYY-MM'。两种格式都认（口径坑 9）。

    '11507' → '2026-07'；'115/7' → '2026-07'。认不出来抛异常，不猜。
    """
    s = str(raw).strip()
    if '/' in s:
        roc, mm = s.split('/', 1)
    elif s.isdigit() and len(s) in (5, 6):
        roc, mm = s[:-2], s[-2:]
    else:
        raise MopsRemarksFetchError(f'认不出的民国年月 {raw!r}')
    try:
        return f'{int(roc) + 1911}-{int(mm):02d}'
    except ValueError as exc:
        raise MopsRemarksFetchError(f'认不出的民国年月 {raw!r}') from exc


def _month_matches(raw, month):
    """该行的 `資料年月` 是不是请求的那个月。两种格式都认（口径坑 9）。"""
    try:
        return _roc_to_month(raw) == month
    except MopsRemarksFetchError:
        return False


# ── 网络 ────────────────────────────────────────────────────────────────
def _get(url, *, data=None, timeout=180, tries=3):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(
                url, data=data, headers={'User-Agent': _UA, 'Accept': '*/*'})
            return urllib.request.urlopen(req, timeout=timeout).read()
        except Exception as exc:                                   # noqa: BLE001
            last = exc
            time.sleep(2)
    raise MopsRemarksFetchError(f'{url} 取不到：{last!r}')


# ── 源 1：MOPS 全市场月档 CSV ────────────────────────────────────────────
def _mops_csv(month, cache_dir=None):
    """取某个月的全市场月营收 CSV 正文。

    护栏（一条都不能省，理由见口径坑 1/2/5）：
      ① 体长 >= `_MIN_CSV`  —— 挡限流页（564 字节）与未来月空表（344 字节）；
      ② 正文里必须有 `公司代號` 表头 —— 挡「拿回来的根本不是这张表」；
      ③ 解析出的**数据行数** >= `_MIN_ROWS` —— 挡口径坑 2b 那种
         「表头合法、零条数据」的空表，②③ 缺一不可；
      ④ 调用方再核每一行的 `資料年月`。
    一条都不看 HTTP 状态码 —— 在 mopsov 上状态码没有判别力（口径坑 1）。
    """
    y, m = int(month[:4]), int(month[5:7])
    fname = f't21sc03_{y - 1911}_{m}.csv'
    cpath = os.path.join(cache_dir, 'mops_remarks_' + fname) if cache_dir else None

    body = None
    if cpath and os.path.exists(cpath) and os.path.getsize(cpath) >= _MIN_CSV:
        body = open(cpath, 'rb').read()

    if body is None:
        payload = urllib.parse.urlencode({
            'step': '9', 'functionName': 'show_file2',
            'filePath': '/t21/sii/', 'fileName': fname}).encode()
        for _ in range(3):
            body = _get(MOPS_DL, data=payload, tries=2)
            if len(body) >= _MIN_CSV:
                break
            head = body[:400].decode('utf-8', 'ignore')
            if 'Overrun' in head or '過於頻繁' in head:
                # HTTP 200 + 564 字节的限流页（口径坑 2a）。退避重试，
                # **不能**当成「这个月没数据」——那是把限流写成事实。
                print(f'[mops_remarks][warn] MOPS 限流（{len(body)} 字节），'
                      f'退避 {_MOPS_BACKOFF}s 后重试 {fname}')
                time.sleep(_MOPS_BACKOFF)
                continue
            raise MopsRemarksFetchError(
                f'MOPS {fname} 只有 {len(body)} 字节（<{_MIN_CSV}）—— 不是月营收档。'
                f'344 字节 = 该月尚未开放申报的空表（口径坑 2b），'
                f'564 字节 = 限流页；开头：{head[:160]!r}')
        else:
            raise MopsRemarksFetchError(f'MOPS {fname} 连续 3 次拿到限流页，本次放弃')
        if cpath:
            os.makedirs(cache_dir, exist_ok=True)
            open(cpath, 'wb').write(body)
        time.sleep(_MOPS_GAP)

    text = body.decode('utf-8-sig')
    if _COL_ID not in text:
        raise MopsRemarksFetchError(f'MOPS {fname} 里没有「{_COL_ID}」表头，版式变了？')
    return text, fname


def _mops_month(month, cache_dir=None):
    """{co_id: row}，只留本模块要的七家。

    找不到某一家 → 抛异常。理由：七家全是长期上市的大型半导体，
    `latest_month()` 又保证了这个月已经全市场汇总完毕，缺行只可能是解析/取档出了事，
    不可能是「这家没申报」。把它降级成 warn 会让整列静默变空。
    """
    text, fname = _mops_csv(month, cache_dir)
    recs = list(csv.DictReader(io.StringIO(text)))
    if len(recs) < _MIN_ROWS:
        # 口径坑 2b + 5：表头能过、行数过不去的那种 200。阈值来历见口径坑 5。
        raise MopsRemarksFetchError(
            f'MOPS {fname} 只解析出 {len(recs)} 条数据行（<{_MIN_ROWS}）。'
            f'这张是**统一全市场档**，实测 1,064~1,087 家；'
            f'0 行 = 该月尚未开放申报的空表（口径坑 2b）')

    out = {}
    for row in recs:
        row = {(k or '').strip(): (v or '').strip() for k, v in row.items()}
        cid = row.get(_COL_ID, '')
        if cid not in CO_ID_TO_TICKER:
            continue
        if not _month_matches(row.get(_COL_YM, ''), month):
            raise MopsRemarksFetchError(
                f'MOPS {fname} 里 {cid} 的 {_COL_YM} 是 {row.get(_COL_YM)!r}，'
                f'不是 {month} —— 取到了别的月份的档')
        out[cid] = row

    missing = [f'{CO_ID_TO_TICKER[c]}({c})' for c in TICKERS.values() if c not in out]
    if missing:
        raise MopsRemarksFetchError(
            f'MOPS {fname}（{len(recs)} 家）里缺 {", ".join(missing)}。'
            f'七家应全在这张统一全市场档里（口径坑 3/4），缺行只可能是取档或解析出了事')
    return out


# ── 源 2：TWSE OpenAPI（当期探针 + 重述体检）────────────────────────────
_TWSE_MEMO = {}


def _twse_current():
    """('YYYY-MM', {co_id: row})。抓不到抛异常 —— 它是 latest_month 的主探针。

    一次 `update()` 里有三处要用它（探最新月 / 重述体检 / 写完后的交叉核对），
    而它是一份 ~600KB 的全市场当期档 —— 所以按进程记一次。
    记的是**成功结果**，失败不记：失败要能被下一次调用重试到。
    """
    if 'v' in _TWSE_MEMO:
        return _TWSE_MEMO['v']
    blob = _get(TWSE_API, timeout=120)
    if len(blob) < _MIN_JSON:
        raise MopsRemarksFetchError(
            f'TWSE OpenAPI 只有 {len(blob)} 字节（<{_MIN_JSON}），疑似错误页')
    recs = json.loads(blob.decode('utf-8', 'ignore'))
    if not isinstance(recs, list) or len(recs) < _MIN_ROWS:
        raise MopsRemarksFetchError(
            f'TWSE OpenAPI 返回 {len(recs) if isinstance(recs, list) else "非列表"}，'
            f'不是全市场当期表')

    out, months = {}, set()
    for rec in recs:
        cid = str(rec.get(_COL_ID, '')).strip()
        if cid not in CO_ID_TO_TICKER:
            continue
        out[cid] = {(k or '').strip(): str(v).strip() for k, v in rec.items()}
        months.add(_roc_to_month(rec[_COL_YM]))

    missing = [f'{CO_ID_TO_TICKER[c]}({c})' for c in TICKERS.values() if c not in out]
    if missing:
        raise MopsRemarksFetchError(
            f'TWSE OpenAPI 当期名单（{len(recs)} 家）里缺 {", ".join(missing)}。'
            f'七家全是上市（含上市 KY 的世芯 3661），都该在 _L 里（口径坑 4）')
    if len(months) != 1:
        raise MopsRemarksFetchError(f'TWSE OpenAPI 七家的資料年月不唯一：{sorted(months)}')
    _TWSE_MEMO['v'] = (months.pop(), out)
    return _TWSE_MEMO['v']


# ── 字段口径 ────────────────────────────────────────────────────────────
def _clean_remark(raw):
    """MOPS 的 `備註` → 落库值。

    `-`（及全角 `－`/破折号/纯空白）是 MOPS 的**「没填」占位符，不是内容**，
    落成空字符串（口径坑 6）。其余**原文逐字**：繁体不转简、标点不规整、
    句号有就留、夹的英文括注照抄（口径坑 7）。
    """
    s = (raw or '').strip()
    return '' if s in _BLANK_MARKS else s


def _pct(raw, what, who):
    """百分比栏 → float。认不出来抛异常，绝不当 0（口径坑 8）。

    当成 0 的后果是 `triggered` 静默变 0，也就是把一句法定增减说明降级成
    「常设口径注」—— 正好是本模块存在的理由的反面。
    """
    s = (raw or '').strip().replace(',', '')
    try:
        return float(s)
    except ValueError as exc:
        raise MopsRemarksFetchError(
            f'{who} 的「{what}」是 {raw!r}，解析不出数值 —— '
            f'triggered 必须由它现算，认不出就不能入库') from exc


def _triggered(yoy, ytd_yoy):
    """(是否触发 50% 门槛, 哪条腿越线)。

    脚注第 6 条：「本月營收**或**本年累計營收較去年同期增減變動達50％以上者」——
    是**或**，两条腿任一越线即触发；`達…以上` 是闭区间，所以用 >=。
    两个百分比都在同一份 JSON/CSV 里，不用第二次请求。
    """
    a, b = abs(yoy) >= TRIGGER_PCT, abs(ytd_yoy) >= TRIGGER_PCT
    leg = {(True, True): 'both', (True, False): 'month',
           (False, True): 'ytd', (False, False): '-'}[(a, b)]
    return (a or b), leg


def _row_from(month, cid, row):
    """把 MOPS 的一行（CSV 或 OpenAPI，字段名相同）变成落库的一行。"""
    who = f'{CO_ID_TO_TICKER[cid]}({cid}) {month}'
    yoy = _pct(row.get(_COL_YOY), _COL_YOY, who)
    ytd = _pct(row.get(_COL_YTD_YOY), _COL_YTD_YOY, who)
    trig, leg = _triggered(yoy, ytd)
    return [month, CO_ID_TO_TICKER[cid], cid, _clean_remark(row.get(_COL_REMARK)),
            '1' if trig else '0', leg, f'{yoy:.2f}', f'{ytd:.2f}',
            (row.get(_COL_NAME) or '').strip()]


def _warn_edges(rows):
    """两类需要人看一眼、但不该阻断入库的情形。"""
    for r in rows:
        month, ticker, _cid, remark, _trig, _leg, yoy, ytd = r[:8]
        # ① 原值贴 ±50 太近：落库的两位小数会与 triggered 看上去打架（口径坑 8）
        for what, v in (('单月同比', float(yoy)), ('累计同比', float(ytd))):
            if abs(abs(v) - TRIGGER_PCT) < _EPS_50:
                print(f'[mops_remarks][warn] {month} {ticker} {what} {v:+.2f}% 贴着 '
                      f'±{TRIGGER_PCT:.0f}% 门槛（±{_EPS_50}），落库的两位小数与 '
                      f'triggered 可能看上去矛盾 —— 请人看一眼原值')
        # ② 公司自己打字填的「無」：不是 MOPS 占位符，会原样入库（口径坑 6）
        if remark in _SELF_TYPED_NONE:
            print(f'[mops_remarks][warn] {month} {ticker} 的備註是 {remark!r} —— '
                  f'这是公司自己填的「没有」，不是 MOPS 的 `-` 占位符，'
                  f'本模块按原文入库；下游别把它当增减说明读')


# ── 契约函数 ────────────────────────────────────────────────────────────
def latest_month(cache_dir):
    """官方源当前最新月 'YYYY-MM'。

    走 TWSE OpenAPI（源 2）—— 一次请求、当期一份、与 MOPS 月档同期。
    它的 `資料年月` 是证交所**汇总完整个市场之后**才翻的（2026-07 那期 出表日期
    1150813），所以拿它当闸门就不会去请求一个还在陆续申报、只有半截的月档。
    TWSE 挂了就退回 MOPS：从上个月往回探最多 3 个月。
    """
    try:
        return _twse_current()[0]
    except MopsRemarksFetchError as exc:
        print(f'[mops_remarks][warn] TWSE OpenAPI 探针失败，改用 MOPS 回探：{exc}')
    cursor = _prev_month(_dt.date.today().strftime('%Y-%m'))
    for _ in range(3):
        try:
            _mops_month(cursor, cache_dir)
            return cursor
        except MopsRemarksFetchError:
            cursor = _prev_month(cursor)
    raise MopsRemarksFetchError('TWSE 与 MOPS 两条探针都没能确认最新月')


def _read_series(csv_path):
    """读已入库的行。文件不存在 → 空库（首次落库）。"""
    if not os.path.exists(csv_path):
        return list(COLUMNS), []
    with open(csv_path, newline='', encoding='utf-8') as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return list(COLUMNS), []
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    if header != COLUMNS:
        raise MopsRemarksFetchError(f'series/mops_remarks.csv 列不对：{header} != {COLUMNS}')
    seen = set()
    for r in body:
        key = (r[0], r[1])
        if key in seen:
            raise MopsRemarksFetchError(f'series/mops_remarks.csv 有重复行 {key}')
        seen.add(key)
    return header, body


def _restate_check(have, cache_dir):
    """重述体检：拿 TWSE OpenAPI（源 2）核已入库的**当期**那七行。

    只查当期一个月，因为源 2 只有当期；成本是一次已经要发的请求（`latest_month`
    也走它），所以这条体检是白捡的。核不上 → 抛异常，不改写。
    上游把备注原文或百分比改了，必须由人判断是公司更正还是解析出错。
    """
    if not have:
        return
    try:
        month, recs = _twse_current()
    except MopsRemarksFetchError as exc:
        print(f'[mops_remarks][warn] 重述体检跳过（TWSE OpenAPI 取不到）：{exc}')
        return
    drift, checked = [], 0
    for cid in TICKERS.values():
        key = (month, CO_ID_TO_TICKER[cid])
        if key not in have:
            continue
        checked += 1
        want = _row_from(month, cid, recs[cid])
        if have[key] != want:
            drift.append((key, have[key], want))
    if drift:
        raise MopsRemarksFetchError(
            'TWSE OpenAPI 与已入库行不一致（上游改了备注原文 / 百分比？），本次不写入：\n  '
            + '\n  '.join(f'{k}: 库内 {old} vs 官方 {new}' for k, old, new in drift[:5])
            + '\n（已入库行永不覆盖 —— 先人工判断是公司更正还是解析出错）')
    if checked == 0:
        print(f'[mops_remarks][warn] 重述体检一格都没比到（库内还没有 {month}），'
              f'本次体检视为未执行')
        return
    print(f'[mops_remarks] 重述体检：TWSE OpenAPI {month} 逐格比对 {checked} 行，全部一致')


def update(series_dir, cache_dir):
    """把新月份追加进 series/mops_remarks.csv，返回新增**月份**列表（升序）。

    增量：只抓库里没有的月份。一个月写 7 行（七家各一行）。
    幂等：没有新月份时**一个字节都不写**（既有行连重排都不做）。
    已入库行永不覆盖 —— 与官方不一致时抛异常（`_restate_check`），由人判断。
    """
    csv_path = os.path.join(series_dir, 'mops_remarks.csv')
    header, body = _read_series(csv_path)
    have = {(r[0], r[1]): r for r in body}
    have_months = {r[0] for r in body}

    latest = latest_month(cache_dir)

    # 要补的月份：[窗口起点, latest] 里库内没有的。窗口只约束**往回补多深**，
    # 不做任何回删 —— 库里已有的更早月份原样留着（见「为什么只回补 24 个月」）。
    window_start = latest
    for _ in range(_WINDOW_MONTHS - 1):
        window_start = _prev_month(window_start)
    wanted, cursor = [], window_start
    while cursor <= latest:
        if cursor not in have_months:
            wanted.append(cursor)
        cursor = _next_month(cursor)

    if len(wanted) > MAX_BACKFILL:
        raise MopsRemarksFetchError(
            f'要补 {len(wanted)} 个月（{wanted[0]} ~ {wanted[-1]}），超过 '
            f'MAX_BACKFILL={MAX_BACKFILL}。先人工确认再放开。')

    # 重述体检放在写入之前：上游改过已入库的行就整批不写
    _restate_check(have, cache_dir)

    new_rows = []
    for month in wanted:
        recs = _mops_month(month, cache_dir)
        for cid in TICKERS.values():
            new_rows.append(_row_from(month, cid, recs[cid]))

    if not new_rows:
        newest = max(have_months) if have_months else '空'
        print(f'[mops_remarks] 无新月份（库内最新 {newest}，官方最新 {latest}），'
              f'series/mops_remarks.csv 未改动')
        return []

    _warn_edges(new_rows)
    body.extend(new_rows)
    body.sort(key=lambda r: (r[0], list(TICKERS).index(r[1])))
    os.makedirs(series_dir, exist_ok=True)
    with open(csv_path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(header)
        w.writerows(body)

    # ── 交叉核对：当期那个月的七行 vs TWSE OpenAPI（同一笔申报的另一条通道）
    try:
        tw_month, recs = _twse_current()
        if tw_month in wanted:
            bad = []
            for cid in TICKERS.values():
                want = _row_from(tw_month, cid, recs[cid])
                got = next(r for r in new_rows if r[0] == tw_month and r[2] == cid)
                if got != want:
                    bad.append((CO_ID_TO_TICKER[cid], got, want))
            if bad:
                raise MopsRemarksFetchError(
                    f'{tw_month} MOPS 月档与 TWSE OpenAPI 对不上（同一笔申报的两条通道）：\n  '
                    + '\n  '.join(f'{t}: CSV {g} vs API {w}' for t, g, w in bad[:5]))
            print(f'[mops_remarks] 交叉核对 TWSE OpenAPI {tw_month} 七行：逐字一致')
    except MopsRemarksFetchError as exc:
        if '对不上' in str(exc):
            raise
        print(f'[mops_remarks][warn] TWSE 交叉核对跳过：{exc}')

    n_trig = sum(1 for r in new_rows if r[4] == '1')
    n_rem = sum(1 for r in new_rows if r[3])
    print(f'[mops_remarks] 新增 {len(wanted)} 个月 / {len(new_rows)} 行'
          f'（{wanted[0]} ~ {wanted[-1]}）：触发 {n_trig} 行，備註非空 {n_rem} 行')
    return wanted


# ── 自检（不写任何文件；`python3 fetch/mops_remarks.py` 直接跑）────────────
def selfcheck(series_dir=None):
    """复算模块头「对账 B」那张交叉表 —— triggered 现算 × 備註非空。

    这张表是本模块唯一有判读价值的产物：它把「填了但没触发」（常设口径注 /
    自愿披露，**不得当增减原因引用**）与「触发了却没填」（上游合规缺口）分开。
    """
    series_dir = series_dir or os.path.join(ROOT, 'series')
    _, body = _read_series(os.path.join(series_dir, 'mops_remarks.csv'))
    if not body:
        print('series/mops_remarks.csv 是空的')
        return

    months = sorted({r[0] for r in body})
    cross = {(t, n): [] for t in (1, 0) for n in (1, 0)}
    per = {t: [0, 0] for t in TICKERS}          # [備註非空月数, 触发月数]
    for r in body:
        trig, nonempty = int(r[4]), 1 if r[3] else 0
        cross[(trig, nonempty)].append(r)
        per[r[1]][0] += nonempty
        per[r[1]][1] += trig

    print(f'series/mops_remarks.csv：{len(body)} 行 = '
          f'{len(months)} 个月（{months[0]} ~ {months[-1]}）× {len(TICKERS)} 家\n')
    print('交叉表  triggered（现算 |yoy|>=50 或 |ytd_yoy|>=50） × 備註非空')
    print(f'  triggered=1 且 備註非空 {len(cross[(1, 1)]):>4} 格   法定增减说明')
    print(f'  triggered=1 但 備註为空 {len(cross[(1, 0)]):>4} 格   上游合规缺口')
    print(f'  triggered=0 但 備註非空 {len(cross[(0, 1)]):>4} 格   常设口径注 / 自愿披露')
    print(f'  triggered=0 且 備註为空 {len(cross[(0, 0)]):>4} 格\n')

    for label, key in (('触发了却没填（合规缺口）', (1, 0)),
                       ('填了但没触发（不得当增减原因引用）', (0, 1))):
        hits = cross[key]
        print(f'  ── {label}：{len(hits)} 格')
        by_t = {}
        for r in hits:
            by_t.setdefault(r[1], []).append(r)
        for t, rs in sorted(by_t.items(), key=lambda kv: -len(kv[1])):
            texts = sorted({r[3] for r in rs})
            note = f'{len(texts)} 种写法' if len(texts) > 1 else repr(texts[0]) if texts else '（空）'
            print(f'       {t:<8}{len(rs):>3} 个月  {note}')
        print()

    print(f'{"ticker":<9}{"co_id":<7}{"備註非空":>9}{"触发":>7}{"共":>5}')
    for t, cid in TICKERS.items():
        n = sum(1 for r in body if r[1] == t)
        print(f'{t:<9}{cid:<7}{per[t][0]:>9}{per[t][1]:>7}{n:>5}')


# ────────────────────────────────────────────────────────────────────────
# WIRING —— 接线现状（**2026-08-14 已接完，下面是接成了什么样，不是待办**）
# ────────────────────────────────────────────────────────────────────────
# `monthly_run.py` 里有一个独立的 `mops_remarks()`，跑在**按 ticker 的循环之后**、
# `fee_rates()` 之前；它是继 `fee_rates` / `fx` 之后的**第三张公共表**。
#
# 1) **不进 `TICKERS`、不进 `build/roster.py` 的 `LAG` / `GROUPS`。**
#    本模块不是一个 ticker，序列文件也不叫 <ticker>.csv。`LAG` 全仓只有两处取值 ——
#    `roster.main()` 按 `GROUPS` 遍历（喂首页红点）与 `monthly_run.not_due()`
#    （读 `data/<t>.js` 的 `data_through`）—— 而本模块没有页、没有 data 文件、
#    没有 `data_through`，两处都取不到它。只加 `LAG` 是一行谁都不读的死配置；
#    连 `GROUPS` 一起加则首页会多一张永远空白的卡片。
#    （早先这里写着「真要登记，可沿用 ase 的 (15,15)」——**那条建议是错的，已撤回**。）
# 2) **它自己要主动重跑那七页**，这一步不能省：各家月营收在次月第 2-15 天陆续到，
#    而 MOPS 全市场汇总要等最后一家申报完（实测第 13 天）。等備註到的那天，
#    七家的 `not_due()` 早已判定「已追平 M 月」→ 全部 NOCHANGE、连 fetch 都不下。
#    不催重建的话，本 CSV 更新了而七页永远读不到，症状是**当月引文与核对表末行
#    永久缺席**（上个月的却在，因为下个月重建时补上了）。也因此不能用
#    「本轮已建过就跳过」优化 —— 循环里那次 build 读的还是旧 CSV。
#    消费者名单直接迭代本文件的 `TICKERS`，**不另抄一份**。
# 3) **失败计入 `fails` → PARTIAL，不阻断**：本序列只喂注脚（brief 一句引文 +
#    核对表一列），没有任何数值 / 图 / `data_through` 依赖它；抓不到时
#    `mrbase._remark()` 返回 None，页面一个字都不说。而且「只扣七页」这个选项
#    不存在 —— 提交是整个 data/ 一起走的，抛异常 = 34 张页今天全不发。
#
# 下游取数契约：按 `(ticker, month)` 取一行，用 `remark` + `triggered`。
# 判读规则一句话：**`triggered=0` 而 `remark` 非空 ⇒ 常设口径注 / 自愿披露，
# 不得当作「公司对本月增减的解释」引用**（实测这类 24 格全是联发科那条汇率换算注）。
# ────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    selfcheck()
