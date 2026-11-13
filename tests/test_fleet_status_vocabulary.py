"""tests/test_fleet_status_vocabulary.py — the runner's status words and the two screens agree.

The heartbeat reports a machine's state as one word (`mesh/heartbeat.py node_status`).
Two screens turn that word into a colour: the Live page (`dashboard/lib/wall/snapshot.ts`)
and the `/mc` pane plus the `fleet_status` tool (`mods/mission-control/hooks/fleet.ts`).
Neither may import the runner or each other, so each holds its own copy of the words.

The rule both copies follow is an ALLOW-list: only `online` and `working` can be green.
The HELD list only chooses the wording ("held: quota"), never whether to alert. So a word
the runner adds later is not green by default; this test then fails until a screen names it.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEARTBEAT = ROOT / "mesh" / "heartbeat.py"
SCREENS = {
    "snapshot.ts": ROOT / "dashboard" / "lib" / "wall" / "snapshot.ts",
    "fleet.ts": ROOT / "mods" / "mission-control" / "hooks" / "fleet.ts",
}
HEALTHY = {"online", "working"}
# Reported while the runner swaps code; neither healthy nor a hold.
TRANSIENT = {"updating"}
# The runner is not running at all: not a hold it chose. Not healthy, so both screens alert.
DOWN = {"runner-down"}


def _runner_states() -> set[str]:
    """Every literal word node_status() can return, read from its source (docstring excluded)."""
    tree = ast.parse(HEARTBEAT.read_text())
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "node_status")
    doc = fn.body[0].value if fn.body and isinstance(fn.body[0], ast.Expr) else None
    words = {n.value for n in ast.walk(fn)
             if isinstance(n, ast.Constant) and isinstance(n.value, str) and n is not doc}
    words.discard("state")  # the breadcrumb key, not a status
    return words


def _ts_set(path: Path, name: str) -> set[str]:
    m = re.search(rf"export const {name}\s*=\s*new Set\(\[([^\]]*)\]\)", path.read_text())
    assert m, f"{path.relative_to(ROOT)} has no `export const {name} = new Set([...])`"
    return set(re.findall(r"""["']([^"']+)["']""", m.group(1)))


def test_the_runner_vocabulary_was_read():
    states = _runner_states()
    # A positive control: if parsing broke, every later subset test would pass on an empty set.
    assert {"quota", "blocked", "runner-down", "online", "working"} <= states, states


def test_only_online_and_working_are_healthy_on_both_screens():
    for label, path in SCREENS.items():
        assert _ts_set(path, "HEALTHY_STATUSES") == HEALTHY, label


def test_every_word_is_classified():
    # Nothing node_status() can say falls outside the four groups, so a new word fails here first.
    states = _runner_states()
    assert all(" " not in w for w in states), states  # only status words, no prose
    assert DOWN <= states and TRANSIENT <= states, states


def test_every_runner_hold_is_named_held_on_both_screens():
    holds = _runner_states() - HEALTHY - TRANSIENT - DOWN
    for label, path in SCREENS.items():
        held = _ts_set(path, "HELD_STATUSES")
        assert holds <= held, f"{label} does not name {sorted(holds - held)} as held"
        assert not (held & HEALTHY), f"{label} names a healthy word as held"


def test_both_screens_use_the_same_held_words():
    sets = {label: _ts_set(path, "HELD_STATUSES") for label, path in SCREENS.items()}
    assert sets["snapshot.ts"] == sets["fleet.ts"], sets
