from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.domains.auth.models import User
from app.domains.bess_unit.models import BESSUnit, StageHistory
from app.domains.bess_unit.service import _ensure_qr_file
from app.domains.engineer.models import Engineer, SiteAssignment
from app.domains.installation.models import ChecklistResponse, ChecklistTemplate
from app.domains.master.models import City, Country, ProductModel, Warehouse
from app.domains.rbac.models import Role, UserRole
from app.domains.shipment.models import Shipment, ShipmentItem
from app.shared.acid import atomic
from app.shared.enums import AssignmentStatus, BESSStage, ShipmentStatus


async def _get_or_create_user(
    session,
    *,
    email: str,
    full_name: str,
    phone: str,
    password: str,
    role_name: str,
    assigned_by_user_id: int | None,
) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name=full_name,
            phone=phone,
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.flush()

    role = await session.scalar(select(Role).where(Role.name == role_name))
    if role is not None:
        mapping = await session.scalar(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id))
        if mapping is None:
            session.add(
                UserRole(
                    user_id=user.id,
                    role_id=role.id,
                    assigned_by_user_id=assigned_by_user_id,
                )
            )
            await session.flush()

    return user


async def _get_or_create_bess_unit(
    session,
    *,
    serial_number: str,
    stage: BESSStage,
    product_model_id: int,
    country_id: int,
    city_id: int,
    warehouse_id: int | None,
    site_address: str | None,
    customer_user_id: int | None,
) -> BESSUnit:
    unit = await session.scalar(select(BESSUnit).where(BESSUnit.serial_number == serial_number))
    qr_code_url, _ = _ensure_qr_file(serial_number)

    if unit is None:
        unit = BESSUnit(
            serial_number=serial_number,
            qr_code_url=qr_code_url,
            product_model_id=product_model_id,
            current_stage=stage,
            country_id=country_id,
            city_id=city_id,
            warehouse_id=warehouse_id,
            site_address=site_address,
            site_latitude=28.6139 if city_id else None,
            site_longitude=77.2090 if city_id else None,
            customer_user_id=customer_user_id,
            manufactured_date=datetime.now(UTC),
            is_active=stage == BESSStage.ACTIVE,
            is_deleted=False,
        )
        session.add(unit)
        await session.flush()
    else:
        unit.current_stage = stage
        unit.warehouse_id = warehouse_id
        unit.site_address = site_address
        unit.customer_user_id = customer_user_id
        unit.qr_code_url = qr_code_url
        unit.is_active = stage == BESSStage.ACTIVE
        await session.flush()

    return unit


async def _upsert_stage_history(session, unit_id: int, from_stage: BESSStage, to_stage: BESSStage, changed_by: int):
    row = await session.scalar(
        select(StageHistory).where(
            StageHistory.bess_unit_id == unit_id,
            StageHistory.from_stage == from_stage,
            StageHistory.to_stage == to_stage,
        )
    )
    if row is None:
        session.add(
            StageHistory(
                bess_unit_id=unit_id,
                from_stage=from_stage,
                to_stage=to_stage,
                changed_by_user_id=changed_by,
                notes="Demo seeded transition",
            )
        )
        await session.flush()


async def _seed_checklist_progress(
    session,
    *,
    bess_unit_id: int,
    stage: BESSStage,
    checked_count: int,
    checked_by_user_id: int,
):
    templates = (
        await session.scalars(
            select(ChecklistTemplate)
            .where(ChecklistTemplate.stage == stage)
            .order_by(ChecklistTemplate.order_index.asc(), ChecklistTemplate.id.asc())
        )
    ).all()

    for idx, template in enumerate(templates):
        response = await session.scalar(
            select(ChecklistResponse).where(
                ChecklistResponse.bess_unit_id == bess_unit_id,
                ChecklistResponse.checklist_template_id == template.id,
            )
        )
        is_checked = idx < checked_count
        if response is None:
            response = ChecklistResponse(
                bess_unit_id=bess_unit_id,
                checklist_template_id=template.id,
                stage=stage,
                is_checked=is_checked,
                checked_by_user_id=checked_by_user_id if is_checked else None,
                checked_at=datetime.now(UTC) if is_checked else None,
                notes="Seeded demo checklist item",
                photo_url="https://example.com/demo-check.jpg" if (is_checked and template.requires_photo) else None,
            )
            session.add(response)
        else:
            response.is_checked = is_checked
            response.checked_by_user_id = checked_by_user_id if is_checked else None
            response.checked_at = datetime.now(UTC) if is_checked else None
            response.notes = "Seeded demo checklist item"
            response.photo_url = "https://example.com/demo-check.jpg" if (is_checked and template.requires_photo) else None
    await session.flush()


