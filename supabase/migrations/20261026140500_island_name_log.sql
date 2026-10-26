-- Private log of names suggested for unnamed atlas islands.
-- Visitors may insert a row. They may not read it: the email stays here.
-- The map reads island_names_public(), which omits the email.

create table if not exists public.island_name_log (
  id uuid primary key default gen_random_uuid(),
  island_id text not null,
  island_name text not null,
  contributor_name text not null,
  contributor_email text not null,
  attribution text,
  lat double precision,
  lng double precision,
  created_at timestamptz not null default now(),
  constraint island_name_log_island_id_len check (char_length(trim(island_id)) between 1 and 200),
  constraint island_name_log_island_name_len check (char_length(trim(island_name)) between 2 and 80),
  constraint island_name_log_contributor_len check (char_length(trim(contributor_name)) between 2 and 60),
  constraint island_name_log_email_len check (char_length(trim(contributor_email)) between 6 and 200),
  constraint island_name_log_email_shape check (
    contributor_email ~* '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'
  ),
  constraint island_name_log_attribution_len check (
    attribution is null or char_length(attribution) <= 300
  )
);

comment on table public.island_name_log is
  'Append-only log of visitor names for unnamed islands. Email is private.';

create index if not exists island_name_log_island_idx
  on public.island_name_log (island_id, created_at);

alter table public.island_name_log enable row level security;

revoke all on table public.island_name_log from anon, authenticated;
grant insert on table public.island_name_log to anon, authenticated;

drop policy if exists island_name_log_insert on public.island_name_log;
create policy island_name_log_insert
  on public.island_name_log
  for insert
  to anon, authenticated
  with check (
    char_length(trim(island_id)) between 1 and 200
    and char_length(trim(island_name)) between 2 and 80
    and char_length(trim(contributor_name)) between 2 and 60
    and char_length(trim(contributor_email)) between 6 and 200
    and contributor_email ~* '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'
    and (attribution is null or char_length(attribution) <= 300)
  );

create or replace function public.island_names_public()
returns table (
  island_id text,
  island_name text,
  contributor_name text,
  attribution text,
  created_at timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
  select island_id, island_name, contributor_name, attribution, created_at
  from public.island_name_log
  order by created_at asc;
$$;

comment on function public.island_names_public() is
  'Suggested names for the map. Does not return email addresses.';

revoke all on function public.island_names_public() from public;
grant execute on function public.island_names_public() to anon, authenticated;
