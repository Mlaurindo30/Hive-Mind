# Patterns & Conventions

Operational patterns accumulated from GBrain, GStack, and Superpowers methodologies.

## RESOLVER (skill dispatcher)

     1|     1|---
     2|     2|tags: [system, resolver, skill-dispatcher]
     3|     3|status: active
     4|     4|created: 2026-05-22
     5|     5|updated: 2026-05-22
     6|     6|---
     7|     7|
     8|     8|# RESOLVER — Skill Dispatcher
     9|     9|
    10|    10|Inspirado no GBrain do Garry Tan. Este arquivo diz qual skill carregar para cada trigger.
    11|    11|O agente lê este arquivo antes de agir. Skills são a implementação.
    12|    12|
    13|    13|## Thinking Skills (GStack-inspired)
    14|    14|
    15|    15|| Trigger | Ação |
    16|    16||---------|------|
    17|    17|| "Brainstorm", "tenho uma ideia", "office hours" | `_conventions/builder-ethos.md` — 6 forcing questions |
    18|    18|| "Review esse plano", "CEO review", "acha furos" | Desafiar premissas, 4 modos de escopo |
    19|    19|| "Debug", "corrigir", "quebrado", "investigar" | Investigação sistemática, no fixes without investigation |
    20|    20|| "Retro", "o que shipamos", "retrospectiva" | Weekly retro com per-person breakdowns |
    21|    21|
    22|    22|## Always-On (toda mensagem)
    23|    23|
    24|    24|| Trigger | Ação |
    25|    25||---------|------|
    26|    26|| Toda mensagem recebida | Carregar `[[current-state]]` + ver `_conventions/brain-first.md` |
    27|    27|| Toda decisão de build | Aplicar `_conventions/builder-ethos.md` (Boil the Lake, Search Before Building) |
    28|    28|| Qualquer decisão registrada | Salvar em `_decisions/` com frontmatter YAML |
    29|    29|| Qualquer aprendizado | Salvar em `_learnings/` com tags apropriadas |
    30|    30|
    31|    31|## Brain Operations
    32|    32|
    33|    33|| Trigger | Ação |
    34|    34||---------|------|
    35|    35|| "O que sabemos sobre", "buscar", "pesquisar" | Consultar graph.json + claude-mem primeiro |
    36|    36|| "Quem é", "background de" | Checar `_knowledge/` e `_projects/` |
    37|    37|| "Relacionamento entre", "conexões" | Usar graph query (nodes + edges) |
    38|    38|| Criar/enriquecer página de projeto | `_projects/<nome>/README.md` |
    39|    39|| Onde arquivar algo novo? | `_conventions/filing-rules.md` |
    40|    40|| "Auditar citações", "verificar links" | `_conventions/quality.md` |
    41|    41|| "Brain health", "estado do vault" | Verificar graph.json idade + nodes count |
    42|    42|
    43|    43|## Captura & Ingestão
    44|    44|
    45|    45|| Trigger | Ação |
    46|    46||---------|------|
    47|    47|| "Salva isso", "anota", "lembra disso" | `_conventions/filing-rules.md` → diretório correto |
    48|    48|| Link, artigo, tweet compartilhado | Criar nota em `_knowledge/references.md` ou pasta apropriada |
    49|    49|| "Resume esse vídeo/PDF/livro" | `_knowledge/` com link pro source |
    50|    50|| Transcrição de reunião | `_sessions/YYYY-MM-DD-meeting-*.md` |
    51|    51|
    52|    52|## Operacional
    53|    53|
    54|    54|| Trigger | Ação |
    55|    55||---------|------|
    56|    56|| Task nova, completada, adiada | Atualizar `_pipeline/` |
    57|    57|| Briefing diário, "o que tem hoje" | Ler `_pipeline/` + `_memory/current-state.md` |
    58|    58|| "Cria uma skill", "melhora essa skill" | Atualizar AGENTS.md ou criar em `_prompts/` |
    59|    59|| "Estado do projeto X" | `_projects/<X>/README.md` |
    60|    60|
    61|    61|## Identidade & Acesso
    62|    62|
    63|    63|| Trigger | Ação |
    64|    64||---------|------|
    65|    65|| Agente precisa saber identidade | Ler `_knowledge/about-me.md` |
    66|    66|| Agente precisa de contexto do usuário | Ler `_memory/current-state.md` |
    67|    67|| Setup inicial, primeiro boot | Ler `START-HERE.md` |
    68|    68|
    69|    69|## Regras de Desambiguação
    70|    70|
    71|    71|Quando múltiplas ações se aplicam:
    72|    72|1. Prefira a mais específica
    73|    73|2. Se menciona pessoa/empresa/projeto → pasta específica, não genérica
    74|    74|3. Se menciona URL → identificar tipo (artigo, vídeo, tweet) e rotear
    75|    75|4. Na dúvida: onde você buscaria isso depois?
    76|    76|
    77|    77|## Convenções (cross-cutting)
    78|    78|
    79|    79|Estas se aplicam a TODA escrita no vault:
    80|    80|- `_conventions/quality.md` — citações, back-links, no slop
    81|    81|- `_conventions/brain-first.md` — consultar vault antes de APIs externas
    82|    82|- `_conventions/filing-rules.md` — onde cada coisa vai
    83|    83|- `_conventions/output-rules.md` — padrões de qualidade de saída
    84|    84|

---

## brain-first.md

     1|     1|---
     2|     2|tags: [convention, mandatory, brain-first]
     3|     3|status: active
     4|     4|created: 2026-05-22
     5|     5|updated: 2026-05-22
     6|     6|---
     7|     7|
     8|     8|# Brain-First Lookup
     9|     9|
    10|    10|Regra obrigatória para todo agente: **consultar o vault antes de qualquer API externa**.
    11|    11|
    12|    12|O vault é a fonte de informação mais barata, rápida e pessoal que você tem.
    13|    13|
    14|    14|## Protocolo
    15|    15|
    16|    16|1. **Toda pergunta** → verificar vault primeiro (graph.json + claude-mem)
    17|    17|2. **Se o vault tem resposta** → usar. Não chamar API externa.
    18|    18|3. **Se o vault não tem** → web search como fallback
    19|    19|4. **Se encontrou algo novo externamente** → salvar no vault pra próxima
    20|    20|
    21|    21|## Por que isso importa
    22|    22|
    23|    23|- **Custo:** 1 consulta ao vault = $0. 1 web search = tokens + API calls.
    24|    24|- **Velocidade:** vault é local. API externa é rede.
    25|    25|- **Personalização:** o vault contém o contexto do Michel, não informação genérica.
    26|    26|- **Compound effect:** cada consulta ao vault enriquece o grafo. Cada bypass desperdiça.
    27|    27|
    28|    28|## Exemplos
    29|    29|
    30|    30|| Mensagem do usuário | Ação |
    31|    31||---------------------|------|
    32|    32|| "O que decidimos sobre o Thoth?" | vault → `_projects/thoth/` → `_decisions/` |
    33|    33|| "Qual a config do Hermes?" | vault → `_projects/hermes-vps/` |
    34|    34|| "Quem é aquele cliente?" | vault → `_knowledge/` → fallback web |
    35|    35|| "O que é X (termo técnico)?" | vault → web search (conhecimento externo) |
    36|    36|

---

## builder-ethos.md

     1|     1|---
     2|     2|tags: [ethos, principles, builder]
     3|     3|status: active
     4|     4|created: 2026-05-22
     5|     5|updated: 2026-05-22
     6|     6|source: gstack (Garry Tan, Y Combinator)
     7|     7|---
     8|     8|
     9|     9|# Builder Ethos
    10|    10|
    11|    11|Princípios que guiam como pensamos, recomendamos e construímos.
    12|    12|Extraídos do GStack (Garry Tan) e adaptados para o Sinapse Agent.
    13|    13|
    14|    14|## 1. Boil the Lake (Ferva o Lago)
    15|    15|
    16|    16|Com AI-assisted coding, o custo marginal da completude é próximo de zero.
    17|    17|Quando a implementação completa custa minutos a mais que o atalho — faça completo. Sempre.
    18|    18|
    19|    19|- **Lago vs oceano:** Um "lago" é fervível — 100% de cobertura de testes, feature completa, todos os edge cases. Um "oceano" não é — reescrever sistema inteiro, migração multi-trimestre.
    20|    20|- **Completude é barata.** "Abordagem A (completa, ~150 LOC) vs abordagem B (90%, ~80 LOC)" — sempre prefira A.
    21|    21|- **"Ship the shortcut" é pensamento legado** de quando engenheiro humano era o gargalo.
    22|    22|
    23|    23|**Anti-padrões:**
    24|    24|- "Escolhe B — cobre 90% com menos código." (Se A é 70 linhas a mais, escolhe A.)
    25|    25|- "Vamos deixar testes pra outro PR." (Testes são o lago mais barato de ferver.)
    26|    26|
    27|    27|## 2. Search Before Building (Busque Antes de Construir)
    28|    28|
    29|    29|O primeiro instinto do engenheiro 1000x é "alguém já resolveu isso?" não "deixa eu criar do zero."
    30|    30|
    31|    31|### Três Camadas de Conhecimento
    32|    32|
    33|    33|**Camada 1: Tried and true.** Padrões estabelecidos, abordagens testadas em batalha.
    34|    34|**Camada 2: New and popular.** Melhores práticas atuais, trends do ecossistema. Busque. Mas escrutine.
    35|    35|**Camada 3: First principles.** Observações originais derivadas de raciocínio sobre o problema específico. As mais valiosas de todas.
    36|    36|
    37|    37|O momento Eureka não é achar uma solução pra copiar. É entender o que todos fazem e POR QUÊ, aplicar first principles, e descobrir uma razão clara pela qual a abordagem convencional está errada.
    38|    38|
    39|    39|## 3. User Sovereignty (Soberania do Usuário)
    40|    40|
    41|    41|AI models recomendam. Usuários decidem. Esta regra sobrepõe todas as outras.
    42|    42|
    43|    43|Dois modelos concordando é sinal forte. Não é mandato. O usuário sempre tem contexto que modelos não têm: domínio, timing estratégico, gosto pessoal, planos futuros não compartilhados.
    44|    44|
    45|    45|Quando Claude e Codex concordam em "juntar essas duas coisas" e o Michel diz "não, mantenha separado" — o Michel está certo. Sempre.
    46|    46|
    47|    47|**A regra:** Quando você e outro modelo concordam em algo que muda a direção declarada do usuário — apresente a recomendação, explique por que acham melhor, declare que contexto podem estar perdendo, e pergunte. Nunca aja.
    48|    48|
    49|    49|## Como Eles Funcionam Juntos
    50|    50|
    51|    51|- **Boil the Lake** diz: faça completo.
    52|    52|- **Search Before Building** diz: saiba o que existe antes de decidir o que construir.
    53|    53|- **User Sovereignty** diz: o Michel decide. Sempre.
    54|    54|
    55|    55|Juntos: busque primeiro, depois construa a versão completa da coisa certa. E o Michel aprova.
    56|    56|

---

