"""Iteration-6 backend tests for LeadUnify.

Covers new/bug-fix features:
- FEATURE: flag/unflag-enrichment on people + needs_enrichment filter in query
- FEATURE: merge_people audit_log entry
- FEATURE: merge_companies audit_log entry (with people_moved count)
- FEATURE: /api/audit-log admin-only + ?action= filter
- REGRESSION: reset-password via PATCH /users/{id} + fresh login
- BASELINE: 20 people / 17 companies / 7 campaigns / 38 links / 1 user / 0 access / 0 audit at end
"""
import os
import time
import uuid
import pytest
import requests
from bson import ObjectId
from pymongo import MongoClient

_mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
_db = _mc[os.environ.get("DB_NAME", "leadunify")]


def _utc_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

def _load_base_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL", "")
    if not url:
        try:
            with open("/app/frontend/.env") as f:
                for ln in f:
                    if ln.startswith("REACT_APP_BACKEND_URL="):
                        url = ln.split("=", 1)[1].strip()
                        break
        except FileNotFoundError:
            pass
    return url.rstrip("/")


BASE_URL = _load_base_url()
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@leadunify.com"
ADMIN_PASSWORD = "admin123"

RUN_TAG = f"iter6_{int(time.time())}"


@pytest.fixture(scope="session")
def admin_headers():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200
    tok = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def state():
    return {}


class TestEnrichmentFlag:
    def test_a_pick_person_and_flag(self, admin_headers, state):
        r = requests.post(f"{API}/people/query", json={"page_size": 200}, headers=admin_headers, timeout=15)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) >= 1
        # pick a stable seed person (exclude any concurrent TEST_ inserts and already-flagged)
        candidate = next(
            (p for p in items
             if not p.get("enrichment_flag")
             and not (p.get("full_name") or "").startswith("TEST_")),
            items[0],
        )
        pid = candidate["id"]
        state["pid"] = pid

        fr = requests.post(f"{API}/people/{pid}/flag-enrichment", headers=admin_headers, timeout=10)
        assert fr.status_code == 200, fr.text
        body = fr.json()
        assert body.get("ok") is True
        assert body.get("flagged") is True

        # verify persisted via detail query
        det = requests.post(f"{API}/people/query", json={"search": candidate.get("primary_email") or candidate.get("full_name")}, headers=admin_headers, timeout=15)
        rows = det.json().get("items", [])
        row = [p for p in rows if p["id"] == pid][0]
        assert row.get("enrichment_flag") is True
        assert row.get("enrichment_flagged_by") == ADMIN_EMAIL
        assert row.get("enrichment_flagged_at")

    def test_b_needs_enrichment_filter(self, admin_headers, state):
        r = requests.post(f"{API}/people/query", json={"needs_enrichment": True, "limit": 100}, headers=admin_headers, timeout=15)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) >= 1
        assert any(p["id"] == state["pid"] for p in items), "flagged person missing from needs_enrichment filter"
        for p in items:
            assert p.get("enrichment_flag") is True

    def test_c_unflag(self, admin_headers, state):
        pid = state["pid"]
        ur = requests.post(f"{API}/people/{pid}/unflag-enrichment", headers=admin_headers, timeout=10)
        assert ur.status_code == 200
        assert ur.json().get("flagged") is False

        r = requests.post(f"{API}/people/query", json={"needs_enrichment": True, "limit": 100}, headers=admin_headers, timeout=15)
        items = r.json().get("items", [])
        assert not any(p["id"] == pid for p in items), "unflag did not clear filter"

    def test_d_flag_invalid_id_400(self, admin_headers):
        r = requests.post(f"{API}/people/badid/flag-enrichment", headers=admin_headers, timeout=10)
        assert r.status_code == 400

    def test_e_flag_nonexistent_404(self, admin_headers):
        # 24-char hex but random -> 404
        r = requests.post(f"{API}/people/{'0'*24}/flag-enrichment", headers=admin_headers, timeout=10)
        assert r.status_code == 404


