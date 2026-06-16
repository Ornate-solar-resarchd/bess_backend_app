from __future__ import annotations

from fastapi import FastAPI, Request
from sqlalchemy import func, select
from sqladmin import Admin, BaseView, ModelView, expose
from sqladmin.authentication import AuthenticationBackend
from starlette.responses import HTMLResponse
from wtforms import validators as wtf_validators

from app.core.database import AsyncSessionLocal, async_engine
from app.core.security import get_password_hash, verify_password
from app.domains.auth.models import User
from app.domains.bess_unit.models import AuditLog, BESSUnit, StageCertificate, StageHistory
from app.domains.commissioning.models import CommissioningRecord
from app.domains.engineer.models import Engineer, SiteAssignment
from app.domains.installation.models import ChecklistResponse, ChecklistTemplate
from app.domains.master.models import City, Country, ProductModel, Site, State, Warehouse
from app.domains.rbac.models import Permission, Role, RolePermission, UserRole
from app.domains.shipment.models import Shipment, ShipmentDocument, ShipmentItem
from app.shared.enums import BESSStage


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
    form_args = {
        "hashed_password": {
            "label": "Password (type a new one to change it; leave blank to keep current)",
            # Optional so a blank edit keeps the current password (handled in on_model_change).
            "validators": [wtf_validators.Optional()],
        }
    }
    column_export_list = [User.id, User.email, User.full_name, User.phone, User.is_active, User.is_verified, User.created_at]
    page_size = 25
    page_size_options = [25, 50, 100]

    async def on_model_change(self, data: dict, model: User, is_created: bool, request: Request) -> None:
        _ = (model, request)
        password_value = data.get("hashed_password")
        if password_value and not str(password_value).startswith("$2"):
            data["hashed_password"] = get_password_hash(str(password_value))
        elif not password_value:
            if is_created:
                raise ValueError("Password is required for a new user")
            # Field cleared on edit: keep the existing hash instead of wiping it.
            data.pop("hashed_password", None)


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
    form_columns = [Role.name, Role.description]
    page_size = 25


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
    form_columns = [Permission.name, Permission.description]
    page_size = 25


class UserRoleAdmin(ModelView, model=UserRole):
    name = "User Role"
    name_plural = "User Roles"
    icon = "fa-solid fa-user-tag"
    category = "Access Control"

    column_list = ["user", "role", UserRole.assigned_at, UserRole.assigned_by_user_id]
    column_sortable_list = [UserRole.assigned_at]
    column_default_sort = [(UserRole.assigned_at, True)]
    column_labels = {
        "user": "User",
        "role": "Role",
        UserRole.assigned_at: "Assigned At",
        UserRole.assigned_by_user_id: "Assigned By",
    }
    form_columns = ["user", "role"]
    page_size = 25


class RolePermissionAdmin(ModelView, model=RolePermission):
    name = "Role Permission"
    name_plural = "Role Permissions"
    icon = "fa-solid fa-lock"
    category = "Access Control"

    column_list = ["role", "permission"]
    column_labels = {
        "role": "Role",
        "permission": "Permission",
    }
    form_columns = ["role", "permission"]
    page_size = 50
    page_size_options = [25, 50, 100]


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
    form_columns = [Country.name, Country.code]
    page_size = 25


class StateAdmin(ModelView, model=State):
    name = "State"
    name_plural = "States"
    icon = "fa-solid fa-map"
    category = "Master Data"

    column_list = [State.id, State.name, "country", State.created_at]
    column_searchable_list = [State.name]
    column_sortable_list = [State.id, State.name, State.created_at]
    column_labels = {
        State.id: "ID",
        State.name: "State Name",
        "country": "Country",
        State.created_at: "Created At",
    }
    form_columns = [State.name, "country"]
    page_size = 50
    page_size_options = [25, 50, 100]


