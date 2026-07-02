# 🧠 Hive-Mind Dashboard

Este painel exibe a inteligência coletiva do projeto Hive-Mind em tempo real, consultando o banco de dados unificado SQLite.

## 📊 Status do Cérebro
| Métrica | Valor |
| :--- | :--- |
| **Neurônios (Nós)** | `sqlite-query: SELECT count(*) FROM neurons` |
| **Sinapses (Arestas)** | `sqlite-query: SELECT count(*) FROM synapses` |
| **Observações (Logs)** | `sqlite-query: SELECT count(*) FROM observations` |
| **Vetores Indexados** | `sqlite-query: SELECT count(*) FROM search_vec` |

---

## 🕒 Últimas Atividades (Timeline)
```sqlite-query
SELECT created_at, type, title, content 
FROM observations 
ORDER BY created_at DESC 
LIMIT 10
```

---

## ⚡ Otimizações de Terminal (RTK)
```sqlite-query
SELECT created_at, title, content 
FROM observations 
WHERE type = 'execution' 
ORDER BY created_at DESC 
LIMIT 5
```

---

## 🕸️ Neurônios Órfãos (Sem conexões)
```sqlite-query
SELECT label, type, source_file 
FROM neurons 
WHERE id NOT IN (SELECT source_id FROM synapses) 
  AND id NOT IN (SELECT target_id FROM synapses)
LIMIT 5
```

---

## 🤖 Sugestões de Links Semânticos (Top Similarity)
> Use este bloco para encontrar notas relacionadas via IA.
```sqlite-query
SELECT n.label as 'Nota', n.type as 'Tipo'
FROM search_vec v
JOIN neurons n ON v.neuron_id = n.id
ORDER BY distance
LIMIT 5
```

---
*Este dashboard requer o plugin **SQLite DB Viewer** configurado para ler o arquivo `hive_mind.db` na raiz do projeto.*
