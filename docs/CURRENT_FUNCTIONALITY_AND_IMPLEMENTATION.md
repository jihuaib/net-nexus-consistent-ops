# 当前已完成功能与实现分析

本文档记录 `NetNexus ConsistentOps` 当前代码态已经完成的能力、实现方式、关键文件和边界。时间点为 2026-06-29。

## 1. 当前结论

当前系统已经形成第二阶段闭环：

```text
设备上报事件
  -> 事件标准化和存储
  -> 时间窗口关联
  -> Fault Case
  -> Fact 标准化
  -> 问题上下文和环境约束构造
  -> 故障指纹
  -> 真实大模型结构化诊断
  -> JSON Schema 校验
  -> 指纹缓存
  -> Agent 会话和一致性评分
```

当前实现不是后端规则引擎覆盖 AI 结论的架构。后端做确定性预处理和一致性护栏，包括事件归一化、Fact 排序、上下文约束、故障指纹、缓存、Schema 校验和评分；诊断结论本身由真实 OpenAI-compatible 大模型生成。Prompt 会要求模型基于事实判断根因，尤其要求模型识别同一依赖锚点上的派生异常链路；代码中没有 `rule_engine.py`，也没有规则结果强行替换 LLM 输出。

## 2. 已完成能力总览

| 能力 | 当前状态 | 主要实现 |
|---|---|---|
| 事件上报输入 | 已完成 Syslog、SNMP Trap、Telemetry API 输入 | `udp_receivers.py`、`event_normalizer.py`、`main.py` |
| 事件实时推送 | 已完成 WebSocket 广播和页面实时刷新 | `event_stream.py`、`EventTypeView.vue` |
| 当前事件存储 | 已完成进程内事件存储、过滤、摘要 | `event_store.py` |
| 事件关联 | 已完成按时间窗口、设备、接口依赖关联 | `correlation_engine.py` |
| SNMP/LLDP 拓扑发现 | 已完成 SNMP targets/CIDR 扫描、IF-MIB/LLDP-MIB 拓扑生成 | `snmp_lldp_provider.py` |
| 运行时拓扑状态覆盖 | 已完成 linkDown/linkUp 事件驱动的接口和边状态覆盖 | `topology_service.py` |
| MIB 编译和 OID 翻译 | 已完成 profile、内置 MIB、上传 MIB、Tree、Translate | `mib_service.py`、`mib_registry.py` |
| Fault Case 生成 | 已完成从当前关联事件生成 `live-snmp-current` | `snmp_observation_collector.py` |
| Fact 标准化 | 已完成接口、Syslog、Telemetry、BGP、Route、FIB、Service facts | `fact_normalizer.py`、`facts.py` |
| Fact 依赖上下文 | 已完成 `depends_on_interface`、`source_event_id` 等上下文保留 | `correlation_engine.py`、`fact_normalizer.py` |
| 诊断上下文构造 | 已完成问题目标设备、孤立节点、事实链、候选类型和证据摘要 | `diagnosis_service.py`、`diagnosis_context.py` |
| 故障指纹 | 已完成 fact 指纹和无活动故障上下文指纹 | `fingerprint.py` |
| 真实 LLM 诊断 | 已完成 OpenAI-compatible Chat Completions 和 Agents SDK 调用 | `openai_compatible_client.py`、`agent_service.py` |
| 知识库/RAG | 已完成内置 Runbook、自定义文档、BM25 检索和诊断上下文注入 | `knowledge_base.py`、`KnowledgeView.vue` |
| Schema 校验 | 已完成 LLM 输出字段和列表非空校验 | `diagnosis_schema.py` |
| 诊断缓存 | 已完成基于故障指纹的进程内缓存 | `diagnosis_service.py` |
| Agent 会话 | 已完成同步和流式 Agent、会话历史、工具轨迹 | `agent_service.py`、`useAgentWorkspace.js` |
| 一致性测试 | 已完成单会话和多会话评分 | `consistency_service.py` |
| 前端工作台 | 已完成诊断、拓扑、事实、工具轨迹、一致性、事件、MIB、设置页面 | `App.vue`、`DiagnosisView.vue`、`views/events/*`、`MibView.vue` |
| FRR lab | 已完成 Spine-Leaf lab、SNMP、LLDP、真实链路事件 agent | `labs/frr-spine-leaf/*` |
| 回归验证 | 已完成后端单测、前端构建、本地阶段脚本 | `backend/tests/test_phase1.py`、`scripts/test_phase1.sh` |

