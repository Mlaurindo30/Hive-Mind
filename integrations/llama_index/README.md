# LlamaIndex Adapter

K7 uses LlamaIndex only as an optional adapter surface for retriever utilities
such as reranking and future workflow experiments.

The canonical routing logic stays in `core/retrieval/router.py`. This wrapper
must not hide the route decision, citations, or backend provenance.

Runtime:

- package dependency: `llama-index` from `pyproject.toml`;
- health: `integrations.llama_index.client.assert_health()`;
- reranker: enabled only when `HIVE_RETRIEVAL_RERANKER` is set.
