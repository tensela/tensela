---
title: Formas
description: Rectángulo, Caja, Prisma, Esfera, Puntos al azar y Caja envolvente, el punto de partida de casi todos los diseños.
---

Las formas son el punto de partida de casi todos los diseños: una fachada, un terreno, un bloque, un quiebrasol. En
el lienzo son azules.

**Cada entrada acepta varios valores.** Un Rectángulo con **ancho** `4; 6; 8` da tres rectángulos, y un Prisma cuyo
**alto** viene de una Serie de 5 pisos da cinco volúmenes. Mira [Listas con nombre](/es/manual/key-ideas/named-lists/).

## Rectángulo

![Rectángulo](/images/manual/nodes/rectangle.png)

**Para qué.** Una fachada, un terreno, una losa, una plancha para cortar: la base de muchos diseños.

**Cómo.** Escribe su **ancho** y su **alto** y elige el **plano**: *planta* para un piso o un terreno, *alzado* para
una fachada.

**Qué hace.**

| Entrada | Qué quiere decir |
|---|---|
| **ancho** | el lado horizontal: en X (en Y si es *lateral*) |
| **alto** | el otro lado: norte-sur en planta, hacia arriba en alzado |
| **origen** | dónde está su esquina inferior izquierda (`0 0 0` de fábrica) |
| **plano** | *planta* (acostado), *alzado* (de pie, mirando al sur) o *lateral* (de pie, mirando al este) |

**Trucos.**
- Un rectángulo es un contorno plano, no un cuerpo: tiene área pero no volumen. **Extrúyelo** con tapas para tener
  un volumen.
- Pártelo en paneles con una **Retícula**, como en [Tu primer proyecto](/es/manual/getting-started/first-project/).

## Caja

![Caja](/images/manual/nodes/box.png)

**Para qué.** Un quiebrasol, una viga, un ladrillo, un bloque que repites muchas veces.

**Cómo.** Escribe su **ancho**, su **fondo** y su **alto**, y después llévala donde quieras con **Colocar** o
**Mover**.

**Qué hace.**

| Entrada | Qué quiere decir |
|---|---|
| **ancho** | en X |
| **fondo** | en Y |
| **alto** | en Z, hacia arriba |

**Trucos.**
- Una Caja está **centrada en el origen**, así que cuando **Colocar** la gira, gira sobre su propio centro: justo lo
  que necesita un quiebrasol.
- Para un edificio que se apoya en una esquina, usa mejor un **Prisma**.

## Prisma

![Prisma](/images/manual/nodes/prism.png)

**Para qué.** El volumen de un edificio, una torre, una manzana de un plan maestro.

**Cómo.** Escribe su **ancho** (este-oeste), su **fondo** (norte-sur) y su **alto**. El **origen** es su esquina
inferior sur-oeste.

**Qué hace.**

| Entrada | Qué quiere decir |
|---|---|
| **ancho** | este-oeste, en X |
| **fondo** | norte-sur, en Y |
| **alto** | hacia arriba |
| **origen** | la esquina inferior sur-oeste |

**Trucos.**
- Pide sus caras **por nombre** con **Caras**: *sur*, *este*, *norte*, *oeste*, *techo*, *base*, o todas las
  *fachadas* a la vez. Después parte una fachada con una **Retícula** para ponerle paneles.
- **Caras** también funciona con una **Caja**.

## Esfera

![Esfera](/images/manual/nodes/sphere.png)

**Para qué.** Una cúpula, un volumen de referencia, una zona hecha visible.

**Cómo.** Escribe su **centro** y su **radio**.

**Qué hace.**

| Entrada | Qué quiere decir |
|---|---|
| **centro** | el punto del medio (`0 0 0` de fábrica) |
| **radio** | en metros |

**Trucos.**
- Varios radios dan varias esferas alrededor del mismo centro.

## Puntos al azar

![Puntos al azar](/images/manual/nodes/random-points.png)

**Para qué.** Árboles en un terreno, perforaciones dispersas en un panel, personas en una plaza, las semillas de un
Voronoi.

**Cómo.** Conecta una **región**, una caja, un prisma o un rectángulo, y escribe cuántos puntos quieres.

**Qué hace.**

| Entrada | Qué quiere decir |
|---|---|
| **región** | dónde caen los puntos: dentro de un volumen, o sobre un rectángulo en planta o en alzado |
| **cantidad** | cuántos puntos |
| **semilla** | la misma semilla da siempre los mismos puntos; otra semilla, otra distribución |
| **nivel** | el nombre de la lista de puntos (`punto` de fábrica) |

**Trucos.**
- Prueba algunas **semillas** hasta que te guste la distribución: no vuelve a cambiar a menos que cambies la semilla.
- Conecta los puntos a un **Voronoi** para convertirlos en celdas.

## Caja envolvente

![Caja envolvente](/images/manual/nodes/bounding-box.png)

**Para qué.** Saber qué tamaño tiene algo y dónde está, o hacer la celda que deforma una geometría con
**Encajar módulo**.

**Cómo.** Conecta la **geometría** que quieres envolver.

**Qué hace.**

| Entrada | Qué quiere decir |
|---|---|
| **geometría** | lo que se envuelve |
| **de** | *todos*: una caja alrededor de todo · *cada uno*: una caja alrededor de cada elemento |

**Trucos.**
- Con **Encajar módulo**, mueve las esquinas de la caja y la geometría de adentro la sigue: una forma rápida de
  afinar o torcer una forma.
