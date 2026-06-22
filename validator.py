#!/usr/bin/env python3
"""
Autonomous AI Trading Agent - Deterministic Validator v1.0
Enforces hard rules before any trade reaches Robinhood MCP.

Usage:
  python validator.py --proposals proposals.json --state state.json
  python validator.py --proposals proposals.json --state state.json --dry-run

Output: PASS or FAIL with full violation list. Exits 0 on PASS, 1 on FAIL.
"""

import json
import shutil
import sys
import argparse
from datetime import date, datetime
from zoneinfo import ZoneInfo
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ── CONFIG ─────────────────────────────────────────────────────────────────
# Update these to match your current CLAUDE.md universe and allocations.

AGENTIC_ACCOUNT = "926627357"  # Agentic ···7357 — only account this may trade

UNIVERSE = {
    "NVDA", "AVGO", "MU",                          # Tier 1
    "CEG", "GEV", "VST", "BE",                     # Tier 2
    "IREN", "APLD", "CORZ", "CRWV",                # Tier 3
    "ASML", "NBIS", "RIOT",                         # Tier 4 — held
    "AMD", "AMAT", "MRVL", "VRT"                   # Tier 4 — not yet held
}

MAX_ALLOCS = {
    "NVDA": 0.25, "AVGO": 0.15, "MU": 0.12,
    "CEG": 0.08, "GEV": 0.08, "VST": 0.07, "BE": 0.08,
    "IREN": 0.07, "APLD": 0.07, "CORZ": 0.07, "CRWV": 0.07,
    "ASML": 0.07, "NBIS": 0.05, "RIOT": 0.05,
    "AMD": 0.05, "AMAT": 0.05, "MRVL": 0.05, "VRT": 0.05
}

# Risk controls
MIN_CASH_RESERVE_PCT  = 0.05    # 5% of account value
MAX_TRADES_PER_DAY    = 10
MAX_CASH_DEPLOY_PCT   = 0.50    # 50% of available cash per session
MIN_TRADE_SIZE        = 25      # $ minimum per trade
CONFIRMATION_THRESHOLD = 750    # $ — trades above this require manual confirmation
NVDA_MAX_TRIM_SESSION = 500     # $ max NVDA sell per session

# Tiered drawdown thresholds (from high-water mark)
DRAWDOWN_REDUCE   = 0.10   # -10%: cap deployment at 25% of cash
DRAWDOWN_PAUSE_BUYS = 0.15 # -15%: no new buys, trims only
DRAWDOWN_FULL_STOP  = 0.20 # -20%: full stop, notify user

# 2026 US market holidays (NYSE closed)
MARKET_HOLIDAYS_2026 = {
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 19),  # MLK Day
    date(2026, 2, 16),  # Presidents' Day
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 6, 19),  # Juneteenth
    date(2026, 7, 3),   # Independence Day (observed)
    date(2026, 9, 7),   # Labor Day
    date(2026, 11, 26), # Thanksgiving
    date(2026, 12, 25), # Christmas
}

# ── HELPERS ────────────────────────────────────────────────────────────────

def is_market_open():
    """Check if US equity market is currently open (ET)."""
    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    today = now.date()

    if today.weekday() >= 5:
        return False, "Weekend"
    if today in MARKET_HOLIDAYS_2026:
        return False, f"Market holiday: {today}"
    if now.hour < 9 or (now.hour == 9 and now.minute < 30):
        return False, "Pre-market (before 9:30 AM ET)"
    if now.hour >= 16:
        return False, "Market closed (after 4:00 PM ET)"

    return True, "Open"


def load_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: File not found: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {path}: {e}")
        sys.exit(1)


def load_state(path):
    """Load state.json, create default if missing."""
    try:
        return load_json(path)
    except SystemExit:
        print(f"WARNING: {path} not found. Using defaults. Run will be limited.")
        return {
            "account_number": AGENTIC_ACCOUNT,
            "account_value": 0,
            "buying_power": 0,
            "positions": {},
            "high_water_mark": 0,
            "trades_today": 0,
            "last_trade_date": None
        }


def get_trades_today(state):
    """Return trade count, resetting if it's a new ET calendar day."""
    last = state.get("last_trade_date")
    today = str(datetime.now(ZoneInfo("America/New_York")).date())
    if last != today:
        return 0
    return state.get("trades_today", 0)


