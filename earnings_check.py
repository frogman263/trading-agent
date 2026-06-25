#!/usr/bin/env python3
"""
earnings_check.py — Earnings calendar and 5-day move checker v1.2

Uses Python built-in urllib + http.cookiejar only — no pip install required.
Implements Yahoo Finance crumb authentication to avoid 429 rate limiting.
Outputs /tmp/earnings.json for the trading agent at STEP 7.

Usage:
  python3 earnings_check.py
  python3 earnings_check.py --days 7
  python3 earnings_check.py --symbols NVDA MU AVGO

Output: /tmp/earnings.json
"""

import json
import sys
import argparse
import logging
import time
import urllib.request
import urllib.error
import http.cookiejar
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

UNIVERSE = [
    "NVDA", "AVGO", "MU",
    "CEG", "GEV", "VST", "BE",
    "IREN", "APLD", "CORZ", "CRWV",
    "ASML", "NBIS", "RIOT",
    "AMD", "AMAT", "MRVL", "VRT"
]

OUTPUT_PATH = "/tmp/earnings.json"

HEADERS = [
    ("User-Agent",
     "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
     "AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/124.0.0.0 Safari/537.36"),
    ("Accept", "application/json,text/plain,*/*"),
    ("Accept-Language", "en-US,en;q=0.9"),
    ("Accept-Encoding", "gzip, deflate"),
    ("Referer", "https://finance.yahoo.com/"),
]


def create_session():
    """
    Create an authenticated Yahoo Finance session.
    Returns (opener, crumb) — crumb is None if auth fails (fallback mode).
    """
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar)
    )
    opener.addheaders = HEADERS

    # Step 1 — seed cookies via fc.yahoo.com
    try:
        opener.open("https://fc.yahoo.com/", timeout=8)
        logging.info("Yahoo Finance session cookie obtained")
    except Exception as e:
        logging.warning(f"Cookie seed failed (non-fatal): {e}")

    # Step 2 — get crumb token
    crumb = None
    for endpoint in [
        "https://query1.finance.yahoo.com/v1/test/getcrumb",
        "https://query2.finance.yahoo.com/v1/test/getcrumb",
    ]:
        try:
            resp = opener.open(endpoint, timeout=8)
            raw = resp.read().decode("utf-8").strip()
            if raw and raw != "":
                crumb = raw
                logging.info(f"Crumb obtained: {crumb[:8]}...")
                break
        except Exception as e:
            logging.warning(f"Crumb endpoint {endpoint} failed: {e}")

    if not crumb:
        logging.warning("Could not obtain Yahoo Finance crumb — will try without")

    return opener, crumb


def fetch_yahoo(opener, url, retries=3):
    """Fetch a Yahoo Finance URL with retry on 429."""
    for attempt in range(retries):
        try:
            with opener.open(url, timeout=12) as r:
                raw = r.read()
                if r.info().get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2 ** attempt
                logging.warning(
                    f"Rate limited (429) — retry {attempt+1}/{retries} in {wait}s"
                )
                time.sleep(wait)
            else:
                logging.warning(f"HTTP {e.code}: {url[:60]}")
                return None
        except urllib.error.URLError as e:
            logging.warning(f"URL error: {e.reason}")
            return None
        except Exception as e:
            logging.warning(f"Fetch error: {e}")
            return None
    logging.warning(f"All {retries} retries exhausted for {url[:60]}")
    return None


def get_5day_move(opener, crumb, sym):
    """Return 5-session % change. None on failure."""
    crumb_param = f"&crumb={crumb}" if crumb else ""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        f"?interval=1d&range=10d{crumb_param}"
    )
    data = fetch_yahoo(opener, url)
    if not data:
        return None
    try:
        result = data["chart"]["result"]
        if not result:
            return None
        closes = result[0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        if len(closes) < 2:
            return None
        recent = closes[-min(6, len(closes)):]
        start, end = recent[0], recent[-1]
        if start == 0:
            return None
        return round(((end - start) / start) * 100, 2)
    except (KeyError, IndexError, TypeError) as e:
        logging.warning(f"{sym} 5-day parse error: {e}")
        return None


def get_earnings_date(opener, crumb, sym, lookahead_days):
    """Return next earnings date within lookahead_days, or None."""
    crumb_param = f"&crumb={crumb}" if crumb else ""
    url = (
        f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}"
        f"?modules=calendarEvents{crumb_param}"
    )
    data = fetch_yahoo(opener, url)
    if not data:
        return None
    try:
        result = data["quoteSummary"]["result"]
        if not result:
            return None
        events = result[0].get("calendarEvents", {})
        earnings = events.get("earnings", {})
        dates = earnings.get("earningsDate", [])

        today = date.today()
        cutoff = today + timedelta(days=lookahead_days)

        for d in dates:
            if isinstance(d, dict):
                raw = d.get("raw")
                if raw:
                    dt = date.fromtimestamp(raw)
                else:
                    continue
            elif isinstance(d, (int, float)):
                dt = date.fromtimestamp(d)
            else:
                continue
            if today <= dt <= cutoff:
                return dt

        return None
    except (KeyError, IndexError, TypeError) as e:
        logging.warning(f"{sym} earnings parse error: {e}")
        return None


