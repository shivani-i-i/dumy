"""RAID capacity maths and rule-based recommendation. Simulation only - no hardware is configured."""
import math

RAID_INFO = {
    "RAID0": {"label": "RAID 0", "min": 2, "tolerance": "0 disks", "perf": "Fastest reads/writes (striping)",
              "note": "No redundancy - one disk loss destroys the array. Not suitable for surveillance."},
    "RAID1": {"label": "RAID 1", "min": 2, "tolerance": "N-1 disks", "perf": "Good reads; writes at single-disk speed",
              "note": "Mirroring; usable capacity equals one disk."},
    "RAID5": {"label": "RAID 5", "min": 3, "tolerance": "1 disk", "perf": "Good reads; parity write penalty",
              "note": "Cost-efficient; long rebuilds on large disks risk a second failure."},
    "RAID6": {"label": "RAID 6", "min": 4, "tolerance": "2 disks", "perf": "Good reads; higher write penalty",
              "note": "Dual parity; safer for large disks/arrays."},
    "RAID10": {"label": "RAID 10", "min": 4, "tolerance": "1 guaranteed (up to N/2 if in different mirror pairs)",
               "perf": "Fast reads/writes, fast rebuilds", "note": "Striped mirrors; 50% efficiency, higher cost."},
}
LEVELS = list(RAID_INFO)


def calculate(level, n, disk_tb):
    """Return capacity numbers for a RAID level. 'valid' False if the disk count is not allowed."""
    info = RAID_INFO[level]
    out = {"level": level, "disks": n, "raw_tb": n * disk_tb, "valid": True, "message": "",
           "min_disks": info["min"]}
    if n < info["min"]:
        out.update(valid=False, usable_tb=0.0, efficiency=0.0, fault_tolerance=0,
                   message=f"{info['label']} needs at least {info['min']} disks.")
        return out
    if level == "RAID10" and n % 2:
        out.update(valid=False, usable_tb=0.0, efficiency=0.0, fault_tolerance=0,
                   message="RAID 10 needs an even number of disks.")
        return out
    usable = {"RAID0": n * disk_tb, "RAID1": disk_tb, "RAID5": (n - 1) * disk_tb,
              "RAID6": (n - 2) * disk_tb, "RAID10": (n / 2) * disk_tb}[level]
    tol = {"RAID0": 0, "RAID1": n - 1, "RAID5": 1, "RAID6": 2, "RAID10": 1}[level]
    out.update(usable_tb=usable, efficiency=usable / out["raw_tb"], fault_tolerance=tol,
               redundancy_tb=out["raw_tb"] - usable)
    return out


def disks_needed(level, usable_tb, disk_tb):
    """Disks required for a target usable capacity, or None if the level cannot provide it."""
    d = math.ceil(usable_tb / disk_tb)
    if level == "RAID0":
        return max(2, d)
    if level == "RAID1":
        return 2 if usable_tb <= disk_tb else None
    if level == "RAID5":
        return max(3, d + 1)
    if level == "RAID6":
        return max(4, d + 2)
    if level == "RAID10":
        n = max(4, 2 * d)
        return n + (n % 2)
    return None


def array_status(level, n, failed):
    """Healthy / Degraded / Failed for a given number of failed disks (worst-case for RAID 10)."""
    if failed <= 0:
        return "Healthy"
    tol = {"RAID0": 0, "RAID1": n - 1, "RAID5": 1, "RAID6": 2}.get(level)
    if level == "RAID10":
        return "Degraded" if failed == 1 else ("Degraded" if failed <= n // 2 else "Failed")
    return "Failed" if failed > tol else "Degraded"


def rebuild_hours(level, disk_tb, rate_mb_s=100):
    """Rough rebuild-time estimate for one replaced disk (parity levels are slower)."""
    base = disk_tb * 1_000_000 / rate_mb_s / 3600
    return round(base * {"RAID5": 1.5, "RAID6": 2.0}.get(level, 1.0), 1)


def recommend(required_usable_tb, disk_tb, goal="Balanced", write_heavy=False, budget_flexible=False):
    """goal in {'Lowest cost','Balanced','High availability + fault tolerance'}."""
    reasons = []
    if goal.startswith("High availability"):
        if write_heavy and budget_flexible:
            level = "RAID10"
            reasons.append("Availability goal + write-heavy workload + flexible budget -> striped mirrors "
                           "give fast writes and quick rebuilds.")
        else:
            level = "RAID6"
            reasons.append("Availability goal -> dual parity survives two simultaneous disk failures "
                           "at a lower cost than mirroring.")
    elif goal == "Lowest cost":
        level = "RAID5"
        reasons.append("Cost goal -> single parity gives the best usable-to-raw ratio among redundant levels.")
        if disk_tb >= 8:
            level = "RAID6"
            reasons.append(f"But {disk_tb} TB disks have long rebuilds; a second failure during rebuild is a "
                           "real risk, so RAID 6 is advised instead.")
    else:
        level = "RAID6" if disk_tb >= 6 or required_usable_tb >= 40 else "RAID5"
        reasons.append("Balanced goal -> " + ("large disks/arrays favour dual parity." if level == "RAID6"
                       else "modest disk size makes single parity acceptable."))
    if write_heavy and level != "RAID10":
        reasons.append("CCTV recording is sequential-write heavy; parity write penalty is usually tolerable "
                       "with a cache-backed controller.")
    n = disks_needed(level, required_usable_tb, disk_tb)
    calc = calculate(level, n, disk_tb)
    reasons.append("RAID protects against disk failure only - it is NOT a backup.")
    alts = []
    for lv in LEVELS:
        nn = disks_needed(lv, required_usable_tb, disk_tb)
        if nn:
            c = calculate(lv, nn, disk_tb)
            alts.append({"Level": RAID_INFO[lv]["label"], "Disks needed": nn, "Raw (TB)": round(c["raw_tb"], 1),
                         "Usable (TB)": round(c["usable_tb"], 1), "Efficiency (%)": round(c["efficiency"] * 100, 1),
                         "Fault tolerance": RAID_INFO[lv]["tolerance"]})
    return {"level": level, "disks": n, "calc": calc, "reasons": reasons, "alternatives": alts}
