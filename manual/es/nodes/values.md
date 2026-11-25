---
title: Valores
description: Número, Serie, Fórmula, Función, Al azar, Punto, Sí o no, Info, Repetir, Juntar, Unir listas y Código.
---

Los valores son los números y las listas que mueven un diseño: el ancho de un vano, 16 pisos, un ángulo que depende
de una distancia. En el lienzo son verdes.

## Número

**Para qué.** Un valor que quieres cambiar a mano: la altura de un piso, el fondo de un quiebrasol. O una lista corta
escrita a mano: pisos de alturas distintas, vanos de anchos distintos.

**Cómo.** Escribe el **valor**. En la ventana se vuelve un deslizador que puedes arrastrar.

| Entrada | Qué quiere decir |
|---|---|
| **valor** | un número, o varios separados por `;`: `3,5; 3; 3; 4` |
| **nivel** | el nombre de la lista cuando hay varios valores: *piso*, *vano*, *eje* |

**Trucos.**
- Con varios valores, ponle nombre a la lista, para que se empareje o se cruce bien con otras.
  [Listas con nombre](/es/manual/key-ideas/named-lists/)

## Serie

**Para qué.** Muchos números que siguen una regla: 25 pisos cada 3,2 m, 12 escalones, 40 quiebrasoles repartidos en
una fachada.

**Cómo.** Escribe cuántos (**cantidad**) y cómo avanzan: **con paso** (desde el inicio, tanto cada vez) o **entre
dos** (repartidos parejo desde el inicio hasta el final).

| Entrada | Qué quiere decir |
|---|---|
| **cantidad** | cuántos números |
| **modo** | *con paso* o *entre dos* |
| **inicio** | el primer número |
| **paso** | cuánto suma cada uno (con paso) |
| **hasta** | el último número, incluido (entre dos) |
| **nivel** | el nombre de la lista nueva: *piso*, *escalón*, *eje* |

**Trucos.**
- Una Serie es la forma habitual de empezar una lista. Ponle nombre a su nivel desde el principio.
- `cantidad 5, inicio 0, paso 3,2` da `0; 3,2; 6,4; 9,6; 12,8`: los niveles de cinco pisos.

## Fórmula

**Para qué.** Un cálculo, como una celda de hoja de cálculo: un ángulo a partir de una distancia, una altura que
crece piso a piso.

**Cómo.** Escribe la **fórmula** con las letras **a** a **h**, y conecta un valor a cada letra que uses. Las letras
**e** a **h** aparecen cuando las escribes.

| Entrada | Qué quiere decir |
|---|---|
| **fórmula** | como en una hoja de cálculo: `a * 3,5`, `si(a < 5; 90; 0)`, `sen(a)` |
| **a … h** | los valores que usa la fórmula |

**Trucos.**
- Los ángulos van en **grados**: `sen(30)` es 0,5.
- Entiende español e inglés, incluso mezclados: `si(a < 7; 3; 6)` = `if(a < 7, 3, 6)`.
- Si **a** es una lista de 240 valores, la fórmula se calcula 240 veces, una por cada uno.

## Función

![Función](/images/manual/nodes/function.png)

**Para qué.** Formas listas para un número: una onda, un arco, una catenaria, una colina, una silla de montar. Para
darle una onda a una fachada o un abombado a una cubierta sin escribir una fórmula.

**Cómo.** Elige la **forma**, conecta dónde se calcula (**x**, e **y** en las formas de dos variables) y dale su
**altura** y su **ancho**.

| Entrada | Qué quiere decir |
|---|---|
| **forma** | de una variable: *onda*, *rampa*, *parábola*, *catenaria*, *campana*, *escalón*, *diente de sierra* · de dos: *ola*, *ondas*, *colina*, *silla*, *cúpula*, *pirámide* |
| **x** | dónde se calcula: una Serie, unas distancias, la x de unos puntos |
| **y** | la segunda variable, en las formas de dos: otra Serie, con otro nombre de nivel |
| **altura** | cuánto sube |
| **ancho** | cada cuánto se repite, o qué tan grande es la forma |

**Trucos.**
- La *silla* es el paraboloide hiperbólico, la forma de muchas cáscaras de Félix Candela.
- El panel del nodo dice para qué sirve cada forma.

## Al azar

![Al azar](/images/manual/nodes/random.png)

