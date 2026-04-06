import subprocess
import multiprocessing
multiprocessing.freeze_support()

import re
import os
import sys
import json
import time
import random
import string
import hashlib
import numpy as np
from math import log2
from collections import defaultdict
from multiprocessing import Pool, cpu_count

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════
EXEC_DIR        = "fuzzing/executables"
RUNS_PER_EXE    = 50
TIMEOUT         = 0.3
NUM_WORKERS     = 8
OUTPUT_FILE     = "fuzzing/dynamic_features.json"
BATCH_SIZE      = 200
FAST_FAIL_PROBE = 10
FAST_FAIL_MIN   = 20

# ══════════════════════════════════════════════════════════════════════════════
# ASAN / UBSAN / CRASH PATTERNS
# ══════════════════════════════════════════════════════════════════════════════
_RE_FLAGS = re.IGNORECASE | re.MULTILINE

ASAN_PATTERNS = {
    "heap_overflow":   re.compile(r"heap.buffer.overflow",          _RE_FLAGS),
    "stack_overflow":  re.compile(r"stack.buffer.overflow",         _RE_FLAGS),
    "use_after_free":  re.compile(r"use.after.free",                _RE_FLAGS),
    "double_free":     re.compile(r"double.free",                   _RE_FLAGS),
    "invalid_access":  re.compile(r"invalid (read|write) of size",  _RE_FLAGS),
    "global_overflow": re.compile(r"global.buffer.overflow",        _RE_FLAGS),
    "stack_use_ret":   re.compile(r"stack.use.after.return",        _RE_FLAGS),
    "alloc_dealloc":   re.compile(r"alloc-dealloc-mismatch",        _RE_FLAGS),
    "memcpy_overlap":  re.compile(r"memcpy.param.overlap",          _RE_FLAGS),
    "msvc_asan":       re.compile(r"AddressSanitizer",              _RE_FLAGS),
}

UBSAN_PATTERNS = {
    "int_overflow":    re.compile(r"(signed|unsigned) integer overflow",  _RE_FLAGS),
    "divide_by_zero":  re.compile(r"division by zero",                    _RE_FLAGS),
    "null_deref":      re.compile(r"null pointer dereference",            _RE_FLAGS),
    "invalid_shift":   re.compile(r"shift (exponent|amount)",             _RE_FLAGS),
    "out_of_bounds":   re.compile(r"index \S+ out of bounds",             _RE_FLAGS),
    "invalid_bool":    re.compile(r"not a valid value for type 'bool'",   _RE_FLAGS),
    "ptr_overflow":    re.compile(r"pointer (index expression|overflow)", _RE_FLAGS),
    "float_cast":      re.compile(r"value \S+ is outside the range",      _RE_FLAGS),
    "invalid_enum":    re.compile(r"not a valid value for type",          _RE_FLAGS),
    "msvc_rtc":        re.compile(r"Run-Time Check Failure",              _RE_FLAGS),
    "msvc_ubsan":      re.compile(r"UndefinedBehaviorSanitizer",          _RE_FLAGS),
    "sanitizer_fatal": re.compile(r"SUMMARY: \w+Sanitizer",               _RE_FLAGS),
}

CRASH_PATTERNS = {
    "segfault":        re.compile(r"segmentation fault|access violation",  _RE_FLAGS),
    "abort":           re.compile(r"\bAborted\b|SIGABRT",                  _RE_FLAGS),
    "runtime_error":   re.compile(r"runtime error",                        _RE_FLAGS),
    "fatal_error":     re.compile(r"fatal error|FATAL",                    _RE_FLAGS),
    "exception":       re.compile(r"unhandled exception|terminate called", _RE_FLAGS),
}

# ══════════════════════════════════════════════════════════════════════════════
# INPUT GENERATOR
# ══════════════════════════════════════════════════════════════════════════════
INPUT_CATEGORIES = [
    "overflow", "null_byte", "numeric", "divzero",
    "format_str", "structured", "random", "mutated", "combined",
]