## 3. 后端架构和依赖装配

后端入口是 `backend/app/main.py`。它负责：

1. 定义 FastAPI 应用。
2. 挂载 CORS 和 API 日志中间件。
3. 在启动时启动 Syslog 和 Trap UDP receiver。
4. 暴露健康、事件、拓扑、MIB、事实、LLM 配置、诊断、Agent、Consistency API。

依赖装配集中在 `backend/app/core/container.py`：

```text
EventStore
  -> CorrelationEngine
  -> SnmpObservationCollector
  -> DiagnosisService
  -> AgentService

MibProfileRegistry
  -> MibService
  -> SnmpLldpTopologyProvider
  -> TopologyService

EventStore listeners
  -> TopologyService.apply_event
  -> EventStreamHub.publish_event
```

这个装配方式让事件进入 `EventStore` 后自动触发两件事：

1. WebSocket 推送给事件页面。
2. linkDown/linkUp 事件覆盖当前拓扑中的接口和边状态。

## 4. 事件输入和实时流

### 4.1 支持的事件入口

当前有两类入口：

1. UDP receiver：
   - Syslog receiver，默认 `0.0.0.0:1514`
   - SNMP Trap receiver，默认 `0.0.0.0:1162`
2. HTTP API：
   - `POST /api/events/syslog`
   - `POST /api/events/trap`
   - `POST /api/events/telemetry`

`backend/app/infrastructure/events/udp_receivers.py` 实现 UDP 监听。Syslog 文本直接进入 `normalize_reported_event`，SNMP Trap 二进制包先经过 `snmp_trap_decoder.py` 解码。

### 4.2 SNMP Trap 解码

`backend/app/infrastructure/events/snmp_trap_decoder.py` 支持标准 SNMPv2 和 SNMPv1 trap 的基础解析。它识别：

- linkDown：`.1.3.6.1.6.3.1.1.5.3`
- linkUp：`.1.3.6.1.6.3.1.1.5.4`
- `sysName`
- `ifIndex`
- `ifDescr`
- `ifName`
- `ifAdminStatus`
- `ifOperStatus`

解码后会生成结构化 payload。事件名由 trap state 动态生成，不从后端故障类型枚举表读取：

```json
{
  "device_id": "leaf-01",
  "event_type": "INTERFACE_OPER_<STATE>",
  "object": "eth1",
  "severity": "critical",
  "attributes": {
    "trap_name": "linkDown",
    "if_index": "2",
    "if_name": "eth1",
    "if_oper_status": "down"
  }
}
```

### 4.3 事件标准化

`backend/app/application/event_normalizer.py` 将不同来源的输入统一为 `ReportedEvent`：

- 自动生成 `event_id`
- 归一化时间戳
- 对显式 `event_type` 或协议解析结果只做字符串规范化，不做业务类型 alias 映射
- 对没有显式类型的 Syslog/raw text 标记为 `RAW_REPORTED_EVENT`
- 归一化 severity 和 confidence
- 保留原始 `raw` 和 `attributes`

`backend/app/application/event_extractor.py` 负责 raw event 的 AI 抽取：

- 只处理 `RAW_REPORTED_EVENT` 或 `UNKNOWN_EVENT`
- 输出 `event_type`、`object`、`severity`、`confidence`、`attributes`、`evidence`
- 只做事件字段抽取，不做根因诊断
- LLM 未配置或抽取失败时保留 raw event，不用关键词规则兜底分类

### 4.4 事件存储和推送

`backend/app/application/event_store.py` 使用进程内 `deque` 保存最近事件，支持：

- 按 channel、event_type、device_id、since_seconds 过滤
- 事件总量、按 channel、按 type 摘要
- listener 机制

`backend/app/application/event_stream.py` 实现 WebSocket hub：

- `GET /api/events/ws`
- 支持按 channel 订阅
- 收到事件后推送 `{ "type": "event", "event": ... }`
- 清空事件后推送 `{ "type": "reset", "summary": ... }`

前端 `frontend/src/views/events/EventTypeView.vue` 使用 WebSocket 连接事件流，并在 Syslog、Trap、Telemetry 三个页面复用同一套过滤、详情和 KPI 组件。

## 5. 事件关联和 Fault Case

