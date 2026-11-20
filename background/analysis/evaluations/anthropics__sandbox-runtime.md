# Anthropic Sandbox Runtime architecture and reliability evaluation

## 1. Snapshot, scope, and elapsed-time evidence

| Item | Evidence |
| --- | --- |
| Repository | `repos/anthropics__sandbox-runtime` |
| Pinned revision | `0bbebed0aa9a8e628dc4df8bc30293550a1988eb`, `Release v0.0.83 (#824)`, committed `2026-11-12T17:34:05-05:00` |
| Start | `2026-11-19T07:18:15Z`. Exact HEAD matched. Porcelain status was empty with untracked files included. A second status check included ignored entries and returned empty. |
| UTC checkpoints | `07:19:04` isolated toolchain and cache gate, `07:21:43` native helper and first suite results, `07:24:22` raw baseline tally and procfs control, `07:26:48` compiled FD handoff and native Windows ownership, `07:30:40` CLI signal, stdio and FD probes, `07:32:29` managed suite and live policy swaps, `07:33:40` wrap queue and cancellation review, `07:35:33` startup watchdog and external-origin oracle, `07:37:44` CLI residual socket and CA fixture attribution, `07:38:00` namespace and test limits, `07:41:09` per-verdict deadline and report appendix review, `07:43:22` scanner-budget and appendix syntax checks, `07:44:24` Unix path budget, `07:45:25` event store and complete replay output, `07:45:55` replay differences and standalone handoff. All times on 2026-11-19. |
| End | `2026-11-19T07:48:20Z`. **30 minutes 5 seconds** elapsed. HEAD remained `0bbebed0aa9a8e628dc4df8bc30293550a1988eb`. Staged and unstaged diffs were empty. Status was empty with untracked and ignored entries included. Both disposable review trees had been removed. |
| Scope | Command planning and launch, OS boundaries, proxy data paths, process and resource ownership, cancellation and recovery, runtime policy, observability, and embedder contracts. |
| Environment | Linux x86-64 `7.2.15-1-omarchy`, UID 1000, Bun `1.4.2`, Node `22.23.1` and `24.22.2`, bubblewrap `0.13.1`, socat `1.8.1.3`, GCC `16.2.1`, libseccomp `2.6.0`, and JDK `21.0.13`. Tests ran from a Git archive inside an isolated namespace with loopback, a synthetic home and etc directory, and an empty inherited environment. |

SRT offers two primitives for a harness. Its manager compiles policy for an OS-specific process wrapper and owns session networking. Its standalone proxy runs the HTTP data plane for a workload confined by another supervisor. The Linux wrapper and standalone proxy worked in the local controls. The largest reliability gap is how the manager transfers ownership during startup and teardown. Two ordinary reset interleavings left the caller with a false readiness result or left bridge processes running. The controls and their dependency limits are in sections 6 and 7. [Library exports](repos/anthropics__sandbox-runtime/src/index.ts:1), [Manager API](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3922), [Standalone proxy contract](repos/anthropics__sandbox-runtime/docs/srt-proxy.md:1)

The integration boundary is process execution and traffic policy. The host harness owns task scheduling, command replay, stdout/stderr retention, environment selection, CPU/memory quotas and tool outcome interpretation. The separate Windows recovery database tracks native ACL ownership and repair, which serves a different purpose from a task or execution log. [Invocation API](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3958), [Windows state scopes](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/state_db.rs:1)

## 2. Core architecture and end-to-end control/data flow

### Full sandbox mode

1. **Admission.** The CLI loads default or explicit settings and validates JSON through the Zod schema. It uses built-in defaults only for a missing implicit file. A malformed, inaccessible, or explicitly missing file stops startup. Positional arguments are quoted individually into a command string. The `-c` interface accepts shell text. The library takes a typed configuration and trusted callbacks. It leaves construction and schema parsing for programmatically supplied configs to the embedder, while individual operations still validate what they use. A single process can own one initialized manager session. [Settings outcomes](repos/anthropics__sandbox-runtime/src/utils/config-loader.ts:14), [CLI admission](repos/anthropics__sandbox-runtime/src/cli.ts:377), [Command construction](repos/anthropics__sandbox-runtime/src/cli.ts:567), [Config schema](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-config.ts:1189), [Initialize entry](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1170)

2. **Session startup.** Initialization sets the policy reference and generation, resolves parent routing and direct address checks, builds a CA if configured, checks dependencies, and optionally attaches an OS monitor. Native Windows setup may verify the helper and machine policy, refresh profile grants, and record/apply session ACLs. MXC instead caches the selected SDK and the probed access set. The managed listener is a loopback multiplexor. The HTTP backend binds first, SOCKS is dispatched by the first octet, and a tracked set of accepted sockets belongs to the mux. An external HTTP or SOCKS port substitutes for that protocol. Both external ports together bypass the mux. Linux starts the host relay or relay pair and then publishes the context containing the ports and bridge handles. [Initial policy and dependencies](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1246), [Windows ACL startup](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1691), [MXC state](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:427), [Mux startup](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1010), [Mux dispatch](repos/anthropics__sandbox-runtime/src/sandbox/mux-proxy.ts:159), [Context publication](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1779)

3. **Invocation planning.** The POSIX wrapper obtains a turn for the filesystem walk before reading config, its install counter, and cwd. It resolves literal and pattern entries, default writable paths, and credential-specific deny or mask inputs. It retries with fresh observations if config or cwd changed during the yielding walk. The Linux backend then scans for mandatory denies and compiles the mount plan. A long mount vector can travel through an unlinked args file with an open descriptor owned by the manager process. Raw per-invocation network list registration is a separate API. Specifying network policy requests a restricted network path, while the managed proxy judges traffic against the session rules and the registration it can attribute. [Walk ordering](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:2713), [Config and cwd invariants](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:2952), [Literal path shape](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-config.ts:74), [Long bwrap invocation](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:1035), [Per-command lists](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3975)

4. **Launch and enforcement.** The CLI starts the wrapper and owns terminal exit. A library caller can spawn the POSIX shell string, or use `wrapWithSandboxArgv()` to get argv and environment. Windows native expects `shell:false` so command text is parsed by the sandbox's intended shell. MXC needs `spawnSandboxed()` and returns a handle that exposes streams, tree kill, wait, and dispose. The initial cwd has policy meaning. POSIX path planning uses the host process's cwd. The Windows argv contract expects the cwd used for injection to match the eventual spawn. These are real integration requirements for a harness running multiple tools. [POSIX and Windows launch](repos/anthropics__sandbox-runtime/src/cli.ts:681), [Argv/cwd contract](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3082), [MXC process contract](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3345)

5. **Network data path.** A managed HTTP/SOCKS request reaches the mux from the OS-permitted loopback endpoint. Linux uses inner TCP relays in the command's network namespace, bind-mounted Unix sockets, and host socat relays to the proxy ports. The managed proxy evaluates explicit denies, configured allows, strict allowlist, eligible invocation allowances, and the ask callback in that order. Default and callback failures deny, and only literal `true` allows through an ask. The direct-dial lookup constrains the actual resolved addresses. Parent proxy and external MITM routing hand resolution to the selected hop. HTTP can run a separate per-request decision before forwarding. CONNECT can carry an opaque upstream tunnel, use the configured upstream MITM socket, or terminate TLS in-process, depending on policy. In-process termination uses the CONNECT transport and an inner HTTP parser, so a separate per-tunnel listening port is unnecessary. [Linux relays](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:1491), [Destination policy](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:774), [Direct versus delegated address resolution](repos/anthropics__sandbox-runtime/src/sandbox/resolved-address-guard.ts:1), [HTTP proxy control](repos/anthropics__sandbox-runtime/src/sandbox/http-proxy.ts:1), [In-process termination](repos/anthropics__sandbox-runtime/src/sandbox/tls-terminate-proxy.ts:1)

6. **Command completion and teardown.** CLI exit calls `cleanupAfterCommand()` for mount artifacts and exits with the child's code or its signal mapping. By design the POSIX/native library callers still own child supervision. Manager reset stops monitors, signals bridge processes, closes servers and connections, and disposes temp data and registries. Exit hooks can synchronously remove known temporary items when the asynchronous tail of reset cannot finish. Windows native additionally releases session ACL holds and keeps intentionally persistent write roots. MXC callers retain ownership of the process handles they launched. [CLI terminal outcome](repos/anthropics__sandbox-runtime/src/cli.ts:595), [Manager exit cleanup](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:460), [Resource teardown](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3682), [MXC reset boundary](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3705)

### Platform enforcement and ownership

| Backend | Enforcement and process tree | State and recovery |
| --- | --- | --- |
| Linux | Bubblewrap builds mount, user, network, and normally fresh PID/proc views. Host-readable filesystem with a read-only write baseline, explicit write binds and denies, read masks through file or tmpfs mounts, and selected read carve-outs. Inner relays start before the seccomp helper. The native helper creates its worker boundary, keeps an outer waiter, and reaps the isolated process tree. `--new-session` and `--die-with-parent` complement caller supervision. | Disk-backed workload changes persist under write roots. The host JS process owns its Unix bridge sockets, mount placeholders, args FDs, and diagnostic listener. `cleanupAfterCommand()` returns one unit of shared mount ownership. A crashed process has no durable task record or automatic replay. [Filesystem plan](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:2095), [Namespace args](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:3800), [Helper process shape](repos/anthropics__sandbox-runtime/vendor/seccomp-src/apply-seccomp.c:2), [Mount cleanup](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:1112) |
| macOS | A command is launched through `/usr/bin/sandbox-exec -p` with an SBPL profile and a quoted environment and shell command. Read/write policy and selected localhost, Unix socket, Mach, PTY and Apple Events exceptions are expressed as profile predicates. Credential file masking degrades to a read denial because this backend cannot replace file contents. Violations are drawn from a tagged OS log stream. | Profile applies for the launched process tree. The host owns the listeners and optional log process. Linux mount filesystem ownership is unnecessary on this backend. Native Seatbelt enforcement and log delivery are source-only in this review. [Profile assembly](repos/anthropics__sandbox-runtime/src/sandbox/macos-sandbox-utils.ts:1047), [Launch and env](repos/anthropics__sandbox-runtime/src/sandbox/macos-sandbox-utils.ts:1412), [Log monitor](repos/anthropics__sandbox-runtime/src/sandbox/macos-sandbox-utils.ts:1627) |
| Windows native | The TypeScript broker plans access, verifies setup, and dispatches to the Rust helper. Machine-wide WFP install confines the configured sandbox identity to the configured loopback access. A runner receives a length-prefixed command spec, builds the restricted token and environment, applies desktop and handle rules, and starts the command suspended. It assigns the job before resume. The command-side job disallows breakaway and tears down the remaining tree on close. | Machine setup and per-user session DB have distinct owners. The DB records additive ACL holds and object identities, serializes mutation across brokers, and converges live ACLs on recovery. Individual commands may request additional denies. Session grants are shared OS state, including kept write grants whose lifetime is longer than a process. The README documents identity and platform scope. [Windows manager](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1397), [WFP install](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/wfp.rs:625), [Runner protocol](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/runner.rs:60), [Suspended launch](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/launch.rs:263), [Job ownership](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/job.rs:31), [State DB](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/state_db.rs:1), [Windows limitation notes](repos/anthropics__sandbox-runtime/README.md:1054) |
| Windows MXC | The harness can provide an SDK or let SRT resolve the optional dependency. SRT builds a complete request and checks the probe's ability to enforce it before SDK spawn. Per-command read/write grants can travel with that request. The adapter exposes the SDK's pipe, wait, timeout, kill and dispose semantics. Settings with no faithful translation are refused. | Access rules are associated with the launch request. Reset clears the cached SDK/session selection. The caller releases the native process handle. Real provider enforcement was outside this Linux environment. [SDK load surface](repos/anthropics__sandbox-runtime/src/sandbox/mxc-sandbox-utils.ts:166), [Probe and spawn](repos/anthropics__sandbox-runtime/src/sandbox/mxc-sandbox-utils.ts:286), [Request translation](repos/anthropics__sandbox-runtime/src/sandbox/mxc-sandbox-utils.ts:435), [Manager spawn](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3393) |

