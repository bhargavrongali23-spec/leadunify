"""LeadUnify backend tests — updated after rename + bug fixes.

Covers:
  - App rename (backend /api/ returns service=LeadUnify)
  - Auth (login returns access_token in body AND sets cookies; Bearer + cookie both work; /api/auth/me)
  - People query with in_campaigns OR (union) semantics
  - One person, multiple campaigns (Bhargav Reddy)
  - Chat via Claude Sonnet 4.5
  - Sheets graceful degradation (503 login, configured:false)
  - Column mapping suggestion — global optimal (First Name NOT stolen by full_name)
  - Import commit: combines first_name+last_name into full_name, dedups Bhargav by email
"""
from __future__ import annotations

import io
import os
import time

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@leadunify.com"
ADMIN_PASSWORD = "admin123"

TEST_CSV_PATH = "/tmp/test_first_last.csv"


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def login_response(session):
    r = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r


@pytest.fixture(scope="session")
def access_token(login_response):
    body = login_response.json()
    tok = body.get("access_token")
    assert tok, f"login body must include access_token, got: {body}"
    return tok


@pytest.fixture(scope="session")
def auth_session(session, login_response):
    """Cookie-authenticated session (same session used to login)."""
    assert "access_token" in session.cookies
    return session


@pytest.fixture(scope="session")
def bearer_session(access_token):
    """Fresh session using ONLY Bearer token (no cookies)."""
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    })
    return s


