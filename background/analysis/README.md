# Orchestration Harness Evaluations & Post-Mortems

This directory contains the 51 offline core-architecture evaluations, post-mortems, and corpus manifests produced prior to building **drost++**. Each evaluation examined pinned repository source code and executed local reliability, concurrency, cancellation, state-recovery, and resource-boundary controls (GUI/frontend presentation out of scope).

- [Evaluation Protocol](evaluations/README.md)
- [Authoritative Corpus Manifest (35 repos)](corpus/orchestrators.tsv)
- [Authoritative Evaluation Queue](evaluations/orchestrator-queue.tsv) · [Retry Queue](evaluations/retry-queue.tsv)
- [Supplemental Framework Survey Manifest](corpus/repos.tsv) · [Corpus Notes](corpus/README.md)

## Key Cross-Corpus Findings Behind drost++

Across the evaluations, failures clustered **between** components rather than inside single-turn model loops—where state, ownership, and process boundaries diverged across `await`s, restarts, or overlapping writers:

1. **One durable attempt identity and monotonic generation fencing (`majiayu000/harness`):** Claims use conditional SQL updates (`WHERE status = 'ready' AND generation = ?`), and every subsequent runtime attach, heartbeat, blackboard publish, and completion validates `(attempt_id, generation)` against the active row so stale workers are fenced and audited rather than silently overwriting newer state.
2. **Transactional event journal + projections in one database transaction (`nin-dev-ai/harness`):** State transitions and append-only `events` rows commit atomically inside `BEGIN IMMEDIATE` SQLite WAL transactions under a single-writer `fcntl.flock` lock (`coordinator.lock`), preventing journal/projection drift.
3. **Explicit phase invariants instead of queue emptiness (`ARTEX` & `ScopeWeaver` lessons):** Runs track `RunPhase` explicitly (`INIT → PLANNING → RUNNING → VERIFYING → COMPLETED`) plus `plan_materialized`, preventing restarts during bootstrap or while paused tasks remain from marking unfinished runs `completed`.
4. **Separated control-plane state vs. session execution (`Gas City` & `IronCurtain` lessons):** Workers execute inside bounded adapters (`CodexAdapter`, `KimiApiAdapter`, `KimiCliAdapter`) with explicit quota/transient failover and never unilaterally declare global goal completion. Graceful shutdown interrupts in-flight attempts cleanly back to `ready` without exhausting retry budgets.
5. **Process-group reaping and bounded resources (`Drost Community Edition` lessons):** `ProcessSupervisor` spawns children in fresh POSIX sessions (`start_new_session=True`), monitors Linux `/proc` PGID RSS and attempt directory disk usage, and terminates the entire process group (`SIGTERM → SIGKILL` until `os.killpg(pgid, 0)` raises `ProcessLookupError`) so grandchildren inheriting stdout/stderr pipes cannot leak after cancellation or timeout.
6. **Drost as an external containerized tool & workspace provider:** Orchestration remains outside Drost's per-client stdio MCP server, wiring Drost via `docker exec -i` (`compact`/`full`), validating both exit status and JSON health (`check_drost_health`), tolerating malformed sibling manifests (`DrostWorkspaceBridge`), syncing deduplicated SHA-256 artifacts safely, and writing JSON through unique per-writer staging files (`atomic_write_json`).

---

## Authoritative Orchestration Corpus (35 Repositories)

