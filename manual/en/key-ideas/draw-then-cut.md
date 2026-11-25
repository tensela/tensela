---
title: Draw the form, then cut it
description: The easiest way to get most designs, before learning to build them point by point.
---

## What for

To reach a complex form, a ribbed wall, a waffle roof, a sliced pavilion, with **few nodes and no formulas**.

## How

Instead of calculating every point of the form, **draw the form first and cut it afterwards**:

1. **Draw the form** with a few curves and a surface through them, for example a **Loft** through three or four
   curves.
2. **Cut it** with **Ribs**, which slices it into as many boards as you ask for, with the thickness you give.

A ribbed wall made this way needs about six nodes. Change the curves and all the ribs follow.

![Draw the form, cut it, lay the pieces flat](/images/manual/diagrams/draw-then-cut-en.svg)

## What it does

- **Ribs** cuts the surface with parallel planes and closes each rib against a back plane, the wall behind it. The
  **back** input is how far that plane is: with `0`, each rib goes from the form to the axis; with more, each rib
  keeps a straight backing.
- The same idea works for fabrication: **Sections** cuts a body into slices that you then lay flat on sheets.

## When to go further

Building the form **point by point**, with Series, a Point and a Formula or a Graph, gives total control over each
rib. It is the next step, and it is a very good way to learn [Lists with names](/manual/key-ideas/named-lists/). Start
by drawing and cutting; go point by point when you need it.