## filing-rules.md

     1|     1|---
     2|     2|tags: [convention, filing, mandatory]
     3|     3|status: active
     4|     4|created: 2026-05-22
     5|     5|updated: 2026-05-22
     6|     6|---
     7|     7|
     8|     8|# Filing Rules
     9|     9|
    10|    10|O **PRIMARY SUBJECT** do conteúdo determina onde ele vai. Não o formato, não a fonte, não a skill que está rodando. Inspirado no GBrain do Garry Tan.
    11|    11|
    12|    12|## Regra de Ouro
    13|    13|
    14|    14|1. Identifique o primary subject (pessoa? projeto? conceito? decisão?)
    15|    15|2. Arquive no diretório que corresponde ao subject
    16|    16|3. Faça cross-link dos diretórios relacionados
    17|    17|4. Na dúvida: o que você buscaria para encontrar isso depois?
    18|    18|
    19|    19|## Tabela de Decisão
    20|    20|
    21|    21|| Tipo de Conteúdo | Vai para | Exemplo |
    22|    22||-----------------|----------|---------|
    23|    23|| Decisão sobre projeto X | `_decisions/` + cross-link em `_projects/X/` | `_decisions/2026-05-22-thoth-arquitetura.md` |
    24|    24|| Aprendizado técnico | `_learnings/` | `_learnings/padroes-system-prompts.md` |
    25|    25|| Estado atual de projeto | `_projects/<nome>/README.md` | `_projects/thoth/README.md` |
    26|    26|| Conhecimento sobre pessoa | `_knowledge/about-me.md` | Identidade, stack, preferências |
    27|    27|| Objetivos e metas | `_knowledge/goals.md` | Curto, médio, longo prazo |
    28|    28|| Lista de projetos ativos | `_knowledge/projects.md` | Status, links pros READMEs |
    29|    29|| Referências e links | `_knowledge/references.md` | URLs, recursos |
    30|    30|| Template de pipeline item | `_pipeline/_exemplo.md` | Tarefas, prospects |
    31|    31|| Brain dump / reflexão | `_sessions/YYYY-MM-DD-brainderp-*.md` | Pensamentos soltos |
    32|    32|
    33|    33|## Anti-Padrões — NUNCA FAÇA
    34|    34|
    35|    35|| Errado | Certo | Por quê |
    36|    36||--------|-------|---------|
    37|    37|| Análise de projeto → `_knowledge/` | → `_projects/<nome>/` | Primary subject é o projeto |
    38|    38|| Decisão sobre feature → `_knowledge/` | → `_decisions/` + link no projeto | Decisões são entidade própria |
    39|    39|| Aprendizado de projeto → solto no root | → `_learnings/` | Aprendizados são cross-project |
    40|    40|| Card de pipeline → `_knowledge/` | → `_pipeline/` | Pipeline é fila de trabalho |
    41|    41|| Nota sobre Hermes → `_projects/thoth/` | → `_projects/hermes-vps/` | Cada projeto na sua pasta |
    42|    42|
    43|    43|## Notability Gate
    44|    44|
    45|    45|Nem tudo merece uma página no vault. Antes de criar:
    46|    46|
    47|    47|- **Projeto:** está ativo? Tem código ou tarefas associadas?
    48|    48|- **Decisão:** é estratégica ou operacional? Operacional não precisa de página.
    49|    49|- **Aprendizado:** é reutilizável? Vale referenciar depois?
    50|    50|- **Na dúvida, NÃO crie.** Uma página faltante pode ser criada depois. Uma página lixo polui o grafo.
    51|    51|
    52|    52|## Iron Law: Back-Linking (MANDATORY)
    53|    53|
    54|    54|Toda menção a um projeto ou entidade que tem página no vault DEVE criar um back-link.
    55|    55|
    56|    56|- Se uma decisão menciona o Thoth → `[[thoth]]` na decisão + link reverso no `_projects/thoth/README.md`
    57|    57|- Se um aprendizado veio do Hermes → `[[hermes-vps]]` no aprendizado + link reverso
    58|    58|- Um link unidirecional é um cérebro quebrado. O grafo é a inteligência.
    59|    59|
    60|    60|Formato de back-link:
    61|    61|```markdown
    62|    62|- **YYYY-MM-DD** | Referenciado em [[pagina]] — breve contexto
    63|    63|```
    64|    64|

---

## output-rules.md

     1|     1|---
     2|     2|tags: [convention, output, mandatory]
     3|     3|status: active
     4|     4|created: 2026-05-22
     5|     5|updated: 2026-05-22
     6|     6|---
     7|     7|
     8|     8|# Output Rules
     9|     9|
    10|    10|Padrões de qualidade de saída para todo agente conectado ao vault.
    11|    11|Inspirado no GBrain do Garry Tan.
    12|    12|
    13|    13|## No Slop
    14|    14|
    15|    15|Output de agente não é chat. É comunicação profissional.
    16|    16|
    17|    17|- Sem filler ("É interessante notar que...", "Vale mencionar...")
    18|    18|- Sem hedging quando fatos são claros
    19|    19|- Sem preamble ("Aqui está o que eu fiz...", "Certamente!", "Vou te ajudar com isso!")
    20|    20|- Frases curtas. Fatos concretos. Zero enrolação.
    21|    21|
    22|    22|## Respeito ao Tempo
    23|    23|
    24|    24|- Respostas padrão: 1-4 linhas
    25|    25|- Tarefas complexas: direto ao ponto, sem introdução
    26|    26|- Nunca explique o que você fez a menos que perguntado
    27|    27|- "Feito" é melhor que "Eu realizei a tarefa conforme solicitado"
    28|    28|
    29|    29|## Português (BR)
    30|    30|
    31|    31|- Conversas: português informal (vc, ta, pra, porra, caralho)
    32|    32|- Código e output técnico: inglês
    33|    33|- Documentação no vault: português (BR)
    34|    34|- Sem misturar idiomas na mesma frase
    35|    35|
    36|    36|## Nunca
    37|    37|
    38|    38|- Emojis a menos que o Michel use primeiro
    39|    39|- Moralizar ("É importante...", "Você deveria...")
    40|    40|- Concordar por conveniência — se é má ideia, diga
    41|    41|- Postamble explicando o que fez — só confirme conclusão
    42|    42|- Markdown em chat messaging (WhatsApp não renderiza)
    43|    43|

---

## quality.md

     1|     1|---
     2|     2|tags: [convention, quality, mandatory]
     3|     3|status: active
     4|     4|created: 2026-05-22
     5|     5|updated: 2026-05-22
     6|     6|---
     7|     7|
     8|     8|# Quality Standards
     9|     9|
    10|    10|Padrões de qualidade para toda página escrita no vault.
    11|    11|Inspirado no GBrain do Garry Tan.
    12|    12|
    13|    13|## Deterministic Links
    14|    14|
    15|    15|Links em páginas do vault DEVEM ser determinísticos (construídos de dados reais, não inventados).
    16|    16|
    17|    17|- Links do vault: `[[nome-da-pagina]]`
    18|    18|- Links de commit: `[abc1234](https://github.com/{owner}/{repo}/commit/abc1234)`
    19|    19|- Links externos: usar URL real da fonte, nunca reconstruir
    20|    20|
    21|    21|## No Slop
    22|    22|
    23|    23|Páginas do vault não são output de chat. São artefatos de conhecimento duráveis.
    24|    24|
    25|    25|- Sem filler ("É importante notar que...", "Interessantemente...")
    26|    26|- Sem hedging quando fatos são citados ("Segundo a fonte, X é verdade" não "X pode ser verdade")
    27|    27|- Sem preamble de IA ("Eu criei...", "Aqui está o atualizado...", "Certamente!")
    28|    28|- Sem datas placeholder ("YYYY-MM-DD", "recentemente", "em breve")
    29|    29|- Parágrafos curtos. Fatos concretos. Citações inline.
    30|    30|
    31|    31|## Preservação de Fraseado Exato
    32|    32|
    33|    33|Ao capturar pensamento original de alguém, use as palavras exatas. Não parafraseie.
    34|    34|Não limpe a gramática. A linguagem É o insight.
    35|    35|
    36|    36|- Citações diretas: preservar verbatim em blocos de quote
    37|    37|- Ideias e frameworks: usar a terminologia da pessoa para títulos
    38|    38|- Observações: capturar o fraseado, não uma versão sanitizada
    39|    39|
    40|    40|## Títulos de Qualidade
    41|    41|
    42|    42|- Descritivos o suficiente para identificar a página numa busca
    43|    43|- Curtos o suficiente para escanear numa lista (máx 60 caracteres)
    44|    44|- NÃO são frases ("Reunião com Pedro" não "Reunião com Pedro sobre a estrutura do novo deal")
    45|    45|- NÃO são genéricos ("Pedro Franceschi" não "Página de Pessoa")
    46|    46|- kebab-case: `estrategia-de-precos.md`
    47|    47|
    48|    48|## Citation Requirements (MANDATORY)
    49|    49|
    50|    50|Toda afirmação factual deve ter citação inline `[Source: ...]`.
    51|    51|
    52|    52|Três formatos:
    53|    53|- **Atribuição direta:** `[Source: Michel, conversa WhatsApp, YYYY-MM-DD]`
    54|    54|- **API/externo:** `[Source: {provider}, YYYY-MM-DD]` ou `[Source: {publication}, {URL}]`
    55|    55|- **Síntese:** `[Source: compilado de {lista de fontes}]`
    56|    56|
    57|    57|Precedência de fonte (maior → menor autoridade):
    58|    58|1. Declarações diretas do Michel (autoridade máxima)
    59|    59|2. Verdade compilada (síntese pré-existente no vault)
    60|    60|3. Evidência bruta (transcrições, logs)
    61|    61|4. Fontes externas (API, web search — menor autoridade)
    62|    62|
    63|    63|Quando fontes conflitam, anote a contradição com ambas as citações.
    64|    64|Não escolha uma silenciosamente.
    65|    65|

---

## superpowers-methodology.md

     1|     1|---
     2|     2|tags: [convention, methodology, superpowers]
     3|     3|status: active
     4|     4|created: 2026-05-22
     5|     5|updated: 2026-05-22
     6|     6|source: Superpowers (Jesse Vincent / Obra)
     7|     7|---
     8|     8|
     9|     9|# Superpowers Methodology
    10|    10|
    11|    11|Metodologia de desenvolvimento adaptada do Superpowers (Obra) para o Sinapse Agent.
    12|    12|Define COMO o agente trabalha, não O QUE ele faz.
    13|    13|
    14|    14|## The Skills-First Rule
    15|    15|
    16|    16|Se existe 1% de chance de uma skill ou convenção se aplicar, você DEVE usá-la.
    17|    17|Isso não é negociável. Isso não é opcional. Você não pode racionalizar pra sair dessa.
    18|    18|Verifique ANTES de qualquer resposta — até perguntas de clarificação.
    19|    19|
    20|    20|## Iron Laws (não-negociáveis)
    21|    21|
    22|    22|### 1. No Fixes Without Root Cause
    23|    23|
    24|    24|Antes de tentar qualquer correção:
    25|    25|1. Leia mensagens de erro cuidadosamente
    26|    26|2. Reproduza consistentemente
    27|    27|3. Verifique mudanças recentes (git diff, commits)
    28|    28|4. Junte evidências em sistemas multi-componente
    29|    29|
    30|    30|Correções de sintoma são falha. Correções aleatórias criam novos bugs.
    31|    31|
    32|    32|### 2. Evidence Before Claims
    33|    33|
    34|    34|NUNCA declare trabalho como completo sem verificação fresca.
    35|    35|- Identifique: qual comando prova essa afirmação?
    36|    36|- Execute: rode o comando COMPLETO
    37|    37|- Leia: output inteiro, exit code, conte falhas
    38|    38|- Verifique: o output confirma a afirmação?
    39|    39|- Só então: faça a afirmação COM evidência
    40|    40|
    41|    41|"Deve funcionar" ou "provavelmente corrigido" é mentir, não verificar.
    42|    42|
    43|    43|### 3. Subagent Freshness
    44|    44|
    45|    45|Cada subagente recebe contexto FRESCO — você constrói exatamente o que ele precisa.
    46|    46|Nunca herdam seu histórico de sessão.
    47|    47|Two-stage review: conformidade com spec primeiro, qualidade de código depois.
    48|    48|
    49|    49|## Red Flags — PARE Imediatamente
    50|    50|
    51|    51|| Pensamento | Realidade |
    52|    52||-----------|----------|
    53|    53|| "Isso é só uma pergunta simples" | Perguntas são tarefas. Verifique skills. |
    54|    54|| "Preciso de mais contexto primeiro" | Skill check vem ANTES de clarificar. |
    55|    55|| "Deixa eu explorar primeiro" | Skills dizem COMO explorar. |
    56|    56|| "Eu lembro dessa skill" | Skills evoluem. Leia a versão atual. |
    57|    57|| "A skill é overkill" | Simples vira complexo. Use. |
    58|    58|| "Vou só fazer isso rápido primeiro" | Verifique ANTES de fazer qualquer coisa. |
    59|    59|| "Isso deve funcionar agora" | Evidência antes de afirmações. Sempre. |
    60|    60|| "Só um quick fix" | Correções aleatórias criam novos bugs. |
    61|    61|

