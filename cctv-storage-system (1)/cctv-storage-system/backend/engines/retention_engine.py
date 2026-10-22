"""Class-based (importance-aware) retention rules."""
from datetime import timedelta

from backend.config.constants import FAR_FUTURE, PROTECTED_CLASSES


def is_protected(importance, legal_hold=False):
    return bool(legal_hold) or importance in PROTECTED_CLASSES


def retention_days(importance, camera_retention_days, policy):
    """Normal footage uses the camera's own retention. Other classes use the policy value but never
    less than the camera's retention (a class can only extend retention, never shorten it)."""
    cls = {"Normal": camera_retention_days, "Important": policy["important_days"],
           "Incident": policy["incident_days"], "Critical Evidence": policy["critical_days"]}[importance]
    return max(cls, camera_retention_days)


def expiry(end_time, importance, camera_retention_days, policy, legal_hold=False):
    if legal_hold:
        return FAR_FUTURE
    return end_time + timedelta(days=retention_days(importance, camera_retention_days, policy))
