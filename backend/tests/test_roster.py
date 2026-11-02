"""Leaders see the core team as a hierarchy and can download it."""
import io
from datetime import date

import pytest
from openpyxl import load_workbook

from app.audit.models import AuditEvent
from app.org.models import MemberProfile, Position, PositionAssignment
from tests.conftest import grant, make_user
from tests.orgsetup import build_org, login


@pytest.fixture
def org(db, chair):
    org = build_org(db, chair)
    db.add(MemberProfile(user_id=org.ops_member.id, uid="25BCS1", official_email="member@cumail.in", phone="9876543210",
                         branch="CSE", year_of_study=2, block="C2"))
    db.commit()
    return org


def _groups(client):
    r = client.get("/api/org/roster")
    assert r.status_code == 200, r.text
    return {g["name"]: g for g in r.json()}


def test_lead_sits_above_members_and_sees_only_their_department(make_client, org):
    lead = login(make_client, org.ops_lead)
    assert lead.get("/api/auth/me").json()["can_view_roster"] is True
    groups = _groups(lead)
    assert list(groups) == ["Operations"]
    people = groups["Operations"]["people"]
    assert [(p["name"], p["is_lead"]) for p in people] == [(org.ops_lead.full_name, True), (org.ops_member.full_name, False)]
    member = people[1]
    assert (member["email"], member["uid"], member["mobile"], member["department"], member["block"]) == (
        "member@cumail.in", "25BCS1", "9876543210", "Operations", "C2")
    # An account with no profile details yet falls back to its sign-in email.
    assert people[0]["email"] == org.ops_lead.email and people[0]["mobile"] is None

    assert lead.get("/api/org/roster/export", params={"department_id": org.tech.id}).status_code == 403
    assert lead.get("/api/org/roster/export", params={"department_id": 999999}).status_code == 404


def test_senior_leaders_see_everything(make_client, org, db, chair):
    joint = make_user(db, "js@ietecu.in")
    position = Position(title="Joint Secretary", is_lead=True)
    db.add(position)
    db.flush()
    db.add(PositionAssignment(user_id=joint.id, position_id=position.id, valid_from=date.today(), start_reason="appointed", assigned_by=chair.id))
    db.commit()
    for user in (org.chair, org.vc, org.secretary, joint):
        assert list(_groups(login(make_client, user))) == ["Leadership", "Operations", "Technical"]
    leadership = {p["position"] for p in _groups(login(make_client, org.chair))["Leadership"]["people"]}
    assert {"Vice Chairperson", "Secretary", "Joint Secretary"} <= leadership


def test_everyone_else_is_refused(make_client, org, db, chair):
    grant(db, org.tech_member, "users.view", by=chair)
    for user in (org.ops_member, org.tech_member):
        client = login(make_client, user)
        assert client.get("/api/auth/me").json()["can_view_roster"] is False
        assert client.get("/api/org/roster").status_code == 403
        assert client.get("/api/org/roster/export").status_code == 403


def test_people_who_left_drop_out(make_client, org):
    chair = login(make_client, org.chair)
    assert chair.post(f"/api/users/{org.ops_member.id}/suspend", json={"reason": "Testing"}).status_code == 200
    names = [p["name"] for p in _groups(chair)["Operations"]["people"]]
    assert org.ops_member.full_name not in names and org.ops_lead.full_name in names


def _book(response):
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
    return load_workbook(io.BytesIO(response.content))


def test_download_matches_the_format_and_is_logged(make_client, org, db):
    lead = login(make_client, org.ops_lead)
    r = lead.get("/api/org/roster/export", params={"department_id": org.ops.id})
    assert "Operations%20Members.xlsx" in r.headers["content-disposition"]
    book = _book(r)
    assert book.sheetnames == ["Operations"]
    sheet = book.active
    assert sheet["A1"].value == "Operations Team Members"
    assert "A1:G1" in [str(m) for m in sheet.merged_cells.ranges]
    assert [c.value for c in sheet[2]] == ["S.No", "Name", "Email", "Uid", "Mobile No", "Department", "Academic Block"]
    assert sheet["A2"].fill.fgColor.rgb.endswith("1F3864") and sheet["A2"].font.color.rgb.endswith("FFFFFF")
    assert sheet["A1"].fill.fgColor.rgb.endswith("D9E1F2") and sheet["A1"].font.bold
    assert sheet["A3"].value == 1 and sheet["B3"].value == org.ops_lead.full_name and sheet["B3"].font.bold
    assert [c.value for c in sheet[4]] == [2, org.ops_member.full_name, "member@cumail.in", "25BCS1", "9876543210", "Operations", "C2"]
    event = db.query(AuditEvent).filter_by(action="org.roster_export").one()
    assert event.actor_id == org.ops_lead.id and event.after["people"] == 2


def test_download_all_gives_a_sheet_each(make_client, org):
    assert _book(login(make_client, org.chair).get("/api/org/roster/export")).sheetnames == ["Leadership", "Operations", "Technical"]
    assert _book(login(make_client, org.ops_lead).get("/api/org/roster/export")).sheetnames == ["Operations"]


def test_a_name_cant_run_as_a_formula(make_client, org, db):
    org.ops_member.full_name = '=HYPERLINK("http://evil","x")'
    db.commit()
    sheet = _book(login(make_client, org.chair).get("/api/org/roster/export", params={"department_id": org.ops.id})).active
    cell = next(c for row in sheet.iter_rows(min_row=3) for c in row if str(c.value).startswith("=HYPERLINK"))
    assert cell.data_type == "s"
