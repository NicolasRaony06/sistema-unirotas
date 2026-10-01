from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class InviteDTO:
    higher_role_email: str
    role: str
    email: str
    city_id: Optional[int] = None
