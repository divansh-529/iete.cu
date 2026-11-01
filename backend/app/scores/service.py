"""Score rounds: open, score, close and publish. See models.py and rules.py.

Who is scored, and as what, is decided when the round opens, from the positions people hold:
Vice Chairperson, Secretary and Joint Secretary by their leadership position, Leads by holding a
department's Lead position, everyone else in a department as a Member. The Chairperson is not
scored. A slot is filled by whoever currently holds that role (for 'lead': a Lead of the card's
department). Nobody scores their own card.

While a round is open, scorers see only their own entries (the Chairperson sees everything), so
early marks don't sway others. Once closed, every card is published to the whole team.
"""
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.errors import AppError, forbidden, not_found
from app.core.time import utcnow
from app.notifications.service import notify
from app.org.models import Department, DepartmentMembership, Position, PositionAssignment, Term
from app.org.service import department_names, people_by_id
from app.scores.models import ScoreCard, ScoreEntry, ScoreRound
from app.scores.rules import CATEGORY_LABELS, LEADERSHIP_TITLES, ROUND_MAX, RULES, SLOT_LABELS
from app.scores.schemas import EntryIn, RoundIn
from app.users.models import User


# ---------------------------------------------------------------- roles

def _held(db: Session) -> dict[int, list[Position]]:
    """Current position(s) of every person."""
    rows = db.execute(select(PositionAssignment.user_id, Position)
                      .join(Position, Position.id == PositionAssignment.position_id)
                      .where(PositionAssignment.valid_to.is_(None), Position.status == "active")).all()
    held: dict[int, list[Position]] = defaultdict(list)
    for user_id, pos in rows:
        held[user_id].append(pos)
    return held


def _roles(positions: list[Position]) -> set[str]:
    """Leadership roles ('chairperson', 'vice_chair', ...) held through these positions."""
    return {LEADERSHIP_TITLES[p.title.strip().lower()] for p in positions
            if p.department_id is None and p.title.strip().lower() in LEADERSHIP_TITLES}


def _classify(user: User, positions: list[Position], first_dept: int | None) -> tuple[str, int | None] | None:
    roles = _roles(positions)
    if user.is_super_admin or "chairperson" in roles:
        return None
    for role in ("vice_chair", "secretary", "joint_secretary"):
        if role in roles:
            return role, None
    lead_of = [p.department_id for p in positions if p.department_id and p.is_lead]
    if lead_of:
        return "lead", lead_of[0]
    return ("member", first_dept) if first_dept else None


def _can_fill(user: User, positions: list[Position], card: ScoreCard, slot: str) -> bool:
    if card.user_id == user.id:
        return False
    if slot == "chairperson":
        return user.is_super_admin or "chairperson" in _roles(positions)
    if slot == "lead":
        return any(p.department_id == card.department_id and p.is_lead for p in positions)
    return slot in _roles(positions)


def _require_chair(user: User) -> None:
    if not user.is_super_admin:
        raise forbidden("Only the Chairperson manages scoring rounds.")


# ---------------------------------------------------------------- rounds

