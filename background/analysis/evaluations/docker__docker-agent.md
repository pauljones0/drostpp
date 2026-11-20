# Docker Agent architecture and orchestration evaluation

## 1. Snapshot, scope, and elapsed-time evidence.

Reviewed `docker/docker-agent` at **`00578ca8a20d6e3d02d2cca92dd2c80ab0e979b7`**, the merge of “Bump direct Go dependencies,” dated 2026-11-18 16:12:09 UTC. The opening check at **2026-11-19 17:07:56 UTC** returned that exact commit and zero bytes of tracked or untracked porcelain status. The checkout was the source of record. Builds and tests used a separate Git archive in the evaluation workspace, with temporary modfiles and Go overlays. GUI and frontend quality were out of scope. The worktree board is included because it owns worker processes, task routing, state and recovery.

**Overall assessment.** Docker Agent provides a capable single-process agent engine and a separate process supervisor for local worktree tasks. Its strongest architectural features are the explicit provider and tool contracts, fresh child transcripts, workspace-specific tool reconstruction, and the distinction between visible stream completion and resource cleanup. The highest-impact defects arise where ownership still lives in a runtime-wide slot or is split across independent systems. A child can consume a parent's input queue, a completed API turn can lose an input from its durable transcript, a deleted server-owned runtime can retain detached work, and a board transition can be saved without its prompt. Several of these were reproduced against the relevant Go paths with deterministic fixtures.

The protocol README lists nine numbered sections. Sections 1–9 retain its order and wording. Section 10 supplies the prioritized improvements explicitly requested.

**Isolation and exception.** Tests and fixture processes ran with a cleared environment, private home and temporary directories, and a Bubblewrap network namespace with loopback and no external route. They used local cached modules, fake completions, SQLite, local Git, tmux, and Unix or loopback HTTP. One host-side version probe of a second Go installation, run from the archived checkout, inadvertently auto-downloaded Go 1.27.4 into the shared toolchain cache. The before/after cache listing confirms the download. This was an exception to the offline constraint. The downloaded toolchain was excluded, no accounts or credentials were used for tests, and all executed builds and tests used the pre-existing Go 1.27.3 inside the sandbox.

**UTC working period.** 2026-11-19 **17:07:56–17:37:56 UTC**, **30 minutes** of active review through the closing audit. During 17:07–17:13 I verified provenance and isolation, mapped the core, ran the broad and race suites, and investigated their build and subprocess failures. During 17:13–17:22 I traced worker and lifecycle ownership, built targeted profiles and exercised board, runtime, queue, filesystem and migration controls. During 17:22–17:37 I broadened the native runtime and MCP coverage, confirmed the process and admission findings, reran controls from the report's reconstructed config and audited citations, commands and artifacts. Tests ran alongside source review and fixture work. I removed the disposable archive and test cache. The closing check again returned HEAD `00578ca8a20d6e3d02d2cca92dd2c80ab0e979b7` and zero bytes from `git status --porcelain=v1 --untracked-files=all -z`.

## 2. Core architecture and end-to-end control/data flow.

Docker Agent's execution unit is a **session stream**. A team is an in-process graph of named agent definitions, model clients and toolsets. A normal tool call, a delegated sub-session, a background shell job and a worktree board card have different owners and lifetimes. The project exposes this engine through CLI, embedders, ACP, MCP, A2A, and HTTP. The board supervises independent CLI processes. These paths share the native engine where applicable, while each adapter chooses how to start, serialize and close its runs. `pkg/team/team.go:18–35,116–157`, `pkg/runtime/runtime.go:239–345,719–753`, `pkg/board/model.go:1–6`, `pkg/mcp/server.go:159–184,248–315`, `pkg/acp/agent.go:104–168,738–795`.

```text
Config source → versioned config + flavor resolution → team loader
                       ↓                                  ↓
             validated model and tool registries      linked Agent graph
                                                           ↓
CLI / HTTP / protocol adapter → session + runtime → RunStream
                                                           ↓
            steer and follow-up → hook / context / budget → provider stream
                                                           ↓
       session store ← persistence observer ← typed events ← tool dispatcher
                                                           ↓
                  child session / harness / tool process / workspace

Board JSON → controller → tmux pane → separate CLI run → session database
                  ↑                      ↓
                  └── Unix HTTP snapshot + SSE, follow-up POST ──┘
```

**Construction.** The loader clones the host's runtime configuration, resolves the workspace, parses the versioned source with selected flavors, merges hook and provider definitions, resolves models and compiles tool schemas. It builds agent objects first, then connects local and imported sub-agent, handoff and forced-handoff edges. Imported sources are cached per resolution and kept separate from local names. Strict mode allows dependency-light hosts to reject unavailable features up front. A workspace factory on each agent rebuilds tool configuration with a different working directory while retaining model and instruction options. Loader failures dispose partially created agent tool resources. The stock composition root registers historical config migrations, built-in tools, concrete providers, OCI/URL resolution, JS, wrappers, and deferred tools. `pkg/teamloader/teamloader.go:244–361,562–645,676–692`, `pkg/teamloader/defaults/defaults.go:24–49`, `pkg/config/runtime.go:101–130`.

**Execution.** The runtime constructs a channel and a per-run observer chain, registers the live session, and starts one loop goroutine. It stamps conversation context, binds tool handlers, runs start hooks, emits the user's boundary, and either dispatches a harness or repeatedly assembles the provider payload. The native loop resolves the active agent, refreshes visible tools, checks iteration and budget, prepares the context, executes a streamed request, records the result, and dispatches the tool batch. A typed return value decides continuation or exit. Stop hooks, steering, a single follow-up, and routed continuation are evaluated at explicit boundaries. The loop subscribes to plan and toolset changes and unregisters at teardown. `pkg/runtime/loop.go:145–275,277–381,404–572,665–736,982–1097`.

| Orchestration mechanism | State and completion |
| --- | --- |
| Synchronous `transfer_task` | A call validates a declared sub-agent, checks lineage and depth (10), constructs a fresh child session with task and expected output, inherits selected approvals, attachments and workspace, drains and forwards the child's stream, then returns its last assistant response or error. Child history is attached to the parent and persisted on completion. `pkg/runtime/agent_delegation.go:54–95,226–304,381–459,733–799`. |
| Handoff and hook routing | Handoff changes the active agent within the conversation. A forced handoff advances after normal completion. Hook routing uses per-invocation state, an allowlist, a 100-transition bound, and recorded decisions. New user input resets a routed invocation to its entry agent and steering waits until its boundary. `pkg/runtime/agent_delegation.go:802–871`, `pkg/runtime/routing.go:20–114,127–184`, `pkg/runtime/loop.go:1023–1084`. |
| Background agents | A runtime-owned handler admits and immediately returns task IDs, caps active executions at 20 and retained entries at 100, and prunes joined terminal entries on pressure. The child context outlives the initiating turn. The runtime pins the child agent and uses non-interactive policy with inherited permissions. `wait_background_agents` joins an ordered set at one shared deadline and reports drained completion separately from the status field. Cancel marks stop and requests cancellation while cleanup can still be in progress. `pkg/tools/builtin/agent/agent.go:34–40,135–167,310–328,344–415,458–515,561–600`, `pkg/tools/builtin/agent/wait.go:46–146`, `pkg/runtime/agent_delegation.go:471–612,696–730`. |
| Planning | Plan tools expose named, versioned documents with content and status, optimistic revision checks, and notifications. The native toolset shares its storage/notifier across agents and binds file import/export to a workspace. The API and CLI service adapt the same storage operations. Plans inform the model and the host. The native loop advances through tool choices, handoffs and routing hooks. There is no scheduler that treats plan items as executable DAG nodes. `pkg/tools/builtin/plan/plan.go:200–277,307–337,981–1049`, `pkg/tools/builtin/plan/creator.go:16–69`, `pkg/plans/service.go:29–156`, `pkg/runtime/loop.go:1023–1097`. |
| Background shell jobs | A toolset owns an in-memory job map, starts an OS command in a process group, monitors direct-child exit and captured output, and supports view, wait and stop. Output is bounded to 10 MiB per job. Optional completion recall goes through the embedder's wake-up path or the native steering queue. The map has no job-count or completed-job retention cap in this path. `pkg/tools/builtin/backgroundjobs/backgroundjobs.go:41–124,231–342,413–476,662–688`, `pkg/tools/builtin/backgroundjobs/cmd_unix.go:10–25`, `pkg/runtime/runtime.go:1492–1516`. |
| Worktree board | A JSON card maps stable card, tmux, worktree, branch and conversation IDs. Creation starts the current executable through a private tmux server with a per-card Unix control socket. The controller watches snapshots and events, restarts a dead pane using the same conversation, and resends a forward stage's prompt through follow-up or launches with it when the pane is gone. A new board process acquires an OS lock and reconciles persisted cards. The board has one watcher per card and no explicit admission limit. `pkg/board/app.go:49–88,421–542`, `pkg/board/controller.go:97–131,226–403,463–556`, `pkg/board/tmux.go:44–91,196–248`, `pkg/board/lock_unix.go:13–36`. |

**Transport and persistence.** The API owns a cached runtime per session on first use. A per-session streaming lock protects the assistant/tool message sequence against concurrent writes and also gates direct attached runs. Another lock coordinates model updates and rollback. The ordinary run POST sends request-scoped SSE and cancellation on disconnection. Attached runs register a separate sequenced event source and an input injector. The replay log retains 1,024 events per session with a monotonically increasing sequence and a bounded channel per subscriber. Clients can reconnect with their cursor and receive a gap marker when it has been evicted. The durable store is a different boundary. SQLite stores session metadata plus ordered message, sub-session, summary, error and routing items. Budgets, queue entries, task handles and the replay cursor are in-process state. Reconstruction restores the conversation and configuration that were committed. `pkg/server/session_manager.go:256–275,451–470,568–620,1041–1235,1348–1394,1645–1779`, `pkg/server/server.go:515–563,694–768`, `pkg/server/eventlog.go:9–12,76–130,139–235`, `pkg/session/store.go:93–154,1007–1024,1168–1185,1313–1340`.

**Workspace ownership.** A child can use its parent's workspace or branch a dedicated git worktree from the workspace's current HEAD. The latter rebuilds the whole reachable team graph and rebinds its toolsets, copies model overrides, runs workspace-creation hooks, disables the workspace-insensitive response cache for cloned agents, and shares the parent store and budget. The runtime tears down the clone and toolsets while retaining the branch and files for inspection, including on setup failure. This is filesystem/worktree scoping. Process isolation comes from a separately configured sandbox, where used. The board uses the upstream default branch when discoverable and owns forced removal of its card worktree and branch. `pkg/runtime/background_worktree.go:36–150`, `pkg/team/workspace.go:14–103`, `pkg/session/working_dir.go:50–115`, `pkg/worktree/worktree.go:118–184,303–315,364–376`, `pkg/board/app.go:456–460,524–542`, `pkg/board/git.go:15–24,121–144`.

**ACP turn ownership.** An arriving prompt establishes a new generation and cancels the previous prompt. It must acquire the turn token and revalidate its generation before changing the session. Closing retires the client terminal and MCP owners, cancels the turn, waits for its token to return, closes the runtime and joins tool cleanup. That explicit close path is a useful precedent for server-managed sessions. This comparison is based on local source. `pkg/acp/agent.go:113–164,195–273,738–793`.

## 3. Why the design works and its governing invariants.

1. **An adapter owns the conversation writer.** Native turns mutate the session and emit matching tool results. The server admits one stream per session and holds that ownership until the inner stream has been drained. A returned close is an important handoff between writers. `pkg/server/session_manager.go:1079–1095,1169–1235`, `pkg/runtime/loop.go:86–131`. 
2. **Tool eligibility comes from the selected definition.** The dispatcher resolves calls against the current tool catalog and dispatches the handler declared on the resolved definition. Input transforms and guard checks precede approval and execution. Non-interactive children deny calls that would need a human. Each batch runs concurrently but waits for all results. Cancelling one call or receiving a stop verdict cancels siblings cooperatively. `pkg/runtime/toolexec/dispatcher.go:247–290,399–499,800–842`, `pkg/runtime/tool_dispatch.go:41–92`.
3. **Child state and target permissions are explicit.** Delegation lineage prevents reentering an active agent in the same chain. Child prompts start from a task contract, parent security settings are copied, and scoped child histories survive user-visible error finishes. Native background and worktree child identity is pinned, so foreground changes do not normally redirect those workers. `pkg/runtime/agent_delegation.go:70–85,226–313,393–447,574–589,696–730`, `pkg/runtime/agent_router.go:73–95`.
4. **A worker can outlive a request only through a defined owner.** The background handler accounts for admission and registers its goroutine under one lock, makes `done` represent drained completion and cancels before joining on shutdown. In external tool supervision, a single watcher owns Wait, startup may adopt a late connection, and Stop schedules reaping any late result. For worktree loading failures, disposal runs on an independent cleanup context and walks shared resource identity before closing. `pkg/tools/builtin/agent/agent.go:366–415,505–515,582–600`, `pkg/tools/lifecycle/supervisor.go:304–386,424–568`, `pkg/tools/disposal.go:58–141`.
5. **Persistence has separate ownership from execution.** The embedder owns the store lifecycle, the observer has per-run streaming state, and its synchronous ordering means consumers see events after the store write has been attempted. Sub-sessions publish through the parent completion event or direct background persistence. Snapshots use cloned state and file-backed plans use revision-guarded mutation. An event cursor and a durable transcript have different retention and semantics. `pkg/runtime/runtime.go:885–891,1293–1304`, `pkg/runtime/observer.go:91–138`, `pkg/runtime/persistence_observer.go:59–141`, `pkg/session/branch.go:35–77`, `pkg/tools/builtin/plan/plan.go:981–1049`.
6. **Recovery is specific to the layer.** Model fallback is an attempt-chain decision, tool supervisor reconnect is a transport decision, board recovery replaces a process while retaining conversation identity, and opening SQLite advances durable schema and history. A failed HTTP stream or a killed process can lose in-flight work. Tool operations and providers do not share a durable transaction or an exactly-once execution log. `pkg/runtime/fallback.go:218–265,297–430`, `pkg/tools/lifecycle/supervisor.go:656–742,762–854`, `pkg/board/controller.go:480–541`, `pkg/session/sqlitestore/sqlitestore.go:20–69`.

## 4. What it does well and poorly, with source evidence.

**Strengths.** The design separates provider dispatch identity from serving/catalog identity and carries the latter into usage accounting. Retry policy distinguishes cancellation, rate limits, retryable errors and permanent fallback, and can stick to a working fallback under a cooldown. A direct transfer child is allowed one immediate idle retry only before payload appears and after a budget admission check. Streaming cancellation gives each attempt its own context so a cooperative HTTP stream can unblock its reader. Context overflow has a separate bounded compaction path. This avoids restarting a whole conversation for a single transport error. `pkg/model/provider/contracts/contracts.go:29–73,137–170`, `pkg/runtime/fallback.go:183–265,315–430`, `pkg/runtime/streaming.go:76–132`, `pkg/runtime/loop_steps.go:135–221`.

Workspace graph reconstruction and explicit disposers make running a specialist in a separate checkout practical. Real local tests covered staged and untracked worktree diff handling, protected include targets, baseline branch identity, tmux death and recovery, and Unix socket delivery. The control plane also correctly separates replay registration and live fanout under one lock, evicts a slow listener without blocking publishers, and publishes an explicit terminal on source close. `pkg/team/workspace.go:14–103`, `pkg/tools/disposal.go:20–24,58–141`, `pkg/worktree/include.go:77–207,360–493`, `pkg/board/git.go:37–70`, `pkg/server/eventlog.go:76–130,139–183`.

### Findings with direct controls

