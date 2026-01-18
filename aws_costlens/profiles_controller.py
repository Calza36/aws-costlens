"""Profile processing controller for AWS CostLens."""

from typing import Dict, List, Optional, Union

import boto3
from rich.console import Console

from aws_costlens.aws_api import ec2_summary, get_account_id
from aws_costlens.cost_controller import (
    change_in_total_cost,
    format_budget_info,
    format_ec2_summary,
    get_cost_data,
    process_service_costs,
)
from aws_costlens.models import ProfileData

# Force UTF-8 and modern Windows terminal mode for Unicode support
console = Console(force_terminal=True, legacy_windows=False)


def process_single_profile(
    profile: str,
    regions: Optional[List[str]] = None,
    time_range: Optional[Union[int, str]] = None,
    tags: Optional[Dict[str, str]] = None,
) -> ProfileData:
    """
    Process cost and resource data for a single AWS profile.

    Args:
        profile: AWS CLI profile name
        regions: Optional list of regions to check
        time_range: Optional time range for cost data
        tags: Optional tag filters

    Returns:
        ProfileData dict with all processed information
    """
    try:
        session = boto3.Session(profile_name=profile)
        account_id = get_account_id(session) or "Unknown"

        # Get cost data
        cost_data = get_cost_data(session, time_range=time_range, tags=tags)

        # Process service costs
        current_services = process_service_costs(
            cost_data["current_month_cost_by_service"]
        )
        previous_services = process_service_costs(
            cost_data["previous_month_cost_by_service"]
        )

        # Get EC2 summary
        ec2_data = ec2_summary(session, regions)

        # Calculate percent change
        pct_change = change_in_total_cost(
            cost_data["current_month"], cost_data["last_month"]
        )

        return {
            "profile": profile,
            "account_id": account_id,
            "last_month": cost_data["last_month"],
            "current_month": cost_data["current_month"],
            "service_costs": current_services,
            "service_costs_formatted": [
                f"{svc}: ${cost:,.2f}" for svc, cost in current_services
            ],
            "previous_service_costs": previous_services,
            "previous_service_costs_formatted": [
                f"{svc}: ${cost:,.2f}" for svc, cost in previous_services
            ],
            "budget_info": format_budget_info(cost_data["budgets"]),
            "ec2_summary": dict(ec2_data),
            "ec2_summary_formatted": format_ec2_summary(ec2_data),
            "success": True,
            "error": None,
            "current_period_name": cost_data["current_period_name"],
            "previous_period_name": cost_data["previous_period_name"],
            "percent_change_in_total_cost": pct_change,
        }

    except Exception as e:
        console.print(f"[bold red]Error processing profile {profile}: {str(e)}[/]")
        return {
            "profile": profile,
            "account_id": "Error",
            "last_month": 0.0,
            "current_month": 0.0,
            "service_costs": [],
            "service_costs_formatted": [],
            "previous_service_costs": [],
            "previous_service_costs_formatted": [],
            "budget_info": [],
            "ec2_summary": {},
            "ec2_summary_formatted": [],
            "success": False,
            "error": str(e),
            "current_period_name": "N/A",
            "previous_period_name": "N/A",
            "percent_change_in_total_cost": None,
        }


def process_combined_profiles(
    account_id: str,
    profiles: List[str],
    regions: Optional[List[str]] = None,
    time_range: Optional[Union[int, str]] = None,
    tags: Optional[Dict[str, str]] = None,
) -> ProfileData:
    """
    Process and merge cost data from multiple profiles for the same account.

    This aggregates costs across profiles that belong to the same account,
    providing a unified view.

    Args:
        account_id: The AWS account ID
        profiles: List of AWS CLI profile names
        regions: Optional list of regions
        time_range: Optional time range
        tags: Optional tag filters

    Returns:
        Merged ProfileData
    """
    combined: ProfileData = {
        "profile": ", ".join(profiles),
        "account_id": "Merged",
        "last_month": 0.0,
        "current_month": 0.0,
        "service_costs": [],
        "service_costs_formatted": [],
        "previous_service_costs": [],
        "previous_service_costs_formatted": [],
        "budget_info": [],
        "ec2_summary": {"running": 0, "stopped": 0},
        "ec2_summary_formatted": [],
        "success": True,
        "error": None,
        "current_period_name": "Merged",
        "previous_period_name": "Merged",
        "percent_change_in_total_cost": None,
    }

    service_totals: Dict[str, float] = {}
    prev_service_totals: Dict[str, float] = {}
    account_ids = set()
    all_budgets: List[str] = []

    for profile in profiles:
        data = process_single_profile(profile, regions, time_range, tags)
        if not data["success"]:
            continue

        account_ids.add(data["account_id"])
        combined["last_month"] += data["last_month"]
        combined["current_month"] += data["current_month"]

        # Aggregate service costs
        for svc, cost in data["service_costs"]:
            service_totals[svc] = service_totals.get(svc, 0) + cost

        for svc, cost in data["previous_service_costs"]:
            prev_service_totals[svc] = prev_service_totals.get(svc, 0) + cost

        # Aggregate EC2
        for state, count in data["ec2_summary"].items():
            combined["ec2_summary"][state] = combined["ec2_summary"].get(state, 0) + count

        # Collect budgets
        all_budgets.extend(data["budget_info"])

        # Use first successful profile's period names
        if combined["current_period_name"] == "Merged":
            combined["current_period_name"] = data["current_period_name"]
            combined["previous_period_name"] = data["previous_period_name"]

    # Sort and format merged service costs
    sorted_current = sorted(service_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    sorted_previous = sorted(prev_service_totals.items(), key=lambda x: x[1], reverse=True)[:5]

    combined["service_costs"] = sorted_current
    combined["service_costs_formatted"] = [
        f"{svc}: ${cost:,.2f}" for svc, cost in sorted_current
    ]
    combined["previous_service_costs"] = sorted_previous
    combined["previous_service_costs_formatted"] = [
        f"{svc}: ${cost:,.2f}" for svc, cost in sorted_previous
    ]

    combined["account_id"] = ", ".join(sorted(account_ids))
    combined["budget_info"] = all_budgets if all_budgets else ["No budgets configured"]
    combined["ec2_summary_formatted"] = format_ec2_summary(combined["ec2_summary"])

    # Calculate merged percent change
    combined["percent_change_in_total_cost"] = change_in_total_cost(
        combined["current_month"], combined["last_month"]
    )

    return combined
