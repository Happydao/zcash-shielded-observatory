#!/usr/bin/env python3
"""Build the static dataset for Zcash Shielded Observatory.

ZcashInfo is the public supply/history source. An authenticated Zebra 6+ RPC
can be supplied through ZEBRA_RPC_URL (and optionally ZEBRA_RPC_USER/PASSWORD).
No RPC credentials or URLs are written to the public dataset.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://api.zcashinfo.com/api/v1"
ACTIVATION_HEIGHT = 3_428_143
ACTIVATION_ESTIMATE = "2026-07-28T12:00:00Z"
ROOT = Path(__file__).resolve().parents[1]
OUTFILE = ROOT / "data" / "data.json"
ZEBRA_HISTORY = ROOT / "data" / "ironwood-history.json"
POOL_FIELDS = {
    "transparent": "transparent_zatoshis",
    "sapling": "sapling_zatoshis",
    "orchard": "orchard_zatoshis",
    "sprout": "sprout_zatoshis",
    "lockbox": "lockbox_zatoshis",
    "ironwood": "ironwood_zatoshis",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def optional_int(value):
    return None if value is None else int(value)


def request_json(url: str, *, payload: dict | None = None, headers: dict | None = None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=body, headers={
        "Accept": "application/json",
        "User-Agent": "zcash-shielded-observatory/2.0",
        **({"Content-Type": "application/json"} if body else {}),
        **(headers or {}),
    })
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error from {url}: {exc.reason}") from exc


def fetch_zcashinfo(path: str):
    return request_json(f"{BASE_URL}{path}")


class ZebraClient:
    def __init__(self, url: str, user: str | None = None, password: str | None = None):
        self.url = url
        self.headers = {}
        if user is not None:
            token = base64.b64encode(f"{user}:{password or ''}".encode()).decode()
            self.headers["Authorization"] = f"Basic {token}"

    def call(self, method: str, params: list | None = None):
        result = request_json(self.url, payload={
            "jsonrpc": "2.0", "id": method, "method": method, "params": params or []
        }, headers=self.headers)
        if result.get("error"):
            raise RuntimeError(f"Zebra {method}: {result['error']}")
        return result.get("result")


def find_pool(value_pools: list[dict] | None, pool_id: str):
    return next((pool for pool in (value_pools or []) if pool.get("id") == pool_id), None)


def normalize_history(points: list[dict]) -> list[dict]:
    normalized = []
    for point in points:
        row = {"height": int(point.get("height", 0)), "timestamp": int(point.get("timestamp", 0))}
        for pool, field in POOL_FIELDS.items():
            if field in point:
                row[pool] = int(point[field])
        normalized.append(row)
    return sorted(normalized, key=lambda row: row["height"])


def merge_history(*series: list[dict]) -> list[dict]:
    """Merge resolutions by height, preferring the later (usually denser) source."""
    merged = {}
    for rows in series:
        for row in rows:
            merged[int(row["height"])] = row
    return [merged[height] for height in sorted(merged)]


def closest_at_or_before(history: list[dict], timestamp: int):
    return next((p for p in reversed(history) if p["timestamp"] <= timestamp), None)


def net_change(history: list[dict], pool: str, seconds: int):
    if not history:
        return None
    current = history[-1]
    reference = closest_at_or_before(history, current["timestamp"] - seconds)
    if not reference or pool not in current or pool not in reference:
        return None
    return current[pool] - reference[pool]


def change_since_height(history: list[dict], pool: str, height: int):
    points = [row for row in history if row.get("height", 0) >= height and row.get(pool) is not None]
    if len(points) < 2:
        return None
    return points[-1][pool] - points[0][pool]


def change_bps(current: int | None, delta: int | None):
    if current is None or delta is None:
        return None
    reference = current - delta
    return round(delta * 1_000_000 / reference) if reference else None


def pool_metrics(current: dict, history: list[dict], pool: str, shielded_total: int):
    value = optional_int(current.get(POOL_FIELDS[pool]))
    day = net_change(history, pool, 86_400)
    week = net_change(history, pool, 7 * 86_400)
    return {
        "balance_zatoshis": value,
        "shielded_share_bps": round(value * 1_000_000 / shielded_total) if value is not None and shielded_total else None,
        "supply_share_bps": None,
        "net_change_24h_zatoshis": day,
        "net_change_24h_bps": change_bps(value, day),
        "net_change_7d_zatoshis": week,
        "net_change_7d_bps": change_bps(value, week),
        "net_change_since_activation_zatoshis": change_since_height(history, pool, ACTIVATION_HEIGHT),
        "flow_semantics": "net_balance_change",
    }


def load_ironwood_history() -> list[dict]:
    if not ZEBRA_HISTORY.exists():
        return []
    data = json.loads(ZEBRA_HISTORY.read_text())
    return data if isinstance(data, list) else []


def save_ironwood_history(rows: list[dict]):
    atomic_write(ZEBRA_HISTORY, rows)


def backfill_ironwood(zebra: ZebraClient, tip: int, rows: list[dict]) -> list[dict]:
    by_height = {int(row["height"]): row for row in rows}
    # Re-check a short canonical window on every run. If a stored hash no longer
    # matches, discard that height and every descendant before resuming.
    for height in sorted(by_height)[-12:]:
        block = zebra.call("getblock", [height, 1])
        if block.get("hash") != by_height[height].get("block_hash"):
            by_height = {h: row for h, row in by_height.items() if h < height}
            break
    start = max(ACTIVATION_HEIGHT, max(by_height, default=ACTIVATION_HEIGHT - 1) + 1)
    for height in range(start, tip + 1):
        block = zebra.call("getblock", [height, 1])
        pool = find_pool(block.get("valuePools"), "ironwood")
        if not pool or pool.get("chainValueZat") is None:
            break
        by_height[height] = {
            "height": height,
            "timestamp": int(block.get("time", 0)),
            "block_hash": block.get("hash"),
            "balance_zatoshis": int(pool["chainValueZat"]),
            "value_delta_zatoshis": optional_int(pool.get("valueDeltaZat")),
        }
    return [by_height[h] for h in sorted(by_height)]


def derive_ironwood(zebra: ZebraClient | None, tip: int, zcashinfo_pools: dict):
    public_value = optional_int(zcashinfo_pools.get("ironwood_zatoshis"))
    state = {
        "status": "pending_activation" if tip < ACTIVATION_HEIGHT else "activation_reached_waiting_data",
        "supported": public_value is not None,
        "active": False,
        "monitored": public_value is not None,
        "balance_zatoshis": public_value,
        "tree_present": False,
        "source": "zcashinfo" if public_value is not None else None,
        "last_error": None,
    }
    history = load_ironwood_history()
    if zebra is None:
        return state, history
    try:
        info = zebra.call("getblockchaininfo")
        tip = int(info.get("blocks", tip))
        pool = find_pool(info.get("valuePools"), "ironwood")
        state["supported"] = pool is not None
        state["monitored"] = bool(pool and pool.get("monitored"))
        if pool and pool.get("chainValueZat") is not None:
            state["balance_zatoshis"] = int(pool["chainValueZat"])
            state["source"] = "zebra_rpc"
        if tip < ACTIVATION_HEIGHT:
            state["status"] = "supported_pre_activation" if pool else "pending_activation"
        else:
            try:
                tree = zebra.call("z_gettreestate", [-1])
                state["tree_present"] = bool(tree and tree.get("ironwood") is not None)
            except RuntimeError:
                pass
            if state["monitored"]:
                state["status"] = "backfilling"
                history = backfill_ironwood(zebra, tip, history)
                save_ironwood_history(history)
                state["status"] = "active" if history and history[-1]["height"] >= tip else "backfilling"
                state["active"] = state["status"] == "active"
    except Exception as exc:
        state["status"] = "source_error"
        # The RPC URL may be private. Publish an actionable class, never the
        # original exception string or endpoint.
        state["last_error"] = f"{type(exc).__name__}: Zebra RPC unavailable"
    return state, history


def build_dataset(pools: dict, dashboard: dict, history: list[dict], zebra: ZebraClient | None):
    info = dashboard.get("info", {})
    tip = int(info.get("chain_tip") or info.get("best_block") or 0)
    ironwood, ironwood_history = derive_ironwood(zebra, tip, pools)
    balances = {pool: optional_int(pools.get(field)) for pool, field in POOL_FIELDS.items()}
    if ironwood["balance_zatoshis"] is not None:
        balances["ironwood"] = ironwood["balance_zatoshis"]
    shielded_total = sum(balances[p] or 0 for p in ("sprout", "sapling", "orchard", "ironwood"))
    transparent = balances["transparent"] or 0
    total_supply = optional_int(pools.get("total_supply_zatoshis")) or 0
    accounted = sum(value or 0 for value in balances.values())
    latest_ts = history[-1]["timestamp"] if history else int(utc_now().timestamp())
    blocks_remaining = max(0, ACTIVATION_HEIGHT - tip)
    status = ironwood["status"]
    sapling_metrics = pool_metrics(pools, history, "sapling", shielded_total)
    orchard_metrics = pool_metrics(pools, history, "orchard", shielded_total)
    for metrics in (sapling_metrics, orchard_metrics):
        metrics["supply_share_bps"] = round(metrics["balance_zatoshis"] * 1_000_000 / total_supply) if total_supply and metrics["balance_zatoshis"] is not None else None
    shielded_day = sum(net_change(history, p, 86_400) or 0 for p in ("sprout", "sapling", "orchard"))
    transparent_day = net_change(history, "transparent", 86_400)
    transparent_week = net_change(history, "transparent", 7 * 86_400)
    ironwood_points = [
        {"timestamp": row["timestamp"], "ironwood": row["balance_zatoshis"]}
        for row in ironwood_history
    ]
    ironwood_day = net_change(ironwood_points, "ironwood", 86_400)
    ironwood_week = net_change(ironwood_points, "ironwood", 7 * 86_400)
    return {
        "schema_version": 2,
        "generated_at": utc_now().isoformat(),
        "network": "main",
        "project": {"name": "Zcash Shielded Observatory", "focus": ["sapling", "orchard", "ironwood"]},
        "activation": {
            "height": ACTIVATION_HEIGHT,
            "estimated_at": ACTIVATION_ESTIMATE,
            "current_height": tip,
            "blocks_remaining": blocks_remaining,
            "progress_bps": min(1_000_000, round(tip * 1_000_000 / ACTIVATION_HEIGHT)),
            "reached": tip >= ACTIVATION_HEIGHT,
        },
        "health": {
            "status": "stale" if int(utc_now().timestamp()) - latest_ts > 7_200 else "ok",
            "chain_status": info.get("status", "unknown"),
            "tip_hash": info.get("best_block_hash"),
            "last_chain_timestamp": latest_ts,
        },
        "supply": {
            "total_zatoshis": total_supply,
            "shielded_zatoshis": shielded_total,
            "transparent_zatoshis": transparent,
            "legacy_sprout_zatoshis": balances["sprout"],
            "lockbox_zatoshis": balances["lockbox"],
            "accounting_difference_zatoshis": total_supply - accounted,
            "shielded_share_bps": round(shielded_total * 1_000_000 / total_supply) if total_supply else None,
            "transparent_share_bps": round(transparent * 1_000_000 / total_supply) if total_supply else None,
            "net_change_24h_zatoshis": shielded_day,
            "net_change_24h_bps": change_bps(shielded_total, shielded_day),
            "net_change_7d_zatoshis": sum(net_change(history, p, 7 * 86_400) or 0 for p in ("sprout", "sapling", "orchard")),
            "transparent_net_change_24h_zatoshis": transparent_day,
            "transparent_net_change_24h_bps": change_bps(transparent, transparent_day),
            "transparent_net_change_7d_zatoshis": transparent_week,
            "transparent_net_change_7d_bps": change_bps(transparent, transparent_week),
        },
        "pools": {
            "sapling": sapling_metrics,
            "orchard": orchard_metrics,
            "ironwood": {
                **ironwood,
                "net_change_24h_zatoshis": ironwood_day,
                "net_change_24h_bps": change_bps(ironwood["balance_zatoshis"], ironwood_day),
                "net_change_7d_zatoshis": ironwood_week,
                "net_change_7d_bps": change_bps(ironwood["balance_zatoshis"], ironwood_week),
                "net_change_since_activation_zatoshis": (
                    ironwood_history[-1]["balance_zatoshis"] - ironwood_history[0]["balance_zatoshis"]
                    if len(ironwood_history) > 1 else None
                ),
                "supply_share_bps": (
                    round(ironwood["balance_zatoshis"] * 1_000_000 / total_supply)
                    if total_supply and ironwood["balance_zatoshis"] is not None else None
                ),
                "flow_semantics": "per_block_net_delta" if ironwood_history else "not_available",
            },
        },
        "history": history,
        "ironwood_history": ironwood_history,
        "sources": [
            {"id": "zcashinfo", "role": "supply_and_history", "status": "available", "public": True},
            {"id": "zebra_rpc", "role": "ironwood_primary", "status": "configured" if zebra else "not_configured", "public": False},
        ],
        "methodology": {
            "shielded_definition": "sprout + sapling + orchard + ironwood",
            "primary_focus": "sapling + orchard + ironwood",
            "gross_flows_available": False,
            "flow_note": "Snapshot differences and valueDeltaZat are net pool changes, not provable gross inflow/outflow or destinations.",
            "ironwood_state": status,
        },
    }


def stable_payload(dataset: dict):
    return {key: value for key, value in dataset.items() if key != "generated_at"}


def atomic_write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as tmp:
        tmp.write(text)
        temp_path = Path(tmp.name)
    temp_path.replace(path)


def main() -> int:
    pools = fetch_zcashinfo("/coin-pools")
    dashboard = fetch_zcashinfo("/dashboard")
    history = merge_history(
        normalize_history(fetch_zcashinfo("/coin-pools/history?range=all")),
        normalize_history(fetch_zcashinfo("/coin-pools/history?range=1m")),
    )
    url = os.getenv("ZEBRA_RPC_URL")
    zebra = ZebraClient(url, os.getenv("ZEBRA_RPC_USER"), os.getenv("ZEBRA_RPC_PASSWORD")) if url else None
    dataset = build_dataset(pools, dashboard, history, zebra)
    if OUTFILE.exists() and stable_payload(json.loads(OUTFILE.read_text())) == stable_payload(dataset):
        print("Dataset unchanged")
        return 0
    atomic_write(OUTFILE, dataset)
    print(f"Wrote {OUTFILE.relative_to(ROOT)} at height {dataset['activation']['current_height']}")
    print(f"Ironwood state: {dataset['pools']['ironwood']['status']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"update failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
