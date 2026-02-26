from __future__ import annotations

from fastapi import FastAPI, Request
from sqlalchemy import func, select
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend

from app.core.database import AsyncSessionLocal, async_engine
from app.core.security import get_password_hash, verify_password
from app.domains.auth.models import User
from app.domains.bess_unit.models import AuditLog, BESSUnit, StageCertificate, StageHistory
from app.domains.commissioning.models import CommissioningRecord
from app.domains.engineer.models import Engineer, SiteAssignment
from app.domains.installation.models import ChecklistResponse, ChecklistTemplate
from app.domains.master.models import City, Country, ProductModel, Site, Warehouse
from app.domains.rbac.models import Permission, Role, RolePermission, UserRole
from app.domains.shipment.models import Shipment, ShipmentDocument, ShipmentItem


class AdminAuthBackend(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        email = str(form.get("username", "")).strip().lower()
        password = str(form.get("password", ""))
        if not email or not password:
            return False

        async with AsyncSessionLocal() as session:
            user = await session.scalar(
                select(User).where(func.lower(User.email) == email, User.is_active.is_(True))
            )
            if user is None or not verify_password(password, user.hashed_password):
                return False

            super_admin_count = await session.scalar(
                select(func.count(UserRole.user_id))
                .select_from(UserRole)
                .join(Role, Role.id == UserRole.role_id)
                .where(UserRole.user_id == user.id, Role.name == "SUPER_ADMIN")
            )
            if int(super_admin_count or 0) < 1:
                return False

        request.session.update({"admin_user_id": str(user.id), "admin_user_email": user.email})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("admin_user_id"))


class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.email, User.full_name, User.phone, User.is_active, User.is_verified, User.created_at]
    column_searchable_list = [User.email, User.full_name]
    column_sortable_list = [User.id, User.created_at]
    form_columns = [User.email, User.hashed_password, User.full_name, User.phone, User.is_active, User.is_verified]

    async def on_model_change(self, data: dict, model: User, is_created: bool, request: Request) -> None:
        _ = (model, is_created, request)
        password_value = data.get("hashed_password")
        if password_value and not str(password_value).startswith("$2"):
            data["hashed_password"] = get_password_hash(str(password_value))


class RoleAdmin(ModelView, model=Role):
    column_list = [Role.id, Role.name, Role.description, Role.created_at]
    column_searchable_list = [Role.name]


class PermissionAdmin(ModelView, model=Permission):
    column_list = [Permission.id, Permission.name, Permission.description, Permission.created_at]
    column_searchable_list = [Permission.name]


class UserRoleAdmin(ModelView, model=UserRole):
    column_list = [UserRole.user_id, UserRole.role_id, UserRole.assigned_at, UserRole.assigned_by_user_id]


class RolePermissionAdmin(ModelView, model=RolePermission):
    column_list = [RolePermission.role_id, RolePermission.permission_id]


class CountryAdmin(ModelView, model=Country):
    column_list = [Country.id, Country.name, Country.code, Country.created_at]
    column_searchable_list = [Country.name, Country.code]


class CityAdmin(ModelView, model=City):
    column_list = [City.id, City.name, City.country_id, City.created_at]
    column_searchable_list = [City.name]


class WarehouseAdmin(ModelView, model=Warehouse):
    column_list = [Warehouse.id, Warehouse.name, Warehouse.city_id, Warehouse.address, Warehouse.created_at]
    column_searchable_list = [Warehouse.name]


class SiteAdmin(ModelView, model=Site):
    column_list = [Site.id, Site.name, Site.country_id, Site.city_id, Site.address, Site.created_at]
    column_searchable_list = [Site.name, Site.address]


class ProductModelAdmin(ModelView, model=ProductModel):
    column_list = [ProductModel.id, ProductModel.model_number, ProductModel.capacity_kwh, ProductModel.created_at]
    column_searchable_list = [ProductModel.model_number]


class BESSUnitAdmin(ModelView, model=BESSUnit):
    column_list = [
        BESSUnit.id,
        BESSUnit.serial_number,
        BESSUnit.current_stage,
        BESSUnit.product_model_id,
        BESSUnit.country_id,
        BESSUnit.city_id,
        BESSUnit.warehouse_id,
        BESSUnit.is_active,
        BESSUnit.created_at,
    ]
    column_searchable_list = [BESSUnit.serial_number]


class StageHistoryAdmin(ModelView, model=StageHistory):
    column_list = [
        StageHistory.id,
        StageHistory.bess_unit_id,
        StageHistory.from_stage,
        StageHistory.to_stage,
        StageHistory.changed_by_user_id,
        StageHistory.changed_at,
    ]


class StageCertificateAdmin(ModelView, model=StageCertificate):
    column_list = [
        StageCertificate.id,
        StageCertificate.bess_unit_id,
        StageCertificate.stage,
        StageCertificate.certificate_name,
        StageCertificate.uploaded_at,
    ]


