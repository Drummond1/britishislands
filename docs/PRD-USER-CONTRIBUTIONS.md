# PRD — User contributions: photos, content, and accounts

Status: **Draft v1**
Owner: drummondgilberta2aa9
Last updated: 2026-05-12

---

## 1. Context

Today the atlas is a static site that ships a single `data/islands.json`
of ~6,776 islands built top-down from open data (OSM, Wikidata, OS,
Wikimedia Commons). Every record carries a provenance entry and an
explicit licence (see [`ETHICS.md`](ETHICS.md)). There is no backend,
no database, and no concept of a user.

This PRD describes what it would take to let real people upload photos
and contribute textual content (corrections, anecdotes, accommodation
tips, etc.) **without breaking the licensing rigour or the static
deploy model below a sensible threshold**.

It is intentionally opinionated: the recommendation is **gated
contributions with mandatory sign-up**, a strict moderation queue, and
a per-feature dark-launch.

---

## 2. Problem & opportunity

### Problem
- The current dataset is comprehensive but impersonal. Photos come from
  Wikimedia Commons (great) or are absent (worse — 5,800+ islands have
  no usable image).
- Locals, kayakers, lighthouse-keepers' descendants, RSPB volunteers,
  ferry operators, and visitors hold tacit knowledge no public dataset
  captures: "the only safe landing is the east cove at low tide", "the
  bothy was repainted in 2024", "the puffin colony moved north of the
  cairn".
- Content like that is the difference between a reference site and a
  destination.

### Opportunity
- Photo-fill rate could go from ~14 % to >60 % within a year with a
  modest contributor base (200–500 active uploaders).
- Cross-references (corrections to OSM, additions to Wikidata) make
  the project a positive contributor to the upstream commons.
- Builds the foundation for higher-trust features later: trip reports,
  ferry-status crowdsourcing, accessible-landing reports.

### Why now
- Area + elevation pipelines have just landed (2026-05-12), so the
  factual spine is solid enough that user contributions sit on top of
  authoritative data rather than fighting it.
- The chatbot Q&A surface (also 2026-05-12) reveals interaction is
  desirable; users immediately want to ask follow-up questions and
  add their own facts.

---

## 3. Goals & non-goals

### Goals (MVP)
1. Authenticated users can upload **photos** to any island, with caption
   and licence selection.
2. Authenticated users can submit **text contributions** (description
   improvements, transport notes, accommodation tips, corrections).
3. **Every contribution passes through a moderation queue** before
   going live; nothing user-uploaded is ever auto-published.
4. **Attribution and licence are preserved end-to-end** for every
   accepted upload, mirroring the existing `provenance` model.
5. Visitors can browse and read user contributions without signing up.
6. A clean separation between **canonical data** (auto-ingested,
   provenance-bound, deterministic) and **community data**
   (user-uploaded, moderated, mutable). They render in the UI together
   but live in distinct stores.

### Goals (post-MVP, 6–12 months)
- Reputation / trust score per contributor (silent for first 90 days).
- Verified-local badge (claim via postcode + light identity check).
- Comments & threaded Q&A on each island.
- Edit-suggestions on canonical fields (proposed corrections flow back
  to OSM / Wikidata where appropriate).
- Trip reports with date-stamped condition reports.

### Non-goals
- Replacing the auto-ingestion pipeline. User content augments;
  it never overrides Wikidata/OSM-sourced canonical fields without an
  audit step.
- Real-time chat or DMs between users.
- Hosting commercial listings (accommodation bookings stay affiliate
  links to Booking.com / Airbnb / Hostelworld as per existing model).
- Anonymous contributions. We require a real email + accept-terms gate.
- Selling user data. **Never.**

---

## 4. Personas

