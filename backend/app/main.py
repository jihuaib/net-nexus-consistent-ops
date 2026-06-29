from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .application.consistency_service import DEFAULT_QUESTIONS, run_consistency_test
from .application.event_normalizer import normalize_reported_event
from .core.api_logging import ApiLoggingMiddleware
from .core.container import build_container
from .core.observability import configure_logging
from .infrastructure.llm.base import LLMConfigurationError, LLMResponseError

configure_logging()


class DiagnosisRequest(BaseModel):
    question: str = Field(default="帮我分析当前故障")
    fault_case_id: str = Field(default="live-snmp-current")
    session_id: str = Field(default="default-session")
    topology_group_id: Optional[str] = Field(default=None)


class AgentChatRequest(BaseModel):
    message: str = Field(default="帮我分析当前故障")
    fault_case_id: str = Field(default="live-snmp-current")
    session_id: str = Field(default="default-agent-session")
    topology_group_id: Optional[str] = Field(default=None)


class ConsistencyTestRequest(BaseModel):
    fault_case_id: str = Field(default="live-snmp-current")
    session_modes: list[Literal["single_session", "multi_session"]] = Field(
        default_factory=lambda: ["single_session", "multi_session"]
    )
    questions: list[str] = Field(default_factory=lambda: DEFAULT_QUESTIONS)
    run_count: int = Field(default=8, ge=1, le=50)


class LLMConfigRequest(BaseModel):
    base_url: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)
    api_key: Optional[str] = Field(default=None)
    timeout_seconds: Optional[float] = Field(default=None, gt=0, le=300)
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    top_p: Optional[float] = Field(default=None, ge=0, le=1)
    json_mode: Optional[bool] = Field(default=None)


class TopologyDiscoverRequest(BaseModel):
    mode: str = Field(default="snmp_lldp")
    nodes: Optional[List[Dict[str, Any]]] = Field(default=None)
    edges: Optional[List[Dict[str, Any]]] = Field(default=None)
    options: Optional[Dict[str, Any]] = Field(default=None)


class TopologyDiscoveryConfigRequest(BaseModel):
    profile_id: Optional[str] = Field(default=None)
    community: Optional[str] = Field(default=None)
    targets: Optional[List[str]] = Field(default=None)
    scan_cidrs: Optional[List[str]] = Field(default=None)
    scan_enabled: Optional[bool] = Field(default=None)
    timeout_seconds: Optional[float] = Field(default=None, gt=0, le=60)
    scan_timeout_seconds: Optional[float] = Field(default=None, gt=0, le=30)
    scan_concurrency: Optional[int] = Field(default=None, ge=1, le=64)
    max_scan_hosts: Optional[int] = Field(default=None, ge=1, le=4096)


class MibFilePayload(BaseModel):
    file_name: str = Field()
    content: str = Field(default="")


class MibCompileRequest(BaseModel):
    profile_id: str = Field(default="snmp_lldp")
    files: Optional[List[MibFilePayload]] = Field(default=None)
    include_tree: bool = Field(default=True)


class MibTranslateRequest(BaseModel):
    profile_id: str = Field(default="snmp_lldp")
    oid: str = Field()


class ReportedEventRequest(BaseModel):
    device_id: Optional[str] = Field(default=None)
    timestamp: Optional[str] = Field(default=None)
    event_type: Optional[str] = Field(default=None)
    object: Optional[str] = Field(default=None)
    severity: Optional[str] = Field(default=None)
    message: str = Field(default="")
    raw: Optional[str] = Field(default=None)
    source_ip: Optional[str] = Field(default=None)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


app = FastAPI(
    title="NetNexus ConsistentOps Phase 2",
    description="AI 大模型在运维场景的诊断一致性第二阶段实现",
    version="0.2.0",
)

app.add_middleware(ApiLoggingMiddleware)

container = build_container()


@app.on_event("startup")
async def start_event_receivers() -> None:
    container.event_stream_hub.attach_loop(asyncio.get_running_loop())
    container.syslog_receiver.start()
    container.trap_receiver.start()


