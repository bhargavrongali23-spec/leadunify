"""
Iteration 8 — Bulk delete-by-filter + Bulk-share multiple campaigns
Tests:
  POST /api/people/delete-by-filter              (admin only)
  POST /api/people/remove-by-filter-from-campaign
  POST /api/campaigns/bulk-share                  (owner/admin, skipped tracking)
Regression:
  POST /api/people/bulk-delete
  POST /api/people/bulk-remove-from-campaign
  POST /api/campaigns/{cid}/share (single)
"""
import io
import os
import uuid
import pytest
import requests


def _seed_people_via_import(session, campaign_name, company_name, count):
    """Upload a CSV of `count` fake people into a fresh campaign via /api/import.
    Returns the created campaign dict and total_rows."""
    lines = ["email,name,company"]
    for i in range(count):
        lines.append(f"iter8_{uuid.uuid4().hex[:8]}_{i}@example.com,Person_{i},{company_name}")
    csv_bytes = ("\n".join(lines)).encode("utf-8")
    # Post multipart WITHOUT the default JSON Content-Type header from session
    files = {"file": (f"seed_{campaign_name}.csv", csv_bytes, "text/csv")}
    hdrs = {k: v for k, v in session.headers.items() if k.lower() != "content-type"}
    r = requests.post(f"{API}/import/preview", files=files, headers=hdrs)
    assert r.status_code == 200, f"preview failed: {r.status_code} {r.text}"
    prev = r.json()
    token = prev["token"]
    mapping = {"primary_email": "email", "full_name": "name", "company_name": "company"}
    body = {
        "token": token,
        "mapping": mapping,
        "new_campaign_name": campaign_name,
    }
    r2 = session.post(f"{API}/import/commit", json=body)
    assert r2.status_code == 200, f"commit failed: {r2.status_code} {r2.text}"
    return r2.json()  # {batch_id, campaign_id, campaign_name, stats}


def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

RUN_ID = uuid.uuid4().hex[:8]
TEST_COMPANY = f"TEST_iter8_{RUN_ID}"


# ------------------------- fixtures -------------------------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": "admin@leadunify.com", "password": "admin123"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    s.headers.update({"Authorization": f"Bearer {tok}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def non_admin_session(admin_session):
    """Create a non-admin user and return an authenticated session."""
    email = f"test_iter8_{RUN_ID}@leadunify.com"
    password = "Testpass123!"
    # Try register (public endpoint)
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": password, "name": "Iter8 User"})
    if r.status_code not in (200, 201):
        # Maybe already exists → attempt login
        pass
    s = requests.Session()
    lr = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    if lr.status_code != 200:
        pytest.skip(f"could not create/login non-admin: register={r.status_code} login={lr.status_code}")
    tok = lr.json().get("access_token")
    s.headers.update({"Authorization": f"Bearer {tok}",
                      "Content-Type": "application/json"})
    # Fetch user id from /auth/me
    me = s.get(f"{API}/auth/me")
    s.user_id = me.json().get("id") or me.json().get("_id") or me.json().get("user", {}).get("id")
    s.user_email = email
    return s


@pytest.fixture(scope="module")
def campaigns(admin_session):
    r = admin_session.get(f"{API}/campaigns")
    assert r.status_code == 200
    items = r.json().get("items") or r.json()
    assert isinstance(items, list) and len(items) >= 1
    return items


@pytest.fixture(scope="module")
def all_users(admin_session):
    r = admin_session.get(f"{API}/users")
    assert r.status_code == 200
    items = r.json().get("items") or r.json()
    return items


@pytest.fixture(scope="module")
def seeded_people(admin_session, campaigns):
    """Seed a fresh test campaign + 30 dummy contacts under company TEST_COMPANY."""
    # Seed via CSV import: creates a fresh campaign + 30 people
    cn = f"TEST_iter8_camp_{RUN_ID}"
    info = _seed_people_via_import(admin_session, cn, TEST_COMPANY, 30)
    cid = info["campaign_id"]
    # Sanity: query total back
    q = admin_session.post(f"{API}/people/query", json={
        "company_name": TEST_COMPANY, "limit": 200, "offset": 0,
    })
    body = q.json()
    total = body.get("total", 0) or len(body.get("items", []))
    assert total >= 30, f"seed only produced {total} people"
    yield {"campaign": {"id": cid, "name": info["campaign_name"]},
           "person_ids": [it["id"] for it in body.get("items", [])]}

    # teardown — hard delete anything left with this company/campaign
    admin_session.post(f"{API}/people/delete-by-filter",
                       json={"company_name": TEST_COMPANY, "limit": 200, "offset": 0})
    admin_session.delete(f"{API}/campaigns/{cid}")


