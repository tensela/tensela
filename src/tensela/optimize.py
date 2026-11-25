"""Finding the best values: the sliders of a project move until a number reaches its minimum, its maximum or a value.

It is the engine of «Find the best…» (the window), with nothing of the window: a search over the ranges of some
variables, each one a slider (its minimum, its maximum and its step), and an objective, a number that a node gives.

«Near» (search_near): it refines from where the sliders are, a pattern search (Hooke and Jeeves). It tries a step up
and a step down on each slider, keeps what improves, repeats the move that worked, and halves the steps when nothing
improves, until they reach the step of each slider. It never leaves the ranges, it always lands on values the slider
can show, and a calculation that fails counts as the worst. It finds the best value near the start: with several
valleys, the one where it starts.

«Wide» (over the whole range): a population that evolves, like Galapagos. Many candidates at random and the
sliders where they are; the best cross and mutate, generation after generation, until the best stops improving.
Slower, but it does not stay in the valley where it starts. «Both»: wide, and then near from the best.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

from .data import ShapeError
from .language import tr

#: What is searched for: the smallest number, the largest one, or the one nearest to a value.
GOALS = ('minimum', 'maximum', 'value')

#: Why it stopped: it cannot improve one step more (near), it has not improved for a while (wide), the time, the
#: attempts, or «Stop».
ENDS = ('found', 'settled', 'time', 'attempts', 'stopped')


@dataclass
class Variable:
    """A slider that the search moves: where it starts, its range and its step (0: any value)."""

    start: float
    low: float
    high: float
    step: float = 0.0

    def snap(self, x: float) -> float:
        """The nearest value the slider can take: inside its range and on its steps (counted from its minimum)."""
        x = min(max(float(x), self.low), self.high)
        if self.step > 0:
            x = self.low + round((x - self.low) / self.step) * self.step
            x = min(max(x, self.low), self.high)
            decimals = max(0, -int(math.floor(math.log10(self.step))) + 2) if self.step < 1 else 0
            x = round(x, decimals + 6)
        return x

    @property
    def finest(self) -> float:
        """The smallest move that still changes something: its step, or a millionth of its range."""
        return self.step if self.step > 0 else max((self.high - self.low) * 1e-6, 1e-12)


@dataclass
class Result:
    """What the search found: the best values, their number (as the node gives it) and how it went."""

    values: list[float]
    number: float
    score: float
    attempts: int
    seconds: float
    end: str
    failed: int = 0
    history: list[tuple[int, float]] = field(default_factory=list)   # (attempt, best number so far)
    best: list[tuple[float, list[float]]] = field(default_factory=list)   # the best ones found, the best first
    generations: list[tuple[int, float, float]] = field(default_factory=list)   # wide: (attempt, best, average)


def score_of(number: float, goal: str, target: float = 0.0) -> float:
    """How far a number is from what is wanted (lower is better): itself, its opposite, or its distance to the value."""
    if goal == 'minimum':
        return number
    if goal == 'maximum':
        return -number
    if goal == 'value':
        return abs(number - target)
    raise ShapeError(tr('The goal must be one of: {options}.').format(options=", ".join(tr(g) for g in GOALS)))


#: How it searches: refining from where the sliders are, over the whole range (a population that evolves), or both
#: (first over the whole range, then refining the best: the usual advice for hard problems).
METHODS = ('near', 'wide', 'both')


class _Enough(Exception):
    """Time, attempts or «Stop»: the search ends with the best found."""


class _Search:
    """What every way of searching shares: the evaluations already made (each set of values once), the count of
    attempts and failures, the time, and the best so far with its history."""

    def __init__(self, evaluate, variables, goal, target, seconds, attempts, stop, report, keep):
        if not variables:
            raise ShapeError(tr('Choose at least one slider to move.'))
        score_of(0.0, goal, target)                            # (an unknown goal says so before starting)
        self.evaluate, self.variables, self.goal, self.target = evaluate, variables, goal, target
        self.seconds, self.limit, self.stop, self.report, self.keep = seconds, attempts, stop, report, keep
        self.begin = time.monotonic()
        self.seen: dict[tuple, tuple[float, float]] = {}       # values → (score, number)
        self.attempts = self.failed = 0
        self.best, self.best_x = None, None
        self.history: list[tuple[int, float]] = []
        self.generations: list[tuple[int, float, float]] = []  # (attempt, best number, average number)

    def why_stop(self) -> str | None:
        if self.stop is not None and self.stop():
            return 'stopped'
        if self.attempts >= self.limit:
            return 'attempts'
        if time.monotonic() - self.begin >= self.seconds:
            return 'time'
        return None

    def result(self, end: str) -> Result:
        ranked = sorted(self.seen.items(), key=lambda kv: kv[1][0])
        best = [(number, list(x)) for x, (s, number) in ranked if math.isfinite(s)][:self.keep]
        x = self.best_x if self.best_x is not None else [v.snap(v.start) for v in self.variables]
        s, number = self.seen.get(tuple(x), (math.inf, math.nan))
        out = Result(list(x), number, s, self.attempts, time.monotonic() - self.begin, end, self.failed,
                     list(self.history), best)
        out.generations = list(self.generations)
        return out

    def snapped(self, x) -> list[float]:
        return [v.snap(c) for v, c in zip(self.variables, x)]

    def number(self, x: list[float]) -> float:
        return self.seen.get(tuple(x), (math.inf, math.nan))[1]

    def f(self, x: list[float]) -> float:
        """The score of some values (lower is better): computed once, the next times remembered."""
        key = tuple(x)
        if key in self.seen:
            return self.seen[key][0]
        end = self.why_stop()
        if end is not None:
            raise _Enough(end)
        self.attempts += 1
        try:
            number = float(self.evaluate(list(x)))
            s = score_of(number, self.goal, self.target) if math.isfinite(number) else math.inf
        except _Enough:
            raise
        except Exception:                                      # noqa: BLE001 (a calculation that fails is the worst)
            number, s = math.nan, math.inf
            self.failed += 1
        self.seen[key] = (s, number)
        if self.best is None or s < self.best:
            self.best, self.best_x = s, list(x)
            self.history.append((self.attempts, number))
            if self.report is not None:
                self.report(self.result('searching'))
        return s

    # --- Near: a pattern search from some values -------------------------------------------------------

    def near(self, start: list[float], first: float = 0.1) -> None:
        """Refines from `start` (Hooke and Jeeves): a step up and a step down on each slider, the move that worked
        once more, and half the steps when nothing improves, down to the step of each slider. `first`: the first
        step, as a share of each range."""
        variables = self.variables

        def explore(base: list[float], base_score: float, h: list[float]) -> tuple[list[float], float]:
            x, best = list(base), base_score
            for i, v in enumerate(variables):
                for sign in (1, -1):
                    trial = list(x)
                    trial[i] = v.snap(x[i] + sign * h[i])
                    if trial[i] == x[i]:
                        continue
                    s = self.f(trial)
                    if s < best:
                        x, best = trial, s
                        break
            return x, best

        x = self.snapped(start)
        fx = self.f(x)
        h = [max((v.high - v.low) * first, v.finest) for v in variables]
        while True:
            y, fy = explore(x, fx, h)
            if fy < fx:
                # It improved: the same move once more (the pattern), and a look around where it lands.
                while True:
                    pattern = self.snapped([2 * b - a for a, b in zip(x, y)])
                    x, fx = y, fy
                    fp = self.f(pattern)
                    z, fz = explore(pattern, fp, h)
                    if fz < fx:
                        y, fy = z, fz
                    else:
                        break
                continue
            if all(hi <= v.finest * (1 + 1e-9) for hi, v in zip(h, variables)):
                return
            h = [max(hi / 2, v.finest) for hi, v in zip(h, variables)]

    # --- Wide: a population that evolves -----------------------------------------------------------------

    def wide(self, population: int = 30, patience: int = 25, seed: int = 1) -> str:
        """Over the whole range: a population of candidates (the sliders where they are, and many at random), the
        best ones cross (each child takes something of two parents) and mutate (a small random change), the two
        best always stay, and some newcomers keep it from closing too soon. It ends when the best has not improved
        for `patience` generations ('settled'). The same seed, the same search."""
        rng = np.random.default_rng(seed)
        n, variables = len(self.variables), self.variables
        low = np.array([v.low for v in variables])
        span = np.array([v.high - v.low for v in variables])
        span = np.where(span > 0, span, 1.0)

        def to_values(u: np.ndarray) -> list[float]:
            return self.snapped(low + np.clip(u, 0.0, 1.0) * span)

        def to_u(x: list[float]) -> np.ndarray:
            return (np.array(x) - low) / span

        start = self.snapped([v.start for v in variables])
        candidates = [start] + [to_values(rng.random(n)) for _ in range(2 * population - 1)]   # an initial boost
        scored = sorted(((self.f(x), x) for x in candidates), key=lambda sx: sx[0])
        alive = scored[:population]
        stagnant, best = 0, alive[0][0]
        sigma = 0.15
        # A mutation never smaller than the step of each slider: below half a step, the slider would not move.
        least = np.array([v.finest for v in variables]) / span
        while stagnant < patience:
            self._generation(alive)

            def pick() -> list[float]:                         # a tournament of three: the best of them
                group = [alive[k] for k in rng.integers(0, len(alive), 3)]
                return min(group, key=lambda sx: sx[0])[1]

            children = [alive[0][1], alive[1][1]] if len(alive) > 1 else [alive[0][1]]
            taken = {tuple(x) for x in children}
            while len(children) < population:
                if rng.random() < 0.1:                          # a newcomer, anywhere
                    children.append(to_values(rng.random(n)))
                    continue
                a, b = to_u(pick()), to_u(pick())
                if rng.random() < 0.5:                          # between the parents, or a little beyond
                    child = a + rng.uniform(-0.25, 1.25, n) * (b - a)
                else:                                           # or each slider from one of the two
                    child = np.where(rng.random(n) < 0.5, a, b)
                change = rng.random(n) < max(1.0 / n, 0.3)
                child = child + change * rng.normal(0.0, 1.0, n) * np.maximum(sigma, least)
                values = to_values(child)
                tries = 0
                while tuple(values) in taken and tries < 3:      # already there: a bigger push, to keep variety
                    child = child + rng.normal(0.0, 1.0, n) * np.maximum(2 * sigma, least)
                    values, tries = to_values(child), tries + 1
                taken.add(tuple(values))
                children.append(values)
            alive = sorted(((self.f(x), x) for x in children), key=lambda sx: sx[0])[:population]
            if alive[0][0] < best - 1e-12 * max(1.0, abs(best)):
                best, stagnant = alive[0][0], 0
            else:
                stagnant += 1
                sigma = max(sigma * 0.85, 0.01)                # closer and closer around the best
        self._generation(alive)
        return 'settled'

    def _generation(self, alive) -> None:
        numbers = [self.number(x) for s, x in alive if math.isfinite(s)]
        if numbers:
            self.generations.append((self.attempts, numbers[0], float(np.mean(numbers))))
            if self.report is not None:                        # each generation, for the chart
                self.report(self.result('searching'))


def search(evaluate, variables: list[Variable], goal: str = 'minimum', target: float = 0.0, method: str = 'near',
           seconds: float = 30.0, attempts: int = 100000, stop=None, report=None, keep: int = 10,
           population: int = 30, patience: int = 25, seed: int = 1) -> Result:
    """Looks for the values of `variables` that bring `evaluate(values) → number` to the `goal` ('minimum',
    'maximum' or 'value', with `target`), by `method`: 'near' (from where they are), 'wide' (over the whole range)
    or 'both' (wide, then near from the best).

    `stop()`: True to stop (it keeps the best found). `report(result)`: called each time something better is found.
    A failed evaluation (an exception, or a number that is not finite) counts as the worst.
    """
    if method not in METHODS:
        raise ShapeError(tr('The way of searching must be one of: {options}.').format(
            options=", ".join(tr(m) for m in METHODS)))
    s = _Search(evaluate, variables, goal, target, seconds, attempts, stop, report, keep)
    try:
        if method == 'near':
            s.near([v.start for v in variables])
            return s.result('found')
        end = s.wide(population, patience, seed)
        if method == 'both':
            s.near(s.best_x, first=0.02)                       # then it refines the best, closely
            end = 'found'
        return s.result(end)
    except _Enough as e:
        return s.result(str(e))


def search_near(evaluate, variables: list[Variable], goal: str = 'minimum', target: float = 0.0,
                seconds: float = 30.0, attempts: int = 2000, stop=None, report=None, keep: int = 10) -> Result:
    """«Near»: from where the sliders are (see `search`)."""
    return search(evaluate, variables, goal, target, 'near', seconds, attempts, stop, report, keep)


def put_value(graph, node: str, input_: str, value: float, index: int | None = None, whole: bool = False) -> None:
    """A slider's value into its node: `whole`, as a whole number (a slider with a whole step); `index`, one value
    of a list (a slider per value), keeping the list written as it was."""
    from .project_file import numbers_items
    from .values import text_value
    if whole and float(value).is_integer():
        value = int(value)
    if index is not None:
        current = graph.nodes[node].inputs[input_]
        items = numbers_items(current)
        items[index] = value
        value = "; ".join(text_value(x) for x in items) if isinstance(current, str) else items
    graph.change(node, input_, value)


def single_number(value) -> float:
    """The number of a node's result, if it is a single one; if not, it says how to get one."""
    if value is None:
        raise ShapeError(tr('That node has no result yet.'))
    if getattr(value, "kind", None) is not None:
        raise ShapeError(tr('That node gives geometry, not a number: measure it first (Length, Area, Distance…).'))
    numbers = np.asarray(value.values, dtype=float).ravel()
    if numbers.size != 1:
        raise ShapeError(tr('That node gives {n} numbers: the search needs a single one (add them up or take the '
                            'largest with Summarise).').format(n=numbers.size))
    return float(numbers[0])
