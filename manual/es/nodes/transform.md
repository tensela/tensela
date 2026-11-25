---
title: Transformar
description: "Mover, girar, escalar, colocar, orientar, encajar, torcer, engrosar y enmarcar: todo lo que cambia dónde está una geometría y qué forma toma."
---

Transformar toma una geometría y cambia dónde está o qué forma tiene: copias a lo largo de una fachada,
quiebrasoles que giran, módulos que se curvan sobre una superficie. Estos nodos son rojo teja en el lienzo.

**Cada transformación trabaja sobre cada elemento.** Un Mover con una distancia que viene de una Serie de 6 valores da
6 copias; un Escalar cuyo factor viene de un Atractor achica cada panel según su propia medida.

## Llevarla a otro lugar

### Mover

![Mover](/images/manual/nodes/move.png)

**Para qué.** Llevar cada elemento a otro lugar: un piso más arriba, adelante de una fachada, a otro punto.

| Entrada | Qué quiere decir |
|---|---|
| **modo** | *vector* (hacia dónde y cuánto) o *de un punto a otro* (lo que está en *desde* termina en *hasta*) |
| **vector** | hacia dónde; hacia arriba de fábrica |
| **distancia** | si la das, el vector solo marca la dirección: `3` sube 3 m |
| **desde**, **hasta** | el punto base y dónde termina (de un punto a otro) |

**Trucos.**
- Para subir algo sin escribir coordenadas, da solo una **distancia**: sube.

### Colocar

![Colocar](/images/manual/nodes/place.png)

**Para qué.** Poner una pieza en cada punto, girada: un quiebrasol en cada panel, una columna en cada cruce.

| Entrada | Qué quiere decir |
|---|---|
| **geometría** | la pieza, dibujada alrededor del origen |
| **en** | los puntos donde van las copias |
| **giro** | grados, uno para todas o uno por punto |
| **eje** | sobre qué gira: *vertical*, *x* o *y* |

**Trucos.**
- Una **Caja** está centrada en el origen, así que gira sobre su propio centro. Mira [Tu primer proyecto](/es/manual/getting-started/first-project/).

### Orientar

![Orientar](/images/manual/nodes/orient.png)

**Para qué.** Llevar una pieza a otros lugares girándola hacia su dirección y su normal: un módulo en cada punto de
una superficie, una pieza a lo largo de una curva. Conserva forma y tamaño.

| Entrada | Qué quiere decir |
|---|---|
| **desde** | el punto de la pieza que va a *hasta* (su base, una esquina) |
| **hasta** | adónde va: un punto, o muchos |
| **dirección hasta** | hacia dónde mira su x ahí (unas tangentes); vacío: la x del mundo acostada en el lugar |
| **normal hasta** | qué es arriba ahí (las normales de una superficie) |

### Girar

![Girar](/images/manual/nodes/rotate.png)

**Para qué.** Girar cada elemento alrededor de un eje: vertical, x, y o cualquier dirección, por un centro.

| Entrada | Qué quiere decir |
|---|---|
| **grados** | cuánto gira |
| **eje** | *vertical*, *x*, *y* o *dirección* (una bisagra, la pendiente de una cubierta) |
| **centro** | un punto por donde pasa el eje |
| **dirección** | la dirección del eje, para *dirección* |

### Proyectar

![Proyectar](/images/manual/nodes/project.png)

**Para qué.** Llevar una geometría plana a una altura: su huella en el suelo, o en otro nivel.

## Cambiar su tamaño

### Escalar

![Escalar](/images/manual/nodes/scale.png)

**Para qué.** Agrandar o achicar cada elemento: paneles que se achican hacia un punto, una copia más pequeña.

| Entrada | Qué quiere decir |
|---|---|
| **factor** | más de 1 agranda, menos de 1 achica |
| **centro** | vacío: cada elemento sobre su propio centro |

### Escalar por ejes

![Escalar por ejes](/images/manual/nodes/scale-by-axis.png)

**Para qué.** Escalar distinto en x, y y z: un piso que se estira a lo ancho, una losa que se adelgaza.

| Entrada | Qué quiere decir |
|---|---|
| **x**, **y**, **z** | el factor en cada dirección |
| **centro** | vacío: cada elemento sobre su propio centro |

## Cambiar su forma

### Torcer

![Torcer](/images/manual/nodes/twist.png)

**Para qué.** Torcer una geometría alrededor de un eje vertical: abajo queda quieta, arriba gira. Una torre que se
retuerce.

| Entrada | Qué quiere decir |
|---|---|
| **grados** | cuánto gira arriba |
| **centro** | por dónde pasa el eje vertical |
| **desde** | a qué altura empieza a torcerse, de 0 (abajo) a 1 (arriba) |

### Encajar módulo

![Encajar módulo](/images/manual/nodes/morph.png)

**Para qué.** Encajar un módulo en cada celda, curvándose con ella: lo que llena la caja del módulo llena la celda,
por torcida que esté.

| Entrada | Qué quiere decir |
|---|---|
| **geometría** | el módulo, dibujado en cualquier lugar |
| **celdas** | las celdas: cajas, bloques (de Engrosar), paneles de una Retícula, u ocho esquinas movidas una por una |
| **alto** | para paneles: cuánto sube la celda desde el panel |

**Trucos.**
- Sobre una superficie curva, **Encajar en superficie** divide la superficie y encaja el módulo en un solo paso.

### Engrosar

![Engrosar](/images/manual/nodes/thicken.png)

**Para qué.** Darle espesor a cada rectángulo, un bloque, o a una superficie: losas, paneles con espesor, muros.

| Entrada | Qué quiere decir |
|---|---|
| **rectángulo** | los rectángulos o la superficie |
| **espesor** | positivo hacia afuera, negativo hacia adentro |

**Trucos.**
- Crece hacia la cara de la superficie: para que crezca hacia el otro lado, da un espesor negativo o invierte la
  superficie.

### Marco

![Marco](/images/manual/nodes/frame.png)

**Para qué.** Un marco con una abertura en cada panel, o solo la abertura (el vidrio). Aberturas que crecen según un
atractor dan una fachada que respira.

| Entrada | Qué quiere decir |
|---|---|
| **panel** | los paneles |
| **abertura** | la abertura respecto del panel, de 0 (cerrado) a 1 |
| **espesor** | `0`: un marco plano |
| **ancho** | el ancho del marco en metros, igual en todo el borde, en vez de la abertura |
| **salida** | el *marco*, o el *hueco* (el rectángulo de adentro) |

## Direcciones

### Vector

![Vector](/images/manual/nodes/vector.png)

**Para qué.** Una dirección con su largo, para usar donde va un punto o una dirección: en Mover, Línea por dirección,
Girar.

| Modo | Lo que da |
|---|---|
| *x, y, z* | escrito |
| *eje* | a lo largo de x, y o z |
| *de un punto a otro* | de **desde** a **hasta** |
| *unitario*, *a un largo* | la misma dirección, de largo 1 o del **largo** que des |
| *multiplicar* | por un **factor** (negativo lo invierte) |
| *sumar*, *invertir*, *perpendicular* | dos sumados, al revés, o perpendicular a dos |
