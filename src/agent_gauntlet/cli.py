"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent_gauntlet import __version__
from agent_gauntlet.engine import PermissionDenied, check_permission, execute
from agent_gauntlet.journey import JourneyError, load_journey


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
    for pace in result.paces:
        where = f" (failed at step {pace.failed_step})" if pace.failed_step else ""
        print(f"{pace.pace:>7} pace: {pace.status}{where}")
    print(f"Wrote {args.out / 'result.json'}")
    return result.exit_code


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
