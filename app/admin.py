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


# ─── Users & Access Control ───────────────────────────────────────────────────

class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-users"
    category = "Access Control"

    column_list = [User.id, User.email, User.full_name, User.phone, User.is_active, User.is_verified, User.created_at]
    column_searchable_list = [User.email, User.full_name, User.phone]
    column_sortable_list = [User.id, User.email, User.full_name, User.is_active, User.created_at]
    column_default_sort = [(User.created_at, True)]
    column_labels = {
        User.id: "ID",
        User.email: "Email",
        User.full_name: "Full Name",
        User.phone: "Phone",
        User.is_active: "Active",
        User.is_verified: "Verified",
        User.created_at: "Registered At",
    }
    form_columns = [User.email, User.hashed_password, User.full_name, User.phone, User.is_active, User.is_verified]
    page_size = 20
    page_size_options = [20, 50, 100]

    async def on_model_change(self, data: dict, model: User, is_created: bool, request: Request) -> None:
        _ = (model, is_created, request)
        password_value = data.get("hashed_password")
        if password_value and not str(password_value).startswith("$2"):
            data["hashed_password"] = get_password_hash(str(password_value))


class RoleAdmin(ModelView, model=Role):
    name = "Role"
    name_plural = "Roles"
    icon = "fa-solid fa-shield-halved"
    category = "Access Control"

    column_list = [Role.id, Role.name, Role.description, Role.created_at]
    column_searchable_list = [Role.name]
    column_sortable_list = [Role.id, Role.name, Role.created_at]
    column_labels = {
        Role.id: "ID",
        Role.name: "Role Name",
        Role.description: "Description",
        Role.created_at: "Created At",
    }
    page_size = 20


class PermissionAdmin(ModelView, model=Permission):
    name = "Permission"
    name_plural = "Permissions"
    icon = "fa-solid fa-key"
    category = "Access Control"

    column_list = [Permission.id, Permission.name, Permission.description, Permission.created_at]
    column_searchable_list = [Permission.name]
    column_sortable_list = [Permission.id, Permission.name]
    column_labels = {
        Permission.id: "ID",
        Permission.name: "Permission Key",
        Permission.description: "Description",
        Permission.created_at: "Created At",
    }
    page_size = 20


class UserRoleAdmin(ModelView, model=UserRole):
    name = "User Role"
    name_plural = "User Roles"
    icon = "fa-solid fa-user-tag"
    category = "Access Control"

    column_list = [UserRole.user_id, UserRole.role_id, UserRole.assigned_at, UserRole.assigned_by_user_id]
    column_sortable_list = [UserRole.assigned_at]
    column_default_sort = [(UserRole.assigned_at, True)]
    column_labels = {
        UserRole.user_id: "User ID",
        UserRole.role_id: "Role ID",
        UserRole.assigned_at: "Assigned At",
        UserRole.assigned_by_user_id: "Assigned By",
    }
    page_size = 20


class RolePermissionAdmin(ModelView, model=RolePermission):
    name = "Role Permission"
    name_plural = "Role Permissions"
    icon = "fa-solid fa-lock"
    category = "Access Control"

    column_list = [RolePermission.role_id, RolePermission.permission_id]
    column_labels = {
        RolePermission.role_id: "Role ID",
        RolePermission.permission_id: "Permission ID",
    }
    page_size = 20


# ─── Master Data ──────────────────────────────────────────────────────────────

class CountryAdmin(ModelView, model=Country):
    name = "Country"
    name_plural = "Countries"
    icon = "fa-solid fa-globe"
    category = "Master Data"

    column_list = [Country.id, Country.name, Country.code, Country.created_at]
    column_searchable_list = [Country.name, Country.code]
    column_sortable_list = [Country.id, Country.name, Country.code]
    column_labels = {
        Country.id: "ID",
        Country.name: "Country Name",
        Country.code: "ISO Code",
        Country.created_at: "Created At",
    }
    page_size = 20


class CityAdmin(ModelView, model=City):
    name = "City"
    name_plural = "Cities"
    icon = "fa-solid fa-city"
    category = "Master Data"

    column_list = [City.id, City.name, City.country_id, City.created_at]
    column_searchable_list = [City.name]
    column_sortable_list = [City.id, City.name, City.created_at]
    column_labels = {
        City.id: "ID",
        City.name: "City Name",
        City.country_id: "Country ID",
        City.created_at: "Created At",
    }
    page_size = 20


