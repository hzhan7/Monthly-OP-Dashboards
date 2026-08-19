# -*- coding: utf-8 -*-
"""IBKR 官方 PDF 的下载与解析管道。

**本文件搬自 `~/.claude/skills` 下的 `IBKR月度指标/build_report.py`，原 skill 已删除。**
逐字复制该文件里被本仓库引用的部分（`UA` / `HIST_URL` / `PR_URL` / `curl` /
`LABELS` / `parse_hist_page` / `parse_pr`），注释一并保留 —— 那些注释记录的是
踩过的坑，不是装饰。skill 里出 PDF 的那一半（matplotlib 绘图、GS 版式排版、
OneDrive 落盘、`main()`）本仓库用不上，没有搬。

调用方：
  · `fetch/ibkr.py`  —— curl / HIST_URL / PR_URL / parse_hist_page / LABELS
  · `build/ibkr.py`  —— parse_pr（月度新闻稿的佣金与订单规模）、
                        parse_pr_fut_fee（期货费用占比，页尾脚注用）

`parse_pr_fut_fee` 是**本仓后加的**，原 skill 里没有；加在这里而不是 build/ 侧，
是为了让「新闻稿怎么解析」始终只有一处定义。除它以外本文件仍是逐字复制。

两边都用 `spec_from_file_location` 按路径加载本文件：`fetch/` 与 `build/` 都不在
sys.path 上（monthly_run.py 用 spec 加载 fetch 模块、用子进程跑 build 脚本），
裸 `import ibkr_source` 在 fetch 侧会 ModuleNotFoundError。

缓存目录 `cache/ibkr/`（gitignored）由本模块定义，fetch 与 build 共用同一个常量 ——
两边各写各的路径正是「fetch 下到 A、build 去 B 找」这类空转的来源。
"""
import os
import re
import subprocess

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 原 skill 的 cache/ 整个搬到这里（hist_latest.pdf + 各月 pr_YYYYMM.pdf）。
# 历史新闻稿是一月一个文件、且部分月份的链接未必还在，丢了就补不回来。
CACHE = os.path.join(ROOT, 'cache', 'ibkr')

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'
HIST_URL = 'https://www.interactivebrokers.com/mkt/getFileNew.php?file=latestMetric'
PR_URL = 'https://www.interactivebrokers.com/mkt/getFileNew.php?file={ym}MetricsPressRelease.pdf'


# ---------------- download helpers ----------------
def curl(url, dest):
    """下到临时文件 → 验过 → 才改名到 dest。**失败绝不碰 dest 已有的内容。**

    以前是直接 `curl -o dest`，失败只抛异常不清理，于是磁盘上留下一个 0 字节残骸；
    而下游（fetch/ibkr.py 与 build/ibkr.py）都用 `os.path.exists(...)` 判断「缓存在不在」，
    残骸存在就等于「已经有了」→ **永不重试**。一次瞬时 404 之后 IBKR 会永久停在旧月份，
    而调度器每天读到的都是 NOTHING_TO_DO。

    但「失败就删 dest」同样是错的：hist_latest.pdf 每次都要重下，网络抖一下就会把
    上一次成功的缓存也删掉，等于把一次瞬时故障升级成数据丢失。所以走临时文件 + 原子改名：
    成功才替换，失败时 dest 保持原样（新鲜度由调用方按内容判断，不靠文件在不在）。
    """
    tmp = dest + '.part'
    try:
        r = subprocess.run(['curl', '-sL', '--retry', '3', '--max-time', '120',
                            '-A', UA, '-o', tmp, url])
        ok = (r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) >= 5000)
        if ok:
            with open(tmp, 'rb') as f:
                blob = f.read()
            if not blob.startswith(b'%PDF'):
                # IBKR 这个端点会（至少 2026-08 起）把 PDF 包在一个 Java 序列化的
                # javax.sql.rowset.serial.SerialBlob 里吐出来：HTTP 200、
                # Content-Type 仍是 application/pdf，只是前面多了 147 字节的序列化头。
                # 实测 2026-08-03 那期是 147 字节头 + 138536 字节完整 PDF。
                # 只判大小的老写法会把整坨写进缓存，然后 fitz.open 崩在别处 ——
                # 报错点离病因十万八千里。这里直接把内层 PDF 抠出来。
                i, j = blob.find(b'%PDF'), blob.rfind(b'%%EOF')
                if i >= 0 and j > i:
                    blob = blob[i:j + 5]
                    with open(tmp, 'wb') as f:
                        f.write(blob)
                else:
                    ok = False                      # 真不是 PDF：拦截页 / 错误页
        if not ok:
            raise RuntimeError(f'download failed (not a PDF): {url}')
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# ---------------- parse historical metrics PDF ----------------
LABELS = [
    ('trading_days',  r'US Trading days'),
    ('accounts',      r'Total Accounts'),
    ('net_new',       r'Net New Accounts'),
    ('darts',         r'Total Client DARTs'),
    ('ann_dart_acct', r'Cleared Avg\. DART per Account'),
    ('opt_contracts', r'Options Contracts'),
    ('fut_contracts', r'Futures Contracts'),
    ('stk_shares',    r'Stock Shares'),
    ('equity',        r'Client Equity'),
    ('credits',       r'Client Credits\(\d\)'),
    ('margin',        r'Client Margin Loans'),
]


