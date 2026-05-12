"""Pi-CEO Board personas — 9-persona deliberation per ceo-board skill."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    role: str
    description: str
    perspective: str  # what they argue from


CANONICAL_PERSONAS = [
    Persona("CEO",
            "Final synthesiser; reads the other 8 and writes the decision memo.",
            "$2B by Jun 2028 — does this bet move us measurably closer?"),
    Persona("Revenue",
            "Customer / acquisition / retention",
            "Will this protect or grow vetted-client ARR?"),
    Persona("Product Strategist",
            "Portfolio fit + moat",
            "Does this deepen our defensibility per exit-thesis benchmarks?"),
    Persona("Technical Architect",
            "Build feasibility + tech debt",
            "Can the autonomous swarm execute this without HITL bottleneck?"),
    Persona("Contrarian",
            "Steel-man the no",
            "What's the failure mode we'd most regret?"),
    Persona("Compounder",
            "Long-horizon leverage",
            "Will this compound or decay over the next 24 months?"),
    Persona("Custom Oracle",
            "Phill's intuition — pattern-match against founder priors",
            "What would Phill say if he saw this without context?"),
    Persona("Market Strategist",
            "ANZ + global macro / competitor landscape",
            "Does the market window favour this now vs Q1 2027?"),
    Persona("Moonshot",
            "Highest-upside variant",
            "What's the 10x version of this bet?"),
]
