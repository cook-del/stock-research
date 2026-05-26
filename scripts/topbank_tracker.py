#!/usr/bin/env python3
"""
顶级投行关注度追踪器 v3 — 最终版
==================================
追踪 A 股的大单资金流向 + 研报评级 + 大宗交易数据，
识别哪些股票正被顶级外资投行关注。

特点:
  - 无外部依赖 (仅需 requests)
  - 从东方财富公开 API 获取数据
  - 自动检测 高盛/摩根大通/摩根士丹利/花旗/瑞银等投行
  - 输出 Markdown 表格

用法:
  python3 topbank_tracker.py                          # 使用默认名单
  python3 topbank_tracker.py 600183 002916 688981     # 查询指定股票
  python3 topbank_tracker.py --list                   # 查看默认名单
"""

import requests
import json
import time
import re
import sys
from datetime import datetime, timedelta

# ============================================================
# 配置
# ============================================================

TOP_BANKS = [
    "高盛", "Goldman Sachs",
    "摩根大通", "JPMorgan", "J.P. Morgan",
    "摩根士丹利", "Morgan Stanley", "大摩",
    "花旗", "Citigroup", "Citi",
    "瑞银", "UBS",
    "美林", "Merrill Lynch",
    "野村", "Nomura",
    "瑞信", "Credit Suisse",
    "汇丰", "HSBC",
    "巴克莱", "Barclays",
    "德银", "Deutsche Bank",
    "贝莱德", "BlackRock",
    "先锋", "Vanguard",
    "景顺", "Invesco",
]

LOOKBACK_DAYS = 30
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SLEEP = 0.3

DEFAULT_WATCH = [
    #  (代码,    名称,     市场, 行业)
    ("600183", "生益科技", "1", "覆铜板"),
    ("002916", "深南电路", "0", "PCB"),
    ("601138", "工业富联", "1", "AI服务器"),
    ("002463", "沪电股份", "0", "PCB"),
    ("300476", "胜宏科技", "0", "PCB"),
    ("002938", "鹏鼎控股", "0", "PCB"),
    ("688981", "中芯国际", "1", "晶圆代工"),
    ("688012", "中微公司", "1", "半导体设备"),
    ("002371", "北方华创", "0", "半导体设备"),
    ("603501", "韦尔股份", "1", "芯片设计"),
    ("300782", "卓胜微", "0", "射频芯片"),
    ("688041", "海光信息", "1", "CPU/GPU"),
    ("688256", "寒武纪", "1", "AI芯片"),
    ("600584", "长电科技", "1", "封测"),
    ("000938", "紫光股份", "0", "ICT设备"),
    ("300308", "中际旭创", "0", "光模块"),
    ("300502", "新易盛", "0", "光模块"),
    ("002230", "科大讯飞", "0", "AI语音"),
    ("000977", "浪潮信息", "0", "AI服务器"),
    ("603019", "中科曙光", "1", "算力"),
    ("002475", "立讯精密", "0", "连接器"),
    ("300433", "蓝思科技", "0", "玻璃盖板"),
]

# ============================================================
# API 工具
# ============================================================

def safe_req(url, params=None, timeout=12):
    for _ in range(2):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except:
            time.sleep(SLEEP)
    return None


def date_str(days_ago=0):
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y%m%d")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def fmt_money(v):
    try:
        v = float(v)
        a = abs(v)
        if a >= 1e8:
            return f"{v/1e8:.1f}亿"
        elif a >= 1e4:
            return f"{v/1e4:.0f}万"
        else:
            return f"{v:.0f}"
    except:
        return str(v)


def market_of(code):
    return "1" if code.startswith(("6", "9")) else "0"


# ============================================================
# 1. 近期研报
# ============================================================

def get_reports(code, market):
    url = "https://reportapi.eastmoney.com/report/list"
    params = {
        "pageNo": "1", "pageSize": "10",
        "code": code, "marketCode": market,
        "industryCode": "*", "reportType": "1",
        "beginTime": date_str(LOOKBACK_DAYS),
        "endTime": date_str(0),
        "qType": "0"
    }
    data = safe_req(url, params)
    results = []
    if data and data.get("data"):
        for r in data["data"]:
            org = r.get("orgName", "") or r.get("orgSName", "")
            results.append({
                "org": org,
                "rating": r.get("emRatingName", "") or r.get("sRatingName", ""),
                "title": r.get("title", ""),
                "date": (r.get("publishDate") or "")[:10],
                "target": r.get("indvAimPriceT", ""),
            })
    return results


