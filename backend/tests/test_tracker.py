"""Document tracker: a paper document carried from office to office for signatures."""
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.documents import storage
from app.org.models import Position, PositionAssignment
from tests.conftest import make_user
from tests.orgsetup import build_org, login, notifications

JPG = b"\xff\xd8\xff" + b"0" * 20
TODAY = date.today().isoformat()


@pytest.fixture
def org(db, chair):
    return build_org(db, chair)


@pytest.fixture
def stored(monkeypatch):
    files = {}
    monkeypatch.setattr(storage, "put", lambda key, content, mime: files.update({key: (content, mime)}))
    monkeypatch.setattr(storage, "presigned_url", lambda key, name, mime, inline: f"https://files/{key}?inline={inline}")
    return files


def _new(client, assignee, steps=("AD", "ED", "PVC", "VC"), title="Venue permission for Tech Fest"):
    return client.post("/api/tracker", json={"title": title, "reference_no": "IETE/2026/14", "assigned_to": assignee.id,
                                             "steps": list(steps)})


def _record(client, doc_id, status, note=None, on=TODAY, file=None):
    return client.post(f"/api/tracker/{doc_id}/updates", data={"status": status, "happened_on": on, **({"note": note} if note else {})},
                       files={"file": file} if file else None)


def test_document_goes_through_every_signature(make_client, org, stored):
    member, carrier, chair = (login(make_client, u) for u in (org.ops_member, org.tech_member, org.chair))
    r = _new(member, org.tech_member)                      # an ordinary member adds it and assigns someone else
    assert r.status_code == 201, r.text
    doc = r.json()
    assert [s["authority"] for s in doc["steps"]] == ["AD", "ED", "PVC", "VC"]
    assert (doc["current_step"], doc["steps_signed"], doc["steps_total"]) == ("AD", 0, 4)
    assert notifications(carrier, "tracker.assigned")

    assert _record(carrier, doc["id"], "submitted").status_code == 200
    r = _record(carrier, doc["id"], "returned")
    assert r.json()["error"]["code"] == "NOTE_REQUIRED"
    assert _record(carrier, doc["id"], "returned", "AD wants the budget page signed by faculty").status_code == 200
    r = _record(carrier, doc["id"], "signed", file=("ad.jpg", JPG))
    assert r.status_code == 200, r.text
    assert (r.json()["current_step"], r.json()["steps_signed"]) == ("ED", 1)
    assert notifications(member, "tracker.updated")

    for _ in ("ED", "PVC", "VC"):
        r = _record(carrier, doc["id"], "signed")
    done = r.json()
    assert (done["status"], done["current_step"], done["steps_signed"]) == ("completed", None, 4)
    kinds = [(t["kind"], t["step"]) for t in done["timeline"]]
    assert kinds == [("created", None), ("submitted", "AD"), ("returned", "AD"), ("signed", "AD"), ("signed", "ED"),
                     ("signed", "PVC"), ("signed", "VC"), ("completed", None)]
    assert _record(carrier, doc["id"], "signed").status_code == 409

    photo = next(t for t in done["timeline"] if t["file_name"])
    assert photo["file_name"] == "ad.jpg" and len(stored) == 1
    url = chair.get(f"/api/tracker/{doc['id']}/updates/{photo['id']}/file").json()["url"]
    assert "inline=True" in url


def test_who_sees_a_document(make_client, org, db, chair):
    member, carrier, lead, vc, sec, chairc = (login(make_client, u) for u in
                                              (org.ops_member, org.tech_member, org.ops_lead, org.vc, org.secretary, org.chair))
    doc = _new(member, org.tech_member).json()
    js = make_user(db, "js@ietecu.in")
    pos = Position(title="Joint Secretary", is_lead=True)
    db.add(pos)
    db.flush()
    db.add(PositionAssignment(user_id=js.id, position_id=pos.id, valid_from=date.today(), start_reason="appointed",
                              assigned_by=chair.id))
    db.commit()
    jsc = login(make_client, js)

    for client in (member, carrier, vc, sec, chairc, jsc):
        assert client.get(f"/api/tracker/{doc['id']}").status_code == 200
    assert lead.get(f"/api/tracker/{doc['id']}").status_code == 404           # a Lead who isn't involved
    assert _record(lead, doc["id"], "submitted").status_code == 404

    assert [d["id"] for d in carrier.get("/api/tracker").json()] == [doc["id"]]
    assert lead.get("/api/tracker", params={"view": "all"}).json() == []      # "all" is only for the leaders
    assert [d["id"] for d in vc.get("/api/tracker", params={"view": "all"}).json()] == [doc["id"]]
    assert vc.get("/api/tracker/access").json() == {"sees_all": True}
    assert lead.get("/api/tracker/access").json() == {"sees_all": False}