_OVERFLOW_INPUTS = [
    "A" * 100, "A" * 1000, "A" * 5000,
    "A" * 10_000, "B" * 20_000, "C" * 50_000,
]
_NULL_INPUTS = [
    "", "\x00", "\x00\x00\x00", "\xff\xff\xff",
    "\x00" * 100, "\xff" * 1000,
]
_NUMERIC_INPUTS = [
    str(2**31 - 1), str(-(2**31)), str(2**63 - 1), str(-(2**63)),
    "999999999999999999999", "-999999999999999999999", "0", "-1",
    "2147483648", "-2147483649",
]
_DIVZERO_INPUTS = ["0", "00", "0/0", "100/0", "1 0", "0\n0"]
_FORMAT_INPUTS  = ["%x%x%x%x%x", "%s%s%s%s", "%n%n%n", "%p%p%p%p", "%.9999d"]
_STRUCTURED_INPUTS = [
    '{"key":"value"}', '{"a":123}', '{"a":-999999999}',
    '{"nested":{"x":1}}', "<xml><a>1</a></xml>",
    "<a>" + "A" * 1000 + "</a>",
    "GET / HTTP/1.1\r\nHost: test\r\n\r\n",
    "admin' OR '1'='1",
    "../../../etc/passwd",
]


def _random_input() -> str:
    return "".join(random.choices(string.printable, k=random.randint(1, 500)))


def _mutate(s: str) -> str:
    chars = list(s) if s else ["A"]
    for _ in range(random.randint(1, min(5, len(chars)))):
        chars[random.randint(0, len(chars) - 1)] = random.choice(string.printable)
    return "".join(chars)


def _combine() -> str:
    base = random.choice(_OVERFLOW_INPUTS + _STRUCTURED_INPUTS + _NUMERIC_INPUTS)
    return base + random.choice(["", "\x00", "%x", "A" * 100])


def generate_input(run_id: int):
    t = run_id % 9
    if   t == 0: return random.choice(_OVERFLOW_INPUTS),   "overflow"
    elif t == 1: return random.choice(_NULL_INPUTS),        "null_byte"
    elif t == 2: return random.choice(_NUMERIC_INPUTS),     "numeric"
    elif t == 3: return random.choice(_DIVZERO_INPUTS),     "divzero"
    elif t == 4: return random.choice(_FORMAT_INPUTS),      "format_str"
    elif t == 5: return random.choice(_STRUCTURED_INPUTS),  "structured"
    elif t == 6: return _random_input(),                    "random"
    elif t == 7: return _mutate(random.choice(_OVERFLOW_INPUTS + _STRUCTURED_INPUTS)), "mutated"
    else:        return _combine(),                         "combined"


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
_ADDR_RE = re.compile(r'0x[0-9a-fA-F]+')
_NUM_RE  = re.compile(r'\b\d+\b')


def normalize_stderr(raw: str) -> str:
    """Strip addresses + numbers for deduplication only. Never use for keyword matching."""
    s = raw.strip().lower()
    s = _ADDR_RE.sub("ADDR", s)
    s = _NUM_RE.sub("NUM", s)
    return s[:300]


def shannon_entropy(values: list) -> float:
    if len(values) < 2:
        return 0.0
    mn, mx = min(values), max(values)
    if mx == mn:
        return 0.0
    buckets = [0] * 10
    span = mx - mn
    for v in values:
        b = min(int((v - mn) / span * 10), 9)
        buckets[b] += 1
    n = len(values)
    return round(-sum((c / n) * log2(c / n) for c in buckets if c > 0), 6)