class TestMergePeopleAudit:
    def test_a_create_two_and_merge(self, admin_headers, state):
        tag = RUN_TAG
        now = _utc_iso()
        keep_doc = {
            "full_name": f"TEST_Sarah_{tag}",
            "primary_email": f"sarah1_{tag}@test.io",
            "additional_emails": [],
            "phones": [],
            "linkedin_url": None,
            "job_title": None,
            "company_id": None,
            "company_name": "TestCo",
            "sources": ["iter6-test"],
            "created_at": now,
            "updated_at": now,
        }
        merge_doc = {
            "full_name": f"TEST_Sarah_Merged_{tag}",
            "primary_email": f"sarah2_{tag}@test.io",
            "additional_emails": [],
            "phones": ["+1-555-0100"],
            "linkedin_url": "https://linkedin.com/in/sarah-test",
            "job_title": "Tester",
            "company_id": None,
            "company_name": "TestCo",
            "sources": ["iter6-test"],
            "created_at": now,
            "updated_at": now,
        }
        keep_id = str(_db.people.insert_one(keep_doc).inserted_id)
        merge_id = str(_db.people.insert_one(merge_doc).inserted_id)

        state["keep_id"] = keep_id
        state["merge_id"] = merge_id

        m = requests.post(
            f"{API}/people/merge",
            json={"keep_person_id": keep_id, "merge_person_id": merge_id},
            headers=admin_headers, timeout=15,
        )
        assert m.status_code == 200, m.text
        assert m.json().get("ok") is True
        # merged person is deleted
        assert _db.people.find_one({"_id": ObjectId(merge_id)}) is None

    def test_b_audit_entry_created(self, admin_headers, state):
        r = requests.get(f"{API}/audit-log", params={"action": "merge_people"}, headers=admin_headers, timeout=10)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) >= 1
        entry = next((e for e in items if e.get("detail", {}).get("kept_id") == state["keep_id"]), None)
        assert entry, f"no merge_people audit entry for keep_id={state['keep_id']}"
        assert entry["action"] == "merge_people"
        assert entry["performed_by_email"] == ADMIN_EMAIL
        assert entry["detail"]["kept_name"].startswith("TEST_Sarah_")
        assert entry["detail"]["merged_name"].startswith("TEST_Sarah_Merged_")
        assert entry.get("created_at")
        state["merge_people_audit_id"] = entry["id"]

    def test_c_cleanup_kept_person(self, admin_headers, state):
        # direct DB cleanup
        _db.people.delete_one({"_id": ObjectId(state["keep_id"])})
        # also purge audit rows we created
        _db.audit_log.delete_many({"detail.kept_id": state["keep_id"]})


class TestMergeCompaniesAudit:
    def test_a_create_two_companies_with_people_and_merge(self, admin_headers, state):
        tag = RUN_TAG
        now = _utc_iso()
        keep_cid = str(_db.companies.insert_one({
            "name": f"TEST_KeepCo_{tag}", "normalized_name": f"test_keepco_{tag}".lower(),
            "created_at": now, "updated_at": now,
        }).inserted_id)
        merge_cid = str(_db.companies.insert_one({
            "name": f"TEST_MergeCo_{tag}", "normalized_name": f"test_mergeco_{tag}".lower(),
            "created_at": now, "updated_at": now,
        }).inserted_id)

        # attach two people to merge_cid
        p_ids = []
        for i in range(2):
            pid = str(_db.people.insert_one({
                "full_name": f"TEST_CoPerson{i}_{tag}",
                "primary_email": f"cop{i}_{tag}@test.io",
                "additional_emails": [], "phones": [],
                "linkedin_url": None, "job_title": None,
                "company_id": merge_cid, "company_name": f"TEST_MergeCo_{tag}",
                "sources": ["iter6-test"],
                "created_at": now, "updated_at": now,
            }).inserted_id)
            p_ids.append(pid)

        state["keep_cid"] = keep_cid
        state["merge_cid"] = merge_cid
        state["co_people_ids"] = p_ids

        m = requests.post(
            f"{API}/companies/merge",
            json={"keep_company_id": keep_cid, "merge_company_ids": [merge_cid]},
            headers=admin_headers, timeout=15,
        )
        assert m.status_code == 200, m.text
        # merged company must be deleted
        assert _db.companies.find_one({"_id": ObjectId(merge_cid)}) is None

    def test_b_audit_entry_and_filter(self, admin_headers, state):
        r = requests.get(f"{API}/audit-log", params={"action": "merge_companies"}, headers=admin_headers, timeout=10)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) >= 1
        entry = next((e for e in items if e.get("detail", {}).get("kept_id") == state["keep_cid"]), None)
        assert entry, "no merge_companies audit entry"
        assert entry["action"] == "merge_companies"
        assert entry["performed_by_email"] == ADMIN_EMAIL
        det = entry["detail"]
        assert det.get("people_moved") == 2, f"people_moved expected 2, got {det.get('people_moved')}"
        assert det.get("kept_name", "").startswith("TEST_KeepCo_")
        state["merge_co_audit_id"] = entry["id"]

        # filter must not return merge_people entries
        for e in items:
            assert e["action"] == "merge_companies"

    def test_c_cleanup(self, admin_headers, state):
        # delete the two people we created (their company_id was moved to keep_cid)
        for pid in state.get("co_people_ids", []):
            _db.people.delete_one({"_id": ObjectId(pid)})
        # delete keep company
        _db.companies.delete_one({"_id": ObjectId(state["keep_cid"])})
        # purge audit rows for this merge
        _db.audit_log.delete_many({"detail.kept_id": state["keep_cid"]})


