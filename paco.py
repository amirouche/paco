from collections import namedtuple

import pytest


def test_true():
    assert True


# XXX: The types 'pair', and 'maybe' are fused together.
CX = namedtuple("Combinatorix", ("ok", "head", "tail"))

# Promote a reader to first-class to allow tree walk
CXR_type = namedtuple("CombinatorixReader", ("reader", "args", "read"))


def CXR(reader, *args):
    return CXR_type(reader, args, reader(*args))


def cx_any(*ops):
    """Read with the first in order that succeed."""

    def func(cx):
        for op in ops:
            out = op(cx)
            if out.ok:
                return out
        return CX(False, cx.head, cx.tail)

    return func


def cx_when(predicate):
    """Read when PREDICATE returns true.

    PREDICATE read the object, and returns it as-is."""

    def func(cx):
        if predicate(cx.head):
            return CX(True, cx.head, cx.tail)
        return CX(False, cx.head, cx.tail)

    return func


def cx_sequence(*readers):
    """Read one after the other using READERS. If one fail, all fail."""

    readers = [
        reader.read if isinstance(reader, CXR_type) else reader for reader in readers
    ]

    def aux(cx, ops):
        if not ops:
            return cx
        if cx is None:
            return CX(False, None, None)

        op = ops[0]
        print("SEQHEAD", cx.head)
        head = op(cx)
        if not head.ok:
            return CX(False, head.head, head.tail)
        out = CX(True, head.head, aux(head.tail, ops[1:]))
        return out

    def func(cx):
        cx = aux(cx, readers)
        return cx

    return func


def cx_from_string(string):
    """Translate STRING to a datastructure that reader can read"""

    if not string:
        return None

    cx = CX(None, string[0], cx_from_string(string[1:]))
    return cx


def cx_to_string(cx):
    """Convert CX to a string"""

    if not cx:
        return ""
    if cx.head is None:
        return ""
    if not cx.ok:
        return ""

    head = cx.head if isinstance(cx.head, str) else "".join(cx.head)

    return head + cx_to_string(cx.tail)


def test_cx_when():
    input = cx_from_string("yinyang")
    why = CXR(cx_when, lambda x: x == "y")
    cx = why.read(input)
    assert cx.ok
    assert cx.head == "y"


def test_cx_fortythree():
    four = CXR(cx_when, lambda x: x == "4")
    three = CXR(cx_when, lambda x: x == "3")
    cx = cx_sequence(four, three)
    fortytwo = cx_from_string("42")
    fortytwo = cx(fortytwo)
    assert cx_to_string(fortytwo) == "4"
    fortythree = cx_from_string("43")
    fortythree = cx(fortythree)
    assert fortythree.ok
    assert cx_to_string(fortythree) == "43"


def test_zero_or_more():
    cx = cx_zero_or_more(cx_any(cx_when(lambda x: True)))
    out = cx_to_string(cx(cx_from_string("Will, i am.")))
    assert out == "Will, i am."


def test_zero_or_more_parentheses():
    cx = cx_zero_or_more(cx_when(lambda x: x == "("))
    out = cx(cx_from_string("(((zzz"))
    assert cx_to_string(out) == "((("


def cx_zero_or_more(reader):
    """Read zero or more time with READER"""

    reader = reader.read if isinstance(reader, CXR_type) else reader

    def aux(cx):
        if cx is None:
            return CX(None, None, None)

        if cx.head is None:
            return CX(True, None, None)

        head = reader(cx)
        if not head.ok:
            return cx
        else:
            return head

    def func(cx):
        out = []
        while cx := aux(cx):
            if cx.ok:
                out.append(cx.head)
                cx = cx.tail
            elif not out:
                return CX(False, None, None)
            else:
                return CX(True, out, CX(None, cx.head, cx.tail))

    return func


def cx_apply(func, op):
    """Read using OP, and process the result with FUNC"""

    def wrapper(cx):
        cx = op(cx)
        if not cx.ok:
            return cx
        return func(cx)

    return wrapper


def test_cx_apply():
    expected = object()
    hello = cx_from_string("xxx")
    cx = cx_apply(
        lambda cx: CX(True, expected, hello),
        cx_zero_or_more(cx_when(lambda x: x == "x")),
    )
    out = cx(hello)
    assert out.ok
    assert out.head == expected
    assert out.tail == hello


