"""Exceptions métier et objets de diagnostic OptiFLUX."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Diagnostic:
    sheet: str | None
    row: int | None
    column: str | None
    severity: str
    code: str
    message: str
    action: str | None = None


class OptiFluxError(Exception):
    """Classe de base des erreurs métier OptiFLUX."""


class ImportBlockingError(OptiFluxError):
    """Erreur bloquante détectée pendant l'import Excel."""

    def __init__(self, diagnostics: list[Diagnostic]):
        self.diagnostics = diagnostics
        super().__init__("Erreurs bloquantes à l'import")


class InfeasibleProblemError(OptiFluxError):
    """Le problème ne peut pas être résolu avec les paramètres donnés."""

    def __init__(self, diagnostics: list[Diagnostic]):
        self.diagnostics = diagnostics
        super().__init__("Problème logistique infaisable")


class OptimizationError(OptiFluxError):
    """Erreur d'optimisation ou solution invalide."""
