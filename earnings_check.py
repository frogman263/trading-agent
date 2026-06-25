#!/usr/bin/env python3
"""
earnings_check.py — Earnings calendar and 5-day move checker v1.0

Fetches upcoming earnings dates and recent price moves for all universe
symbols. Outputs /tmp/earnings.json for the trading agent to consume
at STEP 7 before trade evaluation.

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


def get_5day_move(ticker):
    """Return 5-session price change as a percentage. None on failure."""
    try:
        hist = ticker.history(period="10d")
        if hist.empty or len(hist) < 2:
            return None
        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return None
        recent = closes.iloc[-min(6, len(closes)):]
        start = float(recent.iloc[0])
        end = float(recent.iloc[-1])
        if start == 0:
            return None
        return round(((end - start) / start) * 100, 2)
    except Exception as e:
        logging.warning(f"5-day move error: {e}")
        return None


def get_earnings_date(ticker, sym, lookahead_days):
    """
    Return next earnings date if within lookahead_days, else None.
    Handles yfinance 1.4.x calendar format.
    """
    try:
        cal = ticker.calendar
        if cal is None:
            return None

        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if ed is None:
                return None
            dates = ed if isinstance(ed, list) else [ed]
        else:
            try:
                dates = cal.loc["Earnings Date"].tolist()
            except Exception:
                return None

        today = date.today()
        cutoff = today + timedelta(days=lookahead_days)

        for d in dates:
            if hasattr(d, "date"):
                d = d.date()
            elif isinstance(d, str):
                try:
                    d = date.fromisoformat(d[:10])
                except Exception:
                    continue
            if isinstance(d, date) and today <= d <= cutoff:
                return d

        return None

    except Exception as e:
        logging.warning(f"{sym} earnings date error: {e}")
        return None


def classify_action(five_day_move, has_earnings, earnings_date, post_earnings):
    """
    Pre-earnings:  down 5%+ → buy_weakness | up 10%+ → no_chase | else → hold
    Post-earnings: post_earnings_check (agent applies beat/raise rule)
    No earnings:   no_earnings
    """
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
    try:
        import yfinance as yf
    except ImportError:
        logging.error("yfinance not installed. Run: pip3 install yfinance")
        sys.exit(1)

    today = date.today()
    results = {}

    logging.info(f"Checking {len(symbols)} symbols for earnings within {lookahead_days} days...")

    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            five_day = get_5day_move(ticker)
            earnings_date = get_earnings_date(ticker, sym, lookahead_days)

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
            logging.info(f"  {sym:6s} | 5d: {status:8s} | earnings: {earn_str} | action: {action}")

        except Exception as e:
            logging.warning(f"  {sym}: Error — {e}")
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

    logging.info(f"\nOutput written to {OUTPUT_PATH}")
    logging.info(f"Summary:")
    logging.info(f"  buy_weakness:        {output['summary']['buy_weakness']}")
    logging.info(f"  no_chase:            {output['summary']['no_chase']}")
    logging.info(f"  post_earnings_check: {output['summary']['post_earnings_check']}")
    logging.info(f"  hold:                {output['summary']['hold']}")
    logging.info(f"  no_earnings:         {output['summary']['no_earnings']}")

    return output


def main():
    parser = argparse.ArgumentParser(description="Earnings check v1.0")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--symbols", nargs="+", default=UNIVERSE)
    args = parser.parse_args()
    run(args.symbols, args.days)


if __name__ == "__main__":
    main()