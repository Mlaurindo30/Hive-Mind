# 🔐 Segurança do Hive-Mind Cloud

Seu cérebro de IA agora pode ser acessado remotamente de forma segura.

## 🚀 Como expor para a Nuvem
Eu sugiro usar o **Tailscale Funnel** ou **Cloudflare Tunnels** para expor a porta `37702`.

### Passo a Passo (Tailscale - Sugerido):
1. Instale o Tailscale no seu PC e na VPS.
2. No seu PC, rode: `tailscale serve 37702`.
3. Sua API estará disponível em: `http://seu-pc.tailscale-ip:37702/api/v1/health`.

## 🔑 Autenticação
Todos os endpoints (exceto health) exigem o header:
`Authorization: Bearer <SUA_CHAVE_AQUI>`

A chave é configurada via variável de ambiente:
`HIVE_MIND_API_KEY`

## 📡 Endpoints Disponíveis
- `POST /api/v1/query`: Consulta híbrida (Texto + Vetores).
- `POST /api/v1/observations`: Grava logs/decisões remotas no seu banco local.
- `GET /api/v1/semantic/related`: Recomendação de notas (usado pelo Obsidian).

---
*Mantenha sua `HIVE_MIND_API_KEY` em segredo absoluto.*
