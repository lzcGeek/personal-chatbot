# FinanceBench 30 题 RAG 测评操作与读数指南

这份文档用于反复执行 NewAgent 的端到端 RAG 测评。评测不是只测一个检索函数，而是走真实链路：登录评测账号 → 创建会话 → 调用聊天接口 → 检索个人知识库 → 生成答案和引用 → 校验来源 → DeepEval 使用裁判模型评分。

当前数据来自 FinanceBench `OPEN_SOURCE` 人工标注：5 份 PDF、30 个问题，其中开发集 18 题、保留测试集 12 题。标准答案不是本项目自动生成的。

## 1. 文件和数据集

| 文件 | 用途 |
|---|---|
| `backend/evals/test_rag.py` | 端到端测评入口 |
| `backend/evals/summarize_results.py` | 将 DeepEval JSON 转成中文 Markdown 报告 |
| `backend/evals/datasets/financebench_goldens_dev.json` | 18 题开发集，只用于调参 |
| `backend/evals/datasets/financebench_goldens_test.json` | 12 题保留测试集，用于最终验收 |
| `backend/evals/datasets/financebench_goldens_30.json` | 30 题合集，用于完整报告 |
| `backend/evals/datasets/financebench_manifest.json` | PDF、题目数量、分组及来源清单 |

需要上传的 5 份 PDF 完整路径：

```text
<项目根目录>\data\financebench-main\pdfs\AMCOR_2023_10K.pdf
<项目根目录>\data\financebench-main\pdfs\AMD_2022_10K.pdf
<项目根目录>\data\financebench-main\pdfs\AMERICANEXPRESS_2022_10K.pdf
<项目根目录>\data\financebench-main\pdfs\BOEING_2022_10K.pdf
<项目根目录>\data\financebench-main\pdfs\PEPSICO_2022_10K.pdf
```

必须用同一个专用评测账号上传，文件名不要修改，并等待状态变为“可检索”。专用账号中不要混入其他文档，否则其他文档可能抢占 Top-K，导致结果不可比较。

## 2. 首次安装

DeepEval 使用独立环境 `backend/.venv-eval`，后端仍使用 `backend/.venv`。如果评测环境不存在：

```powershell
cd <项目根目录>\backend
python -m venv .venv-eval
.\.venv-eval\Scripts\pip.exe install -e ".[dev,eval]"
.\.venv-eval\Scripts\python.exe -c "import importlib.metadata as m; print(m.version('deepeval'))"
```

当前验证版本是 DeepEval 4.1.3。不要把 DeepEval 安装到后端主环境，以免依赖版本冲突。

## 3. 每次测评前如何启动

先在项目根目录启动数据库：

```powershell
cd <项目根目录>
docker compose up -d
docker compose ps
```

再开一个终端启动后端：

```powershell
cd <项目根目录>\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8021
```

浏览器访问 `http://127.0.0.1:8021/api/health`，返回成功后才运行评测。前端不是测评必需；只有上传或检查文档时才需运行：

```powershell
cd <项目根目录>\frontend
npm run dev
```

## 4. `.env` 配置

在项目根目录的 `.env` 中填写，真实密钥和密码不得提交 Git：

```dotenv
EVAL_BASE_URL=http://127.0.0.1:8021
EVAL_USERNAME=financebench_eval
EVAL_PASSWORD=你的评测账号密码
EVAL_DATASET_PATH=backend/evals/datasets/financebench_goldens_dev.json
EVAL_CASE_LIMIT=5
EVAL_METRIC_PROFILE=fast
EVAL_INCLUDE_REASON=false
EVAL_REQUEST_TIMEOUT_SECONDS=180
EVAL_KEEP_CONVERSATIONS=false

# 可选；不填时复用 OPENAI_BASE_URL/API_KEY/MODEL
EVAL_JUDGE_BASE_URL=
EVAL_JUDGE_API_KEY=
EVAL_JUDGE_MODEL=
```

关键参数：

