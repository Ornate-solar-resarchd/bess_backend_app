from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth.models import User
from app.domains.bess_unit.models import AuditLog
from app.domains.bess_unit.repository import bess_repository
from app.domains.engineer.models import Engineer, SiteAssignment
from app.domains.engineer.repository import ACTIVE_ASSIGNMENT_STATUSES, engineer_repository
from app.domains.engineer.schemas import EngineerCreate
from app.shared.acid import atomic
from app.shared.enums import AssignmentStatus, BESSStage, SITE_STAGES, STAGE_TO_SPECIALIZATION, STAGE_TRANSITIONS, Specialization
from app.shared.exceptions import APINotFoundException, BESSNotFoundException


async def create_engineer(db: AsyncSession, payload: EngineerCreate, current_user: User) -> Engineer:
    async with atomic(db) as session:
        engineer = await engineer_repository.create_engineer(
            session,
            Engineer(
                user_id=payload.user_id,
                employee_code=payload.employee_code,
                specialization=payload.specialization,
                city_id=payload.city_id,
                country_id=payload.country_id,
                is_available=payload.is_available,
                max_concurrent_assignments=payload.max_concurrent_assignments,
                certifications=payload.certifications,
            ),
        )
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="ENGINEER_CREATE",
                entity_type="Engineer",
                entity_id=engineer.id,
                payload_json={"user_id": payload.user_id, "specialization": payload.specialization.value},
            ),
        )
    return engineer


async def list_available_engineers(
    db: AsyncSession,
    page: int,
    size: int,
    city_id: int | None,
    stage: BESSStage | None,
):
    specialization: Specialization | None = None
    if stage and stage in STAGE_TO_SPECIALIZATION:
        specialization = Specialization(STAGE_TO_SPECIALIZATION[stage])
    return await engineer_repository.list_available(db, page, size, city_id, specialization)


async def list_engineer_candidate_users(
    db: AsyncSession,
    page: int,
    size: int,
    query: str | None,
    unassigned_only: bool,
):
    return await engineer_repository.list_candidate_users(
        db=db,
        page=page,
        size=size,
        query=query,
        unassigned_only=unassigned_only,
    )


async def auto_assign_engineer(
    bess_unit_id: int,
    stage: BESSStage,
    db: AsyncSession,
) -> SiteAssignment:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)

    existing = await engineer_repository.get_existing_assignment_for_stage(db, bess_unit_id, stage)
    if existing and existing.status in ACTIVE_ASSIGNMENT_STATUSES + [AssignmentStatus.COMPLETED]:
        return existing

    required_spec = STAGE_TO_SPECIALIZATION.get(stage)

    engineer = await engineer_repository.find_best_available(
        db,
        specialization=required_spec,
        city_id=unit.city_id,
        country_id=unit.country_id,
    )

    async with atomic(db) as session:
        assignment = await engineer_repository.create_assignment(
            session,
            SiteAssignment(
                bess_unit_id=bess_unit_id,
                engineer_id=engineer.id,
                assigned_stage=stage,
                status=AssignmentStatus.PENDING,
                assigned_by="AUTO",
            ),
        )

        active_count = await engineer_repository.count_active_assignments(session, engineer.id)
        if active_count >= engineer.max_concurrent_assignments:
            engineer.is_available = False

        await bess_repository.create_audit_log(
            session,
            AuditLog(
                action="AUTO_ASSIGNMENT",
                entity_type="SiteAssignment",
                entity_id=assignment.id,
                payload_json={"engineer_id": engineer.id, "stage": stage.value},
            ),
        )

    from app.domains.engineer.tasks import notify_engineer_task

    notify_engineer_task.delay(assignment.id)
    return assignment


