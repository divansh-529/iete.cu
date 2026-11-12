"""Score cards: the Chairperson's rules (who scores whom, out of how much)."""
from datetime import date

import pytest

from app.audit.models import AuditEvent
from app.org.models import Position, PositionAssignment
from tests.conftest import make_user
from tests.orgsetup import build_org, login, notifications


@pytest.fixture
def org(db, chair):
    return build_org(db, chair)


def _cards(client):
    data = client.get("/api/scores/to-score").json()
    return {c["person"]["email"]: c for c in (data["cards"] if data else [])}


def _slots(card):
    return {s["slot"]: s for s in card["slots"]}


def _score(client, card, slot, points, remarks=None):
    return client.put(f"/api/scores/cards/{card['card_id']}/{slot}", json={"points": points, "remarks": remarks})


def test_round_follows_the_chairpersons_rules(make_client, org):
    chair, vc, sec, lead, member = (login(make_client, u) for u in
                                    (org.chair, org.vc, org.secretary, org.ops_lead, org.ops_member))
    assert vc.post("/api/scores/rounds", json={"title": "November 2026"}).status_code == 403
    r = chair.post("/api/scores/rounds", json={"title": "November 2026"})
    assert r.status_code == 201, r.text
    rnd = r.json()
    assert rnd["cards"] == 5 and rnd["entries_expected"] == 4 + 4 + 4 + 2 + 2   # 2 members, lead, VC, Secretary
    assert chair.post("/api/scores/rounds", json={"title": "Again"}).json()["error"]["code"] == "ROUND_OPEN"
    assert notifications(lead, "score.round_opened")

    # Each scorer sees only the cards and parts they give
    lead_cards = _cards(lead)
    assert list(lead_cards) == ["opsmember@ietecu.in"]                          # not the Technical member
    assert [s["slot"] for s in lead_cards["opsmember@ietecu.in"]["slots"] if s["editable"]] == ["lead"]
    vc_cards = _cards(vc)
    assert "vc@ietecu.in" not in vc_cards                                          # nobody scores themselves
    assert _slots(vc_cards["secretary@ietecu.in"])["vice_chair"]["max_points"] == "10"
    assert set(_slots(vc_cards["opslead@ietecu.in"])) == {"joint_secretary", "secretary", "vice_chair", "chairperson"}
    assert _slots(_cards(sec)["vc@ietecu.in"])["secretary"]["max_points"] == "10"
    assert _cards(member) == {}

    m = lead_cards["opsmember@ietecu.in"]
    assert _score(lead, m, "lead", 6).json()["error"]["code"] == "VALIDATION_ERROR"   # out of 5
    assert _score(lead, m, "secretary", 4).status_code == 403
    assert _score(lead, m, "lead", 4.5, "Reliable at events").status_code == 204
    assert _score(sec, _cards(sec)["opsmember@ietecu.in"], "secretary", 4).status_code == 204
    assert _slots(_cards(vc)["opsmember@ietecu.in"])["lead"]["points"] is None       # hidden while open
    chair_view = _cards(chair)["opsmember@ietecu.in"]
    assert _slots(chair_view)["lead"]["points"] == "4.5"                               # the Chairperson sees all
    assert _score(chair, chair_view, "chairperson", 5).status_code == 204
    assert _score(sec, _cards(sec)["vc@ietecu.in"], "secretary", 9).status_code == 204
    assert chair.get("/api/scores/leaderboard").json() == []                           # nothing published yet

    # Closing publishes each card to its person; nothing can change afterwards
    assert vc.post(f"/api/scores/rounds/{rnd['id']}/close").status_code == 403
    assert chair.post(f"/api/scores/rounds/{rnd['id']}/close").json()["status"] == "closed"
    assert notifications(member, "score.published")
    assert _score(lead, m, "lead", 5).status_code == 409
    board = {b["person"]["email"]: b for b in chair.get("/api/scores/leaderboard").json()}
    assert board["opsmember@ietecu.in"]["total"] == "13.5" and board["opsmember@ietecu.in"]["max_total"] == "20"
    assert board["vc@ietecu.in"]["total"] == "9.0"
    card = member.get(f"/api/scores/people/{org.ops_member.id}").json()["cards"][0]
    assert _slots(card)["lead"]["remarks"] == "Reliable at events" and _slots(card)["vice_chair"]["given"] is False
    # Only the Chairperson sees other people's cards and the standings.
    for client in (member, lead, vc):
        assert client.get("/api/scores/leaderboard").status_code == 403
    assert vc.get(f"/api/scores/people/{org.ops_member.id}").status_code == 403
    assert chair.get(f"/api/scores/people/{org.ops_member.id}").status_code == 200

    # A second round adds up: out of 40
    second = chair.post("/api/scores/rounds", json={"title": "December 2026"}).json()
    _score(lead, _cards(lead)["opsmember@ietecu.in"], "lead", 5)
    chair.post(f"/api/scores/rounds/{second['id']}/close")
    person = member.get(f"/api/scores/people/{org.ops_member.id}").json()
    assert (person["total"], person["max_total"], len(person["cards"])) == ("18.5", "40", 2)


