# RedAmon non-UI runtime review

## 1. Snapshot, scope, and elapsed-time evidence

Reviewed the local checkout under `repos/samugit83__redamon` at **0f6420aed8be78257046080218100dff8a2ea22f**. The initial and closing HEAD checks returned that full revision, and each porcelain status check reported no changes. I read the entire evaluation protocol before tracing application behavior. The timing below is fresh to this review. The previous draft and its runtime, results, and timings did not contribute to the reported elapsed interval. [evaluations/README.md:1](./README.md:1)

The review covers the agent's request and session lifecycle, local jobs and staging, the separately owned scheduler and container control plane, plugin and provider boundaries, and the event, log, and persistence paths. The most consequential local failures concern incomplete file writes, destructive recovery after a failed restore, and unfinished transcript saves. Source-supported cases extend the analysis to durable claims and process replacement. UI behavior and product-domain procedures are outside the scope.

| UTC checkpoint on 2026-11-19 | Active work |
| --- | --- |
| 07:30:57 | Verified HEAD and the clean checkout. Read the evaluation protocol, scoped repository rules, and sections of the previous report before independent source tracing. |
| 07:33:22 | Checked job, workspace, and emitter tests. Inspected filesystem and version constraints and resolved the first harness issue. |
| 07:35:55 | Traced and exercised uploaded byte counts, session handoff, pre-start cleanup, swap recovery, and alternate Python and filesystem controls. |
| 07:38:52 | Traced socket/task ownership, transcript barriers, checkpoint setup and closure, and provider bindings. Checked in-flight and on-disk controls. |
| 07:42:33 | Traced plugin readiness, worker cancellation, completion reporting, and the server's paired storage boundary. Verified progress and terminal predicates with a deterministic store double. |
| 07:46:20 | Compared queue guard and admission logic, verified source calendar behavior against independent reference arithmetic, and repeated the Python controls on the declared runtime minor version. |
| 07:50:17 | Checked restart and queue state against the owning stores, source fixtures, and the process-maintenance path. Finished the expanded selected unit and passive syntax runs. |
| 07:52:00 | Verified real filesystem permission and space errors, and the unmodified extraction cancellation grace. Audited scope of the negative cases. |
| 07:56:06 | Confirmed separate-process local job recovery, checked measurement alternatives, and assembled the exact test replays for verification. |
| 07:59:16 | Replayed the appendix, checked logging and SDK controls, and verified adjacent lifespan and scheduler contracts. |
| 08:03:04 | Completed source-anchor, evidence, report structure, and clean-checkout verification. |

The elapsed interval is **32 whole minutes** from the first snapshot to the closing evidence check. The checkpoints cover source tracing, controlled experiments, call-path verification, and citation verification. No idle wait was used to reach the interval. A final checker compared 95 cited files byte for byte with their HEAD blobs and verified 279 distinct line anchors.

## 2. Core architecture and end-to-end control/data flow

The service composition separates three Python owners. The agent API owns conversational and workspace tasks. The recon orchestrator owns the lifecycle and resource accounting of separately managed containers. The optional plugin supervisor owns versioned worker processes. The web application's server routes own project and conversation records, scheduled occurrences, queue and history rows, and plugin job records. PostgreSQL holds those records and the optional agent checkpoints. Neo4j stores graph data behind a shared client whose mixins separate connection lifecycle and data operations. The agent also isolates selected blocking graph reads in a small executor. Bind-mounted workspace and log directories carry files, transfer staging, job metadata, and diagnostics. The plugin gateway is the boundary between the optional runner and the server, and the runner mounts the extension code read-only. [docker-compose.yml:23](repos/samugit83__redamon/docker-compose.yml:23) [docker-compose.yml:51](repos/samugit83__redamon/docker-compose.yml:51) [graph_db/neo4j_client.py:26](repos/samugit83__redamon/graph_db/neo4j_client.py:26) [agentic/neo4j_read_pool.py:15](repos/samugit83__redamon/agentic/neo4j_read_pool.py:15) [docker-compose.yml:457](repos/samugit83__redamon/docker-compose.yml:457) [docker-compose.yml:878](repos/samugit83__redamon/docker-compose.yml:878) [docker-compose.yml:979](repos/samugit83__redamon/docker-compose.yml:979) [docker-compose.yml:995](repos/samugit83__redamon/docker-compose.yml:995) [docker-compose.yml:1112](repos/samugit83__redamon/docker-compose.yml:1112) [docker-compose.yml:1470](repos/samugit83__redamon/docker-compose.yml:1470) [docker-compose.yml:1517](repos/samugit83__redamon/docker-compose.yml:1517)

### Agent HTTP, streaming, and checkpointing

Uvicorn loads the FastAPI app. Its lifespan checks the process assumption, initializes the orchestrator and connection manager, recovers old job records and staged swaps, clears disposable staging, starts idle-session cleanup, and attaches the job-event emitter. FastAPI combines local routes with included routers. The workspace router checks its internal request boundary, shapes body and offset errors, and delegates to project-scoped session and job methods. The WebSocket app route delegates to a receive loop that decodes and dispatches frames. Admission and typed validation happen at the handler boundary. The agent lifespan cancels the idle sweeper and calls the orchestrator's close method at shutdown. Per-run finalizers and boot recovery handle their own resources. [agentic/Dockerfile:239](repos/samugit83__redamon/agentic/Dockerfile:239) [agentic/api.py:72](repos/samugit83__redamon/agentic/api.py:72) [agentic/api.py:103](repos/samugit83__redamon/agentic/api.py:103) [agentic/api.py:148](repos/samugit83__redamon/agentic/api.py:148) [agentic/api.py:154](repos/samugit83__redamon/agentic/api.py:154) [agentic/api.py:186](repos/samugit83__redamon/agentic/api.py:186) [agentic/api.py:6034](repos/samugit83__redamon/agentic/api.py:6034) [agentic/workspace_import/http_routes.py:31](repos/samugit83__redamon/agentic/workspace_import/http_routes.py:31) [agentic/workspace_import/http_routes.py:59](repos/samugit83__redamon/agentic/workspace_import/http_routes.py:59) [agentic/websocket_api.py:2526](repos/samugit83__redamon/agentic/websocket_api.py:2526) [agentic/websocket_api.py:2582](repos/samugit83__redamon/agentic/websocket_api.py:2582)

The manager keys connections, active run tasks, and callbacks by user, project, and session. A query checks permission to start given the project's current writers, queues the user event for persistence, registers a background task, and returns control to the receive loop. A verified replacement socket can inherit the run's connection-local state. The callback finds the current socket at send time, while the active task registry answers liveness. Disconnect preserves an active task. Explicit stop paths cancel the registered work and delegate termination to the owner of associated processes. Completion releases the task by identity, drains the callback's persistence worker, releases that callback by identity, and requests a conversation status update. [agentic/websocket_api.py:321](repos/samugit83__redamon/agentic/websocket_api.py:321) [agentic/websocket_api.py:405](repos/samugit83__redamon/agentic/websocket_api.py:405) [agentic/websocket_api.py:464](repos/samugit83__redamon/agentic/websocket_api.py:464) [agentic/websocket_api.py:522](repos/samugit83__redamon/agentic/websocket_api.py:522) [agentic/websocket_api.py:598](repos/samugit83__redamon/agentic/websocket_api.py:598) [agentic/websocket_api.py:673](repos/samugit83__redamon/agentic/websocket_api.py:673) [agentic/websocket_api.py:1034](repos/samugit83__redamon/agentic/websocket_api.py:1034) [agentic/websocket_api.py:1889](repos/samugit83__redamon/agentic/websocket_api.py:1889) [agentic/websocket_api.py:1921](repos/samugit83__redamon/agentic/websocket_api.py:1921) [agentic/websocket_api.py:2631](repos/samugit83__redamon/agentic/websocket_api.py:2631)

The orchestrator compiles a LangGraph over a typed state dictionary. The run binds its settings and provider client, passes a checkpoint identity and separate project data scope in the invocation config, and streams state snapshots into a callback until it produces a response or pauses for input. The module starts with an in-memory saver. If persistent setup succeeds, it installs an asynchronous PostgreSQL saver before graph compilation. A checkpoint carries logical state. Live sockets, tasks, queues, and process ownership are held by their respective runtimes. Transcript entries take a separate path through a callback-local FIFO to the server's conversation store. [agentic/orchestrator.py:69](repos/samugit83__redamon/agentic/orchestrator.py:69) [agentic/orchestrator.py:121](repos/samugit83__redamon/agentic/orchestrator.py:121) [agentic/orchestrator.py:191](repos/samugit83__redamon/agentic/orchestrator.py:191) [agentic/orchestrator.py:546](repos/samugit83__redamon/agentic/orchestrator.py:546) [agentic/orchestrator.py:755](repos/samugit83__redamon/agentic/orchestrator.py:755) [agentic/orchestrator.py:1122](repos/samugit83__redamon/agentic/orchestrator.py:1122) [agentic/orchestrator.py:1188](repos/samugit83__redamon/agentic/orchestrator.py:1188) [agentic/orchestrator_helpers/config.py:43](repos/samugit83__redamon/agentic/orchestrator_helpers/config.py:43) [agentic/state.py:984](repos/samugit83__redamon/agentic/state.py:984) [agentic/websocket_api.py:949](repos/samugit83__redamon/agentic/websocket_api.py:949) [agentic/orchestrator_helpers/chat_persistence.py:23](repos/samugit83__redamon/agentic/orchestrator_helpers/chat_persistence.py:23)

### Local files and background jobs

An upload creates staging outside the project tree and reserves capacity. Each chunk is bounded, serialized by an upload lock, and acknowledged by offset. Commit hands the complete session to a background job and returns an ID. The runner optionally extracts on a dedicated pool, verifies the project still exists, and places the staged entry under a destination lock. Replacement records the relationship between the old entry and target before the two renames. The normal job cleanup releases the busy marker and reservation and removes staging. Idle sessions, project reset, and startup provide additional cleanup paths. The URL import path delegates source inspection to its adapter and reuses the stage, place, and job interfaces. [agentic/workspace_import/http_routes.py:142](repos/samugit83__redamon/agentic/workspace_import/http_routes.py:142) [agentic/workspace_import/http_routes.py:163](repos/samugit83__redamon/agentic/workspace_import/http_routes.py:163) [agentic/workspace_import/http_routes.py:211](repos/samugit83__redamon/agentic/workspace_import/http_routes.py:211) [agentic/workspace_import/upload_sessions.py:89](repos/samugit83__redamon/agentic/workspace_import/upload_sessions.py:89) [agentic/workspace_import/upload_sessions.py:149](repos/samugit83__redamon/agentic/workspace_import/upload_sessions.py:149) [agentic/workspace_import/upload_sessions.py:189](repos/samugit83__redamon/agentic/workspace_import/upload_sessions.py:189) [agentic/workspace_import/upload_job.py:50](repos/samugit83__redamon/agentic/workspace_import/upload_job.py:50) [agentic/workspace_import/upload_job.py:101](repos/samugit83__redamon/agentic/workspace_import/upload_job.py:101) [agentic/workspace_import/jobs_common.py:53](repos/samugit83__redamon/agentic/workspace_import/jobs_common.py:53) [agentic/workspace_import/place.py:100](repos/samugit83__redamon/agentic/workspace_import/place.py:100) [agentic/workspace_import/http_routes.py:297](repos/samugit83__redamon/agentic/workspace_import/http_routes.py:297) [agentic/workspace_import/runner.py:228](repos/samugit83__redamon/agentic/workspace_import/runner.py:228)

The registry's process-wide admission lock counts running handles before accepting a job. Workspace work and governed background work use separate limits. The in-memory handle owns a task, contains project and lifecycle facts, and excludes the task from serialized metadata. The runner returns a success or failure mapping, or raises. Progress updates use task context and throttle interim metadata writes to one per second. The registry records terminal state, timestamps it, persists a snapshot to disk, and emits a best-effort update. Polling can read a former process's metadata. Boot labels a persisted **running** job **interrupted**. Recovery stops at the stored status. [agentic/job_runner.py:61](repos/samugit83__redamon/agentic/job_runner.py:61) [agentic/job_runner.py:105](repos/samugit83__redamon/agentic/job_runner.py:105) [agentic/job_runner.py:129](repos/samugit83__redamon/agentic/job_runner.py:129) [agentic/job_runner.py:171](repos/samugit83__redamon/agentic/job_runner.py:171) [agentic/job_runner.py:206](repos/samugit83__redamon/agentic/job_runner.py:206) [agentic/job_runner.py:237](repos/samugit83__redamon/agentic/job_runner.py:237) [agentic/job_runner.py:282](repos/samugit83__redamon/agentic/job_runner.py:282) [agentic/job_runner.py:300](repos/samugit83__redamon/agentic/job_runner.py:300) [agentic/job_runner.py:374](repos/samugit83__redamon/agentic/job_runner.py:374)

### Scheduled work and separate process ownership

The orchestrator lifespan starts a scheduler, a dispatcher, and a periodic reaper alongside its container manager. The scheduler reads due occurrences. The server handles authorization, advances the schedule, records the outcome, and persists temporary deferrals to the queue. An unknown start has a distinct disposition because an absent acknowledgement leaves execution ambiguous. The dispatcher consults the resource snapshot and requests a durable conditional claim. The queue can move from **queued** to **dispatching**, then **running**, a terminal state, or back to **queued** for later. Configuration drift can require review. Capacity waits keep the attempt allowance, while answered transient failures spend it. Reconciliation closes deferred bookkeeping using runtime information and keeps detailed execution history separately. [recon_orchestrator/api.py:770](repos/samugit83__redamon/recon_orchestrator/api.py:770) [recon_orchestrator/scan_scheduler.py:68](repos/samugit83__redamon/recon_orchestrator/scan_scheduler.py:68) [recon_orchestrator/job_dispatcher.py:80](repos/samugit83__redamon/recon_orchestrator/job_dispatcher.py:80) [webapp/src/app/api/internal/scan-schedules/\[scheduleId\]/run/route.ts:190](repos/samugit83__redamon/webapp/src/app/api/internal/scan-schedules/[scheduleId]/run/route.ts:190) [webapp/src/app/api/internal/job-queue/\[id\]/dispatch/route.ts:164](repos/samugit83__redamon/webapp/src/app/api/internal/job-queue/[id]/dispatch/route.ts:164) [webapp/src/app/api/internal/job-queue/\[id\]/dispatch/route.ts:268](repos/samugit83__redamon/webapp/src/app/api/internal/job-queue/[id]/dispatch/route.ts:268) [webapp/src/app/api/internal/job-queue/\[id\]/dispatch/route.ts:302](repos/samugit83__redamon/webapp/src/app/api/internal/job-queue/[id]/dispatch/route.ts:302) [webapp/src/app/api/internal/job-queue/reconcile/route.ts:146](repos/samugit83__redamon/webapp/src/app/api/internal/job-queue/reconcile/route.ts:146) [webapp/prisma/schema.prisma:2251](repos/samugit83__redamon/webapp/prisma/schema.prisma:2251)

The authoritative reservation ledger budgets expected peak demand and checks physical headroom. It releases by owner key and periodically reconciles against work still occupying the host, including tracked draining or paused work. The container manager gives long-lived log readers a different executor from short blocking control calls. Server-sent event delivery uses a bounded handoff from the log reader thread. The generator signals stop and closes the source when its consumer leaves. Orderly shutdown attempts to stop tracked workers. Startup source acknowledges that daemon-owned work can survive an abrupt API-process restart without a corresponding live in-memory handle. Queue records, execution history, and container state therefore have distinct semantics after restart. [recon_orchestrator/admission_ledger.py:181](repos/samugit83__redamon/recon_orchestrator/admission_ledger.py:181) [recon_orchestrator/admission_ledger.py:243](repos/samugit83__redamon/recon_orchestrator/admission_ledger.py:243) [recon_orchestrator/admission_ledger.py:272](repos/samugit83__redamon/recon_orchestrator/admission_ledger.py:272) [recon_orchestrator/container_manager.py:565](repos/samugit83__redamon/recon_orchestrator/container_manager.py:565) [recon_orchestrator/container_manager.py:716](repos/samugit83__redamon/recon_orchestrator/container_manager.py:716) [recon_orchestrator/container_manager.py:2324](repos/samugit83__redamon/recon_orchestrator/container_manager.py:2324) [recon_orchestrator/container_manager.py:2468](repos/samugit83__redamon/recon_orchestrator/container_manager.py:2468) [recon_orchestrator/api.py:628](repos/samugit83__redamon/recon_orchestrator/api.py:628) [recon_orchestrator/api.py:799](repos/samugit83__redamon/recon_orchestrator/api.py:799)

### Plugin and provider contracts

Plugin server routes validate a declared action and its request context. For async work the server creates a durable job plus an active uniqueness record, then asks the runner to accept it. The supervisor resolves the requested version, checks the declared action and timeout, and owns the async reporting task. Internally a worker handle correlates newline-framed JSON requests and replies by ID across a process boundary. Plugin code receives an immutable per-call context with a transport-backed SDK. The supervisor keeps protocol communication and worker diagnostics separate. It bounds concurrent calls per worker, asks for cooperative cancellation, and escalates if the worker does not respond. The server fences terminal jobs, and a deadline or changed supervisor boot ID can resolve an outstanding record. [webapp/src/lib/plugins/actions.ts:259](repos/samugit83__redamon/webapp/src/lib/plugins/actions.ts:259) [webapp/src/lib/plugins/actions.ts:345](repos/samugit83__redamon/webapp/src/lib/plugins/actions.ts:345) [webapp/src/lib/plugins/jobs.ts:202](repos/samugit83__redamon/webapp/src/lib/plugins/jobs.ts:202) [webapp/src/lib/plugins/jobs.ts:314](repos/samugit83__redamon/webapp/src/lib/plugins/jobs.ts:314) [services/plugin_runner/supervisor/app.py:108](repos/samugit83__redamon/services/plugin_runner/supervisor/app.py:108) [services/plugin_runner/supervisor/workers.py:294](repos/samugit83__redamon/services/plugin_runner/supervisor/workers.py:294) [services/plugin_runner/supervisor/workers.py:399](repos/samugit83__redamon/services/plugin_runner/supervisor/workers.py:399) [services/plugin_runner/worker/bootstrap.py:263](repos/samugit83__redamon/services/plugin_runner/worker/bootstrap.py:263) [services/plugin_runner/sdk/redamon_plugin_sdk/context.py:12](repos/samugit83__redamon/services/plugin_runner/sdk/redamon_plugin_sdk/context.py:12)

Model handling uses a common asynchronous chat interface with vendor-specific construction and structured error normalization at its edges. Session setup binds a client through a ContextVar and caches by model, provider configuration fingerprint, and owner. The exact-provider builder, used on isolated feature boundaries, requires the configured custom or instance row. The session settings path can use a legacy fallback for a recreated custom provider. The optional broker-backed model uses run-owned futures with scoped cleanup and implements the same async result interface. Plugin data and progress use the SDK transport interface, which has an in-memory fake. These seams support local tests with synthetic inputs. The agent also holds a process-wide lease on its configured extension catalog while a run streams. A conflicting catalog for a different owner can be deferred, protecting the live run from a configuration swap. [agentic/orchestrator.py:137](repos/samugit83__redamon/agentic/orchestrator.py:137) [agentic/llm_builder.py:250](repos/samugit83__redamon/agentic/llm_builder.py:250) [agentic/llm_builder.py:270](repos/samugit83__redamon/agentic/llm_builder.py:270) [agentic/llm_builder.py:345](repos/samugit83__redamon/agentic/llm_builder.py:345) [agentic/orchestrator_helpers/llm_setup.py:536](repos/samugit83__redamon/agentic/orchestrator_helpers/llm_setup.py:536) [agentic/orchestrator_helpers/llm_setup.py:626](repos/samugit83__redamon/agentic/orchestrator_helpers/llm_setup.py:626) [agentic/agent_in_the_loop/model.py:28](repos/samugit83__redamon/agentic/agent_in_the_loop/model.py:28) [agentic/agent_in_the_loop/broker.py:307](repos/samugit83__redamon/agentic/agent_in_the_loop/broker.py:307) [agentic/agent_in_the_loop/broker.py:388](repos/samugit83__redamon/agentic/agent_in_the_loop/broker.py:388) [agentic/orchestrator.py:1101](repos/samugit83__redamon/agentic/orchestrator.py:1101) [agentic/mcp_toolset_guard.py:88](repos/samugit83__redamon/agentic/mcp_toolset_guard.py:88) [services/plugin_runner/sdk/redamon_plugin_sdk/client.py:350](repos/samugit83__redamon/services/plugin_runner/sdk/redamon_plugin_sdk/client.py:350) [services/plugin_runner/sdk/redamon_plugin_sdk/testing.py:564](repos/samugit83__redamon/services/plugin_runner/sdk/redamon_plugin_sdk/testing.py:564)

