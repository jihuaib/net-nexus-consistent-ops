# AI 大模型在运维场景的诊断一致性实现方案

## 1. 赛题信息与理解

| 项目 | 内容 |
|---|---|
| 赛题编号 | 6.4.3 |
| 赛题名称 | AI 大模型在运维场景的诊断一致性 |
| 难度 | A |
| 出题 PDT | 驱动软件平台 |
| 核心方向 | 网络设备运维、AI Agent、诊断一致性、多设备联动分析 |
| 业务价值 | 提升设备运维效率，降低人工排障成本，提高诊断稳定性和可信度 |

本赛题关注的重点不是“让大模型随意回答网络问题”，而是解决大模型在运维场景中的一个关键痛点：

```text
同一个网络故障环境下，
用户单次提问、多轮提问、多会话提问，
Agent 都应该给出稳定、一致、可解释、可复现的诊断结论。
```

网络运维场景对准确性和稳定性要求较高。传统大模型存在表达随机、结论波动、证据链不稳定等问题，即使用户输入相同或相近，输出也可能不一致，无法直接满足运维诊断场景的要求。

因此，本方案的核心思想是：

```text
用确定性的工程系统包裹大模型，
让大模型负责理解、解释和总结，
让系统负责事实提取、规则约束、拓扑分析、结果缓存、格式校验和一致性兜底。
```

## 2. 图片赛题要求拆解

### 2.1 背景拆解

图片中背景信息可拆解为以下要点：

1. 网络设备专业性强，业务复杂，组合多样。
2. 客户现场问题和测试环境问题通常需要大量人力投入分析和定位。
3. 经验依赖强，排障过程耗时，对研发和运维团队造成较大负担。
4. 传统运维软件已经可以通过 MIB、NETCONF、gRPC 等通道采集设备数据，并在后台分析。
5. 新场景下，运维能力需要同步适配设备版本、软件版本和功能升级。
6. 2025 年以来，AI 大模型能力在运维场景中逐步应用。
7. 大模型可以分析设备运行状态、转发表、Telemetry 等数据，帮助提升设备可维护性。
8. 但大模型存在一致性问题：相同或相似输入下，输出结果不一定稳定，无法满足运维场景中的确定性要求。

### 2.2 设计要求拆解

| 题目要求 | 本方案对应实现 |
|---|---|
| 设计一套基于 Agent 运行的运维一致性兜底策略 | 设计 Consistency Agent，由故障指纹、规则引擎、拓扑分析、诊断缓存、Schema 校验、一致性评分组成 |
| 设备侧现有能力能够保持少变动或不变动 | 不在设备侧安装新 Agent，不要求升级设备版本，复用 MIB、NETCONF、gRPC、Telemetry、Syslog、只读 CLI |
| 具备多台设备互联场景的联动分析能力 | 基于拓扑图和事件图，支持 Spine-Leaf 多设备关联诊断 |

### 2.3 完成度判据拆解

| 完成度 | 题目判据 | 本方案实现方式 |
|---|---|---|
| 60% | 单一设备确定网络故障环境中，Agent 单会话多次交互以及多会话交互时，输出内容保持一致 | 单设备单故障场景，基于故障指纹和诊断缓存稳定输出 |
| 80% | 单一设备异常常发现网络故障环境中，Agent 单会话多次交互以及多会话交互时，输出内容保持一致 | 单设备多异常场景，识别主因和派生异常，固定诊断链 |
| 100% | 不少于 3 台设备互联的 Spine-Leaf 典型三层组网故障中，Agent 单会话多次交互以及多会话交互时，输出内容保持一致 | 构建三台及以上设备拓扑图，进行多设备联动分析和一致性输出 |

## 3. 建设目标

系统名称建议：

```text
NetNexus ConsistentOps
面向网络运维场景的 AI Agent 诊断一致性系统
```

建设目标：

1. 对同一网络故障生成稳定的故障指纹。
2. 对同一故障在单会话、多轮会话、多会话下输出一致诊断结果。
3. 支持单设备单一故障、单设备多异常、多设备 Spine-Leaf 联动故障。
4. 在不大幅改造设备侧能力的前提下完成数据采集和诊断分析。
5. 将大模型输出约束为结构化 JSON，便于系统校验、缓存、复用和展示。
6. 通过一致性评分量化 Agent 结果稳定性。
7. 通过前端可视化展示事实证据、诊断链路、拓扑影响和一致性验证结果。

## 4. 总体技术路线

本方案推荐采用全 Python 后端实现，前端采用 Vue 3。

推荐原因：

1. Python 更适合 AI 编排、Prompt 管理、RAG 检索和网络自动化。
2. FastAPI 可以快速构建接口服务，适合比赛项目快速落地。
3. Python 生态中有成熟的 SNMP、NETCONF、gRPC、Telemetry、SSH、图分析和向量检索库。
4. Vue 3 + AntV G6 适合做拓扑可视化和诊断流程展示。
5. 本题重点在诊断一致性，不是大型企业后台，Python 单体模块化架构足够支撑。

### 4.1 推荐技术栈

| 层级 | 技术选型 | 作用 |
|---|---|---|
| 前端 | Vue 3 + TypeScript | 构建运维诊断控制台 |
| UI 组件 | Element Plus | 表格、表单、弹窗、步骤条 |
| 拓扑可视化 | AntV G6 | 展示 Spine-Leaf 拓扑和故障路径 |
| 图表 | ECharts | 展示一致性评分、指标趋势 |
| 后端框架 | Python + FastAPI | 提供 API、Agent 编排入口 |
| Agent 编排 | LangGraph 或自研状态机 | 固定诊断流程，避免自由跳转 |
| 大模型接入 | DeepSeek、通义千问、智谱、OpenAI API、私有化 Qwen/DeepSeek | 负责诊断解释和自然语言总结 |
| 规则引擎 | Python 自研规则表 / durable_rules 可选 | 处理确定性故障 |
| 拓扑分析 | NetworkX | 多设备拓扑关联、影响路径分析 |
| 向量检索 | FAISS / Chroma | 检索历史案例和运维知识 |
| 关系数据库 | MySQL / PostgreSQL | 存储设备、拓扑、故障、诊断结果 |
| 缓存 | Redis | 存储诊断缓存、会话状态和故障指纹 |
| 消息队列 | Redis Stream / Celery | 异步采集、诊断任务、批量测试 |
| SNMP | pysnmp | 通过 MIB 获取设备状态 |
| NETCONF | ncclient | 获取结构化配置和运行状态 |
| gRPC/Telemetry | grpcio | 获取实时运行指标 |
| SSH/CLI | Paramiko / Netmiko | 获取只读诊断命令输出 |
| 部署 | Docker Compose | 快速部署前后端、Redis、数据库 |