class CityAdmin(ModelView, model=City):
    name = "City"
    name_plural = "Cities"
    icon = "fa-solid fa-city"
    category = "Master Data"

    column_list = [City.id, City.name, "country", "state", City.created_at]
    column_searchable_list = [City.name]
    column_sortable_list = [City.id, City.name, City.created_at]
    column_labels = {
        City.id: "ID",
        City.name: "City Name",
        "country": "Country",
        "state": "State",
        City.created_at: "Created At",
    }
    form_columns = [City.name, "country", "state"]
    page_size = 50
    page_size_options = [25, 50, 100]


class WarehouseAdmin(ModelView, model=Warehouse):
    name = "Warehouse"
    name_plural = "Warehouses"
    icon = "fa-solid fa-warehouse"
    category = "Master Data"

    column_list = [Warehouse.id, Warehouse.name, "city", Warehouse.address, Warehouse.created_at]
    column_searchable_list = [Warehouse.name, Warehouse.address]
    column_sortable_list = [Warehouse.id, Warehouse.name, Warehouse.created_at]
    column_labels = {
        Warehouse.id: "ID",
        Warehouse.name: "Warehouse Name",
        "city": "City",
        Warehouse.address: "Address",
        Warehouse.created_at: "Created At",
    }
    form_columns = [Warehouse.name, "city", Warehouse.address]
    page_size = 25


class SiteAdmin(ModelView, model=Site):
    name = "Site"
    name_plural = "Sites"
    icon = "fa-solid fa-location-dot"
    category = "Master Data"

    column_list = [Site.id, Site.name, "country", "city", Site.address, Site.latitude, Site.longitude, Site.created_at]
    column_searchable_list = [Site.name, Site.address]
    column_sortable_list = [Site.id, Site.name, Site.created_at]
    column_labels = {
        Site.id: "ID",
        Site.name: "Site Name",
        "country": "Country",
        "city": "City",
        Site.address: "Address",
        Site.latitude: "Lat",
        Site.longitude: "Lng",
        Site.created_at: "Created At",
    }
    form_columns = [Site.name, "country", "city", Site.address, Site.latitude, Site.longitude]
    page_size = 25


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
    form_columns = [ProductModel.model_number, ProductModel.capacity_kwh, ProductModel.description]
    page_size = 25


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
        "product_model",
        "country",
        "state",
        "city",
        "warehouse",
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
        BESSUnit.current_stage: "Stage",
        "product_model": "Product Model",
        "country": "Country",
        "state": "State",
        "city": "City",
        "warehouse": "Warehouse",
        "customer_user": "Customer",
        "installed_by_user": "Installed By",
        BESSUnit.site_address: "Site Address",
        BESSUnit.is_active: "Active",
        BESSUnit.is_deleted: "Deleted",
        BESSUnit.created_at: "Registered At",
    }
    column_export_list = [
        BESSUnit.id, BESSUnit.serial_number, BESSUnit.current_stage,
        BESSUnit.site_address, BESSUnit.is_active, BESSUnit.created_at,
    ]
    form_columns = [
        BESSUnit.serial_number,
        "product_model",
        BESSUnit.current_stage,
        "country",
        "state",
        "city",
        "warehouse",
        "customer_user",
        "installed_by_user",
        BESSUnit.qr_code_url,
        BESSUnit.nameplate_photo_url,
        BESSUnit.site_address,
        BESSUnit.site_latitude,
        BESSUnit.site_longitude,
        BESSUnit.manufactured_date,
        BESSUnit.is_active,
        BESSUnit.is_deleted,
    ]
    page_size = 25
    page_size_options = [25, 50, 100]


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
        StageHistory.bess_unit_id: "BESS Unit",
        StageHistory.from_stage: "From",
        StageHistory.to_stage: "To",
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
        StageCertificate.bess_unit_id: "BESS Unit",
        StageCertificate.stage: "Stage",
        StageCertificate.certificate_name: "Certificate",
        StageCertificate.certificate_url: "URL",
        StageCertificate.notes: "Notes",
        StageCertificate.uploaded_by_user_id: "Uploaded By",
        StageCertificate.uploaded_at: "Uploaded At",
    }
    form_columns = [
        "bess_unit",
        StageCertificate.stage,
        StageCertificate.certificate_name,
        StageCertificate.certificate_url,
        StageCertificate.notes,
    ]
    page_size = 25


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
        AuditLog.entity_type: "Entity",
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
        "origin_country",
        "destination_country",
        "warehouse",
        "site",
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
        Shipment.shipment_code: "Code",
        Shipment.status: "Status",
        "origin_country": "Origin",
        "destination_country": "Destination",
        "warehouse": "Warehouse",
        "site": "Site",
        Shipment.expected_quantity: "Qty",
        Shipment.created_date: "Shipment Date",
        Shipment.expected_arrival_date: "ETA",
        Shipment.created_at: "Created At",
    }
    column_export_list = [
        Shipment.id, Shipment.shipment_code, Shipment.status,
        Shipment.expected_quantity, Shipment.created_date, Shipment.expected_arrival_date,
    ]
    form_columns = [
        Shipment.shipment_code,
        Shipment.status,
        "origin_country",
        "destination_country",
        "warehouse",
        "site",
        Shipment.expected_quantity,
        Shipment.created_date,
        Shipment.expected_arrival_date,
    ]
    page_size = 25


