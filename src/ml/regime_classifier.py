"""
Market regime classifier.

Identifies the current market regime from the multi-scale feature vector
and returns a MarketRegime label. The active regime determines how the
Avellaneda-Stoikov controller adjusts its behavior:

  RANGING:        Normal conditions. Standard A-S parameters apply.
  TRENDING:       Sustained directional pressure. Quote skewing is more
                  aggressive; order sizes are reduced to limit adverse fills.
  HIGH_VOLATILITY: Chaotic conditions. Spreads are widened significantly;
                   quoting may be suspended entirely above a volatility threshold.

As with the drift estimator, a trained model is not required for the system
to function. When no model is loaded, predict() returns RANGING, which causes
the controller to run standard A-S parameters — the safest default.

Training workflow (not yet implemented — see TODO):
  1. Collect feature vectors and hand-label or algorithmically label regimes
     from historical data (e.g. using realized volatility thresholds and
     Hurst exponent to distinguish trending from ranging).
  2. Call RegimeClassifier.train(X, y) to fit and persist the model.
"""

from __future__ import annotations

import pickle
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np


class MarketRegime(str, Enum):
    RANGING = "ranging"
    TRENDING = "trending"
    HIGH_VOLATILITY = "high_volatility"


class RegimeClassifier:
    """
    Wraps a classification model for market regime detection.

    Falls back to MarketRegime.RANGING when no trained model is loaded.
    """

    DEFAULT_MODEL_PATH = Path("models/regime_classifier.pkl")

    def __init__(self, model_path: Optional[Path] = None) -> None:
        self._model_path = model_path or self.DEFAULT_MODEL_PATH
        self._model = None
        self._feature_order: Optional[list[str]] = None
        self._load_if_exists()

    def predict(self, features: dict[str, float]) -> MarketRegime:
        """
        Return the predicted market regime for the current feature vector.

        Falls back to RANGING if no model is loaded.
        """
        if self._model is None or self._feature_order is None:
            return MarketRegime.RANGING

        x = np.array(
            [features.get(k, 0.0) for k in self._feature_order], dtype=float
        ).reshape(1, -1)

        label = self._model.predict(x)[0]
        return MarketRegime(label)

    def train(self, X: np.ndarray, y: np.ndarray, feature_names: list[str]) -> None:
        """
        Fit a Random Forest classifier on (X, y) and persist it to disk.

        Parameters
        ----------
        X:
            2-D array of shape (n_samples, n_features).
        y:
            1-D array of MarketRegime string values or equivalent integer labels.
        feature_names:
            Ordered list of feature names matching columns of X.
        """
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", RandomForestClassifier(n_estimators=100, random_state=42)),
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