# ══════════════════════════════════════════════════════════════════════════════
# SINGLE-EXE FUZZER  — UNCHANGED from v2
# ══════════════════════════════════════════════════════════════════════════════
def fuzz_one_exe(exe_path: str, exe_type: str, runs: int = RUNS_PER_EXE) -> dict | None:
    r = dict(
        asan_hits        = defaultdict(int),
        ubsan_hits       = defaultdict(int),
        crash_hits       = defaultdict(int),
        total_runs       = 0,
        crash_count      = 0,
        exit_nonzero     = 0,
        asan_match_count = 0,
        ubsan_match_count= 0,
        crash_generic    = 0,
        timeouts         = 0,
        total_time       = 0.0,
        times            = [],
        exit_codes       = set(),
        cat_crashes      = defaultdict(int),
        cat_runs         = defaultdict(int),
        raw_stderr_map   = {},
        raw_stderr_set   = set(),
        path_sigs        = set(),
        max_stderr_len   = 0,
        last_norm        = None,
        input_effect     = 0,
        last_crashed     = None,
        crash_transitions= 0,
        error_keywords   = set(),
    )

    ERROR_KW = ["overflow", "invalid", "error", "null", "divide", "shift",
                "free", "oob", "bound", "dereference", "exception", "fatal",
                "abort", "segfault", "access"]

    actual_runs = runs
    probe_done  = False

    run_id = 0
    while run_id < actual_runs:
        fuzz_input, category = generate_input(run_id)
        r["cat_runs"][category] += 1

        start = time.perf_counter()
        try:
            proc = subprocess.Popen(
                [exe_path],
                stdin =subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text  =True,
            )
            _, raw_stderr = proc.communicate(input=fuzz_input, timeout=TIMEOUT)
            exec_time = time.perf_counter() - start

        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            exec_time = TIMEOUT
            r["timeouts"]    += 1
            r["total_runs"]  += 1
            r["crash_count"] += 1
            r["cat_crashes"][category] += 1
            r["exit_nonzero"] += 1
            r["exit_codes"].add(-1)
            run_id += 1
            continue

        except OSError as e:
            if "WinError 225" in str(e):
                return None
            return None

        except Exception:
            run_id += 1
            continue

        r["total_runs"]  += 1
        r["total_time"]  += exec_time
        r["times"].append(exec_time)
        r["exit_codes"].add(proc.returncode)

        exit_nonzero = (proc.returncode != 0)
        if exit_nonzero:
            r["exit_nonzero"] += 1

        asan_matched  = False
        ubsan_matched = False
        crash_matched = False

        for name, pat in ASAN_PATTERNS.items():
            if pat.search(raw_stderr):
                r["asan_hits"][name] += 1
                asan_matched = True

        for name, pat in UBSAN_PATTERNS.items():
            if pat.search(raw_stderr):
                r["ubsan_hits"][name] += 1
                ubsan_matched = True

        for name, pat in CRASH_PATTERNS.items():
            if pat.search(raw_stderr):
                r["crash_hits"][name] += 1
                crash_matched = True

        if asan_matched:  r["asan_match_count"]  += 1
        if ubsan_matched: r["ubsan_match_count"] += 1
        if crash_matched: r["crash_generic"]     += 1

        crashed = exit_nonzero or asan_matched or crash_matched

        if crashed:
            r["crash_count"] += 1
            r["cat_crashes"][category] += 1

        if r["last_crashed"] is not None and crashed != r["last_crashed"]:
            r["crash_transitions"] += 1
        r["last_crashed"] = crashed

        raw_stripped = raw_stderr.strip()
        raw_len      = len(raw_stripped)
        r["max_stderr_len"] = max(r["max_stderr_len"], raw_len)

        norm = normalize_stderr(raw_stderr)
        r["raw_stderr_map"][norm] = r["raw_stderr_map"].get(norm, 0) + 1

        raw_sample = raw_stripped[:300]
        r["raw_stderr_set"].add(raw_sample)

        sig = hashlib.md5(f"{norm}|{proc.returncode}".encode()).hexdigest()
        r["path_sigs"].add(sig)

        if r["last_norm"] is not None and r["last_norm"] != norm:
            r["input_effect"] += 1
        r["last_norm"] = norm

        raw_lower = raw_stderr.lower()
        for kw in ERROR_KW:
            if kw in raw_lower:
                r["error_keywords"].add(kw)

        if not probe_done and r["total_runs"] >= FAST_FAIL_PROBE:
            probe_done = True
            if (r["crash_count"] == 0
                    and r["asan_match_count"] == 0
                    and r["ubsan_match_count"] == 0
                    and r["max_stderr_len"] == 0
                    and len(r["exit_codes"]) == 1):
                actual_runs = min(actual_runs, FAST_FAIL_MIN)

        run_id += 1

    total = r["total_runs"]
    if total == 0:
        return None

    times = r["times"]

    asan_total  = sum(r["asan_hits"].values())
    ubsan_total = sum(r["ubsan_hits"].values())

    rare_raw       = sum(1 for v in r["raw_stderr_map"].values() if v == 1)
    total_distinct = max(len(r["raw_stderr_map"]), 1)

    crash_inducing_cats = sum(1 for c in INPUT_CATEGORIES if r["cat_crashes"].get(c, 0) > 0)

    feat = {
        "exe_type":               exe_type,
        "total_runs":             total,

        "crash_count":            r["crash_count"],
        "crash_rate":             round(r["crash_count"] / total, 4),
        "exit_nonzero_count":     r["exit_nonzero"],
        "exit_nonzero_rate":      round(r["exit_nonzero"] / total, 4),

        "asan_total":             asan_total,
        "asan_rate":              round(asan_total / total, 4),
        "asan_run_count":         r["asan_match_count"],
        "asan_run_rate":          round(r["asan_match_count"] / total, 4),
        **{f"asan_{k}": r["asan_hits"].get(k, 0) for k in ASAN_PATTERNS},

        "ubsan_total":            ubsan_total,
        "ubsan_rate":             round(ubsan_total / total, 4),
        "ubsan_run_count":        r["ubsan_match_count"],
        "ubsan_run_rate":         round(r["ubsan_match_count"] / total, 4),
        **{f"ubsan_{k}": r["ubsan_hits"].get(k, 0) for k in UBSAN_PATTERNS},

        "crash_generic_count":    r["crash_generic"],
        "crash_generic_rate":     round(r["crash_generic"] / total, 4),
        **{f"crash_{k}": r["crash_hits"].get(k, 0) for k in CRASH_PATTERNS},

        "timeout_count":          r["timeouts"],
        "timeout_rate":           round(r["timeouts"] / total, 4),

        "avg_exec_time":          round(r["total_time"] / total, 6),
        "time_variance":          round(float(np.var(times)), 8) if times else 0.0,
        "time_entropy":           shannon_entropy(times),
        "max_exec_time":          round(max(times), 6)           if times else 0.0,
        "p90_exec_time":          round(float(np.percentile(times, 90)), 6) if times else 0.0,

        "unique_exit_codes":      len(r["exit_codes"]),
        "path_variability":       len(r["path_sigs"]),
        "unique_outputs":         len(r["raw_stderr_set"]),
        "input_sensitivity":      r["input_effect"],
        "max_stderr_len":         r["max_stderr_len"],
        "error_type_diversity":   len(r["error_keywords"]),
        "rare_behavior_ratio":    round(rare_raw / total_distinct, 4),
    }
    return feat


