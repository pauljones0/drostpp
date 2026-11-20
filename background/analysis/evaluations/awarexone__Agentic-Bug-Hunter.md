# Agentic-Bug-Hunter non-UI runtime review

## 1. Snapshot, scope, and elapsed-time evidence

I read the complete 31-line [evaluation protocol](./README.md) and verified the already-present snapshot of `awarexone/Agentic-Bug-Hunter` at `82f4512ec432765297c36e6b3ef7dc3fe5a58be2`. The opening `git rev-parse HEAD` returned that digest, and `git --no-optional-locks status --porcelain=v1 --untracked-files=all` produced no lines. History is shallow with one visible commit, so the post-mortem uses code and bundled history notes for context.

The review covers non-UI lifecycle, local process ownership, interfaces, records, and defensive policy wiring. It uses inert fixtures, fake model clients, the checkout's credential-free tests, and a loopback-only HTTP fixture. Domain routing and tool tactics are background. The runtime-specific claims distinguish source reading, executed component behavior, and unobserved integrations. I used no accounts, credentials, remote services, or external systems.

| UTC on 2026-11-19 | Investigation checkpoint |
| --- | --- |
| 06:53:40 | Read rubric and recorded opening HEAD and status. |
| 06:54:34 | Verified the credential-free, network-isolated execution environment. |
| 06:55:27–06:55:55 | Reproduced evidence snapshot inconsistency and audit rotation ownership failure. |
| 06:58:05–06:58:51 | Checked timeout/status behavior and recovered from induced file write errors. |
| 07:00:58 | Reproduced persistence results on Btrfs and traced import identity. |
| 07:03:39 | Isolated installer permission failures with a writable exact-commit archive. |
| 07:04:48–07:06:48 | Tested interrupted evidence commits, migration, alternate interpreter, and denial-path integration. |
| 07:08:50–07:10:05 | Checked admission-time budget, resource release, retry/count semantics, and process launch ownership. Validated a transaction as a counterfactual to two independent writes. |
| 07:13:48–07:14:59 | Checked four concurrent evidence writers, ran the appendix commands verbatim, and compared unstaged verification with a shared-lock control. |
| 07:16:24–07:17:29 | Examined session restart with a synthetic clock, tested both console shims, and traced permission behavior to the two installed Python implementations. |
| 07:18:59–07:20:52 | Checked operator message consumption and snapshot caps, repeated the version-specific permission control on Btrfs, reran the extended appendix, and distinguished imports from runtime calls with test profiling. |
| 07:21:49–07:22:11 | Compared every cited repository file byte-for-byte against HEAD and checked the proposed sibling-lock ownership with the real audit writer. |
| 07:23:46 | Closed the active review after checking source and index diffs, ignored and untracked status, and HEAD again. |

**Elapsed active review window was 30 minutes 6 seconds**, from `2026-11-19T06:53:40Z` through `2026-11-19T07:23:46Z`. The interval covers source tracing, constructing and running controls, auditing alternative explanations, and checking the report against the checkout. I took no idle waits to reach the threshold. At the 06:54:54 UTC intermediate checkpoint, boot-relative uptime was 345743.33 s. At closure it was 347475.40 s, consistent with the UTC difference over the same portion of the run. Final HEAD was `82f4512ec432765297c36e6b3ef7dc3fe5a58be2`. The final status command and both Git diffs were empty.

## 2. Core architecture and end-to-end control/data flow

- **Entry and ownership.** The package maps two console scripts to `bughunter.__main__`. The conventional CLI dispatches subcommands from its argument parser and has a model-adapter layer in `brain.py`. The built-in agent runner is a synchronous function called by its CLI. It chooses a session directory and constructs mutable memory, a dispatcher with scope and budget state, and a local evidence store. The built-in branch creates a trace handle, hands it to the loop, and returns a result dictionary together with artifact paths. The owner of the process or function call is the owner of this run. [pyproject.toml:35](repos/awarexone__Agentic-Bug-Hunter/pyproject.toml:35), [bughunter/__main__.py:13](repos/awarexone__Agentic-Bug-Hunter/bughunter/__main__.py:13), [bughunter/engine.py:1023](repos/awarexone__Agentic-Bug-Hunter/bughunter/engine.py:1023), [bughunter/agent.py:1918](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1918), [bughunter/agent.py:1987](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1987)
- **Planning and dispatch boundary.** The built-in coordinator runs a bounded outer loop. A step checks its time allowance, builds context from current session state, and asks the model for a response with the declared tool interface. The dispatcher is the application effect boundary. Model responses are distinct from the policy decision, and the runtime records observations and increments progress at dispatch. The optional graph has a message state and an agent/tool loop around the dispatcher. Its compile call supplies no checkpointer. The model-assisted conventional CLI uses the separate, string-returning `LLMClient.chat` interface. [bughunter/agent.py:1548](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1548), [bughunter/agent.py:1575](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1575), [bughunter/agent.py:1622](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1622), [bughunter/agent.py:929](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:929), [bughunter/agent.py:1740](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1740), [bughunter/agent.py:1813](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1813), [bughunter/agent.py:1840](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1840), [bughunter/brain.py:571](repos/awarexone__Agentic-Bug-Hunter/bughunter/brain.py:571)
- **Scheduling and worker lifetime.** The built-in iteration invokes its dispatcher inline. The separate batch coordinator uses a process-local `ThreadPoolExecutor` with a bounded number of worker threads and eagerly submits futures. It aggregates completion results and exceptions in the caller. Ordinary local workers are subprocesses owned by several helper implementations. The reviewed entrypoints offer no durable work queue or cross-process run scheduler. The batch ledger's serialized updates persist records independently of the pool that owns the futures. [bughunter/agent.py:1644](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1644), [bughunter/tools/swarm.py:146](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/swarm.py:146), [bughunter/tools/swarm.py:167](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/swarm.py:167), [bughunter/tools/lead_board.py:166](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/lead_board.py:166), [bughunter/tools/hunt.py:297](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/hunt.py:297), [bughunter/engine.py:232](repos/awarexone__Agentic-Bug-Hunter/bughunter/engine.py:232)
- **State and restart.** The session resolver creates a timestamp-and-random-suffix directory or looks up an existing explicit ID. The snapshot contains rolling notes, observations, recorded candidates and findings, completed step names, and a counter. The snapshot stores bounded slices of record lists. Reopening the neutral-state fixture preserved 200 of 230 entries from each result list and 10 of 15 observations, alongside all 230 completed step labels and the original counter. A later run reloads those fields and constructs new timers, clients, and loop state. The dispatcher writes evidence records and updates the snapshot in separate operations. A successful explicit-ID resume rehydrates local context. In-flight work and thread ownership live in the original process. [bughunter/tools/hunt.py:246](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/hunt.py:246), [bughunter/agent.py:428](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:428), [bughunter/agent.py:450](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:450), [bughunter/agent.py:920](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:920), [bughunter/agent.py:1428](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1428), [bughunter/agent.py:1934](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1934)
- **Events and other surfaces.** `AgentTracer` appends JSONL and flushes each event immediately. It can attach an evidence ID to a result. The evidence store redacts selected content, hashes and appends a structured record, and updates a separate head file. Audit logs and journal records have their own schemas and readers. The MCP surface is a stdio adapter with typed decisions, tool metadata, and response redaction. Its validation-artifact evidence lookup is distinct from the session chain verifier. The repository also ships declarative agent and command definitions that external harnesses interpret. [bughunter/agent.py:1283](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1283), [bughunter/agent.py:1309](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1309), [bughunter/memory/evidence.py:170](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:170), [bughunter/memory/schemas.py:11](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/schemas.py:11), [bughunter/mcp/bughunter-mcp/server.py:66](repos/awarexone__Agentic-Bug-Hunter/bughunter/mcp/bughunter-mcp/server.py:66), [bughunter/mcp/bughunter-mcp/server.py:284](repos/awarexone__Agentic-Bug-Hunter/bughunter/mcp/bughunter-mcp/server.py:284), [bughunter/mcp/bughunter-mcp/server.py:356](repos/awarexone__Agentic-Bug-Hunter/bughunter/mcp/bughunter-mcp/server.py:356), [bughunter/engine.py:172](repos/awarexone__Agentic-Bug-Hunter/bughunter/engine.py:172)

