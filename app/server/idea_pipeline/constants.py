"""UNI-2633 idea pipeline constants — North Star, verdicts, directives."""

from __future__ import annotations

NORTH_STAR = (
    "empower small business owners to grow, self-paced, all learning styles"
)

VERDICTS = frozenset({"PROMOTE", "BACKLOG", "PARK", "KILL"})
SOURCES = frozenset({"phill", "margot"})

# Founder directives the Board can name. Each row is (id, label, cue words).
DIRECTIVES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "small-business-growth",
        "Help small business owners grow",
        ("grow", "growth", "sales", "customer", "revenue", "owner", "shop", "cafe"),
    ),
    (
        "self-paced-learning",
        "Self-paced learning, not a live class",
        ("learn", "course", "lesson", "pace", "teach", "training", "self-paced"),
    ),
    (
        "all-learning-styles",
        "Reach every learning style",
        ("video", "audio", "read", "practise", "practice", "visual", "style"),
    ),
    (
        "mission-control",
        "Founder daily operating system",
        ("mission control", "daily", "board", "packet", "idea pipeline"),
    ),
)

NORTH_STAR_TERMS = frozenset(
    {
        "empower",
        "small",
        "business",
        "owner",
        "owners",
        "grow",
        "growth",
        "self-paced",
        "learning",
        "style",
        "styles",
        "course",
        "teach",
        "lesson",
        "shop",
        "cafe",
        "founder",
        "sales",
        "customer",
        "video",
        "audio",
        "practise",
        "practice",
        "training",
    }
)

HIGH_EFFORT = frozenset(
    {"rebuild", "platform", "migrate", "rewrite", "marketplace", "rewrite"}
)
LOW_EFFORT = frozenset(
    {"note", "reminder", "label", "copy", "tweak", "nudge", "prompt"}
)
ACTION_VERBS = frozenset(
    {
        "add",
        "build",
        "create",
        "teach",
        "help",
        "make",
        "launch",
        "film",
        "write",
        "send",
        "show",
        "give",
        "offer",
    }
)

INTAKE_SKIP_PHRASES = (
    "drop one to three",
    "no formatting",
    "start a line with",
    "idea template",
    "phill writes",
    "margot appends",
)

INTAKE_FILENAME = "IDEAS.md"
STORE_DIRNAME = "idea-pipeline"
