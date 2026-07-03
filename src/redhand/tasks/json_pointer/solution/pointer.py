def _unescape(token):
    return token.replace("~1", "/").replace("~0", "~")


def resolve(document, pointer):
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("pointer must be empty or start with '/'")
    node = document
    for raw in pointer.split("/")[1:]:
        token = _unescape(raw)
        if isinstance(node, list):
            if token == "-" or not token.isdigit():
                raise IndexError(token)
            if len(token) > 1 and token[0] == "0":
                raise IndexError(token)
            node = node[int(token)]
        elif isinstance(node, dict):
            if token not in node:
                raise KeyError(token)
            node = node[token]
        else:
            raise KeyError(token)
    return node
