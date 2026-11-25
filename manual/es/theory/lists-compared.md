---
title: Las listas en Tensela, Grasshopper y Dynamo
description: Las mismas listas en tres herramientas, las mismas tareas hechas en cada una, y qué cambia con los nombres.
---

Si vienes de Grasshopper o de Dynamo, el cambio más grande es cómo se guardan y se combinan las listas. Esta página
pone las tres lado a lado, con los mismos 20 valores: 4 pisos por 5 vanos.

![Los mismos 20 valores en Grasshopper, Dynamo y Tensela](/images/manual/diagrams/lists-compared-es.svg)

## Grasshopper: un árbol de ramas numeradas

En Grasshopper los datos se guardan en un **árbol**. Cada rama tiene una **ruta** de números, como `{0;2}`, y guarda
una lista. Los 4 pisos son 4 ramas, cada una con una lista de 5 vanos.

- Cuando un componente recibe dos entradas, las empareja elemento por elemento y, de fábrica, repite el último
  elemento de la lista más corta (*longest list*).
- Para combinar **cada piso con cada vano** hay que cambiar antes la estructura: **Graft** a una de las listas (cada
  elemento a su propia rama), o usar **Cross Reference**.
- **Flatten**, **Graft**, **Simplify**, **Flip Matrix** y **Shift Paths** existen para darle otra forma al árbol
  antes de combinar.

Es muy potente y muy explícito: la forma del árbol la controlas tú, paso a paso.

## Dynamo: listas dentro de listas

En Dynamo los datos son **listas anidadas**: una lista de 4 pisos, cada uno una lista de 5 vanos.

- Cómo se combinan dos listas se elige en cada nodo con su **lacing**: *shortest*, *longest* o *cross product*.
- Las **replication guides** (`<1>`, `<2>`) y los **niveles de lista** (`@L1`, `@L2`) dicen sobre qué nivel de las
  listas anidadas trabaja un nodo.
- **List.Transpose** intercambia lo de adentro y lo de afuera.

## Tensela: un bloque con nombres

En Tensela los 20 valores son un solo bloque, `piso 4 × vano 5`. Los nombres deciden cómo se combina: el **mismo
nombre** va uno con uno, **nombres distintos** se cruzan. No hay árbol que acomodar ni lacing que elegir; la regla es
siempre la misma. Cómo funciona por dentro: [Las listas con nombre, por dentro](/es/manual/theory/named-lists-inside/).

## Las mismas tareas en las tres

| Tarea | Grasshopper | Dynamo | Tensela |
|---|---|---|---|
| Cada piso con cada vano | Graft a una entrada, o Cross Reference | lacing *cross product*, o `<1>` `<2>` | nombres distintos: solo |
| Cada piso con su propio valor | la misma estructura de árbol en los dos lados | lacing *shortest* o *longest* | el mismo nombre: solo |
| Invertir solo los pisos | Flip Matrix, Reverse List, Flip Matrix | List.Reverse en el nivel justo (`@L2`) | **Reordenar**, nivel *piso* |
| Intercambiar pisos y vanos | Flip Matrix | List.Transpose | nada que hacer: los niveles no tienen orden |
| El total de cada piso | Mass Addition en cada rama | Math.Sum en el nivel justo | **Resumir**, suma a lo largo de *vano* |
| Dos listas que no encajan | se repite el último elemento de la más corta | depende del lacing | un aviso con los dos tamaños |

## Lo que ganas, y lo que cambia

- **Ganas:** el cable dice lo que lleva (`piso 4 × vano 5`), la misma regla vale en todos los nodos, y una operación
  sobre un nivel dice cuál por su nombre. Un error de tamaños da un aviso con los dos tamaños.
- **Lo que cambia:** los niveles no tienen posición, así que no existe *el segundo nivel*: le pones nombre. Los datos
  irregulares, como más paneles abajo de una torre que arriba, se guardan como **niveles de tamaño variable**, y lo
  que saca un filtro deja **huecos**, así la retícula se sigue leyendo igual.

---

*Rhino y Grasshopper son marcas de Robert McNeel & Associates. Dynamo y Revit son marcas de Autodesk. Tensela no está
asociada con ellas.*
