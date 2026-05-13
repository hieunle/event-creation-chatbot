from __future__ import annotations

from datetime import date as date_type
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class EventQueryFilter(BaseModel):
    """Structured filter for the query_events tool. All fields optional.

    JSON schema is customised to satisfy OpenAI strict tool-schema rules:
    every property is listed in `required`, `additionalProperties: false`.
    The LLM passes `null` for fields it doesn't need.
    """

    model_config = ConfigDict(extra="forbid")

    latest: Optional[bool] = Field(
        default=None, description="True to order by created_at DESC (most recent first)"
    )
    date_from: Optional[date_type] = Field(default=None, description="Inclusive lower bound on event date (YYYY-MM-DD)")
    date_to: Optional[date_type] = Field(default=None, description="Inclusive upper bound on event date (YYYY-MM-DD)")
    category: Optional[str] = Field(default=None, description="Match category exactly")
    limit: Optional[int] = Field(
        default=None, ge=1, le=50, description="Max rows to return (default 5)"
    )

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict:
        schema = handler(core_schema)
        if "properties" in schema:
            schema["required"] = list(schema["properties"].keys())
            schema["additionalProperties"] = False
        return schema
