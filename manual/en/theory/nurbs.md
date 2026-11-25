---
title: NURBS curves and surfaces
description: Control points that pull like magnets, the degree, the weights and the knots.
---

A **NURBS** is a smooth curve or surface defined by a few numbers. It is the usual way to describe free shapes
precisely: a handrail, the edge of a slab, a shell.

## Control points

![A NURBS curve of degree 3 and its control points](/images/manual/diagrams/nurbs-en.svg)

The curve does **not** pass through its control points (only, usually, through the first and the last): they **pull
it like magnets**. This is the difference with **Curve through points**, which passes through every point. The polygon of the control points is a good guide to the
shape: the curve follows it, smoothed.

## Degree

How smooth and how taut the curve is: `1` is the control polygon itself, `2` makes arcs, `3` is the usual smooth
curve, and higher is tauter. A curve needs at least one more control point than its degree.

## Weights

How strongly each control point pulls. What counts is the difference between them: all at `2` is the same as all at
`1`. With the right weights, a NURBS draws an exact circle, which a plain polynomial curve cannot.

## Knots

How the curve is spread between its control points: evenly, by distance, or by hand. Repeating a knot makes a kink.
You only need them to fine-tune a curve.

## Surfaces: u and v

A NURBS surface is the same in two directions: a grid of control points, rows by columns, with a degree in each
direction. Its two directions are **u** (along the rows) and **v** (along the columns), each from `0` to `1`. Every
point of the surface has its u and v, which is how nodes ask for *a point at the middle* or *the curves along u*.

## Judging a curve

The **curvature comb** shows whether a curve is good: smooth tips mean a smooth curve; a jump, an abrupt change; a
spike, a corner.
