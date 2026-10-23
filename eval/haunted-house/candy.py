CANDY = {"chocolate": 3, "lollipop": 1, "toffee": 2}


def value(kind):
    return CANDY.get(kind, 0)