`backend/app/application/correlation_engine.py` 负责把原始事件变成当前诊断窗口。

当前关联策略：

1. 从 `EventStore` 取最近 `window_seconds` 内事件，默认 300 秒。
2. 过滤活动故障事件，带恢复语义的事件类型后缀或 `attributes.recovery=true` 会抑制同一关联锚点上更早的异常事件。
3. 按 severity、timestamp、device、object 选择窗口锚点，不按固定 fact_type 优先级判断主因。
4. 只把同一设备、同一依赖接口的事件纳入当前故障窗口。
5. 输出 observations，供 collector 生成 Fault Case。

`backend/app/infrastructure/collectors/snmp_observation_collector.py` 不从 SNMP 轮询结果直接构造故障。SNMP/LLDP 只提供拓扑上下文，真正诊断输入来自 `CorrelationEngine` 输出的上报事件窗口。

当没有活动故障事件时，它返回：

```text
state = no_active_fault
facts = []
```

这保证系统不会在没有上报事件时默认编造接口 Down。

## 6. 拓扑发现和运行时状态

### 6.1 SNMP/LLDP 拓扑发现

`backend/app/infrastructure/topology/snmp_lldp_provider.py` 实现当前主运行模式 `snmp_lldp`。

发现过程：

1. 从 `TopologyDiscoveryConfigStore` 读取配置：
   - profile_id
   - community
   - targets
   - scan_cidrs
   - timeout_seconds
   - scan_concurrency
   - max_scan_hosts
2. 如果配置了 explicit targets，直接使用。
3. 如果配置了 CIDR，先扫描 `sysName` 判断 SNMP 可达设备。
4. 对每个设备 walk profile 绑定的 OID：
   - `sysName`
   - `sysDescr`
   - `ifName`
   - `ifAdminStatus`
   - `ifOperStatus`
   - `lldpLocPortId`
   - `lldpRemSysName`
   - `lldpRemPortId`
5. 生成 nodes、interfaces、edges。

OID 不硬编码在 provider 业务逻辑里，而是来自 `mibs/profiles/*.json`。当前有：

- `snmp_lldp`
- `h3c_snmp_lldp`

### 6.2 拓扑服务

`backend/app/application/topology_service.py` 负责：

- `/api/topology`
- `/api/topology/discover`
- `/api/topology/discovery-capabilities`
- `/api/topology/discovery-config`
- connected component 分组
- linkDown/linkUp 事件覆盖接口和边状态

运行时事件覆盖逻辑：

1. `EventStore.append` 通知 `TopologyService.apply_event`。
2. 如果事件能从类型后缀或 `if_oper_status` 推导出接口 up/down，且带有接口线索，保存 `(device_id, interface)` 的状态覆盖。
3. `current_topology()` 返回拓扑时，把覆盖状态合并进 node interface 和 edge。

这使前端拓扑在真实接口 down/up 后可以反映运行时链路状态。

## 7. MIB 编译、OID Tree 和 OID 翻译

MIB 能力由 `backend/app/infrastructure/mib/*` 实现。

`MibProfileRegistry` 负责读取 `mibs/profiles/*.json`，暴露 public profile。

`MibService` 负责：

- 列出 profiles：`GET /api/mibs/profiles`
- 编译 profile：`POST /api/mibs/compile`
- 查询编译状态：`GET /api/mibs/status`
- 查询 OID Tree：`GET /api/mibs/tree`
- 翻译 OID：`POST /api/mibs/translate`
- 将上传 MIB 写入 `mibs/workspace/<profile>/uploads`

`MibRegistry` 负责解析 MIB 文件、构建对象索引、构建树、做 OID 翻译。

前端 `MibView.vue` 和 `MibCompilerPanel.vue` 提供 profile 选择、上传、编译、Tree 展示和 OID 翻译。

## 7.5 知识库/RAG

知识库能力由 `backend/app/application/knowledge_base.py` 实现，当前采用 `rank-bm25` 本地 BM25 检索，并保留无依赖 fallback；检索接口和文档结构可替换为向量库、混合检索和重排模型。

当前能力：