def test_joint_secretary_card_and_lead_scoring(db, make_client, org, chair):
    js_pos = Position(title="Joint Secretary", is_lead=True)
    db.add(js_pos)
    db.flush()
    js = make_user(db, "js@ietecu.in")
    db.add(PositionAssignment(user_id=js.id, position_id=js_pos.id, valid_from=date.today(),
                              start_reason="appointed", assigned_by=chair.id))
    db.commit()
    chair_c, js_c = login(make_client, org.chair), login(make_client, js)
    chair_c.post("/api/scores/rounds", json={"title": "Term 1"})
    js_card = _cards(chair_c)["js@ietecu.in"]
    assert {s["slot"]: s["max_points"] for s in js_card["slots"]} == {"secretary": "7", "vice_chair": "7",
                                                                     "chairperson": "6"}
    mine = _cards(js_c)
    assert list(mine) == ["opslead@ietecu.in"]                    # the Joint Secretary scores Leads only
    assert _score(js_c, mine["opslead@ietecu.in"], "joint_secretary", 5).status_code == 204


def _published_round(chair, vc, title):
    rnd = chair.post("/api/scores/rounds", json={"title": title}).json()
    card = _cards(vc)["opsmember@ietecu.in"]
    assert _score(vc, card, "vice_chair", 4).status_code == 204
    assert chair.post(f"/api/scores/rounds/{rnd['id']}/close").status_code == 200
    return rnd


def test_chairperson_deletes_a_round_and_totals_drop(make_client, org, db):
    chair, vc = login(make_client, org.chair), login(make_client, org.vc)
    first, second = _published_round(chair, vc, "October"), _published_round(chair, vc, "November")
    row = chair.get("/api/scores/leaderboard").json()[0]
    assert float(row["total"]) == 8 and float(row["max_total"]) == 40

    body = {"reason": "Entered by mistake", "confirm": "October"}
    assert vc.post(f"/api/scores/rounds/{first['id']}/delete", json=body).status_code == 403
    r = chair.post(f"/api/scores/rounds/{first['id']}/delete", json={**body, "confirm": "Wrong"})
    assert r.json()["error"]["code"] == "CONFIRMATION_MISMATCH"
    assert chair.post(f"/api/scores/rounds/{first['id']}/delete", json=body).status_code == 204

    row = chair.get("/api/scores/leaderboard").json()[0]
    assert float(row["total"]) == 4 and float(row["max_total"]) == 20
    assert [r["id"] for r in chair.get("/api/scores/rounds").json()] == [second["id"]]
    assert chair.post(f"/api/scores/rounds/{first['id']}/delete", json=body).status_code == 404
    assert db.query(AuditEvent).filter_by(action="score.round_delete", entity_id=first["id"]).count() == 1


