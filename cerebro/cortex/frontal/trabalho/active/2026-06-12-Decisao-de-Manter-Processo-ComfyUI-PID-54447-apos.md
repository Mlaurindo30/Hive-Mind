---
tags: [decision]
status: active
created: 2026-06-12
updated: 2026-06-12
source: hermes-session
---

# Decisão de Manter Processo ComfyUI (PID 54447) após Investigação de VRAM

O usuário questionou o consumo de 50% (5GB de 12GB) de sua VRAM. A investigação via nvidia-smi confirmou que o processo PID 54447 (ComfyUI) é o principal consumidor (4GB). 

Após deliberação do LLM Council:
1. O consumo é considerado normal/esperado para o uso de modelos de IA.
2. Encerrar o processo foi desencorajado devido ao risco de perda de workflows e latência de recarregamento.
3. Foi recomendado o uso de ferramentas internas do ComfyUI (Unload Models) para gerenciamento de memória em vez de interrupção forçada do processo.
4. Identificou-se que o usuário possui margem de sobra (7GB livres).

Resultado: O processo foi mantido e o usuário orientado sobre gerenciamento de cache de modelos.
