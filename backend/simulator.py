"""
Storage Cluster Simulator + YCSB-compatible Workload Generator.
Deterministic when seed is provided. Simulates distributed storage with N nodes,
partitions, keys, cache, queue, latency dynamics.
"""
from __future__ import annotations
import math
import random
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple


# ---------- YCSB Presets (workload proportions) ----------
YCSB_PRESETS: Dict[str, Dict[str, float]] = {
    "A": {"read": 0.50, "update": 0.50, "insert": 0.0, "scan": 0.0, "rmw": 0.0, "distribution": "zipfian"},
    "B": {"read": 0.95, "update": 0.05, "insert": 0.0, "scan": 0.0, "rmw": 0.0, "distribution": "zipfian"},
    "C": {"read": 1.00, "update": 0.00, "insert": 0.0, "scan": 0.0, "rmw": 0.0, "distribution": "zipfian"},
    "D": {"read": 0.95, "update": 0.0, "insert": 0.05, "scan": 0.0, "rmw": 0.0, "distribution": "latest"},
    "E": {"read": 0.0, "update": 0.0, "insert": 0.05, "scan": 0.95, "rmw": 0.0, "distribution": "zipfian"},
    "F": {"read": 0.50, "update": 0.0, "insert": 0.0, "scan": 0.0, "rmw": 0.50, "distribution": "zipfian"},
}

DISTRIBUTIONS = ["uniform", "zipfian", "latest", "hotkey", "hotspot"]


@dataclass
class NodeState:
    node_id: str
    cpu: float = 0.20
    memory: float = 0.35
    storage: float = 0.42
    read_iops: float = 0.0
    write_iops: float = 0.0
    throughput_mbps: float = 0.0
    queue_depth: float = 0.0
    avg_latency_ms: float = 1.5
    p95_latency_ms: float = 3.0
    p99_latency_ms: float = 5.0
    cache_hit_rate: float = 0.72
    load: float = 0.20
    hotspot_score: float = 0.0
    replicas_hosted: int = 0
    cache_promoted_keys: int = 0
    throttle_pct: float = 0.0
    tier: str = "SSD"  # NVMe, SSD, S3


@dataclass
class WorkloadConfig:
    workload: str = "B"  # A-F or "custom"
    distribution: str = "zipfian"
    read_pct: float = 0.95
    update_pct: float = 0.05
    insert_pct: float = 0.0
    scan_pct: float = 0.0
    rmw_pct: float = 0.0
    record_count: int = 10000
    operation_count: int = 500000
    request_rate: float = 800.0  # ops/sec
    zipfian_theta: float = 0.99
    hot_key_pct: float = 0.01  # top-1% of keys
    hot_key_traffic_share: float = 0.4  # top-1% keys get 40% traffic
    duration_sec: int = 300
    seed: int = 42
    burst_multiplier: float = 1.0
    burst_start: int = -1  # sec index; -1 disabled
    burst_duration: int = 30
    burst_period: int = -1  # if >0, burst repeats every N seconds from burst_start


