from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.affiliate import AffiliateCommentPlacement, AffiliateCommentTemplate
from src.schemas.affiliate_comment_template import (
    ALLOWED_TEMPLATE_VARIABLES,
    AffiliateCommentTemplateCreateRequest,
    AffiliateCommentTemplateUpdateRequest,
)


VARIABLE_PATTERN = re.compile(r"{{\s*([a-z_][a-z0-9_]*)\s*}}", re.IGNORECASE)
UNRESOLVED_PATTERN = re.compile(r"{{[^{}]+}}")


class AffiliateCommentTemplateError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class AffiliateCommentTemplateService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, workspace_id: UUID, platform: str = "FACEBOOK_REELS") -> list[AffiliateCommentTemplate]:
        return list(
            self.db.scalars(
                select(AffiliateCommentTemplate)
                .where(
                    AffiliateCommentTemplate.workspace_id == workspace_id,
                    AffiliateCommentTemplate.platform == platform,
                )
                .order_by(AffiliateCommentTemplate.is_active.desc(), AffiliateCommentTemplate.created_at.desc())
            )
        )

    def get(self, workspace_id: UUID, template_id: UUID) -> AffiliateCommentTemplate:
        template = self.db.scalar(
            select(AffiliateCommentTemplate).where(
                AffiliateCommentTemplate.id == template_id,
                AffiliateCommentTemplate.workspace_id == workspace_id,
            )
        )
        if template is None:
            raise AffiliateCommentTemplateError("affiliate_comment_template_not_found", "Affiliate comment template was not found")
        return template

    def active(self, workspace_id: UUID, platform: str = "FACEBOOK_REELS") -> AffiliateCommentTemplate | None:
        return self.db.scalar(
            select(AffiliateCommentTemplate).where(
                AffiliateCommentTemplate.workspace_id == workspace_id,
                AffiliateCommentTemplate.platform == platform,
                AffiliateCommentTemplate.is_active.is_(True),
            )
        )

    def create(
        self,
        workspace_id: UUID,
        request: AffiliateCommentTemplateCreateRequest,
        operator_subject: str,
    ) -> AffiliateCommentTemplate:
        self.validate_template(request.message_template)
        version = int(
            self.db.scalar(
                select(func.max(AffiliateCommentTemplate.version)).where(
                    AffiliateCommentTemplate.workspace_id == workspace_id,
                    AffiliateCommentTemplate.platform == request.platform,
                    AffiliateCommentTemplate.name == request.name,
                )
            )
            or 0
        ) + 1
        template = AffiliateCommentTemplate(
            workspace_id=workspace_id,
            platform=request.platform,
            name=request.name,
            message_template=request.message_template,
            default_cta=request.default_cta,
            default_disclosure=request.default_disclosure,
            attach_product_image=request.attach_product_image,
            version=version,
            is_active=False,
            metadata_json={"created_by": operator_subject[:180]},
        )
        self.db.add(template)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AffiliateCommentTemplateError("affiliate_comment_template_exists", "This template version already exists") from exc
        self.db.refresh(template)
        return template

    def revise(
        self,
        workspace_id: UUID,
        template_id: UUID,
        request: AffiliateCommentTemplateUpdateRequest,
        operator_subject: str,
    ) -> AffiliateCommentTemplate:
        current = self.get(workspace_id, template_id)
        payload = request.model_dump(exclude_unset=True)
        message_template = str(payload.get("message_template", current.message_template))
        self.validate_template(message_template)
        replacement = AffiliateCommentTemplateCreateRequest(
            platform=current.platform,
            name=str(payload.get("name", current.name)),
            message_template=message_template,
            default_cta=str(payload.get("default_cta", current.default_cta)),
            default_disclosure=str(payload.get("default_disclosure", current.default_disclosure)),
            attach_product_image=bool(payload.get("attach_product_image", current.attach_product_image)),
        )
        revised = self.create(workspace_id, replacement, operator_subject)
        revised.metadata_json = {
            **(revised.metadata_json or {}),
            "revises_template_id": str(current.id),
            "revises_version": current.version,
        }
        self.db.commit()
        self.db.refresh(revised)
        return revised

    def activate(self, workspace_id: UUID, template_id: UUID) -> AffiliateCommentTemplate:
        template = self.get(workspace_id, template_id)
        self.db.execute(
            update(AffiliateCommentTemplate)
            .where(
                AffiliateCommentTemplate.workspace_id == workspace_id,
                AffiliateCommentTemplate.platform == template.platform,
            )
            .values(is_active=False)
        )
        template.is_active = True
        self.db.commit()
        self.db.refresh(template)
        return template

    def delete(self, workspace_id: UUID, template_id: UUID) -> None:
        template = self.get(workspace_id, template_id)
        if template.is_active:
            raise AffiliateCommentTemplateError(
                "affiliate_comment_template_active",
                "Activate another template before deleting the active template",
            )
        referenced = self.db.scalar(
            select(AffiliateCommentPlacement.id)
            .where(AffiliateCommentPlacement.template_id == template.id)
            .limit(1)
        )
        if referenced is not None:
            raise AffiliateCommentTemplateError(
                "affiliate_comment_template_in_use",
                "This template is referenced by a comment placement and is kept for audit",
            )
        self.db.delete(template)
        self.db.commit()

    @staticmethod
    def validate_template(message_template: str) -> None:
        AffiliateCommentTemplateService.validate_custom_template(message_template)
        variables = {value.lower() for value in VARIABLE_PATTERN.findall(message_template)}
        # Disclosure is intentionally optional: operators may choose a fully
        # neutral comment format. Affiliate URL remains mandatory because it
        # is the product's conversion target and must never be omitted.
        missing = ["affiliate_url"] if "affiliate_url" not in variables else []
        if missing:
            raise AffiliateCommentTemplateError(
                "affiliate_comment_template_variable_required",
                f"Template must include: {', '.join('{{' + value + '}}' for value in missing)}",
            )

    @staticmethod
    def validate_custom_template(message_template: str) -> None:
        variables = {value.lower() for value in VARIABLE_PATTERN.findall(message_template)}
        unknown = sorted(variables - ALLOWED_TEMPLATE_VARIABLES)
        if unknown:
            raise AffiliateCommentTemplateError(
                "affiliate_comment_template_variable_invalid",
                f"Unsupported template variables: {', '.join(unknown)}",
            )

    @staticmethod
    def render(message_template: str, variables: dict[str, str]) -> str:
        def replace(match: re.Match[str]) -> str:
            return str(variables.get(match.group(1).lower(), "")).strip()

        rendered = VARIABLE_PATTERN.sub(replace, message_template)
        if UNRESOLVED_PATTERN.search(rendered):
            raise AffiliateCommentTemplateError(
                "affiliate_comment_template_unresolved",
                "Template contains unresolved variables",
            )
        lines = [line.rstrip() for line in rendered.splitlines()]
        compact: list[str] = []
        previous_blank = False
        for line in lines:
            blank = not line.strip()
            if blank and previous_blank:
                continue
            compact.append(line)
            previous_blank = blank
        return "\n".join(compact).strip()
