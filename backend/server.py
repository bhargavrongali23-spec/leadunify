"""LeadUnify — FastAPI backend."""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import asyncio
import io
import json
import logging
import os
import re
import secrets
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional

import bcrypt
import jwt
import pandas as pd
from bson import ObjectId
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse, RedirectResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

from dedup import (
    clean_str,
    get_or_create_company,
    link_person_campaign,
    normalize_email,
    normalize_linkedin,
    normalize_phone,
    process_import_row,
)
from models import (
    Campaign,
    Company,
    ImportBatch,
    LoginInput,
    Person,
    RegisterInput,
    User,
    UserPublic,
    utc_now_iso,
)
from seed_data import seed_demo_data


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).parent

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 60 * 24  # 24h for internal tool convenience
REFRESH_TOKEN_DAYS = 30

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="LeadUnify")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("leadunify")

# ---------------------------------------------------------------------------
# Password hashing / JWT helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    # Frontend and backend share the same host through ingress (/api -> backend), so lax is fine.
    response.set_cookie(
        "access_token", access, httponly=True, secure=True, samesite="lax",
        max_age=ACCESS_TOKEN_MINUTES * 60, path="/",
    )
    response.set_cookie(
        "refresh_token", refresh, httponly=True, secure=True, samesite="lax",
        max_age=REFRESH_TOKEN_DAYS * 86400, path="/",
    )


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def _user_public(u: dict) -> dict:
    return {
        "id": u["_id"] if isinstance(u["_id"], str) else str(u["_id"]),
        "email": u["email"],
        "name": u.get("name", "User"),
        "role": u.get("role", "member"),
    }


async def _log_audit(user: dict, action: str, detail: dict) -> None:
    """Append an audit-log entry (merges, deletes, invites)."""
    await db.audit_log.insert_one({
        "action": action,
        "performed_by_id": str(user["_id"]),
        "performed_by_email": user.get("email"),
        "performed_by_name": user.get("name", "User"),
        "detail": detail,
        "created_at": utc_now_iso(),
    })


# ---------------------------------------------------------------------------
# Startup — indexes, admin seed, demo data
# ---------------------------------------------------------------------------
async def _startup() -> None:
    await db.users.create_index("email", unique=True)
    await db.people.create_index("primary_email")
    await db.people.create_index("additional_emails")
    await db.people.create_index("linkedin_url")
    await db.people.create_index("phones")
    await db.people.create_index("company_id")
    await db.people.create_index("company_name")
    await db.people.create_index("updated_at")
    await db.people.create_index("created_at")
    await db.people.create_index("full_name")
    await db.people.create_index([("full_name", "text"), ("primary_email", "text"), ("company_name", "text")])
    await db.companies.create_index("name")
    await db.companies.create_index("email_domain")
    await db.companies.create_index("canonical_name")
    await db.campaigns.create_index("name")
    await db.person_campaigns.create_index([("person_id", 1), ("campaign_id", 1)], unique=True)
    await db.person_campaigns.create_index("campaign_id")
    await db.person_campaigns.create_index("person_id")
    await db.duplicate_flags.create_index("status")
    await db.duplicate_flags.create_index("created_at")
    await db.import_batches.create_index("created_at")
    await db.saved_filters.create_index("owner_id")
    await db.oauth_states.create_index("created_at", expireAfterSeconds=900)
    await db.access_requests.create_index([("status", 1), ("created_at", -1)])
    await db.access_requests.create_index("user_id")
    await db.access_requests.create_index("campaign_id")
    await db.campaigns.create_index("owner_id")
    await db.campaigns.create_index("shared_with_user_ids")
    await db.audit_log.create_index([("created_at", -1)])
    await db.audit_log.create_index("action")
    await db.people.create_index("enrichment_flag")
    await db.campaign_columns.create_index([("campaign_id", 1), ("position", 1)])

    # seed admin
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@vaultedge.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Admin",
            "role": "admin",
            "created_at": utc_now_iso(),
        })
        logger.info("Seeded admin user")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password)}},
        )

    # Back-fill canonical_name for pre-existing companies (safe to run every startup)
    from dedup import normalize_company_name
    async for c in db.companies.find({"canonical_name": {"$in": [None, ""]}}, {"name": 1}):
        canon = normalize_company_name(c.get("name"))
        if canon:
            await db.companies.update_one({"_id": c["_id"]}, {"$set": {"canonical_name": canon}})

    # Ensure the admin owns any legacy campaign that has no owner_id
    admin = await db.users.find_one({"role": "admin"}, {"_id": 1})
    if admin:
        await db.campaigns.update_many(
            {"$or": [{"owner_id": None}, {"owner_id": {"$exists": False}}]},
            {"$set": {"owner_id": str(admin["_id"]), "shared_with_user_ids": []}},
        )

    # seed demo data (only if empty)
    result = await seed_demo_data(db)
    logger.info("Demo seed result: %s", result)


@app.on_event("startup")
async def _on_startup() -> None:
    await _startup()


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    client.close()


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@api.post("/auth/register")
async def register(payload: RegisterInput, response: Response):
    email = payload.email.strip().lower()
    if not email or not payload.password:
        raise HTTPException(status_code=400, detail="Email and password required")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="An account with this email already exists")
    doc = {
        "email": email,
        "password_hash": hash_password(payload.password),
        "name": payload.name or email.split("@")[0].capitalize(),
        "role": "member",
        "created_at": utc_now_iso(),
    }
    result = await db.users.insert_one(doc)
    user_id = str(result.inserted_id)
    access = create_access_token(user_id, email)
    refresh = create_refresh_token(user_id)
    _set_auth_cookies(response, access, refresh)
    doc["_id"] = user_id
    return {"user": _user_public(doc), "access_token": access}


@api.post("/auth/login")
async def login(payload: LoginInput, response: Response):
    email = payload.email.strip().lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user_id = str(user["_id"])
    access = create_access_token(user_id, email)
    refresh = create_refresh_token(user_id)
    _set_auth_cookies(response, access, refresh)
    user["_id"] = user_id
    return {"user": _user_public(user), "access_token": access}


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return _user_public(user)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------
def serialize_doc(doc: Optional[dict]) -> Optional[dict]:
    if doc is None:
        return None
    out = {}
    for k, v in doc.items():
        if k == "_id":
            out["id"] = str(v)
        elif isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------
