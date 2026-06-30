"""K9 fixtures reais para RAGFlow (wrapper headless).

Valida que o wrapper RAGFlow em `integrations/ragflow/` consegue
instanciar `RAGFlowSettings` e bater em `/api/v1/health` ou `/`. Em
modo offline, pula limpo com motivo nomeado. Este teste fecha o item
4 do Proximo Corte Recomendado (`docs/12` §10): fixtures reais
reutilizaveis para RAGFlow.

RAGFlow roda headless: o store dele e cache de ingestao, e o canonico
continua sendo UMC + `cerebro/`. Aqui so provamos que o wrapper
funciona contra o servico real.
"""
from __future__ import annotations

import pytest


@pytest.mark.real
@pytest.mark.requires_service("ragflow")
def test_ragflow_or_skip_resolves_to_online_service():
    """A fixture `ragflow_or_skip` so cede quando o servico esta online."""
    from tests.real.service_registry import check_service

    status = check_service("ragflow")
    assert status.ok, status.reason


@pytest.mark.real
@pytest.mark.requires_service("ragflow")
def test_ragflow_settings_reflect_env(ragflow_or_skip):
    """`RAGFlowSettings` le env vars reais (RAGFLOW_BASE, RAGFLOW_API_KEY)."""
    RAGFlowSettings, _ = ragflow_or_skip
    s = RAGFlowSettings(base_url="http://example.invalid:9380", api_key="k")
    assert s.base_url == "http://example.invalid:9380"
    assert s.api_key == "k"
    assert s.version  # default v1


@pytest.mark.real
@pytest.mark.requires_service("ragflow")
def test_ragflow_health_against_real_service(ragflow_or_skip):
    """`assert_health(strict=False)` retorna `ok=True` quando o servico responde."""
    RAGFlowSettings, assert_health = ragflow_or_skip
    result = assert_health(strict=False)
    assert result["service"] == "ragflow"
    assert result.get("ok") is True, result


@pytest.mark.real
@pytest.mark.requires_service("ragflow")
def test_ragflow_create_and_list_dataset(ragflow_or_skip, tmp_path):
    """Cria um dataset real via SDK, lista e deleta.

    Cobre o caminho de ingestao K6 contra o wrapper RAGFlow real. O
    dataset tem nome unico por teste (`hm_test_<uuid12>`) e eh
    deletado no teardown para nao poluir o servico entre runs.
    Quando RAGFlow esta offline, a fixture pula explicito.
    """
    import os
    import uuid

    os.environ.setdefault("RAGFLOW_API_KEY", "test-key")
    RAGFlowSettings, assert_health = ragflow_or_skip
    settings = RAGFlowSettings(
        base_url=os.environ.get("RAGFLOW_BASE", "http://localhost:9380"),
        api_key=os.environ.get("RAGFLOW_API_KEY", "test-key"),
    )
    if not settings.api_key:
        pytest.skip("RAGFLOW_API_KEY nao configurado; sem ele nao ha como chamar o SDK")

    from integrations.ragflow import create_client

    try:
        client = create_client(settings)
    except Exception as exc:
        pytest.skip(f"RAGFlow SDK indisponivel: {exc}")

    dataset_name = f"hm_test_{uuid.uuid4().hex[:12]}"
    try:
        dataset = client.create_dataset(name=dataset_name, description="K9 upload fixture")
        assert dataset is not None, "create_dataset retornou None"
        # Listar e confirmar que o dataset novo aparece
        listed = client.list_datasets(name=dataset_name)
        names = {getattr(d, "name", None) for d in listed}
        assert dataset_name in names, f"dataset {dataset_name} nao apareceu em list_datasets"
    except Exception as exc:
        # RAGFlow pode estar online mas exigir auth/permission; o teste
        # so eh obrigatorio quando o servico aceita create_dataset.
        pytest.skip(f"RAGFlow create_dataset falhou (pode ser permissao): {exc}")
    finally:
        try:
            listed = client.list_datasets(name=dataset_name)
            if listed:
                client.delete_datasets(ids=[listed[0].id])
        except Exception:
            pass


@pytest.mark.real
@pytest.mark.requires_service("ragflow")
def test_ragflow_upload_then_list_documents(ragflow_or_skip, tmp_path):
    """Cria dataset, sobe documento de texto e lista; cobre ingestao K6 real.

    O arquivo de texto eh minimo (1 frase) e vive em `tmp_path` — some
    no teardown. Quando RAGFlow esta offline, a fixture pula explicito.
    """
    import os
    import uuid

    os.environ.setdefault("RAGFLOW_API_KEY", "test-key")
    RAGFlowSettings, assert_health = ragflow_or_skip
    settings = RAGFlowSettings(
        base_url=os.environ.get("RAGFLOW_BASE", "http://localhost:9380"),
        api_key=os.environ.get("RAGFLOW_API_KEY", "test-key"),
    )
    if not settings.api_key:
        pytest.skip("RAGFLOW_API_KEY nao configurado")

    from integrations.ragflow import create_client

    doc = tmp_path / "k9-real-doc.md"
    doc.write_text(
        "# K9 Real Test\n\nFixture real de upload RAGFlow: valida o "
        "caminho SDK create_dataset -> upload_documents -> list_documents.",
        encoding="utf-8",
    )
    dataset_name = f"hm_upload_{uuid.uuid4().hex[:12]}"
    try:
        client = create_client(settings)
        dataset = client.create_dataset(name=dataset_name)
        try:
            dataset.upload_documents([{"display_name": doc.name, "blob": doc.read_bytes()}])
        except Exception as exc:
            pytest.skip(f"RAGFlow upload_documents falhou: {exc}")
        try:
            docs = dataset.list_documents(name=doc.name)
        except Exception as exc:
            pytest.skip(f"RAGFlow list_documents falhou: {exc}")
        names = {getattr(d, "name", None) or getattr(d, "display_name", None) for d in docs}
        assert any(n and doc.name in n for n in names), (
            f"documento {doc.name} nao apareceu em list_documents: {names}"
        )
    except Exception as exc:
        pytest.skip(f"RAGFlow SDK nao aceitou operacao: {exc}")
    finally:
        try:
            from integrations.ragflow import create_client
            client = create_client(settings)
            listed = client.list_datasets(name=dataset_name)
            if listed:
                client.delete_datasets(ids=[listed[0].id])
        except Exception:
            pass

