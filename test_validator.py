#!/usr/bin/env python3
"""
test_validator.py — Unit tests for Trading Agent Validator v1.1

Tests all critical safety scenarios. Run with:
  python3 test_validator.py
  python3 test_validator.py -v  (verbose)

All tests mock market hours as OPEN unless specifically testing market hours.
"""

import copy
import sys
import os
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validator

BASE_STATE = {
    "account_number": "926627357",
    "account_value": 8887.15,
    "buying_power": 1530.19,
    "high_water_mark": 8887.15,
    "trades_today": 0,
    "last_trade_date": "2026-06-24",
    "positions": {
        "NVDA": {"value": 2061.74, "pct": 0.2320},
        "AVGO": {"value": 1072.88, "pct": 0.1207},
        "MU":   {"value":  811.08, "pct": 0.0913},
        "CEG":  {"value":  342.96, "pct": 0.0386},
        "GEV":  {"value":  339.21, "pct": 0.0382},
        "VST":  {"value":  300.55, "pct": 0.0338},
        "BE":   {"value":  374.74, "pct": 0.0422},
        "IREN": {"value":  345.96, "pct": 0.0389},
        "APLD": {"value":  349.55, "pct": 0.0393},
        "CORZ": {"value":  351.15, "pct": 0.0395},
        "CRWV": {"value":  354.03, "pct": 0.0398},
        "ASML": {"value":  326.27, "pct": 0.0367},
        "NBIS": {"value":  311.06, "pct": 0.0350},
        "RIOT": {"value":   13.58, "pct": 0.0015},
    }
}

def make_state(**overrides):
    state = copy.deepcopy(BASE_STATE)
    state.update(overrides)
    return state

def make_proposal(symbol, action, amount, reason=None):
    p = {"symbol": symbol, "action": action, "amount": amount}
    if reason:
        p["reason"] = reason
    return p

def today_et():
    return str(datetime.now(ZoneInfo("America/New_York")).date())

MARKET_OPEN = patch("validator.is_market_open", return_value=(True, "Open"))


class TestAccountSafety(unittest.TestCase):
    """Account number must always match 926627357."""

    @MARKET_OPEN
    def test_wrong_account_halts(self, _):
        state = make_state(account_number="999999999")
        violations, _ = validator.validate([], state)
        self.assertTrue(any("WRONG ACCOUNT" in v for v in violations),
            "Wrong account number must be flagged")

    @MARKET_OPEN
    def test_correct_account_passes(self, _):
        violations, _ = validator.validate([], BASE_STATE)
        self.assertFalse(any("WRONG ACCOUNT" in v for v in violations),
            "Correct account must not be flagged")


class TestMarketHours(unittest.TestCase):
    """Trades must not execute outside market hours."""

    def test_pre_market_blocks_trades(self):
        with patch("validator.is_market_open",
                   return_value=(False, "Pre-market (before 9:30 AM ET)")):
            violations, _ = validator.validate(
                [make_proposal("MU", "BUY", 100)], BASE_STATE)
            self.assertTrue(any("Market not open" in v for v in violations),
                "Pre-market must block trades")

    @MARKET_OPEN
    def test_open_market_allows_trades(self, _):
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 100)], BASE_STATE)
        self.assertFalse(any("Market not open" in v for v in violations),
            "Open market must not flag market hours")


class TestDrawdownTiers(unittest.TestCase):
    """Drawdown tiers must enforce correct restrictions."""

    @MARKET_OPEN
    def test_full_stop_at_20pct(self, _):
        state = make_state(account_value=7020.85, high_water_mark=8887.15)
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 100)], state)
        self.assertTrue(any("FULL STOP" in v for v in violations),
            "20%+ drawdown must trigger FULL STOP")

    @MARKET_OPEN
    def test_buy_pause_at_15pct(self, _):
        state = make_state(account_value=7465.21, high_water_mark=8887.15)
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 100)], state)
        self.assertTrue(any("BUY PAUSE" in v for v in violations),
            "15%+ drawdown must pause buys")

    @MARKET_OPEN
    def test_reduced_cap_at_10pct_is_warning_not_violation(self, _):
        state = make_state(account_value=7909.56, high_water_mark=8887.15)
        violations, warnings = validator.validate(
            [make_proposal("MU", "BUY", 100)], state)
        self.assertFalse(
            any("FULL STOP" in v or "BUY PAUSE" in v for v in violations),
            "10% drawdown must not trigger full stop or buy pause")
        self.assertTrue(any("Drawdown" in w for w in warnings),
            "10% drawdown must produce a warning")

    @MARKET_OPEN
    def test_no_drawdown_normal_operation(self, _):
        violations, _ = validator.validate([], BASE_STATE)
        self.assertFalse(
            any("FULL STOP" in v or "BUY PAUSE" in v for v in violations),
            "Zero drawdown must not trigger any drawdown violations")


