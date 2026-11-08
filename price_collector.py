#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Price Collector
---------------
Yahoo Finance から 1 時間足のローソク足を取得し、data/price/<SYMBOL>.csv に保存する。
GitHub Pages のグラフページで、センチメントと並べて表示するためのもの。
（MT5 用の data/<SYMBOL>.csv には一切触れない）

CSV: data/price/<SYMBOL>.csv
列 : utc_unix, open, high, low, close   （utc_unix は足の開始時刻・UTC）

※ 価格は表示用の参考値。ゴールドは COMEX 先物（GC=F）なので XM のスポットとは数ドルずれる。
"""
import csv
import json
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
OUT_DIR = BASE_DIR / "data" / "price"

# Yahoo のティッカー（config.json の "price_tickers" で上書き可）
DEFAULT_TICKERS = {
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
}

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?interval=1h&range={r}"
HEADERS = {"User-Agent": "Mozilla/5.0 (public-bias price collector)"}


def ticker_for(sym, cfg):
    over = cfg.get("price_tickers") or {}
    return over.get(sym) or DEFAULT_TICKERS.get(sym) or f"{sym}=X"


def fetch(ticker, rng):
    last = None
    for i in range(3):
        try:
            r = requests.get(URL.format(t=ticker, r=rng), headers=HEADERS, timeout=30)
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            ts = res.get("timestamp") or []
            q = res["indicators"]["quote"][0]
            bars = {}
            for k, t in enumerate(ts):
                o, h, l, c = q["open"][k], q["high"][k], q["low"][k], q["close"][k]
                if None in (o, h, l, c):
                    continue
                t = int(t) // 3600 * 3600  # 足の開始時刻に揃える
                bars[t] = (o, h, l, c)
            return bars
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"{ticker}: {last}")


def load(path):
    bars = {}
    if path.exists():
        with open(path, encoding="ascii") as f:
            for row in csv.reader(f):
                if not row or not row[0].isdigit():
                    continue
                bars[int(row[0])] = tuple(float(x) for x in row[1:5])
    return bars


def save(path, bars):
    dec = 5 if max(v[3] for v in bars.values()) < 50 else (3 if max(v[3] for v in bars.values()) < 1000 else 2)
    with open(path, "w", newline="", encoding="ascii") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["utc_unix", "open", "high", "low", "close"])
        for t in sorted(bars):
            w.writerow([t] + [f"{x:.{dec}f}" for x in bars[t]])


def main():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ok = 0
    for sym in cfg["symbols"]:
        sym = sym.upper()
        path = OUT_DIR / f"{sym}.csv"
        old = load(path)
        rng = "5d" if old else "1mo"  # 初回は 1 か月分さかのぼる
        try:
            new = fetch(ticker_for(sym, cfg), rng)
        except Exception as e:  # noqa: BLE001
            print(f"WARN {sym}: 価格取得失敗 {e}")
            continue
        if not new:
            print(f"WARN {sym}: データなし")
            continue
        old.update(new)  # 未確定だった直近の足は新しい値で上書き
        save(path, old)
        ok += 1
        print(f"{sym}: {len(new)} 本取得 / 合計 {len(old)} 本")

    print(f"完了: {ok}/{len(cfg['symbols'])} シンボル")
    return 0


if __name__ == "__main__":
    sys.exit(main())
