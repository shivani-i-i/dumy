"""Statistical trend forecasting (ordinary least squares). Not AI."""
from datetime import timedelta

import numpy as np


def forecast(history, capacity_gb, now, steady_state_gb=None, window=14, min_points=7):
    """history: list of (date, used_gb) oldest first. Uses the last `window` points."""
    out = {"ok": False, "capacity_gb": capacity_gb, "message": ""}
    pts = history[-window:]
    if len(pts) < min_points:
        out["message"] = f"Insufficient data: {len(pts)} daily points, need at least {min_points}."
        return out
    x = np.arange(len(pts), dtype=float)
    y = np.array([p[1] for p in pts], dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res, ss_tot = float(((y - pred) ** 2).sum()), float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 if ss_tot == 0 else 1 - ss_res / ss_tot
    cur = float(y[-1])
    out.update(ok=True, slope=float(slope), daily_gb=float(slope), weekly_gb=float(slope) * 7,
               monthly_gb=float(slope) * 30, r2=r2, current_gb=cur, points=len(pts),
               current_util=cur / capacity_gb * 100, line=[(p[0], float(v)) for p, v in zip(pts, pred)])
    for pct in (80, 100):
        key = f"days_to_{pct}"
        target = capacity_gb * pct / 100
        if cur >= target:
            out[key], out[f"date_{pct}"] = 0.0, now
        elif slope <= 0:
            out[key], out[f"date_{pct}"] = None, None
        else:
            d = (target - cur) / slope
            out[key], out[f"date_{pct}"] = d, now + timedelta(days=d)
    if slope <= 0:
        out["message"] = "Storage is not growing (flat or shrinking trend)."
    elif out["days_to_80"] == 0:
        out["message"] = "Storage is already above 80% of capacity."
    else:
        out["message"] = f"Storage will reach 80% capacity in approximately {out['days_to_80']:.0f} days."
    if steady_state_gb is not None:
        out["steady_state_gb"] = steady_state_gb
        out["steady_util"] = steady_state_gb / capacity_gb * 100
        out["steady_exceeds"] = steady_state_gb > capacity_gb
        out["steady_msg"] = (
            f"Once retention-based deletion balances ingest, usage plateaus near {steady_state_gb / 1000:.1f} TB "
            f"({out['steady_util']:.0f}% of capacity)"
            + (" - this EXCEEDS capacity, so capacity must be increased or retention reduced."
               if out["steady_exceeds"] else " - capacity is sufficient in the long run."))
    return out
