---
title: Simulation
description: Shapes that find themselves under their weight, a first check of bars, and where the material should go.
---

Simulation lets the forces draw the shape, or tells you how hard a structure works. These nodes are rose on the
canvas. Forces are in newtons: 1 kg weighs about 10 N, 1 kN is 1000 N.

## Equilibrium

![Equilibrium](/images/manual/nodes/equilibrium.png)

**What for.** The shape a cable, a net, a membrane or a shell takes at rest, hanging from its supports or lying on a
floor, under its weight and its loads: the form finding of hanging models, cable nets, tensile fabrics, soap films
and shells. Turned upside down, the vault that works mainly in compression.

**How.** Connect what hangs to **shape**: curves (cables) or a mesh (a membrane, from **Mesh surface**). It always
gives the shape already at rest: change a support or a load and it hangs again.

| Input | What it means |
|---|---|
| **shape** | curves or lines (cables) or a mesh (a membrane) |
| **spans** | into how many spans each curve is divided; a mesh keeps its own |
| **supports**, **more supports** | *ends or corners*, the whole *border*, the *start*, or *none*; and points that also hold it |
| **self weight** | of all of it, in N |
| **loads**, **load** | points where a load hangs, and how much |
| **stiffness** | the force that would stretch it to twice its length: more, it stretches less |
| **rest length** | how long each span wants to be: `1` elastic, less pre-tensioned, `0` a soap film |
| **diagonals** | none, a cable net; one or both per square, a sheet that keeps its shape |
| **bending** | `0` a cable or a cloth; `0.001` rubber; `0.01` or more, a shell |
| **floor** | the height of a floor it rests on; with a floor it needs no supports |
| **ties** | lines whose ends are pulled together, as stitches (a gather, a pleat) |
| **gravity** | where the weight goes; upwards gives the shape that works in compression |
| **moment** | `1` at rest, `0` the start: the ▶ of the panel plays it |
| **show** | the *shape*, the *spans*, their *elongation* or their *forces* |

**Tips.**
- Supports can be moved by hand in the 3D view with **Move supports**: the shape follows.
- The forces are for finding the shape, not for sizing cables or membranes.

## Bar analysis

![Bar analysis](/images/manual/nodes/bar-analysis.png)

**What for.** How much a structure of bars bends and how hard each bar works: beams, columns, porticos, trusses,
gridshells. A first sizing: it does not check buckling nor the joints, and applies no safety factors or building
codes: an approximation for design, to be checked by a structural engineer.

| Input | What it means |
|---|---|
| **shape** | the bars: lines, curves or a mesh (each edge a bar) |
| **diagonals** | of each square of a mesh: none (a frame) or braced like a truss |
| **supports**, **support** | points held, and how: *clamped*, *pinned* or *roller* |
| **loads**, **load**, **load per metre** | point loads, and a load spread along every bar (a slab, snow) |
| **self weight** | add the weight of the bars |
| **material** | steel, timber, glulam, concrete or aluminium |
| **section** | `IPE 300`, `HEA 200`, `rect 200x400`, `tube 200x100x8`, `pipe 168x8`… in mm |
| **show** | the *deformed* shape, *displacements*, *axial forces*, *moments*, *utilization*, *reactions*, the *largest* of each, or the *total weight* |

**Tips.**
- **Utilization** above 1 (100 %) means the bar is too weak: a larger section, or more support. Below 1 is not a
  guarantee: it is a first check.

## Topology optimization

![Topology optimization](/images/manual/nodes/topology-optimization.png)

**What for.** Where the material should be, inside a region, to carry some loads to some supports with the least of
it. It starts full and thin, and turn after turn the material goes where it works, until a structure is left: the
arches and diagonals of a beam, the legs of a bridge. A form study: the result still has to be designed and checked
as a structure.

| Input | What it means |
|---|---|
| **region** | where the material can go: an outline (2D) or a body (3D) |
| **voids**, **solid parts** | what must stay empty (a door) or full (a slab) |
| **supports**, **rollers** | points or outlines held in every direction, or only along the weight |
| **loads**, **load** | where a force is applied, and how much |
| **density** | how much of the region stays full: `0.3` leaves 30 % |
| **resolution** | cells along the longer side: more, finer and slower |
| **show** | the *shape* (outlines to extrude or cut), the *plate*, the *cells*, the *density*, the *stress*… |
