"""不可重抓源件的存证：内容寻址、只增不改。

━━ 为什么需要它 ━━
series/*.csv 是**结论**，cache/ 是**工作副本**。工作副本里有一类文件是「源站原地覆盖、
而且历史取不回」的：

  · NDAQ 的 Monthly Reporting Sheet —— fetch/ndaq.py 顶部已记：static-file 的 uuid
    **不带月份、每月原地替换**，文件里只有「上一整年 + 本年 YTD = 19–24 个月」，
    **2025-01 之前回不去**（IR 站不留历史副本，唯一副本在 Wayback，本机 hook 硬禁）。
  · Euronext 的 IR 统计工作簿 —— fetch/enx.py:21 已记：文件名固定、不带月份、
    每月原地覆盖，永远指向最新一期。

这两个源件被下一期覆盖之后就再也拿不到。**值还在 CSV 里，但推导过程没了**：
解析器以后被发现有归属错误（这类事在姊妹仓 market-share 的 trendforce 解析器上
已经真实发生过），那边能拿归档的 raw body 离线重放逐格复核，本仓做不到 ——
因为本仓一份源件都没留。写下这个模块就是为了补上这个能力。

按 2026-08-19 实测，series/ndaq.csv 的四个 IR 列里**只剩两列还完全依赖当期 PDF**：
`vol_us_options_mmcontracts` 与 `vol_nordic_cash_value_usdbn`，覆盖 2025-01..2026-07
共 19 个月，**正好等于当期 PDF 的跨度**：2027-01 版一出，2025-01 就掉出窗口，
所以对这两列这件事没有余量。
（另两列 2026-08-18 已由**别的官方链路**回补出档案：`vol_nordic_derivs_mmcontracts`
走 Nasdaq Nordic 交易所公告档案回到 2013-01（163 个月）、`vol_us_cash_matched_mnsh`
由 B 组三盘口之和回到 2010-10（190 个月）。它们不再是「PDF 一覆盖就永远拿不回来」，
但存证照存 —— 存证要留的是**当期 IR 口径的原始字节**，不是「能不能凑出一个近似值」。）

━━ 边界 ━━
· 只存字节，不解析、不校验内容语义 —— 那是各 fetch 模块自己的事。
· **任何调用点都不许因为存证失败而中断抓取**：存证是附加能力，当期数据的正确性优先。
  所以 keep() 自己吞掉所有异常，只打印一行告警。
· 内容寻址 ⇒ 同一份字节重复抓多少次都只落一个文件，重跑不会膨胀。
· 文件只增不改：同月拿到不同字节（源站修订）会并存两份，这正是想要的 —— 修订本身
  就是需要留痕的事实，覆盖掉就看不见了。

━━ 落盘位置与备份 ━━
cache/raw/<kind>/<month|nomonth>-<sha256 前 12>.<ext>
cache/ 整个在 .gitignore 里（600 MB，不该进 git），所以这些字节的**唯一异地副本靠
dashboards-data-archive 的 backup.sh** —— 那边已相应加了一行 rsync。改这里的路径
必须同步改那边，否则存证只存在于本机，等于没存。
"""
import hashlib
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW_DIR = os.path.join(ROOT, 'cache', 'raw')

# 存证总量的软上限：单文件超过这个就不存（防止哪天有人把一个 GB 级 zip 接进来）。
# NDAQ 的 PDF 约 0.4 MB、Euronext 的 xlsx 约 2 MB，离上限很远。
MAX_BYTES = 64 * 1024 * 1024


def keep(kind, data, ext, month=None):
    """把 data 按内容寻址另存一份，返回路径；任何失败都只告警不抛。

    kind   存证子目录名，用 ticker（'ndaq' / 'enx'）
    ext    扩展名，不带点（'pdf' / 'xlsx' / 'html'）
    month  该字节对应的数据月 'YYYY-MM'；拿不到就留 None（落 'nomonth-'）。
           月份只用于让人肉眼能找到文件，**不参与去重** —— 去重只看 sha256，
           因为同一份 PDF 可能在两个月里都被下到（官方还没更新）。
    """
    try:
        if not data:
            return None
        if len(data) > MAX_BYTES:
            print('[rawkeep] ⚠ %s 源件 %.1f MB 超过 %d MB 上限，未存证'
                  % (kind, len(data) / 1e6, MAX_BYTES // 1024 // 1024))
            return None
        digest = hashlib.sha256(data).hexdigest()[:12]
        tag = (month or 'nomonth').replace('/', '-')
        d = os.path.join(RAW_DIR, kind)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, '%s-%s.%s' % (tag, digest, ext))
        if os.path.exists(path):
            return path                      # 同字节已存过：内容寻址的正常路径，不是错误
        tmp = path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)                # 原子落盘：半个存证文件比没有更糟
        return path
    except Exception as e:                    # noqa: BLE001 —— 见模块 docstring「边界」第 2 条
        print('[rawkeep] ⚠ %s 存证失败（不影响本次抓取）：%r' % (kind, e))
        return None
