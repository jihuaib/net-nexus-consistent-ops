# NetNexus ConsistentOps 安装与运行文档

本文档用于从零安装、启动和验证 `NetNexusConsistentOps` 第二阶段系统。

## 1. 当前实现范围

当前目录实现的是赛题 6.4.3 的第二阶段能力，对应 80% 完成度目标：

```text
单一设备出现多个异常表现时，
Agent 单会话多次交互以及多会话交互时，
输出内容保持一致，并能回到同一根因。
```

当前已经实现：

1. 基于 Syslog、SNMP Trap、Telemetry 上报事件的当前故障观测。
2. 原始观测数据标准化为 Fact。
3. 稳定故障指纹生成。
4. 真实大模型诊断、Schema 校验和故障指纹缓存。
5. 基于故障指纹的诊断缓存。
6. 单会话、多会话一致性测试。
7. FastAPI 后端接口。
8. 后端拓扑发现接口和动态前端拓扑展示。
9. FRR + snmpd + LLDP-MIB 三设备 Spine-Leaf 加一台孤立设备的测试环境。
10. Vue 3 会话式 Agent 人机交互界面。
11. 基于 `pysmi` 的 MIB 编译接口、MIB Tree 页面和 provider profile 绑定。
12. 单设备多异常事实链：链路 Down、BGP 邻居 Down、路由缺失、FIB 缺失、业务不可达。
13. Fact 依赖上下文保留：派生异常会携带依赖接口、下一跳、远端设备和来源事件，供大模型诊断使用。
14. 本地知识库/RAG：内置 Runbook、自定义 SOP 文档、BM25 检索和诊断 `knowledge_context` 注入。
15. Syslog、Trap、Telemetry 按类型拆分页面，通过 WebSocket 实时展示原始输入、接收状态和时间窗口关联摘要。
16. FRR lab 接口真实 down/up 时，容器内链路事件 agent 会发出 UDP Syslog 和标准 SNMPv2 linkDown/linkUp Trap。

当前尚未实现：

1. 第三阶段完整 Spine-Leaf 三台以上设备联动诊断。
2. NETCONF、Telemetry 长连接接收器和生产级事件总线。
3. Redis、数据库、向量检索和生产级知识库权限管理。

## 2. 目录结构

```text
NetNexusConsistentOps/
├── README.md
├── .gitignore
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   └── container.py
│   │   ├── application/
│   │   │   ├── agent_service.py
│   │   │   ├── consistency_service.py
│   │   │   ├── diagnosis_service.py
│   │   │   └── fact_normalizer.py
│   │   ├── domain/
│   │   │   ├── facts.py
│   │   │   └── fingerprint.py
│   │   └── infrastructure/
│   │       ├── collectors/
│   │       │   ├── base.py
│   │       │   └── snmp_observation_collector.py
│   │       └── mib/
│   │           ├── mib_registry.py
│   │           ├── mib_service.py
│   │           └── profile_registry.py
│   │       └── topology/
│   │           └── snmp_lldp_provider.py
│   ├── tests/
│   │   └── test_phase1.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   │   └── ui/
│   │   ├── composables/
│   │   ├── views/
│   │   ├── App.vue
│   │   ├── main.js
│   │   └── style.css
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── scripts/
│   ├── setup_backend.sh
│   ├── start_backend.sh
│   ├── start_frontend.sh
│   ├── start_frr_lab.sh
│   ├── stop_frr_lab.sh
│   ├── test_phase1.sh
│   └── check_phase1.sh
├── labs/
│   └── frr-spine-leaf/
│       ├── docker-compose.yml
│       ├── spine-01/
│       ├── leaf-01/
│       ├── leaf-02/
│       └── isolated-01/
├── mibs/
│   ├── builtin/
│   └── profiles/
└── docs/
    ├── INSTALLATION.md
    ├── PHASE1_IMPLEMENTATION_REPORT.md
    └── PHASE2_IMPLEMENTATION_REPORT.md
```

## 3. 数据来源说明

第二阶段不保留本地大模型诊断样本。诊断事实来自设备通过 Syslog、SNMP Trap、gRPC/Telemetry 等通道上报的事件；SNMP/LLDP 只作为拓扑上下文。没有上报事件时，系统不会默认生成接口 Down 诊断。只有同一时间窗口内收到链路、BGP、路由、FIB 或业务事件后，系统才会生成 Fact 链并进入诊断。

本地 FRR lab 是测试设备环境，不是诊断假数据：容器内运行 `FRR + snmpd + LLDP-MIB pass_persist subagent`，后端通过 SNMP 协议读取拓扑，并通过 UDP Syslog/SNMP Trap 接收真实接口状态变化事件。后续切到真实设备时仍复用同一个 provider 和事件数据结构。

