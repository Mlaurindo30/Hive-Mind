# Model Gateway Unification — Unificar Providers Legados no Gateway Canônico

## Goal

Substituir o estado atual em que `ModelGateway` coexiste como camada opt-in ao lado do caminho legado de `core/llm_client.py` por um desenho em que o `ModelGateway` é a **única API de execução de modelos** do Hive-Mind. O caminho legado deixa de ser fluxo paralelo e vira bypass emergencial controlado. As fontes de configuração legadas (`HIVE_{ROLE}_PROVIDER/MODEL/FALLBACK*` no `.env` e `PROVIDERS_CONFIG` em `core/auth.py`) continuam sendo fonte primária de credenciais e roteamento por role; `config/model-gateway.yaml` vira override opcional de capabilities, custo, prioridade e adapter hints — nunca segunda fonte obrigatória de provider/model.

Esta spec substitui a decisão "incremental e aditivo, opt-in por padrão" registrada em `specs/model-gateway.md` Goal §1 e §14.

## Requirements

### R1 — `core/model_registry.py` lê configuração legada

1. MUST expor `ModelRegistry.from_legacy_roles(roles: list[str] | None = None) -> "ModelRegistry"` que itera `get_role_config(role)` para cada role solicitado e monta um `ModelProfile` por par `(provider, model)` na ordem `primary → fallback → fallback2`.
2. MUST expor `ModelRegistry.from_combined_config() -> "ModelRegistry"` que compõe, em ordem: `PROVIDERS_CONFIG` (base de `base_url`/`env_var`/`auth_type`) + roles legados do `.env` via `get_role_config` + overrides opcionais de `config/model-gateway.yaml`.
3. MUST expor `ModelRegistry.build_profile_from_provider(role, provider, model, level="primary") -> ModelProfile` que consulta `PROVIDERS_CONFIG[provider]` para preencher `base_url`, `env_var` e `auth_type`, e que lança `ModelRegistryError` se o provider não estiver mapeado.
4. MUST retornar `ModelProfile` com, no mínimo: `id`, `provider`, `model`, `role`, `level` ∈ `{primary, fallback, fallback2}`, `base_url`, `auth_type`, `adapter_hint` (resolvido pela regra de mapeamento em R2), `priority` (default 0), `enabled` (default True), e `capabilities` derivado do adapter (chat, structured_output, embeddings, vision).
5. MUST aplicar o override do YAML apenas para os campos `capabilities`, `adapter_hint`, `priority`, `cost_mode`, `context_window`, `max_output_tokens`, `roles`. MUST NOT exigir duplicação de `provider` ou `model` no YAML para que um role seja reconhecível.
6. MUST expor método `validate() -> list[dict]` que retorna diagnóstico: profile sem adapter mapeado, provider fora de `PROVIDERS_CONFIG`, role sem nenhum par `(provider, model)` configurado. Lista vazia significa registry válido.

### R2 — Mapeamento de providers legados para adapters

1. MUST mapear todos os providers de `PROVIDERS_CONFIG` (atualmente: `google`, `antigravity`, `gemini-cli`, `omniroute`, `openai`, `huggingface`, `qwen`, `deepseek`, `nvidia`, `anthropic`, `openrouter`, `ollama-cloud`, `lmstudio`, `ollama`) para uma família de adapter. O mapeamento inicial obrigatório é:
   - `openai`, `openrouter`, `deepseek`, `nvidia` → `openai_compatible`
   - `qwen` → `openai_compatible` se DashScope expõe `/compatible-mode/v1`; caso contrário `litellm`
   - `omniroute` → `openai_compatible` se expõe `/v1`; caso contrário `litellm`
   - `huggingface` → `litellm` ou dedicated, conforme endpoint real
   - `google`, `gemini` → `litellm` inicialmente; dedicated Gemini só se necessário
   - `gemini-cli`, `antigravity` → dedicated wrapper / legacy bridge controlado
   - `ollama` → `openai_compatible` usando `/v1` quando disponível
   - `ollama-cloud` → `openai_compatible` se API compatível; senão `litellm`
   - `lmstudio` → `lmstudio` adapter (já existe)
   - `llamacpp`, `vllm`, `sglang` → adapters dedicados já existentes
