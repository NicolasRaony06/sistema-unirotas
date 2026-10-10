from .data_type import RouteDTO, TripStopDTO

class RouteMaterialization:
    def __init__(self, route_data:RouteDTO):
        self.route_data = route_data
        self.route_stops:list[TripStopDTO] = []

    def get_route_stops(self):
        route_stops_obj = ... #RouteStop.objects.filter(route=route).select_related('start_stop', 'end_stop').order_by('order')
        return None
        for rs in route_stops_obj:
            self.route_stops.append(TripStopDTO(start_stop_id=rs.start_stop.pk, end_stop_id=rs.end_stop.pk, order=rs.order, distance_km=rs.distance))
