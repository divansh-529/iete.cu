from datetime import date, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.audit.models import AuditEvent
from app.documents import storage
from app.org.models import Position, PositionAssignment
from tests.conftest import grant, make_user
from tests.orgsetup import build_org, login, notifications

TODAY = date.today().isoformat()


def _hold(db, user, title, by):
    position = Position(title=title)
    db.add(position)
    db.flush()
    db.add(PositionAssignment(user_id=user.id, position_id=position.id, valid_from=date.today(), start_reason="appointed", assigned_by=by.id))
    db.commit()
    return position
PDF = b"%PDF-1.7 bill"


@pytest.fixture
def org(db, chair):
    org = build_org(db, chair)
    # The Treasurer's permissions are sensitive, so they are direct grants (docs/02-permissions.md).
    for code in ("finance.view", "finance.income.record", "finance.expense.verify"):
        grant(db, org.secretary, code, by=chair)
    _hold(db, org.secretary, "Treasurer", chair)
    for code in ("finance.view", "finance.expense.approve"):
        grant(db, org.vc, code, by=chair)
    return org


def _account(client, name="Main", opening="1000.00"):
    assert client.post("/api/finance/accounts", json={"name": name, "opening_balance": opening, "opening_date": TODAY}).status_code == 204
    return next(a for a in client.get("/api/finance/accounts").json() if a["name"] == name)


def _balance(client, account):
    return float(next(a for a in client.get("/api/finance/accounts").json() if a["id"] == account["id"])["book_balance"])


def _expense(client, account, amount="500.00", **extra):
    return client.post("/api/finance/expenses", json={"account_id": account["id"], "amount": amount, "txn_date": TODAY,
                                                      "counterparty": "Print Shop", "purpose": "Posters", "payment_mode": "upi", **extra})


def _income(client, account, amount="200.00"):
    return client.post("/api/finance/income", json={"account_id": account["id"], "amount": amount, "txn_date": TODAY,
                                                    "counterparty": "Sponsor", "purpose": "Sponsorship", "payment_mode": "bank_transfer"})


def test_expense_counts_only_after_verify_and_approve(make_client, org):
    chair, treasurer, vc, lead = (login(make_client, u) for u in (org.chair, org.secretary, org.vc, org.ops_lead))
    account = _account(chair)

    r = _expense(lead, account, department_id=org.ops.id)
    assert r.status_code == 201, r.text
    tx = r.json()
    assert tx["status"] == "submitted" and tx["code"].startswith("EXP-")
    assert _balance(chair, account) == 1000
    assert notifications(treasurer, "expense.submitted")[0]["payload"]["transaction_id"] == tx["id"]

    # Approve can't skip verify.
    assert vc.post(f"/api/finance/expenses/{tx['id']}/approve").status_code == 403
    r = treasurer.post(f"/api/finance/expenses/{tx['id']}/verify")
    assert r.status_code == 200 and r.json()["status"] == "verified"
    assert notifications(vc, "expense.verified")
    assert _balance(chair, account) == 1000

    r = vc.post(f"/api/finance/expenses/{tx['id']}/approve")
    assert r.status_code == 200 and r.json()["status"] == "posted"
    assert _balance(chair, account) == 500
    assert notifications(lead, "expense.approved")


def test_nobody_verifies_or_approves_their_own_expense(make_client, org, db):
    chair, treasurer, vc = (login(make_client, u) for u in (org.chair, org.secretary, org.vc))
    account = _account(chair)
    grant(db, org.secretary, "finance.expense.submit", by=org.chair)
    own = _expense(treasurer, account).json()
    assert treasurer.post(f"/api/finance/expenses/{own['id']}/verify").status_code == 403
    assert treasurer.post(f"/api/finance/expenses/{own['id']}/reject", json={"reason": "Own one"}).status_code == 403

    # The approver can't approve their own either.
    grant(db, org.vc, "finance.expense.submit", by=org.chair)
    theirs = _expense(vc, account).json()
    assert treasurer.post(f"/api/finance/expenses/{theirs['id']}/verify").status_code == 200
    assert vc.post(f"/api/finance/expenses/{theirs['id']}/approve").status_code == 403
    assert chair.post(f"/api/finance/expenses/{theirs['id']}/approve").json()["status"] == "posted"

    # The database refuses it as well, even if the service were wrong.
    for column in ("verified_by", "approved_by"):
        with pytest.raises(DBAPIError):
            db.execute(text(f"UPDATE fin_transactions SET {column} = submitted_by WHERE id = :i"), {"i": own["id"]})
        db.rollback()


