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
    profile_data: Dict,
    current_period: str,
    previous_period: str,
    output_path: Optional[str] = None,
) -> bytes:
    """
    Export cost dashboard to PDF format.

    Args:
        profile_data: Dictionary with profile cost data
        current_period: Name of current period
        previous_period: Name of previous period
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

    # Title
    title = Paragraph(
        f"<b>AWS Cost Report - {profile_data.get('profile', 'N/A')}</b>",
        styles["Heading1"],
    )
    story.append(title)
    story.append(Spacer(1, 0.2 * inch))

    # Summary
    story.append(miniHeader("Summary"))
    pct = profile_data.get("percent_change_in_total_cost")
    pct_str = f"{pct:+.1f}%" if pct is not None else "N/A"

    summary_rows = [
        ("Account ID", profile_data.get("account_id", "N/A")),
        (current_period, f"${profile_data.get('current_month', 0):,.2f}"),
        (previous_period, f"${profile_data.get('last_month', 0):,.2f}"),
        ("Change", pct_str),
    ]
    story.append(keyValueTable(summary_rows))
    story.append(Spacer(1, 0.2 * inch))

    # Top Services - Current
    story.append(miniHeader(f"Highest Cost Services - {current_period}"))
    services = profile_data.get("service_costs", [])
    story.append(bulletList(formatServicesForList(services)))
    story.append(Spacer(1, 0.2 * inch))

    # Top Services - Previous
    story.append(miniHeader(f"Highest Cost Services - {previous_period}"))
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
    audit_data: Dict,
    profile: str,
    output_path: Optional[str] = None,
) -> bytes:
    """
    Export audit/scan report to PDF.

    Args:
        audit_data: Dictionary with scan findings
        profile: Profile name
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

    # Title
    story.append(Paragraph(f"<b>AWS Resource Scan - {profile}</b>", styles["Heading1"]))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 0.3 * inch))

    # Stopped Instances
    story.append(miniHeader("Stopped EC2 Instances"))
    stopped = audit_data.get("stopped_instances", {})
    if stopped:
        for region, ids in stopped.items():
            story.append(paragraphStyling(f"<b>{region}:</b>"))
            story.append(bulletList(ids))
    else:
        story.append(paragraphStyling("None found"))
    story.append(Spacer(1, 0.2 * inch))

    # Unused Volumes
    story.append(miniHeader("Unused EBS Volumes"))
    volumes = audit_data.get("unused_volumes", {})
    if volumes:
        for region, ids in volumes.items():
            story.append(paragraphStyling(f"<b>{region}:</b>"))
            story.append(bulletList(ids))
    else:
        story.append(paragraphStyling("None found"))
    story.append(Spacer(1, 0.2 * inch))

    # Unused EIPs
    story.append(miniHeader("Unused Elastic IPs"))
    eips = audit_data.get("unused_eips", {})
    if eips:
        for region, ips in eips.items():
            story.append(paragraphStyling(f"<b>{region}:</b>"))
            story.append(bulletList(ips))
    else:
        story.append(paragraphStyling("None found"))
    story.append(Spacer(1, 0.2 * inch))

    # Untagged Resources
    story.append(miniHeader("Untagged Resources"))
    untagged = audit_data.get("untagged_resources", {})
    if untagged:
        for service, regions in untagged.items():
            if regions:
                story.append(paragraphStyling(f"<b>{service}:</b>"))
                for region, ids in regions.items():
                    story.append(paragraphStyling(f"  {region}:"))
                    story.append(bulletList(ids))
    else:
        story.append(paragraphStyling("None found"))

    doc.build(story)
    buffer.seek(0)
    pdf_bytes = buffer.read()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        console.print(f"[green]✓ Scan PDF saved to {output_path}[/]")

    return pdf_bytes


def export_audit_report_to_csv(audit_data: Dict, output_path: Optional[str] = None) -> str:
    """Export scan report to CSV format."""
    import csv
    from io import StringIO

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(["Category", "Region", "Resource ID"])

    for region, ids in audit_data.get("stopped_instances", {}).items():
        for id in ids:
            writer.writerow(["Stopped EC2", region, id])

    for region, ids in audit_data.get("unused_volumes", {}).items():
        for id in ids:
            writer.writerow(["Unused Volume", region, id])

    for region, ips in audit_data.get("unused_eips", {}).items():
        for ip in ips:
            writer.writerow(["Unused EIP", region, ip])

    for service, regions in audit_data.get("untagged_resources", {}).items():
        for region, ids in regions.items():
            for id in ids:
                writer.writerow([f"Untagged {service}", region, id])

    csv_content = output.getvalue()

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(csv_content)
        console.print(f"[green]✓ Scan CSV saved to {output_path}[/]")

    return csv_content


def export_audit_report_to_json(audit_data: Dict, output_path: Optional[str] = None) -> str:
    """Export scan report to JSON format."""
    json_content = json.dumps(audit_data, indent=2)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_content)
        console.print(f"[green]✓ Scan JSON saved to {output_path}[/]")

    return json_content


def export_trend_data_to_json(
    monthly_costs: List[Tuple[str, float]],
    profile: str,
    output_path: Optional[str] = None,
) -> str:
    """Export cost history data to JSON format."""
    data = {
        "profile": profile,
        "generated": datetime.now().isoformat(),
        "monthly_costs": [{"month": m, "cost": c} for m, c in monthly_costs],
    }
    json_content = json.dumps(data, indent=2)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_content)
        console.print(f"[green]✓ History JSON saved to {output_path}[/]")

    return json_content
