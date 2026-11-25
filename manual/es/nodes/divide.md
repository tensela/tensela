---
title: Dividir
description: Retícula, Dividir, Voronoi, Centro, Caras, Vértices, Aristas, y los nodos que eligen, parten, reordenan y unen listas.
---

Dividir es donde una cosa se vuelve muchas: una fachada en paneles, una caja en sus caras, una lista en grupos. Estos
nodos son ocre en el lienzo.

## Retícula

![Retícula](/images/manual/nodes/grid.png)

**Para qué.** Para dividir un rectángulo o una superficie curva en paneles: filas y columnas, rombos, hexágonos o
triángulos.

**Cómo.** Conecta el **rectángulo** (o una superficie) y di cómo dividirlo: por número (**columnas**, **filas**) o
por medida (**ancho celda**, **alto celda**).

| Entrada | Qué quiere decir |
|---|---|
| **rectángulo** | un rectángulo, o una superficie curva |
| **columnas**, **filas** | cuántas, o los cortes como fracciones (`0; 0,2; 0,5; 1`: disparejos) |
| **ancho celda**, **alto celda** | la medida de cada celda, en vez de cuántas |
| **nivel filas**, **nivel columnas** | los nombres de las dos listas (*fila* y *columna* de fábrica) |
| **forma** | *cuadrados*, *rombos*, *hexágonos* (un panal), *triángulos*, o *remates de rombos* (los triángulos que completan el borde) |
| **paneles** | sobre una superficie curva: *planos* (cuatro esquinas) o *curvos* (siguen la superficie) |

**Trucos.**
- Los cortes disparejos pueden venir de otro nodo: una **Fórmula** da celdas que crecen.
- El cable dice `fila 12 × columna 20 = 240`: todo lo que viene después de la Retícula trabaja con todos los paneles
  a la vez.

## Dividir

![Dividir](/images/manual/nodes/divide.png)

**Para qué.** Para dividir un rectángulo en partes en una sola dirección: vanos a lo ancho de una fachada, franjas de
un piso.

| Entrada | Qué quiere decir |
|---|---|
| **rectángulo** | lo que se divide |
| **partes** o **medida** | cuántas partes, o la medida de cada una |
| **dirección** | a lo *ancho* o a lo *alto* |
| **nivel** | el nombre de la lista nueva (*parte* de fábrica) |

## Voronoi

![Voronoi](/images/manual/nodes/voronoi.png)

**Para qué.** Celdas alrededor de semillas: cada semilla se queda con la parte del plano más cerca de ella que de
cualquier otra. Pieles orgánicas, pavimentos, perforaciones, la planta de un parque.

| Entrada | Qué quiere decir |
|---|---|
| **puntos** | las semillas |
| **borde** | una curva cerrada que contiene las celdas; vacío: un rectángulo un poco más grande que las semillas |
| **radio** | ninguna celda pasa de esta distancia a su semilla: se redondean y dejan huecos |
| **nivel** | el nombre de la lista de celdas (*celda* de fábrica) |

**Trucos.**
- Semillas de **Puntos al azar** dan un aspecto natural; cambia la semilla hasta que te guste.
- Con **Vértices**, **Centro** y **Delaunay**, una pirámide en cada celda: una piel Voronoi.

## Voronoi 3D

![Voronoi 3D](/images/manual/nodes/voronoi-3d.png)

**Para qué.** Lo mismo en un volumen: cada punto se queda con el espacio más cerca de él. Cada celda es un poliedro.

| Entrada | Qué quiere decir |
|---|---|
| **puntos**, **región** | las semillas, y el volumen que se divide |
| **nivel**, **nivel caras** | los nombres de las celdas y de las caras de cada celda |

## Centro

![Centro](/images/manual/nodes/centre.png)

**Para qué.** El centro de cada elemento: donde poner un quiebrasol, una lámpara, un rótulo, una columna.

## Caras

![Caras](/images/manual/nodes/faces.png)

**Para qué.** Las caras de un prisma o una caja, por nombre, como rectángulos: para poner paneles en la fachada sur,
o paneles solares en el techo.

| Entrada | Qué quiere decir |
|---|---|
| **volumen** | un Prisma o una Caja |
| **cuáles** | *sur*, *este*, *norte*, *oeste*, *techo*, *base*, o *fachadas* (las cuatro) o *todas* |
| **nivel** | el nombre de la lista nueva (*cara* de fábrica) |

## Vértices

![Vértices](/images/manual/nodes/vertices.png)

**Para qué.** Las esquinas de cada elemento, como puntos: las 8 esquinas de una caja, las esquinas de cada panel.

## Aristas

![Aristas](/images/manual/nodes/edges.png)

**Para qué.** Los bordes de cada elemento, como líneas: las 12 aristas de una caja, el marco de cada panel.

## Elegir

![Elegir](/images/manual/nodes/pick.png)

**Para qué.** Para tomar elementos de una lista por su número, contando desde `0`: la fila 4, el último piso, los
puntos 1, 5 y 3, del 2 al 5.

| Entrada | Qué quiere decir |
|---|---|
| **dato** | la lista |
| **nivel** | qué nivel; vacío: el único |
| **posición** | `4` · `último` · `-1` (el último) · `1; 5; 3` · `2-5` (del 2 al 5) |

## Partir

![Partir](/images/manual/nodes/split.png)

**Para qué.** Para partir los elementos de una lista en grupos: paneles de a cuatro, una fachada en tres partes.

| Entrada | Qué quiere decir |
|---|---|
| **dato**, **nivel** | la lista y qué nivel |
| **modo** | *grupos de*: tantos a la vez · *en partes*: en tantos grupos iguales |
| **cantidad** | cuántos por grupo, o cuántos grupos |
| **nivel nuevo** | el nombre de los grupos: *tramo*, *módulo*, *piso* |

**Trucos.**
- Para partir en dos en un punto, usa **Elegir** con dos rangos: `0-3` y `4-último`.

## Reordenar

**Para qué.** Para cambiar el orden de una lista: al revés, corrida unos puestos, o de menor a mayor según un valor.

| Entrada | Qué quiere decir |
|---|---|
| **dato**, **nivel** | la lista y qué nivel; vacío en una curva: invierte su sentido |
| **modo** | *invertir*, *desplazar* u *ordenar* |
| **cantidad** | cuántos puestos se corre (negativo, hacia el otro lado) |
| **dar la vuelta** | sí: lo que sale por un extremo vuelve por el otro · no: se pierde |
| **clave** | el número por el que se ordena (una distancia, una altura); vacío: los valores mismos |

**Trucos.**
- **Desplaza** en uno y compara cada piso con el de arriba: el *vecino*.

## Unir niveles

**Para qué.** Para unir dos niveles en uno, en orden: *triángulo 4 × vértice 3* se vuelve *vértice 12*. Para dibujar
una curva por todos los puntos, o numerarlos en fila.

| Entrada | Qué quiere decir |
|---|---|
| **dato** | la lista |
| **primero** | el nivel de afuera; vacío: el primero |
| **segundo** | el nivel que va adentro; vacío: el último |
| **nivel nuevo** | el nombre del nivel unido; vacío: el del segundo |

**Trucos.**
- **Partir** en grupos lo deshace.
