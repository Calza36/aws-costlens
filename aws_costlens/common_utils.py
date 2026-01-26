"""Common utility functions for AWS CostLens - YAML config only."""

import json
import os
import re
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import yaml
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, portrait
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from rich.console import Console

from aws_costlens.pdf_renderer import (
    bulletList,
    footerParagraph,
    formatServicesForList,
    keyValueTable,
    miniHeader,
    paragraphStyling,
    profileHeaderCard,
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
    Export cost dashboard to PDF format with improved styling.

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
        pagesize=portrait(letter),
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        allowSplitting=True,
    )
    styles = getSampleStyleSheet()
    story = []

    # Main Title
    story.append(Paragraph("AWS CostLens (Cost Report)", styles["Title"]))
    story.append(Spacer(1, 10))

    def _profile_separator() -> Table:
        separator = Table(
            [[" "]],
            colWidths=[doc.width],
            hAlign="LEFT",
        )
        separator.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 0.75, colors.HexColor("#BFBFBF")),
        ]))
        return separator

    # Period dates header
    story.append(paragraphStyling(
        f"<b>Previous Period:</b> {previous_period_dates}<br/>"
        f"<b>Current Period:</b> {current_period_dates}"
    ))
    story.append(Spacer(1, 6))

    for idx, profile_data in enumerate(export_data):
        # Header card per profile
        profile = profile_data.get("profile", "N/A")
        account_id = profile_data.get("account_id", "N/A")
        story.append(profileHeaderCard(profile, account_id, doc.width))
        story.append(Spacer(1, 6))

        # Cost summary with percentage change
        pct = profile_data.get("percent_change_in_total_cost")
        pct_str = f" ({pct:+.1f}%)" if pct is not None else ""
        kv_rows = [
            ("Previous Period Cost", f"<b>${profile_data.get('last_month', 0):,.2f}</b>"),
            ("Current Period Cost", f"<b>${profile_data.get('current_month', 0):,.2f}</b>{pct_str}"),
        ]
        story.append(keyValueTable(kv_rows))
        story.append(Spacer(1, 6))

        # Service comparison table
        story.append(miniHeader("Service Cost Comparison"))

        prev_services = profile_data.get("previous_service_costs", [])
        curr_services = profile_data.get("service_costs", [])

        prev_map = {svc: cost for svc, cost in prev_services}
        curr_map = {svc: cost for svc, cost in curr_services}
        services = sorted(set(prev_map) | set(curr_map), key=lambda s: curr_map.get(s, 0), reverse=True)

        table_rows = [
            [
                paragraphStyling("<b>Service</b>"),
                paragraphStyling("<b>Previous</b>"),
                paragraphStyling("<b>Current</b>"),
                paragraphStyling("<b>Diff</b>"),
                paragraphStyling("<b>Diff %</b>"),
            ]
        ]

        # Total row
        prev_total = float(profile_data.get("last_month", 0))
        curr_total = float(profile_data.get("current_month", 0))
        total_diff = curr_total - prev_total
        total_pct = (total_diff / prev_total * 100.0) if abs(prev_total) > 0.0001 else None
        table_rows.append([
            paragraphStyling("<b>Total costs</b>"),
            paragraphStyling(f"<b>${prev_total:,.2f}</b>"),
            paragraphStyling(f"<b>${curr_total:,.2f}</b>"),
            paragraphStyling(f"<b>${total_diff:,.2f}</b>"),
            paragraphStyling(f"<b>{total_pct:+.2f}%</b>" if total_pct is not None else "<b>N/A</b>"),
        ])

        for svc in services:
            prev_cost = float(prev_map.get(svc, 0.0))
            curr_cost = float(curr_map.get(svc, 0.0))
            if prev_cost < 0.0001 and curr_cost < 0.0001:
                continue
            diff = curr_cost - prev_cost
            diff_pct = (diff / prev_cost * 100.0) if abs(prev_cost) > 0.0001 else None
            table_rows.append([
                paragraphStyling(svc),
                paragraphStyling(f"${prev_cost:,.2f}"),
                paragraphStyling(f"${curr_cost:,.2f}"),
                paragraphStyling(f"${diff:,.2f}"),
                paragraphStyling(f"{diff_pct:+.2f}%" if diff_pct is not None else "N/A"),
            ])

        service_table = Table(
            table_rows,
            colWidths=[2.8 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch, 1.1 * inch],
            hAlign="LEFT",
        )
        service_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E1F2")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(service_table)
        story.append(Spacer(1, 8))

        # Budgets and EC2 side-by-side
        budgets = [clean_rich_tags(b) for b in profile_data.get("budget_info", ["No budgets configured"])]
        ec2_summary = profile_data.get("ec2_summary", {})
        ec2_items = [
            f"{state}: {count}"
            for state, count in ec2_summary.items()
            if count > 0
        ] or ["No instances"]

        info_table = Table(
            [
                [paragraphStyling("<b>Budgets</b>"), paragraphStyling("<b>EC2 Summary</b>")],
                [bulletList(budgets), bulletList(ec2_items)],
            ],
            colWidths=[doc.width / 2, doc.width / 2],
            hAlign="LEFT",
        )
        info_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(info_table)

        # Add spacing between profiles (not page break for better flow)
        if idx < len(export_data) - 1:
            story.append(Spacer(1, 8))
            story.append(_profile_separator())
            story.append(Spacer(1, 10))

    # Footer
    story.append(Spacer(1, 8))
    footer_text = f"Generated by AWS CostLens on {datetime.now():%Y-%m-%d %H:%M:%S}"
    story.append(footerParagraph(footer_text))

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
    Export audit/scan report to PDF with improved styling.

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
        pagesize=portrait(letter),
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        allowSplitting=True,
    )
    styles = getSampleStyleSheet()
    story = []

    # Main Title
    story.append(Paragraph("AWS CostLens (Scan Report)", styles["Title"]))
    story.append(Spacer(1, 8))

    def _profile_separator() -> Table:
        separator = Table(
            [[" "]],
            colWidths=[doc.width],
            hAlign="LEFT",
        )
        separator.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 0.75, colors.HexColor("#BFBFBF")),
        ]))
        return separator

    def _region_header(text: str) -> Table:
        header = Table(
            [[paragraphStyling(f"<b>{text}</b>")]],
            colWidths=[doc.width],
            hAlign="LEFT",
        )
        header.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F2F2")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return header

    def _chunk_rows(items: List[str], columns: int) -> List[List[str]]:
        rows = []
        row = []
        for item in items:
            row.append(item)
            if len(row) == columns:
                rows.append(row)
                row = []
        if row:
            row.extend([""] * (columns - len(row)))
            rows.append(row)
        return rows or [["None"] + [""] * (columns - 1)]

    def _render_region_items(title: str, region_map: Dict[str, List[str]], columns: int = 3) -> None:
        if title:
            story.append(miniHeader(title))
        if not region_map:
            story.append(paragraphStyling("None found"))
            story.append(Spacer(1, 6))
            return

        for region in sorted(region_map.keys()):
            items = region_map.get(region, []) or []
            story.append(_region_header(f"{region}:"))
            table_rows = _chunk_rows(items, columns)
            table = Table(
                table_rows,
                colWidths=[doc.width / columns] * columns,
                hAlign="LEFT",
            )
            table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(table)
            story.append(Spacer(1, 4))
        story.append(Spacer(1, 6))

    def _render_region_items_wrapped(title: str, region_map: Dict[str, List[str]], columns: int = 2) -> None:
        if title:
            story.append(miniHeader(title))
        if not region_map:
            story.append(paragraphStyling("None found"))
            story.append(Spacer(1, 6))
            return

        for region in sorted(region_map.keys()):
            items = region_map.get(region, []) or []
            story.append(_region_header(f"{region}:"))
            if not items:
                story.append(paragraphStyling("None found"))
                story.append(Spacer(1, 4))
                continue

            row_items = _chunk_rows(items, columns)
            table_rows = [
                [paragraphStyling(item) if item else paragraphStyling("") for item in row]
                for row in row_items
            ]
            table = Table(
                table_rows,
                colWidths=[doc.width / columns] * columns,
                hAlign="LEFT",
            )
            table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(table)
            story.append(Spacer(1, 4))
        story.append(Spacer(1, 6))

    for idx, data in enumerate(audit_data):
        # Header card per profile
        profile = data.get("profile", "Unknown")
        account_id = data.get("account_id", "Unknown")
        story.append(profileHeaderCard(profile, account_id, doc.width))
        story.append(Spacer(1, 6))

        # Untagged resources (service -> region -> ids)
        untagged = data.get("untagged_resources", {})
        if isinstance(untagged, dict):
            story.append(miniHeader("Untagged Resources"))
            has_any = False
            for service in sorted(untagged.keys()):
                region_map = untagged.get(service) or {}
                if not region_map:
                    continue
                has_any = True
                story.append(paragraphStyling(f"<b>{service}</b>"))
                _render_region_items_wrapped("", region_map, columns=2)
            if not has_any:
                story.append(paragraphStyling("None found"))
                story.append(Spacer(1, 6))
        else:
            story.append(miniHeader("Untagged Resources"))
            story.append(bulletList(split_to_items(untagged)))
            story.append(Spacer(1, 6))

        # Stopped EC2 instances (region -> ids)
        stopped = data.get("stopped_instances", {})
        if isinstance(stopped, dict):
            _render_region_items("Stopped EC2 Instances", stopped, columns=3)
        else:
            story.append(miniHeader("Stopped EC2 Instances"))
            story.append(bulletList(split_to_items(stopped)))
            story.append(Spacer(1, 6))

        # Unused EBS volumes (region -> ids)
        volumes = data.get("unused_volumes", {})
        if isinstance(volumes, dict):
            _render_region_items("Unused EBS Volumes", volumes, columns=3)
        else:
            story.append(miniHeader("Unused EBS Volumes"))
            story.append(bulletList(split_to_items(volumes)))
            story.append(Spacer(1, 6))

        # Unused EIPs (region -> ids)
        eips = data.get("unused_eips", {})
        if isinstance(eips, dict):
            _render_region_items("Unused Elastic IPs", eips, columns=3)
        else:
            story.append(miniHeader("Unused Elastic IPs"))
            story.append(bulletList(split_to_items(eips)))
            story.append(Spacer(1, 6))

        # Budget Alerts
        story.append(miniHeader("Budget Alerts"))
        budget_alerts = data.get("budget_alerts", "No budgets exceeded")
        if isinstance(budget_alerts, list):
            if not budget_alerts:
                story.append(paragraphStyling("No budgets exceeded"))
            else:
                budget_lines = []
                for b in budget_alerts:
                    if isinstance(b, dict):
                        if b.get("actual", 0) > b.get("limit", 0):
                            budget_lines.append(
                                f"{b.get('name', 'Budget')}: "
                                f"${b.get('actual', 0):,.2f} > ${b.get('limit', 0):,.2f}"
                            )
                    else:
                        budget_lines.append(str(b))
                story.append(bulletList(budget_lines or ["No budgets exceeded"]))
        else:
            story.append(bulletList(split_to_items(budget_alerts)))
        story.append(Spacer(1, 6))

        # Add spacing between profiles
        if idx < len(audit_data) - 1:
            story.append(Spacer(1, 8))
            story.append(_profile_separator())
            story.append(Spacer(1, 10))

    # Footer
    story.append(Spacer(1, 8))
    footer_note = (
        "Note: This scan checks stopped EC2, unattached EBS volumes, unused EIPs, "
        "untagged EC2/RDS/Lambda/ELBv2 resources, and budget alerts."
    )
    story.append(footerParagraph(footer_note))
    footer_text = f"Generated by AWS CostLens on {datetime.now():%Y-%m-%d %H:%M:%S}"
    story.append(footerParagraph(footer_text))

    doc.build(story)
    buffer.seek(0)
    pdf_bytes = buffer.read()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        console.print(f"[green]✓ Scan PDF saved to {output_path}[/]")

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
