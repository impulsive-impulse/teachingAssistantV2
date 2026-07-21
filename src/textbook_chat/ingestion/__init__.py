"""Uploaded-textbook validation and artifact construction.

This package is the explicit adapter between arbitrary accepted uploads and
the frozen research pipeline. Adapter policies are versioned separately and
must never be written into the immutable research configuration.
"""

from .policy import INGESTION_POLICY_VERSION, IngestionPolicy

__all__ = ["INGESTION_POLICY_VERSION", "IngestionPolicy"]