## 3. Why the design works and its governing invariants

| Invariant or design contract | Mechanism and rationale |
| --- | --- |
| In-memory registries have one process owner. | The default agent command has one worker and the startup guard checks advertised worker counts. The process-local locks, task references, and workspace reservation records rely on that placement. The guard explicitly documents that its environment checks cannot see a bare CLI worker override. [agentic/Dockerfile:239](repos/samugit83__redamon/agentic/Dockerfile:239) [agentic/startup_guard.py:38](repos/samugit83__redamon/agentic/startup_guard.py:38) [agentic/workspace_import/staging.py:82](repos/samugit83__redamon/agentic/workspace_import/staging.py:82) |
| Live identity survives reconnect. | The socket and the active task are separate references. Release compares object identity, so an old operation cannot erase the replacement entry through that release path. A separate conversation flag serves as persisted metadata. [agentic/websocket_api.py:481](repos/samugit83__redamon/agentic/websocket_api.py:481) [agentic/websocket_api.py:522](repos/samugit83__redamon/agentic/websocket_api.py:522) [agentic/websocket_api.py:531](repos/samugit83__redamon/agentic/websocket_api.py:531) [agentic/websocket_api.py:598](repos/samugit83__redamon/agentic/websocket_api.py:598) |
| File visibility has a deliberate publication point. | Staging starts invisible to project readers. While an operation is active, admission and busy checks limit contention, the destination lock serializes placement, and recovery can put back an old entry from a replace journal. The failure branches of that last contract are examined in §4. [agentic/workspace_import/staging.py:37](repos/samugit83__redamon/agentic/workspace_import/staging.py:37) [agentic/workspace_import/staging.py:151](repos/samugit83__redamon/agentic/workspace_import/staging.py:151) [agentic/workspace_import/busy.py:50](repos/samugit83__redamon/agentic/workspace_import/busy.py:50) [agentic/workspace_import/place.py:100](repos/samugit83__redamon/agentic/workspace_import/place.py:100) |
| A request timeout can leave a job in progress. | The job owns its task. A wait shields the task so the observer can time out without cancelling the work. Explicit cancellation has a separate status transition and accounts for cancellation before the task's first step. [agentic/job_runner.py:300](repos/samugit83__redamon/agentic/job_runner.py:300) [agentic/job_runner.py:312](repos/samugit83__redamon/agentic/job_runner.py:312) |
| A committed terminal state takes precedence over a late update. | Both server-backed queue families use conditional state transitions. Local plugin completion is a report to the database owner. The job's prior status fences cancellation and completion. The condition protects the lifecycle field, with a narrower guarantee for other fields in the same JSON row. [webapp/src/app/api/internal/job-queue/\[id\]/dispatch/route.ts:306](repos/samugit83__redamon/webapp/src/app/api/internal/job-queue/[id]/dispatch/route.ts:306) [webapp/src/lib/plugins/jobs.ts:151](repos/samugit83__redamon/webapp/src/lib/plugins/jobs.ts:151) [webapp/src/lib/plugins/jobs.ts:167](repos/samugit83__redamon/webapp/src/lib/plugins/jobs.ts:167) [webapp/src/lib/plugins/jobs.ts:370](repos/samugit83__redamon/webapp/src/lib/plugins/jobs.ts:370) |
| Buffering, delivery, persistence, and recovery have separate acknowledgements. | Runtime frames are advisory, callback FIFO provides local ordering, project job metadata supports polling, and persisted records have their own ordering and recovery. Diagnostics and readiness also have different authorities. [agentic/ws_job_emitter.py:43](repos/samugit83__redamon/agentic/ws_job_emitter.py:43) [agentic/websocket_api.py:959](repos/samugit83__redamon/agentic/websocket_api.py:959) [agentic/job_runner.py:282](repos/samugit83__redamon/agentic/job_runner.py:282) [webapp/src/app/api/conversations/by-session/\[sessionId\]/messages/route.ts:74](repos/samugit83__redamon/webapp/src/app/api/conversations/by-session/[sessionId]/messages/route.ts:74) [services/plugin_runner/supervisor/manager.py:147](repos/samugit83__redamon/services/plugin_runner/supervisor/manager.py:147) |


## 4. What it does well and poorly, with source evidence

The best boundaries are the task registries and the explicit separation of socket, job, and process ownership, the separation of runtime capacity from durable claims, and the dependency-light storage and event seams. Versioned plugin workers give request isolation by process identity and use separate protocol and log streams. The checked-in test layout makes it possible to verify those seams without the service stack. Most weaknesses below occur when a task hands over responsibility for a resource, a durable write, or a pending event. [agentic/job_runner.py:88](repos/samugit83__redamon/agentic/job_runner.py:88) [agentic/workspace_import/executor.py:38](repos/samugit83__redamon/agentic/workspace_import/executor.py:38) [recon_orchestrator/admission_ledger.py:181](repos/samugit83__redamon/recon_orchestrator/admission_ledger.py:181) [services/plugin_runner/supervisor/workers.py:294](repos/samugit83__redamon/services/plugin_runner/supervisor/workers.py:294) [agentic/conftest.py:21](repos/samugit83__redamon/agentic/conftest.py:21)

| Finding | Mechanism and evidence |
| --- | --- |
| **W1 · High · Reproduced.** File bytes can diverge from acknowledged progress. | The coroutine awaits an append in a thread, then advances its offset. Cancelling that await can leave the actual write running. A partial write followed by a mapped storage error reaches the same stale-counter state. Retry appends at the physical end. Commit trusts the counter and the ordinary file placement uses the actual bytes. The fixture committed six bytes after cancellation, or four after injected quota failure, with three acknowledged in each case. [agentic/workspace_import/upload_sessions.py:179](repos/samugit83__redamon/agentic/workspace_import/upload_sessions.py:179) [agentic/workspace_import/upload_sessions.py:197](repos/samugit83__redamon/agentic/workspace_import/upload_sessions.py:197) [agentic/workspace_import/upload_sessions.py:236](repos/samugit83__redamon/agentic/workspace_import/upload_sessions.py:236) [agentic/workspace_import/upload_job.py:59](repos/samugit83__redamon/agentic/workspace_import/upload_job.py:59) [agentic/workspace_import/place.py:73](repos/samugit83__redamon/agentic/workspace_import/place.py:73) |
| **W2 and W3 · High · Reproduced.** Staging can lose its owner during handoff. | Commit takes the session out of the table before spawning. The registry inserts the handle before creating its log. Throwing at log creation leaves a running handle with no task, a retained reservation and staging file, and a session the idle sweeper cannot see. The handled capacity-refusal path restores the session. In a separate path, pre-start cancellation correctly sets job status but the runner that releases the reservation never enters its cleanup block. [agentic/workspace_import/upload_job.py:101](repos/samugit83__redamon/agentic/workspace_import/upload_job.py:101) [agentic/workspace_import/upload_job.py:108](repos/samugit83__redamon/agentic/workspace_import/upload_job.py:108) [agentic/job_runner.py:206](repos/samugit83__redamon/agentic/job_runner.py:206) [agentic/job_runner.py:312](repos/samugit83__redamon/agentic/job_runner.py:312) [agentic/workspace_import/upload_sessions.py:89](repos/samugit83__redamon/agentic/workspace_import/upload_sessions.py:89) |
| **W4 · High · Reproduced.** An unsuccessful restore can discard the previous copy. | Placement retains the old entry if promotion and immediate rollback both fail. Boot attempts restoration and removes the trash after a restore exception. Its later generic sweep also removes staging. A single injected EIO on recovery of a valid record left neither the target nor its staged previous copy. [agentic/workspace_import/place.py:90](repos/samugit83__redamon/agentic/workspace_import/place.py:90) [agentic/workspace_import/place.py:126](repos/samugit83__redamon/agentic/workspace_import/place.py:126) [agentic/workspace_import/staging.py:173](repos/samugit83__redamon/agentic/workspace_import/staging.py:173) [agentic/workspace_import/staging.py:193](repos/samugit83__redamon/agentic/workspace_import/staging.py:193) [agentic/api.py:110](repos/samugit83__redamon/agentic/api.py:110) |
| **W5 · Medium · Reproduced on a bounded cancellation path.** | Extraction checks cancellation before reading a chunk and calls the reservation callback after that read. The await can give up after its grace, at which point caller cleanup releases the ledger entry. A worker returning from that read can enter the growth loop with a released reservation. Its increment is then a no-op and its loop has no progress check. The bounded fixture observed five unchanged iterations. The normal grace is 30 seconds. [agentic/workspace_import/extract.py:225](repos/samugit83__redamon/agentic/workspace_import/extract.py:225) [agentic/workspace_import/jobs_common.py:15](repos/samugit83__redamon/agentic/workspace_import/jobs_common.py:15) [agentic/workspace_import/jobs_common.py:65](repos/samugit83__redamon/agentic/workspace_import/jobs_common.py:65) [agentic/workspace_import/jobs_common.py:103](repos/samugit83__redamon/agentic/workspace_import/jobs_common.py:103) [agentic/workspace_import/staging.py:133](repos/samugit83__redamon/agentic/workspace_import/staging.py:133) [agentic/workspace_import/upload_job.py:101](repos/samugit83__redamon/agentic/workspace_import/upload_job.py:101) |
| **E1 · High · Reproduced.** Persistence can close with a save in flight. | The callback queue counts buffered items. Its worker removes an item before awaiting the save. Reconnect's zero-buffer fast path can report success while a write is pending, and the final drain can cancel that same write. The save await precedes the block that calls task_done. The fixture observed one unfinished item after cancellation. The two-item control joined both saves in order. [agentic/websocket_api.py:959](repos/samugit83__redamon/agentic/websocket_api.py:959) [agentic/websocket_api.py:1004](repos/samugit83__redamon/agentic/websocket_api.py:1004) [agentic/websocket_api.py:1011](repos/samugit83__redamon/agentic/websocket_api.py:1011) [agentic/websocket_api.py:1839](repos/samugit83__redamon/agentic/websocket_api.py:1839) [agentic/websocket_api.py:1889](repos/samugit83__redamon/agentic/websocket_api.py:1889) |
| **E3 · Medium · Reproduced with a synthetic pool.** The resource owner omits pool closure. | Saver setup can fail after the pool has been opened and before assignment to the owner. The exception branch clears the ownership attribute. Successful setup attaches the pool, while the shutdown method only closes a knowledge-base driver. The fake observed an open and zero closes on each path. This verifies the application's ownership contract. The live driver's reclamation behavior is outside the fixture. [agentic/orchestrator.py:191](repos/samugit83__redamon/agentic/orchestrator.py:191) [agentic/orchestrator.py:1558](repos/samugit83__redamon/agentic/orchestrator.py:1558) [agentic/api.py:148](repos/samugit83__redamon/agentic/api.py:148) |
| **E4 · Medium · Reproduced.** A disconnected session can keep an admission slot. | The receive-loop cleanup skips removing the connection when its task is active. Run finalization later clears the task and callback, leaving that connection entry. The admission cap includes connection keys. At a synthetic cap of one, a new session was refused after the disconnected task had exited. Verified replacement and disconnect of an idle session were effective controls. [agentic/websocket_api.py:425](repos/samugit83__redamon/agentic/websocket_api.py:425) [agentic/websocket_api.py:481](repos/samugit83__redamon/agentic/websocket_api.py:481) [agentic/websocket_api.py:1889](repos/samugit83__redamon/agentic/websocket_api.py:1889) [agentic/websocket_api.py:2631](repos/samugit83__redamon/agentic/websocket_api.py:2631) |
| **J1 · Medium · Reproduced.** An observer can get different results for the same cancellation. | The shield protects a job from the observer's timeout or cancellation. When the child itself is cancelled, its shield raises CancelledError. The method catches TimeoutError and ordinary exceptions. An in-flight observer raised, while a later call read the already-terminal snapshot. Explicit cancel returns the cancelled snapshot. [agentic/job_runner.py:254](repos/samugit83__redamon/agentic/job_runner.py:254) [agentic/job_runner.py:300](repos/samugit83__redamon/agentic/job_runner.py:300) [agentic/job_runner.py:312](repos/samugit83__redamon/agentic/job_runner.py:312) |
| **J3 · Medium · Reproduced under a partial-write fault.** Persisted metadata can become unreadable. | Direct replacement of the text in the live metadata file can tear. A failed final write logs an error and leaves memory available. After a new registry reads the damaged file, status reports it unreadable, listing omits it, and boot reconciliation cannot derive its prior state. A previously durable snapshot would be useful in precisely this case. [agentic/job_runner.py:153](repos/samugit83__redamon/agentic/job_runner.py:153) [agentic/job_runner.py:261](repos/samugit83__redamon/agentic/job_runner.py:261) [agentic/job_runner.py:282](repos/samugit83__redamon/agentic/job_runner.py:282) [agentic/job_runner.py:332](repos/samugit83__redamon/agentic/job_runner.py:332) [agentic/job_runner.py:374](repos/samugit83__redamon/agentic/job_runner.py:374) |
| **J4 · Medium · Reproduced.** Live job frames can arrive in reverse order. | The job task is created before the spawn method awaits its running notice. The fan-out visits recipients sequentially and awaits each send. With one earlier recipient gated on the running event, a second recipient saw **done** before **running**. Persisted and polled status remained terminal. [agentic/job_runner.py:161](repos/samugit83__redamon/agentic/job_runner.py:161) [agentic/job_runner.py:261](repos/samugit83__redamon/agentic/job_runner.py:261) [agentic/job_runner.py:273](repos/samugit83__redamon/agentic/job_runner.py:273) [agentic/ws_job_emitter.py:60](repos/samugit83__redamon/agentic/ws_job_emitter.py:60) [agentic/websocket_api.py:267](repos/samugit83__redamon/agentic/websocket_api.py:267) |
| **J5 · Medium · Reproduced.** A small tail response allocates in proportion to the complete log. | Status reads all lines synchronously before slicing 40. The narrower workspace status route still computes this tail before discarding it. Two synthetic logs produced the same 5,120-byte tail with sharply different allocations. One newline-terminated line returned 262,145 bytes. Synchronous cost and response size are distinct. [agentic/job_runner.py:282](repos/samugit83__redamon/agentic/job_runner.py:282) [agentic/job_runner.py:366](repos/samugit83__redamon/agentic/job_runner.py:366) [agentic/workspace_import/http_routes.py:126](repos/samugit83__redamon/agentic/workspace_import/http_routes.py:126) |
| **P1 and P2 · Medium · Reproduced at supervisor boundaries.** | A changed run list removes the old version from lookups before the replacement reports ready. A failed start still leads to stopping the old handle. Top-level health can remain **ok** because it records acceptance of a version-compatible run list, with worker state carried separately. There is also no join on report tasks cancelled by stop_all. The controls verified both state transitions. At the application boundary, the server refuses new actions during updates and checks the exact worker's readiness after changing the active version. [services/plugin_runner/supervisor/manager.py:61](repos/samugit83__redamon/services/plugin_runner/supervisor/manager.py:61) [services/plugin_runner/supervisor/manager.py:80](repos/samugit83__redamon/services/plugin_runner/supervisor/manager.py:80) [services/plugin_runner/supervisor/manager.py:123](repos/samugit83__redamon/services/plugin_runner/supervisor/manager.py:123) [services/plugin_runner/supervisor/app.py:81](repos/samugit83__redamon/services/plugin_runner/supervisor/app.py:81) [webapp/src/lib/plugins/actions.ts:267](repos/samugit83__redamon/webapp/src/lib/plugins/actions.ts:267) [webapp/src/lib/plugins/lifecycle.ts:188](repos/samugit83__redamon/webapp/src/lib/plugins/lifecycle.ts:188) |
| **P5 · Medium · Reproduced against an in-memory persistence double.** A status update can overwrite acknowledged progress. | The whole JSON value is written under a predicate on status. A progress update can commit without changing that status, so a concurrent running or completion transition can apply a stale snapshot. This is distinct from a terminal-state collision. The synthetic store rejected a late completion after cancellation as intended. [webapp/src/lib/plugins/jobs.ts:167](repos/samugit83__redamon/webapp/src/lib/plugins/jobs.ts:167) [webapp/src/lib/plugins/jobs.ts:259](repos/samugit83__redamon/webapp/src/lib/plugins/jobs.ts:259) [webapp/src/lib/plugins/jobs.ts:370](repos/samugit83__redamon/webapp/src/lib/plugins/jobs.ts:370) [webapp/src/lib/plugins/jobs.ts:412](repos/samugit83__redamon/webapp/src/lib/plugins/jobs.ts:412) |
| **Q1 and Q2 · Medium · Reproduced at local scheduling seams.** | A dispatcher guard tracks the coroutine waiting on a thread, so selective cancellation can clear it before the thread stops. The matched scope is an isolated cancellation, and the durable claim remains a separate fence. Also, the dispatcher's advisory pool test can refuse a head item while the admission ledger's empty-pool exception would allow that item under the physical-memory check. Both decisions were exercised with synthetic inputs. [recon_orchestrator/job_dispatcher.py:109](repos/samugit83__redamon/recon_orchestrator/job_dispatcher.py:109) [recon_orchestrator/job_dispatcher.py:142](repos/samugit83__redamon/recon_orchestrator/job_dispatcher.py:142) [recon_orchestrator/job_dispatcher.py:183](repos/samugit83__redamon/recon_orchestrator/job_dispatcher.py:183) [recon_orchestrator/admission_ledger.py:166](repos/samugit83__redamon/recon_orchestrator/admission_ledger.py:166) [recon_orchestrator/admission_ledger.py:250](repos/samugit83__redamon/recon_orchestrator/admission_ledger.py:250) |
| **R1 and R2 · Medium · Source-supported inference.** Two provider-adjacent paths can add latency. | Project settings resolution uses a synchronous request from async entry points, so a slow settings read can occupy the loop. Separately, the broad retry classifier consults transient text before rejecting an ordinary explicit permanent status. A 401 carrying a transient-looking phrase could be retried at call sites using that wrapper, even though the provider availability classifier treats the status as permanent. There is no observed production latency or sampled provider response. [agentic/project_settings.py:724](repos/samugit83__redamon/agentic/project_settings.py:724) [agentic/project_settings.py:1017](repos/samugit83__redamon/agentic/project_settings.py:1017) [agentic/orchestrator.py:1191](repos/samugit83__redamon/agentic/orchestrator.py:1191) [agentic/llm_builder.py:306](repos/samugit83__redamon/agentic/llm_builder.py:306) [agentic/llm_builder.py:382](repos/samugit83__redamon/agentic/llm_builder.py:382) [agentic/orchestrator_helpers/llm_retry.py:212](repos/samugit83__redamon/agentic/orchestrator_helpers/llm_retry.py:212) [agentic/orchestrator_helpers/llm_retry.py:554](repos/samugit83__redamon/agentic/orchestrator_helpers/llm_retry.py:554) |
| **Q3 · Lower · Reproduced with an independent UTC oracle.** | The gap validator assumes a next selected hour is adjacent when multiple hours and minutes are listed. This can underestimate the attainable gap and reject a valid schedule. The date search's four-year cutoff also misses leap dates across omitted century leap days. The minimum-floor validation and time search were checked separately. Neither issue requires an executing job to observe. [webapp/src/lib/cron.ts:115](repos/samugit83__redamon/webapp/src/lib/cron.ts:115) [webapp/src/lib/cron.ts:161](repos/samugit83__redamon/webapp/src/lib/cron.ts:161) [webapp/src/lib/scanSchedule.ts:45](repos/samugit83__redamon/webapp/src/lib/scanSchedule.ts:45) [webapp/src/lib/scanSchedule.ts:134](repos/samugit83__redamon/webapp/src/lib/scanSchedule.ts:134) |
| **Q4 and Q5 · High · Source-supported inference.** Scheduled work can lose its durable handoff, and a durable dispatch claim can outlive its owner. | Advancing the recurrence and inserting the deferred job are separate writes. A failure after advance can leave neither a due occurrence nor a queued job for it. A separate crash window follows the **dispatching** write. Candidate selection counts that state as in flight, while periodic reconciliation works from **running** rows. The source provides manual cancellation and access-change cleanup. [webapp/src/app/api/internal/scan-schedules/\[scheduleId\]/run/route.ts:38](repos/samugit83__redamon/webapp/src/app/api/internal/scan-schedules/[scheduleId]/run/route.ts:38) [webapp/src/app/api/internal/scan-schedules/\[scheduleId\]/run/route.ts:200](repos/samugit83__redamon/webapp/src/app/api/internal/scan-schedules/[scheduleId]/run/route.ts:200) [webapp/src/app/api/internal/job-queue/\[id\]/dispatch/route.ts:164](repos/samugit83__redamon/webapp/src/app/api/internal/job-queue/[id]/dispatch/route.ts:164) [webapp/src/app/api/internal/job-queue/candidates/route.ts:32](repos/samugit83__redamon/webapp/src/app/api/internal/job-queue/candidates/route.ts:32) [webapp/src/app/api/internal/job-queue/reconcile/route.ts:159](repos/samugit83__redamon/webapp/src/app/api/internal/job-queue/reconcile/route.ts:159) |
| **Q6 · Medium · Source-supported inference.** Surviving workers can be missing from restart accounting. | The manager initializes empty state maps. A named status request can observe a surviving process and return a live status without recording it. The periodic active set starts from the in-memory maps, so a worker in that condition can be missing from reservation and queue inputs. An existing strict expected-failure test names the mismatch. [recon_orchestrator/container_manager.py:533](repos/samugit83__redamon/recon_orchestrator/container_manager.py:533) [recon_orchestrator/container_manager.py:762](repos/samugit83__redamon/recon_orchestrator/container_manager.py:762) [recon_orchestrator/container_manager.py:793](repos/samugit83__redamon/recon_orchestrator/container_manager.py:793) [recon_orchestrator/container_manager.py:1184](repos/samugit83__redamon/recon_orchestrator/container_manager.py:1184) [recon_orchestrator/tests/test_restart_adoption.py:128](repos/samugit83__redamon/recon_orchestrator/tests/test_restart_adoption.py:128) |