---

## padroes-system-prompts.md

     1|     1|---
     2|     2|tags: [learning, pattern, agents]
     3|     3|status: active
     4|     4|created: 2026-05-20
     5|     5|updated: 2026-05-20
     6|     6|---
     7|     7|
     8|     8|# Padroes de System Prompts dos Maiores Agentes
     9|     9|
    10|    10|Fonte: https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools (138k stars)
    11|    11|
    12|    12|## Padroes Universais
    13|    13|
    14|    14|1. **Todo-driven execution** — Todo agente de elite usa task planning. Nao e opcional, e estrutural.
    15|    15|
    16|    16|2. **Dedicated file tools, never shell** — Nenhum usa cat/sed/echo/vim. Todos tem read/edit/write dedicados.
    17|    17|
    18|    18|3. **Batching paralelo** — Leituras em paralelo, edicoes em serie. Batching de tools independentes.
    19|    19|
    20|    20|4. **Zero filler** — "2+2 → 4" (Claude Code). Sem preambulo, sem postambulo, sem "Otima pergunta!".
    21|    21|
    22|    22|5. **Quality gates before done** — Build, lint, tipo, testes. Nao declara concluido sem verificar.
    23|    23|
    24|    24|## Por Agente
    25|    25|
    26|    26|| Agente | Destaque |
    27|    27||--------|---------|
    28|    28|| Claude Code | Concise: 1-4 linhas, TodoWrite obrigatorio, proactivity balanceada |
    29|    29|| Cursor | codebase_search semantico, memory tool, batch paralelo |
    30|    30|| Devin | Planning mode vs execution mode, think tool (scratchpad oculto) |
    31|    31|| Copilot | Quality gates, requirement extraction, batch parallel |
    32|    32|| Perplexity | Query type awareness, citacao inline, nunca moralizar |
    33|    33|
    34|    34|## O que aplicamos no Hermes
    35|    35|
    36|    36|- SOUL.md reescrito com concisao, todo-driven, quality gates
    37|    37|- Memoria persistente ja existe (cursor-style)
    38|    38|- Batch paralelo ja suportado
    39|    39|- Query type awareness implementada
    40|    40|
    41|    41|## Relacionado
    42|    42|
    43|    43|- [[methodology]] — metodologia da THOTH AI
    44|    44|- [[CLAUDE]] — SOUL do Claude Code
    45|    45|


---

## MCP Pattern (2026-05-23)

Learning from MCP


---

## Thoth deve usar sinapse-mcp.py como MCP server unificado (2026-05-24)

O sinapse-memory.py (plugin de 984 linhas) é o backend unificado. O sinapse-mcp.py expõe 5 tools. Ambos usam o mesmo código. Não é necessário MCP server separado para claude-mem — o sinapse_query já cobre todos os backends.


---

## Aprendizado via API (2026-05-24)

Novo padrão identificado no fluxo de testes de integração da API REST.


---

## temporal: Graphify reindex executado. graph.json atualizado: 547 nodes, 707 edges (links), (2026-05-25)

Graphify reindex executado. graph.json atualizado: 547 nodes, 707 edges (links), 44 communities. LLM: deepseek, 36 cache hit, 55 re-extraídos. Custo: ~$0.014. Output em graphify/graphify-out/graph.json (382 KB).


---

## temporal: Reindex Graphify do vault Sinapse executado via cron. Resultado: 494 nodes, 630  (2026-05-25)

Reindex Graphify do vault Sinapse executado via cron. Resultado: 494 nodes, 630 edges, 38 comunidades (Leiden clustering). Tipos de nodes: 408 code, 53 concept, 29 document, 4 rationale. Custo: ~$0.0258 via DeepSeek. Graph movido para graphify/graphify-out/ com symlinks de retrocompatibilidade em cerebro/graphify-out/. Todos os backends saudáveis.


---

## temporal: Graphify reindex executado com sucesso. Vault Obsidian indexado com backend deep (2026-05-26)

Graphify reindex executado com sucesso. Vault Obsidian indexado com backend deepseek. Resultado: 567 nodes, 699 links/edges, 58 comunidades. graph.json atualizado (389.5K) em graphify/graphify-out/. Cache semântico: 91 hit, 0 miss. 32 nodes deduplicados (9 exact, 22 fuzzy).


---

## sqlite-vec como substituto do Chroma (2026-05-30)

sqlite-vec worker substitui Chroma no claude-mem para busca semântica. Usa sqlite-vec (extensão nativa SQLite) + fastembed (all-MiniLM-L6-v2, 384 dims). Zero dependência de Python MCP/uvx. Worker standalone em :37701, systemd user service (sinapse-sqlite-vec.service). Backfill automático na primeira query. Priority backend no plugin sinapse-memory (mais leve e rápido que Chroma).


---

## Análise Fria: Manus Agent — 3 fases de adoção (2026-05-30)

Análise Fria do Manus Agent concluída. Veredito: adotar parcialmente. 3 fases de adoção recomendadas: (1) Event stream tipado no plugin sinapse-memory, (2) Planner com pseudocódigo + reflexão estendendo o todo, (3) Knowledge module condicional com scope por skill. Ignorar sandbox, deploy público, Data API Python, message_ask_user síncrono. PDF salvo em reference/analises/.


---

## Cebolinha voice clone provider (2026-05-30)

Michel aprovou a voz do Cebolinha clonada via Qwen3-TTS Base. O ref_text precisa ser EXATAMENTE o que foi falado no áudio, incluindo os erros propositais (Cebolinha troca R por L). Parâmetros que funcionaram: temperature=1.0, top_k=50, top_p=1.0, language=portuguese. Provider registrado como 'cebolinha' no Hermes.


---

## Go build tags pattern for TTS registry + filepath.ExpandUser fix + CacheKey on Result (2026-06-01)

Go build tags: registry.go + registry_audio.go + registry_stub.go precisam seguir o padrão: struct Registry declarado SEMPRE (sem build tag), métodos declarados por arquivo condicional (//go:build audio / //go:build !audio). Build tags não podem ter overlap de declarações. filepath.ExpandUser NÃO existe em Go — usar os.UserHomeDir() + filepath.Join. Result.CacheKey deve existir na struct se providers a usam.


---

## L1+L2 cache pattern para providers com synthesis caro (2026-06-02)

## L1+L2 cache pattern (2026-06-01)

TTS providers Kokoro e Qwen3 wired com cache de dois tiers:
- L1: in-memory LRUCache (bounded, volátil, ~50ns hit)
- L2: DiskCache JSON+sidecar (persistente, ~200μs hit)

Pattern transferível: qualquer provider cuja síntese é cara
(>100ms) e que pode ser chamada repetidamente com mesmos inputs
beneficia desta arquitetura. O L1 hit serve requests recentes, o
L2 hit serve restarts.

Critical implementation detail: **modtime alignment via os.Chtimes**
no Put. Sem isso, `Has()` (cheque Stat().ModTime()) e `Get()` (cheque
entry.CachedAt) podem divergir em alguns segundos pela precisão do
FS, causando testes flaky em Windows e comportamento inconsistente
em produção.

## Opt-in via settings (default off)

DiskCache sempre opt-in via setting. Razão: o L2 consome disco,
não deve ser surpresa para operadores. Settings shape:
`{disk_cache_enabled, disk_cache_dir, disk_cache_ttl}`. Failures
de init do L2 degradam silenciosamente para L1-only — cache miss
não vira erro.

## Quando NÃO usar este pattern

- Síntese barata (<50ms): overhead do L2 é pior que repetir
- Request único por key (no repetition possible): L1+L2 só desperdiça memória/disco
- Dados confidenciais (PII): cache em disco pode violar compliance. Usar L1 only ou L2 com encryption-at-rest (não implementado)



---

## Thoth TTS/Voice: prefer shell-out ffmpeg no runtime Go, não wrapper Python externo (2026-06-02)

Quando o runtime alvo é Go (Thoth), não depender de wrappers Python externos para transcoding de mídia, mesmo que o Hermes já tenha função equivalente (_convert_to_opus).

Padrão recomendado:
1) Runtime Go chama ffmpeg via exec.CommandContext (timeout + stderr trimming)
2) Define erro explícito para ausência de binário (ErrFFmpegUnavailable)
3) Adapter de canal usa best-effort + soft-fail: tenta transcode, em erro mantém fluxo legado
4) Cache de transcode por hash(input+opts)+TTL para evitar subprocess repetido
5) Cobrir com testes sem ffmpeg real via hook de runCommand/lookPath

Benefício: autonomia do runtime, menos acoplamento operacional entre projetos, mesma qualidade de áudio no Telegram (OGG Opus mono 64k).


---

## Reaper seguro: limpar só '.transcode-cache*' sob raiz TTS (2026-06-02)

Ao integrar cleanup de cache de transcode com reaper global, não usar recursão cega na raiz de attachments.

Padrão seguro aplicado:
- reapOldTTSAttachments só entra em subdirs com prefixo '.transcode-cache'
- subdirs fora desse padrão são ignorados
- arquivos antigos em cache são removidos por TTL
- cache dir vazio é removido best-effort

Esse padrão evita apagar artefatos de outras features e mantém limpeza automática do transcode cache.


---

## OpenAlice langgraph_agent underrated upside — Expansionist council take (2026-06-09)

The langgraph_agent sidecar is a general-purpose multi-agent research platform disguised as a trading bot. Underrated elements: (1) shadow-only architecture is a free, safe LLM eval harness — rare in retail trading where the norm is "no analysis or real money at risk"; (2) capability gateway at /api/langgraph/capabilities is mislabeled — it's a generic MCP skill broker, not LangGraph-specific. Allowlist shows ~20 skills consumable by any external agent (Claude Code, Codex, Hermes, OpenClaw) over MCP. Rename, spec, ship as openalice-mcp-broker. (3) Etraider→OpenAlice port is the first faithful TypeScript port of TradingAgents (AGPL-3.0), 351-line STATUS with per-task evidence — publishable as real OSS, not just local overlay. (4) rank_aware candidate selection with feature-flag scaffold, redacted audit, fail-closed promotion is publication-grade ML infra. Reframe: shadow-mode multi-agent research platform with pluggable capability broker. Trading is the demo; medical/legal/security/supply-chain is the market.


---

## Restore Hermes após formatação (2026-06-09)

Para restaurar o Hermes após formatação:
1. Clonar o repo: `git clone git@github.com:Mlaurindo30/hermes_thoth.git`
2. Instalar o Hermes Agent normalmente
3. Rodar: `cd hermes_thoth && bash scripts/restore_hermes.sh`
4. Editar `~/.hermes/.env` — substituir `<MASKED>` pelos secrets reais (DeepSeek, NVIDIA, LM Studio, etc.)
5. Editar `~/.hermes/config.yaml` — verificar providers e API keys
6. Configurar git: `git config --global user.name "Michel Laurindo" && git config --global user.email "michel.laurindo@outlook.com"`
7. Instalar plugins extras se necessário: `hermes plugins install ...`
8. Restartar o Hermes

