# zetbrush/multiagents offline architecture and reliability evaluation

## 1. Snapshot, scope, and elapsed-time evidence

| Field | Value |
| --- | --- |
| Repository | repos/zetbrush__multiagents |
| Pinned commit | `6038986b739937aaf3f2da2346e97a25f00369b1` |
| Commit subject | Merge pull request #10 from zetbrush/docs/readme-current-state |
| Package and checkout | `multiagents` 0.7.0. Bun and TypeScript. 77 tracked files in a shallow checkout. |
| Start UTC | 2026-11-19 16:36:16 UTC |
| End UTC | 2026-11-19 17:07:20 UTC |
| Elapsed | 31.07 minutes. Fresh active investigation exceeded 30 minutes. |
| Integrity | Exact pinned HEAD and empty porcelain status at entry and exit. The exit check also produced no `git clean -ndx` candidates. |
| Test platform | Linux x86-64, Bun 1.4.2, Node 26.13.1, npm 11.20.0, TypeScript 5.9.3. Primary SQLite experiments used Btrfs. Focused controls also ran on tmpfs. |

Multiagents is a local coordination service for small, supervised provider teams. A durable slot and retained mailbox make ordinary agent replacement practical. The strongest tested failure modes were in the boundary between that durable state and the controller's in-memory process ownership. A completed SQLite write, a started subprocess, and a live provider thread are three different facts. Several paths treat one as evidence of the others. That shows up as successful-looking archive or resume operations with an orphan or an absent worker, and as reviews or messages closing before the intended recipient has processed them. [Broker schema](repos/zetbrush__multiagents/broker.ts:85), [controller ownership](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:45), [driver delivery](repos/zetbrush__multiagents/orchestrator/delivery.ts:45).

This review covered orchestration, task state, provider and tool protocols, messaging, recovery, concurrency, workspace identity, observability, and package/runtime contracts. Dashboard integration tests ran as part of the repository suite. GUI design was outside scope. I archived the exact commit to a disposable directory inside the evaluation workspace and used private databases, project trees, homes, stdio fixtures and loopback services. I checked out no other commit. The network namespaces had only loopback and no external route. I used no accounts, credentials, provider binaries or remote services. The pre-existing report was an unfinished artifact. I used its headings to resolve the numbering discrepancy and used pre-existing local dependency materials for staging. I ran all measurements in this report fresh. The evaluation README enumerates nine required headings. They appear first in the prescribed order, followed by the requested tenth section on prioritized improvements. [Evaluation protocol](./README.md:1), [package and test entry points](repos/zetbrush__multiagents/package.json:8), [CI](repos/zetbrush__multiagents/.github/workflows/ci.yml:11).

| UTC activity | Fresh investigative work and sampled evidence |
| --- | --- |
| 16:36:16–16:39:08 | Read the evaluation protocol, verified the checkout, staged the pinned source and isolated dependencies, ran the full suite, traced the SQL and ran B1–B6. The first suite ran 16:37:04–16:37:23. |
| 16:39:08–16:43:49 | Traced launch, driver registration, review and recovery. Ran O1–O5, checked SDK transport internals, tested offline installation and repeated the full suite with UID 1000 and two SDK versions. Repeated broker controls on tmpfs. |
| 16:43:49–16:48:43 | Tested project identity, config migration and CLI/MCP parity. Exercised live local stdio paths for D1–D5 and natural scheduler ticks for S1–S4. Compared one-controller and two-controller ownership. |
| 16:48:43–16:54:52 | Profiled broker queue scans, writer contention and storage sensitivity. Ran real orchestrator tick controls for P1–P7, including a 64.9-second interruption and a watchdog duplicate. Checked monitor accounting, health contracts and partial launch. |
| 16:54:52–17:07:20 | Ran repeat workloads and cross-SDK cancellation, tested the extracted package, audited test counts and archived source bytes, corrected and reran combined fault controls, reproduced from the embedded shell, and verified checkout and citation integrity. The final standalone canceled-delivery control completed at 17:07:13. |

Long-running controls overlapped source tracing, fixture review and cross-checks. I used the longer natural timers for the policy decisions they actually exercise. The UTC interval excludes the previous attempt and contains no wait inserted to meet the time criterion. The host's UTC clock and `/proc/uptime` were sampled together near entry and again at exit. Uptime advanced from 380,630.79 s at 16:36:22 to 382,489.42 s at 17:07:20. That agrees within the sampling interval with the 1,858-second UTC difference between these two samples. Short timings below come from local monotonic process clocks. The test suite's elapsed times, whole-investigation time and simulated provider clocks measure different things.

## 2. Core architecture and end-to-end control/data flow

### Entry points and authorities

The package ships four Bun executables. The CLI handles install/configuration, daemon and session commands, and dispatch to the MCP servers. The broker is a long-running HTTP process on `127.0.0.1` with a default per-user SQLite database. An MCP controller invoked by a host owns its own managed-process and driver maps. Each provider can run a second MCP process for peer tools. Interactive providers can use their peer tools without a controller. The library entry exports the broker client, constants and TypeScript shapes. This is a small local control plane with SQLite underneath it and provider-specific turns above it. It requires neither a second DB service nor a model SDK in the orchestration process. [Package executables](repos/zetbrush__multiagents/package.json:8), [broker startup](repos/zetbrush__multiagents/broker.ts:69), [listener](repos/zetbrush__multiagents/broker.ts:1344), [CLI dispatch](repos/zetbrush__multiagents/cli/commands.ts:162), [adapter dispatch](repos/zetbrush__multiagents/server.ts:15), [library exports](repos/zetbrush__multiagents/index.ts:15).

| Boundary | Durable state or responsibility |
| --- | --- |
| Broker | Session, stable slot, ephemeral peer registration, mailbox rows with delivery stamps, plan items, file leases and ownership, shared knowledge, guardrail overrides and some event records. SQLite WAL supplies local durable commits. |
| MCP controller | Admits foreground commands, launches processes, tracks local process objects and drivers, invokes provider protocol operations, coordinates periodic checks, carries pending status events and in-memory restart history. These objects disappear at controller exit. |
| Provider and peer MCP service | The provider owns its conversation, output stream and tool execution. A local adapter registers the peer, provides callable team tools and brings teammate mail into the provider's interaction. Driver-managed adapters keep the tool registration but mostly cede delivery. |
| Project directory | A shared cwd and Git tree, `.mcp.json`, `.multiagents/session.json`, provider-specific driver or PID markers, optional Markdown inboxes. Separate provider conversation IDs live in slot snapshots. Codex and Gemini also receive per-user config changes. |

[Database tables and migrations](repos/zetbrush__multiagents/broker.ts:85), [slot and peer identity types](repos/zetbrush__multiagents/shared/types.ts:66), [controller maps](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:45), [config writer](repos/zetbrush__multiagents/orchestrator/launcher.ts:156), [adapter registration](repos/zetbrush__multiagents/adapters/base-adapter.ts:466), [file inbox](repos/zetbrush__multiagents/adapters/inbox.ts:9).

### Admission, assignment and review

1. `create_team` takes the caller's project directory, session name, typed provider list, roles and initial tasks. It probes the CLIs, constructs a slug after reading current sessions, creates the project directory and uses existing Git or initializes it. It commits the session before launching workers. An optional team plan is created after launches. Repeating the same name normally creates a suffixed session. [MCP entry](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:665), [admission and create](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:672).
2. A launch writes MCP configuration, adds a broker slot, attempts ownership assignment, records the workspace's most recent slot and passes the provider its cwd and initial task. Expensive calls happen across multiple process and HTTP boundaries. Within one create/resume request, repeated provider kinds are delayed by three seconds to reduce shared provider-initialization conflicts. `add_agent` launches immediately via the same launcher. `trackLaunch` installs monitoring and process ownership once the launcher returns. [Admission loop](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:747), [added workers](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:933), [launch adapter](repos/zetbrush__multiagents/orchestrator/launcher.ts:619), [tracking](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:106).
3. The caller apportions work. The controller gives each plan row a stable slot reference by matching the name or falling back to the last launched slot. The plan is an ordered, mutable status board. The broker can store a parent item ID, counts rows with status `done`, and can replace the session's plan. Worker prompts and team tools carry instructions for collaboration, roles, reporting and recovery. No process is waiting on a plan-item dependency transition. Agents can start their real work before plan assignment arrives. [Plan dispatch](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:778), [plan persistence](repos/zetbrush__multiagents/broker.ts:1194), [worker planning tools](repos/zetbrush__multiagents/adapters/base-adapter.ts:1524), [task prompt](repos/zetbrush__multiagents/orchestrator/launcher.ts:339), [team protocol](repos/zetbrush__multiagents/adapters/protocol-text.ts:1).
4. A slot keeps connection state, pause state and task state independently. Its nominal task sequence is `idle → working → done_pending_review → approved → released`, with actionable feedback routing back through `addressing_feedback`. `signal_done` emits messages to connected slots and auto-approves reviewer-like roles based on a name regex. Other approvals are aggregated from historical message rows and current slot roles. Registration and work are asynchronous, so an existing slot may be disconnected, connected without a peer, connected with a peer, or recently detached while a process is still exiting. [Task model](repos/zetbrush__multiagents/shared/types.ts:31), [task transitions](repos/zetbrush__multiagents/broker.ts:1480), [adapter completion](repos/zetbrush__multiagents/adapters/base-adapter.ts:1383), [working transition](repos/zetbrush__multiagents/orchestrator/monitor.ts:169).
5. Session `active`, `paused` and `archived` are recorded status values. The CLI and MCP workflow apply different process and mailbox effects to them. The MCP end handler removes local ownership, signals local processes, marks slots disconnected, and archives. Delete also removes session rows and associated data. Broker shutdown is a distinct path that signals registered peer PIDs. Operators call resumptions explicitly and the controller may also perform several automatic respawn paths while running. [MCP end, delete and resume](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1191), [CLI session lifecycle](repos/zetbrush__multiagents/cli/session.ts:130), [broker delete](repos/zetbrush__multiagents/broker.ts:835), [broker signal handler](repos/zetbrush__multiagents/broker.ts:1652).

### Provider and tool boundaries

| Provider | Start and identity | Output, work and delivery |
| --- | --- | --- |
| Claude | Long-lived CLI in stream-json mode. Inline MCP includes explicit session and slot arguments and an optional broker port override. The first prompt precedes the init event. A saved provider session ID is passed with `--resume`, with a fresh launch fallback. | New teammate text is written as stdin user input. Echo text resolves in-flight delivery. Assistant output and results update activity and usage. Stdin EOF is the cooperative stop path. A standalone Claude adapter can push best-effort channel notifications outside this driver path. |
| Codex | Persistent app-server via newline-delimited JSON-RPC. Initializes, starts a thread and short bootstrap turn, then sends the real task in another turn. A separate MCP process can attach to the slot. Crash recovery tries `thread/resume`, with thread/start fallback. | Active turns accept `turn/steer`, idle sessions get a new `turn/start`, and `turn/interrupt` can end a turn. Request IDs and early notification caches handle responses and fast output arriving in the same chunk. Usage and progress come from app-server notifications. |
| Gemini | Plain `npx @google/gemini-cli` child with stream-json output. Project plus global config, environment and a PID-addressed marker help the separate adapter register. | The controller monitors stdout/stderr and exit. The standalone adapter polls the broker and stages tool-result text and a file inbox. Recovery respawns the CLI with a handoff prompt. There is no parallel driver API for this provider. |

[Claude command, timeouts and stream](repos/zetbrush__multiagents/orchestrator/claude-driver.ts:63), [Claude and Codex launcher](repos/zetbrush__multiagents/orchestrator/launcher.ts:424), [Codex handshake and turn model](repos/zetbrush__multiagents/orchestrator/codex-driver.ts:210), [turn correlation](repos/zetbrush__multiagents/orchestrator/codex-driver.ts:367), [Gemini launch](repos/zetbrush__multiagents/orchestrator/launcher.ts:585), [Gemini CLI args](repos/zetbrush__multiagents/orchestrator/launcher.ts:749), [session handoff](repos/zetbrush__multiagents/orchestrator/recovery.ts:138).

The model-facing tools are an MCP request/response contract backed by the broker's internal HTTP API. The local provider trust boundary varies. Claude launches with skipped prompts and an inline strict MCP config. Codex launches workspace-write and supplies a turn sandbox with the project writable, network access and tmp access. Approval messages received by its driver have explicit response shapes. Command and file approvals are accepted for the session, session permission requests are granted as supplied, elicitation is declined, user input gets empty answers and dynamic tools get an error-shaped result. Gemini uses its own CLI sandbox and approval configuration. These are unattended execution choices in the provider, not a broker-enforced policy for file writes or network access. Real provider isolation semantics were outside the offline tests. [Claude arguments](repos/zetbrush__multiagents/orchestrator/claude-driver.ts:63), [Codex sandbox](repos/zetbrush__multiagents/orchestrator/codex-driver.ts:76), [provider request routing](repos/zetbrush__multiagents/orchestrator/codex-driver.ts:642), [Gemini args](repos/zetbrush__multiagents/orchestrator/launcher.ts:749), [role tool descriptions](repos/zetbrush__multiagents/adapters/base-adapter.ts:64).

### Mailbox and supervision

A send records peer and, when known, stable slot identity. Slot routing can synthesize a target before an adapter registers. A normal poll consumes. A retained poll records handoff in `delivered` and leaves `acked_at` empty. A later explicit ack is idempotent for a given message ID. A slot-backed message is available to the next peer binding. A pause blocks polls and marks new messages held. A separate release update clears held messages within the session. A history query and reconnect recap serve different roles from the unread queue. [Send and poll](repos/zetbrush__multiagents/broker.ts:602), [ack](repos/zetbrush__multiagents/broker.ts:681), [recap](repos/zetbrush__multiagents/broker.ts:474), [hold and release](repos/zetbrush__multiagents/broker.ts:1308).

Standalone adapters serialize the broker poll, stage new messages by ID, decorate the next tool result and retry failed acks. Push and file notifications are best effort. A driver-mode `check_messages` consumes only unclaimed rows. The controller retains and delivers by slot. Claude tracks one write per in-flight ID until echo, Codex acks a steer response immediately, and an idle Codex forwarding turn acks on the driver's resolved result. None of these local confirmations proves that the user's underlying task was completed. [Adapter poll and ack](repos/zetbrush__multiagents/adapters/base-adapter.ts:949), [driver-mode check](repos/zetbrush__multiagents/adapters/base-adapter.ts:1172), [provider-specific delivery](repos/zetbrush__multiagents/orchestrator/delivery.ts:45).

| Mechanism | Default behavior |
| --- | --- |
| Broker liveness and adapter | Live probe on `/health`, registration before or alongside MCP handling, 15 s adapter heartbeat, 30 s broker stale scan, 0.3–1 s standalone polls by provider. PID existence and heartbeat age serve different purposes. |
| Driver tick | One 3 s delivery pass per controller at a time. It walks all registered drivers, can wait on Codex steer or interrupt, and checks released slots. Codex heartbeat requests are separate from model-output activity. |
| Release | With no pending mail and idle provider output the controller stops owned drivers. The verdict allows 60 s of recent turn activity and uses a 10 minute cap from the first release observation. Claude close adds its own EOF and signal grace. |
| Supervision | Crash and code-zero restart histories have separate 5 minute windows, with a threshold of three exits. The 10 s inbox watchdog uses read/unclaimed evidence by connection state, 120 s connected staleness and 45 s between attempts per slot. |
| Other clocks | Git conflict checks every 10 s, escalation history every 15 s, completion checks every 15 s with a grace period, guardrails every 30 s, status nudges every 45 s, old disconnected slots swept every 60 s after five minutes. |

[Defaults](repos/zetbrush__multiagents/shared/constants.ts:13), [broker PID cleanup](repos/zetbrush__multiagents/broker.ts:320), [driver delivery and release](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1546), [release and watchdog verdicts](repos/zetbrush__multiagents/orchestrator/supervision.ts:83), [restart rules](repos/zetbrush__multiagents/orchestrator/recovery.ts:35), [completion and watchdog](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1763).

## 3. Why the design works and its governing invariants

- **Logical identity survives provider replacement.** A slot is the unit of team assignment and mailbox continuity. A peer represents the current adapter or local process registration. Reusing the slot rather than minting one on every respawn keeps the plan, review, file ownership and message destination stable. A shallow broker-side context patch preserves distinct fields written by monitor and launcher. The WAL restart passed a kill and restart with acknowledged and unacknowledged messages coexisting. [Broker slot and peer binding](repos/zetbrush__multiagents/broker.ts:441), [slot-targeted read](repos/zetbrush__multiagents/broker.ts:418), [context merge](repos/zetbrush__multiagents/broker.ts:932), [WAL init](repos/zetbrush__multiagents/broker.ts:83).
- **Liveness is a best-effort observation through multiple owners.** For registered peers the stale sweep probes PID existence, catches any error as dead and uses heartbeat age to evict a different class of sessionless peers. This relies on same-user visibility and an unreused PID. For driver-only slots the controller's subprocess object is stronger evidence while the controller is live. The database does not preserve that distinction across restart. The experiments exercised owned same-user children. PID reuse and another user's permissions remain code-path concerns rather than measured incidence. [Stale peer scan](repos/zetbrush__multiagents/broker.ts:320), [driver disconnect](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:138), [resume predicate](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1327).
- **Work state and process state carry different information.** A provider can finish a turn while its role continues, fail during a valid handoff, or die while waiting for review. Separate task and connection state lets recovery treat code zero with unfinished work differently from a deliberate release. The release-before-kill sequence and conditional driver detachment are useful when callbacks from an old child race with a replacement. The intended invariant still needs durable generation checks. [Exit handlers](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:138), [completion recovery](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:327), [explicit remove](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:977), [driver registry](repos/zetbrush__multiagents/orchestrator/supervision.ts:35).
- **The broker can retain work independently of provider delivery.** Recording a handoff and an ack separately lets a driver exit before echo without destroying the row. Retain supports at-least-once attempts when the sender and receiver survive a restart, while older clients can keep consuming polls. In-flight IDs prevent routine duplicate Claude writes. Exactly-once model processing would require correlation and idempotency at the provider boundary as well as in SQLite. [Ack migration](repos/zetbrush__multiagents/broker.ts:276), [handoff pipeline](repos/zetbrush__multiagents/broker.ts:655), [Claude pending IDs](repos/zetbrush__multiagents/orchestrator/delivery.ts:107), [exit fixture](repos/zetbrush__multiagents/tests/delivery-loop.test.ts:153).
- **There is a real benefit to narrowly scoped supervision.** `RespawnGuard.run` sets the in-flight flag before its first await and clears it in a finally block. `DriverRegistry.detach` compares the object that actually exited. `nonOverlapping` enforces one in-flight tick. Treating claimed mail as waiting on the next tool call avoids killing an otherwise active standalone agent for one delivered row. These rules are enforceable within a controller and are small enough to unit-test independently. [Respawn guard](repos/zetbrush__multiagents/orchestrator/respawn-guard.ts:7), [pure supervision](repos/zetbrush__multiagents/orchestrator/supervision.ts:12), [supervision tests](repos/zetbrush__multiagents/tests/supervision.test.ts:1).
- **The shared workspace is a deliberate collaboration contract.** All workers see the same current tree, so a worker can review a teammate's changes without synchronizing worktrees or moving artifacts. Broker-side ownership patterns and expiring locks give cooperative tools a common view of intent. A local Git probe supplies progress and detects unmerged paths. The invariant is cooperation by the participating agents. Filesystem writes go through their provider tools and can occur without a lease. [Work directory and launch](repos/zetbrush__multiagents/orchestrator/launcher.ts:301), [file lease checks](repos/zetbrush__multiagents/broker.ts:977), [conflict monitor](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1685), [repo-local summaries](repos/zetbrush__multiagents/shared/summarize.ts:17).
- **Centralized local state has a simple installation and failure model.** Each HTTP mutation's synchronous SQL body executes on the broker event loop. This makes the common one-broker case easy to reason about. A sequence of SQL calls still crosses individual commit boundaries, and control loops and provider I/O interleave at awaits. The implementation has no session-scoped owner epoch, multi-object mutation transaction boundary, or durable active-turn record. The design works best with a single controlling client, prompt provider acknowledgments, explicit review, and active operator supervision. [Broker runtime](repos/zetbrush__multiagents/broker.ts:1344), [SQLite setup](repos/zetbrush__multiagents/broker.ts:85), [multi-step session deletion](repos/zetbrush__multiagents/broker.ts:835), [process ownership](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:80).

## 4. What it does well and poorly, with source evidence

### Strengths

- **A compact local system with isolated protocol parts.** The broker, process launcher, adapters and drivers communicate across small interfaces. It is possible to exercise actual schema migrations, inbox persistence, stdio wire order and monitor behavior locally. Pure supervision functions have command-independent tests. [Broker client](repos/zetbrush__multiagents/shared/broker-client.ts:47), [driver delivery](repos/zetbrush__multiagents/orchestrator/delivery.ts:17), [supervision](repos/zetbrush__multiagents/orchestrator/supervision.ts:11), [MCP test client](repos/zetbrush__multiagents/tests/helpers/mcp-stdio-client.ts:17).
- **Resumption carries useful context.** Crash recovery reconstructs role, summary, recent clipped messages and roster, then tries the existing conversation for both drivers. Manual resume additionally includes assigned plan rows. Retained mail remains in the broker and follows the slot. B4, S1 and P5 exercised the durability and lifecycle pieces. [Crash handoff](repos/zetbrush__multiagents/orchestrator/recovery.ts:138), [manual handoff](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1353), [slot mailbox](repos/zetbrush__multiagents/broker.ts:418).
- **Provider differences are explicit.** Startup context, Claude's delayed init and echo, split JSONL frames, Codex's early notifications and steer races, and no-push adapter paths have separate implementations and fixtures. Codex attaches request timeouts and rejects pending operations on process exit. Claude has cooperative close followed by TERM/KILL escalation while its owner is running. [Claude driver](repos/zetbrush__multiagents/orchestrator/claude-driver.ts:130), [Codex driver](repos/zetbrush__multiagents/orchestrator/codex-driver.ts:170), [driver wire tests](repos/zetbrush__multiagents/tests/codex-driver.test.ts:1), [adapter deliveries](repos/zetbrush__multiagents/tests/adapter-delivery.test.ts:118).
- **Cooperative release works.** Lifecycle feedback and approval are visible to agents and kept with the session. A driver that knows it is released can drain its queue and stop without respawning. The older inbox migration acknowledges already-consumed historical messages to avoid a rollout replay flood. [Lifecycle notifications](repos/zetbrush__multiagents/broker.ts:1495), [review aggregation](repos/zetbrush__multiagents/broker.ts:1535), [release verdict](repos/zetbrush__multiagents/orchestrator/supervision.ts:100), [message migration](repos/zetbrush__multiagents/broker.ts:276).

### Reliability findings

