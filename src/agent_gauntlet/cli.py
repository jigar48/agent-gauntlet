"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent_gauntlet import __version__
from agent_gauntlet.demo import run_demo
from agent_gauntlet.engine import PermissionDenied, check_permission, execute
from agent_gauntlet.journey import JourneyError, load_journey
from agent_gauntlet.presets import PRESET_NAMES, render_preset
from agent_gauntlet.report import write_report
from agent_gauntlet.result import RunResult
from agent_gauntlet.scorecard import headline, scorecard_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-gauntlet",
        description="Deterministic audit of a checkout journey, run the way an AI shopping "
        "agent runs it. Stops before payment. Only test sites you own or have written "
        "permission to test.",
    )
    parser.add_argument("--version", action="version", version=f"agent-gauntlet {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a journey file")
    run.add_argument("journey", type=Path, help="path to the journey YAML file")
    run.add_argument(
        "--out",
        type=Path,
        default=Path("gauntlet-out"),
        help="output directory (default: gauntlet-out)",
    )
    run.add_argument(
        "--i-have-permission",
        action="store_true",
        help="confirm you own the site or have written permission to test it "
        "(required for any host other than localhost)",
    )

    rep = sub.add_parser(
        "report", help="print the scorecard and write report.html from a result.json"
    )
    rep.add_argument("result", type=Path, help="path to result.json")
    rep.add_argument(
        "--out", type=Path, default=None, help="output directory (default: next to result.json)"
    )

    demo = sub.add_parser(
        "demo", help="start the built-in fake shops on localhost and audit every variant"
    )
    demo.add_argument(
        "--out",
        type=Path,
        default=Path("gauntlet-demo"),
        help="output directory (default: gauntlet-demo)",
    )

    init = sub.add_parser(
        "init", help="write a starter journey file (presets are experimental, fixture-tested only)"
    )
    init.add_argument("--preset", choices=PRESET_NAMES, default="generic")
    init.add_argument("--out", type=Path, default=Path("journey.yml"))
    init.add_argument("--base-url", default=None, help="store URL to put in the file")
    init.add_argument("--force", action="store_true", help="overwrite an existing file")
    return parser


def cmd_run(args: argparse.Namespace) -> int:
    try:
        journey = load_journey(args.journey)
    except JourneyError as exc:
        print(f"Journey file problem in {args.journey}:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    try:
        permission = check_permission(journey, args.i_have_permission)
    except PermissionDenied as exc:
        print(f"Refusing to run: {exc}", file=sys.stderr)
        return 2
    result = execute(journey, out_dir=args.out, permission=permission)
    report_path = write_report(result, args.out)
    print(scorecard_text(result))
    print()
    print(f"Wrote {args.out / 'result.json'} and {report_path}")
    return result.exit_code


def cmd_report(args: argparse.Namespace) -> int:
    try:
        result = RunResult.model_validate_json(args.result.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Cannot read a result from {args.result}: {exc}", file=sys.stderr)
        return 2
    out_dir = args.out or args.result.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = write_report(result, out_dir)
    print(scorecard_text(result))
    print()
    print(f"Wrote {report_path}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    entries = run_demo(args.out, log=print)
    print()
    for e in entries:
        mark = "ok " if e.as_designed else "!! "
        print(f"{mark}{e.variant:<14} {headline(e.result)}")
    print()
    print(f"Wrote {args.out / 'index.html'} (open it in a browser)")
    return 0 if all(e.as_designed for e in entries) else 1


def cmd_init(args: argparse.Namespace) -> int:
    if args.out.exists() and not args.force:
        print(f"{args.out} already exists. Use --force to overwrite it.", file=sys.stderr)
        return 2
    args.out.write_text(render_preset(args.preset, args.base_url), encoding="utf-8")
    print(f"Wrote {args.out} from the '{args.preset}' preset (experimental, not verified against")
    print("a live store). Edit base_url and the selectors, then run:")
    print(f"  agent-gauntlet run {args.out} --i-have-permission")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "report":
        return cmd_report(args)
    if args.command == "init":
        return cmd_init(args)
    if args.command == "demo":
        return cmd_demo(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