def classify_action(five_day_move, has_earnings, earnings_date, post_earnings):
    if not has_earnings:
        return "no_earnings"
    if post_earnings:
        return "post_earnings_check"
    if five_day_move is not None:
        if five_day_move <= -5.0:
            return "buy_weakness"
        if five_day_move >= 10.0:
            return "no_chase"
    return "hold"


def run(symbols, lookahead_days):
    today = date.today()
    results = {}

    logging.info(
        f"earnings_check.py v1.2 — {len(symbols)} symbols, "
        f"{lookahead_days}-day window"
    )

    opener, crumb = create_session()

    for i, sym in enumerate(symbols):
        if i > 0:
            time.sleep(0.4)
        try:
            five_day = get_5day_move(opener, crumb, sym)
            earnings_date = get_earnings_date(opener, crumb, sym, lookahead_days)

            has_earnings = earnings_date is not None
            post_earnings = has_earnings and earnings_date <= today
            action = classify_action(five_day, has_earnings, earnings_date, post_earnings)

            results[sym] = {
                "symbol": sym,
                "five_day_move_pct": five_day,
                "earnings_date": str(earnings_date) if earnings_date else None,
                "has_earnings_within_window": has_earnings,
                "post_earnings": post_earnings,
                "action": action,
            }

            status = f"{five_day:+.1f}%" if five_day is not None else "N/A"
            earn_str = str(earnings_date) if earnings_date else "none"
            logging.info(
                f"  {sym:6s} | 5d: {status:8s} | "
                f"earnings: {earn_str} | action: {action}"
            )

        except Exception as e:
            logging.warning(f"  {sym}: Unexpected error — {e}")
            results[sym] = {
                "symbol": sym,
                "five_day_move_pct": None,
                "earnings_date": None,
                "has_earnings_within_window": False,
                "post_earnings": False,
                "action": "no_earnings",
                "error": str(e)
            }

    output = {
        "generated_at": datetime.now(ZoneInfo("America/New_York")).strftime(
            "%Y-%m-%d %H:%M:%S ET"
        ),
        "version": "1.2",
        "lookahead_days": lookahead_days,
        "symbols_checked": len(symbols),
        "results": results,
        "summary": {
            "buy_weakness":        [s for s, v in results.items() if v["action"] == "buy_weakness"],
            "no_chase":            [s for s, v in results.items() if v["action"] == "no_chase"],
            "post_earnings_check": [s for s, v in results.items() if v["action"] == "post_earnings_check"],
            "hold":                [s for s, v in results.items() if v["action"] == "hold"],
            "no_earnings":         [s for s, v in results.items() if v["action"] == "no_earnings"],
        }
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    logging.info(f"Output written to {OUTPUT_PATH}")
    logging.info(f"Summary:")
    logging.info(f"  buy_weakness:        {output['summary']['buy_weakness']}")
    logging.info(f"  no_chase:            {output['summary']['no_chase']}")
    logging.info(f"  post_earnings_check: {output['summary']['post_earnings_check']}")
    logging.info(f"  hold:                {output['summary']['hold']}")
    logging.info(f"  no_earnings:         {output['summary']['no_earnings']}")

    return output


def main():
    parser = argparse.ArgumentParser(description="Earnings check v1.2")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--symbols", nargs="+", default=UNIVERSE)
    args = parser.parse_args()
    run(args.symbols, args.days)


if __name__ == "__main__":
    main()