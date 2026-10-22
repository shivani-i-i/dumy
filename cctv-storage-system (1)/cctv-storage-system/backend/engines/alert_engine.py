"""Evaluates system state into alert specifications (pure). Persistence/dedup is in alert_service."""


def _a(key, sev, cat, desc, action):
    return {"dedup_key": key, "severity": sev, "category": cat, "description": desc, "recommended_action": action}


def evaluate(s, th):
    """s: state dict, th: thresholds (util_warn, util_high, util_critical, forecast_alert_days)."""
    out = []
    u = s["pool_util"]
    if u > th["util_critical"]:
        out.append(_a("UTIL_CRIT", "Critical", "Storage Utilization", f"Pool utilization is {u:.1f}% (> {th['util_critical']:g}%).",
                      "Open Storage Tiers > Recommendations: compress, tier down, shorten Normal retention or add capacity."))
    elif u > th["util_high"]:
        out.append(_a("UTIL_HIGH", "High", "Storage Utilization", f"Pool utilization is {u:.1f}% (> {th['util_high']:g}%).",
                      "Run the lifecycle engine and review optimization recommendations."))
    elif u > th["util_warn"]:
        out.append(_a("UTIL_WARN", "Warning", "Storage Utilization", f"Pool utilization is {u:.1f}% (> {th['util_warn']:g}%).",
                      "Plan capacity; check the forecast for the expected exhaustion date."))
    for t in s["tiers"]:
        tu = t["util"]
        if tu > 100:
            out.append(_a(f"TIER_OVER_{t['name']}", "Critical", "Tier Capacity",
                          f"{t['name']} tier is over capacity ({tu:.0f}% of {t['capacity_tb']:.1f} TB).",
                          "Run the lifecycle engine to move footage to the next tier, or enlarge the tier."))
        elif tu > 90:
            out.append(_a(f"TIER_FULL_{t['name']}", "High", "Tier Capacity",
                          f"{t['name']} tier is {tu:.0f}% full.", "Run the lifecycle engine to free this tier."))
    b = s.get("backup")
    if b and s["used_gb"] > 0:
        if b["latest_failed"]:
            out.append(_a("BACKUP_FAIL", "Critical", "Backup", "The most recent backup attempt FAILED.",
                          "Re-run the backup and check the destination."))
        if not b["rpo_ok"]:
            out.append(_a("RPO_EXCEEDED", "High", "RPO", b["rpo_msg"], "Run a backup now; consider more frequent incrementals."))
        if b["chain"] and not b["rto_ok"]:
            out.append(_a("RTO_EXCEEDED", "High", "RTO", b["rto_msg"],
                          "Use faster restore media, take a fresh Full backup, or relax the RTO target."))
    r = s.get("raid")
    if r and r["status"] in ("Degraded", "Failed"):
        sev = "Critical" if r["status"] == "Failed" else "High"
        out.append(_a("RAID_" + r["status"].upper(), sev, "RAID",
                      f"{r['level']} array is {r['status']} ({r['failed']} failed disk(s)).",
                      "Replace the failed disk and start a rebuild." if r["status"] == "Degraded"
                      else "Array lost - restore from the latest backup."))
    if s.get("retention_violations", 0) > 0:
        out.append(_a("RET_VIOLATION", "High", "Retention", f"{s['retention_violations']} unprotected clip(s) are past "
                      "their retention expiry but not yet marked for deletion.", "Run the lifecycle engine."))
    if s.get("protected_review", 0) > 0:
        out.append(_a("PROTECTED_REVIEW", "Warning", "Retention", f"{s['protected_review']} protected clip(s) passed their "
                      "retention period. They are never auto-deleted.", "Review each clip; downgrade or release the hold (Admin) if no longer needed."))
    f = s.get("forecast")
    if f and f.get("ok"):
        d80 = f.get("days_to_80")
        if d80 is not None and 0 < d80 <= th["forecast_alert_days"]:
            out.append(_a("FORECAST_80", "High", "Forecast", f"Storage is predicted to reach 80% in about {d80:.0f} days.",
                          "Order capacity or tighten retention before that date."))
        if f.get("steady_exceeds"):
            out.append(_a("STEADY_STATE", "High", "Forecast", f.get("steady_msg", ""),
                          "Add capacity or reduce retention/bitrate; current policy cannot fit in this pool."))
    return out


AUTO_PREFIXES = ("UTIL_", "TIER_", "BACKUP_", "RPO_", "RTO_", "RAID_", "RET_", "PROTECTED_", "FORECAST_", "STEADY_")
