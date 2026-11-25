---
title: Meshes
description: Meshes from points and faces, from surfaces or from triangles, and the nodes that read, join, smooth and shape them by hand.
---

A mesh is a surface made of flat faces that share their corners: triangles, quadrilaterals. It is how a shape is
built with flat glass, panels or folded sheet, and how free shapes are modelled by subdivision. These nodes are
copper on the canvas.

**Geometry and topology.** In a mesh, the **points** say where the corners are (its geometry) and the **faces** say
how they are joined (its topology). Move a point and the faces follow; the order of the corners of a face says which
side is its front.

## Make a mesh

### Mesh surface

![Mesh surface](/images/manual/nodes/mesh-surface.png)

**What for.** A surface as one mesh of quadrilaterals sharing their corners. On a surface of revolution or of
translation, the quadrilaterals come out flat: panels that can be built with flat glass.

| Input | What it means |
|---|---|
| **surface** | a surface, or a rectangle |
| **count u**, **count v** | faces across and up |

### Delaunay

![Delaunay](/images/manual/nodes/delaunay.png)

**What for.** To join points in triangles as even as possible, without thin ones: a terrain from survey points, a
skin of triangles, pyramids on the cells of a Voronoi.

| Input | What it means |
|---|---|
| **points** | the points to join; with other levels, one group for each |
| **more** | optional: a point added to each group, like the raised centre of a cell to make a pyramid |

### Mesh

**What for.** A mesh written by hand, from its corners and its faces: to understand meshes, or to build a precise
piece.

| Input | What it means |
|---|---|
| **points** | the corners, numbered from 0 in order |
| **faces** | the corners of each face, `;` between faces: `0 1 2; 2 1 3` (two triangles), `0 1 2 3` (a quadrilateral) |

**Tips.**
- Write the corners of each face counter-clockwise, seen from the front.

### Join meshes

![Join meshes](/images/manual/nodes/join-meshes.png)

**What for.** Everything with faces as one mesh. Welded, the faces that touch share their corners and become one
piece, which is what smoothing needs.

| Input | What it means |
|---|---|
| **a … h** | meshes, or anything with faces: boxes, panels, frames, surfaces |
| **weld** | yes: corners that touch become one |
| **doubled faces** | *leave* or *remove*: removing them turns a group of boxes into its outer skin |

**Tips.**
- Where the edges of two parts do not meet corner to corner (a T-node), they do not weld. **Mesh edges** with
  *naked* shows those seams.

## Change it

### Smooth mesh

![Smooth mesh](/images/manual/nodes/smooth-mesh.png)

**What for.** A smooth mesh from a simple one: model the shape with a few faces, and let the levels round it. A
table, a pavilion, a free form.

| Input | What it means |
|---|---|
| **method** | *Catmull-Clark* (any faces, they become quadrilaterals) or *Loop* (triangles) |
| **levels** | how many times it subdivides: each level about four times the faces |
| **border** | *smooth*, *fixed* or *corners fixed* |

**Tips.**
- For a shape of several parts, **join and weld** them first.

### Edit mesh

**What for.** To shape a mesh by hand: in the 3D view, choose its corners and drag them (Alt: up or down). Only the
moves are kept, so if the mesh that comes in changes, the edits stay.

**Tips.**
- **Edit mesh** followed by **Smooth mesh** is the way to model a free shape: a coarse cage moved by hand, and the
  levels round it.

### Triangulate

![Triangulate](/images/manual/nodes/triangulate.png)

**What for.** Every face as triangles, each quadrilateral split by a diagonal. Triangles are always flat.

| Input | What it means |
|---|---|
| **diagonal** | the *shorter* one, or always the *first* (0-2) or the *second* (1-3) |

### Flip faces

**What for.** To turn faces over, so the front becomes the back: to make all the faces of a mesh look the same way.

| Input | What it means |
|---|---|
| **which** | the faces to turn (`1` · `0 3`); empty: all |

## Read it

### Mesh faces

![Mesh faces](/images/manual/nodes/mesh-faces.png)

**What for.** To read each face of a mesh: its outline, its centre, its normal, how many sides it has, whether it
looks the same way as its neighbours, or how flat it is.

| Input | What it means |
|---|---|
| **what** | *outlines*, *centres*, *normals*, *sides*, *orientation* (+1 like its neighbours, −1 turned over) or *flatness* |

### Mesh edges

![Mesh edges](/images/manual/nodes/mesh-edges.png)

**What for.** The edges of a mesh as lines: its border, or the bars of a structure along its edges.

| Input | What it means |
|---|---|
| **which** | *naked* (used by one face: the border, or a seam that did not weld), *inner* (shared) or *all* |
