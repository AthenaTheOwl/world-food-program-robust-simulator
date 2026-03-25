"""Cost breakdown visualizations: pie charts, stacked bars, treemaps."""

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from core.scenario import Scenario
from models.solver_utils import SolutionResult
from ui.theme import format_currency, NODE_COLORS, CATEGORY_COLORS


def plot_cost_split(solution: SolutionResult, title: str = "Cost Breakdown") -> go.Figure:
    """Pie chart: procurement vs transportation cost split."""
    fig = go.Figure(
        data=[
            go.Pie(
                labels=["Procurement", "Transportation"],
                values=[solution.procurement_cost, solution.transportation_cost],
                hole=0.4,
                marker=dict(colors=["#1976D2", "#FF9800"]),
                textinfo="label+percent",
                hovertemplate="%{label}<br>%{value:$,.0f}<br>%{percent}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title=title,
        height=350,
        annotations=[
            dict(
                text=format_currency(solution.total_cost),
                x=0.5,
                y=0.5,
                font_size=16,
                showarrow=False,
            )
        ],
    )
    return fig


def plot_procurement_by_node(
    scenario: Scenario, solution: SolutionResult, title: str = "Procurement by Source"
) -> go.Figure:
    """Stacked bar chart: procurement cost by node, colored by commodity category."""
    if not solution.procurement:
        return go.Figure().update_layout(title=title)

    rows = []
    for (node, commodity), tons in solution.procurement.items():
        price = scenario.price_lookup.get((node, commodity), 0)
        cost = tons * price
        # Get category
        cat_row = scenario.commodities[scenario.commodities["commodity_id"] == commodity]
        category = cat_row.iloc[0]["category"] if not cat_row.empty else "other"
        node_type = scenario.get_node_type(node)
        rows.append(
            {
                "Node": node,
                "Commodity": commodity,
                "Category": category,
                "Cost ($)": cost,
                "Tons": tons,
                "Node Type": node_type,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return go.Figure().update_layout(title=title)

    fig = px.bar(
        df,
        x="Node",
        y="Cost ($)",
        color="Category",
        color_discrete_map=CATEGORY_COLORS,
        title=title,
        hover_data=["Commodity", "Tons"],
    )
    fig.update_layout(height=400, xaxis_tickangle=-45)
    return fig


def plot_ration_composition(
    scenario: Scenario, solution: SolutionResult, title: str = "Daily Ration (kg/person)"
) -> go.Figure:
    """Horizontal bar chart of ration composition."""
    if not solution.ration_pp:
        return go.Figure().update_layout(title=title)

    items = sorted(solution.ration_pp.items(), key=lambda x: -x[1])
    commodities = [c for c, v in items]
    values = [v for c, v in items]

    # Get categories for coloring
    colors = []
    for c in commodities:
        cat_row = scenario.commodities[scenario.commodities["commodity_id"] == c]
        cat = cat_row.iloc[0]["category"] if not cat_row.empty else "other"
        colors.append(CATEGORY_COLORS.get(cat, "#B0BEC5"))

    fig = go.Figure(
        data=[
            go.Bar(
                y=commodities,
                x=values,
                orientation="h",
                marker_color=colors,
                text=[f"{v:.3f}" for v in values],
                textposition="auto",
                hovertemplate="%{y}: %{x:.4f} kg/person<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title=title,
        height=max(300, len(commodities) * 25 + 100),
        xaxis_title="kg per person per day",
        yaxis=dict(autorange="reversed"),
    )
    return fig
