---
title: Surfaces
description: Surfaces through curves, points or edges, revolutions and sweeps, structures on surfaces, and the nodes that measure, cut and flatten them.
---

Surfaces are roofs, walls, shells, skins and slabs. They are petrol blue on the canvas.

**On a surface, a position is u and v.** A surface has two directions, like the rows and columns of a sheet: **u**
along the rows and **v** along the columns, each from `0` (one edge) to `1` (the other). `u 0.5, v 0.5` is the middle.

## Make a surface

### Cap

![Cap](/images/manual/nodes/cap.png)

**What for.** To close a closed curve with a surface: a roof, a free-form slab, a slab with a courtyard.

| Input | What it means |
|---|---|
| **curve** | the closed outline |
| **holes** | optional: closed curves inside it (a courtyard, a skylight) |

### Loft

![Loft](/images/manual/nodes/loft.png)

**What for.** A surface through several curves in order: a wavy wall through three profiles, a roof through its
sections.

| Input | What it means |
|---|---|
| **curves** | the sections, in a list |
| **along** | the level of the sections; empty: the last |
| **smooth** | yes: smooth through the sections · no: straight between them |
| **closed** | yes: the last section goes back to the first |

**Tips.**
- If it comes out twisted, some curves go the other way: put a **Flip curve** with a direction before it.

### Extrude

![Extrude](/images/manual/nodes/extrude.png)

**What for.** To drag curves into a sheet or a wall; with caps, a closed plan becomes a volume. Or to bring them to a
point: a pyramid, a cone, a hip roof.

| Input | What it means |
|---|---|
| **mode** | *vector*: dragged · *to a point*: meets at an apex |
| **vector** | which way and how far; 1 m up by default |
| **point** | the apex (to a point) |
| **caps** | yes: a closed curve gives a closed body |

### Surface from points

![Surface from points](/images/manual/nodes/surface-from-points.png)

**What for.** A surface through points: a grid of points (rows × columns), or a loose cloud like the points of a land
survey.

| Input | What it means |
|---|---|
| **points** | in a grid (two levels) or loose |
| **mode** | *grid* or *cloud* (joined in triangles) |
| **smooth** | yes: curved between the points · no: flat facets |

**Tips.**
- A **cloud** gives flat triangles, which is right for a survey: between two measured heights nothing more is known.
  With **smooth**, each triangle curves, still passing exactly through every height.
- Shapes with sharp edges show small steps when smooth: use more points, or turn smooth off.

### NURBS Surface

![NURBS Surface](/images/manual/nodes/nurbs-surface.png)

**What for.** Full control of a free surface: a grid of control points that pull it, for shells and free skins.

| Input | What it means |
|---|---|
| **points** | the control points, rows × columns |
| **level u**, **level v** | which levels are rows and columns |
| **degree u**, **degree v** | `1`: facets · `2`: curves · `3`: smooth, up to `7` |
| **weights** | how much each point pulls |
| **closed u**, **closed v** | all the way round: a tube; in both, a torus |

### Revolve

![Revolve](/images/manual/nodes/revolve.png)

**What for.** A profile turning around an axis: a column, a dome, a vase, a tower.

| Input | What it means |
|---|---|
| **profile** | the half section that turns |
| **origin**, **axis** | a point on the axis and its direction (vertical by default) |
| **degrees** | how much it turns: `360` a full turn |

### Sweep

![Sweep](/images/manual/nodes/sweep.png)

**What for.** A profile running along a path without twisting: a handrail, a moulding, a curved beam, a tube.

| Input | What it means |
|---|---|
| **profile** | the section that runs |
| **path** | the curve it runs along |
| **path 2** | optional: a second path; the profile stretches to touch both |
| **place** | *where it is* (drawn at the start of the path) or *centred on the path* (drawn anywhere) |
| **rotation** | how many degrees it turns along the whole path |

### Network surface

![Network surface](/images/manual/nodes/network-surface.png)

**What for.** A surface through a network of curves in two directions: the ribs of a hull or of a free roof.

**How.** Connect one family of curves to **curves u** and the other to **curves v**; each curve of one family must
cross all those of the other.

### Edge surface

![Edge surface](/images/manual/nodes/edge-surface.png)