class WarehouseAdmin(ModelView, model=Warehouse):
    name = "Warehouse"
    name_plural = "Warehouses"
    icon = "fa-solid fa-warehouse"
    category = "Master Data"

    column_list = [Warehouse.id, Warehouse.name, Warehouse.city_id, Warehouse.address, Warehouse.created_at]
    column_searchable_list = [Warehouse.name, Warehouse.address]
    column_sortable_list = [Warehouse.id, Warehouse.name, Warehouse.created_at]
    column_labels = {
        Warehouse.id: "ID",
        Warehouse.name: "Warehouse Name",
        Warehouse.city_id: "City ID",
        Warehouse.address: "Address",
        Warehouse.created_at: "Created At",
    }
    page_size = 20


class SiteAdmin(ModelView, model=Site):
    name = "Site"
    name_plural = "Sites"
    icon = "fa-solid fa-location-dot"
    category = "Master Data"

    column_list = [Site.id, Site.name, Site.country_id, Site.city_id, Site.address, Site.latitude, Site.longitude, Site.created_at]
    column_searchable_list = [Site.name, Site.address]
    column_sortable_list = [Site.id, Site.name, Site.created_at]
    column_labels = {
        Site.id: "ID",
        Site.name: "Site Name",
        Site.country_id: "Country ID",
        Site.city_id: "City ID",
        Site.address: "Address",
        Site.latitude: "Latitude",
        Site.longitude: "Longitude",
        Site.created_at: "Created At",
    }
    page_size = 20


class ProductModelAdmin(ModelView, model=ProductModel):
    name = "Product Model"
    name_plural = "Product Models"
    icon = "fa-solid fa-box"
    category = "Master Data"

    column_list = [ProductModel.id, ProductModel.model_number, ProductModel.capacity_kwh, ProductModel.description, ProductModel.created_at]
    column_searchable_list = [ProductModel.model_number]
    column_sortable_list = [ProductModel.id, ProductModel.model_number, ProductModel.capacity_kwh]
    column_labels = {
        ProductModel.id: "ID",
        ProductModel.model_number: "Model Number",
        ProductModel.capacity_kwh: "Capacity (kWh)",
        ProductModel.description: "Description",
        ProductModel.created_at: "Created At",
    }
    page_size = 20


# ─── BESS Units ───────────────────────────────────────────────────────────────

class BESSUnitAdmin(ModelView, model=BESSUnit):
    name = "BESS Unit"
    name_plural = "BESS Units"
    icon = "fa-solid fa-battery-full"
    category = "BESS"

    column_list = [
        BESSUnit.id,
        BESSUnit.serial_number,
        BESSUnit.current_stage,
        BESSUnit.product_model_id,
        BESSUnit.country_id,
        BESSUnit.city_id,
        BESSUnit.warehouse_id,
        BESSUnit.site_address,
        BESSUnit.is_active,
        BESSUnit.is_deleted,
        BESSUnit.created_at,
    ]
    column_searchable_list = [BESSUnit.serial_number, BESSUnit.site_address]
    column_sortable_list = [BESSUnit.id, BESSUnit.serial_number, BESSUnit.current_stage, BESSUnit.is_active, BESSUnit.created_at]
    column_default_sort = [(BESSUnit.created_at, True)]
    column_labels = {
        BESSUnit.id: "ID",
        BESSUnit.serial_number: "Serial Number",
        BESSUnit.current_stage: "Current Stage",
        BESSUnit.product_model_id: "Product Model",
        BESSUnit.country_id: "Country",
        BESSUnit.city_id: "City",
        BESSUnit.warehouse_id: "Warehouse",
        BESSUnit.site_address: "Site Address",
        BESSUnit.is_active: "Active",
        BESSUnit.is_deleted: "Deleted",
        BESSUnit.created_at: "Registered At",
    }
    page_size = 20
    page_size_options = [20, 50, 100]


class StageHistoryAdmin(ModelView, model=StageHistory):
    name = "Stage History"
    name_plural = "Stage History"
    icon = "fa-solid fa-timeline"
    category = "BESS"

    can_create = False
    can_edit = False
    can_delete = False

    column_list = [
        StageHistory.id,
        StageHistory.bess_unit_id,
        StageHistory.from_stage,
        StageHistory.to_stage,
        StageHistory.changed_by_user_id,
        StageHistory.notes,
        StageHistory.changed_at,
    ]
    column_sortable_list = [StageHistory.id, StageHistory.bess_unit_id, StageHistory.changed_at]
    column_default_sort = [(StageHistory.changed_at, True)]
    column_labels = {
        StageHistory.id: "ID",
        StageHistory.bess_unit_id: "BESS Unit ID",
        StageHistory.from_stage: "From Stage",
        StageHistory.to_stage: "To Stage",
        StageHistory.changed_by_user_id: "Changed By",
        StageHistory.notes: "Notes",
        StageHistory.changed_at: "Changed At",
    }
    page_size = 30


