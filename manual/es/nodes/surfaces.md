---
title: Superficies
description: Superficies por curvas, puntos o bordes, revoluciones y barridos, estructuras sobre superficies, y los nodos que las miden, cortan y desarrollan.
---

Las superficies son cubiertas, muros, cáscaras, pieles y losas. En el lienzo son azul petróleo.

**En una superficie, una posición es u y v.** Una superficie tiene dos direcciones, como las filas y columnas de una
hoja: **u** a lo largo de las filas y **v** a lo largo de las columnas, cada una de `0` (un borde) a `1` (el otro).
`u 0,5, v 0,5` es el medio.

## Hacer una superficie

### Tapa

![Tapa](/images/manual/nodes/cap.png)

**Para qué.** Para cerrar una curva cerrada con una superficie: una cubierta, una losa de forma libre, una losa con
patio.

| Entrada | Qué quiere decir |
|---|---|
| **curva** | el contorno cerrado |
| **huecos** | opcional: curvas cerradas dentro de él (un patio, un lucernario) |

### Superficie por secciones

![Superficie por secciones](/images/manual/nodes/loft.png)

**Para qué.** Una superficie por varias curvas en orden: un muro ondulado por tres perfiles, una cubierta por sus
secciones.

| Entrada | Qué quiere decir |
|---|---|
| **curvas** | las secciones, en una lista |
| **sobre** | el nivel de las secciones; vacío: el último |
| **suave** | sí: suave por las secciones · no: recta entre ellas |
| **cerrada** | sí: la última sección vuelve a la primera |

**Trucos.**
- Si sale torcida, algunas curvas van al revés: pon antes un **Invertir curva** con una dirección.

### Extruir

![Extruir](/images/manual/nodes/extrude.png)

**Para qué.** Para arrastrar curvas en una lámina o un muro; con tapas, una planta cerrada se vuelve un volumen. O
para llevarlas a un punto: una pirámide, un cono, una cubierta a cuatro aguas.

| Entrada | Qué quiere decir |
|---|---|
| **modo** | *vector*: arrastrada · *hasta un punto*: se junta en un vértice |
| **vector** | hacia dónde y cuánto; 1 m hacia arriba de fábrica |
| **punto** | el vértice (hasta un punto) |
| **tapas** | sí: una curva cerrada da un cuerpo cerrado |

### Superficie por puntos

![Superficie por puntos](/images/manual/nodes/surface-from-points.png)

**Para qué.** Una superficie por puntos: una retícula de puntos (filas × columnas), o una nube suelta como los puntos
de un levantamiento topográfico.

| Entrada | Qué quiere decir |
|---|---|
| **puntos** | en retícula (dos niveles) o sueltos |
| **modo** | *retícula* o *nube* (unida en triángulos) |
| **suave** | sí: curva entre los puntos · no: facetas planas |

**Trucos.**
- Una **nube** da triángulos planos, que es lo correcto para un levantamiento: entre dos cotas medidas no se sabe
  más. Con **suave**, cada triángulo se curva, y sigue pasando exactamente por cada cota.
- Las formas con aristas vivas muestran pequeños escalones cuando son suaves: usa más puntos, o apaga suave.

### Superficie NURBS

![Superficie NURBS](/images/manual/nodes/nurbs-surface.png)

**Para qué.** Control total de una superficie libre: una retícula de puntos de control que la tiran, para cáscaras y
pieles libres.

| Entrada | Qué quiere decir |
|---|---|
| **puntos** | los puntos de control, filas × columnas |
| **nivel u**, **nivel v** | qué niveles son las filas y las columnas |
| **grado u**, **grado v** | `1`: facetas · `2`: curvas · `3`: suave, hasta `7` |
| **pesos** | cuánto tira cada punto |
| **cerrada u**, **cerrada v** | da la vuelta completa: un tubo; en las dos, un toro |

### Revolución

![Revolución](/images/manual/nodes/revolve.png)

**Para qué.** Un perfil que gira alrededor de un eje: una columna, una cúpula, un jarrón, una torre.

