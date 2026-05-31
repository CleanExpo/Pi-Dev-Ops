-- SYN-508: Featured in Synthex programme
alter table clients
  add column if not exists featured_programme_status text
    not null default 'not_applied'
    check (featured_programme_status in ('not_applied', 'applied', 'in_production', 'published'));
