"""Reference tables and defaults. Values are *assumptions* typical of vendor
surveillance sizing guides; they are editable at runtime via Settings."""
from datetime import datetime

# Base bitrate (Mbps) at 30 fps, H.264, typical surveillance scene
RESOLUTION_BASE_MBPS = {"720p": 2.0, "1080p": 4.0, "4MP": 6.0, "4K": 12.0}

# Codec factor relative to H.264 (lower = better compression)
DEFAULT_CODEC_FACTORS = {"H.264": 1.0, "H.265": 0.55, "H.265+": 0.40, "MJPEG": 3.0}

# Fraction of the day a camera actually writes, by recording mode
MODE_FACTORS = {"Continuous": 1.0, "Motion": 0.35, "Scheduled": 1.0}

# 1 Mbps for 1 hour = 3600 s / 8 bits-per-byte / 1000 MB-per-GB = 0.45 GB
GB_PER_MBPS_HOUR = 3600 / 8 / 1000

PRIORITIES = ["Low", "Medium", "High", "Critical"]
IMPORTANCE = ["Normal", "Important", "Incident", "Critical Evidence"]
PROTECTED_CLASSES = ("Incident", "Critical Evidence")
TIERS = ["Hot", "Warm", "Cold"]
TIER_RANK = {"Hot": 0, "Warm": 1, "Cold": 2}
RECORDING_MODES = list(MODE_FACTORS)
RESOLUTIONS = list(RESOLUTION_BASE_MBPS)
CODECS = list(DEFAULT_CODEC_FACTORS)

FAR_FUTURE = datetime(2999, 12, 31)  # expiry used for legal-hold footage

ROLES = ["Admin", "Storage Manager", "Viewer"]

DEFAULT_SETTINGS = {
    # lifecycle windows (days)
    "hot_window_days": "7",
    "warm_window_days": "30",
    "priority_mult_low": "0.5",
    "priority_mult_medium": "1.0",
    "priority_mult_high": "1.5",
    "priority_mult_critical": "2.0",
    # pressure overlay (utilization %)
    "pressure_l1": "80",
    "pressure_l2": "90",
    "pressure_shrink": "0.5",
    # alert thresholds (utilization %)
    "util_warn": "75",
    "util_high": "85",
    "util_critical": "90",
    "forecast_alert_days": "30",
    # capacity planning
    "overhead_pct": "10",
    "headroom_pct": "20",
    "codec_H264": "1.0",
    "codec_H265": "0.55",
    "codec_H265plus": "0.40",
    "codec_MJPEG": "3.0",
    "motion_factor": "0.35",
    # backup / DR
    "rpo_hours": "24",
    "rto_hours": "4",
    "backup_frequency_hours": "24",
    "backup_destination": "Local NAS (simulated)",
    "backup_speed_gb_per_hr": "800",
    "restore_speed_gb_per_hr": "500",
    "restore_overhead_hours": "0.25",
    # simulation
    "segments_per_day": "4",
    "sim_clock": "",
    "generated_until": "",
}

DEMO_CAMERAS = [
    # code, name, location, res, fps, codec, mode, priority, retention
    ("C01", "Camera 01", "Main Gate", "1080p", 30, "H.265", "Continuous", "High", 30),
    ("C02", "Camera 02", "Parking A", "1080p", 25, "H.264", "Continuous", "Medium", 30),
    ("C03", "Camera 03", "Parking B", "720p", 15, "H.264", "Continuous", "Low", 15),
    ("C04", "Camera 04", "Server Room", "4MP", 25, "H.265", "Continuous", "Critical", 90),
    ("C05", "Camera 05", "Library", "1080p", 20, "H.265", "Continuous", "Medium", 30),
    ("C06", "Camera 06", "Cafeteria", "720p", 15, "H.264", "Continuous", "Low", 15),
    ("C07", "Camera 07", "Lab Corridor", "1080p", 25, "H.265", "Continuous", "High", 45),
    ("C08", "Camera 08", "Admin Office", "4MP", 25, "H.265", "Continuous", "High", 60),
    ("C09", "Camera 09", "Boundary Wall", "1080p", 15, "H.264", "Continuous", "Medium", 30),
    ("C10", "Camera 10", "Hostel Gate", "1080p", 30, "H.265", "Continuous", "High", 45),
]