拓扑不由前端固定。页面通过后端接口读取 `nodes/edges/discovery`：

| 发现内容 | 真实协议来源 |
|---|---|
| 设备数量 | SNMP sysName/sysObjectID、NETCONF、gNMI system paths |
| 接口状态 | SNMP IF-MIB/IF-XTable、NETCONF `ietf-interfaces`、Telemetry |
| 二层链路 | LLDP-MIB `lldpRemTable`、厂商 NDP/CDP 等价表 |
| 三层链路 | BGP-LS、BMP、路由邻居表 |

当前 `/api/topology/discover` 主运行模式是 `mode=snmp_lldp`：通过配置的 seed IP 或管理网段 CIDR 主动探测 SNMP `sysName`，再读取标准 `IF-MIB`、`LLDP-MIB` 发现设备和链路。真实设备切换时优先复用 `SnmpLldpTopologyProvider`；如果后续需要 NETCONF、Telemetry、BGP-LS 或 BMP，再新增 provider，输出同样的 `nodes/edges/discovery`，前端和 Agent 不需要改。

SNMP provider 使用 `mibs/profiles/*.json` 中的 `oid_bindings`，不在 provider 代码里写死 OID。页面的 MIB 编译入口会调用后端 `pysmi` 解析内置 MIB 或上传 MIB，生成 OID Tree，并用于 OID 翻译。不同厂商或不同 provider 可以新增 profile，例如当前内置的 `snmp_lldp` 和 `h3c_snmp_lldp`。

## 4. 环境要求

| 环境 | 建议版本 | 用途 |
|---|---|---|
| macOS / Linux | 任意现代版本 | 开发和演示环境 |
| Python | 3.10+，当前也兼容 Python 3.9 | 后端 FastAPI |
| Node.js | 16+ | 前端 Vue/Vite |
| npm | 8+ | 前端依赖安装 |
| Docker | Docker Desktop 或 docker engine | 可选，运行 FRR 本地测试设备 |
| curl | 系统自带即可 | 接口验证 |
| 大模型服务 | OpenAI-compatible Chat Completions | 诊断分析 |

检查命令：

```bash
python3 --version
node --version
npm --version
curl --version
```

## 5. 大模型配置

本项目不提供本地模拟诊断。首次诊断必须调用真实大模型接口。未配置时，诊断接口会返回 503。

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

如果模型服务不支持 `response_format={"type":"json_object"}`，可设置：

```bash
export LLM_JSON_MODE=0
```

也可以在前端“设置”页面的大模型配置面板中填写配置。页面配置通过 `/api/llm/config` 写入后端运行时内存，不会回显 API Key，重启后端后会丢失。生产部署应改为加密持久化存储。

## 5.5 环境划分

开发环境：

- 后端用 `scripts/start_backend.sh`，默认监听 `0.0.0.0:8010`，方便本机或 Linux VM 联调。
- 前端用 `scripts/start_frontend.sh`，默认监听 `0.0.0.0:5178`。
- 浏览器请求同源 `/api/*`，由 Vite dev server 根据 `VITE_PROXY_TARGET` 代理到后端。
- 外部访问只需要放行 `5178/tcp`，一般不需要让浏览器直接访问 `8010/tcp`。

生产环境：

- 后端用 `scripts/start_backend_prod.sh`，默认监听 `127.0.0.1:8010`，建议放在 Nginx、Caddy 或 Ingress 后面。
- 前端用 `scripts/build_frontend_prod.sh` 构建 `frontend/dist`。
- 生产不依赖 Vite proxy；反向代理负责服务静态文件，并把 `/api/` 和 `/api/events/ws` 转发到后端。
- Nginx 示例见 `deploy/nginx/netnexus.conf.example`。

## 6. 后端安装

进入后端目录：

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps/backend
```

创建虚拟环境：

```bash
python3 -m venv .venv
```

激活虚拟环境：

```bash
source .venv/bin/activate
```

安装依赖：

```bash
pip install -r requirements.txt
```

也可以直接使用脚本：

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps
./scripts/setup_backend.sh
```

## 7. 开发环境：启动后端

手动启动：

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps/backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

