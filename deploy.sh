#!/bin/zsh
# Bring the running copies up to date with the commit just made (or just pulled).
# Run in the background by hooks/post-commit and hooks/post-merge; safe to run by hand.
#
#   ./deploy.sh            deploy whatever changed in the last commit (HEAD~1..HEAD)
#   ./deploy.sh A B        deploy whatever changed between commits A and B
#   ./deploy.sh --all      rebuild and restart everything regardless of what changed
#
# frontend/ or backend/ changed  -> rebuild the frontend and bounce the launchd server
#                                   (only if the server agent is installed)
# desktop/ or the icon changed   -> rebuild ~/Applications/Reading Feed.app; if it was
#                                   open, quit it and reopen it in the background
# Log: ~/Library/Logs/recommender-feed-deploy.log
set -u
cd "$(dirname "$0")"
# A hook inherits GIT_DIR / GIT_INDEX_FILE from the commit in progress; drop them so the
# git and build commands below see the repo normally.
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX
LOG=~/Library/Logs/recommender-feed-deploy.log
APP=~/Applications/"Reading Feed.app"
BUNDLE_ID=com.elityre.recommender-feed
SERVER=gui/$(id -u)/com.elityre.recommender-feed.server
say() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

if [ "${1:-}" = "--all" ]; then
  changed="frontend/
backend/
desktop/"   # one path per line, like git's output: the checks below match at line start
elif [ $# -ge 2 ]; then
  changed=$(git diff --name-only "$1" "$2")
else
  # --root so the very first commit of a clone also lists its files.
  changed=$(git diff-tree --root --no-commit-id --name-only -r HEAD)
fi
head=$(git rev-parse --short HEAD)

if echo "$changed" | grep -q -E '^(frontend|backend)/'; then
  if launchctl print "$SERVER" >/dev/null 2>&1; then
    # A Refresh-button pipeline run is a child of the server and dies with it; let it finish
    # first (up to 20 minutes, then restart anyway).
    for i in {1..240}; do pgrep -f "app.pipeline --trigger manual" >/dev/null || break; [ $i = 1 ] && say "$head: waiting for a manual pipeline run to finish"; sleep 5; done
    if make restart >> "$LOG" 2>&1; then say "$head: server rebuilt and restarted"
    else say "$head: FAILED to rebuild/restart the server (output above); the old build keeps running"; fi
  else
    say "$head: server agent not installed, nothing restarted (./install.sh --app installs it)"
  fi
fi

if echo "$changed" | grep -q -E '^(desktop/|frontend/public/icon-512\.png)'; then
  pid=$(pgrep -x ReadingFeed | head -1)
  if ./desktop/build.sh >> "$LOG" 2>&1; then
    if [ -n "$pid" ]; then
      # Quit the old copy by PID and wait for it to go, so the reopen cannot land on it.
      kill "$pid" 2>/dev/null
      for i in {1..50}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
      open -g "$APP"   # -g: reopen without taking focus
      say "$head: app rebuilt and reopened (was pid $pid)"
    else
      say "$head: app rebuilt (it was not open)"
    fi
  else
    say "$head: FAILED to build the app (output above); the installed copy is unchanged"
  fi
fi
