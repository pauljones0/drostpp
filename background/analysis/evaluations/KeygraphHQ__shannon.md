# Shannon local architecture and reliability evaluation

## 1. Snapshot, scope, and elapsed-time evidence

| Item | Evidence |
| --- | --- |
| Repository | KeygraphHQ/shannon, local source checkout |
| Pinned revision | `c20e119ac2220d17013b73526ea460e32efc30da` |
| Commit | `docs: add UTM tags to keygraph.io links (#491)`, author date `2026-11-16T13:59:01-08:00` |
| Start | `2026-11-19T06:47:21Z`. HEAD matched. Porcelain status and both staged and unstaged diffs were empty. |
| Checkpoints | `06:49:34Z` snapshot and state inventory, `06:51:32Z` filesystem and runtime guard controls, `06:52:49Z` worker and stop paths, `06:55:01Z` persistence and audit paths, `06:56:24Z` provider and audit interfaces, `06:58:46Z` resume and cancellation integration path, `07:02:20Z` audit and artifact proof checks, `07:06:38Z` transport and trace controls, `07:08:21Z` appendix re-run, `07:09:17Z` inode and interleaving diagnosis, `07:13:29Z` cross-runtime reproduction, `07:14:17Z` ten-block appendix and anchor validation, `07:14:56Z` alternate syntax check, `07:15:45Z` complete report structure check and final launch-clock control, `07:16:47Z` predecessor accounting replay check. |
| End | `2026-11-19T07:17:32Z`. 30 minutes 11 seconds elapsed. HEAD remained `c20e119ac2220d17013b73526ea460e32efc30da`. Porcelain status was empty, including ignored and untracked entries. Staged and unstaged diff checks both exited zero. |
| Files | This report is the only retained review artifact. Test fixtures were disposable directories under the review workspace. |

This evaluation covers launch ownership, workflow and activity boundaries, cooperative and forced shutdown, record and report integrity, filesystem confinement, observability, and extension contracts. The active testing pipeline is represented at the control-plane level. Experiments used inert synthetic inputs, local files and Git repositories, and fake clocks or dependency boundaries where necessary. No application target, model account, credential store, network service, Docker daemon, or running Temporal instance was exercised. GUI and frontend presentation were outside scope. Shannon identifies itself as an autonomous pentester and documents the potential for external side effects, which is why the executable coverage is limited to defensive controls and infrastructure. [CLI package purpose](repos/KeygraphHQ__shannon/apps/cli/package.json:2), [Safety and limitations](repos/KeygraphHQ__shannon/docs/safety.md:5)

**Overall assessment.** Shannon has a clear execution split and unusually explicit report-proof and shutdown contracts for a local tool. Its most important weakness is that the workspace is a durable shared resource whose writes assume one live owner, while queue ownership and startup records identify individual invocations. A second weakness is that the final proof covers immutable Git blobs, while the customer-copy step reads mutable paths. The controls below distinguish these seams from ordinary same-worker concurrency, which generally behaves correctly in isolation.

## 2. Core architecture and end-to-end control/data flow

1. **Launch and identity.** The CLI classifies the workspace from the launch and session records, checks that a resume agrees with the target and output route, and chooses a workspace name, workflow ID, worker container name, and task queue. It installs a queue-specific launch candidate before handing work to Docker. The worker's labels carry the workspace, queue, and workflow ID. A durable session entry matching the exact invocation acknowledges handoff and allows the CLI to remove the pending candidate. A workspace therefore groups executions, while the workflow ID identifies one execution. [Workspace classification](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:168), [Launch identity selection](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:356), [Pending handoff](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:405), [Registration poll](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:499), [Worker labels](repos/KeygraphHQ__shannon/apps/cli/src/docker.ts:424)

2. **Worker and orchestration.** The detached worker combines a Temporal client and poller. It validates startup configuration, binds its activity registry to the mounted resources, polls its own queue, starts the workflow on that queue, and waits for its result. The local Temporal service persists server state in a mounted database. The process then shuts down the worker and closes the connections on the normal path. Queue affinity limits cross-invocation dispatch, while the workspace remains a separate persistence boundary. [Temporal worker creation](repos/KeygraphHQ__shannon/apps/worker/src/temporal/worker.ts:724), [Worker result and shutdown](repos/KeygraphHQ__shannon/apps/worker/src/temporal/worker.ts:774), [Persistent service configuration](repos/KeygraphHQ__shannon/docker-compose.yml:5)

3. **Planning and work lifecycle.** The top-level workflow owns phase ordering and fan-in. The ordinary activity registry exposes named units of work, and an optional child workflow has its own typed activity family and sends progress back to the parent. Agent metadata documents prerequisites. The actual dependencies and barriers are encoded in the workflow. Work execution, provider calls, files, and Git all sit behind activities or the child boundary. An activity receives its attempt identity, heartbeats while work is active, uses per-attempt audit context, forwards cancellation, and returns typed metrics and optional checkpoint metadata. [Workflow isolation](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:7), [Workflow state and progress](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:381), [Workflow phases and join](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:1393), [Agent catalog contract](repos/KeygraphHQ__shannon/apps/worker/src/session-manager.ts:13), [Activity lifecycle](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:393), [Child activity registration](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/temporal/registry.ts:19)

4. **Persisted state and re-entry.** Temporal history reconstructs workflow state within an execution. For a new execution of an existing workspace, the worker checks saved policy, registers a resume identity, and compares durable state, metrics, and on-disk checkpoint evidence. It restores the selected deliverables checkpoint and then marks validated units complete in the new workflow. A previously authored, coherent report carries its own progress and durable reason set. A workspace without a usable checkpoint can be rejected even if it has a session record. [Workflow resume entry](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:1292), [Checkpoint restoration call](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:1318), [Resume state scoring](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1598), [No-checkpoint boundary](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1696), [Resume registration order](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1907)

5. **Outputs and completion.** The report moves through pending, draft, and finalized forms. JSON and Markdown plus the optional machine artifact are validated against an exact Git commit and a manifest. The persisted final state couples that checkpoint and digest to the terminal record. The derived PDF has a separate provenance token. The workflow tries customer copies after terminal proof. Optional publication failures produce warnings. A terminal summary then persists audit totals and clears the process-local container entry on the activity's success path. [Report progress type](repos/KeygraphHQ__shannon/apps/worker/src/types/run-state.ts:796), [Finalization and adoption](repos/KeygraphHQ__shannon/apps/worker/src/services/report-finalization.ts:330), [Proof before terminal promotion](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1374), [Surface phase and warnings](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:1272), [Terminal audit and cleanup](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1957)

6. **Stop and observability.** The CLI assembles a stop target set from persisted launch records, session identity, worker labels, and visible workflows. It tries cooperative closure while a worker can still acknowledge it, escalates if closure cannot be established, stops captured containers, and verifies again. Status uses Temporal pending activity descriptions and the workflow's progress query. The audit log and JSON ledger serve independent forensic and accounting purposes and can outlive the server's execution record. [Stop target union](repos/KeygraphHQ__shannon/apps/cli/src/commands/stop.ts:294), [Stop verification](repos/KeygraphHQ__shannon/apps/cli/src/commands/stop.ts:381), [Progress query and task descriptions](repos/KeygraphHQ__shannon/apps/cli/src/temporal-client.ts:215), [Terminal outcome reader](repos/KeygraphHQ__shannon/apps/cli/src/temporal-client.ts:381), [Unified log writer](repos/KeygraphHQ__shannon/apps/worker/src/audit/workflow-logger.ts:202)

| Boundary | What it owns | Persistence and lifetime |
| --- | --- | --- |
| CLI | Launch policy, candidate identity, initial status acknowledgement | `launch.json` and queue-specific pending files under the stable workspace |
| Temporal service | Workflow existence, history, scheduled command and activity disposition | Server database volume |
| Worker process | Model sessions, activity execution, leases, dependency instances | Process-local. A new invocation has its own queue and process. |
| Audit facade | Stable workspace state, attempt metrics, resume and terminal records | `session.json` and `workflow.log`. Agent logs are projections. |
| Deliverables storage | Committed report proof, intermediate files, structured artifact references | Workspace-backed Git repository and per-workspace files. Optional customer outputs are derived copies. |

[CLI pending record](repos/KeygraphHQ__shannon/apps/cli/src/pending-workflow.ts:39), [Service volume](repos/KeygraphHQ__shannon/docker-compose.yml:9), [Worker container scope](repos/KeygraphHQ__shannon/apps/worker/src/services/container.ts:48), [Workspace paths](repos/KeygraphHQ__shannon/apps/worker/src/audit/utils.ts:38), [Artifact lookup model](repos/KeygraphHQ__shannon/apps/worker/src/ai/reconciliation/artifact-store.ts:459)

## 3. Why the design works and its governing invariants