| 参数 | 含义 |
|---|---|
| `EVAL_DATASET_PATH` | 选择开发集、测试集或 30 题合集 |
| `EVAL_CASE_LIMIT` | 前 N 题；`0` 表示数据集全部，设为 `30` 对当前合集也能跑完 |
| `EVAL_METRIC_PROFILE` | `fast`、`retrieval`、`generation` 或 `full` |
| `EVAL_INCLUDE_REASON` | 是否要求裁判生成文字理由；正式报告用 `true`，快速迭代用 `false` |
| `EVAL_KEEP_CONVERSATIONS` | `false` 时结束后清理测试会话；中断运行可能留下少量会话 |
| `EVAL_JUDGE_*` | 单独指定裁判模型；正式对比时必须固定模型和版本 |

PowerShell 中临时设置的 `$env:...` 优先于 `.env`，适合只改变本次运行，不必反复编辑文件。

## 5. 三种推荐运行方式

### 5.1 最快冒烟：5 题、2 个核心指标

用于确认接口、文档、API 和基本召回是否正常。`fast` 只测 Contextual Recall 与 Faithfulness，并关闭文字理由，调用量约为完整四指标的一半。

```powershell
cd <项目根目录>\backend
$env:EVAL_DATASET_PATH='backend/evals/datasets/financebench_goldens_dev.json'
$env:EVAL_CASE_LIMIT='5'
$env:EVAL_METRIC_PROFILE='fast'
$env:EVAL_INCLUDE_REASON='false'
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
.\.venv-eval\Scripts\deepeval.exe test run evals\test_rag.py -n 2 -c -d failing --color no
```

### 5.2 日常调参：18 题开发集

先用 `fast` 找方向；确认有提升后改成 `full` 检查全部指标。只能根据开发集调整分块、Top-K、阈值、查询路由或重排。

```powershell
$env:EVAL_DATASET_PATH='backend/evals/datasets/financebench_goldens_dev.json'
$env:EVAL_CASE_LIMIT='0'
$env:EVAL_METRIC_PROFILE='fast'
.\.venv-eval\Scripts\deepeval.exe test run evals\test_rag.py -n 2 -c -d failing --color no
```

### 5.3 正式验收：12 题测试集或完整 30 题

参数确定后再跑保留测试集，不要看完测试集失败样本又继续调参，否则它就变成开发集了。

```powershell
$env:EVAL_DATASET_PATH='backend/evals/datasets/financebench_goldens_test.json'
$env:EVAL_CASE_LIMIT='0'
$env:EVAL_METRIC_PROFILE='full'
$env:EVAL_INCLUDE_REASON='true'
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
.\.venv-eval\Scripts\deepeval.exe test run evals\test_rag.py -n 2 -c -d failing --color no
.\.venv-eval\Scripts\python.exe evals\summarize_results.py
```

完整 30 题只需把路径改为：

```powershell
$env:EVAL_DATASET_PATH='backend/evals/datasets/financebench_goldens_30.json'
```

建议并发保持 `-n 2`。提高到 4 或更多不一定更快，反而容易撞到后端每分钟请求限制、裁判 API 限流或超时。`-c` 会复用完全相同输入的裁判缓存，但如果被测回答发生变化，缓存不一定命中。`-d failing` 和 `--color no` 主要减少终端输出，不会减少模型计算。

## 6. 指标到底在测什么

测试在调用 DeepEval 前还有两条硬校验：

1. 接口必须返回至少一条 `citation`；没有引用直接失败。
2. 返回引用的文件名必须命中该题的 `acceptable_sources`；召回错 PDF 直接失败。

通过硬校验后，四个 LLM-as-a-Judge 指标如下：

| 指标 | 使用的数据 | 阈值 | 它回答的问题 | 低分通常说明 |
|---|---|---:|---|---|
| Contextual Precision | 问题、标准答案、按顺序排列的检索片段 | 0.70 | 相关片段是否排在检索列表前面 | Top-K 混入噪声、重排差、同文档重复片段占位 |
| Contextual Recall | 标准答案、检索片段 | 0.70 | 标准答案需要的事实是否被召回 | 正确表格/段落没找到、切分破坏语义、Top-K 太小 |
| Faithfulness | 实际答案、检索片段 | 0.80 | 答案中的陈述能否由证据支持 | 模型幻觉、跨片段错误拼接、计算过程用了证据外信息 |
| Answer Relevancy | 问题、实际答案 | 0.70 | 回答是否正面回应问题 | 答非所问、内容冗余、拒答或只复述背景 |

