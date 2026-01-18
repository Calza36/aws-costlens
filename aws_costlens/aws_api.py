"""AWS API client functions for CostLens."""

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence

import boto3
from boto3.session import Session
from botocore.exceptions import ClientError
from rich.console import Console

from aws_costlens.models import BudgetInfo, EC2Summary, RegionName

# Force UTF-8 and modern Windows terminal mode for Unicode support
console = Console(force_terminal=True, legacy_windows=False)


def _chunked(items: Sequence[str], size: int) -> Iterable[List[str]]:
    """Yield chunks of a list."""
    for i in range(0, len(items), size):
        yield list(items[i : i + size])


def get_aws_profiles() -> List[str]:
    """Get all configured AWS profiles from the AWS CLI configuration."""
    try:
        session = boto3.Session()
        return session.available_profiles
    except Exception as e:
        console.print(f"[bold red]Error getting AWS profiles: {str(e)}[/]")
        return []


def get_account_id(session: Session) -> Optional[str]:
    """Get the AWS account ID for a session."""
    try:
        account_id = session.client("sts").get_caller_identity().get("Account")
        return str(account_id) if account_id is not None else None
    except Exception as e:
        console.log(f"[yellow]Warning: Could not get account ID: {str(e)}[/]")
        return None


def get_all_regions(session: Session) -> List[RegionName]:
    """
    Get all available AWS regions.
    Using us-east-1 as a default region to get the list of all regions.

    If the call fails, it will return a hardcoded list of common regions.
    """
    try:
        ec2_client = session.client("ec2", region_name="us-east-1")
        regions = [
            region["RegionName"] for region in ec2_client.describe_regions()["Regions"]
        ]
        return regions
    except Exception as e:
        console.log(f"[yellow]Warning: Could not get all regions: {str(e)}[/]")
        return [
            "us-east-1",
            "us-east-2",
            "us-west-1",
            "us-west-2",
            "ap-southeast-1",
            "ap-south-1",
            "eu-west-1",
            "eu-west-2",
            "eu-central-1",
        ]


def get_accessible_regions(session: Session) -> List[RegionName]:
    """Get regions that are accessible with the current credentials."""
    all_regions = get_all_regions(session)
    accessible_regions = []

    for region in all_regions:
        try:
            ec2_client = session.client("ec2", region_name=region)
            ec2_client.describe_instances(MaxResults=5)
            accessible_regions.append(region)
        except Exception:
            console.log(
                f"[yellow]Region {region} is not accessible with the current credentials[/]"
            )

    if not accessible_regions:
        console.log("[yellow]No accessible regions found. Using default regions.[/]")
        return ["us-east-1", "us-east-2", "us-west-1", "us-west-2"]

    return accessible_regions


def ec2_summary(
    session: Session, regions: Optional[List[RegionName]] = None
) -> EC2Summary:
    """Get EC2 instance summary across specified regions or all regions."""
    if regions is None:
        regions = [
            "us-east-1",
            "us-east-2",
            "us-west-1",
            "us-west-2",
            "ap-southeast-1",
            "ap-south-1",
            "eu-central-1",
            "eu-west-1",
            "eu-west-2",
        ]

    instance_summary: EC2Summary = defaultdict(int)

    for region in regions:
        try:
            ec2_regional = session.client("ec2", region_name=region)
            paginator = ec2_regional.get_paginator("describe_instances")
            for page in paginator.paginate():
                for reservation in page.get("Reservations", []):
                    for instance in reservation.get("Instances", []):
                        state = instance["State"]["Name"]
                        instance_summary[state] += 1
        except Exception as e:
            console.log(
                f"[yellow]Warning: Could not access EC2 in region {region}: {str(e)}[/]"
            )

    # Ensure key states are always present for consistent display
    if "running" not in instance_summary:
        instance_summary["running"] = 0
    if "stopped" not in instance_summary:
        instance_summary["stopped"] = 0
    if "terminated" not in instance_summary:
        instance_summary["terminated"] = 0

    return instance_summary


def get_stopped_instances(
    session: Session, regions: List[RegionName]
) -> Dict[RegionName, List[str]]:
    """Get stopped EC2 instances per region."""
    stopped = {}
    for region in regions:
        try:
            ec2 = session.client("ec2", region_name=region)
            paginator = ec2.get_paginator("describe_instances")
            ids = []
            for page in paginator.paginate(
                Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
            ):
                ids.extend(
                    inst["InstanceId"]
                    for res in page.get("Reservations", [])
                    for inst in res.get("Instances", [])
                )
            if ids:
                stopped[region] = ids
        except Exception as e:
            console.log(
                f"[yellow]Warning: Could not fetch stopped instances in {region}: {str(e)}[/]"
            )
    return stopped


def get_unused_volumes(
    session: Session, regions: List[RegionName]
) -> Dict[RegionName, List[str]]:
    """Get unattached EBS volumes per region."""
    unused = {}
    for region in regions:
        try:
            ec2 = session.client("ec2", region_name=region)
            paginator = ec2.get_paginator("describe_volumes")
            vols = []
            for page in paginator.paginate(
                Filters=[{"Name": "status", "Values": ["available"]}]
            ):
                vols.extend(vol["VolumeId"] for vol in page.get("Volumes", []))
            if vols:
                unused[region] = vols
        except Exception as e:
            console.log(
                f"[yellow]Warning: Could not fetch unused volumes in {region}: {str(e)}[/]"
            )
    return unused


