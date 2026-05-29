# 行业标准知识图谱使用指南

## 1. 用途

将行业标准文档（如地质灾害评估规范、建筑抗震规范等）解析为结构化知识图谱，支持：

- **标准检索**：按标准编号、行业、关键词查找标准
- **条款查询**：检索特定条款内容及其所属章节
- **要求提取**：自动识别强制性要求（应）、推荐要求（宜）、允许要求（可）
- **指标抽取**：识别标准中的数值指标参数（如"稳定系数不小于 1.15"）
- **术语管理**：提取标准中定义的术语及定义
- **关联分析**：查询某对象（如"滑坡"）相关的所有标准条款

## 2. 节点类型

| 节点 | 标签 | 说明 |
|------|------|------|
| StandardDocument | `StandardDocument` | 行业标准文档 |
| Chapter | `Chapter` | 章节 |
| Clause | `Clause` | 条款 |
| Term | `Term` | 术语定义 |
| Requirement | `Requirement` | 规范要求 |
| Indicator | `Indicator` | 指标参数 |
| Method | `Method` | 方法/技术 |
| StandardObject | `StandardObject` | 适用对象 |

## 3. 关系类型

| 关系 | 方向 | 说明 |
|------|------|------|
| `HAS_CHAPTER` | StandardDocument → Chapter | 标准包含章节 |
| `HAS_CLAUSE` | StandardDocument → Clause | 标准包含条款 |
| `HAS_CLAUSE` | Chapter → Clause | 章节包含条款 |
| `HAS_SUB_CLAUSE` | Clause → Clause | 条款包含子条款 |
| `DEFINES` | StandardDocument → Term | 标准定义术语 |
| `DEFINES` | Clause → Term | 条款定义术语 |
| `HAS_REQUIREMENT` | Clause → Requirement | 条款包含要求 |
| `HAS_INDICATOR` | Clause → Indicator | 条款包含指标 |
| `USES_METHOD` | Clause → Method | 条款使用的方法 |
| `APPLIES_TO` | Clause → StandardObject | 条款适用对象 |
| `REFERENCES` | StandardDocument → StandardDocument | 标准引用 |

## 4. Markdown 文档格式要求

标准文档应为 Markdown 或纯文本格式，使用数字编号标题：

```markdown
# 1 总则
## 1.1 目的
内容...

# 2 术语和定义
## 2.1 地质灾害
指自然因素或人为活动引发的...

# 3 基本规定
## 3.1 一般规定
### 3.1.1 评估原则
地质灾害评估应采用定性与定量相结合的方法。

### 3.1.2 安全系数
滑坡稳定性计算的安全系数不应小于 1.15。
```

支持的标题格式：
- Markdown 标题：`# 1 标题`、`## 1.1 标题`
- 纯数字标题：`1 标题`、`1.1 标题`、`3.1.2 标题`
- 混合格式：`3.1.2 具体条款内容`

## 5. 单个标准导入示例

```bash
python scripts/import_standard_graph.py \
    --file data/standards/DZ_T_0286-2015.md \
    --code "DZ/T 0286-2015" \
    --title "地质灾害危险性评估规范" \
    --industry "geological_disaster" \
    --issuing-body "国土资源部"
```

输出：
```
==================================================
Import complete
==================================================
  Standard:     DZ/T 0286-2015 — 地质灾害危险性评估规范
  Standard ID:  std-a1b2c3d4e5f6
  Chapters:     8
  Clauses:      45
  Terms:        12
  Requirements: 23
  Indicators:   15
  Methods:      8
  Objects:      6
  Relationships: 89
```

预览模式（不写入 Neo4j）：

```bash
python scripts/import_standard_graph.py \
    --file data/standards/example.md \
    --code "DZ/T xxxx-xxxx" \
    --title "测试标准" \
    --industry "geological_disaster" \
    --dry-run
```

## 6. 批量标准导入建议

```bash
# 将多个标准放在同一目录下
for f in data/standards/*.md; do
    echo "Importing $f..."
    python scripts/import_standard_graph.py \
        --file "$f" \
        --code "$(basename "$f" .md)" \
        --title "$(head -1 "$f" | sed 's/^# //')" \
        --industry "geological_disaster"
done
```

## 7. 查询命令

```bash
# 按标准编号查询
python scripts/query_standard_graph.py --code "DZ/T 0286-2015"

# 查看完整章节树
python scripts/query_standard_graph.py --code "DZ/T 0286-2015" --tree

# 搜索关键词
python scripts/query_standard_graph.py --keyword "滑坡"

# 查询强制性要求
python scripts/query_standard_graph.py --requirements

# 查询指标参数
python scripts/query_standard_graph.py --indicators

# 查询某对象相关条款
python scripts/query_standard_graph.py --object "泥石流"

# 查看条款子图
python scripts/query_standard_graph.py --clause-id "cl-xxxxxxxxxxxx"
```

