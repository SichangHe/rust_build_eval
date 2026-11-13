# Results
(authored by agents unless marked 🧑)

Full tables with CIs: `data/analysis.txt`. Raw samples: `data/raw_{A,B,C}.csv`.

## Method
- toolchain `1.97.1-x86_64-unknown-linux-gnu` via `RUSTUP_TOOLCHAIN`; per-repo `Cargo.lock`; `cargo fetch` once, then `--offline --locked`
- isolated `CARGO_HOME` with no `config.toml` (registry/git symlinked); every config is passed by `--config`/`RUSTFLAGS`; `cargo build -v` logs of the warm-up edit were kept and checked (flags, linker)
- linker verified per binary via `readelf -p .comment`: baseline/split/etc = `LLD 22.1.6`, `bfd` = system ld (no tag), `mold` = `mold 3.0.0`; std dynamic verified via `libstd-*.so` in `readelf -d` (`dynrpath`, `depdylib` only)
- workloads (copies, originals untouched): `agent_managers` (single crate, 207 pkgs in lock), `teamtype--teamtype` (574), `rustls--rustls` (`-p rustls-examples`, 325), `webapp` (small axum service from `seamless_rust_setup/experiments/compile_speed`, 89)
- trial = fresh dirs, cold build, no-op build, warm-up edit, 4 leaf + 4 wide edits (appends a dead function), sizes, run binary with a clean env, `cargo test --no-run` (rep 0 only)
  - leaf edit = bin crate file; wide edit = the library crate everything uses (`teamtype` lib.rs, `rustls` lib.rs); n/a for single-crate `agent_managers` and `webapp`
- 5 trials per (repo, config) => 5 cold builds, 20 edit samples per edit type, in shuffled interleaved order (seeded)
- two lanes ran concurrently, each pinned with `taskset` to 16 disjoint CPUs (lane A: teamtype + pair test; lane B: the rest); same repo always in one lane
- load1 per sample in the CSV: min 17, median 37, max 58
- statistics: median, 95% bootstrap CI (10000 resamples); ratio = bootstrap CI of median(cfg)/median(`split`)
- scale-down: `risc0` skipped (own toolchain, guest builds); `rustls` built only `-p rustls-examples`; 5 trials not 10 trials (edit samples >= 20)

## Configs
- `baseline`: Cargo defaults (debug=2 everywhere)
- `dbg`: `dev.debug="line-tables-only"` + `dev.package."*".debug=false`
- `split`: `dbg` + `split-debuginfo="unpacked"`, default linker (rust-lld); the reference for ratios
- `bfd`: `split` + `-Clinker-features=-lld` (system GNU ld.bfd via gcc)
- `mold`: `split` + `-Clinker-features=-lld -Clink-arg=-B<dir with ld->mold>`
- `dynrpath`: `split` + `RUSTC_WRAPPER` shim adding `-Cprefer-dynamic -Clink-arg=-Wl,-rpath,<target-libdir>,-rpath,$ORIGIN/deps`
- `depdylib`: `dynrpath` + facade `dylib` crate holding all third-party deps (webapp only; feature `dylib`, `use deps_dylib as _`)
- `builddir`: `split` + `build.build-dir` on another disk; `builddir_shm`: same on `/dev/shm`
- `pair_shared` / `pair_sep`: cold build of `agent_managers` after `teamtype` with one shared build-dir vs separate ones

## Findings
Medians; `x` = ratio vs `split` with 95% CI. Edit times are leaf edits unless noted.

Debug info (baseline -> `dbg`) is the big win for size, and a moderate one for speed.
- target dir size: baseline/dbg = 1.71 (agent_managers), 1.90 (rustls), 2.45 (teamtype), 1.73 (webapp); `cargo test --no-run` dir for teamtype 10.6 GB -> 3.3 GB
- binary: teamtype 462 MB -> 117 MB, agent_managers 113 -> 36 MB, rustls example 27 -> 13 MB
- edit: baseline vs split x1.10 [1.07,1.12] agent_managers, x1.09 [1.05,1.14] rustls, x1.34 [1.31,1.36] teamtype, x1.16 [1.12,1.31] webapp
- cold: baseline x1.09 / x1.17 / x1.31 / x1.06 (same order), all CIs exclude 1
- `split-debuginfo=unpacked` on top of `dbg`: speed unchanged (all CIs include 1 or are within 3%); binary -7% (agent_managers), -3% (teamtype), -5% (rustls); dir size within 1%