## 5. Core-code quality

**Decomposition and types.** The workspace package splits HTTP parsing, session ownership, disk admission, thread execution, placement, and error presentation. The plugin service separates run-list parsing, process lifecycle, protocol, result reporting, and SDK transport. Request DTOs, the graph's typed dictionary, and plugin context and manifest data classes clarify these seams. Several cross-boundary agreements still live in plain dictionaries and string status values. The local runner's success mapping is documented in a callable type, while its failure and interrupted shapes are only enforced by execution paths. The durable queue's status column is a string and plugin progress shares a JSON record. The strongest regression cases assert what survives the handoff. [agentic/workspace_import/http_routes.py:59](repos/samugit83__redamon/agentic/workspace_import/http_routes.py:59) [agentic/workspace_import/errors.py:90](repos/samugit83__redamon/agentic/workspace_import/errors.py:90) [agentic/job_runner.py:61](repos/samugit83__redamon/agentic/job_runner.py:61) [agentic/job_runner.py:88](repos/samugit83__redamon/agentic/job_runner.py:88) [agentic/state.py:984](repos/samugit83__redamon/agentic/state.py:984) [services/plugin_runner/supervisor/runlist.py:24](repos/samugit83__redamon/services/plugin_runner/supervisor/runlist.py:24) [services/plugin_runner/sdk/redamon_plugin_sdk/context.py:12](repos/samugit83__redamon/services/plugin_runner/sdk/redamon_plugin_sdk/context.py:12) [webapp/prisma/schema.prisma:2272](repos/samugit83__redamon/webapp/prisma/schema.prisma:2272) [webapp/prisma/schema.prisma:3039](repos/samugit83__redamon/webapp/prisma/schema.prisma:3039)

**Concurrency and error propagation.** Async locks protect local admission and destination selection, and a threading lock protects the disk ledger used by both the loop and workers. ContextVars bind job progress and model identity within a run. The worker protocol uses one future per request and validates replies before resolving it. Cooperative cancellation can preserve a sibling call, while an escalation affects calls sharing that process. The supervisor distinguishes plugin-level result errors from runner errors and retries terminal reporting for transport faults, throttling, and server errors. Workspace failures are mapped to stable codes and project existence is checked before publication. The open problems are at cancellation and durable commit boundaries, as detailed in §4. [agentic/job_runner.py:93](repos/samugit83__redamon/agentic/job_runner.py:93) [agentic/workspace_import/staging.py:87](repos/samugit83__redamon/agentic/workspace_import/staging.py:87) [agentic/workspace_import/place.py:29](repos/samugit83__redamon/agentic/workspace_import/place.py:29) [agentic/agent_context.py:29](repos/samugit83__redamon/agentic/agent_context.py:29) [agentic/workspace_import/project_check.py:26](repos/samugit83__redamon/agentic/workspace_import/project_check.py:26) [services/plugin_runner/supervisor/workers.py:318](repos/samugit83__redamon/services/plugin_runner/supervisor/workers.py:318) [services/plugin_runner/supervisor/workers.py:399](repos/samugit83__redamon/services/plugin_runner/supervisor/workers.py:399) [services/plugin_runner/supervisor/workers.py:430](repos/samugit83__redamon/services/plugin_runner/supervisor/workers.py:430) [services/plugin_runner/supervisor/jobs.py:33](repos/samugit83__redamon/services/plugin_runner/supervisor/jobs.py:33)

**Logs and observability.** The agent has per-session rotating prose logs with an LRU bound on open file handlers, a separate JSONL event stream, advisory socket frames, and persisted timeline messages. The fallback log is retained when per-session handlers are evicted. The recon orchestrator reports runtime counts and resource snapshots without performing reconciliation from the stats route. The plugin supervisor exposes boot identity and worker states and has a bounded per-plugin log tail. Its process state and the durable job record explain different anomalies. The agent health flag for persistent checkpointing reports the configured setting. The optional saver can fall back and still let initialization complete, so that flag alone cannot establish which saver is active. The workspace polling path has an independent limitation in J5. [agentic/logging_config.py:100](repos/samugit83__redamon/agentic/logging_config.py:100) [agentic/logging_config.py:132](repos/samugit83__redamon/agentic/logging_config.py:132) [agentic/logging_config.py:218](repos/samugit83__redamon/agentic/logging_config.py:218) [agentic/session_log.py:49](repos/samugit83__redamon/agentic/session_log.py:49) [agentic/api.py:1834](repos/samugit83__redamon/agentic/api.py:1834) [agentic/api.py:1860](repos/samugit83__redamon/agentic/api.py:1860) [agentic/orchestrator.py:226](repos/samugit83__redamon/agentic/orchestrator.py:226) [recon_orchestrator/api.py:909](repos/samugit83__redamon/recon_orchestrator/api.py:909) [services/plugin_runner/supervisor/manager.py:147](repos/samugit83__redamon/services/plugin_runner/supervisor/manager.py:147) [services/plugin_runner/supervisor/logs.py:23](repos/samugit83__redamon/services/plugin_runner/supervisor/logs.py:23)

**Transcript sequencing, source-supported inference E5.** FIFO orders attempts from one callback. The server takes a maximum sequence number and later inserts the rows, and the schema indexes the number without a uniqueness constraint. A different writer can therefore allocate the same number. The plugin transcript reader already paginates with timestamp and row ID as tie-breakers, including a stored-duplicate test. The session reader orders by the sequence field alone. This affects what a reader can infer about global order. [agentic/websocket_api.py:949](repos/samugit83__redamon/agentic/websocket_api.py:949) [webapp/src/app/api/conversations/by-session/\[sessionId\]/messages/route.ts:74](repos/samugit83__redamon/webapp/src/app/api/conversations/by-session/[sessionId]/messages/route.ts:74) [webapp/src/app/api/conversations/by-session/\[sessionId\]/route.ts:32](repos/samugit83__redamon/webapp/src/app/api/conversations/by-session/[sessionId]/route.ts:32) [webapp/prisma/schema.prisma:2489](repos/samugit83__redamon/webapp/prisma/schema.prisma:2489) [webapp/src/lib/plugins/transcript.ts:206](repos/samugit83__redamon/webapp/src/lib/plugins/transcript.ts:206) [webapp/src/lib/plugins/transcript.ts:240](repos/samugit83__redamon/webapp/src/lib/plugins/transcript.ts:240)

**Extensibility and tests.** The runner callable, SDK transport, injectable clocks, reservation probes, emitter callback, and model constructor offer narrow test seams. The unit gate isolates collection by file because several modules replace imports and mutate globals. Many cross-service tests exercise richer boundaries that the generic probes here deliberately replace with local doubles. The agent image includes shared modules at different import roots from the checkout, and the plugin supervisor pins its Python dependencies. Those differences help explain why host collection or an ad hoc import is weak evidence about an application behavior. In the scheduler, the module overview still describes preflight capacity deferral inside the tick. The live tick implementation and its tight-ledger test place the decision on the server. [agentic/Dockerfile:194](repos/samugit83__redamon/agentic/Dockerfile:194) [agentic/AGENTS.md:64](repos/samugit83__redamon/agentic/AGENTS.md:64) [agentic/conftest.py:21](repos/samugit83__redamon/agentic/conftest.py:21) [tooling/scripts/pytest_isolated.py:1](repos/samugit83__redamon/tooling/scripts/pytest_isolated.py:1) [services/plugin_runner/requirements.txt:12](repos/samugit83__redamon/services/plugin_runner/requirements.txt:12) [services/plugin_runner/sdk/redamon_plugin_sdk/testing.py:564](repos/samugit83__redamon/services/plugin_runner/sdk/redamon_plugin_sdk/testing.py:564) [recon_orchestrator/scan_scheduler.py:2](repos/samugit83__redamon/recon_orchestrator/scan_scheduler.py:2) [recon_orchestrator/scan_scheduler.py:68](repos/samugit83__redamon/recon_orchestrator/scan_scheduler.py:68) [recon_orchestrator/tests/test_scan_scheduler.py:143](repos/samugit83__redamon/recon_orchestrator/tests/test_scan_scheduler.py:143)

## 6. Executed tests and experiments, and limitations

The fresh selected standard-library unit runs passed **146 tests across eleven subprocesses under CPython 3.11.17**. The selection was 12 registry, 5 progress, 4 workspace cap, 20 upload session, 12 staging, 11 event fan-out, 3 static boot-wiring, 18 logging, 33 reservation-ledger, 8 startup-guard, and 20 dispatcher tests. Selected tests exercise the cited modules or inspect source. A separate passive CPython 3.11 syntax and compile pass covered 45 cited Python files.

| Probe | Fresh observation |
| --- | --- |
| J1–J4, registry and fan-out | A zero-timeout waiter left the job running. Caller cancellation left the job running. Child cancellation raised in the active waiter, with cancelled visible to a subsequent observer. Injected log-open errors yielded a taskless running handle. A partial metadata write left live status done and fresh reads unreadable. With the real fan-out and send method over fake transports, a second receiver saw done then running. |
| J5, local tail | CPython 3.11.17 traced peaks of 204,521 and 3,051,001 bytes for 128 KiB and 2 MiB files, respectively. Both returned 5,120 bytes. An unbroken 256 KiB line plus newline all appeared in the tail. The peak is Python allocation inside status, independent of application request timing or process RSS. |
| J6, fresh process | A run written before an abrupt exit read as running when a second process opened the same workspace. Boot recovery changed it to interrupted, retained its last log line, and left an already completed record unchanged. The fresh process had no live handles. |
| W1–W4, actual local bytes | Normal duplicate write committed 3 bytes. The cancellation and quota-fault variants committed 6 and 4 bytes, respectively, and reported 3. A bounded tmpfs produced a real ENOSPC with the same outcome category. A tailored cap refusal preserved a complete session; injected log failure and pre-start cancellation left staging. Runtime rollback and healthy boot restore preserved the old entry. Injected restore failure removed it. Workspace controls agreed on tmpfs and Btrfs. Real directory permission tests reproduced the log-admission and recovery branches. |
| W5, bounded in-flight thread | A blocked local read resumed after release of its reservation in both a forced-expiry control and the unmodified 30-second grace. Five real ledger growth calls made zero progress before a fixture sentinel stopped the loop. A live reservation grew normally. |
| E1–E4, persistence and connection lifetime | A single in-flight save yielded an apparent flush and was cancelled by final drain. A two-entry case saved in FIFO order. Two failed saves issued one warning. A fake pool recorded no close on either setup-failure or normal shutdown. A fake disconnect event left a cap-occupying connection after the run task ended. |
| P1–P4, synthetic supervisor | A fetch refusal retained the last run list. A failed replacement stayed visible as a worker failure while the manager reported ok. Stop requested report-task cancellation ahead of its cleanup. Fake protocol replies verified per-worker concurrency and cooperative vs forced cancellation. Fake HTTP outcomes verified reporting retries, terminal refusal, payload normalization, and bounded log storage. |
| P5, in-memory plugin record | The actual TypeScript transition code overwrote progress after a successful same-status update. Serial order kept progress. A truly different status defeated the stale completion predicate. Synthetic boot and deadline transitions produced their documented failure dispositions. |
| P6 and E6, local SDK and event primitives | Four selected FakeSdk assertions verified TTL, storage owner scope, JSON copying, and ordered progress. A blocked fake log iterator woke when cancellation closed the generator's source. This checks the transport-free seam and the reader's cleanup signal. |
| Q1 and Q2, local dispatch and ledger | Gated threads demonstrated the difference between ending an await and ending its thread. A synthetic envelope and host budget exposed the advisory vs authoritative headroom difference. Both probes use no live runner or scheduling workflow. |
| Q3, UTC schedule arithmetic | On 488,520 possible rules with exactly two minute values, two hour values, and every date eligible, the implementation understated 109,620 gaps. Of these, 26,460 crossed the default 15-minute floor and 109,620 crossed a 30-minute floor. The separate date search matched the minute-step oracle on the selected sparse-hour cases. Across the 400-year leap controls it missed twelve March-start cases around skipped century leap days. Results matched with two host time-zone settings inside the sandbox. |

The experiments used checked-in source, standard library process and event primitives, direct temporary-file operations, and synthetic boundaries. The Python probes ran on Linux x86-64 using CPython 3.11.17, 3.12.16, and 3.14.8. The Btrfs workspace rerun used 3.14.8. The pure TypeScript controls ran on local Node 24.22.2. Findings about real database concurrency, storage-controller or power-loss behavior, actual provider SDK exceptions, service container behavior, and production frequency remain outside the measurement. The selected fixtures used synthetic inputs in an isolated network namespace, a read-only source mount, and private temporary storage. Source-supported inferences are marked separately from local reproduction.


## 7. Measurement audit

The earlier draft was a lead list. Its test totals, elapsed time, runtime assertions, and harness setup are excluded from this review's evidence. I read the checked-in code and adjacent tests before deciding whether to retain a claim or add a fresh control. The fresh transcript and dry tests provide independent evidence. The earlier description that ordinary disconnect removes the connection was revised after tracing both branches of the receive-loop finally block. [agentic/websocket_api.py:2631](repos/samugit83__redamon/agentic/websocket_api.py:2631)

The first selected upload-test pass used a global log-disable flag and failed an assertLogs check. Replacing it with a root NullHandler allowed the local logger to reach its own test handler. The isolated file then passed, including timer and storage assertions. An initial CPython 3.12 AST harness also failed before the event test because it omitted evaluated annotation names for a selected WebSocket class. Supplying the original standard-library types and inert annotation stand-ins corrected the harness. Python 3.11, 3.12, and 3.14 then agreed on the relevant behavior. Those two initial failures are measurement faults. Full image dependency resolution, pytest tier collection, and integration suites are separate from these controls. The first aggregated Bash syntax invocation hit a here-document staging quota, while aggregate filesystem totals still showed free blocks and tmpfs inodes. Passing the same text as a quoted command supplied it without that temporary-file step. Syntax and the complete replay then passed. [agentic/tests/test_workspace_upload_sessions.py:178](repos/samugit83__redamon/agentic/tests/test_workspace_upload_sessions.py:178) [agentic/websocket_api.py:8](repos/samugit83__redamon/agentic/websocket_api.py:8) [agentic/websocket_api.py:241](repos/samugit83__redamon/agentic/websocket_api.py:241) [agentic/pytest.ini:1](repos/samugit83__redamon/agentic/pytest.ini:1) [agentic/conftest.py:21](repos/samugit83__redamon/agentic/conftest.py:21)