### Standalone proxy mode

The harness binds and passes the listener, supplies a bidirectional decider link or its two ends, and may pass a lifeline and CA pipe. It is responsible for workload confinement and listener reachability. The proxy speaks protocol version 1, validates the other side's hello, sets the name and direct-address policy, then accepts. The network socket is handed to an HTTP server. Host permission is checked before a request verdict. The HTTP phase can make a bounded body available to the decider and consumes the reply under a request ID before any upstream dial. Shutdown stops acceptance, wakes pending verdict waiters, offers a short response flush window, then destroys remaining tracked connections. The enclosing service is the restart owner. [FDs and invocation](repos/anthropics__sandbox-runtime/docs/srt-proxy.md:13), [Proxy lifecycle](repos/anthropics__sandbox-runtime/src/sandbox/proxy-only.ts:113), [Readiness and close](repos/anthropics__sandbox-runtime/src/sandbox/proxy-only.ts:223), [Verdict states](repos/anthropics__sandbox-runtime/src/sandbox/decider-client.ts:368)

## 3. Why the design works and its governing invariants

- **Primitive enforcement sits below the workload.** The CLI and library generate launch inputs. The platform's mount/namespace/profile/token/job path controls resource access. Proxy env and a Java adapter make standard clients cooperate without inventing an alternate application protocol. The Linux network namespace still controls clients that ignore those settings. An embedder passing external ports takes responsibility for enforcement at those endpoints. [Linux isolated net](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:3695), [Proxy env generation](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:3728), [External listener selection](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1787)
- **One filesystem plan follows one configuration and cwd.** The glob walker yields periodically and holds cached directory listings for one attempt. The manager serializes that work, releases the turn before waiting for networking, and discards a walk that crossed a policy or cwd transition. The Linux compiler resolves sources after its async scan and memoizes them for the rest of the plan. Cwd drift across that scan triggers a new attempt. Mount order and deduplication are policy decisions: read hides can conceal older binds, read carve-outs selectively restore content, and the write denies are scheduled to continue to protect the resulting view. [Walk reservation](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:2647), [Snapshot checks](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:2741), [Cwd retry](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3057), [Canonical/path roles](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:2095)
- **Live and launch-time policy have different publication points.** The manager reads domain rules and the direct-address guard per new request/dial. Already-established opaque streams retain their admission. The OS filesystem namespace or profile is decided for a particular command, and Windows native ACL policy is tied to session initialization and per-invocation denies. Listener addresses, TLS setup, and some callbacks are captured on startup. A successful update therefore has a narrower effect than restarting a session and respawning its tools. [Live guard](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:209), [Proxy options captured or read live](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1014), [Update contract](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3488), [Control channel scope](repos/anthropics__sandbox-runtime/README.md:201)
- **Name permission is distinct from connection permission.** Direct mode filters resolver candidates and dials one of the candidates checked. The address guard gives deliberate IP literals and explicit loopback names their specified meaning, while classifying configured and built-in address denials. A delegated hop owns its resolver. The standalone mode further requires a matching authority and a well-formed request verdict before forwarding. [Address guard](repos/anthropics__sandbox-runtime/src/sandbox/resolved-address-guard.ts:199), [Hello permissions](repos/anthropics__sandbox-runtime/src/sandbox/proxy-only.ts:223), [Standalone delivery contract](repos/anthropics__sandbox-runtime/docs/srt-proxy.md:264)
- **Resource identity and teardown are tied to the owner.** Session Linux relay ownership lives in the manager context. Native Windows keeps the original SID and helper identity for release. Windows's DB tracks the holder PID with its creation time and records intent before applying an ACE, so a later broker can recover a partial operation without confusing a reused PID for the owner. Grants retire before dependent denies. The Linux mount counter instead assumes each successful wrap gets one matching cleanup and that forced cleanup follows the end of all active uses. [Linux readiness and ownership](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1826), [Windows cleanup identity](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3688), [ACL write/release ordering](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/state_db.rs:30), [Recovery order](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/state_db.rs:1833), [Mount batch ownership](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:1141)
- **A decider verdict progresses once per phase.** A request begins with one waiter and an expiry. The one permitted `need_body` phase reserves shared bytes and allows an early deny. A second waiter starts after the body frame. Version, framing, schema, ID, and queue checks turn incompatible or unavailable decision links into an explicit refusal. Full manager's permission callback and out-of-process verdict channel have different guarantees. [Protocol framing](repos/anthropics__sandbox-runtime/src/sandbox/decider-client.ts:313), [Waiter lifecycle](repos/anthropics__sandbox-runtime/src/sandbox/decider-client.ts:368), [Body budget](repos/anthropics__sandbox-runtime/src/sandbox/decider-client.ts:511), [Manager permission callback](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:850)

## 4. What it does well and poorly, with source evidence

### Strengths

| Quality | Assessment |
| --- | --- |
| Policy compiler distinguishes ambiguity from absence | Structured literal paths and separate rendered paths let clients specify a bracketed filename with its literal meaning. Linux code keeps the lexical spelling, the resolved destination, and whether the target exists distinct. It budgets argv, handles filesystem errors according to their meaning, and uses conservative masks when policy cannot be inspected at its exact path. Live mount and generated-plan tests give this code stronger support than syntax-only wrappers. [Path entry schema](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-config.ts:76), [Linux target classification](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:2148), [Argument profile errors](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:961), [Mount plan tests](repos/anthropics__sandbox-runtime/test/sandbox/linux-mount-plan-record.test.ts:1) |
| Startup probes expose enforcement limitations | Linux returns structured dependency errors and warnings. Native Windows verifies provisioning, capabilities and running egress under the relevant identity. The experimental MXC adapter declines unsupported features and checks its own probe before starting. Failed CA loading and unsupported TLS runtimes are surfaced before program launch. [Linux dependency status](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:1304), [Windows WFP startup gate](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1728), [MXC gate](repos/anthropics__sandbox-runtime/src/sandbox/mxc-sandbox-utils.ts:286), [TLS startup gate](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1270) |
| Data-plane cancellation is deliberately engineered | The proxy can stop waiting when the peer detaches, tunnel budgets and deadlines have explicit owners, and the terminated path accounts for runtime-specific backpressure. The standalone proxy resolves pending decisions as unavailable on link death and drains clients only for a bounded time. Tests independently exercise delayed verdicts, client detach, head/body limits, and keepalive reuse. [Standalone close](repos/anthropics__sandbox-runtime/src/sandbox/proxy-only.ts:249), [Decider link death](repos/anthropics__sandbox-runtime/src/sandbox/decider-client.ts:282), [Client abort tests](repos/anthropics__sandbox-runtime/test/sandbox/client-abort.test.ts:1), [Handshake deadline tests](repos/anthropics__sandbox-runtime/test/sandbox/tls-terminate-handshake-deadline.test.ts:1), [Relay budget tests](repos/anthropics__sandbox-runtime/test/sandbox/tls-terminate-relay-budget.test.ts:1) |
| Native Windows recovery is explicit | Record-first ACL writes, identity rechecks, a cross-broker lock, pending persistent-grant replay, and ordered revoke all aim to converge after interruption. Suspended creation and resource guards prevent a failed setup step from releasing an unconfined ordinary command. These properties are visible in code and covered by native fixtures in CI. [DB locking](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/state_db.rs:30), [Recovery](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/state_db.rs:1780), [Launch guard](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/launch.rs:296), [Native test matrix](repos/anthropics__sandbox-runtime/.github/workflows/integration-tests.yml:35) |
| Integration seams keep agent decisions outside enforcement | A harness can supply trusted ask and request callbacks, set an opaque invocation ID for lease-like network permissions, annotate stderr, and pass external ports or already-open descriptors where it owns infrastructure. The source documents limits on attribution keys, compatibility of deny answers, and the distinct scope of external ports. [External decider](repos/anthropics__sandbox-runtime/docs/srt-proxy.md:1), [Ask compatibility](repos/anthropics__sandbox-runtime/README.md:321), [Invocation allowlist contract](repos/anthropics__sandbox-runtime/README.md:345), [Public exports](repos/anthropics__sandbox-runtime/src/index.ts:35) |

### Weaknesses

| Severity of operational impact | Observation and evidence status |
| --- | --- |
| High for a long-lived harness | **Teardown and restart have no shared transition barrier.** A new initialize called while reset is waiting for an old relay can see the resolved initialization promise and return early. Reset then clears runtime references. The caller receives a fulfilled initialize with `waitForNetworkInitialization() === false`. The old configuration is still readable and `isSandboxingEnabled()` reports true. Reproduced under Node 22 and 24 with real Linux subprocesses and both external-port overrides. Waiting for reset before reinitializing gave a ready session. [Reuse path](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1235), [Enabled predicate](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1872), [Async teardown and reference clearing](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3725) |
| High for repeated cancellation | **A bridge duo can outlive a cancelled startup.** Linux setup returns live processes and socket paths to a local temporary. The generation check runs before that value is adopted by `managerContext`. Reset and the initialization error handler clean published state. In the controlled in-flight case initialize rejected, readiness stayed false, and both relays and both paths survived two awaited resets. Before-spawn and after-ready controls left zero. Reproduced with gated timing around real socat on Node 22 and 24. [Linux bridge creation](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:1513), [Adoption and catch](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1826), [Context-owned teardown](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3725) |
| Medium for host supervision | **Preparation, running child, and session are individually managed.** POSIX wrapping yields a shell string and a global accounting increment. The embedder must track processes, match cleanup to a successfully prepared command, and wait for children before reset. Reset supports teardown of the session's resources and forces mount cleanup. It has no table of active POSIX child handles. A caller which spawns redundantly, loses a wrapper, or resets out of order sees weak ownership feedback. There is no general POSIX/MXC-neutral command timeout API. The native Windows runner waits indefinitely for its main child, while the MXC option has an explicit timeout. [Wrapper API](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3958), [Linux mount accounting](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:3594), [Forced cleanup](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3711), [MXC timeout](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3323), [Native wait](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/launch.rs:348) |
| Medium for a policy control plane | **A config assignment can describe values the running proxy did not adopt.** The live route consults the new domain rules, resolved address guard and selected configuration getters. Other options are bound when the servers start. The API resolves void and the CLI channel receives no application acknowledgment or generation. A config object is retained by reference on initialize and returned directly by `getConfig()`. The version check catches published replacements, not arbitrary caller mutation. `updateConfig()` clones its input apart from the callback reference. Its invalid-CIDR atomicity worked in the local control. [Initial config reference](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1255), [Captured options](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1025), [Update swap](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3484), [CLI reader](repos/anthropics__sandbox-runtime/src/cli.ts:523) |
| Medium for readiness diagnostics | **Linux bridge readiness is socket existence; health after publication is best effort.** The startup loop checks process handles and socket paths. Exit handlers log loss. The wrapper checks paths before mounting them and reports missing ones. There is no monitor that restarts a dead bridge or transitions a published session to failed. A path or init promise is therefore a poor substitute for a current end-to-end health check. The external-port contract also leaves target service liveness to the embedder. [Health handlers](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:1533), [Readiness loop](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:1608), [Wrap path check](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:3704), [Readiness accessor](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:2602) |
| Medium for platform and launch diagnosability | **Temp paths and partial scans affect startup and plan quality.** A long valid `TMPDIR` exceeds the relay's Unix address budget. The manager waits on its intended filename and loses socat's detailed diagnostic. A mandatory scan deadline can return a plan for the results scanned so far and an optional debug warning. Caller abort rejects the plan. The two outcomes should be distinguishable to a harness that requires a complete scan. [Bridge socket naming and stdio](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:1513), [Readiness loop](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:1608), [Scanner fallback](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:604), [Scanner timeout](repos/anthropics__sandbox-runtime/src/utils/ripgrep.ts:28) |
| Medium for shared hosting | **The proxy's bounded mechanisms cover particular traffic and resources.** TLS admission, verdict waits, body bytes and relay queues have caps. The standalone docs explicitly leave plain pre-header/idle connections uncapped. The HTTP options document weaker upload pacing on Bun's native HTTP listener than on the standalone handed-in socket path. The decider hello waits on a frame or failure and has no separate startup timeout. The body-inspection intermediate waiter has no deadline. On an exceptional body-read exit the surrounding catch returns a refusal and releases bytes, while waiter cancellation only follows the successful body-read branch. The latter is a source-level concern. A harness should supervise startup, transport and workload limits at its own layer. [Published bounds](repos/anthropics__sandbox-runtime/docs/srt-proxy.md:286), [Bun transport-specific budget](repos/anthropics__sandbox-runtime/src/sandbox/http-proxy.ts:413), [Hello promise](repos/anthropics__sandbox-runtime/src/sandbox/decider-client.ts:265), [Body-reading waiter](repos/anthropics__sandbox-runtime/src/sandbox/decider-client.ts:523), [Standalone ready](repos/anthropics__sandbox-runtime/src/sandbox/proxy-only.ts:223) |
| Medium for portability | **Descriptor and HTTP runtime behavior affect the orchestration contract.** Node's proxy CLI duplex socket route worked, and its actual anonymous two-pipe route rejected with the documented `ENOTCONN` under both Node versions. Bun source and the compiled executable passed both transports. The distinction matters if the supervising process uses true OS pipes rather than a socketpair surfaced as a child-process pipe. [FD implementation](repos/anthropics__sandbox-runtime/src/sandbox/proxy-only.ts:287), [Documented Node limit](repos/anthropics__sandbox-runtime/docs/srt-proxy.md:50), [CLI descriptor selection](repos/anthropics__sandbox-runtime/src/proxy-cli.ts:131) |

