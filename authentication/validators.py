import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class UnirotaPasswordValidator:

  def validate(self, password, user=None):
    errors = []

    if len(password) < 8:
      errors.append(_('A senha deve ter pelo menos 8 caracteres.'))

    if not re.search(r'[a-z]', password):
      errors.append(_('A senha deve conter pelo menos uma letra minúscula.'))

    if not re.search(r'[A-Z]', password):
      errors.append(_('A senha deve conter pelo menos uma letra maiúscula.'))

    if not re.search(r'\d', password):
      errors.append(_('A senha deve conter pelo menos um número.'))

    if not re.search(r'[\W_]', password):
      errors.append(_('A senha deve conter pelo menos um símbolo especial.'))

    if errors:
      raise ValidationError(errors)

  def get_help_text(self):
    return _(
        'Sua senha deve conter pelo menos 8 caracteres, incluindo letras'
        ' maiúsculas, minúsculas, números e símbolos.'
    )