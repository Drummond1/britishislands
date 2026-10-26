# Supabase setup — Isles of Britain

Backend for **user accounts**, **moderated contributions**, and **cross-device saved islands**.
The canonical island spine stays in `data/islands.json`; Supabase holds community data only.

Schema matches [`PRD-USER-CONTRIBUTIONS.md`](PRD-USER-CONTRIBUTIONS.md) §7, implemented with
**Supabase Auth** + `public.profiles` (no custom password table).

---

## 1. Create a Supabase project

1. Sign in at [supabase.com](https://supabase.com) → **New project**.
2. Pick a region close to UK users (e.g. **London** / `eu-west-2`).
3. Save the database password somewhere safe (you need it for direct Postgres access).

---

## 2. Apply the database schema

**Option A — SQL Editor (no CLI)**

1. In the project: **SQL** → **New query**.
2. Paste the full contents of  
   [`supabase/migrations/20260517000000_initial_contributions.sql`](../supabase/migrations/20260517000000_initial_contributions.sql).
3. **Run**. You should see tables: `profiles`, `submissions`, `community_photos`,
   `community_text`, `reports`, `audit_log`, `saved_islands`, plus bucket `community-photos`.

**Option B — Supabase CLI (local + linked remote)**

```bash
brew install supabase/tap/supabase   # or: npm i -g supabase
cd "/path/to/Scottish Islands"
supabase login
supabase link --project-ref YOUR_PROJECT_REF
supabase db push
```

---

## 3. Configure Auth redirect URLs

**Authentication** → **URL configuration**:

| Setting | Value |
|---------|--------|
| Site URL | `https://www.findmyisland.com` |
| Redirect URLs | `http://127.0.0.1:8765/**`, `http://localhost:8765/**`, `https://www.findmyisland.com/**` |

Enable **Email** provider. Keep **Confirm email** on for production.

---

## 4. API keys (never commit secrets)

**Project Settings** → **API**:

| Key | Use |
|-----|-----|
| Project URL | `SUPABASE_URL` / `window.IOB_SUPABASE_URL` |
| `anon` `public` | Browser client (`supabase-client.js`) |
| `service_role` `secret` | Server scripts / moderation only — **never** in frontend |

Copy [`.env.local.example`](../.env.local.example) → `.env.local` and fill values for local Python scripts.

For the static site, copy [`config.local.example.js`](../config.local.example.js) → `config.local.js`:

```js
window.IOB_SUPABASE_URL = "https://YOUR_PROJECT_REF.supabase.co";
window.IOB_SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...";
```

`index.html` already loads `config.local.js` before `app.js`. Wire `supabase-client.js` when you
enable cloud saved islands or sign-in UI.

---

## 5. Storage bucket

Migration creates **`community-photos`** (private, 10 MB, images only). Upload path convention:

```
{user_id}/{submission_id}/{filename}
```

Moderation tooling (later) copies accepted files to public CDN URLs stored in `community_photos.url_*`.

---

## 6. Row Level Security (summary)

| Table | Anonymous | Signed-in user | Staff |
|-------|-----------|----------------|-------|
| `profiles` | Read active profiles | Update own | Service role for moderation |
| `submissions` | — | Insert + read own | Service role |
| `community_*` | Read published | Read published | Service role writes on accept |
| `saved_islands` | — | Full CRUD own rows | — |
| `audit_log` | — | — | Service role only |
| `interest_categories` | Read `published` | Read `published` | Service role writes |
| `interest_memberships` | Read `accepted` whose category is `published` | Same as anonymous | Service role writes |

Staff actions today require the **service role** key in a trusted worker (Edge Function,
GitHub Action, or local script). Add explicit `is_staff()` policies when you ship a mod UI.

---

## 7. Verify

In **Table Editor**, confirm empty tables exist. In **SQL**:

```sql
select tablename from pg_tables where schemaname = 'public' order by 1;
```

Optional smoke test from the browser console (with `config.local.js` loaded):

```js
import { getSupabase } from "./supabase-client.js";
const sb = getSupabase();
await sb.auth.getSession();
```

---

## 8. Interest categories

Migration `supabase/migrations/20261025122727_interest_categories.sql`.

`interest_categories` is the filter spec: `slug`, `label`, `blurb`, `status` (`draft` | `published` | `retired`), `sort_order`, `populator`, `acceptance_rules`.

`interest_memberships` is one cited hit: `category_slug`, `island_id` (an id that already exists in the atlas), `facet` (`film`, `artwork`, `music`, `distillery`, `silent`, `story`, `planned`, `listing`, `wildlife`, `tidal`), `title`, `source_url`, `licence`, `evidence`, `external_id`, `confidence` (`high` | `medium`), `status` (`candidate` | `accepted` | `rejected`). Unique on category + island + facet + title. Whisky subdivisions (`islay`, `hebrides`, `orkney`, `other`) live on the static index stories, not as their own column.

Anonymous and signed-in clients may `SELECT` published categories and accepted memberships of those categories. There are no insert or update policies. Agents write with the service role from `scripts/interest_categories.py`, never from the browser. The public map does not call these tables; `publish` writes `data/interest_index.json`.

Published (2026-10-25): film, art and music **13** islands / **20** rows; whisky distilleries **10** / **24**; for sale **37** / **37**. Draft, empty, and hidden from the anon API: `uninhabited-stay`.

How to add the next category: [`.cursor/skills/interest-category-populate/SKILL.md`](../.cursor/skills/interest-category-populate/SKILL.md).

---

## Related

- [`PRD-USER-CONTRIBUTIONS.md`](PRD-USER-CONTRIBUTIONS.md) — product scope
- [`ETHICS.md`](ETHICS.md) — licensing and moderation rules
- [`../supabase-client.js`](../supabase-client.js) — browser helper (saved islands first)