- 读取 `knowledge/*.md` 作为内置知识。
- 将自定义文档持久化到 `.netnexus/knowledge_documents.json`。
- 按 Markdown 标题和段落分块，默认每块约 900 字，并保留少量 overlap。
- 使用 `rank_bm25.BM25Okapi` 检索，结合标题、标签、来源、短语命中和词项覆盖度做 hybrid 排名。
- 不维护网络故障类型 query expansion 表；检索 query 由用户问题、实时 facts、context 和证据文本直接构造。
- 提供文档列表、保存、删除和搜索 API。
- 诊断缓存 miss 时，按用户问题、facts、依赖接口、下一跳、远端设备和证据摘要构造检索 query。
- 将命中的片段注入 LLM payload 的 `knowledge_context`。

API：

| API | 说明 |
|---|---|
| `GET /api/knowledge/documents` | 查询知识库文档 |
| `POST /api/knowledge/documents` | 新增或更新自定义文档 |
| `DELETE /api/knowledge/documents/{document_id}` | 删除自定义文档 |
| `POST /api/knowledge/search` | 检索知识片段 |

前端 `frontend/src/views/KnowledgeView.vue` 提供文档管理和检索验证页面。RAG 的定位是补充厂商手册、SOP 和历史案例，不能替代实时 facts 判断。

## 8. Fact 标准化和上下文增强

`backend/app/domain/facts.py` 定义 Fact：

```text
fact_id
device_id
scope
object
fact_type
value
severity
timestamp
source
confidence
context
```

`context` 是当前新增的事实追踪字段，用于把事件关联过程中的依赖和来源保留下来。典型字段包括：

- `depends_on_interface`
- `source_event_id`
- `remote_device`
- `remote_interface`
- `next_hop`
- `target`
- `channel`
- `in_bps`
- `out_bps`

`backend/app/application/fact_normalizer.py` 当前优先从 `reported_events` 通用生成 Fact：`fact_type = event_type`、`value = message/raw`、`context = attributes + source_event_id`。因此新增事件类型不需要为每类故障新增一个 Fact 分支。

新增的 `context` 字段解决的是 AI 输入信息不完整的问题。例如事件不只说明“异常”，还会保留依赖接口、下一跳、远端设备、AI 抽取证据和来源 `event_id`。

前端 `frontend/src/components/FactListPanel.vue` 会展示 Fact 的依赖接口、下一跳、远端设备和来源事件。

## 9. 诊断输入构造

诊断输入由 `backend/app/application/diagnosis_service.py` 组装。

### 9.1 Question Context

`build_question_context` 从用户问题和拓扑中提取：

- 用户问题原文
- 是否有活动 facts
- 拓扑节点数、边数
- 用户提到的设备
- 用户提到的接口
- 提到设备的邻居、degree、是否孤立
- 当前事件数量
- fact 类型集合
- fact 设备集合

这让系统在没有活动故障事件时也能回答“用户点名的设备在拓扑里是否孤立”。

### 9.2 Context Constraints

`backend/app/application/diagnosis_context.py` 生成环境事实摘要：

- `primary_signal`
- `fact_chain`
- `fact_types`
- `affected_devices`
- `affected_services`
- `evidence`
- `question_context`

这里的 `is_deterministic` 当前为 `False`，语义是：这些内容是环境事实和一致性约束，不是后端规则结论。后端不再提供 `candidate_fault_types` 或 `allowed_fault_types`，Prompt 要求模型结合 facts、topology、question_context 和 knowledge_context 自行生成 `fault_type`。

## 10. LLM 诊断、Schema 和缓存

### 10.1 LLM 客户端

`backend/app/infrastructure/llm/openai_compatible_client.py` 实现 OpenAI-compatible Chat Completions：

- 必须配置 `LLM_API_KEY`
- 必须配置 `LLM_BASE_URL`
- 必须配置 `LLM_MODEL`
- 默认 `temperature=0`
- 默认 `top_p=0.1`
- 默认启用 JSON mode
- 缺少配置时抛出 `LLMConfigurationError`
- Provider 返回非法 JSON 时抛出 `LLMResponseError`

本项目不提供本地模拟诊断。没有真实 LLM 配置时，诊断相关接口返回 503。

### 10.2 Prompt 约束

`backend/app/application/llm_prompt.py` 的系统 Prompt 要求：

- 只能基于输入事实，不允许编造设备、接口、路由或告警。
- 必须输出 JSON。
- `fault_type` 由模型基于证据生成稳定、简短、可机器读取的英文大写标识。
- evidence 必须引用输入 facts、question_context 或 context_constraints。
- 没有活动 facts 但用户点名设备时，要结合 topology/question_context 判断。
- 证据不足时设置 `need_more_data=true`。
- 同一 `fault_fingerprint` 下核心字段保持一致。
- 多个异常通过 context 指向同一底层对象时，可将该对象作为根因候选；缺少底层根因证据时需要 `need_more_data=true`。
- knowledge_context 只能用于解释术语、补充排障步骤和建议，不能覆盖实时 facts。

