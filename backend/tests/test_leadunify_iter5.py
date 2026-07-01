"""Iteration-5 backend tests for LeadUnify final feature round.

Covers:
- BUG FIX: company_name substring filter (POST /api/people/query)
- FEATURE: users list/invite/patch/delete
- FEATURE: campaign owner + share/unshare
- FEATURE: access request flow (request/list/approve/deny)
- REGRESSION: login, /auth/me, Bhargav dedup, normalize_company_name, seed baseline
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://contact-unify.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@leadunify.com"
ADMIN_PASSWORD = "admin123"

# Unique per-run tag for cleanup
RUN_TAG = f"iter5_{int(time.time())}"
SARA_EMAIL = f"sara_{RUN_TAG}@leadunify.com"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def state():
    """Shared mutable state across tests (sara_id, sara_token, temp_campaign_id, etc.)."""
    return {}


# ---------- 1) Regression: login + /auth/me ----------
class TestAuthRegression:
    def test_login_and_me(self, admin_token):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
        assert r.status_code == 200
        me = r.json()
        assert me.get("email") == ADMIN_EMAIL
        assert me.get("role") == "admin"


# ---------- 2) BUG FIX: company_name substring filter ----------
class TestCompanySubstringFilter:
    def test_hdfc_substring_returns_hdfc_bank_people(self, admin_headers):
        r = requests.post(f"{API}/people/query", json={"company_name": "HDFC"}, headers=admin_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        items = data.get("items", [])
        assert len(items) == 4, f"expected 4 HDFC Bank people, got {len(items)}: {[p.get('company_name') for p in items]}"
        for p in items:
            assert "hdfc" in (p.get("company_name") or "").lower()

    def test_case_insensitive_bank_substring(self, admin_headers):
        r = requests.post(f"{API}/people/query", json={"company_name": "bank"}, headers=admin_headers, timeout=15)
        assert r.status_code == 200
        items = r.json().get("items", [])
        # Should include the 4 HDFC Bank people at minimum
        hdfc_count = sum(1 for p in items if "hdfc" in (p.get("company_name") or "").lower())
        assert hdfc_count == 4, f"expected 4 hdfc rows in 'bank' substring, got {hdfc_count}"
        # every hit must contain 'bank' case-insensitively
        for p in items:
            assert "bank" in (p.get("company_name") or "").lower()


# ---------- 3) Bhargav dedup regression ----------
class TestBhargavDedup:
    def test_bhargav_single_person_two_campaigns(self, admin_headers):
        r = requests.post(f"{API}/people/query", json={"search": "bhargav@company.com"}, headers=admin_headers, timeout=15)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) == 1, f"expected 1 Bhargav, got {len(items)}"
        p = items[0]
        camps = p.get("campaigns") or []
        assert len(camps) == 2, f"expected 2 campaigns for bhargav, got {len(camps)}"


# ---------- 4) FEATURE: users list ----------
class TestUsersList:
    def test_admin_lists_users(self, admin_headers):
        r = requests.get(f"{API}/users", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) >= 1
        admin = [u for u in items if u["email"] == ADMIN_EMAIL]
        assert admin and admin[0]["role"] == "admin"
        # no password_hash leak
        for u in items:
            assert "password_hash" not in u

    def test_non_admin_forbidden(self, admin_headers, state):
        # invite a temp member
        r = requests.post(
            f"{API}/users/invite",
            json={"email": f"tmp_{RUN_TAG}@leadunify.com", "name": "Tmp", "role": "member"},
            headers=admin_headers,
            timeout=10,
        )
        assert r.status_code == 200
        body = r.json()
        pwd = body["temporary_password"]
        tmp_id = body["user"]["id"]

        # login as tmp
        lr = requests.post(f"{API}/auth/login", json={"email": f"tmp_{RUN_TAG}@leadunify.com", "password": pwd}, timeout=10)
        assert lr.status_code == 200
        tok = lr.json().get("access_token") or lr.json().get("token")

        # 403 on /users
        forb = requests.get(f"{API}/users", headers={"Authorization": f"Bearer {tok}"}, timeout=10)
        assert forb.status_code == 403

        # cleanup
        d = requests.delete(f"{API}/users/{tmp_id}", headers=admin_headers, timeout=10)
        assert d.status_code == 200


# ---------- 5) FEATURE: invite + login + patch (role/password) + delete ----------
class TestUserInviteLifecycle:
    def test_invite_login_promote_reset_delete(self, admin_headers, state):
        # invite Sara
        r = requests.post(
            f"{API}/users/invite",
            json={"email": SARA_EMAIL, "name": "Sara", "role": "member"},
            headers=admin_headers,
            timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("temporary_password"), "temporary_password missing"
        assert body["user"]["email"] == SARA_EMAIL
        assert body["user"]["role"] == "member"
        assert isinstance(body["temporary_password"], str) and len(body["temporary_password"]) > 0
        sara_id = body["user"]["id"]
        sara_pw = body["temporary_password"]

        # login with returned password
        lr = requests.post(f"{API}/auth/login", json={"email": SARA_EMAIL, "password": sara_pw}, timeout=10)
        assert lr.status_code == 200, f"sara login failed: {lr.text}"
        sara_tok = lr.json().get("access_token") or lr.json().get("token")
        assert sara_tok
        state["sara_id"] = sara_id
        state["sara_token"] = sara_tok

        # patch to admin
        p = requests.patch(f"{API}/users/{sara_id}", json={"role": "admin"}, headers=admin_headers, timeout=10)
        assert p.status_code == 200
        # verify
        lu = requests.get(f"{API}/users", headers=admin_headers, timeout=10).json()["items"]
        sara_row = [u for u in lu if u["id"] == sara_id][0]
        assert sara_row["role"] == "admin"

        # revert to member for later share tests
        rev = requests.patch(f"{API}/users/{sara_id}", json={"role": "member"}, headers=admin_headers, timeout=10)
        assert rev.status_code == 200

        # reset password
        rp = requests.patch(f"{API}/users/{sara_id}", json={"password": "newpass_iter5!"}, headers=admin_headers, timeout=10)
        assert rp.status_code == 200
        lr2 = requests.post(f"{API}/auth/login", json={"email": SARA_EMAIL, "password": "newpass_iter5!"}, timeout=10)
        assert lr2.status_code == 200
        state["sara_token"] = lr2.json().get("access_token") or lr2.json().get("token")

        # cleanup THIS test's sara so TestCampaignsAccessAndCleanup can create its own
        requests.delete(f"{API}/users/{sara_id}", headers=admin_headers, timeout=10)

    def test_delete_self_forbidden(self, admin_headers):
        me = requests.get(f"{API}/auth/me", headers=admin_headers, timeout=10).json()
        r = requests.delete(f"{API}/users/{me['id']}", headers=admin_headers, timeout=10)
        assert r.status_code == 400


# ---------- 6) FEATURE: campaign owner + share + access + cleanup (single class so loadscope keeps state on one worker) ----------
class TestCampaignsAccessAndCleanup:
    def test_a_invite_sara(self, admin_headers, state):
        r = requests.post(
            f"{API}/users/invite",
            json={"email": SARA_EMAIL + ".v2", "name": "Sara2", "role": "member"},
            headers=admin_headers,
            timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        state["sara_id"] = body["user"]["id"]
        state["sara_email"] = body["user"]["email"]
        state["sara_pw"] = body["temporary_password"]
        lr = requests.post(f"{API}/auth/login", json={"email": body["user"]["email"], "password": body["temporary_password"]}, timeout=10)
        assert lr.status_code == 200
        state["sara_token"] = lr.json().get("access_token") or lr.json().get("token")

    def test_b_scope_all_and_share(self, admin_headers, state):
        assert "sara_id" in state, "invite test must run first"
        sara_id = state["sara_id"]
        sara_tok = state["sara_token"]
        sara_headers = {"Authorization": f"Bearer {sara_tok}"}

        # admin: scope=mine returns all (admin owns everything post-seed)
        r = requests.get(f"{API}/campaigns", params={"scope": "mine"}, headers=admin_headers, timeout=10)
        assert r.status_code == 200
        admin_mine = r.json().get("items", [])
        assert len(admin_mine) >= 7, f"admin should see all seed campaigns, got {len(admin_mine)}"
        for c in admin_mine:
            assert c.get("owner_id"), f"campaign has no owner_id: {c.get('name')}"

        # sara: scope=mine (member) returns her own+shared only (none yet -> 0)
        r = requests.get(f"{API}/campaigns", params={"scope": "mine"}, headers=sara_headers, timeout=10)
        assert r.status_code == 200
        sara_mine = r.json().get("items", [])
        assert len(sara_mine) == 0, f"sara has no campaigns yet, got {len(sara_mine)}"

        # sara: scope=all returns all with has_access flags
        r = requests.get(f"{API}/campaigns", params={"scope": "all"}, headers=sara_headers, timeout=10)
        assert r.status_code == 200
        sara_all = r.json().get("items", [])
        assert len(sara_all) >= 7
        # all should be has_access=False for sara
        locked = [c for c in sara_all if not c.get("has_access")]
        assert len(locked) >= 7, "sara should see locked campaigns in scope=all"

        # Sara creates a campaign of her own -> owner should be sara
        cr = requests.post(
            f"{API}/campaigns",
            json={"name": f"TEST_sara_camp_{RUN_TAG}", "category": "Other"},
            headers=sara_headers,
            timeout=10,
        )
        assert cr.status_code == 200
        camp = cr.json()
        assert camp.get("owner_id") == sara_id
        state["sara_camp_id"] = camp["id"]

        # sara mine should now be 1
        r = requests.get(f"{API}/campaigns", params={"scope": "mine"}, headers=sara_headers, timeout=10)
        assert len(r.json()["items"]) == 1

        # Admin shares seed campaign with sara
        seed_cid = admin_mine[0]["id"]
        state["shared_camp_id"] = seed_cid
        sh = requests.post(
            f"{API}/campaigns/{seed_cid}/share",
            json={"user_ids": [sara_id]},
            headers=admin_headers,
            timeout=10,
        )
        assert sh.status_code == 200
        after = sh.json()
        assert sara_id in (after.get("shared_with_user_ids") or [])

        # sara now sees 2 (her own + shared)
        r = requests.get(f"{API}/campaigns", params={"scope": "mine"}, headers=sara_headers, timeout=10)
        assert len(r.json()["items"]) == 2

        # unshare
        un = requests.post(
            f"{API}/campaigns/{seed_cid}/unshare",
            json={"user_id": sara_id},
            headers=admin_headers,
            timeout=10,
        )
        assert un.status_code == 200
        r = requests.get(f"{API}/campaigns", params={"scope": "mine"}, headers=sara_headers, timeout=10)
        assert len(r.json()["items"]) == 1

    def test_c_share_non_owner_forbidden(self, state, admin_headers):
        """Sara (non-admin, non-owner of seed) should get 403 sharing a seed campaign."""
        sara_headers = {"Authorization": f"Bearer {state['sara_token']}"}
        seed_cid = state["shared_camp_id"]
        r = requests.post(
            f"{API}/campaigns/{seed_cid}/share",
            json={"user_ids": [state["sara_id"]]},
            headers=sara_headers,
            timeout=10,
        )
        assert r.status_code == 403


    def test_d_request_list_approve_deny(self, state, admin_headers):
        sara_headers = {"Authorization": f"Bearer {state['sara_token']}"}
        sara_id = state["sara_id"]

        # sara requests access to two campaigns
        campaigns = requests.get(f"{API}/campaigns", params={"scope": "all"}, headers=sara_headers, timeout=10).json()["items"]
        locked = [c for c in campaigns if not c.get("has_access")]
        assert len(locked) >= 2
        c1, c2 = locked[0]["id"], locked[1]["id"]

        rr = requests.post(f"{API}/campaigns/{c1}/request-access", headers=sara_headers, timeout=10)
        assert rr.status_code == 200
        assert rr.json().get("requested") is True or rr.json().get("already_requested")

        rr2 = requests.post(f"{API}/campaigns/{c2}/request-access", headers=sara_headers, timeout=10)
        assert rr2.status_code == 200

        # admin lists pending
        lst = requests.get(f"{API}/access-requests", headers=admin_headers, timeout=10)
        assert lst.status_code == 200
        pending = lst.json()["items"]
        mine = [p for p in pending if p.get("user_id") == sara_id]
        assert len(mine) >= 2
        req_c1 = [p for p in mine if p["campaign_id"] == c1][0]
        req_c2 = [p for p in mine if p["campaign_id"] == c2][0]

        # approve first
        ap = requests.post(f"{API}/access-requests/{req_c1['id']}/action", json={"action": "approve"}, headers=admin_headers, timeout=10)
        assert ap.status_code == 200

        # verify sara now sees c1 in scope=mine
        mine_now = requests.get(f"{API}/campaigns", params={"scope": "mine"}, headers=sara_headers, timeout=10).json()["items"]
        assert any(c["id"] == c1 for c in mine_now), "sara should see approved campaign"

        # deny second
        dn = requests.post(f"{API}/access-requests/{req_c2['id']}/action", json={"action": "deny"}, headers=admin_headers, timeout=10)
        assert dn.status_code == 200
        mine_now2 = requests.get(f"{API}/campaigns", params={"scope": "mine"}, headers=sara_headers, timeout=10).json()["items"]
        assert not any(c["id"] == c2 for c in mine_now2), "denied campaign must NOT appear in sara's mine"

        # cleanup: unshare c1 so seed shared_with_user_ids is empty
        requests.post(f"{API}/campaigns/{c1}/unshare", json={"user_id": sara_id}, headers=admin_headers, timeout=10)
        state["approved_camp_id"] = c1
        state["denied_camp_id"] = c2


    def test_e_share_route_not_captured_by_patch(self, admin_headers, state):
        """POST /campaigns/{id}/share must hit the share handler, not PATCH /campaigns/{id}."""
        seed_cid = state["shared_camp_id"]
        # POST to /share with an empty user_ids -> should return the campaign doc (200)
        r = requests.post(f"{API}/campaigns/{seed_cid}/share", json={"user_ids": []}, headers=admin_headers, timeout=10)
        assert r.status_code == 200
        # response should have owner_id + shared_with_user_ids fields (from share handler)
        body = r.json()
        assert "owner_id" in body
        assert "shared_with_user_ids" in body

    def test_f_delete_sara_reassigns_campaigns_and_restores_baseline(self, state, admin_headers):
        # Delete sara — her campaign should reassign to admin (caller)
        me = requests.get(f"{API}/auth/me", headers=admin_headers, timeout=10).json()
        admin_id = me["id"]

        d = requests.delete(f"{API}/users/{state['sara_id']}", headers=admin_headers, timeout=10)
        assert d.status_code == 200

        # sara's campaign should now be owned by admin
        camp = requests.get(f"{API}/campaigns/{state['sara_camp_id']}", headers=admin_headers, timeout=10).json()
        assert camp["owner_id"] == admin_id

        # delete sara's test campaign
        dc = requests.delete(f"{API}/campaigns/{state['sara_camp_id']}", headers=admin_headers, timeout=10)
        assert dc.status_code in (200, 204)

        # delete access_requests for sara (cleanup)
        # (delete_user endpoint already deletes access_requests for the user)

        # sanity: 1 user, 7 campaigns, 20 people
        users = requests.get(f"{API}/users", headers=admin_headers, timeout=10).json()["items"]
        assert len(users) == 1, f"users count should be 1, got {len(users)}: {[u['email'] for u in users]}"

        camps = requests.get(f"{API}/campaigns", params={"scope": "mine"}, headers=admin_headers, timeout=10).json()["items"]
        assert len(camps) == 7, f"campaigns count should be 7, got {len(camps)}"

        stats = requests.get(f"{API}/stats/overview", headers=admin_headers, timeout=10).json()
        assert stats.get("total_people") == 20
        assert stats.get("total_companies") == 17
        assert stats.get("total_campaigns") == 7

        # access_requests should all be gone (sara was the only requester)
        pend = requests.get(f"{API}/access-requests", headers=admin_headers, timeout=10).json()["items"]
        assert len(pend) == 0
