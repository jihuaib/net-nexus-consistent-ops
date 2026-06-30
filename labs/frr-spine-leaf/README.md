# FRR SNMP/LLDP Spine-Leaf Lab

这个 lab 用四台 `FRR + snmpd + LLDP-MIB` 容器模拟最小 Spine-Leaf 三层网络和一台管理网可达但业务链路不联通的孤立设备，用于验证拓扑发现不是前端固定写死，并且发现链路尽量接近真实设备 SNMP/LLDP-MIB。

容器内还运行一个轻量链路事件 agent。它只监听真实 `/sys/class/net/eth*` 状态变化；当你执行 `ip link set eth1 down/up` 时，会向后端发出：

```text
UDP Syslog:     host.docker.internal:1514
SNMPv2 Trap:    host.docker.internal:1162
```

这不是页面或脚本模拟投递事件，而是 FRR lab 设备侧基于真实接口状态变化发出的上报。

接口名固定如下，避免 Docker 网络接入顺序变化导致误断管理网：

```text
mgmt0  管理/上报网络，不要用于故障注入
eth1   leaf-01/leaf-02 到 spine 的业务链路
eth2   spine-01 到 leaf-02 的第二条业务链路
```

## 拓扑

```text
leaf-01 -- 10.0.11.0/29 -- spine-01 -- 10.0.12.0/29 -- leaf-02

isolated-01 仅连接 Docker 内部管理网，不连接 `spine_leaf_1` 或 `spine_leaf_2`。
后端通过本机 seed targets 原生 SNMP walk 访问这些容器。
```

| 设备 | 角色 | 管理地址 | ASN |
|---|---|---:|---:|
| `spine-01` | spine | `127.0.0.1:11611` | `65000` |
| `leaf-01` | leaf | `127.0.0.1:11612` | `65101` |
| `leaf-02` | leaf | `127.0.0.1:11613` | `65102` |
| `isolated-01` | router | `127.0.0.1:11614` | `65200` |

## 启动

```bash
cd /Users/jihuaibin/code/NetNexusConsistentOps
./scripts/start_frr_lab.sh
```

默认 FRR lab 不指定 Docker platform，Docker 会按当前宿主机架构拉取基础镜像。

如果 `frrouting/frr:latest` 没有当前架构的镜像，换成支持当前架构的 FRR 基础镜像：

```bash
FRR_BASE_IMAGE=<your-frr-image> ./scripts/start_frr_lab.sh
```

查看 BGP：

```bash
docker exec netnexus-spine-01 vtysh -c 'show bgp summary'
docker exec netnexus-spine-01 vtysh -c 'show bgp summary json'
```

验证 SNMP：

```bash
curl -X POST http://127.0.0.1:8010/api/topology/discovery-config \
  -H 'Content-Type: application/json' \
  -d '{"targets":["127.0.0.1:11611","127.0.0.1:11612","127.0.0.1:11613","127.0.0.1:11614"],"scan_cidrs":[],"community":"public"}'
```

## 通过后端发现拓扑

先启动后端：

```bash
./scripts/start_backend.sh
```

先配置 SNMP/LLDP-MIB 发现入口。FRR 本地实验环境使用 seed targets，真实设备可以改为管理网段 CIDR：

```bash
curl -X POST http://127.0.0.1:8010/api/topology/discovery-config \
  -H 'Content-Type: application/json' \
  -d '{"targets":["127.0.0.1:11611","127.0.0.1:11612","127.0.0.1:11613","127.0.0.1:11614"],"scan_cidrs":[],"community":"public"}'
```

触发 SNMP/LLDP-MIB 发现：

```bash
curl -X POST http://127.0.0.1:8010/api/topology/discover \
  -H 'Content-Type: application/json' \
  -d '{"mode":"snmp_lldp"}'
```

预期结果包含：

```json
{
  "discovery": {
    "mode": "snmp_lldp",
    "node_count": 4,
    "edge_count": 2,
    "group_count": 2,
    "target_source": "cidr_scan"
  }
}
```

## 故障注入

示例：断开 `leaf-01` 到 `spine-01` 的实验链路。

```bash
docker exec netnexus-leaf-01 ip link set eth1 down
```

后端启动时默认监听 `0.0.0.0:1514/udp` 和 `0.0.0.0:1162/udp`。前端左侧进入 `Syslog` 和 `Trap` 页面，应能看到 `leaf-01 eth1` 的 linkDown 上报。

恢复：

```bash
docker exec netnexus-leaf-01 ip link set eth1 up
```

## 与真实设备切换关系

SNMP/LLDP provider 是真实设备切换优先路径：

```text
TopologyService
  -> SnmpLldpTopologyProvider
  -> SNMP sysName / IF-MIB / LLDP-MIB
  -> nodes / edges / discovery
```

真实 H3C 设备接入时，优先复用同一个 provider：

```text
POST /api/topology/discover
{
  "mode": "snmp_lldp",
  "options": {
    "scan_cidrs": ["真实设备管理网段 CIDR"],
    "targets": ["可选 seed IP"],
    "community": "真实 community"
  }
}
```

如果后续需要 NETCONF/gNMI 或 BGP-LS/BMP，再新增 provider；前端、Agent 和一致性测试继续消费同一份 `nodes/edges/discovery`，不需要再改页面结构。

## 停止

```bash
./scripts/stop_frr_lab.sh
```
