"""Application-wide configuration and solver settings."""

import cvxpy as cp

# Solver settings
DEFAULT_SOLVER = cp.CLARABEL
FALLBACK_SOLVER = cp.SCS
SOLVER_TOLERANCE = 1e-6
ACTIVE_THRESHOLD = 1e-3  # threshold for considering a variable "active" (non-zero)

# App settings
APP_TITLE = "Food Relief Optimization Simulator"
APP_ICON = "🌾"
DEFAULT_BUDGET = 6000.0
DEFAULT_ROBUSTNESS = 0.95
MONTE_CARLO_DEFAULT_SAMPLES = 1000

# Node type colors for visualization
NODE_COLORS = {
    "supplier_international": "#2196F3",  # blue
    "supplier_regional": "#FF9800",       # orange
    "supplier_local": "#4CAF50",          # green
    "transshipment": "#9C27B0",           # purple
    "demand": "#F44336",                  # red
    "hybrid_supply_demand": "#009688",    # teal
}

NODE_TYPE_LABELS = {
    "supplier_international": "International Supplier",
    "supplier_regional": "Regional Supplier",
    "supplier_local": "Local Supplier",
    "transshipment": "Transshipment",
    "demand": "Demand Point",
    "hybrid_supply_demand": "Supply & Demand",
}

VALID_NODE_TYPES = set(NODE_COLORS.keys())
