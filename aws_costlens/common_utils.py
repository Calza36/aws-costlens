"""Common utility functions for AWS CostLens - YAML config only."""

import json
import os
import re
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import yaml
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from rich.console import Console

from aws_costlens.pdf_renderer import (
    bulletList,
    formatServicesForList,
    keyValueTable,
    miniHeader,
    paragraphStyling,
    split_to_items,
)

# Force UTF-8 and modern Windows terminal mode for Unicode support
console = Console(force_terminal=True, legacy_windows=False)


def load_config_file(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from a YAML file.

    Args:
        config_path: Path to config file (.yaml or .yml)

    Returns:
        Configuration dictionary
    """
    if not os.path.exists(config_path):
        console.print(f"[bold red]Config file not found: {config_path}[/]")
        return {}

    ext = os.path.splitext(config_path)[1].lower()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            if ext in (".yaml", ".yml"):
                return yaml.safe_load(f) or {}
            else:
                console.print(f"[bold red]Unsupported config format: {ext}. Use .yaml or .yml[/]")
                return {}
    except Exception as e:
        console.print(f"[bold red]Error loading config: {str(e)}[/]")
        return {}


def clean_rich_tags(text: str) -> str:
    """Remove Rich library formatting tags from text."""
    return re.sub(r"\[/?[^\]]+\]", "", text)


def export_cost_dashboard_to_pdf(
    export_data: List[Dict],
    report_name: str,
    previous_period_dates: str,
    current_period_dates: str,
    output_path: Optional[str] = None,
) -> bytes:
    """
    Export cost dashboard to PDF format.

    Args:
        export_data: List of profile data dictionaries
        report_name: Report name
        previous_period_dates: Previous period date range
        current_period_dates: Current period date range
        output_path: Optional path to save PDF

    Returns:
        PDF content as bytes
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    story = []

    # Main Title
    story.append(Paragraph(f"<b>AWS CostLens Report</b>", styles["Heading1"]))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 0.3 * inch))

    for i, profile_data in enumerate(export_data):
        if i > 0:
            story.append(PageBreak())

        # Profile Title
        story.append(Paragraph(
            f"<b>Profile: {profile_data.get('profile', 'N/A')}</b>",
            styles["Heading2"],
        ))
        story.append(Spacer(1, 0.2 * inch))

        # Summary
        story.append(miniHeader("Summary"))
        pct = profile_data.get("percent_change_in_total_cost")
        pct_str = f"{pct:+.1f}%" if pct is not None else "N/A"

        summary_rows = [
            ("Account ID", profile_data.get("account_id", "N/A")),
            (f"Current ({current_period_dates})", f"${profile_data.get('current_month', 0):,.2f}"),
            (f"Previous ({previous_period_dates})", f"${profile_data.get('last_month', 0):,.2f}"),
            ("Change", pct_str),
        ]
        story.append(keyValueTable(summary_rows))
        story.append(Spacer(1, 0.2 * inch))

        # Top Services - Current
        story.append(miniHeader("Highest Cost Services - Current Period"))
        services = profile_data.get("service_costs", [])
        story.append(bulletList(formatServicesForList(services)))
        story.append(Spacer(1, 0.2 * inch))

        # Top Services - Previous
        story.append(miniHeader("Highest Cost Services - Previous Period"))
        prev_services = profile_data.get("previous_service_costs", [])
        story.append(bulletList(formatServicesForList(prev_services)))
        story.append(Spacer(1, 0.2 * inch))

        # Budgets
        story.append(miniHeader("Budgets"))
        budgets = profile_data.get("budget_info", ["No budgets configured"])
        story.append(bulletList([clean_rich_tags(b) for b in budgets]))
        story.append(Spacer(1, 0.2 * inch))

        # EC2 Summary
        story.append(miniHeader("EC2 Summary"))
        ec2 = profile_data.get("ec2_summary_formatted", ["No data"])
        story.append(bulletList(ec2))

    # Build PDF
    doc.build(story)
    buffer.seek(0)
    pdf_bytes = buffer.read()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        console.print(f"[green]✓ PDF saved to {output_path}[/]")

    return pdf_bytes


