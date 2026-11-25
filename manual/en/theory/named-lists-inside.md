---
title: Named lists, inside
description: How a list with levels is kept, the one rule that combines them, and what it looks like in code.
---

This page is for whoever wants to know how [lists with names](/manual/key-ideas/named-lists/) work inside, with some
code. You do not need it to design. The code is Python, simplified from the source of Tensela (the file `data.py`).

## What a value is

Every value in Tensela, from a single number to the corners of a thousand panels, is a **Data**: a block of numbers
(a *numpy* array) and the names of its first directions, its **levels**.

![A block of numbers whose directions have names](/images/manual/diagrams/block-en.svg)

```python
centres = Data(values,                    # a numpy array of 12 × 20 × 3
               levels=("row", "column"),  # the names of the first two directions
               name="centres")

centres.sizes   # {"row": 12, "column": 20}
centres.shape   # "row 12 × column 20 = 240"   (what the cable says)
```

The directions after the levels describe **each element**: a number has none, a point has one of size 3 (x y z), a
rectangle has its four corners. So the block of 240 centres is 12 × 20 × 3, but only *row* and *column* are lists.

## The one rule

Every node that combines inputs goes through the same function, `align`. It has three steps:

1. **The result has all the levels of the inputs**, in the order they appear.
2. **A level that is in two inputs must have the same size in both**; it pairs one with one. If the sizes differ,
   Tensela stops with a notice instead of guessing.
3. **A level that is in only one input crosses** with all the others.

```python
def align(*inputs):
    levels, sizes = [], {}
    for data in inputs:
        for level, size in data.sizes.items():
            if level not in sizes:              # a new level: it goes into the result
                levels.append(level)
                sizes[level] = size
            elif sizes[level] != size:          # the same name, another size: a clear notice
                raise ShapeError(f"The sizes of “{level}” do not match: …")
    return levels, [extend(d, levels, sizes) for d in inputs]
```

`extend` puts each block in all the directions of the result. It turns the block to the order of the result, gives
it size 1 in the levels it does not have, and **stretches** it to the full size. The stretching is numpy's
*broadcasting*: no number is copied, the block is only read as if it were bigger.

![The three steps of the rule](/images/manual/diagrams/align-en.svg)

```python
def extend(data, levels, sizes):
    order = sorted(range(len(data.levels)), key=lambda axis: levels.index(data.levels[axis]))
    block = numpy.transpose(data.values, order + element_axes)
    block = block.reshape([data.sizes.get(n, 1) for n in levels] + element_shape)
    return numpy.broadcast_to(block, [sizes[n] for n in levels] + element_shape)
```

With the inputs aligned, a node is written **once, for whole blocks**, and works the same for one element or for
24 000:

```python
>>> heights = Data([0, 3.5, 7, 10.5], levels=("floor",), name="heights")
>>> x = Data([0, 1, 2, 3, 4], levels=("bay",), name="x")
>>> points = apply(make_point, x, heights)        # different names: they cross
>>> points.shape
'floor 4 × bay 5 = 20'
>>> shift = Data([0, 0.2, 0.4, 0.6], levels=("floor",), name="shift")
>>> apply(add, heights, shift).shape              # the same name: one with one
'floor 4'
>>> apply(add, heights, Data(range(5), levels=("floor",), name="five"))
ShapeError: The sizes of “floor” do not match: 4 in “heights”, 5 in “five”.
```

## Working on one level, by its name

Because levels have names, an operation can say **which** level it works on without counting positions:

```python
reduce(areas, "sum", along="panel")      # the area of each floor: the panels are added up
reorder(points, "floor", mode="invert")  # the floors upside down; the bays as they were
```

**Summarise**, **Reorder**, **Filter**, **Pick** and **Split** all ask for a level by name. There is no *transpose*:
`floor × bay` and `bay × floor` are the same block, because the order of the levels never decides anything.

## Lists that are not rectangular

Real projects are not always regular blocks:

- **Levels of variable size.** A tower with more panels at the bottom than at the top: the level *panel* has a
  different size on each floor. Tensela keeps the block padded to the largest size, the **count** of panels of each
  floor, and a **mask** that says which cells really exist. The nodes only read the cells that exist.
- **Holes.** By default, **Filter** does not remove elements: it leaves them **empty in their place**, so the grid
  still reads the same (the panel of row 3, column 7 is still there, or is an empty place). With *remove: yes*, the
  ones that stay are numbered again.
- **Numbering.** The elements of a level are numbered from 0, unless the level starts at another number: with two
  basements, the floors go from −2.

## A safety net

Before calculating, `align` multiplies the sizes of the result. Above **5 million elements** it stops with a notice
instead of freezing the computer: it is almost always two levels crossing that should have been paired (the same
name), or one digit too many.

## Why “tensor”

A block of numbers with several directions is what mathematics calls a **tensor**. Most programs number its
directions (axis 0, axis 1, axis 2). Tensela names them. That small change is what removes the need to arrange data
by hand, and it is where the name *Tensela* comes from: [How Tensela thinks](/manual/theory/how-tensela-thinks/).
