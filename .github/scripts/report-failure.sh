#!/usr/bin/env bash
# Open an issue for a failed scheduled check, or comment on the one already open.
#
# A red run in the Actions tab notifies nobody; an issue does. One open issue
# per title, so a check that fails every day adds a comment instead of a pile
# of duplicates. Close the issue once the cause is fixed.
#
# Usage: report-failure.sh "<issue title>" "<what failed and where to look>"
# Needs GH_TOKEN with issues: write, and RUN_URL for the link back to the run.
set -euo pipefail

title="$1"
body="$2

Run: ${RUN_URL:-unknown}"

number=$(gh issue list --state open --limit 200 --json number,title \
  --jq "map(select(.title == \"$title\")) | .[0].number // empty")

if [ -n "$number" ]; then
  gh issue comment "$number" --body "Failed again. $body"
else
  gh issue create --title "$title" --body "$body" --label bug
fi