Skills críticas salvas: dynamic-workflow, council, devin-mode, kiro-mode, windsurf-cascade, manus-loop, comet-security, tts-system, hermes-infrastructure, segundo-cerebro, systematic-debugging, subagent-driven-development, test-driven-development, coding-agent-toolchain. Total: 58 skills customizadas.


<!-- merge straggler 2026-06-17 -->


---

## MCP Pattern (2026-06-17)

Learning from MCP


---

## Ler fonte antes de explicar ferramenta externa — não decorar da memória (2026-06-25)

Não decorar explicações sobre ferramentas da memória do projeto. Sempre ler a fonte primária (README do GitHub, código atual) antes de explicar o que uma ferramenta faz.

Caso concreto: descrevi RTK como "plugin Hermes" e "camada de execução do cérebro" baseado no que a memória do Hive-Mind tinha — sem verificar o repositório oficial https://github.com/rtk-ai/rtk. Michel pegou o erro e pediu pra ler antes de vomitar.

O RTK na real:
- CLI proxy Rust (rtk-ai/rtk, 66k stars), single binary
- Intercepta comandos shell antes da execução e rewrite pra versões compactas
- Reduz 60-90% token consumption em comandos comuns
- NÃO é plugin Hermes — Hermes é um dos 14 tools suportados
- Funciona com Claude Code, Cursor, Codex, Gemini, OpenCode, Cline, Roo Code, Kilo Code, etc.
- Age entre agente e shell via hooks (PreToolUse / tool.execute.before / plugin)

Heurística:
- Quando uma frase sobre uma ferramenta "soa" como um resumo de arquivo de docs do projeto, ir verificar o upstream oficial antes de usar como verdade
- "Plugin do X" é claim forte — exige confirmar via repo, README ou código
- "Camada Y" também — exige confirmar arquitetura real
- Preferir ler 30 segundos do README do que confiar em resumo decorado

Aplicável a qualquer ferramenta externa: RTK, Graphify, LightRAG, OmniParser, OpenMemory, Cognee, etc. Todas são "órgãos" do cérebro no sentido anatômico, mas cada uma tem arquitetura, runtime e escopo próprios que precisam ser lidos na fonte, não decorados.


---

## Não descrever ferramenta externa como parte do Hive-Mind — ler código antes (2026-06-25)

Lição do incidente RTK/Hermes no sinapse_health (commits a91b39e → 84a4d80 → 8a1db6b):

A fronteira "o que é parte do Hive-Mind vs o que é ferramenta externa" não estava clara na minha memória decorada. Michel corrigiu três vezes até ficar certo.

Regra operacional: ao descrever qualquer ferramenta no schema MCP, no roadmap, em docstring ou em commit message, antes de afirmar a relação dela com o Hive-Mind, verificar:

1. LER `plugins/hermes/sinapse-memory.py` linhas 1-13 (cabeçalho) pra confirmar o que o plugin DO Hermes faz (acesso ao cérebro, não parte do cérebro).

2. LER `README.md` linhas ao redor de "Arquitetura" / "Componentes" pra ver o que o repo declara como interno vs externo.

3. Verificar no `integrations/` — TUDO dentro é vendor que virou órgão do cérebro. TUDO fora (RTK upstream, Hermes, Claude Code, etc.) é externo e só se conecta.

4. Para qualquer ferramenta externa (RTK, Hermes, Claude Code, Cursor, etc.), a frase correta é SEMPRE: "<ferramenta> é externa, unrelated ao Hive-Mind; agents that want <ferramenta> install it themselves". Nunca descrever como se fosse parte do produto.

Erros específicos que cometi e por quê:

- "RTK é plugin Hermes" → decorei da memória do projeto sem verificar. RTK é independente; Hermes é um dos 14 consumers suportados pelo `rtk init`.

- "shell optimizer / execution layer" → descrevi o RTK pelo que eu achava que fazia, não pelo que ele faz. RTK é CLI proxy Rust (rtk-ai/rtk, 66k stars) que intercepta comandos shell.

- Sugerir que RTK é parte do Hive-Mind → venho do `integrations/rtk/` que existe no repo, mas é CLONE pra o usuário ter binário pronto, não feature do cérebro. O cérebro não usa RTK.

Como o Michel sinalizou: "Hermes é um agent que se conecta a nbossa tool ele nem tem que ser listado diferente disso em nenhum lugar, assim como qualquer outro". Hermes é cliente, não parte. Mesma categoria do RTK, do Claude Code, do Cursor.

Heurística final: se a frase começa com "<ferramenta> faz parte do Hive-Mind" ou "<ferramenta> é um módulo/plugin do <repo>", pare e releia. Provavelmente está confundindo "instalado em" com "parte de".


---

## P2P Sync implementation: estado atual vs docs/07-p2p-sync-setup.md (2026-06-25)

Revisão pré-implementação do P2P Sync em 2026-06-25.

Arquivos existentes:
- scripts/health/audit_memory.py: já faz scan de cortex/temporal, detecta hash mismatch (SHA-256 truncado em 16 chars), reindexa, ingere arquivos .sync-conflict-*.md e move para cortex/insula/conflitos/. Chama register_ambiguity() do core.database.
- scripts/dream/semantic_diff.py: já calcula cosine similarity via get_embedder() e, se abaixo de threshold (0.98 default), chama call_llm_structured com SemanticDiffResult (DiffCategory.ADDITIVE/SUBSTITUTIVE/etc).
- core/umc_schema.sql: tabela ambiguities já existe com id, neuron_id, source_a_hash, source_b_hash, content_a, content_b, metadata_a, metadata_b, status (pending/synthesized/branched).

Gaps em relação a docs/07-p2p-sync-setup.md:
1. O documento fala em UUID v4 para neuron_id; audit_memory.py ainda usa md_file.stem (hash/identificador derivado do filename), não UUID.
2. O frontmatter integrity_hash esperado no .md não é verificado nem atualizado por audit_memory.py.
3. semantic_diff.py não segue os thresholds definidos na spec (>0.92 idêntico, 0.70-0.92 complementar, <0.70 divergente → LLM).
4. O documento descreve resolução autônoma (merge/choose_a/choose_b/branch) no dream_cycle.py; semantic_diff.py retorna suggested_resolution mas não aplica no vault nem atualiza ambiguities.status.
5. Não há script de setup/install do Syncthing integrado ao install.sh, nem geração de cron para audit_memory.py.
6. O spec menciona metadata machine_id, trust_level, source_observation_ids no frontmatter; ainda não propagado para atomic writes de decisões/aprendizados.
7. Disaster recovery recover.sh é mencionado mas precisa ser verificado se já reconstrói o índice a partir do vault.

Próximos passos sugeridos: alinhar com usuário quais gaps serão implementados neste ciclo e em que ordem; priorizar reconciliação vault↔SQLite + resolução de conflitos + UUID/PK.


---

## crsql_changes.pk é blob binário packed — nunca decodificar como utf-8 (2026-06-25)

O campo `pk` retornado por `SELECT * FROM crsql_changes` no CR-SQLite 0.16.x NÃO é a string do id — é um blob binário packed (ex.: id 'n1' vira b'\x01\x0b\x02n1'). Para aplicar changes em outro peer, use SEMPRE INSERT INTO crsql_changes (apply_changes), que devolve o pk ao engine intacto. Nunca tente pk.decode('utf-8') para reconstruir o id e fazer INSERT direto na tabela user — isso corrompe a PK silenciosamente.

Corolário de teste: um teste de convergência que só compara COUNT(*) entre dois DBs é insuficiente — passa mesmo com PKs corrompidas e updates perdidos. Sempre verificar (a) que os ids batem e (b) que UPDATE em linha existente propaga, não só insert de linha nova.

Corolário de perf: antes de abandonar um caminho "lento", reproduza o benchmark isoladamente. Os 190s atribuídos a apply_changes/crsql_changes na verdade vinham do truque de arquivo temporário do Bloco C. apply_changes faz 65k changes em ~0.5s. Medir, não estimar.


---

## temporal: P8 Bloco D concluído: endpoints HTTP de sync CRDT adicionados em scripts/service (2026-06-25)

P8 Bloco D concluído: endpoints HTTP de sync CRDT adicionados em scripts/services/sinapse-api.py — GET /api/v1/sync/export e POST /api/v1/sync/import. Reusam _export/_import_changes do CLI sinapse-sync.py via importlib (DRY, fonte única da lógica crsql_changes). Auth Bearer (verify_api_key), rate-limit 30/min, gate HIVE_CRDT_SYNC=true (503 se desabilitado). Ativam --push/--pull/--sync over-the-wire. Novo teste tests/integration/test_sync_endpoints.py: 4 testes (auth export, auth import, gate 503, round-trip HTTP completo preservando PK + propagando UPDATE) contra DBs CR-SQLite temporários, autocontido (não precisa do hive_mind.db real nem HIVE_RUN_INTEGRATION). Suíte CRDT+sync: 10/10 verde. Roadmap §P8 Sprint 3.1 atualizado (tarefas 4,6 corrigidas + tarefa 7 Bloco D). Lobo: Tronco (infra de transporte de estado).


---

## P8 re-pass com swarm (tester + code-analyzer): 12 achados, 9 corrigidos (2026-06-25)

Em 2026-06-25 disparei dois agentes de swarm para re-passar toda a Fase P8 (CR-SQLite sync). Ambos foram precisos (verifiquei cada achado contra o código antes de agir — diferente da "péssima decisão" original que confiou em benchmark não-medido).

TESTER (ruflo-testgen): adicionou tests/integration/test_crdt_gaps.py (11 testes), total subiu de 10 → 21 passando. Cobriu: convergência BIDIRECIONAL real, DELETE propaga via tombstone (CR-SQLite v0.16.3 emite tombstone com site_id local — confirmado empírico), --since incremental, idempotência (mesmo payload 2x), NULLs, preservação de TODAS as colunas (gap do bug antigo), tabelas goals/observations no round-trip, payload vazio, serialização bytes/None. Nenhum bug de produção novo revelado — confirma que o revert para apply_changes está sólido. PK composta não testável (synapses usa id TEXT PK simples, não composta).

CODE-ANALYZER: confirmou ZERO vestígio do padrão quebrado (nenhum INSERT OR IGNORE/pk.decode no path de import). 12 achados. Corrigidos 9:
- #1 (database.py:131) double-load da extensão crsql — enable_crdt já carrega internamente; removido.
- #2 (database.py:299) injeção SQL via hostname no ALTER ... DEFAULT '{hostname}' — parametrizado (ALTER sem default + UPDATE com placeholder).
- #3 (sinapse-api.py) /sync/import sem limite de payload — guard 413 com teto _MAX_SYNC_CHANGES=1M (env HIVE_SYNC_MAX_CHANGES).
- #4 (setup_crdt.py) conexão vazada entre fases (b-c) e (e) — new.close() antes de reabrir.
- #5 (sinapse-sync.py main) CLI não tinha gate HIVE_CRDT_SYNC — falha cedo com mensagem acionável (exit 1) em vez de OperationalError cru.
- #7 (setup_crdt.py) re-executar resetava relógio vetorial CRDT — preflight detecta DB já-CRR e aborta sem --force.
- #8 (sinapse-sync.py) timeout=10 vs 30s do get_connection — alinhado para timeout=30 (busy_timeout).
- #9 (setup_crdt.py) --keep-original inerte (store_true+default=True nunca False) — virou BooleanOptionalAction funcional (--no-keep-original apaga backup).
- #12 (setup_crdt.py) guard morto if not args.dry_run (dry-run já retorna antes) — removido.
Pulei #6 (commit fora do try em apply_changes — mitigado por #8), #10 (ValueError de hex inválido), #11 (doc do commit em enable_crdt). Suíte 21/21 verde após todas as correções.

