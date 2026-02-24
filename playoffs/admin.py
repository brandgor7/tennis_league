from django.contrib import admin
from .models import PlayoffBracket, PlayoffSlot


class PlayoffSlotInline(admin.TabularInline):
    model = PlayoffSlot
    extra = 0
    fields = ('round', 'bracket_position', 'match', 'next_slot')
    autocomplete_fields = ('match',)


@admin.register(PlayoffBracket)
class PlayoffBracketAdmin(admin.ModelAdmin):
    list_display = ('season', 'generated_at', 'generated_by')
    list_filter = ('season',)
    search_fields = ('season__name',)
    inlines = [PlayoffSlotInline]


@admin.register(PlayoffSlot)
class PlayoffSlotAdmin(admin.ModelAdmin):
    list_display = ('bracket', 'round', 'bracket_position', 'match', 'next_slot')
    list_filter = ('bracket__season', 'round')
    search_fields = ('bracket__season__name',)
    autocomplete_fields = ('match', 'next_slot')