### 4.2 比赛版最小落地组合

```text
后端：Python + FastAPI
前端：Vue 3 + Element Plus + AntV G6 + ECharts
数据库：PostgreSQL 或 MySQL
缓存：Redis
模型：DeepSeek / 通义千问 / 智谱 API
拓扑分析：NetworkX
向量检索：FAISS 或 Chroma
设备采集：模拟数据 + SNMP/CLI 可选接入
部署：Docker Compose
```

## 5. 总体架构

```text
                         +------------------------------+
                         |          Vue 3 前端           |
                         | 拓扑 / 诊断 / 一致性 / 报告   |
                         +---------------+--------------+
                                         |
                                         v
                         +------------------------------+
                         |        FastAPI API 网关       |
                         | 鉴权 / 会话 / 任务 / 查询接口 |
                         +---------------+--------------+
                                         |
           +-----------------------------+-----------------------------+
           |                             |                             |
           v                             v                             v
+--------------------+       +--------------------+       +--------------------+
|    数据采集层       |       |   Consistency Agent |       |    数据存储层       |
| MIB/NETCONF/gRPC    |       | 一致性诊断编排       |       | DB/Redis/VectorDB   |
| Telemetry/Syslog/CLI|       +----------+---------+       +----------+---------+
+----------+---------+                  |                            |
           |                            v                            |
           |                 +--------------------+                  |
           |                 |   诊断能力组件      |                  |
           |                 | 规则/拓扑/RAG/LLM   |                  |
           |                 +----------+---------+                  |
           |                            |                            |
           +----------------------------+----------------------------+
                                        |
                                        v
                         +------------------------------+
                         |       一致性校验与输出        |
                         | JSON Schema / Score / Cache   |
                         +------------------------------+
```

## 6. 核心设计思想

### 6.1 大模型不直接做最终裁决

大模型在系统中的角色是“解释器”和“推理助手”，不是唯一裁决者。

| 能力 | 是否由大模型负责 | 说明 |
|---|---|---|
| 设备数据采集 | 否 | 使用 MIB、NETCONF、gRPC、Telemetry、CLI |
| 事实标准化 | 否 | 系统解析为结构化 Fact |
| 故障指纹生成 | 否 | 采用确定性算法 |
| 确定性故障判断 | 否 | 规则引擎优先判断 |
| 拓扑路径分析 | 否 | NetworkX 图算法完成 |
| 历史案例检索 | 部分 | 向量检索负责召回，模型负责理解 |
| 根因解释 | 是 | 大模型生成可读解释 |
| 输出格式化 | 部分 | 模型输出 JSON，系统再次校验归一 |
| 一致性判定 | 否 | 系统计算一致性评分 |

### 6.2 一致性兜底闭环

```text
用户问题
  -> 意图识别
  -> 读取故障上下文
  -> 结构化事实抽取
  -> 故障指纹生成
  -> 查询诊断缓存
  -> 命中缓存：直接返回标准诊断
  -> 未命中缓存：规则诊断 + 拓扑分析 + RAG + LLM
  -> JSON Schema 校验
  -> 结果归一化
  -> 写入诊断缓存
  -> 一致性评分
  -> 前端展示
```

### 6.3 保障一致性的关键机制

| 机制 | 作用 |
|---|---|
| 事实标准化 Fact Model | 将日志、表项、指标统一成结构化事实 |
| 故障指纹 Fault Fingerprint | 判断多次输入是否属于同一故障 |
| 诊断缓存 Diagnosis Cache | 同一故障返回同一标准结果 |
| 固定 Agent 工作流 | 避免模型自由选择诊断路径 |
| 低随机模型参数 | temperature 设置为 0 或接近 0 |
| Prompt 模板版本化 | 同一版本模板保证一致上下文 |
| JSON Schema 校验 | 保证输出字段、类型和枚举稳定 |
| 术语归一化 | 将“邻居断开”“Peer Down”等统一为 BGP_NEIGHBOR_DOWN |
| 规则引擎优先 | 明确故障不让模型随机判断 |
| 一致性评分 | 对单会话、多会话结果进行量化比较 |

## 7. Agent 架构设计

### 7.1 Agent 组件

| Agent/组件 | 职责 |
|---|---|
| Coordinator Agent | 总控调度，维护诊断状态机 |
| Collector Agent | 获取设备运行数据、日志、表项和指标 |
| Fact Agent | 将原始数据标准化为事实对象 |
| Fingerprint Agent | 生成故障指纹 |
| Rule Agent | 基于规则库进行确定性诊断 |
| Topology Agent | 进行拓扑关联和影响路径分析 |
| RAG Agent | 检索历史案例、手册、命令解释和故障知识 |
| LLM Reasoner Agent | 调用大模型完成根因解释和建议 |
| Consistency Guard | 输出归一化、Schema 校验、缓存命中、一致性评分 |
| Report Agent | 生成诊断报告和展示摘要 |

### 7.2 Agent 状态机

```text
START
  -> LOAD_CONTEXT
  -> COLLECT_FACTS
  -> NORMALIZE_FACTS
  -> BUILD_FINGERPRINT
  -> CHECK_CACHE
       |-- HIT  -> RETURN_CACHED_DIAGNOSIS
       |-- MISS -> RULE_DIAGNOSIS
  -> TOPOLOGY_ANALYSIS
  -> RAG_RETRIEVAL
  -> LLM_REASONING
  -> NORMALIZE_OUTPUT
  -> SCHEMA_VALIDATE
  -> CONSISTENCY_SCORE
  -> SAVE_CACHE
  -> REPORT
END
```

