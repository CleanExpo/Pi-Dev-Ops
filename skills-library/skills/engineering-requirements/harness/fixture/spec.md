# spec.md — FieldCapture (seeded fixture)

## 1. What this is
A field-capture and reporting tool. Technicians capture readings offline; the server
generates a report that is distributed to insurers.

## 2. Gates
- A report may not be distributed unless its verification checklist is complete.
- Offline capture must survive poor connectivity and retry.
- Tenants must not read each other's reports.

## 3. Done when
- Deploy is repeatable and observable.
- Migrations are applied and recorded.
- Tests gate the classification engine.
