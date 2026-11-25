---
title: Cómo piensa Tensela
description: Cada valor es un bloque de números cuyas direcciones tienen nombre. De ahí viene el nombre Tensela.
---

## Bloques de números

Por dentro, en Tensela cada valor es un **bloque de números**: un número, una lista, una tabla, o un bloque con más
direcciones. Los 240 paneles de una fachada son un bloque `fila 12 × columna 20`; las esquinas de cada panel suman
una dirección más, `esquina 4`; sus coordenadas, otra más, `x y z`.

En matemática, un bloque de números con varias direcciones se llama **tensor**. Ese es el *ten* de Tensela.

![Tensor y tela: de dónde viene el nombre Tensela](/images/manual/diagrams/tensor-fabric-es.svg)

## Direcciones con nombre

Lo que hace distinto a Tensela es que cada dirección de un bloque tiene un **nombre**: su **nivel**. *Fila*,
*columna*, *piso*, *costilla*. Cuando un nodo combina dos bloques, los alinea por nombre:

- las direcciones con el **mismo nombre** van uno con uno;
- las direcciones con **nombres distintos** se cruzan, todas con todas.

El resultado tiene todas las direcciones de los dos. Esa es la *tela* de Tensela: dos listas son la urdimbre y la
trama, y cada cruce es una pieza. Mira [Listas con nombre](/es/manual/key-ideas/named-lists/).

## Por qué es rápido

Un nodo no va elemento por elemento: calcula **todo el bloque de una vez**. Mover 240 paneles, o 24 000, es una sola
operación sobre un bloque. Por eso una fachada de miles de piezas puede actualizarse mientras arrastras un
deslizador.

## Por qué no hay nada que acomodar

Como las direcciones tienen nombre y no orden, `fila × columna` y `columna × fila` son el mismo bloque. No hace falta
transponer, aplanar ni injertar listas antes de combinarlas: los nombres dicen cómo van juntas. Cuando dos listas con
el mismo nombre tienen tamaños distintos, un aviso lo dice en vez de adivinar.

## Para ir más lejos

- [Las listas con nombre, por dentro](/es/manual/theory/named-lists-inside/): la regla en código, los niveles de
  tamaño variable y los huecos.
- [Cómo se calcula un proyecto](/es/manual/theory/the-engine/): qué se recalcula cuando cambias algo.
- [Las listas en Tensela, Grasshopper y Dynamo](/es/manual/theory/lists-compared/): las mismas tareas en las tres.
