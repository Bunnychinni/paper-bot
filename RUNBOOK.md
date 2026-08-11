# RUNBOOK — Stage 1

Run these in order. **Stop at any step that fails the verification check.** Each step has a "bug vs. genuine result" test, because the failure mode that will actually cost you time is a silent fail-closed exclusion that looks like "the strategy has no signal."

Total: ~35 minutes of wall clock, ~30 of which is unattended.

---

## Step 0 — Alpaca paper keys

1. Sign up at `alpaca.markets` → Trading API (not Broker API).
2. Dashboard → toggle to **Paper Trading** (top-left switcher). Confirm the URL is `paper-api.alpaca.markets`, not `api.alpaca.markets`.
3. **Generate API Key** → copy both values. The secret shows once.

```bash
export APCA_API_KEY_ID='PK...'          # paper keys start PK, live start AK
export APCA_API_SECRET_KEY='...'
export SEC_UA='swing-research you@youremail.com'
pip install alpaca-py
```

**Verify:**
```bash
python -c "
from alpaca.trading.client import TradingClient
import os
c=TradingClient(os.environ['APCA_API_KEY_ID'],os.environ['APCA_API_SECRET_KEY'],paper=True)
a=c.get_account(); print('status',a.status,'| cash',a.cash,'| PAPER' if 'PK' in os.environ['APCA_API_KEY_ID'] else '| CHECK KEY')"
```
Expect `ACTIVE` and $100,000 (paper default). If your key starts `AK`, stop — those are live keys.

**Failure:** `403` = wrong environment (live keys against paper endpoint or vice versa). `401` = bad secret.

Market data on the free tier is IEX-only for recent quotes but **historical daily bars come from SIP and go back years** — that's all Stage 1 needs. Free tier is 200 req/min.

---

## Step 1 — universe.txt

```bash
python build_universe_file.py --max-symbols 400 --years 6 --out universe.txt
```

Two-pass: probes every tradable US equity over a 90-day window at the *start* of your backtest, then keeps the top 400 by dollar ADV among those passing $10–100 and ADV>2M shares.

**Runtime:** ~3–6 min. **API calls:** ~30–40 (≈5,000 symbols ÷ 200/batch, paginated).

Ranking is at window start, not today, on purpose — ranking on current liquidity selects names that *became* liquid, which is forward-looking. This does not fix survivorship (A5); delisted names aren't in the asset list at all.

**Verify:** 400 lines, and the top 10 should be recognisable liquid mid-caps in the $10–100 band. Mega-caps above $100 are correctly absent.

**Bug vs. real:** fewer than ~250 symbols surviving means your price/ADV filters are too tight for the era, or the probe window hit a holiday stretch. An alphabetical-looking list (AAL, AAP, ABEV…) means the old truncation path ran — re-pull the file.

---

## Step 2 — EDGAR verification on 3 symbols (do not skip)

```bash
python build_earnings.py --symbols AAPL,MSFT,JPM --years 4 --out _verify.csv
cat _verify.csv
```

**Runtime:** ~5 sec. **API calls:** 4 (1 ticker map + 3 submissions).

**Expected:**

| Symbol | Count over 4y | Timing | Months |
|---|---|---|---|
| AAPL | ~16 | **`amc`** | late Jan, late Apr/early May, late Jul/early Aug, late Oct/early Nov |
| MSFT | ~16 | **`amc`** | late Jan, late Apr, late Jul, late Oct |
| JPM | ~16 | **`bmo`** | mid Jan, mid Apr, mid Jul, mid Oct |

The AAPL/MSFT vs JPM contrast is the point. Apple and Microsoft report after the close; JPMorgan reports before the open. **If all three come back the same, the timing parser is broken.**

**The specific bug I could not resolve:** I don't know whether SEC's `acceptanceDateTime` is UTC or already Eastern, and the two interpretations differ by 4–5 hours — enough to flip `amc` into `intraday`. There's a `SEC_TS_IS_UTC = True` flag at the top of `build_earnings.py`.

- AAPL `amc` in winter but `intraday` in summer → timestamps are UTC, flag is correct, but check zoneinfo is installed.
- AAPL `intraday` year-round → set `SEC_TS_IS_UTC = False` and re-run.
- AAPL `amc` year-round and JPM `bmo` → correct, proceed.

Timing is not load-bearing for Stage 1 (the ±7 day blackout absorbs it). It becomes load-bearing in Stage 2. Fix it now while the test is cheap.

**Other failures:** `403` from SEC = your `SEC_UA` is missing or generic; they block default agents. Zero rows for a symbol = it files 6-K (foreign issuer) rather than 8-K.

---

## Step 3 — full earnings pull

```bash
python build_earnings.py --from-universe universe.txt --years 7 --out earnings.csv
```

7 years, not 6 — the blackout needs announcements slightly before the window opens.

