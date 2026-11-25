---
title: Dibuja la forma y después córtala
description: La forma más fácil de lograr casi cualquier diseño, antes de aprender a armarlo punto por punto.
---

## Para qué

Para llegar a una forma compleja, un muro de costillas, una cubierta waffle, un pabellón rebanado, con **pocos nodos
y sin fórmulas**.

## Cómo

En vez de calcular cada punto de la forma, **dibuja primero la forma y córtala después**:

1. **Dibuja la forma** con unas pocas curvas y una superficie que pase por ellas, por ejemplo una **Superficie por
   secciones** por tres o cuatro curvas.
2. **Córtala** con **Costillas**, que la rebana en tantas tablas como pidas, con el grosor que le des.

Un muro de costillas hecho así lleva unos seis nodos. Cambias las curvas y todas las costillas las siguen.

![Dibuja la forma, córtala, acuesta las piezas](/images/manual/diagrams/draw-then-cut-es.svg)

## Qué hace

- **Costillas** corta la superficie con planos paralelos y cierra cada costilla contra un plano de atrás, la pared.
  La entrada **espalda** dice a qué distancia está ese plano: con `0`, cada costilla va desde la forma hasta el eje;
  con más, cada costilla deja un respaldo recto.
- La misma idea sirve para fabricar: **Secciones** corta un cuerpo en rebanadas que después acuestas en planchas.

## Cuándo ir más allá

Armar la forma **punto por punto**, con Series, un Punto y una Fórmula o una Gráfica, da control total sobre cada
costilla. Es el paso siguiente, y una muy buena manera de aprender [Listas con
nombre](/es/manual/key-ideas/named-lists/). Empieza dibujando y cortando; ve punto por punto cuando lo necesites.
