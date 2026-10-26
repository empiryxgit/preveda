from __future__ import annotations
from fastapi import APIRouter, Depends
from ...persistence import Store
from ...security import AUDIT_ROLES, Principal, require
from ..deps import get_store

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/verify")
def audit_verify(who: Principal = Depends(require(*AUDIT_ROLES)), store: Store = Depends(get_store)):
    """Re-computes the hash chain; any edited, deleted or re-ordered entry is reported."""
    return store.verify_audit()