## 5. Core-code quality: decomposition, state, concurrency, errors, types, tests, observability, extensibility, and maintainability

- **Decomposition.** The design splits policy matching, path semantics, transport adaptation, native launch and observation, which makes several meaningful suites independent of the top-level CLI. The proxy-only entry builds from a narrower graph and built successfully without the SOCKS dependency. The manager and the Linux/Windows adapters are large concentration points: `sandbox-manager.ts` is 4,114 lines, `linux-sandbox-utils.ts` 3,937, and `windows-sandbox-utils.ts` 4,814. The Linux compiler has a semantic plan embedded in a single function alongside filesystem probes and emitted argv, which makes precedence changes expensive to review. A typed plan representation plus explicit ownership boundaries would retain the native backend's semantics while making fault injection local. [Manager file](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:175), [Linux compiler](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:2095), [Windows utilities](repos/anthropics__sandbox-runtime/src/sandbox/windows-sandbox-utils.ts:1), [Proxy-only entry](repos/anthropics__sandbox-runtime/src/proxy-main.ts:1)
- **State and concurrency.** The initializer's same-arguments join and changed-arguments rejection are useful. The generation counter guards installation across awaits, and the walk gate prevents concurrent walks from hoarding listings. The reset code still types resources as unrelated globals. This allows publishing a successful promise, a policy reference, and a backend handle at different times. The main unbounded work source is caller-supplied workload and command concurrency. Yielding a filesystem walk helps, while synchronous fallback and synchronous access checks still add event-loop latency for big or slow trees. [State slots](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:185), [Initialize conflict](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1170), [Walk fallback](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:2782), [Reset teardown](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3682)
- **Errors and types.** Strict TypeScript flags, schema-inferred configs, discriminated policy verdicts, typed native/probe errors, and Linux profile errors make many failure paths actionable. Interfaces evolve with optional backend APIs and an ask-denial feature marker. A library type describes input but does not itself validate JavaScript callers. Admission, resource failure, policy denial, and cancellation are represented inconsistently across CLI exit codes, exceptions, negative return values, and debug logs. A uniform result should retain the useful native details. [Type compiler](repos/anthropics__sandbox-runtime/tsconfig.json:19), [Schema-inferred types](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-config.ts:1557), [Linux error taxonomy](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:961), [Library compatibility markers](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:4020)
- **Observability.** Proxy denials, tagged Seatbelt log messages, and Linux seccomp observation feed a common bounded store. The Linux observer is best effort: it observes write intent, then classifies paths against policy supplied at initialization, while the kernel and transport enforce on their own. The store retains the latest 100 records plus a count and sends the full snapshot synchronously to listeners. It sanitizes display text and separates an invocation's display text from the correlation key. Reset clears command registries while store and subscribers are process-lifetime. Use per-invocation IDs and an explicit retention decision in the harness. A subscriber that throws propagates synchronously. This and stale diagnostic filters argue for an event API with typed severity/cause, sequence, generation and listener isolation. [Monitor classification](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1344), [Linux observer](repos/anthropics__sandbox-runtime/src/sandbox/linux-violation-monitor.ts:82), [Store and subscribers](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-violation-store.ts:11), [Reason sanitization](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-violation-store.ts:120), [Stderr annotation](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3830)
- **Extensibility.** Public hooks let a trusted caller decide destination or HTTP request permission, supply a native SDK, configure externally owned endpoints, choose launch paths, and integrate credential masking and local trust. The hook contracts encode subtle lifetime and threat assumptions. A per-command allowlist is bound to a client-provided high-entropy invocation ID with explicit registration/unregistration. It should be treated as permission within a session. A harness that needs independent trust domains should use process and network separation that owns independent state. [Public extensions](repos/anthropics__sandbox-runtime/src/index.ts:35), [Per-exec registration](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:613), [Attribution boundary](repos/anthropics__sandbox-runtime/README.md:379), [SDK injection option](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1150)
- **Tests.** The repo mixes pure logic, property tests, argv/profile snapshots and behavioral tests that demand affirmative child startup before accepting a denial as evidence. CI includes architecture and OS matrices plus Docker cap variants, with Bun pinned and native helpers built. Several guarded tests show why a code-path gate matters. Linker prerequisites can make an entire test arm skip, skipped platforms and import failures can make a raw count misleading, and several suites share process-level state. Per-file execution and a baseline identity check make the local results interpretable. [Linux namespace capability probe](repos/anthropics__sandbox-runtime/test/helpers/bwrap-namespace.ts:3), [Positive startup marker](repos/anthropics__sandbox-runtime/test/sandbox/literal-path-entries.test.ts:154), [CI toolchain and tests](repos/anthropics__sandbox-runtime/.github/workflows/integration-tests.yml:427), [Docker CI controls](repos/anthropics__sandbox-runtime/.github/workflows/integration-tests.yml:682)

## 6. Executed tests/experiments and their limitations

The baseline was a Git archive of the pinned revision. Every test process was inside bubblewrap with only loopback and no IPv4 or IPv6 default routes. The system tool directories were read-only. `HOME`, `TMPDIR` and the account/hostname lookup files were synthetic. The first toolchain probe ran an actual nested bwrap with PID, user, proc and network support. A local TCP listener returned the expected loopback marker. Tests used repository fixtures and disposable local payloads. TLS and signing test material was fabricated and local. All managed backend experiments treated the missing SOCKS dependency explicitly.

| Run | Result and what it established |
| --- | --- |
| Offline lockfile and build | The corrected offline install returned `ENOTCACHED`. Integrity checks found 266 of 333 locked tarballs in the inspected npm content store. Exact Zod, Commander, fast-check, pure-rand, TypeScript and Node types were available. The TLS tests used locally cached `node-forge 1.4.2` in place of locked `1.4.0`. Compiler emit made `dist/cli.js` and `dist/proxy-main.js`, with exit 2 because of unavailable types/dependencies. The full lock, strict typecheck and all-code package installation remain unverified. [Package requirements](repos/anthropics__sandbox-runtime/package.json:12), [TypeScript config](repos/anthropics__sandbox-runtime/tsconfig.json:5) |
| Native and standalone artifacts | Rebuilt the Java agent with the packaged script. Built the x86-64 filters using an alternate dynamic generator and a static launcher from the same C sources. The native namespace filter exposed all 15 expected syscall comparisons. The bundled Node and compiled Bun standalone proxy both built and returned version `0.0.83`. [Native build](repos/anthropics__sandbox-runtime/vendor/seccomp/build.ts:20), [Filter generator tests](repos/anthropics__sandbox-runtime/test/sandbox/seccomp-filter-generator.test.ts:58), [Java build](repos/anthropics__sandbox-runtime/vendor/java-proxy-agent/build.ts:53), [Proxy build scripts](repos/anthropics__sandbox-runtime/package.json:15) |
| Unmodified suite, no SOCKS fixture | Discovered 133 files and invoked 130 independently. Bun totals were **1,747 pass, 171 fail, 166 skip**, with 86 file invocations exiting 0. The raw fail count includes startup/import errors. The 44 red files reduce to 43 dependency/fixture-blocked files and one procfs-owner expectation explained in section 7. Passed areas included 157 schema tests, 65 Linux ancestor pin checks, 26 mount-plan checks, 9 Linux relay startup checks, 26 standalone CLI tests, 75 proxy-only tests, 43 decider tests across three files, 21 client-abort tests, and 33 MXC request/probe tests. [Schema suite](repos/anthropics__sandbox-runtime/test/config-validation.test.ts:1), [Linux pin suite](repos/anthropics__sandbox-runtime/test/sandbox/linux-ancestor-pin.test.ts:1), [Proxy-only suite](repos/anthropics__sandbox-runtime/test/sandbox/proxy-only.test.ts:148), [Decider tests](repos/anthropics__sandbox-runtime/test/sandbox/decider-client.test.ts:1), [MXC probe tests](repos/anthropics__sandbox-runtime/test/sandbox/mxc-config.test.ts:270) |
| Fail-on-use import fixture | 13 selected files returned **1,172 pass, 34 fail, 133 skip**. The missing SOCKS module was replaced by an import that throws on factory invocation. The 34 failures went through the deliberate guard. This recovered pure public API, path, Java, HTTP and Windows adapter checks. The 427 passes in `winsrt.test.ts` exercise TypeScript contracts and fake/helper inputs on Linux. The native arms remain skipped. [Public exports assertions](repos/anthropics__sandbox-runtime/test/public-exports.test.ts:85), [Windows tests](repos/anthropics__sandbox-runtime/test/sandbox/winsrt.test.ts:1), [Java composition tests](repos/anthropics__sandbox-runtime/test/sandbox/java-proxy-agent.test.ts:22) |
| Real managed Linux/HTTP with an inert SOCKS factory | 19 files returned **1,039 pass, 0 fail, 90 skip**. The fixture accepts handler registration and fails on SOCKS transport use. Its invocation marker remained absent. Bubblewrap, the native seccomp launcher, socat, HTTP mux/proxy, fixtures, and the production CLI and manager were the real code. Coverage included 28 CLI tests, 16 control-FD tests, 216 glob tests, 15 bwrap-args tests, 16 observer tests, 121 literal-path tests, 191 read-precedence tests and 7 exit cleanup tests. [CLI launch suite](repos/anthropics__sandbox-runtime/test/cli.test.ts:52), [Node and Bun control-FD modes](repos/anthropics__sandbox-runtime/test/control-fd.test.ts:81), [Linux profile tests](repos/anthropics__sandbox-runtime/test/sandbox/linux-bwrap-args-file.test.ts:1), [Cleanup suite](repos/anthropics__sandbox-runtime/test/sandbox/temp-objects-at-exit.test.ts:24) |
| Extra targeted repo cases, same fixture | A filtered command/shell/termination selection from `integration.test.ts` returned 10 pass and 2 skip. The targeted rewrite selection returned 8 pass. The request-target suite returned 508 pass, and TLS manager returned 7 pass. The proxy-port suite printed 9 pass, including one remote-dependent positive with an insufficient assertion. The selected manager-update file recorded 45 pass and 10 fail. All ten misses depended on successfully dialing a public-name origin and are audited below. These groups overlap earlier runs and are reported separately. [Local command tests](repos/anthropics__sandbox-runtime/test/sandbox/integration.test.ts:359), [Proxy port test positive](repos/anthropics__sandbox-runtime/test/configurable-proxy-ports.test.ts:293), [Update fixture](repos/anthropics__sandbox-runtime/test/sandbox/update-config.test.ts:19), [TLS manager tests](repos/anthropics__sandbox-runtime/test/sandbox/tls-terminate-runtime.test.ts:1) |

