# Segurança — Segredos, PII, Assinatura e Validação

> **Hive-Mind v3.10.1** — Normativa de segurança do projeto.
> Fontes canônicas: [`04-infrastructure.md`](04-infrastructure.md) §7 (Security), [`arquitetura.md`](arquitetura.md) §19 (HM-12: visibility, Ed25519, redaction), §30 (workspace), ADR-009/015/016; código: `core/redactor.py`, `core/signing.py`, `core/model_telemetry.py`, `core/model_gateway.py`, `scripts/services/sinapse-api.py` (`encrypt_and_vault`, `verify_api_key`), `core/auth.py` (`PROVIDERS_CONFIG`).

---

## 1. Princípios

1. **Fail-closed.** A REST API não inicia sem `HIVE_MIND_API_KEY`.
2. **Segredos só no `.env`.** Nunca em código, nunca no vault, nunca em docs. `.gitignore` cobre `.env` e `*.db`.
3. **Comparação em tempo constante.** Tokens comparados com `hmac.compare_digest`, nunca `==`.
4. **Vault de segredos.** Segredos detectados em conteúdo são criptografados com **Fernet** e substituídos por placeholder.
5. **Escrita atômica.** `os.replace()` impede corrupção por falha parcial.

---

## 2. Segredos — nunca em código, vault ou docs

**Regra absoluta:** segredos não podem existir em código, no `cerebro/`, nem na documentação. O único lugar autorizado é o `.env` na raiz (não commitado).

Quando um segredo é **detectado no conteúdo** (regex de API key, `sk-proj-*`, etc.), o fluxo é:

1. **Criptografia field-level** (Fernet) na tabela `vault` do UMC.
2. Substituição do valor por referência no conteúdo final (`[VAULT_SECURE:<id>]` / `[SECRET:uuid]`).
3. Recuperação só via endpoint autenticado `GET /api/v1/vault/{secret_id}` (rate limit 10/min), com validação de formato (`vault-[a-f0-9]{8}`).

Implementação de detecção+cofre: `scripts/services/sinapse-api.py:encrypt_and_vault()` + `execute_insert(conn, "vault", ...)`. O fluxo de escrita (`sinapse_save_decision`/`learning`) passa título e conteúdo por `encrypt_and_vault` e retorna `status: "hardened"` (com contagem) ou `"clean"`.

> **Não documente segredos reais.** Este documento descreve **nomes** de variáveis e **como** protegê-los, nunca valores.

---

## 3. Chaves e tokens

### 3.1 Chaves da infraestrutura

| Chave | Uso | Falha-closed / nota |
|---|---|---|
| `HIVE_MIND_API_KEY` | Bearer token da REST API `:37702` (obrigatória) | API **não inicia** sem ela |
| `SINAPSE_DRY_RUN` | `1` = sem efeitos colaterais | proteção de ambiente |
| `HIVE_ALLOW_DEFERRED_MIGRATIONS` | bypass de migração estrutural | `0` (fail-closed); `1` **só** para diagnóstico de DB legado, com log visível e **sem** marcar instalação saudável |

### 3.2 Chaves de provedor LLM

Fonte: `core/auth.py` `PROVIDERS_CONFIG` + [`04-infrastructure.md`](04-infrastructure.md) §2.4.

| Variável | Provedor |
|---|---|
| `GOOGLE_API_KEY` | Google AI Studio (Gemini) |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth Device Flow (**⚠️ rotacionar se comprometida**) |
| `OPENAI_API_KEY` | OpenAI / OpenRouter-compatible |
| `ANTHROPIC_API_KEY` | Anthropic |
| `DEEPSEEK_API_KEY` | DeepSeek |
| `HF_TOKEN` | Hugging Face Inference |
| `DASHSCOPE_API_KEY` | Alibaba Qwen (DashScope) |
| `NVIDIA_API_KEY` | NVIDIA NIM |
| `OPENROUTER_API_KEY` | OpenRouter |
| `OLLAMA_API_KEY` | `ollama-cloud` (provider remoto; Ollama local não exige chave) |
| `LITELLM_API_KEY` | LiteLLM proxy (modo HTTP) |

> **Regra de não-duplicação:** chaves de API são resolvidas **uma vez por provedor** via `PROVIDERS_CONFIG` pelo nome do provider — nunca duplicadas por papel/role (ADR-009). No Model Gateway, a chave é resolvida em tempo de chamada via `ModelProfile.api_key_env` (`profile.api_key()`), nunca armazenada no objeto de perfil, nunca logada.

### 3.3 Tokens de bot e credenciais de identidade (Bot/Entra)

Princípio idêntico ao das chaves de provedor: qualquer **token de bot** (ex.: bot de Telegram/outros) e qualquer **credencial de identidade Microsoft Entra ID / Azure AD** (ex.: `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`, client secrets de app registration) são **segredos**: vivem exclusivamente no `.env`, nunca hardcoded, nunca no vault, nunca em docs, nunca em `components.lock.json`.