### 7.3 为什么使用状态机

直接使用大模型多轮对话，输出路径不可控。状态机可以让每次诊断都经过相同步骤，从而保证：

1. 输入事实一致。
2. 分析路径一致。
3. 输出字段一致。
4. 缓存策略一致。
5. 多会话结果一致。

## 8. 数据采集设计

### 8.1 设备侧少变动原则

题目要求设备侧能力少变动或不变动，因此系统遵循：

1. 不要求在设备侧安装新 Agent。
2. 不要求升级设备系统版本。
3. 不修改设备转发逻辑。
4. 不依赖设备新增私有接口。
5. 优先复用现有标准运维接口。

### 8.2 采集通道

| 通道 | 数据类型 | 用途 |
|---|---|---|
| MIB/SNMP | 接口状态、CPU、内存、基础告警 | 单设备状态判断 |
| NETCONF | 配置、接口、路由协议状态 | 结构化状态采集 |
| gRPC/Telemetry | 流量、丢包、队列、转发表状态 | 实时指标分析 |
| Syslog | Link Down、协议震荡、配置变更 | 事件触发 |
| CLI 只读命令 | display interface、display bgp peer、display ip routing-table | 兼容无结构化接口场景 |
| 模拟数据 | JSON/YAML 故障样本 | 比赛演示兜底 |

### 8.3 采集数据示例

```json
{
  "device_id": "leaf-01",
  "timestamp": "2026-06-25T10:21:33+08:00",
  "interfaces": [
    {
      "name": "GE1/0/1",
      "admin_status": "up",
      "oper_status": "down",
      "in_bps": 0,
      "out_bps": 0,
      "crc_errors": 0
    }
  ],
  "bgp_neighbors": [
    {
      "peer": "10.0.0.1",
      "state": "idle",
      "remote_device": "spine-01"
    }
  ],
  "routes": [
    {
      "prefix": "10.10.10.0/24",
      "status": "missing"
    }
  ],
  "syslogs": [
    "%LINK-3-UPDOWN: Interface GE1/0/1 changed state to DOWN"
  ]
}
```

## 9. 事实模型设计

### 9.1 Fact 标准格式

所有原始数据会被转换为统一事实对象：

```json
{
  "fact_id": "fact-001",
  "device_id": "leaf-01",
  "scope": "interface",
  "object": "GE1/0/1",
  "fact_type": "INTERFACE_OPER_DOWN",
  "value": "down",
  "severity": "critical",
  "timestamp": "2026-06-25T10:21:33+08:00",
  "source": "syslog",
  "confidence": 1.0
}
```

### 9.2 常用事实类型

| fact_type | 含义 |
|---|---|
| INTERFACE_OPER_DOWN | 接口运行状态 Down |
| INTERFACE_ADMIN_DOWN | 接口管理状态 Down |
| BGP_NEIGHBOR_DOWN | BGP 邻居 Down |
| OSPF_NEIGHBOR_DOWN | OSPF 邻居 Down |
| ROUTE_MISSING | 路由缺失 |
| FIB_ENTRY_MISSING | 转发表缺失 |
| TELEMETRY_TRAFFIC_ZERO | 接口流量为 0 |
| PACKET_LOSS_HIGH | 丢包率过高 |
| CPU_HIGH | CPU 使用率过高 |
| CONFIG_CHANGED | 设备配置发生变更 |
| SERVICE_UNREACHABLE | 业务不可达 |

## 10. 故障指纹设计

故障指纹是保证一致性的核心。

### 10.1 指纹目标

同一个故障环境下，即使用户问题不同，也应该得到同一个指纹。

示例：

```text
用户问题 1：leaf-01 为什么业务不通？
用户问题 2：重新分析一下 leaf-01 当前问题。
用户问题 3：BGP 邻居为什么 down？
用户问题 4：新开会话后问：帮我诊断 leaf-01。

如果底层事实相同，则生成同一个 fault_fingerprint。
```

### 10.2 指纹生成字段

```text
fault_fingerprint = hash(
  topology_id +
  device_role +
  primary_device_id +
  primary_object_type +
  primary_object_id +
  normalized_fault_type +
  related_peer_device +
  affected_protocol +
  affected_prefixes +
  time_window_bucket +
  key_fact_set
)
```

### 10.3 指纹示例

```json
{
  "fingerprint": "fp_8a71c9e2",
  "primary_device": "leaf-01",
  "primary_object": "GE1/0/1",
  "fault_type": "INTERFACE_DOWN_CAUSES_BGP_DOWN",
  "related_devices": ["spine-01"],
  "affected_protocols": ["BGP"],
  "affected_services": ["10.10.10.0/24"]
}
```

### 10.4 指纹算法伪代码

```python
def build_fault_fingerprint(facts, topology):
    normalized_facts = normalize_fact_order(facts)
    primary_fault = select_primary_fault(normalized_facts, topology)
    related_devices = find_related_devices(primary_fault, topology)
    affected_protocols = extract_affected_protocols(normalized_facts)
    affected_prefixes = extract_affected_prefixes(normalized_facts)

    payload = {
        "topology_id": topology.id,
        "primary_device": primary_fault.device_id,
        "primary_object": primary_fault.object,
        "fault_type": primary_fault.normalized_type,
        "related_devices": sorted(related_devices),
        "affected_protocols": sorted(affected_protocols),
        "affected_prefixes": sorted(affected_prefixes),
        "key_facts": sorted([f.fact_type for f in normalized_facts])
    }

    return sha256(canonical_json(payload)).hexdigest()[:16]
```

## 11. 诊断一致性策略

### 11.1 缓存一致性

当故障指纹命中缓存时，不再调用大模型，直接返回标准诊断结果。

缓存键：

```text
diagnosis:{model_version}:{prompt_version}:{topology_version}:{fault_fingerprint}
```

缓存值：

