# Formulation comparison

| formulation | pure_lp_bound | mip_objective | mip_best_bound | mip_gap | binary_variables | branch_and_bound_nodes | mip_runtime_seconds |
|---|---|---|---|---|---|---|---|
| base | 20925.08148 | 22910.0 | 22910.0 | 0.0 | 1856 | 3062.0 | 6.506453 |
| network | 22162.618038 | 22910.0 | 22910.0 | 0.0 | 832 | 3300.0 | 2.337758 |
| network_mir | 22674.8 | 22910.0 | 22910.0 | 0.0 | 832 | 118.0 | 0.903584 |

The formulations use identical data, seed, thread setting, time limit, and MIP gap.
Different layouts with the same objective are alternative optimal solutions.