class ClusterSimulator:
    """Deterministic trace-driven simulator."""

    def __init__(self, num_nodes: int = 4, seed: int = 42, tiers: Optional[List[str]] = None):
        self.num_nodes = num_nodes
        self.seed = seed
        self.rng = random.Random(seed)
        tiers = tiers or ["NVMe", "SSD", "SSD", "S3"]
        self.nodes: Dict[str, NodeState] = {}
        for i in range(num_nodes):
            nid = f"node-{i+1:02d}"
            self.nodes[nid] = NodeState(
                node_id=nid,
                tier=tiers[i % len(tiers)],
                cpu=0.15 + self.rng.random() * 0.1,
                memory=0.30 + self.rng.random() * 0.1,
                storage=0.35 + self.rng.random() * 0.15,
                cache_hit_rate=0.68 + self.rng.random() * 0.1,
            )
        self.t_sec: int = 0
        self.workload: Optional[WorkloadConfig] = None
        # partition->node map (16 partitions, RR)
        self.num_partitions = 16
        self.part_to_node: Dict[int, str] = {}
        node_ids = list(self.nodes.keys())
        for p in range(self.num_partitions):
            self.part_to_node[p] = node_ids[p % num_nodes]
        # Mitigation state
        self.replicas: Dict[int, List[str]] = {p: [self.part_to_node[p]] for p in range(self.num_partitions)}
        self.promoted_keys: Dict[int, str] = {}  # partition -> node cache
        self.in_flight_mitigations: List[Dict] = []
        self.completed_mitigations: List[Dict] = []
        self.aborted_mitigations: List[Dict] = []

    def reset(self):
        self.__init__(self.num_nodes, self.seed)

    def set_workload(self, cfg: WorkloadConfig):
        # If preset chosen, override mix from preset
        if cfg.workload in YCSB_PRESETS:
            p = YCSB_PRESETS[cfg.workload]
            cfg.read_pct = p["read"]
            cfg.update_pct = p["update"]
            cfg.insert_pct = p["insert"]
            cfg.scan_pct = p["scan"]
            cfg.rmw_pct = p["rmw"]
            cfg.distribution = p["distribution"]
        self.workload = cfg
        self.rng = random.Random(cfg.seed)

    # ---------- Distributions ----------
    def _pick_partition(self, cfg: WorkloadConfig) -> Tuple[int, int]:
        """Return (partition_id, key_id)."""
        if cfg.distribution == "uniform":
            k = self.rng.randint(0, cfg.record_count - 1)
        elif cfg.distribution in ("zipfian",):
            # simple zipf approximation: draw uniformly from [0, hot%) with prob 'share'
            if self.rng.random() < cfg.hot_key_traffic_share:
                hot_pool = max(1, int(cfg.record_count * cfg.hot_key_pct))
                k = self.rng.randint(0, hot_pool - 1)
            else:
                k = self.rng.randint(0, cfg.record_count - 1)
        elif cfg.distribution == "latest":
            # bias toward recent inserts
            k = cfg.record_count - 1 - int(abs(self.rng.gauss(0, cfg.record_count * 0.02)))
            k = max(0, min(cfg.record_count - 1, k))
        elif cfg.distribution == "hotkey":
            if self.rng.random() < 0.7:
                k = self.rng.randint(0, max(1, int(cfg.record_count * 0.005)) - 1)
            else:
                k = self.rng.randint(0, cfg.record_count - 1)
        elif cfg.distribution == "hotspot":
            # concentrate on one partition
            partition = 3
            k = partition + self.num_partitions * self.rng.randint(0, cfg.record_count // self.num_partitions - 1)
            return partition, k
        else:
            k = self.rng.randint(0, cfg.record_count - 1)
        partition = k % self.num_partitions
        return partition, k

    def _pick_op(self, cfg: WorkloadConfig) -> str:
        r = self.rng.random()
        c = 0.0
        for op, pct in [("read", cfg.read_pct), ("update", cfg.update_pct),
                         ("insert", cfg.insert_pct), ("scan", cfg.scan_pct), ("rmw", cfg.rmw_pct)]:
            c += pct
            if r < c:
                return op
        return "read"

    def _current_rate(self, cfg: WorkloadConfig) -> float:
        rate = cfg.request_rate
        if cfg.burst_start >= 0:
            if cfg.burst_period and cfg.burst_period > 0:
                in_burst = (self.t_sec - cfg.burst_start) >= 0 and \
                    ((self.t_sec - cfg.burst_start) % cfg.burst_period) < cfg.burst_duration
            else:
                in_burst = cfg.burst_start <= self.t_sec < cfg.burst_start + cfg.burst_duration
            if in_burst:
                rate *= cfg.burst_multiplier
        return rate

    def step(self) -> Dict:
        """Advance simulator by 1 second. Returns aggregated telemetry per node."""
        assert self.workload is not None
        cfg = self.workload
        rate = self._current_rate(cfg)
        ops = int(rate)
        # Per-node counters
        node_ops: Dict[str, Dict[str, float]] = {
            n: {"read": 0, "write": 0, "scan": 0, "cache_hits": 0, "cache_miss": 0,
                "bytes": 0.0}
            for n in self.nodes
        }
        # Distribute ops
        for _ in range(ops):
            partition, key = self._pick_partition(cfg)
            op = self._pick_op(cfg)
            # Route
            node_id = self._route(partition, key)
            # Apply throttle
            n = self.nodes[node_id]
            if n.throttle_pct > 0 and self.rng.random() < n.throttle_pct:
                continue
            # Cache
            hit_prob = min(0.97, n.cache_hit_rate + (0.15 if partition in self.promoted_keys else 0))
            hit = self.rng.random() < hit_prob
            no = node_ops[node_id]
            no["cache_hits" if hit else "cache_miss"] += 1
            if op in ("read", "scan"):
                no["read"] += 1
                no["bytes"] += 1024 if op == "read" else 8192
            elif op in ("update", "insert", "rmw"):
                no["write"] += 1
                no["bytes"] += 2048
            if op == "scan":
                no["scan"] += 1

        # Update node states
        telemetry: Dict[str, Dict] = {}
        tier_capacity = {"NVMe": 1200.0, "SSD": 700.0, "S3": 350.0}
        for nid, n in self.nodes.items():
            no = node_ops[nid]
            reads = no["read"]
            writes = no["write"]
            total = reads + writes
            miss = no["cache_miss"]
            n.read_iops = float(reads)
            n.write_iops = float(writes)
            n.throughput_mbps = no["bytes"] / (1024 * 1024)
            # queue depth: EMA on load pressure (saturates as demand exceeds capacity)
            capacity = tier_capacity.get(n.tier, 700.0)
            util = total / capacity
            overload = max(0.0, util - 0.55)
            n.queue_depth = 0.6 * n.queue_depth + 0.4 * (overload * 14.0 + miss * 0.01)
            # cache hit rate EMA
            hit_rate = (no["cache_hits"] / max(1, total)) if total > 0 else n.cache_hit_rate
            n.cache_hit_rate = 0.85 * n.cache_hit_rate + 0.15 * hit_rate
            # CPU/memory
            n.cpu = min(0.99, 0.12 + 0.95 * min(1.0, util) + 0.02 * math.sin(self.t_sec / 20 + hash(nid) % 7))
            n.memory = min(0.98, 0.25 + 0.6 * min(1.0, util))
            # Latency
            n.avg_latency_ms = 1.0 + 18 * util + n.queue_depth * 1.2
            n.p95_latency_ms = n.avg_latency_ms * (1.8 + n.queue_depth * 0.15)
            n.p99_latency_ms = n.avg_latency_ms * (2.6 + n.queue_depth * 0.3)
            n.load = min(1.0, 0.15 + 1.05 * util)
            # Hotspot score
            n.hotspot_score = min(1.0, 0.4 * n.load + 0.3 * min(1, n.queue_depth / 8) +
                                  0.2 * min(1, n.p99_latency_ms / 80) +
                                  0.1 * max(0, 1 - n.cache_hit_rate))

            telemetry[nid] = {
                "node_id": nid, "t": self.t_sec, "read_iops": n.read_iops, "write_iops": n.write_iops,
                "throughput_mbps": round(n.throughput_mbps, 3),
                "cpu": round(n.cpu, 4), "memory": round(n.memory, 4), "storage": round(n.storage, 4),
                "queue_depth": round(n.queue_depth, 3),
                "avg_latency_ms": round(n.avg_latency_ms, 3),
                "p95_latency_ms": round(n.p95_latency_ms, 3),
                "p99_latency_ms": round(n.p99_latency_ms, 3),
                "cache_hit_rate": round(n.cache_hit_rate, 4),
                "load": round(n.load, 4),
                "hotspot_score": round(n.hotspot_score, 4),
                "tier": n.tier,
                "replicas_hosted": n.replicas_hosted,
                "throttle_pct": n.throttle_pct,
            }

        # Process in-flight mitigations (progressive data transfers)
        active_in_flight = []
        for inf in self.in_flight_mitigations:
            inf["remaining_sec"] -= 1
            src_nid = inf.get("src")
            dest_nid = inf.get("dest")
            src_node = self.nodes.get(src_nid) if src_nid else None
            dest_node = self.nodes.get(dest_nid) if dest_nid else None

            # Apply transient network & disk transfer tax during data copy
            if src_node:
                src_node.load = min(1.0, src_node.load + 0.04)
            if dest_node:
                dest_node.load = min(1.0, dest_node.load + 0.04)

            # Emergency preemption circuit breaker:
            # If source node reaches critical saturation (>0.96) mid-transfer,
            # abort to prevent total I/O starvation
            if src_node and src_node.load >= 0.96:
                inf["status"] = "ABORTED"
                inf["abort_reason"] = "Preempted: source node reached critical saturation (>0.96) during transfer"
                self.aborted_mitigations.append(dict(inf))
                continue

            if inf["remaining_sec"] <= 0:
                # Transfer finished: commit cutover
                inf["status"] = "COMPLETED"
                p = inf["partition"]
                if inf["action"] == "MIGRATE":
                    self.part_to_node[p] = dest_nid
                    self.replicas[p] = [dest_nid] + [r for r in self.replicas.get(p, []) if r != src_nid]
                elif inf["action"] == "REPLICATE":
                    self.replicas.setdefault(p, []).append(dest_nid)
                    if dest_node:
                        dest_node.replicas_hosted += 1
                self.completed_mitigations.append(dict(inf))
            else:
                active_in_flight.append(inf)
        self.in_flight_mitigations = active_in_flight

        self.t_sec += 1
        return telemetry

    def _route(self, partition: int, key: int) -> str:
        replicas = self.replicas.get(partition, [self.part_to_node[partition]])
        # Route to least-loaded replica (simulated)
        return min(replicas, key=lambda nid: self.nodes[nid].load)

    # ---------- Mitigation actions ----------
    def replicate(self, partition: int, destination: Optional[str] = None, duration_sec: float = 0.0) -> Dict:
        current = self.replicas.get(partition, [self.part_to_node[partition]])
        candidates = [n for n in self.nodes if n not in current]
        if not candidates:
            return {"ok": False, "reason": "no_destination"}
        dest = destination if destination in candidates else min(candidates, key=lambda n: self.nodes[n].load)

        if duration_sec <= 0.0:
            self.replicas.setdefault(partition, list(current)).append(dest)
            self.nodes[dest].replicas_hosted += 1
            return {"ok": True, "partition": partition, "destination": dest,
                    "replicas": self.replicas[partition], "status": "COMPLETED", "duration_sec": 0.0}

        in_flight_record = {
            "action": "REPLICATE", "partition": partition, "src": current[0], "dest": dest,
            "duration_sec": duration_sec, "remaining_sec": int(duration_sec), "start_t": self.t_sec, "status": "IN_PROGRESS"
        }
        self.in_flight_mitigations.append(in_flight_record)
        return {"ok": True, "partition": partition, "destination": dest,
                "status": "IN_PROGRESS", "duration_sec": duration_sec}

    def migrate(self, partition: int, destination: Optional[str] = None, duration_sec: float = 0.0) -> Dict:
        src = self.part_to_node[partition]
        candidates = [n for n in self.nodes if n != src]
        if not candidates:
            return {"ok": False, "reason": "no_destination"}
        dest = destination if destination in candidates else min(candidates, key=lambda n: self.nodes[n].load)

        if duration_sec <= 0.0:
            self.part_to_node[partition] = dest
            self.replicas[partition] = [dest] + [r for r in self.replicas.get(partition, []) if r != src]
            return {"ok": True, "partition": partition, "from": src, "to": dest, "status": "COMPLETED", "duration_sec": 0.0}

        in_flight_record = {
            "action": "MIGRATE", "partition": partition, "src": src, "dest": dest,
            "duration_sec": duration_sec, "remaining_sec": int(duration_sec), "start_t": self.t_sec, "status": "IN_PROGRESS"
        }
        self.in_flight_mitigations.append(in_flight_record)
        return {"ok": True, "partition": partition, "from": src, "to": dest, "status": "IN_PROGRESS", "duration_sec": duration_sec}


    def abort_mitigation(self, partition: int) -> Dict:
        aborted = []
        remaining = []
        for inf in self.in_flight_mitigations:
            if inf.get("partition") == partition:
                inf["status"] = "ABORTED"
                inf["abort_reason"] = "Manual/Policy preemption"
                self.aborted_mitigations.append(inf)
                aborted.append(inf)
            else:
                remaining.append(inf)
        self.in_flight_mitigations = remaining
        return {"ok": True, "aborted_count": len(aborted), "aborted": aborted}

    def promote_cache(self, partition: int) -> Dict:
        node_id = self.part_to_node[partition]
        self.promoted_keys[partition] = node_id
        self.nodes[node_id].cache_promoted_keys += 1
        # Boost cache_hit_rate slightly (immediate)
        self.nodes[node_id].cache_hit_rate = min(0.98, self.nodes[node_id].cache_hit_rate + 0.08)
        return {"ok": True, "partition": partition, "node": node_id}

    def throttle(self, node_id: str, pct: float) -> Dict:
        if node_id not in self.nodes:
            return {"ok": False, "reason": "unknown_node"}
        self.nodes[node_id].throttle_pct = max(0.0, min(0.9, pct))
        return {"ok": True, "node": node_id, "throttle_pct": self.nodes[node_id].throttle_pct}

    def snapshot(self) -> Dict:
        return {
            "t": self.t_sec,
            "nodes": [asdict(n) for n in self.nodes.values()],
            "part_to_node": self.part_to_node,
            "replicas": self.replicas,
            "in_flight_mitigations": [dict(x) for x in self.in_flight_mitigations],
            "completed_mitigations": [dict(x) for x in self.completed_mitigations],
            "aborted_mitigations": [dict(x) for x in self.aborted_mitigations],
        }

