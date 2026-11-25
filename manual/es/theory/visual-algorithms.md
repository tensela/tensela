---
title: Algoritmos visuales
description: Qué es un algoritmo, por qué dibujarlo como nodos le sirve a un arquitecto, y de dónde viene el diseño paramétrico.
---

## Un algoritmo es una receta

Un **algoritmo** es una lista de pasos que, seguidos en orden, siempre dan un resultado: una receta. No necesita una
computadora. *Toma un rectángulo de 20 × 12 m, pártelo en paneles de 1 m, pon un quiebrasol en el centro de cada
panel* ya es un algoritmo.

![El mismo algoritmo como receta, como código y como nodos](/images/manual/diagrams/visual-algorithm-es.svg)

La misma receta se puede escribir de tres maneras. En palabras la entiende cualquiera, pero ninguna máquina la
ejecuta. En código la ejecuta una máquina, pero para leerla hay que aprender un lenguaje. Un **algoritmo visual** la
dibuja como nodos y cables: se lee como la receta y se ejecuta como el código.

## Qué es un algoritmo visual

Un algoritmo visual es un **grafo**: un conjunto de nodos unidos por cables.

- **Un nodo es una función:** recibe unas entradas y da un resultado. Una Retícula recibe un rectángulo y dos
  medidas, y da paneles. Con las mismas entradas, siempre da el mismo resultado.
- **Un cable es un dato:** lleva el resultado de un nodo a una entrada de otro.
- **Los datos van en un solo sentido.** De los valores que escribes, por los nodos, hasta la forma. Por eso el grafo
  se lee de izquierda a derecha.
- **No hay vueltas.** Un nodo no puede depender de su propio resultado: Tensela no acepta el cable que cerraría un
  círculo, y dice por qué. Eso hace que el grafo siempre dé una respuesta, y que Tensela sepa exactamente qué
  recalcular cuando algo cambia ([Cómo se calcula un proyecto](/es/manual/theory/the-engine/)).

### Repetir sin vueltas

Si no hay vueltas, ¿cómo se repite un paso 240 veces? No se repite: se le da al paso **una lista de 240**, y trabaja
con todos a la vez. Para eso están las [listas con nombre](/es/manual/key-ideas/named-lists/).

Cuando un paso de verdad tiene que trabajar sobre su propio resultado (un fractal, una curva que se subdivide, un
crecimiento), un [grupo](/es/manual/key-ideas/groups/) puede **repetirse** una cantidad de veces: la vuelta queda
cerrada dentro de una tarjeta, con una cuenta, así que siempre termina.

## Qué lo hace paramétrico

*Paramétrico* no quiere decir curvo ni complicado. Quiere decir que el diseño se describe por sus **parámetros** (el
ancho, la cantidad de pisos, el ángulo) y por las **dependencias** entre sus partes: los paneles dependen de la
fachada, los quiebrasoles de los paneles. Cambias un parámetro y todo lo que depende de él lo sigue.

El valor no está en una forma sino en la **familia de formas** que puede dar la receta: el mismo proyecto hace una
fachada de 12 m o de 40 m, abierta o cerrada, y eliges entre ellas mirando.

## De dónde viene

Diseñar con reglas es mucho más antiguo que las computadoras.

- **Antoni Gaudí** encontraba la forma de sus bóvedas colgando cadenas con pesos e invirtiendo la maqueta: la forma
  salía de la gravedad, no de un dibujo. El nodo [Equilibrio](/es/manual/nodes/simulation/#equilibrio) hace lo
  mismo.
- **Frei Otto** estudió películas de jabón y redes colgantes para encontrar las formas de sus cubiertas tensadas,
  como la del Estadio Olímpico de Múnich.
- **Luigi Moretti**, en Italia, habló de *arquitectura paramétrica* a mediados del siglo XX, con estudios de
  estadios cuya forma salía de parámetros como la vista desde cada asiento.
- **Sketchpad, de Ivan Sutherland**, en 1963, fue uno de los primeros programas para dibujar con reglas: líneas que
  siguen paralelas, puntos que siguen unidos.
- A fines de los años 2000 la **programación visual** llegó a los arquitectos, con herramientas como Grasshopper y,
  después, Dynamo. Tensela viene de esa tradición, y busca una curva de aprendizaje suave.

## La matemática detrás

Cada familia de nodos se apoya en un poco de geometría. No la necesitas para diseñar, pero ayuda saber de dónde
salen las cosas:

- **Coordenadas y vectores:** cada punto son tres números, cada dirección una flecha.
  [Unidades y direcciones](/es/manual/theory/units-and-directions/).
- **Curvas y superficies:** puntos de control que tiran de una forma suave. [NURBS](/es/manual/theory/nurbs/).
- **Curvatura:** por qué algunas superficies se construyen con chapa plana y otras no.
  [Curvatura](/es/manual/theory/curvature/).
- **Mallas:** formas hechas de caras planas, el idioma de la fabricación y la simulación.
  [Mallas](/es/manual/theory/meshes/).
- **Fuerzas y optimización:** formas que se encuentran solas, y el mejor valor entre muchos.
  [Búsqueda de forma](/es/manual/theory/form-finding/).
