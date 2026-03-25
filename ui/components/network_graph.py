"""Interactive network graph visualization using Plotly."""

import plotly.graph_objects as go
import numpy as np

from core.scenario import Scenario
from models.solver_utils import SolutionResult
from ui.theme import NODE_COLORS, format_currency, format_tons


def plot_network(
    scenario: Scenario,
    solution: SolutionResult = None,
    title: str = "Supply Chain Network",
    height: int = 600,
) -> go.Figure:
    """Plot the supply chain network with optional flow overlay.

    If a solution is provided, edge widths reflect flow volumes and
    node sizes reflect procurement/delivery volumes.
    """
    fig = go.Figure()

    # Build node position lookup
    node_positions = {}
    for _, row in scenario.nodes.iterrows():
        nid = row["node_id"]
        lat = row.get("latitude", 0)
        lon = row.get("longitude", 0)
        if np.isnan(lat) or np.isnan(lon):
            lat, lon = 0, 0
        node_positions[nid] = (lon, lat)  # plotly uses (x=lon, y=lat)

    # Determine if we have valid geographic coordinates
    has_geo = any(
        abs(pos[1]) > 0.01 for pos in node_positions.values()
    )

    # --- Draw edges ---
    max_flow = 1.0
    if solution and solution.transportation:
        max_flow = max(solution.transportation.values())

    for _, edge_row in scenario.edges.iterrows():
        src, tgt = edge_row["source"], edge_row["target"]
        x0, y0 = node_positions.get(src, (0, 0))
        x1, y1 = node_positions.get(tgt, (0, 0))

        flow_val = 0
        if solution and solution.transportation:
            flow_val = solution.transportation.get((src, tgt), 0)

        # Edge styling based on flow
        if solution:
            if flow_val > 0:
                width = max(1, 6 * flow_val / max_flow)
                color = f"rgba(25, 118, 210, {min(0.3 + 0.7 * flow_val / max_flow, 1.0)})"
            else:
                width = 0.5
                color = "rgba(200, 200, 200, 0.3)"
        else:
            width = 1
            color = "rgba(150, 150, 150, 0.5)"

        hover = f"{src} → {tgt}<br>Cost: {format_currency(edge_row['transport_cost_per_ton'])}/MT"
        if flow_val > 0:
            hover += f"<br>Flow: {format_tons(flow_val)}"

        fig.add_trace(
            go.Scatter(
                x=[x0, x1, None],
                y=[y0, y1, None],
                mode="lines",
                line=dict(width=width, color=color),
                hoverinfo="text",
                hovertext=hover,
                showlegend=False,
            )
        )

    # --- Draw nodes ---
    for node_type in scenario.node_sets:
        nodes_of_type = scenario.node_sets[node_type]
        xs, ys, texts, sizes, hover_texts = [], [], [], [], []

        for nid in nodes_of_type:
            x, y = node_positions.get(nid, (0, 0))
            xs.append(x)
            ys.append(y)
            texts.append(nid)

            # Size based on demand or procurement volume
            base_size = 12
            hover_parts = [f"<b>{nid}</b>", f"Type: {node_type}"]

            if nid in scenario.demand_dict:
                demand = scenario.demand_dict[nid]
                base_size = max(10, 8 + np.sqrt(demand) / 10)
                hover_parts.append(f"Demand: {demand:,.0f} people")

            if solution:
                # Procurement at this node
                proc_vol = sum(
                    v for (n, c), v in solution.procurement.items() if n == nid
                )
                if proc_vol > 0:
                    base_size = max(base_size, 10 + np.sqrt(proc_vol) * 3)
                    hover_parts.append(f"Procurement: {format_tons(proc_vol)}")

                # Delivery at this node
                del_vol = sum(
                    v for (d, c), v in solution.delivery.items() if d == nid
                )
                if del_vol > 0:
                    hover_parts.append(f"Delivery: {format_tons(del_vol)}")

            sizes.append(base_size)
            hover_texts.append("<br>".join(hover_parts))

        color = NODE_COLORS.get(node_type, "#999999")
        label = node_type.replace("_", " ").title()

        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers+text",
                marker=dict(
                    size=sizes,
                    color=color,
                    line=dict(width=1.5, color="white"),
                    opacity=0.9,
                ),
                text=texts,
                textposition="top center",
                textfont=dict(size=10),
                hoverinfo="text",
                hovertext=hover_texts,
                name=label,
            )
        )

    fig.update_layout(
        title=title,
        height=height,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
        xaxis=dict(title="Longitude" if has_geo else "", showgrid=False),
        yaxis=dict(title="Latitude" if has_geo else "", showgrid=False, scaleanchor="x"),
    )

    return fig