@pytest.fixture(scope="session")
def campaigns(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/campaigns", timeout=30)
    assert r.status_code == 200
    items = r.json()["items"]
    return {c["name"]: c for c in items}


# ---------- Rename ----------
class TestRename:
    def test_root_returns_leadunify(self, session):
        r = session.get(f"{BASE_URL}/api/", timeout=30)
        assert r.status_code == 200
        d = r.json()
        # Case-insensitive check for "LeadUnify"
        assert any("leadunify" in str(v).lower() for v in d.values()), f"Expected LeadUnify in root response, got {d}"


# ---------- Auth ----------
class TestAuth:
    def test_login_returns_access_token_and_cookies(self, session):
        s = requests.Session()
        r = s.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["user"]["email"] == ADMIN_EMAIL
        assert body["user"]["role"] == "admin"
        assert body.get("access_token"), "login body must contain access_token"
        assert "access_token" in s.cookies, "login must set access_token cookie"

    def test_me_with_bearer(self, bearer_session):
        r = bearer_session.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["email"] == ADMIN_EMAIL

    def test_me_with_cookie(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_login_invalid(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": "wrongpass"},
            timeout=30,
        )
        assert r.status_code == 401


# ---------- People / one person, multiple campaigns ----------
class TestOnePersonManyCampaigns:
    def test_bhargav_in_both_campaigns(self, auth_session, campaigns):
        qr = auth_session.post(
            f"{BASE_URL}/api/people/query",
            json={"search": "bhargav@company.com", "page_size": 5},
            timeout=30,
        )
        assert qr.status_code == 200
        d = qr.json()
        assert d["total"] == 1, f"Expected exactly 1 Bhargav, got {d['total']}"
        person = d["items"][0]
        names = [c["name"] for c in person["campaigns"]]
        assert "MBA Annual 2026" in names
        assert "Non-QM Introductory Campaign" in names

        # GET by id also returns both campaigns
        pid = person["id"]
        r2 = auth_session.get(f"{BASE_URL}/api/people/{pid}", timeout=30)
        assert r2.status_code == 200
        detail = r2.json()
        detail_camps = [c["name"] for c in detail["campaigns"]]
        assert "MBA Annual 2026" in detail_camps
        assert "Non-QM Introductory Campaign" in detail_camps


# ---------- In-campaign filter: OR (union) semantics ----------
class TestInCampaignUnion:
    def test_in_campaigns_uses_union(self, auth_session, campaigns):
        mba = campaigns["MBA Annual 2026"]["id"]
        non_qm = campaigns["Non-QM Introductory Campaign"]["id"]
        # Get people counts per campaign
        r_mba = auth_session.post(
            f"{BASE_URL}/api/people/query",
            json={"in_campaigns": [mba], "page_size": 100},
            timeout=30,
        )
        r_non_qm = auth_session.post(
            f"{BASE_URL}/api/people/query",
            json={"in_campaigns": [non_qm], "page_size": 100},
            timeout=30,
        )
        r_union = auth_session.post(
            f"{BASE_URL}/api/people/query",
            json={"in_campaigns": [mba, non_qm], "page_size": 100},
            timeout=30,
        )
        assert r_mba.status_code == 200
        assert r_non_qm.status_code == 200
        assert r_union.status_code == 200

        names_mba = {p["full_name"] for p in r_mba.json()["items"]}
        names_non_qm = {p["full_name"] for p in r_non_qm.json()["items"]}
        names_union = {p["full_name"] for p in r_union.json()["items"]}

        expected_union = names_mba | names_non_qm
        # Union must include Bhargav (in both)
        assert "Bhargav Reddy" in names_union
        # Union must equal set-union of both individual results
        assert names_union == expected_union, (
            f"Union filter does not use OR semantics.\n"
            f"MBA: {names_mba}\nNon-QM: {names_non_qm}\n"
            f"Union: {names_union}\nExpected: {expected_union}"
        )
        # And strictly larger than intersection (i.e. more than just Bhargav)
        assert len(names_union) > len(names_mba & names_non_qm)


# ---------- Column mapping suggestion — global optimal ----------
class TestColumnMappingGlobal:
    def _upload(self, sess, csv_text, filename="t.csv"):
        s = requests.Session()
        s.cookies.update(sess.cookies)
        s.headers.update({k: v for k, v in sess.headers.items() if k.lower() == "authorization"})
        files = {"file": (filename, csv_text.encode("utf-8"), "text/csv")}
        return s.post(f"{BASE_URL}/api/import/preview", files=files, timeout=30)

    def test_first_last_headers_not_stolen(self, auth_session):
        with open(TEST_CSV_PATH, "r") as f:
            csv_text = f.read()
        r = self._upload(auth_session, csv_text, "test_first_last.csv")
        assert r.status_code == 200, r.text
        d = r.json()
        m = d["suggested_mapping"]
        # Global-optimal: First Name must go to first_name, not stolen by full_name
        assert m.get("first_name") == "First Name", f"first_name mapping wrong: {m}"
        assert m.get("last_name") == "Last Name", f"last_name mapping wrong: {m}"
        # full_name must not have taken 'First Name'
        assert m.get("full_name") != "First Name"
        assert m.get("primary_email") == "Business Email"
        assert m.get("phone") == "Cell Number"
        assert m.get("linkedin_url") == "LinkedIn Profile"
        assert m.get("company_name") == "Employer"
        assert m.get("job_title") == "Job Role"
        assert m.get("notes") == "Comments"


# ---------- Import commit: first_name+last_name -> full_name, dedup Bhargav ----------
class TestImportFirstLastDedup:
    def test_commit_combines_first_last_and_dedups(self, auth_session, campaigns):
        with open(TEST_CSV_PATH, "r") as f:
            csv_text = f.read()

        # preview
        s = requests.Session()
        s.cookies.update(auth_session.cookies)
        files = {"file": ("test_first_last.csv", csv_text.encode("utf-8"), "text/csv")}
        prev = s.post(f"{BASE_URL}/api/import/preview", files=files, timeout=30)
        assert prev.status_code == 200, prev.text
        pv = prev.json()
        token = pv["token"]
        mapping = {
            "first_name": "First Name",
            "last_name": "Last Name",
            "primary_email": "Business Email",
            "phone": "Cell Number",
            "linkedin_url": "LinkedIn Profile",
            "company_name": "Employer",
            "job_title": "Job Role",
            "notes": "Comments",
        }

        camp_name = f"TEST_FirstLast_{int(time.time())}"
        r = auth_session.post(
            f"{BASE_URL}/api/import/commit",
            json={"token": token, "mapping": mapping, "new_campaign_name": camp_name},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        stats = d["stats"]
        campaign_id = d["campaign_id"]

        # Bhargav should be MATCHED, not created new
        assert stats.get("matched_people", 0) >= 1, f"Bhargav should have been matched: {stats}"
        assert stats.get("matched_by_email", 0) >= 1
        # Sarah + Alex are new → 2. Bhargav is dupe. So new_people <= 2
        assert stats.get("new_people", 0) <= 2

        # Verify Sarah Mitchell has full_name populated (combined from first+last)
        qr = auth_session.post(
            f"{BASE_URL}/api/people/query",
            json={"search": "sarah.m@newco.example", "page_size": 5},
            timeout=30,
        )
        items = qr.json()["items"]
        assert len(items) == 1, f"Sarah not created: {items}"
        assert items[0]["full_name"] == "Sarah Mitchell", (
            f"Expected full_name 'Sarah Mitchell', got {items[0].get('full_name')!r}"
        )

        # Bhargav should now have this new campaign in his list — still ONE record
        qr2 = auth_session.post(
            f"{BASE_URL}/api/people/query",
            json={"search": "bhargav@company.com", "page_size": 5},
            timeout=30,
        )
        assert qr2.json()["total"] == 1
        bhargav_camps = [c["name"] for c in qr2.json()["items"][0]["campaigns"]]
        assert camp_name in bhargav_camps

        # Cleanup: delete new campaign, and delete the newly-created people (Sarah, Alex)
        auth_session.delete(f"{BASE_URL}/api/campaigns/{campaign_id}", timeout=30)
        # Also try to delete Sarah + Alex so re-runs stay clean
        for email in ("sarah.m@newco.example", "alex@example.com"):
            qq = auth_session.post(
                f"{BASE_URL}/api/people/query",
                json={"search": email, "page_size": 3},
                timeout=30,
            )
            for p in qq.json().get("items", []):
                auth_session.delete(f"{BASE_URL}/api/people/{p['id']}", timeout=30)


# ---------- Chat ----------
class TestChat:
    def test_chat_hdfc(self, auth_session):
        r = auth_session.post(
            f"{BASE_URL}/api/chat/query",
            json={"message": "show me everyone from HDFC Bank"},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["intent"] == "people_search"
        assert d.get("results") is not None
        assert d["results"]["total"] >= 4


# ---------- Sheets graceful degradation ----------
class TestSheets:
    def test_status(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/sheets/status", timeout=30)
        assert r.status_code == 200
        assert r.json()["configured"] is False

    def test_login_503(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/oauth/sheets/login", timeout=30)
        assert r.status_code == 503