Linker.
- bfd is much slower than rust-lld: edit x2.86 [2.80,2.94] agent_managers, x2.30 [2.22,2.37] rustls, x5.22 [5.13,5.33] teamtype (wide x4.09), x3.14 [3.03,3.26] webapp; cold x1.16-1.50
- mold vs rust-lld depends on repo: teamtype edit x0.78 [0.75,0.80] (wide x0.84 [0.82,0.86]), agent_managers x0.93 [0.90,0.98], webapp x0.98 [0.96,1.03] (no difference), rustls x1.12 [1.07,1.15] (slower; wide x1.00)
- mold binaries are larger: x1.13 agent_managers, x1.32 teamtype, x1.09 rustls, x1.04-1.08 target dir

Dynamic std with user rpath (`dynrpath`).
- all binaries ran in a clean env (no `LD_LIBRARY_PATH`), `cargo test --no-run` succeeded everywhere: the rpath shim solves the loader problem on this machine/user
- edit time unchanged: x1.00-1.02, all CIs include 1
- binary: -14% agent_managers, -35% rustls, -4% teamtype, -24% webapp; target dir -2.5% to -6%
- cost: binaries need this user's toolchain `libstd-*.so` at the rpath path; not portable to other machines or after a toolchain update

Dependency dylib (`depdylib`, webapp only, under the same controlled conditions).
- edit x0.79 [0.78,0.82] vs `split`; 431 ms vs 550 ms for `dynrpath` (x0.78)
- app binary 1.9 MB (x0.11) but the dylib moves bytes: target dir x1.04; cold x1.07 [1.02,1.23]
- needs project source changes; only helps edits to the final app, not to deps; one workload only

Build-dir relocation and sharing.
- `builddir` vs `split`: all metrics within CI of 1 (edit x0.99-1.04); total bytes unchanged, they just move: `target/` shrinks to 7% (agent_managers), 22% (rustls), 10% (teamtype) of the total
- `builddir_shm` (tmpfs): no gain, and worse for rustls leaf edit x1.45 [1.25,1.53] and no-op builds x1.4-2.5; unexplained
- shared build-dir across two repos: no reuse. Second repo cold x0.96 [pair_shared vs pair_sep CIs overlap]; build dir 2.08 GB vs 0.49 + 1.6 GB separate, i.e. no dedup

`cargo test --no-run` is one sample per config, noisy; teamtype: baseline 103 s vs split 72 s, others 69-80 s.

## Recommended global config
```toml
[build]
build-dir = "{cargo-cache-home}/build/{workspace-path-hash}"   # optional: location only, speed/size neutral
[profile.dev]
debug = "line-tables-only"
split-debuginfo = "unpacked"      # small binary win, harmless
[profile.dev.package."*"]
debug = false
```
- keep default rust-lld; never GNU bfd
- mold: opt-in per project with big binaries (teamtype-like); not a safe global default (slower on rustls, larger binaries)
- do not make `dynrpath` or `depdylib` global: no edit speedup (dynrpath), non-portable binaries, source changes (depdylib)
- do not use `/dev/shm` for build-dir; sharing one build-dir across repos saves nothing

## Threats to validity
- shared busy host (load 17-58 on 128 logical CPUs, 2 SMT threads per core); pinning limits but does not remove interference; the two lanes also shared memory bandwidth, disk and page cache
- 5 trials per cell; the 20 edit samples come from 5 trials, so they are correlated and bootstrap CIs on edits are too narrow; size CIs are near-degenerate because sizes are almost deterministic
- one machine, one toolchain (1.97.1), one disk pair, warm page cache; "cold" = no target dir, sources and registry cached
- edit = appending a dead function; real edits differ (generic/inlined code, macros)
- 4 workloads of one language/ecosystem; mold vs lld results vary by repo, so one more repo could flip the aggregate
- `cargo test --no-run` n=1; tests were not run, only binaries `--help`/`--version`/`--once`
- run time of binaries (startup, dynamic loading cost) not measured
- lane A's first `test --no-run` failed because the copy missed an untracked-by-copy file (`daemon_race_tests.rs`); lane C reran teamtype with 1 trial per config to get the test metrics (analysis uses lane C only for those)
- `depdylib` only on webapp, built by an earlier agent's facade design; `rustc_wrap.sh` adds flags to all crates incl. build scripts
- shared `~/.cargo/registry` is symlinked (not read-only): `cargo fetch` for rustls/webapp added crates to it before the runs
- `mold` came from a nix store path; the unified setup is not measured on other mold versions

