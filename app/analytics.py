from datetime import timedelta
from math import exp

CTL_DAYS = 42
ATL_DAYS = 7


def _interpolate(times, distances, target_distance):
    for i in range(1, len(distances)):
        if distances[i] >= target_distance:
            d0, d1 = distances[i - 1], distances[i]
            t0, t1 = times[i - 1], times[i]
            if d1 == d0:
                return t1
            fraction = (target_distance - d0) / (d1 - d0)
            return t0 + fraction * (t1 - t0)
    return None


def best_effort(times, distances, target_distance_meters):
    if distances[-1] - distances[0] < target_distance_meters:
        return None

    best = None
    for i in range(len(distances)):
        target = distances[i] + target_distance_meters
        crossing_time = _interpolate(times[i:], distances[i:], target)
        if crossing_time is None:
            break
        duration = crossing_time - times[i]
        if best is None or duration < best:
            best = duration
    return best


def is_new_best_effort(existing_seconds, candidate_seconds):
    if existing_seconds is None:
        return True
    return candidate_seconds < existing_seconds


def _zone_for_hr(hr, zones):
    matched = None
    for zone in sorted(zones, key=lambda z: z["min_bpm"]):
        if hr >= zone["min_bpm"]:
            matched = zone
        else:
            break
    return matched["zone_number"] if matched else None


def time_in_zone(times, hr_values, zones):
    zone_seconds = {zone["zone_number"]: 0.0 for zone in zones}
    for i in range(len(times) - 1):
        dt = times[i + 1] - times[i]
        zone_number = _zone_for_hr(hr_values[i], zones)
        if zone_number is not None:
            zone_seconds[zone_number] += dt
    return zone_seconds


def km_splits(times, distances, split_meters=1000.0):
    total_distance = distances[-1]
    splits = []
    prev_time = times[0]
    covered = 0.0
    boundary = split_meters
    while boundary <= total_distance:
        crossing_time = _interpolate(times, distances, boundary)
        splits.append(
            {
                "distance_meters": split_meters,
                "duration_seconds": crossing_time - prev_time,
                "pace_per_km_seconds": crossing_time - prev_time,
            }
        )
        prev_time = crossing_time
        covered = boundary
        boundary += split_meters

    remainder = total_distance - covered
    if remainder > 0:
        end_time = times[-1]
        splits.append(
            {
                "distance_meters": remainder,
                "duration_seconds": end_time - prev_time,
                "pace_per_km_seconds": (end_time - prev_time) / (remainder / split_meters),
            }
        )
    return splits


# Empirical grade-adjustment constant: running pace slows ~3.3% per 1% incline.
GRADE_ADJUSTMENT_FACTOR = 0.033


def grade_adjusted_pace(raw_pace_sec_per_km, grade_percent):
    return raw_pace_sec_per_km * (1 + GRADE_ADJUSTMENT_FACTOR * grade_percent)


def trimp(duration_minutes, avg_hr, hr_rest, hr_max, gender="male"):
    delta_ratio = (avg_hr - hr_rest) / (hr_max - hr_rest)
    if gender == "male":
        weighting = 0.64 * exp(1.92 * delta_ratio)
    else:
        weighting = 0.86 * exp(1.67 * delta_ratio)
    return duration_minutes * delta_ratio * weighting


def ctl_atl(daily_loads):
    ctl_decay = 1 - exp(-1 / CTL_DAYS)
    atl_decay = 1 - exp(-1 / ATL_DAYS)

    results = []
    ctl = atl = None
    for load in daily_loads:
        ctl = load if ctl is None else ctl + (load - ctl) * ctl_decay
        atl = load if atl is None else atl + (load - atl) * atl_decay
        results.append({"ctl": ctl, "atl": atl, "form": ctl - atl})
    return results


def riegel_predict(known_time_seconds, known_distance_meters, target_distance_meters, exponent=1.06):
    return known_time_seconds * (target_distance_meters / known_distance_meters) ** exponent


def estimate_vo2max(distance_meters, duration_seconds, avg_hr=None, max_hr=None):
    velocity = distance_meters / (duration_seconds / 60)
    vo2_at_pace = -4.60 + 0.182258 * velocity + 0.000104 * velocity**2
    t_minutes = duration_seconds / 60
    percent_max = (
        0.8
        + 0.1894393 * exp(-0.012778 * t_minutes)
        + 0.2989558 * exp(-0.1932605 * t_minutes)
    )
    vdot = vo2_at_pace / percent_max
    if avg_hr and max_hr:
        vdot *= max_hr / avg_hr
    return vdot


def coalesce_stream_metric(times, values):
    pairs = [(t, v) for t, v in zip(times, values) if v is not None]
    if not pairs:
        return [], []
    ts, vs = zip(*pairs)
    return list(ts), list(vs)


METERS_PER_MILE = 1609.344
FEET_PER_METER = 3.28084
LB_PER_KG = 2.20462262


def convert_distance(meters, units):
    if units == "imperial":
        return meters / METERS_PER_MILE, "mi"
    return meters / 1000, "km"


def convert_pace(seconds_per_km, units):
    if units == "imperial":
        return seconds_per_km * (METERS_PER_MILE / 1000), "mi"
    return seconds_per_km, "km"


def convert_elevation(meters, units):
    if units == "imperial":
        return meters * FEET_PER_METER, "ft"
    return meters, "m"


