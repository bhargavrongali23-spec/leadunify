"""Iteration 9 — LeadUnify backend tests for:
- cascade cleanup (bulk-delete, single-delete, delete-by-filter)
- self-healing duplicate flags
- DELETE /companies/{id}, DELETE /campaigns/{id}
- 3-tier role system (owner > admin > member)
- seed idempotence (owner role stays 'owner')

NOTE: This test file INTENTIONALLY wipes and restarts the backend to reseed
demo data at the end (see conftest teardown at bottom).
"""
import os
import uuid
import time
import subprocess
import pytest
import requests
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@leadunify.com"
ADMIN_PASSWORD = "admin123"
RUN_ID = uuid.uuid4().hex[:8]

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "leadunify")
_mongo = MongoClient(MONGO_URL)
raw_db = _mongo[DB_NAME]


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _import_csv(owner_token, rows, company_name=None, campaign_id=None):
    """rows = list of (name, email, company_name_str). Imports via CSV. Returns
    (person_ids, company_id_of_last_row)."""
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {owner_token}"})
    csv_lines = ["name,email,company"]
    for name, email, comp in rows:
        csv_lines.append(f"{name},{email},{comp}")
    csv_bytes = ("\n".join(csv_lines) + "\n").encode()
    prev = sess.post(
        f"{BASE_URL}/api/import/preview",
        files={"file": ("s.csv", csv_bytes, "text/csv")},
    )
    assert prev.status_code == 200, prev.text
    token = prev.json()["token"]
    mapping = {"full_name": "name", "primary_email": "email", "company_name": "company"}
    body = {"token": token, "mapping": mapping}
    if campaign_id:
        body["campaign_id"] = campaign_id
    else:
        body["new_campaign_name"] = f"TEST_iter9_camp_{uuid.uuid4().hex[:6]}"
    commit = sess.post(f"{BASE_URL}/api/import/commit", json=body)
    assert commit.status_code == 200, commit.text
    # Query back — use company_name if given, else search by first email
    if company_name:
        q = requests.post(
            f"{BASE_URL}/api/people/query", headers=_hdr(owner_token),
            json={"company_name": company_name, "limit": 500},
        )
    else:
        q = requests.post(
            f"{BASE_URL}/api/people/query", headers=_hdr(owner_token),
            json={"search": rows[0][1], "limit": 500},
        )
    assert q.status_code == 200, q.text
    items = q.json()["items"]
    pids = [p["id"] for p in items]
    cid = items[0].get("company_id") if items else None
    return pids, cid