| Priority | Failure and root cause | Direct and source evidence |
| --- | --- | --- |
| Critical | **Session end leaves in-flight launches unfenced.** A launch commits the session and starts a child before ownership is visible to stop. The later callback repopulates a dropped process map. A failing second spawn also leaves live work in an active, partially built team. Retrying creates another session. | O4 archived during startup, then listed the same archived session as managed with its child alive. N1 returned an MCP error with a live first worker and a second disconnected slot. [Startup commit](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:739), [ownership publication](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:106), [archive](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1191). |
| Critical | **Ownership stays local to controller memory.** A durable slot carries no owner generation. Resume trusts a connected slot, even after losing a peerless driver. Two controllers can launch against the same slot. Even one controller can launch two plain processes when the watchdog kill and its exit callback independently restart a worker. | O2 false-online slot after controller death, S3 duplicated PIDs across controllers, and P7 two live Gemini fixtures in one controller. End stopped the last one only. [Local maps](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:45), [manual resume filter](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1327), [watchdog separation](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1912), [plain process callback](repos/zetbrush__multiagents/orchestrator/monitor.ts:112). |
| Critical | **Stop owns direct subprocesses, with inconsistent waiting and escalation.** Codex signals and marks its driver dead without observing exit. The plain process path signals a PID and drops the map. Controller SIGTERM calls process.exit immediately after scheduling asynchronous kills. A failed Codex initialize rejects before the caller gains a process handle. | A descendant survived in P1, a resistant worker survived controller SIGTERM in P6, and a Codex child survived its failed handshake in D1. P5 and the explicit end in P6 corroborate the intended stop paths. [Stop](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:80), [shutdown](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1977), [Codex handshake](repos/zetbrush__multiagents/orchestrator/codex-driver.ts:210), [Codex kill](repos/zetbrush__multiagents/orchestrator/codex-driver.ts:356), [Claude escalation](repos/zetbrush__multiagents/orchestrator/claude-driver.ts:266). |
| High | **Task correctness is derived from coarse role and slot state.** The approval query counts all historical approvals for one slot. Completion can mark every assigned plan row done from one text report, including blocked work. A cached idle slot can subsequently write working over a newer completion. The completion timer counts disconnected slots as done and approves orphaned authors if the reviewer-like slots are gone or finished. | B1, W3, S2. [Approve query](repos/zetbrush__multiagents/broker.ts:1554), [slot update](repos/zetbrush__multiagents/broker.ts:912), [summary transition](repos/zetbrush__multiagents/adapters/base-adapter.ts:1143), [auto-plan update](repos/zetbrush__multiagents/adapters/base-adapter.ts:1393), [auto-approval](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1763). |
| High | **Acknowledgments describe different events on different paths.** A driver-mode tool poll can consume before MCP sends its reply. Codex idle forwarding accepts a resolved interrupted result. A failed ack can replay the whole input. Claude's exact echo never expires on a live driver. SDK cancellation scopes do not reach launch or delivery-side effects. | O3 and D2–D5. [MCP request handler](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:665), [adapter dispatch](repos/zetbrush__multiagents/adapters/base-adapter.ts:895), [driver-mode polling](repos/zetbrush__multiagents/adapters/base-adapter.ts:1005), [driver ack points](repos/zetbrush__multiagents/orchestrator/delivery.ts:62), [interrupted status](repos/zetbrush__multiagents/orchestrator/codex-driver.ts:412). |
| High | **Workspace config doubles as identity.** The workspace marker wins over explicit session env, and the driver-mode marker is shared by the entire project. A plain TOML legacy section can spin in the launcher or consume a neighboring section. The latest-slot hint is written but unused by standalone resolution. | W1, W2. [Config loop](repos/zetbrush__multiagents/orchestrator/launcher.ts:192), [shared marker](repos/zetbrush__multiagents/orchestrator/launcher.ts:522), [latest-slot writer](repos/zetbrush__multiagents/orchestrator/launcher.ts:648), [adapter identity precedence](repos/zetbrush__multiagents/adapters/base-adapter.ts:440), [identity fallback](repos/zetbrush__multiagents/adapters/base-adapter.ts:593). |
| High | **Broker invariants depend on route and timing.** Overlapping registrations keep two peer rows for one slot. Peer discovery can remove the row the janitor needs to capture context and release locks. Plan replacement lacks a transaction across delete and insert. Expired leases remain physically unique until sweep, so normal reacquisition can fail. Ownership assignment checks exact pattern equality, while acquisition denies any match against someone else's pattern. | B2, B3 and B5–B7. [Registration](repos/zetbrush__multiagents/broker.ts:447), [liveness cleanup](repos/zetbrush__multiagents/broker.ts:320), [list side effect](repos/zetbrush__multiagents/broker.ts:590), [plan replace](repos/zetbrush__multiagents/broker.ts:1200), [lease query](repos/zetbrush__multiagents/broker.ts:1002), [ownership matcher](repos/zetbrush__multiagents/broker.ts:1041). |
| High | **Restart policy is split across heuristics and a disconnected guardrail.** Crash-loop suppression and the mail watchdog disagree. The adjustable stop limit counts an event name no normal exit path writes. Its trigger produces a status event without stopping the worker. The silence handler requests work completion after interrupting a quiet running turn. Pause affects mailbox flow. | S1, R3, P2, P4, P7. [Crash threshold](repos/zetbrush__multiagents/orchestrator/recovery.ts:43), [watchdog gates](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1867), [guardrail event count](repos/zetbrush__multiagents/broker.ts:1123), [stop action](repos/zetbrush__multiagents/orchestrator/guardrails.ts:112), [silence path](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1552), [pause handler](repos/zetbrush__multiagents/orchestrator/session-control.ts:131). |
| Medium | **Route semantics and responses disagree.** The controller's direct, broadcast and immediate plan paths require a peer ID even on a connected driver-addressable slot. Release-all excludes idle slots. CLI resume sets the session active while leaving paused slots and held rows. CLI sends omit session ID, leaving paused-slot messages held after ordinary resume. | O1, O5, W5. [Direct and broadcast calls](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:899), [direct plan delivery](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:799), [release-all predicate](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1114), [CLI resume](repos/zetbrush__multiagents/cli/session.ts:130), [CLI send](repos/zetbrush__multiagents/cli/commands.ts:201), [held release](repos/zetbrush__multiagents/broker.ts:1313). |
| Medium | **Slow work delays unrelated work.** The delivery loop serializes all drivers, so awaiting one RPC blocks later slots and skips new ticks. The broker uses synchronous SQLite with a 3 s busy timeout. Mail queries scan and sort history and hand off unbounded batches with a write per row. Resource monitors impose no effective queue or team admission limit. | P3 and R1–R2. [Global tick](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1602), [delivery wait](repos/zetbrush__multiagents/orchestrator/delivery.ts:66), [busy timeout](repos/zetbrush__multiagents/broker.ts:85), [mail queries](repos/zetbrush__multiagents/broker.ts:418), [row-wise handoff](repos/zetbrush__multiagents/broker.ts:681). |

## 5. Core-code quality: decomposition, state, concurrency, errors, types, tests, observability, extensibility, and maintainability

**Decomposition and state.** The supervision helpers, guardrail evaluation, launcher contracts, session-control helpers, broker wrapper and provider drivers are useful isolation points. `broker.ts` (1,667 lines), `orchestrator-server.ts` (1,987) and `base-adapter.ts` (1,795) aggregate schema, state and dispatch decisions across roughly 5,449 lines. HTTP handlers, asynchronous exit callbacks, request handlers, adapter caches, monitors and background loops all change lifecycle state. Numerous writes have a slot ID in common without a generation check. A conditional driver object delete protects one stale local callback. It cannot stop an already-running asynchronous database update from losing a newer owner transition. [Schema and handlers](repos/zetbrush__multiagents/broker.ts:83), [controller tracks and exit](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:106), [adapter state](repos/zetbrush__multiagents/adapters/base-adapter.ts:400), [guard helpers](repos/zetbrush__multiagents/orchestrator/supervision.ts:12).

**Concurrency and errors.** Synchronous handlers provide some intra-broker serialization. HTTP calls, provider operations and scheduler callbacks interleave at awaits. Several async intervals lack an overlap guard. Tool handler exceptions produce MCP `isError` in many paths. Other semantically unsuccessful results return text with no error flag or HTTP 200 with `ok: false`. Some callers do not check that flag. Silent catches around config, recovery, status and metrics hide outages alongside genuinely optional work. Most HTTP errors lack a retry class, required recovery action, or durable operation ID. [Tool catch](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1490), [tick guards](repos/zetbrush__multiagents/orchestrator/supervision.ts:69), [unguarded intervals](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1502), [HTTP response adapter](repos/zetbrush__multiagents/shared/broker-client.ts:50), [send results](repos/zetbrush__multiagents/broker.ts:602), [announce](repos/zetbrush__multiagents/orchestrator/launcher.ts:802).

**Types and schema.** TypeScript enables strict mode, unchecked index checks and override checks. The type interfaces cover many entities and provider protocol results, and `DriverSlot` is a useful discriminated union. SQLite returns pause, held and delivered as numeric flags while domain types declare booleans, so some callers test both. The broker casts inbound request JSON and accepts free-form task state in its general slot update. Slot context is an unversioned JSON string with both safe merges and unguarded parses. Migration catches all ALTER errors, folding duplicate columns and unrelated failures into the same result. Runtime validation and a versioned event contract would reduce the gap between internal types and wire state. [TypeScript config](repos/zetbrush__multiagents/tsconfig.json:17), [slot and message types](repos/zetbrush__multiagents/shared/types.ts:81), [migration](repos/zetbrush__multiagents/broker.ts:246), [generic update](repos/zetbrush__multiagents/broker.ts:912), [HTTP body](repos/zetbrush__multiagents/broker.ts:1358), [context parse](repos/zetbrush__multiagents/orchestrator/progress.ts:67).

**Tests.** The useful layers are pure supervision, real broker subprocesses with temporary databases, real MCP subprocesses, provider wire fakes and two opt-in credentialed integrations. Fast fixtures check request shapes, state changes, approval replies and delayed echo/steer paths. They model specific protocol versions named in comments. Upstream tests use fixed ports, `/tmp` and provider config resolution. Running them all safely required private networking, HOME and `/tmp`. The credential-free controller file has one test and checks nondefault broker port routing. The live controller test would cover more lifecycle integration. In the full offline run, the largest focused files were launcher (48 pass), update (33), Codex driver (20), delivery (18) and supervision (16), with one full controller process test. Important gaps include end racing launch, controllers sharing a slot, sidecar loss during restart, subprocess trees, budgets, canceled acknowledgments and partially created work. [Offline controller test](repos/zetbrush__multiagents/tests/orchestrator-server.test.ts:44). [CI](repos/zetbrush__multiagents/.github/workflows/ci.yml:11), [fixture version notes](repos/zetbrush__multiagents/tests/fakes/fake-codex-app-server.ts:2), [driver tests](repos/zetbrush__multiagents/tests/delivery-loop.test.ts:119), [adapter deliverability](repos/zetbrush__multiagents/tests/adapter-delivery.test.ts:118), [fixture homes](repos/zetbrush__multiagents/tests/launcher.test.ts:289), [live switch](repos/zetbrush__multiagents/tests/live-orchestrator.test.ts:15).

**Observability.** stderr is reserved from stdio protocol, progress materializes into slot snapshots, and telemetry includes usage, agent events and Git conflicts. The event table and controller event queue are separate. Operational metadata also has inconsistent cleanup scope. Deleting one session clears the process-wide monitor and crash maps, and explicit end clears all crash history. An operator managing multiple teams can lose accounting baselines or retry history for another still-running session. `get_team_status` destructively drains a controller-global array, including events from other sessions. Escalation reads a bounded recent window and deduplicates by sender and timestamp. Status uses separate broker reads and reports last connected in the last-activity field. Token accounting keys cumulative data by slot and moves its baseline before the database update succeeds. A fresh Codex thread can lose its first delta, reset during a resumed thread can double count, and a failed update creates a gap. A fast Claude first turn can finish before monitoring is installed. [stderr convention](repos/zetbrush__multiagents/shared/utils.ts:54), [slot usage deltas](repos/zetbrush__multiagents/orchestrator/monitor.ts:28), [Codex cumulative meter](repos/zetbrush__multiagents/orchestrator/monitor.ts:482), [status and events](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:853), [escalation scan](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1723), [progress view](repos/zetbrush__multiagents/orchestrator/progress.ts:105), [agent event table](repos/zetbrush__multiagents/broker.ts:1333), [cross-session monitor cleanup](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1217).

**Extensibility.** A peer adapter implements delivery, capability and instruction hooks. It can override tool handlers and reuse polling and registration. A managed provider needs coordinated source changes across type enums, command detection, config injection, launch, delivery, status and recovery. The exported `custom` type has no executable, and the server falls back to Claude adapter behavior. The TypeScript launch field `report_to` has no runtime routing policy. Provider differences are duplicated over launch, relaunch and crash code. That drift explains why one Codex recovery path resumes and the other bootstraps a fresh thread. [Base adapter hooks](repos/zetbrush__multiagents/adapters/base-adapter.ts:452), [provider enum](repos/zetbrush__multiagents/shared/types.ts:12), [launch config](repos/zetbrush__multiagents/shared/types.ts:424), [provider detection](repos/zetbrush__multiagents/orchestrator/launcher.ts:82), [adapter dispatch](repos/zetbrush__multiagents/server.ts:21), [manual relaunch](repos/zetbrush__multiagents/orchestrator/launcher.ts:701), [crash relaunch](repos/zetbrush__multiagents/orchestrator/recovery.ts:183).

## 6. Executed tests/experiments and their limitations

### Repository checks

| Run | Result |
| --- | --- |
| Bun 1.4.2 with staged MCP SDK 1.30.0, private root-mapped user, mount, PID and network namespaces | 262 pass, 3 skip, 0 fail, 695 assertions across 20 files. 18.51 s. |
| Bun 1.4.2 with SDK 1.30.0, Bubblewrap UID 1000 and private devices, tmp and loopback | 262 pass, 3 skip, 0 fail, 695 assertions across 20 files. 23.84 s. |
| Bun 1.4.2 with staged MCP SDK 1.26.0 and the same dependency tree, Bubblewrap UID 1000 | 262 pass, 3 skip, 0 fail, 695 assertions across 20 files. 23.92 s. O3, W4 and D5 also reproduced. This SDK is below the declared range and provides a sensitivity comparison. |
| Reproduction-shell repeat, SDK 1.30.0 | 262 pass, 3 skip, 0 fail, 695 assertions across 20 files. 18.45 s. The same report's Bubblewrap function also repeated the tmpfs peer cleanup and SDK 1.26.0 cancellation checks. |
| TypeScript and package | TypeScript 5.9.3 no-emit exited 0 with both SDK versions. Offline npm pack with scripts disabled produced multiagents-0.7.0.tgz, 46 entries, 664,375 unpacked bytes. The archive contained the broker, adapter, controller, both drivers and package manifest. Starting from the extracted tarball gave version 0.7.0, a genuine broker health response, 17 controller tools, 19 peer tools and successful session listing. |
| Exact dependency install | Frozen Bun resolves SDK 1.27.1. A closed-loopback-registry install could not find it and other exact tarballs. npm CI in strict offline mode failed ENOTCACHED. The main suite uses SDK 1.30.0, which satisfies the declared range, with the staged transitive tree. |

The three skips were two credentialed live tests and the real-lsof test. M5 checked the injected process-selection contract using a synthetic listener, a connected client and native ss output. Native lsof integration remains unverified. The calculator team is a standalone live script outside Bun test discovery and credential-free scope. Real provider service, actual account-dependent tool execution, macOS and Windows were outside the experiments. The fake providers introduce controlled message delays, errors and exits. The controls establish what the pinned coordination code does under those inputs. [CI](repos/zetbrush__multiagents/.github/workflows/ci.yml:11), [Bun lock](repos/zetbrush__multiagents/bun.lock:21), [package scripts](repos/zetbrush__multiagents/package.json:31), [live Claude](repos/zetbrush__multiagents/tests/live-claude.test.ts:21), [live controller](repos/zetbrush__multiagents/tests/live-orchestrator.test.ts:15), [lsof skip](repos/zetbrush__multiagents/tests/update.test.ts:130), [calculator integration](repos/zetbrush__multiagents/tests/e2e-team.ts:160).

### Focused results

| ID | Observation |
| --- | --- |
| B1 | QA alone left the author pending. QA plus lead approved. Actionable feedback reset the author, whose second submission became pending. The next QA approval alone made it approved by reusing the lead's older approval. |
| B2 | Baseline plan was 50% complete. A replacement with a valid prefix and missing second label failed 500. The new title and first item persisted. A corrected replacement succeeded. |
| B3 | Sweep-only cleanup kept the provider snapshot key and summary, duplicated one assigned item three times with three slots, and removed the lease. Listing peers before the sweep removed the peer first. The timer disconnected the slot with only the original provider key, leaving the still-valid lease. Both backing stores agreed. |
| B4 | Killed the broker with its WAL present and restarted the same DB. After a peer died and a new peer took the same slot, both rows appeared in recap but only the unacked one in the unread path. Ack retried with one change, then zero. |
| B5–B8 | Expired file lease disappeared from the lock list but reacquire returned UNIQUE constraint until explicit release. Two overlapping peer records both saw the retained slot mail. Old peer unregister detached the slot from its newer peer. Overlapping ownership globs both assigned and both denied the intersection. A standalone adapter served a tool call after SIGTERM while unreleased and exited 0 on SIGTERM after release. |
| O1 | A connected Codex slot without a peer was excluded from direct, broadcast and plan notification. The plan was durable. A real adapter then read the plan over MCP. Direct and broadcast mail reached the same driver and were acked. |
| O2 | The fake provider exited when its controller was killed. Peerless slot remained connected. Fresh controller resume reported one online and performed no spawn. Marking the slot disconnected enabled a new worker via thread/start. |
| O3–O5 | A canceled create request never replied, but kept its worker and session. Ending during a delayed startup archived the session, then the launch returned success with a live process under the archived session. Release-all skipped a connected idle slot that individual release successfully released. |
| W1 | Fresh config, a dotted legacy tool section and quoted legacy table all completed. A bare legacy table alone spun until the 650 ms deadline and used 59 CPU ticks. With a following unrelated section it completed and removed that section too. The quoted legacy entry remained alongside the new one. |
| W2–W3 | A stale workspace file overrode explicit Claude session and slot arguments. Without it the same launch bound correctly. Completion marked pending and blocked plan items done, then the first summary changed the completed author back to working. |
| W4–W5 | Closing controller stdin left the process alive at 3.2 s. CLI resume changed session status to active while its slot stayed paused. MCP resume-all unpaused the slot and delivered same-session mail. The earlier CLI mail remained held with null session ID. |
| D1–D3 | A configured 250 ms Codex initialize timeout rejected with a live child. The Claude init timeout killed its child. Healthy Codex initialized. An interrupted Codex forwarding turn nevertheless acked. Claude missing an echo stayed unacked/in-flight without a second write, and a healthy successor replayed it. |
| D4–D6 | One ack 503 caused two Codex forwarding turns for the same row, then a successful ack. Canceling MCP check after the consuming poll left the mailbox empty and the request without a reply. The uncanceled control returned its message. A standalone adapter also lost the canceled delivery when the broker ack committed before SDK response. |
| S1 | Three provider exits produced two crash restarts and a flapping event. Limit 1 still reported usage 0. Chat alone left the slot stopped across a tick. A system message caused a fourth launch with thread/resume. |
| S2 | With an offline reviewer, the author became approved after roughly 15.0 s with zero approval messages. Archival followed after roughly 75.1 s. The external fixture worker remained alive. Its broker slot was disconnected and retained the peer ID. |
| S3–S4 | Two controllers obtained two live PIDs for one slot. Ending in one stopped its PID only. Two concurrent resumes within one controller yielded one PID. One status request drained Codex events from both sessions. The next request for the other session had none. |
| P1–P2 | Ending stopped the fake Gemini leader, but its descendant lived with PPID 1. Pause held Codex mail and removed a file lease. The active turn completed with token count advancing 120 to 240, and no interrupt. |
| P3–P4 | Healthy-slot baseline ack was 2.84 s. A gated earlier steer left later healthy mail unclaimed for 4.35 s, then it acked 321 ms after gate release. A quiet active turn with a heartbeat was interrupted and given a completion instruction after 64.9 s. Two repeats put the interrupt-to-new-prompt sequence in the same 64.9–65.0 s band. Broker task state stayed working. |
| P5–P6 | Released Claude echoed and acked the notice, exited without a replacement. A TERM-resistant child died after escalation during explicit end. When SIGTERM hit the controller itself, the child observed TERM and survived its owner. |
| P7 | Old chat alone left one plain-process launch. Adding fresh system mail caused a restart within 8.9 s because the oldest unclaimed row was chat. Two replacements were then live. Explicit end stopped the later one. |
| R1 | Four Btrfs runs gathered 30 empty-poll samples per population. Median was 0.021–0.031 ms with no history and 3.23–3.84 ms with 100k acknowledged 128-byte rows. A partial index reduced the latter to 0.018–0.025 ms. A native 1,000-row response was 391,014 bytes. Btrfs first claim was 665–711 ms, repeat 6.5–8.1 ms and ack 658–711 ms. Tmpfs measured 9.48 ms, 5.95 ms and 3.46 ms respectively. |
| R2 | A separate SQLite writer held the lock for 450 and 1,400 ms. Concurrent HTTP health took about 457 and 1,356 ms. A 3,400 ms hold returned a 500 from the write after roughly 3,003 ms and health took 2,928 ms. A 25 ms client timer remained about 25 ms. |
| R3–R4 | A fixture event with the exact counted name triggered restart stop at 1/1. The slot, process and session kept running. Duration and count overrides remained monitor-only. Equal sent_at returned IDs 1, 2, 3 in poll and 3, 2, 1 in history and recap. |
| M1–M2 | Metered totals 120, 240 and duplicate 240 in one thread stayed 240. A new thread's totals 120 and 240 left 240 and 360. A cache reset followed by cumulative 360 raised the stored total to 720. One failed +100 update caused only 100 of 200 cumulative tokens to persist. |
| M3–M5 | Generic HTTP 200 passed the client's liveness probe but failed a typed health check. Real broker returned PID and version. Unknown /healthz returned generic 200. A malformed snapshot made status error until repaired. A never-connected slot stayed in starting. The injected ss command returned the listener PID and excluded the client. |
| N1–N3 | Partial create errored, left its first worker alive and skipped the plan. Retrying the name created another active session. A fast Claude fixture's first turn was unmetered, and the next turn produced tokens and working state. Custom admission failed although all three supported provider names had stubs. The adapter dispatch offered the existing peer tool set. |

The database size and process timings are local workload observations. The throughput fixture directly seeded a specified history in its private SQLite database, then used normal HTTP for the benchmark. The successful runs used a longer measurement client deadline to preserve tail observations. The shipped HTTP client still uses five seconds per POST. The natural scheduler tests used unchanged application timers. [HTTP deadline](repos/zetbrush__multiagents/shared/broker-client.ts:50), [poll and ack](repos/zetbrush__multiagents/broker.ts:670), [controller intervals](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1502).

## 7. Measurement audit for every negative or surprising result, including alternate commands or code-path checks used to rule out setup mistakes

### Environment and harness issues

- **Exact dependency and skip audit.** Staged TypeScript 5.9.3, SDK 1.30.0, Bun types 1.4.0 and Zod 4.6.7 were identified from the available package manifests. The Bun lock wants SDK 1.27.1 and Bun types 1.3.11. Offline npm CI named an uncached transitive package. Its lock root still lists version 0.2.0 and a self-dependency. Closed-loopback Bun registry reported exact tarballs absent. Swapping the SDK to staged 1.26.0 repeated the tests and MCP EOF and cancellation effects, without claiming the exact compatible lock graph. Two explicit live skip guards remained off. Optional native lsof was absent. Upstream covered missing binary/reported PID, and M5 independently covered the injected subprocess argument and returned PID shape with ss. [npm lock root](repos/zetbrush__multiagents/package-lock.json:1), [Bun lock](repos/zetbrush__multiagents/bun.lock:21), [CI install](repos/zetbrush__multiagents/.github/workflows/ci.yml:19), [skip and fallback](repos/zetbrush__multiagents/tests/update.test.ts:84).
- **Shell and runtime isolation.** Unshare with the caller UID mapping alone could not raise loopback. Root mapping inside a private namespace and Bubblewrap with preserved UID were successful alternatives. Bubblewrap without private /dev aborted Bun at startup with code 134. Bare bun version ran, while repo-free Bun JavaScript aborted. Shell writes to inherited /dev/null failed. Root writable and tmpfs /dev/shm alternatives still failed. Mounting Bubblewrap's own devices fixed both the shell permission error and Bun. PID and /proc checks in experiments only targeted known synthetic children. I removed the two scratch cores and disabled subsequent dumps.
- **Invalid first fixture runs.** B3 initially omitted required slot_id and asserted an incorrect response field. The NOT NULL constraint plus source identified the fixture error. Corrected B3 reproduced on both Btrfs and tmpfs. S1's first wait returned JavaScript undefined into a function that retries only on false. The fixed sentinel gave the intended live PID observations. P7's first shell template lost one dollar in a JavaScript replacement and recorded a malformed PID. A replacement callback preserved the real PID expression and later runs reproduced the scheduler effects. M2 initially timed out in the bundled run but passed when invoked alone. The wait timed out before any proxy POST. The preceding scenario had left an in-memory token baseline under the same slot ID in a different synthetic database. Clearing tracking between isolated fixture scenarios restored both +100 writes and the same successful +100 broker result in the full monitor run. In the concurrent process-family rerun P7's direct synthetic timestamp update first hit SQLITE_BUSY. An independent fixture-side busy timeout allowed the direct setup write to wait without changing the broker code or its production busy timeout.
- **Timing and storage audit.** The tests verified process exit via owned handles or /proc state, where a zombie is not counted as live. B3 used configurable cleanup periods with state sampling. S2, P3, P4 and P7 used actual controller clocks. R1's first DROP INDEX hit SQLITE_LOCKED on the fixture's same connection with cached statements. An independent schema connection allowed it. A later three-second timeout left 1,000 durable claimed but unacked rows. Four longer-deadline Btrfs reruns and one tmpfs rerun completed. The two filesystems substantiate write-cost sensitivity, while neither establishes the cause of the single outlier. R2 compared the same client's local timer and an HTTP read under an otherwise idle writer to isolate the busy wait inside the broker. [Broker cleanup interval](repos/zetbrush__multiagents/broker.ts:378), [SQLite timeout](repos/zetbrush__multiagents/broker.ts:85), [queue writes](repos/zetbrush__multiagents/broker.ts:681).

### Counterfactuals and code paths