### 10.3 Schema 校验

`backend/app/application/diagnosis_schema.py` 使用 Pydantic 校验 LLM 输出：

- `fault_type`
- `root_cause`
- `affected_devices`
- `affected_services`
- `evidence`
- `diagnosis_chain`
- `confidence`
- `recommendation`
- `need_more_data`

其中 evidence、diagnosis_chain、recommendation 必须非空。

### 10.4 指纹和缓存

`backend/app/domain/fingerprint.py` 生成两类指纹：

1. 有 facts 时生成 `fp_*`：
   - topology_id
   - related_devices
   - fact_count
   - fact_types
   - observed_facts
2. 没有 facts 时生成 `fp_ctx_*`：
   - topology_id
   - state
   - mentioned_nodes
   - mentioned_interfaces
   - active_event_count

`DiagnosisService` 用指纹作为缓存 key。首次诊断调用 LLM，后续同一指纹直接返回缓存结果，并替换 question、session_id、topology_group_id。

## 11. Agent 会话和流式响应

`backend/app/application/agent_service.py` 实现 Agent 会话层。

支持接口：

- `POST /api/agent/chat`
- `POST /api/agent/chat/stream`
- `GET /api/agent/sessions`
- `GET /api/agent/sessions/{session_id}`

同步接口使用 OpenAI Agents SDK 的 `Runner.run_sync`。

流式接口使用 `Runner.run_streamed`，后端以 NDJSON 返回：

- `message`
- `stage`
- `text_delta`
- `final`
- `error`

工具轨迹包括：

- `collect_observations`
- `normalize_facts`
- `build_fault_fingerprint`
- `diagnosis_cache`
- `llm_reasoning`
- `context_constraints`
- `consistency_guard`

这里的 `consistency_guard` 表示输出进入固定字段结构、Schema 校验、指纹缓存和一致性评分流程，不表示规则引擎覆盖诊断结论。

## 12. 一致性测试

`backend/app/application/consistency_service.py` 实现一致性评分。

默认问题集覆盖：

- 当前故障
- leaf-01 业务不通
- BGP 问题
- 路由缺失
- FIB 未下发
- 业务探测不可达
- 重新诊断

测试模式：

- single_session：所有问题使用同一个 session_id
- multi_session：每轮使用不同 session_id

比较字段包括：

- `fault_fingerprint`
- `fault_type`
- `root_cause`
- `affected_devices`
- `affected_services`
- `evidence`
- `diagnosis_chain`
- `recommendation`
- `need_more_data`

同一指纹下由于缓存复用，预期核心字段一致。

## 13. 前端工作台

前端入口是 `frontend/src/App.vue`，全局状态编排在 `frontend/src/composables/useAgentWorkspace.js`。

已完成页面：

- 诊断工作台：`DiagnosisView.vue`
- MIB 页面：`MibView.vue`
- 知识库页面：`KnowledgeView.vue`
- Syslog 事件页：`SyslogEventsView.vue`
- Trap 事件页：`TrapEventsView.vue`
- Telemetry 事件页：`TelemetryEventsView.vue`
- 设置弹窗：LLM 配置和拓扑发现配置

诊断工作台整合：

- AgentChat
- DiagnosisPanel
- ToolTracePanel
- FactListPanel
- ConsistencyPanel
- TopologyPanel
- TopologyGraph
- TopologyDiscoveryConfigPanel

`useAgentWorkspace.js` 负责：

- 加载健康状态、LLM 配置、拓扑能力、拓扑配置、拓扑数据
- 发送流式 Agent 请求
- 处理 `stage`、`text_delta`、`final`、`error`
- 管理本地会话记录和 active session
- 拓扑事件 WebSocket 重连
- 收到 linkDown/linkUp 后刷新拓扑

事件页面复用 `EventTypeView.vue`，支持：

- WebSocket 实时连接状态
- 刷新
- 清空事件
- 按 severity、event_type、device、keyword 过滤
- 事件列表
- 事件详情
- 接收器状态
- 关联摘要

## 14. FRR 本地实验环境