### Focused lifecycle and transport controls

| Control | Observed result |
| --- | --- |
| Start, execution and reset, both ports external | Equivalent in-flight initialize calls joined, a different in-flight configuration rejected with `initialize_conflict`, and the same external port produced one socket. Real bwrap executed a shell process which made a request through its inner relay to an owned HTTP fixture and returned exact output `start:fixture-response:done` with status 37. A different initialize while ready reused the initial configuration. An overlapping `reset(); initialize(next)` resolved both promises with ready false, enabled true, original config retained, and zero sockets. Serial reset/start installed the intended config and one working socket. Three independent controls on config verified the old config survived an invalid CIDR, a valid update installed a new config, and editing the input after the call did not edit the installed copy. The lifecycle sequence matched on Node 22 and five repeats on Node 24. |
| Cancellation during bridge acquisition | Two real external-port listeners allowed an isolated supervisor to gate each child just before `exec socat`. Cancellation before either child was started and reset after ready left **0 processes, 0 socket paths**. Reset while both children waited at the gate was followed by initialize rejection and **2 live processes, 2 socket paths**, despite a second awaited reset. The result matched three Node 22 runs and one Node 24 run. The controller then terminated and reaped its own children and removed only their temporary directory. |
| Bridge health and initial readiness | Node and Bun both rejected a missing explicit bwrap tool. `getConfig()` still returned the failed attempt and `isSandboxingEnabled()` was true with `waitForNetworkInitialization()` false. Starting a valid session produced a real relay response. After intentionally terminating that owned relay, the socket disappeared and wrap reported the missing bridge while the initialization wait still returned true. A serial reset and new initialize restored traffic through a different socket. |
| Command supervision and control FD | With a valid settings file using both external ports, Node dist and Bun source refused absent/empty/directory settings and closed or write-only control FDs before a command emitted output. With a real anonymous control pipe kept open, invalid JSON was reported, a valid config was applied, the child slot identified `/dev/null`, and child's stdin produced the expected output and status 37. On both engines, directly sending SIGTERM or SIGINT during a running Linux command caused wrapper exit 0 and left zero live processes from the recorded child tree. A command that started a background sleep then exited 37 returned within 184 ms on Node and 55 ms on Bun, with stdio closed. Those durations are observations, not performance thresholds. |
| Policy update inside one running workload | With managed HTTP and the inert SOCKS registration fixture, Node and Bun both ran a real wrapped command sending three separate loopback requests. On one unchanged proxy port, policy swaps led to **403, 200, 403**. Exactly the middle request hit the origin. Both refusals were attributed to the invocation and included in stderr annotation. A new write deny left the running process's three ordinary fixture writes intact. Its next wrapped process received the new policy and could not add another line. |
| Serialized walks and abort | With 6,400 inert directories and both ports external, a second wrap aborted while queued and returned the exact reason. A policy replacement during the first walk led both surviving plans to use the new literal path. Completion order differed on Node and Bun. An independently gated scan was in a real child process when aborted, after which the caller received the reason and the scanner was gone in 2–3 ms. The subsequent wrap succeeded. |
| Mandatory scan deadline, same gated child | With no caller abort, the scanner exited at the internal budget. The wrapper emitted a plan, reaped the subprocess, and logged `ripgrep scan failed` under debug. Measured **10,003 ms on Node and 10,001 ms on Bun**. Switching the scan back to ordinary rg gave a successful wrapper again. The default budget limits helper liveness, while abort prevents a partial plan. |
| Long temp path and repeated host signal | With equivalent external-port settings, a 160-byte Unix socket path failed manager setup after 607–617 ms. A 64-byte path immediately succeeded. Direct socat showed a listening path truncated to the Unix address limit. In a separate long-lived host control, one SIGTERM event consumed the manager's one-shot listener. After initialize again, a second emitted SIGTERM reached the host's own listener, and the manager remained ready. Node and Bun agreed on both controls. |
| Violation store lifetime | Adding 107 records retained the latest 100 with total 107. A deliberately throwing trusted subscriber propagated to the caller after record 108 was stored and before a subsequent subscriber received that notification. The manager's store retained its entry across reset. `clear()` removed it and retained the monotonic total. This exercised the host-side callback contract with inert diagnostics. [Store implementation](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-violation-store.ts:11) |
| Standalone host handoff | A controller passed an already-listening TCP socket and lifeline. Bun source and compiled Bun passed with both Unix socketpair and two true anonymous pipes. Node bundle passed on Unix socketpair under Node 22 and 24. In every successful row the proxy hello came first, it accepted after the valid hello, a 451 refusal made no upstream contact, and a 200 allow hit the owned loopback origin exactly once. Lifeline EOF after readiness exited 0. With Node and two actual pipes, the initial handshake ended with the documented `read ENOTCONN` and exit 2. |
| Startup timeout and lifeline coverage | Node bundle and compiled Bun with a connected decider withheld its hello for 5.2 s. Neither served and both remained live. Lifeline EOF then stopped them with exit 2 because startup had never completed. With an open empty CA pipe, both blocked in the kernel's pipe read. Closing the lifeline while the CA pipe was still open did not complete startup. CA EOF made both exit 2 with a missing PEM error. These tests exercised a trusted supervisor's incomplete startup inputs and used an empty CA pipe. |
| Standalone verdict timeout and recovery | With a valid hello, a legitimate local request waited **5.038 s on Node** and **5.002 s in compiled Bun**, then got HTTP 503 marked `decider_unavailable`. No origin request occurred. A late allow for that ID made no change. The next request received 200 with one upstream hit. Decider EOF after readiness exited 0 on both with the decider close reason on stderr. This distinguishes per-request timeout from startup and transport shutdown. |

This evidence covers the Linux kernel and runtime versions in section 1. It covers the shipped wrapper's behavior with a locally rebuilt x86-64 helper, the standalone HTTP proxy, and substantial real managed HTTP and filesystem paths. Real SOCKS negotiation, the Docker/root/no-CAP_SYS_ADMIN matrix, external network behavior, native macOS, native Windows, and real MXC are outside the executed boundary. The SSH suites that need a network peer or account provisioning were left out. Several original integration tests hardcode a public service. There was no route to such services. Local replacements preserved the assertions about runtime policy and ownership without assigning external-service behavior to SRT.

## 7. Measurement audit for every negative or surprising result, including alternate commands or code-path checks used to rule out setup mistakes

