"""Enums shared across API areas."""

from __future__ import annotations

from enum import StrEnum


class CloudProvider(StrEnum):
    GCP = "gcp"
    AWS = "aws"
    AZURE = "azure"


class InstanceType(StrEnum):
    """Instance types. ``ENTERPRISE_DB`` is AuraDB Virtual Dedicated Cloud."""

    ENTERPRISE_DB = "enterprise-db"
    ENTERPRISE_DS = "enterprise-ds"
    BUSINESS_CRITICAL = "business-critical"
    PROFESSIONAL_DB = "professional-db"
    PROFESSIONAL_DS = "professional-ds"
    FREE_DB = "free-db"