def export_audit_report_to_pdf(
    audit_data: List[Dict],
    report_name: str,
    output_path: Optional[str] = None,
) -> bytes:
    """
    Export audit/scan report to PDF.

    Args:
        audit_data: List of audit data dictionaries
        report_name: Report name
        output_path: Optional save path

    Returns:
        PDF bytes
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    story = []

    # Main Title
    story.append(Paragraph(f"<b>AWS CostLens Audit Report</b>", styles["Heading1"]))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 0.3 * inch))

    for i, data in enumerate(audit_data):
        if i > 0:
            story.append(PageBreak())

        profile = data.get("profile", "Unknown")
        story.append(Paragraph(f"<b>Profile: {profile}</b>", styles["Heading2"]))
        story.append(Paragraph(f"Account: {data.get('account_id', 'Unknown')}", styles["Normal"]))
        story.append(Spacer(1, 0.2 * inch))

        # Stopped Instances
        story.append(miniHeader("Stopped EC2 Instances"))
        stopped_str = data.get("stopped_instances", "None")
        if stopped_str and stopped_str != "None":
            story.append(bulletList(split_to_items(stopped_str)))
        else:
            story.append(paragraphStyling("None found"))
        story.append(Spacer(1, 0.2 * inch))

        # Unused Volumes
        story.append(miniHeader("Unused EBS Volumes"))
        volumes_str = data.get("unused_volumes", "None")
        if volumes_str and volumes_str != "None":
            story.append(bulletList(split_to_items(volumes_str)))
        else:
            story.append(paragraphStyling("None found"))
        story.append(Spacer(1, 0.2 * inch))

        # Unused EIPs
        story.append(miniHeader("Unused Elastic IPs"))
        eips_str = data.get("unused_eips", "None")
        if eips_str and eips_str != "None":
            story.append(bulletList(split_to_items(eips_str)))
        else:
            story.append(paragraphStyling("None found"))
        story.append(Spacer(1, 0.2 * inch))

        # Untagged Resources
        story.append(miniHeader("Untagged Resources"))
        untagged_str = data.get("untagged_resources", "None")
        if untagged_str and untagged_str != "None":
            story.append(bulletList(split_to_items(untagged_str)))
        else:
            story.append(paragraphStyling("None found"))
        story.append(Spacer(1, 0.2 * inch))

        # Budget Alerts
        story.append(miniHeader("Budget Alerts"))
        alerts_str = data.get("budget_alerts", "No budgets exceeded")
        story.append(paragraphStyling(alerts_str))

    doc.build(story)
    buffer.seek(0)
    pdf_bytes = buffer.read()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        console.print(f"[green]✓ Audit PDF saved to {output_path}[/]")

    return pdf_bytes


def export_audit_report_to_csv(audit_data: List[Dict], output_path: Optional[str] = None) -> str:
    """Export scan report to CSV format (one item per row)."""
    import csv
    from io import StringIO

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(["Profile", "Account ID", "Category", "Region", "Item", "Details"])

    for data in audit_data:
        profile = data.get("profile", "Unknown")
        account_id = data.get("account_id", "Unknown")

        # Stopped EC2 instances
        stopped = data.get("stopped_instances") or {}
        if stopped:
            for region, ids in stopped.items():
                for instance_id in ids:
                    writer.writerow([profile, account_id, "Stopped EC2", region, instance_id, ""])
        else:
            writer.writerow([profile, account_id, "Stopped EC2", "", "None", ""])

        # Unused volumes
        volumes = data.get("unused_volumes") or {}
        if volumes:
            for region, ids in volumes.items():
                for volume_id in ids:
                    writer.writerow([profile, account_id, "Unused Volume", region, volume_id, ""])
        else:
            writer.writerow([profile, account_id, "Unused Volume", "", "None", ""])

        # Unused EIPs
        eips = data.get("unused_eips") or {}
        if eips:
            for region, ips in eips.items():
                for ip in ips:
                    writer.writerow([profile, account_id, "Unused EIP", region, ip, ""])
        else:
            writer.writerow([profile, account_id, "Unused EIP", "", "None", ""])

        # Untagged resources
        untagged = data.get("untagged_resources") or {}
        if untagged:
            for service, region_map in untagged.items():
                if region_map:
                    for region, ids in region_map.items():
                        for resource_id in ids:
                            writer.writerow(
                                [profile, account_id, f"Untagged {service}", region, resource_id, ""]
                            )
        else:
            writer.writerow([profile, account_id, "Untagged Resources", "", "None", ""])

        # Budget alerts (only exceeded budgets)
        budgets = data.get("budget_alerts") or []
        alerts = [
            b for b in budgets
            if b.get("actual", 0) > b.get("limit", 0)
        ]
        if alerts:
            for b in alerts:
                details = f"${b['actual']:.2f} > ${b['limit']:.2f}"
                writer.writerow([profile, account_id, "Budget Alert", "", b.get("name", "Unknown"), details])
        else:
            writer.writerow([profile, account_id, "Budget Alerts", "", "No budgets exceeded", ""])

        writer.writerow([])

    csv_content = output.getvalue()

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(csv_content)
        console.print(f"[green]✓ Audit CSV saved to {output_path}[/]")

    return csv_content


def export_audit_report_to_json(audit_data: List[Dict], output_path: Optional[str] = None) -> str:
    """Export scan report to JSON format."""
    output = {
        "report_type": "audit",
        "generated": datetime.now().isoformat(),
        "profiles": audit_data,
    }
    json_content = json.dumps(output, indent=2)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_content)
        console.print(f"[green]✓ Audit JSON saved to {output_path}[/]")

    return json_content


def export_trend_data_to_json(
    trend_data: List[Dict],
    report_name: str,
    output_path: Optional[str] = None,
) -> str:
    """Export cost history data to JSON format."""
    output = {
        "report_name": report_name,
        "report_type": "trend",
        "generated": datetime.now().isoformat(),
        "data": trend_data,
    }
    json_content = json.dumps(output, indent=2)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_content)
        console.print(f"[green]✓ Trend JSON saved to {output_path}[/]")

    return json_content
