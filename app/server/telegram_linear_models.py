"""Strict answer models and the one parse helper for telegram_linear (RA-8632).

Every Linear answer the Telegram /linear/create path reads is validated here:
StrictStr ids, `success` only the boolean true, required id/identifier/url/title
on issues. `_parse` turns any validation error into a 502 naming what was
malformed and what happened as a result; nothing else reads raw GraphQL dicts.
"""
from __future__ import annotations

from typing import Annotated, Any, Generic, Literal, TypeVar

from fastapi import HTTPException
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictStr, ValidationError

NOTHING = "nothing created"

_Text = Annotated[StrictStr, Field(min_length=1)]


def _is_true(value: Any) -> Any:
    """Literal[True] alone accepts 1 (1 == True); only the bool True is success."""
    if value is not True:
        raise ValueError("success must be the boolean true")
    return value


_Success = Annotated[Literal[True], BeforeValidator(_is_true)]
T = TypeVar("T")


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)


class _Nodes(_Strict, Generic[T]):
    nodes: list[T]


class _Ref(_Strict):  # a team: only its id is read
    id: _Text


class _Label(_Ref):
    name: StrictStr


class _Issue(_Ref):
    identifier: _Text
    url: _Text
    title: _Text


class _Project(_Ref):
    name: StrictStr
    teams: _Nodes[_Ref]


class _TeamLabels(_Strict):
    labels: _Nodes[_Label]


class OpenIssueAnswer(_Strict):
    issues: _Nodes[_Issue]


class ProjectAnswer(_Strict):
    projects: _Nodes[_Project]


class LabelAnswer(_Strict):
    team: _TeamLabels


class _LabelCreated(_Strict):
    success: _Success
    issueLabel: _Label


class LabelCreateAnswer(_Strict):
    issueLabelCreate: _LabelCreated


class _IssueCreated(_Strict):
    success: _Success
    issue: _Issue


class IssueCreateAnswer(_Strict):
    issueCreate: _IssueCreated


class _ConfigRouting(_Strict):
    teamId: _Text
    projectId: StrictStr | None = None


M = TypeVar("M", bound=BaseModel)


def _parse(model: type[M], data: Any, what: str, consequence: str = NOTHING) -> M:
    """Validate `data` against `model`; any mismatch is 502, never a guess."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(502, f"{what} was malformed ({exc.error_count()} problem(s)); {consequence}") from None