# =====================================================================
# delete-by-filter
# =====================================================================
class TestDeleteByFilter:
    def test_zero_match_returns_deleted_zero(self, admin_session):
        r = admin_session.post(f"{API}/people/delete-by-filter", json={
            "company_name": "NORESULT_zzz_xyz",
            "limit": 25, "offset": 0,
        })
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True, "deleted": 0}

    def test_non_admin_forbidden(self, non_admin_session):
        r = non_admin_session.post(f"{API}/people/delete-by-filter", json={
            "company_name": "anything",
            "limit": 25, "offset": 0,
        })
        assert r.status_code == 403, r.text

    def test_delete_by_filter_removes_all_matching(self, admin_session, seeded_people):
        # Verify 30 exist first
        q1 = admin_session.post(f"{API}/people/query", json={
            "company_name": TEST_COMPANY, "limit": 200, "offset": 0,
        })
        assert q1.status_code == 200
        total_before = q1.json().get("total") or len(q1.json().get("items", []))
        assert total_before >= 30, f"expected >=30 seeded, got {total_before}"

        # Delete-by-filter
        d = admin_session.post(f"{API}/people/delete-by-filter", json={
            "company_name": TEST_COMPANY, "limit": 25, "offset": 0,
        })
        assert d.status_code == 200, d.text
        body = d.json()
        assert body["ok"] is True
        assert body["deleted"] >= 30, f"deleted={body['deleted']} vs before={total_before}"

        # Verify 0 now
        q2 = admin_session.post(f"{API}/people/query", json={
            "company_name": TEST_COMPANY, "limit": 200, "offset": 0,
        })
        items = q2.json().get("items", [])
        assert len(items) == 0
        total_after = q2.json().get("total")
        if total_after is not None:
            assert total_after == 0


# =====================================================================
# remove-by-filter-from-campaign
# =====================================================================
class TestRemoveByFilterFromCampaign:
    """Uses a second seeded set — separate from TestDeleteByFilter (which deletes them)."""

    @pytest.fixture(scope="class")
    def second_seed(self, admin_session):
        # Fresh campaign + 5 people, plus a second campaign to link them to
        run = uuid.uuid4().hex[:6]
        company = f"TEST_iter8b_{run}"

        # Seed via import into c1
        info1 = _seed_people_via_import(admin_session, f"TEST_iter8b_c1_{run}", company, 5)
        c1 = {"id": info1["campaign_id"], "name": info1["campaign_name"]}
        # Create c2 (empty) then link the 5 people to it as well
        r2 = admin_session.post(f"{API}/campaigns", json={"name": f"TEST_iter8b_c2_{run}"})
        assert r2.status_code == 200
        c2 = r2.json()
        # Fetch pids
        q = admin_session.post(f"{API}/people/query",
                               json={"company_name": company, "limit": 100, "offset": 0})
        pids = [x["id"] for x in q.json().get("items", [])]
        assert len(pids) >= 5
        # Link them to c2 using POST /people/{id}/campaigns
        for pid in pids:
            lr = admin_session.post(f"{API}/people/{pid}/campaigns",
                                    json={"campaign_id": c2["id"]})
            assert lr.status_code == 200, lr.text
        yield {"c1": c1, "c2": c2, "pids": pids, "company": company}

        # Cleanup
        admin_session.post(f"{API}/people/delete-by-filter",
                           json={"company_name": company, "limit": 200, "offset": 0})
        admin_session.delete(f"{API}/campaigns/{c1['id']}")
        admin_session.delete(f"{API}/campaigns/{c2['id']}")

    def test_no_match_returns_zero(self, admin_session, second_seed):
        r = admin_session.post(f"{API}/people/remove-by-filter-from-campaign", json={
            "company_name": "NO_MATCH_zzz",
            "campaign_id": second_seed["c1"]["id"],
            "limit": 25, "offset": 0,
        })
        assert r.status_code == 200
        assert r.json() == {"ok": True, "removed": 0}

    def test_removes_only_that_campaign_link(self, admin_session, second_seed):
        company = second_seed["company"]
        c1 = second_seed["c1"]["id"]
        c2 = second_seed["c2"]["id"]
        pid = second_seed["pids"][0]

        # Verify person is in both campaigns
        gr = admin_session.get(f"{API}/people/{pid}")
        assert gr.status_code == 200
        camps_before = gr.json().get("campaigns") or []
        cids_before = {c["id"] for c in camps_before}
        assert c1 in cids_before and c2 in cids_before, f"pre: {cids_before}"

        # Remove from c1 only
        rr = admin_session.post(f"{API}/people/remove-by-filter-from-campaign", json={
            "company_name": company,
            "campaign_id": c1,
            "limit": 100, "offset": 0,
        })
        assert rr.status_code == 200, rr.text
        assert rr.json()["ok"] is True
        assert rr.json()["removed"] >= 5

        # Person still exists
        gr2 = admin_session.get(f"{API}/people/{pid}")
        assert gr2.status_code == 200
        camps_after = gr2.json().get("campaigns") or []
        cids_after = {c["id"] for c in camps_after}
        assert c1 not in cids_after, f"c1 should be gone, got {cids_after}"
        assert c2 in cids_after, f"c2 should remain, got {cids_after}"


