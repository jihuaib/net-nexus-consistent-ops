# NetNexus ConsistentOps

AI 大模型在运维场景的诊断一致性系统，当前目录实现第二阶段能力：

1. 基于 Syslog、SNMP Trap、Telemetry 上报事件的当前故障观测。
2. 设备、接口、拓扑和当前故障观测数据模型。
3. 后端拓扑发现服务和动态前端拓扑展示。
4. 原始观测数据标准化为 Fact。
5. 基于 Fact 的确定性故障指纹。
6. 真实大模型 JSON 诊断和 Schema 校验。
7. 基于故障指纹的诊断缓存。
8. 单会话、多会话一致性测试。
9. 会话式 Agent 人机交互界面。
10. 基于 `pysmi` 的 MIB 编译、OID Tree、OID 翻译和 provider profile 绑定。
11. 单设备多异常事实链：`SYSLOG_LINK_DOWN`/`INTERFACE_OPER_DOWN`、`BGP_NEIGHBOR_DOWN`、`ROUTE_MISSING`、`FIB_ENTRY_MISSING`、`SERVICE_UNREACHABLE`。
12. 确定性规则引擎识别根因和派生异常，输出稳定诊断链。
13. 上报事件页面通过 WebSocket 实时接收后端推送，不做定时轮询。

## 技术栈

| 模块 | 技术 |
|---|---|
| 后端 | Python 3.10+、FastAPI |
| 前端 | Vue 3、Vite |
| 第二阶段缓存 | 进程内缓存，后续可替换 Redis |
| 第二阶段数据源 | Syslog、SNMP Trap、gRPC/Telemetry 上报事件；SNMP/LLDP 仅作为拓扑上下文 |
| 大模型 | OpenAI-compatible Chat Completions API，必须通过环境变量配置 |
| 一致性策略 | Fact 标准化、故障指纹、大模型 JSON 诊断、Schema 校验、诊断缓存、结果评分 |
| MIB 编译 | `pysmi` 解析 SMIv2 MIB，后端生成 OID Tree、OID 翻译索引和 provider 绑定视图 |

## 大模型配置

本项目不提供本地模拟诊断。首次诊断必须调用真实大模型接口。未配置时，`/api/agent/chat`、`/api/diagnosis/analyze` 和 `/api/consistency/test` 会返回 503。

必填环境变量：

```bash
export LLM_BASE_URL=https://your-provider.example/v1
export LLM_MODEL=your-model-name
export LLM_API_KEY=your-api-key
```

要求服务端兼容：

```text
POST {LLM_BASE_URL}/chat/completions
```

可选环境变量：

```bash
export LLM_TIMEOUT_SECONDS=60
export LLM_TEMPERATURE=0
export LLM_TOP_P=0.1
export LLM_JSON_MODE=1
```

也可以在前端“设置”页面的大模型配置面板中填写 Base URL、Model 和 API Key。页面配置只保存在当前后端进程内，重启后端后会丢失；生产环境应改为加密持久化存储。

## 数据说明

第二阶段不提供本地大模型模拟诊断。诊断事实来自设备通过 Syslog、SNMP Trap、gRPC/Telemetry 等通道上报的事件；`SnmpLldpTopologyProvider` 只提供设备和链路拓扑上下文。没有上报事件时，系统不会默认诊断接口 Down；只有收到同一时间窗口内的链路、BGP、路由、FIB 或业务事件后，才会生成 Fact 链并进入诊断。

拓扑不在前端写死。页面通过 `/api/topology` 和 `/api/topology/discover` 获取后端发现结果，并按返回的 `nodes` 和 `edges` 渲染。真实环境中设备数量和连接关系应由采集器发现：

| 目标 | 主要协议 |
|---|---|
| 发现设备身份 | SNMP sysName/sysObjectID、NETCONF、gNMI system paths |
| 发现接口状态 | SNMP IF-MIB/IF-XTable、NETCONF ietf-interfaces、gRPC/gNMI Telemetry |
| 发现二层连接 | SNMP LLDP-MIB `lldpRemTable`，或厂商 NDP/CDP 等价表 |
| 发现三层连接 | BGP-LS、BMP、路由邻居表 |

当前第二阶段运行时主模式是 `snmp_lldp`：通过标准 SNMP `IF-MIB` 和 `LLDP-MIB` 发现设备、接口和邻居拓扑，是当前最接近真机发现链路的模式。前端不写死设备和链路，诊断也不从本地样本生成事实。本地 FRR lab 的接口 down/up 会由容器内链路事件 agent 基于真实 `/sys/class/net` 状态变化发出 UDP Syslog 和标准 SNMPv2 linkDown/linkUp Trap，后端通过 WebSocket 将新事件实时推送到 Syslog、Trap、Telemetry 三类独立页面。

