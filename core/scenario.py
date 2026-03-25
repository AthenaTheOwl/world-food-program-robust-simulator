"""Scenario dataclass: loads, validates, and provides structured access to scenario data."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .validators import validate_scenario


@dataclass
class Scenario:
    """A complete food relief scenario definition."""

    name: str
    description: str
    currency: str
    weight_unit: str
    time_unit: str
    num_periods: int
    budget: Optional[float]

    # Core data tables
    nodes: pd.DataFrame
    edges: pd.DataFrame
    commodities: pd.DataFrame
    nutrition: pd.DataFrame  # long-form: (commodity_id, nutrient_name, per_100g)
    procurement_costs: pd.DataFrame
    nutrition_requirements: pd.DataFrame
    diet_constraints: pd.DataFrame  # may be empty

    # Derived sets (computed on load)
    node_sets: dict = field(default_factory=dict)
    demand_nodes: list = field(default_factory=list)
    supply_nodes: list = field(default_factory=list)
    commodity_list: list = field(default_factory=list)
    nutrient_list: list = field(default_factory=list)
    edge_index: list = field(default_factory=list)
    procurement_index: list = field(default_factory=list)
    demand_dict: dict = field(default_factory=dict)
    total_demand: float = 0.0

    # Nutrition lookup: {commodity: {nutrient: value_per_100g}}
    nutrition_matrix: dict = field(default_factory=dict)

    # Procurement cost lookup: {(node, commodity): price}
    price_lookup: dict = field(default_factory=dict)

    # Uncertainty parameters: {(node, commodity): {std_fraction, correlation_group, cross_correlation}}
    uncertainty_params: dict = field(default_factory=dict)

    def __post_init__(self):
        self._compute_derived()

    def _compute_derived(self):
        """Compute all derived sets and lookups from the raw data."""
        # Node sets by type
        self.node_sets = {}
        for _, row in self.nodes.iterrows():
            ntype = row["node_type"]
            if ntype not in self.node_sets:
                self.node_sets[ntype] = []
            self.node_sets[ntype].append(row["node_id"])

        # Demand nodes: any node with non-null demand_persons
        demand_rows = self.nodes[self.nodes["demand_persons"].notna()]
        self.demand_nodes = list(demand_rows["node_id"])
        self.demand_dict = dict(
            zip(demand_rows["node_id"], demand_rows["demand_persons"])
        )
        self.total_demand = sum(self.demand_dict.values())

        # Supply nodes: all node types that can procure
        supply_types = {
            "supplier_international",
            "supplier_regional",
            "supplier_local",
            "hybrid_supply_demand",
        }
        self.supply_nodes = [
            row["node_id"]
            for _, row in self.nodes.iterrows()
            if row["node_type"] in supply_types
        ]

        # Commodity and nutrient lists
        self.commodity_list = sorted(self.commodities["commodity_id"].unique().tolist())
        self.nutrient_list = sorted(self.nutrition["nutrient_name"].unique().tolist())

        # Edge index
        self.edge_index = [
            (row["source"], row["target"]) for _, row in self.edges.iterrows()
        ]

        # Procurement index: (node, commodity) pairs where procurement is possible
        self.procurement_index = [
            (row["node_id"], row["commodity_id"])
            for _, row in self.procurement_costs.iterrows()
        ]

        # Nutrition matrix: {commodity: {nutrient: value}}
        self.nutrition_matrix = {}
        for _, row in self.nutrition.iterrows():
            cid = row["commodity_id"]
            if cid not in self.nutrition_matrix:
                self.nutrition_matrix[cid] = {}
            self.nutrition_matrix[cid][row["nutrient_name"]] = row["per_100g"]

        # Price lookup
        self.price_lookup = {
            (row["node_id"], row["commodity_id"]): row["price_per_ton"]
            for _, row in self.procurement_costs.iterrows()
        }

        # Uncertainty parameters
        self.uncertainty_params = {}
        for _, row in self.procurement_costs.iterrows():
            key = (row["node_id"], row["commodity_id"])
            self.uncertainty_params[key] = {
                "price_std_fraction": row.get("price_std_fraction", np.nan),
                "correlation_group": row.get("correlation_group", np.nan),
                "cross_correlation": row.get("cross_correlation", np.nan),
            }

    def get_node_type(self, node_id: str) -> str:
        """Get the type of a node."""
        row = self.nodes[self.nodes["node_id"] == node_id]
        if row.empty:
            raise ValueError(f"Node '{node_id}' not found")
        return row.iloc[0]["node_type"]

    def is_international(self, node_id: str) -> bool:
        return self.get_node_type(node_id) == "supplier_international"

    def get_commodities_at_node(self, node_id: str) -> list:
        """Get all commodities available for procurement at a node."""
        mask = self.procurement_costs["node_id"] == node_id
        return self.procurement_costs[mask]["commodity_id"].tolist()

    def get_transport_cost(self, source: str, target: str) -> float:
        """Get transport cost for an edge."""
        mask = (self.edges["source"] == source) & (self.edges["target"] == target)
        row = self.edges[mask]
        if row.empty:
            raise ValueError(f"Edge ({source}, {target}) not found")
        return row.iloc[0]["transport_cost_per_ton"]

    def get_requirement(self, nutrient: str) -> float:
        """Get the daily per-person requirement for a nutrient."""
        mask = self.nutrition_requirements["nutrient_name"] == nutrient
        row = self.nutrition_requirements[mask]
        if row.empty:
            raise ValueError(f"Nutrient requirement '{nutrient}' not found")
        return row.iloc[0]["min_per_person_day"]

    @classmethod
    def load(cls, scenario_dir: str) -> "Scenario":
        """Load a scenario from a directory containing scenario.json and CSV files."""
        scenario_dir = Path(scenario_dir)

        # Load metadata
        with open(scenario_dir / "scenario.json", "r", encoding="utf-8") as f:
            meta = json.load(f)

        # Load CSV files
        def read_csv(name, required=True):
            path = scenario_dir / name
            if not path.exists():
                if required:
                    raise FileNotFoundError(f"Required file '{name}' not found in {scenario_dir}")
                return pd.DataFrame()
            return pd.read_csv(path, encoding="utf-8-sig")

        nodes = read_csv("nodes.csv")
        edges = read_csv("edges.csv")
        commodities = read_csv("commodities.csv")
        nutrition = read_csv("nutrition.csv")
        procurement_costs = read_csv("procurement_costs.csv")
        nutrition_requirements = read_csv("nutrition_requirements.csv")
        diet_constraints = read_csv("diet_constraints.csv", required=False)

        # Fill optional columns with defaults
        if "capacity_tons" not in edges.columns:
            edges["capacity_tons"] = np.inf
        if "lead_time_days" not in edges.columns:
            edges["lead_time_days"] = 0
        if "reliability" not in edges.columns:
            edges["reliability"] = 1.0

        if "shelf_life_days" not in commodities.columns:
            commodities["shelf_life_days"] = np.inf
        if "category" not in commodities.columns:
            commodities["category"] = "other"

        for col in ["price_std_fraction", "correlation_group", "cross_correlation"]:
            if col not in procurement_costs.columns:
                procurement_costs[col] = np.nan

        scenario = cls(
            name=meta.get("name", "Unnamed Scenario"),
            description=meta.get("description", ""),
            currency=meta.get("currency", "USD"),
            weight_unit=meta.get("weight_unit", "metric_ton"),
            time_unit=meta.get("time_unit", "day"),
            num_periods=meta.get("num_periods", 1),
            budget=meta.get("budget"),
            nodes=nodes,
            edges=edges,
            commodities=commodities,
            nutrition=nutrition,
            procurement_costs=procurement_costs,
            nutrition_requirements=nutrition_requirements,
            diet_constraints=diet_constraints,
        )

        # Validate
        errors = validate_scenario(scenario)
        if errors:
            raise ValueError(
                "Scenario validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        return scenario

    def export(self, output_dir: str):
        """Export scenario to a directory."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "name": self.name,
            "description": self.description,
            "currency": self.currency,
            "weight_unit": self.weight_unit,
            "time_unit": self.time_unit,
            "num_periods": self.num_periods,
            "budget": self.budget,
        }
        with open(output_dir / "scenario.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        self.nodes.to_csv(output_dir / "nodes.csv", index=False)
        self.edges.to_csv(output_dir / "edges.csv", index=False)
        self.commodities.to_csv(output_dir / "commodities.csv", index=False)
        self.nutrition.to_csv(output_dir / "nutrition.csv", index=False)
        self.procurement_costs.to_csv(output_dir / "procurement_costs.csv", index=False)
        self.nutrition_requirements.to_csv(
            output_dir / "nutrition_requirements.csv", index=False
        )
        if not self.diet_constraints.empty:
            self.diet_constraints.to_csv(
                output_dir / "diet_constraints.csv", index=False
            )