| Result | Audit |
| --- | --- |
| B1–B2 | The first review round required both modeled reviewer roles before approving. A later QA approval only passed with the historical lead row present. Valid plan before and after the invalid replacement isolated the missing constraint and statement ordering from filesystem failure. [Approvals](repos/zetbrush__multiagents/broker.ts:1554), [plan replace](repos/zetbrush__multiagents/broker.ts:1200). |
| B3–B4, R4 | Both B3 cases waited for owned child death and a broker status change. Listing peers changes the available input to the sweeper. Independent plan GET confirmed no stored duplicates. The snapshot join includes each slot in the same session and repeats the assigned row. B4 stable-slot replay excluded the acknowledged row after real WAL recovery. Equal fixed timestamps in R4 reproduced the incidental recap reversal. [Snapshot query](repos/zetbrush__multiagents/broker.ts:295), [fast peer discovery](repos/zetbrush__multiagents/broker.ts:590), [poll/recap](repos/zetbrush__multiagents/broker.ts:418), [history](repos/zetbrush__multiagents/broker.ts:1285). |
| B5–B8 | Verified lock absence through API and surviving row via SQLite, plus successful unrelated acquisition and explicit release. Two live PIDs and new IDs ruled out one process's retry for overlapping peers. Exact pattern conflict and acquisition outside the intersection scoped the glob behavior. Actual standalone MCP call between signals and exit after release isolated graceful-disconnect policy. [Lease predicate](repos/zetbrush__multiagents/broker.ts:1002), [peer release gate](repos/zetbrush__multiagents/broker.ts:708), [ownership matcher](repos/zetbrush__multiagents/broker.ts:1041), [adapter signal handler](repos/zetbrush__multiagents/adapters/base-adapter.ts:554). |
| O1, O2 | Durable slot and validated health were already visible. New peer registration restored delivery to the existing driver. The killed controller and its old provider both exited before replacement was attempted. A deliberate connected-to-disconnected correction changed only the resume predicate. S1 demonstrates the same fake supports thread/resume. [Codex startup](repos/zetbrush__multiagents/orchestrator/launcher.ts:537), [resume eligibility](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1327), [crash resume](repos/zetbrush__multiagents/orchestrator/recovery.ts:222). |
| O3, W4, D5–D6 | Sent cancellation for the actual request ID after a controlled side-effect barrier. Follow-up MCP request remained functional. Both SDKs suppress an aborted handler response. The repository handlers receive the request and do not act on the SDK's cancellation signal. D6 gated the standalone ack response rather than the driver's consuming poll and observed the same loss. Its first teardown hit the independently demonstrated SIGTERM refusal before release. Explicit release before signaling corrected teardown. The EOF fixture reproduced with both SDKs and controller shutdown is wired to process signals. [Controller dispatch](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:665), [adapter dispatch](repos/zetbrush__multiagents/adapters/base-adapter.ts:895), [controller lifetime](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1955). |
| O4, N1 | Delayed fixture spawn log proved child existence before trackLaunch and later process-map insertion. Case N1's deterministic code-7 failure left the first healthy PID alive and plan absent. Retry allocated a distinct session ID. [Track launch](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:106), [create sequence](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:739), [end](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1191). |
| O5, W5 | Individual release on the same idle slot passed. MCP resume-all was the positive control after CLI resume, and the same-session message reappeared. SQL still showed the CLI message held with null session. [Release filter](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1114), [CLI send](repos/zetbrush__multiagents/cli/commands.ts:201), [release held](repos/zetbrush__multiagents/broker.ts:1313). |
| W1–W3 | Adjacent layouts wrote the same project/user config files successfully. The bare header's closing bracket is consumed before the regex requires a second bracket. The protected loop either never advances or finds a bracket in the next section. Python's TOML parser independently confirmed the ordinary following section was absent and the quoted legacy server remained. Removing the stale session marker corrected identity with the same args. A persisted completion after plan setup preceded the ordinary summary call that overwrote it. [Legacy migration](repos/zetbrush__multiagents/orchestrator/launcher.ts:192), [marker read](repos/zetbrush__multiagents/adapters/base-adapter.ts:824), [cached task update](repos/zetbrush__multiagents/adapters/base-adapter.ts:1143). |
| D1–D4 | Compared a healthy Codex handshake and same-clock Claude failure, with both children observed externally. D2 waited for active item before interrupt. D3 confirmed result events and one stdin write without echo, then replay on successor. D4 counted two distinct turns and one finally acknowledged row. No claim depends on fake inference. [Initialize](repos/zetbrush__multiagents/orchestrator/codex-driver.ts:210), [init timeout](repos/zetbrush__multiagents/orchestrator/claude-driver.ts:185), [turn resolution](repos/zetbrush__multiagents/orchestrator/codex-driver.ts:412), [delivery](repos/zetbrush__multiagents/orchestrator/delivery.ts:66). |
| S1, R3 | Confirmed actual exit category, three-crash diagnostic and two resumed thread wire traces before testing mail revival. Chat waited one actual watchdog tick. A correctly named synthetic event isolated the guardrail predicate from missing event production. A true trigger only emitted the event. [Restart counter](repos/zetbrush__multiagents/broker.ts:1123), [stop branch](repos/zetbrush__multiagents/orchestrator/guardrails.ts:112), [watchdog](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1870). |
| S2–S4 | Zero approval rows and natural interval timing identified automatic progress. PID parentage distinguished one versus two controllers. Separate slot IDs identified which session's events appeared in the first status response, and the immediate second response had none. [Completion](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1763), [respawn guard](repos/zetbrush__multiagents/orchestrator/respawn-guard.ts:7), [event drain](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:858). |
| P1, P2, P5, P6 | Verified descendant PID and reparenting. Confirmed pause via held and unclaimed mail, lock release and continued turn output. Cooperative release proved the normal code can drain and exit. Explicit end retaining a live controller allowed escalation in the same fixture that resisted owner shutdown. [Stop](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:80), [pause](repos/zetbrush__multiagents/orchestrator/session-control.ts:131), [release check](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1582), [shutdown](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1977). |
| P3, P4, P7 | Held a recorded steer response and measured the independent slot through the broker. The later mail remained unclaimed, so its healthy driver speed could not explain the delay. Heartbeat confirmed the quiet provider connection. The completion prompt was observed on wire and state remained working. P7 used an old-only control and confirmed separate code-zero and watchdog restart decisions in the logs. [Global tick](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1602), [quiet-turn condition](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1552), [watchdog ordering](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1886). |
| R1–R2 | EXPLAIN QUERY PLAN showed SCAN plus temp sort, then index search on the same 100k-row population. The 1,000-row repeated response kept the same IDs and size. The difference in first claim and ack is associated with writes, and changing filesystem changed their timing much more than the pure read. Concurrent health delay tracked the broker's 3 s limit while client timers ran normally. [Queries](repos/zetbrush__multiagents/broker.ts:418), [WAL and busy timeout](repos/zetbrush__multiagents/broker.ts:85), [handoff writes](repos/zetbrush__multiagents/broker.ts:681). |
| M1–M5, N2–N3 | Actual cumulative wire-shaped events and broker reads distinguished accounting from rendering. Duplicate totals were inert in one thread, a new thread used the previous baseline and a reset lost it. A valid health probe and repaired JSON snapshot served as positive controls. The second fast Claude turn was monitored by the same established driver. Custom admission failed despite fixture binaries for the three supported types. [Token baseline](repos/zetbrush__multiagents/orchestrator/monitor.ts:35), [health probe](repos/zetbrush__multiagents/shared/broker-client.ts:70), [status parse](repos/zetbrush__multiagents/orchestrator/progress.ts:88), [monitor install](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:124), [custom detection](repos/zetbrush__multiagents/orchestrator/launcher.ts:82). |

## 8. Post-mortem: design pressures, accumulated tradeoffs, likely failure modes, and the highest-leverage improvements

The design started from a sensible local collaboration problem. A developer wants existing CLI sessions to find one another, share a working tree and exchange progress with very little infrastructure. Local HTTP, a single SQLite file and small adapters make that model deployable. The headless orchestration layer adds durable logical slots over provider-specific subprocesses. The launch notes, config fallbacks and wire-specific code make the pressure visible. Host CLIs can delay MCP initialization or drop environment, headless Claude channels do not guarantee push, Codex streams early notifications and asks for approval replies, and Gemini supplies a process rather than a turn API. Multiple delivery paths are a reasonable response to those constraints. [Launcher config](repos/zetbrush__multiagents/orchestrator/launcher.ts:149), [adapter startup](repos/zetbrush__multiagents/adapters/base-adapter.ts:466), [driver wire](repos/zetbrush__multiagents/orchestrator/codex-driver.ts:502), [Gemini process launch](repos/zetbrush__multiagents/orchestrator/launcher.ts:585).

The next design step is to make every launch and task transition explicit in durable state. Currently, many patches add heuristics at a call site: use role strings for review, enter working on first output, skip a recently disconnected slot, retain mail on crash, and decide whether to resume from whatever evidence that call site has. This makes normal interaction forgiving but leaves no common place to reject a stale owner, report partial progress for a multi-step action, or distinguish provider execution from request completion. Codex may reach connected before its peer exists. Incoming work can race a canceled launch. An exit can occur after the component that owns its PID has already forgotten it. A durable controller lease and generation-aware worker state address these as one design error. [Connected status during bootstrap](repos/zetbrush__multiagents/orchestrator/launcher.ts:537), [foreground launch timeline](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:739), [process exit](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:138), [general slot writes](repos/zetbrush__multiagents/broker.ts:912).

The next failure an operator is most likely to notice is a superficially healthy or finished team that has unfinished work. Provider bootstrap is treated as connection readiness, job completion is inferred from role and prior messages, and quiet output prompts completion. Those signals are helpful hints if shown separately. They become risky when used to archive, mark plan items complete or discard an inbox row. An operator trying to recover can then trigger another issue by restarting the controller, using the CLI resume path, or submitting the same team again. A steady-state “all tests green” result fails to exercise these sequences. The local positive controls show that SQLite durability and ordinary driver delivery are sound building blocks for making repair predictable. [Progress](repos/zetbrush__multiagents/orchestrator/progress.ts:67), [role-based completion](repos/zetbrush__multiagents/broker.ts:1480), [auto-end](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1763), [CLI resume](repos/zetbrush__multiagents/cli/session.ts:130), [ack state](repos/zetbrush__multiagents/broker.ts:681).

The most consequential tradeoff is between a frictionless single-operator prototype and a service that can supervise unattended execution. The current architecture avoids managing a separate supervisor daemon, a scheduler queue or distributed coordination. The missing pieces can be implemented locally. A persisted owner generation protects against both same-process callback races and two-controller overlap. SQLite transactions protect logical state changes inside the existing broker. Per-slot scheduling with global caps preserves the simple topology while removing cross-slot blocking. An append-only event cursor supplies operational evidence without changing how human-facing status is presented. The improvements below are ordered by the outcomes that would otherwise orphan processes, accept unreviewed work, or lose delivery.

## 9. Evidence appendix with local file/line references and commands

### Local source index

| Domain | Primary local anchors |
| --- | --- |
| Durable entities and migrations | [Database initialization](repos/zetbrush__multiagents/broker.ts:83), [session and slot rows](repos/zetbrush__multiagents/broker.ts:116), [ownership and leases](repos/zetbrush__multiagents/broker.ts:156), [plans and knowledge](repos/zetbrush__multiagents/broker.ts:208), [schema upgrades](repos/zetbrush__multiagents/broker.ts:246), [TypeScript domain](repos/zetbrush__multiagents/shared/types.ts:66) |
| Registration, inbox and lifecycle | [cleanup](repos/zetbrush__multiagents/broker.ts:320), [register](repos/zetbrush__multiagents/broker.ts:441), [send](repos/zetbrush__multiagents/broker.ts:602), [poll](repos/zetbrush__multiagents/broker.ts:655), [ack](repos/zetbrush__multiagents/broker.ts:681), [unregister gate](repos/zetbrush__multiagents/broker.ts:708), [hold/release](repos/zetbrush__multiagents/broker.ts:1308), [task/review routes](repos/zetbrush__multiagents/broker.ts:1480) |
| Commands and process lifecycle | [controller maps](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:45), [track and exit](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:101), [foreground create](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:672), [remove](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:977), [resume](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1309), [shutdown](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1977), [CLI session functions](repos/zetbrush__multiagents/cli/session.ts:130) |
| Scheduler and ledgers | [periodic policy](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1502), [driver loop](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1546), [completion](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1763), [watchdog](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1854), [one-slot guard](repos/zetbrush__multiagents/orchestrator/respawn-guard.ts:7), [crash history](repos/zetbrush__multiagents/orchestrator/recovery.ts:35), [restart budget](repos/zetbrush__multiagents/broker.ts:1123) |
| Peer and provider boundary | [provider config](repos/zetbrush__multiagents/orchestrator/launcher.ts:156), [driver starts](repos/zetbrush__multiagents/orchestrator/launcher.ts:468), [adapter startup](repos/zetbrush__multiagents/adapters/base-adapter.ts:466), [adapter fallback](repos/zetbrush__multiagents/adapters/base-adapter.ts:593), [MCP tool result](repos/zetbrush__multiagents/adapters/base-adapter.ts:895), [delivery loop function](repos/zetbrush__multiagents/orchestrator/delivery.ts:45) |
| Provider protocol and monitor | [Claude stream seek](repos/zetbrush__multiagents/orchestrator/claude-driver.ts:167), [Claude result/echo](repos/zetbrush__multiagents/orchestrator/claude-driver.ts:291), [Codex JSON-RPC](repos/zetbrush__multiagents/orchestrator/codex-driver.ts:460), [turn data](repos/zetbrush__multiagents/orchestrator/codex-driver.ts:569), [typed approvals](repos/zetbrush__multiagents/orchestrator/codex-driver.ts:642), [token meter](repos/zetbrush__multiagents/orchestrator/monitor.ts:28), [health](repos/zetbrush__multiagents/orchestrator/progress.ts:67) |
| Extension and tests | [index exports](repos/zetbrush__multiagents/index.ts:15), [adapter hooks](repos/zetbrush__multiagents/adapters/base-adapter.ts:452), [provider default commands](repos/zetbrush__multiagents/orchestrator/launcher.ts:82), [driver fixtures](repos/zetbrush__multiagents/tests/fakes/fake-claude.ts:1), [Codex fixture](repos/zetbrush__multiagents/tests/fakes/fake-codex-app-server.ts:1), [stdio helper](repos/zetbrush__multiagents/tests/helpers/mcp-stdio-client.ts:17) |

### Reproduction commands

Run from the evaluation workspace. The commands stage and exercise the source in a disposable directory. The reproduction assumes a pre-existing offline node_modules tree with the stated package versions. On this workspace that tree and the alternate SDK were already present before this review. Supply REVIEW_DEPS and REVIEW_SDK126 to use different local copies. There is no registry dependency for the supported reproduction.

```bash
set -euo pipefail
review_root="$PWD"
review_head=6038986b739937aaf3f2da2346e97a25f00369b1
review_repo="$review_root/repos/zetbrush__multiagents"
review_report="$review_root/evaluations/zetbrush__multiagents.md"
review_deps="${REVIEW_DEPS:-$review_root/.multiagents-review.d1jXAHLl/src/node_modules}"
review_alt_sdk="${REVIEW_SDK126:-$review_root/.multiagents-review.d1jXAHLl/sdk-1.26.0}"
review_lab=$(mktemp -d "$review_root/.multiagents-reproduce.XXXXXXXX")
mkdir -p "$review_lab"/{src,alt,tmp,logs}
git --no-optional-locks -C "$review_repo" rev-parse HEAD
git --no-optional-locks -C "$review_repo" status --porcelain=v1 --untracked-files=all
test "$(git -C "$review_repo" rev-parse HEAD)" = "$review_head"
git -C "$review_repo" archive "$review_head" | tar -xf - -C "$review_lab/src"
git -C "$review_repo" archive "$review_head" | tar -xf - -C "$review_lab/alt"
mkdir -p "$review_lab"/{src,alt}/node_modules
cp -a "$review_deps"/. "$review_lab/src/node_modules/"
cp -a "$review_deps"/. "$review_lab/alt/node_modules/"
mv "$review_lab/alt/node_modules/@modelcontextprotocol/sdk" "$review_lab/sdk-primary"
cp -a "$review_alt_sdk" "$review_lab/alt/node_modules/@modelcontextprotocol/sdk"

python3 - "$review_lab" "$review_report" <<'PY'
from pathlib import Path
import re
import sys
lab, report = map(Path, sys.argv[1:])
pattern = r"^<!-- fixture ([a-z-]+\.ts) -->\n```ts\n(.*?)\n```$"
fixtures = re.findall(pattern, report.read_text(), re.MULTILINE | re.DOTALL)
assert len(fixtures) == 10, [name for name, _ in fixtures]
for name, source in fixtures:
    (lab / name).write_text(source.rstrip() + "\n")
PY

review_path="$(dirname "$(command -v bun)"):$(dirname "$(command -v node)"):/usr/bin:/bin"
review_run() {
    local profile=$1
    shift
    local private_run
    private_run=$(mktemp -d "$review_lab/run.XXXXXXXX")
    mkdir -p "$private_run"/{home,tmp}
    local options=()
    case "$profile" in
        primary) ;;
        alternate) options+=(--ro-bind "$review_lab/alt" "$review_lab/src");;
        tmpfs) options+=(--tmpfs "$review_lab/tmp");;
        *) return 2;;
    esac
    bwrap --die-with-parent --unshare-net --unshare-pid \
      --ro-bind / / --bind "$review_lab" "$review_lab" \
      "${options[@]}" --dev /dev --proc /proc --bind "$private_run/tmp" /tmp \
      --chdir "$review_lab/src" -- \
      env -i PATH="$review_path" HOME="$private_run/home" TMPDIR=/tmp \
      XDG_CACHE_HOME="$private_run/home/.cache" XDG_CONFIG_HOME="$private_run/home/.config" \
      XDG_DATA_HOME="$private_run/home/.local/share" GIT_CONFIG_NOSYSTEM=1 \
      GIT_CONFIG_GLOBAL=/dev/null LANG=C.UTF-8 CI=true REVIEW_LAB="$review_lab" \
      bash -c 'ulimit -c 0; exec "$@"' review "$@"
}

review_run primary ip -brief address
review_run primary ip route show table main
review_run primary bun test
review_run alternate bun test
review_run primary node node_modules/typescript/bin/tsc --noEmit
review_run alternate node node_modules/typescript/bin/tsc --noEmit
review_run primary npm pack --ignore-scripts --offline --pack-destination "$review_lab"
tar -tf "$review_lab/multiagents-0.7.0.tgz"
mkdir -p "$review_lab/release-smoke"
tar -xf "$review_lab/multiagents-0.7.0.tgz" -C "$review_lab/release-smoke"
ln -s "$review_lab/src/node_modules" "$review_lab/release-smoke/package/node_modules"
review_run primary timeout 20s bun "$review_lab/pack-smoke.ts"
review_run primary timeout 60s bun "$review_lab/broker-fresh.ts"
review_run tmpfs timeout 60s bun "$review_lab/broker-fresh.ts"
review_run primary timeout 65s bun "$review_lab/orch-fresh.ts"
review_run primary timeout 45s bun "$review_lab/workspace-fresh.ts"
review_run primary timeout 55s bun "$review_lab/wire-fresh.ts"
review_run alternate timeout 20s bun "$review_lab/wire-fresh.ts" D5-mcp-cancelled-mail
review_run alternate timeout 20s bun "$review_lab/workspace-fresh.ts" W4-eof
review_run alternate timeout 35s bun "$review_lab/orch-fresh.ts" O3-cancel
review_run primary timeout 115s bun "$review_lab/scheduler-fresh.ts"
review_run primary timeout 115s bun "$review_lab/process-fresh.ts"
review_run primary timeout 45s bun "$review_lab/resource-fresh.ts"
review_run tmpfs timeout 45s bun "$review_lab/resource-fresh.ts" R1-poll-growth
review_run primary timeout 45s bun "$review_lab/monitor-fresh.ts"
review_run primary timeout 45s bun "$review_lab/launch-fresh.ts"

git --no-optional-locks -C "$review_repo" rev-parse HEAD
git --no-optional-locks -C "$review_repo" status --porcelain=v1 --untracked-files=all
git --no-optional-locks -C "$review_repo" clean -ndx
```

The frozen install probes used copies of the lock files in separate empty package fixtures inside the lab. The npm command was `npm ci --offline --ignore-scripts --no-audit --no-fund` with a local cache. The Bun command was `bun install --frozen-lockfile --ignore-scripts --prefer-offline --registry http://127.0.0.1:1` with a private install cache. The private namespace had no service on port 1. These probes are documented as dependency-availability checks. They are unnecessary for the pre-staged reproduction.

The test helper's MCP writes are real newline-delimited stdio. For the two SDKs, the implementation inspected was `node_modules/@modelcontextprotocol/sdk/dist/esm/shared/protocol.js` at `_oncancel` and `_onrequest`, and `dist/esm/server/stdio.js` at `start` and `close`. An independent byte comparison checked all 77 archived files and their owner execute bits in each tested source staging. GNU tar compare additionally reported ordinary extraction ownership and mode differences, which the byte/execute comparison isolated.

### Embedded isolated controls

The scripts below are the local fixtures used for the focused controls, with diagnosed fixture errors corrected. The scenario harnesses accept scenario names as optional positional arguments. Logs include the scenario labels and UTC timestamps. Reproduction teardown should happen after the namespace exits. The fixture cases use only private local data.


<details>
<summary>broker-fresh.ts</summary>

