# Security — Secrets, PII, Signing and Validation

> **Hive-Mind v3.10.1** — Project security norm.
> Canonical sources: [`04-infrastructure.md`](04-infrastructure.md) §7 (Security), [`architecture.md`](architecture.md) §19 (HM-12: visibility, Ed25519, redaction), §30 (workspace), ADR-009/015/016; code: `core/redactor.py`, `core/signing.py`, `core/model_telemetry.py`, `core/model_gateway.py`, `scripts/services/sinapse-api.py` (`encrypt_and_vault`, `verify_api_key`), `core/auth.py` (`PROVIDERS_CONFIG`).

---

## 1. Principles

1. **Fail-closed.** The REST API does not start without `HIVE_MIND_API_KEY`.
2. **Secrets only in `.env`.** Never in code, never in the vault, never in docs. `.gitignore` covers `.env` and `*.db`.
3. **Constant-time comparison.** Tokens compared with `hmac.compare_digest`, never `==`.
4. **Secret vault.** Secrets detected in content are encrypted with **Fernet** and replaced by a placeholder.
5. **Atomic write.** `os.replace()` prevents corruption from a partial failure.

---

## 2. Secrets — never in code, vault or docs

**Absolute rule:** secrets must not exist in code, in `cerebro/`, or in the documentation. The only authorized place is the `.env` at the root (not committed).

When a secret is **detected in content** (API key regex, `sk-proj-*`, etc.), the flow is:

1. **Field-level encryption** (Fernet) in the UMC `vault` table.
2. Replacement of the value by a reference in the final content (`[VAULT_SECURE:<id>]` / `[SECRET:uuid]`).
3. Recovery only via the authenticated endpoint `GET /api/v1/vault/{secret_id}` (rate limit 10/min), with format validation (`vault-[a-f0-9]{8}`).

Detection+vault implementation: `scripts/services/sinapse-api.py:encrypt_and_vault()` + `execute_insert(conn, "vault", ...)`. The write flow (`sinapse_save_decision`/`learning`) passes title and content through `encrypt_and_vault` and returns `status: "hardened"` (with a count) or `"clean"`.

> **Do not document real secrets.** This document describes **names** of variables and **how** to protect them, never values.

---

## 3. Keys and tokens

### 3.1 Infrastructure keys

| Key | Use | Fail-closed / note |
|---|---|---|
| `HIVE_MIND_API_KEY` | Bearer token of the REST API `:37702` (required) | API **does not start** without it |
| `SINAPSE_DRY_RUN` | `1` = no side effects | environment protection |
| `HIVE_ALLOW_DEFERRED_MIGRATIONS` | structural migration bypass | `0` (fail-closed); `1` **only** for legacy DB diagnosis, with visible logging and **without** marking the installation healthy |

### 3.2 LLM provider keys

Source: `core/auth.py` `PROVIDERS_CONFIG` + [`04-infrastructure.md`](04-infrastructure.md) §2.4.

| Variable | Provider |
|---|---|
| `GOOGLE_API_KEY` | Google AI Studio (Gemini) |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth Device Flow (**⚠️ rotate if compromised**) |
| `OPENAI_API_KEY` | OpenAI / OpenRouter-compatible |
| `ANTHROPIC_API_KEY` | Anthropic |
| `DEEPSEEK_API_KEY` | DeepSeek |
| `HF_TOKEN` | Hugging Face Inference |
| `DASHSCOPE_API_KEY` | Alibaba Qwen (DashScope) |
| `NVIDIA_API_KEY` | NVIDIA NIM |
| `OPENROUTER_API_KEY` | OpenRouter |
| `OLLAMA_API_KEY` | `ollama-cloud` (remote provider; local Ollama requires no key) |
| `LITELLM_API_KEY` | LiteLLM proxy (HTTP mode) |

> **No-duplication rule:** API keys are resolved **once per provider** via `PROVIDERS_CONFIG` by provider name — never duplicated per role (ADR-009). In the Model Gateway, the key is resolved at call time via `ModelProfile.api_key_env` (`profile.api_key()`), never stored in the profile object, never logged.

### 3.3 Bot tokens and identity credentials (Bot/Entra)

Identical principle to provider keys: any **bot token** (e.g. Telegram/other bot) and any **Microsoft Entra ID / Azure AD identity credential** (e.g. `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`, app registration client secrets) are **secrets**: they live exclusively in `.env`, never hardcoded, never in the vault, never in docs, never in `components.lock.json`.

