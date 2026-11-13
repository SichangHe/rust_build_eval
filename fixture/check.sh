#!/bin/bash
# usage: EVAL_OUT=... check.sh default|wild ; sanity checks on fixture builds (panic backtrace, gdb, addr2line, cdylib, proc-macro, build script)
set -u
l=$1; d=$(cd "$(dirname "$0")" && pwd)
flags=""; [ $l = wild ] && flags="-Clinker-features=-lld -Clink-arg=-B$EVAL_OUT/wildbin"
export CARGO_HOME=$EVAL_OUT/cargo_home CARGO_TARGET_DIR=$EVAL_OUT/target/fixture.$l RUSTFLAGS="$flags" RUST_BACKTRACE=1
export CARGO_PROFILE_DEV_DEBUG=line-tables-only
cd "$d"; cargo build --offline -q --workspace 2>&1 | grep -E "^error" ; cargo test --offline -q --workspace 2>&1 | grep -E '^test result|FAILED|error' 
t=$CARGO_TARGET_DIR/debug
echo "run: $($t/app 1)"
echo "backtrace:"; $t/app 200 2>&1 | grep -E 'main.rs:[0-9]+' | head -4
echo "gdb:"; gdb -batch -ex 'break main.rs:11' -ex run -ex bt --args $t/app 1 2>&1 | grep -E 'Breakpoint 1|#[0-9]' | head -4
echo "addr2line:"; a=$(nm $t/app | grep ' t .*boom' | head -1 | cut -d' ' -f1); addr2line -e $t/app 0x$a
echo "cdylib: $(python3 -c "import ctypes,sys;print(ctypes.CDLL(sys.argv[1]).cd_add(2,3))" $t/libcd.so)"
echo "linker comment:"; readelf -p .comment $t/app | grep -iE 'wild|lld|GNU ld' | head -2
