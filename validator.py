import json
import logging
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def validate(proposals, state):
    """
    Deterministic validation layer for trading proposals.
    Returns (violations, warnings)
    """
    violations = []
    warnings = []

    # Load config
    try:
        with open("/tmp/config.json") as f:
            config = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config.json: {e}")
        return ["Config load failed"], []

    max_allocs = config.get("max_allocs", {})
    market_holidays = set(config.get("market_holidays_2026", []))
    drawdown_limits = config.get("drawdown", {})

    # Normalize positions
    raw_positions = state.get("positions", {})
    positions = {}
    prices = {}
    for sym, val in raw_positions.items():
        if isinstance(val, dict):
            positions[sym] = val.get("value", 0)
            prices[sym] = val.get("price", 0)
        else:
            positions[sym] = val
            prices[sym] = 0

    account_value = float(state.get("account_value", 0))
    if account_value <= 0:
        violations.append("Invalid account value in state.json")
        return violations, warnings

    high_water_mark = float(state.get("high_water_mark", account_value))
    drawdown = (high_water_mark - account_value) / high_water_mark if high_water_mark > 0 else 0

    # Drawdown checks
    if drawdown >= 0.20:
        violations.append(f"Drawdown {drawdown*100:.1f}% exceeds 20% threshold. Full stop required.")
    elif drawdown >= 0.15:
        warnings.append(f"Drawdown {drawdown*100:.1f}% >= 15%. New buys paused.")
    elif drawdown >= 0.10:
        warnings.append(f"Drawdown {drawdown*100:.1f}% >= 10%. Deployment capped at 25% of buying power.")

    # Market hours check
    now = datetime.now(timezone.utc)
    et_now = now.astimezone(timezone(timedelta(hours=-4)))
    is_weekday = et_now.weekday() < 5
    is_market_hours = 9 <= et_now.hour < 16 and is_weekday

    if not is_market_hours:
        violations.append("Market not open: Pre-market (before 9:30 AM ET)")

    # NVDA trim limit
    nvda_trades_today = state.get("nvda_trades_today", 0)
    if nvda_trades_today >= 500:
        warnings.append("NVDA trim limit of $500 reached for this session.")

    # Process each proposal
    for proposal in proposals:
        sym = proposal.get("symbol")
        action = proposal.get("action", "").upper()
        amount = float(proposal.get("amount", 0))

        if sym not in max_allocs:
            violations.append(f"{sym}: Not in approved universe.")
            continue

        max_pct = max_allocs[sym]
        current_value = positions.get(sym, 0)
        current_pct = current_value / account_value if account_value > 0 else 0

        if action == "BUY":
            new_value = current_value + amount
            new_pct = new_value / account_value

            # Strict max allocation check for buys (no buffer)
            if new_pct > max_pct:
                violations.append(
                    f"{sym}: Post-trade weight {new_pct*100:.1f}% would exceed "
                    f"max allocation {max_pct*100:.1f}%."
                )

        elif action == "SELL":
            # Tax Lot Check: Warn if SELL generates >$500 in Short-Term Capital Gains
            if sym in prices and prices[sym] > 0:
                shares_to_sell = amount / prices[sym]
                tax_lots = state.get("tax_lots", [])

                # Filter and sort lots for this symbol (FIFO)
                sym_lots = [lot for lot in tax_lots if lot.get("symbol") == sym]
                sym_lots.sort(key=lambda x: x.get("acquired", ""))

                stcg = 0.0
                shares_remaining = shares_to_sell

                for lot in sym_lots:
                    if shares_remaining <= 0:
                        break
                    lot_shares = lot.get("quantity", 0)
                    if lot_shares <= 0:
                        continue

                    shares_from_lot = min(shares_remaining, lot_shares)

                    if lot.get("term") == "short":
                        cost_basis = lot.get("cost_basis", 0)
                        gain = (prices[sym] - cost_basis) * shares_from_lot
                        stcg += gain

                    shares_remaining -= shares_from_lot

                if stcg > 500:
                    warnings.append(
                        f"{sym}: SELL of ${amount:,.2f} is projected to generate "
                        f"${stcg:,.2f} in short-term capital gains (exceeds $500 threshold)."
                    )

    return violations, warnings


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--proposals", required=True)
    parser.add_argument("--state", required=True)
    args = parser.parse_args()

    with open(args.proposals) as f:
        proposals = json.load(f).get("proposals", [])

    with open(args.state) as f:
        state = json.load(f)

    violations, warnings = validate(proposals, state)

    print("=======================================================")
    print(f"  Trading Agent Validator — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Account:   {state.get('account_number')}")
    print(f"  Value:     ${state.get('account_value', 0):,.2f}")
    print(f"  Cash:      ${state.get('buying_power', 0):,.2f}")
    print(f"  HWM:       ${state.get('high_water_mark', 0):,.2f}")
    print(f"  Proposals: {len(proposals)} trade(s)")
    print("=======================================================")

    if violations:
        print("\nVIOLATIONS:")
        for v in violations:
            print(f"  ✗  {v}")
        print("\nRESULT: FAIL — DO NOT EXECUTE TRADES")
    else:
        print("\nRESULT: PASS")

    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(f"  !  {w}")