| # | Repository | Pinned Commit | Evaluation Report |
| --- | --- | --- | --- |
| 1 | `cskwork/scopeweaver` | `1f33072cbb09` | [cskwork__scopeweaver.md](evaluations/cskwork__scopeweaver.md) |
| 2 | `RuoJi6/ARTEX` | `6997a4661921` | [RuoJi6__ARTEX.md](evaluations/RuoJi6__ARTEX.md) |
| 3 | `provos/ironcurtain` | `0e9a75497a19` | [provos__ironcurtain.md](evaluations/provos__ironcurtain.md) |
| 4 | `vxcontrol/pentagi` | `cffed9485aa1` | [vxcontrol__pentagi.md](evaluations/vxcontrol__pentagi.md) |
| 5 | `usestrix/strix` | `8db295a5b356` | [usestrix__strix.md](evaluations/usestrix__strix.md) |
| 6 | `OpenHands/software-agent-sdk` | `9105eac86f51` | [OpenHands__software-agent-sdk.md](evaluations/OpenHands__software-agent-sdk.md) |
| 7 | `OpenHands/automation` | `03823b431d54` | [OpenHands__automation.md](evaluations/OpenHands__automation.md) |
| 8 | `langchain-ai/deepagents` | `a502bd69d067` | [langchain-ai__deepagents.md](evaluations/langchain-ai__deepagents.md) |
| 9 | `gadievron/raptor` | `ad278b6e0afe` | [gadievron__raptor.md](evaluations/gadievron__raptor.md) |
| 10 | `KeygraphHQ/shannon` | `c20e119ac222` | [KeygraphHQ__shannon.md](evaluations/KeygraphHQ__shannon.md) |
| 11 | `awarexone/Agentic-Bug-Hunter` | `82f4512ec432` | [awarexone__Agentic-Bug-Hunter.md](evaluations/awarexone__Agentic-Bug-Hunter.md) |
| 12 | `samugit83/redamon` | `0f6420aed8be` | [samugit83__redamon.md](evaluations/samugit83__redamon.md) |
| 13 | `pydantic/pydantic-ai` | `be80a0429866` | [pydantic__pydantic-ai.md](evaluations/pydantic__pydantic-ai.md) |
| 14 | `langchain-ai/langgraph` | `bbd52757e72d` | [langchain-ai__langgraph.md](evaluations/langchain-ai__langgraph.md) |
| 15 | `earendil-works/pi` | `7b570f3517d7` | [earendil-works__pi.md](evaluations/earendil-works__pi.md) |
| 16 | `anomalyco/opencode` | `49cbcd8c0c31` | [anomalyco__opencode.md](evaluations/anomalyco__opencode.md) |
| 17 | `anthropics/sandbox-runtime` | `0bbebed0aa9a` | [anthropics__sandbox-runtime.md](evaluations/anthropics__sandbox-runtime.md) |
| 18 | `NVIDIA/OpenShell` | `fd3cff606a48` | [NVIDIA__OpenShell.md](evaluations/NVIDIA__OpenShell.md) |
| 19 | `aliasrobotics/cai` | `6dc79257777f` | [aliasrobotics__cai.md](evaluations/aliasrobotics__cai.md) |
| 20 | `GreyDGL/PentestGPT` | `e8b1bb77d1ac` | [GreyDGL__PentestGPT.md](evaluations/GreyDGL__PentestGPT.md) |
| 21 | `elder-plinius/T3MP3ST` | `29824d5625ed` | [elder-plinius__T3MP3ST.md](evaluations/elder-plinius__T3MP3ST.md) |
| 22 | `drost-ai/drost-community` | `3a410ee3f786` | [drost-ai__drost-community.md](evaluations/drost-ai__drost-community.md) |
| 23 | `gastownhall/gastown` | `94cc82289d2e` | [gastownhall__gastown.md](evaluations/gastownhall__gastown.md) |
| 24 | `gastownhall/gascity` | `7b5614ac70d1` | [gastownhall__gascity.md](evaluations/gastownhall__gascity.md) |
| 25 | `jayminwest/overstory` | `ff38f3f76f08` | [jayminwest__overstory.md](evaluations/jayminwest__overstory.md) |
| 26 | `dlorenc/multiclaude` | `dfad1a58343b` | [dlorenc__multiclaude.md](evaluations/dlorenc__multiclaude.md) |
| 27 | `nin-dev-ai/harness` | `2910cd8d061d` | [nin-dev-ai__harness.md](evaluations/nin-dev-ai__harness.md) |
| 28 | `zetbrush/multiagents` | `6038986b7399` | [zetbrush__multiagents.md](evaluations/zetbrush__multiagents.md) |
| 29 | `artificemachine/superharness` | `e77627733cf3` | [artificemachine__superharness.md](evaluations/artificemachine__superharness.md) |
| 30 | `Intelligent-Internet/zenith` | `a8d9b5786f81` | [Intelligent-Internet__zenith.md](evaluations/Intelligent-Internet__zenith.md) |
| 31 | `dsifry/metaswarm` | `4bbb10abd301` | [dsifry__metaswarm.md](evaluations/dsifry__metaswarm.md) |
| 32 | `majiayu000/harness` | `7e63762f453f` | [majiayu000__harness.md](evaluations/majiayu000__harness.md) |
| 33 | `docker/docker-agent` | `00578ca8a20d` | [docker__docker-agent.md](evaluations/docker__docker-agent.md) |
| 34 | `mco-org/mco` | `7ce642193a12` | [mco-org__mco.md](evaluations/mco-org__mco.md) |
| 35 | `AY-Liu/multi-agent-runner` | `e2fe272625e4` | [AY-Liu__multi-agent-runner.md](evaluations/AY-Liu__multi-agent-runner.md) |