本地 lab 位于 `labs/frr-spine-leaf`。

组成：

- `spine-01`
- `leaf-01`
- `leaf-02`
- `isolated-01`

镜像构建文件：

- `Dockerfile.snmp`
- `image/netnexus-start.sh`
- `image/netnexus-lldp-mib-agent.py`
- `image/netnexus-link-event-agent.py`

`netnexus-link-event-agent.py` 监听真实 `/sys/class/net` 和 `ip monitor link`：

1. 发现 eth* 接口状态变化。
2. 发送 UDP Syslog 到后端。
3. 调用 `snmptrap` 发送标准 linkDown/linkUp Trap。

因此本地验证可以通过：

```bash
docker exec netnexus-leaf-01 ip link set eth1 down
docker exec netnexus-leaf-01 ip link set eth1 up
```

触发真实链路事件，而不是页面模拟故障。

## 15. 关键 API

| API | 说明 |
|---|---|
| `GET /api/health` | 健康、能力、LLM、事件 receiver 状态 |
| `GET /api/events` | 查询事件列表和摘要 |
| `DELETE /api/events` | 清空事件、清空拓扑覆盖、清空诊断缓存 |
| `GET /api/events/ws` | WebSocket 事件流 |
| `POST /api/events/syslog` | 手动写入 Syslog 事件 |
| `POST /api/events/trap` | 手动写入 Trap 事件 |
| `POST /api/events/telemetry` | 手动写入 Telemetry 事件 |
| `GET /api/events/correlation` | 查看当前事件关联摘要 |
| `GET /api/topology` | 查询当前拓扑 |
| `POST /api/topology/discover` | 触发拓扑发现 |
| `GET/POST /api/topology/discovery-config` | 查询/更新拓扑发现配置 |
| `GET /api/mibs/profiles` | 查询 MIB profiles |
| `POST /api/mibs/compile` | 编译 MIB profile |
| `GET /api/mibs/tree` | 查询 MIB Tree |
| `POST /api/mibs/translate` | OID 翻译 |
| `GET /api/knowledge/documents` | 查询知识库文档 |
| `POST /api/knowledge/documents` | 新增或更新自定义知识文档 |
| `DELETE /api/knowledge/documents/{document_id}` | 删除自定义知识文档 |
| `POST /api/knowledge/search` | 检索知识库片段 |
| `GET /api/fault-cases` | 查询当前 fault case |
| `GET /api/facts` | 查询当前标准化 facts |
| `GET/POST /api/llm/config` | 查询/更新 LLM 配置 |
| `POST /api/diagnosis/analyze` | 直接诊断 |
| `POST /api/agent/chat` | Agent 同步诊断 |
| `POST /api/agent/chat/stream` | Agent 流式诊断 |
| `GET /api/agent/sessions` | 会话列表 |
| `POST /api/consistency/test` | 一致性测试 |

## 16. 验证情况

当前已经验证：

```bash
backend/.venv/bin/python -m unittest discover backend/tests
```

结果：

```text
Ran 31 tests
OK (skipped=3)
```

跳过的 3 个测试需要真实 LLM 环境变量或页面运行时配置：

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`

前端构建已验证：

```bash
cd frontend
npm run build
```

结果：Vite production build 成功。

阶段脚本已验证：

```bash
./scripts/test_phase1.sh
```

结果：FRR lab 启动、后端测试、前端构建均通过。

## 17. 当前边界和未完成项

1. 事件和诊断缓存仍是进程内实现，生产环境需要 Redis、Kafka 或数据库。
2. Telemetry 当前通过 HTTP API 写入 `grpc_telemetry` channel，尚未实现生产级 gRPC/gNMI 长连接接收器。
3. 当前没有长期诊断报告和诊断运行记录持久化；知识库/RAG 已有本地 BM25 实现，生产可升级为向量检索、重排模型和权限管理。
4. 当前没有后端规则引擎覆盖 LLM 输出。系统依赖事实输入、Prompt 约束、Schema 校验、指纹缓存和一致性评分保证第二阶段一致性。
5. 第三阶段三台以上设备联动根因分析尚未实现。
6. 前端拓扑是轻量自绘和状态展示，复杂大规模拓扑可后续替换为 AntV G6 等图引擎。
7. LLM 配置虽然支持页面保存，但当前存储方式适合开发和演示，生产应改为加密持久化和权限控制。
