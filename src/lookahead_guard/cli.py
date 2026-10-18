"""Command line interface: ``lookahead-guard check|mask|cutoffs|rules|demo``."""

from __future__ import annotations

import argparse
import json
import os
import sys
from importlib import resources
from typing import List, Optional

from . import __version__
from .cutoffs import CutoffTable
from .dates import parse_date
from .io import load_records, record_from_dict
from .mask import Masker
from .report import render_github, render_json, render_text
from .rules import RULES, SEVERITY_RANK, Checker

EXIT_OK, EXIT_FINDINGS, EXIT_USAGE = 0, 1, 2


def _table(args) -> CutoffTable:
    table = CutoffTable.bundled()
    for path in args.cutoffs or []:
        table.load_file(path)
    return table


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--as-of", help="decision date for plain-text files or records without one (YYYY-MM-DD)")
    p.add_argument("--entity", action="append", default=[], metavar="NAME",
                   help="extra asset name/ticker to treat as an identifier (repeatable)")


def _cmd_check(args) -> int:
    try:
        records = load_records(args.paths, as_of=args.as_of, model=args.model)
    except (OSError, ValueError) as exc:
        print(f"lookahead-guard: {exc}", file=sys.stderr)
        return EXIT_USAGE
    default_as_of = parse_date(args.as_of) if args.as_of else None
    for r in records:
        if r.as_of is None and default_as_of is not None:
            r.as_of = default_as_of
        if r.model is None and args.model:
            r.model = args.model
    checker = Checker(
        cutoffs=_table(args),
        default_model=args.model,
        default_horizon_days=args.horizon_days,
        cutoff_override=parse_date(args.cutoff) if args.cutoff else None,
        margin_days=args.margin_days,
        entities=args.entity,
    )
    results = checker.check_all(records)
    if args.format == "json":
        print(render_json(results, args.min_severity))
    elif args.format == "github":
        out = render_github(results, args.min_severity if args.min_severity != "info" else "warning")
        if out:
            print(out)
    else:
        color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        print(render_text(results, args.min_severity, color=color))
    if args.fail_on == "never":
        return EXIT_OK
    floor = SEVERITY_RANK[args.fail_on]
    worst = [SEVERITY_RANK[f.severity] for r in results for f in r.findings]
    return EXIT_FINDINGS if worst and max(worst) >= floor else EXIT_OK


def _cmd_mask(args) -> int:
    masker = Masker(args.entity)
    path = args.path
    if path.endswith(".jsonl"):
        out_lines = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                d = json.loads(line)
                rec = record_from_dict(d)
                as_of = rec.as_of or (parse_date(args.as_of) if args.as_of else None)
                if as_of is None:
                    print("lookahead-guard: record without as_of; pass --as-of", file=sys.stderr)
                    return EXIT_USAGE
                d["prompt"] = masker.mask(rec.prompt, as_of, rec.entities).text
                d.pop("messages", None)
                d["masked"] = True
                out_lines.append(json.dumps(d, ensure_ascii=False))
        print("\n".join(out_lines))
    else:
        if not args.as_of:
            print("lookahead-guard: --as-of is required for plain-text input", file=sys.stderr)
            return EXIT_USAGE
        with open(path, encoding="utf-8") as fh:
            print(masker.mask(fh.read(), parse_date(args.as_of)).text)
    if args.mapping:
        with open(args.mapping, "w", encoding="utf-8") as fh:
            json.dump(masker.mapping, fh, indent=2, ensure_ascii=False)
    return EXIT_OK


def _cmd_cutoffs(args) -> int:
    table = _table(args)
    if args.model:
        mc = table.lookup(args.model)
        if mc is None:
            print(f"{args.model}: unknown (add it with --cutoffs FILE)")
            return EXIT_FINDINGS
        print(f"{args.model}: {mc.id} ({mc.vendor}) cutoff {mc.cutoff.isoformat()} [{mc.kind}] {mc.note}".rstrip())
        return EXIT_OK
    print(f"{'model':<22} {'vendor':<10} {'cutoff':<11} kind")
    for mc in table.entries():
        print(f"{mc.id:<22} {mc.vendor:<10} {mc.cutoff.isoformat():<11} {mc.kind}")
    print("\nVendor-reported values; verify before relying on them. 'cutoff' = last day the model may have seen.")
    return EXIT_OK


def _cmd_rules(args) -> int:
    for rule, name in RULES.items():
        print(f"{rule}  {name}")
    return EXIT_OK


def _cmd_demo(args) -> int:
    raw = resources.files("lookahead_guard").joinpath("data/demo_log.jsonl").read_text("utf-8")
    records = [record_from_dict(json.loads(line), "demo_log.jsonl", n)
               for n, line in enumerate(raw.splitlines(), 1) if line.strip()]
    print("Synthetic demo log: prices are made up; ACMR / Acme Robotics and Northwind Foods are fictional.\n")
    results = Checker(entities=["ACMR", "Acme Robotics", "Northwind Foods"]).check_all(records)
    color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    print(render_text(results, "info", color=color))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lookahead-guard",
        description="Lint LLM backtest prompts and logs for look-ahead (temporal) leakage.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command")

    c = sub.add_parser("check", help="check prompt/log files")
    c.add_argument("paths", nargs="+", help=".jsonl / .json logs or plain-text prompts")
    _add_common(c)
    c.add_argument("--model", help="model id for records without one (e.g. gpt-4o-2024-08-06)")
    c.add_argument("--horizon-days", type=int, help="outcome window after as_of (default: record value or 1)")
    c.add_argument("--cutoff", help="override the model cutoff (YYYY-MM or YYYY-MM-DD)")
    c.add_argument("--cutoffs", action="append", metavar="FILE", help="extra cutoff table JSON (repeatable)")
    c.add_argument("--margin-days", type=int, default=0, help="add a safety margin to every cutoff")
    c.add_argument("--format", choices=["text", "json", "github"], default="text")
    c.add_argument("--min-severity", choices=["info", "warning", "error"], default="info",
                   help="hide findings below this level")
    c.add_argument("--fail-on", choices=["info", "warning", "error", "never"], default="error",
                   help="exit 1 when a finding at or above this level exists (default: error)")
    c.set_defaults(func=_cmd_check)

    m = sub.add_parser("mask", help="mask dates, tickers and events in a prompt file or .jsonl log")
    m.add_argument("path")
    _add_common(m)
    m.add_argument("--mapping", metavar="FILE", help="write alias -> original mapping as JSON")
    m.set_defaults(func=_cmd_mask)

    k = sub.add_parser("cutoffs", help="show the model cutoff table or look up one model")
    k.add_argument("model", nargs="?")
    k.add_argument("--cutoffs", action="append", metavar="FILE")
    k.set_defaults(func=_cmd_cutoffs)

    r = sub.add_parser("rules", help="list rule ids")
    r.set_defaults(func=_cmd_rules)

    d = sub.add_parser("demo", help="run the checker on a built-in synthetic log")
    d.set_defaults(func=_cmd_demo)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_USAGE
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"lookahead-guard: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except BrokenPipeError:  # e.g. piped into `head`
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
