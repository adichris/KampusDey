from .models import CampusKind


def classify_kind(name: str | None) -> str:
    """Kind classification in the order given by DATA_SOURCES_PROMPT §6."""
    text = (name or "").lower()
    if "technical university" in text:
        return CampusKind.TECHNICAL_UNIVERSITY
    if "college of education" in text:
        return CampusKind.COLLEGE_OF_EDUCATION
    if "nursing" in text or "midwifery" in text or "midwives" in text:
        return CampusKind.NURSING_MIDWIFERY
    if "health" in text or "medical assistants" in text or "health assistants" in text:
        return CampusKind.HEALTH_TRAINING
    if "university college" in text:
        return CampusKind.UNIVERSITY_COLLEGE
    if "university" in text:
        return CampusKind.UNIVERSITY
    return CampusKind.OTHER
