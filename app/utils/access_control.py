from functools import wraps

from flask import abort
from flask_login import current_user


def role_required(*role_slugs):
    """Restrict a view to users with one of the specified roles."""
    if not role_slugs:
        raise ValueError('At least one role slug is required.')

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or (
                not current_user.has_role('admin') and not any(
                    current_user.has_role(role_slug) for role_slug in role_slugs
                )
            ):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def permission_required(permission_slug):
    """Restrict a view to users whose role grants the specified permission."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if (
                not current_user.is_authenticated
                or not current_user.has_permission(permission_slug)
            ):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
