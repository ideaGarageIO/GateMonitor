"""Minimal KiCad s-expression reader/writer."""


class Q(str):
    """A quoted string token."""


def parse(text):
    tokens = _tokenize(text)
    pos = 0

    def read():
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            lst = []
            while tokens[pos] != ")":
                lst.append(read())
            pos += 1
            return lst
        return tok

    return read()


def _tokenize(text):
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c in "()":
            out.append(c)
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while text[j] != '"':
                if text[j] == "\\":
                    buf.append(text[j:j + 2])
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            out.append(Q("".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\r\n()"':
                j += 1
            out.append(text[i:j])
            i = j
    return out


def dump(node, indent=0):
    if isinstance(node, Q):
        return '"' + node + '"'
    if not isinstance(node, list):
        return str(node)
    simple = all(not isinstance(x, list) for x in node)
    if simple or len(node) <= 2 and all(
            not isinstance(x, list) or all(not isinstance(y, list) for y in x) for x in node):
        return "(" + " ".join(dump(x, indent) for x in node) + ")"
    pad = "  " * (indent + 1)
    head = []
    rest = list(node)
    while rest and not isinstance(rest[0], list):
        head.append(dump(rest.pop(0)))
    s = "(" + " ".join(head)
    for x in rest:
        s += "\n" + pad + dump(x, indent + 1)
    return s + ")"


def find(node, key):
    """All direct children lists whose head is `key`."""
    return [x for x in node if isinstance(x, list) and x and x[0] == key]
