---
title: Form finding and the best value
description: How Equilibrium finds the shape at rest, and how Find the best moves the sliders.
---

## Equilibrium: particles and springs

**Equilibrium** replaces a cable or a membrane by **particles** (points, each with a share of the weight) joined by
**springs**: each spring pulls or pushes in proportion to how much it is stretched from its rest length. Some
particles are supports and do not move. The particles move until every force balances.

The shape found this way carries its loads **only along the springs**, in tension or in compression. This is the
principle of the hanging models of Gaudí and of the tensile structures of Frei Otto: hang it, and turn it upside down
to get a vault that works only in compression.

Inside, it uses **dynamic relaxation**, the usual method for tensile structures: the particles move with the forces
that are out of balance, and each time their motion peaks, they stop and start again from there, until they rest.
The node always gives the shape already at rest.

## Find the best

**Find the best…** moves some sliders until a number given by a node reaches its minimum, its maximum or a value:
the least material, the most sun in winter, a given area.

- **Near** refines from where the sliders are: it tries a step up and a step down on each one, keeps what improves,
  and halves the steps when nothing improves. It finds the best value close to the start.
- **Over the whole range** keeps a population of candidates that cross and mutate, generation after generation,
  until the best stops improving. It explores more, and takes longer.

Both stay inside the ranges of the sliders and land on values the sliders can show.
