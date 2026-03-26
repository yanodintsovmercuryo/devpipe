from __future__ import annotations


class KubernetesTimeoutError(RuntimeError):
    pass


class KubernetesAdapter:
    def __init__(self, client) -> None:
        self.client = client

    def wait_until_ready(self, namespace: str, service: str, attempts: int = 10) -> list[dict[str, object]]:
        last_seen = []
        for _ in range(attempts):
            pods = self.client(namespace, service)
            last_seen = pods
            if pods and all(pod.get("phase") == "Running" for pod in pods):
                return pods
        raise KubernetesTimeoutError(f"Pods for {service} in {namespace} did not reach Running state: {last_seen}")

