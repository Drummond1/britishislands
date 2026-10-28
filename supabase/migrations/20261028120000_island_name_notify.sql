-- Email the project inbox when someone names an island, and let a private
-- Google Sheet read the same rows. The public map still uses island_names_public(),
-- which does not return the email.

create extension if not exists pg_net;

create table if not exists public.island_name_sheet_token (
  id int primary key,
  token text not null,
  constraint island_name_sheet_token_one check (id = 1)
);

alter table public.island_name_sheet_token enable row level security;
revoke all on table public.island_name_sheet_token from public, anon, authenticated;

comment on table public.island_name_sheet_token is
  'Secret for the private names spreadsheet. Not readable from the browser.';

drop function if exists public.island_names_public();

create function public.island_names_public()
returns table (
  island_id text,
  island_name text,
  contributor_name text,
  attribution text,
  created_at timestamptz,
  lat double precision,
  lng double precision
)
language sql
stable
security definer
set search_path = public
as $$
  select island_id, island_name, contributor_name, attribution, created_at, lat, lng
  from public.island_name_log
  order by created_at asc;
$$;

comment on function public.island_names_public() is
  'Suggested names for the map. Does not return email addresses.';

revoke all on function public.island_names_public() from public;
grant execute on function public.island_names_public() to anon, authenticated;

create or replace function public.island_name_notify()
returns trigger
language plpgsql
security definer
set search_path = public, net
as $$
begin
  perform net.http_post(
    url := 'https://formsubmit.co/ajax/drummondgilbert@gmail.com',
    body := jsonb_build_object(
      '_subject', 'New island name: ' || left(btrim(new.island_name), 80),
      '_template', 'table',
      '_captcha', 'false',
      '_replyto', new.contributor_email,
      'Island', new.island_name,
      'Named by', new.contributor_name,
      'Email', new.contributor_email,
      'Island id', new.island_id,
      'Latitude', new.lat,
      'Longitude', new.lng,
      'When', new.created_at
    ),
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Accept', 'application/json',
      'Origin', 'https://www.findmyisland.com',
      'Referer', 'https://www.findmyisland.com/'
    )
  );
  return new;
exception when others then
  raise warning 'island name notify failed: %', sqlerrm;
  return new;
end;
$$;

revoke all on function public.island_name_notify() from public, anon, authenticated;

drop trigger if exists island_name_notify_trg on public.island_name_log;
create trigger island_name_notify_trg
  after insert on public.island_name_log
  for each row
  execute function public.island_name_notify();

notify pgrst, 'reload schema';
