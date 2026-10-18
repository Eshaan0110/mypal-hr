from pydantic import BaseModel


class PrincipalOut(BaseModel):
    """What the interface may show about the logged-in user: the attributes that decide which
    policies apply. (Real names come with SSO in Phase 8.)"""

    subject: str
    company_code: str
    location_code: str | None
    category_code: str | None
    is_development_login: bool
