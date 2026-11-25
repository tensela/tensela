---
title: Medir
description: Distancias, atractores, remapeos, áreas, largos y volúmenes, y las condiciones que hacen cada pieza distinta.
---

Medir es donde un diseño empieza a responder: a qué distancia está cada panel de un punto, qué tan grande es cada
celda, qué piezas pasan una regla. Estos nodos son violeta en el lienzo, y la mayoría da **números**, uno por
elemento, que conectas a un tamaño, un ángulo o una distancia. Mira [Condiciones y atractores](/es/manual/key-ideas/conditions-and-attractors/).

**Para ver esos números sobre el modelo**, pinta la geometría según un valor en su panel (**Color → según un
valor**): así se hicieron las imágenes de esta página.

## Cercanía

### Atractor

![Atractor](/images/manual/nodes/attractor.png)

**Para qué.** Un valor por elemento según lo cerca que esté de unos puntos o curvas: quiebrasoles que se abren cerca
de una entrada, paneles que se achican hacia una esquina, perforaciones que crecen a lo largo de un camino.

| Entrada | Qué quiere decir |
|---|---|
| **dónde** | los puntos que lo sienten, o una geometría (cada elemento por su centro) |
| **atractores**, **más** | uno o más puntos o curvas; *más* para mezclar puntos y curvas |
| **alcance** | hasta dónde llega el efecto, en metros; vacío: hasta el más lejano |
| **cerca**, **lejos** | el valor junto al atractor, y en el alcance o más allá |
| **varios** | manda *el más cercano*, o sus efectos *se suman* |
| **curva** | *lineal*, *suave*, *acelera* o *frena* |

**Trucos.**
- Conecta lo que da al **giro** de un Colocar, al **factor** de un Escalar o a la **distancia** de un Mover.

### Distancia

![Distancia](/images/manual/nodes/distance.png)

**Para qué.** La distancia entre puntos, en metros: cada panel a un punto, cada columna a la siguiente.

**Cómo.** Conecta puntos a **a** y **b**. Con listas de nombres distintos, todos con todos.

### Punto más cercano

![Punto más cercano](/images/manual/nodes/closest-point.png)

**Para qué.** El punto de una curva más cercano a cada punto: para unirlos con líneas, orientar algo hacia la curva,
o saber dónde cae a lo largo de ella.

| Entrada | Qué quiere decir |
|---|---|
| **puntos** | los puntos, o una geometría (cada elemento por su centro) |
| **curva** | la curva donde se busca |
| **da** | el *punto* en la curva, su *fracción* a lo largo, o la *distancia* |

## De un rango a otro

### Remapear

![Remapear](/images/manual/nodes/remap.png)

**Para qué.** Llevar un valor de un rango a otro: distancias de 0 a 12 m a ángulos de 90° a 0°.

| Entrada | Qué quiere decir |
|---|---|
| **valor** | los números que se remapean |
| **desde min**, **desde max** | el rango de origen; vacío: el menor y el mayor de los datos |
| **hacia min**, **hacia max** | el rango al que van |
| **curva** | *lineal*, *suave*, *acelera* o *frena* |
| **limitar** | sí: lo que pasa del rango de origen se queda en el extremo |

### Gráfica

![Gráfica](/images/manual/nodes/graph.png)

**Para qué.** Como Remapear, pero **dibujas la curva** moviendo sus puntos en el panel: decides cómo cambia un valor
de abajo hacia arriba sin escribir una fórmula.

| Entrada | Qué quiere decir |
|---|---|
| **valor** | los números que pasan por la gráfica |
| **puntos** | los puntos de la curva, movidos en el panel |
| **hacia min**, **hacia max** | lo que sale abajo y arriba |
| **suave** | sí: una curva suave · no: tramos rectos |
| **desde min**, **desde max** | el rango de origen; vacío: el de los datos |

**Trucos.**
- Una curva guía, una **Distancia** hasta ella y una **Gráfica** hacen relieves sin ninguna fórmula.

### Muestreo de imagen

**Para qué.** Un valor en cada punto leído de una imagen: qué tan clara es ahí. Para perforar una fachada a partir de
una foto, o levantar columnas a partir de un dibujo.

