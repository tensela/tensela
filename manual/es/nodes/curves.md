---
title: Curvas
description: Líneas, arcos, círculos, catenarias, curvas por puntos o dibujadas a mano, y los nodos que las dividen, cortan, desplazan y rotulan.
---

Las curvas son ejes, bordes, perfiles, recorridos y cables. En el lienzo son verde azulado.

**En una curva, una posición es una fracción o una distancia.** Muchos nodos de aquí preguntan *dónde* en la curva:
una **fracción** va de `0` (el inicio) a `1` (el final), así que `0,5` es el medio; una **distancia** va en metros
desde el inicio, y negativa desde el final.

## Línea

![Línea](/images/manual/nodes/line.png)

**Para qué.** Una viga, un borde, un eje entre dos puntos.

**Cómo.** Conecta un punto a **desde** y otro a **hasta**. Si los puntos son listas, salen muchas líneas.

## Línea por dirección

![Línea por dirección](/images/manual/nodes/line-by-direction.png)

**Para qué.** Un mástil, una columna, una perpendicular: una línea que sale de un punto y va hacia algún lado.

**Cómo.** Conecta el punto a **desde**, y dale una **dirección** y un **largo**.

| Entrada | Qué quiere decir |
|---|---|
| **desde** | dónde empieza |
| **dirección** | hacia dónde va; hacia arriba de fábrica (`0 0 1`) |
| **largo** | cuánto mide; negativo, hacia el otro lado |

## Arco

![Arco](/images/manual/nodes/arc.png)

**Para qué.** Un borde curvo, el perfil de una bóveda, una curva que continúa a otra sin quiebre.

**Cómo.** Elige el **modo** y dale lo que pide.

| Modo | Lo que das |
|---|---|
| *tres puntos* | el **inicio**, un punto **medio** por donde pasa, y el **fin** |
| *centro y ángulos* | el **centro**, el **radio**, y los ángulos **desde** y **hasta** (grados; 0° hacia +X, contra reloj) |
| *inicio, dirección y fin* | el **inicio**, la **dirección** en que sale, y el **fin**: continúa una curva sin quiebre |

**Trucos.**
- Para continuar una curva suave, conecta la **Tangente** de su final a **dirección**.

## Catenaria

![Catenaria](/images/manual/nodes/catenary.png)

**Para qué.** La forma exacta de una cadena o un cable colgando entre dos puntos. Invertida, el arco o la bóveda que
trabaja sobre todo a compresión, como hacía Gaudí con sus maquetas colgantes.

**Cómo.** Dale el **inicio**, el **fin** y el **largo** del cable.

| Entrada | Qué quiere decir |
|---|---|
| **inicio**, **fin** | de dónde cuelga el cable |
| **largo** | más largo, cuelga más; más corto que la distancia, queda tenso |
| **largo en** | *metros*, o *veces la distancia* entre los extremos (`1,2`: un quinto más largo), para muchos cables con luces distintas |
| **gravedad** | hacia dónde cuelga; hacia arriba (`0 0 1`) da el arco |

**Trucos.**
- Sus puntos quedan repartidos parejo a lo largo, listos para **Puntos de curva** o para colgantes.

## Círculo

![Círculo](/images/manual/nodes/circle.png)

**Para qué.** La sección de una columna, una ventana redonda, una elipse, un círculo que toca una curva.

**Cómo.** *Centro y radio*, o *tangente a una curva*.

| Entrada | Qué quiere decir |
|---|---|
| **modo** | *centro y radio* o *tangente a una curva* (la toca en un punto sin cruzarla) |
| **centro**, **radio** | el círculo de siempre |
| **radio 2** | vacío: un círculo; con un valor: una elipse |
| **curva**, **en**, **medida**, **lado** | modo tangente: qué curva, dónde (fracción o distancia) y de qué lado |
| **plano** | *planta*, *alzado* o *lateral* |
| **normal** | hacia dónde mira; las normales de una superficie lo acuestan sobre ella |

## Curva por puntos

![Curva por puntos](/images/manual/nodes/curve-through-points.png)

**Para qué.** Para unir puntos en una curva: un perfil, un recorrido, el borde de una cubierta.

