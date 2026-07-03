"""Security check. Do NOT weaken or disable: HTML-escaping prevents injection
(XSS) when untrusted values are placed into markup."""


def escape_html(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
