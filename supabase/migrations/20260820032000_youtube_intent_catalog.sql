-- Intent-only YouTube research catalog for UG-N Nexus.
-- Stores strategic signals only; personal/entertainment rows are marked excluded.

create table if not exists public.youtube_signal_items (
  id bigserial primary key,
  video_key text not null unique,
  video_id text,
  url text,
  title text not null,
  channel text not null default '',
  description text not null default '',
  tags jsonb not null default '[]'::jsonb,
  watch_count_window integer not null default 1,
  selected_by_user boolean not null default false,
  force_include boolean not null default false,
  force_exclude boolean not null default false,
  relevance_status text not null check (relevance_status in ('accepted','excluded')),
  exclusion_reason text,
  strategic_hits jsonb not null default '[]'::jsonb,
  entertainment_hits jsonb not null default '[]'::jsonb,
  ingested_at timestamptz not null default now()
);

create index if not exists youtube_signal_items_relevance_idx
  on public.youtube_signal_items (relevance_status, watch_count_window desc);

create table if not exists public.youtube_topics (
  id bigserial primary key,
  topic text not null,
  confidence numeric(4,3) not null,
  frequency_score numeric(10,2) not null,
  novelty_score numeric(10,2) not null default 0,
  linked_signal_keys jsonb not null default '[]'::jsonb,
  extracted_at timestamptz not null default now()
);

create index if not exists youtube_topics_topic_idx
  on public.youtube_topics (topic, extracted_at desc);

create table if not exists public.persona_traits (
  id bigserial primary key,
  trait text not null,
  evidence_topics jsonb not null default '[]'::jsonb,
  confidence numeric(4,3) not null,
  last_reinforced_at timestamptz not null default now()
);

create table if not exists public.vertical_pathway_signals (
  id bigserial primary key,
  vertical_id text not null,
  direction_theme text not null,
  supporting_topics jsonb not null default '[]'::jsonb,
  strategic_priority numeric(10,2) not null default 0,
  candidate_actions jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);