| Observation | Counter-paths, controls, and applicability |
| --- | --- |
| W1, byte count | The cancellation test observes the worker enter, cancels its caller, and allows the physical write to finish before retry. Normal serial and concurrent duplicates retained one copy. The existing ENOSPC mock raises before writing. A separate injected short write plus EDQUOT and an actual ENOSPC on a private 256 KiB tmpfs both left physical bytes before the error. The latter had 8 KiB after refusal and committed 73,728 bytes after a retry against 65,536 declared. The real commit and placement branches were used with a fake project-existence answer. The HTTP source awaits the same chunk function and its ordinary exception handlers leave task cancellation to the runtime. A WebSocket, reverse proxy, or TCP disconnect may have different cancellation timing. [agentic/tests/test_workspace_upload_sessions.py:137](repos/samugit83__redamon/agentic/tests/test_workspace_upload_sessions.py:137) [agentic/tests/test_workspace_upload_sessions.py:164](repos/samugit83__redamon/agentic/tests/test_workspace_upload_sessions.py:164) [agentic/workspace_import/http_routes.py:203](repos/samugit83__redamon/agentic/workspace_import/http_routes.py:203) [agentic/workspace_import/errors.py:113](repos/samugit83__redamon/agentic/workspace_import/errors.py:113) [agentic/workspace_import/upload_job.py:59](repos/samugit83__redamon/agentic/workspace_import/upload_job.py:59) |
| W2, unowned staging | Existing-project storage failure was injected at log creation after directory lookup, separating it from earlier directory-creation errors. Direct registry controls covered injected EACCES, injected EDQUOT, and a real unwritable directory. Distinct controls used a governed slot and a workspace slot. The ordinary cap refusal restored the session, and the same staged bytes later committed after restoring the fixture. Idle sweep only visits sessions it still owns. Project reset and startup can recover space. These tests say when ownership is lost, independently of the frequency of storage or quota faults in a privileged container. [agentic/job_runner.py:142](repos/samugit83__redamon/agentic/job_runner.py:142) [agentic/job_runner.py:206](repos/samugit83__redamon/agentic/job_runner.py:206) [agentic/workspace_import/upload_sessions.py:89](repos/samugit83__redamon/agentic/workspace_import/upload_sessions.py:89) [agentic/tests/test_workspace_upload_commit.py:385](repos/samugit83__redamon/agentic/tests/test_workspace_upload_commit.py:385) [agentic/workspace_import/http_routes.py:142](repos/samugit83__redamon/agentic/workspace_import/http_routes.py:142) |
| W3, cancellation before first step | The fixture used the default task scheduling policy and no sending callbacks. The immediate cancellation branch had no runner entry and left staging. A separate control cancelled only after the runner reached a gated project check and released the reservation. An explicit project sweep cleared the pre-start case. The repository's bare registry test asserts cancelled metadata, while its already-running extraction test asserts cleanup. Neither establishes how often the pre-start window is reached through a deployed HTTP server. [agentic/tests/test_job_runner_progress.py:99](repos/samugit83__redamon/agentic/tests/test_job_runner_progress.py:99) [agentic/tests/test_workspace_upload_commit.py:205](repos/samugit83__redamon/agentic/tests/test_workspace_upload_commit.py:205) [agentic/workspace_import/upload_job.py:85](repos/samugit83__redamon/agentic/workspace_import/upload_job.py:85) |
| W4, swap recovery | Runtime second-rename failure followed by successful rollback kept the old file. Failing both renames created the actual recovery layout. A healthy restore from the same layout worked on both filesystems. Fault injection targeted only the restore rename. A real unwritable destination parent reproduced the cleanup branch, and the test restored the fixture directory's mode afterwards. The staged record was valid and the destination absent. Existing tests also cover a present replacement and cancellation between async steps. The tests do not model power loss, directory durability, or cross-device placement. [agentic/tests/test_workspace_staging.py:149](repos/samugit83__redamon/agentic/tests/test_workspace_staging.py:149) [agentic/tests/test_workspace_staging.py:157](repos/samugit83__redamon/agentic/tests/test_workspace_staging.py:157) [agentic/tests/test_workspace_place.py:137](repos/samugit83__redamon/agentic/tests/test_workspace_place.py:137) [agentic/workspace_import/staging.py:183](repos/samugit83__redamon/agentic/workspace_import/staging.py:183) |
| W5, stalled reservation growth | The event gate is inside the source read, after extraction's cancellation check. The first pass controls expiry directly and a second used the unmodified 30-second grace, reaching the same no-progress loop after 30.027 and 30.001 seconds on two CPython 3.11 runs. A sentinel stops after five unchanged growth steps. The active-reservation control grows by one step. The existing cooperative cancellation fixture exits before the timeout, and the ledger test checks a single post-release grow. The corner case depends on a worker surviving the grace or equivalent cancellation pressure. [agentic/workspace_import/extract.py:225](repos/samugit83__redamon/agentic/workspace_import/extract.py:225) [agentic/workspace_import/jobs_common.py:76](repos/samugit83__redamon/agentic/workspace_import/jobs_common.py:76) [agentic/tests/test_workspace_staging.py:118](repos/samugit83__redamon/agentic/tests/test_workspace_staging.py:118) [agentic/tests/test_workspace_upload_commit.py:205](repos/samugit83__redamon/agentic/tests/test_workspace_upload_commit.py:205) |
| E1 and E2, transcript flush | The synthetic saver signalled entry before flush, proving work was in flight even with an empty buffer. Releasing a two-entry control allowed FIFO completion. Failed saves can count as finished attempts and produce one warning. The existing flush tests start with either a backlog or an untouched queue. The in-flight cancellation may interrupt a client request before the server commits, or leave an already-committed write there. This control observed cancellation and queue accounting, with no database involved. [agentic/tests/test_persist_flush_on_connect.py:50](repos/samugit83__redamon/agentic/tests/test_persist_flush_on_connect.py:50) [agentic/tests/test_persist_flush_on_connect.py:81](repos/samugit83__redamon/agentic/tests/test_persist_flush_on_connect.py:81) [agentic/tests/test_persist_flush_on_connect.py:87](repos/samugit83__redamon/agentic/tests/test_persist_flush_on_connect.py:87) [agentic/orchestrator_helpers/chat_persistence.py:38](repos/samugit83__redamon/agentic/orchestrator_helpers/chat_persistence.py:38) |
| E3, checkpoint pool | Missing configuration created no pool. Distinct controls tested failure after open and successful attachment followed by close. The checkpointer's boot use and FastAPI shutdown were read on both sides of the pool assignment. The health response reads the configuration flag, while initialization can complete after saver setup falls back. The application logs that fallback. The test records calls through the application owner, independent of real psycopg worker lifetime, garbage collection, or OS process exit. [agentic/orchestrator.py:152](repos/samugit83__redamon/agentic/orchestrator.py:152) [agentic/orchestrator.py:191](repos/samugit83__redamon/agentic/orchestrator.py:191) [agentic/orchestrator.py:1558](repos/samugit83__redamon/agentic/orchestrator.py:1558) [agentic/requirements.txt:64](repos/samugit83__redamon/agentic/requirements.txt:64) [agentic/api.py:1860](repos/samugit83__redamon/agentic/api.py:1860) |
| E4, retained connection | The exact loop's fake transport emitted one disconnect event with a live task attached. Releasing that task ran the real finalization method. I traced reconnect, normal disconnect, and task/callback release separately. Admission impact requires a cap and no subsequent cleanup or replacement of the entry. The successful replacement and idle-disconnect controls separate stale-map behavior from a cap calculation or stale task. [agentic/websocket_api.py:425](repos/samugit83__redamon/agentic/websocket_api.py:425) [agentic/websocket_api.py:464](repos/samugit83__redamon/agentic/websocket_api.py:464) [agentic/websocket_api.py:481](repos/samugit83__redamon/agentic/websocket_api.py:481) [agentic/websocket_api.py:2631](repos/samugit83__redamon/agentic/websocket_api.py:2631) |
| E5, non-global ordering | Both append routes read max and later insert. The schema's index and the transcript keyset explicitly permit ties. The existing PostgreSQL test creates ties for pagination and gives evidence about the reader contract, distinct from proving production interleavings. No transaction isolation, duplicate rate, or request overlap was measured. [webapp/src/app/api/conversations/\[id\]/messages/route.ts:32](repos/samugit83__redamon/webapp/src/app/api/conversations/[id]/messages/route.ts:32) [webapp/src/app/api/conversations/by-session/\[sessionId\]/messages/route.ts:74](repos/samugit83__redamon/webapp/src/app/api/conversations/by-session/[sessionId]/messages/route.ts:74) [webapp/prisma/schema.prisma:2500](repos/samugit83__redamon/webapp/prisma/schema.prisma:2500) [webapp/src/lib/plugins/jobs.pg.integration.test.ts:182](repos/samugit83__redamon/webapp/src/lib/plugins/jobs.pg.integration.test.ts:182) |
| J1, wait outcomes | The runner and observer used independent gates. The zero-timeout control and cancelled-observer control leave the job running. The active observer saw a cancelled child raise on all checked Python minor versions. The cancel and subsequent wait paths return the stored status. This narrows the result to an observer already waiting on the child. [agentic/job_runner.py:300](repos/samugit83__redamon/agentic/job_runner.py:300) [agentic/tests/test_job_runner.py:149](repos/samugit83__redamon/agentic/tests/test_job_runner.py:149) [agentic/tests/test_job_runner.py:163](repos/samugit83__redamon/agentic/tests/test_job_runner.py:163) |
| J3, durable metadata | A synthetic short write left a real truncated file, followed by an exception. The actual ENOSPC test used a bounded tmpfs and a larger terminal snapshot. It left 8,192 bytes of incomplete JSON. A healthy read before the fault and a manual rewrite after freeing fixture space worked, excluding a decoding or path error. An error before opening the file could leave its older snapshot usable. The damaged-file probe creates a fresh registry over the same local directory. The separate J6 control verifies real process replacement on an intact snapshot. [agentic/job_runner.py:153](repos/samugit83__redamon/agentic/job_runner.py:153) [agentic/job_runner.py:374](repos/samugit83__redamon/agentic/job_runner.py:374) [agentic/tests/test_job_runner.py:216](repos/samugit83__redamon/agentic/tests/test_job_runner.py:216) |
| J4, live delivery | The test used the real fan-out and connection method with an in-memory transport. Only the first recipient's running send blocked. A single unblocked recipient received the expected order. The fresh metadata read was terminal before the delayed running event. The checked-in emitter test checks event membership and project scope. Send backpressure differs by deployment and this test observes callback ordering. [agentic/ws_job_emitter.py:43](repos/samugit83__redamon/agentic/ws_job_emitter.py:43) [agentic/tests/test_workspace_ws_emitter.py:183](repos/samugit83__redamon/agentic/tests/test_workspace_ws_emitter.py:183) [agentic/websocket_api.py:267](repos/samugit83__redamon/agentic/websocket_api.py:267) |
| J5, tail allocation | Tracemalloc wrapped status after log creation. File byte size and returned tail matched the fixture in each run. Repeated measures agreed on scaling across 3.11, 3.12, and 3.14, with different allocation totals. Polling avoids a log read at list-only call sites. The targeted status path computes it even when omitting it from its reply. No end-to-end latency, storage throughput, or allocator RSS was measured. [agentic/job_runner.py:332](repos/samugit83__redamon/agentic/job_runner.py:332) [agentic/job_runner.py:366](repos/samugit83__redamon/agentic/job_runner.py:366) [agentic/workspace_import/http_routes.py:126](repos/samugit83__redamon/agentic/workspace_import/http_routes.py:126) |
| P1 and P2, supervisor lifecycle | A fake failed start and a gated starting state show lookup semantics without depending on fork, UID availability, memory, or subprocess timing. Unreachable run lists retain the previous handle, and the next successful reload retries. The server compares per-worker readiness when settling a deployment, and during an update the run list retains the active version until it changes. A separate gated finally confirms stop_all returns before report-task cleanup. Process exit and transport teardown races were not run. [services/plugin_runner/tests/test_supervisor_runlist.py:34](repos/samugit83__redamon/services/plugin_runner/tests/test_supervisor_runlist.py:34) [services/plugin_runner/tests/test_supervisor_runlist.py:68](repos/samugit83__redamon/services/plugin_runner/tests/test_supervisor_runlist.py:68) [services/plugin_runner/tests/test_supervisor_workers.py:101](repos/samugit83__redamon/services/plugin_runner/tests/test_supervisor_workers.py:101) [webapp/src/app/api/plugin-runner/v1/run-list/route.ts:40](repos/samugit83__redamon/webapp/src/app/api/plugin-runner/v1/run-list/route.ts:40) [webapp/src/lib/plugins/lifecycle.ts:758](repos/samugit83__redamon/webapp/src/lib/plugins/lifecycle.ts:758) |
| P5, stale JSON progress | Each fake storage read clones the record, the fake compares the current status at write time, and the write replaces the entire value. Serial progress survives. A cancellation changes status and defeats the late completion. The gateway accepts progress on the active record. Existing PG tests exercise terminal races and serial progress, with the DB concurrency gate outside this review. The result demonstrates the application's write predicate and payload under the scheduled interleaving. [webapp/src/app/api/plugin-gateway/v1/jobs/progress/route.ts:12](repos/samugit83__redamon/webapp/src/app/api/plugin-gateway/v1/jobs/progress/route.ts:12) [webapp/src/lib/plugins/jobs.ts:167](repos/samugit83__redamon/webapp/src/lib/plugins/jobs.ts:167) [webapp/src/lib/plugins/jobs.pg.integration.test.ts:102](repos/samugit83__redamon/webapp/src/lib/plugins/jobs.pg.integration.test.ts:102) [webapp/src/lib/plugins/jobs.pg.integration.test.ts:137](repos/samugit83__redamon/webapp/src/lib/plugins/jobs.pg.integration.test.ts:137) |
| Scheduler documentation | The module overview describes deferrals and a ledger read inside the scheduler. The current tick and its tight-ledger test call the server for the occurrence, while the separate dispatcher does a budget peek. The discrepancy concerns the documented owner, independently of runtime conditions. [recon_orchestrator/scan_scheduler.py:4](repos/samugit83__redamon/recon_orchestrator/scan_scheduler.py:4) [recon_orchestrator/scan_scheduler.py:68](repos/samugit83__redamon/recon_orchestrator/scan_scheduler.py:68) [recon_orchestrator/tests/test_scan_scheduler.py:143](repos/samugit83__redamon/recon_orchestrator/tests/test_scan_scheduler.py:143) [recon_orchestrator/job_dispatcher.py:109](repos/samugit83__redamon/recon_orchestrator/job_dispatcher.py:109) |
| Q1 and Q2, scheduler admission | The busy-thread control blocked a second tick while the first waiter remained live. Selective cancellation made the old thread physically live after guard release. Both production trigger tasks are cancelled during normal shutdown, and claims are conditional. The memory discrepancy used a synthetic ledger and no real jobs. Free disk and the global cap permitted the fixture request. A second reservation and a budget-fit comparison exercised the neighboring branches. [recon_orchestrator/tests/test_job_dispatcher.py:299](repos/samugit83__redamon/recon_orchestrator/tests/test_job_dispatcher.py:299) [recon_orchestrator/api.py:813](repos/samugit83__redamon/recon_orchestrator/api.py:813) [tests/test_admission_ledger.py:180](repos/samugit83__redamon/tests/test_admission_ledger.py:180) [webapp/src/app/api/internal/job-queue/\[id\]/dispatch/route.ts:164](repos/samugit83__redamon/webapp/src/app/api/internal/job-queue/[id]/dispatch/route.ts:164) |
| Q3, calendar arithmetic | Independent sorted UTC event times and a Gregorian leap predicate supplied the oracle. Adjacent selected hours exercised the correct wrap case. Repeating with Pacific/Auckland exercised the environment alternative, and directly calling validation confirmed the configured-default threshold branch. Existing tests validate hour wildcards and a usual leap year. The century result remained the same in both zone settings and reflects the fixed horizon. [webapp/src/lib/cron.test.ts:87](repos/samugit83__redamon/webapp/src/lib/cron.test.ts:87) [webapp/src/lib/cron.test.ts:93](repos/samugit83__redamon/webapp/src/lib/cron.test.ts:93) [webapp/src/lib/scanSchedule.ts:125](repos/samugit83__redamon/webapp/src/lib/scanSchedule.ts:125) |
| Q4, scheduled occurrence durability | The temporary and project-busy paths write the schedule advance separately from job insertion. Confirmed the prior-open-job branch intentionally coalesces occurrences. The tests exercise both successful deferral and coalescing. The failure condition instead requires the advance to commit, no prior open equivalent row, and a failed enqueue or process loss between the writes. The fallback logs the enqueue failure, and due selection works from the persisted new due time. Inferred from the application call paths. [webapp/src/app/api/internal/scan-schedules/\[scheduleId\]/run/route.ts:38](repos/samugit83__redamon/webapp/src/app/api/internal/scan-schedules/[scheduleId]/run/route.ts:38) [webapp/src/app/api/internal/scan-schedules/\[scheduleId\]/run/route.ts:171](repos/samugit83__redamon/webapp/src/app/api/internal/scan-schedules/[scheduleId]/run/route.ts:171) [webapp/src/app/api/internal/scan-schedules/\[scheduleId\]/run/route.ts:200](repos/samugit83__redamon/webapp/src/app/api/internal/scan-schedules/[scheduleId]/run/route.ts:200) [webapp/src/app/api/internal/scan-schedules/due/route.ts:26](repos/samugit83__redamon/webapp/src/app/api/internal/scan-schedules/due/route.ts:26) [webapp/src/app/api/internal/scan-schedules/internal.test.ts:192](repos/samugit83__redamon/webapp/src/app/api/internal/scan-schedules/internal.test.ts:192) [webapp/src/app/api/internal/scan-schedules/internal.test.ts:338](repos/samugit83__redamon/webapp/src/app/api/internal/scan-schedules/internal.test.ts:338) |
| Q5, stranded claim | Checked the durable claim operation, catch and cancellation paths, candidates query, periodic reconcile query, and queue write sites. A handled error after claim can retry. A process exit skips the handler catch, and a failed repair write can also leave the claim. The reconciliation selects running rows and candidate generation counts dispatching rows as busy. Authorized cancellation, access-change cleanup, and project deletion can clear such rows. No service restart was performed. [webapp/src/app/api/internal/job-queue/\[id\]/dispatch/route.ts:164](repos/samugit83__redamon/webapp/src/app/api/internal/job-queue/[id]/dispatch/route.ts:164) [webapp/src/app/api/internal/job-queue/\[id\]/dispatch/route.ts:384](repos/samugit83__redamon/webapp/src/app/api/internal/job-queue/[id]/dispatch/route.ts:384) [webapp/src/app/api/internal/job-queue/candidates/route.ts:32](repos/samugit83__redamon/webapp/src/app/api/internal/job-queue/candidates/route.ts:32) [webapp/src/app/api/internal/job-queue/reconcile/route.ts:159](repos/samugit83__redamon/webapp/src/app/api/internal/job-queue/reconcile/route.ts:159) [webapp/src/app/api/job-queue/\[id\]/cancel/route.ts:15](repos/samugit83__redamon/webapp/src/app/api/job-queue/[id]/cancel/route.ts:15) [webapp/src/lib/authz/revocation.ts:174](repos/samugit83__redamon/webapp/src/lib/authz/revocation.ts:174) |
| Q6, restart accounting | Traced fresh dictionaries, named status fallback, the tracked-only refresh loop, and the reaper's inputs to server reconciliation. A direct lookup can still report a live worker without reattaching its accounting entry. The repository separately documents and marks this expectation as a strict xfail. Scope is the checked-in normal startup and reaper path, independent of a particular daemon's shutdown settings. The restart fixture was reviewed as source evidence. [recon_orchestrator/container_manager.py:533](repos/samugit83__redamon/recon_orchestrator/container_manager.py:533) [recon_orchestrator/container_manager.py:762](repos/samugit83__redamon/recon_orchestrator/container_manager.py:762) [recon_orchestrator/container_manager.py:793](repos/samugit83__redamon/recon_orchestrator/container_manager.py:793) [recon_orchestrator/container_manager.py:1184](repos/samugit83__redamon/recon_orchestrator/container_manager.py:1184) [recon_orchestrator/tests/test_restart_adoption.py:128](repos/samugit83__redamon/recon_orchestrator/tests/test_restart_adoption.py:128) |
| R1 and R2, provider boundaries | R1 follows the async entry to the synchronous settings fetch. Missing service configuration uses defaults. The isolation tests replace the fetch with a fake. Other feature handlers already offload provider lookup, which exercises a different call path. I also checked the shared setup-error attribute, which is read in the immediate no-client path before its first suspension. I did not infer an ordinary same-loop race from the attribute alone. For R2, the explicit no-retry and quota branches return before the keyword fallback. A clean authentication fixture, the 403 test using text that misses the broad keyword list, and callers of the rate-only wrapper exercise other paths. The conditional finding is scoped to an error whose ordinary status and text disagree and to callers using the broad classifier. [agentic/orchestrator.py:1005](repos/samugit83__redamon/agentic/orchestrator.py:1005) [agentic/orchestrator.py:1191](repos/samugit83__redamon/agentic/orchestrator.py:1191) [agentic/tests/test_settings_llm_isolation.py:109](repos/samugit83__redamon/agentic/tests/test_settings_llm_isolation.py:109) [agentic/api.py:514](repos/samugit83__redamon/agentic/api.py:514) [agentic/tests/test_llm_retry.py:142](repos/samugit83__redamon/agentic/tests/test_llm_retry.py:142) [agentic/tests/test_llm_rate_limits.py:192](repos/samugit83__redamon/agentic/tests/test_llm_rate_limits.py:192) [agentic/tests/test_llm_rate_limits.py:403](repos/samugit83__redamon/agentic/tests/test_llm_rate_limits.py:403) [agentic/orchestrator_helpers/llm_retry.py:477](repos/samugit83__redamon/agentic/orchestrator_helpers/llm_retry.py:477) |

## 8. Post-mortem and prioritized improvements

The source shows pressures that explain the current shape. A single async process keeps run state cheap to share, dedicated executors protect short operations from long jobs, and a persistent row or file allows services to report work after the original requester leaves. Compatibility paths preserve older metadata and client behavior, while plugin versioning and structured errors reduce ambiguity at external boundaries. The main accumulated tradeoff is the number of places that infer ownership or durability from one observable fact. A present handle can lack a task. A task cancellation can outpace its thread. An empty queue can have an unfinished write. A terminal status can share a stale payload with a progress update. Process-local truths also change abruptly when the process is replaced. [agentic/job_runner.py:206](repos/samugit83__redamon/agentic/job_runner.py:206) [agentic/job_runner.py:332](repos/samugit83__redamon/agentic/job_runner.py:332) [agentic/workspace_import/executor.py:38](repos/samugit83__redamon/agentic/workspace_import/executor.py:38) [agentic/websocket_api.py:959](repos/samugit83__redamon/agentic/websocket_api.py:959) [services/plugin_runner/supervisor/manager.py:80](repos/samugit83__redamon/services/plugin_runner/supervisor/manager.py:80) [webapp/src/lib/plugins/jobs.ts:167](repos/samugit83__redamon/webapp/src/lib/plugins/jobs.ts:167)

