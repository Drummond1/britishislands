-- Unusual wildlife filter. Island-level species only.
-- The public map reads data/interest_index.json. This keeps the database
-- in step: a wildlife facet, and the published category row.

alter table public.interest_memberships
  drop constraint if exists interest_memberships_facet_check;

alter table public.interest_memberships
  add constraint interest_memberships_facet_check
  check (
    facet is null
    or facet in ('film', 'artwork', 'music', 'distillery', 'listing', 'wildlife')
  );

insert into public.interest_categories
  (slug, label, blurb, status, sort_order, populator, acceptance_rules)
values
  (
    'unusual-wildlife',
    'Unusual wildlife',
    'Islands with a rare, endemic, or remarkable animal or plant.',
    'published',
    25,
    'cited_research',
    'A Wikipedia, Wikidata, or Open Government Licence page names the species and the island. The species is endemic, named for the island, or a principal stronghold. No colony coordinates, nest counts, or visit advice. The picture is of the species.'
  )
on conflict (slug) do update set
  label = excluded.label,
  blurb = excluded.blurb,
  status = 'published',
  sort_order = excluded.sort_order,
  populator = excluded.populator,
  acceptance_rules = excluded.acceptance_rules;