| Entrada | Qué quiere decir |
|---|---|
| **perfil** | la media sección que gira |
| **origen**, **eje** | un punto del eje y su dirección (vertical de fábrica) |
| **grados** | cuánto gira: `360` una vuelta completa |

### Barrido

![Barrido](/images/manual/nodes/sweep.png)

**Para qué.** Un perfil que recorre un camino sin torcerse: un pasamanos, una moldura, una viga curva, un tubo.

| Entrada | Qué quiere decir |
|---|---|
| **perfil** | la sección que recorre |
| **camino** | la curva por la que va |
| **camino 2** | opcional: un segundo camino; el perfil se estira para tocar los dos |
| **colocar** | *donde está* (dibujado al inicio del camino) o *centrado en el camino* (dibujado en cualquier lugar) |
| **giro** | cuántos grados gira a lo largo de todo el camino |

### Superficie por red de curvas

![Superficie por red de curvas](/images/manual/nodes/network-surface.png)

**Para qué.** Una superficie por una red de curvas en dos direcciones: las costillas de un casco o de una cubierta
libre.

**Cómo.** Conecta una familia de curvas a **curvas u** y la otra a **curvas v**; cada curva de una familia debe
cruzar todas las de la otra.

### Superficie por bordes

![Superficie por bordes](/images/manual/nodes/edge-surface.png)

**Para qué.** Una superficie tendida entre dos, tres o cuatro bordes que se juntan en las esquinas: una losa o una
cubierta con bordes curvos.

**Cómo.** Conecta los bordes a **a**, **b**, **c** y **d**, en cualquier orden. Con dos, una superficie reglada; con
tres, un lado se cierra en un punto.

## Trabajar sobre una superficie

### Puntos de superficie

![Puntos de superficie](/images/manual/nodes/surface-points.png)

**Para qué.** Puntos sobre una superficie, o hacia dónde mira ahí: para pararle columnas, anclajes o piezas encima.

| Entrada | Qué quiere decir |
|---|---|
| **qué** | *puntos* o *normales* (hacia dónde mira) |
| **modo** | *rejilla*: cantidad u × cantidad v de borde a borde · *centros*: el centro de cada panel · *fracciones*: en ciertas u y v |
| **cantidad u**, **cantidad v** | cuántos en cada dirección |
| **u**, **v** | las fracciones, varias con `;` |

### Isocurvas

![Isocurvas](/images/manual/nodes/isocurves.png)

**Para qué.** Las líneas propias de la superficie, en u o en v: costillas, montantes, un trazado que sigue la forma.

| Entrada | Qué quiere decir |
|---|---|
| **dirección** | *u* o *v* |
| **modo** | *partes* (repartidas parejo) o *fracción* (en ciertas posiciones) |
| **cantidad**, **posiciones** | cuántas, o dónde |

### Parte de superficie

![Parte de superficie](/images/manual/nodes/sub-surface.png)

**Para qué.** El pedazo de una superficie entre dos fracciones de u y dos de v: un paño de una cubierta, un gajo de
una cúpula.

### Punto más cercano en superficie

![Punto más cercano en superficie](/images/manual/nodes/closest-point-on-surface.png)

**Para qué.** El punto de una superficie más cercano a cada punto: para llevar algo sobre ella, o saber su u y v ahí,
a qué distancia está, o hacia dónde mira la superficie.

**Cómo.** Conecta los **puntos** y la **superficie**, y elige qué **da**: *punto*, *u v*, *distancia* o *normal*.

### Curva sobre superficie

![Curva sobre superficie](/images/manual/nodes/curve-on-surface.png)

**Para qué.** Una curva acostada sobre una superficie que sigue cada lomo: un camino sobre una cubierta, una costura
en una membrana.

**Cómo.** Dale puntos por su u y su v, desde **Punto más cercano en superficie** (*u v*) o con un **Punto** donde x es
u e y es v.

### Geodésica

![Geodésica](/images/manual/nodes/geodesic.png)

