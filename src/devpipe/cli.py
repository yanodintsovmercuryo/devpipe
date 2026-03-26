from __future__ import annotations

import argparse
import json
from pathlib import Path

from devpipe.app import RunConfig, build_default_app
from devpipe.roles.loader import load_roles


class CommaSeparatedTags(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        current = list(getattr(namespace, self.dest, []) or [])
        for part in values.split(","):
            tag = part.strip()
            if tag and tag not in current:
                current.append(tag)
        setattr(namespace, self.dest, current)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="devpipe", description="devpipe")
    subparsers = parser.add_subparsers(dest="command", required=False)

    run_parser = subparsers.add_parser("run", help="Run full pipeline")
    run_parser.add_argument("--task-id", default=None)
    run_parser.add_argument("--task", required=True)
    run_parser.add_argument("--runner", required=True, choices=["codex", "claude"])
    run_parser.add_argument("--roles-dir", default=None)
    run_parser.add_argument("--runs-dir", default=None)
    run_parser.add_argument("--target-branch")
    run_parser.add_argument("--param", dest="params", action="append", metavar="KEY=VALUE",
                            help="Extra tag param, e.g. --param dataset=s4-3ds")
    run_parser.add_argument("--namespace")
    run_parser.add_argument("--service", default="acquiring")
    run_parser.add_argument("--tag", dest="tags", action=CommaSeparatedTags, default=[])
    run_parser.add_argument("--first-role", default=None, choices=["architect", "developer", "test_developer", "qa_local", "release", "qa_stand"])
    run_parser.add_argument("--last-role", default=None, choices=["architect", "developer", "test_developer", "qa_local", "release", "qa_stand"])

    inspect_parser = subparsers.add_parser("inspect", help="Inspect available roles")
    inspect_parser.add_argument("--roles-dir", required=True)

    subparsers.add_parser("tui", help="Interactive TUI (default when no subcommand given)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in (None, "tui"):
        from devpipe.tui import run_tui
        base_dir = Path(args.roles_dir).resolve().parents[0] if getattr(args, "roles_dir", None) else Path(__file__).resolve().parents[2]
        config = run_tui(base_dir)
        if config is None:
            return 0
        app = build_default_app(base_dir)
        state = app.run(config)
        print(json.dumps({"run_id": state.run_id, "status": state.status, "current_stage": state.current_stage}))
        return 0

    if args.command == "inspect":
        roles = load_roles(args.roles_dir)
        for role_name in sorted(roles):
            print(role_name)
        return 0

    base_dir = Path(args.roles_dir).resolve().parents[0] if args.roles_dir else Path(__file__).resolve().parents[2]
    app = build_default_app(base_dir)
    if args.runs_dir:
        app.runs_dir = Path(args.runs_dir)
    extra_params = {}
    for p in args.params or []:
        if "=" in p:
            k, v = p.split("=", 1)
            extra_params[k.strip()] = v.strip()

    state = app.run(
        RunConfig(
            task_id=args.task_id,
            task=args.task,
            runner=args.runner,
            target_branch=args.target_branch,
            namespace=args.namespace,
            service=args.service,
            tags=args.tags,
            extra_params=extra_params or None,
            first_role=args.first_role,
            last_role=args.last_role,
        )
    )
    print(json.dumps({"run_id": state.run_id, "status": state.status, "current_stage": state.current_stage}))
    return 0
