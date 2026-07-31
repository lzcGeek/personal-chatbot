# NewAgent RAG PDF 解析与第一阶段召回重排优化报告

## 1. 报告结论

本阶段针对两个已经定位清楚的失败类型进行了优化：

- **Quick ratio**：正确证据已经进入 Dense Top-30，但因为向量只表示中心
  Chunk、词项重排无法理解派生指标，最终没有进入 Top-6。
- **Acquisitions**：正确证据只在相邻上下文组合后完整，原中心 Chunk 的向量
  相似度只有 `0.3508`，低于 `0.45` 阈值，无法进入候选池。

完成上下文向量化、查询扩展、词项归一化、字段加权重排及候选池扩展后，
同一份 5 条黄金证据快测结果如下：

| 指标 | PDF 修复后的阶段基线 | 第一阶段最终结果 |
|---|---:|---:|
| Gold Evidence Hit Rate@6 | 0.600 | **1.000** |
| Gold Evidence Recall@6 | 0.600 | **1.000** |
| MRR | 0.333 | **0.383** |
| 平均最佳证据覆盖率 | 0.682 | **0.967** |

最终 5 条用例全部命中，但这只是一个小规模开发集结果，不能直接等同于生产
数据上的 100% 准确率。

## 2. 前置修复：PDF 页面与表格证据丢失

### 2.1 问题表现

第一阶段召回优化开始前，Debt securities 用例即使检索到了 American Express
年报的相关页，黄金证据覆盖率仍然只有 `0.080`。

最初将它归因于“财务表格解析能力不足”，但对黄金证据和原 PDF 进行逐页核对后
发现：

- 黄金证据位于 PDF 第 1 页，不是检索结果中的第 162 页。
- 第 1 页包含证券登记信息：

  ```text
  Securities registered pursuant to Section 12(b) of the Act
  Title of each class
  Trading Symbol(s)
  Name of each exchange on which registered
  Common Shares ... AXP ... New York Stock Exchange
  ```

- PostgreSQL 中第一个 American Express Chunk 从 PDF 第 2 页开始。
- PDF 第 1 页在解析阶段被整页跳过，因此无论怎样调整 Top-K 都无法召回。

这说明当时的主要问题不是“召回没有找到第 1 页”，而是“第 1 页根本没有进入
Chunk 和向量索引”。

### 2.2 根因定位

当前默认解析模式为：

```text
pypdf Layout + pdfplumber 表格提取
```

对 American Express 第 1 页实测得到：

| 提取方式 | 结果 |
|---|---:|
| `pypdf.extract_text(extraction_mode="layout")` | 0 字 |
| `pypdf.extract_text()` 普通模式 | 4242 字 |
| `pdfplumber.extract_text()` | 可提取完整证券登记信息 |
| `pdfplumber.find_tables()` 默认策略 | 0 张表 |

这是一张没有完整网格边框的封面表格。pdfplumber 默认表格检测没有识别出表格
边界，但普通文本提取能够保留标题、证券名称、交易代码和交易所。

旧代码的关键流程是：

```python
layout_text = self._layout_text(page)

if not self._looks_like_table(layout_text):
    if layout_text:
        units.append(...)
    continue
```

当 `layout_text == ""` 时，代码直接 `continue`，没有继续尝试 pypdf 普通模式
或 pdfplumber 文本模式，因此整页丢失。

### 2.3 已实现的逐页降级链

文件：

- `backend/app/services/document_parser.py`

修复后的逐页提取顺序为：

```text
pypdf Layout
→ 如果为空，使用 pypdf 普通文本
→ 如果仍为空，使用 pdfplumber Layout/普通文本
→ 三种方式都为空时才跳过该页
```

对应的解析来源会写入 Chunk 元数据：

```text
pypdf_layout
pypdf_plain_fallback
pdfplumber_text_fallback
```

修复后的核心逻辑：

```python
page_text, fallback_parser = self._pypdf_page_text(page)

if not page_text:
    page_text = self._pdfplumber_text(plumber_page)
    fallback_parser = "pdfplumber_text_fallback"

if not page_text:
    continue
```

如果页面文本疑似包含表格，仍然继续执行原有的 pdfplumber 表格抽取和 Markdown
表格转换；如果默认表格识别找不到边界，则保留已经成功提取的页面文本，而不是
丢掉整页。

该方案不是针对 FinanceBench 文件名或固定页码的特殊判断，而是通用的单页
解析降级机制。