def convert_weight(kg, units):
    if units == "imperial":
        return kg * LB_PER_KG, "lb"
    return kg, "kg"


def split_distance_meters(units):
    return METERS_PER_MILE if units == "imperial" else 1000.0


def weight_to_kg(value, units):
    if units == "imperial":
        return value / LB_PER_KG
    return value


def elevation_gain_from_stream(times, elevations):
    coalesced_times, coalesced_elevations = coalesce_stream_metric(times, elevations)
    gain = 0.0
    for prev, curr in zip(coalesced_elevations, coalesced_elevations[1:]):
        if curr > prev:
            gain += curr - prev
    return gain


def build_daily_trimp_loads(daily_totals, start_date, end_date):
    loads = []
    current = start_date
    while current <= end_date:
        loads.append(daily_totals.get(current, 0.0))
        current += timedelta(days=1)
    return loads


def default_max_hr(birth_year, reference_year):
    return 220 - (reference_year - birth_year)


def value_at_time(times, values, target_time):
    if not times:
        return None
    closest_index = min(range(len(times)), key=lambda i: abs(times[i] - target_time))
    return values[closest_index]


RUN_DOT = "#7FB2E8"
RIDE_DOT = "#8FD1B0"
GYM_DOT = "#C9A46B"
OTHER_DOT = "#9C9CA6"

_GYM_TYPES = {
    "TraditionalStrengthTraining",
    "FunctionalStrengthTraining",
    "CoreTraining",
    "HighIntensityIntervalTraining",
    "JumpRope",
}


def categorize_activity_type(activity_type):
    if activity_type == "Run":
        return {"category": "Run", "label": "Run", "dot": RUN_DOT}
    if activity_type == "Cycle":
        return {"category": "Ride", "label": "Ride", "dot": RIDE_DOT}
    if activity_type in _GYM_TYPES:
        return {"category": "Gym", "label": "Gym", "dot": GYM_DOT}
    return {"category": "Other", "label": activity_type, "dot": OTHER_DOT}


def format_duration(seconds):
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_pace(seconds_per_km):
    if seconds_per_km is None:
        return None
    total = int(round(seconds_per_km))
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


# Five distinct hues, cool → hot, the fitness-app zone convention. Shared with
# the route-map gradient, which interpolates between them. Validated for CVD
# and normal-vision adjacent-pair separation and ≥3:1 surface contrast; zone
# names/bpm labels always accompany the color, so identity is never color-alone.
_HR_ZONE_DEFS = [
    ("Zone 1 — Recovery", "Very light · active recovery", 0.50, 0.60, "#38BDF8"),
    ("Zone 2 — Aerobic", "Endurance base building", 0.60, 0.70, "#4ADE80"),
    ("Zone 3 — Tempo", "Sustained moderate effort", 0.70, 0.80, "#FDE047"),
    ("Zone 4 — Threshold", "Hard · lactate threshold", 0.80, 0.90, "#F97316"),
    ("Zone 5 — VO2 max", "Maximal · short intervals", 0.90, 1.00, "#E11D48"),
]


# Karvonen method, matching Apple Watch defaults: zone boundaries are
# percentages of heart-rate reserve (max − resting), not of max HR alone.
def hr_zone_bands(max_hr, resting_hr):
    reserve = max_hr - resting_hr
    zones = []
    for i, (name, desc, lo, hi, color) in enumerate(_HR_ZONE_DEFS):
        lo_bpm = round(resting_hr + lo * reserve)
        hi_bpm = round(resting_hr + hi * reserve)
        zones.append(
            {
                "zone_number": i + 1,
                "name": name,
                "desc": desc,
                "color": color,
                "lo": lo,
                "hi": hi,
                # Zone 1 is open-ended below so warm-up and recovery time is
                # counted instead of dropped.
                "min_bpm": 0 if i == 0 else lo_bpm,
                "pct_range": f"{round(lo * 100)}–{round(hi * 100)}%",
                "bpm_range": f"< {hi_bpm} bpm" if i == 0 else f"{lo_bpm}–{hi_bpm} bpm",
            }
        )
    return zones


def calendar_levels(daily_loads, start_date, end_date):
    days = []
    current = start_date
    while current <= end_date:
        days.append({"date": current, "load": daily_loads.get(current, 0.0)})
        current += timedelta(days=1)

    nonzero = [d["load"] for d in days if d["load"] > 0]
    max_load = max(nonzero) if nonzero else 0.0

    levels = []
    for d in days:
        if d["load"] <= 0 or max_load <= 0:
            level = 0
        elif d["load"] <= max_load / 3:
            level = 1
        elif d["load"] <= max_load * 2 / 3:
            level = 2
        else:
            level = 3
        levels.append({"date": d["date"], "level": level})
    return levels


def current_streak(levels):
    streak = 0
    for day in reversed(levels):
        if day["level"] <= 0:
            break
        streak += 1
    return streak


def annotate_splits_for_display(splits):
    if not splits:
        return []
    paces = [s["pace_per_km_seconds"] for s in splits]
    fastest = min(paces)
    slowest = max(paces)
    spread = slowest - fastest

    annotated = []
    for split, pace in zip(splits, paces):
        bar_pct = 100.0 if spread == 0 else round(30 + (slowest - pace) / spread * 70, 2)
        annotated.append({**split, "is_fastest": pace == fastest, "bar_pct": bar_pct})
    return annotated
