#!/usr/bin/env python3
"""
Autonomous AI Trading Agent - Deterministic Validator v1.4
Enforces hard rules before any trade reaches Robinhood MCP.

Usage:
  python validator.py --proposals proposals.json --state state.json
  python validator.py --proposals proposals.json --state state.json --dry-run

Output: PASS or FAIL with full violation list. Exits 0 on PASS, 1 on FAIL.

v1.1 changes:
  - Loads target_allocs and tiers from config.json
  - Auto-detects Tier 3 build phase vs steady state
  - Entry threshold check added (warnings, not violations)
  - Version checking between config and validator

v1.2 changes:
  - Version bumped to match config.json v1.2 (AMD/AMAT/MRVL/VRT @ 2% target).
    No logic change; validator reads target_allocs dynamically from config.
"""

import json
import shutil
import sys
import argparse
from datetime import date, datetime
from zoneinfo import ZoneInfo
import logging

import os as _os

_CONFIG_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "config.json")

VALIDATOR_VERSION = "1.4"

def _load_config():
    try:
        with open(_CONFIG_PATH, "r") as _f:
            _cfg = json.load(_f)
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        cfg_version = _cfg.get("_version", "unknown")
        logging.info(f"Config loaded from {_CONFIG_PATH} (version {cfg_version})")
        if cfg_version != VALIDATOR_VERSION:
            logging.warning(
                f"Version mismatch: validator v{VALIDATOR_VERSION} / "
                f"config v{cfg_version} — verify both files are in sync."
            )
        return _cfg
    except FileNotFoundError:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        logging.error(
            f"config.json not found at {_CONFIG_PATH} — refusing to run on "
            f"stale hardcoded defaults. Fetch config.json before validating."
        )
        sys.exit(1)


def check_tier_band_invariant(cfg):
    """
    Verify the sum of per-name target_allocs in each tier falls within that
    tier's [floor, ceiling] band (config.json -> tier_bands). This catches an
    internally inconsistent config (e.g. Tier 2 per-name targets summing below
    the band floor) at load time and in CI, before any live run.
    Returns (ok: bool, messages: list[str]).
    """
    tiers = cfg.get("tiers", {})
    targets = cfg.get("target_allocs", {})
    bands = cfg.get("tier_bands", {})
    if not bands:
        return True, ["tier_bands not defined - invariant check skipped"]
    sums = {}
    for sym, t in tiers.items():
        sums[str(t)] = sums.get(str(t), 0.0) + targets.get(sym, 0.0)
    ok = True
    msgs = []
    for t in sorted(k for k in bands.keys() if k != "_note"):
        s = round(sums.get(t, 0.0), 6)
        floor = bands[t]["floor"]
        ceil = bands[t]["ceiling"]
        if s < floor - 1e-9 or s > ceil + 1e-9:
            ok = False
            msgs.append(
                f"Tier {t}: target sum {s*100:.1f}% OUTSIDE band "
                f"{floor*100:.0f}-{ceil*100:.0f}%"
            )
        else:
            msgs.append(
                f"Tier {t}: target sum {s*100:.1f}% within band "
                f"{floor*100:.0f}-{ceil*100:.0f}%"
            )
    return ok, msgs


_cfg = _load_config()