### 2.4 为什么没有强制使用文本策略识别无边框表格

诊断中也尝试了 pdfplumber 的文本线索表格策略。它虽然能在封面页识别出一个
区域，但会把整张封面错误切成约 18 列，将标题、复选框和正文混入同一张表。

因此本阶段采用更稳妥的策略：

```text
能够可靠识别表格边界
→ 转成 Markdown 表格

无法可靠识别表格边界
→ 保留 Layout/普通文本
```

对于 RAG 来说，证券名称、交易代码和交易所仍然保持正确的阅读顺序，已经足以
支持语义检索和回答；错误的结构化表格反而可能破坏原始语义。

### 2.5 回归测试

文件：

- `backend/tests/test_document_pipeline.py`

新增测试覆盖：

1. Layout 返回空、pypdf 普通模式有文本时，必须生成
   `pypdf_plain_fallback` ParsedUnit。
2. pypdf 两种模式都为空、pdfplumber 有文本时，必须生成
   `pdfplumber_text_fallback` ParsedUnit。
3. 保留原有表格抽取、不重复正文表格内容、页码溯源和 layout-only 模式测试。

PDF 文档流水线测试结果：

```text
12 passed
```

### 2.6 真实文档验证

修复后重新索引 American Express 文档：

| 项目 | 修复前 | 修复后 |
|---|---:|---:|
| 文档 Chunk 数 | 1153 | 1158 |
| PDF 第 1 页 Chunk | 0 | 5 |
| 第 1 页解析器 | 无 | `pypdf_plain_fallback` |
| Debt 黄金证据覆盖率 | 0.080 | 0.980 |
| Debt 最终排名 | 未命中 | Top-1 |

修复 PDF 页面丢失后，5 条快测的整体指标从：

```text
Hit@6 0.400 → 0.600
Recall@6 0.400 → 0.600
MRR 0.133 → 0.333
平均覆盖率 0.502 → 0.682
```

### 2.7 为什么修复后必须重新索引

解析器修改只影响以后生成的 ParsedUnit。已经存在于 PostgreSQL 和 Qdrant 中的
Chunk、向量不会自动变化，因此必须重新执行：

```text
原 PDF
→ 新解析器
→ 新 Chunk
→ 新 Embedding
→ 覆盖 Qdrant 文档向量
```

只重启后端但不重新索引，旧文档仍然缺少第 1 页证据。

## 3. 优化前的问题

### 3.1 索引文本与返回证据不一致

优化前，Qdrant 向量由中心 `chunk.content` 生成，而实际交给模型、用于评测的
证据是 `chunk.context_text`：

```text
context_text = 前一个 Chunk + 中心 Chunk + 后一个 Chunk
```

这会造成以下错位：

```text
向量检索看到：中心 Chunk
最终回答看到：带相邻上下文的完整证据
```

Acquisitions 的中心 Chunk 从句子中间开始，章节标题、年份和第一项收购主要位于
前一个 Chunk。虽然 `context_text` 能完整覆盖黄金证据，但中心 Chunk 向量无法
表达完整主题。

Quick ratio 也存在类似问题：计算需要同时看到流动资产和流动负债，而它们被
分布在相邻的表格 Chunk 中。

### 3.2 原词项覆盖率无法区分候选

原重排公式为：

```text
最终排序分数 = Dense 相似度 + 0.35 × 查询词项覆盖率
```

Quick ratio 查询产生的主要词项为：

```text
amcor, quick, ratio, improved, declined, fy2023, fy2022
```

财务报表通常不会直接出现 `quick ratio improved`，只会提供计算所需的
`cash`、`receivables`、`current liabilities` 等数据。大量 Chunk 只能匹配
公司名，得到相同加分，因此正确 Chunk 的排名没有提升。

此外，文件名、章节、正文和上下文原来被无差别拼接，文件名中的公司词可能让
同一文档的大量 Chunk 获得相似加分。

### 3.3 Dense Top-30 对 Acquisitions 不够

诊断过程中的正确证据排名变化如下：

| 阶段 | Dense 排名 | Dense 分数 | 结果 |
|---|---:|---:|---|
| 中心 Chunk 向量 | 184 | 0.3508 | 低于 0.45，被过滤 |
| 上下文向量 + 初版扩展 | 107 | 0.4811 | 越过阈值，但未进 Top-30 |
| 上下文向量 + 精炼扩展 | 71 | 0.5046 | 越过阈值，但仍需扩大候选池 |
| Dense Top-100 + 字段重排 | 71 → 6 | 0.5046 | 最终 Top-6 命中 |

