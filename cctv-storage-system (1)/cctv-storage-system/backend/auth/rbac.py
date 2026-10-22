"""Role-based access control. Pure Python - enforced in the service layer AND the UI."""

ADMIN, MANAGER, VIEWER = "Admin", "Storage Manager", "Viewer"
ALL = [ADMIN, MANAGER, VIEWER]

PERMISSIONS = {
    # pages
    "dashboard": [ADMIN, MANAGER], "view_cameras": [ADMIN, MANAGER], "calculator": [ADMIN, MANAGER],
    "raid_view": [ADMIN, MANAGER], "tiers_view": [ADMIN, MANAGER], "footage_view": ALL,
    "archive_view": ALL, "backup_view": [ADMIN, MANAGER], "forecast_view": [ADMIN, MANAGER],
    "alerts_view": [ADMIN, MANAGER], "audit_view": [ADMIN], "settings_view": [ADMIN],
    # actions
    "manage_users": [ADMIN], "manage_cameras": [ADMIN], "edit_raid": [ADMIN],
    "run_lifecycle": [ADMIN, MANAGER], "edit_tiers": [ADMIN], "flag_footage": [ADMIN, MANAGER],
    "downgrade_footage": [ADMIN], "request_flag": [VIEWER], "run_backup": [ADMIN],
    "config_backup": [ADMIN], "resolve_alerts": [ADMIN, MANAGER], "edit_settings": [ADMIN],
    "simulate": [ADMIN],
}


class PermissionDenied(Exception):
    pass


def has_permission(role, perm):
    return role in PERMISSIONS.get(perm, [])


def check(user, perm):
    """Raise PermissionDenied unless `user` (dict with 'role') holds `perm`. Called by every mutating service."""
    if not user or not has_permission(user.get("role"), perm):
        raise PermissionDenied(f"Your role cannot perform '{perm}'.")
    return user
