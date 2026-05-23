     1|---
     2|description: "Vault entry point — embedded dashboards, quick links, current focus"
     3|tags:
     4|  - index
     5|---
     6|
     7|# Home
     8|
     9|## Current Focus
    10|
    11|![[North Star#Current Focus]]
    12|
    13|## Active Work
    14|
    15|![[Work Dashboard.base#Active Work]]
    16|
    17|## Incidents
    18|
    19|![[Incidents.base#All Incidents]]
    20|
    21|## Quick Links
    22|
    23|- [[Index|Work Notes]] | [[People & Context]] | [[Brag Doc]]
    24|- [[Memories]] | [[North Star]] | [[Skills]]
    25|
    26|## Recent 1:1s
    27|
    28|![[1-1 History.base#All 1:1s]]
    29|
    30|## People
    31|
    32|![[People Directory.base#By Team]]
    33|

---

     1|     1|# Bem-vindo ao seu Segundo Cérebro
     2|     2|
     3|     3|Você acabou de adquirir um sistema de memória persistente para o Claude Code. Ele vai lembrar quem você é, o que você faz, seus projetos, suas decisões e seus aprendizados - tudo isso entre sessões, sem precisar explicar tudo de novo.
     4|     4|
     5|     5|---
     6|     6|
     7|     7|## O que você comprou
     8|     8|
     9|     9|| Componente | O que faz |
    10|    10||------------|-----------|
    11|    11|| **CLAUDE.md** | A alma do cérebro - define como o Claude pensa, opera e protege seus dados |
    12|    12|| **8 slash commands** | Comandos prontos que executam tarefas complexas com uma linha |
    13|    13|| **Templates de knowledge** | Perguntas-guia para você preencher e o cérebro te conhecer |
    14|    14|| **Módulo negócios** | Templates e comandos extras para quem usa o cérebro para gerenciar um negócio (opcional) |
    15|    15|| **4 prompts de setup** | Os mesmos prompts do vídeo + complementares para configurar tudo |
    16|    16|| **Guias completos** | Instalação passo a passo e personalização por perfil |
    17|    17|| **Suporte via IA** | Um prompt que transforma qualquer LLM num assistente que conhece o kit inteiro |
    18|    18|
    19|    19|---
    20|    20|
    21|    21|## Setup em 3 passos
    22|    22|
    23|    23|### Passo 1: Instalar e abrir
    24|    24|
    25|    25|Siga o [[guia-instalacao]] para instalar o Obsidian e o Claude Code (se ainda não tiver), e abrir o vault.
    26|    26|
    27|    27|**Se já tem Obsidian e Claude Code instalados:** Basta abrir esta pasta como vault no Obsidian e rodar `claude` no terminal dentro dela.
    28|    28|
    29|    29|### Passo 2: Personalizar
    30|    30|
    31|    31|Siga o [[guia-personalizacao]] para preencher sua identidade no CLAUDE.md e alimentar o cérebro com seus dados.
    32|    32|
    33|    33|**Tempo estimado:** 15-30 minutos para o setup básico. Você pode ir completando com o tempo.
    34|    34|
    35|    35|### Passo 3: Testar
    36|    36|
    37|    37|Rode o seu primeiro comando no Claude Code:
    38|    38|
    39|    39|```
    40|    40|/daily-briefing
    41|    41|```
    42|    42|
    43|    43|Se tudo estiver configurado, o cérebro vai gerar um briefing do seu dia com base no que você preencheu.
    44|    44|
    45|    45|---
    46|    46|
    47|    47|## Seus comandos
    48|    48|
    49|    49|### Universais (todo mundo usa)
    50|    50|
    51|    51|| Comando | O que faz |
    52|    52||---------|-----------|
    53|    53|| `/daily-briefing` | Gera o briefing do dia: estado atual, projetos, prioridades, próximos passos |
    54|    54|| `/end-session` | Fecha a sessão: salva o que foi feito, decisões, aprendizados. **O cérebro evolui a cada uso.** |
    55|    55|| `/braindump [texto]` | Captura uma ideia ou pensamento e conecta ao vault automaticamente |
    56|    56|| `/weekly-review` | Revisão semanal: o que avançou, o que travou, ajustes de prioridade |
    57|    57|
    58|    58|### Semi-universal
    59|    59|
    60|    60|| Comando | O que faz |
    61|    61||---------|-----------|
    62|    62|| `/content-idea` | Gera ideias de conteúdo baseadas no seu perfil, objetivos e posicionamento |
    63|    63|
    64|    64|### Módulo negócios (opcional)
    65|    65|
    66|    66|| Comando | O que faz |
    67|    67||---------|-----------|
    68|    68|| `/prospect-research [nome]` | Pesquisa um prospect e cria nota no pipeline |
    69|    69|| `/pipeline` | Dashboard completo do seu funil com métricas e alertas |
    70|    70|| `/proposal-generator [nome]` | Gera proposta personalizada baseada nos dados do vault |
    71|    71|
    72|    72|---
    73|    73|
    74|    74|## Precisa de ajuda?
    75|    75|
    76|    76|Abra o arquivo [[prompt-suporte-llm]] e copie o conteúdo inteiro como primeira mensagem num chat novo do Claude (web) ou ChatGPT. Você terá um assistente que conhece o kit inteiro e pode te ajudar com qualquer dúvida - personalização, troubleshooting, criação de novos comandos, tudo.
    77|    77|
    78|    78|---
    79|    79|
    80|    80|## Estrutura do vault
    81|    81|
    82|    82|```
    83|    83|CLAUDE.md                    ← Alma do cérebro (personalizar primeiro)
    84|    84|START-HERE.md                ← Você está aqui
    85|    85|guia-instalacao.md           ← Setup passo a passo
    86|    86|guia-personalizacao.md       ← Como adaptar ao seu uso
    87|    87|prompt-suporte-llm.md        ← Suporte via IA
    88|    88|
    89|    89|_prompts/                    ← Prompts usados no vídeo
    90|    90|_memory/                     ← Estado atual (atualizado automaticamente)
    91|    91|_knowledge/                  ← Sua base de conhecimento
    92|    92|  business/                  ← Módulo negócios (opcional)
    93|    93|_pipeline/                   ← Itens ativos do seu funil
    94|    94|_learnings/                  ← Aprendizados acumulados
    95|    95|_decisions/                  ← Registro de decisões
    96|    96|_sessions/                   ← Braindumps e sessões
    97|    97|.claude/commands/             ← Os 8 slash commands
    98|    98|```
    99|    99|
   100|   100|---
   101|   101|
   102|   102|> **Dica:** O segundo cérebro fica mais inteligente com o uso. Cada vez que você roda `/end-session`, ele consolida o que aconteceu e se prepara melhor para a próxima sessão. Use consistentemente e em poucas semanas ele vai conhecer seu contexto melhor do que qualquer chat novo.
   103|   103|