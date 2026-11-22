"""Single source of truth for spark-upgrade-ledger."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BASE_URL = "http://localhost:8080/v1"
MODEL_ID = "spark2.6-4B"
MODEL_REVISION = "fe31f8d64890302cc3a1d365d700357b4b75ba77"
MODEL_QUANT = "Q4_K_M"
CONTEXT_SIZE = 16384

TEMPERATURE = 0.2
TOP_P = 0.95
TOP_K = 20
REPEAT_PENALTY = 1.05
MAX_TOKENS = 1200
REQUEST_TIMEOUT_SECONDS = 180.0
ENABLE_THINKING = False

MIN_INPUT_CHARS = 20
MAX_INPUT_CHARS = 8000
MAX_ITEMS = 12
MAX_SOURCE_LINES = 200

CACHE_TTL_SECONDS = 900.0
MIN_INTERVAL_SECONDS = 1.0

SKILL_COORDINATE = "global/research-evidence-auditor"
SKILL_VERSION = "20260820.034025"
SKILL_WEB_URL = "https://skill.xfyun.cn/space/global/research-evidence-auditor"
SKILL_DIR = ROOT / ".codex" / "skills" / "research-evidence-auditor"
SKILL_AUDIT_SCRIPT = SKILL_DIR / "scripts" / "audit_evidence.py"

DEFAULT_INPUT = ROOT / "data" / "release_notes.txt"
