"""Monte Carlo simulation result visualizations."""

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

from ui.theme import format_currency


def plot_cost_histogram(
    simulation_results: dict[str, pd.DataFrame],
    budget: float = None,
    title: str = "Realized Cost Distribution",
    height: int = 450,
) -> go.Figure:
    """Overlapping histograms of realized costs for different solutions.

    Args:
        simulation_results: Dict mapping solution label -> simulation DataFrame
        budget: Optional budget line to draw
        title: Chart title
    """
    fig = go.Figure()

    colors = ["#1976D2", "#FF9800", "#4CAF50", "#F44336", "#9C27B0"]

    for i, (label, df) in enumerate(simulation_results.items()):
        color = colors[i % len(colors)]
        fig.add_trace(
            go.Histogram(
                x=df["realized_total_cost"],
                name=label,
                opacity=0.6,
                marker_color=color,
                nbinsx=50,
            )
        )

    if budget is not None:
        fig.add_vline(
            x=budget,
            line_dash="dash",
            line_color="red",
            line_width=2,
            annotation_text=f"Budget: {format_currency(budget)}",
            annotation_position="top right",
        )

    fig.update_layout(
        title=title,
        height=height,
        barmode="overlay",
        xaxis_title="Realized Total Cost ($)",
        yaxis_title="Frequency",
        xaxis=dict(tickprefix="$", tickformat=","),
    )

    return fig


def plot_feasibility_curve(
    feasibility_data: list[dict],
    title: str = "Theoretical vs. Empirical Feasibility",
    height: int = 400,
) -> go.Figure:
    """Plot theoretical robustness level vs empirical feasibility rate.

    Args:
        feasibility_data: List of dicts with 'robustness_level', 'empirical_feasibility'
    """
    fig = go.Figure()

    xs = [d["robustness_level"] for d in feasibility_data]
    ys = [d["empirical_feasibility"] for d in feasibility_data]

    # Theoretical reference (perfect calibration line)
    fig.add_trace(
        go.Scatter(
            x=[0.5, 1.0],
            y=[0.5, 1.0],
            mode="lines",
            name="Perfect Calibration",
            line=dict(color="rgba(0,0,0,0.3)", dash="dash"),
        )
    )

    # Empirical data
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="lines+markers",
            name="Empirical",
            line=dict(color="#1976D2", width=2),
            marker=dict(size=8),
        )
    )

    fig.update_layout(
        title=title,
        height=height,
        xaxis_title="Theoretical Robustness Level",
        yaxis_title="Empirical Feasibility Rate",
        xaxis=dict(tickformat=".0%", range=[0.45, 1.01]),
        yaxis=dict(tickformat=".0%", range=[0.45, 1.01]),
    )

    return fig


def plot_empirical_cdf(
    simulation_results: dict[str, pd.DataFrame],
    budget: float = None,
    title: str = "Empirical CDF of Realized Cost",
    height: int = 400,
) -> go.Figure:
    """Plot empirical CDFs of realized costs for multiple solutions."""
    fig = go.Figure()

    colors = ["#1976D2", "#FF9800", "#4CAF50", "#F44336", "#9C27B0"]

    for i, (label, df) in enumerate(simulation_results.items()):
        sorted_costs = np.sort(df["realized_total_cost"].values)
        cdf = np.arange(1, len(sorted_costs) + 1) / len(sorted_costs)
        color = colors[i % len(colors)]

        fig.add_trace(
            go.Scatter(
                x=sorted_costs,
                y=cdf,
                mode="lines",
                name=label,
                line=dict(color=color, width=2),
            )
        )

    if budget is not None:
        fig.add_vline(
            x=budget,
            line_dash="dash",
            line_color="red",
            line_width=2,
            annotation_text=f"Budget: {format_currency(budget)}",
        )

    fig.update_layout(
        title=title,
        height=height,
        xaxis_title="Realized Total Cost ($)",
        yaxis_title="Cumulative Probability",
        xaxis=dict(tickprefix="$", tickformat=","),
        yaxis=dict(tickformat=".0%"),
    )

    return fig
