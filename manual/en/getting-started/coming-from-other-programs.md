---
title: Coming from other programs
description: If you use Grasshopper, Dynamo or Geometry Nodes, what stays the same and what changes.
---

If you already design with nodes, you will feel at home quickly: a canvas, cards, cables, numbers that change the
model live. This page tells you what changes, so you do not look for things that work differently here.

## The biggest difference: lists with names

In other programs, the data is **arranged** before combining it: trees with numbered branches, lists inside lists,
choosing how two lists are matched. In Tensela every list carries a **name**, its level: *floor*, *bay*, *panel*. When a
node gets two lists, it looks at their names:

- **same name:** they go one with one, the first with the first, the second with the second;
- **different names:** every one is combined with every other one.

There are no branches to flatten, graft or transpose. Read [Lists with names](/manual/key-ideas/named-lists/) for
the full idea, with examples, and [Lists in Tensela, Grasshopper and Dynamo](/manual/theory/lists-compared/) for the
same tasks done in the three tools.

## If you come from Grasshopper

Grasshopper is a visual programming tool inside Rhino. Tensela works on its own, without Rhino.

| In Grasshopper | In Tensela |
|---|---|
| Number Slider | **Number** (a slider on the card) |
| Expression | **Formula** |
| Python or C# script | **Code** (Python, running apart and with limits) |
| Panel | **Info** |
| Divide Curve | **Points on curve** |
| Nurbs Curve | **NURBS Curve** |
| Series | **Series** |
| Graft, Cross Reference | nothing: lists with different names are combined by themselves |
| Flip Matrix | nothing: levels have names, not an order |
| Simplify, Shift Paths | nothing: there are no paths |
| Shift List, Relative Item | **Reorder**, shift, on one level |
| Cull Pattern, Cull Nth | **Filter**, pattern or one every *n* |
| List Item, Sub List | **Pick** |
| Partition | **Split** |
| Merge | **Merge lists** (one after the other) |
| Entwine | **Merge** (side by side, with a new level) |
| Flatten | **Join levels** |

## If you come from Dynamo

Dynamo is a visual programming tool for Revit. It works with BIM elements: walls, floors, families. Tensela is not
BIM: it makes the geometry, and you take it to your BIM program as OBJ or DXF.

| In Dynamo | In Tensela |
|---|---|
| Lacing: shortest | lists with the same name |
| Lacing: cross product, replication guides | lists with different names |
| List levels (`@L1`, `@L2`) | the level, chosen by its name |
| List.Transpose | nothing: levels have names, not an order |
| List.ShiftIndices | **Reorder**, shift |
| List.FilterByBoolMask, List.TakeEveryNthItem | **Filter** |
| List.GetItemAtIndex, List.Slice | **Pick** |
| List.Chop | **Split** |
| List.Join | **Merge lists** |
| List.Create | **Merge** |
| List.Flatten | **Join levels** |

## If you come from Geometry Nodes

Geometry Nodes is part of Blender, a complete 3D program. Its nodes build any kind of 3D content, from scenes to
effects. Tensela is only for design with rules, and it speaks the language of architecture: facades, floors, bays,
sun fins, sheets for cutting. You can send what you make to Blender as OBJ.

---

*Rhino and Grasshopper are trademarks of Robert McNeel & Associates. Dynamo and Revit are trademarks of Autodesk.
Blender is a trademark of the Blender Foundation. Tensela is not associated with them.*
