"""Violin humidity monitor - weather-API version (no sensor, standard library only).

Pulls Seoul outdoor conditions from Open-Meteo (free, no API key), converts them to an
ESTIMATED indoor relative humidity, logs to CSV, and alerts Discord on status change.

Local test:
    export DISCORD_WEBHOOK="https://discord.com/api/webhooks/..."
    python3 check.py
Force an alert to test Discord:
    HUM_LOW=99 HUM_HIGH=100 python3 check.py
"""
import csv
import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEBHOOK = os.environ["DISCORD_WEBHOOK"]

LAT, LON = 37.5665, 126.9780  # Seoul
INDOOR_TEMP = 22.0            # assumed room temperature (C) - adjust to your room
CALIB_OFFSET = 0.0            # tune after comparing with a real hygrometer reading
LOW = float(os.environ.get("HUM_LOW", 40))    # violin-safe RH (%); env override is for testing
HIGH = float(os.environ.get("HUM_HIGH", 60))
HYST = 2                      # must come this far back inside range to clear an alert
KST = timezone(timedelta(hours=9))

DATA = Path("data")
DATA.mkdir(exist_ok=True)
CSV_PATH = DATA / "readings.csv"
STATE_PATH = DATA / "state.json"

# Discord rejects Python's default User-Agent (403), so always send our own.
UA = {"User-Agent": "violin-humidity-monitor/1.0"}


def read_weather():
    query = urllib.parse.urlencode({
        "latitude": LAT,
        "longitude": LON,
        "current": "temperature_2m,relative_humidity_2m,dew_point_2m",
        "timezone": "Asia/Seoul",
    })
    req = urllib.request.Request(
        "https://api.open-meteo.com/v1/forecast?" + query, headers=UA
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        c = json.load(r)["current"]
    return c["temperature_2m"], c["relative_humidity_2m"], c["dew_point_2m"]


def sat_vp(t_c):
    """Saturation vapor pressure (hPa), Magnus formula."""
    return 6.112 * math.exp(17.62 * t_c / (243.12 + t_c))


def est_indoor_rh(dew_point_c):
    """Outdoor air's moisture content, re-expressed as RH at room temperature.

    Heating/AC changes RH indoors, but the moisture content (dew point) stays roughly
    the same. Ignores indoor sources (cooking, showers, people), so treat as a proxy.
    """
    rh = 100 * sat_vp(dew_point_c) / sat_vp(INDOOR_TEMP) + CALIB_OFFSET
    return round(max(0.0, min(100.0, rh)), 1)


def classify(h, prev):
    """ok / low / high, with hysteresis so it doesn't flap at the boundary."""
    if h < LOW:
        return "low"
    if h > HIGH:
        return "high"
    if prev == "low" and h < LOW + HYST:
        return "low"
    if prev == "high" and h > HIGH - HYST:
        return "high"
    return "ok"


def discord(msg):
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps({"content": msg}).encode("utf-8"),
        headers={**UA, "Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=20).read()


def main():
    out_temp, out_rh, dew = read_weather()
    indoor = est_indoor_rh(dew)
    now = datetime.now(KST)

    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {"status": "ok"}
    prev = state["status"]
    status = classify(indoor, prev)

    is_new = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["timestamp_kst", "outdoor_temp", "outdoor_rh", "dew_point",
                        "est_indoor_rh", "status"])
        w.writerow([now.isoformat(timespec="minutes"), out_temp, out_rh, dew, indoor, status])

    if status != prev:
        label = {
            "ok": "✅ Back in range",
            "low": "🔴 DRY - add humidity to the case (humidifier pack)",
            "high": "🔴 HUMID - remove humidifier / add silica gel",
        }[status]
        discord(
            f"{label}\nEst. indoor RH ~{indoor}% (safe {LOW:g}-{HIGH:g}%)\n"
            f"Outside Seoul: {out_temp}°C, {out_rh}% RH"
        )

    STATE_PATH.write_text(json.dumps({"status": status, "updated": now.isoformat()}))
    print(f"{now:%F %H:%M} outdoor={out_rh}% est_indoor={indoor}% status={status}")


if __name__ == "__main__":
    main()
