from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.domains.auth.models import User
from app.domains.engineer.schemas import (
    EngineerCandidateUserRead,
    EngineerCreate,
    EngineerDashboardRead,
    EngineerOverviewRead,
    EngineerRead,
    ManualAssignmentCreate,
    PaginatedAssignments,
    PaginatedEngineerCandidateUsers,
    PaginatedEngineers,
    SiteAssignmentRead,
)
from app.domains.engineer.service import (
    accept_assignment,
    complete_assignment,
    create_engineer,
    decline_assignment,
    get_engineers_overview,
    get_my_dashboard,
    list_assignments_for_bess,
    list_available_engineers,
    list_engineer_candidate_users,
    list_my_assignments,
    manual_assign_engineer,
)
from app.shared.enums import BESSStage

router = APIRouter(tags=["Engineers"])


@router.get("/engineers/my-dashboard", response_model=EngineerDashboardRead)
async def my_dashboard_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("engineer:read")),
) -> EngineerDashboardRead:
    return await get_my_dashboard(db, current_user)


@router.get("/engineers/overview", response_model=EngineerOverviewRead)
async def engineers_overview_endpoint(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("engineer:read")),
) -> EngineerOverviewRead:
    return await get_engineers_overview(db)


@router.post("/engineers/", response_model=EngineerRead, status_code=status.HTTP_201_CREATED)
async def create_engineer_endpoint(
    payload: EngineerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user:manage")),
) -> EngineerRead:
    engineer = await create_engineer(db, payload, current_user)
    return EngineerRead.model_validate(engineer)


@router.get("/engineers/available", response_model=PaginatedEngineers)
async def list_available_engineers_endpoint(
    city_id: int | None = None,
    stage: BESSStage | None = None,
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("engineer:read")),
) -> PaginatedEngineers:
    total, items = await list_available_engineers(db, page, size, city_id, stage)
    return PaginatedEngineers(total=total, items=[EngineerRead.model_validate(e) for e in items], page=page, size=size)


@router.get("/engineers/candidate-users", response_model=PaginatedEngineerCandidateUsers)
async def list_candidate_users_endpoint(
    q: str | None = None,
    unassigned_only: bool = True,
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("user:manage")),
) -> PaginatedEngineerCandidateUsers:
    total, items = await list_engineer_candidate_users(db, page, size, q, unassigned_only)
    return PaginatedEngineerCandidateUsers(
        total=total,
        items=[EngineerCandidateUserRead.model_validate(item) for item in items],
        page=page,
        size=size,
    )


@router.get("/engineers/my-assignments", response_model=PaginatedAssignments)
async def my_assignments(
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("engineer:read")),
) -> PaginatedAssignments:
    total, items = await list_my_assignments(db, current_user, page, size)
    return PaginatedAssignments(
        total=total,
        items=[SiteAssignmentRead.model_validate(i) for i in items],
        page=page,
        size=size,
    )


@router.post("/bess/{bess_unit_id}/assign-engineer", response_model=SiteAssignmentRead)
async def manual_assign_endpoint(
    bess_unit_id: int,
    payload: ManualAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("engineer:assign")),
) -> SiteAssignmentRead:
    assignment = await manual_assign_engineer(
        db,
        bess_unit_id,
        payload.engineer_id,
        payload.stage,
        payload.notes,
        current_user,
    )
    return SiteAssignmentRead.model_validate(assignment)


@router.get("/bess/{bess_unit_id}/assignments", response_model=PaginatedAssignments)
async def list_assignments_endpoint(
    bess_unit_id: int,
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("engineer:read")),
) -> PaginatedAssignments:
    total, items = await list_assignments_for_bess(db, bess_unit_id, page, size)
    return PaginatedAssignments(
        total=total,
        items=[SiteAssignmentRead.model_validate(i) for i in items],
        page=page,
        size=size,
    )


@router.patch("/assignments/{assignment_id}/accept", response_model=SiteAssignmentRead)
async def accept_assignment_endpoint(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("engineer:read")),
) -> SiteAssignmentRead:
    assignment = await accept_assignment(db, assignment_id, current_user)
    return SiteAssignmentRead.model_validate(assignment)


@router.patch("/assignments/{assignment_id}/decline", response_model=SiteAssignmentRead)
async def decline_assignment_endpoint(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("engineer:read")),
) -> SiteAssignmentRead:
    assignment = await decline_assignment(db, assignment_id, current_user)
    return SiteAssignmentRead.model_validate(assignment)


@router.patch("/assignments/{assignment_id}/complete", response_model=SiteAssignmentRead)
async def complete_assignment_endpoint(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("engineer:read")),
) -> SiteAssignmentRead:
    assignment = await complete_assignment(db, assignment_id, current_user)
    return SiteAssignmentRead.model_validate(assignment)