| Impact | Finding and cause |
| --- | --- |
| High | **A child can consume user input addressed to its parent.** The default queues belong to `LocalRuntime`, with no input owner in `QueuedMessage`. A shared-runtime child uses the same steering drain and follow-up dequeue as the root. Holding the root at its provider call while a non-interactive pinned child ran sent the synthetic root input to the child on both paths. With the child absent, the root received it. Separate isolated-worktree runtimes have their own queues. `pkg/runtime/runtime.go:330–336,1462–1479`, `pkg/runtime/message_queue.go:10–17,77–107`, `pkg/runtime/continuation.go:51–82`, `pkg/runtime/loop.go:540–547,1048–1084`, `pkg/runtime/agent_delegation.go:491–514,711–730`. |
| High | **The API can omit accepted batch input from durable history.** `RunSession` appends all request messages to the live session, then updates only store metadata. The runtime emits a user message event for the tail of the submitted batch and the observer persists that event. With a real SQLite file, the model and live transcript saw all three fixture messages across two turns. Close/reopen kept the single-message control and the last item of the two-message batch. `pkg/server/session_manager.go:1141–1159,1230–1232,1559–1581`, `pkg/runtime/loop.go:352–375`, `pkg/runtime/persistence_observer.go:115–121`, `pkg/session/store.go:1168–1185`. |
| High | **Server-managed deletion cancels a turn without closing its runtime.** The server removes the store row and clears registries, callbacks and the tracked cancel function. `WaitStopped` joins the streaming lock. The route never calls the registered runtime's `Close`, which is where detached agent tasks are cancelled and joined. A recording runtime observed a cancelled context and successful `WaitStopped` with zero close calls. Attached runtime ownership explicitly belongs to the embedder. The concern here is the server-owned path. `pkg/server/session_manager.go:908–1022,1733–1746`, `pkg/runtime/runtime.go:1293–1304`, `pkg/tools/builtin/agent/agent.go:388–415,582–600`. |
| High | **Follow-up deduplication represents reservation, even if a batch partly succeeds or enqueue later fails.** The manager reserves a request key, enqueues each item separately and releases the key on error. At capacity one, two identical two-item requests returned HTTP 429 twice and delivered the first item twice. The single-item 202 retry control delivered once. A gated same-key retry also returned duplicate success while its first request was still pending, then the first returned an enqueue error. `pkg/server/session_manager.go:1348–1394`, `pkg/server/idempotency.go:32–67`, `pkg/server/server.go:771–803`. |
| High | **A failing legacy migration can be marked complete before the payload is safely copied.** The migration marker commits before its Go callback. Migration 15 loops over sessions, logging and skipping a per-session failure. Per-item inserts can leave a partial transcript, which the “no items yet” selection would skip on rerun. A later migration drops the legacy messages column. An injected failure on item two left one item after reopen for the affected session and two for the clean control. A separate failing `UpFunc` proved the marker prevented retry. `pkg/session/migrations.go:113–128,143–179,347–352,390–397,506–578,582–596`. |
| High | **Tool supervisor can publish a usable connection without a watcher.** Starting during an earlier watcher's terminal failure callback sees `watcherAlive=true`, installs the new session without its own watcher and returns Ready. The old watcher exits and clears the flag. In the controlled overlap, the replacement never entered Wait and its subsequent exit left state Ready. Starting after retirement yielded a watched replacement and state Failed on its exit. `pkg/tools/lifecycle/supervisor.go:304–386,656–669,704–735`. |
| High | **Parallel synchronous transfers can select another agent and leave the foreground selection changed.** Both calls see the original caller's allowed targets. Each then switches the same runtime-wide agent pointer and creates an unpinned child, which resolves that pointer at execution time. The defers also restore snapshots of the shared pointer. In 25 gated real-dispatch runs, the alpha task used beta every time. The beta task used root three times and the foreground pointer remained alpha eight times. Two sequential dispatches selected each intended agent and restored root in all 25 controls. The word “synchronous” describes each tool's wait for its child. The batch can run several such tools concurrently. `pkg/runtime/toolexec/dispatcher.go:247–290`, `pkg/runtime/agent_delegation.go:344–358,388–423,787–799`, `pkg/runtime/agent_router.go:73–95`. |
| High | **Board movement and prompt execution are separate commits.** The column commits first, then the controller sends an HTTP follow-up. A 503 from a real Unix HTTP fixture with a live pane report left the card in the new column on disk. A retry of the same move produced zero new deliveries. Reversing and advancing sent a fresh key. A prompt-bearing relaunch also trusts the earlier liveness sample even if a watcher has recovered the pane under the shared relaunch lock. `pkg/board/app.go:494–521`, `pkg/board/controller.go:463–528`, `pkg/board/client.go:128–155`. |
| High | **Board save failure can split in-memory and durable state.** Mutators change the stored struct or slice before calling `save`. For a deterministic pre-writer `ENOTDIR`, memory advanced to running, reopen showed waiting, and retrying that same status made no write. Watcher updates only notify on successful persistence and drop the save error. This same mutation shape exists for move, insert and delete. `pkg/board/store.go:64–82,114–139,145–213`, `pkg/board/controller.go:431–444`. |
| Medium | **A board reconnect can misclassify busy as waiting.** The server snapshot includes streaming state. The board decodes only title and sequence and derives activity from bounded replay. A 1,024-frame suffix lacking the start boundary retained waiting status, and real Unix HTTP with `streaming:true` showed the same startup-to-waiting behavior. The same retained window with a start boundary correctly became running. A lagged client also depends on heartbeats being seen before its idle watchdog starts. `pkg/server/session_manager.go:568–619`, `pkg/board/client.go:47–76,162–214`, `pkg/board/controller.go:274–394`. |
| Medium | **Backpressure can block native cancellation when an embedder abandons the stream.** The native sink and observer forwarder use blocking sends and observer output forwarding disregards context. A fake provider saturated both stages, held its Close after cancellation, and released once the test drained the output. The bounded stop event solves a narrower final-send case. Stock wrappers explicitly drain in relevant paths, so the failure is an SDK/adapter lifecycle risk. `pkg/runtime/event_sink.go:15–47`, `pkg/runtime/observer.go:108–138`, `pkg/runtime/loop.go:86–131`, `pkg/server/session_manager.go:1195–1216`. |
| Medium | **Plan listing is not a collection snapshot.** Get opens a named path and benefits from atomic file replacement. List enumerates the directory first and can miss an existing plan while it is replaced. The upstream concurrent listing test failed consistently on Btrfs and passed on tmpfs with the same Go binary and shim. A separate Python control using only directory enumeration, direct open and atomic rename reproduced omissions on Btrfs with zero missing opens. Version-guarded writers and point reads remain useful. `pkg/tools/builtin/plan/plan.go:945–978,981–1024,1052–1110`, `pkg/tools/builtin/plan/plan_test.go:702–781`. |
| Medium | **Budget admission is a point-in-time observation.** Two sibling fixture calls admitted at zero usage against a 10-token wallet spent 14 before the next root boundary denied a model call. This matches boundary-based accounting but the documentation's single in-flight turn wording understates parallel overshoot. A native shared-runtime background child already over budget returned its explanatory text as a successful result, while the worktree branch explicitly treats its scoped budget event as an error. Rebuilding the runtime resets the in-memory wallet by design. `docs/configuration/budget/index.md:83–99,183–191`, `pkg/runtime/budget.go:195–223,343–400,434–451`, `pkg/runtime/loop.go:478–491,549–553`, `pkg/runtime/agent_delegation.go:533–548,591–612`. |
| Medium | **Replacing an event source leaves the old pump running.** Lazy logs are explicitly adopted, but replacing a non-lazy source overwrites its only cancel reference. The replacement was cancelled by delete, while an old source still waiting on its context required explicit fixture release. This applies when an embedder registers the same session twice. `pkg/server/session_manager.go:238–275,329–341,944–992`. |

**Process-tree cleanup and narrower lifecycle caveats.** A background job stop succeeds after the direct child and I/O monitor finish. Escalation to SIGKILL is conditional on that join taking too long. A benign fixture with a same-group descendant that ignored TERM and closed the captured I/O survived a successful stop and a toolset stop in all five repetitions. The default-signal child exited in the five control runs. The documented intentional case of a command daemonizing and leaving its own output redirected explains the direct-child completion policy. An explicit stop has a stronger natural ownership contract, which the current implementation cannot demonstrate. Startup cancellation likewise depends on owner semantics. With a positive startup timeout the supervisor waits for the shared handshake or timer and omits caller cancellation from that select. A cancelled caller waited 100 ms of fake time and got the policy timeout. The zero-policy branch passed cancellation immediately to the cooperative connector. A caller-facing timeout and ownership of an adoptable handshake can be handled separately. `pkg/tools/builtin/backgroundjobs/backgroundjobs.go:43–55,299–342,453–477,666–688`, `pkg/tools/builtin/backgroundjobs/cmd_unix.go:10–25`, `pkg/tools/lifecycle/supervisor.go:140–148,424–474`.

**Global admission.** `RunSession` holds the manager-wide mutex across store lookup and cold team/runtime construction, including config resolution, external references and provider construction. A controlled cold store read held that mutex and blocked a different, already-initialized session from entering its provider. The warm-only and resumed controls both entered the provider. The lock keeps a half-initialized runtime from becoming visible, which is a useful invariant to preserve with per-session creation ownership. `pkg/server/session_manager.go:1041–1095,1645–1671`, `pkg/teamloader/teamloader.go:244–290,595–645`.

**Source-only capacity risks.** Managed runtimes are cached for the session's lifetime with no eviction evident in the manager. The manual plan store and replay log bound individual data units more reliably than they bound the number of active sessions or watchers. Background-agent output tracking is also a soft cap, checking the current size before writing a whole chunk and retaining the final result separately. Production throughput ceilings and resource exhaustion remain unmeasured. `pkg/server/session_manager.go:1066–1075,1733–1746`, `pkg/tools/builtin/agent/agent.go:34–40,169–178,491–498`, `pkg/board/controller.go:111–131`.

## 5. Core-code quality: decomposition, state, concurrency, errors, types, tests, observability, extensibility, and maintainability.

| Dimension | Evaluation |
| --- | --- |
| Decomposition | The split between team configuration, session objects, provider contracts, tool invocation and transports has practical benefits. I compiled the production loop without concrete providers and supplied a controllable fake through the supported contract. The loop still centralizes many independent policies, including context selection, compaction, steering, routing, retry, billing and hook lifecycle. Recent extracts such as `loopState`, `fallbackExecutor`, `agentRouter` and `toolexec.Dispatcher` make flow easier to follow. A smaller per-invocation owner would make session lifetime and resource ownership harder to mix up. `pkg/runtime/loop.go:592–620,665–736`, `pkg/runtime/fallback.go:42–68`, `pkg/runtime/agent_router.go:12–35`, `pkg/runtime/tool_dispatch.go:41–92`. |
| State and concurrency | Session accessors, per-run observers, per-session stream/mutation locks and scoped MCP elicitation IDs are good designs for asynchronous work. Global current-agent state, runtime input queues, partially ordered bridge detach and unscoped approval slots are harder to reason about. The bridge explicitly documents its remaining best-effort role for overlapping streams. Tool batches spawn one goroutine per call with no independent concurrency limiter in the mapper. `pkg/runtime/agent_router.go:20–25,73–95`, `pkg/runtime/elicitation.go:52–76,105–157`, `pkg/runtime/runtime.go:253–273,330–336`, `pkg/concurrent/mapslice.go:12–21`. |
| Reliability and errors | Many expected failures have sentinels and clear ownership boundaries, including session busy, quota or iteration stops, store origin, tool lifecycle and worktree creation. SQLite open distinguishes newer schema, transient lock/cancel and file-open failure from recovery-worthy cases, retaining a backup in the latter case. Failures that only log, such as per-event persistence and board cleanup errors, weaken the caller's ability to verify that state was actually committed or released. `pkg/session/sqlitestore/sqlitestore.go:24–69,92–123`, `pkg/runtime/persistence_observer.go:123–198`, `pkg/board/git.go:15–24`, `pkg/board/controller.go:431–444,551–555`. |
| Types and extensions | `Provider`, `MessageStream`, `ToolSet`, `ToolHandler`, `MessageQueue`, `Store`, `EventObserver`, `Harness.Provider` and lifecycle connectors expose useful seams. Registry-based tool and model assembly enables tailored hosts and dependency-light tests. Events have typed structs and an explicit registry, and the app/remote boundaries keep compatibility layers. Extension correctness still relies on custom tools honoring context, closing process trees, and maintaining idempotent cleanup. Tests can express many of these obligations directly at the interface. `pkg/model/provider/contracts/contracts.go:137–204`, `pkg/model/provider/factory.go:19–40,229–252`, `pkg/tools/tools.go:16–65,168–205`, `pkg/runtime/message_queue.go:31–50`, `pkg/harness/harness.go:54–77`, `pkg/tools/lifecycle/supervisor.go:39–56`. |
| Observability | The runtime emits conversation, tool, provider/fallback and budget context in typed events and OTel. Detached agent traces link to the initiating span, and route choices and tool usage can persist separately from display text. Observers execute synchronously, so they are also on the producer's critical path. The session transcript writes interim content on each delta, and the replay buffer does a slice copy at capacity. Both are performance interests for long streams. A bounded replay window counts events, while payload byte totals depend on event sizes. `pkg/runtime/loop.go:189–236`, `pkg/tools/builtin/agent/agent.go:394–455`, `pkg/runtime/persistence_observer.go:96–113,203–241`, `pkg/server/eventlog.go:92–110`, `pkg/runtime/observer.go:108–138`. |
| Tests and maintainability | The pinned tree contains 1,631 Go test files, including focused regression suites for turn draining, cancellation, fallback, workspace rebuilding, store races and remote/event contracts. `testing/synctest`, local fixtures and injected factories complement package-level coverage. Some native tests import the full provider/tool default graph even when the production core does not, which weakens offline portability. The production module and extensive provider integrations make a dependency-complete offline release bundle valuable. `Taskfile.yml:141–163`, `pkg/tools/lifecycle/supervisor_test.go:32–90,210–278`, `pkg/server/session_manager_drain_test.go`, `pkg/runtime/stream_stopped_delivery_test.go`, `pkg/runtime/budget_wiring_test.go`. |

## 6. Executed tests/experiments and their limitations.

Results are fresh `go test -count=1` runs unless repetition is specified. A test count is the number of Go JSON `pass` records with a `Test` field, including passing subtests. Package counts exclude `[no test files]`. Repeated findings below are passing assertions of observed behavior, which can itself be undesirable. The three lanes use different evidence strength.

| Lane | Command and result | Qualification |
| --- | --- | --- |
| Original manifest | `GOTOOLCHAIN=local go test -mod=readonly -p=3 -count=1 ./...` exited 1 at the toolchain floor. Isolated `GOTOOLCHAIN=auto` with a file-only cache proxy also exited 1, unable to supply Go 1.27.4. | Exact locked build/test unavailable with the pre-existing offline toolchain set. |
| Broad package inventory | `GOFLAGS='-mod=readonly -modfile=/s/compat.mod' go test -p=3 -parallel=3 -count=1 -timeout=3m -json ./...` on 1.27.3 with only the Go floor adjusted. **47 packages passed, 3,187 test records passed, 30 packages had no tests, 247 packages failed setup.** All 247 failing packages reported `FailedBuild`. There were no test assertion failures after correction. The setup output named 58 different missing zip paths. | Original Go source and dependency versions for this lane. Many central packages depend on missing modules. |
| Broad race control | Selected all 47 passing packages and ran `go test -race -shuffle=593718 -p=2 -parallel=3 -count=1 -timeout=2m -json` with the same compatibility manifest. **47 packages and 3,187 test records passed.** | Change in scheduling and instrumentation. Same compilation boundary. |
| Standard-library component tests | `go test -race -count=3 -v` with named files in `pkg/server` for the event log and idempotency cache, and named files in `pkg/board` for the Unix HTTP client and flock. Both commands passed. | Same Go floor adjustment, no dependency substitutions for the named files. Full server composition and board storage are outside this lane. |
| Git and workspace controls | `go test -p=2 -parallel=3 -count=1 -json ./pkg/fsx ./pkg/worktree/...` with cached Git filesystem and x/sys/x/net replacements. **159 pass records across two packages**, one test skipped and one package with no tests. | Used real Git fixtures, local refs and temporary worktrees. Cache replacements affect filesystem utility dependencies. |
| Board production package with contained writer | `go test -race -p=3 -parallel=3 -count=3 ./pkg/board ./pkg/runregistry ./pkg/userconfig ./pkg/atomicfile` passed **735 records** across four packages. | Missing `natefinch/atomic` replaced by local temp-file + Sync + Rename. The wrapper's chmod and all four packages' production sources were intact. |
| Native store, plans and workers | On tmpfs, the reduced offline profile passed `pkg/session` (579 records, two unsupported integration files excluded), `session/sqlitestore` (8), `sqliteutil` (7), `tools/builtin/plan` (126), `plans` (49), `tools/builtin/agent` (73), `tools/builtin/backgroundjobs` (35), `chat` (178), `team` (19), `runtime/eventmerge` (21), `agent` (53), `hooks` (575), `tools/builtin/shell` (78), `runtime/compactor` (52), and `runtime/modelcatalog` (97), all with the race detector. A run using the reconstructed appendix config matched these counts. | Uses cached alternate versions and the limited shims in section 9. Actual SQLite, Git, subprocesses, package APIs and output remain under test. |
| Native runtime and tool dispatch | The selective native suites passed under `-race`, with **1,712 passing runtime records and 215 passing tool execution records**. | Provider/harness integration test files with missing SDKs omitted. Setup was restored for JS and per-process test config. |
| MCP transport | **370 passing race records** after isolating the two discover/subscription fixtures. An earlier targeted stdio, SSE, elicitation, supervisor and refresh run passed 18 records. A one-variable capability control passed the omitted test group, including cancellation and failed stream cleanup, for six pass records. Five serial race repetitions of that control passed 30/30 records. | Uses pre-existing SDK 1.8.0. The pinned SDK replacement was absent. See section 7 for the unchanged fixture outcome and capability control. |
| Streaming persistence benchmark | Three runs of 50 iterations gave **101–110 µs and about 416 KB per iteration** in memory, and **3.19–3.25 ms and about 1.64 MB** using in-memory SQLite, with 500 deltas each. The latter allocated about 9,542 objects per iteration versus 1,527. | Smoke measurements on one machine with the selective test profile. The in-memory benchmark creates and deletes a session per iteration, while the SQLite benchmark reuses its session. These timings show the scale of the event path under each workload. They provide no disk latency, durability, or service capacity estimate. `pkg/runtime/persistence_observer_bench_test.go:19–21,219–272`. |

Focused isolated controls used ordinary product call paths or package-private seams that preserve the mechanism under study.

