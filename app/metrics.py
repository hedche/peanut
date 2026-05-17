from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderMetricsSnapshot:
    """Snapshot of metrics for a single provider."""

    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    retry_count: int = 0

    @property
    def avg_latency_ms(self) -> float:
        if self.request_count == 0:
            return 0.0
        return self.total_latency_ms / self.request_count

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    @property
    def failure_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.failure_count / total


@dataclass
class ProviderMetricsEntry:
    """Thread-safe metrics storage for a single provider."""

    _lock: threading.Lock = field(default_factory=threading.Lock)
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    retry_count: int = 0

    def record_request(self, latency_ms: float, success: bool, retries: int = 0) -> None:
        with self._lock:
            self.request_count += 1
            self.total_latency_ms += latency_ms
            self.retry_count += retries
            if success:
                self.success_count += 1
            else:
                self.failure_count += 1

    def snapshot(self) -> ProviderMetricsSnapshot:
        with self._lock:
            return ProviderMetricsSnapshot(
                request_count=self.request_count,
                success_count=self.success_count,
                failure_count=self.failure_count,
                total_latency_ms=self.total_latency_ms,
                retry_count=self.retry_count,
            )


class MetricsCollector:
    """Central metrics collector for LLM providers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._providers: dict[str, ProviderMetricsEntry] = {}

    def _ensure_provider(self, provider_name: str) -> ProviderMetricsEntry:
        with self._lock:
            if provider_name not in self._providers:
                self._providers[provider_name] = ProviderMetricsEntry()
            return self._providers[provider_name]

    def record_request(
        self,
        provider_name: str,
        latency_ms: float,
        success: bool,
        retries: int = 0,
    ) -> None:
        entry = self._ensure_provider(provider_name)
        entry.record_request(latency_ms, success, retries)

    def get_snapshot(self, provider_name: str) -> ProviderMetricsSnapshot | None:
        with self._lock:
            entry = self._providers.get(provider_name)
            if entry is None:
                return None
            return entry.snapshot()

    def get_all_snapshots(self) -> dict[str, ProviderMetricsSnapshot]:
        with self._lock:
            return {name: entry.snapshot() for name, entry in self._providers.items()}

    def to_prometheus_format(self) -> str:
        """Export metrics in Prometheus text exposition format."""
        lines: list[str] = []
        snapshots = self.get_all_snapshots()

        # Header comments
        lines.append("# HELP llm_requests_total Total LLM requests by provider")
        lines.append("# TYPE llm_requests_total counter")
        for name, snap in snapshots.items():
            lines.append(f'llm_requests_total{{provider="{name}"}} {snap.request_count}')

        lines.append("")
        lines.append("# HELP llm_success_total Successful LLM requests by provider")
        lines.append("# TYPE llm_success_total counter")
        for name, snap in snapshots.items():
            lines.append(f'llm_success_total{{provider="{name}"}} {snap.success_count}')

        lines.append("")
        lines.append("# HELP llm_failures_total Failed LLM requests by provider")
        lines.append("# TYPE llm_failures_total counter")
        for name, snap in snapshots.items():
            lines.append(f'llm_failures_total{{provider="{name}"}} {snap.failure_count}')

        lines.append("")
        lines.append("# HELP llm_latency_ms_total Total latency in milliseconds by provider")
        lines.append("# TYPE llm_latency_ms_total counter")
        for name, snap in snapshots.items():
            lines.append(f'llm_latency_ms_total{{provider="{name}"}} {snap.total_latency_ms:.3f}')

        lines.append("")
        lines.append("# HELP llm_latency_avg_ms Average latency in milliseconds by provider")
        lines.append("# TYPE llm_latency_avg_ms gauge")
        for name, snap in snapshots.items():
            lines.append(f'llm_latency_avg_ms{{provider="{name}"}} {snap.avg_latency_ms:.3f}')

        lines.append("")
        lines.append("# HELP llm_retries_total Total retry attempts by provider")
        lines.append("# TYPE llm_retries_total counter")
        for name, snap in snapshots.items():
            lines.append(f'llm_retries_total{{provider="{name}"}} {snap.retry_count}')

        lines.append("")
        lines.append("# HELP llm_success_rate Success rate (0-1) by provider")
        lines.append("# TYPE llm_success_rate gauge")
        for name, snap in snapshots.items():
            lines.append(f'llm_success_rate{{provider="{name}"}} {snap.success_rate:.4f}')

        return "\n".join(lines)

    def to_json(self) -> dict[str, Any]:
        """Export metrics as JSON-serializable dict."""
        snapshots = self.get_all_snapshots()
        return {
            name: {
                "request_count": snap.request_count,
                "success_count": snap.success_count,
                "failure_count": snap.failure_count,
                "success_rate": round(snap.success_rate, 4),
                "failure_rate": round(snap.failure_rate, 4),
                "avg_latency_ms": round(snap.avg_latency_ms, 3),
                "total_latency_ms": round(snap.total_latency_ms, 3),
                "retry_count": snap.retry_count,
            }
            for name, snap in snapshots.items()
        }


# Global singleton metrics collector
metrics = MetricsCollector()
