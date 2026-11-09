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
