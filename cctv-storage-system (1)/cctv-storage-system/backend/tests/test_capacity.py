from backend.engines import capacity_engine as ce, compression_engine as comp


def test_gb_per_hour_4mbps():
    assert abs(ce.gb_per_hour(4) - 1.8) < 1e-9


def test_daily_4mbps_24h():
    assert abs(ce.camera_storage(4, 24)["gb_day"] - 43.2) < 1e-9


def test_bitrate_estimate_h265_saves_45pct():
    h264 = ce.effective_bitrate("1080p", 30, "H.264")
    h265 = ce.effective_bitrate("1080p", 30, "H.265")
    assert h264 == 4.0 and abs((1 - h265 / h264) - 0.45) < 1e-9


def test_manual_calculation_chain():
    r = ce.manual_calculation(10, "1080p", 30, "H.264", 24, 30, overhead_pct=10, headroom_pct=20)
    assert abs(r["total_daily_gb"] - 432) < 1e-6
    assert abs(r["retention_gb"] - 12960) < 1e-6
    assert abs(r["recommended_gb"] - 12960 * 1.1 * 1.2) < 1e-6
    assert len(r["steps"]) == 9


def test_motion_mode_reduces_storage():
    assert ce.camera_storage(4, 24, "Motion")["gb_day"] < ce.camera_storage(4, 24)["gb_day"]


def test_compression_compare():
    rows = comp.compare(4.0, "H.264")
    d = {r["Codec"]: r for r in rows}
    assert d["H.264"]["Saving vs H.264 (%)"] == 0
    assert abs(d["H.265"]["Saving vs H.264 (%)"] - 45.0) < 0.1
    assert d["MJPEG"]["Saving vs H.264 (%)"] < 0