因此，单纯降低阈值或把最终 Top-K 改大都不是合适方案。需要扩大内部候选池，
然后仍然只把重排后的 Top-6 交给模型。

## 4. 已实现的改动

### 4.1 使用 `context_text` 生成文档向量

文件：

- `backend/app/services/document_index_worker.py`

核心改动：

```python
contents = [chunk.context_text for chunk in batch]
vectors = await self.embedding_service.embed_batch(contents)
```

效果：

- 向量索引和最终证据使用同一语义窗口。
- 表格的相邻行、章节标题和跨段事实能够参与向量召回。
- 不增加 Qdrant 点数，也不需要数据库迁移。

代价：

- 单条 Embedding 输入比中心 Chunk 更长。
- 重新索引时间和 Embedding Token 消耗会有所增加。
- 相邻 Chunk 的向量相似度可能更高，需要依赖现有近似去重。

### 4.2 增加可扩展的查询扩展

文件：

- `backend/app/services/document_knowledge_service.py`

当前包含以下通用财务概念扩展：

```text
quick ratio
→ quick assets, cash, cash equivalents, short-term investments,
  marketable securities, accounts receivable, trade receivables,
  current liabilities

current ratio
→ current assets, current liabilities

acquisition / acquisitions
→ acquisitions and divestitures, completed acquisition,
  equity interest, purchase consideration
```

原问题仍被保留，扩展词只作为补充。这样可以缩小“用户提问术语”和“原文证据
术语”之间的差距。

收购扩展没有继续使用 `acquired intangible assets` 或
`business combination`，因为消融实验发现这些词容易召回无形资产摊销和
非 GAAP 调整段落。

### 4.3 查询词项清洗与归一化

实现内容：

- `FY2023 → 2023`、`FY2022 → 2022`
- `acquisitions → acquisition`
- `liabilities → liability`
- 下划线按词边界处理
- 查询重排阶段去掉低价值词，例如：
  `done`、`major`、`improved`、`declined`、`calculate`

这些词不会从用户原问题中删除，只是不再参与规则重排的分母。

### 4.4 字段加权词项重排

新的词项覆盖率不再把所有字段无差别拼接，而是分别计算：

```text
词项相关度 =
    正文/上下文覆盖率
  + 0.25 × 章节覆盖率
  + 0.10 × 文件名覆盖率
```

最终排序仍保持：

```text
最终排序分数 = Dense 相似度 + 0.35 × 词项相关度
```

作用：

- 正文和上下文是主要信号。
- 章节标题可以提供额外主题证据。
- 文件名仍可帮助区分不同公司或文档，但不能像正文一样主导排序。

已有的失败意图加分和近似去重逻辑继续保留。

### 4.5 候选池从 30 调整为 100

配置：

```env
DOCUMENT_VECTOR_CANDIDATE_LIMIT=100
DOCUMENT_RESULT_LIMIT=6
DOCUMENT_RELEVANCE_THRESHOLD=0.45
```

这里有两个不同的 K：

```text
Dense 候选 K = 100
最终返回 K = 6
```

Qdrant 最多返回 100 个候选用于 PostgreSQL 取回、规则重排和去重；最终仍只把
6 个证据交给模型。因此不会把 100 个 Chunk 塞入对话上下文。

本阶段保留 `0.45` 阈值。Acquisitions 正确证据经过上下文向量化和查询扩展后
已经达到 `0.5046`，无需为了单个用例整体降低阈值。

## 5. 当前检索流程

```mermaid
flowchart LR
    A["用户问题"] --> B["去掉回答格式后置指令"]
    B --> C["派生指标/主题查询扩展"]
    C --> D["Dense Embedding"]
    D --> E["Qdrant Top-100<br/>阈值 0.45"]
    E --> F["PostgreSQL 读取有效 Chunk"]
    F --> G["字段加权词项重排"]
    G --> H["精确去重与近似去重"]
    H --> I["最终 Top-6"]
```

图谱当前关闭，因此本报告中的所有结果都来自文本向量检索，没有图谱分数参与。

## 6. 评测结果

### 6.1 阶段对比

| 阶段 | Hit@6 | Recall@6 | MRR | 平均覆盖率 |
|---|---:|---:|---:|---:|
| 清理残留向量后的原流程 | 0.400 | 0.400 | 0.133 | 0.502 |
| 修复 PDF 第 1 页丢失 | 0.600 | 0.600 | 0.333 | 0.682 |
| 上下文向量 + 初版重排 | 0.800 | 0.800 | 0.367 | 0.778 |
| 第一阶段最终版本 | **1.000** | **1.000** | **0.383** | **0.967** |

