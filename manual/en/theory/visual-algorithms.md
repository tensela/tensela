---
title: Visual algorithms
description: What an algorithm is, why drawing it as nodes helps an architect, and where parametric design comes from.
---

## An algorithm is a recipe

An **algorithm** is a list of steps that, followed in order, always gives a result: a recipe. It does not need a
computer. *Take a rectangle of 20 × 12 m, divide it into panels of 1 m, put a sun fin on the centre of each panel*
is already an algorithm.

![The same algorithm as a recipe, as code and as nodes](/images/manual/diagrams/visual-algorithm-en.svg)

The same recipe can be written in three ways. In words, anyone understands it but no machine runs it. In code, a
machine runs it but you need to learn a language to read it. A **visual algorithm** draws it as nodes and cables:
it reads like the recipe and runs like the code.

## What a visual algorithm is

A visual algorithm is a **graph**: a set of nodes joined by cables.

- **A node is a function:** it receives some inputs and gives one result. A Grid receives a rectangle and two
  sizes, and gives panels. It always gives the same result for the same inputs.
- **A cable is data:** it carries the result of one node to an input of another.
- **The data flow one way.** From the values you type, through the nodes, to the form. That is why the graph reads
  from left to right.
- **There are no loops.** A node cannot depend on its own result: Tensela refuses the cable that would close a
  circle, and says why. This is what makes the graph always give an answer, and what lets Tensela know exactly what
  to recalculate when something changes ([How a project is calculated](/manual/theory/the-engine/)).

### Repeating without loops

If there are no loops, how do you repeat a step 240 times? You do not: you give the step **a list of 240**, and it
works on all of them at once. This is what [lists with names](/manual/key-ideas/named-lists/) are for.

When a step really has to work on its own result (a fractal, a curve that subdivides, a growth), a
[group](/manual/key-ideas/groups/) can **repeat** itself a number of times: the loop is closed inside one card, with
a count, so it always ends.

## What makes it parametric

*Parametric* does not mean curved or complicated. It means that the design is described by its **parameters** (the
width, the number of floors, the angle) and by the **dependencies** between its parts: the panels depend on the
facade, the fins on the panels. Change a parameter and everything that depends on it follows.

The value is not in one form but in the **family of forms** the recipe can give: the same project makes a facade of
12 m or of 40 m, open or closed, and you choose among them by looking.

## Where it comes from

Designing with rules is much older than computers.

- **Antoni Gaudí** found the form of his vaults by hanging chains with weights and turning the model upside down:
  the form came out of gravity, not of a drawing. The node [Equilibrium](/manual/nodes/simulation/#equilibrium)
  does the same thing.
- **Frei Otto** studied soap films and hanging nets to find the forms of his tensile roofs, such as the Munich
  Olympic Stadium.
- **Luigi Moretti**, in Italy, spoke of *parametric architecture* in the middle of the 20th century, with studies of
  stadiums whose form came from parameters such as the view from each seat.
- **Ivan Sutherland's Sketchpad**, in 1963, was one of the first programs to draw with rules: lines that stay
  parallel, points that stay joined.
- In the late 2000s, **visual programming** reached architects, with tools such as Grasshopper and, later, Dynamo.
  Tensela comes from that tradition, and aims at a gentle learning curve.

## The mathematics behind

Each family of nodes rests on a piece of geometry. You do not need it to design, but it helps to know where things
come from:

- **Coordinates and vectors:** every point is three numbers, every direction an arrow.
  [Units and directions](/manual/theory/units-and-directions/).
- **Curves and surfaces:** control points that pull a smooth form. [NURBS](/manual/theory/nurbs/).
- **Curvature:** why some surfaces can be built with flat sheets and others cannot.
  [Curvature](/manual/theory/curvature/).
- **Meshes:** forms made of flat faces, the language of fabrication and simulation. [Meshes](/manual/theory/meshes/).
- **Forces and optimisation:** forms that find themselves, and the best value among many.
  [Form finding](/manual/theory/form-finding/).
