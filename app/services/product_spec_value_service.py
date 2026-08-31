from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.catalog import (
    ProductSpecValue,
    ProductSpecValueHistory,
    SpecConflictStatus,
    SpecValueHistoryAction,
    SpecValueKind,
    SpecValueSourceType,
    SpecVerificationStatus,
)
from app.repositories.product_spec_value_repository import ProductSpecValueRepository


SOURCE_PRIORITY = {
    SpecValueSourceType.ADMIN.value: 100,
    SpecValueSourceType.MANUFACTURER.value: 80,
    SpecValueSourceType.EXTERNAL.value: 60,
    SpecValueSourceType.STORE.value: 50,
    SpecValueSourceType.SCRAPER.value: 40,
    SpecValueSourceType.INGESTION.value: 40,
    SpecValueSourceType.AI.value: 20,
    SpecValueSourceType.AI_RESEARCH.value: 20,
    SpecValueSourceType.UNKNOWN.value: 10,
}


@dataclass(frozen=True)
class SpecValueInput:
    product_id: int
    definition_id: int
    value_kind: str = SpecValueKind.TEXT.value
    raw_value: str | None = None
    value_text: str | None = None
    value_number: int | float | Decimal | None = None
    value_boolean: bool | None = None
    value_json: dict | list | None = None
    unit: str | None = None
    normalized_value: dict | None = None
    source_type: str = SpecValueSourceType.UNKNOWN.value
    source_name: str | None = None
    source_url: str | None = None
    extraction_method: str | None = None
    confidence: float | Decimal | None = None
    verification_status: str = SpecVerificationStatus.AUTO.value
    changed_by: str | None = None
    note: str | None = None
    force_source_update: bool = False