def parse_hist_page(page):
    text = page.get_text()
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    has_pct = '% Change' in text
    years = [int(l) for l in lines if re.fullmatch(r'20\d{2}', l)]
    year = max(years) if years else None
    numre = re.compile(r'^\$?-?[\d,]+(\.\d+)?%?$')
    out = {}
    for key, pat in LABELS:
        idx = next((j for j, l in enumerate(lines) if re.match(pat, l)), None)
        if idx is None:
            out[key] = []
            continue
        j = idx + 1
        while j < len(lines) and not numre.match(lines[j]):
            j += 1
        vals = []
        while j < len(lines) and numre.match(lines[j]):
            vals.append(float(lines[j].replace('$', '').replace(',', '').replace('%', '')))
            j += 1
        out[key] = vals[:-2] if has_pct and len(vals) >= 2 else vals
    return year, out


# ---------------- parse press release ----------------
def parse_pr(path):
    t = fitz.open(path)[0].get_text()
    mo = re.search(r'Average commission per cleared Commissionable Order.*?of \$([\d.]+)', t, re.S)
    mk = re.search(r'Stocks\s*\n([\d,.]+)\s*shares?\s*\n\$([\d.]+)\s*\nEquity Options\s*\n([\d.]+)\s*contracts\s*\n\$([\d.]+)\s*\nFutures\s*\n([\d.]+)\s*contracts\s*\n\$([\d.]+)', t)
    if not (mo and mk):
        raise RuntimeError(f'PR parse failed: {path}')
    return (float(mo.group(1)), float(mk.group(1).replace(',', '')), float(mk.group(2)),
            float(mk.group(3)), float(mk.group(4)), float(mk.group(5)), float(mk.group(6)))


# 「We estimate exchange, clearing and regulatory fees to be NN% of the futures commissions.」
# PDF 抽文本时这句被换行拆开（"… to be 54% of the \nfutures commissions."），故 \s+ 跨行。
FUT_FEE_RE = re.compile(r'fees to be\s+(\d+(?:\.\d+)?)\s*%\s+of the\s+futures commissions', re.I)


def parse_pr_fut_fee(path):
    """新闻稿里「交易所／清算／监管费用占期货佣金」的百分比。命中返回 float，没有返回 None。

    ⚠ **这个比例逐月披露、每月都在动**（本地缓存的十几份稿子跨了好几个百分点），
    任何地方都不许写死一个常数 —— build/ibkr.py 页尾脚注原先写死的「56%」正是这么
    与目标月（那期披露的是 54%）对不上的。

    单独成函数、不并进 `parse_pr` 的返回元组：那个元组按位置解包、已有调用方在用；
    而这一句只喂页尾脚注，缺了不该让整个月度构建挂掉，所以命中失败返回 None 而不 raise。
    放在本文件是因为**「新闻稿怎么解析」只能有一处定义**（同 parse_pr 的理由）。
    """
    m = FUT_FEE_RE.search(fitz.open(path)[0].get_text())
    return float(m.group(1)) if m else None