# Round 2: transparent dependency dylibs, and other options
(authored by agents) Tables: `data/analysis_round2.txt`; raw: `data/raw_{D1,D2,E,F}.csv`. Round 1 above is unchanged. Same harness (`scripts/run.py`), all configs interleaved in one shuffled run, ratios vs `split` of the same round (not round 1 numbers). Reps: 5 trials per cell (teamtype 4: lanes D1+D2 x2), 20 edit samples; lanes pinned to disjoint 16-CPU ranges, load1 55-95. Each lane edits a private copy of the sources.

## `dyndeps`: zero-edit dependency dylibs (works, but does not pay)
Mechanism (`scripts/dyndeps_wrap.py`, via `RUSTC_WRAPPER`; no project edits, no Cargo.toml change):
- every registry/git library crate is compiled as `lib` + `dylib` (extra `--crate-type dylib`, same `-Cextra-filename`, so `libX-hash.so` sits beside `libX-hash.rlib`)
- each consumer gets `-Cprefer-dynamic`, rpath to the toolchain libdir and to `target/debug/deps`, and a second `--extern name=libX.so` beside every `.rlib/.rmeta`
- cargo starts dependents when it sees the `metadata` artifact, but the `.so` is not linked yet: the wrapper buffers rustc's stderr and releases the `metadata` notice only at exit (the dylib twin costs wall time on the critical path)
- fallbacks to plain static build: proc-macros, build scripts, workspace crates, crates with `static` native libs (`aws-lc-sys`: a dylib hides the bundled C symbols, link fails), crates where `dylib` fails (`#![no_std]`)
- all 4 workloads: cold build ok, binary runs in a clean env, `cargo test --no-run` ok, every test binary loads (`--list`) in a clean env (0 failures); there is no source/manifest change. So "needs source changes" was an artifact of the facade design, not necessary.

Measured (ratio vs `split`, 95% CI of ratio of medians):
- leaf edit: agent_managers x1.066 [1.03,1.10], rustls x1.094 [1.03,1.15], teamtype x0.983 [0.92,1.03], webapp x0.945 [0.92,0.99]; teamtype wide x0.963 [0.93,1.00], rustls wide x1.055 [0.99,1.10]. So no real speedup (up to 9% slower, at best 5% faster)
- cold build: x1.47 [1.34,1.54] agent_managers, x1.36 rustls, x1.44 teamtype, x1.77 webapp (every CI > 1): twin dylib builds plus held-back pipelining
- app binary: x0.81 agent_managers, x0.65 rustls, x0.86 teamtype, x0.44 webapp; target dir x1.05-1.08 (agent_managers 1.07, rustls 0.97). Total deployable bytes grow because the `.so` files move bytes (as noted for `depdylib`)
- `test --no-run` n=1 per cell: x0.95-1.18

Why the earlier `depdylib` won (x0.79) but this loses: one facade `.so` = 1 link input and 1 dynamic object; `dyndeps` makes 90-570 `.so` files, so the linker/loader work per edit does not shrink (lld handles many rlibs fast, and `--gc-sections` over rlibs is cheap) while symbol-versioned dynamic relocation of 100s of libs adds work. Explanation is an inference; I did not profile `ld.so` or link time per config. Linker time share in the edit loop (`-Ztime-passes`, agent_managers, one edit): link 0.31 s of 1.07 s total; the rest is frontend/codegen/incremental-cache writing of the one crate, which dependency dylibs cannot touch.

