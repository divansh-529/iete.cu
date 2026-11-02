"""The Treasurer and Joint Secretary manage finances by position, what they record waits for the
Chairperson, and they can appeal a rejection with documents only they can upload."""
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.documents import storage
from app.org.models import Position, PositionAssignment
from tests.conftest import make_user
from tests.orgsetup import build_org, login, notifications

TODAY = date.today().isoformat()
PDF = b"%PDF-1.7 bill"


def _hold(db, user, title, by):
    position = Position(title=title)
    db.add(position)
    db.flush()
    db.add(PositionAssignment(user_id=user.id, position_id=position.id, valid_from=date.today(), start_reason="appointed", assigned_by=by.id))
    db.commit()


def _end_position(db, user, by):
    pa = db.scalar(select(PositionAssignment).where(PositionAssignment.user_id == user.id, PositionAssignment.valid_to.is_(None)))
    pa.valid_to, pa.end_reason, pa.ended_by = date.today(), "resigned", by.id
    db.commit()


@pytest.fixture
def org(db, chair, monkeypatch):
    org = build_org(db, chair)
    org.treasurer, org.joint = make_user(db, "treasurer@ietecu.in"), make_user(db, "joint@ietecu.in")
    _hold(db, org.treasurer, "Treasurer", chair)
    _hold(db, org.joint, "Joint Secretary", chair)
    monkeypatch.setattr(storage, "put", lambda key, content, mime: None)
    monkeypatch.setattr(storage, "presigned_url", lambda key, name, mime, inline: f"https://files/{key}")
    return org


def _account(client, name="Main", opening="1000.00"):
    r = client.post("/api/finance/accounts", json={"name": name, "opening_balance": opening, "opening_date": TODAY})
    assert r.status_code == 204, r.text
    return next(a for a in client.get("/api/finance/accounts").json() if a["name"] == name)


def _balance(client, account):
    return float(next(a for a in client.get("/api/finance/accounts").json() if a["id"] == account["id"])["book_balance"])


def _money(client, path, account, amount="500.00"):
    return client.post(path, json={"account_id": account["id"], "amount": amount, "txn_date": TODAY, "counterparty": "Print Shop",
                                   "purpose": "Standee", "payment_mode": "upi"})


def _appeal(client, tx_id, note="Bills are attached now", files=None):
    files = [("files", ("bill.pdf", PDF))] if files is None else files
    return client.post(f"/api/finance/transactions/{tx_id}/appeal", data={"note": note}, files=files)


def _rejected(chair, keeper, account, reason="Attach the bills"):
    tx = _money(keeper, "/api/finance/expenses", account).json()
    assert chair.post(f"/api/finance/expenses/{tx['id']}/reject", json={"reason": reason}).status_code == 200
    return tx["id"]


@pytest.mark.parametrize("who", ["treasurer", "joint"])
def test_powers_come_with_the_position_and_end_with_it(make_client, org, db, chair, who):
    person = getattr(org, who)
    client = login(make_client, person)
    me = client.get("/api/auth/me").json()
    assert {"finance.view", "finance.expense.verify", "finance.accounts.manage"} <= {p["code"] for p in me["permissions"]}
    assert "finance.expense.approve" not in {p["code"] for p in me["permissions"]}
    assert me["can_record_members"] is True
    account = _account(client)
    assert client.get("/api/finance/reconciliations").status_code == 200
    assert client.post("/api/finance/reconciliations", json={"account_id": account["id"], "period_end": TODAY,
                                                             "statement_balance": "1000.00"}).status_code == 204

    _end_position(db, person, chair)
    assert client.get("/api/finance/accounts").status_code == 403
    assert client.get("/api/auth/me").json()["can_record_members"] is False


@pytest.mark.parametrize("who, path", [("treasurer", "/api/finance/expenses"), ("treasurer", "/api/finance/income"),
                                       ("joint", "/api/finance/expenses"), ("joint", "/api/finance/income")])