def test_large_expenses_need_the_chairperson(make_client, org):
    chair, treasurer, vc, lead = (login(make_client, u) for u in (org.chair, org.secretary, org.vc, org.ops_lead))
    account = _account(chair, opening="20000.00")
    tx = _expense(lead, account, amount="5000.01", department_id=org.ops.id).json()
    assert tx["needs_chairperson"] is True
    treasurer.post(f"/api/finance/expenses/{tx['id']}/verify")
    r = vc.post(f"/api/finance/expenses/{tx['id']}/approve")
    assert r.status_code == 403 and "Chairperson" in r.json()["error"]["message"]
    assert chair.post(f"/api/finance/expenses/{tx['id']}/approve").json()["status"] == "posted"
    # Exactly the limit doesn't.
    tx = _expense(lead, account, amount="5000.00", department_id=org.ops.id).json()
    treasurer.post(f"/api/finance/expenses/{tx['id']}/verify")
    assert vc.post(f"/api/finance/expenses/{tx['id']}/approve").json()["status"] == "posted"


def test_rejected_expense_never_counts_and_is_final(make_client, org):
    chair, treasurer, lead = (login(make_client, u) for u in (org.chair, org.secretary, org.ops_lead))
    account = _account(chair)
    tx = _expense(lead, account, department_id=org.ops.id).json()
    r = treasurer.post(f"/api/finance/expenses/{tx['id']}/reject", json={"reason": "No bill"})
    assert r.json()["status"] == "rejected" and r.json()["rejection_reason"] == "No bill"
    assert notifications(lead, "expense.rejected")[0]["payload"]["reason"] == "No bill"
    assert treasurer.post(f"/api/finance/expenses/{tx['id']}/verify").status_code == 403
    assert _balance(chair, account) == 1000


def test_who_can_see_and_submit(make_client, org):
    chair, lead, member, tech = (login(make_client, u) for u in (org.chair, org.ops_lead, org.ops_member, org.tech_member))
    account = _account(chair)
    # An ordinary member can't submit; a lead can, for their own department only.
    assert _expense(member, account, department_id=org.ops.id).status_code == 403
    assert _expense(lead, account, department_id=org.tech.id).status_code == 403
    assert _expense(lead, account).status_code == 403
    tx = _expense(lead, account, department_id=org.ops.id).json()
    # Balances and other people's records stay private.
    assert lead.get("/api/finance/accounts").status_code == 403
    assert [a["name"] for a in lead.get("/api/finance/account-names").json()] == ["Main"]
    assert tech.get("/api/finance/accounts").status_code == 403
    assert tech.get(f"/api/finance/transactions/{tx['id']}").status_code == 404
    assert tech.get("/api/finance/transactions").json() == []
    assert [t["id"] for t in lead.get("/api/finance/transactions").json()] == [tx["id"]]
    assert _income(lead, account).status_code == 403
    assert lead.post("/api/finance/accounts", json={"name": "Nope", "opening_date": TODAY}).status_code == 403


def test_posted_transactions_cannot_be_changed_only_reversed(make_client, org, db):
    chair, treasurer, vc = (login(make_client, u) for u in (org.chair, org.secretary, org.vc))
    account = _account(chair)
    r = _income(treasurer, account)
    assert r.status_code == 201 and r.json()["status"] == "posted", r.text
    tx = r.json()
    assert _balance(chair, account) == 1200

    for sql in ("UPDATE fin_transactions SET amount = 1", "DELETE FROM fin_transactions"):
        with pytest.raises(DBAPIError):
            db.execute(text(sql))
        db.rollback()

    # Whoever recorded it can't reverse it; someone who can approve can, with a reason.
    assert treasurer.post(f"/api/finance/transactions/{tx['id']}/reverse", json={"reason": "Oops"}).status_code == 403
    r = vc.post(f"/api/finance/transactions/{tx['id']}/reverse", json={"reason": "Wrong amount"})
    assert r.status_code == 200 and r.json()["reversed_by_code"].startswith("REV-")
    assert _balance(chair, account) == 1000
    assert vc.post(f"/api/finance/transactions/{tx['id']}/reverse", json={"reason": "Again"}).status_code == 403
    assert db.query(AuditEvent).filter_by(action="finance.reversal").count() == 1


