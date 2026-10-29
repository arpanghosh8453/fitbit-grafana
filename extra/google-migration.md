# Google Health API Migration Guide

This guide explains how to migrate this project from the legacy Fitbit Web API to the Google Health API while keeping the same overall workflow (token bootstrap, periodic fetch, historical backfill, InfluxDB writes, Grafana dashboards).

## 1) What Changes in This Project

### API and OAuth changes

- Legacy Fitbit API base:
  - `https://api.fitbit.com`
- Google Health API base:
  - `https://health.googleapis.com/v4`

- Legacy token endpoint:
  - `https://api.fitbit.com/oauth2/token`
- Google token endpoint:
  - `https://oauth2.googleapis.com/token`

- User identity/profile endpoints:
  - Google profile: `GET /users/me/profile`
  - Google settings: `GET /users/me/settings`

- Intraday/detailed data endpoint style:
  - `GET /users/me/dataTypes/{dataType}/dataPoints`

### Data type naming rules

- In endpoint path: use **kebab-case**
  - Example: `heart-rate`, `daily-oxygen-saturation`
- In filter expressions: use **snake_case**
  - Example: `heart_rate`, `daily_oxygen_saturation`

### Scope changes

Google uses URL scopes. Use only what you need. Typical read-only scopes for this project:

- `https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly`
- `https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly`
- `https://www.googleapis.com/auth/googlehealth.sleep.readonly`
- `https://www.googleapis.com/auth/googlehealth.location.readonly`
- `https://www.googleapis.com/auth/googlehealth.profile.readonly`
- `https://www.googleapis.com/auth/googlehealth.settings.readonly`
- `https://www.googleapis.com/auth/googlehealth.nutrition.readonly` (only for the `nutrition` and `hydration` values of `EXTRA_FETCH_SELECTION`, see below)

## 2) Configure Google Cloud (Client ID / Secret)

1. Open Google Cloud Console:
   - https://console.cloud.google.com
2. Create or select a project.
3. Enable **Google Health API** for the project from services.
4. Configure OAuth consent screen:
   - Set app information
   - Add required test users who can use the app (add yourself) if app is in Testing mode (from the Audience tab of sidebar) or make the app public. Otherwise you will get an access denied error.
5. Create OAuth credentials:
   - APIs & Services -> Credentials -> Create Credentials -> OAuth client ID
   - Application type: Desktop app
6. Add redirect URI exactly:
   - `http://localhost:8080`
7. Save and copy:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`

## 3) Get Refresh Token Using Parity Tool Settings Menu

Use the parity tool to bootstrap OAuth and extract a refresh token.

- Parity tool:
  - https://developers.google.com/health/migration/parity-tool

### Steps

1. Open parity tool and click **Settings** (gear icon).
2. In OAuth configuration inside Settings:
   - Enter Client ID: your Google OAuth client id
   - Enter Client Secret: your Google OAuth client secret
   - Enter same Redirect URI: `http://localhost:8080`
3. Trigger authentication/re-authentication from Settings.
4. Complete the Google consent flow in browser - copy the `code=xxxxxxxxxx` part from the redirected url (it will be a `This site can’t be reached` page).
5. Return to Settings and paste the code. If successful, you will see the refresh token shown by the tool.
6. Copy and save the refresh token shown there.

Notes:

- If you see repeated Unauthorized errors in parity tool, re-authenticate from Settings.
- Refresh tokens can expire in some cases (for example long inactivity or testing-mode policy constraints).

## 4) Update Project Configuration

Use Google mode in `compose.yml` (or shell env vars for local runs).

Required environment variables:

- `HEALTH_API_PROVIDER=google`
- `GOOGLE_CLIENT_ID=<your_client_id>`
- `GOOGLE_CLIENT_SECRET=<your_client_secret>`
- `TOKEN_FILE_PATH=/app/tokens/fitbit.token` (or your preferred location) - delete any existing token file you might have before you started the migration.

Existing variables still required for database/write pipeline:

- `INFLUXDB_VERSION`
- `INFLUXDB_HOST`
- `INFLUXDB_PORT`
- `INFLUXDB_DATABASE` (and auth vars when applicable)

Optional for local validation without DB writes:

- `DRY_RUN_MODE=true` but this will skip any database writes so don't use this for actual migration.

### Optional extra data (`EXTRA_FETCH_SELECTION`)

