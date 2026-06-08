# Real-Time Geological Disaster Information Query

实时地质灾害信息查询与灾害知识问答系统。项目基于 Streamlit、ChromaDB、DeepSeek API / 本地 llama-server 可切换 LLM 和本地 Ollama Embedding，结合 CENC、USGS、GDACS 等实时灾害数据源，提供中文灾害知识问答、地图展示、附近灾害筛选、来源追踪、导出和规则评测能力。

## 功能概览

- 实时灾害数据：接入 CENC records via Wolfx mirror、USGS、GDACS，支持地震、洪水、热带气旋等事件。
- 交互式地图：按灾种、风险等级、时间范围、数据源筛选地图事件，并计算参考位置一定半径内的附近灾害。
- RAG 问答：结合本地专业文档和实时事件库回答灾害应急问题。
- 来源追踪：回答来源标注为 `[文档]`、`[实时]`、`[通用]`。
- 文档管理：支持上传 PDF、TXT、MD，切片后写入 ChromaDB。
- 实时事件同步：地图刷新后可同步实时事件到向量库，避免问答与地图数据割裂。
- 导出能力：支持导出问答 Markdown、检索来源 Markdown、附近灾害 CSV、地图事件 CSV 和灾害简报 Markdown。
- 生成统计：显示生成耗时、输入/输出 Token、总 Token、输出速度、Max Tokens、LLM 地址和 Token 来源。
- 规则评测：支持 `must_include`、`must_include_any`、`must_include_any_group`，适配中文同义表达，减少评测误判。

## 技术架构

```text
用户提问
  -> 查询改写
  -> 文档与实时事件双路检索
  -> 相似度阈值过滤
  -> FlashRank Reranker
  -> DeepSeek API 或本地 LLM 流式生成
  -> 中文回答与来源标注
```

主要组件：

| 组件 | 技术 | 默认位置 |
| --- | --- | --- |
| UI | Streamlit | `http://localhost:8501` |
| LLM | DeepSeek API，或本地 llama.cpp server | `https://api.deepseek.com` / `http://127.0.0.1:8080/v1` |
| Embedding | Ollama `nomic-embed-text:v1.5` | `http://127.0.0.1:11434` |
| 向量库 | ChromaDB | `data/chroma_db/` |
| 数据源 | CENC / USGS / GDACS | 网络 API 与本地缓存 |
| PDF 解析 | MinerU，可降级 PyPDF | CLI / Python |

## 目录结构

```text
.
├── config.py                  # 项目配置
├── start_all.sh               # 一键启动检查与启动脚本
├── run.sh                     # Streamlit 运行脚本
├── requirements.txt           # Python 依赖
├── src/
│   ├── ingestion/             # 文档解析与实时灾害 API
│   ├── rag/                   # 检索、查询改写、回答生成
│   ├── ui/                    # Streamlit 页面与组件
│   └── vectorstore/           # ChromaDB 封装
├── scripts/
│   ├── run_llama.sh           # 启动 llama.cpp server
│   ├── refresh_api_data.py    # 刷新实时灾害数据
│   ├── eval_fast.sh           # 快速评测脚本
│   └── eval_all_batches.sh    # 分批完整评测脚本
├── tests/
│   ├── eval_questions.json    # 规则评测题库
│   └── run_eval.py            # 评测执行器
├── data/documents/            # 示例知识库文档
└── docs/                      # 项目补充说明
```

## 环境准备

建议使用 Python 3.11 或更高版本。

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

安装并启动本地 Ollama Embedding：

```bash
ollama pull nomic-embed-text:v1.5
ollama serve
```

## DeepSeek API 模式

默认模式是 DeepSeek API 生成回答，本地仍保存文档、向量库和实时灾害缓存。

编辑 `.env`：

```bash
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
LLM_MAX_TOKENS=512
LLM_TEMPERATURE=0.2

EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBED_MODEL=nomic-embed-text:v1.5
```

启动：

```bash
bash start_all.sh
```

评测：

```bash
source venv/bin/activate
python tests/run_eval.py --fast
```

DeepSeek 模式下不需要下载 GGUF 模型，也不需要启动 `llama-server`。

## 本地模型模式

如果需要回退到本地 Qwen GGUF，请编辑 `.env`：

```bash
LLM_PROVIDER=local
LOCAL_LLM_BASE_URL=http://127.0.0.1:8080/v1
LOCAL_LLM_MODEL=qwen-local
LOCAL_LLM_MODEL_PATH=models/Qwen_Qwen3.5-9B-Q4_K_M.gguf
```

模型文件通常较大，不提交到 GitHub。默认建议放在：

```text
models/Qwen_Qwen3.5-9B-Q4_K_M.gguf
```

然后启动：

```bash
bash start_all.sh
```

`start_all.sh` 会在 local 模式下检查模型文件并自动启动 `llama-server`。

## 启动项目

推荐使用一键启动脚本：

```bash
bash start_all.sh
```

该脚本会读取 `LLM_PROVIDER`：

- `deepseek`：检查 `DEEPSEEK_API_KEY`、DeepSeek 网络可达性、Ollama 和 embedding 模型，然后启动 Streamlit；不检查 GGUF，不启动 `llama-server`。
- `local`：检查 GGUF 模型、本地 `llama-server`、Ollama 和 embedding 模型，然后启动 Streamlit。

浏览器访问：

```text
http://localhost:8501
```

## FastAPI Web 入口

本项目新增了轻量 FastAPI Web 应用，保留原有 Streamlit 启动方式不变。FastAPI 入口整合了知识图谱、RAG 问答、实时灾害数据、文档上传和来源追踪，适合部署到 2 核 2G 的云服务器。

本地启动：

```bash
uvicorn app_server.main:app --host 0.0.0.0 --port 8000
```

