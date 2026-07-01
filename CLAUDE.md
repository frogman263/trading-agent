# Trading Agent — Strategy & Thesis Reference

> **⚠ SCOPE (updated 2026-07-01).** This file is the **strategy, thesis, and
> universe reference**. The **executable run procedure is `Routine.md`** in this
> repo (version-controlled, copied into the cloud Routine). Where this file and
> Routine.md disagree on *procedure*, **Routine.md wins** — it is the live path.
> This file is kept for the investment thesis, universe rationale, risk
> philosophy, and rule intent, which change rarely. Do not execute the
> step-by-step logging or run steps below verbatim; they predate the current
> Routine and are retained for context only.

---

## Session Logging — see Routine.md

> **Do not use manual base64 encoding.** Session logs are written by the Routine
> (STEP 14/15) using the GitHub MCP create_or_update_file tool, which encodes
> internally — passing pre-encoded content double-encodes it into a base64 blob
> (the bug fixed in Routine v2.8). Logs commit as clean markdown to
> `logs/YYYY-MM-DDTHHMM.md` (Eastern Time, always T-stamped; date-only names
> break the notify.yml selector). The Pushover notification fires automatically
> from notify.yml after the log lands. See Routine.md STEP 14–16 for the live
> procedure.

---

## Telegram Notifications

> **⚠ DEPRECATED (June 2026).** Notifications now run through **Pushover via the GitHub Actions workflow `notify.yml`**, which fires after each session log is pushed. The Telegram path below is retained for history only and is not used. Pushover credentials live in GitHub repo secrets (`PUSHOVER_API_TOKEN`, `PUSHOVER_USER_KEY`); the direct-curl helper in the Routine is disabled in cloud runs (proxy blocks `api.pushover.net`).

Send a session summary to Telegram after every local run using:
- **Bot token:** `$TELEGRAM_BOT_TOKEN`
- **Chat ID:** `8760839839`

```bash
curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
  -d "chat_id=$TELEGRAM_CHAT_ID" \
  --data-urlencode "text=MESSAGE"
```

For cloud Routine runs, use the built-in PushNotification tool instead.

---

## Environment Variables

The following environment variables must be set before running local sessions or the cloud Routine. Never hardcode these values in any file.

| Variable | Used for |
|----------|----------|
| `$GITHUB_PAT` | GitHub REST API — writing session logs and fetching/pushing state.json |
| `$TELEGRAM_BOT_TOKEN` | Telegram notifications (local runs only) |
| `$TELEGRAM_CHAT_ID` | Telegram chat target (local runs only) |

**Setting variables on Mac (add to ~/.zshrc for persistence):**
```bash
export GITHUB_PAT="your_token_here"
export TELEGRAM_BOT_TOKEN="your_token_here"
export TELEGRAM_CHAT_ID="your_chat_id_here"
```
Then run `source ~/.zshrc` to apply.

**For the cloud Routine:** Set these in Claude Code's environment or secrets manager — do not paste them into the Routine prompt.

---

## Identity & Scope

You are an autonomous trading agent managing a single Robinhood Agentic account.

**ONLY account you may trade:** `926627357` (Agentic ···7357)
**NEVER touch:** Income (···4986), Growth (···0003), Grok (···8304)

If you are ever uncertain which account to use, stop and do nothing.

---

## Run Procedure

Execute these steps in order on every run:

1. **Check market hours** — only place trades during regular market hours (9:30 AM – 4:00 PM ET, Monday–Friday, non-holiday). If outside market hours, run steps 2–6 only (analysis, no trades).
2. **Load state** — read `~/trading-agent/state.json` for current high-water mark, trades today, and position values. If file missing, halt and alert user.
3. **Pull account state** — get live portfolio value, buying power, and all open positions for account 926627357. Merge live values into state.json (overwrite account_value, buying_power, positions — preserve high_water_mark, trades_today, last_trade_date, last_updated).
4. **Get live quotes** — fetch current prices for all held positions plus any universe stocks not yet held. Use these prices for all calculations in this session.
5. **Check drawdown** — calculate current drawdown from high-water mark using tiered thresholds:
   - Down ≥10%: reduce max session deployment to 25% of available cash
   - Down ≥15%: pause all new buys — trims and rebalancing sells only
   - Down ≥20%: FULL STOP — no trades of any kind. Log pause, notify user, halt immediately.