**Runtime:** ~2–4 min (rate-limited to ~9 req/sec by design; SEC's ceiling is 10). **API calls:** ~400–900.

**Verify:**
```bash
wc -l earnings.csv
cut -d, -f1 earnings.csv | sort -u | wc -l
cut -d, -f3 earnings.csv | sort | uniq -c
```
Expect ~10,000–12,000 rows (400 × 4/yr × 7yr), 350–400 distinct symbols, and a timing mix skewed to `amc`/`bmo` with few `unknown`.

**This is the highest-risk step for silent failure.** Every symbol missing from `earnings.csv` is permanently excluded from the backtest by A3 fail-closed. If the script reports `NO DATA for 120 symbols`, your effective universe is 280, not 400 — and every downstream result is on that smaller universe. The script prints the list. Read it.

---

## Step 4 — profiler (Stage 0.5)

```bash
python mfe_profile.py --years 6 --universe universe.txt --earnings earnings.csv \
  2>&1 | tee profile_output.txt
```

**Runtime:** ~4–8 min (≈3–5 min fetching, ~30 sec computing — I benchmarked the loop at ~30 sec for 400 symbols × 1500 days). **API calls:** ~60–80. **Memory:** ~1–1.5 GB. If you're tight, use `--max-symbols 200` first.

No target, no stop, no position limit, no capital. Nothing in it knows a gate exists.

**Verify:** signal count in the low thousands. Then check `mean signals per active date` and `share of signals on the busiest 10% of dates` — that's the clustering, measured.

**Bug vs. genuine no-signal:**

| Symptom | Diagnosis |
|---|---|
| **0 signals** | Almost certainly a bug. Check `earnings.csv` loaded (`len(earnings)` printed at start) — fail-closed with an empty file excludes everything. |
| **< 200 signals** | Suspect. The z ≤ −1.5 threshold with a 200-day trend filter should fire far more often. Check how many symbols pass `build_universe`. |
| **> 20,000 signals** | Also suspect — the trend or z filter may not be engaging. Confirm the 200-day SMA is being computed on enough history. |
| **1,000–8,000 signals** | Normal. Proceed. |

Send me `profile_output.txt` before choosing a target.

---

## Step 5 — Stage 1 (only after we agree on target/stop)

```bash
python run_stage1.py --target X --stop Y --years 6 --block entry_date \
  2>&1 | tee stage1_output.txt
```

Refuses to run without both `--target` and `--stop`, and without `profile_obs.json`. Exits 0 on pass, 1 on fail.

**Runtime:** ~6–10 min. **API calls:** ~60–80.

---

## The 6-year window: regime concerns

**Correction to your premise:** six years back from Aug 2026 starts Aug 2020, and the 200-day trend filter means nothing trades until ~200 sessions in. **The Feb–Mar 2020 crash lands entirely in warmup.** You'd need ~7 years to get it into the tested window.

**My recommendation: keep 6 years. Don't add year 7 to chase COVID.** Three reasons:

1. **It would probably inflate, not deflate, your result.** People assume COVID punishes dip-buying. The March crash does — but the April–August V-recovery rewarded it spectacularly. Net, including 2020 likely makes a mean-reversion strategy look *better* than it is.
2. **My cost model is badly wrong for March 2020.** I assumed 3–10 bps spreads. Spreads on $10–100 names blew out to 30–100+ bps. The backtest would understate costs by an order of magnitude in exactly the period you'd be including for realism.
3. **One crash is one draw, not a distribution.** Tuning around it is as much a fitting error as excluding it.

**What the 6-year window does contain, and why it matters:**

- **2020–21:** zero rates, meme-stock retail flow, extreme dispersion. Mean reversion worked unusually well. Not representative.
- **2022:** bear market. The 200-day filter should keep you mostly flat — a genuine test of the filter, but low trade count.
- **2023–24:** narrow mega-cap leadership, poor breadth. Mid-cap mean reversion less rewarded.
- **2024–26:** I have no reliable knowledge past May 2026. Treat that stretch as unexamined by me.

**Structural consequence you should know:** walk-forward folds are chronological, so fold 1 ≈ 2020–21 (the most favourable regime) and the 35% holdout ≈ the most recent, least favourable one. That's the right direction — but it means a Q3 walk-forward/holdout inconsistency may reflect **regime change rather than overfitting**, and those need different responses. Don't read a WF/holdout gap as automatic evidence of curve-fitting.

I added a **regime decomposition** to the Stage 1 output: expectancy per calendar year, plus what share of gross P&L the best single year contributes. **If one year is more than ~50% of gross P&L, you found a regime, not an edge** — and that's true even if the gate passes.

---

## API call and runtime summary

| Step | Runtime | Calls | Fails how |
|---|---|---|---|
| 0 keys | 1 min | 1 | 401/403 |
| 1 universe | 3–6 min | 30–40 | too few symbols |
| 2 EDGAR verify | 5 sec | 4 | timing all-identical |
| 3 EDGAR full | 2–4 min | 400–900 | silent symbol exclusions |
| 4 profiler | 4–8 min | 60–80 | 0 signals = bug |
| 5 Stage 1 | 6–10 min | 60–80 | exit code 1 = gate fail |

Well inside Alpaca's 200 req/min and SEC's 10 req/sec.

**Nothing in any of these steps places an order.** `TradingClient` appears once, read-only, for `get_all_assets`. Grep for `submit_order` returns nothing.
