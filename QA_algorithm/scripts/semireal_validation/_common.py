"""Shared 1PL defect-shift estimator for semi-real validation studies."""

import numpy as np

PRIOR_SD = 3.0


def fit_delta(y, base_logit, prior_sd=PRIOR_SD):
    y = np.asarray(y, float)
    d = 0.0
    for _ in range(100):
        p = 1.0 / (1.0 + np.exp(-(base_logit - d)))
        g = float(np.sum(p - y)) - d / prior_sd**2
        h = -float(np.sum(p * (1 - p))) - 1.0 / prior_sd**2
        step = g / h
        d -= step
        if abs(step) < 1e-10:
            break
    p = 1.0 / (1.0 + np.exp(-(base_logit - d)))
    se = 1.0 / np.sqrt(np.sum(p * (1 - p)) + 1.0 / prior_sd**2)
    return float(d), float(se)