class ShipmentItemAdmin(ModelView, model=ShipmentItem):
    name = "Shipment Item"
    name_plural = "Shipment Items"
    icon = "fa-solid fa-list-check"
    category = "Shipments"

    column_list = [ShipmentItem.id, "shipment", "bess_unit", ShipmentItem.order_id, ShipmentItem.created_at]
    column_searchable_list = [ShipmentItem.order_id]
    column_sortable_list = [ShipmentItem.id, ShipmentItem.shipment_id, ShipmentItem.created_at]
    column_default_sort = [(ShipmentItem.created_at, True)]
    column_labels = {
        ShipmentItem.id: "ID",
        "shipment": "Shipment",
        "bess_unit": "BESS Unit",
        ShipmentItem.order_id: "Order ID",
        ShipmentItem.created_at: "Added At",
    }
    form_columns = ["shipment", "bess_unit", ShipmentItem.order_id]
    page_size = 25


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
        ShipmentDocument.shipment_id: "Shipment",
        ShipmentDocument.document_name: "Document",
        ShipmentDocument.document_type: "Type",
        ShipmentDocument.document_url: "URL",
        ShipmentDocument.uploaded_at: "Uploaded At",
    }
    form_columns = [
        "shipment",
        ShipmentDocument.document_name,
        ShipmentDocument.document_type,
        ShipmentDocument.document_url,
        ShipmentDocument.notes,
    ]
    page_size = 25


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
        ChecklistTemplate.item_text: "Item",
        ChecklistTemplate.is_mandatory: "Mandatory",
        ChecklistTemplate.requires_photo: "Photo Required",
        ChecklistTemplate.order_index: "Order",
    }
    form_columns = [
        ChecklistTemplate.stage,
        ChecklistTemplate.item_text,
        ChecklistTemplate.description,
        ChecklistTemplate.safety_warning,
        ChecklistTemplate.is_mandatory,
        ChecklistTemplate.requires_photo,
        ChecklistTemplate.order_index,
    ]
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
        ChecklistResponse.bess_unit_id: "BESS Unit",
        ChecklistResponse.checklist_template_id: "Template",
        ChecklistResponse.stage: "Stage",
        ChecklistResponse.is_checked: "Checked",
        ChecklistResponse.checked_by_user_id: "Checked By",
        ChecklistResponse.checked_at: "Checked At",
        ChecklistResponse.notes: "Notes",
    }
    # Responses come from engineers in the field; admin may only correct these.
    form_columns = [ChecklistResponse.is_checked, ChecklistResponse.notes, ChecklistResponse.photo_url]
    page_size = 30