| Observation | Alternate check, root cause and disposition |
| --- | --- |
| First npm command exited before package resolution | Passing `/dev/null` as both user and global npm config caused npm to reject duplicate config file identity. Reran with an empty `HOME`, no inherited environment, no duplicate flags, no install scripts and offline-only cache. The corrected run reached tarball selection and failed `ENOTCACHED` for `yaml 2.8.3`. Checked package-lock digests directly and looked for alternate local cache entries. `@pondwader/socks5-server 1.0.10`, `node-forge 1.4.0`, the matching forge types and pinned Bun declarations were absent. The result is an offline dependency gap. |
| Strict TypeScript compile and test typecheck failed | The first compiler run reported missing module declarations plus implicit any errors for Bun globals and SOCKS callbacks. Locally cached Bun declarations `1.3.14` eliminated the Bun-global errors but lacked the pinned signatures and left unavailable forge/SOCKS types. Full test typechecking also had callback inference diagnostics on this substitute profile. On-disk emitted JS, executable Node/Bun proxy bundles and explicit runtime version checks distinguish emission from a verified strict build. No inference about locked source typechecking follows. [Dependencies](repos/anthropics__sandbox-runtime/package.json:26), [Bun-specific FD API](repos/anthropics__sandbox-runtime/src/sandbox/proxy-only.ts:306) |
| Production seccomp build failed and generator tests skipped | The header was present and shared libseccomp linked. `gcc -print-file-name=libseccomp.a` returned the bare string, proving the static archive was missing and explaining both build failure and the test gate. A dynamic build of the unmodified generator produced x86-64 BPF, verified 15/15 comparisons, and a static build of the unmodified launcher accepted it. Cross generation refused to write the aarch64 filter because installed libseccomp 2.6.0 did not name `open_tree_attr` for that architecture. The code and stock test expect complete cross output or a named refusal. This is neither a Linux x86-64 launch failure nor live aarch64 validation. [Generator flags](repos/anthropics__sandbox-runtime/vendor/seccomp/build.ts:20), [Generator readiness probe](repos/anthropics__sandbox-runtime/test/sandbox/seccomp-filter-generator.test.ts:58), [Other-architecture contract](repos/anthropics__sandbox-runtime/test/sandbox/seccomp-filter-generator.test.ts:161) |
| Java build initially found no `javac` | The synthetic PATH originally omitted the local JDK. Read-only mounting the installed JDK and adding it to PATH recovered the stock build with JDK 21.0.13. Result was 12,142 bytes, SHA-256 `6d3f71201e5f061eb59e00c90a68176b0438244f441970e7eff05926b241da2a`. In the managed fixture the JVM integration suite passed 15 with 3 platform skips. [Build lookup](repos/anthropics__sandbox-runtime/vendor/java-proxy-agent/build.ts:31), [Sandboxed JVM test](repos/anthropics__sandbox-runtime/test/sandbox/java-proxy-agent.test.ts:151) |
| One native expectation saw procfs owner 65534 where it expected 0 | Both executable-mode sanity arms launched correctly. The test equates a non-dumpable process with visible root ownership. The isolated user namespace did not map outer root. A separate process called `PR_SET_DUMPABLE` and read it back. Dumpable 1 yielded owner 1000 and dumpable 0 yielded owner 65534, matching `overflowuid`. A post-fork ownership sample for both helper modes `0755` and `0111` gave 65534. This rules out a slow setup and an unintended dumpable helper in this fixture. The native test assumes root maps visibly in its procfs. [Exact test assertion](repos/anthropics__sandbox-runtime/test/sandbox/execute-only-binary.test.ts:135), [Helper dumpability transition](repos/anthropics__sandbox-runtime/vendor/seccomp-src/apply-seccomp.c:781) |
| Namespace probe differed with invocation | A direct unprivileged net-only unshare returned EPERM. A user+network namespace probe and actual nested bwrap with a new proc mount were successful. The suite's real Linux arms depend on the latter kernel capability surface. Windows, macOS and native Docker combinations required their own environments. Rust 1.98.1 was installed locally, but its stdlib directories covered Linux and Linux musl only. No native Windows execution result was inferred from the TypeScript adapter tests. [Namespace test probe](repos/anthropics__sandbox-runtime/test/helpers/bwrap-namespace.ts:3), [CI target matrix](repos/anthropics__sandbox-runtime/.github/workflows/integration-tests.yml:19), [Cargo toolchain](repos/anthropics__sandbox-runtime/rust-toolchain.toml:1) |
| Baseline CLI, control-FD, rules-through-links, glob and manager tests reported failures | The first group of raw failures included direct module-load errors, child processes with no startup marker, cleanup hooks that ran after missing imports, and packaged-layout copy assertions on the absent dependency. Direct CLI invocation reported module-not-found before config loading. The fail-on-use fixture let pure interfaces, module-backed fixtures, and test doubles exercise their real code without pretending to provide SOCKS. The next fixture allowed registration and raised on transport use. 19 rerun files then passed, including both CLI and FD suites, glob, and cross-runtime path rules. Neither managed fixture supplies real SOCKS guarantees. [CLI import path](repos/anthropics__sandbox-runtime/src/cli.ts:4), [SOCKS import](repos/anthropics__sandbox-runtime/src/sandbox/socks-proxy.ts:2), [Rule start predicate](repos/anthropics__sandbox-runtime/test/sandbox/rules-through-links-on-every-runtime.test.ts:93) |
| Ten selected `update-config` misses and one exterior proxy false positive | The first auth test's 407 subassertion passed. Its authenticated public-name CONNECT positive failed. The strict allowlist test also stopped at the initial public-name CONNECT. The remaining failures were successful CONNECT or body assertions for `example.com`. The no-route namespace made the positive oracle depend on an impossible dial. The local replacement proved policy changes with named response status, upstream count, and unchanged port. A separate authenticated, local CONNECT check yielded 407 without auth, 200 with auth to the allowed endpoint and 403 to the off-list fixture, with zero ask calls in strict mode, on Node and Bun. The external port repo test asserts curl exit 0 and absence of a policy-denial phrase. Its external fixture converts a dial failure to a 502. A synthetic loopback 502 yielded curl exit 0 and HTTP 502, while `--fail` yielded exit 22 and HTTP 502. The local relay control also proved a positive byte round trip. [CONNECT oracle](repos/anthropics__sandbox-runtime/test/sandbox/update-config.test.ts:37), [Auth subassertions](repos/anthropics__sandbox-runtime/test/sandbox/update-config.test.ts:72), [Public origin body oracle](repos/anthropics__sandbox-runtime/test/sandbox/update-config.test.ts:1577), [External proxy 502 and assertions](repos/anthropics__sandbox-runtime/test/configurable-proxy-ports.test.ts:342) |
| Proxy handoff began with bad-hello errors | The first Python fixture omitted the required `deniedDomains` array. Compared it with the schema and checked-in hello usage. Adding the empty array let five transport/artifact pairs complete startup and both requests. The remaining Node/two-pipe failure occurred before the decider could send its hello. The same binary working over a socketpair, Bun accepting the same OS pipes, and repeated Node 22/24 results isolate the FD adoption limitation. [Hello schema](repos/anthropics__sandbox-runtime/src/sandbox/decider-client.ts:155), [FD adapter](repos/anthropics__sandbox-runtime/src/sandbox/proxy-only.ts:302), [Documented Node transport](repos/anthropics__sandbox-runtime/docs/srt-proxy.md:50) |
| Startup watchdog harness initially stopped on an unexpected wait-channel name | The probe first expected `pipe_read`. This kernel reported `anon_pipe_read`. Accepting both known names let the probe observe a kernel-blocked read before it closed the lifeline. The two read/write operations and process-exit observations were also measured separately. The sync PEM read and the order in which CLI installs the lifeline match the observed trusted-input limitation. [CA read](repos/anthropics__sandbox-runtime/src/sandbox/proxy-only.ts:282), [CLI setup order](repos/anthropics__sandbox-runtime/src/proxy-cli.ts:131) |
| Abort ordering varied by engine | The aborted queued request consistently completed first with its own reason. The two successful wrappers completed in different orders, and both used the new policy. The walk gate is FIFO for the protected walk. An interrupted stale attempt rejoins behind current waiters, and the lock releases before the native scan/command assembly completes. Completion order is not a scheduling or execution promise. [Walk gate](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:2654), [Requeue](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:2760), [Early release](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:2925) |
| Manager restart and pending resource ownership | Used the same immutable settings shape, functioning local listeners, an ordinary command, and an adapter that could not create a SOCKS listener. Checked both status accessors, filesystem socket counts, and real process liveness. Ran serial controls and an alternate Node version. The precise distinction is between promise/state publication and live resource ownership. Dependency precheck rejection and explicit termination of an owned relay provided separate controls showing what the status getters actually represent. [Setter before dependency checking](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1255), [Bridge ownership gap](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1826), [Enabled predicate](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1872), [Reset await](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3733) |
| A passing stock cancellation test left a socket | In a fresh temp directory for each case, three runs of the stock CLI interrupt-during-initialize case passed their original assertions and each left one socket. Three runs of the interrupt-during-wrap sibling passed and each left zero. The stock oracle covers reported interrupt, child admission and CLI status. Resource acquisition and adoption explain the residue. The separately gated manager test measured live children as well as path existence before cleaning its own children. [Stock cancellation assertions](repos/anthropics__sandbox-runtime/test/cli.test.ts:311), [Synchronous exit cleanup scope](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:470), [Bridge adoption](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1826) |
| Raw TLS tests left temporary trust bundle directories | Repeated four suites in fresh temp roots. `mitm-ca` left 3 bundle directories, `tls-terminate-in-process` left 16, `request-target-forwarding` left 1, and `temp-objects-at-exit` left 0. All passed and none left a `ca.key` in those roots. The direct test fixtures create their own CA objects. For example, the in-process suite closes HTTP resources but does not dispose the CA objects constructed in its setup. The manager exit suite exercises actual manager ownership. The aggregate residue alone cannot establish a leak in the managed teardown path. [Test-owned CA creation](repos/anthropics__sandbox-runtime/test/sandbox/tls-terminate-in-process.test.ts:72), [CA bundle allocation](repos/anthropics__sandbox-runtime/src/sandbox/mitm-ca.ts:429), [Manager-exit oracle](repos/anthropics__sandbox-runtime/test/sandbox/temp-objects-at-exit.test.ts:109) |
| Shell and platform skips | `zsh` was absent from PATH. The test logs explicitly mark the two zsh exit-status cases skipped and two older shell-selection cases return early while being tallied as passes. The Bash cases ran using the same namespace. `bwrap` reported successful user, PID, proc and network setup. macOS/Windows gates and the generator build gate account for other reported skips. [Old shell gate](repos/anthropics__sandbox-runtime/test/sandbox/integration.test.ts:393), [Portable exit-status gate](repos/anthropics__sandbox-runtime/test/sandbox/integration.test.ts:1417), [CI OS matrix](repos/anthropics__sandbox-runtime/.github/workflows/integration-tests.yml:19) |
| Scan deadline versus AbortSignal | Used the same PID readiness marker to exclude measuring before the child started. In both engines the deadline terminated the helper, preserved wrapping, and warned. An explicit abort propagated the exact reason and returned no wrapper. The same directory and ordinary rg were the recovery control. Code accepts complete lines already received on a non-abort failure. This is intentional degraded scanning rather than a failed abort. [Process timeout](repos/anthropics__sandbox-runtime/src/utils/ripgrep.ts:28), [Partial listing and abort check](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:604) |
| Long `TMPDIR` and signal handler consumption | Used an owned, writable temp root, the same ports and the same Unix-socket client path with a shorter root as positive control. Direct socat diagnostics showed truncated binding even though the intended long path did not appear. The same manager startup failure on Node and Bun localizes it to Unix socket path handling. The mux has a separate short-path strategy and was bypassed in this comparison. For the signal control, a host listener counted two events and kept the process alive, while `process.listenerCount` fell from 2 to 1 and explicit reset still worked. This isolates the one-shot signal semantics from process exit and socket failures. [Linux socket construction](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:1513), [Mux socket path](repos/anthropics__sandbox-runtime/src/sandbox/mux-proxy.ts:77), [Signal registration guard](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:460) |
| Appendix replay moved four raw passes to failures | The replay created a private workspace with `umask 077` and initially inherited that mask into the suite. The replay total was 1,743 pass, 175 fail and 166 skip. A line-by-line comparison localized all four changes to two Linux tests. In the first, the host fixture was created at `0600` instead of the expected `0644`. In the second, the requested placeholder `0444` became `0400`. Direct mode creation verified both masks. Retesting just those files under `0077` reproduced 3 and 1 failures. Under `0022` they returned 19 pass and 38 pass with 6 skips, matching the baseline. Managed rerun counts remained 1,039/0/90. The appendix now sets the mode explicitly inside its test launcher and keeps the temp container private. [Mode comparison](repos/anthropics__sandbox-runtime/test/sandbox/linux-file-above-deny.test.ts:202), [Placeholder mode expectation](repos/anthropics__sandbox-runtime/test/sandbox/linux-unmakeable-mount-point.test.ts:425) |

## 8. Post-mortem: design pressures, accumulated tradeoffs, likely failure modes, and the highest-leverage improvements

The checkout is shallow, so design history beyond the pinned snapshot is unavailable. The likely pressures are visible in today's contracts. SRT needs low setup friction for local tools, minimal extra privilege on Linux and macOS, a durable Windows path for host ACL mutations, integration with existing applications, and enough compatibility across Node and Bun to serve as a reusable substrate. The implementation spends complexity on translating a common policy into each platform's disparate primitives. Examples include literal-vs-pattern path disambiguation, control-FD handling conditioned on the runtime, user namespace/capability probes, and compatibility with JVM and SSH client conventions. This is valuable complexity. The missed responsibility is a common ownership protocol for the runtime's own objects. [Platform interfaces](repos/anthropics__sandbox-runtime/src/index.ts:53), [Control fd interpretation](repos/anthropics__sandbox-runtime/src/cli.ts:95), [Native namespace compatibility](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:1423), [Credential and proxy env adapter](repos/anthropics__sandbox-runtime/src/sandbox/java-proxy-agent.ts:1)

The principal incident sequence is a cancellation or overlapping restart during asynchronous host relay startup/teardown. In the cancellation sequence, relay creation happens with local ownership and then crosses an await. Cancellation advances the generation, blocks publication and triggers reset. The cleanup code discovers only published bridges. It therefore rejects correctly and can leave resources owned by neither the old awaiting request nor the manager state. In the restart sequence, reset advances generation but old readiness remains observable until teardown finishes. Initialization sees it and returns. A generator that prevents stale publication is necessary and still insufficient when the acquisition and release mechanisms do not own the same objects. Recovering by serial reset and init works when the previous manager state owns the resources that need disposing. It cannot retire a relay pair which was never adopted. [Initialize gate](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1170), [Generation check](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1246), [Bridge handoff](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1826), [Reset memory clearing](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3793)

| Priority | Change | Acceptance criterion |
| --- | --- | --- |
| P0 | Represent the session as explicit idle, starting, ready, stopping and failed states under one transition owner. Register every acquired resource in a local disposable scope before its next await. Transfer the whole scope only when publishing ready. Give teardown a single awaited completion promise and invalidate ready before closing any resource. | No fulfilled initialize without a ready generation. In all gated startup cancellation phases the owner closes its relay process(es), socket, monitor and temporary resources. Parallel resets join. Serial and overlapping reinitialization either reach the requested generation or surface a typed conflict. |
| P0 | Introduce an invocation lifecycle API and retain the current wrapper methods as lower-level compatibility entry points. A prepared invocation should be releasable before spawn. The supervisor should own the process tree or SDK handle with explicit cancel, wait, exit/status and dispose. Per-command lists, mount artifacts and argument descriptors should have an identity-based owner. | Failed spawn and abandoned plans release their leases. A double cleanup cannot decrement a sibling's ownership. Reset either waits for or explicitly retires active commands. Launch cancellation is distinguishable from a successful exit. |
| P1 | Publish immutable, validated config with a revision and classify update fields by scope. Return an applied/will-apply-on-wrap/restart-required result, including proxy endpoint generation. Reflect bridge liveness in readiness and provide a typed failed or degraded event with a path to restart under the host's supervision. Apply an explicit Unix-socket path budget and report backend setup and scan degradation on the normal caller-facing diagnostics path. | A rejected config leaves the running generation unchanged. New requests and children can report the revision that applied. A dead relay immediately changes health. A long temp path selects a safe alternate or fails with its cause. A control-FD writer can tell which rules took effect, and a host can reject partial mandatory scan results when required. |
| P1 | Bound outstanding startup and decision work per stage. Add a hello deadline, bounded async CA input that observes the lifeline, plain accepted-connection budgets, and a guaranteed waiter-release path after body/callback cancellation. Separate intended shutdown from dependency loss in structured status. | Ready is emitted only after a complete configuration. Closing the lifeline terminates pre-ready work within a documented bound. Timed-out and cancelled requests return their reservations. The harness can choose the correct restart policy without parsing stderr. |
| P1 | Add hermetic package/test fixtures for the supported offline data plane and deterministic fault barriers around every startup transition. Gate Linux project safety and mount-argument behavior on real namespace probes, and distinguish kernel UID mapping from a process's dumpability. Replace public-origin positives with local destinations and assert response status, body and upstream observations. | A cached install or a test closure is sufficient to reproduce the essential tests without the internet. Positive tests cannot pass off a proxy or origin error page. A red fixture names the missing package, capability or incompatible runtime, and separates dependency failures from product failures. |
| P2 | Extract a typed filesystem/policy enforcement plan and an effects adapter. Contain event-listener exceptions, validate observation messages at the boundary, mark diagnostics as observations, and expose truncation and generation. Keep critical native release cases in their platform matrix. | Plan diffs and ownership can be inspected independently. Event consumers cannot interrupt the proxy path merely by throwing. Windows ACL maintenance retains its install/session separation and tested recovery order. |

