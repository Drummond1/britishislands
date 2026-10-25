-- Interest categories: editorial filters over the static island atlas.
-- The island catalogue stays in data/islands.json. These tables store the
-- category, the cited reason, and which atlas island id it attaches to.
-- Anonymous clients may read published + accepted rows only. Writes are
-- service-role (local populators), never the browser.

-- ---------------------------------------------------------------------------
-- Categories
-- ---------------------------------------------------------------------------
create table public.interest_categories (
  slug text primary key,
  label text not null,
  blurb text,
  status text not null default 'draft'
    check (status in ('draft', 'published', 'retired')),
  sort_order int not null default 100,
  populator text not null,
  acceptance_rules text,
  created_at timestamptz not null default now()
);

comment on table public.interest_categories is
  'Named atlas filters. Draft rows stay off the public map until published.';

-- ---------------------------------------------------------------------------
-- Memberships (one row per cited place, work, or listing on an island)
-- ---------------------------------------------------------------------------
create table public.interest_memberships (
  id uuid primary key default gen_random_uuid(),
  category_slug text not null references public.interest_categories (slug),
  island_id text not null,
  facet text
    check (facet is null or facet in ('film', 'artwork', 'music', 'distillery', 'listing')),
  title text not null,
  source_url text not null,
  source_title text,
  licence text,
  evidence text,
  external_id text,
  confidence text not null
    check (confidence in ('high', 'medium')),
  status text not null default 'candidate'
    check (status in ('candidate', 'accepted', 'rejected')),
  reject_reason text,
  fetched_at timestamptz not null default now()
);

comment on table public.interest_memberships is
  'Cited island hits for an interest category. island_id matches the atlas.';

create unique index interest_memberships_natural_key
  on public.interest_memberships (
    category_slug,
    island_id,
    coalesce(facet, ''),
    title
  );

create index interest_memberships_category_status_idx
  on public.interest_memberships (category_slug, status);

create index interest_memberships_island_idx
  on public.interest_memberships (island_id);

create index interest_categories_status_idx
  on public.interest_categories (status);

-- ---------------------------------------------------------------------------
-- Grants: select only for the Data API. Service role keeps write access.
-- ---------------------------------------------------------------------------
revoke all on table public.interest_categories from public, anon, authenticated;
revoke all on table public.interest_memberships from public, anon, authenticated;

grant select on table public.interest_categories to anon, authenticated;
grant select on table public.interest_memberships to anon, authenticated;

grant select, insert, update, delete on table public.interest_categories to service_role;
grant select, insert, update, delete on table public.interest_memberships to service_role;

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------
alter table public.interest_categories enable row level security;
alter table public.interest_memberships enable row level security;

create policy "interest_categories_select_published"
  on public.interest_categories
  for select
  to anon, authenticated
  using (status = 'published');

create policy "interest_memberships_select_published"
  on public.interest_memberships
  for select
  to anon, authenticated
  using (
    status = 'accepted'
    and exists (
      select 1
      from public.interest_categories c
      where c.slug = interest_memberships.category_slug
        and c.status = 'published'
    )
  );

-- No insert, update, or delete policies for anon or authenticated.

-- ---------------------------------------------------------------------------
-- First-batch specs. Memberships are filled by the populators, not here.
-- ---------------------------------------------------------------------------
insert into public.interest_categories
  (slug, label, blurb, status, sort_order, populator, acceptance_rules)
values
  (
    'film-art-music',
    'Film, art and music',
    'Islands tied to a specific film, artwork, or piece of music.',
    'published',
    10,
    'cited_research',
    'A Wikipedia, Wikidata, or Wikimedia Commons page must name both the work and the island. Filmed there, the work depicts the island, or the song, album, or video is about it. Inspired by the wider region is not enough.'
  ),
  (
    'whisky-distilleries',
    'Whisky distilleries',
    'Islands with a working whisky distillery.',
    'published',
    20,
    'osm_wikidata',
    'The distillery itself sits on the island. Evidence is an OpenStreetMap craft=distillery feature or a Wikidata distillery whose location chain is that island. A caption that merely mentions whisky is not enough.'
  ),
  (
    'for-sale',
    'For sale',
    'Islands with a current broker listing.',
    'published',
    30,
    'property_registry',
    'Copy the verified property registry only. Outbound broker links. Do not scrape Rightmove, Zoopla, or OnTheMarket.'
  ),
  (
    'uninhabited-stay',
    'Uninhabited, with a place to stay',
    'Uninhabited islands where a visitor can stay, without publishing private addresses.',
    'draft',
    40,
    'cited_research',
    'Population is not known to be above zero, and a public island-level place to stay is cited (bothy, hostel, or island-level holiday let). No street addresses, owner names, or private dwelling details.'
  );
