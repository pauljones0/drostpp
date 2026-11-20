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
   - **Model Router & Resource Caps:** tier/role routing (`fast`, `default`, `strong`) with quota/transient cooldown failover; run/task token, wall-time, disk-quota, free-disk floor, capped stdout/stderr buffers, repeated-error stall detection, Linux `/proc` PGID RSS watchdog, Docker container runner (`DockerRunner`), and full process-group teardown (`terminate_process_group`).

4. **External Drost Integration (`integrations/mcp.py`, `integrations/drost.py`)**
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

## Development & Tests

```bash
PYTHONPATH=src pytest -v
```

## License

- The **drost++** engine (`src/drostpp/`, `tests/`, `examples/`) is licensed under the Apache License, Version 2.0 ([LICENSE](LICENSE)).
- The `drost/` submodule links to `drost-ai/drost-community`, also licensed under Apache-2.0; see `drost/LICENSE` and `drost/THIRD_PARTY_NOTICES.md`.
