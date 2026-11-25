"""Join levels (thought with named levels): Flatten, and its undoing."""

from pathlib import Path

import numpy as np
import pytest

from tensela.data import Data, ShapeError, join_levels, split
from tensela.geometry import POINT
from tensela.nodes import automatic_level
from tensela.project_file import open_


def test_joining_keeps_the_order_inside_each_outer_element():
    d = Data(np.arange(12.).reshape(4, 3), ("triangle", "vertex"))
    j = join_levels(d)
    assert j.levels == ("vertex",) and np.allclose(j.values, np.arange(12))


def test_the_joined_level_takes_the_place_of_the_first_and_can_be_renamed():
    d = Data(np.arange(24.).reshape(2, 3, 4), ("floor", "row", "column"))
    j = join_levels(d, "floor", "column", "slot")
    assert j.levels == ("slot", "row") and j.values.shape == (8, 3)
    assert np.allclose(j.values[:4, 0], d.values[0, 0])                 # floor 0, all its columns, then floor 1


def test_split_undoes_it_and_the_empty_places_go():
    pts = Data(np.arange(60.).reshape(2, 10, 3), ("row", "point"), kind=POINT)
    groups = split(pts, "point", "groups of", 4, "group")                 # 12 places: two of them empty
    back = join_levels(groups, "group", "point")
    assert back.levels == ("row", "point") and back.holes is None
    assert np.allclose(back.values, pts.values)
    again = split(join_levels(Data(np.arange(12.).reshape(4, 3), ("t", "v"))), "v", "groups of", 3, "t")
    assert again.levels == ("t", "v")


def test_what_cannot_be_joined_says_so():
    with pytest.raises(ShapeError):
        join_levels(Data(np.arange(3.), ("point",)))
    with pytest.raises(ShapeError):
        join_levels(Data(np.zeros((2, 3)), ("a", "b")), "a", "a")
    with pytest.raises(ShapeError):
        join_levels(Data(np.zeros((2, 3, 4)), ("a", "b", "c")), "a", "b", "c")   # «c» is already there


