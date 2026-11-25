---
title: Curvas y superficies NURBS
description: Puntos de control que tiran como imanes, el grado, los pesos y los nudos.
---

Una **NURBS** es una curva o superficie suave definida por unos pocos números. Es la forma habitual de describir
formas libres con precisión: un pasamanos, el borde de una losa, una cáscara.

## Puntos de control

![Una curva NURBS de grado 3 y sus puntos de control](/images/manual/diagrams/nurbs-es.svg)

La curva **no** pasa por sus puntos de control (solo, por lo general, por el primero y el último): **la tiran
como imanes**. Esa es la diferencia con **Curva por puntos**, que pasa por cada punto. El polígono de los puntos de control es una buena guía de la forma: la curva lo
sigue, suavizado.

## Grado

Qué tan suave y tensa es la curva: `1` es el mismo polígono de control, `2` hace arcos, `3` es la curva suave de
siempre, y más es más tensa. Una curva necesita al menos un punto de control más que su grado.

## Pesos

Cuánto tira cada punto de control. Lo que cuenta es la diferencia entre ellos: todos en `2` es lo mismo que todos en
`1`. Con los pesos justos, una NURBS dibuja un círculo exacto, cosa que una curva polinómica sola no puede.

## Nudos

Cómo se reparte la curva entre sus puntos de control: parejo, por distancia, o a mano. Repetir un nudo hace un
quiebre. Solo hacen falta para afinar una curva.

## Superficies: u y v

Una superficie NURBS es lo mismo en dos direcciones: una retícula de puntos de control, filas por columnas, con un
grado en cada dirección. Sus dos direcciones son **u** (a lo largo de las filas) y **v** (a lo largo de las columnas),
cada una de `0` a `1`. Cada punto de la superficie tiene su u y su v, que es como los nodos piden *un punto en el
medio* o *las curvas en u*.

## Juzgar una curva

El **peine de curvatura** muestra si una curva es buena: puntas sin saltos es una curva suave; un salto, un cambio
brusco; un pico, una esquina.
