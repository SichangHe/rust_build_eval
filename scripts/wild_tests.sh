#!/bin/bash
# Run `cargo test` on a repo copy with the default linker and with wild; report differences.
# usage: EVAL_OUT=/tmp/x CPUS=112-127 wild_tests.sh REPO_NAME [extra cargo test args, also used for the prior build]
# needs: $EVAL_OUT/src/REPO_NAME (source copy), $EVAL_OUT/wildbin/ld -> wild, $EVAL_OUT/cargo_home (no config.toml)
set -u
repo=$1; shift
src=$EVAL_OUT/src/$repo
BUILD_ARGS=("$@")
export CARGO_HOME=$EVAL_OUT/cargo_home
for linker in default wild; do
    flags=""
    [ $linker = wild ] && flags="-Clinker-features=-lld -Clink-arg=-B$EVAL_OUT/wildbin"
    log=$EVAL_OUT/logs/$repo.$linker.log
    mkdir -p "$EVAL_OUT/logs"
    ln -sfn "$EVAL_OUT/target/$repo.$linker" "$src/target" # some e2e tests look for ./target/debug/<bin>
    ( cd "$src" && RUSTFLAGS="$flags" CARGO_TARGET_DIR=$EVAL_OUT/target/$repo.$linker nice taskset -c "$CPUS" cargo build --workspace --offline --locked -j8 "${BUILD_ARGS[@]}" >/dev/null 2>&1; RUSTFLAGS="$flags" CARGO_TARGET_DIR=$EVAL_OUT/target/$repo.$linker RUST_BACKTRACE=1 \
        timeout 3h nice -n10 taskset -c "${CPUS:?}" cargo test --workspace --offline --locked --no-fail-fast -j8 "$@" ) > "$log" 2>&1
    echo "$repo $linker exit=$?" >> "$EVAL_OUT/logs/summary"
    # normalized per-test outcomes (drop timings), sorted
    grep -E '^test .* \.\.\. ' "$log" | sed -E 's/ *\.\.\. (ok|FAILED|ignored).*/ \1/' | sort > "$EVAL_OUT/logs/$repo.$linker.tests"
done
cd "$EVAL_OUT/logs"
echo "$repo: default $(grep -c ' ok$' $repo.default.tests) ok / $(grep -c ' FAILED$' $repo.default.tests) failed;" \
     "wild $(grep -c ' ok$' $repo.wild.tests) ok / $(grep -c ' FAILED$' $repo.wild.tests) failed" >> summary
diff $repo.default.tests $repo.wild.tests > $repo.diff && echo "$repo: per-test outcomes identical" >> summary || echo "$repo: DIFFERENT, see $repo.diff" >> summary