## 3. Why the design works and its governing invariants

The simplest operating case is an interactive, single-owner process. Step boundaries are explicit, the caller can inspect bytes that have already been captured, and durable artifacts remain readable in a fresh process. The filesystem layout gives new sessions independent names. Intent, a policy decision, a tool observation, and a persisted record can be reasoned about separately. That separation is useful even where the implementation leaves partial failure states ambiguous. [bughunter/tools/hunt.py:253](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/hunt.py:253), [bughunter/agent.py:653](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:653), [bughunter/agent.py:677](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:677), [bughunter/agent.py:1641](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1641)

Three invariants have concrete support.

1. **Policy precedes a tested external effect.** The guard returns a block when required scope is absent or rejects the proposed destination. It evaluates scope ahead of other gate criteria. The MCP gate converts denied decisions into structured, redacted responses. Four integration tests used fake effect handlers and verified denial or captured denial without a worker call. This evidence applies to the reviewed entrypoints and fixtures. [bughunter/memory/audit_log.py:319](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/audit_log.py:319), [bughunter/mcp/bughunter-mcp/server.py:66](repos/awarexone__Agentic-Bug-Hunter/bughunter/mcp/bughunter-mcp/server.py:66), [tests/test_agent_dispatcher_scope.py:24](repos/awarexone__Agentic-Bug-Hunter/tests/test_agent_dispatcher_scope.py:24), [tests/test_evidence_provenance.py:211](repos/awarexone__Agentic-Bug-Hunter/tests/test_evidence_provenance.py:211)
2. **A cooperating evidence writer extends one chain tail.** Capture holds an exclusive lock across reading the predecessor, appending the chained digest, and publishing the head. A well-formed committed record can be re-read and verified after reopening. Four concurrent writer processes completed 100 neutral records and the final chain verified with 100 unique observations. The chain is tamper-evident under the documented assumption that the verifier can trust its head anchor. It records what the producer captured and retains the limits of that capture. [bughunter/memory/evidence.py:16](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:16), [bughunter/memory/evidence.py:201](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:201), [bughunter/memory/evidence.py:251](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:251), [tests/test_evidence_provenance.py:19](repos/awarexone__Agentic-Bug-Hunter/tests/test_evidence_provenance.py:19)
3. **The ledger separates lock identity from the published file.** Its sibling lock stays in place while a complete temporary file replaces the readable snapshot. The normal mutation helpers hold the lock over read, change, and publish. Twelve concurrent changes to separate neutral records survived, and a file-size fault before replacement preserved the previous ledger. [bughunter/tools/lead_board.py:166](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/lead_board.py:166), [bughunter/tools/lead_board.py:178](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/lead_board.py:178), [bughunter/tools/lead_board.py:406](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/lead_board.py:406)

## 4. Strengths

- The defensive seams are inspectable with small local tests. Scope matching, method decisions, structured MCP denial, and redaction can be exercised without model inference, remote credentials, or scanner installation. The real loopback redirect fixture complements tests that mock out the HTTP opener. [tests/test_autopilot_guard.py:189](repos/awarexone__Agentic-Bug-Hunter/tests/test_autopilot_guard.py:189), [tests/test_bughunter_mcp.py:29](repos/awarexone__Agentic-Bug-Hunter/tests/test_bughunter_mcp.py:29), [tests/test_safe_http_redirects.py:125](repos/awarexone__Agentic-Bug-Hunter/tests/test_safe_http_redirects.py:125)
- Local artifacts are useful for troubleshooting. The tracer exposes events promptly, chains explicitly link observations, and verification checks both record contents and their ordering. The parser rejects duplicate keys and non-object evidence records. The persistence code sends the snapshot, trace events, and captured content through the shared redactor. Prompt delimiters mark observations as untrusted data. They are presentation cues for a model, with actual authority enforced separately. [bughunter/agent.py:474](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:474), [bughunter/agent.py:571](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:571), [bughunter/agent.py:1288](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1288), [bughunter/memory/evidence.py:74](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:74), [bughunter/memory/evidence.py:224](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:224), [bughunter/tools/prompt_safety.py:12](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/prompt_safety.py:12)
- Several local implementation choices are sound within their boundaries. Explicit model selection rejects a missing choice in the tested selector. The process-group runner bounds `communicate` and kills and waits on timeout. The interactive confirmation boundary refused the non-TTY fixture before process construction. The JSONL audit and pattern files are created owner-only. The journal schema explicitly accepts the previous schema version. [bughunter/brain.py:957](repos/awarexone__Agentic-Bug-Hunter/bughunter/brain.py:957), [bughunter/tools/hunt.py:297](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/hunt.py:297), [bughunter/brain.py:2349](repos/awarexone__Agentic-Bug-Hunter/bughunter/brain.py:2349), [bughunter/memory/audit_log.py:43](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/audit_log.py:43), [bughunter/memory/pattern_db.py:86](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/pattern_db.py:86), [bughunter/memory/schemas.py:11](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/schemas.py:11)

## 5. Weaknesses and evidence status

| Finding | Cause, consequence, and evidence |
| --- | --- |
| **Acknowledged audit append can disappear** | Rotation locks the active file, renames it, and closes its descriptor. Append opens the pathname, then takes its own lock. A paused writer can later write to the former live inode, which may have been unlinked by subsequent retention. It returned normally with link count zero in both the thread and fork controls. The append was absent from all retained files. A single rotation put the same delayed row in a backup, outside `AuditLog.read_all`. [bughunter/memory/rotation.py:39](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/rotation.py:39), [bughunter/memory/rotation.py:66](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/rotation.py:66), [bughunter/memory/audit_log.py:37](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/audit_log.py:37), [bughunter/memory/audit_log.py:90](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/audit_log.py:90) |
| **Evidence, anchor, and export lack one snapshot** | The writer controls its own append critical section. Verification independently reads the log and head without that lock. During an otherwise valid append it returned `head_anchor_mismatch`, and after the writer finished it verified. Abrupt exit between the two writes also left a mismatch after reopen. A strict export that verified one record then read after a second append returned a successful one-record integrity verdict alongside two records. An injected head-write error plus a caller retry produced two copies of the same logical observation. [bughunter/memory/evidence.py:134](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:134), [bughunter/memory/evidence.py:201](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:201), [bughunter/memory/evidence.py:251](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:251), [bughunter/memory/evidence.py:405](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:405) |
| **Resume and configuration can accept lost state** | A real file-size limit interrupted direct writes to previously valid files. The session reader silently recreated default values and the config reader warned and returned defaults. The session loader also assigned several values before encountering a wrong field type, leaving a partial in-memory load. Two independently opened snapshot objects overwrote each other's updates in the last-writer control. There is no common commit covering worker effect, evidence, snapshot, and terminal state. [bughunter/agent.py:450](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:450), [bughunter/agent.py:463](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:463), [bughunter/agent.py:920](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:920), [bughunter/engine.py:103](repos/awarexone__Agentic-Bug-Hunter/bughunter/engine.py:103), [bughunter/engine.py:114](repos/awarexone__Agentic-Bug-Hunter/bughunter/engine.py:114) |
| **Timeout and cancellation contracts differ by owner** | `engine._run_shell` drains stdout to EOF before its timed wait. With an open pipe a neutral 0.25 s child completed successfully despite a 0.055 s timeout. `tools.hunt.run_cmd` applied the timeout while reading. In a separate test, interrupting that runner while its own child was active left the child running in its separate process group. A separate malformed-output fixture left the engine wrapper's child running after decoding failed. The fixtures explicitly cleaned up their children. [bughunter/engine.py:232](repos/awarexone__Agentic-Bug-Hunter/bughunter/engine.py:232), [bughunter/tools/hunt.py:312](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/hunt.py:312) |
| **Terminal status is too coarse for restart or supervision** | The built-in loop returned `success=True` for a zero-iteration cap and for an early deadline exit. Neither produced a terminal trace event in the inert control. Constructor failure also left an opened trace without explicit release. The time guard checks at step entry. The graph branch catches general execution errors and proceeds to the built-in branch with the same loaded state, with no visible reconciliation of prior effects. The graph case is source evidence. [bughunter/agent.py:1548](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1548), [bughunter/agent.py:1662](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1662), [bughunter/agent.py:1740](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1740), [bughunter/agent.py:1960](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1960) |
| **Evidence write work grows with all prior records** | Every append loads the full preceding log to recover the latest digest and count while holding the writer lock. At 250 records the fixture scanned 20,831,355 logical file bytes cumulatively. At 2,000 it scanned 1,339,614,605 bytes for a final file of 1,340,890 bytes. The instrument counts file lengths before reads. It measures logical work within the implementation. [bughunter/memory/evidence.py:107](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:107), [bughunter/memory/evidence.py:207](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:207) |