或：

```bash
python -m app_server.main
```

浏览器访问：

```text
http://localhost:8000
```

常用 API：

- `GET /api/health`
- `GET /api/diagnostics`
- `POST /api/chat`
- `GET /api/graph/summary`
- `GET /api/graph/search?q=滑坡`
- `GET /api/disasters/events`
- `POST /api/documents/upload`
- `GET /api/documents`

部署示例见 `deploy/README_DEPLOY.md`。生产环境请使用 `.env` 配置 DeepSeek API Key，不要提交 `.env`。

### FastAPI 部署前检查

```bash
python scripts/check_server_ready.py
python -m pytest tests/test_fastapi_app.py -q
uvicorn app_server.main:app --host 127.0.0.1 --port 8000 --workers 1
```

浏览器或命令行检查：

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/api/health
http://127.0.0.1:8000/api/diagnostics
```

## 使用示例

可以提问：

- 地震时在家应该怎么做？
- 洪水来了往哪个方向跑？
- 国家自然灾害救助应急响应有几个等级？
- 最近有什么地震？
- 当前有哪些洪水或气旋预警？

地图页可输入参考经纬度和半径，筛选附近灾害事件，并导出灾害简报。

## 评测脚本

项目提供两个便捷脚本，会自动进入项目根目录并激活 `venv`，不需要手动执行 `source venv/bin/activate`。

### 快速评测

```bash
bash scripts/eval_fast.sh
```

等价于：

```bash
python tests/run_eval.py --fast
```

用于快速检查核心链路，默认评测 5 题、跳过实时数据同步，并缩短回答预览。

### 分批完整评测

```bash
bash scripts/eval_all_batches.sh
```

脚本会依次运行：

```bash
python tests/run_eval.py --start 1 --limit 10 --skip-sync
python tests/run_eval.py --start 11 --limit 10 --skip-sync
python tests/run_eval.py --start 21 --limit 10 --skip-sync
```

适合本地大模型生成速度较慢时分段观察评测结果。若某一批存在失败，脚本会继续跑完后续批次，并在最后返回失败状态。

也可以直接运行评测器：

```bash
source venv/bin/activate
python tests/run_eval.py --limit 10 --skip-sync
python tests/run_eval.py --start 11 --limit 5 --skip-sync
python tests/run_eval.py --fast
```

评测输出包含题号、PASS / FAIL、来源数、单题耗时、失败原因、回答预览、总耗时、平均耗时和失败题目列表。

当前已验证：

- 前 10 道核心问题通过率：100%
- 快速模式 5 题通过率：100%

## 数据与隐私说明

以下内容属于本地运行产物或敏感信息，已通过 `.gitignore` 排除，不会提交到 GitHub：

- `.env`
- `venv/`
- `models/`
- `logs/`
- `data/cache/`
- `data/chroma_db/`
- `__pycache__/`

仓库仅保留代码、示例知识库文档、评测题库和配置模板。真实 API Key、模型权重、向量数据库、缓存数据请在本地自行准备。

DeepSeek API 模式下的数据边界：

- 本地上传文档仍存储在本机。
- ChromaDB 向量库仍存储在本机。
- 实时灾害缓存仍存储在本机。
- 每次问答只会把用户问题、对话历史摘要和本次检索命中的文档/实时事件片段发送给 DeepSeek API。
- 系统不会主动一次性上传整个知识库。
- 如果资料敏感，请不要上传敏感个人信息、机密文档或隐私数据；云端 API 调用存在第三方处理风险。

## 后续改进方向

- 拆分 prompt 处理速度和输出生成速度，进一步定位慢查询瓶颈。
- 增加更多中文灾害应急专业文档，提升 RAG 覆盖面。
- 接入更多权威数据源，并增强实时数据异常恢复能力。
- 增加 CI 检查，例如 Python 编译检查、JSON 校验和轻量评测。

## 长沙权威灾害采集

新增的长沙中心采集模块用于采集公开发布的洪水、山洪、滑坡、泥石流、地质灾害气象风险预警、水情雨情等信息。数据源配置在 `configs/disaster_sources.yaml`，采集结果保存到 `data/disaster_events.sqlite3`，不会替换原有 CENC / USGS / GDACS / Firecrawl 实时事件链路。

手动运行：

```bash
python -m app.crawlers.scheduler --once
python -m app.crawlers.scheduler --source hunan_natural_resource
python -m app.crawlers.scheduler --all
```

新增接口：

```text
GET  /api/disaster-events/latest
GET  /api/disaster-events/geojson
GET  /api/disaster-sources
POST /api/crawler/run?source_id=hunan_natural_resource
```

`POST /api/crawler/run` 需要管理员 JWT。前端灾害事件页会合并展示官方采集事件，并在有坐标时尝试加载 Leaflet 地图；Leaflet 加载失败时自动回退到坐标占位卡片。

服务器定时任务示例：

```cron
*/30 * * * * cd /opt/rag-disaster-kb && /opt/rag-disaster-kb/venv/bin/python -m app.crawlers.scheduler --once >> logs/official_crawler.log 2>&1
```

当前 enabled=true 的 MVP 数据源：

- 湖南省自然资源厅地质灾害预警
- 中央气象台灾害预警
- 湖南省水利厅
- 长沙市水利局
- 长沙市自然资源和规划局

其余全国、湖南和长沙扩展源已在配置文件中预留为 `enabled=false`。所有采集只访问公开网页、公开 JSON 或公开 PDF，不绕过登录、验证码或非公开接口。当前 MVP parser 采用通用公告页解析，若某个网站栏目结构变化或 robots.txt 不允许访问，会记录错误并继续处理其他数据源；后续可在 `app/crawlers/parsers/` 下针对单个源增强解析规则。