```json
{
  "fault_fingerprint": "fp_8a71c9e2",
  "diagnosis_version": "v1",
  "root_cause": "leaf-01 GE1/0/1 接口 Down 导致与 spine-01 的 BGP 邻居中断",
  "fault_type": "INTERFACE_DOWN_CAUSES_BGP_DOWN",
  "evidence": [
    "leaf-01 GE1/0/1 oper_status 为 down",
    "spine-01 对端接口状态异常",
    "leaf-01 到 spine-01 的 BGP 邻居状态为 idle"
  ],
  "recommendation": [
    "检查 leaf-01 GE1/0/1 光模块和线缆",
    "恢复接口后检查 BGP 邻居状态",
    "验证 10.10.10.0/24 路由是否恢复"
  ]
}
```

### 11.2 输出归一化

大模型可能输出不同表达，例如：

```text
BGP peer down
BGP 邻居断开
BGP 会话中断
对等体不可达
```

系统统一归一化为：

```text
BGP_NEIGHBOR_DOWN
```

常用归一化枚举：

| 原始表达 | 归一化结果 |
|---|---|
| 接口 down、链路断开、link down | INTERFACE_DOWN |
| BGP peer down、邻居中断 | BGP_NEIGHBOR_DOWN |
| 路由消失、前缀缺失 | ROUTE_MISSING |
| 转发表无条目 | FIB_ENTRY_MISSING |
| 流量为 0、无入方向流量 | TRAFFIC_ZERO |

### 11.3 Schema 校验

大模型输出必须符合 JSON Schema。

核心字段：

```json
{
  "fault_fingerprint": "string",
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
```

校验规则：

1. fault_type 必须来自系统枚举。
2. affected_devices 必须存在于拓扑表。
3. evidence 必须能回溯到 Fact。
4. confidence 必须在 0 到 1 之间。
5. recommendation 不允许包含危险配置命令。
6. 缺少必填字段时，不直接返回，进入修复或降级流程。

### 11.4 一致性评分

系统对多次诊断结果计算一致性分数。

评分维度：

| 维度 | 权重 | 说明 |
|---|---|---|
| fault_type 一致 | 25% | 故障类型是否一致 |
| root_cause 一致 | 25% | 根因结论是否一致 |
| affected_devices 一致 | 15% | 影响设备是否一致 |
| evidence 一致 | 15% | 证据链是否一致 |
| recommendation 一致 | 10% | 建议动作是否一致 |
| confidence 波动 | 10% | 置信度是否稳定 |

计算示例：

```text
consistency_score =
  0.25 * fault_type_match +
  0.25 * root_cause_match +
  0.15 * affected_devices_match +
  0.15 * evidence_match +
  0.10 * recommendation_match +
  0.10 * confidence_stability
```

输出展示：

```json
{
  "single_session_score": 1.0,
  "multi_session_score": 1.0,
  "overall_consistency_score": 1.0,
  "runs": 10,
  "consistent_runs": 10
}
```

## 12. 规则诊断引擎

### 12.1 规则优先级

确定性规则优先于大模型。

```text
物理接口 Down
  > 管理状态 shutdown
  > 协议邻居 Down
  > 路由缺失
  > 转发表缺失
  > 业务不可达
```

原因：

```text
接口 Down 很可能导致协议 Down；
协议 Down 会导致路由缺失；
路由缺失会导致业务不可达。
```

### 12.2 规则示例

```yaml
rule_id: R001
name: interface_down_causes_bgp_down
conditions:
  - fact_type: INTERFACE_OPER_DOWN
  - fact_type: BGP_NEIGHBOR_DOWN
  - relation: interface_connects_to_bgp_peer
result:
  fault_type: INTERFACE_DOWN_CAUSES_BGP_DOWN
  root_cause_template: "{device} {interface} 接口 Down 导致与 {peer_device} 的 BGP 邻居中断"
  confidence: 0.95
```

```yaml
rule_id: R002
name: admin_shutdown
conditions:
  - fact_type: INTERFACE_ADMIN_DOWN
  - fact_type: INTERFACE_OPER_DOWN
result:
  fault_type: INTERFACE_ADMIN_SHUTDOWN
  root_cause_template: "{device} {interface} 被管理 shutdown，导致链路不可用"
  confidence: 0.98
```

```yaml
rule_id: R003
name: route_missing_causes_service_unreachable
conditions:
  - fact_type: ROUTE_MISSING
  - fact_type: SERVICE_UNREACHABLE
result:
  fault_type: ROUTE_MISSING_SERVICE_UNREACHABLE
  root_cause_template: "{device} 缺失到 {prefix} 的路由，导致业务不可达"
  confidence: 0.90
```

## 13. 拓扑联动分析

### 13.1 拓扑数据模型

```text
Device
  -> Interface
  -> Link
  -> Peer Interface
  -> Peer Device
  -> Routing Neighbor
  -> Route Prefix
  -> Service
```

### 13.2 Spine-Leaf 拓扑示例

```text
              spine-01
             /        \
        leaf-01      leaf-02
          |             |
      server-01     server-02
```

或扩展为：

```text
             spine-01       spine-02
             /     \       /     \
        leaf-01   leaf-02 leaf-03 leaf-04
```

### 13.3 联动分析逻辑

当 leaf-01 到 spine-01 的链路异常：

```text
leaf-01 GE1/0/1 Down
  -> spine-01 GE1/0/10 对端链路异常
  -> leaf-01 与 spine-01 的 BGP/OSPF 邻居 Down
  -> leaf-01 发布的业务路由被撤销
  -> leaf-02 到 server-01 所在网段不可达
```

系统应输出：

```text
根因：leaf-01 与 spine-01 之间的上联链路异常。
派生影响：BGP 邻居中断、路由缺失、跨 Leaf 业务访问失败。
非根因：leaf-02 和 server-02 不是故障源。
```

## 14. 大模型接入方案

### 14.1 模型选择

支持以下两种方式：

| 方式 | 说明 |
|---|---|
| 公有云大模型 API | DeepSeek、通义千问、智谱、OpenAI 等，适合比赛快速实现 |
| 私有化大模型 | Qwen、DeepSeek、Llama、ChatGLM 等，适合企业内网部署 |