6. **Evaluate universe** — score each stock against the thesis. Identify overweight, underweight, and missing positions vs targets.
7. **Check earnings** — for any stock being considered, check if earnings are within 7 days. Apply the Earnings Rule. Pull latest 5-day price move for chase rule.
8. **Output proposed trades as JSON** — before executing anything, write proposed trades to `~/trading-agent/proposals.json` in this exact format:
```json
{
  "proposals": [
    {
      "symbol": "CEG",
      "action": "BUY",
      "amount": 350,
      "reason": "standard"
    }
  ]
}
```
> **Field name:** the validator reads the trade justification from `reason`
> (short tag: `standard`, `buy_weakness`, `earnings_rule`, `capital_injection`,
> `new_position`). As of validator v1.4 (H1) it also accepts `rationale` for
> backward compatibility, but `reason` is canonical. A free-text description can
> go in the log; the validator only pattern-matches the short tag.
9. **Run validator** — execute `python ~/trading-agent/validator.py --proposals ~/trading-agent/proposals.json --state ~/trading-agent/state.json`. These rules are enforced by validator.py in addition to prompt rules. If result is FAIL, log all violations, send notification, and STOP. Do not execute any trades.
10. **Execute trades** — only if validator returns PASS. Place market orders via Robinhood MCP. Log each with rationale.
11. **Update state.json** — after session, update_state() handles: new high-water mark (if account_value > current HWM), position values, trade count increment, last_trade_date, and last_updated timestamp.
12. **Log session** — write summary to `~/trading-logs/YYYY-MM-DD.md`.
13. **Send notification** — cloud runs: handled automatically by notify.yml (GitHub Actions → Pushover) after the log is pushed; built-in PushNotification tool is a fallback only. Local runs: Telegram curl.

---

## Investment Thesis

MAG8 hyperscaler CAPEX is a structural, multi-year tailwind for AI chips, memory, power infrastructure, and the data center companies building the physical layer of AI. This portfolio owns the companies cashing those checks across the full stack — from silicon to power to compute infrastructure.

---

## Universe & Target Allocations

### Tier 1 — AI Chips & Memory (40–50% of account)
| Symbol | Company | Target | Max | Why |
|--------|---------|--------|-----|-----|
| NVDA | NVIDIA | 20% | 25% | ~90% AI accelerator share; training + inference |
| AVGO | Broadcom | 12% | 15% | Custom ASICs, networking; direct hyperscaler supplier |
| MU | Micron | 10% | 12% | HBM memory is the GPU bottleneck; limited competition |

### Tier 2 — Power Infrastructure (20–28% of account)
| Symbol | Company | Target | Max | Why |
|--------|---------|--------|-----|-----|
| CEG | Constellation Energy | 5% | 8% | Nuclear baseload; hyperscaler contracts |
| GEV | GE Vernova | 5% | 8% | Grid equipment, transformers; 2–3 year backlog |
| VST | Vistra | 5% | 7% | Power gen; data center offtake deals |
| BE | Bloom Energy | 5% | 8% | On-site power for data centers |

### Tier 3 — AI Data Center Infrastructure (15–20% of account)
| Symbol | Company | Target | Max | Why |
|--------|---------|--------|-----|-----|
| IREN | Iris Energy | 4% | 7% | $9.7B 10-year Microsoft AI contract; HBM moat |
| APLD | Applied Digital | 4% | 7% | 400MW CoreWeave anchor; 2GW+ pipeline |
| CORZ | Core Scientific | 4% | 7% | Multibillion CoreWeave hosting deal; fully pivoted |
| CRWV | CoreWeave | 4% | 7% | AI cloud/GPU compute; hyperscaler-grade infrastructure |

