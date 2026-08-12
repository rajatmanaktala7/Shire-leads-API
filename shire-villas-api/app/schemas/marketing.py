from typing import Any
from pydantic import BaseModel, Field

class LandingPageCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=2, max_length=120)
    config: dict[str, Any]
    active: bool = True

class LandingPageUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    config: dict[str, Any] | None = None
    active: bool | None = None