1. **P0 · Defend the file commit boundary.** Use offset-addressed writes or another idempotent chunk protocol, verify physical size at publication, and retain the recovery record and staged prior entry when restore fails. Add local assertions for partial writes, cancellation, destination errors, and repeat recovery. [W1, W4](#4-what-it-does-well-and-poorly-with-source-evidence)
2. **P0 · Give each accepted operation one cleanup owner.** Make log and metadata preparation part of admission rollback. Register cleanup before handing over a completed upload, including the pre-start and failed-start cases. Track the physical executor future until it completes and make a released reservation a terminal operation for growth. [W2, W3, W5, Q1](#4-what-it-does-well-and-poorly-with-source-evidence)
3. **P0 · Persist a retryable scheduling decision.** Couple due-time advancement to a durable occurrence record. Add an expiring ownership record for dispatch claims and reconcile it with runtime identity before choosing a disposition. Account for workers that can survive the manager, using stable ownership records and verified reattachment at startup. [Q4, Q5, Q6](#4-what-it-does-well-and-poorly-with-source-evidence)
4. **P1 · Make lifecycle observation explicit.** Track in-flight persistence work with a bounded drain and put queue bookkeeping in a cancellation-safe finalizer. Use stable sequence allocation and event IDs across writers. Remove disconnected transport entries independently of live task ownership. Publish lifecycle and progress notices independently of request latency, with a monotonic job version and a bounded buffer. [E1, E4, J4](#4-what-it-does-well-and-poorly-with-source-evidence) [E5](#5-core-code-quality)
5. **P1 · Improve recoverability and readiness at storage boundaries.** Publish job metadata atomically and bound log reads by bytes. Set close ownership when opening the checkpoint pool and join supervisor reporting tasks within shutdown grace. Preserve progress with field-level writes or a record revision. Keep worker readiness distinct from accepted run-list state. [E3, J3, J5, P1, P2, P5](#4-what-it-does-well-and-poorly-with-source-evidence)
6. **P2 · Use one definition for each decision.** Move settings I/O off the event loop, keep provider error classification structured through the final retry decision, use one policy for advisory and authoritative capacity checks, and verify calendar acceptance against actual UTC occurrences. [R1, R2, Q2, Q3](#4-what-it-does-well-and-poorly-with-source-evidence)


## 9. Evidence appendix with local file and line references and commands

The links in §§2–8 point to exact local line anchors in the pinned checkout. Use these read-only commands to retrieve the same primary evidence. The source scans used rg for call sites and nl for the numbered context. The status command returned no lines at both snapshot checks.

~~~bash
git rev-parse --verify HEAD
git --no-optional-locks status --porcelain=v1 --untracked-files=all
git ls-files -z
git diff --no-ext-diff --exit-code
git diff --cached --no-ext-diff --exit-code
date -u '+%FT%TZ'
nl -ba agentic/job_runner.py | sed -n '140,393p'
nl -ba agentic/workspace_import/upload_sessions.py | sed -n '172,243p'
nl -ba agentic/workspace_import/upload_job.py | sed -n '50,125p'
nl -ba agentic/workspace_import/staging.py | sed -n '164,219p'
nl -ba agentic/websocket_api.py | sed -n '949,1041p;1889,1945p;2582,2639p'
nl -ba services/plugin_runner/supervisor/manager.py | sed -n '61,149p'
nl -ba webapp/src/lib/plugins/jobs.ts | sed -n '146,189p;370,416p'
nl -ba recon_orchestrator/job_dispatcher.py | sed -n '80,191p'
rg -n '\bdispatching\b' webapp/src/lib webapp/src/app/api webapp/prisma
rg -n 'flush_persist_queue|drain_persist_queue|release_callback|def disconnect' agentic/websocket_api.py
rg -n 'llm_setup_failure|fetch_agent_settings|retry_llm_call' agentic --glob '*.py'
~~~

The commands below replay the successful generic controls. The wrapper groups the original bubblewrap arguments so the same stdin probe can be run on several locally installed interpreters. Run them from the pinned checkout in Bash. The read-only source is mounted at /src. The test namespace starts with a clean environment and a private /tmp, and contains neither the user home nor the service socket directories. A Python audit hook rejects network socket families, connect and bind, name lookup, and external command launch. The Node controls use only built-in modules and the checked-in TypeScript named in each probe.

<details>
<summary>Read-only sandbox command wrappers</summary>

~~~bash
cd 'repos/samugit83__redamon'

review_python() {
  local review_edition="$1"
  shift
  local review_exe
  local -a review_interpreter=()
  local -a review_scratch=(--tmpfs /tmp)

  case "$review_edition" in
    311)
      review_interpreter=(--ro-bind $HOME/.local/share/uv/python/cpython-3.11.17-linux-x86_64-gnu /cpython311)
      review_exe=/cpython311/bin/python3.11
      ;;
    312)
      review_interpreter=(--ro-bind $HOME/.local/share/mise/installs/python/3.12.16 /cpython312)
      review_exe=/cpython312/bin/python3.12
      ;;
    314) review_exe=/usr/bin/python3 ;;
    *) return 2 ;;
  esac

  if [[ -n "${review_tmpfs_size-}" ]]; then
    review_scratch=(--size "$review_tmpfs_size" --tmpfs /tmp)
  fi
  if [[ -n "${redamon_lab-}" ]]; then
    review_scratch+=(--bind "$redamon_lab" /lab --setenv TMPDIR /lab)
  fi
  bwrap --unshare-all --die-with-parent --new-session --clearenv \
    --setenv PATH /usr/bin --ro-bind /usr /usr --symlink usr/lib /lib \
    --symlink usr/lib /lib64 --dev /dev "${review_scratch[@]}" \
    --ro-bind "$PWD" /src --chdir /src "${review_interpreter[@]}" \
    "$review_exe" -I -B -S - "$@"
}

review_node() {
  local -a review_tz=()
  if [[ -n "${review_zone-}" ]]; then
    review_tz=(--setenv TZ "$review_zone")
  fi
  bwrap --unshare-all --die-with-parent --new-session --clearenv \
    --setenv PATH /usr/bin "${review_tz[@]}" --ro-bind /usr /usr \
    --symlink usr/lib /lib --symlink usr/lib /lib64 --dev /dev --tmpfs /tmp \
    --ro-bind "$PWD" /src --chdir /src \
    --ro-bind $HOME/.local/share/mise/installs/node/24.22.2 /node24 \
    /node24/bin/node --no-warnings --input-type=module -
}
~~~

</details>

<details>
<summary>Selected existing unit tests and passive source compile</summary>

~~~bash
review_unit_1() {
  review_python 311 "$@" <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)
import job_runner
job_runner._governed_max_jobs = lambda: None
logging.getLogger().addHandler(logging.NullHandler())
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
result = unittest.TextTestRunner(verbosity=1).run(suite)
if not result.wasSuccessful() or result.skipped:
    raise SystemExit(1)
PY
}

review_unit_1 test_job_runner.TestSpawn.test_spawn_without_project_returns_error test_job_runner.TestSpawn.test_tee_appends_to_log test_job_runner.TestStatus test_job_runner.TestList.test_list_isolates_projects test_job_runner.TestRecoverOnBoot test_job_runner.TestWebSocketEmitter
review_unit_1 test_job_runner_progress.ReportProgress.test_report_progress_outside_job_is_noop test_job_runner_progress.ReportProgress.test_meta_writes_throttled_to_one_per_second test_job_runner_progress.ReportProgress.test_job_update_event_carries_progress test_job_runner_progress.ReportProgress.test_cancel_before_the_task_starts_marks_cancelled test_job_runner_progress.ReportProgress.test_old_meta_without_progress_loads
review_unit_1 test_job_runner_workspace_cap
review_unit_1 test_workspace_upload_sessions
review_unit_1 test_workspace_staging
review_unit_1 test_workspace_ws_emitter.TestEmitJobUpdate test_workspace_ws_emitter.TestRegistryEmitterWiring test_workspace_ws_emitter.TestEmitterEdges
review_unit_1 test_workspace_import_boot_wiring
review_unit_1 test_startup_guard

review_unit_2() {
  review_python 311 "$@" <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)
import types
conf = types.ModuleType("project_settings")
conf.get_setting = lambda key, default=None: default
sys.modules["project_settings"] = conf
import job_runner
job_runner._governed_max_jobs = lambda: None
logging.getLogger().addHandler(logging.NullHandler())
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
result = unittest.TextTestRunner(verbosity=1).run(suite)
if not result.wasSuccessful() or result.skipped:
    raise SystemExit(1)
PY
}

review_unit_2 test_logging_per_session.TestRouting test_logging_per_session.TestEviction test_logging_per_session.TestSetupToggle test_logging_per_session.TestSeparateVarRegression test_logging_per_session.TestEventStream test_logging_per_session.TestSetupInstallsEventStream

review_unit_3() {
  review_python 311 "$@" <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)
sys.path.insert(0, '/src/tests')
import job_runner
job_runner._governed_max_jobs = lambda: None
logging.getLogger().addHandler(logging.NullHandler())
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
result = unittest.TextTestRunner(verbosity=1).run(suite)
if not result.wasSuccessful() or result.skipped:
    raise SystemExit(1)
PY
}

review_unit_3 test_admission_ledger

review_unit_4() {
  review_python 311 "$@" <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)
sys.path[:0] = ['/src/recon_orchestrator', '/src/recon_orchestrator/tests']
import job_runner
job_runner._governed_max_jobs = lambda: None
logging.getLogger().addHandler(logging.NullHandler())
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
result = unittest.TextTestRunner(verbosity=1).run(suite)
if not result.wasSuccessful() or result.skipped:
    raise SystemExit(1)
PY
}

review_unit_4 test_job_dispatcher.TestConfig test_job_dispatcher.TestTick test_job_dispatcher.TestLoop.test_disabled_loop_returns_immediately test_job_dispatcher.TestLoop.test_a_second_tick_is_skipped_while_one_is_in_flight test_job_dispatcher.TestLoop.test_a_tick_runs_and_clears_the_flag_when_idle

review_python 311 agentic/agent_context.py agentic/agent_in_the_loop/broker.py agentic/api.py agentic/conftest.py agentic/job_runner.py agentic/llm_builder.py agentic/logging_config.py agentic/orchestrator.py agentic/orchestrator_helpers/chat_persistence.py agentic/orchestrator_helpers/config.py agentic/orchestrator_helpers/llm_retry.py agentic/orchestrator_helpers/llm_setup.py agentic/project_settings.py agentic/session_log.py agentic/startup_guard.py agentic/state.py agentic/websocket_api.py agentic/workspace_import/busy.py agentic/workspace_import/errors.py agentic/workspace_import/executor.py agentic/workspace_import/extract.py agentic/workspace_import/http_routes.py agentic/workspace_import/jobs_common.py agentic/workspace_import/place.py agentic/workspace_import/project_check.py agentic/workspace_import/staging.py agentic/workspace_import/upload_job.py agentic/workspace_import/upload_sessions.py agentic/ws_job_emitter.py recon_orchestrator/admission_ledger.py recon_orchestrator/api.py recon_orchestrator/container_manager.py recon_orchestrator/job_dispatcher.py recon_orchestrator/scan_scheduler.py services/plugin_runner/sdk/redamon_plugin_sdk/client.py services/plugin_runner/sdk/redamon_plugin_sdk/context.py services/plugin_runner/sdk/redamon_plugin_sdk/testing.py services/plugin_runner/supervisor/app.py services/plugin_runner/supervisor/jobs.py services/plugin_runner/supervisor/logs.py services/plugin_runner/supervisor/manager.py services/plugin_runner/supervisor/runlist.py services/plugin_runner/supervisor/workers.py services/plugin_runner/worker/bootstrap.py tooling/scripts/pytest_isolated.py <<'PY'
import ast, pathlib, sys
for name in sys.argv[1:]:
    path = pathlib.Path(name)
    tree = ast.parse(path.read_bytes(), filename=name, feature_version=(3, 11))
    compile(tree, name, "exec", dont_inherit=True)
print(f"Python 3.11 syntax/compile only: {len(sys.argv)-1} files")
PY
~~~

</details>

<details>
<summary>J1–J4 and E4/J5 · Registry, transport ordering, connection lifetime, log tail</summary>

~~~bash
for review_edition in 311 312 314; do
  review_python "$review_edition" <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)

import ast, asyncio, errno, json, tempfile
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import job_runner
import ws_job_emitter

logging.getLogger().addHandler(logging.NullHandler())
job_runner._governed_max_jobs = lambda: 1

async def success(*_args):
    return {"success": True, "output": "sample"}

async def wait_semantics():
    reg = job_runner.JobRegistry()
    runner_entered = asyncio.Event()
    waiter_entered = asyncio.Event()

    async def held(*_args):
        runner_entered.set()
        await asyncio.Event().wait()

    job = (await reg.spawn("project", "sample", {}, held))["job_id"]
    await runner_entered.wait()
    assert (await reg.wait("project", job, 0))["status"] == "running"

    async def wait_once():
        waiter_entered.set()
        return await reg.wait("project", job)

    waiter = asyncio.create_task(wait_once())
    await waiter_entered.wait()
    waiter.cancel()
    try:
        await waiter
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("waiter cancellation must propagate to its caller")
    assert reg.status("project", job)["status"] == "running"

    waiter_entered.clear()
    waiter = asyncio.create_task(wait_once())
    await waiter_entered.wait()
    assert (await reg.cancel("project", job))["status"] == "cancelled"
    try:
        await waiter
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("child cancellation did not propagate")
    assert (await reg.wait("project", job))["status"] == "cancelled"
    print("J1 timeout=running caller-cancel=running child-cancel=CancelledError subsequent-wait=cancelled")

async def prelaunch_log_failure():
    for errno_case in (errno.EACCES, errno.EDQUOT):
        reg = job_runner.JobRegistry()
        async def never_started(*_):
            raise AssertionError("a failed admission must not start a child")
        with patch.object(Path, "touch", side_effect=OSError(errno_case, "injected log creation fault")):
            try:
                await reg.spawn("storage", "sample", {}, never_started)
            except OSError as fault:
                assert fault.errno == errno_case
            else:
                raise AssertionError("expected injected error")
        [row] = reg.list("storage", active=True)
        jid = row["job_id"]
        assert reg._jobs[jid].task is None
        assert not Path(row["output_path"]).exists()
        assert (await reg.cancel("storage", jid))["status"] == "running"
        assert (await reg.wait("storage", jid))["status"] == "running"
        assert (await reg.spawn("storage", "sample", {}, success))["limitType"] == "ram"
        assert job_runner.JobRegistry().list("storage") == []
    reg = job_runner.JobRegistry()
    jid = (await reg.spawn("storage", "baseline", {}, success))["job_id"]
    assert (await reg.wait("storage", jid))["status"] == "done"
    print("J2 injected EACCES and EDQUOT both leave a taskless running handle consuming one slot")

async def torn_meta():
    reg = job_runner.JobRegistry()
    held = asyncio.Event()
    async def blocked(*_):
        await held.wait()
        return {"success": True}
    jid = (await reg.spawn("metadata", "sample", {}, blocked))["job_id"]
    meta = reg._meta_path("metadata", jid)
    assert json.loads(meta.read_text())["status"] == "running"
    real_write = Path.write_text

    def fail_midwrite(path, data, *args, **kwargs):
        if path == meta:
            real_write(path, data[:31], *args, **kwargs)
            raise OSError(errno.ENOSPC, "simulated partial write")
        return real_write(path, data, *args, **kwargs)

    with patch.object(Path, "write_text", fail_midwrite):
        held.set()
        assert (await reg.wait("metadata", jid))["status"] == "done"
    assert len(meta.read_text()) == 31
    fresh = job_runner.JobRegistry()
    fresh.recover_on_boot()
    assert "meta unreadable" in fresh.status("metadata", jid)["error"]
    assert fresh.list("metadata") == []
    jid = (await reg.spawn("metadata", "baseline", {}, success))["job_id"]
    await reg.wait("metadata", jid)
    assert fresh.status("metadata", jid)["status"] == "done"
    print("J3 injected partial metadata write -> memory=done fresh status=meta unreadable fresh list=omits")

def selected(path, names, namespace):
    tree = ast.parse(path.read_text(), filename=str(path))
    futures = [x for x in tree.body if isinstance(x, ast.ImportFrom) and x.module == "__future__"]
    definitions = [x for x in tree.body if getattr(x, "name", None) in names]
    assert {x.name for x in definitions} == set(names)
    exec(compile(ast.Module(body=futures + definitions, type_ignores=[]), str(path), "exec"), namespace)
    return namespace

async def event_order():
    ws_file = Path("/src/agentic/websocket_api.py")
    ns = selected(ws_file, {"serialize_for_json", "MessageType", "WebSocketConnection"},
                  dict(asyncio=asyncio, datetime=datetime, timezone=timezone, logger=logging.getLogger("event"),
                       WebSocket=object, RunActor=object, Any=Any, Optional=Optional, Enum=Enum))
    conn_cls = ns["WebSocketConnection"]
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    terminal_on_second = asyncio.Event()
    seen = []

    class Sink:
        def __init__(self, delayed):
            self.delayed = delayed

        async def send_json(self, frame):
            assert frame["type"] == "job_update"
            status = frame["payload"]["status"]
            if self.delayed and status == "running":
                first_started.set()
                await release_first.wait()
            if not self.delayed:
                seen.append((frame["payload"]["job_id"], status))
                if status == "done":
                    terminal_on_second.set()

    def connection(sid, delayed):
        obj = conn_cls(Sink(delayed))
        obj.user_id, obj.project_id, obj.session_id = "user", "events", sid
        obj.authenticated = True
        return obj

    reg = job_runner.JobRegistry()
    reg.set_ws_emitter(ws_job_emitter.emit_job_update)
    a, b = connection("a", True), connection("b", False)
    ws_job_emitter.set_ws_manager(SimpleNamespace(active_connections={c.get_key(): c for c in (a, b)}))
    spawn = asyncio.create_task(reg.spawn("events", "sample", {}, success))
    await first_started.wait()
    await terminal_on_second.wait()
    [(jid, _)] = seen
    assert reg.status("events", jid)["status"] == "done"
    assert not spawn.done()
    release_first.set()
    assert (await spawn)["job_id"] == jid
    assert seen == [(jid, "done"), (jid, "running")]

    seen.clear()
    ws_job_emitter.set_ws_manager(SimpleNamespace(active_connections={b.get_key(): b}))
    jid = (await reg.spawn("events", "baseline", {}, success))["job_id"]
    await reg.wait("events", jid)
    assert seen == [(jid, "running"), (jid, "done")]
    print("J4 actual emitter and connection method, fake send_json -> done,running on second recipient; baseline running,done")

async def main():
    with tempfile.TemporaryDirectory() as root:
        job_runner.WORKSPACE_ROOT = Path(root)
        for test in (wait_semantics, prelaunch_log_failure, torn_meta, event_order):
            await asyncio.wait_for(test(), 5)

asyncio.run(main())
PY
done

for review_edition in 311 312 314; do
  review_python "$review_edition" <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)

import ast, asyncio, tempfile, tracemalloc, weakref
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional
import job_runner
import ws_job_emitter

logging.getLogger().addHandler(logging.NullHandler())

def event_classes():
    path = Path("/src/agentic/websocket_api.py")
    tree = ast.parse(path.read_text(), filename=str(path))
    names = {"MessageType", "WebSocketConnection", "WebSocketManager", "WebSocketHandler", "websocket_endpoint", "serialize_for_json"}
    required = {"__init__", "connect", "authenticate", "disconnect", "register_task", "get_task",
                "release_task", "release_callback", "get_connection_count"}
    code = []
    for item in tree.body:
        if getattr(item, "name", None) not in names:
            continue
        if item.name == "WebSocketManager":
            item.body = [n for n in item.body if getattr(n, "name", None) in required]
        elif item.name == "WebSocketHandler":
            item.body = [n for n in item.body if getattr(n, "name", None) == "_finish_run"]
        code.append(item)

    flags = []
    async def update_conversation(sid, state):
        flags.append((sid, state["agentRunning"]))

    class WebSocketDisconnect(Exception):
        pass

    ns = dict(asyncio=asyncio, weakref=weakref, datetime=datetime, timezone=timezone, Enum=Enum,
              Any=Any, Dict=Dict, Optional=Optional, WebSocket=object, RunActor=object,
              WebSocketDisconnect=WebSocketDisconnect, logger=logging.getLogger("events"),
              _governed_max_sessions=lambda: 1, update_conversation=update_conversation)
    exec(compile(ast.Module(body=code, type_ignores=[]), str(path), "exec"), ns)
    assert ws_job_emitter._JOB_UPDATE.value == ns["MessageType"].JOB_UPDATE.value
    return ns, flags

async def disconnected_slots():
    ns, flags = event_classes()
    manager = ns["WebSocketManager"]()
    real_handler = ns["WebSocketHandler"]()
    real_handler.ws_manager = manager
    # The loop will consume exactly a fake disconnect event. Message handling and graph runtime are absent.
    ns["WebSocketHandler"] = lambda app, mgr: None

    class Socket:
        client = "local fixture"
        closed = []
        def __init__(self):
            self.closed = []

        async def accept(self):
            pass

        async def receive(self):
            return {"type": "websocket.disconnect"}

        async def close(self, code, reason):
            self.closed.append((code, reason))

    async def drain():
        pass

    first = await manager.connect(Socket())
    await manager.authenticate(first, "user", "project", "session", verified=True)
    key = first.get_key()
    current = asyncio.Event()
    async def run_stub():
        await current.wait()
        await real_handler._finish_run(first, SimpleNamespace(drain_persist_queue=drain))

    run = asyncio.create_task(run_stub())
    first._active_task = run
    manager.register_task(key, run)

    real_connect = manager.connect
    async def existing(socket):
        assert socket is first.websocket
        return first
    manager.connect = existing
    await ns["websocket_endpoint"](first.websocket, object(), manager)
    manager.connect = real_connect
    assert manager.get_task(key) is run and manager.get_connection_count() == 1
    current.set()
    await run
    assert flags == [("session", False)]
    assert manager.get_task(key) is None and manager.get_connection_count() == 1

    blocked = await manager.connect(Socket())
    await manager.authenticate(blocked, "user", "project", "new-session", verified=True)
    assert not blocked.authenticated and blocked.websocket.closed[0][0] == 1013
    replacement = await manager.connect(Socket())
    await manager.authenticate(replacement, "user", "project", "session", verified=True)
    assert replacement.authenticated and manager.active_connections[key] is replacement
    await manager.disconnect(first)
    assert manager.active_connections[key] is replacement
    await manager.disconnect(replacement)
    assert manager.get_connection_count() == 0
    eligible = await manager.connect(Socket())
    await manager.authenticate(eligible, "user", "project", "new-session", verified=True)
    assert eligible.authenticated

    async def current_connection(socket):
        assert socket is eligible.websocket
        return eligible
    manager.connect = current_connection
    await ns["websocket_endpoint"](eligible.websocket, object(), manager)
    assert manager.get_connection_count() == 0
    print("E4 enum parity confirmed; fake disconnect with live task retains registry slot after finalization; at cap new session refused; verified replacement and idle disconnect controls clear it")

