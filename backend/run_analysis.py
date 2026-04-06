import os
import subprocess
import shutil

BASE_DIR = os.path.abspath("workspace")

INPUT_C = os.path.join(BASE_DIR, "input", "1.c")
CPG_PATH = os.path.join(BASE_DIR, "cpg", "code.cpg.bin")

# ✅ SINGLE SCRIPT
GRAPH_SCRIPT = "scripts/extract_graphs.sc"

# ✅ Joern paths (adjust if needed)
JOERN_PARSE = r"C:\joern-cli\joern-parse.bat"
JOERN = r"C:\joern-cli\joern.bat"


def run_joern_pipeline():
    os.makedirs(os.path.dirname(INPUT_C), exist_ok=True)
    os.makedirs(os.path.dirname(CPG_PATH), exist_ok=True)

    shutil.rmtree(os.path.join(BASE_DIR, "graphs", "runtime"), ignore_errors=True)

    # ---------------- STEP 1: Generate CPG ----------------
    subprocess.run([
        JOERN_PARSE,
        INPUT_C,
        "--output", CPG_PATH
    ], check=True, capture_output=True, text=True)

    env = {
        **os.environ,
        "CPG_FILE": CPG_PATH,
        "SPLIT": "runtime"
    }

    # ---------------- STEP 2: Extract ALL graphs ----------------
    subprocess.run([
        JOERN,
        "--script", GRAPH_SCRIPT
    ], env=env, check=True, capture_output=True, text=True)