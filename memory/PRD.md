# LeadUnify — Contact & Campaign Intelligence Hub

## Original problem statement

Internal contact-and-campaign tool for a mortgage-automation company. Turn
scattered, duplicate-ridden spreadsheets (dozens of Google Sheets / Excel files,
each ≈ one outreach campaign) into ONE clean database where each person exists
exactly once, tagged with every campaign they belong to. Around 100 active
campaigns; scale target 10–50k contacts.

## User personas

- **Sales / marketing analyst (member role)** — imports sheets, filters people
  by campaign/company, exports subsets, collaborates on notes.
- **Admin** — invites teammates, manages roles, merges duplicate companies,
  approves campaign access requests.

## Architecture

- **Backend:** FastAPI + Motor (async MongoDB) + bcrypt + PyJWT + pandas +
  openpyxl + emergentintegrations (Claude Sonnet 4.5).
- **Frontend:** React 19 + shadcn/ui + Manrope (sans) + JetBrains Mono
  (numbers/emails) + Indigo accent + Tailwind.
- **DB:** MongoDB — collections: users, people, companies, campaigns,
  person_campaigns (many-to-many), import_batches, duplicate_flags,
  saved_filters, access_requests, google_tokens, oauth_states.
- **Auth:** JWT Bearer + httpOnly cookie (both work). Token cached in
  `localStorage['leadunify_access_token']` so multipart uploads never lose auth.

## Implemented (v1 — 2026-07-01)

- One person = one record: import dedup by email → LinkedIn → phone. Soft
  dedup by name+company similarity is bounded to first-token prefix scan.
- People Directory: dense table with select-all + per-row checkbox, campaign
  chips, inline editable notes column, LinkedIn icon, LI/email/phone in
  monospace.
- Person Detail side panel with campaigns list, add/remove campaigns, notes.
- Companies view with paginated list, per-company editable notes on the
  filtered People banner, and a Possible-duplicate companies section
  (fuzzy match via canonical_name) + merge dialog.
- Campaigns view with Owner/Shared badges, Share dialog, tabs "My campaigns"
  and "Explore" for members, admin access-requests inbox with Approve/Deny.
- Import: drag-drop Excel/CSV upload → global-optimal column mapping suggestion
  (First Name / Last Name / Email / Phone / LinkedIn / Company / Title / Notes),
  10-row preview, commit into new-or-existing campaign (name defaults to sheet
  filename). First+Last combined into full_name when full_name isn't mapped.
- Duplicate review queue with side-by-side view + Merge / Not-a-duplicate
  actions.
- Team page (admin-only): invite users (temp password shown once), change
  role, reset password, remove user.
- Bulk delete: two modes — "remove from this campaign only" (context-aware,
  only when filtered) or "delete from all lists & campaigns".
- Selective export: select rows → "Export N selected" produces CSV/XLSX with
  only those people; otherwise exports the current filter (up to 200k rows).
- Filter combos: search / company-contains / in-campaigns (OR union) /
  not-in-campaigns / saved filter lists. URL params (?in, ?company, ?search)
  drive the filter for deep-linkable views. Header shows filter context.
- Chat assistant (Claude Sonnet 4.5): natural-language → filter payload +
  inline result table. E.g. "everyone from HDFC Bank" returns 4 people.
- Google Sheets integration scaffold: /api/sheets/status returns configured
  false (GOOGLE_CLIENT_SECRET intentionally empty). Adding the secret enables
  the OAuth + list + preview flow already coded.
- Scalability: indexes on people (primary_email, additional_emails,
  linkedin_url, phones, company_id, company_name, full_name, updated_at,
  created_at + text index), companies (canonical_name), person_campaigns
  (composite unique). Export limit raised to 200k. Companies list paginated.

## Core invariants — verified

- **Bhargav test**: `bhargav@company.com` is in "MBA Annual 2026" AND
  "Non-QM Introductory Campaign" — GET /api/people/{bhargav_id} returns ONE
  person with BOTH campaigns.
- **Duplicate on import**: uploading a fresh row for Bhargav via a CSV using
  different header names (e.g. `Contact Name`, `email`) matches by email,
  merges sources, does NOT create a second record.
- **In-campaign filter is OR**: multi-select shows the union.
- **Fuzzy company merge**: `A and D Mortgage`, `A & D Mortgage LLC`,
  `A and D Mortgage, Inc.` share canonical `a and d mortgage`. `Texas Bank`,
  `Texas Bank Pvt Ltd`, `Texas Bank Financial` share canonical `texas bank`.

## Backlog / next up (P0 → P2)

- **P0 — Flag-for-enrichment button** on people missing phone/LinkedIn (per
  original spec, deferred from v1).
- **P0 — Google Sheets direct import (unblock)**: user has provided
  GOOGLE_CLIENT_ID; add GOOGLE_CLIENT_SECRET to `/app/backend/.env` and
  restart backend. UI flow is already wired.
- **P1 — Bulk delete by all-matching-filter** (not just currently-visible
  page). Currently limited to selected on visible pages.
- **P1 — Bulk share** — share multiple campaigns at once.
- **P1 — Person merge tool** on the Duplicate review queue is functional but
  a manual "merge two arbitrary people" UI (side-panel button) is not yet
  wired.
- **P2 — Column mapping memory**: remember mapping per (headers-shape,
  campaign) so repeat imports skip the mapping step (spec mentions this).
- **P2 — Password self-serve reset for members** (currently only admin can
  reset).
- **P2 — Audit trail on merges** (who merged which company/person, when).
- **P2 — In-app onboarding tour** for new invitees.

## Test seed

20 seed people across 17 companies and 7 campaigns (see
`/app/backend/seed_data.py DEMO_PEOPLE`). Admin credentials are in
`/app/memory/test_credentials.md`.