# ── VALIDATOR ──────────────────────────────────────────────────────────────

def validate(proposals, state, dry_run=False):
    violations = []
    warnings = []
    account_value = state.get("account_value", 0)
    buying_power = state.get("buying_power", 0)
    # Normalize positions — state.json stores {symbol: {value, pct}} or {symbol: float}
    raw_positions = state.get("positions", {})
    positions = {}
    for sym, val in raw_positions.items():
        if isinstance(val, dict):
            if "value" not in val:
                logging.warning(f"Malformed position entry for {sym}: missing 'value' key")
            positions[sym] = val.get("value", 0)
        else:
            positions[sym] = val
    high_water_mark = state.get("high_water_mark", account_value)
    trades_today = get_trades_today(state)

    # ── State integrity check ──────────────────────────────────
    if high_water_mark > 0 and account_value > 0:
        if high_water_mark < account_value:
            logging.warning(f"State integrity: HWM (${high_water_mark:,.2f}) < account value (${account_value:,.2f}). Auto-correcting.")
            high_water_mark = account_value

    # ── Account check ──────────────────────────────────────────
    acct = state.get("account_number", "")
    if acct != AGENTIC_ACCOUNT:
        violations.append(f"WRONG ACCOUNT: {acct} — must be {AGENTIC_ACCOUNT}")

    # ── Market hours ───────────────────────────────────────────
    market_open, market_status = is_market_open()
    if not market_open:
        violations.append(f"Market not open: {market_status}")

    # ── Drawdown check ─────────────────────────────────────────
    drawdown = 0
    if high_water_mark > 0:
        drawdown = (high_water_mark - account_value) / high_water_mark

    if drawdown >= DRAWDOWN_FULL_STOP:
        violations.append(
            f"FULL STOP — drawdown {drawdown*100:.1f}% exceeds {DRAWDOWN_FULL_STOP*100:.0f}% limit. "
            "Manual review required before any trading resumes."
        )
    elif drawdown >= DRAWDOWN_PAUSE_BUYS:
        buy_proposals = [p for p in proposals if p.get("action","").upper() == "BUY"]
        if buy_proposals:
            violations.append(
                f"BUY PAUSE — drawdown {drawdown*100:.1f}% exceeds {DRAWDOWN_PAUSE_BUYS*100:.0f}%. "
                "No new buys allowed. Trims only."
            )
    elif drawdown >= DRAWDOWN_REDUCE:
        warnings.append(
            f"Drawdown {drawdown*100:.1f}% — max cash deployment reduced to 25% of buying power."
        )

    # ── Trade count ────────────────────────────────────────────
    total_trades = trades_today + len(proposals)
    if total_trades > MAX_TRADES_PER_DAY:
        violations.append(
            f"Trade count {total_trades} exceeds daily max {MAX_TRADES_PER_DAY} "
            f"({trades_today} already executed today)."
        )

    # ── Total cash deployment ──────────────────────────────────
    total_buy_amount = sum(
        p.get("amount", 0) for p in proposals
        if p.get("action", "").upper() == "BUY"
    )

    # Reduce cap if in drawdown warning zone
    effective_cap = (0.25 if drawdown >= DRAWDOWN_REDUCE else MAX_CASH_DEPLOY_PCT) * buying_power

    if total_buy_amount > effective_cap:
        violations.append(
            f"Total buy amount ${total_buy_amount:.2f} exceeds "
            f"{'reduced ' if drawdown >= DRAWDOWN_REDUCE else ''}session cap "
            f"${effective_cap:.2f}."
        )

    # ── Per-trade checks ───────────────────────────────────────
    projected_positions = dict(positions)

    for p in proposals:
        sym    = p.get("symbol", "").upper()
        action = p.get("action", "").upper()
        amount = p.get("amount", 0)

        # Universe
        if sym not in UNIVERSE:
            violations.append(f"{sym}: Not in approved universe.")

        # Min trade size
        if amount < MIN_TRADE_SIZE:
            violations.append(f"{sym}: Trade amount ${amount} below minimum ${MIN_TRADE_SIZE}.")

        # Confirmation threshold
        if amount > CONFIRMATION_THRESHOLD:
            violations.append(
                f"{sym}: Trade amount ${amount} exceeds confirmation threshold "
                f"${CONFIRMATION_THRESHOLD} — requires manual approval."
            )

        # NVDA trim limit
        if sym == "NVDA" and action == "SELL":
            if amount > NVDA_MAX_TRIM_SESSION:
                violations.append(
                    f"NVDA: Trim amount ${amount} exceeds session limit ${NVDA_MAX_TRIM_SESSION}."
                )

        # Position limit (post-trade projection)
        if action == "BUY" and account_value > 0:
            current_val = projected_positions.get(sym, 0)
            new_val = current_val + amount
            new_pct = new_val / account_value
            max_pct = MAX_ALLOCS.get(sym, 0.05)

            if new_pct > max_pct + 0.03:  # 3% buffer for rounding
                violations.append(
                    f"{sym}: Post-trade weight {new_pct*100:.1f}% would exceed "
                    f"max allocation {max_pct*100:.1f}%."
                )

            # Update projection for subsequent trades in same session
            projected_positions[sym] = new_val

    # ── Cash reserve after all buys ────────────────────────────
    if account_value > 0:
        cash_after = buying_power - total_buy_amount
        reserve_pct = cash_after / account_value
        if reserve_pct < MIN_CASH_RESERVE_PCT:
            violations.append(
                f"Cash reserve after trades {reserve_pct*100:.1f}% would fall below "
                f"minimum {MIN_CASH_RESERVE_PCT*100:.0f}%."
            )

    return violations, warnings