def open_round(db: Session, actor: User, body: RoundIn) -> ScoreRound:
    _require_chair(actor)
    if db.scalar(select(ScoreRound.id).where(ScoreRound.status == "open")):
        raise AppError(409, "ROUND_OPEN", "A scoring round is already open. Close it first.")
    rnd = ScoreRound(title=body.title.strip(), opened_by=actor.id,
                     term_id=db.scalar(select(Term.id).where(Term.is_current.is_(True))))
    db.add(rnd)
    db.flush()
    held = _held(db)
    first_dept = {}
    for user_id, dept_id in db.execute(select(DepartmentMembership.user_id, DepartmentMembership.department_id)
                                       .join(Department, Department.id == DepartmentMembership.department_id)
                                       .where(DepartmentMembership.valid_to.is_(None), Department.status == "active")
                                       .order_by(DepartmentMembership.valid_from, DepartmentMembership.id)):
        first_dept.setdefault(user_id, dept_id)
    cards = []
    for user in db.scalars(select(User).where(User.user_type == "team", User.status.in_(("active", "invited")))):
        kind = _classify(user, held.get(user.id, []), first_dept.get(user.id))
        if kind:
            cards.append(ScoreCard(round_id=rnd.id, user_id=user.id, category=kind[0], department_id=kind[1]))
    if not cards:
        raise AppError(409, "NOBODY_TO_SCORE", "Nobody holds a position or belongs to a department yet.")
    db.add_all(cards)
    db.flush()
    scorers = {u for u, positions in held.items()
               if any(_can_fill(_Stub(u), positions, c, s) for c in cards for s in RULES[c.category])}
    audit.record(db, actor.id, "score.round_open", "score_round", rnd.id,
                 after={"title": rnd.title, "cards": len(cards)})
    notify(db, scorers, "score.round_opened", {"round_id": rnd.id, "title": rnd.title}, actor.id)
    db.commit()
    return rnd


class _Stub:
    """Just enough of a User for _can_fill when only the id is known."""
    is_super_admin = False

    def __init__(self, user_id: int):
        self.id = user_id


def close_round(db: Session, actor: User, round_id: int) -> ScoreRound:
    _require_chair(actor)
    rnd = db.get(ScoreRound, round_id)
    if rnd is None or rnd.status == "deleted":
        raise not_found("Scoring round")
    if rnd.status != "open":
        raise AppError(409, "INVALID_STATE", "This round is already closed.")
    rnd.status, rnd.closed_by, rnd.closed_at = "closed", actor.id, utcnow()
    people = list(db.scalars(select(ScoreCard.user_id).where(ScoreCard.round_id == rnd.id)))
    audit.record(db, actor.id, "score.round_close", "score_round", rnd.id, after={"title": rnd.title})
    notify(db, people, "score.published", {"round_id": rnd.id, "title": rnd.title}, actor.id)
    db.commit()
    return rnd


def _delete_rounds(db: Session, actor: User, rows: list[ScoreRound], reason: str) -> None:
    """Takes rounds off every screen, so their scores stop counting. The rows stay, marked deleted,
    so the audit log's record of what was removed can still be checked."""
    progress = _progress(db, [r.id for r in rows])
    for r in rows:
        before = {"title": r.title, "status": r.status, "cards": progress[r.id][0], "entries_given": progress[r.id][1]}
        r.status = "deleted"
        audit.record(db, actor.id, "score.round_delete", "score_round", r.id, before=before, after={"reason": reason})


def delete_round(db: Session, actor: User, round_id: int, reason: str, confirm: str) -> None:
    _require_chair(actor)
    rnd = db.get(ScoreRound, round_id)
    if rnd is None or rnd.status == "deleted":
        raise not_found("Scoring round")
    if confirm.strip().lower() != rnd.title.lower():
        raise AppError(422, "CONFIRMATION_MISMATCH", f"Type the round's name, “{rnd.title}”, to confirm.")
    _delete_rounds(db, actor, [rnd], reason)
    db.commit()


def reset_scores(db: Session, actor: User, reason: str, confirm: str) -> int:
    """Every round goes, including one still open, so everyone starts again from zero."""
    _require_chair(actor)
    if confirm.strip() != "RESET":
        raise AppError(422, "CONFIRMATION_MISMATCH", "Type RESET to confirm.")
    rows = list(db.scalars(select(ScoreRound).where(ScoreRound.status != "deleted")))
    _delete_rounds(db, actor, rows, reason)
    db.commit()
    return len(rows)


