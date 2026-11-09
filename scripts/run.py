#!/usr/bin/env python3
"""Randomized interleaved cargo build benchmark. Usage: run.py LANE CPURANGE lo-hi REPO,REPO,... [REPS]

One trial = fresh dirs -> cold build -> no-op -> 1 warm-up edit (`-v`, flags check) ->
4x(leaf edit, wide edit) -> sizes -> run binary in clean env -> (rep 0) `cargo test --no-run`.
Trials of all (repo, config, rep) are shuffled (seeded) so configs interleave in time.
Long-format CSV: lane,repo,config,rep,metric,value,load1.
"""
import os, random, resource, shutil, subprocess, sys, time

OUT = os.environ["EVAL_OUT"]
HERE = os.path.dirname(os.path.abspath(__file__))
TC = "1.97.1-x86_64-unknown-linux-gnu"
N_EDIT_PAIRS = 4
DBG = '[profile.dev]\ndebug = "line-tables-only"\n[profile.dev.package."*"]\ndebug = false\n'
SPLIT = '[profile.dev]\ndebug = "line-tables-only"\nsplit-debuginfo = "unpacked"\n[profile.dev.package."*"]\ndebug = false\n'
NOLLD = "-Clinker-features=-lld"
MOLD = f"{NOLLD} -Clink-arg=-B{OUT}/moldbin"
# name -> toml, rustflags, dynamic-std wrapper, build-dir kind, extra cargo args
CFGS = {
    "baseline": ("", "", 0, None, []),
    "dbg": (DBG, "", 0, None, []),
    "split": (SPLIT, "", 0, None, []),  # default linker (rust-lld)
    "bfd": (SPLIT, NOLLD, 0, None, []),
    "mold": (SPLIT, MOLD, 0, None, []),
    "dynrpath": (SPLIT, "", 1, None, []),
    "builddir": (SPLIT, "", 0, "disk", []),
    "builddir_shm": (SPLIT, "", 0, "/dev/shm", []),
    "depdylib": (SPLIT, "", 1, None, ["--features", "dylib"]),  # webapp only
}
# repo -> (cargo args, bin, run args, leaf file, wide file)
REPOS = {
    "agent_managers": ([], "amh", ["--help"], "src/main.rs", None),
    "teamtype--teamtype": ([], "teamtypev", ["--version"], "crates/teamtype/src/main.rs", "crates/teamtype/src/lib.rs"),
    "rustls--rustls": (["-p", "rustls-examples"], "limitedclient", ["--help"], "examples/src/bin/limitedclient.rs", "rustls/src/lib.rs"),
    "webapp": (["-p", "app"], "app", ["--once"], "app/src/main.rs", None),
}
CARGO = subprocess.check_output(["rustup", "which", "cargo"], text=True, env={**os.environ, "RUSTUP_TOOLCHAIN": TC}).strip()


def load1():
    return open("/proc/loadavg").read().split()[0]


def du_kb(*paths):
    ps = [p for p in paths if p and os.path.exists(p)]
    return sum(int(subprocess.check_output(["du", "-sk", p], text=True).split()[0]) for p in ps)


