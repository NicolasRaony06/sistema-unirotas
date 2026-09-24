from django.core.cache import cache
from django.utils import timezone



def start_trip_cache(line, route, start_stop, ttl=28800):
    now = timezone.now()
    today = now.date()

    cache_key = f"trip_start:{line}:{route}:{today}"

    cache.set(
        cache_key,
        {
            "start_stop": start_stop,
            "start_time": now,
        },
        timeout=ttl,
    )