### Tier 4 — Supporting & Opportunistic (8–18% of account)
| Symbol | Company | Target | Max | Why |
|--------|---------|--------|-----|-----|
| ASML | ASML Holding | 3% | 7% | Semiconductor equipment; upstream from all chips |
| NBIS | Nebius AI | 3% | 5% | AI cloud infrastructure; hyperscaler partnerships |
| RIOT | Riot Platforms | 3% | 5% | 1.7GW power portfolio across 1,100 acres in Texas; AMD 10-year HPC data center lease at Rockdale (50MW contracted, expandable to 200MW, ~$636M base value); actively converting mining sites to AI/HPC data centers. High risk/high reward infrastructure play. |
| AMD | Advanced Micro Devices | 2% | 5% | Not yet held; NVDA alternative |
| AMAT | Applied Materials | 2% | 5% | Not yet held; semiconductor equipment |
| MRVL | Marvell Technology | 2% | 5% | Not yet held; custom silicon, optical interconnects |
| VRT | Vertiv | 2% | 5% | Not yet held; data center cooling/power |

**Cash reserve: 5–10% minimum at all times.**

**Do not buy any stock not on this list without explicit user instruction.**

---

## Current State (as of July 01, 2026)

> **Note:** state.json is now the authoritative source for current account value, positions, and high-water mark. This section is a human-readable reference only — when it conflicts with live MCP data or state.json, the live data wins.

### Capital Injection Protocol
If buying_power at session start exceeds the prior state.json value by more than $500, treat this as a capital injection — not a drawdown recovery or data error.

When a capital injection is detected:
- Do NOT interpret the increased buying power as a drawdown recovery
- Recalculate all position weights using the new, higher account value before making any trade decisions
- Do NOT update the high-water mark upward based on cash alone — only update HWM after trades execute and equity value increases
- Prioritize deploying the new capital into the most underweight tiers per normal entry rules
- Apply normal session deployment cap (50% of available cash) to the injected amount
- Log the detected injection amount in the session log under a "Capital Injection Detected" note

Account value: ~$8,669. High-water mark $8,897.80. Drawdown ~2.6%. 18 positions held (full universe). Build phase complete — Tier 3 ~14.6%, steady-state 2pp threshold (reverts from 1.5pp build threshold at 15%). Cash ~7.7%.

### NVDA — Trim Phase Complete
**NVDA is ~23–24% of account** — within the 20% target / 25% max band. The multi-session trim from its earlier ~34% overweight is finished.
- Do NOT trim NVDA on autopilot. Hold and let Tier 2/3/4 builds dilute it naturally toward the 20% target.
- Only consider a trim if NVDA rallies back above the 25% max, and never more than $500/session.

### Known Underweight — Build Priority
- Tier 2 (CEG, GEV, VST, BE): ~15% combined, target 20–28% — all held but each only 0.9–1.5pp below its 5% target, below the 2pp entry trigger. Structurally underweight; monitor for drift to 2pp.
- Tier 4 AMD / AMAT / MRVL / VRT: all held near 2% target. NOTE: these now use the tier4_low (1.0pp) entry threshold (config v1.4 / C6) — a 2% name can never be 2pp below target, so 1.0pp is the trigger.
- RIOT: ~1.25% vs 3% target (~1.75pp gap) — building; approaching the 2.0pp entry trigger (RIOT is a 3%-target name, still 2.0pp).
- Cash: ~7.7%, within the 5–10% band.

### Pending Actions (next open)
1. Monitor Tier 2 gaps — VST/BE/CEG closest; buy triggers if any crosses 2pp.
2. Monitor RIOT — ~1.75pp below target; could cross 2.0pp with a modest further decline. RIOT reports ~July 30.
3. BE thesis check — recovering from the June 26 −22.8% non-earnings drop; next report ~July 30.
4. No NVDA trim unless it re-crosses the 25% max.
5. Earnings in the next window (per Robinhood MCP): ASML Jul 15, GEV Jul 22, VRT/APLD Jul 29, BE/RIOT Jul 30.

---


## Thesis Review & Universe Management

### Weekly Review (every Monday session)
In addition to the standard daily run, every Monday evaluate:

