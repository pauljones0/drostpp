# drost++

**drost++** (`drostpp`) is a zero-dependency Python 3.12+ durable multi-agent orchestration engine packaged alongside the [Drost Community Edition](https://github.com/drost-ai/drost-community) containerized MCP runtime (`drost/`).

Orchestration lives cleanly **outside** Drost's per-session stdio MCP server while integrating directly with Drost's container tools and engagement workspaces.

## Repository Layout

- `src/drostpp/` — **drost++** coordinator, SQLite WAL state engine, blackboard, diversity scheduler, Codex/Kimi adapters, process-group supervisor, and Drost bridge.
- `drost/` — Git submodule pointing to [`drost-ai/drost-community`](https://github.com/drost-ai/drost-community) (Apache-2.0).
- `background/analysis/` — Architectural findings, post-mortems, and corpus manifests across 51 evaluated agent/orchestration repositories ([`background/analysis/README.md`](background/analysis/README.md)).
- `examples/` — Sample configurations (`config.toml`, `config.drost.toml`) and exploration seed knowledge base (`knowledge_base.jsonl`).
- `tests/` — Offline reliability, fencing, recovery, diversity, adapter, and Drost bridge test suite.

## Core Architecture

1. **Coordinator & SQLite WAL State Engine (`store.py`, `coordinator.py`)**
   - **Exclusive single-writer lock (`CoordinatorLock`):** non-blocking `fcntl.flock(LOCK_EX | LOCK_NB)` on `coordinator.lock` rejects overlapping coordinator processes.
   - **Atomic event journal + projections:** SQLite WAL (`synchronous=FULL`, `foreign_keys=ON`) using serialized `BEGIN IMMEDIATE ... COMMIT` transactions that write state rows and `events` together.
   - **Explicit phase machine (`RunPhase`):** `INIT → PLANNING → RUNNING → VERIFYING → COMPLETED` (plus `PAUSED`, `FAILED`, `CANCELLED`). Blocks `PLANNING → COMPLETED` and `RUNNING → COMPLETED` unless `plan_materialized = 1` and zero non-terminal tasks remain.
   - **Monotonic `(attempt_id, generation)` fencing & DAG tasks:** atomic CAS `claim_next_task`, dependency cycle detection, expired-lease reclamation, startup process-group recovery (`recover()`), and `FencedAttemptError` rejection + audit logging for stale writers.

2. **Blackboard & Controlled Diversity (`blackboard.py`, `diversity.py`)**
   - Content-fingerprinted deduplication across `fact`, `hypothesis`, `finding`, `note`, `synthesis`, and `artifact_ref` entries with strictly bounded `render_context(max_chars=...)`.
   - Seeded per-attempt exploration assignment combining **least-used personas**, **unsampled knowledge-base entries** (`.jsonl` or `.md`/`.txt`/`.json` directory), and **sibling-avoidance summaries** so parallel workers diverge naturally.

3. **Multi-Provider Adapters, Budgets & Supervision (`adapters/`, `routing.py`, `budgets.py`, `supervision.py`)**
   - **Codex (`CodexAdapter`):** runs `codex exec --ephemeral --json --output-schema ...` using your existing `$CODEX_HOME` OAuth login, forwarding enabled MCP servers (including Drost) via `-c mcp_servers.<name>.*`.
   - **Kimi (`KimiApiAdapter` / `KimiCliAdapter`):** calls Moonshot/Kimi's OpenAI-compatible HTTP API with `KIMI_API_KEY` or `MOONSHOT_API_KEY` (never written to SQLite) and bridges stdio MCP tools, or runs `kimi -p ... --output-format stream-json --auto`.
   - **Model Router & Resource Caps:** tier/role routing (`fast`, `default`, `strong`) with quota/transient cooldown failover; run/task token, wall-time, disk-quota, free-disk and available-RAM admission floors, capped stdout/stderr buffers, repeated-error stall detection, Linux `/proc` PGID RSS watchdog, and full process-group teardown (`terminate_process_group`).

4. **Managed Container Ownership (`resources.py`, `resource_mcp.py`)**
   - Every worker-created container has a durable SQLite resource row and one or more expiring attempt/task leases. Ownership is persisted before `docker run`; if a worker dies between Docker creation and activation, label reconciliation adopts the container back into that row. Attempt heartbeats renew borrows. Releasing the final borrow atomically makes it non-borrowable, then synchronously runs `docker rm -f`.
   - A worker may transfer a lease only to a newly-created, explicitly named immediate follow-up. The short task reservation becomes an attempt lease when that task is claimed; an unclaimed reservation expires and is reaped.
   - `docker run` applies hard RAM, swap, PID, and rotating-log caps. The coordinator audits Docker's writable-layer size continuously and removes containers exceeding the configured logical disk cap. `resource exec` caps captured output and removes the container after an execution timeout. New containers are rejected if aggregate task/container reservations would overcommit RAM or disk safety floors.
   - Codex and Kimi API workers receive the broker as MCP tools; shell-capable workers can use `drost++ resource`. Direct Docker access is pointed at a dead socket by default to prevent accidental unmanaged starts, while trusted Drost and broker commands restore the coordinator endpoint.

5. **External Drost Integration (`integrations/mcp.py`, `integrations/drost.py`)**
   - Connects workers to `docker exec -i -e DROST_MCP_MODE=compact ... drost-ai drost-mcp` (or `full` / filtered `DROST_TOOL_CATEGORIES`).
   - `drost++ drost check` verifies both `exit_code == 0` and `"status": "healthy"` with zero `missing_executables`.
   - `DrostWorkspaceBridge` handles defensive engagement listing, safe SHA-256 deduplicated artifact sync into the Blackboard (skipping escaping/dangling symlinks), and unique-staging `atomic_write_json`.

---

## Installation & Quickstart

```bash
# Clone with the Drost submodule
git clone --recurse-submodules https://github.com/pauljones0/drostpp.git
cd drostpp

# Install drost++ in editable mode (zero runtime dependencies beyond Python 3.12 stdlib)
uv pip install --no-deps -e .
# (Both `drost++` and `drostpp` commands are installed.)
```

### Codex OAuth + Kimi Setup

- **Codex:** Authenticate once with `codex login` (uses `~/.codex/auth.json` or `$CODEX_HOME`; no `OPENAI_API_KEY` needed).
- **Kimi:** Export `KIMI_API_KEY` (or `MOONSHOT_API_KEY`) for API mode, or authenticate with `kimi login` and set `mode = "cli"` under `[providers.kimi]`.

### Running With Drost

```bash
# 1. Start the Drost container using the included submodule (see drost/README.md for options)
./drost/install.sh

# 2. Check local toolchain and Drost container readiness
drost++ doctor --config examples/config.drost.toml
drost++ drost check --config examples/config.drost.toml

# 3. Initialize a project directory wired to Drost + diversity KB
drost++ init ./my-run --with-drost --drost-mode compact --kb examples/knowledge_base.jsonl

# 4. Run a dry-run smoke test with mock workers, then inspect state
drost++ run --config examples/config.toml --goal "Audit component boundaries" --state-dir ./.drostpp_state --mock
drost++ status --state-dir ./.drostpp_state
drost++ events --state-dir ./.drostpp_state
drost++ blackboard list --state-dir ./.drostpp_state

# 5. Run against a Drost engagement
drost++ drost list-engagements --config examples/config.drost.toml
drost++ run --config examples/config.drost.toml \
  --goal "Review imported artifacts and organize verified findings" \
  --drost-engagement eng_20261120_0123456789abcdef0123456789abcdef
```

### Container ownership contract

Enable `[container]` (already enabled in `examples/config.drost.toml`). Workers can then use the `drostpp_resources` MCP tools or the equivalent shell commands:

```bash
# These context variables are injected automatically into a running worker.
drost++ resource start --key target-lab --image redis:8-alpine --publish 6379 -- redis-server
drost++ resource exec --key target-lab -- redis-cli ping
drost++ resource list
drost++ resource release --key target-lab
```

`resource start` returns any random loopback host-port mappings. A resource not named in `resource_handoffs` is removed when its attempt ends. A handoff must match a task title in the same response's `follow_up_tasks`; it is not an indefinite keepalive.

The dead-socket guard prevents normal tools from accidentally bypassing the broker. It is not a security boundary against a malicious worker with unrestricted host root access: such a process can deliberately select the Docker socket. For hostile-code isolation, run workers without the host Docker socket and expose only the resource MCP broker.

## Development & Tests

```bash
PYTHONPATH=src pytest -v
```

## License

- The **drost++** engine (`src/drostpp/`, `tests/`, `examples/`) is licensed under the Apache License, Version 2.0 ([LICENSE](LICENSE)).
- The `drost/` submodule links to `drost-ai/drost-community`, also licensed under Apache-2.0; see `drost/LICENSE` and `drost/THIRD_PARTY_NOTICES.md`.
