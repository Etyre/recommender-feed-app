#!/bin/sh
# Install (or reinstall) the Recommender Feed launchd agents. Idempotent; safe to rerun.
#
#   ./install.sh            schedule the pipeline (com.elityre.recommender-feed.pipeline,
#                           runs 7:30 / 12:30 / 17:30 / 21:30)
#   ./install.sh --server   also build the frontend and install the always-on web server
#                           (com.elityre.recommender-feed.server at http://localhost:8000)
#   ./install.sh --app      --server, plus build the desktop app into
#                           ~/Applications/Reading Feed.app (desktop/build.sh)
#
# Both targets substitute the checkout, data and log paths into launchd/*.plist, copy the
# result to ~/Library/LaunchAgents, boot out any previously loaded copy (including the old
# com.elityre.feedapp.* labels) and bootstrap the new one. Logs: ~/Library/Logs/recommender-feed*.log
set -eu
cd "$(dirname "$0")"
[ -d backend/.venv ] || make setup
# Every commit and pull then updates the running server and app by itself (deploy.sh).
git config core.hooksPath hooks
make schedule
if [ "${1:-}" = "--server" ] || [ "${1:-}" = "--app" ]; then
  make install
fi
if [ "${1:-}" = "--app" ]; then
  ./desktop/build.sh
fi
make status
