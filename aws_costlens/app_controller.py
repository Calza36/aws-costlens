"""Main application controller for AWS CostLens."""

import os
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import boto3
from rich import box
from rich.console import Console
from rich.progress import track
from rich.status import Status
from rich.table import Column, Table

# Setup UTF-8 console for Windows
from aws_costlens.console_setup import setup_console
setup_console()

from aws_costlens.aws_api import (
    get_accessible_regions,
    get_account_id,
    get_aws_profiles,
    get_budgets,
    get_stopped_instances,
    get_unused_eips,
    get_unused_volumes,
    get_untagged_resources,
)
from aws_costlens.cost_controller import (
    export_to_csv,
    export_to_json,
    export_to_xlsx,
    get_cost_data,
    get_trend,
)
from aws_costlens.report_exporter import ExportHandler
from aws_costlens.common_utils import (
    clean_rich_tags,
    export_audit_report_to_csv,
    export_audit_report_to_json,
    export_audit_report_to_pdf,
    export_cost_dashboard_to_pdf,
    export_trend_data_to_json,
)
from aws_costlens.profiles_controller import process_combined_profiles, process_single_profile
from aws_costlens.visuals import create_trend_bars
from aws_costlens.models import ProfileData

console = Console(force_terminal=True, legacy_windows=False)