def get_unused_eips(
    session: Session, regions: List[RegionName]
) -> Dict[RegionName, List[str]]:
    """Get unused Elastic IPs per region."""
    eips = {}
    for region in regions:
        try:
            ec2 = session.client("ec2", region_name=region)
            free = []
            response = ec2.describe_addresses()
            free.extend(
                addr["PublicIp"]
                for addr in response.get("Addresses", [])
                if not addr.get("AssociationId")
            )
            # Handle manual pagination if NextToken is present
            while response.get("NextToken"):
                response = ec2.describe_addresses(NextToken=response["NextToken"])
                free.extend(
                    addr["PublicIp"]
                    for addr in response.get("Addresses", [])
                    if not addr.get("AssociationId")
                )
            if free:
                eips[region] = free
        except Exception as e:
            console.log(
                f"[yellow]Warning: Could not fetch EIPs in {region}: {str(e)}[/]"
            )
    return eips


def get_untagged_resources(
    session: Session, regions: List[str]
) -> Dict[str, Dict[str, List[str]]]:
    """Get resources without tags across EC2, RDS, Lambda, and ELBv2."""
    result: Dict[str, Dict[str, List[str]]] = {
        "EC2": {},
        "RDS": {},
        "Lambda": {},
        "ELBv2": {},
    }

    for region in regions:
        # EC2
        try:
            ec2 = session.client("ec2", region_name=region)
            paginator = ec2.get_paginator("describe_instances")
            for page in paginator.paginate():
                for reservation in page.get("Reservations", []):
                    for instance in reservation.get("Instances", []):
                        if not instance.get("Tags"):
                            result["EC2"].setdefault(region, []).append(
                                instance["InstanceId"]
                            )
        except Exception as e:
            console.log(
                f"[yellow]Warning: Could not fetch EC2 instances in {region}: {str(e)}[/]"
            )

        # RDS
        try:
            rds = session.client("rds", region_name=region)
            paginator = rds.get_paginator("describe_db_instances")
            for page in paginator.paginate():
                for db_instance in page.get("DBInstances", []):
                    arn = db_instance["DBInstanceArn"]
                    tags = rds.list_tags_for_resource(ResourceName=arn).get(
                        "TagList", []
                    )
                    if not tags:
                        result["RDS"].setdefault(region, []).append(
                            db_instance["DBInstanceIdentifier"]
                        )
        except Exception as e:
            console.log(
                f"[yellow]Warning: Could not fetch RDS instances in {region}: {str(e)}[/]"
            )

        # Lambda
        try:
            lambda_client = session.client("lambda", region_name=region)
            paginator = lambda_client.get_paginator("list_functions")
            for page in paginator.paginate():
                for function in page.get("Functions", []):
                    arn = function["FunctionArn"]
                    tags = lambda_client.list_tags(Resource=arn).get("Tags", {})
                    if not tags:
                        result["Lambda"].setdefault(region, []).append(
                            function["FunctionName"]
                        )
        except Exception as e:
            console.log(
                f"[yellow]Warning: Could not fetch Lambda functions in {region}: {str(e)}[/]"
            )

        # ELBv2
        try:
            elbv2 = session.client("elbv2", region_name=region)
            lbs = []
            paginator = elbv2.get_paginator("describe_load_balancers")
            for page in paginator.paginate():
                lbs.extend(page.get("LoadBalancers", []))

            if lbs:
                arn_to_name = {
                    lb["LoadBalancerArn"]: lb["LoadBalancerName"] for lb in lbs
                }
                arns = list(arn_to_name.keys())
                for arn_batch in _chunked(arns, 20):
                    tags_response = elbv2.describe_tags(ResourceArns=arn_batch)
                    for desc in tags_response.get("TagDescriptions", []):
                        arn = desc["ResourceArn"]
                        if not desc.get("Tags"):
                            lb_name = arn_to_name.get(arn, arn)
                            result["ELBv2"].setdefault(region, []).append(lb_name)
        except Exception as e:
            console.log(
                f"[yellow]Warning: Could not fetch ELBv2 load balancers in {region}: {str(e)}[/]"
            )

    return result


def get_budgets(session: Session) -> List[BudgetInfo]:
    """Get AWS Budgets for the account."""
    account_id = get_account_id(session)
    budgets = session.client("budgets", region_name="us-east-1")

    budgets_data: List[BudgetInfo] = []
    try:
        paginator = budgets.get_paginator("describe_budgets")
        for page in paginator.paginate(AccountId=account_id):
            for budget in page.get("Budgets", []):
                budgets_data.append(
                    {
                        "name": budget["BudgetName"],
                        "limit": float(budget["BudgetLimit"]["Amount"]),
                        "actual": float(
                            budget["CalculatedSpend"]["ActualSpend"]["Amount"]
                        ),
                        "forecast": float(
                            budget["CalculatedSpend"]
                            .get("ForecastedSpend", {})
                            .get("Amount", 0.0)
                        )
                        or None,
                    }
                )
    except Exception as e:
        pass

    return budgets_data