async def manual_assign_engineer(
    db: AsyncSession,
    bess_unit_id: int,
    engineer_id: int,
    stage: BESSStage,
    notes: str | None,
    current_user: User,
) -> SiteAssignment:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)

    engineer = await db.get(Engineer, engineer_id)
    if engineer is None:
        raise APINotFoundException("Engineer not found")

    async with atomic(db) as session:
        assignment = await engineer_repository.create_assignment(
            session,
            SiteAssignment(
                bess_unit_id=bess_unit_id,
                engineer_id=engineer_id,
                assigned_stage=stage,
                status=AssignmentStatus.PENDING,
                assigned_by="MANUAL",
                notes=notes,
            ),
        )

        active_count = await engineer_repository.count_active_assignments(session, engineer.id)
        if active_count >= engineer.max_concurrent_assignments:
            engineer.is_available = False

        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="MANUAL_ASSIGNMENT",
                entity_type="SiteAssignment",
                entity_id=assignment.id,
                payload_json={"engineer_id": engineer_id, "stage": stage.value},
            ),
        )

    return assignment


async def list_assignments_for_bess(db: AsyncSession, bess_unit_id: int, page: int, size: int):
    return await engineer_repository.list_assignments_for_bess(db, bess_unit_id, page, size)


async def list_my_assignments(db: AsyncSession, current_user: User, page: int, size: int):
    engineer = await engineer_repository.get_engineer_by_user_id(db, current_user.id)
    if engineer is None:
        raise APINotFoundException("Engineer profile not found")
    total, assignments = await engineer_repository.list_assignments_for_engineer(db, engineer.id, page, size)
    assigner_names = await engineer_repository.get_assignment_assigner_names(
        db,
        [assignment.id for assignment in assignments],
    )
    for assignment in assignments:
        setattr(assignment, "assigned_by_name", assigner_names.get(assignment.id))
    return total, assignments


async def accept_assignment(db: AsyncSession, assignment_id: int, current_user: User):
    assignment = await engineer_repository.get_assignment(db, assignment_id)
    if assignment is None:
        raise APINotFoundException("Assignment not found")

    engineer = await engineer_repository.get_engineer_by_user_id(db, current_user.id)
    if engineer is None or assignment.engineer_id != engineer.id:
        raise APINotFoundException("Assignment not found")

    async with atomic(db) as session:
        assignment.status = AssignmentStatus.ACCEPTED
        assignment.accepted_at = datetime.now(UTC)
        await session.flush()
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="ASSIGNMENT_ACCEPT",
                entity_type="SiteAssignment",
                entity_id=assignment.id,
            ),
        )
    return assignment


async def decline_assignment(db: AsyncSession, assignment_id: int, current_user: User):
    assignment = await engineer_repository.get_assignment(db, assignment_id)
    if assignment is None:
        raise APINotFoundException("Assignment not found")

    engineer = await engineer_repository.get_engineer_by_user_id(db, current_user.id)
    if engineer is None or assignment.engineer_id != engineer.id:
        raise APINotFoundException("Assignment not found")

    async with atomic(db) as session:
        assignment.status = AssignmentStatus.DECLINED
        await session.flush()
        engineer.is_available = True
        await session.flush()
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="ASSIGNMENT_DECLINE",
                entity_type="SiteAssignment",
                entity_id=assignment.id,
            ),
        )

    from app.domains.engineer.tasks import auto_assign_engineer_task

    auto_assign_engineer_task.delay(assignment.bess_unit_id, assignment.assigned_stage.value)
    return assignment


async def complete_assignment(db: AsyncSession, assignment_id: int, current_user: User):
    assignment = await engineer_repository.get_assignment(db, assignment_id)
    if assignment is None:
        raise APINotFoundException("Assignment not found")

    engineer = await engineer_repository.get_engineer_by_user_id(db, current_user.id)
    if engineer is None or assignment.engineer_id != engineer.id:
        raise APINotFoundException("Assignment not found")

    async with atomic(db) as session:
        assignment.status = AssignmentStatus.COMPLETED
        assignment.completed_at = datetime.now(UTC)
        await session.flush()

        active_count = await engineer_repository.count_active_assignments(session, engineer.id)
        engineer.is_available = active_count < engineer.max_concurrent_assignments

        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="ASSIGNMENT_COMPLETE",
                entity_type="SiteAssignment",
                entity_id=assignment.id,
            ),
        )

    next_stage = STAGE_TRANSITIONS.get(assignment.assigned_stage)
    if next_stage in SITE_STAGES:
        from app.domains.engineer.tasks import auto_assign_engineer_task

        auto_assign_engineer_task.delay(assignment.bess_unit_id, next_stage.value)

    return assignment
