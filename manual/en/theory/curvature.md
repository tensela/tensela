---
title: Curvature and developable surfaces
description: Can it be made from flat sheet, or does it have to be moulded? The Gaussian and the mean curvature.
---

## The builder's question

Before anything else, a builder asks of a curved surface: **can it be made from flat sheet** (metal, plywood, card)
**or does it have to be moulded?** Curvature answers it.

## Gaussian curvature

- **Zero:** it can be made from flat sheet without stretching. Planes, cylinders, cones.
- **Positive:** it curves the same way in every direction, like a dome. It has to be moulded or cut in gores.
- **Negative:** it curves opposite ways, like a saddle. It has to be moulded too.

## Mean curvature

How much the surface **bends** on average. A balanced saddle has a mean curvature of zero and still cannot be made
from flat sheet: that is why both are needed. The sign of the mean depends on which way the face looks; for a
pattern, use its absolute value (`abs` in a Formula).

## Developable surfaces

A surface you get by bending a sheet without stretching it is **developable**: its Gaussian curvature is zero
everywhere. **Surface curvature** answers yes or no, and **Unroll** flattens it exactly.

A surface that is not developable, like a dome, can still be built from flat pieces: cut it into gores with **Sub
surface**, and unroll each one. **Unroll** says how much each piece stretches; with more gores, each stretches less.
