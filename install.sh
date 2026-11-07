#!/bin/sh
# Install (or reinstall) the Recommender Feed launchd agents. Idempotent; safe to rerun.
#
#   ./install.sh            schedule the pipeline (com.elityre.recommender-feed.pipeline,
#                           runs 7:30 / 12:30 / 17:30 / 21:30)
#   ./install.sh --server   also build the frontend and install the always-on web server
#                           (com.elityre.recommender-feed.server at http://localhost:8000)
#
# Both targets substitute the checkout, data and log paths into launchd/*.plist, copy the
# result to ~/Library/LaunchAgents, boot out any previously loaded copy (including the old
# com.elityre.feedapp.* labels) and bootstrap the new one. Logs: ~/Library/Logs/recommender-feed*.log
set -eu
cd "$(dirname "$0")"
[ -d backend/.venv ] || make setup
make schedule
if [ "${1:-}" = "--server" ]; then
  make install
fi
make status