| Control | Result |
| --- | --- |
| Native ownership, 10 repetitions under `-race` | With the root blocked immediately inside its fake provider, both steering and follow-up intended for root went to a shared-runtime background child. The root-only control saw input. The unrelated task and providers were inert local fixtures. |
| Parallel transfer, 25 paired repetitions under `-race` | The production dispatcher started two real transfer handlers. One test event sink gated agent-switch order. Alpha used beta 25/25, beta used root 3/25, and the shared current agent ended at alpha 8/25. Serial controls used both intended agents and restored root 25/25. |
| Runtime budget and cancellation, 10 repetitions under `-race` | Token counts 7+7 against cap 10 after simultaneous admissions at zero. The next root attempt emitted one budget stop without a provider request. A reconstructed runtime started with an empty budget, and a same-runtime background result reported budget-stop text in its success payload. The undrained 128-event public channel held the provider open at cancellation after 254 received frames. Draining 259–260 events allowed cleanup, with minor variation in final events. |
| HTTP and SQLite, three repetitions under `-race` | Real loopback HTTP route returned 429 on a partially committed batch and 202 for the successful single-message control and its duplicate. A gated cache test observed the premature acknowledgement. The actual manager's RunSession, real SqliteStore, fake provider and reopen established batch input loss. The delete and replacement controls measured the missing Close invocation and unreaped original event pump. |
| Cross-session admission, 10 paired repetitions under `-race` | A cold store wrapper blocked one read and returned a sentinel on release. A different, already-initialized runtime did not enter its provider during that barrier and did enter after release. The same warm runtime entered in the uncontended control. |
| SQLite migrations, five repetitions under `-race` | Custom `UpFunc` failure left the marker with no payload and no retry. Real built-in migrations skipped the second item of an otherwise valid legacy record on a local SQL fault and later dropped the old messages column. The healthy record migrated both items. |
| Board controls, five repetitions under `-race` | Tested save fault before writer, durable column vs 503, duplicate move, truncated activity replay, stale pane liveness and a real Unix HTTP response with streaming state. Fixture title/status events and media were small. |
| Board real OS lifecycle | Four fresh runs with real tmux, local Git and Unix sockets carried a tiny self-exec fake agent. The first pane's process started in the original repo and made a real worktree. SIGKILL forced recovery with the same session ID and checkout and a different PID. Follow-up reached the new fixture. Deletion removed the tmux session, worktree, branch and socket. |
| Tool supervisor, 20 paired repetitions under `-race` | A failure-callback barrier reproduced a replacement with no watcher. A post-retirement start was watched. A separate test showed startup policy wait vs immediate caller cancellation with no policy timeout. |
| Background job process ownership, five paired repetitions under `-race` | Real process group and signal tests distinguished direct-child exit, zombie state and a surviving same-group descendant. Normal fixture descendants died. TERM-ignoring descendants with closed output remained live after both job and toolset Stop, then the test cleaned them up. |
| Plan concurrency and filesystem | Original test failed 30/30 twice on Btrfs and passed 30/30 on tmpfs. A separate Python experiment used two readers with 15,000 enumerations each. Btrfs omitted the existing plan 2,983/30,000 times with same-directory replacement and 2,841/30,000 times with a sibling-directory temp. Direct reads had zero missing or malformed values. Static Btrfs and all tmpfs variants had zero omissions. These are local observations, not general failure rates. |

The CLI binary, default registry, production providers, cloud sandboxes, external coding harnesses, OCI pulls, Desktop credentials, and non-Linux resource semantics were not exercised end to end. No Docker daemon or credentialed model request was needed. The provider shims used deterministic data. The portable tool supervisors and actual Unix subprocesses were exercised, but Windows job objects and access-control semantics were assessed from source only. The compatibility lanes cannot validate the missing modules' implementation or API behavior.

## 7. Measurement audit for every negative or surprising result, including alternate commands or code-path checks used to rule out setup mistakes.

| Result | Root-cause checks and scope |
| --- | --- |
| Native manifest failure and missing dependencies | Checked the host's 1.27.1 and the pre-existing cache's 1.27.3 under `GOTOOLCHAIN=local`. The pinned file requires 1.27.4 at `go.mod:3`. The local proxy auto-selection failed before the accidental external version probe. Parsed the preshipped module declarations, checked cache artifacts and read Go's `FailedBuild` and attempted file-proxy paths. The floor-only rerun built independent packages. Missing ZIP/module errors were recorded as dependency setup, separate from product assertions. The module graph has 232 declared entries in the two require blocks. The literal lookup found 113 absent before applying replace directives. Go's actual attempted paths gave the smaller 58-path missing set for that run. |
| First broad run's `TestPackageDoesNotDependOnEcho` failure | The child command uses `exec.CommandContext(..., "go", "list", "-deps", "-test", ".")` at `pkg/httpsec/httpsec_test.go:99–106`. CLI-only `-modfile` flags on the parent test command were invisible to the child, which reached the original Go floor. Inherited `GOFLAGS` fixed its subprocess and the corrected full run. The package passed again under the race detector. |
| Targeted build retries | The first worktree retry still lacked the repo's replacement pin for securejoin and x/net. Cached securejoin and x/net variants got the real tests through. The first fixed session manifest still inherited Docker Desktop secrets modules, Docker CLI, and x/oauth2 through `session → agent → provider → environment → HTTP/Desktop`. The disabled Desktop engine comes from the repository's own unsupported-platform implementation. Running `go list -deps -test -e -json` then distinguished provider/udiff test imports from production core imports. The minimal source build succeeded for runtime, session, SQLite, jobs, plans, teamloader and the server with its unused cold composition registry replaced. The larger tests for provider defaults, teamloader defaults, embeddedchat and root tool suites hit absent provider/HCL/harness/Tree-sitter packages. An ACP-specific retry at the same compatibility level also stopped at missing local ZIPs, independently including `acp-go-sdk@v0.13.5`, even after removing the default loader entry point from the test graph. |
| Selective native suite errors | Dropping an integration test can also drop package setup. The omitted harness test contained the JS evaluator registration and temp config root in `pkg/runtime/harness_test.go:39–46,63–78`. Thirteen command tests initially saw literal templates and prompt-file guard tests saw a missing config directory. Recreated those two setup actions and copied the SQLite/evaluator test helpers without harness/provider imports. Restored dispatcher test helpers while removing the dependent redaction case. Removed an unused test-only import. Initial focused probe compile errors involved a pointer-valued context-window field, the named budget option, and a pointer receiver on a board helper. Corrected each temporary fixture and reran the affected package before counting evidence. |
| MCP setup timeout on the alternate SDK | Cached 1.7.0 had an unexported `protocolVersion`. With 1.8.0 the full suite compiled, with 373 pass records before the timeout. The subscription subtest failed to enter the request in five serial repeats. Its headers, endpoint and legacy initialize siblings passed each time. A second test was blocked receiving the same absent subscription at `pkg/tools/mcp/session_remote_test.go:397`. Alternate SDK `mcp/client.go:337–358` opens a discovery-driven subscription only for an advertised list-change capability and enrolled handler. The unchanged replies use `"tools":{}` at `pkg/tools/mcp/session_remote_test.go:115,369`. Overlaying an otherwise identical reply with `"tools":{"listChanged":true}` let both targeted native tests finish and pass under race. This isolates the measured failure to fixture negotiation with the alternate SDK. The pinned SDK behavior remains unverified. |
| Board startup/phase and write faults | Tested regular persisted cards with a writable parent as a control. For the fault, moved the parent aside and placed a regular file at that pathname, producing deterministic `ENOTDIR` from `MkdirAll` before the local writer shim. Restored the original dir before retry and compared memory with a newly opened store. Replayed the same 1,024-frame window with and without start, and tested actual Unix socket exchange. A ready HTTP socket plus the same message server checked transport separately from board state synthesis. The stale-liveness subtest scripted a state change just after the liveness read. It establishes the relaunch dispatch behavior, while the unmodified tmux test covers a genuine dead process and observed recovery. |
| Follow-up, transcript and teardown | Plain valid synthetic messages and one local receiver eliminated repair, schema and provider variables. Compared successful single-item request retry to a partially committed two-item request, then gated the duplicate while the original remained pending. For transcript durability, verified exactly what reached the provider and compared the still-live session with a freshly reopened SQLite DB after terminal drain and Close. Both a single-input positive control and the last member persisted on the same filesystem. Explicitly seeded the fake runtime as server-owned for delete and recorded its Close count. A registry replacement control used two cancellable producers and measured which context ended, with explicit old-pump release at teardown. |
| Cold admission lock | The initial test used `synctest.Wait` on a goroutine blocked on `sync.Mutex`, which cannot satisfy the bubble's durable-block condition. The corrected control directly checks the manager mutex with `TryLock` during the channel-gated store call. A 10 ms observation window pairs with the lock oracle and both a warm-only and resumed provider entry. The mutex establishes causality. The window is a scheduling check and the test makes no latency claim. |
| Child queue and agent routing | A root-only control on the same runtime received the message. A provider barrier ensured root was active and could not win the queue race. Both child transcript inputs and queue depth were observed. The transfer control used the real dispatcher and verified the task text each model implementation received, independently of status events. The gating sink coordinated the shared-state interleaving and serial calls confirmed correct fixtures. The remaining restore outcome varied with finish order, consistent with shared atomics guarding individual writes but not the lifetime of a switch. |
| Budget, backpressure and timing | The two dispatch callbacks were parked before either had produced usage and explicit fake counts were received from each. A root attempted afterward made zero provider calls. A known priced model was unnecessary because the oracle was token count. The fake ID's unpriced warning was expected. An early direct child test omitted a persisted parent row and produced a store warning. Registering the parent before dispatch removed that warning without changing the result. The native stream backpressure probe used a finite fake producer, explicit full-buffer check and a positive drain branch. Logical times from `testing/synctest` are test clocks. They do not count as elapsed investigation time. |
| Migration 15 and legacy column observation | Used the original migration list and first initialized only IDs 1–14. An SQL trigger failed only position one of an otherwise valid synthetic legacy row. An early post-migration check incorrectly expected the source JSON after all migrations. Inspection located the explicit ID 20 drop. The corrected test observes source JSON midway, removes the trigger, closes and reopens using the full migration list, and verifies the truncated transcript and absent legacy column. The second record in the same DB proves normal migration. A separate custom callback probe confirms the marker ordering without relying on the per-row skip path. |
| Supervisor and OS child lifetime | The fake connector uses the stock test session with distinct readiness, Wait and Close channels. Channel barriers remove scheduler timing from the missing-watcher result. Starting after retirement restores normal Wait and terminal state. The real shell fixture verified the descendant was a running `sleep` in the same process group before stop. The `/proc` oracle excluded zombies instead of using existence alone. The default TERM control and explicitly joined shell remove “the stop signal never reached the group” and “main command had not exited” as explanations. The SIGKILL cleanup was limited to the isolated fixture. |
| Plan list under concurrent rename | Same binary, shim, test and command ran against Btrfs-bound and mount-namespace tmpfs `/tmp`. Both had enough space and permissions. A language-independent control wrote candidates and called `os.replace` without the shim, including with temp files in a sibling directory. Direct path open succeeded in every sample, while enumeration on Btrfs sometimes returned an empty list. The Btrfs outcome is a collection enumeration consistency flaw under atomic rename. The data support neither torn point reads nor corruption. |
| Environment and limits | The restricted namespace confirmed only loopback and no routes. Host Git 2.56.0 and tmux 3.8 were exercised with disposable fixtures. Git-dependent controls initialize their own local repos because the archive omits Git metadata. The one worktree skip was `TestWorktreeIncludeUppercaseActiveAgentsIgnore`, which explicitly skips on case-sensitive filesystems at `pkg/worktree/include_test.go:124–135`. The standalone `unshare -n` probe failed for an unprivileged user, while user and network namespaces together worked through Bubblewrap. No negative result used a real provider, account, host credential, or a Docker daemon. Fake time and barriers establish ordering and lifetime for the controlled paths. |

## 8. Post-mortem: design pressures, accumulated tradeoffs, likely failure modes, and the highest-leverage improvements.

The core's history is visible in overlapping lifetimes. The original synchronous conversation and in-process approval model remains a good fit for a single human-driven stream. Adding concurrent child sessions, callbacks, tool recovery and attached transports required preserving old APIs and moving state into narrower owners. Pinned background agents, explicit stream drains, workspace disposers and generation-aware ACP turnover show that migration in progress. Parallel synchronous transfers and shared input queues still use state owned by the original runtime. A clean race-detector run is compatible with their failures because individual operations are synchronized. The entire logical transition needs its own owner.

Three different success signals recur: a request has been accepted, a run has emitted its outcome, and its state and resources are durable or fully released. The existing `done` distinction in background agents, the observer barrier and the ACP cleanup join are useful precedents. The follow-up API, board transition, server deletion and legacy migration all expose earlier signals as if they completed the later boundary. Failure recovery needs an operation ID, explicit phase, and an owner who can reconcile an interrupted transition. A process-local receipt can improve retries within a runtime. Anything promising recovery across restart needs durable state for that receipt and a documented replay policy.

Recovery is strongest around independently testable local units: a provider attempt, an MCP session, a SQLite item, a Git worktree, a JSON file. The most likely field faults are partial cross-unit transitions, such as an HTTP acknowledgement lost after enqueue, tmux recovering between a health check and restart, a replaced provider without a watcher, or a transcript prefix that exists only in memory. Capping one output or retry counter does not cap the number of simultaneously active owners. The next architecture step is to carry session, task and generation identity across the full submit, execute, observe and teardown path, and reserve scarce resources at admission.

The project already supports incremental improvement. Provider, store, event, tool and connector seams allowed the highest-severity findings to be demonstrated without real provider calls. A supported smaller test graph and cached dependency bundle would keep that benefit available in isolated environments. Separation between production core and composition should extend to native test setup. A version and schema migration test should exercise the actual supported old database fixtures through fault injection and reopen.

## 9. Evidence appendix with local file/line references and commands.

All source references are relative to `repos/docker__docker-agent` at the reviewed commit. The primary ownership boundaries can be followed directly.

- Turn ownership, user input and child identity. [Runtime loop](repos/docker__docker-agent/pkg/runtime/loop.go:145), [delegation](repos/docker__docker-agent/pkg/runtime/agent_delegation.go:226), [runtime input queue](repos/docker__docker-agent/pkg/runtime/message_queue.go:10), [parallel dispatcher](repos/docker__docker-agent/pkg/runtime/toolexec/dispatcher.go:247).
- Durability, admission and transport retirement. [Session manager run](repos/docker__docker-agent/pkg/server/session_manager.go:1041), [batch submission](repos/docker__docker-agent/pkg/server/session_manager.go:1348), [persistence observer](repos/docker__docker-agent/pkg/runtime/persistence_observer.go:115), [migration sequence](repos/docker__docker-agent/pkg/session/migrations.go:392), [ACP close](repos/docker__docker-agent/pkg/acp/agent.go:113).
- Worker recovery and cleanup. [Board watcher](repos/docker__docker-agent/pkg/board/controller.go:463), [job stop](repos/docker__docker-agent/pkg/tools/builtin/backgroundjobs/backgroundjobs.go:453), [MCP supervisor](repos/docker__docker-agent/pkg/tools/lifecycle/supervisor.go:424).

### Reproduction commands

Run from the evaluation workspace. The inference and subprocess fixtures below use no live provider. For this cache snapshot, use the pre-existing Go 1.27.3 and download cache paths in the included `offline` wrapper. Save the named listings under the same temporary directory as that wrapper. Invoke the wrapper only after creating the directories.

```sh
repo="$PWD/repos/docker__docker-agent"
sha=00578ca8a20d6e3d02d2cca92dd2c80ab0e979b7
date -u +%FT%TZ
git -C "$repo" rev-parse HEAD
git -C "$repo" status --porcelain=v1 --untracked-files=all -z | wc -c
scratch=$(mktemp -d "$PWD/.docker-agent-review.XXXXXXXX")
mkdir -p "$scratch"/{source,logs,home,tmp,gopath,config,state}
git -C "$repo" archive "$sha" | tar -x -C "$scratch/source"
sed 's/^go 1\.27\.4$/go 1.27.3/' "$scratch/source/go.mod" > "$scratch/compat.mod"
cp "$scratch/source/go.sum" "$scratch/compat.sum"
chmod +x "$scratch/offline"
sed 's@--bind "\$scratch/tmp" /tmp@--tmpfs /tmp@' "$scratch/offline" > "$scratch/offline-tmpfs"
chmod +x "$scratch/offline-tmpfs"
"$scratch/offline" go version
"$scratch/offline" go test -mod=readonly -p=3 -count=1 ./...
"$scratch/offline" bash -c '
  export GOFLAGS="-mod=readonly -modfile=/s/compat.mod"
  go test -p=3 -parallel=3 -count=1 -timeout=3m -json ./... > /s/logs/broad.jsonl
'
"$scratch/offline" bash -c '
  export GOFLAGS="-mod=readonly -modfile=/s/compat.mod"
  mapfile -t passing < <(python3 -c '\''
import json, sys
for line in open(sys.argv[1]):
    row = json.loads(line)
    if row["Action"] == "pass" and "Test" not in row:
        print(row["Package"])
'\'' /s/logs/broad.jsonl)
  go test -race -shuffle=593718 -p=2 -parallel=3 -count=1 -timeout=2m -json "${passing[@]}" > /s/logs/race.jsonl
'
"${scratch}/offline" bash -c '
  export GOFLAGS="-mod=readonly -modfile=/s/compat.mod"
  go test -race -count=3 -v pkg/server/eventlog{,_test}.go pkg/server/idempotency{,_test}.go
  go test -race -count=3 -v pkg/board/client{,_test}.go pkg/board/lock_unix{,_test}.go
'
```