**Para qué.** El camino más corto entre dos puntos sobre una superficie, como un hilo tenso sobre ella. Los listones
puestos sobre geodésicas quedan rectos en su propio plano: por eso los usan las gridshells.

| Entrada | Qué quiere decir |
|---|---|
| **desde**, **hasta** | los puntos de inicio y de llegada, una llegada por cada inicio |
| **mostrar** | las *curvas*, sus *largos*, los *cruces* (los nudos de una gridshell) o las *barras* entre cruces |

### Curvatura de superficie

![Curvatura de superficie](/images/manual/nodes/surface-curvature.png)

**Para qué.** Para saber si una superficie se puede hacer con chapa plana, y cuánto se curva.

| Entrada | Qué quiere decir |
|---|---|
| **qué** | *gaussiana*: cero, se hace con chapa plana; positiva, como una cúpula; negativa, como una silla de montar · *media*: cuánto se curva · *desarrollable*: sí o no |
| **modo**, **cantidad**, **u**, **v** | dónde, como en Puntos de superficie |

**Trucos.**
- Para ver la curvatura como colores sobre la superficie, usa el panel de la geometría (**Color → según un valor**).

### Invertir superficie

**Para qué.** Para voltear una superficie (su cara), o invertir o intercambiar su u y su v.

**Trucos.**
- **Engrosar** crece hacia la cara: inviértela para que crezca hacia el otro lado.

### Intersección

![Intersección](/images/manual/nodes/intersection.png)

**Para qué.** Donde se cruzan dos geometrías: dos superficies dan las curvas del cruce; una curva y una superficie,
los puntos.

### Partir superficie

![Partir superficie](/images/manual/nodes/split-surface.png)

**Para qué.** Una superficie partida en trozos por curvas proyectadas sobre ella: una chapa perforada y sus recortes.

| Entrada | Qué quiere decir |
|---|---|
| **curvas** | las curvas que la cortan, proyectadas desde **dirección** (desde arriba de fábrica) |
| **qué** | *todos los trozos* (el más grande primero), *el más grande* (la chapa perforada) o *los demás* (los recortes) |

### Booleana

![Booleana](/images/manual/nodes/boolean.png)

**Para qué.** Para unir, restar o intersecar cuerpos cerrados: un muro menos sus vanos, dos volúmenes en una sola
piel.

| Entrada | Qué quiere decir |
|---|---|
| **a**, **b** | cuerpos cerrados |
| **operación** | *unión*, *diferencia* (a menos b) o *intersección* |

### Desarrollar

![Desarrollar](/images/manual/nodes/unroll.png)

**Para qué.** Para estirar superficies sobre el plano y cortarlas de una plancha de metal, tablero o tela. Un cuerpo
de caras planas da su red, para recortar y plegar.

| Entrada | Qué quiere decir |
|---|---|
| **qué** | las piezas *desarrolladas*, sus *contornos* para cortar, los *pliegues* de una red, o el *estiramiento* de una superficie no desarrollable |
| **colocar** | *en fila* o *en su lugar* |
| **separación** | entre piezas |

**Trucos.**
- Una superficie desarrollable se estira sin deformarse; una que no lo es, como una cúpula, se estira aproximada y
  dice cuánto se deforma.

## Estructuras sobre una superficie

### Diagrid

![Diagrid](/images/manual/nodes/diagrid.png)

**Para qué.** Una malla de barras diagonales sobre una superficie, en rombos: una torre, una cúpula, una cubierta.

| Entrada | Qué quiere decir |
|---|---|
| **divisiones u**, **divisiones v** | rombos en cada dirección |
| **qué** | las *diagonales*, los *cruces* (nudos) o los *anillos* por los nudos |
| **barras** | *rectas* o *curvas* que siguen la superficie |
| **seguidas** | sí: cada diagonal de punta a punta como una sola barra (una hélice en una torre) |

**Trucos.**
- Con **Tubo** sobre las diagonales, la estructura; con **Tapa** sobre los anillos, las losas.

### Malla espacial

![Malla espacial](/images/manual/nodes/space-frame.png)