注意：这些分数不是“最终答案正确率”。例如答案可能忠于检索到的错误/不完整片段，因此 Faithfulness 很高，但财务数值仍算错。FinanceBench 有计算题，正式完善时还应增加数值容差或基于标准答案的 Correctness/GEval 指标。

评测请求会设置 `include_retrieval_context=true`，接口因此只在本次响应中返回回答模型实际使用的完整 `retrieval_context`。它不会写入聊天历史；普通前端请求仍只保存和返回最多 1000 字的 `citations[].excerpt`。如果后端尚未重启、没有返回完整字段，评测脚本会兼容性回退到 `excerpt`，但这种结果可能低估 Contextual Recall，不能作为新的正式基线。

### 指标档位

| 档位 | 指标 | 适用场景 |
|---|---|---|
| `fast` | Recall + Faithfulness | 高频开发反馈，先判断“有没有找全、有没有胡编” |
| `retrieval` | Precision + Recall | 专门调分块、召回、Top-K、重排 |
| `generation` | Faithfulness + Answer Relevancy | 专门调提示词和回答模型 |
| `full` | 全部四项 | 正式、可比较的完整报告 |

“一条用例通过”表示来源硬校验和本档位内所有指标都达到阈值。整体通过数通常很严格，不能只看它；还要看各指标均值、通过数和具体失败理由。

## 7. 如何读报告并定位问题

正常运行后执行：

```powershell
.\.venv-eval\Scripts\python.exe evals\summarize_results.py
```

主要结果位置：

- 可读报告：`backend/evals/results/rag-eval-latest.md`
- DeepEval 原始结果：`backend/.deepeval/.latest_run_full.json`
- DeepEval 缓存：`backend/.deepeval/.deepeval-cache.json`

阅读顺序：

1. 看“用例数量”是否符合预期，避免误把 5 题冒烟当成完整报告。
2. 看“无分数”是否为 0；非 0 代表裁判超时/取消，不能当成模型质量分。
3. 先看 Recall，再看 Precision：先解决“没找全”，再优化“相关片段是否靠前”。
4. 再看 Faithfulness 和 Answer Relevancy，判断生成阶段是否幻觉或跑题。
5. 打开失败用例，对照问题、标准答案、实际答案和检索片段，进行人工复核。

常见组合判断：

| 现象 | 更可能的问题 | 优先检查 |
|---|---|---|
| Recall 低，Faithfulness 高 | 模型只根据有限证据作答，没有胡编，但关键证据没召回 | PDF 表格解析、分块、查询改写、Top-K |
| Recall 高，Precision 低 | 找到了答案，但前面有很多无关或重复片段 | 重排、阈值、MMR/去重、单文档配额 |
| 检索两项高，Faithfulness 低 | 证据够，但生成模型使用错误 | 提示词、引用约束、计算步骤、模型能力 |
| Faithfulness 高，Relevancy 低 | 内容有依据，但没有直接回答 | 回答模板、减少冗余、明确输出格式 |
| 四项高但数值答案错 | 现有指标没有充分检查计算正确性 | 增加数值正确率/容差指标和人工抽查 |

不同模型裁判、不同阈值或不同题集的分数不能直接横向比较。LLM 裁判也会波动；正式对外报告应固定裁判模型、温度、题集和配置，最好重复 3 次并报告均值与波动。

## 8. 本次 Vector Baseline 结果（2026-07-29）

本次使用 30 题合集、图谱关闭、`full` 四指标、`-n 2`。实际指标计算约耗时 1487 秒（约 24 分 47 秒）。DeepEval 最后在 Windows GBK 终端展示特殊字符时异常，因此从临时 JSON 中按问题保留最后一条记录恢复报告；30 个问题齐全，但 4 题有部分裁判指标超时/取消。

| 指标 | 有分数题数 | 平均分 | 达标 | 未达标 | 无分数 |
|---|---:|---:|---:|---:|---:|
| Contextual Precision | 27/30 | 0.401 | 7 | 20 | 3 |
| Contextual Recall | 28/30 | 0.179 | 5 | 23 | 2 |
| Faithfulness | 26/30 | 0.973 | 25 | 1 | 4 |
| Answer Relevancy | 30/30 | 0.932 | 27 | 3 | 0 |