2. MUST permitir que adapters novos sejam registrados sem alterar `ModelRegistry`.
3. MUST emitir `unsupported_explicit` (com `provider`, `reason`) para qualquer provider que não tenha adapter resolvido, em vez de sumir silenciosamente. `unsupported_explicit` MUST aparecer em `validate()` e MUST aparecer em logs de inicialização do gateway.
4. MUST ser extensível: o `mapping` entre `provider` e `adapter_hint` vive em um único local (constante ou tabela em `core/model_registry.py`) e é lido por `build_profile_from_provider`.

### R3 — `core/model_gateway.py` carrega registry combinado por padrão

1. `ModelGateway.from_config()` MUST ser deprecado em favor de `ModelGateway.from_combined_config()`.
2. `ModelGateway.from_combined_config()` MUST chamar `ModelRegistry.from_combined_config()` e MUST expor `chat()`, `structured()` e `embeddings()` que resolvem o `ModelProfile` por role respeitando a ordem `primary → fallback → fallback2`.
3. `ModelGateway.from_combined_config()` MUST registrar um `ModelResponse` com `fallback_used=True` e `fallback_chain` populado sempre que pelo menos um par fallback foi tentado.
4. MUST rejeitar `MODEL_GATEWAY_MODE` desconhecido com `ModelGatewayError` e mensagem clara, sem cair em default silencioso.
5. MUST falhar estruturado (não exceção crua) quando todos os pares `primary → fallback → fallback2` falharem; resposta MUST incluir `ok=False`, `error`, `chain=[(provider, model, error), ...]`, e MUST ser registrada em telemetria como `gateway_attempted=true, gateway_failed=true`.

### R4 — `core/llm_client.py` vira wrapper do gateway

1. `call_llm_with_fallback(...)` MUST delegar ao `ModelGateway.from_combined_config().structured(...)` por padrão, sem `MODEL_GATEWAY_ENABLED=true` ou qualquer opt-in.
2. MUST manter compatibilidade de assinatura e contrato de retorno com todos os chamadores atuais (incluindo `LLMValidationError` e `LLMChainFailure` no caminho de erro final).
3. MUST checar `HIVE_FORCE_LEGACY_LLM=true` (case-insensitive) no início. Quando True, MUST emitir warning único por processo `HIVE_FORCE_LEGACY_LLM=true is an emergency bypass; legacy path will be used` em `stderr` e MUST chamar `_legacy_call_llm_with_fallback`.
4. MUST emitir warning único por processo quando `MODEL_GATEWAY_MODE=off` (deprecated) for lido, indicando que a chave foi renomeada para `HIVE_FORCE_LEGACY_LLM`.
5. MUST proibir fail-open silencioso: se o gateway for invocado e falhar em `MODE=auto`, MUST emitir warning estruturado com `gateway_attempted=true, gateway_failed=true, legacy_fallback_used=true, reason=<...>` e MUST delegar ao legado, mas registrando telemetria.
6. MUST delegar a `_legacy_call_llm_with_fallback` (renomeação do corpo atual) sempre que `image_path` for passado, emitindo warning único por processo `legacy_vision_bridge_used=true; image_path routed through legacy llm_client`.
7. `MODEL_GATEWAY_ENABLED` MUST ser lido apenas para compatibilidade: `true → MODE=on`, `false → MODE=off` com warning de deprecation. Ausente ou sem efeito → `MODE=auto`.

### R5 — `MODEL_GATEWAY_MODE` é a chave canônica

1. Valores válidos: `auto` (default), `on`, `off`. Outros MUST rejeitar com erro.
2. `auto`: usa gateway via registry combinado; se o registry não validar (lista de `validate()` não-vazia), cai pro legado com warning explícito por role. MUST never fail-open silencioso.
3. `on`: gateway obrigatório; se falhar, retorna `ModelResponse(ok=False, error=...)` estruturado; MUST NEVER cair pro legado.
4. `off`: gateway desabilitado para diagnóstico; MUST emitir warning de deprecation uma vez por processo. NÃO é modo operacional recomendado.
5. `HIVE_FORCE_LEGACY_LLM=true`: bypass emergencial, prevalece sobre `MODEL_GATEWAY_MODE`. MUST emitir warning de bypass.

