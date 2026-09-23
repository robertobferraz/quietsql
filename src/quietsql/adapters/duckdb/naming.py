def singular(name: str) -> str:
    return name[:-1] if name.endswith("s") and len(name) > 1 else name
