import subprocess
from pathlib import Path
from backend.config import OUT_DIR, SRC_FILE, LOG_DIR, ERR_DIR, TEST_INPUT

# -----------------------------
# DIRECTORIES
# -----------------------------


# -----------------------------
# SANITIZER MODES
# -----------------------------
SANITIZER_MODES = {
    "asan_ubsan": [
        "-fsanitize=address,undefined",
        "-fno-omit-frame-pointer",
        "-g"
    ],
    "ubsan_only": [
        "-fsanitize=undefined",
        "-fno-sanitize-recover=all",
        "-g"
    ]
}

FALLBACK_FLAGS = {
    "asan_ubsan": ["-fsanitize=address", "-g"],
    "ubsan_only": ["-g"]
}

# -----------------------------
# SETUP
# -----------------------------
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
ERR_DIR.mkdir(exist_ok=True)

success_log = open(LOG_DIR / "compile_success.txt", "a")
fail_log = open(LOG_DIR / "compile_failed.txt", "a")
sanity_log = open(LOG_DIR / "sanity_check.txt", "a")


# -----------------------------
# FUNCTIONS
# -----------------------------
def compile_file(c_file, exe_file, flags):
    cmd = [
        "clang",
        *flags,
        str(c_file),
        "-o", str(exe_file),
        "-Wl,/NOIMPLIB"
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    return result.returncode, result.stderr.decode()


def sanity_check(exe_file):
    try:
        result = subprocess.run(
            [str(exe_file)],
            input=TEST_INPUT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3
        )

        output = result.stdout + result.stderr

        output = "\n".join(
            line for line in output.splitlines()
            if "interception_win" not in line
        )

        if any(keyword in output for keyword in [
            "ERROR: AddressSanitizer",
            "runtime error:",
            "undefined behavior",
            "heap-buffer-overflow",
            "stack-buffer-overflow",
            "use-after-free"
        ]):
            status = "SANITIZER_TRIGGERED"
        else:
            status = "CLEAN"

        with open(LOG_DIR / f"{exe_file.stem}.runtime.txt", "w") as f:
            f.write(output)

        return status

    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except Exception:
        return "ERROR"


# -----------------------------
# MAIN (SINGLE FILE)
# -----------------------------
def run_compile_pipeline():

    c_file = SRC_FILE

    if not c_file.exists():
        print("❌ No input file found")
        return

    print(f"🚀 Processing {c_file.name}...")

    for mode, flags in SANITIZER_MODES.items():

        exe_file = OUT_DIR / f"{c_file.stem}_{mode}.exe"

        # overwrite old exe
        if exe_file.exists():
            exe_file.unlink()

        # ---- PRIMARY COMPILE ----
        code, err = compile_file(c_file, exe_file, flags)

        # ---- FALLBACK ----
        if code != 0:
            print(f"⚠️ Retrying ({mode}) with fallback")
            fallback_flags = FALLBACK_FLAGS.get(mode, ["-g"])
            code, err = compile_file(c_file, exe_file, fallback_flags)

        # ---- FAILURE ----
        if code != 0:
            fail_log.write(f"{c_file.name} [{mode}]\n")
            with open(ERR_DIR / f"{c_file.stem}_{mode}.err", "w") as f:
                f.write(err)
            print(f"❌ Failed ({mode})")
            continue

        success_log.write(f"{c_file.name} [{mode}]\n")

        # ---- SANITY CHECK ----
        status = sanity_check(exe_file)
        sanity_log.write(f"{c_file.name} [{mode}]: {status}\n")

        # ---- DELETE NON-EXE FILES ----
        for f in OUT_DIR.iterdir():
            if f.is_file() and f.suffix != ".exe":
                try:
                    f.unlink()
                except Exception:
                    pass

    success_log.flush()
    fail_log.flush()
    sanity_log.flush()

    print("✅ Done")