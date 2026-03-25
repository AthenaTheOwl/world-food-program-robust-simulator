"""Sankey flow diagram for supply chain visualization."""

import plotly.graph_objects as go

from core.scenario import Scenario
from models.solver_utils import SolutionResult
from ui.theme import NODE_COLORS
from config import ACTIVE_THRESHOLD


def plot_sankey(
    scenario: Scenario,
    solution: SolutionResult,
    title: str = "Supply Chain Flow",
    height: int = 500,
) -> go.Figure:
    """Sankey diagram showing commodity flows from suppliers to demand points."""
    if not solution.transportation:
        return go.Figure().update_layout(title=title, height=height)

    # Build node list (only include nodes with non-zero flow)
    active_nodes = set()
    for (src, tgt), val in solution.transportation.items():
        if val > ACTIVE_THRESHOLD:
            active_nodes.add(src)
            active_nodes.add(tgt)

    # Also include nodes with procurement or delivery
    for (n, c) in solution.procurement:
        active_nodes.add(n)
    for (d, c) in solution.delivery:
        active_nodes.add(d)

    node_list = sorted(active_nodes)
    node_idx = {n: i for i, n in enumerate(node_list)}

    # Node colors
    node_colors = []
    for n in node_list:
        ntype = scenario.get_node_type(n)
        node_colors.append(NODE_COLORS.get(ntype, "#999999"))

    # Build links
    sources, targets, values, link_labels = [], [], [], []
    for (src, tgt), val in solution.transportation.items():
        if val > ACTIVE_THRESHOLD and src in node_idx and tgt in node_idx:
            sources.append(node_idx[src])
            targets.append(node_idx[tgt])
            values.append(val)
            link_labels.append(f"{src} → {tgt}: {val:.1f} MT")

    fig = go.Figure(
        data=[
            go.Sankey(
                node=dict(
                    pad=15,
                    thickness=20,
                    line=dict(color="black", width=0.5),
                    label=node_list,
                    color=node_colors,
                ),
                link=dict(
                    source=sources,
                    target=targets,
                    value=values,
                    label=link_labels,
                    color="rgba(25, 118, 210, 0.3)",
                ),
            )
        ]
    )

    fig.update_layout(title=title, height=height)
    return fig
