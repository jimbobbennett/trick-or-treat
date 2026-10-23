from pumpkin import carve


def test_happy():
    assert carve("happy") == "^_^"


def test_sleepy():
    assert carve("sleepy") == "-_-"