比赛阶段建议优先使用公有云 API，系统预留模型适配层，后续可替换为私有化模型。

### 14.2 模型调用参数

为保证一致性，建议参数：

```json
{
  "temperature": 0,
  "top_p": 0.1,
  "presence_penalty": 0,
  "frequency_penalty": 0,
  "response_format": "json_object"
}
```

### 14.3 Prompt 模板

```text
你是一名网络设备运维诊断专家。请根据系统提供的结构化事实、拓扑关系、规则诊断结果和知识库片段进行诊断。

必须遵守：
1. 只能基于输入事实分析，不允许编造不存在的设备、接口、路由或告警。
2. 输出必须是 JSON，不要输出 Markdown。
3. fault_type 必须从候选枚举中选择。
4. evidence 必须引用输入事实。
5. 如果规则诊断已经给出高置信度结论，不得推翻规则结论，只能补充解释。
6. 如果证据不足，需要将 need_more_data 设置为 true。
7. 同一 fault_fingerprint 下应保持 root_cause、fault_type、evidence、recommendation 一致。
```

### 14.4 输入上下文模板

```json
{
  "fault_fingerprint": "fp_8a71c9e2",
  "prompt_version": "ops-consistency-v1",
  "topology": {
    "devices": ["leaf-01", "spine-01", "leaf-02"],
    "links": [
      {"a": "leaf-01:GE1/0/1", "b": "spine-01:GE1/0/10"},
      {"a": "leaf-02:GE1/0/1", "b": "spine-01:GE1/0/11"}
    ]
  },
  "facts": [
    {
      "device_id": "leaf-01",
      "object": "GE1/0/1",
      "fact_type": "INTERFACE_OPER_DOWN",
      "source": "syslog"
    },
    {
      "device_id": "leaf-01",
      "object": "10.0.0.1",
      "fact_type": "BGP_NEIGHBOR_DOWN",
      "source": "netconf"
    }
  ],
  "rule_result": {
    "fault_type": "INTERFACE_DOWN_CAUSES_BGP_DOWN",
    "confidence": 0.95
  },
  "knowledge_snippets": [
    "当接口 Down 与 BGP 邻居 Down 同时发生，并且邻居依赖该接口连接时，接口 Down 通常是根因。"
  ]
}
```

### 14.5 输出示例

```json
{
  "fault_fingerprint": "fp_8a71c9e2",
  "fault_type": "INTERFACE_DOWN_CAUSES_BGP_DOWN",
  "root_cause": "leaf-01 的 GE1/0/1 接口 Down，导致 leaf-01 与 spine-01 的 BGP 邻居中断",
  "affected_devices": ["leaf-01", "spine-01"],
  "affected_services": ["10.10.10.0/24"],
  "evidence": [
    "leaf-01 GE1/0/1 存在 INTERFACE_OPER_DOWN 事实",
    "leaf-01 到 spine-01 的 BGP 邻居存在 BGP_NEIGHBOR_DOWN 事实",
    "拓扑显示该 BGP 邻居依赖 leaf-01 GE1/0/1 到 spine-01 的链路"
  ],
  "diagnosis_chain": [
    "leaf-01 GE1/0/1 接口 Down",
    "leaf-01 与 spine-01 的 BGP 邻居中断",
    "相关业务路由撤销",
    "跨 Leaf 业务访问异常"
  ],
  "confidence": 0.95,
  "recommendation": [
    "检查 leaf-01 GE1/0/1 物理链路、光模块和线缆",
    "恢复接口后检查 BGP 邻居状态",
    "验证相关业务前缀是否重新出现在路由表和转发表"
  ],
  "need_more_data": false
}
```

## 15. RAG 知识库设计

知识库用于增强大模型对网络运维场景的理解，但不直接决定最终结论。

### 15.1 知识内容

| 类型 | 示例 |
|---|---|
| 故障手册 | 接口 Down 排查手册、BGP 邻居 Down 排查手册 |
| 设备命令解释 | display interface、display bgp peer、display ip routing-table |
| 协议知识 | BGP/OSPF 邻居状态机、路由收敛机制 |
| 典型案例 | 链路 Down 导致 BGP Down、ACL 拦截导致业务不可达 |
| 版本差异 | 不同设备版本字段名和命令输出差异 |
| 术语词典 | Peer、Neighbor、邻居、对等体统一映射 |

### 15.2 检索流程

```text
故障摘要 + 事实类型 + 拓扑角色
  -> 向量检索相似案例
  -> 关键词检索精确手册
  -> 合并去重
  -> 注入大模型上下文
```

### 15.3 亮点：版本感知知识检索

题目背景提到“设备版本、软件版本升级支持”。本方案在知识库中记录设备型号和版本，检索时优先召回匹配版本的知识。

示例：

```json
{
  "device_vendor": "H3C",
  "device_model": "S6850",
  "software_version": "Release 6628",
  "knowledge_scope": "bgp_peer_status"
}
```

## 16. 数据库设计

### 16.1 主要表

| 表名 | 说明 |
|---|---|
| device | 设备信息 |
| device_version | 设备型号和软件版本 |
| interface | 接口信息 |
| topology_link | 拓扑链路 |
| routing_neighbor | 路由协议邻居 |
| service_mapping | 业务、网段和设备映射 |
| raw_observation | 原始采集数据 |
| fact | 标准化事实 |
| fault_case | 故障样本 |
| diagnosis_run | 每次诊断运行记录 |
| diagnosis_result | 标准诊断结果 |
| diagnosis_cache | 故障指纹到诊断结果的缓存 |
| consistency_test | 一致性测试任务 |
| consistency_run_result | 多轮测试结果 |
| knowledge_doc | 知识库文档 |
| prompt_template | Prompt 模板版本 |

### 16.2 diagnosis_result 关键字段

