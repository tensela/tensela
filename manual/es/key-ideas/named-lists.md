---
title: Listas con nombre
description: Cada lista dice qué es, y su nombre decide cómo se combina con otras listas.
---

Esta es la idea más importante de Tensela. Cuando se entiende, lo demás se vuelve mucho más claro.

## Para qué

Para trabajar con **muchas cosas a la vez**, 16 pisos, 20 vanos, 320 paneles, sin acomodar los datos a mano antes
de combinarlos.

## La idea: hilos y cruces

Cada lista en Tensela lleva un **nombre**, su **nivel**: *piso*, *vano*, *panel*, *costilla*. Cuando un nodo recibe
dos listas, mira sus nombres:

- **Nombres distintos: todos con todos.** 16 pisos y 20 vanos dan 320 paneles, como los hilos de una tela: cada hilo
  vertical cruza a cada hilo horizontal, y cada cruce es una pieza.
- **El mismo nombre: uno con uno.** El primero con el primero, el segundo con el segundo. Dos listas de 16 pisos dan
  16 resultados, no 256.

![Los nombres distintos se cruzan; el mismo nombre va uno con uno](/images/manual/diagrams/named-lists-es.svg)

Eso es todo. No hay nada que aplanar, injertar ni transponer.

## Cómo

- Los nodos que hacen listas, como **Serie**, **Retícula**, **Puntos de curva** o **Partir**, tienen un campo para
  nombrar el nivel. Una Serie de 60 números con el nivel `costilla` quiere decir *estos 60 valores son 60 costillas*.
- **El nombre es libre.** Lo que importa es escribirlo **igual** donde quieres que las listas vayan uno con uno, y
  **distinto** donde quieres que se crucen.
- **Consejo:** usa el singular de lo que cuentas, *costilla*, *piso*, *panel*, porque se lee natural: *costilla 3*.

## Qué hace

- **El cable muestra la forma:** `costilla 60 × altura 60 = 3 600`.
- **Los niveles no tienen orden.** `piso × vano` y `vano × piso` son lo mismo.
- **Las operaciones se hacen sobre un nivel, por su nombre:** invertir los pisos, quedarse con un vano de cada dos,
  correr los pisos uno hacia arriba, partir en grupos de cuatro. **Reordenar**, **Filtrar**, **Elegir** y **Partir**
  preguntan qué nivel, por su nombre.
- **Si dos listas con el mismo nombre tienen tamaños distintos**, un aviso lo dice en vez de adivinar.

## Un ejemplo para probar

Haz dos **Series**: una de 5 números con el nivel `x` y otra de 5 con el nivel `y`, y conéctalas a un **Punto** (una
a x, la otra a y). Salen 25 puntos en un cuadrado: los nombres son distintos, así que se cruzan. Ahora ponles `x` a
las dos: salen 5 puntos en diagonal, porque van uno con uno.

## Para ir más lejos

Cómo se guarda y se combina una lista con niveles, con código: [Las listas con nombre, por
dentro](/es/manual/theory/named-lists-inside/). Las mismas tareas en Grasshopper y Dynamo: [Las listas en Tensela,
Grasshopper y Dynamo](/es/manual/theory/lists-compared/).