async def log_cost():
    with tempfile.TemporaryDirectory() as root:
        job_runner.WORKSPACE_ROOT = Path(root)
        job_runner._governed_max_jobs = lambda: None
        reg = job_runner.JobRegistry()

        async def make_log(data):
            async def runner(_, __, append):
                await append(data)
                return {"success": True}
            jid = (await reg.spawn("project", "local-log", {}, runner))["job_id"]
            await reg.wait("project", jid)
            return jid

        line = ("z" * 127) + "\n"
        sizes = [128 * 1024, 2 * 1024 * 1024]
        exports = []
        for size in sizes:
            jid = await make_log(line * (size // len(line)))
            tracemalloc.start()
            try:
                row = reg.status("project", jid)
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            assert row["size_bytes"] == size and row["tail"] == line * 40
            exports.append((size, len(row["tail"]), peak))
        assert exports[1][2] > 5 * exports[0][2]
        jid = await make_log("a" * (256 * 1024))
        assert len(reg.status("project", jid)["tail"]) == 256 * 1024 + 1
        assert len(reg._jobs) == 3 and len(job_runner.JobRegistry().list("project")) == 3
        print(f"J5 file_bytes, tail_bytes, traced_peak_bytes={exports}; single line tail=262145")

async def main():
    for case in (disconnected_slots, log_cost):
        await asyncio.wait_for(case(), 5)

asyncio.run(main())
PY
done
~~~

</details>

<details>
<summary>W1–W4 · Physical file, session handoff, and swap controls</summary>

~~~bash
review_workspace_probe=$(cat <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)

import ast, asyncio, errno, tempfile, threading, unicodedata
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import job_runner, workspace_fs
from workspace_import import busy, staging, upload_sessions, place
from workspace_import.errors import ImportFailure

# Substitute only the project-existence boundary; no HTTP import or transport.
project_check = ModuleType("workspace_import.project_check")
project_check.ProjectCheckFailed = type("ProjectCheckFailed", (Exception,), {})
async def present(project):
    assert project == "project"
    return True
project_check.project_exists = present
sys.modules[project_check.__name__] = project_check

# Load the exact pure filename formatting helper without importing prompt setup.
sanitizer_path = Path("/src/agentic/prompts/base.py")
tree = ast.parse(sanitizer_path.read_text(), filename=str(sanitizer_path))
sanitizer = next(x for x in tree.body if getattr(x, "name", None) == "_prompt_safe_name")
prompts = ModuleType("prompts")
prompts.__path__ = []
base = ModuleType("prompts.base")
base.unicodedata = unicodedata
exec(compile(ast.Module(body=[sanitizer], type_ignores=[]), str(sanitizer_path), "exec"), base.__dict__)
sys.modules["prompts"] = prompts
sys.modules["prompts.base"] = base
from workspace_import import upload_job

logging.getLogger().addHandler(logging.NullHandler())
job_runner._governed_max_jobs = lambda: None
os.environ.update(JOB_QUEUE_MIN_FREE_DISK="0", WORKSPACE_IMPORT_MIN_FREE_BYTES="1", WORKSPACE_IMPORT_MAX_JOBS="1")
staging.disk_usage = lambda _: SimpleNamespace(free=1024**3)
pid = "project"

def session(name):
    uid = upload_sessions.create(pid, "uploads", name, 3, "file", "keep_both")["uploadId"]
    return uid, upload_sessions.get(pid, uid)

async def finish(uid, dest, name, expected):
    ack = await upload_job.commit(pid, uid)
    reg = job_runner.get_registry()
    status = await reg.wait(pid, ack["jobId"])
    assert ack["size"] == 3
    assert status["status"] == "done", status
    assert status["progress"]["bytes"] == 3
    assert (dest / name).read_bytes() == expected
    assert staging.reserved_total() == 0

async def upload_bytes(dest):
    name = "baseline.bin"
    uid, obj = session(name)
    assert await upload_sessions.write_chunk(pid, uid, 0, b"abc") == 3
    assert await upload_sessions.write_chunk(pid, uid, 0, b"abc") == 3
    assert obj.data_path.read_bytes() == b"abc"
    await finish(uid, dest, name, b"abc")

    name = "cancel.bin"
    uid, obj = session(name)
    then_append = threading.Event()
    entered = asyncio.Event()
    written = asyncio.Event()
    loop = asyncio.get_running_loop()
    real_append = upload_sessions._append
    def gated_append(path, data):
        loop.call_soon_threadsafe(entered.set)
        assert then_append.wait(3)
        real_append(path, data)
        loop.call_soon_threadsafe(written.set)

    with patch.object(upload_sessions, "_append", gated_append):
        req = asyncio.create_task(upload_sessions.write_chunk(pid, uid, 0, b"abc"))
        try:
            await entered.wait()
            req.cancel()
            try:
                await req
            except asyncio.CancelledError:
                pass
            else:
                raise AssertionError("request should be cancelled")
        finally:
            then_append.set()
        await written.wait()
    assert obj.received == 0 and obj.data_path.read_bytes() == b"abc"
    assert await upload_sessions.write_chunk(pid, uid, 0, b"abc") == 3
    await finish(uid, dest, name, b"abcabc")

    name = "quota.bin"
    uid, obj = session(name)
    serial = 0
    real_write = os.write
    def partial_write(fd, view):
        nonlocal serial
        serial += 1
        if serial == 1:
            return real_write(fd, view[:1])
        raise OSError(errno.EDQUOT, "synthetic write quota")
    with patch.object(upload_sessions.os, "write", partial_write):
        try:
            await upload_sessions.write_chunk(pid, uid, 0, b"abc")
        except ImportFailure as e:
            assert e.code == "insufficient_storage"
        else:
            raise AssertionError("quota error should be mapped")
    assert obj.received == 0 and obj.data_path.read_bytes() == b"a"
    assert await upload_sessions.write_chunk(pid, uid, 0, b"abc") == 3
    await finish(uid, dest, name, b"aabc")
    print("W1 baseline actual=3/declared=3; cancel+retry actual=6/declared=3; partial EDQUOT+retry actual=4/declared=3; all final done")

async def ownership(dest):
    reg = job_runner.get_registry()
    uid, obj = session("handoff.bin")
    await upload_sessions.write_chunk(pid, uid, 0, b"abc")
    blocker = asyncio.Event()
    async def hold(*_):
        await blocker.wait()
        return {"success": True}
    occupying = await reg.spawn(pid, "fixture", {}, hold, counts_toward_cap=False)
    try:
        await upload_job.commit(pid, uid)
    except ImportFailure as e:
        assert e.code == "too_many_jobs"
    else:
        raise AssertionError("must refuse occupied slot")
    assert upload_sessions.get(pid, uid) is obj and staging.reserved_total() == 3
    blocker.set()
    await reg.wait(pid, occupying["job_id"])

    with patch.object(Path, "touch", side_effect=OSError(errno.EACCES, "synthetic log refusal")):
        try:
            await upload_job.commit(pid, uid)
        except OSError as e:
            assert e.errno == errno.EACCES
        else:
            raise AssertionError("must fault before task creation")
    [orphan] = reg.list(pid, active=True)
    assert reg._jobs[orphan["job_id"]].task is None
    assert uid not in upload_sessions._sessions
    assert obj.op_dir.exists() and staging.reserved_total() == 3
    assert upload_sessions.sweep_idle(now=obj.updated_at + 7200) == 0
    # Reconstitute the known live session and cap state for a same-filesystem control.
    reg._jobs.pop(orphan["job_id"])
    upload_sessions.restore(obj)
    await finish(uid, dest, "handoff.bin", b"abc")
    print("W2 cap refusal restores session; EACCES leaves taskless state, staging and 3-byte reservation; same upload succeeds after fixture reset")

    uid, obj = session("prestart.bin")
    await upload_sessions.write_chunk(pid, uid, 0, b"abc")
    ack = await upload_job.commit(pid, uid)
    assert (await reg.cancel(pid, ack["jobId"]))["status"] == "cancelled"
    assert obj.op_dir.exists() and staging.reserved_total() == 3
    assert not (dest / "prestart.bin").exists()
    assert upload_sessions.sweep_idle(now=obj.updated_at + 7200) == 0
    staging.sweep_project(pid)
    assert staging.reserved_total() == 0 and not obj.op_dir.exists()

    uid, obj = session("started.bin")
    await upload_sessions.write_chunk(pid, uid, 0, b"abc")
    started = asyncio.Event()
    async def block_project(project):
        assert project == pid
        started.set()
        await asyncio.Event().wait()
    with patch.object(project_check, "project_exists", block_project):
        ack = await upload_job.commit(pid, uid)
        await started.wait()
        assert (await reg.cancel(pid, ack["jobId"]))["status"] == "cancelled"
    assert staging.reserved_total() == 0 and not obj.op_dir.exists()
    assert not (dest / "started.bin").exists()
    assert not busy._entries
    print("W3 pre-start cancel records cancelled but retains resources; cancellation inside runner releases them; explicit project sweep clears orphan")

async def swap_recovery(dest):
    stagedirs = {}
    real_rename = os.rename
    async def prepare(name, fail_rollback):
        target = dest / name
        target.write_bytes(b"existing")
        op = staging.new_op_dir(pid, "up")
        incoming = op / "new"
        incoming.write_bytes(b"replacement")
        def failing_rename(src, dst, *args, **kw):
            if Path(src) == incoming and Path(dst) == target:
                raise OSError(errno.EIO, "synthetic second rename failure")
            if fail_rollback and Path(src).name == staging.SWAP_ENTRY and Path(dst) == target:
                raise OSError(errno.EIO, "synthetic rollback failure")
            return real_rename(src, dst, *args, **kw)
        with patch.object(place.os, "rename", failing_rename):
            try:
                await place.place(pid, incoming, "uploads", name, "replace")
            except OSError as e:
                assert e.errno == errno.EIO
            else:
                raise AssertionError("swap must report error")
        if fail_rollback:
            [trash] = [x for x in staging.project_staging(pid).glob("trash-*") if (x / staging.SWAP_ENTRY).exists()]
            assert not target.exists() and (trash / staging.SWAP_ENTRY).read_bytes() == b"existing"
            return target, trash
        assert target.read_bytes() == b"existing"
        return target, None

    await prepare("immediate.bin", False)
    dst, trash = await prepare("recover.bin", True)
    assert staging.recover_swaps() == 1
    assert not trash.exists() and dst.read_bytes() == b"existing"

    dst, trash = await prepare("restore-error.bin", True)
    attempted = []
    def interrupted_restore(src, target, *args, **kw):
        if Path(src) == trash / staging.SWAP_ENTRY and Path(target) == dst:
            attempted.append(errno.EIO)
            raise OSError(errno.EIO, "synthetic restore failure")
        return real_rename(src, target, *args, **kw)
    with patch.object(staging.os, "rename", interrupted_restore):
        assert staging.recover_swaps() == 0
    assert attempted == [errno.EIO] and not dst.exists() and not trash.exists()
    staging.sweep_all()
    assert not dst.exists()
    print("W4 ordinary rollback preserves old copy; double rename failure recovers at boot; injected boot EIO removes the last staged copy")

async def main():
    with tempfile.TemporaryDirectory() as root:
        workspace_fs.WORKSPACE_ROOT = job_runner.WORKSPACE_ROOT = Path(root)
        dest = workspace_fs.resolve_for_project(pid, "uploads")
        for case in (upload_bytes, ownership, swap_recovery):
            await asyncio.wait_for(case(dest), 10)

asyncio.run(main())
PY
)
for review_edition in 311 312 314; do
  printf '%s\n' "$review_workspace_probe" | review_python "$review_edition"
done
(
  redamon_lab=$(mktemp -d -p /var/tmp redamon-review.XXXXXXXX)
  trap 'rmdir "$redamon_lab"' EXIT
  stat -f -c '%T' "$redamon_lab"
  printf '%s\n' "$review_workspace_probe" | review_python 314
)
~~~

</details>

<details>
<summary>W1, W2, W4 and J3 · Private tmpfs exhaustion and actual directory permissions</summary>

~~~bash
review_tmpfs_size=262144 review_python 311 <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)

import ast, asyncio, errno, tempfile, threading, unicodedata
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import job_runner, workspace_fs
from workspace_import import busy, staging, upload_sessions, place
from workspace_import.errors import ImportFailure

# Substitute only the project-existence boundary; no HTTP import or transport.
project_check = ModuleType("workspace_import.project_check")
project_check.ProjectCheckFailed = type("ProjectCheckFailed", (Exception,), {})
async def present(project):
    assert project == "project"
    return True
project_check.project_exists = present
sys.modules[project_check.__name__] = project_check

# Load the exact pure filename formatting helper without importing prompt setup.
sanitizer_path = Path("/src/agentic/prompts/base.py")
tree = ast.parse(sanitizer_path.read_text(), filename=str(sanitizer_path))
sanitizer = next(x for x in tree.body if getattr(x, "name", None) == "_prompt_safe_name")
prompts = ModuleType("prompts")
prompts.__path__ = []
base = ModuleType("prompts.base")
base.unicodedata = unicodedata
exec(compile(ast.Module(body=[sanitizer], type_ignores=[]), str(sanitizer_path), "exec"), base.__dict__)
sys.modules["prompts"] = prompts
sys.modules["prompts.base"] = base
from workspace_import import upload_job

logging.getLogger().addHandler(logging.NullHandler())
job_runner._governed_max_jobs = lambda: None
os.environ.update(JOB_QUEUE_MIN_FREE_DISK="0", WORKSPACE_IMPORT_MIN_FREE_BYTES="1", WORKSPACE_IMPORT_MAX_JOBS="1")
staging.disk_usage = lambda _: SimpleNamespace(free=1024**3)
pid = "project"

def session(name):
    uid = upload_sessions.create(pid, "uploads", name, 3, "file", "keep_both")["uploadId"]
    return uid, upload_sessions.get(pid, uid)


async def main():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        workspace_fs.WORKSPACE_ROOT = job_runner.WORKSPACE_ROOT = root
        destination = workspace_fs.resolve_for_project(pid, "uploads")
        payload = b"local-probe-data" * 4096
        uid = upload_sessions.create(pid, "uploads", "probe.bin", len(payload), "file", "keep_both")["uploadId"]
        obj = upload_sessions.get(pid, uid)
        space = os.statvfs(root)
        assert space.f_blocks * space.f_frsize == 262144
        two_pages = 2 * space.f_frsize
        filler = root / "filler"
        with filler.open("wb") as f:
            os.posix_fallocate(f.fileno(), 0, space.f_bavail * space.f_frsize - two_pages)
        assert os.statvfs(root).f_bavail * space.f_frsize == two_pages
        try:
            await upload_sessions.write_chunk(pid, uid, 0, payload)
        except ImportFailure as problem:
            assert problem.code == "insufficient_storage"
        else:
            raise AssertionError("expected disk to fill")
        written = obj.data_path.read_bytes()
        assert written == payload[:two_pages] and obj.received == 0
        filler.unlink()
        assert await upload_sessions.write_chunk(pid, uid, 0, payload) == len(payload)
        ack = await upload_job.commit(pid, uid)
        status = await job_runner.get_registry().wait(pid, ack["jobId"])
        actual = (destination / "probe.bin").read_bytes()
        assert status["status"] == "done" and status["progress"]["bytes"] == len(payload)
        assert actual == written + payload
        print(f"W1 private 256 KiB tmpfs exhausted: wrote {len(written)} bytes before error; after retry declared={len(payload)}, actual={len(actual)}, status=done")
asyncio.run(main())
PY

review_tmpfs_size=262144 review_python 311 <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)

import asyncio, json, tempfile
from pathlib import Path
import job_runner

logging.getLogger().addHandler(logging.NullHandler())
job_runner._governed_max_jobs = lambda: None

async def main():
    with tempfile.TemporaryDirectory() as lab:
        root = Path(lab)
        job_runner.WORKSPACE_ROOT = root
        reg = job_runner.JobRegistry()
        finish = asyncio.Event()
        async def run(*_):
            await finish.wait()
            return {"success": True}
        details = {"payload": "short"}
        jid = (await reg.spawn("fixture", "local", details, run))["job_id"]
        meta = reg._meta_path("fixture", jid)
        assert json.loads(meta.read_text())["status"] == "running"
        committed = os.statvfs(root)
        assert committed.f_blocks * committed.f_frsize == 262144
        fill = root / "filler"
        with fill.open("wb") as file:
            leave = committed.f_frsize
            os.posix_fallocate(file.fileno(), 0, committed.f_bavail * committed.f_frsize - leave)
        assert os.statvfs(root).f_bavail * committed.f_frsize == leave
        details["payload"] = "m" * 65536
        finish.set()
        assert (await reg.wait("fixture", jid))["status"] == "done"
        written = meta.stat().st_size
        assert 0 < written < 65536
        check = job_runner.JobRegistry()
        assert "meta unreadable" in check.status("fixture", jid)["error"]
        assert check.list("fixture") == []
        fill.unlink()
        reg._write_meta(reg._jobs[jid])
        assert check.status("fixture", jid)["status"] == "done"
        print(f"J3 private 256 KiB tmpfs exhausted: terminal JSON stopped at {written} bytes. Live and fresh snapshots diverged until an explicit retry")
asyncio.run(main())
PY

review_python 311 <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)

import asyncio, errno, tempfile
from pathlib import Path
from types import SimpleNamespace
import job_runner, workspace_fs
from workspace_import import staging

logging.getLogger().addHandler(logging.NullHandler())
job_runner._governed_max_jobs = lambda: 1
pid = "permission-probe"

async def verify(root):
    job_runner.WORKSPACE_ROOT = workspace_fs.WORKSPACE_ROOT = root
    reg = job_runner.JobRegistry()
    # Reconstruct the precise admission edge. Parent lookup succeeds and the existing folder is not writable.
    jobs = reg._jobs_dir(pid)
    jobs.chmod(0o555)
    try:
        assert not os.access(jobs, os.W_OK, effective_ids=True)
        async def runner(*_):
            return {"success": True}
        try:
            await reg.spawn(pid, "flat-work", {}, runner)
        except PermissionError as e:
            assert e.errno == errno.EACCES
        else:
            raise AssertionError("real file creation was expected to fail")
    finally:
        jobs.chmod(0o700)
    [stuck] = reg.list(pid, active=True)
    assert reg._jobs[stuck["job_id"]].task is None
    assert (await reg.spawn(pid, "flat-work", {}, runner))["limitType"] == "ram"

    parent = workspace_fs.resolve_for_project(pid, "uploads")
    trash = staging.new_op_dir(pid, "trash")
    staging.write_swap_record(trash, "uploads/document")
    (trash / staging.SWAP_ENTRY).write_bytes(b"old")
    parent.chmod(0o555)
    try:
        assert not os.access(parent, os.W_OK, effective_ids=True)
        assert staging.recover_swaps() == 0
        assert not trash.exists() and not (parent / "document").exists()
    finally:
        parent.chmod(0o700)
    print("W2/W4 real local directory permission controls reproduced EACCES/log orphan and unsuccessful recovery cleanup")

with tempfile.TemporaryDirectory() as temp:
    asyncio.run(verify(Path(temp)))
PY
~~~

</details>

<details>
<summary>W5 · Bounded and default-grace cancellation controls</summary>

~~~bash
for review_edition in 311 312 314; do
  review_python "$review_edition" <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)

import asyncio, tempfile, threading
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import workspace_fs
from workspace_import import extract, staging
from workspace_import.errors import ImportFailure
check = ModuleType("workspace_import.project_check")
sys.modules[check.__name__] = check
from workspace_import import jobs_common

