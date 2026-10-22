"""Capacity planning formulas (pure functions)."""
from backend.config.constants import (DEFAULT_CODEC_FACTORS, GB_PER_MBPS_HOUR, MODE_FACTORS,
                              RESOLUTION_BASE_MBPS)


def effective_bitrate(resolution, fps, codec, factors=None):
    """Encoded bitrate (Mbps) estimate: base(res) x fps/30 x codec factor.
    FPS scaling is linear here as a simplification (real codecs scale sub-linearly)."""
    f = factors or DEFAULT_CODEC_FACTORS
    return round(RESOLUTION_BASE_MBPS[resolution] * (fps / 30.0) * f[codec], 2)


def gb_per_hour(bitrate_mbps):
    """Mbps x 3600 s / 8 / 1000 = Mbps x 0.45 (decimal GB)."""
    return bitrate_mbps * GB_PER_MBPS_HOUR


def camera_storage(bitrate_mbps, hours_per_day=24, mode="Continuous", mode_factors=None):
    mf = (mode_factors or MODE_FACTORS)[mode]
    per_hour = gb_per_hour(bitrate_mbps)
    per_day = per_hour * hours_per_day * mf
    return {"gb_hour": per_hour, "gb_day": per_day, "gb_month": per_day * 30, "mode_factor": mf}


def plan(cameras, overhead_pct=10, headroom_pct=20, mode_factors=None):
    """cameras: dicts with bitrate_mbps, recording_hours, recording_mode, retention_days, [label].
    Returns per-camera rows and aggregate requirement."""
    rows, daily, base = [], 0.0, 0.0
    for c in cameras:
        s = camera_storage(c["bitrate_mbps"], c.get("recording_hours", 24),
                           c.get("recording_mode", "Continuous"), mode_factors)
        ret_gb = s["gb_day"] * c["retention_days"]
        rows.append({"camera": c.get("label", c.get("camera_code", "?")),
                     "gb_hour": s["gb_hour"], "gb_day": s["gb_day"], "gb_month": s["gb_month"],
                     "retention_days": c["retention_days"], "retention_gb": ret_gb})
        daily += s["gb_day"]
        base += ret_gb
    with_overhead = base * (1 + overhead_pct / 100)
    recommended = with_overhead * (1 + headroom_pct / 100)
    return {"rows": rows, "daily_gb": daily, "monthly_gb": daily * 30, "base_gb": base,
            "overhead_gb": with_overhead - base, "with_overhead_gb": with_overhead,
            "headroom_gb": recommended - with_overhead, "recommended_gb": recommended,
            "recommended_tb": recommended / 1000}


def manual_calculation(n, resolution, fps, codec, hours, retention_days, mode="Continuous",
                       bitrate_override=None, overhead_pct=10, headroom_pct=20,
                       factors=None, mode_factors=None):
    """Calculator for N identical cameras, returning a worked step table."""
    est = effective_bitrate(resolution, fps, codec, factors)
    br = bitrate_override if bitrate_override else est
    mf = (mode_factors or MODE_FACTORS)[mode]
    gh = gb_per_hour(br)
    gd = gh * hours * mf
    total_d = gd * n
    total_m = total_d * 30
    ret = total_d * retention_days
    ovh = ret * overhead_pct / 100
    with_o = ret + ovh
    head = with_o * headroom_pct / 100
    rec = with_o + head
    src = "user-supplied" if bitrate_override else \
        f"{RESOLUTION_BASE_MBPS[resolution]} Mbps x ({fps}/30) x codec factor {(factors or DEFAULT_CODEC_FACTORS)[codec]}"
    steps = [
        ("1. Bitrate (Mbps)", src, f"{br:.2f} Mbps"),
        ("2. Storage / camera / hour", f"{br:.2f} Mbps x 3600 s / 8 / 1000", f"{gh:.3f} GB"),
        ("3. Storage / camera / day", f"{gh:.3f} GB x {hours} h x mode factor {mf}", f"{gd:.2f} GB"),
        ("4. Total daily storage", f"{gd:.2f} GB x {n} cameras", f"{total_d:.2f} GB"),
        ("5. Total monthly storage", f"{total_d:.2f} GB x 30 days", f"{total_m / 1000:.2f} TB"),
        ("6. Retention requirement", f"{total_d:.2f} GB x {retention_days} days", f"{ret / 1000:.2f} TB"),
        ("7. + File-system / metadata overhead", f"{ret / 1000:.2f} TB x {overhead_pct}%", f"+{ovh / 1000:.2f} TB"),
        ("8. + Headroom (never run at 100%)", f"{with_o / 1000:.2f} TB x {headroom_pct}%", f"+{head / 1000:.2f} TB"),
        ("9. Recommended usable capacity", "retention + overhead + headroom", f"{rec / 1000:.2f} TB"),
    ]
    return {"bitrate": br, "gb_hour": gh, "gb_day": gd, "total_daily_gb": total_d,
            "total_monthly_gb": total_m, "retention_gb": ret, "overhead_gb": ovh,
            "headroom_gb": head, "recommended_gb": rec, "recommended_tb": rec / 1000, "steps": steps}