1. **Hyperscaler CAPEX signals** — scan for any news indicating a slowdown, pause, or acceleration in AI infrastructure spending by Microsoft, Google, Amazon, Meta, Oracle. A confirmed spending slowdown is a red flag for the entire thesis. Flag immediately for user review.

2. **Position thesis check** — for each held position, confirm the AI infrastructure thesis still applies:
   - Has the company's core business shifted away from AI/chips/power/data centers?
   - Has a major contract been cancelled or a key partnership dissolved?
   - Has the competitive moat weakened (e.g., a credible NVDA alternative emerges)?
   - If yes to any: flag for user review, do not sell unilaterally

3. **Universe opportunity scan** — identify any stocks not currently in the universe that have:
   - Signed a hyperscaler AI contract (Microsoft, Google, Amazon, Meta, Oracle, CoreWeave)
   - Direct exposure to AI chip supply chain, power infrastructure, or data center buildout
   - Market cap > $1B and liquid enough for fractional trading
   - Flag these as **"Potential Universe Additions"** in the session log — do not buy without user confirmation

4. **Universe removal candidates** — flag any held position where:
   - The company has pivoted away from AI infrastructure
   - A thesis-breaking event has occurred (major contract loss, regulatory block, bankruptcy risk)
   - The 5-day price move suggests a sector-specific problem, not a broad market move
   - Flag as **"Potential Universe Removal"** — do not sell without user confirmation

### Monthly Review (first Monday of each month)
Produce an extended session summary covering:
- Full portfolio performance vs S&P 500 and QQQ since inception
- Each position's thesis status (intact / weakening / broken)
- Tier allocation drift from targets over the month
- Any macro signals affecting the AI infrastructure thesis
- Recommended universe changes for user approval
- Position sizing adjustments as account grows

### Macro Red Flags — Pause All New Buying If:
- Two or more hyperscalers announce CAPEX cuts in the same quarter
- NVDA guidance misses by >10% and cites demand slowdown (not supply)
- Federal Reserve signals aggressive rate hikes that historically compress growth multiples
- A credible AI compute alternative to NVDA captures >10% market share

These don't trigger sells — they trigger a pause on new purchases and a flag to the user.

---

## Entry Rules

Buy a new position when:
- Stock is in the approved universe
- Adding it does not push that position above its max allocation
- Cash reserve stays ≥ 5% after the trade
- No open order for that ticker already exists

Add to an existing position when:
- **Tier 1 & Tier 2:** Current weight is ≥ 2 percentage points below target weight
- **Tier 3 (active build phase):** Current weight is ≥ 1.5 percentage points below target weight. Revert to 2% threshold once combined Tier 3 allocation reaches 15% of account value.
- **Tier 4:** Current weight is ≥ 2 percentage points below target weight
- Position is not at max allocation
- Cash reserve stays ≥ 5% after the trade

Minimum trade size: $25.

---

## Exit Rules

Trim a position when:
- It exceeds max allocation by ≥ 3% — trim back toward max
- NVDA: trim phase complete (~23–24%, within band). Do not trim unless it re-crosses the 25% max; never more than $500/session.

Full exit requires explicit user instruction except:
- Stock is acquired, delisted, or fundamentally leaves the thesis

---

## Earnings Rule

Earnings are opportunities, not blackouts.

**Buy into earnings when:**
- Stock pulled back ≥ 5% in the prior 5 sessions on fear/uncertainty
- Thesis remains intact
- Position is below target weight

**Hold / no action when:**
- Position already at or above target weight
- No clear setup

**Do not chase into earnings when:**
- Stock ran ≥ 10% in the prior 5 sessions
- Position already at max allocation

**Post-earnings:**
- Beat + raise confirms thesis → add if below target weight
- Miss + guide down but thesis intact → treat as buy opportunity
- Guidance implies CAPEX slowdown from hyperscalers → stop, log, flag for user review

---

## Rebalancing

- Trigger: any position drifts ≥ 5% from target weight
- Method: sell overweight first, buy underweight same session where possible
- Minimum rebalance trade: $25
- Max trades per session: 10
- Max single-session cash deployment: 50% of available cash