logging.getLogger().addHandler(logging.NullHandler())
os.environ["JOB_QUEUE_MIN_FREE_DISK"] = "0"
os.environ["WORKSPACE_IMPORT_MIN_FREE_BYTES"] = "1"
staging.disk_usage = lambda _path: SimpleNamespace(free=2**40)

class BoundedProbe(Exception):
    pass

async def delayed_worker():
    root = workspace_fs.WORKSPACE_ROOT
    loop = asyncio.get_running_loop()
    reading, done = asyncio.Event(), asyncio.Event()
    release_read = threading.Event()
    cancel = threading.Event()
    outcomes = []
    grow_calls = []
    reservation = staging.reserve("late", 2)
    actual_grow = staging.Reservation.grow
    progress = jobs_common.Progress({})
    op = root / "stage"
    op.mkdir()

    class Source:
        def read(self, _amount):
            loop.call_soon_threadsafe(reading.set)
            assert release_read.wait(5)
            return b"x"

    def bounded_grow(res, amount):
        before = res.nbytes
        actual_grow(res, amount)
        grow_calls.append((before, res.nbytes))
        if len(grow_calls) == 5:
            raise BoundedProbe

    def extractor(_, dest, *, cancel_event, on_bytes, **_kwargs):
        fd = os.open(dest / "output", os.O_CREAT | os.O_WRONLY, 0o600)
        budget = extract._Budget(100, 5, extract.ExtractReport(), None, cancel_event, lambda: 0, on_bytes)
        try:
            extract._copy(Source(), fd, budget, None)
        except BoundedProbe:
            outcomes.append("bounded sentinel")
        finally:
            loop.call_soon_threadsafe(done.set)

    with patch.object(jobs_common, "CANCEL_GRACE_SEC", 0), patch.object(staging.Reservation, "grow", bounded_grow):
        t = asyncio.create_task(jobs_common.extract_on_pool(
            extractor, None, op, progress, cancel, reservation=reservation, base_bytes=2,
        ))
        try:
            await reading.wait()
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
            else:
                raise AssertionError("expected cancel")
            assert cancel.is_set() and not done.is_set()
            reservation.release()
            staging.remove_tree(op)
        finally:
            release_read.set()
        await done.wait()
        assert outcomes == ["bounded sentinel"] and grow_calls == [(0, 0)] * 5
    control = staging.reserve("control", 2)
    jobs_common.ReservationGrower(control)(3)
    assert control.nbytes == 2 + jobs_common.GROW_STEP
    control.release()
    print("W5 cancelled wrap with expired synthetic grace; actual post-read grow loop had five zero-to-zero advances and was stopped by a sentinel; live reservation advances once")

async def main():
    with tempfile.TemporaryDirectory() as td:
        workspace_fs.WORKSPACE_ROOT = Path(td)
        await asyncio.wait_for(delayed_worker(), 10)

asyncio.run(main())
PY
done

review_python 311 <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)

import asyncio, tempfile, threading
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import workspace_fs
from workspace_import import extract, staging
from workspace_import.errors import ImportFailure
check = ModuleType("workspace_import.project_check")
sys.modules[check.__name__] = check
from workspace_import import jobs_common

logging.getLogger().addHandler(logging.NullHandler())
os.environ["JOB_QUEUE_MIN_FREE_DISK"] = "0"
os.environ["WORKSPACE_IMPORT_MIN_FREE_BYTES"] = "1"
staging.disk_usage = lambda _path: SimpleNamespace(free=2**40)

class BoundedProbe(Exception):
    pass

async def delayed_worker():
    root = workspace_fs.WORKSPACE_ROOT
    loop = asyncio.get_running_loop()
    reading, done = asyncio.Event(), asyncio.Event()
    release_read = threading.Event()
    cancel = threading.Event()
    outcomes = []
    grow_calls = []
    reservation = staging.reserve("late", 2)
    actual_grow = staging.Reservation.grow
    progress = jobs_common.Progress({})
    op = root / "stage"
    op.mkdir()

    class Source:
        def read(self, _amount):
            loop.call_soon_threadsafe(reading.set)
            assert release_read.wait(40)
            return b"x"

    def bounded_grow(res, amount):
        before = res.nbytes
        actual_grow(res, amount)
        grow_calls.append((before, res.nbytes))
        if len(grow_calls) == 5:
            raise BoundedProbe

    def extractor(_, dest, *, cancel_event, on_bytes, **_kwargs):
        fd = os.open(dest / "output", os.O_CREAT | os.O_WRONLY, 0o600)
        budget = extract._Budget(100, 5, extract.ExtractReport(), None, cancel_event, lambda: 0, on_bytes)
        try:
            extract._copy(Source(), fd, budget, None)
        except BoundedProbe:
            outcomes.append("bounded sentinel")
        finally:
            loop.call_soon_threadsafe(done.set)

    assert jobs_common.CANCEL_GRACE_SEC == 30
    with patch.object(staging.Reservation, "grow", bounded_grow):
        t = asyncio.create_task(jobs_common.extract_on_pool(
            extractor, None, op, progress, cancel, reservation=reservation, base_bytes=2,
        ))
        try:
            await reading.wait()
            t0 = loop.time()
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
            else:
                raise AssertionError("expected cancel")
            age = loop.time() - t0
            assert 29 <= age <= 39, age
            print(f'Unmodified extraction grace expired after {age:.3f} seconds')
            assert cancel.is_set() and not done.is_set()
            reservation.release()
            staging.remove_tree(op)
        finally:
            release_read.set()
        await done.wait()
        assert outcomes == ["bounded sentinel"] and grow_calls == [(0, 0)] * 5
    control = staging.reserve("control", 2)
    jobs_common.ReservationGrower(control)(3)
    assert control.nbytes == 2 + jobs_common.GROW_STEP
    control.release()
    print("W5 cancelled wrap after unmodified grace; actual post-read grow loop had five zero-to-zero advances and was stopped by a sentinel; live reservation advances once")

async def main():
    with tempfile.TemporaryDirectory() as td:
        workspace_fs.WORKSPACE_ROOT = Path(td)
        await asyncio.wait_for(delayed_worker(), 42)

asyncio.run(main())
PY
~~~

</details>

<details>
<summary>E1–E3 · Ordered persistence, failed saves, and checkpoint-pool ownership</summary>

~~~bash
for review_edition in 311 312 314; do
  review_python "$review_edition" <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)

import ast, asyncio, copy, tempfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Optional
from unittest.mock import patch

logging.getLogger().addHandler(logging.NullHandler())
log = logging.getLogger("review")

def methods(path, class_name, names, namespace):
    tree = ast.parse(path.read_text(), filename=str(path))
    definition = copy.deepcopy(next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name))
    definition.body = [node for node in definition.body if getattr(node, "name", None) in names]
    assert {x.name for x in definition.body} == set(names)
    exec(compile(ast.Module(body=[definition], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[class_name]

async def persistence():
    path = Path("/src/agentic/websocket_api.py")
    entered = asyncio.Event()
    release = asyncio.Event()
    saved = []
    warnings = []
    cancelled = []

    async def writer(**row):
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.append(row["msg_type"])
            raise
        saved.append(row["msg_type"])

    async def receive(_kind, payload):
        warnings.append(payload)

    namespace = dict(asyncio=asyncio, Optional=Optional, WebSocketConnection=object, logger=log,
                     save_chat_message=writer, MessageType=SimpleNamespace(ERROR="error"))
    Callback = methods(path, "StreamingCallback",
        {"__init__", "_ensure_persist_worker", "_persist_worker", "_report_persist_failure",
         "drain_persist_queue", "flush_persist_queue", "connection", "_persist"}, namespace)
    conn = SimpleNamespace(get_key=lambda: "sample", session_id="session", project_id="project",
                           user_id="actor", send_message=receive)
    cb = Callback(conn)
    cb._persist("single", {})
    await entered.wait()
    assert cb._persist_queue.qsize() == 0 and cb._persist_queue._unfinished_tasks == 1
    assert await cb.flush_persist_queue()
    assert not saved
    task = cb._persist_worker_task
    await cb.drain_persist_queue()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert cancelled == ["single"] and not saved
    assert cb._persist_queue._unfinished_tasks == 1

    entered.clear()
    cb = Callback(conn)
    cb._persist("first", {})
    cb._persist("second", {})
    await entered.wait()
    assert cb._persist_queue.qsize() == 1
    join_entered = asyncio.Event()
    join = cb._persist_queue.join
    async def observed_join():
        join_entered.set()
        return await join()
    cb._persist_queue.join = observed_join
    flush = asyncio.create_task(cb.flush_persist_queue())
    await join_entered.wait()
    assert not flush.done()
    release.set()
    assert await flush
    assert saved == ["first", "second"] and cb._persist_queue._unfinished_tasks == 0
    task = cb._persist_worker_task
    await cb.drain_persist_queue()
    await asyncio.gather(task, return_exceptions=True)
    print("E1 single in flight: false-success flush then cancellation with unfinished=1; two-item control joins FIFO")

    async def fail_save(**_row):
        return {"http_status": 503}
    namespace["save_chat_message"] = fail_save
    cb = Callback(conn)
    cb._persist("failure1", {})
    cb._persist("failure2", {})
    assert await cb.flush_persist_queue()
    assert [w["code"] for w in warnings] == ["persist_failed"]
    assert cb._persist_queue._unfinished_tasks == 0
    task = cb._persist_worker_task
    await cb.drain_persist_queue()
    await asyncio.gather(task, return_exceptions=True)
    print("E2 two rejected save attempts complete the queue and send one persistence warning")

async def checkpoint_owner():
    instances = []
    transitions = []
    fail_setup = False

    class Pool:
        def __init__(self, *, conninfo, max_size, kwargs, open):
            assert conninfo == "synthetic" and open is False
            self.opens = self.closes = 0
            instances.append(self)

        async def open(self):
            self.opens += 1

        async def close(self):
            self.closes += 1

    class Saver:
        def __init__(self, pool):
            self.pool = pool

        async def setup(self):
            if fail_setup:
                raise RuntimeError("injected setup failure")

    modules = {}
    for name in ("langgraph", "langgraph.checkpoint", "langgraph.checkpoint.postgres",
                 "langgraph.checkpoint.postgres.aio", "psycopg_pool"):
        modules[name] = ModuleType(name)
        modules[name].__path__ = []
    modules["langgraph.checkpoint.postgres.aio"].AsyncPostgresSaver = Saver
    modules["psycopg_pool"].AsyncConnectionPool = Pool
    namespace = dict(os=SimpleNamespace(environ={}), logger=log,
                     checkpointer=object(), get_setting=lambda key, default: True if key == "PERSISTENT_CHECKPOINTER" else default,
                     set_checkpointer=transitions.append)
    Orchestrator = methods(Path("/src/agentic/orchestrator.py"), "AgentOrchestrator",
                           {"_setup_checkpointer", "close"}, namespace)
    initial = namespace["checkpointer"]
    with patch.dict(sys.modules, modules):
        no_dsn = Orchestrator()
        await no_dsn._setup_checkpointer()
        assert no_dsn._checkpoint_pool is None and not instances
        namespace["os"].environ["DATABASE_URL"] = "synthetic"
        fail_setup = True
        failed = Orchestrator()
        await failed._setup_checkpointer()
        assert failed._checkpoint_pool is None and namespace["checkpointer"] is initial
        await failed.close()
        assert [(p.opens, p.closes) for p in instances] == [(1, 0)]
        fail_setup = False
        ready = Orchestrator()
        await ready._setup_checkpointer()
        assert ready._checkpoint_pool is instances[-1] is transitions[-1].pool
        await ready.close()
        assert [(p.opens, p.closes) for p in instances] == [(1, 0), (1, 0)]
    print("E3 no-configuration makes no pool; injected post-open setup failure and normal close each leave 0 calls to synthetic pool.close")

async def main():
    await asyncio.wait_for(persistence(), 5)
    await asyncio.wait_for(checkpoint_owner(), 5)

asyncio.run(main())
PY
done
~~~

</details>

<details>
<summary>P1–P5 · Supervisor and persisted plugin-job controls</summary>

~~~bash
for review_edition in 311 312 314; do
  review_python "$review_edition" <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)

import asyncio, io, json, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, "/src/services/plugin_runner")
from supervisor import jobs, manager, runlist, workers
from supervisor.logs import LogBuffer
from platform_version import PLATFORM_VERSION

class Clock:
    def __init__(self):
        self.delays = []
        self.grace_entered = asyncio.Event()
        self.advance = asyncio.Event()

    async def sleep(self, seconds):
        self.delays.append(seconds)
        if seconds == 5:
            self.grace_entered.set()
            await self.advance.wait()

    def now_iso(self):
        return "2030-01-01T00:00:00Z"

async def rollout_and_shutdown():
    with tempfile.TemporaryDirectory() as root:
        entered = asyncio.Event()
        release = asyncio.Event()
        old_stopped = asyncio.Event()
        startup_failed = True

        class Worker:
            def __init__(self, *, entry, **kwargs):
                self.entry = entry
                self.plugin_id, self.version = entry.key
                self.state = "created"
                self.jobs = {}

            async def start(self):
                self.state = "starting"
                if self.version == "2.0.0" and startup_failed:
                    entered.set()
                    await release.wait()
                    self.state = "failed"
                    return False
                self.state = "ready"
                return True

            async def stop(self):
                self.state = "stopped"
                if self.version == "1.0.0":
                    old_stopped.set()

            def describe(self):
                return {"version": self.version, "state": self.state}

        def entry(version):
            folder = Path(root) / "sample" / "versions" / version
            folder.mkdir(parents=True, exist_ok=True)
            return {"id": "sample", "version": version, "root": str(folder),
                    "manifest": {"id": "sample", "version": version, "actions": []}}

        class Client:
            status = 200
            platform = PLATFORM_VERSION
            version = "1.0.0"
            async def get(self, url, *, headers, timeout):
                assert timeout == 10
                return SimpleNamespace(status_code=self.status, json=lambda: {
                    "platformVersion": self.platform, "plugins": [entry(self.version)]
                })

        cfg = SimpleNamespace(spawn_as_user=False, uid_range=(42, 43), plugins_dir=root,
                              gateway_url="fixture:", runner_key="synthetic")
        client = Client()
        mgr = manager.Manager(cfg, LogBuffer(stream=io.StringIO()), Clock(), client)
        mgr.log = lambda message: None

        with patch.object(manager, "WorkerHandle", Worker):
            assert await mgr.reload() == "ok"
            old = mgr.find("sample", "1.0.0")
            assert old.state == "ready"
            client.status = 503
            assert await mgr.reload() == "degraded"
            assert mgr.find("sample", "1.0.0") is old and not old_stopped.is_set()
            client.status = 200
            client.version = "2.0.0"
            reload_task = asyncio.create_task(mgr.reload())
            await entered.wait()
            assert old.state == "ready" and mgr.find("sample", "1.0.0") is None
            assert mgr.find("sample", "2.0.0").state == "starting"
            release.set()
            assert await reload_task == "ok"
            assert old_stopped.is_set() and mgr.find("sample", "2.0.0").state == "failed"
            assert mgr.health()["state"] == "ok"
            startup_failed = False
            assert await mgr.reload() == "ok"
            assert mgr.find("sample", "2.0.0").state == "ready"
            print("P1 run-list refusal keeps old; replacement becomes lookup authority before ready; failed start leaves top-level ok with failed worker; next reload retries")

            cancelled = asyncio.Event()
            cleaned = asyncio.Event()
            unblocked = asyncio.Event()
            entered_finalizer = asyncio.Event()
            async def report_task():
                entered_finalizer.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
                    await unblocked.wait()
                    cleaned.set()
            active = asyncio.create_task(report_task())
            mgr.job_tasks.add(active)
            active.add_done_callback(mgr.job_tasks.discard)
            await entered_finalizer.wait()
            await mgr.stop_all()
            assert not active.done() and not cleaned.is_set()
            await cancelled.wait()
            assert not active.done()
            unblocked.set()
            await asyncio.gather(active, return_exceptions=True)
            assert cleaned.is_set() and not mgr.job_tasks
            print("P2 stop_all requests report-task cancellation and returns before asynchronous task cleanup")

async def worker_calls():
    logs = LogBuffer(stream=io.StringIO())
    clock = Clock()
    manifest = runlist.Entry("sample", "1.0.0", "/unused", {
        "routine": runlist.Action("unused", 60, True)
    })
    cfg = SimpleNamespace(spawn_as_user=False, max_concurrent=2, kill_grace=5)
    worker = workers.WorkerHandle(settings=cfg, logs=logs, clock=clock, entry=manifest, uid=None,
                                  should_run=lambda _: False, release_uid=lambda _: None)
    worker.state = "ready"
    worker.proc = process = SimpleNamespace()
    incoming = asyncio.Queue()
    kills = []
    async def send(frame):
        incoming.put_nowait(frame)
    def kill(reason):
        kills.append(reason)
        worker._kill_reason = reason
        worker._on_exit(process, -9)
    worker._send = send
    worker._kill = kill
    dummy_ready = asyncio.get_running_loop().create_future()

    async def launch_both():
        tasks = [asyncio.create_task(worker.invoke("routine", {}, {}, "synthetic", 30, job_id=name)) for name in ("a", "b")]
        frames = [await incoming.get(), await incoming.get()]
        assert {f["type"] for f in frames} == {"invoke"}
        assert all(worker.jobs[x] in worker.pending for x in ("a", "b"))
        try:
            await worker.invoke("routine", {}, {}, "synthetic", 30)
        except workers.RunnerError as e:
            assert (e.status, e.code) == (429, "plugin_busy")
        else:
            raise AssertionError("concurrency cap not applied")
        return tasks

    first, second = await launch_both()
    assert await worker.cancel("a")
    cancel_frame = await incoming.get()
    worker._handle({"type": "result", "id": cancel_frame["id"], "ok": False,
                    "error": {"code": "cancelled", "message": "fixture"}}, dummy_ready)
    worker._handle({"type": "result", "id": worker.jobs["b"], "ok": True, "result": {"ok": "second"}}, dummy_ready)
    assert (await first)["error"]["code"] == "cancelled"
    assert (await second)["result"] == {"ok": "second"}
    assert not kills
    clock.advance.set()
    await asyncio.gather(*worker._tasks)
    assert not kills

    clock.grace_entered.clear()
    clock.advance.clear()
    first, second = await launch_both()
    assert await worker.cancel("a")
    assert (await incoming.get())["type"] == "cancel"
    await clock.grace_entered.wait()
    assert not first.done() and not second.done() and not kills
    clock.advance.set()
    a, b = await asyncio.gather(first, second, return_exceptions=True)
    assert a["error"]["code"] == "cancelled"
    assert isinstance(b, workers.RunnerError) and b.code == "worker_restarted"
    assert kills == ["cancel"]
    assert not worker.pending and not worker.jobs
    print("P3 fake pipe boundaries: per-handle cap; cooperative cancellation preserves peer; grace expiry ends peer with worker_restarted")

async def result_reports():
    logstream = io.StringIO()
    logs = LogBuffer(max_lines=2, stream=logstream)
    cfg = SimpleNamespace(gateway_url="fixture:", job_report_delays=(1, 2, 4))
    handle = SimpleNamespace(plugin_id="sample", version="1.0.0")

    async def drive(outcomes, body):
        t = Clock()
        outgoing = []
        sequence = iter(outcomes)
        async def post(url, *, content, headers, timeout):
            assert timeout == 10 and url.startswith("fixture:")
            outgoing.append(json.loads(content))
            next_step = next(sequence)
            if isinstance(next_step, Exception):
                raise next_step
            return SimpleNamespace(status_code=next_step)
        ok = await jobs.report(client=SimpleNamespace(post=post), settings=cfg, clock=t, logs=logs,
                               handle=handle, job_id="sample", token="synthetic", body=body)
        return ok, t.delays, outgoing

    body = {"status": "succeeded", "result": {"n": 1}}
    ok, waits, sent = await drive([503, OSError("fixture"), 429, 201], body)
    assert ok and waits == [1, 2, 4] and sent == [body] * 4
    ok, waits, sent = await drive([400], body)
    assert not ok and not waits and len(sent) == 1
    for invalid in ("\ud800", float("inf"), object()):
        ok, waits, sent = await drive([201], {"status": "succeeded", "result": {"n": invalid}})
        assert ok and not waits and sent[0]["error"]["code"] == "invalid_result"
    logs.add("sample", "1.0.0", "one")
    logs.add("sample", "2.0.0", "two\x1b")
    logs.event("sample", "2.0.0", "three")
    assert logs.tail("sample", 10) == ["2.0.0 two\\x1b", "2.0.0 [runner] three"]
    print("P4 fake reporter retries transport/503/429, stops on 400, uses invalid_result for 3 unencodable forms; log tail is bounded and escapes controls")

async def main():
    for fn in (rollout_and_shutdown, worker_calls, result_reports):
        await asyncio.wait_for(fn(), 5)

asyncio.run(main())
PY
done

review_node <<'NODE'
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';

const path = '/src/webapp/src/lib/plugins/jobs.ts';
const original = readFileSync(path, 'utf8');
const sources = original.split('\n');
assert.equal(sources.filter(line => /^import /.test(line)).length, 6);
const local = sources.filter(line => !/^import /.test(line)).join('\n').replace(/^export /gm, '');
const body = stripTypeScriptTypes(local, { mode: 'transform' });
const load = new Function('prisma', 'now', 'runnerHealth', 'isStorableJson',
  body + '\nreturn {markRunning, reportProgress, completeJob, cancelJobRow, refreshJob};');

const jobId = '12345678-1234-4234-9234-123456789abc';
const base = new Date('2030-01-01T00:00:00.000Z');
const pathEqual = (value, path, expected) => path.length === 1 && value[path[0]] === expected;
function latch() {
  let release;
  const wait = new Promise(resolve => { release = resolve });
  return { wait, release };
}
function fixture(status = 'queued', bootId = null) {
  let at = base;
  let observedBoot = 'boot-test';
  const log = [];
  const row = {
    id: 'row-test', key: jobId, pluginId: 'fixture', ownerId: 'local', userId: 'local',
    namespace: 'live', ownerType: 'user', collection: '__jobs',
    value: {
      status, actionId: 'sample', context: {}, pick: null, progress: null,
      result: null, error: null, bootId, deadline: '2030-01-01T00:01:00.000Z',
      createdAt: base.toISOString(), updatedAt: base.toISOString(),
    }
  };
  const lock = latch();
  const hit = latch();
  let pauseStatus = null;
  const prisma = {pluginData: {
    async findFirst({where}) {
      for (const [key, val] of Object.entries(where)) assert.equal(row[key], val);
      return structuredClone(row);
    },
    async findUnique({where}) {
      assert.equal(where.id, row.id);
      return structuredClone(row);
    },
    async updateMany({where, data}) {
      assert.equal(where.id, row.id);
      assert.deepEqual(where.value.path, ['status']);
      assert.equal(data.sizeBytes, Buffer.byteLength(JSON.stringify(data.value)));
      if (data.value.status === pauseStatus) {
        pauseStatus = null;
        hit.release();
        await lock.wait;
      }
      const matches = pathEqual(row.value, where.value.path, where.value.equals);
      log.push([where.value.equals, row.value.status, data.value.status, matches]);
      if (matches) row.value = structuredClone(data.value);
      return {count: matches ? 1 : 0};
    },
    async deleteMany({where}) {
      assert.equal(where.value.equals, jobId);
      assert.equal(where.collection, '__jobs_active');
      return {count: 1};
    }
  }};
  const readHealth = async () => {
    if (observedBoot instanceof Error) throw observedBoot;
    return {bootId: observedBoot};
  };
  return {
    api: load(prisma, () => at, readHealth, () => true), row, log, hit, lock,
    view: () => ({ ...structuredClone(row.value), jobId, pluginId: 'fixture', userId: 'local' }),
    pause: status => { pauseStatus = status },
    setAt: next => { at = new Date(next) },
    setBoot: next => { observedBoot = next },
  };
}

const report = { message: 'staged', fields: { count: '3' } };
{
  const f = fixture();
  f.pause('running');
  const mark = f.api.markRunning(f.view(), 'boot-test');
  await f.hit.wait;
  assert.equal((await f.api.reportProgress('fixture', 'local', jobId, report)).changed, true);
  assert.deepEqual(f.row.value.progress, report);
  f.lock.release();
  assert.equal((await mark).status, 'running');
  assert.deepEqual(f.log, [
    ['queued','queued','queued',true], ['queued','queued','running',true]
  ]);
  assert.equal(f.row.value.progress, null);
}
{
  const f = fixture();
  assert.equal((await f.api.reportProgress('fixture','local',jobId,report)).changed, true);
  await f.api.markRunning(f.view(), 'boot-test');
  assert.deepEqual(f.row.value.progress, report);
}
{
  const f = fixture('running', 'boot-test');
  f.pause('succeeded');
  const end = f.api.completeJob('fixture', 'local', jobId, {status: 'succeeded', result: {}});
  await f.hit.wait;
  assert.equal((await f.api.reportProgress('fixture', 'local', jobId, report)).changed, true);
  f.lock.release();
  await end;
  assert.equal(f.row.value.status, 'succeeded');
  assert.equal(f.row.value.progress, null);
}
{
  const f = fixture('running', 'boot-test');
  f.pause('succeeded');
  const end = f.api.completeJob('fixture', 'local', jobId, {status: 'succeeded', result: {}});
  await f.hit.wait;
  assert.equal((await f.api.cancelJobRow(f.view())).changed, true);
  f.lock.release();
  assert.equal((await end).changed, false);
  assert.equal(f.row.value.status, 'cancelled');
  assert.deepEqual(f.log, [
    ['running','running','cancelled',true], ['running','cancelled','succeeded',false]
  ]);
}
{
  const f = fixture('running', 'boot-test');
  f.setBoot(new Error('fixture availability failure'));
  assert.equal((await f.api.refreshJob(f.view())).status, 'running');
  f.setAt('2030-01-01T00:01:01.000Z');
  assert.equal((await f.api.refreshJob(f.view())).error.code, 'timeout');
  const restarted = fixture('running', 'boot-old');
  assert.equal((await restarted.api.refreshJob(restarted.view())).error.code, 'runner_restarted');
}

console.log('P5 exact jobs.ts, fake compare-and-swap store: queued+progress and running+progress overwrote acked progress; serial retains it; terminal cancel fence, boot mismatch, and deadline controls passed');
NODE
~~~

</details>

<details>
<summary>Q1–Q3 · Guard lifetime, synthetic resource decisions, and UTC oracle</summary>

~~~bash
for review_edition in 311 312 314; do
  review_python "$review_edition" <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)