| 字段 | 类型 | 说明 |
|---|---|---|
| id | varchar | 诊断结果 ID |
| fault_fingerprint | varchar | 故障指纹 |
| fault_type | varchar | 归一化故障类型 |
| root_cause | text | 根因结论 |
| affected_devices | json | 影响设备 |
| affected_services | json | 影响业务 |
| evidence | json | 证据列表 |
| diagnosis_chain | json | 诊断链 |
| confidence | decimal | 置信度 |
| recommendation | json | 建议 |
| prompt_version | varchar | Prompt 版本 |
| model_name | varchar | 模型名称 |
| model_version | varchar | 模型版本 |
| created_at | datetime | 创建时间 |

### 16.3 consistency_test 关键字段

| 字段 | 说明 |
|---|---|
| id | 测试任务 ID |
| fault_case_id | 故障样本 ID |
| session_mode | single_session 或 multi_session |
| run_count | 运行次数 |
| expected_fingerprint | 期望故障指纹 |
| consistency_score | 一致性评分 |
| passed | 是否通过 |

## 17. API 设计

| 接口 | 方法 | 说明 |
|---|---|---|
| /api/devices | GET | 查询设备 |
| /api/topology | GET | 查询拓扑 |
| /api/facts | GET | 查询标准化事实 |
| /api/diagnosis/analyze | POST | 发起诊断 |
| /api/diagnosis/{id} | GET | 查询诊断结果 |
| /api/diagnosis/{id}/evidence | GET | 查询证据链 |
| /api/consistency/test | POST | 发起一致性测试 |
| /api/consistency/{id} | GET | 查询一致性测试结果 |
| /api/fault-cases | GET | 查询故障样本 |
| /api/fault-cases/{id}/replay | POST | 回放故障样本 |
| /api/knowledge/search | POST | 查询知识库 |
| /api/reports/{id} | GET | 查询诊断报告 |

### 17.1 诊断请求示例

```json
{
  "question": "帮我分析 leaf-01 当前为什么业务不通",
  "scope": {
    "topology_id": "spine-leaf-demo",
    "devices": ["leaf-01"]
  },
  "mode": "diagnosis",
  "session_id": "session-001"
}
```

### 17.2 一致性测试请求示例

```json
{
  "fault_case_id": "case-spine-leaf-link-down",
  "session_modes": ["single_session", "multi_session"],
  "questions": [
    "帮我分析当前故障",
    "为什么 leaf-01 业务不通",
    "重新诊断一下 BGP 邻居异常",
    "这是不是 leaf-02 的问题"
  ],
  "run_count": 10
}
```

## 18. 前端页面设计

### 18.1 页面列表

| 页面 | 功能 |
|---|---|
| 总览 Dashboard | 展示诊断次数、通过率、一致性评分、故障类型分布 |
| 拓扑视图 | 展示 Spine-Leaf 拓扑、故障链路、影响路径 |
| 故障样本 | 管理单设备和多设备故障样本 |
| Agent 诊断 | 用户输入问题，查看 Agent 稳定诊断结果 |
| 证据链视图 | 展示 Fact、规则命中、拓扑路径、RAG 片段 |
| 一致性测试 | 批量执行单会话、多会话一致性测试 |
| 诊断报告 | 输出根因、证据、影响范围、评分、建议 |
| 知识库管理 | 管理故障手册、案例、命令解释 |

### 18.2 拓扑视图亮点

1. 故障设备高亮。
2. 故障链路红色高亮。
3. 派生影响路径橙色高亮。
4. 非根因设备灰色展示。
5. 点击设备可查看事实列表。
6. 点击链路可查看接口状态、邻居状态和流量指标。

### 18.3 一致性测试视图亮点

展示表格：

| 轮次 | 会话类型 | 用户问题 | fault_type | root_cause | score | 是否一致 |
|---|---|---|---|---|---|---|
| 1 | 单会话 | 为什么业务不通 | INTERFACE_DOWN_CAUSES_BGP_DOWN | leaf-01 上联接口 Down | 1.0 | 是 |
| 2 | 单会话 | 重新分析 | INTERFACE_DOWN_CAUSES_BGP_DOWN | leaf-01 上联接口 Down | 1.0 | 是 |
| 3 | 多会话 | BGP 为什么 Down | INTERFACE_DOWN_CAUSES_BGP_DOWN | leaf-01 上联接口 Down | 1.0 | 是 |

## 19. 三类完成度场景实现

### 19.1 60% 场景：单设备确定性故障

目标：

```text
单一设备、单一确定故障。
Agent 在单会话多次交互和多会话交互时输出一致。
```

故障样本：

```text
设备：leaf-01
故障：GE1/0/1 接口 Down
现象：
1. 接口 oper_status 为 down
2. Syslog 出现 Link Down
3. 接口流量为 0
```

标准诊断：

```text
根因：leaf-01 GE1/0/1 接口 Down。
影响：该接口承载的上联链路不可用。
建议：检查接口物理连接、光模块、线缆和对端接口状态。
```

一致性验证：

1. 同一会话连续提问 5 次。
2. 新建 5 个会话分别提问。
3. fault_fingerprint、fault_type、root_cause 必须一致。
4. 一致性评分达到 1.0 或接近 1.0。

### 19.2 80% 场景：单设备多异常表现

目标：

```text
单一设备出现多个异常表现，
Agent 需要区分根因和派生异常，
多轮、多会话输出保持一致。
```

故障样本：

```text
设备：leaf-01
根因：GE1/0/1 上联接口 Down
派生异常：
1. BGP 邻居 Down
2. 相关路由缺失
3. 转发表缺失
4. 业务网段不可达
5. 流量突降
```

诊断链：

```text
GE1/0/1 接口 Down
  -> BGP 邻居 Down
  -> 路由撤销
  -> FIB 表项缺失
  -> 业务不可达
```

标准诊断：

```text
根因不是 BGP 协议本身，也不是业务服务器故障；
根因是 leaf-01 上联接口 GE1/0/1 Down。
```

一致性验证：

1. 用户分别从接口、BGP、路由、业务不可达角度提问。
2. Agent 必须回到同一个根因。
3. 证据链顺序保持稳定。
4. 输出中的 affected_devices 和 recommendation 保持一致。

### 19.3 100% 场景：三台以上 Spine-Leaf 联动故障

