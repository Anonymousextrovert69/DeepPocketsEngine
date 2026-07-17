# Deep Pockets — Daily Trend Tracker Setup

This runs `deep_pockets_tracker.py` automatically every morning via GitHub Actions,
and commits the results (CSV + Markdown digest) back into the repo — so you
just open the repo each morning and read the latest report. No server needed.

## Setup (10 minutes, one-time)

1. **Create a new GitHub repository**
   - Go to github.com → New repository → name it e.g. `deep-pockets-trends`
   - Private or public, your choice (private is fine and free)

2. **Add these three files to the repo**, keeping this exact folder structure:
   ```
   deep-pockets-trends/
   ├── deep_pockets_tracker.py
   ├── requirements.txt
   └── .github/
       └── workflows/
           └── daily-trend-report.yml
   ```
   Easiest way: on the repo's GitHub page, use "Add file → Upload files" and
   drag all three in (GitHub will recreate the `.github/workflows/` folder
   automatically as long as you keep that path when uploading).

3. **Turn on write access for the workflow**
   - In your repo: Settings → Actions → General → scroll to "Workflow permissions"
   - Select **"Read and write permissions"** → Save
   - (This lets the daily job commit the report files back into the repo.)

4. **That's it.** The workflow will now run automatically every day at
   06:00 IST. You'll see a new commit each morning with:
   - `trend_report_YYYY-MM-DD.csv` — ranked keyword table
   - `digest_YYYY-MM-DD.md` — the headlines/links behind each keyword

## Test it immediately (don't wait for tomorrow)

- Go to your repo → **Actions** tab → click "Deep Pockets Daily Trend Report"
  on the left → click **"Run workflow"** (top right) → Run workflow.
- Wait ~30 seconds, refresh, and you'll see the run complete and new files
  committed to your repo.

## Changing the run time

Edit the `cron` line in `daily-trend-report.yml`. Cron time is in UTC.
IST is UTC+5:30, so subtract 5:30 from your desired IST time to get the UTC
value to put in the cron field. E.g. 8:00 AM IST = 2:30 AM UTC = `'30 2 * * *'`.

## Optional: get it emailed to you instead of checking GitHub

See the commented-out block at the bottom of `daily-trend-report.yml` —
uncomment it and add the three secrets it mentions (Settings → Secrets and
variables → Actions) to get the digest emailed to you every morning instead
of (or in addition to) checking the repo.

## Growing the keyword list over time

Just edit the `KEYWORDS` list in `deep_pockets_tracker.py` whenever a new
video does well — add a few terms from that topic so related follow-up
news gets flagged automatically going forward. Push the change and the
next day's run picks it up.