# ─── Engineers ────────────────────────────────────────────────────────────────

class EngineerAdmin(ModelView, model=Engineer):
    name = "Engineer"
    name_plural = "Engineers"
    icon = "fa-solid fa-helmet-safety"
    category = "Engineers"

    column_list = [
        Engineer.id,
        "user",
        Engineer.employee_code,
        Engineer.specialization,
        "city",
        Engineer.is_available,
        Engineer.max_concurrent_assignments,
    ]
    column_searchable_list = [Engineer.employee_code]
    column_sortable_list = [Engineer.id, Engineer.employee_code, Engineer.specialization, Engineer.is_available]
    column_labels = {
        Engineer.id: "ID",
        "user": "User",
        Engineer.employee_code: "Employee Code",
        Engineer.specialization: "Specialization",
        "city": "City",
        Engineer.is_available: "Available",
        Engineer.max_concurrent_assignments: "Max Jobs",
    }
    form_columns = [
        "user",
        Engineer.employee_code,
        Engineer.specialization,
        "country",
        "city",
        Engineer.is_available,
        Engineer.max_concurrent_assignments,
        Engineer.certifications,
    ]
    page_size = 25


class SiteAssignmentAdmin(ModelView, model=SiteAssignment):
    name = "Site Assignment"
    name_plural = "Site Assignments"
    icon = "fa-solid fa-user-gear"
    category = "Engineers"

    column_list = [
        SiteAssignment.id,
        "bess_unit",
        "engineer",
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
        "bess_unit": "BESS Unit",
        "engineer": "Engineer",
        SiteAssignment.assigned_stage: "Stage",
        SiteAssignment.status: "Status",
        SiteAssignment.assigned_by: "Assigned By",
        SiteAssignment.notes: "Notes",
        SiteAssignment.created_at: "Assigned At",
    }
    form_columns = [
        "bess_unit",
        "engineer",
        SiteAssignment.assigned_stage,
        SiteAssignment.status,
        SiteAssignment.assigned_by,
        SiteAssignment.accepted_at,
        SiteAssignment.completed_at,
        SiteAssignment.notes,
    ]
    page_size = 25


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
        CommissioningRecord.bess_unit_id: "BESS Unit",
        CommissioningRecord.stage: "Stage",
        CommissioningRecord.status: "Status",
        CommissioningRecord.notes: "Notes",
        CommissioningRecord.recorded_by_user_id: "Recorded By",
        CommissioningRecord.created_at: "Recorded At",
    }
    form_columns = [
        "bess_unit",
        "recorded_by_user",
        CommissioningRecord.stage,
        CommissioningRecord.status,
        CommissioningRecord.notes,
    ]
    page_size = 25


# ─── Bulk Assign Units ────────────────────────────────────────────────────────