**Para qué.** Un poco de variedad: quiebrasoles con ángulos apenas distintos, paneles de colores al azar, árboles
de alturas distintas.

**Cómo.** **Por elemento:** un número al azar para cada elemento de un dato. **Cantidad:** una cantidad suelta de
números.

| Entrada | Qué quiere decir |
|---|---|
| **modo** | *por elemento* o *cantidad* |
| **dato** | los elementos que reciben un número cada uno (por elemento) |
| **sobre** | un número por cada… celda, fila; vacío: el primer nivel |
| **cantidad** | cuántos números (cantidad) |
| **nivel** | el nombre de la lista nueva; el mismo nombre que otra lista, para emparejarlas |
| **mínimo**, **máximo** | el rango |
| **enteros** | sí: números enteros, del mínimo al máximo, los dos incluidos |
| **semilla** | la misma semilla da siempre los mismos números; otra semilla, otros |

**Trucos.**
- Aquí el azar se puede repetir: el diseño no cambia cada vez que lo abres, solo cuando cambias la semilla.

## Punto

![Punto](/images/manual/nodes/point.png)

**Para qué.** Un punto en el espacio: un atractor, una esquina, el centro de algo.

**Cómo.** Escribe su **x**, su **y** y su **z**.

**Trucos.**
- Si una coordenada es una lista, salen muchos puntos. Dos listas con nombres distintos dan una retícula de puntos.
  [Listas con nombre](/es/manual/key-ideas/named-lists/)
- X va hacia el este, Y hacia el norte, Z hacia arriba.

## Sí o no

**Para qué.** Un interruptor: para encender o apagar una parte del modelo, o para comparar dos variantes.

**Cómo.** Conéctalo a la **condición** de un **Escoger**, que entonces da una variante o la otra.

## Info

**Para qué.** Para leer lo que lleva un cable: números, una lista, puntos. Lo deja pasar sin cambios, así que lo
puedes poner en medio de una cadena.

**Cómo.** Conecta cualquier cosa a su **valor** y léelo en la tarjeta.

## Repetir

**Para qué.** Para que una lista corta vaya con una larga: un patrón de tres anchos de vano repetido a lo largo de
una fachada de 20.

**Cómo.** Conecta el **dato**, elige el **nivel** y escribe el **largo** final.

| Entrada | Qué quiere decir |
|---|---|
| **dato** | la lista que se repite |
| **nivel** | qué nivel, si hay varios; vacío: el único |
| **largo** | cuántos elementos debe tener al final |

**Trucos.**
- `2; 6; 1` repetido hasta 5 da `2; 6; 1; 2; 6`.

## Juntar

**Para qué.** Para poner de dos a ocho cosas **lado a lado**, con un nivel nuevo: una curva y su huella, para unirlas
con una superficie; el inicio, el medio y el final de cada línea, para una curva por los tres.

**Cómo.** Conecta **a** y **b**; conecta la última y aparece otra entrada, hasta **h**.

| Entrada | Qué quiere decir |
|---|---|
| **a … h** | lo que juntas |
| **nivel** | el nombre del nivel nuevo (*parte* de fábrica) |

## Unir listas

**Para qué.** Para poner listas **una detrás de otra** en una sola lista: las aristas de una caja y unas barras más.

**Cómo.** Conecta **a** y **b**; aparece otra entrada cada vez, hasta **h**.

**Trucos.**
- **Juntar** pone las cosas lado a lado y suma un nivel; **Unir listas** las pone en fila en una sola lista.

## Código

**Para qué.** Para lo que los nodos no alcanzan: un ciclo, una función que se llama a sí misma, una regla propia. La
mayoría de los diseños nunca lo necesita.

**Cómo.** Escribe un trozo corto de **Python**. Lo que conectas a **a … h** llega al código con esas letras, y lo que
el código deja en `result` sale del nodo.

| Entrada | Qué quiere decir |
|---|---|
| **código** | hasta 200 líneas de Python que dejan su respuesta en `result` |
| **a … h** | los valores que usa el código |
| **niveles** | el nombre de la lista que da el código; para listas dentro de listas, un nombre para cada una, separados por `;` |

**Trucos.**
- El código corre **aparte de la app y con límites**: trabaja con números, listas, puntos, líneas y mallas, y
  está hecho para no abrir archivos, usar la red ni ejecutar otros programas.
