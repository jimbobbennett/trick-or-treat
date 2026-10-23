from cauldron import brew, bubble


def test_brew_sorts():
    assert brew(["toad", "bat wing", "newt"]) == "bat wing + newt + toad"


def test_bubble():
    assert bubble(2) == "blub blub"
