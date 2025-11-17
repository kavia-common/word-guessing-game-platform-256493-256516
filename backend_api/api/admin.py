from django.contrib import admin

from .models import Word, GameSession, Guess


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ("text", "length", "is_active", "created_at")
    list_filter = ("is_active", "length")
    search_fields = ("text",)
    ordering = ("length", "text")


class GuessInline(admin.TabularInline):
    model = Guess
    extra = 0
    fields = ("attempt_number", "guess_word", "result", "is_correct", "created_at")
    readonly_fields = ("created_at",)


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "target_word",
        "mode",
        "puzzle_type",
        "difficulty",
        "hints_used",
        "max_attempts",
        "is_completed",
        "is_won",
        "started_at",
        "ended_at",
        "player_name",
        "time_limit_secs",
        "total_time_secs",
    )
    list_filter = ("is_completed", "is_won", "max_attempts", "mode", "puzzle_type", "difficulty")
    search_fields = ("target_word__text", "player_name")
    inlines = [GuessInline]
    readonly_fields = ("created_at", "updated_at")


@admin.register(Guess)
class GuessAdmin(admin.ModelAdmin):
    list_display = ("session", "attempt_number", "guess_word", "is_correct", "created_at")
    list_filter = ("is_correct",)
    search_fields = ("guess_word", "session__id", "session__target_word__text")
    ordering = ("session", "attempt_number")
    readonly_fields = ("metadata",)