class TestUniverseEnforcement(unittest.TestCase):
    """Only approved universe stocks may be traded."""

    @MARKET_OPEN
    def test_non_universe_stock_blocked(self, _):
        violations, _ = validator.validate(
            [make_proposal("TSLA", "BUY", 100)], BASE_STATE)
        self.assertTrue(
            any("TSLA" in v and "universe" in v.lower() for v in violations),
            "Non-universe stock must be blocked")

    @MARKET_OPEN
    def test_universe_stock_allowed(self, _):
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 100)], BASE_STATE)
        self.assertFalse(any("universe" in v.lower() for v in violations),
            "Universe stock must not trigger universe violation")


class TestAllocationLimits(unittest.TestCase):
    """Per-position max allocations must be enforced including multi-trade projection."""

    @MARKET_OPEN
    def test_nvda_max_allocation_breach(self, _):
        # NVDA at 23.2%. Max 25%, violation fires at 28% (max + 3% buffer).
        # $2061 + $430 = $2491 / $8887 = 28.03% — just over threshold.
        violations, _ = validator.validate(
            [make_proposal("NVDA", "BUY", 430)], BASE_STATE)
        self.assertTrue(
            any("NVDA" in v and "exceed" in v.lower() for v in violations),
            "NVDA buy breaching max + 3% buffer must be blocked")

    @MARKET_OPEN
    def test_buy_within_max_allowed(self, _):
        # MU at 9.13%. $811 + $80 = $891 / $8887 = 10.0% — well under 15% threshold.
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 80)], BASE_STATE)
        self.assertFalse(
            any("MU" in v and "exceed" in v.lower() for v in violations),
            "MU buy within max must not trigger allocation violation")

    @MARKET_OPEN
    def test_multi_trade_cumulative_projection(self, _):
        # Two MU buys of $300. Trade 1: $1111 (12.5%) — ok.
        # Trade 2: $1411 (15.9%) — over 15% (max + buffer) — violation fires.
        violations, _ = validator.validate([
            make_proposal("MU", "BUY", 300),
            make_proposal("MU", "BUY", 300),
        ], BASE_STATE)
        self.assertTrue(
            any("MU" in v and "exceed" in v.lower() for v in violations),
            "Cumulative multi-trade projection must catch combined allocation breach")


class TestNVDATrimCap(unittest.TestCase):
    """NVDA trim must not exceed $500 per session."""

    @MARKET_OPEN
    def test_nvda_trim_over_500_blocked(self, _):
        violations, _ = validator.validate(
            [make_proposal("NVDA", "SELL", 600)], BASE_STATE)
        self.assertTrue(
            any("NVDA" in v and "Trim" in v for v in violations),
            "NVDA trim over $500 must be blocked")

    @MARKET_OPEN
    def test_nvda_trim_at_500_allowed(self, _):
        violations, _ = validator.validate(
            [make_proposal("NVDA", "SELL", 500)], BASE_STATE)
        self.assertFalse(
            any("NVDA" in v and "Trim" in v for v in violations),
            "NVDA trim at exactly $500 must be allowed")


class TestConfirmationThreshold(unittest.TestCase):
    """Single trades over $750 require manual confirmation."""

    @MARKET_OPEN
    def test_trade_over_750_flagged(self, _):
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 800)], BASE_STATE)
        self.assertTrue(any("confirmation" in v.lower() for v in violations),
            "Trade over $750 must require confirmation")

    @MARKET_OPEN
    def test_trade_at_750_allowed(self, _):
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 750)], BASE_STATE)
        self.assertFalse(any("confirmation" in v.lower() for v in violations),
            "Trade at exactly $750 must not require confirmation")


