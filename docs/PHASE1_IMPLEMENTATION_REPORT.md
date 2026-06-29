# 第一阶段实现报告

## 1. 阶段目标

第一阶段目标是完成赛题 6.4.3 的 60% 完成度要求：

```text
在单一设备确定网络故障环境中，
Agent 单会话多次交互以及多会话交互时，
能够保持输出内容一致。
```

当前实现以 SNMP 实时采集到的 `leaf-01 eth1 接口 Down` 为第一阶段确定故障观测，完成了从设备采集、事实、指纹、诊断、缓存到一致性评分的闭环。

本阶段对 Agent 的定义是：

```text
会话式人机界面
  + 后端 Agent 编排
  + 工具调用轨迹
  + 会话历史
  + 一致性兜底
```

因此，用户看到的是可追问的 Agent 界面；系统内部则调用事实标准化、故障指纹、证据构造和诊断缓存等确定性工具，最终诊断由真实大模型生成。

## 2. 技术选型

| 模块 | 当前实现 | 后续扩展 |
|---|---|---|
| 后端语言 | Python | 保持 Python |
| 后端框架 | FastAPI | 可继续扩展为模块化服务 |
| 前端框架 | Vue 3 + Vite | 后续接入 AntV G6 拓扑 |
| 数据源 | 原生 Python SNMP walk 采集 FRR SNMP/LLDP lab 或真实设备 | NETCONF、gRPC Telemetry、Syslog |
| 缓存 | 进程内字典 | Redis |
| 诊断方式 | OpenAI-compatible 大模型 + 规则证据约束 | 大模型 + RAG + 真实采集 |
| MIB 编译 | `pysmi` SMIv2 解析 + provider profile | 厂商 MIB、Trap 解析、MIB 包版本管理 |
| 测试 | unittest | 增加 API 和前端 E2E |

## 3. 代码模块映射

| 文件 | 作用 |
|---|---|
| `backend/app/main.py` | FastAPI API 入口 |
| `backend/app/core/container.py` | 依赖装配，绑定采集器和应用服务 |
| `backend/app/application/agent_service.py` | Agent 会话、消息历史、工具调用轨迹和自然语言回答 |
| `backend/app/application/diagnosis_service.py` | 大模型诊断编排、Schema 校验和诊断缓存 |
| `backend/app/application/diagnosis_schema.py` | 大模型诊断 JSON Schema |
| `backend/app/application/llm_prompt.py` | 大模型诊断 Prompt 和上下文构造 |
| `backend/app/application/fact_normalizer.py` | 原始观测数据标准化为 Fact |
| `backend/app/application/topology_service.py` | 拓扑发现编排、运行时拓扑状态和发现能力声明 |
| `backend/app/application/consistency_service.py` | 单会话、多会话一致性测试和评分 |
| `backend/app/domain/facts.py` | Fact 领域对象 |
| `backend/app/domain/fingerprint.py` | 生成稳定故障指纹 |
| `backend/app/infrastructure/collectors/base.py` | 采集器抽象接口 |
| `backend/app/infrastructure/collectors/snmp_observation_collector.py` | 基于 SNMP 拓扑和接口状态生成当前故障观测 |
| `backend/app/infrastructure/topology/snmp_client.py` | 原生 Python SNMP walk 客户端 |
| `backend/app/infrastructure/mib/mib_registry.py` | `pysmi` MIB 编译适配、OID 索引、Tree 和 OID 翻译 |
| `backend/app/infrastructure/mib/mib_service.py` | MIB profile 编译服务、上传 MIB 管理 |
| `backend/app/infrastructure/mib/profile_registry.py` | 读取 `mibs/profiles/*.json` 中的 provider profile 和 OID 绑定 |
| `backend/app/infrastructure/topology/snmp_lldp_provider.py` | 标准 SNMP IF-MIB/LLDP-MIB 拓扑发现 provider |
| `backend/app/infrastructure/llm/openai_compatible_client.py` | 真实大模型接入客户端 |
| `backend/tests/test_phase1.py` | 第一阶段单元测试 |
| `frontend/src/api/` | 前端 API 访问层 |
| `frontend/src/composables/useAgentWorkspace.js` | 前端 Agent 工作台状态和动作编排 |
| `frontend/src/components/` | 前端业务组件、应用导航和 scoped CSS |
| `frontend/src/components/ui/` | 通用面板、页面头等基础 UI 组件 |
| `frontend/src/views/` | 诊断、MIB、设置功能页；拓扑画布集成在诊断页 |
| `frontend/src/App.vue` | 应用壳、导航和 view 切换 |
| `frontend/src/style.css` | 全局 reset 和基础控件样式 |

