# Trading Agent — Optimization Roadmap

Tracking file for `frogman263/trading-agent`. Status of fixes and planned work.
Last updated: 2026-07-01 (v3)

---

## DONE (live in repo, proven in production)

Fixes 1–9 (audit sprint) + A1–A3 (post-audit), all verified. The first live
v2.6 run on 2026-06-27 confirmed clean JSON/markdown commits through the GitHub
MCP path that previously double-encoded.

- Fix 1  — STEP 11 push raw JSON (no pre-base64)            [prevents Monday HALT]
- Fix 2  — earnings_check.py removed from cloud runs        [-20s, -39 calls/run]
- Fix 3  — STEP 15 drop unnecessary SHA fetch for logs
- Fix 4  — STEP 14/15 single compose (no double markdown)
- Fix 5  — CLAUDE.md Pending Actions refreshed
- Fix 6  — notify.yml cash grep tightened to 'cash %:'
- Fix 7  — state.json cleanup (schema_version 1.2, session_log removed)
- Fix 8a — state.json prior_session_value field seeded
- Fix 8b — Routine wiring: read baseline first, roll forward last  [Routine v2.7]
- Fix 9  — validator.py config fallback exits(1) on missing config
- A1     — VST 4->5%, ASML 4->3% (Tier 2 band floor now reachable) [config v1.3]
- A2     — prior_session_value P&L wiring (STEP 5 + STEP 10 + STEP 14)
- A3     — deterministic 5-day move helper (STEP 7 §2a, close-to-close)

### 2026-07-01 session — log-push root fix + Tier 4 fix + validator hardening

- v2.8 log fix — STEP 15 session-log push now uses the GitHub MCP
  create_or_update_file tool (same pattern as STEP 11 state push) instead of a
  raw curl Contents API call with manual base64. This is the ROOT fix for the
  session-log double-base64 problem — the same fix Fix 1 applied to state.json,
  finally applied to logs. Confirmed: notify.yml parses the resulting clean
  markdown correctly (all 6 fields). This obsoletes the C1/C2/C5 workarounds
  (see Tier C notes below). [Routine v2.8]

- C6 — Tier 4 entry-threshold split. Added tier4_low (1.0pp) for
  AMD/AMAT/MRVL/VRT (2% target); tier4 (2.0pp) unchanged for ASML/NBIS/RIOT
  (3% target). The flat 2.0pp threshold made the four 2%-target names
  structurally UNBUYABLE after their initial entry — a 2% position can never be
  2pp below target without dropping to 0% value. validator.get_entry_threshold()
  now branches on target_pct within Tier 4. Config: entry_thresholds.tier4_low.
  Tests 38 -> 43. [config v1.4, Routine v2.9]

- C7 — Validator hardening (2026-07-01 full-repo audit). One commit, five fixes:
  - H1  validator accepts BOTH 'reason' and 'rationale' proposal fields. The
        docs (CLAUDE.md, Routine) instruct the agent to write 'rationale' but the
        validator only read 'reason' — so earnings_rule / capital_injection /
        new_position OVERRIDES were silently failing (trade still executed, but
        every override buy threw a spurious threshold warning). Verified fix
        against the BE-into-July-30 scenario.
  - H2  proposal amounts coerced to float up front, before the deployment-sum
        math. A non-numeric amount previously CRASHED validate() with a
        TypeError at the total_buy_amount summation. Now garbage/None produce a
        clean 'non-numeric amount' violation; numeric strings are accepted.
  - M1  max-allocation buy buffer is now config-driven
        (risk_controls.max_alloc_buffer_pp, default 3.0pp — behavior preserved).
        Was a hardcoded 0.03 that let a name be bought to 3pp above its hard max.
  - M2  drawdown reduce-deployment cap now reads config (drawdown.reduce_deploy_cap)
        instead of a hardcoded 0.25. Values matched, so no live behavior change —
        but editing config now actually takes effect.
  - L2  validator.py version strings (docstring + argparse) synced to 1.4.
  - Tests 43 -> 50 (new TestAuditFixes class). [validator v1.4, config v1.4]