The broad command is expected to return nonzero on this module cache, while producing test counts for compilable packages. In Go JSON, count distinct completed package records, then test records with `Action=pass` and a `Test` field. The setup failures have `FailedBuild`; missing archives appear in build-output records as `file:///proxy/...zip`. No downloaded toolchain is required for the compatible lanes. The offline wrapper mounts the existing proxy read-only.

### Compatibility profiles and focused runs

See the listings for the modfile generator, overlay builder and fixture source. The focused overlays replace only unavailable composition seams and test files. Runtime and server focused fixtures use synthetic providers and the same native runtime package methods as the API. The supervisor fixture reuses the upstream package's fake session. Keep the shim scope as recorded in section 6. In a dependency-complete workspace, prefer the original manifest and the focused test-only overlays on the pinned Go release. Restricting the test build is still useful when measuring the fixtures on their own.

```sh
python3 "$scratch/make-review-config.py" "$scratch"
"$scratch/offline" bash -c '
  export GOFLAGS="-mod=readonly -modfile=/s/compat.mod"
  go test -race -overlay=/s/lifecycle-review-overlay.json -run "^TestReview" -count=20 -timeout=45s -v ./pkg/tools/lifecycle
'
"$scratch/offline" bash -c '
  export GOFLAGS="-mod=readonly -modfile=/s/board.mod"
  go test -race -p=3 -parallel=3 -count=3 ./pkg/board ./pkg/runregistry ./pkg/userconfig ./pkg/atomicfile
  go test -race -overlay=/s/board-review-overlay.json -run "^TestReview" -count=5 -timeout=45s -v ./pkg/board
  for repetition in 1 2 3; do
    go test -overlay=/s/tmux-review-overlay.json -run "^TestReviewTmuxGitUnixSocketLifecycle$" -count=1 -timeout=45s -v ./pkg/board
  done
'
"$scratch/offline" bash -c '
  export GOFLAGS="-mod=readonly -modfile=/s/worktree.mod"
  go test -p=2 -parallel=3 -count=1 -json ./pkg/fsx ./pkg/worktree/...
'
"$scratch/offline" bash -c '
  export GOFLAGS="-mod=readonly -modfile=/s/selective.mod"
  go test -race -overlay=/s/runtime-review-overlay.json -run "^TestReview" -count=10 -timeout=45s -v ./pkg/runtime
  go test -race -overlay=/s/runtime-review-overlay.json -run "^TestReviewParallelSiblingTransfersSwitchSharedAgent$" -count=25 -timeout=45s -v ./pkg/runtime
  go test -race -overlay=/s/core-selective-overlay2.json -p=2 -parallel=3 -count=1 -timeout=100s -json ./pkg/runtime ./pkg/runtime/toolexec
  go test -overlay=/s/core-selective-overlay2.json -run "^$" -bench "^BenchmarkPersistenceObserver_StreamingChunks" -benchtime=50x -count=3 -benchmem ./pkg/runtime
'
"$scratch/offline" bash -c '
  export GOFLAGS="-mod=readonly -modfile=/s/server.mod"
  go test -race -overlay=/s/server-review-overlay.json -run "^TestReview(FollowUp|ServerOwned|Replacing|Batch)" -count=3 -timeout=45s -v ./pkg/server
  go test -race -overlay=/s/server-review-overlay.json -run "^TestReviewColdStoreReadBlocksIndependentWarmRun$" -count=10 -timeout=25s -v ./pkg/server
'
"$scratch/offline" bash -c '
  export GOFLAGS="-mod=readonly -modfile=/s/core.mod"
  go test -race -overlay=/s/session-review-overlay.json -run "^TestReview" -count=5 -timeout=45s -v ./pkg/session
  go test -race -overlay=/s/jobs-review-overlay.json -run "^TestReview" -count=5 -timeout=45s -v ./pkg/tools/builtin/backgroundjobs
'
"$scratch/offline-tmpfs" bash -c '
  export GOFLAGS="-mod=readonly -modfile=/s/selective.mod"
  go test -race -p=2 -parallel=3 -overlay=/s/core-selective-overlay2.json -count=1 -timeout=100s -json \
    ./pkg/session ./pkg/session/sqlitestore ./pkg/sqliteutil ./pkg/tools/builtin/plan ./pkg/plans \
    ./pkg/tools/builtin/agent ./pkg/tools/builtin/backgroundjobs ./pkg/chat ./pkg/team \
    ./pkg/runtime/eventmerge ./pkg/agent ./pkg/hooks ./pkg/tools/builtin/shell \
    ./pkg/runtime/compactor ./pkg/runtime/modelcatalog
'
for wrapper in offline offline-tmpfs; do
  "$scratch/$wrapper" bash -c '
    export GOFLAGS="-mod=readonly -modfile=/s/core.mod"
    go test -race -overlay=/s/desktop-no-engine.json -run "^TestFilesystemStorage_LockFreeReadsUnderConcurrentWrites$" -count=30 -timeout=90s -v ./pkg/tools/builtin/plan
    python3 /s/readdir-control.py
  '
done
"$scratch/offline" bash -c '
  export GOFLAGS="-mod=readonly -modfile=/s/mcp.mod"
  go test -race -overlay=/s/desktop-no-engine.json -shuffle=593718 -skip "^TestSessionRemote(CancelsSetup|FailedSubscriptionCleanup)$" -count=1 -timeout=65s -json ./pkg/tools/mcp
  go test -race -overlay=/s/mcp-capability-overlay.json -run "^TestSessionRemote(CancelsSetup|FailedSubscriptionCleanup)$" -count=1 -timeout=20s -json ./pkg/tools/mcp
'
```

### Offline test wrapper and fixture listings

Save each listing as named beneath the temporary directory. These are the local review fixtures and small build substitutes. They were supplied through overlays and do not become part of the project. The response fixtures carry synthetic application data. The redaction and power-management substitutes exist solely to compile unrelated paths.

<details>
<summary>offline</summary>

```sh
#!/usr/bin/bash
set -euo pipefail
scratch=$(cd -- "$(dirname -- "$0")" && pwd)
hostcache=$HOME/go/pkg/mod
exec bwrap --unshare-all --die-with-parent --new-session \
  --ro-bind /usr /usr --symlink usr/lib /lib --symlink usr/lib /lib64 --symlink usr/bin /bin \
  --dev /dev --proc /proc --ro-bind /etc/passwd /etc/passwd --ro-bind /etc/group /etc/group \
  --bind "$scratch" /s --bind "$scratch/tmp" /tmp \
  --ro-bind "$hostcache/cache/download" /proxy \
  --ro-bind "$hostcache/golang.org/toolchain@v0.0.1-go1.27.3.linux-amd64" /go \
  --clearenv --setenv PATH /go/bin:/usr/bin --setenv HOME /s/home --setenv TMPDIR /tmp \
  --setenv XDG_CONFIG_HOME /s/config --setenv XDG_DATA_HOME /s/state \
  --setenv GOPATH /s/gopath --setenv GOMODCACHE /s/modcache --setenv GOCACHE /s/gocache \
  --setenv GOPROXY file:///proxy --setenv GOSUMDB off --setenv GOENV off \
  --setenv GOTOOLCHAIN local --setenv GOMAXPROCS 4 --setenv GOWORK off \
  --setenv GIT_CONFIG_NOSYSTEM 1 --setenv GIT_TERMINAL_PROMPT 0 \
  --setenv AWS_EC2_METADATA_DISABLED true --setenv LC_ALL C.UTF-8 \
  --chdir /s/source /usr/bin/bash -c 'test -z "$(ip route)" && test "$(ls /sys/class/net 2>/dev/null | head -1)" = "" || exit 91; exec "$@"' bash "$@"
```

</details>

<details>
<summary>make-review-config.py</summary>

```python
import json
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1]).resolve()
src = root / "source"
assert src.is_dir()
baseline = (root / "compat.mod").read_text()
sum_data = (src / "go.sum").read_bytes() + (root / "offline-extra.sum").read_bytes()

def additions(text):
    return [line.strip() for line in text.splitlines() if line.strip()]

worktree = additions("""
github.com/cyphar/filepath-securejoin => github.com/cyphar/filepath-securejoin v0.7.0
golang.org/x/sys => golang.org/x/sys v0.49.0
github.com/go-git/go-git/v5 => github.com/go-git/go-git/v5 v5.19.2
github.com/go-git/go-billy/v5 => github.com/go-git/go-billy/v5 v5.9.1
golang.org/x/net => golang.org/x/net v0.62.0
""")
core = worktree + additions("""
github.com/modelcontextprotocol/go-sdk => github.com/modelcontextprotocol/go-sdk v1.7.0
github.com/natefinch/atomic => /s/shims/atomic
github.com/docker/aijson => /s/shims/aijson
golang.org/x/image => golang.org/x/image v0.46.0
modernc.org/sqlite => modernc.org/sqlite v1.54.0
modernc.org/libc => modernc.org/libc v1.74.3
modernc.org/memory => modernc.org/memory v1.11.0
github.com/ncruces/go-strftime => github.com/ncruces/go-strftime v1.0.0
golang.org/x/sync => golang.org/x/sync v0.24.0
golang.org/x/text => golang.org/x/text v0.43.0
github.com/docker/cli => github.com/docker/cli v29.9.3+incompatible
golang.org/x/oauth2 => golang.org/x/oauth2 v0.37.0
github.com/docker/portcullis => /s/shims/portcullis
github.com/rumpl/keepawake => /s/shims/keepawake
""")
selective = core + additions("""
github.com/dop251/goja => github.com/dop251/goja v0.0.0-20260723142020-b4aef50fa347
github.com/dlclark/regexp2/v2 => github.com/dlclark/regexp2/v2 v2.8.2
github.com/google/pprof => github.com/google/pprof v0.0.0-20260402051712-545e8a4df936
""")
server = selective + additions("""
github.com/labstack/echo/v4 => github.com/labstack/echo/v4 v4.13.4
github.com/labstack/gommon => github.com/labstack/gommon v0.4.2
golang.org/x/crypto => golang.org/x/crypto v0.58.0
""")
mcp = selective + additions("""
github.com/modelcontextprotocol/go-sdk => github.com/modelcontextprotocol/go-sdk v1.8.0
""")
board = ["github.com/natefinch/atomic => /s/shims/atomic"]

for name, changes in (("worktree", worktree), ("core", core), ("selective", selective),
                      ("server", server), ("mcp", mcp), ("board", board)):
    replacements = {line.split(" => ", 1)[0]: "replace " + line for line in changes}
    lines = [
        line for line in baseline.splitlines()
        if not line.startswith("replace ") or line[8:].split(" => ", 1)[0] not in replacements
    ]
    (root / (name + ".mod")).write_text("\n".join(lines) + "\n\n" + "\n\n".join(replacements.values()) + "\n")
    (root / (name + ".sum")).write_bytes(sum_data)

for directory, module in (
    ("atomic", "github.com/natefinch/atomic"),
    ("aijson", "github.com/docker/aijson"),
    ("keepawake", "github.com/rumpl/keepawake"),
    ("portcullis", "github.com/docker/portcullis"),
):
    target = root / "shims" / directory
    target.mkdir(parents=True, exist_ok=True)
    (target / "go.mod").write_text(f"module {module}\n\ngo 1.27.3\n")

def overlay(name, replacements, absent=()):
    paths = {"/s/source/" + key: "/s/" + value for key, value in replacements.items()}
    paths.update(("/s/source/" + path, "") for path in absent)
    (root / (name + ".json")).write_text(json.dumps({"Replace": paths}, indent=2))

desktop = {"pkg/desktop/secrets_engine.go": "desktop-no-engine.go"}
overlay("desktop-no-engine", desktop)

board_fixture = {"pkg/board/review_test.go": "board_review_test.go"}
overlay("board-review-overlay", board_fixture)
overlay("tmux-review-overlay", board_fixture | {"pkg/board/review_tmux_test.go": "board_tmux_review_test.go"})
overlay("lifecycle-review-overlay", {"pkg/tools/lifecycle/review_test.go": "lifecycle_review_test.go"})
overlay("jobs-review-overlay", desktop | {"pkg/tools/builtin/backgroundjobs/review_test.go": "jobs_review_test.go"})
overlay("server-review-overlay", desktop | {
    "pkg/teamloader/defaults/defaults.go": "loader-minimal.go",
    "pkg/server/review_test.go": "server_review_test.go",
}, [str(path.relative_to(src)) for path in (src / "pkg/server").glob("*_test.go")])
overlay("runtime-review-overlay", desktop | {"pkg/runtime/review_test.go": "runtime_review_test.go"},
        [str(path.relative_to(src)) for path in (src / "pkg/runtime").glob("*_test.go")])
overlay("session-review-overlay", desktop | {"pkg/session/review_test.go": "session_review_test.go"}, [
    "pkg/session/history_reasoning_replay_test.go",
    "pkg/session/result_meta_clone_test.go",
])

native_after = (src / "pkg/runtime/after_llm_call_test.go").read_text()
native_after = native_after.replace('\tstdruntime "runtime"\n', "")
native_after = re.sub(r"(?ms)^// TestAfterLLMCallHook_HarnessUsageWithoutCostIsUnpriced.*?(?=^// TestSanitizeToolCallName)", "\n", native_after)
(root / "runtime-native-afterllm.go").write_text(native_after)
tool_phases = (src / "pkg/runtime/toolexec/tool_phases_test.go").read_text()
for package in ("github.com/docker/portcullis", "github.com/docker/docker-agent/pkg/hooks/builtins", "github.com/docker/docker-agent/pkg/internal/portcullistest"):
    tool_phases = tool_phases.replace(f'\t"{package}"\n', "")
tool_phases = tool_phases[:tool_phases.index("func TestToolPhases_RedactSecretsUnderYolo(")]
(root / "tool-phases-localonly.go").write_text(tool_phases)
overlay("core-selective-overlay2", desktop | {
    "pkg/runtime/toolexec/tool_phases_test.go": "tool-phases-localonly.go",
    "pkg/runtime/after_llm_call_test.go": "runtime-native-afterllm.go",
    "pkg/runtime/offline_helpers_test.go": "runtime-native-helpers.go",
}, [
    "pkg/runtime/background_worktree_test.go",
    "pkg/runtime/chat_completions_content_filter_test.go",
    "pkg/runtime/chat_completions_finish_reason_test.go",
    "pkg/runtime/claude5_compaction_lifecycle_test.go",
    "pkg/runtime/claude5_server_fallback_test.go",
    "pkg/runtime/claude5_sticky_attribution_test.go",
    "pkg/runtime/evaluator_hook_test.go",
    "pkg/runtime/fable_empty_turn_test.go",
    "pkg/runtime/fallback_billing_evidence_test.go",
    "pkg/runtime/gemini_finish_reason_test.go",
    "pkg/runtime/harness_test.go",
    "pkg/runtime/hooks_isolation_test.go",
    "pkg/runtime/image_output_guard_integration_test.go",
    "pkg/runtime/openai_tool_search_integration_test.go",
    "pkg/runtime/routing_command_test.go",
    "pkg/runtime/routing_integration_test.go",
    "pkg/runtime/server_fallback_budget_test.go",
    "pkg/session/history_reasoning_replay_test.go",
    "pkg/session/result_meta_clone_test.go",
    "pkg/runtime/toolexec/result_meta_redaction_test.go",
    "pkg/runtime/toolexec/result_meta_test.go",
])

wire = "pkg/tools/mcp/session_remote_test.go"
data = (src / wire).read_text()
data = data.replace('"capabilities":{"tools":{}}', '"capabilities":{"tools":{"listChanged":true}}')
(root / "mcp-capability-review.go").write_text(data)
overlay("mcp-capability-overlay", desktop | {wire: "mcp-capability-review.go"})
```

</details>

<details>
<summary>offline-extra.sum</summary>

