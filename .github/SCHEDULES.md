# Workflow schedules (cron-job.org)

GitHub's own `schedule:` triggers start hours late on this repo (2-5 hours
in Sept-Oct 2026) and sometimes skip runs. Manual (`workflow_dispatch`) runs
start within seconds, so the daily jobs are started by
[cron-job.org](https://cron-job.org) calling GitHub's API on time.

All times are US Eastern. Set each job's time zone to `America/New_York`
so daylight saving is handled for you.

## The jobs

| Job | Workflow file | When (ET) | Body |
|---|---|---|---|
| NHL predictions, morning | `daily-nhl-analysis.yml` | Every day 6:37 AM | `{"ref":"main","inputs":{"slot":"morning"}}` |
| NHL predictions, midday | `daily-nhl-analysis.yml` | Every day 12:23 PM | `{"ref":"main","inputs":{"slot":"midday"}}` |
| NHL predictions, pre-game | `daily-nhl-analysis.yml` | Every day 5:41 PM | `{"ref":"main","inputs":{"slot":"pregame"}}` |
| NHL odds, opening | `market-snapshot.yml` | Every day 9:00 AM | `{"ref":"main","inputs":{"slot":"opening"}}` |
| NHL odds, midday | `market-snapshot.yml` | Every day 3:00 PM | `{"ref":"main","inputs":{"slot":"midday"}}` |
| NHL odds, close | `market-snapshot.yml` | Every day 6:30 PM | `{"ref":"main","inputs":{"slot":"close"}}` |
| MLB predictions | `daily-mlb-analysis.yml` | Every day 12:00 PM | `{"ref":"main"}` |
| MLB odds, opening | `mlb-market-snapshot.yml` | Every day 9:00 AM | `{"ref":"main","inputs":{"slot":"opening"}}` |
| MLB odds, midday | `mlb-market-snapshot.yml` | Every day 1:00 PM | `{"ref":"main","inputs":{"slot":"midday"}}` |
| MLB odds, close | `mlb-market-snapshot.yml` | Every day 6:30 PM | `{"ref":"main","inputs":{"slot":"close"}}` |
| NFL, evening | `nfl-predictions.yml` | Tue-Sat 5:17 PM | `{"ref":"main"}` |
| NFL, morning | `nfl-predictions.yml` | Thu, Sat, Sun, Mon 9:17 AM | `{"ref":"main"}` |

Why these times:

- **NHL predictions:** the slate rolls over at 6 AM ET, so 6:37 AM is the
  first run of the day. 5:41 PM refreshes with odds closer to puck drop. The
  `slot` makes the weekly Sunday refit run only on the morning run.
- **Odds snapshots:** 6:30 PM is the closing line for 7 PM games. The
  `slot` keeps failure emails to the opening snapshot (one per day).
- **NFL:** the evening runs land just after each injury-report deadline
  (4 PM the day before Thursday games, two days before the rest). The
  morning runs are retries and score the weekend's games. Extra runs are
  harmless: games that aren't ready are skipped.

## Setting up a job

Every job is the same request with a different URL, body and time:

- **URL:** `https://api.github.com/repos/totqro/projects/actions/workflows/<workflow file>/dispatches`
- **Method:** POST (under Advanced)
- **Headers:**
  - `Authorization: Bearer <your token>`
  - `Accept: application/vnd.github+json`
  - `X-GitHub-Api-Version: 2022-11-28`
  - `Content-Type: application/json`
- **Body:** from the table
- **Schedule:** custom, time zone `America/New_York`
- **Notifications:** turn on "notify on failure"

GitHub answers `204 No Content` on success. A `422` means the body names
an input the workflow on `main` doesn't have.

## The token

A fine-grained personal access token that can only start workflows here:

1. github.com > Settings > Developer settings > Personal access tokens >
   Fine-grained tokens > Generate new token.
2. Resource owner: `totqro`. Repository access: only `totqro/projects`.
3. Permissions > Repository > **Actions: Read and write**. Nothing else.
4. Expiry: the longest allowed. Put a reminder in your calendar a week
   before it expires; when it does, every job starts failing with `401`.

## GitHub's own cron

Once the cron-job.org jobs are running, remove the `schedule:` blocks from
the workflows above; otherwise every job also runs a second time, hours
late, and spends Odds API quota twice.
