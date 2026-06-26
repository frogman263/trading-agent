import unittest
from datetime import datetime, timezone, timedelta
import validator

# ============================================================
# Test Helpers & Constants
# ============================================================

def make_proposal(symbol, action, amount):
    return {
        "symbol": symbol,
        "action": action,
        "amount": amount
    }

# Base state used across tests (approximate values from recent sessions)
BASE_STATE = {
    "account_number": "926627357",
    "account_value": 8887.0,
    "buying_power": 1200.0,
    "high_water_mark": 9200.0,
    "positions": {
        "NVDA": {"value": 2061, "price": 195.75},
        "AVGO": {"value": 1050, "price": 379.57},
        "MU": {"value": 811, "price": 1213.52},
        "CEG": {"value": 342, "price": 268.71},
        "GEV": {"value": 342, "price": 1085.04},
        "VST": {"value": 307, "price": 167.76},
        "BE": {"value": 336, "price": 309.145},
        "CORZ": {"value": 339, "price": 27.27},
        "IREN": {"value": 316, "price": 47.73},
        "CRWV": {"value": 334, "price": 98.81},
        "APLD": {"value": 332, "price": 40.93},
        "ASML": {"value": 325, "price": 1843.07},
        "NBIS": {"value": 296, "price": 256.635},
        "RIOT": {"value": 112, "price": 27.755}
    },
    "tax_lots": [],  # Populate as needed for STCG tests
    "trades_today": 0,
    "nvda_trades_today": 0
}

def MARKET_OPEN(func):
    """Decorator to skip tests outside market hours (for realism)."""
    def wrapper(self):
        now = datetime.now(timezone.utc)
        et_now = now.astimezone(timezone(timedelta(hours=-4)))
        if et_now.weekday() >= 5 or not (9 <= et_now.hour < 16):
            self.skipTest("Market is closed")
        return func(self)
    return wrapper

# ============================================================
# Test Classes
# ============================================================

class TestAllocationLimits(unittest.TestCase):
    """Per-position max allocations must be enforced strictly on buys."""

    @MARKET_OPEN
    def test_max_allocation_breach(self, _):
        """
        NVDA is currently at ~23.2%. Max = 25%.
        Buying $200 more would push it to ~25.44% — must be blocked.
        """
        violations, _ = validator.validate(
            [make_proposal("NVDA", "BUY", 200)], BASE_STATE)
        self.assertTrue(
            any("NVDA" in v and "exceed" in v.lower() for v in violations),
            "NVDA buy breaching strict max allocation (25%) must be blocked"
        )

    @MARKET_OPEN
    def test_buy_within_max_allowed(self, _):
        """
        MU is at ~9.13%. Max = 12%.
        Buying $80 keeps it well under 12% — should pass.
        """
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 80)], BASE_STATE)
        self.assertFalse(
            any("MU" in v and "exceed" in v.lower() for v in violations),
            "MU buy within max allocation must not trigger violation"
        )

    @MARKET_OPEN
    def test_multi_trade_cumulative_projection(self, _):
        """
        Two separate $150 buys on MU.
        After first buy: ~10.8% (still under 12%)
        After second buy: ~12.5% (exceeds 12% max)
        The validator must catch the cumulative breach.
        """
        violations, _ = validator.validate([
            make_proposal("MU", "BUY", 150),
            make_proposal("MU", "BUY", 150),
        ], BASE_STATE)
        self.assertTrue(
            any("MU" in v and "exceed" in v.lower() for v in violations),
            "Cumulative multi-trade projection must catch combined allocation breach"
        )

    @MARKET_OPEN
    def test_buy_exactly_at_max(self, _):
        """
        Edge case: buying up to exactly the max allocation should be allowed.
        """
        violations, _ = validator.validate(
            [make_proposal("MU", "BUY", 250)], BASE_STATE)
        self.assertFalse(
            any("MU" in v and "exceed" in v.lower() for v in violations),
            "Buying up to exactly max allocation should be allowed"
        )


class TestSTCGWarnings(unittest.TestCase):
    """Short-term capital gains warnings should trigger correctly on sells."""

    def setUp(self):
        self.state_with_lots = BASE_STATE.copy()
        self.state_with_lots["tax_lots"] = [
            {"symbol": "NVDA", "quantity": 5, "cost_basis": 180.0, "acquired": "2025-08-15", "term": "short"},
            {"symbol": "NVDA", "quantity": 5, "cost_basis": 195.0, "acquired": "2026-01-10", "term": "short"},
        ]
        self.state_with_lots["positions"]["NVDA"]["price"] = 200.0

    @MARKET_OPEN
    def test_stcg_warning_triggered(self, _):
        """Selling enough to generate >$500 STCG should produce a warning."""
        violations, warnings = validator.validate(
            [make_proposal("NVDA", "SELL", 1200)], self.state_with_lots)
        self.assertTrue(
            any("short-term capital gains" in w.lower() for w in warnings),
            "Expected STCG warning when selling generates >$500 gain"
        )

    @MARKET_OPEN
    def test_stcg_warning_not_triggered(self, _):
        """Small sells that generate <$500 STCG should not warn."""
        violations, warnings = validator.validate(
            [make_proposal("NVDA", "SELL", 300)], self.state_with_lots)
        self.assertFalse(
            any("short-term capital gains" in w.lower() for w in warnings),
            "Small STCG should not trigger warning"
        )


if __name__ == "__main__":
    unittest.main()