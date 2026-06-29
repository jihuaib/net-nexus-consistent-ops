from __future__ import annotations

from .diagnosis_context import ALLOWED_FAULT_TYPES

SYSTEM_PROMPT = """你是一名网络设备运维诊断专家。请基于输入的结构化事实、故障指纹、上下文约束和拓扑上下文完成诊断。

必须遵守：
1. 只能基于输入事实分析，不允许编造不存在的设备、接口、路由或告警。
2. 必须输出 JSON 对象，不要输出 Markdown。
3. fault_type 必须从 allowed_fault_types 中选择。
4. evidence 必须引用输入 facts、question_context 或 context_constraints 中已有证据。
5. question_context 是系统从用户问题、拓扑和事件窗口抽取出的环境上下文，可作为诊断证据。
6. context_constraints 是环境事实摘要和一致性约束，不是规则诊断结论；不得把它当作最终答案照抄。
7. 如果当前没有活动故障 facts，但用户问题点名了设备、接口或业务，请结合 question_context 判断；不要机械回答“无活动故障”。
8. 如果证据不足，将 need_more_data 设置为 true 并降低 confidence。
9. 同一 fault_fingerprint 下应保持 fault_type、root_cause、evidence、diagnosis_chain 和 recommendation 一致。
10. 如果看到 BGP、路由、FIB 或业务不可达异常依赖同一个 Down 接口，根因应回到该接口 Down。
11. 如果只有 BGP、路由、FIB 或业务异常 facts，但没有接口/链路根因事实，不要直接推断接口 Down，应输出 UNKNOWN_NEED_MORE_DATA。
12. 你的职责是基于 facts、topology、question_context 和 context_constraints 共同诊断。

输出 JSON 字段：
{
  "fault_type": "string",
  "root_cause": "string",
  "affected_devices": ["string"],
  "affected_services": ["string"],
  "evidence": ["string"],
  "diagnosis_chain": ["string"],
  "confidence": 0.0,
  "recommendation": ["string"],
  "need_more_data": false
}
"""


def build_diagnosis_payload(
    question: str,
    fault_case: dict,
    facts: list[dict],
    topology: dict,
    fingerprint_info: dict,
    context_constraints: dict,
    question_context: dict | None = None,
) -> dict:
    return {
        "task": "network_operations_fault_diagnosis",
        "question": question,
        "allowed_fault_types": ALLOWED_FAULT_TYPES,
        "fault_case": {
            "id": fault_case["id"],
            "title": fault_case["title"],
            "data_source": fault_case.get("data_source"),
            "primary_device": fault_case.get("primary_device"),
            "primary_interface": fault_case.get("primary_interface"),
        },
        "topology": topology,
        "question_context": question_context or {},
        "facts": facts,
        "fault_fingerprint": fingerprint_info["fingerprint"],
        "fingerprint_payload": fingerprint_info["payload"],
        "context_constraints": context_constraints,
    }
