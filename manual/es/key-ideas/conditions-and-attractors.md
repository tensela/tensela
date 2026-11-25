---
title: Condiciones y atractores
description: Hacer cada pieza distinta a propósito, por distancia, por una regla o por un valor.
---

## Para qué

Para que cada panel, quiebrasol o costilla sea **distinto a propósito**: más grande cerca de una entrada, abierto
hacia el sol, cerrado desde cierto piso.

## Atractores

Un **Atractor** le da a cada elemento un valor según lo cerca que esté de unos puntos o curvas.

- **cerca:** el valor justo al lado del atractor (por ejemplo, `90` grados).
- **lejos:** el valor en el **alcance** o más allá (por ejemplo, `0`).
- **alcance:** hasta dónde llega el efecto, en metros. Vacío: hasta el elemento más lejano.
- **atractores:** uno o más puntos, o curvas: un camino, la orilla de un río, el borde de una plaza.
- **varios:** con varios atractores, manda el más cercano o sus efectos se suman.
- **curva:** cómo pasa de cerca a lejos: lineal, suave, acelerando o frenando.

![Un atractor: el valor va de cerca a lejos a lo largo del alcance](/images/manual/diagrams/attractor-es.svg)

Conecta lo que sale a lo que quieras variar: el **giro** de un Colocar, el **factor** de un Escalar, la
**distancia** de un Mover.

**Truco:** para ver qué hace el Atractor por dentro, arma lo mismo a mano una vez: una **Distancia** de cada elemento
al punto, y un **Remapear** de esa distancia al rango que quieres, con **limitar** encendido.

## Condiciones

- **Escoger** da **un resultado por elemento**, una cosa u otra: un panel abierto o uno cerrado.
- **Filtrar** **deja** solo los elementos que pasan, y saca los demás. Con **quitar: sí**, los que quedan se numeran
  de nuevo (0, 1, 2…); con **no**, los otros quedan en su lugar, vacíos.
- **Comparar** da un sí o un no por elemento: *a* es menor, mayor, igual o distinto de *b*. **Combinar condiciones**
  junta dos con *y* u *o*, o invierte una con *no*.

## Fórmulas en tu idioma

Una **Fórmula** funciona como una celda de hoja de cálculo, y entiende español e inglés, incluso mezclados:

- `si(a < 7; 3; a < 16; 4,5; 6)` es lo mismo que `if(a < 7, 3, a < 16, 4.5, 6)`.
- `y`, `o`, `no` o `and`, `or`, `not`.
- Los espacios no importan: `a/2` y `a / 2` son lo mismo.
