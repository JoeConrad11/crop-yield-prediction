"""POST /calendar/plan and GET /calendar/knowledge -- the smart farm
calendar (see src/farm_calendar.py, src/calendar_service.py and
ARCHITECTURE.md). Stateless and on-demand: the frontend sends the farmer's
fields/herds/anchor dates (read from Supabase under RLS) and gets back the
derived due dates. Nothing here reads or writes the database.

Every returned item carries its citation; health items are vet-confirm
reminders only (enforced when the knowledge files load).
"""
from datetime import date
from typing import Literal, Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from calendar_service import build_plan, knowledge_summary

router = APIRouter()


class SubjectIn(BaseModel):
    subject_type: Literal["field", "herd"]
    subject_id: Union[int, str]
    kind: str  # crop ("corn", "soybeans") for fields, species ("cattle", "sheep") for herds
    name: Optional[str] = None
    anchors: dict[str, str] = Field(default_factory=dict)
    boundary: Optional[dict] = None
    planting_date: Optional[str] = None


class CompletionIn(BaseModel):
    subject_type: Literal["field", "herd"]
    subject_id: Union[int, str]
    rule_id: str
    occurrence_date: str


class PlanRequest(BaseModel):
    subjects: list[SubjectIn] = Field(max_length=100)
    completions: list[CompletionIn] = Field(default_factory=list, max_length=2000)


@router.get("/calendar/knowledge")
def calendar_knowledge():
    return knowledge_summary()


@router.post("/calendar/plan")
def calendar_plan(req: PlanRequest):
    for subject in req.subjects:
        for kind, value in subject.anchors.items():
            try:
                date.fromisoformat(value)
            except ValueError:
                raise HTTPException(422, f"'{value}' isn't a valid date for '{kind}' (use YYYY-MM-DD).")
    completions = [(c.subject_type, c.subject_id, c.rule_id, c.occurrence_date) for c in req.completions]
    return build_plan([s.model_dump() for s in req.subjects], completions)
