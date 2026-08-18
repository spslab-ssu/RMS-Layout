from pathlib import Path
from types import SimpleNamespace


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "Data"

# Main-paper defaults. The strongest compact profile from the seminar is used.
PROBLEM_NAME = "single_part"
STRENGTHENING_PROFILE = "network_mir"
TIME_LIMIT = 300
MIP_GAP = 0.001
OUTPUT_FLAG = 1
SEED = 1
THREADS = 0

# Network and valid-inequality options.
SAME_MACHINE_RECONFIG_ONLY = True
PRUNE_DOMINATED_CUTS = True
THETA_VALUES = None
LP_RELAXATION = False

# Extensions are disabled in the main-paper baseline.
USE_SHARED_RESOURCES = False
OPTIMIZE_SHARED_RESOURCE_CAPACITY = False
RESOURCE_OPTIMIZATION_RESERVED_SECONDS = 120

# Relocation is opt-in so the published baseline remains exactly reproducible.
# These are layer-(ii) coupling assumptions, not lifecycle equations.
ENABLE_RELOCATION = False
RELOCATION_DISTANCE_COST = 1.0
RELOCATION_FIXED_COST = 0.0
RELOCATION_DOWNTIME_FRACTION = 0.0
RELOCATION_CREW_CAPACITY = None
FORBID_REVERSE_SWAPS = False
# Exact lexicographic policy: system cost first, relocation count second.
MINIMIZE_RELOCATIONS_SECONDARY = True
RELOCATION_SECONDARY_RESERVED_SECONDS = 60
RELOCATION_PRIMARY_COST_TOLERANCE = 1e-4
# A strict hierarchy requires the primary system cost to be proven exactly.
LEXICOGRAPHIC_PRIMARY_MIP_GAP = 0.0
# Number of equal-primary-cost configurations retained for visual comparison.
# Keep one in normal CLI runs; the interactive app raises this value.
STAGE_ONE_CONFIGURATION_LIMIT = 1
# Increasing marginal crew-slot cost: rank r costs r * step.
# Kept only for later sensitivity experiments; the main algorithm leaves it 0.
RELOCATION_CONGESTION_COST_STEP = 0.0

START_OPERATION = 0
END_OPERATION = 999


def build_config(
    problem_name: str = PROBLEM_NAME,
    profile: str = STRENGTHENING_PROFILE,
    result_dir: Path | None = None,
    **overrides,
) -> SimpleNamespace:
    """Create one self-contained experiment configuration."""
    values = {name: value for name, value in globals().items() if name.isupper()}
    problem_dir = DATA_DIR / problem_name
    values.update(
        {
            "PROBLEM_NAME": problem_name,
            "PROBLEM_DIR": problem_dir,
            "LOCATION_FILE": problem_dir / "locations.csv",
            "CONFIGURATION_FILE": problem_dir / "configurations.csv",
            "PRODUCTION_RATE_FILE": problem_dir / "production_rates.csv",
            "DEMAND_FILE": problem_dir / "demands.csv",
            "PARAMETER_FILE": problem_dir / "parameters.csv",
            "SHARED_RESOURCE_FILE": problem_dir / "shared_resources.csv",
            "RESOURCE_REQUIREMENT_FILE": problem_dir / "resource_requirements.csv",
            "STRENGTHENING_PROFILE": profile,
            "RESULT_DIR": result_dir or BASE_DIR / "results" / problem_name / profile,
        }
    )
    values.update(overrides)
    return SimpleNamespace(**values)


_DEFAULT = build_config()
for _name, _value in vars(_DEFAULT).items():
    globals()[_name] = _value