The Google Health API exposes more data than the default dashboard uses. These extra data types are **off by default**, so an existing setup keeps making the same API calls. Enable the ones you want with a comma separated list, for example `EXTRA_FETCH_SELECTION=vo2max,active_minutes,hr_zone_time`, or `EXTRA_FETCH_SELECTION=all`. They are fetched every 3 hours in the regular update and in 28-day chunks during a bulk update. This variable is ignored with `HEALTH_API_PROVIDER=fitbit`.

| Value | Google data type(s) | Measurement written | Notes |
| --- | --- | --- | --- |
| `vo2max` | `daily-vo2-max`, `vo2-max`, `run-vo2-max` | `VO2 Max` (tag `Type`: `daily`, `measured`, `run`) | Cardio Fitness score |
| `hrv_intraday` | `heart-rate-variability` | `HRV_Intraday` | Individual HRV samples (`HRV` keeps the nightly summary) |
| `breathing_sleep_stages` | `respiratory-rate-sleep-summary` | `BreathingRate_Sleep` | Breathing rate per sleep stage, one point per sleep |
| `activity_level` | `activity-level` | `ActivityLevel_Intraday` | Minute level, 0 = sedentary to 3 = very active |
| `active_minutes` | `active-minutes` | `Activity Minutes` | Adds `minutesLightlyActive`, `minutesFairlyActive`, `minutesVeryActive` (same fields as Fitbit mode) |
| `hr_zone_time` | `time-in-heart-rate-zone`, `calories-in-heart-rate-zone`, `daily-heart-rate-zones` | `HR zone time`, `HR zone calories`, `HR zone limits` | Minutes, kcal and bpm boundaries per zone |
| `active_calories` | `active-energy-burned` | `Active Calories` | Daily active kcal (`calories` is the total) |
| `swim` | `swim-lengths-data` | `Swim` | Daily lengths, strokes and swim time |
| `nutrition` | `nutrition-log` | `Nutrition` | Food logged in the Fitbit app. Needs the `nutrition.readonly` scope |
| `hydration` | `hydration-log` | `Hydration` | Water logged in the Fitbit app (ml). Needs the `nutrition.readonly` scope |
| `exercise_gps` | `exercise` (`exportExerciseTcx`) | `GPS` | GPS track of exercises recorded with GPS (up to 10 per run). Needs the `location.readonly` scope |

The default Grafana dashboard has no panels for these measurements; build your own panels to visualize them. A data type your device does not record simply returns no points.

## 5) First Run / Token Bootstrap

After setting appropriate env vars, run one interactive start:

```bash
docker compose run fitbit-fetch-data
```

When prompted, paste the refresh token obtained from parity tool Settings.

The script will refresh access token and persist token metadata to `TOKEN_FILE_PATH`.

stop the container after the first run with `ctrl+c` and then run the container again with `docker compose down && docker compose up -d` to start the container in detached mode.

## 6) Validate Historical Fetch

Example historical fetch run:

```bash
AUTO_DATE_RANGE=False MANUAL_START_DATE="2024-08-20" docker compose run --rm fitbit-fetch-data
```

Use `DRY_RUN_MODE=true` while validating API shape/parsing before writing to InfluxDB.

## 7) Common Migration Issues

### `INVALID_DATA_POINT_FILTER_*` errors

Cause:
- Unsupported filter member for a datatype.

Fix:
- Use datatype-appropriate filter members.
- Remember endpoint datatype naming != filter datatype naming:
  - endpoint: kebab-case
  - filter: snake_case

### API returns 200 but script inserts 0 points

Cause:
- Parser mismatch (nested payload/timestamp/value fields), or date mismatch due to timezone and civil vs physical time.

Fix:
- Confirm payload path for that datatype (`heartRate`, `steps`, `exercise`, `dailyOxygenSaturation`, etc.).
- Confirm filter uses supported field member.
- Verify timezone from `users/me/settings`.

### Unauthorized errors after working earlier

Cause:
- Expired/invalid token.

Fix:
- Re-authenticate from parity tool Settings.
- Re-run script and re-enter a valid refresh token.

## 8) Security Notes

- Never commit real client secrets or refresh tokens.
- If secrets were shared in logs/chat, rotate immediately in Google Cloud.
- Keep token file under protected permissions.

## 9) Migration Status Expectations

The migration in this repository is being rolled out in phases.

- Some Google datasets are already mapped and tested.
- Some grouped legacy fetch blocks may still be marked as not finalized in logs while parity work continues.

Use this guide together with project logs to validate each datatype path incrementally.