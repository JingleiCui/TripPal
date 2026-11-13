"""Adapted from Atlas (MIT), Dejan Žegarac, 2026.
Upstream efebcd9371b2b66ed538f2e57d0b8fb17d388a15.
See docs/upstream/Atlas-LICENSE and Atlas-NOTICE.md.
"""

OWNER = "owner"
EDITOR = "editor"
VIEWER = "viewer"
_MEMBER_ROLES = (VIEWER, EDITOR)


def access_role(owner_id: str | None, member_role: str | None, user_id: str | None) -> str | None:
    """The effective role a user has: 'owner' if they own the trip, else their membership role
    ('editor'/'viewer'), else None. None means no access at all."""
    if user_id and owner_id and user_id == owner_id:
        return OWNER
    if member_role in _MEMBER_ROLES:
        return member_role
    return None


def role_can_edit(role: str | None) -> bool:
    """Owners and editors may edit; viewers and non-members may not."""
    return role in (OWNER, EDITOR)


def role_can_read(role: str | None) -> bool:
    """Any granted role may read; only None (no access) is denied."""
    return role is not None
