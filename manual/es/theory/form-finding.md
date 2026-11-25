---
title: Búsqueda de forma y el mejor valor
description: Cómo encuentra Equilibrio la forma en reposo, y cómo mueve Buscar el mejor los deslizadores.
---

## Equilibrio: partículas y resortes

**Equilibrio** reemplaza un cable o una membrana por **partículas** (puntos, cada uno con una parte del peso) unidas
por **resortes**: cada resorte tira o empuja según cuánto se estiró desde su largo en reposo. Algunas partículas son
apoyos y no se mueven. Las partículas se mueven hasta que todas las fuerzas se equilibran.

La forma encontrada así lleva sus cargas **solo a lo largo de los resortes**, a tracción o a compresión. Es el
principio de las maquetas colgantes de Gaudí y de las estructuras tensadas de Frei Otto: cuélgala, e inviértela para
tener una bóveda que trabaja solo a compresión.

Por dentro usa **relajación dinámica**, el método habitual para estructuras tensadas: las partículas se mueven con las
fuerzas que no están en equilibrio, y cada vez que su movimiento llega al máximo se detienen y vuelven a partir desde
ahí, hasta quedar en reposo. El nodo siempre da la forma ya en reposo.

## Buscar el mejor

**Buscar el mejor…** mueve algunos deslizadores hasta que un número que da un nodo llegue a su mínimo, a su máximo o
a un valor: el menor material, el mayor sol en invierno, un área dada.

- **Cerca** afina desde donde están los deslizadores: prueba un paso hacia arriba y uno hacia abajo en cada uno, se
  queda con lo que mejora, y achica los pasos cuando nada mejora. Encuentra el mejor valor cerca del inicio.
- **En todo el rango** mantiene una población de candidatos que se cruzan y mutan, generación tras generación, hasta
  que el mejor deja de mejorar. Explora más, y tarda más.

Los dos se quedan dentro de los rangos de los deslizadores y caen en valores que los deslizadores pueden mostrar.