class StageCertificateAdmin(ModelView, model=StageCertificate):
    name = "Stage Certificate"
    name_plural = "Stage Certificates"
    icon = "fa-solid fa-certificate"
    category = "BESS"

    column_list = [
        StageCertificate.id,
        StageCertificate.bess_unit_id,
        StageCertificate.stage,
        StageCertificate.certificate_name,
        StageCertificate.certificate_url,
        StageCertificate.notes,
        StageCertificate.uploaded_by_user_id,
        StageCertificate.uploaded_at,
    ]
    column_searchable_list = [StageCertificate.certificate_name]
    column_sortable_list = [StageCertificate.id, StageCertificate.bess_unit_id, StageCertificate.stage, StageCertificate.uploaded_at]
    column_default_sort = [(StageCertificate.uploaded_at, True)]
    column_labels = {
        StageCertificate.id: "ID",
        StageCertificate.bess_unit_id: "BESS Unit ID",
        StageCertificate.stage: "Stage",
        StageCertificate.certificate_name: "Certificate Name",
        StageCertificate.certificate_url: "Document URL",
        StageCertificate.notes: "Notes",
        StageCertificate.uploaded_by_user_id: "Uploaded By",
        StageCertificate.uploaded_at: "Uploaded At",
    }
    page_size = 20


class AuditLogAdmin(ModelView, model=AuditLog):
    name = "Audit Log"
    name_plural = "Audit Logs"
    icon = "fa-solid fa-clock-rotate-left"
    category = "BESS"

    can_create = False
    can_edit = False
    can_delete = False

    column_list = [
        AuditLog.id,
        AuditLog.user_id,
        AuditLog.action,
        AuditLog.entity_type,
        AuditLog.entity_id,
        AuditLog.created_at,
    ]
    column_searchable_list = [AuditLog.action, AuditLog.entity_type]
    column_sortable_list = [AuditLog.id, AuditLog.action, AuditLog.entity_type, AuditLog.created_at]
    column_default_sort = [(AuditLog.created_at, True)]
    column_labels = {
        AuditLog.id: "ID",
        AuditLog.user_id: "User ID",
        AuditLog.action: "Action",
        AuditLog.entity_type: "Entity Type",
        AuditLog.entity_id: "Entity ID",
        AuditLog.created_at: "Timestamp",
    }
    page_size = 30
    page_size_options = [30, 50, 100]


# ─── Shipments ────────────────────────────────────────────────────────────────

class ShipmentAdmin(ModelView, model=Shipment):
    name = "Shipment"
    name_plural = "Shipments"
    icon = "fa-solid fa-ship"
    category = "Shipments"

    column_list = [
        Shipment.id,
        Shipment.shipment_code,
        Shipment.status,
        Shipment.origin_country_id,
        Shipment.destination_country_id,
        Shipment.warehouse_id,
        Shipment.site_id,
        Shipment.expected_quantity,
        Shipment.created_date,
        Shipment.expected_arrival_date,
        Shipment.created_at,
    ]
    column_searchable_list = [Shipment.shipment_code]
    column_sortable_list = [Shipment.id, Shipment.shipment_code, Shipment.status, Shipment.created_date, Shipment.created_at]
    column_default_sort = [(Shipment.created_at, True)]
    column_labels = {
        Shipment.id: "ID",
        Shipment.shipment_code: "Shipment Code",
        Shipment.status: "Status",
        Shipment.origin_country_id: "Origin Country",
        Shipment.destination_country_id: "Destination Country",
        Shipment.warehouse_id: "Warehouse",
        Shipment.site_id: "Site",
        Shipment.expected_quantity: "Expected Qty",
        Shipment.created_date: "Shipment Date",
        Shipment.expected_arrival_date: "Expected Arrival",
        Shipment.created_at: "Created At",
    }
    page_size = 20


class ShipmentItemAdmin(ModelView, model=ShipmentItem):
    name = "Shipment Item"
    name_plural = "Shipment Items"
    icon = "fa-solid fa-list-check"
    category = "Shipments"

    column_list = [ShipmentItem.id, ShipmentItem.shipment_id, ShipmentItem.bess_unit_id, ShipmentItem.order_id, ShipmentItem.created_at]
    column_searchable_list = [ShipmentItem.order_id]
    column_sortable_list = [ShipmentItem.id, ShipmentItem.shipment_id, ShipmentItem.created_at]
    column_default_sort = [(ShipmentItem.created_at, True)]
    column_labels = {
        ShipmentItem.id: "ID",
        ShipmentItem.shipment_id: "Shipment ID",
        ShipmentItem.bess_unit_id: "BESS Unit ID",
        ShipmentItem.order_id: "Order ID",
        ShipmentItem.created_at: "Added At",
    }
    page_size = 20