if _cfg:
    AGENTIC_ACCOUNT       = _cfg.get("agentic_account", "926627357")
    UNIVERSE              = set(_cfg.get("universe", []))
    MAX_ALLOCS            = _cfg.get("max_allocs", {})
    TARGET_ALLOCS         = _cfg.get("target_allocs", {})
    TIERS                 = _cfg.get("tiers", {})
    _rc                   = _cfg.get("risk_controls", {})
    MIN_CASH_RESERVE_PCT  = _rc.get("min_cash_reserve_pct", 0.05)
    MAX_TRADES_PER_DAY    = _rc.get("max_trades_per_day", 10)
    MAX_CASH_DEPLOY_PCT   = _rc.get("max_cash_deploy_pct", 0.50)
    MIN_TRADE_SIZE        = _rc.get("min_trade_size_usd", 25)
    CONFIRMATION_THRESHOLD= _rc.get("confirmation_threshold_usd", 750)
    NVDA_MAX_TRIM_SESSION = _rc.get("nvda_max_trim_per_session_usd", 500)
    _dd                   = _cfg.get("drawdown", {})
    DRAWDOWN_REDUCE       = _dd.get("reduce_deploy_at_pct", 0.10)
    DRAWDOWN_PAUSE_BUYS   = _dd.get("pause_buys_at_pct", 0.15)
    DRAWDOWN_FULL_STOP    = _dd.get("full_stop_at_pct", 0.20)
    _et                   = _cfg.get("entry_thresholds", {})
    ENTRY_THRESH_T1       = _et.get("tier1", 2.0)
    ENTRY_THRESH_T2       = _et.get("tier2", 2.0)
    ENTRY_THRESH_T3_BUILD = _et.get("tier3_build_phase", 1.5)
    ENTRY_THRESH_T3_STEADY= _et.get("tier3_steady_state", 2.0)
    ENTRY_THRESH_T4       = _et.get("tier4", 2.0)
    ENTRY_THRESH_T4_LOW   = _et.get("tier4_low", 1.0)
    TIER3_BUILD_COMPLETE  = _et.get("tier3_build_complete_at_pct", 15.0) / 100.0
    MAX_ALLOC_BUFFER_PP   = _rc.get("max_alloc_buffer_pp", 3.0) / 100.0
    DRAWDOWN_REDUCE_CAP   = _dd.get("reduce_deploy_cap", 0.25)
    MARKET_HOLIDAYS_2026  = {
        date.fromisoformat(d)
        for d in _cfg.get("market_holidays_2026", [])
    }
else:
    AGENTIC_ACCOUNT = "926627357"
    UNIVERSE = {
        "NVDA", "AVGO", "MU",
        "CEG", "GEV", "VST", "BE",
        "IREN", "APLD", "CORZ", "CRWV",
        "ASML", "NBIS", "RIOT",
        "AMD", "AMAT", "MRVL", "VRT"
    }
    MAX_ALLOCS = {
        "NVDA": 0.25, "AVGO": 0.15, "MU": 0.12,
        "CEG": 0.08, "GEV": 0.08, "VST": 0.07, "BE": 0.08,
        "IREN": 0.07, "APLD": 0.07, "CORZ": 0.07, "CRWV": 0.07,
        "ASML": 0.07, "NBIS": 0.05, "RIOT": 0.05,
        "AMD": 0.05, "AMAT": 0.05, "MRVL": 0.05, "VRT": 0.05
    }
    TARGET_ALLOCS = {
        "NVDA": 0.20, "AVGO": 0.12, "MU": 0.10,
        "CEG": 0.05, "GEV": 0.05, "VST": 0.04, "BE": 0.05,
        "IREN": 0.04, "APLD": 0.04, "CORZ": 0.04, "CRWV": 0.04,
        "ASML": 0.04, "NBIS": 0.03, "RIOT": 0.03,
        "AMD": 0.02, "AMAT": 0.02, "MRVL": 0.02, "VRT": 0.02
    }
    TIERS = {
        "NVDA": 1, "AVGO": 1, "MU": 1,
        "CEG": 2, "GEV": 2, "VST": 2, "BE": 2,
        "IREN": 3, "APLD": 3, "CORZ": 3, "CRWV": 3,
        "ASML": 4, "NBIS": 4, "RIOT": 4,
        "AMD": 4, "AMAT": 4, "MRVL": 4, "VRT": 4
    }
    MIN_CASH_RESERVE_PCT   = 0.05
    MAX_TRADES_PER_DAY     = 10
    MAX_CASH_DEPLOY_PCT    = 0.50
    MIN_TRADE_SIZE         = 25
    CONFIRMATION_THRESHOLD = 750
    NVDA_MAX_TRIM_SESSION  = 500
    DRAWDOWN_REDUCE        = 0.10
    DRAWDOWN_PAUSE_BUYS    = 0.15
    DRAWDOWN_FULL_STOP     = 0.20
    ENTRY_THRESH_T1        = 2.0
    ENTRY_THRESH_T2        = 2.0
    ENTRY_THRESH_T3_BUILD  = 1.5
    ENTRY_THRESH_T3_STEADY = 2.0
    ENTRY_THRESH_T4        = 2.0
    ENTRY_THRESH_T4_LOW    = 1.0
    TIER3_BUILD_COMPLETE   = 0.15
    MAX_ALLOC_BUFFER_PP    = 0.03
    DRAWDOWN_REDUCE_CAP    = 0.25
    MARKET_HOLIDAYS_2026   = {
        date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16),
        date(2026, 4, 3), date(2026, 5, 25), date(2026, 6, 19),
        date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26),
        date(2026, 12, 25),
    }

