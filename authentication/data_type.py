from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class InviteDTO:
    higher_role_email: str
    role: str
    email: str
    city_id: Optional[int] = None
    institution_id: Optional[int] = None

@dataclass(frozen=True)
class CacheDTO:
    invitation_dict: dict
    cache_key: str