There are related lower-level consistency issues. A prefix-only append can leave the next successful audit row joined to an unreadable line. Pattern deduplication behaves differently after reopening a rotated live file, even while the earlier row remains in a backup. A maintenance migration can rewrite past a concurrent append after copying its backup. Parseable wrong shapes receive inconsistent treatment across readers. The security impact of file permissions depends on ancestor-directory access. Under umask `022` the new trace, session snapshot, and journal had mode `0644` inside a private fixture root. The tested audit and journal writers retained a synthetic marker that the snapshot, evidence, and tracer removed. [bughunter/memory/audit_log.py:47](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/audit_log.py:47), [bughunter/memory/audit_log.py:90](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/audit_log.py:90), [bughunter/memory/pattern_db.py:37](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/pattern_db.py:37), [bughunter/memory/pattern_db.py:48](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/pattern_db.py:48), [bughunter/tools/memory_migrate.py:42](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/memory_migrate.py:42), [bughunter/memory/hunt_journal.py:32](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/hunt_journal.py:32), [bughunter/agent.py:1283](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1283)

## 6. Core-code quality

- **Decomposition and extension.** The console shims, decision types, redactor, validators, ledger, and evidence parser have narrow interfaces. The primary modules are considerably broader. The 2,143-line `agent.py` contains orchestration, schema declarations, worker adaptation, progress, and storage. The 2,939-line `brain.py` contains provider selection, adapters, and application-level behavior. The graph wrapper derives its tool list from the registry but constructs a generic keyword-argument callable. The MCP registry and policy metadata live on a separate surface. Adding an entry therefore requires checking its schema, authority, and event contract at each exercised interface. [bughunter/agent.py:421](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:421), [bughunter/agent.py:428](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:428), [bughunter/agent.py:1813](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1813), [bughunter/brain.py:169](repos/awarexone__Agentic-Bug-Hunter/bughunter/brain.py:169), [bughunter/mcp/bughunter-mcp/policy/tool_meta.py:1](repos/awarexone__Agentic-Bug-Hunter/bughunter/mcp/bughunter-mcp/policy/tool_meta.py:1)
- **Types and errors.** Policy decisions use enums and a data class. Core run outputs and persisted snapshots use dictionaries and conventions. Journal validation checks version and allowed fields, while several readers trust the shape returned by the JSON parser. The neutral provider tests showed that a successful empty completion and a timeout have the same string return value. The HTTP-path fixture saw one call for each of 200, 429, and 503. That establishes wrapper behavior for these local responses. SDK retry behavior remains unmeasured. [bughunter/mcp/bughunter-mcp/policy/decisions.py:10](repos/awarexone__Agentic-Bug-Hunter/bughunter/mcp/bughunter-mcp/policy/decisions.py:10), [bughunter/memory/schemas.py:254](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/schemas.py:254), [bughunter/memory/hunt_journal.py:46](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/hunt_journal.py:46), [bughunter/brain.py:571](repos/awarexone__Agentic-Bug-Hunter/bughunter/brain.py:571), [bughunter/brain.py:697](repos/awarexone__Agentic-Bug-Hunter/bughunter/brain.py:697)
- **Concurrency and configuration.** The worker ledger has explicit ownership. The session files and scope handoff depend on a single effective owner. The agent temporarily sets a module-global checker and restores it in `finally`. A run-local argument therefore crosses a process-wide boundary. Separately, the engine materializes model settings into process environment, which caused a second provider fixture in the same process to pick up the earlier model selection. The normal shims work by bootstrapping flat imports. Direct package import without that bootstrap failed, and loading the same source through flat and package names yielded separate module objects. The conventional CLI and MCP artifact adapters also use different root settings. [bughunter/agent.py:83](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:83), [bughunter/agent.py:1949](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1949), [bughunter/agent.py:2012](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:2012), [bughunter/__main__.py:13](repos/awarexone__Agentic-Bug-Hunter/bughunter/__main__.py:13), [bughunter/engine.py:65](repos/awarexone__Agentic-Bug-Hunter/bughunter/engine.py:65), [bughunter/engine.py:196](repos/awarexone__Agentic-Bug-Hunter/bughunter/engine.py:196), [bughunter/mcp/bughunter-mcp/adapters.py:11](repos/awarexone__Agentic-Bug-Hunter/bughunter/mcp/bughunter-mcp/adapters.py:11), [bughunter/mcp/bughunter-mcp/adapters.py:311](repos/awarexone__Agentic-Bug-Hunter/bughunter/mcp/bughunter-mcp/adapters.py:311)
- **Observability and maintainability.** The three useful observations are progress from the trace, captured provenance from the evidence log, and resumable context from the snapshot. They have different schemas and publication points. Immediate flush provides visibility to a reader. The log/anchor and snapshot writers lack an explicit durable commit protocol. A status accessor for the circuit breaker also advances cooldown state, so the first read after a synthetic expiry returned the old failure count alongside the updated status. The rate limiter has component tests, but a whole-tree search found only initialization of the guard's limiter, so the tested guard decisions establish no enforced pacing contract. [bughunter/agent.py:1288](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1288), [bughunter/memory/evidence.py:134](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:134), [bughunter/memory/audit_log.py:188](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/audit_log.py:188), [bughunter/memory/audit_log.py:200](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/audit_log.py:200), [bughunter/memory/audit_log.py:279](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/audit_log.py:279)
- **Tests.** The suite has useful regression tests for denial, permissions, malformed evidence, legacy records, and rotation. The concurrent rotation test intentionally retains all its generations and counts after all writers join. Its pass is compatible with misplaced writes and does not exercise an FD that remains open across deletion. A call-profiled 56-test subset executed the session locator, capture, verification, and config-save paths, and recorded zero calls to `ReActAgent.step`, `ReActAgent.run`, `run_agent_hunt`, `_run_shell`, and `run_cmd`. That result applies to this subset and parent process. An initial source-line tracer counted a few lines within multiline function signatures at import time. Filtering actual function-call events removed that artifact. This is why the worker and run-loop cases use direct local controls. [tests/test_rotation.py:211](repos/awarexone__Agentic-Bug-Hunter/tests/test_rotation.py:211), [tests/test_rotation.py:236](repos/awarexone__Agentic-Bug-Hunter/tests/test_rotation.py:236), [tests/test_rotation.py:280](repos/awarexone__Agentic-Bug-Hunter/tests/test_rotation.py:280), [.github/workflows/tests.yml:16](repos/awarexone__Agentic-Bug-Hunter/.github/workflows/tests.yml:16)

## 7. Executed tests, experiments, and limitations

Primary interpreter Python 3.12.16, pytest 9.0.3, requests 2.33.1. Tests ran as UID 1000, with an empty execution environment populated with the few variables in the appendix, an isolated home and data root, and a private network namespace containing only loopback. Source was mounted read-only. Installer tests that deliberately change permission bits ran on a writable tar export of the exact HEAD into namespace-local temporary storage. Storage controls ran on tmpfs by default. The rotation and evidence publication controls also ran on Btrfs and under system Python 3.14.8.

