# Runtime gates state — 2026-07-28

Status: no host atual, `G7` saiu do estado “sem prova quase total” para
evidência operacional parcial forte, `G9` continua objetivamente `degraded`,
`G12` tem superfície viva e CLI funcional, mas ainda não tem prova semântica
unificada com o mesmo marcador, e `G8` continua sem a cadeia controlada ponta a
ponta exigida pelo anexo.

## Objetivo

Registrar, com evidência fresca do host em 28 de julho de 2026, o estado real
dos gates de runtime que ainda restavam ambíguos depois do fechamento material
de `G5`, `G11`, `G14` e `G15`:

- `G7` — providers/surfaces;
- `G8` — bridge + identidade canônica + UMC;
- `G9` — knowledge health / backends;
- `G12` — CLI + REST + MCP HTTP.

## Evidência atual

Comandos executados em 28 de julho de 2026 no runtime correto da
`D:\Hive-Mind\.venv`:

- `D:\Hive-Mind\.venv\Scripts\python.exe -m hive_mind.cli validate agents --json`
- `D:\Hive-Mind\.venv\Scripts\python.exe -m hive_mind.cli service status --json`
- `D:\Hive-Mind\.venv\Scripts\python.exe scripts/health/knowledge_health.py --json`
- `D:\Hive-Mind\.venv\Scripts\python.exe -m hive_mind.cli doctor --help`
- `GET http://127.0.0.1:37702/api/v1/health`
- `GET http://127.0.0.1:37703/health`

Resultados relevantes:

- `validate_agents.report.ok = true`
- `validate_agents.report.total = 12`
- `validate_agents.report.passed = 8`
- `validate_agents.report.failed = 0`
- `validate_agents.outbox.total = 0`
- `validate_agents.umc.observations = 3484`
- `validate_agents.umc.canonical = 2947`
- `validate_agents.umc.legacy = 537`
- `knowledge_health.metrics.status = degraded`
- `knowledge_health.metrics.observations_linked_pct = 5.3`
- `knowledge_health.metrics.discoveries_pending = 2517`
- `knowledge_health.metrics.observation_vectors_vectorized_pct = 97.05`
- `knowledge_health.metrics.memory_vectors_vectorized_pct = 92.05`
- `knowledge_health.metrics.document_vectors_vectorized_pct = 0.0`
- `knowledge_health.metrics.orphan_vectors_before_prune = 7`
- `knowledge_health.metrics.orphan_vectors_pruned = 7`
- `service_status.services.sinapse-sqlite-vec.state = running`
- `service_status.services.sinapse-capture-realtime.state = running`
- `service_status.services.sinapse-api.state = exited`
- `service_status.services.sinapse-mcp-http.state = exited`
- `GET /api/v1/health -> 200`
- `GET /health (MCP HTTP) -> 200`
- `hive-mind doctor --help -> exit 0`

## Leitura por gate

### G7 — providers/surfaces

O estado do host hoje é melhor do que o anexo antigo descrevia.

Providers com prova operacional nova pelo validador nativo:

- `antigravity` — `PASSED`
- `codex` — `PASSED`
- `copilot` — `PASSED`
- `hermes` — `PASSED`
- `kilo` — `PASSED`
- `kimi` — `PASSED`
- `mimo` — `PASSED`
- `qwen` — `PASSED`

Providers explicitamente sem fonte real neste host, portanto `SKIPPED`:

- `openclaw`
- `roo`
- `screenpipe`
- `swarmclaw`

Conclusão objetiva:

- o host já não sustenta a leitura antiga de que “quase nada além de Codex”
  tinha prova;
- ainda assim o gate do anexo exigia matriz final cobrindo literalmente todos
  os providers/surfaces esperados, com justificativa formal por item;
- portanto `G7` melhora de forma material, mas ainda não fecha como concluído
  só com esta evidência.

Estado atual recomendado: `PARTIAL` com evidência forte.

### G8 — bridge + identidade canônica + UMC

O que existe hoje:

- o validador de agents gravou novos eventos;
- a saída mostra persistência nova em UMC (`observations = 3484`,
  `canonical = 2947`);
- os providers `PASSED` exibem `project_id` resolvido no relatório.

O que ainda não foi provado nesta rodada:

- o mesmo marcador controlado atravessando explicitamente
  `parser -> Claude Mem -> bridge -> UMC -> query`;
- a prova isolada de que `workspace_id = project_id` para um marcador novo
  auditado ponta a ponta.

Conclusão objetiva:

- `G8` continua melhor sustentado do que estava, mas o requisito do anexo ainda
  pede uma cadeia controlada com marcador único.

Estado atual recomendado: `PARTIAL`.

### G9 — knowledge health / backends

O gate continua objetivamente aberto.

Falhas reais do check nativo:

- `observations_linked_pct = 5.3% < 80%`
- `discoveries_pending = 2517 > 500`

Leitura complementar:

- vetorização de `observation_vectors` e `memory_vectors` está alta
  (`97.05%` e `92.05%`);
- `document_vectors` segue em `0.0%`;
- havia `7` órfãos, e o próprio check os podou nesta execução;
- `milvus_sync_lag.available = false` com motivo `milvus_not_enabled`, então não
  há prova local de sincronização Milvus a ser usada como “verde”.

Conclusão objetiva:

- o problema principal de `G9` hoje não é disponibilidade básica dos processos;
- é saúde de conhecimento insuficiente, sobretudo backlog pendente e baixa
  linkagem das observations.

Estado atual recomendado: `DEGRADED`, sem ambiguidade.

### G12 — CLI + REST + MCP HTTP

Pontos já provados hoje:

