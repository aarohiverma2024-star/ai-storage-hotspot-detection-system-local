"""Unit and integration tests for the Buffer-Aware Hierarchical Mitigation Framework."""
import pytest
from decision import choose_action, estimate_action_duration
from simulator import ClusterSimulator, WorkloadConfig


def test_action_duration_estimation():
    """Verify that different actions have distinct, realistic physical durations."""
    cache_dur = estimate_action_duration("CACHE_PROMOTION")
    throttle_dur = estimate_action_duration("THROTTLE")
    rep_dur = estimate_action_duration("REPLICATE", partition_size_mb=500, network_bandwidth_mbps=100)
    mig_dur = estimate_action_duration("MIGRATE", partition_size_mb=500, network_bandwidth_mbps=100)

    # Sub-second actions
    assert cache_dur == 1.0
    assert throttle_dur == 0.2

    # Heavy data transfer actions: MIGRATE > REPLICATE > CACHE_PROMOTION
    assert rep_dur > cache_dur
    assert mig_dur > rep_dur
    assert mig_dur >= 5.0  # At 500MB/100MBps with overhead


def test_positive_buffer_allows_migration():
    """When lead time is long, heavy migration is permitted with HEALTHY buffer."""
    ctx = {
        "probability": 0.85,
        "confidence": 0.90,
        "lead_time_sec": 300.0,
        "node_load": 0.80,
        "cluster_headroom": 0.30,
        "access_concentration": 0.50,
        "read_ratio": 0.60,
        "partition_size_mb": 500.0,
        "network_bandwidth_mbps": 100.0,
        "safety_margin_sec": 15.0,
    }
    decision = choose_action(ctx)
    assert decision["action"] == "MIGRATE"
    assert decision["downgraded"] is False
    assert decision["buffer_status"] == "HEALTHY"
    assert decision["buffer_time_sec"] > 15.0
    assert decision["guardrail_passed"] is True


def test_buffer_exceeded_downgrades_migrate_to_cache():
    """When lead time is too short for migration, read-heavy workload downgrades to CACHE_PROMOTION."""
    # MIGRATE with 500MB on 100MB/s takes ~12-14s; with safety margin 15s, need lead time > 29s
    ctx = {
        "probability": 0.85,
        "confidence": 0.90,
        "lead_time_sec": 18.0,  # 18s is not enough for MIGRATE + 15s margin
        "node_load": 0.80,
        "cluster_headroom": 0.30,
        "access_concentration": 0.50,
        "read_ratio": 0.70,
        "partition_size_mb": 500.0,
        "network_bandwidth_mbps": 100.0,
        "safety_margin_sec": 15.0,
    }
    decision = choose_action(ctx)
    assert decision["action"] == "CACHE_PROMOTION"
    assert decision["original_candidate"] == "MIGRATE"
    assert decision["downgraded"] is True
    assert decision["buffer_status"] == "EXCEEDED_DOWNGRADED"
    assert "Buffer exceeded for MIGRATE" in decision["downgrade_reason"]


def test_buffer_exceeded_downgrades_migrate_to_throttle():
    """When lead time is too short and workload is write-heavy, downgrade to THROTTLE."""
    ctx = {
        "probability": 0.85,
        "confidence": 0.90,
        "lead_time_sec": 12.0,
        "node_load": 0.88,
        "cluster_headroom": 0.30,
        "access_concentration": 0.50,
        "read_ratio": 0.30,  # Write heavy
        "partition_size_mb": 500.0,
        "network_bandwidth_mbps": 100.0,
        "safety_margin_sec": 15.0,
    }
    decision = choose_action(ctx)
    assert decision["action"] == "THROTTLE"
    assert decision["downgraded"] is True
    assert decision["buffer_status"] == "EXCEEDED_DOWNGRADED"


def test_critically_short_lead_time_fallback():
    """When lead time is virtually zero (<2s), hands off to reactive controller."""
    ctx = {
        "probability": 0.85,
        "confidence": 0.90,
        "lead_time_sec": 1.0,
        "node_load": 0.80,
        "cluster_headroom": 0.30,
        "access_concentration": 0.50,
        "read_ratio": 0.70,
        "severity": "HIGH",
    }
    decision = choose_action(ctx)
    assert decision["action"] == "MONITOR"
    assert decision["guardrail_passed"] is False
    assert decision["buffer_status"] == "INSUFFICIENT_TIME"


def test_progressive_in_flight_migration_in_simulator():
    """Test that simulator accurately tracks in-flight migration and cutover."""
    sim = ClusterSimulator(num_nodes=4, seed=42)
    cfg = WorkloadConfig(workload="B", seed=42)
    sim.set_workload(cfg)

    # Initial partition 0 host
    src_node = sim.part_to_node[0]

    # Start 3-second migration
    res = sim.migrate(partition=0, duration_sec=3.0)
    assert res["status"] == "IN_PROGRESS"
    assert len(sim.in_flight_mitigations) == 1
    dest_node = res["to"]

    # Step 1 sec: should still be in progress
    sim.step()
    assert len(sim.in_flight_mitigations) == 1
    assert sim.part_to_node[0] == src_node  # Not yet cut over

    # Step 2 more secs: should complete
    sim.step()
    sim.step()
    assert len(sim.in_flight_mitigations) == 0
    assert len(sim.completed_mitigations) == 1
    assert sim.part_to_node[0] == dest_node  # Cutover complete