- **Workflow decisions and side effects have different kinds of state.** The workflow registers a query over local state and uses named activity or child contracts to leave the deterministic execution context. This places a checkpoint boundary between a decision and its effects. A stopped client or lost acknowledgement can be reasoned about independently of a completed file write. Current-release history compatibility still depends on matching APIs and command shape. [Workflow determinism contract](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:7), [Query setup](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:437), [Historical activity names](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/temporal/activity-types.ts:215)
- **An identity handshake precedes external side effects.** For the ordinary launch path, the CLI journals a candidate before spawning the detached worker and the progress poll accepts only a matching registration. For graceful resume, the audit marker is written before the new workflow ID entry. The handoff makes a registered run discoverable independently of the lifetime of the launching CLI. The intended identity check is stronger than the timeout fallback, as shown in section 4. [Pending workflow installation](repos/KeygraphHQ__shannon/apps/cli/src/pending-workflow.ts:39), [Launcher registration handshake](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:499), [Resume boundary ordering](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1903)
- **Closure needs positive evidence.** A stop RPC receipt confirms the request. Direct status supplies closure evidence. An RPC failure or unknown state keeps the result unverified, with a renewed connection opportunity for escalation. Visibility contributes candidates. The shutdown plan separately observes that captured workers exited and looks for work that appeared during the stop window. [Lifecycle status and deadlines](repos/KeygraphHQ__shannon/apps/cli/src/temporal-client.ts:140), [Cancel and terminate verification](repos/KeygraphHQ__shannon/apps/cli/src/commands/stop.ts:159), [Late registration reconciliation](repos/KeygraphHQ__shannon/apps/cli/src/commands/stop.ts:377), [Shutdown success predicate](repos/KeygraphHQ__shannon/apps/cli/src/commands/stop.ts:616)
- **The single-process state writer pairs a lock with a fresh read.** Independent audit instances protect their own logging context. For ordinary state updates they reload inside the session-keyed mutex, apply one change, and publish the replacement file. This prevents stale in-memory objects from losing a sibling update when the worker shares one process. A process boundary and the pre-lock initialization path lie outside this guarantee. [Per-agent audit ownership](repos/KeygraphHQ__shannon/apps/worker/src/audit/audit-session.ts:43), [Reload and persist](repos/KeygraphHQ__shannon/apps/worker/src/audit/audit-session.ts:157), [FIFO mutex](repos/KeygraphHQ__shannon/apps/worker/src/utils/concurrency.ts:35), [Initial metrics creation](repos/KeygraphHQ__shannon/apps/worker/src/audit/metrics-tracker.ts:212)
- **Artifact proof precedes terminal promotion.** Canonical Git outputs use path-scoped commit mechanics and semantic validation. The proof checks ancestry, reachability, exact manifest serialization, and artifact hashes. Partial reasons are append-only and project from typed records. The report agent's ordinary success path cannot bypass terminal proof. Re-drive may adopt previously published bytes without a second commit. [Draft and terminal verification](repos/KeygraphHQ__shannon/apps/worker/src/services/report-checkpoints.ts:146), [Exact publication](repos/KeygraphHQ__shannon/apps/worker/src/services/exact-output-commit.ts:234), [Report success guard](repos/KeygraphHQ__shannon/apps/worker/src/audit/metrics-tracker.ts:291), [Partial reason set](repos/KeygraphHQ__shannon/apps/worker/src/types/run-state.ts:485)
- **Some state has a stronger restart contract than other state.** The intermediate artifact store installs exact bytes with a unique temporary file, file sync, an exclusive link, and a directory sync when supported. Readback recomputes the expected path and digest and checks metadata and ordered inputs. Operational metrics are upserted by workflow ID. Human-readable trace lines are diagnostic and selectively flushed. These distinct policies make sense for the respective artifacts, provided operators can see their different failure modes. [Content-addressed publication](repos/KeygraphHQ__shannon/apps/worker/src/ai/reconciliation/artifact-store.ts:299), [Artifact ref verification](repos/KeygraphHQ__shannon/apps/worker/src/ai/reconciliation/artifact-store.ts:458), [Terminal metric upsert](repos/KeygraphHQ__shannon/apps/worker/src/audit/metrics-tracker.ts:661), [Log flush policy](repos/KeygraphHQ__shannon/apps/worker/src/audit/workflow-logger.ts:233)
- **Confinement is a specific tool contract.** The read-only repository view combines lexical containment, target resolution, deny checks, descriptor identity checks, and resource budgets. It provides bounded errors without echoing host paths. The main Docker mount is read-only with explicit writable overlays. Broader worker filesystem and process isolation has a separate trust boundary. [Repository path validation](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/tools/confinement.ts:237), [Read identity and bounds](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/tools/confinement.ts:325), [Docker mount policy](repos/KeygraphHQ__shannon/apps/cli/src/docker.ts:453)

## 4. What it does well and poorly, with source evidence

| Strength | Source and observed behavior |
| --- | --- |
| Recoverable launch identity | The pending file uses an exclusive linked destination and syncs before spawn. A second writer for the same queue receives `EEXIST`. The actual reader distinguishes a missing directory from malformed state and preserves two valid independent candidates. [Pending create and sync](repos/KeygraphHQ__shannon/apps/cli/src/pending-workflow.ts:39), [Pending read validation](repos/KeygraphHQ__shannon/apps/cli/src/pending-workflow.ts:83) |
| Stop distinguishes intent, acknowledgement, and result | Fake-clock controls confirmed graceful and forced closure, delayed registration discovery, lost acknowledgement, unknown state, and a second worker appearing while stopping a captured worker. A stale visibility row alone cannot turn a failed direct request into proof of closure. [Cancel and verify](repos/KeygraphHQ__shannon/apps/cli/src/commands/stop.ts:191), [Container verification](repos/KeygraphHQ__shannon/apps/cli/src/commands/stop.ts:254), [Candidate closeout](repos/KeygraphHQ__shannon/apps/cli/src/commands/stop.ts:406) |
| Most normal writes have explicit ownership | Three concurrent operations through separate audit sessions preserved all three metric entries. Parallel holders of one log stream maintained write order and had independent close lifetimes. The scratch Git fixture preserved staged and unstaged sibling edits across publication, retry, and deletion. [Audit commit mutex](repos/KeygraphHQ__shannon/apps/worker/src/audit/audit-session.ts:160), [Queue and reference lifetime](repos/KeygraphHQ__shannon/apps/worker/src/audit/log-stream.ts:75), [Git scoped write and repair](repos/KeygraphHQ__shannon/apps/worker/src/services/exact-output-commit.ts:119) |
| Strong proof and artifact recovery | Exact report state survived a simulated error after the commit. Retrying adopted the already committed version and repaired owned paths. A wrong final manifest digest failed proof. Twenty same-content intermediate writes converged on one path and corrupted bytes failed verification. [Exact lost-ack adoption](repos/KeygraphHQ__shannon/apps/worker/src/services/exact-output-commit.ts:234), [Final proof](repos/KeygraphHQ__shannon/apps/worker/src/services/report-checkpoints.ts:178), [Artifact conflict policy](repos/KeygraphHQ__shannon/apps/worker/src/ai/reconciliation/artifact-store.ts:334) |
| Useful separation of different time and cost measurements | Group timing merges overlapping intervals and separates time from priced usage. Unknown cost remains distinct in the pure view, and incomplete cumulative accounting is explicitly modeled. A set-over-integer-time oracle agreed on 10,000 generated cases. [Intervals and cost](repos/KeygraphHQ__shannon/apps/worker/src/audit/operational-summary.ts:62), [Workflow usage flag](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:413), [Audit summary representation](repos/KeygraphHQ__shannon/apps/worker/src/temporal/summary-mapper.ts:60) |

**High priority — workspace ownership and startup evidence.** Invocation identity is narrower than workspace ownership. Fresh classification occurs before an awaited infrastructure setup. Workspace directories are created with recursive calls, and `launch.json` is installed with a replacing rename. Two callers can both qualify as fresh before either publication. Direct re-publication changed the route. Two actual CLI callers driven through a mocked infrastructure barrier then reached separate synthetic detachers with different routes, and the later route replaced the first in the shared file. A frozen-clock repeat yielded distinct task queues and the same workflow ID. The workflow ID uses the workspace and millisecond timestamp. For resume, the worker enumerates previously recorded IDs and logs errors during termination without refusing the new run. The impact of overlapping live worker writes is inferred from the mocked handoff and the independent file primitive controls. No live workers were started. Independently, a completed prior session qualified as `scan-running` in the timeout fallback despite no matching resume registration. The ordinary poll has the exact ID check that the fallback omits. [Check-before-await boundary](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:304), [Await then workspace writes](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:348), [Replacing launch rename](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:233), [Best-effort predecessor termination](repos/KeygraphHQ__shannon/apps/worker/src/temporal/worker.ts:405), [Exact acknowledgement predicate](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:499), [Startup timeout fallback](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:547) [Workflow ID derivation](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:268)

**High priority — customer artifact identity can differ from terminal proof.** Final verification reads committed Markdown and checks its digest. The surfacing activity then passes the deliverables directory to a helper that reads working files. An ordinary post-commit edit in a fixture was copied to the customer path while the immutable proof remained valid. The comparison copy verifies the bytes it read, so it enforces copy integrity for the chosen working bytes. The customer destination has no comparison against the committed digest. For committed SARIF, the structure is analogous by source inspection. For absent SARIF the proof explicitly checks its absence in the working directory. Derived PDF has an additional file/digest check and a separate helper. Severity depends on whether operators or other processes modify deliverables between finalization and publication. [Committed proof](repos/KeygraphHQ__shannon/apps/worker/src/services/report-checkpoints.ts:185), [Production surface adapter](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1427), [Copy input and readback](repos/KeygraphHQ__shannon/apps/worker/src/services/report-output-surface.ts:53), [Output policy and loop](repos/KeygraphHQ__shannon/apps/worker/src/services/report-output-surface.ts:149)

**High priority — the JSON durability primitive assumes writer exclusion.** With six parallel writers to one destination, 150 of 180 writes failed with `ENOENT` over 30 trials. Sequential, distinct-target, and session-mutex cases had zero failures. The first run ended with valid submitted values. Appendix re-runs observed one and five invalid final values respectively. A native 40-trial size control observed six at 512 KiB and none at 64 B or 64 KiB. A controlled interleaving proved that the successful rename publishes the same inode a competing writer still has open. That writer subsequently changes the final file even though its own rename fails. Six independent fresh trackers on the same file had 80 rejected writes over 16 trials. The default workflow initializes before normal parallel phases. Competing initializers, independent processes, and any callers without exclusion are the exposure. The generic write also lacks file and directory sync, so successful fixture writes provide no power-loss guarantee. [Shared temporary pathname](repos/KeygraphHQ__shannon/apps/worker/src/utils/file-io.ts:30), [Tracker check-then-create](repos/KeygraphHQ__shannon/apps/worker/src/audit/metrics-tracker.ts:207), [Audit init relative to lock](repos/KeygraphHQ__shannon/apps/worker/src/audit/audit-session.ts:208), [First workflow activity](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:1292)

**Medium priority — accounting and lifecycle views can misstate outcomes.** Replaying one already-recorded ordinary audit attempt with the same fields appended a second row and added its cost a second time. Terminal workflow-level metrics upserted correctly. This measures one duplicate accounting callback. Actual provider billing was outside the fixture. Separately, the CLI progress projector reported synthetic `PAUSED` as failed and normalized the raw status to `UNKNOWN`, although the stop client explicitly considers it open. The CLI snapshot branches into a result read for that state. The actual JSON command requested a terminal result in a client shim. Behaviour against a real paused execution remained unmeasured. [Attempt append and summation](repos/KeygraphHQ__shannon/apps/worker/src/audit/metrics-tracker.ts:956), [Run-level upsert](repos/KeygraphHQ__shannon/apps/worker/src/audit/metrics-tracker.ts:661), [Stop lifecycle state](repos/KeygraphHQ__shannon/apps/cli/src/temporal-client.ts:156), [Status branching](repos/KeygraphHQ__shannon/apps/cli/src/commands/status.ts:35), [JSON state derivation](repos/KeygraphHQ__shannon/apps/cli/src/scan/status-json.ts:53)

**Medium priority — resume and stop still have failure-handling gaps.** A stepped commit clock caused the exact resume selection command to choose an ancestor. Injected missing-object and transient-I/O outcomes both caused the restore function to return successfully before reset, leaving the surrounding workflow free to adopt prior completions. In another fixture a deliberately unwritable audit log prevented a resume marker, while the new workflow ID still persisted. The next successful write repaired the boundary after permissions were restored. In a separate tail control, the predecessor terminal marker ended the tail before checking a supplied resume workflow ID. In the stop path, positively terminal candidates each replayed a full settling interval in fake time. [Checkpoint selection](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1773), [Restore verification catch](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1852), [Resume state handoff](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:1322), [Resume identity publication](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1907), [Best-effort log wrapper](repos/KeygraphHQ__shannon/apps/worker/src/audit/workflow-logger.ts:534), [Serial stop settlement](repos/KeygraphHQ__shannon/apps/cli/src/commands/stop.ts:406)

