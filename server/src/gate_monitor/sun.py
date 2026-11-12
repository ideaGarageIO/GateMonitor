"""Approximate sunrise/sunset — good enough for coop schedules and solar mocks.

Uses the standard solar declination / hour-angle equations (accurate to a few
minutes away from the poles). No external dependencies.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone


def sun_times(day: date, latitude: float, longitude: float) -> tuple[datetime, datetime]:
    """Return (sunrise, sunset) for ``day`` as aware datetimes in local time.

    At polar day/night the result is clamped to 00:00 / 23:59.
    """
    n = day.timetuple().tm_yday
    gamma = 2 * math.pi / 365 * (n - 1)
    # Equation of time (minutes) and declination (radians) — NOAA approximation.
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    lat = math.radians(latitude)
    zenith = math.radians(90.833)
    cos_ha = (math.cos(zenith) / (math.cos(lat) * math.cos(decl))) - math.tan(lat) * math.tan(decl)

    midnight_utc = datetime.combine(day, time(0), tzinfo=timezone.utc)
    if cos_ha >= 1:  # polar night
        start = midnight_utc
        return _local(start), _local(start)
    if cos_ha <= -1:  # midnight sun
        return _local(midnight_utc), _local(midnight_utc + timedelta(hours=23, minutes=59))

    ha = math.degrees(math.acos(cos_ha))
    sunrise_min = 720 - 4 * (longitude + ha) - eqtime
    sunset_min = 720 - 4 * (longitude - ha) - eqtime
    sunrise = midnight_utc + timedelta(minutes=sunrise_min)
    sunset = midnight_utc + timedelta(minutes=sunset_min)
    return _local(sunrise), _local(sunset)


def _local(dt: datetime) -> datetime:
    return dt.astimezone()


def daylight_fraction(now: datetime, latitude: float, longitude: float) -> float:
    """0 at night, rising to 1 at solar noon (half-sine across the day)."""
    sunrise, sunset = sun_times(now.astimezone().date(), latitude, longitude)
    if not sunrise < now < sunset:
        return 0.0
    span = (sunset - sunrise).total_seconds()
    return math.sin(math.pi * (now - sunrise).total_seconds() / span)
