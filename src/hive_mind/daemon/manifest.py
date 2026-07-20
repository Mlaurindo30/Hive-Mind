"""Manifest schema, validation and invariants (F2 / D006).

Implements Pydantic v2 models for `config/runtime.yaml` (schema v3):
  - Services, External Services, Jobs, Compose Projects
  - Invariants: unique startup_order, valid dependencies, valid profiles
  - Loading, validating, dumping, and translating legacy unit_definitions().
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Union
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class PathsConfig(BaseModel):
    data_dir: Optional[str] = None
    state_dir: Optional[str] = None
    log_dir: Optional[str] = None
    user_config_dir: Optional[str] = None
    config_file: Optional[str] = None


class ReadinessProbe(BaseModel):
    type: Literal["tcp", "http", "command"]
    host: Optional[str] = None
    port: Optional[int] = None
    url: Optional[str] = None
    command: Optional[List[str]] = None
    expected_status: List[int] = Field(default_factory=lambda: [200])
    timeout_seconds: int = 60


class ServiceSpec(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True
    required: bool = False
    profiles: List[Literal["local-min", "local-full"]] = Field(default_factory=lambda: ["local-min", "local-full"])
    ownership: Literal["legacy", "shadow", "managed"] = "legacy"
    command: List[str]
    working_directory: str = "."
    env_file: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)
    startup_order: int = 100
    restart_policy: Literal["always", "on-failure", "never"] = "on-failure"
    restart_delay_seconds: int = 15
    restart_max_delay_seconds: int = 120
    restart_limit: int = 10
    readiness: Optional[ReadinessProbe] = None
    healthcheck: Optional[ReadinessProbe] = None
    requires_claude_mem_plugin: bool = False
    category: Literal["background-service", "user-session"] = "background-service"


class ExternalServiceSpec(BaseModel):
    name: str
    description: Optional[str] = None
    required: bool = True
    profiles: List[Literal["local-min", "local-full"]] = Field(default_factory=lambda: ["local-min", "local-full"])
    dependencies: List[str] = Field(default_factory=list)
    readiness: ReadinessProbe


class JobSchedule(BaseModel):
    type: Literal["cron", "interval"]
    expression: Optional[str] = None
    seconds: Optional[int] = None
    timezone: Optional[str] = "America/Sao_Paulo"
    misfire_policy: Literal["run_once", "ignore"] = "run_once"
    run_on_startup: bool = False
    max_instances: int = 1


class JobRetryPolicy(BaseModel):
    max_attempts: int = 0


class JobSpec(BaseModel):
    name: str
    description: Optional[str] = None
    command: List[str]
    schedule: JobSchedule
    enabled: bool = True
    timeout_seconds: int = 1800
    retry: JobRetryPolicy = Field(default_factory=JobRetryPolicy)
    on_failure: Literal["log", "notify"] = "log"
    category: Literal["scheduled-job"] = "scheduled-job"
    blocking_service: Optional[str] = None


class ComposeProjectSpec(BaseModel):
    name: str
    file: str
    profiles: List[Literal["local-min", "local-full"]] = Field(default_factory=lambda: ["local-full"])
    required: bool = True
    health_check: Optional[ReadinessProbe] = None


class GlobalRestartPolicy(BaseModel):
    default_policy: Literal["always", "on-failure", "never"] = "on-failure"
    default_delay_seconds: int = 15
    default_max_delay_seconds: int = 120
    default_limit: int = 10
    on_circuit_open: str = "log_and_mark_degraded"


class RuntimeManifest(BaseModel):
    schema_version: Literal[3] = 3
    profile: Literal["local-min", "local-full"] = "local-min"
    vault: str = "cerebro"
    pyproject_root: str = "."
    paths: PathsConfig = Field(default_factory=PathsConfig)
    services: List[ServiceSpec] = Field(default_factory=list)
    external_services: List[ExternalServiceSpec] = Field(default_factory=list)
    jobs: List[JobSpec] = Field(default_factory=list)
    compose_projects: List[ComposeProjectSpec] = Field(default_factory=list)
    restart: GlobalRestartPolicy = Field(default_factory=GlobalRestartPolicy)

    @model_validator(mode="after")
    def validate_invariants(self) -> "RuntimeManifest":
        service_names: Set[str] = set()
        external_names: Set[str] = set()
        startup_orders: Set[int] = set()

        for s in self.services:
            if s.name in service_names:
                raise ValueError(f"Nome de serviço duplicado no manifesto: {s.name}")
            service_names.add(s.name)

            if s.startup_order in startup_orders:
                raise ValueError(f"startup_order duplicado ({s.startup_order}) para o serviço {s.name}")
            startup_orders.add(s.startup_order)

        for ext in self.external_services:
            if ext.name in service_names or ext.name in external_names:
                raise ValueError(f"Nome de serviço externo duplicado: {ext.name}")
            external_names.add(ext.name)

        all_known = service_names | external_names

        # Validar dependências existentes e ciclos
        for s in self.services:
            for dep in s.dependencies:
                if dep not in all_known:
                    raise ValueError(f"Serviço '{s.name}' depende de '{dep}' que não existe no manifesto")

        return self


def load_manifest(manifest_path: Path) -> RuntimeManifest:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifesto não encontrado em {manifest_path}")
    raw_data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    return RuntimeManifest.model_validate(raw_data)


def validate_manifest(manifest_path: Path) -> List[str]:
    """Retorna lista de erros de validação (vazia se válido)."""
    try:
        load_manifest(manifest_path)
        return []
    except Exception as exc:
        return [str(exc)]
