-- Local traditions. The public map reads data/interest_index.json.
-- This keeps the database in step: a tradition facet, and the category row.
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
        'castle',
        'book',
        'tradition'
      )
    );

insert into public.interest_categories
  (slug, label, blurb, status, sort_order, populator, acceptance_rules)
values
  (
    'local-traditions',
    'Local traditions',
    'A custom, festival, dance, or craft the source places on the island.',
    'published',
    24,
    'cited_tradition',
    'The English Wikipedia article describes the custom and places it on the atlas island. The summary is the article''s own sentences. A legend with no practice, a breed, a book, a film, and a monastic pilgrimage do not count. Great Britain and Ireland do not count. The picture is an open-licence photograph of the custom, or of the island when the article has none.'
  )
on conflict (slug) do update set
  label = excluded.label,
  blurb = excluded.blurb,
  status = 'published',
  sort_order = excluded.sort_order,
  populator = excluded.populator,
  acceptance_rules = excluded.acceptance_rules;