- If one of these credentials is compromised, **rotate it immediately** and record the incident (see [`incidents.md`](incidents.md)).
- The reading pattern is always `_env(...)`/`os.environ` — never a string literal in code (e.g. `_env("GOOGLE_OAUTH_CLIENT_SECRET")`).

---

## 4. PII redaction — `core/redactor.py`

**Irreversible** redaction applied to a neuron's `content` and `label` **before the federated export**. **Local neurons are never modified** — `redact_neuron` deep-copies and only processes `content`/`label`.

| Function | What it does |
|---|---|
| `redact_for_export(text)` | Applies all rules in sequence; returns clean text |
| `redact_neuron(neuron)` | Deep-copy; redacts `content` and `label`; remaining fields pass through unchanged |

### 4.1 Rule categories (order matters — specific first)

The order is deliberate: specific rules before generic ones so that a broad rule does not swallow a specific match.

| # | Category | Placeholder |
|---|---|---|
| 1 | API tokens (`sk-*`, `GOCSPX-*`, `ghp_*`, JWTs `eyJ...`, `Bearer ...`) | `[REDACTED:token]` |
| 1a | AWS access keys (`AKIA`/`ASIA` + 16) — **before** phone | `[REDACTED:aws-key]` |
| 1b | AWS assignment in variable (`aws_access_key_id=`/`aws_secret_access_key=`) | `...[REDACTED:aws-key]` |
| 1c | Generic `key=value`/`key: value` secret (`api_key`, `token`, `secret`, `client_secret`, ...) — preserves key and separator, masks only the value | `...[REDACTED:token]` |
| 2 | Emails | `[REDACTED:email]` |
| 3 | IPv4 | `[REDACTED:ip]` |
| 4 | IPv6 | `[REDACTED:ip]` |
| 5 | Absolute paths (`/home/`, `/root/`, `/Users/`, `/var/`) | `[REDACTED:path]` |
| 6 | SSH/PEM private key block (multiline) | `[REDACTED:key]` |
| 7 | CPF / CNPJ (before phone, to avoid digit overlap) | `[REDACTED:cpf]` |
| 8 | Phone (broad pattern — runs last) | `[REDACTED:phone]` |

> `redact_for_export` is also reused in Model Gateway telemetry to redact `endpoint`, `error_type`, `reason`, and `unsupported_reason` before any write — no secret reaches the telemetry stream (see [`ai-models.md`](ai-models.md) § "Avoiding secret leakage" and [`observability.md`](observability.md) §4.4).

---

## 5. Ed25519 signing — `core/signing.py`

Integrity and authenticity in the **federated export** (HM-12). PEM keys in `config/keys/` (must be gitignored); private key created with `chmod 0600`.

| Function | What it does |
|---|---|
| `generate_keypair(name="default")` | Generates an Ed25519 pair; persists `{name}_privkey.pem` / `{name}_pubkey.pem`; returns `{name, fingerprint, pubkey_path}` |
| `load_private_key(name)` / `load_public_key(name)` | Loads PEM from disk |
| `sign_neuron(neuron, key_name)` | Returns a copy with `_signature` (base64 Ed25519) and `_pubkey_fingerprint` (SHA-256 hex of the public key DER) |
| `verify_neuron(neuron, pubkey)` | Verifies signature; `True`/`False`; **never raises** on an invalid signature |
| `fingerprint(pubkey)` | SHA-256 hex of the public key DER |

**Deterministic canonical payload:** `_canonical_bytes` **excludes** volatile fields (`created_at`, `updated_at`, `indexed_at`) and signature fields (`_signature`, `_pubkey_fingerprint`) to guarantee determinism across nodes.

**Federation contract** (see [`architecture.md`](architecture.md) §30.3): export only of `visibility IN (shared, public)`, always `redact` (default `true`) and optional `sign` (default `false`); import **verifies the signature** and preserves provenance (`origin_instance`, `origin_signature`); **never** import cross-instance raw without redaction, **never** overwrite local without `invalid_at`.

---

## 6. Data classification

