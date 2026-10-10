#!/bin/bash
# Commit and push the data files the screener produced. Safe to run repeatedly.
git config user.name dma-bot; git config user.email dma-bot@users.noreply.github.com
for f in signals.json state.json status.json mcap.json nodata.json nifty.json strategies.json forward.json dma44_deep.json insights.json fund.json universe_nse.csv universe_bse.csv backtest.csv backtest.txt; do [ -e "$f" ] && git add "$f"; done
git diff --cached --quiet && exit 0
git commit -q -m "data update"
for i in 1 2 3; do
  git fetch -q origin main
  if git rebase -q -X theirs origin/main && git push -q origin HEAD:main; then exit 0; fi
  git rebase --abort || true
  sleep 5
done
exit 1