<!-- fixture broker-fresh.ts -->
```ts
import { strict as A } from "node:assert";
import { Database } from "bun:sqlite";
import { mkdirSync, statSync } from "node:fs";
import { join } from "node:path";
const root = process.env.REVIEW_LAB!;
const cases = new Set(process.argv.slice(2));
const included = (s: string) => cases.size === 0 || cases.has(s);
const stamp = () => new Date().toISOString();
const out = (label: string, fact: unknown) => console.log(stamp(), label, JSON.stringify(fact));
const brokerPath = join(root, "src/broker.ts");
let nextPort = 17000;

async function until<T>(sample: () => Promise<T | false>, timeout = 4000): Promise<T> {
  const end = performance.now() + timeout;
  do {
    const result = await sample();
    if (result !== false) return result;
    await Bun.sleep(20);
  } while (performance.now() < end);
  throw Error("condition deadline");
}
type Process = ReturnType<typeof Bun.spawn>;
async function scenario(name: string, sweepMs: number, run: (h: Awaited<ReturnType<typeof make>>) => Promise<void>) {
  if (!included(name)) return;
  const h = await make(name, sweepMs);
  try { await run(h); }
  catch (e) { out(name + " error", String(e)); process.exitCode = 1; }
  finally { await h.finish(); }
}
async function make(name: string, sweepMs: number) {
  const port = nextPort++;
  const cwd = join(root, "tmp", name + "-" + Date.now());
  const dbPath = join(cwd, "db.sqlite");
  const base = "http://127.0.0.1:" + port;
  mkdirSync(cwd);
  const children: Process[] = [];
  let broker: Process | undefined;
  const spawn = (argv: string[], additional = {}) => {
    const proc = Bun.spawn(argv, { cwd, stdin: "ignore", stdout: "ignore", stderr: "inherit", ...additional });
    children.push(proc);
    return proc;
  };
  const boot = async () => {
    broker = spawn(["bun", brokerPath], { env: { ...process.env, MULTIAGENTS_PORT: String(port), MULTIAGENTS_DB: dbPath, MULTIAGENTS_CLEANUP_INTERVAL_MS: String(sweepMs) } });
    const instance = broker;
    await until(async () => {
      if (instance.exitCode !== null) throw Error("broker exited early: " + instance.exitCode);
      try { const res = await fetch(base + "/health", { signal: AbortSignal.timeout(300) }); return res.ok && (await res.json()).pid === instance.pid; }
      catch { return false; }
    });
    return instance.pid;
  };
  const stop = async (signal: "SIGTERM" | "SIGKILL" = "SIGTERM") => {
    if (!broker || broker.exitCode !== null) return;
    broker.kill(signal);
    await broker.exited;
  };
  const raw = async (path: string, data: unknown) => {
    const response = await fetch(base + path, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(data), signal: AbortSignal.timeout(3000) });
    return {status: response.status, data: await response.json()};
  };
  const post = async (path: string, data: unknown) => {
    const result = await raw(path, data);
    A.equal(result.status, 200, path + " " + JSON.stringify(result.data));
    return result.data;
  };
  const session = (id = name) => post("/sessions/create", { id, name: id, project_dir: cwd });
  const slot = (id = name, role = "developer") => post("/slots/create", { session_id: id, agent_type: "claude", role, display_name: role });
  const readSlot = (id: number) => post("/slots/get", { id });
  const worker = () => spawn(["sleep", "600"]);
  const register = (proc: Process, slotId: number, sessionId = name) => post("/register", { pid: proc.pid, cwd, git_root: cwd, tty: null, summary: "fixture-ready", agent_type: "claude", session_id: sessionId, slot_id: slotId });
  const send = (toSlot: number, text: string, sessionId = name) => post("/send-message", {session_id: sessionId, from_id: "orchestrator", to_slot_id: toSlot, text});
  const kill = async (proc: Process) => { proc.kill("SIGKILL"); await proc.exited; };
  const finish = async () => {
    await stop();
    await Promise.all(children.filter(p => p.exitCode === null && p.signalCode === null).map(kill));
  };
  await boot();
  return { cwd, dbPath, spawn, worker, boot, stop, finish, raw, post, session, slot, readSlot, register, send, kill };
}

await scenario("B1-review-attempts", 30000, async h => {
  await h.session();
  const [dev, qa, lead] = await Promise.all([h.slot(), h.slot(undefined, "qa"), h.slot(undefined, "lead")]);
  const [author, reviewer, owner] = await Promise.all([dev, qa, lead].map(s => h.register(h.worker(), s.id)));
  const base = { session_id: dev.session_id, target_slot_id: dev.id };
  const done = () => h.post("/lifecycle/signal-done", { ...base, peer_id: author.id, summary: "completed a revision" });
  const approve = (peer: string) => h.post("/lifecycle/approve", { ...base, peer_id: peer });
  const feedback = (actionable: boolean) => h.post("/lifecycle/submit-feedback", { ...base, peer_id: owner.id, feedback: "update the revision", actionable });
  const initial = await done();
  const one = await approve(reviewer.id);
  const both = await approve(owner.id);
  const note = await feedback(false);
  const revise = await feedback(true);
  const again = await done();
  const second = await approve(reviewer.id);
  const approvals = (await h.post("/message-log", { session_id: dev.session_id, with_slot: dev.id, limit: 100 })).filter((m: any) => m.msg_type === "approval");
  A.deepEqual([initial.task_state, one.task_state, both.task_state, note.task_state, revise.task_state, again.task_state],
  ["done_pending_review", "done_pending_review", "approved", "approved", "addressing_feedback", "done_pending_review"]);
  A.equal(approvals.length, 3);
  out("B1", { initial, one, both, note, revise, again, second, approvalSenders: approvals.map((m: any) => m.from_slot_id) });
});

await scenario("B2-plan-replace", 30000, async h => {
  const s = await h.session();
  const slot = await h.slot();
  const valid = [{label:"baseline-1"}, {label:"baseline-2", assigned_to_slot:slot.id}];
  const create = (title: string, items: unknown[]) => h.post("/plan/create", {session_id:s.id,title,items});
  const before = await create("baseline", valid);
  const update = await h.post("/plan/update-item", {item_id: before.items[0].id, session_id:s.id, status:"done"});
  const failed = await h.raw("/plan/create", {session_id:s.id,title:"bad replacement",items:[{label:"prefix succeeded"},{}]});
  const after = await h.post("/plan/get", {session_id:s.id});
  const corrected = await create("corrected", valid);
  A.equal(update.completion, 50);
  A.equal(failed.status, 500);
  A.equal(corrected.items.length, 2);
  A.ok(before.plan.id < corrected.plan.id);
  out("B2", { prior: before.items.map((i: any) => i.label), failed, survivingTitle: after.plan.title, survivingLabels: after.items.map((i: any) => i.label), corrected: corrected.items.length });
});

for (const [name, discover] of [["B3-sweep", false], ["B3-list-first", true]] as const) {
  await scenario(name, discover ? 2200 : 100, async h => {
    const s = await h.session();
    const [a, b, c] = await Promise.all([h.slot(), h.slot(undefined,"qa"), h.slot(undefined,"lead")]);
    const owner = h.worker();
    const peer = await h.register(owner, a.id);
    const update = await h.post("/slots/update", {id:a.id,context_patch:{provider_session:"keep"}});
    A.equal(JSON.parse(update.context_snapshot).provider_session, "keep");
    const plan = await h.post("/plan/create", {session_id:s.id,title:"snapshot control",items:[{label:"one",assigned_to_slot:a.id},{label:"other",assigned_to_slot:b.id}]});
    A.equal(plan.items.length, 2);
    const lease = await h.post("/files/acquire", {session_id:s.id,peer_id:peer.id,slot_id:a.id,file_path:"src/test.ts",timeout_ms:30000});
    A.equal(lease.status, "acquired", JSON.stringify(lease));
    const start = performance.now();
    await h.kill(owner);
    let listed: unknown;
    if (discover) {
      listed = await h.post("/list-peers", {scope:"machine", session_id:s.id});
      A.deepEqual(listed, []);
    }
    const disconnected = await until(async () => {const slot = await h.readSlot(a.id);return slot.status === "disconnected" && slot;});
    const locks = await h.post("/files/locks", {session_id:s.id});
    const snap = JSON.parse(disconnected.context_snapshot);
    A.equal(snap.provider_session, "keep");
    out(name, { discover, elapsedMs: Math.round(performance.now() - start), listed, snapshot:snap, locks: locks.length, slotCount: [a,b,c].length });
  });
}

await scenario("B4-wal", 100, async h => {
  const session = await h.session();
  const agent = await h.slot();
  const firstWorker = h.worker();
  const first = await h.register(firstWorker, agent.id);
  await h.send(agent.id, "retained one");
  await h.send(agent.id, "ack before crash");
  const polled = await h.post("/poll-by-slot", {slot_id:agent.id,retain:true});
  A.equal(polled.messages.length, 2);
  const [retained, acked] = polled.messages;
  await h.post("/ack-messages", {ids:[acked.id]});
  const version = statSync(h.dbPath + "-wal").size;
  await h.stop("SIGKILL");
  A.equal(firstWorker.signalCode, null);
  const pidAfter = await h.boot();
  A.equal((await h.readSlot(agent.id)).peer_id, first.id);
  await h.kill(firstWorker);
  const disconnected = await until(async () => {const s = await h.readSlot(agent.id);return s.status === "disconnected" && s;});
  const second = await h.register(h.worker(), agent.id);
  A.notEqual(second.id, first.id);
  A.equal(second.slot.id, agent.id);
  const replay = await h.post("/poll-messages", {id:second.id,retain:true});
  A.deepEqual(replay.messages.map((m: any) => m.id), [retained.id]);
  const a1 = await h.post("/ack-messages", {ids:[retained.id]});
  const a2 = await h.post("/ack-messages", {ids:[retained.id]});
  A.deepEqual([a1.acked, a2.acked], [1, 0]);
  out("B4", { pidAfter, walBytes:version, snap:JSON.parse(disconnected.context_snapshot), recap:second.recap.map((m: any) => [m.text, m.acked_at !== null]), replay: replay.messages.map((m: any) => m.text), ack:[a1.acked,a2.acked], session:session.id });
});

await scenario("B5-expired-lease", 30000, async h => {
  const s = await h.session();
  const [a,b] = await Promise.all([h.slot(), h.slot(undefined,"qa")]);
  const [p1,p2] = await Promise.all([h.register(h.worker(),a.id), h.register(h.worker(),b.id)]);
  const file = "src/./entry.ts";
  const args = (slot: number, peer: string, ttl: number, path = file) => ({session_id:s.id,slot_id:slot,peer_id:peer,file_path:path,timeout_ms:ttl});
  const lease = await h.post("/files/acquire",args(a.id,p1.id,1200));
  A.equal(lease.status,"acquired");
  const conflict = await h.post("/files/acquire",args(b.id,p2.id,1000,"src/entry.ts"));
  A.equal(conflict.status,"locked");
  const unlisted = await until(async () => {
    const rows = await h.post("/files/locks",{session_id:s.id});
    return rows.length === 0;
  });
  const db = new Database(h.dbPath,{readonly:true});
  const physical = db.query("select file_path, expires_at from file_locks").all();
  const failed = await h.raw("/files/acquire",args(b.id,p2.id,1000,"src/entry.ts"));
  const otherPath = await h.post("/files/acquire",args(b.id,p2.id,1000,"src/other.ts"));
  await h.post("/files/release",{session_id:s.id,peer_id:p1.id,file_path:"src/entry.ts"});
  const reclaimed = await h.post("/files/acquire",args(b.id,p2.id,1000,"src/entry.ts"));
  const postWindow = Date.now() - lease.expires_at;
  db.close();
  A.equal(otherPath.status,"acquired");
  A.equal(reclaimed.status,"acquired");
  out("B5", {unlisted, physical, conflict:conflict.status, failed, otherPath:otherPath.status, reclaimed:reclaimed.status, postWindow});
});

await scenario("B6-overlap-replacement", 30000, async h => {
  const s = await h.session();
  const slot = await h.slot();
  const old = await h.register(h.worker(),slot.id);
  const current = await h.register(h.worker(),slot.id);
  A.notEqual(old.id,current.id);
  A.equal((await h.readSlot(slot.id)).peer_id,current.id);
  const peerview = await h.post("/list-peers",{scope:"machine",session_id:s.id});
  const idsBefore = peerview.map((p: any) => p.id);
  const release = await h.post("/lifecycle/release",{session_id:s.id,target_slot_id:slot.id,released_by:"orchestrator"});
  A.equal(release.task_state,"released");
  await h.send(slot.id,"final cooperative notice");
  const handoff1 = await h.post("/poll-messages",{id:old.id,retain:true});
  const handoff2 = await h.post("/poll-messages",{id:current.id,retain:true});
  const unregistered = await h.post("/unregister",{id:old.id});
  A.equal(unregistered.ok,true);
  const after = await h.readSlot(slot.id);
  const survivors = await h.post("/list-peers",{scope:"machine",session_id:s.id});
  A.equal(survivors.length,1);
  A.equal(survivors[0].id,current.id);
  out("B6",{idsBefore, current:current.id, handoff1:handoff1.messages.map((m: any)=>m.id), handoff2:handoff2.messages.map((m: any)=>m.id), after:[after.status,after.peer_id,after.task_state],survivingPeerSlot:survivors[0].slot_id});
});

await scenario("B7-ownership-overlap",30000,async h=>{
  const session=await h.session();
  const [a,b]=await Promise.all([h.slot(),h.slot(undefined,"qa")]);
  const [pa,pb]=await Promise.all([h.register(h.worker(),a.id),h.register(h.worker(),b.id)]);
  const own=(slot_id:number,path_patterns:string[])=>h.post("/files/assign-ownership",{session_id:session.id,slot_id,path_patterns,assigned_by:"orchestrator"});
  const acquire=(slot_id:number,peer_id:string,file_path:string)=>h.post("/files/acquire",{session_id:session.id,slot_id,peer_id,file_path});
  const ownA=await own(a.id,["src/**"]);
  const ownB=await own(b.id,["src/auth/*"]);
  const exact=await own(b.id,["src/**"]);
  const [blockedA,blockedB,works]=await Promise.all([acquire(a.id,pa.id,"src/auth/session.ts"),acquire(b.id,pb.id,"src/auth/session.ts"),acquire(a.id,pa.id,"src/core.ts")]);
  out("B7",{ownA,ownB,exact,blocked:[blockedA.status,blockedB.status],control:works.status});
});

await scenario("B8-standalone-signal",30000,async h=>{
  const {McpStdioClient}=await import(join(root,"src/tests/helpers/mcp-stdio-client.ts"));
  const s=await h.session();
  const sl=await h.slot();
  const c=await McpStdioClient.spawn(["bun",join(root,"src/server.ts"),"--agent-type","claude"],{cwd:h.cwd,env:{...process.env,MULTIAGENTS_PORT:String(nextPort-1),MULTIAGENTS_SESSION:s.id,MULTIAGENTS_SLOT:String(sl.id)},stderrLog:join(h.cwd,"signal.log")});
  try {
    const live=await until(async()=>{const r=await h.readSlot(sl.id);return Boolean(r.peer_id)&&r;});
    await c.callTool("check_team_status");
    c.proc.kill("SIGTERM");
    const survived=await Promise.race([c.proc.exited.then(()=>false),Bun.sleep(450).then(()=>true)]);
    const after=await h.readSlot(sl.id);
    const tool=await c.callTool("set_summary",{summary:"still running after signal"});
    await h.post("/lifecycle/release",{session_id:s.id,target_slot_id:sl.id,released_by:"orchestrator"});
    c.proc.kill("SIGTERM");
    const afterRelease=await Promise.race([c.proc.exited.then(code=>({exit:true,code})),Bun.sleep(1200).then(()=>({exit:false}))]);
    out("B8",{registered:live.status,survived,stillConnected:after.status,tool:tool.text,afterRelease,final:(await h.readSlot(sl.id)).status});
  }finally{ if(c.proc.exitCode===null&&c.proc.signalCode===null)c.proc.kill("SIGKILL");await c.proc.exited;}
});
```

</details>

<details>
<summary>orch-fresh.ts</summary>

<!-- fixture orch-fresh.ts -->
```ts
import { strict as A } from "node:assert";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
const root = process.env.REVIEW_LAB!;
const src = join(root,"src");
const { McpStdioClient } = await import(join(src,"tests/helpers/mcp-stdio-client.ts"));
const startCases = process.argv.slice(2);
const only = (name: string) => startCases.length === 0 || startCases.includes(name);
const stamp = () => new Date().toISOString();
function log(label: string, value: unknown) { console.log(stamp(), label, JSON.stringify(value)); }
const controllers: InstanceType<typeof McpStdioClient>[] = [];
const children: ReturnType<typeof Bun.spawn>[] = [];
const port = 17101;
const url = "http://127.0.0.1:" + port;
const run = join(root,"tmp","orchestrator-" + Date.now());
const home = join(run,"home");
const bin = join(run,"bin");
mkdirSync(home,{recursive:true});
mkdirSync(bin);
const mockCommand = (name: string, lines: string[]) => writeFileSync(join(bin,name), ["#!/bin/sh", "set -eu", ...lines, ""].join("\n"), {mode:0o700});
mockCommand("codex", [
  'if [ "${1-}" = "--version" ]; then echo codex-fake-0.156.1; exit; fi',
  'printf "%s %s %s\n" "$$" "$MULTIAGENTS_SESSION" "$MULTIAGENTS_SLOT" >> "$MOCK_LOG/provider-pids"',
  'export FAKE_CODEX_LOG="$MOCK_LOG/codex-$$.jsonl"',
  'exec bun "$REVIEW_LAB/src/tests/fakes/fake-codex-app-server.ts" "$@"'
]);
mockCommand("claude", [
  'if [ "${1-}" = "--version" ]; then echo claude-fake-2.1.241; exit; fi',
  'printf "%s %s %s\n" "$$" "$MULTIAGENTS_SESSION" "$MULTIAGENTS_SLOT" >> "$MOCK_LOG/provider-pids"',
  'export FAKE_CLAUDE_LOG="$MOCK_LOG/claude-$$.jsonl"',
  'if [ -n "${MOCK_CLAUDE_DELAY-}" ]; then sleep "$MOCK_CLAUDE_DELAY"; fi',
  'exec bun "$REVIEW_LAB/src/tests/fakes/fake-claude.ts" "$@"'
]);
mockCommand("npx", ['case " $* " in *" --version "*) echo gemini-fake-1; exit 0;; esac', 'echo fixture-only >&2','exit 99']);
const env = {
  ...process.env,
  HOME:home, XDG_CONFIG_HOME:join(home,".config"), XDG_CACHE_HOME:join(home,".cache"),
  PATH:bin+":"+process.env.PATH,
  MULTIAGENTS_PORT:String(port), MULTIAGENTS_DB:join(run,"db.sqlite"),
  MULTIAGENTS_CLEANUP_INTERVAL_MS:"120",
  MULTIAGENTS_NO_DASHBOARD:"1",
  MOCK_LOG:run,
};
const awaitUntil = async <T>(proposal: () => Promise<T | false> | T | false, ms = 6000): Promise<T> => {
  const end = performance.now() + ms;
  do {
    const result = await proposal();
    if (result !== false) return result;
    await Bun.sleep(25);
  } while (performance.now() < end);
  throw Error("condition deadline");
};
const post = async (path: string, body: unknown) => {
  const res = await fetch(url+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body),signal:AbortSignal.timeout(2500)});
  const data = await res.json();
  A.equal(res.status,200,path+" "+JSON.stringify(data));
  return data;
};
const slots = (id: string) => post("/slots/list",{session_id:id});
const slot = (id: number) => post("/slots/get",{id});
const session = (id: string) => post("/sessions/get",{id});
const history = (id: string) => post("/message-log",{session_id:id,limit:200});
const pidRows = () => {
  try {return readFileSync(join(run,"provider-pids"),"utf8").trim().split("\n").filter(Boolean).map(line => {const [pid,sid,s] = line.split(" ");return {pid:Number(pid),sid,slot:Number(s)};});}
  catch {return [];}
};
const isRunning = (pid: number) => {
  try {
    const stat = readFileSync("/proc/"+pid+"/stat","utf8");
    return !/^[ZX]/.test(stat.slice(stat.lastIndexOf(")")+2));
  } catch {return false;}
};
const codexLog = (pid: number) => {
  try {return readFileSync(join(run,"codex-"+pid+".jsonl"),"utf8").trim().split("\n").filter(Boolean).map(v=>JSON.parse(v));}
  catch {return [];}
};
const project = (s: string) => join(run,s);
const client = async (tag: string, tuning: Record<string,string> = {}) => {
  const c = await McpStdioClient.spawn(["bun",join(src,"orchestrator/orchestrator-server.ts")],{cwd:run,env:{...env,...tuning},stderrLog:join(run,tag+".log")});
  controllers.push(c);
  return c;
};
const agent = (type:string, name:string, task = "Produce the synthetic fixture") => ({agent_type:type,name,role:"developer",role_description:"Fixture only",initial_task:task});
const create = (c: InstanceType<typeof McpStdioClient>, sid: string, agents: unknown[], plan?: unknown[]) => c.callTool("create_team",{session_name:sid,project_dir:project(sid),agents,...(plan ? {plan} : {})},25000);
const end = (c: InstanceType<typeof McpStdioClient>, sid: string) => c.callTool("end_session",{session_id:sid});
const start = () => {
  const b = Bun.spawn(["bun",join(src,"broker.ts")],{cwd:run,env,stdin:"ignore",stdout:"ignore",stderr:"inherit"});
  children.push(b);
  return b;
};
const killed = async (pid: number) => {
  await awaitUntil(() => !isRunning(pid));
};
const scenario = async (name: string, test: () => Promise<void>) => {
  if (!only(name)) return;
  try { await test(); }
  catch (e) { log(name+" error", String(e)); process.exitCode = 1; }
};
try {
  const broker = start();
  await awaitUntil(async () => {
    try { const r = await fetch(url+"/health",{signal:AbortSignal.timeout(300)});return r.ok && (await r.json()).pid === broker.pid; }
    catch {return false;}
  });

  await scenario("O1-routing", async () => {
    const sid = "routing";
    const c = await client(sid);
    const created = await create(c,sid,[agent("codex","codex-worker")],[{label:"record durable plan",agent_name:"codex-worker"}]);
    A.equal(created.isError,false,created.text);
    const [createdSlot] = await slots(sid);
    const initialPlan = await post("/plan/get",{session_id:sid});
    const planPush = (await history(sid)).filter((m: any) => m.text.includes("Your assigned items"));
    A.equal(initialPlan.items[0].assigned_to_slot,createdSlot.id);
    A.equal(createdSlot.status,"connected");
    A.equal(createdSlot.peer_id,null);
    const target = {session_id:sid,target:String(createdSlot.id)};
    const d1 = await c.callTool("direct_agent",{...target,message:"before register"});
    const b1 = await c.callTool("broadcast_to_team",{session_id:sid,message:"before register broadcast"});
    const adapter = await McpStdioClient.spawn(["bun",join(src,"server.ts"),"--agent-type","codex"],{
      cwd:project(sid), env:{...env,MULTIAGENTS_DRIVER_MODE:"1",MULTIAGENTS_SESSION:sid,MULTIAGENTS_SLOT:String(createdSlot.id)},stderrLog:join(run,"O1-adapter.log"),
    });
    controllers.push(adapter);
    await awaitUntil(async () => Boolean((await slot(createdSlot.id)).peer_id));
    const d2 = await c.callTool("direct_agent",{...target,message:"after register"});
    const b2 = await c.callTool("broadcast_to_team",{session_id:sid,message:"after register broadcast"});
    const planRead = await adapter.callTool("get_plan");
    A.match(planRead.text,/record durable plan/);
    const messages = await awaitUntil(async () => {
      const observed = (await history(sid)).filter((m: any) => m.text.startsWith("after register"));
      return observed.length === 2 && observed.every((m: any) => m.acked_at) && observed;
    },10000);
    const [pid] = pidRows().filter(p => p.sid === sid);
    A.equal(codexLog(pid.pid).filter((record: any) => (record.params?.input ?? []).some((i: any) => i.text?.includes("after register"))).length,1);
    log("O1",{peerlessDirect:d1.text,peerlessDirectError:d1.isError,peerlessBroadcast:b1.text,planPush:planPush.length,planViaAdapter:true,directAfter:d2.text,broadcastAfter:b2.text,ack:messages.map((m: any)=>[m.msg_type,Boolean(m.acked_at)])});
    await end(c,sid);
    await killed(pid.pid);
  });

  await scenario("O2-restart", async () => {
    const sid = "restart-owner";
    const c1 = await client(sid+"-first");
    const created = await create(c1,sid,[agent("codex","worker")]);
    A.equal(created.isError,false,created.text);
    const [s] = await slots(sid);
    const [old] = pidRows().filter(p=>p.sid===sid);
    await awaitUntil(async () => String((await slot(s.id)).context_snapshot).includes("codex_thread_id"));
    c1.proc.kill("SIGKILL");
    await c1.proc.exited;
    await killed(old.pid);
    const c2 = await client(sid+"-second");
    const persisted = await slot(s.id);
    const list = await c2.callTool("list_sessions",{});
    const refused = await c2.callTool("resume_session",{session_id:sid});
    const spawnCountBefore = pidRows().filter(p=>p.sid===sid).length;
    A.equal(spawnCountBefore,1);
    A.equal(persisted.status,"connected");
    A.equal(persisted.peer_id,null);
    A.match(refused.text,/No disconnected agents/);
    await post("/slots/update",{id:s.id,status:"disconnected"});
    const fixed = await c2.callTool("resume_session",{session_id:sid});
    const [_,newOne] = await awaitUntil(() => {
      const found = pidRows().filter(p=>p.sid===sid);
      return found.length >= 2 && found;
    });
    await awaitUntil(() => codexLog(newOne.pid).some(x=>x.request==="thread/start"));
    const wire = codexLog(newOne.pid).map((x: any) => x.request);
    A.equal(newOne.slot,s.id);
    log("O2",{oldPid:old.pid, oldAlive:isRunning(old.pid), connected:persisted.status, peer:persisted.peer_id, listLine:list.text.split("\n").find((x: string)=>x.includes("Name: "+sid)), resumeBefore:refused.text, resumeAfter:fixed.text.split("\n").find((x: string)=>x.includes("Respawned")), newPid:newOne.pid, wire});
    await end(c2,sid);
    await killed(newOne.pid);
  });

  await scenario("O3-cancel", async () => {
    const sid = "cancel-create";
    const c = await client(sid,{MOCK_CLAUDE_DELAY:"1.5"});
    const requestId = (c as any).nextId;
    const response = create(c,sid,[agent("claude","worker")]);
    response.catch(()=>{});
    await awaitUntil(() => pidRows().some(p=>p.sid===sid));
    const before = await slots(sid);
    c.notify("notifications/cancelled",{requestId,reason:"credential-free cancellation control"});
    const withTimer = await Promise.race([response.then(v=>({received:true,result:v})),Bun.sleep(2500).then(()=>({received:false}))]);
    const provider = pidRows().find(p=>p.sid===sid)!;
    const after = await slot(before[0].id);
    const isAlive = isRunning(provider.pid);
    const list = await c.callTool("list_sessions", {});
    log("O3",{requestId,response:withTimer,spawned:isAlive,threadKnown:JSON.parse(after.context_snapshot ?? "{}").claude_session_id ?? null,listed:list.text.includes(sid)});
    await end(c,sid);
    await killed(provider.pid);
    if (!("result" in withTimer)) { c.proc.kill(); await c.proc.exited; }
  });

  await scenario("O4-end-overlap", async () => {
    const sid = "end-overlap";
    const c = await client(sid,{MOCK_CLAUDE_DELAY:"1.2"});
    const creation = create(c,sid,[agent("claude","worker")]);
    await awaitUntil(() => pidRows().some(p=>p.sid===sid));
    const provider = pidRows().find(p=>p.sid===sid)!;
    const endResult = await end(c,sid);
    const archiveEarly = (await session(sid)).status;
    const created = await creation;
    const archiveLate = (await session(sid)).status;
    const list = await c.callTool("list_sessions", {});
    const remains = isRunning(provider.pid);
    A.equal(archiveEarly,"archived");
    A.equal(archiveLate,"archived");
    log("O4",{early:endResult.text,archiveEarly,create:created.text.split("\n")[0],archiveLate,aliveAfterArchive:remains,pid:provider.pid,listLine:list.text.split("\n").find((x: string)=>x.includes("Name: "+sid))});
    await end(c,sid);
    await killed(provider.pid);
  });

  await scenario("O5-release-idle", async () => {
    const sid = "idle-release";
    const c = await client(sid);
    await post("/sessions/create",{id:sid,name:sid,project_dir:run});
    const first = await post("/slots/create",{session_id:sid,agent_type:"codex",display_name:"unused"});
    await post("/slots/update",{id:first.id,status:"connected"});
    const before = await slot(first.id);
    const all = await c.callTool("release_all",{session_id:sid});
    const after = await slot(first.id);
    const explicit = await c.callTool("release_agent",{session_id:sid,target:"unused"});
    const afterExplicit = await slot(first.id);
    log("O5",{before:before.task_state,releaseAll:all.text,after:after.task_state,releaseAgent:explicit.text,explicitState:afterExplicit.task_state});
    await end(c,sid);
  });
} finally {
  for (const c of controllers.reverse()) if (c.proc.exitCode === null && c.proc.signalCode === null) { c.proc.kill("SIGTERM"); await c.proc.exited; }
  for (const child of children) if (child.exitCode === null && child.signalCode === null) { child.kill("SIGTERM"); await child.exited; }
}
```

</details>

<details>
<summary>workspace-fresh.ts</summary>

