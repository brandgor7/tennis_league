from django import forms as django_forms
from django.contrib.auth import get_user_model
from django.test import TestCase

from config.admin_mixins import DetailedChangeMessageMixin

User = get_user_model()


class _FallbackAdmin:
    def construct_change_message(self, request, form, formsets, add=False):
        return 'FALLBACK'


class _ConcreteAdmin(DetailedChangeMessageMixin, _FallbackAdmin):
    pass


class _MockMeta:
    def get_field(self, name):
        field = type('F', (), {'verbose_name': name.replace('_', ' ')})()
        return field


class _MockInstance:
    _meta = _MockMeta()


class _MockForm:
    def __init__(self, changed_data, initial, cleaned_data, fields=None):
        self.changed_data = changed_data
        self.initial = initial
        self.cleaned_data = cleaned_data
        self.fields = fields or {}
        self.instance = _MockInstance()


class _MockFormset:
    def __init__(self, new_objects=(), changed_objects=(), deleted_objects=()):
        self.new_objects = list(new_objects)
        self.changed_objects = list(changed_objects)
        self.deleted_objects = list(deleted_objects)


class _MockObj:
    def __init__(self, name, verbose_name='roster entry'):
        self._name = name
        self._meta = type('M', (), {'verbose_name': verbose_name})()

    def __str__(self):
        return self._name


admin = _ConcreteAdmin()


class DetailedChangeMessageAddTest(TestCase):
    def test_add_delegates_to_super(self):
        form = _MockForm([], {}, {})
        result = admin.construct_change_message(None, form, [], add=True)
        self.assertEqual(result, 'FALLBACK')


class DetailedChangeMessageNoChangesTest(TestCase):
    def test_no_changed_data_no_formsets(self):
        form = _MockForm([], {}, {})
        result = admin.construct_change_message(None, form, [], add=False)
        self.assertEqual(result, 'No fields changed.')

    def test_empty_formsets_no_changed_data(self):
        form = _MockForm([], {}, {})
        formset = _MockFormset()
        result = admin.construct_change_message(None, form, [formset], add=False)
        self.assertEqual(result, 'No fields changed.')


class DetailedChangeMessagePlainFieldTest(TestCase):
    def test_simple_text_field(self):
        form = _MockForm(
            changed_data=['name'],
            initial={'name': 'Spring 2024'},
            cleaned_data={'name': 'Spring 2025'},
        )
        result = admin.construct_change_message(None, form, [], add=False)
        self.assertIn('"Spring 2024"', result)
        self.assertIn('"Spring 2025"', result)
        self.assertIn('→', result)

    def test_integer_field(self):
        form = _MockForm(
            changed_data=['points_for_win'],
            initial={'points_for_win': 2},
            cleaned_data={'points_for_win': 3},
        )
        result = admin.construct_change_message(None, form, [], add=False)
        self.assertIn('"2"', result)
        self.assertIn('"3"', result)

    def test_multiple_changed_fields_joined_by_period(self):
        form = _MockForm(
            changed_data=['name', 'year'],
            initial={'name': 'Old', 'year': 2024},
            cleaned_data={'name': 'New', 'year': 2025},
        )
        result = admin.construct_change_message(None, form, [], add=False)
        self.assertIn('"Old"', result)
        self.assertIn('"New"', result)
        self.assertIn('"2024"', result)
        self.assertIn('"2025"', result)
        self.assertTrue(result.endswith('.'))


class DetailedChangeMessageChoiceFieldTest(TestCase):
    def _choice_field(self, choices):
        field = django_forms.ChoiceField(choices=choices)
        return field

    def test_choice_field_shows_display_label_not_value(self):
        choices = [('weekly', 'Weekly'), ('consecutive_days', 'Consecutive days')]
        form = _MockForm(
            changed_data=['schedule_type'],
            initial={'schedule_type': 'weekly'},
            cleaned_data={'schedule_type': 'consecutive_days'},
            fields={'schedule_type': self._choice_field(choices)},
        )
        result = admin.construct_change_message(None, form, [], add=False)
        self.assertIn('"Weekly"', result)
        self.assertIn('"Consecutive days"', result)
        self.assertNotIn('weekly', result.replace('"Weekly"', ''))

    def test_unknown_choice_value_falls_back_to_raw(self):
        choices = [('a', 'Alpha')]
        form = _MockForm(
            changed_data=['status'],
            initial={'status': 'unknown_old'},
            cleaned_data={'status': 'a'},
            fields={'status': self._choice_field(choices)},
        )
        result = admin.construct_change_message(None, form, [], add=False)
        self.assertIn('"unknown_old"', result)
        self.assertIn('"Alpha"', result)


