-- Books set on an island. The public map reads data/interest_index.json.
-- This keeps the database in step: a book facet, and the category row.
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
        'book'
      )
    );

insert into public.interest_categories
  (slug, label, blurb, status, sort_order, populator, acceptance_rules)
values
  (
    'island-books',
    'Books',
    'Novels, memoirs, and stories set on the island.',
    'published',
    22,
    'cited_book',
    'The English Wikipedia article sets the book on the atlas island. Inspired by, based on, and filmed on do not count. Great Britain and Ireland do not count. The picture is an open-licence image of the book, or a photograph of the island when the cover is not open.'
  )
on conflict (slug) do update set
  label = excluded.label,
  blurb = excluded.blurb,
  status = 'published',
  sort_order = excluded.sort_order,
  populator = excluded.populator,
  acceptance_rules = excluded.acceptance_rules;
