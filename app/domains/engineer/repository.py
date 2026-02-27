from __future__ import annotations

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth.models import User
from app.domains.engineer.models import Engineer, SiteAssignment
from app.shared.enums import AssignmentStatus, BESSStage, Specialization
from app.shared.exceptions import EngineerNotAvailableException


ACTIVE_ASSIGNMENT_STATUSES = [
    AssignmentStatus.PENDING,
    AssignmentStatus.ACCEPTED,
    AssignmentStatus.IN_PROGRESS,
]


class EngineerRepository:
    async def create_engineer(self, db: AsyncSession, engineer: Engineer) -> Engineer:
        db.add(engineer)
        await db.flush()
        return engineer

    async def list_available(
        self,
        db: AsyncSession,
        page: int,
        size: int,
        city_id: int | None,
        specialization: Specialization | None,
    ) -> tuple[int, list[Engineer]]:
        count_stmt = select(func.count(Engineer.id)).where(Engineer.is_available.is_(True))
        stmt: Select[tuple[Engineer]] = select(Engineer).where(Engineer.is_available.is_(True))
        if city_id is not None:
            count_stmt = count_stmt.where(Engineer.city_id == city_id)
            stmt = stmt.where(Engineer.city_id == city_id)
        if specialization is not None:
            count_stmt = count_stmt.where(Engineer.specialization == specialization)
            stmt = stmt.where(Engineer.specialization == specialization)

        total = await db.scalar(count_stmt)
        items = (
            await db.scalars(stmt.order_by(Engineer.id).offset((page - 1) * size).limit(size))
        ).all()
        return int(total or 0), list(items)

    async def list_candidate_users(
        self,
        db: AsyncSession,
        page: int,
        size: int,
        query: str | None,
        unassigned_only: bool,
    ) -> tuple[int, list[User]]:
        count_stmt = select(func.count(User.id)).where(User.is_active.is_(True))
        stmt: Select[tuple[User]] = select(User).where(User.is_active.is_(True))

        if unassigned_only:
            count_stmt = count_stmt.outerjoin(Engineer, Engineer.user_id == User.id).where(Engineer.id.is_(None))
            stmt = stmt.outerjoin(Engineer, Engineer.user_id == User.id).where(Engineer.id.is_(None))

        normalized_query = (query or "").strip()
        if normalized_query:
            like_value = f"%{normalized_query}%"
            search_filter = (
                User.full_name.ilike(like_value)
                | User.email.ilike(like_value)
                | User.phone.ilike(like_value)
            )
            count_stmt = count_stmt.where(search_filter)
            stmt = stmt.where(search_filter)

        total = await db.scalar(count_stmt)
        items = (
            await db.scalars(stmt.order_by(User.id.asc()).offset((page - 1) * size).limit(size))
        ).all()
        return int(total or 0), list(items)

    async def count_active_assignments(self, db: AsyncSession, engineer_id: int) -> int:
        stmt = select(func.count(SiteAssignment.id)).where(
            SiteAssignment.engineer_id == engineer_id,
            SiteAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
        )
        return int(await db.scalar(stmt) or 0)

    async def find_best_available(
        self,
        db: AsyncSession,
        specialization: str | None,
        city_id: int,
        country_id: int,
    ) -> Engineer:
        filters = [Engineer.is_available.is_(True)]
        if specialization is not None:
            filters.append(Engineer.specialization == Specialization(specialization))

        base = (
            select(
                Engineer,
                func.count(
                    case(
                        (
                            SiteAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
                            SiteAssignment.id,
                        ),
                        else_=None,
                    )
                ).label("active_count"),
            )
            .outerjoin(SiteAssignment, SiteAssignment.engineer_id == Engineer.id)
            .where(and_(*filters))
            .group_by(Engineer.id)
        )

        city_stmt = base.where(Engineer.city_id == city_id).order_by(
            "active_count", Engineer.max_concurrent_assignments.desc(), Engineer.id.asc()
        )
        city_candidates = (await db.execute(city_stmt)).all()
        for engineer, active_count in city_candidates:
            if int(active_count or 0) < engineer.max_concurrent_assignments:
                return engineer

        country_stmt = base.where(Engineer.country_id == country_id).order_by(
            "active_count", Engineer.max_concurrent_assignments.desc(), Engineer.id.asc()
        )
        country_candidates = (await db.execute(country_stmt)).all()
        for engineer, active_count in country_candidates:
            if int(active_count or 0) < engineer.max_concurrent_assignments:
                return engineer

        raise EngineerNotAvailableException()

    async def create_assignment(self, db: AsyncSession, assignment: SiteAssignment) -> SiteAssignment:
        db.add(assignment)
        await db.flush()
        return assignment

    async def list_assignments_for_bess(
        self,
        db: AsyncSession,
        bess_unit_id: int,
        page: int,
        size: int,
    ) -> tuple[int, list[SiteAssignment]]:
        total = await db.scalar(
            select(func.count(SiteAssignment.id)).where(SiteAssignment.bess_unit_id == bess_unit_id)
        )
        stmt: Select[tuple[SiteAssignment]] = (
            select(SiteAssignment)
            .where(SiteAssignment.bess_unit_id == bess_unit_id)
            .order_by(SiteAssignment.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items = (await db.scalars(stmt)).all()
        return int(total or 0), list(items)

    async def list_assignments_for_engineer(
        self,
        db: AsyncSession,
        engineer_id: int,
        page: int,
        size: int,
    ) -> tuple[int, list[SiteAssignment]]:
        total = await db.scalar(
            select(func.count(SiteAssignment.id)).where(SiteAssignment.engineer_id == engineer_id)
        )
        stmt: Select[tuple[SiteAssignment]] = (
            select(SiteAssignment)
            .where(SiteAssignment.engineer_id == engineer_id)
            .order_by(SiteAssignment.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items = (await db.scalars(stmt)).all()
        return int(total or 0), list(items)

    async def get_engineer_by_user_id(self, db: AsyncSession, user_id: int) -> Engineer | None:
        stmt = select(Engineer).where(Engineer.user_id == user_id)
        return await db.scalar(stmt)

    async def get_assignment(self, db: AsyncSession, assignment_id: int) -> SiteAssignment | None:
        return await db.get(SiteAssignment, assignment_id)

    async def get_existing_assignment_for_stage(
        self,
        db: AsyncSession,
        bess_unit_id: int,
        stage: BESSStage,
    ) -> SiteAssignment | None:
        stmt = (
            select(SiteAssignment)
            .where(SiteAssignment.bess_unit_id == bess_unit_id, SiteAssignment.assigned_stage == stage)
            .order_by(SiteAssignment.id.desc())
        )
        return await db.scalar(stmt)


engineer_repository = EngineerRepository()