| Persona | Description | Primary action | Trust tier on day 1 |
|---|---|---|---|
| **Visitor** | Anyone reading the atlas. No account. | Browse, read, share | n/a |
| **Casual contributor** | Hikers / kayakers / day-trippers who took a nice photo. | Upload 1–5 photos a year. | Tier 0 — every submission moderated. |
| **Engaged contributor** | Locals, ferry crew, naturalists. Tens of uploads, repeated visits. | Photos + descriptions + corrections. | Tier 1 after ≥10 accepted contributions; less aggressive moderation. |
| **Domain expert** | RSPB volunteer, OS field surveyor, lighthouse historian, dialect linguist. Invited or applied. | Substantive corrections; some auto-publish rights for specific fields. | Tier 2 (invite-only). |
| **Moderator** | Project team or trusted volunteers. | Review queue, accept/reject/escalate, ban abusers. | Staff. |
| **Admin** | Owner. Schema migrations, feature flags, takedowns. | Everything above + delete & restore. | Staff. |

---

## 5. User stories

### Visitor
- As a visitor, I can browse community photos on an island page
  alongside curated photos so I see both perspectives.
- As a visitor, I can sort or filter to view "community only" or
  "curated only" if I want to confirm a fact against open sources.
- As a visitor, I see who contributed each piece of content and the
  licence it is under.

### Casual contributor
- As a logged-in user, I can drag a photo onto an island page and add a
  caption in <30 seconds.
- As a logged-in user, I see clear copy explaining that:
  - I own the photo or have the right to upload it;
  - I am granting a licence (CC-BY 4.0 default, with a CC0 or
    rights-reserved option);
  - my email is private but my display name is public.
- As a logged-in user, I get email confirmation when my upload is
  accepted, rejected, or needs more info.
- As a logged-in user, I can see all my contributions in a profile page
  and edit captions or delete photos.

### Engaged contributor
- As a Tier 1 contributor I can submit a correction to a non-canonical
  field (description, accommodation, transport) that goes live within
  4 hours instead of 24.
- I can flag other contributors' content as inappropriate or
  copyright-infringing.

### Moderator
- As a moderator, I have a queue showing every pending submission with
  EXIF data, perceptual hash, similar-image matches, reverse-image
  search shortcut, and the contributor's history.
- I can accept, accept-with-edits, reject (with reason category),
  or escalate to admin.
- I can ban a user account and roll back all their accepted
  contributions in one action.

### Admin
- As an admin, I can issue a DMCA-style takedown that purges an image
  from storage and CDN within 1 hour.
- I can export every piece of data about a single user (GDPR Article
  15) and delete every piece of their personal data (Article 17) on
  request.

---

## 6. Functional requirements

### 6.1 Accounts & authentication

| Requirement | Detail |
|---|---|
| Sign-up methods | Email + password **and** OAuth (Google, Apple, GitHub). |
| Email verification | Required before first upload. |
| Password | Argon2id hashed; min 10 chars; HIBP-pwned check on set. |
| MFA | TOTP optional for all users; **mandatory** for moderators and admins. |
| Session | Signed JWT (httpOnly cookie), 7-day idle, 30-day max. |
| Age gate | Self-attested 16+ on sign-up; under-16 is hard-blocked from uploads (UK GDPR Article 8 / Irish equivalents). |
| Account deletion | Self-service in profile settings; full erasure within 30 days. |
| Public profile | Display name, optional bio (≤280 chars), list of accepted contributions. Email never exposed. |

### 6.2 Photo upload

| Requirement | Detail |
|---|---|
| Formats | JPEG, PNG, WebP, HEIC (server-side converts to JPEG/AVIF). |
| Max size | 25 MB per file; resized server-side to a 320 / 800 / 1600 / 2560 px ladder. |
| Upload UX | Drag-and-drop on island page, mobile camera capture, EXIF auto-fill for date and (optional) location. |
| EXIF | Strip GPS by default; allow user to opt-in to keeping GPS if they confirm the photo is not of a private dwelling. |
| Per-photo metadata | Caption (required, ≤200 chars), date taken, licence choice (CC-BY 4.0 default; CC0 or rights-reserved alt), source attribution (defaults to display name). |
| Tagging | Optional tags: beach, summit, wildlife, transport, accommodation, weather, etc. — same vocabulary the chatbot already uses. |
| Quota | 20 uploads/day for Tier 0, 100/day for Tier 1, unlimited for Tier 2. |
| Storage | S3-compatible object store (Cloudflare R2 or AWS S3) with image transforms behind a CDN. |
| Hashing | sha256 + pHash on ingest; reject exact duplicates, surface near-duplicates to the moderator. |