**Medium priority — the audit and worker boundaries expose more than their safe structural fields suggest.** The URL headline keeps only its origin, and structured error projections use fixed messages. The tool trace intentionally records complete argument JSON in the canonical and projected log files. Both received an inert confidential marker in the fixture, and an explicit umask of 022 gave both log files mode 0644. These are sensitive operational records and require filesystem and retention protection. The worker also receives the broader workspace mount and a container-wide relaxed seccomp profile, and it hands positional values through a shell command string when dropping privileges. Argument preservation, narrower mount access, and ownership controls are defensively valuable. The review did not exercise abuse of any of these boundaries. [Safe origin and error projection](repos/KeygraphHQ__shannon/apps/worker/src/audit/safe-fields.ts:100), [Whole argument capture](repos/KeygraphHQ__shannon/apps/worker/src/audit/trace.ts:77), [Canonical and projected writes](repos/KeygraphHQ__shannon/apps/worker/src/audit/workflow-logger.ts:258), [Mounts and seccomp](repos/KeygraphHQ__shannon/apps/cli/src/docker.ts:453), [Entrypoint privilege drop](repos/KeygraphHQ__shannon/entrypoint.sh:18)

**Medium priority — input identity and optional artifact adoption have separate gaps.** The static-analysis artifact key includes the Git HEAD identity, while the reader sees live mounted working files. A benign uncommitted edit changed the observed bytes under the same key. The production PDF adapter also discards provenance if the internal PDF path fails its current-file check, so a previously verified customer copy can be removed when only the internal PDF is missing. Passing the still-valid provenance to the helper directly preserved that customer's bytes in the isolated fixture. The PDF case is a source-matched adapter predicate test. [Git-derived fingerprint](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/artifacts.ts:82), [Repository data source](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/tools/confinement.ts:325), [Provenance passed to the helper](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1449), [Customer PDF digest and retention](repos/KeygraphHQ__shannon/apps/worker/src/services/report-output-surface.ts:128)

**Lower priority — compatibility contracts drift at build and Git boundaries.** All 54 checked-in worker activity names matched the CLI read model. Of 28 worker export paths, 27 had the expected TypeScript source. The remaining export points to a file absent from the pinned tree and has no alternate source or generation step in the package script. The CLI manifest advertises Node 18, while its direct file-watcher dependency in the lockfile declares Node 20.19 or later. This is a metadata mismatch. An actual published build on Node 18 was unavailable. The Git text reader also strips a leading UTF-8 BOM with its default decoder despite describing byte fidelity, and a missing revision produces a retryable unknown classification on this Git version. These concerns have narrower reach than the ownership and publication risks. [Worker export and build script](repos/KeygraphHQ__shannon/apps/worker/package.json:6), [CLI engines](repos/KeygraphHQ__shannon/apps/cli/package.json:49), [File-watcher lock entry](repos/KeygraphHQ__shannon/pnpm-lock.yaml:996), [Git byte reader](repos/KeygraphHQ__shannon/apps/worker/src/services/git-manager.ts:595), [Git failure mapping](repos/KeygraphHQ__shannon/apps/worker/src/services/git-manager.ts:625), [Checkpoint revision resolution](repos/KeygraphHQ__shannon/apps/worker/src/services/report-checkpoints.ts:80)

## 5. Core-code quality: decomposition, state, concurrency, errors, types, tests, observability, extensibility, and maintainability

| Dimension | Evaluation |
| --- | --- |
| Decomposition | Temporal workflow, activity adapter, execution service, audit facade, and artifact stores have understandable ownership. The central workflow also holds policy, state projection, report transitions, and terminal handling in one module. The resume contract is easier to reason about at file and identity boundaries than by following each branch of that module. [Central workflow](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:361), [Activity execution boundary](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:402), [Service input contract](repos/KeygraphHQ__shannon/apps/worker/src/services/agent-execution.ts:44) |
| State model | Discriminated report states, checked schema versions, and explicit partial reasons make illegal transitions visible. The CLI has a second validator for a subset of the durable record. The complete worker validator still runs later, so the two checks can disagree on a structurally damaged record. An early CLI check is useful for operator feedback but should share the same versioned boundary when the result authorizes a workspace handoff. [CLI durable-state twin](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:92), [Worker durable-state validation](repos/KeygraphHQ__shannon/apps/worker/src/types/run-state.ts:1015), [Terminal conflict check](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1385) |
| Concurrency and cancellation | A session mutex serializes local updates and a process-wide Git semaphore protects composite Git commands. Lock ownership uses async context for nested calls. Workflow, worker, workspace, and activity are different cancellation and write scopes. State-writing activities request completion on cooperative cancellation. A forced stop can interrupt the cleanup path, and process-local queues cannot fence a second owner. [Git lock and reentrancy](repos/KeygraphHQ__shannon/apps/worker/src/services/git-manager.ts:134), [Activity cancellation profiles](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:116), [Non-cancellable final audit](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:1443), [Worker-side cleanup](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:2011) |
| Errors and retries | Typed faults separate permanent policy or consistency failures from transient I/O. Shutdown distinguishes a lost RPC from definite absence, and the top-level workflow converts hard failures into a terminal Temporal application error. Real-world failure families can still collapse at adapter edges. The Git command classifier illustrates the cost of mapping multiple command dialects with one stderr matcher. [Retry classification](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:87), [Lifecycle outcomes](repos/KeygraphHQ__shannon/apps/cli/src/temporal-client.ts:156), [Terminal failure path](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:1462), [Git error distinction](repos/KeygraphHQ__shannon/apps/worker/src/services/report-checkpoints.ts:45) |
| Types and extension contracts | TypeScript enables strict, exact-optional and unchecked-index rules. Worker registry names are runtime-checked and collision-checked. Injected checkpoint, findings, and report output providers have explicit methods, typed inputs, and no-op defaults. The skip contract models required metrics as an optional property, then gates on both fields at runtime. The standard workflow conditionally invokes checkpoint completion. The pinned production code has no call to the report-output provider, and its external-findings adapter is outside the ordinary activity registry. Registry identity, effect ordering, and idempotency need an explicit contract suite as well as structural typing. [Compiler settings](repos/KeygraphHQ__shannon/tsconfig.base.json:12), [Registry composition](repos/KeygraphHQ__shannon/apps/worker/src/temporal/worker.ts:217), [Collision guard](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/temporal/registry.ts:53), [Provider factory](repos/KeygraphHQ__shannon/apps/worker/src/services/container.ts:95), [Checkpoint interface](repos/KeygraphHQ__shannon/apps/worker/src/interfaces/checkpoint-provider.ts:13), [Skip guard](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:377), [Report output interface](repos/KeygraphHQ__shannon/apps/worker/src/interfaces/report-output-provider.ts:13), [Findings interface](repos/KeygraphHQ__shannon/apps/worker/src/interfaces/findings-provider.ts:13) [Checkpoint invocation gate](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:609), [Adapter-only extension surface](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:2036) |
| Provider and tool boundaries | Model selection is injected and coalesced in a process-local promise. Rejection clears the promise for a subsequent resolution, and a successful selection is reused for the run's roles. The direct mock controls backed that ownership policy. Config loading offers a typed result at the service layer. Tool restrictions use a dedicated repository view in one path and a separate harness policy adapter in another. A configured tool policy and operating-system isolation represent different assurances. [Model host resolver](repos/KeygraphHQ__shannon/apps/worker/src/ai/model-host.ts:14), [Config loader](repos/KeygraphHQ__shannon/apps/worker/src/services/config-loader.ts:26), [Read-only repository tools](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/tools/repository-tools.ts:372), [Permission adapter](repos/KeygraphHQ__shannon/apps/worker/src/ai/pi/permission-system.ts:7) |
| Tests and maintainability | Package scripts cover compile and lint entry points. The four tracked executable TypeScript test files are all in the stand-alone experimental probe package path. Template files with `.test.hbs` are prompt fixtures. The defensive control plane has good injection seams, as the local controls showed, but the pinned snapshot has no checked-in lifecycle regression suite. The 54-name read-model comparison is a good candidate for an offline release check. [Root scripts](repos/KeygraphHQ__shannon/package.json:7), [Worker scripts](repos/KeygraphHQ__shannon/apps/worker/package.json:36), [CLI scripts](repos/KeygraphHQ__shannon/apps/cli/package.json:14), [Release build path](repos/KeygraphHQ__shannon/.github/workflows/release.yml:190), [CLI mirror comment](repos/KeygraphHQ__shannon/apps/cli/src/scan/pipeline.ts:1) |
| Events and observability | Live query state, pending activity observation, terminal result, and the audit projections carry complementary evidence. A per-emitter tool-call ID map correlates start and end. Ordered append and stable resume markers make local logs useful during outages. Log text is best-effort, mixed with sensitive full-argument traces, and has a different lifecycle from authoritative state. Machine-readable pause, closure, and usage results would benefit from one shared state map and incident-friendly event IDs. [Progress to status](repos/KeygraphHQ__shannon/apps/cli/src/scan/status-json.ts:74), [Correlation and flushing](repos/KeygraphHQ__shannon/apps/worker/src/ai/pi/trace-emitter.ts:23), [Resume marker policy](repos/KeygraphHQ__shannon/apps/worker/src/audit/workflow-logger.ts:580), [Append semantics](repos/KeygraphHQ__shannon/apps/worker/src/audit/log-stream.ts:165) |

## 6. Executed tests/experiments and their limitations

All fixture tests ran with an empty credential environment and a separate Linux network namespace. Bun source runs used local modules, with auto-install explicitly disabled after the initial dependency-free controls. Native Node was used for the filesystem race and to cross-check five Bun source suites. Initial tool discovery and read-only Git verification ran without a network-facing command. Tests with a dependency stub exercised the checked-in function bodies and replaced the external boundary. An unexpected call to a live boundary failed the fixture.