<!-- fixture workspace-fresh.ts -->
```ts
import { strict as A } from "node:assert";
import { Database } from "bun:sqlite";
import { mkdirSync, statSync } from "node:fs";
import { join } from "node:path";
const root = process.env.REVIEW_LAB!;
const cases = new Set(process.argv.slice(2));
const included = (s: string) => cases.size === 0 || cases.has(s);
const stamp = () => new Date().toISOString();
const out = (label: string, fact: unknown) => console.log(stamp(), label, JSON.stringify(fact));
const brokerPath = join(root, "src/broker.ts");
let nextPort = 17000;

async function until<T>(sample: () => Promise<T | false>, timeout = 4000): Promise<T> {
  const end = performance.now() + timeout;
  do {
    const result = await sample();
    if (result !== false) return result;
    await Bun.sleep(20);
  } while (performance.now() < end);
  throw Error("condition deadline");
}
type Process = ReturnType<typeof Bun.spawn>;
async function scenario(name: string, sweepMs: number, run: (h: Awaited<ReturnType<typeof make>>) => Promise<void>) {
  if (!included(name)) return;
  const h = await make(name, sweepMs);
  try { await run(h); }
  catch (e) { out(name + " error", String(e)); process.exitCode = 1; }
  finally { await h.finish(); }
}
async function make(name: string, sweepMs: number) {
  const port = nextPort++;
  const cwd = join(root, "tmp", name + "-" + Date.now());
  const dbPath = join(cwd, "db.sqlite");
  const base = "http://127.0.0.1:" + port;
  mkdirSync(cwd);
  const children: Process[] = [];
  let broker: Process | undefined;
  const spawn = (argv: string[], additional = {}) => {
    const proc = Bun.spawn(argv, { cwd, stdin: "ignore", stdout: "ignore", stderr: "inherit", ...additional });
    children.push(proc);
    return proc;
  };
  const boot = async () => {
    broker = spawn(["bun", brokerPath], { env: { ...process.env, MULTIAGENTS_PORT: String(port), MULTIAGENTS_DB: dbPath, MULTIAGENTS_CLEANUP_INTERVAL_MS: String(sweepMs) } });
    const instance = broker;
    await until(async () => {
      if (instance.exitCode !== null) throw Error("broker exited early: " + instance.exitCode);
      try { const res = await fetch(base + "/health", { signal: AbortSignal.timeout(300) }); return res.ok && (await res.json()).pid === instance.pid; }
      catch { return false; }
    });
    return instance.pid;
  };
  const stop = async (signal: "SIGTERM" | "SIGKILL" = "SIGTERM") => {
    if (!broker || broker.exitCode !== null) return;
    broker.kill(signal);
    await broker.exited;
  };
  const raw = async (path: string, data: unknown) => {
    const response = await fetch(base + path, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(data), signal: AbortSignal.timeout(3000) });
    return {status: response.status, data: await response.json()};
  };
  const post = async (path: string, data: unknown) => {
    const result = await raw(path, data);
    A.equal(result.status, 200, path + " " + JSON.stringify(result.data));
    return result.data;
  };
  const session = (id = name) => post("/sessions/create", { id, name: id, project_dir: cwd });
  const slot = (id = name, role = "developer") => post("/slots/create", { session_id: id, agent_type: "claude", role, display_name: role });
  const readSlot = (id: number) => post("/slots/get", { id });
  const worker = () => spawn(["sleep", "600"]);
  const register = (proc: Process, slotId: number, sessionId = name) => post("/register", { pid: proc.pid, cwd, git_root: cwd, tty: null, summary: "fixture-ready", agent_type: "claude", session_id: sessionId, slot_id: slotId });
  const send = (toSlot: number, text: string, sessionId = name) => post("/send-message", {session_id: sessionId, from_id: "orchestrator", to_slot_id: toSlot, text});
  const kill = async (proc: Process) => { proc.kill("SIGKILL"); await proc.exited; };
  const finish = async () => {
    await stop();
    await Promise.all(children.filter(p => p.exitCode === null && p.signalCode === null).map(kill));
  };
  await boot();
  return { cwd, dbPath, spawn, worker, boot, stop, finish, raw, post, session, slot, readSlot, register, send, kill };
}


import { writeFileSync, readFileSync, unlinkSync, existsSync } from "node:fs";
const src = join(root,"src");
const { McpStdioClient } = await import(join(src,"tests/helpers/mcp-stdio-client.ts"));
const rootEnv = {...process.env,MULTIAGENTS_NO_DASHBOARD:"1"};
const pidCpu = (pid: number) => {
  const stat = readFileSync("/proc/"+pid+"/stat","utf8");
  const fields = stat.slice(stat.lastIndexOf(")")+2).split(" ");
  return [11,12].reduce((n,i)=>n+Number(fields[i]),0);
};
const sessionFile = (work:string) => join(work,".multiagents","session.json");
async function customHome(h: Awaited<ReturnType<typeof make>>, name: string) {
  const home = join(h.cwd,"home-"+name);
  mkdirSync(join(home,".codex"),{recursive:true});
  return home;
}
function portForCurrentScenario() { return String(nextPort-1); }

await scenario("W1-toml",30000,async h=>{
  const variants = {
    empty:"",
    legacy:'[mcp_servers.multiagents]\ncommand = "bun"\n',
    legacyFollowing:'[mcp_servers.multiagents]\ncommand = "bun"\n[features]\nfeature_x = true\n',
    dotted:'[mcp_servers.multiagents.tools.old]\napproval_mode = "approve"\n[features]\nfeature_x = true\n',
    quoted:'[mcp_servers."multiagents"]\ncommand = "bun"\n',
  };
  for (const [variant,contents] of Object.entries(variants)) {
    const home = await customHome(h,variant);
    const config = join(home,".codex","config.toml");
    const folder = join(h.cwd,"project-"+variant);
    mkdirSync(folder);
    writeFileSync(config,contents);
    const launcher = join(src,"orchestrator/launcher.ts");
    const code = 'const {ensureMcpConfigs}=await import('+JSON.stringify(launcher)+');await ensureMcpConfigs(process.cwd(),"synthetic","codex");console.log("finished");';
    const proc = h.spawn(["bun","-e",code],{cwd:folder,env:{...rootEnv,HOME:home},stdout:"pipe",stderr:"ignore"});
    const result = await Promise.race([proc.exited.then(code=>({done:true,code})),Bun.sleep(650).then(()=>({done:false}))]);
    let cpuTicks: null | number = null;
    if (!result.done) { cpuTicks = pidCpu(proc.pid); await h.kill(proc); }
    const written = readFileSync(config,"utf8");
    out("W1 "+variant,{result,cpuTicks,projectMcp:existsSync(join(folder,".mcp.json")),sessionMarker:existsSync(sessionFile(folder)),featuresHeader:written.includes("[features]"),featuresKey:written.includes("feature_x"),stillContainsLegacy:written.includes("[mcp_servers.multiagents]"),quotedLegacy:written.includes('[mcp_servers."multiagents"]'),updated:written.includes("multiagents-peer")});
  }
});

await scenario("W2-session-precedence",30000,async h=>{
  const a = await h.session("intended");
  const b = await h.session("later-workspace-marker");
  const target = await h.slot(a.id,"developer");
  const other = await h.slot(b.id,"qa");
  mkdirSync(join(h.cwd,".multiagents"));
  writeFileSync(sessionFile(h.cwd),JSON.stringify({session_id:b.id,last_slot_id:other.id,broker_port:Number(portForCurrentScenario())}));
  const spawnCli = (suffix:string) => McpStdioClient.spawn(["bun",join(src,"cli.ts"),"mcp-server","--agent-type","claude","--session",a.id,"--slot",String(target.id),"--driver-mode"],{cwd:h.cwd,env:{...rootEnv,MULTIAGENTS_PORT:portForCurrentScenario()},stderrLog:join(h.cwd,"adapter-"+suffix+".log")});
  const sessionView = (id:string) => h.post("/slots/list",{session_id:id});
  const first = await spawnCli("stale-marker");
  try {
    const row = await until(async()=>{const peers=await h.post("/list-peers",{scope:"machine"});return peers.find((p:any)=>p.pid===first.pid)||false;});
    const original = await h.readSlot(target.id);
    const later = await sessionView(b.id);
    unlinkSync(sessionFile(h.cwd));
    const second = await spawnCli("no-marker");
    try {
      const exact = await until(async()=>{const s=await h.readSlot(target.id);return s.last_peer_pid===second.pid&&s;});
      const t = await second.callTool("check_team_status");
      const lines = t.text.split("\n");
      out("W2",{explicit:[a.id,target.id], staleFile:[b.id,other.id], staleRegistered:[row.session_id,row.slot_id], intendedBefore:[original.status,original.peer_id], laterSlots:later.map((s:any)=>s.id), cleanRegistered:[exact.session_id,exact.id], identifiesSelf:lines.some(x=>x.endsWith("(you)"))});
    } finally { second.proc.kill(); await second.proc.exited; }
  } finally { first.proc.kill(); await first.proc.exited; }
});

await scenario("W3-task-cached-state",30000,async h=>{
  const s = await h.session();
  const sl = await h.slot();
  const plan = await h.post("/plan/create",{session_id:s.id,title:"Work",items:[{label:"never started",assigned_to_slot:sl.id},{label:"blocked input",assigned_to_slot:sl.id}]});
  await h.post("/plan/update-item",{item_id:plan.items[1].id,session_id:s.id,status:"blocked"});
  const c = await McpStdioClient.spawn(["bun",join(src,"server.ts"),"--agent-type","claude"],{cwd:h.cwd,env:{...rootEnv,MULTIAGENTS_PORT:portForCurrentScenario(),MULTIAGENTS_DRIVER_MODE:"1",MULTIAGENTS_SESSION:s.id,MULTIAGENTS_SLOT:String(sl.id)},stderrLog:join(h.cwd,"adapter-state.log")});
  try {
    await until(async()=>Boolean((await h.readSlot(sl.id)).peer_id));
    const before = await h.readSlot(sl.id);
    const done = await c.callTool("signal_done",{summary:"work statement"});
    const doneSlot = await h.readSlot(sl.id);
    const donePlan = await h.post("/plan/get",{session_id:s.id});
    const updated = await c.callTool("set_summary",{summary:"status after completion"});
    const after = await h.readSlot(sl.id);
    A.equal(doneSlot.task_state,"done_pending_review");
    A.equal(donePlan.completion,100);
    out("W3",{initial:before.task_state,done:done.text,donePlan:donePlan.items.map((i:any)=>[i.label,i.status]),updated:updated.text,after:after.task_state});
  } finally { c.proc.kill(); await c.proc.exited; }
});

await scenario("W4-eof",30000,async h=>{
  const c = await McpStdioClient.spawn(["bun",join(src,"orchestrator/orchestrator-server.ts")],{cwd:h.cwd,env:{...rootEnv,MULTIAGENTS_PORT:portForCurrentScenario()},stderrLog:join(h.cwd,"eof.log")});
  try {
    const list = await c.callTool("list_sessions");
    c.closeStdin();
    const result = await Promise.race([c.proc.exited.then(code=>({exited:true,code})),Bun.sleep(3200).then(()=>({exited:false}))]);
    out("W4",{before:list.text,result,exitCode:c.proc.exitCode,processStat:existsSync("/proc/"+c.pid+"/stat")});
  } finally { if(c.proc.exitCode===null) c.proc.kill("SIGTERM"); await c.proc.exited; }
});

await scenario("W5-cli-pause",30000,async h=>{
  const s = await h.session();
  const sl = await h.slot();
  await h.register(h.worker(),sl.id);
  const cli = async (args:string[])=>{
    const p = h.spawn(["bun",join(src,"cli.ts"),...args],{env:{...rootEnv,MULTIAGENTS_PORT:portForCurrentScenario()},stdout:"pipe",stderr:"pipe"});
    const [stdout,stderr,exit]=await Promise.all([new Response(p.stdout).text(),new Response(p.stderr).text(),p.exited]);
    A.equal(exit,0,stderr);
    return stdout.trim();
  };
  await cli(["session","pause",s.id]);
  const queued = await cli(["send",String(sl.id),"valid CLI message"]);
  await h.send(sl.id,"same-session control");
  const resume = await cli(["session","resume",s.id]);
  const [sessionAfter,slotAfter] = await Promise.all([h.post("/sessions/get",{id:s.id}),h.readSlot(sl.id)]);
  const stillPaused = await h.post("/poll-by-slot",{slot_id:sl.id,retain:true});
  const c = await McpStdioClient.spawn(["bun",join(src,"orchestrator/orchestrator-server.ts")],{cwd:h.cwd,env:{...rootEnv,MULTIAGENTS_PORT:portForCurrentScenario()},stderrLog:join(h.cwd,"cli-pause.log")});
  try {
    const control = await c.callTool("control_session",{session_id:s.id,action:"resume_all"});
    const afterControl = await h.readSlot(sl.id);
    const ready = await h.post("/poll-by-slot",{slot_id:sl.id,retain:true});
    const db = new Database(h.dbPath,{readonly:true});
    const persisted = db.query("select session_id, held, text from messages order by id").all();
    db.close();
    out("W5",{cliSend:queued,cliResume:resume,session:sessionAfter.status,slotPaused:slotAfter.paused,pollPaused:stillPaused.paused,control:control.text,releasedPausedValue:afterControl.paused,seen:ready.messages.map((m:any)=>m.text),persisted});
  } finally { c.proc.kill(); await c.proc.exited; }
});
```

</details>

<details>
<summary>wire-fresh.ts</summary>

<!-- fixture wire-fresh.ts -->
```ts
import { strict as A } from "node:assert";
import { Database } from "bun:sqlite";
import { mkdirSync, statSync } from "node:fs";
import { join } from "node:path";
const root = process.env.REVIEW_LAB!;
const cases = new Set(process.argv.slice(2));
const included = (s: string) => cases.size === 0 || cases.has(s);
const stamp = () => new Date().toISOString();
const out = (label: string, fact: unknown) => console.log(stamp(), label, JSON.stringify(fact));
const brokerPath = join(root, "src/broker.ts");
let nextPort = 17000;

async function until<T>(sample: () => Promise<T | false>, timeout = 4000): Promise<T> {
  const end = performance.now() + timeout;
  do {
    const result = await sample();
    if (result !== false) return result;
    await Bun.sleep(20);
  } while (performance.now() < end);
  throw Error("condition deadline");
}
type Process = ReturnType<typeof Bun.spawn>;
async function scenario(name: string, sweepMs: number, run: (h: Awaited<ReturnType<typeof make>>) => Promise<void>) {
  if (!included(name)) return;
  const h = await make(name, sweepMs);
  try { await run(h); }
  catch (e) { out(name + " error", String(e)); process.exitCode = 1; }
  finally { await h.finish(); }
}
async function make(name: string, sweepMs: number) {
  const port = nextPort++;
  const cwd = join(root, "tmp", name + "-" + Date.now());
  const dbPath = join(cwd, "db.sqlite");
  const base = "http://127.0.0.1:" + port;
  mkdirSync(cwd);
  const children: Process[] = [];
  let broker: Process | undefined;
  const spawn = (argv: string[], additional = {}) => {
    const proc = Bun.spawn(argv, { cwd, stdin: "ignore", stdout: "ignore", stderr: "inherit", ...additional });
    children.push(proc);
    return proc;
  };
  const boot = async () => {
    broker = spawn(["bun", brokerPath], { env: { ...process.env, MULTIAGENTS_PORT: String(port), MULTIAGENTS_DB: dbPath, MULTIAGENTS_CLEANUP_INTERVAL_MS: String(sweepMs) } });
    const instance = broker;
    await until(async () => {
      if (instance.exitCode !== null) throw Error("broker exited early: " + instance.exitCode);
      try { const res = await fetch(base + "/health", { signal: AbortSignal.timeout(300) }); return res.ok && (await res.json()).pid === instance.pid; }
      catch { return false; }
    });
    return instance.pid;
  };
  const stop = async (signal: "SIGTERM" | "SIGKILL" = "SIGTERM") => {
    if (!broker || broker.exitCode !== null) return;
    broker.kill(signal);
    await broker.exited;
  };
  const raw = async (path: string, data: unknown) => {
    const response = await fetch(base + path, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(data), signal: AbortSignal.timeout(3000) });
    return {status: response.status, data: await response.json()};
  };
  const post = async (path: string, data: unknown) => {
    const result = await raw(path, data);
    A.equal(result.status, 200, path + " " + JSON.stringify(result.data));
    return result.data;
  };
  const session = (id = name) => post("/sessions/create", { id, name: id, project_dir: cwd });
  const slot = (id = name, role = "developer") => post("/slots/create", { session_id: id, agent_type: "claude", role, display_name: role });
  const readSlot = (id: number) => post("/slots/get", { id });
  const worker = () => spawn(["sleep", "600"]);
  const register = (proc: Process, slotId: number, sessionId = name) => post("/register", { pid: proc.pid, cwd, git_root: cwd, tty: null, summary: "fixture-ready", agent_type: "claude", session_id: sessionId, slot_id: slotId });
  const send = (toSlot: number, text: string, sessionId = name) => post("/send-message", {session_id: sessionId, from_id: "orchestrator", to_slot_id: toSlot, text});
  const kill = async (proc: Process) => { proc.kill("SIGKILL"); await proc.exited; };
  const finish = async () => {
    await stop();
    await Promise.all(children.filter(p => p.exitCode === null && p.signalCode === null).map(kill));
  };
  await boot();
  return { cwd, dbPath, spawn, worker, boot, stop, finish, raw, post, session, slot, readSlot, register, send, kill };
}


import { readFileSync, writeFileSync } from "node:fs";
const src=join(root,"src");
const { ClaudeDriver }=await import(join(src,"orchestrator/claude-driver.ts"));
const { CodexDriver }=await import(join(src,"orchestrator/codex-driver.ts"));
const { deliverPendingMessages }=await import(join(src,"orchestrator/delivery.ts"));
const { BrokerClient }=await import(join(src,"shared/broker-client.ts"));
const { McpStdioClient }=await import(join(src,"tests/helpers/mcp-stdio-client.ts"));
const fakeClaude=join(src,"tests/fakes/fake-claude.ts");
const fakeCodex=join(src,"tests/fakes/fake-codex-app-server.ts");
const currentPort=()=>nextPort-1;
const address=()=>"http://127.0.0.1:"+currentPort();
const peek=(h:Awaited<ReturnType<typeof make>>,id:number)=>h.post("/peek-undelivered",{slot_id:id});
const lines=(path:string)=>readFileSync(path,"utf8").trim().split("\n").filter(Boolean).map(x=>JSON.parse(x));
const alive=(pid:number)=>{
  try { const s=readFileSync("/proc/"+pid+"/stat","utf8");return !/^[ZX]/.test(s.slice(s.lastIndexOf(")")+2));}
  catch {return false;}
};
async function codex(cwd:string, name:string) {
  const wire=join(cwd,name+".jsonl");
  const driver=await CodexDriver.spawn(cwd,{...process.env,FAKE_CODEX_LOG:wire},{command:["bun",fakeCodex]});
  await driver.startSession({cwd,prompt:"initial"});
  return {driver,wire};
}
const close=async(driver:any)=>{
  await driver.kill();
  if(alive(driver.pid)) driver.process.kill("SIGKILL");
  await driver.process.exited;
};

await scenario("D1-unowned-handshake",30000,async h=>{
  const timeout=250;
  const pidMarker=join(h.cwd,"codex-pid");
  const silence='require("node:fs").writeFileSync(process.argv[1],String(process.pid));process.stdin.on("data",()=>{});setInterval(()=>{},1000)';
  const codexFailure=await CodexDriver.spawn(h.cwd,process.env,{command:["bun","-e",silence,pidMarker],timeoutMs:timeout}).then(()=>null,e=>String(e));
  let silentPid=Number(readFileSync(pidMarker,"utf8"));
  try {
    A.ok(silentPid>1);
    A.match(codexFailure!,/initialize timed out/);
    const remained=alive(silentPid);
    const clMarker=join(h.cwd,"claude-pid");
    const shim=join(h.cwd,"claude-without-init");
    writeFileSync(shim,'#!/bin/sh\nprintf "%s" "$$" > "$FAKE_MARKER"\nexec bun "$FAKE_CLAUDE" "$@"\n',{mode:0o700});
    const claudeFailure=await ClaudeDriver.spawn({cwd:h.cwd,env:{...process.env,FAKE_MARKER:clMarker,FAKE_CLAUDE:fakeClaude,FAKE_CLAUDE_NO_INIT:"1"},command:[shim],mcpConfig:{},firstPrompt:"starts but never reports init",initTimeoutMs:timeout}).then(()=>null,e=>String(e));
    const clPid=Number(readFileSync(clMarker,"utf8"));
    A.match(claudeFailure!,/did not emit its init event/);
    await until(async()=>!alive(clPid));
    const good=await codex(h.cwd,"normal");
    try {
      out("D1",{codexFailure, timeoutMs:timeout, codexRemained:remained, claudeFailure,claudeRemained:alive(clPid),normalCodexReady:good.driver.alive && Boolean(good.driver.threadId),normalRequests:lines(good.wire).map(x=>x.request)});
    } finally { await close(good.driver); }
  } finally {if(alive(silentPid)) process.kill(silentPid,"SIGKILL");}
});

await scenario("D2-interrupted-mail",30000,async h=>{
  const s=await h.session();
  const sl=await h.slot();
  const {driver,wire}=await codex(h.cwd,"interrupted");
  try {
    const completed:string[]=[];
    driver.onNotification((n:any)=>{if(n.method==="turn/completed") completed.push(n.params.turn?.status);});
    await h.send(sl.id,"SCENARIO:slow:3000 please acknowledge when delivered");
    const state={kind:"codex",driver,threadId:driver.threadId,busy:false,lastNudge:0};
    const client=new BrokerClient(address());
    const dispatch=await deliverPendingMessages(s.id,sl.id,state,client);
    await until(async()=>Boolean(driver.activeTurnId && driver.activeItems>0));
    const pendingBefore=(await peek(h,sl.id)).count;
    await driver.interrupt(driver.threadId!);
    await until(async()=>!state.busy);
    const pendingAfter=(await peek(h,sl.id)).count;
    A.equal(dispatch,"replied");
    A.equal(pendingBefore,1);
    A.deepEqual(completed,["interrupted"]);
    out("D2",{dispatch,pendingBefore,completed,pendingAfter,wire:lines(wire).map(x=>x.request)});
  } finally {await close(driver);}
});

await scenario("D3-no-claude-echo",30000,async h=>{
  const s=await h.session();
  const sl=await h.slot();
  const fixture=join(h.cwd,"claude-noecho.ts");
  const seen=join(h.cwd,"seen.tsv");
  const program=[
    'const out=(m)=>process.stdout.write(JSON.stringify(m)+"\\n");',
    'let buf="",init=false;process.stdin.on("data",data=>{buf+=data.toString();let lines=buf.split("\\n");buf=lines.pop();',
    'for (const line of lines){const x=JSON.parse(line),text=x.message.content;require("fs").appendFileSync(process.env.SEEN,JSON.stringify(text)+"\\n");',
    'if (!init){init=true;out({type:"system",subtype:"init",session_id:"silent-echo"});}',
    'if (!text.startsWith("[Teammate messages]"))out({type:"user",isReplay:true,message:x.message});',
    'out({type:"assistant",message:{role:"assistant",content:[{type:"text",text:"work continues"}]}});',
    'out({type:"result",is_error:false,subtype:"success",result:"control turn done"});}});',
    'process.stdin.on("end",()=>process.exit(0));',
  ].join("\n");
  writeFileSync(fixture,program);
  const launch = (command:string[])=>ClaudeDriver.spawn({cwd:h.cwd,env:{...process.env,SEEN:seen},command,mcpConfig:{},firstPrompt:"initial"});
  const driver=await launch(["bun",fixture]);
  const client=new BrokerClient(address());
  try {
    await h.send(sl.id,"requires a replay marker");
    const state={kind:"claude",driver,busy:false,lastNudge:0};
    const first=await deliverPendingMessages(s.id,sl.id,state,client);
    await until(async()=>driver.turnsCompleted>=2);
    const again=await deliverPendingMessages(s.id,sl.id,state,client);
    const pendingWhileAlive=(await peek(h,sl.id)).count;
    const wrote=lines(seen).filter(x=>x.includes("requires a replay marker")).length;
    A.equal(wrote,1);
    await close(driver);
    const later=await launch(["bun",fakeClaude]);
    try {
      const replay=await deliverPendingMessages(s.id,sl.id,{kind:"claude",driver:later,busy:false,lastNudge:0},client);
      await until(async()=> (await peek(h,sl.id)).count===0);
      out("D3",{first,again,wrote,pendingWhileAlive,replay,pendingAfter:(await peek(h,sl.id)).count});
    } finally { await close(later); }
  } finally {await close(driver);}
});

await scenario("D4-ack-timeout-boundary",30000,async h=>{
  const s=await h.session();
  const sl=await h.slot();
  const {driver,wire}=await codex(h.cwd,"double");
  let ackRequests=0;
  const proxy=Bun.serve({hostname:"127.0.0.1",port:0,async fetch(req){
    const path=new URL(req.url).pathname;
    if(path==="/ack-messages" && ++ackRequests===1) return new Response("controlled error",{status:503});
    return fetch(address()+path,{method:req.method,headers:req.headers,body:req.method==="POST"?await req.text():undefined});
  }});
  const client=new BrokerClient("http://127.0.0.1:"+proxy.port);
  const state={kind:"codex",driver,threadId:driver.threadId,busy:false,lastNudge:0};
  try {
    await h.send(sl.id,"ack delivery marker");
    const first=await deliverPendingMessages(s.id,sl.id,state,client);
    await until(async()=>!state.busy);
    const firstPending=(await peek(h,sl.id)).count;
    const second=await deliverPendingMessages(s.id,sl.id,state,client);
    await until(async()=>!state.busy);
    const after=(await peek(h,sl.id)).count;
    const deliveries=lines(wire).filter(x=>x.request==="turn/start" && x.params.input[0].text.includes("ack delivery marker")).length;
    A.equal(ackRequests,2);
    out("D4",{first,second,firstPending,after,deliveries,ackRequests});
  } finally {proxy.stop(true);await close(driver);}
});

await scenario("D5-mcp-cancelled-mail",30000,async h=>{
  const s=await h.session();
  const sl=await h.slot();
  let gated=false;
  let upstreamComplete=false;
  let unblock:()=>void=()=>{};
  const proxy=Bun.serve({hostname:"127.0.0.1",port:0,async fetch(req){
    const path=new URL(req.url).pathname;
    const response=await fetch(address()+path,{method:req.method,headers:req.headers,body:req.method==="POST"?await req.text():undefined});
    if(path==="/poll-messages"&&gated){upstreamComplete=true;await new Promise<void>(resolve=>unblock=resolve);}
    return response;
  }});
  const c=await McpStdioClient.spawn(["bun",join(src,"server.ts"),"--agent-type","claude"],{cwd:h.cwd,env:{...process.env,MULTIAGENTS_PORT:String(proxy.port),MULTIAGENTS_DRIVER_MODE:"1",MULTIAGENTS_SESSION:s.id,MULTIAGENTS_SLOT:String(sl.id)},stderrLog:join(h.cwd,"adapter.log")});
  try {
    await until(async()=>Boolean((await h.readSlot(sl.id)).peer_id));
    await h.send(sl.id,"control mail succeeds");
    const success=await c.callTool("check_messages");
    A.match(success.text,/control mail succeeds/);
    await h.send(sl.id,"mail polled after client cancel");
    const before=(await peek(h,sl.id)).count;
    gated=true;
    const requestId=(c as any).nextId;
    const pending=c.callTool("check_messages",{},1200).then(r=>r.text,e=>String(e));
    await until(async()=>upstreamComplete);
    const afterPoll=(await peek(h,sl.id)).count;
    c.notify("notifications/cancelled",{requestId,reason:"local cancellation control"});
    await Bun.sleep(80);
    gated=false;
    unblock();
    const result=await pending;
    const next=await c.callTool("check_messages");
    out("D5",{positive:success.text,before,upstreamComplete,afterPoll,cancelledRequest:result,following:next.text,remaining:(await peek(h,sl.id)).count});
  } finally {unblock();c.proc.kill();await c.proc.exited;proxy.stop(true);}
});

await scenario("D6-standalone-cancelled-ack",30000,async h=>{
  const s=await h.session();
  const sl=await h.slot();
  let gated=false;
  let upstreamComplete=false;
  let unblock:()=>void=()=>{};
  const proxy=Bun.serve({hostname:"127.0.0.1",port:0,async fetch(req){
    const path=new URL(req.url).pathname;
    const response=await fetch(address()+path,{method:req.method,headers:req.headers,body:req.method==="POST"?await req.text():undefined});
    if(path==="/ack-messages"&&gated&&!upstreamComplete){upstreamComplete=true;await new Promise<void>(resolve=>unblock=resolve);}
    return response;
  }});
  const c=await McpStdioClient.spawn(["bun",join(src,"server.ts"),"--agent-type","claude"],{cwd:h.cwd,env:{...process.env,MULTIAGENTS_PORT:String(proxy.port),MULTIAGENTS_SESSION:s.id,MULTIAGENTS_SLOT:String(sl.id)},stderrLog:join(h.cwd,"adapter.log")});
  try {
    await until(async()=>Boolean((await h.readSlot(sl.id)).peer_id));
    await h.send(sl.id,"control mail succeeds");
    const success=await c.callTool("check_messages");
    A.match(success.text,/control mail succeeds/);
    await h.send(sl.id,"mail polled after client cancel");
    const before=(await peek(h,sl.id)).count;
    gated=true;
    const requestId=(c as any).nextId;
    const pending=c.callTool("check_messages",{},1200).then(r=>r.text,e=>String(e));
    await until(async()=>upstreamComplete);
    const afterAck=(await peek(h,sl.id)).count;
    c.notify("notifications/cancelled",{requestId,reason:"local cancellation control"});
    await Bun.sleep(80);
    gated=false;
    unblock();
    const result=await pending;
    const next=await c.callTool("check_messages");
    out("D6",{positive:success.text,before,upstreamComplete,afterAck,cancelledRequest:result,following:next.text,remaining:(await peek(h,sl.id)).count});
  } finally {
    unblock();
    await h.post("/lifecycle/release",{session_id:s.id,target_slot_id:sl.id,released_by:"orchestrator"});
    c.proc.kill();
    await c.proc.exited;
    proxy.stop(true);
  }
});
```

