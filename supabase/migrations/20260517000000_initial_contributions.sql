-- Isles of Britain — community contributions schema (Supabase / Postgres)
-- Aligns with docs/PRD-USER-CONTRIBUTIONS.md §7
-- Auth: Supabase Auth (auth.users); app profile in public.profiles

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
create type public.trust_tier as enum ('0', '1', '2', 'staff');
create type public.user_status as enum ('active', 'suspended', 'banned', 'deleted');
create type public.submission_kind as enum (
  'photo', 'text', 'correction', 'tag', 'report'
);
create type public.submission_status as enum (
  'pending', 'accepted', 'accepted_with_edits', 'rejected', 'withdrawn'
);
create type public.report_reason as enum (
  'copyright', 'nsfw', 'spam', 'inaccurate', 'other'
);
create type public.report_target_kind as enum ('photo', 'text', 'user');

-- ---------------------------------------------------------------------------
-- Profiles (extends auth.users)
-- ---------------------------------------------------------------------------
create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text unique,
  trust_tier public.trust_tier not null default '0',
  contribution_count int not null default 0 check (contribution_count >= 0),
  accepted_count int not null default 0 check (accepted_count >= 0),
  rejected_count int not null default 0 check (rejected_count >= 0),
  status public.user_status not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.profiles is
  'Public contributor profile; email lives in auth.users only.';

-- Auto-create profile on sign-up
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (
    new.id,
    coalesce(
      nullif(trim(new.raw_user_meta_data ->> 'display_name'), ''),
      split_part(new.email, '@', 1)
    )
  );
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- Submissions (moderation queue source of truth)
-- ---------------------------------------------------------------------------
create table public.submissions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  island_id text not null,
  kind public.submission_kind not null,
  payload jsonb not null default '{}',
  status public.submission_status not null default 'pending',
  reviewed_by uuid references public.profiles (id),
  review_reason text,
  created_at timestamptz not null default now(),
  reviewed_at timestamptz
);

create index submissions_status_created_idx
  on public.submissions (status, created_at desc);
create index submissions_island_idx on public.submissions (island_id);
create index submissions_user_idx on public.submissions (user_id);

-- ---------------------------------------------------------------------------
-- Published community content (denormalised for fast reads)
-- ---------------------------------------------------------------------------
create table public.community_photos (
  id uuid primary key default gen_random_uuid(),
  submission_id uuid not null references public.submissions (id),
  island_id text not null,
  user_id uuid not null references public.profiles (id),
  storage_path text not null,
  url_320 text,
  url_800 text,
  url_1600 text,
  url_2560 text,
  caption text,
  date_taken date,
  license text not null,
  attribution text not null,
  width int,
  height int,
  sha256 text,
  phash text,
  accepted_at timestamptz not null default now(),
  deleted_at timestamptz
);

create index community_photos_island_idx
  on public.community_photos (island_id)
  where deleted_at is null;

create table public.community_text (
  id uuid primary key default gen_random_uuid(),
  submission_id uuid not null references public.submissions (id),
  island_id text not null,
  user_id uuid not null references public.profiles (id),
  field_name text not null,
  body text not null,
  accepted_at timestamptz not null default now(),
  supersedes_id uuid references public.community_text (id),
  deleted_at timestamptz
);

create index community_text_island_idx
  on public.community_text (island_id)
  where deleted_at is null;

-- ---------------------------------------------------------------------------
-- Abuse reports
-- ---------------------------------------------------------------------------
create table public.reports (
  id uuid primary key default gen_random_uuid(),
  target_kind public.report_target_kind not null,
  target_id uuid not null,
  reporter_id uuid not null references public.profiles (id),
  reason public.report_reason not null,
  notes text,
  created_at timestamptz not null default now(),
  resolved_at timestamptz,
  resolved_by uuid references public.profiles (id)
);

-- ---------------------------------------------------------------------------
-- Moderator audit (append-only)
-- ---------------------------------------------------------------------------
create table public.audit_log (
  id bigserial primary key,
  actor_id uuid references public.profiles (id),
  action text not null,
  target_table text,
  target_id text,
  metadata jsonb not null default '{}',
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Saved islands (sync hearts across devices; optional MVP)
-- ---------------------------------------------------------------------------
create table public.saved_islands (
  user_id uuid not null references public.profiles (id) on delete cascade,
  island_id text not null,
  created_at timestamptz not null default now(),
  primary key (user_id, island_id)
);

create index saved_islands_user_idx on public.saved_islands (user_id);

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------
alter table public.profiles enable row level security;
alter table public.submissions enable row level security;
alter table public.community_photos enable row level security;
alter table public.community_text enable row level security;
alter table public.reports enable row level security;
alter table public.audit_log enable row level security;
alter table public.saved_islands enable row level security;

-- Profiles: public read display names; users update own row
create policy "profiles_select_public"
  on public.profiles for select
  using (status = 'active');

create policy "profiles_update_own"
  on public.profiles for update
  using (auth.uid() = id)
  with check (auth.uid() = id);

-- Submissions: insert/read own; moderators need service role or staff policies later
create policy "submissions_insert_own"
  on public.submissions for insert
  with check (auth.uid() = user_id);

create policy "submissions_select_own"
  on public.submissions for select
  using (auth.uid() = user_id);

-- Published photos/text: world-readable when not deleted
create policy "community_photos_select_public"
  on public.community_photos for select
  using (deleted_at is null);

create policy "community_text_select_public"
  on public.community_text for select
  using (deleted_at is null);

-- Reports: authenticated users may file
create policy "reports_insert_authenticated"
  on public.reports for insert
  with check (auth.uid() = reporter_id);

create policy "reports_select_own"
  on public.reports for select
  using (auth.uid() = reporter_id);

-- Audit log: no public access (service role / Edge Functions only)
-- (no select policies for anon/authenticated)

-- Saved islands: per-user
create policy "saved_islands_all_own"
  on public.saved_islands for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- Storage: community photo uploads (private bucket; public URLs via signed CDN later)
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'community-photos',
  'community-photos',
  false,
  10485760,
  array['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif']
)
on conflict (id) do nothing;

create policy "community_photos_storage_insert_own"
  on storage.objects for insert
  to authenticated
  with check (
    bucket_id = 'community-photos'
    and (storage.foldername (name))[1] = auth.uid()::text
  );

create policy "community_photos_storage_select_own"
  on storage.objects for select
  to authenticated
  using (
    bucket_id = 'community-photos'
    and (storage.foldername (name))[1] = auth.uid()::text
  );

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------
create or replace function public.is_staff()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid() and trust_tier = 'staff'
  );
$$;
