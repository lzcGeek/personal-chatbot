"""Convert DeepEval's latest internal JSON into a readable Markdown report."""

import json
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
SOURCE_PATH = BACKEND_DIR / ".deepeval" / ".latest_run_full.json"
OUTPUT_PATH = BACKEND_DIR / "evals" / "results" / "rag-eval-latest.md"


def cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def score(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "-"


def main() -> None:
    if not SOURCE_PATH.exists():
        raise SystemExit(
            f"DeepEval result not found: {SOURCE_PATH}\n"
            "Run `deepeval test run evals/test_rag.py -v` first."
        )

    data = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    cases = data.get("testCases") or []
    metrics_scores = data.get("metricsScores") or []
    generated_at = datetime.fromtimestamp(SOURCE_PATH.stat().st_mtime).astimezone()

    lines = [
        "# NewAgent RAG DeepEval 报告",
        "",
        f"- 生成时间：{generated_at:%Y-%m-%d %H:%M:%S %z}",
        f"- 测试文件：`{data.get('testFile', '-')}`",
        f"- 用例数量：{len(cases)}",
        f"- 整体通过：{data.get('testPassed', 0)}",
        f"- 整体失败：{data.get('testFailed', 0)}",
        f"- 总耗时：{float(data.get('runDuration') or 0):.2f} 秒",
        "",
        "## 指标汇总",
        "",
        "| 指标 | 平均分 | 通过 | 失败 |",
        "|---|---:|---:|---:|",
    ]

    for item in metrics_scores:
        scores = [float(value) for value in item.get("scores") or []]
        lines.append(
            f"| {cell(item.get('metric', '-'))} | "
            f"{mean(scores):.3f} | {item.get('passes', 0)} | {item.get('fails', 0)} |"
        )

    metric_names: list[str] = []
    for case_data in cases:
        for metric in case_data.get("metricsData") or []:
            name = str(metric.get("name", "-"))
            if name not in metric_names:
                metric_names.append(name)

    lines.extend(
        [
            "",
            "## 用例明细",
            "",
            "| 问题 | 结果 | " + " | ".join(metric_names) + " | 耗时 |",
            "|---|---:|" + "---:|" * len(metric_names) + "---:|",
        ]
    )
    for case_data in cases:
        by_name = {
            metric.get("name"): metric for metric in case_data.get("metricsData") or []
        }
        values = [score(by_name.get(name, {}).get("score")) for name in metric_names]
        result = "通过" if case_data.get("success") else "失败"
        lines.append(
            f"| {cell(case_data.get('input', '-'))} | {result} | "
            + " | ".join(values)
            + f" | {float(case_data.get('runDuration') or 0):.2f}s |"
        )

    failed_details: list[str] = []
    for case_data in cases:
        failed_metrics = [
            metric
            for metric in case_data.get("metricsData") or []
            if not metric.get("success")
        ]
        if not failed_metrics:
            continue
        failed_details.extend(["", f"### {cell(case_data.get('input', '-'))}", ""])
        for metric in failed_metrics:
            failed_details.append(
                f"- **{cell(metric.get('name', '-'))}**："
                f"{score(metric.get('score'))} / 阈值 {score(metric.get('threshold'))}"
            )
            reason = str(metric.get("reason") or "未提供原因").strip()
            failed_details.append(f"  - {reason}")

    lines.extend(["", "## 失败原因", *failed_details])
    lines.extend(
        [
            "",
            "## 阅读说明",
            "",
            "- Contextual Precision 低：召回列表前部混入无关片段，通常需要改进 Top-K、阈值或重排。",
            "- Contextual Recall 低：召回证据不足以覆盖标准答案。当前测试使用 `citations[].excerpt`，该字段最多保留 300 字，可能低估完整上下文召回率。",
            "- Faithfulness 低：最终回答包含检索证据无法支持的内容，可能存在幻觉。",
            "- Answer Relevancy 低：最终回答没有直接回应问题或混入无关内容。",
            "",
            f"原始数据：`{SOURCE_PATH}`",
        ]
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
