from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

import nh3


ALLOWED_TAGS = {
    "a",
    "article",
    "ast-r",
    "br",
    "div",
    "em",
    "h3",
    "label",
    "li",
    "p",
    "section",
    "span",
    "strong",
    "sup",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
    # MathML
    "math",
    "menclose",
    "mfenced",
    "mfrac",
    "mi",
    "mlongdiv",
    "mn",
    "mo",
    "mover",
    "mroot",
    "mrow",
    "msgroup",
    "msline",
    "mspace",
    "msqrt",
    "mstack",
    "mstyle",
    "msup",
    "msrow",
    "mtable",
    "mtd",
    "mtr",
    "none",
    # Images
    "img",
}

ALLOWED_ATTRIBUTES = {
    "*": {"style"},
    "a": {"href"},
    "ast-r": {"type", "marker"},
    "div": {"title"},
    "img": {
        "src",
        "width",
        "height",
        "alt",
        "data-mathml",
    },
    "math": {"xmlns", "class"},
    "menclose": {"notation", "mathcolor"},
    "mfenced": {"open", "close"},
    "mi": {"mathvariant"},
    "mlongdiv": {
        "charalign",
        "charspacing",
        "stackalign",
    },
    "mspace": {"linebreak"},
    "mstack": {"charalign", "stackalign"},
    "mstyle": {
        "mathsize",
        "displaystyle",
    },
    "mtable": {"columnalign"},
    "p": {"dir"},
    "table": {
        "border",
        "width",
        "cellspacing",
        "cellpadding",
    },
    "td": {
        "colspan",
        "rowspan",
    },
    "th": {"scope"},
}

ALLOWED_STYLE_PROPERTIES = {
    "background-color",
    "border-collapse",
    "border-color",
    "border-style",
    "color",
    "display",
    "font-family",
    "font-size",
    "font-style",
    "font-variant",
    "font-weight",
    "height",
    "letter-spacing",
    "list-style-type",
    "margin-left",
    "margin-right",
    "max-width",
    "text-align",
    "text-decoration",
    "text-indent",
    "text-transform",
    "vertical-align",
    "white-space",
    "width",
    "word-spacing",
}

ALLOWED_IMAGE_HOSTS = {
    "access.openupresources.org",
    "app.assistments.org",
    "cdn.openupresources.org",
    "cms-assets.illustrativemathematics.org",
    "cms-k12oer-staging.s3.amazonaws.com",
    "resources.assistments.org",
}


def _filter_attribute(
    tag: str,
    attribute: str,
    value: str,
) -> str | None:
    if tag == "img" and attribute == "src":
        parsed = urlparse(value)

        # Keep ordinary relative dataset image paths.
        if not parsed.scheme and not parsed.netloc:
            return value

        # Explicitly reject data images, including SVG.
        if parsed.scheme.lower() == "data":
            return None

        if (
            parsed.scheme.lower() == "https"
            and parsed.hostname
            and parsed.hostname.lower() in ALLOWED_IMAGE_HOSTS
        ):
            return value

        return None

    if tag == "a" and attribute == "href":
        parsed = urlparse(value)

        if not parsed.scheme and not parsed.netloc:
            return value

        if parsed.scheme.lower() == "https":
            return value

        return None

    return value


@lru_cache(maxsize=4096)
def sanitize_learning_html(value: object) -> str:
    if value is None:
        return ""

    return nh3.clean(
        str(value),
        tags=ALLOWED_TAGS,
        clean_content_tags={
            "iframe",
            "object",
            "script",
            "style",
        },
        attributes=ALLOWED_ATTRIBUTES,
        attribute_filter=_filter_attribute,
        filter_style_properties=ALLOWED_STYLE_PROPERTIES,
        url_schemes={"https"},
        url_relative="pass_through",
        link_rel="noopener noreferrer",
        strip_comments=True,
    )