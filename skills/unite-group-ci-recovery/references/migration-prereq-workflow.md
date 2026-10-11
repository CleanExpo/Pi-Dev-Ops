> Moved from SKILL.md. Read when a migration references tables that may not exist on prod.

## 5 — Migration prereq detection workflow

Before opening a PR that adds a Prisma migration:

```bash
# 1. List existing tables on prod for any new schema you reference
supabase db query --linked "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'marketing_agency_%' ORDER BY table_name;"

# 2. Cross-check vs prisma schema declarations
grep -E "^model MarketingAgency" prisma/schema.prisma | wc -l

# 3. If counts don't match → there's a latent gap; write a prereq migration first
```
