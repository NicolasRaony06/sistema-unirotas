from dataclasses import dataclass
from typing import Optional
from django.utils import timezone

@dataclass(frozen=True)
class LastStopDTO:
    line: int
    route: int
    current_stop: int

@dataclass(frozen=True)
class StopDTO:
    line: int
    route: int
    order: int
    distance_km: float

@dataclass(frozen=True)
class RouteDTO:
    line: int
    route: int


@dataclass(frozen=True)
class TripStopDTO:
    start_stop: int
    end_stop: int
    order: int
    distance_km: float

@dataclass(frozen=True)
class TimeLineDTO:
    order: int
    start_stop: int
    end_stop: int
    status: str
    distance_km: float
    step_seconds: int
    accumulated_seconds: int
    eta: Optional[timezone.datetime] = None

@dataclass(frozen=True)
class RoutePredictionDTO:
    current_order: int
    base_time: timezone.datetime
    total_remaining_seconds: int
    timeline: list[TimeLineDTO]
