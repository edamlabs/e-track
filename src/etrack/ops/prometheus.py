"""ops/prometheus: names as Prometheus takes them — a class name as the snake_case a metric is called by."""


def prometheus_snake(name: str) -> str:
    """`BoundaryCrossed` → `boundary_crossed`; an acronym stays one word: `HTTPRefused` → `http_refused`."""
    marks = [
        index > 0
        and char.isupper()
        and (not name[index - 1].isupper() or (index + 1 < len(name) and name[index + 1].islower()))
        for index, char in enumerate(name)
    ]
    return "".join(f"_{char}" if mark else char for char, mark in zip(name, marks, strict=True)).lower()
