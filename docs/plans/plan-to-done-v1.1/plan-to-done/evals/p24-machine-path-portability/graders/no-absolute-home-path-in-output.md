---
type: regex
pattern: '/(Users|home)/[A-Za-z0-9._-]+/'
match: not_contains
target: last_message
weight: 2
arm: both
---
