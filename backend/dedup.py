"""De-duplication + import row processing."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Optional

from bson import ObjectId

from models import Person, SourceEntry, utc_now_iso


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s or s in {"nan", "none", "null"}:
        return None
    if not EMAIL_RE.match(s):
        return None
    return s


def normalize_phone(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = re.sub(r"[^\d+]", "", str(value))
    if not s or s in {"nan"}:
        return None
    # keep last 10 digits comparison key + full string
    return s


def normalize_linkedin(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s or s in {"nan", "none"}:
        return None
    # strip trailing slashes / query
    s = s.split("?")[0].rstrip("/")
    if "linkedin.com" not in s and not s.startswith("http"):
        # sometimes just a handle
        s = f"https://linkedin.com/in/{s}"
    return s


def clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    return s


def domain_from_email(email: str) -> Optional[str]:
    if not email or "@" not in email:
        return None
    return email.split("@", 1)[1].lower()


def similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


async def find_person_by_email(db, email: str) -> Optional[dict]:
    if not email:
        return None
    return await db.people.find_one({
        "$or": [{"primary_email": email}, {"additional_emails": email}]
    })


async def find_person_by_linkedin(db, url: str) -> Optional[dict]:
    if not url:
        return None
    return await db.people.find_one({"linkedin_url": url})


async def find_person_by_phone(db, phone: str) -> Optional[dict]:
    if not phone:
        return None
    return await db.people.find_one({"phones": phone})


async def find_soft_duplicate(db, full_name: str, company_name: Optional[str]) -> Optional[dict]:
    """Look up by name+company similarity (no hard identifier)."""
    if not full_name:
        return None
    cursor = db.people.find({}, {
        "full_name": 1, "company_name": 1, "primary_email": 1,
    }).limit(500)
    async for doc in cursor:
        n_score = similar(full_name, doc.get("full_name") or "")
        if n_score < 0.85:
            continue
        if company_name and doc.get("company_name"):
            c_score = similar(company_name, doc["company_name"])
            if c_score >= 0.7:
                return doc
        elif not company_name:
            # name-only match with very high similarity
            if n_score >= 0.95:
                return doc
    return None


async def get_or_create_company(db, name: Optional[str], email: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Returns (company_id, company_name)."""
    if not name and not email:
        return None, None

    if name:
        existing = await db.companies.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
        if existing:
            return str(existing["_id"]), existing["name"]

    domain = domain_from_email(email) if email else None
    # Try match by domain
    if not name and domain:
        existing = await db.companies.find_one({"email_domain": domain})
        if existing:
            return str(existing["_id"]), existing["name"]
        name = domain.split(".")[0].capitalize()

    doc = {
        "name": name,
        "email_domain": domain,
        "created_at": utc_now_iso(),
    }
    result = await db.companies.insert_one(doc)
    return str(result.inserted_id), name


def _merge_fields(existing: dict, row: dict, source_name: str, batch_id: str) -> tuple[dict, list]:
    """Merge new row into existing person doc without overwriting.
    Returns (update_ops, conflicts)."""
    updates: dict[str, Any] = {}
    push_ops: dict[str, Any] = {}
    add_to_set_ops: dict[str, Any] = {}
    conflicts: list = []

    def set_if_blank(field: str, new_value):
        if new_value is None:
            return
        current = existing.get(field)
        if current in (None, "", []):
            updates[field] = new_value
        elif isinstance(current, str) and current.strip().lower() != str(new_value).strip().lower():
            conflicts.append({"field": field, "existing": current, "incoming": new_value, "source": source_name})

    set_if_blank("full_name", row.get("full_name"))
    set_if_blank("linkedin_url", row.get("linkedin_url"))
    set_if_blank("company_id", row.get("company_id"))
    set_if_blank("company_name", row.get("company_name"))
    set_if_blank("job_title", row.get("job_title"))

    # Add-to-set for arrays (dedupe)
    new_emails = []
    if row.get("primary_email") and row["primary_email"] != existing.get("primary_email"):
        if row["primary_email"] not in (existing.get("additional_emails") or []):
            new_emails.append(row["primary_email"])
    for e in row.get("additional_emails") or []:
        if e != existing.get("primary_email") and e not in (existing.get("additional_emails") or []):
            new_emails.append(e)
    if new_emails:
        add_to_set_ops["additional_emails"] = {"$each": list(set(new_emails))}

    new_phones = [p for p in (row.get("phones") or []) if p and p not in (existing.get("phones") or [])]
    if new_phones:
        add_to_set_ops["phones"] = {"$each": list(set(new_phones))}

    # Record the source
    push_ops["sources"] = {
        "batch_id": batch_id,
        "source_name": source_name,
        "imported_at": utc_now_iso(),
    }

    if conflicts:
        push_ops.setdefault("conflicts", {"$each": []})
        # Actually conflicts uses $push with $each
        push_ops["conflicts"] = {"$each": [
            {"field": c["field"], "values": [
                {"value": c["existing"], "source": "existing"},
                {"value": c["incoming"], "source": c["source"]},
            ]} for c in conflicts
        ]}

    updates["updated_at"] = utc_now_iso()

    op: dict[str, Any] = {}
    if updates:
        op["$set"] = updates
    if add_to_set_ops:
        op["$addToSet"] = add_to_set_ops
    if push_ops:
        op["$push"] = push_ops

    return op, conflicts


