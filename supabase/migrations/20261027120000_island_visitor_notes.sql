-- Visitor notes: what's interesting, and what you can do.
-- Anonymous clients may insert a row and may read the public function.
-- contributor_email is optional. It is not returned by the public function,
-- and anonymous clients cannot select the table. These notes are not part of islands.json.

create table if not exists public.island_visitor_notes (
  id uuid primary key default gen_random_uuid(),
  island_id text not null,
  interesting text,
  can_do text,
  contributor_name text not null,
  contributor_email text,
  created_at timestamptz not null default now()
);

alter table public.island_visitor_notes
  add column if not exists contributor_email text;

alter table public.island_visitor_notes drop constraint if exists island_visitor_notes_island_id_len;
alter table public.island_visitor_notes drop constraint if exists island_visitor_notes_name_len;
alter table public.island_visitor_notes drop constraint if exists island_visitor_notes_interesting_len;
alter table public.island_visitor_notes drop constraint if exists island_visitor_notes_can_do_len;
alter table public.island_visitor_notes drop constraint if exists island_visitor_notes_has_text;
alter table public.island_visitor_notes drop constraint if exists island_visitor_notes_email_shape;
alter table public.island_visitor_notes drop constraint if exists island_visitor_notes_no_email_in_text;

alter table public.island_visitor_notes
  add constraint island_visitor_notes_island_id_len check (char_length(trim(island_id)) between 1 and 200);

alter table public.island_visitor_notes
  add constraint island_visitor_notes_name_len check (char_length(trim(contributor_name)) between 2 and 60);

alter table public.island_visitor_notes
  add constraint island_visitor_notes_interesting_len check (
    interesting is null or char_length(interesting) <= 280
  );

alter table public.island_visitor_notes
  add constraint island_visitor_notes_can_do_len check (
    can_do is null or char_length(can_do) <= 280
  );

alter table public.island_visitor_notes
  add constraint island_visitor_notes_has_text check (
    char_length(trim(coalesce(interesting, ''))) >= 4
    or char_length(trim(coalesce(can_do, ''))) >= 4
  );

alter table public.island_visitor_notes
  add constraint island_visitor_notes_email_shape check (
    contributor_email is null
    or (
      char_length(trim(contributor_email)) between 6 and 200
      and contributor_email ~* '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'
    )
  );

alter table public.island_visitor_notes
  add constraint island_visitor_notes_no_email_in_text check (
    coalesce(interesting, '') !~* '[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+'
    and coalesce(can_do, '') !~* '[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+'
    and contributor_name !~* '[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+'
  );

comment on table public.island_visitor_notes is
  'Visitor notes on an island. Not canonical. Email is private and is omitted from island_visitor_notes_public().';

comment on column public.island_visitor_notes.contributor_email is
  'Optional reply address. Not published and not readable by anonymous clients.';

create index if not exists island_visitor_notes_island_idx
  on public.island_visitor_notes (island_id, created_at desc);

alter table public.island_visitor_notes enable row level security;

revoke all on table public.island_visitor_notes from anon, authenticated;
grant insert on table public.island_visitor_notes to anon, authenticated;
grant all on table public.island_visitor_notes to service_role;

drop policy if exists island_visitor_notes_insert on public.island_visitor_notes;
create policy island_visitor_notes_insert
  on public.island_visitor_notes
  for insert
  to anon, authenticated
  with check (
    char_length(trim(island_id)) between 1 and 200
    and char_length(trim(contributor_name)) between 2 and 60
    and (interesting is null or char_length(interesting) <= 280)
    and (can_do is null or char_length(can_do) <= 280)
    and (
      char_length(trim(coalesce(interesting, ''))) >= 4
      or char_length(trim(coalesce(can_do, ''))) >= 4
    )
    and (
      contributor_email is null
      or (
        char_length(trim(contributor_email)) between 6 and 200
        and contributor_email ~* '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'
      )
    )
    and coalesce(interesting, '') !~* '[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+'
    and coalesce(can_do, '') !~* '[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+'
    and contributor_name !~* '[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+'
  );

create or replace function public.island_visitor_notes_public()
returns table (
  id uuid,
  island_id text,
  interesting text,
  can_do text,
  contributor_name text,
  created_at timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
  select id, island_id, interesting, can_do, contributor_name, created_at
  from public.island_visitor_notes
  order by created_at desc
  limit 400;
$$;

comment on function public.island_visitor_notes_public() is
  'Visitor notes for the island page. Does not return email addresses.';

revoke all on function public.island_visitor_notes_public() from public;
grant execute on function public.island_visitor_notes_public() to anon, authenticated;
