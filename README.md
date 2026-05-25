# Real-Time Geological Disaster Information Query

实时地质灾害信息查询与灾害知识问答系统。项目基于 Streamlit、ChromaDB、本地 Qwen GGUF 大模型和 Ollama Embedding，结合 CENC、USGS、GDACS 等实时灾害数据源，提供中文灾害知识问答、地图展示、附近灾害筛选、来源追踪、导出和规则评测能力。

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
  -> 本地 LLM 流式生成
  -> 中文回答与来源标注
```

主要组件：

| 组件 | 技术 | 默认位置 |
| --- | --- | --- |
| UI | Streamlit | `http://localhost:8501` |
| LLM | llama.cpp server + Qwen GGUF | `http://127.0.0.1:8080/v1` |
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

安装并启动 Ollama Embedding：

```bash
ollama pull nomic-embed-text:v1.5
ollama serve
```

准备 Qwen GGUF 模型文件。模型文件通常较大，不提交到 GitHub。默认配置会查找：

```text
models/Qwen_Qwen3.5-9B-Q4_K_M.gguf
```

也可以通过 `.env` 或启动脚本参数调整模型路径。

## 启动项目

推荐使用一键启动脚本：

```bash
bash start_all.sh
```

该脚本会检查 Ollama、Embedding 模型、llama.cpp server、Qwen GGUF 模型和 Streamlit 端口，并给出清晰的错误提示。

手动启动时可分两步：

```bash
bash scripts/run_llama.sh models/Qwen_Qwen3.5-9B-Q4_K_M.gguf
streamlit run src/ui/app.py --server.headless true
```

浏览器访问：

```text
http://localhost:8501
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

## 后续改进方向

- 在评测输出中增加 token 统计，区分输入过长、输出过长和生成速度瓶颈。
- 增加更多中文灾害应急专业文档，提升 RAG 覆盖面。
- 接入更多权威数据源，并增强实时数据异常恢复能力。
- 增加 CI 检查，例如 Python 编译检查、JSON 校验和轻量评测。