import asyncio, threading
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, "/src/recon_orchestrator")
import admission_ledger as admission
import job_dispatcher as dispatcher

logging.getLogger().addHandler(logging.NullHandler())
GIB = 1024**3

async def cancel_guard():
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()
    exited = asyncio.Event()
    concurrent = []
    def fake_tick(kind):
        if kind == "held":
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(5)
            loop.call_soon_threadsafe(exited.set)
        else:
            concurrent.append(not release.is_set())
        return {"case": kind}
    with patch.object(dispatcher, "run_dispatcher_tick", fake_tick):
        task = asyncio.create_task(dispatcher._guarded_tick("held"))
        try:
            await entered.wait()
            assert dispatcher._tick_in_progress
            assert await dispatcher._guarded_tick("before_cancel") is None
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            assert not dispatcher._tick_in_progress and not exited.is_set()
            assert await dispatcher._guarded_tick("cancelled_await",) == {"case": "cancelled_await"}
            assert concurrent == [True]
        finally:
            release.set()
        await exited.wait()
    print("Q1 live blocking tick excluded a peer; cancelling the await released the guard before old thread exit")

async def budget_disagreement():
    machine = lambda: (8 * GIB, 7 * GIB)
    fixture = {"OS_HEADROOM_MEM": "2g", "SERVICE_BASELINE_MEM": "6g",
               "REDAMON_MEM_GOVERNOR": "true", "RECON_JOB_ENVELOPE_MEM": "4g",
               "JOB_QUEUE_MAX_CONCURRENT": "4", "JOB_QUEUE_MIN_FREE_DISK": "0"}
    called = []
    def request(url, key, *args, **kwargs):
        called.append(url.rsplit("/", 1)[-1])
        if called[-1] == "candidates":
            return {"activeCount": 0, "candidates": [{"id": "one", "projectId": "project",
                     "kind": "sample", "envelopeBytes": 4 * GIB}]}
        return {"ok": True}
    with patch.dict(os.environ, fixture), patch.object(dispatcher, "_free_disk_bytes", return_value=40 * GIB), \
            patch.object(dispatcher, "webapp_base", return_value="fixture:"), \
            patch.object(dispatcher, "internal_key", return_value="synthetic"), \
            patch.object(dispatcher, "request_json", request):
        ledger = admission.ReservationLedger(mem_reader=machine, pressure_fn=lambda: "normal")
        assert ledger.remaining_for_new() == 0
        row = dispatcher.run_dispatcher_tick(SimpleNamespace(ledger=ledger))
        assert row["candidates"] == 1 and row["dispatched"] == 0 and called == ["candidates"]
        assert (await ledger.try_admit("one", 4 * GIB)).admitted
        assert not (await ledger.try_admit("two", 4 * GIB)).admitted
        await ledger.release("one")
        os.environ["SERVICE_BASELINE_MEM"] = "2g"
        assert ledger.remaining_for_new() == 4 * GIB
        row = dispatcher.run_dispatcher_tick(SimpleNamespace(ledger=ledger))
        assert row["candidates"] == 1 and row["dispatched"] == 1 and called == ["candidates", "candidates", "dispatch"]
    print("Q2 same synthetic budget: empty ledger admits a physical-fit job that the advisory pool check declined; fit and second-job controls agree")

async def main():
    for case in (cancel_guard, budget_disagreement):
        await asyncio.wait_for(case(), 5)

asyncio.run(main())
PY
done

for review_zone in '' Pacific/Auckland; do
  review_zone="$review_zone" review_node <<'NODE'
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
const ts = readFileSync('/src/webapp/src/lib/cron.ts', 'utf8');
assert.doesNotMatch(ts, /^import /m);
const body = stripTypeScriptTypes(ts.replace(/^export /gm, ''), {mode:'transform'});
const {nextCronRun, minCronIntervalMinutes} = new Function(body + '\nreturn {nextCronRun, minCronIntervalMinutes};')();

const scheduleRaw = readFileSync('/src/webapp/src/lib/scanSchedule.ts', 'utf8');
const schedulePrefix = scheduleRaw.split('// ---------------------------------------------------------------- RAM')[0];
const scheduleBody = stripTypeScriptTypes(schedulePrefix.replace(/^import .*\n/gm, '').replace(/^export /gm, ''), {mode:'transform'});
const {parseCron, CronParseError} = new Function(body + '\nreturn {parseCron, CronParseError};')();
const {minIntervalMinutes, validateSchedule} = new Function('nextCronRun', 'minCronIntervalMinutes', 'parseCron', 'CronParseError',
  scheduleBody + '\nreturn {minIntervalMinutes, validateSchedule};')(nextCronRun, minCronIntervalMinutes, parseCron, CronParseError);
assert.equal(minIntervalMinutes(), 15);
const cutoffs = [minIntervalMinutes(), 30];
const samples = [];
let rules = 0, lowerBounds = 0, rejecting = cutoffs.map(() => 0), higher = 0;
for (let h = 0; h < 24; h++) {
  for (let k = h + 1; k < 24; k++) {
    for (let a = 0; a < 60; a++) {
      for (let b = a + 1; b < 60; b++) {
        const times = [60 * h + a, 60 * h + b, 60 * k + a, 60 * k + b, 1440 + 60 * h + a];
        const actual = Math.min(...times.slice(1).map((v, i) => v - times[i]));
        const expr = `${a},${b} ${h},${k} * * *`;
        const estimated = minCronIntervalMinutes(expr);
        rules++;
        if (estimated < actual) lowerBounds++;
        if (estimated > actual) higher++;
        cutoffs.forEach((cutoff, index) => {
          if (estimated < cutoff && actual >= cutoff) {
            rejecting[index]++;
            if (index === 0 && samples.length < 3) samples.push({expr, actual, estimated});
          }
        });
      }
    }
  }
}
assert.equal(rules, 488520);
assert.equal(higher, 0);
assert.equal(minCronIntervalMinutes('0,59 0,1 * * *'), 1);
assert.equal(minCronIntervalMinutes('0,59 0,12 * * *'), 1);
assert.ok(rejecting.every(x => x > 0));
for (const pattern of ['0,59 0,1 * * *', '0,59 0,12 * * *']) {
  const [_, hour] = pattern.split(' ');
  const hours = hour.split(',').map(Number);
  for (const instant of ['2030-01-01T00:00:00Z','2030-01-01T00:59:00Z','2030-01-01T12:59:00Z']) {
    const from = new Date(instant);
    let clock = new Date(Math.floor(from.getTime() / 60000) * 60000 + 60000);
    while (!hours.includes(clock.getUTCHours()) || ![0,59].includes(clock.getUTCMinutes())) clock = new Date(clock.getTime() + 60000);
    assert.equal(nextCronRun(pattern, from).getTime(), clock.getTime());
  }
}

const leap = y => y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
const horizon = 4 * 366 * 24 * 60 * 60000;
const uncovered = [];
for (let y = 2000; y < 2400; y++) {
  const from = new Date(Date.UTC(y, 2, 1));
  let n = y + 1;
  while (!leap(n)) n++;
  const want = new Date(Date.UTC(n, 1, 29));
  const next = nextCronRun('0 0 29 2 *', from);
  if (want.getTime() - from.getTime() > horizon) {
    assert.equal(next, null);
    uncovered.push(y);
  } else {
    assert.equal(next.getTime(), want.getTime());
  }
}
assert.deepEqual(uncovered, [2096,2097,2098,2099,2196,2197,2198,2199,2296,2297,2298,2299]);
assert.equal(nextCronRun('0 0 30 2 *', new Date('2096-03-01T00:00:00Z')), null);
assert.throws(() => validateSchedule({mode:'cron', cronExpr:'0,59 0,12 * * *'}, new Date('2030-01-01T00:00:00Z')), /minimum is 15/);
assert.throws(() => validateSchedule({mode:'cron', cronExpr:'0 0 29 2 *'}, new Date('2096-03-01T00:00:00Z')), /never matches a real date/);
assert.equal(validateSchedule({mode:'cron', cronExpr:'0 0 29 2 *'}, new Date('2026-03-01T00:00:00Z')).nextRunAt.toISOString(), '2028-02-29T00:00:00.000Z');
console.log(JSON.stringify({rules, lowerBounds, cutoffs, rejecting, higher, samples, uncovered}));
NODE
done
~~~

</details>

<details>
<summary>J6 · Persistence across two isolated Python processes</summary>

~~~bash
review_restart_probe=$(cat <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)

import asyncio, json, shutil
from pathlib import Path
import job_runner

logging.getLogger().addHandler(logging.NullHandler())
job_runner.WORKSPACE_ROOT = Path("/lab/workspace")
job_runner._governed_max_jobs = lambda: 1
pid = "local-project"
manifest = Path("/lab/fixture-ids.json")

async def first():
    registry = job_runner.JobRegistry()
    async def complete(*_):
        return {"success": True, "output": "stable record"}
    ended_id = (await registry.spawn(pid, "complete", {}, complete))["job_id"]
    assert (await registry.wait(pid, ended_id))["status"] == "done"

    started = asyncio.Event()
    async def awaiting(_, __, append_log):
        await append_log("physical write before process exit")
        started.set()
        await asyncio.Event().wait()
    active_id = (await registry.spawn(pid, "interrupted", {}, awaiting))["job_id"]
    await started.wait()
    assert registry.status(pid, active_id)["status"] == "running"
    manifest.write_text(json.dumps({"completed": ended_id, "live": active_id}))
    os._exit(0)

def read_fresh():
    ids = json.loads(manifest.read_text())
    registry = job_runner.JobRegistry()
    assert registry.status(pid, ids["live"])["status"] == "running"
    registry.recover_on_boot()
    rows = {row["job_id"]: row for row in registry.list(pid)}
    assert rows[ids["completed"]]["status"] == "done"
    assert rows[ids["live"]]["status"] == "interrupted"
    assert rows[ids["live"]]["ended_at"]
    assert "physical write" in registry.status(pid, ids["live"])["tail"]
    assert registry._jobs == {}
    print("J6 fresh Python process recovered abandoned running metadata to interrupted; done and log files survived, no live tasks restored")
    shutil.rmtree(job_runner.WORKSPACE_ROOT)
    manifest.unlink()

if sys.argv[1] == "first":
    asyncio.run(first())
elif sys.argv[1] == "second":
    read_fresh()
else:
    raise AssertionError(sys.argv)
PY
)
(
  redamon_lab=$(mktemp -d -p /var/tmp redamon-review.XXXXXXXX)
  trap 'rmdir "$redamon_lab"' EXIT
  printf '%s\n' "$review_restart_probe" | review_python 311 first
  printf '%s\n' "$review_restart_probe" | review_python 311 second
)
~~~

</details>

<details>
<summary>P6 and E6 · Fake SDK storage and blocking log generator</summary>

~~~bash
for review_edition in 311 312 314; do
  review_python "$review_edition" <<'PY'
import logging, os, socket, sys, unittest
sys.path[:0] = ['/src/agentic', '/src/agentic/tests']
def deny_external(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
        raise AssertionError(f'outside boundary: {event}')
    if event == 'socket.__new__' and args[1] != socket.AF_UNIX:
        raise AssertionError('outside boundary: non-Unix socket')
sys.addaudithook(deny_external)

import ast, asyncio, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import AsyncGenerator

sys.path.insert(0, "/src/services/plugin_runner/sdk")
from redamon_plugin_sdk.testing import FakeSdk
logging.getLogger().addHandler(logging.NullHandler())

sdk_case_path = Path("/src/services/plugin_runner/tests/test_sdk_fake.py")
sdk_case_names = {"test_data_expires_by_the_injected_clock", "test_data_owners_are_separate",
                  "test_data_values_are_copied_like_json", "test_progress_is_recorded_in_order"}
sdk_tree = ast.parse(sdk_case_path.read_text(), filename=str(sdk_case_path))
selected = [n for n in sdk_tree.body if getattr(n, "name", None) in sdk_case_names]
assert len(selected) == len(sdk_case_names)
sdk_ns = {"asyncio":asyncio, "FakeSdk":FakeSdk}
exec(compile(ast.Module(body=selected, type_ignores=[]), str(sdk_case_path), "exec"), sdk_ns)
for name in sorted(sdk_case_names):
    sdk_ns[name]()
print("P6 four source-selected FakeSdk cases passed for TTL, owner scope, JSON copy, and ordered progress")

path = Path("/src/recon_orchestrator/container_manager.py")
tree = ast.parse(path.read_text(), filename=str(path))
definition = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ContainerManager")
definition.body = [node for node in definition.body if getattr(node, "name", None) == "_follow_container_logs"]
scope = dict(asyncio=asyncio, threading=threading, time=time, AsyncGenerator=AsyncGenerator,
             LOG_STREAM_BUFFER_LINES=2, LOG_STREAM_IDLE_CHECK_S=60, LOG_STREAM_LIVENESS_S=60,
             logger=logging.getLogger("test"))
exec(compile(ast.Module(body=[definition], type_ignores=[]), str(path), "exec"), scope)
Manager = scope["ContainerManager"]

async def case():
    loop = asyncio.get_running_loop()
    opened = asyncio.Event()
    read_began = asyncio.Event()
    finished = asyncio.Event()
    close_flag = threading.Event()

    class QuietLog:
        def __iter__(self):
            loop.call_soon_threadsafe(read_began.set)
            assert close_flag.wait(5)
            loop.call_soon_threadsafe(finished.set)
            return iter(())

        def close(self):
            close_flag.set()

    def logs(**params):
        assert params == {"stream": True, "follow": True}
        loop.call_soon_threadsafe(opened.set)
        return QuietLog()

    manager = Manager()
    with ThreadPoolExecutor(max_workers=1) as pool:
        manager._log_stream_executor = pool
        stream = manager._follow_container_logs(SimpleNamespace(logs=logs))
        pending = asyncio.create_task(anext(stream))
        await opened.wait()
        await read_began.wait()
        assert not close_flag.is_set()
        pending.cancel()
        [result] = await asyncio.gather(pending, return_exceptions=True)
        assert isinstance(result, asyncio.CancelledError)
        await finished.wait()
        await stream.aclose()
    print("E6 quiet blocking log fixture woke after generator consumer cancellation closed its stream")

async def guarded():
    await asyncio.wait_for(case(), 8)
asyncio.run(guarded())
PY
done
~~~

</details>

## 10. Execution policy

This was an independent, serial review in the local checkout. I used the nine numbered requirements in the evaluation protocol and recorded its execution policy in this tenth section. Only this Markdown report was edited, through apply_patch. Local experiments used the read-only checkout and disposable temporary storage. Execution boundaries excluded application workflows, service access, real credentials and accounts, network access, frontends, and product-domain procedures.
