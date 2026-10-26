-- Whisky subdivisions. Working stills stay facet "distillery".
-- Silent stills, whisky stories, and stills not yet in production
-- use facets silent, story, and planned. The public map reads
-- data/interest_index.json. Not applied remotely in the session that wrote it.

alter table public.interest_memberships
  drop constraint if exists interest_memberships_facet_check;

alter table public.interest_memberships
  add constraint interest_memberships_facet_check
    check (
      facet is null
      or facet in (
        'film', 'artwork', 'music', 'distillery', 'silent', 'story', 'planned',
        'listing', 'wildlife', 'tidal'
      )
    );

insert into public.interest_categories
  (slug, label, blurb, status, sort_order, populator, acceptance_rules)
values
  (
    'whisky-distilleries',
    'Whisky',
    'Working distilleries, silent stills, and the whisky stories that name the island.',
    'published',
    20,
    'wikidata_and_wikipedia',
    'The still is on the island. A working distillery, a silent still the source places on the island, a still the source says is not yet producing, or a whisky story (wreck, film, or festival) whose page names the island. Gin, a stalled plan, a brand whose still is elsewhere, and a closed site the page cannot locate are out.'
  )
on conflict (slug) do update set
  label = excluded.label,
  blurb = excluded.blurb,
  status = 'published',
  sort_order = excluded.sort_order,
  populator = excluded.populator,
  acceptance_rules = excluded.acceptance_rules;
