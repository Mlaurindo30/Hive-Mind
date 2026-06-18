---
type: decision
project: Hive-Mind
topic: infrastructure
integrity_hash: 6f6aee5476ea795c
last_updated: 2026-06-17 15:13
source: hive-dreamer
aliases:
- dec-comfyui-keep-process
sectors:
- ai-infra
- infra
---
# Keep ComfyUI Process and Manage VRAM

After investigation, the ComfyUI process (PID 54447) consuming 4GB of 12GB VRAM is considered normal. Decision to keep the process running, not kill it, and use ComfyUI's Unload Models tool for memory management. User has 7GB free margin.

## Evidência (Groundedness)
> O usuário questionou o consumo de 50% (5GB de 12GB) de sua VRAM. A investigação via nvidia-smi confirmou que o processo PID 54447 (ComfyUI) é o principal consumidor (4GB). Após deliberação do LLM Council: 1. O consumo é considerado normal/esperado para o uso de modelos de IA. 2. Encerrar o processo foi desencorajado devido ao risco de perda de workflows e latência de recarregamento. 3. Foi recomendado o uso de ferramentas internas do ComfyUI (Unload Models) para gerenciamento de memória em vez de interrupção forçada do processo. 4. Identificou-se que o usuário possui margem de sobra (7GB livres). Resultado: O processo foi mantido e o usuário orientado sobre gerenciamento de cache de modelos.

## Sinapses
- projeto:: [[_Hive-Mind]]
- tópico:: [[_infrastructure]]

#consolidated #infrastructure
