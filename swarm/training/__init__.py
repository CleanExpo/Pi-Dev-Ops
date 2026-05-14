"""swarm.training — labelled-corpus assembly toward the Q3 2026 PEFT LoRA experiment.

Per [[research-hf-agent-trains-models-2026-05-14]], the Pi-CEO swarm
generates the richest labelled signal in Phill's stack — preamble_trainer
outputs, pm_scoper specs, intake_router classifications, feature_orchestrator
routing decisions. This package captures those (input, output, metadata)
tuples as JSONL traces ready for HF Datasets upload + downstream training.

Foundation only tonight. The actual fine-tune is deferred to Q3 2026
when the corpus reaches ≥5k labelled examples.
"""
