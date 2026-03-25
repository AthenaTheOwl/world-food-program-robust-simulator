"""Nutrition fulfillment radar/spider chart."""

import plotly.graph_objects as go

from core.scenario import Scenario
from models.solver_utils import SolutionResult


def plot_nutrition_radar(
    scenario: Scenario,
    solutions: dict[str, SolutionResult],
    title: str = "Nutrient Fulfillment",
    height: int = 500,
) -> go.Figure:
    """Plot a radar chart showing nutrient fulfillment vs requirements.

    Args:
        scenario: Scenario definition
        solutions: Dict mapping label -> SolutionResult
        title: Chart title
        height: Chart height in pixels
    """
    fig = go.Figure()

    nutrients = scenario.nutrient_list
    # Short labels for display
    short_labels = [n.split("(")[0].strip() for n in nutrients]

    for label, sol in solutions.items():
        if not sol.is_optimal:
            continue

        # Compute fulfillment as fraction of requirement
        fulfillment = []
        for nutrient in nutrients:
            req = scenario.get_requirement(nutrient)
            actual = sol.nutrients_pp.get(nutrient, 0)
            pct = (actual / req * 100) if req > 0 else 0
            fulfillment.append(min(pct, 200))  # cap at 200% for display

        # Close the radar
        fulfillment_closed = fulfillment + [fulfillment[0]]
        labels_closed = short_labels + [short_labels[0]]

        fig.add_trace(
            go.Scatterpolar(
                r=fulfillment_closed,
                theta=labels_closed,
                fill="toself",
                name=label,
                opacity=0.6,
            )
        )

    # Add 100% reference line
    ref_values = [100] * (len(short_labels) + 1)
    ref_labels = short_labels + [short_labels[0]]
    fig.add_trace(
        go.Scatterpolar(
            r=ref_values,
            theta=ref_labels,
            mode="lines",
            line=dict(color="rgba(0,0,0,0.3)", dash="dash", width=2),
            name="100% Requirement",
            fill=None,
        )
    )

    fig.update_layout(
        title=title,
        height=height,
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 150], ticksuffix="%"),
        ),
        showlegend=True,
    )

    return fig
