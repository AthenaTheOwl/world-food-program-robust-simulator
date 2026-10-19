# Separate the contract discount from the value of adaptation

Method update: October 18, 2026. Proposed experiments below are not reported as executed results.

The README already identifies that the adaptive comparison combines a contract discount with scenario-specific recourse. To explain a lower adaptive cost, isolate both mechanisms instead of attributing the full difference to adaptation.

The next proposed synthetic experiment is a two-by-two comparison: fixed versus adaptive flows, each with and without the contract discount. Use the same network, nutrition targets, price draws, and disrupted routes in all four cells. Report cost, delivered nutrition and infeasibility together. An adaptive plan with more information or different feasibility rules is not a matched comparison.

Preserve the hybrid-node balance `procurement + inflow = outflow + local_delivery` in every cell. Count unserved demand explicitly when a route fails; a smaller invoice caused by leaving people unserved is not an improvement. The contract effect is the within-policy discount difference; the recourse effect is the within-price-regime policy difference. Report their interaction when it is material. This proposed decomposition uses synthetic scenarios and makes no operational relief recommendation.

## References

- https://web.stanford.edu/~boyd/cvxbook/
- https://github.com/3orionkings/ai-product-team/blob/main/workflows/process-change.md