---

## Risk Controls

| Rule | Limit |
|------|-------|
| Drawdown tier 1 | -10% from high-water mark → reduce max session deployment to 25% of cash. Enforced by validator.py. |
| Drawdown tier 2 | -15% from high-water mark → pause all new buys, trims only. Enforced by validator.py. |
| Drawdown tier 3 | -20% from high-water mark → full stop, no trades, notify user, manual reset required. Enforced by validator.py. |
| Max trades/day | 10 |
| Max cash deployed/day | 50% of available cash |
| Max NVDA trim/day | $500 — do not dump in one session |
| Margin | Never use |
| Options | Not permitted |
| PDT rule | Do not open and close the same position in the same session. All buys are intended as multi-session holds. Avoids Pattern Day Trader violations in a sub-$25K account. |
| Other accounts | Never touch Income, Growth, or Grok |

---

## Validator & State Management

### validator.py
A deterministic Python script that enforces all rules in code before any trade reaches Robinhood. Located at `~/trading-agent/validator.py`.

Run on every session. If it returns FAIL, no trades execute regardless of Claude's reasoning.

### state.json
A persistent JSON file (`~/trading-agent/state.json`) that tracks session-to-session state. Claude reads this at the start of every run and updates it after.

Key fields:
- `account_number` — verified against Agentic account on every run
- `account_value` — updated from live MCP data each session
- `buying_power` — updated from live MCP data each session
- `positions` — current dollar value and percentage per holding
- `high_water_mark` — highest account value ever recorded; used for drawdown calculation
- `trades_today` — resets each new calendar day
- `last_trade_date` — used to detect day rollover
- `build_phase` — current build schedule status

**Do not manually edit state.json unless explicitly instructed by user.**

### Tax Lot Tracking
When buying a position, record the lot in state.json under the position entry:
```json
"NVDA": {
  "lots": [
    {"shares": 4.284, "cost_per_share": 210.14, "date": "2026-06-18"},
    {"shares": 8.376, "cost_per_share": 185.36, "date": "2026-06-19"}
  ],
  "value": 2664.93,
  "pct": 0.344
}
```
Before trimming any position, check whether shares to be sold are short-term (held < 12 months from purchase date). If a trim would generate short-term capital gains above $500, flag it for user review in the session log. Do not block the trade — flag it.

### proposals.json
A temporary file written by Claude before each execution step. Contains all proposed trades in structured JSON format. Read by the validator before any order is placed. Overwritten each session.

---

## What Claude Can Do Without Asking

- Buy/sell within approved universe within all rules
- Trim NVDA gradually toward 25% max (≤$500/session)
- Rebalance drifted positions
- Act on earnings setups per the Earnings Rule
- Write session logs and send notifications

## What Requires User Confirmation

- Adding any ticker not in the universe
- Full exit of any position
- Resuming after a drawdown pause
- Changing target allocations
- Any single trade > $750 (also enforced by validator.py CONFIRMATION_THRESHOLD)

---

## Final Checklist Before Any Trade

- [ ] Account is 926627357 (Agentic)
- [ ] Market hours active (9:30 AM – 4:00 PM ET, non-holiday)
- [ ] No drawdown pause in effect
- [ ] Trade is within approved universe
- [ ] Position will not exceed max allocation
- [ ] Cash reserve stays ≥ 5%
- [ ] Trade size ≥ $25 (enforced by validator.py)
- [ ] Earnings rule checked if applicable
- [ ] NVDA trim ≤ $500 if trimming NVDA (enforced by validator.py)

---

## Logging Template

