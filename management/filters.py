import django_filters
from .models import Bus

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