**What for.** A surface stretched between two, three or four edges that meet at the corners: a slab or a roof with
curved edges.

**How.** Connect the edges to **a**, **b**, **c** and **d**, in any order. With two, a ruled surface; with three, one
side closes into a point.

## Work on a surface

### Surface points

![Surface points](/images/manual/nodes/surface-points.png)

**What for.** Points on a surface, or the direction it faces there: to stand columns, anchors or pieces on it.

| Input | What it means |
|---|---|
| **what** | *points* or *normals* (where it faces) |
| **mode** | *lattice*: count u × count v from edge to edge · *centres*: the centre of each panel · *fractions*: at some u and v |
| **count u**, **count v** | how many along each direction |
| **u**, **v** | the fractions, several with `;` |

### Isocurves

![Isocurves](/images/manual/nodes/isocurves.png)

**What for.** The surface's own lines, in u or in v: ribs, mullions, a layout that follows the shape.

| Input | What it means |
|---|---|
| **direction** | *u* or *v* |
| **mode** | *parts* (spread evenly) or *fraction* (at some positions) |
| **count**, **positions** | how many, or where |

### Sub surface

![Sub surface](/images/manual/nodes/sub-surface.png)

**What for.** The piece of a surface between two fractions of u and two of v: a bay of a roof, a segment of a dome.

### Closest point on surface

![Closest point on surface](/images/manual/nodes/closest-point-on-surface.png)

**What for.** The point of a surface closest to each point: to bring something onto it, or to know its u and v there,
how far it is, or where the surface faces.

**How.** Connect the **points** and the **surface**, and choose what it **gives**: *point*, *u v*, *distance* or
*normal*.

### Curve on surface

![Curve on surface](/images/manual/nodes/curve-on-surface.png)

**What for.** A curve lying on a surface and following every bump: a path on a roof, a seam on a membrane.

**How.** Give points by their u and v, from **Closest point on surface** (*u v*) or with a **Point** where x is u and y
is v.

### Geodesic

![Geodesic](/images/manual/nodes/geodesic.png)

**What for.** The shortest path between two points over a surface, like a string pulled tight on it. Laths laid
along geodesics stay straight in their own plane: that is why gridshells use them.

| Input | What it means |
|---|---|
| **from**, **to** | the start and end points, one end for each start |
| **show** | *curves*, their *lengths*, the *crossings* (the knots of a gridshell) or the *bars* between crossings |

### Surface curvature

![Surface curvature](/images/manual/nodes/surface-curvature.png)

**What for.** To know whether a surface can be built from flat sheet, and how much it bends.

| Input | What it means |
|---|---|
| **what** | *Gaussian*: zero, made from flat sheet; positive, like a dome; negative, like a saddle · *mean*: how much it bends · *developable*: yes or no |
| **mode**, **count**, **u**, **v** | where, as in Surface points |

**Tips.**
- To see the curvature as colours on the surface, use the panel of the geometry (**Colour → by a value**).

### Flip surface

**What for.** To turn a surface the other way (its face), or to reverse or swap its u and v.

**Tips.**
- **Thicken** grows towards the face: flip it to grow the other way.

### Intersection

![Intersection](/images/manual/nodes/intersection.png)

**What for.** Where two geometries cross: two surfaces give the crossing curves; a curve and a surface, the points.

### Split surface

![Split surface](/images/manual/nodes/split-surface.png)

**What for.** A surface split into pieces by curves projected onto it: a perforated sheet and its offcuts.

| Input | What it means |
|---|---|
| **curves** | the curves that cut it, projected from **direction** (from above by default) |
| **what** | *all pieces* (largest first), *the largest* (the perforated sheet) or *the others* (the offcuts) |

### Boolean

![Boolean](/images/manual/nodes/boolean.png)

**What for.** To unite, subtract or intersect closed bodies: a wall minus its openings, two volumes in one skin.

| Input | What it means |
|---|---|
| **a**, **b** | closed bodies |
| **operation** | *union*, *difference* (a minus b) or *intersection* |

### Unroll

![Unroll](/images/manual/nodes/unroll.png)

**What for.** To flatten surfaces to cut them from a sheet of metal, board or fabric. A body with flat faces gives its
net, to cut and fold.