def test_their_money_waits_for_the_chairperson_alone(make_client, org, who, path):
    chair, keeper = login(make_client, org.chair), login(make_client, getattr(org, who))
    other = login(make_client, org.joint if who == "treasurer" else org.treasurer)
    account = _account(chair)
    r = _money(keeper, path, account)
    assert r.status_code == 201, r.text
    tx = r.json()
    assert tx["status"] == "submitted" and tx["for_chairperson"] is True
    assert _balance(chair, account) == 1000
    assert notifications(chair, "entry.waiting")[0]["payload"]["transaction_id"] == tx["id"]

    # Neither can clear their own or each other's, and there is no verify step.
    for client in (keeper, other):
        assert client.post(f"/api/finance/expenses/{tx['id']}/verify").status_code == 403
        assert client.post(f"/api/finance/expenses/{tx['id']}/approve").status_code == 403
        assert client.post(f"/api/finance/expenses/{tx['id']}/reject", json={"reason": "Not ok"}).status_code == 403
    assert tx["id"] in [t["id"] for t in chair.get("/api/finance/transactions", params={"view": "to_act"}).json()]
    assert tx["id"] not in [t["id"] for t in other.get("/api/finance/transactions", params={"view": "to_act"}).json()]

    r = chair.post(f"/api/finance/expenses/{tx['id']}/approve")
    assert r.status_code == 200 and r.json()["status"] == "posted", r.text
    assert _balance(chair, account) == (500 if "expenses" in path else 1500)


def test_vice_chair_with_approve_still_cant_clear_their_expense(make_client, org, db, chair):
    from tests.conftest import grant
    grant(db, org.vc, "finance.expense.approve", by=chair)
    grant(db, org.vc, "finance.view", by=chair)
    boss, vc, keeper = login(make_client, org.chair), login(make_client, org.vc), login(make_client, org.treasurer)
    tx = _money(keeper, "/api/finance/expenses", _account(boss)).json()
    assert vc.post(f"/api/finance/expenses/{tx['id']}/approve").status_code == 403
    assert vc.post(f"/api/finance/expenses/{tx['id']}/reject", json={"reason": "Not ok"}).status_code == 403


def test_a_transfers_two_sides_move_together(make_client, org):
    chair, keeper = login(make_client, org.chair), login(make_client, org.treasurer)
    main, fund = _account(chair), _account(chair, "Fund", "0.00")
    body = {"from_account_id": main["id"], "to_account_id": fund["id"], "amount": "300.00", "txn_date": TODAY, "purpose": "Move money"}
    tx = keeper.post("/api/finance/transfers", json=body)
    assert tx.status_code == 201 and tx.json()["status"] == "submitted", tx.text
    assert (_balance(chair, main), _balance(chair, fund)) == (1000, 0)

    # Only one side asks for action, and rejecting or appealing either side moves both.
    waiting = chair.get("/api/finance/transactions", params={"view": "to_act"}).json()
    assert [t["txn_type"] for t in waiting] == ["transfer_out"]
    assert chair.post(f"/api/finance/expenses/{tx.json()['id']}/reject", json={"reason": "Wrong amount"}).status_code == 200
    legs = [t for t in chair.get("/api/finance/transactions").json() if t["txn_type"].startswith("transfer")]
    assert {t["status"] for t in legs} == {"rejected"} and len(legs) == 2
    other_side = next(t["id"] for t in legs if t["txn_type"] == "transfer_in")
    assert _appeal(keeper, other_side).status_code == 201
    assert {t["status"] for t in chair.get("/api/finance/transactions", params={"status": "appealed"}).json()} == {"appealed"}
    r = chair.post(f"/api/finance/expenses/{other_side}/approve")
    assert r.status_code == 200 and r.json()["attachments"], r.text
    assert (_balance(chair, main), _balance(chair, fund)) == (700, 300)


def test_membership_fees_still_post_at_once(make_client, org):
    chair, keeper = login(make_client, org.chair), login(make_client, org.treasurer)
    account = _account(chair)
    assert keeper.post("/api/membership/categories", json={"name": "Student", "fee": "300.00"}).status_code == 204
    category = keeper.get("/api/membership/categories").json()[0]
    m = keeper.post("/api/memberships", json={"holder_name": "Asha Rao", "category_id": category["id"]}).json()
    pay = {"account_id": account["id"], "paid_on": TODAY, "payment_mode": "upi"}
    assert keeper.post(f"/api/memberships/{m['id']}/pay", json=pay).status_code == 204
    assert _balance(chair, account) == 1300


