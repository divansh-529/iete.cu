"""The core team as a hierarchy, each department's Lead above its members, and the same list as an
Excel file. It holds phone numbers, so it goes by the position held: a department Lead sees their own
department, and the Joint Secretary, Secretary, Vice Chairperson and Chairperson see every department."""
import io
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.errors import forbidden, not_found
from app.org.models import Department, DepartmentMembership, MemberProfile, Position, PositionAssignment
from app.users.models import User

ALL_DEPARTMENTS_POSITIONS = {"Joint Secretary", "Secretary", "Vice Chairperson", "Chairperson"}
ACCOUNTS_POSITIONS = {"Joint Secretary", "Vice Chairperson", "Chairperson"}
SHOWN_STATUSES = ("active", "invited")      # not suspended, deactivated, deleted or still proposed
COLUMNS = (("S.No", 7), ("Name", 26), ("Email", 34), ("Uid", 16), ("Mobile No", 16), ("Department", 26), ("Academic Block", 16))
TITLE_FILL, HEADER_FILL = PatternFill("solid", fgColor="D9E1F2"), PatternFill("solid", fgColor="1F3864")
THIN = Side(style="thin", color="8EA9DB")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _held(db: Session, user: User) -> list[Position]:
    return list(db.scalars(select(Position).join(PositionAssignment, PositionAssignment.position_id == Position.id).where(
        PositionAssignment.user_id == user.id, PositionAssignment.valid_to.is_(None), Position.status == "active")))


def sees_all(db: Session, user: User) -> bool:
    return user.is_super_admin or any(p.title in ALL_DEPARTMENTS_POSITIONS for p in _held(db, user))


def led_departments(db: Session, user: User) -> set[int]:
    return {p.department_id for p in _held(db, user) if p.is_lead and p.department_id}


def can_view_roster(db: Session, user: User) -> bool:
    return sees_all(db, user) or bool(led_departments(db, user))


def can_view_accounts(db: Session, user: User) -> bool:
    """Team accounts, by position only (the Chairperson's rule). Each action on an account also needs its own permission."""
    return user.is_super_admin or any(p.title in ACCOUNTS_POSITIONS for p in _held(db, user))


def _person(user: User, profile: MemberProfile | None, department: str, position: str | None, lead: bool) -> dict:
    return {"user_id": user.id, "name": user.full_name, "email": (profile.official_email if profile else None) or user.email,
            "uid": profile.uid if profile else None, "mobile": profile.phone if profile else None, "department": department,
            "block": profile.block if profile else None, "position": position, "is_lead": lead}


def groups(db: Session, user: User) -> list[dict]:
    everything = sees_all(db, user)
    led = led_departments(db, user)
    if not everything and not led:
        raise forbidden()
    users = {u.id: u for u in db.scalars(select(User).where(User.user_type == "team", User.status.in_(SHOWN_STATUSES)))}
    profiles = {p.user_id: p for p in db.scalars(select(MemberProfile))}
    holdings = db.execute(select(Position, PositionAssignment.user_id)
                          .join(PositionAssignment, PositionAssignment.position_id == Position.id)
                          .where(PositionAssignment.valid_to.is_(None), Position.status == "active")
                          .order_by(Position.rank_order, Position.title)).all()
    out = []
    if everything:
        rows = [_person(users[uid], profiles.get(uid), "Leadership", p.title, True)
                for p, uid in holdings if p.department_id is None and uid in users]
        out.append({"id": None, "name": "Leadership", "people": rows})
    memberships = db.execute(select(DepartmentMembership.department_id, DepartmentMembership.user_id)
                             .where(DepartmentMembership.valid_to.is_(None))).all()
    for dept in db.scalars(select(Department).where(Department.status == "active").order_by(Department.name)):
        if not everything and dept.id not in led:
            continue
        leads, titles = [], {}
        for p, uid in holdings:
            if p.department_id != dept.id or uid not in users:
                continue
            if p.is_lead:
                leads.append(_person(users[uid], profiles.get(uid), dept.name, p.title, True))
            else:
                titles.setdefault(uid, p.title)
        lead_ids = {r["user_id"] for r in leads}
        ids = {uid for d, uid in memberships if d == dept.id and uid in users} | set(titles)
        members = sorted((_person(users[uid], profiles.get(uid), dept.name, titles.get(uid), False) for uid in ids - lead_ids),
                         key=lambda r: r["name"].lower())
        out.append({"id": dept.id, "name": dept.name, "people": leads + members})
    return out


def _sheet_name(name: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", name).strip()[:28] or "Team"
    title, n = base, 2
    while title.lower() in used:
        title, n = f"{base} {n}", n + 1
    used.add(title.lower())
    return title


def _write(sheet, group: dict) -> None:
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(COLUMNS))
    title = sheet.cell(row=1, column=1, value=f"{group['name']} Team Members")
    title.font, title.fill = Font(bold=True, size=14), TITLE_FILL
    title.alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = 30
    for col, (heading, width) in enumerate(COLUMNS, start=1):
        sheet.cell(row=1, column=col).border = BOX
        cell = sheet.cell(row=2, column=col, value=heading)
        cell.font, cell.fill, cell.border = Font(bold=True, color="FFFFFF"), HEADER_FILL, BOX
        cell.alignment = Alignment(horizontal="center", vertical="center")
        sheet.column_dimensions[cell.column_letter].width = width
    for number, person in enumerate(group["people"], start=1):
        values = (person["name"], person["email"], person["uid"], person["mobile"], person["department"], person["block"])
        sheet.cell(row=number + 2, column=1, value=number).border = BOX
        for col, value in enumerate(values, start=2):
            cell = sheet.cell(row=number + 2, column=col, value=value or "")
            cell.data_type = "s"     # always text, so a name starting with = can't run as a formula
            cell.border = BOX
            cell.font = Font(bold=person["is_lead"])
    sheet.freeze_panes = "A3"


def export(db: Session, actor: User, department_id: int | None) -> tuple[bytes, str]:
    """One sheet for a department, or a sheet for each group the person can see."""
    visible = groups(db, actor)
    if department_id is not None:
        visible = [g for g in visible if g["id"] == department_id]
        if not visible:
            if db.get(Department, department_id) is None:
                raise not_found("Department")
            raise forbidden()
    book = Workbook()
    book.remove(book.active)
    used: set[str] = set()
    for group in visible:
        _write(book.create_sheet(_sheet_name(group["name"], used)), group)
    out = io.BytesIO()
    book.save(out)
    label = visible[0]["name"] if department_id is not None else "Core Team"
    audit.record(db, actor.id, "org.roster_export", "department", department_id,
                 after={"list": label, "people": sum(len(g["people"]) for g in visible)})
    db.commit()
    return out.getvalue(), f"{label} Members.xlsx"