def _generate_timestamped_filename(base_name: str, extension: str) -> str:
    """Generate a filename with timestamp (like aws-finops-dashboard).
    
    Args:
        base_name: Base name for the file (e.g., "cost-report")
        extension: File extension without dot (e.g., "pdf", "csv", "json")
    
    Returns:
        Filename with timestamp: "{base_name}_{YYYYMMDD_HHMM}.{extension}"
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    return f"{base_name}_{timestamp}.{extension}"


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
) -> int:
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
    # Initialize profiles
    with Status("[bright_cyan]🔄 Connecting to AWS...", spinner="dots12", speed=0.1):
        profiles_to_use = _initialize_profiles(profiles, all_profiles)
        if not profiles_to_use:
            return 1

    # Run audit report if requested
    if audit:
        _run_audit_report(profiles_to_use, regions, report_name, report_types, output_dir, s3_bucket, s3_prefix)
        return 0

    # Run trend analysis if requested
    if trend:
        _run_trend_analysis(profiles_to_use, combine, report_name, report_types, output_dir, s3_bucket, s3_prefix, tags)
        return 0

    # Run main cost dashboard
    _run_cost_dashboard(
        profiles_to_use=profiles_to_use,
        user_regions=regions,
        combine=combine,
        report_name=report_name,
        report_types=report_types,
        output_dir=output_dir,
        s3_bucket=s3_bucket,
        s3_prefix=s3_prefix,
        time_range=time_range,
        tags=tags,
    )
    return 0


def _initialize_profiles(profiles: Optional[List[str]], all_profiles: bool) -> List[str]:
    """Initialize AWS profiles based on arguments."""
    available_profiles = get_aws_profiles()
    if not available_profiles:
        console.log("[bold red]No AWS profiles found. Please configure AWS CLI first.[/]")
        return []

    profiles_to_use = []
    if profiles:
        for profile in profiles:
            if profile in available_profiles:
                profiles_to_use.append(profile)
            else:
                console.log(f"[yellow]Warning: Profile '{profile}' not found in AWS configuration[/]")
        if not profiles_to_use:
            console.log("[bold red]None of the specified profiles were found in AWS configuration.[/]")
            return []
    elif all_profiles:
        profiles_to_use = available_profiles
    else:
        if "default" in available_profiles:
            profiles_to_use = ["default"]
        else:
            profiles_to_use = available_profiles
            console.log("[yellow]No default profile found. Using all available profiles.[/]")

    return profiles_to_use


def _run_audit_report(
    profiles_to_use: List[str],
    regions: Optional[List[str]],
    report_name: Optional[str],
    report_types: Optional[List[str]],
    output_dir: Optional[str],
    s3_bucket: Optional[str],
    s3_prefix: Optional[str],
) -> None:
    """Generate and export a resource scan report."""
    console.print("[bold bright_green]⚡ Scanning resources...[/]")
    console.print("[dim]Untagged check: EC2, RDS, Lambda, ELBv2[/]")
    console.print("[dim]Also scanning: Stopped instances, Unused volumes, Unused EIPs, Budget alerts (all resources)[/]\n")
    
    table = Table(
        Column("Profile", justify="center"),
        Column("Account ID", justify="center"),
        Column("Untagged Resources"),
        Column("Stopped EC2 Instances"),
        Column("Unused Volumes"),
        Column("Unused EIPs"),
        Column("Budget Alerts"),
        title="🔍 Resource Scan Results",
        show_lines=True,
        box=box.ASCII_DOUBLE_HEAD,
        style="bright_green",
    )

    audit_data = []
    raw_audit_data = []
    nl = "\n"
    comma_nl = ",\n"

    for profile in profiles_to_use:
        session = boto3.Session(profile_name=profile)
        account_id = get_account_id(session) or "Unknown"
        check_regions = regions or get_accessible_regions(session)

        try:
            untagged = get_untagged_resources(session, check_regions)
            anomalies = []
            for service, region_map in untagged.items():
                if region_map:
                    service_block = f"[bright_yellow]{service}[/]:\n"
                    for region, ids in region_map.items():
                        if ids:
                            ids_block = "\n".join(f"[orange1]{res_id}[/]" for res_id in ids)
                            service_block += f"\n{region}:\n{ids_block}\n"
                    anomalies.append(service_block)
            if not any(region_map for region_map in untagged.values()):
                anomalies = ["None"]
        except Exception as e:
            anomalies = [f"Error: {str(e)}"]

        stopped = get_stopped_instances(session, check_regions)
        stopped_list = [f"{r}:\n[gold1]{nl.join(ids)}[/]" for r, ids in stopped.items()] or ["None"]

        unused_vols = get_unused_volumes(session, check_regions)
        vols_list = [f"{r}:\n[dark_orange]{nl.join(ids)}[/]" for r, ids in unused_vols.items()] or ["None"]

        unused_eips = get_unused_eips(session, check_regions)
        eips_list = [f"{r}:\n{comma_nl.join(ids)}" for r, ids in unused_eips.items()] or ["None"]

        budget_data = get_budgets(session)
        alerts = []
        for b in budget_data:
            if b["actual"] > b["limit"]:
                alerts.append(f"[red1]{b['name']}[/]: ${b['actual']:.2f} > ${b['limit']:.2f}")
        if not alerts:
            alerts = ["No budgets exceeded"]

        audit_data.append({
            "profile": profile,
            "account_id": account_id,
            "untagged_resources": clean_rich_tags("\n".join(anomalies)),
            "stopped_instances": clean_rich_tags("\n".join(stopped_list)),
            "unused_volumes": clean_rich_tags("\n".join(vols_list)),
            "unused_eips": clean_rich_tags("\n".join(eips_list)),
            "budget_alerts": clean_rich_tags("\n".join(alerts)),
        })

        raw_audit_data.append({
            "profile": profile,
            "account_id": account_id,
            "untagged_resources": untagged,
            "stopped_instances": stopped,
            "unused_volumes": unused_vols,
            "unused_eips": unused_eips,
            "budget_alerts": budget_data,
        })

        table.add_row(
            f"[dark_magenta]{profile}[/]",
            account_id,
            "\n".join(anomalies),
            "\n".join(stopped_list),
            "\n".join(vols_list),
            "\n".join(eips_list),
            "\n".join(alerts),
        )

    console.print(table)
    # Note already shown at the start of scan

    # Export if requested
    if report_name and report_types:
        export_handler = ExportHandler(
            output_dir=output_dir or os.getcwd(),
            s3_bucket=s3_bucket,
            s3_prefix=s3_prefix,
            profile=profiles_to_use[0] if profiles_to_use else None,
        )

        for report_type in report_types:
            if report_type == "csv":
                csv_content = export_audit_report_to_csv(raw_audit_data)
                export_handler.save_csv(csv_content, _generate_timestamped_filename(report_name, "csv"))
            elif report_type == "json":
                json_content = export_audit_report_to_json(raw_audit_data)
                export_handler.save_json(json_content, _generate_timestamped_filename(report_name, "json"))
            elif report_type == "pdf":
                pdf_bytes = export_audit_report_to_pdf(raw_audit_data, report_name)
                export_handler.save_pdf(pdf_bytes, _generate_timestamped_filename(report_name, "pdf"))


def _run_trend_analysis(
    profiles_to_use: List[str],
    combine: bool,
    report_name: Optional[str],
    report_types: Optional[List[str]],
    output_dir: Optional[str],
    s3_bucket: Optional[str],
    s3_prefix: Optional[str],
    tags: Optional[Dict[str, str]],
) -> None:
    """Analyze and display cost trends."""
    console.print("[bold bright_magenta]📊 Loading cost history...[/]")
    raw_trend_data = []

    if combine:
        account_profiles = defaultdict(list)
        for profile in profiles_to_use:
            try:
                session = boto3.Session(profile_name=profile)
                account_id = get_account_id(session)
                if account_id:
                    account_profiles[account_id].append(profile)
            except Exception as e:
                console.print(f"[red]Error checking account ID for profile {profile}: {str(e)}[/]")

        for account_id, profile_list in account_profiles.items():
            try:
                primary_profile = profile_list[0]
                session = boto3.Session(profile_name=primary_profile)
                cost_data = get_trend(session, tags)
                trend_data = cost_data.get("monthly_costs")

                if not trend_data:
                    console.print(f"[yellow]No trend data available for account {account_id}[/]")
                    continue

                profiles_str = ", ".join(profile_list)
                console.print(f"\n[bright_yellow]Account: {account_id} (Profiles: {profiles_str})[/]")
                raw_trend_data.append(cost_data)
                create_trend_bars(trend_data)
            except Exception as e:
                console.print(f"[red]Error getting trend for account {account_id}: {str(e)}[/]")
    else:
        for profile in profiles_to_use:
            try:
                session = boto3.Session(profile_name=profile)
                cost_data = get_trend(session, tags)
                trend_data = cost_data.get("monthly_costs")
                account_id = cost_data.get("account_id", "Unknown")

                if not trend_data:
                    console.print(f"[yellow]No trend data available for profile {profile}[/]")
                    continue

                console.print(f"\n[bright_yellow]Account: {account_id} (Profile: {profile})[/]")
                raw_trend_data.append(cost_data)
                create_trend_bars(trend_data)
            except Exception as e:
                console.print(f"[red]Error getting trend for profile {profile}: {str(e)}[/]")

    # Export if requested
    if raw_trend_data and report_name and report_types:
        export_handler = ExportHandler(
            output_dir=output_dir or os.getcwd(),
            s3_bucket=s3_bucket,
            s3_prefix=s3_prefix,
            profile=profiles_to_use[0] if profiles_to_use else None,
        )

        if "json" in report_types:
            json_content = export_trend_data_to_json(raw_trend_data, report_name)
            export_handler.save_json(json_content, _generate_timestamped_filename(f"{report_name}_trend", "json"))


def _get_display_table_period_info(
    profiles_to_use: List[str], time_range: Optional[Union[int, str]]
) -> Tuple[str, str, str, str]:
    """Get period information for the display table."""
    for profile in profiles_to_use:
        try:
            sample_session = boto3.Session(profile_name=profile)
            sample_cost_data = get_cost_data(sample_session, time_range)
            previous_period_name = sample_cost_data.get("previous_period_name", "Last Month Due")
            current_period_name = sample_cost_data.get("current_period_name", "Current Month Cost")
            previous_period_dates = (
                f"{sample_cost_data['previous_period_start']} to {sample_cost_data['previous_period_end']}"
            )
            current_period_dates = (
                f"{sample_cost_data['current_period_start']} to {sample_cost_data['current_period_end']}"
            )
            return (previous_period_name, current_period_name, previous_period_dates, current_period_dates)
        except Exception:
            continue
    return "Last Month Due", "Current Month Cost", "N/A", "N/A"


def create_display_table(
    previous_period_dates: str,
    current_period_dates: str,
    previous_period_name: str = "Last Month Due",
    current_period_name: str = "Current Month Cost",
) -> Table:
    """Create and configure the display table with dynamic column names."""
    return Table(
        Column("AWS Account Profile", justify="center", vertical="middle"),
        Column(f"{previous_period_name}\n({previous_period_dates})", justify="center", vertical="middle"),
        Column(f"{current_period_name}\n({current_period_dates})", justify="center", vertical="middle"),
        Column("Previous Costs by Service", vertical="middle"),
        Column("Current Costs by Service", vertical="middle"),
        Column("Budget Status", vertical="middle"),
        Column("EC2 Summary", justify="center", vertical="middle"),
        title="💰 Spending Overview",
        caption="CostLens",
        box=box.ASCII_DOUBLE_HEAD,
        show_lines=True,
        style="bright_cyan",
    )


def add_profile_to_table(table: Table, profile_data: ProfileData) -> None:
    """Add profile data to the display table."""
    if profile_data["success"]:
        percentage_change = profile_data.get("percent_change_in_total_cost")
        change_text = ""

        if percentage_change is not None:
            if percentage_change > 0:
                change_text = f"\n\n[bright_red]⬆ {percentage_change:.2f}%"
            elif percentage_change < 0:
                change_text = f"\n\n[bright_green]⬇ {abs(percentage_change):.2f}%"
            elif percentage_change == 0:
                change_text = "\n\n[bright_yellow]➡ 0.00%[/]"

        current_month_with_change = f"[bold red]${profile_data['current_month']:.2f}[/]{change_text}"

        table.add_row(
            f"[bright_magenta]Profile: {profile_data['profile']}\nAccount: {profile_data['account_id']}[/]",
            f"[bold red]${profile_data['last_month']:.2f}[/]",
            current_month_with_change,
            "[bright_green]" + "\n".join(profile_data["previous_service_costs_formatted"]) + "[/]",
            "[bright_green]" + "\n".join(profile_data["service_costs_formatted"]) + "[/]",
            "[bright_yellow]" + "\n\n".join(profile_data["budget_info"]) + "[/]",
            "\n".join(profile_data["ec2_summary_formatted"]),
        )
    else:
        table.add_row(
            f"[bright_magenta]{profile_data['profile']}[/]",
            "[red]Error[/]",
            "[red]Error[/]",
            "[red]Error[/]",
            f"[red]Failed to process profile: {profile_data['error']}[/]",
            "[red]N/A[/]",
            "[red]N/A[/]",
        )


def _run_cost_dashboard(
    profiles_to_use: List[str],
    user_regions: Optional[List[str]],
    combine: bool,
    report_name: Optional[str],
    report_types: Optional[List[str]],
    output_dir: Optional[str],
    s3_bucket: Optional[str],
    s3_prefix: Optional[str],
    time_range: Optional[Union[int, str]],
    tags: Optional[Dict[str, str]],
) -> None:
    """Run cost dashboard and generate reports."""
    with Status("[bright_cyan]💰 Preparing dashboard...", spinner="dots12", speed=0.1):
        (
            previous_period_name,
            current_period_name,
            previous_period_dates,
            current_period_dates,
        ) = _get_display_table_period_info(profiles_to_use, time_range)

        table = create_display_table(
            previous_period_dates,
            current_period_dates,
            previous_period_name,
            current_period_name,
        )

    export_data: List[ProfileData] = []

    if combine:
        account_profiles = defaultdict(list)
        for profile in profiles_to_use:
            try:
                session = boto3.Session(profile_name=profile)
                current_account_id = get_account_id(session)
                if current_account_id:
                    account_profiles[current_account_id].append(profile)
                else:
                    console.log(f"[yellow]Could not determine account ID for profile {profile}[/]")
            except Exception as e:
                console.log(f"[bold red]Error checking account ID for profile {profile}: {str(e)}[/]")

        for account_id_key, profile_list in track(
            account_profiles.items(), description="[bright_cyan]Retrieving AWS costs..."
        ):
            if len(profile_list) > 1:
                profile_data = process_combined_profiles(
                    account_id_key, profile_list, user_regions, time_range, tags
                )
            else:
                profile_data = process_single_profile(
                    profile_list[0], user_regions, time_range, tags
                )
            export_data.append(profile_data)
            add_profile_to_table(table, profile_data)
    else:
        for profile in track(profiles_to_use, description="[bright_cyan]Retrieving AWS costs..."):
            profile_data = process_single_profile(profile, user_regions, time_range, tags)
            export_data.append(profile_data)
            add_profile_to_table(table, profile_data)

    console.print(table)

    # Export if requested
    if report_name and report_types:
        export_handler = ExportHandler(
            output_dir=output_dir or os.getcwd(),
            s3_bucket=s3_bucket,
            s3_prefix=s3_prefix,
            profile=profiles_to_use[0] if profiles_to_use else None,
        )

        for report_type in report_types:
            if report_type == "csv":
                csv_content = export_to_csv(export_data, report_name, previous_period_dates, current_period_dates)
                export_handler.save_csv(csv_content, _generate_timestamped_filename(report_name, "csv"))
            elif report_type == "json":
                json_content = export_to_json(export_data, report_name)
                export_handler.save_json(json_content, _generate_timestamped_filename(report_name, "json"))
            elif report_type == "pdf":
                pdf_bytes = export_cost_dashboard_to_pdf(
                    export_data, report_name, previous_period_dates, current_period_dates
                )
                export_handler.save_pdf(pdf_bytes, _generate_timestamped_filename(report_name, "pdf"))
            elif report_type == "xlsx":
                xlsx_bytes = export_to_xlsx(
                    export_data,
                    report_name,
                    previous_period_name,
                    current_period_name,
                    previous_period_dates,
                    current_period_dates,
                )
                export_handler.save_xlsx(xlsx_bytes, _generate_timestamped_filename(report_name, "xlsx"))