class ProductSpecValueService:
    def __init__(self, db: Session, *, auto_commit: bool = True):
        self.db = db
        self.auto_commit = auto_commit
        self.repository = ProductSpecValueRepository(db)

    def upsert(self, payload: SpecValueInput) -> ProductSpecValue:
        existing = self.repository.get_by_product_definition(payload.product_id, payload.definition_id)
        if existing is None:
            value = ProductSpecValue(product_id=payload.product_id, definition_id=payload.definition_id)
            self._apply_payload(value, payload)
            self._apply_verified_metadata(value, payload)
            self.repository.add(value)
            self._record(value, SpecValueHistoryAction.CREATED.value, new_value=self._snapshot(value), payload=payload)
            self._commit_or_flush()
            return value

        incoming_snapshot = self._snapshot_payload(payload)
        current_snapshot = self._snapshot(existing)
        if self._same_value(current_snapshot, incoming_snapshot):
            if self._same_source(existing, payload) and existing.verification_status == payload.verification_status:
                return existing
            if payload.force_source_update or self._incoming_source_priority(payload) >= self._current_source_priority(existing) or payload.verification_status == SpecVerificationStatus.VERIFIED.value:
                self._apply_source(existing, payload)
                self._apply_verified_metadata(existing, payload)
                self._record(existing, SpecValueHistoryAction.SOURCE_UPDATED.value, previous_value=current_snapshot, new_value=self._snapshot(existing), payload=payload)
                self._commit_or_flush()
            return existing

        if self._should_protect_current(existing, payload):
            existing.conflict_status = SpecConflictStatus.PENDING.value
            self._record(
                existing,
                SpecValueHistoryAction.CONFLICT_DETECTED.value,
                previous_value=current_snapshot,
                incoming_value=incoming_snapshot,
                payload=payload,
                note=payload.note or "Incoming specification value did not replace the protected current value.",
            )
            self._commit_or_flush()
            return existing

        self._apply_payload(existing, payload)
        self._apply_verified_metadata(existing, payload)
        if payload.verification_status != SpecVerificationStatus.VERIFIED.value:
            existing.verification_status = SpecVerificationStatus.REVIEW.value
        existing.conflict_status = SpecConflictStatus.PENDING.value
        self._record(existing, SpecValueHistoryAction.VALUE_CHANGED.value, previous_value=current_snapshot, new_value=self._snapshot(existing), incoming_value=incoming_snapshot, payload=payload)
        self._commit_or_flush()
        return existing

    def verify(self, value: ProductSpecValue, *, verified_by: str, note: str | None = None, correction: SpecValueInput | None = None) -> ProductSpecValue:
        previous = self._snapshot(value)
        if correction is not None:
            self._apply_payload(value, correction)
        value.verification_status = SpecVerificationStatus.VERIFIED.value
        value.conflict_status = SpecConflictStatus.RESOLVED.value
        value.verified_by = verified_by
        value.verified_at = datetime.now(UTC)
        self._record(
            value,
            SpecValueHistoryAction.VERIFIED.value,
            previous_value=previous,
            new_value=self._snapshot(value),
            payload=correction,
            changed_by=verified_by,
            note=note,
        )
        self._commit_or_flush()
        return value

    def _commit_or_flush(self) -> None:
        if self.auto_commit:
            self.db.commit()
        else:
            self.db.flush()

    def _should_protect_current(self, existing: ProductSpecValue, payload: SpecValueInput) -> bool:
        if existing.verification_status == SpecVerificationStatus.VERIFIED.value and payload.source_type != SpecValueSourceType.ADMIN.value:
            return True
        return self._incoming_source_priority(payload) < self._current_source_priority(existing)

    def _apply_payload(self, value: ProductSpecValue, payload: SpecValueInput) -> None:
        value.value_kind = payload.value_kind
        value.raw_value = payload.raw_value
        value.value_text = payload.value_text
        value.value_number = payload.value_number
        value.value_boolean = payload.value_boolean
        value.value_json = payload.value_json
        value.unit = payload.unit
        value.normalized_value = payload.normalized_value or self._snapshot_payload(payload)["value"]
        value.confidence = payload.confidence
        self._apply_source(value, payload)

    def _apply_source(self, value: ProductSpecValue, payload: SpecValueInput) -> None:
        value.source_type = payload.source_type
        value.source_name = payload.source_name
        value.source_url = payload.source_url
        value.extraction_method = payload.extraction_method

    def _apply_verified_metadata(self, value: ProductSpecValue, payload: SpecValueInput) -> None:
        value.verification_status = payload.verification_status
        if payload.verification_status == SpecVerificationStatus.VERIFIED.value:
            value.conflict_status = SpecConflictStatus.RESOLVED.value
            value.verified_by = payload.changed_by
            value.verified_at = datetime.now(UTC)
        elif value.conflict_status != SpecConflictStatus.PENDING.value:
            value.conflict_status = SpecConflictStatus.NONE.value

    def _record(
        self,
        value: ProductSpecValue,
        action: str,
        *,
        previous_value: dict | None = None,
        new_value: dict | None = None,
        incoming_value: dict | None = None,
        payload: SpecValueInput | None,
        changed_by: str | None = None,
        note: str | None = None,
    ) -> None:
        self.repository.add_history(
            ProductSpecValueHistory(
                spec_value=value,
                product_id=value.product_id,
                definition_id=value.definition_id,
                action=action,
                previous_value=previous_value,
                new_value=new_value,
                incoming_value=incoming_value,
                source_type=payload.source_type if payload else value.source_type,
                source_name=payload.source_name if payload else value.source_name,
                source_url=payload.source_url if payload else value.source_url,
                extraction_method=payload.extraction_method if payload else value.extraction_method,
                verification_status=payload.verification_status if payload else value.verification_status,
                conflict_status=value.conflict_status,
                changed_by=changed_by or (payload.changed_by if payload else None),
                note=note or (payload.note if payload else None),
            )
        )

    def _snapshot(self, value: ProductSpecValue) -> dict:
        return {
            "value_kind": value.value_kind,
            "value": {
                "text": value.value_text,
                "number": self._json_number(value.value_number),
                "boolean": value.value_boolean,
                "json": value.value_json,
                "unit": value.unit,
            },
            "raw_value": value.raw_value,
        }

    def _snapshot_payload(self, payload: SpecValueInput) -> dict:
        return {
            "value_kind": payload.value_kind,
            "value": {
                "text": payload.value_text,
                "number": self._json_number(payload.value_number),
                "boolean": payload.value_boolean,
                "json": payload.value_json,
                "unit": payload.unit,
            },
            "raw_value": payload.raw_value,
        }

    def _same_value(self, current: dict, incoming: dict) -> bool:
        return json.dumps({"kind": current["value_kind"], "value": current["value"]}, sort_keys=True, ensure_ascii=True) == json.dumps({"kind": incoming["value_kind"], "value": incoming["value"]}, sort_keys=True, ensure_ascii=True)

    def _same_source(self, value: ProductSpecValue, payload: SpecValueInput) -> bool:
        return (
            value.source_type == payload.source_type
            and value.source_name == payload.source_name
            and value.source_url == payload.source_url
            and value.extraction_method == payload.extraction_method
        )

    def _current_source_priority(self, value: ProductSpecValue) -> int:
        if value.verification_status == SpecVerificationStatus.VERIFIED.value:
            return SOURCE_PRIORITY[SpecValueSourceType.ADMIN.value]
        return SOURCE_PRIORITY.get(value.source_type, SOURCE_PRIORITY[SpecValueSourceType.UNKNOWN.value])

    def _incoming_source_priority(self, payload: SpecValueInput) -> int:
        if payload.verification_status == SpecVerificationStatus.VERIFIED.value:
            return SOURCE_PRIORITY[SpecValueSourceType.ADMIN.value]
        return SOURCE_PRIORITY.get(payload.source_type, SOURCE_PRIORITY[SpecValueSourceType.UNKNOWN.value])

    def _json_number(self, value: Any) -> int | float | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return int(value) if value == value.to_integral_value() else float(value)
        return value