### 6.2 最终逐题结果

| 用例 | 最终排名 | 最佳证据覆盖率 | 状态 |
|---|---:|---:|---|
| Quick ratio | 3 | 0.898 | 命中 |
| Acquisitions | 6 | 1.000 | 命中 |
| Industry | 6 | 1.000 | 命中 |
| Gross margin | 4 | 0.957 | 命中 |
| Debt securities | 1 | 0.980 | 命中 |

最终原始报告：

- `backend/evals/results/gold-retrieval-20260731-160319.md`
- `backend/evals/results/gold-retrieval-20260731-160319.json`

## 7. 测试与数据一致性

### 7.1 自动化测试

相关功能测试：

```text
37 passed
```

完整业务单元测试：

```text
108 passed, 3 skipped
```

直接运行不限定目录的 `pytest` 会收集 `evals/test_rag.py`。该文件需要独立的
`.venv-eval` 和 DeepEval，不属于业务 `.venv` 的单元测试范围。业务测试命令应为：

```powershell
cd <项目根目录>\backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

### 7.2 PostgreSQL 与 Qdrant 一致性

重新索引完成后的状态：

```text
ready 文档：2
PostgreSQL Chunk：1886
Qdrant 文档向量：1886
Qdrant 集合：document_chunks_dense_v3
```

当前不存在 Chunk 与向量数量不一致的问题。

## 8. 修改文件

核心实现：

- `backend/app/services/document_index_worker.py`
  - 使用 `context_text` 生成向量。
- `backend/app/services/document_knowledge_service.py`
  - 查询扩展、词项归一化、字段加权重排。
- `backend/app/core/config.py`
  - 默认候选池调整为 100。
- `.env`
  - 当前本地候选池调整为 100。
- `.env.example`
  - 示例配置同步为 100。

测试：

- `backend/tests/test_document_worker_pipeline.py`
  - 验证 Embedding 输入使用 `context_text`。
- `backend/tests/test_graph_controls.py`
  - 验证查询扩展、年份归一化和文件名弱权重。

本阶段也依赖前一阶段已经完成的 PDF 空 Layout 降级修复：

- `backend/app/services/document_parser.py`
- `backend/tests/test_document_pipeline.py`

## 9. 后续如何复测

黄金证据快测：

```powershell
cd <项目根目录>\backend
$env:EVAL_USERNAME="admin"
.\.venv\Scripts\python.exe evals\evaluate_gold_retrieval.py `
  --dataset evals\datasets\financebench_goldens_dev.json `
  --limit 5
```

结果会生成到：

```text
backend/evals/results/gold-retrieval-时间戳.md
backend/evals/results/gold-retrieval-时间戳.json
```

如果修改以下任意内容，需要重新索引已有文档：

- PDF 解析方式
- Chunk 大小或重叠窗口
- `document_context_window`
- Embedding 模型或维度
- 向量化使用的文本，例如 `content` 与 `context_text`

只修改查询扩展、候选 K、重排公式或最终 Top-K 时，不需要重新生成文档向量，
但需要重启后端加载新代码和配置。

## 10. 当前局限

1. 评测集只有 5 条开发用例，需要继续扩展到 30/50 条，并加入非财务文档，
   防止针对少量问题产生过拟合。
2. 查询扩展目前是规则表，只覆盖少量派生指标和收购表达；未知术语仍可能存在
   查询与证据词汇不一致。
3. Acquisitions 和 Industry 都位于最终第 6，虽然已经命中，但排序余量较小。
4. 当前重排仍是规则重排，不是 Cross-Encoder 模型精排。
5. 候选池从 30 增加到 100 会增加少量 Qdrant 返回、PostgreSQL 读取和本地重排
   开销；最终模型上下文数量不变。
6. `context_text` 向量会增加相邻 Chunk 之间的向量相似度，目前依赖近似去重控制
   重复证据，后续应在更大评测集上观察证据多样性。

下一阶段如需继续提升首位命中率，建议优先建立 30/50 条通用评测集，再比较：

- 当前规则重排；
- Dense + Sparse/BM25 + RRF；
- Cross-Encoder Top-30 精排。

不建议在没有更大评测集的情况下继续针对这 5 条问题增加专用规则。