class Trial:
    def __init__(self, lane, repo, cfg, rep, csv):
        self.lane, self.repo, self.cfg, self.rep, self.csv = lane, repo, cfg, rep, csv
        self.toml, self.rf, self.dyn, bd, self.extra = CFGS[cfg]
        self.cargo_args, self.bin, self.run_args, self.leaf, self.wide = REPOS[repo]
        tag = f"{lane}.{repo}.{cfg}.{rep}"
        self.src = f"{OUT}/repos/{repo}"
        self.target = f"{OUT}/t/{tag}"
        self.bdir = None if bd is None else (f"{OUT}/bd/{tag}" if bd == "disk" else f"{bd}/rbe_{tag}")
        self.env = {
            "PATH": os.environ["PATH"], "HOME": os.environ["HOME"], "CARGO_HOME": f"{OUT}/cargo_home",
            "RUSTUP_TOOLCHAIN": TC, "CARGO_TARGET_DIR": self.target, "CARGO_TERM_COLOR": "never",
            "CARGO_NET_OFFLINE": "true", "RUSTFLAGS": self.rf,
        }
        if self.dyn:
            self.env["RUSTC_WRAPPER"] = f"{HERE}/rustc_wrap.sh"
        self.flags = ["--offline", "--locked"]
        if self.toml:
            open(f"{OUT}/cfg/{cfg}.toml", "w").write(self.toml)
            self.flags += ["--config", f"{OUT}/cfg/{cfg}.toml"]
        if self.bdir:
            self.flags += ["--config", f'build.build-dir="{self.bdir}"']

    def rec(self, metric, value):
        self.csv.write(f"{self.lane},{self.repo},{self.cfg},{self.rep},{metric},{value},{load1()}\n")
        self.csv.flush()

    def cargo(self, sub, extra=(), log=None):
        cmd = [CARGO, sub, *self.cargo_args, *self.extra, *self.flags, *extra]
        r0 = resource.getrusage(resource.RUSAGE_CHILDREN)
        t0 = time.perf_counter()
        p = subprocess.run(cmd, cwd=self.src, env=self.env, capture_output=True, text=True, timeout=1800)
        ms = (time.perf_counter() - t0) * 1000
        r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
        if log:
            open(log, "w").write(p.stdout + p.stderr)
        if p.returncode:
            sys.stderr.write(f"FAIL {cmd}\n{p.stderr[-1500:]}\n")
        return ms, (r1.ru_utime + r1.ru_stime - r0.ru_utime - r0.ru_stime), p.returncode

    def edit(self, rel, i):
        with open(f"{self.src}/{rel}", "a") as f:
            f.write(f"\n#[allow(dead_code)]\nfn __bench_{i}() -> u32 {{ {i} }}\n")

    def sizes(self, tag):
        self.rec(f"size_{tag}_target_kb", du_kb(self.target))
        self.rec(f"size_{tag}_build_kb", du_kb(self.bdir))

    def run(self):
        os.makedirs(f"{OUT}/flags", exist_ok=True)
        for d in (self.target, self.bdir):
            if d:
                shutil.rmtree(d, ignore_errors=True)
        files = [self.leaf] + ([self.wide] if self.wide else [])
        orig = {f: open(f"{self.src}/{f}").read() for f in files}
        try:
            self.body()
        finally:
            for f, s in orig.items():
                open(f"{self.src}/{f}", "w").write(s)
            for d in (self.target, self.bdir):
                if d:
                    shutil.rmtree(d, ignore_errors=True)

    def body(self):
        ms, cpu, rc = self.cargo("build")
        self.rec("cold_ms", ms), self.rec("cold_cpu_s", cpu), self.rec("cold_rc", rc)
        if rc:
            return
        self.sizes("cold")
        binp = f"{self.target}/debug/{self.bin}"
        self.rec("bin_bytes", os.path.getsize(binp))
        comment = subprocess.run(["readelf", "-p", ".comment", binp], capture_output=True, text=True).stdout
        self.rec("linker", "|".join(l.split("]")[-1].strip() for l in comment.splitlines() if "]" in l).replace(",", ";"))
        dyn = subprocess.run(["readelf", "-d", binp], capture_output=True, text=True).stdout
        self.rec("dyn_std", int("libstd-" in dyn))
        ok = subprocess.run([binp, *self.run_args], cwd=self.src, env={"PATH": "/usr/bin:/bin"}, capture_output=True, timeout=20).returncode
        self.rec("run_rc", ok)
        ms, cpu, rc = self.cargo("build")
        self.rec("noop_ms", ms)
        i = 0
        self.edit(self.leaf, i)  # warm-up; `-v` log proves actual rustc flags
        self.cargo("build", ["-v"], log=f"{OUT}/flags/{self.repo}.{self.cfg}.{self.rep}.txt")
        for _ in range(N_EDIT_PAIRS):
            for kind, f in (("leaf", self.leaf), ("wide", self.wide)):
                if f:
                    i += 1
                    self.edit(f, i)
                    ms, cpu, rc = self.cargo("build")
                    self.rec(f"edit_{kind}_ms", ms), self.rec(f"edit_{kind}_cpu_s", cpu), self.rec(f"edit_{kind}_rc", rc)
        self.sizes("edited")
        if self.rep == 0:
            ms, cpu, rc = self.cargo("test", ["--no-run"])
            self.rec("test_norun_ms", ms), self.rec("test_norun_rc", rc)
            self.sizes("test")


def shared_pair(lane, kind, rep, csv):
    """Cold-build teamtype then agent_managers (cfg `split`), with one build-dir (`pair_shared`) or two (`pair_sep`)."""
    shared = kind == "pair_shared"
    for repo in ("teamtype--teamtype", "agent_managers"):
        t = Trial(lane, repo, "split", rep, csv)
        t.cfg = kind if repo == "agent_managers" else "pair_prelude"
        bd = f"{OUT}/bd/pair{rep}_{'s' if shared else repo}"
        t.flags += ["--config", f'build.build-dir="{bd}"']
        t.target = t.env["CARGO_TARGET_DIR"] = f"{OUT}/t/{lane}.{repo}.{kind}.{rep}"
        t.bdir = bd
        if repo == "teamtype--teamtype":
            shutil.rmtree(bd, ignore_errors=True)
        shutil.rmtree(t.target, ignore_errors=True)
        ms, cpu, rc = t.cargo("build")
        t.rec("cold_ms", ms), t.rec("cold_rc", rc)
        if repo == "agent_managers":
            t.rec("size_cold_build_kb", du_kb(bd))
    for p in (bd, f"{OUT}/bd/pair{rep}_teamtype--teamtype"):
        shutil.rmtree(p, ignore_errors=True)
    shutil.rmtree(f"{OUT}/t/{lane}.teamtype--teamtype.{kind}.{rep}", ignore_errors=True)
    shutil.rmtree(f"{OUT}/t/{lane}.agent_managers.{kind}.{rep}", ignore_errors=True)


if __name__ == "__main__":
    lane, cpus, repos = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
    reps = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    lo, hi = map(int, cpus.split("-"))
    os.sched_setaffinity(0, set(range(lo, hi + 1)))
    os.makedirs(f"{OUT}/cfg", exist_ok=True)
    trials = [(r, c, i) for r in repos if r in REPOS for c in CFGS if c != "depdylib" or r == "webapp" for i in range(reps)]
    trials += [("PAIR", k, i) for k in ("pair_shared", "pair_sep") for i in range(reps) if "PAIR" in repos]
    random.Random(f"{lane}").shuffle(trials)
    os.makedirs(f"{HERE}/../data", exist_ok=True)
    only = os.environ.get("ONLY")  # smoke tests: comma list of repo:cfg
    with open(f"{HERE}/../data/raw_{lane}.csv", "a") as csv:
        for n, (r, c, i) in enumerate(trials):
            if only and f"{r}:{c}" not in only.split(","):
                continue
            print(f"{time.strftime('%H:%M:%S')} {n+1}/{len(trials)} {r} {c} {i} load={load1()}", flush=True)
            shared_pair(lane, c, i, csv) if r == "PAIR" else Trial(lane, r, c, i, csv).run()
