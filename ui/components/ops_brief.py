"""Operations Brief: one-page markdown summary of a plan for non-technical stakeholders."""

from core.scenario import Scenario
from models.solver_utils import SolutionResult
from ui.theme import format_currency


def generate_ops_brief(
    scenario: Scenario,
    sol: SolutionResult,
    label: str = "Plan",
    sol_baseline: SolutionResult = None,
) -> str:
    """Generate a one-page operations brief as markdown text.

    Args:
        scenario: The scenario definition.
        sol: The solution to summarize.
        label: Human-readable plan name.
        sol_baseline: Optional baseline (e.g., nominal) for delta comparisons.

    Returns:
        Markdown string suitable for display or download.
    """
    lines = []
    lines.append(f"# Operations Brief: {label}")
    lines.append(f"**Scenario:** {scenario.name}")
    lines.append(f"**Population:** {scenario.total_demand:,.0f} persons/day")
    lines.append("")

    # ── Cost summary ──
    lines.append("## Cost Summary")
    lines.append(f"- **Total daily cost:** {format_currency(sol.total_cost)}")
    lines.append(f"- **Per person:** {format_currency(sol.cost_per_person)}/day")
    lines.append(f"- **Procurement:** {format_currency(sol.procurement_cost)} ({sol.procurement_ratio:.0%})")
    lines.append(f"- **Transportation:** {format_currency(sol.transportation_cost)} ({sol.transportation_ratio:.0%})")

    if sol_baseline:
        delta = sol.total_cost - sol_baseline.total_cost
        pct = delta / sol_baseline.total_cost * 100 if sol_baseline.total_cost else 0
        lines.append(f"- **vs baseline:** {format_currency(delta):+} ({pct:+.1f}%)")
    lines.append("")

    # ── Nutrition ──
    lines.append("## Nutrition Coverage")
    lines.append(f"**Overall:** {sol.nutrient_slack:.0%} of daily requirements met")
    lines.append("")
    lines.append("| Nutrient | Required | Delivered | Met |")
    lines.append("|----------|----------|-----------|-----|")
    for nutrient in scenario.nutrient_list:
        req = scenario.get_requirement(nutrient)
        actual = sol.nutrients_pp.get(nutrient, 0)
        pct = (actual / req * 100) if req > 0 else 0
        short = nutrient.split("(")[0].strip()
        lines.append(f"| {short} | {req:.1f} | {actual:.1f} | {pct:.0f}% |")
    lines.append("")

    # ── Sourcing ──
    lines.append("## Sourcing Strategy")
    lines.append(f"- **International suppliers:** {sol.international_procurement_ratio:.0%} of procurement cost")
    lines.append(f"- **Regional/local suppliers:** {1 - sol.international_procurement_ratio:.0%} of procurement cost")
    lines.append(f"- **Active procurement links:** {sol.num_active_procurement}")
    lines.append(f"- **Active transport routes:** {sol.num_active_transport}")

    if sol_baseline:
        intl_shift = sol.international_procurement_ratio - sol_baseline.international_procurement_ratio
        if abs(intl_shift) > 0.01:
            direction = "toward" if intl_shift > 0 else "away from"
            lines.append(f"- **Shift:** {abs(intl_shift):.0%} {direction} international suppliers vs baseline")
    lines.append("")

    # ── Risk ──
    lines.append("## Risk Profile")
    if sol.robustness_level > 0.5:
        lines.append(f"- **Robustness level:** {sol.robustness_level:.0%}")
        lines.append(f"  Plan is designed to stay within budget under {sol.robustness_level:.0%} of price scenarios.")
    else:
        lines.append("- **Robustness:** Nominal (no protection against price uncertainty)")
        lines.append("  Plan assumes all prices are exactly as expected.")
    lines.append("")

    # ── Top ration items ──
    lines.append("## Daily Ration (per person)")
    if sol.ration_pp:
        sorted_ration = sorted(sol.ration_pp.items(), key=lambda x: -x[1])
        total_kg = sum(v for _, v in sorted_ration)
        lines.append(f"**Total:** {total_kg:.3f} kg/person/day")
        lines.append("")
        lines.append("| Commodity | kg/person/day | Share |")
        lines.append("|-----------|---------------|-------|")
        for c, v in sorted_ration[:10]:
            share = v / total_kg * 100 if total_kg > 0 else 0
            lines.append(f"| {c} | {v:.4f} | {share:.1f}% |")
        if len(sorted_ration) > 10:
            lines.append(f"| *(+ {len(sorted_ration) - 10} more)* | | |")
    lines.append("")

    # ── Recommendation ──
    lines.append("## Recommended Action")
    if sol.nutrient_slack >= 1.0 and sol.robustness_level >= 0.90:
        lines.append("This plan meets all nutritional requirements with robust protection against price uncertainty. **Recommended for deployment.**")
    elif sol.nutrient_slack >= 1.0:
        lines.append("This plan meets all nutritional requirements but has limited protection against price spikes. **Consider robust optimization** to reduce budget overrun risk.")
    elif sol.nutrient_slack >= 0.8:
        lines.append(f"This plan covers {sol.nutrient_slack:.0%} of nutritional needs. **Seek additional funding** or prioritize critical nutrients.")
    else:
        lines.append(f"This plan covers only {sol.nutrient_slack:.0%} of nutritional needs. **Emergency funding required.** Current budget is critically insufficient.")
    lines.append("")

    lines.append("---")
    lines.append(f"*Generated by Food Relief Optimizer · {scenario.name}*")

    return "\n".join(lines)
