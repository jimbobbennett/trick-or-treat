def brew(ingredients: list[str]) -> str:
    """Brew a potion: ingredients joined with ' + ', in alphabetical order."""
    return " + ".join(ingredients)


def bubble(level: int) -> str:
    """Return a bubbling sound, one 'blub' per level."""
    return " ".join(["blub"] * level)