def _progress(db: Session, round_ids: list[int]) -> dict[int, tuple[int, int, int]]:
    """round_id -> (cards, entries given, entries expected)."""
    if not round_ids:
        return {}
    cards = db.execute(select(ScoreCard.round_id, ScoreCard.category).where(ScoreCard.round_id.in_(round_ids))).all()
    given = dict(db.execute(select(ScoreCard.round_id, func.count(ScoreEntry.id))
                            .join(ScoreEntry, ScoreEntry.card_id == ScoreCard.id)
                            .where(ScoreCard.round_id.in_(round_ids)).group_by(ScoreCard.round_id)).all())
    out = {}
    for rid in round_ids:
        mine = [c for r, c in cards if r == rid]
        out[rid] = (len(mine), given.get(rid, 0), sum(len(RULES[c]) for c in mine))
    return out


def rounds(db: Session) -> list[dict]:
    rows = list(db.scalars(select(ScoreRound).where(ScoreRound.status != "deleted")
                           .order_by(ScoreRound.opened_at.desc(), ScoreRound.id.desc())))
    progress = _progress(db, [r.id for r in rows])
    return [{"id": r.id, "title": r.title, "status": r.status, "opened_at": r.opened_at, "closed_at": r.closed_at,
             "cards": progress[r.id][0], "entries_given": progress[r.id][1], "entries_expected": progress[r.id][2]}
            for r in rows]


# ---------------------------------------------------------------- scoring

def _card_view(card: ScoreCard, people: dict, depts: dict, entries: list[ScoreEntry], visible_slots,
               editable_slots=()) -> dict:
    by_slot = {e.slot: e for e in entries}
    slots = []
    for slot, maximum in RULES[card.category].items():
        e = by_slot.get(slot)
        show = slot in visible_slots
        slots.append({"slot": slot, "label": SLOT_LABELS[slot], "max_points": maximum,
                      "points": e.points if e and show else None, "remarks": e.remarks if e and show else None,
                      "scored_by": people.get(e.scored_by) if e and show else None,
                      "given": e is not None, "editable": slot in editable_slots})
    shown = [s["points"] for s in slots if s["points"] is not None]
    return {"card_id": card.id, "person": people[card.user_id], "category": card.category,
            "category_label": CATEGORY_LABELS[card.category],
            "department": {"id": card.department_id, "name": depts[card.department_id]} if card.department_id else None,
            "slots": slots, "total": sum(shown, Decimal(0)), "max_total": ROUND_MAX}


def to_score(db: Session, user: User) -> dict | None:
    """The open round, with the cards this person scores (the Chairperson sees every card)."""
    rnd = db.scalar(select(ScoreRound).where(ScoreRound.status == "open"))
    if rnd is None:
        return None
    mine = _held(db).get(user.id, [])
    cards = list(db.scalars(select(ScoreCard).where(ScoreCard.round_id == rnd.id)))
    entries = defaultdict(list)
    for e in db.scalars(select(ScoreEntry).join(ScoreCard, ScoreCard.id == ScoreEntry.card_id)
                        .where(ScoreCard.round_id == rnd.id)):
        entries[e.card_id].append(e)
    people = people_by_id(db, [c.user_id for c in cards] + [e.scored_by for es in entries.values() for e in es])
    depts = department_names(db, [c.department_id for c in cards])
    views = []
    for c in cards:
        editable = [s for s in RULES[c.category] if _can_fill(user, mine, c, s)]
        if not editable and not user.is_super_admin:
            continue
        visible = RULES[c.category] if user.is_super_admin else editable
        views.append(_card_view(c, people, depts, entries[c.id], visible, editable))
    views.sort(key=lambda v: (v["category"] != "member", v["department"]["name"] if v["department"] else "",
                              v["person"]["full_name"]))
    mine_slots = [s for v in views for s in v["slots"] if s["editable"]]
    return {"round": next(r for r in rounds(db) if r["id"] == rnd.id), "cards": views,
            "my_given": sum(1 for s in mine_slots if s["given"]), "my_expected": len(mine_slots)}