| Data | Classification | Treatment |
|---|---|---|
| **Neurons** (`neurons`) | brain content | `visibility`: `private` (never exported) / `shared` (trusted peers) / `public` (no restriction). Export filters `IN ('shared','public')`. |
| **Observations** (`observations`) | temporal evidence | `archived`: `0` pending / `1` consolidated / `2` quarantine. `source_id` (`claude-mem:<table>:<id>`) preserves traceability; `neuron_id` links to promotion. |
| **Identity** | isolation boundary | `workspace_id` in all critical tables (default `'default'`). Cross-workspace leakage is a **security bug** (ADR-015), not a ranking one. Milvus uses `partition_key=workspace_id`. |
| **Secrets** (`vault`) | highest | Fernet, placeholder `[VAULT_SECURE:<id>]`, authenticated recovery. |
| **Federated provenance** | origin identity | `origin_instance` + `origin_signature` preserved on import. |
| **Telemetry** | metadata (no payload) | Query stored as **hash** (`query_route_log`), never text; payload forbidden in gateway hooks. |

### 6.1 Sensitive files

| File/Directory | Content | Protection |
|---|---|---|
| `.env` | keys, tokens, OAuth secrets | `.gitignore`, `chmod 600` |
| `hive_mind.db` | entire memory (includes `vault` table) | `.gitignore` |
| `~/.claude-mem/` | global temporal observations | local permissions + controlled backup |
| `claude-mem/data/lightrag/` | knowledge graph + embeddings (P4) | `.gitignore` (regenerable via Dream Cycle) |
| `backups/` | UMC backups | `.gitignore` |
| `config/keys/` | Ed25519 keys | `.gitignore`; private `0600` |

---

## 7. Validation — runtime changes only with evidence

The "runtime changes only with evidence" rule is the project's epistemic discipline (AGENTS.md §3) applied to operational security:

1. **Every verifiable claim carries evidence.** When saving a decision/learning (`sinapse_save_decision`/`sinapse_save_learning`), pass `evidence` (the command run, the test that passed, the file read). With evidence, the note is `confidence: verified`; **without** evidence, it is `hypothesis` and the `RetrievalRouter` demotes it until validation.
2. **Model fallback is never silent.** Switching models on an *availability* failure emits telemetry; switching on an *output-validation* failure is forbidden (ADR-009). A model change does not happen "blind" — it is recorded and justified.
3. **Structural migration is fail-closed.** The only way around it is `HIVE_ALLOW_DEFERRED_MIGRATIONS=1`, explicitly marked as legacy DB diagnosis and **without** marking the installation healthy.
4. **No model is hardcoded.** The system strictly obeys `HIVE_DREAMER_PROVIDER/MODEL` (and other roles) from `.env`; there is no embedded model to swap outside tracked configuration.
5. **A refuted hypothesis is corrected in place.** Do not delete or leave a refuted hypothesis poisoning retrieval — correct the note with the truth + evidence (see [`incidents.md`](incidents.md) §4).

---

## 8. Attack surface and mitigations

| Vector | Risk | Mitigation |
|---|---|---|
| REST API `:37702` | Forged token | `hmac.compare_digest` (timing-safe); fail-closed without `HIVE_MIND_API_KEY` |
| claude-mem worker `:37700` | Unauthorized local access | Bind to `127.0.0.1` only |
| Path traversal (vault write) | File outside `cerebro/` | `_sanitize_slug()` removes `/` and `..` |
| Secret injection (MCP input) | API key in query/content | Regex scan → Fernet → `vault` table |
| Google OAuth `client_secret` | Compromised if hardcoded | Only via `.env` (`_env("GOOGLE_OAUTH_CLIENT_SECRET")`) |
| SSRF in the OpenAI-compatible adapter | Malicious endpoint | `_reject_unsafe_endpoint()` blocks non-http(s) and known AWS/GCP metadata; **no anti-DNS-rebinding protection** (endpoints come from operator-controlled config/env — limitation documented in [`ai-models.md`](ai-models.md)) |

No port is exposed externally by default. On a VPS, the REST API sits behind nginx/Caddy with TLS; Milvus/RAGFlow run on the internal network.

---

## Cross-references

- [`architecture.md`](architecture.md) — ADR-009 (fallback), ADR-015 (workspace), ADR-016 (quarantine), §19 (HM-12).
- [`observability.md`](observability.md) — anti-secret discipline in telemetry.
- [`incidents.md`](incidents.md) — response to secret leakage.
- [`data-pipeline.md`](data-pipeline.md) — promotion and traceability (`source_id`, `neuron_id`).
- [`installation.md`](installation.md) — `.env`, `.gitignore`, `chmod 600`.
- [`blueprint.md`](blueprint.md) — diagrams.
- [`ai-models.md`](ai-models.md) — SSRF and gateway limitations.