# =====================================================================
# campaigns/bulk-share
# =====================================================================
class TestBulkShare:
    @pytest.fixture(scope="class")
    def bulk_share_setup(self, admin_session, non_admin_session):
        """Create 2 campaigns owned by non-admin + 1 campaign owned by admin."""
        run = uuid.uuid4().hex[:6]
        # Non-admin creates 2 campaigns (should be owner)
        r1 = non_admin_session.post(f"{API}/campaigns", json={"name": f"TEST_iter8_own1_{run}"})
        r2 = non_admin_session.post(f"{API}/campaigns", json={"name": f"TEST_iter8_own2_{run}"})
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text
        own1, own2 = r1.json(), r2.json()

        # Admin creates a campaign non-admin does NOT own
        ra = admin_session.post(f"{API}/campaigns", json={"name": f"TEST_iter8_admin_{run}"})
        assert ra.status_code == 200
        admin_camp = ra.json()

        yield {"own1": own1, "own2": own2, "admin_camp": admin_camp}

        # Cleanup
        for c in (own1, own2, admin_camp):
            admin_session.delete(f"{API}/campaigns/{c['id']}")

    def test_admin_bulk_share_two_campaigns(self, admin_session, all_users, bulk_share_setup):
        """Admin bulk-shares 2 campaigns to 2 users."""
        # Pick two users that are not the admin themselves
        me = admin_session.get(f"{API}/auth/me").json()
        my_id = me.get("id") or me.get("_id")
        others = [u["id"] for u in all_users if u["id"] != my_id][:2]
        if len(others) < 1:
            pytest.skip("need >=1 non-self user to test bulk-share")

        camp_ids = [bulk_share_setup["own1"]["id"], bulk_share_setup["own2"]["id"]]
        r = admin_session.post(f"{API}/campaigns/bulk-share", json={
            "campaign_ids": camp_ids,
            "user_ids": others,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert set(body["shared"]) == set(camp_ids)
        assert body["skipped"] == []
        # Verify persistence
        for cid in camp_ids:
            gr = admin_session.get(f"{API}/campaigns/{cid}")
            assert gr.status_code == 200
            sw = set(gr.json().get("shared_with_user_ids") or [])
            for u in others:
                assert u in sw, f"user {u} not in shared_with for {cid}: {sw}"

    def test_non_admin_bulk_share_mixed_owner_and_nonowner(
        self, admin_session, non_admin_session, all_users, bulk_share_setup
    ):
        """Non-admin bulk-shares [own1, admin_camp] — expect own1 in 'shared', admin_camp in 'skipped'."""
        me = non_admin_session.get(f"{API}/auth/me").json()
        my_id = me.get("id") or me.get("_id")
        # Pick another user to share to
        others = [u["id"] for u in all_users if u["id"] != my_id][:1]
        if not others:
            pytest.skip("no other user to share to")

        payload = {
            "campaign_ids": [bulk_share_setup["own1"]["id"], bulk_share_setup["admin_camp"]["id"]],
            "user_ids": others,
        }
        r = non_admin_session.post(f"{API}/campaigns/bulk-share", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert bulk_share_setup["own1"]["id"] in body["shared"]
        assert bulk_share_setup["admin_camp"]["id"] not in body["shared"]
        skipped_ids = [s["campaign_id"] for s in body["skipped"]]
        assert bulk_share_setup["admin_camp"]["id"] in skipped_ids
        # Reason should be 'not owner'
        reasons = {s["campaign_id"]: s["reason"] for s in body["skipped"]}
        assert reasons[bulk_share_setup["admin_camp"]["id"]] == "not owner"

    def test_bulk_share_invalid_ids_reported(self, admin_session):
        r = admin_session.post(f"{API}/campaigns/bulk-share", json={
            "campaign_ids": ["not-an-id", "000000000000000000000000"],
            "user_ids": [],
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["shared"] == []
        reasons = [s["reason"] for s in body["skipped"]]
        assert "invalid id" in reasons
        assert "not found" in reasons


# =====================================================================
# Regression: bulk-delete + single-share still work
# =====================================================================
class TestRegression:
    @pytest.fixture(scope="class")
    def regression_seed(self, admin_session):
        run = uuid.uuid4().hex[:6]
        company = f"TEST_iter8reg_{run}"
        info = _seed_people_via_import(admin_session, f"TEST_iter8reg_{run}", company, 3)
        camp = {"id": info["campaign_id"], "name": info["campaign_name"]}
        q = admin_session.post(f"{API}/people/query",
                               json={"company_name": company, "limit": 100, "offset": 0})
        pids = [x["id"] for x in q.json().get("items", [])]
        yield {"camp": camp, "pids": pids, "company": company}
        admin_session.post(f"{API}/people/delete-by-filter",
                           json={"company_name": company, "limit": 100, "offset": 0})
        admin_session.delete(f"{API}/campaigns/{camp['id']}")

    def test_explicit_bulk_delete(self, admin_session, regression_seed):
        ids = regression_seed["pids"][:2]
        r = admin_session.post(f"{API}/people/bulk-delete", json={"ids": ids})
        assert r.status_code == 200
        assert r.json()["deleted"] == 2
        # Verify gone
        for pid in ids:
            g = admin_session.get(f"{API}/people/{pid}")
            assert g.status_code == 404

    def test_explicit_bulk_remove_from_campaign(self, admin_session, regression_seed):
        # Use one of the seeded people (only test_explicit_bulk_delete deleted 2 above)
        # regression_seed has 3 pids; first 2 were deleted; pid[2] remains
        pid = regression_seed["pids"][2]
        r = admin_session.post(f"{API}/people/bulk-remove-from-campaign", json={
            "ids": [pid], "campaign_id": regression_seed["camp"]["id"],
        })
        assert r.status_code == 200
        assert r.json()["removed"] == 1
        # Person still exists
        g = admin_session.get(f"{API}/people/{pid}")
        assert g.status_code == 200
        cids_after = {c["id"] for c in (g.json().get("campaigns") or [])}
        assert regression_seed["camp"]["id"] not in cids_after

    def test_single_share_still_works(self, admin_session, all_users):
        # Create a temp camp, share to 1 user, verify
        me = admin_session.get(f"{API}/auth/me").json()
        my_id = me.get("id") or me.get("_id")
        others = [u["id"] for u in all_users if u["id"] != my_id][:1]
        if not others:
            pytest.skip("no user to share to")
        rc = admin_session.post(f"{API}/campaigns", json={"name": f"TEST_iter8_single_{uuid.uuid4().hex[:6]}"})
        cid = rc.json()["id"]
        try:
            r = admin_session.post(f"{API}/campaigns/{cid}/share",
                                   json={"user_ids": others})
            assert r.status_code == 200
            sw = set(r.json().get("shared_with_user_ids") or [])
            assert others[0] in sw
        finally:
            admin_session.delete(f"{API}/campaigns/{cid}")


# =====================================================================
# Auth checks
# =====================================================================
class TestAuth:
    def test_delete_by_filter_unauthenticated(self):
        r = requests.post(f"{API}/people/delete-by-filter",
                          json={"limit": 25, "offset": 0})
        assert r.status_code in (401, 403)

    def test_bulk_share_unauthenticated(self):
        r = requests.post(f"{API}/campaigns/bulk-share",
                          json={"campaign_ids": [], "user_ids": []})
        assert r.status_code in (401, 403)