@app.on_event("shutdown")
def stop_event_receivers() -> None:
    container.syslog_receiver.stop()
    container.trap_receiver.stop()
    container.event_stream_hub.detach_loop()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "phase": "phase2",
        "data_source": "reported_events",
        "architecture": ["api", "application", "domain", "infrastructure"],
        "llm": container.diagnosis_service.llm_metadata(),
        "capabilities": [
            "live_snmp_fault_observation",
            "fact_normalization",
            "fault_fingerprint",
            "diagnosis_cache",
            "interactive_agent_chat",
            "dynamic_topology_discovery",
            "pysmi_mib_compile_and_tree",
            "syslog_event_receiver",
            "snmp_trap_event_receiver",
            "event_store",
            "event_websocket_stream",
            "event_correlation",
            "single_device_multi_anomaly_chain",
            "context_constraint_extraction",
            "single_and_multi_session_consistency_test",
        ],
        "event_receivers": {
            "syslog": container.syslog_receiver.status(),
            "snmp_trap": container.trap_receiver.status(),
        },
        "event_stream": container.event_stream_hub.status(),
    }


@app.get("/api/events")
def get_events(
    limit: int = Query(default=200, ge=1, le=1000),
    channel: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    device_id: Optional[str] = Query(default=None),
    since_seconds: Optional[int] = Query(default=None, ge=1, le=86400),
) -> dict:
    return {
        "items": container.event_store.list_events(
            limit=limit,
            channel=channel,
            event_type=event_type,
            device_id=device_id,
            since_seconds=since_seconds,
        ),
        "summary": container.event_store.summary(),
        "receivers": {
            "syslog": container.syslog_receiver.status(),
            "snmp_trap": container.trap_receiver.status(),
        },
    }


@app.delete("/api/events")
def clear_events() -> dict:
    container.event_store.clear()
    container.topology_service.clear_event_overrides()
    container.diagnosis_service.clear_cache()
    summary = container.event_store.summary()
    container.event_stream_hub.publish_reset(summary)
    return {"cleared": True, "summary": summary}


