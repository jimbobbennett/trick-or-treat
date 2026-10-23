def carve(face: str) -> str:
    """Return the pumpkin carving for a face name."""
    faces = {"happy": "^_^", "scary": ">_<", "sleepy": "-_-"}
    return faces[face]