class ShipmentDocumentAdmin(ModelView, model=ShipmentDocument):
    name = "Shipment Document"
    name_plural = "Shipment Documents"
    icon = "fa-solid fa-file-invoice"
    category = "Shipments"

    column_list = [
        ShipmentDocument.id,
        ShipmentDocument.shipment_id,
        ShipmentDocument.document_name,
        ShipmentDocument.document_type,
        ShipmentDocument.document_url,
        ShipmentDocument.uploaded_at,
    ]
    column_searchable_list = [ShipmentDocument.document_name, ShipmentDocument.document_type]
    column_sortable_list = [ShipmentDocument.id, ShipmentDocument.shipment_id, ShipmentDocument.document_type, ShipmentDocument.uploaded_at]
    column_default_sort = [(ShipmentDocument.uploaded_at, True)]
    column_labels = {
        ShipmentDocument.id: "ID",
        ShipmentDocument.shipment_id: "Shipment ID",
        ShipmentDocument.document_name: "Document Name",
        ShipmentDocument.document_type: "Type",
        ShipmentDocument.document_url: "URL",
        ShipmentDocument.uploaded_at: "Uploaded At",
    }
    page_size = 20


# ─── Checklists ───────────────────────────────────────────────────────────────

class ChecklistTemplateAdmin(ModelView, model=ChecklistTemplate):
    name = "Checklist Template"
    name_plural = "Checklist Templates"
    icon = "fa-solid fa-clipboard-list"
    category = "Checklists"

    column_list = [
        ChecklistTemplate.id,
        ChecklistTemplate.stage,
        ChecklistTemplate.item_text,
        ChecklistTemplate.is_mandatory,
        ChecklistTemplate.requires_photo,
        ChecklistTemplate.order_index,
    ]
    column_searchable_list = [ChecklistTemplate.item_text]
    column_sortable_list = [ChecklistTemplate.id, ChecklistTemplate.stage, ChecklistTemplate.order_index, ChecklistTemplate.is_mandatory]
    column_default_sort = [(ChecklistTemplate.stage, False), (ChecklistTemplate.order_index, False)]
    column_labels = {
        ChecklistTemplate.id: "ID",
        ChecklistTemplate.stage: "Stage",
        ChecklistTemplate.item_text: "Item Text",
        ChecklistTemplate.is_mandatory: "Mandatory",
        ChecklistTemplate.requires_photo: "Photo Required",
        ChecklistTemplate.order_index: "Order",
    }
    page_size = 30
    page_size_options = [30, 50, 100]


class ChecklistResponseAdmin(ModelView, model=ChecklistResponse):
    name = "Checklist Response"
    name_plural = "Checklist Responses"
    icon = "fa-solid fa-clipboard-check"
    category = "Checklists"

    can_create = False

    column_list = [
        ChecklistResponse.id,
        ChecklistResponse.bess_unit_id,
        ChecklistResponse.checklist_template_id,
        ChecklistResponse.stage,
        ChecklistResponse.is_checked,
        ChecklistResponse.checked_by_user_id,
        ChecklistResponse.checked_at,
        ChecklistResponse.notes,
    ]
    column_sortable_list = [
        ChecklistResponse.id,
        ChecklistResponse.bess_unit_id,
        ChecklistResponse.stage,
        ChecklistResponse.is_checked,
        ChecklistResponse.checked_at,
    ]
    column_default_sort = [(ChecklistResponse.checked_at, True)]
    column_labels = {
        ChecklistResponse.id: "ID",
        ChecklistResponse.bess_unit_id: "BESS Unit ID",
        ChecklistResponse.checklist_template_id: "Template ID",
        ChecklistResponse.stage: "Stage",
        ChecklistResponse.is_checked: "Checked",
        ChecklistResponse.checked_by_user_id: "Checked By",
        ChecklistResponse.checked_at: "Checked At",
        ChecklistResponse.notes: "Notes",
    }
    page_size = 30


# ─── Engineers ────────────────────────────────────────────────────────────────

