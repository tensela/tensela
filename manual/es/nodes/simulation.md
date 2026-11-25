---
title: Simulación
description: Formas que se encuentran solas bajo su peso, una primera revisión de barras, y dónde debe ir el material.
---

Simulación deja que las fuerzas dibujen la forma, o te dice cuánto trabaja una estructura. Estos nodos son rosa en el
lienzo. Las fuerzas van en newtons: 1 kg pesa unos 10 N, 1 kN son 1000 N.

## Equilibrio

![Equilibrio](/images/manual/nodes/equilibrium.png)

**Para qué.** La forma que toma en reposo un cable, una red, una membrana o una cáscara, colgada de sus apoyos o
apoyada en un piso, bajo su peso y sus cargas: la búsqueda de forma de las maquetas colgantes, las redes de cables,
las telas tensadas, las películas de jabón y las cáscaras. Invertida, la bóveda que trabaja sobre todo a
compresión.

**Cómo.** Conecta lo que cuelga a **forma**: curvas (cables) o una malla (una membrana, desde **Malla de
superficie**). Siempre da la forma ya en reposo: cambias un apoyo o una carga y vuelve a colgar.

| Entrada | Qué quiere decir |
|---|---|
| **forma** | curvas o líneas (cables) o una malla (una membrana) |
| **tramos** | en cuántos tramos se divide cada curva; una malla conserva los suyos |
| **apoyos**, **más apoyos** | *extremos o esquinas*, todo el *borde*, el *inicio*, o *ninguno*; y puntos que también la sostienen |
| **peso propio** | de todo, en N |
| **cargas**, **carga** | puntos donde cuelga una carga, y cuánta |
| **rigidez** | la fuerza que la estiraría al doble de su largo: más, se estira menos |
| **largo en reposo** | cuánto quiere medir cada tramo: `1` elástico, menos pretensado, `0` una película de jabón |
| **diagonales** | ninguna, una red de cables; una o las dos por cuadro, una lámina que conserva su forma |
| **flexión** | `0` un cable o una tela; `0,001` goma; `0,01` o más, una cáscara |
| **piso** | la altura de un piso donde se apoya; con piso no necesita apoyos |
| **lazos** | líneas cuyos extremos se juntan, como puntadas (un fruncido, un pliegue) |
| **gravedad** | hacia dónde va el peso; hacia arriba da la forma que trabaja a compresión |
| **instante** | `1` en reposo, `0` el inicio: el ▶ del panel lo recorre |
| **mostrar** | la *forma*, los *tramos*, su *alargamiento* o sus *fuerzas* |

**Trucos.**
- Los apoyos se pueden mover a mano en la vista 3D con **Mover apoyos**: la forma los sigue.
- Las fuerzas sirven para encontrar la forma, no para dimensionar cables ni membranas.

## Análisis de barras

![Análisis de barras](/images/manual/nodes/bar-analysis.png)

**Para qué.** Cuánto se deforma una estructura de barras y cuánto trabaja cada barra: vigas, columnas, pórticos,
cerchas, gridshells. Un primer dimensionado: no revisa pandeo ni uniones, y no aplica coeficientes de seguridad ni
normas: una aproximación para diseñar, que revisa un ingeniero estructural.

| Entrada | Qué quiere decir |
|---|---|
| **forma** | las barras: líneas, curvas o una malla (cada arista una barra) |
| **diagonales** | de cada cuadro de una malla: ninguna (un marco) o arriostrada como una cercha |
| **apoyos**, **apoyo** | puntos sostenidos, y cómo: *empotrado*, *articulado* o *rodillo* |
| **cargas**, **carga**, **carga por metro** | cargas puntuales, y una carga repartida en cada barra (una losa, nieve) |
| **peso propio** | sumar el peso de las barras |
| **material** | acero, madera, madera laminada, hormigón o aluminio |
| **sección** | `IPE 300`, `HEA 200`, `rect 200x400`, `tube 200x100x8`, `pipe 168x8`… en mm |
| **mostrar** | la *deformada*, los *desplazamientos*, los *axiles*, los *momentos*, el *aprovechamiento*, las *reacciones*, el *mayor* de cada uno, o el *peso total* |

**Trucos.**
- Un **aprovechamiento** sobre 1 (100 %) quiere decir que la barra no alcanza: una sección mayor, o más apoyos. Por
  debajo de 1 no es una garantía: es una primera revisión.

## Optimización topológica

![Optimización topológica](/images/manual/nodes/topology-optimization.png)

**Para qué.** Dónde debe ir el material, dentro de una región, para llevar unas cargas a unos apoyos con lo mínimo.
Empieza lleno y delgado, y vuelta a vuelta el material se va adonde trabaja, hasta que queda una estructura: los
arcos y diagonales de una viga, las patas de un puente. Un estudio de forma: el resultado hay que diseñarlo y
verificarlo como estructura.

| Entrada | Qué quiere decir |
|---|---|
| **región** | dónde puede ir el material: un contorno (2D) o un cuerpo (3D) |
| **vacíos**, **partes macizas** | lo que debe quedar vacío (una puerta) o lleno (una losa) |
| **apoyos**, **rodillos** | puntos o contornos sostenidos en toda dirección, o solo en la del peso |
| **cargas**, **carga** | dónde se aplica una fuerza, y cuánta |
| **densidad** | cuánto de la región queda lleno: `0,3` deja el 30 % |
| **resolución** | celdas a lo largo del lado más largo: más, más fino y más lento |
| **mostrar** | la *forma* (contornos para extruir o cortar), la *placa*, las *celdas*, la *densidad*, la *tensión*… |