# ── STATE UPDATE ───────────────────────────────────────────────────────────

def update_state(state_path, state, proposals, result_pass):
    """Update state.json after a successful session."""
    if not result_pass:
        return  # Don't update state if validation failed

    account_value = state.get("account_value", 0)
    high_water_mark = state.get("high_water_mark", 0)
    trades_today = get_trades_today(state)

    state["high_water_mark"] = max(high_water_mark, account_value)
    state["trades_today"] = trades_today + len(proposals)
    et_now = datetime.now(ZoneInfo("America/New_York"))
    state["last_trade_date"] = str(et_now.date())
    state["last_updated"] = et_now.strftime("%Y-%m-%d %H:%M:%S ET")

    # Backup current state before overwriting
    try:
        shutil.copy(state_path, state_path + ".bak")
        logging.info(f"State backup written: {state_path}.bak")
    except FileNotFoundError:
        pass  # No existing state to back up

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)
    print(f"\nState updated: {state_path}")


# ── MAIN ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Trading Agent Validator")
    parser.add_argument("--proposals", required=True, help="Path to proposals.json")
    parser.add_argument("--state",     required=True, help="Path to state.json")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Validate only, do not update state.json")
    args = parser.parse_args()

    proposals_data = load_json(args.proposals)
    state = load_state(args.state)

    proposals = proposals_data.get("proposals", proposals_data)
    if not isinstance(proposals, list):
        print("ERROR: proposals.json must contain a list under 'proposals' key.")
        sys.exit(1)

    print(f"\n{'='*55}")
    print(f"  Trading Agent Validator — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Account:   {state.get('account_number','?')}")
    print(f"  Value:     ${state.get('account_value',0):,.2f}")
    print(f"  Cash:      ${state.get('buying_power',0):,.2f}")
    print(f"  HWM:       ${state.get('high_water_mark',0):,.2f}")
    print(f"  Proposals: {len(proposals)} trade(s)")
    print(f"{'='*55}\n")

    violations, warnings = validate(proposals, state, args.dry_run)

    if not violations:
        logging.info(f"Validation PASSED — {len(proposals)} proposal(s) cleared all checks")
    else:
        logging.warning(f"Validation FAILED — {len(violations)} violation(s) found")
        for v in violations:
            logging.warning(f"  Violation: {v}")

    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  ⚠  {w}")
        print()

    if violations:
        print("VIOLATIONS:")
        for v in violations:
            print(f"  ✗  {v}")
        print(f"\n{'='*55}")
        print("  RESULT: FAIL — DO NOT EXECUTE TRADES")
        print(f"{'='*55}\n")
        sys.exit(1)
    else:
        print("All checks passed.")
        print(f"\n{'='*55}")
        print("  RESULT: PASS — Safe to execute via Robinhood MCP")
        print(f"{'='*55}\n")
        if not args.dry_run:
            update_state(args.state, state, proposals, True)
        sys.exit(0)


if __name__ == "__main__":
    main()
