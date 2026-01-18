"""Main application controller for AWS CostLens."""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import boto3
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from aws_costlens.aws_api import (
    get_accessible_regions,
    get_aws_profiles,
    get_stopped_instances,
    get_unused_eips,
    get_unused_volumes,
    get_untagged_resources,
)
from aws_costlens.cost_controller import export_to_csv, export_to_json, get_trend
from aws_costlens.report_exporter import ExportHandler
from aws_costlens.common_utils import (
    export_audit_report_to_csv,
    export_audit_report_to_json,
    export_audit_report_to_pdf,
    export_cost_dashboard_to_pdf,
    export_trend_data_to_json,
)
from aws_costlens.profiles_controller import process_combined_profiles, process_single_profile
from aws_costlens.visuals import create_trend_bars

console = Console()


def run_dashboard(
    profiles: Optional[List[str]] = None,
    regions: Optional[List[str]] = None,
    all_profiles: bool = False,
    combine: bool = False,
    audit: bool = False,
    trend: bool = False,
    report_name: Optional[str] = None,
    report_types: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    s3_bucket: Optional[str] = None,
    s3_prefix: Optional[str] = None,
    time_range: Optional[Union[int, str]] = None,
    tags: Optional[Dict[str, str]] = None,
) -> None:
    """
    Run the AWS CostLens application.

    Args:
        profiles: List of AWS profiles to process
        regions: List of regions to check
        all_profiles: Process all available profiles
        combine: Merge results from multiple profiles
        audit: Run resource scan
        trend: Show cost history
        report_name: Base name for report files
        report_types: List of export formats (pdf, csv, json)
        output_dir: Output directory for reports
        s3_bucket: Optional S3 bucket for uploads
        s3_prefix: Optional S3 path
        time_range: Custom time range
        tags: Tag filters
    """
    # Determine profiles to process
    if all_profiles:
        profiles = get_aws_profiles()
        if not profiles:
            console.print("[bold red]No AWS profiles found[/]")
            return
        console.print(f"[cyan]Found {len(profiles)} profiles[/]")
    elif not profiles:
        profiles = ["default"]

    # Setup export handler
    handler = ExportHandler(
        output_dir=output_dir or os.getcwd(),
        s3_bucket=s3_bucket,
        s3_prefix=s3_prefix,
        profile=profiles[0] if profiles else None,
    )

    # Generate timestamp for report names
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = report_name or "costlens_report"

    # Run scan if requested
    if audit:
        _run_scan(profiles, regions, handler, base_name, timestamp, report_types)
        return

    # Run history if requested
    if trend:
        _run_history(profiles, handler, base_name, timestamp, report_types)
        return

    # Run cost dashboard
    _run_cost_dashboard(
        profiles=profiles,
        regions=regions,
        combine=combine,
        handler=handler,
        base_name=base_name,
        timestamp=timestamp,
        report_types=report_types,
        time_range=time_range,
        tags=tags,
    )


def _run_scan(
    profiles: List[str],
    regions: Optional[List[str]],
    handler: ExportHandler,
    base_name: str,
    timestamp: str,
    report_types: Optional[List[str]],
) -> None:
    """Run resource scan and generate reports."""
    for profile in profiles:
        console.print(f"\n[bold cyan]Scanning resources for: {profile}[/]")

        try:
            session = boto3.Session(profile_name=profile)

            # Get regions
            if regions:
                check_regions = regions
            else:
                check_regions = get_accessible_regions(session)
                console.print(f"[dim]Checking {len(check_regions)} regions...[/]")

            # Collect scan data
            scan_data = {
                "profile": profile,
                "timestamp": timestamp,
                "stopped_instances": get_stopped_instances(session, check_regions),
                "unused_volumes": get_unused_volumes(session, check_regions),
                "unused_eips": get_unused_eips(session, check_regions),
                "untagged_resources": get_untagged_resources(session, check_regions),
            }

            # Display results
            _display_scan_results(scan_data, profile)

            # Export if requested
            if report_types:
                filename_base = f"{base_name}_{profile}_scan_{timestamp}"

                if "pdf" in report_types:
                    pdf_bytes = export_audit_report_to_pdf(scan_data, profile)
                    handler.save_pdf(pdf_bytes, f"{filename_base}.pdf")

                if "csv" in report_types:
                    csv_content = export_audit_report_to_csv(scan_data)
                    handler.save_csv(csv_content, f"{filename_base}.csv")

                if "json" in report_types:
                    json_content = export_audit_report_to_json(scan_data)
                    handler.save_json(json_content, f"{filename_base}.json")

        except Exception as e:
            console.print(f"[bold red]Error scanning {profile}: {str(e)}[/]")


def _display_scan_results(scan_data: Dict, profile: str) -> None:
    """Display scan results in console."""
    # Create summary table
    table = Table(title=f"Resource Scan - {profile}", show_header=True)
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right", style="yellow")
    table.add_column("Details", style="dim")

    # Stopped instances
    stopped = scan_data.get("stopped_instances", {})
    stopped_count = sum(len(ids) for ids in stopped.values())
    stopped_regions = ", ".join(stopped.keys()) if stopped else "None"
    table.add_row("Stopped EC2", str(stopped_count), stopped_regions)

    # Unused volumes
    volumes = scan_data.get("unused_volumes", {})
    vol_count = sum(len(ids) for ids in volumes.values())
    vol_regions = ", ".join(volumes.keys()) if volumes else "None"
    table.add_row("Unused Volumes", str(vol_count), vol_regions)

    # Unused EIPs
    eips = scan_data.get("unused_eips", {})
    eip_count = sum(len(ips) for ips in eips.values())
    eip_regions = ", ".join(eips.keys()) if eips else "None"
    table.add_row("Unused EIPs", str(eip_count), eip_regions)

    # Untagged resources
    untagged = scan_data.get("untagged_resources", {})
    for service, regions in untagged.items():
        count = sum(len(ids) for ids in regions.values())
        if count > 0:
            region_list = ", ".join(regions.keys())
            table.add_row(f"Untagged {service}", str(count), region_list)

    console.print(table)


