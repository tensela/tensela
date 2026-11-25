---
title: Nodos y cables
description: Cómo se arma un diseño con pasos pequeños, y por qué cambiar un número cambia todo lo que viene después.
---

## Para qué

Para describir **cómo** se hace tu diseño en vez de dibujar el resultado. Con los pasos armados, cambias cualquiera
de ellos, el ancho de la fachada, la cantidad de pisos, el ángulo de un quiebrasol, y todo lo que depende de él se
vuelve a calcular.


## Un algoritmo es una receta

Una receta tiene **ingredientes**, **pasos** en un orden y un **plato** al final. Un proyecto de Tensela es igual:

![Ingredientes, pasos y el plato: una fachada hecha como una receta](/images/manual/sketches/recipe-es.svg)

| En una receta | En Tensela | En la fachada con quiebrasoles |
|---|---|---|
| Los ingredientes | los valores que escribes | 20 m de ancho, 12 m de alto, paneles de 1 m |
| Los pasos | los nodos | un rectángulo, una retícula, un quiebrasol en cada panel |
| El orden de los pasos | los cables | la retícula necesita antes el rectángulo |
| El plato | la forma en la vista 3D | la fachada con sus 240 quiebrasoles |

Cambias un ingrediente, una fachada más alta o paneles más angostos, y la misma receta te da otro plato. No vuelves a dibujar la
fachada: cambias la receta. Y como una receta, un proyecto se puede compartir: quien lo abre tiene los mismos pasos y
puede probar sus propios ingredientes. Por eso los proyectos de este manual se llaman [recetas](/es/manual/recipes/).

## Cómo

- **Añadir un nodo:** doble clic en un lugar vacío del lienzo, o la tecla **Tab**, y escribe. Puedes escribir el
  nombre del nodo (*Prisma*) o lo que quieres hacer (*volumen*, *edificio*): el buscador lo encuentra igual.
- **Conectar:** arrastra desde el circulito a la **derecha** de una tarjeta, que es lo que da el nodo, hasta una
  entrada de otra tarjeta.
- **Dar valores:** cada entrada de una tarjeta se puede **escribir** (un número, un punto, una lista) o **traer por un
  cable** desde otro nodo. Cuando llega un cable, el campo toma su valor de él.

## Qué hace

![El grafo del primer proyecto: tarjetas y cables](/images/manual/diagrams/first-project-graph-es.svg)

- **Un cable lleva una sola cosa** de un nodo a otro: un rectángulo, 240 puntos, una lista de ángulos. Sobre el cable
  se lee su tamaño, por ejemplo `fila 12 × columna 20 = 240`.
- **Cambias un valor y todo lo que viene después se actualiza**, en orden, en la vista.
- **Cada familia de nodos tiene su color**, el mismo en la franja de la tarjeta, en su icono y en el buscador:

| Familia | Color | Ejemplos |
|---|---|---|
| Valores | verde | Número, Serie, Fórmula, Sí o no |
| Formas | azul | Punto, Caja, Prisma, Rectángulo |
| Curvas | verde azulado | Círculo, Arco, Curva NURBS, Línea |
| Superficies | azul petróleo | Superficie por secciones, Extruir, Costillas, Superficie por puntos |
| Dividir | ocre | Retícula, Caras, Vértices, Puntos de curva |
| Medir | violeta | Área, Distancia, Atractor, Filtrar |
| Transformar | rojo teja | Mover, Girar, Escalar, Colocar |

## Trucos

- **Una tarjeta con un problema lo dice con palabras**: qué falta o qué no calza, y casi siempre cómo arreglarlo.
- **Números:** los decimales se escriben con coma o con punto, `3,5` o `3.5`. Varios valores se separan siempre con
  punto y coma: `1,5; 2; 3`. Un punto se escribe `0 0 0`, `8 0 2,5` o `(0; 0; 1,5)`.
- **Dentro de un campo de la tarjeta**, Tab pasa al valor siguiente y Supr borra letras, no el nodo.
