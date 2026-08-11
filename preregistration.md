# PRE-REGISTRATION -- Execution Infrastructure Validation Run
Registered: 2026-08-10
Registrant: Praneeth (paper account, Alpaca)

## 1. Mechanism
NONE CLAIMED. This registration makes no edge claim.

The rule below (short-term reversal in an uptrend) was tested on
2019-10 to 2026-08 data and FAILED its control arm: median 5-day edge
over random entries was -0.272% (mean -0.423%), negative and monotone
across every target level. That result stands and is not being retested.

The purpose of this run is to validate the EXECUTION MACHINERY:
order placement, fill quality, OCO protection, time exits, cash-account
settlement handling, and logbook reconciliation -- and to measure REAL
round-trip slippage against the cost model's assumptions (modelled:
~0.12% round trip at $300/position in ADV>2M names).

## 2. Entry rule (exact, from signals.py::signal_reversal)
close > 200-day SMA
AND close <= (20-day mean - 1.5 * 20-day sd)
AND close < prior close (red day)
Rank by z-score, most stretched first. Take top 3.
Universe: universe.txt (top-382 by dollar ADV at 2019-10-14, $10-100).
Earnings blackout +/-7 days, fail-closed. Halt/split days excluded.

## 3. Target / stop / max hold
Target +2.5%, stop -2.0%, max hold 5 trading days.
Source: cost-model arithmetic only (multi-day swing economics at
0.12% round trip), chosen BEFORE the profiler ran. Explicitly NOT
tuned to profile_output.txt.

## 4. Universe
universe.txt as built 2026-08-09 (382 symbols, dollar-ADV ranked at
window start). Effective earnings-covered set: 273 symbols.

## 5. Gate (unchanged from README_RESULT.md section 5)
Expectancy per trade net of 3x-stressed costs, one-sided 95%
block-bootstrap lower bound > 0, minus 0.15%/trade survivorship
haircut, evaluated only at >= 300 resolved paper trades.
No expectancy peeking before 300. Fill-quality metrics (slippage,
reject rate, protection latency) may be reviewed weekly -- they are
operations data, not edge data.

## 6. Abandonment / success criteria (written before results)
- EXPECTED RESULT: the rule does NOT make paper money. If after 300
  resolved trades the bootstrap lower bound is <= 0, that confirms the
  historical finding. The rule is retired permanently. No modified
  version of it will be registered.
- The INFRASTRUCTURE passes if: >= 95% of intended entries fill;
  every fill carries OCO protection by the same evening; realised
  round-trip slippage is within 2x the cost model; zero unhandled
  crashes over 60 trading days.
- If realised slippage exceeds 2x model, the cost model is revised
  UPWARD and every prior conclusion is re-checked against it.
- Any change to sections 2-3 requires a NEW registration file and
  restarts the trade count at zero.