@api.get("/companies")
async def list_companies(
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 200,
    _: dict = Depends(get_current_user),
):
    """Paginated companies list. Use page/page_size for scale. `q` is a
    case-insensitive substring match on the name."""
    query: dict = {}
    if q:
        query["name"] = {"$regex": re.escape(q), "$options": "i"}
    total = await db.companies.count_documents(query)
    page = max(1, page)
    page_size = max(1, min(page_size, 500))
    cursor = (
        db.companies.find(query)
        .sort("name", 1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    companies = [serialize_doc(d) async for d in cursor]
    if companies:
        ids = [c["id"] for c in companies]
        pipeline = [
            {"$match": {"company_id": {"$in": ids}}},
            {"$group": {"_id": "$company_id", "count": {"$sum": 1}}},
        ]
        counts = {d["_id"]: d["count"] async for d in db.people.aggregate(pipeline)}
        for c in companies:
            c["people_count"] = counts.get(c["id"], 0)
    return {"items": companies, "total": total, "page": page, "page_size": page_size}


@api.get("/companies/lookup/by-name")
async def lookup_company_by_name(name: str, _: dict = Depends(get_current_user)):
    """Find a company by its exact (case-insensitive) name — used by People
    view when navigating via ?company=<name>."""
    doc = await db.companies.find_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    )
    if not doc:
        return {"company": None}
    company = serialize_doc(doc)
    company["people_count"] = await db.people.count_documents({"company_id": company["id"]})
    return {"company": company}


@api.get("/companies/merge-candidates")
async def company_merge_candidates(_: dict = Depends(get_current_user)):
    """Return groups of companies that appear to be the same organization based
    on canonical_name (normalized form). Only groups with 2+ companies returned."""
    pipeline = [
        {"$match": {"canonical_name": {"$nin": [None, ""]}}},
        {"$group": {
            "_id": "$canonical_name",
            "companies": {"$push": {
                "id": {"$toString": "$_id"},
                "name": "$name",
                "email_domain": "$email_domain",
            }},
            "count": {"$sum": 1},
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}},
    ]
    groups = []
    async for g in db.companies.aggregate(pipeline):
        for c in g["companies"]:
            c["people_count"] = await db.people.count_documents({"company_id": c["id"]})
        groups.append({
            "canonical_name": g["_id"],
            "companies": g["companies"],
            "count": g["count"],
        })
    return {"groups": groups}


class CompanyMergeInput(BaseModel):
    keep_company_id: str
    merge_company_ids: List[str]


@api.post("/companies/merge")
async def merge_companies(payload: CompanyMergeInput, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        keep_oid = ObjectId(payload.keep_company_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid company id")
    keep = await db.companies.find_one({"_id": keep_oid})
    if not keep:
        raise HTTPException(status_code=404, detail="Company to keep not found")
    keep_id = str(keep["_id"])

    merged_ids = [mid for mid in payload.merge_company_ids if mid != keep_id]
    if not merged_ids:
        return {"ok": True, "moved": 0}

    result = await db.people.update_many(
        {"company_id": {"$in": merged_ids}},
        {"$set": {"company_id": keep_id, "company_name": keep["name"], "updated_at": utc_now_iso()}},
    )
    moved = result.modified_count

    disappearing = []
    async for c in db.companies.find(
        {"_id": {"$in": [ObjectId(m) for m in merged_ids if ObjectId.is_valid(m)]}}
    ):
        if c.get("notes"):
            disappearing.append(f"[from {c['name']}]\n{c['notes']}")
    if disappearing:
        merged_notes = keep.get("notes") or ""
        if merged_notes:
            merged_notes += "\n\n"
        merged_notes += "\n\n".join(disappearing)
        await db.companies.update_one({"_id": keep_oid}, {"$set": {"notes": merged_notes}})

    await db.companies.delete_many(
        {"_id": {"$in": [ObjectId(m) for m in merged_ids if ObjectId.is_valid(m)]}}
    )
    await _log_audit(user, "merge_companies", {
        "kept_id": keep_id,
        "kept_name": keep.get("name"),
        "merged_ids": merged_ids,
        "people_moved": moved,
    })
    return {"ok": True, "moved": moved, "deleted": len(merged_ids)}


class CompanyPatch(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None


@api.get("/companies/{company_id}")
async def get_company(company_id: str, _: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(company_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid company id")
    doc = await db.companies.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Company not found")
    doc = serialize_doc(doc)
    doc["people_count"] = await db.people.count_documents({"company_id": company_id})
    return doc


@api.patch("/companies/{company_id}")
async def update_company(
    company_id: str, payload: CompanyPatch, _: dict = Depends(get_current_user)
):
    try:
        oid = ObjectId(company_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid company id")
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if "name" in updates:
        from dedup import normalize_company_name
        updates["canonical_name"] = normalize_company_name(updates["name"])
    if not updates:
        return {"ok": True}
    await db.companies.update_one({"_id": oid}, {"$set": updates})
    doc = await db.companies.find_one({"_id": oid})
    return serialize_doc(doc)


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------
class CampaignInput(BaseModel):
    name: str
    category: Optional[str] = None
    status: Optional[str] = "Active"
    description: Optional[str] = None


@api.get("/campaigns")
async def list_campaigns(scope: str = "mine", user: dict = Depends(get_current_user)):
    """List campaigns.

    scope='mine' (default) — admins see all, members see owned + shared.
    scope='all' — admin sees all; members also see all so they can request access.
    """
    is_admin = user.get("role") == "admin"
    uid = str(user["_id"])
    query: dict = {}
    if not is_admin and scope != "all":
        query = {
            "$or": [
                {"owner_id": uid},
                {"shared_with_user_ids": uid},
                {"owner_id": None},  # legacy campaigns w/o owner remain visible
            ]
        }
    cursor = db.campaigns.find(query).sort("created_at", -1)
    campaigns = [serialize_doc(d) async for d in cursor]
    if campaigns:
        pipeline = [
            {"$group": {"_id": "$campaign_id", "count": {"$sum": 1}}},
        ]
        counts = {d["_id"]: d["count"] async for d in db.person_campaigns.aggregate(pipeline)}
        for c in campaigns:
            c["people_count"] = counts.get(c["id"], 0)
            c["is_owner"] = (c.get("owner_id") == uid)
            c["is_shared_with_me"] = uid in (c.get("shared_with_user_ids") or [])
            c["has_access"] = is_admin or c["is_owner"] or c["is_shared_with_me"] or c.get("owner_id") is None
    return {"items": campaigns}


@api.post("/campaigns")
async def create_campaign(payload: CampaignInput, user: dict = Depends(get_current_user)):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Campaign name required")
    doc = {
        "name": payload.name.strip(),
        "category": payload.category,
        "status": payload.status or "Active",
        "description": payload.description,
        "owner_id": str(user["_id"]),
        "shared_with_user_ids": [],
        "created_at": utc_now_iso(),
    }
    result = await db.campaigns.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_doc(doc)


@api.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, _: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(campaign_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign id")
    doc = await db.campaigns.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Campaign not found")
    doc = serialize_doc(doc)
    doc["people_count"] = await db.person_campaigns.count_documents({"campaign_id": campaign_id})

    # overlap indicator — how many people in this campaign are also in >=1 other active campaign
    pipeline = [
        {"$match": {"campaign_id": campaign_id}},
        {"$lookup": {
            "from": "person_campaigns",
            "let": {"pid": "$person_id"},
            "pipeline": [
                {"$match": {
                    "$expr": {
                        "$and": [
                            {"$eq": ["$person_id", "$$pid"]},
                            {"$ne": ["$campaign_id", campaign_id]},
                        ]
                    }
                }},
            ],
            "as": "others",
        }},
        {"$match": {"others.0": {"$exists": True}}},
        {"$count": "overlap"},
    ]
    overlap = 0
    async for r in db.person_campaigns.aggregate(pipeline):
        overlap = r.get("overlap", 0)
    doc["overlap_count"] = overlap
    return doc


class CampaignPatch(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None


@api.patch("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: str, payload: CampaignPatch, user: dict = Depends(get_current_user)
):
    try:
        oid = ObjectId(campaign_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign id")
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not updates:
        return {"ok": True}
    await db.campaigns.update_one({"_id": oid}, {"$set": updates})
    doc = await db.campaigns.find_one({"_id": oid})
    return serialize_doc(doc)


@api.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        oid = ObjectId(campaign_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign id")
    await db.campaigns.delete_one({"_id": oid})
    await db.person_campaigns.delete_many({"campaign_id": campaign_id})
    await db.campaign_columns.delete_many({"campaign_id": campaign_id})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Campaign custom columns (Excel-like extra fields, PER campaign)
# ---------------------------------------------------------------------------
class CampaignColumnInput(BaseModel):
    name: str
    kind: str = "text"  # "text" | "select" | "checkbox"
    options: Optional[List[str]] = None
    position: Optional[int] = None


class CampaignColumnPatch(BaseModel):
    name: Optional[str] = None
    options: Optional[List[str]] = None
    position: Optional[int] = None


class CampaignCellInput(BaseModel):
    column_id: str
    value: Any = None  # str | bool | None


async def _assert_campaign_access(campaign_id: str, user: dict) -> dict:
    """Return the campaign doc if the user has access, else 403/404."""
    try:
        oid = ObjectId(campaign_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign id")
    camp = await db.campaigns.find_one({"_id": oid})
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
    uid = str(user["_id"])
    is_admin = user.get("role") == "admin"
    if not is_admin and camp.get("owner_id") not in (None, uid) and uid not in (camp.get("shared_with_user_ids") or []):
        raise HTTPException(status_code=403, detail="You don't have access to this campaign")
    return camp


@api.get("/campaigns/{campaign_id}/columns")
async def list_campaign_columns(campaign_id: str, user: dict = Depends(get_current_user)):
    await _assert_campaign_access(campaign_id, user)
    cursor = db.campaign_columns.find({"campaign_id": campaign_id}).sort("position", 1)
    return {"items": [serialize_doc(d) async for d in cursor]}


@api.post("/campaigns/{campaign_id}/columns")
async def create_campaign_column(
    campaign_id: str, payload: CampaignColumnInput, user: dict = Depends(get_current_user)
):
    await _assert_campaign_access(campaign_id, user)
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Column name required")
    if payload.kind not in ("text", "select", "checkbox"):
        raise HTTPException(status_code=400, detail="Kind must be text, select, or checkbox")
    if payload.kind == "select" and not (payload.options or []):
        raise HTTPException(status_code=400, detail="Select columns need at least one option")

    if payload.position is None:
        max_pos = 0
        async for d in db.campaign_columns.find({"campaign_id": campaign_id}, {"position": 1}).sort("position", -1).limit(1):
            max_pos = int(d.get("position") or 0)
        position = max_pos + 1
    else:
        position = payload.position

    doc = {
        "campaign_id": campaign_id,
        "name": payload.name.strip(),
        "kind": payload.kind,
        "options": payload.options or [],
        "position": position,
        "created_at": utc_now_iso(),
        "created_by": user.get("email"),
    }
    result = await db.campaign_columns.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_doc(doc)


@api.patch("/campaigns/{campaign_id}/columns/{column_id}")
async def update_campaign_column(
    campaign_id: str, column_id: str, payload: CampaignColumnPatch, user: dict = Depends(get_current_user)
):
    await _assert_campaign_access(campaign_id, user)
    try:
        oid = ObjectId(column_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid column id")
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if "name" in updates:
        updates["name"] = updates["name"].strip()
    if not updates:
        return {"ok": True}
    await db.campaign_columns.update_one({"_id": oid, "campaign_id": campaign_id}, {"$set": updates})
    doc = await db.campaign_columns.find_one({"_id": oid})
    return serialize_doc(doc)


@api.delete("/campaigns/{campaign_id}/columns/{column_id}")
async def delete_campaign_column(
    campaign_id: str, column_id: str, user: dict = Depends(get_current_user)
):
    await _assert_campaign_access(campaign_id, user)
    try:
        oid = ObjectId(column_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid column id")
    await db.campaign_columns.delete_one({"_id": oid, "campaign_id": campaign_id})
    # Remove any cell values under that column key across the campaign
    await db.person_campaigns.update_many(
        {"campaign_id": campaign_id},
        {"$unset": {f"custom_values.{column_id}": ""}},
    )
    return {"ok": True}


@api.patch("/campaigns/{campaign_id}/cells/{person_id}")
async def update_campaign_cell(
    campaign_id: str, person_id: str, payload: CampaignCellInput, user: dict = Depends(get_current_user)
):
    """Set (or clear) one custom-column cell value for a person in a campaign."""
    await _assert_campaign_access(campaign_id, user)
    # Ensure the link exists — if not, create it (adding the person to the campaign implicitly).
    link = await db.person_campaigns.find_one({"person_id": person_id, "campaign_id": campaign_id})
    if not link:
        await db.person_campaigns.insert_one({
            "person_id": person_id,
            "campaign_id": campaign_id,
            "status": "Not Contacted",
            "added_at": utc_now_iso(),
            "custom_values": {},
        })
    # Validate column exists
    try:
        col_oid = ObjectId(payload.column_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid column id")
    column = await db.campaign_columns.find_one({"_id": col_oid, "campaign_id": campaign_id})
    if not column:
        raise HTTPException(status_code=404, detail="Column not found")

    key = f"custom_values.{payload.column_id}"
    if payload.value is None or payload.value == "":
        await db.person_campaigns.update_one(
            {"person_id": person_id, "campaign_id": campaign_id},
            {"$unset": {key: ""}},
        )
    else:
        # For select columns, ensure value is one of options (or fall through if list is empty)
        if column["kind"] == "select" and column.get("options") and payload.value not in column["options"]:
            raise HTTPException(status_code=400, detail=f"Value must be one of: {', '.join(column['options'])}")
        await db.person_campaigns.update_one(
            {"person_id": person_id, "campaign_id": campaign_id},
            {"$set": {key: payload.value}},
        )
    return {"ok": True}


@api.get("/campaigns/{campaign_id}/cell-value-counts")
async def cell_value_counts(campaign_id: str, user: dict = Depends(get_current_user)):
    """Return distinct value counts per column for the campaign — used to
    render the Excel-like filter popover with real distributions."""
    await _assert_campaign_access(campaign_id, user)
    columns = [serialize_doc(c) async for c in db.campaign_columns.find({"campaign_id": campaign_id})]
    result: dict = {}
    total_links = await db.person_campaigns.count_documents({"campaign_id": campaign_id})
    for col in columns:
        cid = col["id"]
        pipeline = [
            {"$match": {"campaign_id": campaign_id}},
            {"$group": {"_id": f"$custom_values.{cid}", "count": {"$sum": 1}}},
        ]
        counts = []
        with_value = 0
        async for d in db.person_campaigns.aggregate(pipeline):
            v = d["_id"]
            if v is None or v == "":
                continue
            counts.append({"value": v, "count": d["count"]})
            with_value += d["count"]
        empty = total_links - with_value
        if empty > 0:
            counts.append({"value": "__empty", "count": empty, "label": "(empty)"})
        result[cid] = counts
    return {"counts": result}


# ---------------------------------------------------------------------------
# People — list / filter / detail
# ---------------------------------------------------------------------------
async def _build_people_query(filters: dict) -> dict:
    """Build MongoDB filter query from the standardized filter payload."""
    q: dict = {}
    ands: list = []

    text = (filters.get("search") or "").strip()
    if text:
        # case-insensitive substring across common fields
        regex = re.escape(text)
        ands.append({"$or": [
            {"full_name": {"$regex": regex, "$options": "i"}},
            {"primary_email": {"$regex": regex, "$options": "i"}},
            {"additional_emails": {"$regex": regex, "$options": "i"}},
            {"company_name": {"$regex": regex, "$options": "i"}},
            {"job_title": {"$regex": regex, "$options": "i"}},
            {"linkedin_url": {"$regex": regex, "$options": "i"}},
        ]})

    if filters.get("company_id"):
        ands.append({"company_id": filters["company_id"]})
    if filters.get("company_name"):
        # Case-insensitive SUBSTRING match, so typing "HDFC" finds "HDFC Bank".
        ands.append({
            "company_name": {"$regex": re.escape(filters["company_name"]), "$options": "i"}
        })
    if filters.get("in_companies"):
        # Match by exact company_id OR by exact company_name (any of the given).
        cids = filters["in_companies"]
        ands.append({
            "$or": [
                {"company_id": {"$in": cids}},
                {"company_name": {"$in": cids}},
            ]
        })

    if filters.get("tag"):
        ands.append({"tags": filters["tag"]})

    if filters.get("source"):
        ands.append({"sources.source_name": {"$regex": re.escape(filters["source"]), "$options": "i"}})

    # in_campaigns: person is in ANY of the selected campaigns (OR/union)
    include_ids = filters.get("in_campaigns") or []
    if include_ids:
        pids = set()
        cursor = db.person_campaigns.find(
            {"campaign_id": {"$in": include_ids}}, {"person_id": 1}
        )
        async for d in cursor:
            pids.add(d["person_id"])
        ands.append({"_id": {"$in": [ObjectId(p) for p in pids if ObjectId.is_valid(p)]}})

    # not_in_campaigns: person MUST NOT be in any of these
    exclude_ids = filters.get("not_in_campaigns") or []
    if exclude_ids:
        pids = set()
        cursor = db.person_campaigns.find({"campaign_id": {"$in": exclude_ids}}, {"person_id": 1})
        async for d in cursor:
            pids.add(d["person_id"])
        ands.append({"_id": {"$nin": [ObjectId(p) for p in pids]}})

    # created after (for "added in last N days")
    if filters.get("created_after"):
        ands.append({"created_at": {"$gte": filters["created_after"]}})

    if filters.get("needs_enrichment"):
        ands.append({"enrichment_flag": True})

    # Custom-column filters — apply only when exactly one campaign is in `in_campaigns`
    # (custom columns belong to a specific campaign).
    custom = filters.get("custom_filters") or {}
    in_ids = filters.get("in_campaigns") or []
    if custom and len(in_ids) == 1:
        campaign_id = in_ids[0]
        # For each column filter, gather person_ids whose cell value is in allowed set.
        for column_id, allowed in custom.items():
            if not allowed:
                continue
            allowed_set = list(allowed) if isinstance(allowed, list) else [allowed]
            pids = set()
            # "__empty" is a sentinel meaning "cell is missing / empty"
            include_empty = "__empty" in allowed_set
            concrete = [v for v in allowed_set if v != "__empty"]
            key = f"custom_values.{column_id}"
            or_clauses: List[dict] = []
            if concrete:
                or_clauses.append({key: {"$in": concrete}})
            if include_empty:
                or_clauses.append({key: {"$in": [None, ""]}})
                or_clauses.append({key: {"$exists": False}})
            cursor = db.person_campaigns.find(
                {"campaign_id": campaign_id, "$or": or_clauses} if or_clauses else {"campaign_id": campaign_id},
                {"person_id": 1},
            )
            async for d in cursor:
                pids.add(d["person_id"])
            ands.append({"_id": {"$in": [ObjectId(p) for p in pids if ObjectId.is_valid(p)]}})

    if ands:
        q["$and"] = ands
    return q


async def _hydrate_people(docs: List[dict], single_campaign_id: Optional[str] = None) -> List[dict]:
    """Attach campaign chips to each person.
    If `single_campaign_id` is provided, also attach that campaign's custom
    cell values (from person_campaigns.custom_values) under key `custom_values`.
    """
    if not docs:
        return []
    ids = [str(d["_id"]) for d in docs]
    # bulk load links
    links: dict[str, list] = {}
    custom_by_person: dict[str, dict] = {}
    async for link in db.person_campaigns.find({"person_id": {"$in": ids}}):
        links.setdefault(link["person_id"], []).append(link["campaign_id"])
        if single_campaign_id and link.get("campaign_id") == single_campaign_id:
            custom_by_person[link["person_id"]] = link.get("custom_values") or {}
    # bulk load campaigns
    campaign_ids = list({c for arr in links.values() for c in arr})
    campaigns: dict[str, dict] = {}
    if campaign_ids:
        oids = [ObjectId(c) for c in campaign_ids if ObjectId.is_valid(c)]
        async for c in db.campaigns.find({"_id": {"$in": oids}}):
            campaigns[str(c["_id"])] = {"id": str(c["_id"]), "name": c["name"], "status": c.get("status", "Active")}
    out = []
    for d in docs:
        s = serialize_doc(d)
        s["campaigns"] = [campaigns[cid] for cid in links.get(s["id"], []) if cid in campaigns]
        if single_campaign_id:
            s["custom_values"] = custom_by_person.get(s["id"], {})
        out.append(s)
    return out


class PeopleQuery(BaseModel):
    search: Optional[str] = None
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    in_companies: Optional[List[str]] = None
    tag: Optional[str] = None
    source: Optional[str] = None
    in_campaigns: Optional[List[str]] = None
    not_in_campaigns: Optional[List[str]] = None
    created_after: Optional[str] = None
    needs_enrichment: Optional[bool] = None
    # {column_id: [allowed values]} — only applied when `in_campaigns` narrows to
    # exactly one campaign that owns those columns.
    custom_filters: Optional[dict] = None
    page: int = 1
    page_size: int = 25
    sort_by: Optional[str] = "updated_at"
    sort_dir: Optional[str] = "desc"


@api.post("/people/query")
async def query_people(payload: PeopleQuery, _: dict = Depends(get_current_user)):
    filters = payload.model_dump()
    q = await _build_people_query(filters)
    total = await db.people.count_documents(q)
    sort_dir = -1 if (payload.sort_dir or "desc").lower() == "desc" else 1
    sort_by = payload.sort_by or "updated_at"
    page = max(1, payload.page)
    size = max(1, min(payload.page_size, 200))
    cursor = db.people.find(q).sort(sort_by, sort_dir).skip((page - 1) * size).limit(size)
    docs = [d async for d in cursor]
    single_campaign_id = payload.in_campaigns[0] if payload.in_campaigns and len(payload.in_campaigns) == 1 else None
    items = await _hydrate_people(docs, single_campaign_id=single_campaign_id)
    return {"items": items, "total": total, "page": page, "page_size": size}


@api.get("/people/{person_id}")
async def get_person(person_id: str, _: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person id")
    doc = await db.people.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Person not found")
    hydrated = await _hydrate_people([doc])
    result = hydrated[0]
    # attach campaign link status
    links = {}
    async for link in db.person_campaigns.find({"person_id": person_id}):
        links[link["campaign_id"]] = {
            "status": link.get("status", "Not Contacted"),
            "added_at": link.get("added_at"),
        }
    for c in result["campaigns"]:
        c.update(links.get(c["id"], {}))
    return result


class PersonPatch(BaseModel):
    full_name: Optional[str] = None
    primary_email: Optional[str] = None
    linkedin_url: Optional[str] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    additional_emails: Optional[List[str]] = None
    phones: Optional[List[str]] = None


@api.patch("/people/{person_id}")
async def update_person(person_id: str, payload: PersonPatch, _: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person id")
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if "primary_email" in updates:
        e = normalize_email(updates["primary_email"])
        if not e:
            raise HTTPException(status_code=400, detail="Invalid email")
        updates["primary_email"] = e
    if "linkedin_url" in updates:
        updates["linkedin_url"] = normalize_linkedin(updates["linkedin_url"])
    if "company_name" in updates:
        cname = clean_str(updates["company_name"])
        cid, resolved = await get_or_create_company(db, cname, None)
        updates["company_id"] = cid
        updates["company_name"] = resolved
    updates["updated_at"] = utc_now_iso()
    await db.people.update_one({"_id": oid}, {"$set": updates})
    doc = await db.people.find_one({"_id": oid})
    return (await _hydrate_people([doc]))[0]


class PersonCampaignInput(BaseModel):
    campaign_id: str
    status: Optional[str] = "Not Contacted"


@api.post("/people/{person_id}/campaigns")
async def add_person_campaign(
    person_id: str, payload: PersonCampaignInput, _: dict = Depends(get_current_user)
):
    try:
        ObjectId(person_id)
        ObjectId(payload.campaign_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    existing = await db.person_campaigns.find_one({
        "person_id": person_id, "campaign_id": payload.campaign_id,
    })
    if existing:
        return {"ok": True, "already_in": True}
    # collect other campaigns the person is in for the "heads up"
    other_ids = [d["campaign_id"] async for d in db.person_campaigns.find(
        {"person_id": person_id}, {"campaign_id": 1}
    )]
    other_names = []
    if other_ids:
        oids = [ObjectId(c) for c in other_ids if ObjectId.is_valid(c)]
        async for c in db.campaigns.find({"_id": {"$in": oids}}):
            other_names.append(c["name"])
    await db.person_campaigns.insert_one({
        "person_id": person_id,
        "campaign_id": payload.campaign_id,
        "status": payload.status or "Not Contacted",
        "added_at": utc_now_iso(),
    })
    return {"ok": True, "already_in": False, "other_campaigns": other_names}


@api.delete("/people/{person_id}/campaigns/{campaign_id}")
async def remove_person_campaign(
    person_id: str, campaign_id: str, _: dict = Depends(get_current_user)
):
    await db.person_campaigns.delete_one({"person_id": person_id, "campaign_id": campaign_id})
    return {"ok": True}


class MergeInput(BaseModel):
    keep_person_id: str
    merge_person_id: str


@api.post("/people/merge")
async def merge_people(payload: MergeInput, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        keep_oid = ObjectId(payload.keep_person_id)
        merge_oid = ObjectId(payload.merge_person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ids")
    keep = await db.people.find_one({"_id": keep_oid})
    merge = await db.people.find_one({"_id": merge_oid})
    if not keep or not merge:
        raise HTTPException(status_code=404, detail="Person not found")

    # merge scalar fields (keep -> preserve existing values)
    ops: dict = {"$set": {}, "$addToSet": {}}
    for field in ["linkedin_url", "job_title", "company_id", "company_name"]:
        if not keep.get(field) and merge.get(field):
            ops["$set"][field] = merge[field]

    add_emails = set(keep.get("additional_emails") or [])
    if merge.get("primary_email") and merge["primary_email"] != keep.get("primary_email"):
        add_emails.add(merge["primary_email"])
    for e in merge.get("additional_emails") or []:
        if e != keep.get("primary_email"):
            add_emails.add(e)
    if add_emails - set(keep.get("additional_emails") or []):
        ops["$addToSet"]["additional_emails"] = {"$each": list(add_emails)}

    keep_phones = set(keep.get("phones") or [])
    new_phones = [p for p in (merge.get("phones") or []) if p not in keep_phones]
    if new_phones:
        ops["$addToSet"]["phones"] = {"$each": new_phones}

    keep_sources = keep.get("sources") or []  # noqa: F841
    merge_sources = merge.get("sources") or []
    if merge_sources:
        ops["$addToSet"]["sources"] = {"$each": merge_sources}

    ops["$set"]["updated_at"] = utc_now_iso()
    # clean empty operators
    if not ops["$set"]:
        ops.pop("$set")
    if not ops["$addToSet"]:
        ops.pop("$addToSet")

    if ops:
        await db.people.update_one({"_id": keep_oid}, ops)

    # move person_campaigns from merge -> keep
    async for link in db.person_campaigns.find({"person_id": payload.merge_person_id}):
        existing = await db.person_campaigns.find_one({
            "person_id": payload.keep_person_id,
            "campaign_id": link["campaign_id"],
        })
        if not existing:
            await db.person_campaigns.insert_one({
                "person_id": payload.keep_person_id,
                "campaign_id": link["campaign_id"],
                "status": link.get("status", "Not Contacted"),
                "added_at": link.get("added_at", utc_now_iso()),
            })
    await db.person_campaigns.delete_many({"person_id": payload.merge_person_id})
    await db.people.delete_one({"_id": merge_oid})
    await _log_audit(user, "merge_people", {
        "kept_id": payload.keep_person_id,
        "kept_name": keep.get("full_name"),
        "kept_email": keep.get("primary_email"),
        "merged_id": payload.merge_person_id,
        "merged_name": merge.get("full_name"),
        "merged_email": merge.get("primary_email"),
    })
    return {"ok": True}


@api.delete("/people/{person_id}")
async def delete_person(person_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person id")
    await db.people.delete_one({"_id": oid})
    await db.person_campaigns.delete_many({"person_id": person_id})
    return {"ok": True}


class BulkDeleteInput(BaseModel):
    ids: List[str]


@api.post("/people/{person_id}/flag-enrichment")
async def flag_person_for_enrichment(person_id: str, user: dict = Depends(get_current_user)):
    """Queue a person for future contact-discovery enrichment (Lusha / LinkedIn
    Sales Navigator). No external call is made yet — this is a placeholder flag
    the team can filter on."""
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person id")
    person = await db.people.find_one({"_id": oid})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    await db.people.update_one({"_id": oid}, {"$set": {
        "enrichment_flag": True,
        "enrichment_flagged_at": utc_now_iso(),
        "enrichment_flagged_by": user["email"],
        "updated_at": utc_now_iso(),
    }})
    return {"ok": True, "flagged": True}


@api.post("/people/{person_id}/unflag-enrichment")
async def unflag_person_for_enrichment(person_id: str, user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person id")
    await db.people.update_one({"_id": oid}, {"$set": {
        "enrichment_flag": False,
        "enrichment_flagged_at": None,
        "enrichment_flagged_by": None,
        "updated_at": utc_now_iso(),
    }})
    return {"ok": True, "flagged": False}


@api.post("/people/bulk-delete")
async def bulk_delete_people(payload: BulkDeleteInput, user: dict = Depends(get_current_user)):
    """Completely remove the selected people (from every campaign, every list)."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if not payload.ids:
        return {"ok": True, "deleted": 0}
    oids = [ObjectId(i) for i in payload.ids if ObjectId.is_valid(i)]
    result = await db.people.delete_many({"_id": {"$in": oids}})
    await db.person_campaigns.delete_many({"person_id": {"$in": payload.ids}})
    return {"ok": True, "deleted": result.deleted_count}


class BulkRemoveFromCampaignInput(BaseModel):
    ids: List[str]
    campaign_id: str


@api.post("/people/bulk-remove-from-campaign")
async def bulk_remove_from_campaign(
    payload: BulkRemoveFromCampaignInput, user: dict = Depends(get_current_user)
):
    """Remove the selected people from ONE specific campaign only. Their
    Person records and other campaign links stay intact."""
    if not payload.ids:
        return {"ok": True, "removed": 0}
    result = await db.person_campaigns.delete_many({
        "person_id": {"$in": payload.ids},
        "campaign_id": payload.campaign_id,
    })
    return {"ok": True, "removed": result.deleted_count}


def _is_non_empty_people_filter(payload_dict: dict) -> bool:
    """Guard rail: bulk-by-filter endpoints must have at least ONE narrowing
    field or they would iterate the whole people collection. Fields that just
    control pagination/sorting do NOT count."""
    ignore = {"page", "page_size", "sort", "sort_order", "sort_by", "sort_dir", "campaign_id"}
    for k, v in payload_dict.items():
        if k in ignore:
            continue
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        if isinstance(v, (list, dict)) and len(v) == 0:
            continue
        return True
    return False


@api.post("/people/delete-by-filter")
async def delete_people_by_filter(payload: PeopleQuery, user: dict = Depends(get_current_user)):
    """Delete EVERY person matching the given filter (all pages, not just
    visible). Admin only. Returns how many were removed."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if not _is_non_empty_people_filter(payload.model_dump()):
        raise HTTPException(
            status_code=400,
            detail="Refusing to delete without at least one filter — this would remove every contact.",
        )
    q = await _build_people_query(payload.model_dump())
    # Collect all matching ids first so we can also purge their person_campaigns.
    ids: List[str] = []
    async for d in db.people.find(q, {"_id": 1}):
        ids.append(str(d["_id"]))
    if not ids:
        return {"ok": True, "deleted": 0}
    oids = [ObjectId(i) for i in ids if ObjectId.is_valid(i)]
    result = await db.people.delete_many({"_id": {"$in": oids}})
    await db.person_campaigns.delete_many({"person_id": {"$in": ids}})
    return {"ok": True, "deleted": result.deleted_count}


class RemoveByFilterFromCampaignInput(PeopleQuery):
    campaign_id: str


@api.post("/people/remove-by-filter-from-campaign")
async def remove_by_filter_from_campaign(
    payload: RemoveByFilterFromCampaignInput, user: dict = Depends(get_current_user)
):
    """Remove EVERY person matching the given filter from a specific campaign.
    The person records themselves stay; only the person_campaigns links are
    dropped for the specified campaign."""
    # Owner-or-admin gate — you can only bulk-remove people from a campaign you
    # actually own (or if you're an admin).
    if not ObjectId.is_valid(payload.campaign_id):
        raise HTTPException(status_code=404, detail="Campaign not found")
    camp = await db.campaigns.find_one({"_id": ObjectId(payload.campaign_id)})
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if user.get("role") != "admin" and camp.get("owner_id") != str(user["_id"]):
        raise HTTPException(status_code=403, detail="Only the campaign owner or an admin can bulk-remove")
    filter_dict = payload.model_dump(exclude={"campaign_id"})
    if not _is_non_empty_people_filter(filter_dict):
        raise HTTPException(
            status_code=400,
            detail="Refusing to remove without at least one filter — this would clear the whole campaign.",
        )
    q = await _build_people_query(filter_dict)
    ids: List[str] = []
    async for d in db.people.find(q, {"_id": 1}):
        ids.append(str(d["_id"]))
    if not ids:
        return {"ok": True, "removed": 0}
    result = await db.person_campaigns.delete_many({
        "person_id": {"$in": ids},
        "campaign_id": payload.campaign_id,
    })
    return {"ok": True, "removed": result.deleted_count}


# ---------------------------------------------------------------------------
# Import — preview + commit
# ---------------------------------------------------------------------------
STANDARD_FIELDS = ["full_name", "first_name", "last_name", "primary_email", "phone", "linkedin_url", "company_name", "job_title", "notes"]

HEADER_HINTS: dict[str, list[str]] = {
    "full_name": [
        "name", "full name", "fullname", "contact", "contact name",
        "person", "person name", "prospect", "lead name", "customer name",
    ],
    "first_name": ["first name", "first", "firstname", "given name", "fname"],
    "last_name": ["last name", "last", "lastname", "surname", "family name", "lname"],
    "primary_email": [
        "email", "e-mail", "email address", "mail", "work email",
        "business email", "primary email", "contact email",
    ],
    "phone": [
        "phone", "mobile", "cell", "cellular", "telephone", "tel",
        "contact number", "phone number", "mobile number", "cell number",
        "work phone", "office phone",
    ],
    "linkedin_url": [
        "linkedin", "linkedin url", "linkedin profile", "linkedin link",
        "li", "linkedin.com", "profile url", "linkedin profile url",
    ],
    "company_name": [
        "company", "organization", "organisation", "org", "employer",
        "company name", "workplace", "firm", "business", "account",
    ],
    "job_title": [
        "title", "job title", "role", "position", "designation",
        "job", "job role", "job position",
    ],
    "notes": ["notes", "note", "comments", "comment", "remarks", "description", "about"],
}


def _norm_header(h: str) -> str:
    """Normalize a header for matching: lowercase, remove punctuation."""
    if not h:
        return ""
    s = str(h).strip().lower()
    s = re.sub(r"[_\-.]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _suggest_mapping(headers: list[str]) -> dict[str, str]:
    """Suggest a best-guess mapping of standard fields to sheet headers.

    Strategy: score every (field, header) pair, then greedily assign the
    strongest matches first. This prevents a weak match on one field from
    stealing a header that another field would match more strongly.

    Rank scale (lower = stronger):
        0 — header text equals the field key
        1 — header exactly equals a hint (or same set of words as a hint)
        2 — hint and header share at least one word
        3 — hint appears as a substring of header (or vice versa)
    """
    normalized = [_norm_header(h) for h in headers]
    candidates: list[tuple[int, int, str, int]] = []  # (rank, field_priority, field, header_idx)

    field_priority = {name: i for i, name in enumerate(STANDARD_FIELDS)}

    for field, hints in HEADER_HINTS.items():
        for i, n in enumerate(normalized):
            if not n:
                continue

            best_rank = None
            field_as_phrase = field.replace("_", " ")

            if n == field or n == field_as_phrase:
                best_rank = 0
            else:
                words_n = set(n.split())
                for hint in hints:
                    if n == hint:
                        best_rank = 1
                        break
                    words_h = set(hint.split())
                    if words_n and words_n == words_h:
                        best_rank = min(best_rank if best_rank is not None else 99, 1)
                    if words_n & words_h:
                        best_rank = min(best_rank if best_rank is not None else 99, 2)
                    if hint in n or n in hint:
                        best_rank = min(best_rank if best_rank is not None else 99, 3)

            if best_rank is not None:
                candidates.append((best_rank, field_priority.get(field, 99), field, i))

    candidates.sort()

    mapping: dict[str, str] = {}
    used_fields: set[str] = set()
    used_headers: set[int] = set()
    for _rank, _prio, field, idx in candidates:
        if field in used_fields or idx in used_headers:
            continue
        mapping[field] = headers[idx]
        used_fields.add(field)
        used_headers.add(idx)

    return mapping


def _read_sheet(file_bytes: bytes, filename: str) -> tuple[list[str], list[dict], str]:
    name_lower = filename.lower()
    if name_lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes), dtype=str).fillna("")
        return list(df.columns), df.to_dict(orient="records"), "csv"
    df = pd.read_excel(io.BytesIO(file_bytes), dtype=str, engine="openpyxl").fillna("")
    return list(df.columns), df.to_dict(orient="records"), "xlsx"


# In-memory staged files: token -> (headers, rows, filename)
_STAGED: dict[str, tuple[list[str], list[dict], str]] = {}


@api.post("/import/preview")
async def import_preview(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    try:
        headers, rows, kind = _read_sheet(content, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

    suggested = _suggest_mapping(headers)
    if "primary_email" not in suggested:
        # not a hard failure — user might map manually
        pass

    token = secrets.token_urlsafe(16)
    _STAGED[token] = (headers, rows, file.filename)

    return {
        "token": token,
        "file_name": file.filename,
        "kind": kind,
        "headers": headers,
        "suggested_mapping": suggested,
        "preview_rows": rows[:10],
        "total_rows": len(rows),
    }


class ImportCommit(BaseModel):
    token: str
    mapping: dict  # {standard_field: header_name}
    campaign_id: Optional[str] = None
    new_campaign_name: Optional[str] = None
    new_campaign_category: Optional[str] = None


@api.post("/import/commit")
async def import_commit(payload: ImportCommit, user: dict = Depends(get_current_user)):
    staged = _STAGED.get(payload.token)
    if not staged:
        raise HTTPException(status_code=400, detail="Upload token expired — please re-upload the file")
    headers, rows, filename = staged

    identifier_fields = {"primary_email", "linkedin_url", "phone"}
    name_fields = {"full_name", "first_name", "last_name"}
    has_identifier = any(f in payload.mapping and payload.mapping[f] for f in identifier_fields)
    has_name = any(f in payload.mapping and payload.mapping[f] for f in name_fields)
    if not has_identifier and not has_name:
        raise HTTPException(
            status_code=400,
            detail=(
                "Map at least one column to a standard field. Recommended: Email, LinkedIn or "
                "Phone (used to detect duplicates) — or a Name column."
            ),
        )

    # Resolve campaign
    if payload.campaign_id:
        try:
            oid = ObjectId(payload.campaign_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid campaign id")
        camp = await db.campaigns.find_one({"_id": oid})
        if not camp:
            raise HTTPException(status_code=404, detail="Campaign not found")
        campaign_id = payload.campaign_id
        campaign_name = camp["name"]
    else:
        if not payload.new_campaign_name or not payload.new_campaign_name.strip():
            raise HTTPException(status_code=400, detail="Provide a campaign name")
        result = await db.campaigns.insert_one({
            "name": payload.new_campaign_name.strip(),
            "category": payload.new_campaign_category,
            "status": "Active",
            "description": None,
            "created_at": utc_now_iso(),
        })
        campaign_id = str(result.inserted_id)
        campaign_name = payload.new_campaign_name.strip()

    # Create import batch record
    batch_doc = {
        "file_name": filename,
        "source_type": "upload",
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "column_mapping": payload.mapping,
        "imported_by": user["_id"],
        "imported_by_email": user["email"],
        "created_at": utc_now_iso(),
        "stats": {},
    }
    batch_result = await db.import_batches.insert_one(batch_doc)
    batch_id = str(batch_result.inserted_id)

    stats = {
        "total_rows": len(rows),
        "new_people": 0,
        "matched_people": 0,
        "matched_by_email": 0,
        "matched_by_linkedin": 0,
        "matched_by_phone": 0,
        "possible_duplicates": 0,
        "skipped": 0,
    }
    for row in rows:
        mapped = {std: row.get(hdr, "") for std, hdr in payload.mapping.items() if hdr}
        result = await process_import_row(
            db,
            mapped,
            campaign_id=campaign_id,
            campaign_name=campaign_name,
            batch_id=batch_id,
            source_name=filename,
        )
        status = result["status"]
        if status == "new":
            stats["new_people"] += 1
        elif status == "matched":
            stats["matched_people"] += 1
            reason = result.get("match_reason") or "email"
            stats[f"matched_by_{reason}"] = stats.get(f"matched_by_{reason}", 0) + 1
        elif status == "soft_duplicate":
            stats["new_people"] += 1
            stats["possible_duplicates"] += 1
        else:
            stats["skipped"] += 1

    await db.import_batches.update_one({"_id": batch_result.inserted_id}, {"$set": {"stats": stats}})
    _STAGED.pop(payload.token, None)
    return {"batch_id": batch_id, "campaign_id": campaign_id, "campaign_name": campaign_name, "stats": stats}


@api.get("/import/batches")
async def list_batches(_: dict = Depends(get_current_user)):
    cursor = db.import_batches.find({}).sort("created_at", -1).limit(50)
    return {"items": [serialize_doc(d) async for d in cursor]}


# ---------------------------------------------------------------------------
# Export — CSV/XLSX matching current filter
# ---------------------------------------------------------------------------
@api.post("/people/export")
async def export_people(payload: PeopleQuery, format: str = "csv", ids: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Export the current filter as CSV/XLSX. If `ids` (comma-separated) is
    provided, ONLY those people are exported (used for the 'Export selected' flow)."""
    if ids:
        id_list = [i.strip() for i in ids.split(",") if i.strip()]
        oids = [ObjectId(i) for i in id_list if ObjectId.is_valid(i)]
        cursor = db.people.find({"_id": {"$in": oids}})
    else:
        filters = payload.model_dump()
        q = await _build_people_query(filters)
        # 200k is a generous ceiling; the UI paginates so full-list exports over this
        # threshold are extremely rare. We can raise this if it ever becomes a limit.
        cursor = db.people.find(q).limit(200000)
    docs = [d async for d in cursor]
    people = await _hydrate_people(docs)

    rows = []
    for p in people:
        rows.append({
            "Name": p.get("full_name"),
            "Email": p.get("primary_email"),
            "Additional Emails": ", ".join(p.get("additional_emails") or []),
            "Phone": ", ".join(p.get("phones") or []),
            "LinkedIn": p.get("linkedin_url"),
            "Company": p.get("company_name"),
            "Title": p.get("job_title"),
            "Campaigns": ", ".join(c["name"] for c in p.get("campaigns", [])),
            "Notes": p.get("notes"),
            "Tags": ", ".join(p.get("tags") or []),
            "Last Updated": p.get("updated_at"),
        })
    df = pd.DataFrame(rows)
    fmt = (format or "csv").lower()
    if fmt == "xlsx":
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="People")
        buf.seek(0)
        return StreamingResponse(
            buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=people_export.xlsx"},
        )
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(csv_bytes), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=people_export.csv"},
    )


# ---------------------------------------------------------------------------
# Duplicate review queue
# ---------------------------------------------------------------------------
@api.get("/duplicates")
async def list_duplicates(_: dict = Depends(get_current_user)):
    cursor = db.duplicate_flags.find({"status": "pending"}).sort("created_at", -1).limit(200)
    items = []
    async for d in cursor:
        s = serialize_doc(d)
        try:
            existing = await db.people.find_one({"_id": ObjectId(d["existing_person_id"])})
            s["existing_person"] = serialize_doc(existing) if existing else None
        except Exception:
            s["existing_person"] = None
        cand_id = d.get("candidate_person_id")
        if cand_id:
            try:
                cand = await db.people.find_one({"_id": ObjectId(cand_id)})
                s["candidate_person"] = serialize_doc(cand) if cand else None
            except Exception:
                s["candidate_person"] = None
        items.append(s)
    return {"items": items}


class DuplicateAction(BaseModel):
    action: str  # merge | dismiss


@api.post("/duplicates/{flag_id}/action")
async def duplicate_action(flag_id: str, payload: DuplicateAction, user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(flag_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid flag id")
    flag = await db.duplicate_flags.find_one({"_id": oid})
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    if payload.action == "dismiss":
        await db.duplicate_flags.update_one({"_id": oid}, {"$set": {"status": "dismissed"}})
        return {"ok": True}
    if payload.action == "merge":
        # Merge candidate into existing
        cand_id = flag.get("candidate_person_id")
        if not cand_id:
            raise HTTPException(status_code=400, detail="No candidate to merge")
        await merge_people(
            MergeInput(keep_person_id=flag["existing_person_id"], merge_person_id=cand_id),
            user,
        )
        await db.duplicate_flags.update_one({"_id": oid}, {"$set": {"status": "merged"}})
        return {"ok": True}
    raise HTTPException(status_code=400, detail="Unknown action")


# ---------------------------------------------------------------------------
# Saved filters
# ---------------------------------------------------------------------------
class SavedFilterInput(BaseModel):
    name: str
    filters: dict


@api.get("/saved-filters")
async def list_saved_filters(user: dict = Depends(get_current_user)):
    cursor = db.saved_filters.find({"owner_id": user["_id"]}).sort("created_at", -1)
    return {"items": [serialize_doc(d) async for d in cursor]}


@api.post("/saved-filters")
async def create_saved_filter(payload: SavedFilterInput, user: dict = Depends(get_current_user)):
    doc = {
        "name": payload.name.strip(),
        "owner_id": user["_id"],
        "filters": payload.filters,
        "created_at": utc_now_iso(),
    }
    result = await db.saved_filters.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_doc(doc)


@api.delete("/saved-filters/{filter_id}")
async def delete_saved_filter(filter_id: str, user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(filter_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    await db.saved_filters.delete_one({"_id": oid, "owner_id": user["_id"]})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------
@api.get("/stats/overview")
async def stats_overview(_: dict = Depends(get_current_user)):
    total_people = await db.people.count_documents({})
    total_companies = await db.companies.count_documents({})
    total_campaigns = await db.campaigns.count_documents({})
    active_campaigns = await db.campaigns.count_documents({"status": "Active"})
    pending_duplicates = await db.duplicate_flags.count_documents({"status": "pending"})
    recent_batches = []
    async for d in db.import_batches.find({}).sort("created_at", -1).limit(5):
        recent_batches.append(serialize_doc(d))
    return {
        "total_people": total_people,
        "total_companies": total_companies,
        "total_campaigns": total_campaigns,
        "active_campaigns": active_campaigns,
        "pending_duplicates": pending_duplicates,
        "recent_batches": recent_batches,
    }


# ---------------------------------------------------------------------------
# Chat assistant — Claude Sonnet 4.5 -> filter payload
# ---------------------------------------------------------------------------
class ChatInput(BaseModel):
    message: str
    history: Optional[List[dict]] = None  # optional [{role, content}]


SYSTEM_PROMPT = """You are the LeadUnify assistant. Your job is to translate a
user's natural-language request about their sales contact database into a strict JSON filter payload
that the app can execute against MongoDB. You also produce a short human-readable summary of what
you understood.

You have access to these entities:
- People (with fields: full_name, primary_email, company_name, job_title, tags, created_at, updated_at)
- Companies (fields: name, email_domain)
- Campaigns (fields: name, status = Active|Paused|Completed)

Given a user query, decide whether it needs to run a people search, a company search, a campaign
navigation, or simply an answer. Return a JSON object with EXACTLY these keys:

{
  "intent": "people_search" | "company_search" | "campaigns" | "duplicates" | "import" | "dashboard" | "answer",
  "filters": {
      "search": string | null,
      "company_id": string | null,
      "company_name": string | null,
      "tag": string | null,
      "in_campaign_names": string[] | null,      // campaigns the person MUST be in
      "not_in_campaign_names": string[] | null,  // campaigns the person MUST NOT be in
      "days_back": integer | null,               // "in last N days"
      "source": string | null
  },
  "navigate": string | null,   // one of: "/people", "/companies", "/campaigns", "/duplicates", "/import", "/dashboard", or null
  "answer": string             // short (1-2 sentence) summary the user will see
}

Rules:
- If unsure, prefer intent "people_search".
- Only fill filter fields that the user explicitly indicated; leave others null.
- Use campaign NAMES (not ids). The backend will resolve them.
- Return valid JSON only — no markdown fences, no extra prose. Your entire reply is the JSON object.
"""


async def _resolve_campaign_names(names: List[str]) -> List[str]:
    if not names:
        return []
    ids = []
    for name in names:
        c = await db.campaigns.find_one({"name": {"$regex": f"^{re.escape(name.strip())}$", "$options": "i"}})
        if c:
            ids.append(str(c["_id"]))
    return ids


@api.post("/chat/query")
async def chat_query(payload: ChatInput, user: dict = Depends(get_current_user)):
    """Interpret a natural-language query and return a filter + results preview."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Chat assistant is not configured")

    # Include a short context about existing campaigns to help the model
    campaign_names = []
    async for c in db.campaigns.find({}, {"name": 1, "status": 1}).limit(200):
        campaign_names.append(f"- {c['name']} ({c.get('status','Active')})")
    context_block = "Known campaigns:\n" + "\n".join(campaign_names) if campaign_names else ""

    session_id = f"leadunify-{user['_id']}"
    chat = LlmChat(
        api_key=api_key,
        session_id=session_id,
        system_message=SYSTEM_PROMPT + "\n\n" + context_block,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")

    try:
        response_text = await chat.send_message(UserMessage(text=payload.message))
    except Exception as e:
        logger.exception("LLM error")
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    parsed = None
    # try to extract JSON
    text = response_text.strip()
    # strip fences if any
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except Exception:
        # heuristic fallback
        parsed = {
            "intent": "answer",
            "filters": {},
            "navigate": None,
            "answer": response_text,
        }

    intent = parsed.get("intent", "people_search")
    filters_llm = parsed.get("filters") or {}

    # Build our filter payload
    resolved_filters: dict = {
        "search": filters_llm.get("search"),
        "company_name": filters_llm.get("company_name"),
        "tag": filters_llm.get("tag"),
        "source": filters_llm.get("source"),
    }
    if filters_llm.get("in_campaign_names"):
        resolved_filters["in_campaigns"] = await _resolve_campaign_names(filters_llm["in_campaign_names"])
    if filters_llm.get("not_in_campaign_names"):
        resolved_filters["not_in_campaigns"] = await _resolve_campaign_names(filters_llm["not_in_campaign_names"])
    if filters_llm.get("days_back"):
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(filters_llm["days_back"]))
        resolved_filters["created_after"] = cutoff.isoformat()

    # Fetch results preview for people_search intents
    people_preview = None
    total = 0
    if intent == "people_search":
        q = await _build_people_query({**resolved_filters, "search": resolved_filters.get("search") or None})
        total = await db.people.count_documents(q)
        cursor = db.people.find(q).sort("updated_at", -1).limit(15)
        docs = [d async for d in cursor]
        people_preview = await _hydrate_people(docs)

    return {
        "intent": intent,
        "answer": parsed.get("answer") or "Here's what I found.",
        "navigate": parsed.get("navigate"),
        "filters": resolved_filters,
        "results": {"items": people_preview, "total": total} if people_preview is not None else None,
    }


# ---------------------------------------------------------------------------
# Google Sheets OAuth
# ---------------------------------------------------------------------------
@api.get("/sheets/status")
async def sheets_status(user: dict = Depends(get_current_user)):
    configured = bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))
    token = await db.google_tokens.find_one({"user_id": user["_id"]})
    return {"configured": configured, "connected": token is not None}


@api.get("/oauth/sheets/login")
async def sheets_login(user: dict = Depends(get_current_user)):
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Google Sheets not configured — admin needs to add GOOGLE_CLIENT_SECRET")
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        raise HTTPException(status_code=503, detail="Google libraries not installed")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
    ]
    redirect_uri = os.environ["GOOGLE_REDIRECT_URI"]
    flow = Flow.from_client_config({
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }, scopes=scopes, redirect_uri=redirect_uri)
    url, state = flow.authorization_url(access_type="offline", prompt="consent")
    await db.oauth_states.insert_one({
        "state": state, "user_id": user["_id"], "created_at": datetime.now(timezone.utc),
    })
    return {"authorization_url": url}


@api.get("/oauth/sheets/callback")
async def sheets_callback(code: str, state: str):
    state_doc = await db.oauth_states.find_one({"state": state})
    if not state_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    user_id = state_doc["user_id"]
    await db.oauth_states.delete_one({"state": state})

    from google_auth_oauthlib.flow import Flow
    client_id = os.environ["GOOGLE_CLIENT_ID"]
    client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
    redirect_uri = os.environ["GOOGLE_REDIRECT_URI"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
    ]
    flow = Flow.from_client_config({
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }, scopes=scopes, redirect_uri=redirect_uri)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        flow.fetch_token(code=code)
    creds = flow.credentials
    expires_at = creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry else datetime.now(timezone.utc) + timedelta(hours=1)
    await db.google_tokens.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "expires_at": expires_at.isoformat(),
            "client_id": client_id,
            "client_secret": client_secret,
            "token_uri": "https://oauth2.googleapis.com/token",
        }},
        upsert=True,
    )
    # Redirect back to the app
    return RedirectResponse(url="/import?google=connected")


async def _get_google_creds(user_id: str):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GoogleRequest
    token = await db.google_tokens.find_one({"user_id": user_id})
    if not token:
        raise HTTPException(status_code=400, detail="Google not connected")
    expires = token.get("expires_at")
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    creds = Credentials(
        token=token["access_token"],
        refresh_token=token.get("refresh_token"),
        token_uri=token["token_uri"],
        client_id=token["client_id"],
        client_secret=token["client_secret"],
    )
    if datetime.now(timezone.utc) >= expires and creds.refresh_token:
        await asyncio.to_thread(creds.refresh, GoogleRequest())
        new_expires = creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry else datetime.now(timezone.utc) + timedelta(hours=1)
        await db.google_tokens.update_one(
            {"user_id": user_id},
            {"$set": {"access_token": creds.token, "expires_at": new_expires.isoformat()}},
        )
    return creds


@api.get("/sheets/list")
async def sheets_list(user: dict = Depends(get_current_user)):
    creds = await _get_google_creds(user["_id"])
    from googleapiclient.discovery import build
    service = await asyncio.to_thread(build, "drive", "v3", credentials=creds)
    result = await asyncio.to_thread(
        lambda: service.files().list(
            q="mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
            pageSize=50,
            fields="files(id, name, modifiedTime)",
        ).execute()
    )
    return {"items": result.get("files", [])}


class SheetsImportPreview(BaseModel):
    spreadsheet_id: str
    tab: Optional[str] = None


@api.post("/sheets/preview")
async def sheets_preview(payload: SheetsImportPreview, user: dict = Depends(get_current_user)):
    creds = await _get_google_creds(user["_id"])
    from googleapiclient.discovery import build
    sheets = await asyncio.to_thread(build, "sheets", "v4", credentials=creds)
    meta = await asyncio.to_thread(
        lambda: sheets.spreadsheets().get(spreadsheetId=payload.spreadsheet_id).execute()
    )
    tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    tab = payload.tab or tabs[0] if tabs else None
    if not tab:
        raise HTTPException(status_code=400, detail="No tabs found in this spreadsheet")
    rng = f"'{tab}'!A1:Z10000"
    result = await asyncio.to_thread(
        lambda: sheets.spreadsheets().values().get(spreadsheetId=payload.spreadsheet_id, range=rng).execute()
    )
    values = result.get("values", [])
    if not values:
        raise HTTPException(status_code=400, detail="Sheet is empty")
    headers = values[0]
    rows = []
    for row in values[1:]:
        row = row + [""] * (len(headers) - len(row))
        rows.append({headers[i]: row[i] for i in range(len(headers))})

    suggested = _suggest_mapping(headers)
    token = secrets.token_urlsafe(16)
    _STAGED[token] = (headers, rows, f"{meta.get('properties', {}).get('title', 'Google Sheet')} — {tab}")
    return {
        "token": token,
        "file_name": _STAGED[token][2],
        "tabs": tabs,
        "tab": tab,
        "headers": headers,
        "suggested_mapping": suggested,
        "preview_rows": rows[:10],
        "total_rows": len(rows),
    }


# ---------------------------------------------------------------------------
# Team / users management (admin only)
# ---------------------------------------------------------------------------
def _admin_only(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


class InviteUserInput(BaseModel):
    email: str
    name: Optional[str] = None
    role: str = "member"  # "admin" | "member"
    password: Optional[str] = None  # optional; auto-generated if omitted


class UserPatchInput(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None  # admin reset


@api.get("/users")
async def list_users(user: dict = Depends(get_current_user)):
    _admin_only(user)
    cursor = db.users.find({}, {"password_hash": 0}).sort("created_at", -1)
    items = []
    async for d in cursor:
        items.append({
            "id": str(d["_id"]),
            "email": d["email"],
            "name": d.get("name", "User"),
            "role": d.get("role", "member"),
            "created_at": d.get("created_at"),
        })
    return {"items": items}


@api.post("/users/invite")
async def invite_user(payload: InviteUserInput, user: dict = Depends(get_current_user)):
    """Create a new team member. Returns the temporary password so the admin
    can share it with the invitee. (This is an internal tool — no email is sent.)"""
    _admin_only(user)
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="A user with this email already exists")
    if payload.role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail="Role must be admin or member")

    temp_password = payload.password or secrets.token_urlsafe(9)
    doc = {
        "email": email,
        "password_hash": hash_password(temp_password),
        "name": payload.name or email.split("@")[0].capitalize(),
        "role": payload.role,
        "created_at": utc_now_iso(),
    }
    result = await db.users.insert_one(doc)
    return {
        "user": {
            "id": str(result.inserted_id),
            "email": email,
            "name": doc["name"],
            "role": doc["role"],
            "created_at": doc["created_at"],
        },
        "temporary_password": temp_password,
    }


@api.patch("/users/{user_id}")
async def update_user(user_id: str, payload: UserPatchInput, user: dict = Depends(get_current_user)):
    _admin_only(user)
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user id")
    updates: dict = {}
    if payload.name is not None:
        updates["name"] = payload.name.strip()
    if payload.role is not None:
        if payload.role not in ("admin", "member"):
            raise HTTPException(status_code=400, detail="Role must be admin or member")
        updates["role"] = payload.role
    if payload.password:
        updates["password_hash"] = hash_password(payload.password)
    if not updates:
        return {"ok": True}
    await db.users.update_one({"_id": oid}, {"$set": updates})
    return {"ok": True}


@api.delete("/users/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(get_current_user)):
    _admin_only(user)
    if user_id == str(user["_id"]):
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user id")
    await db.users.delete_one({"_id": oid})
    # Remove the user's shares
    await db.campaigns.update_many({}, {"$pull": {"shared_with_user_ids": user_id}})
    # Reassign owned campaigns to admin (current caller) — safer than deleting
    await db.campaigns.update_many({"owner_id": user_id}, {"$set": {"owner_id": str(user["_id"])}})
    await db.access_requests.delete_many({"user_id": user_id})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Campaign sharing + access requests
# ---------------------------------------------------------------------------
class ShareCampaignInput(BaseModel):
    user_ids: List[str]


@api.post("/campaigns/{campaign_id}/share")
async def share_campaign(
    campaign_id: str, payload: ShareCampaignInput, user: dict = Depends(get_current_user)
):
    try:
        oid = ObjectId(campaign_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign id")
    camp = await db.campaigns.find_one({"_id": oid})
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
    uid = str(user["_id"])
    is_admin = user.get("role") == "admin"
    if not is_admin and camp.get("owner_id") != uid:
        raise HTTPException(status_code=403, detail="Only the owner or an admin can share this campaign")

    # dedupe + validate the user ids exist
    valid_ids = []
    for user_id in payload.user_ids:
        if not ObjectId.is_valid(user_id):
            continue
        u = await db.users.find_one({"_id": ObjectId(user_id)}, {"_id": 1})
        if u:
            valid_ids.append(str(u["_id"]))
    await db.campaigns.update_one(
        {"_id": oid},
        {"$addToSet": {"shared_with_user_ids": {"$each": valid_ids}}},
    )
    doc = await db.campaigns.find_one({"_id": oid})
    return serialize_doc(doc)


class UnshareCampaignInput(BaseModel):
    user_id: str


class BulkShareCampaignsInput(BaseModel):
    campaign_ids: List[str]
    user_ids: List[str]


@api.post("/campaigns/bulk-share")
async def bulk_share_campaigns(
    payload: BulkShareCampaignsInput, user: dict = Depends(get_current_user)
):
    """Share MANY campaigns with the same set of users at once.

    Only campaigns the caller owns (or all, if admin) will be touched. Skipped
    campaigns are reported back so the UI can surface which ones the user
    doesn't have permission to share."""
    is_admin = user.get("role") == "admin"
    uid = str(user["_id"])

    # dedupe + validate user ids exist
    valid_user_ids: List[str] = []
    for user_id in payload.user_ids:
        if not ObjectId.is_valid(user_id):
            continue
        u = await db.users.find_one({"_id": ObjectId(user_id)}, {"_id": 1})
        if u:
            valid_user_ids.append(str(u["_id"]))

    shared: List[str] = []
    skipped: List[dict] = []
    for cid in payload.campaign_ids:
        if not ObjectId.is_valid(cid):
            skipped.append({"campaign_id": cid, "reason": "invalid id"})
            continue
        oid = ObjectId(cid)
        camp = await db.campaigns.find_one({"_id": oid})
        if not camp:
            skipped.append({"campaign_id": cid, "reason": "not found"})
            continue
        if not is_admin and camp.get("owner_id") != uid:
            skipped.append({"campaign_id": cid, "reason": "not owner", "name": camp.get("name")})
            continue
        await db.campaigns.update_one(
            {"_id": oid},
            {"$addToSet": {"shared_with_user_ids": {"$each": valid_user_ids}}},
        )
        shared.append(cid)
    return {"ok": True, "shared": shared, "skipped": skipped, "user_ids": valid_user_ids}


@api.post("/campaigns/{campaign_id}/unshare")
async def unshare_campaign(
    campaign_id: str, payload: UnshareCampaignInput, user: dict = Depends(get_current_user)
):
    try:
        oid = ObjectId(campaign_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign id")
    camp = await db.campaigns.find_one({"_id": oid})
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if user.get("role") != "admin" and camp.get("owner_id") != str(user["_id"]):
        raise HTTPException(status_code=403, detail="Only the owner or admin can un-share")
    await db.campaigns.update_one({"_id": oid}, {"$pull": {"shared_with_user_ids": payload.user_id}})
    return {"ok": True}


@api.post("/campaigns/{campaign_id}/request-access")
async def request_campaign_access(campaign_id: str, user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(campaign_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign id")
    camp = await db.campaigns.find_one({"_id": oid})
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
    uid = str(user["_id"])
    # Already has access
    if user.get("role") == "admin" or camp.get("owner_id") == uid or uid in (camp.get("shared_with_user_ids") or []):
        return {"ok": True, "already_has_access": True}
    # Already requested and pending
    existing = await db.access_requests.find_one({
        "campaign_id": campaign_id, "user_id": uid, "status": "pending",
    })
    if existing:
        return {"ok": True, "already_requested": True}
    await db.access_requests.insert_one({
        "campaign_id": campaign_id,
        "campaign_name": camp["name"],
        "user_id": uid,
        "user_email": user["email"],
        "user_name": user.get("name", "User"),
        "status": "pending",
        "created_at": utc_now_iso(),
    })
    return {"ok": True, "requested": True}


@api.get("/access-requests")
async def list_access_requests(user: dict = Depends(get_current_user)):
    """Admins see all pending requests. Non-admin owners see requests for
    campaigns they own."""
    is_admin = user.get("role") == "admin"
    uid = str(user["_id"])
    if is_admin:
        query = {"status": "pending"}
    else:
        owned = [str(c["_id"]) async for c in db.campaigns.find({"owner_id": uid}, {"_id": 1})]
        if not owned:
            return {"items": []}
        query = {"status": "pending", "campaign_id": {"$in": owned}}
    items = []
    async for d in db.access_requests.find(query).sort("created_at", -1).limit(200):
        items.append(serialize_doc(d))
    return {"items": items}


class AccessRequestAction(BaseModel):
    action: str  # "approve" | "deny"


@api.post("/access-requests/{req_id}/action")
async def action_access_request(
    req_id: str, payload: AccessRequestAction, user: dict = Depends(get_current_user)
):
    try:
        oid = ObjectId(req_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request id")
    req = await db.access_requests.find_one({"_id": oid})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    is_admin = user.get("role") == "admin"
    campaign_id = req["campaign_id"]
    camp = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign no longer exists")
    if not is_admin and camp.get("owner_id") != str(user["_id"]):
        raise HTTPException(status_code=403, detail="Not authorized to act on this request")

    if payload.action == "approve":
        await db.campaigns.update_one(
            {"_id": ObjectId(campaign_id)},
            {"$addToSet": {"shared_with_user_ids": req["user_id"]}},
        )
        await db.access_requests.update_one({"_id": oid}, {"$set": {"status": "approved"}})
    elif payload.action == "deny":
        await db.access_requests.update_one({"_id": oid}, {"$set": {"status": "denied"}})
    else:
        raise HTTPException(status_code=400, detail="Unknown action")
    return {"ok": True}


@api.get("/my-access-requests")
async def my_access_requests(user: dict = Depends(get_current_user)):
    """Requests the current user has made — so they can see their pending status."""
    cursor = db.access_requests.find({"user_id": str(user["_id"])}).sort("created_at", -1).limit(50)
    return {"items": [serialize_doc(d) async for d in cursor]}


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
@api.get("/audit-log")
async def get_audit_log(
    limit: int = 100,
    action: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _admin_only(user)
    limit = max(1, min(limit, 500))
    query: dict = {}
    if action:
        query["action"] = action
    cursor = db.audit_log.find(query).sort("created_at", -1).limit(limit)
    return {"items": [serialize_doc(d) async for d in cursor]}


# ---------------------------------------------------------------------------
# Root ping
# ---------------------------------------------------------------------------
@api.get("/")
async def root():
    return {"service": "LeadUnify", "status": "ok"}


# ---------------------------------------------------------------------------
# CORS + register
# ---------------------------------------------------------------------------
_cors_env = os.environ.get("CORS_ORIGINS", "*")
if _cors_env.strip() == "*":
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in _cors_env.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


app.include_router(api)
