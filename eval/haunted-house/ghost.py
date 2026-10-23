from cauldron import brew


def boo():
    return "boo"


def haunt(rooms):
    """Visit each room and leave a potion behind."""
    return {room: brew([room, "ectoplasm"]) for room in rooms}
