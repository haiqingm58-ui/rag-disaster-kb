import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DOCUMENTS_DIR = DATA_DIR / "documents"
CACHE_DIR = DATA_DIR / "cache"
UPLOADS_DIR = DATA_DIR / "uploads"
MARKDOWN_DIR = DATA_DIR / "markdown"
REPORTS_DIR = DATA_DIR / "reports"
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", str(DATA_DIR / "chroma_db")))

# Collections
COLLECTION_DOCS = "local_docs"
COLLECTION_EVENTS = "disaster_events"

# Embedding — default remains local Ollama, while preserving legacy names.
EMBEDDING_PROVIDER = os.getenv(
    "EMBEDDING_PROVIDER",
    "ollama" if os.getenv("EMBEDDING_BACKEND", "local") == "local" else os.getenv("EMBEDDING_BACKEND", "ollama"),
).lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"))
OLLAMA_EMBED_MODEL = os.getenv(
    "OLLAMA_EMBED_MODEL",
    os.getenv("LOCAL_EMBEDDING_MODEL", "nomic-embed-text:v1.5"),
)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# Backward-compatible aliases used by older modules/scripts.
EMBEDDING_BACKEND = "local" if EMBEDDING_PROVIDER == "ollama" else EMBEDDING_PROVIDER
LOCAL_EMBEDDING_MODEL = OLLAMA_EMBED_MODEL

# LLM provider
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").lower()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:8080/v1"))
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", os.getenv("LLM_MODEL", "qwen-local"))
LOCAL_LLM_MODEL_PATH = os.getenv("LOCAL_LLM_MODEL_PATH", os.getenv("QWEN_MODEL_PATH", ""))

LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "512"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))

# Backward-compatible aliases. New LLM code uses provider-specific values.
LLM_MODEL = DEEPSEEK_MODEL if LLM_PROVIDER == "deepseek" else LOCAL_LLM_MODEL
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", DEEPSEEK_API_KEY if LLM_PROVIDER == "deepseek" else "not-needed")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", DEEPSEEK_BASE_URL if LLM_PROVIDER == "deepseek" else LOCAL_LLM_BASE_URL)


def validate_llm_config() -> None:
    """Raise a friendly error for unsupported or incomplete LLM configuration."""
    if LLM_PROVIDER not in {"deepseek", "local"}:
        raise ValueError(
            f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}. "
            "Supported values: deepseek, local."
        )
    if LLM_PROVIDER == "deepseek" and not DEEPSEEK_API_KEY.strip():
        raise ValueError(
            "DEEPSEEK_API_KEY is missing. "
            "Suggestion: add DEEPSEEK_API_KEY=xxx to .env."
        )

# Text splitting
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
CHUNK_SEPARATORS = ["\n\n", "\n", "。", "，", "；", "！", "？", " ", ""]

# Retrieval
RETRIEVAL_K_DOCS = 5
RETRIEVAL_K_EVENTS = 3
RETRIEVAL_PREFETCH = 20              # 先召回更多，再 rerank 精选
RELEVANCE_THRESHOLD = float(os.getenv("RELEVANCE_THRESHOLD", "1.2"))  # Chroma L2 距离阈值，越小越相关
RERANK_TOP_K = 5                     # rerank 后最终保留条数

# Query rewriting
ENABLE_QUERY_REWRITE = os.getenv("ENABLE_QUERY_REWRITE", "true").lower() == "true"

# Multi-turn conversation
MAX_HISTORY_TURNS = 3                # 保留最近 N 轮对话作为上下文

# Reranker
RERANK_MODEL = os.getenv("RERANK_MODEL", "ms-marco-MiniLM-L-6-v2")  # FlashRank 模型

# Cache TTL (seconds)
CACHE_TTL_EARTHQUAKE = 600   # 10 minutes
CACHE_TTL_GDACS = 1800       # 30 minutes
CACHE_TTL_CENC = 600         # 10 minutes

# USGS API
USGS_API_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"

# GDACS API
GDACS_API_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"

# CENC latest earthquake list via Wolfx Open API mirror
CENC_API_URL = os.getenv("CENC_API_URL", "https://api.wolfx.jp/cenc_eqlist.json")

# MinerU PDF parsing backend, e.g. pipeline / hybrid-auto-engine / vlm-auto-engine.
MINERU_BACKEND = os.getenv("MINERU_BACKEND", "pipeline")
MINERU_ENABLE_FORMULA = os.getenv("MINERU_ENABLE_FORMULA", "false").lower() == "true"
MINERU_ENABLE_TABLE = os.getenv("MINERU_ENABLE_TABLE", "false").lower() == "true"

# Default reference location (Changsha)
DEFAULT_LOCATION_NAME = os.getenv("DEFAULT_LOCATION_NAME", "长沙")
DEFAULT_LATITUDE = float(os.getenv("DEFAULT_LATITUDE", "28.2282"))
DEFAULT_LONGITUDE = float(os.getenv("DEFAULT_LONGITUDE", "112.9388"))
DEFAULT_RADIUS_KM = int(os.getenv("DEFAULT_RADIUS_KM", "500"))
DEFAULT_MAP_ZOOM = int(os.getenv("DEFAULT_MAP_ZOOM", "6"))

# Geocoding
GEOCODER_PROVIDER = os.getenv("GEOCODER_PROVIDER", "nominatim").lower()
GEOCODER_CACHE_TTL_HOURS = int(os.getenv("GEOCODER_CACHE_TTL_HOURS", "24"))
GEOCODER_USER_AGENT = os.getenv(
    "GEOCODER_USER_AGENT",
    "georisk-disaster-query/1.0",
)

# Optional public social signal adapters
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
SOCIAL_SIGNALS_CACHE_FILE = CACHE_DIR / "social_signals.json"

# Event deduplication and confidence scoring
EVENT_DEDUP_TIME_WINDOW_MINUTES = int(os.getenv("EVENT_DEDUP_TIME_WINDOW_MINUTES", "30"))
EVENT_DEDUP_DISTANCE_KM = float(os.getenv("EVENT_DEDUP_DISTANCE_KM", "50"))
EVENT_DEDUP_MAGNITUDE_DELTA = float(os.getenv("EVENT_DEDUP_MAGNITUDE_DELTA", "0.3"))

# Ensure directories exist
for d in [DOCUMENTS_DIR, CACHE_DIR, UPLOADS_DIR, MARKDOWN_DIR, REPORTS_DIR, REPORTS_DIR / "images", CHROMA_DIR]:
    d.mkdir(parents=True, exist_ok=True)