TIER3_SYMBOLS = {sym for sym, t in TIERS.items() if t == 3}

# B2: config-consistency check at load (soft warning; CI test enforces hard).
if _cfg:
    _band_ok, _band_msgs = check_tier_band_invariant(_cfg)
    for _m in _band_msgs:
        logging.info("Tier band check - " + _m)
    if not _band_ok:
        logging.warning(
            "CONFIG INCONSISTENCY: one or more tier target sums fall outside "
            "their band. Per-name targets and tier_bands disagree - fix config.json."
        )




def is_market_open():
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
    try:
        return load_json(path)
    except SystemExit:
        print(f"WARNING: {path} not found. Using defaults.")
        return {
            "account_number": AGENTIC_ACCOUNT,
            "account_value": 0, "buying_power": 0,
            "positions": {}, "high_water_mark": 0,
            "trades_today": 0, "last_trade_date": None
        }


def get_trades_today(state):
    last = state.get("last_trade_date")
    today = str(datetime.now(ZoneInfo("America/New_York")).date())
    if last != today:
        return 0
    return state.get("trades_today", 0)


def get_entry_threshold(sym, tier3_in_build_phase):
    tier = TIERS.get(sym, 0)
    if tier == 1:
        return ENTRY_THRESH_T1, "Tier 1"
    elif tier == 2:
        return ENTRY_THRESH_T2, "Tier 2"
    elif tier == 3:
        if tier3_in_build_phase:
            return ENTRY_THRESH_T3_BUILD, "Tier 3 build phase"
        else:
            return ENTRY_THRESH_T3_STEADY, "Tier 3 steady state"
    elif tier == 4:
        target_pct = TARGET_ALLOCS.get(sym, 0)
        if target_pct <= 0.025:  # AMD/AMAT/MRVL/VRT — 2% target
            return ENTRY_THRESH_T4_LOW, "Tier 4 (low-target)"
        else:  # ASML/NBIS/RIOT — 3% target
            return ENTRY_THRESH_T4, "Tier 4"
    else:
        return 2.0, "default"