| Entrada | Qué quiere decir |
|---|---|
| **archivo** | la imagen: una foto, un dibujo, un degradado |
| **dónde** | los puntos que la leen, o una geometría (cada elemento por su centro) |
| **marco** | dónde se apoya la imagen, estirada para calzar; vacío: alrededor de los puntos |
| **plano** | cómo se apoya: *planta*, *alzado* o *lateral* |
| **canal** | *luminosidad*, *rojo*, *verde*, *azul* u *opacidad* |
| **negro**, **blanco** | los valores para lo oscuro y lo claro; intercámbialos para invertir |

### Resumir

**Para qué.** Un número a partir de muchos: el área total de una fachada, el piso más alto, el ángulo promedio,
cuántos son.

| Entrada | Qué quiere decir |
|---|---|
| **dato** | los números |
| **operación** | *máximo*, *mínimo*, *suma*, *promedio* o *contar* |
| **sobre** | qué nivel desaparece; vacío: todos |

## Tamaños

### Área

![Área](/images/manual/nodes/area.png)

**Para qué.** El área de cada elemento en m²: una planta, una superficie, la piel de un volumen.

### Largo

![Largo](/images/manual/nodes/length.png)

**Para qué.** El largo de cada curva en metros: un cable, un borde, un perímetro.

### Volumen

![Volumen](/images/manual/nodes/volume.png)

**Para qué.** El volumen de cada cuerpo cerrado en m³: una caja, un prisma, unos tubos.

**Trucos.**
- Un rectángulo no tiene volumen: no está cerrado. Extrúyelo con tapas primero.

### Centroide

![Centroide](/images/manual/nodes/centroid.png)

**Para qué.** El centro de gravedad de cada elemento: de su volumen, área o largo. No el promedio de sus esquinas,
que es lo que da **Centro**.

### Coordenada

![Coordenada](/images/manual/nodes/coordinate.png)

**Para qué.** La x, la y o la z de cada punto: para compararla (los paneles de un lado, los que están sobre cierta
altura) o usarla en una Fórmula.

### Normal

![Normal](/images/manual/nodes/normal.png)

**Para qué.** Hacia dónde mira cada rectángulo: hacia afuera en las caras de un prisma, o en los paneles de una
superficie. Para parar cosas sobre una superficie con **Orientar**, o saber qué paneles miran al sur.

### Medir vector

**Para qué.** El largo de un vector, o el ángulo en grados entre dos: `90`, perpendiculares.

| Entrada | Qué quiere decir |
|---|---|
| **modo** | *largo* o *ángulo* |
| **base** | el vector que se mide |
| **otro** | el segundo vector; la vertical de fábrica |

## Condiciones

### Comparar

![Comparar](/images/manual/nodes/compare.png)

**Para qué.** Un sí o un no por elemento: *a* es *menor*, *menor o igual*, *mayor*, *mayor o igual*, *igual* o
*distinto* de *b*.

### Combinar condiciones

**Para qué.** Para juntar dos condiciones: *y* (las dos), *o* (cualquiera), *solo uno*, o *no* (lo contrario de *a*).

### Dentro de

![Dentro de](/images/manual/nodes/inside.png)

**Para qué.** Sí o no para cada punto: si cae dentro de una planta, vista desde arriba, o dentro de un volumen
cerrado. Las columnas dentro del patio, los árboles dentro del edificio.

### Escoger

![Escoger](/images/manual/nodes/choose.png)

**Para qué.** Una cosa u otra para cada elemento: donde se cumple la condición, el **sí**; si no, el **no**. Un panel
abierto o uno cerrado. Con un solo **Sí o no**, toda una variante o la otra.

### Filtrar

![Filtrar](/images/manual/nodes/filter.png)

**Para qué.** Para quedarse con algunos elementos: los que cumplen una condición, los de un patrón, o uno de cada
tantos.

| Entrada | Qué quiere decir |
|---|---|
| **modo** | *condición*, *patrón* (`sí; no; no` deja uno de cada tres) o *cada* (uno de cada tantos) |
| **condición**, **patrón**, **cada**, **desde** | los valores de cada modo |
| **nivel** | qué nivel; vacío: el único |
| **quitar** | sí: los otros se van y la lista se acorta · no: quedan en su lugar, vacíos |
| **conservar** | *los que sí* o *los que no*: dos Filtrar, uno de cada uno, parten una lista en dos |
