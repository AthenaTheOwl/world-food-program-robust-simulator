"""Schema validation and referential integrity checks for scenarios."""

from config import VALID_NODE_TYPES


def validate_scenario(scenario) -> list[str]:
    """Validate a Scenario object. Returns a list of error messages (empty if valid)."""
    errors = []

    # --- Nodes ---
    if scenario.nodes.empty:
        errors.append("nodes.csv is empty")
        return errors

    required_node_cols = {"node_id", "node_type"}
    missing = required_node_cols - set(scenario.nodes.columns)
    if missing:
        errors.append(f"nodes.csv missing columns: {missing}")
        return errors

    # Check node types
    invalid_types = set(scenario.nodes["node_type"]) - VALID_NODE_TYPES
    if invalid_types:
        errors.append(f"Invalid node types: {invalid_types}. Valid: {VALID_NODE_TYPES}")

    # Check unique node IDs
    dupes = scenario.nodes[scenario.nodes["node_id"].duplicated()]["node_id"].tolist()
    if dupes:
        errors.append(f"Duplicate node IDs: {dupes}")

    all_node_ids = set(scenario.nodes["node_id"])

    # --- Edges ---
    if scenario.edges.empty:
        errors.append("edges.csv is empty")
    else:
        required_edge_cols = {"source", "target", "transport_cost_per_ton"}
        missing = required_edge_cols - set(scenario.edges.columns)
        if missing:
            errors.append(f"edges.csv missing columns: {missing}")
        else:
            bad_sources = set(scenario.edges["source"]) - all_node_ids
            if bad_sources:
                errors.append(f"Edge sources reference unknown nodes: {bad_sources}")
            bad_targets = set(scenario.edges["target"]) - all_node_ids
            if bad_targets:
                errors.append(f"Edge targets reference unknown nodes: {bad_targets}")

    # --- Commodities ---
    if scenario.commodities.empty:
        errors.append("commodities.csv is empty")
    elif "commodity_id" not in scenario.commodities.columns:
        errors.append("commodities.csv missing 'commodity_id' column")

    all_commodity_ids = set(scenario.commodities["commodity_id"]) if not scenario.commodities.empty else set()

    # --- Nutrition ---
    if scenario.nutrition.empty:
        errors.append("nutrition.csv is empty")
    else:
        required_nutr_cols = {"commodity_id", "nutrient_name", "per_100g"}
        missing = required_nutr_cols - set(scenario.nutrition.columns)
        if missing:
            errors.append(f"nutrition.csv missing columns: {missing}")
        else:
            bad_comms = set(scenario.nutrition["commodity_id"]) - all_commodity_ids
            if bad_comms:
                errors.append(f"nutrition.csv references unknown commodities: {bad_comms}")

    # --- Procurement costs ---
    if scenario.procurement_costs.empty:
        errors.append("procurement_costs.csv is empty")
    else:
        required_pc_cols = {"node_id", "commodity_id", "price_per_ton"}
        missing = required_pc_cols - set(scenario.procurement_costs.columns)
        if missing:
            errors.append(f"procurement_costs.csv missing columns: {missing}")
        else:
            bad_nodes = set(scenario.procurement_costs["node_id"]) - all_node_ids
            if bad_nodes:
                errors.append(f"procurement_costs.csv references unknown nodes: {bad_nodes}")
            bad_comms = set(scenario.procurement_costs["commodity_id"]) - all_commodity_ids
            if bad_comms:
                errors.append(f"procurement_costs.csv references unknown commodities: {bad_comms}")

    # --- Nutrition requirements ---
    if scenario.nutrition_requirements.empty:
        errors.append("nutrition_requirements.csv is empty")
    else:
        required_req_cols = {"nutrient_name", "min_per_person_day"}
        missing = required_req_cols - set(scenario.nutrition_requirements.columns)
        if missing:
            errors.append(f"nutrition_requirements.csv missing columns: {missing}")

    # --- Check that at least one demand node exists ---
    if not scenario.demand_nodes:
        errors.append("No demand nodes found (no nodes with demand_persons > 0)")

    # --- Check that at least one supply node has procurement ---
    if scenario.procurement_index and not errors:
        supply_in_proc = set(n for n, c in scenario.procurement_index)
        if not supply_in_proc:
            errors.append("No procurement links defined")

    return errors
