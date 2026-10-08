"""The ``/api/v1`` router. Every module router is mounted here and nowhere else.

Order matters in one place: ``users_router`` declares ``/roles/catalogue`` before the
``/{user_id}`` routes inside its own module, so a literal path is never swallowed by the
UUID parameter.
"""

from fastapi import APIRouter

from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.org.router import branches_router, classes_router, institutes_router
from app.modules.rbac.router import grants_router, permissions_router, roles_router
from app.modules.search.router import router as search_router
from app.modules.users.router import me_router
from app.modules.users.router import router as users_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(me_router, prefix="/me", tags=["me"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(institutes_router, prefix="/institutes", tags=["organisation"])
api_router.include_router(branches_router, prefix="/branches", tags=["organisation"])
api_router.include_router(classes_router, prefix="/classes", tags=["organisation"])
api_router.include_router(roles_router, prefix="/roles", tags=["access control"])
api_router.include_router(permissions_router, prefix="/permissions", tags=["access control"])
api_router.include_router(grants_router, prefix="/users", tags=["access control"])
api_router.include_router(search_router, prefix="/search", tags=["search"])
api_router.include_router(audit_router, prefix="/audit-logs", tags=["audit"])