- Se uma credencial dessas for comprometida, **rotacionar imediatamente** e registrar o incidente (ver [`incidentes.md`](incidentes.md)).
- O padrão de leitura é sempre `_env(...)`/`os.environ` — nunca string literal no código (ex.: `_env("GOOGLE_OAUTH_CLIENT_SECRET")`).

---

## 4. Redação de PII — `core/redactor.py`

Redação **irreversível** aplicada ao `content` e `label` de um neurônio **antes do export federado**. **Neurônios locais nunca são modificados** — `redact_neuron` faz deep-copy e só processa `content`/`label`.

| Função | O que faz |
|---|---|
| `redact_for_export(text)` | Aplica todas as regras em sequência; retorna texto limpo |
| `redact_neuron(neuron)` | Deep-copy; redige `content` e `label`; demais campos passam inalterados |

### 4.1 Categorias de regra (ordem importa — específica primeiro)

A ordem é proposital: regras específicas antes das genéricas para que uma regra ampla não engula um match específico.

| # | Categoria | Placeholder |
|---|---|---|
| 1 | API tokens (`sk-*`, `GOCSPX-*`, `ghp_*`, JWTs `eyJ...`, `Bearer ...`) | `[REDACTED:token]` |
| 1a | AWS access keys (`AKIA`/`ASIA` + 16) — **antes** de telefone | `[REDACTED:aws-key]` |
| 1b | Atribuição AWS em variável (`aws_access_key_id=`/`aws_secret_access_key=`) | `...[REDACTED:aws-key]` |
| 1c | Segredo genérico `key=value`/`key: value` (`api_key`, `token`, `secret`, `client_secret`, ...) — preserva chave e separador, mascara só o valor | `...[REDACTED:token]` |
| 2 | Emails | `[REDACTED:email]` |
| 3 | IPv4 | `[REDACTED:ip]` |
| 4 | IPv6 | `[REDACTED:ip]` |
| 5 | Caminhos absolutos (`/home/`, `/root/`, `/Users/`, `/var/`) | `[REDACTED:path]` |
| 6 | Bloco de chave privada SSH/PEM (multilinha) | `[REDACTED:key]` |
| 7 | CPF / CNPJ (antes de telefone, para evitar overlap de dígitos) | `[REDACTED:cpf]` |
| 8 | Telefone (padrão amplo — roda por último) | `[REDACTED:phone]` |

> `redact_for_export` também é reutilizado na telemetria do Model Gateway para redigir `endpoint`, `error_type`, `reason` e `unsupported_reason` antes de qualquer escrita — nenhum segredo alcança o stream de telemetria (ver [`modelos-ia.md`](modelos-ia.md) § "Avoiding secret leakage" e [`observabilidade.md`](observabilidade.md) §4.4).

---

## 5. Assinatura Ed25519 — `core/signing.py`

Integridade e autenticidade no **export federado** (HM-12). Chaves PEM em `config/keys/` (deve ser gitignorado); chave privada criada com `chmod 0600`.

| Função | O que faz |
|---|---|
| `generate_keypair(name="default")` | Gera par Ed25519; persiste `{name}_privkey.pem` / `{name}_pubkey.pem`; retorna `{name, fingerprint, pubkey_path}` |
| `load_private_key(name)` / `load_public_key(name)` | Carrega PEM do disco |
| `sign_neuron(neuron, key_name)` | Retorna cópia com `_signature` (base64 Ed25519) e `_pubkey_fingerprint` (SHA-256 hex do DER da chave pública) |
| `verify_neuron(neuron, pubkey)` | Verifica assinatura; `True`/`False`; **nunca levanta** em assinatura inválida |
| `fingerprint(pubkey)` | SHA-256 hex do DER da chave pública |

**Payload canônico determinístico:** `_canonical_bytes` **exclui** campos voláteis (`created_at`, `updated_at`, `indexed_at`) e campos de assinatura (`_signature`, `_pubkey_fingerprint`) para garantir determinismo entre nós.

**Contrato de federação** (ver [`arquitetura.md`](arquitetura.md) §30.3): export só de `visibility IN (shared, public)`, sempre `redact` (default `true`) e `sign` opcional (default `false`); import **verifica assinatura** e preserva proveniência (`origin_instance`, `origin_signature`); **nunca** importar cross-instance raw sem redação, **nunca** sobrescrever local sem `invalid_at`.

---

## 6. Classificação de dados

