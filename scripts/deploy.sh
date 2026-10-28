#!/usr/bin/env bash
# Deploy/update KampusDey on the server (alwaysdata). Run from the checkout:
#   cd ~/kampusdey && scripts/deploy.sh [branch]
# Safe to re-run. Restart the site afterwards (alwaysdata: Web → Sites → Restart, or the API).
set -euo pipefail

BRANCH="${1:-main}"
cd "$(dirname "$0")/.."

echo "==> Updating code ($BRANCH)"
git fetch --prune origin
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"

echo "==> Python packages"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "==> Front-end assets (Tailwind CSS, vendored JS)"
npm ci --no-audit --no-fund --loglevel=error
npm run --silent vendor
npm run --silent build:css

echo "==> Database and static files"
python manage.py migrate --noinput
python manage.py collectstatic --noinput --verbosity 0
python manage.py check --deploy --fail-level ERROR

echo "==> Done. Restart the site to load the new code."
