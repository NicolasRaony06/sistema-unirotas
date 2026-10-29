from .data_type import RouteDTO, TripStopDTO
from management.models import TrechoViagem
class RouteMaterialization:
    def __init__(self, route_data:RouteDTO):
        self.route_data = route_data
        self.route_stops:list[TripStopDTO] = []

    def get_route_stops(self):
        route_stops_obj = TrechoViagem.objects.filter(rota=self.route_data.route).order_by('ordem')
        for rs in route_stops_obj:
            self.route_stops.append(TripStopDTO(start_stop=rs.parada_inicio, end_stop=rs.parada_fim, order=rs.ordem, distance_km=rs.distancia_km))
