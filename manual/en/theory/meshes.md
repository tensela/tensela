---
title: Meshes
description: Geometry and topology, the front of a face, flat panels, and smooth shapes from coarse cages.
---

## NURBS or mesh

A **NURBS** is one smooth entity defined by a formula. A **mesh** is a set of flat faces joined by their corners: it
is not smooth, it only looks smoother the more faces it has. For free shapes that are hard to describe (a table, an
object), a mesh smoothed by subdivision is easier than a NURBS.

## Geometry and topology

A mesh has **vertices**, which are its **geometry** (where things are), and **faces**, which are its **topology**
(how they are joined). The same points joined another way make another mesh; the same faces with one point moved
make another geometry with the same topology.

## The front of a face

The order of the corners of a face says which side is its front: counter-clockwise seen from the front. Two
neighbouring faces are **compatible** when they go along their shared edge in opposite directions; a mesh whose faces
are all compatible is **orientable**. **Mesh faces** with *orientation* says +1 or −1 for each face.

## Flat panels

Triangles are always flat; a quadrilateral may not be. For free architecture built with flat glass or board, what
matters is a mesh of **flat quadrilaterals**. A surface of revolution or of translation (one curve swept along
another) gives them; a free form does not, and then **Planarize** flattens the panels, or **Triangulate** splits them
into triangles at the cost of more joints.

## Subdivision

**Smooth mesh** splits every face and moves the vertices towards the smooth surface the mesh stands for, level after
level. Model a coarse cage with few faces, move its corners by hand with **Edit mesh**, and let the levels round it.
