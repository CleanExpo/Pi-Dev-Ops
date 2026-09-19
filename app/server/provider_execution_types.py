"""Evidence returned by one observed model execution."""
from dataclasses import dataclass

@dataclass
class ProviderExecution:
    """Observed execution; absent model or cost evidence stays unknown."""
    rc: int
    text: str
    cost_usd: float | None
    error: str | None
    provenance: dict

    def as_tuple(self):
        return self.rc, self.text, self.cost_usd, self.error
