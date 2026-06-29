from __future__ import annotations

from typing import Any

from .diagnosis_service import DiagnosisService

DEFAULT_QUESTIONS = [
    "帮我分析当前故障",
    "leaf-01 为什么业务不通",
    "是不是 BGP 的问题",
    "相关路由为什么缺失",
    "FIB 表项为什么没有下发",
    "业务探测不可达的根因是什么",
    "重新诊断一下 leaf-01",
]

COMPARE_FIELDS = [
    "fault_fingerprint",
    "fault_type",
    "root_cause",
    "affected_devices",
    "affected_services",
    "evidence",
    "diagnosis_chain",
    "recommendation",
    "need_more_data",
]


def run_consistency_test(
    service: DiagnosisService,
    fault_case_id: str = "live-snmp-current",
    session_modes: list[str] | None = None,
    questions: list[str] | None = None,
    run_count: int = 8,
) -> dict[str, Any]:
    session_modes = session_modes or ["single_session", "multi_session"]
    questions = questions or DEFAULT_QUESTIONS
    run_count = max(1, run_count)

    mode_results = []
    all_scores = []
    for mode in session_modes:
        runs = []
        for index in range(run_count):
            question = questions[index % len(questions)]
            session_id = "phase2-single-session" if mode == "single_session" else f"phase2-session-{index + 1}"
            diagnosis = service.analyze(question=question, fault_case_id=fault_case_id, session_id=session_id)
            runs.append(
                {
                    "round": index + 1,
                    "session_mode": mode,
                    "session_id": session_id,
                    "question": question,
                    "cache_hit": diagnosis["cache_hit"],
                    "diagnosis": project_comparison_fields(diagnosis),
                }
            )

        score_result = score_runs(runs)
        all_scores.append(score_result["score"])
        mode_results.append(
            {
                "session_mode": mode,
                "score": score_result["score"],
                "consistent_runs": score_result["consistent_runs"],
                "total_runs": len(runs),
                "baseline": score_result["baseline"],
                "runs": runs,
            }
        )

    overall_score = sum(all_scores) / len(all_scores) if all_scores else 0
    return {
        "fault_case_id": fault_case_id,
        "overall_consistency_score": round(overall_score, 4),
        "passed": overall_score >= 0.99,
        "mode_results": mode_results,
    }


def score_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        return {"score": 0, "consistent_runs": 0, "baseline": None}

    baseline = runs[0]["diagnosis"]
    consistent_runs = sum(1 for run in runs if run["diagnosis"] == baseline)
    return {
        "score": round(consistent_runs / len(runs), 4),
        "consistent_runs": consistent_runs,
        "baseline": baseline,
    }


def project_comparison_fields(diagnosis: dict[str, Any]) -> dict[str, Any]:
    return {field: diagnosis[field] for field in COMPARE_FIELDS}