def test_reassign_add_step_and_cancel(make_client, org):
    member, carrier, lead, vc = (login(make_client, u) for u in (org.ops_member, org.tech_member, org.ops_lead, org.vc))
    doc = _new(member, org.tech_member, steps=["AD", "VC"]).json()

    # The carrier learns another signature is needed; only the person who added it or a leader reassigns.
    r = carrier.post(f"/api/tracker/{doc['id']}/steps", json={"authority": "Dean"})
    assert [s["authority"] for s in r.json()["steps"]] == ["AD", "VC", "Dean"]
    assert carrier.put(f"/api/tracker/{doc['id']}/assignee", json={"user_id": org.ops_lead.id}).status_code == 403
    r = member.put(f"/api/tracker/{doc['id']}/assignee", json={"user_id": org.ops_lead.id})
    assert r.status_code == 200 and r.json()["assigned_to"]["id"] == org.ops_lead.id
    assert notifications(lead, "tracker.assigned")
    assert carrier.get(f"/api/tracker/{doc['id']}").status_code == 404          # no longer carrying it

    assert _record(lead, doc["id"], "submitted", on=(date.today() + timedelta(days=2)).isoformat()).json()["error"]["code"] == "FUTURE_DATE"
    assert _record(lead, doc["id"], "rejected", "AD said no outside events this month").json()["status"] == "rejected"
    assert vc.post(f"/api/tracker/{doc['id']}/cancel", json={"reason": "Too late"}).status_code == 409

    other = _new(member, org.tech_member).json()
    assert carrier.post(f"/api/tracker/{other['id']}/cancel", json={"reason": "Not needed"}).status_code == 403
    assert vc.post(f"/api/tracker/{other['id']}/cancel", json={"reason": "Event moved online"}).status_code == 204
    assert member.get(f"/api/tracker/{other['id']}").json()["status"] == "cancelled"


def test_bad_input_is_refused(make_client, org, db, stored):
    member = login(make_client, org.ops_member)
    assert member.post("/api/tracker", json={"title": "Letter", "assigned_to": org.tech_member.id,
                                             "steps": ["  "]}).json()["error"]["code"] == "STEPS_REQUIRED"
    away = make_user(db, "away@ietecu.in", status="suspended")
    r = member.post("/api/tracker", json={"title": "Letter", "assigned_to": away.id, "steps": ["AD"]})
    assert r.json()["error"]["code"] == "INVALID_PERSON"
    doc = _new(member, org.ops_member).json()
    r = _record(member, doc["id"], "signed", file=("notes.docx", b"PK\x03\x04x"))
    assert r.json()["error"]["code"] == "FILE_TYPE" and stored == {}


def test_timeline_cannot_be_changed_in_the_database(make_client, org, db):
    member = login(make_client, org.ops_member)
    _new(member, org.tech_member)
    with pytest.raises(Exception, match="cannot be changed"):
        db.execute(text("UPDATE tracked_document_updates SET note = 'edited'"))
    db.rollback()


def test_only_chairperson_and_vice_chairperson_delete(make_client, org, db):
    member, sec, vc, chair = (login(make_client, u) for u in (org.ops_member, org.secretary, org.vc, org.chair))
    first, second = _new(member, org.tech_member).json(), _new(member, org.tech_member, title="Sponsor letter").json()
    assert member.get(f"/api/tracker/{first['id']}").json()["can_delete"] is False
    for client in (member, sec):
        assert client.post(f"/api/tracker/{first['id']}/delete", json={"reason": "Duplicate"}).status_code == 403
    assert vc.post(f"/api/tracker/{first['id']}/delete", json={"reason": "Duplicate"}).status_code == 204
    assert chair.post(f"/api/tracker/{second['id']}/delete", json={"reason": "Entered by mistake"}).status_code == 204
    assert member.get(f"/api/tracker/{first['id']}").status_code == 404
    assert member.get("/api/tracker").json() == [] and vc.get("/api/tracker", params={"view": "all"}).json() == []
    # Kept in the database, with its timeline, and the deletion is audited.
    assert db.scalar(text("SELECT count(*) FROM tracked_document_updates WHERE document_id = :d"), {"d": first["id"]}) == 1
    assert db.scalar(text("SELECT count(*) FROM audit_events WHERE action = 'tracker.delete'")) == 2


