"""Built-in profile registry. Third-party profile loading is not implemented yet."""
from .ordinal import OrdinalProfile
from .json_transform.profile import JsonTransformProfile
from .graph_path.profile import GraphPathProfile

PROFILES = {p.profile_id: p for p in (OrdinalProfile(), JsonTransformProfile(), GraphPathProfile())}


def get_profile(profile_id):
    try:
        return PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError("unknown profile: " + profile_id) from exc