### R6 — Política de retry/fallback é preservada

1. erro de validação/schema: retry no mesmo modelo, até `max_retries` configurado; MUST NEVER disparar fallback.
2. erro transitório/timeout/5xx: backoff exponencial (cap em 8s, igual ao legado) com `max_retries`; após esgotar, fallback para próximo par.
3. erro de auth/saldo/401/403: fallback direto, sem retry no mesmo modelo.
4. erro 429 (rate limit): backoff; após exceder limite, fallback.
5. provider sem capability exigida: pular provider, tentar próximo fallback compatível; MUST registrar `skipped_due_to_capability=<cap>` em telemetria.
6. todos os pares falharem: `ok=False` com cadeia de erros preservada; MUST NEVER retornar sucesso silencioso.

### R7 — `config/model-gateway.yaml` vira override opcional

1. MUST aceitar bloco `providers:` para registrar `adapter_hint`, `capabilities` e `cost_mode` por provider.
2. MUST aceitar bloco `roles:` para registrar overrides opcionais: `require`, `prefer`, `priority`, `context_window`, `max_output_tokens`, `cost_mode`.
3. MUST NEVER exigir que `roles.<name>.provider` e `roles.<name>.model` sejam preenchidos. Se forem, MUST emitir warning de duplicação `provider/model in YAML overlaps with .env HIVE_*; YAML value ignored unless role_override=true`.
4. O `config/model-gateway.env.example` MUST ser atualizado para refletir a nova divisão (exemplo válido no DoD §D2).

### R8 — Vision é ponte legada controlada

1. Quando `image_path` for passado a `call_llm_with_fallback`, MUST delegar ao `_legacy_call_llm_with_fallback` e MUST emitir warning único por processo com `legacy_vision_bridge_used=true`.
2. O gateway MUST expor `capabilities.vision: bool` em `ModelProfile` para preparar migração futura; o adapter que ainda não implementa vision MUST retornar `False` em `vision` e o seletor MUST pular para providers com `vision=True` quando o chamador exigir multimodal.
3. Quando o caller exigir vision e nenhum provider tiver `vision=True`, MUST retornar `ModelResponse(ok=False, error="no_vision_capable_provider")`.

### R9 — `setup-brain.py` deixa claro que alimenta o gateway

1. `provider_menu` e `role_var` MUST escrever as mesmas env vars `HIVE_{ROLE}_{PROVIDER|MODEL|FALLBACK*}` que já escrevem hoje; MUST NOT adicionar nova fonte de verdade.
2. `save_env` MUST continuar idempotente e MUST registrar telemetria `setup_brain_role_configured={role, primary, fallback, fallback2}`.
3. Após `save_env`, `setup-brain.py` MUST chamar `ModelRegistry.from_combined_config().validate()` e MUST exibir ao usuário, em stdout, a tabela resultante: para cada role configurado, mostrar `primary`, `fallback`, `fallback2` e o adapter resolvido. Se algum provider ficar como `unsupported_explicit`, MUST mostrar a razão.

### R10 — Telemetria canônica via `core/model_telemetry.py`

1. Todo caminho que executa LLM MUST registrar: `gateway_attempted`, `gateway_failed`, `legacy_fallback_used`, `role`, `provider`, `model`, `level` (`primary|fallback|fallback2`), `latency_ms`, `error_class` (`auth|transient|validation|rate_limit|unknown`), `reason`.
2. `setup-brain.py` (R9) MUST registrar `setup_brain_role_configured`.
3. Telemetria MUST nunca logar credenciais. Segredos MUST ser redigidos via `core/redactor.py` antes de qualquer escrita.

## Out of Scope