SNMP provider 不在代码里硬编码业务 OID。OID 绑定来自 `mibs/profiles/*.json`，页面可以按 profile 编译内置 MIB 或上传厂商 MIB，并生成 MIB Tree。当前提供：

| Profile | Provider | 用途 |
|---|---|---|
| `snmp_lldp` | `snmp_lldp` | 标准 SNMPv2-MIB、IF-MIB、LLDP-MIB |
| `h3c_snmp_lldp` | `snmp_lldp` | H3C 接入 profile，可上传 H3C 私有 MIB 后编译 |

扩展方式：

```text
TopologyService
  -> SnmpLldpTopologyProvider
  -> 后续 NetconfTelemetryTopologyProvider / BgpLsBmpTopologyProvider
  -> nodes / edges / discovery
```

真实 H3C 设备切换时，优先复用 `SnmpLldpTopologyProvider`，在设置弹窗配置 `scan_cidrs`、可选 `targets`、`community` 和 MIB profile 即可；前端、Agent 和一致性评分继续消费同一份 `nodes/edges/discovery`。

## 后端分层

```text
backend/app/
├── main.py                         API 入口
├── core/container.py               依赖装配
├── application/                    Agent、诊断、事实标准化、一致性用例
├── domain/                         Fact、故障指纹等确定性领域逻辑
└── infrastructure/                 SNMP 采集器、MIB 编译、拓扑 provider 和大模型客户端
```

```text
mibs/
├── builtin/                        拓扑发现所需标准 SNMPv2/IF/LLDP MIB
├── profiles/                       provider profile 和 OID 绑定
└── workspace/                      页面上传 MIB 的运行时目录，已忽略提交
```

## 前端分层

```text
frontend/src/
├── api/                            后端 API 调用
├── components/                     业务组件、应用导航和 scoped CSS
├── components/ui/                  通用面板、页面头等基础 UI 组件
├── composables/                    页面状态和动作编排
├── views/                          诊断、MIB、Syslog、Trap、Telemetry 功能页；拓扑画布集成在诊断页
├── App.vue                         应用壳、导航和 view 切换
└── style.css                       全局 reset 和基础控件样式
```

## Agent 边界说明

本项目里的 Agent 不是单纯的聊天框，也不是单纯的后端诊断函数，而是两部分组合：

```text
会话式人机界面
  + 后端 Agent 编排
  + 诊断工具调用
  + 会话历史
  + 工具轨迹
  + 一致性兜底
```

第二阶段继续使用 `/api/agent/chat` 作为 Agent 会话入口。用户可以从接口、BGP、路由、FIB 或业务不可达等角度追问，Agent 会保留会话历史，并调用事实标准化、规则归因、故障指纹、证据构造、缓存等工具；最终诊断结论由真实大模型生成并经过规则归一化。

## 文档

| 文档 | 说明 |
|---|---|
| `docs/INSTALLATION.md` | 完整安装、启动、测试、接口验证和故障排查 |
| `docs/PHASE1_IMPLEMENTATION_REPORT.md` | 第一阶段实现分析、题目覆盖情况、验证记录和后续计划 |
| `docs/PHASE2_IMPLEMENTATION_REPORT.md` | 第二阶段单设备多异常实现、差异和验证记录 |
| `labs/frr-spine-leaf/README.md` | FRR + snmpd + LLDP-MIB 本地 Spine-Leaf 测试环境 |

## 运行后端

```bash
cd NetNexusConsistentOps/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

也可以直接运行：

```bash
cd NetNexusConsistentOps
./scripts/setup_backend.sh
./scripts/start_backend.sh
```

后端接口地址：

```text
http://127.0.0.1:8010
```

## 运行前端

```bash
cd NetNexusConsistentOps/frontend
npm install
npm run dev
```

前端默认连接：

```text
http://127.0.0.1:8010
```

如需修改后端地址：

```bash
VITE_API_BASE=http://127.0.0.1:8010 npm run dev
```

也可以直接运行：

```bash
cd NetNexusConsistentOps
./scripts/start_frontend.sh
```

## 运行测试

```bash
cd NetNexusConsistentOps/backend
python3 -m unittest discover tests
```

本地结构检查：

```bash
cd NetNexusConsistentOps
./scripts/test_phase1.sh
```

真实大模型联调检查：

```bash
cd NetNexusConsistentOps
./scripts/check_phase1.sh
```

## 第二阶段接口

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/health` | GET | 健康检查 |
| `/api/devices` | GET | 查询设备 |
| `/api/topology` | GET | 查询拓扑 |
| `/api/topology/discovery-capabilities` | GET | 查询拓扑发现能力和真实协议边界 |
| `/api/topology/discover` | POST | 触发 SNMP 拓扑发现 |
| `/api/mibs/profiles` | GET | 查询 MIB provider profiles |
| `/api/mibs/compile` | POST | 编译内置或上传 MIB 并生成 OID Tree |
| `/api/mibs/tree` | GET | 查询 MIB Tree |
| `/api/mibs/translate` | POST | 翻译 OID 到 MIB 对象 |
| `/api/fault-cases` | GET | 查询当前 SNMP 可诊断故障观测 |
| `/api/facts?fault_case_id=live-snmp-current` | GET | 查询标准化事实 |
| `/api/llm/config` | GET/POST | 查询或配置大模型 API，不回显 API Key |
| `/api/agent/chat` | POST | Agent 会话式诊断入口 |
| `/api/agent/sessions/{session_id}` | GET | 查询 Agent 会话历史 |
| `/api/diagnosis/analyze` | POST | 发起诊断 |
| `/api/consistency/test` | POST | 执行一致性测试 |

