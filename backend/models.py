"""Pydantic models for Vaultedge Outreach Hub."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, List, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _coerce_object_id(v: Any) -> str:
    if v is None:
        return v
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, str):
        return v
    raise ValueError(f"Not a valid ObjectId: {v!r}")


PyObjectId = Annotated[str, BeforeValidator(_coerce_object_id)]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BaseDocument(BaseModel):
    """Base model that maps Mongo _id -> id and back."""

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: Optional[dict]):
        if doc is None:
            return None
        if "_id" in doc:
            doc = {**doc, "_id": str(doc["_id"])}
        return cls(**doc)

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True, exclude_none=True)
        if "_id" in data and isinstance(data["_id"], str):
            try:
                data["_id"] = ObjectId(data["_id"])
            except Exception:
                data.pop("_id")
        return data


# --------------------------------------------------------------------------
# User / Auth
# --------------------------------------------------------------------------
class User(BaseDocument):
    email: str
    password_hash: str
    name: str = "User"
    role: str = "member"  # "admin" | "member"
    created_at: str = Field(default_factory=utc_now_iso)


class UserPublic(BaseModel):
    id: str
    email: str
    name: str
    role: str


class RegisterInput(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


class LoginInput(BaseModel):
    email: str
    password: str


# --------------------------------------------------------------------------
# Company
# --------------------------------------------------------------------------
class Company(BaseDocument):
    name: str
    email_domain: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)


# --------------------------------------------------------------------------
# Person
# --------------------------------------------------------------------------
class SourceEntry(BaseModel):
    """Which import batch produced which field values."""

    batch_id: Optional[str] = None
    source_name: str  # file/sheet name
    imported_at: str = Field(default_factory=utc_now_iso)


class FieldConflict(BaseModel):
    """When two sources disagree, we keep both."""

    field: str
    values: List[dict] = Field(default_factory=list)  # [{value, source}]


class Person(BaseDocument):
    full_name: str
    primary_email: str  # normalized lowercase
    additional_emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    linkedin_url: Optional[str] = None
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    sources: List[SourceEntry] = Field(default_factory=list)
    conflicts: List[FieldConflict] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


# --------------------------------------------------------------------------
# Campaign
# --------------------------------------------------------------------------
class Campaign(BaseDocument):
    name: str
    category: Optional[str] = None  # Introductory / Event / Nurture / Product / Other
    status: str = "Active"  # Active / Paused / Completed
    description: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)


# --------------------------------------------------------------------------
# Person <-> Campaign link (many-to-many)
# --------------------------------------------------------------------------
class PersonCampaignLink(BaseDocument):
    person_id: str
    campaign_id: str
    status: str = "Not Contacted"  # Not Contacted / Contacted / Replied / Meeting Booked / Opted Out
    added_at: str = Field(default_factory=utc_now_iso)


# --------------------------------------------------------------------------
# Import batch
# --------------------------------------------------------------------------
class ImportBatch(BaseDocument):
    file_name: str
    source_type: str = "upload"  # upload | google_sheets
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    column_mapping: dict = Field(default_factory=dict)
    imported_by: Optional[str] = None
    imported_by_email: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)
    stats: dict = Field(default_factory=dict)
    # stats: { total_rows, new_people, matched_people, matched_by_email, matched_by_linkedin,
    #          matched_by_phone, possible_duplicates, skipped }


# --------------------------------------------------------------------------
# Duplicate flag (soft duplicate awaiting review)
# --------------------------------------------------------------------------
class DuplicateFlag(BaseDocument):
    existing_person_id: str
    candidate_data: dict  # raw row data that "looks like" a duplicate
    match_reason: str  # e.g. "name+company similar"
    source_batch_id: Optional[str] = None
    source_name: Optional[str] = None
    status: str = "pending"  # pending / merged / dismissed
    created_at: str = Field(default_factory=utc_now_iso)


# --------------------------------------------------------------------------
# Saved filter list
# --------------------------------------------------------------------------
class SavedFilter(BaseDocument):
    name: str
    owner_id: str
    filters: dict
    created_at: str = Field(default_factory=utc_now_iso)