Lição de processo: agentes de swarm para review são eficazes QUANDO o orquestrador verifica cada achado contra o código antes de aplicar — não aplicar cegamente nem descartar cegamente.


---

## temporal: P7 (MCP Streamable HTTP) concluído em 2026-06-25. scripts/services/sinapse-mcp-h (2026-06-25)

P7 (MCP Streamable HTTP) concluído em 2026-06-25. scripts/services/sinapse-mcp-http.py com aiohttp, paralelo ao stdio, reusa handle_request/TOOLS de sinapse-mcp.py via importlib (nome com hífen). Decisão de design: tools sinapse_* são todas request/response → SEM SSE/server-push (stream sem nada a transmitir). Conformidade Streamable HTTP onde importa: POST /mcp single+batch→JSON, notificação→202, initialize→header Mcp-Session-Id, GET /mcp→405 (spec permite sem SSE), DELETE→encerra sessão, /health. aiohttp>=3.9 em pyproject; unit sinapse-mcp-http.service porta 37703 via env em install_services.py. 9 testes (test_mcp_http.py) + smoke ao vivo curl (initialize/tools-list=13/405/health). Commit cd7b632 no branch p8-crsqlite-sync. Sprint 3 (P7+P8) concluída. Pendentes: P9 Langfuse, P10 RAPTOR, P11 LanceDB, P13 OmniParser. Roadmap §P7 e §11 atualizados. Interop com cliente MCP real é verificação manual (claude mcp add --transport http sinapse-http http://localhost:37703/mcp).


---

## components.py tinha bug de path + patch do graphify foi perdido no rebase (2026-06-26)

Dois bugs descobertos e corrigidos ao montar o fluxo de atualização:

1. BUG DE PATH em scripts/setup/components.py: usava `ROOT / name` (ex.: <root>/graphify), mas os checkouts reais estão em <root>/integrations/<name>. Resultado: `verify` dava FAIL em todos. Corrigido adicionando campo `path` por componente no components.lock.json e helper component_target(name, spec) = ROOT / spec.get("path", name). Trocado em clone_pinned, bootstrap, verify, update, rollback, apply/remove_component_patch.

2. PATCH DO GRAPHIFY PERDIDO: o git pull --rebase antigo avançou graphify para 905e0a7 e o patch Hive-Mind (graphify-hive-mind.patch) sumiu — sqlite_export.py ausente, zero to_sqlite/_trigger_document_ingest/.docx. A integração rodava SEM export SQLite em tempo real nem ingest de PDF/DOCX. Regenerado via `git apply --3way --unidiff-zero` (resolvi 4 conflitos manualmente; o 3-way preservou melhorias upstream que o patch antigo destruiria: to_json(community_labels=labels) e Path(os.fsdecode(...))). Novo patch valida forward+reverse-check, compila e passa tests/test_watch.py (44 passed).

3. rtk tinha mudança Hive-Mind UNTRACKED (_log_to_umc em hooks/hermes/rtk-rewrite/__init__.py) que travaria o is_dirty do components.py update. Virou patch rastreado: integrations/patches/rtk-umc-logging.patch.

LIÇÃO: patches frágeis em -U0 (unidiff-zero, sem contexto) quebram em git pull raw. O fluxo correto é components.py update (remove patch → fetch → reaplica → bumpa lock). O update script agora limpa __pycache__ antes para não disparar 'dirty checkout beyond the pinned patch'.


---

## agy/gemini CLIs são agênticos — isolar skills via HOME limpo p/ saída determinística (2026-06-26)

Os CLIs `agy` (antigravity) e `gemini` suportam modo headless (`agy -p "..." --model X`; `gemini -p "..." -m X -o json`), mas são ASSISTENTES AGÊNTICOS: por padrão carregam contexto/skills globais de ~/.gemini/GEMINI.md e ~/.gemini/skills/ (inclui llm-council), poluindo a saída com vereditos em vez de JSON.

SOLUÇÃO DE ISOLAMENTO (validada): rodar o CLI com HOME apontando p/ um dir cujo .gemini contém APENAS as credenciais (oauth_creds.json, projects.json, google_accounts.json, installation_id, state.json, config) via SYMLINKS para os arquivos reais (refresh do OAuth propaga), e SEM GEMINI.md nem skills/. Resultado: saída limpa ("OK" em vez de ensaio do council). Implementado em core/agy_client.py (_ensure_isolated_home em ~/.cache/hive-mind/agy-isolated). Também rodar de cwd neutro p/ evitar GEMINI.md/AGENTS.md do projeto.

Extração de model IDs reais: `strings ~/.local/bin/agy | grep` revelou gemini-3.5-flash, gemini-3.1-pro, claude-sonnet-4-6, claude-opus-4-6, gpt-oss-120b-maas. `agy models` lista os nomes de display (com níveis Low/Medium/High = thinking budget, não modelos separados).

CUIDADO: latência — cada chamada spawna o agy (segundos+). Para roles de alta frequência, o client Python (gemini-2.5 via Code Assist) é mais rápido; antigravity-cli é p/ quando se quer Claude/GPT-OSS especificamente.


---

## Code Assist serve Gemini 3.x na forma -preview; 404 inicial é transitório (validar 2x) (2026-06-26)

CORREÇÃO de aprendizado anterior (que dizia 'gemini-cli só serve gemini-2.5'). Errado: foi artefato de 404s TRANSITÓRIOS na 1ª chamada (cold start / onboarding do loadCodeAssist / estado do token). Revalidando 2x e tratando 429 como 'modelo existe' (só quota), o quadro real do endpoint Code Assist (cloudcode-pa, v1internal:generateContent, provider gemini-cli) é:

USÁVEL via client Python (core/gemini_cli_client.py):
  gemini-2.5-flash, gemini-2.5-pro, gemini-3.1-flash-lite,
  gemini-3-flash-preview, gemini-3.1-pro-preview, gemini-3-pro-preview

404 (NÃO existem nesta superfície):
  gemini-3.5-flash, gemini-3.1-pro (forma SEM -preview)

ASSIMETRIA-CHAVE entre as duas superfícies:
  • Code Assist (gemini-cli, client Python): Gemini 3.x usa forma '-preview'
    (gemini-3.1-pro-preview, gemini-3-flash-preview, gemini-3-pro-preview).
  • agy nativo (provider antigravity): usa forma SEM -preview (gemini-3.1-pro)
    e tem gemini-3.5-flash + claude-sonnet/opus-4-6 + gpt-oss-120b-maas.

LIÇÃO METODOLÓGICA: ao validar disponibilidade de modelo via Code Assist, rodar
>=2 passagens e classificar 200/429 como 'usável', só 404 consistente como
'indisponível'. Uma única chamada pode dar 404 falso por cold start.

Config atual (auth.PROVIDERS_CONFIG models_hint + gemini_cli_client._MODEL_ROTATION):
gemini-cli = [2.5-flash, 3.1-flash-lite, 3-flash-preview, 3.1-pro-preview, 3-pro-preview, 2.5-pro];
antigravity = [gemini-3.5-flash, gemini-3.1-pro, claude-sonnet-4-6, claude-opus-4-6, gpt-oss-120b-maas].


---

## Estudo 2 — correção das 11 falhas de teste (6 unit + 3 regressão + 2 integ) (2026-06-26)

Investigação e correção das falhas pré-existentes + regressões do Estudo 1. Suíte final: 579 passed, 7 skipped, 0 failed.

UNIT (6 originais):
1. test_visual_capture (2): LACUNA REAL. capture_screen não tinha param `monitor` nem guarda multi-monitor (o protocolo/MCP exigem). Implementado em scripts/capture/visual_capture.py: detecta >1 monitor real via mss.monitors e exige monitor=N; passa mon=monitor ao sct.shot. BÔNUS: o __main__ não parseava --monitor (o wrapper MCP _capture_screen já passava `--monitor N`, mas o CLI jogava tudo na description) — corrigido o parse.
2. test_register_mcp (3): TESTES DESATUALIZADOS. register-mcp.sh foi consolidado p/ registrar SÓ sinapse-memory (federa os backends; CLAUDE.md "use SOMENTE sinapse_*"), removendo claude-mem-local/neural-memory-local. Tests atualizados p/ servidor único + corrigida asserção do log do codex (mcp add tem --env antes do --) + o merge test agora usa PROJECT_ROOT tmp (não poluir repo real).
3. test_capture_tailer (1): BUG REAL. capture-tailer.py fazia `if not sources: continue`, pulando adapters mode=reparse sem fontes de arquivo (screenpipe REST, owner=timer) → captura REST nunca rodava pelo timer. Corrigido: reparse sem sources processa uma vez com source=None.

REGRESSÃO do Estudo 1 (3): test_gemini_cli_client (endpoint_por_provider, model_chain_rotaciona, 429_rotaciona) referenciavam antigravity como Code Assist + IDs antigos. Atualizados: antigravity saiu do gemini_cli_client (virou agy); default endpoint=cloudcode-pa; chain gemini-cli com 3.x-preview.

INTEGRAÇÃO (5):
4. test_sinapse_api authenticated (3): POLUIÇÃO CROSS-FILE. test_sinapse_api e test_sync_endpoints setam HIVE_MIND_API_KEY no nível de módulo com chaves diferentes; a API lê a key por request → quem importa por último vence. Fix: fixture autouse com monkeypatch.setenv reafirmando a key de cada módulo antes de cada teste.
5. test_vision_real (2): 429 do ollama-cloud (limite semanal da conta) — ambiental. Fix: _vision_call_or_skip pula (pytest.skip) em 429/quota em vez de falhar.


---

## setup-brain deve confirmar modelo vivo do claude-mem (2026-06-26)

Ao trocar o papel claude_mem pelo scripts/setup/setup-brain.py, salvar HIVE_CLAUDE_MEM_PROVIDER/MODEL no .env não basta. É preciso executar scripts/setup/sync-claude-mem-provider.py e confirmar http://127.0.0.1:37700/api/settings, pois o worker real usa ~/.claude-mem/settings.json e pode permanecer no modelo antigo.


---

## P2 importlib zerado nos serviços via shim+rename (sinapse_mcp / sinapse_sync) (2026-06-26)

Continuação da auditoria P2 (sys.path/importlib). Estado final: importlib inline ELIMINADO dos 4 consumers.

Padrão aplicado (igual ao zettelkasten do codex — shim+rename, superior ao wrapper-importlib do hermes):
1. `git mv scripts/services/sinapse-mcp.py → sinapse_mcp.py`; criado shim hifenizado `sinapse-mcp.py` (10 linhas: sys.path.insert(parents[2]) + `from scripts.services.sinapse_mcp import main`). Mantém o caminho que `register-mcp.sh` registra (linhas 104/266) e o stdio entrypoint. `sinapse-mcp-http.py` agora faz `from scripts.services import sinapse_mcp as _MCP` (removido `_load_mcp_module`/importlib); `_mcp()` retorna o global `_MCP` para os testes injetarem fake via monkeypatch.
2. `git mv sinapse-sync.py → sinapse_sync.py` + shim análogo. `sinapse-api.py` `_get_sync_module()` agora faz `from scripts.services import sinapse_sync` (removido importlib.util import e o spec_from_file_location).
3. `validate_hive_mind.py` e `operational_benchmark.py`: trocado importlib inline do plugin hermes pelo adapter existente `from plugins.hermes import sinapse_memory as sm` (operational_benchmark precisou de `sys.path.insert(ROOT)` pois roda direto via systemd).
4. Testes ajustados (consequência do rename, pois carregavam o hifenizado por path e agora pegariam só o shim): test_sinapse_mcp.py, test_crdt.py, test_crdt_gaps.py, test_telemetry.py → todos passaram a `from scripts.services import sinapse_mcp/sinapse_sync`.

Decisão de escopo: hermes (plugins/hermes/sinapse-memory.py) NÃO renomeado agora — ~20 conftests/__init__ de teste referenciam o path hifenizado; adapter sinapse_memory.py mantido (ainda tem 1 importlib interno, aceito).

Verificação: py_compile OK; smoke import dos 3 módulos; MCP shim respondeu initialize JSON-RPC real pelo caminho registrado; 76 passed / 1 skipped na suíte afetada (mcp, api, sync, crdt, crdt_gaps, mcp_http, mcp_http_gaps, telemetry).

Gotcha: shims só re-exportam `main`; qualquer consumidor que carregue o arquivo hifenizado por path e espere outros símbolos (handle_request/TOOLS/_export) quebra — apontar para o módulo underscore.


---

## Auditoria de funcionalidade Hive-Mind: gaps em LightRAG/Graphiti, loop asyncio e backlog (2026-06-26)

Auditoria empírica (2026-06-26) do fluxo de arquitetura vivo. Núcleo 100% funcional (sinapse_query funde 7 backends, search_memories, temporal_search, REST :37702, claude-mem :37700, Graphify 3070 nós limpos, Dream Cycle roda). Gaps encontrados e correções:

1. **Estágio 3.5 nunca rodava (causa raiz)**: o push para Graphiti (push_neuron) e LightRAG (index_memory) estava DENTRO do loop de síntese de ambiguidades em dream_cycle.py — só dispara em conflitos P2P, raríssimos single-machine. Por isso vdb_entities.json/relationships.json = 49 bytes (vazios) e FalkorDB sem grafos, apesar de 5028 neurons. FIX: helper _push_neurons_to_graphs() chamado em _route_and_persist_project — todo neurônio persistido alimenta os dois grafos. Commit 4e458a6.

2. **Bug asyncio no Graphiti**: integrations/graphiti/client.py push_neuron/search_graph usavam asyncio.run() (cria+FECHA loop por chamada). O FalkorDriver no singleton _graphiti fica preso ao loop fechado → "Event loop is closed" a partir da 2ª chamada (exposto pelo push em lote). FIX: _run_async() com event loop dedicado persistente + reset do cliente se o loop fechar. Verificado: FalkorDB 0 grafos → grafo 'hive-mind' com 81 nós.

3. **Pendência (qualidade de modelo, não código)**: extração de entidades do Ollama emite "json: unsupported value: NaN" e "entity not found for edge relation" para alguns conteúdos. Modelos: GRAPHITI_LLM_MODEL=qwen2.5-coder:3b (modelo de CÓDIGO sendo usado p/ extração de prosa) + bge-m3. Resultado: search_graph e sinapse_rag_query ainda esparsos pois a busca opera sobre edges de entidades, e a maioria dos 81 nós são Episodic (texto cru). Provável fix: trocar o modelo de extração por um de prosa (qwen2.5:7b / granite3-dense:8b). NaN do bge-m3 costuma vir de input vazio/whitespace.

4. **test_sinapse_zettelkasten**: carregava o sinapse-zettelkasten.py hifenizado (shim só com main, pós codex rename) → faltavam _query_ollama/_sanitize_slug/_atomic_write. FIX: apontado p/ scripts.knowledge.sinapse_zettelkasten. 4/4 verdes.

5. **Backlog reenquadrado**: archived=0 (fila)=3708, mas 90% (3343) é pico histórico Jun 16-18, 84% projeto Hive-Mind (dev pesado). Jun 26 só 94. Não é throughput crônico — é rajada represada. Quarentena archived=2=437 espalhada (decision 165, discovery 119, learning 85), 242 sem projeto. Dream Cycle tem size gate por design. Drenar com catch-up runs ou triagem.

IMPORTANTE: MCP server e serviços systemd são processos de longa duração — não pegam mudanças de código até restart. Para LightRAG/Graphiti corrigidos valerem nas tools MCP, reiniciar sinapse-mcp e o próximo Dream Cycle.


---

## Embedder dim-0, LightRAG persistência e lentidão do Dream Cycle por NaN-retry (2026-06-27)

Continuação da auditoria (2026-06-27). Correções e diagnósticos:

COMMITS: 7937218 (embedder), 43b20a2 (lightrag estrutural), 532df74 (graphiti 8b), 4e458a6 (push+loop), 6cc8671 (P2).

ITEM 1 (MCP reload): há 8+ processos sinapse-mcp.py stdio (um por sessão de agente). NÃO podem ser mortos às cegas (quebra sessões ativas, inclusive a própria). Código novo no disco recarrega quando cada agente reconecta. Não há daemon systemd de MCP; o HTTP :37703 não roda.

ITEM 2 (embedder/LightRAG):
- CORRIGIDO e commitado: OllamaEmbedder.embed("") devolvia dim-0 (Ollama /api/embeddings com prompt vazio → {"embedding":[]}). Agora placeholder " " + 1 retry. Beneficia sqlite-vec/UMC/LightRAG. Reprodução: embed("")→dim0, embed("   ")→1024, concorrente 8x→sem 500 (concorrência NÃO era a causa).
- LightRAG estrutural corrigido em 4 camadas (loop dedicado, initialize_pipeline_status, persist via finalize_storages+reset, removido finalize-por-query). Extração passou a rodar (granite3-dense:8b extrai entidades válidas — provado). MAS persistência ainda falha: vdb_entities continua 49B mesmo com storage limpo. O 500 anterior vinha do estado poluído (36 docs PENDING/FAILED) no purge-on-resume; limpei o storage (backup .bak). Mesmo limpo, entidades não persistem — wiring extração→storage do LightRAG v1.5.4 com schema custom precisa de debug dedicado. Storage limpo em claude-mem/data/lightrag (backup .bak.*).

ITEM 3 (backlog): catch-up (janela 80) consolidou 28 neurônios em 6 projetos, pendentes 3580→3500, MAS levou 25min (route_and_persist 16min). Causa da lentidão: push Graphiti falha com NaN ("failed to encode response: json: unsupported value: NaN" do Ollama, provável bge-m3 sob pressão de memória com 8b+bge carregados) e _retry_with_backoff trata como transitório → 1+2+4s por neurônio. .env NÃO seta GRAPHITI_LLM_MODEL (default 8b do código em efeito). A 80/25min, drenar 3500 = ~18h — inviável como está.

RECOMENDAÇÕES FOCADAS (follow-up):
1. Graphiti: não retentar erro NaN (determinístico, não-transitório) — ir direto ao fallback. Acelera o Dream Cycle massivamente.
2. NaN sob carga: investigar Ollama (keep_alive/num parallel) ou separar modelos de chat vs embed para não competir memória.
3. LightRAG: debug dedicado do wiring extração→nano-vectordb (v1.5.4 + entity_extraction_use_json custom).
4. Backlog: após (1), drenar com janelas grandes; ou triar a rajada Jun 16-18 (84% Hive-Mind dev noise).


---

## LightRAG/Graphiti totalmente funcionais: schema field-names, modelo 2b na GPU e no-retry NaN (2026-06-27)

Resolução dos 3 follow-ups da auditoria (2026-06-27). Commits c958e32, 2a5fdfb, 64dcecb.

#1 — Dream Cycle lento (64dcecb): _retry_with_backoff do Graphiti retentava TODOS os erros (1+2+4s). O "json: unsupported value: NaN" do Ollama é determinístico → 7s desperdiçados/neurônio → route_and_persist ~16min. Novo _is_transient(): NaN/validação/schema falham na hora (→ fallback JSON-lines); só rede/timeout retenta. Verificado: NaN=1 tentativa/0s, ConnectionError=3/3s.

#2 — NaN sob carga (2a5fdfb): causa = GPU 12GB. No Dream Cycle carregam Dreamer 8b (~6GB) + extração Graphiti 8b (~5GB) + bge-m3 (~1.2GB) > 12GB → OOM → embeddings NaN. Trocado GRAPHITI_LLM_MODEL default 8b→granite3-dense:2b (~1.6GB, prosa): coexiste (6.2+1.6+1.2≈9GB<12GB). Verificado: 3/3 push sem NaN, Entity nodes 85→145, search_graph retorna edges. (qwen2.5-coder:3b de CÓDIGO falhava; 2b de PROSA funciona.)

#3 — LightRAG persistência (c958e32) — A DESCOBERTA CHAVE: o schema de extração e o prompt usavam entity_name/entity_type/entity_description e source_entity/etc. Mas o parser do LightRAG v1.5.4 (operate.py L770/838) lê entity_data.get("name"/"type"/"description") e rel_data.get("source"/"target"/"keywords"/"description"). Mismatch → name="" → "Empty entity name after sanitization" → "Completed merging: 0 entities" → vdb_entities 49B (vazio) eternamente. Renomeado para name/type/description e source/target/keywords/description. Verificado em storage limpo: "merging: 8 entities, 6 relations", vdb_entities 49B→67KB, query hybrid/local/naive/mix retorna contexto real. Pipeline end-to-end OK.

LIÇÕES TRANSVERSAIS:
- Ao integrar lib externa com schema custom, conferir os NOMES DE CAMPO exatos que o parser dela lê (não assumir entity_name; era name).
- GPU pequena (12GB): não empilhar múltiplos modelos grandes; preferir modelos pequenos de prosa que coexistam.
- Erro determinístico (NaN) nunca deve ser retentado com backoff.
- Storage do LightRAG acumula docs PENDING/FAILED que travam purge-on-resume; limpar quando poluído.
- granite3-dense:2b no gleaning-pass alucina entidades (Apple/iPhone); mitigado com instrução anti-alucinação no prompt, mas o passe extra ainda injeta ruído com modelos pequenos.

Storage LightRAG foi limpo (backups .bak.* em claude-mem/data/lightrag/). Próximo Dream Cycle real popula ambos os grafos. MCP server recarrega o código novo ao reconectar.


---

## Uso correto das buscas Sinapse: query hibrida vs temporal claude-mem (2026-06-27)

Em Hive-Mind, agentes devem usar sinapse_query como busca hibrida padrao para entender estado/historico/decisoes/codigo/vault. sinapse_temporal_search consulta a timeline textual do claude-mem global (~/.claude-mem) via termos curtos/exatos; resultados vazios com frases longas nao provam ausencia de memoria. Em caso de vazio, reduzir a consulta ou usar titulos retornados por sinapse_query.


---

## Descrições de tools Sinapse devem espelhar comportamento real e workflow claude-mem (2026-06-27)

Ao documentar busca no Hive-Mind, diferenciar claramente: sinapse_query é busca híbrida canônica; sinapse_temporal_search encapsula só a camada search/index textual do claude-mem global (/api/search), não o fluxo completo nativo search -> timeline -> get_observations. Tool descriptions devem ser auditadas contra handlers reais em scripts/services/sinapse_mcp.py e contra a versão instalada do claude-mem antes de orientar agentes.


---

## Sinapse deve preservar workflow search timeline get_observations do claude-mem (2026-06-27)

Ao encapsular claude-mem no sinapse-memory, expor apenas /api/search perde a etapa mais valiosa do backend: filtrar pelo índice, inspecionar janela cronológica e hidratar detalhes por IDs. O MCP Sinapse deve manter o fluxo search -> timeline -> get_observations via sinapse_temporal_search, sinapse_temporal_timeline e sinapse_temporal_get_observations, orientando agentes a nunca buscar detalhes antes de filtrar.


---

## Auditoria Sinapse deve comparar descricao MCP com integracao real (2026-06-27)

Na auditoria das tools Sinapse, comparar apenas a lista de tools não basta. A descrição precisa ser confrontada com o backend real: sinapse_health deve separar read_backends (UMC, NeuralMemory, sqlite-vec, claude-mem, Graphify, Graphiti, filesystem) de components (RTK etc.); register-mcp registra apenas o orquestrador sinapse-memory; wrappers como Screenpipe precisam aceitar os mesmos parâmetros prometidos pela tool MCP, como monitor em sinapse_capture_screen.


---

## RTK no Hive-Mind e componente de execucao hook-based, nao memoria (2026-06-27)

RTK (rtk-ai/rtk) funciona como proxy/filtro de comandos shell: `rtk rewrite` decide se um comando deve virar `rtk <cmd>` e os hooks/plugins aplicam essa mutacao antes da execução. No Hive-Mind, RTK deve ser descrito como componente de execução/tronco e aparecer em `components`, não em read_backends do sinapse_query. A integração Hermes usa `integrations/rtk/hooks/hermes/rtk-rewrite` e falha aberta se RTK não estiver no PATH.


---

## RTK no Hive-Mind e transversal por agente, nao backend de memoria (2026-06-27)

RTK (rtk-ai/rtk) deve ser documentado e configurado como camada transversal de execucao shell por agente/CLI via rtk init/start-rtk.sh. Hermes e apenas um alvo. RTK nao deve aparecer em hybrid_search.backends nem ser tratado como backend do sinapse_query; pode aparecer como component/camada de execucao.


---

## Como buscar no claude-mem sem se perder (sinapse_temporal_search) (2026-06-27)

Lição de método de busca temporal, validada em 2026-06-27 ao recuperar o trabalho do Codex sobre RTK.

PROBLEMA: `sinapse_temporal_search` retornou vazio e concluí erradamente que o claude-mem "não rastreou" a sessão do Codex. Na verdade rastreou tudo em detalhe (#14212 start-rtk.sh, #14213 sinapse.yaml backends→components, #14214 docs RTK). A falha foi minha query.

CAUSA: usei frases longas com termos misturados, ex.: "RTK start-rtk.sh rtk init --only agente" e "sinapse.yaml backends components" → 0 resultados. Isso viola a regra 4 do sinapse-agent-prompt.md: `sinapse_temporal_search` é ÍNDICE TEXTUAL do claude-mem, não orquestrador híbrido.

REGRA: 
1. Use 2–5 termos EXATOS que provavelmente estão no texto real. Comparação real: "hybrid_search components" ACHOU o #14213; "sinapse.yaml backends components" NÃO achou. "RTK sinapse_query" e "start-rtk.sh" funcionaram.
2. Fluxo nativo: search (acha IDs/títulos) → timeline(anchor=<id>) (janela cronológica) → get_observations(ids=[...]) (hidrata só os filtrados). Nunca hidrate antes de filtrar.
3. Resultado vazio NÃO prova ausência (regra 3): reduza a query, tente o título retornado por sinapse_query, ou volte ao sinapse_query para contexto consolidado.
4. Para "o que aconteceu no projeto" comece SEMPRE por sinapse_query (híbrido, tolerante a linguagem natural); use temporal_search só para achar a sessão/prompt bruto que originou aquilo.

BÔNUS: o hook PreToolUse ao ler um arquivo já injeta IDs de observações recentes daquele arquivo — atalho para pegar o anchor sem nem buscar.




---

## Embedding default Hive-Mind migrado para snowflake-arctic-embed2 (2026-06-27)

Decisao de 2026-06-27: Hive-Mind deve usar snowflake-arctic-embed2:latest como default de embeddings 1024d em core/database.py, LightRAG, Graphiti e NeuralMemory. A decisao veio de avaliacao no claude-mem: snowflake-arctic-embed2 teve 0 NaNs nos triggers testados e melhor separacao PT/EN vs conteudo nao relacionado que bge-m3/qwen3-embedding:0.6b. install.sh deve baixar snowflake-arctic-embed2. Ao migrar search_vec, pausar graphify watch para evitar database locked e religar depois.


---

## Desenho alvo do fluxo de preenchimento do cerebro Hive-Mind (2026-06-27)

Desenho alvo: captura bruta -> caixa de entrada sensorial -> triagem -> consolidacao -> memoria atomica -> indices especializados -> busca federada -> feedback. Cada camada deve ter contrato de escrita: observacao bruta, resumo de sessao, fato, decisao, aprendizado, preferencia, rationale, operational_fact, code_symbol, document_chunk. Vector search deve separar memoria consolidada, documentos, codigo e observacoes temporais para evitar mistura de granularidades.


---

## Hive-Mind deve nascer born-large na arquitetura de conhecimento (2026-06-27)

Decisao: nao tratar Milvus/RAGFlow/LlamaIndex como futuro distante. A arquitetura de conhecimento do Hive-Mind deve nascer local-first por operacao e born-large por arquitetura: VectorBackend com sqlite-vec local e Milvus producao, DocumentPipeline inspirado/compativel com RAGFlow, RetrievalRouter inspirado em LlamaIndex, Promotion Layer para discoveries/session summaries do claude-mem virarem neuronios atomicos. Documento criado em docs/11-knowledge-promotion-architecture.md e referenciado em docs/README.md e docs/01-architecture.md.


---

## Cadencia hierarquica de escrita do Hive-Mind (2026-06-27)

A arquitetura de conhecimento do Hive-Mind deve tratar session summaries, diario, semanal, mensal e anual como camadas hierarquicas. Sessao e diario podem usar modelos pequenos para compressao local; semanal deve usar modelo medio/forte para padroes; mensal/anual devem usar modelo forte ou batch offline para sintese estrategica. Nem todo resumo vira neuronio: promocao exige fonte, tipo canonico, parent_id/hash e regra explicita de decisao, learning, project_status, goal/task ou rationale.


---

## Plano K0-K10 para implementar arquitetura de conhecimento (2026-06-27)

O plano operacional da arquitetura de conhecimento do Hive-Mind foi documentado em docs/12-knowledge-implementation-plan.md. Ele define fases K0-K10, clones obrigatorios em integrations/ para RAGFlow/Milvus/LlamaIndex, embeddings locais snowflake-arctic-embed2:latest 1024d, modelos locais pequenos por papel, perfis local-min/local-full/prod-local e aceite com testes reais sem mocks para cada fase.


---

## RAGFlow Milvus LlamaIndex entram no fluxo de install e update (2026-06-27)

Para a arquitetura de conhecimento born-large, RAGFlow, Milvus e LlamaIndex precisam existir em duas camadas: pacotes Python na .venv (`ragflow-sdk`, `pymilvus`, `llama-index`) e vendors git em `integrations/` registrados no `config/components.lock.json`. O script `scripts/maintenance/integrations-update.sh` deve rodar `components.py bootstrap/update` para esses vendors e `uv lock --upgrade && uv sync --all-groups` para manter a .venv alinhada.


---

## Hive-Mind já tem merge/dedup e redação de PII; gaps reais são reranker, forget e eval (2026-06-27)

Verificado em código (2026-06-27) ao revisar docs/11 (arquitetura de conhecimento). NÃO reimplementar:

JÁ EXISTE — merge/dedup de memória:
- Dream Cycle Router decide append|create_new|merge por fato (core/schemas/dream_models.py:84, router_prompt.yaml/synthesis_prompt.yaml)
- Tabela `ambiguities` (umc_schema.sql:63 "Semantic Merge") + core/database.py:216 register_ambiguity + loop de síntese em dream_cycle.py:282-370 (status pending→synthesized). Disparado por conflitos sync-conflict do Syncthing e mismatch de hash (audit_memory.py:181)
- Dedup de learning por título exato em core/memory/writers.py:168
- Dedup cross-backend na query em core/memory/context_fusion.py:164 (_fuse_contexts)

JÁ EXISTE — PII/segredo:
- core/redactor.py redige token (sk-/ghp_/JWT/Bearer/GOCSPX), email, IP, path, chave, CPF/CNPJ, telefone. Chamado no EXPORT federado (sinapse-api.py:376 redact_neuron). Filosofia: neurônio local nunca é modificado; redação só ao sair pra federação. `vault.encrypted_secret` para segredos.
- IMPORTANTE: promoção pra vetor NÃO redige (raw local por design). Só o export.

GAPS REAIS (viraram contrato em docs/11 §17, ligados a docs/12 K7/K8/K9):
1. Reranker (§17.1): context_fusion dedupa e TRUNCA por ordem de backend, não reordena por relevância à query. Falta cross-encoder pequeno opcional entre fusão e retorno do RetrievalRouter (K7 task 8).
2. Esquecimento intencional (§17.2): regra é "nunca deletar"; falta forget()/tombstone CRDT-safe + poda de orphan_vectors (hoje só medido). K8 task 6.
3. Eval de recuperação (§17.3): mede cobertura, não qualidade. Falta golden set tests/real/golden_retrieval.jsonl + precision/recall@k como gate. K9 task 7.

Refinamento (não subsistema faltando): dedup hoje é por chave exata (título/hash/id); duplicata semântica por similaridade de embedding seria refinamento do que já existe.


---

## Mapa real ferramenta→área do cérebro: escrita cobre 8 áreas; leitura (router) não roteia ínsula/tronco/diencéfalo (2026-06-28)

Verificado em código (2026-06-28). Correção: eu havia dito que "ínsula não é preenchida" — ERRADO, era só ausência no docs/11 §3. O sistema preenche as 8 áreas.

MAPA ESCRITA (ferramenta→área, código real):
- Temporal (neuronios): dream_cycle (Distiller→Validator→Router) ← claude_mem_bridge; drift_detector(→arquivo); topic_consolidator; alias_miner. Índices: UMC vec/fts, Graphiti, LightRAG.
- Frontal: decision_promoter, work_tracker, decision_staleness, MCP save_decision/plan_goal (goals).
- Parietal: capture/*, document_ingest.
- Occipital: visual_capture, Graphify, dream estágio visual.
- Ínsula: health_dashboard, alert_dispatcher, review_writer (→saude); conflict_detector, topic_consolidator (→conflitos); ambiguities (síntese dialética).
- Cerebelo: session_consolidator, daily_writer, weekly_synthesizer, pattern_distiller.
- Diencéfalo: sector_classifier, generate_mocs (→setores).
- Tronco: modelos/ (templates), meta/ — mais estático que promovido.

CLAUDE-MEM FLOW: scripts/services/claude_mem_bridge.py lê claude-mem.db read-only, preserva project, idempotente cm-{content_hash}+INSERT OR IGNORE → hive_mind.observations(archived=0) → dream_cycle promove → neurons + ambiguities + push Graphiti/LightRAG. Importa tabela `observations` (com type/narrative); discoveries/session_summaries separados é o que K4 deve estender.

GAP REAL (leitura, não escrita): RetrievalRouter §11/K7 NÃO tem intent para ínsula (saúde/autoconsciência), tronco (config/operacional) nem diencéfalo (setor). Áreas escritas mas não roteáveis. Adicionados intents self_state/operational/sector no docs/11 §11 + docs/12 K7.

DRIFTS corrigidos nesta sessão: docs/11 §3 (sem ínsula→adicionada + ferramentas reais), §8 (faltava summary_vectors), docs/12 K4 (mandava "criar" o bridge que já existe), K10 (mandava clonar wrapper).


---

## Auditoria frente-K (2026-06-28): substrato verde (457 unit), frente K 0% implementada, 8 omissões técnicas no plano (2026-06-28)

Auditoria técnica de docs/11+12 cruzada com código e testes (2026-06-28).

CONFORMIDADE VERIFICADA:
- tests/unit: 457 passed, 3 skipped (56s) → substrato existente sólido.
- tests/integration: 101 skipped (Ollama/FalkorDB/Milvus offline no ambiente).
- Frente K = 0% implementada: 15/15 arquivos-alvo FALTAM (vector_backend, knowledge/*, retrieval/*, document_pipeline, knowledge_health, monthly/yearly, integrations/milvus|ragflow). tests/real/ não existe. workspace_id ausente no schema. Coleções §8 = 2/7 reais (search_vec + vec_observations; este vive em claude-mem.db via worker). deps pinadas OK.

8 OMISSÕES adicionadas ao docs/12:
- B1 (ALTO): ensure_migrations faz ALTER puro (database.py:318-393); tabela CRR exige crsql_begin_alter/commit_alter (zero ocorrências no código). → helper alter_table_crr_safe() em K0 task7.
- B2 (ALTO): VectorBackend "único" cruza 2 bancos — observation_vectors=vec_observations vive em claude-mem.db (worker), não hive_mind.db. → K2 task7 mapear coleção→(DB,processo).
- B3 (ALTO): tests/real (K9) é gate de TODAS as fases mas estava por último → esqueleto K9 vira pré-requisito de K0 (§6/§10).
- B4 (MÉDIO): K3 são N refactors dos promotores existentes (decision_promoter etc. escrevem MD direto), não 2 arquivos → K3 task8.
- B5 (MÉDIO): backfill das 5 coleções novas sem fase + métrica *_vectorized_pct por coleção → K2 task8 + K8 metric.
- B6 (MÉDIO): colunas origin_instance/origin_signature (§18.3) e embedding_model/dim (§18.4) não nascem no schema → mesma migração CRR-safe (K0 task7).
- B7 (MÉDIO): RetrievalRouter sem mecanismo de classificação de intent → K7 task9 (topic_router local + fallback hybrid).
- B8 (MÉDIO): migração sem backup obrigatório → backup hive_mind.db.pre-workspace no K0 task7.

Sequenciamento corrigido: esqueleto K9 + migração CRR-safe (backup) ANTES de qualquer fase. B1/B2/B3 travam a 1ª fase se ignorados.


---

## Frente K iniciada (2026-06-28): K9-esqueleto + K0 migração CRR-safe entregues e verdes (2026-06-28)

Primeiro corte de implementação da frente de conhecimento (docs/12), iniciado em 2026-06-28.

ENTREGUE E VERDE:
K9-esqueleto (gate B3):
- pytest.ini: markers `real` + `requires_service`.
- tests/real/: __init__.py, conftest.py (fixtures real_db = init_db em tmp + ensure_migrations; ollama_or_skip = pula se Ollama offline), README.md.
- tests/run_real_knowledge.sh (executável, -m real, pula requires_service offline).
- tests/real/test_embedding_stack.py: dim 1024 (Ollama up confirmou), modelo unificado (worker source check), colunas da migração. 3 passed.

K0 migração CRR-safe (B1/B6):
- core/database.py: helpers _table_is_crr (detecta shadow __crsql_clock), alter_table_crr_safe (envolve em crsql_begin_alter/commit_alter se CRR, senão ALTER puro), migrate_workspace_and_federation (workspace_id NOT NULL DEFAULT 'default' nas 9 tabelas _WORKSPACE_TABLES + origin_instance/origin_signature/embedding_model/embedding_dim em neurons + índices idx_<t>_workspace). Chamada dentro de ensure_migrations antes do commit, try/except OperationalError.
- umc_schema.sql + umc_schema_crr.sql: 5 colunas novas no CREATE de neurons (neurons agora 17 colunas).
- tests/unit/test_workspace_migration.py: 7 testes (colunas, default, federação, idempotência, tabela ausente, alter plain, índice).

VERIFICAÇÃO: unit 464 passed/3 skipped; real 3 passed; schemas parseiam (neurons 17 cols). Nada quebrou.

DECISÃO de arquitetura: migração (ensure_migrations) é a fonte única para as 8 tabelas além de neurons — mesmo padrão que archived/uuid/visibility já seguem — evita drift de schema duplicado em 9 CREATEs. Só neurons ganhou colunas no schema-file (tabela quente + federação/embedding só aplicam a ela).

PENDENTE no corte: K0 tasks 2-6, backup explícito B8 (hive_mind.db.pre-workspace antes da migração), K9 tasks 3/6/7 (fixtures Milvus/claude-mem, golden set §17.3). Próximo: K2 VectorBackend.


---

## Frente K docs/12: wrappers nao entram em components.lock (2026-06-28)

Revisao 2026-06-28: a decisao atual para a frente de conhecimento substitui a ideia anterior de clonar RAGFlow/Milvus/LlamaIndex como vendors git. Contrato correto: components.lock.json fica apenas para componentes source-built/patchados pelo instalador (graphify, neural-memory, rtk). Milvus e RAGFlow entram como wrappers/compose+SDK em integrations/; LlamaIndex entra como dependencia pip. Docs e scripts devem tratar components.lock como contrato negativo para esses wrappers, para impedir agentes futuros de reintroduzirem clones.


---

## Frente K docs alinhados aos testes reais K0/K9 (2026-06-28)

Em 2026-06-28, docs/11 e docs/12 foram ajustados para refletir os testes reais atuais da Frente K: embedding snowflake-arctic-embed2 1024d validado, migração workspace/federação com backup coberta por unit 9 passed e suíte real 3 passed. O plano agora registra três gates pendentes antes de K1/K2: modo --no-components/--wrappers-only no integrations-update, skip requires_service por registry/fixture de serviço, e strict/health fail-closed para falha estrutural de migração em install/CI/maquina zerada.


---

## Frente K K0-K1-K9 gates implementados e run_all verde (2026-06-28)

Em 2026-06-28, a Frente K avançou no recorte base: K9 ganhou service registry em tests/real/service_registry.py para requires_service nomeado (ollama, milvus, falkordb, claude_mem, ragflow), K1 ganhou --no-components e --wrappers-only em scripts/maintenance/integrations-update.sh para evitar repin acidental de components.lock, e K0 ganhou HIVE_STRICT_MIGRATIONS=1 para falhar fechado em migrate_workspace_and_federation. Também foram corrigidos testes de integração Graphiti/hybrid para contratos atuais. Validação final: ./tests/run_all.sh verde com Smoke 19 passed, Unit 473 passed/3 skipped, Integration 104 passed/4 skipped, E2E 22 passed.


---

## Frente K K0 migracao estrutural falha fechado por padrao (2026-06-28)

Correcao 2026-06-28: K0 nao usa mais HIVE_STRICT_MIGRATIONS como opt-in. A migracao workspace/federacao em core/database.py falha fechado por padrao se migrate_workspace_and_federation falhar. O unico bypass e HIVE_ALLOW_DEFERRED_MIGRATIONS=1, apenas para diagnostico de DB legado, com log visivel. Docs/11 e docs/12 foram atualizados. Validado com tests/unit/test_workspace_migration.py + tests/unit/test_database.py: 31 passed.


---

## Frente K auditoria CRR-safe e run_all verde (2026-06-28) (2026-06-28)

Auditoria da implementação K0/K1/K9 encontrou divergência real: ensure_migrations ainda tinha ADD COLUMN legado direto, incompatível com tabelas CRR. Correção: centralizar todos ADD COLUMN em add_column_if_missing -> alter_table_crr_safe, exigir DEFAULT NULL explícito em opcionais, manter migração workspace/federação fail-closed por padrão e bypass apenas via HIVE_ALLOW_DEFERRED_MIGRATIONS=1. Validação: ./tests/run_all.sh verde (Smoke 19, Unit 474/3 skipped, Integration 104/4 skipped, E2E 22), testes reais 3 passed e registry 5 passed.


---

## Frente K1 K2 imports wrappers e VectorBackend Milvus E2E (2026-06-28) (2026-06-28)

K1: wrappers integrations/milvus e integrations/ragflow criados sem clone de monorepo, com client.py, README, docker-compose.yml pinado por digest e assert_health(strict=...). pyproject/uv.lock contem pymilvus, ragflow-sdk e llama-index; imports reais no .venv passaram. K2: SQLiteVecBackend real para memory_vectors e MilvusBackend real com pymilvus.MilvusClient, schema explícito, metadados canonicos obrigatorios, filtro workspace_id e E2E contra Milvus Docker. Validação: tests/real 13 passed; K2 sqlite+Milvus 6 passed; ./tests/run_all.sh verde (Smoke 19, Unit 474/3 skipped, Integration 104/4 skipped, E2E 22). Pendentes K2: sync local->Milvus e backfill por coleção.


---

## K2 sync/backfill memory_vectors para Milvus com idempotencia (2026-06-28) (2026-06-28)

Implementado core/vector_sync.py para sincronizar a coleção viva memory_vectors de hive_mind.db/search_vec para Milvus via MilvusBackend. O sync hidrata metadados canônicos de neurons, decodifica vetores 1024d, usa idempotência por (id, hash, workspace_id), reporta scanned/upserted/skipped/failed/errors e não oculta falhas por linha. Teste real tests/real/test_vector_sync_milvus.py cobre primeira carga, reexecução idempotente, update por hash e falha real rejeitada pelo Milvus. Validação: ./tests/run_real_knowledge.sh 15 passed; ./tests/run_all.sh verde (Smoke 19, Unit 474/3 skipped, Integration 104/4 skipped, E2E 22). Pendentes: sync/backfill de observation/document/code/visual/graph/summary vectors.


---

## K2 observation_vectors usa claude-mem read-only local e sync Milvus (2026-06-28)

No Hive-Mind K2, observation_vectors nao vive em hive_mind.db: a rota local correta consulta claude-mem.db/vec_observations com sqlite-vec carregado e trata a colecao como read-only, porque a escrita canonica pertence ao sqlite-vec-worker. Para producao, core/vector_sync.py exporta vec_observations para Milvus usando ids obs-<id>, metadados canonicos parent_id/parent_type/brain_lobe/knowledge_type/project/source_uri/hash/valid_at/workspace_id e idempotencia por (id, hash, workspace_id). Aceite real em 2026-06-28: tests/real/test_observation_vectors.py 2 passed, run_real_knowledge 17 passed, run_all verde.


---

## K2 E2E live bounded para sync vetorial (2026-06-28)

Para validar K2 com dados reais sem risco operacional, o teste E2E deve ler hive_mind.db e ~/.claude-mem/claude-mem.db em modo read-only, usar limit de lote nos syncs vetoriais e escrever apenas em colecoes Milvus temporarias com prefixo randomico. Em 2026-06-28, core/vector_sync.py ganhou limit opcional em sync_memory_vectors_to_milvus e sync_observation_vectors_to_milvus, preservando default full backfill. tests/real/test_vector_sync_live_e2e.py validou importacoes/sync E2E com bancos reais, Milvus real e idempotencia; run_real_knowledge fechou 18 passed e run_all fechou verde.


---

## K1 wrappers validam compose e digest no install/update (2026-06-28)

No Hive-Mind K1, Milvus e RAGFlow sao wrappers Docker/SDK, nao clones git. Para evitar regressao de supply chain e setup em maquina nova, scripts/setup/verify_wrappers.py valida os docker-compose.yml reais via docker compose config --quiet e exige imagem pinada por digest @sha256:<64 hex>. install.sh chama esse gate apos uv sync/imports, e scripts/maintenance/integrations-update.sh chama o mesmo gate no fluxo --wrappers-only/normal. Aceite real em 2026-06-28: tests/real/test_integration_wrappers.py 7 passed, verify_wrappers.py OK para Milvus/RAGFlow, integrations-update.sh --wrappers-only --no-pip OK, run_real_knowledge 21 passed, run_all verde.