The measures distinguish software boundaries from harness responsibilities. In the current API an embedding harness can serialize initialize/reset, treat readiness as an explicitly observed state, supervise and reap its own process trees, and set a launch deadline for a standalone proxy. The lifecycle work above would make those responsibilities expressible and testable without assuming undocumented timing. [Public manager contract](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3922), [Proxy lifeline contract](repos/anthropics__sandbox-runtime/docs/srt-proxy.md:13), [Windows DB recovery](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/state_db.rs:1780)

## 9. Evidence appendix with local file/line references and commands

### Source trace

| Boundary | Checkpoints for an independent review |
| --- | --- |
| Admission to start | [Config discriminants](repos/anthropics__sandbox-runtime/src/utils/config-loader.ts:14), [CLI defaults and refusal](repos/anthropics__sandbox-runtime/src/cli.ts:377), [FD usability check](repos/anthropics__sandbox-runtime/src/cli.ts:95), [Manager startup guard](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1170), [Async dependency interface](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:2014) |
| Session state transitions | [Module state](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:175), [Setup rollback](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1213), [Local proxy and bridge ownership](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1767), [Config updates](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3507), [Reset and release](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3682) |
| Plan to work | [Serialization and abort](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:2667), [Reconciliation check](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:2952), [Linux compiler snapshot](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:2095), [POSIX and Windows argv](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3082), [CLI execution](repos/anthropics__sandbox-runtime/src/cli.ts:621), [Go/no-go MXC probe](repos/anthropics__sandbox-runtime/src/sandbox/mxc-sandbox-utils.ts:286) |
| Process stop to cleanup | [CLI early cancellation](repos/anthropics__sandbox-runtime/src/cli.ts:498), [CLI child exit](repos/anthropics__sandbox-runtime/src/cli.ts:595), [Bridge stop deadline](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3581), [Mount cleanup counter](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:1163), [Seccomp parent and reaper](repos/anthropics__sandbox-runtime/vendor/seccomp-src/apply-seccomp.c:791), [Windows job handle](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/job.rs:31) |
| Network admission to data plane | [Mux accepts](repos/anthropics__sandbox-runtime/src/sandbox/mux-proxy.ts:159), [HTTP CONNECT cancellation and auth](repos/anthropics__sandbox-runtime/src/sandbox/http-proxy.ts:676), [Host filter and callback](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:774), [Address lookup](repos/anthropics__sandbox-runtime/src/sandbox/resolved-address-guard.ts:255), [Request callback and streaming body](repos/anthropics__sandbox-runtime/src/sandbox/request-filter.ts:195), [Parent CONNECT route](repos/anthropics__sandbox-runtime/src/sandbox/parent-proxy.ts:327) |
| Standalone orchestration | [Protocol integration](repos/anthropics__sandbox-runtime/docs/srt-proxy.md:67), [FD adoption](repos/anthropics__sandbox-runtime/src/sandbox/proxy-only.ts:302), [Hello/ready/close](repos/anthropics__sandbox-runtime/src/sandbox/proxy-only.ts:223), [Frame, startup and fatal errors](repos/anthropics__sandbox-runtime/src/sandbox/decider-client.ts:265), [Verdict timeout](repos/anthropics__sandbox-runtime/src/sandbox/decider-client.ts:372), [Body budget and handoff](repos/anthropics__sandbox-runtime/src/sandbox/decider-client.ts:483) |
| Windows persistence | [Runner creation](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/logon.rs:447), [Child lockdown](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/launch.rs:132), [Native profile lock](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/state_db.rs:919), [Process-identity recovery](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/state_db.rs:1864), [WFP install](repos/anthropics__sandbox-runtime/vendor/srt-win-src/src/wfp.rs:625) |
| Events and tests | [Violation event tail](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-violation-store.ts:11), [Observer transport](repos/anthropics__sandbox-runtime/src/sandbox/linux-violation-monitor.ts:157), [CLI interrupt case](repos/anthropics__sandbox-runtime/test/cli.test.ts:311), [FD harness exit/drain](repos/anthropics__sandbox-runtime/test/control-fd.test.ts:36), [Temporary resource cleanup](repos/anthropics__sandbox-runtime/test/sandbox/temp-objects-at-exit.test.ts:59) |

### Reproduce the isolated test environment

Run from the review workspace. The toolchain paths reflect this machine's local installs. Alternate installations can supply the same binaries. All artifact-producing commands in this appendix target the archive and disposable test directory.

```bash
set -eu
checkout="$PWD/repos/anthropics__sandbox-runtime"
pin=0bbebed0aa9a8e628dc4df8bc30293550a1988eb
date -u +%FT%TZ
test "$(git -C "$checkout" rev-parse HEAD)" = "$pin"
test -z "$(git -C "$checkout" status --porcelain=v1 --untracked-files=all)"
saved_umask=$(umask)
umask 077
review=$(mktemp -d "$PWD/.srt-reproduce.XXXXXXXX")
mkdir -p "$review"/{tree,home,tmp,logs,etc,cache}
git -C "$checkout" archive "$pin" | tar -xf - -C "$review/tree"
printf '127.0.0.1 localhost\n::1 localhost\n' > "$review/etc/hosts"
printf 'hosts: files dns\npasswd: files\ngroup: files\n' > "$review/etc/nsswitch.conf"
printf 'root:x:0:0:root:/review/home:/bin/bash\nreview:x:1000:1000:review:/review/home:/bin/bash\nnobody:x:65534:65534:nobody:/:/bin/false\n' > "$review/etc/passwd"
printf 'root:x:0:\nreview:x:1000:\nnobody:x:65534:\n' > "$review/etc/group"
umask "$saved_umask"
node_tree=$HOME/.local/share/mise/installs/node/22.23.1
jdk_tree=$HOME/.local/share/mise/installs/java/21.0.13+9.0.LTS
bun_exec=$HOME/.bun/bin/bun
cache_tree=$HOME/.npm/_cacache

srtbox() (
  umask 022
  bwrap --unshare-all --die-with-parent --ro-bind /usr /usr \
    --symlink usr/bin /bin --symlink usr/lib /lib --symlink usr/lib /lib64 \
    --dev /dev --proc /proc --ro-bind "$review/etc" /etc --tmpfs /tmp \
    --bind "$review" /review --ro-bind "$node_tree" /node \
    --ro-bind "$jdk_tree" /jdk --ro-bind "$bun_exec" /review/bun \
    --clearenv --setenv PATH /review:/node/bin:/jdk/bin:/usr/bin \
    --setenv JAVA_HOME /jdk --setenv HOME /review/home \
    --setenv TMPDIR /review/tmp --chdir /review/tree "$@"
)

srtbox -- /bin/bash -eu -c '
  ip -brief link
  test -z "$(ip route show default)"
  test -z "$(ip -6 route show default)"
  bwrap --unshare-pid --unshare-user --unshare-net --cap-drop ALL \
    --ro-bind / / --proc /proc /bin/true
  node --version
  bun --version
  getconf ARG_MAX
  ulimit -n
'
# Observed only lo, nested bwrap status 0, Node 22.23.1, Bun 1.4.2,
# ARG_MAX 2097152, open-FD soft limit 524288.
if srtbox --ro-bind "$cache_tree" /review/cache/_cacache -- /bin/bash -c '
  npm_config_cache=/review/cache npm ci --offline --ignore-scripts --no-audit --no-fund
'; then
  printf '%s\n' 'Exact offline dependencies installed'
else
  printf 'Offline lock install returned %s (reviewed cache: 1 / ENOTCACHED)\n' "$?"
fi
```

### Recover cached dependencies and native helpers

The extraction below selects explicit packages, checks their digest against the lock or cache entry and keeps the installed alternate version visible. The read-only cache was mounted only for these dependency checks. An already populated exact offline mirror can replace this step and eliminate the managed SOCKS test fixture.

```bash
srtbox --ro-bind "$cache_tree" /review/cache/_cacache -- /bin/bash -s <<'BOX'
set -eu
node --input-type=module - <<'JS'
import fs from 'node:fs';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
const packages = JSON.parse(fs.readFileSync('package-lock.json', 'utf8')).packages;
const cache = '/review/cache/_cacache';
const require = createRequire('/node/lib/node_modules/npm/package.json');
function localBlob(integrity) {
  const [alg, digest] = integrity.split('-');
  const hex = Buffer.from(digest, 'base64').toString('hex');
  return [alg, digest, [cache,'content-v2',alg,hex.slice(0,2),hex.slice(2,4),hex.slice(4)].join('/')];
}
function extract(name, integrity) {
  const [alg, digest, path] = localBlob(integrity);
  if (!fs.existsSync(path)) return false;
  const tarball = fs.readFileSync(path);
  if (crypto.createHash(alg).update(tarball).digest('base64') !== digest) throw Error(name);
  const dir = 'node_modules/' + name;
  fs.mkdirSync(dir, {recursive:true});
  if (spawnSync('tar',['-xz','--strip-components=1','-C',dir],{input:tarball,stderr:'inherit'}).status) {
    throw Error('extract ' + name);
  }
  console.log(name, JSON.parse(fs.readFileSync(dir+'/package.json','utf8')).version);
  return true;
}
const pinned = Object.values(packages).filter(p => p.integrity);
console.log('cached', pinned.filter(p => fs.existsSync(localBlob(p.integrity)[2])).length, 'of', pinned.length);
for (const name of ['commander','zod','fast-check','pure-rand','typescript','@types/node',
    'undici-types','node-forge','@types/node-forge','@types/bun','bun-types','@pondwader/socks5-server']) {
  const entry = packages['node_modules/' + name];
  if (!extract(name,entry.integrity)) console.log(name, entry.version, 'absent');
}
const alt = await require('cacache').get.info(cache,
  'make-fetch-happen:request-cache:https://registry.npmjs.org/node-forge/-/node-forge-1.4.2.tgz');
if (alt && !fs.existsSync('node_modules/node-forge/package.json')) extract('node-forge',alt.integrity);
JS
mkdir -p /review/seccomp-work vendor/seccomp/x64
bun vendor/java-proxy-agent/build.ts
gcc -O2 -Wall -Wextra -o /review/seccomp-work/gen vendor/seccomp-src/seccomp-unix-block.c -lseccomp
for rule in unix namespaces; do
  /review/seccomp-work/gen "/review/seccomp-work/$rule.bpf" x86_64 "$rule"
done
python3 - <<'PY'
from pathlib import Path
work = Path('/review/seccomp-work')
body = ['#if defined(__x86_64__)']
for symbol, name in [('unix_block_bpf','unix'), ('namespace_block_bpf','namespaces')]:
    data = (work / (name + '.bpf')).read_bytes()
    body += ['static const unsigned char ' + symbol + '[] = {',
             ',\n'.join('    ' + ', '.join(f'0x{v:02x}' for v in data[i:i+8])
                        for i in range(0,len(data),8)), '};']
body += ['#else', '#error "these filters were generated for another architecture"', '#endif']
(work / 'unix-block-bpf.h').write_text('\n'.join(body)+'\n')
PY
gcc -static -O2 -Wall -Wextra -I/review/seccomp-work \
  -o vendor/seccomp/x64/apply-seccomp vendor/seccomp-src/apply-seccomp.c
strip vendor/seccomp/x64/apply-seccomp
sha256sum vendor/seccomp/x64/apply-seccomp vendor/java-proxy-agent/srt-proxy-agent.jar
node node_modules/typescript/bin/tsc --pretty false || test -s dist/cli.js
test -s dist/proxy-main.js
npm_config_offline=true npm run build:srt-proxy
npm_config_offline=true npm run build:srt-proxy-node
dist/srt-proxy --version
node dist/srt-proxy.mjs --version
BOX
```