def save_entry(db: Session, user: User, card_id: int, slot: str, body: EntryIn) -> None:
    card = db.get(ScoreCard, card_id)
    if card is None:
        raise not_found("Score card")
    rnd = db.get(ScoreRound, card.round_id)
    if rnd.status != "open":
        raise AppError(409, "INVALID_STATE", "This round is closed; scores can no longer change.")
    maximum = RULES[card.category].get(slot)
    if maximum is None:
        raise not_found("Score")
    if not _can_fill(user, _held(db).get(user.id, []), card, slot):
        raise forbidden("You don't give this part of this person's score.")
    if body.points > maximum:
        raise AppError(422, "VALIDATION_ERROR", f"This part is out of {maximum}.")
    entry = db.scalar(select(ScoreEntry).where(ScoreEntry.card_id == card.id, ScoreEntry.slot == slot))
    before = {"points": str(entry.points), "remarks": entry.remarks} if entry else None
    if entry is None:
        entry = ScoreEntry(card_id=card.id, slot=slot, max_points=maximum)
        db.add(entry)
    entry.points, entry.remarks, entry.scored_by = body.points, (body.remarks or "").strip() or None, user.id
    audit.record(db, user.id, "score.save", "score_card", card.id, before=before,
                 after={"slot": slot, "points": str(body.points), "remarks": entry.remarks})
    db.commit()


# ---------------------------------------------------------------- published results

def _published(db: Session, user_id: int | None = None):
    stmt = (select(ScoreCard, ScoreRound).join(ScoreRound, ScoreRound.id == ScoreCard.round_id)
            .join(User, User.id == ScoreCard.user_id)
            .where(ScoreRound.status == "closed", User.status != "deleted"))
    if user_id is not None:
        stmt = stmt.where(ScoreCard.user_id == user_id)
    return db.execute(stmt.order_by(ScoreRound.closed_at.desc(), ScoreRound.id.desc())).all()


def leaderboard(db: Session) -> list[dict]:
    rows = _published(db)
    totals = dict(db.execute(select(ScoreEntry.card_id, func.sum(ScoreEntry.points))
                             .where(ScoreEntry.card_id.in_([c.id for c, _ in rows] or [0]))
                             .group_by(ScoreEntry.card_id)).all())
    people = people_by_id(db, {c.user_id for c, _ in rows})
    depts = department_names(db, [c.department_id for c, _ in rows])
    board: dict[int, dict] = {}
    for card, rnd in rows:                       # newest round first: its role is the person's latest
        b = board.setdefault(card.user_id, {
            "person": people[card.user_id], "category_label": CATEGORY_LABELS[card.category],
            "department": depts.get(card.department_id), "rounds": 0, "total": Decimal(0), "max_total": Decimal(0),
            "latest": totals.get(card.id, Decimal(0))})
        b["rounds"] += 1
        b["total"] += totals.get(card.id, Decimal(0))
        b["max_total"] += ROUND_MAX
    return sorted(board.values(), key=lambda b: (-b["total"], b["person"]["full_name"]))


def person(db: Session, user_id: int) -> dict:
    user = db.get(User, user_id)
    if user is None or user.user_type != "team" or user.status == "deleted":
        raise not_found("Person")
    rows = _published(db, user_id)
    entries = defaultdict(list)
    for e in db.scalars(select(ScoreEntry).where(ScoreEntry.card_id.in_([c.id for c, _ in rows] or [0]))):
        entries[e.card_id].append(e)
    people = people_by_id(db, [user_id] + [e.scored_by for es in entries.values() for e in es])
    depts = department_names(db, [c.department_id for c, _ in rows])
    cards = [{**_card_view(c, people, depts, entries[c.id], RULES[c.category]), "round_id": r.id,
              "round_title": r.title, "closed_at": r.closed_at} for c, r in rows]
    return {"person": people[user_id], "cards": cards,
            "total": sum((c["total"] for c in cards), Decimal(0)), "max_total": ROUND_MAX * len(cards)}