def test_appeal_needs_a_note_and_a_document_from_the_submitter(make_client, org):
    chair, keeper, other = login(make_client, org.chair), login(make_client, org.treasurer), login(make_client, org.joint)
    tx_id = _rejected(chair, keeper, _account(chair))
    detail = keeper.get(f"/api/finance/transactions/{tx_id}").json()
    assert detail["can_appeal"] is True and detail["can_attach"] is False

    assert _appeal(keeper, tx_id, note="x").json()["error"]["code"] == "NOTE_REQUIRED"
    assert keeper.post(f"/api/finance/transactions/{tx_id}/appeal", data={"note": "No files here"}).status_code == 422
    too_many = [("files", (f"b{i}.pdf", PDF)) for i in range(6)]
    assert _appeal(keeper, tx_id, files=too_many).json()["error"]["code"] == "DOCUMENTS_REQUIRED"
    assert _appeal(keeper, tx_id, files=[("files", ("bill.exe", b"MZ"))]).json()["error"]["code"] == "FILE_TYPE"
    assert keeper.get(f"/api/finance/transactions/{tx_id}").json()["status"] == "rejected"

    # Not the other keeper, and not the Chairperson.
    assert _appeal(other, tx_id).status_code == 403
    assert _appeal(chair, tx_id).status_code == 403
    r = _appeal(keeper, tx_id)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "appealed" and r.json()["appeals"][0]["rejection_reason"] == "Attach the bills"
    assert r.json()["attachments"][0]["kind"] == "proof"
    assert _appeal(keeper, tx_id).status_code == 403      # already under appeal


def test_a_leads_rejected_expense_cant_be_appealed(make_client, org):
    chair, lead = login(make_client, org.chair), login(make_client, org.ops_lead)
    tx = lead.post("/api/finance/expenses", json={"account_id": _account(chair)["id"], "amount": "100.00", "txn_date": TODAY, "counterparty": "Shop",
                                                  "purpose": "Posters", "payment_mode": "upi", "department_id": org.ops.id}).json()
    assert chair.post(f"/api/finance/expenses/{tx['id']}/reject", json={"reason": "No bill"}).status_code == 200
    assert lead.get(f"/api/finance/transactions/{tx['id']}").json()["can_appeal"] is False
    assert _appeal(lead, tx["id"]).status_code == 403
    r = lead.post(f"/api/finance/transactions/{tx['id']}/attachments", files={"file": ("bill.pdf", PDF)})
    assert r.status_code == 403


def test_only_the_person_appealing_uploads_and_leaders_read_and_comment(make_client, org):
    chair, keeper = login(make_client, org.chair), login(make_client, org.treasurer)
    lead, vc, secretary, member = (login(make_client, u) for u in (org.ops_lead, org.vc, org.secretary, org.ops_member))
    joint = login(make_client, org.joint)
    tx_id = _rejected(chair, keeper, _account(chair))
    url = f"/api/finance/transactions/{tx_id}"
    assert lead.get(url).status_code == 404      # nothing to see until it is appealed
    assert _appeal(keeper, tx_id).status_code == 201

    for client in (lead, vc, secretary, joint, chair):
        assert notifications(client, "appeal.submitted")
        assert tx_id in [t["id"] for t in client.get("/api/finance/transactions", params={"view": "appeals"}).json()]
        detail = client.get(url).json()
        assert detail["can_comment"] is True and detail["can_attach"] is False
        attachment = detail["attachments"][0]["id"]
        assert client.get(f"{url}/attachments/{attachment}/download").status_code == 200
        assert client.post(f"{url}/attachments", files={"file": ("x.pdf", PDF)}).status_code == 403
    # Reading the appeal doesn't open up the books.
    assert lead.get("/api/finance/accounts").status_code == 403
    assert lead.get("/api/finance/transactions").json() == []

    assert lead.post(f"{url}/appeal/comments", json={"body": "The bill looks right"}).status_code == 201
    assert notifications(chair, "appeal.comment") and notifications(keeper, "appeal.comment")
    assert keeper.post(f"{url}/attachments", files={"file": ("more.pdf", PDF)}).status_code == 201

    # Nobody but the Chairperson decides.
    for client in (lead, vc, secretary, joint, keeper):
        assert client.post(f"/api/finance/expenses/{tx_id}/approve").status_code == 403
        assert client.post(f"/api/finance/expenses/{tx_id}/reject", json={"reason": "Not ok"}).status_code == 403

    # An ordinary member sees none of it.
    assert member.get(url).status_code == 404
    assert member.post(f"{url}/appeal/comments", json={"body": "Hello"}).status_code == 404
    assert member.get("/api/finance/transactions", params={"view": "appeals"}).json() == []


