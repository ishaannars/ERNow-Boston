#!/usr/bin/env bash
# Rebuild ERNow from a new CMS release. Stops at the first failed check, so nothing unverified is committed.
#   1. Save the new CMS hospital archive as data/cms_archives/hospitals_compare_YYYYMM.zip
#   2. bash scripts/refresh_release.sh
set -euo pipefail
cd "$(dirname "$0")/.."
python national_model.py --check
python national_model.py
python boston_choice_analysis.py
python research/calibrate_chance_fastest.py
python research/national_impact.py
python research/regime_switch_test.py
python research/equity_audit.py
python research/write_extra_tests.py
python scripts/verify_claims.py
pytest -q
git add -A
git commit -m "ERNow: refresh from new CMS release (all checks passed)"
echo "All checks passed and committed. Review, then: git push (and reboot ERNow on Streamlit Cloud)."