- C7b — Validator enforcement gaps (2026-07-01 second audit). One commit:
        N1  SELL orders validated against held position value (was unchecked —
            agent could propose selling more than it holds).
        N2  PDT rule enforced in code (same-symbol BUY+SELL in one session
            blocked; was prompt-only on a sub-$25K account).
        N3  $750 confirmation reconciled: hard-block by default (no confirmer in
            autonomous 1 AM runs), with a proposal-level "confirmed": true escape
            hatch that downgrades to a warning for supervised large trades.
        N4  Cash-neutral rebalances no longer falsely blocked — sell proceeds
            now credited to both the deployment cap and the cash-reserve floor.
        N6  Drawdown reduce-cap warning text reads DRAWDOWN_REDUCE_CAP instead
            of a hardcoded 25%.
        Tests 50 -> 59. [validator v1.4]
---

## TIER B — Real robustness, moderate effort (in progress)

- B1 — Post-execution reconciliation: verify fills matched proposals
       (symbols + dollar size); flag partial fills / material slippage.
- B2 — Tier bands into config.json + validator self-checks the
       name-target-sum-vs-band invariant. Would have auto-caught the Tier 2
       contradiction. [interlocks with B3]
- B3 — CI: GitHub Actions runs test_validator.py on every push to
       validator.py or config.json. Catches regressions before a live run.
       Absorbs C4. [Grok suggestion — adopted] [UP NEXT]
- B4 — metrics.json capture layer: append per-session data every run; compute
       the low-sample-size-safe metrics now (Tier Allocation Drift, Capital
       Efficiency, Validator Pass Rate). Start capturing inputs for D2 today.
       [Grok suggestion — reframed: capture now, compute later]
- B5 — Earnings calendar integration (STEP 7): call get_earnings_results via
       Robinhood MCP at session open to auto-flag any universe name reporting
       within 7 days. Replaces disabled earnings_check.py (Yahoo 403). Surfaces
       report date, timing (AM/PM), EPS estimate, and verified/tentative status
       in session log before buy/sell logic runs. Wires earnings awareness into
       buy-weakness rule. 18 MCP calls/session, soft-fail on errors.
       Confirmed tools live: get_earnings_calendar + get_earnings_results
       as of 2026-06-30. On completion, DELETE earnings_check.py (see L4).
       [UP NEXT after B3]

Suggested sequence: B2 -> B3 -> B4 -> B5.

---

## TIER C — Hygiene / low-risk polish (whenever)

Note: the v2.8 log-push root fix (see DONE above) changed the status of C1/C2/C5.
Logs now commit as clean markdown at the source, so the downstream base64
workarounds are belt-and-suspenders rather than required. Safe to remove after
2–3 more confirmed-clean runs.

- C1 — Delete stale base64 logs from before the v2.8 fix (pre-2026-07-01
       T-stamped logs that committed as base64 blobs). Cosmetic repo cleanup.
- C2 — Remove the notify.yml base64-decode branch. Now SAFE post-v2.8 (logs
       arrive as markdown), but keep for 2–3 runs as a fallback, then delete.
- C3 — Auto-derive or drop build_phase (validator computes Tier 3 live; the
       state.json build_phase string is redundant with the live computation).
- C4 — Test for the Fix 9 config-missing exit path. [folds into B3]
- C5 — Post-push verification in STEP 15: confirm the committed raw URL starts
       with '## Session:' not 'ewog'. Less critical post-v2.8 but still a cheap
       guard. [Grok suggestion — adopted]
- C8 — Standardize state.json position schema between runs. Agent occasionally
       rebuilds the positions dict with slightly different field order/names
       (e.g. 'shares' vs 'quantity', single-line vs expanded dicts). Add an
       explicit schema note to STEP 5 instructing the agent to preserve the exact
       field structure from the fetched state.json when writing positions back.
       Flagged from 2026-06-28 Saturday run. [renumbered from C6 — that number now
       refers to the Tier 4 threshold fix shipped 2026-07-01]
       RECURRED 2026-07-01: test run added a new 'last_price' field to every
       position that wasn't in the prior schema. Harmless (validator ignores
       unknown keys), but confirms this is a live, repeating pattern, not a
       one-off. Consider having STEP 5 enumerate the exact allowed per-position
       keys explicitly (value, pct, shares, avg_cost, lots) rather than leaving
       it to the agent's judgment each run.
- C9 — Periodic tax-lot reconciliation. From the 2026-07-01 audit: AVGO
       (2.765885 sh held vs 2.762300 in tax_lots) and VST (1.829312 vs 1.826818)
       have sub-share drift between positions.shares and sum(tax_lots.quantity),
       almost certainly un-logged DRIP. Harmless in dollar terms but erodes the
       short-term-gains >$500 flag accuracy over time. Reconcile on next Reno
       return / quarterly. [audit M3]