```text
github.com/cyphar/filepath-securejoin v0.7.0 h1:s0Y3ITPy6sQn5xt54DuYvTF8hu134ooYLUb58DX/HjE=
github.com/cyphar/filepath-securejoin v0.7.0/go.mod h1:ymLGms/u3BYaviIiuKFnUx8EkQEZeK6cInNoAPJA3o4=
github.com/dlclark/regexp2/v2 v2.8.2 h1:uTTe+cxADL4be+dv4DZwsBIEPCQ6RHPlnVuKrtLqSx0=
github.com/dlclark/regexp2/v2 v2.8.2/go.mod h1:avUrQvPaLz2DrFNHJF0taWAFFX2C1GMSSoeiqFjcBmU=
github.com/docker/cli v29.9.3+incompatible h1:SBaMp7ecohadEHMDrUJg22t9I3awqsAVhnJ7GOcWpfE=
github.com/docker/cli v29.9.3+incompatible/go.mod h1:JLrzqnKDaYBop7H2jaqPtU4hHvMKP+vjCwu2uszcLI8=
github.com/dop251/goja v0.0.0-20260723142020-b4aef50fa347 h1:RZr+96+PKQjn444QL1K9MtncwJ/PwfE+3TJLCYJL8es=
github.com/dop251/goja v0.0.0-20260723142020-b4aef50fa347/go.mod h1:LiIEzozrcvNXorsG/3+ypGqdTUAqZryhzSsqi0oU/Qg=
github.com/go-git/go-billy/v5 v5.9.1 h1:8U73XiOTfINdItHVa6z4Gv7ToObcZ6grkqQbLryLCdA=
github.com/go-git/go-billy/v5 v5.9.1/go.mod h1:ExsU+jcGwXTBOnyilvAnEM1wug1IxHr4yP2ZXsNRtV0=
github.com/go-git/go-git/v5 v5.19.2 h1:wkfn7vOlUBu8ivAWKBWisTiwJK4jYHzTF8Ndv1LyGqY=
github.com/go-git/go-git/v5 v5.19.2/go.mod h1:QqCBE1EFN5ddFmrliLQ3/ntRCUjZU3EJuwuB/jWEHjk=
github.com/google/go-cmp v0.6.0/go.mod h1:17dUlkBOakJ0+DkrSSNjCkIjxS6bF9zb3elmeNGIjoY=
github.com/google/pprof v0.0.0-20260402051712-545e8a4df936 h1:EwtI+Al+DeppwYX2oXJCETMO23COyaKGP6fHVpkpWpg=
github.com/google/pprof v0.0.0-20260402051712-545e8a4df936/go.mod h1:MxpfABSjhmINe3F1It9d+8exIHFvUqtLIRCdOGNXqiI=
github.com/labstack/echo/v4 v4.13.4 h1:oTZZW+T3s9gAu5L8vmzihV7/lkXGZuITzTQkTEhcXEA=
github.com/labstack/echo/v4 v4.13.4/go.mod h1:g63b33BZ5vZzcIUF8AtRH40DrTlXnx4UMC8rBdndmjQ=
github.com/labstack/gommon v0.4.2 h1:F8qTUNXgG1+6WQmqoUWnz8WiEU60mXVVw0P4ht1WRA0=
github.com/labstack/gommon v0.4.2/go.mod h1:QlUFxVM+SNXhDL/Z7YhocGIBYOiwB0mXm1+1bAPHPyU=
github.com/modelcontextprotocol/go-sdk v1.7.0 h1:yqjY2dsbKAC0LSuWZVBMrHgiG8ukXv6NRo0JiALay44=
github.com/modelcontextprotocol/go-sdk v1.7.0/go.mod h1:dL7u98E/zjJTGzEq+j30jQ8K2k1mb6LeAH4inEcSGts=
github.com/modelcontextprotocol/go-sdk v1.8.0 h1:KIvahhYqwtbeniWVPs3TcXEA7b8jEtwfBpOTAI+Urx4=
github.com/modelcontextprotocol/go-sdk v1.8.0/go.mod h1:dL7u98E/zjJTGzEq+j30jQ8K2k1mb6LeAH4inEcSGts=
github.com/ncruces/go-strftime v1.0.0/go.mod h1:Fwc5htZGVVkseilnfgOVb9mKy6w1naJmn9CehxcKcls=
github.com/yuin/goldmark v1.4.13/go.mod h1:6yULJ656Px+3vBD8DxQVa3kxgyrAnzto9xy5taEt/CY=
golang.org/x/crypto v0.58.0 h1:COkYLr4k7nDI4r6QtMML2AfzeIswWHAJthLS6K/M/54=
golang.org/x/crypto v0.58.0/go.mod h1:Xh+kl5A+M0gMiWDytH2Hhr5Z7WbNCpv/eB/EFgfSk+w=
golang.org/x/image v0.46.0 h1:b1+oYj0Jbp6K5MDT4i4/eZpYlk3V8SJhhDKh6LBHAyQ=
golang.org/x/image v0.46.0/go.mod h1:3B3W05VGVQyuXucLINLjXKrqISASfi4Xj+iCVkLMwew=
golang.org/x/mod v0.41.0/go.mod h1:Ek9pY8RKWXwsWvd3rQiHYtMqkjSUV+s1Rj7j4H5Ur6o=
golang.org/x/net v0.62.0 h1:18ELalfM5+XNRwzM2nYqXsZQ9ByS1uhj2O/U7+5jqRY=
golang.org/x/net v0.62.0/go.mod h1:WgDCOTH8iwtB66T4/GfI94AHo/hhdb7Hah9NDseQfiI=
golang.org/x/oauth2 v0.37.0 h1:JUlcxA8oAtauLfiH8FX2/FkAWHAdi0QtGCGc+hofE98=
golang.org/x/oauth2 v0.37.0/go.mod h1:IxwZNxUULJmpBFf9K/9NTMSIfZZuvuTy1gGxhigP/58=
golang.org/x/sync v0.24.0 h1:iqiDrGoDgyuvAKrhLQthUEzU/R378N78gXbBjxed7oA=
golang.org/x/sync v0.24.0/go.mod h1:sUUOizhqBxiL6pEWpqNLUiaJn1ShEbZ6BBqskPbjZm0=
golang.org/x/sys v0.49.0 h1:XbzkgYJHdqh/8m2Uu0W/dQv8nktxx4BFHp1M0gROTXA=
golang.org/x/sys v0.49.0/go.mod h1:hNLxWAXmnKAxqDtdwIYC4bM9oQPEecfsnNMuSxOs3og=
golang.org/x/telemetry v0.0.0-20260924152758-ed294f943157/go.mod h1:i+ivNqjDnTF3WTElsdk5g9V5DTSBYgdNo7xTU9SDwYA=
golang.org/x/term v0.47.0/go.mod h1:efAfAuG6RKABvg1ArGebRkvX6LXul14SM67o2e4mUCY=
golang.org/x/text v0.43.0 h1:1QivrlhwAsnMOcqgOdl9my7s9OyZl8O5/UGUTJVXoWc=
golang.org/x/text v0.43.0/go.mod h1:hbSIYA/amXcRXTFSZqh8tWHEoqRvvbKPJ2uz/KU+a+s=
golang.org/x/tools v0.49.0/go.mod h1:SJNXV9DBKT0UbdttsQjbfJlAE/q+y36++zo3uL3N0Oo=
golang.org/x/tools v0.51.0/go.mod h1:9eEncMayCV6zRMGhR5eZEC2iBx98qWcF1HZ9Z7wJOoA=
modernc.org/libc v1.74.3 h1:a4J+Z8aVaxPyjyxRAdJzw246PqpcFGvVPnfT/AuM5Ws=
modernc.org/libc v1.74.3/go.mod h1:4H7h/MJ8wnjL8RAbp9v3OXgnk22X7MouHIhDbvP3gj4=
modernc.org/memory v1.11.0 h1:o4QC8aMQzmcwCK3t3Ux/ZHmwFPzE6hf2Y5LbkRs+hbI=
modernc.org/memory v1.11.0/go.mod h1:/JP4VbVC+K5sU2wZi9bHoq2MAkCnrt2r98UGeSK7Mjw=
modernc.org/sqlite v1.54.0 h1:JCxR4qwkJvOaqAoYcgDoO25Nc+ROg6EJ2LfBVzdrgog=
modernc.org/sqlite v1.54.0/go.mod h1:4ntCLuNmnH8+GNqjka1wNg7KJd5/Hi5FYp8K+XQ7GZw=
```

</details>

<details>
<summary>runtime-native-helpers.go</summary>

```go
package runtime
import (
  "context"
  "os"
  "path/filepath"
  "github.com/docker/docker-agent/pkg/js"
  "github.com/docker/docker-agent/pkg/tools"
  "github.com/docker/docker-agent/pkg/paths"
  "testing"
  "github.com/docker/docker-agent/pkg/session"
  "github.com/docker/docker-agent/pkg/session/sqlitestore"
  "github.com/docker/docker-agent/pkg/evaluator"
  "github.com/stretchr/testify/require"
  "github.com/stretchr/testify/assert"
)
func openSessionStore(t *testing.T, path string) session.Store {
	t.Helper()
	store, err := sqlitestore.New(t.Context(), path)
	require.NoError(t, err)
	t.Cleanup(func() { assert.NoError(t, store.Close()) })
	return store
}

type runtimeEvaluatorFunc func(context.Context, any) (*evaluator.Result, error)

func (f runtimeEvaluatorFunc) Evaluate(ctx context.Context, state any) (*evaluator.Result, error) {
	return f(ctx, state)
}

func TestMain(m *testing.M) {
    RegisterCommandEvaluator(func(ts []tools.Tool) CommandEvaluator { return js.NewEvaluator(ts) })
    dir,err:=os.MkdirTemp("", "runtime-test-config-*")
    if err != nil {panic(err)}
    paths.SetConfigDir(dir)
    code:=m.Run()
    _ = os.RemoveAll(filepath.Clean(dir))
    os.Exit(code)
}
```

</details>

<details>
<summary>desktop-no-engine.go</summary>

```go
package desktop

import "context"

// secretsEngineToken never finds a token: the SDK doesn't support this platform.
func secretsEngineToken(context.Context) (string, DockerHubInfo, bool) {
	return "", DockerHubInfo{}, false
}
```

</details>

<details>
<summary>loader-minimal.go</summary>

```go
package defaults

import "github.com/docker/docker-agent/pkg/teamloader"

// The isolated server fixtures attach already-built in-process runtimes.
func Opts() []teamloader.Opt { return nil }
func LoaderOpts() []teamloader.Opt { return nil }
```

</details>

<details>
<summary>readdir-control.py</summary>

```python
import concurrent.futures
import json
import os
import pathlib
import tempfile
import threading

root = pathlib.Path(tempfile.mkdtemp())
for placement in ('same-dir', 'sibling-dir', 'no-writer'):
    destdir = root / placement
    destdir.mkdir()
    dest = destdir / 'p.json'
    dest.write_text('0')
    scratch = destdir if placement == 'same-dir' else root
    stop=threading.Event()
    barrier=threading.Barrier(3)
    def writer():
        i=0
        barrier.wait()
        if placement != 'no-writer':
            while not stop.is_set():
                tmp=scratch / ('candidate-' + str(i))
                tmp.write_text(str(i + 1))
                os.replace(tmp, dest)
                i += 1
        return i
    def reader():
        barrier.wait()
        missing=absent_by_path=other=0
        examples=[]
        for i in range(15000):
            names=os.listdir(destdir)
            if names.count(dest.name)!=1:
                missing += 1
                if len(examples) < 4: examples.append(names)
            try:
                int(dest.read_text())
            except FileNotFoundError:
                absent_by_path += 1
            except ValueError:
                other += 1
        return missing,absent_by_path,other,examples
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        w=pool.submit(writer)
        r1,r2=pool.submit(reader),pool.submit(reader)
        reads=[r1.result(),r2.result()]
        stop.set()
        print(json.dumps(dict(placement=placement, reads=reads, writes=w.result())))
```

</details>

<details>
<summary>board_review_test.go</summary>

```go
package board

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
	"testing/synctest"
	"time"

	"github.com/stretchr/testify/require"
)

func TestReviewStorePublishFailure(t *testing.T) {
	t.Parallel()
	base := t.TempDir()
	parent := filepath.Join(base, "active")
	stash := filepath.Join(base, "pre-fault")
	path := filepath.Join(parent, "cards.json")
	store, err := OpenStore(path)
	require.NoError(t, err)
	require.NoError(t, store.InsertCard(&Card{ID: "one", Column: "dev", Status: StatusWaiting}))
	require.NoError(t, os.Rename(parent, stash))
	require.NoError(t, os.WriteFile(parent, []byte("not a directory"), 0o600))
	changed, err := store.UpdateCardStatus("one", StatusRunning)
	require.Error(t, err)
	require.True(t, changed)
	require.ErrorContains(t, err, "not a directory")
	memory, err := store.GetCard("one")
	require.NoError(t, err)
	require.Equal(t, StatusRunning, memory.Status)
	require.NoError(t, os.Remove(parent))
	require.NoError(t, os.Rename(stash, parent))
	changed, err = store.UpdateCardStatus("one", StatusRunning)
	require.NoError(t, err)
	require.False(t, changed)
	disk, err := OpenStore(path)
	require.NoError(t, err)
	persisted, err := disk.GetCard("one")
	require.NoError(t, err)
	require.Equal(t, StatusWaiting, persisted.Status)
	t.Logf("fault before atomic writer; in-memory=%s reopened=%s same-value retry changed=%t", memory.Status, persisted.Status, changed)
}

func TestReviewMoveAckFailure(t *testing.T) {
	id := newID()
	sock := socketPath(id)
	ln, err := net.Listen("unix", sock)
	require.NoError(t, err)
	var calls atomic.Int32
	var key atomic.Value
	srv := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte("{}"))
			return
		}
		key.Store(r.Header.Get("Idempotency-Key"))
		if calls.Add(1) == 1 {
			http.Error(w, "fixture unavailable", 503)
			return
		}
		w.WriteHeader(202)
	})}
	go func() { _ = srv.Serve(ln) }()
	t.Cleanup(func(){ _ = srv.Close() })
	store := testStore(t)
	card := &Card{ID: "c1", Column: "dev", Status: StatusWaiting, AgentSession: id}
	require.NoError(t, store.InsertCard(card))
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	sessions := fakeSessions{}
	ctrl := newController(ctx, store, sessions, func() {})
	defer ctrl.Stop(card.ID)
	app := &App{ctx: ctx, store: store, sessions: sessions, controller: ctrl, columns: []Column{
		{ID:"dev"}, {ID:"next", Prompt:"benign fixture"},
	}, onChanged: func() {}}
	require.ErrorContains(t, app.MoveCard("c1", "next"), "503")
	persisted, err := OpenStore(store.path)
	require.NoError(t, err)
	got, err := persisted.GetCard("c1")
	require.NoError(t, err)
	require.Equal(t, "next", got.Column)
	require.NoError(t, app.MoveCard("c1", "next"))
	require.Equal(t, int32(1), calls.Load())
	firstKey := key.Load().(string)
	require.NotEmpty(t, firstKey)
	require.NoError(t, app.MoveCard("c1", "dev"))
	require.NoError(t, app.MoveCard("c1", "next"))
	require.Equal(t, int32(2), calls.Load())
	require.NotEqual(t, firstKey, key.Load())
	t.Logf("503 left destination persisted; same-destination retry did not deliver; reverse/forward did with a fresh key")
}

func TestReviewReplayWithoutBoundary(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		var events []event
		for i := uint64(3); i <= 1026; i++ {
			events = append(events, event{Type: "agent_choice", Seq: i})
		}
		store, _ := watchCard(t, snapshot{LastEventSeq: 1026}, events)
		synctest.Wait()
		card, err := store.GetCard("c1")
		require.NoError(t, err)
		require.Equal(t, StatusWaiting, card.Status)
		t.Logf("covered seq 3–1026 (1024 frames), truncated start; status=%s", card.Status)
		store, _ = watchCard(t, snapshot{LastEventSeq: 1026}, append([]event{{Type: eventStreamStarted, Seq: 2}}, events[:1023]...))
		synctest.Wait()
		card, err = store.GetCard("c1")
		require.NoError(t, err)
		require.Equal(t, StatusWaiting, card.Status, "without snapshot seq saw only intermediate replay")
		events[0].Type = eventStreamStarted
		store, _ = watchCard(t, snapshot{LastEventSeq: 1026}, events)
		synctest.Wait()
		card, err = store.GetCard("c1")
		require.NoError(t, err)
		require.Equal(t, StatusRunning, card.Status)
	})
}

type faultMover struct { fakeSessions; c *controller; card *Card; alreadyAlive bool; operations []string }
func (f *faultMover) Alive(string) (bool, error) {
	if f.alreadyAlive {
		return true, nil
	}
	f.alreadyAlive = true
	defer func() {
		f.operations = append(f.operations, "watcher admitted a new pane after liveness sample")
	}()
	return false, nil
}
func (f *faultMover) KillSession(string) error {
	f.operations = append(f.operations, fmt.Sprintf("kill while alive=%t", f.alreadyAlive))
	return nil
}
func (f *faultMover) NewSession(_, _, _, _, _, _, _, prompt string) error {
	f.operations = append(f.operations, "new: " + prompt)
	return nil
}

func TestReviewPromptRelaunchUsesStaleLiveness(t *testing.T) {
	store := testStore(t)
	card := &Card{ID:"c1", Status:StatusWaiting, Worktree:t.TempDir(), AgentSession:newID()}
	require.NoError(t, store.InsertCard(card))
	f := &faultMover{card:card}
	f.c = newController(t.Context(), store, f, func(){})
	f.c.clientFor = func(_, _ string) sessionClient { return &reviewFailedFollowup{} }
	require.NoError(t, f.c.SendPrompt(card, "benign follow-up"))
	require.Equal(t, []string{"watcher admitted a new pane after liveness sample", "kill while alive=true", "new: benign follow-up"}, f.operations)
	t.Log(f.operations)
}

type reviewFailedFollowup struct{ fakeClient }
func (reviewFailedFollowup) Followup(context.Context, string, string) error { return errors.New("fixture disconnected") }

func TestReviewSnapshotSuccessWithoutHeartbeat(t *testing.T) {
	var requests atomic.Int32
	var follow atomic.Int32
	id := newID()
	ln, err := net.Listen("unix", socketPath(id))
	require.NoError(t, err)
	started := make(chan struct{})
	srv := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch filepath.Base(r.URL.Path) {
		case "snapshot":
			requests.Add(1)
			_, _ = w.Write([]byte("{\"streaming\":true,\"last_event_seq\":1}"))
		case "events":
			w.Header().Set("Content-Type","text/event-stream")
			w.WriteHeader(200)
			w.(http.Flusher).Flush()
			close(started)
			<-r.Context().Done()
		case "followup":
			follow.Add(1)
			w.WriteHeader(202)
		}
	})}
	go func(){_ = srv.Serve(ln)}()
	defer srv.Close()
	store := testStore(t)
	card := &Card{ID:"c1", AgentSession:id, Status:StatusStarting}
	require.NoError(t, store.InsertCard(card))
	c := newController(t.Context(),store,fakeSessions{},func(){})
	c.Start(card)
	defer c.Stop(card.ID)
	select {
	case <-started:
	case <-time.After(time.Second): t.Fatal("event HTTP handshake never reached")
	}
	status, err := store.GetCard(card.ID)
	require.NoError(t,err)
	require.Equal(t, StatusWaiting, status.Status)
	require.Equal(t,int32(1),requests.Load())
	require.NoError(t,c.SendPrompt(card, "benign"))
	require.Equal(t,int32(1),follow.Load())
	t.Logf("real Unix HTTP snapshot said streaming=true; card=%s with no replayed boundary",status.Status)
}
```

