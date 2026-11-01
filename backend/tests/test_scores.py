"""Score cards: the Chairperson's rules (who scores whom, out of how much)."""
from datetime import date

import pytest

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
    assert member.get("/api/scores/leaderboard").json() == []                          # nothing published yet

    # Closing publishes to everyone; nothing can change afterwards
    assert vc.post(f"/api/scores/rounds/{rnd['id']}/close").status_code == 403
    assert chair.post(f"/api/scores/rounds/{rnd['id']}/close").json()["status"] == "closed"
    assert notifications(member, "score.published")
    assert _score(lead, m, "lead", 5).status_code == 409
    board = {b["person"]["email"]: b for b in member.get("/api/scores/leaderboard").json()}
    assert board["opsmember@ietecu.in"]["total"] == "13.5" and board["opsmember@ietecu.in"]["max_total"] == "20"
    assert board["vc@ietecu.in"]["total"] == "9.0"
    card = member.get(f"/api/scores/people/{org.ops_member.id}").json()["cards"][0]
    assert _slots(card)["lead"]["remarks"] == "Reliable at events" and _slots(card)["vice_chair"]["given"] is False

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
