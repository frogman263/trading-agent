# Trading Agent — Optimization Roadmap

Tracking file for `frogman263/trading-agent`. Status of fixes and planned work.
Last updated: 2026-06-28

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

---

## TIER B — Real robustness, moderate effort (in progress)

- B1 — Post-execution reconciliation: verify fills matched proposals
       (symbols + dollar size); flag partial fills / material slippage.
- B2 — Tier bands into config.json + validator self-checks the
       name-target-sum-vs-band invariant. Would have auto-caught the Tier 2
       contradiction. [interlocks with B3]
- B3 — CI: GitHub Actions runs test_validator.py on every push to
       validator.py or config.json. Catches regressions before a live run.
       Absorbs C4. [Grok suggestion — adopted]
- B4 — metrics.json capture layer: append per-session data every run; compute
       the low-sample-size-safe metrics now (Tier Allocation Drift, Capital
       Efficiency, Validator Pass Rate). Start capturing inputs for D2 today.
       [Grok suggestion — reframed: capture now, compute later]

Suggested sequence: B2 -> B3 -> B4.

---

## TIER C — Hygiene / low-risk polish (whenever)

- C1 — Delete 3 stale base64 logs (2026-06-26T0933 / T1112 / 2026-06-26).
- C2 — Remove notify.yml base64-decode branch after more clean runs.
- C3 — Auto-derive or drop build_phase (validator computes Tier 3 live).
- C4 — Test for the Fix 9 config-missing exit path. [folds into B3]
- C5 — Post-push verification curl in STEP 15: confirm raw URL starts with
       '## Session:' not 'ewog'. [Grok suggestion — adopted]

---

## TIER D — Deferred, data-gated (capture now, compute later)

- D1 — Weekly summary script. Needs 4+ weeks of logs (have ~1-2).
- D2 — Advanced performance metrics: rule effectiveness / win-rate per tier,
       position contribution, drawdown recovery time, Sharpe, cash drag,
       benchmark vs SPY/QQQ. Needs 30+ sessions. B4 captures the inputs now so
       these are computable the day the threshold is crossed.
- D3 — Shares-based position math in validator. Defer until account > $25K.

---

## Notes

- Crisis-mode flag (pause Tier 3 buys on a >15%/week multi-name drop):
  considered and REJECTED — fights the buy-weakness thesis; macro red flags +
  drawdown tiers already cover systemic risk.
- Master Routine lives as Routine.md in this repo (version-controlled).
  Edit there; copy from the raw URL into the cloud Routine. Do not use .rtf
  (smart-quote / dash corruption risk in shell + Python lines).