def test_transfer_moves_money_and_reverses_both_sides(make_client, org):
    chair = login(make_client, org.chair)
    main, fund = _account(chair, "Main"), _account(chair, "Fund", "0.00")
    body = {"from_account_id": main["id"], "to_account_id": fund["id"], "amount": "300.00", "txn_date": TODAY, "purpose": "Event float"}
    assert chair.post("/api/finance/transfers", json={**body, "to_account_id": main["id"]}).json()["error"]["code"] == "SAME_ACCOUNT"
    r = chair.post("/api/finance/transfers", json=body)
    assert r.status_code == 201, r.text
    assert (_balance(chair, main), _balance(chair, fund)) == (700, 300)
    assert chair.post(f"/api/finance/transactions/{r.json()['id']}/reverse", json={"reason": "Not needed"}).status_code == 200
    assert (_balance(chair, main), _balance(chair, fund)) == (1000, 0)


def test_opening_balance_locks_once_used_and_dates_are_checked(make_client, org):
    chair = login(make_client, org.chair)
    account = _account(chair)
    body = {"name": "Main", "opening_balance": "5.00", "opening_date": TODAY}
    assert chair.put(f"/api/finance/accounts/{account['id']}", json=body).status_code == 204
    assert _income(chair, account).status_code == 201
    assert chair.put(f"/api/finance/accounts/{account['id']}", json={**body, "opening_balance": "9.00"}).json()["error"]["code"] == "ACCOUNT_IN_USE"
    future = (date.today() + timedelta(days=1)).isoformat()
    r = chair.post("/api/finance/income", json={"account_id": account["id"], "amount": "1.00", "txn_date": future, "counterparty": "Someone",
                                                "purpose": "Tomorrow", "payment_mode": "cash"})
    assert r.json()["error"]["code"] == "FUTURE_DATE"
    r = chair.post("/api/finance/income", json={"account_id": account["id"], "amount": "1.00", "txn_date": "2020-01-01", "counterparty": "Someone",
                                                "purpose": "Long ago", "payment_mode": "cash"})
    assert r.json()["error"]["code"] == "BEFORE_OPENING"
    assert chair.post("/api/finance/income", json={"account_id": account["id"], "amount": "-5", "txn_date": TODAY, "counterparty": "Someone",
                                                   "purpose": "Negative", "payment_mode": "cash"}).status_code == 422


def test_reconciliation_compares_statement_with_books(make_client, org, db):
    chair, lead = login(make_client, org.chair), login(make_client, org.ops_lead)
    account = _account(chair)
    _income(chair, account)
    body = {"account_id": account["id"], "period_end": TODAY, "statement_balance": "1150.00", "notes": "Bank charge"}
    assert lead.post("/api/finance/reconciliations", json=body).status_code == 403
    assert chair.post("/api/finance/reconciliations", json=body).status_code == 204
    row = chair.get("/api/finance/reconciliations").json()[0]
    assert float(row["book_balance"]) == 1200 and float(row["difference"]) == -50
    listed = next(a for a in chair.get("/api/finance/accounts").json() if a["id"] == account["id"])
    assert listed["reconciled_to"] == TODAY and float(listed["reconciled_difference"]) == -50
    assert chair.post("/api/finance/reconciliations", json=body).json()["error"]["code"] == "ALREADY_RECONCILED"
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE fin_reconciliations SET notes = 'x'"))
    db.rollback()


def test_attachments_follow_the_transaction(make_client, org, monkeypatch):
    stored = {}
    monkeypatch.setattr(storage, "put", lambda key, content, mime: stored.update({key: content}))
    monkeypatch.setattr(storage, "presigned_url", lambda key, name, mime, inline: f"https://files/{key}?inline={inline}")
    chair, lead, tech = (login(make_client, u) for u in (org.chair, org.ops_lead, org.tech_member))
    tx = _expense(lead, _account(chair), department_id=org.ops.id).json()
    url = f"/api/finance/transactions/{tx['id']}/attachments"
    assert lead.post(url, files={"file": ("bill.exe", b"MZ")}).json()["error"]["code"] == "FILE_TYPE"
    assert tech.post(url, files={"file": ("bill.pdf", PDF)}).status_code == 404
    r = lead.post(url, data={"kind": "bill"}, files={"file": ("bill.pdf", PDF)})
    assert r.status_code == 201, r.text
    attachment = r.json()["attachments"][0]
    assert attachment["kind"] == "bill" and list(stored.values()) == [PDF]
    assert "inline=True" in chair.get(f"{url}/{attachment['id']}/download", params={"inline": True}).json()["url"]
    assert tech.get(f"{url}/{attachment['id']}/download").status_code == 404


