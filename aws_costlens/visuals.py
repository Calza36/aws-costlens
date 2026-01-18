"""Visualization functions for cost data charts."""

from typing import List, Tuple

from rich.console import Console
from rich.panel import Panel


def create_trend_bars(monthly_costs: List[Tuple[str, float]], max_width: int = 40) -> Panel:
    """
    Create ASCII bar chart for cost history.

    Args:
        monthly_costs: List of (month, cost) tuples
        max_width: Maximum width of bars
    """
    console = Console()

    if not monthly_costs:
        return Panel("[yellow]No cost history available[/]", title="📈 Cost History")

    max_cost = max(cost for _, cost in monthly_costs) if monthly_costs else 1
    lines = []

    for month, cost in monthly_costs:
        bar_width = int((cost / max_cost) * max_width) if max_cost > 0 else 0
        bar = "█" * bar_width
        # Color based on relative cost
        if cost == max_cost:
            color = "red"
        elif cost > max_cost * 0.7:
            color = "yellow"
        else:
            color = "green"
        lines.append(f"[dim]{month}[/] [{color}]{bar}[/] [bold]${cost:,.2f}[/]")

    content = "\n".join(lines)
    return Panel(content, title="📈 Cost History (6 months)", border_style="blue")
