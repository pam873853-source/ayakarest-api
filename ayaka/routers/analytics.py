from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import Principal, require
from ..responses import ok
from ..services import analytics

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/analytics")
def user_analytics(p: Principal = Depends(require("analytics:read"))):
    return ok(analytics.build(p.user_id), "Analytics loaded")
