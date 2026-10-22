from datetime import datetime, timedelta
from backend.engines import lifecycle_engine as le, retention_engine as re_

NOW = datetime(2026, 10, 7)
CFG = le.LifecycleConfig()
POLICY = {"important_days": 90, "incident_days": 180, "critical_days": 365, "normal_days": 30}


def clip(age_days, tier="Hot", priority="Medium", importance="Normal", retention=30, status="Retained", hold=False, fid_=1):
    end = NOW - timedelta(days=age_days)
    return {"footage_id": fid_, "camera_code": "C01", "camera_name": "Main Gate", "priority": priority,
            "end_time": end, "importance": importance, "tier": tier, "legal_hold": hold, "deletion_status": status,
            "retention_expiry": re_.expiry(end, importance, retention, POLICY, hold)}


def test_hot_boundary_stays_hot():
    assert le.evaluate(clip(7), NOW, CFG, 40) is None


def test_moves_to_warm_after_hot_window():
    d = le.evaluate(clip(8), NOW, CFG, 40)
    assert d.to_tier == "Warm" and "7 d x 1" in d.reason


def test_cold_after_warm_window():
    assert le.evaluate(clip(31, "Warm", retention=90), NOW, CFG, 40).to_tier == "Cold"


def test_priority_adjusts_hot_window():
    assert le.evaluate(clip(9, priority="High"), NOW, CFG, 40) is None      # 7 x 1.5 = 10.5
    assert le.evaluate(clip(4, priority="Low"), NOW, CFG, 40).to_tier == "Warm"  # 7 x 0.5 = 3.5


def test_pressure_shrinks_window():
    assert le.evaluate(clip(5), NOW, CFG, 50) is None
    d = le.evaluate(clip(5), NOW, CFG, 85)                # Medium window 7 -> 3.5
    assert d.to_tier == "Warm" and "reduced" in d.reason
    assert le.evaluate(clip(5, priority="High"), NOW, CFG, 85) is None  # High unaffected at level 1


def test_expired_marked_for_deletion():
    d = le.evaluate(clip(31), NOW, CFG, 40)
    assert d.action == "mark_delete" and d.deletion_status == "Marked"


def test_incident_survives_beyond_normal_expiry():
    c = clip(100, "Warm", importance="Incident")
    assert c["retention_expiry"] > NOW           # 180 d retention
    assert le.evaluate(c, NOW, CFG, 40) is None


def test_protected_never_marked_even_if_expired():
    c = clip(400, "Warm", importance="Critical Evidence")
    d = le.evaluate(c, NOW, CFG, 40)
    assert d is None or d.action != "mark_delete"
    c2 = clip(200, "Warm", importance="Incident")
    d2 = le.evaluate(c2, NOW, CFG, 40)
    assert d2 is None or d2.action != "mark_delete"


def test_legal_hold_never_expires():
    c = clip(5000, "Warm", importance="Normal", hold=True)
    assert le.evaluate(c, NOW, CFG, 40) is None


def test_protected_restored_from_cold():
    d = le.evaluate(clip(50, "Cold", importance="Incident"), NOW, CFG, 40)
    assert d.to_tier == "Warm"


def test_protected_footage_is_unmarked():
    d = le.evaluate(clip(35, "Warm", importance="Incident", status="Marked"), NOW, CFG, 40)
    assert d.action == "unmark"


def test_no_automatic_promotion():
    assert le.evaluate(clip(2, "Cold"), NOW, CFG, 40) is None


def test_idempotent():
    clips = [clip(a, "Hot", fid_=i, retention=45) for i, a in enumerate([1, 6, 9, 20, 33, 44, 50], 1)]
    for d in le.run(clips, NOW, CFG, 40):
        c = next(x for x in clips if x["footage_id"] == d.footage_id)
        c["tier"], c["deletion_status"] = d.to_tier, d.deletion_status
    assert le.run(clips, NOW, CFG, 40) == []


def test_retention_classes():
    assert re_.retention_days("Normal", 30, POLICY) == 30
    assert re_.retention_days("Incident", 30, POLICY) == 180
    assert re_.retention_days("Critical Evidence", 30, POLICY) == 365
    assert re_.retention_days("Important", 120, POLICY) == 120      # never shortened


def test_recommendations_only_under_pressure():
    s = dict(pool_util=50, hot_util=10, used_gb=1, capacity_gb=2, recompress_gb=5, hot_movable_gb=5, expiring_gb=5)
    assert le.recommend_actions(s) == []
    s["pool_util"] = 92
    recs = le.recommend_actions(s)
    assert recs[-1]["key"] == "add_capacity" and recs[0]["rank"] == 1