class TestAuditLogAccessControl:
    def test_admin_can_read(self, admin_headers):
        r = requests.get(f"{API}/audit-log", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_non_admin_forbidden(self, admin_headers):
        # invite a member
        email = f"aud_member_{RUN_TAG}@test.io"
        inv = requests.post(f"{API}/users/invite", json={"email": email, "name": "AudMember", "role": "member"}, headers=admin_headers, timeout=10)
        assert inv.status_code == 200
        pw = inv.json()["temporary_password"]
        uid = inv.json()["user"]["id"]

        lg = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=10)
        assert lg.status_code == 200
        mtok = lg.json().get("access_token") or lg.json().get("token")

        r = requests.get(f"{API}/audit-log", headers={"Authorization": f"Bearer {mtok}"}, timeout=10)
        assert r.status_code == 403

        # cleanup member
        requests.delete(f"{API}/users/{uid}", headers=admin_headers, timeout=10)

    def test_unauth_401(self):
        r = requests.get(f"{API}/audit-log", timeout=10)
        assert r.status_code in (401, 403)


class TestResetPasswordRegression:
    """The bug fix: /team dialog resets password via PATCH /users/{id} {password: ...}
    which is the same API iter5 verified; here we re-verify end-to-end for the new
    Dialog flow (login with new password succeeds)."""
    def test_reset_password_flow(self, admin_headers):
        email = f"rp_{RUN_TAG}@test.io"
        inv = requests.post(f"{API}/users/invite", json={"email": email, "name": "RP", "role": "member"}, headers=admin_headers, timeout=10)
        assert inv.status_code == 200
        uid = inv.json()["user"]["id"]
        old_pw = inv.json()["temporary_password"]

        # login with initial temp pw
        assert requests.post(f"{API}/auth/login", json={"email": email, "password": old_pw}, timeout=10).status_code == 200

        new_pw = "NewPassIter6_" + uuid.uuid4().hex[:6]
        pr = requests.patch(f"{API}/users/{uid}", json={"password": new_pw}, headers=admin_headers, timeout=10)
        assert pr.status_code == 200

        # old pw no longer works
        old = requests.post(f"{API}/auth/login", json={"email": email, "password": old_pw}, timeout=10)
        assert old.status_code == 401

        # new pw works
        new = requests.post(f"{API}/auth/login", json={"email": email, "password": new_pw}, timeout=10)
        assert new.status_code == 200

        # cleanup
        requests.delete(f"{API}/users/{uid}", headers=admin_headers, timeout=10)


class TestFinalBaseline:
    """After all classes ran, purge audit_log entries created and verify seed."""
    def test_purge_audit_and_verify_baseline(self, admin_headers):
        # Wait for other workers' cleanup to complete
        deadline = time.time() + 20
        last_stats = None
        while time.time() < deadline:
            stats = requests.get(f"{API}/stats/overview", headers=admin_headers, timeout=10).json()
            last_stats = stats
            if (stats.get("total_people") == 20
                    and stats.get("total_companies") == 17
                    and stats.get("total_campaigns") == 7):
                break
            time.sleep(1)
        # Purge any leftover TEST_ people/companies + audit rows to guarantee baseline
        _db.people.delete_many({"full_name": {"$regex": "^TEST_"}})
        _db.companies.delete_many({"name": {"$regex": "^TEST_"}})
        _db.audit_log.delete_many({})
        _db.users.delete_many({"email": {"$regex": "iter6_"}})

        # There is no explicit audit-log delete endpoint via API; verify via GET
        r = requests.get(f"{API}/audit-log", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        print(f"[iter6] audit_log entries remaining after purge: {len(r.json().get('items', []))}")

        # Final baseline check
        stats = requests.get(f"{API}/stats/overview", headers=admin_headers, timeout=10).json()
        assert stats.get("total_people") == 20, f"people={stats.get('total_people')} (last:{last_stats})"
        assert stats.get("total_companies") == 17, f"companies={stats.get('total_companies')}"
        assert stats.get("total_campaigns") == 7, f"campaigns={stats.get('total_campaigns')}"

        users = requests.get(f"{API}/users", headers=admin_headers, timeout=10).json()["items"]
        assert len(users) == 1, f"users leaked: {[u['email'] for u in users]}"

        pend = requests.get(f"{API}/access-requests", headers=admin_headers, timeout=10).json()["items"]
        assert len(pend) == 0

        # Verify 38 person_campaign links baseline
        assert _db.person_campaigns.count_documents({}) == 38
