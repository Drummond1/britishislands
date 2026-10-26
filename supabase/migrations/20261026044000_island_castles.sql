-- Islands with Castles. The public map reads data/interest_index.json.
-- This keeps the database in step: a castle facet, and the category row.
-- Not applied remotely in the session that wrote it.

alter table public.interest_memberships
  drop constraint if exists interest_memberships_facet_check;

alter table public.interest_memberships
  add constraint interest_memberships_facet_check
    check (
      facet is null
      or facet in (
        'film',
        'artwork',
        'music',
        'distillery',
        'listing',
        'wildlife',
        'tidal',
        'silent',
        'story',
        'planned',
        'castle'
      )
    );

insert into public.interest_categories
  (slug, label, blurb, status, sort_order, populator, acceptance_rules)
values
  (
    'island-castles',
    'Islands with Castles',
    'Islands with a castle standing on them.',
    'published',
    40,
    'cited_castle',
    'A castle stands on the atlas island. The citation is English Wikipedia, Wikidata, OpenStreetMap, Canmore, the National Heritage List for England, Cadw, or the Archaeological Survey of Ireland. A martello tower, a broch, and a fort do not count. Great Britain and Ireland do not count. No living owner, private address, or way in.'
  )
on conflict (slug) do update set
  label = excluded.label,
  blurb = excluded.blurb,
  status = 'published',
  sort_order = excluded.sort_order,
  populator = excluded.populator,
  acceptance_rules = excluded.acceptance_rules;