目标：

```text
不少于 3 台设备互联的 Spine-Leaf 三层组网中，
发生网络故障后，
Agent 能进行多设备联动分析，
并在单会话、多会话下保持输出一致。
```

推荐拓扑：

```text
             spine-01
             /      \
        leaf-01    leaf-02
          |           |
      server-01   server-02
```

设备数量：

```text
spine-01、leaf-01、leaf-02，共 3 台网络设备。
server-01、server-02 可作为业务端点或模拟端点。
```

故障样本：

```text
leaf-01 到 spine-01 的上联链路 Down。
```

多设备事实：

| 设备 | 事实 |
|---|---|
| leaf-01 | GE1/0/1 oper_status down |
| leaf-01 | 到 spine-01 的 BGP 邻居 idle |
| spine-01 | 对端 GE1/0/10 link down |
| leaf-02 | 到 server-01 网段路由缺失或下一跳不可达 |
| server-02 | 访问 server-01 失败 |

联动诊断：

```text
leaf-01 上联链路故障
  -> leaf-01 与 spine-01 邻居中断
  -> leaf-01 侧业务网段路由撤销
  -> leaf-02 访问 leaf-01 下挂业务失败
```

标准诊断：

```text
根因：leaf-01 与 spine-01 之间的上联链路异常。
不是 leaf-02 故障，也不是 server-02 故障。
```

一致性验证：

1. 从 leaf-01 角度提问。
2. 从 leaf-02 业务访问失败角度提问。
3. 从 spine-01 看到邻居 Down 角度提问。
4. 从整体拓扑角度提问。
5. Agent 输出的根因始终一致。

## 20. 亮点实现

### 20.1 亮点一：确定性外壳包裹大模型

系统不是简单调用大模型，而是将大模型放入固定诊断流水线中：

```text
Fact -> Rule -> Topology -> RAG -> LLM -> Schema -> Cache -> Score
```

这样既利用大模型的分析和表达能力，又避免其随机性直接影响最终诊断。

### 20.2 亮点二：故障指纹驱动的一致性缓存

同一故障不依赖用户问题文本，而依赖底层事实生成指纹。

优势：

1. 用户换一种问法，结果仍一致。
2. 新开会话，结果仍一致。
3. 多次调用模型，命中缓存后不再重复推理。
4. 可显著降低模型调用成本。

### 20.3 亮点三：证据可追溯

每条诊断结论都能追溯到具体事实：

```text
root_cause
  -> evidence
  -> fact
  -> raw_observation
  -> source
```

运维人员可以看到结论来源，不是黑盒回答。

### 20.4 亮点四：一致性评分量化展示

系统不只声称“一致”，而是通过多轮测试给出分数：

```text
单会话一致性：100%
多会话一致性：100%
根因一致性：100%
证据链一致性：95%
建议一致性：98%
```

### 20.5 亮点五：Spine-Leaf 故障链路可视化

前端将根因链路和派生影响区分展示：

```text
红色：根因链路
橙色：派生影响路径
灰色：非故障设备
绿色：正常链路
```

### 20.6 亮点六：版本感知诊断

结合设备型号和软件版本检索知识库，解决设备版本升级后字段和命令输出差异导致的诊断不一致。

### 20.7 亮点七：一致性回归测试

每个故障样本都可以自动进行 N 轮测试：

```text
同一问题重复问
相似问题变换问
单会话连续问
多会话并发问
不同模型版本对比问
```

用于证明系统稳定性。

## 21. 项目目录建议

```text
NetNexusConsistentOps/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── agent/
│   │   │   ├── coordinator.py
│   │   │   ├── state_machine.py
│   │   │   └── consistency_guard.py
│   │   ├── collector/
│   │   │   ├── snmp_collector.py
│   │   │   ├── netconf_collector.py
│   │   │   ├── grpc_collector.py
│   │   │   ├── syslog_collector.py
│   │   │   └── cli_collector.py
│   │   ├── facts/
│   │   │   ├── normalizer.py
│   │   │   └── schema.py
│   │   ├── fingerprint/
│   │   │   └── builder.py
│   │   ├── rules/
│   │   │   ├── engine.py
│   │   │   └── rules.yml
│   │   ├── topology/
│   │   │   ├── graph.py
│   │   │   └── impact.py
│   │   ├── rag/
│   │   │   ├── retriever.py
│   │   │   └── indexer.py
│   │   ├── llm/
│   │   │   ├── client.py
│   │   │   ├── prompts/
│   │   │   └── output_schema.py
│   │   ├── consistency/
│   │   │   ├── scorer.py
│   │   │   └── test_runner.py
│   │   ├── models/
│   │   └── reports/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── Dashboard.vue
│   │   │   ├── Topology.vue
│   │   │   ├── Diagnosis.vue
│   │   │   ├── ConsistencyTest.vue
│   │   │   └── Report.vue
│   │   ├── components/
│   │   └── api/
│   └── package.json
├── data/
│   ├── fault_cases/
│   ├── topology/
│   └── knowledge/
├── deploy/
│   └── docker-compose.yml
└── docs/
    └── AI_OPERATIONS_DIAGNOSIS_CONSISTENCY_SOLUTION.md
```

## 22. 开发实施计划

### 22.1 第一阶段：基础诊断闭环

目标：完成单设备单故障 60% 场景。

任务：

1. 搭建 FastAPI 后端。
2. 搭建 Vue 前端基础页面。
3. 定义设备、接口、Fact、Diagnosis 数据模型。
4. 准备单设备接口 Down 故障样本。
5. 实现事实标准化。
6. 实现故障指纹生成。
7. 实现诊断缓存。
8. 实现单会话和多会话一致性测试。

### 22.2 第二阶段：单设备多异常分析

目标：完成 80% 场景。

任务：

1. 增加 BGP 邻居、路由、转发表、业务探测事实类型。
2. 实现规则引擎。
3. 构建诊断链。
4. 接入大模型生成解释。
5. 实现 JSON Schema 校验。
6. 前端展示证据链和一致性评分。

### 22.3 第三阶段：Spine-Leaf 联动分析

