# Documentação do Hive-Mind

> Índice da **documentação nova** (conjunto em português, organizado por assunto).
> Última revisão: 2026-08-15.

A documentação do projeto está sendo reorganizada de documentos numerados
(`arquitetura.md`, `02-ai-models.md`, …) para um conjunto nomeado por
assunto. Este `README.md` é o índice desse conjunto novo. Os documentos
numerados ainda existem e continuam sendo a **referência canônica** até que a
migração de cada área seja concluída — veja [Fontes de verdade](#fontes-de-verdade-prioridade-de-evidência).

---

## Índice da documentação nova

| Documento | Conteúdo | Status |
|---|---|---|
| [blueprint.md](blueprint.md) | Diagramas e fluxogramas de arquitetura, fluxo de captura, Dream Cycle, cadência e RetrievalRouter | a escrever (migra `blueprint.md`) |
| [arquitetura.md](arquitetura.md) | Referência canônica de arquitetura: anatomia do cérebro, UMC, fluxos de leitura/escrita, arquitetura de Conhecimento Born-Large (K0–K10), ADRs | a escrever (migra `arquitetura.md`) |
| [pipeline-dados.md](pipeline-dados.md) | Pipeline de dados: Captura → Intake → Promotion → Persistência → Index; `DocumentPipeline` (K6) e `VectorBackend` (K1) | a escrever (migra `03-data-pipeline.md`) |
| [modelos-ia.md](modelos-ia.md) | Modelos de IA e embeddings, papéis canônicos, cadeia de fallback, Model Gateway | a escrever (migra `02-ai-models.md` + `modelos-ia.md`) |
| [runtime.md](runtime.md) | Daemon `hive-mindd`, manifesto declarativo `config/runtime.yaml`, modelo de ownership, socket de controle | **já existe** |
| [cli.md](cli.md) | CLI nativo `hive-mind` e subcomandos | a escrever |
| [agentes.md](agentes.md) | Registro MCP de agentes (`hive-mind agents`), escrita transacional, bloco de instruções, desfazer | **escrito** |
| [captura.md](captura.md) | Providers de captura, contrato de evento normalizado, outbox durável com leases, identidade canônica de projeto | **escrito** |
| [desenvolvimento.md](desenvolvimento.md) | Como alterar, matriz alteração→documentação, testes, build, release, fronteiras | **escrito** |
| [instalacao.md](instalacao.md) | Instalação em máquina nova (Linux/WSL2 e Windows nativo) | a escrever (migra `instalacao.md`) |
| [operacao.md](operacao.md) | Operação: serviços, portas, cron jobs, backup e recuperação | a escrever (migra `04-infrastructure.md` §3–§5 + `operacao.md`) |
| [observabilidade.md](observabilidade.md) | Observabilidade: health check, métricas, auditoria de integridade, Knowledge Health (K8) | a escrever |
| [incidentes.md](incidentes.md) | Resposta a incidentes e recuperação de desastres (`recover.sh`) | a escrever |
| [seguranca.md](seguranca.md) | Princípios de segurança, superfície de ataque, arquivos sensíveis, fail-closed | a escrever (migra `04-infrastructure.md` §7) |
| [HANDOVER.md](HANDOVER.md) | Handover entre sessões/agentes: estado atual, pendências, como retomar | a escrever |

---

## Por onde começar

| Se você precisa… | Leia… |
|---|---|
| Entender a arquitetura e o "porquê" das decisões | [arquitetura.md](arquitetura.md) → [arquitetura.md](arquitetura.md) |
| Ver os diagramas e fluxos | [blueprint.md](blueprint.md) |
| Registrar o Hive-Mind em um agente (MCP) | [agentes.md](agentes.md) |
| Entender como a captura funciona e como o projeto é identificado | [captura.md](captura.md) → [captura.md](captura.md) |
| Alterar código, rodar testes, fazer release | [desenvolvimento.md](desenvolvimento.md) |
| Instalar do zero | [instalacao.md](instalacao.md) → [instalacao.md](instalacao.md) |
| Operar serviços, cron e backups | [operacao.md](operacao.md) |
| Diagnosticar saúde do sistema | [observabilidade.md](observabilidade.md) |
| Responder a uma falha / recuperar | [incidentes.md](incidentes.md) |
| Revisar segurança antes de expor algo | [seguranca.md](seguranca.md) |
| Configurar o daemon e o manifesto de serviços | [runtime.md](runtime.md) |
| Usar o CLI nativo | [cli.md](cli.md) |

---

## Fontes de verdade (prioridade de evidência)

Quando dois documentos divergirem, vale a ordem abaixo. Documentos mais
próximos do código têm prioridade sobre documentos derivados.

1. **Código-fonte e artefatos de build** — `src/`, `scripts/`, `core/`,
   `config/runtime.yaml`, `pyproject.toml`, `components.lock.json`.
2. **Testes** — `tests/` documentam o comportamento esperado e o que é
   considerado regressão.
3. **Specs e ADRs** — `specs/`, .
4. **Documentação nova (este conjunto)** — o índice e os documentos nomeados.
5. **Documentação numerada legada** — `arquitetura.md` e demais, até a
   migração de cada área.
6. **`AGENTS.md` (raiz)** — guia operacional para agentes; resumo, não fonte
   primária.

Quando em conflito, corrija a documentação **na mesma entrega** que corrige o
código — nunca deixe um documento descrevendo o comportamento antigo.

---

## Regras de manutenção

1. **Reflita o código.** A documentação descreve o que está entregue, não o
   que foi planejado. Confira o comando, a tabela e o caminho no código antes
   de documentar.
2. **Não comprima specs nem evidências.** Conciso = organizado, não esvaziado.
   Não apague tabelas de comandos, opções, exit codes ou matrizes de teste para
   encurtar o texto.
3. **Não deixe documentação obsoleta.** Toda alteração de comportamento é feita
   junto com a atualização do documento correspondente (matriz em
   [desenvolvimento.md](desenvolvimento.md)).
4. **Use a ordem de evidência.** Em divergência, o código prevalece; corrija o
   documento que está atrás.
5. **Não invente.** Nada de comandos, flags ou caminhos que não existam no
   código. Em dúvida, rode o comando ou leia o arquivo.
6. **Não toque nos documentos de origem.** Os documentos legados
   (`agentes.md`, `capture/providers.md`, `captura.md`,
   `04-infrastructure.md`, `09-integration-study.md`) só são removidos ou
   reescritos quando a migração da área correspondente estiver concluída e
   revisada.
7. **Cross-reference.** Todo documento novo aponta para os documentos que
   detalham as áreas que ele apenas menciona. Link, não duplique.
8. **Público-alvo claro.** Cada documento declara para quem foi escrito;
   exemplos de comando são copiáveis.
9. **Nunca documente segredos.** `.env`, chaves de API, tokens e caminhos que
   vazem credenciais não aparecem na documentação.
10. **Mantenha o índice atualizado.** Ao criar, renomear ou remover um
    documento deste conjunto, atualize a tabela acima na mesma entrega.

---

## Documentação legada (referência canônica durante a migração)

| Documento | Conteúdo | Substituído por |
|---|---|---|
| [arquitetura.md](arquitetura.md) | Arquitetura canônica (Born-Large §22–§31) | arquitetura.md |
| [02-ai-models.md](02-ai-models.md) | Modelos de IA e papéis | modelos-ia.md |
| [03-data-pipeline.md](03-data-pipeline.md) | Pipeline de dados | pipeline-dados.md |
| [04-infrastructure.md](04-infrastructure.md) | Infraestrutura, portas, segurança | operacao.md + seguranca.md |
| [blueprint.md](blueprint.md) | Diagramas | blueprint.md |
| [modelos-ia.md](modelos-ia.md) | Model Gateway (camada canônica de execução de LLM) | modelos-ia.md |
| [instalacao.md](instalacao.md) | Instalação | instalacao.md |
| [runtime.md](runtime.md) | Daemon e manifesto | runtime.md (já é nomeado) |
| [captura.md](captura.md) | Identidade canônica de projeto | captura.md |
| [capture/providers.md](capture/providers.md) | Providers de captura | captura.md |
| [agentes.md](agentes.md) | Registro MCP (inglês) | agentes.md |