A facade (one `.so`) from the resolved graph is still possible from a wrapper (generate it into the target dir and rewrite `--extern`), but needs `use deps_dylib as _` for the linker to keep the `.so` (the earlier needed edit) or a link-arg `-l`; not attempted: all dyndeps results show the linking share is small, so the ceiling (webapp x0.79 at best; webapp's link share is the highest of the four) is low.

## Other options (all with zero project edits)
Edit time (leaf), ratio vs `split` [95% CI]:
- `wild` linker (0.10.0 via `-B` shim, like mold): teamtype x0.658 [0.63,0.69], webapp x0.747 [0.73,0.79], agent_managers x0.878 [0.84,0.91], rustls x0.831 [0.80,0.87]; wide edits teamtype x0.710, rustls x0.868; cold x0.96-0.98 (CI includes 1 for 3 of 4); binary -1% to -2%; dir -0.2% to -0.6%. Beats mold in round 1 on every repo (rustls: mold x1.12 vs wild x0.83), but mold/wild were not run in the same round
- `threads8` (`-Zthreads=8`, nightly flag via `RUSTC_BOOTSTRAP`): edit x0.98-1.06 (no gain), but cold x0.655 [0.62,0.69] webapp, x0.838 agent_managers, x0.905 teamtype, x0.924 rustls; no size change
- nightly 1.101 (2026-10-22) vs stable `split_nightly`: edit x0.83-0.93 [CIs below 1 for 4 of 4: agent_managers .896-.979, rustls .797-.877, teamtype .799-.876, webapp .880-.960], target dir x0.73-0.84. Toolchain version, not a flag: confounded with 1.97.1 stable
- `cranelift` (nightly backend): vs `split_nightly` edit x1.001 [0.95,1.03] agent_managers, x0.984 [0.96,1.04] rustls, x0.989 [0.95,1.05] teamtype, x0.949 [0.91,0.98] webapp: no gain over nightly alone; binary x1.13-1.54 bigger; cold within CI of 1
- `noembed` (`-Zno-embed-metadata`): edit within CI of 1 except teamtype wide x0.92; target dir x0.73-0.85 on stable (equal to the nightly toolchain's dir shrink, so likely nightly cargo turns it on by default; not separated)
- `nodebug` (`debug=false`): binary x0.58 (rustls), x0.76 (webapp), x0.79 (agent_managers), x0.93 (teamtype); dir x0.90-0.97; edit x0.94-1.00; loses line numbers in backtraces
- `noinc` (incremental off): edit x1.2-3.5 slower, dir -7% to -22%. Never.
- `sccache`: cold miss x1.02-1.28 (slower); full-hit cold (same project, fresh target dir) is x0.38 webapp, x0.50 rustls, x0.62 agent_managers, x0.69 teamtype of `split` cold (point ratios of medians, no CI); edit x0.97-1.03 (no gain); dir unchanged. Only helps rebuilds after `cargo clean`/across projects with identical deps
- `combo_stable` = `dyndeps` + `wild`: edit teamtype x0.654 [0.63,0.70], webapp x0.788 [0.78,0.83], agent_managers x0.840 [0.81,0.94], rustls x0.917; cold x1.3-1.9; binary x0.43-0.84. Not better than `wild` alone for edits (teamtype 0.658), worse cold
- `combo_boot` = + `-Zthreads=8`: edit teamtype x0.699, webapp x0.870; no better than `wild` alone

Not measured: `hint-mostly-unused` (nightly; docs say it only helps crates with huge, mostly unused APIs, and `package."*"` is discouraged: https://blog.rust-lang.org/inside-rust/2025/07/15/call-for-testing-hint-mostly-unused), TPDE backend (planned 2027 per the Rust 2026 Fast Builds roadmap), `-Zshare-generics` (already default for debug), `panic=abort`/`strip` (change test/backtrace behaviour).

## Deployable globally (transparent, stable, no project edits)
- same recommended config as round 1, plus a linker choice: `wild` for edit speed (x0.66-0.88 vs lld, 4/4 repos, CIs below 1), via `-Clink-arg=-B<dir with ld->wild>` (needs a `-fuse-ld`-able driver trick, `-Clinker-features=-lld`, and a pinned wild binary; its README says to use GNU ld/lld for production, so keep it dev-profile only)
- `debug=false` for the deps already there; `nodebug` for the app only if backtrace line numbers are not needed (artifact size lever, 7-42% smaller binary)
- do not ship `dyndeps`, `-Zthreads` (nightly flag, only cold gains), `noinc`, `sccache` (unless cold rebuilds are common)
- `cranelift`/nightly: nightly only, left as opt-in

## Threats to validity (round 2)
- same as round 1 (shared busy host, load 55-95, 5 trials, correlated edit samples so CIs are too narrow, one machine, appended-dead-fn edits, `test --no-run` n=1 and test binaries only loaded not run)
- `wild`: one binary version (0.10.0, built earlier from the sibling repo's tools dir), wild is not a drop-in on all link lines; not tested on all binary kinds (cdylib, proc macros, `-Clink-self-contained`)
- nightly/stable configs differ in toolchain AND cargo; `noembed` on stable used `RUSTC_BOOTSTRAP=1` (unsupported)
- a `noembed` rustls binary timed out (>20 s) once under load before the harness fix; rerun then passed; the fix records timeouts as `run_rc=124` and `run.py` resumes finished trials
- `dyndeps` correctness beyond these 4 workloads is unknown: crates with `links`/build-script-emitted `-l` flags, `#[no_mangle]`/`#[global_allocator]` in deps, duplicated statics across dylibs (each `.so` has its own copies of generics' statics; singleton/TLS issues possible) are untested; tests were only loaded, not executed
- sccache config used a fresh per-trial cache dir, so "hit" times are best case
- the `wild` and `dyndeps` ratios above were computed against a `split` run in the same shuffled round, but statistics ignore pairing

# Round 3: wild correctness

Question: does wild 0.10.0 (x86_64 release tarball, SHA-256 `641265506a7c06cfb03181b8916ab663ec8407855db6d4db7f8450667d105283`) break anything that the default linker (rustc 1.99.1 stable, rust-lld 23.1.1) does not?

## Method
- `scripts/wild_tests.sh REPO`: `git archive HEAD` copy under `/tmp`, isolated `CARGO_HOME` without config, separate target dir per linker, `cargo build` then `cargo test --workspace --offline --locked --no-fail-fast -j8` (dev profile, `RUST_BACKTRACE=1`), run under `nice` and `taskset` on 16 CPUs of a loaded host
- wild is set through `RUSTFLAGS`, so build scripts and proc macros are also linked by wild (checked with `readelf -p .comment`: `Linker: Wild 0.10.0` vs `Linker: LLD 23.1.1`)
- compared: sorted per-test outcome lines (`test X ... ok|FAILED|ignored`)
- `fixture/` (own workspace: proc-macro derive, build script, cdylib, binary with a `#[should_panic]` and a real panic) with `fixture/check.sh default|wild`: tests, panic backtrace with `file:line`, gdb breakpoint on `main.rs:11` plus `bt`, `addr2line` on a symbol, cdylib loaded with `ctypes` and called
- rust-analyzer 1.95.0 `analysis-stats .` with the toolchain proc-macro server, build scripts run by cargo with the same `RUSTFLAGS`, so proc macros and build-script output come from wild-linked binaries

## Results
- `agent_managers` (f8a48aa): 192 tests ok, 0 failed with both linkers, outcomes identical (186+6 passed, 2 ignored)
- `teamtype` (f422ecf): 168 ok, 6 failed with both, outcomes identical; the 6 are the nvim e2e tests, failing identically under both because they need `./target/debug/teamtypev` at a fixed path; rerunning `-p e2e-tests` with that path linked: 6/6 pass with both linkers
  - first run, a different test `peer::recovery_tests::tunnel_survives_blocked_relay_without_sync_peers` failed once under wild (`Error: deadline has elapsed`) and passed under default; rerun of the whole suite with wild passed it. Not reproduced, timing test on a host with load average ~75; only one sample each, so a wild-specific flake is not excluded
- `rustls` (2b55f63f, `--exclude rustls-ci-bench`, which needs valgrind headers for `crabgrind`): 799 passed, 3 failed with both; the 3 are `raw_key_openssl_interop` tests (openssl tests, same failures with both linkers, cause not investigated). Per-test outcomes identical after discarding interleaved log lines
- fixture: all checks give the same output with both linkers except addresses; backtrace frames, gdb source lines and `addr2line` resolve; proc macro, build script, cdylib work
- rust-analyzer: `fixture`, `teamtype`, `agent_managers` give identical statistics with both linkers (panics 0; unresolved types `??ty` 0; same failed-MIR/const-eval counts, which come from r-a itself), proc-macro expansion worked in the fixture (derive-generated `S::answer()` resolved, build-script constant `GEN` evaluated)

## Limits
- one wild version, x86_64 only (aarch64 binary checksum recorded but not run); one machine
- default and wild each ran the suites once (plus the reruns above)
- tests do not prove runtime equivalence of every binary; `-Clink-self-contained`, static/musl targets, `--target` cross builds, and `cdylib`s beyond the fixture were not tested
- wild's README still advises lld/GNU ld for production, hence dev profile only