def test_chairperson_resets_all_scores_to_start_again(make_client, org):
    chair, vc = login(make_client, org.chair), login(make_client, org.vc)
    _published_round(chair, vc, "October")
    still_open = chair.post("/api/scores/rounds", json={"title": "November"}).json()
    card = _cards(vc)["opsmember@ietecu.in"]

    assert vc.post("/api/scores/reset", json={"reason": "No way", "confirm": "RESET"}).status_code == 403
    r = chair.post("/api/scores/reset", json={"reason": "New term", "confirm": "reset"})
    assert r.json()["error"]["code"] == "CONFIRMATION_MISMATCH"
    r = chair.post("/api/scores/reset", json={"reason": "New term", "confirm": "RESET"})
    assert r.status_code == 200 and r.json() == {"rounds_deleted": 2}

    assert chair.get("/api/scores/leaderboard").json() == []
    assert chair.get("/api/scores/rounds").json() == []
    assert chair.get("/api/scores/to-score").json() is None
    assert chair.get(f"/api/scores/people/{org.ops_member.id}").json()["total"] in (0, "0", "0.0")
    assert _score(vc, card, "vice_chair", 5).status_code == 409             # the open round is gone too
    assert chair.post(f"/api/scores/rounds/{still_open['id']}/close").status_code == 404

    # A new round starts from zero.
    _published_round(chair, vc, "December")
    row = chair.get("/api/scores/leaderboard").json()[0]
    assert float(row["total"]) == 4 and float(row["max_total"]) == 20


def test_each_person_sees_their_own_score_and_ranks(make_client, org):
    chair, vc, sec, lead, member, tech = (login(make_client, u) for u in
                                          (org.chair, org.vc, org.secretary, org.ops_lead, org.ops_member, org.tech_member))
    assert member.get("/api/scores/me").json() == {**member.get("/api/scores/me").json(), "cards": [], "ranks": [],
                                                   "category_label": None}       # nothing published yet
    rnd = chair.post("/api/scores/rounds", json={"title": "November"}).json()
    _score(lead, _cards(lead)["opsmember@ietecu.in"], "lead", 4)
    _score(sec, _cards(sec)["opsmember@ietecu.in"], "secretary", 4)
    _score(chair, _cards(chair)["techmember@ietecu.in"], "chairperson", 5)
    _score(chair, _cards(chair)["opslead@ietecu.in"], "chairperson", 3)
    _score(sec, _cards(sec)["vc@ietecu.in"], "secretary", 9)
    assert member.get("/api/scores/me").json()["cards"] == []                     # not until the round closes
    chair.post(f"/api/scores/rounds/{rnd['id']}/close")

    def ranks(client):
        return [(r["label"], r["rank"], r["out_of"]) for r in client.get("/api/scores/me").json()["ranks"]]

    mine = member.get("/api/scores/me").json()
    assert (mine["total"], mine["category_label"], len(mine["cards"])) == ("8.0", "Member", 1)
    assert ranks(member) == [("In Operations", 1, 1), ("In the IETE core team", 1, 2)]
    assert ranks(tech) == [("In Technical", 1, 1), ("In the IETE core team", 2, 2)]
    assert ranks(lead) == [("Among all Department Leads", 1, 1)]
    vc_view = vc.get("/api/scores/me").json()
    assert (vc_view["total"], vc_view["ranks"]) == ("9.0", [])                       # posts above: score only
    assert sec.get("/api/scores/me").json()["ranks"] == []

    # Equal totals share a rank.
    second = chair.post("/api/scores/rounds", json={"title": "December"}).json()
    _score(chair, _cards(chair)["techmember@ietecu.in"], "chairperson", 3)
    chair.post(f"/api/scores/rounds/{second['id']}/close")
    assert ranks(member)[1] == ranks(tech)[1] == ("In the IETE core team", 1, 2)
