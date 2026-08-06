# -*- coding: utf-8 -*-
"""各家「官方把这个月的数据发出来的那一天」的台账 —— series/source_dates.csv。

页面抬头那行写着「官方发布于 2026-08-03」。**那是一句关于外部世界的事实断言**，
所以它必须来自源头自己说的日期，不能是构建日、不能是文件 mtime、更不能是「我们下载它的那天」。
拿不到就让它缺席（页面会自动省掉那半句），缺席远好过印一个像模像样的错日期。

═══ 为什么要落盘，而不是每次 build 时现从 cache/ 里解析 ═══
cache/ 是 gitignore 的、随时可以删。现解析有两个坏处：
  1. 缓存被清掉之后，这行断言会静默消失；
  2. 更糟的是**串月**——缓存里躺着的可能是比 data_through 更新的一期文件，
     现解析会把新一期的发布日安到旧月份的数据上，页面照样理直气壮地印出来。
落盘按「月份」钉死，就不会串。这和 series/ 是唯一真值、cache/ 只是过程物是同一条原则。

═══ 谁不用这张表 ═══
自己的序列里**本来就带发布日列**的模块不写这里，直接用自己的（避免同一个事实存两份、
然后哪天对不上）。目前只有 AXP：series/axp_trust_full.csv 的 filing_date 是 10-D 的
报送日，build/axp.py 直接读它。

═══ 格式 ═══
    ticker,month,source_date,evidence
    ibkr,2026-07,2026-08-03,新闻稿电头 "GREENWICH, CT, August 3, 2026 —"

evidence 一栏写**这个日期是从源文件的哪一处拿到的**，不是写「官网」。
将来有人怀疑某个日期时，这一栏决定他要花五分钟还是半天。
"""
import csv
import os

try:
    import fcntl
except ImportError:                     # 非 POSIX：退化成不加锁（本项目只跑 macOS/Linux）
    fcntl = None

NAME = 'source_dates.csv'
FIELDS = ['ticker', 'month', 'source_date', 'evidence']


def path(series_dir):
    return os.path.join(series_dir, NAME)


def _read(p):
    if not os.path.exists(p):
        return []
    with open(p, newline='', encoding='utf-8') as f:
        return [r for r in csv.DictReader(f) if r.get('ticker')]


def lookup(series_dir, ticker, month):
    """返回 'YYYY-MM-DD'，没有记录就返回 None（调用方必须容忍 None）。"""
    if not month:
        return None
    month = str(month)
    for r in _read(path(series_dir)):
        if r['ticker'] == ticker and r['month'] == month:
            return r['source_date'] or None
    return None


def latest_of(series_dir, tickers, months):
    """横截面页用：成员里**最晚**的那个发布日。

    横截面页要等成员都发齐了才算完整，所以「这一页什么时候成立」取决于最后到的那一家。
    有任何一个成员查不到发布日就返回 None —— 拿部分成员算出来的 max 会偏早，
    而偏早的日期看上去完全正常，没人会发现。
    """
    got = [lookup(series_dir, t, months.get(t)) for t in tickers]
    return max(got) if got and all(got) else None


def record(series_dir, ticker, month, source_date, evidence):
    """写入/更新一条。同 (ticker, month) 覆盖，其余行原样保留，按 ticker+month 排序。

    加 flock：fetch 各家在同一次 monthly_run 里是顺序跑的，但**改代码时人会并行跑**
    （12 个终端各跑各的 build），读-改-写不加锁会互相把对方的行吃掉，
    而丢一行的表现只是「某一页少了半句话」，不报错、不好发现。
    """
    month, source_date = str(month), str(source_date)
    if not (len(source_date) == 10 and source_date[4] == '-' and source_date[7] == '-'):
        raise ValueError(f'source_date 必须是 YYYY-MM-DD，收到 {source_date!r}')
    # 发布日必须**严格晚于数据月结束**。原来只比到「年-月」（source_date[:7] < month），
    # 那样给 2026-07 记一个 2026-07-15 会被放行 —— 一个月还没过完就「发布」了当月数据，
    # 是解析取错字段的典型症状（多半取到了封面上的「报告期」或上一期的日期），
    # 而它看上去完全正常。审计指出这道护栏比看上去弱，这里收紧到日。
    y, mo = int(month[:4]), int(month[5:7])
    month_end_next = f'{y + 1}-01-01' if mo == 12 else f'{y}-{mo + 1:02d}-01'
    if source_date < month_end_next:
        raise ValueError(f'{ticker} {month} 的发布日 {source_date} 不晚于数据月结束'
                         f'（{month} 要到 {month_end_next} 才结束），拒绝写入')
    if not evidence:
        raise ValueError('evidence 不能为空 —— 不写清出处的日期，将来没人敢信也没人敢改')

    p = path(series_dir)
    os.makedirs(series_dir, exist_ok=True)
    with open(p, 'a+', encoding='utf-8') as lock:
        if fcntl:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        rows = [r for r in _read(p) if not (r['ticker'] == ticker and r['month'] == month)]
        rows.append({'ticker': ticker, 'month': month,
                     'source_date': source_date, 'evidence': evidence})
        rows.sort(key=lambda r: (r['ticker'], r['month']))
        tmp = p + '.tmp'
        with open(tmp, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, FIELDS, lineterminator='\n')
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, p)               # 原子替换：中途挂掉也不会留下半张表
        if fcntl:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def load(root):
    """给 fetch/ 与 build/ 下的模块按路径加载本模块用。

    两边都不能裸 `import source_dates`：fetch/<t>.py 被 monthly_run 用
    spec_from_file_location 加载，那时 sys.path 上既没有 fetch/ 也没有仓库根；
    build/<t>.py 是 `python3 build/<t>.py` 跑的，sys.path 上只有 build/。
    """
    import importlib.util
    p = os.path.join(root, 'source_dates.py')
    spec = importlib.util.spec_from_file_location('source_dates', p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