The launcher fingerprint from this build was `5e96a385f07134560994a251ca9f0de2aaebf9daf4df6f4ce3d6f2eba1f5c8e4`. The native filter had 42 instructions. Replacing `node_tree` with the local `24.22.2` directory before invoking `srtbox` repeats the Node comparison. The TypeScript step above deliberately uses the emitted JavaScript for experiments and retains the diagnostics in its output. [Stock seccomp build](repos/anthropics__sandbox-runtime/vendor/seccomp/build.ts:20), [TypeScript output options](repos/anthropics__sandbox-runtime/tsconfig.json:5)

### Suite passes and isolation profiles

The unmodified archive source runs without a SOCKS fixture for the first pass. The tests run one file per Bun process to bound liveness failures and avoid cross-file mock contamination. This reproduces the raw baseline counts. TLS code takes the alternate forge version disclosed in section 6.

```bash
srtbox -- /bin/bash -s <<'BOX'
set -u
mkdir -p /review/logs/suite
find test -name '*.test.ts' | sort > /review/logs/test-files
while IFS= read -r test; do
  case "$test" in
    test/docker-weak-sandbox.test.ts|test/sandbox/integration.test.ts|test/sandbox/git-over-ssh.test.ts) continue;;
  esac
  logfile="/review/logs/suite/$(printf '%s' "$test" | tr / _).log"
  timeout --kill-after=3s 30s bun test "$test" > "$logfile" 2>&1
  rc=$?
  printf '%s\t%s\t' "$test" "$rc"
  awk '/^ [[:digit:]]+ (pass|fail|skip|todo)/ {printf "%s ",$0} END{print ""}' "$logfile"
done < /review/logs/test-files | tee /review/logs/suite-results.tsv
BOX
```

For the fail-on-use profile, place a module in the archived `node_modules/@pondwader/socks5-server` with `{"name":"@pondwader/socks5-server","type":"module","exports":"./index.js"}` as `package.json` and one throwing `createServer()` export. Run `test/public-exports.test.ts` and the following `test/sandbox/` files separately with `bun test FILE`: `check-dependencies`, `own-files`, `resolved-address-guard`, `linux-bwrap-args-file`, `linux-violation-monitor`, `request-rewriting`, `request-target-forwarding`, `mxc`, `winsrt`, `java-proxy-agent`, `default-write-paths` and `proxy-env-vars` (each suffix `.test.ts`).

Use this inert registration fixture for the HTTP/CLI phase. The marker makes a mistakenly exercised SOCKS path detectable independently of an assertion result. The trigger remains an error.

```bash
srtbox -- /bin/bash -s <<'BOX'
set -u
mkdir -p node_modules/@pondwader/socks5-server /review/logs/http-managed
printf '%s\n' '{"name":"@pondwader/socks5-server","type":"module","exports":"./index.js"}' \
  > node_modules/@pondwader/socks5-server/package.json
cat > node_modules/@pondwader/socks5-server/index.js <<'JS'
import { appendFileSync } from 'node:fs';
export function createServer() {
  return {
    setAuthHandler() {},
    setRulesetValidator() {},
    setConnectionHandler() {},
    _handleConnection(socket) {
      appendFileSync('/review/logs/http-managed/socks-invoked','SOCKS handler called\n');
      socket.destroy();
      throw new Error('SOCKS not part of the HTTP-only test fixture');
    },
  };
}
JS
for f in \
  test/{cli,control-fd}.test.ts \
  test/sandbox/{allow-read,command-text-registry,default-write-paths,filesystem-disabled,glob-expand,java-proxy-agent,linux-bridge-burst,linux-bwrap-args-file,linux-violation-monitor,literal-path-entries,mandatory-deny-paths,read-deny-glob,read-list-precedence,rules-through-links-on-every-runtime,stale-mount-point,temp-objects-at-exit,wrap-with-sandbox}.test.ts
do
  logfile=/review/logs/http-managed/$(basename "$f").log
  timeout --kill-after=3s 50s bun test "$f" > "$logfile" 2>&1
  rc=$?
  printf '%s\t%s\t' "$f" "$rc"
  awk '/^ [[:digit:]]+ (pass|fail|skip|todo)/ {printf "%s ",$0} END{print ""}' "$logfile"
done | tee /review/logs/http-managed-results.tsv
test ! -e /review/logs/http-managed/socks-invoked
BOX
```

### Reproduce the lifecycle controls

The following short control uses both external-port overrides. It performs no outbound dial beyond the owned fixture. With both overrides, the entire managed mux factory is skipped. An alternative to the inert registration fixture is an import which throws from `createServer()`, as in the original lifecycle probes.

```bash
srtbox -- /bin/bash -s <<'BOX'
set -eu
timeout --kill-after=2s 12s node --input-type=module - <<'JS'
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import fs from 'node:fs/promises';
import { SandboxManager as s } from './dist/index.js';
const tmp = await fs.mkdtemp('/review/tmp/rows-');
process.env.TMPDIR = tmp;
const origin = createServer((req,res) => res.end('fixture-response'));
origin.listen(0,'127.0.0.1');
await once(origin,'listening');
const port = origin.address().port;
const config = {network:{allowedDomains:[],deniedDomains:[],httpProxyPort:port,socksProxyPort:port},
                filesystem:{allowWrite:[tmp],denyWrite:[],denyRead:[]}};
const next = {...config,network:{...config.network,strictAllowlist:true}};
const sockets = async () => (await fs.readdir(tmp)).filter(f=>f.endsWith('.sock')).length;
try {
  const first = s.initialize(config);
  const same = s.initialize(structuredClone(config));
  await assert.rejects(s.initialize(next),{code:'initialize_conflict'});
  await Promise.all([first,same]);
  assert.equal(await sockets(),1);
  const cmd = "printf 'start:'; curl --silent --show-error --max-time 2 --noproxy '' --proxy http://127.0.0.1:3128 http://proxy-fixture.invalid/; printf ':done'; exit 37";
  const spec = await s.wrapWithSandboxArgv(cmd);
  const child = spawn(spec.argv[0],spec.argv.slice(1),{env:spec.env,cwd:tmp});
  let out = '';
  child.stdout.on('data',d=>{out+=d;});
  child.stderr.resume();
  assert.deepEqual(await once(child,'close'),[37,null]);
  assert.equal(out,'start:fixture-response:done');
  s.cleanupAfterCommand();
  await s.initialize(next);
  assert.equal(s.getConfig(),config);
  await Promise.all([s.reset(),s.initialize(next)]);
  console.log('overlap',{ready:await s.waitForNetworkInitialization(),enabled:s.isSandboxingEnabled(),
    sockets:await sockets(),old:s.getConfig()===config});
  await s.initialize(next);
  console.log('serial',{ready:await s.waitForNetworkInitialization(),sockets:await sockets(),next:s.getConfig()===next});
} finally {
  await s.reset();
  origin.closeAllConnections();
  await new Promise(resolve=>origin.close(resolve));
  await fs.rm(tmp,{recursive:true,force:true});
}
JS
BOX
```

Observed `overlap {ready:false,enabled:true,sockets:0,old:true}` and `serial {ready:true,sockets:1,next:true}`. For the pending-acquisition control, this is the complete gate and assertion sequence. The two test endpoints and both relays belong to the process under test. It cleans up the retained relay children after measuring them.

```bash
srtbox -- /bin/bash -s <<'BOX'
set -eu
cat > /review/bridge-gate <<'PY'
#!/usr/bin/python3
import os, pathlib, sys, time
sock = sys.argv[1].split(':',1)[1].split(',',1)[0]
folder = pathlib.Path(sock).parent
(folder / f'child-{os.getpid()}').write_text(sock)
deadline = time.monotonic() + 2
while not (folder / 'release').exists():
    if time.monotonic() > deadline:
        sys.exit(75)
    time.sleep(.002)
os.execv('/usr/bin/socat',['/usr/bin/socat', *sys.argv[1:]])
PY
chmod 0700 /review/bridge-gate
cat > /review/bridge-control.mjs <<'JS'
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { createServer } from 'node:net';
import { once } from 'node:events';
import { setTimeout as delay } from 'node:timers/promises';
import { SandboxManager as s } from '/review/tree/dist/index.js';
const a = createServer(c=>c.end()), b = createServer(c=>c.end());
for(const server of [a,b]) {server.listen(0,'127.0.0.1'); await once(server,'listening');}
const work = await fs.mkdtemp('/review/tmp/gate-');
process.env.TMPDIR = work;
const config = {
  network:{allowedDomains:[],deniedDomains:[],httpProxyPort:a.address().port,socksProxyPort:b.address().port},
  filesystem:{allowWrite:[],denyWrite:[],denyRead:[]},socatPath:'/review/bridge-gate'
};
const phase = process.argv[2];
const children = async () => (await fs.readdir(work)).filter(f=>f.startsWith('child-')).map(f=>Number(f.slice(6)));
const sockets = async () => (await fs.readdir(work)).filter(f=>f.endsWith('.sock'));
const alive = pid => {try {process.kill(pid,0); return true;} catch(e) {if(e.code==='ESRCH') return false; throw e;}};
async function until(condition) {
  const deadline = performance.now()+1500;
  while(performance.now()<deadline) {if(await condition()) return; await delay(2);}
  throw Error('fixture gate not reached');
}
try {
  const starting = s.initialize(config).then(()=>'ready',e=>e.message);
  if (phase!=='before-spawn') {
    await until(async ()=>(await children()).length===2);
    assert.equal((await sockets()).length,0);
  }
  if (phase!=='after-ready') await s.reset();
  await fs.writeFile(work+'/release','');
  const result = await starting;
  if (phase==='after-ready') assert.equal(await s.waitForNetworkInitialization(),true);
  await s.reset();
  console.log(phase,{result,ready:await s.waitForNetworkInitialization(),
    pids:(await children()).filter(alive).length,sockets:(await sockets()).length});
} finally {
  for (const pid of await children()) if (alive(pid)) process.kill(pid,'SIGTERM');
  await until(async()=>(await children()).every(pid=>!alive(pid)));
  await fs.rm(work,{recursive:true,force:true});
  for(const server of [a,b]) await new Promise(resolve=>server.close(resolve));
}
JS
for phase in before-spawn after-ready before-ready; do
  timeout --kill-after=2s 10s node /review/bridge-control.mjs "$phase"
done
BOX
```

Observed before-spawn and after-ready rows `0/0` for relay processes and socket paths. Observed before-ready row `2/2` and `initialize() was cancelled by reset()`. The test can also check the actual CLI symptom using a new `TMPDIR` for each invocation of `bun test test/cli.test.ts -t 'while the sandbox is being initialized'` and `-t 'while the command is being wrapped'`. The first run path asserts that the command never begins. Count remaining Unix socket files separately with `find "$TMPDIR" -maxdepth 1 -type s`. [CLI tests](repos/anthropics__sandbox-runtime/test/cli.test.ts:311), [Manager process kill](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3592), [Generation-gated adoption](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:1826)

