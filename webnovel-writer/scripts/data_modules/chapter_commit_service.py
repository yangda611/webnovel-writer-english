#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from chapter_outline_loader import volume_num_for_chapter_from_state

from .chapter_commit_schema import (
    DisambiguationResult,
    ExtractionResult,
    FulfillmentResult,
    ReviewResult,
)
from .commit_artifacts import extraction_list
from .config import DataModulesConfig
from .event_log_store import EventLogStore
from .event_projection_router import EventProjectionRouter
from .story_contracts import write_json
from .index_manager import IndexManager
from .text_metrics import chapter_measurement
from .profile_contracts import contract_profile_errors, profile_meta
from .story_runtime_sources import load_runtime_sources
from .writing_profile import load_writing_profile
from .override_ledger_service import (
    AmendProposalTrigger,
    ensure_override_ledger_columns,
    persist_amend_proposals,
)


class ChapterCommitService:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def build_commit(
        self,
        chapter: int,
        review_result: Dict[str, Any],
        fulfillment_result: Dict[str, Any],
        disambiguation_result: Dict[str, Any],
        extraction_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        review = ReviewResult.model_validate(review_result)
        fulfillment = FulfillmentResult.model_validate(fulfillment_result)
        disambiguation = DisambiguationResult.model_validate(disambiguation_result)
        extraction = ExtractionResult.model_validate(extraction_result)
        rejected = bool(review.blocking_count) or bool(
            fulfillment.missed_nodes
        ) or bool(disambiguation.pending)
        status = "rejected" if rejected else "accepted"
        acceptance_meta = self._validate_acceptance(chapter) if status == "accepted" else {}
        volume = volume_num_for_chapter_from_state(self.project_root, chapter) or 1
        accepted_events = EventLogStore(self.project_root).normalize_events(
            chapter, extraction.accepted_events
        )
        extraction_payload = extraction.model_dump()
        extraction_payload["accepted_events"] = accepted_events
        if status == "accepted":
            chapter_meta = extraction_payload.get("chapter_meta")
            if not isinstance(chapter_meta, dict):
                chapter_meta = {}
            chapter_meta.update(chapter_measurement(self.project_root, chapter,
                incoming_count=self._safe_count(chapter_meta.get("word_count"))))
            extraction_payload["chapter_meta"] = chapter_meta
        return {
            "meta": {
                "schema_version": "story-system/v1",
                "chapter": chapter,
                "status": status,
                **acceptance_meta,
            },
            "contract_refs": {
                "master": "MASTER_SETTING.json",
                "volume": f"volume_{volume:03d}.json",
                "chapter": f"chapter_{chapter:03d}.json",
                "review": f"chapter_{chapter:03d}.review.json",
            },
            "provenance": {
                "write_fact_role": "chapter_commit",
                "projection_role": "derived_read_models",
                "legacy_state_role": "projection_only",
            },
            "outline_snapshot": {
                "planned_nodes": fulfillment.planned_nodes,
                "covered_nodes": fulfillment.covered_nodes,
                "missed_nodes": fulfillment.missed_nodes,
                "extra_nodes": fulfillment.extra_nodes,
            },
            "review_result": review.model_dump(),
            "fulfillment_result": fulfillment.model_dump(),
            "disambiguation_result": disambiguation.model_dump(),
            "extraction_result": extraction_payload,
            "projection_status": {
                "state": "pending",
                "index": "pending",
                "summary": "pending",
                "memory": "pending",
                "vector": "pending",
            },
        }

    def _validate_acceptance(self, chapter: int, payload: dict | None = None) -> dict:
        """Bind accepted facts to all current contracts before any event write."""
        if payload is not None:
            # A queued commit's own explicit provenance remains a configuration
            # marker even if its project's state and contracts were removed.
            load_writing_profile(self.project_root, state=payload)
        snapshot = load_runtime_sources(self.project_root, chapter)
        errors = contract_profile_errors(self.project_root, snapshot.contracts, require_all=True)
        if payload is not None:
            errors.extend(contract_profile_errors(self.project_root, {"commit": payload}, require_all=True))
        if errors:
            raise ValueError("; ".join(errors))
        return profile_meta(load_writing_profile(self.project_root))

    @staticmethod
    def _safe_count(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def persist_commit(self, payload: Dict[str, Any]) -> Path:
        target = self.project_root / ".story-system" / "commits"
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"chapter_{int(payload['meta']['chapter']):03d}.commit.json"
        write_json(path, payload)
        return path

    def _projection_writers(self) -> dict[str, Any]:
        from .index_projection_writer import IndexProjectionWriter
        from .memory_projection_writer import MemoryProjectionWriter
        from .state_projection_writer import StateProjectionWriter
        from .summary_projection_writer import SummaryProjectionWriter
        from .vector_projection_writer import VectorProjectionWriter

        return {
            "state": StateProjectionWriter(self.project_root),
            "index": IndexProjectionWriter(self.project_root),
            "summary": SummaryProjectionWriter(self.project_root),
            "memory": MemoryProjectionWriter(self.project_root),
            "vector": VectorProjectionWriter(self.project_root),
        }

    def _writer_status(self, result: dict[str, Any]) -> str:
        if result.get("applied"):
            return "done"
        reason = str(result.get("reason") or "").strip()
        if reason in {"not_required", "commit_rejected"}:
            return "skipped"
        if reason.startswith("error:"):
            return f"failed:{reason[6:] or 'writer_error'}"
        return "skipped"

    def apply_projection_writers(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        status = str((payload.get("meta") or {}).get("status") or "")
        if status not in {"accepted", "rejected"}:
            return payload
        if status == "accepted":
            self._validate_acceptance(int((payload.get("meta") or {}).get("chapter") or 0), payload)

        payload.setdefault("projection_status", {})
        if not isinstance(payload["projection_status"], dict):
            payload["projection_status"] = {}

        writers = self._projection_writers()
        required_writers = set(EventProjectionRouter().required_writers(payload))
        writer_results: dict[str, dict[str, Any]] = {}
        for name, writer in writers.items():
            if name not in required_writers:
                payload["projection_status"][name] = "skipped"
                writer_results[name] = {"status": "skipped", "reason": "not_required"}
                continue
            try:
                result = writer.apply(payload)
                payload["projection_status"][name] = self._writer_status(result)
                writer_results[name] = {
                    "status": payload["projection_status"][name],
                    "result": result,
                }
            except Exception as exc:
                payload["projection_status"][name] = f"failed:{exc}"
                writer_results[name] = {"status": "failed", "error": str(exc)}
        commit_path = self.persist_commit(payload)
        try:
            from .projection_log import append_projection_run

            append_projection_run(
                self.project_root,
                payload,
                writer_results,
                commit_path=commit_path,
            )
        except Exception:
            pass
        return payload

    def apply_projections(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        status = str((payload.get("meta") or {}).get("status") or "")
        if status not in {"accepted", "rejected"}:
            return payload

        if status == "accepted":
            chapter = int((payload.get("meta") or {}).get("chapter") or 0)
            self._validate_acceptance(chapter, payload)
            event_store = EventLogStore(self.project_root)
            accepted_events = extraction_list(payload, "accepted_events")
            extraction = payload.setdefault("extraction_result", {})
            if not isinstance(extraction, dict):
                extraction = {}
                payload["extraction_result"] = extraction
            extraction["accepted_events"] = event_store.normalize_events(
                chapter, accepted_events
            )
            event_store.write_events(chapter, extraction["accepted_events"])

            proposals = AmendProposalTrigger().check(chapter, extraction["accepted_events"])
            if proposals:
                manager = IndexManager(DataModulesConfig.from_project_root(self.project_root))
                with manager._get_conn() as conn:
                    ensure_override_ledger_columns(conn)
                    persist_amend_proposals(conn, chapter, proposals)
                    conn.commit()

        return self.apply_projection_writers(payload)
