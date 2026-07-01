"""Seed demo people, companies, and campaigns."""
from __future__ import annotations

import random
from datetime import datetime, timezone

from dedup import get_or_create_company, link_person_campaign
from models import utc_now_iso


DEMO_CAMPAIGNS = [
    {"name": "MBA Annual 2026", "category": "Event", "status": "Active"},
    {"name": "Non-QM Introductory Campaign", "category": "Introductory", "status": "Active"},
    {"name": "FinTech Summit Invite", "category": "Event", "status": "Active"},
    {"name": "Q1 Product Announcement", "category": "Product-specific", "status": "Active"},
    {"name": "Enterprise Nurture — Wave 3", "category": "Nurture", "status": "Active"},
    {"name": "Broker Outreach — West Coast", "category": "Introductory", "status": "Paused"},
    {"name": "Mortgage Bankers Meetup NYC", "category": "Event", "status": "Completed"},
]


DEMO_PEOPLE = [
    # (name, email, phone, linkedin, company, title, campaign_indices)
    ("Bhargav Reddy", "bhargav@company.com", "+1-415-555-0142", "linkedin.com/in/bhargavr", "Company Inc", "VP of Lending", [0, 1]),
    ("Ananya Sharma", "ananya.sharma@hdfcbank.com", "+91-98765-43210", "linkedin.com/in/ananyas", "HDFC Bank", "Head of Digital Lending", [1, 4]),
    ("Marcus Chen", "mchen@rocketfin.com", "+1-312-555-0187", "linkedin.com/in/marcuschen", "Rocket Financial", "Director of Product", [0, 2, 3]),
    ("Priya Iyer", "priya.iyer@hdfcbank.com", "+91-99887-76655", "linkedin.com/in/priyaiyer", "HDFC Bank", "Senior Analyst", [1]),
    ("James O'Connor", "j.oconnor@wellsloan.com", "+1-202-555-0165", "linkedin.com/in/joconnor", "WellsLoan Corp", "Chief Underwriter", [0, 6]),
    ("Sofia Ramirez", "sofia.r@brightmortgage.co", "+1-305-555-0139", "linkedin.com/in/sofiaramirez", "BrightMortgage", "Sales Director", [1, 4]),
    ("Rajesh Kumar", "rajesh.k@hdfcbank.com", "+91-98111-22233", "linkedin.com/in/rajeshk", "HDFC Bank", "VP Technology", [3, 4]),
    ("Emily Novak", "emily.novak@lendhub.io", "+1-646-555-0121", "linkedin.com/in/emilynovak", "LendHub", "Growth Marketing Lead", [2, 3]),
    ("David Park", "d.park@capitalcrest.com", "+1-415-555-0198", "linkedin.com/in/davidpark", "CapitalCrest", "SVP Operations", [0, 4, 6]),
    ("Meera Patel", "meera@fintechforward.io", "+1-628-555-0117", "linkedin.com/in/meerapatel", "FinTech Forward", "CEO", [2]),
    ("Thomas Berg", "tberg@nordicloan.se", "+46-8-555-0104", "linkedin.com/in/thomasberg", "NordicLoan", "Head of Partnerships", [0, 2]),
    ("Zara Ahmed", "zara.ahmed@quickapprove.com", "+1-773-555-0156", "linkedin.com/in/zaraahmed", "QuickApprove", "Product Manager", [3, 4]),
    ("Ken Nakamura", "ken@originatepro.com", "+1-408-555-0173", "linkedin.com/in/kennakamura", "OriginatePro", "CTO", [1, 3]),
    ("Isabella Rossi", "isabella@romefin.it", "+39-06-555-0129", "linkedin.com/in/isabellarossi", "RomeFin", "Marketing Director", [2]),
    ("Wei Zhang", "wzhang@paceloan.com", "+1-510-555-0184", "linkedin.com/in/weizhang", "PaceLoan", "Head of Data Science", [0, 3, 4]),
    ("Olivia Kim", "olivia.kim@northstarfin.com", "+1-206-555-0145", "linkedin.com/in/oliviakim", "NorthStar Financial", "VP of Sales", [1, 6]),
    ("Aditya Verma", "aditya.v@hdfcbank.com", "+91-97777-55544", "linkedin.com/in/adityaverma", "HDFC Bank", "Regional Head", [4]),
    ("Grace Thompson", "grace@brokerhub.us", "+1-503-555-0192", "linkedin.com/in/gracethompson", "BrokerHub", "Head of Compliance", [5]),
    ("Miguel Santos", "miguel.s@iberianloan.es", "+34-91-555-0108", "linkedin.com/in/miguelsantos", "IberianLoan", "Business Development", [0, 2]),
    ("Hannah Weiss", "hannah.w@berlinlend.de", "+49-30-555-0163", "linkedin.com/in/hannahweiss", "BerlinLend", "Product Owner", [1, 3]),
]


async def seed_demo_data(db) -> dict:
    """Seed if there are no people yet."""
    existing = await db.people.count_documents({})
    if existing > 0:
        return {"skipped": True, "reason": "data already present"}

    # Seed campaigns
    campaign_ids = []
    for c in DEMO_CAMPAIGNS:
        doc = {
            **c,
            "description": None,
            "created_at": utc_now_iso(),
        }
        result = await db.campaigns.insert_one(doc)
        campaign_ids.append(str(result.inserted_id))

    # Seed a demo import batch
    batch_doc = {
        "file_name": "demo_seed.xlsx",
        "source_type": "seed",
        "campaign_id": None,
        "campaign_name": "Demo Seed",
        "column_mapping": {},
        "imported_by": None,
        "imported_by_email": "admin@vaultedge.com",
        "created_at": utc_now_iso(),
        "stats": {"total_rows": len(DEMO_PEOPLE), "new_people": len(DEMO_PEOPLE)},
    }
    batch_result = await db.import_batches.insert_one(batch_doc)
    batch_id = str(batch_result.inserted_id)

    people_created = 0
    links_created = 0
    for name, email, phone, linkedin, company, title, campaign_idxs in DEMO_PEOPLE:
        company_id, company_name = await get_or_create_company(db, company, email)
        person_doc = {
            "full_name": name,
            "primary_email": email.lower(),
            "additional_emails": [],
            "phones": [phone] if phone else [],
            "linkedin_url": f"https://{linkedin}" if linkedin and not linkedin.startswith("http") else linkedin,
            "company_id": company_id,
            "company_name": company_name,
            "job_title": title,
            "tags": [],
            "notes": None,
            "sources": [{
                "batch_id": batch_id,
                "source_name": "demo_seed.xlsx",
                "imported_at": utc_now_iso(),
            }],
            "conflicts": [],
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
        result = await db.people.insert_one(person_doc)
        pid = str(result.inserted_id)
        people_created += 1
        for ci in campaign_idxs:
            if await link_person_campaign(db, pid, campaign_ids[ci]):
                links_created += 1

    return {
        "campaigns": len(campaign_ids),
        "people": people_created,
        "links": links_created,
    }