---

## Supplemental Framework & Runtime Survey (16 Repositories)

| Repository | Pinned Commit | Evaluation Report |
| --- | --- | --- |
| `aaif-goose/goose` | `024e4cd5a8b8` | [aaif-goose__goose.md](evaluations/aaif-goose__goose.md) |
| `agentscope-ai/agentscope` | `9fdad22cd64a` | [agentscope-ai__agentscope.md](evaluations/agentscope-ai__agentscope.md) |
| `agno-agi/agno` | `821be55d1ec3` | [agno-agi__agno.md](evaluations/agno-agi__agno.md) |
| `crewAIInc/crewAI` | `7cd52acbe8af` | [crewAIInc__crewAI.md](evaluations/crewAIInc__crewAI.md) |
| `dapr/dapr-agents` | `80288c59c6a0` | [dapr__dapr-agents.md](evaluations/dapr__dapr-agents.md) |
| `deepset-ai/haystack` | `bbf5b2b42967` | [deepset-ai__haystack.md](evaluations/deepset-ai__haystack.md) |
| `google-gemini/gemini-cli` | `f10b8c7657ab` | [google-gemini__gemini-cli.md](evaluations/google-gemini__gemini-cli.md) |
| `google/adk-python` | `c890aa317f61` | [google__adk-python.md](evaluations/google__adk-python.md) |
| `huggingface/smolagents` | `2689e450364d` | [huggingface__smolagents.md](evaluations/huggingface__smolagents.md) |
| `langchain4j/langchain4j` | `52636becdb57` | [langchain4j__langchain4j.md](evaluations/langchain4j__langchain4j.md) |
| `mastra-ai/mastra` | `8cadd3bc68a6` | [mastra-ai__mastra.md](evaluations/mastra-ai__mastra.md) |
| `MoonshotAI/kimi-code` | `84439d5f4ec7` | [MoonshotAI__kimi-code.md](evaluations/MoonshotAI__kimi-code.md) |
| `openai/codex` | `8e9746b19d20` | [openai__codex.md](evaluations/openai__codex.md) |
| `openai/openai-agents-python` | `91fb508a8931` | [openai__openai-agents-python.md](evaluations/openai__openai-agents-python.md) |
| `QwenLM/qwen-code` | `d9ac287c9fd5` | [QwenLM__qwen-code.md](evaluations/QwenLM__qwen-code.md) |
| `strands-agents/harness-sdk` | `9faf8a49a000` | [strands-agents__harness-sdk.md](evaluations/strands-agents__harness-sdk.md) |