### 6.3 Text contributions

Five field categories, each with its own moderation rules:

| Field | Canonical source | User contribution model |
|---|---|---|
| `name`, `nation`, `type`, `subtype`, `lat`, `lng`, `areaKm2`, `highestPointM`, `population` | Auto-ingested, locked. | **Suggest a correction** with citation; routed to admin queue; if accepted, attempt upstream PR to OSM/Wikidata. |
| `shortDescription`, `history`, `geography` | Often auto-stub from Wikipedia. | **Replace or extend** with a moderator-approved version. Diff shown to moderator. |
| `transport`, `accommodation` | Often empty. | **Free text up to 2,000 chars**, moderation-required. |
| `tips`, `bestSeasons`, `accessNotes` *(new fields)* | None. | Net-new community-only fields; never written by auto-ingestion. |
| Tags | Auto + curated. | Users can add or remove tags subject to moderation. |

### 6.4 Moderation

- Every Tier 0 submission is held in a queue rendered to the moderator
  in a single-page review UI.
- Auto-pre-checks run before queueing:
  - Perceptual hash matches against an internal NSFW/violence model
    (open-source classifier; AWS Rekognition fallback if budget allows).
  - Reverse-image lookup against Google Images and TinEye (manual click,
    not automated).
  - Per-pixel similarity to existing Wikimedia Commons assets (cheap
    pHash join).
  - Spam classifier on captions and text contributions.
- A moderator may **accept**, **accept with edit**, **reject (with
  category)**, or **escalate**. Rejected uploads are stored for 14 days
  for appeal then purged.
- Tier 1 users skip pre-moderation for text contributions on
  non-canonical fields only; photos still go through.
- Tier 2 (expert) users may auto-publish on a scoped allowlist of
  fields per island.

### 6.5 Display

- Island detail panel gains a **Community** section, with subsections
  for photos and notes.
- Each card carries a small badge:
  - "Curated" (existing pipeline) — current pill style.
  - "Community" with the contributor's display name and date.
- A persistent "Suggest a correction" link sits at the bottom of every
  island page; visible to logged-out visitors too (clicking prompts
  sign-up).
- "Report" link on every community item routes to moderation queue.

### 6.6 Notifications

- Email-only for v1. No push, no in-app bell.
- Templates: upload received, upload accepted, upload rejected (with
  category), correction accepted, report received, account warning,
  account suspension.

---

## 7. Data model additions

Introduce a relational store for everything user-related. The island
spine (`data/islands.json`) stays canonical and immutable on the build
side; community data lives in the DB and is *merged in at render time*.

```
users
  id (uuid)
  email (unique, encrypted at rest)
  display_name (unique, public)
  password_hash
  created_at, last_login_at
  trust_tier (0 | 1 | 2 | staff)
  contribution_count, accepted_count, rejected_count
  status (active | suspended | banned | deleted)
  email_verified_at

submissions
  id (uuid)
  user_id → users.id
  island_id (matches data/islands.json id)
  kind (photo | text | correction | tag | report)
  payload (jsonb — schema per `kind`)
  status (pending | accepted | accepted_with_edits | rejected | withdrawn)
  reviewed_by (user_id of moderator, nullable)
  review_reason (enum, nullable)
  created_at, reviewed_at

community_photos (denormalised, queried at render)
  id, submission_id, island_id, user_id
  url_320, url_800, url_1600, url_2560
  caption, date_taken, license, attribution
  width, height, sha256, phash
  accepted_at, deleted_at

community_text
  id, submission_id, island_id, user_id, field_name
  body (markdown subset; sanitised on render)
  accepted_at, supersedes_id (nullable for revisions)

reports
  id, target_kind (photo | text | user), target_id, reporter_id
  reason (copyright | nsfw | spam | inaccurate | other)
  notes, created_at, resolved_at, resolved_by

audit_log
  Everything moderator-touched; immutable; 7-year retention.
```

