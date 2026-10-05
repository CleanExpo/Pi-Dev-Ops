---
type: regex
pattern: '(planning|product|project)\s+status\s*:\s*(COMPLETE|SHIPPED|DONE)\b'
flags: i
match: not_contains
target: last_message
weight: 3
arm: both
---
