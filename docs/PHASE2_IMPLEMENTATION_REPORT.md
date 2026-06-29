# 第二阶段实现报告

## 1. 阶段目标

第二阶段对应赛题 6.4.3 的 80% 完成度：

```text
单一设备出现多个异常表现时，
Agent 单会话多次交互以及多会话交互时，
输出内容保持一致，并能回到同一根因。
```

当前实现以设备上报事件为诊断输入。本地 FRR lab 不再通过页面或脚本模拟投递链路事件；容器内链路事件 agent 监听真实 `/sys/class/net/eth*` 状态变化，接口 down/up 时发出 UDP Syslog 和标准 SNMPv2 linkDown/linkUp Trap。示例事件窗口如下：

```text
Syslog/Trap: leaf-01 eth1 link down
Telemetry: eth1 traffic 0bps
Trap: BGP neighbor down
Trap: route missing
Trap: FIB entry missing
Syslog/Probe: service unreachable
```

关联后的诊断链：

```text
leaf-01 eth1 链路 Down
  -> BGP 邻居 Down
  -> 路由缺失
  -> FIB 表项缺失
  -> 业务探测不可达
```

## 2. 已实现能力

1. 新增 `EventStore` 保存 Syslog、SNMP Trap、Telemetry 上报事件。
2. 新增 `SyslogReceiver` 和 `SnmpTrapReceiver`，后端启动时监听 UDP 上报端口。
3. 新增 `CorrelationEngine`，按时间窗口和设备/接口依赖关系关联上报事件。
4. `SnmpObservationCollector` 不再默认用 SNMP 轮询结果生成故障，只消费 `CorrelationEngine` 输出的事件窗口；SNMP/LLDP 仅作为拓扑上下文。
5. `FactNormalizer` 新增 `BGP_NEIGHBOR_DOWN`、`ROUTE_MISSING`、`FIB_ENTRY_MISSING`。
6. `RuleEngine` 新增确定性规则 `R-P2-001`，识别 `INTERFACE_DOWN_CAUSES_BGP_ROUTE_LOSS`；如果只有 BGP/路由/业务异常但缺少链路根因证据，则返回 `UNKNOWN_NEED_MORE_DATA`。
7. `SnmpTrapReceiver` 能解码标准 SNMPv2 linkDown/linkUp Trap，将 `ifIndex`、`ifName`、`ifOperStatus` 等 varbind 归一为结构化事件。
8. FRR lab 镜像新增真实链路事件 agent，`docker exec netnexus-leaf-01 ip link set eth1 down` 后页面能收到 Syslog 和 Trap。
9. 前端按类型拆成 `Syslog`、`Trap`、`Telemetry` 独立页面，能查看事件列表、接收器状态和关联摘要。
10. 事件页面通过 WebSocket 接收后端实时推送，不再用定时轮询刷接口。

## 3. 关键代码

| 文件 | 第二阶段变更 |
|---|---|
| `backend/app/application/event_store.py` | 内存事件存储 |
| `backend/app/application/event_stream.py` | WebSocket 事件推送 Hub |
| `backend/app/application/event_normalizer.py` | 上报事件标准化 |
| `backend/app/application/correlation_engine.py` | 时间窗口关联 |
| `backend/app/infrastructure/events/snmp_trap_decoder.py` | 标准 SNMP Trap 解码 |
| `backend/app/infrastructure/events/udp_receivers.py` | Syslog/Trap UDP 接收 |
| `backend/app/infrastructure/collectors/snmp_observation_collector.py` | 从事件关联结果生成 observations |
| `labs/frr-spine-leaf/image/netnexus-link-event-agent.py` | FRR lab 真实链路状态上报 |
| `frontend/src/views/events/*` | Syslog、Trap、Telemetry 拆分页面 |
| `backend/app/application/fact_normalizer.py` | 标准化 BGP/Route/FIB Fact |
| `backend/app/application/rule_engine.py` | 根因和派生异常规则 |
| `backend/app/application/diagnosis_service.py` | 规则归一化和诊断缓存 |
| `backend/app/application/llm_prompt.py` | 多异常 Prompt 约束 |
| `backend/app/application/consistency_service.py` | 第二阶段一致性问题集 |
| `backend/tests/test_phase1.py` | 第二阶段回归测试 |

## 4. 一致性策略

第二阶段的稳定输出由以下机制共同保证：

1. Fact 按固定字段和固定顺序生成。
2. 根因优先级固定为接口 Down。
3. 多异常按 BGP、路由、FIB、业务不可达排序。
4. 故障指纹包含根因设备、根因对象和 Fact 类型集合。
5. 高置信规则命中后，核心输出字段以规则结果为准。
6. 同一故障指纹命中诊断缓存后直接返回同一诊断结果。

## 5. 验证记录

已执行：

```bash
cd backend
.venv/bin/python -m unittest discover tests
```

结果：

```text
Ran 18 tests
OK (skipped=3)
```

跳过的 3 个测试需要真实 LLM 环境变量：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。

## 6. 仍未覆盖

1. 第三阶段三台以上 Spine-Leaf 多设备联动诊断。
2. EventStore 当前仍是进程内内存，生产环境应替换为 Redis、Kafka 或数据库。
3. 缓存仍为进程内字典，生产部署应替换为 Redis。
4. 诊断运行记录、知识库/RAG 和长期报告存储仍未实现。
5. 前端拓扑仍是轻量自绘布局，第三阶段可替换为 AntV G6。
