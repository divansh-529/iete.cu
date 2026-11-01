import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.audit.models import AuditEvent
from app.documents import storage
from app.documents.folders import EVENT_FOLDERS
from tests.orgsetup import build_org, login, notifications

PDF = b"%PDF-1.7 test"
PNG = b"\x89PNG\r\n\x1a\nimage"


@pytest.fixture
def org(db, chair):
    return build_org(db, chair)


@pytest.fixture(autouse=True)
def stored(monkeypatch):
    files = {}
    monkeypatch.setattr(storage, "put", lambda key, content, mime: files.update({key: (content, mime)}))
    monkeypatch.setattr(storage, "presigned_url", lambda key, name, mime, inline: f"https://files/{key}?inline={inline}&name={name}")
    return files


def _event(client, dept):
    r = client.post("/api/events", json={"name": "Tech Fest", "department_ids": [dept.id]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _folder(client, event_id):
    r = client.get("/api/documents/folders", params={"event_id": event_id})
    assert r.status_code == 200, r.text
    return r.json()["folders"][0]["id"]


def _upload(client, folder_id, name="plan.pdf", content=PDF, title="Plan"):
    return client.post("/api/documents", data={"folder_id": folder_id, "title": title}, files={"file": (name, content)})


def test_new_event_gets_the_standard_folders(make_client, org):
    lead = login(make_client, org.ops_lead)
    event_id = _event(lead, org.ops)
    r = lead.get("/api/documents/folders", params={"event_id": event_id}).json()
    assert [f["name"] for f in r["folders"]] == list(EVENT_FOLDERS)
    assert r["can_upload"] is True


def test_upload_review_and_new_version_flow(make_client, org, stored):
    lead, vc = login(make_client, org.ops_lead), login(make_client, org.vc)
    folder = _folder(lead, _event(lead, org.ops))

    r = _upload(lead, folder)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["status"] == "draft" and doc["current_version"]["version_no"] == 1
    assert doc["current_version"]["mime_type"] == "application/pdf"
    assert len(stored) == 1

    # Uploader submits; Leadership is told and approves. The uploader can't approve their own.
    assert lead.post(f"/api/documents/{doc['id']}/review", json={"to_status": "submitted"}).status_code == 200
    assert notifications(vc, "document.submitted")[0]["payload"]["document_id"] == doc["id"]
    assert lead.post(f"/api/documents/{doc['id']}/review", json={"to_status": "approved"}).status_code == 403
    r = vc.post(f"/api/documents/{doc['id']}/review", json={"to_status": "rejected"})
    assert r.json()["error"]["code"] == "REMARKS_REQUIRED"
    r = vc.post(f"/api/documents/{doc['id']}/review", json={"to_status": "rejected", "remarks": "Wrong date"})
    assert r.json()["status"] == "rejected"
    assert notifications(lead, "document.reviewed")[0]["payload"]["remarks"] == "Wrong date"

    # A new version goes back to draft and the first one is kept.
    r = lead.post(f"/api/documents/{doc['id']}/versions", files={"file": ("plan-v2.pdf", PDF + b"2")})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "draft"
    assert [v["version_no"] for v in r.json()["versions"]] == [2, 1]
    assert len(stored) == 2

    lead.post(f"/api/documents/{doc['id']}/review", json={"to_status": "submitted"})
    assert vc.post(f"/api/documents/{doc['id']}/review", json={"to_status": "approved"}).json()["status"] == "approved"
    assert vc.post(f"/api/documents/{doc['id']}/review", json={"to_status": "final"}).json()["status"] == "final"
    r = lead.post(f"/api/documents/{doc['id']}/versions", files={"file": ("x.pdf", PDF)})
    assert r.json()["error"]["code"] == "DOCUMENT_LOCKED"


@pytest.mark.parametrize("name,content,code", [
    ("virus.exe", b"MZ", "FILE_TYPE"),
    ("fake.pdf", b"<script>", "FILE_CONTENT"),
    ("fake.png", PDF, "FILE_CONTENT"),
    ("empty.pdf", b"", "FILE_EMPTY"),
    ("big.png", PNG + b"x" * (5 * 1024 * 1024), "FILE_TOO_LARGE"),
    ("big.pdf", PDF + b"x" * (15 * 1024 * 1024), "FILE_TOO_LARGE"),
])
def test_bad_files_are_refused(make_client, org, stored, name, content, code):
    lead = login(make_client, org.ops_lead)
    r = _upload(lead, _folder(lead, _event(lead, org.ops)), name, content)
    assert r.json()["error"]["code"] == code
    assert stored == {}


def test_access_follows_the_event(make_client, org):
    lead, member, outsider = (login(make_client, u) for u in (org.ops_lead, org.ops_member, org.tech_member))
    event_id = _event(lead, org.ops)
    folder = _folder(lead, event_id)
    doc_id = _upload(lead, folder).json()["id"]

    # Same department: can read but not upload (Member role).
    assert member.get(f"/api/documents/{doc_id}").status_code == 200
    assert member.get(f"/api/documents/{doc_id}/download").json()["url"].startswith("https://files/")
    assert _upload(member, folder).status_code == 403
    assert [d["id"] for d in member.get("/api/documents").json()] == [doc_id]

    # Another department sees nothing, not even that it exists.
    assert outsider.get(f"/api/documents/{doc_id}").status_code == 404
    assert outsider.get(f"/api/documents/{doc_id}/download").status_code == 404
    assert outsider.get("/api/documents/folders", params={"event_id": event_id}).status_code == 404
    assert _upload(outsider, folder).status_code == 404
    assert outsider.get("/api/documents").json() == []

    # Joining the event's team opens it, including uploads.
    r = lead.post(f"/api/events/{event_id}/team", json={"user_id": org.tech_member.id, "event_role": "volunteer"})
    assert r.status_code < 300, r.text
    assert outsider.get(f"/api/documents/{doc_id}").status_code == 200
    assert _upload(outsider, folder).status_code == 201


def test_preview_only_for_safe_types_and_version_must_match(make_client, org):
    lead = login(make_client, org.ops_lead)
    folder = _folder(lead, _event(lead, org.ops))
    pdf, docx = _upload(lead, folder).json(), _upload(lead, folder, "a.docx", b"PK\x03\x04x").json()
    assert "inline=True" in lead.get(f"/api/documents/{pdf['id']}/download", params={"inline": True}).json()["url"]
    assert "inline=False" in lead.get(f"/api/documents/{docx['id']}/download", params={"inline": True}).json()["url"]
    other = docx["current_version"]["id"]
    assert lead.get(f"/api/documents/{pdf['id']}/download", params={"version_id": other}).status_code == 404


def test_delete_is_soft_audited_and_keeps_versions(make_client, org, db):
    lead, chair = login(make_client, org.ops_lead), login(make_client, org.chair)
    folder = _folder(lead, _event(lead, org.ops))
    doc_id = _upload(lead, folder).json()["id"]

    assert lead.delete(f"/api/documents/{doc_id}").status_code == 403
    assert chair.delete(f"/api/documents/{doc_id}").status_code == 204
    assert lead.get(f"/api/documents/{doc_id}").status_code == 404
    assert lead.get("/api/documents").json() == []
    assert db.scalar(text("SELECT count(*) FROM document_versions WHERE document_id = :d"), {"d": doc_id}) == 1
    assert db.query(AuditEvent).filter_by(action="document.delete", entity_id=doc_id).count() == 1
    # A folder that ever held a document stays.
    assert chair.delete(f"/api/documents/folders/{folder}").json()["error"]["code"] == "FOLDER_IN_USE"


def test_versions_cannot_be_changed_in_the_database(make_client, org, db):
    lead = login(make_client, org.ops_lead)
    _upload(lead, _folder(lead, _event(lead, org.ops)))
    for sql in ("UPDATE document_versions SET original_filename = 'x'", "DELETE FROM document_versions"):
        with pytest.raises(DBAPIError):
            db.execute(text(sql))
        db.rollback()


def test_forum_folders_need_a_global_grant(make_client, org):
    chair, vc, lead = login(make_client, org.chair), login(make_client, org.vc), login(make_client, org.ops_lead)
    assert chair.post("/api/documents/folders", json={"name": "Constitution"}).status_code == 204
    folder = chair.get("/api/documents/folders").json()["folders"][0]
    assert _upload(vc, folder["id"]).status_code == 201     # Leadership holds it globally
    assert lead.get("/api/documents/folders").status_code == 403
    assert _upload(lead, folder["id"]).status_code == 404
    assert vc.post("/api/documents/folders", json={"name": "Nope"}).status_code == 403
    assert chair.put(f"/api/documents/folders/{folder['id']}", json={"name": "Rules"}).status_code == 204
    assert chair.post("/api/documents/folders", json={"name": "Spare"}).status_code == 204
    spare = [f for f in chair.get("/api/documents/folders").json()["folders"] if f["name"] == "Spare"][0]
    assert chair.delete(f"/api/documents/folders/{spare['id']}").status_code == 204


def test_upload_without_storage_settings_says_so(make_client, org, monkeypatch):
    monkeypatch.undo()
    lead = login(make_client, org.ops_lead)
    r = _upload(lead, _folder(lead, _event(lead, org.ops)))
    assert r.status_code == 503 and r.json()["error"]["code"] == "STORAGE_NOT_CONFIGURED"