</details>

<details>
<summary>board_tmux_review_test.go</summary>

```go
package board

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync/atomic"
	"syscall"
	"testing"
	"time"

	"github.com/docker/docker-agent/pkg/paths"
	"github.com/stretchr/testify/require"
)

func TestMain(m *testing.M) {
	if len(os.Args)>1 && os.Args[1]=="run" {
		if err:=reviewFixtureWorker(os.Args[2:]); err!=nil {
			fmt.Fprintln(os.Stderr,err)
			os.Exit(2)
		}
		os.Exit(0)
	}
	os.Exit(m.Run())
}

func reviewFixtureWorker(args []string) error {
	if len(args)==0 { return fmt.Errorf("agent argument missing") }
	args = args[1:]
	var dir,id,sock,wname,base,prompt string
	for len(args)>0 {
		flag:=args[0]
		args=args[1:]
		if flag=="--yolo" { continue }
		if name,ok:=strings.CutPrefix(flag,"--worktree="); ok { wname=name;continue }
		if !strings.HasPrefix(flag,"--") { prompt=flag;continue }
		if len(args)==0 { return fmt.Errorf("missing value for %s",flag) }
		val:=args[0]; args=args[1:]
		switch flag {
		case "--session": id=val
		case "--data-dir": dir=val
		case "--listen": sock=strings.TrimPrefix(val,"unix://")
		case "--worktree-base": base=val
		}
	}
	if id=="" || sock=="" || dir=="" { return fmt.Errorf("session, socket and data dir required") }
	if wname!="" {
		dest:=filepath.Join(dir,"worktrees",wname)
		if err:=os.MkdirAll(filepath.Dir(dest),0o700);err!=nil { return err }
		git:=exec.Command("git","worktree","add","-b","worktree-"+wname,dest,base)
		if out,err:=git.CombinedOutput();err!=nil { return fmt.Errorf("git: %s: %w",out,err) }
	}
	cwd,err:=os.Getwd()
	if err!=nil{return err}
	marker:=filepath.Join(dir,id+".fixture")
	file,err:=os.OpenFile(marker,os.O_CREATE|os.O_APPEND|os.O_WRONLY,0o600)
	if err!=nil{return err}
	_,err=fmt.Fprintf(file,"pid=%d cwd=%s prompt=%q\n",os.Getpid(),cwd,prompt)
	_ = file.Close()
	if err!=nil{return err}
	ln,err:=net.Listen("unix",sock)
	if err!=nil{return err}
	defer ln.Close()
	mux:=http.NewServeMux()
	mux.HandleFunc("GET /api/sessions/"+id+"/snapshot",func(w http.ResponseWriter,r *http.Request){
		seq:=0
		if prompt!="" { seq=3 }
		_ = json.NewEncoder(w).Encode(map[string]any{"title":"Fixture process","last_event_seq":seq})
	})
	mux.HandleFunc("GET /api/sessions/"+id+"/events",func(w http.ResponseWriter,r *http.Request){
		w.Header().Set("Content-Type","text/event-stream")
		_,_ = io.WriteString(w,": ping\n\n")
		if prompt!="" {
			_,_ = io.WriteString(w,"id: 1\ndata: {\"type\":\"user_message\"}\n\nid: 2\ndata: {\"type\":\"stream_started\"}\n\nid: 3\ndata: {\"type\":\"stream_stopped\",\"reason\":\"normal\"}\n\n")
		}
		w.(http.Flusher).Flush()
		<-r.Context().Done()
	})
	mux.HandleFunc("POST /api/sessions/"+id+"/followup",func(w http.ResponseWriter,r *http.Request){
		raw,err:=io.ReadAll(r.Body)
		if err!=nil || r.Header.Get("Idempotency-Key")=="" { http.Error(w,"invalid fixture request",400);return }
		f,err:=os.OpenFile(marker,os.O_APPEND|os.O_WRONLY,0o600)
		if err!=nil { http.Error(w,err.Error(),500);return }
		_,err=fmt.Fprintf(f,"followup=%s\n",raw)
		_ = f.Close()
		if err!=nil { http.Error(w,err.Error(),500);return }
		w.WriteHeader(http.StatusAccepted)
	})
	return (&http.Server{Handler:mux,ReadHeaderTimeout:time.Second}).Serve(ln)
}

func TestReviewTmuxGitUnixSocketLifecycle(t *testing.T) {
	t.Setenv("SHELL","/bin/sh")
	base:=t.TempDir()
	data, repo:=filepath.Join(base,"data"),filepath.Join(base,"repo")
	require.NoError(t,os.MkdirAll(repo,0o700))
	paths.SetDataDir(data)
	defer paths.SetDataDir("")
	sh:=func(a ...string) string {
		t.Helper()
		cmd:=exec.CommandContext(t.Context(),"git",a...)
		cmd.Dir=repo
		b,err:=cmd.CombinedOutput()
		require.NoError(t,err,"%s",b)
		return strings.TrimSpace(string(b))
	}
	sh("init","-b","main")
	sh("-c","user.name=Local Fixture","-c","user.email=fixture@localhost","commit","--allow-empty","-m","fixture")
	ctx,cancel:=context.WithCancel(t.Context())
	defer cancel()
	t.Cleanup(func(){ _,_ = tmuxRun(context.Background(),"kill-server") })
	app,err:=NewApp(ctx,func(){})
	require.NoError(t,err)
	var notices atomic.Int32
	app.onChanged=func(){notices.Add(1)}
	app.columns=[]Column{{ID:"dev"},{ID:"next",Prompt:"bounded local follow-up"}}
	card,err:=app.CreateCard(Project{Name:"fixture",Path:repo,Agent:"fixture"},"bounded local first turn")
	require.NoError(t,err)
	defer app.controller.Stop(card.ID)
	marker:=filepath.Join(data,card.AgentSession+".fixture")
	readMarker:=func()string { b,_:=os.ReadFile(marker);return string(b) }
	waitStage:=func(substr string){
		t.Helper()
		require.Eventually(t,func()bool{
			c,err:=app.store.GetCard(card.ID)
			return err==nil && c.Status==StatusWaiting && strings.Contains(readMarker(),substr)
		},5*time.Second,20*time.Millisecond)
	}
	waitStage("prompt=\"bounded local first turn\"")
	require.Equal(t,sh("rev-parse","HEAD"),sh("rev-parse",card.Branch))
	require.DirExists(t,card.Worktree)
	queryPID:=func() int{
		t.Helper()
		result,err:=tmuxRun(ctx,"list-panes","-t","="+card.Session,"-F","#{pane_pid}")
		require.NoError(t,err)
		i,err:=strconv.Atoi(strings.TrimSpace(result))
		require.NoError(t,err)
		return i
	}
	first:=queryPID()
	require.NoError(t,syscall.Kill(first,syscall.SIGKILL))
	waitStage("cwd="+card.Worktree+" prompt=\"\"")
	second:=queryPID()
	require.NotEqual(t,first,second)
	require.NoError(t,app.MoveCard(card.ID,"next"))
	require.Contains(t,readMarker(),"bounded local follow-up")
	require.Equal(t,int32(2),notices.Load())
	require.NoError(t,app.DeleteCard(card.ID))
	require.NoDirExists(t,card.Worktree)
	require.Empty(t,sh("branch","--list",card.Branch))
	exists,err:=app.sessions.Exists(card.Session)
	require.NoError(t,err)
	require.False(t,exists)
	t.Logf("actual tmux process %d -> %d under stable session ID %s, resumed from same checkout; branch, socket and tmux session cleaned",first,second,card.AgentSession)
	require.NoFileExists(t,socketPath(card.AgentSession))
}
```

</details>

<details>
<summary>lifecycle_review_test.go</summary>

```go
package lifecycle_test

import (
	"context"
	"errors"
	"testing"
	"testing/synctest"
	"time"

	"github.com/docker/docker-agent/pkg/tools/lifecycle"
	"github.com/stretchr/testify/require"
)

func TestReviewStartDuringFailureCallback(t *testing.T) {
	for _, overlap := range []bool{false,true} {
		name := "after watcher retired"
		if overlap { name = "during terminal callback" }
		t.Run(name, func(t *testing.T) {
			synctest.Test(t, func(t *testing.T) {
				first, second := newFakeSession(), newFakeSession()
				entered, release := make(chan struct{}), make(chan struct{})
				callbackCount := 0
				c := newScriptedConnector(scriptStep{session:first},scriptStep{session:second})
				s := lifecycle.New("fixture", c, lifecycle.Policy{Restart:lifecycle.RestartNever, OnFailed:func(error){
					callbackCount++
					if callbackCount==1 { close(entered); <-release }
				}})
				require.NoError(t,s.Start(t.Context()))
				first.waitParked(t)
				first.fail(errors.New("first transport ended"))
				<-entered
				require.Equal(t,lifecycle.StateFailed,s.State().State)
				if !overlap { close(release); synctest.Wait() }
				require.NoError(t,s.Start(t.Context()))
				if overlap { close(release) }
				synctest.Wait()
				watching := false
				select { case <-second.waiting: watching=true; default: }
				second.fail(errors.New("replacement transport ended"))
				synctest.Wait()
				if overlap {
					require.False(t,watching)
					require.Equal(t,lifecycle.StateReady,s.State().State)
				} else {
					require.True(t,watching)
					require.Equal(t,lifecycle.StateFailed,s.State().State)
				}
				require.Equal(t,2,c.Calls())
				t.Logf("overlap=%t replacement_wait_entered=%t after_replacement_exit=%s",overlap,watching,s.State().State)
				require.NoError(t,s.Stop(t.Context()))
			})
		})
	}
}

func TestReviewStartCallerCancellation(t *testing.T) {
	for _, timed := range []bool{false,true} {
		name := "no policy deadline"
		if timed { name = "policy deadline" }
		t.Run(name,func(t *testing.T){
			synctest.Test(t,func(t *testing.T){
				timeout := time.Duration(0)
				if timed { timeout = 100*time.Millisecond }
				c:=&blockingConnector{release: make(chan struct{}), session:newFakeSession()}
				s:=lifecycle.New("fixture",c,lifecycle.Policy{StartupTimeout:timeout})
				ctx,cancel:=context.WithCancel(t.Context())
				started:=time.Now()
				done:=make(chan error,1)
				go func(){done<-s.Start(ctx)}()
				synctest.Wait()
				cancel()
				err:=<-done
				if timed {
					require.ErrorIs(t,err,lifecycle.ErrInitTimeout)
					require.Equal(t,timeout,time.Since(started))
				} else {
					require.ErrorIs(t,err,context.Canceled)
					require.Zero(t,time.Since(started))
				}
				t.Logf("timed=%t cancel_result=%v elapsed=%v",timed,err,time.Since(started))
				close(c.release)
				require.NoError(t,s.Stop(t.Context()))
				synctest.Wait()
			})
		})
	}
}
```

</details>

<details>
<summary>runtime_review_test.go</summary>