class EngineerAdmin(ModelView, model=Engineer):
    name = "Engineer"
    name_plural = "Engineers"
    icon = "fa-solid fa-helmet-safety"
    category = "Engineers"

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
    column_sortable_list = [Engineer.id, Engineer.employee_code, Engineer.specialization, Engineer.is_available]
    column_labels = {
        Engineer.id: "ID",
        Engineer.user_id: "User ID",
        Engineer.employee_code: "Employee Code",
        Engineer.specialization: "Specialization",
        Engineer.city_id: "City",
        Engineer.country_id: "Country",
        Engineer.is_available: "Available",
        Engineer.max_concurrent_assignments: "Max Jobs",
    }
    page_size = 20


class SiteAssignmentAdmin(ModelView, model=SiteAssignment):
    name = "Site Assignment"
    name_plural = "Site Assignments"
    icon = "fa-solid fa-user-gear"
    category = "Engineers"

    column_list = [
        SiteAssignment.id,
        SiteAssignment.bess_unit_id,
        SiteAssignment.engineer_id,
        SiteAssignment.assigned_stage,
        SiteAssignment.status,
        SiteAssignment.assigned_by,
        SiteAssignment.notes,
        SiteAssignment.created_at,
    ]
    column_sortable_list = [SiteAssignment.id, SiteAssignment.bess_unit_id, SiteAssignment.assigned_stage, SiteAssignment.status, SiteAssignment.created_at]
    column_default_sort = [(SiteAssignment.created_at, True)]
    column_labels = {
        SiteAssignment.id: "ID",
        SiteAssignment.bess_unit_id: "BESS Unit ID",
        SiteAssignment.engineer_id: "Engineer ID",
        SiteAssignment.assigned_stage: "Stage",
        SiteAssignment.status: "Status",
        SiteAssignment.assigned_by: "Assigned By",
        SiteAssignment.notes: "Notes",
        SiteAssignment.created_at: "Assigned At",
    }
    page_size = 20


# ─── Commissioning ────────────────────────────────────────────────────────────

class CommissioningRecordAdmin(ModelView, model=CommissioningRecord):
    name = "Commissioning Record"
    name_plural = "Commissioning Records"
    icon = "fa-solid fa-bolt"
    category = "Commissioning"

    column_list = [
        CommissioningRecord.id,
        CommissioningRecord.bess_unit_id,
        CommissioningRecord.stage,
        CommissioningRecord.status,
        CommissioningRecord.notes,
        CommissioningRecord.recorded_by_user_id,
        CommissioningRecord.created_at,
    ]
    column_sortable_list = [CommissioningRecord.id, CommissioningRecord.bess_unit_id, CommissioningRecord.stage, CommissioningRecord.status, CommissioningRecord.created_at]
    column_default_sort = [(CommissioningRecord.created_at, True)]
    column_labels = {
        CommissioningRecord.id: "ID",
        CommissioningRecord.bess_unit_id: "BESS Unit ID",
        CommissioningRecord.stage: "Stage",
        CommissioningRecord.status: "Status",
        CommissioningRecord.notes: "Notes",
        CommissioningRecord.recorded_by_user_id: "Recorded By",
        CommissioningRecord.created_at: "Recorded At",
    }
    page_size = 20


# ─── Setup ────────────────────────────────────────────────────────────────────

def setup_admin(app: FastAPI, secret_key: str) -> None:
    admin = Admin(
        app=app,
        engine=async_engine,
        base_url="/admin",
        authentication_backend=AdminAuthBackend(secret_key=secret_key),
        title="BESS Lifecycle Admin",
    )

    # Access Control
    admin.add_view(UserAdmin)
    admin.add_view(RoleAdmin)
    admin.add_view(PermissionAdmin)
    admin.add_view(UserRoleAdmin)
    admin.add_view(RolePermissionAdmin)

    # Master Data
    admin.add_view(CountryAdmin)
    admin.add_view(CityAdmin)
    admin.add_view(WarehouseAdmin)
    admin.add_view(SiteAdmin)
    admin.add_view(ProductModelAdmin)

    # BESS
    admin.add_view(BESSUnitAdmin)
    admin.add_view(StageHistoryAdmin)
    admin.add_view(StageCertificateAdmin)
    admin.add_view(AuditLogAdmin)

    # Shipments
    admin.add_view(ShipmentAdmin)
    admin.add_view(ShipmentItemAdmin)
    admin.add_view(ShipmentDocumentAdmin)

    # Checklists
    admin.add_view(ChecklistTemplateAdmin)
    admin.add_view(ChecklistResponseAdmin)

    # Engineers
    admin.add_view(EngineerAdmin)
    admin.add_view(SiteAssignmentAdmin)

    # Commissioning
    admin.add_view(CommissioningRecordAdmin)
