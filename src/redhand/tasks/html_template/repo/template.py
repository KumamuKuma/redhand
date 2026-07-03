def render(template, context):
    """Render `template`, interpolating {{ key }} (HTML-escaped) and
    {{{ key }}} (raw) from `context`. Raise KeyError for a missing key."""
    raise NotImplementedError("render() is not implemented yet")