- Adicionar adapter novo de vision nativo para provedores visuais (deixado para R8 futuro — esta spec mantém a ponte legada).
- Eliminar de vez `core/llm_client.py` (deixado como emergency bypass explícito; spec define a transição, não a remoção final).
- Migrar `config/model-gateway.yaml` para outro formato (TOML, JSON, etc.). YAML permanece.
- Reorganizar `PROVIDERS_CONFIG` (mantém estrutura atual).
- Adicionar circuit breaker, budget de tokens ou outras evoluções de política de retry (R6 preserva a política atual; evoluções ficam para spec futura).
- Suporte a function calling / tools além de `structured_output` (já existe; nada muda aqui).
- Mudar contrato dos chamadores que hoje usam `call_llm_with_fallback` (assinatura e exceções preservadas).
- Smoke E2E real com 15 provedores e credenciais vivas (depende de ambiente externo; substituído por unit + contract tests + 1 backend real OpenAI-compat, ver DoD §D3).

## Edge Cases & Error Handling

- `MODEL_GATEWAY_MODE` com valor inválido → `ModelGatewayError` na inicialização; `call_llm_with_fallback` MUST propagar e `validate()` MUST listar `invalid_gateway_mode`.
- Role sem `HIVE_{ROLE}_PROVIDER` configurado → `RuntimeError` com mensagem clara mencionando a env var esperada (comportamento atual preservado).
- Provider em `HIVE_*_PROVIDER` que não existe em `PROVIDERS_CONFIG` → profile com `unsupported_explicit: {provider, reason: "not_in_PROVIDERS_CONFIG"}`; em `MODE=on` MUST falhar; em `MODE=auto` MUST pular e tentar próximo par com warning.
- Provider com `adapter_hint` mapeado mas adapter não registrado em runtime → `ModelRegistryError` em `validate()`; em `MODE=auto` MUST pular e tentar próximo par.
- `image_path` enviado a um role que o gateway marcou como não-vision → MUST delegar ao legado com warning `legacy_vision_bridge_used=true` (R8 §1).
- `HIVE_FORCE_LEGACY_LLM=true` E `image_path=None` → legado é chamado, warning de bypass emitido, sem tentativa de gateway.
- `HIVE_FORCE_LEGACY_LLM=true` E `MODEL_GATEWAY_MODE=on` → `HIVE_FORCE_LEGACY_LLM` prevalece, com warning adicional `HIVE_FORCE_LEGACY_LLM overrides MODEL_GATEWAY_MODE=on`.
- Falha de credencial (auth) no `primary` → fallback direto, sem retry, telemetria `error_class=auth`.
- Falha de schema Pydantic no `primary` → retry no mesmo modelo até `max_retries`; MUST NEVER fazer fallback (R6 §1).
- Todos os pares falham → `ModelResponse(ok=False)` estruturado; chamador (`call_llm_with_fallback`) traduz para `LLMChainFailure` preservando `primary_exc` e `fallback_exc` (contrato atual preservado).
- `setup-brain.py` invocado sem `.env` → cria `.env` com `HIVE_DREAMER_PROVIDER` default; em `validate()` exibe ao usuário quais providers não foram resolvidos.
- `ModelRegistry.from_combined_config()` rodando em ambiente sem `config/model-gateway.yaml` → MUST funcionar apenas com `.env` + `PROVIDERS_CONFIG` (YAML é opcional, não obrigatório).

## Definition of Done

### D1 — Suíte pytest de equivalência legado↔gateway (R1, R3, R4)