def test_membership_payment_creates_income_and_refund_reverses_it(make_client, org):
    chair, treasurer, lead = (login(make_client, u) for u in (org.chair, org.secretary, org.ops_lead))
    account = _account(chair, opening="0.00")
    assert lead.post("/api/membership/categories", json={"name": "Student", "fee": "300.00"}).status_code == 403
    assert treasurer.post("/api/membership/categories", json={"name": "Student", "fee": "300.00"}).status_code == 204
    category = treasurer.get("/api/membership/categories").json()[0]
    r = treasurer.post("/api/memberships", json={"user_id": org.ops_member.id, "category_id": category["id"]})
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["status"] == "pending" and m["membership_no"].startswith("MEM-") and m["holder_email"] == org.ops_member.email
    outsider = treasurer.post("/api/memberships", json={"holder_name": "Outside Person", "holder_email": "o@gmail.com", "category_id": category["id"]})
    assert outsider.status_code == 201, outsider.text
    assert treasurer.post("/api/memberships", json={"category_id": category["id"]}).json()["error"]["code"] == "NAME_REQUIRED"

    pay = {"account_id": account["id"], "paid_on": TODAY, "payment_mode": "upi", "payment_reference": "UPI123"}
    assert treasurer.post(f"/api/memberships/{m['id']}/pay", json=pay).status_code == 204
    assert _balance(chair, account) == 300
    assert treasurer.post(f"/api/memberships/{m['id']}/pay", json=pay).status_code == 409
    assert treasurer.post(f"/api/memberships/{m['id']}/cancelled", json={"reason": "Mistake"}).json()["error"]["code"] == "INVALID_STATE"
    assert treasurer.post(f"/api/memberships/{outsider.json()['id']}/waived", json={"reason": "Scholarship"}).status_code == 204

    summary = treasurer.get("/api/memberships/summary").json()
    assert summary["by_status"] == {"paid": 1, "waived": 1}
    assert summary["by_category"] == [{"name": "Student", "count": 2}] and float(summary["fees_collected"]) == 300

    income = next(t for t in chair.get("/api/finance/transactions").json() if t["membership_id"] == m["id"])
    assert chair.post(f"/api/finance/transactions/{income['id']}/reverse", json={"reason": "Refund"}).status_code == 200
    assert _balance(chair, account) == 0
    assert treasurer.get("/api/memberships", params={"status": "refunded"}).json()[0]["id"] == m["id"]
    assert lead.get("/api/memberships").status_code == 403


HEADER = "Name,Father Name,Membership No,Course,Year,Membership Valid Upto\n"


def _upload(client, text_or_bytes, name="members.csv"):
    content = text_or_bytes.encode() if isinstance(text_or_bytes, str) else text_or_bytes
    return client.post("/api/memberships/upload", files={"file": (name, content)})


def test_treasurer_uploads_paid_members_from_csv(make_client, org, db):
    treasurer, lead, chair = (login(make_client, u) for u in (org.secretary, org.ops_lead, org.chair))
    account = _account(chair, opening="100.00")
    body = HEADER + "Asha Rao,Ravi Rao,IETE-101,BE CSE,2,31/03/2027\nVik Das,Om Das,IETE-102,BE ECE,3,31-03-2027\n"
    assert _upload(lead, body).status_code == 403
    r = _upload(treasurer, body)
    assert r.status_code == 200, r.text
    assert r.json() == {"created": 2, "updated": 0}

    row = treasurer.get("/api/memberships", params={"q": "IETE-101"}).json()[0]
    assert (row["holder_name"], row["father_name"], row["course"], row["study_year"]) == ("Asha Rao", "Ravi Rao", "BE CSE", "2")
    assert row["status"] == "paid" and row["valid_to"] == "2027-03-31" and row["category"] is None
    # Fees collected before the portal don't touch the books.
    assert _balance(chair, account) == 100
    summary = treasurer.get("/api/memberships/summary").json()
    assert summary["by_status"] == {"paid": 2} and float(summary["fees_collected"]) == 0
    assert db.query(AuditEvent).filter_by(action="membership.upload").count() == 1

    # Uploading a renewal list updates, and an unchanged row isn't counted.
    r = _upload(treasurer, HEADER + "Asha Rao,Ravi Rao,IETE-101,BE CSE,3,31/03/2028\nVik Das,Om Das,IETE-102,BE ECE,3,31-03-2027\n")
    assert r.json() == {"created": 0, "updated": 1}
    assert treasurer.get("/api/memberships", params={"q": "IETE-101"}).json()[0]["valid_to"] == "2028-03-31"


