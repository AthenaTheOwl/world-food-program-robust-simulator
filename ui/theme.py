"""Shared Plotly theme, color palettes, and styling utilities."""

import plotly.graph_objects as go
import plotly.io as pio

# Color palette
COLORS = {
    "primary": "#1976D2",
    "secondary": "#FF9800",
    "success": "#4CAF50",
    "danger": "#F44336",
    "warning": "#FFC107",
    "info": "#00BCD4",
    "dark": "#37474F",
    "light": "#ECEFF1",
    "white": "#FFFFFF",
}

# Node type colors (consistent with config.py)
NODE_COLORS = {
    "supplier_international": "#2196F3",
    "supplier_regional": "#FF9800",
    "supplier_local": "#4CAF50",
    "transshipment": "#9C27B0",
    "demand": "#F44336",
    "hybrid_supply_demand": "#009688",
}

# Commodity category colors
CATEGORY_COLORS = {
    "grain": "#FDD835",
    "legume": "#8D6E63",
    "protein": "#E53935",
    "dairy": "#BBDEFB",
    "fortified": "#AB47BC",
    "fat": "#FFB74D",
    "sweetener": "#F48FB1",
    "condiment": "#90A4AE",
    "other": "#B0BEC5",
}

# Plotly layout template
LAYOUT_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        font=dict(family="Inter, -apple-system, sans-serif", size=13, color="#37474F"),
        paper_bgcolor="white",
        plot_bgcolor="#FAFAFA",
        title=dict(font=dict(size=18, color="#1976D2"), x=0.0, xanchor="left"),
        xaxis=dict(
            gridcolor="#E0E0E0",
            linecolor="#BDBDBD",
            zerolinecolor="#BDBDBD",
        ),
        yaxis=dict(
            gridcolor="#E0E0E0",
            linecolor="#BDBDBD",
            zerolinecolor="#BDBDBD",
        ),
        colorway=[
            "#1976D2", "#FF9800", "#4CAF50", "#F44336", "#9C27B0",
            "#009688", "#FFC107", "#795548", "#607D8B", "#E91E63",
        ],
        margin=dict(l=60, r=30, t=60, b=50),
    )
)

pio.templates["food_relief"] = LAYOUT_TEMPLATE
pio.templates.default = "food_relief"


def format_currency(value: float, currency: str = "USD") -> str:
    """Format a value as currency."""
    if currency == "USD":
        return f"${value:,.0f}"
    return f"{value:,.0f} {currency}"


def format_tons(value: float) -> str:
    """Format a value in metric tons."""
    if value < 1:
        return f"{value * 1000:.0f} kg"
    return f"{value:,.1f} MT"


def format_percent(value: float) -> str:
    """Format a value as a percentage."""
    return f"{value:.1%}"
