---
title: Ambiente
description: El sol de cualquier lugar y fecha, sombras, qué tan de frente llega el sol a cada cara, energía solar y horas de sol, luz natural dentro de una sala, y el clima de un archivo meteorológico.
---

Ambiente trae el lugar al diseño: dónde está el sol, a qué caras llega, cuánta luz entra. Estos nodos son ámbar en el
lienzo.

**La hora es la hora local estándar, sin horario de verano.** `13,5` es la una y media. El **huso horario** son las
horas desde UTC sin horario de verano: Madrid `+1`, Montevideo `-3`.

## Sol y sombra

### Sol

![Sol](/images/manual/nodes/sun.png)

**Para qué.** Dónde está el sol para un lugar, un día y una hora, y su recorrido: el diagrama solar, el rayo de luz
para sombras y ángulos, su altura y azimut, la salida y la puesta.

| Entrada | Qué quiere decir |
|---|---|
| **lugar** | una ciudad de la lista, u *otro lugar* para dar su **latitud**, **longitud** y **huso horario** |
| **día**, **mes**, **hora** | el momento; cada uno puede ser una lista |
| **escala** | el radio del diagrama y la distancia del sol, en metros |
| **mostrar** | el *diagrama*, el *recorrido del día*, la *posición*, un *haz*, el *rayo*, la *altura*, el *azimut*, la *salida*… |

**Trucos.**
- El ▶ de la hora, en el panel, recorre el día: las sombras y los ángulos se mueven con él.
- Para **Sombra** e **Incidencia**, pon **mostrar** en *rayo*.

### Sombra

![Sombra](/images/manual/nodes/shadow.png)

**Para qué.** La sombra de una geometría con el rayo de un Sol: en el suelo, exacta, con su contorno y su área; o
sobre otras superficies (un terreno, una fachada), cara por cara.

| Entrada | Qué quiere decir |
|---|---|
| **geometría** | lo que hace sombra |
| **rayo** | el rayo de un Sol; con una lista de horas, las sombras de todas |
| **suelo** | la altura del suelo |
| **superficies** | opcional: donde cae en vez del suelo, cara por cara |
| **mostrar** | la *sombra*, su *contorno*, su *área*, o las caras *al sol* o *en sombra* |

### Incidencia

![Incidencia](/images/manual/nodes/incidence.png)

**Para qué.** Qué tan de frente llega el sol a cada cara: 1 cuando cae a escuadra, 0 cuando roza o viene de atrás.
Para paneles que se abren o cierran con el sol, o para ver qué lado de un edificio recibe sol.

| Entrada | Qué quiere decir |
|---|---|
| **caras** | paneles, una malla, una superficie o una caja |
| **rayo** | el rayo de un Sol; con una lista de horas, su promedio |
| **lado** | *su cara* (hacia donde mira cada cara) o *las dos caras* |
| **mostrar** | *sol que llega* (1 a 0) o el *ángulo* desde la cara, en grados |

## Energía y luz

### Asoleamiento

![Asoleamiento](/images/manual/nodes/insolation.png)

**Para qué.** La energía solar que recibe cada cara en un período, con lo que la sombrea: en kWh/m², las horas de
sol, o cuánto cielo ve. Para la ganancia pasiva (mucho sol en invierno, poco en verano) y para ubicar paneles
solares. Una estimación para comparar opciones, no un cálculo energético ni de rendimiento.

| Entrada | Qué quiere decir |
|---|---|
| **caras** | lo que se analiza |
| **obstrucciones** | opcional: lo que la sombrea (vecinos, árboles, el resto del edificio) |
| **clima** | opcional: un nodo **Clima**, para el sol real de cada hora; sin él, un cielo despejado |
| **lugar** y su **latitud**, **longitud**, **huso horario** | el lugar |
| **período** | *año*, *verano*, *invierno*, *mes* o *día* |
| **mostrar** | *radiación*, *directa*, *difusa*, *horas de sol* o *factor de cielo* |

**Trucos.**
- Pinta las caras según su valor (**Color → según un valor**) para ver el resultado sobre el edificio.

### Luz natural

**Para qué.** Cuánta luz natural llega a unos puntos dentro de una sala bajo un cielo nublado: el factor de luz
diurna, los lux, y el promedio y la uniformidad de la sala. Una estimación simplificada para comparar opciones; para
normativa o certificación, una simulación validada.

| Entrada | Qué quiere decir |
|---|---|
| **puntos** | dónde se mide: una retícula a la altura de un escritorio, de 0,7 a 0,85 m |
| **sala** | la sala: una caja, o sus muros, piso y cielorraso |
| **vidrio** | las ventanas: rectángulos sobre los muros |
| **obstrucciones** | opcional: lo que tapa el cielo afuera (quiebrasoles, aleros, vecinos) |
| **transmisión** | cuánta luz deja pasar el vidrio, en % (doble vidrio, unos 70) |
| **reflexión** | cuánta luz reflejan los muros, en % (muros claros, unos 70; oscuros, 30) |
| **mostrar** | *factor de luz diurna*, *iluminancia*, *componente de cielo*, *iluminancia media*, *factor de luz diurna medio* o *uniformidad* |

**Trucos.**
- Como referencia, suele tomarse 2 % como una sala bien iluminada y 5 % como una muy luminosa.

### Clima

**Para qué.** El clima de un lugar a partir de un archivo meteorológico (`.epw`): temperatura, humedad, sol y viento
de cada hora de un año típico. Conectado a **Asoleamiento**, el sol real en vez de un cielo despejado.

| Entrada | Qué quiere decir |
|---|---|
| **archivo** | un archivo meteorológico `.epw`, o el `.zip` en que viene (climate.onebuilding.org) |
| **mostrar** | *temperatura*, *humedad*, *radiación*, *velocidad* o *dirección del viento*, *nubosidad* |
| **por** | *hora* (8760), *día* (365) o *mes* (12) |
