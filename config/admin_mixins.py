from django import forms as django_forms


def _display_value(form_field, raw):
    if raw is None or raw == '':
        return '(none)'
    if isinstance(form_field, django_forms.ModelChoiceField):
        return str(raw)
    if hasattr(form_field, 'choices'):
        return dict(form_field.choices).get(raw, raw)
    if isinstance(raw, bool):
        return 'Yes' if raw else 'No'
    return str(raw)


class DetailedChangeMessageMixin:
    """
    Enriches the admin history entry for changes to show old → new values
    instead of just the field name.
    """

    def construct_change_message(self, request, form, formsets, add=False):
        if add:
            return super().construct_change_message(request, form, formsets, add)

        parts = []
        for field_name in form.changed_data:
            try:
                label = str(form.instance._meta.get_field(field_name).verbose_name).capitalize()
            except Exception:
                label = field_name.replace('_', ' ').capitalize()

            form_field = form.fields.get(field_name)
            old_raw = form.initial.get(field_name, None)
            new_val = form.cleaned_data.get(field_name, None)

            # For FK fields, initial is a PK integer; resolve via the form field's queryset.
            if isinstance(form_field, django_forms.ModelChoiceField) and isinstance(old_raw, int):
                try:
                    old_raw = form_field.queryset.get(pk=old_raw)
                except Exception:
                    pass

            old_display = _display_value(form_field, old_raw)
            new_display = _display_value(form_field, new_val)

            parts.append(f'{label}: "{old_display}" → "{new_display}"')

        for formset in (formsets or []):
            for obj in formset.new_objects:
                parts.append(f'Added {obj._meta.verbose_name} "{obj}"')
            for obj, fields in formset.changed_objects:
                parts.append(f'Changed {obj._meta.verbose_name} "{obj}" ({", ".join(fields)})')
            for obj in formset.deleted_objects:
                parts.append(f'Deleted {obj._meta.verbose_name} "{obj}"')

        return '. '.join(parts) + '.' if parts else 'No fields changed.'
