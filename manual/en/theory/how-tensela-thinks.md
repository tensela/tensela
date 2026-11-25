---
title: How Tensela thinks
description: Every value is a block of numbers whose directions have names. That is where the name Tensela comes from.
---

## Blocks of numbers

Inside Tensela, every value is a **block of numbers**: one number, a list, a table, or a block with more directions.
240 panels of a facade are a block `row 12 × column 20`; the corners of each panel add one more direction, `corner
4`; their coordinates, one more, `x y z`.

In mathematics, a block of numbers with several directions is called a **tensor**. That is the *ten* of Tensela.

![Tensor and fabric: where the name Tensela comes from](/images/manual/diagrams/tensor-fabric-en.svg)

## Directions with names

What makes Tensela different is that every direction of a block has a **name**: its **level**. *Row*, *column*,
*floor*, *rib*. When a node combines two blocks, it lines them up by name:

- directions with the **same name** go one with one;
- directions with **different names** cross, every one with every other one.

The result has all the directions of both. That is the *tela*, the fabric, of Tensela: two lists are the warp and the
weft, and every crossing is a piece. See [Lists with names](/manual/key-ideas/named-lists/).

## Why it is fast

A node does not go element by element: it computes the **whole block at once**. Moving 240 panels, or 24 000, is one
operation on a block. This is why a facade of thousands of pieces can update while you drag a slider.

## Why there is nothing to arrange

Because directions have names and no order, `row × column` and `column × row` are the same block. There is no need
to transpose, flatten or graft lists before combining them: the names say how they go together. When two lists with
the same name have different sizes, a notice says so instead of guessing.

## To go further

- [Named lists, inside](/manual/theory/named-lists-inside/): the rule in code, levels of variable size and holes.
- [How a project is calculated](/manual/theory/the-engine/): what is recalculated when you change something.
- [Lists in Tensela, Grasshopper and Dynamo](/manual/theory/lists-compared/): the same tasks in the three tools.
