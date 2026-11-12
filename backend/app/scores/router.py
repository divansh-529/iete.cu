from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import require_in_service
from app.core.db import get_db
from app.core.errors import not_found
from app.scores import service
from app.scores.schemas import (DeleteRoundIn, EntryIn, LeaderboardRow, MyScoresOut, PersonScoresOut, ResetOut, RoundIn,
                                RoundOut, ToScoreOut)
from app.users.models import User

router = APIRouter(prefix="/api/scores", tags=["scores"])

# The Chairperson's rules, not grants, decide who does what here: each person sees their own
# published score cards and ranks, scorers are whoever holds the scoring roles, and only the
# Chairperson opens and closes rounds and sees everyone's results. So routes only require a signed-in user; the service enforces the rest.


def _team(user: User) -> User:
    if user.user_type != "team":
        raise not_found("Page")
    return user


@router.get("/rounds", response_model=list[RoundOut])
def list_rounds(user: User = Depends(require_in_service("points.view")), db: Session = Depends(get_db)):
    _team(user)
    return service.rounds(db)


@router.post("/rounds", response_model=RoundOut, status_code=201)
def open_round(body: RoundIn, actor: User = Depends(require_in_service("points.approve")), db: Session = Depends(get_db)):
    rnd = service.open_round(db, actor, body)
    return next(r for r in service.rounds(db) if r["id"] == rnd.id)


@router.post("/rounds/{round_id}/close", response_model=RoundOut)
def close_round(round_id: int, actor: User = Depends(require_in_service("points.approve")),
                db: Session = Depends(get_db)):
    service.close_round(db, actor, round_id)
    return next(r for r in service.rounds(db) if r["id"] == round_id)


@router.post("/rounds/{round_id}/delete", status_code=204)
def delete_round(round_id: int, body: DeleteRoundIn, actor: User = Depends(require_in_service("points.approve")),
                 db: Session = Depends(get_db)):
    service.delete_round(db, actor, round_id, body.reason, body.confirm)


@router.post("/reset", response_model=ResetOut)
def reset(body: DeleteRoundIn, actor: User = Depends(require_in_service("points.approve")),
          db: Session = Depends(get_db)):
    return {"rounds_deleted": service.reset_scores(db, actor, body.reason, body.confirm)}


@router.get("/to-score", response_model=ToScoreOut | None)
def to_score(user: User = Depends(require_in_service("points.evaluate")), db: Session = Depends(get_db)):
    return service.to_score(db, _team(user))


@router.put("/cards/{card_id}/{slot}", status_code=204)
def save_entry(card_id: int, slot: str, body: EntryIn, user: User = Depends(require_in_service("points.evaluate")),
               db: Session = Depends(get_db)):
    service.save_entry(db, _team(user), card_id, slot, body)


@router.get("/leaderboard", response_model=list[LeaderboardRow])
def leaderboard(user: User = Depends(require_in_service("points.leaderboard.view")), db: Session = Depends(get_db)):
    _team(user)
    return service.leaderboard(db, user)


@router.get("/me", response_model=MyScoresOut)
def my_scores(user: User = Depends(require_in_service("points.view")), db: Session = Depends(get_db)):
    return service.my_scores(db, _team(user))


@router.get("/people/{user_id}", response_model=PersonScoresOut)
def person(user_id: int, user: User = Depends(require_in_service("points.view")), db: Session = Depends(get_db)):
    _team(user)
    return service.person(db, user, user_id)