| Run | Local experiment | Result and reach |
| --- | --- | --- |
| A | Inventory, pinned Git tree, static source checks, dependency probe | Parsed/transpiled all 217 tracked TypeScript and parsed all 15 tracked JSON files with zero diagnostics. `node --check shannon` and `bash -n entrypoint.sh` passed. Bun's in-memory builds of the CLI, worker, and workflow entry points passed with external packages left external. The static workflow runtime closure reached 16 local modules and `@temporalio/workflow` only. Node 22 native transform followed by explicit ESM syntax checking agreed on all 217 files. Two direct-file checker failures reproduced on Node 26 and were ruled out with the native transform and executed imports. These checks establish syntax, local resolution, and import layering. Full TypeScript and Temporal bundling remained outside that evidence. |
| B | Node 26 atomic JSON publication and `ensureDirectory` | Four modes, 30 trials each, six 512 KiB records per trial. Same-target concurrency failed 150/180 writes, all `ENOENT`. The other three modes each passed 180/180. The initial final reads matched submitted records. Appendix repeats found one and five invalid final values. A 40-trial follow-up distinguished mixed bodies from parse failures and found six mixed 512 KiB values. A deterministic native-FS interleaving then produced the same mixed-value class using a 4 KiB record on Node 22 and on Node 26. Native recursive `mkdir` against a regular file returned `EEXIST` and `ensureDirectory` fulfilled while the object remained a file. |
| C | CLI pending candidates and workspace ownership | Separate queue publications, mode `0600`, duplicate queue refusal, malformed-record count, temp-file exclusion, and repeated removal passed on Bun and Node 22. A mocked infrastructure barrier let two actual CLI launch paths reach the synthetic detacher for one workspace with different output routes. It recorded two task queues and the second route in the shared launch file. A fixed-clock repeat produced one workflow ID across the two queue candidates. Both detachers returned simulated failure before any live worker activity. |
| D | File-based identity, startup diagnostics, and compatibility | Named workspace follows its latest recorded resume. The exact older workflow ID, legacy layout, ambiguous claims, and pre-registration directory behavior matched the read contract. A saved, completed predecessor returned `scan-running` for a new unregistered launch. A record missing finalized-report proof passed the CLI's early check and failed the worker guard. A valid baseline was accepted by both validators. |
| E | Shutdown state machines and Temporal client adapter | Fake clocks covered a cancellation acknowledgement, lost acknowledgement, confirmed absence, unknown/transport failures, termination escalation, concurrent ordered results, worker stop verification, late registration, and unavailable visibility. A late visibility-only fixture was discovered and closed. With positively terminal candidates and the standard 3 s settling window, the fake clock advanced 3, 12, and 48 seconds for 1, 4, and 16 candidates respectively. A zero-window control removed those waits. The SDK shim confirmed channel reset on transport error and channel reuse on definite absence. |
| F | Durability and attempt accounting | With an existing session, concurrent end writes through three independent audit instances kept all three metric entries. Replaying the same attempt raised fixture cost from 0.375 to 0.500 and retained two attempt-number-1 rows. Repeat terminal accounting retained one workflow record and stable totals. After recording the result of a later resume, re-driving an older receipt preserved both individual run rows and the latest workflow ID but replaced the top-level session status with the predecessor's outcome. Simultaneous initial creation by six trackers failed five writes in each of 16 trials. |
| G | Log ordering, marker semantics, and privacy | 100 concurrent append calls preserved submission order. One process appended a scope marker once, supported an independent lease, then reopened cleanly after its last close. Four independent Node processes appended the same marker in 12 independent trials, with duplicates in 11 trials. A local parser recognized split marker lines and reset them across resume boundaries. A repeated forced-stop fallback appended one cancellation marker. Both streams included a synthetic argument marker. A trace-emitter control preserved event pairing and copied the emitted lines exactly to both files, which had mode 0644 under a controlled umask of 022. A read-only log allowed the resume identity to persist without its boundary. |
| H | Repository read boundary and persisted artifacts | Bounded reads, deny checks for lexical and resolved paths, symlink handling in an inert workspace, abort, expiration, sorted enumeration, size/count/depth limits, and basic glob rules passed on Bun and Node 22. Twenty identical in-process artifact publishers converged on one envelope. Four independent processes per scratch workspace yielded 32 successful publication and readback operations across eight workspaces, with one path and a matching independent SHA-256 per workspace. Reference mismatch, damaged bytes, absent files, and same-name conflicts returned typed outcomes. A separate artifact consumer validated its digest and rejected an altered fingerprint. A staged write failure before rename preserved the old bytes. |
| I | Checkpoint input provenance and Git proof | The confined reader saw an uncommitted fixture edit while the Git-based input fingerprint stayed constant. Committing the change altered the fingerprint. Repository stage reuse and reference loading classified genuine `EACCES` as absent or missing. Restoring the file mode restored both paths. A real Git commit-preservation test covered path-limited update, temporary-index deletion, staged and dirty siblings, and re-drive after a thrown post-commit hook. The raw Git blob kept a UTF-8 BOM, while the text reader omitted it. A second Git fixture proved date-based selection can choose an ancestor. |
| J | Report lifecycle with real local Git | Advanced empty-report fixtures in both SHA-1 and SHA-256 Git repositories through pending, draft, canonical, and final state. A wrong manifest digest failed proof. Exact terminal replay and Git re-drive adopted existing evidence. A simulated renderer failure warned and retained the previously verified PDF. The surfacing helper copied the expected Markdown, then copied a benign mutable edit while the Git proof still verified. This exercised the proof and copy functions in order. Applying the production PDF provenance predicate also removed a still-valid customer PDF once its internal source disappeared. The production activity adapter was inspected at source. |
| K | Status, provider selection, and extension compatibility | The 10,000-case timing oracle agreed with duration union. The machine view covered eight known status tokens and three time modes. A paused status entered the terminal result branch in the SDK shim, while a running status used the query. Shared model-resolution promises coalesced success and failure, then recovered after rejection through an injected resolver. Provider error classification covered bounded structured status, typed configuration failure, transport error, and an injected context-limit classification while redacting raw diagnostics. The 54 production activity declarations matched the CLI mirror. The checked-in worker sources satisfied 27 of 28 package export targets. |

The native Node checks used v26.13.1 and v22.23.3. Bun was 1.4.2, Git was 2.56.0, and the scratch filesystem was Btrfs. Standalone linked artifacts, concurrent process writes, and historical Git bytes were exercised on that filesystem. This provides no power-loss, kernel-containment, or container-filesystem durability result. The experiments give no evidence about live RPC timing, Temporal replay across releases, model accuracy or cancellation latency, or remote service behavior.

The four executable TypeScript tests in the pinned tree belong to the experimental active-probe code. Their source was parsed as part of the syntax inventory. The three entry-point builds checked the production module graphs. The executable suite here focused on credential-free defensive and control-plane fixtures. The checkout lacked its production dependency tree, a usable pinned package manager in isolation, and installed Temporal and Typst executables. Module-resolution probes and the fixture suite were feasible offline. A native package typecheck, real Temporal integration, and a real PDF render remained unverified. [Root scripts and pin](repos/KeygraphHQ__shannon/package.json:6), [Worker dependencies](repos/KeygraphHQ__shannon/apps/worker/package.json:36), [CLI scripts and dependencies](repos/KeygraphHQ__shannon/apps/cli/package.json:14)

## 7. Measurement audit for every negative or surprising result