- `hive-mind doctor --help` existe e funciona (`exit 0`);
- REST health respondeu em `37702`;
- MCP HTTP health respondeu em `37703`.

Respostas de health:

- REST: `{"status":"online","engine":"Hive-Mind Vault Ready", ...}`
- MCP HTTP: `{"status":"ok","transport":"streamable-http","sessions":1}`

Divergência operacional encontrada:

- `service status --json` marca `sinapse-api` e `sinapse-mcp-http` como
  `exited`;
- porém os endpoints HTTP correspondentes estão vivos e respondendo `200`.

Isso significa que o manager/supervisor não está refletindo corretamente o
estado efetivo dos processos que escutam nas portas, ou está observando outra
instância/owner.

Limite da prova atual:

- o shell desta sessão não tinha `HIVE_MIND_API_KEY` carregada, então não foi
  possível executar `POST /api/v1/query` deste prompt sem recorrer a segredo
  externo;
- logo não há, nesta rodada, prova semântica unificada do mesmo marcador entre
  CLI, REST e MCP HTTP.

Investigação adicional realizada em 28 de julho de 2026:

- as portas vivas pertencem a:
  - `37702 -> pid 20012`, comando
    `C:\Users\miche\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe D:\Hive-Mind\scripts\services\sinapse-api.py`
  - `37703 -> pid 39100`, comando
    `C:\Users\miche\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe D:\Hive-Mind\scripts\services\sinapse-mcp-http.py`
- esses listeners são filhos de:
  - `sinapse-api` pai `pid 39744`
  - `sinapse-mcp-http` pai `pid 39404`
- ambos os pais continuam vivos e são filhos do supervisor Node
  `pid 41960`, comando:
  `node.exe D:\Hive-Mind\npm\lib\supervisor.js __daemon`
- o arquivo de estado lido pelo CLI é
  `D:\Hive-Mind\.hive-mind\state\services.managed.json`,
  com `LastWriteTime = 2026-07-27 22:09:59`
- `hive-mind service ping` falha com:
  `control socket unreachable: cannot reach control pipe: (2, 'WaitNamedPipe', 'O sistema não pode encontrar o arquivo especificado.')`

Causa objetiva da divergência:

- o runtime atual tem serviços vivos sob o supervisor Node;
- porém o control socket do daemon gerenciado não está acessível;
- por isso `hive-mind service status` cai para o JSON stale em disco;
- além disso, havia um defeito de código no modo gerenciado:
  `ManagedControlDispatcher._status()` priorizava `read_state()` em disco em vez
  de `supervisor.status()` vivo.

Correção de código aplicada nesta rodada:

- `src/hive_mind/daemon/control_dispatch.py`
  - `ManagedControlDispatcher._status()` agora devolve o estado vivo do
    supervisor, não o JSON stale;
- `src/hive_mind/cli.py`
  - `_service_status()` agora tenta consultar o control socket em managed mode e
    só cai para `services.managed.json` como fallback quando o socket não está
    acessível;
  - quando o control socket não existe, mas o host ainda está sob o supervisor
    Node legado, `_service_status()` agora reconhece e normaliza
    `D:\Hive-Mind\logs\supervisor\state.json` como `mode=legacy-supervisor`,
    em vez de mentir via `services.managed.json` stale.

Validação da correção:

- `D:\Hive-Mind\.venv\Scripts\python.exe -m pytest`
  `tests\unit\test_cli_service_status.py`
  `tests\unit\test_control_dispatch.py -q`
  -> `9 passed`

Estado atual do comando no host depois da correção:

- `D:\Hive-Mind\.venv\Scripts\python.exe -m hive_mind.cli service status --json`
  agora responde com:
  - `mode = legacy-supervisor`
  - `ready = true`
  - `sinapse-api.state = running`
  - `sinapse-mcp-http.state = running`
  - `sinapse-capture-realtime.state = running`

Leitura operacional atual:

- o host ainda não está usando o control plane novo via named pipe;
- mas o CLI deixou de reportar um falso negativo e agora reflete corretamente o
  runtime legado que está de fato vivo sob o supervisor Node.

Conclusão objetiva:

- a parte “doctor ausente” do anexo ficou superada;
- a parte “superfície viva” também ficou provada;
- o gate completo ainda não fecha porque falta a resposta semântica unificada;
- porém a divergência operacional principal entre `service status` e os
  endpoints vivos foi corrigida: o comando agora reflete o runtime real deste
  host, mesmo em modo legado.

Estado atual recomendado: `PARTIAL`.

## Conclusão executiva

No estado atual do host em 28 de julho de 2026:

- `G7` melhorou materialmente e já tem `8` providers em `PASSED`, mas ainda
  falta a matriz final formal do anexo;
- `G8` continua `PARTIAL` por ausência da cadeia controlada com marcador único;
- `G9` continua `DEGRADED` por backlog/linkagem, independentemente de alguns
  backends estarem vivos;
- `G12` tem CLI/REST/MCP HTTP vivos, porém ainda `PARTIAL` por falta de prova
  semântica unificada e por divergência entre `service status` e os endpoints.

## Próxima ação objetiva sugerida

Ordem técnica mais direta a partir daqui:

1. fechar a divergência `service status` versus endpoints vivos (`G12`);
2. executar prova controlada de marcador único para `G8` e reutilizar o mesmo
   marcador no REST/MCP/CLI para `G12`;
3. drenar `discoveries_pending` e elevar `observations_linked_pct` para sair de
   `degraded` em `G9`;
4. consolidar a matriz final de providers/surfaces com `PASSED` ou justificativa
   formal de `SKIPPED/NOT_CAPTURE_SOURCE` para `G7`.