@app.websocket("/api/events/ws")
async def events_websocket(websocket: WebSocket, channel: Optional[str] = Query(default=None)) -> None:
    client = await container.event_stream_hub.connect(websocket, channel=channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await container.event_stream_hub.disconnect(client)


@app.post("/api/events/syslog")
def ingest_syslog_event(request: ReportedEventRequest) -> dict:
    event = normalize_reported_event(
        channel="syslog",
        payload=request.model_dump(exclude_none=True),
        raw=request.raw or request.message,
        source_ip=request.source_ip,
    )
    container.diagnosis_service.clear_cache()
    return {"event": container.event_store.append(event), "summary": container.event_store.summary()}


@app.post("/api/events/trap")
def ingest_trap_event(request: ReportedEventRequest) -> dict:
    event = normalize_reported_event(
        channel="snmp_trap",
        payload=request.model_dump(exclude_none=True),
        raw=request.raw or request.message,
        source_ip=request.source_ip,
    )
    container.diagnosis_service.clear_cache()
    return {"event": container.event_store.append(event), "summary": container.event_store.summary()}


@app.post("/api/events/telemetry")
def ingest_telemetry_event(request: ReportedEventRequest) -> dict:
    event = normalize_reported_event(
        channel="grpc_telemetry",
        payload=request.model_dump(exclude_none=True),
        raw=request.raw or request.message,
        source_ip=request.source_ip,
    )
    container.diagnosis_service.clear_cache()
    return {"event": container.event_store.append(event), "summary": container.event_store.summary()}


@app.get("/api/events/correlation")
def get_event_correlation(
    device_id: Optional[str] = Query(default=None),
    window_seconds: int = Query(default=300, ge=1, le=86400),
) -> dict:
    return container.correlation_engine.preview(device_id=device_id, window_seconds=window_seconds)


@app.get("/api/devices")
def get_devices() -> dict:
    return {"items": container.collector.list_devices()}


@app.get("/api/topology")
def get_topology() -> dict:
    return container.topology_service.current_topology()


@app.get("/api/topology/discovery-capabilities")
def get_topology_discovery_capabilities() -> dict:
    return container.topology_service.capabilities()


@app.get("/api/topology/discovery-config")
def get_topology_discovery_config() -> dict:
    return container.topology_config_store.get_config()


@app.post("/api/topology/discovery-config")
def update_topology_discovery_config(request: TopologyDiscoveryConfigRequest) -> dict:
    try:
        return container.topology_config_store.update_config(request.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/topology/discover")
def discover_topology(request: TopologyDiscoverRequest) -> dict:
    try:
        return container.topology_service.discover(
            mode=request.mode,
            nodes=request.nodes,
            edges=request.edges,
            options=request.options,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/mibs/profiles")
def get_mib_profiles() -> dict:
    try:
        return container.mib_service.list_profiles()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/mibs/compile")
def compile_mibs(request: MibCompileRequest) -> dict:
    try:
        return container.mib_service.compile_profile(
            profile_id=request.profile_id,
            uploaded_files=[item.model_dump() for item in request.files or []],
            include_tree=request.include_tree,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/mibs/status")
def get_mib_status(profile_id: str = Query(default="snmp_lldp")) -> dict:
    try:
        return container.mib_service.get_status(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/mibs/tree")
def get_mib_tree(
    profile_id: str = Query(default="snmp_lldp"),
    parent_oid: str = Query(default=""),
    full: bool = Query(default=False),
) -> dict:
    try:
        return container.mib_service.get_tree(profile_id=profile_id, parent_oid=parent_oid, full=full)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/mibs/translate")
def translate_mib_oid(request: MibTranslateRequest) -> dict:
    try:
        return container.mib_service.translate_oid(profile_id=request.profile_id, oid=request.oid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/fault-cases")
def get_fault_cases() -> dict:
    return {"items": container.collector.list_fault_cases()}


@app.get("/api/fault-cases/{fault_case_id}")
def get_fault_case(fault_case_id: str) -> dict:
    try:
        return container.collector.get_fault_case(fault_case_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/facts")
def get_facts(fault_case_id: str = Query(default="live-snmp-current")) -> dict:
    try:
        return {"fault_case_id": fault_case_id, "items": container.diagnosis_service.facts(fault_case_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/llm/config")
def get_llm_config() -> dict:
    return container.llm_client.metadata()


@app.post("/api/llm/config")
def configure_llm(request: LLMConfigRequest) -> dict:
    metadata = container.llm_client.configure(
        api_key=request.api_key,
        base_url=request.base_url,
        model=request.model,
        timeout_seconds=request.timeout_seconds,
        temperature=request.temperature,
        top_p=request.top_p,
        json_mode=request.json_mode,
    )
    container.llm_config_store.update_config(container.llm_client.settings_snapshot(include_api_key=True))
    container.diagnosis_service.clear_cache()
    return metadata


@app.post("/api/diagnosis/analyze")
def analyze(request: DiagnosisRequest) -> dict:
    try:
        return container.diagnosis_service.analyze(
            question=request.question,
            fault_case_id=request.fault_case_id,
            session_id=request.session_id,
            topology_group_id=request.topology_group_id,
        )
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/agent/chat")
def agent_chat(request: AgentChatRequest) -> dict:
    try:
        return container.agent_service.chat(
            message=request.message,
            fault_case_id=request.fault_case_id,
            session_id=request.session_id,
            topology_group_id=request.topology_group_id,
        )
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/agent/chat/stream")
async def agent_chat_stream(request: AgentChatRequest) -> StreamingResponse:
    async def event_source():
        try:
            async for event in container.agent_service.stream_chat(
                message=request.message,
                fault_case_id=request.fault_case_id,
                session_id=request.session_id,
                topology_group_id=request.topology_group_id,
            ):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except (LLMConfigurationError, LLMResponseError, ValueError) as exc:
            yield json.dumps(
                {
                    "type": "error",
                    "message": str(exc),
                    "error_class": exc.__class__.__name__,
                },
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(event_source(), media_type="application/x-ndjson")


@app.get("/api/agent/sessions")
def list_agent_sessions() -> dict:
    return container.agent_service.list_sessions()


@app.get("/api/agent/sessions/{session_id}")
def get_agent_session(session_id: str) -> dict:
    return container.agent_service.get_session(session_id)


@app.post("/api/consistency/test")
def consistency_test(request: ConsistencyTestRequest) -> dict:
    try:
        return run_consistency_test(
            service=container.diagnosis_service,
            fault_case_id=request.fault_case_id,
            session_modes=list(request.session_modes),
            questions=request.questions,
            run_count=request.run_count,
        )
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
