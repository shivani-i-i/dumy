"""Rule-based Storage Optimization Engine (NOT AI/ML).

Decision order (first match wins):
  1. protected footage (Incident / Critical Evidence / legal hold) -> never deleted, kept in Hot/Warm
  2. age >= retention expiry                                       -> mark for deletion
  3. age <= effective hot window                                   -> Hot
  4. age <= warm window                                            -> Warm
  5. otherwise                                                     -> Cold (archive)
Pressure overlay: when pool utilization crosses thresholds the hot window shrinks.
Tiers only move *down* automatically (Hot->Warm->Cold); only protected footage is promoted out of Cold.
The engine is deterministic and idempotent: running it twice yields no further changes.
"""
from dataclasses import dataclass, field
from typing import Optional

from backend.config.constants import TIER_RANK, TIERS
from backend.engines.retention_engine import is_protected


@dataclass
class LifecycleConfig:
    hot_window: float = 7
    warm_window: float = 30
    priority_mult: dict = field(default_factory=lambda: {"Low": 0.5, "Medium": 1.0, "High": 1.5, "Critical": 2.0})
    pressure_l1: float = 80
    pressure_l2: float = 90
    shrink: float = 0.5


@dataclass
class Decision:
    footage_id: int
    action: str                 # move | mark_delete | unmark
    from_tier: str
    to_tier: str
    deletion_status: str
    reason: str
    rule: str


def fid(n):
    return f"F-{int(n):06d}"


def pressure_level(util, cfg):
    return 2 if util > cfg.pressure_l2 else (1 if util > cfg.pressure_l1 else 0)


def effective_hot_window(priority, util, cfg):
    base = cfg.hot_window
    mult = cfg.priority_mult[priority]
    days = base * mult
    note = f"{priority}-priority hot window = {base:g} d x {mult:g} = {days:.1f} d"
    lvl = pressure_level(util, cfg)
    if lvl == 2:
        f = cfg.shrink if priority != "Critical" else (1 + cfg.shrink) / 2
    elif lvl == 1:
        f = cfg.shrink if priority in ("Low", "Medium") else 1.0
    else:
        f = 1.0
    if f != 1.0:
        note += (f"; pool utilization {util:.0f}% > {cfg.pressure_l2 if lvl == 2 else cfg.pressure_l1:g}% "
                 f"so window reduced x{f:g} to {days * f:.1f} d")
    return days * f, note


def age_days(f, now):
    return max(0.0, (now - f["end_time"]).total_seconds() / 86400)


def evaluate(f, now, cfg, util) -> Optional[Decision]:
    """Return a Decision if the footage record must change, else None."""
    age = age_days(f, now)
    cur = f["tier"]
    label = f"{fid(f['footage_id'])} ({f['camera_code']} {f['camera_name']}, {f['priority']} priority, {f['importance']})"
    protected = is_protected(f["importance"], f.get("legal_hold"))
    hot_w, hot_note = effective_hot_window(f["priority"], util, cfg)
    warm_w = max(cfg.warm_window, hot_w)

    if protected:
        want = 0 if age <= hot_w else 1
        rank = min(max(TIER_RANK[cur], want), 1)       # never Cold; promote Cold -> Warm
        tier = TIERS[rank]
        if f["deletion_status"] == "Marked":
            return Decision(f["footage_id"], "unmark", cur, tier, "Retained",
                            f"{label} is protected evidence, so its deletion mark was removed.", "R1-protected")
        if tier != cur:
            why = ("restored from Cold archive because protected evidence must stay in Hot/Warm"
                   if cur == "Cold" else f"age {age:.1f} d exceeds hot window {hot_w:.1f} d; protected footage stops at Warm")
            return Decision(f["footage_id"], "move", cur, tier, "Retained", f"{label}: {why}. {cur} -> {tier}.",
                            "R1-protected")
        return None

    if now >= f["retention_expiry"]:
        if f["deletion_status"] == "Retained":
            return Decision(f["footage_id"], "mark_delete", cur, cur, "Marked",
                            f"{label} is {age:.1f} d old and reached its retention expiry "
                            f"({f['retention_expiry']:%Y-%m-%d}); not protected, so marked for deletion.", "R2-expired")
        return None

    if f["deletion_status"] == "Marked":      # retention was extended after marking
        return Decision(f["footage_id"], "unmark", cur, cur, "Retained",
                        f"{label}: retention was extended to {f['retention_expiry']:%Y-%m-%d}; deletion mark removed.",
                        "R2-extended")

    computed = 0 if age <= hot_w else (1 if age <= warm_w else 2)
    rank = max(TIER_RANK[cur], computed)
    if rank == TIER_RANK[cur]:
        return None
    tier = TIERS[rank]
    if computed == 1:
        rule, cmp_txt = "R3-warm", f"{hot_w:.1f} d < age {age:.1f} d <= warm window {warm_w:g} d"
    else:
        rule, cmp_txt = "R4-cold", f"age {age:.1f} d > warm window {warm_w:g} d"
    return Decision(f["footage_id"], "move", cur, tier, "Retained",
                    f"{label} is {age:.1f} d old. {hot_note}. {cmp_txt} -> {cur} -> {tier}.", rule)


def run(footage, now, cfg, util):
    return [d for d in (evaluate(f, now, cfg, util) for f in footage) if d]


def recommend_actions(s, util_warn=75, target_util=70):
    """Ranked optimization recommendations from aggregate stats `s`:
    pool_util, used_gb, capacity_gb, recompress_gb, hot_movable_gb, expiring_gb, hot_util."""
    if s["pool_util"] < util_warn and s.get("hot_util", 0) < 90:
        return []
    recs = []
    if s["recompress_gb"] > 1:
        recs.append({"action": "Compress older H.264/MJPEG footage to H.265 (simulated)",
                     "saving_gb": s["recompress_gb"], "key": "compress",
                     "why": "Warm/Cold footage still uses a less efficient codec; re-encoding at the configured "
                            "H.265 factor frees space without deleting any data."})
    if s["hot_movable_gb"] > 1:
        recs.append({"action": "Move older Hot footage to a lower-cost tier (run lifecycle under pressure profile)",
                     "saving_gb": s["hot_movable_gb"], "key": "tier_down",
                     "why": "Hot storage is the most expensive tier; footage past its shortened hot window can move "
                            "to Warm. This frees Hot capacity (pool total is unchanged)."})
    if s["expiring_gb"] > 1:
        recs.append({"action": "Shorten Normal-class retention by ~20% on non-critical cameras",
                     "saving_gb": s["expiring_gb"], "key": "retention",
                     "why": "Normal footage in the last 20% of its retention window would be deleted earlier. "
                            "Protected footage is never affected. Change retention in Cameras (advisory only)."})
    recs.sort(key=lambda r: -r["saving_gb"])
    need = max(0.0, s["used_gb"] / (target_util / 100) - s["capacity_gb"])
    recs.append({"action": f"Add storage capacity (about {need / 1000:.1f} TB) to return to {target_util}% utilization",
                 "saving_gb": 0.0, "key": "add_capacity",
                 "why": "If optimization cannot free enough space, capacity must grow. Add disks on the RAID page."})
    for i, r in enumerate(recs, 1):
        r["rank"] = i
        r["util_after"] = max(0.0, (s["used_gb"] - r["saving_gb"]) / s["capacity_gb"] * 100) \
            if r["key"] != "add_capacity" else target_util
    return recs
