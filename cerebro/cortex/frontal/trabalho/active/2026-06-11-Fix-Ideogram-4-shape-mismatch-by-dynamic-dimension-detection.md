---
tags: [decision]
status: active
created: 2026-06-11
updated: 2026-06-11
source: hermes-session
---

# Fix Ideogram 4 shape mismatch by dynamic dimension detection

Identified shape mismatch in Ideogram 4 model (53248 vs 2560). Patched `comfy/model_detection.py` to dynamically detect `llm_features_dim` and `comfy/supported_models_base.py` to prevent default values from overwriting detected ones.
