"""Centralized tooltip registry for OR concept explanations."""

TOOLTIPS = {
    # --- Optimization Models ---
    "nominal_lp": {
        "title": "Nominal Linear Program",
        "body": (
            "Minimizes total cost assuming all prices are exactly at their expected values. "
            "No protection against price uncertainty. The solution is optimal for the average "
            "case but may exceed budget if prices increase."
        ),
    },
    "budget_constrained": {
        "title": "Budget-Constrained Optimization",
        "body": (
            "With a fixed budget, we can't always feed everyone fully. Instead, we maximize "
            "the 'nutrient slack' — the fraction of daily nutritional requirements we can meet. "
            "A slack of 0.8 means we meet 80% of each nutrient requirement."
        ),
    },
    "robust_socp": {
        "title": "Robust Optimization (SOCP)",
        "body": (
            "Protects against price uncertainty by hedging the procurement plan. Uses an "
            "ellipsoidal uncertainty set around nominal prices. The robust counterpart is a "
            "Second-Order Cone Program (SOCP) — a type of convex optimization that can be "
            "solved efficiently. Higher robustness costs more but provides stronger guarantees."
        ),
    },
    "disruption": {
        "title": "Disruption Scenario Analysis",
        "body": (
            "Tests how the supply chain performs when things go wrong: route closures, "
            "supplier failures, or demand surges. The model re-optimizes under the disrupted "
            "conditions to find the best response."
        ),
    },
    "multi_period": {
        "title": "Multi-Period Planning",
        "body": (
            "Extends optimization over multiple time periods. Accounts for inventory "
            "carry-over between periods, food spoilage, and changing demand over time. "
            "Enables strategic planning rather than day-by-day reactions."
        ),
    },
    "adaptive_robust": {
        "title": "Adaptive Robust Optimization",
        "body": (
            "A simplified two-stage procurement hedge: some decisions (contracts) are made "
            "before uncertainty is revealed, while later purchases can respond afterward. "
            "This page is an approximation, not a full scenario-recourse model with "
            "scenario-specific routing and delivery decisions."
        ),
    },
    # --- Parameters ---
    "robustness_level": {
        "title": "Robustness Level (p)",
        "body": (
            "The probability that the solution remains feasible under price uncertainty. "
            "p = 50% gives the nominal solution (no protection). p = 95% means the solution "
            "stays within budget for 95% of possible price realizations. Higher p = more "
            "protection but higher cost."
        ),
    },
    "nutrient_slack": {
        "title": "Nutrient Slack",
        "body": (
            "A multiplier on nutritional requirements. At 1.0, all daily requirements are "
            "fully met. At 0.8, each person receives 80% of every required nutrient. "
            "This measures how well we're feeding people given our constraints."
        ),
    },
    "budget": {
        "title": "Daily Budget",
        "body": (
            "Total available funds for one day of operations, covering both food procurement "
            "and transportation costs. When budget is limited, we may not be able to fully "
            "meet nutritional needs for everyone."
        ),
    },
    # --- Metrics ---
    "cost_per_person": {
        "title": "Cost per Person Fed",
        "body": (
            "Total cost divided by the effective number of people fed (total demand × "
            "nutrient slack). A key efficiency metric for humanitarian operations."
        ),
    },
    "procurement_ratio": {
        "title": "Procurement/Total Cost Ratio",
        "body": (
            "What fraction of total cost goes to buying food vs. transporting it. "
            "Higher procurement ratio means food costs dominate; lower means logistics "
            "is the bottleneck."
        ),
    },
    "international_ratio": {
        "title": "International Procurement Ratio",
        "body": (
            "Fraction of procurement cost spent at international suppliers (vs. regional/local). "
            "This is useful for seeing whether the solution is leaning on stable but distant "
            "international suppliers or more volatile but better-positioned regional/local markets."
        ),
    },
    # --- Simulation ---
    "monte_carlo": {
        "title": "Monte Carlo Simulation",
        "body": (
            "Generates thousands of random price scenarios and tests each solution against "
            "them. This empirically validates the theoretical robustness guarantees. If a "
            "robust solution at p=95% truly works, it should be feasible in ~95% of simulated "
            "scenarios."
        ),
    },
    "feasibility_rate": {
        "title": "Empirical Feasibility Rate",
        "body": (
            "The fraction of simulated price scenarios where the solution stays within "
            "budget. Should approximately match the theoretical robustness level."
        ),
    },
    # --- Network ---
    "node_type": {
        "title": "Node Types",
        "body": (
            "International suppliers: outside the crisis zone, stable prices. "
            "Regional suppliers: within the broader region, moderate price volatility. "
            "Local markets: at or near demand points, high price volatility but lower transport costs. "
            "Demand points: where displaced people need food delivery."
        ),
    },
    "flow_conservation": {
        "title": "Flow Conservation",
        "body": (
            "Food must balance physically at every node. In general: procurement + inflow = "
            "outflow + local delivery. This lets the model represent pure suppliers, pure demand "
            "points, and hybrid local markets that both buy food and serve nearby populations."
        ),
    },
    # --- Diet ---
    "diet_constraints": {
        "title": "Diet Balance Constraints",
        "body": (
            "Ensures rations have balanced macronutrient ratios: at least 4:1 carbohydrate "
            "to protein and 4:1 carbohydrate to fat by mass. This prevents cheap but "
            "nutritionally unbalanced rations (e.g., all sugar and oil)."
        ),
    },
}


def get_tooltip(key: str) -> str:
    """Get formatted tooltip text for a given key."""
    tip = TOOLTIPS.get(key, {})
    title = tip.get("title", key)
    body = tip.get("body", "")
    return f"**{title}**: {body}"


def get_tooltip_title(key: str) -> str:
    return TOOLTIPS.get(key, {}).get("title", key)


def get_tooltip_body(key: str) -> str:
    return TOOLTIPS.get(key, {}).get("body", "")
