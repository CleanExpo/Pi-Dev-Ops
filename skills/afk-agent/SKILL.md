---
name: afk-agent
description: Run agents unattended with stop guards and notifications.
---

# AFK Agent

## The AFK Contract
1. Bounded runtime (max N minutes)
2. Bounded cost (max N tokens)
3. No silent failure
4. No premature exit (stop guards)
5. Notification on completion

## Stop Guards
Intercept exit attempts. Verify completion criteria before allowing stop.
