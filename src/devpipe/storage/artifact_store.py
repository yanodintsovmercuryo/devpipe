from __future__ import annotations

import json
from pathlib import Path


class ArtifactStore:
    def __init__(self, run_dir: str | Path) -> None:
        self.run_dir = Path(run_dir)
        self.artifacts_dir = self.run_dir / "artifacts"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def write_stage_artifacts(self, stage: str, artifacts: dict[str, object]) -> Path:
        target = self.artifacts_dir / f"{stage}.json"
        target.write_text(json.dumps(artifacts, indent=2, sort_keys=True), encoding="utf-8")
        return target