## 4. 数据流

```text
API / Agent 会话
  -> DiagnosisService
  -> ObservationCollector
  -> SnmpObservationCollector
  -> SnmpLldpTopologyProvider
  -> SNMP IF-MIB / LLDP-MIB 实时采集
  -> 当前故障 observations
  -> Fact 标准化
  -> 故障指纹 fingerprint
  -> 查询诊断缓存
  -> 构造规则证据和 LLM Prompt
  -> 调用真实 OpenAI-compatible 大模型
  -> 大模型返回 JSON
  -> Schema 校验和归一化
  -> 一致性测试评分
  -> 前端展示
```

## 5. 题目要求覆盖情况

| 题目点 | 第一阶段覆盖情况 | 说明 |
|---|---|---|
| Agent 运维一致性兜底策略 | 已覆盖第一版 | 使用故障指纹、大模型 JSON、Schema 校验、缓存和评分 |
| 设备侧少变动或不变动 | 第一阶段通过 SNMP 标准协议采集，不在设备侧装 Agent | 后续继续接入现有协议 |
| 单设备确定故障一致性 | 已实现 | 对应 60% 完成度 |
| 单设备多异常一致性 | 未实现 | 第二阶段实现 |
| 三台以上 Spine-Leaf 联动 | 已提供 FRR SNMP/LLDP 测试环境，未完成联动诊断 | 第三阶段实现完整分析 |
| MIB/Trap 可解析基础 | 已实现 Python MIB 编译、MIB Tree、OID 翻译和 profile 绑定 | Trap 接收器属于后续采集器扩展 |
| 多会话输出一致 | 已实现 | `multi_session` 模式验证 |
| 单会话多次输出一致 | 已实现 | `single_session` 模式验证 |

## 6. 当前故障观测

故障：

```text
leaf-01 eth1 接口 Down
```

当前数据说明：

当前数据来自 SNMP 实时采集。测试时使用 FRR SNMP/LLDP lab 作为真实协议设备环境；切到真实设备时仍使用同一套 `SnmpLldpTopologyProvider`、MIB profile 和 `ObservationCollector` 数据结构。

原始观测：

1. `sysName` 发现 `spine-01`、`leaf-01`、`leaf-02`、`isolated-01`。
2. `LLDP-MIB` 发现 `spine-01 -- leaf-01`、`spine-01 -- leaf-02`。
3. `IF-MIB` 发现 `leaf-01 eth1 ifOperStatus=down`。
4. `isolated-01` 只在管理网可达，不参与业务链路。

标准化事实：

| fact_type | 说明 |
|---|---|
| `INTERFACE_OPER_DOWN` | 接口运行状态 Down |

## 6.1 拓扑发现实现

拓扑不能由前端固定写死。当前实现已经把拓扑入口放到后端：

```text
前端 TopologyPanel
  -> /api/topology 或 /api/topology/discover
  -> TopologyService
  -> SnmpLldpTopologyProvider
  -> SNMP sysName / IF-MIB / LLDP-MIB
  -> nodes / edges / discovery
```

接口返回示例：

```json
{
  "id": "snmp-lldp-discovered-topology",
  "nodes": [{"id": "leaf-01", "role": "leaf"}],
  "edges": [{"source": "leaf-01", "target": "spine-01", "protocol": "snmp-lldp"}],
  "discovery": {
    "mode": "snmp_lldp",
    "node_count": 4,
    "edge_count": 2,
    "protocols": ["SNMPv2c", "IF-MIB", "LLDP-MIB"]
  }
}
```

真实设备数量和连接关系的发现方式：

| 发现对象 | 推荐协议/数据源 | 输出 |
|---|---|---|
| 设备身份 | SNMP `sysName/sysObjectID`、NETCONF、gNMI system paths | `nodes` |
| 接口状态 | SNMP IF-MIB/IF-XTable、NETCONF `ietf-interfaces`、Telemetry | 节点接口状态、告警事实 |
| 二层连接 | LLDP-MIB `lldpRemTable`、厂商 NDP/CDP 表 | `edges.source/target` 和接口 |
| 三层连接 | BGP-LS、BMP、路由邻居表 | L3 `edges` 和路由相关事实 |

第一阶段主运行时模式：

| 模式 | 用途 |
|---|---|
| `snmp_lldp` | 通过标准 SNMP `sysName`、`IF-MIB`、`LLDP-MIB` 发现节点、接口和邻居链路，作为接近真机的实验模式 |

因此，页面展示的设备数和链路数来自 API 的 `node_count` 和 `edge_count`，不是 Vue 组件中的固定值。

FRR SNMP/LLDP lab 位于：

