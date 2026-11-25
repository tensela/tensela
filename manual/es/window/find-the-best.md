---
title: Buscar el mejor
description: Deja que Tensela mueva los deslizadores hasta que un número llegue a su mínimo, a su máximo o a un valor.
---

## Para qué

Para encontrar los valores que hacen mejor un diseño según algún número: el menor material, el mayor sol en invierno
en una fachada, un área lo más cerca posible de 500 m², la estructura más liviana que pasa el
[Análisis de barras](/es/manual/nodes/simulation/#análisis-de-barras).

## Cómo

![Buscar el mejor: el volumen de la torre como número a buscar, y los controles que puede mover](/images/manual/app/find-the-best-es.png)

1. Abre **Editar → Buscar el mejor…**, o haz clic derecho en el nodo que da el número, **Buscar su mejor valor…**. Se
   abre al lado de la ventana, así sigues viendo el modelo.
2. **Arriba, lo que se busca:** un nodo que da un solo número (un Largo, un Área, una Fórmula, el peso total de un
   Análisis de barras…) y si quieres su **mínimo**, su **máximo** o **llegar a** un valor.
3. **Abajo, qué deslizadores mueve:** los que cambian ese número, todos marcados al empezar. Desmarca los que debe
   dejar quietos. Si algún número todavía no tiene deslizador, el botón para mostrar los marcados como deslizadores
   los suma a *Valores*.
4. **Buscar.** Cada vez que encuentra algo mejor, los deslizadores y la vista 3D lo muestran. **Detener** se queda con
   lo mejor hasta ahí.

Al terminar, los mejores valores quedan en los deslizadores, y **Ctrl + Z** vuelve a como estaban. La lista guarda los
mejores encontrados: un clic devuelve cualquiera de ellos.

## Cerca, o en todo el rango

- **Cerca** afina desde donde están los deslizadores: rápido, y encuentra el mejor cerca del inicio.
- **En todo el rango** explora todo con una población de candidatos, generación tras generación: más lento, y mejor
  cuando hay varias buenas respuestas lejos unas de otras.

**Truco.** La búsqueda trabaja sobre una copia del proyecto, así que la ventana sigue respondiendo mientras busca.
Cómo busca se cuenta en [Búsqueda de forma y el mejor valor](/es/manual/theory/form-finding/).