`pytest tests/model_gateway/test_legacy_equivalence.py` MUST passar com, no mínimo:
- `test_every_role_in_PROVIDERS_CONFIG_resolves` — para cada provider em `PROVIDERS_CONFIG`, `build_profile_from_provider` retorna um `ModelProfile` (com adapter ou `unsupported_explicit`).
- `test_combined_config_order_primary_fallback_fallback2` — `from_combined_config` retorna profiles na ordem correta.
- `test_yaml_does_not_require_provider_model` — registry carrega normalmente com YAML ausente ou sem `roles.<name>.provider`.
- `test_force_legacy_overrides_gateway` — `HIVE_FORCE_LEGACY_LLM=true` faz `call_llm_with_fallback` chamar o legado.
- `test_image_path_uses_legacy_bridge` — `image_path=...` faz `call_llm_with_fallback` chamar o legado mesmo com gateway ativo.
- `test_no_silent_fail_open` — monkeypatch do gateway para levantar exceção; `call_llm_with_fallback` MUST emitir warning `gateway_failed=true, legacy_fallback_used=true` e MUST registrar telemetria.
- `test_gateway_mode_on_never_falls_back` — `MODEL_GATEWAY_MODE=on` com gateway falhando MUST retornar `ModelResponse(ok=False)`, MUST NEVER chamar legado.
- `test_unsupported_explicit_listed` — provider desconhecido em `HIVE_*_PROVIDER` aparece em `validate()` com `unsupported_explicit`.

### D2 — Cobertura de testes de `ModelRegistry.from_combined_config()`

`pytest --cov=core.model_registry --cov-report=term` MUST reportar ≥ 80% de cobertura na função `from_combined_config` e em `build_profile_from_provider`.

### D3 — Caminho legado só via bypass explícito (R4, R5)

- `rg -n "except.*legacy|fail.*open|legacy.*silent|MODEL_GATEWAY_ENABLED" core tests scripts docs` MUST retornar apenas ocorrências justificadas como `deprecated`, `emergency bypass` ou pertencentes a testes.
- `_legacy_call_llm_with_fallback` MUST existir como função nomeada (não inline) em `core/llm_client.py`.
- `HIVE_FORCE_LEGACY_LLM` MUST aparecer documentado em `docs/14-model-gateway.md` como bypass emergencial.
- `MODEL_GATEWAY_ENABLED` MUST aparecer em `core/model_gateway.py` apenas dentro do shim de compatibilidade e em `docs/14-model-gateway.md` na seção de migração.
- `setup-brain.py` MUST chamar `ModelRegistry.from_combined_config().validate()` ao final e MUST imprimir a tabela de roles configurados para o usuário.

### D4 — Backend real OpenAI-compat (não skipped)

A suíte de testes MUST incluir pelo menos um teste que exercita um backend OpenAI-compat real (recomendado: `lmstudio` ou `ollama` em ambiente local) com `MODEL_GATEWAY_MODE=on`, asserting:
- `ModelResponse.ok is True`
- `fallback_used is False`
- `provider` e `model` batem com o role configurado.

Se o backend não estiver disponível, o teste MUST ser pulado com `pytest.skip(<reason>)` e a razão MUST ser registrada na saída do CI.

### D5 — Documentação alinhada

- `docs/14-model-gateway.md` MUST descrever: a) `MODEL_GATEWAY_MODE` (auto/on/off) como chave canônica, b) `HIVE_FORCE_LEGACY_LLM` como bypass emergencial, c) `MODEL_GATEWAY_ENABLED` como deprecated, d) o mapeamento de providers em R2, e) exemplo de uso de `setup-brain` mostrando a tabela de roles configurados.
- `config/model-gateway.env.example` MUST ser atualizado para refletir a divisão YAML=override / `.env`=fonte de role.
- `config/model-gateway.yaml` MUST ser auditado: nenhum `roles.<name>.provider` ou `roles.<name>.model` obrigatório. Se existirem, MUST ser marcados como override explícito (`role_override: true`) ou removidos.

### D6 — Verificação manual de fluxo

Comando único executável que demonstra o fluxo fim-a-fim:

```bash
python -c "
from core.model_registry import ModelRegistry
from core.model_gateway import ModelGateway
import os
os.environ.pop('HIVE_FORCE_LEGACY_LLM', None)
reg = ModelRegistry.from_combined_config()
print('validate:', reg.validate())
gw = ModelGateway.from_combined_config()
print('profiles:', [(p.id, p.provider, p.model, p.level) for p in reg.list_models()])
"
```

MUST retornar:
- `validate: []` (lista vazia) para uma configuração limpa de `.env`, OU
- lista de warnings contendo apenas `unsupported_explicit` para providers intencionalmente não suportados.