Render-time merge:

```
final_island = canonical_island
             + community_photos.find(island_id)
             + community_text.find(island_id, by field, latest accepted)
```

---

## 8. Technical architecture

This is the largest single change. We move from "files on a CDN" to
"static frontend + small backend + object store + Postgres".

### 8.1 Stack recommendation

| Layer | Choice | Rationale |
|---|---|---|
| Frontend | Existing vanilla JS app; add `?` `/contribute`, `/profile`, `/queue` routes. | No build step today; we keep it. |
| Edge/CDN | Cloudflare. | Already what the static site likely fronts; free tier covers us. |
| Backend | Cloudflare Workers + D1 (SQLite) **or** a small Fly.io node running FastAPI + Postgres. | Workers + D1 if traffic stays low (<1M req/mo); Fly + Postgres if we expect heavier moderation tooling. |
| Auth | Clerk or Auth.js (self-hosted). Clerk for speed-to-MVP, Auth.js if we want zero per-MAU cost. | Sidesteps writing password reset, OAuth, MFA from scratch. |
| Storage | Cloudflare R2 (S3-compatible, no egress fees). | Egress is the silent killer for image hosts. |
| Image transforms | Cloudflare Images (per-image pricing) or `cf-image-resize` workers. | Avoids running ImageMagick ourselves. |
| Email | Postmark transactional. | Reliable, low volume, cheap. |
| Background jobs | Cloudflare Cron + Queues (or a tiny Sidekiq if on Fly). | Reverse-image checks, EXIF stripping, thumbnail generation. |
| Search | Existing client-side index for islands. New full-text on submissions via Postgres `tsvector`. | Keeps current UX. |
| Logging | Cloudflare Logpush → R2; structured JSON. | Cheap and durable. |
| Observability | Sentry (errors), simple Grafana dashboard on Postgres metrics. | Sufficient for MVP. |

### 8.2 Build flow change

```
old: scripts/* → data/islands.json → git push → CDN
new: scripts/* → data/islands.json → git push → CDN
     (unchanged)
     +
     user actions → backend API → DB → ETL pass → community.json
                                               → published nightly
                                               (or, on accept, hot-pushed
                                                via cache invalidation)
```

Two delivery patterns to choose between (Open Question 1):

- **A. JSON-side-car**: nightly bake of `data/community.json`,
  fetched in parallel with `data/islands.json` and merged client-side.
  Pros: keeps offline-friendly static UX. Cons: 24-hour lag for new
  contributions; large file growth.
- **B. Live API**: backend `GET /api/community/island/:id` called on
  each island click. Pros: instant, paginated, cheap per request.
  Cons: forces a backend dependency for every page open.

Recommended: **B for photos, A for tags** (low-volume + bake-friendly).

### 8.3 Backwards compatibility

- The static atlas must continue to function with `community.json`
  unreachable; community sections simply don't render. **Hard
  requirement.**
- The chatbot continues to ignore community text in v1 (Open Question 4).

---

## 9. Trust, safety, legal & compliance

### 9.1 Licensing posture
- Default licence offered to uploaders: **CC-BY 4.0**.
- Permitted alternatives: CC0 1.0, CC-BY-SA 4.0.
- **Rights-reserved is not permitted**; we don't host content we can't
  redistribute under our own ETHICS.md rules.
- Every accepted contribution carries an immutable `provenance` row
  citing the contributor, licence, upload date, and accepted-by
  moderator id.

### 9.2 Copyright
- Terms of upload include a *signed* declaration that the user owns or
  has the right to license the work. Stored alongside the submission.
- DMCA-equivalent takedown flow: reachable from any island page, SLA
  72 h for staff review, 1 h for emergency takedown.
- Three confirmed copyright strikes → permanent ban + content rollback.

