# 44-DMA Screener (flat version)
All files sit in one folder. Only `workflow.yml` needs special handling: GitHub requires it at `.github/workflows/screener.yml`.
Steps: 1) upload every file here to a new PUBLIC GitHub repo. 2) Add file > Create new file, name it `.github/workflows/screener.yml`, paste in the contents of workflow.yml, commit.
3) Add secrets TELEGRAM_TOKEN and TELEGRAM_CHAT_ID (optional: EMAIL_USER, EMAIL_APP_PASSWORD, EMAIL_TO) under Settings > Secrets and variables > Actions.
4) Actions > screener > Run workflow > mode test-alert, then mode run. Backtest: same menu, mode backtest.
5) Deploy the repo on vercel.com. Install on phone from the browser menu (Android: Install app, iPhone Safari: Add to Home Screen).
Change strategy in config.yaml. Alerts only, no orders. Not financial advice.
