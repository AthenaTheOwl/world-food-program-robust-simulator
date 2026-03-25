"""Robustness-cost tradeoff (Pareto frontier) visualization."""

import plotly.graph_objects as go

from models.solver_utils import SolutionResult
from ui.theme import format_currency


def plot_tradeoff_curve(
    solutions: list[SolutionResult],
    x_field: str = "robustness_level",
    y_field: str = "total_cost",
    highlight_idx: int = None,
    title: str = "Cost vs. Robustness Tradeoff",
    height: int = 450,
) -> go.Figure:
    """Plot the Pareto frontier of robustness level vs. cost (or nutrient slack).

    Args:
        solutions: List of SolutionResults at different robustness levels
        x_field: Field for x-axis ('robustness_level')
        y_field: Field for y-axis ('total_cost' or 'nutrient_slack')
        highlight_idx: Index of current operating point to highlight
        title: Chart title
    """
    fig = go.Figure()

    xs = [getattr(s, x_field) for s in solutions]
    ys = [getattr(s, y_field) for s in solutions]

    # Format hover text
    hover_texts = []
    for s in solutions:
        parts = [
            f"Robustness: {s.robustness_level:.1%}",
            f"Total Cost: {format_currency(s.total_cost)}",
            f"Slack: {s.nutrient_slack:.3f}",
            f"Cost/Person: {format_currency(s.cost_per_person)}",
            f"Intl Procurement: {s.international_procurement_ratio:.1%}",
        ]
        hover_texts.append("<br>".join(parts))

    # Main curve
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="lines+markers",
            name="Solutions",
            line=dict(color="#1976D2", width=2),
            marker=dict(size=8, color="#1976D2"),
            hovertext=hover_texts,
            hoverinfo="text",
        )
    )

    # Highlight current point
    if highlight_idx is not None and 0 <= highlight_idx < len(solutions):
        fig.add_trace(
            go.Scatter(
                x=[xs[highlight_idx]],
                y=[ys[highlight_idx]],
                mode="markers",
                name="Current",
                marker=dict(size=16, color="#F44336", symbol="star"),
                hovertext=[hover_texts[highlight_idx]],
                hoverinfo="text",
            )
        )

    x_label = "Robustness Level (p)" if x_field == "robustness_level" else x_field
    y_label = "Total Cost ($)" if y_field == "total_cost" else y_field.replace("_", " ").title()

    fig.update_layout(
        title=title,
        height=height,
        xaxis_title=x_label,
        yaxis_title=y_label,
        xaxis=dict(tickformat=".0%") if x_field == "robustness_level" else {},
        yaxis=dict(tickprefix="$", tickformat=",") if "cost" in y_field else {},
    )

    return fig
