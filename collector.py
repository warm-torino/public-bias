#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Public Bias Collector
---------------------
Myfxbook Community Outlook（＋任意で OANDA Position Book）から
リテールのロング比率を取得し、MT5 共通フォルダにシンボル別 CSV で追記する。
GitHub Actions で 1 時間ごとに実行し、data/ 以下の CSV をコミットする。
（output_dir を空にすればローカル PC で MT5 共通フォルダへ直接書き出すこともできる）

CSV: data/<SYMBOL>.csv
列 : utc_unix, long_pct, mfb_long_pct, oanda_long_pct,
     mfb_long_vol, mfb_short_vol, mfb_positions, utc_iso
"""
import argparse
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote

import requests

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
SESSION_PATH = BASE_DIR / ".myfxbook_session"
LOG_PATH = BASE_DIR / "collector.log"

MFB_BASE = "https://www.myfxbook.com/api"
OANDA_HOSTS = {
    "live": "https://api-fxtrade.oanda.com",
    "practice": "https://api-fxpractice.oanda.com",
}

HEADER = ["utc_unix", "long_pct", "mfb_long_pct", "oanda_long_pct",
          "mfb_long_vol", "mfb_short_vol", "mfb_positions", "utc_iso"]

log = logging.getLogger("publicbias")


# ---------------------------------------------------------------- 基本
def setup_logging():
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)


def load_config():
    if not CONFIG_PATH.exists():
        sys.exit(f"config.json がありません: {CONFIG_PATH}")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    # 秘密情報は環境変数（GitHub Secrets）を優先
    cfg.setdefault("myfxbook", {})
    cfg.setdefault("oanda", {})
    if os.environ.get("MYFXBOOK_EMAIL"):
        cfg["myfxbook"]["email"] = os.environ["MYFXBOOK_EMAIL"]
    if os.environ.get("MYFXBOOK_PASSWORD"):
        cfg["myfxbook"]["password"] = os.environ["MYFXBOOK_PASSWORD"]
    if os.environ.get("OANDA_TOKEN"):
        cfg["oanda"]["token"] = os.environ["OANDA_TOKEN"]
    if not cfg["myfxbook"].get("email") or not cfg["myfxbook"].get("password"):
        sys.exit("Myfxbook のメール/パスワードが未設定です（Secrets: MYFXBOOK_EMAIL / MYFXBOOK_PASSWORD）")
    return cfg


def output_dir(cfg):
    d = cfg.get("output_dir")
    if d:
        p = Path(os.path.expandvars(d))
        if not p.is_absolute():
            p = BASE_DIR / p
    else:
        appdata = os.environ.get("APPDATA")
        p = (Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files" / "PublicBias"
             if appdata else BASE_DIR / "output")
    p.mkdir(parents=True, exist_ok=True)
    return p


def http_get_json(url, headers=None, retries=3):
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries - 1:
                time.sleep(5 * (i + 1))
    raise RuntimeError(f"GET失敗: {url.split('?')[0]} ({last})")


# ---------------------------------------------------------------- Myfxbook
def _session_param(s):
    # 返ってくるセッションがエンコード済みでも未エンコードでも正しく渡せるよう正規化
    return quote(unquote(s), safe="")


def mfb_login(cfg):
    m = cfg["myfxbook"]
    url = (f"{MFB_BASE}/login.json?email={quote(m['email'], safe='')}"
           f"&password={quote(m['password'], safe='')}")
    j = http_get_json(url)
    if j.get("error"):
        raise RuntimeError(f"Myfxbookログイン失敗: {j.get('message')}")
    s = j["session"]
    SESSION_PATH.write_text(s, encoding="utf-8")
    log.info("Myfxbook: 新しいセッションを取得")
    return s


def mfb_outlook(cfg):
    """{SYMBOL: {...}} を返す。セッション切れなら1回だけ再ログイン。"""
    session = SESSION_PATH.read_text(encoding="utf-8").strip() if SESSION_PATH.exists() else None
    for _ in range(2):
        if not session:
            session = mfb_login(cfg)
        j = http_get_json(f"{MFB_BASE}/get-community-outlook.json?session={_session_param(session)}")
        if not j.get("error"):
            return {str(s.get("name", "")).upper(): s for s in j.get("symbols", [])}
        msg = str(j.get("message", ""))
        log.warning(f"Myfxbook: {msg}")
        if "session" in msg.lower():
            session = None
            continue
        raise RuntimeError(f"Myfxbook取得失敗: {msg}")
    raise RuntimeError("Myfxbook: 再ログイン後も失敗")


# ---------------------------------------------------------------- OANDA（任意）
def oanda_long_pct(cfg, symbol):
    o = cfg.get("oanda") or {}
    if not o.get("token"):
        return None
    inst = (o.get("instruments") or {}).get(symbol) or f"{symbol[:3]}_{symbol[3:]}"
    host = OANDA_HOSTS.get(o.get("env", "live"), OANDA_HOSTS["live"])
    try:
        j = http_get_json(f"{host}/v3/instruments/{inst}/positionBook",
                          headers={"Authorization": f"Bearer {o['token']}"}, retries=2)
        buckets = j["positionBook"]["buckets"]
        L = sum(float(b["longCountPercent"]) for b in buckets)
        S = sum(float(b["shortCountPercent"]) for b in buckets)
        return round(100.0 * L / (L + S), 2) if L + S > 0 else None
    except Exception as e:  # noqa: BLE001
        log.warning(f"OANDA {inst}: {e}")
        return None


# ---------------------------------------------------------------- 集計・保存
def blend(values, weights):
    tot = w = 0.0
    for k, v in values.items():
        if v is None:
            continue
        wk = float(weights.get(k, 1.0))
        tot += v * wk
        w += wk
    return round(tot / w, 2) if w > 0 else None


def last_ts(path):
    if not path.exists():
        return None
    with open(path, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 512))
        lines = f.read().decode("utf-8", "ignore").strip().splitlines()
    if not lines:
        return None
    try:
        return int(lines[-1].split(",")[0])
    except ValueError:
        return None


def append_row(path, row):
    new = not path.exists()
    with open(path, "a", newline="", encoding="ascii") as f:
        w = csv.writer(f, lineterminator="\r\n")
        if new:
            w.writerow(HEADER)
        w.writerow(row)


def _num(v, fmt="{:.2f}"):
    return "" if v is None else fmt.format(v)


def main():
    ap = argparse.ArgumentParser(description="Public Bias collector")
    ap.add_argument("--force", action="store_true", help="同じ時間帯に記録済みでも追記する")
    args = ap.parse_args()

    setup_logging()
    cfg = load_config()
    out = output_dir(cfg)

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    ts = int(now.timestamp())

    try:
        mfb = mfb_outlook(cfg)
    except Exception as e:  # noqa: BLE001
        log.error(e)
        mfb = {}

    weights = cfg.get("weights", {"myfxbook": 1.0, "oanda": 1.0})
    written = attempted = 0
    for sym in cfg["symbols"]:
        sym = sym.upper()
        path = out / f"{sym}.csv"

        lt = last_ts(path)
        if lt and lt // 3600 == ts // 3600 and not args.force:
            log.info(f"{sym}: この時間帯は記録済みのためスキップ")
            continue
        attempted += 1

        m = mfb.get(sym)
        mfb_long = float(m["longPercentage"]) if m and m.get("longPercentage") is not None else None
        oa = oanda_long_pct(cfg, sym)
        long_pct = blend({"myfxbook": mfb_long, "oanda": oa}, weights)
        if long_pct is None:
            log.warning(f"{sym}: どのソースからも取得できず")
            continue

        append_row(path, [
            ts, f"{long_pct:.2f}", _num(mfb_long), _num(oa),
            m.get("longVolume", "") if m else "",
            m.get("shortVolume", "") if m else "",
            m.get("totalPositions", "") if m else "",
            now.strftime("%Y-%m-%dT%H:%MZ"),
        ])
        written += 1
        log.info(f"{sym}: long={long_pct:.2f}%  (myfxbook={mfb_long}, oanda={oa})")

    log.info(f"完了: {written} シンボル書き込み → {out}")
    # 1つも書けなかった場合は失敗扱い（GitHub から失敗通知メールが届く）
    return 1 if attempted and not written else 0


if __name__ == "__main__":
    sys.exit(main())