- C10 — Market holidays are year-locked (MARKET_HOLIDAYS_2026 / config key
        market_holidays_2026). On 2027-01-01 the set is stale — is_market_open()
        would not recognize any 2027 holiday and could think the market is open
        on New Year's / MLK Day 2027. Rename to market_holidays and add 2027
        dates before year-end; the validator gate should not rely on Robinhood
        rejecting holiday orders. [audit N7 — annual maintenance]
- C11 — Document the N3 "confirmed": true proposal field in Routine.md and
        CLAUDE.md where the >$750 rule is described, so the escape hatch is
        discoverable. Also note that full position exits remain documented-but-
        unenforced in the validator (same class as N3). [audit follow-up]
- C12 — Test-run market-hours self-check used a hand-rolled UTC-4 offset after
        `import pytz` failed (not installed, correctly — pip blocked in cloud).
        Got the right answer only because the test ran during EDT season; the
        same hardcoded-offset pattern would silently misjudge market hours
        during EST season (Nov-Mar, UTC-5). Low risk today because validator.py's
        actual is_market_open() (proper zoneinfo, stdlib, no pip needed) is the
        real gate and is unaffected — this was just the agent's own supplementary
        pre-check. Fix: add a one-line note to Routine.md STEP 2 telling the
        agent to use Python's stdlib zoneinfo (already used by validator.py),
        never a manual UTC offset, for any ad hoc time check. [test run 2026-07-01]
- C13 — Pre/post-market runs value positions from the officially settled prior
        close, but write account_value from Robinhood MCP's live total_value
        (which already includes pre/post-market marks) — the two bases don't
        reconcile. Confirmed on the 2026-07-01 test run: sum(positions.value) +
        cash = $8,712.77 vs account_value written = $8,681.62, a $31.15 gap,
        94% of it traced to BE's single-name pre-market pop (close $302.70 vs
        premarket $329.77). Harmless today — validator only reads
        positions[sym]["value"], never the stored pct, and STEP 5 overwrites
        everything fresh from live MCP data on the next real run regardless.
        But it leaves state.json internally inconsistent for anyone reviewing a
        pre/post-market snapshot. Fix: STEP 4/5 should specify using the live
        quote (last_trade_price or last_non_reg_trade_price) for position math
        consistently, matching the same basis Robinhood's own total_value
        already uses — not the settled close. [test run 2026-07-01]        

---

## TIER D — Deferred, data-gated (capture now, compute later)

- D1 — Weekly summary script. Needs 4+ weeks of logs (have ~1-2).
- D2 — Advanced performance metrics: rule effectiveness / win-rate per tier,
       position contribution, drawdown recovery time, Sharpe, cash drag,
       benchmark vs SPY/QQQ. Needs 30+ sessions. B4 captures the inputs now so
       these are computable the day the threshold is crossed.
- D3 — Shares-based position math in validator. Defer until account > $25K.

---

## DOC DEBT (from 2026-07-01 audit)

- L1 — CLAUDE.md is a full generation behind Routine.md: 13-step procedure
       (Routine is 16), manual base64 log encoding via raw curl (the exact
       double-encoding pattern fixed in v2.8), June-26 14-position / ~$8,500
       state, and the 'rationale' field. Its own header says "keep in sync."
       Resolution: demote CLAUDE.md to the strategy/thesis reference and make
       Routine.md the single authoritative live procedure. [being addressed]
- L3 — state.json last_trade_date vs last_updated naming is load-bearing: the
       day-rollover trade-count reset keys off last_trade_date, so the two fields
       legitimately differ on no-trade days. Document the distinction; do NOT
       rename casually. [audit L3]
- L4 — Delete earnings_check.py when B5 lands. Fully disabled (Yahoo 403),
       correctly documented everywhere, but a loaded gun if re-enabled. [audit L4]

---

## Notes

- Crisis-mode flag (pause Tier 3 buys on a >15%/week multi-name drop):
  considered and REJECTED — fights the buy-weakness thesis; macro red flags +
  drawdown tiers already cover systemic risk.
- Master Routine lives as Routine.md in this repo (version-controlled).
  Edit there; copy from the raw URL into the cloud Routine. Do not use .rtf
  (smart-quote / dash corruption risk in shell + Python lines).
- Numbering note: Tier C was renumbered on 2026-07-01. The old C6 (state.json
  position schema) is now C8, because C6 shipped as the Tier 4 threshold fix.
  C7 = validator hardening. C9 = tax-lot reconciliation (new from audit).
