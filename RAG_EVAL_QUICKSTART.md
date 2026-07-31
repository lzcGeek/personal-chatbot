# RAG 测评快速使用说明

## 1. 运行前确认

- 后端已启动，默认地址为 `http://127.0.0.1:8021`
- PostgreSQL 和 Qdrant 已启动
- FinanceBench PDF 已上传并显示“处理完成”
- 上传 PDF 的账号与 `.env` 中的 `EVAL_USERNAME` 相同

## 2. 配置测试参数

打开项目根目录的 `.env`：

```text
<项目根目录>\.env
```

加入或修改：

```dotenv
EVAL_DATASET_PATH=backend/evals/datasets/financebench_goldens_dev.json
EVAL_CASE_LIMIT=5
EVAL_METRIC_PROFILE=fast
```

- `EVAL_CASE_LIMIT=5`：只跑前 5 题，适合冒烟测试
- `EVAL_METRIC_PROFILE=fast`：运行精简指标，速度较快
- 完整测试可将 `fast` 改为 `full`

如果之前在 PowerShell 中设置过同名 `$env:` 变量，请关闭终端并重新打开，避免临时变量覆盖 `.env`。

## 3. 运行 DeepEval

```powershell
cd <项目根目录>\backend
.\.venv-eval\Scripts\deepeval.exe test run evals\test_rag.py -v
```

## 4. 生成 Markdown 报告

测试结束后运行：

```powershell
.\.venv-eval\Scripts\python.exe evals\summarize_results.py
```

报告目录：

```text
<项目根目录>\backend\evals\results\
```

最新报告：

```text
rag-eval-latest.md
```

## 5. 常用数据集

```dotenv
# 开发集：日常调试
EVAL_DATASET_PATH=backend/evals/datasets/financebench_goldens_dev.json

# 测试集：最终验收
EVAL_DATASET_PATH=backend/evals/datasets/financebench_goldens_test.json

# 完整 30 题
EVAL_DATASET_PATH=backend/evals/datasets/financebench_goldens_30.json
```

每次只保留一个 `EVAL_DATASET_PATH` 生效。

## 常见错误

`NewAgent returned no document citations` 表示没有召回文档证据。请检查：

1. 是否选择了 FinanceBench 数据集。
2. PDF 是否处理完成。
3. `EVAL_USERNAME` 是否为上传 PDF 的账号。
4. 后端和 Qdrant 是否正常运行。
