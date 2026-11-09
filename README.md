# rust_build_eval
(authored by agents unless marked 🧑)

Controlled evaluation of Cargo settings for artifact size and compile speed.

🧑 "Do all your evals more scientifically and include them in a dedicated repo. This would be like its own research"
🧑 "Do the artifact size + compilation speed first"
🧑 "I also mentioned dynamic linking for compilation speed (but also artifact size)"
🧑 goal: a transparent Rust build setup, "Just as a rapper around everything. And then the user would not even need to notice it. Most of the time."
🧑 "for dynamic linking rpath problem, maybe we require a setup that has a user-specific rpath that the shims would use? Then those programs would run?"

## Layout
- `scripts/run.py`: harness (`run.py LANE LO-HI REPOS REPS`); config table inside
- `scripts/rustc_wrap.sh`: `RUSTC_WRAPPER` shim for `dynrpath` / `depdylib`
- `scripts/analyze.py`: medians, bootstrap CIs, ratios vs `split`
- `data/raw_*.csv`: raw long-format samples (lane,repo,config,rep,metric,value,load1)
- `results.md`: results and threats to validity

## Reproduce
- scratch: `EVAL_OUT` (required env var; put it on `/`, not the repo disk) holds repo copies, `cargo_home`, mold shim, builds
- `cargo_home` has no `config.toml` (isolates from the global one) and symlinks `registry`/`git` from `~/.cargo`
- `moldbin/ld` -> mold binary (`nix shell nixpkgs#mold`; gcc lacks `-fuse-ld=mold`, so `-B` shim dir)
- repo copies: `git ls-files` of each source repo plus its `Cargo.lock`; `cargo fetch` once, all runs `--offline --locked`
- `EVAL_OUT=... python3 scripts/run.py LANE LO-HI REPOS REPS`, then `python3 scripts/analyze.py data/raw_*.csv`