## 8. Neo4j Browser 可视化查询

在 Neo4j Browser 中执行以下 Cypher：

```cypher
// 查看标准完整图谱
MATCH (s:StandardDocument {code: "DZ/T 0286-2015"})
MATCH (s)-[*1..3]->(n)
RETURN s, n

// 查看所有强制性要求
MATCH (r:Requirement {obligation: "shall"})
MATCH (r)<-[:HAS_REQUIREMENT]-(cl:Clause)
MATCH (cl)<-[:HAS_CLAUSE*1..2]-(s:StandardDocument)
RETURN s, cl, r
LIMIT 50

// 查看某个指标相关的完整上下文
MATCH (i:Indicator {name: "滑坡稳定系数"})
MATCH (i)<-[:HAS_INDICATOR]-(cl:Clause)
MATCH (cl)<-[:HAS_CLAUSE*1..2]-(s:StandardDocument)
OPTIONAL MATCH (cl)-[:HAS_REQUIREMENT]->(r:Requirement)
RETURN s, cl, i, r

// 跨标准术语关联
MATCH (t:Term {name: "地质灾害"})
MATCH (t)<-[:DEFINES]-(source)
RETURN t, source
```

## 9. 常见问题

**Q: 导入失败，提示 Neo4j 连接失败？**
A: 确认 Neo4j 已启动，检查 `.env` 中的 `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD`。

**Q: 如何设置环境变量？**
A: 在项目根目录的 `.env` 文件中添加：
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=neo4j
```

**Q: 条款没有被正确拆分？**
A: 检查 Markdown 标题格式是否符合要求。parser 识别以下格式：
- `# 1 标题` (Markdown heading)
- `1 标题` (纯数字标题)
- 对于无标题的文档，整体作为一个条款导入

**Q: "应/宜/可"要求没有全被抽取？**
A: 规则抽取基于正则匹配，对复杂句式可能遗漏。可以待后续启用 LLM 增强抽取。

**Q: 如何清空图谱重新导入？**
A: 在 Neo4j Browser 中执行：
```cypher
MATCH (n) DETACH DELETE n
```
然后重新运行导入脚本。

## 10. 深度学习抽取模型扩展

### 10.1 概述

系统在规则抽取基础上预留了深度学习模型接口，支持：

- **NER（命名实体识别）**：BiLSTM-CRF、BERT-BiLSTM-CRF
- **RE（关系抽取）**：CasRel、PRGC

深度学习模型为可选增强。没有模型权重时，系统自动 fallback 到规则抽取，所有功能正常工作。

### 10.2 抽取模式

| 模式 | 说明 | 依赖 |
|------|------|------|
| `rule` | 基于正则和关键词的规则抽取（默认） | 无 |
| `bilstm_crf` | BiLSTM + CRF 序列标注 | PyTorch |
| `bert_bilstm_crf` | BERT 编码 + BiLSTM + CRF | PyTorch + transformers |
| `casrel` | CasRel 级联二元标注关系抽取 | PyTorch + transformers |
| `prgc` | PRGC 全局对应关系抽取 | PyTorch + transformers |

### 10.3 实体类型（BIO 标签）

11 种实体类型使用 BIO 标注：STANDARD、CHAPTER、CLAUSE、TERM、REQUIREMENT、INDICATOR、METHOD、OBJECT、ORGANIZATION、LOCATION、DISASTER_TYPE。

示例：`B-TERM` / `I-TERM` / `B-REQUIREMENT` / `I-REQUIREMENT` / `O`

### 10.4 关系类型

11 种关系：HAS_CHAPTER、HAS_CLAUSE、HAS_SUB_CLAUSE、DEFINES、HAS_REQUIREMENT、HAS_INDICATOR、USES_METHOD、APPLIES_TO、ISSUED_BY、REFERENCES、RELATED_TO_DISASTER。

### 10.5 训练数据格式

**NER 标注数据** (`data/annotations/ner_sample.jsonl`)：

```json
{
  "text": "滑坡调查应包括资料收集、现场踏勘和综合分析。",
  "tokens": ["滑", "坡", "调", "查", "应", "包", "括", ...],
  "labels": ["B-OBJECT", "I-OBJECT", ..., "B-METHOD", "I-METHOD", ...]
}
```

**RE 标注数据** (`data/annotations/re_sample.jsonl`)：

```json
{
  "text": "滑坡调查应包括资料收集、现场踏勘和综合分析。",
  "spo_list": [
    {"subject": "滑坡调查", "predicate": "HAS_REQUIREMENT", "object": "应包括..."},
    {"subject": "滑坡调查", "predicate": "USES_METHOD", "object": "现场踏勘"}
  ]
}
```

### 10.6 数据准备脚本

