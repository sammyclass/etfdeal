# -*- coding: utf-8 -*-
"""
ETF 溢价数据层（安卓 App 与桌面共用，纯标准库 + requests，不依赖 pandas/numpy）

职责：
  1. 下载近 N 个交易日的「不复权收盘价」+「基金每日单位净值」，按日期对齐算溢价
  2. 本地 JSON 缓存读写（安卓存 App 私有目录，断网也能看上次结果）
  3. 输出结构化序列，供 UI 绘制曲线 / 生成 Top 榜

口径
  溢价率 = (收盘价 - 单位净值) / 单位净值 * 100，两者都不复权
  货币 ETF（511990）按百份净值计价，直接相除会得到 3 万多的假溢价，默认剔除
"""
import json
import os
import time
from datetime import datetime

import requests

UA = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36")

# 代码 -> 名称
NAMES = {
    "513100": "纳指ETF国泰", "159941": "纳指ETF广发", "513500": "标普500ETF博时",
    "513030": "德国ETF华安", "513050": "中概互联ETF", "513180": "恒生科技ETF华夏",
    "159742": "恒生科技ETF博时", "159920": "恒生ETF华夏", "510900": "H股ETF易方达",
    "518880": "黄金ETF华安", "159934": "黄金ETF易方达", "162411": "华宝油气LOF",
    "511380": "可转债ETF博时", "511260": "十年国债ETF国泰", "511360": "短融ETF海富通",
    "511220": "城投债ETF海富通", "511880": "银华日利ETF",
    "159857": "光伏ETF天弘(A股T+1)", "159507": "通信ETF广发(A股T+1)",
}

# 分组：用于图例配色与筛选
GROUPS = {
    "美股QDII": ["513100", "159941", "513500", "513030"],
    "港股中概": ["513050", "513180", "159742", "159920", "510900"],
    "黄金商品": ["518880", "159934", "162411"],
    "债券货币": ["511380", "511260", "511360", "511220", "511880"],
    "A股ETF": ["159857", "159507"],
}
COLORS = {
    "美股QDII": (0.16, 0.47, 0.87),   # 蓝
    "港股中概": (0.13, 0.68, 0.45),   # 绿
    "黄金商品": (0.95, 0.62, 0.13),   # 橙
    "债券货币": (0.55, 0.55, 0.60),   # 灰
    "A股ETF": (0.60, 0.35, 0.75),     # 紫
}
ALL_CODES = [c for g in GROUPS.values() for c in g]
THRESHOLD = 3.0      # 溢价告警线 %
DAYS = 100           # 默认取最近 100 个交易日
SKIP_CODES = {"511990"}   # 货币 ETF 计价口径特殊，自动跳过


def group_of(code):
    for g, lst in GROUPS.items():
        if code in lst:
            return g
    return "其它"


# ---------------- HTTP ----------------
def _get_json(url, referer=None, timeout=15):
    h = {"User-Agent": UA}
    if referer:
        h["Referer"] = referer
    r = requests.get(url, headers=h, timeout=timeout)
    r.raise_for_status()
    txt = r.text.strip()
    if not txt:
        raise RuntimeError("空响应")
    return json.loads(txt)


def fetch_price_history(code, need=150):
    """场内日 K 收盘价（不复权）。东财 → 新浪 → 腾讯 三源回退。"""
    if code.startswith(("5", "6", "9")):
        secid, sym = "1." + code, "sh" + code
    else:
        secid, sym = "0." + code, "sz" + code

    # 源 1 东方财富
    try:
        u = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?"
             f"secid={secid}&klt=101&fqt=0&lmt={need}&end=20500101"
             "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58")
        d = _get_json(u)
        kl = (d.get("data") or {}).get("klines") or []
        if kl:
            return {k.split(",")[0]: float(k.split(",")[2]) for k in kl}
    except Exception:
        pass

    # 源 2 新浪
    try:
        u = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
             f"CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen={need}")
        d = _get_json(u)
        if isinstance(d, list) and d:
            return {it["day"]: float(it["close"]) for it in d}
    except Exception:
        pass

    # 源 3 腾讯
    u = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
         f"param={sym},day,,,{need},")
    d = _get_json(u)
    node = ((d.get("data") or {}).get(sym)) or {}
    bars = node.get("day") or node.get("qfqday") or []
    if not bars:
        raise RuntimeError("行情接口均失败")
    return {b[0]: float(b[2]) for b in bars}