### 9.3 Privacy (UK GDPR + Irish Data Protection Act)
- Lawful basis for processing: contract (account) and consent
  (community contributions).
- Data Protection Officer details published in Privacy Policy.
- GDPR Articles 15 (access), 16 (rectification), 17 (erasure), 20
  (portability) self-serviceable in profile, with a 30-day SLA.
- Cookie banner only if we add non-essential cookies; auth cookie is
  strictly necessary so consent banner is not required for that.
- All emails encrypted at rest; never sold or shared. Email is
  available to mods only when investigating abuse.

### 9.4 Minors
- Self-attested 16+ at sign-up; uploads blocked under 16.
- Photos containing identifiable minors must be flagged by uploader
  and either consent-confirmed or rejected. Automatic age estimation
  is a moderation aid, not an auto-reject signal.

### 9.5 Geographic / location safety
- GPS EXIF is stripped by default to protect private dwellings.
- Locations of sensitive sites (RSPB Schedule 1 nests, MoD ranges,
  certain seal pupping beaches) follow the existing ETHICS.md rules:
  we accept photos but not precise locations.

### 9.6 Moderation policy
- Plain-English Community Guidelines published before launch.
- Rejection categories: copyright, off-topic, NSFW, low quality, exact
  duplicate, fabricated location, spam, harassment, advertising.
- Right of appeal: 14-day window via email reply; second human review.

### 9.7 Defamation
- User-uploaded text is hosted-not-published in legal terms; the
  notice-and-takedown safe harbour applies. Designated complaints
  email published.

---

## 10. Roll-out phases

Each phase is a separate releasable unit; do not start the next until
the prior has been stable for two weeks.

### Phase 0 — Foundations (4 weeks)
- Stand up backend, auth, DB, R2.
- Build moderation queue UI (private route).
- Publish Privacy Policy, Terms, Community Guidelines.
- Tabletop legal review.

### Phase 1 — Photo uploads, gated launch (3 weeks)
- Open to a hand-picked beta of ~25 contributors recruited via
  existing contacts.
- Moderation 100 %, no Tier 1 promotion yet.
- Goal: ≥80 % moderator-acceptance rate; <2 h moderator turnaround.

### Phase 2 — Open photo uploads (4 weeks)
- Sign-up open to anyone. Email verification required.
- Tier 1 promotion auto-fires at 10 accepted submissions.
- Add public profile page.

### Phase 3 — Text contributions on non-canonical fields (4 weeks)
- Description, transport, accommodation, tips.
- Diff view for moderators.
- Render attribution under each modified field.

### Phase 4 — Suggest-a-correction on canonical fields (open-ended)
- Routed to admin only.
- Successful corrections trigger an upstream contribution to OSM /
  Wikidata where applicable.

### Phase 5 — Trust system, reports, badges (open-ended)
- Tier 2 invite flow.
- Reputation scoring (silent first).
- Verified-local badge.

---

## 11. Success metrics

### MVP exit criteria (end of Phase 2)
- ≥200 sign-ups.
- ≥50 active contributors (≥1 accepted submission).
- ≥1,500 accepted photos.
- ≥10 % of currently photo-less islands have ≥1 community photo.
- Moderator queue median age <12 h.
- Zero copyright complaints unresolved >72 h.

### 12-month targets
- ≥10,000 accepted photos.
- ≥60 % of all islands have at least one photo (community or curated).
- ≥500 accepted text contributions.
- Contributor retention (≥1 submission/quarter) ≥30 %.
- DMCA volume <0.5 % of submissions.

### Guardrail metrics (must NOT regress)
- Time-to-interactive on island page ≤2.0 s P75 (current: ~1.4 s).
- Total page weight increase for community content ≤300 KB P75.
- Static-site fallback works when backend is down (manual test
  every release).

---

