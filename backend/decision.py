"""Decision engine + buffer-aware guardrails.

Implements the Dual-Timeframe Buffer-Aware Hierarchical Mitigation Framework:
- Estimates realistic mitigation transfer duration (tau_action).
- Calculates the buffer safety window: Delta t_buffer = lead_time_sec - tau_action.
- Evaluates against safety margins.
- Executes Graceful Downgrade Policy when buffer deadline is exceeded to prevent
  destructive I/O storms and migration collisions during peak hotspots.
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple


ACTIONS = ["MONITOR", "REPLICATE", "MIGRATE", "CACHE_PROMOTION", "THROTTLE"]


def confidence_level(prob: float) -> str:
    if prob >= 0.80:
        return "HIGH"
    if prob >= 0.55:
        return "MEDIUM"
    return "LOW"


def severity_from_score(score: float) -> str:
    if score >= 0.90:
        return "CRITICAL"
    if score >= 0.75:
        return "HIGH"
    if score >= 0.55:
        return "MEDIUM"
    if score >= 0.35:
        return "LOW"
    return "NORMAL"


def estimate_action_duration(
    action: str,
    partition_size_mb: float = 500.0,
    network_bandwidth_mbps: float = 100.0,
    node_load: float = 0.5,
    dest_load: float = 0.3,
) -> float:
    """
    Estimates realistic execution time in seconds for a storage mitigation action.
    - CACHE_PROMOTION: sub-second (RAM/SSD metadata pinning) ~ 1.0s
    - THROTTLE: sub-second (token-bucket rule application) ~ 0.2s
    - REPLICATE: streaming partition to peer node: (size / bw) * (1 + dest_load) + sync_overhead
    - MIGRATE: streaming partition + double-node handshake: (size / bw) * (1 + src_load + dest_load) + state_handoff
    """
    bw = max(1.0, network_bandwidth_mbps)
    size = max(1.0, partition_size_mb)
    act = action.upper()

    if act == "CACHE_PROMOTION":
        return 1.0
    if act == "THROTTLE":
        return 0.2
    if act == "REPLICATE":
        base_sec = size / bw
        overhead = 2.0  # handshakes & replica register
        dest_penalty = 1.0 + max(0.0, dest_load) * 0.8
        return round(base_sec * dest_penalty + overhead, 2)
    if act == "MIGRATE":
        base_sec = size / bw
        overhead = 4.0  # 2PC partition lock & routing table propagation
        load_penalty = 1.0 + max(0.0, node_load) * 0.6 + max(0.0, dest_load) * 0.6
        return round(base_sec * load_penalty + overhead, 2)
    return 0.0


def choose_action(context: Dict) -> Dict:
    """
    context keys:
      probability, confidence (numeric 0..1), lead_time_sec, severity,
      read_ratio, write_ratio, access_concentration, cache_hit_rate,
      node_load, cluster_headroom (best-load 0..1), migration_cost, replication_cost,
      partition_size_mb, network_bandwidth_mbps, safety_margin_sec

    Guardrails:
      - Minimum confidence to act = 0.55
      - Buffer-aware feasibility check: lead_time_sec >= tau_action + safety_margin_sec
      - Cluster headroom (best_load) must be < 0.70 for replication/migration
      - Graceful downgrade to fast sub-second mitigations if buffer time is exceeded
    """
    prob = context.get("probability", 0)
    conf = context.get("confidence", prob)
    lead = max(0.0, float(context.get("lead_time_sec", 0.0)))
    severity = context.get("severity", "NORMAL")
    read_ratio = float(context.get("read_ratio", 0.5))
    concentration = float(context.get("access_concentration", 0.5))
    cache_hit = float(context.get("cache_hit_rate", 0.7))
    node_load = float(context.get("node_load", 0.5))
    headroom = float(context.get("cluster_headroom", 0.5))

    # Cluster physical parameters for duration calculation
    partition_size_mb = float(context.get("partition_size_mb", 500.0))
    network_bandwidth_mbps = float(context.get("network_bandwidth_mbps", 100.0))
    safety_margin = float(context.get("safety_margin_sec", 15.0))

    # 1. Confidence Guardrail
    if conf < 0.55:
        return {
            "action": "MONITOR",
            "original_candidate": "MONITOR",
            "downgraded": False,
            "downgrade_reason": None,
            "reason": "Confidence below guardrail (0.55).",
            "confidence": conf,
            "cost": 0.0,
            "benefit": 0.0,
            "affected_layer": "NONE",
            "guardrail_passed": False,
            "lead_time_sec": lead,
            "estimated_duration_sec": 0.0,
            "buffer_time_sec": lead,
            "safety_margin_sec": safety_margin,
            "buffer_status": "HEALTHY",
        }

    # 2. Select initial optimal candidate action based on workload patterns
    candidate_action = "MONITOR"
    layer = "NONE"
    cost = 0.0
    benefit = 0.0
    candidate_reasons: List[str] = []

    # Cache promotion: read-heavy + low cache hit
    if read_ratio >= 0.75 and cache_hit < 0.80 and concentration >= 0.30:
        candidate_action = "CACHE_PROMOTION"
        layer = "CACHE"
        cost = 5 + 20 * (1 - cache_hit)
        benefit = 30 * concentration + 20 * (1 - cache_hit)
        candidate_reasons.append(f"Read ratio {read_ratio:.2f}, cache hit {cache_hit:.2f} — promote hot keys.")
    # Migration: overloaded node + destination available
    elif node_load >= 0.75 and headroom < 0.55 and concentration >= 0.40:
        candidate_action = "MIGRATE"
        layer = "NODE"
        cost = 15 + 20 * node_load
        benefit = 40 * (node_load - headroom)
        candidate_reasons.append(f"Node load {node_load:.2f} > 0.75, headroom {headroom:.2f} available.")
    # Replication: read heavy + moderate load
    elif read_ratio >= 0.60 and node_load >= 0.60 and headroom < 0.60:
        candidate_action = "REPLICATE"
        layer = "PARTITION"
        cost = 8 + 12 * node_load
        benefit = 35 * (read_ratio - 0.5) + 15 * concentration
        candidate_reasons.append("Read-heavy hotspot: replicate hot partition to less-loaded node.")
    # Throttle: write-heavy overload
    elif node_load >= 0.85 and read_ratio < 0.5:
        candidate_action = "THROTTLE"
        layer = "NODE"
        cost = 25
        benefit = 30 * node_load
        candidate_reasons.append("Write-heavy overload and no read replication benefit.")
    else:
        return {
            "action": "MONITOR",
            "original_candidate": "MONITOR",
            "downgraded": False,
            "downgrade_reason": None,
            "reason": "No guardrail-safe mitigation strictly indicated.",
            "confidence": conf,
            "cost": 0.0,
            "benefit": 0.0,
            "affected_layer": layer,
            "guardrail_passed": True,
            "lead_time_sec": lead,
            "estimated_duration_sec": 0.0,
            "buffer_time_sec": lead,
            "safety_margin_sec": safety_margin,
            "buffer_status": "HEALTHY",
        }

    # 3. Buffer-Aware Feasibility Validation & Graceful Downgrade Policy
    est_duration = estimate_action_duration(
        candidate_action,
        partition_size_mb=partition_size_mb,
        network_bandwidth_mbps=network_bandwidth_mbps,
        node_load=node_load,
        dest_load=headroom,
    )
    buffer_time = round(lead - est_duration, 2)

    # Check if lead time is severely depleted (< 2s)
    if lead < 2.0 and severity != "CRITICAL":
        return {
            "action": "MONITOR",
            "original_candidate": candidate_action,
            "downgraded": True,
            "downgrade_reason": f"Lead time ({lead:.1f}s) virtually zero; handing off to reactive controller.",
            "reason": "Lead time too short; letting reactive controller handle.",
            "confidence": conf,
            "cost": 0.0,
            "benefit": 0.0,
            "affected_layer": "NONE",
            "guardrail_passed": False,
            "lead_time_sec": lead,
            "estimated_duration_sec": est_duration,
            "buffer_time_sec": buffer_time,
            "safety_margin_sec": safety_margin,
            "buffer_status": "INSUFFICIENT_TIME",
        }

    effective_action = candidate_action
    downgraded = False
    downgrade_reason = None
    buffer_status = "HEALTHY" if buffer_time >= safety_margin else ("TIGHT" if buffer_time >= 0 else "EXCEEDED_DOWNGRADED")

    # If buffer time exceeds safety deadline (buffer_time < safety_margin):
    # Do NOT run heavy data movement during the oncoming hotspot!
    if buffer_time < safety_margin:
        downgraded = True

        if candidate_action == "MIGRATE":
            # Attempt 1: Check if REPLICATE fits in remaining lead time (for read-heavy traffic)
            rep_duration = estimate_action_duration(
                "REPLICATE",
                partition_size_mb=partition_size_mb,
                network_bandwidth_mbps=network_bandwidth_mbps,
                node_load=node_load,
                dest_load=headroom,
            )
            if read_ratio >= 0.60 and (lead - rep_duration) >= safety_margin:
                effective_action = "REPLICATE"
                layer = "PARTITION"
                est_duration = rep_duration
                buffer_time = round(lead - est_duration, 2)
                cost = 8 + 12 * node_load
                benefit = 35 * (read_ratio - 0.5) + 15 * concentration
                downgrade_reason = (
                    f"Buffer exceeded for MIGRATE (req {estimate_action_duration('MIGRATE'):.1f}s, lead {lead:.1f}s). "
                    f"Downgraded to faster REPLICATE (req {rep_duration:.1f}s, buffer {buffer_time:.1f}s)."
                )
                buffer_status = "TIGHT" if buffer_time < safety_margin else "HEALTHY"
            elif read_ratio >= 0.50:
                # Attempt 2: Fast-path Cache Promotion
                effective_action = "CACHE_PROMOTION"
                layer = "CACHE"
                est_duration = estimate_action_duration("CACHE_PROMOTION")
                buffer_time = round(lead - est_duration, 2)
                cost = 5 + 20 * (1 - cache_hit)
                benefit = 30 * concentration + 20 * (1 - cache_hit)
                downgrade_reason = (
                    f"Buffer exceeded for MIGRATE (req {estimate_action_duration('MIGRATE'):.1f}s, lead {lead:.1f}s). "
                    f"Downgraded to sub-second CACHE_PROMOTION to prevent I/O transfer storm."
                )
                buffer_status = "EXCEEDED_DOWNGRADED"
            else:
                # Attempt 3: Fast-path Throttle / Rate limit
                effective_action = "THROTTLE"
                layer = "NODE"
                est_duration = estimate_action_duration("THROTTLE")
                buffer_time = round(lead - est_duration, 2)
                cost = 25
                benefit = 30 * node_load
                downgrade_reason = (
                    f"Buffer exceeded for MIGRATE and write-heavy. "
                    f"Downgraded to sub-second THROTTLE ({est_duration:.1f}s) to shed oncoming peak load."
                )
                buffer_status = "EXCEEDED_DOWNGRADED"

        elif candidate_action == "REPLICATE":
            # Downgrade REPLICATE to CACHE_PROMOTION or THROTTLE
            if read_ratio >= 0.50:
                effective_action = "CACHE_PROMOTION"
                layer = "CACHE"
                est_duration = estimate_action_duration("CACHE_PROMOTION")
                buffer_time = round(lead - est_duration, 2)
                cost = 5 + 20 * (1 - cache_hit)
                benefit = 30 * concentration + 20 * (1 - cache_hit)
                downgrade_reason = (
                    f"Buffer exceeded for REPLICATE (lead {lead:.1f}s). "
                    f"Downgraded to sub-second CACHE_PROMOTION."
                )
                buffer_status = "EXCEEDED_DOWNGRADED"
            else:
                effective_action = "THROTTLE"
                layer = "NODE"
                est_duration = estimate_action_duration("THROTTLE")
                buffer_time = round(lead - est_duration, 2)
                cost = 25
                benefit = 30 * node_load
                downgrade_reason = (
                    f"Buffer exceeded for REPLICATE (lead {lead:.1f}s). "
                    f"Downgraded to sub-second THROTTLE."
                )
                buffer_status = "EXCEEDED_DOWNGRADED"

        elif candidate_action in ("CACHE_PROMOTION", "THROTTLE"):
            # Already sub-second actions
            if lead < est_duration:
                if severity == "CRITICAL":
                    effective_action = "THROTTLE"
                    est_duration = 0.2
                    buffer_status = "CRITICAL_FALLBACK"
                    downgrade_reason = "Lead time near zero during CRITICAL severity; applying emergency throttle."
                else:
                    return {
                        "action": "MONITOR",
                        "original_candidate": candidate_action,
                        "downgraded": True,
                        "downgrade_reason": f"Lead time ({lead:.1f}s) insufficient even for sub-second action.",
                        "reason": "Lead time too short; letting reactive controller handle.",
                        "confidence": conf,
                        "cost": 0.0,
                        "benefit": 0.0,
                        "affected_layer": "NONE",
                        "guardrail_passed": False,
                        "lead_time_sec": lead,
                        "estimated_duration_sec": est_duration,
                        "buffer_time_sec": buffer_time,
                        "safety_margin_sec": safety_margin,
                        "buffer_status": "INSUFFICIENT_TIME",
                    }

    full_reason = (" ".join(candidate_reasons) if not downgraded else downgrade_reason) or f"{effective_action} suggested."

    return {
        "action": effective_action,
        "original_candidate": candidate_action,
        "downgraded": downgraded,
        "downgrade_reason": downgrade_reason,
        "reason": full_reason,
        "confidence": conf,
        "cost": round(cost, 2),
        "benefit": round(benefit, 2),
        "affected_layer": layer,
        "guardrail_passed": True,
        "lead_time_sec": lead,
        "estimated_duration_sec": est_duration,
        "buffer_time_sec": buffer_time,
        "safety_margin_sec": safety_margin,
        "buffer_status": buffer_status,
    }