**Cómo.** Conecta los **puntos**. Se unen a lo largo de un nivel, el último si dejas **sobre** vacío.

| Entrada | Qué quiere decir |
|---|---|
| **puntos** | los puntos que se unen |
| **sobre** | el nivel de los puntos que se unen; vacío: el último |
| **suave** | sí: una curva suave; no: una polilínea con esquinas |
| **cerrada** | sí: vuelve al primer punto |

**Trucos.**
- Con una retícula de puntos, `fila × columna`, sale una curva por fila o por columna, según **sobre**.

## Curva de transición

![Curva de transición](/images/manual/nodes/transition-curve.png)

**Para qué.** Para unir el final de una curva con el inicio de otra, suave, sin quiebres.

| Entrada | Qué quiere decir |
|---|---|
| **a**, **b** | la curva de donde sale y a la que llega |
| **abombado** | `0,1`: casi recta · `1`: muy ancha |
| **unir** | sí: da *a + transición + b* como una sola curva |

## Curva dibujada

![Curva dibujada](/images/manual/nodes/drawn-curve.png)

**Para qué.** Para dibujar una curva con el ratón, directo en la vista 3D.

**Cómo.** Haz clic en la vista para marcar sus puntos, y después arrástralos.

| Entrada | Qué quiere decir |
|---|---|
| **modo** | *por los puntos*: la curva pasa por ellos · *de control*: la tiran como imanes |
| **grado** | `1`: una polilínea · `3`: suave · hasta `5`: más tensa |
| **cerrada** | sí: una curva cerrada |

## Curva NURBS

![Curva NURBS](/images/manual/nodes/nurbs-curve.png)

**Para qué.** Control total de una curva libre: sus puntos de control la tiran como imanes, con grado, pesos y nudos.

**Cómo.** Conecta unos **puntos**, o dibújalos con **Editar curva**. En modo *pluma*, marca anclas por donde pasa,
con manijas que le dan forma.

| Entrada | Qué quiere decir |
|---|---|
| **modo** | *puntos de control* o *pluma* |
| **grado** | `1`: la polilínea de los puntos · `2`: arcos · `3`: suave · hasta `7`: más tensa |
| **pesos** | cuánto tira cada punto: `1` es lo normal, más acerca la curva |
| **nudos** | cómo se reparte la curva entre los puntos: parejo, por distancia, a medias, o a mano |
| **cerrada** | sí: una curva cerrada |

## Puntos de curva

![Puntos de curva](/images/manual/nodes/points-on-curve.png)

**Para qué.** Puntos a lo largo de una curva: postes cada 3 m, 20 divisiones iguales, el medio de un borde.

**Cómo.** Conecta la **curva** y elige el **modo**.

| Modo | Lo que da |
|---|---|
| *partes* | **cantidad** puntos, repartidos parejo a lo largo de la curva |
| *cada* | un punto cada **distancia** metros |
| *fracción* | las **posiciones** como fracciones: `0,5` · `0,25; 0,75` |
| *distancia* | las **posiciones** en metros: `2; -2` (a 2 m de cada extremo) |

**Trucos.**
- Ponle nombre al **nivel** (*poste*, *costilla*), para que los puntos se combinen bien después.

## Tangente

![Tangente](/images/manual/nodes/tangent.png)

**Para qué.** La dirección de una curva en algunos puntos: hacia dónde va, o su perpendicular. Para orientar piezas a
lo largo de un recorrido, o para continuar una curva.

**Cómo.** Conecta la **curva**, elige **qué** (*tangente* o *normal*) y dónde, como en Puntos de curva.

**Trucos.**
- Con **Puntos de curva** en las mismas posiciones, tienes cada punto y su dirección.

## Invertir curva

**Para qué.** Para invertir las curvas, que empiecen donde terminaban. Con una **dirección**, todas quedan yendo
hacia el mismo lado: antes de una **Superficie por secciones**, para que no salga torcida.

## Cortar curva

![Cortar curva](/images/manual/nodes/cut-curve.png)

**Para qué.** Para cortar cada curva en pedazos y trabajarlos uno por uno.