</details>

<details>
<summary>scheduler-fresh.ts</summary>

<!-- fixture scheduler-fresh.ts -->
```ts
import { strict as A } from "node:assert";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
const root = process.env.REVIEW_LAB!;
const src = join(root,"src");
const { McpStdioClient } = await import(join(src,"tests/helpers/mcp-stdio-client.ts"));
const startCases = process.argv.slice(2);
const only = (name: string) => startCases.length === 0 || startCases.includes(name);
const stamp = () => new Date().toISOString();
function log(label: string, value: unknown) { console.log(stamp(), label, JSON.stringify(value)); }
const controllers: InstanceType<typeof McpStdioClient>[] = [];
const children: ReturnType<typeof Bun.spawn>[] = [];
const port = 17101;
const url = "http://127.0.0.1:" + port;
const run = join(root,"tmp","orchestrator-" + Date.now());
const home = join(run,"home");
const bin = join(run,"bin");
mkdirSync(home,{recursive:true});
mkdirSync(bin);
const mockCommand = (name: string, lines: string[]) => writeFileSync(join(bin,name), ["#!/bin/sh", "set -eu", ...lines, ""].join("\n"), {mode:0o700});
mockCommand("codex", [
  'if [ "${1-}" = "--version" ]; then echo codex-fake-0.156.1; exit; fi',
  'printf "%s %s %s\n" "$$" "$MULTIAGENTS_SESSION" "$MULTIAGENTS_SLOT" >> "$MOCK_LOG/provider-pids"',
  'export FAKE_CODEX_LOG="$MOCK_LOG/codex-$$.jsonl"',
  'exec bun "$REVIEW_LAB/src/tests/fakes/fake-codex-app-server.ts" "$@"'
]);
mockCommand("claude", [
  'if [ "${1-}" = "--version" ]; then echo claude-fake-2.1.241; exit; fi',
  'printf "%s %s %s\n" "$$" "$MULTIAGENTS_SESSION" "$MULTIAGENTS_SLOT" >> "$MOCK_LOG/provider-pids"',
  'export FAKE_CLAUDE_LOG="$MOCK_LOG/claude-$$.jsonl"',
  'if [ -n "${MOCK_CLAUDE_DELAY-}" ]; then sleep "$MOCK_CLAUDE_DELAY"; fi',
  'exec bun "$REVIEW_LAB/src/tests/fakes/fake-claude.ts" "$@"'
]);
mockCommand("npx", ['case " $* " in *" --version "*) echo gemini-fake-1; exit 0;; esac', 'echo fixture-only >&2','exit 99']);
const env = {
  ...process.env,
  HOME:home, XDG_CONFIG_HOME:join(home,".config"), XDG_CACHE_HOME:join(home,".cache"),
  PATH:bin+":"+process.env.PATH,
  MULTIAGENTS_PORT:String(port), MULTIAGENTS_DB:join(run,"db.sqlite"),
  MULTIAGENTS_CLEANUP_INTERVAL_MS:"120",
  MULTIAGENTS_NO_DASHBOARD:"1",
  MOCK_LOG:run,
};
const awaitUntil = async <T>(proposal: () => Promise<T | false> | T | false, ms = 6000): Promise<T> => {
  const end = performance.now() + ms;
  do {
    const result = await proposal();
    if (result !== false) return result;
    await Bun.sleep(25);
  } while (performance.now() < end);
  throw Error("condition deadline");
};
const post = async (path: string, body: unknown) => {
  const res = await fetch(url+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body),signal:AbortSignal.timeout(2500)});
  const data = await res.json();
  A.equal(res.status,200,path+" "+JSON.stringify(data));
  return data;
};
const slots = (id: string) => post("/slots/list",{session_id:id});
const slot = (id: number) => post("/slots/get",{id});
const session = (id: string) => post("/sessions/get",{id});
const history = (id: string) => post("/message-log",{session_id:id,limit:200});
const pidRows = () => {
  try {return readFileSync(join(run,"provider-pids"),"utf8").trim().split("\n").filter(Boolean).map(line => {const [pid,sid,s] = line.split(" ");return {pid:Number(pid),sid,slot:Number(s)};});}
  catch {return [];}
};
const isRunning = (pid: number) => {
  try {
    const stat = readFileSync("/proc/"+pid+"/stat","utf8");
    return !/^[ZX]/.test(stat.slice(stat.lastIndexOf(")")+2));
  } catch {return false;}
};
const codexLog = (pid: number) => {
  try {return readFileSync(join(run,"codex-"+pid+".jsonl"),"utf8").trim().split("\n").filter(Boolean).map(v=>JSON.parse(v));}
  catch {return [];}
};
const project = (s: string) => join(run,s);
const client = async (tag: string, tuning: Record<string,string> = {}) => {
  const c = await McpStdioClient.spawn(["bun",join(src,"orchestrator/orchestrator-server.ts")],{cwd:run,env:{...env,...tuning},stderrLog:join(run,tag+".log")});
  controllers.push(c);
  return c;
};
const agent = (type:string, name:string, task = "Produce the synthetic fixture") => ({agent_type:type,name,role:"developer",role_description:"Fixture only",initial_task:task});
const create = (c: InstanceType<typeof McpStdioClient>, sid: string, agents: unknown[], plan?: unknown[]) => c.callTool("create_team",{session_name:sid,project_dir:project(sid),agents,...(plan ? {plan} : {})},25000);
const end = (c: InstanceType<typeof McpStdioClient>, sid: string) => c.callTool("end_session",{session_id:sid});
const start = () => {
  const b = Bun.spawn(["bun",join(src,"broker.ts")],{cwd:run,env,stdin:"ignore",stdout:"ignore",stderr:"inherit"});
  children.push(b);
  return b;
};
const killed = async (pid: number) => {
  await awaitUntil(() => !isRunning(pid));
};
const scenario = async (name: string, test: () => Promise<void>) => {
  if (!only(name)) return;
  try { await test(); }
  catch (e) { log(name+" error", String(e)); process.exitCode = 1; }
};
try {
  const broker = start();
  await awaitUntil(async () => {
    try { const r = await fetch(url+"/health",{signal:AbortSignal.timeout(300)});return r.ok && (await r.json()).pid === broker.pid; }
    catch {return false;}
  });


  await Promise.all([
    scenario("S1-watchdog-reresumes",async()=>{
      const sid="crash-watchdog";
      const c=await client(sid);
      const created=await create(c,sid,[agent("codex","worker")]);
      A.equal(created.isError,false,created.text);
      const [s]=await slots(sid);
      await post("/guardrails/update",{session_id:sid,guardrail_id:"max_restarts",new_value:1,changed_by:"orchestrator"});
      const select = () => pidRows().filter(p=>p.sid===sid);
      const guardrail = async () => (await post("/guardrails",{session_id:sid})).find((x:any)=>x.id==="max_restarts").usage;
      const resetWires:unknown[]=[];
      for(let i=0;i<3;i++){
        const p=await awaitUntil(()=>{const candidate=select()[i];return !!candidate&&codexLog(candidate.pid).some(e=>e.request==="turn/start")&&candidate;});
        if (i===0) await awaitUntil(async()=>Boolean(JSON.parse((await slot(s.id)).context_snapshot??"{}").codex_thread_id));
        resetWires.push(codexLog(p.pid).map(e=>e.request));
        process.kill(p.pid,"SIGKILL");
        await killed(p.pid);
      }
      const flapping=await awaitUntil(async()=>{
        const report=await c.callTool("get_team_status",{session_id:sid});
        return /flapping: 3 crashes/.test(report.text)&&report.text.split("\n").filter(x=>x.includes("flapping"));
      },8500);
      const prior=(await slot(s.id)).status;
      const priorSpawns=select().length;
      const usage=await guardrail();
      A.equal(priorSpawns,3);
      A.equal(prior,"disconnected");
      await post("/send-message",{session_id:sid,from_id:"orchestrator",to_slot_id:s.id,msg_type:"chat",text:"non-actionable baseline"});
      await Bun.sleep(11000);
      const afterChat=select().length;
      A.equal(afterChat,3);
      await post("/send-message",{session_id:sid,from_id:"orchestrator",to_slot_id:s.id,msg_type:"system",text:"watchdog actionable fixture"});
      const renewed=await awaitUntil(()=>select()[3]||false,15000);
      A.equal(renewed.slot,s.id);
      const afterRenewal=await guardrail();
      const wire=await awaitUntil(()=>{const recorded=codexLog(renewed.pid);return recorded.some(e=>e.request==="turn/start")&&recorded.map(e=>e.request);});
      log("S1",{priorSpawns,resetWires,prior,usage,flapping,afterChat,relaunchedSlot:renewed.slot,relaunchedWire:wire,afterRenewal});
      await end(c,sid);
      await killed(renewed.pid);
    }),
    scenario("S2-autoarchive",async()=>{
      const sid="completion";
      const c=await client(sid);
      await post("/sessions/create",{id:sid,name:sid,project_dir:run});
      const dev=await post("/slots/create",{session_id:sid,agent_type:"codex",display_name:"author",role:"developer"});
      const qa=await post("/slots/create",{session_id:sid,agent_type:"claude",display_name:"offline reviewer",role:"qa"});
      const worker=Bun.spawn(["sleep","300"],{stdin:"ignore",stdout:"ignore",stderr:"ignore"});
      children.push(worker);
      const registered=await post("/register",{pid:worker.pid,cwd:run,summary:"fixture",session_id:sid,slot_id:dev.id,agent_type:"codex"});
      const start=performance.now();
      const resumed=await c.callTool("resume_session",{session_id:sid,agents_to_skip:["qa"]});
      A.equal(resumed.isError,false,resumed.text);
      const initial=await post("/lifecycle/signal-done",{peer_id:registered.id,session_id:sid,summary:"ready for review"});
      A.equal(initial.task_state,"done_pending_review");
      const pending=await slot(dev.id);
      const approved=await awaitUntil(async()=>{
        const current=await slot(dev.id);
        return current.task_state==="approved"&&current;
      },23000);
      const untilApproved=Math.round(performance.now()-start);
      const logs=await history(sid);
      const approvals=logs.filter((m:any)=>m.msg_type==="approval").length;
      const archived=await awaitUntil(async()=>{
        const current=await session(sid);
        return current.status==="archived"&&current;
      },75000);
      log("S2",{initial:pending.task_state,approved:approved.task_state,untilApprovedMs:untilApproved,approvals,archiveMs:Math.round(performance.now()-start),status:archived.status,reviewer:(await slot(qa.id)).status,workerStillRunning:isRunning(worker.pid), finalSlot:[(await slot(dev.id)).status,(await slot(dev.id)).peer_id]});
    }),
    scenario("S3-controller-race",async()=>{
      const sid="two-owners";
      const c1=await client(sid+"-first",{MOCK_CLAUDE_DELAY:"1.4"});
      const c2=await client(sid+"-second",{MOCK_CLAUDE_DELAY:"1.4"});
      await post("/sessions/create",{id:sid,name:sid,project_dir:run});
      const row=await post("/slots/create",{session_id:sid,agent_type:"claude",display_name:"ambiguous owner",role:"developer"});
      const resume = (c:InstanceType<typeof McpStdioClient>) => c.callTool("resume_session",{session_id:sid});
      const output=await Promise.all([resume(c1),resume(c2)]);
      const current=pidRows().filter(p=>p.sid===sid);
      A.equal(current.length,2);
      const proc1 = current.find(p=>{try{return readFileSync("/proc/"+p.pid+"/status","utf8").match(/^PPid:\s*(\d+)/m)?.[1]===String(c1.pid);}catch{return false;}})!;
      A.ok(proc1);
      const proc2 = current.find(p=>p.pid!==proc1.pid)!;
      const bothBefore=current.map(p=>[p.pid,p.slot,isRunning(p.pid)]);
      await end(c1,sid);
      await killed(proc1.pid);
      A.equal(isRunning(proc2.pid),true);
      const after=await session(sid);
      log("S3",{slot:row.id,reported:output.map(r=>r.text.split("\n").find(x=>x.includes("Respawned"))),bothBefore,foreignAliveAfterFirstEnd:isRunning(proc2.pid),after:after.status});
      await end(c2,sid);
      await killed(proc2.pid);

      const singleSid = "one-owner";
      await post("/sessions/create",{id:singleSid,name:singleSid,project_dir:run});
      const single = await post("/slots/create",{session_id:singleSid,agent_type:"claude",display_name:"single-slot",role:"developer"});
      const same = await Promise.all([c1.callTool("resume_session",{session_id:singleSid}),c1.callTool("resume_session",{session_id:singleSid})]);
      const owned = pidRows().filter(p=>p.sid===singleSid);
      A.equal(owned.length,1);
      A.equal(owned[0].slot,single.id);
      log("S3-single",{reports:same.map(r=>r.text.split("\n").find(x=>x.includes("Respawned")||x.includes("Failed to respawn"))),count:owned.length});
      await end(c1,singleSid);
      await killed(owned[0].pid);
    }),
    scenario("S4-events",async()=>{
      const c=await client("event-drain");
      const labels = ["event-alpha","event-beta"];
      for (const sid of labels) {
        const result=await create(c,sid,[agent("codex",sid+"-worker")]);
        A.equal(result.isError,false,result.text);
      }
      const [a,b] = await Promise.all(labels.map(s=>slots(s).then(x=>x[0])));
      await awaitUntil(async()=>Boolean((await slot(a.id)).input_tokens && (await slot(b.id)).input_tokens));
      const first = await c.callTool("get_team_status",{session_id:labels[0]});
      const second = await c.callTool("get_team_status",{session_id:labels[1]});
      const recent = (text:string) => text.split("\n\nRecent events:\n")[1]?.split("\n").filter(x=>x.includes("Codex turn")) ?? [];
      log("S4",{slots:[a.id,b.id],recentFirst:recent(first.text),recentSecond:recent(second.text)});
      for (const sid of labels) await end(c,sid);
    }),
  ]);
} finally {
  for (const c of controllers.reverse()) if (c.proc.exitCode === null && c.proc.signalCode === null) { c.proc.kill("SIGTERM"); await c.proc.exited; }
  for (const child of children) if (child.exitCode === null && child.signalCode === null) { child.kill("SIGTERM"); await child.exited; }
}
```

</details>

<details>
<summary>process-fresh.ts</summary>