class DetailedChangeMessageNullAndBoolTest(TestCase):
    def test_none_old_value_shown_as_none_label(self):
        form = _MockForm(
            changed_data=['winner'],
            initial={'winner': None},
            cleaned_data={'winner': None},
        )
        result = admin.construct_change_message(None, form, [], add=False)
        self.assertIn('(none)', result)

    def test_empty_string_old_value_shown_as_none_label(self):
        form = _MockForm(
            changed_data=['notes'],
            initial={'notes': ''},
            cleaned_data={'notes': 'Replay needed'},
        )
        result = admin.construct_change_message(None, form, [], add=False)
        self.assertIn('(none)', result)
        self.assertIn('"Replay needed"', result)

    def test_boolean_field_shows_yes_no(self):
        field = django_forms.BooleanField()
        form = _MockForm(
            changed_data=['is_active'],
            initial={'is_active': True},
            cleaned_data={'is_active': False},
            fields={'is_active': field},
        )
        result = admin.construct_change_message(None, form, [], add=False)
        self.assertIn('"Yes"', result)
        self.assertIn('"No"', result)


class DetailedChangeMessageFKFieldTest(TestCase):
    def test_fk_old_pk_resolved_to_string_via_queryset(self):
        user = User.objects.create_user(username='jdoe', first_name='John', last_name='Doe')
        field = django_forms.ModelChoiceField(queryset=User.objects.all())
        form = _MockForm(
            changed_data=['winner'],
            initial={'winner': user.pk},
            cleaned_data={'winner': user},
            fields={'winner': field},
        )
        result = admin.construct_change_message(None, form, [], add=False)
        self.assertIn(str(user), result)
        self.assertIn(str(user), result.split('→')[0])

    def test_fk_nonexistent_pk_falls_back_gracefully(self):
        field = django_forms.ModelChoiceField(queryset=User.objects.all())
        form = _MockForm(
            changed_data=['winner'],
            initial={'winner': 99999},
            cleaned_data={'winner': None},
            fields={'winner': field},
        )
        result = admin.construct_change_message(None, form, [], add=False)
        self.assertIn('99999', result)


class DetailedChangeMessageFormsetTest(TestCase):
    def test_added_inline_object(self):
        obj = _MockObj('Alice', verbose_name='roster entry')
        formset = _MockFormset(new_objects=[obj])
        form = _MockForm([], {}, {})
        result = admin.construct_change_message(None, form, [formset], add=False)
        self.assertIn('Added', result)
        self.assertIn('roster entry', result)
        self.assertIn('Alice', result)

    def test_changed_inline_object(self):
        obj = _MockObj('Bob', verbose_name='roster entry')
        formset = _MockFormset(changed_objects=[(obj, ['tier', 'seed'])])
        form = _MockForm([], {}, {})
        result = admin.construct_change_message(None, form, [formset], add=False)
        self.assertIn('Changed', result)
        self.assertIn('Bob', result)
        self.assertIn('tier', result)
        self.assertIn('seed', result)

    def test_deleted_inline_object(self):
        obj = _MockObj('Carol', verbose_name='roster entry')
        formset = _MockFormset(deleted_objects=[obj])
        form = _MockForm([], {}, {})
        result = admin.construct_change_message(None, form, [formset], add=False)
        self.assertIn('Deleted', result)
        self.assertIn('Carol', result)

    def test_main_form_changes_and_inline_combined(self):
        form = _MockForm(
            changed_data=['name'],
            initial={'name': 'Old'},
            cleaned_data={'name': 'New'},
        )
        obj = _MockObj('Dave', verbose_name='roster entry')
        formset = _MockFormset(new_objects=[obj])
        result = admin.construct_change_message(None, form, [formset], add=False)
        self.assertIn('"Old"', result)
        self.assertIn('"New"', result)
        self.assertIn('Added', result)
        self.assertIn('Dave', result)
