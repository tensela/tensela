---
title: Lists with names
description: Each list says what it is, and its name decides how it combines with other lists.
---

This is the most important idea in Tensela. Once it clicks, the rest becomes much clearer.

## What for

To work with **many things at once**, 16 floors, 20 bays, 320 panels, without arranging the data by hand before
combining it.

## The idea: threads and crossings

Every list in Tensela carries a **name**, its **level**: *floor*, *bay*, *panel*, *rib*. When a node receives two
lists, it looks at their names:

- **Different names: every one with every other one.** 16 floors and 20 bays give 320 panels, like the threads of
  a fabric: every vertical thread crosses every horizontal one, and each crossing is a piece.
- **The same name: one with one.** The first with the first, the second with the second. Two lists of 16 floors
  give 16 results, not 256.

![Different names cross; the same name pairs](/images/manual/diagrams/named-lists-en.svg)

That is all. There is nothing to flatten, graft or transpose.

## How

- Nodes that make lists, such as **Series**, **Grid**, **Points on curve** or **Split**, have a field to name the
  level. A Series of 60 numbers named `rib` means *these 60 values are 60 ribs*.
- **The name is free.** What matters is to write it **the same** where you want lists to pair one with one, and
  **different** where you want them to cross.
- **Tip:** use the singular of what you count, *rib*, *floor*, *panel*, because it reads naturally: *rib 3*.

## What it does

- **The cable shows the shape:** `rib 60 × height 60 = 3 600`.
- **Levels have no order.** `floor × bay` and `bay × floor` are the same thing.
- **Operations work on a level, by its name:** reverse the floors, keep one bay out of two, shift the floors one up,
  split into groups of four. **Reorder**, **Filter**, **Pick** and **Split** ask which level, by name.
- **If two lists with the same name have different sizes**, a notice says so instead of guessing.

## An example to try

Make two **Series**: one of 5 numbers named `x` and one of 5 named `y`, and connect them to a **Point** (one to x,
the other to y). You get 25 points in a square: the names are different, so they cross. Now name both `x`: you
get 5 points on a diagonal, because they pair one with one.

## To go further

How a list with levels is kept and combined, with code: [Named lists, inside](/manual/theory/named-lists-inside/).
The same tasks in Grasshopper and Dynamo: [Lists in Tensela, Grasshopper and Dynamo](/manual/theory/lists-compared/).