class TestCashReserve(unittest.TestCase):
    """Cash reserve must remain at or above 5% after all buys."""

    @MARKET_OPEN
    def test_cash_reserve_breach_blocked(self, _):
        # $1530 - $1100 = $430 / $8887 = 4.84% < 5% — violation.
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 1100)], BASE_STATE)
        self.assertTrue(any("Cash reserve" in v for v in violations),
            "Trade breaching 5% cash reserve must be blocked")

    @MARKET_OPEN
    def test_cash_reserve_maintained(self, _):
        # $1530 - $400 = $1130 / $8887 = 12.7% — fine.
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 400)], BASE_STATE)
        self.assertFalse(any("Cash reserve" in v for v in violations),
            "Trade maintaining cash reserve must not be blocked")


class TestCashDeploymentCap(unittest.TestCase):
    """Total session buys must not exceed 50% of buying power."""

    @MARKET_OPEN
    def test_deployment_over_50pct_cap_blocked(self, _):
        # $1530 x 50% = $765 cap. $800 > $765 — violation.
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 800)], BASE_STATE)
        self.assertTrue(any("session cap" in v.lower() for v in violations),
            "Total buys over 50% cap must be blocked")

    @MARKET_OPEN
    def test_deployment_within_50pct_cap_allowed(self, _):
        # $700 < $765 cap — fine.
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 700)], BASE_STATE)
        self.assertFalse(any("session cap" in v.lower() for v in violations),
            "Total buys within 50% cap must not be blocked")


class TestTradeCount(unittest.TestCase):
    """Daily trade count must not exceed 10."""

    @MARKET_OPEN
    def test_trade_count_exceeded(self, _):
        state = make_state(trades_today=10, last_trade_date=today_et())
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 100)], state)
        self.assertTrue(any("Trade count" in v for v in violations),
            "Exceeding daily trade count must be blocked")

    @MARKET_OPEN
    def test_trade_count_within_limit(self, _):
        state = make_state(trades_today=5, last_trade_date=today_et())
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 100)], state)
        self.assertFalse(any("Trade count" in v for v in violations),
            "Trade count within limit must be allowed")

    @MARKET_OPEN
    def test_trade_count_resets_on_new_day(self, _):
        # trades_today=10 but last_trade_date is old — resets to 0.
        state = make_state(trades_today=10, last_trade_date="2026-01-01")
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 100)], state)
        self.assertFalse(any("Trade count" in v for v in violations),
            "Trade count must reset on new ET calendar day")


class TestMinTradeSize(unittest.TestCase):
    """Trades below $25 minimum must be rejected."""

    @MARKET_OPEN
    def test_trade_below_minimum_blocked(self, _):
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 20)], BASE_STATE)
        self.assertTrue(any("below minimum" in v.lower() for v in violations),
            "Trade below $25 minimum must be blocked")

    @MARKET_OPEN
    def test_trade_at_minimum_allowed(self, _):
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 25)], BASE_STATE)
        self.assertFalse(any("below minimum" in v.lower() for v in violations),
            "Trade at exactly $25 minimum must be allowed")


class TestEntryThresholds(unittest.TestCase):
    """Entry threshold checks fire as warnings, not violations."""

    @MARKET_OPEN
    def test_tier1_below_2pp_threshold_warns(self, _):
        # MU at 9.13% vs 10% target = 0.87% — below 2% Tier 1 threshold.
        _, warnings = validator.validate(
            [make_proposal("MU", "BUY", 80)], BASE_STATE)
        self.assertTrue(
            any("MU" in w and "0.87%" in w for w in warnings),
            "MU buy with 0.87% gap should warn about Tier 1 2% threshold")

    @MARKET_OPEN
    def test_threshold_warning_does_not_block_trade(self, _):
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 80)], BASE_STATE)
        self.assertFalse(
            any("MU" in v and "threshold" in v.lower() for v in violations),
            "Threshold miss must be a warning only, not a violation")

    @MARKET_OPEN
    def test_earnings_rule_suppresses_threshold_warning(self, _):
        _, warnings = validator.validate(
            [make_proposal("MU", "BUY", 80, reason="earnings_rule")], BASE_STATE)
        self.assertFalse(
            any("MU" in w and "threshold" in w.lower() for w in warnings),
            "earnings_rule reason must suppress threshold warning")

    @MARKET_OPEN
    def test_new_position_skips_threshold_check(self, _):
        # AMD not in positions — new position, skip threshold entirely.
        _, warnings = validator.validate(
            [make_proposal("AMD", "BUY", 100)], BASE_STATE)
        self.assertFalse(
            any("AMD" in w and "threshold" in w.lower() for w in warnings),
            "New position must skip entry threshold check")

    @MARKET_OPEN
    def test_tier3_steady_state_uses_2pp_threshold(self, _):
        # Tier 3 at 15.8% — steady state. IREN 3.89% vs 4% = 0.11pp — warns.
        _, warnings = validator.validate(
            [make_proposal("IREN", "BUY", 100)], BASE_STATE)
        self.assertTrue(
            any("IREN" in w and "threshold" in w.lower() for w in warnings),
            "IREN buy with 0.11pp gap must warn under 2pp steady state threshold")

    @MARKET_OPEN
    def test_tier3_build_phase_uses_1pt5pp_threshold(self, _):
        # Force T3 below 15% — build phase (1.5pp). IREN at 2.2% = 1.8pp gap.
        # 1.8pp >= 1.5pp — no warning.
        state = copy.deepcopy(BASE_STATE)
        for sym in ["IREN", "APLD", "CORZ", "CRWV"]:
            state["positions"][sym] = {"value": 200.0, "pct": 0.0225}
        state["positions"]["IREN"] = {"value": 195.52, "pct": 0.0220}
        _, warnings = validator.validate(
            [make_proposal("IREN", "BUY", 100)], state)
        self.assertFalse(
            any("IREN" in w and "threshold" in w.lower() for w in warnings),
            "1.8pp gap must clear 1.5pp build phase threshold — no warning")