```go
package runtime

import (
	"context"
	"errors"
	"io"
	"slices"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"testing/synctest"
	"time"

	"github.com/docker/docker-agent/pkg/agent"
	"github.com/docker/docker-agent/pkg/chat"
	"github.com/docker/docker-agent/pkg/config/latest"
	"github.com/docker/docker-agent/pkg/model/provider/base"
	"github.com/docker/docker-agent/pkg/modelsdev"
	"github.com/docker/docker-agent/pkg/session"
	"github.com/docker/docker-agent/pkg/team"
	"github.com/docker/docker-agent/pkg/tools"
	agenttool "github.com/docker/docker-agent/pkg/tools/builtin/agent"
	"github.com/docker/docker-agent/pkg/tools/builtin/transfertask"
	"github.com/stretchr/testify/require"
)

type reviewProvider struct {
	name string
	call func(context.Context, []chat.Message) (chat.MessageStream, error)
}

func (p reviewProvider) ID() modelsdev.ID { return modelsdev.NewID("fixture",p.name) }
func (p reviewProvider) BaseConfig() base.Config { return base.Config{ModelConfig:latest.ModelConfig{Provider:"fixture",Model:p.name,ContextWindow:new(int64(4096))}} }
func (p reviewProvider) CreateChatCompletionStream(ctx context.Context,msgs []chat.Message,_ []tools.Tool)(chat.MessageStream,error) {
	return p.call(ctx,msgs)
}
type reviewModels struct{ ModelStore }
func (reviewModels) GetModel(context.Context,modelsdev.ID)(*modelsdev.Model,error){return nil,nil}

type reviewStream struct{
	i,n int
	onRecv func()
	onClose func()
}
func (s *reviewStream) Recv()(chat.MessageStreamResponse,error){
	s.i++
	if s.onRecv!=nil{s.onRecv()}
	if s.i <= s.n{
		return chat.MessageStreamResponse{Choices:[]chat.MessageStreamChoice{{Index:0,Delta:chat.MessageDelta{Content:"fixture reply "}}}},nil
	}
	if s.i==s.n+1{
		return chat.MessageStreamResponse{Choices:[]chat.MessageStreamChoice{{Index:0,FinishReason:chat.FinishReasonStop}},Usage:&chat.Usage{InputTokens:6,OutputTokens:1}},nil
	}
	return chat.MessageStreamResponse{},io.EOF
}
func (s *reviewStream) Close(){ if s.onClose!=nil{s.onClose()} }

func reviewRuntime(t *testing.T, rootP reviewProvider, childP *reviewProvider, opts ...Opt) (*LocalRuntime,*session.Session) {
	t.Helper()
	root:=agent.New("root","Fixture root",agent.WithModel(rootP))
	members:=[]*agent.Agent{root}
	if childP!=nil {
		child:=agent.New("child","Fixture child",agent.WithModel(*childP),agent.WithMaxIterations(8))
		agent.WithSubAgents(child)(root)
		members=append(members,child)
	}
	standard:=[]Opt{WithSessionCompaction(false),WithModelStore(reviewModels{})}
	r,err:=NewLocalRuntime(t.Context(),team.New(team.WithAgents(members...)),append(standard,opts...)...)
	require.NoError(t,err)
	t.Cleanup(func(){require.NoError(t,r.Close())})
	s:=session.New(session.WithMaxIterations(8),session.WithNonInteractive(true))
	s.AddMessage(session.UserMessage("initial fixture"))
	return r,s
}

func TestReviewChildConsumesRuntimeUserQueue(t *testing.T){
	for _, mode:=range []string{"steer","followup","no child"} {
		t.Run(mode,func(t *testing.T){
			synctest.Test(t,func(t *testing.T){
				rootParked, release:=make(chan struct{}),make(chan struct{})
				var once sync.Once
				var rootInput,childInput []string
				root:=reviewProvider{"root",func(ctx context.Context,m []chat.Message)(chat.MessageStream,error){
					for _,v:=range m { if v.Role==chat.MessageRoleUser{rootInput=append(rootInput,v.Content)} }
					once.Do(func(){close(rootParked);<-release})
					return &reviewStream{n:1},nil
				}}
				child:=reviewProvider{"child",func(ctx context.Context,m []chat.Message)(chat.MessageStream,error){
					for _,v:=range m{if v.Role==chat.MessageRoleUser{childInput=append(childInput,v.Content)}}
					return &reviewStream{n:1},nil
				}}
				r,s:=reviewRuntime(t,root,&child)
				main:=r.RunStream(t.Context(),s)
				<-rootParked
				const content="user input addressed to root"
				m:=QueuedMessage{ID:"root-message",Content:content}
				if mode=="steer" {require.NoError(t,r.Steer(t.Context(),m));require.Equal(t,1,r.QueueStatus().SteerDepth)} else { require.NoError(t,r.FollowUp(t.Context(),m));require.Equal(t,1,r.QueueStatus().FollowupDepth) }
				if mode!="no child"{
					result:=r.RunAgent(t.Context(),agenttool.RunParams{ParentSession:s,AgentName:"child",Task:"count benign fixture data"})
					require.Empty(t,result.ErrMsg)
					require.Contains(t,childInput,content)
					require.Zero(t,r.QueueStatus().SteerDepth+r.QueueStatus().FollowupDepth)
				}
				close(release)
				for range main{}
				if mode=="no child" {require.Contains(t,rootInput,content)}else{require.NotContains(t,rootInput,content)}
				t.Logf("queue=%s reached_root=%t reached_child=%t root_items=%d",mode,slices.Contains(rootInput,content),slices.Contains(childInput,content),s.ItemCount())
			})
		})
	}
}

func TestReviewConcurrentBudgetAdmission(t *testing.T){
	synctest.Test(t,func(t *testing.T){
		arrivals:=make(chan struct{},2)
		release:=make(chan struct{})
		var rootCalls atomic.Int32
		root:=reviewProvider{"root",func(context.Context,[]chat.Message)(chat.MessageStream,error){
			rootCalls.Add(1)
			return &reviewStream{n:1},nil
		}}
		child:=reviewProvider{"child",func(context.Context,[]chat.Message)(chat.MessageStream,error){
			arrivals<-struct{}{}
			<-release
			return &reviewStream{n:1},nil
		}}
		r,s:=reviewRuntime(t,root,&child,WithBudget(&latest.BudgetConfig{MaxTokens:10}))
		r.ensureBudget()
		require.NoError(t,r.sessionStore.AddSession(t.Context(),s))
		results:=make(chan *agenttool.RunResult,2)
		for range 2 { go func(){results<-r.RunAgent(t.Context(),agenttool.RunParams{ParentSession:s,AgentName:"child",Task:"benign budget fixture"})}() }
		<-arrivals
		<-arrivals
		require.Zero(t,r.currentBudget().trackers[runBudgetName].snapshot().Tokens)
		close(release)
		for range 2 {require.Empty(t,(<-results).ErrMsg)}
		b:=r.currentBudget().trackers[runBudgetName].snapshot()
		require.Equal(t,int64(14),b.Tokens)
		breaches:=0
		for e:=range r.RunStream(t.Context(),s){if _,ok:=e.(*BudgetExceededEvent);ok {breaches++}}
		require.Zero(t,rootCalls.Load())
		require.Equal(t,1,breaches)
		result:=r.RunAgent(t.Context(),agenttool.RunParams{ParentSession:s,AgentName:"child",Task:"budget already reached"})
		require.Empty(t,result.ErrMsg)
		require.Contains(t,result.Result,"max_tokens")
		t.Logf("two concurrent dispatches admitted at usage=0; spent=%d cap=%d; next root rejected; child reported stop as successful output",b.Tokens,b.MaxTokens)
	})
}

func TestReviewUndrainedCancelKeepsProducerLive(t *testing.T){
	synctest.Test(t,func(t *testing.T){
		var read atomic.Int32
		closed:=make(chan struct{})
		root:=reviewProvider{"root",func(context.Context,[]chat.Message)(chat.MessageStream,error){
			return &reviewStream{n:4*defaultEventChannelCapacity,onRecv:func(){read.Add(1)},onClose:func(){close(closed)}},nil
		}}
		r,s:=reviewRuntime(t,root,nil)
		ctx,cancel:=context.WithCancel(t.Context())
		out:=r.RunStream(ctx,s)
		synctest.Wait()
		require.Equal(t,cap(out),len(out))
		require.Greater(t,read.Load(),int32(defaultEventChannelCapacity))
		count:=read.Load()
		cancel()
		synctest.Wait()
		require.Equal(t,count,read.Load())
		select{case <-closed:t.Fatal("provider should still be waiting behind an undrained send");default:}
		events:=0
		for range out{events++}
		select{case <-closed:default:t.Fatal("provider never closed after drain")}
		synctest.Wait()
		require.Zero(t,r.activeRootStreams.Load())
		t.Logf("cancel at full %d-event out buffer held stream open after %d received frames; draining %d events released the provider",cap(out),count,events)
	})
}

func TestReviewBudgetAfterRestartIsNew(t *testing.T){
	root:=reviewProvider{"root",func(context.Context,[]chat.Message)(chat.MessageStream,error){return &reviewStream{n:1},nil}}
	cfg:=&latest.BudgetConfig{MaxTokens:7}
	r,s:=reviewRuntime(t,root,nil,WithBudget(cfg))
	for range r.RunStream(t.Context(),s){}
	require.Equal(t,int64(7),r.currentBudget().trackers[runBudgetName].snapshot().Tokens)
	budgetStops:=func(rt *LocalRuntime) int {
		stops:=0
		for e:=range rt.RunStream(t.Context(),s){if _,ok:=e.(*BudgetExceededEvent);ok {stops++}}
		return stops
	}
	require.Equal(t,1,budgetStops(r))
	r2,_:=reviewRuntime(t,root,nil,WithBudget(cfg))
	require.Equal(t,0,budgetStops(r2))
	require.Equal(t,int64(7),r2.currentBudget().trackers[runBudgetName].snapshot().Tokens)
	require.True(t,strings.Contains(s.GetLastAssistantMessageContent(),"fixture reply"))
}

var _ = errors.Is
var _ = time.Second

type reviewDelegateSink struct {
	alphaSet, betaSet, alphaUsed chan struct{}
	firstAlpha, firstBeta atomic.Bool
}

func (gate *reviewDelegateSink) Emit(event Event) {
	switch e:=event.(type){
	case *AgentSwitchingEvent:
		if e.Switching && e.ToAgent=="beta" {<-gate.alphaSet}
	case *AgentInfoEvent:
		switch e.AgentName {
		case "alpha":
			if gate.firstAlpha.CompareAndSwap(false,true){close(gate.alphaSet);<-gate.betaSet}
		case "beta":
			if gate.firstBeta.CompareAndSwap(false,true){close(gate.betaSet);<-gate.alphaUsed}
		}
	}
}

func TestReviewParallelSiblingTransfersSwitchSharedAgent(t *testing.T){
	for _,parallel:=range []bool{false,true}{
		label:="serial"
		if parallel{label="parallel"}
		t.Run(label,func(t *testing.T){
			synctest.Test(t,func(t *testing.T){
				type observation struct{ task, agent string }
				recorded:=make(chan observation,3)
				gate:=&reviewDelegateSink{alphaSet:make(chan struct{}),betaSet:make(chan struct{}),alphaUsed:make(chan struct{})}
				var routedAlpha atomic.Bool
				makeModel:=func(name string)reviewProvider{
					return reviewProvider{name,func(_ context.Context,msgs []chat.Message)(chat.MessageStream,error){
						for _,m:=range msgs{
							for _,task:=range []string{"alpha fixture task","beta fixture task"}{
								if strings.Contains(m.Content,task){
									recorded<-observation{task,name}
									if task=="alpha fixture task" && routedAlpha.CompareAndSwap(false,true){close(gate.alphaUsed)}
								}
							}
						}
						return &reviewStream{n:1},nil
					}}
				}
				alpha:=agent.New("alpha","Fixture alpha",agent.WithModel(makeModel("alpha")))
				beta:=agent.New("beta","Fixture beta",agent.WithModel(makeModel("beta")))
				root:=agent.New("root","Fixture root",agent.WithModel(makeModel("root")),agent.WithSubAgents(alpha,beta))
				rt,err:=NewLocalRuntime(t.Context(),team.New(team.WithAgents(root,alpha,beta)),WithSessionCompaction(false),WithModelStore(reviewModels{}))
				require.NoError(t,err)
				defer rt.Close()
				sess:=session.New(session.WithNonInteractive(true),session.WithToolsApproved(true))
				require.NoError(t,rt.sessionStore.AddSession(t.Context(),sess))
				defs,err:=transfertask.New().Tools(t.Context())
				require.NoError(t,err)
				calls:=[]tools.ToolCall{
					{ID:"alpha-call",Function:tools.FunctionCall{Name:"transfer_task",Arguments:`{"agent":"alpha","task":"alpha fixture task","expected_output":"alpha"}`}},
					{ID:"beta-call",Function:tools.FunctionCall{Name:"transfer_task",Arguments:`{"agent":"beta","task":"beta fixture task","expected_output":"beta"}`}},
				}
				if parallel{
					stop,msg:=rt.processToolCalls(t.Context(),sess,root,calls,defs,gate)
					require.False(t,stop,msg)
				}else{
					sink:=NewChannelSink(make(chan Event,500))
					for _,call:=range calls {
						stop,msg:=rt.processToolCalls(t.Context(),sess,root,[]tools.ToolCall{call},defs,sink)
						require.False(t,stop,msg)
					}
				}
				close(recorded)
				output:=map[string]string{}
				for entry:=range recorded{output[entry.task]=entry.agent}
				require.Len(t,output,2)
				if parallel{ require.Equal(t,"beta",output["alpha fixture task"])}else{ require.Equal(t,"alpha",output["alpha fixture task"]);require.Equal(t,"beta",output["beta fixture task"]) }
				if !parallel {require.Equal(t,"root",rt.currentAgentName())}
				t.Logf("parallel=%t task-to-provider=%v final_shared=%s",parallel,output,rt.currentAgentName())
			})
		})
	}
}
```

</details>

<details>
<summary>server_review_test.go</summary>

```go
package server

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"slices"
	"strings"
	"sync/atomic"
	"testing"
	"testing/synctest"
	"time"

	"github.com/docker/docker-agent/pkg/agent"
	"github.com/docker/docker-agent/pkg/api"
	"github.com/docker/docker-agent/pkg/chat"
	"github.com/docker/docker-agent/pkg/config"
	"github.com/docker/docker-agent/pkg/config/latest"
	"github.com/docker/docker-agent/pkg/model/provider/base"
	"github.com/docker/docker-agent/pkg/modelsdev"
	"github.com/docker/docker-agent/pkg/runtime"
	"github.com/docker/docker-agent/pkg/session"
	"github.com/docker/docker-agent/pkg/session/sqlitestore"
	"github.com/docker/docker-agent/pkg/team"
	"github.com/docker/docker-agent/pkg/tools"
	"github.com/stretchr/testify/require"
)

type reviewServerRuntime struct {
	runtime.Runtime
	closeCount atomic.Int32
	follow func(context.Context,runtime.QueuedMessage)error
}

func (*reviewServerRuntime) OnElicitationRequest(func(runtime.Event)){}
func (*reviewServerRuntime) OnBackgroundEvent(func(runtime.Event)){}
func (*reviewServerRuntime) CurrentAgentName(context.Context)string{return "root"}
func (r *reviewServerRuntime) Close() error { r.closeCount.Add(1);return nil }
func (r *reviewServerRuntime) FollowUp(ctx context.Context,msg runtime.QueuedMessage)error {return r.follow(ctx,msg)}

func TestReviewFollowUpPartialBatchRetry(t *testing.T){
	ctx:=t.Context()
	store:=session.NewInMemorySessionStore()
	sess:=session.New()
	require.NoError(t,store.AddSession(ctx,sess))
	q:=runtime.NewInMemoryMessageQueue(1)
	rt:=&reviewServerRuntime{follow:func(ctx context.Context,msg runtime.QueuedMessage)error{
		if !q.Enqueue(ctx,msg){return runtime.ErrFollowUpQueueFull}
		return nil
	}}
	sm:=NewSessionManager(ctx,nil,store,0,&config.RuntimeConfig{})
	sm.AttachRuntime(ctx,sess.ID,rt,sess)
	srv:=httptest.NewServer(NewWithManager(sm,"").e)
	defer srv.Close()
	request:=func(body,key string) int{
		t.Helper()
		req,err:=http.NewRequestWithContext(ctx,http.MethodPost,srv.URL+"/api/sessions/"+sess.ID+"/followup",strings.NewReader(body))
		require.NoError(t,err)
		req.Header.Set("Content-Type","application/json")
		req.Header.Set("Idempotency-Key",key)
		resp,err:=srv.Client().Do(req)
		require.NoError(t,err)
		_,_ = io.Copy(io.Discard,resp.Body)
		_ = resp.Body.Close()
		return resp.StatusCode
	}
	var seen []string
	for range 2{
		require.Equal(t,429,request("{\"messages\":[{\"content\":\"first\"},{\"content\":\"second\"}]}","same-request"))
		m,ok:=q.Dequeue(ctx)
		require.True(t,ok)
		seen=append(seen,m.Content)
	}
	require.Equal(t,[]string{"first","first"},seen)
	require.Equal(t,202,request("{\"messages\":[{\"content\":\"single\"}]}","one"))
	require.Equal(t,202,request("{\"messages\":[{\"content\":\"single\"}]}","one"))
	msg,ok:=q.Dequeue(ctx);require.True(t,ok);require.Equal(t,"single",msg.Content)
	_,ok=q.Dequeue(ctx);require.False(t,ok)
	t.Logf("same two-message request returned 429 twice, queued contents=%v; successful one-message duplicate did not enqueue twice",seen)
}

func TestReviewFollowUpConcurrentAckBeforeFailure(t *testing.T){
	synctest.Test(t,func(t *testing.T){
		store:=session.NewInMemorySessionStore()
		sess:=session.New()
		ctx:=t.Context()
		require.NoError(t,store.AddSession(ctx,sess))
		entered,release:=make(chan struct{}),make(chan struct{})
		fault:=errors.New("fixture did not commit")
		rt:=&reviewServerRuntime{follow:func(context.Context,runtime.QueuedMessage)error{close(entered);<-release;return fault}}
		sm:=NewSessionManager(ctx,nil,store,0,&config.RuntimeConfig{})
		sm.AttachRuntime(ctx,sess.ID,rt,sess)
		messages:=[]api.Message{{Content:"fixture"}}
		first:=make(chan error,1)
		go func(){_,_,e:=sm.FollowUpSession(ctx,sess.ID,messages,"shared");first<-e}()
		<-entered
		_,dup,err:=sm.FollowUpSession(ctx,sess.ID,messages,"shared")
		require.NoError(t,err)
		require.True(t,dup)
		close(release)
		require.ErrorIs(t,<-first,fault)
		t.Log("concurrent retry acknowledged duplicate before original enqueue failed; zero successful enqueue operations")
	})
}

func TestReviewServerOwnedDeleteOmitsRuntimeClose(t *testing.T){
	synctest.Test(t,func(t *testing.T){
		ctx:=t.Context()
		store:=session.NewInMemorySessionStore()
		sess:=session.New()
		require.NoError(t,store.AddSession(ctx,sess))
		rt:=&reviewServerRuntime{}
		sm:=NewSessionManager(ctx,nil,store,0,&config.RuntimeConfig{})
		life,cancel:=context.WithCancel(context.WithoutCancel(ctx))
		defer cancel()
		sm.runtimeSessions.Store(sess.ID,&activeRuntimes{runtime:rt,session:sess,cancel:cancel})
		require.NoError(t,sm.DeleteSession(ctx,sess.ID))
		require.ErrorIs(t,life.Err(),context.Canceled)
		require.NoError(t,sm.WaitStopped(ctx,sess.ID,time.Second))
		_,err:=store.GetSession(ctx,sess.ID)
		require.ErrorIs(t,err,session.ErrNotFound)
		require.Zero(t,rt.closeCount.Load())
		t.Logf("delete cancelled managed turn and removed row; WaitStopped succeeded; runtime Close calls=%d",rt.closeCount.Load())
	})
}

func TestReviewReplacingEventSourceLeavesOldPump(t *testing.T) {
	synctest.Test(t,func(t *testing.T){
		ctx:=t.Context()
		store:=session.NewInMemorySessionStore()
		sess:=session.New()
		require.NoError(t,store.AddSession(ctx,sess))
		sm:=NewSessionManager(ctx,nil,store,0,&config.RuntimeConfig{})
		oldStarted,newStarted:=make(chan struct{}),make(chan struct{})
		oldDone,newDone:=make(chan struct{}),make(chan struct{})
		release:=make(chan struct{})
		defer close(release)
		sm.RegisterEventSource(sess.ID,func(ctx context.Context,send func(any)){
			close(oldStarted)
			defer close(oldDone)
			select{case <-ctx.Done():case <-release:}
		})
		<-oldStarted
		sm.RegisterEventSource(sess.ID,func(ctx context.Context,send func(any)){close(newStarted);<-ctx.Done();close(newDone)})
		<-newStarted
		require.NoError(t,sm.DeleteSession(ctx,sess.ID))
		<-newDone
		synctest.Wait()
		select{case <-oldDone:t.Fatal("replaced source has unexpectedly closed");default:}
		require.False(t,sm.HasEventSource(sess.ID))
		t.Log("replacement pump canceled on delete; original pump remained live until fixture release")
	})
}

type reviewServerModel struct { onInput func([]chat.Message) }
func (reviewServerModel) ID() modelsdev.ID {return modelsdev.NewID("fixture","server")}
func (reviewServerModel) BaseConfig() base.Config{return base.Config{ModelConfig:latest.ModelConfig{Provider:"fixture",Model:"server",ContextWindow:new(int64(4096))}}}
func (m reviewServerModel) CreateChatCompletionStream(_ context.Context,in []chat.Message,_ []tools.Tool)(chat.MessageStream,error){
	m.onInput(in);return new(reviewServerStream),nil
}
type reviewServerStream struct{ done bool }
func (s *reviewServerStream) Recv()(chat.MessageStreamResponse,error){
	if s.done{return chat.MessageStreamResponse{},io.EOF}
	s.done=true
	return chat.MessageStreamResponse{Choices:[]chat.MessageStreamChoice{{Index:0,FinishReason:chat.FinishReasonStop,Delta:chat.MessageDelta{Content:"fixture success"}}}},nil
}
func (*reviewServerStream) Close(){}
type reviewServerStore struct{runtime.ModelStore}
func (reviewServerStore) GetModel(context.Context,modelsdev.ID)(*modelsdev.Model,error){return nil,nil}

func TestReviewBatchUserPersistenceAfterReopen(t *testing.T){
	ctx:=t.Context()
	path:=filepath.Join(t.TempDir(),"store.db")
	store,err:=sqlitestore.New(ctx,path)
	require.NoError(t,err)
	var observed [][]string
	model:=reviewServerModel{onInput:func(ms []chat.Message){
		var users []string
		for _,m:=range ms{if m.Role==chat.MessageRoleUser{users=append(users,m.Content)}}
		observed=append(observed,users)
	}}
	r,err:=runtime.NewLocalRuntime(ctx,team.New(team.WithAgents(agent.New("root","Fixture root",agent.WithModel(model)))),runtime.WithModelStore(reviewServerStore{}),runtime.WithSessionStore(store),runtime.WithSessionCompaction(false))
	require.NoError(t,err)
	s:=session.New(session.WithNonInteractive(true))
	require.NoError(t,store.AddSession(ctx,s))
	sm:=NewSessionManager(ctx,nil,store,0,&config.RuntimeConfig{})
	sm.runtimeSessions.Store(s.ID,&activeRuntimes{runtime:r,session:s})
	for _,batch:=range [][]api.Message{{{Content:"one-message control"}},{{Content:"first in batch"},{Content:"last in batch"}}}{
		events,err:=sm.RunSession(ctx,s.ID,"fixture","root",batch,"")
		require.NoError(t,err)
		for e:=range events{if f,ok:=e.(*runtime.ErrorEvent);ok{t.Fatal(f.Error)}}
	}
	require.Len(t,observed,2)
	require.Equal(t,[]string{"one-message control","first in batch","last in batch"},observed[1])
	var live []string
	for _,m:=range s.GetAllMessages(){if m.Message.Role==chat.MessageRoleUser{live=append(live,m.Message.Content)}}
	require.Equal(t,observed[1],live)
	require.NoError(t,r.Close())
	require.NoError(t,store.Close())
	restored,err:=sqlitestore.New(ctx,path)
	require.NoError(t,err)
	defer restored.Close()
	resumed,err:=restored.GetSession(ctx,s.ID)
	require.NoError(t,err)
	persisted:=[]string{}
	for _,m:=range resumed.GetAllMessages(){if m.Message.Role==chat.MessageRoleUser{persisted=append(persisted,m.Message.Content)}}
	require.Equal(t,[]string{"one-message control","last in batch"},persisted)
	t.Logf("model and live transcript=%v; reopened SQLite=%v",live,persisted)
}

var _ = fmt.Sprint
var _ = slices.Clone[[]string, string]

type reviewBlockingStore struct {
	session.Store
	coldID string
	entered chan struct{}
	release chan struct{}
	failure error
}

func (s *reviewBlockingStore) GetSession(ctx context.Context, id string) (*session.Session, error) {
	if id != s.coldID {
		return s.Store.GetSession(ctx, id)
	}
	close(s.entered)
	<-s.release
	return nil, s.failure
}

func TestReviewColdStoreReadBlocksIndependentWarmRun(t *testing.T) {
	{
		ctx := t.Context()
		store := &reviewBlockingStore{
			Store: session.NewInMemorySessionStore(), coldID: "cold",
			entered: make(chan struct{}), release: make(chan struct{}), failure: errors.New("cold read fixture"),
		}
		sm := NewSessionManager(ctx, nil, store, 0, &config.RuntimeConfig{})
		s := session.New(session.WithID("warm"), session.WithNonInteractive(true))
		require.NoError(t, store.AddSession(ctx, s))
		providerEntered := make(chan struct{}, 2)
		model := reviewServerModel{onInput: func([]chat.Message) { providerEntered <- struct{}{} }}
		r, err := runtime.NewLocalRuntime(ctx, team.New(team.WithAgents(agent.New("root", "Fixture root", agent.WithModel(model)))),
			runtime.WithModelStore(reviewServerStore{}), runtime.WithSessionStore(store), runtime.WithSessionCompaction(false))
		require.NoError(t, err)
		defer r.Close()
		defer func() {
			select {
			case <-store.release:
			default:
				close(store.release)
			}
		}()
		sm.runtimeSessions.Store(s.ID, &activeRuntimes{runtime: r, session: s})
		warmRun := func() error {
			events, err := sm.RunSession(ctx, s.ID, "fixture", "root", []api.Message{{Content: "warm input"}}, "")
			if err == nil {
				for range events {}
			}
			return err
		}
		require.NoError(t, warmRun())
		<-providerEntered
		cold := make(chan error, 1)
		go func() {
			_, err := sm.RunSession(ctx, store.coldID, "fixture", "root", nil, "")
			cold <- err
		}()
		<-store.entered
		if sm.mux.TryLock() {
			sm.mux.Unlock()
			t.Fatal("manager mutex remained free during cold read")
		}
		warm := make(chan error, 1)
		warmIssued := make(chan struct{})
		go func() {
			close(warmIssued)
			warm <- warmRun()
		}()
		<-warmIssued
		select {
		case <-providerEntered:
			close(store.release)
			t.Fatal("warm runtime entered the provider while cold store read was parked")
		case <-time.After(10 * time.Millisecond):
		}
		close(store.release)
		require.ErrorIs(t, <-cold, store.failure)
		require.NoError(t, <-warm)
		<-providerEntered
		t.Log("warm run entered its provider immediately in the control and only after the independent cold read was released in the paired run")
	}
}
```