def validate(proposals, state, dry_run=False):
    violations = []
    warnings = []

    # H2: coerce every proposal amount to float up front. A non-numeric amount
    # becomes a clean violation instead of crashing the summation math below.
    for p in proposals:
        raw = p.get("amount", 0)
        try:
            p["amount"] = float(raw)
        except (TypeError, ValueError):
            sym = p.get("symbol", "?").upper()
            violations.append(f"{sym}: non-numeric amount {raw!r}.")
            p["amount"] = 0.0
    account_value = state.get("account_value", 0)
    buying_power = state.get("buying_power", 0)

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

    if high_water_mark > 0 and account_value > 0:
        if high_water_mark < account_value:
            logging.warning(f"State integrity: HWM < account value. Auto-correcting.")
            high_water_mark = account_value

    # Tier 3 build phase auto-detection
    tier3_value = sum(positions.get(sym, 0) for sym in TIER3_SYMBOLS)
    tier3_pct = tier3_value / account_value if account_value > 0 else 0
    tier3_in_build_phase = tier3_pct < TIER3_BUILD_COMPLETE
    logging.info(
        f"Tier 3 combined: {tier3_pct*100:.1f}% (threshold: {TIER3_BUILD_COMPLETE*100:.0f}%) — "
        f"{'BUILD PHASE (1.5% entry)' if tier3_in_build_phase else 'STEADY STATE (2% entry)'}"
    )

    # Account check
    acct = state.get("account_number", "")
    if acct != AGENTIC_ACCOUNT:
        violations.append(f"WRONG ACCOUNT: {acct} — must be {AGENTIC_ACCOUNT}")

    # Market hours
    market_open, market_status = is_market_open()
    if not market_open:
        violations.append(f"Market not open: {market_status}")

    # Drawdown
    drawdown = 0
    if high_water_mark > 0:
        drawdown = (high_water_mark - account_value) / high_water_mark

    if drawdown >= DRAWDOWN_FULL_STOP:
        violations.append(
            f"FULL STOP — drawdown {drawdown*100:.1f}% exceeds "
            f"{DRAWDOWN_FULL_STOP*100:.0f}% limit. Manual review required."
        )
    elif drawdown >= DRAWDOWN_PAUSE_BUYS:
        buy_proposals = [p for p in proposals if p.get("action", "").upper() == "BUY"]
        if buy_proposals:
            violations.append(
                f"BUY PAUSE — drawdown {drawdown*100:.1f}% exceeds "
                f"{DRAWDOWN_PAUSE_BUYS*100:.0f}%. No new buys. Trims only."
            )
    elif drawdown >= DRAWDOWN_REDUCE:
        warnings.append(
            f"Drawdown {drawdown*100:.1f}% — max cash deployment reduced to "
            f"{DRAWDOWN_REDUCE_CAP*100:.0f}% of buying power."
        )

    # Trade count
    total_trades = trades_today + len(proposals)
    if total_trades > MAX_TRADES_PER_DAY:
        violations.append(
            f"Trade count {total_trades} exceeds daily max {MAX_TRADES_PER_DAY} "
            f"({trades_today} already executed today)."
        )

    # Total cash deployment (N4: net sells against buys — a rebalance funded
    # by same-session sales is not net-new cash deployment).
    total_buy_amount = sum(
        p.get("amount", 0) for p in proposals
        if p.get("action", "").upper() == "BUY"
    )
    total_sell_amount = sum(
        p.get("amount", 0) for p in proposals
        if p.get("action", "").upper() == "SELL"
    )
    net_deployment = total_buy_amount - total_sell_amount
    effective_cap = (
        DRAWDOWN_REDUCE_CAP if drawdown >= DRAWDOWN_REDUCE else MAX_CASH_DEPLOY_PCT
    ) * buying_power

    if net_deployment > effective_cap:
        violations.append(
            f"Net cash deployment ${net_deployment:.2f} exceeds "
            f"{'reduced ' if drawdown >= DRAWDOWN_REDUCE else ''}session cap "
            f"${effective_cap:.2f}."
        )

    # N2: PDT rule — same symbol proposed as both BUY and SELL in one session.
    _buys  = {p.get("symbol","").upper() for p in proposals
              if p.get("action","").upper() == "BUY"}
    _sells = {p.get("symbol","").upper() for p in proposals
              if p.get("action","").upper() == "SELL"}
    for _sym in sorted(_buys & _sells):
        violations.append(
            f"{_sym}: PDT risk — BUY and SELL of the same symbol in one "
            f"session is not permitted (sub-$25K account)."
        )

    # Per-trade checks
    projected_positions = dict(positions)

    for p in proposals:
        sym    = p.get("symbol", "").upper()
        action = p.get("action", "").upper()
        amount = p.get("amount", 0)
        # H1: accept either 'reason' or 'rationale' (docs use 'rationale')
        reason = p.get("reason", p.get("rationale", ""))

        if sym not in UNIVERSE:
            violations.append(f"{sym}: Not in approved universe.")

        if amount < MIN_TRADE_SIZE:
            violations.append(f"{sym}: Trade amount ${amount} below minimum ${MIN_TRADE_SIZE}.")

        # N3: >$750 is blocked in autonomous runs (no one to confirm at run
        # time). A proposal may carry "confirmed": true — set only by the user
        # in a supervised run — which downgrades the block to a warning.
        if amount > CONFIRMATION_THRESHOLD:
            if p.get("confirmed", False) is True:
                warnings.append(
                    f"{sym}: Trade amount ${amount:.2f} exceeds ${CONFIRMATION_THRESHOLD} "
                    f"but carries confirmed=true — allowed."
                )
            else:
                violations.append(
                    f"{sym}: Trade amount ${amount:.2f} exceeds confirmation threshold "
                    f"${CONFIRMATION_THRESHOLD} — set \"confirmed\": true to approve."
                )

        if sym == "NVDA" and action == "SELL":
            if amount > NVDA_MAX_TRIM_SESSION:
                violations.append(
                    f"NVDA: Trim amount ${amount} exceeds session limit ${NVDA_MAX_TRIM_SESSION}."
                )

        # N1: a SELL cannot exceed the current value of the held position.
        if action == "SELL":
            held_val = positions.get(sym, 0)
            if amount > held_val + 1e-6:
                violations.append(
                    f"{sym}: SELL ${amount:.2f} exceeds held position value "
                    f"${held_val:.2f}."
                )

        if action == "BUY" and account_value > 0:
            current_val = projected_positions.get(sym, 0)
            new_val = current_val + amount
            new_pct = new_val / account_value
            max_pct = MAX_ALLOCS.get(sym, 0.05)

            if new_pct > max_pct + MAX_ALLOC_BUFFER_PP:
                violations.append(
                    f"{sym}: Post-trade weight {new_pct*100:.1f}% would exceed "
                    f"max allocation {max_pct*100:.1f}%."
                )

            projected_positions[sym] = new_val

            # Entry threshold check (warning only)
            target_pct = TARGET_ALLOCS.get(sym, 0)
            is_new_position = positions.get(sym, 0) == 0
            is_override = reason in (
                "earnings_rule", "earnings_override",
                "new_position", "capital_injection"
            )

            if target_pct > 0 and not is_new_position and not is_override:
                current_pct = positions.get(sym, 0) / account_value
                gap_pp = (target_pct - current_pct) * 100
                threshold_pp, threshold_label = get_entry_threshold(
                    sym, tier3_in_build_phase
                )

                if gap_pp < 0:
                    warnings.append(
                        f"{sym}: BUY proposed but position is AT or ABOVE target "
                        f"({current_pct*100:.1f}% vs {target_pct*100:.1f}% target). "
                        f"Verify earnings rule or rebalance intent."
                    )
                elif gap_pp < threshold_pp:
                    warnings.append(
                        f"{sym}: BUY proposed with {gap_pp:.2f}% gap to target "
                        f"(threshold: {threshold_pp:.1f}%, {threshold_label}). "
                        f"Verify entry trigger — earnings rule or override may apply."
                    )

    # Cash reserve (N4: sell proceeds add to cash — credit them so a
    # cash-neutral rebalance is not falsely blocked below the floor).
    if account_value > 0:
        cash_after = buying_power - total_buy_amount + total_sell_amount
        reserve_pct = cash_after / account_value
        if reserve_pct < MIN_CASH_RESERVE_PCT:
            violations.append(
                f"Cash reserve after trades {reserve_pct*100:.1f}% would fall below "
                f"minimum {MIN_CASH_RESERVE_PCT*100:.0f}%."
            )

    return violations, warnings


