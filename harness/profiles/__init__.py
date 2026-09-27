"""Built-in profile registry. Third-party profile loading is not implemented yet."""
from .ordinal import OrdinalProfile
from .json_transform.profile import JsonTransformProfile

PROFILES = {p.profile_id: p for p in (OrdinalProfile(), JsonTransformProfile())}


def get_profile(profile_id):
    try:
        return PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError("unknown profile: " + profile_id) from exc