| Input | What it means |
|---|---|
| **what** | *unrolled* pieces, their *outlines* to cut, the *folds* of a net, or the *stretch* of a surface that is not developable |
| **place** | *in a row* or *in place* |
| **spacing** | between pieces |

**Tips.**
- A developable surface unrolls without stretching; one that is not, like a dome, unrolls approximately and says how
  much it stretches.

## Structures on a surface

### Diagrid

![Diagrid](/images/manual/nodes/diagrid.png)

**What for.** A grid of diagonal members on a surface, in diamonds: a tower, a dome, a roof.

| Input | What it means |
|---|---|
| **divisions u**, **divisions v** | diamonds along each direction |
| **what** | the *diagonals*, the *crossings* (nodes) or the *rings* through the nodes |
| **members** | *straight* or *curves* following the surface |
| **continuous** | yes: each diagonal from end to end as one member (a helix on a tower) |

**Tips.**
- With **Pipe** on the diagonals, the structure; with **Cap** on the rings, the floor slabs.

### Space frame

![Space frame](/images/manual/nodes/space-frame.png)

**What for.** A two-layer structure on a surface: the top chord on it, the bottom one shifted half a module and
lowered, and diagonals joining them in pyramids.

| Input | What it means |
|---|---|
| **divisions u**, **divisions v** | modules along each direction |
| **truss depth** | the distance between the two chords |
| **what** | all members, one chord, the diagonals, or the crossings above or below |

### Chebyshev net

![Chebyshev net](/images/manual/nodes/chebyshev-net.png)

**What for.** The way a mesh of laths settles when bent, or a fabric when it drapes: quadrilaterals with four equal
sides. For lath roofs and gridshells.

| Input | What it means |
|---|---|
| **u**, **v** | the starting point |
| **step** | the length of each side, between nodes |
| **count** | nodes on each side of the start |
| **angle**, **rotation** | the angle between the two starting laths, and their turn |
| **what** | all laths, one family, or the knots |

### Hypar

![Hypar](/images/manual/nodes/hypar.png)

**What for.** To fold each panel into a hyperbolic paraboloid: two opposite corners rise and the panel becomes a
saddle of straight lines, like paper folded along a diagonal.

| Input | What it means |
|---|---|
| **panels** | four-corner panels: a Grid, rectangles |
| **lift** | how much two opposite corners rise, in metres |
| **corners** | which two corners rise |
| **show** | the *folded piece*, the *flat piece* to cut, the *fold* or the *longest edge* |

### Ribs

![Ribs](/images/manual/nodes/ribs.png)

**What for.** To cut a shape into parallel boards closed against a wall: a rib wall, a slatted ceiling, a sliced
bench. See [Draw the form, then cut it](/manual/key-ideas/draw-then-cut/).

| Input | What it means |
|---|---|
| **shape** | a surface, a mesh or a volume |
| **count**, **weight** | how many ribs, and their thickness |
| **cuts** | *x*, *y*: vertical ribs · *z*: horizontal slices |
| **back** | where the back wall is |

### Surface morph

![Surface morph](/images/manual/nodes/surface-morph.png)

**What for.** To cover a surface with a module: the surface is divided into cells that follow its curve, and the
module is fitted into each one, bending with it.

| Input | What it means |
|---|---|
| **geometry** | the module, drawn anywhere; empty: the cells themselves |
| **count u**, **count v** | cells along each direction |
| **height** | how far the top of the module rises from the surface |

### Pipe

![Pipe](/images/manual/nodes/pipe.png)

**What for.** A member along each curve: round (railings, cables), rectangular (beams, mullions) or with a profile
you draw (an I, an L).

| Input | What it means |
|---|---|
| **section** | *round*, *rectangular* or *profile* |
| **radius**, **sides** | for round sections |
| **width**, **height** | for rectangular ones |
| **profile** | a curve drawn around the origin, in plan |
| **rotation**, **caps** | turn the section; close the ends |

### Pipes

![Pipes](/images/manual/nodes/pipes.png)

**What for.** A pipe around each line, all fused into one skin with smooth fillets at the nodes: a single sculptural
structure.

| Input | What it means |
|---|---|
| **radius** | of the pipes |
| **fillet** | how much the nodes are filled; `0`: none |
| **detail** | more is finer and slower |
