-- SYN-507: client_videos table
-- Feeds: VideoObject schema (SYN-507), Featured in Synthex (SYN-508), YouTube embed widget (SYN-509)
-- youtube_video_id: just the ID (e.g. "dQw4w9WgXcQ"), not the full URL
-- duration_iso: ISO 8601 duration (e.g. "PT2M30S" = 2 min 30 sec)

create table if not exists client_videos (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references clients(id) on delete cascade,
  youtube_video_id text not null,
  title text not null,
  description text,
  thumbnail_url text,
  upload_date date not null,
  duration_iso text,
  published_at timestamptz default now(),
  created_at timestamptz default now(),
  unique (client_id, youtube_video_id)
);

create index if not exists idx_client_videos_client_id on client_videos(client_id, published_at desc);

alter table client_videos enable row level security;

create policy "service_role_all" on client_videos
  for all
  using (true)
  with check (true);

create policy "client_read_own_videos" on client_videos
  for select
  using (
    client_id in (
      select id from clients where user_id = auth.uid()
    )
  );
