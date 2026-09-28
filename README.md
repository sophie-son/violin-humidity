# Violin Humidity Monitor

An hourly automation that estimates indoor humidity in Seoul from public weather
data and sends a Discord alert only when the estimate moves outside the safe range
for a violin (40–60% relative humidity). Built to protect my own violin, and as a
portfolio piece alongside my other GitHub Actions automations.

## Why

Wood instruments crack, warp, or develop glue problems outside a fairly narrow
humidity band. I wanted a passive early-warning system rather than remembering to
check a hygrometer — something that tells me only when I actually need to act
(add a humidifier pack to the case, or pull it out), not a constant stream of
readings I'd learn to ignore.

## How it works

1. **GitHub Actions** runs `check.py` on a schedule (hourly).
2. The script calls **Open-Meteo** (free, no API key) for Seoul's current outdoor
   temperature, relative humidity, and dew point.
3. Outdoor RH isn't a useful proxy for indoor RH on its own — heating and AC change
   relative humidity indoors, but the *amount* of moisture in the air (its dew
   point) stays roughly constant as that air moves inside and is heated or cooled
   to room temperature. The script re-expresses the outdoor dew point as an
   estimated RH at an assumed indoor temperature, using the Magnus formula for
   saturation vapor pressure.
4. The estimate is compared against a 40–60% safe range, with a small hysteresis
   band (±2%) so the status doesn't flap back and forth when the estimate sits
   right at the boundary.
5. Every run is appended to `data/readings.csv`, so there's a growing time series
   to look back on.
6. A Discord message is sent **only when the status changes** (ok → too dry → ok,
   etc.) — not on every run. The workflow commits the updated data files back to
   the repo, so state persists between runs without a database.

## Architecture

```
GitHub Actions (cron, hourly)
        │
        ▼
   check.py ──► Open-Meteo API (weather)
        │
        ├─► data/readings.csv   (full history, one row per run)
        ├─► data/state.json     (last known status, for change detection)
        └─► Discord webhook     (only fires on a status change)
```

No server, no database, no paid API — the repo itself is the datastore, and GitHub
Actions is the scheduler.

## Known limitation: estimate, not measurement

This estimates indoor humidity from *outdoor* weather. It ignores real indoor
moisture sources (cooking, showers, the room's ventilation and heating pattern),
so it's a proxy, not a ground truth reading. The plan is to calibrate it against a
real hygrometer placed near the violin case:

- Compare the estimate to the actual reading over a few days across different
  weather.
- Adjust `CALIB_OFFSET` and `INDOOR_TEMP` in `check.py` to close the gap.
- If the gap is large or inconsistent, that's the signal to move to a real sensor
  (e.g. a Bluetooth hygrometer with a cloud API) instead of a weather-based proxy.

## Debugging notes (for my own reference)

A few things that broke during setup, in case future-me or someone reading this
hits the same issues:

- **`.gitignore` blocked the workflow's own commit.** I originally ignored `data/`
  to keep local test runs out of git, forgetting the workflow *needs* to commit
  `data/readings.csv` back to the repo. Fixed by removing `data/` from
  `.gitignore` entirely — the data is meant to be tracked.
- **"Re-run jobs" reruns the old broken commit.** After pushing a fix, clicking
  "Re-run jobs" on an already-failed run replays the exact commit it originally
  failed on. A genuinely new run has to be started from the workflow's own
  "Run workflow" button, not from inside a past run.
- **Transient SSL handshake timeout to Open-Meteo.** A GitHub-hosted runner
  occasionally can't complete a TLS handshake to the API on the first try. Added a
  retry with backoff (3 attempts) around the fetch so a one-off network blip
  doesn't fail the whole run.

## Setup

1. Create a Discord webhook in the channel you want alerts in (Server Settings →
   Integrations → Webhooks).
2. Add it as a repo secret named `DISCORD_WEBHOOK` (Settings → Secrets and
   variables → Actions).
3. Settings → Actions → General → Workflow permissions → **Read and write
   permissions** (the workflow commits `data/` back to the repo).
4. Push this repo, then trigger the workflow once manually (Actions →
   violin-humidity → Run workflow) to confirm it's green.
5. After that it runs automatically every hour.

## Possible next steps

- Swap the weather-based estimate for a real Bluetooth/Wi-Fi hygrometer once
  calibration data justifies the cost.
- Add a rate-of-change alert (a fast swing can stress the wood more than a
  moderate but stable out-of-range reading).
- Plot `data/readings.csv` into a chart, refreshed by the workflow, and embed it
  here.