class TestTier3AutoDetection(unittest.TestCase):
    """Tier 3 build phase auto-detection from live position data."""

    @MARKET_OPEN
    def test_tier3_above_15pct_is_steady_state(self, _):
        # BASE_STATE T3 at 15.8% — steady state. IREN 0.11pp gap warns with label.
        _, warnings = validator.validate(
            [make_proposal("IREN", "BUY", 100)], BASE_STATE)
        self.assertTrue(
            any("Tier 3 steady" in w for w in warnings),
            "Tier 3 at 15.8% must show steady state label in warning")

    @MARKET_OPEN
    def test_tier3_below_15pct_is_build_phase(self, _):
        # Reduce T3 to ~9% — build phase. IREN 1.8pp gap clears 1.5pp threshold.
        state = copy.deepcopy(BASE_STATE)
        for sym in ["IREN", "APLD", "CORZ", "CRWV"]:
            state["positions"][sym] = {"value": 200.0, "pct": 0.0225}
        state["positions"]["IREN"] = {"value": 195.52, "pct": 0.0220}
        _, warnings = validator.validate(
            [make_proposal("IREN", "BUY", 100)], state)
        self.assertFalse(
            any("IREN" in w and "threshold" in w.lower() for w in warnings),
            "1.8pp gap must clear 1.5pp build phase threshold")


class TestEmptyProposals(unittest.TestCase):
    """Empty proposal list must pass cleanly."""

    @MARKET_OPEN
    def test_empty_proposals_pass(self, _):
        violations, warnings = validator.validate([], BASE_STATE)
        self.assertEqual(violations, [],
            "Empty proposals must produce no violations")
        self.assertEqual(warnings, [],
            "Empty proposals must produce no warnings")




class TestTierBandInvariant(unittest.TestCase):
    """B2: per-name target sums must fall within each tier's band."""

    def test_current_config_satisfies_bands(self):
        # The shipped config.json must be internally consistent.
        ok, msgs = validator.check_tier_band_invariant(validator._cfg)
        self.assertTrue(ok, "Shipped config violates tier bands: " + "; ".join(msgs))

    def test_detects_tier_below_floor(self):
        # Simulate the historical Tier 2 bug (VST 4%, ASML 4% -> Tier 2 = 19%).
        import copy
        bad = copy.deepcopy(validator._cfg)
        bad["target_allocs"]["VST"] = 0.04
        bad["target_allocs"]["ASML"] = 0.04
        ok, msgs = validator.check_tier_band_invariant(bad)
        self.assertFalse(ok)
        self.assertTrue(any("Tier 2" in m and "OUTSIDE" in m for m in msgs))

    def test_missing_bands_skips_gracefully(self):
        import copy
        nob = copy.deepcopy(validator._cfg)
        nob.pop("tier_bands", None)
        ok, msgs = validator.check_tier_band_invariant(nob)
        self.assertTrue(ok)  # no bands defined -> skip, not fail


if __name__ == "__main__":
    unittest.main(verbosity=2)
