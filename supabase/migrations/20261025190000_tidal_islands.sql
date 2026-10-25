-- Tidal islands filter. Cited from the English Wikipedia article
-- Tidal island. The public map reads data/interest_index.json.
-- This keeps the database in step: a tidal facet, and the category row.
-- Not applied remotely in the session that wrote it.

alter table public.interest_memberships
  drop constraint if exists interest_memberships_facet_check;

alter table public.interest_memberships
  add constraint interest_memberships_facet_check
    check (
      facet is null
      or facet in ('film', 'artwork', 'music', 'distillery', 'listing', 'wildlife', 'tidal')
    );

insert into public.interest_categories
  (slug, label, blurb, status, sort_order, populator, acceptance_rules)
values
  (
    'tidal-islands',
    'Tidal islands',
    'Islands joined to other land at low tide and cut off at high tide.',
    'published',
    35,
    'wikipedia_tidal_island',
    'The English Wikipedia article Tidal island names the island for Britain, Ireland, Guernsey, or Jersey, and the link is exposed at low tide and submerged at high tide. A permanent causeway named on that page is out. No crossing times.'
  )
on conflict (slug) do update set
  label = excluded.label,
  blurb = excluded.blurb,
  status = 'published',
  sort_order = excluded.sort_order,
  populator = excluded.populator,
  acceptance_rules = excluded.acceptance_rules;
