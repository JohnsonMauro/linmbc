"""Pure button translation: source button events -> output key/button events.

No device I/O here, so every rule is unit-tested. Output codes are routed to the
virtual mouse or keyboard by the engine.
"""

from collections import Counter
from collections.abc import Mapping

Combo = tuple[int, ...]
Output = list[tuple[int, int]]  # (code, value) pairs, value 1 = down, 0 = up

DOWN, UP, REPEAT = 1, 0, 2


class Remapper:
    """Hold-style remap: the output combo is down exactly while the source button is."""

    def __init__(self, mapping: Mapping[int, Combo]) -> None:
        self._mapping: dict[int, Combo] = dict(mapping)
        # What each held source emitted on press, so release matches it even if
        # the mapping changed in between.
        self._held: dict[int, Combo] = {}
        # How many owners (held sources, timed taps) keep each output code down.
        self._down: Counter[int] = Counter()

    def set_mapping(self, mapping: Mapping[int, Combo]) -> None:
        self._mapping = dict(mapping)

    def is_held(self, code: int) -> bool:
        return code in self._held

    def key(self, code: int, value: int) -> Output:
        if value == DOWN:
            return self._press(code)
        if value == UP:
            return self._release(code)
        if value == REPEAT and code not in self._mapping and code in self._held:
            return [(code, REPEAT)]
        return []

    def release_all(self) -> Output:
        out: Output = []
        for code in list(self._held):
            out += self._release(code)
        return out

    def acquire(self, combo: Combo) -> Output:
        """Press combo for one more owner; only codes that were up are emitted."""
        out: Output = []
        for out_code in combo:
            self._down[out_code] += 1
            if self._down[out_code] == 1:
                out.append((out_code, DOWN))
        return out

    def release(self, combo: Combo) -> Output:
        """Undo one acquire(combo), in reverse order; codes still owned stay down."""
        out: Output = []
        for out_code in reversed(combo):
            self._down[out_code] -= 1
            if self._down[out_code] <= 0:
                del self._down[out_code]
                out.append((out_code, UP))
        return out

    def _press(self, code: int) -> Output:
        if code in self._held:
            return []
        combo = self._mapping.get(code, (code,))
        self._held[code] = combo
        return self.acquire(combo)

    def _release(self, code: int) -> Output:
        combo = self._held.pop(code, None)
        if combo is None:
            return []
        return self.release(combo)
