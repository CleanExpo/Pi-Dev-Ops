# Pi-Dev-Ops — Research Intent

## What to Improve

Cycle 24 focus: close the ZTE Section C gaps identified in the RA-675 audit.

- Target ZTE automated score: 90/100 (current: 81/100)
- Priority files: `app/server/sessions.py`, `app/server/pipeline.py`, `app/server/agents/board_meeting.py`
- Explore confidence-calibrated evaluation — sessions with evaluator_confidence <60% warrant a second human review pass before merge
- Explore multi-turn feedback loops where the evaluator's reasoning improves the next generator prompt

## Success Metrics

- ZTE automated score ≥ 90/100 (tracked via `python scripts/zte_v2_score.py`)
- Mean evaluator confidence > 75% across last 10 sessions
- Zero scope violations in last 5 autonomous builds
- MARATHON-4 (RA-588) completes without human intervention

## Strategic Direction

Pi-CEO should be able to run a full 6-hour self-maintenance cycle autonomously.
All blocking issues for MARATHON-4 must be cleared before the next board meeting.