def test_upload_reads_excel_with_real_dates_and_number_cells(make_client, org):
    import io
    from datetime import datetime

    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.append(["NAME", "FATHER NAME", "MEMBERSHIP NO", "COURSE", "YEAR", "MEMBERSHIP VALID UPTO"])
    sheet.append(["Asha Rao", "Ravi Rao", 153, "BE CSE", 2, datetime(2027, 3, 31)])
    sheet.append([None, None, None, None, None, None])
    out = io.BytesIO()
    book.save(out)
    treasurer = login(make_client, org.secretary)
    r = _upload(treasurer, out.getvalue(), "members.xlsx")
    assert r.status_code == 200 and r.json() == {"created": 1, "updated": 0}, r.text
    row = treasurer.get("/api/memberships").json()[0]
    assert (row["membership_no"], row["study_year"], row["valid_to"]) == ("153", "2", "2027-03-31")


@pytest.mark.parametrize("body,name,code,mentions", [
    ("Name,Course\nA,B\n", "m.csv", "MISSING_COLUMNS", "Father name"),
    ("", "m.csv", "FILE_EMPTY", ""),
    (HEADER, "m.csv", "FILE_EMPTY", ""),
    ("hello", "m.pdf", "FILE_TYPE", ""),
    ("not really excel", "m.xlsx", "FILE_CONTENT", ""),
])
def test_upload_refuses_bad_files(make_client, org, body, name, code, mentions):
    r = _upload(login(make_client, org.secretary), body, name).json()["error"]
    assert r["code"] == code and mentions in r["message"]


def test_upload_saves_nothing_if_any_row_is_wrong(make_client, org):
    treasurer = login(make_client, org.secretary)
    body = (HEADER + "Good Person,Dad,IETE-1,BE,1,31/03/2027\n"     # row 2 is fine
            + ",Dad,IETE-2,BE,1,31/03/2027\n"                       # no name
            + "Date Wrong,Dad,IETE-3,BE,1,soon\n"                   # bad date
            + "Same Number,Dad,IETE-1,BE,1,31/03/2027\n")           # repeated number
    r = _upload(treasurer, body).json()["error"]
    assert r["code"] == "ROWS_INVALID"
    details = {d["field"]: d["message"] for d in r["details"]}
    assert "Name is empty" in details["Row 3"] and "isn't a date" in details["Row 4"] and "also on row 2" in details["Row 5"]
    assert treasurer.get("/api/memberships").json() == []


def test_upload_wont_overwrite_a_membership_that_isnt_paid(make_client, org):
    treasurer = login(make_client, org.secretary)
    assert treasurer.post("/api/membership/categories", json={"name": "Student", "fee": "300.00"}).status_code == 204
    category = treasurer.get("/api/membership/categories").json()[0]
    pending = treasurer.post("/api/memberships", json={"holder_name": "Pending Person", "category_id": category["id"]}).json()
    r = _upload(treasurer, HEADER + f"New Name,Dad,{pending['membership_no']},BE,1,31/03/2027\n").json()["error"]
    assert r["code"] == "ROWS_INVALID"
    assert treasurer.get("/api/memberships").json()[0]["holder_name"] == "Pending Person"


def test_treasurer_adds_one_paid_member_by_hand(make_client, org):
    treasurer, lead = login(make_client, org.secretary), login(make_client, org.ops_lead)
    body = {"holder_name": "Asha Rao", "father_name": "Ravi Rao", "membership_no": "IETE-9", "course": "BE CSE",
            "study_year": "2", "valid_to": "2027-03-31"}
    assert lead.post("/api/memberships/paid", json=body).status_code == 403
    r = treasurer.post("/api/memberships/paid", json=body)
    assert r.status_code == 201 and r.json()["status"] == "paid", r.text
    assert treasurer.post("/api/memberships/paid", json=body).json()["error"]["code"] == "NUMBER_TAKEN"