| Existing tests and checks | Observed result |
| --- | --- |
| Audit, rotation, schemas, maintenance, permissions, redaction, pattern store | 134 passed |
| Model selection, session directories, journal research schema, prompt delimiters, evidence store | 40 passed, 2 deselected |
| Scope, methods, guard, TLS defaults, and mocked redirect boundary | 82 passed |
| MCP policy/adapter, plugin metadata, harness metadata, Python and shell normalization | 54 passed |
| HTTP opener against the isolated loopback fixture | 4 passed |
| Installer and selected inert provider adapter tests, writable exact-HEAD export | 26 passed, 2 deselected |
| Three dispatcher denial tests and one captured-denial test | 4 passed |
| Dispatcher budget arithmetic and admission denial | 4 passed |
| Storage test subset under Python 3.14.8, repeated rather than additional | 129 passed, 2 deselected |
| Syntax-only source checks | 89 Python source files parsed and 19 Bash files passed `bash -n` |

The primary groups contain 348 distinct passing tests. I reran all listed groups and all five runnable Python blocks directly from the appendix and reproduced the expected results. The unlocked evidence race count varied on rerun, as expected. Local controls additionally exercised inode lifetime, kernel-backed partial writes, read/append interleavings, abrupt process exit, consistent read views, ledger locking, configuration propagation, permissions, and bounded child lifetime. Their outputs and the important disambiguating cases are in section 8. The neutral transaction comparator had a one-event/one-head view after a child exited before commit, then a two-event/two-head view after a complete transaction. It is a test of an alternative persistence primitive in this environment, with no changes to the project.

The inspected environments lacked the Ollama, LangGraph, and MCP SDK packages. I exercised inspectable boundary behavior with local stubs and read the graph and stdio adapter source. The plain-text adapter's stdlib Ollama fallback decoded a synthetic model listing and both single and streaming replies. The built-in agent's native client remained unavailable. The MCP diagnostic exited 1 with `No module named 'mcp.server'` and confirmed that its tracked server file, policy, ledger, and audit imports were present. Stdio protocol interoperability, actual SDK retry and cancellation, live model reliability, hosted quotas, multi-run policy behavior, and domain-related tools remain unmeasured. The distribution metadata requires requests >=2.32.3 and MCP >=1.28. The CI requirements specify requests >=2.34.2 and MCP >=2.2.0. The preinstalled requests 2.33.1 satisfies the package floor and is below the CI floor. Results establish the checked paths on this host, plus the stated comparisons. Forced process exit and artificial file-size limits are distinct from electrical power loss and real filesystem exhaustion. [pyproject.toml:22](repos/awarexone__Agentic-Bug-Hunter/pyproject.toml:22), [requirements.txt:1](repos/awarexone__Agentic-Bug-Hunter/requirements.txt:1), [bughunter/mcp/bughunter-mcp/cli.py:32](repos/awarexone__Agentic-Bug-Hunter/bughunter/mcp/bughunter-mcp/cli.py:32), [bughunter/agent.py:55](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:55)

## 8. Measurement audit

