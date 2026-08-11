#!/usr/bin/env bash
# Stage 1, in order. Stops on any failure.
set -euo pipefail

: "${APCA_API_KEY_ID:?set APCA_API_KEY_ID}"
: "${APCA_API_SECRET_KEY:?set APCA_API_SECRET_KEY}"
: "${SEC_UA:?set SEC_UA to 'project your@email.com'}"

case "$APCA_API_KEY_ID" in
  PK*) echo "paper keys OK" ;;
  *)   echo "REFUSING: key does not start with PK. Those look like LIVE keys." >&2; exit 1 ;;
esac

YEARS=${YEARS:-6}
N=${N:-400}

echo; echo "=== 1/5 universe (3-6 min) ==="
python build_universe_file.py --max-symbols "$N" --years "$YEARS" --out universe.txt

echo; echo "=== 2/5 EDGAR verification (5 sec) -- STOP AND READ ==="
python build_earnings.py --symbols AAPL,MSFT,JPM --years 4 --out _verify.csv
cat _verify.csv
echo
echo "AAPL and MSFT must be 'amc'. JPM must be 'bmo'."
echo "All three identical => parser broken, flip SEC_TS_IS_UTC in build_earnings.py."
read -r -p "Verification passed? [y/N] " ok
[ "$ok" = "y" ] || { echo "stopping"; exit 1; }

echo; echo "=== 3/5 full earnings pull (2-4 min) ==="
python build_earnings.py --from-universe universe.txt --years $((YEARS+1)) --out earnings.csv

echo; echo "=== 4/5 profiler (4-8 min) ==="
python mfe_profile.py --years "$YEARS" --universe universe.txt \
    --earnings earnings.csv 2>&1 | tee profile_output.txt

echo; echo "=== 5/5 control arm (1 min) ==="
python control_arm.py --years "$YEARS" --universe universe.txt \
    --earnings earnings.csv 2>&1 | tee control_output.txt

echo
echo "Done. Send back profile_output.txt and control_output.txt."
echo "Stage 1 is NOT run automatically -- target and stop must be chosen first."