### Reproduce the standalone FD handoff

Run the compiled and source variants against the same kernel descriptors and owned loopback origin. The socketpair path and two unidirectional pipes are separate controls. The Node row's documented startup refusal is visible as a raw result. The current outputs are in section 6.

```bash
srtbox -- /bin/bash -s <<'BOX'
set -eu
timeout --kill-after=2s 24s python3 -u - <<'PY'
import http.server, json, os, select, socket, struct, subprocess, threading, time

variants = {
    'bun-source': ['bun', 'src/proxy-main.ts'],
    'bun-compiled': ['dist/srt-proxy'],
    'node-bundle': ['node', 'dist/srt-proxy.mjs'],
}

def close(fd):
    try:
        os.close(fd)
    except OSError:
        pass

def read_exact(fd, length, deadline):
    data = b''
    while len(data) < length:
        left = deadline - time.monotonic()
        if left <= 0 or not select.select([fd], [], [], left)[0]:
            raise TimeoutError(f'frame stalled at {len(data)}/{length}')
        piece = os.read(fd, length - len(data))
        if not piece:
            raise EOFError('decider fd closed')
        data += piece
    return data

def read_frame(fd, secs=2):
    deadline = time.monotonic() + secs
    return json.loads(read_exact(fd, struct.unpack('>I', read_exact(fd, 4, deadline))[0], deadline))

def write_frame(fd, obj):
    data = json.dumps(obj, separators=(',', ':')).encode()
    msg = struct.pack('>I', len(data)) + data
    assert os.write(fd, msg) == len(msg)

upstream_hits = []
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        upstream_hits.append(self.path)
        self.send_response(200)
        self.send_header('Content-Length', '10')
        self.end_headers()
        self.wfile.write(b'fixture-ok')
    def log_message(self, *args):
        pass

origin = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=origin.serve_forever, daemon=True).start()

def run(name, transport):
    life_in, life_out = os.pipe()
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    addr = listener.getsockname()
    if transport == 'socket':
        peer, server = socket.socketpair()
        child_in = child_out = server.detach()
        read_fd = write_fd = peer.detach()
        opts = ['--decider-fd', str(child_in)]
    else:
        child_in, write_fd = os.pipe()
        read_fd, child_out = os.pipe()
        opts = ['--decider-in', str(child_in), '--decider-out', str(child_out)]
    p = subprocess.Popen(
        variants[name] + opts + ['--listen-fd', str(listener.fileno()), '--lifeline-fd', str(life_in)],
        pass_fds=tuple(set((child_in, child_out, listener.fileno(), life_in))),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    for fd in {child_in, child_out, life_in}:
        close(fd)
    listener.close()
    try:
        try:
            hello = read_frame(read_fd)
            assert hello == {'t': 'hello', 'proto': 1}, hello
            write_frame(write_fd, {'t': 'hello', 'proto': 1, 'allowedDomains': ['localhost'], 'deniedDomains': []})
            if not select.select([p.stderr], [], [], 3)[0]:
                raise TimeoutError('ready did not resolve')
            ready = p.stderr.readline().decode().strip()
            if not ready.startswith('srt proxy: serving fd'):
                raise RuntimeError(ready)
        except (TimeoutError, EOFError, RuntimeError) as e:
            try:
                p.wait(timeout=1)
            except subprocess.TimeoutExpired:
                p.kill()
            err = p.communicate(timeout=2)[1].decode().strip()
            print(name, transport, 'startup', type(e).__name__, repr(str(e)), 'exit', p.returncode, repr(err))
            return
        before = len(upstream_hits)
        host = f'localhost:{origin.server_port}'
        responses = []
        for path, verdict in (('/refuse', {'action': 'deny', 'status': 451, 'reason': 'fixture verdict'}),
                              ('/allow', {'action': 'allow'})):
            with socket.create_connection(addr, timeout=2) as request:
                request.sendall(f'GET http://{host}{path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n'.encode())
                req = read_frame(read_fd)
                assert (req['t'], req['method'], req['host'], req['path']) == ('req', 'GET', 'localhost', path), req
                assert len(upstream_hits) == before, upstream_hits
                write_frame(write_fd, {'t': 'verdict', 'id': req['id'], **verdict})
                data = b''
                while (chunk := request.recv(4096)):
                    data += chunk
                code = int(data.split(b' ')[1])
                responses.append(code)
                if verdict['action'] == 'allow':
                    assert data.endswith(b'fixture-ok'), data
        close(life_out)
        p.wait(timeout=3)
        err = p.communicate(timeout=2)[1].decode().strip()
        assert responses == [451, 200] and upstream_hits[before:] == ['/allow'], (responses, upstream_hits)
        assert p.returncode == 0 and 'lifeline closed' in err, (p.returncode, err)
        print(name, transport, 'hello+ready', responses, 'origin', upstream_hits[before:], 'exit', p.returncode, repr(err))
    finally:
        for fd in {life_out, read_fd, write_fd}:
            close(fd)
        if p.poll() is None:
            p.kill()
            p.wait(timeout=2)

try:
    for name in variants:
        for transport in ('socket', 'pipe'):
            run(name, transport)
finally:
    origin.shutdown()
    origin.server_close()
PY
BOX
```

For the startup-deadline control, keep the decider socketpair and lifeline open after reading SRT's hello. Withhold the peer hello for 5.2 s and check that there is no serving message and the process is still running. Close the lifeline writer and check exit 2. With a valid peer hello, withholding the first verdict instead produced a 503 in about 5 s, with zero origin hits. Sending that request's allow afterwards left the next local request able to succeed with its own allow. Closing the decider's write half then stopped a ready proxy with exit 0. For the separate CA startup control, pass an empty read pipe as `--ca-fd`, keep its write end open, and check `/proc/PID/wchan` before closing the lifeline. The kernel reported `anon_pipe_read` here. Close the CA writer to see the invalid-PEM exit immediately. [Proxy frame protocol](repos/anthropics__sandbox-runtime/docs/srt-proxy.md:67), [FD/lifeline order](repos/anthropics__sandbox-runtime/src/proxy-cli.ts:131), [Per-verdict timer](repos/anthropics__sandbox-runtime/src/sandbox/decider-client.ts:385)

### Other experiment recipes

- **Procfs oracle.** In the same box, create two ordinary Python children which call `ctypes.CDLL(None).prctl(4, mode, 0, 0, 0)` for modes 1 and 0. Have each print the readback via `prctl(3, 0, 0, 0, 0)` before waiting. Compare `stat -c %u /proc/PID/environ` with `cat /proc/sys/kernel/overflowuid`. Copy `vendor/seccomp/x64/apply-seccomp` to two fresh paths, use mode `0755` and `0111`, and invoke each with `/bin/sleep 2`. Wait for a nonempty `/proc/PID/task/PID/children` to confirm post-fork, then stat each helper's environ. The wrapper test itself can be repeated with `bun test test/sandbox/execute-only-binary.test.ts`. [Fork-stage test](repos/anthropics__sandbox-runtime/test/sandbox/execute-only-binary.test.ts:66), [Native dumpability](repos/anthropics__sandbox-runtime/vendor/seccomp-src/apply-seccomp.c:781)
- **Bridge health.** In the external-port control above, call `getLinuxHttpSocketPath()` after initialize, connect to it with `net.connect(path)`, drain the return from the local fixture, then terminate the owned socat PID. Identify that child via `/proc/self/task/PID/children` and its matching socket path in `/proc/CHILD/cmdline`. Wait for the socket to disappear, compare `waitForNetworkInitialization()` with a wrap of `true`, then run `await reset(); await initialize(config)`. Confirm the new path and loopback response. An explicit missing `bwrapPath` before the first startup separately exercises configured-but-unready admission. [Bridge readiness check](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:1608), [Wrap refusal](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:3704)
- **Control-FD timing and signal ownership.** The stock `bun test test/control-fd.test.ts` covers inherited pipes, Node and Bun, stdin, early fd refusal and Docker-independent isolation. For a subprocess-only control supply the two external ports and a JSON settings file. In Python use `os.pipe()` and `subprocess.Popen(..., pass_fds=(read_fd,))`, pass `--control-fd` with that number, and keep the writer open across child exit. Write an invalid JSON line then a valid full config. Verify stderr indicated each, child stdout contains its stdin result, and status 37 is preserved. Separately wait on a running marker before sending SIGTERM or SIGINT. Capture the process tree under `/proc` before the signal and check after stdio close. [Existing control-FD fixture](repos/anthropics__sandbox-runtime/test/control-fd.test.ts:116), [CLI signal forwarding](repos/anthropics__sandbox-runtime/src/cli.ts:722)
- **Live policy with an actual origin result.** In the managed HTTP profile start an owned origin on `127.0.0.1:0`. Wrap a command using `curl --noproxy '' --proxy "$HTTP_PROXY" -o /dev/null -w '%{http_code}'` to the origin, once per line sent over the command's stdin. Set strict allowlist, then no allowed hosts, allow literal origin authority, and explicit deny of that authority before successive requests. Expect 403/200/403 and one origin call. Keep appending to a disposable file under an allowed write root, add a deny on it together with the final network update, and check the running child can finish its writes while a newly wrapped child gets the new deny. Confirm two events under the caller-assigned command ID. [Atomic update](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3507), [Output annotation](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:3830), [Existing local TLS integration](repos/anthropics__sandbox-runtime/test/sandbox/tls-terminate-runtime.test.ts:1)
- **Planner queue and scan abort.** Start the external-port profile under a scratch cwd with 6,400 empty directories and a `denyRead` glob walking them. Start one wrap, yield once with `setImmediate`, start a second wrap with an AbortSignal and a third wrap. Create an inert file and publish a new literal deny for it. Abort the middle wrap and check the exact error, then verify both surviving wrappers mention the new path and each relinquishes its cleanup unit. For the scan arm, set `ripgrep.command` to a fixture which records its PID then execs sleep. Abort after seeing the new PID, wait for that PID to leave, and verify the next wrap using real rg succeeds. [Yield interval](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-utils.ts:1282), [Scan cancellation](repos/anthropics__sandbox-runtime/src/utils/ripgrep.ts:20), [Mandatory scan gate](repos/anthropics__sandbox-runtime/src/sandbox/linux-sandbox-utils.ts:604)
- **Alternative scan and signal controls.** Let the same inert scanner sleep for 15 s without caller abort and enable `SRT_DEBUG`. Measure process exit and wrapper resolution at about 10 s with the warning. For the signal test register a counting listener with `process.on('SIGTERM', listener)`, initialize the external-port profile, and emit SIGTERM as a process event. After readiness clears, initialize again and emit it a second time. Readiness then remains and the process's only signal listener is the host's. Await explicit reset at the end. [Scanner process deadline](repos/anthropics__sandbox-runtime/src/utils/ripgrep.ts:28), [Manager signal hook](repos/anthropics__sandbox-runtime/src/sandbox/sandbox-manager.ts:490)

## 10. Execution policy

This is one serial review of one pinned repository. The README lists nine numbered sections and gives a separate `Execution policy` heading. The report uses that heading as section ten. Test work took place in disposable directories under the specified workspace. The evaluation report is the retained deliverable. No repository files or evaluation queue entries were edited. [Evaluation protocol](./README.md:1)

The appendix setup, build, baseline and managed matrices, lifecycle controls and standalone FD harness were replayed. The only changed raw baseline outcomes traced to inherited umask, and the normalized-mask retest recovered all four. The structural check validated the numbered headings, shell blocks and local source anchors.

The final cross-runtime control-FD rerun on Node 24 returned 16 pass, 0 fail. The local shallow Git object graph passed `git fsck --no-reflogs --no-dangling` before the final HEAD and status check. [Control-FD tests](repos/anthropics__sandbox-runtime/test/control-fd.test.ts:81)
