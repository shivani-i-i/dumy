"""Codec comparison. Savings are *estimates from configurable factors*; no video is re-encoded."""
from backend.config.constants import DEFAULT_CODEC_FACTORS
from backend.engines.capacity_engine import camera_storage


def compare(bitrate_mbps, current_codec, hours=24, mode="Continuous", cameras=1,
            retention_days=30, factors=None, baseline="H.264"):
    f = factors or DEFAULT_CODEC_FACTORS
    base_br = bitrate_mbps / f[current_codec]          # normalise to H.264-equivalent
    base_day = camera_storage(base_br * f[baseline], hours, mode)["gb_day"] * cameras
    rows = []
    for codec, factor in f.items():
        br = base_br * factor
        s = camera_storage(br, hours, mode)
        day = s["gb_day"] * cameras
        rows.append({"Codec": codec, "Bitrate (Mbps)": round(br, 2),
                     "GB / day": round(day, 1), "GB / month": round(day * 30, 1),
                     "Retention (TB)": round(day * retention_days / 1000, 2),
                     f"Saving vs {baseline} (%)": round((1 - day / base_day) * 100, 1) if base_day else 0.0})
    return rows


def recompression_saving(size_gb, from_codec, to_codec, factors=None):
    """GB saved if footage encoded with from_codec were stored as to_codec."""
    f = factors or DEFAULT_CODEC_FACTORS
    if f[to_codec] >= f[from_codec]:
        return 0.0
    return size_gb * (1 - f[to_codec] / f[from_codec])