def update_state(state_path, state, proposals, result_pass):
    if not result_pass:
        return
    account_value = state.get("account_value", 0)
    high_water_mark = state.get("high_water_mark", 0)
    trades_today = get_trades_today(state)
    state["high_water_mark"] = max(high_water_mark, account_value)
    state["trades_today"] = trades_today + len(proposals)
    et_now = datetime.now(ZoneInfo("America/New_York"))
    state["last_trade_date"] = str(et_now.date())
    state["last_updated"] = et_now.strftime("%Y-%m-%d %H:%M:%S ET")
    try:
        shutil.copy(state_path, state_path + ".bak")
        logging.info(f"State backup written: {state_path}.bak")
    except FileNotFoundError:
        pass
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)
    print(f"\nState updated: {state_path}")


def main():
    parser = argparse.ArgumentParser(description="Trading Agent Validator v1.4")
    parser.add_argument("--proposals", required=True)
    parser.add_argument("--state",     required=True)
    parser.add_argument("--dry-run",   action="store_true")
    args = parser.parse_args()

    proposals_data = load_json(args.proposals)
    state = load_state(args.state)
    proposals = proposals_data.get("proposals", proposals_data)
    if not isinstance(proposals, list):
        print("ERROR: proposals.json must contain a list under 'proposals' key.")
        sys.exit(1)

    cfg_version = _cfg.get("_version", "fallback") if _cfg else "fallback"
    print(f"\n{'='*55}")
    print(f"  Trading Agent Validator v{VALIDATOR_VERSION} — "
          f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Config:    v{cfg_version}"
          + (" ✓" if cfg_version == VALIDATOR_VERSION else " ⚠ VERSION MISMATCH"))
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