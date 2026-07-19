# Hive-Mind Implementation Control

Página de entrada do controle de implementação. Este diretório NÃO é uma spec
concorrente: a arquitetura aprovada continua sendo
[specs/control-plane-redesign-v2.md](../../specs/control-plane-redesign-v2.md).
Aqui registra-se execução, evidência, desvios e decisões posteriores.

## Fonte de verdade

| Assunto | Documento |
|---|---|
| Arquitetura | [specs/control-plane-redesign-v2.md](../../specs/control-plane-redesign-v2.md) |
| Identidade de projeto (design) | [docs/superpowers/specs/2026-07-17-canonical-project-identity-and-windows-capture-design.md](../superpowers/specs/2026-07-17-canonical-project-identity-and-windows-capture-design.md) |
| Identidade de projeto (plano) | [docs/superpowers/plans/2026-07-17-canonical-project-identity-and-windows-capture.md](../superpowers/plans/2026-07-17-canonical-project-identity-and-windows-capture.md) |
| Plano de execução | [MASTER-PLAN.md](MASTER-PLAN.md) |
| Estado atual (só o HEAD) | [CURRENT-STATE.md](CURRENT-STATE.md) |
| Critérios de aceite | [ACCEPTANCE-MATRIX.md](ACCEPTANCE-MATRIX.md) |
| Entregas (append-only) | [DELIVERY-LEDGER.md](DELIVERY-LEDGER.md) |
| Decisões arquiteturais | [ARCHITECTURE-DECISIONS.md](ARCHITECTURE-DECISIONS.md) |
| Documentação afetada | [DOCUMENTATION-MAP.md](DOCUMENTATION-MAP.md) |
| Template de entrega | [templates/DELIVERY-TEMPLATE.md](templates/DELIVERY-TEMPLATE.md) |

## Regras

1. Nenhuma fase inicia sem entrada no plano.
2. Nenhuma entrega inicia sem registro no ledger.
3. Nenhuma entrega termina sem evidência.
4. Nenhum item vira DONE apenas com teste unitário.
5. Teste mockado não é evidência operacional.
6. Status BLOCKED exige causa-raiz e próximo passo.
7. Toda mudança de comportamento atualiza documentação de produto
   (ver [DOCUMENTATION-MAP.md](DOCUMENTATION-MAP.md)).
8. Toda decisão arquitetural relevante recebe ADR.
9. O ledger é append-only — entregas passadas não são reescritas.
10. O estado atual deve refletir o HEAD, não intenção futura.

Toda mensagem de commit de uma entrega cita o ID no corpo ou trailer:

```
Delivery: D00X
```

## Estados permitidos

```
NOT_STARTED
IN_PROGRESS
PARTIAL
BLOCKED
FAILED
DONE
SUPERSEDED
```

Estados vagos são proibidos: "quase pronto", "aparentemente funcionando",
"deve funcionar", "provavelmente correto".

## Ciclo de uma entrega

Antes de alterar código:

1. criar entrada no [DELIVERY-LEDGER.md](DELIVERY-LEDGER.md);
2. marcar fase e entrega IN_PROGRESS;
3. registrar HEAD inicial;
4. registrar arquivos planejados;
5. registrar testes planejados;
6. registrar documentação afetada.

Depois de alterar código:

1. preencher arquivos realmente alterados;
2. preencher testes realmente executados;
3. anexar evidência;
4. atualizar [CURRENT-STATE.md](CURRENT-STATE.md);
5. atualizar [ACCEPTANCE-MATRIX.md](ACCEPTANCE-MATRIX.md);
6. atualizar documentação do produto;
7. registrar commits;
8. registrar HEAD final;
9. registrar pendências;
10. somente então marcar DONE.

Uma entrega NÃO pode ser DONE quando:

- a worktree contém mudanças inexplicadas;
- teste obrigatório falha;
- teste obrigatório foi pulado;
- a prova é somente mock;
- documentação não foi atualizada;
- rollback não foi definido;
- runtime real não foi testado quando exigido;
- critério da matriz continua PARTIAL/BLOCKED.
