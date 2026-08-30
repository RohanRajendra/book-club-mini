#!/usr/bin/env bash
# Take a clean machine to a running app.
#
# This script matters more than it looks: the second installation is the
# highest-friction part of the whole design, and the failure it exists to
# prevent is a 404 from Notion with no hint that the cause is an unconnected
# integration.
set -euo pipefail

cd "$(dirname "$0")"

TICK="✓"
CROSS="✗"

say() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# --- 1. prerequisites --------------------------------------------------------

say "Checking prerequisites"

if ! command -v python3 >/dev/null; then
  echo "$CROSS Python 3.11+ is required. Install it from https://python.org or: brew install python@3.13"
  exit 1
fi

python3 - <<'PY' || { echo "$CROSS Python 3.11+ is required (found $(python3 --version))."; exit 1; }
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
echo "$TICK $(python3 --version)"

if ! command -v node >/dev/null; then
  echo "$CROSS Node 20+ is required. Install it from https://nodejs.org or: brew install node"
  exit 1
fi

node_major=$(node --version | sed 's/^v\([0-9]*\).*/\1/')
if [[ "$node_major" -lt 20 ]]; then
  echo "$CROSS Node 20+ is required (found $(node --version))."
  exit 1
fi
echo "$TICK node $(node --version)"

# --- 2. dependencies ---------------------------------------------------------

say "Installing backend dependencies"
[[ -d backend/.venv ]] || python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --quiet --upgrade pip
(cd backend && .venv/bin/python -m pip install --quiet -e ".[dev]")
echo "$TICK backend/.venv ready"

say "Installing frontend dependencies"
(cd frontend && npm install --silent)
echo "$TICK frontend/node_modules ready"

# --- 3. configuration --------------------------------------------------------

if [[ -f backend/.env ]]; then
  say "backend/.env already exists — leaving it alone"
  echo "  Delete it yourself and re-run this script if you want to start over."
else
  say "Configuring this installation"
  cat <<'NOTE'
You need, from the person who set up the Notion workspace:
  - an integration token (starts with ntn_), yours alone
  - the two database IDs, which are the same for both of you
  - the exact member roster, in the same order on both machines

Both integrations must be connected to the Book Club page:
  open the page -> ••• -> Connections -> add the integration.
NOTE

  read -r -p $'\nNotion integration token: ' token
  read -r -p 'Books database ID: ' books_db
  read -r -p 'Posts database ID: ' posts_db
  read -r -p 'Your name (exactly as it should appear on your posts): ' member
  echo
  echo "The roster is both names, comma-separated, e.g. Ada,Grace"
  echo "IMPORTANT: both installations must list them in the SAME ORDER."
  echo "Reader colours are assigned by position, so a swapped order swaps your colours."
  read -r -p 'Roster: ' members

  cat > backend/.env <<EOF
NOTION_TOKEN=$token
NOTION_BOOKS_DB_ID=$books_db
NOTION_POSTS_DB_ID=$posts_db
MEMBER_NAME=$member
MEMBERS=$members
EOF
  chmod 600 backend/.env
  echo "$TICK wrote backend/.env (gitignored)"
fi

# --- 4. verify ---------------------------------------------------------------

say "Checking the Notion workspace"
if (cd backend && .venv/bin/python scripts/verify_notion.py); then
  say "Ready"
  echo "Start the app with:"
  echo
  echo "    ./dev.sh"
  echo
  echo "Then open http://localhost:5173"
else
  say "Notion is not ready yet"
  echo "Fix what is marked $CROSS above, then re-run:"
  echo
  echo "    cd backend && .venv/bin/python scripts/verify_notion.py"
  echo
  echo "The most common cause is an integration that is not connected to the"
  echo "Book Club page: open the page -> ••• -> Connections -> add it."
  exit 1
fi
