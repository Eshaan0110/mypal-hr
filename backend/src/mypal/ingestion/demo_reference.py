"""FICTIONAL reference codes matching the fictional sample policies in sample_data/policies.

Used only in development until HR confirms the real business unit, locations and employee
categories. Every name is marked fictional so it cannot be mistaken for real organisation data.
"""

from sqlalchemy.orm import Session

from mypal.db.models import Company, EmployeeCategory, Location

DEMO_COMPANIES = {
    "DEMO-HEALTH": "Demo Health Services (fictional)",
    # A second fictional company, used to prove one company cannot see another's policies.
    "DEMO-OTHER": "Other Demo Company (fictional)",
}
DEMO_LOCATIONS = {
    "DEMO-NORTH": "North Campus (fictional)",
    "DEMO-SOUTH": "South Campus (fictional)",
}
DEMO_CATEGORIES = {
    "PERMANENT": "Permanent employee (fictional category)",
    "PROBATION": "Employee on probation (fictional category)",
    "TRAINEE": "Trainee (fictional category)",
}


def seed_demo_reference_data(session: Session) -> int:
    """Insert any missing demo codes. Safe to run repeatedly. Returns the number added."""
    added = 0
    for model, values in (
        (Company, DEMO_COMPANIES),
        (Location, DEMO_LOCATIONS),
        (EmployeeCategory, DEMO_CATEGORIES),
    ):
        for code, name in values.items():
            if session.get(model, code) is None:
                session.add(model(code=code, name=name))
                added += 1
    session.flush()
    return added