整体只有 1/30 题满足所有指标。最明显短板是检索召回，尤其是财务表格、跨段事实和计算题所需证据没有完整进入 Top-K；回答一旦拿到证据，忠实性和相关性总体较高。因此下一轮应优先改 PDF 表格解析、检索上下文完整性、混合召回与重排，而不是先换回答提示词。

恢复后的详细报告：`backend/evals/results/financebench-vector-30-20260729.md`。

如果未来终端仍在结果展示阶段异常，但 `.deepeval/.temp_test_run_data.json` 已包含完整问题，可执行：

```powershell
.\.venv-eval\Scripts\python.exe evals\summarize_results.py `
  --source .deepeval\.temp_test_run_data.json `
  --output evals\results\rag-eval-recovered.md `
  --deduplicate
```

`--deduplicate` 仅用于同一次中断后又继续运行、临时文件出现重复问题的恢复场景；正常报告不要随意去重。

## 9. 如何让测评更快

耗时来自两部分：每题先调用一次 NewAgent 生成答案，然后每个指标还会调用裁判模型。30 题 × 4 指标最多形成约 120 次指标评估，部分指标内部还可能需要多步判断，所以明显慢于普通单元测试。

推荐按以下顺序提速：

1. 平时只跑前 5 题和 `fast`，确认方向后再跑 18 题开发集。
2. 专门调检索时用 `retrieval`，专门调回答时用 `generation`，正式报告才用 `full`。
3. 使用 `-n 2 -c`；不要盲目增加并发。
4. 快速阶段设置 `EVAL_INCLUDE_REASON=false`，减少裁判输出；正式报告再开启理由。
5. 参数不变时保留 DeepEval 缓存；改了检索或模型后要把结果视为新实验。
6. 不要每次都跑 30 题。18 题开发集负责迭代，12 题测试集负责最后验收。

如果看到 `Timed out/cancelled while evaluating metric`，先降低并发；仍超时时可在本次终端设置：

```powershell
$env:DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE='300'
```

超时题应标记为“无分数”并重测，不能按 0 分解释为 RAG 质量差。

## 10. Vector 与 GraphRAG 公平对比

第一次让 5 个文档关闭图谱，得到 Vector Baseline；第二次为相同文档开启图谱并等待构建完成，得到 Hybrid GraphRAG。两次必须保持题集、生成模型、裁判模型、分块、Top-K、阈值和提示词一致，只改变图谱检索能力。

建议把两次 Markdown 报告分别保存为带日期和配置的文件，并比较：

- 全部 30 题的四指标变化；
- 领域事实题、指标抽取题、计算题分别变化；
- 平均延迟和失败/超时数量；
- 图谱是否提高关系型问题，同时引入无关实体噪声。

当前 30 题只是一套小规模回归基线，可以用于项目迭代和面试说明，但不应宣称代表所有金融 RAG 场景。

## 11. 常见错误

- `ECONNREFUSED 127.0.0.1:8021`：后端没启动或端口不对。
- `Missing EVAL_USERNAME/EVAL_PASSWORD`：根目录 `.env` 缺少评测账号。
- `returned no document citations`：文档还在解析/向量化，或问题没有召回任何文档。
- `Expected at least one source...`：召回了错误 PDF；优先查账号文档隔离、文件名和检索结果。
- `UnicodeEncodeError: gbk`：先设置 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`，并使用 `--color no`。
- 指标分数每次略有变化：LLM-as-a-Judge 存在波动，需要固定裁判模型并重复正式实验。

## 12. 数据来源与重建

原始 FinanceBench 更新后可重新生成整理数据：

```powershell
cd <项目根目录>\backend
.\.venv\Scripts\python.exe evals\build_financebench_dataset.py
```

生成脚本会校验数量、题型、重复 ID 和 PDF 是否存在。原始语料目录已加入 `.gitignore`，整理后的轻量 JSON 可以提交。

- FinanceBench：<https://github.com/patronus-ai/financebench>
- 论文：<https://arxiv.org/abs/2311.11944>

对外发布结果时应按 FinanceBench 原仓库要求引用数据集和论文。