async def link_person_campaign(db, person_id: str, campaign_id: str) -> bool:
    """Ensure a link exists; returns True if newly created."""
    existing = await db.person_campaigns.find_one({
        "person_id": person_id,
        "campaign_id": campaign_id,
    })
    if existing:
        return False
    await db.person_campaigns.insert_one({
        "person_id": person_id,
        "campaign_id": campaign_id,
        "status": "Not Contacted",
        "added_at": utc_now_iso(),
    })
    return True


async def process_import_row(
    db,
    raw_row: dict,
    campaign_id: str,
    campaign_name: str,
    batch_id: str,
    source_name: str,
) -> dict:
    """Process one mapped row.
    raw_row keys: full_name, primary_email, phone, linkedin_url, company_name, job_title, additional_emails
    Returns: {status: 'new'|'matched'|'skipped'|'soft_duplicate', match_reason: str, person_id: str}
    """
    email = normalize_email(raw_row.get("primary_email"))
    phone = normalize_phone(raw_row.get("phone"))
    linkedin = normalize_linkedin(raw_row.get("linkedin_url"))

    # Combine first_name + last_name into full_name when full_name isn't present
    full_name = clean_str(raw_row.get("full_name"))
    if not full_name:
        first = clean_str(raw_row.get("first_name"))
        last = clean_str(raw_row.get("last_name"))
        combined = " ".join(x for x in [first, last] if x)
        if combined:
            full_name = combined

    company_name = clean_str(raw_row.get("company_name"))
    job_title = clean_str(raw_row.get("job_title"))
    notes = clean_str(raw_row.get("notes"))

    # Skip rows with no useful data
    if not any([email, phone, linkedin, full_name]):
        return {"status": "skipped", "match_reason": "no_data", "person_id": None}

    # Resolve company
    company_id, resolved_company = await get_or_create_company(db, company_name, email)

    row = {
        "primary_email": email,
        "phone": phone,
        "linkedin_url": linkedin,
        "full_name": full_name or (email.split("@")[0] if email else "Unknown"),
        "company_id": company_id,
        "company_name": resolved_company,
        "job_title": job_title,
        "phones": [phone] if phone else [],
        "additional_emails": [],
    }

    # 1. Match by email
    match_reason = None
    existing = None
    if email:
        existing = await find_person_by_email(db, email)
        if existing:
            match_reason = "email"

    # 2. Match by linkedin
    if not existing and linkedin:
        existing = await find_person_by_linkedin(db, linkedin)
        if existing:
            match_reason = "linkedin"

    # 3. Match by phone
    if not existing and phone:
        existing = await find_person_by_phone(db, phone)
        if existing:
            match_reason = "phone"

    if existing:
        op, _ = _merge_fields(existing, row, source_name, batch_id)
        if op:
            await db.people.update_one({"_id": existing["_id"]}, op)
        person_id = str(existing["_id"])
        await link_person_campaign(db, person_id, campaign_id)
        return {"status": "matched", "match_reason": match_reason, "person_id": person_id}

    # 4. Soft duplicate check (name+company)
    soft = await find_soft_duplicate(db, row["full_name"], resolved_company)
    if soft:
        # Insert the new person anyway but ALSO flag as possible duplicate for review
        pass  # handled below by inserting + flagging

    # 5. Create new person
    new_doc = {
        "full_name": row["full_name"],
        "primary_email": email,
        "additional_emails": [],
        "phones": [phone] if phone else [],
        "linkedin_url": linkedin,
        "company_id": company_id,
        "company_name": resolved_company,
        "job_title": job_title,
        "tags": [],
        "notes": notes,
        "sources": [{
            "batch_id": batch_id,
            "source_name": source_name,
            "imported_at": utc_now_iso(),
        }],
        "conflicts": [],
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }
    result = await db.people.insert_one(new_doc)
    person_id = str(result.inserted_id)
    await link_person_campaign(db, person_id, campaign_id)

    if soft:
        await db.duplicate_flags.insert_one({
            "existing_person_id": str(soft["_id"]),
            "candidate_person_id": person_id,
            "candidate_data": {
                "full_name": row["full_name"],
                "primary_email": email,
                "company_name": resolved_company,
                "linkedin_url": linkedin,
            },
            "match_reason": "name+company similar",
            "source_batch_id": batch_id,
            "source_name": source_name,
            "status": "pending",
            "created_at": utc_now_iso(),
        })
        return {"status": "soft_duplicate", "match_reason": "name+company", "person_id": person_id}

    return {"status": "new", "match_reason": None, "person_id": person_id}
