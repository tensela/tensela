---
title: Common stumbles
description: What usually goes wrong at the start, and how to fix it.
---

Things that confused people while Tensela was being tested, so you do not have to find them out yourself.

## Installing and opening

- **It does not open with a double-click.** First check that it may run (step 2 of
  [Install](/manual/getting-started/install/)). Then open it from a terminal, `./Tensela-*.AppImage`, to read what it
  says. If it speaks of **FUSE**, your system lacks a library that AppImages use: install it (on Ubuntu 24.04 and
  newer `sudo apt install libfuse2t64`, before that `libfuse2`), or open Tensela without it with
  `./Tensela-*.AppImage --appimage-extract-and-run`.
- **The 3D view stays black, or the window closes as it opens.** It is the graphics: Tensela needs OpenGL 3.2 or newer
  (see [What you need](/manual/getting-started/requirements/#the-graphics)). Update your system; in a virtual
  machine, turn on its 3D acceleration.
- **The program is in another language.** **Preferences → General → Language**; it applies the next time you open
  Tensela.

## Writing numbers

- **Decimals:** `3.5` and `3,5` both work.
- **Several values:** always separated by a semicolon, `1.5; 2; 3`. With decimals, `0,0,1,5` cannot be read: write
  `0; 0; 1,5` or `0 0 1.5`.
- **A point:** `0 0 0`, `8 0 2.5` or `(0; 0; 1.5)`.
- **Units:** measures are in metres unless you change it in **Preferences → Units**. You can also type the unit with
  the number, `120 cm`, and Tensela converts it.

## In the card

- **Tab** jumps to the next value of the card.
- **Delete** inside a field erases letters, not the node.
- **An empty level** in Reorder, Filter or Split means *automatic*: the card says which level it took, for example
  `auto: point`.

## Common situations

- **Raising a point without typing coordinates:** use **Move** with a distance (it goes up by default), or **Line by
  direction**.
- **After Filter**, with **remove: yes** the elements that stay are numbered again from 0. With **no**, the others
  stay in their place, empty.
- **A curve with empty points** passes through the points that are there.
- **A rectangle is not a closed body**, so it has no volume. To measure a volume, extrude it with caps first.
- **Reliefs without formulas:** a guide curve, a **Distance** to it and a **Graph** to shape the answer.
- **A smooth surface with steps:** a smooth surface through a coarse grid of points shows small steps at sharp edges.
  Use more points, or turn **smooth** off for shapes with edges.

## When it goes slowly

- **Turn off the eyes** of the nodes you do not need to see: drawing thousands of pieces often takes longer than
  calculating them.
- **Try ideas with small counts** (fewer panels, fewer sections) and raise them at the end.
- **The heavy nodes** (Topology optimization, Equilibrium, Insolation) take longer the finer they work: lower the
  resolution, the spans or the number of panels you give them while you look for the form.

## When the view asks before drawing

If a node with its eye on makes more than 50 000 pieces (or 2 million points), a strip appears above the view:
**Show them** or **Turn off its eye**. It usually means a digit too many in a count, or two lists crossing by
mistake. Check the names of their levels.
