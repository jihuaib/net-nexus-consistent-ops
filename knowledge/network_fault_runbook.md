# 网络故障排障 Runbook

## 接口 Down 引发控制面和转发面异常

当同一时间窗口内出现接口 Down、BGP 邻居 Down、路由缺失、FIB 表项缺失和业务不可达时，应优先确认这些派生异常是否依赖同一个接口或下一跳。如果 BGP、路由、FIB 和业务探测都依赖同一个 Down 接口，排障顺序应从物理链路和端口状态开始，而不是先修改路由协议配置。

建议步骤：

1. 检查本端接口 admin/oper 状态、光模块、线缆、对端端口和链路层错误计数。
2. 恢复接口后观察 BGP 邻居是否重新 Established。
3. BGP 恢复后检查路由表是否重新学习受影响前缀。
4. 路由恢复后检查 FIB 是否完成下发。
5. 最后重新执行业务探测，确认端到端连通性。

## 只有派生异常但缺少链路根因证据

如果当前只有 BGP 邻居 Down、路由缺失、FIB 缺失或业务不可达，但没有 linkDown、ifOperStatus down、Syslog 链路 Down 或等价链路质量证据，不应直接断定接口 Down。此时应补充同一时间窗口内的接口状态、对端端口状态、链路质量、设备日志和 Trap。

建议步骤：

1. 查询本端和对端接口状态。
2. 检查同一时间窗口内是否有 linkDown/linkUp 抖动。
3. 检查 BGP 邻居状态机变化和 hold timer 超时记录。
4. 检查 route withdraw、next-hop 不可达和策略过滤记录。
5. 如果仍无根因证据，将诊断标记为需要补充数据。

## BGP End-of-RIB 信息

FRR 或其他路由软件中的 End-of-RIB 通常表示某个地址族的初始路由发送结束，单独出现时不应视为故障。只有它与邻居 Down、路由撤销、FIB 缺失或业务不可达等异常事实同时出现，才作为上下文参考。

## SNMP Trap 和 Syslog 联合使用

Syslog 往往提供可读事件描述，SNMP Trap 往往提供结构化 OID、ifIndex、ifName、ifOperStatus 等字段。两者同时出现时，应把 Trap 的结构化字段用于定位对象，把 Syslog 文本用于补充证据描述。