</details>

<details>
<summary>session_review_test.go</summary>

```go
package session

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
	_ "modernc.org/sqlite"
)

func TestReviewMigrationMarkerAfterDataFailure(t *testing.T) {
	ctx:=t.Context()
	db,err:=sql.Open("sqlite",filepath.Join(t.TempDir(),"marker.db"))
	require.NoError(t,err)
	defer db.Close()
	fault:=errors.New("injected UpFunc error")
	calls:=0
	migrations:=[]Migration{{
		ID:1,Name:"fixture",UpSQL:"CREATE TABLE fixture_payload (val TEXT)",
		UpFunc:func(ctx context.Context, db *sql.DB) error {
			calls++
			if calls==1{return fault}
			_,err:=db.ExecContext(ctx,"INSERT INTO fixture_payload(val) VALUES ('expected')")
			return err
		},
	}}
	require.ErrorIs(t,NewMigrationManagerWithMigrations(db,migrations).InitializeMigrations(ctx),fault)
	require.NoError(t,NewMigrationManagerWithMigrations(db,migrations).InitializeMigrations(ctx))
	var marker,payload int
	require.NoError(t,db.QueryRow("SELECT count(*) FROM migrations").Scan(&marker))
	require.NoError(t,db.QueryRow("SELECT count(*) FROM fixture_payload").Scan(&payload))
	require.Equal(t,1,marker)
	require.Equal(t,1,calls)
	require.Zero(t,payload)
	t.Logf("first open returned injected error; marker=%d second open success; UpFunc calls=%d payload rows=%d",marker,calls,payload)
}

func TestReviewLegacyMigrationPartiallyCopiesRows(t *testing.T) {
	ctx:=t.Context()
	path:=filepath.Join(t.TempDir(),"legacy.db")
	db,err:=sql.Open("sqlite",path)
	require.NoError(t,err)
	db.SetMaxOpenConns(1)
	defer db.Close()
	_,err=db.Exec(`CREATE TABLE sessions (
		id TEXT PRIMARY KEY,
		messages TEXT,
		created_at DATETIME DEFAULT CURRENT_TIMESTAMP
	)`)
	require.NoError(t,err)
	require.NoError(t,NewMigrationManagerWithMigrations(db,getAllMigrations()[:14]).InitializeMigrations(ctx))
	two:=[]Item{NewMessageItem(UserMessage("first fixture item")),NewMessageItem(UserMessage("second fixture item"))}
	items,err:=json.Marshal(two)
	require.NoError(t,err)
	for _,id:=range []string{"affected","control"} {
		_,err=db.Exec("INSERT INTO sessions(id,messages,created_at) VALUES (?,?,?)",id,string(items),"2026-11-19T12:00:00Z")
		require.NoError(t,err)
	}
	_,err=db.Exec(`CREATE TRIGGER second_item_fails BEFORE INSERT ON session_items
	 WHEN NEW.session_id='affected' AND NEW.position=1
	 BEGIN SELECT RAISE(FAIL, 'fixture obstruction'); END`)
	require.NoError(t,err)
	require.NoError(t,NewMigrationManagerWithMigrations(db,getAllMigrations()[:15]).InitializeMigrations(ctx))
	var legacy string
	require.NoError(t,db.QueryRow("SELECT messages FROM sessions WHERE id='affected'").Scan(&legacy))
	require.JSONEq(t,string(items),legacy)
	var marker int
	require.NoError(t,db.QueryRow("SELECT count(*) FROM migrations WHERE id=15").Scan(&marker))
	require.Equal(t,1,marker)
	_,err=db.Exec("DROP TRIGGER second_item_fails")
	require.NoError(t,err)
	require.NoError(t,db.Close())
	db2,err:=sql.Open("sqlite",path)
	require.NoError(t,err)
	defer db2.Close()
	restored,err:=NewSQLiteSessionStoreFromDB(ctx,db2)
	require.NoError(t,err)
	defer restored.Close()
	a,err:=restored.GetSession(ctx,"affected")
	require.NoError(t,err)
	b,err:=restored.GetSession(ctx,"control")
	require.NoError(t,err)
	require.Equal(t,1,a.OwnMessageCount())
	require.Equal(t,2,b.OwnMessageCount())
	var original string
	require.ErrorContains(t,db2.QueryRow("SELECT messages FROM sessions WHERE id='affected'").Scan(&original),"no such column")
	t.Logf("built-in migration #15 marked applied; reopened affected=%d control=%d, the later migration dropped the original legacy JSON column",a.OwnMessageCount(),b.OwnMessageCount())
}
```

</details>

<details>
<summary>jobs_review_test.go</summary>

```go
package backgroundjobs

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/docker/docker-agent/pkg/config"
	"github.com/docker/docker-agent/pkg/tools"
	"github.com/stretchr/testify/require"
)

func TestReviewStopDirectChildWithSurvivingDescendant(t *testing.T){
	for _,stubborn:=range []bool{false,true}{
		t.Run(fmt.Sprint(stubborn),func(t *testing.T){
			ctx:=t.Context()
			dir:=t.TempDir()
			ts:=New(os.Environ(),&config.RuntimeConfig{Config:config.Config{WorkingDir:dir}})
			ts.handler.shell="/bin/sh"
			ts.handler.shellArgsPrefix=[]string{"-c"}
			prefix:=""
			if stubborn{prefix=`trap '' TERM; `}
			cmd:=fmt.Sprintf("sh -c '%sexec sleep 20' </dev/null >/dev/null 2>&1 & printf '%%s' \"$!\" > child.pid; wait",strings.ReplaceAll(prefix,"'","'\\''"))
			result,err:=ts.handler.RunBackgroundJob(ctx,RunBackgroundJobArgs{Cmd:cmd},tools.NopRuntime{})
			require.NoError(t,err)
			require.False(t,result.IsError)
			var job *backgroundJob
			ts.handler.jobs.Range(func(_ string,j *backgroundJob)bool{job=j;return false})
			require.NotNil(t,job)
			pidfile:=filepath.Join(dir,"child.pid")
			var pid int
			require.Eventually(t,func()bool{
				b,err:=os.ReadFile(pidfile)
				if err!=nil{return false}
				pid,err=strconv.Atoi(string(b))
				if err!=nil || pid<2{return false}
				stat,err:=os.ReadFile(fmt.Sprintf("/proc/%d/comm",pid))
				return err==nil && strings.TrimSpace(string(stat))=="sleep"
			},3*time.Second,5*time.Millisecond)
			defer syscall.Kill(pid,syscall.SIGKILL)
			pgid,err:=syscall.Getpgid(pid)
			require.NoError(t,err)
			require.Equal(t,job.process.Pid,pgid)
			result,err=ts.handler.StopBackgroundJob(ctx,StopBackgroundJobArgs{JobID:job.id})
			require.NoError(t,err)
			require.False(t,result.IsError)
			select{case <-job.done: default:t.Fatal("job not joined")}
			running:=func()bool{
				b,err:=os.ReadFile(fmt.Sprintf("/proc/%d/stat",pid))
				if err!=nil{return false}
				text:=string(b); end:=strings.LastIndex(text,") ")
				return end>=0 && text[end+2]!='Z' && text[end+2]!='X'
			}
			if stubborn{
				require.True(t,running())
				require.NoError(t,ts.Stop(ctx))
				require.True(t,running())
			}else{require.Eventually(t,func()bool{return !running()},time.Second,time.Millisecond)}
			t.Logf("ignores TERM=%t stop returned success, direct child joined, same process group descendant alive=%t",stubborn,running())
		})
	}
}
```

</details>

<details>
<summary>shims/atomic/atomic.go</summary>

```go
package atomic

import (
	"io"
	"os"
	"path/filepath"
)

func WriteFile(path string, input io.Reader) error {
	file, err := os.CreateTemp(filepath.Dir(path), ".test-atomic-")
	if err != nil {
		return err
	}
	defer os.Remove(file.Name())
	_, err = io.Copy(file, input)
	if err != nil {
		_ = file.Close()
		return err
	}
	if err = file.Sync(); err != nil {
		_ = file.Close()
		return err
	}
	if err = file.Close(); err != nil {
		return err
	}
	return os.Rename(file.Name(), path)
}
```

</details>

<details>
<summary>shims/aijson/aijson.go</summary>

```go
package aijson

import "encoding/json"

type Kind string
type Opt func()
const KindWrapInArray Kind = "wrap_in_array"
func OnRepair(_ func([]Kind)) Opt { return func() {} }
func Unmarshal(data []byte, out any, _ ...Opt) error { return json.Unmarshal(data, out) }
```

</details>

<details>
<summary>shims/keepawake/keepawake.go</summary>

```go
package keepawake

import "context"

func Acquire(context.Context) (func() error, error) {
	return func() error { return nil }, nil
}
```

</details>

<details>
<summary>shims/portcullis/portcullis.go</summary>

```go
package portcullis

const Marker = "[redacted]"
func Redact(s string) string { return s }
func Contains(string) bool { return false }
```

</details>

## 10. Prioritized improvements.

1. **P0. Give each invocation a conversation identity and an owner for its input.** Store the resolved agent and queue key on the invocation and pass them into children, hooks, routing, and continuation. Synchronous transfers can then run independently in a dispatcher batch with stable permission and provider selection. Keep root steering and follow-up delivery scoped to the submitted conversation. Acceptance requires the gated transfer and root-input controls in section 6 to assert correct identity and exactly one addressed delivery, including a same-workspace child.
2. **P0. Make input acceptance and persistence one explicit commit.** Persist the ordered submitted batch before advancing the provider state. Reserve all queue capacity or reject the bulk request before publishing anything. Associate idempotency keys with pending and committed outcomes. A same-key retry should join the pending result or get an explicit pending answer. Decide whether the receipt is process-local or durable and document its lifetime. Acceptance includes a capacity-one bulk request, overlapping same-key retries, request cancellation between admission and commit, and SQLite reopen with every accepted input preserved.
3. **P0. Make migration payload and version advance together.** Use a single transaction for each built-in schema/data migration whose marker represents completion. For large migrations, use durable checkpoints with row counts and resumable batches. Aggregate/report failed rows and protect the legacy column until verification. Acceptance requires injected item and callback failures, reopen/retry, and an intact source backup until a complete result.
4. **P1. Retire and join every owner the service creates.** Give managed runtimes and event pumps an explicit owned handle with generation and join semantics. Remove admission before joining. Keep embedder-owned handles separate. Require the tool supervisor's replaced generation to install a watcher atomically with retirement, and make explicit shell job Stop report process-tree cleanup separately from direct-child exit. Acceptance includes server delete with a detached child, source replacement, restart within the failure callback, and a TERM-resistant descendant.
5. **P1. Recover board transitions using a retryable operation.** Persist a desired stage and associated delivery receipt as one board state update. Reconcile after startup or lost acknowledgement with the same operation ID. Publish memory after a successful save and derive current activity from a snapshot plus a cursor, with re-snapshot after a gap. Acceptance includes write failure before rename, restart after save and before follow-up, a 503 retry, stale pane state and the streaming replay control.
6. **P2. Allocate capacity before dispatch and decouple cancel from slow consumers.** Coordinate cold initialization with a per-session reservation and publish a fully constructed result in one step. Add session and team resource budgets for concurrent model calls, tool executions, watchers and output. Document which limits are reservations or advisory. Carry a typed budget stop through background results. Give downstream adapters a defined drain or drop policy for typed events and a cancellation path with bounded observer cleanup. Acceptance includes a blocked cold store read with independent warm progress, simultaneous admissions near quota, an undrained consumer and a slow observer, with no loss of essential terminal or persistence events.
7. **P2. Shrink the minimum offline test graph and improve recovery telemetry.** Maintain a native core suite with fake providers and no integrations in its test setup. Provide a versioned dependency cache for release verification. Attach operation and generation IDs to queue acceptance, provider attempts, persistence failures, snapshots and shutdown outcomes so a report can distinguish failure to start, failure to commit and incomplete drain. Repeat filesystem tests on Btrfs and tmpfs and make plan listing's concurrent snapshot semantics explicit.