<!-- fixture process-fresh.ts -->
```ts
import { strict as A } from "node:assert";
import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
const root = process.env.REVIEW_LAB!;
const src = join(root,"src");
const { McpStdioClient } = await import(join(src,"tests/helpers/mcp-stdio-client.ts"));
const startCases = process.argv.slice(2);
const only = (name: string) => startCases.length === 0 || startCases.includes(name);
const stamp = () => new Date().toISOString();
function log(label: string, value: unknown) { console.log(stamp(), label, JSON.stringify(value)); }
const controllers: InstanceType<typeof McpStdioClient>[] = [];
const children: ReturnType<typeof Bun.spawn>[] = [];
const port = 17101;
const url = "http://127.0.0.1:" + port;
const run = join(root,"tmp","orchestrator-" + Date.now());
const home = join(run,"home");
const bin = join(run,"bin");
mkdirSync(home,{recursive:true});
mkdirSync(bin);
const mockCommand = (name: string, lines: string[]) => writeFileSync(join(bin,name), ["#!/bin/sh", "set -eu", ...lines, ""].join("\n"), {mode:0o700});
mockCommand("codex", [
  'if [ "${1-}" = "--version" ]; then echo codex-fake-0.156.1; exit; fi',
  'printf "%s %s %s\n" "$$" "$MULTIAGENTS_SESSION" "$MULTIAGENTS_SLOT" >> "$MOCK_LOG/provider-pids"',
  'export FAKE_CODEX_LOG="$MOCK_LOG/codex-$$.jsonl"',
  'if [ -n "${MOCK_WIRE:-}" ]; then exec bun "$MOCK_WIRE" "$@"; fi',
  'exec bun "$REVIEW_LAB/src/tests/fakes/fake-codex-app-server.ts" "$@"'
]);
mockCommand("claude", [
  'if [ "${1-}" = "--version" ]; then echo claude-fake-2.1.241; exit; fi',
  'printf "%s %s %s\n" "$$" "$MULTIAGENTS_SESSION" "$MULTIAGENTS_SLOT" >> "$MOCK_LOG/provider-pids"',
  'export FAKE_CLAUDE_LOG="$MOCK_LOG/claude-$$.jsonl"',
  'if [ -n "${MOCK_CLAUDE_DELAY-}" ]; then sleep "$MOCK_CLAUDE_DELAY"; fi',
  'if [ -n "${MOCK_STUBBORN:-}" ]; then exec bun "$MOCK_STUBBORN" "$@"; fi',
  'exec bun "$REVIEW_LAB/src/tests/fakes/fake-claude.ts" "$@"'
]);
mockCommand("npx", ['case " $* " in *" --version "*) echo gemini-fake-1; exit 0;; esac',
'printf "%s %s %s\n" "$$" "$MULTIAGENTS_SESSION" "$MULTIAGENTS_SLOT" >> "$MOCK_LOG/provider-pids"',
'exec bun "$MOCK_LOG/fake-gemini.ts" "$@"']);
const env = {
  ...process.env,
  HOME:home, XDG_CONFIG_HOME:join(home,".config"), XDG_CACHE_HOME:join(home,".cache"),
  PATH:bin+":"+process.env.PATH,
  MULTIAGENTS_PORT:String(port), MULTIAGENTS_DB:join(run,"db.sqlite"),
  MULTIAGENTS_CLEANUP_INTERVAL_MS:"120",
  MULTIAGENTS_NO_DASHBOARD:"1",
  MOCK_LOG:run,
};
const awaitUntil = async <T>(proposal: () => Promise<T | false> | T | false, ms = 6000): Promise<T> => {
  const end = performance.now() + ms;
  do {
    const result = await proposal();
    if (result !== false) return result;
    await Bun.sleep(25);
  } while (performance.now() < end);
  throw Error("condition deadline");
};
const post = async (path: string, body: unknown) => {
  const res = await fetch(url+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body),signal:AbortSignal.timeout(2500)});
  const data = await res.json();
  A.equal(res.status,200,path+" "+JSON.stringify(data));
  return data;
};
const slots = (id: string) => post("/slots/list",{session_id:id});
const slot = (id: number) => post("/slots/get",{id});
const session = (id: string) => post("/sessions/get",{id});
const history = (id: string) => post("/message-log",{session_id:id,limit:200});
const pidRows = () => {
  try {return readFileSync(join(run,"provider-pids"),"utf8").trim().split("\n").filter(Boolean).map(line => {const [pid,sid,s] = line.split(" ");return {pid:Number(pid),sid,slot:Number(s)};});}
  catch {return [];}
};
const isRunning = (pid: number) => {
  try {
    const stat = readFileSync("/proc/"+pid+"/stat","utf8");
    return !/^[ZX]/.test(stat.slice(stat.lastIndexOf(")")+2));
  } catch {return false;}
};
const codexLog = (pid: number) => {
  try {return readFileSync(join(run,"codex-"+pid+".jsonl"),"utf8").trim().split("\n").filter(Boolean).map(v=>JSON.parse(v));}
  catch {return [];}
};
const project = (s: string) => join(run,s);
const client = async (tag: string, tuning: Record<string,string> = {}) => {
  const c = await McpStdioClient.spawn(["bun",join(src,"orchestrator/orchestrator-server.ts")],{cwd:run,env:{...env,...tuning},stderrLog:join(run,tag+".log")});
  controllers.push(c);
  return c;
};
const agent = (type:string, name:string, task = "Produce the synthetic fixture") => ({agent_type:type,name,role:"developer",role_description:"Fixture only",initial_task:task});
const create = (c: InstanceType<typeof McpStdioClient>, sid: string, agents: unknown[], plan?: unknown[]) => c.callTool("create_team",{session_name:sid,project_dir:project(sid),agents,...(plan ? {plan} : {})},25000);
const end = (c: InstanceType<typeof McpStdioClient>, sid: string) => c.callTool("end_session",{session_id:sid});
const start = () => {
  const b = Bun.spawn(["bun",join(src,"broker.ts")],{cwd:run,env,stdin:"ignore",stdout:"ignore",stderr:"inherit"});
  children.push(b);
  return b;
};
const killed = async (pid: number) => {
  await awaitUntil(() => !isRunning(pid));
};
const scenario = async (name: string, test: () => Promise<void>) => {
  if (!only(name)) return;
  try { await test(); }
  catch (e) { log(name+" error", String(e)); process.exitCode = 1; }
};
try {
  const broker = start();
  await awaitUntil(async () => {
    try { const r = await fetch(url+"/health",{signal:AbortSignal.timeout(300)});return r.ok && (await r.json()).pid === broker.pid; }
    catch {return false;}
  });


  const {Database}=await import("bun:sqlite");
  const fakeWire=join(run,"fake-codex-controlled.ts");
  const fakeSource=readFileSync(join(src,"tests/fakes/fake-codex-app-server.ts"),"utf8");
  const quietBranch = [
    '  } else if (text.includes("SCENARIO:quiet")) {',
    '    await new Promise<void>((resolve) => { wakeSlowTurn = resolve; setTimeout(resolve, 82000); });',
    '    wakeSlowTurn = null;',
    '    if (interruptRequested) status = "interrupted";',
    '  } else if (text.includes("SCENARIO:slow")) {',
  ].join("\n");
  const steerBranch = [
    '      if (process.env.MOCK_GATE) {',
    '        const seenTurn = activeTurn;',
    '        const timer = setInterval(() => {if (fs.existsSync(process.env.MOCK_GATE!)) {clearInterval(timer);reply(id,{turnId:seenTurn});}}, 10);',
    '        return;',
    '      }',
    '      return reply(id, { turnId: activeTurn });',
  ].join("\n");
  writeFileSync(fakeWire,fakeSource.replace('  } else if (text.includes("SCENARIO:slow")) {',quietBranch).replace('      return reply(id, { turnId: activeTurn });',steerBranch));
  writeFileSync(join(run,"fake-gemini.ts"), [
    'const child=Bun.spawn(["sleep","300"],{stdin:"ignore",stdout:"ignore",stderr:"ignore"});child.unref();',
    'require("fs").appendFileSync(process.env.MOCK_LOG+"/descendants",JSON.stringify([process.env.MULTIAGENTS_SESSION,process.pid,child.pid])+"\\n");',
    'process.on("SIGTERM",()=>process.exit(0));',
    'process.stdin.on("data",()=>{});setInterval(()=>{},1000);',
  ].join("\n"));
  const stubborn=join(run,"fake-stubborn-claude.ts");
  writeFileSync(stubborn,[
    'const out=m=>process.stdout.write(JSON.stringify(m)+"\\n");let buf="", init=false;',
    'process.on("SIGTERM",()=>require("fs").appendFileSync(process.env.MOCK_LOG+"/stub-term",String(process.pid)+"\\n"));',
    'process.stdin.on("data",chunk=>{buf+=chunk.toString();const lines=buf.split("\\n");buf=lines.pop();for(const line of lines){',
    'const m=JSON.parse(line);if(!init){init=true;out({type:"system",subtype:"init",session_id:"stubborn-fake"});}',
    'out({type:"user",isReplay:true,message:m.message});out({type:"result",subtype:"success",result:"fixture"});}});',
    'process.stdin.on("end",()=>{});setInterval(()=>{},1000);',
  ].join("\n"));
  const rowsFor=(sid:string)=>pidRows().filter(p=>p.sid===sid);
  const offspring=(sid:string):Array<[string,number,number]>=>{
    try {return readFileSync(join(run,"descendants"),"utf8").trim().split("\n").filter(Boolean).map(x=>JSON.parse(x)).filter(x=>x[0]===sid);}
    catch {return [];}
  };
  const killOwned = (pid:number) => { if (isRunning(pid)) process.kill(pid,"SIGKILL"); };
  const seedPeer = async (sid:string,slotId:number,wantedPid?:number) => {
    let pid=wantedPid;
    if (pid===undefined) {
      const child=Bun.spawn(["sleep","300"],{stdin:"ignore",stdout:"ignore",stderr:"ignore"});
      children.push(child);pid=child.pid;
    }
    const peer=await post("/register",{session_id:sid,slot_id:slotId,pid,cwd:project(sid),agent_type:(await slot(slotId)).agent_type,summary:"synthetic peer"});
    return peer;
  };
  const mail=(session_id:string,to_slot_id:number,text:string,msg_type="chat")=>post("/send-message",{session_id,to_slot_id,from_id:"orchestrator",text,msg_type});
  const unread=(slot_id:number)=>post("/peek-undelivered",{slot_id});

  await Promise.all([
    scenario("P1-descendant",async()=>{
      const sid="process-tree";
      const c=await client(sid);
      A.equal((await create(c,sid,[agent("gemini","runner")])).isError,false);
      const [_,leader,child] = await awaitUntil(()=>offspring(sid)[0]||false);
      try {
        await end(c,sid);
        await killed(leader);
        const leaderGone=!isRunning(leader);
        const childAlive=isRunning(child);
        const parent=readFileSync("/proc/"+child+"/status","utf8").match(/^PPid:\s*(\d+)/m)?.[1];
        log("P1",{leader,child,leaderGone,childAlive,childNowParent:parent,session:(await session(sid)).status});
      } finally {killOwned(leader);killOwned(child);}
    }),
    scenario("P2-pause-turn",async()=>{
      const sid="pause-current";
      const c=await client(sid);
      A.equal((await create(c,sid,[agent("codex","pause-worker","SCENARIO:slow:5000")])).isError,false);
      const [s]=await slots(sid);
      const provider=await awaitUntil(()=>rowsFor(sid)[0]||false);
      const peer=await seedPeer(sid,s.id);
      await awaitUntil(()=>codexLog(provider.pid).filter(x=>x.request==="turn/start").length>=2);
      const old=await slot(s.id);
      const lock=await post("/files/acquire",{session_id:sid,slot_id:s.id,peer_id:peer.id,file_path:"status.txt"});
      A.equal(lock.status,"acquired");
      const paused=await c.callTool("control_session",{session_id:sid,action:"pause_agent",target:String(s.id)});
      await mail(sid,s.id,"held when paused");
      const held=(await history(sid)).find((m:any)=>m.text==="held when paused");
      const notices=(await history(sid)).filter((m:any)=>m.msg_type==="control");
      const blocked=await post("/poll-by-slot",{slot_id:s.id,retain:true});
      const locks=(await post("/files/locks",{session_id:sid})).length;
      const after=await awaitUntil(async()=>{const x=await slot(s.id);return x.input_tokens>=240&&x;},9500);
      const interrupts=codexLog(provider.pid).filter(x=>x.request==="turn/interrupt").length;
      log("P2",{paused:paused.text,oldTokens:old.input_tokens,newTokens:after.input_tokens,slotPaused:after.paused,mailHeld:held.held,notice:notices.map((x:any)=>[x.held,x.acked_at]),blocked,locks,interrupts});
      await end(c,sid);
      await killed(provider.pid);
    }),
    scenario("P3-head-of-line",async()=>{
      const sid="slow-steer";
      const other="healthy-other";
      const gate=join(run,"release-steer.gate");
      const c=await client(sid,{MOCK_GATE:gate,MOCK_WIRE:fakeWire});
      A.equal((await create(c,sid,[agent("codex","first","SCENARIO:slow:29000")])).isError,false);
      A.equal((await create(c,other,[agent("claude","second")])).isError,false);
      const [a]=await slots(sid);
      const [b]=await slots(other);
      const provider=await awaitUntil(()=>rowsFor(sid)[0]||false);
      const startBaseline=performance.now();
      await mail(other,b.id,"healthy baseline");
      await awaitUntil(async()=> (await unread(b.id)).count===0,5500);
      const baselineMs=Math.round(performance.now()-startBaseline);
      await mail(sid,a.id,"gated steer delivery");
      await awaitUntil(()=>codexLog(provider.pid).some(x=>x.request==="turn/steer"),5500);
      const blockedSince=performance.now();
      await mail(other,b.id,"healthy behind slow slot");
      await Bun.sleep(4350);
      const withheld=await unread(b.id);
      const waitedMs=Math.round(performance.now()-blockedSince);
      writeFileSync(gate,"continue");
      const released=performance.now();
      await awaitUntil(async()=> (await unread(b.id)).count===0,5000);
      const after=Math.round(performance.now()-released);
      log("P3",{baselineMs,waitedMs,unclaimedWhileGated:withheld.unclaimed_count,pendingWhileGated:withheld.count,afterGateMs:after,healthyAfter:(await unread(b.id)).count});
      await end(c,other); await end(c,sid);
    }),
    scenario("P4-quiet-active",async()=>{
      const sid="quiet-turn";
      const c=await client(sid,{MOCK_WIRE:fakeWire});
      A.equal((await create(c,sid,[agent("codex","quiet","SCENARIO:quiet")])).isError,false);
      const [s]=await slots(sid);
      const worker=await awaitUntil(()=>rowsFor(sid)[0]||false);
      const promptStarts=()=>codexLog(worker.pid).filter(x=>x.request==="turn/start");
      await awaitUntil(()=>promptStarts().length>=2);
      const started=performance.now();
      const replaced=await awaitUntil(()=>promptStarts().find(x=>x.params.input[0].text.includes("Your previous task is complete."))||false,77000);
      const wire=codexLog(worker.pid);
      const health=await slot(s.id);
      log("P4",{ms:Math.round(performance.now()-started),heartbeat:wire.filter(x=>x.request==="thread/list").length,interrupted:wire.filter(x=>x.request==="turn/interrupt").length,completionPrompt:replaced.params.input[0].text,persistedTask:health.task_state});
      await end(c,sid);
    }),
    scenario("P5-release-drain",async()=>{
      const sid="release-drain";
      const c=await client(sid);
      A.equal((await create(c,sid,[agent("claude","release-worker")])).isError,false);
      const [s]=await slots(sid);
      await seedPeer(sid,s.id);
      const p=await awaitUntil(()=>rowsFor(sid)[0]||false);
      const release=await c.callTool("release_agent",{session_id:sid,target:String(s.id)});
      const before=(await unread(s.id)).count;
      await awaitUntil(()=>!isRunning(p.pid),10000);
      const logRows=await history(sid);
      const releaseMsg=logRows.find((m:any)=>m.msg_type==="release");
      const wire=readFileSync(join(run,"claude-"+p.pid+".jsonl"),"utf8");
      log("P5",{release:release.text,before,sawRelease:wire.includes("RELEASED"),acked:Boolean(releaseMsg.acked_at),procAlive:isRunning(p.pid),newSpawns:rowsFor(sid).length,state:(await slot(s.id)).task_state});
      await end(c,sid);
    }),
    scenario("P6-shutdown-escalation",async()=>{
      for (const mode of ["explicit-end","owner-sigterm"]) {
        const sid="stubborn-"+mode;
        const c=await client(sid,{MOCK_STUBBORN:stubborn});
        A.equal((await create(c,sid,[agent("claude","stubborn")])).isError,false);
        const p=await awaitUntil(()=>rowsFor(sid)[0]||false);
        try {
          const begun=performance.now();
          if(mode==="explicit-end") await end(c,sid);
          else {c.proc.kill("SIGTERM");await c.proc.exited;}
          await Bun.sleep(3475);
          const observed=readFileSync(join(run,"stub-term"),"utf8").split("\n").includes(String(p.pid));
          log("P6 "+mode,{ms:Math.round(performance.now()-begun),termObserved:observed,childAlive:isRunning(p.pid),controllerAlive:isRunning(c.pid)});
        } finally {killOwned(p.pid);}
      }
    }),
    scenario("P7-watchdog-age-mix",async()=>{
      const sid="mixed-age";
      const c=await client(sid);
      A.equal((await create(c,sid,[agent("gemini","mail-worker")])).isError,false);
      const [s]=await slots(sid);
      const first=await awaitUntil(()=>rowsFor(sid)[0]||false);
      await seedPeer(sid,s.id,first.pid);
      try {
        await mail(sid,s.id,"old chat");
        const db=new Database(env.MULTIAGENTS_DB);
        db.run("PRAGMA busy_timeout=3000");
        db.query("UPDATE messages SET sent_at = ? WHERE session_id = ?").run(new Date(Date.now()-121000).toISOString(),sid);
        db.close();
        await Bun.sleep(11100);
        const noWake=rowsFor(sid).length;
        A.equal(noWake,1);
        const mark=performance.now();
        await mail(sid,s.id,"fresh system request","system");
        const gate=await unread(s.id);
        const firstNew=await awaitUntil(()=>rowsFor(sid)[1]||false,13500);
        const age=Math.round(performance.now()-mark);
        await Bun.sleep(1550);
        const total=rowsFor(sid).length;
        const after = rowsFor(sid).slice(1);
        const beforeEnd = after.map(p=>[p.pid,isRunning(p.pid)]);
        const priorAlive = isRunning(first.pid);
        await end(c,sid);
        await killed(after.at(-1)!.pid);
        log("P7",{oldOnlyLaunchCount:noWake,unclaimedKinds:gate.unclaimed_msg_types,freshAgeAtRestartMs:age,newPid:firstNew.pid,total,priorAlive,beforeEnd,afterEnd:after.map(p=>[p.pid,isRunning(p.pid)])});
      } finally {for (const [_,leader,child] of offspring(sid)){killOwned(leader);killOwned(child);}}
    }),
  ]);
} finally {
  for (const c of controllers.reverse()) if (c.proc.exitCode === null && c.proc.signalCode === null) { c.proc.kill("SIGTERM"); await c.proc.exited; }
  for (const child of children) if (child.exitCode === null && child.signalCode === null) { child.kill("SIGTERM"); await child.exited; }
}
```

</details>

<details>
<summary>resource-fresh.ts</summary>

<!-- fixture resource-fresh.ts -->
```ts
import { strict as A } from "node:assert";
import { Database } from "bun:sqlite";
import { mkdirSync, statSync } from "node:fs";
import { join } from "node:path";
const root = process.env.REVIEW_LAB!;
const cases = new Set(process.argv.slice(2));
const included = (s: string) => cases.size === 0 || cases.has(s);
const stamp = () => new Date().toISOString();
const out = (label: string, fact: unknown) => console.log(stamp(), label, JSON.stringify(fact));
const brokerPath = join(root, "src/broker.ts");
let nextPort = 17000;

async function until<T>(sample: () => Promise<T | false>, timeout = 4000): Promise<T> {
  const end = performance.now() + timeout;
  do {
    const result = await sample();
    if (result !== false) return result;
    await Bun.sleep(20);
  } while (performance.now() < end);
  throw Error("condition deadline");
}
type Process = ReturnType<typeof Bun.spawn>;
async function scenario(name: string, sweepMs: number, run: (h: Awaited<ReturnType<typeof make>>) => Promise<void>) {
  if (!included(name)) return;
  const h = await make(name, sweepMs);
  try { await run(h); }
  catch (e) { out(name + " error", String(e)); process.exitCode = 1; }
  finally { await h.finish(); }
}
async function make(name: string, sweepMs: number) {
  const port = nextPort++;
  const cwd = join(root, "tmp", name + "-" + Date.now());
  const dbPath = join(cwd, "db.sqlite");
  const base = "http://127.0.0.1:" + port;
  mkdirSync(cwd);
  const children: Process[] = [];
  let broker: Process | undefined;
  const spawn = (argv: string[], additional = {}) => {
    const proc = Bun.spawn(argv, { cwd, stdin: "ignore", stdout: "ignore", stderr: "inherit", ...additional });
    children.push(proc);
    return proc;
  };
  const boot = async () => {
    broker = spawn(["bun", brokerPath], { env: { ...process.env, MULTIAGENTS_PORT: String(port), MULTIAGENTS_DB: dbPath, MULTIAGENTS_CLEANUP_INTERVAL_MS: String(sweepMs) } });
    const instance = broker;
    await until(async () => {
      if (instance.exitCode !== null) throw Error("broker exited early: " + instance.exitCode);
      try { const res = await fetch(base + "/health", { signal: AbortSignal.timeout(300) }); return res.ok && (await res.json()).pid === instance.pid; }
      catch { return false; }
    });
    return instance.pid;
  };
  const stop = async (signal: "SIGTERM" | "SIGKILL" = "SIGTERM") => {
    if (!broker || broker.exitCode !== null) return;
    broker.kill(signal);
    await broker.exited;
  };
  const raw = async (path: string, data: unknown) => {
    const response = await fetch(base + path, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(data), signal: AbortSignal.timeout(18000) });
    return {status: response.status, data: await response.json()};
  };
  const post = async (path: string, data: unknown) => {
    const result = await raw(path, data);
    A.equal(result.status, 200, path + " " + JSON.stringify(result.data));
    return result.data;
  };
  const session = (id = name) => post("/sessions/create", { id, name: id, project_dir: cwd });
  const slot = (id = name, role = "developer") => post("/slots/create", { session_id: id, agent_type: "claude", role, display_name: role });
  const readSlot = (id: number) => post("/slots/get", { id });
  const worker = () => spawn(["sleep", "600"]);
  const register = (proc: Process, slotId: number, sessionId = name) => post("/register", { pid: proc.pid, cwd, git_root: cwd, tty: null, summary: "fixture-ready", agent_type: "claude", session_id: sessionId, slot_id: slotId });
  const send = (toSlot: number, text: string, sessionId = name) => post("/send-message", {session_id: sessionId, from_id: "orchestrator", to_slot_id: toSlot, text});
  const kill = async (proc: Process) => { proc.kill("SIGKILL"); await proc.exited; };
  const finish = async () => {
    await stop();
    await Promise.all(children.filter(p => p.exitCode === null && p.signalCode === null).map(kill));
  };
  await boot();
  return { cwd, dbPath, spawn, worker, boot, stop, finish, raw, post, session, slot, readSlot, register, send, kill };
}


import {readFileSync} from "node:fs";
const src=join(root,"src");
const {BrokerClient}=await import(join(src,"shared/broker-client.ts"));
const {enforceGuardrails}=await import(join(src,"orchestrator/guardrails.ts"));
const port=()=>nextPort-1;
const address=()=>"http://127.0.0.1:"+port();
async function timed<T>(f:()=>Promise<T>){const start=performance.now();const value=await f();return {ms:+(performance.now()-start).toFixed(3),value};}
function percentile(arr:number[],p:number){return [...arr].sort((a,b)=>a-b)[Math.ceil(arr.length*p)-1];}

await scenario("R1-poll-growth",30000,async h=>{
  const s=await h.session();
  const idle=await h.slot();
  const busy=await h.slot();
  const sql=new Database(h.dbPath);
  sql.run("PRAGMA busy_timeout = 2500");
  const select="SELECT * FROM messages WHERE to_slot_id = ? AND acked_at IS NULL AND held = 0 ORDER BY sent_at ASC";
  const qp=()=>(sql.query("EXPLAIN QUERY PLAN "+select).all(idle.id) as any[]).map(row=>row.detail);
  const schema=sql.query("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'messages'").all();
  const size0=statSync(h.dbPath+"-wal").size;
  const write=sql.prepare("INSERT INTO messages (from_id,to_id,text,sent_at,delivered,session_id,to_slot_id,msg_type,held,acked_at) VALUES ('fixture','fixture',?,?,?,?,?,'chat',0,?)");
  let rows=0;
  const makeRows=sql.transaction((end:number,slot:number,acked:boolean)=>{
    for(let i=rows;i<end;i++){
      const t=new Date(1795100000000+i).toISOString();
      write.run("x".repeat(128),t,acked?1:0,s.id,slot,acked?t:null);
    }
    rows=end;
  });
  const probe=async (n=31)=>{
    const times:number[]=[];
    for(let i=0;i<n;i++){
      const r=await timed(()=>h.post("/poll-by-slot",{slot_id:idle.id,retain:true}));
      A.equal(r.value.messages.length,0);
      if(i>0)times.push(r.ms);
    }
    return {n:times.length,p50:percentile(times,0.5),p95:percentile(times,0.95)};
  };
  const baseline=[];
  for(const n of [0,1000,10000,100000]){
    makeRows(n,busy.id,true);
    baseline.push({n,search:qp(),latency:await probe()});
  }
  sql.run("CREATE INDEX fixture_active_mail ON messages(to_slot_id,sent_at) WHERE acked_at IS NULL AND held=0");
  const indexed={search:qp(),latency:await probe()};
  const schemaWriter = new Database(h.dbPath);
  schemaWriter.run("PRAGMA busy_timeout = 2500");
  schemaWriter.run("DROP INDEX fixture_active_mail");
  schemaWriter.close();
  makeRows(101000,busy.id,false);
  out("R1 stage","first poll start");
  const first=await timed(()=>h.post("/poll-by-slot",{slot_id:busy.id,retain:true}));
  out("R1 stage",{firstPoll: first.ms, n: first.value.messages.length});
  const repeated=await timed(()=>h.post("/poll-by-slot",{slot_id:busy.id,retain:true}));
  out("R1 stage",{repeated:repeated.ms,n:repeated.value.messages.length});
  const ids=first.value.messages.map((m:any)=>m.id);
  A.equal(ids.length,1000);
  A.deepEqual(repeated.value.messages.map((m:any)=>m.id),ids);
  out("R1 stage","ack start");
  const ack=await timed(()=>h.post("/ack-messages",{ids}));
  A.equal(ack.value.acked,1000);
  const bytes=Buffer.byteLength(JSON.stringify(first.value));
  const walAfter=statSync(h.dbPath+"-wal").size;
  sql.close();
  out("R1",{schema,base:baseline,partialIndex:indexed,unackedBatch:ids.length,firstPollMs:first.ms,repeatedPollMs:repeated.ms,ackMs:ack.ms,responseBytes:bytes,walBefore:size0,walAfter});
});

await scenario("R2-writer-contention",30000,async h=>{
  const s=await h.session();
  const sl=await h.slot();
  const sql=new Database(h.dbPath);
  const health=()=>fetch(address()+"/health",{signal:AbortSignal.timeout(6000)}).then(r=>r.json());
  const slowWrite=async()=>{
    const r=await fetch(address()+"/send-message",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({session_id:s.id,from_id:"orchestrator",to_slot_id:sl.id,text:"controlled contention fixture"}),signal:AbortSignal.timeout(6500)});
    return {status:r.status,body:await r.json()};
  };
  const baseline=await timed(health);
  sql.run("BEGIN IMMEDIATE");
  const whileOnlyReader=await timed(health);
  sql.run("ROLLBACK");
  const observations=[];
  for(const holdMs of [450,1400,3400]){
    sql.run("BEGIN IMMEDIATE");
    const unlock=Bun.sleep(holdMs).then(()=>{sql.run("ROLLBACK");});
    const lateWrite=timed(slowWrite);
    await Bun.sleep(75);
    const concurrent=timed(health);
    const localTimer=timed(()=>Bun.sleep(25));
    const [writeResult,readResult,clientDelay]=await Promise.all([lateWrite,concurrent,localTimer,unlock]);
    observations.push({holdMs,writeResult,readMs:readResult.ms,clientDelayMs:clientDelay.ms});
  }
  sql.close();
  const successful=(await h.post("/message-log",{session_id:s.id,limit:10})).length;
  out("R2",{baselineMs:baseline.ms,whileOnlyReaderMs:whileOnlyReader.ms,observations,successful});
});

await scenario("R3-guardrail-stop",30000,async h=>{
  const s=await h.session();
  const sl=await h.slot();
  const worker=h.worker();
  await h.register(worker,sl.id);
  const client=new BrokerClient(address());
  const set=async(guardrail_id:string,new_value:number)=>h.post("/guardrails/update",{session_id:s.id,guardrail_id,new_value,changed_by:"orchestrator"});
  await set("max_restarts",1);
  await set("agent_count",0.5);
  await set("session_duration",0.00001);
  const get=async(id:string)=>(await client.getGuardrails(s.id)).find((x:any)=>x.id===id);
  const before=(await get("max_restarts")).usage;
  await h.post("/agent-event",{session_id:s.id,slot_id:sl.id,event_type:"agent_exited",metadata:{counter:"synthetic positive control"}});
  const restart=(await get("max_restarts")).usage;
  const duration=(await get("session_duration")).usage;
  const agentCount=(await get("agent_count")).usage;
  const events:any[]=[];
  await enforceGuardrails(s.id,client,(evt:any)=>events.push(evt));
  const after=await h.readSlot(sl.id);
  const processStat=readFileSync("/proc/"+worker.pid+"/stat","utf8").split(" ")[2];
  out("R3",{before,restart,duration,agentCount,events,sessionStatus:(await h.post("/sessions/get",{id:s.id})).status,slot:[after.status,after.paused,after.task_state],processStat});
});

await scenario("R4-equal-timestamp",30000,async h=>{
  const s=await h.session();
  const sl=await h.slot();
  const p1=await h.register(h.worker(),sl.id);
  const matching="2026-11-19T10:11:12.000Z";
  for(const label of ["one","two","three"]) await h.send(sl.id,label);
  const db=new Database(h.dbPath);
  db.query("UPDATE messages SET sent_at = ?").run(matching);
  const poll=await h.post("/poll-by-slot",{slot_id:sl.id,retain:true});
  const history=await h.post("/message-log",{session_id:s.id,limit:10});
  const recap=await h.register(h.worker(),sl.id);
  const compact=(rows:any[])=>rows.map(m=>[m.id,m.text,m.sent_at]);
  out("R4",{poll:compact(poll.messages),history:compact(history),recap:compact(recap.recap)});
  db.close();
});
```

</details>

<details>
<summary>monitor-fresh.ts</summary>

