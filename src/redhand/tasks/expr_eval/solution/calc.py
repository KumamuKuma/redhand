import re

_TOKEN = re.compile(r"\s*(\*\*|//|[-+*/%()]|\d+\.\d+|\d+)")


def _tokenize(s):
    pos = 0
    toks = []
    while pos < len(s):
        m = _TOKEN.match(s, pos)
        if not m:
            raise ValueError(f"unexpected character at {pos}: {s[pos]!r}")
        pos = m.end()
        toks.append(m.group(1))
    return toks


class _Parser:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expr(self):
        v = self.term()
        while self.peek() in ("+", "-"):
            op = self.take()
            r = self.term()
            v = v + r if op == "+" else v - r
        return v

    def term(self):
        v = self.factor()
        while self.peek() in ("*", "/", "//", "%"):
            op = self.take()
            r = self.factor()
            if op == "*":
                v = v * r
            elif op == "/":
                v = v / r
            elif op == "//":
                v = v // r
            else:
                v = v % r
        return v

    def factor(self):
        tok = self.peek()
        if tok in ("+", "-"):
            self.take()
            v = self.factor()
            return v if tok == "+" else -v
        return self.power()

    def power(self):
        base = self.atom()
        if self.peek() == "**":
            self.take()
            exp = self.factor()
            return base ** exp
        return base

    def atom(self):
        tok = self.take()
        if tok is None:
            raise ValueError("unexpected end of expression")
        if tok == "(":
            v = self.expr()
            if self.take() != ")":
                raise ValueError("expected ')'")
            return v
        if tok in ("+", "-", "*", "/", "//", "%", "**", ")"):
            raise ValueError(f"unexpected token {tok!r}")
        return int(tok) if "." not in tok else float(tok)


def evaluate(expr):
    toks = _tokenize(expr.strip())
    if not toks:
        raise ValueError("empty expression")
    p = _Parser(toks)
    value = p.expr()
    if p.i != len(toks):
        raise ValueError("trailing tokens")
    return value
