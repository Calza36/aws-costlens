"""Cost data processing and formatting controller."""

import csv
import json
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple, Union

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
    """Export cost data to CSV format."""
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(["AWS CostLens Report"])
    writer.writerow(["Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    writer.writerow([])

    writer.writerow(["Profile", "Account ID", "Section", "Item", "Value"])

    for profile_data in export_data:
        profile = profile_data.get("profile", "N/A")
        account_id = profile_data.get("account_id", "N/A")

        # Summary section
        writer.writerow([
            profile,
            account_id,
            "Summary",
            f"Previous ({previous_period_dates})",
            f"${profile_data.get('last_month', 0):,.2f}",
        ])
        writer.writerow([
            profile,
            account_id,
            "Summary",
            f"Current ({current_period_dates})",
            f"${profile_data.get('current_month', 0):,.2f}",
        ])
        pct = profile_data.get("percent_change_in_total_cost")
        if pct is not None:
            writer.writerow([profile, account_id, "Summary", "Change", f"{pct:+.2f}%"])

        # Previous period services
        prev_services = profile_data.get("previous_service_costs", [])
        if prev_services:
            for service, cost in prev_services:
                writer.writerow([profile, account_id, "Previous Service Costs", service, f"${cost:,.2f}"])
        else:
            writer.writerow([profile, account_id, "Previous Service Costs", "None", ""])

        # Current period services
        curr_services = profile_data.get("service_costs", [])
        if curr_services:
            for service, cost in curr_services:
                writer.writerow([profile, account_id, "Current Service Costs", service, f"${cost:,.2f}"])
        else:
            writer.writerow([profile, account_id, "Current Service Costs", "None", ""])

        # Budgets
        budgets = profile_data.get("budget_info", [])
        if budgets:
            for budget_line in budgets:
                writer.writerow([profile, account_id, "Budgets", "", budget_line])
        else:
            writer.writerow([profile, account_id, "Budgets", "None", ""])

        # EC2 summary
        ec2_summary = profile_data.get("ec2_summary", {})
        if ec2_summary:
            for state in sorted(ec2_summary.keys()):
                writer.writerow([profile, account_id, "EC2 Summary", state, str(ec2_summary[state])])
        else:
            writer.writerow([profile, account_id, "EC2 Summary", "None", ""])

        writer.writerow([])

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
