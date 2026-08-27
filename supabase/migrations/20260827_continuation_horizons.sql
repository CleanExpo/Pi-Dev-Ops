create table if not exists public.continuation_horizons (
  key text primary key,
  state jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.continuation_horizons enable row level security;

revoke all on table public.continuation_horizons from anon, authenticated;

create or replace function public.set_continuation_horizons_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

revoke all on function public.set_continuation_horizons_updated_at() from public;

drop trigger if exists continuation_horizons_set_updated_at
on public.continuation_horizons;

create trigger continuation_horizons_set_updated_at
before update on public.continuation_horizons
for each row execute function public.set_continuation_horizons_updated_at();