脚本启动：

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps
./scripts/start_backend.sh
```

后端地址：

```text
http://127.0.0.1:8010
```

如果运行在 Linux 虚拟机上，宿主机或局域网机器访问：

```text
http://<虚拟机IP>:8010
```

API 文档：

```text
http://127.0.0.1:8010/docs
```

健康检查：

```bash
curl http://127.0.0.1:8010/api/health
```

预期返回：

```json
{
  "status": "ok",
  "phase": "phase2",
  "capabilities": [
    "single_device_multi_anomaly_chain",
    "fact_normalization",
    "fault_fingerprint",
    "diagnosis_cache",
    "single_and_multi_session_consistency_test"
  ]
}
```

## 8. 前端安装

进入前端目录：

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps/frontend
```

安装依赖：

```bash
npm install
```

前端依赖必须安装在当前独立项目的 `frontend/node_modules` 下，避免和其他 Vue/Vite 项目混用依赖。

## 9. 开发环境：启动前端

手动启动：

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps/frontend
npm run dev -- --host 0.0.0.0 --port 5178
```

未设置 `VITE_API_BASE` 时，前端会请求同源 `/api/*`，由 Vite 开发服务器代理到后端。比如页面是 `http://192.168.56.10:5178/`，浏览器请求 `http://192.168.56.10:5178/api/health`，Vite 再转发到后端默认 `http://127.0.0.1:8010/api/health`。

如果后端不在默认端口，可以只改代理目标：

```bash
VITE_PROXY_TARGET=http://127.0.0.1:8011 npm run dev -- --host 0.0.0.0 --port 5178
```

如果不走代理、让浏览器直连后端，可以显式指定：

```bash
VITE_API_BASE=http://<后端主机IP>:8010 npm run dev -- --host 0.0.0.0 --port 5178
```

脚本启动：

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps
./scripts/start_frontend.sh
```

前端地址：

```text
http://127.0.0.1:5178/
```

Linux 虚拟机外部访问：

```text
http://<虚拟机IP>:5178/
```

## 10. 生产环境：构建和部署

构建前端：

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps
./scripts/build_frontend_prod.sh
```

启动后端生产进程：

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps
./scripts/start_backend_prod.sh
```

默认生产拓扑：

```text
Nginx/Caddy/Ingress :80 or :443
  /                  -> frontend/dist
  /api/              -> http://127.0.0.1:8010
  /api/events/ws     -> http://127.0.0.1:8010 with WebSocket upgrade
```

如果生产前后端不同域名，构建时显式指定 API：

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps/frontend
VITE_API_BASE=https://api.example.com npm run build
```

## 11. 启动 FRR SNMP/LLDP Lab

FRR lab 是可选测试设备，用于验证接近真机的 SNMP 拓扑发现：

```text
leaf-01 -- spine-01 -- leaf-02
isolated-01
```

启动：

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps
./scripts/start_frr_lab.sh
```

检查 BGP：

```bash
docker exec netnexus-spine-01 vtysh -c 'show bgp summary'
```

检查 SNMP：

```bash
curl -X POST http://127.0.0.1:8010/api/topology/discovery-config \
  -H 'Content-Type: application/json' \
  -d '{"targets":["127.0.0.1:11611","127.0.0.1:11612","127.0.0.1:11613","127.0.0.1:11614"],"scan_cidrs":[],"community":"public"}'
```

配置管理网段扫描：

```bash
curl -X POST http://127.0.0.1:8010/api/topology/discovery-config \
  -H 'Content-Type: application/json' \
  -d '{"targets":["127.0.0.1:11611","127.0.0.1:11612","127.0.0.1:11613","127.0.0.1:11614"],"scan_cidrs":[],"community":"public"}'
```

停止：

```bash
./scripts/stop_frr_lab.sh
```

## 12. 后端测试

运行单元测试：

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps/backend
.venv/bin/python -m unittest discover tests
```

脚本运行：

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps
./scripts/test_phase1.sh
```

预期结果：

```text
...
----------------------------------------------------------------------
Ran 17 tests

OK
```

测试覆盖：

1. Fact 标准化是否提取接口 Down、流量为 0、Syslog Link Down、业务不可达。
2. 故障指纹是否不受 Fact 顺序影响。
3. 大模型输出 Schema 是否包含诊断必需字段。
4. 未配置大模型时是否明确报告缺失配置。
5. 拓扑服务是否返回发现到的节点数和链路数。
6. SNMP LLDP provider 是否能通过 IF-MIB/LLDP-MIB 解析 3 节点 2 链路，并能通过管理网段 CIDR 扫描发现孤立节点。
7. MIB profile 是否能加载 provider OID 绑定。
8. `pysmi` MIB 编译器是否能生成 MIB Tree 并翻译 IF-MIB/LLDP-MIB OID。
9. 如果配置了真实大模型环境变量，才运行单会话和多会话一致性集成测试。

## 13. 前端构建验证

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps/frontend
npm run build
```

预期结果包含：

```text
✓ built
```

## 14. 接口验证

启动后端后验证拓扑发现：

```bash
curl http://127.0.0.1:8010/api/topology
curl -X POST http://127.0.0.1:8010/api/topology/discover \
  -H 'Content-Type: application/json' \
  -d '{"mode": "snmp_lldp"}'
```

关键预期字段：

```json
{
  "discovery": {
    "mode": "snmp_lldp",
    "node_count": 4,
    "edge_count": 2
  }
}
```

如果已启动 FRR lab，优先验证 SNMP/LLDP-MIB 管理网段扫描拓扑：

```bash
curl -X POST http://127.0.0.1:8010/api/topology/discovery-config \
  -H 'Content-Type: application/json' \
  -d '{"targets":["127.0.0.1:11611","127.0.0.1:11612","127.0.0.1:11613","127.0.0.1:11614"],"scan_cidrs":[],"community":"public"}'

curl -X POST http://127.0.0.1:8010/api/topology/discover \
  -H 'Content-Type: application/json' \
  -d '{"mode": "snmp_lldp"}'
```

关键预期字段：

```json
{
  "discovery": {
    "mode": "snmp_lldp",
    "node_count": 4,
    "edge_count": 2,
    "group_count": 2
  }
}
```

验证 MIB 编译和 OID Tree：

```bash
curl http://127.0.0.1:8010/api/mibs/profiles

curl -X POST http://127.0.0.1:8010/api/mibs/compile \
  -H 'Content-Type: application/json' \
  -d '{"profile_id": "snmp_lldp", "include_tree": true}'
```

关键预期字段：

```json
{
  "profile": {"id": "snmp_lldp", "provider": "snmp_lldp"},
  "summary": {
    "failedFiles": [],
    "unresolvedObjects": [],
    "modules": ["SNMPv2-MIB", "IF-MIB", "LLDP-MIB"]
  },
  "tree": [{"objectName": "iso"}]
}
```

验证 OID 翻译：

```bash
curl -X POST http://127.0.0.1:8010/api/mibs/translate \
  -H 'Content-Type: application/json' \
  -d '{"profile_id": "snmp_lldp", "oid": ".1.3.6.1.2.1.31.1.1.1.1.2"}'
```

启动后端后执行 Agent 会话请求：

```bash
curl -X POST http://127.0.0.1:8010/api/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "leaf-01 为什么业务不通",
    "fault_case_id": "live-snmp-current",
    "session_id": "check-agent-session"
  }'
```

关键预期字段：

```json
{
  "session_id": "check-agent-session",
  "diagnosis": {
    "fault_fingerprint": "fp_...",
    "fault_type": "INTERFACE_DOWN",
    "root_cause": "leaf-01 eth1 接口 Down",
    "confidence": 0.96
  },
  "history": ["user message", "assistant message"],
  "tool_trace": [{"name": "collect_observations"}]
}
```

一致性测试：

```bash
curl -X POST http://127.0.0.1:8010/api/consistency/test \
  -H 'Content-Type: application/json' \
  -d '{
    "fault_case_id": "live-snmp-current",
    "session_modes": ["single_session", "multi_session"],
    "run_count": 8
  }'
```

关键预期字段：

```json
{
  "overall_consistency_score": 1.0,
  "passed": true
}
```

也可以使用脚本完整验证：

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps
./scripts/check_phase1.sh
```

注意：`check_phase1.sh` 会检查环境变量或当前后端运行时配置。环境变量和页面配置都没有时会直接失败。

## 15. 页面验证

打开：

```text
http://127.0.0.1:5178/
```

页面应展示：

1. `NetNexus ConsistentOps` 标题。
2. 左侧应用导航：诊断、MIB、设置。
3. 诊断页展示 Agent 会话、拓扑画布、拓扑发现模式、快捷追问、结构化诊断、工具轨迹、标准化 Fact 和一致性评分。
4. 拓扑画布展示后端发现到的设备数、链路数、拓扑节点和链路。
5. 诊断页提供拓扑发现模式选择：`collector` 或 `SNMP LLDP`。
6. MIB 页提供 MIB 编译面板，可选择 profile、上传 MIB、生成 MIB Tree、翻译 OID。
7. 设置页提供大模型配置和系统状态。
8. 配置真实模型后诊断页展示诊断结果：`INTERFACE_DOWN`。

## 16. 常见问题

### 16.1 后端端口被占用

检查端口：

```bash
lsof -nP -iTCP:8010 -sTCP:LISTEN
```

可以改端口启动：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8011
```

前端也要同步指定：

```bash
VITE_PROXY_TARGET=http://127.0.0.1:8011 npm run dev
```

### 16.2 前端端口被占用

检查端口：

```bash
lsof -nP -iTCP:5178 -sTCP:LISTEN
```

改端口：

```bash
npm run dev -- --host 0.0.0.0 --port 5179
```

### 16.3 Python 依赖缺失

重新安装：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 16.4 前端无法访问后端

确认后端运行：

```bash
curl http://127.0.0.1:8010/api/health
```

默认情况下前端通过 `/api` 代理访问后端，确认代理目标：

```bash
VITE_PROXY_TARGET=http://127.0.0.1:8010 npm run dev
```

如果显式设置了 `VITE_API_BASE`，浏览器会绕过代理直连该地址，需要确认宿主机能访问这个后端地址和端口。

### 16.5 FRR lab 构建出现 exec format error

现象：

```text
exec /bin/sh: exec format error
ERROR [2/6] RUN apk add --no-cache ...
```

原因通常是历史缓存里还留着旧的 amd64 FRR 基础镜像。当前 FRR lab 默认用 `ubuntu:24.04` 多架构基础镜像，再用 `apt` 安装 FRR，Docker 会按当前宿主机架构拉取。

处理：

```bash
docker image rm netnexus-frr-snmp:latest 2>/dev/null || true
./scripts/start_frr_lab.sh
```

如果需要替换基础镜像，使用 Ubuntu/Debian 系镜像：

```bash
FRR_BASE_IMAGE=<your-ubuntu-or-debian-image> ./scripts/start_frr_lab.sh
```

### 16.6 大模型未配置

现象：

```text
Large model is not configured. Missing environment variables: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
```

处理：

```bash
export LLM_BASE_URL=https://your-provider.example/v1
export LLM_MODEL=your-model-name
export LLM_API_KEY=your-api-key
```

然后重启后端。

### 16.6 一致性评分不是 1.0

同一 SNMP 故障观测下应为 `1.0`。如果不是，优先检查：

1. FRR lab 或真实设备的当前故障是否稳定存在。
2. 是否修改了 `backend/app/application/diagnosis_service.py` 中返回字段。
3. 是否修改了 `backend/app/application/consistency_service.py` 中比较字段。

## 17. 第二阶段验收标准

| 验收项 | 标准 |
|---|---|
| 后端能启动 | `/api/health` 返回 `status=ok` |
| 大模型已配置 | `/api/health` 中 `llm.configured=true` |
| 前端能启动 | 浏览器打开 5178 页面 |
| 拓扑发现 | `/api/topology/discover` 返回 `node_count` 和 `edge_count` |
| FRR lab | 启动 lab 并配置 4 个本机 seed targets 后，`mode=snmp_lldp` 通过后端原生 SNMP 返回 4 台设备、2 条链路、2 个组网 |
| MIB 编译 | `/api/mibs/compile` 返回模块、对象数、MIB Tree 且无 failed/unresolved |
| 上报事件 | `/api/events/syslog`、`/api/events/trap`、`/api/events/telemetry` 可以写入事件，页面“事件”能看到原始上报 |
| 事件关联 | `/api/events/correlation` 返回同一窗口内的事件摘要 |
| 多异常 Fact | 显式事件或 AI 抽取后的 raw 事件进入 `/api/facts`，Fact 类型来自结构化 `event_type` |
| 多异常诊断 | `/api/agent/chat` 返回 `ANCHOR_EVENT_CAUSES_DEPENDENT_FAILURES` |
| 证据不足 | 只上报 BGP/路由/业务异常且无链路根因事件时，诊断返回 `UNKNOWN_NEED_MORE_DATA` |
| 故障指纹 | 同一故障稳定返回同一指纹 |
| 单会话一致性 | 分数为 1.0 |
| 多会话一致性 | 分数为 1.0 |
| 单元测试 | 本地结构测试通过，真实 LLM 集成测试在配置环境变量后运行 |
| 前端构建 | `npm run build` 通过 |

## 18. 下一阶段扩展方向

第三阶段建议实现：

1. 基于 FRR SNMP/LLDP lab 或真实设备采集生成三台设备以上联动故障观测。
2. 实现 Spine-Leaf 拓扑联动分析。
3. 前端拓扑从静态布局升级为 AntV G6。
4. 新增 `SnmpLldpTopologyProvider`、`NetconfTelemetryTopologyProvider` 或 `BgpLsBmpTopologyProvider` 接真实设备。
5. 支持从不同设备视角提问后仍定位同一根因。
6. 增加 Redis、数据库、向量检索和知识库权限管理作为生产化增强。