def test_carrier_hands_over_and_the_next_person_accepts_first(make_client, org):
    member, carrier, lead = (login(make_client, u) for u in (org.ops_member, org.tech_member, org.ops_lead))
    doc = _new(member, org.tech_member).json()
    _record(carrier, doc["id"], "signed")                                        # AD signed

    assert member.post(f"/api/tracker/{doc['id']}/handover", json={"user_id": org.ops_lead.id}).status_code == 403
    assert lead.get(f"/api/tracker/{doc['id']}").status_code == 404              # not offered yet
    r = carrier.post(f"/api/tracker/{doc['id']}/handover", json={"user_id": org.ops_lead.id, "note": "Please take it to ED"})
    assert r.status_code == 200 and r.json()["handover"]["to"]["id"] == org.ops_lead.id
    assert carrier.post(f"/api/tracker/{doc['id']}/handover", json={"user_id": org.vc.id}).json()["error"]["code"] == "HANDOVER_PENDING"
    assert notifications(lead, "tracker.handover")

    # The offered person sees it but can't act on it until they accept; the carrier still carries it.
    offered = lead.get(f"/api/tracker/{doc['id']}").json()
    assert (offered["can_answer_handover"], offered["can_record"], offered["assigned_to"]["id"]) == (True, False, org.tech_member.id)
    assert [d["id"] for d in lead.get("/api/tracker").json()] == [doc["id"]]
    assert _record(lead, doc["id"], "submitted").status_code == 403
    assert carrier.post(f"/api/tracker/{doc['id']}/handover/answer", json={"accept": True}).status_code == 403
    assert lead.post(f"/api/tracker/{doc['id']}/handover/answer", json={"accept": False}).json()["error"]["code"] == "REASON_REQUIRED"

    assert lead.post(f"/api/tracker/{doc['id']}/handover/answer", json={"accept": True}).status_code == 204
    now = lead.get(f"/api/tracker/{doc['id']}").json()
    assert (now["assigned_to"]["id"], now["handover"], now["can_record"]) == (org.ops_lead.id, None, True)
    assert notifications(carrier, "tracker.handover_answered")
    assert carrier.get(f"/api/tracker/{doc['id']}").status_code == 404           # handed over
    assert _record(lead, doc["id"], "signed").json()["steps_signed"] == 2
    assert [t["kind"] for t in now["timeline"]][-2:] == ["handover_requested", "handover_accepted"]


def test_handover_declined_or_withdrawn_keeps_the_carrier(make_client, org):
    member, carrier, lead, vc = (login(make_client, u) for u in (org.ops_member, org.tech_member, org.ops_lead, org.vc))
    doc = _new(member, org.tech_member).json()
    carrier.post(f"/api/tracker/{doc['id']}/handover", json={"user_id": org.ops_lead.id})
    assert lead.post(f"/api/tracker/{doc['id']}/handover/answer", json={"accept": False, "reason": "Out of town"}).status_code == 204
    after = carrier.get(f"/api/tracker/{doc['id']}").json()
    assert (after["assigned_to"]["id"], after["handover"]) == (org.tech_member.id, None)
    assert lead.get(f"/api/tracker/{doc['id']}").status_code == 404

    carrier.post(f"/api/tracker/{doc['id']}/handover", json={"user_id": org.ops_lead.id})
    assert lead.post(f"/api/tracker/{doc['id']}/handover/withdraw").status_code == 403
    assert vc.post(f"/api/tracker/{doc['id']}/handover/withdraw").json()["handover"] is None
    assert lead.post(f"/api/tracker/{doc['id']}/handover/answer", json={"accept": True}).status_code == 404
    kinds = [t["kind"] for t in carrier.get(f"/api/tracker/{doc['id']}").json()["timeline"]]
    assert kinds == ["created", "handover_requested", "handover_declined", "handover_requested", "handover_withdrawn"]
