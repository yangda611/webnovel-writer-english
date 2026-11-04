#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ContractMeta(BaseModel):
    schema_version: str = "story-system/v1"
    contract_type: str
    generator_version: str = "phase2"
    source_trace: List[Dict[str, Any]] = Field(default_factory=list)
    query: str = ""
    chapter: int | None = None
    market: str | None = None
    body_language: str | None = None
    writing_profile_ref: Dict[str, Any] = Field(default_factory=dict)
    rule_pack_versions: Dict[str, str] = Field(default_factory=dict)
    language_pack_version: str | None = None


class OverrideBundle(BaseModel):
    locked: Dict[str, Any] = Field(default_factory=dict)
    append_only: Dict[str, Any] = Field(default_factory=dict)
    override_allowed: Dict[str, Any] = Field(default_factory=dict)


class MasterSetting(BaseModel):
    meta: ContractMeta
    route: Dict[str, Any] = Field(default_factory=dict)
    master_constraints: Dict[str, Any] = Field(default_factory=dict)
    base_context: List[Dict[str, Any]] = Field(default_factory=list)
    source_trace: List[Dict[str, Any]] = Field(default_factory=list)
    override_policy: Dict[str, List[str]] = Field(default_factory=dict)
    editorial_guidance: Dict[str, Any] = Field(default_factory=dict)


class ChapterBrief(BaseModel):
    meta: ContractMeta
    override_allowed: Dict[str, Any] = Field(default_factory=dict)
    chapter_directive: Dict[str, Any] = Field(default_factory=dict)
    dynamic_context: List[Dict[str, Any]] = Field(default_factory=list)
    source_trace: List[Dict[str, Any]] = Field(default_factory=list)
    language_rules: Dict[str, Any] = Field(default_factory=dict)
    editorial_guidance: Dict[str, Any] = Field(default_factory=dict)


class VolumeBrief(BaseModel):
    meta: ContractMeta
    volume_goal: Dict[str, Any]
    selected_tropes: List[str] = Field(default_factory=list)
    selected_pacing: Dict[str, Any] = Field(default_factory=dict)
    selected_scenes: List[str] = Field(default_factory=list)
    anti_patterns: List[str] = Field(default_factory=list)
    system_constraints: List[str] = Field(default_factory=list)
    editorial_guidance: Dict[str, Any] = Field(default_factory=dict)
    overrides: OverrideBundle = Field(default_factory=OverrideBundle)


class ReviewContract(BaseModel):
    meta: ContractMeta
    must_check: List[str] = Field(default_factory=list)
    blocking_rules: List[str] = Field(default_factory=list)
    genre_specific_risks: List[str] = Field(default_factory=list)
    anti_patterns: List[str] = Field(default_factory=list)
    system_constraints: List[str] = Field(default_factory=list)
    review_thresholds: Dict[str, Any] = Field(default_factory=dict)
    language_advisory: Dict[str, Any] = Field(default_factory=dict)
    aesthetics_advisory: List[Dict[str, Any]] = Field(default_factory=list)
    editorial_guidance: Dict[str, Any] = Field(default_factory=dict)
    overrides: OverrideBundle = Field(default_factory=OverrideBundle)
