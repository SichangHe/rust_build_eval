#!/usr/bin/env python3
"""Usage: analyze.py data/raw_*.csv > results_table.txt

Per (repo, config, metric): n, median, 95% bootstrap CI of the median (10000 resamples, seed 0).
Per (repo, metric): each config's median ratio vs `ref`, with bootstrap CI of the ratio of medians.
Lane C (teamtype re-run) contributes only test metrics. Unit = one sample (edits are per-edit samples; cold/size are per-trial).
"""
import csv, random, statistics as st, sys
from collections import defaultdict

REF = "split"
N_BOOT = 10000
LANE_C = any("raw_C" in p for p in sys.argv[1:])
REF2 = {"cranelift": "split_nightly"}  # nightly-only configs are also compared with a nightly reference
rng = random.Random(0)
d = defaultdict(list)
text = defaultdict(set)
for path in sys.argv[1:]:
    for lane, repo, cfg, rep, metric, val, load in csv.reader(open(path)):
        is_test = metric.startswith(("test_norun", "size_test"))
        # lane A's teamtype test builds failed (copy lacked an untracked file); lane C redid them
        if LANE_C and (lane == "C") != (is_test and repo == "teamtype--teamtype"):
            continue
        try:
            d[repo, cfg, metric].append(float(val))
        except ValueError:
            text[repo, cfg, metric].add(val)


def boot(xs, ys=None):
    ms = []
    for _ in range(N_BOOT):
        a = st.median(rng.choices(xs, k=len(xs)))
        ms.append(a if ys is None else a / st.median(rng.choices(ys, k=len(ys))))
    ms.sort()
    return ms[int(.025 * N_BOOT)], ms[int(.975 * N_BOOT)]


SHOW = ["cold_ms", "cold_cpu_s", "cold_hit_ms", "edit_leaf_cpu_s", "edit_wide_cpu_s", "test_bins_load_fail", "edit_leaf_ms", "edit_wide_ms", "noop_ms", "size_cold_target_kb", "size_cold_build_kb",
        "size_edited_target_kb", "size_edited_build_kb", "bin_bytes", "test_norun_ms", "size_test_target_kb", "size_test_build_kb"]
repos = sorted({k[0] for k in d})
for repo in repos:
    cfgs = sorted({k[1] for k in d if k[0] == repo})
    print(f"\n## {repo}")
    for m in SHOW:
        rows = [(c, d[repo, c, m]) for c in cfgs if d.get((repo, c, m))]
        if not rows:
            continue
        print(f"\n{m}  (median [95% CI], n, ratio vs {REF} [95% CI])")
        ref = d.get((repo, REF, m))
        for c, xs in rows:
            lo, hi = boot(xs)
            r = ""
            if ref and c != REF and st.median(ref) > 0:
                rl, rh = boot(xs, ref)
                r = f"  x{st.median(xs) / st.median(ref):.3f} [{rl:.3f},{rh:.3f}]"
            r2 = ""
            if c in REF2 and st.median(d.get((repo, REF2[c], m)) or [0]) > 0:
                rl, rh = boot(xs, d[repo, REF2[c], m])
                r2 = f"  | vs {REF2[c]} x{st.median(xs) / st.median(d[repo, REF2[c], m]):.3f} [{rl:.3f},{rh:.3f}]"
            print(f"  {c:13s} {st.median(xs):12.1f} [{lo:.1f},{hi:.1f}] n={len(xs)}{r}{r2}")
    bad = [(c, m, sum(v)) for (r, c, m), v in d.items() if r == repo and (m.endswith("_rc") or m == "test_bins_load_fail") and sum(v)]
    bad += [(c, m, sum(1 for x in v if x)) for (r, c, m), v in d.items() if r == repo and m == "run_rc" and any(v)]
    print("\nnonzero exit codes (cfg, metric, count):", bad or "none")
