"""
Short-horizon drift estimator.

Wraps a scikit-learn regressor that predicts short-horizon price drift
(expressed as a fraction of mid price per second) from the multi-scale
feature vector produced by features.py.

The model is intentionally simple at this stage: a Ridge regressor trained
on historical feature vectors with realized short-horizon returns as labels.
This baseline can be swapped for a more expressive model (gradient boosting,
LSTM, etc.) once sufficient training data has been collected from paper trading.

Training workflow (not yet implemented — see TODO):
  1. Run paper trading to accumulate (features, realized_drift) pairs.
  2. Call DriftEstimator.train(X, y) to fit and persist the model.
  3. The live controller calls DriftEstimator.predict(features) each tick.

Until a trained model is available, predict() returns 0.0, which causes
the Avellaneda-Stoikov model to operate with zero-drift assumption (safe default).
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Optional

import numpy as np


class DriftEstimator:
    """
    Wraps a regression model for short-horizon drift prediction.

    The model is loaded from disk if a persisted file exists; otherwise
    it operates in zero-drift mode until trained and saved.
    """

    DEFAULT_MODEL_PATH = Path("models/drift_estimator.pkl")

    def __init__(self, model_path: Optional[Path] = None) -> None:
        self._model_path = model_path or self.DEFAULT_MODEL_PATH
        self._model = None
        self._feature_order: Optional[list[str]] = None
        self._load_if_exists()

    def predict(self, features: dict[str, float]) -> float:
        """
        Return the drift estimate in units of (quote asset / second).

        If no trained model is loaded, returns 0.0 (zero-drift fallback).
        """
        if self._model is None or self._feature_order is None:
            return 0.0

        x = np.array(
            [features.get(k, 0.0) for k in self._feature_order], dtype=float
        ).reshape(1, -1)

        return float(self._model.predict(x)[0])

    def train(self, X: np.ndarray, y: np.ndarray, feature_names: list[str]) -> None:
        """
        Fit a Ridge regressor on (X, y) and persist it to disk.

        Parameters
        ----------
        X:
            2-D array of shape (n_samples, n_features).
        y:
            1-D array of realized short-horizon drift values.
        feature_names:
            Ordered list of feature names corresponding to columns of X.
            Must match the keys produced by features.compute_features().
        """
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        model = Pipeline([
            ("scaler", StandardScaler()),
            ("ridge", Ridge(alpha=1.0)),
        ])
        model.fit(X, y)

        self._model = model
        self._feature_order = feature_names
        self._persist()

    def _load_if_exists(self) -> None:
        if not self._model_path.exists():
            return
        with self._model_path.open("rb") as f:
            payload = pickle.load(f)
        self._model = payload["model"]
        self._feature_order = payload["feature_order"]

    def _persist(self) -> None:
        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"model": self._model, "feature_order": self._feature_order}
        with self._model_path.open("wb") as f:
            pickle.dump(payload, f)