async def _get_engineer_for_city(session, city_id: int, fallback_city_id: int | None = None) -> Engineer:
    engineer = await session.scalar(select(Engineer).where(Engineer.city_id == city_id).order_by(Engineer.id.asc()))
    if engineer is None and fallback_city_id is not None:
        engineer = await session.scalar(
            select(Engineer).where(Engineer.city_id == fallback_city_id).order_by(Engineer.id.asc())
        )
    if engineer is None:
        raise RuntimeError("No engineer found. Run scripts/seed.py first.")
    return engineer


async def _upsert_assignment(
    session,
    *,
    bess_unit_id: int,
    engineer_id: int,
    stage: BESSStage,
    status: AssignmentStatus,
    assigned_by: str,
):
    assignment = await session.scalar(
        select(SiteAssignment)
        .where(SiteAssignment.bess_unit_id == bess_unit_id, SiteAssignment.assigned_stage == stage)
        .order_by(SiteAssignment.id.desc())
    )
    if assignment is None:
        assignment = SiteAssignment(
            bess_unit_id=bess_unit_id,
            engineer_id=engineer_id,
            assigned_stage=stage,
            status=status,
            assigned_by=assigned_by,
            notes="Seeded demo assignment",
        )
        session.add(assignment)
    else:
        assignment.engineer_id = engineer_id
        assignment.status = status
        assignment.assigned_by = assigned_by
        assignment.notes = "Seeded demo assignment"
    await session.flush()


