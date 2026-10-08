"""Audit event names (PRD §7.6).

Constants, not free-form strings: a typo in an event name silently breaks every report
built on it, and these values end up in a column that is indexed and queried.
"""

from __future__ import annotations

from typing import Final

LOGIN_SUCCESS: Final = "login_success"
LOGIN_FAILURE: Final = "login_failure"
ACCOUNT_LOCKED: Final = "account_locked"
LOGOUT: Final = "logout"
LOGOUT_ALL: Final = "logout_all"
TOKEN_REUSE_DETECTED: Final = "token_reuse_detected"

PASSWORD_RESET_REQUESTED: Final = "password_reset_requested"
PASSWORD_RESET_COMPLETED: Final = "password_reset_completed"
PASSWORD_CHANGED: Final = "password_changed"
PASSWORD_SETUP_COMPLETED: Final = "password_setup_completed"

USER_REGISTERED: Final = "user_registered"
USER_INVITED: Final = "user_invited"
USER_SUSPENDED: Final = "user_suspended"
USER_REACTIVATED: Final = "user_reactivated"
INVITE_RESENT: Final = "invite_resent"

ROLE_ASSIGNED: Final = "role_assigned"
ROLE_REVOKED: Final = "role_revoked"

INSTITUTE_CREATED: Final = "institute_created"
INSTITUTE_UPDATED: Final = "institute_updated"
INSTITUTE_ARCHIVED: Final = "institute_archived"
BRANCH_CREATED: Final = "branch_created"
BRANCH_UPDATED: Final = "branch_updated"
BRANCH_ARCHIVED: Final = "branch_archived"
SESSION_CREATED: Final = "session_created"
SESSION_UPDATED: Final = "session_updated"
CLASS_CREATED: Final = "class_created"
CLASS_UPDATED: Final = "class_updated"
CLASS_ARCHIVED: Final = "class_archived"

FACULTY_ASSIGNED: Final = "class_faculty_assigned"
FACULTY_REMOVED: Final = "class_faculty_removed"
STUDENT_ENROLLED: Final = "student_enrolled"
STUDENT_UNENROLLED: Final = "student_unenrolled"

MODULE_ENABLED: Final = "module_enabled"
MODULE_DISABLED: Final = "module_disabled"

# Access-control changes. These are the highest-value rows in the table: they are
# how you answer "who gave this person that power, and when?" months after the fact.
ROLE_CREATED: Final = "role_created"
ROLE_UPDATED: Final = "role_updated"
ROLE_ARCHIVED: Final = "role_archived"
PERMISSION_GRANTED: Final = "permission_granted"
PERMISSION_DENIED_SET: Final = "permission_denied_set"
PERMISSION_GRANT_REVOKED: Final = "permission_grant_revoked"
