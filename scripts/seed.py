from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.domains.auth.models import User
from app.domains.engineer.models import Engineer
from app.domains.installation.models import ChecklistTemplate
from app.domains.master.models import City, Country, ProductModel, Warehouse
from app.domains.rbac.models import Permission, Role, RolePermission, UserRole
from app.shared.acid import atomic
from app.shared.enums import BESSStage, Specialization


PERMISSIONS = [
    "bess:create",
    "bess:read",
    "bess:transition",
    "checklist:read",
    "checklist:write",
    "engineer:assign",
    "engineer:read",
    "shipment:manage",
    "shipment:read",
    "master:write",
    "master:read",
    "report:view",
    "user:manage",
    "role:manage",
]

ROLE_PERMISSIONS = {
    "SUPER_ADMIN": PERMISSIONS,
    "FACTORY_ADMIN": ["bess:create", "bess:read", "shipment:manage", "master:write", "master:read"],
    "LOGISTICS_OPS": ["shipment:manage", "shipment:read", "bess:read", "bess:transition"],
    "SITE_ENGINEER": [
        "bess:read",
        "checklist:read",
        "checklist:write",
        "bess:transition",
        "engineer:read",
    ],
    "QA_INSPECTOR": ["checklist:read", "bess:read", "report:view"],
    "CUSTOMER": ["bess:read", "report:view"],
}

CHECKLISTS: dict[BESSStage, list[dict[str, object]]] = {
    BESSStage.SITE_ARRIVED: [
        {"item_text": "Inspect unit for physical damage", "is_mandatory": True, "requires_photo": True},
        {"item_text": "Verify serial number matches delivery note", "is_mandatory": True},
        {"item_text": "Confirm correct unit delivered to correct site", "is_mandatory": True},
    ],
    BESSStage.CIVIL_INSTALLATION: [
        {"item_text": "Foundation >=800x800mm concrete pad confirmed", "is_mandatory": True},
        {"item_text": "Ground level within +/-5mm tolerance (spirit level)", "is_mandatory": True},
        {"item_text": "BESS cabinet placed per layout drawing", "is_mandatory": True},
        {
            "item_text": "Cabinet secured with M24 anchor bolts to specified torque",
            "is_mandatory": True,
        },
        {"item_text": "Minimum 1000mm clearance on all 4 sides confirmed", "is_mandatory": True},
        {"item_text": "Anti-vibration pads installed under cabinet", "is_mandatory": True},
        {"item_text": "Post-placement photo captured", "is_mandatory": True, "requires_photo": True},
    ],
    BESSStage.DC_INSTALLATION: [
        {
            "item_text": "All DC breakers confirmed OFF before wiring",
            "is_mandatory": True,
            "safety_warning": "Electrocution risk",
        },
        {"item_text": "Battery cluster cables connected per wiring diagram", "is_mandatory": True},
        {"item_text": "Busbar bolts torqued to spec - blue pen mark by installer", "is_mandatory": True},
        {"item_text": "Inspector re-torque verified - red pen mark applied", "is_mandatory": True},
        {"item_text": "No loose DC connections found", "is_mandatory": True},
        {
            "item_text": "Anti-static gloves worn throughout",
            "is_mandatory": True,
            "safety_warning": "ESD damage risk",
        },
        {"item_text": "BMU boards not touched bare-handed", "is_mandatory": True},
    ],
    BESSStage.AC_INSTALLATION: [
        {
            "item_text": "MCCB1 (AC circuit breaker) confirmed OFF",
            "is_mandatory": True,
            "safety_warning": "Electrocution risk",
        },
        {"item_text": "AC grid cables connected to combiner cabinet", "is_mandatory": True},
        {"item_text": "Phase sequence verified A-B-C: 400V between phases", "is_mandatory": True},
        {"item_text": "Phase-to-neutral verified: 230V", "is_mandatory": True},
        {"item_text": "PE grounding wire connected and secure", "is_mandatory": True},
        {"item_text": "All cable entries sealed with sealing compound", "is_mandatory": True},
        {"item_text": "No cables routed through air inlet or outlet", "is_mandatory": True},
        {"item_text": "Cables of different types separated >=30mm", "is_mandatory": True},
    ],
    BESSStage.PRE_COMMISSION: [
        {"item_text": "All wiring connections verified correct", "is_mandatory": True},
        {"item_text": "BMS<->EMS communication cables connected", "is_mandatory": True},
        {"item_text": "No loose connections throughout the entire unit", "is_mandatory": True},
        {"item_text": "AC surge protector indicator is GREEN", "is_mandatory": True},
        {"item_text": "UPS functional and output confirmed", "is_mandatory": True},
        {
            "item_text": "CO2 fire extinguisher present on site",
            "is_mandatory": True,
            "safety_warning": "Fire risk",
        },
        {"item_text": '"Do Not Close" warning signs on all switches', "is_mandatory": True},
    ],
    BESSStage.COLD_COMMISSION: [
        {"item_text": "MCCB2 (auxiliary power) turned ON", "is_mandatory": True},
        {"item_text": "AC output button pressed - indicator GREEN", "is_mandatory": True},
        {"item_text": "UPS started successfully", "is_mandatory": True},
        {"item_text": "BMS contactor status: CLOSED after 30 seconds", "is_mandatory": True},
        {"item_text": "PCS indicator illuminated", "is_mandatory": True},
        {"item_text": "EMS web interface accessible", "is_mandatory": True},
        {"item_text": "Zero alarms present at startup", "is_mandatory": True},
    ],
    BESSStage.HOT_COMMISSION: [
        {"item_text": "Charging test: SOC increasing confirmed", "is_mandatory": True, "requires_photo": True},
        {"item_text": "Discharging test: load response verified", "is_mandatory": True},
        {"item_text": "Grid synchronization: voltage and frequency within tolerance", "is_mandatory": True},
        {"item_text": "No alarms in EMS dashboard", "is_mandatory": True},
        {"item_text": "Performance test completed and result logged", "is_mandatory": True},
    ],
    BESSStage.FINAL_ACCEPTANCE: [
        {"item_text": "QA team sign-off obtained", "is_mandatory": True},
        {
            "item_text": "Customer acceptance signature collected",
            "is_mandatory": True,
            "requires_photo": True,
        },
        {"item_text": "Warranty start date recorded in system", "is_mandatory": True},
        {"item_text": "All checklist documentation uploaded", "is_mandatory": True},
        {"item_text": "Full photo set of installation captured", "is_mandatory": True, "requires_photo": True},
    ],
}


