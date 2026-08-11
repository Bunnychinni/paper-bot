# Stage 1 — Short-Term Reversal Research

Laptop version. Python 3.11+, macOS / Linux / Windows.

**Nothing in this project places an order.** There is no live path and no paper-order path. `TradingClient` appears once, read-only, for `get_all_assets`. Verify yourself:

```bash
grep -rn "submit_order\|place_order\|OrderRequest\|MarketOrder\|LimitOrder" *.py
```

Should return nothing.

---

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Alpaca **paper** account at alpaca.markets — free, no funding. Switch the dashboard to Paper Trading, generate keys. **Paper keys start `PK`. Live keys start `AK`.** `run_all.sh` refuses to proceed on `AK`.

```bash
export APCA_API_KEY_ID='PK...'
export APCA_API_SECRET_KEY='...'
export SEC_UA='swing-research you@youremail.com'   # SEC 403s generic agents
```

Windows PowerShell:
```powershell
$env:APCA_API_KEY_ID='PK...'
$env:APCA_API_SECRET_KEY='...'
$env:SEC_UA='swing-research you@youremail.com'
```

Put them in your shell profile, or a `.env` you never commit. `.gitignore` already excludes `.env`, `*.key`, and every generated data file. **Never paste keys into a chat window.**

---

## Run

```bash
./run_all.sh
```

Five steps, ~15 min, stops on any failure and pauses at the EDGAR verification for a y/n. Override defaults with `YEARS=6 N=400 ./run_all.sh`.

Or step by step:

```bash
python build_universe_file.py --max-symbols 400 --years 6      # 3-6 min
python build_earnings.py --symbols AAPL,MSFT,JPM --years 4 --out _verify.csv   # STOP
python build_earnings.py --from-universe universe.txt --years 7 # 2-4 min
python mfe_profile.py --years 6 | tee profile_output.txt        # 4-8 min
python control_arm.py --years 6 | tee control_output.txt        # 1 min
```

Stage 1 is deliberately **not** in `run_all.sh` — it requires a target and stop, and those come from reading the profiler output:

```bash
python run_stage1.py --target X --stop Y --years 6 | tee stage1_output.txt
```

It refuses to run without both, and without `profile_obs.json`.

---

## The verification step is not optional

```
AAPL   amc      # reports after the close
MSFT   amc      # reports after the close
JPM    bmo      # banks report before the open
```

**All three identical → the parser is broken.** Flip `SEC_TS_IS_UTC` at the top of `build_earnings.py` and re-run. I could not determine whether SEC's `acceptanceDateTime` is UTC or already Eastern; the two readings differ by enough to flip `amc` into `intraday`. Five seconds to settle it.

---

## Files

**Pipeline** — run in this order

| | |
|---|---|
| `build_universe_file.py` | Top N by dollar ADV at window start. Not alphabetical. |
| `build_earnings.py` | EDGAR 8-K Item 2.02 → `earnings.csv` |
| `mfe_profile.py` | Stage 0.5. MFE/MAE with **no target, no stop, no capital** |
| `control_arm.py` | Random-entry baseline. Signal MFE is meaningless without it |
| `run_stage1.py` | Walk-forward + 35% holdout + expectancy gate |

**Core**

| | |
|---|---|
| `stage1_data.py` | Fetch, filters, halts, splits, earnings blackout |
| `signals.py` | Three candidates with rationale. #1 is wired up |
| `stage1_backtest.py` | Cash account, T+1 settlement, separated gap accounting |
| `stage1_validate.py` | Walk-forward split, reporting |
| `bootstrap.py` | Block bootstrap, measured ICC, expectancy gate, regime split |

**Analysis** (standalone, no API key needed)

| | |
|---|---|
| `cost_model.py` | Per-price round-trip cost, aggressive vs passive, 3x stress |
| `gate_power.py` | Sample size the expectancy gate needs |
| `q4_cluster.py` | Design effect vs required trade count |
| `montecarlo_equity.py` | Dollar equity distribution given an assumed edge |

**Tests** (synthetic data, no key needed — every number they print is meaningless)

| | |
|---|---|
| `test_dryrun.py` | End-to-end with network stubbed. Run this first. |
| `test_bootstrap.py` | ICC recovers known ρ; bootstrap widens with clustering |
| `test_mechanics.py` | Gap exits separate correctly; gate fails closed on noise |

```bash
python test_dryrun.py        # ~30s, no API key, catches runtime errors
```

---

## What to watch

**Effective universe.** Every symbol missing from `earnings.csv` is permanently excluded by fail-closed. If the pull reports 120 missing, your real sample is 280, not 400, and every downstream number is on that smaller set.

**Signal count.** 0 = bug, almost certainly `earnings.csv` failing closed. Under 200 = suspect. A few thousand = healthy.

**Control arm.** If the median 5-day edge over random is near zero, the signal selects nothing and no target choice fixes it. If signal and control are near-identical across *every* row, suspect a filter silently excluding everything rather than a weak signal.

**Regime decomposition** (Stage 1 output). If one calendar year contributes more than ~50% of gross P&L, that's a regime, not an edge — even if the gate passes.

---

## Known limitations, unchanged

- **Survivorship (A5) is not fixed.** The universe is symbols active today. Delisted names are invisible. For a dip-buying signal this cuts hard — those names generated buy signals repeatedly on the way down. Subtract ~0.10–0.20%/trade from expectancy before believing it. Real fix needs paid point-in-time data (Norgate, Sharadar, CRSP).
- **`signal_reversal` is a candidate, not a validated edge.** The mechanism (liquidity provision to forced sellers, Nagel 2012) is documented; this parameterization is not.
- **Cost model assumes 3–10 bps spreads.** Wrong by an order of magnitude in a crisis. The 6-year window starts Aug 2020, so March 2020 is in warmup, not tested — deliberately.
- **`build_earnings.py` is untested against live SEC.** I had no network access to sec.gov. The 3-symbol check exists for exactly this reason.
