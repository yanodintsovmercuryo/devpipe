"""Tests for profile loader."""
from __future__ import annotations

from pathlib import Path
import pytest
import yaml

from devpipe.profiles.loader import ProfileDefinition, load_profile, ProfileLoadError


class TestProfileLoader:
    """Test profile loading from files."""

    def test_load_builtin_profile(self, tmp_path: Path):
        """Test loading a builtin profile from repo."""
        # Create a mock builtin profile structure
        profile_dir = tmp_path / "profiles" / "test-builtin"
        profile_dir.mkdir(parents=True)

        pipeline_yml = profile_dir / "pipeline.yml"
        pipeline_yml.write_text(
            """
version: 1
name: test-builtin
inputs:
  task:
    type: string
    default: ""
    custom: true
stages:
  developer:
    runner: codex
    model: medium
    effort: middle
    out:
      code:
        type: string
routing:
  start_stage: developer
  by_stage:
    developer:
      next_stages:
        - stage: developer
          default: true
"""
        )

        # Test via load_profile with a custom builtin base
        profile = load_profile("test-builtin", builtin_base=tmp_path / "profiles")
        assert profile.name == "test-builtin"
        assert "developer" in profile.stages

    def test_load_project_profile(self, tmp_path: Path):
        """Test loading a project profile from .devpipe/profiles/."""
        project_root = tmp_path / "myproject"
        project_root.mkdir()
        profiles_dir = project_root / ".devpipe" / "profiles" / "myprofile"
        profiles_dir.mkdir(parents=True)

        pipeline_yml = profiles_dir / "pipeline.yml"
        pipeline_yml.write_text(
            """
version: 1
name: myprofile
inputs:
  environment:
    type: string
    default: qa
    values: [dev, qa, prod]
    custom: false
stages:
  build:
    runner: codex
    model: medium
    effort: middle
    in:
      env: input.environment
    out:
      artifact:
        type: string
routing:
  start_stage: build
  by_stage:
    build:
      next_stages:
        - stage: build
          default: true
"""
        )

        profile = load_profile("myprofile", project_root=project_root)
        assert profile.name == "myprofile"
        assert profile.defaults is not None
        assert "environment" in profile.inputs
        assert profile.inputs["environment"].type == "string"
        assert profile.inputs["environment"].values == ["dev", "qa", "prod"]

    def test_missing_pipeline_yml_raises_error(self, tmp_path: Path):
        """Test error when pipeline.yml is missing."""
        profile_dir = tmp_path / "profiles" / "broken"
        profile_dir.mkdir(parents=True)

        with pytest.raises(ProfileLoadError, match="pipeline.yml not found"):
            load_profile("broken", builtin_base=tmp_path / "profiles")

    def test_profile_requires_stages_and_routing(self, tmp_path: Path):
        """Test profile must have both stages and routing."""
        profile_dir = tmp_path / "profiles" / "incomplete"
        profile_dir.mkdir(parents=True)

        profile_dir.joinpath("pipeline.yml").write_text(
            """
version: 1
name: incomplete
inputs:
  task:
    type: string
    default: ""
    custom: true
stages:
  developer:
    runner: codex
    model: medium
    effort: middle
    out:
      code:
        type: string
"""
        )

        with pytest.raises(ProfileLoadError, match="missing required sections"):
            load_profile("incomplete", builtin_base=tmp_path / "profiles")

    def test_routing_stages_must_match_existing_stages(self, tmp_path: Path):
        """Test routing must only reference defined stages."""
        profile_dir = tmp_path / "profiles" / "mismatch"
        profile_dir.mkdir(parents=True)

        profile_dir.joinpath("pipeline.yml").write_text(
            """
version: 1
name: mismatch
inputs:
  task:
    type: string
    default: ""
    custom: true
stages:
  defined_stage:
    runner: codex
    model: medium
    effort: middle
    out:
      result:
        type: string
routing:
  start_stage: defined_stage
  by_stage:
    defined_stage:
      next_stages:
        - stage: undefined_stage
          default: true
"""
        )

        with pytest.raises(ProfileLoadError, match="references undefined stage"):
            load_profile("mismatch", builtin_base=tmp_path / "profiles")

    def test_profile_definition_integration(self):
        """Test ProfileDefinition connects stages and routing properly."""
        from devpipe.profiles.stages import ProfileStages
        from devpipe.profiles.routing import RoutingSpec

        # Create minimal valid data
        stages = ProfileStages(
            inputs={
                "task": {"type": "string", "default": "", "custom": True},
            },
            stages={
                "dev": {"runner": "codex", "model": "medium", "effort": "middle", "out": {"code": {"type": "string"}}},
            },
        )

        routing = RoutingSpec(
            start_stage="dev",
            by_stage={
                "dev": {"stage": "dev", "next_stages": [{"stage": "completed", "default": True}]},
                "completed": {"stage": "completed", "next_stages": [{"stage": "completed", "default": True}]},
            },
        )

        profile = ProfileDefinition(
            name="test",
            defaults={"runner": "codex"},
            inputs=stages.inputs,
            stages=stages.stages,
            routing=routing,
        )

        assert profile.name == "test"
        assert profile.stages["dev"].name == "dev"
        assert profile.routing.start_stage == "dev"
        # Verify routing stage exists in stages
        assert profile.routing.start_stage in profile.stages
