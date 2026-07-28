# DeepEval 评测运行指南

本项目使用 DeepEval 对 RAG / GraphRAG 的检索质量和回答质量进行评测。

DeepEval 安装在独立的 `backend/.venv-eval` 虚拟环境中，避免其 `click` 版本要求与后端主环境中的依赖发生冲突。正常启动后端仍使用 `backend/.venv`。

## 1. 当前环境

- 后端运行环境：`backend/.venv`
- DeepEval 评测环境：`backend/.venv-eval`
- DeepEval 版本：`4.1.3`
- 评测依赖定义：`backend/pyproject.toml` 中的 `eval` 可选依赖

## 2. 首次创建评测环境

如果 `backend/.venv-eval` 不存在，在项目根目录执行：

```powershell
cd D:\ruijie\agent\newagent\backend

python -m venv .venv-eval
.\.venv-eval\Scripts\pip.exe install -e ".[dev,eval]"
```

不要把 DeepEval 安装进主环境 `backend/.venv`。

## 3. 验证安装

```powershell
cd D:\ruijie\agent\newagent\backend

.\.venv-eval\Scripts\python.exe -c "import importlib.metadata as m; print(m.version('deepeval'))"
.\.venv-eval\Scripts\pip.exe check
```

预期版本输出：

```text
4.1.3
```

依赖检查应输出：

```text
No broken requirements found.
```

## 4. 推荐目录结构

```text
backend/
├─ app/
├─ tests/                         # 普通单元测试和集成测试
├─ evals/
│  ├─ test_rag.py                 # DeepEval 测试入口
│  ├─ datasets/
│  │  └─ rag_goldens.json         # 问题、标准答案和可接受来源
├─ .venv/                         # 后端主环境
├─ .venv-eval/                    # DeepEval 独立环境
└─ pyproject.toml
```

## 5. 配置评测模型

DeepEval 的 RAG 指标大多需要 LLM-as-a-Judge。建议使用能力稳定、温度为 `0` 的模型作为裁判模型，并通过环境变量提供密钥，不要把密钥写进测试代码或提交到 Git。

如果评测代码复用本项目的 OpenAI 兼容配置，请确认项目根目录 `.env` 已配置：

```dotenv
OPENAI_BASE_URL=https://your-api.example.com/v1
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=your-model-name
```

评测模型最好与被评测的生成模型不同，以降低自评偏差。如果使用同一个模型，需要在评测报告中注明。

## 6. 运行前准备

当前 `evals/test_rag.py` 是端到端测试，会真实调用运行中的 NewAgent，而不是使用手工填写的回答。运行前必须：

1. 启动 PostgreSQL、Qdrant、Neo4j 和后端服务。
2. 创建一个专门用于评测的本地账号。
3. 使用该账号上传项目根目录下的 `README.md`、`PERSONAL_GRAPH_RAG.md` 和 `MULTI_USER_REFACTOR.md`。
4. 等待三个文档状态变为可检索。
5. 在项目根目录 `.env` 中填写：

```dotenv
EVAL_BASE_URL=http://127.0.0.1:8021
EVAL_USERNAME=你的评测账号
EVAL_PASSWORD=你的评测账号密码
EVAL_CASE_LIMIT=5
EVAL_REQUEST_TIMEOUT_SECONDS=180
EVAL_KEEP_CONVERSATIONS=false
```

默认只运行数据集的前 5 条，以控制生成模型和裁判模型费用。设置 `EVAL_CASE_LIMIT=0` 可运行全部用例。测试创建的会话默认在结束时删除；如需保留并在界面检查，设置 `EVAL_KEEP_CONVERSATIONS=true`。

## 7. 运行 DeepEval

进入后端目录：

```powershell
cd D:\ruijie\agent\newagent\backend
```

运行全部 RAG 评测：

```powershell
.\.venv-eval\Scripts\deepeval.exe test run evals\test_rag.py
```

输出详细评分过程与失败原因：

```powershell
.\.venv-eval\Scripts\deepeval.exe test run evals\test_rag.py -v
```

将 DeepEval 内部 JSON 转换为可读 Markdown 报告：

```powershell
.\.venv-eval\Scripts\python.exe evals\summarize_results.py
```

报告生成在 `backend/evals/results/rag-eval-latest.md`。DeepEval 的原始 JSON 位于隐藏目录 `backend/.deepeval`，主要面向程序和缓存，不建议直接阅读。

DeepEval 应使用 `deepeval test run`，不建议直接使用普通 `pytest` 执行评测用例。

## 8. 建议评测指标

### 检索质量

- `ContextualPrecisionMetric`：相关片段是否排在无关片段之前。
- `ContextualRecallMetric`：检索上下文是否包含回答问题所需的信息。
- `ContextualRelevancyMetric`：检索结果与问题是否相关。

### 回答质量

- `FaithfulnessMetric`：回答是否忠于实际检索到的上下文，是否存在幻觉。
- `AnswerRelevancyMetric`：回答是否直接回应用户问题。

### 建议额外统计

DeepEval 指标之外，建议同步记录：

- `Recall@6`
- 来源文档命中率
- 页码或章节引用准确率
- 平均检索延迟
- P95 检索延迟
- 单次评测 Token 消耗与费用

## 9. GraphRAG 对比方式

使用同一份测试集分别运行以下配置：

| 实验组 | Qdrant | Neo4j | 用途 |
|---|---:|---:|---|
| Vector Baseline | 开启 | 关闭 | 建立纯向量检索基线 |
| Hybrid GraphRAG | 开启 | 开启 | 评估混合检索效果 |
| Graph Only | 关闭 | 开启 | 验证关系型问题检索能力 |

对比时必须保持测试问题、标准答案、生成模型、裁判模型、Top-K 和分块参数一致，只改变检索策略。

建议至少准备 50 条问题；用于简历量化时建议准备 100～200 条，并单独统计事实型问题和关系型问题。

## 10. 普通后端测试

DeepEval 评测与项目原有测试使用不同环境。运行原有后端测试时继续使用主环境：

```powershell
cd D:\ruijie\agent\newagent\backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

## 11. 常见问题

### 找不到 `test_rag.py`

确认当前目录是 `backend`，并检查 `backend/evals/test_rag.py` 是否存在。

### 提示缺少 `EVAL_USERNAME` 或 `EVAL_PASSWORD`

在项目根目录 `.env` 中配置评测账号。不要把真实账号密码写入 `.env.example` 或提交到 Git。

### 提示没有文档引用

确认评测账号已经上传三份测试文档，并且文档状态已经变为可检索。测试会把接口返回的 `citations[].excerpt` 作为 DeepEval 的真实 `retrieval_context`；如果没有引用，说明当前问题没有召回测试文档。

### 裁判模型请求失败

检查 API 地址、密钥、模型名称和网络连接。部分 OpenAI 兼容服务可能不支持 DeepEval 所需的结构化输出，此时应更换裁判模型或实现自定义 DeepEval 模型适配器。

### 分数每次略有变化

LLM-as-a-Judge 本身存在随机性。建议将裁判模型温度设为 `0`，固定模型版本，并对正式测试重复运行 3 次后报告均值。

### 主环境出现 `click` 依赖冲突

确认执行的是 `.venv-eval\Scripts\pip.exe`，而不是 `.venv\Scripts\pip.exe`。DeepEval 不应安装在主后端环境中。
