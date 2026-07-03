from math import gcd


class Rational:
    def __init__(self, num, den=1):
        if den == 0:
            raise ZeroDivisionError("denominator must be non-zero")
        if den < 0:
            num, den = -num, -den
        g = gcd(abs(num), den) or 1
        self.num = num // g
        self.den = den // g

    def __add__(self, other):
        return Rational(self.num * other.den + other.num * self.den, self.den * other.den)

    def __sub__(self, other):
        return Rational(self.num * other.den - other.num * self.den, self.den * other.den)

    def __mul__(self, other):
        return Rational(self.num * other.num, self.den * other.den)

    def __eq__(self, other):
        return isinstance(other, Rational) and self.num == other.num and self.den == other.den

    def __lt__(self, other):
        return self.num * other.den < other.num * self.den

    def __hash__(self):
        return hash((self.num, self.den))

    def __repr__(self):
        return str(self.num) if self.den == 1 else f"{self.num}/{self.den}"

    @classmethod
    def from_string(cls, s):
        s = s.strip()
        if "/" in s:
            a, b = s.split("/")
            return cls(int(a), int(b))
        return cls(int(s))
