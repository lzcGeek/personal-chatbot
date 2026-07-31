"""Convert a DeepEval internal JSON result into a readable Markdown report."""

import argparse
import json
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_PATH = BACKEND_DIR / ".deepeval" / ".latest_run_full.json"
DEFAULT_OUTPUT_DIR = BACKEND_DIR / "evals" / "results"


def cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def score(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "-"


def timestamped_output_path(created_at: datetime) -> Path:
    """Return a new default report path without overwriting an earlier report."""
    base = DEFAULT_OUTPUT_DIR / f"rag-eval-{created_at:%Y%m%d-%H%M%S}.md"
    if not base.exists():
        return base

    counter = 2
    while True:
        candidate = base.with_stem(f"{base.stem}-{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_PATH)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Report path. By default, write a unique timestamped file under "
            "evals/results so previous reports are preserved."
        ),
    )
    parser.add_argument(
        "--deduplicate",
        action="store_true",
        help="Keep the last record for each input (useful after an interrupted run).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = args.source
    if not source_path.is_absolute():
        source_path = (BACKEND_DIR / source_path).resolve()
    report_created_at = datetime.now().astimezone()
    if args.output is None:
        output_path = timestamped_output_path(report_created_at)
    else:
        output_path = args.output
        if not output_path.is_absolute():
            output_path = (BACKEND_DIR / output_path).resolve()

    if not source_path.exists():
        raise SystemExit(
            f"DeepEval result not found: {source_path}\n"
            "Run `deepeval test run evals/test_rag.py -v` first."
        )

    data = json.loads(source_path.read_text(encoding="utf-8"))
    cases = data.get("testCases") or []
    if args.deduplicate:
        latest_by_input: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for case_data in cases:
            case_input = str(case_data.get("input", ""))
            latest_by_input.pop(case_input, None)
            latest_by_input[case_input] = case_data
        cases = list(latest_by_input.values())
    metrics_scores = data.get("metricsScores") or []
    generated_at = datetime.fromtimestamp(source_path.stat().st_mtime).astimezone()

    if not metrics_scores:
        aggregate: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for case_data in cases:
            for metric in case_data.get("metricsData") or []:
                name = str(metric.get("name", "-"))
                item = aggregate.setdefault(
                    name,
                    {
                        "metric": name,
                        "scores": [],
                        "passes": 0,
                        "fails": 0,
                        "unavailable": 0,
                    },
                )
                value = metric.get("score")
                if isinstance(value, (int, float)):
                    item["scores"].append(float(value))
                    if metric.get("success"):
                        item["passes"] += 1
                    else:
                        item["fails"] += 1
                else:
                    item["unavailable"] += 1
        metrics_scores = list(aggregate.values())
    else:
        unavailable_by_metric: dict[str, int] = {}
        for case_data in cases:
            for metric in case_data.get("metricsData") or []:
                if not isinstance(metric.get("score"), (int, float)):
                    name = str(metric.get("name", "-"))
                    unavailable_by_metric[name] = unavailable_by_metric.get(name, 0) + 1
        for item in metrics_scores:
            item["unavailable"] = max(
                int(item.get("errors") or 0),
                unavailable_by_metric.get(str(item.get("metric", "-")), 0),
            )

    passed = sum(bool(case_data.get("success")) for case_data in cases)
    failed = len(cases) - passed

    lines = [
        "# NewAgent RAG DeepEval 报告",
        "",
        f"- 生成时间：{generated_at:%Y-%m-%d %H:%M:%S %z}",
        f"- 测试文件：`{data.get('testFile', '-')}`",
        f"- 用例数量：{len(cases)}",
        f"- 整体通过：{passed}",
        f"- 整体失败：{failed}",
        (
            f"- 总耗时：{float(data['runDuration']):.2f} 秒"
            if data.get("runDuration")
            else "- 总耗时：未记录"
        ),
        "",
        "## 指标汇总",
        "",
        "| 指标 | 平均分 | 通过 | 失败 | 无分数 |",
        "|---|---:|---:|---:|---:|",
    ]

    for item in metrics_scores:
        scores = [float(value) for value in item.get("scores") or []]
        average = f"{mean(scores):.3f}" if scores else "-"
        lines.append(
            f"| {cell(item.get('metric', '-'))} | "
            f"{average} | {item.get('passes', 0)} | {item.get('fails', 0)} | "
            f"{item.get('unavailable', 0)} |"
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
            if metric.get("error"):
                reason = f"裁判执行异常：{metric['error']}"
            failed_details.append(f"  - {reason}")

    lines.extend(["", "## 失败原因", *failed_details])
    lines.extend(
        [
            "",
            "## 阅读说明",
            "",
            "- Gold Evidence Recall 低：Top-K 没有覆盖全部人工标注原文；优先检查 PDF 解析、分块和候选召回。",
            "- Gold Evidence Reciprocal Rank 低：证据已召回但首次出现位置靠后；优先检查重复片段、重排和证据多样性。",
            "- Numeric Answer Correctness 低：检索可能已经通过，但最终数值、变化方向、公式或舍入口径不符合数据集声明。",
            "- Faithfulness 低：最终回答包含检索证据无法支持的内容，可能存在幻觉。",
            "- Answer Relevancy 低：最终回答没有直接回应问题或混入无关内容。",
            "- 旧报告中的 Contextual Recall/Precision 是 LLM 裁判口径，不应与新版确定性 Gold 指标直接横向比较。",
            "",
            f"原始数据：`{source_path}`",
        ]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report written to: {output_path}")


if __name__ == "__main__":
    main()