| Result or scope gap | Alternate check, root cause, and remaining uncertainty |
| --- | --- |
| First tool wrapper rejected fixture cleanup | The command wrapper rejected a shell recursive forced removal before executing any fixture. Replaced it with a runtime-owned `mkdtemp` scoped beneath the review root and cleanup of that exact generated path in `finally`. Tests then ran and created no retained fixture. This was a measurement setup issue. |
| Package bootstrap failed and the native suite was unavailable | The first bare Corepack shim hit an account-cache path permission error in the root-mapped namespace. The repeat used the current UID mapping, an empty environment, isolated cache paths, and network disabled. The shim identified the missing pinned pnpm tarball and exited. Independent `import.meta.resolve` probes found neither the compiler/task runner nor the SDK/module dependencies. Root and both app `node_modules` directories and the two `dist` trees were absent. No dependence on account permissions, credentials, quota, or any service was needed to explain the missing local stack. Bun's syntax and external-package bundling controls were run separately. [Package manager pin](repos/KeygraphHQ__shannon/package.json:6), [Worker package requirements](repos/KeygraphHQ__shannon/apps/worker/package.json:36), [CLI package requirements](repos/KeygraphHQ__shannon/apps/cli/package.json:14) |
| Early syntax check used the wrong interpreter | `bash -n shannon` returned exit 2 on JavaScript syntax. The actual shebang is Node. `node --check shannon` and `bash -n entrypoint.sh` both passed. The apparent launcher syntax failure was discarded. [Node launcher](repos/KeygraphHQ__shannon/shannon:1), [Bash entrypoint](repos/KeygraphHQ__shannon/entrypoint.sh:1) |
| Node direct-file syntax check misclassified two TypeScript modules | Node 22 and Node 26 both reported an unexpected type-alias identifier for the same two files. A second pass transformed each source with Node 22's `stripTypeScriptTypes(..., {mode:'transform'})`, piped it into `node --input-type=module --check`, and passed all 217. Both affected modules imported and ran on Node 22. The CJS direct-file check path caused the apparent syntax failures. [Concurrency utility](repos/KeygraphHQ__shannon/apps/worker/src/utils/concurrency.ts:14), [Pipeline utility](repos/KeygraphHQ__shannon/apps/worker/src/utils/functional.ts:14) |
| Fixture and harness corrections | The first status fixture supplied `runningAgents` instead of `RenderInput.running`. The first run-state assertion matched `type` instead of `failureType`. The first stage-artifact fixture supplied `numTurns` instead of `turns`. Actual input types and guards explained all three. Corrected runs passed, and the first two passed on Node 22 as well as Bun. An SDK shim run also needed the complete fake home-module export shape before the real status path could import. An extracted function imported from a URI-escaped source string initially produced no export. Importing the same compiled code as base64 exposed the expected export. The appendix parser also needed its block count corrected from seven to eight before the full re-run. The artifact child command initially parsed a fixture path as a module argument. Moving fixture fields into its sterile environment corrected the launcher, and all 32 child checks passed. [Render input](repos/KeygraphHQ__shannon/apps/cli/src/scan/render.ts:17), [Durable error fields](repos/KeygraphHQ__shannon/apps/worker/src/types/run-state.ts:860), [Artifact usage validator](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/artifacts.ts:180), [Zero usage record](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/types.ts:35) |
| Concurrent JSON writes failed | Same runtime, same Btrfs mount, same data sizes, and same write permissions passed in sequential, distinct-target, and serialized cases. Every same-target failure was `ENOENT`. The single shared temporary filename explains the failed rename once a peer consumes that directory entry, and the initial files passed content checks. The appendix validity check combined unreadable JSON and mismatched bodies. Repeats returned one and five invalid values. A native size control separated the two error classes and observed six mixed records with 512 KiB bodies and zero parse errors. The deterministic fixture paused a write at an open descriptor and let a second writer publish the same inode. Before releasing the first writer, the file held the second writer's exact value. Resuming the first writer changed the body while its rename failed. The published inode matched the one opened by the first writer. A subsequent single writer restored its exact content. The separate real initializer test found the same errno and exposed the pre-lock call path. Filesystem space was available and the isolated reproduction had no provider or server dependencies. [Temporary write and rename](repos/KeygraphHQ__shannon/apps/worker/src/utils/file-io.ts:34), [Unlocked initializer](repos/KeygraphHQ__shannon/apps/worker/src/audit/metrics-tracker.ts:212), [Write lock scope](repos/KeygraphHQ__shannon/apps/worker/src/audit/audit-session.ts:208) |
| Regular file accepted as a directory | Native `mkdir(..., {recursive:true})` and an immediate `stat` proved the setup. The wrapper suppressed `EEXIST` even though the path remained an ordinary file. A real directory fixture was accepted in normal log and artifact paths. This is an error-reporting and contract issue which can defer the failure to a later write. [Directory helper](repos/KeygraphHQ__shannon/apps/worker/src/utils/file-io.ts:16) |
| Launch route replacement and old-record acknowledgement | Direct re-publication showed replacing-rename semantics. The actual CLI flow with a fake infrastructure barrier confirmed both callers pass the original freshness check and each can reach the detacher. Fixing Date.now to one millisecond gave both candidates one workflow ID with independent queue records. The fixture tested the CLI identity derivation, with Temporal workflow admission outside the observed result. No live owner or physical writer collision was assumed. For timeout, missing, malformed, and unknown-schema files returned `unregistered`, but a completed valid predecessor with an empty resume list returned `scan-running`. Comparing the exact-ID poll and timeout code ruled out file visibility, fixture shape, and polling cadence as causes. [Fresh classification](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:176), [Launch write](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:233), [Registration check](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:499), [Timeout classifier](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:564) |
| CLI accepted incomplete finalized state | Both views accepted the same generated initial state. The malformed report omitted only required proof fields. The CLI's subset check deliberately checks version, mode, and membership arrays, while the worker also checks report fields and cross-field invariants. The contradiction is at early classification. The worker's full validator remains a backstop. [CLI validation subset](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:92), [Final report guard](repos/KeygraphHQ__shannon/apps/worker/src/types/run-state.ts:981), [Worker state guard](repos/KeygraphHQ__shannon/apps/worker/src/types/run-state.ts:1015) |
| Paused status mislabeled and sent to result read | The direct projector produced `failed` and `UNKNOWN` for `PAUSED`. A mocked Temporal client exposed the branch in the actual JSON command. A `RUNNING` describe with the same fixture used progress and exited normally. The stop client classified `PAUSED` as open. The cause is competing status predicates and allowlists. No live paused execution or production SDK latency was measured. [Stop lifecycle mapping](repos/KeygraphHQ__shannon/apps/cli/src/temporal-client.ts:157), [CLI result branch](repos/KeygraphHQ__shannon/apps/cli/src/commands/status.ts:175), [Projection terminal predicate](repos/KeygraphHQ__shannon/apps/cli/src/scan/derive.ts:64), [Raw status allowlist](repos/KeygraphHQ__shannon/apps/cli/src/scan/safe-fields.ts:254) |
| Verified terminal candidate still waited | The fake status returned positively terminal on every describe. There was no RPC delay, capacity constraint, or server propagation. Zero settling time eliminated the measured delay. Each candidate receives its own settle deadline and terminal confirmation updates bookkeeping without breaking the loop. The number is simulated settling work and does not predict live response time. [Serial candidate settle loop](repos/KeygraphHQ__shannon/apps/cli/src/commands/stop.ts:406) |
| Duplicate attempt accounting and duplicate marker | The prior ledger was valid and three separate updates survived, which rules out a corrupt initial file or dropped unrelated write. Same attempt fields doubled that event's cost. Terminal upsert provided a positive same-run control. Across runs, the top-level session status followed write order in a fixture with an older failed run and a completed resume, while the per-run entries still distinguished their outcomes. One-process marker dedup worked repeatedly, while new processes with synchronized start produced duplicates with identical file, marker, and permissions. Both loops are scoped to a process. No actual duplicate charge or overlapping shipped workers was observed. [Attempt summation](repos/KeygraphHQ__shannon/apps/worker/src/audit/metrics-tracker.ts:956), [Terminal accounting](repos/KeygraphHQ__shannon/apps/worker/src/audit/metrics-tracker.ts:661), [Log dedup queue](repos/KeygraphHQ__shannon/apps/worker/src/audit/log-stream.ts:180) |
| Customer Markdown drifted from the final proof | Baseline customer bytes equaled the committed blob and corrupt manifest digest was rejected. A local edit changed only the working file. The same proof still succeeded and the copy matched the edited file, so the discrepancy is the source-of-bytes contract. The actual adapter checks the commit then passes the worktree directory to the helper, which rereads it. This rules out the PDF stub, hash computation, destination permissions, and stale prior copy as causes. [Committed proof](repos/KeygraphHQ__shannon/apps/worker/src/services/report-checkpoints.ts:178), [Production copy adapter](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1427), [Copy input selection](repos/KeygraphHQ__shannon/apps/worker/src/services/report-output-surface.ts:186) |
| Source bytes changed independently of their input fingerprint | A second read via the actual repository view reported the edited fixture bytes. Git status confirmed a dirty working tree, and both `repositoryIdentity` and the derived fingerprint were stable. A clean commit changed both identity and fingerprint. The key describes a Git commit and options. It does not fingerprint a mutable working tree exposed to the file reader. No analysis stage or model was run. [Repository identity](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/artifacts.ts:82), [Fingerprint inputs](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/artifacts.ts:104), [Repository file read](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/tools/confinement.ts:325), [Host source bind](repos/KeygraphHQ__shannon/apps/cli/src/docker.ts:453) |
| Stage artifact permission error appeared missing | A direct file read of the identical path proved `EACCES` with UID 1000. The cached artifact read returned `undefined` and the reference read returned `ARTIFACT_MISSING`. Restoring mode `0600` made both succeed without changing bytes, reference, or fingerprint. The catch handlers collapse filesystem causes. The intermediate content-addressed store has a finer absent/I/O taxonomy, so this is specific to the stage artifact layer. [Cached and referenced stage reads](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/artifacts.ts:215), [Intermediate artifact read errors](repos/KeygraphHQ__shannon/apps/worker/src/ai/reconciliation/artifact-store.ts:474) |
| Git checkpoint surprising cases | Independent `git show` proved the BOM bytes were stored intact, and a plain-text control decoded identically. Node's text decoder defaults explain the normalization. For the missing revision, actual `git rev-parse --verify` returned exit 128 and `fatal: Needed a single revision`. The same repository resolved `HEAD` and classified a missing blob as absent. The retry choice reflects stderr classification, with no filesystem or network outage. A two-commit graph with a stepped clock proved the later descendant had the earlier timestamp. The resume command selected the ancestor in either input order, while ancestry and topological ordering selected the descendant. A forward-time control selected the expected descendant. A live rollback was outside the test. [Committed text read](repos/KeygraphHQ__shannon/apps/worker/src/services/git-manager.ts:595), [Checkpoint command adapters](repos/KeygraphHQ__shannon/apps/worker/src/services/report-checkpoints.ts:80), [Checkpoint selection](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1773) |
| Full trace argument appeared despite safe status fields | The marker was synthetic and entered through the supported argument serializer. It appeared in both output files. A separate synthetic exception and URL projection were sanitized as designed. Invalid circular arguments produced a generic log warning at serialization, after which valid output still landed. Lossless capture is a deliberate contract distinct from the safe error and status projections. [Argument serializer](repos/KeygraphHQ__shannon/apps/worker/src/audit/trace.ts:77), [Log writer](repos/KeygraphHQ__shannon/apps/worker/src/audit/workflow-logger.ts:324), [Safe error projection](repos/KeygraphHQ__shannon/apps/worker/src/audit/safe-fields.ts:118) |
| Export and runtime metadata drift | Compared each export's `dist` path against the `tsc` source layout. Then checked the missing path in the pinned Git tree, searched the application sources for the name, and checked the build script for generated artifacts. The result is a dangling declaration in this source revision. The engine mismatch is between checked-in metadata entries. In-memory builds externalized the dependency and provide no evidence of Node 18 execution. [Worker export and scripts](repos/KeygraphHQ__shannon/apps/worker/package.json:6), [CLI direct dependency and engine](repos/KeygraphHQ__shannon/apps/cli/package.json:19), [Locked engine floor](repos/KeygraphHQ__shannon/pnpm-lock.yaml:996) |
| Missing commit check and predecessor termination returned normally | The exact restore body was extracted and transpiled with a Git command recorder. Both a missing-checkpoint verifier and injected `EIO` returned before the reset recorder. A positive verifier reached reset and scoped clean. Omitted durable membership raised a typed error. A separate extracted predecessor helper continued after a failed termination and skipped the `PAUSED` predecessor, although the stop adapter treats that state as open. [Restore verification](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1801), [Predecessor disposition](repos/KeygraphHQ__shannon/apps/worker/src/temporal/worker.ts:405), [Stop adapter](repos/KeygraphHQ__shannon/apps/cli/src/temporal-client.ts:156) |
| Resume identity survived a failed log boundary | Native `0444` on the exact log made a direct write return `EACCES`. The audit facade still resolved the resume marker call and persisted the ID. Mode `0600` restored the marker write. The actual tail helper, with a watcher stub, accepted the predecessor marker before checking Temporal even with a new workflow ID. [Best-effort write contract](repos/KeygraphHQ__shannon/apps/worker/src/audit/workflow-logger.ts:528), [Production resume write order](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1907), [Initial tail close path](repos/KeygraphHQ__shannon/apps/cli/src/commands/logs.ts:204) |
| Verified customer PDF removed when the source PDF vanished | Passing valid provenance directly preserved the copy. Applying the adapter's internal-file predicate reduced the same provenance to null and the helper removed the customer file. Canonical report, template, and customer PDF bytes were held constant. [Internal file check](repos/KeygraphHQ__shannon/apps/worker/src/services/pdf-renderer.ts:120), [Surface adapter](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1449), [PDF destination preservation](repos/KeygraphHQ__shannon/apps/worker/src/services/report-output-surface.ts:128) |

The controls above separate observed function behavior from production consequences inferred through call sites. Repository history was shallow, and Git could supply only the pinned commit in the relevant path histories. The post-mortem uses current code comments, module boundaries, and fault paths as evidence for design pressures. [Worker current-release workflow comment](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:7)

## 8. Post-mortem: design pressures, accumulated tradeoffs, likely failure modes, and the highest-leverage improvements

**Root cause and pressures.** The code is designed to ship a self-contained local invocation with durable audit evidence and no permanently running application worker. It uses Temporal for scheduling and replay, local Git for recoverable outputs, and independently versioned files for CLI handoff and workspace continuity. Early identity and verification can then work during container startup or after the worker exits. The resulting system has several individually sensible authorities. It lacks one authority for the right to mutate the workspace throughout a launch, stop, or resume transition. Process-local mutexes and a per-queue pending record address smaller scopes. The path between classification and publication crosses an awaited infrastructure setup, the output route can be replaced, and worker-side predecessor termination logs uncertainty and continues. That combination creates the workspace ownership failure. [CLI handoff transaction gap](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:290), [CLI shared workspace creation](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:348), [Per-invocation registration](repos/KeygraphHQ__shannon/apps/cli/src/pending-workflow.ts:39), [Worker predecessor handling](repos/KeygraphHQ__shannon/apps/worker/src/temporal/worker.ts:405), [Process-local mutex](repos/KeygraphHQ__shannon/apps/worker/src/audit/audit-session.ts:43)