## 12. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Copyright laundering (users uploading scraped photos) | High | High | pHash-match against Wikimedia / Flickr commons; visible reverse-image-search shortcut for moderators; three-strikes ban. |
| Moderation backlog | High | Med | Cap Tier 0 daily quota; auto-defer if queue >100; recruit 3+ volunteer mods before Phase 2. |
| Vandalism on canonical fields | Med | High | No user-writeable path to canonical fields; suggest-corrections route only. |
| Cost runaway (image storage / bandwidth) | Med | Med | R2 zero-egress; image-transforms billed per-image not per-fetch; budget alarm at £50/mo. |
| Legal complaint (defamation, copyright, child safety) | Low | Very high | Hosted-not-published terms; designated complaints email; takedown SLA; staff insurance line item. |
| Community capture by special interests (e.g. estate owners removing tips) | Med | Med | Public audit log per island; reverts visible. |
| Backend outage breaks islands page | Low | High | Frontend must render canonical data even if API errors; explicit fallback test. |
| Account farming / spam | High | Low | Email verification + HIBP password check + per-IP rate limits. |
| GDPR mistake | Low | Very high | DPO designated; legal review at end of Phase 0; automated data-export and erasure paths in v1. |

---

## 13. Cost envelope (rough)

Monthly, in £, at ~10k MAU / ~1k uploads:

| Item | Cost |
|---|---|
| Cloudflare (CDN + Workers + R2 + Images) | 15–25 |
| Postgres (Fly.io 1 GB) **or** D1 (within free tier) | 0–10 |
| Postmark email (10k sent) | 8 |
| Auth (Auth.js self-hosted) | 0 |
| Sentry (developer tier) | 0–25 |
| Domain / TLS | 0 (already paid) |
| **Total** | **~25–70 / mo** |

Beta phase fits inside free tiers; the figure scales near-linearly with
storage, which is the dominant variable.

---

## 14. Open questions (decisions needed before Phase 0)

1. **Delivery model**: JSON side-car bake vs live API for community
   photos? (Recommendation: live API.)
2. **Auth provider**: Clerk (faster, costs at scale) vs Auth.js
   (free, more work).
3. **Default licence**: CC-BY 4.0 vs CC0. CC-BY is friendlier to
   uploaders; CC0 lets us push to Wikimedia Commons trivially.
4. **Chatbot vs community content**: should the Q&A engine surface
   community photos and notes, or stay canonical-only? (Strongly
   recommended: stay canonical for v1; revisit in Phase 4.)
5. **Verification of "local" status**: postcode + selfie holding ID? A
   subscription to a single local newspaper? Hand-vouching by a Tier 2
   contributor? Defer to Phase 5.
6. **Naming**: keep "Community" label or use something warmer like
   "From visitors" / "Islander contributions" / "Field notes"?
7. **Pre-launch beta recruitment**: existing Wikimedia island
   contributors (already CC-aligned), Hebridean Way cyclists, RSPB
   reserve wardens?
8. **Geographic scope at launch**: open to all 6,776 islands at once,
   or stage by nation (e.g. Scotland first)?
9. **Moderator team**: paid staff, volunteers, or hybrid? Volunteer
   programme needs its own light governance doc.

---

## 15. Out of scope (explicitly)

- Booking integrations beyond the existing affiliate-link model.
- Monetisation of contributors (creator payouts, etc.).
- Mobile apps; the web app remains the only surface.
- Federated identity (ActivityPub etc.); revisit if interest emerges.
- Real-time multi-user editing.
- Auto-translation of community content; English at launch, expand
  via professional translation later.

---

## 16. Appendix: relationship to existing docs

- [`ETHICS.md`](ETHICS.md) — licensing rules above are **subordinate**
  to this file. If they conflict, ETHICS wins. (Update ETHICS only if
  the change is unambiguously safer than the current rule.)
- [`DATA-SCHEMA.md`](DATA-SCHEMA.md) — does not change for v1. The
  canonical record stays as is; community data is merged at render
  time, not written into `data/islands.json`.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — needs a new section ("§6.
  Backend & community data") added alongside Phase 0.
- [`SESSION-LOG.md`](SESSION-LOG.md) — append a phase-completion entry
  at each release.