| Result under review | Controls and ruling |
| --- | --- |
| **Audit rotation hides or loses an acknowledged row** | The no-rotation control kept the expected row on the active inode. With one rotation and spare generations, the delayed write remained in the backup, proving the live-only view and ruling out a JSON counting error. With two rotations and one retained backup, the inode had zero links before the delayed writer made its real write. After it returned, no subsequent writer ran, and a scan of live plus every retained file found zero records from that writer. The fork control had the same result with child exit 0 and three retained rows. The source locks the descriptor after opening, which explains the result without assuming weak `flock` behavior or a timing race in the fixture. Replicated on Btrfs and with Python 3.14.8. The original stress test's `keep=20` deliberately avoids retirement, so it does not invalidate the result. [tests/test_rotation.py:236](repos/awarexone__Agentic-Bug-Hunter/tests/test_rotation.py:236), [bughunter/memory/rotation.py:39](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/rotation.py:39) |
| **Torn audit row affects the following successful append** | The existing disk-full fixture returns zero bytes and checks error propagation. The first isolated control committed a 12-byte prefix before returning a short write. A forked control with kernel `RLIMIT_FSIZE` independently left exactly 12 bytes. The next real append returned, but the reader warned and retained only the baseline row. That distinguishes a framing problem from lost process output, JSON fixture shape, or backing-volume quota. [tests/test_rotation.py:283](repos/awarexone__Agentic-Bug-Hunter/tests/test_rotation.py:283), [bughunter/memory/audit_log.py:47](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/audit_log.py:47) |
| **Evidence mismatch, retry duplication, export divergence** | A barrier paused a healthy writer after its complete log append and before the head write. The same two records verified immediately after release. An uninstrumented run with three writers found 38 transient mismatches in 210 reads on tmpfs, and 53 in 210 on Btrfs. With a shared read lock on the stable evidence file, a separate run gave 210 clean reads on each filesystem. All four trials finished with a valid 211-record chain. A separate kernel-limited write to the head alone returned capture success with a 12-byte head. Verification then returned `head_anchor_unreadable`. Separately, explicit fault injection produced errno 5 and two records, and an abrupt exit at that boundary produced two records on reopen with the old head. A retry was a third persisted valid record with the same logical body. A single intervening healthy append between verification and enumeration yielded a strict export with integrity count 1 and two records. No digest manipulation, credentials, or corrupted fixture were involved. Stable export before and after gave matching counts. [bughunter/memory/evidence.py:201](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:201), [bughunter/memory/evidence.py:405](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:405), [bughunter/memory/evidence.py:466](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:466) |
| **Evidence read work** | The timing function measured separate uninstrumented repetitions. At 250 and 2,000 records the observed medians were 0.034 s and 1.001 s on tmpfs. For the work count, a separate hook recorded file length at each real read. Doubling the fixture count progressed through 20.8, 83.5, 334.6, and 1,339.6 million cumulative logical bytes. The per-append full-file read under the lock accounts for quadratic cumulative work regardless of cache timing. The timings characterize synthetic tmpfs payloads on this host. [bughunter/memory/evidence.py:107](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:107), [bughunter/memory/evidence.py:201](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:201) |
| **Lost snapshot/config, malformed record behavior** | Normal writes reopened with the expected values first. A child then capped file size at 64 bytes and got errno 27 for both classes while the volume had ample free space. A subsequent neutral ledger-file control with the same limit kept its old published state. Valid JSON with a null list field reproduced a partial session load without an I/O failure. For evidence heads, malformed syntax returned `head_anchor_unreadable` but valid non-object heads raised `AttributeError`. Restoring the original head verified again. Non-object JSON in the audit file or pattern index raised during interpretation while the journal returned the value as a list. Invalid UTF-8 escaped evidence verification as `UnicodeDecodeError`. A local unreadable-directory control produced errno 13 from explicit `stat` under both interpreters. Verification raised `PermissionError` in 3.12 and returned clean empty state in 3.14. The local `pathlib.Path.is_file` implementation in 3.14 delegates to `genericpath.isfile`, which maps the stat error to false. Normal permissions restored a valid one-record chain in both. The 3.14 behavior also repeated on Btrfs. The config reader warned for malformed JSON and accepted valid non-object JSON as an unvalidated list or null. [bughunter/agent.py:450](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:450), [bughunter/memory/evidence.py:289](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:289), [bughunter/memory/pattern_db.py:45](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/pattern_db.py:45) |
| **Retention changes reopened deduplication, migration can overwrite a row** | Save/reopen works with a single live file, as tested upstream. Lowering the cap to rotate one row into a retained backup makes the original instance reject its existing key while a reopened instance accepts it. Both read the same directory. In the migration control a dry run detected one upgrade and preserved the bytes. With a barrier after the backup write, a valid concurrent append was readable before the rewrite and absent from both files afterward. This locates the race in maintenance publication, independent of wrong schema fixtures or normal retention. [tests/test_pattern_db.py:190](repos/awarexone__Agentic-Bug-Hunter/tests/test_pattern_db.py:190), [bughunter/memory/pattern_db.py:48](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/pattern_db.py:48), [bughunter/tools/memory_migrate.py:42](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/memory_migrate.py:42) |
| **Permissions and redaction differ by sink** | Scope for this result is fresh files under umask `022`, with the sandbox and fixture directories writable. The mode control found audit `0700/0600`, patterns `0755/0600`, and standalone journal, trace, and snapshot `0755/0644` for parent/file. The recognized placeholder was present in audit and journal and removed from the other tested sinks. The first mode attempt omitted two required fixture arguments and failed before making a measurement. It was rerun with a valid journal entry. A private ancestor directory can protect a mode-0644 file. The result concerns default creation modes and redaction code paths, with no inference about actual unauthorized reads. [bughunter/memory/schemas.py:357](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/schemas.py:357), [bughunter/memory/hunt_journal.py:32](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/hunt_journal.py:32), [docs/phase3-evidence-provenance.md:145](repos/awarexone__Agentic-Bug-Hunter/docs/phase3-evidence-provenance.md:145) |
| **Timeout and interruption** | Both runners completed a neutral immediate child. For the delayed worker, `engine._run_shell` returned success at 0.256 s in three trials, and `run_cmd` returned timeout at 0.056–0.057 s. The first probe used a substring that also matched the diagnostic's argv, so the marker was tightened to an exact stdout line. Closing the child's two output descriptors early made the engine wrapper return timeout at 0.080 s with a 0.075 s requested limit, locating the wait after EOF. A FIFO handoff verified actual child startup and process-group ownership in the separate interrupt control. The timeout path reaped its worker, and a separate same-group fixture confirmed that its child and grandchild were both gone. Parent-only SIGINT left a live, sleeping worker, which the fixture killed inside the PID namespace. This establishes behavior of the two tested helpers. [bughunter/engine.py:245](repos/awarexone__Agentic-Bug-Hunter/bughunter/engine.py:245), [bughunter/tools/hunt.py:312](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/hunt.py:312) |
| **Terminal events, acquisition cleanup, and retries** | Constructorless controls used no model or dispatcher for the early budget and iteration branches. The trace was measured after closing it. With a fake dispatcher and model constructor, the normal run closed its trace and the constructor-failure path failed to explicitly close it. This concerns deterministic ownership, with no claim that garbage collection never closes the handle. A zero-tool mock client was called three times in three iterations for either empty replies or exceptions, while reported steps were three and zero respectively. The response adapter logged a synthetic timeout and returned the same empty string as a successful empty response. Offline 200, 429, and 503 response stubs each recorded one transport call. No measured provider quota or SDK behavior is implied. [bughunter/agent.py:1589](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1589), [bughunter/agent.py:1696](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1696), [bughunter/agent.py:1987](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1987), [bughunter/brain.py:596](repos/awarexone__Agentic-Bug-Hunter/bughunter/brain.py:596) |
| **Config roots, import identity, and diagnostic counts** | Separate fake provider settings first resolved correctly in isolation. A second sequential constructor inherited the first configured model, with the change traced to the environment write. The root fixture used the same validation object in each of the two possible directory anchors and confirmed which reader sees it. The direct-package import failed only before console bootstrapping. After bootstrap, both loaded paths resolved to the same files and different module identities. Under a synthetic monotonic clock the breaker reported failure/tripped pairs of `(2, true)`, `(2, false)`, then `(1, false)` across cooldown. No real clock changes or unrelated account state were involved. [bughunter/engine.py:196](repos/awarexone__Agentic-Bug-Hunter/bughunter/engine.py:196), [bughunter/__main__.py:13](repos/awarexone__Agentic-Bug-Hunter/bughunter/__main__.py:13), [bughunter/mcp/bughunter-mcp/adapters.py:311](repos/awarexone__Agentic-Bug-Hunter/bughunter/mcp/bughunter-mcp/adapters.py:311), [bughunter/memory/audit_log.py:188](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/audit_log.py:188) |
| **Session selection and timestamp domains** | An existing explicit ID and a lookup-only latest request found the saved fixture with step count 17. A creation request with the same latest label produced a fresh directory with step count zero. The top-level caller passes the creation flag, which limits the older documentation's claim about resuming the latest run. A synthetic backwards clock selected the lexically higher prior ID, as required by the helper's ordering rule. Under a separate process-local timezone, trace timestamps were naive and evidence and journal timestamps were UTC. Tests made no system clock change. In the operator mailbox fixture, an uninterrupted read consumed its one message. With a barrier between reading the first message and clearing the file, a second writer published another message. The consumer returned the first and cleared the second, confirming that this control is a best-effort single-slot file. [bughunter/agent.py:1918](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1918), [bughunter/tools/hunt.py:246](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/hunt.py:246), [docs/phase1-engine-validation.md:40](repos/awarexone__Agentic-Bug-Hunter/docs/phase1-engine-validation.md:40), [bughunter/agent.py:1288](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1288), [bughunter/agent.py:1535](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1535), [bughunter/memory/evidence.py:60](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:60) |
| **Environment and fixture failures** | Bare `unshare -n` got EPERM. User-namespace unshare and Bubblewrap succeeded. `ip -br link` and `/proc/net/route` confirmed loopback only and no route from the namespace to an external host. The first 3.14 pytest run lacked Pygments, and adding the already-present pure-Python runtime dependency path produced 129 passes. The individual permission control still revealed a standard-library API difference absent from that test sample. The four standalone installer tests failed on the read-only checkout, including two downstream missing-link assertions. A writable exact-HEAD archive passed the whole group. The tracked executable was already mode `100755`. The unconditional `chmod` on the input file caused the failures, so they establish a writable-source dependency for this installer. The Btrfs rerun used a private writable bind and empty-directory cleanup after an earlier command with a recursive cleanup was rejected before it could launch. The MCP SDK import failure was independently confirmed by module discovery. The bundled `mcp` namespace had no `mcp.server` submodule. [install.sh:296](repos/awarexone__Agentic-Bug-Hunter/install.sh:296), [bughunter/mcp/bughunter-mcp/cli.py:39](repos/awarexone__Agentic-Bug-Hunter/bughunter/mcp/bughunter-mcp/cli.py:39) |

## 9. Post-mortem and highest-leverage improvements

The commit shows an incremental design organized around a command-line process and ordinary local files. That choice makes the toolkit easy to embed in host harnesses and makes individual runs inspectable. The change log describes adding rotation before each append and then eliminating a full read on every pattern insert. Later evidence design notes describe a second file that detects truncation and a human-readable trace for supervision. Each step solves a specific operational need. The resulting contracts overlap without a common owner for process lifetime or one transaction boundary for local state. This is an inference from the source and bundled notes. The available Git history cannot establish when each current transition was introduced. [CHANGELOG.md:74](repos/awarexone__Agentic-Bug-Hunter/CHANGELOG.md:74), [CHANGELOG.md:87](repos/awarexone__Agentic-Bug-Hunter/CHANGELOG.md:87), [docs/phase1-engine-validation.md:3](repos/awarexone__Agentic-Bug-Hunter/docs/phase1-engine-validation.md:3), [docs/phase3-evidence-provenance.md:100](repos/awarexone__Agentic-Bug-Hunter/docs/phase3-evidence-provenance.md:100)

The central persistence mistake is treating locks around adjacent operations as a lock around their combined lifetime. A descriptor still refers to its inode after rename and unlink. In a separate part of the code, an exclusive writer lock keeps records ordered but a reader can still observe half of a two-file publication. Ordinary snapshot truncation adds a third meaning of successful file ownership. When a worker is interrupted or evidence publication fails, an operator may see some progress yet have no dependable answer about whether a run is complete or safe to continue.

