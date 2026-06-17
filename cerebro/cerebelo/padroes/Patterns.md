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