class BulkAssignUnitsView(BaseView):
    name = "Assign Units to Shipment"
    icon = "fa-solid fa-boxes-stacked"
    category = "Shipments"

    @expose("/bulk-assign-units", methods=["GET", "POST"])
    async def bulk_assign_page(self, request: Request) -> HTMLResponse:
        message: str | None = None
        errors: list[str] = []
        selected_shipment_id: str | None = None

        async with AsyncSessionLocal() as session:
            assigned_subq = select(ShipmentItem.bess_unit_id)
            shipments = (
                await session.execute(select(Shipment).order_by(Shipment.created_at.desc()))
            ).scalars().all()
            units = (
                await session.execute(
                    select(BESSUnit)
                    .where(BESSUnit.is_deleted == False)  # noqa: E712
                    .where(~BESSUnit.id.in_(assigned_subq))
                    .order_by(BESSUnit.serial_number)
                )
            ).scalars().all()

            if request.method == "POST":
                form = await request.form()
                selected_shipment_id = form.get("shipment_id")
                unit_ids = form.getlist("unit_ids")
                order_id_raw = form.get("order_id", "")
                order_id = order_id_raw.strip() if order_id_raw else None

                if not selected_shipment_id:
                    errors.append("Please select a shipment.")
                elif not unit_ids:
                    errors.append("Please select at least one BESS unit.")
                else:
                    shipment_id_int = int(selected_shipment_id)
                    assigned_count = 0
                    skip_count = 0

                    for uid_str in unit_ids:
                        uid = int(uid_str)
                        existing = await session.scalar(
                            select(ShipmentItem).where(ShipmentItem.bess_unit_id == uid)
                        )
                        if existing:
                            skip_count += 1
                            continue
                        session.add(ShipmentItem(
                            shipment_id=shipment_id_int,
                            bess_unit_id=uid,
                            order_id=order_id,
                        ))
                        unit_obj = await session.get(BESSUnit, uid)
                        if unit_obj and not unit_obj.is_deleted:
                            unit_obj.current_stage = BESSStage.SHIPMENT_ASSIGNED
                        assigned_count += 1

                    await session.commit()

                    if assigned_count:
                        message = f"Assigned {assigned_count} BESS unit(s) to shipment."
                        if skip_count:
                            message += f" {skip_count} already assigned unit(s) were skipped."
                    else:
                        errors.append("No units were assigned. They may already be linked to other shipments.")

                    # Reload available units after assignment
                    units = (
                        await session.execute(
                            select(BESSUnit)
                            .where(BESSUnit.is_deleted == False)  # noqa: E712
                            .where(~BESSUnit.id.in_(select(ShipmentItem.bess_unit_id)))
                            .order_by(BESSUnit.serial_number)
                        )
                    ).scalars().all()

        return HTMLResponse(_render_bulk_assign_html(
            shipments=shipments,
            units=units,
            message=message,
            errors=errors,
            selected_shipment_id=selected_shipment_id,
        ))