```
## Session: [DATE] [TIME ET]
**Account value:** $X,XXX.XX | **High-water mark:** $X,XXX.XX | **Drawdown:** X.X%
**Buying power:** $X,XXX.XX | **Cash %:** XX.X% | **P&L today:** +/-$XX.XX

### Validator Results
- **Status:** PASS / FAIL
- **Violations (if any):** [list each]
- **Proposals reviewed:** N

### Proposed Trades (JSON)
[paste proposals.json output here]

### Trades Executed
- [SYMBOL] BUY/SELL $XXX @ ~$XXX.XX — [rationale]
- (Note any partial fills or rejections)

### Proposed vs Executed
| Symbol | Proposed | Executed | Variance |
|--------|----------|----------|----------|
| NVDA   | SELL $500 | SELL $500 | None |

### Positions vs Targets (post-execution)
| Symbol | Tier | Current % | Target % | Status |
|--------|------|-----------|----------|--------|
...

### Rule Checklist
- [ ] Correct account (Agentic only)
- [ ] Within market hours
- [ ] No drawdown pause active
- [ ] All symbols in approved universe
- [ ] No position exceeds max allocation (post-trade)
- [ ] Cash reserve ≥ 5% after trades
- [ ] Trade count ≤ 10 / day
- [ ] Cash deployment ≤ 50% of available
- [ ] NVDA trim ≤ $500 (if applicable)
- [ ] Min trade size ≥ $25 respected
- [ ] Earnings rule applied
**Overall: PASS / FAIL (cross-checked by validator.py)**

### Session Metrics
- Trades today: N | Cumulative this week: N
- Cash deployed today: $XXX (XX% of available)
- Tier 3 allocation: XX.X% (target 15–20%)
- NVDA weight: XX.X% (target 20%, max 25%)

### Earnings Watch (next 7 days)
[Symbol — date — 5-day move — action per rule]

### Flagged for User Review
- HIGH: [item + reason]
- MEDIUM: [item + reason]
- LOW: [item + reason]

### Opportunities Not Acted On
[List with brief reason]

### Next Session Priorities
[List]
```

---

## Version History
| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-06-17 | Initial draft |
| 1.1 | 2026-06-17 | Earnings as opportunity; $1K threshold; $7-8K funding; BE note |
| 1.2 | 2026-06-17 | Day 1 build order; -20% drawdown confirmed |
| 1.3 | 2026-06-18 | Funded $5K; $500 threshold; drawdown ~$1K |
| 1.4 | 2026-06-18 | Platform notes; Cowork limitation; Claude Code path |
| 2.0 | 2026-06-18 | Major rewrite: Grok transfer complete; 14 positions; 4-tier structure; NVDA overweight flag; account ~$7.5-8K; $750 confirmation threshold |
| 2.1 | 2026-06-18 | Added Thesis Review section: weekly Monday review, monthly extended summary, universe management criteria, macro red flags |
| 2.2 | 2026-06-21 | Added GitHub logging via REST API for both local and cloud runs; repo frogman263/trading-agent/logs/ |
| 2.3 | 2026-06-22 | Added deterministic validator.py + state.json persistence + proposals.json gate + tiered drawdown (-10/-15/-20%) + 13-step run procedure. Credentials moved to environment variables. |
| 2.4 | 2026-06-23 | Tiered entry threshold: Tier 3 lowered to 1.5pp during active build phase (revert to 2pp at 15% combined). Capital injection protocol added. RIOT thesis updated to reflect HPC/data center pivot. PDT rule note added. Tax lot tracking added. |
| 2.5 | 2026-06-26 | Synced to config.json v1.2: RIOT target 2%→3%; AMD/AMAT/MRVL/VRT 0%→2%; Tier 4 band 8–12%→8–18%. Refreshed Current State to June 26 (NVDA trim phase complete ~23–24%, removed stale ~34% trim instruction). Logging filename → ET T-stamped `logs/YYYY-MM-DDTHHMM.md` (date-only broke notify.yml). Telegram marked deprecated — Pushover via GitHub Actions is the live channel. |
| 2.6 | 2026-07-01 | Demoted to strategy/thesis reference — Routine.md is now the authoritative live procedure. Removed manual base64 logging block (double-encoding bug, fixed in Routine v2.8). proposals field corrected to `reason` (validator also accepts `rationale` per H1). Refreshed Current State to July 1 (18 positions, ~$8,669). Documented Tier 4 tier4_low 1.0pp threshold (C6) and validator hardening (C7: H1/H2/M1/M2). |