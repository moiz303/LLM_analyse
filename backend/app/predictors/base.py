from __future__ import annotations

from abc import ABC, abstractmethod


class Predictor(ABC):
    mode = "unknown"

    @abstractmethod
    def predict(self, configuration: dict[str, float]) -> dict[str, float]:
        raise NotImplementedError