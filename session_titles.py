"""Display-title rules shared by binding and catalog adapters, without storage I/O."""


def clean_title(value):
    """Accept only short, single-line display names, never original prompt bodies."""
    return isinstance(value, str) and 0 < len(value) <= 160 and "\n" not in value and "\r" not in value