class AuditLogAdmin(ModelView, model=AuditLog):
    can_create = False
    can_edit = False
    column_list = [AuditLog.id, AuditLog.user_id, AuditLog.action, AuditLog.entity_type, AuditLog.entity_id, AuditLog.created_at]
    column_searchable_list = [AuditLog.action, AuditLog.entity_type]


class ShipmentAdmin(ModelView, model=Shipment):
    column_list = [
        Shipment.id,
        Shipment.shipment_code,
        Shipment.origin_country_id,
        Shipment.destination_country_id,
        Shipment.created_date,
        Shipment.expected_arrival_date,
        Shipment.expected_quantity,
        Shipment.status,
        Shipment.created_at,
    ]
    column_searchable_list = [Shipment.shipment_code]


class ShipmentItemAdmin(ModelView, model=ShipmentItem):
    column_list = [ShipmentItem.id, ShipmentItem.shipment_id, ShipmentItem.bess_unit_id, ShipmentItem.order_id, ShipmentItem.created_at]
    column_searchable_list = [ShipmentItem.order_id]


class ShipmentDocumentAdmin(ModelView, model=ShipmentDocument):
    column_list = [
        ShipmentDocument.id,
        ShipmentDocument.shipment_id,
        ShipmentDocument.document_name,
        ShipmentDocument.document_type,
        ShipmentDocument.document_url,
        ShipmentDocument.uploaded_at,
    ]
    column_searchable_list = [ShipmentDocument.document_name, ShipmentDocument.document_type]


class ChecklistTemplateAdmin(ModelView, model=ChecklistTemplate):
    column_list = [
        ChecklistTemplate.id,
        ChecklistTemplate.stage,
        ChecklistTemplate.item_text,
        ChecklistTemplate.is_mandatory,
        ChecklistTemplate.requires_photo,
        ChecklistTemplate.order_index,
    ]
    column_searchable_list = [ChecklistTemplate.item_text]


class ChecklistResponseAdmin(ModelView, model=ChecklistResponse):
    column_list = [
        ChecklistResponse.id,
        ChecklistResponse.bess_unit_id,
        ChecklistResponse.checklist_template_id,
        ChecklistResponse.stage,
        ChecklistResponse.is_checked,
        ChecklistResponse.checked_by_user_id,
        ChecklistResponse.checked_at,
    ]


class EngineerAdmin(ModelView, model=Engineer):
    column_list = [
        Engineer.id,
        Engineer.user_id,
        Engineer.employee_code,
        Engineer.specialization,
        Engineer.city_id,
        Engineer.country_id,
        Engineer.is_available,
        Engineer.max_concurrent_assignments,
    ]
    column_searchable_list = [Engineer.employee_code]


class SiteAssignmentAdmin(ModelView, model=SiteAssignment):
    column_list = [
        SiteAssignment.id,
        SiteAssignment.bess_unit_id,
        SiteAssignment.engineer_id,
        SiteAssignment.assigned_stage,
        SiteAssignment.status,
        SiteAssignment.assigned_by,
        SiteAssignment.created_at,
    ]


class CommissioningRecordAdmin(ModelView, model=CommissioningRecord):
    column_list = [
        CommissioningRecord.id,
        CommissioningRecord.bess_unit_id,
        CommissioningRecord.stage,
        CommissioningRecord.status,
        CommissioningRecord.notes,
        CommissioningRecord.recorded_by_user_id,
        CommissioningRecord.created_at,
    ]


def setup_admin(app: FastAPI, secret_key: str) -> None:
    admin = Admin(
        app=app,
        engine=async_engine,
        base_url="/admin",
        authentication_backend=AdminAuthBackend(secret_key=secret_key),
        title="BESS Admin",
    )
    admin.add_view(UserAdmin)
    admin.add_view(RoleAdmin)
    admin.add_view(PermissionAdmin)
    admin.add_view(UserRoleAdmin)
    admin.add_view(RolePermissionAdmin)
    admin.add_view(CountryAdmin)
    admin.add_view(CityAdmin)
    admin.add_view(WarehouseAdmin)
    admin.add_view(SiteAdmin)
    admin.add_view(ProductModelAdmin)
    admin.add_view(BESSUnitAdmin)
    admin.add_view(StageHistoryAdmin)
    admin.add_view(StageCertificateAdmin)
    admin.add_view(AuditLogAdmin)
    admin.add_view(ShipmentAdmin)
    admin.add_view(ShipmentItemAdmin)
    admin.add_view(ShipmentDocumentAdmin)
    admin.add_view(ChecklistTemplateAdmin)
    admin.add_view(ChecklistResponseAdmin)
    admin.add_view(EngineerAdmin)
    admin.add_view(SiteAssignmentAdmin)
    admin.add_view(CommissioningRecordAdmin)