def match_top_bank(org):
    for kw in TOP_BANKS:
        if kw.lower() in org.lower():
            return kw
    return None


# ============================================================
# 2. 大单资金流向 (6字段模式)
#    使用 f62/f63/f64/f65/f184/f66 接口
# ============================================================

def get_flow(code, market, days=5):
    """获取主力资金净流入累计数据"""
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
    params = {
        "secid": f"{market}.{code}",
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "klt": "101", "lmt": str(days),
        "beg": date_str(days), "end": date_str(0),
    }
    data = safe_req(url, params)
    if not data or not data.get("data") or not data["data"].get("klines"):
        return None

    klines = data["data"]["klines"]
    total_main = 0.0
    count = 0
    for k in klines:
        parts = k.split(",")
        if len(parts) >= 6:
            total_main += float(parts[1])  # f52 主力净流入
            count += 1

    return {
        "total_main": total_main,
        "days": count,
    }


# ============================================================
# 3. 大宗交易
# ============================================================

def get_block(code, market, days=5):
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": f"{market}.{code}",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55",
        "lmt": "5",
        "beg": date_str(days), "end": date_str(0),
    }
    data = safe_req(url, params)
    if data and data.get("data") and data["data"].get("klines"):
        results = []
        for k in data["data"]["klines"]:
            parts = k.split(",")
            if len(parts) >= 3:
                results.append({"date": parts[0], "amount": parts[2]})
        return results
    return []


# ============================================================
# 4. 新闻中提及顶级投行
# ============================================================

def scan_news_for_topbanks(code, market):
    """搜新闻标题中是否提及顶级投行"""
    url = "https://searchapi.eastmoney.com/bgsearch/api"
    params = {"client": "app", "keyword": code, "pageindex": "1", "pagesize": "10", "type": "1"}
    data = safe_req(url, params)
    found = set()
    if data and data.get("Data"):
        for item in data["Data"]:
            text = (item.get("Title", "") or "") + " " + (item.get("Summary", "") or "")
            for bank in TOP_BANKS:
                if bank.lower() in text.lower():
                    found.add(bank)
    return sorted(found)


# ============================================================
# 5. 实时行情 (对比到昨日收盘)
# ============================================================

def get_quote(code, market):
    """获取实时行情（价格, 涨跌幅%）"""
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "secid": f"{market}.{code}",
        "fields": "f43,f170,f12,f14"
    }
    data = safe_req(url, params)
    if data and data.get("data"):
        d = data["data"]
        price = d.get("f43", 0)
        chg = d.get("f170", 0)
        # 字段是 x100 格式
        try:
            price_f = round(float(price) / 100, 2)
        except:
            price_f = price
        try:
            chg_f = round(float(chg) / 100, 2)
            chg_s = f"{chg_f:+.2f}%"
        except:
            chg_s = str(chg)
        return {"price": price_f, "chg": chg_s}
    return None


# ============================================================
# 主逻辑
# ============================================================