```bash
# 验证 NER 标注数据
python scripts/prepare_ner_dataset.py --validate-only

# 转换为训练格式
python scripts/prepare_ner_dataset.py

# 验证 RE 标注数据
python scripts/prepare_re_dataset.py --validate-only

# 转换为训练格式
python scripts/prepare_re_dataset.py
```

### 10.7 CLI 参数说明

```bash
# 纯规则模式（默认，不需要模型）
python scripts/import_standard_graph.py \
    --file data/standards/example.md \
    --code "DZ/T XXXX-XXXX" \
    --title "测试标准" \
    --industry "geological_disaster" \
    --ner-model-type rule \
    --re-model-type rule

# 未来：深度学习模型模式
python scripts/import_standard_graph.py \
    --file data/standards/example.md \
    --code "DZ/T XXXX-XXXX" \
    --title "测试标准" \
    --industry "geological_disaster" \
    --ner-model-type bert_bilstm_crf \
    --ner-model-path models/ner/bert_bilstm_crf.pt \
    --re-model-type casrel \
    --re-model-path models/re/casrel.pt
```

### 10.8 自动 Fallback 机制

当以下情况发生时，系统自动降级为规则抽取：

- PyTorch 未安装
- transformers 未安装
- 模型权重文件不存在
- 模型加载异常
- 推理过程出错

降级时会记录 warning 日志，不会中断导入流程。

### 10.9 当前阶段说明

- 模型文件（bilstm_crf.py、bert_bilstm_crf.py、casrel.py、prgc.py）提供了完整的工程骨架和接口定义
- 不包含预训练权重，不默认训练模型
- 规则抽取（rule_ner.py、rule_re.py）完全可用
- 训练数据格式已定义，数据准备脚本可用
- 后续可在此基础上进行标注数据积累和模型训练

## 11. PDF 行业标准导入流程

### 11.1 支持的文件格式

| 格式 | 解析方式 | 说明 |
|------|----------|------|
| `.md` / `.txt` | 直接读取 UTF-8 文本 | 推荐格式 |
| `.pdf` | PyMuPDF (fitz) 提取文字 | 需要 `pip install pymupdf` |

### 11.2 普通 PDF 导入

```bash
# 步骤 1：检查文件是否可解析（不写入 Neo4j）
python scripts/check_standard_file.py \
    --file data/standards/pdf/example.pdf

# 步骤 2：查看提取的文本（保存中间文本）
python scripts/check_standard_file.py \
    --file data/standards/pdf/example.pdf \
    --save-intermediate

# 步骤 3：dry-run（完整解析和抽取，不写入 Neo4j）
python scripts/import_standard_graph.py \
    --file data/standards/pdf/example.pdf \
    --code "DZ/T XXXX-XXXX" \
    --title "标准标题" \
    --industry "geological_disaster" \
    --save-intermediate \
    --dry-run

# 步骤 4：正式写入 Neo4j
python scripts/import_standard_graph.py \
    --file data/standards/pdf/example.pdf \
    --code "DZ/T XXXX-XXXX" \
    --title "标准标题" \
    --industry "geological_disaster" \
    --save-intermediate
```

### 11.3 扫描版 PDF 判断

系统在解析 PDF 时会自动检测扫描版：

- 如果超过 70% 的页面无法提取到文字（每页 < 30 字符），标记为疑似扫描版
- 导入脚本会输出警告：`该 PDF 可能是扫描版，需要 OCR 后再导入`
- 检查脚本会显示：`疑似扫描版: 是 ⚠️`

扫描版 PDF 的处理建议：

1. 使用 OCR 工具（如 Tesseract + pdf2image）将扫描页转为文字
2. 将 OCR 结果整理为 Markdown 格式
3. 使用 `.md` 导入

### 11.4 保存中间文本

`--save-intermediate` 参数会将 PDF 提取的文字保存到：

```
data/standards/converted/<原文件名>.txt
```

方便人工检查提取质量，或手动修正后再导入。

### 11.5 Dry-run 输出

`--dry-run` 输出包含：

- 标准编号、标题、行业
- 章节数量和前 5 个章节
- 条款数量和前 5 个条款
- 术语/要求/指标/方法/对象 的抽取数量和前 5 个样例

### 11.6 在 Neo4j Browser 查看导入结果

```cypher
// 按标准编号查找
MATCH (s:StandardDocument {code: "DZ/T XXXX-XXXX"})
MATCH (s)-[*1..2]->(n)
RETURN s, n

// 查看所有强制性要求
MATCH (s:StandardDocument {code: "DZ/T XXXX-XXXX"})
MATCH (s)-[:HAS_CLAUSE*1..2]->(cl:Clause)
MATCH (cl)-[:HAS_REQUIREMENT]->(r:Requirement)
RETURN cl.clause_number, r.text, r.obligation
```
