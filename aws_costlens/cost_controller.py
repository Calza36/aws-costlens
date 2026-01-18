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

console = Console()


def get_trend(session: Session) -> Optional[List[Tuple[str, float]]]:
    """Get 6-month cost trend data from AWS Cost Explorer."""
    ce = session.client("ce", region_name="us-east-1")

    today = datetime.today()
    end = today.replace(day=1)
    start = (end - timedelta(days=180)).replace(day=1)

    try:
        response = ce.get_cost_and_usage(
            TimePeriod={"Start": start.strftime("%Y-%m-%d"), "End": end.strftime("%Y-%m-%d")},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
        )
        results = response.get("ResultsByTime", [])
        monthly_costs: List[Tuple[str, float]] = []
        for r in results:
            period_start = r["TimePeriod"]["Start"]
            amount = float(r["Total"]["UnblendedCost"]["Amount"])
            monthly_costs.append((period_start[:7], amount))
        return monthly_costs
    except ClientError as e:
        console.print(f"[bold red]Error fetching trend data: {e}[/]")
        return None


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
        if isinstance(time_range, int):
            current_start = today - timedelta(days=time_range)
            current_end = today
            previous_start = current_start - timedelta(days=time_range)
            previous_end = current_start
            current_period_name = f"Last {time_range} days"
            previous_period_name = f"Previous {time_range} days"
        else:
            # Parse custom date range like "2024-01-01:2024-01-31"
            parts = time_range.split(":")
            current_start = datetime.strptime(parts[0], "%Y-%m-%d")
            current_end = datetime.strptime(parts[1], "%Y-%m-%d")
            delta = (current_end - current_start).days
            previous_start = current_start - timedelta(days=delta)
            previous_end = current_start
            current_period_name = f"{parts[0]} to {parts[1]}"
            previous_period_name = f"{previous_start.strftime('%Y-%m-%d')} to {previous_end.strftime('%Y-%m-%d')}"
    else:
        # Default: current month vs last month
        current_start = today.replace(day=1)
        current_end = today
        previous_start = (current_start - timedelta(days=1)).replace(day=1)
        previous_end = current_start - timedelta(days=1)
        current_period_name = today.strftime("%B %Y")
        previous_period_name = previous_start.strftime("%B %Y")

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


def process_service_costs(services: List[Dict], top_n: int = 5) -> List[Tuple[str, float]]:
    """Process and sort service costs, returning top N."""
    sorted_services = sorted(services, key=lambda x: x["cost"], reverse=True)
    return [(s["service"], s["cost"]) for s in sorted_services[:top_n]]


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
    profile_data: Dict,
    current_period: str,
    previous_period: str,
) -> str:
    """Export cost data to CSV format."""
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(["AWS Cost Report"])
    writer.writerow(["Profile", profile_data.get("profile", "N/A")])
    writer.writerow(["Account ID", profile_data.get("account_id", "N/A")])
    writer.writerow([])

    writer.writerow(["Period", "Total Cost"])
    writer.writerow([current_period, f"${profile_data.get('current_month', 0):,.2f}"])
    writer.writerow([previous_period, f"${profile_data.get('last_month', 0):,.2f}"])
    writer.writerow([])

    writer.writerow([f"Top Services - {current_period}"])
    writer.writerow(["Service", "Cost"])
    for service, cost in profile_data.get("service_costs", []):
        writer.writerow([service, f"${cost:,.2f}"])
    writer.writerow([])

    writer.writerow(["Budgets"])
    for budget in profile_data.get("budget_info", []):
        writer.writerow([budget])
    writer.writerow([])

    writer.writerow(["EC2 Summary"])
    for item in profile_data.get("ec2_summary_formatted", []):
        writer.writerow([item])

    return output.getvalue()


def export_to_json(
    profile_data: Dict,
    current_period: str,
    previous_period: str,
) -> str:
    """Export cost data to JSON format."""
    data = {
        "profile": profile_data.get("profile", "N/A"),
        "account_id": profile_data.get("account_id", "N/A"),
        "periods": {
            "current": {
                "name": current_period,
                "total_cost": profile_data.get("current_month", 0),
                "top_services": [
                    {"service": svc, "cost": cost}
                    for svc, cost in profile_data.get("service_costs", [])
                ],
            },
            "previous": {
                "name": previous_period,
                "total_cost": profile_data.get("last_month", 0),
                "top_services": [
                    {"service": svc, "cost": cost}
                    for svc, cost in profile_data.get("previous_service_costs", [])
                ],
            },
        },
        "percent_change": profile_data.get("percent_change_in_total_cost"),
        "budgets": profile_data.get("budget_info", []),
        "ec2_summary": profile_data.get("ec2_summary", {}),
    }
    return json.dumps(data, indent=2)
