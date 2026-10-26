-- Unusual news. The public map reads data/interest_index.json.
-- This keeps the database in step: a news facet, and the category row.
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
        'tradition',
        'news'
      )
    );

insert into public.interest_categories
  (slug, label, blurb, status, sort_order, populator, acceptance_rules)
values
  (
    'unusual-news',
    'Unusual news',
    'Strange events a news report places on the island.',
    'published',
    18,
    'cited_news',
    'A news report or published account places the event on that atlas island. The summary is original. The picture is an open-licence photograph of the subject. Great Britain and Ireland do not count. No private address, no photograph of a person, and no grave coordinates.'
  )
on conflict (slug) do update set
  label = excluded.label,
  blurb = excluded.blurb,
  status = 'published',
  sort_order = excluded.sort_order,
  populator = excluded.populator,
  acceptance_rules = excluded.acceptance_rules;
