# Supabase migrations — conventions

## Row Level Security (RLS) — required on every new table

**Every migration that `CREATE TABLE`s must enable RLS on that table.**

```sql
CREATE TABLE public.my_table (
    id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ...
);

-- REQUIRED: close the auto-exposed PostgREST surface.
ALTER TABLE public.my_table ENABLE ROW LEVEL SECURITY;
```

### Why
Supabase auto-publishes every table in the `public` schema through its PostgREST
API. Without RLS, anyone holding the project URL + **anon key** can read/write
that table directly. `ENABLE ROW LEVEL SECURITY` with no policy = **default deny**
for the `anon`/`authenticated` roles, which shuts that door.

### Why this does not break the backend
The Flask/SQLAlchemy app connects via `DATABASE_URL` as the Supabase **`postgres`
(owner) role**, which **bypasses RLS**. So enabling RLS needs **no policy** for
the backend to keep working. Do **not** add permissive policies just to "make it
work" — the app already works; a policy would only re-open the PostgREST hole.

### When you DO need a policy
Only if a table is meant to be reached directly through PostgREST (anon or a
Supabase-Auth `authenticated` user) — not the case for anything the Flask backend
owns today. If that changes, add explicit `CREATE POLICY` statements scoped as
tightly as possible, in the same migration.

### Checklist for a new-table migration
- [ ] `CREATE TABLE public.<t> (...)`
- [ ] `ALTER TABLE public.<t> ENABLE ROW LEVEL SECURITY;`
- [ ] Indexes / FKs
- [ ] Policies **only** if the table is exposed via PostgREST

> Note: existing tables predate this convention and do **not** yet have RLS
> enabled. This rule is forward-looking; retrofitting the existing tables is a
> separate one-shot migration (not done here).
