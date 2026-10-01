# Notes for Claude

## Talking to the user
- Give times in US Eastern time, not UTC. Convert anything that comes in
  UTC (GitHub Actions logs, cron schedules, API timestamps): UTC-4 while
  daylight time is in effect (2nd Sunday of March to 1st Sunday of November),
  UTC-5 otherwise. Label it "ET" (or EDT/EST when the distinction matters),
  e.g. "the run starts at 12:23 PM ET". Cron expressions in workflow files
  stay in UTC, since that is what GitHub Actions uses; just translate when
  describing them.