**Proof and copy accumulated different responsibilities.** Integrating generated reports, exact artifacts, and optional renderers led to a good durable core with immutable Git and manifest verification, explicit terminal proof, and re-drive behavior. The publication helper inherited an interface in terms of working filesystem paths and a copy verifier. As a result, each verification can succeed against its own input while the copied bytes differ from the committed artifact. A similar provenance boundary exists between the repository fingerprint and the live read-only bind of a host working tree. The preventive invariant at either boundary is that the object verified is the object consumed. [Finalization commit and derivation](repos/KeygraphHQ__shannon/apps/worker/src/services/report-finalization.ts:330), [Commit proof](repos/KeygraphHQ__shannon/apps/worker/src/services/report-checkpoints.ts:178), [Copy contract](repos/KeygraphHQ__shannon/apps/worker/src/services/report-output-surface.ts:53), [Repository identity](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/artifacts.ts:82), [Source mount](repos/KeygraphHQ__shannon/apps/cli/src/docker.ts:453)

| Likely failure mode | Consequence and confidence |
| --- | --- |
| Two invocations qualify for one workspace, or a prior owner has uncertain closure | Split launch configuration and competing state writers. Two mocked handoffs and the filesystem collision are observed separately. Real live overlap is an inference. |
| A worker exits abruptly with operations outstanding | A persistent server record and a local workspace can outlive the dedicated poller. A forced or interrupted end can lack a terminal log and leave startup or cleanup residue. The code puts sensitive temporary-state deletion after terminal metrics and log work. This is a source-derived failure mode. |
| Resume observes durable status but its commit is absent or the clock stepped | Commit selection can prefer an earlier ancestor. Restore also catches any verification failure and returns, after which the workflow can go on to mark previously recorded units complete. The Git command behavior was measured. The full resume effect was source-audited. |
| A publication is acknowledged and later a local working file changes | The immutable record can remain valid while copied Markdown reflects a working edit. The producer/consumer seam was measured. |
| Multiple process owners or nondeduplicated callbacks submit the same audit event | Closure markers and attempt accounting can duplicate. Individual APIs were exercised in isolation. |
| A release changes status or packaging schema | Name parity covers the current tree, while import aliases, runtime engine declarations, startup schema checks, and lifecycle status predicates are maintained separately. Local checks observed drift along those boundaries. |

[Dedicated worker startup and exit](repos/KeygraphHQ__shannon/apps/worker/src/temporal/worker.ts:724), [Resume file verification and reset](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1773), [Resume mark-complete path](repos/KeygraphHQ__shannon/apps/worker/src/temporal/workflows.ts:1322), [Cleanup sequence](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1961), [Activity mirror](repos/KeygraphHQ__shannon/apps/cli/src/scan/pipeline.ts:265)

**Prioritized improvements**

1. **P0 — Establish workspace ownership before mutation.** A workspace lease should fence writes by execution identity from reservation through closure. The handoff should require positively verified disposition of a prior owner or retain an explicit unverified state. Bind startup timeout classification to the same identity predicate as registration. Protect first creation and ongoing reads and writes with the same ownership rule. Replace the shared temporary path with attempt-unique replacement and meaningful durability barriers for records whose recovery depends on them. Use a two-launch fake barrier, a stale resume record, and a separate-process write harness as regressions. [Current label and writer boundary](repos/KeygraphHQ__shannon/apps/cli/src/docker.ts:431), [Startup poll and fallback](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:499), [Ownership-sensitive state creation](repos/KeygraphHQ__shannon/apps/worker/src/audit/metrics-tracker.ts:212)
2. **P0 — Carry immutable artifact identity to the destination.** Surface canonical Markdown and machine output from verified committed bytes or a digest-checked copy of those bytes. Treat derived files as optional proof-bound outputs. Include working-file drift, lost acknowledgement, deleted optional artifact, and persisted receipt mismatch in the offline contract suite. Apply the same invariant to source identity by pinning or verifying the actual repository snapshot exposed to the worker. [Final proof](repos/KeygraphHQ__shannon/apps/worker/src/services/report-checkpoints.ts:178), [Customer publication](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1427), [Read-only repository view](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/tools/confinement.ts:237)
3. **P1 — Make stop and cleanup fail safely across substrate loss.** Reuse one status vocabulary for direct lifecycle decisions and all machine status reads. Reserve the registration settle horizon for uncertain candidates, bound shutdown by a visible end-to-end deadline, and keep explicit unverified outcomes for unavailable dependencies. Use a separately owned cleanup path for expired sensitive state and scoped output mounts, and preserve argument boundaries at the privilege drop. These changes improve operator control and isolation without depending on what any activity does. [Stop settle loop](repos/KeygraphHQ__shannon/apps/cli/src/commands/stop.ts:406), [Temporal lifecycle state](repos/KeygraphHQ__shannon/apps/cli/src/temporal-client.ts:157), [Cleanup ordering](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:2011), [Process boundary](repos/KeygraphHQ__shannon/entrypoint.sh:18)
4. **P1 — Make durable receipts idempotent and errors phase-specific.** Use an execution-scoped identifier for each audit event, so a duplicated write and distinct billable attempts stay distinguishable. Carry versioned structured lifecycle events and keep sensitive traces under a narrower retention and export policy. Grade checkpoint eligibility by verified ancestry, and distinguish confirmed absence, corruption, and transient I/O before deciding whether restoration succeeded. [Attempt receipt storage](repos/KeygraphHQ__shannon/apps/worker/src/audit/metrics-tracker.ts:962), [Marker ownership](repos/KeygraphHQ__shannon/apps/worker/src/audit/log-stream.ts:180), [Checkpoint selection and verification](repos/KeygraphHQ__shannon/apps/worker/src/temporal/activities.ts:1773)
5. **P2 — Contract-test the release boundaries offline.** Check every package export against an actual built target and align the Node declaration with the locked dependencies. Verify registry and CLI status parity, document which extensions production invokes, and share durable wire types and validators where feasible. Add an offline gate with inert test inputs for launch, resume, cancellation, logging, package resolution, and report-state integrity. [Worker exports](repos/KeygraphHQ__shannon/apps/worker/package.json:6), [CLI engine declaration](repos/KeygraphHQ__shannon/apps/cli/package.json:49), [Worker DI lifecycle](repos/KeygraphHQ__shannon/apps/worker/src/services/container.ts:83), [Root build/check scripts](repos/KeygraphHQ__shannon/package.json:7)

## 9. Evidence appendix with local file/line references and commands

### Setup and read-only checks

The commands below use the pinned checkout as the module-resolution directory. Each disk fixture is created as a new sibling under the review root and deleted in its own `finally`. All JavaScript snippets are stdin programs. Git fixture commits use an inert local identity. No lifecycle fixture contacts a Docker daemon or a Temporal server.

```bash
cd repos/KeygraphHQ__shannon
offline() {
  unshare --user --map-current-user --net -- env -i PATH="$PATH" "$@"
}
offline sh -c 'id -u && cat /proc/net/route && cat /proc/net/dev'
git --no-optional-locks rev-parse HEAD
git --no-optional-locks status --porcelain=v1 --untracked-files=all
git --no-optional-locks diff --exit-code
git --no-optional-locks diff --cached --exit-code
git rev-parse --is-shallow-repository
git ls-files '*.ts' | wc -l
git ls-files '*.json' | wc -l
git ls-files '*test.ts'
node --check shannon
bash -n entrypoint.sh
```

Run A printed the pinned hash and an empty status/diff, then `true` for shallow history, `217` TypeScript files, `15` JSON files, four test modules, and zero syntax diagnostics. The isolation probe printed UID `1000`, an empty route table, and loopback with no packets. The following block checks local build and resolution.

```bash
offline bun run --no-install - <<'JS'
import {readFileSync, existsSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {ACTIVITY_TO_PROGRESS} from './apps/cli/src/scan/pipeline.ts';
import {CAPELLA_ACTIVITY_NAMES} from './apps/worker/src/ai/sast/capella/temporal/activity-types.ts';
import {RECONCILIATION_ACTIVITY_NAMES} from './apps/worker/src/temporal/reconcile-activity-types.ts';
import assert from 'node:assert/strict';
const files = execFileSync('git', ['ls-files', '-z'], {encoding:'utf8'}).split('\0');
const transpiler = new Bun.Transpiler({loader:'ts',target:'node'});
for (const file of files.filter(p => p.endsWith('.ts'))) {
  transpiler.transformSync(readFileSync(file, 'utf8'));
}
for (const file of files.filter(p => p.endsWith('.json'))) {
  JSON.parse(readFileSync(file, 'utf8'));
}
for (const entrypoint of [
  'apps/cli/src/index.ts',
  'apps/worker/src/temporal/worker.ts',
  'apps/worker/src/temporal/workflows.ts',
]) {
  const result = await Bun.build({entrypoints:[entrypoint],target:'node',packages:'external',write:false});
  assert.equal(result.success, true);
}
const worker = readFileSync('apps/worker/src/temporal/worker.ts','utf8');
const ordinary = worker.match(/PENTEST_ACTIVITY_NAMES = Object.freeze\(\[([\s\S]+?)\] as const\)/)[1];
const names = [...ordinary.matchAll(/'([A-Za-z0-9]+)'/g)].map(x => x[1]);
const expected = [...names, ...CAPELLA_ACTIVITY_NAMES, ...RECONCILIATION_ACTIVITY_NAMES];
assert.equal(new Set(expected).size, 54);
assert.deepEqual(Object.keys(ACTIVITY_TO_PROGRESS).sort(), expected.sort());
const manifest = JSON.parse(readFileSync('apps/worker/package.json','utf8'));
const missing = Object.entries(manifest.exports).filter(([, target]) =>
  !existsSync(target.replace('./dist/', 'apps/worker/src/').replace(/\.js$/, '.ts')));
console.log({activityAliases:expected.length, exports:Object.keys(manifest.exports).length, missing});
JS

git ls-tree HEAD -- apps/worker/src/ai/pi/source-jail.ts
rg -n 'source-jail' apps
rg -n -A 2 '^  chokidar@5\.0\.0:' pnpm-lock.yaml
rg -n -A 2 '"engines"' apps/cli/package.json
```

Run K returned `54` names and `28` exports, with one missing target at `./ai/pi/source-jail`. The Git tree lookup was empty and the source search found only the export declaration. The pinned lock and package metadata reported Node `>= 20.19.0` and `>=18` respectively. [Worker package exports](repos/KeygraphHQ__shannon/apps/worker/package.json:6), [CLI activity index](repos/KeygraphHQ__shannon/apps/cli/src/scan/pipeline.ts:265)