def _render_bulk_assign_html(
    shipments: list,
    units: list,
    message: str | None,
    errors: list[str],
    selected_shipment_id: str | None,
) -> str:
    shipment_options = "\n".join(
        f'<option value="{s.id}" {"selected" if str(s.id) == selected_shipment_id else ""}>'
        f'{s.shipment_code} — {s.status.value} ({s.expected_quantity} units expected)'
        f'</option>'
        for s in shipments
    )
    unit_rows = "\n".join(
        f"""<label class="unit-row" style="display:flex;align-items:center;gap:10px;padding:8px 12px;
            border:1px solid #dee2e6;border-radius:6px;cursor:pointer;margin-bottom:6px;
            background:#fff;transition:background .15s;">
          <input type="checkbox" name="unit_ids" value="{u.id}"
            style="width:16px;height:16px;accent-color:#0d6efd;">
          <span style="font-family:monospace;font-size:13px;font-weight:600;">{u.serial_number}</span>
          <span style="color:#6c757d;font-size:12px;">ID #{u.id} · Stage: {u.current_stage.value}</span>
        </label>"""
        for u in units
    )
    alert_html = ""
    if message:
        alert_html = f'<div style="background:#d1e7dd;color:#0a3622;border:1px solid #a3cfbb;border-radius:6px;padding:12px 16px;margin-bottom:16px;">{message}</div>'
    if errors:
        err_items = "".join(f"<li>{e}</li>" for e in errors)
        alert_html += f'<div style="background:#f8d7da;color:#58151c;border:1px solid #f1aeb5;border-radius:6px;padding:12px 16px;margin-bottom:16px;"><ul style="margin:0;padding-left:18px;">{err_items}</ul></div>'

    no_units_msg = "" if units else '<p style="color:#6c757d;font-style:italic;">All available BESS units have already been assigned to shipments.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Assign Units to Shipment · UnityESS Admin</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
  <style>
    body {{ background:#f4f6fb; }}
    .page-card {{ background:#fff; border-radius:10px; box-shadow:0 2px 12px rgba(0,0,0,.08); padding:32px; max-width:860px; margin:40px auto; }}
    .unit-row:hover {{ background:#f0f4ff !important; }}
    #select-all-btn {{ cursor:pointer; }}
    .search-box {{ margin-bottom:12px; }}
  </style>
</head>
<body>
<div class="page-card">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:24px;">
    <a href="/admin" style="color:#6c757d;font-size:13px;text-decoration:none;">
      <i class="fa-solid fa-arrow-left"></i> Back to Admin
    </a>
  </div>
  <h4 style="font-weight:700;margin-bottom:4px;"><i class="fa-solid fa-boxes-stacked" style="color:#0d6efd;margin-right:8px;"></i>Assign Units to Shipment</h4>
  <p style="color:#6c757d;font-size:13px;margin-bottom:24px;">
    Select a shipment and one or more BESS units to assign in a single operation.
    Only unassigned units are shown below.
  </p>

  {alert_html}

  <form method="POST" action="/admin/bulk-assign-units">
    <div class="mb-4">
      <label class="form-label fw-semibold">Shipment</label>
      <select name="shipment_id" class="form-select" required>
        <option value="">— Select a shipment —</option>
        {shipment_options}
      </select>
    </div>

    <div class="mb-3">
      <label class="form-label fw-semibold">Order ID <span style="font-weight:400;color:#6c757d;">(optional — applies to all selected units)</span></label>
      <input type="text" name="order_id" class="form-control" placeholder="e.g. ORD-2025-001">
    </div>

    <div class="mb-4">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
        <label class="form-label fw-semibold mb-0">
          BESS Units <span style="color:#6c757d;font-weight:400;">({len(units)} available)</span>
        </label>
        <button type="button" id="select-all-btn" class="btn btn-sm btn-outline-secondary" onclick="toggleAll(this)">
          Select All
        </button>
      </div>
      <input type="text" id="unit-search" class="form-control search-box" placeholder="Search serial number…" oninput="filterUnits(this.value)">
      <div id="units-container" style="max-height:380px;overflow-y:auto;padding:2px;">
        {unit_rows}
        {no_units_msg}
      </div>
    </div>

    <div style="display:flex;gap:12px;">
      <button type="submit" class="btn btn-primary px-4" {"disabled" if not units else ""}>
        <i class="fa-solid fa-link me-2"></i>Assign Selected Units
      </button>
      <a href="/admin/shipmentitem/list" class="btn btn-outline-secondary">View All Shipment Items</a>
    </div>
  </form>
</div>

<script>
function toggleAll(btn) {{
  const boxes = document.querySelectorAll('input[name="unit_ids"]:not([style*="display:none"])');
  const allChecked = Array.from(boxes).every(b => b.checked);
  boxes.forEach(b => b.checked = !allChecked);
  btn.textContent = allChecked ? 'Select All' : 'Deselect All';
}}

function filterUnits(query) {{
  const q = query.toLowerCase();
  document.querySelectorAll('.unit-row').forEach(row => {{
    row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""


# ─── Setup ────────────────────────────────────────────────────────────────────

def setup_admin(app: FastAPI, secret_key: str) -> None:
    admin = Admin(
        app=app,
        engine=async_engine,
        base_url="/admin",
        authentication_backend=AdminAuthBackend(secret_key=secret_key),
        title="UnityESS Admin",
    )

    # Access Control
    admin.add_view(UserAdmin)
    admin.add_view(RoleAdmin)
    admin.add_view(PermissionAdmin)
    admin.add_view(UserRoleAdmin)
    admin.add_view(RolePermissionAdmin)

    # Master Data
    admin.add_view(CountryAdmin)
    admin.add_view(StateAdmin)
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
    admin.add_base_view(BulkAssignUnitsView)

    # Checklists
    admin.add_view(ChecklistTemplateAdmin)
    admin.add_view(ChecklistResponseAdmin)

    # Engineers
    admin.add_view(EngineerAdmin)
    admin.add_view(SiteAssignmentAdmin)

    # Commissioning
    admin.add_view(CommissioningRecordAdmin)
