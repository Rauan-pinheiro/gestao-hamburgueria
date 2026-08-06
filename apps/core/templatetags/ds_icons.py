"""
Tag de ícones do Design System — Hamburgueria ERP.

Renderiza um <svg><use></svg> apontando para o sprite único e self-hosted em
static/img/icons/sprite.svg (sem CDN, sem misturar bibliotecas de ícone).

Uso nos templates:
    {% load ds_icons %}
    {% icon "box-seam" %}
    {% icon "trash" class="icon-sm" %}

`ICON_ALIASES` existe porque vários ícones do antigo Bootstrap Icons usados
no projeto (ex: "graph-up-arrow", "bar-chart-line", variações de calendário)
mapeiam para o mesmo desenho no sprite novo — evita duplicar <symbol> iguais.
"""
from django.template import Library
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = Library()

SPRITE_PATH = "img/icons/sprite.svg"

ICON_ALIASES = {
    "trash3": "trash",
    "check-circle-fill": "check-circle",
    "bar-chart-line": "bar-chart",
    "graph-up-arrow": "graph-up",
    "calendar-week": "calendar",
    "calendar-month": "calendar",
    "calendar3": "calendar",
    "hourglass-split": "hourglass",
    "grid-3x3-gap": "grid",
    "signpost-2": "signpost",
    "speedometer2": "speedometer",
    "menu-button-wide": "menu-card",
    "wallet2": "wallet",
    "check-lg": "check",
    "x-lg": "x",
    "plus-lg": "plus",
    "egg-fried": "burger",
    "toggle-on": "toggle",
    "toggle-off": "toggle",
    "star-fill": "star",
}


@register.simple_tag
def icon(name, **kwargs):
    real_name = ICON_ALIASES.get(name, name)
    css_class = ("icon " + kwargs.get("class", "")).strip()
    sprite_url = static(SPRITE_PATH)
    extra_attrs = mark_safe(
        "".join(
            f' {key}="{value}"'
            for key, value in kwargs.items()
            if key != "class"
        )
    )
    return format_html(
        '<svg class="{}" aria-hidden="true" focusable="false"{}><use href="{}#icon-{}"></use></svg>',
        css_class,
        extra_attrs,
        sprite_url,
        real_name,
    )
