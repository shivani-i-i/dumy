"""End-to-end model of the demo (engines only, no DB): mirrors simulation_service + storage_service."""
import random
from datetime import date, datetime, timedelta

from backend.config.constants import DEMO_CAMERAS
from backend.engines import (alert_engine as ae, backup_engine as be, capacity_engine as ce,
                     forecast_engine as fe, lifecycle_engine as le, retention_engine as rt)

POLICY = {"normal_days": 30, "important_days": 90, "incident_days": 180, "critical_days": 365}
CAP_GB, TIER_CAP = 20000, {"Hot": 4000, "Warm": 10000, "Cold": 6000}
TH = dict(util_warn=75, util_high=85, util_critical=90, forecast_alert_days=30)


def build():
    cams = []
    for i, (code, name, loc, res, fps, codec, mode, pri, ret) in enumerate(DEMO_CAMERAS, 1):
        cams.append(dict(id=i, camera_code=code, camera_name=name, priority=pri, retention_days=ret,
                         bitrate=ce.effective_bitrate(res, fps, codec)))
    return cams


def gen(cams, start, hours, clips, rng, scale=1.0):
    t = start
    while t < start + timedelta(hours=hours):
        end = t + timedelta(hours=6)
        for c in cams:
            clips.append(dict(footage_id=len(clips) + 1, camera_code=c["camera_code"], camera_name=c["camera_name"],
                              priority=c["priority"], start_time=t, end_time=end, tier="Hot", importance="Normal",
                              legal_hold=False, deletion_status="Retained",
                              size_gb=c["bitrate"] * 0.45 * 6 * rng.uniform(.9, 1.1) * scale,
                              retention_expiry=rt.expiry(end, "Normal", c["retention_days"], POLICY), retention=c["retention_days"]))
        t = end
    return t


def used(clips):
    return sum(c["size_gb"] for c in clips if c["deletion_status"] != "Deleted")


def lifecycle(clips, now, purge=True):
    cfg = le.LifecycleConfig()
    live = [c for c in clips if c["deletion_status"] != "Deleted"]
    for d in le.run(live, now, cfg, used(clips) / CAP_GB * 100):
        c = next(x for x in live if x["footage_id"] == d.footage_id)
        c["tier"], c["deletion_status"] = d.to_tier, d.deletion_status
    if purge:
        for c in live:
            if c["deletion_status"] == "Marked" and not rt.is_protected(c["importance"], c["legal_hold"]):
                c["deletion_status"] = "Deleted"


def test_full_demo():
    rng, cams, clips = random.Random(7), build(), []
    t0 = datetime(2026, 9, 1)
    now = gen(cams, t0, 7 * 24, clips, rng)                       # step 3: 7 days history, all Hot
    assert {c["tier"] for c in clips} == {"Hot"}
    daily = sum(ce.camera_storage(c["bitrate"])["gb_day"] for c in cams)
    assert 150 < daily < 300

    now = gen(cams, now, 10 * 24, clips, rng)                     # advance 10 d with lifecycle OFF
    now = t0 + timedelta(days=17)
    lifecycle(clips, now, purge=False)                            # steps 5-6: run lifecycle -> Warm
    assert any(c["tier"] == "Warm" for c in clips)
    assert not any(c["tier"] == "Cold" for c in clips)

    # step 8: flag an incident on a C01 clip that is ~12 days old
    target = next(c for c in clips if c["camera_code"] == "C01" and 11.5 < (now - c["end_time"]).days + 0.0 < 13)
    target["importance"] = "Incident"
    target["retention_expiry"] = rt.expiry(target["end_time"], "Incident", target["retention"], POLICY)
    assert (target["retention_expiry"] - target["end_time"]).days == 180   # step 9: extended retention

    for _ in range(40):                                           # advance 40 days, lifecycle ON daily
        now = gen(cams, now, 24, clips, rng)
        lifecycle(clips, now)
    assert any(c["tier"] == "Cold" for c in clips)                # step 7: archived
    assert target["deletion_status"] == "Retained" and target["tier"] in ("Hot", "Warm")
    old_normal = [c for c in clips if c["camera_code"] == "C01" and c["importance"] == "Normal"
                  and (now - c["end_time"]).days > 31]
    assert all(c["deletion_status"] == "Deleted" for c in old_normal)   # normal footage expired, incident survived

    for _ in range(3):
        lifecycle(clips, now)                                     # idempotent / steady
    before = [(c["tier"], c["deletion_status"]) for c in clips]
    lifecycle(clips, now)
    assert before == [(c["tier"], c["deletion_status"]) for c in clips]

    # steady state is below capacity for the 20 TB demo pool
    steady = sum(ce.camera_storage(c["bitrate"])["gb_day"] * c["retention_days"] for c in cams)
    assert steady < CAP_GB


def test_pressure_raises_alert_and_forecast():
    rng, cams, clips = random.Random(3), build(), []
    now = gen(cams, datetime(2026, 9, 1), 30 * 24, clips, rng, scale=4.0)   # "upgrade to 4K"-like ingest
    u = used(clips) / CAP_GB * 100
    assert u > 85
    state = dict(pool_util=u, used_gb=used(clips), tiers=[], backup=None, raid=None)
    assert ae.evaluate(state, TH)
    hist = [(date(2026, 9, 1) + timedelta(days=i), 4 * 200 * (i + 1) * 1.0) for i in range(14)]
    f = fe.forecast(hist, CAP_GB, now, steady_state_gb=25000)
    assert f["steady_exceeds"] and f["days_to_80"] > 0
