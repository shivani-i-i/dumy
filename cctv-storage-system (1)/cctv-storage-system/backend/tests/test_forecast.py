from datetime import date, datetime, timedelta
from backend.engines import forecast_engine as fe, backup_engine as be, alert_engine as ae

NOW = datetime(2026, 10, 7)


def hist(n, start, step):
    return [(date(2026, 9, 1) + timedelta(days=i), start + step * i) for i in range(n)]


def test_linear_slope_and_dates():
    f = fe.forecast(hist(14, 1000, 100), 10000, NOW)
    assert abs(f["daily_gb"] - 100) < 1e-6 and abs(f["r2"] - 1) < 1e-9
    assert abs(f["weekly_gb"] - 700) < 1e-6
    assert abs(f["days_to_80"] - (8000 - 2300) / 100) < 1e-6


def test_flat_not_growing():
    f = fe.forecast(hist(14, 1000, 0), 10000, NOW)
    assert f["days_to_80"] is None and "not growing" in f["message"]


def test_insufficient_data():
    assert not fe.forecast(hist(3, 1, 1), 100, NOW)["ok"]


def test_steady_state_warning():
    f = fe.forecast(hist(14, 1000, 100), 10000, NOW, steady_state_gb=12000)
    assert f["steady_exceeds"]


def test_rpo_violation():
    b = [{"backup_type": "Full", "status": "Success", "started_at": NOW - timedelta(hours=30), "size_gb": 1000}]
    e = be.evaluate(b, NOW, 24, 4, 500)
    assert not e["rpo_ok"] and abs(e["age_hours"] - 30) < 1e-9
    assert e["rto_ok"]                                           # 1000/500 + 0.25 = 2.25 h


def test_rto_violation_and_chain():
    t = NOW - timedelta(hours=2)
    b = [{"backup_type": "Full", "status": "Success", "started_at": t - timedelta(days=2), "size_gb": 3000},
         {"backup_type": "Incremental", "status": "Success", "started_at": t, "size_gb": 100}]
    e = be.evaluate(b, NOW, 24, 4, 500)
    assert e["rpo_ok"] and len(e["chain"]) == 2 and not e["rto_ok"]


def test_failed_latest():
    b = [{"backup_type": "Full", "status": "Success", "started_at": NOW - timedelta(hours=5), "size_gb": 10},
         {"backup_type": "Incremental", "status": "Failed", "started_at": NOW - timedelta(hours=1), "size_gb": 0}]
    e = be.evaluate(b, NOW, 24, 4, 500)
    assert e["latest_failed"] and e["rpo_ok"]


TH = dict(util_warn=75, util_high=85, util_critical=90, forecast_alert_days=30)


def test_alert_utilization_levels():
    base = dict(tiers=[], used_gb=1)
    sev = lambda u: [a["severity"] for a in ae.evaluate({**base, "pool_util": u}, TH)]
    assert sev(70) == [] and sev(80) == ["Warning"] and sev(88) == ["High"] and sev(95) == ["Critical"]


def test_alert_raid_and_backup():
    s = dict(pool_util=10, used_gb=1, tiers=[], raid={"status": "Degraded", "level": "RAID6", "failed": 1},
             backup={"latest_failed": True, "rpo_ok": False, "rpo_msg": "x", "chain": [], "rto_ok": False, "rto_msg": ""})
    keys = {a["dedup_key"] for a in ae.evaluate(s, TH)}
    assert {"RAID_DEGRADED", "BACKUP_FAIL", "RPO_EXCEEDED"} <= keys
