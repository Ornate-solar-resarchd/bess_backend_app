from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Final

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.domains.auth.models import User
from app.domains.rbac.models import Permission, Role, RolePermission, UserRole
from app.shared.acid import atomic

PERMISSIONS: Final[list[str]] = [
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

ROLE_PERMISSIONS: Final[dict[str, list[str]]] = {
    "SUPER_ADMIN": PERMISSIONS,
    "FACTORY_ADMIN": ["bess:create", "bess:read", "shipment:manage", "master:write", "master:read"],
    "LOGISTICS_OPS": ["shipment:manage", "shipment:read", "bess:read", "bess:transition"],
    "SITE_ENGINEER": ["bess:read", "checklist:read", "checklist:write", "bess:transition", "engineer:read"],
    "QA_INSPECTOR": ["checklist:read", "bess:read", "report:view"],
    "CUSTOMER": ["bess:read", "report:view"],
}

PERMISSION_TO_ENDPOINTS: Final[dict[str, list[str]]] = {
    "bess:create": [
        "POST /api/v1/bess/",
        "PATCH /api/v1/bess/{bess_unit_id}",
    ],
    "bess:read": [
        "GET /api/v1/bess/",
        "GET /api/v1/bess/{bess_unit_id}",
        "GET /api/v1/bess/{bess_unit_id}/qrcode",
        "GET /api/v1/bess/{bess_unit_id}/history",
        "GET /api/v1/commissioning/{bess_unit_id}/records",
    ],
    "bess:transition": [
        "PATCH /api/v1/bess/{bess_unit_id}/transition",
        "POST /api/v1/commissioning/{bess_unit_id}/records",
    ],
    "checklist:read": [
        "GET /api/v1/bess/{bess_unit_id}/checklist/{stage}",
        "POST /api/v1/bess/{bess_unit_id}/checklist/{stage}/validate",
    ],
    "checklist:write": [
        "PATCH /api/v1/bess/{bess_unit_id}/checklist/{item_id}",
    ],
    "engineer:assign": [
        "POST /api/v1/bess/{bess_unit_id}/assign-engineer",
    ],
    "engineer:read": [
        "GET /api/v1/engineers/available",
        "GET /api/v1/engineers/my-assignments",
        "GET /api/v1/bess/{bess_unit_id}/assignments",
        "PATCH /api/v1/assignments/{assignment_id}/accept",
        "PATCH /api/v1/assignments/{assignment_id}/decline",
        "PATCH /api/v1/assignments/{assignment_id}/complete",
    ],
    "shipment:manage": [
        "POST /api/v1/shipments/",
        "POST /api/v1/shipments/{shipment_id}/units",
        "PATCH /api/v1/shipments/{shipment_id}/status",
    ],
    "shipment:read": [
        "GET /api/v1/shipments/",
    ],
    "master:write": [
        "POST /api/v1/master/countries",
        "POST /api/v1/master/cities",
        "POST /api/v1/master/warehouses",
        "POST /api/v1/master/product-models",
    ],
    "master:read": [
        "GET /api/v1/master/countries",
        "GET /api/v1/master/cities",
        "GET /api/v1/master/warehouses",
        "GET /api/v1/master/product-models",
    ],
    "report:view": [
        "GET /api/v1/reports/",
    ],
    "user:manage": [
        "POST /api/v1/engineers/",
    ],
    "role:manage": [
        # Kept for future if role-management is switched to permission guard.
    ],
}

ROLE_ONLY_ENDPOINTS: Final[dict[str, list[str]]] = {
    "SUPER_ADMIN": [
        "GET /api/v1/admin/roles",
        "POST /api/v1/admin/roles",
        "POST /api/v1/admin/users/{user_id}/roles",
        "DELETE /api/v1/admin/users/{user_id}/roles/{role_id}",
    ],
}

PUBLIC_ENDPOINTS: Final[list[str]] = [
    "POST /api/v1/auth/register",
    "POST /api/v1/auth/login",
    "POST /api/v1/auth/refresh",
    "GET /api/v1/bess/scan/{serial_number}",
]

FLOW_SEQUENCE: Final[list[tuple[str, str, str]]] = [
    ("1. User onboarding", "POST /api/v1/auth/register", "PUBLIC"),
    ("2. Login and token", "POST /api/v1/auth/login", "PUBLIC"),
    ("3. Seed/setup master data", "POST /api/v1/master/*", "master:write"),
    ("4. Factory register BESS", "POST /api/v1/bess/", "bess:create"),
    ("5. Create and update shipment", "POST/PATCH /api/v1/shipments/*", "shipment:manage"),
    ("6. Move lifecycle stage", "PATCH /api/v1/bess/{id}/transition", "bess:transition"),
    ("7. Complete checklist", "PATCH /api/v1/bess/{id}/checklist/{item_id}", "checklist:write"),
    ("8. Assign engineer", "POST /api/v1/bess/{id}/assign-engineer", "engineer:assign"),
    ("9. Engineer task updates", "PATCH /api/v1/assignments/{id}/*", "engineer:read"),
    ("10. View reports", "GET /api/v1/reports/", "report:view"),
]

# Default demo accounts by role (idempotent and safe to rerun).
ROLE_USERS: Final[dict[str, tuple[str, str]]] = {
    "SUPER_ADMIN": ("superadmin.demo@bess.com", "Super Admin Demo"),
    "FACTORY_ADMIN": ("factory.admin.demo@bess.com", "Factory Admin Demo"),
    "LOGISTICS_OPS": ("logistics.ops.demo@bess.com", "Logistics Ops Demo"),
    "SITE_ENGINEER": ("site.engineer.demo@bess.com", "Site Engineer Demo"),
    "QA_INSPECTOR": ("qa.inspector.demo@bess.com", "QA Inspector Demo"),
    "CUSTOMER": ("customer.role.demo@bess.com", "Customer Demo"),
}


def build_role_endpoint_map() -> dict[str, list[str]]:
    role_to_endpoints: dict[str, list[str]] = defaultdict(list)
    for role_name, perms in ROLE_PERMISSIONS.items():
        endpoint_set: set[str] = set()
        for perm in perms:
            endpoint_set.update(PERMISSION_TO_ENDPOINTS.get(perm, []))
        endpoint_set.update(ROLE_ONLY_ENDPOINTS.get(role_name, []))
        role_to_endpoints[role_name] = sorted(endpoint_set)
    return role_to_endpoints


async def seed_rbac_flow() -> None:
    async with AsyncSessionLocal() as db:
        async with atomic(db) as session:
            permission_ids: dict[str, int] = {}
            for name in PERMISSIONS:
                permission = await session.scalar(select(Permission).where(Permission.name == name))
                if permission is None:
                    permission = Permission(name=name, description=f"Permission for {name}")
                    session.add(permission)
                    await session.flush()
                permission_ids[name] = permission.id

            role_ids: dict[str, int] = {}
            for role_name in ROLE_PERMISSIONS:
                role = await session.scalar(select(Role).where(Role.name == role_name))
                if role is None:
                    role = Role(name=role_name, description=f"{role_name} role")
                    session.add(role)
                    await session.flush()
                role_ids[role_name] = role.id

            for role_name, perms in ROLE_PERMISSIONS.items():
                role_id = role_ids[role_name]
                for perm in perms:
                    perm_id = permission_ids[perm]
                    mapping = await session.scalar(
                        select(RolePermission).where(
                            RolePermission.role_id == role_id,
                            RolePermission.permission_id == perm_id,
                        )
                    )
                    if mapping is None:
                        session.add(RolePermission(role_id=role_id, permission_id=perm_id))

            default_password = get_password_hash("RoleDemo@123")
            for role_name, (email, full_name) in ROLE_USERS.items():
                user = await session.scalar(select(User).where(User.email == email))
                if user is None:
                    user = User(
                        email=email,
                        hashed_password=default_password,
                        full_name=full_name,
                        phone="9000000000",
                        is_active=True,
                        is_verified=True,
                    )
                    session.add(user)
                    await session.flush()

                user_role = await session.scalar(
                    select(UserRole).where(
                        UserRole.user_id == user.id,
                        UserRole.role_id == role_ids[role_name],
                    )
                )
                if user_role is None:
                    session.add(
                        UserRole(
                            user_id=user.id,
                            role_id=role_ids[role_name],
                            assigned_by_user_id=None,
                        )
                    )

    print("RBAC seed completed.")
    print("Demo role users password: RoleDemo@123\n")

    print("Public endpoints:")
    for endpoint in PUBLIC_ENDPOINTS:
        print(f"  - {endpoint}")

    print("\nFlow sequence (role/permission checkpoints):")
    for step, endpoint, guard in FLOW_SEQUENCE:
        print(f"  - {step}: {endpoint} [{guard}]")

    print("\nDemo users by role:")
    for role_name, (email, _) in ROLE_USERS.items():
        print(f"- {role_name}: {email}")

    print("\nRole -> Permissions:")
    for role_name, perms in ROLE_PERMISSIONS.items():
        print(f"\n{role_name}")
        for perm in perms:
            print(f"  - {perm}")

    role_to_endpoints = build_role_endpoint_map()
    print("\nRole -> API endpoints:")
    for role_name, endpoints in role_to_endpoints.items():
        print(f"\n{role_name}")
        for endpoint in endpoints:
            print(f"  - {endpoint}")

    used_permissions = {perm for perm, endpoints in PERMISSION_TO_ENDPOINTS.items() if endpoints}
    unused_permissions = sorted(set(PERMISSIONS) - used_permissions)
    if unused_permissions:
        print("\nPermissions currently not attached to permission-guarded routes:")
        for perm in unused_permissions:
            print(f"  - {perm}")
        print("  (Example: role management currently uses SUPER_ADMIN role guard.)")


if __name__ == "__main__":
    asyncio.run(seed_rbac_flow())
