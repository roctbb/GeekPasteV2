"""Cache author names from signed logins and the CodingProjects user API."""
import logging
import time

import requests

from codingprojects_users import fetch_user_name
from models import UserProfile, db


logger = logging.getLogger(__name__)
_lookup_retry_at = 0


def remember_user_name(user_id, name):
    remember_user_names({user_id: name})


def remember_user_names(names):
    names = {user_id: ' '.join(name.split())[:255] for user_id, name in names.items()
             if isinstance(name, str) and name.strip()}
    if not names:
        return
    profiles = {profile.id: profile for profile in db.session.execute(
        db.select(UserProfile).where(UserProfile.id.in_(names))
    ).scalars()}
    changed = False
    for user_id, name in names.items():
        profile = profiles.get(user_id)
        if profile is None:
            db.session.add(UserProfile(id=user_id, name=name))
            changed = True
        elif profile.name != name:
            profile.name = name
            changed = True
    if changed:
        db.session.commit()


def load_user_names(user_ids):
    """Load known names and resolve each missing user through the service API."""
    global _lookup_retry_at
    user_ids = {user_id for user_id in user_ids if user_id is not None}
    if not user_ids:
        return {}
    names = dict(db.session.execute(
        db.select(UserProfile.id, UserProfile.name).where(UserProfile.id.in_(user_ids))
    ).all())
    if time.monotonic() < _lookup_retry_at:
        return names
    resolved = {}
    for user_id in sorted(user_ids - names.keys()):
        try:
            name = fetch_user_name(user_id)
        except (requests.RequestException, ValueError):
            # An older CodingProjects deployment or an outage must not break solution pages.
            _lookup_retry_at = time.monotonic() + 60
            logger.warning('Could not retrieve user names from CodingProjects')
            break
        if name:
            resolved[user_id] = name
    remember_user_names(resolved)
    names.update({user_id: ' '.join(name.split())[:255] for user_id, name in resolved.items()})
    return names