def fetch_nav_history(code, need=150, pages=10):
    """基金每日单位净值（东财 f10/lsjz，pageSize 上限 20，必须翻页）"""
    nav = {}
    for i in range(1, pages + 1):
        u = ("https://api.fund.eastmoney.com/f10/lsjz?"
             f"fundCode={code}&pageIndex={i}&pageSize=20&startDate=&endDate="
             f"&_={int(time.time() * 1000)}")
        d = _get_json(u, referer=f"https://fundf10.eastmoney.com/jjjz_{code}.html")
        lst = ((d.get("Data") or {}).get("LSJZList")) or []
        if not lst:
            break
        for it in lst:
            try:
                nav[it["FSRQ"]] = float(it["DWJZ"])
            except Exception:
                continue
        if len(nav) >= need:
            break
        time.sleep(0.3)
    if not nav:
        raise RuntimeError("净值接口无数据")
    return nav


# ---------------- 组装 ----------------
def build_series(code, days=DAYS):
    """返回 {'dates':[...], 'price':[...], 'nav':[...], 'premium':[...]}"""
    px = fetch_price_history(code, need=days + 45)
    nav = fetch_nav_history(code, need=days + 45)
    common = sorted(set(px) & set(nav))[-days:]
    if not common:
        raise RuntimeError("价格与净值日期无交集")
    series = {"dates": [], "price": [], "nav": [], "premium": []}
    for d in common:
        p, n = px[d], nav[d]
        if n <= 0:
            continue
        prem = (p - n) / n * 100
        series["dates"].append(d)
        series["price"].append(round(p, 4))
        series["nav"].append(round(n, 4))
        series["premium"].append(round(prem, 2))
    return series


def fetch_all(days=DAYS, codes=None, progress=None):
    """下载全部标的。progress(i,total,code,ok,msg) 可选回调"""
    codes = [c for c in (codes or ALL_CODES) if c not in SKIP_CODES]
    data = {}
    for i, c in enumerate(codes, 1):
        ok, msg = True, ""
        try:
            s = build_series(c, days)
            if len(s["dates"]) < days - 10:
                ok, msg = False, "仅 %d 天" % len(s["dates"])
            elif max(abs(x) for x in s["premium"]) > 60:
                ok, msg = False, "计价口径异常"
            else:
                data[c] = s
        except Exception as e:
            ok, msg = False, str(e)[:40]
        if progress:
            progress(i, len(codes), c, ok, msg)
        time.sleep(0.6)
    return data


def latest_stats(data):
    """各标的「自己最新一天」的溢价榜。

    QDII 的单位净值常比 A 股 ETF 晚一天披露，所以不能只取全市场共同日期，
    否则纳指/标普这类高溢价标的会被整批过滤掉。每只取自己的最后一个交易日。
    """
    if not data:
        return "", []
    all_dates = set()
    rows = []
    for c, s in data.items():
        if not s["premium"]:
            continue
        all_dates |= set(s["dates"])
        rows.append({"code": c, "name": NAMES.get(c, c), "group": group_of(c),
                     "date": s["dates"][-1], "premium": s["premium"][-1],
                     "price": s["price"][-1], "nav": s["nav"][-1]})
    rows.sort(key=lambda r: r["premium"], reverse=True)
    return (max(all_dates) if all_dates else ""), rows


def summary(data, days=DAYS):
    """每只标的的 100 日均值/最大值/超阈值天数"""
    out = []
    for c, s in data.items():
        prem = s["premium"]
        if not prem:
            continue
        out.append({
            "code": c, "name": NAMES.get(c, c), "group": group_of(c),
            "days": len(prem), "avg": round(sum(prem) / len(prem), 2),
            "max": max(prem), "min": min(prem),
            "over": sum(1 for x in prem if x >= THRESHOLD),
        })
    out.sort(key=lambda r: r["avg"], reverse=True)
    return out


# ---------------- 缓存 ----------------
def cache_path(base_dir):
    return os.path.join(base_dir, "etf_premium_cache.json")


def save_cache(base_dir, data, days=DAYS):
    payload = {"updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "days": days, "data": data}
    path = cache_path(base_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def load_cache(base_dir):
    path = cache_path(base_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