**Para qué.** Una estructura de dos capas sobre una superficie: el cordón superior sobre ella, el inferior corrido
medio módulo y bajado, y diagonales que los unen en pirámides.

| Entrada | Qué quiere decir |
|---|---|
| **divisiones u**, **divisiones v** | módulos en cada dirección |
| **canto** | la distancia entre los dos cordones |
| **qué** | todas las barras, un cordón, las diagonales, o los cruces de arriba o de abajo |

### Red de Chebyshev

![Red de Chebyshev](/images/manual/nodes/chebyshev-net.png)

**Para qué.** Cómo se acomoda una malla de listones al doblarse, o una tela al caer: cuadriláteros de cuatro lados
iguales. Para cubiertas de listones y gridshells.

| Entrada | Qué quiere decir |
|---|---|
| **u**, **v** | el punto de partida |
| **paso** | el largo de cada lado, entre nudos |
| **cantidad** | nudos a cada lado del inicio |
| **ángulo**, **giro** | el ángulo entre los dos listones de partida, y su giro |
| **qué** | todos los listones, una familia, o los nudos |

### Hypar

![Hypar](/images/manual/nodes/hypar.png)

**Para qué.** Para plegar cada panel en un paraboloide hiperbólico: dos esquinas opuestas suben y el panel se vuelve
una silla de rectas, como un papel doblado por una diagonal.

| Entrada | Qué quiere decir |
|---|---|
| **paneles** | paneles de cuatro esquinas: una Retícula, rectángulos |
| **elevación** | cuánto suben dos esquinas opuestas, en metros |
| **esquinas** | qué dos esquinas suben |
| **mostrar** | la *pieza plegada*, la *pieza desplegada* para cortar, el *pliegue* o el *lado más largo* |

### Costillas

![Costillas](/images/manual/nodes/ribs.png)

**Para qué.** Para cortar una forma en tablas paralelas cerradas contra una pared: un muro de costillas, un
cielorraso de listones, un banco rebanado. Mira [Dibuja la forma y después córtala](/es/manual/key-ideas/draw-then-cut/).

| Entrada | Qué quiere decir |
|---|---|
| **forma** | una superficie, una malla o un volumen |
| **cantidad**, **grosor** | cuántas costillas, y su grosor |
| **cortes** | *x*, *y*: costillas verticales · *z*: rebanadas horizontales |
| **espalda** | dónde está la pared de atrás |

### Encajar en superficie

![Encajar en superficie](/images/manual/nodes/surface-morph.png)

**Para qué.** Para cubrir una superficie con un módulo: la superficie se divide en celdas que siguen su curva, y el
módulo se encaja en cada una, curvándose con ella.

| Entrada | Qué quiere decir |
|---|---|
| **geometría** | el módulo, dibujado en cualquier lugar; vacío: las celdas mismas |
| **cantidad u**, **cantidad v** | celdas en cada dirección |
| **alto** | cuánto sube la parte de arriba del módulo desde la superficie |

### Tubo

![Tubo](/images/manual/nodes/pipe.png)

**Para qué.** Una barra a lo largo de cada curva: redonda (barandas, cables), rectangular (vigas, montantes) o con un
perfil que dibujas (una I, una L).

| Entrada | Qué quiere decir |
|---|---|
| **sección** | *redonda*, *rectangular* o *perfil* |
| **radio**, **lados** | para secciones redondas |
| **ancho**, **alto** | para las rectangulares |
| **perfil** | una curva dibujada alrededor del origen, en planta |
| **giro**, **tapas** | girar la sección; cerrar los extremos |

### Tubos

![Tubos](/images/manual/nodes/pipes.png)

**Para qué.** Un tubo alrededor de cada línea, todos fundidos en una sola piel con empalmes suaves en los nudos: una
sola estructura escultórica.

| Entrada | Qué quiere decir |
|---|---|
| **radio** | de los tubos |
| **empalme** | cuánto se rellenan los nudos; `0`: nada |
| **detalle** | más es más fino y más lento |
