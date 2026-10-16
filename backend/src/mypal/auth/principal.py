from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """The authenticated user, as established by the server.

    In production these attributes come from the identity provider (e.g. Azure AD claims).
    None means the attribute is unknown for this user.
    """

    subject: str  # stable user identifier from the identity provider
    company_code: str
    location_code: str | None
    category_code: str | None
    roles: frozenset[str] = frozenset()