@pytest.fixture(scope="module")
def owner_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def admin_user(owner_token):
    """Create a fresh admin user for testing 3-tier role rules."""
    email = f"test_iter9_admin_{RUN_ID}@leadunify.com"
    pwd = "Testpass123!"
    r = requests.post(
        f"{BASE_URL}/api/users/invite",
        headers=_hdr(owner_token),
        json={"email": email, "role": "admin", "password": pwd, "name": f"IT9Admin {RUN_ID}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    return {"id": data["user"]["id"], "email": email, "password": pwd, "token": _login(email, pwd)}


@pytest.fixture(scope="module")
def member_user(owner_token):
    email = f"test_iter9_member_{RUN_ID}@leadunify.com"
    pwd = "Testpass123!"
    r = requests.post(
        f"{BASE_URL}/api/users/invite",
        headers=_hdr(owner_token),
        json={"email": email, "role": "member", "password": pwd, "name": f"IT9Member {RUN_ID}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    return {"id": data["user"]["id"], "email": email, "password": pwd, "token": _login(email, pwd)}


# ------------------------------------------------------------------
# 1. Owner role & seed idempotence
# ------------------------------------------------------------------
class TestOwnerRole:
    def test_auth_me_returns_owner_role(self, owner_token):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=_hdr(owner_token))
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "owner", f"expected role='owner', got {data['role']!r}"

    def test_seed_did_not_downgrade_owner(self):
        u = raw_db.users.find_one({"email": ADMIN_EMAIL})
        assert u is not None
        assert u["role"] == "owner"


# ------------------------------------------------------------------
# 2. DELETE /companies/{cid} — RBAC + unlink behaviour
# ------------------------------------------------------------------
class TestDeleteCompany:
    def _seed_company_with_people(self, owner_token):
        cname = f"TEST_iter9_delco_{RUN_ID}_{uuid.uuid4().hex[:5]}"
        # Import 2 people via CSV — company is auto-created from company_name column
        pids, cid = _import_csv(
            owner_token,
            [
                (f"IT9 DelCo A {RUN_ID}", f"it9delcoa_{RUN_ID}@example.com", cname),
                (f"IT9 DelCo B {RUN_ID}", f"it9delcob_{RUN_ID}@example.com", cname),
            ],
            cname,
        )
        assert cid is not None, f"company {cname} not created"
        assert len(pids) == 2
        return cid, cname, pids

    def test_owner_can_delete_company_with_people_unlink(self, owner_token):
        cid, cname, pids = self._seed_company_with_people(owner_token)
        r = requests.delete(f"{BASE_URL}/api/companies/{cid}", headers=_hdr(owner_token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["people_unlinked"] == 2
        # Company gone
        g = requests.get(f"{BASE_URL}/api/companies/{cid}", headers=_hdr(owner_token))
        assert g.status_code == 404
        # People still exist but with company null
        for pid in pids:
            pr = requests.get(f"{BASE_URL}/api/people/{pid}", headers=_hdr(owner_token))
            assert pr.status_code == 200, pr.text
            pd = pr.json()
            assert pd.get("company_id") in (None, "")
            assert pd.get("company_name") in (None, "")
        # Cleanup — remove the orphan people we created
        for pid in pids:
            requests.delete(f"{BASE_URL}/api/people/{pid}", headers=_hdr(owner_token))

    def test_member_cannot_delete_company(self, owner_token, member_user):
        # create a throwaway company via CSV import
        cname = f"TEST_iter9_memfail_{RUN_ID}"
        _, cid = _import_csv(
            owner_token,
            [(f"MemFail {RUN_ID}", f"memfail_{RUN_ID}@example.com", cname)],
            cname,
        )
        assert cid
        rd = requests.delete(f"{BASE_URL}/api/companies/{cid}", headers=_hdr(member_user["token"]))
        assert rd.status_code == 403
        # cleanup
        requests.delete(f"{BASE_URL}/api/companies/{cid}", headers=_hdr(owner_token))

    def test_invalid_company_id_returns_400_or_404(self, owner_token):
        r1 = requests.delete(f"{BASE_URL}/api/companies/not-an-oid", headers=_hdr(owner_token))
        assert r1.status_code in (400, 404)
        # valid-format-but-not-found
        fake_oid = str(ObjectId())
        r2 = requests.delete(f"{BASE_URL}/api/companies/{fake_oid}", headers=_hdr(owner_token))
        assert r2.status_code == 404


# ------------------------------------------------------------------
# 3. DELETE /campaigns/{cid} — RBAC + cascade
# ------------------------------------------------------------------
class TestDeleteCampaign:
    def _seed_campaign_with_link_and_column(self, owner_token):
        # campaign
        cname = f"TEST_iter9_delcamp_{RUN_ID}_{uuid.uuid4().hex[:5]}"
        r = requests.post(f"{BASE_URL}/api/campaigns", headers=_hdr(owner_token), json={"name": cname, "category": "Cold"})
        assert r.status_code == 200
        cid = r.json()["id"]
        # add a custom column
        cc = requests.post(f"{BASE_URL}/api/campaigns/{cid}/columns", headers=_hdr(owner_token), json={"name": "Notes", "kind": "text"})
        assert cc.status_code == 200, cc.text
        # seed a person + link via CSV
        pids, _ = _import_csv(
            owner_token,
            [(f"IT9 DelCamp {RUN_ID}", f"it9delcamp_{RUN_ID}@example.com", f"TEST_iter9_dcp_{RUN_ID}")],
            f"TEST_iter9_dcp_{RUN_ID}",
            campaign_id=cid,
        )
        assert len(pids) >= 1
        return cid, pids[0]

    def test_owner_can_delete_campaign_and_cascade(self, owner_token):
        cid, pid = self._seed_campaign_with_link_and_column(owner_token)
        # Sanity — link exists
        pc_before = raw_db.person_campaigns.count_documents({"campaign_id": cid})
        assert pc_before >= 1
        cols_before = raw_db.campaign_columns.count_documents({"campaign_id": cid})
        assert cols_before >= 1
        # Delete
        rd = requests.delete(f"{BASE_URL}/api/campaigns/{cid}", headers=_hdr(owner_token))
        assert rd.status_code == 200
        assert rd.json()["ok"] is True
        # Campaign gone; person still exists; links + columns gone
        g = requests.get(f"{BASE_URL}/api/campaigns/{cid}", headers=_hdr(owner_token))
        assert g.status_code in (404, 400)
        pr = requests.get(f"{BASE_URL}/api/people/{pid}", headers=_hdr(owner_token))
        assert pr.status_code == 200
        assert raw_db.person_campaigns.count_documents({"campaign_id": cid}) == 0
        assert raw_db.campaign_columns.count_documents({"campaign_id": cid}) == 0
        # cleanup
        requests.delete(f"{BASE_URL}/api/people/{pid}", headers=_hdr(owner_token))

    def test_member_cannot_delete_campaign(self, owner_token, member_user):
        cname = f"TEST_iter9_delmemfail_{RUN_ID}"
        r = requests.post(f"{BASE_URL}/api/campaigns", headers=_hdr(owner_token), json={"name": cname})
        cid = r.json()["id"]
        rd = requests.delete(f"{BASE_URL}/api/campaigns/{cid}", headers=_hdr(member_user["token"]))
        assert rd.status_code == 403
        requests.delete(f"{BASE_URL}/api/campaigns/{cid}", headers=_hdr(owner_token))

    def test_nonexistent_campaign_returns_404(self, owner_token):
        fake = str(ObjectId())
        r = requests.delete(f"{BASE_URL}/api/campaigns/{fake}", headers=_hdr(owner_token))
        assert r.status_code == 404


# ------------------------------------------------------------------
# 4. Role tiers (admin gates)
# ------------------------------------------------------------------
class TestRoleTiers:
    def test_admin_can_invite_user(self, admin_user):
        email = f"test_iter9_by_admin_{RUN_ID}_{uuid.uuid4().hex[:5]}@leadunify.com"
        r = requests.post(
            f"{BASE_URL}/api/users/invite",
            headers=_hdr(admin_user["token"]),
            json={"email": email, "role": "member"},
        )
        assert r.status_code == 200, r.text
        uid = r.json()["user"]["id"]
        # cleanup
        raw_db.users.delete_one({"_id": ObjectId(uid)})

    def test_admin_cannot_reset_others_password(self, admin_user, member_user):
        r = requests.patch(
            f"{BASE_URL}/api/users/{member_user['id']}",
            headers=_hdr(admin_user["token"]),
            json={"password": "NewPass123!"},
        )
        assert r.status_code == 403
        assert "owner" in r.json()["detail"].lower()

    def test_admin_can_reset_own_password(self, admin_user):
        new_pwd = f"NewPass_{uuid.uuid4().hex[:6]}!"
        r = requests.patch(
            f"{BASE_URL}/api/users/{admin_user['id']}",
            headers=_hdr(admin_user["token"]),
            json={"password": new_pwd},
        )
        assert r.status_code == 200
        # revert
        requests.patch(
            f"{BASE_URL}/api/users/{admin_user['id']}",
            headers=_hdr(admin_user["token"]),
            json={"password": admin_user["password"]},
        )

    def test_admin_cannot_change_roles(self, admin_user, member_user):
        r = requests.patch(
            f"{BASE_URL}/api/users/{member_user['id']}",
            headers=_hdr(admin_user["token"]),
            json={"role": "admin"},
        )
        assert r.status_code == 403
        assert "owner" in r.json()["detail"].lower()

    def test_admin_cannot_modify_owner(self, admin_user):
        owner_id = str(raw_db.users.find_one({"email": ADMIN_EMAIL})["_id"])
        r = requests.patch(
            f"{BASE_URL}/api/users/{owner_id}",
            headers=_hdr(admin_user["token"]),
            json={"name": "Hacked"},
        )
        assert r.status_code == 403
        assert "owner" in r.json()["detail"].lower()

    def test_admin_cannot_delete_owner(self, admin_user):
        owner_id = str(raw_db.users.find_one({"email": ADMIN_EMAIL})["_id"])
        r = requests.delete(f"{BASE_URL}/api/users/{owner_id}", headers=_hdr(admin_user["token"]))
        assert r.status_code == 403

    def test_admin_can_delete_non_owner_user(self, admin_user, owner_token):
        # Create a throwaway member for admin to delete
        email = f"test_iter9_deleteme_{RUN_ID}_{uuid.uuid4().hex[:5]}@leadunify.com"
        r = requests.post(
            f"{BASE_URL}/api/users/invite",
            headers=_hdr(owner_token),
            json={"email": email, "role": "member", "password": "Pw12345!"},
        )
        uid = r.json()["user"]["id"]
        rd = requests.delete(f"{BASE_URL}/api/users/{uid}", headers=_hdr(admin_user["token"]))
        assert rd.status_code == 200

    def test_owner_can_reset_other_user_password(self, owner_token, member_user):
        new_pwd = "OwnerReset123!"
        r = requests.patch(
            f"{BASE_URL}/api/users/{member_user['id']}",
            headers=_hdr(owner_token),
            json={"password": new_pwd},
        )
        assert r.status_code == 200
        # verify with login
        t = _login(member_user["email"], new_pwd)
        assert t
        # restore
        requests.patch(
            f"{BASE_URL}/api/users/{member_user['id']}",
            headers=_hdr(owner_token),
            json={"password": member_user["password"]},
        )

    def test_owner_can_change_role(self, owner_token, member_user):
        r = requests.patch(
            f"{BASE_URL}/api/users/{member_user['id']}",
            headers=_hdr(owner_token),
            json={"role": "admin"},
        )
        assert r.status_code == 200
        # revert
        requests.patch(
            f"{BASE_URL}/api/users/{member_user['id']}",
            headers=_hdr(owner_token),
            json={"role": "member"},
        )

    def test_member_gets_403_on_admin_endpoints(self, member_user):
        # /users list
        r = requests.get(f"{BASE_URL}/api/users", headers=_hdr(member_user["token"]))
        assert r.status_code == 403
        # /users/invite
        r = requests.post(f"{BASE_URL}/api/users/invite", headers=_hdr(member_user["token"]), json={"email": "x@y.com", "role": "member"})
        assert r.status_code == 403

    def test_owner_cannot_change_own_role_or_promote_other_to_owner(self, owner_token, member_user):
        # role='owner' is not accepted at all
        r = requests.patch(
            f"{BASE_URL}/api/users/{member_user['id']}",
            headers=_hdr(owner_token),
            json={"role": "owner"},
        )
        assert r.status_code == 400


# ------------------------------------------------------------------
# 5. Cascade cleanup (single delete + delete-by-filter)
# ------------------------------------------------------------------
class TestCascadeSingleDelete:
    def test_single_delete_removes_last_person_and_company(self, owner_token):
        cname = f"TEST_iter9_solo_{RUN_ID}_{uuid.uuid4().hex[:5]}"
        pids, cid = _import_csv(
            owner_token,
            [(f"Solo {RUN_ID}", f"solo_{RUN_ID}@example.com", cname)],
            cname,
        )
        assert cid is not None
        assert len(pids) == 1
        pid = pids[0]
        # Insert a fake duplicate flag referencing this person
        raw_db.duplicate_flags.insert_one({
            "existing_person_id": pid,
            "candidate_person_id": str(ObjectId()),
            "status": "pending",
            "created_at": "2026-01-01T00:00:00Z",
            "reason": "test",
        })
        # delete
        rd = requests.delete(f"{BASE_URL}/api/people/{pid}", headers=_hdr(owner_token))
        assert rd.status_code == 200
        body = rd.json()
        assert "cleanup" in body
        assert body["cleanup"]["companies_removed"] >= 1
        # company auto-deleted
        g = requests.get(f"{BASE_URL}/api/companies/{cid}", headers=_hdr(owner_token))
        assert g.status_code == 404
        # duplicate flag pointing at deleted person is gone
        assert raw_db.duplicate_flags.count_documents({"existing_person_id": pid}) == 0


class TestSelfHealingDuplicates:
    def test_stale_flag_selfheals(self, owner_token):
        # Insert a stale flag pointing to a non-existent person
        fake_pid = str(ObjectId())
        inserted = raw_db.duplicate_flags.insert_one({
            "existing_person_id": fake_pid,
            "candidate_person_id": str(ObjectId()),
            "status": "pending",
            "created_at": "2026-01-01T00:00:00Z",
            "reason": "test-stale",
        }).inserted_id
        # call list
        r = requests.get(f"{BASE_URL}/api/duplicates", headers=_hdr(owner_token))
        assert r.status_code == 200
        items = r.json()["items"]
        # None of the returned items should reference the stale ids
        for it in items:
            assert it.get("existing_person_id") != fake_pid
        # And the stale doc must have been purged
        assert raw_db.duplicate_flags.find_one({"_id": inserted}) is None


class TestCascadeDeleteByFilter:
    def test_delete_by_filter_removes_people_company_and_flags(self, owner_token):
        cname = f"TEST_iter9_dbf_{RUN_ID}_{uuid.uuid4().hex[:5]}"
        pids, cid = _import_csv(
            owner_token,
            [(f"DBF{i} {RUN_ID}", f"dbf{i}_{RUN_ID}@example.com", cname) for i in range(3)],
            cname,
        )
        assert cid is not None
        assert len(pids) == 3
        # add stale flag for one of them
        raw_db.duplicate_flags.insert_one({
            "existing_person_id": pids[0],
            "candidate_person_id": str(ObjectId()),
            "status": "pending",
            "created_at": "2026-01-01T00:00:00Z",
        })
        # delete-by-filter with company_name
        r = requests.post(
            f"{BASE_URL}/api/people/delete-by-filter",
            headers=_hdr(owner_token),
            json={"company_name": cname},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["deleted"] == 3
        assert body["cleanup"]["companies_removed"] >= 1
        # company gone
        assert requests.get(f"{BASE_URL}/api/companies/{cid}", headers=_hdr(owner_token)).status_code == 404
        # duplicate flags for those people are gone
        assert raw_db.duplicate_flags.count_documents({"existing_person_id": {"$in": pids}}) == 0

    def test_delete_by_filter_rejects_empty(self, owner_token):
        r = requests.post(f"{BASE_URL}/api/people/delete-by-filter", headers=_hdr(owner_token), json={})
        assert r.status_code == 400


# ------------------------------------------------------------------
# 6. THE BIG ONE — bulk-delete ALL people => cascade full cleanup
# NOTE: destructive; teardown restarts backend so seed_demo_data re-runs.
# ------------------------------------------------------------------
class TestBulkDeleteAllCascade:
    def test_bulk_delete_all_and_cascade(self, owner_token):
        # snapshot pre-state
        pre_campaigns = requests.get(f"{BASE_URL}/api/campaigns", headers=_hdr(owner_token)).json()
        pre_campaign_count = len(pre_campaigns.get("items", pre_campaigns) if isinstance(pre_campaigns, dict) else pre_campaigns)
        # get ALL people ids
        pq = requests.post(f"{BASE_URL}/api/people/query", headers=_hdr(owner_token), json={"limit": 5000})
        assert pq.status_code == 200
        all_ids = [p["id"] for p in pq.json()["items"]]
        assert len(all_ids) > 0, "expected seed people to be present"
        pre_people = len(all_ids)
        pre_companies_resp = requests.get(f"{BASE_URL}/api/companies", headers=_hdr(owner_token))
        pre_companies = pre_companies_resp.json().get("total", 0)
        assert pre_companies > 0
        # insert a stale-referencing duplicate flag on one of them (verify cleanup)
        raw_db.duplicate_flags.insert_one({
            "existing_person_id": all_ids[0],
            "candidate_person_id": all_ids[1] if len(all_ids) > 1 else str(ObjectId()),
            "status": "pending",
            "created_at": "2026-01-01T00:00:00Z",
        })
        # BULK DELETE ALL
        r = requests.post(
            f"{BASE_URL}/api/people/bulk-delete",
            headers=_hdr(owner_token),
            json={"ids": all_ids},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["deleted"] == pre_people
        cleanup = body["cleanup"]
        assert cleanup["person_campaigns"] > 0, f"expected person_campaigns > 0, got {cleanup}"
        assert cleanup["companies_removed"] > 0, f"expected companies_removed > 0, got {cleanup}"
        # verify companies == 0
        c = requests.get(f"{BASE_URL}/api/companies", headers=_hdr(owner_token))
        assert c.json().get("total", 0) == 0
        # verify duplicates == []
        d = requests.get(f"{BASE_URL}/api/duplicates", headers=_hdr(owner_token))
        assert d.json()["items"] == []
        # verify campaigns unchanged
        cur_camps = requests.get(f"{BASE_URL}/api/campaigns", headers=_hdr(owner_token)).json()
        cur_camp_count = len(cur_camps.get("items", cur_camps) if isinstance(cur_camps, dict) else cur_camps)
        assert cur_camp_count == pre_campaign_count, f"campaigns changed: {pre_campaign_count} -> {cur_camp_count}"


# ------------------------------------------------------------------
# Teardown: cleanup test users; restart backend so seed_demo_data restores
# ------------------------------------------------------------------
@pytest.fixture(scope="module", autouse=True)
def _cleanup_and_reseed(owner_token):
    yield
    # Delete any TEST_iter9_* users created during this run
    raw_db.users.delete_many({"email": {"$regex": f"^test_iter9_.*_{RUN_ID}"}})
    # Delete any leftover TEST_iter9_* companies + campaigns
    raw_db.companies.delete_many({"name": {"$regex": f"^TEST_iter9_.*_{RUN_ID}"}})
    raw_db.campaigns.delete_many({"name": {"$regex": f"^TEST_iter9_.*_{RUN_ID}"}})
    # If people collection is now empty (bulk-delete test ran), restart backend
    # so the seed re-runs and restores the demo 20 people + ~17 companies.
    if raw_db.people.count_documents({}) == 0:
        # clear any leftover import_batches too (idempotent)
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=False)
        # wait for backend to come back up + seed to finish
        for _ in range(30):
            time.sleep(1)
            try:
                if requests.get(f"{BASE_URL}/api/auth/me", timeout=2).status_code in (200, 401):
                    break
            except Exception:
                continue
        time.sleep(2)
