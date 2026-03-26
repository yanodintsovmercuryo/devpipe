from __future__ import annotations

from pathlib import Path

import pytest

from devpipe.integrations.namespace_map import NamespaceMap, NamespaceResolutionError


def test_namespace_map_prefers_explicit_value(tmp_path: Path) -> None:
    config = tmp_path / "namespace-map.yaml"
    config.write_text("services:\n  acquiring:\n    u1: ns-from-file\n", encoding="utf-8")

    mapping = NamespaceMap(config)

    assert mapping.resolve(service="acquiring", stand="u1", explicit_namespace="explicit-ns") == "explicit-ns"


def test_namespace_map_raises_when_mapping_missing(tmp_path: Path) -> None:
    config = tmp_path / "namespace-map.yaml"
    config.write_text("services: {}\n", encoding="utf-8")

    mapping = NamespaceMap(config)

    with pytest.raises(NamespaceResolutionError):
        mapping.resolve(service="acquiring", stand="u9")
