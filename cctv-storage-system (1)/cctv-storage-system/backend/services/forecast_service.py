"""Capacity forecasting using the daily storage_metrics history."""
from database import connection as db
from backend.engines import forecast_engine as fe
from backend.services import camera_service, settings_service as ss, storage_service


def compute(now=None, window=14):
    now = now or ss.get_clock()
    st = storage_service.pool_state()
    hist_df = storage_service.metrics_history()
    history = [] if hist_df.empty else list(zip(hist_df["recorded_on"], hist_df["used_gb"]))
    cams = camera_service.list_cameras(active_only=True)
    prot = db.fetch_one("SELECT COALESCE(SUM(f.size_gb),0) AS gb FROM footage f LEFT JOIN incidents i USING(footage_id) "
                        "WHERE f.deletion_status<>'Deleted' AND (f.importance IN ('Incident','Critical Evidence') "
                        "OR COALESCE(i.legal_hold,false))")["gb"]
    steady = sum(c["est_gb_day"] * c["retention_days"] for c in cams) + prot
    res = fe.forecast(history, st["capacity_gb"], now, steady if cams else None, window=window)
    return {"result": res, "history": hist_df, "steady_gb": steady, "capacity_gb": st["capacity_gb"],
            "daily_generation_gb": sum(c["est_gb_day"] for c in cams)}