def main():
    # 解析命令行参数
    if "--list" in sys.argv:
        print("默认关注股票:")
        for c, n, m, s in DEFAULT_WATCH:
            print(f"  {c} {n} ({s})")
        return

    watch_list = DEFAULT_WATCH
    custom_codes = [a for a in sys.argv[1:] if not a.startswith("-")]
    if custom_codes:
        watch_list = [(c, c, market_of(c), "") for c in custom_codes]

    print(f"🔍 顶级投行关注度追踪器 | {now_str()}")
    print(f"📅 查询: 最近{LOOKBACK_DAYS}天 | {len(watch_list)}只股票 | {len(TOP_BANKS)}家投行")
    print(f"🏦 监测投行: {', '.join(TOP_BANKS[:6])}…\n")

    results = []

    for idx, (code, name, market, sector) in enumerate(watch_list):
        label = f"{name}" if name != code else code
        print(f"   [{idx+1}/{len(watch_list)}] {code} {label}", end="", flush=True)

        reports = get_reports(code, market);     time.sleep(SLEEP)
        flow = get_flow(code, market);           time.sleep(SLEEP)
        block = get_block(code, market);         time.sleep(SLEEP)
        news_banks = scan_news_for_topbanks(code, market); time.sleep(SLEEP)
        quote = get_quote(code, market);         time.sleep(SLEEP)

        # 检测顶级投行
        bank_orgs = set()
        for r in reports:
            kw = match_top_bank(r["org"])
            if kw:
                bank_orgs.add(kw)

        all_banks = bank_orgs | set(news_banks)

        # 资金流向
        flow_s = "—"
        if flow:
            d = "🟢" if flow["total_main"] > 0 else "🔴"
            flow_s = f"{d}{fmt_money(flow['total_main'])}/{flow['days']}日"

        # 大宗交易
        block_s = "—"
        if block:
            total_amt = sum(float(b["amount"]) for b in block if b.get("amount"))
            block_s = f"{len(block)}笔/{fmt_money(total_amt)}"

        # 研报
        report_lines = []
        for r in reports[:4]:
            p = "🏦" if match_top_bank(r["org"]) else " "
            tp_str = f"→{r['target']}" if r.get("target") else ""
            report_lines.append(f"{p}{r['org'][:10]}→{r['rating']}{tp_str}({r['date']})")

        report_s = "\n".join(report_lines) if report_lines else "—"

        # 新闻提及
        news_s = ", ".join(news_banks) if news_banks else "—"

        results.append({
            "code": code, "name": label, "sector": sector or "—",
            "price": quote["price"] if quote else "-",
            "chg": quote["chg"] if quote else "-",
            "flow": flow_s, "block": block_s,
            "reports": report_s, "news": news_s,
            "bank_count": len(all_banks), "report_count": len(reports),
        })

        flags = []
        if all_banks: flags.append(f"🏦x{len(all_banks)}")
        if news_banks: flags.append("📰新闻提及")
        flag_s = " " + " ".join(flags) if flags else ""
        print(f" 研报{len(reports)}篇{flag_s}")

    # 排序
    results.sort(key=lambda r: (r["bank_count"], r["report_count"]), reverse=True)

    # ==== 输出 ====
    print("\n" + "=" * 140)
    print(f" 📊 顶级投行关注度汇总表 | {now_str()}")
    print("=" * 140)

    def row_md(r):
        banks = ", ".join(str(r["bank_count"])) if r["bank_count"] else "—"
        # 简化为：如果 bank_count > 0 显示 "✅"
        bank_flag = "✅" if r["bank_count"] > 0 else "—"
        return (
            f"| {r['code']:>6} | {r['name']:<8} | {r['sector']:<6} "
            f"| {str(r['price']):>8} | {r['chg']:<7} "
            f"| {bank_flag:^6} | {r['flow']:<14} "
            f"| {r['block']:<12} | {r['news']:<14} "
            f"| {r['reports'][:46]:46} |"
        )

    sep = f"|{'':->6}|{'':->8}|{'':->6}|{'':->8}|{'':->7}|{'':->6}|{'':->14}|{'':->12}|{'':->14}|{'':->46}|"

    print(f"| {'代码':>6} | {'名称':<8} | {'行业':<6} | {'现价':>8} | {'涨跌幅':<7} | {'🏦':^6} | {'主力流向':<14} | {'大宗交易':<12} | {'新闻提及':<14} | {'近期研报(30天)':46} |")
    print(sep)

    for r in results:
        print(row_md(r))
        # 多行研报
        r_lines = r["reports"].split("\n")
        if len(r_lines) > 1:
            for extra in r_lines[1:]:
                if extra.strip():
                    print(f"| {'':>6} | {'':<8} | {'':<6} | {'':>8} | {'':<7} | {'':^6} | {'':<14} | {'':<12} | {'':<14} | {extra[:46]:46} |")
        print(sep)

    print()
    print(f" 🏦 投行监测: {', '.join(TOP_BANKS)}")
    print(" ✅ = 有顶级投行研报或新闻提及    🟢/🔴 = 主力净流入/流出")
    print(" ⚠️  数据来自公开 API，仅供参考")
    print(f" 脚本路径: {__file__}")


if __name__ == "__main__":
    main()