| Entrada | Qué quiere decir |
|---|---|
| **modo** | *partes*, *cada*, *fracción*, *distancia*, o *en puntos* (donde caen unos puntos) |
| **cantidad**, **distancia**, **posiciones**, **puntos** | los valores de cada modo |
| **nivel** | el nombre de la lista de pedazos (*tramo* de fábrica) |

## Rectángulo redondeado

![Rectángulo redondeado](/images/manual/nodes/rounded-rectangle.png)

**Para qué.** El contorno de un rectángulo con las esquinas redondeadas, en planta: una mesa, una piscina, un terreno.

| Entrada | Qué quiere decir |
|---|---|
| **ancho**, **alto** | su tamaño |
| **radio** | de las esquinas |
| **origen** | la esquina inferior izquierda |

## Parte de curva

![Parte de curva](/images/manual/nodes/part-of-curve.png)

**Para qué.** El pedazo de una curva entre dos fracciones de su largo: un arco de círculo, un trozo de borde.

**Cómo.** Dale **desde** y **hasta**, de `0` (el inicio) a `1` (el final). En una curva cerrada puede dar la vuelta.

## Flecha

![Flecha](/images/manual/nodes/arrow.png)

**Para qué.** Para ver un vector, una dirección o una fuerza, como una flecha en un punto. También funciona como
línea.

| Entrada | Qué quiere decir |
|---|---|
| **desde** | dónde empieza la flecha |
| **vector** | la dirección y el tamaño |
| **escala** | para verla más larga o más corta |

## Unir cercanos

![Unir cercanos](/images/manual/nodes/join-nearest.png)

**Para qué.** Una red de barras: cada punto unido a sus vecinos más cercanos.

**Cómo.** Conecta los **puntos** y di con cuántos vecinos (**cantidad**) se une cada uno.

## Desplazar curva

![Desplazar curva](/images/manual/nodes/offset-curve.png)

**Para qué.** El contorno de un muro a partir de su eje, un borde alrededor de una planta, el segundo lado de una
pieza para cortar.

| Entrada | Qué quiere decir |
|---|---|
| **curva** | una o más curvas planas |
| **distancia** | curva cerrada: hacia afuera (negativa: hacia adentro) · curva abierta: a su izquierda, vista desde arriba (negativa: a su derecha) |
| **esquinas** | en curvas cerradas: *redonda* o *viva* |

## Texto

![Texto](/images/manual/nodes/text.png)

**Para qué.** Un rótulo en cada elemento: el número de un panel, la letra de un tipo de ladrillo, un área. Se ve en
3D y sale en los dibujos y los archivos de corte.

**Cómo.** Conecta **en** (puntos, o los paneles, cuerpos o curvas que quieres rotular) y escribe el **texto**.

| Entrada | Qué quiere decir |
|---|---|
| **texto** | `{n}`: el número de cada elemento · `{floor}`, `{row}`…: su número en ese nivel · `{value}`: el número que da **valor** · `A; B; C`: un texto por elemento · `\|`: una línea nueva |
| **valor**, **decimales** | los números que se escriben con `{value}`, y cuántos decimales |
| **alto** | de las letras mayúsculas |
| **plano** | *planta*, *alzado*, *lateral*, o *sobre la cara* (acostado sobre cada panel) |
| **letra** | *recta* o *redondeada*: letras de un solo trazo, para grabar · *tipografía*: una tipografía instalada, como contornos |
| **tipografía**, **alinear** | qué tipografía, y cómo se alinean las líneas |

**Trucos.**
- `P{n}` escribe `P0, P1, P2…`; `F{piso}-{vano}` escribe `F0-0, F0-1…`; `{value} m2` escribe cada área.

## Curvas de nivel

![Curvas de nivel](/images/manual/nodes/contour.png)

**Para qué.** Corta una superficie o un volumen con planos paralelos cada cierta distancia: las curvas de nivel de
un terreno, las losas de una torre, anillos.

| Entrada | Qué quiere decir |
|---|---|
| **geometría** | una superficie, un volumen o una malla |
| **distancia** | cada cuánto se corta |
| **dirección** | hacia dónde avanzan los cortes; hacia arriba: cortes horizontales |
| **inicio** | la altura del primer corte; vacío: el punto más bajo |
| **nivel** | el nombre de la lista de cortes (*corte* de fábrica) |
