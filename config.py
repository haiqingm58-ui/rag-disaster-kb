import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DOCUMENTS_DIR = DATA_DIR / "documents"
CACHE_DIR = DATA_DIR / "cache"
CHROMA_DIR = DATA_DIR / "chroma_db"

# Collections
COLLECTION_DOCS = "local_docs"
COLLECTION_EVENTS = "disaster_events"

# Embedding — use "openai" or "local"
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "local")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
LOCAL_EMBEDDING_MODEL = os.getenv("LOCAL_EMBEDDING_MODEL", "nomic-embed-text:v1.5")

# LLM
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen_Qwen3.5-9B-Q4_K_M.gguf")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))

# API settings
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-placeholder")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:8080/v1")

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

# Ensure directories exist
for d in [DOCUMENTS_DIR, CACHE_DIR, CHROMA_DIR]:
    d.mkdir(parents=True, exist_ok=True)
