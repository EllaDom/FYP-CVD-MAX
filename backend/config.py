from pathlib import Path

# -----------------------------
# BASE DIRECTORY (Frontend/)
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
# This goes from: Frontend/backend/config.py → Frontend/

# -----------------------------
# DIRECTORIES
# -----------------------------
SRC_FILE = BASE_DIR / "workspace" / "input" / "user_code.c"

OUT_DIR = BASE_DIR / "fuzzing" / "executables"

LOG_DIR = BASE_DIR / "logs"
ERR_DIR = LOG_DIR / "errors"

# -----------------------------
# TEST INPUT
# -----------------------------
TEST_INPUT = "A" * 1000 + "\n"