```text
labs/frr-spine-leaf/
├── docker-compose.yml
├── spine-01/
├── leaf-01/
├── leaf-02/
└── isolated-01/
```

实验拓扑：

```text
leaf-01 -- spine-01 -- leaf-02
isolated-01
```

FRR lab 容器内包含 `FRR + snmpd + lldpd + LLDP-MIB pass_persist subagent`。后端 `snmp_lldp` provider 只通过 SNMP 读取 MIB profile 中绑定的 OID：

```text
sysName / sysDescr
IF-MIB ifName / ifOperStatus
LLDP-MIB lldpLocPortTable / lldpRemTable
```

这些 OID 来自 `mibs/profiles/snmp_lldp.json` 或 `mibs/profiles/h3c_snmp_lldp.json`，不是 provider 代码硬编码。页面可以选择 profile、上传 MIB、调用 Python 后端编译并生成 MIB Tree。

FRR 适合验证三层拓扑、BGP 邻居、接口 down、路由异常和孤立设备分组，不用于冒充完整 H3C 交换机协议栈。真实 H3C 设备接入时优先复用 `SnmpLldpTopologyProvider`，在设置里调整 `scan_cidrs/targets/community/profile_id` 即可；需要其他协议时再新增 provider：

```text
NetconfTelemetryTopologyProvider
BgpLsBmpTopologyProvider
```

这些 provider 输出同样的 `nodes/edges/discovery`，因此前端和 Agent 不需要改。

## 7. 故障指纹

当前故障指纹：

```text
fp_d3c161a19522c6af
```

指纹由以下字段生成：

```text
topology_id
primary_device
primary_object
normalized_fault_type
related_devices
key_facts
```

设计目的：

1. 用户不同问法不会影响故障指纹。
2. 单会话和多会话不会影响故障指纹。
3. Fact 顺序变化不会影响故障指纹。
4. 同一故障可直接命中诊断缓存。

## 8. 诊断输出

核心输出：

```json
{
  "fault_fingerprint": "fp_d3c161a19522c6af",
  "fault_type": "INTERFACE_DOWN",
  "root_cause": "leaf-01 GE1/0/1 接口 Down，导致该接口承载链路不可用",
  "affected_devices": ["leaf-01"],
  "affected_services": ["uplink-service"],
  "confidence": 0.96,
  "need_more_data": false
}
```

证据：

1. `leaf-01 GE1/0/1` 接口运行状态为 Down。
2. `leaf-01 GE1/0/1` 入方向和出方向流量均为 0。
3. Syslog 记录 `GE1/0/1 changed state to DOWN`。

建议：

1. 检查物理连接、光模块和线缆。
2. 检查对端接口状态。
3. 接口恢复后重新验证链路和业务连通性。

## 9. 一致性测试设计

测试模式：

| 模式 | 说明 |
|---|---|
| `single_session` | 同一个 session 连续多次提问 |
| `multi_session` | 多个不同 session 分别提问 |

默认问题：

```text
帮我分析当前故障
leaf-01 为什么业务不通
是不是 BGP 的问题
重新诊断一下 leaf-01
```

比较字段：

1. `fault_fingerprint`
2. `fault_type`
3. `root_cause`
4. `affected_devices`
5. `affected_services`
6. `evidence`
7. `diagnosis_chain`
8. `recommendation`
9. `need_more_data`

通过标准：

```text
所有轮次的比较字段与 baseline 完全一致。
```

当前结果：

```text
single_session: 1.0
multi_session: 1.0
overall_consistency_score: 1.0
passed: true
```

## 10. 接口清单

| 接口 | 方法 | 作用 |
|---|---|---|
| `/api/health` | GET | 健康检查 |
| `/api/devices` | GET | 设备列表 |
| `/api/topology` | GET | 拓扑数据 |
| `/api/topology/discovery-capabilities` | GET | 拓扑发现能力和真实协议边界 |
| `/api/topology/discover` | POST | 触发采集器发现或提交运行时拓扑 |
| `/api/mibs/profiles` | GET | 查询 MIB provider profiles |
| `/api/mibs/compile` | POST | 编译内置或上传 MIB 并生成 OID Tree |
| `/api/mibs/status` | GET | 查询 profile 最近一次 MIB 编译状态 |
| `/api/mibs/tree` | GET | 查询完整或局部 MIB Tree |
| `/api/mibs/translate` | POST | OID 翻译到 MIB 对象 |
| `/api/fault-cases` | GET | 当前可诊断故障观测列表 |
| `/api/fault-cases/{id}` | GET | 当前故障观测详情 |
| `/api/facts` | GET | 标准化事实 |
| `/api/llm/config` | GET/POST | 查询或配置大模型 API，不回显 API Key |
| `/api/agent/chat` | POST | Agent 会话式诊断入口 |
| `/api/agent/sessions/{session_id}` | GET | 查询 Agent 会话历史 |
| `/api/diagnosis/analyze` | POST | 发起诊断 |
| `/api/consistency/test` | POST | 一致性测试 |

