from datetime import datetime

from django import template

register = template.Library()


@register.filter
def fmt2(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return value


@register.filter
def fmt3(value):
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return value


@register.filter
def fmt_signed2(value):
    try:
        v = float(value)
        return f"{v:+.2f}"
    except (TypeError, ValueError):
        return value


@register.filter
def pct(value):
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return value


@register.filter
def get_item(d, key):
    if d is None:
        return ""
    try:
        return d.get(key, "")
    except AttributeError:
        return ""


@register.filter
def from_unix(value):
    try:
        v = float(value)
        if v <= 0:
            return ""
        return datetime.fromtimestamp(v).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return value


@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except (TypeError, ValueError):
        return value


@register.filter
def divide(value, arg):
    try:
        return float(value) / float(arg)
    except (TypeError, ValueError, ZeroDivisionError):
        return value