```bash
offline node --input-type=module - <<'JS'
import {existsSync,mkdtempSync,rmSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {resolve} from 'node:path';
const dir = mkdtempSync('../../.shannon-review.');
try {
  const result = spawnSync('pnpm',['--version'],{encoding:'utf8',env:{
    ...process.env, COREPACK_ENABLE_NETWORK:'0', COREPACK_ENABLE_DOWNLOAD_PROMPT:'0',
    COREPACK_HOME:resolve(dir,'corepack'), XDG_CACHE_HOME:resolve(dir,'cache'),
  }});
  console.log(result.status, result.stderr.trim());
  for (const name of ['typescript','turbo','@temporalio/workflow','@temporalio/worker','@earendil-works/pi-ai','zx']) {
    try {console.log(import.meta.resolve(name));} catch (e) {console.log(name,e.code);}
  }
  for (const p of ['node_modules','apps/cli/node_modules','apps/worker/node_modules','apps/cli/dist','apps/worker/dist']) {
    console.log(p,existsSync(p));
  }
} finally {rmSync(dir,{recursive:true});}
JS
```

The clean-cache repeat returned exit `1` with `Network access disabled by the environment`. The listed modules returned `ERR_MODULE_NOT_FOUND` and the checked paths returned `false`. No installation was attempted after that probe. [Pinned package manager](repos/KeygraphHQ__shannon/package.json:6), [Compiler and dependencies](repos/KeygraphHQ__shannon/apps/worker/package.json:36)

### Concurrent JSON and directory-type control

```bash
offline env UV_THREADPOOL_SIZE=8 node --input-type=module - <<'JS'
import assert from 'node:assert/strict';
import {mkdtemp,rm,mkdir,writeFile,stat} from 'node:fs/promises';
import {join} from 'node:path';
import {atomicWrite,ensureDirectory,readJson} from './apps/worker/src/utils/file-io.ts';
import {SessionMutex} from './apps/worker/src/utils/concurrency.ts';
const dir = await mkdtemp('../../.shannon-review.');
try {
  const records = Array.from({length:6},(_,i)=>({writer:i,body:String(i).repeat(524288)}));
  for (const mode of ['sequential','distinct','concurrent','mutex']) {
    let rejected = 0, invalid = 0;
    const codes = {};
    for (let j=0;j<30;j++) {
      const target = i => join(dir,mode==='distinct' ? 'state-'+i+'.json' : 'state.json');
      const mutex = new SessionMutex();
      const write = async (value,i) => {
        if (mode !== 'mutex') return atomicWrite(target(i),value);
        const unlock = await mutex.lock(target(i));
        try {await atomicWrite(target(i),value);} finally {unlock();}
      };
      if (mode==='sequential') {
        for (let i=0;i<records.length;i++) await write(records[i],i);
      } else {
        for (const result of await Promise.allSettled(records.map(write))) {
          if (result.status==='rejected') {
            rejected++;
            codes[result.reason.code] = (codes[result.reason.code] ?? 0) + 1;
          }
        }
      }
      for (const file of new Set(records.map((_,i)=>target(i)))) {
        try {
          const data=await readJson(file);
          if (data.body !== records[data.writer]?.body) invalid++;
        } catch {invalid++;}
      }
    }
    console.log(mode, {rejected,invalid,codes});
  }
  const file=join(dir,'regular');
  await writeFile(file,'payload');
  await assert.rejects(mkdir(file,{recursive:true}),{code:'EEXIST'});
  await ensureDirectory(file);
  assert.equal((await stat(file)).isFile(),true);
} finally {await rm(dir,{recursive:true});}
JS
```

Run B produced rejection counts `0, 0, 150, 0` across the four modes, with zero invalid final reads initially. Both exact appendix re-runs again rejected 150 writes and recorded one and five invalid final reads respectively. Run F used real `MetricsTracker.initialize` calls to reproduce the same-path collision for fresh sessions, then separate `AuditSession` instances to verify the normal locked update. [Atomic file helper](repos/KeygraphHQ__shannon/apps/worker/src/utils/file-io.ts:30), [Metrics initializer](repos/KeygraphHQ__shannon/apps/worker/src/audit/metrics-tracker.ts:207), [Locked audit update](repos/KeygraphHQ__shannon/apps/worker/src/audit/audit-session.ts:157)

To force the observed interleaving in an independent control, the following script pauses the first write on an open file descriptor, then lets the second writer publish. It uses the actual writer, rename, and read functions and restores the ordinary file write after the control.

```bash
offline node --input-type=module - <<'JS'
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {join} from 'node:path';
import {atomicWrite,readJson} from './apps/worker/src/utils/file-io.ts';
const dir=await fs.mkdtemp('../../.shannon-review.');
const normal=fs.writeFile;
try {
  const path=join(dir,'state.json');
  const pending=path+'.tmp';
  const a={writer:0,body:'A'.repeat(4096)};
  const b={writer:1,body:'B'.repeat(4096)};
  const split=JSON.stringify(a,null,2).indexOf('A')+2048;
  const firstOpen=Promise.withResolvers();
  const secondRenamed=Promise.withResolvers();
  let firstIdentity;
  fs.writeFile=async function (filename,text,...args) {
    if (filename!==pending||!text.includes('"writer": 0')) return normal(filename,text,...args);
    const bytes=Buffer.from(text,'utf8');
    const fd=await fs.open(filename,'w');
    try {
      firstIdentity=await fd.stat();
      await fd.write(bytes,0,split,0);
      firstOpen.resolve();
      await secondRenamed.promise;
      await fd.write(bytes,split,bytes.length-split,split);
    } finally {await fd.close();}
  };
  const first=atomicWrite(path,a).then(()=>({ok:true}),e=>({ok:false,code:e.code}));
  await firstOpen.promise;
  await atomicWrite(path,b);
  assert.deepEqual(await readJson(path),b);
  assert.equal((await fs.stat(path)).ino,firstIdentity.ino);
  secondRenamed.resolve();
  const rejection=await first;
  assert.deepEqual(rejection,{ok:false,code:'ENOENT'});
  const mixed=await readJson(path);
  assert.equal(mixed.writer,1);
  assert.equal(mixed.body,'B'.repeat(2048)+'A'.repeat(2048));
  fs.writeFile=normal;
  await atomicWrite(path,b);
  assert.deepEqual(await readJson(path),b);
  console.log(JSON.stringify({firstWriter:rejection,duringSecondReceipt:'submitted B',afterFirstContinued:'B header, B and A body',publishedInodeWasStillOpen:true,singleWriterControl:true}));
} finally {fs.writeFile=normal;await fs.rm(dir,{recursive:true});}
JS
```

The published inode matched the first writer's descriptor. The second writer acknowledged its complete value. Resuming the first writer changed the final body to a mix of the two values, with a valid JSON header and a later `ENOENT` from its own rename.

### Launch and shutdown controls

The following Bun mock boundary lets the pure control functions import without the external dependency tree. The actual launch interleaving experiment additionally replaced `ensureInfra` with a two-caller barrier and `spawnWorker` with a recording event emitter that exited with code 1. All child-process functions were throwing sentinels during that experiment.

```bash
cli_fixture() {
  {
    cat <<'JS'
import {mock} from 'bun:test';
const blocked=()=>{throw new Error('live dependency forbidden in fixture');};
mock.module('@clack/prompts',()=>({spinner:blocked,confirm:blocked,text:blocked,isCancel:blocked,cancel:blocked}));
mock.module('@temporalio/client',()=>({
  Client:class{constructor(){blocked();}},Connection:{connect:blocked},
  WorkflowFailedError:class extends Error{},WorkflowNotFoundError:class extends Error{},
}));
mock.module('chokidar',()=>({watch:blocked}));
mock.module('dotenv',()=>({default:{config:blocked,parse:blocked}}));
mock.module('smol-toml',()=>({parse:blocked,stringify:blocked,TomlError:class extends Error{}}));
mock.module('./apps/cli/src/exp-php2shell/run.ts',()=>({runExpPhp2shell:blocked}));
JS
    cat
  } | offline bun run --no-install -
}
cli_fixture <<'JS'
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm} from 'node:fs/promises';
import {join,resolve} from 'node:path';
const {classifyWorkspaceLaunch,classifyStartupTimeout,writeLaunchStateAtomically}=await import('./apps/cli/src/commands/start.ts');
const {writePendingWorkflowIdentity,readPendingWorkflowIdentities}=await import('./apps/cli/src/pending-workflow.ts');
const {createInitialDurableScanState,isDurableScanState}=await import('./apps/worker/src/types/run-state.ts');
const {toStatusJson}=await import('./apps/cli/src/scan/status-json.ts');
const {executeStopPlan}=await import('./apps/cli/src/commands/stop.ts');
const dir=await mkdtemp('../../.shannon-review.');
try {
  const ws=join(dir,'fixture');
  const internal=join(ws,'.shannon'), session=join(internal,'session.json');
  const url='https://example.invalid';
  await mkdir(internal,{recursive:true});
  const first=resolve(dir,'route-one'), second=resolve(dir,'route-two');
  writeLaunchStateAtomically(internal,first,false,false);
  writeLaunchStateAtomically(internal,second,false,false);
  console.log('route replaced:',JSON.parse(await readFile(join(internal,'launch.json'),'utf8')).customer_output_path===second);
  writePendingWorkflowIdentity(ws,'fixture_shannon-10','shannon-00000001');
  assert.throws(()=>writePendingWorkflowIdentity(ws,'fixture_resume_20','shannon-00000001'),{code:'EEXIST'});
  assert.equal(readPendingWorkflowIdentities(ws).identities.length,1);
  const state=createInitialDurableScanState(false);
  const predecessor={webUrl:url,originalWorkflowId:'fixture_shannon-10',resumeAttempts:[],status:'completed'};
  await writeFile(session,JSON.stringify({session:predecessor,durableScanState:state}));
  console.log('timeout with predecessor only:',classifyStartupTimeout(session));
  const malformed={...state,report:{stage:'finalized',renumber_failed_classes:[],partial_reasons:[]}};
  await writeFile(session,JSON.stringify({session:predecessor,durableScanState:malformed}));
  console.log('CLI resume / worker validator:',classifyWorkspaceLaunch(ws,url,undefined,false,false).isResume,isDurableScanState(malformed));
  const paused=toStatusJson({workspace:'fixture',state:null,running:[],temporalStatus:'PAUSED'},1000);
  console.log('paused projection:',paused.status,paused.temporalStatus);
} finally {await rm(dir,{recursive:true});}
for (const count of [1,4,16]) {
  let clock=0;
  const fake={
    cancel:async()=> 'requested',describe:async()=>({kind:'terminal',status:'CANCELLED'}),
    refresh:async()=>{},terminate:async()=> 'requested',
    containers:()=>({kind:'ok',value:[]}),stopContainers:async()=>{},
    appendFallback:()=>{},now:()=>clock,wait:async(ms)=>{clock+=ms;},
  };
  const targets=Array.from({length:count},(_,i)=>({workflowId:'fixture-'+i,containerCandidate:true}));
  const result=await executeStopPlan(targets,targets.map(t=>({id:t.workflowId})),[],fake);
  assert.ok(result.workflows.every(x=>x.outcome.kind==='graceful'));
  console.log('terminal targets / simulated wait:',count,clock);
}
JS
```

