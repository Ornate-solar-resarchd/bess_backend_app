from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.shared.enums import AssignmentStatus, BESSStage, Specialization


class EngineerCreate(BaseModel):
    user_id: int
    employee_code: str
    specialization: Specialization
    city_id: int
    country_id: int
    is_available: bool = True
    max_concurrent_assignments: int = 1
    certifications: dict | None = None


class EngineerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    employee_code: str
    specialization: Specialization
    city_id: int
    country_id: int
    is_available: bool
    max_concurrent_assignments: int
    certifications: dict | None


class ManualAssignmentCreate(BaseModel):
    engineer_id: int
    stage: BESSStage
    notes: str | None = None


class SiteAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bess_unit_id: int
    engineer_id: int
    assigned_stage: BESSStage
    status: AssignmentStatus
    assigned_by: str
    accepted_at: datetime | None
    completed_at: datetime | None
    notes: str | None
    created_at: datetime


class PaginatedEngineers(BaseModel):
    total: int
    items: list[EngineerRead]
    page: int
    size: int


class PaginatedAssignments(BaseModel):
    total: int
    items: list[SiteAssignmentRead]
    page: int
    size: int


class EngineerCandidateUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    phone: str | None
    is_active: bool


class PaginatedEngineerCandidateUsers(BaseModel):
    total: int
    items: list[EngineerCandidateUserRead]
    page: int
    size: int
