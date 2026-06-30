from __future__ import annotations

SYSTEM_PROMPT = """你是一名网络设备运维诊断专家。请基于输入的结构化事实、故障指纹、上下文约束、拓扑上下文和可选知识库检索结果完成诊断。

必须遵守：
1. 只能基于输入事实分析，不允许编造不存在的设备、接口、路由或告警。
2. 必须输出 JSON 对象，不要输出 Markdown。
3. fault_type 由你基于证据生成，使用稳定、简短、可机器读取的英文大写标识。
4. evidence 必须引用输入 facts、question_context 或 context_constraints 中已有证据。
5. question_context 是系统从用户问题、拓扑和事件窗口抽取出的环境上下文，可作为诊断证据。
6. context_constraints 是环境事实摘要和一致性约束，不是规则诊断结论；不得把它当作最终答案照抄。
7. 如果当前没有活动故障 facts，但用户问题点名了设备、接口或业务，请结合 question_context 判断；不要机械回答“无活动故障”。
8. 如果证据不足，将 need_more_data 设置为 true 并降低 confidence。
9. 同一 fault_fingerprint 下应保持 fault_type、root_cause、evidence、diagnosis_chain 和 recommendation 一致。
10. 你的职责是基于 facts、topology、question_context 和 context_constraints 共同诊断，不要依赖后端预设候选故障类型。
11. 如果多个异常都通过 context 指向同一个底层对象，可将该对象作为根因候选；如果缺少底层根因证据，需要明确 need_more_data=true。
12. knowledge_context 是外部知识库检索结果，只能用于解释术语、补充排障步骤和建议；不能覆盖实时 facts，也不能因为知识库模板存在某类故障就推断当前环境发生该故障。
13. 如果 recommendation 使用了 knowledge_context 中的 SOP 或厂商知识，应在建议文本中简要标注知识来源标题。

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
    knowledge_context: dict | None = None,
) -> dict:
    return {
        "task": "network_operations_fault_diagnosis",
        "question": question,
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
        "knowledge_context": knowledge_context or {},
    }