def _run_history(
    profiles: List[str],
    handler: ExportHandler,
    base_name: str,
    timestamp: str,
    report_types: Optional[List[str]],
) -> None:
    """Run cost history analysis and generate visualizations."""
    for profile in profiles:
        console.print(f"\n[bold cyan]Analyzing account: {profile}[/]")

        try:
            session = boto3.Session(profile_name=profile)
            monthly_costs = get_trend(session)

            if monthly_costs:
                # Display history chart
                panel = create_trend_bars(monthly_costs)
                console.print(panel)

                # Export if requested
                if report_types and "json" in report_types:
                    filename = f"{base_name}_{profile}_history_{timestamp}.json"
                    json_content = export_trend_data_to_json(monthly_costs, profile)
                    handler.save_json(json_content, filename)
            else:
                console.print("[yellow]No cost history available[/]")

        except Exception as e:
            console.print(f"[bold red]Error getting history for {profile}: {str(e)}[/]")


def _run_cost_dashboard(
    profiles: List[str],
    regions: Optional[List[str]],
    combine: bool,
    handler: ExportHandler,
    base_name: str,
    timestamp: str,
    report_types: Optional[List[str]],
    time_range: Optional[Union[int, str]],
    tags: Optional[Dict[str, str]],
) -> None:
    """Run cost dashboard and generate reports."""
    if combine and len(profiles) > 1:
        # Process merged
        console.print(f"[bold cyan]Merging data for {len(profiles)} profiles[/]")
        profile_data = process_combined_profiles(profiles, regions, time_range, tags)
        _display_profile_data(profile_data)

        if report_types:
            _export_profile_data(
                profile_data, handler, f"{base_name}_merged_{timestamp}", report_types
            )
    else:
        # Process individually
        for profile in profiles:
            console.print(f"\n[bold cyan]Analyzing account: {profile}[/]")
            profile_data = process_single_profile(profile, regions, time_range, tags)

            if profile_data["success"]:
                _display_profile_data(profile_data)

                if report_types:
                    _export_profile_data(
                        profile_data,
                        handler,
                        f"{base_name}_{profile}_{timestamp}",
                        report_types,
                    )
            else:
                console.print(f"[bold red]Error: {profile_data.get('error')}[/]")


def _display_profile_data(data: Dict) -> None:
    """Display profile cost data in console."""
    # Create summary panel
    pct = data.get("percent_change_in_total_cost")
    pct_color = "green" if pct and pct < 0 else "red" if pct and pct > 0 else "yellow"
    pct_str = f"[{pct_color}]{pct:+.1f}%[/]" if pct is not None else "[dim]N/A[/]"

    summary = f"""[bold]Account:[/] {data.get('account_id', 'N/A')}
[bold]{data.get('current_period_name', 'Current')}:[/] [green]${data.get('current_month', 0):,.2f}[/]
[bold]{data.get('previous_period_name', 'Previous')}:[/] ${data.get('last_month', 0):,.2f}
[bold]Change:[/] {pct_str}"""

    console.print(Panel(summary, title=f"💵 Spending Overview - {data.get('profile', 'Summary')}", border_style="green"))

    # Services table
    table = Table(title="Highest Cost Services", show_header=True)
    table.add_column("Service", style="cyan")
    table.add_column("Current", justify="right", style="green")
    table.add_column("Previous", justify="right", style="dim")

    current = data.get("service_costs", [])
    previous = dict(data.get("previous_service_costs", []))

    for svc, cost in current:
        prev_cost = previous.get(svc, 0)
        table.add_row(svc, f"${cost:,.2f}", f"${prev_cost:,.2f}")

    console.print(table)

    # Budgets
    budgets = data.get("budget_info", [])
    if budgets and budgets != ["No budgets configured"]:
        console.print("\n[bold]Budgets:[/]")
        for b in budgets:
            console.print(f"  {b}")

    # EC2 Summary
    ec2 = data.get("ec2_summary_formatted", [])
    if ec2:
        console.print("\n[bold]EC2 Summary:[/]")
        for item in ec2:
            console.print(f"  {item}")


def _export_profile_data(
    data: Dict,
    handler: ExportHandler,
    filename_base: str,
    report_types: List[str],
) -> None:
    """Export profile data to requested formats."""
    current_period = data.get("current_period_name", "Current")
    previous_period = data.get("previous_period_name", "Previous")

    if "pdf" in report_types:
        pdf_bytes = export_cost_dashboard_to_pdf(data, current_period, previous_period)
        handler.save_pdf(pdf_bytes, f"{filename_base}.pdf")

    if "csv" in report_types:
        csv_content = export_to_csv(data, current_period, previous_period)
        handler.save_csv(csv_content, f"{filename_base}.csv")

    if "json" in report_types:
        json_content = export_to_json(data, current_period, previous_period)
        handler.save_json(json_content, f"{filename_base}.json")