def cx_one_or_more(reader):
    """Read with READER one or more times"""

    def frob(cx):
        if cx is None:
            return None
        if cx.head is None:
            return CX(True, None, None)
        if cx.tail is None:
            return CX(True, cx.head, None)

        return CX(True, [cx.head] + cx.tail.head, cx.tail.tail)

    return cx_apply(frob, cx_sequence(reader, cx_zero_or_more(reader)))


def pk(*args):
    print(*args)
    return args[-1]


def test_cx_one_or_more():
    cx = cx_one_or_more(cx_when(lambda x: x == "x"))
    assert not cx(cx_from_string("z")).ok
    assert cx(cx_from_string("xxx")).head == ["x", "x", "x"]
    assert cx(cx_from_string("xxxyyy")).head == ["x", "x", "x"]


def test_zero_or_more_three_balanced_parentheses():
    pln = cx_zero_or_more(cx_when(lambda x: x == "("))
    prn = cx_zero_or_more(cx_when(lambda x: x == ")"))
    cx = cx_sequence(pln, prn)
    out = cx(cx_from_string("((()))"))
    assert cx_to_string(out) == "((()))"


def cx_echo(op):
    def func(cx):
        out = op(cx)
        return out

    return func


lilcode = cx_apply(
    lambda x: CX(True, ["code", "".join(x.tail.head)], x.tail.tail.tail),
    cx_sequence(
        cx_when(lambda x: x == "`"),
        cx_zero_or_more(cx_when(lambda x: x != "`")),
        cx_when(lambda x: x == "`"),
    ),
)


def test_lilcode():
    assert lilcode(cx_from_string("`encoded` code")).head == ["code", "encoded"]


liltag = cx_apply(
    lambda x: CX(True, ["tag", "".join(x.tail.head)], x.tail.tail),
    cx_sequence(
        cx_when(lambda x: x == "#"),
        cx_one_or_more(cx_when(lambda x: not x.isspace())),
    ),
)


def test_liltag():
    def _test_liltag_to_pyhtml(cx):
        if cx is None:
            return []
        return [cx.head, *_test_liltag_to_pyhtml(cx.tail)]

    op = cx_sequence(
        liltag,
        cx_apply(
            lambda x: CX(True, "".join(x.head), None),
            cx_one_or_more(cx_when(lambda x: True)),
        ),
    )
    assert _test_liltag_to_pyhtml(op(cx_from_string("#tagged chip"))) == [
        ["tag", "tagged"],
        " chip",
    ]


lilmark = cx_one_or_more(cx_any(lilcode, liltag, cx_when(lambda x: True)))


def test_lilmark():
    def normalize(objects):
        out = []
        string = ""
        for obj in objects:
            if isinstance(obj, list):
                if string:
                    out.append(string)
                    string = ""
                out.append(obj)
            else:
                string += obj
        out.append(string)
        return out

    out = lilmark(
        cx_from_string("hello #people welcome to the `world` of parser combinators!")
    )

    assert normalize(out.head) == [
        "hello ",
        ["tag", "people"],
        " welcome to the ",
        ["code", "world"],
        " of parser combinators!",
    ]


def test_http_json_response():
    input = dict(
        ok=True,
        message="parsing is successful",
        data="XXX",  # dict(id=42, name="paco", type="cat")
    )

    def cxi(x):
        if isinstance(x, dict):
            cx = CX(None, None, None)
            for key, value in sorted(x.items(), key=lambda x: x[0]):
                cx = CX(None, CX(None, key, cxi(value)), cx)
            return CX(None, dict, cx)
        elif isinstance(x, list):
            cx = CX(None, None, None)
            for item in reversed(x):
                cx = CX(None, cxi(item), cx)
            return CX(None, list, cx)
        else:
            return CX(None, x, None)

    cx_dict = cx_apply(lambda x: x.tail, cx_when(lambda x: x is dict))

    given = cxi(input)
    given = cx_dict(given)

    print("GIVEN", given)
    cx_field = cx_any(
        cx_apply(
            lambda x: CX(True, x.tail, None),
            cx_when(lambda x: x.head == "ok"),
        ),
        cx_apply(
            lambda x: CX(True, x.tail, None),
            cx_when(lambda x: x.head == "message"),
        ),
        cx_apply(
            lambda x: CX(True, x.tail, None),
            cx_when(lambda x: x.head == "data"),
        ),
        cx_when(lambda x: x.head is None),
    )

    cx = cx_sequence(cx_field, cx_field, cx_field)
    given = cx(given)
    assert given == []
