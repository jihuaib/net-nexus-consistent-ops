from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from uuid import uuid4

from agents import Agent, RunConfig, Runner

from ..core.observability import log_llm_error, log_llm_request, log_llm_response
from .llm_prompt import SYSTEM_PROMPT
from .diagnosis_service import DiagnosisService


class AgentService:
    def __init__(self, diagnosis_service: DiagnosisService) -> None:
        self._diagnosis_service = diagnosis_service
        self._sessions: dict[str, list[dict[str, Any]]] = {}

    def chat(
        self,
        message: str,
        fault_case_id: str = "live-snmp-current",
        session_id: str = "default-agent-session",
        topology_group_id: str | None = None,
    ) -> dict[str, Any]:
        user_message = self._message("user", message)
        if topology_group_id:
            user_message["topology_group_id"] = topology_group_id
        self._sessions.setdefault(session_id, []).append(user_message)

        prepared = self._diagnosis_service.prepare_analysis(
            question=message,
            fault_case_id=fault_case_id,
            session_id=session_id,
            topology_group_id=topology_group_id,
        )
        diagnosis = self._diagnosis_from_prepared_sync(prepared)
        tool_trace = self._build_tool_trace(diagnosis)
        content = self._compose_answer(diagnosis)
        assistant_message = self._message("assistant", content, diagnosis, tool_trace)
        self._sessions[session_id].append(assistant_message)

        return {
            "session_id": session_id,
            "message": assistant_message,
            "diagnosis": diagnosis,
            "tool_trace": tool_trace,
            "history": deepcopy(self._sessions[session_id]),
        }

    async def stream_chat(
        self,
        message: str,
        fault_case_id: str = "live-snmp-current",
        session_id: str = "default-agent-session",
        topology_group_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        user_message = self._message("user", message)
        if topology_group_id:
            user_message["topology_group_id"] = topology_group_id
        self._sessions.setdefault(session_id, []).append(user_message)
        yield {"type": "message", "message": user_message}

        prepared = self._diagnosis_service.prepare_analysis(
            question=message,
            fault_case_id=fault_case_id,
            session_id=session_id,
            topology_group_id=topology_group_id,
        )
        async for event in self._stream_prepared_analysis(prepared):
            yield event

    async def _stream_prepared_analysis(self, prepared: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        yield self._stage_event("collect_observations", "success", f"采集来源：{prepared['fault_case'].get('data_source', 'unknown')}")
        yield self._stage_event("normalize_facts", "success", f"生成 {len(prepared.get('facts') or [])} 条标准化 Fact")

        if prepared.get("result") is not None:
            diagnosis = prepared["result"]
            tool_trace = self._build_tool_trace(diagnosis)
            content = self._compose_answer(diagnosis)
            async for chunk in stream_text_chunks(content):
                yield {"type": "text_delta", "delta": chunk}
            assistant_message = self._message("assistant", content, diagnosis, tool_trace)
            self._sessions[diagnosis["session_id"]].append(assistant_message)
            yield self._final_event(diagnosis, tool_trace, assistant_message)
            return

        if prepared.get("cache_hit"):
            diagnosis = prepared["cached_result"]
            tool_trace = self._build_tool_trace(diagnosis)
            content = self._compose_answer(diagnosis)
            yield self._stage_event("diagnosis_cache", "hit", "命中同一故障指纹缓存")
            async for chunk in stream_text_chunks(content):
                yield {"type": "text_delta", "delta": chunk}
            assistant_message = self._message("assistant", content, diagnosis, tool_trace)
            self._sessions[diagnosis["session_id"]].append(assistant_message)
            yield self._final_event(diagnosis, tool_trace, assistant_message)
            return

        yield self._stage_event("build_fault_fingerprint", "success", f"生成故障指纹 {prepared['fingerprint']}")
        yield self._stage_event(
            "context_constraints",
            "success",
            f"已构建 {len(prepared['context_constraints'].get('fact_chain') or [])} 条事实链上下文",
        )
        knowledge_count = len((prepared.get("knowledge_context") or {}).get("items") or [])
        yield self._stage_event("knowledge_retrieval", "success", f"检索到 {knowledge_count} 条知识库片段")
        yield self._stage_event("openai_agents_sdk", "running", "OpenAI Agents SDK Runner.run_streamed 正在生成结构化诊断")

        agent = self._build_openai_agent()
        agent_input = self._agent_input(prepared)
        self._log_agents_request(prepared, streaming=True)
        streamed_text = ""
        try:
            streamed_result = Runner.run_streamed(
                agent,
                input=agent_input,
                max_turns=2,
                run_config=self._run_config(),
            )
            async for sdk_event in streamed_result.stream_events():
                delta = extract_text_delta(sdk_event)
                if delta:
                    streamed_text += delta
                    yield {"type": "text_delta", "delta": delta}

            self._log_agents_response(
                streaming=True,
                output=streamed_result.final_output,
                streamed_text=streamed_text,
            )
            raw_llm_result = self._parse_agent_output(streamed_result.final_output)
            diagnosis = self._diagnosis_service.complete_prepared_analysis(prepared, raw_llm_result)
        except Exception as exc:
            self._log_agents_error(exc, streaming=True)
            raise
        tool_trace = self._build_tool_trace(diagnosis)
        content = self._compose_answer(diagnosis)
        if not streamed_text:
            async for chunk in stream_text_chunks(content):
                yield {"type": "text_delta", "delta": chunk}
        assistant_message = self._message("assistant", content, diagnosis, tool_trace)
        self._sessions[diagnosis["session_id"]].append(assistant_message)
        yield self._final_event(diagnosis, tool_trace, assistant_message)

    def get_session(self, session_id: str) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "summary": self._session_summary(session_id, self._sessions.get(session_id, [])),
            "history": deepcopy(self._sessions.get(session_id, [])),
        }

    def list_sessions(self) -> dict[str, Any]:
        sessions = [
            self._session_summary(session_id, history)
            for session_id, history in self._sessions.items()
        ]
        sessions.sort(key=lambda item: item["updated_at"] or "", reverse=True)
        return {
            "items": sessions,
            "total": len(sessions),
        }

    def clear_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def clear_all_sessions(self) -> None:
        self._sessions.clear()

    def _diagnosis_from_prepared_sync(self, prepared: dict[str, Any]) -> dict[str, Any]:
        if prepared.get("result") is not None:
            return prepared["result"]
        if prepared.get("cache_hit"):
            return prepared["cached_result"]
        agent = self._build_openai_agent()
        agent_input = self._agent_input(prepared)
        self._log_agents_request(prepared, streaming=False)
        try:
            result = Runner.run_sync(
                agent,
                input=agent_input,
                max_turns=2,
                run_config=self._run_config(),
            )
            self._log_agents_response(
                streaming=False,
                output=result.final_output,
                streamed_text=None,
            )
            raw_llm_result = self._parse_agent_output(result.final_output)
            return self._diagnosis_service.complete_prepared_analysis(prepared, raw_llm_result)
        except Exception as exc:
            self._log_agents_error(exc, streaming=False)
            raise

    def _build_openai_agent(self) -> Agent:
        model_settings = self._diagnosis_service.llm_agents_model_settings()
        return Agent(
            name="NetNexus ConsistentOps Diagnosis Agent",
            instructions=SYSTEM_PROMPT,
            model=self._diagnosis_service.llm_agents_chat_model(),
            model_settings=model_settings,
        )

    def _run_config(self) -> RunConfig:
        return RunConfig(
            workflow_name="NetNexus ConsistentOps Diagnosis",
            tracing_disabled=True,
        )

    def _agent_input(self, prepared: dict[str, Any]) -> str:
        return json.dumps(prepared["llm_payload"], ensure_ascii=False, sort_keys=True)

    def _log_agents_request(self, prepared: dict[str, Any], *, streaming: bool) -> None:
        metadata = self._diagnosis_service.llm_metadata()
        operation = "agents.run_streamed" if streaming else "agents.run_sync"
        model_settings = self._diagnosis_service.llm_agents_model_settings()
        log_llm_request(
            provider=metadata.get("provider", "unknown"),
            model=metadata.get("model"),
            operation=operation,
            payload={
                "instructions": SYSTEM_PROMPT,
                "input": self._agent_input(prepared),
                "max_turns": 2,
                "model_settings": model_settings.model_dump(exclude_none=True)
                if hasattr(model_settings, "model_dump")
                else model_settings,
                "llm": metadata,
            },
        )

    def _log_agents_response(self, *, streaming: bool, output: Any, streamed_text: str | None) -> None:
        metadata = self._diagnosis_service.llm_metadata()
        operation = "agents.run_streamed" if streaming else "agents.run_sync"
        log_llm_response(
            provider=metadata.get("provider", "unknown"),
            model=metadata.get("model"),
            operation=operation,
            payload={
                "final_output": output,
                "streamed_text": streamed_text,
            },
        )

    def _log_agents_error(self, error: BaseException, *, streaming: bool) -> None:
        metadata = self._diagnosis_service.llm_metadata()
        operation = "agents.run_streamed" if streaming else "agents.run_sync"
        log_llm_error(
            provider=metadata.get("provider", "unknown"),
            model=metadata.get("model"),
            operation=operation,
            error=error,
        )

    def _parse_agent_output(self, output: Any) -> dict[str, Any]:
        if isinstance(output, dict):
            return output
        return self._diagnosis_service.parse_llm_json_content(str(output or ""))

    def _stage_event(self, name: str, status: str, summary: str) -> dict[str, Any]:
        return {
            "type": "stage",
            "tool": {
                "name": name,
                "status": status,
                "summary": summary,
            },
        }

    def _final_event(
        self,
        diagnosis: dict[str, Any],
        tool_trace: list[dict[str, Any]],
        assistant_message: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "type": "final",
            "session_id": diagnosis["session_id"],
            "message": assistant_message,
            "diagnosis": diagnosis,
            "tool_trace": tool_trace,
            "history": deepcopy(self._sessions[diagnosis["session_id"]]),
        }

    def _message(
        self,
        role: str,
        content: str,
        diagnosis: dict[str, Any] | None = None,
        tool_trace: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        message: dict[str, Any] = {
            "id": f"msg_{uuid4().hex[:12]}",
            "role": role,
            "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if diagnosis is not None:
            message["diagnosis"] = diagnosis
        if tool_trace is not None:
            message["tool_trace"] = tool_trace
        return message

    def _session_summary(self, session_id: str, history: list[dict[str, Any]]) -> dict[str, Any]:
        first_user_message = next((item for item in history if item.get("role") == "user"), None)
        last_message = history[-1] if history else None
        return {
            "session_id": session_id,
            "title": _compact_title(first_user_message.get("content") if first_user_message else session_id),
            "message_count": len(history),
            "user_message_count": len([item for item in history if item.get("role") == "user"]),
            "updated_at": last_message.get("created_at") if last_message else None,
        }

    def _compose_answer(self, diagnosis: dict[str, Any]) -> str:
        evidence = "；".join(diagnosis["evidence"])
        recommendation = "；".join(diagnosis["recommendation"])
        if diagnosis["cache_hit"]:
            cache_state = "命中缓存"
        else:
            cache_state = "首次生成并写入缓存"

        return (
            f"结论：{diagnosis['root_cause']}。\n"
            f"故障类型：{diagnosis['fault_type']}，置信度：{diagnosis['confidence']}。\n"
            f"故障指纹：{diagnosis['fault_fingerprint']}，{cache_state}。\n"
            f"证据：{evidence}。\n"
            f"建议：{recommendation}。"
        )

    def _build_tool_trace(self, diagnosis: dict[str, Any]) -> list[dict[str, Any]]:
        trace = [
            {
                "name": "collect_observations",
                "status": "success",
                "summary": f"通过 {diagnosis['data_source']} 采集当前故障环境观测数据",
            },
            {
                "name": "normalize_facts",
                "status": "success",
                "summary": f"生成 {len(diagnosis['facts'])} 条标准化 Fact",
            },
            {
                "name": "build_fault_fingerprint",
                "status": "success",
                "summary": fingerprint_trace_summary(diagnosis),
            },
            {
                "name": "diagnosis_cache",
                "status": "hit" if diagnosis["cache_hit"] else "miss",
                "summary": cache_trace_summary(diagnosis),
            },
        ]
        trace.append(
            {
                "name": "llm_reasoning",
                "status": "success",
                "summary": f"通过 OpenAI Agents SDK 调用 {diagnosis['llm']['provider']} 大模型生成结构化诊断",
            }
        )
        trace.extend(
            [
                {
                    "name": "knowledge_retrieval",
                    "status": "success",
                    "summary": knowledge_retrieval_summary(diagnosis),
                },
                {
                    "name": "context_constraints",
                    "status": "success",
                    "summary": context_constraints_summary(diagnosis),
                },
                {
                    "name": "consistency_guard",
                    "status": "success",
                    "summary": "输出字段经过 JSON Schema 校验、故障指纹缓存，并参与一致性评分",
                },
            ]
        )
        return trace


def _compact_title(content: str | None, limit: int = 28) -> str:
    normalized = " ".join(str(content or "").split())
    if not normalized:
        return "未命名会话"
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def fingerprint_trace_summary(diagnosis: dict[str, Any]) -> str:
    if diagnosis.get("facts"):
        return f"生成稳定故障指纹 {diagnosis['fault_fingerprint']}"
    if str(diagnosis.get("fault_fingerprint", "")).startswith("fp_ctx_"):
        return f"生成上下文指纹 {diagnosis['fault_fingerprint']}"
    return f"生成稳定故障指纹 {diagnosis['fault_fingerprint']}"


def cache_trace_summary(diagnosis: dict[str, Any]) -> str:
    if str(diagnosis.get("fault_fingerprint", "")).startswith("fp_ctx_"):
        return "同一问题上下文指纹返回同一诊断结果"
    return "同一故障指纹返回同一诊断结果"


def context_constraints_summary(diagnosis: dict[str, Any]) -> str:
    constraints = diagnosis.get("context_constraints") or {}
    fact_count = len(constraints.get("fact_chain") or [])
    evidence_count = len(constraints.get("evidence") or [])
    return f"系统提供环境事实摘要：{fact_count} 条事实链，{evidence_count} 条证据"


def knowledge_retrieval_summary(diagnosis: dict[str, Any]) -> str:
    knowledge_context = diagnosis.get("knowledge_context") or {}
    items = knowledge_context.get("items") or []
    if not knowledge_context.get("enabled"):
        return "知识库未启用或未配置，未向本次诊断注入外部资料"
    if not items:
        return "知识库已检索，但没有匹配本次问题的片段"
    titles = []
    for item in items:
        title = item.get("title")
        if title and title not in titles:
            titles.append(title)
    return f"向诊断上下文注入 {len(items)} 条知识片段：{', '.join(titles[:3])}"


def extract_text_delta(event: Any) -> str:
    data = getattr(event, "data", None)
    if data is None:
        return ""
    for attr in ("delta", "text"):
        value = getattr(data, attr, None)
        if isinstance(value, str):
            return value
    event_type = getattr(data, "type", "")
    if event_type in {"response.output_text.delta", "response.refusal.delta"}:
        value = getattr(data, "delta", "")
        return value if isinstance(value, str) else ""
    return ""


async def stream_text_chunks(text: str, size: int = 18) -> AsyncIterator[str]:
    for index in range(0, len(text), size):
        yield text[index : index + size]