@dataclass(slots=True)
class EngineerSeed:
    city_name: str
    country_code: str
    specialization: Specialization
    email: str
    employee_code: str
    full_name: str


ENGINEERS: list[EngineerSeed] = [
    EngineerSeed("Delhi", "IN", Specialization.CIVIL, "eng.delhi.civil@bess.com", "IN-DL-001", "Delhi Civil 1"),
    EngineerSeed("Delhi", "IN", Specialization.COMMISSIONING, "eng.delhi.comm@bess.com", "IN-DL-002", "Delhi Comm 1"),
    EngineerSeed("Mumbai", "IN", Specialization.DC_ELECTRICAL, "eng.mumbai.dc@bess.com", "IN-MH-001", "Mumbai DC 1"),
    EngineerSeed("Mumbai", "IN", Specialization.AC_ELECTRICAL, "eng.mumbai.ac@bess.com", "IN-MH-002", "Mumbai AC 1"),
    EngineerSeed("Dubai", "AE", Specialization.GENERAL, "eng.dubai.gen@bess.com", "AE-DU-001", "Dubai General 1"),
    EngineerSeed("Dubai", "AE", Specialization.COMMISSIONING, "eng.dubai.comm@bess.com", "AE-DU-002", "Dubai Comm 1"),
    EngineerSeed("Berlin", "DE", Specialization.CIVIL, "eng.berlin.civil@bess.com", "DE-BE-001", "Berlin Civil 1"),
    EngineerSeed("Berlin", "DE", Specialization.DC_ELECTRICAL, "eng.berlin.dc@bess.com", "DE-BE-002", "Berlin DC 1"),
]


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        async with atomic(db) as session:
            countries_map: dict[str, Country] = {}
            for name, code in [("India", "IN"), ("UAE", "AE"), ("Germany", "DE")]:
                country = await session.scalar(select(Country).where(Country.code == code))
                if country is None:
                    country = Country(name=name, code=code)
                    session.add(country)
                    await session.flush()
                countries_map[code] = country

            city_refs = [
                ("Delhi", "IN"),
                ("Mumbai", "IN"),
                ("Dubai", "AE"),
                ("Berlin", "DE"),
            ]
            cities_map: dict[str, City] = {}
            for city_name, country_code in city_refs:
                country_id = countries_map[country_code].id
                city = await session.scalar(select(City).where(City.name == city_name, City.country_id == country_id))
                if city is None:
                    city = City(name=city_name, country_id=country_id)
                    session.add(city)
                    await session.flush()
                cities_map[city_name] = city

            for city_name, _ in city_refs:
                city = cities_map[city_name]
                warehouse = await session.scalar(select(Warehouse).where(Warehouse.city_id == city.id))
                if warehouse is None:
                    session.add(
                        Warehouse(
                            name=f"{city_name} Central Warehouse",
                            city_id=city.id,
                            address=f"{city_name} Industrial Logistics Park",
                        )
                    )

            product = await session.scalar(
                select(ProductModel).where(ProductModel.model_number == "UNITYESS-125-261-OS")
            )
            if product is None:
                session.add(
                    ProductModel(
                        model_number="UNITYESS-125-261-OS",
                        capacity_kwh=261.0,
                        description="261 kWh liquid-cooled outdoor cabinet",
                    )
                )

            permission_ids: dict[str, int] = {}
            for permission_name in PERMISSIONS:
                permission = await session.scalar(select(Permission).where(Permission.name == permission_name))
                if permission is None:
                    permission = Permission(name=permission_name, description=permission_name)
                    session.add(permission)
                    await session.flush()
                permission_ids[permission_name] = permission.id

            role_ids: dict[str, int] = {}
            for role_name in ROLE_PERMISSIONS:
                role = await session.scalar(select(Role).where(Role.name == role_name))
                if role is None:
                    role = Role(name=role_name, description=role_name.replace("_", " "))
                    session.add(role)
                    await session.flush()
                role_ids[role_name] = role.id

            for role_name, permissions in ROLE_PERMISSIONS.items():
                role_id = role_ids[role_name]
                for permission_name in permissions:
                    permission_id = permission_ids[permission_name]
                    exists = await session.scalar(
                        select(RolePermission).where(
                            RolePermission.role_id == role_id,
                            RolePermission.permission_id == permission_id,
                        )
                    )
                    if exists is None:
                        session.add(RolePermission(role_id=role_id, permission_id=permission_id))

            for stage, items in CHECKLISTS.items():
                for order_idx, item in enumerate(items):
                    exists = await session.scalar(
                        select(ChecklistTemplate).where(
                            ChecklistTemplate.stage == stage,
                            ChecklistTemplate.item_text == str(item["item_text"]),
                        )
                    )
                    if exists is not None:
                        continue
                    session.add(
                        ChecklistTemplate(
                            stage=stage,
                            item_text=str(item["item_text"]),
                            description=None,
                            safety_warning=item.get("safety_warning"),
                            is_mandatory=bool(item.get("is_mandatory", True)),
                            requires_photo=bool(item.get("requires_photo", False)),
                            order_index=order_idx,
                        )
                    )

            admin = await session.scalar(select(User).where(User.email == settings.default_admin_email))
            if admin is None:
                admin = User(
                    email=settings.default_admin_email,
                    hashed_password=get_password_hash(settings.default_admin_password),
                    full_name="System Admin",
                    phone=None,
                    is_active=True,
                    is_verified=True,
                )
                session.add(admin)
                await session.flush()

            admin_role_exists = await session.scalar(
                select(UserRole).where(UserRole.user_id == admin.id, UserRole.role_id == role_ids["SUPER_ADMIN"])
            )
            if admin_role_exists is None:
                session.add(
                    UserRole(
                        user_id=admin.id,
                        role_id=role_ids["SUPER_ADMIN"],
                        assigned_by_user_id=admin.id,
                    )
                )

            for eng in ENGINEERS:
                user = await session.scalar(select(User).where(User.email == eng.email))
                if user is None:
                    user = User(
                        email=eng.email,
                        hashed_password=get_password_hash("Engineer@123"),
                        full_name=eng.full_name,
                        phone="9999999999",
                        is_active=True,
                        is_verified=True,
                    )
                    session.add(user)
                    await session.flush()

                site_role_exists = await session.scalar(
                    select(UserRole).where(
                        UserRole.user_id == user.id,
                        UserRole.role_id == role_ids["SITE_ENGINEER"],
                    )
                )
                if site_role_exists is None:
                    session.add(
                        UserRole(
                            user_id=user.id,
                            role_id=role_ids["SITE_ENGINEER"],
                            assigned_by_user_id=admin.id,
                        )
                    )

                city = cities_map[eng.city_name]
                country = countries_map[eng.country_code]
                engineer = await session.scalar(select(Engineer).where(Engineer.user_id == user.id))
                if engineer is None:
                    session.add(
                        Engineer(
                            user_id=user.id,
                            employee_code=eng.employee_code,
                            specialization=eng.specialization,
                            city_id=city.id,
                            country_id=country.id,
                            is_available=True,
                            max_concurrent_assignments=2,
                            certifications={"seeded": True},
                        )
                    )


if __name__ == "__main__":
    asyncio.run(seed())
    print("Seed completed")