| Dado | Classificação | Tratamento |
|---|---|---|
| **Neurônios** (`neurons`) | conteúdo do cérebro | `visibility`: `private` (nunca exportado) / `shared` (pares confiáveis) / `public` (sem restrição). Export filtra `IN ('shared','public')`. |
| **Observações** (`observations`) | evidência temporal | `archived`: `0` pendente / `1` consolidado / `2` quarentena. `source_id` (`claude-mem:<table>:<id>`) preserva rastreabilidade; `neuron_id` liga à promoção. |
| **Identidade** | fronteira de isolamento | `workspace_id` em todas as tabelas críticas (default `'default'`). Vazamento cross-workspace é **bug de segurança** (ADR-015), não de ranking. Milvus usa `partition_key=workspace_id`. |
| **Segredos** (`vault`) | altíssima | Fernet, placeholder `[VAULT_SECURE:<id>]`, recuperação autenticada. |
| **Proveniência federada** | identidade de origem | `origin_instance` + `origin_signature` preservados no import. |
| **Telemetria** | metadados (sem payload) | Query armazenada como **hash** (`query_route_log`), nunca texto; payload proibido nos hooks do gateway. |

### 6.1 Arquivos sensíveis

| Arquivo/Diretório | Conteúdo | Proteção |
|---|---|---|
| `.env` | chaves, tokens, OAuth secrets | `.gitignore`, `chmod 600` |
| `hive_mind.db` | memória inteira (inclui tabela `vault`) | `.gitignore` |
| `~/.claude-mem/` | observações temporais globais | permissões locais + backup controlado |
| `claude-mem/data/lightrag/` | knowledge graph + embeddings (P4) | `.gitignore` (regenerável via Dream Cycle) |
| `backups/` | backups do UMC | `.gitignore` |
| `config/keys/` | chaves Ed25519 | `.gitignore`; privada `0600` |

---

## 7. Validação — mudança de runtime só com evidência

A regra "mudança de runtime só com evidência" é a disciplina epistêmica do projeto (AGENTS.md §3) aplicada à segurança operacional:

1. **Toda afirmação verificável carrega evidência.** Ao salvar decisão/learning (`sinapse_save_decision`/`sinapse_save_learning`), passe `evidence` (o comando rodado, o teste que passou, o arquivo lido). Com evidência, a nota é `confidence: verified`; **sem** evidência, é `hypothesis` e o `RetrievalRouter` a rebaixa até validação.
2. **Fallback de modelo nunca é silencioso.** Trocar de modelo por falha de *disponibilidade* emite telemetria; troca por falha de *validação de saída* é proibida (ADR-009). Mudança de modelo não acontece "às cegas" — é registrada e justificada.
3. **Migração estrutural é fail-closed.** A única forma de contornar é `HIVE_ALLOW_DEFERRED_MIGRATIONS=1`, explicitamente marcada como diagnóstico de DB legado e **sem** marcar a instalação como saudável.
4. **Nenhum modelo é hardcoded.** O sistema obedece estritamente `HIVE_DREAMER_PROVIDER/MODEL` (e demais roles) do `.env`; não há modelo embutido a ser trocado fora de configuração rastreada.
5. **Hipótese refutada é corrigida no lugar.** Não se apaga nem se deixa uma hipótese refutada envenenando a recuperação — corrige-se a nota com a verdade + evidência (ver [`incidentes.md`](incidentes.md) §4).

---

## 8. Superfície de ataque e mitigações

| Vetor | Risco | Mitigação |
|---|---|---|
| REST API `:37702` | Token forjado | `hmac.compare_digest` (timing-safe); fail-closed sem `HIVE_MIND_API_KEY` |
| claude-mem worker `:37700` | Acesso local não autorizado | Bind em `127.0.0.1` apenas |
| Path traversal (escrita no vault) | Arquivo fora de `cerebro/` | `_sanitize_slug()` remove `/` e `..` |
| Injeção de segredo (entrada MCP) | Chave de API em query/conteúdo | Regex scan → Fernet → tabela `vault` |
| Google OAuth `client_secret` | Comprometida se hardcoded | Só via `.env` (`_env("GOOGLE_OAUTH_CLIENT_SECRET")`) |
| SSRF no adapter OpenAI-compatible | Endpoint malicioso | `_reject_unsafe_endpoint()` bloqueia non-http(s) e metadados AWS/GCP conhecidos; **sem proteção anti DNS-rebinding** (endpoints vêm de config/env controlada pelo operador — limitação documentada em [`modelos-ia.md`](modelos-ia.md)) |

Nenhuma porta é exposta externamente por default. Em VPS, a REST API fica atrás de nginx/Caddy com TLS; Milvus/RAGFlow rodam em rede interna.

---

## Referências cruzadas

- [`arquitetura.md`](arquitetura.md) — ADR-009 (fallback), ADR-015 (workspace), ADR-016 (quarentena), §19 (HM-12).
- [`observabilidade.md`](observabilidade.md) — disciplina anti-segredo na telemetria.
- [`incidentes.md`](incidentes.md) — resposta a vazamento de segredo.
- [`pipeline-dados.md`](pipeline-dados.md) — promoção e rastreabilidade (`source_id`, `neuron_id`).
- [`instalacao.md`](instalacao.md) — `.env`, `.gitignore`, `chmod 600`.
- [`blueprint.md`](blueprint.md) — diagramas.
- [`modelos-ia.md`](modelos-ia.md) — SSRF e limitações do gateway.