def test_member_list_is_only_for_named_positions(make_client, org, db, chair):
    treasurer, chairperson, vc = (login(make_client, u) for u in (org.secretary, org.chair, org.vc))
    assert treasurer.post("/api/memberships/paid", json={"holder_name": "Asha Rao", "father_name": "Ravi Rao", "membership_no": "9",
                                                         "course": "BE", "study_year": "2", "valid_to": "2027-03-31"}).status_code == 201

    # Secretary and Vice Chair (by position) and the Chairperson can read it, but not change it.
    joint = make_user(db, "js@ietecu.in")
    _hold(db, joint, "Joint Secretary", chair)
    readers = [vc, login(make_client, joint), chairperson]
    for client in readers:
        assert client.get("/api/auth/me").json()["can_view_members"] is True
        assert [m["father_name"] for m in client.get("/api/memberships").json()] == ["Ravi Rao"]
        assert client.get("/api/memberships/summary").status_code == 200
    for client in readers[:2]:
        assert client.get("/api/auth/me").json()["can_record_members"] is False
        assert _upload(client, HEADER + "A B,C D,10,BE,1,31/03/2027\n").status_code == 403

    # Everyone else is refused, even with the permission granted directly or a Lead role.
    outsider = make_user(db, "outsider@ietecu.in")
    grant(db, outsider, "membership.view", by=chair)
    grant(db, outsider, "membership.record", by=chair)
    for user in (outsider, org.ops_lead, org.ops_member):
        client = login(make_client, user)
        assert client.get("/api/auth/me").json()["can_view_members"] is False
        for path in ("/api/memberships", "/api/memberships/summary", "/api/membership/categories"):
            assert client.get(path).status_code == 403
        assert _upload(client, HEADER + "A B,C D,10,BE,1,31/03/2027\n").status_code == 403

    # Leaving the position ends it at once, and names stay out of the audit log.
    pa = db.scalar(select(PositionAssignment).where(PositionAssignment.user_id == joint.id))
    pa.valid_to, pa.end_reason, pa.ended_by = date.today(), "resigned", chair.id
    db.commit()
    assert login(make_client, joint).get("/api/memberships").status_code == 403
    assert all("Asha" not in str(e.after) for e in db.query(AuditEvent).filter(AuditEvent.action.like("membership.%")))


def test_chairpersons_own_expense_posts_at_once_at_any_amount(make_client, org, db):
    chair, treasurer = login(make_client, org.chair), login(make_client, org.secretary)
    account = _account(chair, opening="50000.00")
    r = _expense(chair, account, amount="27012.60")
    assert r.status_code == 201, r.text
    tx = r.json()
    assert tx["status"] == "posted" and tx["needs_chairperson"] is False and tx["approved_by"] is None
    assert _balance(chair, account) == 22987.40
    assert not notifications(treasurer, "expense.submitted")
    assert db.query(AuditEvent).filter_by(action="finance.expense", entity_id=tx["id"]).count() == 1
    # Nobody else's expense skips the checks, and a correction is still a reversal.
    assert chair.post(f"/api/finance/transactions/{tx['id']}/reverse", json={"reason": "Wrong amount"}).status_code == 200
    assert _balance(chair, account) == 50000


def test_chairperson_can_clear_an_own_expense_already_waiting(make_client, org, db):
    """Expenses submitted before the rule changed were stuck: they needed the Chairperson, who can't approve their own."""
    chair, vc, treasurer = login(make_client, org.chair), login(make_client, org.vc), login(make_client, org.secretary)
    account = _account(chair, opening="50000.00")
    for amount in ("27012.60", "100.00"):
        db.execute(text("""INSERT INTO fin_transactions (code, txn_type, is_credit, account_id, amount, txn_date, purpose, status, submitted_by)
                           VALUES (:c, 'expense', false, :a, :m, CURRENT_DATE, 'Old one', 'submitted', :u)"""),
                   {"c": f"EXP-OLD-{amount}", "a": account["id"], "m": amount, "u": org.chair.id})
    db.commit()
    first, second = reversed(chair.get("/api/finance/transactions").json())
    detail = chair.get(f"/api/finance/transactions/{first['id']}").json()
    assert detail["can_approve"] is True and detail["can_reject"] is True and detail["needs_chairperson"] is False
    assert [t["id"] for t in chair.get("/api/finance/transactions", params={"view": "to_act"}).json()] == [second["id"], first["id"]]
    assert vc.post(f"/api/finance/expenses/{first['id']}/approve").status_code == 403       # still not for anyone else
    r = chair.post(f"/api/finance/expenses/{first['id']}/approve")
    assert r.json()["status"] == "posted" and r.json()["approved_by"] is None
    assert _balance(chair, account) == 22987.40
    assert chair.post(f"/api/finance/expenses/{second['id']}/reject", json={"reason": "Duplicate"}).json()["status"] == "rejected"
    assert treasurer.get(f"/api/finance/transactions/{first['id']}").status_code == 200
