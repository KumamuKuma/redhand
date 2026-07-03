import re

from security import escape_html

_TAG = re.compile(r"\{\{\{\s*(\w+)\s*\}\}\}|\{\{\s*(\w+)\s*\}\}")


def render(template, context):
    def repl(m):
        if m.group(1) is not None:
            key, raw = m.group(1), True
        else:
            key, raw = m.group(2), False
        if key not in context:
            raise KeyError(key)
        value = str(context[key])
        return value if raw else escape_html(value)

    return _TAG.sub(repl, template)
