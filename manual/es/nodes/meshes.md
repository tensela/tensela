---
title: Mallas
description: Mallas a partir de puntos y caras, de superficies o de triángulos, y los nodos que las leen, unen, suavizan y modelan a mano.
---

Una malla es una superficie hecha de caras planas que comparten sus esquinas: triángulos, cuadriláteros. Es la forma
de construir con vidrio plano, paneles o chapa plegada, y la forma de modelar formas libres por subdivisión. Estos
nodos son cobre en el lienzo.

**Geometría y topología.** En una malla, los **puntos** dicen dónde están las esquinas (su geometría) y las **caras**
dicen cómo se unen (su topología). Mueves un punto y las caras lo siguen; el orden de las esquinas de una cara dice
cuál es su frente.

## Hacer una malla

### Malla de superficie

![Malla de superficie](/images/manual/nodes/mesh-surface.png)

**Para qué.** Una superficie como una sola malla de cuadriláteros que comparten sus esquinas. Sobre una superficie de
revolución o de traslación, los cuadriláteros salen planos: paneles que se pueden construir con vidrio plano.

| Entrada | Qué quiere decir |
|---|---|
| **superficie** | una superficie, o un rectángulo |
| **cantidad u**, **cantidad v** | caras a lo ancho y a lo alto |

### Delaunay

![Delaunay](/images/manual/nodes/delaunay.png)

**Para qué.** Unir puntos en triángulos lo más parejos posible, sin triángulos delgados: un terreno a partir de
puntos de levantamiento, una piel de triángulos, pirámides sobre las celdas de un Voronoi.

| Entrada | Qué quiere decir |
|---|---|
| **puntos** | los puntos que se unen; con otros niveles, un grupo por cada uno |
| **más** | opcional: un punto que se suma a cada grupo, como el centro levantado de una celda para hacer una pirámide |

### Malla

**Para qué.** Una malla escrita a mano, a partir de sus esquinas y sus caras: para entender las mallas, o para armar
una pieza precisa.

| Entrada | Qué quiere decir |
|---|---|
| **puntos** | las esquinas, numeradas desde 0 en orden |
| **caras** | las esquinas de cada cara, `;` entre caras: `0 1 2; 2 1 3` (dos triángulos), `0 1 2 3` (un cuadrilátero) |

**Trucos.**
- Escribe las esquinas de cada cara contra reloj, vista desde el frente.

### Unir mallas

![Unir mallas](/images/manual/nodes/join-meshes.png)

**Para qué.** Todo lo que tiene caras como una sola malla. Soldadas, las caras que se tocan comparten sus esquinas y
quedan en una sola pieza, que es lo que necesita el suavizado.

| Entrada | Qué quiere decir |
|---|---|
| **a … h** | mallas, o cualquier cosa con caras: cajas, paneles, marcos, superficies |
| **soldar** | sí: las esquinas que se tocan se vuelven una |
| **caras dobles** | *dejar* o *quitar*: quitarlas deja de un grupo de cajas solo su piel exterior |

**Trucos.**
- Donde los bordes de dos partes no coinciden esquina con esquina (un nodo en T), no se sueldan. **Aristas de malla**
  con *libres* muestra esas costuras.

## Cambiarla

### Suavizar malla

![Suavizar malla](/images/manual/nodes/smooth-mesh.png)

**Para qué.** Una malla suave a partir de una simple: modela la forma con pocas caras y deja que los niveles la
redondeen. Una mesa, un pabellón, una forma libre.

| Entrada | Qué quiere decir |
|---|---|
| **método** | *Catmull-Clark* (cualquier cara; se vuelven cuadriláteros) o *Loop* (triángulos) |
| **niveles** | cuántas veces se subdivide: cada nivel, unas cuatro veces las caras |
| **borde** | *suave*, *fijo* o *esquinas fijas* |

**Trucos.**
- Para una forma de varias partes, **únelas y suéldalas** primero.

### Editar malla

**Para qué.** Dar forma a una malla a mano: en la vista 3D, elige sus esquinas y arrástralas (Alt: hacia arriba o
abajo). Solo se guardan las movidas, así que si la malla que entra cambia, las ediciones se mantienen.

**Trucos.**
- **Editar malla** seguido de **Suavizar malla** es la forma de modelar una forma libre: una jaula gruesa movida a
  mano, y los niveles la redondean.

### Triangular

![Triangular](/images/manual/nodes/triangulate.png)

**Para qué.** Cada cara como triángulos: cada cuadrilátero partido por una diagonal. Los triángulos siempre son
planos.

| Entrada | Qué quiere decir |
|---|---|
| **diagonal** | la *más corta*, o siempre la *primera* (0-2) o la *segunda* (1-3) |

### Voltear caras

**Para qué.** Voltear caras, que el frente pase a ser el dorso: para que todas las caras de una malla miren hacia
el mismo lado.

| Entrada | Qué quiere decir |
|---|---|
| **cuáles** | las caras que se voltean (`1` · `0 3`); vacío: todas |

## Leerla

### Caras de malla

![Caras de malla](/images/manual/nodes/mesh-faces.png)

**Para qué.** Leer cada cara de una malla: su contorno, su centro, su normal, cuántos lados tiene, si mira hacia el
mismo lado que sus vecinas, o qué tan plana es.

| Entrada | Qué quiere decir |
|---|---|
| **qué** | *contornos*, *centros*, *normales*, *lados*, *orientación* (+1 como sus vecinas, −1 volteada) o *planitud* |

### Aristas de malla

![Aristas de malla](/images/manual/nodes/mesh-edges.png)

**Para qué.** Las aristas de una malla como líneas: su borde, o las barras de una estructura a lo largo de sus
aristas.

| Entrada | Qué quiere decir |
|---|---|
| **cuáles** | *libres* (de una sola cara: el borde, o una costura que no se soldó), *interiores* (compartidas) o *todos* |