1. **P0 — Make termination and authority auditable.** Give each run a single owner for stop/deadline and allow it to clean up its process group in every exit path. Put timing around both pipe consumption and child lifetime. Record a typed terminal reason, including unknown effects, and preserve the stop disposition before any human-approved restart. Keep operator authority outside the model and scope immutable in the executor. Regression cases should include an open stdout pipe, interrupted parent, acquisition failure, and a stopped run that recorded no steps.
2. **P0 — Make safety and provenance records survive concurrent ownership changes.** Use a stable lock over opening, appending, retaining, and maintenance for the audit files, or move shared state behind a transactional store. The existing ledger shows the sibling-lock pattern. A separate scratch control locked a sibling across real audit appends. A competing descriptor could not obtain ownership during the first write, and the live and backup files held the expected rows after rotation. Evidence verification and export should consume the same fixed view. Define whether publication is atomic across log and head and what repair is safe after an interrupted write. The SQLite control shows rollback of the basic two-write case. Add deterministic interleaving tests at rename, unlink, and head publication.
3. **P1 — Validate and publish local state as a complete unit.** Validate before assigning fields, report corrupt, unreadable, and incompatible state explicitly, and preserve the previous snapshot on a failed write. Use one timezone-aware format for persisted event timestamps. Give every sink an explicit redaction and permission policy. Make migration either exclusive with regular writers or clearly reject an open writer. Document which retained generations are queryable and whether deduplication survives rotation.
4. **P1 — Align the testable interfaces.** Pass configuration and artifact roots as run-local values with one package import identity. Represent provider failure and incomplete output explicitly. Keep provider/transports injectable so blocked effects and refusal are observable without dependencies. Treat agreement on script aliases, schema/version bounds, and typed outcomes as testable contracts across entrypoints.
5. **P2 — Reduce storage work and shrink the maintenance surface.** Once commit and corruption behavior are specified, avoid rescanning the entire log under the writer lock for each small append. Keep explicit verification available against a fixed snapshot. Move acquisition, event serialization, and storage out of the model/coordinator modules where a narrow boundary can be tested directly.

## 10. Evidence appendix

**Checkout and execution wrapper**

Run the commands from the repository directory. The wrapper uses the review host's already-present Python installation and pytest path. The package and test directories are read-only inside the namespace.

```bash
git rev-parse HEAD
git --no-optional-locks status --porcelain=v1 --untracked-files=all
git rev-parse --is-shallow-repository
git rev-list --count --all
date -u +'%Y-%m-%dT%H:%M:%SZ'

review_python="$(python -B -c 'import sys; print(sys.prefix)')"
review_pytest="$(python -B -c 'from pathlib import Path; import pytest; print(Path(pytest.__file__).parent.parent)')"
review_box() {
  bwrap --unshare-all --die-with-parent --clearenv --ro-bind /usr /usr \
    --symlink usr/bin /bin --symlink usr/lib /lib --symlink usr/lib /lib64 \
    --ro-bind "$review_python" /runtime --ro-bind "$review_pytest" /runtime-user \
    --ro-bind "$PWD" /review --proc /proc --dev /dev --tmpfs /tmp \
    --dir /tmp/home --dir /tmp/data --chdir /review \
    --setenv HOME /tmp/home --setenv BUGHUNTER_HOME /tmp/data \
    --setenv PATH /runtime/bin:/usr/bin --setenv PYTHONPATH /review/bughunter:/runtime-user \
    --setenv PYTEST_DISABLE_PLUGIN_AUTOLOAD 1 --setenv PYTHONDONTWRITEBYTECODE 1 \
    --setenv LC_ALL C.UTF-8 -- "$@"
}

review_box /usr/bin/ip -br link
review_box /usr/bin/cat /proc/net/route
review_box /runtime/bin/python -B -m bughunter mcp doctor
```

**Exact pytest inputs**

```bash
review_pytests() {
  review_box /runtime/bin/python -B -m pytest -q -p no:cacheprovider -ra "$@"
}

review_pytests tests/test_audit_log.py tests/test_rotation.py tests/test_schemas.py \
  tests/test_schemas_session_id.py tests/test_memory_gc.py tests/test_memory_file_permissions.py \
  tests/test_redaction.py tests/test_cookie_redaction.py tests/test_config_file_permissions.py \
  tests/test_pattern_db.py

review_pytests tests/test_model_selection.py tests/test_hunt_session_dirs.py \
  tests/test_research_learning.py tests/test_prompt_injection_delimiting.py::TestDelimitUntrusted \
  tests/test_prompt_injection_delimiting.py::TestRecentObservationsDelimited \
  tests/test_evidence_provenance.py -k 'not test_dispatch'

review_pytests tests/test_autopilot_guard.py tests/test_safe_method_policy.py \
  tests/test_scope_checker.py tests/test_tls_verification_default.py \
  tests/test_safe_http_redirects.py::TestIsBlockedRedirectTarget \
  tests/test_safe_http_redirects.py::TestSafeUrlopenRejectsRedirectToBlockedHost

review_pytests tests/test_bughunter_mcp.py tests/test_plugin_manifest.py \
  tests/test_opencode_agent_frontmatter.py tests/test_target_normalize.py

review_pytests tests/test_safe_http_redirects.py::TestSafeUrlopenRealServerRedirects

set -o pipefail
git archive --format=tar HEAD | review_box /usr/bin/bash -c '
  mkdir -p /tmp/export
  tar -xf - -C /tmp/export
  cd /tmp/export
  export PYTHONPATH=/tmp/export/bughunter:/runtime-user
  /runtime/bin/python -B -m pytest -q -p no:cacheprovider -ra \
    tests/test_install_standalone.py tests/test_install_layout.py tests/test_brain_litellm.py \
    -k "not test_chat_forwards_proxy_creds_when_set and not test_auto_detect_only_picks_litellm_with_key"
'

review_pytests \
  tests/test_agent_dispatcher_scope.py::TestNoScopeConfigured::test_network_tool_blocked_with_no_scope_checker \
  tests/test_agent_dispatcher_scope.py::TestScopeConfigured::test_out_of_scope_domain_blocked \
  tests/test_agent_dispatcher_scope.py::TestScopeConfigured::test_lookalike_domain_blocked \
  tests/test_evidence_provenance.py::test_dispatch_block_captures_scope_and_does_not_run

review_pytests tests/test_agent_time_budget_gate.py::TestTimeRemainingFraction \
  tests/test_agent_time_budget_gate.py::TestTimeBudgetGateBlocksNetworkTools::test_network_tool_blocked_when_budget_nearly_exhausted

review_box /usr/bin/env \
  PYTHONPATH=/review/bughunter:/runtime-user:/runtime/lib/python3.12/site-packages \
  /usr/bin/python -B -m pytest -q -p no:cacheprovider -ra tests/test_rotation.py \
  tests/test_schemas.py tests/test_schemas_session_id.py tests/test_audit_log.py \
  tests/test_redaction.py tests/test_pattern_db.py tests/test_hunt_session_dirs.py \
  tests/test_evidence_provenance.py -k 'not test_dispatch'
```

**Small local controls**

Use `review_box /runtime/bin/python -B -` with the Python inputs below on stdin. Fixture URLs are strings used in local records. The controls do not open connections to them.

Audit rotation. The thread hook pauses one writer before its real lock, after opening the file. All appends and renames go through production code.

