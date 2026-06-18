---
type: decision
project: Hive-Mind
topic: error_handling
integrity_hash: e54dc37a8db0e2c3
last_updated: 2026-06-17 15:13
source: hive-dreamer
aliases:
- ideogram-4-shape-mismatch
sectors:
- ai-infra
- dev-tools
---
# Fix Ideogram 4 Shape Mismatch

Identified shape mismatch in Ideogram 4 model (53248 vs 2560). Patched comfy/model_detection.py to dynamically detect llm_features_dim and comfy/supported_models_base.py to prevent default values from overwriting detected ones.

## Evidência (Groundedness)
> Identified shape mismatch in Ideogram 4 model (53248 vs 2560). Patched `comfy/model_detection.py` to dynamically detect `llm_features_dim` and `comfy/supported_models_base.py` to prevent default values from overwriting detected ones.

## Sinapses
- projeto:: [[_Hive-Mind]]
- tópico:: [[_error_handling]]

#consolidated #error_handling