# ══════════════════════════════════════════════════════════════════════════════
# MERGE RESULTS FOR MULTIPLE EXES PER FUNCTION
# ══════════════════════════════════════════════════════════════════════════════
def merge_exe_results(idx: int, exe_feats: dict) -> dict:
    merged = {"idx": idx}
    numeric_keys = [
        "total_runs","crash_count","exit_nonzero_count","asan_total","ubsan_total",
        "timeout_count","avg_exec_time","unique_exit_codes","path_variability",
        "unique_outputs","time_variance","input_sensitivity","max_stderr_len",
        "error_type_diversity","rare_behavior_ratio"
    ]
    for key in numeric_keys:
        merged[key] = sum(feat.get(key,0) for feat in exe_feats.values())
    merged["crash_rate"] = round(merged["crash_count"] / max(merged["total_runs"],1),4)
    merged["asan_rate"]  = round(merged["asan_total"] / max(merged["total_runs"],1),4)
    merged["ubsan_rate"] = round(merged["ubsan_total"] / max(merged["total_runs"],1),4)
    return merged


# ══════════════════════════════════════════════════════════════════════════════
# PROCESS FILE GROUP — FIXED: UNIQUE KEYS TO PREVENT OVERWRITE
# ══════════════════════════════════════════════════════════════════════════════
def process_file_group(idx_and_files: tuple) -> dict | None:
    idx, files = idx_and_files
    results = {}
    for fname in files:
        exe_path = os.path.join(EXEC_DIR, fname)
        # use filename as key to avoid overwriting
        exe_type = fname.lower()
        feat = fuzz_one_exe(exe_path, exe_type, RUNS_PER_EXE)
        if feat:
            results[fname] = feat  # unique key
    if not results:
        return {"idx": idx,
                "crash_count":0,"crash_rate":0.0,"asan_total":0,"ubsan_total":0,
                "timeout_count":0,"avg_exec_time":0.0,"unique_exit_codes":0,
                "path_variability":0,"unique_outputs":0,"time_variance":0.0,
                "input_sensitivity":0,"max_stderr_len":0,
                "error_type_diversity":0,"rare_behavior_ratio":0}
    return merge_exe_results(idx, results)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def run_dynamic_analysis():
    files = os.listdir(EXEC_DIR)
    grouped = defaultdict(list)
    for f in files:
        m = re.match(r'^(\d+)', f)
        if not m:
            continue
        idx = int(m.group(1))
        grouped[idx].append(f)

    jobs = list(grouped.items())
    all_feats = []

    with Pool(processes=NUM_WORKERS) as p:
        for result in p.imap_unordered(process_file_group, jobs):
            if result:
                all_feats.append(result)

    with open(OUTPUT_FILE,"w") as f:
        json.dump(all_feats,f,indent=2)


if __name__ == "__main__":
    run_dynamic_analysis()