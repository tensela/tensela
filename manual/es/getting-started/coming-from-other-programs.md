---
title: Si vienes de otro programa
description: Si usas Grasshopper, Dynamo o Geometry Nodes, qué se mantiene y qué cambia.
---

Si ya diseñas con nodos, te vas a sentir en casa rápido: un lienzo, tarjetas, cables, números que cambian el
modelo en vivo. Esta página cuenta lo que cambia, para que no busques cosas que aquí funcionan distinto.

## La gran diferencia: listas con nombre

En otros programas, los datos **se acomodan** antes de combinarlos: árboles con ramas numeradas, listas dentro de
listas, elegir cómo se emparejan dos listas. En Tensela cada lista lleva un **nombre**, su nivel: *piso*, *vano*,
*panel*. Cuando un nodo recibe dos listas, mira sus nombres:

- **el mismo nombre:** van uno con uno, el primero con el primero, el segundo con el segundo;
- **nombres distintos:** se combinan todos con todos.

No hay ramas que aplanar, injertar ni transponer. Lee [Listas con nombre](/es/manual/key-ideas/named-lists/) para
la idea completa, con ejemplos, y [Las listas en Tensela, Grasshopper y Dynamo](/es/manual/theory/lists-compared/)
para ver las mismas tareas hechas en las tres herramientas.

## Si vienes de Grasshopper

Grasshopper es una herramienta de programación visual dentro de Rhino. Tensela funciona sola, sin Rhino.

| En Grasshopper | En Tensela |
|---|---|
| Number Slider | **Número** (un deslizador en la tarjeta) |
| Expression | **Fórmula** |
| Script de Python o C# | **Código** (Python, que corre aparte y con límites) |
| Panel | **Info** |
| Divide Curve | **Puntos de curva** |
| Nurbs Curve | **Curva NURBS** |
| Series | **Serie** |
| Graft, Cross Reference | nada: las listas con nombres distintos se combinan solas |
| Flip Matrix | nada: los niveles tienen nombre, no orden |
| Simplify, Shift Paths | nada: no hay caminos |
| Shift List, Relative Item | **Reordenar**, desplazar, sobre un nivel |
| Cull Pattern, Cull Nth | **Filtrar**, patrón o uno de cada *n* |
| List Item, Sub List | **Elegir** |
| Partition | **Partir** |
| Merge | **Unir listas** (una detrás de la otra) |
| Entwine | **Juntar** (lado a lado, con un nivel nuevo) |
| Flatten | **Unir niveles** |

## Si vienes de Dynamo

Dynamo es una herramienta de programación visual para Revit. Trabaja con elementos BIM: muros, losas, familias.
Tensela no es BIM: hace la geometría, y tú la llevas a tu programa BIM como OBJ o DXF.

| En Dynamo | En Tensela |
|---|---|
| Lacing: más corta | listas con el mismo nombre |
| Lacing: producto cruzado, guías de replicación | listas con nombres distintos |
| Niveles de lista (`@L1`, `@L2`) | el nivel, elegido por su nombre |
| List.Transpose | nada: los niveles tienen nombre, no orden |
| List.ShiftIndices | **Reordenar**, desplazar |
| List.FilterByBoolMask, List.TakeEveryNthItem | **Filtrar** |
| List.GetItemAtIndex, List.Slice | **Elegir** |
| List.Chop | **Partir** |
| List.Join | **Unir listas** |
| List.Create | **Juntar** |
| List.Flatten | **Unir niveles** |

## Si vienes de Geometry Nodes

Geometry Nodes es parte de Blender, un programa 3D completo. Sus nodos construyen cualquier contenido 3D, desde
escenas hasta efectos. Tensela es solo para diseñar con reglas, y habla el idioma de la arquitectura: fachadas,
pisos, vanos, quiebrasoles, planchas para cortar. Lo que haces lo puedes llevar a Blender como OBJ.

---

*Rhino y Grasshopper son marcas de Robert McNeel & Associates. Dynamo y Revit son marcas de Autodesk. Blender es
una marca de la Blender Foundation. Tensela no está asociada con ellos.*
