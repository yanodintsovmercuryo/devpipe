from __future__ import annotations

import pytest

from devpipe.integrations.kubernetes import KubernetesAdapter, KubernetesTimeoutError


def test_kubernetes_adapter_times_out_when_pods_not_ready() -> None:
    adapter = KubernetesAdapter(client=lambda namespace, service: [{"name": "pod-1", "phase": "Pending"}])

    with pytest.raises(KubernetesTimeoutError):
        adapter.wait_until_ready(namespace="ns", service="svc", attempts=2)
