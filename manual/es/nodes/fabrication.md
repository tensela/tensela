---
title: Fabricación
description: Del modelo a la máquina. Secciones y waffles, encastres, piezas acostadas en planchas con su número, placas, paneles planos, biseles y una revisión antes de imprimir en 3D.
---

Fabricación lleva un diseño a la máquina: una cortadora láser, una fresadora, una impresora 3D. Estos nodos son
verde oliva en el lienzo. Las medidas van en metros de fábrica, como en todo Tensela: `0,003` es una plancha de 3 mm (o escribe `3 mm`; mira [Preferencias](/es/manual/window/preferences/)).

**El camino habitual a un archivo de corte:** corta la forma en tablas con **Secciones** (y **Encastres** para un
waffle), acuéstalas con **Acostar en planchas**, súmales sus números con **Números y planchas**, y exporta con
**Archivo → Exportar → Archivo de corte**: rojo para cortar, azul para grabar.

## Cortar la forma

### Secciones

![Secciones](/images/manual/nodes/sections.png)

**Para qué.** Cortar una forma en tablas del espesor de una plancha, cada una un contorno cerrado listo para cortar:
una maqueta de terreno, un paisaje rebanado, un pabellón de costillas. Pegadas en orden, las tablas rearman la forma.

| Entrada | Qué quiere decir |
|---|---|
| **forma** | una superficie, una malla o un cuerpo |
| **espesor**, **separación** | de las tablas, y entre una y la siguiente (`0`: pegadas) |
| **cortes** | *x*, *y*, *z* (tablas a nivel, apiladas), *radial* (como los gajos de una naranja) o *a lo largo de una curva* |
| **cantidad** | cuántas tablas radiales |
| **guía** | la curva que siguen las tablas, cada una a escuadra con ella (un espinazo, el eje de una torre inclinada) |
| **trozo** | cómo la sección de una superficie se vuelve pieza: una *franja* que la sigue, o *hasta la base* común |
| **fondo** | qué tan honda es la franja, o cuánto baja la base bajo el punto más bajo |
| **mostrar** | los *contornos* para cortar, o las *tablas* con su espesor, para verlas |

### Encastres

**Para qué.** Donde se cruzan dos familias de tablas (un waffle, una caja de huevos), una ranura hasta la mitad en
cada una: una ranurada desde arriba, la otra desde abajo. Ranuradas, las tablas entran una en otra y la estructura
se sostiene sola.

| Entrada | Qué quiere decir |
|---|---|
| **primero**, **segundo** | dos familias de tablas planas que se cruzan (Secciones en x y en y) |
| **espesor** | de las tablas: el ancho de cada ranura |
| **holgura** | lo que se suma a la ranura para que las tablas entren (láser: 0,1 a 0,2 mm; fresadora: más) |
| **ranurada** | qué familia va ranurada desde arriba |
| **mostrar** | la familia *primera* o *segunda* con sus ranuras, lista para acostar, o todas las *tablas* |

### Placas

![Placas](/images/manual/nodes/plates.png)

**Para qué.** Convertir cada cara de una forma en una placa con espesor, recortada desde cada borde para que las
placas mantengan la misma separación en cualquier ángulo. Para pabellones facetados de tableros.

| Entrada | Qué quiere decir |
|---|---|
| **forma** | una malla, una caja o una superficie: cada cara, una placa |
| **espesor**, **separación** | del tablero, y entre dos placas que se juntan |
| **mostrar** | las *placas*, sus *contornos* para acostar, los *ángulos* de las aristas, o los *retiros* |

### Planarizar

![Planarizar](/images/manual/nodes/planarize.png)

**Para qué.** Dejar planos los paneles de una superficie curva, para cortarlos de tableros o vidrio, sin que dejen de
juntarse esquina con esquina.

| Entrada | Qué quiere decir |
|---|---|
| **paneles** | los paneles de una superficie, que comparten sus esquinas (una Retícula sobre una superficie) |
| **mostrar** | los *paneles* planos, su *planitud* ahora, o su *planitud antes* |

**Trucos.**
- Es fácil en una bóveda o un rollo; en una silla de montar, los paneles se curvan un poco hacia adentro.

## A la máquina

### Acostar en planchas

![Acostar en planchas](/images/manual/nodes/lay-flat.png)

**Para qué.** Acostar piezas planas en planchas, listas para cortar: encajadas unas en otras, las pequeñas en los
huecos de las grandes, cada una con un número adentro, el mismo que le da la vista 3D.

| Entrada | Qué quiere decir |
|---|---|
| **trozos** | curvas cerradas planas: de Secciones, Encastres, Desarrollar… |
| **ancho**, **alto** | de la plancha (600 × 400 mm: la cama de un láser; 2440 × 1220 mm: un tablero para fresadora) |
| **separación**, **margen** | entre piezas, y desde el borde |
| **girar** | girar piezas un cuarto si caben mejor |
| **número** | el alto de los números grabados (`0`: sin números) |
| **origen** | dónde va la primera plancha |
| **más** | una segunda familia en las mismas planchas: los números llevan *A* y *B* |

**Trucos.**
- El panel dice cuántas planchas son y cuánto se aprovechan.
- Si una pieza no cabe, un aviso dice cuánto mide: usa planchas más grandes, o divide la pieza.

### Números y planchas

**Para qué.** Los números de las piezas acostadas por un Acostar en planchas, para grabar, o los contornos de sus
planchas. Siempre siguen a las piezas.

| Entrada | Qué quiere decir |
|---|---|
| **acostadas** | las piezas de un Acostar en planchas |
| **mostrar** | *números* o *planchas* |
| **letra**, **grosor**, **lectura**, **tipografía** | cómo se dibujan los números: un trazo, negrita o contorno; a lo largo de la plancha o girados |

### Bisel

**Para qué.** Tablas con sus bordes suavizados, para verlas, imprimirlas o fresarlas con una fresa de bisel. Un láser
siempre corta recto.

| Entrada | Qué quiere decir |
|---|---|
| **trozos** | contornos planos, o las tablas de Secciones |
| **espesor**, **medida** | de la tabla, y cuánto entra el bisel |
| **perfil** | *redondeado*, *chaflán*, *media caña*, o *propio* (dibujado con una **curva**) |
| **facetas** | del redondeado o la media caña |
| **caras** | *las dos caras*, *cara de arriba* o *cara de abajo* |

### Revisar impresión

![Revisar impresión](/images/manual/nodes/print-check.png)

**Para qué.** Saber si una pieza se puede imprimir en 3D, y si no, por qué y dónde: cerrada, cada arista entre dos
caras, las caras hacia afuera, sin cruzarse a sí misma, que quepa en la impresora, sin paredes demasiado delgadas.

| Entrada | Qué quiere decir |
|---|---|
| **geometría** | la pieza, o varias |
| **mostrar** | los *problemas* como líneas rojas, si está *lista*, o el volumen de la *impresora* alrededor |
| **ancho**, **fondo**, **alto** | el volumen de impresión |
| **espesor** | la pared más delgada que puede hacer (`0`: no se revisa) |

**Trucos.**
- Un rectángulo no está cerrado: no tiene volumen y no se puede imprimir. Dale espesor primero.