def test_decisions_post_or_reject_again_and_every_round_is_kept(make_client, org):
    chair, keeper = login(make_client, org.chair), login(make_client, org.treasurer)
    account = _account(chair)
    tx_id = _rejected(chair, keeper, account)
    assert _appeal(keeper, tx_id).status_code == 201
    assert _balance(chair, account) == 1000

    r = chair.post(f"/api/finance/expenses/{tx_id}/reject", json={"reason": "Wrong bill"})
    assert r.json()["status"] == "rejected" and r.json()["rejection_reason"] == "Wrong bill"
    assert notifications(keeper, "appeal.rejected")[0]["payload"]["reason"] == "Wrong bill"
    assert _balance(chair, account) == 1000

    assert _appeal(keeper, tx_id, note="Here is the right bill").status_code == 201
    assert keeper.post(f"/api/finance/transactions/{tx_id}/appeal/comments", json={"body": "Please check"}).status_code == 201
    r = chair.post(f"/api/finance/expenses/{tx_id}/approve")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "posted" and body["rejection_reason"] is None and body["approved_by"]["id"] == org.chair.id
    assert _balance(chair, account) == 500
    assert notifications(keeper, "appeal.approved")

    first, second = body["appeals"]
    assert (first["rejection_reason"], first["outcome"], first["decision_note"]) == ("Attach the bills", "rejected", "Wrong bill")
    assert (second["rejection_reason"], second["outcome"]) == ("Wrong bill", "approved")
    assert second["comments"][0]["body"] == "Please check"
    assert len(body["attachments"]) == 2
    assert body["can_appeal"] is False and body["can_comment"] is False


def test_a_rejected_entry_can_only_go_under_appeal(make_client, org, db):
    chair, keeper = login(make_client, org.chair), login(make_client, org.treasurer)
    tx_id = _rejected(chair, keeper, _account(chair))
    for sql in ("UPDATE fin_transactions SET status = 'posted' WHERE id = :i",
                "UPDATE fin_transactions SET amount = 1 WHERE id = :i",
                "UPDATE fin_transactions SET status = 'appealed', amount = 1 WHERE id = :i",
                "DELETE FROM fin_transactions WHERE id = :i"):
        with pytest.raises(DBAPIError):
            db.execute(text(sql), {"i": tx_id})
        db.rollback()
    db.execute(text("UPDATE fin_transactions SET status = 'appealed' WHERE id = :i"), {"i": tx_id})
    db.commit()
    assert _appeal(keeper, tx_id).status_code == 403      # and an entry under appeal takes no second appeal


def test_someone_who_left_the_position_cant_appeal(make_client, org, db, chair):
    boss, keeper = login(make_client, org.chair), login(make_client, org.treasurer)
    tx_id = _rejected(boss, keeper, _account(boss))
    _end_position(db, org.treasurer, chair)
    assert _appeal(keeper, tx_id).status_code == 403


def test_team_accounts_go_by_position_only(make_client, org, db, chair):
    from tests.conftest import grant
    for user in (org.chair, org.vc, org.joint):
        client = login(make_client, user)
        assert client.get("/api/auth/me").json()["can_view_accounts"] is True
        assert client.get("/api/users").status_code == 200
        assert client.get(f"/api/users/{org.ops_member.id}").status_code == 200

    # Everyone else, even with the actions granted directly or by following a link.
    grant(db, org.secretary, "users.create", by=chair)
    for user in (org.secretary, org.treasurer, org.ops_lead, org.ops_member):
        client = login(make_client, user)
        assert client.get("/api/auth/me").json()["can_view_accounts"] is False
        assert client.get("/api/users").status_code == 403
        assert client.get(f"/api/users/{org.ops_member.id}").status_code == 403
        assert client.post("/api/users", json={"email": "a@gmail.com", "full_name": "Aa Bb", "credential": "invite"}).status_code == 403

    # Seeing the page gives no actions; those keep their own permissions.
    vc = login(make_client, org.vc)
    assert vc.post("/api/users", json={"email": "a@gmail.com", "full_name": "Aa Bb", "credential": "invite"}).status_code == 403
    grant(db, org.vc, "users.create", by=chair)
    assert vc.post("/api/users", json={"email": "a@gmail.com", "full_name": "Aa Bb", "credential": "invite"}).status_code == 201

    # The retired permission is gone from the access screens, and the position ends it.
    assert "users.view" not in {p["code"] for p in login(make_client, org.chair).get("/api/permissions").json()}
    joint = login(make_client, org.joint)
    _end_position(db, org.joint, chair)
    assert joint.get("/api/users").status_code == 403
