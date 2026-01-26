"""Cost data processing and formatting controller."""

import csv
import json
import re
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from typing import Any, Dict, List, Optional, Tuple, Union

import xlsxwriter
from boto3.session import Session
from botocore.exceptions import ClientError
from rich.console import Console

from aws_costlens.aws_api import get_budgets
from aws_costlens.models import BudgetInfo, CostData, EC2Summary

# Force UTF-8 and modern Windows terminal mode for Unicode support
console = Console(force_terminal=True, legacy_windows=False)


def get_trend(session: Session, tags: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Get 6-month cost trend data from AWS Cost Explorer."""
    from aws_costlens.aws_api import get_account_id
    
    ce = session.client("ce", region_name="us-east-1")
    account_id = get_account_id(session)
    profile = session.profile_name

    today = datetime.today()
    end = today
    start = (end - timedelta(days=180)).replace(day=1)

    # Build filter if tags provided
    filter_param = None
    if tags:
        tag_filters = []
        for key, value in tags.items():
            tag_filters.append({
                "Tags": {
                    "Key": key,
                    "Values": [value],
                    "MatchOptions": ["EQUALS"],
                }
            })
        if len(tag_filters) == 1:
            filter_param = tag_filters[0]
        else:
            filter_param = {"And": tag_filters}

    try:
        kwargs: Dict[str, Any] = {
            "TimePeriod": {"Start": start.strftime("%Y-%m-%d"), "End": end.strftime("%Y-%m-%d")},
            "Granularity": "MONTHLY",
            "Metrics": ["UnblendedCost"],
        }
        if filter_param:
            kwargs["Filter"] = filter_param

        response = ce.get_cost_and_usage(**kwargs)
        results = response.get("ResultsByTime", [])
        monthly_costs: List[Tuple[str, float]] = []
        for r in results:
            period_start = r["TimePeriod"]["Start"]
            month = datetime.strptime(period_start, "%Y-%m-%d").strftime("%b %Y")
            amount = float(r["Total"]["UnblendedCost"]["Amount"])
            monthly_costs.append((month, amount))
        
        return {
            "monthly_costs": monthly_costs,
            "account_id": account_id,
            "profile": profile,
        }
    except ClientError as e:
        console.print(f"[bold red]Error fetching trend data: {e}[/]")
        return {"monthly_costs": [], "account_id": account_id, "profile": profile}


def get_cost_data(
    session: Session,
    time_range: Optional[Union[int, str]] = None,
    tags: Optional[Dict[str, str]] = None,
) -> CostData:
    """
    Get cost data from AWS Cost Explorer.

    Args:
        session: boto3 Session
        time_range: Optional int for days or string for custom range
        tags: Optional dict of tag filters
    """
    ce = session.client("ce", region_name="us-east-1")
    account_id = session.client("sts").get_caller_identity().get("Account")

    today = datetime.today()

    # Handle custom time range
    if time_range:
        # Check for "last-month" keyword (case-insensitive)
        if isinstance(time_range, str) and time_range.lower() == "last-month":
            # Last month (full calendar month) vs month before last (full calendar month)
            # Current period = previous calendar month
            current_end = today.replace(day=1)  # First day of current month
            current_start = (current_end - timedelta(days=1)).replace(day=1)  # First day of last month
            
            # Previous period = month before last
            previous_end = current_start  # First day of last month
            previous_start = (previous_end - timedelta(days=1)).replace(day=1)  # First day of month before last
            
            current_period_name = f"{current_start.strftime('%B %Y')} (last month)"
            previous_period_name = f"{previous_start.strftime('%B %Y')} (prior month)"
        
        elif isinstance(time_range, int):
            # N days: last N days vs previous N days
            current_start = today - timedelta(days=time_range)
            current_end = today
            previous_start = current_start - timedelta(days=time_range)
            previous_end = current_start
            current_period_name = f"Last {time_range} days"
            previous_period_name = f"Previous {time_range} days"
        
        else:
            # Parse custom date range like "2024-01-01:2024-01-31"
            parts = time_range.split(":")
            if len(parts) != 2:
                console.print(f"[bold red]Error: Invalid date range format '{time_range}'. Use YYYY-MM-DD:YYYY-MM-DD[/]")
                parts = [today.replace(day=1).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")]
            current_start = datetime.strptime(parts[0], "%Y-%m-%d")
            current_end = datetime.strptime(parts[1], "%Y-%m-%d")
            delta = (current_end - current_start).days
            previous_start = current_start - timedelta(days=delta)
            previous_end = current_start
            current_period_name = f"{parts[0]} to {parts[1]}"
            previous_period_name = f"{previous_start.strftime('%Y-%m-%d')} to {previous_end.strftime('%Y-%m-%d')}"
    else:
        # Default: current month (MTD) vs last month (full)
        current_start = today.replace(day=1)
        current_end = today
        
        # Edge case: if today is the 1st, add 1 day to avoid empty range
        if current_start == current_end:
            current_end = current_end + timedelta(days=1)
        
        previous_start = (current_start - timedelta(days=1)).replace(day=1)
        previous_end = current_start
        current_period_name = f"{today.strftime('%B %Y')} (MTD)"
        previous_period_name = f"{previous_start.strftime('%B %Y')} (full month)"

    # Build filter if tags provided
    filter_expr = None
    if tags:
        tag_filters = []
        for key, value in tags.items():
            tag_filters.append({"Tags": {"Key": key, "Values": [value]}})
        if len(tag_filters) == 1:
            filter_expr = tag_filters[0]
        else:
            filter_expr = {"And": tag_filters}

    def fetch_cost(start: datetime, end: datetime) -> Tuple[float, List[Dict]]:
        """Fetch cost for a period."""
        params: Dict[str, Any] = {
            "TimePeriod": {
                "Start": start.strftime("%Y-%m-%d"),
                "End": end.strftime("%Y-%m-%d"),
            },
            "Granularity": "MONTHLY",
            "Metrics": ["UnblendedCost"],
            "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
        }
        if filter_expr:
            params["Filter"] = filter_expr

        try:
            response = ce.get_cost_and_usage(**params)
            results = response.get("ResultsByTime", [])
            total = 0.0
            services: List[Dict] = []
            for r in results:
                for group in r.get("Groups", []):
                    service = group["Keys"][0]
                    amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                    total += amount
                    services.append({"service": service, "cost": amount})
            return total, services
        except ClientError as e:
            console.print(f"[bold red]Error fetching cost data: {e}[/]")
            return 0.0, []

    current_total, current_services = fetch_cost(current_start, current_end)
    previous_total, previous_services = fetch_cost(previous_start, previous_end)

    budgets = get_budgets(session)

    return {
        "account_id": account_id,
        "current_month": current_total,
        "last_month": previous_total,
        "current_month_cost_by_service": current_services,
        "previous_month_cost_by_service": previous_services,
        "budgets": budgets,
        "current_period_name": current_period_name,
        "previous_period_name": previous_period_name,
        "time_range": time_range,
        "current_period_start": current_start.strftime("%Y-%m-%d"),
        "current_period_end": current_end.strftime("%Y-%m-%d"),
        "previous_period_start": previous_start.strftime("%Y-%m-%d"),
        "previous_period_end": previous_end.strftime("%Y-%m-%d"),
        "monthly_costs": None,
    }


def process_service_costs(services: List[Dict]) -> Tuple[List[str], List[Tuple[str, float]]]:
    """Process and format ALL service costs sorted by amount."""
    service_costs_formatted: List[str] = []
    service_cost_data: List[Tuple[str, float]] = []
    
    # Sort by cost descending
    sorted_services = sorted(services, key=lambda x: x["cost"], reverse=True)
    
    for svc in sorted_services:
        cost = svc["cost"]
        name = svc["service"]
        if cost > 0.001:  # Only show services with meaningful cost
            service_cost_data.append((name, cost))
            service_costs_formatted.append(f"{name}: ${cost:,.2f}")
    
    if not service_cost_data:
        service_costs_formatted.append("No costs associated with this account")
    
    return service_costs_formatted, service_cost_data


def format_budget_info(budgets: List[BudgetInfo]) -> List[str]:
    """Format budget information for display."""
    if not budgets:
        return ["No budgets configured"]

    formatted = []
    for b in budgets:
        pct = (b["actual"] / b["limit"] * 100) if b["limit"] > 0 else 0
        status = "🟢" if pct < 80 else "🟡" if pct < 100 else "🔴"
        forecast_str = f", Forecast: ${b['forecast']:,.2f}" if b["forecast"] else ""
        formatted.append(
            f"{status} {b['name']}: ${b['actual']:,.2f} / ${b['limit']:,.2f} ({pct:.1f}%){forecast_str}"
        )
    return formatted


def format_ec2_summary(summary: EC2Summary) -> List[str]:
    """Format EC2 summary for display."""
    return [f"{state.capitalize()}: {count}" for state, count in summary.items()]


def change_in_total_cost(current: float, previous: float) -> Optional[float]:
    """Calculate percentage change in total cost."""
    if previous == 0:
        return None
    return ((current - previous) / previous) * 100


def export_to_csv(
    export_data: List[Dict],
    report_name: str,
    previous_period_dates: str,
    current_period_dates: str,
) -> str:
    """Export cost data to CSV format (summary view - one row per account).
    
    This format is more Excel-friendly, with each account on one row and
    multi-line data (services, budgets) within single cells.
    """
    output = StringIO()
    
    # Build dynamic column headers with period dates
    previous_period_header = f"Previous Period Cost\n({previous_period_dates})"
    current_period_header = f"Current Period Cost\n({current_period_dates})"
    
    fieldnames = [
        "CLI Profile",
        "AWS Account ID",
        previous_period_header,
        current_period_header,
        "Change %",
        "Previous Period Cost By Service",
        "Current Period Cost By Service",
        "Budget Status",
        "EC2 Instances",
    ]
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for profile_data in export_data:
        # Format previous services as multi-line string
        prev_services = profile_data.get("previous_service_costs", [])
        prev_services_str = "\n".join(
            f"{service}: ${cost:,.2f}" for service, cost in prev_services
        ) or "No costs"
        
        # Format current services as multi-line string
        curr_services = profile_data.get("service_costs", [])
        curr_services_str = "\n".join(
            f"{service}: ${cost:,.2f}" for service, cost in curr_services
        ) or "No costs"
        
        # Format budgets as multi-line string
        budgets = profile_data.get("budget_info", [])
        budgets_str = "\n".join(budgets) if budgets else "No budgets"
        
        # Format EC2 summary as multi-line string
        ec2_summary = profile_data.get("ec2_summary", {})
        ec2_str = "\n".join(
            f"{state}: {count}" 
            for state, count in ec2_summary.items() 
            if count > 0
        ) or "No instances"
        
        # Format percentage change
        pct = profile_data.get("percent_change_in_total_cost")
        pct_str = f"{pct:+.2f}%" if pct is not None else "N/A"
        
        writer.writerow({
            "CLI Profile": profile_data.get("profile", "N/A"),
            "AWS Account ID": profile_data.get("account_id", "N/A"),
            previous_period_header: f"${profile_data.get('last_month', 0):,.2f}",
            current_period_header: f"${profile_data.get('current_month', 0):,.2f}",
            "Change %": pct_str,
            "Previous Period Cost By Service": prev_services_str,
            "Current Period Cost By Service": curr_services_str,
            "Budget Status": budgets_str,
            "EC2 Instances": ec2_str,
        })
    
    return output.getvalue()


def export_to_json(
    export_data: List[Dict],
    report_name: str,
) -> str:
    """Export cost data to JSON format."""
    output = {
        "report_name": report_name,
        "generated": datetime.now().isoformat(),
        "profiles": []
    }
    
    for profile_data in export_data:
        profile_output = {
            "profile": profile_data.get("profile", "N/A"),
            "account_id": profile_data.get("account_id", "N/A"),
            "current_month_cost": profile_data.get("current_month", 0),
            "previous_month_cost": profile_data.get("last_month", 0),
            "percent_change": profile_data.get("percent_change_in_total_cost"),
            "current_services": profile_data.get("service_costs_formatted", []),
            "previous_services": profile_data.get("previous_service_costs_formatted", []),
            "budgets": profile_data.get("budget_info", []),
            "ec2_summary": profile_data.get("ec2_summary_formatted", []),
        }
        output["profiles"].append(profile_output)
    
    return json.dumps(output, indent=2)


def export_to_xlsx(
    export_data: List[Dict],
    report_name: str,
    previous_period_name: str,
    current_period_name: str,
    previous_period_dates: str,
    current_period_dates: str,
) -> bytes:
    """Export cost data to XLSX format (one sheet per account + global sheet)."""

    def safe_sheet_name(name: str, fallback: str, used_names: set) -> str:
        cleaned = re.sub(r"[\[\]\*:/\\?]", "", name).strip()
        if not cleaned:
            cleaned = fallback
        cleaned = cleaned[:31]
        base = cleaned
        counter = 1
        while cleaned in used_names:
            suffix = f"_{counter}"
            cleaned = (base[: 31 - len(suffix)] + suffix) if len(base) > 31 - len(suffix) else base + suffix
            counter += 1
        used_names.add(cleaned)
        return cleaned

    def build_service_rows(previous_services: List[Tuple[str, float]], current_services: List[Tuple[str, float]]):
        prev_map = {svc: cost for svc, cost in previous_services}
        curr_map = {svc: cost for svc, cost in current_services}
        services = set(prev_map) | set(curr_map)

        rows = []
        for svc in services:
            prev_cost = float(prev_map.get(svc, 0.0))
            curr_cost = float(curr_map.get(svc, 0.0))
            if prev_cost < 0.0001 and curr_cost < 0.0001:
                continue
            diff = curr_cost - prev_cost
            if abs(prev_cost) < 0.0001:
                diff_pct = None if abs(curr_cost) > 0.0001 else 0.0
            else:
                diff_pct = diff / prev_cost
            rows.append((svc, prev_cost, curr_cost, diff, diff_pct))

        rows.sort(key=lambda r: r[2], reverse=True)  # Sort by current cost
        return rows

    def write_cost_sheet(
        workbook,
        sheet_name: str,
        title: str,
        account_name: str,
        account_id: str,
        prev_total: float,
        curr_total: float,
        previous_services: List[Tuple[str, float]],
        current_services: List[Tuple[str, float]],
        table_name: str,
    ) -> None:
        worksheet = workbook.add_worksheet(sheet_name)

        # Formats
        title_fmt = workbook.add_format({"bold": True, "font_size": 14, "bg_color": "#FCE4D6"})
        meta_fmt = workbook.add_format({"bold": True})
        note_fmt = workbook.add_format({"italic": True, "font_color": "#666666"})
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1})
        currency_fmt = workbook.add_format({"num_format": "$#,##0.00"})
        percent_fmt = workbook.add_format({"num_format": "0.00%"})

        worksheet.set_column(0, 0, 42)
        worksheet.set_column(1, 3, 18)
        worksheet.set_column(4, 4, 18)

        row = 0
        worksheet.write(row, 0, title, title_fmt)
        row += 1
        worksheet.write(row, 0, f"Account Name: {account_name}", meta_fmt)
        row += 1
        worksheet.write(row, 0, f"Account ID: {account_id}", meta_fmt)
        row += 1
        worksheet.write(row, 0, f"Total Cost (both periods): ${prev_total + curr_total:,.2f}", meta_fmt)
        row += 1
        worksheet.write(row, 0, "Includes costs from ALL regions", note_fmt)
        row += 1
        worksheet.write(row, 0, "Services with $0.00 in both periods excluded", note_fmt)
        row += 2

        table_rows = []
        service_rows = build_service_rows(previous_services, current_services)

        # Total row
        total_diff = curr_total - prev_total
        total_pct = (total_diff / prev_total) if abs(prev_total) > 0.0001 else None
        table_rows.append((
            "Total costs (All Regions)",
            prev_total,
            curr_total,
            total_diff,
            total_pct,
        ))
        table_rows.extend(service_rows)

        header_row = row
        columns = [
            {"header": "Service", "format": header_fmt},
            {"header": f"{previous_period_name} (Global)", "format": header_fmt},
            {"header": f"{current_period_name} (Global)", "format": header_fmt},
            {"header": "Cost difference", "format": header_fmt},
            {"header": "Cost difference (%)", "format": header_fmt},
        ]

        last_row = header_row + len(table_rows)
        worksheet.add_table(
            header_row,
            0,
            last_row,
            4,
            {
                "name": table_name,
                "columns": columns,
                "data": table_rows,
                "style": "Table Style Light 9",
                "autofilter": True,
            },
        )

        # Apply number formats to data rows
        if table_rows:
            worksheet.set_row(header_row, None, header_fmt)
            worksheet.set_column(1, 3, 18, currency_fmt)
            worksheet.set_column(4, 4, 18, percent_fmt)

            # Conditional formatting for percent change
            worksheet.conditional_format(
                header_row + 1,
                4,
                last_row,
                4,
                {
                    "type": "cell",
                    "criteria": ">",
                    "value": 0,
                    "format": workbook.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"}),
                },
            )
            worksheet.conditional_format(
                header_row + 1,
                4,
                last_row,
                4,
                {
                    "type": "cell",
                    "criteria": "<",
                    "value": 0,
                    "format": workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"}),
                },
            )

            worksheet.freeze_panes(header_row + 1, 1)

    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})

    used_names = set()
    table_counter = 1

    # Global sheet (aggregate all profiles)
    global_prev_total = sum(p.get("last_month", 0) for p in export_data)
    global_curr_total = sum(p.get("current_month", 0) for p in export_data)
    global_prev_services: Dict[str, float] = {}
    global_curr_services: Dict[str, float] = {}

    for profile in export_data:
        for svc, cost in profile.get("previous_service_costs", []):
            global_prev_services[svc] = global_prev_services.get(svc, 0) + float(cost)
        for svc, cost in profile.get("service_costs", []):
            global_curr_services[svc] = global_curr_services.get(svc, 0) + float(cost)

    global_title = f"AWS Global Cost Comparison: {previous_period_name} vs {current_period_name}"
    global_sheet = safe_sheet_name("Global Cost Comparison", "Global", used_names)
    write_cost_sheet(
        workbook=workbook,
        sheet_name=global_sheet,
        title=global_title,
        account_name="All Accounts",
        account_id="Multiple",
        prev_total=global_prev_total,
        curr_total=global_curr_total,
        previous_services=list(global_prev_services.items()),
        current_services=list(global_curr_services.items()),
        table_name=f"CostTable{table_counter}",
    )
    table_counter += 1

    # One sheet per account/profile
    for profile_data in export_data:
        profile_name = profile_data.get("profile", "Unknown")
        account_id = profile_data.get("account_id", "Unknown")
        sheet_name = safe_sheet_name(profile_name, f"Account{table_counter}", used_names)
        write_cost_sheet(
            workbook=workbook,
            sheet_name=sheet_name,
            title="Global Cost Analysis",
            account_name=profile_name,
            account_id=account_id,
            prev_total=float(profile_data.get("last_month", 0)),
            curr_total=float(profile_data.get("current_month", 0)),
            previous_services=profile_data.get("previous_service_costs", []),
            current_services=profile_data.get("service_costs", []),
            table_name=f"CostTable{table_counter}",
        )
        table_counter += 1

    workbook.close()
    output.seek(0)
    return output.read()