目标：完成 100% 场景。

任务：

1. 建立 3 台以上设备的 Spine-Leaf 拓扑样本。
2. 使用 NetworkX 构建拓扑图。
3. 实现影响路径分析。
4. 实现跨设备事实聚合。
5. 实现多角度提问的一致性测试。
6. 前端展示故障链路和派生影响路径。

### 22.4 第四阶段：亮点增强和答辩优化

目标：提升展示效果和评分竞争力。

任务：

1. 增加 RAG 知识库。
2. 增加版本感知检索。
3. 增加一致性回归测试报告。
4. 增加模型调用成本统计。
5. 增加诊断报告导出。
6. 准备演示脚本和答辩材料。

## 23. 测试方案

### 23.1 一致性测试

| 测试项 | 方法 | 预期 |
|---|---|---|
| 同问题重复测试 | 同一问题问 10 次 | root_cause 一致 |
| 相似问题测试 | 换不同问法问 10 次 | fault_type 一致 |
| 单会话多轮测试 | 同一会话连续追问 | 结论不漂移 |
| 多会话测试 | 新建多个会话分别诊断 | 结论一致 |
| 缓存命中测试 | 相同 fingerprint 重复诊断 | 不重复调用模型 |
| 拓扑联动测试 | 从不同设备角度提问 | 根因一致 |

### 23.2 示例测试问题

```text
帮我分析当前故障。
leaf-01 为什么业务不通？
BGP 邻居为什么 down？
是不是 spine-01 出问题了？
leaf-02 访问 server-01 失败的原因是什么？
重新诊断一下这个问题。
新开会话后再分析一次。
```

### 23.3 通过标准

| 场景 | 通过标准 |
|---|---|
| 60% 场景 | fault_type、root_cause 100% 一致 |
| 80% 场景 | 根因一致，派生异常链一致性不低于 90% |
| 100% 场景 | 多设备根因一致，非根因设备不被误判 |

## 24. 演示脚本

### 24.1 演示一：单设备确定故障一致性

1. 选择故障样本：leaf-01 GE1/0/1 Down。
2. 用户第一次提问：帮我分析 leaf-01 当前故障。
3. 系统输出根因：GE1/0/1 接口 Down。
4. 用户追问：是不是 BGP 的问题？
5. 系统回答：BGP Down 是派生影响，根因仍是接口 Down。
6. 新开会话再次提问。
7. 系统输出相同 fault_type 和 root_cause。
8. 展示一致性评分 100%。

### 24.2 演示二：单设备多异常一致性

1. 选择故障样本：接口 Down + BGP Down + 路由缺失 + 业务不可达。
2. 从不同角度提问。
3. 系统始终定位到接口 Down。
4. 展示诊断链：

```text
接口 Down -> BGP Down -> 路由缺失 -> 业务不可达
```

5. 展示规则命中和证据链。

### 24.3 演示三：Spine-Leaf 多设备联动

1. 展示 spine-01、leaf-01、leaf-02 拓扑。
2. 模拟 leaf-01 上联链路 Down。
3. 从 leaf-02 业务访问失败角度提问。
4. 系统跨设备关联到 leaf-01 与 spine-01 的链路。
5. 拓扑中高亮故障链路和影响路径。
6. 多会话重复提问，输出一致结果。

## 25. 风险与兜底方案

| 风险 | 影响 | 兜底 |
|---|---|---|
| 大模型输出 JSON 不合法 | 无法解析 | JSON Schema 修复重试，失败使用规则结果 |
| 大模型输出结论漂移 | 一致性下降 | 故障指纹缓存优先返回标准诊断 |
| 设备环境不稳定 | 演示失败 | 使用录制样本和模拟数据回放 |
| 真实设备接口差异 | 采集失败 | CLI 只读命令和模拟数据双通道 |
| 知识库召回不准 | 解释质量下降 | 规则引擎和拓扑分析优先 |
| 多设备拓扑复杂 | 根因误判 | 限定比赛演示拓扑，逐步扩展 |

## 26. 与 NetNexus 现有能力结合

当前项目已有 BGP、BMP、SNMP、Syslog、工具类网络能力，后续可以结合：

| 现有能力 | 可复用方向 |
|---|---|
| Syslog | 作为故障事件输入 |
| SNMP | 获取设备接口和基础状态 |
| BGP/BMP | 获取 BGP 邻居和路由状态 |
| Packet Parser | 辅助解析网络报文 |
| Web/Electron 前端 | 扩展诊断一致性页面 |

短期比赛版可以作为独立模块实现；后续可接入 NetNexus 已有网络工具能力，形成统一运维诊断平台。

## 27. 交付成果

最终可交付：

1. 一套 AI Agent 诊断一致性系统。
2. 一套单设备和 Spine-Leaf 多设备故障样本。
3. 一套故障指纹和诊断缓存机制。
4. 一套规则诊断引擎。
5. 一套大模型 Prompt 和 JSON Schema。
6. 一套一致性测试工具。
7. 一个可视化前端。
8. 一份诊断报告模板。
9. 一份答辩演示脚本。

## 28. 总结

本方案围绕“AI 大模型在运维场景的诊断一致性”构建了一套完整可落地的实现路径。

系统采用 Python + FastAPI + Vue 3 技术架构，接入已有大模型 API，不从零训练模型。通过事实标准化、故障指纹、规则引擎、拓扑分析、RAG 检索、JSON Schema 校验、诊断缓存和一致性评分，实现单设备和多设备网络故障诊断的一致输出。

该方案完整覆盖题目要求：

1. 基于 Agent 的一致性兜底策略。
2. 设备侧少变动或不变动。
3. 多设备互联场景联动分析。
4. 单设备确定故障 60% 完成度。
5. 单设备多异常故障 80% 完成度。
6. 三台以上 Spine-Leaf 组网 100% 完成度。
7. 提升网络设备运维效率的业务价值。

核心亮点是：

```text
不是让大模型自由发挥，
而是用确定性工程体系控制大模型，
让 AI 运维诊断结果稳定、可复现、可解释、可验证。
```