These controls produced `route replaced: true`, `scan-running` for the stale predecessor, `true false` for the two validators, `failed UNKNOWN` for the paused view, and `3000/12000/48000` ms of simulated settling. Run E tested unrelated request/discovery failures through the same injectable lifecycle, and the SDK shim reached the actual machine-status branch. [Classifier and atomic launch write](repos/KeygraphHQ__shannon/apps/cli/src/commands/start.ts:176), [Status JSON](repos/KeygraphHQ__shannon/apps/cli/src/scan/status-json.ts:75), [Stop settling loop](repos/KeygraphHQ__shannon/apps/cli/src/commands/stop.ts:406)

### Git checkpoint ordering and consumer byte contract

The following fixture runs the real Git selection command used by the restore path. It works entirely inside a temporary Git directory, applies no reset, and measures topology independently of commit dates.

```bash
offline env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null LC_ALL=C node --input-type=module - <<'JS'
import {spawnSync} from 'node:child_process';
import {writeFile,mkdtemp,rm} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import assert from 'node:assert/strict';
const dir=resolve(await mkdtemp('../../.shannon-review.'));
try {
  const git=(args,env={})=>{
    const result=spawnSync('git',args,{cwd:dir,encoding:'utf8',env:{...process.env,...env}});
    assert.equal(result.status,0,result.stderr);
    return result.stdout.trim();
  };
  git(['init','-q','--template=']);
  git(['config','user.name','Offline Fixture']);
  git(['config','user.email','fixture@example.invalid']);
  const commit=async (name,time)=>{
    await writeFile(join(dir,'sample'),name);
    git(['add','sample']);
    git(['commit','-qm',name],{GIT_AUTHOR_DATE:time,GIT_COMMITTER_DATE:time});
    return git(['rev-parse','HEAD']);
  };
  const first=await commit('parent','2026-11-19T06:00:10Z');
  const second=await commit('child','2026-11-19T06:00:00Z');
  assert.equal(git(['rev-parse',second+'^']),first);
  assert.equal(git(['rev-list','--max-count=1',first,second]),first);
  assert.equal(git(['rev-list','--max-count=1',second,first]),first);
  assert.equal(git(['rev-list','--topo-order','--max-count=1',first,second]),second);
  console.log('date selection returned the ancestor in both input orders');
} finally {await rm(dir,{recursive:true});}
JS
```

Run J used the checked-in Git, audit, finalization, and copy functions. The only Git SDK shim adapted three read-only `zx` templates to real Git argument arrays. The native write and commit operations ran against the fixture. For a compact reproduction of the consumer-byte discrepancy, commit Markdown in a synthetic Git directory and compare its digest with two successive calls to the actual output helper.

```bash
offline env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null LC_ALL=C bun run --no-install - <<'JS'
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdir,mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import assert from 'node:assert/strict';
import {surfaceReportOutputs} from './apps/worker/src/services/report-output-surface.ts';
import {ASSEMBLED_REPORT_FILENAME as source,FINAL_REPORT_MD_FILENAME as published} from './apps/worker/src/paths.ts';
const dir=resolve(await mkdtemp('../../.shannon-review.'));
try {
  const deliverablesDir=join(dir,'deliverables'), customerDir=join(dir,'customer');
  await mkdir(deliverablesDir);
  const git=(...a)=>execFileSync('git',a,{cwd:deliverablesDir});
  git('init','-q','--template=');
  git('config','user.name','Offline Fixture');
  git('config','user.email','fixture@example.invalid');
  const md=join(deliverablesDir,source);
  await writeFile(md,'canonical fixture bytes\n');
  git('add',source);
  git('commit','-qm','fixture');
  const commit=git('rev-parse','HEAD').toString().trim();
  const committed=()=>git('show',commit+':'+source);
  const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
  const prior=digest(committed());
  const args={deliverablesDir,customerDir,logger:{info(){},warn(){}}};
  await surfaceReportOutputs(args);
  assert.equal(digest(await readFile(join(customerDir,published))),prior);
  await writeFile(md,'local draft edit\n');
  await surfaceReportOutputs(args);
  assert.notEqual(digest(await readFile(join(customerDir,published))),prior);
  assert.equal(digest(committed()),prior);
  console.log('immutable digest stable, customer copy followed working file');
} finally {await rm(dir,{recursive:true});}
JS
```

The extended run used `AuditSession.initializeReportProgress`, `endReportDraft`, `recordCanonicalReportCheckpoint`, `finalizeReport`, `finalProgressIsCoherent`, and `finalizeReportProgress` before publication. It verified terminal replay, manifest-digest rejection, and preservation of the prior PDF upon injected renderer failure. [Audit report state API](repos/KeygraphHQ__shannon/apps/worker/src/audit/audit-session.ts:174), [Manifest validator](repos/KeygraphHQ__shannon/apps/worker/src/services/report-checkpoints.ts:178), [Worktree copy](repos/KeygraphHQ__shannon/apps/worker/src/services/report-output-surface.ts:153)

### Reproducible input provenance comparison

```bash
offline env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null LC_ALL=C bun run --no-install - <<'JS'
import {execFileSync} from 'node:child_process';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import assert from 'node:assert/strict';
import {repositoryIdentity,buildRunInputFingerprint} from './apps/worker/src/ai/sast/capella/artifacts.ts';
import {RepositoryConfinement} from './apps/worker/src/ai/sast/capella/tools/confinement.ts';
const dir=resolve(await mkdtemp('../../.shannon-review.'));
try {
  const git=(...args)=>execFileSync('git',args,{cwd:dir});
  git('init','-q','--template=');
  git('config','user.name','Offline Fixture');
  git('config','user.email','fixture@example.invalid');
  const source=join(dir,'sample.txt');
  await writeFile(source,'one');
  git('add','sample.txt');
  git('commit','-qm','fixture base');
  const reader=await RepositoryConfinement.create({repositoryRoot:dir});
  const settings={modelSpec:'fixture',capellaFormatVersion:'1',promptSetVersion:'fixture',
    codePathAvoids:[],codePathFocus:[],pipelineTestingMode:false};
  const key=()=>repositoryIdentity(dir).then(id=>buildRunInputFingerprint(settings,id));
  const before=await key();
  assert.equal((await reader.readFile('sample.txt')).bytes.toString(),'one');
  await writeFile(source,'two');
  assert.equal((await reader.readFile('sample.txt')).bytes.toString(),'two');
  assert.equal(await key(),before);
  git('add','sample.txt');
  git('commit','-qm','fixture edit');
  assert.notEqual(await key(),before);
  console.log('working bytes changed, key stable until Git HEAD changed');
} finally {await rm(dir,{recursive:true});}
JS
```

This is a source-identity fixture. It invokes no stage, performs no vulnerability analysis, and uses no substantive repository content. [Input fingerprint](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/artifacts.ts:104), [Confined source read](repos/KeygraphHQ__shannon/apps/worker/src/ai/sast/capella/tools/confinement.ts:325)

### Audit receipt replay

This control uses the actual audit facade and metrics tracker. The external package shims reject unexpected requests. The fixture records one terminal summary with deterministic values, alongside synthetic ordinary attempts.

```bash
offline bun run --no-install - <<'JS'
import {mock} from 'bun:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import path,{join,resolve} from 'node:path';
const blocked=()=>{throw new Error('live dependency blocked by fixture');};
mock.module('zx',()=>({$:blocked,fs,path}));
mock.module('@earendil-works/pi-ai',()=>({isContextOverflow:blocked,isRetryableAssistantError:blocked}));
mock.module('@earendil-works/pi-coding-agent',()=>({getAgentDir:blocked,ModelRuntime:{create:blocked}}));
const {AuditSession}=await import('./apps/worker/src/audit/audit-session.ts');
const base=resolve(await mkdtemp('../../.shannon-review.'));
try {
  const meta={id:'audit-fixture',webUrl:'https://example.invalid',outputPath:base};
  const workflowId='audit-fixture_shannon-10';
  await new AuditSession(meta).initializeDurableScanState(workflowId,false,'fresh');
  const sessions=Array.from({length:3},()=>new AuditSession(meta));
  await Promise.all(sessions.map(s=>s.initialize(workflowId)));
  const result={success:true,attemptNumber:1,duration_ms:100,cost_usd:0.125};
  const names=['pre-recon','recon','validate-authentication'];
  await Promise.all(sessions.map((session,i)=>session.endAgent(names[i],result)));
  const data=async()=>JSON.parse(await readFile(join(base,meta.id,'.shannon','session.json'),'utf8'));
  assert.equal((await data()).metrics.total_cost_usd,0.375);
  await sessions[0].endAgent(names[0],result);
  assert.equal((await data()).metrics.total_cost_usd,0.5);
  assert.deepEqual((await data()).metrics.agents[names[0]].attempts.map(a=>a.attempt_number),[1,1]);
  const run={status:'completed',startedAtMs:1000,endedAtMs:2000,usageAccountingComplete:true,
    usageAccountingWarnings:[],operationalMetrics:{},operationalStages:{}};
  const first=await sessions[0].recordTerminalWorkflowMetrics(workflowId,run);
  assert.deepEqual(await sessions[0].recordTerminalWorkflowMetrics(workflowId,run),first);
  assert.equal(Object.keys((await data()).metrics.runs).length,1);
  console.log('three independent entries survived, ordinary receipt doubled, terminal receipt was idempotent');
} finally {await rm(base,{recursive:true});}
JS
```

The separate multi-process marker check used four external Node 22 processes, each loading the local `LogStream` with a relative `.js`-to-`.ts` resolver hook and opening the same inert log. The parent sent all four an IPC start message after every process acknowledged its open. Log line counts across twelve runs were `1,4,3,4,4,4,3,4,4,4,4,4`. A single process with four simultaneous appends produced one line. [LogStream scope and reference counting](repos/KeygraphHQ__shannon/apps/worker/src/audit/log-stream.ts:128)

## 10. Execution policy

This turn covered one repository serially. No queue entry or repository source was changed. The rubric enumerates nine report sections and then gives a separate “Execution policy” heading. This report retains that heading as section ten. [Evaluation protocol](./README.md:1)

The delivered appendix's ten Bash blocks were executed together with `bash -e -o pipefail`. All exited zero. A structural audit verified ten numbered headings, all local source-link paths and line bounds, and the absence of retained scratch directories.