```python
import fcntl
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, current_thread
from unittest.mock import patch
from memory.audit_log import AuditLog
from memory.rotation import list_backups

def run_case(root, keep, other_count):
    path = root / 'audit.jsonl'
    sink = AuditLog(path, max_bytes=300, keep_backups=keep)
    def append(who, index):
        return sink.log_request(url=f'https://example.invalid/{who}/{index}', method='GET',
                                scope_check='pass', session_id=who,
                                error='synthetic fixture data held at a fixed size')
    append('seed', 0)
    baseline = path.stat().st_size
    assert baseline < 300 < 2 * baseline
    staged, release = Event(), Event()
    real_flock = fcntl.flock
    descriptors = {}
    def staged_flock(fd, operation):
        if operation == fcntl.LOCK_EX and current_thread().name.startswith('review'):
            descriptors['opened_inode'] = os.fstat(fd).st_ino
            staged.set()
            assert release.wait(3)
            descriptors['links_at_write'] = os.fstat(fd).st_nlink
        return real_flock(fd, operation)
    with patch.object(fcntl, 'flock', side_effect=staged_flock):
        with ThreadPoolExecutor(1, thread_name_prefix='review') as executor:
            future = executor.submit(append, 'delayed', 0)
            try:
                assert staged.wait(3)
                for i in range(other_count):
                    append('regular', i)
                descriptors['live_inode'] = path.stat().st_ino
            finally:
                release.set()
            assert future.result(timeout=3) is None
    live = [row['session_id'] for row in sink.read_all()]
    backups = [[json.loads(row)['session_id'] for row in bp.read_text().splitlines()]
               for bp in list_backups(path, keep=keep)]
    print('keep', keep, 'other', other_count, 'seed_bytes', baseline,
          'same_inode', descriptors['opened_inode'] == descriptors['live_inode'],
          'links_at_write', descriptors['links_at_write'], 'live', live, 'backups', backups)
    return live, backups, descriptors['links_at_write']

with TemporaryDirectory() as directory:
    base = Path(directory)
    live, backups, links = run_case(base / 'same', 4, 0)
    assert live == ['seed', 'delayed'] and not backups and links == 1
    live, backups, links = run_case(base / 'rename', 4, 2)
    assert live == ['regular'] and 'delayed' in backups[0] and links == 1
    live, backups, links = run_case(base / 'unlink', 1, 4)
    assert 'delayed' not in live + backups[0] and links == 0
```

The three cases recorded link counts `1`, `1`, and `0` in order. The delayed row was live, present in a backup, and absent, respectively. The cross-process control used `os.fork` and two pipes for the same pre-lock barrier and observed child exit 0 and no retained delayed row. For the filesystem comparison, change `--tmpfs /tmp` in the wrapper to `--bind "$review_scratch" /tmp` after creating a private temporary directory on Btrfs and checking it with `stat -f -c '%T' "$review_scratch"`. Experiments used temporary subdirectories that each test deleted.

Evidence publication. The fixture pauses before updating the real head, then checks an injected I/O failure and malformed head handling.

```python
import errno
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch
from memory.evidence import EvidenceStore

def errors(verdict):
    return [entry['error'] for entry in verdict['errors']]

with TemporaryDirectory() as directory:
    base = Path(directory)
    store = EvidenceStore(base / 'interleave')
    store.capture(kind='control', observation='first')
    appended = Event()
    release = Event()
    original = store._write_head
    def stage_head(digest, count):
        appended.set()
        assert release.wait(timeout=3)
        original(digest, count)
    with patch.object(store, '_write_head', side_effect=stage_head):
        with ThreadPoolExecutor(max_workers=1) as pool:
            writer = pool.submit(store.capture, kind='control', observation='second')
            try:
                assert appended.wait(timeout=3)
                during = EvidenceStore(store.session_dir).verify_chain()
                print('concurrent snapshot:', during['count'], errors(during))
                assert during['count'] == 2 and errors(during) == ['head_anchor_mismatch']
            finally:
                release.set()
            writer.result(timeout=3)
    after = store.verify_chain()
    print('writer released:', after['count'], after['ok'])
    assert after['count'] == 2 and after['ok']

    store = EvidenceStore(base / 'write-failure')
    store.capture(kind='control', observation='baseline')
    with patch.object(store, '_write_head', side_effect=OSError(errno.EIO, 'injected I/O fault')):
        try:
            store.capture(kind='control', observation='same logical record')
        except OSError as exc:
            print('anchor write fault:', exc.errno, 'persisted rows', len(store.read_all()),
                  'errors', errors(store.verify_chain()))
            assert exc.errno == errno.EIO and len(store.read_all()) == 2
            assert errors(store.verify_chain()) == ['head_anchor_mismatch']
        else:
            raise AssertionError('expected I/O error')
    store = EvidenceStore(store.session_dir)
    store.capture(kind='control', observation='same logical record')
    verdict = store.verify_chain()
    copies = sum(r['observation'] == 'same logical record' for r in store.read_all())
    print('reopen and retry:', verdict['count'], verdict['ok'], 'logical copies', copies)
    assert verdict['ok'] and verdict['count'] == 3 and copies == 2

    store = EvidenceStore(base / 'malformed-head')
    store.capture(kind='control')
    saved = store.head_path.read_bytes()
    for contents in (b'{', b'[]', b'null'):
        store.head_path.write_bytes(contents)
        try:
            print('head shape', contents, errors(store.verify_chain()))
        except AttributeError as exc:
            print('head shape', contents, type(exc).__name__)
    store.head_path.write_bytes(saved)
    assert store.verify_chain()['ok']
    print('head restored:', store.verify_chain()['ok'])
```

The export variant can be run on a new `EvidenceStore` with one neutral record. Keep an unpatched reference to `EvidenceStore.verify_chain`, then patch the method with a wrapper that calls the original, appends one neutral record using a separately instantiated store for the same directory, and returns the original verdict. Call `export_bundle(store.session_dir, strict=True)` while patched. The expected integrity count and returned record count are `1` and `2`. After restoring the method, they are both `2`. For the work-count control, wrap `store._read_lines` so it adds `store.path.stat().st_size` before calling the original. For each of 250, 500, 1,000, and 2,000 records in a fresh store, append `kind='control', observation='x' * 160, step=i` where `i` starts at zero. Measure runtime in separate runs without the hook.

Process deadline. The original fixture compared a 0.055 s timeout against a 0.25 s child that held its pipe open and printed a completion marker, with a fresh clock reading around each invocation. A condensed control is below.

```python
import contextlib
import io
import sys
import time
from engine import _run_shell
from tools.hunt import run_cmd

source = "import time; print('start', flush=True); time.sleep(0.25); print('done', flush=True)"
argv = [sys.executable, '-c', source]

for run in (_run_shell, run_cmd):
    start = time.monotonic()
    with contextlib.redirect_stdout(io.StringIO()):
        ok, output = run(argv, cwd='/tmp', timeout=0.055)
    print(run.__name__, ok, round(time.monotonic() - start, 3),
          'done' in output.splitlines(), 'timed out' in output)
```

Expected `_run_shell True ~0.256 True False` and `run_cmd False ~0.057 False True`. An independent child fixture closed fd 1 and fd 2 before its delay. That triggered the former helper's timed-wait branch. For the interrupt case, start the same job helper with a worker that writes its PID to a private FIFO and then waits. Read the FIFO, verify `os.getpgid(pid) == pid`, and send SIGINT to the parent helper process only. The test trapped `KeyboardInterrupt` in the enclosing program and checked `/proc/{pid}/stat`. The worker was in `S` after the parent returned. The fixture killed its own worker group before releasing the namespace. Give that same fixture a short timeout instead of sending SIGINT for the control. Its PID was gone when the runner returned.

File-size and restart checks. In a temporary directory save a `HuntMemory` snapshot with a short text and step count 12, and create a neutral config with `engine.save_config` after pointing `engine.CONFIG` at a temporary path. Reopen normally. In a fresh child for each of those paths apply `signal.signal(signal.SIGXFSZ, signal.SIG_IGN)` and `resource.setrlimit(resource.RLIMIT_FSIZE, (64, 64))`, then save an updated fixture with a 700-character text. Expect file size 64 and errno 27 on each child. In the unrestricted parent reopen the snapshot and read the config. The former reports step count zero and empty notes. The latter warns and returns `{}`. Restoring the pre-fault bytes should restore the prior values. A sibling scratch case used a valid snapshot with `observation_buf` set to JSON null, yielding prior notes and default count. For the kernel-backed audit framing check, set the child file-size limit to the original file size plus 12 and make one neutral append. Append another valid record in the unrestricted parent and check `read_all()`. It reports only the original row and warns about the joined line.

Other cross-checks use these entrypoints and neutral data.

