"""声学层（工单 265）。

P0 六项已全部落地：P0-1 反演（`atten_inverse`）、P0-2 空化剂量（`cavitation_dose`）、
P0-3 声源成像（`source_map`）、P0-4 标定集（`dataset` + `data/acoustics/`）、
P0-5/P0-6 两份设计文档（`docs/`）。
"""

from __future__ import annotations

from acoustics.atten_inverse import (
    DistributionFit,
    PowerLawFit,
    fit_power_law,
    gradient_fit_power_law,
    inversion_kernel,
    invert_distribution,
    lcurve_scan,
    plot_lcurve,
    power_law,
    power_law_basis,
    synthesize_distribution,
    synthesize_power_law,
    tikhonov_solve,
)
from acoustics.cavitation_dose import (
    BubbleResult,
    Medium,
    emission_spectrum,
    equilibrium_radius,
    gilmore_rhs,
    keller_rhs,
    minnaert_frequency,
    rp_rhs,
    simulate,
    tait_enthalpy,
)
from acoustics.cavitation_dose import (
    cavitation_dose as dose_from_result,
)
from acoustics.dataset import (
    DatasetSpec,
    generate_monodisperse_dataset,
    load_dataset,
    local_power_law_exponent,
    power_law_exponent,
)
from acoustics.dispersion import (
    ALUMINUM as PLATE_ALUMINUM,
)
from acoustics.dispersion import (
    STEEL as PLATE_STEEL,
)
from acoustics.dispersion import (
    Plate,
    cutoff_frequencies,
    lamb_symmetric_residual,
    plate_velocity,
    s0_curve,
    solve_symmetric_mode,
)
from acoustics.dispersion_branches import (
    a0_curve as a0_branch_curve,
)
from acoustics.dispersion_branches import (
    branch_roots,
    cutoff_families,
    expected_mode_count,
)
from acoustics.dispersion_branches import (
    s0_curve as s0_branch_curve,
)
from acoustics.source_map import (
    SourceMap,
    clean_sc,
    csm_from_snapshots,
    csm_from_sources,
    damas,
    das_map,
    localize,
    planar_array,
    psf_matrix,
    simulate_snapshots,
    steering_matrix,
)

__all__ = [
    "BubbleResult",
    "DatasetSpec",
    "DistributionFit",
    "a0_branch_curve",
    "branch_roots",
    "cutoff_families",
    "expected_mode_count",
    "PLATE_ALUMINUM",
    "PLATE_STEEL",
    "Plate",
    "Medium",
    "PowerLawFit",
    "SourceMap",
    "clean_sc",
    "csm_from_snapshots",
    "csm_from_sources",
    "damas",
    "das_map",
    "dose_from_result",
    "cutoff_frequencies",
    "emission_spectrum",
    "equilibrium_radius",
    "fit_power_law",
    "generate_monodisperse_dataset",
    "gradient_fit_power_law",
    "gilmore_rhs",
    "inversion_kernel",
    "invert_distribution",
    "lcurve_scan",
    "keller_rhs",
    "load_dataset",
    "lamb_symmetric_residual",
    "local_power_law_exponent",
    "localize",
    "minnaert_frequency",
    "planar_array",
    "plot_lcurve",
    "plate_velocity",
    "power_law_exponent",
    "s0_branch_curve",
    "s0_curve",
    "power_law",
    "power_law_basis",
    "psf_matrix",
    "rp_rhs",
    "simulate",
    "simulate_snapshots",
    "solve_symmetric_mode",
    "steering_matrix",
    "synthesize_distribution",
    "synthesize_power_law",
    "tait_enthalpy",
    "tikhonov_solve",
]
