# Rollback evidence — 2026-07-27

Status: rollback testável provado para os artefatos locais preservados

## Objetivo

Demonstrar, com evidência prática, que o archive/backup atual já sustenta
rollback testável sem tocar no runtime ativo `D:\Hive-Mind`.

## Evidência 1 — bundle Git externo verificável

Bundle validado:

- `D:\Hive-Mind-Archive\20260727-141434\hive-mind-all-refs.bundle`

Comando:

- `git -C D:\Hive-Mind bundle verify D:\Hive-Mind-Archive\20260727-141434\hive-mind-all-refs.bundle`

Resultado:

- bundle contém `57` refs
- `The bundle records a complete history.`
- `...hive-mind-all-refs.bundle is okay`

Leitura:

- o histórico Git preservado no archive externo está íntegro o suficiente para
  servir como ponto de recuperação reconstituível.

## Evidência 2 — manifesto de backup verificável

Manifesto:

- `D:\Hive-Mind\backups\backup-manifest-2026-07-27.json`

Artefato declarado:

- `D:\Hive-Mind\backups\hive_mind.2026-07-27.db`
- `sha256 = 515d704d744d7a392d0b100561e3a4f9a3b0e25592c4b9205bc8423eb578ceea`
- `size_bytes = 67375104`

Comando:

- `hive-mind backup verify --manifest D:\Hive-Mind\backups\backup-manifest-2026-07-27.json --json`

Resultado:

- `ok = true`
- check `hive_mind = ok`

Leitura:

- o backup SQLite declarado no manifesto confere com a evidência física no
  disco.

## Evidência 3 — restore em diretório alternativo

Restore executado para:

- `D:\Hive-Mind-Archive\20260727-141434\restore-check\hive_mind.db`

Comando:

- `hive-mind backup restore --manifest D:\Hive-Mind\backups\backup-manifest-2026-07-27.json --into D:\Hive-Mind-Archive\20260727-141434\restore-check --json`

Resultado:

- `ok = true`
- arquivo restaurado:
  - path `D:\Hive-Mind-Archive\20260727-141434\restore-check\hive_mind.db`
  - `Length = 67375104`
  - `SHA-256 = 515D704D744D7A392D0B100561E3A4F9A3B0E25592C4B9205BC8423EB578CEEA`

Comparação:

- hash do restore = hash do manifesto
- tamanho do restore = tamanho do manifesto

Leitura:

- não é apenas “backup existente”; há restauração prática bem-sucedida em
  destino alternativo e conferência por hash.

## Limite desta prova

Esta evidência prova:

- rollback testável para o banco SQLite local preservado;
- integridade do bundle Git externo;
- possibilidade prática de restaurar sem tocar no runtime ativo.

Esta evidência não prova, sozinha:

- snapshot coordenado de Milvus/FalkorDB/RAGFlow;
- restauração integral de todos os componentes externos do ecossistema;
- replay operacional completo do ambiente inteiro.

## Conclusão

No estado atual de 27 de julho de 2026, o critério “archive externo
verificável” está fortemente provado e o critério “rollback testável” tem
evidência prática suficiente pelo menos para:

- histórico Git preservado em bundle verificável;
- backup SQLite validado por manifesto;
- restore alternativo com hash idêntico.
