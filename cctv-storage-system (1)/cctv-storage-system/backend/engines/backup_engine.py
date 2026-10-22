"""Backup sizing, RPO / RTO evaluation (simulation)."""


def full_backup_size(hot_gb, warm_gb):
    """Design decision: Cold tier is already an archive copy, so a full backup covers Hot + Warm."""
    return hot_gb + warm_gb


def duration_hours(size_gb, speed_gb_per_hr):
    return size_gb / speed_gb_per_hr if speed_gb_per_hr > 0 else 0.0


def restore_chain(backups):
    """Latest successful Full + every successful Incremental after it (oldest first)."""
    ok = sorted([b for b in backups if b["status"] == "Success"], key=lambda b: b["started_at"])
    fulls = [b for b in ok if b["backup_type"] == "Full"]
    if not fulls:
        return []
    last_full = fulls[-1]
    return [last_full] + [b for b in ok if b["backup_type"] == "Incremental" and b["started_at"] > last_full["started_at"]]


def estimate_rto(restore_gb, restore_speed, overhead_hours=0.25):
    return restore_gb / restore_speed + overhead_hours if restore_speed > 0 else float("inf")


def evaluate(backups, now, rpo_hours, rto_hours, restore_speed, overhead_hours=0.25, frequency_hours=24):
    """Return the DR posture. Recovery point = START time of the newest successful backup."""
    ok = sorted([b for b in backups if b["status"] == "Success"], key=lambda b: b["started_at"])
    attempts = sorted(backups, key=lambda b: b["started_at"])
    last_ok = ok[-1] if ok else None
    last_attempt = attempts[-1] if attempts else None
    age = max(0.0, (now - last_ok["started_at"]).total_seconds() / 3600) if last_ok else None
    chain = restore_chain(backups)
    restore_gb = sum(b["size_gb"] for b in chain)
    rto = estimate_rto(restore_gb, restore_speed, overhead_hours) if chain else None
    res = {"last_success": last_ok, "last_attempt": last_attempt, "age_hours": age,
           "latest_failed": bool(last_attempt and last_attempt["status"] == "Failed"),
           "rpo_ok": age is not None and age <= rpo_hours,
           "chain": chain, "restore_gb": restore_gb, "est_rto_hours": rto,
           "rto_ok": rto is not None and rto <= rto_hours, "rpo_hours": rpo_hours, "rto_hours": rto_hours}
    res["next_due_hours"] = None if last_ok is None else frequency_hours - age
    res["rpo_msg"] = ("No successful backup exists - potential data loss is unbounded." if last_ok is None else
                      f"Newest recovery point is {age:.1f} h old; target RPO is {rpo_hours:g} h "
                      f"({'met' if res['rpo_ok'] else 'VIOLATED'}).")
    res["rto_msg"] = ("No restorable backup chain (a Full backup is required)." if rto is None else
                      f"Restoring {restore_gb:,.0f} GB is estimated at {rto:.1f} h; target RTO is {rto_hours:g} h "
                      f"({'met' if res['rto_ok'] else 'VIOLATED'}).")
    return res
