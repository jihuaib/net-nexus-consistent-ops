from __future__ import annotations

from dataclasses import dataclass
import os

from ..application.agent_service import AgentService
from ..application.correlation_engine import CorrelationEngine
from ..application.diagnosis_service import DiagnosisService
from ..application.event_stream import EventStreamHub
from ..application.event_store import EventStore
from ..application.event_extractor import EventExtractionService
from ..application.fact_normalizer import FactNormalizer
from ..application.knowledge_base import KnowledgeBaseService
from ..application.topology_service import TopologyService
from ..infrastructure.collectors import SnmpObservationCollector
from ..infrastructure.events import SnmpTrapReceiver, SyslogReceiver
from ..infrastructure.llm.config_store import LLMConfigStore
from ..infrastructure.llm.openai_compatible_client import OpenAICompatibleLLMClient
from ..infrastructure.mib import MibProfileRegistry, MibService
from ..infrastructure.topology import SnmpLldpTopologyProvider, TopologyDiscoveryConfigStore


@dataclass(frozen=True)
class AppContainer:
    collector: SnmpObservationCollector
    fact_normalizer: FactNormalizer
    mib_service: MibService
    event_store: EventStore
    event_stream_hub: EventStreamHub
    correlation_engine: CorrelationEngine
    syslog_receiver: SyslogReceiver
    trap_receiver: SnmpTrapReceiver
    topology_config_store: TopologyDiscoveryConfigStore
    topology_service: TopologyService
    llm_config_store: LLMConfigStore
    llm_client: OpenAICompatibleLLMClient
    event_extractor: EventExtractionService
    knowledge_base_service: KnowledgeBaseService
    diagnosis_service: DiagnosisService
    agent_service: AgentService


def build_container() -> AppContainer:
    fact_normalizer = FactNormalizer()
    event_store = EventStore()
    correlation_engine = CorrelationEngine(
        event_store,
        window_seconds=int(os.getenv("EVENT_CORRELATION_WINDOW_SECONDS", "300")),
    )
    mib_profile_registry = MibProfileRegistry()
    mib_service = MibService(mib_profile_registry)
    topology_config_store = TopologyDiscoveryConfigStore()
    snmp_topology_provider = SnmpLldpTopologyProvider(
        profile_registry=mib_profile_registry,
        config_provider=topology_config_store.get_config,
    )
    collector = SnmpObservationCollector(
        snmp_topology_provider,
        correlation_engine=correlation_engine,
    )
    syslog_receiver = SyslogReceiver(
        event_store,
        host=os.getenv("SYSLOG_RECEIVER_HOST", "0.0.0.0"),
        port=int(os.getenv("SYSLOG_RECEIVER_PORT", "1514")),
        enabled=os.getenv("SYSLOG_RECEIVER_ENABLED", "1") != "0",
    )
    trap_receiver = SnmpTrapReceiver(
        event_store,
        host=os.getenv("TRAP_RECEIVER_HOST", "0.0.0.0"),
        port=int(os.getenv("TRAP_RECEIVER_PORT", "1162")),
        enabled=os.getenv("TRAP_RECEIVER_ENABLED", "1") != "0",
    )
    topology_service = TopologyService(
        collector,
        providers=[snmp_topology_provider],
    )
    event_stream_hub = EventStreamHub()
    event_store.add_listener(topology_service.apply_event)
    event_store.add_listener(event_stream_hub.publish_event)
    llm_config_store = LLMConfigStore()
    llm_client = OpenAICompatibleLLMClient.from_env(saved_config=llm_config_store.get_config())
    event_extractor = EventExtractionService(llm_client)
    knowledge_base_service = KnowledgeBaseService()
    diagnosis_service = DiagnosisService(
        collector=collector,
        fact_normalizer=fact_normalizer,
        llm_client=llm_client,
        knowledge_base=knowledge_base_service,
    )
    agent_service = AgentService(diagnosis_service)
    return AppContainer(
        collector=collector,
        fact_normalizer=fact_normalizer,
        event_store=event_store,
        event_stream_hub=event_stream_hub,
        correlation_engine=correlation_engine,
        syslog_receiver=syslog_receiver,
        trap_receiver=trap_receiver,
        mib_service=mib_service,
        topology_config_store=topology_config_store,
        topology_service=topology_service,
        llm_config_store=llm_config_store,
        llm_client=llm_client,
        event_extractor=event_extractor,
        knowledge_base_service=knowledge_base_service,
        diagnosis_service=diagnosis_service,
        agent_service=agent_service,
    )
