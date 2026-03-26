from __future__ import annotations

from pathlib import Path

import yaml


class NamespaceResolutionError(ValueError):
    pass


class NamespaceMap:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)

    def resolve(self, service: str, target_branch: str, explicit_namespace: str | None = None) -> str:
        if explicit_namespace:
            return explicit_namespace
        config = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        services = config.get("services", {})
        namespace = services.get(service, {}).get(target_branch)
        if namespace:
            return namespace
        raise NamespaceResolutionError(f"Namespace mapping not found for service={service} target_branch={target_branch}")