## 11. 前端实现

当前前端实现为轻量 Vue 3 应用壳，按功能拆分为诊断、MIB、设置三个页面；拓扑画布集成在诊断页，便于边问诊边观察设备和链路关系。

页面能力：

1. 诊断页提供会话式 Agent 消息流、快捷追问和新会话。
2. 诊断页展示根因、故障类型、故障指纹、置信度、缓存命中、标准化事实和工具轨迹。
3. 诊断页展示单会话、多会话一致性测试结果。
4. 诊断页展示后端发现到的节点数、链路数、拓扑节点和链路画布。
5. MIB 页提供 profile 选择、MIB 上传、OID Tree 和 OID 翻译。
6. 设置页提供大模型 API 配置入口和系统状态。

前端分层：

```text
frontend/src/
├── api/              后端 API 调用
├── components/       业务组件和应用导航
├── components/ui/    通用 UI 组件
├── composables/      页面状态和动作编排
├── views/            按功能拆分的页面
├── App.vue           应用壳和 view 切换
└── style.css         全局基础样式
```

说明：

第一阶段前端已经不再固定拓扑。当前用轻量 `TopologyPanel` 渲染 API 返回的 `nodes/edges`。第三阶段进入 Spine-Leaf 多设备联动时，可把该组件内部渲染替换为 AntV G6，API 和状态层不需要变化。

## 12. 验证记录

已完成验证：

1. `python3 -m unittest discover tests` 通过。
2. `.venv/bin/python -m unittest discover tests` 通过。
3. `npm run build` 通过。
4. `/api/health` 返回 `status=ok`。
5. 未配置 LLM 时，诊断接口返回 503，不生成本地假诊断。
6. 配置真实 LLM 后，`/api/agent/chat` 返回会话消息、诊断结果和工具轨迹。
7. 配置真实 LLM 后，`/api/consistency/test` 返回一致性评分。
8. `/api/topology/discover` 返回动态发现摘要，包含设备数和链路数。
9. `SnmpLldpTopologyProvider` 通过 fake SNMP walk 单测验证 3 节点 2 链路解析，以及 CIDR 扫描发现 4 节点 2 链路。
10. 实际 lab 中 `mode=snmp_lldp` 通过 SNMP 管理网段扫描返回 4 节点 2 链路 2 组网。
11. 故障注入 `leaf-01 eth1 down` 后，SNMP IF-MIB 返回接口 down，对应 edge 返回 `status=down`。
12. `pysmi` MIB 编译器通过单测验证内置 SNMP/IF/LLDP MIB 无 failed/unresolved，并能翻译 `ifName`、`lldpRemSysName` 实例 OID。
13. `./scripts/test_phase1.sh` 通过，包含 17 个后端测试和前端生产构建。

## 13. 当前局限

当前不是完整赛题最终形态，只是第一阶段：

1. 没有接真实网络设备。
2. 没有数据库和 Redis。
3. 已提供 FRR SNMP/LLDP 三设备互联加一台孤立设备的实验拓扑，但尚未作为赛题第三阶段完整诊断用例接入。
4. 没有多异常派生链，如 BGP Down、路由缺失、FIB 缺失。
5. 前端拓扑已改为动态数据渲染，但尚未接入 AntV G6 图布局。
6. 大模型必须通过环境变量或页面运行时配置接入真实接口，本仓库不提供本地模拟诊断。
7. 已具备 MIB 编译和 OID 翻译能力，但 Trap receiver、Trap 关联诊断和厂商 MIB 包版本治理仍属于后续采集器能力。

这些不是遗漏，而是第一阶段范围控制。后续阶段应继续补齐。

## 14. 下一步建议

第二阶段：

1. 增加单设备多异常样本。
2. 增加 `BGP_NEIGHBOR_DOWN`、`ROUTE_MISSING`、`FIB_ENTRY_MISSING`。
3. 实现根因和派生异常排序。
4. 将进程内缓存替换为 Redis。
5. 增加 RAG 知识库。

第三阶段：

1. 基于 FRR SNMP/LLDP lab 或真实设备采集生成三设备以上联动故障观测。
2. 引入 NetworkX 拓扑关联。
3. 接入 AntV G6 前端拓扑。
4. 支持从不同设备视角提问仍输出同一根因。
5. 支持三设备以上 Spine-Leaf 一致性测试。
