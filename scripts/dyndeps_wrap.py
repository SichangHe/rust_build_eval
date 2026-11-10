#!/usr/bin/env python3
"""`RUSTC_WRAPPER` that links dependencies dynamically with zero project changes. Usage: dyndeps_wrap.py RUSTC ARGS...

Only `debug/deps` builds are touched (release/other profiles pass through).
- Registry/git library crates (not proc-macros, not workspace crates) are built as `lib` + `dylib`
  twins; the `.so` lands next to the `.rlib` (same `-Cextra-filename`).
- Every consumer that links (bins, tests, dylibs) gets `-Cprefer-dynamic`, an absolute rpath to the toolchain
  libdir and its own `--out-dir`, and, for each `--extern name=X.rlib|.rmeta` whose sibling `X.so` exists,
  a second `--extern name=X.so`.
- Cargo starts dependents once it sees the `metadata` artifact of a pipelined lib, but the dependents of a
  dylib twin need its `.so` already linked, so the `metadata` notice is held back until rustc exits.
- Build scripts and proc-macros are left static (they run inside cargo/rustc).
"""
import os, subprocess, sys

rustc, args = sys.argv[1], sys.argv[2:]


def flag_vals(name):
    return [args[i + 1] for i, a in enumerate(args[:-1]) if a == name] + [a.split("=", 1)[1] for a in args if a.startswith(name + "=")]


def passthrough():
    os.execv(rustc, [rustc, *args])


names, outs, types = flag_vals("--crate-name"), flag_vals("--out-dir"), flag_vals("--crate-type")
if not names or names[0] == "___" or not outs or not outs[0].endswith("/debug/deps"):
    passthrough()
if names[0].startswith("build_script_") or "proc-macro" in types:
    passthrough()
src = next((a for a in args if a.endswith(".rs")), "")
third_party = "/registry/src/" in src or "/git/checkouts/" in src
libdir = subprocess.check_output([rustc, "--print", "target-libdir"], text=True).strip()
extra = ["-Cprefer-dynamic", f"-Clink-arg=-Wl,-rpath,{libdir},-rpath,{outs[0]}"]
static_native = any(a.startswith("static") for a in flag_vals("-l")) or any(a.startswith("-lstatic") for a in args)
twin = third_party and set(types) <= {"lib", "rlib"} and not static_native  # a dylib would hide the crate's bundled C symbols
if twin:
    extra += ["--crate-type", "dylib"]
new = []
for i, a in enumerate(args):
    new.append(a)
    if i and args[i - 1] == "--extern" and "=" in a:
        n, p = a.split("=", 1)
        so = p.rsplit(".", 1)[0] + ".so"
        if p.endswith((".rlib", ".rmeta")) and os.path.exists(so):
            new += ["--extern", f"{n}={so}"]
cmd = [rustc, *new, *extra]
if not twin:
    os.execv(rustc, cmd)
p = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
if p.returncode:  # e.g. `#![no_std]` crates cannot be dylibs: fall back to the plain build
    os.execv(rustc, [rustc, *new, *extra[:2]])
lines = p.stderr.splitlines(keepends=True)
is_meta = lambda l: '"artifact"' in l and '"emit":"metadata"' in l
sys.stderr.write("".join(l for l in lines if not is_meta(l)) + "".join(l for l in lines if is_meta(l)))
