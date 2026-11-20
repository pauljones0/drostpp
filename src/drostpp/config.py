"""TOML/JSON configuration loading, validation, and serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import tomllib
from typing import Any

from .models import McpServerConfig, RouteTarget, RunBudget, TaskBudget

DEFAULT_PERSONAS: list[dict[str, str]] = [
    {
        "name": "first_principles",
        "instructions": (
            "Reason from explicit invariants, system boundaries, and concrete inputs/outputs "
            "rather than assuming conventional abstractions hold."
        ),
    },
    {
        "name": "edge_case_auditor",
        "instructions": (
            "Focus on boundary values, ordering assumptions, partial failures, empty/oversized "
            "inputs, and state transitions across restarts."
        ),
    },
    {
        "name": "adversarial_skeptic",
        "instructions": (
            "Challenge existing hypotheses and claims on the blackboard. Look for missing evidence, "
            "contradictions, false positives, and unverified assumptions."
        ),
    },
    {
        "name": "systems_integrator",
        "instructions": (
            "Examine handoffs between components, persistence layers, background workers, and "
            "external tool boundaries where local successes mask global mismatches."
        ),
    },
    {
        "name": "minimalist_verifier",
        "instructions": (
            "Design the smallest deterministic check or reproduction that distinguishes true behavior "
            "from noise using recorded artifacts and concrete outputs."
        ),
    },
    {
        "name": "lateral_explorer",
        "instructions": (
            "Intentionally diverge from the directions already taken by sibling tasks. Propose "
            "alternative hypotheses and non-obvious angles not yet on the blackboard."
        ),
    },
]

_SENSITIVE_KEY_FRAGMENTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH")


@dataclass(slots=True)
class RunConfig:
    max_workers: int = 2
    lease_seconds: int = 120
    heartbeat_seconds: float = 15.0
    max_total_tasks: int = 50
    max_follow_ups_per_task: int = 5
    enable_verify_phase: bool = True
    seed: int | None = None


@dataclass(slots=True)
class BudgetsConfig:
    max_run_tokens: int = 2_000_000
    max_run_wall_seconds: float = 3600.0
    max_run_disk_bytes: int = 2 * 1024 * 1024 * 1024
    min_free_disk_bytes: int = 256 * 1024 * 1024
    default_task_tokens: int = 100_000
    default_task_wall_seconds: float = 300.0
    default_task_memory_mb: int = 2048
    default_task_disk_bytes: int = 256 * 1024 * 1024
    max_output_bytes: int = 2 * 1024 * 1024
    max_same_error_repeats: int = 2

    def to_run_budget(self) -> RunBudget:
        return RunBudget(
            max_tokens=self.max_run_tokens,
            max_wall_seconds=self.max_run_wall_seconds,
            max_disk_bytes=self.max_run_disk_bytes,
            min_free_disk_bytes=self.min_free_disk_bytes,
        )

    def to_task_budget(self) -> TaskBudget:
        return TaskBudget(
            max_tokens=self.default_task_tokens,
            max_wall_seconds=self.default_task_wall_seconds,
            max_memory_mb=self.default_task_memory_mb,
            max_disk_bytes=self.default_task_disk_bytes,
            max_output_bytes=self.max_output_bytes,
        )


@dataclass(slots=True)
class DiversityConfig:
    enabled: bool = True
    personas: list[dict[str, str]] = field(
        default_factory=lambda: [dict(item) for item in DEFAULT_PERSONAS]
    )
    knowledge_base_path: str | None = None
    kb_samples_per_task: int = 2
    include_sibling_avoidance: bool = True


@dataclass(slots=True)
class RoutingConfig:
    tiers: dict[str, list[RouteTarget]] = field(
        default_factory=lambda: {
            "fast": [RouteTarget(provider="kimi", model="kimi-k2-turbo-preview", tier="fast")],
            "default": [
                RouteTarget(provider="codex", model="", tier="default"),
                RouteTarget(provider="kimi", model="kimi-k2-turbo-preview", tier="default"),
            ],
            "strong": [
                RouteTarget(provider="codex", model="", tier="strong"),
                RouteTarget(provider="kimi", model="kimi-k2.5", tier="strong"),
            ],
        }
    )
    role_overrides: dict[str, str] = field(default_factory=dict)
    cooldown_seconds: float = 60.0


@dataclass(slots=True)
class CodexProviderConfig:
    binary: str = "codex"
    default_model: str = ""
    profile: str | None = None
    sandbox: str = "workspace-write"
    codex_home: str | None = None
    extra_config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class KimiProviderConfig:
    mode: str = "api"
    base_url: str = "https://api.moonshot.ai/v1"
    api_key_env: str = "KIMI_API_KEY"
    default_model: str = "kimi-k2-turbo-preview"
    cli_binary: str = "kimi"
    max_tool_turns: int = 8
    timeout_seconds: float = 120.0


@dataclass(slots=True)
class ContainerConfig:
    enabled: bool = False
    docker_binary: str = "docker"
    image: str = ""
    memory_mb: int = 2048
    pids_limit: int = 256
    network: str | None = None
    read_only: bool = False


@dataclass(slots=True)
class DrostConfig:
    enabled: bool = False
    container_name: str = "drost-ai"
    docker_binary: str = "docker"
    mcp_command: str = "drost-mcp"
    mcp_mode: str = "compact"
    tool_categories: list[str] = field(default_factory=list)
    workspace_host_path: str | None = None
    engagement_id: str | None = None
    max_import_bytes: int = 32 * 1024 * 1024
    extra_env: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class OrchestratorConfig:
    run: RunConfig = field(default_factory=RunConfig)
    budgets: BudgetsConfig = field(default_factory=BudgetsConfig)
    diversity: DiversityConfig = field(default_factory=DiversityConfig)
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    codex: CodexProviderConfig = field(default_factory=CodexProviderConfig)
    kimi: KimiProviderConfig = field(default_factory=KimiProviderConfig)
    container: ContainerConfig = field(default_factory=ContainerConfig)
    mcp_servers: dict[str, McpServerConfig] = field(default_factory=dict)
    drost: DrostConfig = field(default_factory=DrostConfig)

    def to_public_dict(self) -> dict[str, Any]:
        """Serialize configuration while redacting any sensitive environment values."""
        return {
            "run": {
                "max_workers": self.run.max_workers,
                "lease_seconds": self.run.lease_seconds,
                "heartbeat_seconds": self.run.heartbeat_seconds,
                "max_total_tasks": self.run.max_total_tasks,
                "max_follow_ups_per_task": self.run.max_follow_ups_per_task,
                "enable_verify_phase": self.run.enable_verify_phase,
                "seed": self.run.seed,
            },
            "budgets": {
                "max_run_tokens": self.budgets.max_run_tokens,
                "max_run_wall_seconds": self.budgets.max_run_wall_seconds,
                "max_run_disk_bytes": self.budgets.max_run_disk_bytes,
                "min_free_disk_bytes": self.budgets.min_free_disk_bytes,
                "default_task_tokens": self.budgets.default_task_tokens,
                "default_task_wall_seconds": self.budgets.default_task_wall_seconds,
                "default_task_memory_mb": self.budgets.default_task_memory_mb,
                "default_task_disk_bytes": self.budgets.default_task_disk_bytes,
                "max_output_bytes": self.budgets.max_output_bytes,
                "max_same_error_repeats": self.budgets.max_same_error_repeats,
            },
            "diversity": {
                "enabled": self.diversity.enabled,
                "personas": [dict(p) for p in self.diversity.personas],
                "knowledge_base_path": self.diversity.knowledge_base_path,
                "kb_samples_per_task": self.diversity.kb_samples_per_task,
                "include_sibling_avoidance": self.diversity.include_sibling_avoidance,
            },
            "routing": {
                "tiers": {
                    tier: [
                        {
                            "provider": target.provider,
                            "model": target.model,
                            "tier": target.tier,
                            "options": dict(target.options),
                        }
                        for target in targets
                    ]
                    for tier, targets in self.routing.tiers.items()
                },
                "role_overrides": dict(self.routing.role_overrides),
                "cooldown_seconds": self.routing.cooldown_seconds,
            },
            "providers": {
                "codex": {
                    "binary": self.codex.binary,
                    "default_model": self.codex.default_model,
                    "profile": self.codex.profile,
                    "sandbox": self.codex.sandbox,
                    "codex_home": self.codex.codex_home,
                    "extra_config": _redact_mapping(self.codex.extra_config),
                },
                "kimi": {
                    "mode": self.kimi.mode,
                    "base_url": self.kimi.base_url,
                    "api_key_env": self.kimi.api_key_env,
                    "default_model": self.kimi.default_model,
                    "cli_binary": self.kimi.cli_binary,
                    "max_tool_turns": self.kimi.max_tool_turns,
                    "timeout_seconds": self.kimi.timeout_seconds,
                },
            },
            "container": {
                "enabled": self.container.enabled,
                "docker_binary": self.container.docker_binary,
                "image": self.container.image,
                "memory_mb": self.container.memory_mb,
                "pids_limit": self.container.pids_limit,
                "network": self.container.network,
                "read_only": self.container.read_only,
            },
            "mcp_servers": {
                name: {
                    "command": srv.command,
                    "args": list(srv.args),
                    "env": _redact_mapping(srv.env),
                    "timeout_seconds": srv.timeout_seconds,
                    "max_result_bytes": srv.max_result_bytes,
                    "enabled": srv.enabled,
                }
                for name, srv in self.mcp_servers.items()
            },
            "drost": {
                "enabled": self.drost.enabled,
                "container_name": self.drost.container_name,
                "docker_binary": self.drost.docker_binary,
                "mcp_command": self.drost.mcp_command,
                "mcp_mode": self.drost.mcp_mode,
                "tool_categories": list(self.drost.tool_categories),
                "workspace_host_path": self.drost.workspace_host_path,
                "engagement_id": self.drost.engagement_id,
                "max_import_bytes": self.drost.max_import_bytes,
                "extra_env": _redact_mapping(self.drost.extra_env),
            },
        }


def _redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        upper = str(key).upper()
        if any(frag in upper for frag in _SENSITIVE_KEY_FRAGMENTS):
            cleaned[key] = "<REDACTED>"
        elif isinstance(value, dict):
            cleaned[key] = _redact_mapping(value)
        else:
            cleaned[key] = value
    return cleaned


def load_config(path: Path | str | None) -> OrchestratorConfig:
    """Load configuration from a TOML or JSON file, or return defaults if path is None."""
    if path is None:
        return OrchestratorConfig()
    cfg_path = Path(path)
    raw_bytes = cfg_path.read_bytes()
    if cfg_path.suffix.lower() == ".json":
        data = json.loads(raw_bytes.decode("utf-8"))
    else:
        data = tomllib.loads(raw_bytes.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"config file must decode to a table/object: {cfg_path}")
    return config_from_dict(data, base_dir=cfg_path.parent)


def _resolve_optional_path(raw: str | None, base_dir: Path | None) -> str | None:
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute() and base_dir is not None:
        return str((base_dir / p).resolve())
    return str(p)


def config_from_dict(data: dict[str, Any], *, base_dir: Path | None = None) -> OrchestratorConfig:
    """Build and validate OrchestratorConfig from a parsed dictionary."""
    cfg = OrchestratorConfig()

    run_raw = data.get("run", {})
    if run_raw:
        cfg.run = RunConfig(
            max_workers=max(1, int(run_raw.get("max_workers", cfg.run.max_workers))),
            lease_seconds=max(5, int(run_raw.get("lease_seconds", cfg.run.lease_seconds))),
            heartbeat_seconds=max(0.2, float(run_raw.get("heartbeat_seconds", cfg.run.heartbeat_seconds))),
            max_total_tasks=max(1, int(run_raw.get("max_total_tasks", cfg.run.max_total_tasks))),
            max_follow_ups_per_task=max(
                0, int(run_raw.get("max_follow_ups_per_task", cfg.run.max_follow_ups_per_task))
            ),
            enable_verify_phase=bool(run_raw.get("enable_verify_phase", cfg.run.enable_verify_phase)),
            seed=int(run_raw["seed"]) if run_raw.get("seed") is not None else None,
        )

    budgets_raw = data.get("budgets", {})
    if budgets_raw:
        cfg.budgets = BudgetsConfig(
            max_run_tokens=max(1, int(budgets_raw.get("max_run_tokens", cfg.budgets.max_run_tokens))),
            max_run_wall_seconds=max(
                1.0, float(budgets_raw.get("max_run_wall_seconds", cfg.budgets.max_run_wall_seconds))
            ),
            max_run_disk_bytes=max(
                1024, int(budgets_raw.get("max_run_disk_bytes", cfg.budgets.max_run_disk_bytes))
            ),
            min_free_disk_bytes=max(
                0, int(budgets_raw.get("min_free_disk_bytes", cfg.budgets.min_free_disk_bytes))
            ),
            default_task_tokens=max(
                1, int(budgets_raw.get("default_task_tokens", cfg.budgets.default_task_tokens))
            ),
            default_task_wall_seconds=max(
                0.5, float(budgets_raw.get("default_task_wall_seconds", cfg.budgets.default_task_wall_seconds))
            ),
            default_task_memory_mb=max(
                16, int(budgets_raw.get("default_task_memory_mb", cfg.budgets.default_task_memory_mb))
            ),
            default_task_disk_bytes=max(
                1024, int(budgets_raw.get("default_task_disk_bytes", cfg.budgets.default_task_disk_bytes))
            ),
            max_output_bytes=max(1024, int(budgets_raw.get("max_output_bytes", cfg.budgets.max_output_bytes))),
            max_same_error_repeats=max(
                1, int(budgets_raw.get("max_same_error_repeats", cfg.budgets.max_same_error_repeats))
            ),
        )

    div_raw = data.get("diversity", {})
    if div_raw:
        personas_raw = div_raw.get("personas")
        personas = (
            [
                {
                    "name": str(item["name"]).strip(),
                    "instructions": str(item.get("instructions", "")).strip(),
                }
                for item in personas_raw
                if isinstance(item, dict) and item.get("name")
            ]
            if isinstance(personas_raw, list)
            else list(cfg.diversity.personas)
        )
        if not personas:
            personas = [dict(item) for item in DEFAULT_PERSONAS]
        cfg.diversity = DiversityConfig(
            enabled=bool(div_raw.get("enabled", cfg.diversity.enabled)),
            personas=personas,
            knowledge_base_path=_resolve_optional_path(div_raw.get("knowledge_base_path"), base_dir),
            kb_samples_per_task=max(
                0, int(div_raw.get("kb_samples_per_task", cfg.diversity.kb_samples_per_task))
            ),
            include_sibling_avoidance=bool(
                div_raw.get("include_sibling_avoidance", cfg.diversity.include_sibling_avoidance)
            ),
        )

    routing_raw = data.get("routing", {})
    if routing_raw:
        tiers = dict(cfg.routing.tiers)
        raw_tiers = routing_raw.get("tiers")
        if raw_tiers is None:
            raw_tiers = {
                k: v for k, v in routing_raw.items() if k in {"fast", "default", "strong"} and isinstance(v, list)
            }
        for tier_name, entries in raw_tiers.items():
            parsed_targets: list[RouteTarget] = []
            for entry in entries:
                if isinstance(entry, dict) and entry.get("provider"):
                    parsed_targets.append(
                        RouteTarget(
                            provider=str(entry["provider"]),
                            model=str(entry.get("model", "")),
                            tier=str(tier_name),
                            options=dict(entry.get("options", {})),
                        )
                    )
            if parsed_targets:
                tiers[str(tier_name)] = parsed_targets
        cfg.routing = RoutingConfig(
            tiers=tiers,
            role_overrides={str(k): str(v) for k, v in routing_raw.get("role_overrides", {}).items()},
            cooldown_seconds=max(0.0, float(routing_raw.get("cooldown_seconds", cfg.routing.cooldown_seconds))),
        )

    providers_raw = data.get("providers", {})
    codex_raw = providers_raw.get("codex", {})
    if codex_raw:
        sandbox = str(codex_raw.get("sandbox", cfg.codex.sandbox))
        if sandbox not in {"read-only", "workspace-write", "danger-full-access"}:
            raise ValueError(f"unsupported codex sandbox mode: {sandbox}")
        cfg.codex = CodexProviderConfig(
            binary=str(codex_raw.get("binary", cfg.codex.binary)),
            default_model=str(codex_raw.get("default_model", cfg.codex.default_model)),
            profile=codex_raw.get("profile"),
            sandbox=sandbox,
            codex_home=_resolve_optional_path(codex_raw.get("codex_home"), base_dir),
            extra_config=dict(codex_raw.get("extra_config", {})),
        )

    kimi_raw = providers_raw.get("kimi", {})
    if kimi_raw:
        mode = str(kimi_raw.get("mode", cfg.kimi.mode)).lower()
        if mode not in {"api", "cli"}:
            raise ValueError(f"unsupported kimi mode: {mode}")
        cfg.kimi = KimiProviderConfig(
            mode=mode,
            base_url=str(kimi_raw.get("base_url", cfg.kimi.base_url)).rstrip("/"),
            api_key_env=str(kimi_raw.get("api_key_env", cfg.kimi.api_key_env)),
            default_model=str(kimi_raw.get("default_model", cfg.kimi.default_model)),
            cli_binary=str(kimi_raw.get("cli_binary", cfg.kimi.cli_binary)),
            max_tool_turns=max(1, int(kimi_raw.get("max_tool_turns", cfg.kimi.max_tool_turns))),
            timeout_seconds=max(1.0, float(kimi_raw.get("timeout_seconds", cfg.kimi.timeout_seconds))),
        )

    cont_raw = data.get("container", {})
    if cont_raw:
        cfg.container = ContainerConfig(
            enabled=bool(cont_raw.get("enabled", cfg.container.enabled)),
            docker_binary=str(cont_raw.get("docker_binary", cfg.container.docker_binary)),
            image=str(cont_raw.get("image", cfg.container.image)),
            memory_mb=max(64, int(cont_raw.get("memory_mb", cfg.container.memory_mb))),
            pids_limit=max(16, int(cont_raw.get("pids_limit", cfg.container.pids_limit))),
            network=cont_raw.get("network"),
            read_only=bool(cont_raw.get("read_only", cfg.container.read_only)),
        )

    mcp_raw = data.get("mcp_servers", {})
    for name, srv in mcp_raw.items():
        if not isinstance(srv, dict) or not srv.get("command"):
            continue
        cfg.mcp_servers[str(name)] = McpServerConfig(
            name=str(name),
            command=str(srv["command"]),
            args=[str(a) for a in srv.get("args", [])],
            env={str(k): str(v) for k, v in srv.get("env", {}).items()},
            timeout_seconds=max(1.0, float(srv.get("timeout_seconds", 60.0))),
            max_result_bytes=max(1024, int(srv.get("max_result_bytes", 256 * 1024))),
            enabled=bool(srv.get("enabled", True)),
        )

    drost_raw = data.get("drost", {})
    if drost_raw:
        mcp_mode = str(drost_raw.get("mcp_mode", cfg.drost.mcp_mode)).strip().lower()
        if mcp_mode not in {"compact", "full"}:
            raise ValueError(f"drost.mcp_mode must be 'compact' or 'full', got {mcp_mode!r}")
        cfg.drost = DrostConfig(
            enabled=bool(drost_raw.get("enabled", cfg.drost.enabled)),
            container_name=str(drost_raw.get("container_name", cfg.drost.container_name)),
            docker_binary=str(drost_raw.get("docker_binary", cfg.drost.docker_binary)),
            mcp_command=str(drost_raw.get("mcp_command", cfg.drost.mcp_command)),
            mcp_mode=mcp_mode,
            tool_categories=[str(c) for c in drost_raw.get("tool_categories", [])],
            workspace_host_path=_resolve_optional_path(drost_raw.get("workspace_host_path"), base_dir),
            engagement_id=drost_raw.get("engagement_id"),
            max_import_bytes=max(1024, int(drost_raw.get("max_import_bytes", cfg.drost.max_import_bytes))),
            extra_env={str(k): str(v) for k, v in drost_raw.get("extra_env", {}).items()},
        )

    return cfg


def _toml_val(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        return json.dumps(val)
    if isinstance(val, list):
        return "[" + ", ".join(_toml_val(item) for item in val) + "]"
    if isinstance(val, dict):
        parts = [f"{k} = {_toml_val(v)}" for k, v in val.items() if v is not None]
        return "{ " + ", ".join(parts) + " }"
    raise TypeError(f"unsupported TOML value: {type(val)!r}")


def config_to_toml(cfg: OrchestratorConfig) -> str:
    """Render an OrchestratorConfig into a well-commented TOML string."""
    lines: list[str] = [
        "[run]",
        f"max_workers = {cfg.run.max_workers}",
        f"lease_seconds = {cfg.run.lease_seconds}",
        f"heartbeat_seconds = {cfg.run.heartbeat_seconds}",
        f"max_total_tasks = {cfg.run.max_total_tasks}",
        f"max_follow_ups_per_task = {cfg.run.max_follow_ups_per_task}",
        f"enable_verify_phase = {_toml_val(cfg.run.enable_verify_phase)}",
    ]
    if cfg.run.seed is not None:
        lines.append(f"seed = {cfg.run.seed}")

    lines.extend(
        [
            "",
            "[budgets]",
            f"max_run_tokens = {cfg.budgets.max_run_tokens}",
            f"max_run_wall_seconds = {cfg.budgets.max_run_wall_seconds}",
            f"max_run_disk_bytes = {cfg.budgets.max_run_disk_bytes}",
            f"min_free_disk_bytes = {cfg.budgets.min_free_disk_bytes}",
            f"default_task_tokens = {cfg.budgets.default_task_tokens}",
            f"default_task_wall_seconds = {cfg.budgets.default_task_wall_seconds}",
            f"default_task_memory_mb = {cfg.budgets.default_task_memory_mb}",
            f"default_task_disk_bytes = {cfg.budgets.default_task_disk_bytes}",
            f"max_output_bytes = {cfg.budgets.max_output_bytes}",
            f"max_same_error_repeats = {cfg.budgets.max_same_error_repeats}",
            "",
            "[diversity]",
            f"enabled = {_toml_val(cfg.diversity.enabled)}",
            f"kb_samples_per_task = {cfg.diversity.kb_samples_per_task}",
            f"include_sibling_avoidance = {_toml_val(cfg.diversity.include_sibling_avoidance)}",
        ]
    )
    if cfg.diversity.knowledge_base_path:
        lines.append(f"knowledge_base_path = {_toml_val(cfg.diversity.knowledge_base_path)}")
    for persona in cfg.diversity.personas:
        lines.extend(
            [
                "",
                "[[diversity.personas]]",
                f"name = {_toml_val(persona['name'])}",
                f"instructions = {_toml_val(persona['instructions'])}",
            ]
        )

    lines.extend(["", "[routing]", f"cooldown_seconds = {cfg.routing.cooldown_seconds}"])
    if cfg.routing.role_overrides:
        lines.append(f"role_overrides = {_toml_val(cfg.routing.role_overrides)}")
    for tier_name, targets in cfg.routing.tiers.items():
        for target in targets:
            lines.extend(
                [
                    "",
                    f"[[routing.tiers.{tier_name}]]",
                    f"provider = {_toml_val(target.provider)}",
                    f"model = {_toml_val(target.model)}",
                ]
            )
            if target.options:
                lines.append(f"options = {_toml_val(target.options)}")

    lines.extend(
        [
            "",
            "[providers.codex]",
            f"binary = {_toml_val(cfg.codex.binary)}",
            f"default_model = {_toml_val(cfg.codex.default_model)}",
            f"sandbox = {_toml_val(cfg.codex.sandbox)}",
        ]
    )
    if cfg.codex.profile:
        lines.append(f"profile = {_toml_val(cfg.codex.profile)}")
    if cfg.codex.codex_home:
        lines.append(f"codex_home = {_toml_val(cfg.codex.codex_home)}")

    lines.extend(
        [
            "",
            "[providers.kimi]",
            f"mode = {_toml_val(cfg.kimi.mode)}",
            f"base_url = {_toml_val(cfg.kimi.base_url)}",
            f"api_key_env = {_toml_val(cfg.kimi.api_key_env)}",
            f"default_model = {_toml_val(cfg.kimi.default_model)}",
            f"cli_binary = {_toml_val(cfg.kimi.cli_binary)}",
            f"max_tool_turns = {cfg.kimi.max_tool_turns}",
            f"timeout_seconds = {cfg.kimi.timeout_seconds}",
            "",
            "[container]",
            f"enabled = {_toml_val(cfg.container.enabled)}",
            f"docker_binary = {_toml_val(cfg.container.docker_binary)}",
            f"image = {_toml_val(cfg.container.image)}",
            f"memory_mb = {cfg.container.memory_mb}",
            f"pids_limit = {cfg.container.pids_limit}",
            f"read_only = {_toml_val(cfg.container.read_only)}",
        ]
    )
    if cfg.container.network:
        lines.append(f"network = {_toml_val(cfg.container.network)}")

    lines.extend(
        [
            "",
            "[drost]",
            f"enabled = {_toml_val(cfg.drost.enabled)}",
            f"container_name = {_toml_val(cfg.drost.container_name)}",
            f"docker_binary = {_toml_val(cfg.drost.docker_binary)}",
            f"mcp_command = {_toml_val(cfg.drost.mcp_command)}",
            f"mcp_mode = {_toml_val(cfg.drost.mcp_mode)}",
            f"tool_categories = {_toml_val(cfg.drost.tool_categories)}",
            f"max_import_bytes = {cfg.drost.max_import_bytes}",
        ]
    )
    if cfg.drost.workspace_host_path:
        lines.append(f"workspace_host_path = {_toml_val(cfg.drost.workspace_host_path)}")
    if cfg.drost.engagement_id:
        lines.append(f"engagement_id = {_toml_val(cfg.drost.engagement_id)}")
    if cfg.drost.extra_env:
        lines.append(f"extra_env = {_toml_val(cfg.drost.extra_env)}")

    for name, srv in cfg.mcp_servers.items():
        lines.extend(
            [
                "",
                f"[mcp_servers.{name}]",
                f"command = {_toml_val(srv.command)}",
                f"args = {_toml_val(srv.args)}",
                f"env = {_toml_val(srv.env)}",
                f"timeout_seconds = {srv.timeout_seconds}",
                f"max_result_bytes = {srv.max_result_bytes}",
                f"enabled = {_toml_val(srv.enabled)}",
            ]
        )

    return "\n".join(lines) + "\n"