async def seed_demo_data() -> None:
    async with AsyncSessionLocal() as db:
        async with atomic(db) as session:
            admin = await session.scalar(select(User).where(User.email == settings.default_admin_email))
            if admin is None:
                raise RuntimeError("Admin user not found. Run scripts/seed.py first.")

            customer = await _get_or_create_user(
                session,
                email="customer.demo@bess.com",
                full_name="Demo Customer",
                phone="9000000001",
                password="Customer@123",
                role_name="CUSTOMER",
                assigned_by_user_id=admin.id,
            )
            await _get_or_create_user(
                session,
                email="factory.demo@bess.com",
                full_name="Demo Factory Admin",
                phone="9000000002",
                password="Factory@123",
                role_name="FACTORY_ADMIN",
                assigned_by_user_id=admin.id,
            )
            await _get_or_create_user(
                session,
                email="logistics.demo@bess.com",
                full_name="Demo Logistics",
                phone="9000000003",
                password="Logistics@123",
                role_name="LOGISTICS_OPS",
                assigned_by_user_id=admin.id,
            )

            india = await session.scalar(select(Country).where(Country.code == "IN"))
            delhi = await session.scalar(select(City).where(City.name == "Delhi", City.country_id == india.id))
            mumbai = await session.scalar(select(City).where(City.name == "Mumbai", City.country_id == india.id))
            delhi_wh = await session.scalar(select(Warehouse).where(Warehouse.city_id == delhi.id))
            mumbai_wh = await session.scalar(select(Warehouse).where(Warehouse.city_id == mumbai.id))
            product = await session.scalar(select(ProductModel).where(ProductModel.model_number == "UNITYESS-125-261-OS"))

            if not all([india, delhi, mumbai, product]):
                raise RuntimeError("Master data missing. Run scripts/seed.py first.")

            unit_1 = await _get_or_create_bess_unit(
                session,
                serial_number="DEMO-BESS-001",
                stage=BESSStage.FACTORY_REGISTERED,
                product_model_id=product.id,
                country_id=india.id,
                city_id=delhi.id,
                warehouse_id=delhi_wh.id if delhi_wh else None,
                site_address="Demo Site Alpha, Delhi",
                customer_user_id=customer.id,
            )
            unit_2 = await _get_or_create_bess_unit(
                session,
                serial_number="DEMO-BESS-002",
                stage=BESSStage.IN_TRANSIT,
                product_model_id=product.id,
                country_id=india.id,
                city_id=mumbai.id,
                warehouse_id=mumbai_wh.id if mumbai_wh else None,
                site_address="Demo Site Beta, Mumbai",
                customer_user_id=customer.id,
            )
            unit_3 = await _get_or_create_bess_unit(
                session,
                serial_number="DEMO-BESS-003",
                stage=BESSStage.SITE_ARRIVED,
                product_model_id=product.id,
                country_id=india.id,
                city_id=delhi.id,
                warehouse_id=delhi_wh.id if delhi_wh else None,
                site_address="Demo Site Gamma, Delhi",
                customer_user_id=customer.id,
            )
            unit_4 = await _get_or_create_bess_unit(
                session,
                serial_number="DEMO-BESS-004",
                stage=BESSStage.PRE_COMMISSION,
                product_model_id=product.id,
                country_id=india.id,
                city_id=delhi.id,
                warehouse_id=delhi_wh.id if delhi_wh else None,
                site_address="Demo Site Delta, Delhi",
                customer_user_id=customer.id,
            )

            await _upsert_stage_history(
                session,
                unit_id=unit_2.id,
                from_stage=BESSStage.PACKED,
                to_stage=BESSStage.IN_TRANSIT,
                changed_by=admin.id,
            )
            await _upsert_stage_history(
                session,
                unit_id=unit_3.id,
                from_stage=BESSStage.DISPATCHED_TO_SITE,
                to_stage=BESSStage.SITE_ARRIVED,
                changed_by=admin.id,
            )
            await _upsert_stage_history(
                session,
                unit_id=unit_4.id,
                from_stage=BESSStage.AC_INSTALLATION,
                to_stage=BESSStage.PRE_COMMISSION,
                changed_by=admin.id,
            )

            await _seed_checklist_progress(
                session,
                bess_unit_id=unit_3.id,
                stage=BESSStage.SITE_ARRIVED,
                checked_count=2,
                checked_by_user_id=admin.id,
            )
            await _seed_checklist_progress(
                session,
                bess_unit_id=unit_4.id,
                stage=BESSStage.PRE_COMMISSION,
                checked_count=4,
                checked_by_user_id=admin.id,
            )

            shipment = await session.scalar(select(Shipment).where(Shipment.shipment_code == "DEMO-SHP-001"))
            if shipment is None:
                shipment = Shipment(
                    shipment_code="DEMO-SHP-001",
                    origin_country_id=india.id,
                    destination_country_id=india.id,
                    status=ShipmentStatus.IN_TRANSIT,
                )
                session.add(shipment)
                await session.flush()
            else:
                shipment.status = ShipmentStatus.IN_TRANSIT
                await session.flush()

            for unit in (unit_1, unit_2):
                item = await session.scalar(
                    select(ShipmentItem).where(
                        ShipmentItem.shipment_id == shipment.id,
                        ShipmentItem.bess_unit_id == unit.id,
                    )
                )
                if item is None:
                    session.add(ShipmentItem(shipment_id=shipment.id, bess_unit_id=unit.id))
            await session.flush()

            delhi_engineer = await _get_engineer_for_city(session, delhi.id, fallback_city_id=mumbai.id)
            await _upsert_assignment(
                session,
                bess_unit_id=unit_3.id,
                engineer_id=delhi_engineer.id,
                stage=BESSStage.SITE_ARRIVED,
                status=AssignmentStatus.IN_PROGRESS,
                assigned_by="MANUAL",
            )
            await _upsert_assignment(
                session,
                bess_unit_id=unit_4.id,
                engineer_id=delhi_engineer.id,
                stage=BESSStage.PRE_COMMISSION,
                status=AssignmentStatus.PENDING,
                assigned_by="AUTO",
            )

    print("Demo data seeded successfully.")
    print("Demo login users:")
    print(f"- {settings.default_admin_email} / {settings.default_admin_password}")
    print("- factory.demo@bess.com / Factory@123")
    print("- logistics.demo@bess.com / Logistics@123")
    print("- customer.demo@bess.com / Customer@123")
    print("Demo BESS serials:")
    print("- DEMO-BESS-001 (FACTORY_REGISTERED)")
    print("- DEMO-BESS-002 (IN_TRANSIT)")
    print("- DEMO-BESS-003 (SITE_ARRIVED, checklist partial)")
    print("- DEMO-BESS-004 (PRE_COMMISSION, checklist in progress)")


if __name__ == "__main__":
    asyncio.run(seed_demo_data())
