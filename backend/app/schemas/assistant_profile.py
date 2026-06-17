from pydantic import BaseModel, Field


class AssistantProfileResponse(BaseModel):
    name: str
    identity_answer: str
    capability_answer: str
    greeting_answer: str
    thanks_answer: str
    usage_answer: str
    handoff_answer: str
    fallback_casual_answer: str


class AssistantProfileUpdateRequest(BaseModel):
    name: str = Field(min_length=1)
    identity_answer: str = Field(min_length=1)
    capability_answer: str = Field(min_length=1)
    greeting_answer: str = Field(min_length=1)
    thanks_answer: str = Field(min_length=1)
    usage_answer: str = Field(min_length=1)
    handoff_answer: str = Field(min_length=1)
    fallback_casual_answer: str = Field(min_length=1)
