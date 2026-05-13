from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Scenario = Literal[
    "missing_field",
    "invalid_input",
    "confirmation",
    "success_save",
    "error_db",
    "update_previous_field",
    "lookup",
    "small_talk",
]


class ChatResponse(BaseModel):
    """Structured final response emitted by the agent each turn.

    Message format follows the spec: acknowledgement + clarification +
    one actionable next sentence. JSON schema is customised to be
    OpenAI-strict compliant (every property in `required`,
    `additionalProperties: false`).
    """

    model_config = ConfigDict(extra="forbid")

    role: Literal["assistant"] = "assistant"
    scenario: Scenario = Field(description="Classification of this turn's outcome")
    message: str = Field(description="Three-part user-facing message")

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict:
        schema = handler(core_schema)
        if "properties" in schema:
            schema["required"] = list(schema["properties"].keys())
            schema["additionalProperties"] = False
        return schema
