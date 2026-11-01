from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import require_any, require_any_of
from app.core.config import settings
from app.core.db import get_db
from app.members import service
from app.members.models import MemberProposal
from app.members.schemas import DecisionIn, DecisionOut, ProposalOut, ProposeMemberIn
from app.users.models import User

router = APIRouter(prefix="/api", tags=["recruitment"])


def _out(db: Session, viewer: User, proposal_id: int, email_sent: bool | None = None) -> dict:
    view = service.views(db, viewer, [db.get(MemberProposal, proposal_id)])[0]
    return {"proposal": view, "email_sent": email_sent, "login_url": f"{settings.frontend_base_url}/login",
            "default_password": settings.default_member_password}


@router.get("/member-proposals", response_model=list[ProposalOut])
def list_proposals(status: Literal["pending", "decided", "all"] = "pending",
                   user: User = Depends(require_any_of("users.approve", "org.assign")), db: Session = Depends(get_db)):
    return service.views(db, user, service.list_for(db, user, status))


@router.post("/departments/{dept_id}/member-proposals", response_model=ProposalOut, status_code=201)
def propose(dept_id: int, body: ProposeMemberIn, actor: User = Depends(require_any("org.assign")),
            db: Session = Depends(get_db)):
    return service.views(db, actor, [service.propose(db, actor, dept_id, body)])[0]


@router.post("/member-proposals/{proposal_id}/approve", response_model=DecisionOut)
def approve(proposal_id: int, body: DecisionIn, actor: User = Depends(require_any("users.approve")),
            db: Session = Depends(get_db)):
    sent = service.approve(db, actor, proposal_id, body)
    return _out(db, actor, proposal_id, sent)


@router.post("/member-proposals/{proposal_id}/reject", response_model=DecisionOut)
def reject(proposal_id: int, body: DecisionIn, actor: User = Depends(require_any("users.approve")),
           db: Session = Depends(get_db)):
    service.reject(db, actor, proposal_id, body)
    return _out(db, actor, proposal_id)


@router.post("/member-proposals/{proposal_id}/send-email", response_model=DecisionOut)
def resend(proposal_id: int, actor: User = Depends(require_any("users.approve")), db: Session = Depends(get_db)):
    return _out(db, actor, proposal_id, service.resend(db, actor, proposal_id))