<!-- fixture monitor-fresh.ts -->
```ts
import { strict as A } from "node:assert";
import { Database } from "bun:sqlite";
import { mkdirSync, statSync } from "node:fs";
import { join } from "node:path";
const root = process.env.REVIEW_LAB!;
const cases = new Set(process.argv.slice(2));
const included = (s: string) => cases.size === 0 || cases.has(s);
const stamp = () => new Date().toISOString();
const out = (label: string, fact: unknown) => console.log(stamp(), label, JSON.stringify(fact));
const brokerPath = join(root, "src/broker.ts");
let nextPort = 17000;

async function until<T>(sample: () => Promise<T | false>, timeout = 4000): Promise<T> {
  const end = performance.now() + timeout;
  do {
    const result = await sample();
    if (result !== false) return result;
    await Bun.sleep(20);
  } while (performance.now() < end);
  throw Error("condition deadline");
}
type Process = ReturnType<typeof Bun.spawn>;
async function scenario(name: string, sweepMs: number, run: (h: Awaited<ReturnType<typeof make>>) => Promise<void>) {
  if (!included(name)) return;
  const h = await make(name, sweepMs);
  try { await run(h); }
  catch (e) { out(name + " error", {e:String(e),stack:String((e as Error).stack).split("\n").slice(0,6)}); process.exitCode = 1; }
  finally { await h.finish(); }
}
async function make(name: string, sweepMs: number) {
  const port = nextPort++;
  const cwd = join(root, "tmp", name + "-" + Date.now());
  const dbPath = join(cwd, "db.sqlite");
  const base = "http://127.0.0.1:" + port;
  mkdirSync(cwd);
  const children: Process[] = [];
  let broker: Process | undefined;
  const spawn = (argv: string[], additional = {}) => {
    const proc = Bun.spawn(argv, { cwd, stdin: "ignore", stdout: "ignore", stderr: "inherit", ...additional });
    children.push(proc);
    return proc;
  };
  const boot = async () => {
    broker = spawn(["bun", brokerPath], { env: { ...process.env, MULTIAGENTS_PORT: String(port), MULTIAGENTS_DB: dbPath, MULTIAGENTS_CLEANUP_INTERVAL_MS: String(sweepMs) } });
    const instance = broker;
    await until(async () => {
      if (instance.exitCode !== null) throw Error("broker exited early: " + instance.exitCode);
      try { const res = await fetch(base + "/health", { signal: AbortSignal.timeout(300) }); return res.ok && (await res.json()).pid === instance.pid; }
      catch { return false; }
    });
    return instance.pid;
  };
  const stop = async (signal: "SIGTERM" | "SIGKILL" = "SIGTERM") => {
    if (!broker || broker.exitCode !== null) return;
    broker.kill(signal);
    await broker.exited;
  };
  const raw = async (path: string, data: unknown) => {
    const response = await fetch(base + path, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(data), signal: AbortSignal.timeout(3000) });
    return {status: response.status, data: await response.json()};
  };
  const post = async (path: string, data: unknown) => {
    const result = await raw(path, data);
    A.equal(result.status, 200, path + " " + JSON.stringify(result.data));
    return result.data;
  };
  const session = (id = name) => post("/sessions/create", { id, name: id, project_dir: cwd });
  const slot = (id = name, role = "developer") => post("/slots/create", { session_id: id, agent_type: "claude", role, display_name: role });
  const readSlot = (id: number) => post("/slots/get", { id });
  const worker = () => spawn(["sleep", "600"]);
  const register = (proc: Process, slotId: number, sessionId = name) => post("/register", { pid: proc.pid, cwd, git_root: cwd, tty: null, summary: "fixture-ready", agent_type: "claude", session_id: sessionId, slot_id: slotId });
  const send = (toSlot: number, text: string, sessionId = name) => post("/send-message", {session_id: sessionId, from_id: "orchestrator", to_slot_id: toSlot, text});
  const kill = async (proc: Process) => { proc.kill("SIGKILL"); await proc.exited; };
  const finish = async () => {
    await stop();
    await Promise.all(children.filter(p => p.exitCode === null && p.signalCode === null).map(kill));
  };
  await boot();
  return { cwd, dbPath, spawn, worker, boot, stop, finish, raw, post, session, slot, readSlot, register, send, kill };
}


import {readFileSync,writeFileSync} from "node:fs";
const src=join(root,"src");
const {BrokerClient}=await import(join(src,"shared/broker-client.ts"));
const {monitorCodexDriver,clearSlotTracking}=await import(join(src,"orchestrator/monitor.ts"));
const {assessHealth}=await import(join(src,"orchestrator/progress.ts"));
const {probeBrokerHealth,listeningPids}=await import(join(src,"cli/update.ts"));
const {McpStdioClient}=await import(join(src,"tests/helpers/mcp-stdio-client.ts"));
const port=()=>nextPort-1;
const address=()=>"http://127.0.0.1:"+port();
const nsPort=()=>String(port());

await scenario("M1-token-generations",30000,async h=>{
  const s=await h.session();
  const sl=await h.slot();
  const updates:any[]=[];
  const client=new BrokerClient(address());
  const update=client.updateSlot.bind(client);
  client.updateSlot=async (data:any)=>{
    const resp=await update(data);updates.push(data);return resp;
  };
  let note:(x:any)=>void=()=>{};
  const fake={onNotification(cb:(n:any)=>void){note=cb;}};
  monitorCodexDriver(fake as any,sl.id,s.id,client,()=>{});
  const emit=(threadId:string,inputTokens:number)=>note({method:"thread/tokenUsage/updated",threadId,params:{threadId,tokenUsage:{total:{inputTokens}}}});
  const read=async()=> (await h.readSlot(sl.id)).input_tokens;
  const eq=async (n:number)=>until(async()=>await read()===n);
  emit("thread-A",120);await eq(120);
  emit("thread-A",240);await eq(240);
  emit("thread-A",240);
  await Bun.sleep(75);
  const duplicate=await read();
  emit("thread-B",120);
  await Bun.sleep(75);
  const newThreadOne=await read();
  emit("thread-B",240);
  await eq(360);
  const newThreadTwo=await read();
  clearSlotTracking(sl.id);
  emit("thread-B",360);await eq(720);
  out("M1",{duplicate,newThreadOne,newThreadTwo,afterReset:await read(),writtenDeltas:updates.map(x=>x.input_tokens)});
});

await scenario("M2-charge-after-503",30000,async h=>{
  const s=await h.session(),sl=await h.slot();
  clearSlotTracking(sl.id); // isolate module-scoped counters across synthetic DBs
  let writeCount=0;
  const proxy=Bun.serve({hostname:"127.0.0.1",port:0,async fetch(req){
    const path=new URL(req.url).pathname;
    const body=req.method==="POST"?await req.text():undefined;
    if(path==="/slots/update") {
      writeCount++;
      out("M2 update request",{writeCount,body,address:address()});
      if (writeCount===1) return new Response("controlled write rejection",{status:503});
    }
    const response=await fetch(address()+path,{method:req.method,headers:req.headers,body});
    if(path==="/slots/update") out("M2 proxy response",{status:response.status,body:await response.clone().text()});
    return response;
  }});
  try {
    let note:(x:any)=>void=()=>{};
    const fake={onNotification(cb:(n:any)=>void){note=cb;}};
    monitorCodexDriver(fake as any,sl.id,s.id,new BrokerClient("http://127.0.0.1:"+proxy.port),()=>{});
    const emit=(inputTokens:number)=>note({method:"thread/tokenUsage/updated",params:{threadId:"fixed",tokenUsage:{total:{inputTokens}}}});
    const token=async()=> (await h.readSlot(sl.id)).input_tokens;
    emit(100);
    await until(async()=>writeCount>=1);
    const immediately=await token();
    out("M2 after rejection",{immediately,writeCount});
    emit(200);
    await until(async()=>await token()===100);
    emit(200);
    await Bun.sleep(80);
    out("M2",{firstRejected:immediately,realCumulative:200,broker:await token(),writeCount});
  } finally {proxy.stop(true);}
});

await scenario("M3-health-schema",30000,async h=>{
  const plain=Bun.serve({hostname:"127.0.0.1",port:0,fetch(){return new Response("unrelated local fixture");}});
  try {
    const selected="http://127.0.0.1:"+plain.port;
    const httpOnly=await new BrokerClient(selected).isAlive();
    const checked=await probeBrokerHealth(selected);
    const actual=await probeBrokerHealth(address());
    const unknown=(await fetch(address()+"/healthz")).status;
    out("M3",{httpOnly,checked,actual,unknown});
  } finally {plain.stop(true);}
});

await scenario("M4-health-snapshot",30000,async h=>{
  const s=await h.session();
  const sl=await h.slot();
  await h.post("/slots/update",{id:sl.id,status:"connected",context_patch:{updated_at:Date.now(),last_summary:"current"}});
  const good=assessHealth(await h.readSlot(sl.id));
  const c=await McpStdioClient.spawn(["bun",join(src,"orchestrator/orchestrator-server.ts")],{cwd:h.cwd,env:{...process.env,MULTIAGENTS_PORT:nsPort(),MULTIAGENTS_NO_DASHBOARD:"1"},stderrLog:join(h.cwd,"monitor.log")});
  try {
    const status=(opts={})=>c.callTool("get_team_status",{session_id:s.id,...opts});
    const prior=await status();
    await h.post("/slots/update",{id:sl.id,context_snapshot:"legacy: disconnected"});
    const malformed=await status();
    await h.post("/slots/update",{id:sl.id,context_patch:{updated_at:Date.now(),last_summary:"recovered"}});
    const recovered=await status();
    const newSlot=await h.slot(s.id,"another");
    out("M4",{good,prior:prior.isError,malformed,recovered:recovered.isError,neverConnected:assessHealth({...newSlot,created_at:Date.now()-24*3600_000})});
  } finally {c.proc.kill();await c.proc.exited;}
});

await scenario("M5-lsof-contract",30000,async h=>{
  const bound=17255;
  const native=h.spawn(["bun","-e","Bun.serve({hostname:'127.0.0.1',port:"+bound+",fetch:()=>new Response('ready')})"]);
  await until(async()=>{try{return (await fetch("http://127.0.0.1:"+bound)).ok;}catch{return false;}});
  const connected=await Bun.connect({hostname:"127.0.0.1",port:bound,socket:{data(){}}});
  const wrapper=join(h.cwd,"lsof-fixture");
  writeFileSync(wrapper,[
    "#!/bin/sh","set -eu",'[ "$#" = 3 ] && [ "$1" = "-ti" ] && [ "$3" = "-sTCP:LISTEN" ]',
    'case "$2" in tcp:*) selected="${2#tcp:}";; *) exit 24;; esac',
    "ss -H -ltnp \"sport = :$selected\" | sed -En 's/.*pid=([0-9]+).*/\\1/p'",
    "",
  ].join("\n").replaceAll("\\$","$"),{mode:0o700});
  try{
    const ss=Bun.spawnSync(["ss","-H","-ltnp","sport = :"+bound]).stdout.toString().trim();
    const result=listeningPids(bound,{lsof:wrapper});
    A.deepEqual(result,[String(native.pid)]);
    out("M5",{nativeLsof:Boolean(Bun.which("lsof")),expected:native.pid,client:process.pid,processSelection:result,socket:ss});
  } finally {connected.end();}
});
```

</details>

<details>
<summary>launch-fresh.ts</summary>

<!-- fixture launch-fresh.ts -->
```ts
import { strict as A } from "node:assert";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
const root = process.env.REVIEW_LAB!;
const src = join(root,"src");
const { McpStdioClient } = await import(join(src,"tests/helpers/mcp-stdio-client.ts"));
const startCases = process.argv.slice(2);
const only = (name: string) => startCases.length === 0 || startCases.includes(name);
const stamp = () => new Date().toISOString();
function log(label: string, value: unknown) { console.log(stamp(), label, JSON.stringify(value)); }
const controllers: InstanceType<typeof McpStdioClient>[] = [];
const children: ReturnType<typeof Bun.spawn>[] = [];
const port = 17101;
const url = "http://127.0.0.1:" + port;
const run = join(root,"tmp","orchestrator-" + Date.now());
const home = join(run,"home");
const bin = join(run,"bin");
mkdirSync(home,{recursive:true});
mkdirSync(bin);
const mockCommand = (name: string, lines: string[]) => writeFileSync(join(bin,name), ["#!/bin/sh", "set -eu", ...lines, ""].join("\n"), {mode:0o700});
mockCommand("codex", [
  'if [ "${1-}" = "--version" ]; then echo codex-fake-0.156.1; exit; fi',
  'printf "%s %s %s\n" "$$" "$MULTIAGENTS_SESSION" "$MULTIAGENTS_SLOT" >> "$MOCK_LOG/provider-pids"',
  'export FAKE_CODEX_LOG="$MOCK_LOG/codex-$$.jsonl"',
  'exec bun "$REVIEW_LAB/src/tests/fakes/fake-codex-app-server.ts" "$@"'
]);
mockCommand("claude", [
  'if [ "${1-}" = "--version" ]; then echo claude-fake-2.1.241; exit; fi',
  'printf "%s %s %s\n" "$$" "$MULTIAGENTS_SESSION" "$MULTIAGENTS_SLOT" >> "$MOCK_LOG/provider-pids"',
  'if [ "${MOCK_FAIL_NAME:-}" = "$MULTIAGENTS_NAME" ]; then exit 7; fi',
  'export FAKE_CLAUDE_LOG="$MOCK_LOG/claude-$$.jsonl"',
  'if [ -n "${MOCK_CLAUDE_DELAY-}" ]; then sleep "$MOCK_CLAUDE_DELAY"; fi',
  'exec bun "$REVIEW_LAB/src/tests/fakes/fake-claude.ts" "$@"'
]);
mockCommand("npx", ['case " $* " in *" --version "*) echo gemini-fake-1; exit 0;; esac', 'echo fixture-only >&2','exit 99']);
const env = {
  ...process.env,
  HOME:home, XDG_CONFIG_HOME:join(home,".config"), XDG_CACHE_HOME:join(home,".cache"),
  PATH:bin+":"+process.env.PATH,
  MULTIAGENTS_PORT:String(port), MULTIAGENTS_DB:join(run,"db.sqlite"),
  MULTIAGENTS_CLEANUP_INTERVAL_MS:"120",
  MULTIAGENTS_NO_DASHBOARD:"1",
  MOCK_LOG:run,
};
const awaitUntil = async <T>(proposal: () => Promise<T | false> | T | false, ms = 6000): Promise<T> => {
  const end = performance.now() + ms;
  do {
    const result = await proposal();
    if (result !== false) return result;
    await Bun.sleep(25);
  } while (performance.now() < end);
  throw Error("condition deadline");
};
const post = async (path: string, body: unknown) => {
  const res = await fetch(url+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body),signal:AbortSignal.timeout(2500)});
  const data = await res.json();
  A.equal(res.status,200,path+" "+JSON.stringify(data));
  return data;
};
const slots = (id: string) => post("/slots/list",{session_id:id});
const slot = (id: number) => post("/slots/get",{id});
const session = (id: string) => post("/sessions/get",{id});
const history = (id: string) => post("/message-log",{session_id:id,limit:200});
const pidRows = () => {
  try {return readFileSync(join(run,"provider-pids"),"utf8").trim().split("\n").filter(Boolean).map(line => {const [pid,sid,s] = line.split(" ");return {pid:Number(pid),sid,slot:Number(s)};});}
  catch {return [];}
};
const isRunning = (pid: number) => {
  try {
    const stat = readFileSync("/proc/"+pid+"/stat","utf8");
    return !/^[ZX]/.test(stat.slice(stat.lastIndexOf(")")+2));
  } catch {return false;}
};
const codexLog = (pid: number) => {
  try {return readFileSync(join(run,"codex-"+pid+".jsonl"),"utf8").trim().split("\n").filter(Boolean).map(v=>JSON.parse(v));}
  catch {return [];}
};
const project = (s: string) => join(run,s);
const client = async (tag: string, tuning: Record<string,string> = {}) => {
  const c = await McpStdioClient.spawn(["bun",join(src,"orchestrator/orchestrator-server.ts")],{cwd:run,env:{...env,...tuning},stderrLog:join(run,tag+".log")});
  controllers.push(c);
  return c;
};
const agent = (type:string, name:string, task = "Produce the synthetic fixture") => ({agent_type:type,name,role:"developer",role_description:"Fixture only",initial_task:task});
const create = (c: InstanceType<typeof McpStdioClient>, sid: string, agents: unknown[], plan?: unknown[]) => c.callTool("create_team",{session_name:sid,project_dir:project(sid),agents,...(plan ? {plan} : {})},25000);
const end = (c: InstanceType<typeof McpStdioClient>, sid: string) => c.callTool("end_session",{session_id:sid});
const start = () => {
  const b = Bun.spawn(["bun",join(src,"broker.ts")],{cwd:run,env,stdin:"ignore",stdout:"ignore",stderr:"inherit"});
  children.push(b);
  return b;
};
const killed = async (pid: number) => {
  await awaitUntil(() => !isRunning(pid));
};
const scenario = async (name: string, test: () => Promise<void>) => {
  if (!only(name)) return;
  try { await test(); }
  catch (e) { log(name+" error", String(e)); process.exitCode = 1; }
};
try {
  const broker = start();
  await awaitUntil(async () => {
    try { const r = await fetch(url+"/health",{signal:AbortSignal.timeout(300)});return r.ok && (await r.json()).pid === broker.pid; }
    catch {return false;}
  });


  await scenario("N1-partial-team",async()=>{
    const sid="partial-team";
    const c=await client(sid,{MOCK_FAIL_NAME:"fail-at-launch"});
    const failed=await create(c,sid,[agent("codex","stable"),agent("claude","fail-at-launch")],[{label:"planned action",agent_name:"stable"}]);
    A.equal(failed.isError,true,failed.text);
    const row=await session(sid);
    const members=await slots(sid);
    const before=pidRows().filter(p=>p.sid===sid);
    const live=before.map(p=>[p.pid,p.slot,isRunning(p.pid)]);
    const plan=await post("/plan/get",{session_id:sid});
    const replay=await create(c,sid,[agent("codex","stable")]);
    A.equal(replay.isError,false,replay.text);
    const after=(await post("/sessions/list",{})).map((x:any)=>[x.id,x.status]);
    log("N1",{failed,session:row.status,members:members.map((r:any)=>[r.id,r.status,r.display_name]),live,planExists:Boolean(plan.plan),replay:replay.text.split("\n")[0],after});
    await end(c,sid);
    await end(c,sid+"-2");
  });

  await scenario("N2-claude-first-output",async()=>{
    const sid="fast-claude";
    const c=await client(sid);
    A.equal((await create(c,sid,[agent("claude","fast")])).isError,false);
    const [row]=await slots(sid);
    const [p]=pidRows().filter(r=>r.sid===sid);
    const head=await slot(row.id);
    const initialLog=readFileSync(join(run,"claude-"+p.pid+".jsonl"),"utf8");
    await post("/send-message",{session_id:sid,to_slot_id:row.id,from_id:"orchestrator",text:"second turn positive control"});
    const caught=await awaitUntil(async()=>{const r=await slot(row.id);return r.output_tokens>0&&r;},7500);
    log("N2",{initialInputSent:initialLog.includes("Produce the synthetic fixture"),initialTokens:[head.input_tokens,head.output_tokens],initialTask:head.task_state,nextTokens:[caught.input_tokens,caught.output_tokens],nextTask:caught.task_state});
    await end(c,sid);
    await killed(p.pid);
  });

  await scenario("N3-extension",async()=>{
    const sid="unsupported-type";
    const c=await client(sid);
    const result=await create(c,sid,[agent("custom","custom1")]);
    const entry=await post("/sessions/list",{});
    const list=await c.request("tools/list",{});
    const info=await McpStdioClient.spawn(["bun",join(src,"server.ts"),"--agent-type","custom"],{cwd:run,env,stderrLog:join(run,"custom-adapter.log")});
    controllers.push(info);
    const customTools=await info.request("tools/list",{});
    log("N3",{result,created:entry.some((x:any)=>x.id===sid),controlTools:(list as any).tools.length,customPeerTools:(customTools as any).tools.length});
  });
} finally {
  for (const c of controllers.reverse()) if (c.proc.exitCode === null && c.proc.signalCode === null) { c.proc.kill("SIGTERM"); await c.proc.exited; }
  for (const child of children) if (child.exitCode === null && child.signalCode === null) { child.kill("SIGTERM"); await child.exited; }
}
```

</details>

<details>
<summary>pack-smoke.ts</summary>

<!-- fixture pack-smoke.ts -->
```ts
import { strict as assert } from "node:assert";
import { join } from "node:path";
const lab=process.env.REVIEW_LAB!;
const packed=join(lab,"release-smoke/package");
const { McpStdioClient }=await import(join(lab,"src/tests/helpers/mcp-stdio-client.ts"));
const env={...process.env,MULTIAGENTS_PORT:"17715",MULTIAGENTS_DB:join(lab,"tmp/packed-broker.sqlite"),MULTIAGENTS_NO_DASHBOARD:"1"};
const broker=Bun.spawn(["bun",join(packed,"broker.ts")],{cwd:join(lab,"tmp"),env,stderr:"inherit",stdout:"ignore",stdin:"ignore"});
const clients=[];try {
  let health=null;
  for(let i=0;i<50;i++){
    try {health=await (await fetch("http://127.0.0.1:17715/health")).json();break;}catch {await Bun.sleep(20);}
  }
  assert.equal(health.pid,broker.pid);
  assert.equal(health.version,"0.7.0");
  const version=Bun.spawnSync(["bun",join(packed,"cli.ts"),"--version"],{env});
  assert.equal(version.exitCode,0);
  const c=await McpStdioClient.spawn(["bun",join(packed,"orchestrator/orchestrator-server.ts")],{cwd:join(lab,"tmp"),env,stderrLog:join(lab,"logs/release-orch.log")});
  clients.push(c);
  const p=await McpStdioClient.spawn(["bun",join(packed,"server.ts"),"--agent-type","codex"],{cwd:join(lab,"tmp"),env:{...env,MULTIAGENTS_DRIVER_MODE:"1"},stderrLog:join(lab,"logs/release-peer.log")});
  clients.push(p);
  const ctl=await c.request("tools/list",{});
  const peer=await p.request("tools/list",{});
  const status=await c.callTool("list_sessions");
  assert.equal(ctl.tools.length,17);
  assert.equal(peer.tools.length,19);
  assert.match(status.text,/No sessions found/);
  console.log(JSON.stringify({version:version.stdout.toString().trim(),health,controllerTools:ctl.tools.length,peerTools:peer.tools.length,sessionListing:status.text}));
}finally{
  for(const c of clients){c.proc.kill();await c.proc.exited;}
  broker.kill("SIGTERM");await broker.exited;
}
```

</details>

## 10. Prioritized improvements and acceptance criteria

1. **P0 — Put launch, stop and restart behind one owner and generation model.** Persist desired and observed state, controller lease, last known child identity, and worker generation. Reserve before spawn, then publish readiness under a generation check. Compensate failed initialization and canceled/archived launches. Funnel watchdog, exit callback and manual commands through one fenced transition. Adopt or reconcile stale rows on startup. Acceptance requires O2–O4, N1, S3 and P7 to leave no false-online slot, no residually running canceled worker, no double launch and no archive reopened by a late callback. Retry of the same operation uses the original request identity. [Controller maps](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:45), [tracking](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:106), [manual resume](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1309), [watchdog](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1912).
2. **P0 — Own and join the process tree.** Track spawned processes from the first subprocess handle, including failed handshakes. Use platform-appropriate process group or job ownership. Define cooperative EOF, timed TERM, timed KILL and final reaping with bounded upper limits. Give transport close and signals a common shutdown path that waits for escalation. Preserve the distinction between supervised and externally registered peers. Acceptance requires D1, W4 and P1/P6 to leave no owned descendant live, verified after shutdown as well as explicit end. P5's cooperative release still drains. [Codex spawn](repos/zetbrush__multiagents/orchestrator/codex-driver.ts:210), [Claude teardown](repos/zetbrush__multiagents/orchestrator/claude-driver.ts:266), [session stop](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:80), [shutdown](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1977).
3. **P0 — Separate completion, review and operational recovery.** Use compare-and-set task transitions and version each submission/review round. Bind approvals to a submitted revision and explicit roles. Close plans item by item or via explicit acceptance. Treat a disconnected reviewer as a human intervention condition. Silence should yield a diagnostic, resumable interrupt or failure, with no inference about work completeness. Acceptance requires round-specific approvals, retention of pending or blocked items until explicit completion, and an archive gate that preserves unfinished work when reviewers disconnect. A stale summary cannot overwrite completion. [Approval path](repos/zetbrush__multiagents/broker.ts:1535), [adapter summary and plan updates](repos/zetbrush__multiagents/adapters/base-adapter.ts:1143), [auto plan completion](repos/zetbrush__multiagents/adapters/base-adapter.ts:1393), [quiet handling](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1552), [auto-end](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1763).
4. **P1 — Standardize durable operation and message semantics.** Introduce transactional plan replacement, single cleanup transaction for a dead peer, fenced peer replacement, and atomic expired-lease acquisition. Use stable slot-addressed routing and normalize session ownership at the broker. Add a delivery claim with a lease, bounded batches, an independently retried ack and an application-level deduplication key. Specify provider acceptance separately from confirmed delivery. Apply cancellation to requests and their side-effect lifetimes. Acceptance requires B2/B3/B5/B6, O1, W5 and D2–D5 to preserve reversible state during restarts and fault injection, with durable evidence of any unconfirmed delivery. [Broker SQL](repos/zetbrush__multiagents/broker.ts:418), [registration](repos/zetbrush__multiagents/broker.ts:441), [plan replacement](repos/zetbrush__multiagents/broker.ts:1200), [delivery](repos/zetbrush__multiagents/orchestrator/delivery.ts:45).
5. **P1 — Bound scheduling, queues and retries.** Manage long provider operations independently per slot with bounded concurrency. Index the active inbox and session history, paginate by ID or deterministic timestamp-plus-ID, and transact claims/acks to reduce per-row commit cost. Persist retry attempts and enforce one backoff and circuit-breaker policy across all recovery triggers. Gate agent count and other real budgets at admission. Acceptance requires P3 to keep a healthy slot within its service-deadline envelope while a steer is wedged. R1 avoids full-history empty-poll scaling and oversized batches. S1 and P7 cannot bypass the same restart stop state. [Driver loops](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1602), [watchdog](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:1854), [guardrails](repos/zetbrush__multiagents/orchestrator/guardrails.ts:65), [queries](repos/zetbrush__multiagents/broker.ts:418).
6. **P1 — Decouple config, identity and protocol adapters.** Use explicit per-launch identity, consistent precedence and provider-owned configuration roots. Validate and update config with a real parser and atomic writes. Consolidate adapter capabilities for readiness, send/steer, cancel, resume and close. Specify API error, tool result and provider wire versions in executable schemas. Acceptance requires W1 to preserve unrelated tables in each legacy layout, W2 to preserve the explicit slot binding in a shared project, and both recovery paths to use the documented conversation-resume policy. [Config and launcher](repos/zetbrush__multiagents/orchestrator/launcher.ts:156), [adapter identity](repos/zetbrush__multiagents/adapters/base-adapter.ts:593), [manual relaunch](repos/zetbrush__multiagents/orchestrator/launcher.ts:701), [crash resume](repos/zetbrush__multiagents/orchestrator/recovery.ts:183).
7. **P2 — Make runtime state and regression evidence durable.** Persist session-scoped events with stable IDs and a read cursor. Report desired/observed state and the age of the latest provider activity separately. Key cumulative counters by provider conversation and generation with a transactional offset. Record the confirmed reason for every stop or retry. Add the lifecycle, cancellation, mailbox and resource controls to CI and stage pinned dependency artifacts for offline reruns. Acceptance requires deterministic and recoverable results in S4 and M1–M4, retention of first-turn evidence in N2, and a passing suite with the frozen graph and the new regression cases. [Status event drain](repos/zetbrush__multiagents/orchestrator/orchestrator-server.ts:853), [monitor usage](repos/zetbrush__multiagents/orchestrator/monitor.ts:35), [status timestamps](repos/zetbrush__multiagents/orchestrator/progress.ts:88), [CI](repos/zetbrush__multiagents/.github/workflows/ci.yml:11).
