import django_filters
from .models import Bus, BusStop, Municipio
from authentication.models import User, UserRole

class CityFilter(django_filters.FilterSet):
    STATUS_CHOICES = (
        (True, 'Ofertado'),
        (False, 'Inofertado')
    )

    name = django_filters.CharFilter(
        field_name='nome',
        lookup_expr='icontains',
        label='Nome'
    )
    ibge_code = django_filters.CharFilter(
        field_name='codigo_ibge',
        lookup_expr='icontains',
        label='Código ibge'
    )
    oferted_by_system = django_filters.ChoiceFilter(
        field_name='ofertado_pelo_sistema',
        choices = STATUS_CHOICES,
        label='Ofertado pelo sistema',
        empty_label = 'Todos'
    )
    manager = django_filters.ModelChoiceFilter(
        field_name='gestor',
        queryset=User.objects.filter(role=UserRole.MANAGER),
        label='Gestor',
        empty_label='Todos'
    )

    class Meta:
        model = Municipio
        fields = []

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not user or user.role != UserRole.ADMIN:
            self.filters.pop('manager', None)

class BusFilter(django_filters.FilterSet):
    STATUS_CHOICES = (
        (True, 'Ativo'),
        (False, 'Inativo')
    )

    name = django_filters.CharFilter(lookup_expr='icontains', label='Nome')
    license_plate = django_filters.CharFilter(lookup_expr='icontains', label='Placa')
    is_active = django_filters.ChoiceFilter(
        choices = STATUS_CHOICES,
        label='Status',
        empty_label ='Todos'
    )
    min_capacity = django_filters.NumberFilter(
        field_name='capacity',
        lookup_expr='gte',
        label='Capacidade mínima'
    )
    
    class Meta:
        model = Bus
        fields = []

class BusStopFilter(django_filters.FilterSet):
    STATUS_CHOICES = (
        (True, 'Ativo'),
        (False, 'Inativo')
    )

    name = django_filters.CharFilter(lookup_expr='icontains', label="Nome")
    is_active = django_filters.ChoiceFilter(
        choices = STATUS_CHOICES,
        label='Status',
        empty_label ='Todos'
    )
    city = django_filters.ModelChoiceFilter(
        queryset=Municipio.objects.none(),
        label='Município',
        empty_label='Todos'
    )

    class Meta:
        model = BusStop
        fields = []