## 示例 Agent 请求

```bash
curl -X POST http://127.0.0.1:8010/api/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "帮我分析 leaf-01 当前为什么业务不通",
    "fault_case_id": "live-snmp-current",
    "session_id": "agent-session-001"
  }'
```

## 示例一致性测试

```bash
curl -X POST http://127.0.0.1:8010/api/consistency/test \
  -H 'Content-Type: application/json' \
  -d '{
    "fault_case_id": "live-snmp-current",
    "session_modes": ["single_session", "multi_session"],
    "questions": [
      "帮我分析当前故障",
      "leaf-01 为什么业务不通",
      "是不是 BGP 的问题",
      "重新诊断一下"
    ],
    "run_count": 8
  }'
```

## 示例拓扑发现

通过 SNMP/LLDP-MIB 发现当前配置的厂商设备：

```bash
curl -X POST http://127.0.0.1:8010/api/topology/discover \
  -H 'Content-Type: application/json' \
  -d '{"mode": "snmp_lldp"}'
```

通过 SNMP/LLDP-MIB 发现本地 FRR lab：

```bash
cd NetNexusConsistentOps
./scripts/start_frr_lab.sh

curl -X POST http://127.0.0.1:8010/api/topology/discover \
  -H 'Content-Type: application/json' \
  -d '{"mode": "snmp_lldp"}'
```

如果使用本地 FRR lab，先配置管理网段扫描：

```bash
curl -X POST http://127.0.0.1:8010/api/topology/discovery-config \
  -H 'Content-Type: application/json' \
  -d '{"targets":["127.0.0.1:11611","127.0.0.1:11612","127.0.0.1:11613","127.0.0.1:11614"],"scan_cidrs":[],"community":"public"}'
```

预期发现 4 台设备和 2 条链路，其中 `isolated-01` 是无业务链路的孤立设备：

```text
spine-01 -- leaf-01
spine-01 -- leaf-02
isolated-01
```

## 示例真实上报

先启动后端和前端，再启动 FRR lab。后端默认监听：

```text
Syslog UDP: 0.0.0.0:1514
SNMP Trap UDP: 0.0.0.0:1162
```

断开 `leaf-01` 到 `spine-01` 的实验链路：

```bash
docker exec netnexus-leaf-01 ip link set eth1 down
```

前端左侧进入 `Syslog` 和 `Trap` 页面，可以看到由容器真实接口状态变化触发的 Syslog 和 SNMP Trap。恢复链路：

```bash
docker exec netnexus-leaf-01 ip link set eth1 up
```

## 示例 MIB 编译

```bash
curl -X POST http://127.0.0.1:8010/api/mibs/compile \
  -H 'Content-Type: application/json' \
  -d '{"profile_id": "snmp_lldp", "include_tree": true}'
```

翻译实例 OID：

```bash
curl -X POST http://127.0.0.1:8010/api/mibs/translate \
  -H 'Content-Type: application/json' \
  -d '{"profile_id": "snmp_lldp", "oid": ".1.3.6.1.2.1.31.1.1.1.1.2"}'
```

## 第二阶段完成度

当前实现对应赛题 80% 完成度：

```text
单一设备出现多个异常表现时，
Agent 单会话多次交互以及多会话交互时，
输出内容保持一致，并能回到同一根因。
```

本阶段已经接入 OpenAI-compatible 大模型接口。规则引擎负责稳定识别根因和派生异常链，大模型负责生成结构化解释；最终结果再经过 Schema 校验、规则归一化、故障指纹缓存和一致性评分。
