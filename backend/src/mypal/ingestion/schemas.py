"""Validated metadata that must accompany every uploaded policy version (the policy register
fields required by the concept note)."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

_CODE = r"^[A-Z0-9_-]{1,32}$"


class ScopeInput(BaseModel):
    """Who the version applies to. None for location/category means "all"."""

    model_config = ConfigDict(frozen=True)

    company_code: str = Field(pattern=_CODE)
    location_code: str | None = Field(default=None, pattern=_CODE)
    category_code: str | None = Field(default=None, pattern=_CODE)

    @classmethod
    def parse(cls, value: str) -> "ScopeInput":
        """'COMPANY', 'COMPANY:LOCATION' or 'COMPANY:LOCATION:CATEGORY'; '*' means all."""
        parts = [p.strip() for p in value.split(":")]
        if not 1 <= len(parts) <= 3:
            raise ValueError("scope must look like COMPANY[:LOCATION[:CATEGORY]]")
        parts += [""] * (3 - len(parts))
        company, location, category = (None if p in ("", "*") else p for p in parts)
        return cls(company_code=company or "", location_code=location, category_code=category)


class DraftMetadata(BaseModel):
    policy_key: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=64)
    title: str = Field(min_length=3, max_length=200)
    owner: str = Field(min_length=2, max_length=200)
    version_label: str = Field(pattern=r"^[A-Za-z0-9._-]{1,32}$")
    # Who uploaded it. From the authenticated identity once the API exists (Phase 7);
    # the development CLI takes it as an argument.
    uploaded_by: str = Field(min_length=1, max_length=200)
    effective_from: date | None = None
    source_link: HttpUrl | None = None
    scopes: list[ScopeInput] = Field(min_length=1)

    @field_validator("title", "owner", "uploaded_by")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("scopes")
    @classmethod
    def _no_duplicate_scopes(cls, scopes: list[ScopeInput]) -> list[ScopeInput]:
        if len(set(scopes)) != len(scopes):
            raise ValueError("the same scope is listed more than once")
        return scopes