- **Schema and maintenance.** Add a standalone `[]` JSON line to a temporary log after a valid row. Compare `AuditLog.count_by_session`, `PatternDB.save` after reopening, and `HuntJournal.read_all`. The first two raise `AttributeError` and the third returns the list as a row. For migration, begin with a valid v1 journal, check `migrate_file(path, dry_run=True) == (1, 0)`, and pause the normal call at `Path.write_text` for the active file after it wrote the backup. Append a v2 fixture row during the pause and verify it exists before releasing. It is absent from both resulting files. [bughunter/memory/audit_log.py:112](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/audit_log.py:112), [bughunter/memory/pattern_db.py:48](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/pattern_db.py:48), [bughunter/memory/hunt_journal.py:46](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/hunt_journal.py:46), [bughunter/tools/memory_migrate.py:42](repos/awarexone__Agentic-Bug-Hunter/bughunter/tools/memory_migrate.py:42)
- **Import and config.** Run `review_box /usr/bin/env -u PYTHONPATH /runtime/bin/python -B -c 'import bughunter.agent'` and compare importing it after `from bughunter.__main__ import agent_main`. Compare `agent is bughunter.agent` with the two modules' `__file__` fields. The paths match and the objects differ. Put `{'models': {'first': 'a', 'second': 'b'}}` into a stub `load_config` in a cleared environment and stub `_import_brain` with an inert constructor returning its provider and model. Call `_get_client('first')` then `_get_client('second')`. Both use `a`. [bughunter/__main__.py:13](repos/awarexone__Agentic-Bug-Hunter/bughunter/__main__.py:13), [bughunter/engine.py:196](repos/awarexone__Agentic-Bug-Hunter/bughunter/engine.py:196)
- **Lifecycle and model tests.** Use a constructorless `ReActAgent` with a neutral `HuntMemory` and tracer, no available dispatcher, and an inert model identifier. For the early-stop control set `max_steps=0` with ample budget or `max_steps=1` with an exhausted budget, plus `done=False` and empty verdict. `run()` returns success with zero recorded steps and an empty trace in both cases. For the three-iteration control inject a tool-free mock reply or `TimeoutError`, and replace the system text and tool list with inert values. To check acquisition explicitly, stub both effect and model constructors and make only the model constructor raise after the real tracer opens. The normal return closes the tracer and the fault path does not explicitly close it. [bughunter/agent.py:1548](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1548), [bughunter/agent.py:1740](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1740), [bughunter/agent.py:1987](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1987)
- **Static ownership checks.** Use `git grep -n -e '\._limiter' -e 'RateLimiter' -- '*.py'` and `git grep -n 'race_analysis(' -- '*.py'`. The first reports the standalone limiter and initialization of the guard's limiter, with no invocation in the guard. The second reports the helper's definition only, so daemon-thread behavior of that helper is not attributed to the exercised built-in loop. Search `Popen`, `communicate`, `wait(timeout`, and `killpg` in the named wrappers before extending any timeout conclusion beyond the measured call sites. [bughunter/memory/audit_log.py:279](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/audit_log.py:279), [bughunter/agent.py:1341](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1341), [bughunter/brain.py:2364](repos/awarexone__Agentic-Bug-Hunter/bughunter/brain.py:2364), [bughunter/mcp/bughunter-mcp/adapters.py:123](repos/awarexone__Agentic-Bug-Hunter/bughunter/mcp/bughunter-mcp/adapters.py:123)

**Supplemental evidence checks**

The uninstrumented consistency control uses three ordinary writer processes. Run the same input with the Btrfs bind from above to distinguish a pathname/publication issue from tmpfs behavior. The race count varies with scheduling. The committed count and shared-lock read results are invariants in the exercised case.

```python
import fcntl
import multiprocessing as mp
import os
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from memory.evidence import EvidenceStore

def writer(directory, start, counts):
    store = EvidenceStore(directory)
    start.wait(timeout=4)
    for i in range(counts):
        store.capture(kind='control', observation=f'writer-{os.getpid()}-{i}')

def run_trial(directory, protected):
    store = EvidenceStore(directory)
    store.capture(kind='control', observation='seed')
    ctx = mp.get_context('fork')
    start = ctx.Barrier(4)
    procs = [ctx.Process(target=writer, args=(directory, start, 70)) for _ in range(3)]
    results = Counter()
    for proc in procs:
        proc.start()
    try:
        start.wait(timeout=4)
        for i in range(210):
            if protected:
                with store.path.open('rb') as file:
                    fcntl.flock(file.fileno(), fcntl.LOCK_SH)
                    decision = store.verify_chain()
            else:
                decision = store.verify_chain()
            results['clean' if decision['ok'] else ','.join(e['error'] for e in decision['errors'])] += 1
        for proc in procs:
            proc.join(timeout=5)
            assert proc.exitcode == 0
    finally:
        for proc in procs:
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=2)
    final = store.verify_chain()
    print('natural overlap:', 'shared lock' if protected else 'unlocked', dict(results),
          'final', final['count'], final['ok'])
    assert final['ok'] and final['count'] == 211
    if protected:
        assert results == {'clean':210}

with TemporaryDirectory() as directory:
    base = Path(directory)
    run_trial(base / 'standard', False)
    run_trial(base / 'external-lock-control', True)
```

The permission control uses a disposable copy of its own neutral records. It isolates stat, actual file readability, record decoding, and the normal state after restoration. Run under `review_box /runtime/bin/python -B -` and `review_box /usr/bin/python -B -`. Inspect the two local implementations with `import inspect, pathlib; print(inspect.getsource(pathlib.Path.is_file))` in each interpreter, plus `genericpath.isfile` in 3.14.

```python
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from agent import HuntMemory
from memory.evidence import EvidenceStore

def result(call):
    try:
        value = call()
    except (ValueError, OSError, AttributeError) as exc:
        return type(exc).__name__
    return value['ok'], value['count']

with TemporaryDirectory() as directory:
    base = Path(directory)
    evidence = EvidenceStore(base / 'readability')
    evidence.capture(kind='control')
    memory = HuntMemory(str(evidence.session_dir / 'snapshot.json'))
    memory.step_count = 17
    memory.save()
    assert result(evidence.verify_chain) == (True, 1)
    original = evidence.path.read_bytes()
    evidence.path.write_bytes(original + b'\xff\n')
    print('Python', sys.version.split()[0], 'UTF8 error verdict:', result(evidence.verify_chain))
    evidence.path.write_bytes(original)
    evidence.path.chmod(0)
    try:
        assert evidence.path.is_file()
        print('unreadable log as file:', result(evidence.verify_chain))
    finally:
        evidence.path.chmod(0o600)
    evidence.session_dir.chmod(0)
    try:
        try:
            evidence.path.stat()
        except PermissionError:
            print('stat errno', 13,
                  'directory verdict', result(evidence.verify_chain),
                  'session steps', HuntMemory(memory.session_file).step_count)
        else:
            raise AssertionError('fixture expected stat denial under unprivileged uid')
    finally:
        evidence.session_dir.chmod(0o700)
    print('restored:', result(evidence.verify_chain), HuntMemory(memory.session_file).step_count)
    assert result(evidence.verify_chain) == (True, 1) and HuntMemory(memory.session_file).step_count == 17
```

The runtime sources inspected by `inspect` were Python 3.12.16's `pathlib.py:886`, Python 3.14.8's `pathlib/__init__.py:685`, and Python 3.14.8's `genericpath.isfile` at line 36 of its frozen source.

For the head short-write control, use the same baseline-plus-second-record fixture as above. In a child wrap only the real `_write_head` call in a temporary 12-byte soft `RLIMIT_FSIZE` and ignore `SIGXFSZ` in that child. The normal append uses the original limit. Capture reports success, the head length is 12, and verification reports `head_anchor_unreadable`. This isolates the missing return-value check in the head writer. [bughunter/memory/evidence.py:134](repos/awarexone__Agentic-Bug-Hunter/bughunter/memory/evidence.py:134)

For the mailbox control, call `ReActAgent._check_bump` on a neutral object with only a temporary `bump_file` attribute. Pause `Path.read_text` for that file after the real read returns the first string. Write a second string while paused. On release, the first read returns the first string, the file is empty, and a second call returns `None`. A normal single-message read consumes its first string as designed. [bughunter/agent.py:1535](repos/awarexone__Agentic-Bug-Hunter/bughunter/agent.py:1535)
