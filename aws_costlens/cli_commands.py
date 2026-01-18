"""CLI commands entry point for AWS CostLens."""

import argparse
import sys
from typing import Dict, List, Optional

# Setup UTF-8 console for Windows
from aws_costlens.console_setup import setup_console
setup_console()

from rich.console import Console

from aws_costlens import __version__
from aws_costlens.app_controller import run_dashboard
from aws_costlens.common_utils import load_config_file

# Force UTF-8 and modern Windows terminal mode for Unicode support
console = Console(force_terminal=True, legacy_windows=False)


def welcome_banner() -> None:
    """Display the welcome banner with version."""
    # Compact banner with version on the right
    console.print()
    console.print(
        "[bold bright_cyan]╔═══════════════════════════════════════════════╗[/]  "
        f"[dim italic]v{__version__}[/]"
    )
    console.print("[bold bright_cyan]║     AWS CostLens - Cost Intelligence Tool     ║[/]")
    console.print("[bold bright_cyan]╚═══════════════════════════════════════════════╝[/]")
    console.print()  # Single line space before content


def parse_tags(tag_strings: Optional[List[str]]) -> Optional[Dict[str, str]]:
    """Parse tag arguments into a dictionary."""
    if not tag_strings:
        return None

    tags = {}
    for tag in tag_strings:
        if "=" in tag:
            key, value = tag.split("=", 1)
            tags[key.strip()] = value.strip()
        else:
            console.print(f"[yellow]Warning: Invalid tag format '{tag}', use key=value[/]")
    return tags if tags else None


def main() -> None:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog="aws-costlens",
        description="AWS CostLens - Terminal-based AWS cost and resource intelligence tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  aws-costlens cost                              # Cost dashboard for default profile
  aws-costlens cost --profiles dev prod          # Multiple profiles
  aws-costlens cost --all-profiles               # All configured profiles
  aws-costlens cost --all-profiles --merge       # Merge profiles from same account
  aws-costlens history --profiles prod           # 6-month cost history
  aws-costlens scan --profiles prod              # Resource scan
  aws-costlens export --all-profiles --format pdf  # Export report to PDF
""",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Common arguments for all commands
    def add_common_args(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--profiles", "-p",
            nargs="+",
            help="AWS CLI profile names to use",
        )
        subparser.add_argument(
            "--regions", "-r",
            nargs="+",
            help="AWS regions to check (default: common regions)",
        )
        subparser.add_argument(
            "--all-profiles", "-a",
            action="store_true",
            help="Process all available AWS profiles",
        )
        subparser.add_argument(
            "--config", "-c",
            help="Path to YAML config file",
        )

    # Cost command
    cost_parser = subparsers.add_parser("cost", help="Display cost dashboard")
    add_common_args(cost_parser)
    cost_parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge results from multiple profiles",
    )
    cost_parser.add_argument(
        "--time-range", "-t",
        help="Time range: number of days (e.g., 30) or date range (YYYY-MM-DD:YYYY-MM-DD)",
    )
    cost_parser.add_argument(
        "--tag",
        action="append",
        help="Filter by tag (key=value), can be used multiple times",
    )

    # History command (formerly trend)
    history_parser = subparsers.add_parser("history", help="Display 6-month cost history")
    add_common_args(history_parser)

    # Scan command (formerly audit)
    scan_parser = subparsers.add_parser("scan", help="Run resource scan")
    add_common_args(scan_parser)

    # Export command (formerly report)
    export_parser = subparsers.add_parser("export", help="Generate and export reports")
    add_common_args(export_parser)
    export_parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge results from multiple profiles",
    )
    export_parser.add_argument(
        "--time-range", "-t",
        help="Time range for cost data",
    )
    export_parser.add_argument(
        "--tag",
        action="append",
        help="Filter by tag (key=value)",
    )
    export_parser.add_argument(
        "--name", "-n",
        default="costlens_report",
        help="Base name for report files",
    )
    export_parser.add_argument(
        "--format", "-f",
        nargs="+",
        choices=["pdf", "csv", "json"],
        default=["pdf"],
        help="Export format(s): pdf, csv, json",
    )
    export_parser.add_argument(
        "--dir", "-d",
        help="Output directory for reports",
    )
    export_parser.add_argument(
        "--bucket",
        help="S3 bucket for uploading reports",
    )
    export_parser.add_argument(
        "--s3-path",
        help="S3 path/prefix for reports",
    )
    export_parser.add_argument(
        "--scan",
        action="store_true",
        help="Include resource scan report",
    )
    export_parser.add_argument(
        "--history",
        action="store_true",
        help="Include cost history report",
    )

    # Version
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"aws-costlens {__version__}",
    )

    args = parser.parse_args()

    # Show banner
    welcome_banner()

    # No command provided
    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Load config file if provided
    config = {}
    config_path = getattr(args, "config", None)
    if config_path:
        config = load_config_file(config_path)
        if config:
            console.print(f"[dim]Loaded config from {config_path}[/]")

    # Merge config with CLI args (CLI takes precedence)
    profiles = args.profiles or config.get("profiles")
    regions = args.regions or config.get("regions")
    all_profiles = args.all_profiles or config.get("all_profiles", False)

    # Parse time range
    time_range = None
    if hasattr(args, "time_range") and args.time_range:
        try:
            time_range = int(args.time_range)
        except ValueError:
            time_range = args.time_range  # Custom date range string

    # Parse tags
    tags = None
    if hasattr(args, "tag"):
        tags = parse_tags(args.tag)

    # Execute command
    if args.command == "cost":
        run_dashboard(
            profiles=profiles,
            regions=regions,
            all_profiles=all_profiles,
            combine=args.merge,
            time_range=time_range,
            tags=tags,
        )

    elif args.command == "history":
        run_dashboard(
            profiles=profiles,
            regions=regions,
            all_profiles=all_profiles,
            trend=True,
        )

    elif args.command == "scan":
        run_dashboard(
            profiles=profiles,
            regions=regions,
            all_profiles=all_profiles,
            audit=True,
        )

    elif args.command == "export":
        run_dashboard(
            profiles=profiles,
            regions=regions,
            all_profiles=all_profiles,
            combine=getattr(args, "merge", False),
            audit=getattr(args, "scan", False),
            trend=getattr(args, "history", False),
            report_name=args.name,
            report_types=args.format,
            output_dir=args.dir,
            s3_bucket=args.bucket,
            s3_prefix=args.s3_path,
            time_range=time_range,
            tags=tags,
        )


if __name__ == "__main__":
    main()
