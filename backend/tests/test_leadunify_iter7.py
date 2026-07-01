"""
Iteration 7 — Custom Columns per Campaign
Tests backend endpoints:
  POST   /api/campaigns/{cid}/columns
  GET    /api/campaigns/{cid}/columns
  DELETE /api/campaigns/{cid}/columns/{col_id}
  PATCH  /api/campaigns/{cid}/cells/{pid}
  GET    /api/campaigns/{cid}/cell-value-counts
  POST   /api/people/query   with custom_filters
"""
import os
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": "admin@leadunify.com", "password": "admin123"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    assert tok
    s.headers.update({"Authorization": f"Bearer {tok}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def campaigns(admin_session):
    r = admin_session.get(f"{API}/campaigns")
    assert r.status_code == 200
    items = r.json().get("items") or r.json()
    assert isinstance(items, list) and len(items) >= 2, "need >=2 campaigns"
    return items


@pytest.fixture(scope="module")
def cam_a(campaigns):
    return campaigns[0]


@pytest.fixture(scope="module")
def cam_b(campaigns):
    return campaigns[1]


@pytest.fixture(scope="module")
def created_cols(admin_session, cam_a):
    """Create three columns (select/text/checkbox) in campaign A. Cleanup at end."""
    cid = cam_a["id"]
    created = []

    def _mk(name, kind, options=None):
        payload = {"name": name, "kind": kind}
        if options is not None:
            payload["options"] = options
        r = admin_session.post(f"{API}/campaigns/{cid}/columns", json=payload)
        assert r.status_code == 200, f"create col {name}: {r.status_code} {r.text}"
        d = r.json()
        assert d["name"] == name
        assert d["kind"] == kind
        assert "id" in d
        created.append(d)
        return d

    sel = _mk("TEST_QA_Choices", "select", ["Sent", "Not sent", "Bounced"])
    txt = _mk("TEST_QA_Text", "text")
    chk = _mk("TEST_QA_Bool", "checkbox")

    yield {"select": sel, "text": txt, "checkbox": chk}

    for c in created:
        admin_session.delete(f"{API}/campaigns/{cid}/columns/{c['id']}")


# ---------- Create ----------
class TestColumnCreate:
    def test_list_columns_includes_created(self, admin_session, cam_a, created_cols):
        r = admin_session.get(f"{API}/campaigns/{cam_a['id']}/columns")
        assert r.status_code == 200
        items = r.json()["items"]
        names = [c["name"] for c in items]
        for kind in ("select", "text", "checkbox"):
            assert created_cols[kind]["name"] in names

    def test_create_column_missing_name(self, admin_session, cam_a):
        r = admin_session.post(f"{API}/campaigns/{cam_a['id']}/columns",
                               json={"name": "  ", "kind": "text"})
        assert r.status_code == 400

    def test_create_column_bad_kind(self, admin_session, cam_a):
        r = admin_session.post(f"{API}/campaigns/{cam_a['id']}/columns",
                               json={"name": "TEST_bad", "kind": "date"})
        assert r.status_code == 400

    def test_create_select_needs_options(self, admin_session, cam_a):
        r = admin_session.post(f"{API}/campaigns/{cam_a['id']}/columns",
                               json={"name": "TEST_sel_no_opts", "kind": "select"})
        assert r.status_code == 400

    def test_invalid_campaign(self, admin_session):
        r = admin_session.post(f"{API}/campaigns/000000000000000000000000/columns",
                               json={"name": "TEST_x", "kind": "text"})
        assert r.status_code == 404


# ---------- Cells ----------
@pytest.fixture(scope="module")
def people_in_cam_a(admin_session, cam_a):
    """Return first few people that already exist in campaign A."""
    r = admin_session.post(f"{API}/people/query",
                           json={"in_campaigns": [cam_a["id"]], "limit": 10, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    items = body.get("items") or []
    assert len(items) >= 2, f"need >=2 people in campaign A, got {len(items)}"
    return items


class TestCellPersist:
    def test_set_select_cell_persists(self, admin_session, cam_a, created_cols, people_in_cam_a):
        p = people_in_cam_a[0]
        col = created_cols["select"]
        r = admin_session.patch(f"{API}/campaigns/{cam_a['id']}/cells/{p['id']}",
                                json={"column_id": col["id"], "value": "Sent"})
        assert r.status_code == 200, r.text
        # verify via people/query -> custom_values in link
        q = admin_session.post(f"{API}/people/query",
                               json={"in_campaigns": [cam_a["id"]],
                                     "person_ids": [p["id"]],
                                     "limit": 5, "offset": 0})
        assert q.status_code == 200
        items = q.json().get("items", [])
        found = [x for x in items if x["id"] == p["id"]]
        assert found, "person not returned"
        cv = found[0].get("custom_values") or {}
        assert cv.get(col["id"]) == "Sent", f"custom_values={cv}"

    def test_set_select_invalid_value_rejected(self, admin_session, cam_a, created_cols, people_in_cam_a):
        p = people_in_cam_a[0]
        col = created_cols["select"]
        r = admin_session.patch(f"{API}/campaigns/{cam_a['id']}/cells/{p['id']}",
                                json={"column_id": col["id"], "value": "NotAnOption"})
        assert r.status_code == 400

    def test_set_text_cell_persists(self, admin_session, cam_a, created_cols, people_in_cam_a):
        p = people_in_cam_a[1]
        col = created_cols["text"]
        r = admin_session.patch(f"{API}/campaigns/{cam_a['id']}/cells/{p['id']}",
                                json={"column_id": col["id"], "value": "hello world"})
        assert r.status_code == 200
        q = admin_session.post(f"{API}/people/query",
                               json={"in_campaigns": [cam_a["id"]],
                                     "person_ids": [p["id"]], "limit": 5, "offset": 0})
        found = [x for x in q.json()["items"] if x["id"] == p["id"]][0]
        assert (found.get("custom_values") or {}).get(col["id"]) == "hello world"

    def test_set_checkbox_cell_persists(self, admin_session, cam_a, created_cols, people_in_cam_a):
        p = people_in_cam_a[0]
        col = created_cols["checkbox"]
        r = admin_session.patch(f"{API}/campaigns/{cam_a['id']}/cells/{p['id']}",
                                json={"column_id": col["id"], "value": True})
        assert r.status_code == 200
        q = admin_session.post(f"{API}/people/query",
                               json={"in_campaigns": [cam_a["id"]],
                                     "person_ids": [p["id"]], "limit": 5, "offset": 0})
        found = [x for x in q.json()["items"] if x["id"] == p["id"]][0]
        assert (found.get("custom_values") or {}).get(col["id"]) is True

    def test_clear_cell_by_empty(self, admin_session, cam_a, created_cols, people_in_cam_a):
        p = people_in_cam_a[1]
        col = created_cols["text"]
        # First ensure set
        admin_session.patch(f"{API}/campaigns/{cam_a['id']}/cells/{p['id']}",
                            json={"column_id": col["id"], "value": "to be cleared"})
        # Now clear
        r = admin_session.patch(f"{API}/campaigns/{cam_a['id']}/cells/{p['id']}",
                                json={"column_id": col["id"], "value": ""})
        assert r.status_code == 200
        q = admin_session.post(f"{API}/people/query",
                               json={"in_campaigns": [cam_a["id"]],
                                     "person_ids": [p["id"]], "limit": 5, "offset": 0})
        found = [x for x in q.json()["items"] if x["id"] == p["id"]][0]
        assert not (found.get("custom_values") or {}).get(col["id"])


# ---------- Value counts ----------
class TestValueCounts:
    def test_counts_reflect_sent_value(self, admin_session, cam_a, created_cols, people_in_cam_a):
        # ensure person[0] has 'Sent' set
        p = people_in_cam_a[0]
        col = created_cols["select"]
        admin_session.patch(f"{API}/campaigns/{cam_a['id']}/cells/{p['id']}",
                            json={"column_id": col["id"], "value": "Sent"})
        r = admin_session.get(f"{API}/campaigns/{cam_a['id']}/cell-value-counts")
        assert r.status_code == 200
        counts = r.json()["counts"].get(col["id"], [])
        values = {c["value"]: c["count"] for c in counts}
        assert values.get("Sent", 0) >= 1
        # Also should have __empty for people without value
        # (assuming there are >1 people in campaign)
        # Not asserted strictly since campaign may have exactly 1 person


# ---------- Custom filter in /people/query ----------
class TestCustomFilter:
    def test_filter_by_sent_value(self, admin_session, cam_a, created_cols, people_in_cam_a):
        p = people_in_cam_a[0]
        col = created_cols["select"]
        # ensure Sent
        admin_session.patch(f"{API}/campaigns/{cam_a['id']}/cells/{p['id']}",
                            json={"column_id": col["id"], "value": "Sent"})
        r = admin_session.post(f"{API}/people/query", json={
            "in_campaigns": [cam_a["id"]],
            "custom_filters": {col["id"]: ["Sent"]},
            "limit": 50, "offset": 0,
        })
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        ids = [x["id"] for x in items]
        assert p["id"] in ids
        # every returned person must have the value Sent
        for x in items:
            assert (x.get("custom_values") or {}).get(col["id"]) == "Sent"

    def test_filter_by_empty(self, admin_session, cam_a, created_cols, people_in_cam_a):
        col = created_cols["select"]
        # clear one person to guarantee an empty
        p_clear = people_in_cam_a[1]
        admin_session.patch(f"{API}/campaigns/{cam_a['id']}/cells/{p_clear['id']}",
                            json={"column_id": col["id"], "value": ""})
        r = admin_session.post(f"{API}/people/query", json={
            "in_campaigns": [cam_a["id"]],
            "custom_filters": {col["id"]: ["__empty"]},
            "limit": 50, "offset": 0,
        })
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert p_clear["id"] in [x["id"] for x in items]
        for x in items:
            assert not (x.get("custom_values") or {}).get(col["id"])


# ---------- Cross-campaign isolation ----------
class TestIsolation:
    def test_col_of_a_not_in_b(self, admin_session, cam_b, created_cols):
        r = admin_session.get(f"{API}/campaigns/{cam_b['id']}/columns")
        assert r.status_code == 200
        names = [c["name"] for c in r.json()["items"]]
        for k in ("select", "text", "checkbox"):
            assert created_cols[k]["name"] not in names, \
                f"campaign B leaked column {created_cols[k]['name']}"


# ---------- Delete ----------
class TestDelete:
    def test_delete_column_erases_cells(self, admin_session, cam_a, people_in_cam_a):
        # create a fresh column
        r = admin_session.post(f"{API}/campaigns/{cam_a['id']}/columns",
                               json={"name": "TEST_DEL_col", "kind": "text"})
        assert r.status_code == 200
        col = r.json()
        p = people_in_cam_a[0]
        admin_session.patch(f"{API}/campaigns/{cam_a['id']}/cells/{p['id']}",
                            json={"column_id": col["id"], "value": "will vanish"})
        # verify present
        q = admin_session.post(f"{API}/people/query",
                               json={"in_campaigns": [cam_a["id"]],
                                     "person_ids": [p["id"]], "limit": 5, "offset": 0})
        found = [x for x in q.json()["items"] if x["id"] == p["id"]][0]
        assert (found.get("custom_values") or {}).get(col["id"]) == "will vanish"

        # delete column
        d = admin_session.delete(f"{API}/campaigns/{cam_a['id']}/columns/{col['id']}")
        assert d.status_code == 200

        # column list no longer contains it
        L = admin_session.get(f"{API}/campaigns/{cam_a['id']}/columns")
        assert col["id"] not in [c["id"] for c in L.json()["items"]]

        # cell value cleared
        q2 = admin_session.post(f"{API}/people/query",
                                json={"in_campaigns": [cam_a["id"]],
                                      "person_ids": [p["id"]], "limit": 5, "offset": 0})
        f2 = [x for x in q2.json()["items"] if x["id"] == p["id"]][0]
        assert not (f2.get("custom_values") or {}).get(col["id"])


# ---------- Auth ----------
class TestAuth:
    def test_unauthenticated_rejected(self, cam_a):
        r = requests.get(f"{API}/campaigns/{cam_a['id']}/columns")
        assert r.status_code in (401, 403)
