import yaml
from dataclasses import dataclass
from typing import Optional

MODEL_MAP = {'opus':'claude-opus-4-6','sonnet':'claude-sonnet-4-6','haiku':'claude-haiku-4-5-20251001'}

@dataclass
class TierConfig:
    name: str
    model: str
    role: str = ''
    parent: Optional[str] = None
    max_concurrency: int = 1
    token_budget_pct: int = 0
    fallback_model: Optional[str] = None

def load_config(path):
    with open(path) as f:
        raw = yaml.safe_load(f)
    tiers = []
    for t in raw.get('tiers', []):
        tiers.append(TierConfig(**{k:v for k,v in t.items() if k in TierConfig.__dataclass_fields__}))
    return {
        'total_token_budget': raw.get('total_token_budget', 100000),
        'tiers': tiers,
        'agents': raw.get('agents', {}),
        'qa': raw.get('qa', {}),
    }
