from dataclasses import dataclass, field

@dataclass
class BudgetTracker:
    total_budget: int = 100000
    used: int = 0
    per_tier: dict = field(default_factory=dict)
    
    def record(self, tier, tokens):
        self.used += tokens
        self.per_tier.setdefault(tier, 0)
        self.per_tier[tier] += tokens
    
    def remaining(self): return self.total_budget - self.used
    def pct_used(self): return (self.used / self.total_budget * 100) if self.total_budget else 0
